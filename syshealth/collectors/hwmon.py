"""Read temperature/fan sensors from /sys/class/hwmon."""

from __future__ import annotations

import os
import re

from ..util import list_dir, read, read_int

HWMON = "/sys/class/hwmon"

# hwmon driver name -> (kind, friendly name)
KNOWN = {
    "k10temp": ("cpu", "CPU"),
    "coretemp": ("cpu", "CPU"),
    "zenpower": ("cpu", "CPU"),
    "cpu_thermal": ("cpu", "CPU"),
    "amdgpu": ("gpu", "GPU (AMD)"),
    "radeon": ("gpu", "GPU (AMD)"),
    "nouveau": ("gpu", "GPU (NVIDIA)"),
    "xe": ("gpu", "GPU (Intel)"),
    "i915": ("gpu", "GPU (Intel)"),
    "nvme": ("disk", "NVMe SSD"),
    "drivetemp": ("disk", "Drive"),
    "acpitz": ("board", "ACPI thermal zone"),
    "thinkpad": ("board", "ThinkPad embedded controller"),
    "dell_smm": ("board", "Dell embedded controller"),
    "asus": ("board", "ASUS embedded controller"),
    "pch_cannonlake": ("board", "Chipset"),
    "spd5118": ("memory", "Memory module"),
    "jc42": ("memory", "Memory module"),
}
WIFI_PREFIXES = ("iwlwifi", "mt79", "mt76", "ath1", "rtw", "brcm")
SUPERIO_PREFIXES = ("nct", "it87", "it86", "f718", "w83")


def _identify(name: str, path: str):
    if name in KNOWN:
        kind, friendly = KNOWN[name]
    elif name.startswith(WIFI_PREFIXES):
        kind, friendly = "wifi", "Wi-Fi adapter"
    elif name.startswith(SUPERIO_PREFIXES):
        kind, friendly = "board", "Motherboard"
    else:
        kind, friendly = "other", name
    if name == "nvme":
        model = read(os.path.join(path, "device", "model"))
        if model:
            friendly = f"NVMe SSD · {model}"
    elif name == "drivetemp":
        model = read(os.path.join(path, "device", "model"))
        if model:
            friendly = f"Drive · {model}"
    return kind, friendly


def _sane_temp(milli):
    if milli is None:
        return None
    value = milli / 1000.0
    return value if -30 < value < 150 else None


def _sane_limit(milli):
    value = _sane_temp(milli)
    return value if value is not None and value >= 40 else None


def read_sensors() -> list[dict]:
    chips = []
    for entry in list_dir(HWMON):
        path = os.path.join(HWMON, entry)
        name = read(os.path.join(path, "name"), entry)
        files = list_dir(path)
        temps, fans = [], []
        for fname in files:
            m = re.fullmatch(r"temp(\d+)_input", fname)
            if m:
                idx = m.group(1)
                value = _sane_temp(read_int(os.path.join(path, fname)))
                if value is None:
                    continue
                temps.append({
                    "label": read(os.path.join(path, f"temp{idx}_label")) or f"Sensor {idx}",
                    "value": value,
                    "high": _sane_limit(read_int(os.path.join(path, f"temp{idx}_max"))),
                    "crit": _sane_limit(read_int(os.path.join(path, f"temp{idx}_crit"))),
                })
                continue
            m = re.fullmatch(r"fan(\d+)_input", fname)
            if m:
                idx = m.group(1)
                rpm = read_int(os.path.join(path, fname))
                if rpm is None:
                    continue
                fans.append({
                    "label": read(os.path.join(path, f"fan{idx}_label")) or f"Fan {idx}",
                    "rpm": rpm,
                })
        if not temps and not fans:
            continue
        kind, friendly = _identify(name, path)
        chips.append({
            "driver": name, "kind": kind, "name": friendly, "path": path,
            "temps": temps, "fans": fans,
        })
    return chips


def cpu_temperature(chips=None):
    """Best single CPU temperature reading."""
    chips = read_sensors() if chips is None else chips
    for chip in chips:
        if chip["kind"] != "cpu" or not chip["temps"]:
            continue
        by_label = {t["label"]: t["value"] for t in chip["temps"]}
        for preferred in ("Tdie", "Tctl", "Package id 0", "CPU"):
            if preferred in by_label:
                return by_label[preferred]
        return max(t["value"] for t in chip["temps"])
    return None


def thresholds(kind: str, sensor: dict):
    """(warn, crit) thresholds for a temperature sensor."""
    defaults = {
        "cpu": (85, 95),
        "gpu": (85, 100),
        "disk": (65, 75),
        "wifi": (80, 95),
        "memory": (75, 85),
    }.get(kind, (80, 95))
    warn, crit = defaults
    if sensor.get("crit"):
        crit = min(crit, sensor["crit"]) if kind == "disk" else sensor["crit"]
        warn = min(warn, crit - 5)
    if sensor.get("high") and sensor["high"] < crit:
        warn = min(warn, sensor["high"])
    return warn, crit
