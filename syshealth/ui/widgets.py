"""Reusable building blocks: cards, meters, rings, pills, grids, nav buttons."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QAbstractButton, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QSizePolicy, QVBoxLayout, QWidget)

from . import icons, theme
from ..util import CRIT, OK, UNKNOWN, WARN, level_for

LEVEL_TEXT = {"ok": "Healthy", "info": "Note", "warn": "Attention", "crit": "Critical",
              "unknown": "Unknown"}


def label(text="", obj: str | None = None, wrap=False, select=False) -> QLabel:
    lbl = QLabel(str(text))
    if obj:
        lbl.setObjectName(obj)
    lbl.setWordWrap(wrap)
    if select:
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return lbl


def section(text: str) -> QLabel:
    return label(text, "sectionTitle")


def hbox(*widgets, spacing=8, margins=(0, 0, 0, 0)) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for w in widgets:
        if w is None:
            lay.addStretch(1)
        elif isinstance(w, int):
            lay.addSpacing(w)
        elif isinstance(w, QWidget):
            lay.addWidget(w)
        else:
            lay.addLayout(w)
    return lay


def vbox(*widgets, spacing=6, margins=(0, 0, 0, 0)) -> QVBoxLayout:
    lay = QVBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for w in widgets:
        if w is None:
            lay.addStretch(1)
        elif isinstance(w, QWidget):
            lay.addWidget(w)
        else:
            lay.addLayout(w)
    return lay


def divider() -> QFrame:
    line = QFrame()
    line.setObjectName("divider")
    return line


class Card(QFrame):
    """Rounded surface with an optional title row."""

    def __init__(self, title: str | None = None, right: QWidget | None = None,
                 obj: str = "card", margins=(18, 16, 18, 16), spacing=10):
        super().__init__()
        self.setObjectName(obj)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(*margins)
        self.body.setSpacing(spacing)
        if title or right:
            row = QHBoxLayout()
            row.setSpacing(8)
            if title:
                row.addWidget(label(title, "cardTitle"))
            row.addStretch(1)
            if right:
                row.addWidget(right)
            self.body.addLayout(row)

    def add(self, item):
        if isinstance(item, QWidget):
            self.body.addWidget(item)
        else:
            self.body.addLayout(item)
        return item


class ClickableCard(Card):
    clicked = Signal()

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("obj", "tile")
        super().__init__(*args, **kwargs)
        self.setCursor(Qt.PointingHandCursor)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class Pill(QLabel):
    def __init__(self, text: str, level: str = "info"):
        super().__init__(text)
        c = theme.level_color(level)
        self.setStyleSheet(
            f"background: {theme.rgba(c, 0.16)}; color: {c}; border-radius: 8px;"
            "padding: 2px 9px; font-weight: 600; font-size: 8.5pt;")
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)


def status_pill(level: str, text: str | None = None) -> Pill:
    return Pill(text or LEVEL_TEXT.get(level, level), level)


class StatusIcon(QLabel):
    def __init__(self, level: str, size: int = 20):
        super().__init__()
        self.setPixmap(icons.pixmap(level, theme.level_color(level), size))
        self.setFixedSize(size, size)


class Dot(QWidget):
    def __init__(self, level: str, size: int = 9):
        super().__init__()
        self.level = level
        self.setFixedSize(size, size)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.level_color(self.level)))
        p.drawEllipse(self.rect().adjusted(0, 0, -1, -1))


class Meter(QWidget):
    """Thin rounded progress bar colored by status level."""

    def __init__(self, percent, level: str = OK, height: int = 8):
        super().__init__()
        self.percent = max(0.0, min(100.0, float(percent or 0)))
        self.level = level
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        radius = r.height() / 2
        p.setPen(Qt.NoPen)
        p.setBrush(theme.color("track"))
        p.drawRoundedRect(r, radius, radius)
        if self.percent > 0:
            w = max(r.height(), r.width() * self.percent / 100)
            p.setBrush(QColor(theme.level_color(self.level)))
            p.drawRoundedRect(QRectF(r.x(), r.y(), w, r.height()), radius, radius)


class Ring(QWidget):
    """Circular gauge with text in the middle."""

    def __init__(self, percent, level: str, center: str, sub: str = "", size: int = 136,
                 thickness: int = 12):
        super().__init__()
        self.percent = None if percent is None else max(0.0, min(100.0, float(percent)))
        self.level, self.center, self.sub, self.thickness = level, center, sub, thickness
        self.setFixedSize(size, size)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = self.thickness
        r = QRectF(self.rect()).adjusted(t / 2 + 1, t / 2 + 1, -t / 2 - 1, -t / 2 - 1)
        pen = QPen(theme.color("track"), t)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(r, 0, 360 * 16)
        if self.percent:
            pen.setColor(QColor(theme.level_color(self.level)))
            p.setPen(pen)
            p.drawArc(r, 90 * 16, int(-self.percent / 100 * 360 * 16))
        p.setPen(theme.color("text"))
        f = QFont(self.font())
        f.setPointSizeF(self.width() / 7.2)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        text_rect = QRectF(self.rect())
        if self.sub:
            text_rect.adjust(0, -self.height() * 0.08, 0, -self.height() * 0.08)
        p.drawText(text_rect, Qt.AlignCenter, self.center)
        if self.sub:
            f2 = QFont(self.font())
            f2.setPointSizeF(max(7.5, self.width() / 16))
            p.setFont(f2)
            p.setPen(theme.color("muted"))
            p.drawText(QRectF(self.rect()).adjusted(0, self.height() * 0.28, 0, 0),
                       Qt.AlignCenter, self.sub)


class MeterRow(QWidget):
    """Label + value on one line, meter below, optional caption."""

    def __init__(self, title: str, value: str, percent, level: str = OK,
                 caption: str | None = None, right_pill: QWidget | None = None):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        top = QHBoxLayout()
        top.setSpacing(8)
        name = label(title)
        name.setStyleSheet("font-weight: 600;")
        top.addWidget(name)
        if right_pill:
            top.addWidget(right_pill)
        top.addStretch(1)
        top.addWidget(label(value, "muted"))
        lay.addLayout(top)
        lay.addWidget(Meter(percent, level))
        if caption:
            lay.addWidget(label(caption, "faint", wrap=True))


class Stat(QWidget):
    """Small caption over a big value, with an optional sub-line."""

    def __init__(self, title: str, value: str, sub: str | None = None,
                 level: str | None = None, big: bool = True):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        lay.addWidget(label(title, "cardTitle"))
        val = label(value, "bigValue" if big else "midValue", select=True)
        if level and level not in (OK, UNKNOWN):
            val.setStyleSheet(f"color: {theme.level_color(level)};")
        lay.addWidget(val)
        if sub:
            lay.addWidget(label(sub, "muted", wrap=True))
        lay.addStretch(1)


def stat_card(title, value, sub=None, level=None) -> Card:
    card = Card()
    card.add(Stat(title, value, sub, level))
    return card


def kv_grid(rows, key_width: int = 150) -> QWidget:
    """rows: iterable of (key, value) or (key, value, level). None values are skipped."""
    w = QWidget()
    grid = QGridLayout(w)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(16)
    grid.setVerticalSpacing(9)
    grid.setColumnMinimumWidth(0, key_width)
    grid.setColumnStretch(1, 1)
    r = 0
    for row in rows:
        key, value = row[0], row[1]
        if value is None or value == "":
            continue
        level = row[2] if len(row) > 2 else None
        k = label(key, "kvKey")
        k.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        v = label(value, wrap=True, select=True)
        if level and level not in (OK, UNKNOWN):
            v.setStyleSheet(f"color: {theme.level_color(level)}; font-weight: 600;")
        grid.addWidget(k, r, 0, Qt.AlignTop)
        grid.addWidget(v, r, 1, Qt.AlignTop)
        r += 1
    grid.setRowStretch(r, 1)
    return w


class ResponsiveGrid(QWidget):
    """Lays out child widgets in as many equal columns as fit."""

    def __init__(self, min_col: int = 250, max_cols: int = 4, spacing: int = 14):
        super().__init__()
        self.min_col, self.max_cols, self.spacing = min_col, max_cols, spacing
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(spacing)
        self.items: list[QWidget] = []
        self.cols = 0

    def add(self, widget: QWidget) -> QWidget:
        self.items.append(widget)
        self._relayout(force=True)
        return widget

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self, force: bool = False):
        width = self.width() if self.width() > 50 else self.min_col * 2
        cols = max(1, min(self.max_cols, len(self.items) or 1,
                          (width + self.spacing) // (self.min_col + self.spacing)))
        if cols == self.cols and not force:
            return
        self.cols = cols
        for w in self.items:
            self.grid.removeWidget(w)
        for i, w in enumerate(self.items):
            self.grid.addWidget(w, i // cols, i % cols)
        for c in range(self.max_cols):
            self.grid.setColumnStretch(c, 1 if c < cols else 0)


class FindingRow(QWidget):
    def __init__(self, finding, show_detail: bool = True):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(12)
        ico = StatusIcon(finding.level, 20)
        lay.addWidget(ico, 0, Qt.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(2)
        title = label(finding.title, wrap=True)
        title.setStyleSheet("font-weight: 600;")
        text.addWidget(title)
        if show_detail and finding.detail:
            text.addWidget(label(finding.detail, "muted", wrap=True))
        lay.addLayout(text, 1)


def empty_state(text: str, sub: str | None = None) -> QWidget:
    card = Card(margins=(24, 28, 24, 28))
    t = label(text, "midValue", wrap=True)
    t.setAlignment(Qt.AlignCenter)
    card.add(t)
    if sub:
        s = label(sub, "muted", wrap=True)
        s.setAlignment(Qt.AlignCenter)
        card.add(s)
    return card


def temp_level(value, warn=80, crit=95):
    return level_for(value, warn, crit)


def pct_level(value, warn=80, crit=90):
    return level_for(value, warn, crit)


class NavButton(QAbstractButton):
    """Sidebar entry: icon, text and a small status dot."""

    def __init__(self, key: str, text: str):
        super().__init__()
        self.key = key
        self.setText(text)
        self.level = None
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(38)
        self._hover = False

    def set_level(self, level):
        self.level = level
        self.update()

    def sizeHint(self):
        return QSize(200, 38)

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(8, 1, -8, -1)
        if self.isChecked() or self._hover:
            p.setPen(Qt.NoPen)
            p.setBrush(theme.color("surface2" if self.isChecked() else "hover"))
            p.drawRoundedRect(r, 9, 9)
        if self.isChecked():
            p.setBrush(theme.color("accent"))
            p.drawRoundedRect(QRectF(r.x(), r.y() + 10, 3, r.height() - 20), 1.5, 1.5)
        fg = theme.tokens()["text"] if self.isChecked() else theme.tokens()["muted"]
        icons.render(p, self.key, fg, QRectF(r.x() + 12, r.center().y() - 9, 18, 18))
        p.setPen(QColor(fg))
        f = QFont(self.font())
        if self.isChecked():
            f.setWeight(QFont.DemiBold)
        p.setFont(f)
        p.drawText(QRectF(r.x() + 42, r.y(), r.width() - 70, r.height()),
                   Qt.AlignVCenter | Qt.AlignLeft, self.text())
        if self.level and self.level in (WARN, CRIT, "info"):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.level_color(self.level)))
            p.drawEllipse(QRectF(r.right() - 20, r.center().y() - 4, 8, 8))
