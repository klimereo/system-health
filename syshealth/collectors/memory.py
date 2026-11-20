"""RAM, swap and zram usage plus the biggest memory users."""

from __future__ import annotations

import re
from collections import defaultdict

import psutil

from ..util import INFO, OK, Finding, fmt_bytes, level_for, list_dir, read, read_int


def _zram_devices() -> list[dict]:
    devices = []
    for name in list_dir("/sys/block"):
        if not name.startswith("zram"):
            continue
        base = f"/sys/block/{name}"
        disksize = read_int(f"{base}/disksize", 0)
        if not disksize:
            continue
        algo = read(f"{base}/comp_algorithm", "")
        m = re.search(r"\[([^\]]+)\]", algo)
        stats = (read(f"{base}/mm_stat") or "").split()
        orig = int(stats[0]) if len(stats) > 2 else None
        compr = int(stats[1]) if len(stats) > 2 else None
        used = int(stats[2]) if len(stats) > 2 else None
        devices.append({
            "name": name,
            "disksize": disksize,
            "algorithm": m.group(1) if m else algo or None,
            "orig": orig,
            "compressed": compr,
            "mem_used": used,
            "ratio": (orig / compr) if orig and compr else None,
        })
    return devices


def _swaps() -> list[dict]:
    swaps = []
    try:
        with open("/proc/swaps", encoding="utf-8") as fh:
            next(fh, None)
            for line in fh:
                parts = line.split()
                if len(parts) >= 5:
                    swaps.append({
                        "name": parts[0], "type": parts[1],
                        "size": int(parts[2]) * 1024, "used": int(parts[3]) * 1024,
                        "priority": int(parts[4]),
                    })
    except OSError:
        pass
    return swaps


def _top_apps(limit: int = 8) -> list[dict]:
    """Memory grouped by process name (a browser has dozens of processes)."""
    groups = defaultdict(lambda: {"rss": 0, "count": 0})
    for proc in psutil.process_iter(["name", "memory_info"]):
        info = proc.info
        mem = info.get("memory_info")
        if not mem:
            continue
        group = groups[info.get("name") or "?"]
        group["rss"] += mem.rss
        group["count"] += 1
    ranked = sorted(groups.items(), key=lambda kv: kv[1]["rss"], reverse=True)
    return [{"name": n, **g} for n, g in ranked[:limit]]


def collect() -> dict:
    vm = psutil.virtual_memory()
    sw = psutil.swap_memory()
    findings = []

    lvl = level_for(vm.percent, 85, 95)
    if lvl != OK:
        findings.append(Finding(
            lvl, "Memory is nearly full",
            f"{vm.percent:.0f}% of RAM in use — close some apps or browser tabs.",
        ))
    if sw.total:
        lvl = level_for(sw.percent, 80, 95)
        if lvl != OK:
            findings.append(Finding(
                lvl, "Swap is nearly full",
                f"{sw.percent:.0f}% of swap in use; the system may slow down.",
            ))
    else:
        findings.append(Finding(INFO, "No swap configured",
                                "Without swap, running out of RAM kills apps abruptly."))

    used = vm.total - vm.available
    return {
        "total": vm.total,
        "available": vm.available,
        "used": used,
        "percent": vm.percent,
        "cached": getattr(vm, "cached", 0) + getattr(vm, "buffers", 0),
        "shared": getattr(vm, "shared", 0),
        "swap_total": sw.total,
        "swap_used": sw.used,
        "swap_percent": sw.percent if sw.total else None,
        "swaps": _swaps(),
        "zram": _zram_devices(),
        "top": _top_apps(),
        "findings": findings,
        "summary": f"{fmt_bytes(used)} of {fmt_bytes(vm.total)} · {vm.percent:.0f}%",
    }
