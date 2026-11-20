"""Graphics cards: usage, video memory, clocks, temperature, power."""

from __future__ import annotations

import os
import re

from ..util import INFO, Finding, fmt_bytes, have, list_dir, read, read_int, run

VENDORS = {"0x1002": "AMD", "0x10de": "NVIDIA", "0x8086": "Intel"}


def _pci_name(slot: str):
    rc, out, _ = run(["lspci", "-vmm", "-s", slot], timeout=3)
    if rc != 0:
        return None
    fields = {}
    for line in out.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            fields.setdefault(key.strip(), value.strip())
    vendor = fields.get("Vendor", "")
    vendor = re.sub(r"\s*\[.*?\]", "", vendor).replace(", Inc.", "").replace(" Corporation", "")
    vendor = {"Advanced Micro Devices": "AMD", "NVIDIA": "NVIDIA", "Intel": "Intel"}.get(vendor, vendor)
    device = fields.get("Device")
    return f"{vendor} {device}".strip() if device else None


def _cpu_model() -> str:
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("model name"):
                    return line.split(":", 1)[1]
    except OSError:
        pass
    return ""


def _hwmon(dev: str) -> dict:
    out = {}
    for hw in list_dir(f"{dev}/hwmon"):
        base = f"{dev}/hwmon/{hw}"
        temp = read_int(f"{base}/temp1_input")
        if temp is not None:
            out["temp"] = temp / 1000
        power = read_int(f"{base}/power1_average") or read_int(f"{base}/power1_input")
        if power:
            out["power_w"] = power / 1e6
        cap = read_int(f"{base}/power1_cap")
        if cap:
            out["power_cap_w"] = cap / 1e6
        fan = read_int(f"{base}/fan1_input")
        if fan is not None:
            out["fan_rpm"] = fan
    return out


def _nvidia() -> list[dict]:
    if not have("nvidia-smi"):
        return []
    rc, out, _ = run([
        "nvidia-smi",
        "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu,"
        "power.draw,clocks.gr,driver_version,pci.bus_id",
        "--format=csv,noheader,nounits",
    ], timeout=5)
    gpus = []
    if rc != 0:
        return gpus

    def num(v):
        try:
            return float(v)
        except ValueError:
            return None

    for line in out.strip().splitlines():
        p = [x.strip() for x in line.split(",")]
        if len(p) < 9:
            continue
        gpus.append({
            "name": p[0], "vendor": "NVIDIA", "driver": f"nvidia {p[7]}",
            "busy": num(p[1]),
            "vram_used": (num(p[2]) or 0) * 1048576, "vram_total": (num(p[3]) or 0) * 1048576,
            "temp": num(p[4]), "power_w": num(p[5]), "clock_mhz": num(p[6]),
            "slot": p[8].lower()[-12:], "integrated": False,
        })
    return gpus


def collect() -> dict:
    gpus = []
    nvidia = _nvidia()
    nvidia_slots = {g["slot"] for g in nvidia}
    for card in list_dir("/sys/class/drm"):
        if not re.fullmatch(r"card\d+", card):
            continue
        dev = f"/sys/class/drm/{card}/device"
        if not os.path.exists(dev):
            continue
        slot = os.path.basename(os.path.realpath(dev))
        vendor_id = read(f"{dev}/vendor")
        if slot in nvidia_slots:
            continue  # reported via nvidia-smi
        driver = os.path.basename(os.path.realpath(f"{dev}/driver")) if os.path.exists(f"{dev}/driver") else None
        gpu = {
            "card": card,
            "slot": slot,
            "vendor": VENDORS.get(vendor_id, vendor_id or "Unknown"),
            "name": _pci_name(slot) or f"{VENDORS.get(vendor_id, 'Unknown')} GPU",
            "driver": driver,
            "primary": read(f"{dev}/boot_vga") == "1",
            "busy": read_int(f"{dev}/gpu_busy_percent"),
            "vram_used": read_int(f"{dev}/mem_info_vram_used"),
            "vram_total": read_int(f"{dev}/mem_info_vram_total"),
            "gtt_used": read_int(f"{dev}/mem_info_gtt_used"),
            "gtt_total": read_int(f"{dev}/mem_info_gtt_total"),
            "clock_mhz": None,
            "clock_max_mhz": None,
        }
        sclk = read(f"{dev}/pp_dpm_sclk")
        if sclk:
            clocks = [int(m.group(1)) for m in re.finditer(r"(\d+)\s*Mhz", sclk, re.I)]
            cur = re.search(r"(\d+)\s*Mhz\s*\*", sclk, re.I)
            gpu["clock_mhz"] = int(cur.group(1)) if cur else None
            gpu["clock_max_mhz"] = max(clocks) if clocks else None
        elif read_int(f"/sys/class/drm/{card}/gt_cur_freq_mhz") is not None:
            gpu["clock_mhz"] = read_int(f"/sys/class/drm/{card}/gt_cur_freq_mhz")
            gpu["clock_max_mhz"] = read_int(f"/sys/class/drm/{card}/gt_max_freq_mhz")
        gpu.update(_hwmon(dev))
        # APUs / iGPUs carve out a small VRAM region and mostly use system RAM (GTT).
        gpu["integrated"] = gpu["vendor"] == "Intel" or bool(
            gpu["vram_total"] and gpu["vram_total"] <= 2 * 1024**3 and gpu["gtt_total"])
        if gpu["integrated"] and gpu["vendor"] == "AMD":
            # lspci only knows the codename; the CPU model names the iGPU (e.g. "Radeon 780M").
            m = re.search(r"(Radeon\s+[\w ]*?Graphics|Radeon\s+\w+)", _cpu_model())
            if m:
                gpu["codename"] = gpu["name"]
                gpu["name"] = f"AMD {m.group(1)}"
        gpus.append(gpu)
    gpus.extend(nvidia)

    findings = []
    for g in gpus:
        if g.get("vram_total") and g.get("vram_used") is not None and not g["integrated"]:
            pct = g["vram_used"] / g["vram_total"] * 100
            if pct >= 95:
                findings.append(Finding(INFO, f"{g['name']}: video memory almost full",
                                        f"{fmt_bytes(g['vram_used'])} of {fmt_bytes(g['vram_total'])} used."))
    if gpus:
        g = gpus[0]
        bits = [g["name"]]
        if g.get("busy") is not None:
            bits.append(f"{g['busy']:.0f}% busy")
        summary = " · ".join(bits)
    else:
        summary = "No GPU found"
    return {"gpus": gpus, "findings": findings, "summary": summary}
