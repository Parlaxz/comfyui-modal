from __future__ import annotations

import importlib.util
import os
import sys
import types
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
IMPORT_PATH = "/root/comfy/ComfyUI/custom_nodes"
pytestmark = pytest.mark.fast_unit


class _FakeImage:
    def __init__(self):
        self.calls: list[tuple[str, tuple, dict]] = []

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return self

        return record


def _modal_stub(image):
    modal = types.ModuleType("modal")
    image_factory = types.SimpleNamespace(
        from_registry=lambda *args, **kwargs: image,
        debian_slim=lambda *args, **kwargs: image,
    )
    modal.Image = image_factory
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


def _load_comfyapp(delivery: str | None):
    old_delivery = os.environ.get("COMFYMODAL_CUSTOM_NODE_DELIVERY")
    if delivery is None:
        os.environ.pop("COMFYMODAL_CUSTOM_NODE_DELIVERY", None)
    else:
        os.environ["COMFYMODAL_CUSTOM_NODE_DELIVERY"] = delivery
    old_modal = sys.modules.pop("modal", None)
    image = _FakeImage()
    sys.modules["modal"] = _modal_stub(image)
    name = f"comfyapp_delivery_{uuid.uuid4().hex}"
    try:
        spec = importlib.util.spec_from_file_location(name, ROOT / "comfyapp.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module, image
    finally:
        sys.modules.pop(name, None)
        if old_modal is None:
            sys.modules.pop("modal", None)
        else:
            sys.modules["modal"] = old_modal
        if old_delivery is None:
            os.environ.pop("COMFYMODAL_CUSTOM_NODE_DELIVERY", None)
        else:
            os.environ["COMFYMODAL_CUSTOM_NODE_DELIVERY"] = old_delivery


def _custom_node_copy_calls(image):
    return [
        call
        for call in image.calls
        if call[0] == "add_local_dir"
        and len(call[1]) >= 2
        and (
            call[1][1] == IMPORT_PATH
            or str(call[1][1]).startswith(IMPORT_PATH + "/")
        )
    ]


def test_default_delivery_is_image_and_emits_custom_node_source_copy():
    module, image = _load_comfyapp(None)
    assert module.CUSTOM_NODE_DELIVERY == "image"
    assert _custom_node_copy_calls(image)


def test_volume_delivery_skips_custom_node_source_copy():
    module, image = _load_comfyapp("volume")
    assert module.CUSTOM_NODE_DELIVERY == "volume"
    assert not _custom_node_copy_calls(image)


def test_invalid_delivery_warns_and_falls_back_to_image(capsys):
    module, image = _load_comfyapp("not-a-delivery")
    assert module.CUSTOM_NODE_DELIVERY == "image"
    assert "invalid COMFYMODAL_CUSTOM_NODE_DELIVERY" in capsys.readouterr().out
    assert _custom_node_copy_calls(image)


def test_volume_mode_mounts_volume_only_at_import_path():
    from comfymodal_runtime import modal_app

    class FakeApp:
        def __init__(self):
            self.kwargs = None

        def cls(self, **kwargs):
            self.kwargs = kwargs
            return lambda cls: cls

    app = FakeApp()
    custom_volume = object()
    resources = {
        "app": app,
        "models_volume": object(),
        "custom_nodes_volume": custom_volume,
        "runtime_state_volume": object(),
    }
    spec = modal_app.ModalRuntimeSpec()
    with patch.object(modal_app, "CUSTOM_NODE_DELIVERY", "volume"), \
         patch.object(modal_app, "_modal", types.SimpleNamespace(concurrent=lambda **_: lambda cls: cls)), \
         patch.object(modal_app, "_build_decorated_v2_class", return_value=object):
        modal_app._register_remote_entrypoint(resources, spec)
    volumes = app.kwargs["volumes"]
    custom_mounts = [path for path, volume in volumes.items() if volume is custom_volume]
    assert custom_mounts == [modal_app.CUSTOM_NODES_IMPORT_PATH]
    assert spec.custom_nodes_path not in volumes


def test_image_mode_keeps_legacy_custom_nodes_mount():
    from comfymodal_runtime import modal_app

    class FakeApp:
        def __init__(self):
            self.kwargs = None

        def cls(self, **kwargs):
            self.kwargs = kwargs
            return lambda cls: cls

    app = FakeApp()
    custom_volume = object()
    resources = {
        "app": app,
        "models_volume": object(),
        "custom_nodes_volume": custom_volume,
        "runtime_state_volume": object(),
    }
    spec = modal_app.ModalRuntimeSpec()
    with patch.object(modal_app, "CUSTOM_NODE_DELIVERY", "image"), \
         patch.object(modal_app, "_modal", types.SimpleNamespace(concurrent=lambda **_: lambda cls: cls)), \
         patch.object(modal_app, "_build_decorated_v2_class", return_value=object):
        modal_app._register_remote_entrypoint(resources, spec)
    volumes = app.kwargs["volumes"]
    assert volumes[spec.custom_nodes_path] is custom_volume
    assert modal_app.CUSTOM_NODES_IMPORT_PATH not in volumes


def test_volume_mode_creates_legacy_compatibility_symlink(tmp_path):
    from comfymodal_runtime import modal_app

    mounted_path = tmp_path / "comfy" / "ComfyUI" / "custom_nodes"
    mounted_path.mkdir(parents=True)
    legacy_path = tmp_path / "custom_nodes_vol"
    created: dict[str, object] = {}
    realpath = os.path.realpath

    def fake_symlink(target, link, *, target_is_directory):
        created.update(
            target=target,
            link=link,
            target_is_directory=target_is_directory,
        )

    def fake_realpath(path):
        if path == str(legacy_path):
            return realpath(mounted_path)
        return realpath(path)

    with patch.object(modal_app, "CUSTOM_NODE_DELIVERY", "volume"), \
         patch.object(modal_app, "CUSTOM_NODES_IMPORT_PATH", str(mounted_path)), \
         patch.object(modal_app, "CUSTOM_NODES_PATH", str(legacy_path)), \
         patch.object(modal_app.os, "symlink", side_effect=fake_symlink), \
         patch.object(modal_app.os.path, "realpath", side_effect=fake_realpath):
        modal_app._ensure_custom_nodes_compat_symlink()
    assert created == {
        "target": str(mounted_path),
        "link": str(legacy_path),
        "target_is_directory": True,
    }
    assert fake_realpath(str(legacy_path)) == fake_realpath(str(mounted_path))


def test_volume_mode_symlink_failure_fails_closed(tmp_path):
    from comfymodal_runtime import modal_app

    mounted_path = tmp_path / "custom_nodes"
    mounted_path.mkdir()
    legacy_path = tmp_path / "custom_nodes_vol"
    legacy_path.mkdir()
    with patch.object(modal_app, "CUSTOM_NODE_DELIVERY", "volume"), \
         patch.object(modal_app, "CUSTOM_NODES_IMPORT_PATH", str(mounted_path)), \
         patch.object(modal_app, "CUSTOM_NODES_PATH", str(legacy_path)):
        with pytest.raises(RuntimeError, match="compatibility symlink setup failed"):
            modal_app._ensure_custom_nodes_compat_symlink()


def test_volume_gate_fails_closed_for_empty_volume_and_generation_mismatch():
    from comfyapp import decide_custom_node_volume_gate

    missing = decide_custom_node_volume_gate(
        volume_entries=None,
        importable_node_count=None,
        generation_record={"content_generation": "expected"},
        expected_generation="expected",
    )
    empty = decide_custom_node_volume_gate(
        volume_entries=[],
        importable_node_count=0,
        generation_record={"content_generation": "expected"},
        expected_generation="expected",
    )
    mismatch = decide_custom_node_volume_gate(
        volume_entries=["node"],
        importable_node_count=1,
        generation_record={"content_generation": "published"},
        expected_generation="expected",
    )
    missing_generation = decide_custom_node_volume_gate(
        volume_entries=["node"],
        importable_node_count=1,
        generation_record=None,
        expected_generation="expected",
    )
    no_importable_node = decide_custom_node_volume_gate(
        volume_entries=["node"],
        importable_node_count=0,
        generation_record={"content_generation": "expected"},
        expected_generation="expected",
    )
    assert not missing["ok"]
    assert "volume_directory_missing_or_unreadable" in missing["reasons"]
    assert not empty["ok"]
    assert "volume_directory_empty" in empty["reasons"]
    assert "no_importable_custom_node_init_py" in empty["reasons"]
    assert not mismatch["ok"]
    assert "generation_mismatch" in mismatch["reasons"]
    assert not missing_generation["ok"]
    assert "generation_record_missing_or_unreadable" in missing_generation["reasons"]
    assert not no_importable_node["ok"]
    assert "no_importable_custom_node_init_py" in no_importable_node["reasons"]


def test_volume_gate_is_before_comfyui_custom_node_discovery():
    runtime_source = (ROOT / "comfymodal_runtime" / "modal_app.py").read_text(encoding="utf-8")
    gate = runtime_source.index("self._verify_custom_node_volume_before_startup()")
    bootstrap = runtime_source.index("state = self.bootstrap.startup(snapshot=True, trace=trace)")
    comfy_source = (ROOT / "comfyapp.py").read_text(encoding="utf-8")
    backend = comfy_source.index("def _start_in_process_backend")
    discovery = comfy_source.index("import nodes", backend)
    assert gate < bootstrap
    assert "before ComfyUI node discovery" in runtime_source
    assert discovery > backend
