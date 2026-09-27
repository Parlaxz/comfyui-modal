from __future__ import annotations

import importlib.util
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
    name = f"comfyapp_cache_boundary_{uuid.uuid4().hex}"
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


def test_runtime_revision_does_not_participate_in_dependency_key():
    module = _load_comfyapp()
    with tempfile.TemporaryDirectory() as tmp:
        req = Path(tmp) / "requirements"
        req.mkdir()
        (req / "node" ).mkdir()
        (req / "node" / "requirements.txt").write_bytes(b"numpy\r\n")
        key = module._compute_deterministic_context_hash(str(req))["context_hash"]
        module._V2_RUNTIME_REVISION = "first"
        first = module._build_v2_dependency_cache_identity(key)["dependency_key"]
        module._V2_RUNTIME_REVISION = "second"
        second = module._build_v2_dependency_cache_identity(key)["dependency_key"]
    assert first == second


def test_dependency_context_is_order_and_mtime_stable_and_excludes_generated_files():
    module = _load_comfyapp()
    with tempfile.TemporaryDirectory() as tmp:
        req = Path(tmp) / "requirements"
        node = req / "node"
        (node / "src" / "sam3").mkdir(parents=True)
        (node / "build" / "lib").mkdir(parents=True)
        (node / "logs").mkdir()
        (node / "requirements.txt").write_text("numpy\n", encoding="utf-8")
        (node / "src" / "sam3" / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
        (node / "src" / "sam3" / "trace_output.jsonl").write_text("generated\n", encoding="utf-8")
        (node / "build" / "lib" / "generated.py").write_text("generated\n", encoding="utf-8")
        (node / "logs" / "install.log").write_text("generated\n", encoding="utf-8")
        first = module._compute_deterministic_context_hash(str(req))
        assert "node/src/sam3/__init__.py" in first["file_hashes"]
        assert not any("build/" in path or "logs/" in path or path.endswith(".jsonl") for path in first["file_hashes"])
        (node / "build" / "lib" / "generated.py").touch()
        (node / "logs" / "install.log").touch()
        second = module._compute_deterministic_context_hash(str(req))
    assert first["context_hash"] == second["context_hash"]


def test_requirements_and_sam3_source_change_dependency_key():
    module = _load_comfyapp()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "custom_nodes"
        node = root / "comfyui-sam3"
        (node / "src" / "sam3").mkdir(parents=True)
        (node / "requirements.txt").write_text("-e ./src/sam3\n", encoding="utf-8")
        source_a = module._compute_deterministic_context_hash(str(root))
        (node / "src" / "sam3" / "runtime.py").write_text("VALUE = 1\n", encoding="utf-8")
        source_b = module._compute_deterministic_context_hash(str(root))
        assert source_a["context_hash"] != source_b["context_hash"]
        (node / "requirements.txt").write_text("-e ./src/sam3\nnumpy\n", encoding="utf-8")
        source_c = module._compute_deterministic_context_hash(str(root))
    assert source_b["context_hash"] != source_c["context_hash"]
