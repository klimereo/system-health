#!/usr/bin/env bash
# Build dist/System_Health-<version>-x86_64.AppImage
#
#   ./build-appimage.sh
#
# Needs: python3 (with venv), internet access the first time (pip + appimagetool),
# and on every build (appimagetool fetches the AppImage runtime).
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

ARCH="$(uname -m)"
APPIMAGETOOL_VERSION="1.9.1"
VERSION="$(python3 -c 'import re;print(re.search(r"__version__ = \"(.+?)\"", open("syshealth/__init__.py").read()).group(1))')"
VENV=".venv"
BUILD="build"
APPDIR="$BUILD/AppDir"
OUT="dist/System_Health-${VERSION}-${ARCH}.AppImage"

echo "==> Python environment"
if [ ! -x "$VENV/bin/python" ]; then
    python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r requirements.txt pyinstaller

echo "==> Freezing with PyInstaller"
rm -rf "$BUILD/pyinstaller" "$APPDIR"
"$VENV/bin/pyinstaller" --noconfirm --clean --log-level WARN \
    --distpath "$BUILD/pyinstaller/dist" \
    --workpath "$BUILD/pyinstaller/work" \
    packaging/system-health.spec

echo "==> Assembling AppDir"
mkdir -p "$APPDIR/usr/lib" "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/scalable/apps"
cp -a "$BUILD/pyinstaller/dist/system-health" "$APPDIR/usr/lib/system-health"
install -m 755 packaging/AppRun "$APPDIR/AppRun"
install -m 644 packaging/system-health.desktop "$APPDIR/system-health.desktop"
install -m 644 packaging/system-health.desktop "$APPDIR/usr/share/applications/"
install -m 644 packaging/system-health.svg "$APPDIR/system-health.svg"
install -m 644 packaging/system-health.svg "$APPDIR/usr/share/icons/hicolor/scalable/apps/"
mkdir -p "$APPDIR/usr/share/doc/system-health"
install -m 644 LICENSE THIRD_PARTY_NOTICES.md LICENSES/*.txt "$APPDIR/usr/share/doc/system-health/"
QT_QPA_PLATFORM=offscreen "$VENV/bin/python" - "$APPDIR/.DirIcon" <<'PY'
import sys
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import Qt
app = QGuiApplication([])
img = QImage(256, 256, QImage.Format_ARGB32)
img.fill(Qt.transparent)
p = QPainter(img)
QSvgRenderer("packaging/system-health.svg").render(p)
p.end()
img.save(sys.argv[1], "PNG")
PY

echo "==> Getting appimagetool"
TOOL="$(command -v appimagetool || true)"
if [ -z "$TOOL" ]; then
    TOOL="$BUILD/tools/appimagetool-${APPIMAGETOOL_VERSION}-${ARCH}.AppImage"
    if [ ! -x "$TOOL" ]; then
        mkdir -p "$BUILD/tools"
        curl -fL --retry 3 -o "$TOOL.part" \
            "https://github.com/AppImage/appimagetool/releases/download/${APPIMAGETOOL_VERSION}/appimagetool-${ARCH}.AppImage"
        mv "$TOOL.part" "$TOOL"
        chmod +x "$TOOL"
    fi
fi

echo "==> Building AppImage"
mkdir -p dist
rm -f "$OUT"
# APPIMAGE_EXTRACT_AND_RUN lets appimagetool run even without FUSE.
ARCH="$ARCH" APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" --no-appstream "$APPDIR" "$OUT"
chmod +x "$OUT"
(cd dist && sha256sum "$(basename "$OUT")" > "$(basename "$OUT").sha256")
echo
echo "Done: $OUT ($(du -h "$OUT" | cut -f1))"
