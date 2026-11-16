# SPDX-License-Identifier: MIT
# Copyright (c) 2026 IngeTrazo contributors
"""Package entry for folder installs (GitHub zip / Extensions folder).

IngeTrazo loads a directory only when ``__init__.py`` sits directly inside
it. Dropping the unzipped repository folder into the plugins directory
used to show as ``ingetrazo-mac-trackpad-navigation-… (load error)`` because
this file was missing. The catalog still installs the single-file module
``mac_trackpad_navigation.py``.

Loaded by file path (not ``sys.path``), so the implementation is imported
explicitly from the sibling ``.py`` rather than with a package-relative
import that can fail under IngeTrazo's private module name.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_impl_path = Path(__file__).with_name("mac_trackpad_navigation.py")
_mod_name = f"{__name__}._mac_trackpad_navigation_impl"
_spec = importlib.util.spec_from_file_location(_mod_name, _impl_path)
if _spec is None or _spec.loader is None:
    raise ImportError(f"cannot load extension implementation from {_impl_path}")
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_mod_name] = _mod
_spec.loader.exec_module(_mod)

CONFIG = _mod.CONFIG
MacTrackpadFilter = _mod.MacTrackpadFilter
MacTrackpadNavigationTool = _mod.MacTrackpadNavigationTool
attach_to_viewport = _mod.attach_to_viewport
load_config = _mod.load_config
save_config = _mod.save_config
setup = _mod.setup
show_preferences_dialog = _mod.show_preferences_dialog

__all__ = [
    "CONFIG",
    "MacTrackpadFilter",
    "MacTrackpadNavigationTool",
    "attach_to_viewport",
    "load_config",
    "save_config",
    "setup",
    "show_preferences_dialog",
]
