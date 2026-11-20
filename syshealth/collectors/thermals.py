"""All temperature sensors and fans."""

from __future__ import annotations

from ..util import OK, Finding, level_for, worst
from . import hwmon

KIND_ORDER = {"cpu": 0, "gpu": 1, "disk": 2, "memory": 3, "wifi": 4, "board": 5, "other": 6}


def collect() -> dict:
    chips = hwmon.read_sensors()
    chips.sort(key=lambda c: (KIND_ORDER.get(c["kind"], 9), c["name"]))
    findings = []
    hottest = None
    for chip in chips:
        for t in chip["temps"]:
            warn, crit = hwmon.thresholds(chip["kind"], t)
            t["warn"], t["crit_limit"] = warn, crit
            t["level"] = level_for(t["value"], warn, crit)
            if hottest is None or t["value"] > hottest[1]:
                hottest = (chip["name"], t["value"])
        chip_level = worst((t["level"] for t in chip["temps"]), OK)
        chip["level"] = chip_level
        if chip_level != OK:
            peak = max(chip["temps"], key=lambda t: t["value"])
            findings.append(Finding(
                chip_level, f"{chip['name']} is running hot ({peak['value']:.0f}°C)",
                "Check that vents are clear and fans are spinning; "
                "heavy workloads also raise temperatures.",
            ))
    fans = [f for c in chips for f in c["fans"]]
    summary = (f"Hottest: {hottest[0].split(' · ')[0]} {hottest[1]:.0f}°C"
               if hottest else "No temperature sensors found")
    return {
        "chips": chips,
        "fan_count": len(fans),
        "findings": findings,
        "summary": summary,
    }
