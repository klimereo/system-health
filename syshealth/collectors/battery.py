"""Laptop battery health plus wireless peripheral batteries."""

from __future__ import annotations

import os
import re

from ..util import (INFO, OK, WARN, Finding, level_for, list_dir, read, read_int,
                    run)

PSU = "/sys/class/power_supply"
LEVEL_TEXT_PCT = {"Full": 100, "High": 80, "Normal": 55, "Low": 15, "Critical": 5}


def _power_profile():
    rc, out, _ = run(["powerprofilesctl", "get"], timeout=3)
    if rc == 0 and out.strip():
        return out.strip()
    return read("/sys/firmware/acpi/platform_profile")


def _battery(path: str, name: str) -> dict:
    def r(f):
        return read(os.path.join(path, f))

    def ri(f):
        return read_int(os.path.join(path, f))

    # Batteries report either energy (µWh) or charge (µAh); prefer energy.
    full = ri("energy_full") or ri("charge_full")
    design = ri("energy_full_design") or ri("charge_full_design")
    now = ri("energy_now") or ri("charge_now")
    uses_energy = ri("energy_full") is not None
    power = ri("power_now")  # µW
    current = ri("current_now")  # µA
    voltage = ri("voltage_now")  # µV
    if power is None and current is not None and voltage:
        power = current * voltage / 1e6
    status = r("status") or "Unknown"

    rate = power if uses_energy else current  # same unit family as full/now
    # Below ~0.5 W the battery is just holding its charge (e.g. at a charge limit on AC);
    # dividing by that gives absurd estimates like "46 days left".
    idle = power is not None and abs(power) < 500_000
    hours_left = None
    if rate and rate > 0 and not idle and now is not None and full:
        if status == "Discharging":
            hours_left = now / rate
        elif status == "Charging":
            hours_left = max(full - now, 0) / rate

    health = (full / design * 100) if full and design else None
    charge_types = r("charge_types") or ""
    m = re.search(r"\[([^\]]+)\]", charge_types)
    charge_mode = (m.group(1) if m else charge_types or None)
    if charge_mode:
        charge_mode = charge_mode.replace("_", " ").capitalize()
    to_wh = (lambda v: v / 1e6) if uses_energy else (
        lambda v: v * (ri("voltage_min_design") or voltage or 0) / 1e12)

    return {
        "name": name,
        "manufacturer": r("manufacturer"),
        "model": r("model_name"),
        "technology": r("technology"),
        "status": status,
        "capacity": ri("capacity"),
        "health": health,
        "cycles": ri("cycle_count"),
        "full_wh": to_wh(full) if full else None,
        "design_wh": to_wh(design) if design else None,
        "now_wh": to_wh(now) if now is not None else None,
        "power_w": abs(power) / 1e6 if power else None,
        "voltage": voltage / 1e6 if voltage else None,
        "hours_left": hours_left,
        "charge_limit": ri("charge_control_end_threshold"),
        "charge_mode": charge_mode,
    }


def _peripheral(path: str, name: str) -> dict:
    capacity = read_int(os.path.join(path, "capacity"))
    level = read(os.path.join(path, "capacity_level"))
    return {
        "name": name,
        "model": read(os.path.join(path, "model_name")) or name,
        "manufacturer": read(os.path.join(path, "manufacturer")),
        "capacity": capacity,
        "level": level if level and level != "Unknown" else None,
        "approx": capacity if capacity is not None else LEVEL_TEXT_PCT.get(level or ""),
        "status": read(os.path.join(path, "status")) or "Unknown",
    }


def collect() -> dict:
    batteries, peripherals = [], []
    ac_online = None
    for name in list_dir(PSU):
        path = os.path.join(PSU, name)
        kind = read(os.path.join(path, "type"))
        scope = read(os.path.join(path, "scope"))
        if kind == "Mains":
            online = read_int(os.path.join(path, "online"))
            if online is not None:
                ac_online = bool(online) or bool(ac_online)
        elif kind == "Battery":
            if scope == "Device":
                peripherals.append(_peripheral(path, name))
            elif read_int(os.path.join(path, "present"), 1):
                batteries.append(_battery(path, name))

    for bat in batteries:
        # Some laptops report "Discharging" at ~0 W while plugged in and held at a charge limit.
        if ac_online and bat["status"] == "Discharging" and (bat["power_w"] or 0) < 0.5:
            bat["status"] = "Not charging"
            bat["hours_left"] = None

    findings = []
    for bat in batteries:
        lvl = level_for(bat["health"], 80, 60, low_is_bad=True)
        if bat["health"] is not None and lvl != OK:
            findings.append(Finding(
                lvl, f"Battery has worn to {bat['health']:.0f}% of its original capacity",
                f"It now holds {bat['full_wh']:.1f} Wh instead of {bat['design_wh']:.1f} Wh."
                if bat["full_wh"] and bat["design_wh"] else "",
            ))
        if bat["status"] == "Discharging" and bat["capacity"] is not None and bat["capacity"] <= 15:
            findings.append(Finding(WARN, f"Battery low ({bat['capacity']}%)", "Plug in the charger."))
    for p in peripherals:
        if p["approx"] is not None and p["approx"] <= 15:
            findings.append(Finding(INFO, f"{p['model']} battery is low", "Charge or replace it soon."))

    if batteries:
        b = batteries[0]
        summary = f"{b['capacity']}% · {b['status'].lower()}"
        if b["health"] is not None:
            summary += f" · health {b['health']:.0f}%"
    else:
        summary = "No battery (desktop)"

    return {
        "batteries": batteries,
        "peripherals": peripherals,
        "ac_online": ac_online,
        "power_profile": _power_profile(),
        "findings": findings,
        "summary": summary,
    }
