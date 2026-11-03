# SPDX-License-Identifier: MIT
# Copyright (c) 2026 IngeTrazo contributors
"""MAC Trackpad Navigation for IngeTrazo on macOS.

Simplifies MacBook trackpad navigation to match Blender's gestures:
- Two-finger drag: Orbit view around model/target
- Shift + Two-finger drag: Pan camera across the scene
- Control + Two-finger drag (or Cmd): Zoom in / out at cursor
- Two-finger pinch: Native pinch-to-zoom at cursor
- Two-finger double-tap: Smart zoom extents
"""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QNativeGestureEvent, QPointingDevice, QVector3D, QWheelEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)
from tools.base import Tool

# Global config dictionary
CONFIG = {
    "enabled": True,
    "orbit_speed": 1.0,
    "pan_speed": 1.0,
    "zoom_speed": 0.025,
    "invert_orbit_x": False,
    "invert_orbit_y": False,
    "pinch_zoom": True,
}

_dialog_instance = None


class MacTrackpadFilter(QObject):
    """Event filter attached to Viewport to handle Blender-style trackpad gestures."""

    def __init__(self, viewport):
        super().__init__(viewport)
        self.viewport = viewport
        self.last_event_time = 0.0
        self.orbit_pivot = None

    def eventFilter(self, watched, event):
        if not CONFIG["enabled"]:
            return False

        etype = event.type()
        try:
            if etype == QEvent.Type.Wheel:
                return self._handle_wheel(event)
            elif etype == QEvent.Type.NativeGesture:
                return self._handle_gesture(event)
        except Exception:
            # Safe isolation: an extension should never crash or freeze IngeTrazo
            return False

        return False

    def _is_touchpad(self, event) -> bool:
        if hasattr(event, "pointingDevice"):
            dev = event.pointingDevice()
            if dev is not None and dev.type() == QPointingDevice.DeviceType.TouchPad:
                return True
        if hasattr(event, "hasPixelDelta") and event.hasPixelDelta() and not event.pixelDelta().isNull():
            return True
        return False

    def _handle_wheel(self, event: QWheelEvent) -> bool:
        touchpad = self._is_touchpad(event)

        # Extract delta values (high precision pixel delta on macOS trackpad)
        if hasattr(event, "hasPixelDelta") and event.hasPixelDelta() and not event.pixelDelta().isNull():
            dx = float(event.pixelDelta().x())
            dy = float(event.pixelDelta().y())
        else:
            adelta = event.angleDelta()
            dx = float(adelta.x()) / 8.0
            dy = float(adelta.y()) / 8.0

        if abs(dx) < 1e-4 and abs(dy) < 1e-4:
            return False

        mods = event.modifiers()
        is_shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        is_ctrl = bool(mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier))

        # If it is a traditional mouse wheel without modifier keys, fall back to default zoom
        if not touchpad and not is_shift and not is_ctrl:
            return False

        pos = event.position()
        vh = max(self.viewport.height(), 1)

        # -------------------------------------------------------------
        # 1. SHIFT + Two-finger drag -> PAN
        # -------------------------------------------------------------
        if is_shift:
            depth = None
            if hasattr(self.viewport, "_world_under_cursor") and hasattr(self.viewport, "_depth_of"):
                try:
                    focus = self.viewport._world_under_cursor(pos.x(), pos.y())
                    depth = self.viewport._depth_of(focus)
                except Exception:
                    depth = None

            self.viewport.camera.pan(
                dx * CONFIG["pan_speed"],
                dy * CONFIG["pan_speed"],
                vh,
                depth,
            )
            self.viewport.update()
            event.accept()
            return True

        # -------------------------------------------------------------
        # 2. CONTROL (or Command) + Two-finger drag -> ZOOM IN / OUT
        # -------------------------------------------------------------
        elif is_ctrl:
            steps = dy * CONFIG["zoom_speed"]
            focus = None
            if hasattr(self.viewport, "_world_under_cursor"):
                try:
                    focus = self.viewport._world_under_cursor(pos.x(), pos.y())
                except Exception:
                    focus = None

            if focus is not None:
                self.viewport.camera.zoom_to(steps, focus)
            else:
                self.viewport.camera.zoom(steps)

            self.viewport.update()
            event.accept()
            return True

        # -------------------------------------------------------------
        # 3. Plain Two-finger drag -> ORBIT
        # -------------------------------------------------------------
        else:
            now = time.monotonic()
            phase = getattr(event, "phase", lambda: Qt.ScrollPhase.NoScrollPhase)()

            if phase == Qt.ScrollPhase.ScrollBegin or (now - self.last_event_time) > 0.25:
                if hasattr(self.viewport, "_orbit_pivot_at"):
                    try:
                        self.orbit_pivot = self.viewport._orbit_pivot_at(pos.x(), pos.y())
                    except Exception:
                        self.orbit_pivot = None
                else:
                    self.orbit_pivot = None
            elif phase == Qt.ScrollPhase.ScrollEnd:
                self.orbit_pivot = None

            self.last_event_time = now

            odx = -dx if CONFIG["invert_orbit_x"] else dx
            base_inv_y = getattr(self.viewport, "_invert_orbit_y", False)
            invert_y = CONFIG["invert_orbit_y"] ^ base_inv_y
            ody = -dy if invert_y else dy

            odx_scaled = odx * CONFIG["orbit_speed"]
            ody_scaled = ody * CONFIG["orbit_speed"]

            if self.orbit_pivot is not None:
                self.viewport.camera.orbit_about(self.orbit_pivot, odx_scaled, ody_scaled, vh)
            else:
                self.viewport.camera.orbit(odx_scaled, ody_scaled, vh)

            self.viewport.update()
            event.accept()
            return True

    def _handle_gesture(self, event: QNativeGestureEvent) -> bool:
        if not CONFIG["pinch_zoom"]:
            return False

        gtype = getattr(event, "gestureType", lambda: None)()
        if gtype == Qt.NativeGestureType.ZoomNativeGesture:
            val = float(getattr(event, "value", lambda: 0.0)())
            steps = val * 4.0
            pos = event.position()
            focus = None
            if hasattr(self.viewport, "_world_under_cursor"):
                try:
                    focus = self.viewport._world_under_cursor(pos.x(), pos.y())
                except Exception:
                    focus = None

            if focus is not None:
                self.viewport.camera.zoom_to(steps, focus)
            else:
                self.viewport.camera.zoom(steps)

            self.viewport.update()
            event.accept()
            return True

        elif gtype == Qt.NativeGestureType.SmartZoomNativeGesture:
            act = getattr(self.viewport, "_act_zoom_extents", None)
            if act is not None:
                act.trigger()
                event.accept()
                return True

        return False


# -----------------------------------------------------------------------------
# Preferences Dialog
# -----------------------------------------------------------------------------

def show_preferences_dialog(parent_window=None) -> QDialog:
    global _dialog_instance
    if _dialog_instance is not None:
        _dialog_instance.show()
        _dialog_instance.raise_()
        _dialog_instance.activateWindow()
        return _dialog_instance

    dlg = QDialog(parent_window)
    dlg.setWindowTitle("MAC Trackpad Navigation")
    dlg.setMinimumWidth(380)

    lay = QVBoxLayout(dlg)
    lay.setSpacing(12)

    # Info banner / Quick reference
    info_box = QGroupBox("Gestures Quick Reference", dlg)
    info_lay = QVBoxLayout(info_box)
    info_text = (
        "<b>• 2-finger drag:</b> Orbit view around model<br>"
        "<b>• Shift + 2-finger drag:</b> Pan view<br>"
        "<b>• Control + 2-finger drag:</b> Zoom in / out at cursor<br>"
        "<b>• 2-finger pinch:</b> Native pinch-to-zoom<br>"
        "<b>• 2-finger double-tap:</b> Zoom extents"
    )
    lbl = QLabel(info_text, info_box)
    lbl.setTextFormat(Qt.TextFormat.RichText)
    lbl.setStyleSheet("color: #333; line-height: 140%;")
    info_lay.addWidget(lbl)
    lay.addWidget(info_box)

    # Form settings
    form = QFormLayout()
    form.setSpacing(10)

    chk_enabled = QCheckBox("Enable Trackpad Navigation", dlg)
    chk_enabled.setChecked(CONFIG["enabled"])
    form.addRow("", chk_enabled)

    spn_orbit = QDoubleSpinBox(dlg)
    spn_orbit.setRange(0.1, 5.0)
    spn_orbit.setSingleStep(0.1)
    spn_orbit.setValue(CONFIG["orbit_speed"])
    form.addRow("Orbit Sensitivity:", spn_orbit)

    spn_pan = QDoubleSpinBox(dlg)
    spn_pan.setRange(0.1, 5.0)
    spn_pan.setSingleStep(0.1)
    spn_pan.setValue(CONFIG["pan_speed"])
    form.addRow("Pan Sensitivity:", spn_pan)

    spn_zoom = QDoubleSpinBox(dlg)
    spn_zoom.setRange(0.005, 0.1)
    spn_zoom.setSingleStep(0.005)
    spn_zoom.setDecimals(3)
    spn_zoom.setValue(CONFIG["zoom_speed"])
    form.addRow("Zoom Sensitivity:", spn_zoom)

    chk_inv_x = QCheckBox("Invert Orbit Horizontal (X)", dlg)
    chk_inv_x.setChecked(CONFIG["invert_orbit_x"])
    form.addRow("", chk_inv_x)

    chk_inv_y = QCheckBox("Invert Orbit Vertical (Y)", dlg)
    chk_inv_y.setChecked(CONFIG["invert_orbit_y"])
    form.addRow("", chk_inv_y)

    chk_pinch = QCheckBox("Enable Pinch-to-Zoom Gesture", dlg)
    chk_pinch.setChecked(CONFIG["pinch_zoom"])
    form.addRow("", chk_pinch)

    lay.addLayout(form)

    # Save logic
    def on_change():
        CONFIG["enabled"] = chk_enabled.isChecked()
        CONFIG["orbit_speed"] = spn_orbit.value()
        CONFIG["pan_speed"] = spn_pan.value()
        CONFIG["zoom_speed"] = spn_zoom.value()
        CONFIG["invert_orbit_x"] = chk_inv_x.isChecked()
        CONFIG["invert_orbit_y"] = chk_inv_y.isChecked()
        CONFIG["pinch_zoom"] = chk_pinch.isChecked()

    chk_enabled.toggled.connect(on_change)
    spn_orbit.valueChanged.connect(on_change)
    spn_pan.valueChanged.connect(on_change)
    spn_zoom.valueChanged.connect(on_change)
    chk_inv_x.toggled.connect(on_change)
    chk_inv_y.toggled.connect(on_change)
    chk_pinch.toggled.connect(on_change)

    bbox = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dlg)
    bbox.rejected.connect(dlg.close)
    lay.addWidget(bbox)

    def on_closed():
        global _dialog_instance
        _dialog_instance = None

    dlg.finished.connect(lambda _: on_closed())

    _dialog_instance = dlg
    dlg.show()
    return dlg


# -----------------------------------------------------------------------------
# Tool class for Extensions menu
# -----------------------------------------------------------------------------

class MacTrackpadNavigationTool(Tool):
    """Tool entry in Extensions menu."""

    name = "MAC Trackpad Navigation"
    shortcut = "Ctrl+Alt+T"
    description = "MAC trackpad navigation (Blender-style): 2-finger orbit, Shift pan, Ctrl zoom."

    def on_activate(self, viewport):
        win = viewport.window() if hasattr(viewport, "window") else None
        show_preferences_dialog(win)


# -----------------------------------------------------------------------------
# Extension Entry Point: setup(app)
# -----------------------------------------------------------------------------

def attach_to_viewport(vp):
    """Ensure the filter is installed on the given viewport."""
    if vp is None:
        return
    existing = getattr(vp, "_blender_trackpad_filter", None)
    if existing is None:
        flt = MacTrackpadFilter(vp)
        vp.installEventFilter(flt)
        vp._blender_trackpad_filter = flt


def setup(app) -> None:
    """Extension initialization called on startup with ExtensionApp."""
    attach_to_viewport(app.viewport)

    # Keep track when projects switch tabs or documents change
    app.on_document_changed(lambda: attach_to_viewport(app.viewport))

    # Menu item under Extensions
    app.add_menu_action(
        "MAC Trackpad Navigation…",
        lambda: show_preferences_dialog(app.window),
        shortcut="Ctrl+Alt+T",
        tip="Configure MAC trackpad navigation (Blender-style) (Orbit, Pan, Zoom)",
    )
