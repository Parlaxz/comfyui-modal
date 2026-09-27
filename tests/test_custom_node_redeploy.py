import asyncio
import importlib.util
import json
import sys
import tempfile
import types
import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open


REPO_ROOT = Path(__file__).resolve().parents[1]
INIT_PATH = REPO_ROOT / "__init__.py"


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
    setattr(stub, "method", lambda *a, **kw: (lambda f: f))
    setattr(stub, "concurrent", lambda **kw: (lambda c: c))
    return stub


def _make_modal_client_stub():
    stub = types.ModuleType("modal_client")

    async def _async_ok(*args, **kwargs):
        return {"status": "ok"}

    def _noop(*args, **kwargs):
        return None

    for name in (
        "run_prompt",
        "run_prompt_stream",
        "get_object_info",
        "health_check",
        "download_model",
        "download_model_stream",
        "batch_download_models",
        "list_models",
        "delete_model",
        "refresh_custom_nodes",
        "get_sync_status",
        "upload_model_to_volume",
        "upload_model_chunk",
        "clear_cache",
        "set_active_warmup_profile",
        "set_gpu",
        "get_handle_cache_stats",
    ):
        setattr(stub, name, _noop)

    setattr(stub, "sync_custom_nodes", _async_ok)
    setattr(stub, "resync_runtime", _async_ok)
    setattr(stub, "get_runtime_state", _async_ok)
    setattr(stub, "get_default_gpu", lambda: "a10g")
    setattr(stub, "get_gpu", lambda: "a10g")
    setattr(stub, "get_available_gpus", lambda: [{"value": "a10g", "label": "A10G"}])
    setattr(stub, "get_modal_app_name", lambda: "comfyui")
    setattr(stub, "get_modal_class_name", lambda gpu=None: "ComfyAPI")
    setattr(stub, "get_modal_lookup_target", lambda gpu=None, method_name="run_prompt": f"comfyui.ComfyAPI.{method_name}")
    return stub


class _PublicationVolume:
    def __init__(self, name="comfyui-custom-nodes"):
        self.name = name
        self.files = {}

    def read_file(self, path):
        if path not in self.files:
            raise FileNotFoundError(path)
        return iter((self.files[path],))

    class _Batch:
        def __init__(self, volume):
            self.volume = volume

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def put_file(self, handle, path):
            self.volume.files[path] = handle.read()

    def batch_upload(self, *, force):
        assert force is True
        return self._Batch(self)


def _load_init_module():
    original_modal = sys.modules.pop("modal", None)
    original_modal_client = sys.modules.pop("modal_client", None)
    sys.modules["modal"] = _make_modal_stub()
    sys.modules["modal_client"] = _make_modal_client_stub()
    module_name = f"modal_init_test_{uuid.uuid4().hex}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, str(INIT_PATH))
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


class CustomNodeRedeployHelperTests(unittest.TestCase):
    def test_custom_node_fingerprint_is_deterministic(self):
        module = _load_init_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "custom_nodes"
            node1 = root / "node-a"
            node2 = root / "node-b"
            node1.mkdir(parents=True)
            node2.mkdir(parents=True)
            (node1 / "requirements.txt").write_text("torch\n", encoding="utf-8")
            (node2 / "requirements.txt").write_text("diffusers\n", encoding="utf-8")

            result1 = module._build_custom_node_fingerprint(str(root))
            result2 = module._build_custom_node_fingerprint(str(root))

        self.assertEqual(result1, result2)

    def test_custom_node_fingerprint_changes_when_requirements_change(self):
        module = _load_init_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "custom_nodes"
            node = root / "comfyui-easy-use"
            node.mkdir(parents=True)
            (node / "requirements.txt").write_text("numpy==1.26.4\n", encoding="utf-8")

            before = module._build_custom_node_fingerprint(str(root))

            (node / "requirements.txt").write_text("numpy==2.0.0\n", encoding="utf-8")
            after = module._build_custom_node_fingerprint(str(root))

        self.assertNotEqual(before, after)

    def test_custom_node_fingerprint_ignores_non_requirements_file_edits(self):
        module = _load_init_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "custom_nodes"
            node = root / "comfyui-easy-use"
            node.mkdir(parents=True)
            (node / "requirements.txt").write_text("numpy==1.26.4\n", encoding="utf-8")
            (node / "nodes.py").write_text("A = 1\n", encoding="utf-8")

            before = module._build_custom_node_fingerprint(str(root))

            (node / "nodes.py").write_text("A = 2\n", encoding="utf-8")
            after = module._build_custom_node_fingerprint(str(root))

        self.assertEqual(before, after)

    def test_load_deploy_state_falls_back_to_legacy_version_file(self):
        module = _load_init_module()
        with tempfile.TemporaryDirectory() as tmp:
            legacy = Path(tmp) / ".deployed_version"
            state_json = Path(tmp) / ".deployed_state.json"
            legacy.write_text("2.14.2", encoding="utf-8")

            with (
                patch.object(module, "_DEPLOY_STATE_FILE", str(legacy)),
                patch.object(module, "_DEPLOY_STATE_JSON_FILE", str(state_json)),
            ):
                state = module._load_deploy_state()

        self.assertEqual(state["comfyapp_version"], "2.14.2")
        self.assertIsNone(state["custom_nodes_fingerprint"])

    def test_save_deploy_state_writes_version_and_fingerprint_json(self):
        module = _load_init_module()
        with tempfile.TemporaryDirectory() as tmp:
            state_json = Path(tmp) / ".deployed_state.json"
            with patch.object(module, "_DEPLOY_STATE_JSON_FILE", str(state_json)):
                module._save_deploy_state("2.14.2", "abc123")

            payload = json.loads(state_json.read_text(encoding="utf-8"))

        self.assertEqual(payload, {
            "comfyapp_version": "2.14.2",
            "custom_nodes_fingerprint": "abc123",
        })


class CustomNodeRedeployFlowTests(unittest.TestCase):
    def test_ensure_modal_deploy_current_starts_when_fingerprint_changes(self):
        module = _load_init_module()
        with (
            patch.object(module, "_get_comfyapp_version", return_value="2.14.2"),
            patch.object(module, "_load_deploy_state", return_value={
                "comfyapp_version": "2.14.2",
                "custom_nodes_fingerprint": "old-fp",
            }),
            patch.object(module, "_start_background_deploy", return_value={
                "started": True,
                "reason": "custom_nodes_changed",
            }) as start_mock,
        ):
            result = module._ensure_modal_deploy_current("new-fp")

        self.assertEqual(result, {"started": True, "reason": "custom_nodes_changed"})
        start_mock.assert_called_once_with(custom_nodes_fingerprint="new-fp", reason="custom_nodes_changed")

    def test_ensure_modal_deploy_current_starts_when_version_changes(self):
        module = _load_init_module()
        with (
            patch.object(module, "_get_comfyapp_version", return_value="3.0.0"),
            patch.object(module, "_load_deploy_state", return_value={
                "comfyapp_version": "2.14.2",
                "custom_nodes_fingerprint": "some-fp",
            }),
            patch.object(module, "_start_background_deploy", return_value={
                "started": True,
                "reason": "version_changed",
            }) as start_mock,
        ):
            result = module._ensure_modal_deploy_current("some-fp")

        self.assertEqual(result, {"started": True, "reason": "version_changed"})
        start_mock.assert_called_once_with(custom_nodes_fingerprint="some-fp", reason="version_changed")

    def test_ensure_modal_deploy_current_skips_when_version_and_fingerprint_match(self):
        module = _load_init_module()
        with (
            patch.object(module, "_get_comfyapp_version", return_value="2.14.2"),
            patch.object(module, "_load_deploy_state", return_value={
                "comfyapp_version": "2.14.2",
                "custom_nodes_fingerprint": "same-fp",
            }),
            patch.object(module, "_start_background_deploy") as start_mock,
        ):
            result = module._ensure_modal_deploy_current("same-fp")

        self.assertEqual(result, {"started": False, "reason": "already_current"})
        start_mock.assert_not_called()

    def test_start_background_deploy_refuses_second_concurrent_deploy(self):
        module = _load_init_module()
        setattr(module, "_deploy_status", {"state": "deploying", "message": "Running modal deploy..."})

        result = module._start_background_deploy(custom_nodes_fingerprint="fp", reason="custom_nodes_changed")

        self.assertEqual(result, {"started": False, "reason": "deploy_already_running"})

    def test_run_deploy_background_persists_fingerprint_after_success(self):
        module = _load_init_module()
        completed = types.SimpleNamespace(returncode=0, stdout="ok", stderr="")

        with (
            patch.object(module, "_find_modal_executable", return_value="modal"),
            patch.object(module.subprocess, "run", return_value=completed),
            patch.object(module, "_get_comfyapp_version", return_value="2.14.2"),
            patch.object(module, "_save_deploy_state") as save_mock,
            patch.object(module, "clear_cache"),
            patch("builtins.open", new_callable=mock_open),
        ):
            module._run_deploy_background(custom_nodes_fingerprint="fp-123")

        save_mock.assert_called_once_with("2.14.2", "fp-123")

    def test_sync_custom_nodes_and_maybe_deploy_reports_started_flag(self):
        module = _load_init_module()
        workspace = {"id": "ws-1", "label": "test", "token_id": "id", "token_secret": "secret"}

        async def fake_refresh(scope: str, workspace: dict):
            return {"status": "ok", "scope": scope}

        with tempfile.TemporaryDirectory() as tmp:
            cn_root = Path(tmp) / "custom_nodes"
            node = cn_root / "comfyui-easy-use"
            node.mkdir(parents=True)
            (node / "requirements.txt").write_text("numpy==1.26.4\n", encoding="utf-8")

            with (
                patch.object(module, "_publish_custom_nodes_or_skip", return_value={
                    "status": "ok",
                    "publication": {"verified_publication": True},
                }),
                patch.object(module, "resync_runtime", side_effect=fake_refresh),
                patch.object(module, "_ensure_modal_deploy_current", return_value={
                    "started": True,
                    "reason": "custom_nodes_changed",
                }),
            ):
                result = asyncio.run(module._sync_custom_nodes_and_maybe_deploy(str(cn_root), workspace))

        self.assertEqual(result["deploy"], {"started": True, "reason": "custom_nodes_changed"})
        self.assertEqual(result["refresh"], {"status": "ok", "scope": "custom_nodes"})

    def test_sync_custom_nodes_and_maybe_deploy_skips_deploy_on_upload_error(self):
        module = _load_init_module()
        workspace = {"id": "ws-1", "label": "test", "token_id": "id", "token_secret": "secret"}

        with tempfile.TemporaryDirectory() as tmp:
            cn_root = Path(tmp) / "custom_nodes"
            (cn_root / "comfyui-easy-use").mkdir(parents=True)

            with (
                patch.object(module, "_publish_custom_nodes_or_skip", return_value={
                    "status": "error", "message": "upload failed"
                }),
                patch.object(module, "_ensure_modal_deploy_current") as ensure_mock,
            ):
                result = asyncio.run(module._sync_custom_nodes_and_maybe_deploy(str(cn_root), workspace))

        self.assertNotIn("deploy", result)
        ensure_mock.assert_not_called()

    def test_exact_publication_skips_archive_publisher_deploy_and_refresh(self):
        module = _load_init_module()
        workspace = {"id": "ws-1", "label": "test", "token_id": "id", "token_secret": "secret"}
        from tools.v2_control.custom_nodes import (
            RECEIPT_PATH,
            PublicationReceipt,
            prepare_publication,
            publish_or_skip as shared_publish_or_skip,
        )

        volume = _PublicationVolume()

        with tempfile.TemporaryDirectory() as tmp:
            cn_root = Path(tmp) / "custom_nodes"
            node = cn_root / "comfyui-easy-use"
            node.mkdir(parents=True)
            (node / "main.py").write_bytes(b"main")
            identity, _archive, _files = prepare_publication(cn_root)
            volume.files[RECEIPT_PATH] = PublicationReceipt.create(
                identity, volume.name
            ).to_bytes()

            async def fake_publish(_root, **kwargs):
                self.assertEqual(kwargs["volume_name"], volume.name)
                self.assertIs(kwargs["workspace"], workspace)
                return await shared_publish_or_skip(
                    _root, volume=volume, **kwargs
                )

            with (
                patch.object(module, "publish_or_skip", side_effect=fake_publish),
                patch.object(module, "_build_custom_nodes_archive") as archive_mock,
                patch("tools.v2_control.custom_nodes.build_archive", side_effect=AssertionError("archive built")),
                patch.object(module, "sync_custom_nodes") as publisher_mock,
                patch.object(module, "_ensure_modal_deploy_current") as deploy_mock,
                patch.object(module, "resync_runtime") as refresh_mock,
            ):
                result = asyncio.run(module._sync_custom_nodes_and_maybe_deploy(str(cn_root), workspace))

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["publication"]["reason"], "exact_match")
        archive_mock.assert_not_called()
        publisher_mock.assert_not_called()
        deploy_mock.assert_not_called()
        refresh_mock.assert_not_called()

    def test_verified_publication_publishes_then_deploys_and_refreshes(self):
        module = _load_init_module()
        workspace = {"id": "ws-1", "label": "test", "token_id": "id", "token_secret": "secret"}
        from tools.v2_control.custom_nodes import (
            GENERATION_RECORD_PATH,
            prepare_publication,
            publish_or_skip as shared_publish_or_skip,
        )

        volume = _PublicationVolume()
        publisher_calls = []

        async def fake_sync(archive_data: bytes, workspace: dict):
            publisher_calls.append((archive_data, workspace))
            volume.files[GENERATION_RECORD_PATH] = json.dumps({
                "schema_version": 2,
                "content_generation": prepare_publication(cn_root)[0].content_generation,
            }).encode()
            return {
                "status": "ok",
                "content_generation": prepare_publication(cn_root)[0].content_generation,
            }

        async def fake_refresh(scope: str, workspace: dict):
            return {"status": "ok", "scope": scope}

        with tempfile.TemporaryDirectory() as tmp:
            cn_root = Path(tmp) / "custom_nodes"
            node = cn_root / "comfyui-easy-use"
            node.mkdir(parents=True)
            (node / "main.py").write_bytes(b"main")

            async def fake_publish(_root, **kwargs):
                return await shared_publish_or_skip(
                    _root, volume=volume, **kwargs
                )

            with (
                patch.object(module, "publish_or_skip", side_effect=fake_publish),
                patch.object(module, "_build_custom_nodes_archive") as archive_mock,
                patch.object(module, "sync_custom_nodes", side_effect=fake_sync),
                patch.object(module, "_ensure_modal_deploy_current", return_value={
                    "started": True, "reason": "custom_nodes_changed"
                }) as deploy_mock,
                patch.object(module, "resync_runtime", side_effect=fake_refresh) as refresh_mock,
            ):
                result = asyncio.run(module._sync_custom_nodes_and_maybe_deploy(str(cn_root), workspace))

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["publication"]["reason"], "published_verified")
        self.assertEqual(len(publisher_calls), 1)
        self.assertIs(publisher_calls[0][1], workspace)
        self.assertTrue(publisher_calls[0][0])
        archive_mock.assert_not_called()
        deploy_mock.assert_called_once()
        refresh_mock.assert_called_once_with("custom_nodes", workspace=workspace)


    def test_maybe_auto_deploy_skips_in_runtime_container(self):
        module = _load_init_module()
        with (
            patch.object(module.os, "environ", {"COMFYMODAL_RUNTIME": "1"}),
            patch.object(module, "_ensure_modal_deploy_current") as ensure_mock,
        ):
            module._maybe_auto_deploy()

        ensure_mock.assert_not_called()

    def test_maybe_auto_deploy_skips_when_modal_cli_not_found(self):
        module = _load_init_module()
        with (
            patch.object(module.os, "environ", {}),
            patch.object(module, "_find_modal_executable", return_value=None),
            patch.object(module, "_ensure_modal_deploy_current") as ensure_mock,
        ):
            module._maybe_auto_deploy()

        ensure_mock.assert_not_called()

    def test_maybe_auto_deploy_runs_when_enabled(self):
        module = _load_init_module()
        env = {
            "COMFYMODAL_ENABLE_REMOTE_BACKGROUND_DEPLOY": "1",
        }
        with (
            patch.object(module.os, "environ", env),
            patch.object(module, "_find_modal_executable", return_value="modal"),
            patch.object(module, "_build_custom_node_fingerprint", return_value="fp"),
            patch.object(module, "_custom_nodes_root", return_value="custom_nodes"),
            patch.object(module, "_ensure_modal_deploy_current", return_value={"started": False, "reason": "already_current"}) as ensure_mock,
        ):
            module._maybe_auto_deploy()

        ensure_mock.assert_called_once_with("fp")

    def test_build_generation_invocation_plan_marks_stale_state(self):
        module = _load_init_module()
        with (
            patch.object(module, "_get_comfyapp_version", return_value="2.16.0"),
            patch.object(module, "_read_deploy_state_details", return_value={
                "path": "state.json",
                "loaded": True,
                "source": "json",
                "parse_error": "",
                "comfyapp_version": "2.14.3",
                "custom_nodes_fingerprint": "old",
            }),
            patch.object(module, "_build_custom_node_fingerprint_status", return_value={
                "custom_nodes_root": "custom_nodes",
                "available": True,
                "fingerprint": "new",
                "error": "",
            }),
        ):
            plan = module._build_generation_invocation_plan("a10g", stream=True)

        self.assertEqual(plan["invocation_mode"], "deployed_lookup")
        self.assertTrue(plan["version_changed"])
        self.assertTrue(plan["custom_nodes_fingerprint_changed"])

    def test_get_comfyapp_version_parses_constant_without_executing_module(self):
        module = _load_init_module()
        with tempfile.TemporaryDirectory() as tmp:
            comfyapp_path = Path(tmp) / "comfyapp.py"
            comfyapp_path.write_text(
                'COMFYAPP_VERSION = "9.9.9"\nraise RuntimeError("should not execute")\n',
                encoding="utf-8",
            )
            with patch.object(module, "_COMFYAPP_PATH", str(comfyapp_path)):
                version = module._get_comfyapp_version()

        self.assertEqual(version, "9.9.9")


if __name__ == "__main__":
    unittest.main()
