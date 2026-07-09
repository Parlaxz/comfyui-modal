"""Test the HTTP routes registered by comfyui-modal for the testing suite.

These tests load ``__init__.py`` (or a thin shim) with the ``_server``
attribute replaced by a minimal ``PromptServer`` stub so the route
decorators execute.  Each test then constructs an ``aiohttp`` test
client to exercise the route end-to-end.
"""
import asyncio
import importlib.util
import json
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
    """The experiment create route should persist and return normalized_draft."""

    @classmethod
    def setUpClass(cls):
        cls.stub = _StubServer()
        cls.init_mod = _build_init_with_stub(cls.stub)

    def setUp(self):
        # Use a unique experiment_id per test to avoid cross-test collisions
        # on the filesystem store.
        self.exp_id = f"test_nd_{id(self)}"

    # ── compile → create → detail round-trip with normalized_draft ─────

    def test_create_with_normalized_draft_returns_ok(self):
        """POST /experiments with normalized_draft returns 200."""
        fn = _handler_for(self.init_mod, "POST", "/comfymodal/experiments")
        draft = {
            "experiment_id": self.exp_id,
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
        req = _MockRequest(json_body={"normalized_draft": draft})
        resp = _run(fn(req))
        self.assertEqual(resp.status, 200)
        body = json.loads(resp.body)
        self.assertEqual(body.get("status"), "ok")

    def test_detail_returns_normalized_draft_when_present(self):
        """GET /experiments/{id} returns normalized_draft when present
        in the stored experiment."""
        # Create first.
        create_fn = _handler_for(self.init_mod, "POST", "/comfymodal/experiments")
        draft = {
            "experiment_id": self.exp_id,
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
        _run(create_fn(_MockRequest(json_body={"normalized_draft": draft})))

        # Detail.
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
        """Detail for an experiment created without normalized_draft
        must not error."""
        create_fn = _handler_for(self.init_mod, "POST", "/comfymodal/experiments")
        spec = {
            "experiment_id": self.exp_id,
            "revision": 1,
            "name": "legacy",
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
        _run(create_fn(_MockRequest(json_body={"spec": spec})))

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


if __name__ == "__main__":
    unittest.main()
