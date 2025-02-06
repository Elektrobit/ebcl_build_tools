package.path = "rom/?.lua"

local L4 = require "L4";
local system = require "system"

system.start_cons("-ka -c vm-li")

local shms = {
    wdgshm = create_ds(
        0x1000,
        nil,
        0x40173000,
        0x40173fff,
        L4.Mem_alloc_flags.Continuous | L4.Mem_alloc_flags.Pinned
    ),
    fbshm = create_ds(
        0x3000000,
        nil,
        nil,
        nil,
        L4.Mem_alloc_flags.Continuous | L4.Mem_alloc_flags.Pinned
    ),
    proxycomshm = create_ds(
        0x200000,
        nil,
        nil,
        nil,
        L4.Mem_alloc_flags.Continuous | L4.Mem_alloc_flags.Pinned
    ),
    hicomshm = create_ds(
        0x21000,
        nil,
        nil,
        nil,
        L4.Mem_alloc_flags.Continuous | L4.Mem_alloc_flags.Pinned
    ),
    tmshm = create_ds(
        0x1000,
        nil,
        nil,
        nil,
        L4.Mem_alloc_flags.Continuous | L4.Mem_alloc_flags.Pinned
    ),
}

local io_busses = {
    vm_hw = 1,
}
system.start_io(io_busses, "rom/io.cfg")

local vnets = {
   vnet_li_hi = system.start_l4vio_net_p2p(),
}

local vio_blocks = {
   root = 1,
   data = 1,
}
system.start_virtio_block(vio_blocks)

system.start_vm(
    "vm-li",
    0,
    "Image_li",
    512,
    "ramdisk_base",
    "virt-li.dtb",
    "console=hvc0 rdinit=/init rw",
    0x03,
    {
        vnet_li_hi = vnets.vnet_li_hi.portA,
        root_server = vio_blocks.root.server,
        data_server = vio_blocks.data.server,
        vbus = io_busses.vm_hw,
        fbshm = shms.fbshm,
        proxycomshm = shms.proxycomshm,
    }
);
system.start_vm(
    "vm-hi",
    1,
    "Image_hi",
    128,
    nil,
    "virt-hi.dtb",
    "console=hvc0 ip=192.168.7.100::192.168.7.1:255.255.255.0 root=/dev/vda ro sdk_enable init=/hi_main",
    0x0c,
    {
        vnet_li_hi = vnets.vnet_li_hi.portB,
        root_client = vio_blocks.root.client,
        data_client = vio_blocks.data.client,
        fbshm = shms.fbshm,
        proxycomshm = shms.proxycomshm,
        hicomshm = shms.hicomshm,
        tmshm = shms.tmshm,
        wdgshm = shms.wdgshm,
    }
);
