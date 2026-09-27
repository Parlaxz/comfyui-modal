"""Shared test-environment helpers.

Importing this module removes the real ComfyUI root from ``sys.path`` so
``import folder_paths`` fails inside tests and model discovery falls back to
the temporary ``comfyui_root`` passed by each test.  (The plugin's
``__init__.py`` — imported when pytest loads the ``tests`` package — adds
the real ComfyUI root to ``sys.path``, which would otherwise make discovery
scan the real models directory.)
"""

from __future__ import annotations

import sys
from pathlib import Path

_NODE_DIR = Path(__file__).resolve().parents[1]
_COMFYUI_ROOT = _NODE_DIR.parent.parent


def hide_real_folder_paths() -> None:
    sys.modules.pop("folder_paths", None)
    node_dir = _NODE_DIR.resolve()
    comfy_root = _COMFYUI_ROOT.resolve()
    cleaned: list[str] = []
    for entry in sys.path:
        if not entry:
            cleaned.append(entry)
            continue
        try:
            resolved = Path(entry).resolve()
        except Exception:
            cleaned.append(entry)
            continue
        if resolved.is_relative_to(comfy_root) and resolved != node_dir:
            continue
        cleaned.append(entry)
    sys.path[:] = cleaned


hide_real_folder_paths()
