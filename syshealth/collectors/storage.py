"""Filesystem usage, physical drives and (on request) SMART health."""

from __future__ import annotations

import json
import os

import psutil

from ..util import (CRIT, INFO, OK, WARN, Finding, fmt_bytes, have, level_for,
                    list_dir, read, read_int, run)

SKIP_FS = {"squashfs", "tmpfs", "devtmpfs", "overlay", "iso9660", "ramfs", "erofs"}
SKIP_BLOCK_PREFIXES = ("loop", "ram", "zram", "dm-", "sr", "fd", "md", "nbd")


def _volumes() -> list[dict]:
    by_device: dict[str, dict] = {}
    for part in psutil.disk_partitions(all=False):
        if part.fstype in SKIP_FS or part.fstype.startswith("fuse.") and part.fstype != "fuseblk":
            continue
        if part.mountpoint.startswith(("/var/lib/snapd", "/snap")):
            continue
        vol = by_device.setdefault(part.device, {
            "device": part.device, "fstype": part.fstype, "mountpoints": [],
            "readonly": "ro" in part.opts.split(","),
        })
        vol["mountpoints"].append(part.mountpoint)

    volumes = []
    for vol in by_device.values():
        vol["mountpoints"].sort(key=lambda m: (len(m), m))
        primary = vol["mountpoints"][0]
        try:
            usage = psutil.disk_usage(primary)
        except OSError:
            continue
        vol.update(mountpoint=primary, total=usage.total, used=usage.used,
                   free=usage.free, percent=usage.percent)
        volumes.append(vol)
    volumes.sort(key=lambda v: (v["mountpoint"] != "/", v["mountpoint"]))
    return volumes


def _transport(name: str, syspath: str) -> str:
    if name.startswith("nvme"):
        return "NVMe"
    if "/usb" in syspath:
        return "USB"
    if name.startswith("mmcblk"):
        return "SD/eMMC"
    if name.startswith("vd"):
        return "Virtual"
    return "SATA"


def _drives() -> list[dict]:
    drives = []
    for name in list_dir("/sys/block"):
        if name.startswith(SKIP_BLOCK_PREFIXES):
            continue
        base = f"/sys/block/{name}"
        size = read_int(f"{base}/size", 0) * 512
        if not size:
            continue
        syspath = os.path.realpath(base)
        dev = f"{base}/device"
        model = read(f"{dev}/model") or read(f"{dev}/name") or name
        vendor = read(f"{dev}/vendor") or ""
        firmware = read(f"{dev}/firmware_rev") or read(f"{dev}/rev")
        temp = None
        hwmon_dirs = [f"{dev}/{e}" for e in list_dir(dev) if e.startswith("hwmon") and e != "hwmon"]
        hwmon_dirs += [f"{dev}/hwmon/{e}" for e in list_dir(f"{dev}/hwmon")]
        for hw in hwmon_dirs:
            milli = read_int(f"{hw}/temp1_input")
            if milli:
                temp = milli / 1000
        drives.append({
            "name": name,
            "path": f"/dev/{name}",
            "model": model.strip(),
            "vendor": vendor.strip() if vendor and not vendor.startswith("0x") else "",
            "size": size,
            "rotational": read(f"{base}/queue/rotational") == "1",
            "removable": read(f"{base}/removable") == "1",
            "transport": _transport(name, syspath),
            "firmware": firmware,
            "temp": temp,
        })
    return drives


def collect() -> dict:
    volumes = _volumes()
    drives = _drives()
    findings = []
    for vol in volumes:
        lvl = level_for(vol["percent"], 80, 90)
        if lvl != OK:
            findings.append(Finding(
                lvl, f"{vol['mountpoint']} is {vol['percent']:.0f}% full",
                f"Only {fmt_bytes(vol['free'])} free on {vol['device']}.",
            ))
    root = next((v for v in volumes if v["mountpoint"] == "/"), volumes[0] if volumes else None)
    summary = (f"{root['mountpoint']} {root['percent']:.0f}% used · {fmt_bytes(root['free'])} free"
               if root else "No filesystems found")
    return {
        "volumes": volumes,
        "drives": drives,
        "smartctl": have("smartctl"),
        "findings": findings,
        "summary": summary,
    }


# ------------------------------------------------------------------ SMART --

SEPARATOR = "=====SYSHEALTH-SMART-SEPARATOR====="


def read_smart(devices: list[str]) -> dict:
    """Read SMART data for all drives with a single admin prompt (pkexec)."""
    if not devices:
        return {"drives": {}, "findings": [], "error": "No drives to check."}
    if not have("smartctl"):
        return {"drives": {}, "findings": [],
                "error": "smartctl is not installed. Install it with: sudo dnf install smartmontools"}
    if not have("pkexec"):
        return {"drives": {}, "findings": [], "error": "pkexec (polkit) is not available."}

    for dev in devices:  # devices go into a shell command; keep them simple
        if not dev.startswith("/dev/") or not all(c.isalnum() or c in "/-_" for c in dev):
            return {"drives": {}, "findings": [], "error": f"Unexpected device name {dev!r}"}
    script = f"; echo {SEPARATOR}; ".join(f"smartctl -j -a {dev}" for dev in devices)
    rc, out, err = run(["pkexec", "/bin/sh", "-c", script], timeout=120)
    if rc in (126, 127) and not out.strip():
        return {"drives": {}, "findings": [], "error": "Authentication was cancelled."}
    if rc is None:
        return {"drives": {}, "findings": [], "error": err or "pkexec failed."}

    results, findings = {}, []
    for dev, chunk in zip(devices, out.split(SEPARATOR)):
        try:
            data = json.loads(chunk)
        except ValueError:
            results[dev] = {"error": "Could not parse smartctl output."}
            continue
        parsed = _parse_smart(data)
        results[dev] = parsed
        findings.extend(_smart_findings(dev, parsed))
    return {"drives": results, "findings": findings, "error": None}


def _parse_smart(d: dict) -> dict:
    msgs = [m.get("string", "") for m in d.get("smartctl", {}).get("messages", [])
            if m.get("severity") == "error"]
    status = d.get("smart_status", {})
    out = {
        "passed": status.get("passed"),
        "model": d.get("model_name"),
        "serial": d.get("serial_number"),
        "firmware": d.get("firmware_version"),
        "temperature": d.get("temperature", {}).get("current"),
        "power_on_hours": d.get("power_on_time", {}).get("hours"),
        "power_cycles": d.get("power_cycle_count"),
        "error": "; ".join(msgs) if msgs and not status else None,
    }
    nvme = d.get("nvme_smart_health_information_log")
    if nvme:
        out.update(
            kind="nvme",
            critical_warning=nvme.get("critical_warning"),
            percentage_used=nvme.get("percentage_used"),
            available_spare=nvme.get("available_spare"),
            available_spare_threshold=nvme.get("available_spare_threshold"),
            media_errors=nvme.get("media_errors"),
            error_log_entries=nvme.get("num_err_log_entries"),
            unsafe_shutdowns=nvme.get("unsafe_shutdowns"),
            data_read=(nvme.get("data_units_read") or 0) * 512000,
            data_written=(nvme.get("data_units_written") or 0) * 512000,
        )
    else:
        attrs = {a.get("id"): a for a in d.get("ata_smart_attributes", {}).get("table", [])}

        def raw(attr_id):
            a = attrs.get(attr_id)
            return a.get("raw", {}).get("value") if a else None

        wear = None
        for attr_id in (231, 233, 177, 202):  # SSD life / wear-levelling attributes
            a = attrs.get(attr_id)
            if a and a.get("value") is not None and a.get("value") <= 100:
                wear = 100 - a["value"]
                break
        lbas_written = raw(241)
        out.update(
            kind="ata",
            reallocated=raw(5),
            pending=raw(197),
            uncorrectable=raw(198),
            percentage_used=wear,
            data_written=lbas_written * 512 if lbas_written else None,
        )
    return out


def _smart_findings(dev: str, s: dict) -> list[Finding]:
    name = s.get("model") or dev
    f = []
    if s.get("error"):
        f.append(Finding(INFO, f"SMART unavailable for {dev}", s["error"]))
        return f
    if s.get("passed") is False:
        f.append(Finding(CRIT, f"{name}: SMART health check FAILED",
                         "Back up your data now and plan to replace this drive."))
    if s.get("critical_warning"):
        f.append(Finding(CRIT, f"{name}: drive reports a critical warning",
                         f"NVMe critical warning flags = {s['critical_warning']}"))
    used = s.get("percentage_used")
    lvl = level_for(used, 70, 90)
    if used is not None and lvl != OK:
        f.append(Finding(lvl, f"{name}: {used}% of rated endurance used",
                         "The SSD is wearing out; keep backups current."))
    spare, thresh = s.get("available_spare"), s.get("available_spare_threshold")
    if spare is not None and thresh is not None and spare <= thresh + 10:
        f.append(Finding(CRIT if spare <= thresh else WARN,
                         f"{name}: spare blocks low ({spare}%)", ""))
    for key, label in (("media_errors", "media errors"), ("reallocated", "reallocated sectors"),
                       ("pending", "pending sectors"), ("uncorrectable", "uncorrectable sectors")):
        value = s.get(key)
        if value:
            f.append(Finding(WARN, f"{name}: {value} {label}",
                             "The drive has had read/write problems; keep backups current."))
    return f
