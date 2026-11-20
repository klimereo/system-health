"""Data collectors. Each `collect()` returns a plain dict containing at least
`findings` (list[Finding]) and `summary` (str)."""

from . import battery, cpu, gpu, memory, network, processes, storage, system, thermals

COLLECTORS = {
    "cpu": cpu.collect,
    "memory": memory.collect,
    "storage": storage.collect,
    "battery": battery.collect,
    "thermals": thermals.collect,
    "gpu": gpu.collect,
    "network": network.collect,
    "processes": processes.collect,
    "system": system.collect,
}
