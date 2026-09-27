from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_production_filter_excludes_development_copies_and_preserves_canonical_node():
    source = (ROOT / "comfyapp.py").read_text(encoding="utf-8-sig")
    assert "comfyui-modal-(?:agent" in source
    assert "|dc\\d+" in source
    assert "local_agent_or_worktree_clone" in source
    assert "comfyui-modal/.gitignore" in source


def test_filter_is_used_for_dependency_context_manifest_and_image_source():
    source = (ROOT / "comfyapp.py").read_text(encoding="utf-8-sig")
    assert "_iter_syncable_custom_node_dirs(source_root)" in source
    assert "_iter_syncable_custom_node_dirs(_LOCAL_CUSTOM_NODES)" in source
    assert "_CUSTOM_NODE_LOCAL_CLONE_RE" in source
    assert "comfyui-modal-agent*/" in source
    assert "comfyui-modal-dc*/" in source
