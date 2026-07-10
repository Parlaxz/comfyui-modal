"""Backend/behavior tests for Studio preset execution runtime.

Tests cover the studio_run_adapter module and the two new backend routes:
  POST /comfymodal/studio/run
  POST /comfymodal/studio/experiment

All tests use in-memory or temp-directory stores — no real Modal calls.
"""
import asyncio
import copy
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _load_module(name: str, rel_path: str):
    """Load a repo module by relative path."""
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel_path)
    assert spec is not None, f"Could not find spec for {rel_path}"
    assert spec.loader is not None, f"Could not find loader for {rel_path}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _make_runnable_snapshot(snapshot_id: str = "snap_runnable") -> dict:
    return {
        "id": snapshot_id,
        "name": "Runnable Txt2Img Snapshot",
        "compatibleFeatures": ["txt2img"],
        "apiPromptJson": {"3": {"class_type": "KSampler", "inputs": {"seed": 42, "steps": 20}}},
        "nodeBindings": {
            "prompt": {"kind": "widget", "nodeId": "3", "widgetName": "text"},
            "output": {"kind": "output", "nodeId": "9"},
        },
        "outputNodeId": "9",
        "graphJson": {"nodes": [], "links": []},
        "archived": False,
        "status": "runnable",
        "featureStatus": {
            "txt2img": {"status": "runnable", "reason": ""},
        },
        "disabledReason": "",
    }


def _make_runnable_preset(preset_id: str = "preset_runnable",
                          snapshot_id: str = "snap_runnable") -> dict:
    return {
        "id": preset_id,
        "label": "Runnable Preset",
        "snapshotId": snapshot_id,
        "compatibleFeatures": ["txt2img"],
        "defaults": {},
        "sourceType": "snapshot",
        "sourceId": "",
        "archived": False,
        "status": "runnable",
        "disabledReason": "",
    }


def _make_archived_snapshot(snapshot_id: str = "snap_archived") -> dict:
    s = _make_runnable_snapshot(snapshot_id)
    s["archived"] = True
    s["status"] = "archived"
    return s


def _make_archived_preset(preset_id: str = "preset_archived",
                          snapshot_id: str = "snap_archived") -> dict:
    p = _make_runnable_preset(preset_id, snapshot_id)
    p["archived"] = True
    p["status"] = "archived"
    return p


def _make_needs_bindings_snapshot(snapshot_id: str = "snap_needs_bind") -> dict:
    return {
        "id": snapshot_id,
        "name": "Needs Bindings Snapshot",
        "compatibleFeatures": ["txt2img"],
        "apiPromptJson": {"3": {"class_type": "KSampler", "inputs": {"seed": 42}}},
        "nodeBindings": {},
        "outputNodeId": "",
        "archived": False,
        "status": "needs_bindings",
        "featureStatus": {
            "txt2img": {"status": "needs_bindings", "reason": "missing required node bindings"},
        },
        "disabledReason": "Missing required node bindings",
    }


def _make_studio_store_files(tmpdir: str, snapshots: list[dict], presets: list[dict]):
    """Write snapshot and preset JSON store files into tmpdir."""
    snap_path = Path(tmpdir) / ".studio_snapshots.json"
    preset_path = Path(tmpdir) / ".studio_presets.json"
    snap_path.write_text(json.dumps(snapshots), encoding="utf-8")
    preset_path.write_text(json.dumps(presets), encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests for studio_run_adapter module
# ---------------------------------------------------------------------------

class StudioRunAdapterLoadTests(unittest.TestCase):
    """Basic loading and validation of presets/snapshots."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module("studio_run_adapter", "studio_run_adapter.py")

    def test_load_preset_and_snapshot_ok(self):
        """load_preset_and_snapshot returns (preset, snapshot) for valid IDs."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            p, s = self.mod.load_preset_and_snapshot("preset_runnable", tmp)
            self.assertEqual(p["id"], "preset_runnable")
            self.assertEqual(s["id"], "snap_runnable")

    def test_load_missing_preset_rejected(self):
        """Missing preset ID returns None."""
        with tempfile.TemporaryDirectory() as tmp:
            _make_studio_store_files(tmp, [], [])
            result = self.mod.load_preset_and_snapshot("does_not_exist", tmp)
            self.assertIsNone(result)
            err = self.mod.get_load_error()
            self.assertIn("not found", err.lower())

    def test_load_missing_snapshot_rejected(self):
        """Preset referencing missing snapshot returns None."""
        with tempfile.TemporaryDirectory() as tmp:
            preset = {
                "id": "preset_bad", "label": "Bad", "snapshotId": "snap_missing",
                "sourceType": "snapshot", "archived": False,
            }
            _make_studio_store_files(tmp, [], [preset])
            result = self.mod.load_preset_and_snapshot("preset_bad", tmp)
            self.assertIsNone(result)
            err = self.mod.get_load_error()
            self.assertIn("not found", err.lower())

    def test_load_archived_preset_rejected(self):
        """Archived preset is rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_archived_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            result = self.mod.load_preset_and_snapshot("preset_archived", tmp)
            self.assertIsNone(result)
            err = self.mod.get_load_error()
            self.assertIn("archived", err.lower())

    def test_load_archived_snapshot_rejected(self):
        """Preset pointing to archived snapshot is rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_archived_snapshot()
            preset = _make_runnable_preset(snapshot_id="snap_archived")
            _make_studio_store_files(tmp, [snap], [preset])
            result = self.mod.load_preset_and_snapshot("preset_runnable", tmp)
            self.assertIsNone(result)
            err = self.mod.get_load_error()
            self.assertIn("archived", err.lower())


class StudioRunAdapterValidationTests(unittest.TestCase):
    """Validation of runnability, features, bindings."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module("studio_run_adapter", "studio_run_adapter.py")

    def test_non_runnable_preset_rejected(self):
        """Preset whose snapshot is non-runnable is rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_needs_bindings_snapshot()
            preset = _make_runnable_preset(snapshot_id="snap_needs_bind")
            _make_studio_store_files(tmp, [snap], [preset])
            result = self.mod.validate_studio_run(preset, snap, "txt2img")
            self.assertIn("error", result)

    def test_incompatible_feature_rejected(self):
        """Requesting a feature not in compatibleFeatures is rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            result = self.mod.validate_studio_run(preset, snap, "object_remove")
            self.assertIn("error", result)
            self.assertIn("compatible", result.get("error", "").lower())

    def test_runnable_txt2img_accepted(self):
        """Runnable txt2img preset passes validation."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            result = self.mod.validate_studio_run(preset, snap, "txt2img")
            self.assertIsNone(result.get("error"))

    def test_object_remove_blocked_without_image_input(self):
        """object_remove feature is blocked (image/mask flow not implemented)."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = copy.deepcopy(_make_runnable_snapshot("snap_obj"))
            snap["compatibleFeatures"] = ["txt2img", "object_remove"]
            snap["nodeBindings"] = {
                "prompt": {"kind": "widget", "nodeId": "3", "widgetName": "text"},
                "source_image": {"kind": "node", "nodeId": "12"},
                "mask": {"kind": "node", "nodeId": "13"},
                "instruction": {"kind": "widget", "nodeId": "14", "widgetName": "text"},
                "output": {"kind": "output", "nodeId": "9"},
            }
            from studio_models import normalize_snapshot_payload
            snap = normalize_snapshot_payload(snap)
            preset = _make_runnable_preset("preset_obj", "snap_obj")
            preset["compatibleFeatures"] = ["txt2img", "object_remove"]
            _make_studio_store_files(tmp, [snap], [preset])
            # We need apiPromptJson too for object_remove to be runnable
            snap["apiPromptJson"] = {"12": {"class_type": "LoadImage", "inputs": {}}}
            from studio_models import normalize_snapshot_payload
            snap = normalize_snapshot_payload(snap)
            result = self.mod.validate_studio_run(preset, snap, "object_remove")
            self.assertIn("error", result)
            self.assertIn("not yet implemented", result.get("error", "").lower())

    def test_object_replace_blocked_without_image_input(self):
        """object_replace feature is blocked (image/mask flow not implemented)."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = copy.deepcopy(_make_runnable_snapshot("snap_rep"))
            snap["compatibleFeatures"] = ["txt2img", "object_replace"]
            snap["nodeBindings"] = {
                "prompt": {"kind": "widget", "nodeId": "3", "widgetName": "text"},
                "source_image": {"kind": "node", "nodeId": "12"},
                "mask": {"kind": "node", "nodeId": "13"},
                "replacement_prompt": {"kind": "widget", "nodeId": "14", "widgetName": "text"},
                "output": {"kind": "output", "nodeId": "9"},
            }
            snap["apiPromptJson"] = {"12": {"class_type": "LoadImage", "inputs": {}}}
            from studio_models import normalize_snapshot_payload
            snap = normalize_snapshot_payload(snap)
            preset = _make_runnable_preset("preset_rep", "snap_rep")
            preset["compatibleFeatures"] = ["txt2img", "object_replace"]
            _make_studio_store_files(tmp, [snap], [preset])
            result = self.mod.validate_studio_run(preset, snap, "object_replace")
            self.assertIn("error", result)
            self.assertIn("not yet implemented", result.get("error", "").lower())


class StudioRunAdapterCompilationTests(unittest.TestCase):
    """Compilation / spec building from Studio presets."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module("studio_run_adapter", "studio_run_adapter.py")

    def test_build_single_run_spec_copies_api_prompt(self):
        """apiPromptJson is deep-copied, not referenced."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            controls = {"prompt": "a cat", "seed": 42}
            spec = self.mod.build_single_run_spec(preset, snap, "txt2img", controls, tmp)
            self.assertIsNotNone(spec)
            # Verify the workflow is a deep copy (inside checkpoints[0])
            ck = spec["checkpoints"][0]
            self.assertIsNot(ck["workflow"], snap["apiPromptJson"])

    def test_single_run_spec_has_correct_structure(self):
        """Single run spec has the expected compilation-like structure."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            controls = {"prompt": "a cat", "seed": 42, "steps": 25}
            spec = self.mod.build_single_run_spec(preset, snap, "txt2img", controls, tmp)
            self.assertIn("experiment_id", spec)
            self.assertIn("revision", spec)
            self.assertIn("checkpoints", spec)
            self.assertIn("cells", spec)
            self.assertEqual(len(spec["checkpoints"]), 1)
            self.assertEqual(len(spec["cells"]), 1)
            ck = spec["checkpoints"][0]
            self.assertIn("workflow", ck)
            self.assertIn("slots", ck)
            self.assertIn("studio_meta", ck)
            cell = spec["cells"][0]
            self.assertIn("cell_key", cell)
            self.assertIn("axis_values", cell)

    def test_single_run_spec_applies_control_overrides(self):
        """Control overrides modify the deep-copied workflow but not stored snapshot."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            original_prompt_json = copy.deepcopy(snap["apiPromptJson"])
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            controls = {"prompt": "overridden prompt", "seed": 999, "steps": 50}
            spec = self.mod.build_single_run_spec(preset, snap, "txt2img", controls, tmp)
            cell = spec["cells"][0]
            # The cell axis values should carry the override
            self.assertEqual(cell["axis_values"].get("seed"), 999)
            # The stored snapshot must NOT be modified
            self.assertEqual(snap["apiPromptJson"]["3"]["inputs"]["seed"], 42)

    def test_single_run_spec_has_studio_metadata(self):
        """Studio metadata is attached to compilation/cell for history."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            controls = {"prompt": "test", "seed": 1}
            spec = self.mod.build_single_run_spec(preset, snap, "txt2img", controls, tmp)
            meta = spec.get("studio_meta", {})
            self.assertEqual(meta.get("studio_preset_id"), "preset_runnable")
            self.assertEqual(meta.get("studio_snapshot_id"), "snap_runnable")
            self.assertEqual(meta.get("studio_feature_id"), "txt2img")
            self.assertIn("studio_controls", meta)
            self.assertEqual(meta["studio_controls"].get("seed"), 1)


class StudioRunAdapterExperimentTests(unittest.TestCase):
    """Experiment expansion from Studio presets."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module("studio_run_adapter", "studio_run_adapter.py")

    def test_experiment_expansion_returns_cells(self):
        """Experiment over presets/axes returns expected cell count."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            exp_def = {
                "prompts": [
                    {"id": "p1", "text": "a cat", "enabled": True},
                    {"id": "p2", "text": "a dog", "enabled": True},
                ],
                "axes": {"shared": {"seed": {"mode": "list", "values": [1, 2]}}},
            }
            spec = self.mod.build_experiment_spec(
                [(preset, snap)], "txt2img", exp_def, tmp
            )
            # compile_experiment should expand: 2 prompts × 2 seeds = 4 cells
            cells = spec.get("cells", [])
            self.assertGreaterEqual(len(cells), 4)

    def test_experiment_rejects_disabled_preset(self):
        """Experiment submission rejects a disabled/non-runnable preset."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_needs_bindings_snapshot()
            preset = _make_runnable_preset(snapshot_id="snap_needs_bind")
            _make_studio_store_files(tmp, [snap], [preset])
            exp_def = {"prompts": [{"id": "p1", "text": "test", "enabled": True}]}
            result = self.mod.build_experiment_spec(
                [(preset, snap)], "txt2img", exp_def, tmp
            )
            self.assertIn("error", result)

    def test_experiment_checkpoints_have_studio_workflow(self):
        """Checkpoints get snapshot workflow/slots instead of legacy profile lookup."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            exp_def = {"prompts": [{"id": "p1", "text": "test", "enabled": True}]}
            spec = self.mod.build_experiment_spec(
                [(preset, snap)], "txt2img", exp_def, tmp
            )
            for ck in spec.get("checkpoints", []):
                self.assertIn("workflow", ck)
                self.assertIn("slots", ck)
                # Should be from snapshot, not from legacy profile
                self.assertEqual(ck["workflow"], snap["apiPromptJson"])


class StudioRunAdapterHistoryTests(unittest.TestCase):
    """History metadata threading for studio runs."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module("studio_run_adapter", "studio_run_adapter.py")

    def test_history_meta_contains_studio_info(self):
        """History metadata carries preset/snapshot/feature/control info."""
        meta = self.mod._build_studio_history_meta(
            preset_id="preset_1",
            snapshot_id="snap_1",
            feature_id="txt2img",
            controls={"prompt": "test", "seed": 42},
        )
        self.assertEqual(meta.get("studio_preset_id"), "preset_1")
        self.assertEqual(meta.get("studio_snapshot_id"), "snap_1")
        self.assertEqual(meta.get("studio_feature_id"), "txt2img")
        self.assertEqual(meta.get("studio_controls", {}).get("seed"), 42)

    def test_experiment_history_meta_contains_studio_info(self):
        """Experiment definition metadata carries studio info."""
        meta = self.mod._build_studio_experiment_meta(
            preset_ids=["preset_1"],
            snapshot_ids=["snap_1"],
            feature_id="txt2img",
        )
        self.assertEqual(meta.get("studio_preset_ids"), ["preset_1"])
        self.assertEqual(meta.get("studio_snapshot_ids"), ["snap_1"])
        self.assertEqual(meta.get("studio_feature_id"), "txt2img")


# ---------------------------------------------------------------------------
# Tests for route registration + behavior
# ---------------------------------------------------------------------------

class _StubServer:
    def __init__(self):
        self.routes: Any = _StubRouteTable()
        self.sent_events: list[tuple[str, dict, str]] = []

    def send_sync(self, event: str, data: dict, sid: str = ""):
        self.sent_events.append((event, dict(data), sid))


class _StubRouteTable:
    def __init__(self):
        self._handlers: list[tuple[str, str, Any]] = []

    def get(self, path: str):
        def deco(fn):
            self._handlers.append(("GET", path, fn))
            return fn
        return deco

    def post(self, path: str):
        def deco(fn):
            self._handlers.append(("POST", path, fn))
            return fn
        return deco

    def put(self, path: str):
        def deco(fn):
            self._handlers.append(("PUT", path, fn))
            return fn
        return deco

    def delete(self, path: str):
        def deco(fn):
            self._handlers.append(("DELETE", path, fn))
            return fn
        return deco

    def patch(self, path: str):
        def deco(fn):
            self._handlers.append(("PATCH", path, fn))
            return fn
        return deco


class _MockRequest:
    def __init__(self, *, json_body: dict | None = None, query: dict | None = None,
                 match_info: dict | None = None):
        self._json = json_body
        self._query = query or {}
        self._match_info = match_info or {}
        self.body_exists = json_body is not None

    async def json(self) -> dict:
        if self._json is None:
            raise ValueError("no body")
        return self._json

    @property
    def query(self):
        return self._query

    @property
    def match_info(self):
        return self._match_info


def _run(coro):
    return asyncio.run(coro)


def _build_init_with_stub(stub_server):
    """Load __init__.py with a stub server."""
    server_stub = type(sys)("server")
    server_stub.PromptServer = type("PromptServer", (), {"instance": stub_server})
    sys.modules["server"] = server_stub
    exec_stub = type(sys)("execution")
    exec_stub.PromptQueue = type("PromptQueue", (), {})
    sys.modules["execution"] = exec_stub
    for mod in ("local_placeholders", "workflow_metadata", "api_prompt_validator",
                "failure_summary", "output_converter", "output_saver",
                "timing_trace", "profiler_trace_v4", "production_workflow",
                "comparison", "model_manifest", "modal_workspaces",
                "modal_client", "gpu_catalog", "optimizations",
                "run_history", "presets", "matrix_compiler", "experiment_store",
                "experiment_lease", "experiment_models", "experiment_runner",
                "experiment_scheduler", "deploy_warmup", "experiment_service",
                "studio_run_adapter"):
        if mod not in sys.modules:
            try:
                spec = importlib.util.spec_from_file_location(mod, REPO_ROOT / f"{mod}.py")
                if spec is None or spec.loader is None:
                    continue
                m = importlib.util.module_from_spec(spec)
                sys.modules[mod] = m
                spec.loader.exec_module(m)
            except Exception:
                pass
    spec = importlib.util.spec_from_file_location("comfyui_modal_under_test", REPO_ROOT / "__init__.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["comfyui_modal_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def _handler_for(init_mod, method: str, path: str):
    for m, p, fn in init_mod._server.routes._handlers:
        if m == method and p == path:
            return fn
    for m, p, fn in init_mod._server.routes._handlers:
        if m != method:
            continue
        p_parts = p.split("/")
        a_parts = path.split("/")
        if len(p_parts) != len(a_parts):
            continue
        match = True
        for pp, ap in zip(p_parts, a_parts):
            if pp.startswith("{") and pp.endswith("}"):
                continue
            if pp != ap:
                match = False
                break
        if match:
            return fn
    return None


class StudioRunRouteRegistrationTests(unittest.TestCase):
    """The two new Studio run routes must be registered."""

    @classmethod
    def setUpClass(cls):
        cls.stub = _StubServer()
        cls.init_mod = _build_init_with_stub(cls.stub)

    def test_studio_run_route_registered(self):
        fn = _handler_for(self.init_mod, "POST", "/comfymodal/studio/run")
        self.assertIsNotNone(fn, "POST /comfymodal/studio/run not registered")

    def test_studio_experiment_route_registered(self):
        fn = _handler_for(self.init_mod, "POST", "/comfymodal/studio/experiment")
        self.assertIsNotNone(fn, "POST /comfymodal/studio/experiment not registered")


class GitignoreRuntimeArtifactTests(unittest.TestCase):
    """.gitignore covers the runtime artifact files."""

    def test_studio_presets_json_in_gitignore(self):
        text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".studio_presets.json", text)

    def test_studio_snapshots_json_in_gitignore(self):
        text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".studio_snapshots.json", text)

    def test_studio_backends_json_in_gitignore(self):
        text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".studio_backends.json", text)

    def test_tmp_suffix_glob_in_gitignore(self):
        text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("*.tmp", text)


if __name__ == "__main__":
    unittest.main()
