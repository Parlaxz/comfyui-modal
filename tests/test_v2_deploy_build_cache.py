from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dependency_build_context_is_metadata_stable():
    source = (ROOT / "comfyapp.py").read_text(encoding="utf-8-sig")
    assert "def _normalize_requirements_context_metadata" in source
    assert "_REQUIREMENTS_CONTEXT_MTIME = 946684800" in source
    assert "shutil.copyfile(src, dst)" in source
    assert "_normalize_requirements_context_metadata(target_root)" in source


def test_cachedit_lock_is_ensured_not_force_reinstalled():
    source = (ROOT / "comfyapp.py").read_text(encoding="utf-8-sig")
    assert 'pip install --force-reinstall --no-deps -r "$_lock"' not in source
    assert "CACHEDIT_LOCK_FAMILY_REINSTALL_START" not in source
    assert "CACHEDIT_LOCK_FAMILY_ENSURE_START" in source
    assert "--disable-pip-version-check --no-input --no-deps" in source


def test_build_gate_never_touches_runtime_state_mount():
    source = (ROOT / "comfyapp.py").read_text(encoding="utf-8-sig")
    assert 'shutil.rmtree("/root/comfymodal_runtime_state"' not in source


def test_v2_runtime_state_uses_clean_mount_namespace():
    source = (ROOT / "comfymodal_runtime" / "modal_app.py").read_text(encoding="utf-8-sig")
    assert 'RUNTIME_STATE_PATH = "/mnt/comfymodal_runtime_state"' in source
    assert 'RUNTIME_STATE_PATH = "/root/comfymodal_runtime_state"' not in source


def test_changed_python_files_parse():
    for relative in ("comfyapp.py", "comfymodal_runtime/modal_app.py"):
        source = (ROOT / relative).read_text(encoding="utf-8-sig")
        ast.parse(source, filename=relative)
