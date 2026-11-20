# PyInstaller spec for System Health.  Build with:  pyinstaller packaging/system-health.spec
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

# Qt's GTK3 platform-theme plugin drags in GTK, Pango, Cairo, etc. We draw our own
# theme, so drop the plugin and the libraries only it needs.
DROP_PREFIXES = (
    "libqgtk3", "libgtk-3", "libgdk-3", "libgdk_pixbuf", "libglycin", "libatk-1.0",
    "libatk-bridge", "libatspi", "libcairo", "libpango", "libpixman", "libepoxy",
    "libcloudproviders", "libtinysparql", "libjson-glib", "libthai", "libdatrie",
    "libfribidi", "liblcms2", "libseccomp", "libXcomposite", "libXdamage", "libXi.",
    "libXinerama", "libXrandr", "libXcursor",
    # Qt modules we don't use
    "libQt6Network", "libQt6OpenGL", "libQt6EglFS", "libqeglfs", "libqlinuxfb",
    "libqvnc", "libqvkkhrdisplay", "libqminimalegl", "libqoffscreen",
)

a = Analysis(
    [os.path.join(ROOT, "packaging", "launcher.py")],
    pathex=[ROOT],
    excludes=["tkinter", "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick",
              "PySide6.QtOpenGL", "PySide6.QtPdf", "unittest", "pydoc", "sqlite3"],
    noarchive=False,
)
a.binaries = [b for b in a.binaries if not os.path.basename(b[0]).startswith(DROP_PREFIXES)]
a.datas = [d for d in a.datas if "/translations/" not in d[0] or "qtbase_en" in d[0]]

pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="system-health",
          console=False, strip=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="system-health")
