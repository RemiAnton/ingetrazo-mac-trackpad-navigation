# MAC Trackpad Navigation for IngeTrazo

An official community extension for **[IngeTrazo](https://ingetrazo.com)** that brings seamless Blender-style trackpad navigation to macOS users.

## Features

- **✌️ Two-finger drag:** Smoothly Orbit the 3D view around the model/pivot point.
- **⇧ + ✌️ Shift + Two-finger drag:** Pan the camera across the scene (1:1 motion following your fingers).
- **⌃ + ✌️ Control + Two-finger drag (or ⌘ Cmd):** Smooth continuous zoom in / out focused at the 3D cursor position.
- **🤏 Pinch-to-zoom:** Native macOS two-finger pinch gesture for intuitive zooming.
- **Two-finger double-tap:** Smart zoom extents to instantly frame the model.
- **Configurable Preferences:** Customize Orbit, Pan, and Zoom sensitivities, toggle axis inversions, and enable/disable features via `Extensions ▸ MAC Trackpad Navigation…` (`Ctrl+Alt+T`).

## Manual Installation

**Preferred (single file):**

1. Open IngeTrazo → **Extensions ▸ Open extensions folder** (on macOS this is usually `~/.local/share/ingetrazo/plugins/`).
2. Copy **only** `mac_trackpad_navigation.py` into that folder.
3. Restart IngeTrazo. Configure via **Extensions ▸ MAC Trackpad Navigation…** (`Ctrl+Alt+T`).

**Whole-folder install** (clone or GitHub zip): copy the repository folder into the extensions folder. It must contain `__init__.py` at the top level — without that, IngeTrazo shows a disabled `⚠ … (load error)` entry. Do not leave an extra nested wrapper folder around the package.

## License

This project is licensed under the [MIT License](LICENSE).
