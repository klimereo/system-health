"""Shared helpers: status levels, sysfs reading, subprocess running, formatting."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass

# Status levels, ordered by severity.
UNKNOWN, OK, INFO, WARN, CRIT = "unknown", "ok", "info", "warn", "crit"
_RANK = {UNKNOWN: 0, OK: 1, INFO: 2, WARN: 3, CRIT: 4}


def rank(level: str) -> int:
    return _RANK.get(level, 0)


def worst(levels, default: str = OK) -> str:
    levels = list(levels)
    if not levels:
        return default
    return max(levels, key=rank)


@dataclass
class Finding:
    level: str
    title: str
    detail: str = ""


def level_for(value, warn, crit, low_is_bad: bool = False) -> str:
    """Map a number onto ok/warn/crit using thresholds."""
    if value is None:
        return UNKNOWN
    if low_is_bad:
        return CRIT if value <= crit else WARN if value <= warn else OK
    return CRIT if value >= crit else WARN if value >= warn else OK


def overall(findings, default: str = OK) -> str:
    return worst((f.level for f in findings), default)


# ---------------------------------------------------------------- sysfs ----

def read(path: str, default=None):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read().strip()
    except OSError:
        return default


def read_int(path: str, default=None):
    value = read(path)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def list_dir(path: str) -> list[str]:
    try:
        return sorted(os.listdir(path))
    except OSError:
        return []


# ----------------------------------------------------------- processes ----

def clean_env() -> dict:
    """Environment for child processes.

    A frozen (PyInstaller / AppImage) build points LD_LIBRARY_PATH at its
    bundled libraries; system tools must not load those.
    """
    env = dict(os.environ)
    if getattr(sys, "frozen", False):
        orig = env.pop("LD_LIBRARY_PATH_ORIG", None)
        if orig:
            env["LD_LIBRARY_PATH"] = orig
        else:
            env.pop("LD_LIBRARY_PATH", None)
    env["LC_ALL"] = "C.UTF-8"
    return env


def have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def run(cmd: list[str], timeout: float = 10):
    """Run a command; return (returncode, stdout, stderr). returncode is None
    if the command is missing or timed out."""
    if not have(cmd[0]):
        return None, "", f"{cmd[0]} not found"
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            env=clean_env(), stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return None, "", f"{cmd[0]} timed out"
    except OSError as exc:
        return None, "", str(exc)
    return proc.returncode, proc.stdout, proc.stderr


# ----------------------------------------------------------- formatting ----

def fmt_bytes(n, decimals: int = 1) -> str:
    if n is None:
        return "—"
    n = float(n)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if abs(n) < 1024 or unit == "PiB":
            if unit == "B":
                return f"{int(n)} B"
            return f"{n:.{decimals}f} {unit}"
        n /= 1024
    return f"{n:.1f} PiB"


def fmt_rate(n) -> str:
    if n is None:
        return "—"
    return fmt_bytes(n) + "/s"


def fmt_duration(seconds) -> str:
    if seconds is None:
        return "—"
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def fmt_pct(value, decimals: int = 0) -> str:
    return "—" if value is None else f"{value:.{decimals}f}%"


def fmt_temp(value) -> str:
    return "—" if value is None else f"{value:.0f}°C"
