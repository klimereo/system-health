"""OS, hardware, updates, failed services and recent errors."""

from __future__ import annotations

import json
import os
import platform
import re
import socket
import time

import psutil

from ..util import INFO, WARN, Finding, have, read, run

SECURE_BOOT_VAR = "/sys/firmware/efi/efivars/SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c"


def _os_release() -> dict:
    data = {}
    try:
        with open("/etc/os-release", encoding="utf-8") as fh:
            for line in fh:
                if "=" in line:
                    k, v = line.rstrip("\n").split("=", 1)
                    data[k] = v.strip('"')
    except OSError:
        pass
    return data


def _hardware() -> dict:
    dmi = "/sys/class/dmi/id"
    vendor = read(f"{dmi}/sys_vendor")
    product = read(f"{dmi}/product_name")
    version = read(f"{dmi}/product_version")
    # Lenovo stores the marketing name in product_version.
    if vendor and vendor.upper() == "LENOVO" and version and version not in ("None", "Not Specified"):
        model = f"{version} ({product})"
    else:
        model = product
    return {
        "vendor": vendor.title() if vendor and vendor.isupper() else vendor,
        "model": model,
        "bios": " · ".join(x for x in (read(f"{dmi}/bios_version"), read(f"{dmi}/bios_date")) if x),
    }


def _secure_boot():
    try:
        with open(SECURE_BOOT_VAR, "rb") as fh:
            data = fh.read()
        return bool(data[-1]) if data else None
    except OSError:
        return None if os.path.isdir("/sys/firmware/efi") else "legacy"


def _failed_units(user: bool) -> list[dict]:
    cmd = ["systemctl"] + (["--user"] if user else []) + [
        "--failed", "--no-legend", "--plain", "--no-pager"]
    rc, out, _ = run(cmd, timeout=5)
    units = []
    for line in out.splitlines():
        p = line.split(None, 4)
        if p:
            units.append({"unit": p[0], "description": p[4] if len(p) > 4 else "",
                          "scope": "user" if user else "system"})
    return units


def _journal_errors():
    rc, out, _ = run(["journalctl", "-b", "-p", "3", "-q", "--no-pager", "-o", "json",
                      "--output-fields=MESSAGE,SYSLOG_IDENTIFIER,_COMM,__REALTIME_TIMESTAMP"],
                     timeout=15)
    if rc is None:
        return None, []
    entries = []
    for line in out.splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        msg = e.get("MESSAGE")
        if isinstance(msg, list):  # binary payload
            msg = "(binary message)"
        try:
            ts = int(e.get("__REALTIME_TIMESTAMP", 0)) / 1e6
        except (TypeError, ValueError):
            ts = None
        entries.append({
            "time": ts,
            "source": e.get("SYSLOG_IDENTIFIER") or e.get("_COMM") or "kernel",
            "message": (msg or "").strip(),
        })
    return len(entries), entries[-15:][::-1]


def _dnf_updates():
    if os.path.exists("/run/ostree-booted"):
        return None, "Atomic desktop: use rpm-ostree or Discover"
    if not have("dnf"):
        return None, "dnf not found"
    rc, out, _ = run(["dnf", "check-update", "-q", "--cacheonly"], timeout=30)
    if rc is None:
        return None, "dnf check timed out"
    if rc == 0:
        return 0, None
    if rc != 100:
        return None, "dnf check failed"
    count = 0
    for line in out.splitlines():
        if line.startswith((" ", "Obsoleting", "Security:", "Last metadata")):
            continue
        parts = line.split()
        if len(parts) == 3 and "." in parts[0]:
            count += 1
    return count, None


def _flatpak_updates():
    if not have("flatpak"):
        return None
    rc, out, _ = run(["flatpak", "remote-ls", "--updates", "--columns=application"], timeout=20)
    if rc != 0:
        return None
    return len([l for l in out.splitlines() if l.strip()])


def _newest_kernel():
    rc, out, _ = run(["rpm", "-q", "--last", "kernel-core"], timeout=5)
    if rc != 0 or not out.strip():
        return None
    first = out.split()[0]
    return first.removeprefix("kernel-core-")


def _boot_time_text():
    rc, out, _ = run(["systemd-analyze"], timeout=5)
    if rc == 0:
        m = re.search(r"=\s*([\d.]+min\s*[\d.]+s|[\d.]+s)", out.splitlines()[0] if out else "")
        if m:
            return m.group(1)
    return None


def collect() -> dict:
    osr = _os_release()
    kernel = platform.release()
    boot = psutil.boot_time()
    failed = _failed_units(False) + _failed_units(True)
    err_count, errors = _journal_errors()
    dnf_count, dnf_note = _dnf_updates()
    flatpak_count = _flatpak_updates()
    newest = _newest_kernel()
    selinux = run(["getenforce"], timeout=3)[1].strip() or None

    findings = []
    if failed:
        findings.append(Finding(WARN, f"{len(failed)} service{'s' if len(failed) != 1 else ''} failed",
                                ", ".join(u["unit"] for u in failed[:4])))
    updates = (dnf_count or 0) + (flatpak_count or 0)
    if updates:
        findings.append(Finding(INFO, f"{updates} update{'s' if updates != 1 else ''} available",
                                "Install them from Discover or with: sudo dnf upgrade"))
    if newest and newest != kernel:
        findings.append(Finding(INFO, "Restart to use the newest kernel",
                                f"Running {kernel}, installed {newest}."))
    if selinux == "Disabled":
        findings.append(Finding(INFO, "SELinux is disabled", "Fedora enables it by default for security."))

    uptime = time.time() - boot
    return {
        "os": osr.get("PRETTY_NAME") or platform.system(),
        "kernel": kernel,
        "newest_kernel": newest,
        "arch": platform.machine(),
        "hostname": socket.gethostname(),
        "desktop": os.environ.get("XDG_CURRENT_DESKTOP", "").replace(":", " / ") or None,
        "session": os.environ.get("XDG_SESSION_TYPE", "").capitalize() or None,
        "boot_time": boot,
        "uptime": uptime,
        "boot_duration": _boot_time_text(),
        "hardware": _hardware(),
        "selinux": selinux,
        "secure_boot": _secure_boot(),
        "failed_units": failed,
        "journal_error_count": err_count,
        "journal_errors": errors,
        "dnf_updates": dnf_count,
        "dnf_note": dnf_note,
        "flatpak_updates": flatpak_count,
        "findings": findings,
        "summary": f"{osr.get('NAME', 'Linux')} {osr.get('VERSION_ID', '')} · up "
                   + _short_uptime(uptime),
    }


def _short_uptime(seconds: float) -> str:
    days, rem = divmod(int(seconds), 86400)
    hours = rem // 3600
    return f"{days}d {hours}h" if days else f"{hours}h {(rem % 3600) // 60}m"
