# Third-party notices

The **source code in this repository** is MIT-licensed (see [LICENSE](LICENSE)).

The **AppImage** additionally bundles the third-party components below. Each keeps its own
license; copies of the license texts are in [`LICENSES/`](LICENSES) and inside the AppImage at
`usr/share/doc/system-health/`.

| Component | License | Source |
|---|---|---|
| Qt 6 (Core, Gui, Widgets, Svg, DBus, Wayland/XCB plugins) | LGPL-3.0 | https://code.qt.io/ |
| PySide6 / Shiboken6 (Qt for Python) | LGPL-3.0 | https://code.qt.io/cgit/pyside/pyside-setup.git/ |
| psutil | BSD-3-Clause | https://github.com/giampaolo/psutil |
| CPython runtime | PSF License | https://www.python.org/ |
| Shared libraries from the build system (glib, dbus, fontconfig, freetype, libxcb, …) | Their respective open-source licenses (LGPL/MIT/etc.) | Fedora 43 source packages |
| Interface icons, drawn in the style of Lucide | ISC | https://lucide.dev |

## LGPL note (Qt / PySide6)

Qt and PySide6 are used unmodified, as shared libraries. You may replace them with your own
build: extract the AppImage (`./System_Health-*.AppImage --appimage-extract`), swap the
libraries in `squashfs-root/usr/lib/system-health/_internal/PySide6/`, and run
`squashfs-root/AppRun`. The application source (this repository) and the
[build script](build-appimage.sh) needed to re-create the AppImage are provided here.
