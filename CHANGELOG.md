# Changelog

## 1.1.2
- Battery: no more absurd "time left" (e.g. "46 days") when plugged in and held at a charge
  limit; that state now shows as "Not charging" / "Plugged in".
- No more "App info not found" portal warning at startup when the app isn't installed in the launcher.

## 1.1.1
- Removed widgets are hidden immediately, so pages never show stale "ghost" cards while redrawing.
- License files are bundled inside the AppImage; the build writes a SHA-256 checksum.

## 1.1.0
- Automatic refresh every 5 seconds while the window is open (paused while minimized).
- System checks (updates, services, journal) re-run every 5 minutes, or on manual refresh.
- Only the visible page is redrawn; the process list keeps selection, scroll and sort.

## 1.0.0
- First release: Overview, CPU, Memory, Storage (with SMART), Battery, Thermals, Graphics,
  Network, Processes and System pages; light/dark theme; `--check` text report;
  `--install-desktop` launcher integration.
