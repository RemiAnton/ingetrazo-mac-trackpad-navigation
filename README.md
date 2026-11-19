# MAC Trackpad Navigation for IngeTrazo

An official community extension for **[IngeTrazo](https://ingetrazo.com)** that brings native, Apple-grade fluid trackpad navigation to macOS users.

## Features

- **✌️ Fluid Multi-Touch Navigation:**
  - **Blender Preset (Default):** 2-Finger Drag = Orbit, ⇧ Shift + Drag = Pan, ⌃ Ctrl / ⌘ Cmd + Drag = Zoom.
  - **SketchUp Preset:** 2-Finger Drag = Pan, ⇧ Shift or ⌥ Option + Drag = Orbit, ⌃ / ⌘ + Drag = Zoom.
  - **CAD Standard Preset:** 2-Finger Drag = Pan, ⌘ Cmd + Drag = Orbit, ⇧ Shift = Zoom.
- **🌊 Momentum Coasting & Tap-to-Halt:** Natural physics-based deceleration when lifting fingers, with instantaneous interruption on touch-down (Apple WWDC fluid motion principle).
- **🎯 3D Orbit Focus Reticle:** Real-time high-DPI QPainter viewport overlay in IngeTrazo Blue (`rgb(77, 140, 242)`) indicating the active 3D camera pivot point, fading out smoothly upon release.
- **🤏 Calibrated Pinch-to-Zoom:** Native macOS pinch gesture with independent sensitivity tuning and optional natural zoom inversion.
- **🔄 Two-Finger Rotate Gesture:** Two-finger twist for intuitive azimuth turntable rotation and view-plane orientation.
- **⚡ Context-Aware Smart Double-Tap:** Double-tap zooms to selected geometry or cluster; falls back to full Zoom Extents on empty canvas.
- **🎛️ Modern Preferences Dialog (`Ctrl+Alt+T`):**
  - Instant preset switching (Blender, SketchUp, CAD Standard).
  - Dual synchronized Sliders + SpinBoxes for fine-grained sensitivity control.
  - Axis and zoom direction inversions.
  - One-click "Reset to Defaults" button.
  - Full multi-language support (English, Español, Português).
  - Automatic persistence across sessions using `QSettings`.

## Installation

1. Open IngeTrazo.
2. Go to **Extensions ▸ Open extensions folder** (or navigate to `~/.local/share/ingetrazo/plugins/`).
3. Place `mac_trackpad_navigation.py` into that directory.
4. Restart IngeTrazo. The extension will automatically load and appear under the **Extensions** menu (`Ctrl+Alt+T`).

## License

This project is licensed under the [MIT License](LICENSE).
