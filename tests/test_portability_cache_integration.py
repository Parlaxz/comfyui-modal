"""Phase G11 integration tests: G10 derived cache wired under the G9
portability service/route shell.

Proves, through the PRODUCTION route handlers (house _StubServer pattern):

* hit / miss / stale / invalid endpoint semantics with ZERO recomputation
  on hits (injected analyzer spy — no production counters);
* every concrete stamp-field change recomputes; null never hits;
* G8 invalidation fixtures reconcile through the service shell
  (stamp_a vs stamp_a2 → real endpoint hit; every changed field and the
  null variant → recompute with exactly the expected mismatched fields);
* cache corruption/put failures FAIL OPEN to live analysis;
* workflow list/detail summaries are derived-only: tri-state stale,
  null on miss, and provably zero analysis / zero cache writes;
* Export / dry-run Import / committed Import never mutate the sidecar;
* the sidecar lives at the canonical Studio data root.

No provider/network/GPU/live-generation anywhere.
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for p in (str(ROOT), str(TESTS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from typing import Any

import portability_contract as pc  # noqa: E402
import portability_service as portability_service_module  # noqa: E402
import studio_workflow_manifest as manifest_codec  # noqa: E402
from portability_cache import (  # noqa: E402
    DEFAULT_SIDECAR_FILENAME,
    PortabilityReportCache,
)
from portability_service import PortabilityService  # noqa: E402
from studio_domain.services import WorkflowDomainService  # noqa: E402
from studio_workflow_routes import register_workflow_routes  # noqa: E402

from test_portability_backend import (  # noqa: E402
    MAPPING_BODY,
    CoreOnlyResolver,
    _MockRequest,
    _StubServer,
    _handler_for,
    sample_graph_json,
    sample_prompt,
)
import portability_fixtures as fx  # noqa: E402

DOMAIN_STORES = (
    ".studio_workflows.json",
    ".studio_workflow_versions.json",
    ".studio_workflow_mappings.json",
    ".studio_workflow_presets.json",
)

TEST_COMFY_VERSION = "0.24.0-g11-test"


# ── stubs / spies ─────────────────────────────────────────────────────────


class FakeRecordStore:
    """Minimal generation authority (list_records only)."""

    def __init__(self, records=None):
        self.records = [dict(r) for r in (records or [])]

    def list_records(self):
        return [dict(r) for r in self.records]


class RaisingStore:
    def list_records(self):
        raise RuntimeError("store unreadable")


class CountingResolver:
    """Counts resolve_version calls (list path must never call it)."""

    def __init__(self, inner):
        self.inner = inner
        self.resolve_calls = []

    def resolve_version(self, version):
        self.resolve_calls.append(str((version or {}).get("workflow_version_id") or ""))
        return self.inner.resolve_version(version)

    def reasons_for(self, version):
        return self.inner.reasons_for(version)


class ScriptedAnalyzer:
    """DI spy: counts recomputes; optional per-version canned reports."""

    def __init__(self, inner: Any = None):
        self.inner: Any = inner
        self.scripts: dict = {}
        self.calls: list = []

    def __call__(self, version_id):
        self.calls.append(version_id)
        if version_id in self.scripts:
            return copy.deepcopy(self.scripts[version_id])
        return dict(self.inner(version_id))


class BrokenPutCache:
    """get delegates; put hard-crashes (fail-open proof)."""

    def __init__(self, inner):
        self.inner = inner

    @property
    def path(self):
        return self.inner.path

    def get(self, version_id, stamp):
        return self.inner.get(version_id, stamp)

    def put(self, report):
        raise RuntimeError("sidecar unwritable")


# ── shared base ───────────────────────────────────────────────────────────


class CacheIntegrationBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = str(Path(self._tmp.name))
        self.sidecar = Path(self.root) / DEFAULT_SIDECAR_FILENAME
        self.model_source = FakeRecordStore()
        self.registry_source = FakeRecordStore()
        self.resolver = CountingResolver(CoreOnlyResolver())
        self.domain = WorkflowDomainService(self.root)
        self.analyzer = ScriptedAnalyzer(None)  # inner wired below
        self.service = PortabilityService(
            self.domain,
            resolver=self.resolver,
            cache=PortabilityReportCache(self.sidecar),
            model_library_generation_source=self.model_source,
            custom_node_registry_generation_source=self.registry_source,
            analyzer=self.analyzer,
        )
        self.analyzer.inner = self.service.portability_report
        self.stub = _StubServer()
        register_workflow_routes(
            self.stub,
            node_dir=self.root,
            resolver=self.resolver,
            portability_service=self.service,
        )
        comfy_patcher = mock.patch.object(
            portability_service_module,
            "_comfyui_version",
            lambda: TEST_COMFY_VERSION,
        )
        comfy_patcher.start()
        self.addCleanup(comfy_patcher.stop)

    def tearDown(self):
        self._tmp.cleanup()

    # -- HTTP helpers ------------------------------------------------------

    def call(self, method, path, *, body_bytes=None, query=None, match_info=None):
        handler = _handler_for(self.stub, method, path)
        assert handler is not None, "missing route %s %s" % (method, path)
        req = _MockRequest(body_bytes=body_bytes, query=query, match_info=match_info)
        return asyncio_run(handler(req))

    @staticmethod
    def body(resp):
        payload = getattr(resp, "body", None)
        return json.loads(bytes(payload) if payload is not None else b"{}")

    # -- domain helpers ----------------------------------------------------

    def create_workflow(self, name="Sample Workflow"):
        resp = self.call(
            "POST",
            "/comfymodal/studio/workflows",
            body_bytes=json.dumps({"name": name}).encode(),
        )
        assert resp.status == 200, resp.body
        return self.body(resp)["workflow"]

    def capture_version(self, wf_id, prompt=None):
        capture = {
            "graph_json": sample_graph_json(),
            "api_prompt_json": {"workflow": {}, "output": prompt or sample_prompt()},
        }
        resp = self.call(
            "POST",
            "/comfymodal/studio/workflows/{workflow_id}/versions",
            body_bytes=json.dumps(capture).encode(),
            match_info={"workflow_id": wf_id},
        )
        assert resp.status == 200, resp.body
        return self.body(resp)["version"]

    def set_mapping(self, version_id):
        resp = self.call(
            "POST",
            "/comfymodal/studio/workflows/versions/{version_id}/mapping",
            body_bytes=json.dumps(MAPPING_BODY).encode(),
            match_info={"version_id": version_id},
        )
        assert resp.status == 200, resp.body
        return self.body(resp)["mapping"]

    def setup_mapped_version(self, name="Sample Workflow", prompt=None):
        wf = self.create_workflow(name)
        version = self.capture_version(wf["workflow_id"], prompt=prompt)
        self.set_mapping(version["workflow_version_id"])
        return wf, version

    def get_portability(self, version_id):
        return self.call(
            "GET",
            "/comfymodal/studio/workflows/versions/{version_id}/portability",
            match_info={"version_id": version_id},
        )

    def list_workflows(self):
        return self.call("GET", "/comfymodal/studio/workflows")

    # -- state helpers -----------------------------------------------------

    def sidecar_bytes(self):
        return self.sidecar.read_bytes() if self.sidecar.exists() else None

    def snapshot_domain_stores(self):
        snap = {}
        for name in DOMAIN_STORES:
            path = Path(self.root) / name
            snap[name] = path.read_bytes() if path.exists() else None
        return snap

    def mutate_version_record(self, version_id, **fields):
        path = Path(self.root) / ".studio_workflow_versions.json"
        rows = json.loads(path.read_text(encoding="utf-8"))
        hit = False
        for row in rows:
            if row.get("workflow_version_id") == version_id:
                row.update(fields)
                hit = True
        assert hit, "version %r not found" % version_id
        path.write_text(json.dumps(rows), encoding="utf-8")

    def mutate_workflow_record(self, workflow_id, **fields):
        path = Path(self.root) / ".studio_workflows.json"
        rows = json.loads(path.read_text(encoding="utf-8"))
        hit = False
        for row in rows:
            if row.get("workflow_id") == workflow_id:
                row.update(fields)
                hit = True
        assert hit, "workflow %r not found" % workflow_id
        path.write_text(json.dumps(rows), encoding="utf-8")


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)


# ── generation-token authorities ──────────────────────────────────────────


class GenerationTokenTests(unittest.TestCase):
    def test_00_none_and_raising_authorities_yield_null(self):
        self.assertIsNone(
            portability_service_module.model_library_generation_token(None)
        )
        self.assertIsNone(
            portability_service_module.model_library_generation_token(RaisingStore())
        )
        self.assertIsNone(
            portability_service_module.custom_node_registry_generation_token(None)
        )
        self.assertIsNone(
            portability_service_module.custom_node_registry_generation_token(
                RaisingStore()
            )
        )

    def test_00_tokens_are_deterministic_and_evidence_sensitive(self):
        records = [
            {
                "model_id": "ml_1",
                "folder": "checkpoints",
                "filename": "a.safetensors",
                "hash": "ab" * 32,
                "size": 10,
                "source_urls": ["https://example.invalid/a"],
                "provider": "civitai",
                "revision": "1",
                "is_placeholder": False,
                "local_path": r"C:\\x\\a.safetensors",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        ]
        first = portability_service_module.model_library_generation_token(
            FakeRecordStore(records)
        )
        second = portability_service_module.model_library_generation_token(
            FakeRecordStore(copy.deepcopy(records))
        )
        self.assertEqual(first, second)
        changed = copy.deepcopy(records)
        changed[0]["hash"] = "cd" * 32
        self.assertNotEqual(
            first,
            portability_service_module.model_library_generation_token(
                FakeRecordStore(changed)
            ),
        )
        registry = [{"name": "pkg", "repo_url": "r", "installed_commit": "c",
                     "classes": ["B", "A"]}]
        reg_first = portability_service_module.custom_node_registry_generation_token(
            FakeRecordStore(registry)
        )
        reg_same = portability_service_module.custom_node_registry_generation_token(
            FakeRecordStore(copy.deepcopy(registry))
        )
        self.assertEqual(reg_first, reg_same)
        reg_changed = copy.deepcopy(registry)
        reg_changed[0]["installed_commit"] = "d"
        self.assertNotEqual(
            reg_first,
            portability_service_module.custom_node_registry_generation_token(
                FakeRecordStore(reg_changed)
            ),
        )


# ── endpoint hit / miss / recompute flow ──────────────────────────────────


class EndpointCacheFlowTests(CacheIntegrationBase):
    def test_01_first_get_miss_analyzes_and_puts(self):
        _, version = self.setup_mapped_version()
        vid = version["workflow_version_id"]
        resp = self.get_portability(vid)
        self.assertEqual(resp.status, 200)
        payload = self.body(resp)
        self.assertEqual(payload["status"], "ok")
        pc.validate_report(payload["portability"])
        self.assertEqual(payload["portability_cache"]["state"], "miss")
        self.assertTrue(payload["portability_cache"]["recomputed"])
        self.assertEqual(self.analyzer.calls, [vid])
        row = self.service.cache.inspect(vid)
        self.assertTrue(row["usable"])

    def test_02_second_identical_get_hits_with_zero_analysis(self):
        _, version = self.setup_mapped_version()
        vid = version["workflow_version_id"]
        first = self.body(self.get_portability(vid))
        second = self.body(self.get_portability(vid))
        self.assertEqual(second["portability_cache"]["state"], "hit")
        self.assertFalse(second["portability_cache"]["recomputed"])
        self.assertEqual(self.analyzer.calls, [vid])
        self.assertEqual(first["portability"]["risk_level"],
                         second["portability"]["risk_level"])
        self.assertFalse(second["portability"]["stale"])
        self.assertEqual(second["portability"]["invalidation"]["comfyui_version"],
                         TEST_COMFY_VERSION)

    def test_03_unknown_version_is_404_without_cache_write(self):
        before = self.sidecar_bytes()
        resp = self.get_portability("wv_missing")
        self.assertEqual(resp.status, 404)
        self.assertEqual(self.sidecar_bytes(), before)

    def test_04_stamp_has_all_eight_fields_concrete(self):
        _, version = self.setup_mapped_version()
        vid = version["workflow_version_id"]
        self.body(self.get_portability(vid))
        info = self.service.cache.inspect(vid)
        stamp = info["stamp"]
        self.assertEqual(set(stamp), set(pc.INVALIDATION_FIELDS))
        for field in pc.INVALIDATION_FIELDS:
            self.assertIsNotNone(stamp[field], field)
        self.assertEqual(stamp["rule_version"], pc.PORTABILITY_RULE_VERSION)
        self.assertEqual(stamp["manifest_version"],
                         manifest_codec.MANIFEST_SCHEMA_VERSION)


class StampFieldRecomputeTests(CacheIntegrationBase):
    """Each concrete stamp-field change must force a live recompute."""

    def _prime(self):
        _, version = self.setup_mapped_version()
        vid = version["workflow_version_id"]
        self.body(self.get_portability(vid))
        self.assertEqual(len(self.analyzer.calls), 1)
        return vid

    def _assert_recompute(self, vid):
        payload = self.body(self.get_portability(vid))
        self.assertEqual(payload["portability_cache"]["state"], "stale")
        self.assertTrue(payload["portability_cache"]["recomputed"])
        self.assertEqual(len(self.analyzer.calls), 2)
        pc.validate_report(payload["portability"])
        # refreshed entry is current again
        again = self.body(self.get_portability(vid))
        self.assertEqual(again["portability_cache"]["state"], "hit")
        self.assertEqual(len(self.analyzer.calls), 2)

    def test_05_graph_hash_change_recomputes(self):
        vid = self._prime()
        self.mutate_version_record(vid, graph_hash="ff" * 32)
        self._assert_recompute(vid)

    def test_06_dependency_metadata_hash_change_recomputes(self):
        vid = self._prime()
        version = self.service.store.get_version(vid)
        dep = copy.deepcopy(version.get("dependency_metadata") or {})
        dep.setdefault("model_stack", {}).setdefault("checkpoint", []).append(
            "other_model.safetensors"
        )
        self.mutate_version_record(vid, dependency_metadata=dep)
        self._assert_recompute(vid)

    def test_07_model_library_generation_change_recomputes(self):
        vid = self._prime()
        self.model_source.records.append(
            {"model_id": "ml_new", "filename": "new.safetensors",
             "folder": "checkpoints", "hash": "ab" * 32, "size": 5}
        )
        self._assert_recompute(vid)

    def test_08_custom_node_registry_generation_change_recomputes(self):
        vid = self._prime()
        self.registry_source.records.append(
            {"name": "pkg", "repo_url": "https://example.invalid/pkg",
             "installed_commit": "aa" * 20, "classes": ["FixtureNode"]}
        )
        self._assert_recompute(vid)

    def test_09_rule_version_change_recomputes(self):
        vid = self._prime()
        with mock.patch.object(
            pc, "PORTABILITY_RULE_VERSION", "portability-rules-v2"
        ):
            payload = self.body(self.get_portability(vid))
            # A rule bump invalidates old rows at validation time (G10 row
            # discipline) — either way the endpoint must NOT serve them and
            # must recompute live.
            self.assertNotEqual(payload["portability_cache"]["state"], "hit")
            self.assertIn(
                payload["portability_cache"]["state"], ("stale", "invalid")
            )
            self.assertTrue(payload["portability_cache"]["recomputed"])
            self.assertEqual(len(self.analyzer.calls), 2)
            pc.validate_report(payload["portability"])
            self.assertEqual(
                self.body(self.get_portability(vid))["portability"]["rule_version"],
                "portability-rules-v2",
            )
            self.assertEqual(len(self.analyzer.calls), 2)

    def test_10_manifest_version_change_recomputes(self):
        vid = self._prime()
        with mock.patch.object(manifest_codec, "MANIFEST_SCHEMA_VERSION", 2):
            payload = self.body(self.get_portability(vid))
            self.assertEqual(payload["portability_cache"]["state"], "stale")
            self.assertIn(
                "manifest_version", payload["portability_cache"]["mismatched_fields"]
            )
            self.assertTrue(payload["portability_cache"]["recomputed"])
            self.assertEqual(len(self.analyzer.calls), 2)

    def test_11_comfyui_version_change_recomputes(self):
        vid = self._prime()
        with mock.patch.object(
            portability_service_module,
            "_comfyui_version",
            lambda: "0.99.0-other",
        ):
            payload = self.body(self.get_portability(vid))
            self.assertEqual(payload["portability_cache"]["state"], "stale")
            self.assertIn(
                "comfyui_version", payload["portability_cache"]["mismatched_fields"]
            )
            self.assertEqual(len(self.analyzer.calls), 2)

    def test_12_null_stamp_field_recomputes_every_time_never_hits(self):
        vid = self._prime()
        # Authority dies AFTER a concrete entry was cached → null vs concrete.
        self.service._model_generation_source = RaisingStore()
        payload = self.body(self.get_portability(vid))
        self.assertEqual(payload["portability_cache"]["state"], "stale")
        self.assertIn(
            "model_library_generation", payload["portability_cache"]["mismatched_fields"]
        )
        self.assertEqual(len(self.analyzer.calls), 2)
        # Null-vs-null: an all-along-null authority can NEVER produce a hit.
        self.service._registry_generation_source = RaisingStore()
        first = self.body(self.get_portability(vid))
        second = self.body(self.get_portability(vid))
        for payload in (first, second):
            self.assertNotEqual(payload["portability_cache"]["state"], "hit")
            self.assertTrue(payload["portability_cache"]["recomputed"])
        self.assertEqual(len(self.analyzer.calls), 4)


class G8FixtureReconciliationTests(CacheIntegrationBase):
    """G8 invalidation fixtures driven through the REAL route handlers."""

    def _adapted(self, stamp, vid, graph_hash):
        """Bind a fixture stamp to the REAL version identity.

        workflow_version_id is always remapped to the live version; fields
        that are UNCHANGED relative to stamp_a are remapped to the live
        values too, while deliberately-CHANGED fixture values (e.g. the
        graph_hash variant) are preserved so they still fire.
        """
        adapted = dict(stamp)
        adapted["workflow_version_id"] = vid
        if adapted["graph_hash"] == self._fixture_base_graph_hash:
            adapted["graph_hash"] = graph_hash
        return adapted

    def _run_fixture_flow(self, stamps, semantics):
        _, version = self.setup_mapped_version()
        vid = version["workflow_version_id"]
        graph_hash = str(version["graph_hash"])
        self._fixture_base_graph_hash = stamps["stamp_a"]["graph_hash"]
        base = self._adapted(stamps["stamp_a"], vid, graph_hash)
        with mock.patch.object(
            self.service, "current_invalidation_stamp", lambda v: dict(base)
        ):
            first = self.body(self.get_portability(vid))
            self.assertEqual(first["portability_cache"]["state"], "miss")
            self.assertEqual(len(self.analyzer.calls), 1)
            # A vs A2 → actual endpoint cache HIT, zero recomputation.
            a2 = self._adapted(stamps["stamp_a2"], vid, graph_hash)
            with mock.patch.object(
                self.service, "current_invalidation_stamp", lambda v: dict(a2)
            ):
                second = self.body(self.get_portability(vid))
                self.assertEqual(second["portability_cache"]["state"], "hit")
                self.assertFalse(second["portability_cache"]["recomputed"])
                self.assertEqual(len(self.analyzer.calls), 1)
        # Every concrete single-field change → recompute with EXACTLY the
        # expected mismatched fields from the fixture semantics.  Before each
        # variant, re-prime the cached row to stamp_a so variants are
        # evaluated independently (a previous variant's put must not leak).
        for stamp_name, expected_fields in sorted(semantics["stale_variants"].items()):
            with mock.patch.object(
                self.service, "current_invalidation_stamp", lambda v: dict(base)
            ):
                # Restore the cached row to stamp_a (hit when already A,
                # recompute+put after a previous variant contaminated it).
                self.body(self.get_portability(vid))
            variant = self._adapted(stamps[stamp_name], vid, graph_hash)
            with mock.patch.object(
                self.service, "current_invalidation_stamp", lambda v: dict(variant)
            ):
                payload = self.body(self.get_portability(vid))
                self.assertEqual(
                    payload["portability_cache"]["state"],
                    "stale",
                    stamp_name,
                )
                self.assertEqual(
                    set(payload["portability_cache"]["mismatched_fields"]),
                    set(expected_fields),
                    stamp_name,
                )
                self.assertTrue(payload["portability_cache"]["recomputed"])
        # Null variant → conservative recompute (never a hit).
        null_stamp = self._adapted(stamps["stamp_null_field"], vid, graph_hash)
        with mock.patch.object(
            self.service, "current_invalidation_stamp", lambda v: dict(null_stamp)
        ):
            payload = self.body(self.get_portability(vid))
            self.assertNotEqual(payload["portability_cache"]["state"], "hit")
            self.assertIn("dependency_metadata_hash",
                          payload["portability_cache"]["mismatched_fields"])
        # Null-vs-null through the endpoint: still never a hit.
        with mock.patch.object(
            self.service, "current_invalidation_stamp", lambda v: dict(null_stamp)
        ):
            again = self.body(self.get_portability(vid))
            self.assertNotEqual(again["portability_cache"]["state"], "hit")
            self.assertTrue(again["portability_cache"]["recomputed"])

    def test_13_g8_invalidation_fixtures_through_endpoint(self):
        self._run_fixture_flow(fx.load_invalidation_stamps(), fx.load_invalidation_semantics())


# ── fail-open behavior ────────────────────────────────────────────────────


class FailOpenTests(CacheIntegrationBase):
    def test_14_malformed_sidecar_fails_open_then_regenerates(self):
        _, version = self.setup_mapped_version()
        vid = version["workflow_version_id"]
        self.sidecar.write_bytes(b"{this is not json")
        domain_before = self.snapshot_domain_stores()
        payload = self.body(self.get_portability(vid))
        self.assertEqual(resp_status := 200, 200)
        self.assertEqual(payload["portability_cache"]["state"], "invalid")
        self.assertTrue(payload["portability_cache"]["recomputed"])
        self.assertTrue(payload["portability_cache"]["diagnostics"])
        pc.validate_report(payload["portability"])
        self.assertEqual(self.snapshot_domain_stores(), domain_before)
        # The derived sidecar was regenerated from scratch and is hittable.
        regenerated = json.loads(self.sidecar.read_text(encoding="utf-8"))
        self.assertIsInstance(regenerated, list)
        self.assertEqual(regenerated[0]["cache_format_version"], 1)
        self.assertIn(vid, regenerated[0]["reports"])
        second = self.body(self.get_portability(vid))
        self.assertEqual(second["portability_cache"]["state"], "hit")
        self.assertEqual(len(self.analyzer.calls), 1)

    def test_15_put_hard_failure_still_returns_live_report(self):
        _, version = self.setup_mapped_version()
        vid = version["workflow_version_id"]
        self.service.cache = BrokenPutCache(self.service.cache)
        resp = self.get_portability(vid)
        self.assertEqual(resp.status, 200)
        payload = self.body(resp)
        pc.validate_report(payload["portability"])
        self.assertTrue(payload["portability_cache"]["recomputed"])
        self.assertTrue(
            any("put failed open" in d for d in payload["portability_cache"]["diagnostics"])
        )
        self.assertEqual(self.analyzer.calls, [vid])

    def test_16_put_rejection_still_returns_live_report(self):
        _, version = self.setup_mapped_version()
        vid = version["workflow_version_id"]
        # Canned report whose graph_hash disagrees with the authoritative
        # Version → put() rejects; the live report is still served.
        real = self.service.portability_report(vid)
        tampered = dict(real)
        tampered["graph_hash"] = "cd" * 32
        self.analyzer.scripts[vid] = tampered
        resp = self.get_portability(vid)
        self.assertEqual(resp.status, 200)
        payload = self.body(resp)
        self.assertEqual(payload["portability"]["risk_level"], real["risk_level"])
        self.assertTrue(payload["portability_cache"]["recomputed"])
        self.assertTrue(payload["portability_cache"]["diagnostics"])
        info = self.service.cache.inspect(vid)
        self.assertFalse(info["present"])

    def test_17_valid_unknown_report_is_cacheable(self):
        _, version = self.setup_mapped_version()
        vid = version["workflow_version_id"]

        def unknown_inner(v):
            rep = dict(self.service.portability_report(v))
            rep["risk_level"] = "unknown"
            return rep

        self.analyzer.inner = unknown_inner
        first = self.body(self.get_portability(vid))
        self.assertEqual(first["portability"]["risk_level"], "unknown")
        second = self.body(self.get_portability(vid))
        self.assertEqual(second["portability_cache"]["state"], "hit")
        self.assertEqual(second["portability"]["risk_level"], "unknown")
        self.assertEqual(len(self.analyzer.calls), 1)

    def test_18_stale_low_never_served_as_current_after_change(self):
        _, version = self.setup_mapped_version()
        vid = version["workflow_version_id"]
        first = self.body(self.get_portability(vid))
        self.assertEqual(first["portability"]["risk_level"], "low")
        self.model_source.records.append(
            {"model_id": "ml_x", "filename": "x.safetensors"}
        )
        payload = self.body(self.get_portability(vid))
        self.assertEqual(payload["portability_cache"]["state"], "stale")
        self.assertTrue(payload["portability_cache"]["recomputed"])
        report = payload["portability"]
        pc.validate_report(report)
        # FRESH report (stale=False), stamped with the NEW evidence — not the
        # old LOW view flipped to stale=true.
        self.assertFalse(report["stale"])
        self.assertNotEqual(
            report["analyzed_at"], first["portability"]["analyzed_at"]
        )
        self.assertNotEqual(
            report["invalidation"]["model_library_generation"],
            first["portability"]["invalidation"]["model_library_generation"],
        )


# ── list/detail summary enrichment ────────────────────────────────────────


class ListSummaryTests(CacheIntegrationBase):
    def _summary_of(self, resp_payload, wf_id):
        for row in resp_payload["workflows"]:
            if row["workflow_id"] == wf_id:
                return row["portability_summary"]
        return None  # noqa: RET501

    def test_19_list_current_hit_marks_stale_false(self):
        wf, version = self.setup_mapped_version()
        vid = version["workflow_version_id"]
        self.body(self.get_portability(vid))
        payload = self.body(self.list_workflows())
        summary = self._summary_of(payload, wf["workflow_id"])
        self.assertIsNotNone(summary)
        self.assertEqual(summary["version_id"], vid)
        self.assertFalse(summary["stale"])
        self.assertEqual(summary["risk_level"], "low")
        self.assertIsInstance(summary["issue_count"], int)
        self.assertTrue(summary["analyzed_at"])
        self.assertEqual(set(summary),
                         {"version_id", "risk_level", "issue_count", "stale",
                          "analyzed_at"})

    def test_20_list_stale_summary_marked_stale_true(self):
        wf, version = self.setup_mapped_version()
        vid = version["workflow_version_id"]
        self.body(self.get_portability(vid))
        self.model_source.records.append(
            {"model_id": "ml_y", "filename": "y.safetensors"}
        )
        payload = self.body(self.list_workflows())
        summary = self._summary_of(payload, wf["workflow_id"])
        self.assertIsNotNone(summary)
        self.assertTrue(summary["stale"])
        self.assertEqual(summary["risk_level"], "low")

    def test_21_list_miss_summary_is_null(self):
        self.setup_mapped_version(name="Never Analyzed")
        payload = self.body(self.list_workflows())
        summary = self._summary_of(payload, payload["workflows"][0]["workflow_id"])
        self.assertIsNone(summary)

    def test_22_list_unchecked_dangling_pointer_gives_stale_null(self):
        wf, version = self.setup_mapped_version()
        vid = version["workflow_version_id"]
        real = self.service.portability_report(vid)
        phantom = "wv_phantom0000000000000000000000000000000000"
        cached = dict(real)
        cached["version_id"] = phantom
        cached["invalidation"] = dict(real["invalidation"])
        cached["invalidation"]["workflow_version_id"] = phantom
        put_result = self.service.cache.put(cached)
        assert put_result.ok, put_result.reasons
        self.mutate_workflow_record(wf["workflow_id"], latest_version_id=phantom)
        payload = self.body(self.list_workflows())
        summary = self._summary_of(payload, wf["workflow_id"])
        self.assertIsNotNone(summary)
        self.assertIsNone(summary["stale"])
        self.assertEqual(summary["version_id"], phantom)

    def test_23_list_performs_zero_analysis_and_zero_cache_writes(self):
        self.setup_mapped_version(name="A")
        self.setup_mapped_version(name="B")
        before = self.sidecar_bytes()
        payload = self.body(self.list_workflows())
        for row in payload["workflows"]:
            self.assertIsNone(row["portability_summary"])
        self.assertEqual(self.analyzer.calls, [])
        self.assertEqual(self.resolver.resolve_calls, [])
        self.assertEqual(self.sidecar_bytes(), before)

    def test_24_five_workflows_no_cross_contamination(self):
        wf_low, v_low = self.setup_mapped_version(name="Low Current")
        wf_high, v_high = self.setup_mapped_version(name="High Current")
        wf_stale, v_stale = self.setup_mapped_version(name="Stale")
        self.setup_mapped_version(name="Never Analyzed")
        wf_unchecked, v_unchecked = self.setup_mapped_version(name="Unchecked")
        high = dict(self.service.portability_report(v_high["workflow_version_id"]))
        high["risk_level"] = "high"
        medium = dict(self.service.portability_report(v_stale["workflow_version_id"]))
        medium["risk_level"] = "medium"
        self.analyzer.scripts[v_high["workflow_version_id"]] = high
        self.analyzer.scripts[v_stale["workflow_version_id"]] = medium
        self.body(self.get_portability(v_low["workflow_version_id"]))
        self.body(self.get_portability(v_high["workflow_version_id"]))
        self.body(self.get_portability(v_stale["workflow_version_id"]))
        # Version-scoped evidence drift: ONLY wf_stale's stamp stales
        # (global generations stay untouched so Low/High remain current).
        stale_version = self.service.store.get_version(
            v_stale["workflow_version_id"]
        )
        dep = copy.deepcopy(stale_version.get("dependency_metadata") or {})
        dep.setdefault("model_stack", {}).setdefault("checkpoint", []).append(
            "drift_model.safetensors"
        )
        self.mutate_version_record(
            v_stale["workflow_version_id"], dependency_metadata=dep
        )
        # wf_unchecked dangles onto a phantom id that HAS a cached row.
        phantom = "wv_phantomffffffffffffffffffffffffffffffff"
        real_unchecked = self.service.portability_report(
            v_unchecked["workflow_version_id"]
        )
        cached = dict(real_unchecked)
        cached["version_id"] = phantom
        cached["invalidation"] = dict(real_unchecked["invalidation"])
        cached["invalidation"]["workflow_version_id"] = phantom
        assert self.service.cache.put(cached).ok
        self.mutate_workflow_record(
            wf_unchecked["workflow_id"], latest_version_id=phantom
        )
        payload = self.body(self.list_workflows())
        by_name = {row["name"]: row["portability_summary"]
                   for row in payload["workflows"]}
        low_s = by_name["Low Current"]
        high_s = by_name["High Current"]
        stale_s = by_name["Stale"]
        none_s = by_name["Never Analyzed"]
        unchecked_s = by_name["Unchecked"]
        self.assertEqual(low_s["stale"], False)
        self.assertEqual(low_s["risk_level"], "low")
        self.assertEqual(high_s["stale"], False)
        self.assertEqual(high_s["risk_level"], "high")
        self.assertEqual(stale_s["stale"], True)
        self.assertEqual(stale_s["risk_level"], "medium")
        self.assertIsNone(none_s)
        self.assertIsNone(unchecked_s["stale"])
        self.assertEqual(unchecked_s["version_id"], phantom)
        ids = {s["version_id"] for s in (low_s, high_s, stale_s, unchecked_s)}
        self.assertEqual(len(ids), 4)

    def test_25_same_graph_hash_different_version_not_reused(self):
        wf_a, v_a = self.setup_mapped_version(name="A")
        wf_b, v_b = self.setup_mapped_version(name="B")
        self.assertEqual(v_a["graph_hash"], v_b["graph_hash"])
        self.assertNotEqual(v_a["workflow_version_id"], v_b["workflow_version_id"])
        self.body(self.get_portability(v_a["workflow_version_id"]))
        payload = self.body(self.list_workflows())
        a_s = self._summary_of(payload, wf_a["workflow_id"])
        b_s = self._summary_of(payload, wf_b["workflow_id"])
        self.assertIsNotNone(a_s)
        self.assertIsNone(b_s)

    def test_26_detail_carries_same_summary_shape(self):
        wf, version = self.setup_mapped_version()
        vid = version["workflow_version_id"]
        self.body(self.get_portability(vid))
        resp = self.call(
            "GET",
            "/comfymodal/studio/workflows/{workflow_id}",
            match_info={"workflow_id": wf["workflow_id"]},
        )
        detail = self.body(resp)["workflow"]
        summary = detail["portability_summary"]
        self.assertIsNotNone(summary)
        self.assertEqual(set(summary),
                         {"version_id", "risk_level", "issue_count", "stale",
                          "analyzed_at"})
        self.assertEqual(summary["version_id"], vid)
        self.assertFalse(summary["stale"])

    def test_27_corrupt_sidecar_list_treated_absent_no_crash(self):
        self.setup_mapped_version()
        self.sidecar.write_bytes(b"[nope")
        domain_before = self.snapshot_domain_stores()
        resp = self.list_workflows()
        self.assertEqual(resp.status, 200)
        for row in self.body(resp)["workflows"]:
            self.assertIsNone(row["portability_summary"])
        self.assertEqual(self.snapshot_domain_stores(), domain_before)


# ── export / import cache neutrality + canonical location ────────────────


class ImportExportNeutralityTests(CacheIntegrationBase):
    def _export_manifest_bytes(self, version_id):
        resp = self.call(
            "GET",
            "/comfymodal/studio/workflows/versions/{version_id}/export",
            match_info={"version_id": version_id},
        )
        assert resp.status == 200, resp.body
        return bytes(resp.body)

    def _commit_import(self, manifest_bytes):
        resp = self.call(
            "POST",
            "/comfymodal/studio/workflows/import-manifest",
            body_bytes=manifest_bytes,
            query={"dry_run": "0"},
        )
        assert resp.status == 200, self.body(resp)
        return self.body(resp)

    def test_28_export_and_dry_run_import_do_not_mutate_sidecar(self):
        _, version = self.setup_mapped_version()
        vid = version["workflow_version_id"]
        self.body(self.get_portability(vid))
        before = self.sidecar_bytes()
        manifest_bytes = self._export_manifest_bytes(vid)
        self.assertEqual(self.sidecar_bytes(), before)
        resp = self.call(
            "POST",
            "/comfymodal/studio/workflows/import-manifest",
            body_bytes=manifest_bytes,
        )
        self.assertEqual(resp.status, 200)
        self.assertEqual(self.sidecar_bytes(), before)
        self.assertEqual(self.analyzer.calls, [vid])

    def test_29_committed_import_does_not_fill_cache_or_analyze(self):
        _, version = self.setup_mapped_version()
        vid = version["workflow_version_id"]
        self.body(self.get_portability(vid))
        before = self.sidecar_bytes()
        manifest_bytes = self._export_manifest_bytes(vid)
        committed = self._commit_import(manifest_bytes)
        new_vid = committed["workflow_version_id"]
        self.assertNotEqual(new_vid, vid)
        self.assertEqual(self.sidecar_bytes(), before)
        self.assertEqual(self.analyzer.calls, [vid])
        # New Version starts with NO cached report: list shows null until an
        # explicit portability GET computes+caches it.
        payload = self.body(self.list_workflows())
        names = {row["name"]: row["portability_summary"]
                 for row in payload["workflows"]}
        imported_name = committed["workflow_name"]
        self.assertIsNone(names[imported_name])
        fresh = self.body(self.get_portability(new_vid))
        self.assertEqual(fresh["portability_cache"]["state"], "miss")
        self.assertEqual(self.analyzer.calls, [vid, new_vid])
        after = self.body(self.list_workflows())
        summary = [
            row["portability_summary"]
            for row in after["workflows"]
            if row["workflow_id"] == committed["workflow_id"]
        ][0]
        self.assertIsNotNone(summary)
        self.assertFalse(summary["stale"])

    def test_30_sidecar_lives_under_canonical_data_root(self):
        _, version = self.setup_mapped_version()
        self.body(self.get_portability(version["workflow_version_id"]))
        self.assertTrue(self.sidecar.exists())
        self.assertEqual(
            Path(self.service.cache.path), Path(self.root) / DEFAULT_SIDECAR_FILENAME
        )
        envelope = json.loads(self.sidecar.read_text(encoding="utf-8"))
        self.assertEqual(envelope[0]["cache_format_version"], 1)

    def test_31_default_route_composition_builds_canonical_sidecar(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            node_dir = str(Path(tmp.name))
            stub = _StubServer()
            register_workflow_routes(stub, node_dir=node_dir, resolver=None)
            handler = _handler_for(
                stub, "GET",
                "/comfymodal/studio/workflows/versions/{version_id}/portability",
            )
            capture = {
                "graph_json": sample_graph_json(),
                "api_prompt_json": {"workflow": {}, "output": sample_prompt()},
            }
            create = asyncio_run(_handler_for(
                stub, "POST", "/comfymodal/studio/workflows"
            )(_MockRequest(body_bytes=json.dumps({"name": "W"}).encode())))
            wf = json.loads(create.body)["workflow"]
            ver = asyncio_run(_handler_for(
                stub, "POST", "/comfymodal/studio/workflows/{workflow_id}/versions"
            )(_MockRequest(
                body_bytes=json.dumps(capture).encode(),
                match_info={"workflow_id": wf["workflow_id"]},
            )))
            vid = json.loads(ver.body)["version"]["workflow_version_id"]
            resp = asyncio_run(handler(_MockRequest(match_info={"version_id": vid})))
            self.assertEqual(resp.status, 200)
            sidecar = Path(node_dir) / DEFAULT_SIDECAR_FILENAME
            self.assertTrue(sidecar.exists())
            envelope = json.loads(sidecar.read_text(encoding="utf-8"))
            self.assertIn(vid, envelope[0]["reports"])
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main(verbosity=2)
