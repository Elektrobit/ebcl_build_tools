import re
import pytest
from pathlib import Path
from typing import Any, TypeGuard

from ebcl.tools.hypervisor.config_gen import HvFileGenerator
from ebcl.tools.hypervisor.model import HVConfig, VNetRef, VirtioBlockRef
from ebcl.tools.hypervisor.model_gen import ConfigError

test_data = Path(__file__).parent / "data"


def test_empty(tmp_path: Path) -> None:
    gen = HvFileGenerator(str(test_data / "empty.yaml"), str(tmp_path))
    assert gen.config
    assert isinstance(gen.config, HVConfig)
    assert gen.config.vbus == []
    assert len(gen.config.modules) == 0


def test_device(tmp_path: Path) -> None:
    gen = HvFileGenerator(str(test_data / "test_devices.yaml"), str(tmp_path))
    assert isinstance(gen.config, HVConfig)
    assert len(gen.config.vbus) == 2

    vbus = gen.config.get_vbus("empty_vbus")
    assert vbus
    assert vbus.devices == []

    vbus = gen.config.get_vbus("a_vbus")
    assert vbus
    assert len(vbus.devices) == 2
    assert vbus.devices[0].name == "emtpy_device"
    assert vbus.devices[0].compatible is None
    assert vbus.devices[0].mmios == []
    assert vbus.devices[0].irqs == []

    assert vbus.devices[1].name == "a_device"
    assert vbus.devices[1].compatible == "i am compatible"
    assert len(vbus.devices[1].mmios) == 2
    vbus.devices[1].mmios[0].address == 0x123
    vbus.devices[1].mmios[0].size == 456
    vbus.devices[1].mmios[0].cached is False
    vbus.devices[1].mmios[1].address == 0x456
    vbus.devices[1].mmios[1].size == 789
    vbus.devices[1].mmios[1].cached is True

    assert len(vbus.devices[1].irqs) == 3
    assert vbus.devices[1].irqs[0].irq == 1
    assert vbus.devices[1].irqs[0].is_edge is False
    assert vbus.devices[1].irqs[0].type == "SPI"
    assert vbus.devices[1].irqs[0].offset == 32
    assert vbus.devices[1].irqs[1].irq == 2
    assert vbus.devices[1].irqs[1].is_edge is True
    assert vbus.devices[1].irqs[1].type == "PPI"
    assert vbus.devices[1].irqs[1].offset == 16
    assert vbus.devices[1].irqs[2].irq == 3
    assert vbus.devices[1].irqs[2].is_edge is False
    assert vbus.devices[1].irqs[2].type == "SGI"
    assert vbus.devices[1].irqs[2].offset == 0


def test_shm(tmp_path: Path) -> None:
    gen = HvFileGenerator(str(test_data / "test_shms.yaml"), str(tmp_path))
    assert isinstance(gen.config, HVConfig)
    assert len(gen.config.shms) == 4

    gen.config.shms[0].name == "shm_1"
    gen.config.shms[0].size == 123
    gen.config.shms[0].address is None
    gen.config.shms[1].name == "shm_2"
    gen.config.shms[1].size == 124
    gen.config.shms[1].address is None
    gen.config.shms[2].name == "shm_3"
    gen.config.shms[2].size == 0x1000
    gen.config.shms[2].address == 0x2000
    gen.config.shms[3].name == "shm_4"
    gen.config.shms[3].size == 0x1000
    gen.config.shms[3].address == 0x0

    # Ensure sorting of shms works as expected
    # i.e.: First shms with fixed address in address order then all others
    sorted_shms = sorted(gen.config.shms)
    sorted_shms[0].name == "shm_4"
    sorted_shms[0].name == "shm_3"
    sorted_shms[0].name == "shm_1"
    sorted_shms[0].name == "shm_2"


def test_vms(tmp_path: Path) -> None:
    gen = HvFileGenerator(str(test_data / "test_vms.yaml"), str(tmp_path))

    assert isinstance(gen.config, HVConfig)
    assert len(gen.config.vms) == 2

    assert set(gen.config.modules) == set([
        "kernel_1",
        "dtb_1",
        "kernel_2",
        "dtb_2",
        "this is an initrd"
    ])

    assert gen.config.vms[0].name == "vm_1"
    assert gen.config.vms[0].kernel == "kernel_1"
    assert gen.config.vms[0].ram == 10
    assert gen.config.vms[0].cpus == 1
    assert gen.config.vms[0].cmdline == ""
    assert gen.config.vms[0].initrd is None
    assert gen.config.vms[0].dtb == "dtb_1"
    assert gen.config.vms[0].vbus is None
    assert gen.config.vms[0].shms == []
    assert gen.config.vms[0].virtio_block == []
    assert gen.config.vms[0].vnets == []

    assert gen.config.vms[1].name == "vm_2"
    assert gen.config.vms[1].kernel == "kernel_2"
    assert gen.config.vms[1].ram == 20
    assert gen.config.vms[1].cpus == 2
    assert gen.config.vms[1].cmdline == "a wonderful kernel cmdline"
    assert gen.config.vms[1].initrd == "this is an initrd"
    assert gen.config.vms[1].dtb == "dtb_2"
    assert gen.config.vms[1].vbus == gen.config.vbus[0]
    assert gen.config.vms[1].shms == [gen.config.shms[0], gen.config.shms[1]]
    assert gen.config.vms[1].virtio_block == []
    assert gen.config.vms[1].vnets == []


def test_vnets(tmp_path: Path) -> None:
    def is_vnet_list(val: list[Any]) -> TypeGuard[list[VNetRef]]:
        return len(val) == 0 or all(isinstance(x, VNetRef) for x in val)

    gen = HvFileGenerator(str(test_data / "test_vnets.yaml"), str(tmp_path))

    assert isinstance(gen.config, HVConfig)

    assert len(gen.config.vms) == 2

    assert len(gen.config.vnets) == 4
    assert gen.config.vnets[0].name == "vnet_1"
    assert gen.config.vnets[0].users == [gen.config.vms[0], gen.config.vms[1]]
    assert gen.config.vnets[1].name == "vnet_2"
    assert gen.config.vnets[1].users == [gen.config.vms[0]]
    assert gen.config.vnets[2].name == "vnet_3"
    assert gen.config.vnets[2].users == [gen.config.vms[0], gen.config.vms[1]]
    assert gen.config.vnets[3].name == "vnet_4"
    assert gen.config.vnets[3].users == [gen.config.vms[1]]

    vnets = gen.config.vms[0].vnets
    assert len(vnets) == 3
    assert is_vnet_list(vnets)
    assert vnets[0].vnet == gen.config.vnets[0]
    assert vnets[0].name == vnets[0].vnet.name, "It is possible to access vnet properties from the ref"
    assert vnets[0].site_a is True
    assert vnets[1].vnet == gen.config.vnets[1]
    assert vnets[1].site_a is True
    assert vnets[2].vnet == gen.config.vnets[2]
    assert vnets[2].site_a is True

    vnets = gen.config.vms[1].vnets
    assert len(vnets) == 3
    assert is_vnet_list(vnets)
    assert vnets[0].vnet == gen.config.vnets[0]
    assert vnets[0].site_a is False
    assert vnets[1].vnet == gen.config.vnets[2]
    assert vnets[1].site_a is False
    assert vnets[2].vnet == gen.config.vnets[3]
    assert vnets[2].site_a is True


def test_virtio_blocks(tmp_path: Path) -> None:
    def is_vioref_list(val: list[Any]) -> TypeGuard[list[VirtioBlockRef]]:
        return len(val) == 0 or all(isinstance(x, VirtioBlockRef) for x in val)
    gen = HvFileGenerator(str(test_data / "test_virtio_blocks.yaml"), str(tmp_path))

    assert isinstance(gen.config, HVConfig)

    assert len(gen.config.vms) == 3

    assert len(gen.config.vio_block) == 3
    gen.config.vio_block[0].name = 'blk_1'
    gen.config.vio_block[0].server = gen.config.vms[0]
    gen.config.vio_block[0].client = gen.config.vms[1]
    gen.config.vio_block[1].name = 'blk_2'
    gen.config.vio_block[1].server = gen.config.vms[0]
    gen.config.vio_block[1].client = gen.config.vms[1]
    gen.config.vio_block[2].name = 'blk_3'
    gen.config.vio_block[2].server = gen.config.vms[1]
    gen.config.vio_block[2].client = gen.config.vms[2]

    vios = gen.config.vms[0].virtio_block
    assert is_vioref_list(vios)
    assert len(vios) == 2
    assert vios[0].vio == gen.config.vio_block[0]
    assert vios[0].name == vios[0].vio.name, "It is possible to access vio directly from the ref"
    assert vios[0].is_server is True
    assert vios[1].vio == gen.config.vio_block[1]
    assert vios[1].is_server is True

    vios = gen.config.vms[1].virtio_block
    assert is_vioref_list(vios)
    assert len(vios) == 3
    assert vios[0].vio == gen.config.vio_block[2]
    assert vios[0].is_server is True
    assert vios[1].vio == gen.config.vio_block[0]
    assert vios[1].is_server is False
    assert vios[2].vio == gen.config.vio_block[1]
    assert vios[2].is_server is False

    vios = gen.config.vms[2].virtio_block
    assert is_vioref_list(vios)
    assert len(vios) == 1
    assert vios[0].vio == gen.config.vio_block[2]
    assert vios[0].is_server is False


def test_vnet_too_many_users(tmp_path: Path) -> None:
    with pytest.raises(
        ConfigError,
        match="^" + re.escape("VM vm_3: VNet vnet_1 is already used by two vms (vm_1 and vm_2)") + "$"
    ):
        HvFileGenerator(str(test_data / "test_vnet_too_many_users.yaml"), str(tmp_path))


def test_virtio_block_multiple_servers(tmp_path: Path) -> None:
    with pytest.raises(
        ConfigError,
        match="^" + re.escape("VM vm_2: Server for Virtio Block blk_1 already set to vm_1") + "$"
    ):
        HvFileGenerator(str(test_data / "test_virtio_block_multiple_servers.yaml"), str(tmp_path))


def test_virtio_block_multiple_clients(tmp_path: Path) -> None:
    with pytest.raises(
        ConfigError,
        match="^" + re.escape("VM vm_2: Client for Virtio Block blk_1 already set to vm_1") + "$"
    ):
        HvFileGenerator(str(test_data / "test_virtio_block_multiple_clients.yaml"), str(tmp_path))
