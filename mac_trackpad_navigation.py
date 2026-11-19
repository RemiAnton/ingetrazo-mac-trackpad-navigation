# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Remi Clinton and IngeTrazo contributors
"""MAC Trackpad Navigation for IngeTrazo on macOS.

Brings seamless, native Apple-grade trackpad navigation to IngeTrazo:
- Two-finger drag: Orbit view around model/pivot point (or Pan in SketchUp mode)
- Shift + Two-finger drag: Pan camera across the scene
- Control + Two-finger drag (or Cmd): Smooth continuous zoom focused at 3D cursor
- Two-finger pinch: Native pinch-to-zoom with adjustable sensitivity
- Two-finger rotate: View-plane roll and turntable azimuth rotation
- Two-finger double-tap: Context-aware Smart Zoom (Zoom Selection / Extents)
- Momentum Coasting: Physics-based fluid coasting with instant tap-to-halt
- Visual 3D Orbit Reticle: High-DPI QPainter overlay indicating pivot point
- Navigation Presets: 1-click switching between Blender, SketchUp, and CAD styles
- Preferences Dialog: Interactive sliders, axis inversion, preset switcher, and reset
"""
from __future__ import annotations

import math
import sys
import time
from typing import Any, Dict, Optional

from PySide6.QtCore import QEvent, QObject, QPointF, QSettings, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QNativeGestureEvent,
    QPainter,
    QPen,
    QPointingDevice,
    QVector3D,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)
from tools.base import Tool

try:
    from core.i18n import current_language
except ImportError:
    def current_language() -> str:
        return "en"


# -----------------------------------------------------------------------------
# Configuration & Presets
# -----------------------------------------------------------------------------

PRESETS = {
    "blender": {
        "name_en": "Blender Style (Orbit Default)",
        "name_es": "Estilo Blender (Órbita por defecto)",
        "name_pt": "Estilo Blender (Órbita padrão)",
        "tip_en": "Drag: Orbit  |  ⇧ Shift: Pan  |  ⌃ Ctrl / ⌘ Cmd: Zoom",
        "tip_es": "Arrastre: Órbita  |  ⇧ Shift: Encuadre  |  ⌃ Ctrl / ⌘ Cmd: Zoom",
        "tip_pt": "Arrastar: Órbita  |  ⇧ Shift: Panorâmica  |  ⌃ Ctrl / ⌘ Cmd: Zoom",
    },
    "sketchup": {
        "name_en": "SketchUp Style (Pan Default)",
        "name_es": "Estilo SketchUp (Encuadre por defecto)",
        "name_pt": "Estilo SketchUp (Panorâmica padrão)",
        "tip_en": "Drag: Pan  |  ⇧ Shift or ⌥ Opt: Orbit  |  ⌃ Ctrl / ⌘ Cmd: Zoom",
        "tip_es": "Arrastre: Encuadre  |  ⇧ Shift u ⌥ Opt: Órbita  |  ⌃ Ctrl / ⌘ Cmd: Zoom",
        "tip_pt": "Arrastar: Panorâmica  |  ⇧ Shift ou ⌥ Opt: Órbita  |  ⌃ Ctrl / ⌘ Cmd: Zoom",
    },
    "cad": {
        "name_en": "CAD Standard",
        "name_es": "Estándar CAD",
        "name_pt": "Padrão CAD",
        "tip_en": "Drag: Pan  |  ⌘ Cmd: Orbit  |  ⇧ Shift: Zoom",
        "tip_es": "Arrastre: Encuadre  |  ⌘ Cmd: Órbita  |  ⇧ Shift: Zoom",
        "tip_pt": "Arrastar: Panorâmica  |  ⌘ Cmd: Órbita  |  ⇧ Shift: Zoom",
    },
}

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": sys.platform == "darwin",
    "preset": "blender",
    "orbit_speed": 1.0,
    "pan_speed": 1.0,
    "zoom_speed": 0.025,
    "pinch_sensitivity": 3.0,
    "momentum_coasting": True,
    "show_orbit_pivot": True,
    "invert_orbit_x": False,
    "invert_orbit_y": False,
    "invert_zoom": False,
    "pinch_zoom": True,
    "rotate_gesture": True,
    "smart_zoom": True,
}

CONFIG: Dict[str, Any] = dict(DEFAULT_CONFIG)

_SETTINGS_PREFIX = "plugins/mac_trackpad_navigation/"
_dialog_instance: Optional[QDialog] = None
_app_ref: Optional[Any] = None

# Active pivot point for QPainter overlay: tuple(world_x, world_y, world_z, timestamp)
_active_pivot: Optional[tuple[float, float, float, float]] = None


# -----------------------------------------------------------------------------
# Configuration Persistence
# -----------------------------------------------------------------------------

def load_config() -> None:
    """Read saved preferences from QSettings; unreadable values keep defaults."""
    settings = QSettings()
    for key, default in DEFAULT_CONFIG.items():
        value = settings.value(_SETTINGS_PREFIX + key)
        if value is None:
            continue
        try:
            if isinstance(default, bool):
                CONFIG[key] = str(value).lower() in ("1", "true")
            elif isinstance(default, float):
                CONFIG[key] = float(value)
            elif isinstance(default, str):
                CONFIG[key] = str(value)
        except (TypeError, ValueError):
            pass


def save_config() -> None:
    """Persist current configuration to QSettings."""
    settings = QSettings()
    for key, value in CONFIG.items():
        settings.setValue(_SETTINGS_PREFIX + key, value)


def reset_config_to_defaults() -> None:
    """Restore default settings and save."""
    global CONFIG
    CONFIG.clear()
    CONFIG.update(DEFAULT_CONFIG)
    save_config()


# -----------------------------------------------------------------------------
# Event Filter & Trackpad Gesture Controller
# -----------------------------------------------------------------------------

class MacTrackpadFilter(QObject):
    """Event filter attached to Viewport to handle fluid trackpad gestures."""

    def __init__(self, viewport):
        super().__init__(viewport)
        self.viewport = viewport
        self.last_event_time = 0.0
        self.orbit_pivot = None
        self._is_coasting = False

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
            # Safe isolation: an extension should never freeze or crash IngeTrazo
            return False

        return False

    def _is_touchpad(self, event: QWheelEvent) -> bool:
        if hasattr(event, "pointingDevice"):
            dev = event.pointingDevice()
            if dev is not None and dev.type() == QPointingDevice.DeviceType.TouchPad:
                return True
        if hasattr(event, "hasPixelDelta") and event.hasPixelDelta() and not event.pixelDelta().isNull():
            return True
        return False

    def _handle_wheel(self, event: QWheelEvent) -> bool:
        touchpad = self._is_touchpad(event)

        # High precision pixel delta on macOS trackpad
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
        is_ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        is_alt = bool(mods & Qt.KeyboardModifier.AltModifier)
        is_cmd = bool(mods & Qt.KeyboardModifier.MetaModifier)

        # Traditional mouse wheel without modifiers falls back to built-in zoom
        if not touchpad and not (is_shift or is_ctrl or is_alt or is_cmd):
            return False

        # Phase tracking & Apple-style momentum interruptibility
        phase = getattr(event, "phase", lambda: Qt.ScrollPhase.NoScrollPhase)()
        now = time.monotonic()

        # Touch-down instantly interrupts momentum coasting
        if phase == Qt.ScrollPhase.ScrollBegin:
            self._is_coasting = False
        elif phase == Qt.ScrollPhase.ScrollMomentum:
            if not CONFIG["momentum_coasting"]:
                return False  # Coasting disabled by user preference
            self._is_coasting = True
        elif phase == Qt.ScrollPhase.ScrollEnd:
            self._is_coasting = False
            self.orbit_pivot = None
            _fade_orbit_pivot()

        pos = event.position()
        vh = max(self.viewport.height(), 1)
        preset = CONFIG.get("preset", "blender")

        # Determine target action based on active Preset and Modifiers
        action = "orbit"  # default
        if preset == "blender":
            if is_shift:
                action = "pan"
            elif is_ctrl or is_cmd:
                action = "zoom"
            else:
                action = "orbit"
        elif preset == "sketchup":
            if is_shift or is_alt:
                action = "orbit"
            elif is_ctrl or is_cmd:
                action = "zoom"
            else:
                action = "pan"
        elif preset == "cad":
            if is_cmd or is_alt:
                action = "orbit"
            elif is_shift or is_ctrl:
                action = "zoom"
            else:
                action = "pan"

        # -------------------------------------------------------------
        # Action 1: PAN
        # -------------------------------------------------------------
        if action == "pan":
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
        # Action 2: ZOOM
        # -------------------------------------------------------------
        elif action == "zoom":
            direction = -1.0 if CONFIG["invert_zoom"] else 1.0
            steps = dy * CONFIG["zoom_speed"] * direction
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
        # Action 3: ORBIT
        # -------------------------------------------------------------
        else:
            if phase == Qt.ScrollPhase.ScrollBegin or (now - self.last_event_time) > 0.25:
                if hasattr(self.viewport, "_orbit_pivot_at"):
                    try:
                        self.orbit_pivot = self.viewport._orbit_pivot_at(pos.x(), pos.y())
                    except Exception:
                        self.orbit_pivot = None
                else:
                    self.orbit_pivot = None

                # Update visual pivot overlay
                if self.orbit_pivot is not None and CONFIG["show_orbit_pivot"]:
                    _set_active_pivot(self.orbit_pivot)

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
        gtype = getattr(event, "gestureType", lambda: None)()

        # -------------------------------------------------------------
        # Gesture 1: PINCH TO ZOOM
        # -------------------------------------------------------------
        if gtype == Qt.NativeGestureType.ZoomNativeGesture:
            if not CONFIG["pinch_zoom"]:
                return False

            val = float(getattr(event, "value", lambda: 0.0)())
            direction = -1.0 if CONFIG["invert_zoom"] else 1.0
            steps = val * CONFIG["pinch_sensitivity"] * direction
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

        # -------------------------------------------------------------
        # Gesture 2: TWO-FINGER ROTATE (Turntable roll)
        # -------------------------------------------------------------
        elif gtype == Qt.NativeGestureType.RotateNativeGesture:
            if not CONFIG["rotate_gesture"]:
                return False

            angle_deg = float(getattr(event, "value", lambda: 0.0)())
            vh = max(self.viewport.height(), 1)
            # Two-finger twist orbits horizontally (azimuth rotation)
            odx = angle_deg * 8.0 * CONFIG["orbit_speed"]
            if CONFIG["invert_orbit_x"]:
                odx = -odx

            if self.orbit_pivot is not None:
                self.viewport.camera.orbit_about(self.orbit_pivot, odx, 0.0, vh)
            else:
                self.viewport.camera.orbit(odx, 0.0, vh)

            self.viewport.update()
            event.accept()
            return True

        # -------------------------------------------------------------
        # Gesture 3: SMART ZOOM DOUBLE-TAP
        # -------------------------------------------------------------
        elif gtype == Qt.NativeGestureType.SmartZoomNativeGesture:
            if not CONFIG["smart_zoom"]:
                return False

            win = self.viewport.window()
            # Context-aware: frame selection if available, else Zoom Extents
            act = None
            if hasattr(win, "_act_zoom_selection"):
                act = getattr(win, "_act_zoom_selection", None)
            if act is None:
                act = getattr(win, "_act_zoom_extents", None)

            if act is not None:
                act.trigger()
                event.accept()
                return True

        return False


# -----------------------------------------------------------------------------
# Visual Orbit Pivot Overlay (QPainter via Extension API v2)
# -----------------------------------------------------------------------------

def _set_active_pivot(pivot_vec) -> None:
    global _active_pivot
    try:
        if hasattr(pivot_vec, "x") and hasattr(pivot_vec, "y") and hasattr(pivot_vec, "z"):
            _active_pivot = (float(pivot_vec.x()), float(pivot_vec.y()), float(pivot_vec.z()), time.monotonic())
        elif isinstance(pivot_vec, (list, tuple)) and len(pivot_vec) >= 3:
            _active_pivot = (float(pivot_vec[0]), float(pivot_vec[1]), float(pivot_vec[2]), time.monotonic())
    except Exception:
        _active_pivot = None


def _fade_orbit_pivot() -> None:
    global _active_pivot
    if _active_pivot is not None:
        # Mark timestamp for quick fade-out
        _active_pivot = (_active_pivot[0], _active_pivot[1], _active_pivot[2], time.monotonic() - 0.4)


def draw_pivot_overlay(viewport, painter: QPainter) -> None:
    """Render a crisp, high-DPI Apple-style reticle at the active 3D orbit pivot."""
    global _active_pivot
    if not CONFIG["enabled"] or not CONFIG["show_orbit_pivot"] or _active_pivot is None:
        return

    now = time.monotonic()
    age = now - _active_pivot[3]
    if age > 0.8:
        _active_pivot = None
        return

    # Opacity calculation: steady during orbit, smooth fade out on release
    alpha = max(0.0, min(1.0, 1.0 - (age - 0.2) / 0.6)) if age > 0.2 else 1.0
    if alpha <= 0.01:
        _active_pivot = None
        return

    # Project 3D point to 2D viewport coordinates
    pt_2d = None
    if _app_ref is not None and hasattr(_app_ref, "world_to_pixels"):
        try:
            pts = [[_active_pivot[0], _active_pivot[1], _active_pivot[2]]]
            pxs, pys, in_front = _app_ref.world_to_pixels(pts)
            if in_front and in_front[0]:
                pt_2d = QPointF(float(pxs[0]), float(pys[0]))
        except Exception:
            pt_2d = None

    if pt_2d is None and hasattr(viewport, "camera") and hasattr(viewport.camera, "project"):
        try:
            vec = QVector3D(_active_pivot[0], _active_pivot[1], _active_pivot[2])
            res = viewport.camera.project(vec, viewport.width(), viewport.height())
            if res is not None:
                pt_2d = QPointF(float(res.x()), float(res.y()))
        except Exception:
            pt_2d = None

    if pt_2d is None:
        return

    # Draw Apple-grade pivot indicator in IngeTrazo Blue
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    color_ring = QColor(77, 140, 242, int(180 * alpha))
    color_dot = QColor(77, 140, 242, int(240 * alpha))
    color_white = QColor(255, 255, 255, int(200 * alpha))

    # Outer glow / boundary ring
    pen_ring = QPen(color_ring, 2.0)
    painter.setPen(pen_ring)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(pt_2d, 9.0, 9.0)

    # 4 Cardinal Crosshair ticks
    painter.setPen(QPen(color_white, 1.5))
    cx, cy = pt_2d.x(), pt_2d.y()
    painter.drawLine(QPointF(cx - 13.0, cy), QPointF(cx - 6.0, cy))
    painter.drawLine(QPointF(cx + 6.0, cy), QPointF(cx + 13.0, cy))
    painter.drawLine(QPointF(cx, cy - 13.0), QPointF(cx, cy - 6.0))
    painter.drawLine(QPointF(cx, cy + 6.0), QPointF(cx, cy + 13.0))

    # Center focus dot
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(color_dot))
    painter.drawEllipse(pt_2d, 2.5, 2.5)

    painter.restore()


# -----------------------------------------------------------------------------
# Preferences Dialog (UI/UX Pro Max Architecture)
# -----------------------------------------------------------------------------

def show_preferences_dialog(parent_window=None) -> QDialog:
    global _dialog_instance
    if _dialog_instance is not None:
        _dialog_instance.show()
        _dialog_instance.raise_()
        _dialog_instance.activateWindow()
        return _dialog_instance

    lang = current_language()

    # Localized UI string tables
    i18n = {
        "title": {
            "en": "MAC Trackpad Navigation",
            "es": "Navegación de Trackpad para Mac",
            "pt-BR": "Navegação de Trackpad para Mac",
        },
        "preset_box": {
            "en": "Navigation Style Preset",
            "es": "Estilo de Navegación",
            "pt-BR": "Estilo de Navegação",
        },
        "sensitivities": {
            "en": "Sensitivities & Speed",
            "es": "Sensibilidad y Velocidad",
            "pt-BR": "Sensibilidade e Velocidade",
        },
        "orbit_sens": {"en": "Orbit Sensitivity:", "es": "Sensibilidad de Órbita:", "pt-BR": "Sensibilidade de Órbita:"},
        "pan_sens": {"en": "Pan Sensitivity:", "es": "Sensibilidad de Encuadre:", "pt-BR": "Sensibilidade de Pan:"},
        "zoom_sens": {"en": "Zoom Sensitivity:", "es": "Sensibilidad de Zoom:", "pt-BR": "Sensibilidade de Zoom:"},
        "pinch_sens": {"en": "Pinch Sensitivity:", "es": "Sensibilidad de Pinza:", "pt-BR": "Sensibilidade de Pinça:"},
        "behavior": {
            "en": "Behavior & Visual Feedback",
            "es": "Comportamiento y Respuesta Visual",
            "pt-BR": "Comportamento e Resposta Visual",
        },
        "enable_trackpad": {
            "en": "Enable Trackpad Navigation",
            "es": "Activar navegación por trackpad",
            "pt-BR": "Ativar navegação por trackpad",
        },
        "momentum": {
            "en": "Enable Inertial Momentum Coasting",
            "es": "Activar deslizamiento inercial continuo",
            "pt-BR": "Ativar inércia contínua de movimento",
        },
        "orbit_pivot": {
            "en": "Show 3D Orbit Focus Reticle",
            "es": "Mostrar punto de mira 3D en órbita",
            "pt-BR": "Exibir retículo 3D de foco na órbita",
        },
        "pinch": {
            "en": "Enable Two-Finger Pinch Zoom",
            "es": "Activar zoom con gesto de pinza",
            "pt-BR": "Ativar zoom com gesto de pinça",
        },
        "rotate": {
            "en": "Enable Two-Finger Rotate Gesture",
            "es": "Activar rotación con dos dedos",
            "pt-BR": "Ativar rotação com dois dedos",
        },
        "smart_zoom": {
            "en": "Enable Two-Finger Double-Tap (Smart Zoom)",
            "es": "Doble toque con dos dedos (Zoom Inteligente)",
            "pt-BR": "Toque duplo com dois dedos (Zoom Inteligente)",
        },
        "inversions": {
            "en": "Axis & Direction Inversions",
            "es": "Inversión de Ejes y Dirección",
            "pt-BR": "Inversão de Eixos e Direção",
        },
        "inv_x": {"en": "Invert Horizontal Orbit (X)", "es": "Invertir órbita horizontal (X)", "pt-BR": "Inverter órbita horizontal (X)"},
        "inv_y": {"en": "Invert Vertical Orbit (Y)", "es": "Invertir órbita vertical (Y)", "pt-BR": "Inverter órbita vertical (Y)"},
        "inv_zoom": {"en": "Invert Zoom Direction (Natural Zoom)", "es": "Invertir dirección de zoom (Natural)", "pt-BR": "Inverter direção do zoom"},
        "btn_reset": {"en": "Reset to Defaults", "es": "Restablecer valores", "pt-BR": "Restaurar padrões"},
        "btn_close": {"en": "Close", "es": "Cerrar", "pt-BR": "Fechar"},
    }

    def t(key: str) -> str:
        entry = i18n.get(key, {})
        return entry.get(lang, entry.get("en", key))

    dlg = QDialog(parent_window)
    dlg.setWindowTitle(t("title"))
    dlg.setMinimumWidth(440)

    lay = QVBoxLayout(dlg)
    lay.setSpacing(14)

    # 1. Preset Selector Box
    box_preset = QGroupBox(t("preset_box"), dlg)
    lay_preset = QVBoxLayout(box_preset)

    cmb_preset = QComboBox(box_preset)
    for pkey, pdata in PRESETS.items():
        name_key = f"name_{lang}" if f"name_{lang}" in pdata else "name_en"
        cmb_preset.addItem(pdata[name_key], pkey)

    cur_idx = cmb_preset.findData(CONFIG.get("preset", "blender"))
    if cur_idx >= 0:
        cmb_preset.setCurrentIndex(cur_idx)

    lbl_preset_tip = QLabel("", box_preset)
    lbl_preset_tip.setStyleSheet("color: #666; font-size: 11px; padding: 2px 4px;")
    lay_preset.addWidget(cmb_preset)
    lay_preset.addWidget(lbl_preset_tip)
    lay.addWidget(box_preset)

    def update_preset_tip():
        pkey = cmb_preset.currentData()
        pdata = PRESETS.get(pkey, PRESETS["blender"])
        tip_key = f"tip_{lang}" if f"tip_{lang}" in pdata else "tip_en"
        lbl_preset_tip.setText(f"<b>{pdata[tip_key]}</b>")

    update_preset_tip()

    # 2. Sensitivities with Synchronized Sliders + SpinBoxes
    box_sens = QGroupBox(t("sensitivities"), dlg)
    form_sens = QFormLayout(box_sens)
    form_sens.setSpacing(8)

    def make_slider_row(label_text: str, vmin: float, vmax: float, vstep: float, decimals: int, init_val: float):
        row_widget = QWidget(box_sens)
        row_lay = QHBoxLayout(row_widget)
        row_lay.setContentsMargins(0, 0, 0, 0)
        row_lay.setSpacing(10)

        slider = QSlider(Qt.Orientation.Horizontal, row_widget)
        spin = QDoubleSpinBox(row_widget)
        spin.setRange(vmin, vmax)
        spin.setSingleStep(vstep)
        spin.setDecimals(decimals)
        spin.setValue(init_val)

        # Scale slider to integer steps (e.g. 100 steps per unit)
        multiplier = 10 ** decimals
        slider.setRange(int(vmin * multiplier), int(vmax * multiplier))
        slider.setValue(int(init_val * multiplier))

        def on_slider(val):
            fval = float(val) / multiplier
            spin.blockSignals(True)
            spin.setValue(fval)
            spin.blockSignals(False)

        def on_spin(fval):
            slider.blockSignals(True)
            slider.setValue(int(fval * multiplier))
            slider.blockSignals(False)

        slider.valueChanged.connect(on_slider)
        spin.valueChanged.connect(on_spin)

        row_lay.addWidget(slider, 1)
        row_lay.addWidget(spin, 0)
        form_sens.addRow(label_text, row_widget)
        return slider, spin, multiplier

    _, spn_orbit, m_orbit = make_slider_row(t("orbit_sens"), 0.1, 5.0, 0.1, 1, CONFIG["orbit_speed"])
    _, spn_pan, m_pan = make_slider_row(t("pan_sens"), 0.1, 5.0, 0.1, 1, CONFIG["pan_speed"])
    _, spn_zoom, m_zoom = make_slider_row(t("zoom_sens"), 0.005, 0.1, 0.005, 3, CONFIG["zoom_speed"])
    _, spn_pinch, m_pinch = make_slider_row(t("pinch_sens"), 0.5, 10.0, 0.5, 1, CONFIG["pinch_sensitivity"])

    lay.addWidget(box_sens)

    # 3. Behavior & Visuals
    box_behav = QGroupBox(t("behavior"), dlg)
    lay_behav = QVBoxLayout(box_behav)
    lay_behav.setSpacing(6)

    chk_enabled = QCheckBox(t("enable_trackpad"), box_behav)
    chk_enabled.setChecked(CONFIG["enabled"])
    lay_behav.addWidget(chk_enabled)

    chk_momentum = QCheckBox(t("momentum"), box_behav)
    chk_momentum.setChecked(CONFIG["momentum_coasting"])
    lay_behav.addWidget(chk_momentum)

    chk_pivot = QCheckBox(t("orbit_pivot"), box_behav)
    chk_pivot.setChecked(CONFIG["show_orbit_pivot"])
    lay_behav.addWidget(chk_pivot)

    chk_pinch = QCheckBox(t("pinch"), box_behav)
    chk_pinch.setChecked(CONFIG["pinch_zoom"])
    lay_behav.addWidget(chk_pinch)

    chk_rotate = QCheckBox(t("rotate"), box_behav)
    chk_rotate.setChecked(CONFIG["rotate_gesture"])
    lay_behav.addWidget(chk_rotate)

    chk_smart = QCheckBox(t("smart_zoom"), box_behav)
    chk_smart.setChecked(CONFIG["smart_zoom"])
    lay_behav.addWidget(chk_smart)

    lay.addWidget(box_behav)

    # 4. Inversions
    box_inv = QGroupBox(t("inversions"), dlg)
    lay_inv = QVBoxLayout(box_inv)
    lay_inv.setSpacing(6)

    chk_inv_x = QCheckBox(t("inv_x"), box_inv)
    chk_inv_x.setChecked(CONFIG["invert_orbit_x"])
    lay_inv.addWidget(chk_inv_x)

    chk_inv_y = QCheckBox(t("inv_y"), box_inv)
    chk_inv_y.setChecked(CONFIG["invert_orbit_y"])
    lay_inv.addWidget(chk_inv_y)

    chk_inv_zoom = QCheckBox(t("inv_zoom"), box_inv)
    chk_inv_zoom.setChecked(CONFIG["invert_zoom"])
    lay_inv.addWidget(chk_inv_zoom)

    lay.addWidget(box_inv)

    # 5. Live synchronization and persistence
    def on_change():
        CONFIG["enabled"] = chk_enabled.isChecked()
        CONFIG["preset"] = cmb_preset.currentData()
        CONFIG["orbit_speed"] = spn_orbit.value()
        CONFIG["pan_speed"] = spn_pan.value()
        CONFIG["zoom_speed"] = spn_zoom.value()
        CONFIG["pinch_sensitivity"] = spn_pinch.value()
        CONFIG["momentum_coasting"] = chk_momentum.isChecked()
        CONFIG["show_orbit_pivot"] = chk_pivot.isChecked()
        CONFIG["pinch_zoom"] = chk_pinch.isChecked()
        CONFIG["rotate_gesture"] = chk_rotate.isChecked()
        CONFIG["smart_zoom"] = chk_smart.isChecked()
        CONFIG["invert_orbit_x"] = chk_inv_x.isChecked()
        CONFIG["invert_orbit_y"] = chk_inv_y.isChecked()
        CONFIG["invert_zoom"] = chk_inv_zoom.isChecked()
        update_preset_tip()
        save_config()

    cmb_preset.currentIndexChanged.connect(on_change)
    spn_orbit.valueChanged.connect(on_change)
    spn_pan.valueChanged.connect(on_change)
    spn_zoom.valueChanged.connect(on_change)
    spn_pinch.valueChanged.connect(on_change)
    chk_enabled.toggled.connect(on_change)
    chk_momentum.toggled.connect(on_change)
    chk_pivot.toggled.connect(on_change)
    chk_pinch.toggled.connect(on_change)
    chk_rotate.toggled.connect(on_change)
    chk_smart.toggled.connect(on_change)
    chk_inv_x.toggled.connect(on_change)
    chk_inv_y.toggled.connect(on_change)
    chk_inv_zoom.toggled.connect(on_change)

    # 6. Action Bar: Reset to Defaults + Close
    btn_bar = QHBoxLayout()
    btn_reset = QPushButton(t("btn_reset"), dlg)

    def on_reset():
        reset_config_to_defaults()
        chk_enabled.setChecked(CONFIG["enabled"])
        pidx = cmb_preset.findData(CONFIG["preset"])
        if pidx >= 0:
            cmb_preset.setCurrentIndex(pidx)
        spn_orbit.setValue(CONFIG["orbit_speed"])
        spn_pan.setValue(CONFIG["pan_speed"])
        spn_zoom.setValue(CONFIG["zoom_speed"])
        spn_pinch.setValue(CONFIG["pinch_sensitivity"])
        chk_momentum.setChecked(CONFIG["momentum_coasting"])
        chk_pivot.setChecked(CONFIG["show_orbit_pivot"])
        chk_pinch.setChecked(CONFIG["pinch_zoom"])
        chk_rotate.setChecked(CONFIG["rotate_gesture"])
        chk_smart.setChecked(CONFIG["smart_zoom"])
        chk_inv_x.setChecked(CONFIG["invert_orbit_x"])
        chk_inv_y.setChecked(CONFIG["invert_orbit_y"])
        chk_inv_zoom.setChecked(CONFIG["invert_zoom"])
        update_preset_tip()

    btn_reset.clicked.connect(on_reset)
    btn_bar.addWidget(btn_reset)
    btn_bar.addStretch(1)

    bbox = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dlg)
    bbox.rejected.connect(dlg.close)
    btn_bar.addWidget(bbox)

    lay.addLayout(btn_bar)

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
    description = "Configure native Apple trackpad navigation (Blender/SketchUp/CAD styles, Momentum, Pivot reticle)."

    def on_activate(self, viewport):
        win = viewport.window() if hasattr(viewport, "window") else None
        show_preferences_dialog(win)


# -----------------------------------------------------------------------------
# Extension Entry Point: setup(app)
# -----------------------------------------------------------------------------

def attach_to_viewport(vp):
    """Ensure event filter is installed cleanly on the given viewport."""
    if vp is None:
        return
    existing = getattr(vp, "_blender_trackpad_filter", None)
    if existing is None:
        flt = MacTrackpadFilter(vp)
        vp.installEventFilter(flt)
        vp._blender_trackpad_filter = flt


def setup(app) -> None:
    """Extension initialization called on startup with ExtensionApp."""
    global _app_ref
    _app_ref = app

    load_config()
    attach_to_viewport(app.viewport)

    # Multi-tab and document lifecycle tracking
    app.on_document_changed(lambda: attach_to_viewport(app.viewport))

    # Viewport QPainter overlay for the 3D Orbit Focus Reticle
    if hasattr(app, "add_overlay"):
        try:
            app.add_overlay(draw_pivot_overlay)
        except Exception:
            pass

    # Extensions Menu Entry
    app.add_menu_action(
        "MAC Trackpad Navigation…",
        lambda: show_preferences_dialog(app.window),
        shortcut="Ctrl+Alt+T",
        tip="Configure MAC trackpad navigation presets, sensitivity, and momentum",
    )
