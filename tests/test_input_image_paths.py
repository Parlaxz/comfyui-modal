import base64
import importlib.util
import sys
import tempfile
import types
import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch


REPO_ROOT = Path(__file__).resolve().parents[1]
COMFYAPP_PATH = REPO_ROOT / "comfyapp.py"


def _make_modal_stub():
    stub = types.ModuleType("modal")
    image = MagicMock()
    image.debian_slim.return_value.apt_install.return_value.pip_install.return_value.run_commands.return_value = MagicMock()
    app = MagicMock()
    app.return_value.function = lambda **kw: (lambda f: f)
    app.return_value.cls = lambda **kw: (lambda c: c)
    volume = MagicMock()
    volume.from_name.return_value = MagicMock()
    secret = MagicMock()
    secret.from_name.return_value = MagicMock()

    setattr(stub, "Image", image)
    setattr(stub, "App", app)
    setattr(stub, "Volume", volume)
    setattr(stub, "Secret", secret)
    setattr(stub, "web_server", lambda *a, **kw: (lambda f: f))
    setattr(stub, "enter", lambda **kw: (lambda f: f))
    setattr(stub, "exit", lambda: (lambda f: f))
    setattr(stub, "method", lambda: (lambda f: f))
    setattr(stub, "concurrent", lambda **kw: (lambda c: c))
    return stub


def _load_comfyapp_module():
    original_modal = sys.modules.pop("modal", None)
    sys.modules["modal"] = _make_modal_stub()
    module_name = f"comfyapp_test_{uuid.uuid4().hex}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, str(COMFYAPP_PATH))
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if original_modal is not None:
            sys.modules["modal"] = original_modal
        else:
            sys.modules.pop("modal", None)
        sys.modules.pop(module_name, None)


def _make_modal_client_stub():
    stub = types.ModuleType("modal_client")

    def _noop(*args, **kwargs):
        return None

    for name in (
        "run_prompt",
        "get_object_info",
        "health_check",
        "download_model",
        "batch_download_models",
        "list_models",
        "delete_model",
        "set_gpu",
        "get_gpu",
        "get_default_gpu",
        "get_available_gpus",
        "sync_custom_nodes",
        "refresh_custom_nodes",
        "get_sync_status",
        "upload_model_to_volume",
        "upload_model_chunk",
        "clear_cache",
        "resync_runtime",
        "get_runtime_state",
    ):
        setattr(stub, name, _noop)

    setattr(stub, "get_default_gpu", lambda: "a10g")
    setattr(stub, "get_gpu", lambda: "a10g")
    setattr(stub, "get_available_gpus", lambda: [{"value": "a10g", "label": "A10G"}])
    return stub


def _load_init_module():
    original_modal = sys.modules.pop("modal", None)
    original_modal_client = sys.modules.pop("modal_client", None)
    sys.modules["modal"] = _make_modal_stub()
    sys.modules["modal_client"] = _make_modal_client_stub()
    module_name = f"modal_init_test_{uuid.uuid4().hex}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, str(REPO_ROOT / "__init__.py"))
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        with patch("threading.Thread") as thread_cls:
            thread_cls.return_value.start.return_value = None
            spec.loader.exec_module(module)
        return module
    finally:
        if original_modal is not None:
            sys.modules["modal"] = original_modal
        else:
            sys.modules.pop("modal", None)
        if original_modal_client is not None:
            sys.modules["modal_client"] = original_modal_client
        else:
            sys.modules.pop("modal_client", None)
        sys.modules.pop(module_name, None)


class InputImagePathTests(unittest.TestCase):
    def test_collect_input_images_resolves_output_annotation(self):
        modal_init = _load_init_module()

        payload = b"annotated-output-image"
        workflow = {
            "76": {
                "class_type": "LoadImage",
                "inputs": {"image": "clip.png [output]"},
            }
        }

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "output"
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "clip.png").write_bytes(payload)

            with patch.object(modal_init, "_COMFYUI_ROOT", tmp):
                images = modal_init._collect_input_images(workflow)

        self.assertEqual(list(images.keys()), ["clip.png [output]"])
        self.assertEqual(base64.b64decode(images["clip.png [output]"]), payload)

    def test_materialize_input_images_preserves_relative_subdirs(self):
        module = _load_comfyapp_module()
        payload = b"nested-input-image"

        with tempfile.TemporaryDirectory() as tmp:
            module._materialize_input_images(
                {"nested/clip.png": base64.b64encode(payload).decode("ascii")},
                comfy_root=tmp,
            )

            self.assertTrue((Path(tmp) / "input" / "nested" / "clip.png").is_file())
            self.assertEqual((Path(tmp) / "input" / "nested" / "clip.png").read_bytes(), payload)


if __name__ == "__main__":
    unittest.main()
