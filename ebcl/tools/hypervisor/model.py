from __future__ import annotations

import logging

from .model_gen import BaseModel


class VNet:
    """
    Represents a virtual network interface pair
    """

    name: str
    """Name of the net to identify it in the device tree and the configuration"""
    users: list[VM]
    """Users of the vm net"""

    def __init__(self, name: str) -> None:
        self.name = name
        self.users = []

    def add_user(self, vm: VM) -> None:
        """
        add a user to the virtual interface pair
        Since this is a pair, only two users are allowed
        """
        if len(self.users) == 2:
            logging.error("VMNet %s is already used by two vms", self.name)
        self.users.append(vm)

    def __repr__(self) -> str:
        return f"VNet({self.name})"


class VNetRef:
    """
    Reference to one side of a virtual network interface pair
    """

    vnet: VNet
    """Link to the vmnet"""
    site_a: bool
    """True for one of the two sides"""

    def __init__(self, vnet: VNet, site_a: bool) -> None:
        self.vnet = vnet
        self.site_a = site_a

    def __getattr__(self, attr: str):
        return getattr(self.vnet, attr)

    def __repr__(self) -> str:
        return f"VNetRef({self.name})"


class VirtioBlock:
    """
    A virtio block device that has a server and a client interface.
    The server interface is a console interfaces that has to be served by vio_filed
    The client interface is a standard virtio block interface.
    """

    name: str
    """Name used for identification in the configuration and device tree"""
    server: VM | None = None
    """Server VM"""
    client: VM | None = None
    """Client VM"""

    def __init__(self, name) -> None:
        self.name = name

    def __repr__(self) -> str:
        return f"VirtioBlock({self.name})"


class VirtioBlockRef:
    """
    A reference to the client or server side of a virtio block interface
    """
    vio: VirtioBlock
    """Link to the virtio block description"""
    is_server: bool
    """True if this is the link of the server side"""

    def __init__(self, vio: VirtioBlock, is_server: bool) -> None:
        self.vio = vio
        self.is_server = is_server

    def __getattr__(self, attr: str):
        return getattr(self.vio, attr)

    def __repr__(self) -> str:
        return f"VirtioBlockRef({self.name})"


class MMIO(BaseModel):
    """
    A region of memory, that is used by a Device
    """

    address: int
    """Start of the region"""
    size: int
    """Size of the region"""
    cached: bool
    """If cached is true, the memory is mapped as normal memory instead of device memory"""

#    def __init__(self, config: dict) -> None:
#        self.address = config["address"]
#        self.size = config["size"]
#        self.cached = config["cached"]

    def __repr__(self) -> str:
        return f"MMIO(0x{self.address:x}, 0x{self.size:x})"


class IRQ(BaseModel):
    """
    Describes an interrupt used by a Device.
    """

    irq: int
    """The interrupt number"""
    is_edge: bool
    """If true, the interrupt is rising edge triggered, otherwise it is level high triggered."""
    type: str
    """SGI, PPI or SPI"""
    trigger: str
    """Trigger type enum"""

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self.is_edge = self.trigger == "rising_edge"

    @property
    def offset(self) -> int:
        if self.type == "SGI":
            return 0
        elif self.type == "PPI":
            return 16
        elif self.type == "SPI":
            return 32
        return 0


class Device(BaseModel):
    """
    Describes a devices, that is passed through to a vm.
    """

    name: str
    """Name of the device"""
    compatible: str | None
    """Compatible string for mapping the device to the device tree"""
    mmios: list[MMIO]
    """List of mapped memory regions for the device"""
    irqs: list[IRQ]
    """List of interrupts used by the device"""

    def __repr__(self) -> str:
        return f"Device({self.name})"


class VBus(BaseModel):
    """
    A virtual bus, that contains devices
    """

    name: str
    """Name of the virtual bus used to identify it in the configuration"""
    devices: list[Device]
    """List of devices that are part of the bus"""

#    def __init__(self, name: str, config: dict) -> None:
#        self.name = name
#
#        self.devices = []
#        for devname, devconfig in config.items():
#            self.devices.append(Device(devname, devconfig))

    def __repr__(self) -> str:
        return f"VBus({self.name}, {', '.join(map(repr, self.devices))})"


class SHM(BaseModel):
    """
    A shread memory region, that can be assigned to multiple vms
    """

    name: str
    """Name of the region as identifier in the configuration and the device tree"""
    size: int
    """Size of the region in bytes"""
    address: int | None
    """Fixed start address of the region, if required"""

    def __lt__(self, other: SHM) -> bool:
        """
        Ensure that shared memory segments with a specified address
        are allocated first in ascending order
        """
        return (self.address and True or False) and (not other.address or self.address < other.address)

    def __repr__(self) -> str:
        return f"SHM({self.name})"


class Cons(BaseModel):
    """Configuration for the console multiplexer"""

    default_vm: str | None
    """Automatically attach this vm to cons on startup"""


class VirtioBlockNode(BaseModel):
    """A Virtio block property of VM"""
    servers: list[str]
    """List of server virtio block interface names"""
    clients: list[str]
    """List of client virtio block interface names"""


class VM(BaseModel):
    """
    Describes a virtual machine
    """

    name: str
    """Name of the virtual machine used in console output"""
    kernel: str
    """The kernel image name"""
    ram: int
    """The amount of ram assigned to this vm in bytes"""
    initrd: str | None
    """The initrd file name"""
    dtb: str
    """The device tree file name"""
    cmdline: str
    """The kernel command line"""
    cpus: int
    """The cpu mask to use for this vm (e.g. 0x3 -> CPU 0 and 1)"""
    vbus: str | VBus | None
    """The virtual bus to connect to this vm"""
    vnets: list[str] | list[VNetRef]
    """List of virual network pairs used by this vm"""
    shms: list[str] | list[SHM]
    """List of shared memory regions available to this vm"""
    virtio_block = list[VirtioBlockNode] | list[VirtioBlockRef]

    def finalize(self, registry: HVConfig) -> None:
        registry.register_module(self.kernel)
        registry.register_module(self.dtb)
        if self.initrd:
            registry.register_module(self.initrd)

        if not isinstance(self.vbus, VBus):
            self.vbus = registry.get_vbus(self.vbus)
        self.shms = registry.get_shms(self.shms)  # type: ignore
        self.vnets = list(
            map(lambda x: registry.register_vnet(x, self), self.vnets)  # type: ignore
        )

        if self.virtio_block:
            server = map(
                lambda x: registry.register_virtio_block(x, self, True), self.virtio_block.servers  # type: ignore
            )
            clients = map(
                lambda x: registry.register_virtio_block(x, self, False), self.virtio_block.clients  # type: ignore
            )
            self.virtio_block: list[VirtioBlockRef] = list(server) + list(clients)  # type: ignore
        else:
            self.virtio_block = []

    def __repr__(self) -> str:
        return self.name


class HVConfig(BaseModel):
    """
    Complete configuration of the hypervisor.
    """
    vms: list[VM]
    """List of vms defined"""
    cons: Cons
    """Console mupltiplexer configuration"""
    vnets: list[VNet]
    """List of virtual network interface pairs"""
    vio_block: list[VirtioBlock]
    """List of virtio block interface pairs"""
    vbus: list[VBus]
    """List of registered virtual busses"""
    shms: list[SHM]
    """List of registered shared memory regions"""
    modules: set[str]
    """List of required hypervisor modules"""

    def register_vnet(self, name: str, user: VM) -> VNetRef:
        """
        Register a virtual network link user.
        The vnet is matched by the name and if it does not exist yet it will be created.
        """
        for net in self.vnets:
            if net.name == name:
                vnet = net
                break
        else:
            vnet = VNet(name)
            self.vnets.append(vnet)
        vnet.add_user(user)
        return VNetRef(vnet, len(vnet.users) == 1)

    def register_virtio_block(self, name: str, user: VM, is_server: bool) -> VirtioBlockRef:
        """
        Register a virtio block interface user.
        The interface is matched by name and if it does not exist yet it will be created.
        """
        for cur in self.vio_block:
            if cur.name == name:
                vio = cur
                break
        else:
            vio = VirtioBlock(name)
            self.vio_block.append(vio)
        if is_server:
            if vio.server:
                logging.error("Server for Virtio Block %s already set", vio.name)
            else:
                vio.server = user
        else:
            if vio.client:
                logging.error("Client for Virtio Block %s already set", vio.name)
            else:
                vio.client = user
        return VirtioBlockRef(vio, is_server)

    def get_vbus(self, name: str | None) -> VBus | None:
        """
        Returns an existing virtual bus with the given name
        """
        if not name:
            return None
        for vbus in self.vbus:
            if vbus.name == name:
                return vbus
        logging.error("Vbus %s not defined", name)
        return None

    def get_shms(self, names: list[str]) -> list[SHM]:
        """
        Returns all registered shared memories matched by names
        """
        out = list(filter(lambda x: x.name in names, self.shms))
        if len(out) != len(names):
            missing = set(names) - set([out.name for out in out])
            logging.error("Not all used shms are defined: %s", ", ".join(missing))
        return out

    def register_module(self, name: str) -> None:
        """
        Add a module to the list of required hypervisor modules.
        """
        self.modules.add(name)

    def __init__(self, config: dict) -> None:
        self.vnets = []
        self.vio_block = []
        self.modules = set()

        super().__init__(config)

        for vm in self.vms:
            vm.finalize(self)
