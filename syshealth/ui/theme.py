"""Color tokens, light/dark detection and the application stylesheet."""

from __future__ import annotations

import configparser
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette

DARK = {
    "bg": "#15171c",
    "sidebar": "#1a1d23",
    "surface": "#21252c",
    "surface2": "#2a2f37",
    "hover": "#262a32",
    "border": "#2e333b",
    "text": "#e7e9ec",
    "muted": "#9aa2ad",
    "faint": "#6b7380",
    "accent": "#5b9bff",
    "track": "#2f343d",
    "ok": "#3fb950",
    "info": "#5b9bff",
    "warn": "#e8a33d",
    "crit": "#f26b6b",
    "unknown": "#6b7380",
}

LIGHT = {
    "bg": "#f4f5f7",
    "sidebar": "#ebedf1",
    "surface": "#ffffff",
    "surface2": "#f0f2f5",
    "hover": "#e2e5ea",
    "border": "#dfe2e7",
    "text": "#1b1e23",
    "muted": "#5f6773",
    "faint": "#8a929d",
    "accent": "#2f6fec",
    "track": "#e6e8ec",
    "ok": "#1f8f3a",
    "info": "#2f6fec",
    "warn": "#b9770e",
    "crit": "#d1353b",
    "unknown": "#8a929d",
}

_current = dict(DARK)
_is_dark = True


def tokens() -> dict:
    return _current


def is_dark() -> bool:
    return _is_dark


def color(name: str) -> QColor:
    return QColor(_current.get(name, name))


def level_color(level: str) -> str:
    return _current.get(level, _current["unknown"])


def rgba(hex_color: str, alpha: float) -> str:
    c = QColor(hex_color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"


def system_prefers_dark() -> bool:
    scheme = QGuiApplication.styleHints().colorScheme()
    if scheme == Qt.ColorScheme.Dark:
        return True
    if scheme == Qt.ColorScheme.Light:
        return False
    # Fallback: KDE's color scheme.
    cfg = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        cfg.read(os.path.expanduser("~/.config/kdeglobals"), encoding="utf-8")
        rgb = cfg.get("Colors:Window", "BackgroundNormal", fallback=None)
        if rgb:
            r, g, b = (int(x) for x in rgb.split(",")[:3])
            return (0.299 * r + 0.587 * g + 0.114 * b) < 128
    except (configparser.Error, ValueError, OSError):
        pass
    return False


def apply(app, mode: str = "auto") -> None:
    """mode: 'auto', 'light' or 'dark'."""
    global _current, _is_dark
    _is_dark = system_prefers_dark() if mode == "auto" else mode == "dark"
    _current = dict(DARK if _is_dark else LIGHT)
    t = _current

    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(t["bg"]))
    pal.setColor(QPalette.WindowText, QColor(t["text"]))
    pal.setColor(QPalette.Base, QColor(t["surface"]))
    pal.setColor(QPalette.AlternateBase, QColor(t["surface2"]))
    pal.setColor(QPalette.Text, QColor(t["text"]))
    pal.setColor(QPalette.Button, QColor(t["surface2"]))
    pal.setColor(QPalette.ButtonText, QColor(t["text"]))
    pal.setColor(QPalette.Highlight, QColor(t["accent"]))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.ToolTipBase, QColor(t["surface2"]))
    pal.setColor(QPalette.ToolTipText, QColor(t["text"]))
    pal.setColor(QPalette.PlaceholderText, QColor(t["faint"]))
    pal.setColor(QPalette.Link, QColor(t["accent"]))
    app.setPalette(pal)
    app.setStyleSheet(stylesheet())


def stylesheet() -> str:
    t = _current
    return f"""
    QWidget {{ color: {t['text']}; }}
    QMainWindow, #content, #pageBody {{ background: {t['bg']}; }}
    #sidebar {{ background: {t['sidebar']}; border-right: 1px solid {t['border']}; }}
    #appTitle {{ font-size: 13pt; font-weight: 700; }}
    #appSubtitle {{ color: {t['muted']}; font-size: 8.5pt; }}

    QFrame#card {{
        background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 14px;
    }}
    QFrame#tile {{
        background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 14px;
    }}
    QFrame#tile:hover {{ border-color: {t['accent']}; }}
    QFrame#hero {{
        background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 16px;
    }}
    QFrame#divider {{ background: {t['border']}; max-height: 1px; min-height: 1px; border: none; }}

    QLabel {{ background: transparent; }}
    QLabel#pageTitle {{ font-size: 19pt; font-weight: 700; }}
    QLabel#pageSubtitle {{ color: {t['muted']}; }}
    QLabel#sectionTitle {{ font-size: 11.5pt; font-weight: 650; padding-top: 6px; }}
    QLabel#cardTitle {{ color: {t['muted']}; font-size: 9pt; font-weight: 600; }}
    QLabel#bigValue {{ font-size: 21pt; font-weight: 650; }}
    QLabel#midValue {{ font-size: 13pt; font-weight: 600; }}
    QLabel#heroTitle {{ font-size: 17pt; font-weight: 700; }}
    QLabel#muted {{ color: {t['muted']}; }}
    QLabel#faint {{ color: {t['faint']}; font-size: 8.5pt; }}
    QLabel#kvKey {{ color: {t['muted']}; }}
    QLabel#mono {{ font-family: monospace; color: {t['muted']}; }}

    QPushButton {{
        background: {t['surface2']}; border: 1px solid {t['border']}; border-radius: 9px;
        padding: 7px 14px; font-weight: 600;
    }}
    QPushButton:hover {{ background: {t['hover']}; }}
    QPushButton:pressed {{ background: {t['border']}; }}
    QPushButton:disabled {{ color: {t['faint']}; }}
    QPushButton#primary {{
        background: {t['accent']}; color: #ffffff; border: 1px solid {t['accent']};
    }}
    QPushButton#primary:hover {{ background: {QColor(t['accent']).lighter(110).name()}; }}
    QPushButton#primary:disabled {{ background: {rgba(t['accent'], 0.5)}; color: #ffffff; }}
    QPushButton#danger {{ color: {t['crit']}; }}
    QPushButton#ghost {{ background: transparent; border: none; color: {t['muted']}; padding: 6px 10px; }}
    QPushButton#ghost:hover {{ background: {t['hover']}; color: {t['text']}; }}

    QScrollArea {{ border: none; background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {t['border']}; border-radius: 4px; min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background: {t['faint']}; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
    QScrollBar::handle:horizontal {{ background: {t['border']}; border-radius: 4px; min-width: 30px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    QLineEdit {{
        background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 9px;
        padding: 7px 11px; selection-background-color: {t['accent']};
    }}
    QLineEdit:focus {{ border-color: {t['accent']}; }}

    QTableWidget {{
        background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 14px;
        gridline-color: transparent; padding: 4px;
        selection-background-color: {rgba(t['accent'], 0.22)}; selection-color: {t['text']};
        alternate-background-color: {t['surface2']};
    }}
    QTableWidget::item {{ padding: 4px 8px; border: none; }}
    QHeaderView {{ background: transparent; }}
    QHeaderView::section {{
        background: {t['surface']}; color: {t['muted']}; border: none;
        border-bottom: 1px solid {t['border']}; padding: 8px; font-weight: 600;
    }}
    QTableCornerButton::section {{ background: {t['surface']}; border: none; }}

    QToolTip {{
        background: {t['surface2']}; color: {t['text']}; border: 1px solid {t['border']};
        padding: 6px; border-radius: 6px;
    }}
    QMessageBox {{ background: {t['surface']}; }}
    """
