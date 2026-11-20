"""Main window: sidebar navigation, header with refresh, background collection."""

from __future__ import annotations

import time
import traceback
from datetime import datetime

from PySide6.QtCore import QEvent, QObject, QRunnable, QSettings, QSize, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QIcon, QKeySequence, QPainter, QPixmap, QShortcut, QTransform
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QMainWindow, QPushButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from .. import APP_NAME, __version__
from ..collectors import COLLECTORS
from ..collectors.storage import read_smart
from . import icons, theme
from .pages import AREAS, PAGE_CLASSES, area_level
from .widgets import NavButton, label

AUTO_REFRESH_MS = 5000
# Collectors that are slow or touch the network refresh less often automatically
# (seconds). A manual refresh always runs everything.
SLOW_INTERVALS = {"system": 300}

THEME_MODES = ["auto", "light", "dark"]
THEME_LABEL = {"auto": "Theme: System", "light": "Theme: Light", "dark": "Theme: Dark"}
THEME_ICON = {"auto": "auto", "light": "sun", "dark": "moon"}


class _Signals(QObject):
    done = Signal(str, object, int)


class Job(QRunnable):
    def __init__(self, name, fn, signals, generation):
        super().__init__()
        self.name, self.fn, self.signals, self.generation = name, fn, signals, generation

    def run(self):
        try:
            result = self.fn()
        except Exception as exc:  # noqa: BLE001 - report any collector failure in the UI
            traceback.print_exc()
            result = {"__error__": f"{type(exc).__name__}: {exc}"}
        try:
            self.signals.done.emit(self.name, result, self.generation)
        except RuntimeError:
            pass  # window was closed while this job was still running


class MainWindow(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.settings = QSettings("system-health", "system-health")
        self.theme_mode = self.settings.value("theme", "auto")
        if self.theme_mode not in THEME_MODES:
            self.theme_mode = "auto"
        theme.apply(app, self.theme_mode)

        self.results: dict = {}
        self.pending: set[str] = set()
        self.generation = 0
        self.smart_running = False
        self.last_refresh = None
        self.last_run: dict[str, float] = {}
        self.dirty: set[str] = set()
        self.manual_busy = False
        self.round_started = time.monotonic()
        self.auto_timer = QTimer(self)
        self.auto_timer.setSingleShot(True)
        self.auto_timer.setInterval(AUTO_REFRESH_MS)
        self.auto_timer.timeout.connect(self.auto_refresh)
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(max(4, len(COLLECTORS)))
        self.signals = _Signals()
        self.signals.done.connect(self.on_result)

        self.setWindowTitle(APP_NAME)
        self.resize(1180, 800)
        self.setMinimumSize(760, 540)
        self._build()

        app.styleHints().colorSchemeChanged.connect(self._system_scheme_changed)
        QShortcut(QKeySequence("F5"), self, activated=self.refresh)
        QShortcut(QKeySequence("Ctrl+R"), self, activated=self.refresh)
        QShortcut(QKeySequence("Ctrl+Q"), self, activated=self.close)

        self.current = "overview"
        self.navigate(self.settings.value("page", "overview"))
        QTimer.singleShot(50, self.refresh)

    # ------------------------------------------------------------- layout --
    def _build(self):
        root = QWidget()
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Sidebar
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(222)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 18, 0, 14)
        sl.setSpacing(2)
        brand = QHBoxLayout()
        brand.setContentsMargins(20, 0, 16, 14)
        brand.setSpacing(10)
        self.logo = label()
        brand.addWidget(self.logo)
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        brand_text.addWidget(label(APP_NAME, "appTitle"))
        brand_text.addWidget(label(f"Version {__version__}", "appSubtitle"))
        brand.addLayout(brand_text, 1)
        sl.addLayout(brand)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav: dict[str, NavButton] = {}
        for key, title in AREAS:
            btn = NavButton(key, title)
            btn.clicked.connect(lambda _=False, k=key: self.navigate(k))
            self.nav_group.addButton(btn)
            self.nav[key] = btn
            sl.addWidget(btn)
        sl.addStretch(1)

        self.theme_btn = QPushButton()
        self.theme_btn.setObjectName("ghost")
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self.theme_btn.clicked.connect(self.cycle_theme)
        tb = QHBoxLayout()
        tb.setContentsMargins(10, 0, 10, 0)
        tb.addWidget(self.theme_btn)
        tb.addStretch(1)
        sl.addLayout(tb)
        lay.addWidget(side)

        # Content
        content = QWidget()
        content.setObjectName("content")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(28, 22, 28, 14)
        header.setSpacing(12)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.page_title = label("", "pageTitle")
        self.page_sub = label("", "pageSubtitle")
        titles.addWidget(self.page_title)
        titles.addWidget(self.page_sub)
        header.addLayout(titles, 1)
        self.updated = label("", "faint")
        header.addWidget(self.updated, 0, Qt.AlignBottom)
        self.refresh_btn = QPushButton("  Refresh")
        self.refresh_btn.setObjectName("primary")
        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_btn.setToolTip("Take a new snapshot (F5)")
        self.refresh_btn.setIconSize(QSize(16, 16))
        self.refresh_btn.clicked.connect(lambda: self.refresh())
        header.addWidget(self.refresh_btn, 0, Qt.AlignBottom)
        cl.addLayout(header)

        self.stack = QStackedWidget()
        self.pages = {}
        for key, _ in AREAS:
            page = PAGE_CLASSES[key](self)
            self.pages[key] = page
            self.stack.addWidget(page)
        cl.addWidget(self.stack, 1)
        lay.addWidget(content, 1)
        self.setCentralWidget(root)

        self._spin_angle = 0
        self._spin = QTimer(self)
        self._spin.setInterval(30)
        self._spin.timeout.connect(self._spin_tick)
        self._apply_chrome()

    def _apply_chrome(self):
        """Things that depend on the theme but aren't covered by the stylesheet."""
        self.logo.setPixmap(app_logo(30))
        self.setWindowIcon(QIcon(app_logo(128)))
        self.refresh_btn.setIcon(icons.icon("refresh", "#ffffff", 16))
        self.theme_btn.setText("  " + THEME_LABEL[self.theme_mode])
        self.theme_btn.setIcon(icons.icon(THEME_ICON[self.theme_mode], theme.tokens()["muted"], 16))

    # --------------------------------------------------------- navigation --
    def navigate(self, key):
        if key not in self.pages:
            key = "overview"
        self.current = key
        if key in self.dirty:
            self.dirty.discard(key)
            self.pages[key].render(self.results)
        self.nav[key].setChecked(True)
        self.stack.setCurrentWidget(self.pages[key])
        self.settings.setValue("page", key)
        self._update_header()

    def _update_header(self):
        page = self.pages[self.current]
        self.page_title.setText(dict(AREAS)[self.current])
        self.page_sub.setText(page.subtitle(self.results))

    # ------------------------------------------------------------ refresh --
    def refresh(self, names=None, manual=True):
        """Collect a new snapshot. Manual refreshes show a spinner on the button."""
        if manual:
            self._set_busy(True)
        names = [n for n in (names or COLLECTORS) if n not in self.pending]
        if not names:
            return  # already running; on_result re-arms the timer when done
        self.auto_timer.stop()
        if not self.pending:
            self.round_started = time.monotonic()
        self.generation += 1
        now = time.monotonic()
        for n in names:
            self.pending.add(n)
            self.last_run[n] = now
            self.pool.start(Job(n, COLLECTORS[n], self.signals, self.generation))

    def auto_refresh(self):
        if self.isMinimized():
            return  # resumes from changeEvent when the window is restored
        now = time.monotonic()
        names = [n for n in COLLECTORS
                 if now - self.last_run.get(n, 0) >= SLOW_INTERVALS.get(n, 0)]
        self.refresh(names, manual=False)

    def changeEvent(self, event):
        super().changeEvent(event)
        if (event.type() == QEvent.WindowStateChange and not self.isMinimized()
                and not self.pending and not self.auto_timer.isActive()):
            self.auto_refresh()

    def _render(self, key):
        """Redraw a page now if it's visible, otherwise when it's next opened."""
        if key == self.current:
            self.dirty.discard(key)
            self.pages[key].render(self.results)
        else:
            self.dirty.add(key)

    def read_smart(self):
        if self.smart_running:
            return
        storage = self.results.get("storage")
        if not storage or "__error__" in storage:
            return
        devices = [d["path"] for d in storage["drives"]]
        self.smart_running = True
        self.pages["storage"].render(self.results)

        def job():
            res = read_smart(devices)
            res["time"] = time.time()
            return res

        self.pool.start(Job("smart", job, self.signals, self.generation))

    def on_result(self, name, result, _generation):
        if name == "smart":
            self.smart_running = False
            prev = self.results.get("smart")
            if result.get("error") and prev and not prev.get("error"):
                prev = dict(prev, error=None)  # keep the old data, show nothing new
                result = dict(prev, notice=result["error"])
            self.results["smart"] = result
            self._render("storage")
            self._render("overview")
            self._update_nav()
            return

        self.pending.discard(name)
        self.results[name] = result
        if name in self.pages:
            self._render(name)
        # The overview combines every area: redraw it once per round, except on the
        # very first load where showing results as they arrive feels faster.
        if not self.pending or self.last_refresh is None:
            self._render("overview")
        else:
            self.dirty.add("overview")
        self._update_nav()
        if not self.pending:
            self.last_refresh = datetime.now()
            self._set_busy(False)
            # Keep a steady cadence: count the 5 s from when this round started.
            elapsed_ms = int((time.monotonic() - self.round_started) * 1000)
            self.auto_timer.start(max(500, AUTO_REFRESH_MS - elapsed_ms))
        self._update_header()

    def _update_nav(self):
        for key, btn in self.nav.items():
            if key != "overview":
                btn.set_level(area_level(self.results, key))

    def _set_busy(self, busy):
        """Spinner for manual refreshes; automatic ones only update the timestamp."""
        if busy:
            self.manual_busy = True
            self.refresh_btn.setEnabled(False)
            self.refresh_btn.setText("  Refreshing…")
            self._spin.start()
            return
        if self.manual_busy:
            self.manual_busy = False
            self._spin.stop()
            self.refresh_btn.setEnabled(True)
            self.refresh_btn.setText("  Refresh")
            self.refresh_btn.setIcon(icons.icon("refresh", "#ffffff", 16))
        if self.last_refresh:
            self.updated.setText(f"Updated {self.last_refresh:%H:%M:%S} · "
                                 f"every {AUTO_REFRESH_MS // 1000} s")

    def _spin_tick(self):
        self._spin_angle = (self._spin_angle + 12) % 360
        pm = icons.pixmap("refresh", "#ffffff", 16)
        rotated = pm.transformed(QTransform().rotate(self._spin_angle), Qt.SmoothTransformation)
        # keep size constant: crop the center back to the original
        out = QPixmap(pm.size())
        out.fill(Qt.transparent)
        p = QPainter(out)
        p.drawPixmap((out.width() - rotated.width()) // 2, (out.height() - rotated.height()) // 2, rotated)
        p.end()
        out.setDevicePixelRatio(pm.devicePixelRatio())
        self.refresh_btn.setIcon(QIcon(out))

    # -------------------------------------------------------------- theme --
    def cycle_theme(self):
        i = THEME_MODES.index(self.theme_mode)
        self.theme_mode = THEME_MODES[(i + 1) % len(THEME_MODES)]
        self.settings.setValue("theme", self.theme_mode)
        self.retheme()

    def retheme(self):
        theme.apply(self.app, self.theme_mode)
        self._apply_chrome()
        for key, page in self.pages.items():
            page.render(self.results)
        self.dirty.clear()
        for btn in self.nav.values():
            btn.update()

    def _system_scheme_changed(self, *_):
        if self.theme_mode == "auto":
            self.retheme()


def app_logo(size: int) -> QPixmap:
    """Gradient rounded square with a heartbeat line."""
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
      <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#4f8cff"/><stop offset="1" stop-color="#22c3a6"/></linearGradient></defs>
      <rect x="2" y="2" width="60" height="60" rx="16" fill="url(#g)"/>
      <path d="M12 34h10l5-12 8 22 6-14 3 4h8" fill="none" stroke="#fff" stroke-width="4.5"
        stroke-linecap="round" stroke-linejoin="round"/></svg>"""
    from PySide6.QtCore import QByteArray, QRectF
    from PySide6.QtSvg import QSvgRenderer
    dpr = 2
    pm = QPixmap(size * dpr, size * dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    QSvgRenderer(QByteArray(svg.encode())).render(p, QRectF(0, 0, size * dpr, size * dpr))
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm
