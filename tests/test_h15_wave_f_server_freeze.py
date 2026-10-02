"""Phase H15 — Wave F: server-side compatibility & legacy write freeze.

Frozen authority:
  - PHASE_H5_CONSOLIDATION_CONTRACT_FREEZE_2026-08-23.md, H5 Follow-Up D
    (FD-1…FD-26; FD-9/10/11/12/14/15/16/17/18/20/21 are binding here)
  - PHASE_H5D_WAVE_E_CONVERGENCE_WAVE_F_FREEZE_2026-08-24.md

What this suite proves (FD-23 matrix, server lane):
  1. The six retired Comparison mutations answer 409 COMPARISON_READ_ONLY
     and leave stored Comparison data byte-identical.
  2. All ten Comparison COMPAT_READ routes still answer seeded data;
     validate/detect-slots keep their pure-compute POST semantics.
  3. /comparison/run stays 410 COMPARISON_RETIRED.
  4. Retired legacy Experiment execution routes answer 410
     EXPERIMENT_RETIRED and retired write routes answer 409
     EXPERIMENT_READ_ONLY with zero REGISTRY/store mutation.
  5. Protected transitional seams are untouched: GET /experiments/{id}
     (200 shape + 404 unknown) and POST .../stop-now (404 unknown,
     scheduler/pending logic intact).
  6. POST /studio/experiment is bounded 410 EXPERIMENT_RETIRED before any
     preset load / REGISTRY creation / History V2 ensure / scheduler start.
  7. Warmup run cannot execute (410 WARMUP_RETIRED, zero streaming);
     invalidate is 409 WARMUP_RETIRED with a byte-identical state file;
     status still reads. Shared run_prompt_stream survives for V2.
  8. /auth/setup is 409 AUTH_SETUP_RETIRED with zero modal.toml /
     workspace / deploy-thread side effects.
  9. Legacy .presets/prompts|images writers are 409
     LEGACY_PRESETS_READ_ONLY byte-intact; reads survive.
  10. /studio/backends writers are 409 BACKENDS_READ_ONLY byte-intact;
     GET (incl. ?kind=comparable) still answers stored data.
  11. Negative guards against over-freezing: /studio/presets* CRUD stays
     live, Workflow Presets stay distinct, run-history reads survive and
     annotations/save remain COMPAT_WRITE.
  12. Route registry unchanged: every frozen route remains REGISTERED.

Run directly: python -m unittest tests.test_h15_wave_f_server_freeze -v
Registered in tests/run_studio_tests.py by H17 F-TST (after
tests.test_h14_wave_e_retirement, same in-process __init__ harness ordering).
Read-only against production data; no network, no Modal, no GPU.
"""
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
NODE_DIR = REPO_ROOT

sys.path.insert(0, str(REPO_ROOT))

from tests.test_routes_registered import (  # noqa: E402
    _MockRequest,
    _StubServer,
    _build_init_with_stub,
    _handler_for,
    _run,
)

_H15 = {"stub": None, "init": None}


def _harness():
    """Build the stubbed __init__ module once for this file."""
    if _H15["init"] is None:
        stub = _StubServer()
        init_mod = _build_init_with_stub(stub)
        _H15["stub"] = stub
        _H15["init"] = init_mod
    return _H15["stub"], _H15["init"]


def _snapshot(root: Path) -> dict:
    out = {}
    for p in sorted(Path(root).rglob("*")):
        if p.is_file():
            out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def _body(resp) -> dict:
    return json.loads(resp.body)


_COMPARISON_WRITE_MSG = (
    "Comparison stores are read-only compatibility data "
    "(Phase H Wave F). Stored profiles and historical results "
    "remain readable."
)

_WORKFLOW_API = {
    "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "u1"}},
    "2": {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": "c1"}},
    "3": {"class_type": "VAELoader", "inputs": {"vae_name": "v1"}},
    "10": {"class_type": "CLIPTextEncode", "inputs": {"text": "x"}},
}


# ---------------------------------------------------------------------------
# 1-4. Comparison split: writers frozen, reads alive, run stays retired
# ---------------------------------------------------------------------------


class ComparisonWriteFreezeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stub, cls.init = _harness()

    def _call(self, method, path, match=None, body=None):
        fn = _handler_for(self.init, method, path)
        self.assertIsNotNone(fn, f"{method} {path} must stay registered")
        req = _MockRequest(json_body=body if body is not None else {"x": 1},
                           match_info=match or {})
        return _run(fn(req))

    def test_six_writers_return_409_comparison_read_only(self):
        cases = [
            ("POST", "/comfymodal/comparison/profiles", {}, {"name": "n"}),
            ("PUT", "/comfymodal/comparison/profiles/{profile_id}",
             {"profile_id": "p"}, {"name": "n"}),
            ("DELETE", "/comfymodal/comparison/profiles/{profile_id}",
             {"profile_id": "p"}, {}),
            ("POST", "/comfymodal/comparison/profiles/{profile_id}/duplicate",
             {"profile_id": "p"}, {"name": "n2"}),
            ("POST", "/comfymodal/comparison/profiles/{profile_id}/slots",
             {"profile_id": "p"}, {"slots": {"a": "b"}}),
            ("POST", "/comfymodal/comparison/config", {}, {"concurrency": 2}),
        ]
        for method, path, match, body in cases:
            with self.subTest(method=method, path=path):
                resp = self._call(method, path, match, body)
                self.assertEqual(resp.status, 409)
                payload = _body(resp)
                self.assertEqual(payload["status"], "error")
                self.assertEqual(payload["error_code"], "COMPARISON_READ_ONLY")
                self.assertEqual(payload["message"], _COMPARISON_WRITE_MSG)

    def test_writers_and_run_leave_stores_byte_identical(self):
        import comparison
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            created = comparison.create_profile(
                comfyui_root=str(root), name="KeepMe", workflow_api=_WORKFLOW_API)
            comparison.save_comparison_config(str(root), {"concurrency": 1})
            before = _snapshot(root)
            original_root = self.init._COMFYUI_ROOT
            self.init._COMFYUI_ROOT = str(root)
            try:
                frozen = [
                    ("POST", "/comfymodal/comparison/profiles", {}, {"name": "New"}),
                    ("PUT", "/comfymodal/comparison/profiles/{profile_id}",
                     {"profile_id": created["id"]}, {"name": "Edit"}),
                    ("DELETE", "/comfymodal/comparison/profiles/{profile_id}",
                     {"profile_id": created["id"]}, {}),
                    ("POST", "/comfymodal/comparison/profiles/{profile_id}/duplicate",
                     {"profile_id": created["id"]}, {"name": "Dup"}),
                    ("POST", "/comfymodal/comparison/profiles/{profile_id}/slots",
                     {"profile_id": created["id"]}, {"slots": {"seed": "5"}}),
                    ("POST", "/comfymodal/comparison/config", {}, {"concurrency": 9}),
                    ("POST", "/comfymodal/comparison/run", {},
                     {"profile_ids": [created["id"]], "prompt": "nope"}),
                ]
                statuses = []
                for method, path, match, body in frozen:
                    resp = self._call(method, path, match, body)
                    statuses.append(resp.status)
                self.assertEqual(statuses, [409] * 6 + [410])
            finally:
                self.init._COMFYUI_ROOT = original_root
            self.assertEqual(_snapshot(root), before,
                             "retired Comparison requests must not mutate stored data")

    def test_run_stays_410_comparison_retired(self):
        fn = _handler_for(self.init, "POST", "/comfymodal/comparison/run")
        resp = _run(fn(_MockRequest(json_body={"profile_ids": ["p"]})))
        self.assertEqual(resp.status, 410)
        payload = _body(resp)
        self.assertEqual(payload["error_code"], "COMPARISON_RETIRED")

    def test_all_seventeen_comparison_routes_registered(self):
        expected = {
            ("GET", "/comfymodal/comparison/profiles"),
            ("POST", "/comfymodal/comparison/profiles"),
            ("GET", "/comfymodal/comparison/profiles/{profile_id}"),
            ("PUT", "/comfymodal/comparison/profiles/{profile_id}"),
            ("DELETE", "/comfymodal/comparison/profiles/{profile_id}"),
            ("POST", "/comfymodal/comparison/profiles/{profile_id}/duplicate"),
            ("POST", "/comfymodal/comparison/profiles/{profile_id}/validate"),
            ("POST", "/comfymodal/comparison/profiles/{profile_id}/detect-slots"),
            ("POST", "/comfymodal/comparison/profiles/{profile_id}/slots"),
            ("POST", "/comfymodal/comparison/run"),
            ("GET", "/comfymodal/comparison/results"),
            ("GET", "/comfymodal/comparison/results/{comparison_id}"),
            ("GET", "/comfymodal/comparison/profiles/{profile_id}/workflow/nodes"),
            ("GET", "/comfymodal/comparison/profiles/{profile_id}/workflow"),
            ("GET", "/comfymodal/comparison/config"),
            ("POST", "/comfymodal/comparison/config"),
            ("GET", "/comfymodal/comparison/gallery/{comparison_id}"),
        }
        registered = {(m, p) for m, p, _ in self.stub.routes._handlers
                      if "/comparison" in p}
        self.assertTrue(expected.issubset(registered),
                        f"missing: {sorted(expected - registered)}")


class ComparisonReadCompatTests(unittest.TestCase):
    """All ten COMPAT_READ routes still answer seeded data."""

    @classmethod
    def setUpClass(cls):
        cls.stub, cls.init = _harness()
        import comparison
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        root = Path(cls.tmp.name)
        created = comparison.create_profile(
            comfyui_root=str(root), name="Reader", workflow_api=_WORKFLOW_API)
        cls.profile_id = created["id"]
        cls.original_root = cls.init._COMFYUI_ROOT
        cls.init._COMFYUI_ROOT = str(root)

    @classmethod
    def tearDownClass(cls):
        cls.init._COMFYUI_ROOT = cls.original_root

    def _call(self, method, path, match=None, body=None, query=None):
        fn = _handler_for(self.init, method, path)
        self.assertIsNotNone(fn, f"{method} {path} must stay registered")
        req = _MockRequest(json_body=body, query=query, match_info=match or {})
        return _run(fn(req))

    def test_ten_read_routes_answer_from_stored_data(self):
        pid = self.profile_id
        checks = [
            ("GET", "/comfymodal/comparison/profiles", {}, None, 200, "profiles"),
            ("GET", "/comfymodal/comparison/profiles/{profile_id}",
             {"profile_id": pid}, None, 200, "profile"),
            # Pure-compute POSTs stay COMPAT_READ semantically (FD-9).
            ("POST", "/comfymodal/comparison/profiles/{profile_id}/validate",
             {"profile_id": pid}, {}, 200, "validation"),
            ("POST", "/comfymodal/comparison/profiles/{profile_id}/detect-slots",
             {"profile_id": pid}, {}, 200, "candidates"),
            ("GET", "/comfymodal/comparison/results", {}, None, 200, "runs"),
            ("GET", "/comfymodal/comparison/results/{comparison_id}",
             {"comparison_id": "nope"}, None, 404, None),
            ("GET", "/comfymodal/comparison/profiles/{profile_id}/workflow/nodes",
             {"profile_id": pid}, None, 200, "nodes"),
            ("GET", "/comfymodal/comparison/profiles/{profile_id}/workflow",
             {"profile_id": pid}, None, 200, None),
            ("GET", "/comfymodal/comparison/config", {}, None, 200, "config"),
            ("GET", "/comfymodal/comparison/gallery/{comparison_id}",
             {"comparison_id": "nope"}, None, 404, None),
        ]
        for method, path, match, body, want_status, want_key in checks:
            with self.subTest(method=method, path=path):
                resp = self._call(method, path, match, body)
                self.assertEqual(resp.status, want_status)
                if want_key:
                    self.assertIn(want_key, _body(resp))

    def test_profile_list_contains_seeded_profile(self):
        resp = self._call("GET", "/comfymodal/comparison/profiles")
        ids = [p["id"] for p in _body(resp)["profiles"]]
        self.assertIn(self.profile_id, ids)

    def test_validate_and_detect_slots_are_not_409(self):
        pid = self.profile_id
        for path in ("validate", "detect-slots"):
            resp = self._call(
                "POST",
                f"/comfymodal/comparison/profiles/{{profile_id}}/{path}",
                {"profile_id": pid}, {})
            self.assertEqual(resp.status, 200, f"{path} must stay pure compute")


# ---------------------------------------------------------------------------
# 5-7. Legacy experiment retirement + protected seams
# ---------------------------------------------------------------------------


class ExperimentRetirementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stub, cls.init = _harness()

    EXEC_410 = [
        ("POST", "/comfymodal/experiments"),
        ("POST", "/comfymodal/experiments/{experiment_id}/start"),
        ("POST", "/comfymodal/experiments/{experiment_id}/resume"),
        ("POST", "/comfymodal/experiments/{experiment_id}/run-missing"),
        ("POST", "/comfymodal/experiments/{experiment_id}/checkpoints/{checkpoint_id}/continue"),
        ("POST", "/comfymodal/experiments/{experiment_id}/checkpoints/{checkpoint_id}/restart"),
        ("POST", "/comfymodal/experiments/{experiment_id}/checkpoints/{checkpoint_id}/restart-from"),
        ("POST", "/comfymodal/experiments/{experiment_id}/cells/{cell_key}/rerun"),
        ("POST", "/comfymodal/experiments/{experiment_id}/rerun-selected"),
    ]
    WRITE_409 = [
        ("POST", "/comfymodal/experiments/{experiment_id}/pause"),
        ("POST", "/comfymodal/experiments/{experiment_id}/stop-after-current"),
        ("POST", "/comfymodal/experiments/{experiment_id}/clone"),
        ("POST", "/comfymodal/experiments/{experiment_id}/checkpoints/{checkpoint_id}/skip"),
        ("POST", "/comfymodal/experiments/{experiment_id}/checkpoints/{checkpoint_id}/unskip"),
    ]

    def _match_for(self, path):
        names = {
            "experiment_id": "exp_h15",
            "checkpoint_id": "ck_h15",
            "cell_key": "cell_h15",
        }
        out = {}
        for key, val in names.items():
            if f"{{{key}}}" in path:
                out[key] = val
        return out

    def test_execution_routes_return_410_experiment_retired(self):
        for method, path in self.EXEC_410:
            with self.subTest(path=path):
                fn = _handler_for(self.init, method, path)
                self.assertIsNotNone(fn, f"{method} {path} must stay registered")
                resp = _run(fn(_MockRequest(json_body={"spec": {}},
                                            match_info=self._match_for(path))))
                self.assertEqual(resp.status, 410)
                payload = _body(resp)
                self.assertEqual(payload["status"], "error")
                self.assertEqual(payload["error_code"], "EXPERIMENT_RETIRED")

    def test_write_routes_return_409_experiment_read_only(self):
        for method, path in self.WRITE_409:
            with self.subTest(path=path):
                fn = _handler_for(self.init, method, path)
                self.assertIsNotNone(fn, f"{method} {path} must stay registered")
                resp = _run(fn(_MockRequest(json_body={"experiment_id": "x"},
                                            match_info=self._match_for(path))))
                self.assertEqual(resp.status, 409)
                payload = _body(resp)
                self.assertEqual(payload["status"], "error")
                self.assertEqual(payload["error_code"], "EXPERIMENT_READ_ONLY")

    def test_retired_requests_mutate_zero_registry_data(self):
        import experiment_service
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(experiment_service, "experiments_root",
                                   lambda: Path(tmp)):
                before = _snapshot(Path(tmp))
                for method, path in self.EXEC_410 + self.WRITE_409:
                    fn = _handler_for(self.init, method, path)
                    resp = _run(fn(_MockRequest(
                        json_body={"spec": {}, "cell_keys": ["c"]},
                        match_info=self._match_for(path))))
                    self.assertIn(resp.status, (409, 410))
                self.assertEqual(_snapshot(Path(tmp)), before,
                                 "retired experiment requests must not mutate REGISTRY stores")

    def test_compile_remains_pure_compute_and_untouched(self):
        """FD-12: compile is ZERO_CALLER non-persisting — Wave F leaves it."""
        fn = _handler_for(self.init, "POST", "/comfymodal/experiments/compile")
        spec = {
            "experiment_id": "exp_h15_compile",
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
        resp = _run(fn(_MockRequest(json_body={"spec": spec})))
        self.assertEqual(resp.status, 200)
        self.assertEqual(_body(resp).get("status"), "ok")

    def test_reads_remain_compat_read(self):
        import experiment_service
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        with mock.patch.object(experiment_service, "experiments_root",
                               lambda: Path(tmp.name)):
            store = self.init.REGISTRY.store("exp_h15_reads")
            store.write_definition({
                "schema_version": 1, "experiment_id": "exp_h15_reads",
                "revision": 1, "name": "R", "notes": "",
                "created_at": "t", "updated_at": "t",
            })
            list_resp = _run(_handler_for(self.init, "GET", "/comfymodal/experiments")(
                _MockRequest()))
            self.assertEqual(list_resp.status, 200)
            events_resp = _run(_handler_for(
                self.init, "GET",
                "/comfymodal/experiments/{experiment_id}/events")(
                    _MockRequest(match_info={"experiment_id": "exp_h15_reads"})))
            self.assertEqual(events_resp.status, 200)
            logs_resp = _run(_handler_for(
                self.init, "GET",
                "/comfymodal/experiments/{experiment_id}/checkpoints/{checkpoint_id}/logs")(
                    _MockRequest(match_info={"experiment_id": "exp_h15_reads",
                                             "checkpoint_id": "ck"})))
            self.assertEqual(logs_resp.status, 200)
            cell_resp = _run(_handler_for(
                self.init, "GET",
                "/comfymodal/experiments/{experiment_id}/cells/{cell_key}")(
                    _MockRequest(match_info={"experiment_id": "exp_h15_reads",
                                             "cell_key": "c"})))
            self.assertEqual(cell_resp.status, 200)


class ProtectedSingleSeamTests(unittest.TestCase):
    """WAVE_F_DO_NOT_FREEZE = TRUE (FD-13): handlers byte-untouched."""

    @classmethod
    def setUpClass(cls):
        cls.stub, cls.init = _harness()

    def test_detail_unknown_id_404_unchanged(self):
        fn = _handler_for(self.init, "GET", "/comfymodal/experiments/{experiment_id}")
        resp = _run(fn(_MockRequest(match_info={"experiment_id": "no_such_exp_h15"})))
        self.assertEqual(resp.status, 404)

    def test_detail_known_id_shape_unchanged(self):
        import experiment_service
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        with mock.patch.object(experiment_service, "experiments_root",
                               lambda: Path(tmp.name)):
            store = self.init.REGISTRY.store("exp_h15_detail")
            store.write_definition({
                "schema_version": 1, "experiment_id": "exp_h15_detail",
                "revision": 1, "name": "D", "notes": "",
                "created_at": "t", "updated_at": "t",
            })
            fn = _handler_for(self.init, "GET",
                              "/comfymodal/experiments/{experiment_id}")
            resp = _run(fn(_MockRequest(match_info={"experiment_id": "exp_h15_detail"})))
            self.assertEqual(resp.status, 200)
            payload = _body(resp)
            self.assertEqual(payload["status"], "ok")
            for key in ("definition", "snapshot", "events"):
                self.assertIn(key, payload)

    def test_stop_now_unknown_id_404_unchanged(self):
        fn = _handler_for(self.init, "POST",
                          "/comfymodal/experiments/{experiment_id}/stop-now")
        resp = _run(fn(_MockRequest(match_info={"experiment_id": "no_such_exp_h15"})))
        self.assertEqual(resp.status, 404)

    def test_stop_now_handler_semantics_intact(self):
        src = (NODE_DIR / "__init__.py").read_text(encoding="utf-8")
        start = src.index("async def experiment_stop_now(")
        end = src.index("@_server.routes.post", start)
        region = src[start:end]
        for marker in ("REGISTRY.get_scheduler(", "REGISTRY.clear_pending_stop(",
                       "sched.stop_now()", "REGISTRY.request_pending_stop(",
                       'status=404'):
            self.assertIn(marker, region, f"stop-now seam changed: missing {marker}")

    def test_detail_handler_not_frozen(self):
        src = (NODE_DIR / "__init__.py").read_text(encoding="utf-8")
        start = src.index("async def experiment_detail(")
        end = src.index("@_server.routes.get", start)
        region = src[start:end]
        self.assertNotIn("EXPERIMENT_RETIRED", region)
        self.assertNotIn("EXPERIMENT_READ_ONLY", region)


class StudioExperimentRetirementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stub, cls.init = _harness()

    def test_returns_410_before_any_side_effect(self):
        fn = _handler_for(self.init, "POST", "/comfymodal/studio/experiment")
        self.assertIsNotNone(fn)
        resp = _run(fn(_MockRequest(json_body={
            "presetIds": ["preset_default"], "featureId": "txt2img",
            "experiment": {"name": "x"},
        })))
        self.assertEqual(resp.status, 410)
        payload = _body(resp)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error_code"], "EXPERIMENT_RETIRED")

    def test_handler_never_reaches_creator_pipeline(self):
        src = (NODE_DIR / "__init__.py").read_text(encoding="utf-8")
        start = src.index('async def studio_experiment(')
        end = src.index("@_server.routes.get", start)
        region = src[start:end]
        for marker in ("handle_studio_experiment", "validate_studio_request_controls",
                       "preset_ids"):
            self.assertNotIn(marker, region)

    def test_fake_mirror_matches_production_retirement(self):
        fake = (NODE_DIR / "tests" / "browser" / "fake" / "fake-server.mjs").read_text(
            encoding="utf-8")
        start = fake.index('["POST", "/comfymodal/studio/experiment"')
        end = fake.index("}],", start)
        mirror = fake[start:end]
        self.assertIn("410", mirror)
        self.assertIn('"EXPERIMENT_RETIRED"', mirror)
        self.assertNotIn("handleStudioExperiment", mirror)
        # Harness-only seed endpoint keeps the engine creator reachable
        self.assertIn("/__comfymodal_test/legacy-experiment-seed", fake)

    def test_experiment_v2_route_still_registered_and_live(self):
        registered = {(m, p) for m, p, _ in self.stub.routes._handlers
                      if "experiment-v2" in p}
        self.assertIn(("POST", "/comfymodal/studio/experiment-v2"), registered)
        src = (NODE_DIR / "experiment_modern_routes.py").read_text(encoding="utf-8")
        for code in ("EXPERIMENT_RETIRED", "EXPERIMENT_READ_ONLY"):
            self.assertNotIn(code, src)


# ---------------------------------------------------------------------------
# 8. Warmup freeze + run_prompt_stream census
# ---------------------------------------------------------------------------


class WarmupFreezeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stub, cls.init = _harness()

    def test_run_returns_410_warmup_retired(self):
        fn = _handler_for(self.init, "POST", "/comfymodal/deploy-warmup/run")
        self.assertIsNotNone(fn)
        resp = _run(fn(_MockRequest(json_body={"workflow": {"1": {}}})))
        self.assertEqual(resp.status, 410)
        payload = _body(resp)
        self.assertEqual(payload["error_code"], "WARMUP_RETIRED")

    def test_invalidate_returns_409_warmup_retired_state_file_identical(self):
        state_file = NODE_DIR / ".deploy_warmup_state.json"
        before_hash = (hashlib.sha256(state_file.read_bytes()).hexdigest()
                       if state_file.exists() else None)
        before_mtime = state_file.stat().st_mtime if state_file.exists() else None
        fn = _handler_for(self.init, "POST", "/comfymodal/deploy-warmup/invalidate")
        resp = _run(fn(_MockRequest(json_body={})))
        self.assertEqual(resp.status, 409)
        payload = _body(resp)
        self.assertEqual(payload["error_code"], "WARMUP_RETIRED")
        if state_file.exists():
            self.assertEqual(hashlib.sha256(state_file.read_bytes()).hexdigest(),
                             before_hash)
            self.assertEqual(state_file.stat().st_mtime, before_mtime)

    def test_status_still_reads(self):
        fn = _handler_for(self.init, "GET", "/comfymodal/deploy-warmup/status")
        resp = _run(fn(_MockRequest()))
        self.assertEqual(resp.status, 200)
        self.assertIn("state", _body(resp))

    def test_no_warmup_route_reaches_streaming(self):
        src = (NODE_DIR / "__init__.py").read_text(encoding="utf-8")
        start = src.index('async def warmup_run(')
        end = src.index("@_server.routes.post", start)
        region = src[start:end]
        # No import of the streaming transport and no stream consumption
        # remain in the retired handler (docstring prose excluded).
        self.assertNotIn("from modal_client import run_prompt_stream", region)
        self.assertNotIn("async for", region)
        self.assertNotIn("_load_latest_benchmark_workflow", region)
        self.assertNotIn("mark_warmed", region)
        self.assertNotIn("mark_warmup_failed", region)
        # Census: after Wave F retired the warmup call and Wave G (H19)
        # deleted the dead Comparison residue body, ZERO direct stream
        # calls remain in __init__.py. The shared transport lives in
        # modal_client / ModalTransport for V2.
        import re
        direct = re.findall(r"async for (\w+) in run_prompt_stream\(", src)
        self.assertEqual(sorted(direct), [])

    def test_shared_transport_survives_for_v2(self):
        mc_src = (NODE_DIR / "modal_client.py").read_text(encoding="utf-8")
        self.assertIn("async def run_prompt_stream(", mc_src)
        mt_src = (NODE_DIR / "comfymodal_runtime" / "modal_transport.py").read_text(
            encoding="utf-8")
        self.assertIn("run_prompt_stream", mt_src)


# ---------------------------------------------------------------------------
# 9. /auth/setup retirement
# ---------------------------------------------------------------------------


class AuthSetupRetirementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stub, cls.init = _harness()

    def test_returns_409_with_zero_side_effects(self):
        toml_path = NODE_DIR / ".modal.toml"
        if not toml_path.exists():
            candidates = list(NODE_DIR.glob("modal.toml"))
            toml_path = candidates[0] if candidates else None
        before = (hashlib.sha256(toml_path.read_bytes()).hexdigest(), toml_path.stat().st_mtime) \
            if toml_path and toml_path.exists() else None

        calls = {"toml": 0, "upsert": 0, "deploy": 0}

        class _WorkspaceStoreTripwire:
            def __getattr__(self, name):
                def _boom(*a, **k):
                    calls["upsert"] += 1
                    raise AssertionError("workspace mutation attempted")
                return _boom

        def _no_toml(*a, **k):
            calls["toml"] += 1
            raise AssertionError("modal.toml write attempted")

        def _no_deploy(*a, **k):
            calls["deploy"] += 1
            raise AssertionError("background deploy attempted")

        originals = (
            self.init._write_modal_toml,
            self.init._workspace_store,
            self.init._run_deploy_background,
        )
        self.init._write_modal_toml = _no_toml
        self.init._workspace_store = _WorkspaceStoreTripwire()
        self.init._run_deploy_background = _no_deploy
        try:
            fn = _handler_for(self.init, "POST", "/comfymodal/auth/setup")
            self.assertIsNotNone(fn)
            resp = _run(fn(_MockRequest(json_body={
                "token_id": "ak-test", "token_secret": "as-test",
            })))
        finally:
            (self.init._write_modal_toml,
             self.init._workspace_store,
             self.init._run_deploy_background) = originals
        self.assertEqual(resp.status, 409)
        payload = _body(resp)
        self.assertEqual(payload["error_code"], "AUTH_SETUP_RETIRED")
        self.assertEqual(calls, {"toml": 0, "upsert": 0, "deploy": 0})
        if before is not None:
            after = (hashlib.sha256(toml_path.read_bytes()).hexdigest(),
                     toml_path.stat().st_mtime)
            self.assertEqual(after, before, "modal.toml must be untouched")


# ---------------------------------------------------------------------------
# 10. Legacy .presets prompt/image substrate
# ---------------------------------------------------------------------------


class LegacyPresetsFreezeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stub, cls.init = _harness()

    PROMPT_WRITES = [
        ("POST", "/comfymodal/presets/prompts", None),
        ("PUT", "/comfymodal/presets/prompts/{preset_id}", {"preset_id": "p"}),
        ("DELETE", "/comfymodal/presets/prompts/{preset_id}", {"preset_id": "p"}),
        ("POST", "/comfymodal/presets/prompts/{preset_id}/duplicate",
         {"preset_id": "p"}),
        ("POST", "/comfymodal/presets/prompts/import", None),
    ]
    IMAGE_WRITES = [
        ("POST", "/comfymodal/presets/images", None),
        ("PUT", "/comfymodal/presets/images/{preset_id}", {"preset_id": "p"}),
        ("DELETE", "/comfymodal/presets/images/{preset_id}", {"preset_id": "p"}),
    ]

    def _call_frozen(self, method, path, match):
        fn = _handler_for(self.init, method, path)
        self.assertIsNotNone(fn, f"{method} {path} must stay registered")
        return _run(fn(_MockRequest(json_body={"name": "n", "text": "t"},
                                    match_info=match or {})))

    def test_writers_return_409_legacy_presets_read_only(self):
        for method, path, match in self.PROMPT_WRITES + self.IMAGE_WRITES:
            with self.subTest(method=method, path=path):
                resp = self._call_frozen(method, path, match)
                self.assertEqual(resp.status, 409)
                payload = _body(resp)
                self.assertEqual(payload["error_code"], "LEGACY_PRESETS_READ_ONLY")

    def test_writes_leave_presets_dir_byte_identical_and_reads_work(self):
        import presets
        with tempfile.TemporaryDirectory() as tmp:
            node_root = Path(tmp)
            presets.create_prompt_preset(root=str(node_root), name="P1",
                                         shared_negative="", items=[])
            presets.create_image_preset(root=str(node_root), name="I1", items=[])
            before = _snapshot(node_root)
            original_node_dir = self.init._NODE_DIR
            self.init._NODE_DIR = str(node_root)
            try:
                for method, path, match in self.PROMPT_WRITES + self.IMAGE_WRITES:
                    resp = self._call_frozen(method, path, match)
                    self.assertEqual(resp.status, 409)
                # Reads survive (COMPAT_READ).
                list_p = _run(_handler_for(
                    self.init, "GET", "/comfymodal/presets/prompts")(_MockRequest()))
                self.assertEqual(list_p.status, 200)
                prompt_id = _body(list_p)["presets"][0]["id"]
                get_p = _run(_handler_for(
                    self.init, "GET",
                    "/comfymodal/presets/prompts/{preset_id}")(
                        _MockRequest(match_info={"preset_id": prompt_id})))
                self.assertEqual(get_p.status, 200)
                list_i = _run(_handler_for(
                    self.init, "GET", "/comfymodal/presets/images")(_MockRequest()))
                self.assertEqual(list_i.status, 200)
                image_id = _body(list_i)["presets"][0]["id"]
                get_i = _run(_handler_for(
                    self.init, "GET",
                    "/comfymodal/presets/images/{preset_id}")(
                        _MockRequest(match_info={"preset_id": image_id})))
                self.assertEqual(get_i.status, 200)
            finally:
                self.init._NODE_DIR = original_node_dir
            self.assertEqual(_snapshot(node_root), before)


# ---------------------------------------------------------------------------
# 11. /studio/backends split
# ---------------------------------------------------------------------------


class BackendsFreezeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stub, cls.init = _harness()

    WRITERS = [
        ("POST", "/comfymodal/studio/backends", None),
        ("PATCH", "/comfymodal/studio/backends/{backend_id}", {"backend_id": "b1"}),
        ("DELETE", "/comfymodal/studio/backends/{backend_id}", {"backend_id": "b1"}),
        ("POST", "/comfymodal/studio/backends/{backend_id}/duplicate",
         {"backend_id": "b1"}),
    ]

    def test_writers_return_409_backends_read_only(self):
        store_file = NODE_DIR / ".studio_backends.json"
        before = (hashlib.sha256(store_file.read_bytes()).hexdigest(),
                  store_file.stat().st_mtime) if store_file.exists() else None
        for method, path, match in self.WRITERS:
            with self.subTest(method=method, path=path):
                fn = _handler_for(self.init, method, path)
                self.assertIsNotNone(fn, f"{method} {path} must stay registered")
                resp = _run(fn(_MockRequest(json_body={"name": "n"},
                                            match_info=match or {})))
                self.assertEqual(resp.status, 409)
                payload = _body(resp)
                self.assertEqual(payload["error_code"], "BACKENDS_READ_ONLY")
        if before is not None:
            after = (hashlib.sha256(store_file.read_bytes()).hexdigest(),
                     store_file.stat().st_mtime)
            self.assertEqual(after, before, ".studio_backends.json must be untouched")

    def test_get_still_answers_stored_data(self):
        """GET stays a hidden COMPAT_READ shim answering from the stored
        registry (read-only proof against the real store; no writes)."""
        store_file = NODE_DIR / ".studio_backends.json"
        stored = json.loads(store_file.read_text(encoding="utf-8")) \
            if store_file.exists() else []
        stored_ids = [b.get("id") for b in stored if b.get("id")]
        fn = _handler_for(self.init, "GET", "/comfymodal/studio/backends")
        self.assertIsNotNone(fn)
        resp = _run(fn(_MockRequest(query={})))
        self.assertEqual(resp.status, 200)
        payload = _body(resp)
        self.assertEqual(payload["status"], "ok")
        answer_ids = [b["id"] for b in payload["backends"]]
        for sid in stored_ids:
            self.assertIn(sid, answer_ids,
                          "GET /studio/backends must still surface stored entries")
        # ?kind=comparable keeps its filter semantics: only available
        # entries without a disabled_reason survive.
        resp_kinds = _run(fn(_MockRequest(query={"kind": "comparable"})))
        self.assertEqual(resp_kinds.status, 200)
        comparable = {b["id"]: b for b in _body(resp_kinds)["backends"]}
        for b in stored:
            expected_visible = (b.get("status") == "available"
                                and not b.get("disabled_reason"))
            if expected_visible:
                self.assertIn(b["id"], comparable)
            else:
                self.assertNotIn(b["id"], comparable)


# ---------------------------------------------------------------------------
# 12. Negative guards: live families must NOT be frozen
# ---------------------------------------------------------------------------


class LiveFamiliesRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stub, cls.init = _harness()

    def test_backend_runtime_presets_crud_still_live(self):
        """FD-6: /studio/presets* stays MODERN_LIVE_TRANSITIONAL."""
        from tests.test_routes_registered import _load_repo_module
        routes_mod = _load_repo_module("studio_routes_h15", "studio_routes.py")
        with tempfile.TemporaryDirectory() as tmpdir:
            stub = _StubServer()
            routes_mod.register_studio_routes(stub, node_dir=tmpdir)
            mod = type("StudioModule", (), {"_server": stub})

            def call(method, path, **kw):
                fn = _handler_for(mod, method, path)
                self.assertIsNotNone(fn, f"{method} {path} must be registered")
                return _run(fn(_MockRequest(**kw)))

            created = call("POST", "/comfymodal/studio/presets", json_body={
                "label": "Live preset", "sourceType": "import", "snapshotId": "",
            })
            self.assertEqual(created.status, 200)
            preset_id = _body(created)["preset"]["id"]
            updated = call("PATCH", "/comfymodal/studio/presets/{preset_id}",
                           json_body={"description": "updated"},
                           match_info={"preset_id": preset_id})
            self.assertEqual(updated.status, 200)
            dup = call("POST", "/comfymodal/studio/presets/{preset_id}/duplicate",
                       match_info={"preset_id": preset_id})
            self.assertEqual(dup.status, 200)
            listed = call("GET", "/comfymodal/studio/presets")
            self.assertGreaterEqual(len(_body(listed)["presets"]), 2)
            deleted = call("DELETE", "/comfymodal/studio/presets/{preset_id}",
                           match_info={"preset_id": preset_id})
            self.assertEqual(deleted.status, 200)
        src = (NODE_DIR / "studio_routes.py").read_text(encoding="utf-8")
        for code in ("BACKENDS_READ_ONLY", "LEGACY_PRESETS_READ_ONLY",
                     "COMPARISON_READ_ONLY"):
            self.assertNotIn(code, src)

    def test_workflow_presets_distinct_and_unfrozen(self):
        registered = {(m, p) for m, p, _ in self.stub.routes._handlers
                      if "workflows" in p and "presets" in p}
        self.assertTrue(registered, "Workflow Preset routes must stay registered")
        src = (NODE_DIR / "studio_workflow_routes.py").read_text(encoding="utf-8")
        for code in ("LEGACY_PRESETS_READ_ONLY", "BACKENDS_READ_ONLY",
                     "EXPERIMENT_READ_ONLY"):
            self.assertNotIn(code, src)

    def test_run_history_reads_survive_and_compat_write_stays_writable(self):
        import experiment_service
        import studio_run_adapter
        with tempfile.TemporaryDirectory() as tmp:
            hist_root = Path(tmp) / ".run_history"
            rid = "r_h15compat"
            meta = {
                "schema_version": 2, "run_id": rid, "kind": "ordinary",
                "started_at": "2026-08-24T00:00:00+00:00",
                "workflow_name": "w", "prompt": "p", "status": "completed",
                "output_path": "", "annotations": {},
            }
            (hist_root / rid).mkdir(parents=True)
            meta_file = hist_root / rid / "meta.json"
            meta_file.write_text(json.dumps(meta), encoding="utf-8")

            with mock.patch.object(experiment_service, "run_history_root",
                                   lambda: hist_root), \
                 mock.patch("history_v2_writer.get_writer", lambda: None):
                # Reads: list/detail/logs/timing all answer.
                list_resp = _run(_handler_for(
                    self.init, "GET", "/comfymodal/run-history")(
                        _MockRequest(query={"limit": "10"})))
                self.assertEqual(list_resp.status, 200)
                self.assertGreaterEqual(_body(list_resp)["total"], 1)
                detail_resp = _run(_handler_for(
                    self.init, "GET", "/comfymodal/run-history/{run_id}")(
                        _MockRequest(match_info={"run_id": rid})))
                self.assertEqual(detail_resp.status, 200)
                logs_resp = _run(_handler_for(
                    self.init, "GET", "/comfymodal/run-history/{run_id}/logs")(
                        _MockRequest(match_info={"run_id": rid})))
                self.assertEqual(logs_resp.status, 200)
                timing_resp = _run(_handler_for(
                    self.init, "GET", "/comfymodal/run-history/{run_id}/timing")(
                        _MockRequest(match_info={"run_id": rid})))
                self.assertEqual(timing_resp.status, 200)

                # COMPAT_WRITE #1: annotations PATCH actually mutates the record.
                patch_resp = _run(_handler_for(
                    self.init, "PATCH",
                    "/comfymodal/run-history/{run_id}/annotations")(
                        _MockRequest(json_body={"favorite": True, "note": "keep"},
                                     match_info={"run_id": rid})))
                self.assertEqual(patch_resp.status, 200)
                stored = json.loads(meta_file.read_text(encoding="utf-8"))
                self.assertTrue(stored["annotations"]["favorite"])
                self.assertEqual(stored["annotations"]["note"], "keep")

                # COMPAT_WRITE #2: save delegates to the save pipeline and
                # persists saved state into the run meta.
                save_calls = []

                def _fake_save(meta, output_index=0, persist_state_fn=None, **kw):
                    save_calls.append({"run_id": meta.get("run_id"),
                                       "output_index": output_index})
                    if persist_state_fn is not None:
                        persist_state_fn({"output_saved": True})
                    return {"status": "ok", "path": "saved.png",
                            "already_saved": False, "output_index": output_index}

                original_save = studio_run_adapter.save_run_history_output
                studio_run_adapter.save_run_history_output = _fake_save
                try:
                    save_resp = _run(_handler_for(
                        self.init, "POST", "/comfymodal/run-history/{run_id}/save")(
                            _MockRequest(json_body={"output_index": 0},
                                         match_info={"run_id": rid})))
                finally:
                    studio_run_adapter.save_run_history_output = original_save
                self.assertEqual(save_resp.status, 200)
                self.assertEqual(save_calls, [{"run_id": rid, "output_index": 0}])
                stored = json.loads(meta_file.read_text(encoding="utf-8"))
                self.assertTrue(stored["extra"]["output_saved"])

    def test_frozen_routes_have_no_freeze_codes_in_live_modules(self):
        """Sanity: freeze vocabulary only lives in __init__.py server lanes."""
        init_src = (NODE_DIR / "__init__.py").read_text(encoding="utf-8")
        for code in ("COMPARISON_READ_ONLY", "EXPERIMENT_RETIRED",
                     "EXPERIMENT_READ_ONLY", "WARMUP_RETIRED",
                     "AUTH_SETUP_RETIRED", "BACKENDS_READ_ONLY",
                     "LEGACY_PRESETS_READ_ONLY"):
            self.assertIn(code, init_src)


# ---------------------------------------------------------------------------
# 13. Route registry unchanged
# ---------------------------------------------------------------------------


class RouteRegistryUnchangedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stub, cls.init = _harness()

    def test_every_frozen_route_remains_registered(self):
        expected = [
            ("POST", "/comfymodal/comparison/profiles"),
            ("PUT", "/comfymodal/comparison/profiles/{profile_id}"),
            ("DELETE", "/comfymodal/comparison/profiles/{profile_id}"),
            ("POST", "/comfymodal/comparison/profiles/{profile_id}/duplicate"),
            ("POST", "/comfymodal/comparison/profiles/{profile_id}/slots"),
            ("POST", "/comfymodal/comparison/config"),
            ("POST", "/comfymodal/comparison/run"),
            ("POST", "/comfymodal/experiments"),
            ("POST", "/comfymodal/experiments/{experiment_id}/start"),
            ("POST", "/comfymodal/experiments/{experiment_id}/pause"),
            ("POST", "/comfymodal/experiments/{experiment_id}/stop-after-current"),
            ("POST", "/comfymodal/experiments/{experiment_id}/stop-now"),
            ("POST", "/comfymodal/experiments/{experiment_id}/resume"),
            ("POST", "/comfymodal/experiments/{experiment_id}/clone"),
            ("POST", "/comfymodal/experiments/{experiment_id}/run-missing"),
            ("POST", "/comfymodal/experiments/{experiment_id}/checkpoints/{checkpoint_id}/continue"),
            ("POST", "/comfymodal/experiments/{experiment_id}/checkpoints/{checkpoint_id}/restart"),
            ("POST", "/comfymodal/experiments/{experiment_id}/checkpoints/{checkpoint_id}/restart-from"),
            ("POST", "/comfymodal/experiments/{experiment_id}/checkpoints/{checkpoint_id}/skip"),
            ("POST", "/comfymodal/experiments/{experiment_id}/checkpoints/{checkpoint_id}/unskip"),
            ("POST", "/comfymodal/experiments/{experiment_id}/cells/{cell_key}/rerun"),
            ("POST", "/comfymodal/experiments/{experiment_id}/rerun-selected"),
            ("POST", "/comfymodal/studio/experiment"),
            ("GET", "/comfymodal/deploy-warmup/status"),
            ("POST", "/comfymodal/deploy-warmup/run"),
            ("POST", "/comfymodal/deploy-warmup/invalidate"),
            ("POST", "/comfymodal/auth/setup"),
            ("POST", "/comfymodal/presets/prompts"),
            ("PUT", "/comfymodal/presets/prompts/{preset_id}"),
            ("DELETE", "/comfymodal/presets/prompts/{preset_id}"),
            ("POST", "/comfymodal/presets/prompts/{preset_id}/duplicate"),
            ("POST", "/comfymodal/presets/prompts/import"),
            ("POST", "/comfymodal/presets/images"),
            ("PUT", "/comfymodal/presets/images/{preset_id}"),
            ("DELETE", "/comfymodal/presets/images/{preset_id}"),
            ("POST", "/comfymodal/studio/backends"),
            ("PATCH", "/comfymodal/studio/backends/{backend_id}"),
            ("DELETE", "/comfymodal/studio/backends/{backend_id}"),
            ("POST", "/comfymodal/studio/backends/{backend_id}/duplicate"),
        ]
        registered = {(m, p) for m, p, _ in self.stub.routes._handlers}
        missing = [r for r in expected if r not in registered]
        self.assertEqual(missing, [], f"frozen routes lost registration: {missing}")


if __name__ == "__main__":
    unittest.main()
