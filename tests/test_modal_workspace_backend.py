import asyncio
import importlib.util
import json
import sys
import tempfile
import types
import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch


REPO_ROOT = Path(__file__).resolve().parents[1]
INIT_PATH = REPO_ROOT / "__init__.py"


class _Routes:
    def __init__(self):
        self.handlers = {}

    def _register(self, method, path):
        def decorator(fn):
            self.handlers[(method, path)] = fn
            return fn
        return decorator

    def get(self, path):
        return self._register("GET", path)

    def post(self, path):
        return self._register("POST", path)

    def put(self, path):
        return self._register("PUT", path)

    def delete(self, path):
        return self._register("DELETE", path)

    def patch(self, path):
        return self._register("PATCH", path)


def _make_modal_stub():
    stub = types.ModuleType("modal")
    stub.Image = MagicMock()
    stub.Image.debian_slim.return_value.apt_install.return_value.pip_install.return_value.run_commands.return_value = MagicMock()
    stub.App = MagicMock()
    stub.App.return_value.function = lambda **kw: (lambda f: f)
    stub.App.return_value.cls = lambda **kw: (lambda c: c)
    stub.Volume = MagicMock()
    stub.Volume.from_name.return_value = MagicMock()
    stub.Secret = MagicMock()
    stub.Secret.from_name.return_value = MagicMock()
    stub.Client = types.SimpleNamespace(from_credentials=lambda token_id, token_secret: {"token_id": token_id, "token_secret": token_secret})
    stub.Function = types.SimpleNamespace(from_name=lambda *args, **kwargs: MagicMock())
    stub.Cls = types.SimpleNamespace(from_name=lambda *args, **kwargs: (lambda: MagicMock()))
    stub.web_server = lambda *a, **kw: (lambda f: f)
    stub.enter = lambda **kw: (lambda f: f)
    stub.exit = lambda: (lambda f: f)
    stub.method = lambda *a, **kw: (lambda f: f)
    stub.concurrent = lambda **kw: (lambda c: c)
    return stub


def _make_modal_client_stub():
    stub = types.ModuleType("modal_client")

    async def _async_ok(*args, **kwargs):
        return {"status": "ok"}

    for name in (
        "run_prompt", "run_prompt_stream", "get_object_info", "health_check",
        "download_model", "download_model_stream", "batch_download_models", "list_models",
        "delete_model", "sync_custom_nodes", "refresh_custom_nodes", "get_sync_status",
        "upload_model_to_volume", "upload_model_chunk", "resync_runtime", "get_runtime_state",
        "set_active_warmup_profile",
    ):
        setattr(stub, name, _async_ok)

    setattr(stub, "clear_cache", lambda: None)
    setattr(stub, "set_workspace_resolver", lambda resolver: None)
    setattr(stub, "set_gpu", lambda gpu: None)
    setattr(stub, "get_gpu", lambda: "a10g")
    setattr(stub, "get_default_gpu", lambda: "a10g")
    setattr(stub, "get_available_gpus", lambda: [{"value": "a10g", "label": "A10G"}])
    setattr(stub, "get_handle_cache_stats", lambda: {"hits": 0, "misses": 0})
    setattr(stub, "get_modal_app_name", lambda: "comfyui")
    setattr(stub, "get_modal_class_name", lambda gpu=None: "ComfyAPI")
    setattr(stub, "get_modal_lookup_target", lambda gpu=None, method_name="run_prompt": f"comfyui.ComfyAPI.{method_name}")
    return stub


def _load_init_module():
    routes = _Routes()
    prompt_server = types.SimpleNamespace(instance=types.SimpleNamespace(routes=routes, send_sync=lambda *a, **kw: None, prompt_queue=None))
    server_module = types.ModuleType("server")
    server_module.PromptServer = prompt_server
    execution_module = types.ModuleType("execution")

    original_modules = {name: sys.modules.get(name) for name in ("modal", "modal_client", "server", "execution")}
    sys.modules["modal"] = _make_modal_stub()
    sys.modules["modal_client"] = _make_modal_client_stub()
    sys.modules["server"] = server_module
    sys.modules["execution"] = execution_module
    module_name = f"modal_init_test_{uuid.uuid4().hex}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, str(INIT_PATH))
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        with patch("threading.Thread") as thread_cls:
            thread_cls.return_value.start.return_value = None
            spec.loader.exec_module(module)
        return module, routes.handlers
    finally:
        for name, original in original_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original
        sys.modules.pop(module_name, None)


class _Request:
    def __init__(self, body=None, match_info=None, query=None):
        self._body = body or {}
        self.match_info = match_info or {}
        self.rel_url = types.SimpleNamespace(query=query or {})
        self.content_length = None

    async def json(self):
        return self._body


class ModalWorkspaceBackendTests(unittest.TestCase):
    def test_routes_are_registered(self):
        _, handlers = _load_init_module()
        self.assertIn(("GET", "/comfymodal/workspaces"), handlers)
        self.assertIn(("POST", "/comfymodal/workspaces/active"), handlers)
        self.assertIn(("POST", "/comfymodal/workspaces/swap"), handlers)
        self.assertIn(("GET", "/comfymodal/manifest"), handlers)
        self.assertIn(("POST", "/comfymodal/manifest/repair/scan"), handlers)
        self.assertIn(("POST", "/comfymodal/manifest/repair/apply"), handlers)
        self.assertIn(("POST", "/comfymodal/manifest/repair/delete-placeholder"), handlers)
        self.assertIn(("POST", "/comfymodal/manifest/install"), handlers)
        self.assertIn(("POST", "/comfymodal/workflow-manifest/import"), handlers)

    def test_swap_route_requires_confirmation_when_prompt_running(self):
        module, handlers = _load_init_module()
        handler = handlers[("POST", "/comfymodal/workspaces/swap")]
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.object(module, "_WORKSPACES_FILE", str(Path(tmp) / ".modal_workspaces.json")),
                patch.object(module, "_ACTIVE_REQUEST_IDS", {"prompt-1": 1.0}),
            ):
                registry = module._workspace_store.upsert_workspace(module._WORKSPACES_FILE, "Studio A", "ak-a", "as-a", set_active=True)
                workspace_id = registry["workspaces"][0]["id"]
                response = asyncio.run(handler(_Request({"workspace_id": workspace_id})))
                payload = json.loads(response.text)

        self.assertEqual(payload["status"], "confirm_required")

    def test_manifest_repair_scan_returns_issues(self):
        module, handlers = _load_init_module()
        handler = handlers[("POST", "/comfymodal/manifest/repair/scan")]
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / ".model_manifest.json"
            manifest_path.write_text(json.dumps({
                "manifest_version": 1,
                "entries": [{"folder": "vae", "filename": "flux2-vae.safetensors", "url": "", "source_kind": "direct"}],
            }), encoding="utf-8")
            with patch.object(module, "_MODEL_MANIFEST_FILE", str(manifest_path)):
                response = asyncio.run(handler(_Request()))
                payload = json.loads(response.text)

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["issues"][0]["kind"], "missing_url")

    def test_swap_review_includes_to_remove(self):
        module, handlers = _load_init_module()
        handler = handlers[("POST", "/comfymodal/workspaces/swap")]
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(module, "_WORKSPACES_FILE", str(Path(tmp) / ".modal_workspaces.json")):
                registry = module._workspace_store.upsert_workspace(module._WORKSPACES_FILE, "Studio A", "ak-a", "as-a", set_active=True)
                workspace_id = registry["workspaces"][0]["id"]
                with patch.object(module, "_scan_swap_plan", return_value={
                    "blocking_issues": [],
                    "unresolved": [],
                    "already_present": [],
                    "to_install": [],
                    "to_remove": [{"folder": "loras", "filename": "old.safetensors"}],
                }):
                    response = asyncio.run(handler(_Request({"workspace_id": workspace_id})))
                    payload = json.loads(response.text)

        self.assertEqual(payload["status"], "review_required")
        self.assertEqual(payload["to_remove"], [{"folder": "loras", "filename": "old.safetensors"}])

    def test_swap_confirm_recomputes_plan_from_selected_keys(self):
        module, handlers = _load_init_module()
        handler = handlers[("POST", "/comfymodal/workspaces/swap")]
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(module, "_WORKSPACES_FILE", str(Path(tmp) / ".modal_workspaces.json")):
                registry = module._workspace_store.upsert_workspace(module._WORKSPACES_FILE, "Studio A", "ak-a", "as-a", set_active=True)
                workspace_id = registry["workspaces"][0]["id"]
                scan_plan = {
                    "blocking_issues": [],
                    "unresolved": [],
                    "already_present": [{"folder": "vae", "filename": "kept.safetensors"}],
                    "to_install": [
                        {"url": "https://example.com/a", "filename": "a.safetensors", "save_path": "loras"},
                        {"url": "https://example.com/b", "filename": "b.safetensors", "save_path": "vae"},
                    ],
                    "to_remove": [{"folder": "loras", "filename": "old.safetensors"}],
                }
                with (
                    patch.object(module, "_scan_swap_plan", return_value=scan_plan),
                    patch.object(module, "_run_workspace_swap_job", new=MagicMock(return_value=None)) as run_job,
                    patch("asyncio.create_task") as create_task,
                ):
                    response = asyncio.run(handler(_Request({
                        "workspace_id": workspace_id,
                        "confirm": True,
                        "selected_keys": ["loras/a.safetensors"],
                        "to_install": [{"url": "https://malicious.example.com/x", "filename": "x.safetensors", "save_path": "loras"}],
                        "to_remove": [],
                    })))
                    payload = json.loads(response.text)

        self.assertEqual(payload["status"], "started")
        create_task.assert_called_once()
        run_job.assert_called_once()
        _, _, plan = run_job.call_args.args
        self.assertEqual(plan["to_install"], [{"url": "https://example.com/a", "filename": "a.safetensors", "save_path": "loras"}])
        self.assertEqual(plan["already_present"], [{"folder": "vae", "filename": "kept.safetensors"}])
        self.assertEqual(plan["to_remove"], [{"folder": "loras", "filename": "old.safetensors"}])

    def test_swap_scan_returns_error_when_remote_unavailable(self):
        module, handlers = _load_init_module()
        handler = handlers[("POST", "/comfymodal/workspaces/swap")]
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(module, "_WORKSPACES_FILE", str(Path(tmp) / ".modal_workspaces.json")):
                registry = module._workspace_store.upsert_workspace(module._WORKSPACES_FILE, "Studio A", "ak-a", "as-a", set_active=True)
                workspace_id = registry["workspaces"][0]["id"]
                with patch.object(module, "_scan_swap_plan", return_value={
                    "blocking_issues": [],
                    "unresolved": [],
                    "already_present": [],
                    "to_install": [],
                    "to_remove": [],
                    "remote_status": "unavailable",
                    "remote_error": "Connection refused",
                }):
                    response = asyncio.run(handler(_Request({"workspace_id": workspace_id})))
                    payload = json.loads(response.text)

        self.assertEqual(payload["status"], "error")
        self.assertIn("remote_error", payload)
        self.assertEqual(payload["remote_error"], "Connection refused")
        self.assertIn("Connection refused", payload["message"])
        self.assertNotEqual(payload["status"], "repair_required")

    def test_swap_confirm_returns_error_when_remote_unavailable(self):
        module, handlers = _load_init_module()
        handler = handlers[("POST", "/comfymodal/workspaces/swap")]
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.object(module, "_WORKSPACES_FILE", str(Path(tmp) / ".modal_workspaces.json")),
                patch.object(module, "_ACTIVE_REQUEST_IDS", {}),
            ):
                registry = module._workspace_store.upsert_workspace(module._WORKSPACES_FILE, "Studio A", "ak-a", "as-a", set_active=True)
                workspace_id = registry["workspaces"][0]["id"]
                with patch.object(module, "_scan_swap_plan", return_value={
                    "blocking_issues": [],
                    "unresolved": [],
                    "already_present": [],
                    "to_install": [],
                    "to_remove": [],
                    "remote_status": "unavailable",
                    "remote_error": "get_sync_status timed out",
                }):
                    response = asyncio.run(handler(_Request({
                        "workspace_id": workspace_id,
                        "confirm": True,
                        "selected_keys": [],
                    })))
                    payload = json.loads(response.text)

        self.assertEqual(payload["status"], "error")
        self.assertIn("remote_error", payload)
        self.assertEqual(payload["remote_error"], "get_sync_status timed out")
        self.assertIn("get_sync_status timed out", payload["message"])
        self.assertNotEqual(payload["status"], "repair_required")

    def test_scan_plan_returns_not_deployed_on_missing_app(self):
        module, _ = _load_init_module()
        workspace = {"id": "ws-1", "label": "Studio A", "token_id": "ak-test", "token_secret": "as-test"}
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / ".model_manifest.json"
            manifest_path.write_text(json.dumps({
                "manifest_version": 1,
                "entries": [{
                    "folder": "vae",
                    "filename": "new-vae.safetensors",
                    "url": "https://example.com/new-vae.safetensors",
                    "source_kind": "direct",
                }],
            }), encoding="utf-8")
            with (
                patch.object(module, "_MODEL_MANIFEST_FILE", str(manifest_path)),
                patch.object(module, "get_sync_status", side_effect=RuntimeError(
                    "Modal error: Lookup failed for Function 'get_volume_status' "
                    "from the 'comfyui' app: App 'comfyui' not found in environment 'main'."
                )),
            ):
                result = asyncio.run(module._scan_swap_plan(workspace))

        self.assertEqual(result["remote_status"], "not_deployed")
        self.assertIn("Lookup failed", result["remote_error"])
        self.assertIn("not found", result["remote_error"])
        self.assertEqual(result["to_install"][0]["filename"], "new-vae.safetensors")
        self.assertEqual(result["already_present"], [])

    def test_scan_plan_remains_unavailable_on_other_errors(self):
        module, _ = _load_init_module()
        workspace = {"id": "ws-1", "label": "Studio A", "token_id": "ak-test", "token_secret": "as-test"}
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / ".model_manifest.json"
            manifest_path.write_text(json.dumps({
                "manifest_version": 1, "entries": [],
            }), encoding="utf-8")
            with (
                patch.object(module, "_MODEL_MANIFEST_FILE", str(manifest_path)),
                patch.object(module, "get_sync_status", side_effect=TimeoutError("connection timed out")),
            ):
                result = asyncio.run(module._scan_swap_plan(workspace))

        self.assertEqual(result["remote_status"], "unavailable")
        self.assertEqual(result["remote_error"], "connection timed out")

    def test_swap_review_returns_not_deployed_as_review_required(self):
        module, handlers = _load_init_module()
        handler = handlers[("POST", "/comfymodal/workspaces/swap")]
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(module, "_WORKSPACES_FILE", str(Path(tmp) / ".modal_workspaces.json")):
                registry = module._workspace_store.upsert_workspace(module._WORKSPACES_FILE, "Studio A", "ak-a", "as-a", set_active=True)
                workspace_id = registry["workspaces"][0]["id"]
                with patch.object(module, "_scan_swap_plan", return_value={
                    "blocking_issues": [],
                    "unresolved": [],
                    "already_present": [],
                    "to_install": [],
                    "to_remove": [],
                    "remote_status": "not_deployed",
                    "remote_error": "App 'comfyui' not found in environment 'main'",
                }):
                    response = asyncio.run(handler(_Request({"workspace_id": workspace_id})))
                    payload = json.loads(response.text)

        self.assertEqual(payload["status"], "review_required")
        self.assertNotEqual(payload["status"], "error")

    def test_swap_confirm_passes_force_deploy_when_not_deployed(self):
        module, handlers = _load_init_module()
        handler = handlers[("POST", "/comfymodal/workspaces/swap")]
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.object(module, "_WORKSPACES_FILE", str(Path(tmp) / ".modal_workspaces.json")),
                patch.object(module, "_ACTIVE_REQUEST_IDS", {}),
            ):
                registry = module._workspace_store.upsert_workspace(module._WORKSPACES_FILE, "Studio A", "ak-a", "as-a", set_active=True)
                workspace_id = registry["workspaces"][0]["id"]
                scan_plan = {
                    "blocking_issues": [],
                    "unresolved": [],
                    "already_present": [],
                    "to_install": [],
                    "to_remove": [],
                    "remote_status": "not_deployed",
                    "remote_error": "App 'comfyui' not found",
                }
                with (
                    patch.object(module, "_scan_swap_plan", return_value=scan_plan),
                    patch.object(module, "_run_workspace_swap_job", new=MagicMock(return_value=None)) as run_job,
                    patch("asyncio.create_task") as create_task,
                ):
                    response = asyncio.run(handler(_Request({
                        "workspace_id": workspace_id,
                        "confirm": True,
                        "selected_keys": [],
                    })))
                    payload = json.loads(response.text)

        self.assertEqual(payload["status"], "started")
        create_task.assert_called_once()
        run_job.assert_called_once()
        _, _, plan = run_job.call_args.args
        self.assertTrue(plan.get("force_deploy"))

    def test_ensure_modal_deploy_current_ignores_missing_fingerprint(self):
        module, _ = _load_init_module()
        workspace = {"id": "ws-1", "label": "Studio A"}
        with (
            patch.object(module, "_get_comfyapp_version", return_value="1.2.3"),
            patch.object(module, "_load_workspace_deploy_state", return_value={
                "comfyapp_version": "1.2.3",
                "custom_nodes_fingerprint": "abc123",
            }),
            patch.object(module, "_start_background_deploy") as start_deploy,
        ):
            result = module._ensure_modal_deploy_current(workspace, None)

        self.assertEqual(result, {"started": False, "reason": "already_current"})
        start_deploy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
