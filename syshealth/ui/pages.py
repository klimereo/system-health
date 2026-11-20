"""One page per health area. Each page rebuilds itself from a results snapshot."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QHBoxLayout, QHeaderView,
                               QLineEdit, QMessageBox, QPushButton, QScrollArea,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ..collectors import processes as proc_mod
from ..util import (CRIT, INFO, OK, UNKNOWN, WARN, fmt_bytes, fmt_duration, fmt_pct,
                    fmt_rate, fmt_temp, level_for, overall, rank)
from . import icons, theme
from .widgets import (Card, ClickableCard, FindingRow, MeterRow, Pill, ResponsiveGrid,
                      Ring, Stat, StatusIcon, empty_state, hbox, kv_grid, label,
                      section, stat_card, status_pill, vbox)

AREAS = [
    ("overview", "Overview"),
    ("cpu", "CPU"),
    ("memory", "Memory"),
    ("storage", "Storage"),
    ("battery", "Battery"),
    ("thermals", "Thermals"),
    ("gpu", "Graphics"),
    ("network", "Network"),
    ("processes", "Processes"),
    ("system", "System"),
]
AREA_TITLES = dict(AREAS)


def is_error(data) -> bool:
    return isinstance(data, dict) and "__error__" in data


def area_findings(results: dict, key: str) -> list:
    data = results.get(key)
    if not data or is_error(data):
        return []
    found = list(data.get("findings", []))
    if key == "storage" and results.get("smart"):
        found += results["smart"].get("findings", [])
    return found


def area_level(results: dict, key: str) -> str:
    data = results.get(key)
    if data is None:
        return UNKNOWN
    if is_error(data):
        return UNKNOWN
    return overall(area_findings(results, key), OK)


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().hide()  # hide now; deletion happens on the next event-loop pass
            item.widget().deleteLater()
        elif item.layout():
            clear_layout(item.layout())


def ring_card(title, percent, level, center, sub="") -> Card:
    card = Card(title)
    row = QHBoxLayout()
    row.addStretch(1)
    row.addWidget(Ring(percent, level, center, sub, size=120, thickness=11))
    row.addStretch(1)
    card.add(row)
    return card


def ts(t) -> str:
    return datetime.fromtimestamp(t).strftime("%H:%M:%S") if t else "—"


# ===================================================================== base ==

class Page(QWidget):
    key = ""
    scrollable = True

    def __init__(self, window):
        super().__init__()
        self.window = window
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.inner = QWidget()
        self.inner.setObjectName("pageBody")
        self.body = QVBoxLayout(self.inner)
        self.body.setContentsMargins(28, 6, 28, 28)
        self.body.setSpacing(14)
        if self.scrollable:
            self.scroll = QScrollArea()
            self.scroll.setWidgetResizable(True)
            self.scroll.setWidget(self.inner)
            self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            outer.addWidget(self.scroll)
        else:
            self.scroll = None
            outer.addWidget(self.inner)

    def subtitle(self, results) -> str:
        data = results.get(self.key)
        if data and not is_error(data):
            return data.get("summary", "")
        return ""

    def render(self, results: dict):
        pos = self.scroll.verticalScrollBar().value() if self.scroll else 0
        clear_layout(self.body)
        data = results.get(self.key)
        if data is None:
            self.body.addWidget(empty_state("Checking…", "Collecting a fresh snapshot."))
        elif is_error(data):
            self.body.addWidget(empty_state("Couldn't read this information", data["__error__"]))
        else:
            self.build(data, results)
        self.body.addStretch(1)
        if self.scroll:
            QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(pos))

    def build(self, data, results):
        raise NotImplementedError

    def findings_card(self, findings, title="Needs attention"):
        findings = [f for f in findings if f.level in (WARN, CRIT, INFO)]
        if not findings:
            return None
        findings.sort(key=lambda f: -rank(f.level))
        card = Card(title)
        for f in findings:
            card.add(FindingRow(f))
        return card

    def add_findings(self, results):
        card = self.findings_card(area_findings(results, self.key))
        if card:
            self.body.addWidget(card)


# ================================================================= overview ==

HERO_TEXT = {
    OK: ("Everything looks healthy", "No problems found in any area."),
    INFO: ("Everything looks healthy", "A few notes below, nothing urgent."),
    WARN: ("Some things need attention", "Have a look at the items below."),
    CRIT: ("Something needs attention now", "At least one critical problem was found."),
    UNKNOWN: ("Checking your computer…", "Collecting a fresh snapshot."),
}


class OverviewPage(Page):
    key = "overview"

    def subtitle(self, results):
        return "A quick health check of your whole computer"

    def render(self, results):
        pos = self.scroll.verticalScrollBar().value()
        clear_layout(self.body)
        self.build(None, results)
        self.body.addStretch(1)
        QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(pos))

    def build(self, _, results):
        keys = [k for k, _ in AREAS if k != "overview"]
        done = [k for k in keys if k in results]
        findings = [f for k in keys for f in area_findings(results, k)]
        level = overall(findings, OK) if len(done) == len(keys) else UNKNOWN
        if level == UNKNOWN and findings and rank(overall(findings)) >= rank(WARN):
            level = overall(findings)

        # Hero
        hero = Card(obj="hero", margins=(24, 22, 24, 22))
        row = QHBoxLayout()
        row.setSpacing(18)
        row.addWidget(StatusIcon({UNKNOWN: "info", INFO: OK}.get(level, level), 52), 0, Qt.AlignTop)
        title, sub = HERO_TEXT[level]
        n_warn = sum(f.level in (WARN, CRIT) for f in findings)
        if level in (WARN, CRIT):
            title = f"{n_warn} thing{'s' if n_warn != 1 else ''} need{'s' if n_warn == 1 else ''} attention"
        text = vbox(label(title, "heroTitle", wrap=True), label(sub, "muted", wrap=True), spacing=4)
        row.addLayout(text, 1)
        hero.add(row)
        self.body.addWidget(hero)

        # At a glance rings
        glance = ResponsiveGrid(min_col=150, max_cols=5)
        cpu, mem, sto, bat = (results.get(k) for k in ("cpu", "memory", "storage", "battery"))
        temps = results.get("thermals")

        def ring_tile(caption, percent, lvl, center, sub, key):
            tile = ClickableCard(margins=(12, 14, 12, 12), spacing=6)
            r = QHBoxLayout()
            r.addStretch(1)
            r.addWidget(Ring(percent, lvl, center, sub, size=104, thickness=9))
            r.addStretch(1)
            tile.add(r)
            cap = label(caption, "cardTitle")
            cap.setAlignment(Qt.AlignCenter)
            tile.add(cap)
            tile.clicked.connect(lambda: self.window.navigate(key))
            return tile

        if cpu and not is_error(cpu):
            glance.add(ring_tile("CPU", cpu["usage"], level_for(cpu["usage"], 85, 95),
                                 fmt_pct(cpu["usage"]), "busy", "cpu"))
        if mem and not is_error(mem):
            glance.add(ring_tile("Memory", mem["percent"], level_for(mem["percent"], 85, 95),
                                 fmt_pct(mem["percent"]), fmt_bytes(mem["used"], 1), "memory"))
        if sto and not is_error(sto) and sto["volumes"]:
            v = sto["volumes"][0]
            glance.add(ring_tile(f"Disk {v['mountpoint']}", v["percent"],
                                 level_for(v["percent"], 80, 90), fmt_pct(v["percent"]),
                                 f"{fmt_bytes(v['free'], 0)} free", "storage"))
        if bat and not is_error(bat) and bat["batteries"]:
            b = bat["batteries"][0]
            glance.add(ring_tile("Battery", b["capacity"], OK if (b["capacity"] or 0) > 15 else WARN,
                                 fmt_pct(b["capacity"]), b["status"].lower(), "battery"))
        if temps and not is_error(temps):
            cpu_t = cpu.get("temp") if cpu and not is_error(cpu) else None
            if cpu_t is not None:
                glance.add(ring_tile("CPU temperature", cpu_t, level_for(cpu_t, 85, 95),
                                     fmt_temp(cpu_t), "", "thermals"))
        if glance.items:
            self.body.addWidget(glance)

        # Attention list
        card = self.findings_card(findings)
        if card:
            self.body.addWidget(card)

        # Area tiles
        self.body.addWidget(section("All areas"))
        grid = ResponsiveGrid(min_col=240, max_cols=3)
        for key in keys:
            data = results.get(key)
            lvl = area_level(results, key)
            tile = ClickableCard(margins=(16, 14, 16, 14), spacing=6)
            head = QHBoxLayout()
            head.setSpacing(10)
            ico = label()
            ico.setPixmap(icons.pixmap(key, theme.tokens()["text"], 18))
            head.addWidget(ico)
            name = label(AREA_TITLES[key])
            name.setStyleSheet("font-weight: 650; font-size: 11pt;")
            head.addWidget(name)
            head.addStretch(1)
            if data is not None:
                head.addWidget(status_pill(lvl) if lvl != UNKNOWN else Pill("Error", UNKNOWN))
            tile.add(head)
            if data is None:
                summary = "Checking…"
            elif is_error(data):
                summary = data["__error__"]
            else:
                summary = data.get("summary", "")
            tile.add(label(summary, "muted", wrap=True))
            tile.clicked.connect(lambda k=key: self.window.navigate(k))
            grid.add(tile)
        self.body.addWidget(grid)


# ====================================================================== CPU ==

class CpuPage(Page):
    key = "cpu"

    def subtitle(self, results):
        d = results.get("cpu")
        return d["model"] if d and not is_error(d) else ""

    def build(self, d, results):
        self.add_findings(results)
        grid = ResponsiveGrid(min_col=200, max_cols=4)
        grid.add(ring_card("Usage", d["usage"], level_for(d["usage"], 85, 95),
                           fmt_pct(d["usage"]), "all cores"))
        t = d["temp"]
        grid.add(stat_card("Temperature", fmt_temp(t),
                           "Package sensor" if t is not None else "No sensor found",
                           level_for(t, 85, 95) if t is not None else None))
        if d["freq_current"]:
            sub = f"max {d['freq_max'] / 1000:.2f} GHz" if d["freq_max"] else None
            grid.add(stat_card("Clock speed", f"{d['freq_current'] / 1000:.2f} GHz", sub))
        l1, l5, l15 = d["load"]
        grid.add(stat_card("Load average", f"{l1:.2f}",
                           f"5 min {l5:.2f} · 15 min {l15:.2f}\n{d['logical']} threads available",
                           level_for(d["load_ratio"], 1.0, 2.0)))
        self.body.addWidget(grid)

        cores = Card("Per-thread usage")
        cg = ResponsiveGrid(min_col=170, max_cols=4, spacing=16)
        for i, pct in enumerate(d["per_core"]):
            freq = d["core_freqs"][i] if i < len(d["core_freqs"]) else None
            value = fmt_pct(pct) + (f" · {freq / 1000:.1f} GHz" if freq else "")
            cg.add(MeterRow(f"#{i}", value, pct, level_for(pct, 85, 98)))
        cores.add(cg)
        self.body.addWidget(cores)

        details = Card("Details")
        details.add(kv_grid([
            ("Processor", d["model"]),
            ("Cores", f"{d['physical']} physical · {d['logical']} threads" if d["physical"] else str(d["logical"])),
            ("Frequency range", f"{d['freq_min'] / 1000:.2f} – {d['freq_max'] / 1000:.2f} GHz"
             if d["freq_min"] and d["freq_max"] else None),
            ("Scaling driver", d["driver"]),
            ("Governor", d["governor"]),
            ("Energy preference", d["epp"].replace("_", " ") if d["epp"] else None),
        ]))
        self.body.addWidget(details)
        self.body.addWidget(label("Usage is sampled over 0.7 seconds on each refresh.", "faint"))


# =================================================================== Memory ==

class MemoryPage(Page):
    key = "memory"

    def build(self, d, results):
        self.add_findings(results)
        grid = ResponsiveGrid(min_col=200, max_cols=4)
        lvl = level_for(d["percent"], 85, 95)
        grid.add(ring_card("RAM in use", d["percent"], lvl, fmt_pct(d["percent"]),
                           f"{fmt_bytes(d['used'])} / {fmt_bytes(d['total'], 0)}"))
        grid.add(stat_card("Available", fmt_bytes(d["available"]),
                           "Free for new apps right now"))
        grid.add(stat_card("Cache & buffers", fmt_bytes(d["cached"]),
                           "Reclaimed automatically when apps need it"))
        if d["swap_total"]:
            grid.add(stat_card("Swap used", fmt_bytes(d["swap_used"]),
                               f"of {fmt_bytes(d['swap_total'])}",
                               level_for(d["swap_percent"], 80, 95)))
        else:
            grid.add(stat_card("Swap", "None", "No swap configured", INFO))
        self.body.addWidget(grid)

        usage = Card("Usage")
        usage.add(MeterRow("RAM", f"{fmt_bytes(d['used'])} of {fmt_bytes(d['total'])}",
                           d["percent"], lvl))
        zram = {f"/dev/{z['name']}": z for z in d["zram"]}
        for s in d["swaps"]:
            pct = s["used"] / s["size"] * 100 if s["size"] else 0
            z = zram.get(s["name"])
            caption = None
            if z:
                caption = f"Compressed swap in RAM (zram, {z['algorithm']})"
                if z["ratio"] and z["orig"] and z["orig"] > 1024 ** 2:
                    caption += f" · {z['ratio']:.1f}× compression"
            usage.add(MeterRow(f"Swap · {s['name']}", f"{fmt_bytes(s['used'])} of {fmt_bytes(s['size'])}",
                               pct, level_for(pct, 80, 95), caption))
        self.body.addWidget(usage)

        top = Card("Biggest memory users")
        for app in d["top"]:
            name = app["name"] + (f"  ×{app['count']}" if app["count"] > 1 else "")
            top.add(MeterRow(name, fmt_bytes(app["rss"]), app["rss"] / d["total"] * 100, INFO))
        top.add(label("Grouped by program name. Shared memory is counted for each process, "
                      "so totals can be slightly overstated.", "faint", wrap=True))
        self.body.addWidget(top)


# ================================================================== Storage ==

class StoragePage(Page):
    key = "storage"

    def build(self, d, results):
        self.add_findings(results)
        self.body.addWidget(section("Filesystems"))
        grid = ResponsiveGrid(min_col=300, max_cols=3)
        for v in d["volumes"]:
            lvl = level_for(v["percent"], 80, 90)
            card = Card(" · ".join(v["mountpoints"][:3]), Pill(v["fstype"], INFO))
            card.add(Stat("Free space", fmt_bytes(v["free"]), None, lvl if lvl != OK else None))
            card.add(MeterRow("Used", f"{fmt_bytes(v['used'])} of {fmt_bytes(v['total'])} · "
                              f"{v['percent']:.0f}%", v["percent"], lvl))
            cap = v["device"]
            if v["fstype"] == "btrfs" and len(v["mountpoints"]) > 1:
                cap += " · Btrfs subvolumes share this space"
            if v["readonly"]:
                cap += " · read-only"
            card.add(label(cap, "faint", wrap=True))
            grid.add(card)
        self.body.addWidget(grid)

        smart = results.get("smart")
        head = QHBoxLayout()
        head.addWidget(section("Drives"))
        head.addStretch(1)
        if d["smartctl"] and d["drives"]:
            btn = QPushButton("Reading…" if self.window.smart_running else
                              ("Re-check drive health" if smart else "Check drive health"))
            btn.setObjectName("primary" if not smart else "")
            btn.setIcon(icons.icon("lock", "#ffffff" if not smart else theme.tokens()["text"], 16))
            btn.setEnabled(not self.window.smart_running)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(self.window.read_smart)
            head.addWidget(btn)
        self.body.addLayout(head)

        if not d["smartctl"]:
            self.body.addWidget(label("Install smartmontools to see drive health: "
                                      "sudo dnf install smartmontools", "muted", wrap=True))
        elif smart and smart.get("error"):
            self.body.addWidget(label(smart["error"], "muted", wrap=True))
        elif not smart:
            self.body.addWidget(label(
                "Drive health (SMART) needs administrator access. Click “Check drive health” "
                "and enter your password; the data is read once with smartctl.",
                "muted", wrap=True))
        elif smart.get("time"):
            note = f"Drive health read at {ts(smart['time'])}"
            if smart.get("notice"):
                note += f" · last re-check: {smart['notice']}"
            self.body.addWidget(label(note, "faint"))

        grid = ResponsiveGrid(min_col=380, max_cols=2)
        for drv in d["drives"]:
            grid.add(self.drive_card(drv, (smart or {}).get("drives", {}).get(drv["path"])))
        self.body.addWidget(grid)

    def drive_card(self, drv, s):
        kind = "HDD" if drv["rotational"] else "SSD"
        pills = QWidget()
        pl = hbox(Pill(drv["transport"], INFO), Pill(kind, INFO), spacing=6)
        pills.setLayout(pl)
        card = Card(drv["model"], pills)
        rows = [
            ("Device", drv["path"]),
            ("Capacity", fmt_bytes(drv["size"])),
            ("Firmware", drv["firmware"]),
            ("Temperature", fmt_temp(drv["temp"]) if drv["temp"] else None,
             level_for(drv["temp"], 65, 75) if drv["temp"] else None),
            ("Removable", "Yes" if drv["removable"] else None),
        ]
        if s and not s.get("error"):
            passed = s.get("passed")
            status = Pill("SMART: PASSED" if passed else "SMART: FAILED" if passed is False
                          else "SMART: unknown", OK if passed else CRIT if passed is False else UNKNOWN)
            card.add(hbox(status, None))
            used = s.get("percentage_used")
            if used is not None:
                card.add(MeterRow("Rated life used", f"{used}%", used, level_for(used, 70, 90),
                                  "How much of the manufacturer's write endurance has been consumed."))
            rows += [
                ("Power-on time", f"{s['power_on_hours']:,} hours "
                 f"(~{s['power_on_hours'] / 24 / 365:.1f} years)" if s.get("power_on_hours") is not None else None),
                ("Power cycles", f"{s['power_cycles']:,}" if s.get("power_cycles") is not None else None),
                ("Unsafe shutdowns", f"{s['unsafe_shutdowns']:,}" if s.get("unsafe_shutdowns") is not None else None),
                ("Available spare", f"{s['available_spare']}% (threshold {s.get('available_spare_threshold')}%)"
                 if s.get("available_spare") is not None else None),
                ("Media errors", str(s["media_errors"]) if s.get("media_errors") is not None else None,
                 WARN if s.get("media_errors") else OK),
                ("Reallocated sectors", str(s["reallocated"]) if s.get("reallocated") is not None else None,
                 WARN if s.get("reallocated") else OK),
                ("Pending sectors", str(s["pending"]) if s.get("pending") is not None else None,
                 WARN if s.get("pending") else OK),
                ("Data written", fmt_bytes(s["data_written"]) if s.get("data_written") else None),
                ("Data read", fmt_bytes(s["data_read"]) if s.get("data_read") else None),
            ]
        elif s and s.get("error"):
            rows.append(("SMART", s["error"]))
        card.add(kv_grid(rows, key_width=140))
        return card


# ================================================================== Battery ==

class BatteryPage(Page):
    key = "battery"

    def build(self, d, results):
        self.add_findings(results)
        if not d["batteries"]:
            self.body.addWidget(empty_state("No battery detected",
                                            "This looks like a desktop computer."))
        for b in d["batteries"]:
            self.battery(b, d)
        if d["peripherals"]:
            card = Card("Wireless devices")
            for p in d["peripherals"]:
                if p["capacity"] is not None:
                    value = f"{p['capacity']}%"
                elif p["level"]:
                    value = p["level"]
                else:
                    value = "Level not reported"
                title = p["model"] + (f" · {p['manufacturer']}" if p["manufacturer"] else "")
                lvl = level_for(p["approx"], 25, 10, low_is_bad=True) if p["approx"] is not None else UNKNOWN
                card.add(MeterRow(title, value, p["approx"] or 0, lvl if lvl != OK else INFO,
                                  None if p["status"] == "Unknown" else p["status"]))
            self.body.addWidget(card)

    def battery(self, b, d):
        grid = ResponsiveGrid(min_col=200, max_cols=4)
        cap = b["capacity"]
        grid.add(ring_card("Charge", cap, OK if (cap or 0) > 20 else WARN if (cap or 0) > 10 else CRIT,
                           fmt_pct(cap), b["status"].lower()))
        h = b["health"]
        grid.add(stat_card("Health", fmt_pct(h),
                           f"{b['full_wh']:.1f} of {b['design_wh']:.1f} Wh original"
                           if b["full_wh"] and b["design_wh"] else None,
                           level_for(h, 80, 60, low_is_bad=True) if h is not None else None))
        grid.add(stat_card("Charge cycles", str(b["cycles"]) if b["cycles"] is not None else "—",
                           "Most batteries are rated for 500–1000"))
        if b["status"] == "Discharging":
            grid.add(stat_card("Time left", fmt_duration(b["hours_left"] * 3600) if b["hours_left"] else "—",
                               f"Drawing {b['power_w']:.1f} W" if b["power_w"] else None))
        elif b["status"] == "Charging":
            grid.add(stat_card("Until full", fmt_duration(b["hours_left"] * 3600) if b["hours_left"] else "—",
                               f"Charging at {b['power_w']:.1f} W" if b["power_w"] else None))
        else:
            grid.add(stat_card("Power", "Plugged in" if d["ac_online"] else b["status"],
                               b["charge_mode"] and f"Charge mode: {b['charge_mode']}"))
        self.body.addWidget(grid)

        if h is not None:
            hc = Card("Battery wear")
            hc.add(MeterRow("Capacity compared with new", fmt_pct(h, 1), h,
                            level_for(h, 80, 60, low_is_bad=True),
                            "A new battery is 100%. Below about 80% you will notice shorter "
                            "runtime; below 60% consider replacing it."))
            self.body.addWidget(hc)

        details = Card("Details")
        details.add(kv_grid([
            ("Status", b["status"]),
            ("Charger", None if d["ac_online"] is None else ("Connected" if d["ac_online"] else "Not connected")),
            ("Charge mode", b["charge_mode"]),
            ("Charge limit", f"{b['charge_limit']}%" if b["charge_limit"] else None),
            ("Power profile", d["power_profile"].replace("-", " ").capitalize() if d["power_profile"] else None),
            ("Energy now", f"{b['now_wh']:.1f} Wh" if b["now_wh"] is not None else None),
            ("Full charge", f"{b['full_wh']:.1f} Wh" if b["full_wh"] else None),
            ("Design capacity", f"{b['design_wh']:.1f} Wh" if b["design_wh"] else None),
            ("Voltage", f"{b['voltage']:.2f} V" if b["voltage"] else None),
            ("Technology", b["technology"]),
            ("Manufacturer", b["manufacturer"]),
            ("Model", b["model"]),
        ]))
        self.body.addWidget(details)


# ================================================================= Thermals ==

class ThermalsPage(Page):
    key = "thermals"

    def build(self, d, results):
        self.add_findings(results)
        if not d["chips"]:
            self.body.addWidget(empty_state("No sensors found",
                                            "This system does not expose temperature sensors."))
            return
        grid = ResponsiveGrid(min_col=340, max_cols=2)
        for chip in d["chips"]:
            if not chip["temps"] and not chip["fans"]:
                continue
            card = Card(chip["name"], status_pill(chip.get("level", OK)))
            for t in chip["temps"]:
                scale = max(t["crit_limit"], 100)
                card.add(MeterRow(t["label"], fmt_temp(t["value"]), t["value"] / scale * 100, t["level"]))
            for f in chip["fans"]:
                card.add(MeterRow(f["label"], f"{f['rpm']:,} RPM", min(f["rpm"] / 6000 * 100, 100), INFO))
            if chip["temps"]:
                t0 = chip["temps"][0]
                card.add(label(f"Attention above {t0['warn']:.0f}°C · critical at {t0['crit_limit']:.0f}°C",
                               "faint"))
            grid.add(card)
        self.body.addWidget(grid)
        if not d["fan_count"]:
            self.body.addWidget(label(
                "No fan speed sensors are exposed. That's normal on many laptops, where the "
                "embedded controller manages the fans on its own.", "faint", wrap=True))


# ====================================================================== GPU ==

class GpuPage(Page):
    key = "gpu"

    def build(self, d, results):
        self.add_findings(results)
        if not d["gpus"]:
            self.body.addWidget(empty_state("No graphics card found"))
            return
        for g in d["gpus"]:
            pills = QWidget()
            pills.setLayout(hbox(Pill("Integrated" if g["integrated"] else "Dedicated", INFO),
                                 *( [Pill("Primary", OK)] if g.get("primary") else []), spacing=6))
            name = vbox(label(g["name"], "midValue", select=True),
                        label(g["codename"], "muted") if g.get("codename") else None, spacing=2)
            head = hbox(name, None, pills)
            self.body.addLayout(head)

            grid = ResponsiveGrid(min_col=190, max_cols=4)
            if g.get("busy") is not None:
                grid.add(ring_card("Usage", g["busy"], level_for(g["busy"], 90, 101),
                                   fmt_pct(g["busy"]), "busy"))
            if g.get("temp") is not None:
                grid.add(stat_card("Temperature", fmt_temp(g["temp"]), None, level_for(g["temp"], 85, 100)))
            if g.get("clock_mhz"):
                grid.add(stat_card("Clock speed", f"{g['clock_mhz']:.0f} MHz",
                                   f"max {g['clock_max_mhz']:.0f} MHz" if g.get("clock_max_mhz") else None))
            if g.get("power_w") is not None:
                sub = f"limit {g['power_cap_w']:.0f} W" if g.get("power_cap_w") else None
                if g["integrated"] and g["vendor"] == "AMD":
                    sub = "Whole processor chip (CPU + GPU)"
                grid.add(stat_card("Power draw", f"{g['power_w']:.1f} W", sub))
            if grid.items:
                self.body.addWidget(grid)

            if g.get("vram_total") or g.get("gtt_total"):
                mem = Card("Video memory")
                if g.get("vram_total"):
                    pct = g["vram_used"] / g["vram_total"] * 100
                    mem.add(MeterRow("Dedicated (VRAM)" if not g["integrated"] else "Reserved (VRAM)",
                                     f"{fmt_bytes(g['vram_used'])} of {fmt_bytes(g['vram_total'])}", pct,
                                     level_for(pct, 90, 98) if not g["integrated"] else INFO))
                if g.get("gtt_total"):
                    pct = g["gtt_used"] / g["gtt_total"] * 100
                    mem.add(MeterRow("Shared system memory (GTT)",
                                     f"{fmt_bytes(g['gtt_used'])} of {fmt_bytes(g['gtt_total'])}", pct, INFO))
                if g["integrated"]:
                    mem.add(label("Integrated graphics reserve a small block of RAM and borrow more "
                                  "from system memory as needed.", "faint", wrap=True))
                self.body.addWidget(mem)

            details = Card("Details")
            details.add(kv_grid([
                ("Vendor", g["vendor"]),
                ("Driver", g.get("driver")),
                ("PCI slot", g.get("slot")),
                ("Fan", f"{g['fan_rpm']:,} RPM" if g.get("fan_rpm") is not None else None),
            ]))
            self.body.addWidget(details)


# ================================================================== Network ==

class NetworkPage(Page):
    key = "network"

    def build(self, d, results):
        self.add_findings(results)
        conn = d["connectivity"]
        conn_level = {"full": OK, "limited": WARN, "portal": WARN, "none": CRIT}.get(conn, UNKNOWN)
        conn_text = {"full": "Online", "limited": "Limited", "portal": "Login required",
                     "none": "Offline"}.get(conn, "Unknown")

        grid = ResponsiveGrid(min_col=300, max_cols=2)
        status = Card("Connection", status_pill(conn_level, conn_text))
        status.add(kv_grid([
            ("Hostname", d["hostname"]),
            ("Default gateway", d["gateway"] or "None"),
            ("DNS servers", ", ".join(d["dns"][:4]) if d["dns"] else None),
        ], key_width=130))
        grid.add(status)
        w = d["wifi"]
        if w:
            wl = level_for(w["signal"], 35, 20, low_is_bad=True) if w["signal"] is not None else UNKNOWN
            wc = Card("Wi-Fi")
            wc.add(label(w["ssid"], "midValue", wrap=True, select=True))
            if w["signal"] is not None:
                wc.add(MeterRow("Signal strength", f"{w['signal']}%", w["signal"], wl if wl != OK else OK))
            wc.add(kv_grid([("Channel", w["channel"]), ("Link rate", w["rate"]),
                            ("Security", w["security"])], key_width=130))
            grid.add(wc)
        self.body.addWidget(grid)

        self.body.addWidget(section("Interfaces"))
        grid = ResponsiveGrid(min_col=320, max_cols=2)
        for i in d["interfaces"]:
            pills = QWidget()
            items = [Pill(i["kind"], INFO), Pill("Connected" if i["carrier"] else "Down",
                                                  OK if i["carrier"] else UNKNOWN)]
            if i["default"]:
                items.insert(0, Pill("Default route", OK))
            pills.setLayout(hbox(*items, spacing=6))
            card = Card(i["name"], pills)
            if i["carrier"]:
                card.add(hbox(Stat("Download", fmt_rate(i["rx_rate"]), big=False),
                              Stat("Upload", fmt_rate(i["tx_rate"]), big=False), None, spacing=28))
            card.add(kv_grid([
                ("IPv4", ", ".join(i["ipv4"]) if i["ipv4"] else None),
                ("IPv6", "\n".join(i["ipv6"][:2]) if i["ipv6"] else None),
                ("MAC", i["mac"]),
                ("Link speed", f"{i['speed']} Mb/s" if i["speed"] else None),
                ("MTU", str(i["mtu"])),
                ("Since boot", f"↓ {fmt_bytes(i['rx_total'])}  ↑ {fmt_bytes(i['tx_total'])}"
                 if i["rx_total"] is not None else None),
                ("Errors / drops", f"{i['errors']} / {i['drops']}" if i["errors"] or i["drops"] else None),
            ], key_width=110))
            grid.add(card)
        self.body.addWidget(grid)
        self.body.addWidget(label("Throughput is sampled over one second on each refresh.", "faint"))


# ================================================================ Processes ==

class NumItem(QTableWidgetItem):
    def __init__(self, text, value):
        super().__init__(text)
        self.setData(Qt.UserRole, value)
        self.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

    def __lt__(self, other):
        return (self.data(Qt.UserRole) or 0) < (other.data(Qt.UserRole) or 0)


class ProcessesPage(Page):
    key = "processes"
    scrollable = False
    COLUMNS = ["Name", "PID", "User", "CPU", "Memory", "Threads", "Status"]

    def __init__(self, window):
        super().__init__(window)
        self.rows = []
        self.built = False

    def _build_ui(self):
        self.built = True
        bar = QHBoxLayout()
        bar.setSpacing(10)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter by name, user, PID or command…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.apply_filter)
        bar.addWidget(self.search, 1)
        self.mine = QCheckBox("Only my processes")
        self.mine.toggled.connect(self.apply_filter)
        bar.addWidget(self.mine)
        self.end_btn = QPushButton("End process")
        self.end_btn.clicked.connect(lambda: self.signal(False))
        self.kill_btn = QPushButton("Force kill")
        self.kill_btn.setObjectName("danger")
        self.kill_btn.clicked.connect(lambda: self.signal(True))
        bar.addWidget(self.end_btn)
        bar.addWidget(self.kill_btn)
        self.body.addLayout(bar)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setDefaultSectionSize(32)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, len(self.COLUMNS)):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hdr.setHighlightSections(False)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(3, Qt.DescendingOrder)
        self.table.itemSelectionChanged.connect(self.update_buttons)
        self.body.addWidget(self.table, 1)
        self.footer = label("", "faint")
        self.body.addWidget(self.footer)
        self.update_buttons()

    def render(self, results):
        if not self.built:
            self._build_ui()
        d = results.get("processes")
        if d is None or is_error(d):
            self.footer.setText("Checking…" if d is None else d["__error__"])
            return
        selected = self.selected_pid()
        scroll = self.table.verticalScrollBar().value()
        self.rows = d["rows"]
        t = self.table
        t.setSortingEnabled(False)
        t.setRowCount(len(self.rows))
        muted = theme.color("muted")
        for r, p in enumerate(self.rows):
            name = QTableWidgetItem(p["name"])
            name.setData(Qt.UserRole, p["pid"])
            name.setToolTip(p["cmdline"] or p["name"])
            items = [
                name,
                NumItem(str(p["pid"]), p["pid"]),
                QTableWidgetItem(p["user"]),
                NumItem(f"{p['cpu']:.1f}%", p["cpu"]),
                NumItem(fmt_bytes(p["rss"]), p["rss"]),
                NumItem(str(p["threads"]), p["threads"]),
                QTableWidgetItem(p["status"]),
            ]
            for c, item in enumerate(items):
                if c in (2, 6) or not p["own"]:
                    item.setForeground(muted)
                t.setItem(r, c, item)
        t.setSortingEnabled(True)
        self.apply_filter()
        if selected is not None:
            for r in range(t.rowCount()):
                if t.item(r, 0).data(Qt.UserRole) == selected:
                    t.selectRow(r)
                    break
        t.verticalScrollBar().setValue(scroll)
        self.footer.setText(f"{d['total']} processes · {d['threads']:,} threads · CPU % is a share "
                            "of the whole processor, measured over 0.7 seconds. Grey rows belong to "
                            "other users or the system. Kernel threads are hidden.")

    def apply_filter(self):
        text = self.search.text().strip().lower()
        only_mine = self.mine.isChecked()
        by_pid = {p["pid"]: p for p in self.rows}
        for r in range(self.table.rowCount()):
            p = by_pid.get(self.table.item(r, 0).data(Qt.UserRole))
            hide = p is None
            if p:
                if only_mine and not p["own"]:
                    hide = True
                elif text and text not in p["name"].lower() and text not in p["user"].lower() \
                        and text != str(p["pid"]) and text not in p["cmdline"].lower():
                    hide = True
            self.table.setRowHidden(r, hide)

    def selected_pid(self):
        if not self.built:
            return None
        items = self.table.selectedItems()
        if not items:
            return None
        return self.table.item(items[0].row(), 0).data(Qt.UserRole)

    def update_buttons(self):
        has = self.selected_pid() is not None
        self.end_btn.setEnabled(has)
        self.kill_btn.setEnabled(has)

    def signal(self, force: bool):
        pid = self.selected_pid()
        if pid is None:
            return
        p = next((x for x in self.rows if x["pid"] == pid), None)
        name = p["name"] if p else str(pid)
        action = "Force kill" if force else "End"
        msg = (f"{action} “{name}” (PID {pid})?\n\n" +
               ("The process is stopped immediately; unsaved work will be lost."
                if force else "The process is asked to quit; unsaved work may be lost."))
        if QMessageBox.question(self, f"{action} process", msg) != QMessageBox.Yes:
            return
        err = proc_mod.signal_process(pid, force)
        if err:
            QMessageBox.warning(self, "Couldn't stop the process", err)
            return
        QTimer.singleShot(400, lambda: self.window.refresh(["processes"], manual=False))


# =================================================================== System ==

class SystemPage(Page):
    key = "system"

    def subtitle(self, results):
        d = results.get("system")
        return d["os"] if d and not is_error(d) else ""

    def build(self, d, results):
        self.add_findings(results)
        grid = ResponsiveGrid(min_col=200, max_cols=4)
        grid.add(stat_card("Uptime", fmt_duration(d["uptime"]),
                           "Since " + datetime.fromtimestamp(d["boot_time"]).strftime("%a %d %b, %H:%M")))
        upd = (d["dnf_updates"] or 0) + (d["flatpak_updates"] or 0)
        parts = []
        if d["dnf_updates"] is not None:
            parts.append(f"{d['dnf_updates']} packages")
        if d["flatpak_updates"] is not None:
            parts.append(f"{d['flatpak_updates']} Flatpak apps")
        grid.add(stat_card("Updates available", str(upd), " · ".join(parts) or d["dnf_note"],
                           INFO if upd else None))
        nf = len(d["failed_units"])
        grid.add(stat_card("Failed services", str(nf), "All services running" if not nf else "See below",
                           WARN if nf else None))
        ne = d["journal_error_count"]
        grid.add(stat_card("Errors this boot", "—" if ne is None else str(ne), "From the system journal"))
        self.body.addWidget(grid)

        info = Card("This computer")
        hw = d["hardware"]
        kernel = d["kernel"]
        if d["newest_kernel"] and d["newest_kernel"] != kernel:
            kernel += f"  (installed: {d['newest_kernel']}; restart to use it)"
        sb = d["secure_boot"]
        info.add(kv_grid([
            ("Model", hw["model"]),
            ("Manufacturer", hw["vendor"]),
            ("Firmware (BIOS)", hw["bios"]),
            ("Operating system", d["os"]),
            ("Kernel", kernel),
            ("Architecture", d["arch"]),
            ("Desktop", " · ".join(x for x in (d["desktop"], d["session"]) if x) or None),
            ("Hostname", d["hostname"]),
            ("Last boot took", d["boot_duration"]),
            ("SELinux", d["selinux"], INFO if d["selinux"] == "Disabled" else None),
            ("Secure Boot", "Legacy BIOS boot" if sb == "legacy" else
             "Enabled" if sb is True else "Disabled" if sb is False else None),
        ]))
        self.body.addWidget(info)

        if d["failed_units"]:
            card = Card("Failed services")
            for u in d["failed_units"]:
                row = hbox(StatusIcon(WARN, 18), label(u["unit"], select=True),
                           label(u["description"], "muted", wrap=True), None, Pill(u["scope"], INFO),
                           spacing=10)
                card.add(row)
            card.add(label("Inspect with: systemctl status <unit>  (add --user for user services)",
                           "faint", wrap=True))
            self.body.addWidget(card)

        if d["dnf_updates"] is not None or d["flatpak_updates"] is not None:
            card = Card("Updates")
            card.add(label("Install updates from Discover, or in a terminal run:  "
                           "sudo dnf upgrade --refresh  and  flatpak update", "muted", wrap=True))
            card.add(label("Package count comes from cached metadata, so it may lag slightly behind.",
                           "faint", wrap=True))
            self.body.addWidget(card)

        errs = d["journal_errors"]
        if errs:
            card = Card(f"Recent errors · {d['journal_error_count']} this boot")
            for e in errs:
                when = datetime.fromtimestamp(e["time"]).strftime("%H:%M:%S") if e["time"] else ""
                msg = label(e["message"], wrap=True, select=True)
                row = hbox(label(when, "mono"), Pill(e["source"][:24], INFO), spacing=10)
                card.add(vbox(row, msg, spacing=4))
            card.add(label("A few errors are normal on every system; they matter only if "
                           "something is misbehaving.", "faint", wrap=True))
            self.body.addWidget(card)
        self.body.addWidget(label("Updates, services and errors are re-checked every 5 minutes "
                                  "(they are slower and contact Flathub). Refresh checks them now.",
                                  "faint", wrap=True))


PAGE_CLASSES = {
    "overview": OverviewPage,
    "cpu": CpuPage,
    "memory": MemoryPage,
    "storage": StoragePage,
    "battery": BatteryPage,
    "thermals": ThermalsPage,
    "gpu": GpuPage,
    "network": NetworkPage,
    "processes": ProcessesPage,
    "system": SystemPage,
}
