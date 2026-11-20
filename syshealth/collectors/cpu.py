"""CPU usage, frequency, load and temperature."""

from __future__ import annotations

import os

import psutil

from ..util import OK, Finding, level_for, read
from . import hwmon


def _model_name() -> str:
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith(("model name", "Model", "Hardware")):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return "Unknown processor"


def collect() -> dict:
    per_core = psutil.cpu_percent(interval=0.7, percpu=True)
    usage = sum(per_core) / len(per_core) if per_core else None
    logical = psutil.cpu_count() or len(per_core) or 1
    physical = psutil.cpu_count(logical=False)

    freq = None
    try:
        freq = psutil.cpu_freq()
    except (OSError, NotImplementedError):
        pass
    try:
        core_freqs = [f.current for f in psutil.cpu_freq(percpu=True)]
    except (OSError, NotImplementedError):
        core_freqs = []

    load = os.getloadavg()
    temp = hwmon.cpu_temperature()

    cpufreq = "/sys/devices/system/cpu/cpu0/cpufreq"
    governor = read(f"{cpufreq}/scaling_governor")
    epp = read(f"{cpufreq}/energy_performance_preference")
    driver = read(f"{cpufreq}/scaling_driver")

    findings = []
    load_ratio = load[0] / logical
    lvl = level_for(load_ratio, 1.0, 2.0)
    if lvl != OK:
        findings.append(Finding(
            lvl, "CPU is overloaded",
            f"Load average {load[0]:.1f} on {logical} threads — more work is "
            "queued than the CPU can handle.",
        ))

    return {
        "model": _model_name(),
        "physical": physical,
        "logical": logical,
        "usage": usage,
        "per_core": per_core,
        "core_freqs": core_freqs,
        "freq_current": freq.current if freq else None,
        "freq_max": freq.max if freq and freq.max else None,
        "freq_min": freq.min if freq and freq.min else None,
        "load": load,
        "load_ratio": load_ratio,
        "temp": temp,
        "governor": governor,
        "epp": epp,
        "driver": driver,
        "findings": findings,
        "summary": f"{usage:.0f}% busy" + (f" · {temp:.0f}°C" if temp is not None else ""),
    }
