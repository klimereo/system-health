"""Entry point: `python -m syshealth` (or the AppImage)."""

from __future__ import annotations

import os
import sys

from . import APP_ID, APP_NAME, __version__

DESKTOP_ENTRY = """[Desktop Entry]
Type=Application
Name=System Health
GenericName=System Health Monitor
Comment=See the health of your computer at a glance
Exec="{exec}" %U
Icon={icon}
Terminal=false
Categories=System;Monitor;
Keywords=health;cpu;memory;disk;battery;temperature;smart;
StartupWMClass={app_id}
"""


def install_desktop_entry() -> int:
    """Add this AppImage to the application launcher."""
    target = os.environ.get("APPIMAGE")
    if not target:
        print("--install-desktop only works when running the .AppImage file.", file=sys.stderr)
        return 1
    data = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    apps = os.path.join(data, "applications")
    icon_dir = os.path.join(data, "icons", "hicolor", "scalable", "apps")
    os.makedirs(apps, exist_ok=True)
    os.makedirs(icon_dir, exist_ok=True)
    appdir = os.environ.get("APPDIR", "")
    src_icon = os.path.join(appdir, f"{APP_ID}.svg")
    icon_path = os.path.join(icon_dir, f"{APP_ID}.svg")
    if os.path.exists(src_icon):
        with open(src_icon, "rb") as src, open(icon_path, "wb") as dst:
            dst.write(src.read())
    desktop = os.path.join(apps, f"{APP_ID}.desktop")
    with open(desktop, "w", encoding="utf-8") as fh:
        fh.write(DESKTOP_ENTRY.format(exec=target, icon=APP_ID, app_id=APP_ID))
    print(f"Installed launcher entry: {desktop}")
    print("If you move the AppImage, run this again.")
    return 0


def _desktop_entry_installed() -> bool:
    data_home = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    data_dirs = os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":")
    return any(os.path.isfile(os.path.join(d, "applications", f"{APP_ID}.desktop"))
               for d in [data_home, *data_dirs] if d)


def text_report() -> int:
    """Print a plain-text snapshot (no GUI). Exit code 1 if anything is critical."""
    from concurrent.futures import ThreadPoolExecutor

    from .collectors import COLLECTORS
    from .util import CRIT, overall

    marks = {"ok": "✔", "info": "ℹ", "warn": "!", "crit": "✖", "unknown": "?"}
    with ThreadPoolExecutor(len(COLLECTORS)) as pool:
        futures = {name: pool.submit(fn) for name, fn in COLLECTORS.items()}
    worst_level = "ok"
    for name, fut in futures.items():
        try:
            data = fut.result()
        except Exception as exc:  # noqa: BLE001
            print(f"? {name:10s} error: {exc}")
            continue
        level = overall(data["findings"])
        if level == CRIT:
            worst_level = CRIT
        print(f"{marks[level]} {name:10s} {data['summary']}")
        for f in data["findings"]:
            print(f"      {marks[f.level]} {f.title}")
    return 1 if worst_level == CRIT else 0


def main() -> int:
    if "--version" in sys.argv:
        print(f"{APP_NAME} {__version__}")
        return 0
    if "--install-desktop" in sys.argv:
        return install_desktop_entry()
    if "--check" in sys.argv:
        return text_report()

    from PySide6.QtWidgets import QApplication

    from .ui.window import MainWindow

    QApplication.setApplicationName(APP_ID)
    QApplication.setApplicationDisplayName(APP_NAME)
    QApplication.setApplicationVersion(__version__)
    # Link the window to its launcher entry (taskbar icon) only when one is installed;
    # otherwise the desktop portal logs "App info not found" on every start.
    if _desktop_entry_installed():
        QApplication.setDesktopFileName(APP_ID)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow(app)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
