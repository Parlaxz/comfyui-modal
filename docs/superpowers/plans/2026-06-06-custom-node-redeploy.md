# Custom-Node Redeploy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically start a background `modal deploy` after custom-node sync when the top-level node set or any synced `requirements.txt` changes.

**Architecture:** Keep the implementation local to `__init__.py` so the existing sync route, deploy thread, and deploy status flow stay intact. Add deterministic fingerprint helpers plus a JSON deploy-state file, then route both import-time auto-deploy and `/comfymodal/sync/custom-nodes` through one shared decision helper so version and custom-node freshness use the same rules.

**Tech Stack:** Python 3.11, aiohttp route handlers, Modal bridge client wrappers, `unittest`, filesystem-backed local state.

---

## File map

- Modify: `__init__.py` — add custom-node fingerprint helpers, JSON deploy-state helpers, shared deploy-decision helper, and route integration for sync-triggered background deploy.
- Create: `tests/test_custom_node_redeploy.py` — regression tests for fingerprinting, legacy deploy-state fallback, shared deploy-decision logic, and sync helper responses.

## Notes before coding

- Do **not** add git commit steps during execution unless the user explicitly asks.
- Keep the fingerprint intentionally small:
  - sorted top-level custom-node folder names
  - each node's `requirements.txt` contents when present
- Do **not** use raw tarball bytes as the fingerprint source.
- `_maybe_auto_deploy()` is called before `_COMFYUI_ROOT` is defined in `__init__.py`, so any helper it uses must compute the custom-nodes root from `_NODE_DIR` or move the constant earlier.

### Task 1: Add deterministic fingerprint and deploy-state helpers

**Files:**
- Modify: `__init__.py:47-157`
- Create: `tests/test_custom_node_redeploy.py`

- [ ] **Step 1: Write the failing tests for fingerprinting and deploy-state fallback**

Create `tests/test_custom_node_redeploy.py` with this content:

```python
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
    ):
        setattr(stub, name, _noop)

    setattr(stub, "sync_custom_nodes", _async_ok)
    setattr(stub, "resync_runtime", _async_ok)
    setattr(stub, "get_runtime_state", _async_ok)
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `python -m unittest tests.test_custom_node_redeploy.CustomNodeRedeployHelperTests -v`

Expected: FAIL with `AttributeError` because `_build_custom_node_fingerprint`, `_load_deploy_state`, or `_save_deploy_state` do not exist yet.

- [ ] **Step 3: Add the fingerprint and deploy-state helpers in `__init__.py`**

Update `__init__.py` near the existing deploy-state helpers so it contains these definitions:

```python
_DEPLOY_STATE_FILE = os.path.join(_NODE_DIR, ".deployed_version")
_DEPLOY_STATE_JSON_FILE = os.path.join(_NODE_DIR, ".deployed_state.json")
_DEPLOY_LOG_FILE = os.path.join(_NODE_DIR, ".deploy_log")
_LATEST_BENCHMARK_WORKFLOW_FILE = os.path.join(_NODE_DIR, "latest_benchmark_workflow.json")

_CUSTOM_NODE_SYNC_EXCLUDE_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv"}
_CUSTOM_NODE_SYNC_EXCLUDE_EXTENSIONS = {".pyc", ".pyo"}


def _custom_nodes_root() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(_NODE_DIR)), "custom_nodes")


def _iter_syncable_custom_node_dirs(cn_root: str) -> list[str]:
    if not os.path.isdir(cn_root):
        return []
    names = []
    for node_dir in os.listdir(cn_root):
        node_path = os.path.join(cn_root, node_dir)
        if not os.path.isdir(node_path):
            continue
        if node_dir.startswith(".") or node_dir in _CUSTOM_NODE_SYNC_EXCLUDE_DIRS:
            continue
        names.append(node_dir)
    return sorted(names)


def _build_custom_node_fingerprint(cn_root: str) -> str:
    manifest = []
    for node_dir in _iter_syncable_custom_node_dirs(cn_root):
        req_path = os.path.join(cn_root, node_dir, "requirements.txt")
        req_text = ""
        if os.path.isfile(req_path):
            req_text = Path(req_path).read_text(encoding="utf-8")
        manifest.append({
            "node": node_dir,
            "requirements_txt": req_text,
        })
    payload = json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_deploy_state() -> dict:
    try:
        with open(_DEPLOY_STATE_JSON_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if isinstance(payload, dict):
            return {
                "comfyapp_version": payload.get("comfyapp_version"),
                "custom_nodes_fingerprint": payload.get("custom_nodes_fingerprint"),
            }
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass

    legacy_version = None
    try:
        with open(_DEPLOY_STATE_FILE, "r", encoding="utf-8") as f:
            legacy_version = f.read().strip() or None
    except FileNotFoundError:
        legacy_version = None

    return {
        "comfyapp_version": legacy_version,
        "custom_nodes_fingerprint": None,
    }


def _save_deploy_state(version: str | None, fingerprint: str | None) -> None:
    payload = {
        "comfyapp_version": version,
        "custom_nodes_fingerprint": fingerprint,
    }
    with open(_DEPLOY_STATE_JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)


def _get_deployed_version():
    return _load_deploy_state().get("comfyapp_version")


def _get_deployed_custom_nodes_fingerprint():
    return _load_deploy_state().get("custom_nodes_fingerprint")
```

Also add this import near the top of `__init__.py` if it is not already available for text reads:

```python
from pathlib import Path
```

- [ ] **Step 4: Run the helper tests again**

Run: `python -m unittest tests.test_custom_node_redeploy.CustomNodeRedeployHelperTests -v`

Expected: PASS. The new helper tests should confirm deterministic fingerprinting and legacy deploy-state fallback.

### Task 2: Route startup and sync through one shared redeploy decision helper

**Files:**
- Modify: `__init__.py:211-307, 1311-1369`
- Modify: `tests/test_custom_node_redeploy.py`

- [ ] **Step 1: Add failing tests for deploy decisions and sync response wiring**

Append these tests to `tests/test_custom_node_redeploy.py`:

```python
import asyncio


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
        module._deploy_status = {"state": "deploying", "message": "Running modal deploy..."}

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
            patch("builtins.open", new_callable=unittest.mock.mock_open),
        ):
            module._run_deploy_background(custom_nodes_fingerprint="fp-123")

        save_mock.assert_called_once_with("2.14.2", "fp-123")

    def test_sync_custom_nodes_and_maybe_deploy_reports_started_flag(self):
        module = _load_init_module()

        async def fake_sync(archive_data: bytes):
            return {"status": "ok", "nodes": ["comfyui-easy-use"]}

        async def fake_refresh(scope: str):
            return {"status": "ok", "scope": scope}

        with tempfile.TemporaryDirectory() as tmp:
            cn_root = Path(tmp) / "custom_nodes"
            node = cn_root / "comfyui-easy-use"
            node.mkdir(parents=True)
            (node / "requirements.txt").write_text("numpy==1.26.4\n", encoding="utf-8")

            with (
                patch.object(module, "sync_custom_nodes", side_effect=fake_sync),
                patch.object(module, "resync_runtime", side_effect=fake_refresh),
                patch.object(module, "_ensure_modal_deploy_current", return_value={
                    "started": True,
                    "reason": "custom_nodes_changed",
                }),
            ):
                result = asyncio.run(module._sync_custom_nodes_and_maybe_deploy(str(cn_root)))

        self.assertEqual(result["deploy"], {"started": True, "reason": "custom_nodes_changed"})
        self.assertEqual(result["refresh"], {"status": "ok", "scope": "custom_nodes"})

    def test_sync_custom_nodes_and_maybe_deploy_skips_deploy_on_upload_error(self):
        module = _load_init_module()

        async def fake_sync(archive_data: bytes):
            return {"status": "error", "message": "upload failed"}

        with tempfile.TemporaryDirectory() as tmp:
            cn_root = Path(tmp) / "custom_nodes"
            (cn_root / "comfyui-easy-use").mkdir(parents=True)

            with (
                patch.object(module, "sync_custom_nodes", side_effect=fake_sync),
                patch.object(module, "_ensure_modal_deploy_current") as ensure_mock,
            ):
                result = asyncio.run(module._sync_custom_nodes_and_maybe_deploy(str(cn_root)))

        self.assertNotIn("deploy", result)
        ensure_mock.assert_not_called()
```

- [ ] **Step 2: Run the new flow tests to confirm they fail**

Run: `python -m unittest tests.test_custom_node_redeploy.CustomNodeRedeployFlowTests -v`

Expected: FAIL with missing helper errors for `_ensure_modal_deploy_current`, `_start_background_deploy`, or `_sync_custom_nodes_and_maybe_deploy`.

- [ ] **Step 3: Implement shared deploy decision helpers and sync integration**

Update `__init__.py` so the deploy thread, import-time auto-deploy path, and sync route all use the same currentness rules:

```python
def _run_deploy_background(custom_nodes_fingerprint: str | None = None):
    global _deploy_status

    modal_cmd = _find_modal_executable()
    if not modal_cmd:
        _deploy_status = {
            "state": "error",
            "message": "modal CLI not found. Run: pip install modal",
        }
        print(f"[comfyui-modal] {_deploy_status['message']}")
        return

    _deploy_status = {"state": "deploying", "message": "Running modal deploy..."}
    print(f"[comfyui-modal] Deploying comfyapp.py (modal: {modal_cmd})")

    try:
        result = subprocess.run(
            [modal_cmd, "deploy", _COMFYAPP_PATH],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        combined_output = (result.stdout or "") + "\n" + (result.stderr or "")

        try:
            with open(_DEPLOY_LOG_FILE, "w", encoding="utf-8") as f:
                f.write(combined_output)
        except Exception as e:
            print(f"[comfyui-modal] Warning: could not write deploy log: {e}")

        if result.returncode == 0:
            version = _get_comfyapp_version()
            _save_deploy_state(version, custom_nodes_fingerprint)
            _deploy_status = {"state": "ready", "message": f"Deployed v{version}"}
            print(f"[comfyui-modal] Deploy succeeded (v{version})")
            if _modal_available:
                try:
                    clear_cache()
                except Exception as e:
                    print(f"[comfyui-modal] clear_cache failed: {e}")
        else:
            combined = combined_output.strip()
            if "token" in combined.lower() or "auth" in combined.lower() or "credentials" in combined.lower():
                msg = "Modal token not set. Run: modal setup"
            else:
                error_prefix = _parse_deploy_error(combined)
                truncated = combined[:2000]
                msg = f"Deploy failed: {truncated}"
                if error_prefix:
                    msg = f"{error_prefix} {msg}"
            _deploy_status = {
                "state": "error",
                "message": msg,
                "details": combined[:2000],
            }
            print(f"[comfyui-modal] {msg[:500]}")
    except subprocess.TimeoutExpired:
        _deploy_status = {"state": "error", "message": "Deploy timed out (10 min)", "details": "Deploy timed out after 10 minutes"}
        print("[comfyui-modal] Deploy timed out")
    except Exception as e:
        _deploy_status = {"state": "error", "message": str(e), "details": str(e)}
        print(f"[comfyui-modal] Deploy error: {e}")


def _start_background_deploy(custom_nodes_fingerprint: str | None, reason: str) -> dict:
    global _deploy_status
    if _deploy_status.get("state") == "deploying":
        return {"started": False, "reason": "deploy_already_running"}
    thread = threading.Thread(
        target=_run_deploy_background,
        kwargs={"custom_nodes_fingerprint": custom_nodes_fingerprint},
        daemon=True,
    )
    thread.start()
    return {"started": True, "reason": reason}


def _ensure_modal_deploy_current(custom_nodes_fingerprint: str | None = None) -> dict:
    current_version = _get_comfyapp_version()
    deployed = _load_deploy_state()
    deployed_version = deployed.get("comfyapp_version")
    deployed_fingerprint = deployed.get("custom_nodes_fingerprint")

    if current_version != deployed_version:
        return _start_background_deploy(
            custom_nodes_fingerprint=custom_nodes_fingerprint,
            reason="version_changed",
        )

    if custom_nodes_fingerprint != deployed_fingerprint:
        return _start_background_deploy(
            custom_nodes_fingerprint=custom_nodes_fingerprint,
            reason="custom_nodes_changed",
        )

    return {"started": False, "reason": "already_current"}


def _build_custom_nodes_archive(cn_root: str) -> bytes:
    import io
    import tarfile

    def tar_filter(tarinfo):
        parts = tarinfo.name.split("/")
        for part in parts:
            if part in _CUSTOM_NODE_SYNC_EXCLUDE_DIRS:
                return None
        if any(tarinfo.name.endswith(ext) for ext in _CUSTOM_NODE_SYNC_EXCLUDE_EXTENSIONS):
            return None
        return tarinfo

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for node_dir in _iter_syncable_custom_node_dirs(cn_root):
            tar.add(os.path.join(cn_root, node_dir), arcname=node_dir, filter=tar_filter)
    return buf.getvalue()


async def _sync_custom_nodes_and_maybe_deploy(cn_root: str) -> dict:
    fingerprint = _build_custom_node_fingerprint(cn_root)
    archive_data = _build_custom_nodes_archive(cn_root)
    result = await sync_custom_nodes(archive_data)

    if result.get("status") != "ok":
        return result

    result["deploy"] = _ensure_modal_deploy_current(fingerprint)

    try:
        refresh_result = await resync_runtime("custom_nodes")
        result["refresh"] = refresh_result
    except Exception as e:
        result["refresh_error"] = str(e)
        result["message"] = (
            "Custom nodes synced to Modal Volume, but the running Modal ComfyUI process could not be refreshed automatically. "
            "Try again after the container sleeps, or redeploy if the node is still missing."
        )
    else:
        result.setdefault("message", "Custom nodes synced to Modal.")

    return result


def _maybe_auto_deploy():
    fingerprint = _build_custom_node_fingerprint(_custom_nodes_root())
    decision = _ensure_modal_deploy_current(fingerprint)
    if decision["started"]:
        print(f"[comfyui-modal] background deploy started ({decision['reason']})")
    else:
        _deploy_status["state"] = "ready"
        _deploy_status["message"] = "Already deployed and current"
        print("[comfyui-modal] deploy state already current - skipping deploy")
```

Then replace the body of the `/comfymodal/sync/custom-nodes` route with a thin wrapper:

```python
    @_server.routes.post("/comfymodal/sync/custom-nodes")
    async def modal_sync_custom_nodes(request: web.Request) -> web.Response:
        cn_root = os.path.join(_COMFYUI_ROOT, "custom_nodes")
        if not os.path.isdir(cn_root):
            return web.json_response({"status": "error", "message": "custom_nodes directory not found"}, status=400)

        try:
            result = await _sync_custom_nodes_and_maybe_deploy(cn_root)
            return web.json_response(result, status=200 if result.get("status") == "ok" else 500)
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=500)
```

- [ ] **Step 4: Run the flow tests again**

Run: `python -m unittest tests.test_custom_node_redeploy.CustomNodeRedeployFlowTests -v`

Expected: PASS. The shared helper should now cover version changes, fingerprint changes, concurrent deploy suppression, successful fingerprint persistence, and sync response wiring.

- [ ] **Step 5: Run the full targeted regression file**

Run: `python -m unittest tests.test_custom_node_redeploy -v`

Expected: PASS for all fingerprint, state, deploy-decision, and sync-helper tests.

### Task 3: Final verification against existing behavior

**Files:**
- Modify: none
- Test: `tests/test_custom_node_redeploy.py`

- [ ] **Step 1: Re-run existing lightweight route/import regression tests**

Run: `python -m unittest tests.test_input_image_paths tests.test_modal_runtime_routes -v`

Expected: PASS. The new deploy helpers must not break `__init__.py` import stubbing or existing route registration expectations.

- [ ] **Step 2: Re-run one existing runtime-state regression file**

Run: `python -m unittest tests.test_comfyapp_runtime_state -v`

Expected: PASS. This confirms the new deploy-state logic did not spill into the Modal runtime module.

## Self-check before implementation handoff

- The plan covers every approved spec behavior:
  - background deploy after sync
  - no deploy when fingerprint is unchanged
  - fingerprint based only on top-level folder names + `requirements.txt`
  - fingerprint saved only after successful deploy
  - legacy `.deployed_version` treated as stale until first successful JSON-state deploy
  - sync response carries deploy decision metadata
- No commit steps are included because the user has not asked for commits.
- The plan keeps the implementation scope inside `__init__.py` plus one focused test file.
