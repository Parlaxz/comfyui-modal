"""Tests for portability_cache (Phase G10 derived report cache lane).

Covers: miss/hit/stale/invalid semantics, the frozen G5 null-conservative
invalidation rule (via ``portability_contract.invalidation_mismatches``),
fail-open corruption behavior, atomic writes, thread concurrency, stale-view
immutability, the summary helper, and consumption of the read-only G8
invalidation fixtures.

Runs with plain ``python tests/test_portability_cache.py`` (includes a
``__main__`` harness) and is pytest-discoverable. Uses temporary directories
ONLY — never writes a real ``.studio_portability_reports.json`` into the
project. No network, no GPU, no live generation.
"""

import copy
import json
import sys
import tempfile
import threading
import types
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR))
sys.path.insert(0, str(TESTS_DIR.parent))

import portability_contract as c  # noqa: E402
import portability_cache as pc  # noqa: E402
import studio_store  # noqa: E402
import portability_fixtures as fx  # noqa: E402

SIDECAR_NAME = pc.DEFAULT_SIDECAR_FILENAME


# ── Shared builders ───────────────────────────────────────────────────────


def make_stamp(
    *,
    workflow_version_id="wv_cache_test_v1",
    graph_hash="a" * 64,
    dependency_metadata_hash: str | None = "b" * 64,
    model_library_generation=11,
    custom_node_registry_generation=7,
    rule_version=c.PORTABILITY_RULE_VERSION,
    manifest_version=1,
    comfyui_version="0.24.0-test",
):
    return c.build_invalidation_stamp(
        workflow_version_id=workflow_version_id,
        graph_hash=graph_hash,
        dependency_metadata_hash=dependency_metadata_hash,
        model_library_generation=model_library_generation,
        custom_node_registry_generation=custom_node_registry_generation,
        rule_version=rule_version,
        manifest_version=manifest_version,
        comfyui_version=comfyui_version,
    )


def make_report(stamp, *, analyzed_at="2026-08-23T12:00:00+00:00", **overrides):
    issues = [
        c.build_issue(
            code="custom_node_unpinned",
            severity="medium",
            message="2 unpinned custom nodes.",
            subject="custom_nodes",
        ),
        c.build_issue(
            code="required_input_asset",
            severity="low",
            message="Input asset travels separately.",
            subject="assets",
        ),
    ]
    report = {
        "version_id": stamp["workflow_version_id"],
        "graph_hash": stamp["graph_hash"],
        "risk_level": "medium",
        "rule_version": c.PORTABILITY_RULE_VERSION,
        "issue_count": len(issues),
        "counts": {"high": 0, "medium": 1, "low": 1},
        "issues": issues,
        "signals": {"custom_node_count": 2},
        "targets": {
            tid: c.make_target_result(risk_level="low") for tid in c.TARGET_IDS
        },
        "environment": {
            "risk_level": "high",
            "issues": [],
            "source": c.ENVIRONMENT_SOURCE_CURRENT_STUDIO,
        },
        "stale": False,
        "invalidation": dict(stamp),
        "analyzed_at": analyzed_at,
    }
    report.update(overrides)
    return report


class TempCache:
    """Cache bound to a temp-dir sidecar (context manager)."""

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.path = self.dir / SIDECAR_NAME
        self.cache = pc.PortabilityReportCache(self.path)
        return self

    def __exit__(self, *exc):
        self._tmp.cleanup()
        return False


def read_sidecar(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


# ── 1/34: missing file and empty sidecar → miss ──────────────────────────


def test_missing_file_is_miss():
    with TempCache() as t:
        result = t.cache.get("wv_any", make_stamp())
        assert result.state == "miss"
        assert result.report is None
        assert not t.path.exists(), "read must not create the sidecar"


def test_empty_sidecar_is_miss():
    with TempCache() as t:
        t.cache.clear()
        assert t.path.exists()
        result = t.cache.get("wv_any", make_stamp())
        assert result.state == "miss"


# ── 2: first put → hit ────────────────────────────────────────────────────


def test_first_put_then_hit_roundtrip():
    with TempCache() as t:
        stamp = make_stamp()
        put = t.cache.put(make_report(stamp))
        assert put.ok and put.reasons == ()
        result = t.cache.get("wv_cache_test_v1", stamp)
        assert result.state == "hit"
        assert result.report["risk_level"] == "medium"
        assert result.report["issue_count"] == 2
        assert result.mismatched_fields == ()


# ── 3–10: G8 fixture single-field changes → stale ─────────────────────────


def _cached_fixture_row(t, stamps):
    stamp_a = stamps["stamp_a"]
    vid = stamp_a["workflow_version_id"]
    assert t.cache.put(make_report(stamp_a)).ok
    return vid, stamp_a


def test_g8_identical_stamps_a_a2_hit():
    with TempCache() as t:
        stamps = fx.load_invalidation_stamps()
        vid, _ = _cached_fixture_row(t, stamps)
        result = t.cache.get(vid, stamps["stamp_a2"])
        assert result.state == "hit"


def test_g8_graph_hash_change_stales():
    with TempCache() as t:
        stamps = fx.load_invalidation_stamps()
        vid, _ = _cached_fixture_row(t, stamps)
        result = t.cache.get(vid, stamps["stamp_graph_hash_changed"])
        assert result.state == "stale"
        assert set(result.mismatched_fields) == {"graph_hash"}
        assert result.report["stale"] is True


def test_g8_dependency_metadata_hash_change_stales():
    with TempCache() as t:
        stamp = make_stamp()
        assert t.cache.put(make_report(stamp)).ok
        current = dict(stamp)
        current["dependency_metadata_hash"] = "f" * 64
        result = t.cache.get("wv_cache_test_v1", current)
        assert result.state == "stale"
        assert set(result.mismatched_fields) == {"dependency_metadata_hash"}


def test_g8_model_library_generation_change_stales():
    with TempCache() as t:
        stamps = fx.load_invalidation_stamps()
        vid, _ = _cached_fixture_row(t, stamps)
        result = t.cache.get(vid, stamps["stamp_model_library_generation_changed"])
        assert result.state == "stale"
        assert set(result.mismatched_fields) == {"model_library_generation"}


def test_g8_custom_node_registry_generation_change_stales():
    with TempCache() as t:
        stamps = fx.load_invalidation_stamps()
        vid, _ = _cached_fixture_row(t, stamps)
        result = t.cache.get(
            vid, stamps["stamp_custom_node_registry_generation_changed"]
        )
        assert result.state == "stale"
        assert set(result.mismatched_fields) == {"custom_node_registry_generation"}


def test_g8_rule_version_change_stales():
    with TempCache() as t:
        stamps = fx.load_invalidation_stamps()
        vid, _ = _cached_fixture_row(t, stamps)
        result = t.cache.get(vid, stamps["stamp_rule_version_changed"])
        assert result.state == "stale"
        assert set(result.mismatched_fields) == {"rule_version"}


def test_g8_manifest_version_change_stales():
    with TempCache() as t:
        stamps = fx.load_invalidation_stamps()
        vid, _ = _cached_fixture_row(t, stamps)
        result = t.cache.get(vid, stamps["stamp_manifest_version_changed"])
        assert result.state == "stale"
        assert set(result.mismatched_fields) == {"manifest_version"}


def test_g8_comfyui_version_change_stales():
    with TempCache() as t:
        stamps = fx.load_invalidation_stamps()
        vid, _ = _cached_fixture_row(t, stamps)
        result = t.cache.get(vid, stamps["stamp_comfyui_version_changed"])
        assert result.state == "stale"
        assert set(result.mismatched_fields) == {"comfyui_version"}


# ── 11: workflow_version_id mismatch ──────────────────────────────────────


def test_version_id_mismatch_in_current_stamp_stales():
    with TempCache() as t:
        stamp = make_stamp()
        assert t.cache.put(make_report(stamp)).ok
        current = dict(stamp)
        current["workflow_version_id"] = "wv_someone_else_v1"
        result = t.cache.get("wv_cache_test_v1", current)
        assert result.state == "stale"
        assert set(result.mismatched_fields) == {"workflow_version_id"}


def test_row_key_disagreement_is_invalid_not_hit():
    with TempCache() as t:
        stamp = make_stamp()
        assert t.cache.put(make_report(stamp)).ok
        doc = read_sidecar(t.path)
        doc[0]["reports"]["wv_impersonator"] = doc[0]["reports"]["wv_cache_test_v1"]
        t.path.write_text(json.dumps(doc), encoding="utf-8")
        result = t.cache.get("wv_impersonator", stamp)
        assert result.state == "invalid"
        assert result.report is None


# ── 12/13/14: null semantics (null is NEVER "unchanged") ──────────────────


def test_cached_null_field_stales_even_against_concrete():
    with TempCache() as t:
        stamp = make_stamp(dependency_metadata_hash=None)
        assert t.cache.put(make_report(stamp)).ok
        result = t.cache.get("wv_cache_test_v1", make_stamp())
        assert result.state == "stale"
        assert "dependency_metadata_hash" in result.mismatched_fields


def test_current_null_field_stales():
    with TempCache() as t:
        stamp = make_stamp()
        assert t.cache.put(make_report(stamp)).ok
        current = make_stamp(dependency_metadata_hash=None)
        result = t.cache.get("wv_cache_test_v1", current)
        assert result.state == "stale"
        assert "dependency_metadata_hash" in result.mismatched_fields


def test_null_vs_null_stales():
    with TempCache() as t:
        stamp = make_stamp(dependency_metadata_hash=None)
        assert t.cache.put(make_report(stamp)).ok
        result = t.cache.get("wv_cache_test_v1", make_stamp(dependency_metadata_hash=None))
        assert result.state == "stale"
        assert "dependency_metadata_hash" in result.mismatched_fields


def test_entirely_unknown_current_stamp_stales_everything():
    with TempCache() as t:
        stamp = make_stamp()
        assert t.cache.put(make_report(stamp)).ok
        result = t.cache.get("wv_cache_test_v1", None)
        assert result.state == "stale"
        assert set(result.mismatched_fields) == set(c.INVALIDATION_FIELDS)


# ── 15/16: invalid payloads never cached / never returned as hit ──────────


def test_invalid_report_rejected_on_put_and_writes_nothing():
    with TempCache() as t:
        bad = make_report(make_stamp(), risk_level="catastrophic")
        put = t.cache.put(bad)
        assert not put.ok
        assert put.reasons and any("risk level" in r for r in put.reasons)
        assert not t.path.exists(), "rejected put must not create the sidecar"
        bad2 = make_report(make_stamp())
        bad2["issue_count"] = 99
        assert not t.cache.put(bad2).ok
        assert not t.path.exists()


def test_put_without_complete_stamp_rejected():
    with TempCache() as t:
        report = make_report(make_stamp())
        report["invalidation"] = None
        assert not t.cache.put(report).ok
        report["invalidation"] = {"workflow_version_id": "wv_cache_test_v1"}
        assert not t.cache.put(report).ok
        report = make_report(make_stamp())
        report["invalidation"]["graph_hash"] = "mismatched"
        assert not t.cache.put(report).ok
        assert not t.path.exists()


def test_corrupt_cached_report_never_hit():
    with TempCache() as t:
        stamp = make_stamp()
        assert t.cache.put(make_report(stamp)).ok
        doc = read_sidecar(t.path)
        doc[0]["reports"]["wv_cache_test_v1"]["report"]["risk_level"] = "catastrophic"
        t.path.write_text(json.dumps(doc), encoding="utf-8")
        result = t.cache.get("wv_cache_test_v1", stamp)
        assert result.state == "invalid"
        assert result.report is None
        info = t.cache.inspect("wv_cache_test_v1")
        assert info["present"] and not info["usable"] and info["problems"]


# ── 17/18/35: fail-open corruption ────────────────────────────────────────


def test_malformed_json_fails_open_invalid():
    with TempCache() as t:
        t.path.write_text('{"cache_format_version": 1,', encoding="utf-8")
        result = t.cache.get("wv_any", make_stamp())
        assert result.state == "invalid"
        assert result.report is None
        assert t.cache.last_diagnostics


def test_wrong_root_fails_open_invalid():
    with TempCache() as t:
        t.path.write_text(json.dumps({"cache_format_version": 1}), encoding="utf-8")
        assert t.cache.get("wv_any", make_stamp()).state == "invalid"
        t.path.write_text('"just a string"', encoding="utf-8")
        assert t.cache.get("wv_any", make_stamp()).state == "invalid"
        t.path.write_text(json.dumps([{"envelope": 1}, {"envelope": 2}]), encoding="utf-8")
        result = t.cache.get("wv_any", make_stamp())
        assert result.state == "invalid"


def test_unknown_future_cache_format_fails_open():
    with TempCache() as t:
        t.path.write_text(
            json.dumps([{"cache_format_version": 99, "reports": {}}]),
            encoding="utf-8",
        )
        result = t.cache.get("wv_any", make_stamp())
        assert result.state == "invalid"
        assert "cache_format_version" in result.reason
        assert t.cache.summaries(["wv_any"]) == []


# ── 19: one malformed row is not authoritative ────────────────────────────


def test_single_bad_row_does_not_poison_good_rows():
    with TempCache() as t:
        good_stamp = make_stamp(workflow_version_id="wv_good_v1")
        assert t.cache.put(make_report(good_stamp)).ok
        doc = read_sidecar(t.path)
        doc[0]["reports"]["wv_bad_v1"] = "not-a-row"
        t.path.write_text(json.dumps(doc), encoding="utf-8")
        assert t.cache.get("wv_good_v1", good_stamp).state == "hit"
        bad = t.cache.get("wv_bad_v1", make_stamp(workflow_version_id="wv_bad_v1"))
        assert bad.state == "invalid"


# ── 20: atomic write survives simulated failure ───────────────────────────


def test_atomic_write_survives_simulated_replace_failure():
    with TempCache() as t:
        original = make_report(make_stamp(), analyzed_at="2026-08-23T00:00:00+00:00")
        assert t.cache.put(original).ok
        replacement = make_report(
            make_stamp(),
            analyzed_at="2026-08-23T23:59:00+00:00",
        )
        with mock.patch.object(
            studio_store.os, "replace", side_effect=OSError("simulated crash")
        ):
            try:
                t.cache.put(replacement)
            except studio_store.StudioStoreError:
                pass
            else:
                raise AssertionError("simulated failure should surface")
        leftovers = list(t.dir.glob("*.tmp"))
        assert leftovers == [], "temp file must be cleaned up"
        doc = read_sidecar(t.path)
        stored = doc[0]["reports"]["wv_cache_test_v1"]["report"]
        assert stored["analyzed_at"] == "2026-08-23T00:00:00+00:00"
        assert len(doc[0]["reports"]) == 1
        assert t.cache.get("wv_cache_test_v1", make_stamp()).state == "hit"


# ── 21/22/27/28: overwrite, coexistence, removal ──────────────────────────


def test_same_version_overwrite_atomically_replaces():
    with TempCache() as t:
        stamp = make_stamp()
        assert t.cache.put(make_report(stamp, analyzed_at="T1")).ok
        updated = make_report(stamp, analyzed_at="T2")
        updated["issues"].append(
            c.build_issue(
                code="model_hash_unpinned",
                severity="medium",
                message="Model ref has no sha256.",
                subject="models",
            )
        )
        updated["issue_count"] = 3
        updated["counts"] = {"high": 0, "medium": 2, "low": 1}
        assert t.cache.put(updated).ok
        doc = read_sidecar(t.path)
        rows = doc[0]["reports"]
        assert len(rows) == 1
        assert rows["wv_cache_test_v1"]["report"]["analyzed_at"] == "T2"
        assert rows["wv_cache_test_v1"]["report"]["issue_count"] == 3
        result = t.cache.get("wv_cache_test_v1", stamp)
        assert result.state == "hit"
        assert result.report["analyzed_at"] == "T2"
        assert result.report["issue_count"] == 3


def test_different_versions_coexist():
    with TempCache() as t:
        s1 = make_stamp(workflow_version_id="wv_one_v1", graph_hash="1" * 64)
        s2 = make_stamp(workflow_version_id="wv_two_v1", graph_hash="2" * 64)
        assert t.cache.put(make_report(s1)).ok
        assert t.cache.put(make_report(s2)).ok
        assert t.cache.get("wv_one_v1", s1).state == "hit"
        assert t.cache.get("wv_two_v1", s2).state == "hit"
        doc = read_sidecar(t.path)
        assert set(doc[0]["reports"]) == {"wv_one_v1", "wv_two_v1"}


def test_remove_one_version():
    with TempCache() as t:
        s1 = make_stamp(workflow_version_id="wv_one_v1", graph_hash="1" * 64)
        s2 = make_stamp(workflow_version_id="wv_two_v1", graph_hash="2" * 64)
        assert t.cache.put(make_report(s1)).ok
        assert t.cache.put(make_report(s2)).ok
        assert t.cache.remove("wv_one_v1") is True
        assert t.cache.remove("wv_one_v1") is False
        assert t.cache.get("wv_one_v1", s1).state == "miss"


def test_remove_does_not_affect_others():
    with TempCache() as t:
        s1 = make_stamp(workflow_version_id="wv_one_v1", graph_hash="1" * 64)
        s2 = make_stamp(workflow_version_id="wv_two_v1", graph_hash="2" * 64)
        assert t.cache.put(make_report(s1)).ok
        assert t.cache.put(make_report(s2)).ok
        assert t.cache.remove("wv_one_v1") is True
        result = t.cache.get("wv_two_v1", s2)
        assert result.state == "hit"
        assert result.report["graph_hash"] == "2" * 64


# ── 23: thread-concurrent writes remain valid ─────────────────────────────


def test_thread_concurrent_writes_remain_valid():
    with TempCache() as t:
        shared_stamp = make_stamp(workflow_version_id="wv_shared_v1")
        worker_count = 8
        per_worker = 6
        barrier = threading.Barrier(worker_count)
        errors = []

        def worker(i):
            barrier.wait()
            try:
                for j in range(per_worker):
                    vid = "wv_t%d_j%d_v1" % (i, j)
                    assert t.cache.put(
                        make_report(make_stamp(workflow_version_id=vid, graph_hash=str(i % 10) * 64))
                    ).ok
                assert t.cache.put(
                    make_report(shared_stamp, analyzed_at="run-%d" % i)
                ).ok
                t.cache.get("wv_shared_v1", shared_stamp)
            except Exception as exc:  # noqa: BLE001 - collect for assertion
                errors.append(exc)

        threads = [
            threading.Thread(target=worker, args=(i,), daemon=True) for i in range(worker_count)
        ]
        for th in threads:
            th.start()
        for th in threads:
            th.join(timeout=60)
        assert errors == []
        doc = read_sidecar(t.path)
        rows = doc[0]["reports"]
        expected = {"wv_t%d_j%d_v1" % (i, j) for i in range(worker_count) for j in range(per_worker)}
        expected.add("wv_shared_v1")
        assert set(rows) == expected
        for vid in expected:
            row = rows[vid]
            assert not pc._row_problems(vid, row), vid


# ── 24/25/26: stale-view behavior and persistence immutability ────────────


def test_stale_read_does_not_mutate_persisted_report():
    with TempCache() as t:
        stamp = make_stamp()
        original = make_report(stamp, analyzed_at="2026-08-23T08:00:00+00:00")
        assert t.cache.put(original).ok
        current = make_stamp(comfyui_version="0.99.0-changed")
        view = t.cache.get("wv_cache_test_v1", current).report
        assert view is not None
        view["stale"] = False
        view["analyzed_at"] = "tampered"
        view["issues"].append({"code": "junk"})
        view["targets"]["local"]["risk_level"] = "low-tampered"
        doc = read_sidecar(t.path)
        stored = doc[0]["reports"]["wv_cache_test_v1"]["report"]
        assert stored["stale"] is False
        assert stored["analyzed_at"] == "2026-08-23T08:00:00+00:00"
        assert len(stored["issues"]) == 2
        assert stored["targets"]["local"]["risk_level"] == "low"
        again = t.cache.get("wv_cache_test_v1", current)
        assert again.report["analyzed_at"] == "2026-08-23T08:00:00+00:00"
        assert again.report["stale"] is True


def test_stale_view_marked_stale_true():
    with TempCache() as t:
        stamp = make_stamp()
        assert t.cache.put(make_report(stamp)).ok
        result = t.cache.get("wv_cache_test_v1", make_stamp(graph_hash="9" * 64))
        assert result.state == "stale"
        assert result.stale is True
        assert result.report["stale"] is True
        assert result.report["risk_level"] == "medium"


def test_hit_view_remains_stale_false():
    with TempCache() as t:
        stamp = make_stamp()
        assert t.cache.put(make_report(stamp)).ok
        result = t.cache.get("wv_cache_test_v1", stamp)
        assert result.state == "hit"
        assert result.hit is True
        assert result.report["stale"] is False


# ── 29: summary helper ────────────────────────────────────────────────────


def test_summary_helper_preserves_risk_count_stale():
    with TempCache() as t:
        stamp = make_stamp()
        assert t.cache.put(
            make_report(stamp, analyzed_at="2026-08-23T09:30:00+00:00")
        ).ok
        unchecked = t.cache.summaries(["wv_cache_test_v1"])
        assert len(unchecked) == 1
        entry = unchecked[0]
        assert entry["version_id"] == "wv_cache_test_v1"
        assert entry["risk_level"] == "medium"
        assert entry["issue_count"] == 2
        assert entry["analyzed_at"] == "2026-08-23T09:30:00+00:00"
        assert entry["freshness"] == "unchecked"
        assert entry["stale"] is None
        verified = t.cache.summaries(["wv_cache_test_v1"], {"wv_cache_test_v1": stamp})
        assert verified[0]["freshness"] == "verified"
        assert verified[0]["stale"] is False
        staled = t.cache.summaries(
            ["wv_cache_test_v1"],
            {"wv_cache_test_v1": make_stamp(model_library_generation=999)},
        )
        assert staled[0]["stale"] is True
        assert set(staled[0]["mismatched_fields"]) == {"model_library_generation"}
        assert t.cache.summaries(["wv_never_cached"]) == []


# ── 30/31: NO TTL; analyzed_at is never an invalidation criterion ─────────


def test_no_ttl_old_analyzed_at_still_hits():
    with TempCache() as t:
        stamp = make_stamp()
        assert t.cache.put(
            make_report(stamp, analyzed_at="2020-01-01T00:00:00+00:00")
        ).ok
        result = t.cache.get("wv_cache_test_v1", stamp)
        assert result.state == "hit"


def test_analyzed_at_difference_alone_does_not_stale():
    with TempCache() as t:
        stamp = make_stamp()
        assert t.cache.put(
            make_report(stamp, analyzed_at="2020-01-01T00:00:00+00:00")
        ).ok
        result = t.cache.get(
            "wv_cache_test_v1",
            stamp,
        )
        assert result.state == "hit"
        assert result.report["analyzed_at"] == "2020-01-01T00:00:00+00:00"
        assert "analyzed_at" not in c.INVALIDATION_FIELDS


# ── 32: no execution-gating API/dependency ────────────────────────────────


def test_cache_exposes_no_execution_gating_api():
    banned = {
        "runnable",
        "authorize",
        "can_execute",
        "can_import",
        "execute",
        "gate",
        "import_manifest",
    }
    module_public = {n for n in dir(pc) if not n.startswith("_")}
    class_public = {
        n for n in dir(pc.PortabilityReportCache) if not n.startswith("_")
    }
    assert not (banned & module_public), banned & module_public
    assert not (banned & class_public), banned & class_public
    modules = {
        name
        for name, value in vars(pc).items()
        if isinstance(value, types.ModuleType)
    }
    assert modules == {"contract", "studio_store", "copy", "dataclasses"}, modules
    with TempCache() as t:
        methods = {n for n in dir(t.cache) if not n.startswith("_")}
        assert not (banned & methods)


# ── 33: G8 invalidation fixtures consumed unchanged ───────────────────────


def test_g8_invalidation_fixtures_consumed_unchanged():
    stamps = fx.load_invalidation_stamps()
    semantics = fx.load_invalidation_semantics()
    assert len(stamps) == 9
    for name, stamp in stamps.items():
        assert set(stamp) == set(c.INVALIDATION_FIELDS), name
        assert c.invalidation_stamp_issues(stamp) == [], name
    with TempCache() as t:
        vid = stamps["stamp_a"]["workflow_version_id"]
        assert t.cache.put(make_report(stamps["stamp_a"])).ok
        for left, right in semantics["reusable_pairs"]:
            assert left == "stamp_a"
            assert t.cache.get(vid, stamps[right]).state == "hit", (left, right)
        for name, fields in semantics["stale_variants"].items():
            result = t.cache.get(vid, stamps[name])
            assert result.state == "stale", name
            assert set(result.mismatched_fields) == set(fields), name
        null_info = semantics["null_variant"]
        null_stamp = stamps[null_info["stamp"]]
        assert t.cache.put(make_report(null_stamp)).ok
        assert t.cache.get(vid, null_stamp).state == "stale"
        assert t.cache.get(vid, stamps["stamp_a"]).state == "stale"


# ── extras: inspect + clear diagnostics ───────────────────────────────────


def test_inspect_reports_diagnostics_without_stamp():
    with TempCache() as t:
        stamp = make_stamp()
        assert t.cache.put(make_report(stamp)).ok
        info = t.cache.inspect("wv_cache_test_v1")
        assert info["present"] and info["usable"]
        assert info["risk_level"] == "medium"
        assert info["issue_count"] == 2
        assert info["stamp"]["graph_hash"] == stamp["graph_hash"]
        assert info["analyzed_at"]
        assert t.cache.inspect("wv_absent")["present"] is False


def test_clear_resets_to_empty_envelope():
    with TempCache() as t:
        assert t.cache.put(make_report(make_stamp())).ok
        t.cache.clear()
        doc = read_sidecar(t.path)
        assert doc[0]["cache_format_version"] == pc.CACHE_FORMAT_VERSION
        assert doc[0]["reports"] == {}
        assert t.cache.get("wv_cache_test_v1", make_stamp()).state == "miss"


if __name__ == "__main__":
    failed = 0
    fns = sorted(name for name in dir() if name.startswith("test_"))
    for name in fns:
        try:
            globals()[name]()
            print("ok  %s" % name)
        except AssertionError as exc:
            failed += 1
            print("FAIL %s: %s" % (name, exc))
    print("%d/%d passed" % (len(fns) - failed, len(fns)))
    sys.exit(1 if failed else 0)
