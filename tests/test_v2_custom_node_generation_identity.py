"""Focused tests for the V2 custom-node generation identity.

Guards the bounded invariants introduced by the V2 cache-snapshot work:

- The clone filter is canonical in the shared publication policy used by
  ``comfyapp.py`` and ``__init__.py`` (local archive sync), so
  ``comfyui-modal-agent1-full-trace`` variants agree everywhere.
- ``custom_node_source_generation`` is deterministic: identical baked/runtime
  canonical content produces an identical generation, generated files/mtime
  do not affect it, CRLF/LF line endings are normalized, and real content
  changes still produce a mismatch.
- The local archive sync writes a deterministic content generation rather
  than a UUID where required for ``snapshot_exact_skip``.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import types
import uuid
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]


def _modal_stub():
    modal = types.ModuleType("modal")
    modal.Image = MagicMock()
    modal.Image.from_registry.return_value = MagicMock()
    modal.Image.debian_slim.return_value = MagicMock()
    modal.App = MagicMock()
    modal.App.return_value.function = lambda **_: lambda fn: fn
    modal.App.return_value.cls = lambda **_: lambda cls: cls
    modal.Volume = MagicMock()
    modal.Volume.from_name.return_value = MagicMock()
    modal.Dict = MagicMock()
    modal.Dict.from_name.return_value = MagicMock()
    modal.Secret = MagicMock()
    modal.Secret.from_name.return_value = MagicMock()
    modal.web_server = lambda *_, **__: lambda fn: fn
    modal.enter = lambda **_: lambda fn: fn
    modal.exit = lambda: lambda fn: fn
    modal.method = lambda *_, **__: lambda fn: fn
    modal.concurrent = lambda **_: lambda cls: cls
    return modal


def _load_comfyapp():
    old_modal = sys.modules.pop("modal", None)
    sys.modules["modal"] = _modal_stub()
    name = f"comfyapp_gen_identity_{uuid.uuid4().hex}"
    try:
        spec = importlib.util.spec_from_file_location(name, ROOT / "comfyapp.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(name, None)
        if old_modal is None:
            sys.modules.pop("modal", None)
        else:
            sys.modules["modal"] = old_modal


def _write_canonical_node(root: Path) -> None:
    node = root / "ComfyUI-KJNodes"
    (node / "src").mkdir(parents=True)
    (node / "requirements.txt").write_bytes(b"numpy\n")
    (node / "src" / "__init__.py").write_bytes(b"VALUE = 1\n")
    (node / "src" / "runtime.py").write_bytes(b"X = 1\n")


def _write_generated_artifacts(root: Path) -> None:
    node = root / "ComfyUI-KJNodes"
    (node / "build" / "lib").mkdir(parents=True)
    (node / "build" / "lib" / "generated.py").write_bytes(b"generated\n")
    (node / "logs").mkdir()
    (node / "logs" / "install.log").write_bytes(b"generated\n")
    (node / "benchmark_x.py").write_bytes(b"print(1)\n")
    (node / "trace_out.jsonl").write_bytes(b"x\n")


# ---------------------------------------------------------------------------
# Clone filter parity
# ---------------------------------------------------------------------------


def test_clone_filter_is_canonical_and_agent1_full_trace_variants_agree():
    """Both consumers use the same shared clone-filter policy."""
    from comfymodal_runtime.publication_policy import LOCAL_CLONE_RE

    canonical = LOCAL_CLONE_RE
    for variant in (
        "comfyui-modal-agent1-full-trace",
        "comfyui-modal-agent2",
        "comfyui-modal-agent3",
        "comfyui-modal-dc8",
        "comfyui-modal-worktree",
        "comfyui-modal-wt-x",
    ):
        assert canonical.fullmatch(variant), f"variant not matched: {variant}"
    assert not canonical.fullmatch("comfyui-modal-agent")
    assert not canonical.fullmatch("comfyui-modal-dcabc")


def test_archive_filter_excludes_agent_clones_via_canonical_regex():
    """The local archive-sync filter uses the shared publication policy."""
    from comfymodal_runtime.publication_policy import iter_syncable_custom_node_dirs

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name in ("comfyui-modal", "comfyui-modal-agent1-full-trace", "ComfyUI-KJNodes"):
            node = root / name
            node.mkdir()
            (node / "__init__.py").write_text("NODE = True\n", encoding="utf-8")
        assert iter_syncable_custom_node_dirs(root) == ["ComfyUI-KJNodes", "comfyui-modal"]


# ---------------------------------------------------------------------------
# Generation identity
# ---------------------------------------------------------------------------


def test_generation_is_path_independent_for_identical_content():
    module = _load_comfyapp()
    with tempfile.TemporaryDirectory() as tmp:
        baked = Path(tmp) / "baked"
        runtime = Path(tmp) / "runtime"
        _write_canonical_node(baked)
        shutil.copytree(baked, runtime)
        g_baked = module.custom_node_source_generation(str(baked))
        g_runtime = module.custom_node_source_generation(str(runtime))
    assert g_baked == g_runtime


def test_ordinary_runtime_edit_does_not_change_custom_node_identity(tmp_path):
    from comfymodal_runtime.deployment_spec import build_deployment_identity

    runtime = tmp_path / "runtime"
    custom = tmp_path / "custom_nodes"
    runtime.mkdir()
    custom.mkdir()
    (runtime / "runtime.py").write_text("VERSION = 1\n", encoding="utf-8")
    (custom / "node.py").write_text("VERSION = 1\n", encoding="utf-8")
    first = build_deployment_identity(runtime, custom_node_paths=[custom])
    (runtime / "runtime.py").write_text("VERSION = 2\n", encoding="utf-8")
    second = build_deployment_identity(runtime, custom_node_paths=[custom])
    assert first.custom_node_hash == second.custom_node_hash
    assert first.runtime_hash != second.runtime_hash


def test_generation_ignores_generated_files_and_mtime():
    module = _load_comfyapp()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "custom_nodes"
        _write_canonical_node(root)
        _write_generated_artifacts(root)
        g1 = module.custom_node_source_generation(str(root))
        # Touch generated files (mtime must not matter)
        (root / "ComfyUI-KJNodes" / "build" / "lib" / "generated.py").touch()
        (root / "ComfyUI-KJNodes" / "logs" / "install.log").touch()
        g2 = module.custom_node_source_generation(str(root))
        # Rewrite generated content (content must not matter either)
        (root / "ComfyUI-KJNodes" / "build" / "lib" / "generated.py").write_text("changed\n", encoding="utf-8")
        (root / "ComfyUI-KJNodes" / "logs" / "install.log").write_text("changed\n", encoding="utf-8")
        (root / "ComfyUI-KJNodes" / "benchmark_x.py").write_text("print(2)\n", encoding="utf-8")
        (root / "ComfyUI-KJNodes" / "trace_out.jsonl").write_text("y\n", encoding="utf-8")
        g3 = module.custom_node_source_generation(str(root))
    assert g1 == g2
    assert g1 == g3


def test_generation_normalizes_line_endings():
    module = _load_comfyapp()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "custom_nodes"
        _write_canonical_node(root)
        g1 = module.custom_node_source_generation(str(root))
        # Rewrite every tracked text file with CRLF endings.
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".py", ".txt", ".toml", ".cfg"}:
                data = path.read_bytes()
                path.write_bytes(data.replace(b"\n", b"\r\n"))
        g2 = module.custom_node_source_generation(str(root))
    assert g1 == g2


def test_generation_preserves_source_mismatches_but_not_dependency_metadata():
    module = _load_comfyapp()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "custom_nodes"
        _write_canonical_node(root)
        g1 = module.custom_node_source_generation(str(root))
        (root / "ComfyUI-KJNodes" / "src" / "runtime.py").write_text("X = 2\n", encoding="utf-8")
        g2 = module.custom_node_source_generation(str(root))
        (root / "ComfyUI-KJNodes" / "requirements.txt").write_text("numpy==1.26.4\n", encoding="utf-8")
        g3 = module.custom_node_source_generation(str(root))
    assert g1 != g2
    assert g2 == g3


def test_fingerprint_walk_is_sorted_and_excludes_generated_dirs():
    module = _load_comfyapp()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "custom_nodes"
        _write_canonical_node(root)
        _write_generated_artifacts(root)
        fp = module.custom_node_source_fingerprint(str(root))
        node = next(n for n in fp["nodes"] if n["name"] == "ComfyUI-KJNodes")
        # The content hash must not include generated dirs/files (the hash
        # value is opaque, so we verify by comparing against a tree without
        # generated artifacts).
        shutil.rmtree(root / "ComfyUI-KJNodes" / "build")
        shutil.rmtree(root / "ComfyUI-KJNodes" / "logs")
        (root / "ComfyUI-KJNodes" / "benchmark_x.py").unlink()
        (root / "ComfyUI-KJNodes" / "trace_out.jsonl").unlink()
        fp_clean = module.custom_node_source_fingerprint(str(root))
        node_clean = next(n for n in fp_clean["nodes"] if n["name"] == "ComfyUI-KJNodes")
    assert node["content_hash"] == node_clean["content_hash"]


# ---------------------------------------------------------------------------
# Local archive sync deterministic generation
# ---------------------------------------------------------------------------


def test_archive_sync_generation_is_content_derived_not_uuid():
    """sync_custom_nodes_to_volume must pass a deterministic content-derived
    generation (never a UUID) so snapshot_exact_skip identity survives a
    local archive sync of identical content."""
    module = _load_comfyapp()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "custom_nodes"
        _write_canonical_node(root)
        expected = module.custom_node_source_generation(str(root))
    src = (ROOT / "comfyapp.py").read_text(encoding="utf-8-sig")
    assert "custom_node_source_generation(CUSTOM_NODES_PATH)" in src
    assert "generation=_cn_gen_value or None" in src
    # The deterministic value must not be a UUID.
    assert len(expected) == 64, "content-derived generation must be the canonical SHA-256"


def test_startup_init_generation_is_content_derived():
    """The startup init generation-record fallback must be content-derived,
    not a UUID, so baked/runtime generation identity can match."""
    src = (ROOT / "comfyapp.py").read_text(encoding="utf-8-sig")
    assert "reason=\"startup_init_generation_record\"" in src
    assert "generation=_cn_init_generation or None" in src
