local L4 = require "L4";
local l = L4.default_loader;

local max_ds <const> = 16

function sched(prio_up, prio_base, cpus)
  return L4.Env.user_factory:create(L4.Proto.Scheduler, prio_up, prio_base, cpus);
end

function create_ds(size_in_bytes, align, lower, upper, flags)
  args = { L4.Proto.Dataspace, size_in_bytes, flags, align and align or 0 };

  if lower then
    table.insert(args, string.format("physmin=%x", lower));
  end

  if upper then
    table.insert(args, string.format("physmax=%x", upper));
  end

  return L4.Env.user_factory:create(table.unpack(args)):m("rws");
end

function start_cons(opts)
  l.log_fab = l:new_channel()

  return l:start(
    {
      log = L4.Env.log,
      scheduler = sched(0x44, 0x40, 0x1),
      caps = {cons = l.log_fab:svr()},
    },
    "rom/cons " .. opts
  )
end

function start_io(io_busses, files)
  local io_caps = {
    sigma0 = L4.cast(L4.Proto.Factory, L4.Env.sigma0):create(L4.Proto.Sigma0),
    icu    = L4.Env.icu
  }

  for k, v in pairs(io_busses) do
    local c = l:new_channel()
    io_busses[k] = c
    io_caps[k] = c:svr()
  end

  return l:start(
    {
      log = { "io", "white" },
      scheduler = sched(0x65, 0x60, 0x1),
      caps = io_caps,
    },
    "rom/io " .. files
  )
end

function start_l4vio_net_p2p()
  local vnp2p_ipc_gate = l:new_channel()
  l:start(
    {
      caps = {svr = vnp2p_ipc_gate:svr()},
      scheduler = sched(0x44, 0x40, 0x1),
      log = {"vnp2p", "yellow"},
    },
    "rom/l4vio_net_p2p"
  )

  return {
    portA = L4.cast(L4.Proto.Factory, vnp2p_ipc_gate):create(0, "ds-max=" .. max_ds):m("rwd"),
    portB = L4.cast(L4.Proto.Factory, vnp2p_ipc_gate):create(0, "ds-max=" .. max_ds):m("rwd")
  }
end


function start_vm(
  name,
  key,
  kernel,
  rammb,
  initrd,
  dtb,
  cmdline,
  cpus,
  extra_caps
)
  local c = {}
  c[#c + 1] = "-i"
  c[#c + 1] = "-v"
  c[#c + 1] = "-krom/" .. kernel
  c[#c + 1] = "-drom/" .. dtb
  if initrd then
    c[#c + 1] = "-rrom/" .. initrd
  end
  if cmdline and #cmdline > 0 then
    c[#c + 1] = "-c" .. cmdline
  end
  --c[#c + 1] = "-v"

  local caps = {
    ram = create_ds(
      rammb * 1024 * 1024,
      21,
      nil,
      nil,
      L4.Mem_alloc_flags.Continuous | L4.Mem_alloc_flags.Pinned | L4.Mem_alloc_flags.Super_pages
    )
  }
  if extra_caps then
    for k, v in pairs(extra_caps) do 
      caps[k] = v
    end
  end

  return l:startv(
    {
      log  = {name, "", "key=" .. key},
      scheduler = sched(0x6, 0x1, cpus),
      caps = caps
    },
    "rom/uvmm",
    table.unpack(c)
  )
end

function start_virtio_block(channel)
  local c = {}
  local caps = {}
  local servers = {}
  local clients = {}
  for key, value in pairs(channel) do
    channel[key] = {
      server = l:new_channel(),
      client = l:new_channel()
    }
    local server_name = key .. "_server"
    local client_name = key .. "_client"
    c[#c + 1] = client_name .. ",filed,ds-max=" .. max_ds .. ",servercap=" .. server_name
    caps[server_name] = channel[key].server:svr()
    caps[client_name] = channel[key].client:svr()
  end

  l:startv(
    {
      log  = { "vioblk", "b" },
      scheduler = sched(0x45, 0x40, 0x1),
      caps = caps
    },
    "rom/virtio-block", table.unpack(c)
  )
end

return _ENV
