"""Focused tests for the V2 custom-node generation identity.

Guards the bounded invariants introduced by the V2 cache-snapshot work:

- The clone filter (``_CUSTOM_NODE_LOCAL_CLONE_RE``) is canonical and
  identical in ``comfyapp.py`` (baked manifest + runtime) and
  ``__init__.py`` (local archive sync), so ``comfyui-modal-agent1-full-trace``
  variants agree everywhere.
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
    """comfyapp and __init__ must use the exact same clone-regex so the
    baked manifest, runtime volume, and local archive sync agree."""
    comfyapp_src = (ROOT / "comfyapp.py").read_text(encoding="utf-8-sig")
    init_src = (ROOT / "__init__.py").read_text(encoding="utf-8-sig")
    # Extract the two regex literals and assert they are byte-identical.
    def _extract(src: str, marker: str) -> str:
        idx = src.index(marker)
        start = src.index("r\"", idx) + 2
        end = src.index("\"", start)
        return src[start:end]
    app_re = _extract(comfyapp_src, "_CUSTOM_NODE_LOCAL_CLONE_RE = re.compile(")
    init_re = _extract(init_src, "_CUSTOM_NODE_LOCAL_CLONE_RE = re.compile(")
    assert app_re == init_re, (
        f"clone regex diverged:\n comfyapp={app_re!r}\n __init__={init_re!r}"
    )
    import re
    canonical = re.compile(app_re, re.IGNORECASE)
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
    """The local archive-sync filter must deny agent/worktree clones just
    like the baked manifest filter (agent1-full-trace variants included)."""
    init_src = (ROOT / "__init__.py").read_text(encoding="utf-8-sig")
    assert "_CUSTOM_NODE_LOCAL_CLONE_RE.fullmatch(node_dir)" in init_src
    assert "local_agent_or_worktree_clone" in init_src


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


def test_generation_preserves_real_mismatches():
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
    assert g2 != g3


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
    assert len(expected) == 32, "content-derived generation must be a 32-hex md5"


def test_startup_init_generation_is_content_derived():
    """The startup init generation-record fallback must be content-derived,
    not a UUID, so baked/runtime generation identity can match."""
    src = (ROOT / "comfyapp.py").read_text(encoding="utf-8-sig")
    assert "reason=\"startup_init_generation_record\"" in src
    assert "generation=_cn_init_generation or None" in src
