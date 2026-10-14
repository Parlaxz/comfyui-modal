"""FAST_UNIT: Studio KJNodes layout editor contracts.

Thin pytest wrapper over the real Node unit (tests/studio_layout_editor_unit.mjs,
which drives web/studio-layout-editor.js with a DOM stub) plus read-only
structural pins on the editor module and the web/studio-playground.js seam:
kj store key, JSON serializer, prompt-role Send. No ComfyUI/Modal imports.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.fast_unit

ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "web" / "studio-layout-editor.js"
PLAYGROUND = ROOT / "web" / "studio-playground.js"
NODE_UNIT = ROOT / "tests" / "studio_layout_editor_unit.mjs"

KJ_KEY = "comfymodal.studio.layout.kj.v1"
LEGACY_KEY = "comfymodal.studio.layout.v1"


def test_node_unit_green():
    """The real editor unit (norm/caption/parse/migration/persistence/canvas) passes."""
    node = shutil.which("node")
    assert node, "node is required to run the layout editor unit"
    proc = subprocess.run(
        [node, str(NODE_UNIT)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        cwd=str(ROOT),
    )
    tail = (proc.stdout + proc.stderr).strip()[-3000:]
    assert proc.returncode == 0, f"layout editor unit failed:\n{tail}"
    assert "ALL STUDIO LAYOUT EDITOR UNIT TESTS GREEN" in proc.stdout


def test_editor_module_surface():
    """The KJ port exports the tested surface, carries GPL-3.0, and has zero imports."""
    text = EDITOR.read_text(encoding="utf-8")
    assert "GPL-3.0" in text
    for name in (
        "export function normBboxToGrid",
        "export function buildIdeogramCaption",
        "export function parseIdeogramCaption",
        "export function createLayoutEditor",
    ):
        assert name in text, f"missing {name}"
    assert KJ_KEY in text
    assert LEGACY_KEY in text
    assert "MAX_ELEM_COLORS = 5" in text
    assert "MAX_STYLE_COLORS = 16" in text
    for line in text.splitlines():
        assert not line.startswith("import "), "editor must stay dependency-free"
    # Send/preview testids belong to the playground seam, not the editor.
    assert "layout-send" not in text
    assert "layout-preview" not in text


def test_playground_layout_seam():
    """The seam persists the kj key, serializes Ideogram JSON, Sends via the prompt role."""
    text = PLAYGROUND.read_text(encoding="utf-8")
    assert f'LAYOUT_KJ_STORE_KEY = "{KJ_KEY}"' in text
    assert "function serializeLayout" in text
    assert "buildIdeogramCaption" in text
    assert 'commitShelfValue(state, context, actions, "prompt", text)' in text
