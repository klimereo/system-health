"""Network interfaces, addresses, throughput, Wi-Fi signal and connectivity."""

from __future__ import annotations

import os
import socket
import time

import psutil

from ..util import CRIT, INFO, WARN, Finding, read, run


def _split_nmcli(line: str) -> list[str]:
    """Split nmcli terse output on unescaped colons."""
    fields, cur, i = [], [], 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line):
            cur.append(line[i + 1])
            i += 2
            continue
        if ch == ":":
            fields.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
        i += 1
    fields.append("".join(cur))
    return fields


def _wifi() -> dict | None:
    rc, out, _ = run(["nmcli", "-t", "-f", "IN-USE,SSID,SIGNAL,CHAN,RATE,SECURITY,DEVICE",
                      "device", "wifi", "list", "--rescan", "no"], timeout=5)
    if rc != 0:
        return None
    for line in out.splitlines():
        f = _split_nmcli(line)
        if len(f) >= 7 and f[0] == "*":
            return {
                "ssid": f[1] or "(hidden)",
                "signal": int(f[2]) if f[2].isdigit() else None,
                "channel": f[3],
                "rate": f[4],
                "security": f[5] or "Open",
                "device": f[6],
            }
    return None


def _connectivity():
    rc, out, _ = run(["nmcli", "networking", "connectivity"], timeout=5)
    return out.strip() if rc == 0 and out.strip() else None


def _default_gateway():
    try:
        with open("/proc/net/route", encoding="utf-8") as fh:
            next(fh, None)
            for line in fh:
                p = line.split()
                if len(p) > 2 and p[1] == "00000000" and int(p[3], 16) & 2:
                    gw = socket.inet_ntoa(bytes.fromhex(p[2])[::-1])
                    return gw, p[0]
    except (OSError, ValueError):
        pass
    return None, None


def _dns_servers() -> list[str]:
    rc, out, _ = run(["resolvectl", "dns"], timeout=3)
    servers = []
    if rc == 0:
        for line in out.splitlines():
            if ":" in line:
                servers.extend(s for s in line.split(":", 1)[1].split() if s not in servers)
    if not servers:
        try:
            with open("/etc/resolv.conf", encoding="utf-8") as fh:
                servers = [l.split()[1] for l in fh if l.startswith("nameserver")]
        except OSError:
            pass
    return servers


def _iface_kind(name: str) -> str:
    base = f"/sys/class/net/{name}"
    if os.path.isdir(f"{base}/wireless") or os.path.isdir(f"{base}/phy80211"):
        return "Wi-Fi"
    if not os.path.exists(f"{base}/device"):
        if name.startswith(("tun", "tap", "wg", "proton", "nordlynx")):
            return "VPN"
        return "Virtual"
    if name.startswith("ww"):
        return "Mobile"
    return "Ethernet"


def collect() -> dict:
    io1 = psutil.net_io_counters(pernic=True)
    t1 = time.monotonic()
    time.sleep(1.0)
    io2 = psutil.net_io_counters(pernic=True)
    dt = time.monotonic() - t1

    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    gateway, gw_iface = _default_gateway()
    wifi = _wifi()

    interfaces = []
    for name, st in stats.items():
        if name == "lo":
            continue
        ipv4 = [a.address for a in addrs.get(name, []) if a.family == socket.AF_INET]
        ipv6 = [a.address.split("%")[0] for a in addrs.get(name, []) if a.family == socket.AF_INET6]
        mac = next((a.address for a in addrs.get(name, []) if a.family == psutil.AF_LINK), None)
        a, b = io1.get(name), io2.get(name)
        interfaces.append({
            "name": name,
            "kind": _iface_kind(name),
            "up": st.isup,
            "carrier": read(f"/sys/class/net/{name}/operstate") == "up" or (st.isup and bool(ipv4 or ipv6)),
            "speed": st.speed or None,
            "mtu": st.mtu,
            "mac": mac,
            "ipv4": ipv4,
            "ipv6": ipv6,
            "rx_rate": (b.bytes_recv - a.bytes_recv) / dt if a and b else None,
            "tx_rate": (b.bytes_sent - a.bytes_sent) / dt if a and b else None,
            "rx_total": b.bytes_recv if b else None,
            "tx_total": b.bytes_sent if b else None,
            "errors": (b.errin + b.errout) if b else 0,
            "drops": (b.dropin + b.dropout) if b else 0,
            "default": name == gw_iface,
            "wifi": wifi if wifi and wifi["device"] == name else None,
        })
    kind_order = {"Ethernet": 0, "Wi-Fi": 0, "Mobile": 1, "VPN": 2, "Virtual": 3}
    interfaces.sort(key=lambda i: (not i["default"], not i["carrier"],
                                   kind_order.get(i["kind"], 9), i["name"]))

    connectivity = _connectivity()
    findings = []
    if connectivity == "none":
        findings.append(Finding(CRIT, "No network connection", "You are offline."))
    elif connectivity in ("limited", "portal"):
        findings.append(Finding(WARN, "Internet access is limited",
                                "Connected to a network, but the internet is not reachable"
                                + (" (a login page may be required)." if connectivity == "portal" else ".")))
    if wifi and wifi["signal"] is not None and wifi["signal"] < 35:
        findings.append(Finding(WARN if wifi["signal"] < 20 else INFO,
                                f"Weak Wi-Fi signal ({wifi['signal']}%)",
                                "Move closer to the router for a faster, more reliable connection."))

    active = next((i for i in interfaces if i["default"]), None)
    if active:
        label = f"Wi-Fi · {active['wifi']['ssid']}" if active["wifi"] else f"{active['kind']} · {active['name']}"
        summary = label
    else:
        summary = "Offline"
    return {
        "interfaces": interfaces,
        "connectivity": connectivity,
        "gateway": gateway,
        "dns": _dns_servers(),
        "hostname": socket.gethostname(),
        "wifi": wifi,
        "findings": findings,
        "summary": summary,
    }
