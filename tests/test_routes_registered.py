"""Test the HTTP routes registered by comfyui-modal for the testing suite.

These tests load ``__init__.py`` (or a thin shim) with the ``_server``
attribute replaced by a minimal ``PromptServer`` stub so the route
decorators execute.  Each test then constructs an ``aiohttp`` test
client to exercise the route end-to-end.
"""
import asyncio
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]


# ── Minimal _server stub that records sent events ────────────────────────


class _StubServer:
    def __init__(self) -> None:
        self.routes: Any = _StubRouteTable()
        self.sent_events: list[tuple[str, dict, str]] = []

    def send_sync(self, event: str, data: dict, sid: str = "") -> None:
        self.sent_events.append((event, dict(data), sid))


class _StubRouteTable:
    """Mimic ``PromptServer.instance.routes`` enough that the route
    decorators in __init__.py can record their handlers."""

    def __init__(self) -> None:
        self._handlers: list[tuple[str, str, Any]] = []

    def get(self, path: str) -> Any:
        def deco(fn):
            self._handlers.append(("GET", path, fn))
            return fn
        return deco

    def post(self, path: str) -> Any:
        def deco(fn):
            self._handlers.append(("POST", path, fn))
            return fn
        return deco

    def put(self, path: str) -> Any:
        def deco(fn):
            self._handlers.append(("PUT", path, fn))
            return fn
        return deco

    def delete(self, path: str) -> Any:
        def deco(fn):
            self._handlers.append(("DELETE", path, fn))
            return fn
        return deco

    def patch(self, path: str) -> Any:
        def deco(fn):
            self._handlers.append(("PATCH", path, fn))
            return fn
        return deco


def _build_init_with_stub(stub_server):
    """Load __init__.py with sys.modules['_server'] = stub_server."""
    # Stub out the imports __init__.py does at the top, especially
    # ``from server import PromptServer`` which would fail outside ComfyUI.
    server_stub = type(sys)("server")
    server_stub.PromptServer = type("PromptServer", (), {"instance": stub_server})
    sys.modules["server"] = server_stub
    # Execution module
    exec_stub = type(sys)("execution")
    exec_stub.PromptQueue = type("PromptQueue", (), {})
    sys.modules["execution"] = exec_stub
    # Server log_parser is referenced; stub
    for mod in ("local_placeholders", "workflow_metadata", "api_prompt_validator",
                "failure_summary", "output_converter", "output_saver",
                "timing_trace", "profiler_trace_v4", "production_workflow",
                "comparison", "model_manifest", "modal_workspaces",
                "modal_client", "gpu_catalog", "optimizations",
                "run_history", "presets", "matrix_compiler", "experiment_store",
                "experiment_lease", "experiment_models", "experiment_runner",
                "experiment_scheduler", "deploy_warmup", "experiment_service"):
        if mod not in sys.modules:
            try:
                spec = importlib.util.spec_from_file_location(
                    mod, REPO_ROOT / f"{mod}.py"
                )
                if spec is None or spec.loader is None:
                    continue
                m = importlib.util.module_from_spec(spec)
                sys.modules[mod] = m
                spec.loader.exec_module(m)
            except Exception:
                pass
    # Now load __init__.py
    spec = importlib.util.spec_from_file_location("comfyui_modal_under_test", REPO_ROOT / "__init__.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["comfyui_modal_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def _handler_for(init_mod, method: str, path: str):
    """Look up the route handler in the stub server's route table."""
    for m, p, fn in init_mod._server.routes._handlers:
        if m == method and p == path:
            return fn
    # Try with simple path match (ignoring {id} segments)
    for m, p, fn in init_mod._server.routes._handlers:
        if m != method:
            continue
        if _paths_match(p, path):
            return fn
    return None


def _paths_match(pattern: str, actual: str) -> bool:
    p_parts = pattern.split("/")
    a_parts = actual.split("/")
    if len(p_parts) != len(a_parts):
        return False
    for pp, ap in zip(p_parts, a_parts):
        if pp.startswith("{") and pp.endswith("}"):
            continue
        if pp != ap:
            return False
    return True


class _MockRequest:
    """Minimal aiohttp.web.Request shim."""

    def __init__(self, *, json_body: dict | None = None, query: dict | None = None, match_info: dict | None = None):
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
    """Helper to run an async coroutine to completion synchronously.

    Uses ``asyncio.run`` (which creates a fresh event loop each call)
    instead of ``get_event_loop().run_until_complete()`` to avoid
    ``RuntimeError: There is no current event loop`` when other test
    modules (e.g. test_experiment_runner) have called ``asyncio.run``
    in the same process (Python 3.11+ destroys the loop after
    ``asyncio.run`` returns).
    """
    return asyncio.run(coro)


def _load_repo_module(module_name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(module_name, REPO_ROOT / relative_path)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# ── Tests ────────────────────────────────────────────────────────────────


class RouteRegistrationTests(unittest.TestCase):
    """Every route required by the spec must be registered."""

    @classmethod
    def setUpClass(cls):
        cls.stub = _StubServer()
        cls.init_mod = _build_init_with_stub(cls.stub)
        cls.routes = {p: [(m, fn) for m, p_, fn in cls.stub.routes._handlers if p_ == p] for p in [h[1] for h in cls.stub.routes._handlers]}

    def test_experiment_compile_route(self):
        fn = _handler_for(self.init_mod, "POST", "/comfymodal/experiments/compile")
        self.assertIsNotNone(fn)

    def test_docs_page_route(self):
        fn = _handler_for(self.init_mod, "GET", "/comfymodal/docs")
        self.assertIsNotNone(fn)
        self.assertTrue((REPO_ROOT / "web" / "docs.html").is_file())

    def test_experiment_create_route(self):
        fn = _handler_for(self.init_mod, "POST", "/comfymodal/experiments")
        self.assertIsNotNone(fn)

    def test_experiment_list_route(self):
        fn = _handler_for(self.init_mod, "GET", "/comfymodal/experiments")
        self.assertIsNotNone(fn)

    def test_experiment_detail_route(self):
        fn = _handler_for(self.init_mod, "GET", "/comfymodal/experiments/{experiment_id}")
        self.assertIsNotNone(fn)

    def test_experiment_events_route(self):
        fn = _handler_for(self.init_mod, "GET", "/comfymodal/experiments/{experiment_id}/events")
        self.assertIsNotNone(fn)

    def test_start_pause_stop_resume_routes(self):
        for verb, path in [
            ("POST", "/comfymodal/experiments/{experiment_id}/start"),
            ("POST", "/comfymodal/experiments/{experiment_id}/pause"),
            ("POST", "/comfymodal/experiments/{experiment_id}/stop-after-current"),
            ("POST", "/comfymodal/experiments/{experiment_id}/stop-now"),
            ("POST", "/comfymodal/experiments/{experiment_id}/resume"),
        ]:
            with self.subTest(verb=verb, path=path):
                fn = _handler_for(self.init_mod, verb, path)
                self.assertIsNotNone(fn)

    def test_checkpoint_control_routes(self):
        for verb, path in [
            ("POST", "/comfymodal/experiments/{experiment_id}/checkpoints/{checkpoint_id}/continue"),
            ("POST", "/comfymodal/experiments/{experiment_id}/checkpoints/{checkpoint_id}/restart"),
            ("POST", "/comfymodal/experiments/{experiment_id}/checkpoints/{checkpoint_id}/restart-from"),
            ("POST", "/comfymodal/experiments/{experiment_id}/checkpoints/{checkpoint_id}/skip"),
            ("POST", "/comfymodal/experiments/{experiment_id}/checkpoints/{checkpoint_id}/unskip"),
        ]:
            with self.subTest(verb=verb, path=path):
                fn = _handler_for(self.init_mod, verb, path)
                self.assertIsNotNone(fn)

    def test_prompt_preset_crud_routes(self):
        for verb, path in [
            ("GET", "/comfymodal/presets/prompts"),
            ("POST", "/comfymodal/presets/prompts"),
            ("GET", "/comfymodal/presets/prompts/{preset_id}"),
            ("PUT", "/comfymodal/presets/prompts/{preset_id}"),
            ("DELETE", "/comfymodal/presets/prompts/{preset_id}"),
            ("POST", "/comfymodal/presets/prompts/{preset_id}/duplicate"),
            ("POST", "/comfymodal/presets/prompts/import"),
        ]:
            with self.subTest(verb=verb, path=path):
                fn = _handler_for(self.init_mod, verb, path)
                self.assertIsNotNone(fn)

    def test_image_preset_crud_routes(self):
        for verb, path in [
            ("GET", "/comfymodal/presets/images"),
            ("POST", "/comfymodal/presets/images"),
            ("GET", "/comfymodal/presets/images/{preset_id}"),
            ("PUT", "/comfymodal/presets/images/{preset_id}"),
            ("DELETE", "/comfymodal/presets/images/{preset_id}"),
        ]:
            with self.subTest(verb=verb, path=path):
                fn = _handler_for(self.init_mod, verb, path)
                self.assertIsNotNone(fn)

    def test_asset_serve_route(self):
        fn = _handler_for(self.init_mod, "GET", "/comfymodal/assets/{asset_id}")
        self.assertIsNotNone(fn)

    def test_run_history_routes(self):
        for verb, path in [
            ("GET", "/comfymodal/run-history"),
            ("GET", "/comfymodal/run-history/{run_id}"),
            ("GET", "/comfymodal/run-history/{run_id}/logs"),
            ("GET", "/comfymodal/run-history/{run_id}/timing"),
        ]:
            with self.subTest(verb=verb, path=path):
                fn = _handler_for(self.init_mod, verb, path)
                self.assertIsNotNone(fn)

    def test_warmup_routes(self):
        for verb, path in [
            ("GET", "/comfymodal/deploy-warmup/status"),
            ("POST", "/comfymodal/deploy-warmup/run"),
            ("POST", "/comfymodal/deploy-warmup/invalidate"),
        ]:
            with self.subTest(verb=verb, path=path):
                fn = _handler_for(self.init_mod, verb, path)
                self.assertIsNotNone(fn)


class ExperimentRouteBehaviourTests(unittest.TestCase):
    """Verify the routes return JSON for the typical happy path."""

    @classmethod
    def setUpClass(cls):
        cls.stub = _StubServer()
        cls.init_mod = _build_init_with_stub(cls.stub)

    def test_presets_prompts_list_returns_json(self):
        fn = _handler_for(self.init_mod, "GET", "/comfymodal/presets/prompts")
        resp = _run(fn(_MockRequest()))
        self.assertEqual(resp.status, 200)

    def test_presets_images_list_returns_json(self):
        fn = _handler_for(self.init_mod, "GET", "/comfymodal/presets/images")
        resp = _run(fn(_MockRequest()))
        self.assertEqual(resp.status, 200)

    def test_warmup_status_returns_state(self):
        fn = _handler_for(self.init_mod, "GET", "/comfymodal/deploy-warmup/status")
        resp = _run(fn(_MockRequest()))
        self.assertEqual(resp.status, 200)

    def test_run_history_list_returns_json(self):
        fn = _handler_for(self.init_mod, "GET", "/comfymodal/run-history")
        resp = _run(fn(_MockRequest()))
        self.assertEqual(resp.status, 200)

    def test_asset_serve_rejects_invalid_id(self):
        fn = _handler_for(self.init_mod, "GET", "/comfymodal/assets/{asset_id}")
        # Phase 10: route now resolves via exact asset registry.
        # Unknown asset IDs return 404 (asset not found in registry).
        req = _MockRequest(match_info={"asset_id": "nonexistent_asset"})
        resp = _run(fn(req))
        self.assertEqual(resp.status, 404)
        # Empty asset ID
        req = _MockRequest(match_info={"asset_id": ""})
        resp = _run(fn(req))
        self.assertEqual(resp.status, 400)


class ExperimentCompileNormalizedDraftTests(unittest.TestCase):
    """The compile route must accept a normalised draft directly."""

    @classmethod
    def setUpClass(cls):
        cls.stub = _StubServer()
        cls.init_mod = _build_init_with_stub(cls.stub)

    def test_compile_with_spec_still_works(self):
        """Existing spec payloads still compile successfully."""
        fn = _handler_for(self.init_mod, "POST", "/comfymodal/experiments/compile")
        spec = {
            "experiment_id": "exp_1",
            "revision": 1,
            "workflows": [{
                "profile_id": "p1",
                "loader_target_group_id": "g_default",
                "main_triple": {"id": "main", "unet": "u1", "clip": "c1", "vae": "v1"},
                "subprofile_triples": [],
                "selected_triple_ids": ["main"],
                "lora_slots": [],
            }],
            "prompts": {"items": [
                {"id": "p", "label": "t", "text": "hi", "negative": None, "enabled": True},
            ]},
            "images": {"mode": "cartesian", "items": []},
            "loras": {"selections": []},
            "axes": {"shared": {"seed": {"mode": "list", "values": [42]}}},
        }
        req = _MockRequest(json_body={"spec": spec})
        resp = _run(fn(req))
        self.assertEqual(resp.status, 200)
        body = json.loads(resp.body)
        self.assertEqual(body.get("status"), "ok")

    def test_compile_accepts_normalized_draft(self):
        """Compile route accepts a normalised draft payload."""
        fn = _handler_for(self.init_mod, "POST", "/comfymodal/experiments/compile")
        draft = {
            "experiment_id": "exp_nd",
            "revision": 1,
            "profile_type": "t2i",
            "workflows": [{
                "profile_id": "p1",
                "stacks": [{
                    "stack_id": "s1",
                    "loader_target_group_id": "g_default",
                    "main_triple": {"id": "main", "unet": "u1", "clip": "c1", "vae": "v1"},
                    "selected_triple_ids": ["main"],
                    "lora_selections": [],
                }],
            }],
            "prompts": {"items": [
                {"id": "p", "label": "t", "text": "hi", "negative": None, "enabled": True},
            ]},
            "axes": {"shared": {"seed": {"mode": "list", "values": [42]}}},
        }
        req = _MockRequest(json_body={"normalized_draft": draft})
        resp = _run(fn(req))
        body = json.loads(resp.body)
        print(f"compile normalized draft response: {json.dumps(body, indent=2)[:500]}")
        self.assertEqual(resp.status, 200, msg=f"body={body}")
        self.assertEqual(body.get("status"), "ok")
        self.assertIn("compilation", body)

    def test_compile_normalized_draft_produces_cells(self):
        """Normalised draft yields cells via the compiler."""
        fn = _handler_for(self.init_mod, "POST", "/comfymodal/experiments/compile")
        draft = {
            "experiment_id": "exp_cells",
            "revision": 1,
            "profile_type": "t2i",
            "workflows": [{
                "profile_id": "p1",
                "stacks": [{
                    "stack_id": "s1",
                    "loader_target_group_id": "g_default",
                    "main_triple": {"id": "main", "unet": "u1", "clip": "c1", "vae": "v1"},
                    "selected_triple_ids": ["main"],
                    "lora_selections": [
                        {"id": "L_no", "label": "No LoRA", "loras": [], "enabled": True},
                    ],
                }],
            }],
            "prompts": {"items": [
                {"id": "p_a", "label": "a", "text": "a cat", "negative": None, "enabled": True},
            ]},
            "axes": {"shared": {"seed": {"mode": "list", "values": [42]}}},
        }
        req = _MockRequest(json_body={"normalized_draft": draft})
        resp = _run(fn(req))
        self.assertEqual(resp.status, 200)
        body = json.loads(resp.body)
        cells = body.get("compilation", {}).get("cells", [])
        self.assertGreater(len(cells), 0)
        for cell in cells:
            self.assertIn("normalized_dimensions", cell)

    def test_compile_invalid_normalized_draft_rejected(self):
        """Invalid normalised draft is rejected with 400."""
        fn = _handler_for(self.init_mod, "POST", "/comfymodal/experiments/compile")
        draft = {"experiment_id": ""}  # missing required fields
        req = _MockRequest(json_body={"normalized_draft": draft})
        resp = _run(fn(req))
        self.assertEqual(resp.status, 400)
        body = json.loads(resp.body)
        self.assertIn("error", body.get("status", "").lower() or body.get("message", "").lower())


class ComparisonProfileNormalizedViewTests(unittest.TestCase):
    """Comparison profile responses should expose a normalised runtime view."""

    @classmethod
    def setUpClass(cls):
        cls.stub = _StubServer()
        cls.init_mod = _build_init_with_stub(cls.stub)

    def test_profile_list_returns_normalized_key(self):
        """The profile list endpoint returns a 'normalized' key per profile."""
        fn = _handler_for(self.init_mod, "GET", "/comfymodal/comparison/profiles")
        req = _MockRequest()
        resp = _run(fn(req))
        self.assertEqual(resp.status, 200)
        body = json.loads(resp.body)
        profiles = body.get("profiles", [])
        for p in profiles:
            self.assertIn(
                "normalized", p,
                msg=f"Each profile should have a 'normalized' key; got keys={list(p.keys())}",
            )


class ExperimentCreateDetailNormalizedDraftTests(unittest.TestCase):
    """Legacy create is RETIRED_EXECUTION (Phase H Wave F): bounded 410,
    zero store mutation. Detail still serves stored definitions, including
    normalized_draft preserved from the pre-freeze era."""

    @classmethod
    def setUpClass(cls):
        cls.stub = _StubServer()
        cls.init_mod = _build_init_with_stub(cls.stub)

    def setUp(self):
        # Use a unique experiment_id per test to avoid cross-test collisions
        # on the filesystem store.
        self.exp_id = f"test_nd_{id(self)}"

    _DRAFT = {
        "experiment_id": "PLACEHOLDER",
        "revision": 1,
        "profile_type": "t2i",
        "generation_type": "t2i",
        "workflows": [{
            "profile_id": "p1",
            "stacks": [{
                "stack_id": "s1",
                "loader_target_group_id": "g_default",
                "main_triple": {"id": "main", "unet": "u1", "clip": "c1", "vae": "v1"},
                "selected_triple_ids": ["main"],
                "lora_selections": [
                    {"id": "L_no", "label": "No LoRA", "loras": [], "enabled": True},
                ],
            }],
        }],
        "prompts": {"items": [
            {"id": "p_a", "label": "a", "text": "hi", "negative": None, "enabled": True},
        ]},
        "axes": {"shared": {"seed": {"mode": "list", "values": [42]}}},
    }

    def _draft(self):
        draft = json.loads(json.dumps(self._DRAFT))
        draft["experiment_id"] = self.exp_id
        return draft

    def _seed_definition(self, normalized_draft=None):
        """Seed a stored definition + created event the way the retired
        create route used to (direct REGISTRY store write)."""
        import copy as _copy
        from experiment_models import CURRENT_SCHEMA_VERSION
        store = self.init_mod.REGISTRY.store(self.exp_id)
        now = "2026-08-24T00:00:00Z"
        definition = {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "experiment_id": self.exp_id,
            "revision": 1,
            "name": self.exp_id,
            "notes": "",
            "created_at": now,
            "updated_at": now,
        }
        if normalized_draft is not None:
            definition["normalized_draft"] = _copy.deepcopy(normalized_draft)
        store.write_definition(definition)
        payload = {
            "experiment_id": self.exp_id,
            "name": definition["name"],
            "compilation": {},
        }
        if normalized_draft is not None:
            payload["normalized_draft"] = _copy.deepcopy(normalized_draft)
        store.append_event({"type": "experiment.created", "payload": payload})
        return definition

    def test_create_route_retired_bounded_response_no_mutation(self):
        """POST /experiments answers 410 EXPERIMENT_RETIRED and writes
        nothing to the REGISTRY store."""
        fn = _handler_for(self.init_mod, "POST", "/comfymodal/experiments")
        req = _MockRequest(json_body={"normalized_draft": self._draft()})
        resp = _run(fn(req))
        self.assertEqual(resp.status, 410)
        body = json.loads(resp.body)
        self.assertEqual(body.get("status"), "error")
        self.assertEqual(body.get("error_code"), "EXPERIMENT_RETIRED")
        store = self.init_mod.REGISTRY.store(self.exp_id)
        self.assertIsNone(store.read_definition(), "retired create must not persist a definition")

    def test_detail_returns_normalized_draft_when_present(self):
        """GET /experiments/{id} returns normalized_draft when present
        in the stored experiment."""
        draft = self._draft()
        self._seed_definition(normalized_draft=draft)

        detail_fn = _handler_for(self.init_mod, "GET",
                                 "/comfymodal/experiments/{experiment_id}")
        req = _MockRequest(match_info={"experiment_id": self.exp_id})
        resp = _run(detail_fn(req))
        self.assertEqual(resp.status, 200, msg=f"body={resp.body}")
        body = json.loads(resp.body)
        # Currently normalized_draft may be in definition or in an event.
        # The route returns definition + events; we check that it is
        # present somewhere in the response.
        events = body.get("events", [])
        found = False
        for ev in events:
            payload = ev.get("payload", {})
            if payload.get("normalized_draft"):
                found = True
                break
        # Also check if preserved directly in an enriched definition or response key.
        nd_in_response = body.get("normalized_draft") or body.get("definition", {}).get("normalized_draft")
        self.assertTrue(
            found or bool(nd_in_response),
            msg="normalized_draft not found in events or response",
        )

    def test_detail_missing_normalized_draft_no_error(self):
        """Detail for an experiment stored without normalized_draft
        must not error."""
        self._seed_definition(normalized_draft=None)

        detail_fn = _handler_for(self.init_mod, "GET",
                                 "/comfymodal/experiments/{experiment_id}")
        req = _MockRequest(match_info={"experiment_id": self.exp_id})
        resp = _run(detail_fn(req))
        self.assertEqual(resp.status, 200)


class RicherCellNormalizedDimensionsTests(unittest.TestCase):
    """Compiled cells must carry rich normalized_dimensions metadata."""

    @classmethod
    def setUpClass(cls):
        cls.stub = _StubServer()
        cls.init_mod = _build_init_with_stub(cls.stub)

    def _compile_draft(self, draft: dict) -> dict:
        fn = _handler_for(self.init_mod, "POST", "/comfymodal/experiments/compile")
        req = _MockRequest(json_body={"normalized_draft": draft})
        resp = _run(fn(req))
        body = json.loads(resp.body)
        return body.get("compilation", {})

    def test_normalized_dimensions_has_rich_metadata(self):
        """Each cell's normalized_dimensions includes profile, triple, lora,
        prompt and image identifiers."""
        draft = {
            "experiment_id": "exp_richdim",
            "revision": 1,
            "profile_type": "t2i",
            "workflows": [{
                "profile_id": "p1",
                "stacks": [{
                    "stack_id": "s1",
                    "loader_target_group_id": "g_default",
                    "main_triple": {"id": "main", "unet": "u1", "clip": "c1", "vae": "v1"},
                    "selected_triple_ids": ["main"],
                    "lora_selections": [
                        {"id": "L_no", "label": "No LoRA", "loras": [], "enabled": True},
                    ],
                }],
            }],
            "prompts": {"items": [
                {"id": "p_a", "label": "a", "text": "hi", "negative": None, "enabled": True},
            ]},
            "axes": {"shared": {"seed": {"mode": "list", "values": [42]}}},
        }
        compil = self._compile_draft(draft)
        cells = compil.get("cells", [])
        self.assertGreater(len(cells), 0)
        for cell in cells:
            nd = cell.get("normalized_dimensions", {})
            self.assertIn("width", nd)
            self.assertIn("height", nd)
            self.assertIn("profile_id", nd)
            self.assertIn("loader_target_group_id", nd)
            self.assertIn("unet", nd)
            self.assertIn("clip", nd)
            self.assertIn("vae", nd)
            self.assertIn("lora_selection_id", nd)
            self.assertIn("prompt_id", nd)
            self.assertIn("image_id", nd)
            # Check values
            self.assertEqual(nd["profile_id"], "p1")


class StudioStoreAndModelTests(unittest.TestCase):
    """Behavior tests for the extracted Studio store and model modules."""

    def test_json_store_round_trip_and_atomic_replace(self):
        studio_store = _load_repo_module("studio_store_under_test", "studio_store.py")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "snapshots.json"
            store = studio_store.StudioJsonStore(path)
            store.write_atomic([{"id": "snap_1"}])
            self.assertEqual(store.read(), [{"id": "snap_1"}])
            self.assertFalse(path.with_suffix(path.suffix + ".tmp").exists())

    def test_json_store_does_not_treat_corrupt_json_as_empty(self):
        studio_store = _load_repo_module("studio_store_under_test_corrupt", "studio_store.py")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "snapshots.json"
            path.write_text("{not-json}", encoding="utf-8")
            store = studio_store.StudioJsonStore(path)
            with self.assertRaises(studio_store.StudioStoreError):
                store.read()

    def test_json_store_update_mutator_atomic(self):
        """update() performs read-modify-write under one lock."""
        studio_store = _load_repo_module("studio_store_update_test", "studio_store.py")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "data.json"
            store = studio_store.StudioJsonStore(path)
            store.write_atomic([{"id": "a"}, {"id": "b"}])

            def _remover(data):
                data[:] = [d for d in data if d["id"] != "a"]

            result = store.update(_remover)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["id"], "b")
            # Verify persisted
            self.assertEqual(store.read(), [{"id": "b"}])

    def test_json_store_update_mutator_writes_atomically(self):
        """update() cleans up .tmp files."""
        studio_store = _load_repo_module("studio_store_atomic_test", "studio_store.py")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "data.json"
            store = studio_store.StudioJsonStore(path)
            store.write_atomic([{"id": "x"}])

            def _noop(d):
                pass

            store.update(_noop)
            self.assertFalse(path.with_suffix(path.suffix + ".tmp").exists())

    def test_json_store_read_cache_follows_on_disk_change(self):
        """An unchanged file is served from the parse cache, but any on-disk
        change is re-parsed. ``read()`` caches on ``(st_mtime_ns, st_size)``,
        so both a size change and a same-size mtime bump must invalidate."""
        studio_store = _load_repo_module("studio_store_cache_test", "studio_store.py")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "data.json"
            store = studio_store.StudioJsonStore(path)
            store.write_atomic([{"id": "a"}])

            first = store.read()
            # Unchanged file: the parsed rows are reused, not re-parsed.
            self.assertIs(store.read(), first)

            # Same byte size, different content, explicitly bumped mtime.
            path.write_text(json.dumps([{"id": "b"}]), encoding="utf-8")
            stamp = path.stat().st_mtime_ns + 1_000_000_000
            os.utime(path, ns=(stamp, stamp))
            second = store.read()
            self.assertEqual(second, [{"id": "b"}])
            self.assertIsNot(second, first)

            # A size change alone is enough to invalidate.
            path.write_text(json.dumps([{"id": "cc"}]), encoding="utf-8")
            self.assertEqual(store.read(), [{"id": "cc"}])

    def test_json_store_update_after_read_does_not_write_cached_rows(self):
        """``update()`` must not edit the list ``read()`` already handed out:
        the mutator gets a fresh parse, and only its own result is persisted.
        This is the invariant the read cache must preserve."""
        studio_store = _load_repo_module(
            "studio_store_update_cache_test", "studio_store.py"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "data.json"
            store = studio_store.StudioJsonStore(path)
            store.write_atomic([{"id": "a"}, {"id": "b"}])

            handed_out = store.read()  # populates the cache

            def _remover(data):
                data[:] = [d for d in data if d["id"] != "a"]

            store.update(_remover)

            # The pre-update list handed to the earlier caller is untouched.
            self.assertEqual([d["id"] for d in handed_out], ["a", "b"])
            # And the persisted state reflects the mutation, not the cache.
            self.assertEqual(store.read(), [{"id": "b"}])

    def test_strict_validate_feature_ids_rejects_mixed_list(self):
        """Strict validation rejects mixed valid+unknown features."""
        studio_models = _load_repo_module("studio_models_mixed", "studio_models.py")
        with self.assertRaises(ValueError):
            studio_models._validate_feature_ids_strict(["txt2img", "bad_feature"])

    def test_strict_validate_feature_ids_rejects_all_unknown(self):
        """Strict validation rejects entirely unknown feature list."""
        studio_models = _load_repo_module("studio_models_unknown", "studio_models.py")
        with self.assertRaises(ValueError):
            studio_models._validate_feature_ids_strict(["nope", "also_nope"])

    def test_strict_validate_feature_ids_accepts_known_only(self):
        """Strict validation accepts a list of only known features."""
        studio_models = _load_repo_module("studio_models_known", "studio_models.py")
        result = studio_models._validate_feature_ids_strict(["txt2img", "object_remove"])
        self.assertEqual(result, ["txt2img", "object_remove"])

    def test_snapshot_disabled_reason_derived_server_side(self):
        """Client-provided disabledReason must be ignored on create."""
        studio_models = _load_repo_module("studio_models_disabled", "studio_models.py")
        # make_snapshot should ignore client-disabledReason
        snapshot = studio_models.make_snapshot({
            "name": "Test",
            "compatibleFeatures": ["txt2img"],
            "apiPromptJson": {"prompt": {}},
            "nodeBindings": {"prompt": "7.text"},
            "outputNodeId": "42",
            "disabledReason": "Client says disabled",  # must be ignored
        })
        self.assertNotIn("Client says disabled", snapshot.get("disabledReason", ""))
        # A runnable snapshot should have empty disabledReason
        self.assertEqual(snapshot["disabledReason"], "")

    def test_snapshot_feature_status_is_conservative_for_multi_feature_records(self):
        studio_models = _load_repo_module("studio_models_under_test", "studio_models.py")
        snapshot = studio_models.normalize_snapshot_payload({
            "name": "Multi feature snapshot",
            "compatibleFeatures": ["txt2img", "object_remove", "object_replace"],
            "graphJson": {"nodes": [], "links": []},
            "apiPromptJson": {"prompt": {}},
            "nodeBindings": {"prompt": "7.text"},
            "outputNodeId": "42",
        })
        self.assertEqual(snapshot["status"], "needs_bindings")
        self.assertEqual(snapshot["featureStatus"]["txt2img"]["status"], "runnable")
        self.assertEqual(snapshot["featureStatus"]["object_remove"]["status"], "needs_bindings")
        self.assertEqual(snapshot["featureStatus"]["object_replace"]["status"], "needs_bindings")

    def test_tightened_runnability_requires_api_prompt_and_output_for_all(self):
        """All features require outputNodeId and apiPromptJson, not just txt2img."""
        studio_models = _load_repo_module("studio_models_tight", "studio_models.py")
        # txt2img with everything: should be runnable
        snapshot = studio_models.normalize_snapshot_payload({
            "compatibleFeatures": ["txt2img"],
            "apiPromptJson": {"prompt": {}},
            "nodeBindings": {"prompt": "7.text"},
            "outputNodeId": "42",
        })
        self.assertEqual(snapshot["featureStatus"]["txt2img"]["status"], "runnable")

        # txt2img missing outputNodeId: should be needs_bindings
        snapshot2 = studio_models.normalize_snapshot_payload({
            "compatibleFeatures": ["txt2img"],
            "apiPromptJson": {"prompt": {}},
            "nodeBindings": {"prompt": "7.text"},
        })
        self.assertEqual(snapshot2["featureStatus"]["txt2img"]["status"], "needs_bindings")

        # object_remove missing apiPromptJson: should be needs_api_prompt
        snapshot3 = studio_models.normalize_snapshot_payload({
            "compatibleFeatures": ["object_remove"],
            "apiPromptJson": None,
            "nodeBindings": {
                "source_image": {"kind": "node", "nodeId": "7"},
                "mask": {"kind": "node", "nodeId": "8"},
                "instruction": {"kind": "widget", "nodeId": "9", "widgetName": "text"},
            },
            "outputNodeId": "42",
        })
        self.assertEqual(snapshot3["featureStatus"]["object_remove"]["status"], "needs_api_prompt")

        # object_replace missing outputNodeId: should be needs_bindings
        snapshot4 = studio_models.normalize_snapshot_payload({
            "compatibleFeatures": ["object_replace"],
            "apiPromptJson": {"prompt": {}},
            "nodeBindings": {
                "source_image": {"kind": "node", "nodeId": "7"},
                "mask": {"kind": "node", "nodeId": "8"},
                "replacement_prompt": {"kind": "widget", "nodeId": "9", "widgetName": "text"},
            },
        })
        self.assertEqual(snapshot4["featureStatus"]["object_replace"]["status"], "needs_bindings")

    def test_preset_import_only_without_snapshot(self):
        """Import sourceType without snapshotId yields import_only status."""
        studio_models = _load_repo_module("studio_models_import", "studio_models.py")
        preset = studio_models.normalize_preset_payload(
            {"label": "Import preset", "sourceType": "import", "snapshotId": ""},
            snapshots_by_id={},
        )
        self.assertEqual(preset["status"], "import_only")
        self.assertIn("import", preset.get("disabledReason", "").lower())

    def test_preset_metadata_only_without_snapshot(self):
        """Legacy sourceType without snapshotId yields metadata_only status."""
        studio_models = _load_repo_module("studio_models_legacy", "studio_models.py")
        preset = studio_models.normalize_preset_payload(
            {"label": "Legacy preset", "sourceType": "legacy", "snapshotId": ""},
            snapshots_by_id={},
        )
        self.assertEqual(preset["status"], "metadata_only")
        self.assertIn("legacy", preset.get("disabledReason", "").lower())

    def test_preset_manual_without_snapshot_is_invalid(self):
        """Manual sourceType without snapshotId is invalid (not import_only)."""
        studio_models = _load_repo_module("studio_models_manual", "studio_models.py")
        preset = studio_models.normalize_preset_payload(
            {"label": "Manual preset", "sourceType": "manual", "snapshotId": ""},
            snapshots_by_id={},
        )
        self.assertEqual(preset["status"], "invalid")
        self.assertIn("does not reference", preset.get("disabledReason", ""))

    def test_preset_missing_snapshot_is_invalid(self):
        studio_models = _load_repo_module("studio_models_under_test_preset", "studio_models.py")
        preset = studio_models.normalize_preset_payload(
            {
                "label": "Broken preset",
                "snapshotId": "missing_snapshot",
                "sourceType": "snapshot",
            },
            snapshots_by_id={},
        )
        self.assertEqual(preset["status"], "invalid")
        self.assertEqual(preset["disabledReason"], "Preset references a missing snapshot")

    def test_make_snapshot_rejects_unknown_features(self):
        """make_snapshot raises ValueError for unknown features."""
        studio_models = _load_repo_module("studio_models_ms_rej", "studio_models.py")
        with self.assertRaises(ValueError):
            studio_models.make_snapshot({
                "name": "Bad",
                "compatibleFeatures": ["fake_feature"],
            })

    def test_make_preset_rejects_unknown_features(self):
        """make_preset raises ValueError for unknown features."""
        studio_models = _load_repo_module("studio_models_mp_rej", "studio_models.py")
        with self.assertRaises(ValueError):
            studio_models.make_preset(
                {"label": "Bad", "compatibleFeatures": ["fake"]},
                snapshots_by_id={},
            )

    def test_update_snapshot_ignores_client_disabled_reason(self):
        """update_snapshot ignores client-provided disabledReason."""
        studio_models = _load_repo_module("studio_models_udr", "studio_models.py")
        snapshot = {
            "id": "snap_1",
            "name": "Test",
            "compatibleFeatures": ["txt2img"],
            "nodeBindings": {"prompt": "7.text"},
            "outputNodeId": "42",
            "apiPromptJson": {"prompt": {}},
        }
        studio_models.update_snapshot(snapshot, {"disabledReason": "Client reason"})
        self.assertNotEqual(snapshot.get("disabledReason"), "Client reason")
        self.assertEqual(snapshot["disabledReason"], "")  # runnable → no disabledReason

    def test_update_preset_ignores_client_disabled_reason(self):
        """update_preset ignores client-provided disabledReason."""
        studio_models = _load_repo_module("studio_models_updr", "studio_models.py")
        preset = {
            "id": "preset_1",
            "label": "Test",
            "snapshotId": "snap_ok",
            "sourceType": "snapshot",
        }
        snapshots_by_id = {
            "snap_ok": {"id": "snap_ok", "status": "runnable", "compatibleFeatures": ["txt2img"]}
        }
        studio_models.update_preset(preset, {"disabledReason": "Client reason"}, snapshots_by_id)
        self.assertNotEqual(preset.get("disabledReason"), "Client reason")
        # runnable preset with runnable snapshot should have empty disabledReason
        self.assertEqual(preset["disabledReason"], "")


class StudioRouteBehaviourTests(unittest.TestCase):
    """Behavior tests for extracted Studio snapshot/preset routes."""

    @classmethod
    def setUpClass(cls):
        cls.routes_mod = _load_repo_module("studio_routes_under_test", "studio_routes.py")

    def _register(self, tmpdir: str):
        stub = _StubServer()
        self.routes_mod.register_studio_routes(stub, node_dir=tmpdir)
        return type("StudioModule", (), {"_server": stub})

    def test_snapshot_list_hides_archived_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / ".studio_snapshots.json"
            path.write_text(json.dumps([
                {"id": "snap_live", "name": "Live", "archived": False},
                {"id": "snap_old", "name": "Old", "archived": True},
            ]), encoding="utf-8")
            mod = self._register(tmpdir)
            fn = _handler_for(mod, "GET", "/comfymodal/studio/snapshots")
            resp = _run(fn(_MockRequest()))
            body = json.loads(resp.body)
            ids = [item["id"] for item in body.get("snapshots", [])]
            self.assertEqual(ids, ["snap_live"])

    def test_snapshot_list_can_include_archived(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / ".studio_snapshots.json"
            path.write_text(json.dumps([
                {"id": "snap_live", "name": "Live", "archived": False},
                {"id": "snap_old", "name": "Old", "archived": True},
            ]), encoding="utf-8")
            mod = self._register(tmpdir)
            fn = _handler_for(mod, "GET", "/comfymodal/studio/snapshots")
            resp = _run(fn(_MockRequest(query={"includeArchived": "1"})))
            body = json.loads(resp.body)
            ids = [item["id"] for item in body.get("snapshots", [])]
            self.assertEqual(ids, ["snap_live", "snap_old"])

    def test_snapshot_list_re_normalizes_status(self):
        """List response re-normalizes snapshots even if stored status is stale."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Store a snapshot with stale "runnable" status but missing apiPromptJson
            path = Path(tmpdir) / ".studio_snapshots.json"
            path.write_text(json.dumps([{
                "id": "snap_stale",
                "name": "Stale",
                "compatibleFeatures": ["txt2img"],
                "nodeBindings": {"prompt": "7.text"},
                "outputNodeId": "42",
                "apiPromptJson": None,
                "archived": False,
                "status": "runnable",
            }]), encoding="utf-8")
            mod = self._register(tmpdir)
            fn = _handler_for(mod, "GET", "/comfymodal/studio/snapshots")
            resp = _run(fn(_MockRequest()))
            body = json.loads(resp.body)
            snapshots = body.get("snapshots", [])
            self.assertEqual(len(snapshots), 1)
            # With tightened rules, missing apiPromptJson → needs_api_prompt
            self.assertEqual(snapshots[0]["status"], "needs_api_prompt")

    def test_snapshot_detail_re_normalizes_status(self):
        """Detail response re-normalizes snapshot status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / ".studio_snapshots.json"
            path.write_text(json.dumps([{
                "id": "snap_detail",
                "name": "Detail",
                "compatibleFeatures": ["txt2img"],
                "nodeBindings": {},
                "outputNodeId": "",
                "apiPromptJson": None,
                "archived": False,
                "status": "runnable",
            }]), encoding="utf-8")
            mod = self._register(tmpdir)
            fn = _handler_for(mod, "GET", "/comfymodal/studio/snapshots/{snapshot_id}")
            resp = _run(fn(_MockRequest(match_info={"snapshot_id": "snap_detail"})))
            body = json.loads(resp.body)
            self.assertEqual(body.get("snapshot", {}).get("status"), "needs_bindings")

    def test_snapshot_create_rejects_mixed_features_with_stable_message(self):
        """Create rejects mixed valid+unknown feature IDs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mod = self._register(tmpdir)
            fn = _handler_for(mod, "POST", "/comfymodal/studio/snapshots")
            resp = _run(fn(_MockRequest(json_body={
                "name": "Mixed snapshot",
                "compatibleFeatures": ["txt2img", "bad_feature"],
            })))
            self.assertEqual(resp.status, 400)
            body = json.loads(resp.body)
            self.assertEqual(body.get("message"), "Invalid compatible feature")

    def test_snapshot_create_rejects_invalid_feature_with_stable_message(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mod = self._register(tmpdir)
            fn = _handler_for(mod, "POST", "/comfymodal/studio/snapshots")
            resp = _run(fn(_MockRequest(json_body={
                "name": "Bad snapshot",
                "compatibleFeatures": ["definitely_fake"],
            })))
            self.assertEqual(resp.status, 400)
            body = json.loads(resp.body)
            self.assertEqual(body.get("message"), "Invalid compatible feature")

    def test_snapshot_create_ignores_client_disabled_reason(self):
        """Client-provided disabledReason is ignored on snapshot create."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mod = self._register(tmpdir)
            fn = _handler_for(mod, "POST", "/comfymodal/studio/snapshots")
            resp = _run(fn(_MockRequest(json_body={
                "name": "Test snapshot",
                "compatibleFeatures": ["txt2img"],
                "apiPromptJson": {"prompt": {}},
                "nodeBindings": {"prompt": "7.text"},
                "outputNodeId": "42",
                "disabledReason": "Client says disabled",
            })))
            self.assertEqual(resp.status, 200)
            body = json.loads(resp.body)
            snapshot = body.get("snapshot", {})
            self.assertNotEqual(snapshot.get("disabledReason"), "Client says disabled")

    def test_preset_create_rejects_missing_snapshot_with_stable_message(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mod = self._register(tmpdir)
            fn = _handler_for(mod, "POST", "/comfymodal/studio/presets")
            resp = _run(fn(_MockRequest(json_body={
                "label": "Missing snapshot preset",
                "snapshotId": "missing_snapshot",
                "sourceType": "snapshot",
            })))
            self.assertEqual(resp.status, 400)
            body = json.loads(resp.body)
            self.assertEqual(body.get("message"), "Preset references a missing snapshot")

    def test_preset_create_allows_import_without_snapshot(self):
        """Import preset without snapshotId is allowed (import_only)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mod = self._register(tmpdir)
            fn = _handler_for(mod, "POST", "/comfymodal/studio/presets")
            resp = _run(fn(_MockRequest(json_body={
                "label": "Import preset",
                "sourceType": "import",
                "snapshotId": "",
            })))
            self.assertEqual(resp.status, 200)
            body = json.loads(resp.body)
            preset = body.get("preset", {})
            self.assertEqual(preset.get("status"), "import_only")

    def test_preset_create_rejects_manual_without_snapshot(self):
        """Manual preset without snapshotId is rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mod = self._register(tmpdir)
            fn = _handler_for(mod, "POST", "/comfymodal/studio/presets")
            resp = _run(fn(_MockRequest(json_body={
                "label": "Manual preset",
                "sourceType": "manual",
                "snapshotId": "",
            })))
            self.assertEqual(resp.status, 400)
            body = json.loads(resp.body)
            self.assertIn("does not reference", body.get("message", ""))

    def test_preset_update_rejects_invalid_snapshot_id(self):
        """Updating snapshotId to a missing snapshot returns 400."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a valid preset first
            presets_path = Path(tmpdir) / ".studio_presets.json"
            presets_path.write_text(json.dumps([{
                "id": "preset_1",
                "label": "Original",
                "snapshotId": "",
                "sourceType": "snapshot",
                "archived": False,
                "createdAt": "2024-01-01T00:00:00",
                "updatedAt": "2024-01-01T00:00:00",
            }]), encoding="utf-8")
            snapshots_path = Path(tmpdir) / ".studio_snapshots.json"
            snapshots_path.write_text(json.dumps([]), encoding="utf-8")
            mod = self._register(tmpdir)
            fn = _handler_for(mod, "PATCH", "/comfymodal/studio/presets/{preset_id}")
            resp = _run(fn(_MockRequest(
                json_body={"snapshotId": "nonexistent_snap"},
                match_info={"preset_id": "preset_1"},
            )))
            self.assertEqual(resp.status, 400)
            body = json.loads(resp.body)
            self.assertEqual(body.get("message"), "Preset references a missing snapshot")

    def test_snapshot_duplicate_re_normalizes_status(self):
        """Duplicate re-derives status instead of inheriting stale value."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / ".studio_snapshots.json"
            path.write_text(json.dumps([{
                "id": "snap_src",
                "name": "Source",
                "compatibleFeatures": ["txt2img"],
                "nodeBindings": {"prompt": "7.text"},
                "outputNodeId": "42",
                "apiPromptJson": None,
                "archived": False,
                "status": "runnable",  # stale – should be needs_api_prompt
            }]), encoding="utf-8")
            mod = self._register(tmpdir)
            fn = _handler_for(mod, "POST", "/comfymodal/studio/snapshots/{snapshot_id}/duplicate")
            resp = _run(fn(_MockRequest(match_info={"snapshot_id": "snap_src"})))
            self.assertEqual(resp.status, 200)
            body = json.loads(resp.body)
            dup = body.get("snapshot", {})
            self.assertEqual(dup.get("status"), "needs_api_prompt")
            self.assertNotEqual(dup.get("id"), "snap_src")
            self.assertIn("(Copy)", dup.get("name", ""))

    def test_preset_duplicate_re_normalizes_status(self):
        """Preset duplicate re-derives status instead of inheriting stale value."""
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshots_path = Path(tmpdir) / ".studio_snapshots.json"
            snapshots_path.write_text(json.dumps([{
                "id": "snap_ok",
                "name": "Good Snapshot",
                "compatibleFeatures": ["txt2img"],
                "status": "runnable",
            }]), encoding="utf-8")
            presets_path = Path(tmpdir) / ".studio_presets.json"
            presets_path.write_text(json.dumps([{
                "id": "preset_src",
                "label": "Source Preset",
                "snapshotId": "snap_ok",
                "sourceType": "snapshot",
                "archived": False,
                "createdAt": "2024-01-01T00:00:00",
                "updatedAt": "2024-01-01T00:00:00",
                "status": "invalid",  # stale — should be "runnable" after re-derive
            }]), encoding="utf-8")
            mod = self._register(tmpdir)
            fn = _handler_for(mod, "POST", "/comfymodal/studio/presets/{preset_id}/duplicate")
            resp = _run(fn(_MockRequest(match_info={"preset_id": "preset_src"})))
            self.assertEqual(resp.status, 200)
            body = json.loads(resp.body)
            dup = body.get("preset", {})
            self.assertEqual(dup.get("status"), "runnable")
            self.assertNotEqual(dup.get("id"), "preset_src")
            self.assertIn("(Copy)", dup.get("label", ""))

    def test_studio_output_serves_legacy_comfyui_output_file(self):
        """History images may still live in ComfyUI's standard output dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            node_dir = Path(tmpdir) / "ComfyUI" / "custom_nodes" / "comfyui-modal"
            output_dir = node_dir.parent.parent / "output"
            output_dir.mkdir(parents=True)
            image_path = output_dir / "production_test.png"
            image_bytes = b"not-a-real-png-but-valid-route-data"
            image_path.write_bytes(image_bytes)

            stub = _StubServer()
            self.routes_mod.register_studio_routes(stub, node_dir=node_dir)
            handler = _handler_for(
                type("StudioModule", (), {"_server": stub}),
                "GET",
                "/comfymodal/studio/outputs/{filename:.*}",
            )
            response = _run(handler(_MockRequest(
                match_info={"filename": image_path.name},
            )))

            self.assertEqual(response.status, 200)
            self.assertEqual(response.body, image_bytes)
            self.assertEqual(response.content_type, "image/png")

    def test_studio_output_serves_configured_comfyui_output_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            node_dir = Path(tmpdir) / "ComfyUI" / "custom_nodes" / "comfyui-modal"
            configured_output = Path(tmpdir) / "configured-output"
            configured_output.mkdir(parents=True)
            image_path = configured_output / "production_configured.png"
            image_bytes = b"configured-output"
            image_path.write_bytes(image_bytes)

            folder_paths_stub = type(sys)("folder_paths")
            folder_paths_stub.get_output_directory = lambda: str(configured_output)
            previous = sys.modules.get("folder_paths")
            sys.modules["folder_paths"] = folder_paths_stub
            try:
                stub = _StubServer()
                self.routes_mod.register_studio_routes(stub, node_dir=node_dir)
                handler = _handler_for(
                    type("StudioModule", (), {"_server": stub}),
                    "GET",
                    "/comfymodal/studio/outputs/{filename:.*}",
                )
                response = _run(handler(_MockRequest(
                    match_info={"filename": image_path.name},
                )))
            finally:
                if previous is None:
                    sys.modules.pop("folder_paths", None)
                else:
                    sys.modules["folder_paths"] = previous

            self.assertEqual(response.status, 200)
            self.assertEqual(response.body, image_bytes)
            self.assertEqual(response.content_type, "image/png")

    def test_studio_output_rejects_path_traversal(self):
        """The output route accepts basenames only, never path traversal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            stub = _StubServer()
            self.routes_mod.register_studio_routes(stub, node_dir=tmpdir)
            handler = _handler_for(
                type("StudioModule", (), {"_server": stub}),
                "GET",
                "/comfymodal/studio/outputs/{filename:.*}",
            )
            response = _run(handler(_MockRequest(
                match_info={"filename": "..\\outside.png"},
            )))

            self.assertEqual(response.status, 404)

    def test_storage_error_returns_stable_message(self):
        """Storage errors return stable messages, not raw exceptions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Corrupt the snapshots file to trigger a read error
            path = Path(tmpdir) / ".studio_snapshots.json"
            path.write_text("not-json", encoding="utf-8")
            mod = self._register(tmpdir)
            fn = _handler_for(mod, "GET", "/comfymodal/studio/snapshots")
            resp = _run(fn(_MockRequest()))
            self.assertEqual(resp.status, 500)
            body = json.loads(resp.body)
            # Must not contain raw exception details like "Corrupt JSON"
            self.assertNotIn("Corrupt JSON", body.get("message", ""))
            self.assertIn("read error", body.get("message", "").lower())


if __name__ == "__main__":
    unittest.main()
