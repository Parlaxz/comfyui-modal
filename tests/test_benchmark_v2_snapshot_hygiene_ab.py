"""Offline A/B analysis for ``COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE``: targeted local validation.

Covers ``tools.benchmark_v2_snapshot_hygiene_ab`` (no Modal, no network, no
benchmark execution): per-run normalization of both raw run artifacts and
experiment-record shapes, strict "median only when n>=2 / p90 only when n>=5"
statistics, classification rules (CONFIRMED / SUPPORTED INFERENCE /
INSUFFICIENT DATA), Batch-C3 scheduling semantics (``non_scheduling_ms``
primary, legacy placement-only metric informational), freshness via
``container_session_id`` + ``runtime_state_generation_baseline`` corroboration
(fail-closed NOT READY when missing; ``restore_session_id`` demoted to
per-restore correlation), the RSS-drop-without-startup-claim guard, and
Markdown report rendering.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import benchmark_v2_snapshot_hygiene_ab as ab  # noqa: E402

ENV_FLAG = "COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE"


# ── Builder helpers ─────────────────────────────────────────────────────────


def _hygiene_event(**kw):
    """Default capture-boundary hygiene event dict (arm B shape)."""
    event = {
        "enabled": 1,
        "gc_collected": 12345,
        "malloc_trim_available": 1,
        "malloc_trim_result": "ok",
        "hygiene_wall_ms": 320.5,
        "before_rss_kb": 27007828,
        "after_rss_kb": 24734984,
        "delta_rss_kb": 2272844,
        "before_rss_anon_kb": 26500000,
        "after_rss_anon_kb": 24300000,
        "before_rss_file_kb": 400000,
        "after_rss_file_kb": 350000,
        "cgroup_memory_current_before_bytes": 26000000000,
        "cgroup_memory_current_after_bytes": 23800000000,
        "cgroup_memory_current_delta_bytes": 2200000000,
    }
    event.update(kw)
    return event


def _make_waterfall(app_restore, pre_python=1500.0, sched=2000.0, cmd_response=12000.0, total=12000.0,
                    enqueue=1000.0):
    """Host-reconciled waterfall with Batch-C3 scheduling fields.

    ``non_scheduling_ms`` = command_response − (enqueue + placement), matching
    the accepted C3 contract: scheduling time = enqueue + placement; command
    (without scheduling) -> response = COMMAND -> RESPONSE − scheduling time.
    """
    wf = {
        "scheduling_ms": sched,
        "total_wall_ms": total,
        "command_response_ms": cmd_response,
        "command_to_enqueue_ms": enqueue,
        "scheduling_time_ms": round(enqueue + sched, 6),
        "non_scheduling_ms": round(cmd_response - (enqueue + sched), 6),
        "stages": [
            {"key": "modal_scheduling", "label": "Modal scheduling before snapshot restore begins",
             "duration_ms": sched, "status": "measured"},
            {"key": "pre_python_snapshot_restore", "label": "Modal pre-Python snapshot restoration",
             "duration_ms": pre_python, "status": "measured"},
            {"key": "application_restore", "label": "Python/application restore",
             "duration_ms": app_restore, "status": "measured"},
        ],
    }
    return wf


def _make_timing(cmd_response, sched, resume=None, sampling=1500.0):
    if resume is None:
        resume = sched + 2000.0
    return {
        "command_to_response_ms": cmd_response,
        "scheduling_ms": sched,
        "submission_to_remote_python_resume_ms": resume,
        "sampling_ms": sampling,
    }


def _run(rid, arm, app_restore, *, pre_python=1500.0, cmd_response=12000.0, sched=2000.0,
         resume=None, with_event=True, flag=None, hygiene_event=None, session=None,
         container="cont-shared", baseline="base-shared",
         snapshot_identity="snap-shared", enqueue=1000.0):
    """A raw run artifact (``run_*.json`` shape written by benchmark_v2_direct.py).

    Real-artifact semantics: ``container_session_id`` is the per-construction
    identity (stable across restores of the same snapshot), the
    ``runtime_state_generation_baseline`` corroborates it, and
    ``restore_session_id`` is a per-RESTORE uuid (fresh per request).
    """
    if flag is None:
        flag = "1" if arm == "B" else "0"
    restore_timing = {"restore_total_ms": app_restore}
    if container is not None:
        restore_timing["container_session_id"] = container
    if baseline is not None:
        restore_timing["runtime_state_generation_baseline"] = baseline
    if session is not None:
        restore_timing["restore_session_id"] = session
    if with_event:
        restore_timing["snapshot_capture_hygiene"] = (
            _hygiene_event() if hygiene_event is None else hygiene_event
        )
    result = {"_restore_timing": restore_timing}
    return {
        "request_id": rid,
        "snapshot_identity": snapshot_identity,
        "identity": {
            "restore_count": 1,
            "request_count": 1,
            "cloud": "aws",
            "region": "us-east-2",
            "gpu": "A100-80GB",
            "image_id": "img-shared",
            "workflow_hash_prefix": "wf123",
        },
        "effective_env": {ENV_FLAG: flag},
        "result": result,
        "timing": _make_timing(cmd_response, sched, resume=resume),
        "waterfall_local": _make_waterfall(app_restore, pre_python=pre_python, sched=sched,
                                           cmd_response=cmd_response, enqueue=enqueue),
    }


def _extract(runs, arm):
    """Normalize raw artifacts (or pass records through) into analysis records."""
    expected = "1" if arm == "B" else "0"
    return [ab.extract_run(r, arm_label=arm, expected_flag=expected) for r in runs]


def _record(**kw):
    """An experiment-run record shape (persisted by experiment_result_store)."""
    session = kw.pop("session", None)
    container = kw.pop("container", "cont-shared")
    baseline = kw.pop("baseline", "base-shared")
    restore_timing = {
        "restore_total_ms": 8500.0,
        "container_session_id": container,
        "runtime_state_generation_baseline": baseline,
        "snapshot_capture_hygiene": _hygiene_event(),
    }
    if session is not None:
        restore_timing["restore_session_id"] = session
    record = {
        "request_id": "rec-1",
        "experiment": "snapshot_allocator_hygiene_ab",
        "arm": "B",
        "run_ordinal": 1,
        "run_role": "sample",
        "retained": True,
        "image_id": "img-shared",
        "snapshot_identity": "snap-B",
        "provider": "aws",
        "region": "us-east-2",
        "gpu": "A100-80GB",
        "cpu": 4,
        "ram": 32,
        "effective_env": {ENV_FLAG: "1"},
        "command_response_ms": 12100.0,
        "scheduling_ms": 2100.0,
        "total_wall_ms": 12100.0,
        "final_reconciled_waterfall": _make_waterfall(
            8500.0, pre_python=1500.0, sched=2100.0, cmd_response=12100.0, total=12100.0),
        "source_identity": {
            "restore_count": 1,
            "request_count": 1,
            "cloud": "aws",
            "region": "us-east-2",
            "gpu": "A100-80GB",
            "image_id": "img-shared",
            "workflow_hash_prefix": "wf123",
        },
        "result": {"_restore_timing": restore_timing},
    }
    record.update(kw)
    return record


def _strip_c3(artifact):
    """Return a copy of *artifact* with the C3 fields removed (legacy shape)."""
    out = json.loads(json.dumps(artifact))
    wf = out.get("waterfall_local")
    if isinstance(wf, dict):
        wf.pop("non_scheduling_ms", None)
        wf.pop("command_to_enqueue_ms", None)
        wf.pop("scheduling_time_ms", None)
    rec = out.get("final_reconciled_waterfall")
    if isinstance(rec, dict):
        rec.pop("non_scheduling_ms", None)
        rec.pop("command_to_enqueue_ms", None)
        rec.pop("scheduling_time_ms", None)
    return out


# ── Existing tests (preserved; placement-only primary renamed) ─────────────


def test_n1_each_side_is_insufficient_no_fake_p90():
    a = _extract([_run("a1", "A", 8500.0)], "A")
    b = _extract([_run("b1", "B", 8200.0)], "B")
    analysis = ab.analyze(a, b)
    assert analysis["overall"]["classification"] == "INSUFFICIENT DATA"
    for metric in analysis["primary_metrics"]:
        for side in ("stats_a", "stats_b"):
            stats = analysis["metrics"][metric][side]
            assert stats["median"] is None
            assert stats["mean"] is None
            assert stats["p90"] is None
            assert stats["median_meaningful"] is False
            assert stats["p90_meaningful"] is False
    cls = ab.classify_metric(a, b, "application_restore_ms")
    assert cls["classification"] == "INSUFFICIENT DATA"
    assert "n<2" in cls["reason"]
    assert cls["delta_ms"] is None
    report = ab.render_report(analysis)
    assert "median only when n>=2" in report
    assert "p90 only when n>=5" in report
    assert "| 5.000 |" not in report


def test_multiple_samples_medians_and_confirmed():
    a_runs = [
        _run("a1", "A", 8500.0),
        _run("a2", "A", 8600.0),
        _run("a3", "A", 8400.0),
    ]
    b_runs = [
        _run("b1", "B", 7900.0),
        _run("b2", "B", 8000.0),
        _run("b3", "B", 7800.0),
    ]
    analysis = ab.analyze(_extract(a_runs, "A"), _extract(b_runs, "B"))
    cls = analysis["metrics"]["application_restore_ms"]
    assert cls["classification"] == "CONFIRMED"
    assert cls["direction"] == "B faster"
    assert cls["median_a"] == 8500.0
    assert cls["median_b"] == 7900.0
    assert cls["delta_ms"] == 7900.0 - 8500.0
    assert cls["stats_a"]["p90"] is None
    assert cls["stats_b"]["p90"] is None
    assert cls["stats_a"]["median_meaningful"] is True
    # Identical C3 non-scheduling is a neutral "no measurable difference".
    c3 = analysis["metrics"]["non_scheduling_ms"]
    assert c3["classification"] == "INSUFFICIENT DATA"
    assert "no measurable difference" in c3["reason"]
    assert analysis["overall"]["classification"] == "CONFIRMED"
    assert analysis["overall"]["direction"] == "B faster"


def test_scheduling_difference_does_not_contaminate():
    a_runs = [_run(f"a{i}", "A", 8500.0, cmd_response=15000.0, sched=5000.0) for i in range(3)]
    b_runs = [_run(f"b{i}", "B", 8500.0, cmd_response=10500.0, sched=500.0) for i in range(3)]
    analysis = ab.analyze(_extract(a_runs, "A"), _extract(b_runs, "B"))
    c3 = analysis["metrics"]["non_scheduling_ms"]
    assert c3["classification"] == "INSUFFICIENT DATA"
    assert "no measurable difference" in c3["reason"]
    # Identical stage durations -> application/pre-python also neutral.
    assert analysis["metrics"]["application_restore_ms"]["classification"] == "INSUFFICIENT DATA"
    assert analysis["protocol"]["scheduling_contamination"]["flag"] is True
    overall = analysis["overall"]
    assert overall["classification"] == "INSUFFICIENT DATA"
    assert not (overall["classification"] in ("CONFIRMED", "SUPPORTED INFERENCE")
                and overall["direction"] == "B faster")
    report = ab.render_report(analysis)
    assert "scheduling" in report


def test_rss_drop_without_startup_win_no_claim():
    a_runs = [_run(f"a{i}", "A", 8500.0, with_event=False) for i in range(3)]
    b_runs = [_run(f"b{i}", "B", 8500.0, with_event=True) for i in range(3)]
    analysis = ab.analyze(_extract(a_runs, "A"), _extract(b_runs, "B"))
    assert analysis["overall"]["classification"] == "INSUFFICIENT DATA"
    assert analysis["overall"]["direction"] == "none"
    assert analysis["capture_evidence"]["A"]["delta_rss_kb"]["count"] == 0
    assert analysis["capture_evidence"]["B"]["delta_rss_kb"]["median"] == 2272844.0
    assert analysis["overall"]["rss_drop_without_startup_win"] is True
    report = ab.render_report(analysis)
    assert "RSS dropped under hygiene (B) but the startup verdict is not based on RSS" in report


def test_hygiene_startup_win_confirmed():
    a_runs = [
        _run("a1", "A", 8500.0, pre_python=1500.0, cmd_response=12000.0),
        _run("a2", "A", 8600.0, pre_python=1550.0, cmd_response=12100.0),
        _run("a3", "A", 8400.0, pre_python=1450.0, cmd_response=11900.0),
    ]
    b_runs = [
        _run("b1", "B", 7900.0, pre_python=1300.0, cmd_response=11000.0),
        _run("b2", "B", 8000.0, pre_python=1350.0, cmd_response=11100.0),
        _run("b3", "B", 7800.0, pre_python=1250.0, cmd_response=10900.0),
    ]
    analysis = ab.analyze(_extract(a_runs, "A"), _extract(b_runs, "B"))
    assert analysis["metrics"]["non_scheduling_ms"]["classification"] == "CONFIRMED"
    assert analysis["metrics"]["non_scheduling_ms"]["direction"] == "B faster"
    assert analysis["metrics"]["pre_python_snapshot_restore_ms"]["classification"] == "CONFIRMED"
    assert analysis["metrics"]["pre_python_snapshot_restore_ms"]["direction"] == "B faster"
    assert analysis["metrics"]["application_restore_ms"]["classification"] == "CONFIRMED"
    assert analysis["metrics"]["application_restore_ms"]["direction"] == "B faster"
    assert analysis["overall"]["classification"] == "CONFIRMED"
    assert analysis["overall"]["direction"] == "B faster"
    assert analysis["overall"]["sufficient_for_conclusion"] is True
    assert "STOP" in analysis["overall"]["stop_recommendation"]


def test_missing_rss_fields_handled():
    artifact = _run("m1", "B", 8500.0, hygiene_event={"enabled": 1, "gc_collected": 10})
    rec = ab.extract_run(artifact, arm_label="B", expected_flag="1")
    assert rec["valid"] is True
    assert rec["hygiene_event_present"] is True
    assert rec["gc_collected"] == 10.0
    assert rec["before_rss_kb"] is None
    assert rec["after_rss_kb"] is None
    assert rec["delta_rss_kb"] is None
    assert rec["hygiene_wall_ms"] is None
    assert rec["cgroup_delta_bytes"] is None
    analysis = ab.analyze([rec], [rec])
    assert analysis["capture_evidence"]["A"]["delta_rss_kb"]["count"] == 0
    assert analysis["capture_evidence"]["A"]["delta_rss_kb"]["median"] is None
    assert analysis["capture_evidence"]["A"]["gc_collected"]["count"] == 1
    assert analysis["capture_evidence"]["A"]["gc_collected"]["median"] is None  # n=1


def test_invalid_structural_runs_excluded(tmp_path):
    (tmp_path / "run_001_a.json").write_text(json.dumps(_run("good-a1", "A", 8500.0)), encoding="utf-8")
    (tmp_path / "run_002_a.json").write_text(json.dumps(_run("good-a2", "A", 8400.0)), encoding="utf-8")
    # (a) garbage non-JSON file
    (tmp_path / "run_999_bad.json").write_text("this is not json {{{", encoding="utf-8")
    # (b) valid JSON with negative command_response
    neg = {"request_id": "neg", "result": {}, "timing": {"command_to_response_ms": -5}}
    (tmp_path / "run_888_neg.json").write_text(json.dumps(neg), encoding="utf-8")
    # (c) experiment record discarded at the source
    disc = _record(request_id="run_777_discarded", arm="A", retained=False, discard_reason="warm",
                   effective_env={ENV_FLAG: "0"})
    (tmp_path / "run_777_discarded.json").write_text(json.dumps(disc), encoding="utf-8")
    # (d) raw artifact whose effective_env says "1" loaded into arm A (expected "0")
    mismatch = _run("mismatch-a", "A", 8500.0, flag="1")
    (tmp_path / "run_666_mismatch.json").write_text(json.dumps(mismatch), encoding="utf-8")

    records, excluded = ab.load_arm_runs(tmp_path, "A", "0")
    assert len(records) == 2
    assert len(excluded) == 4
    excluded_ids = {r["run_id"] for r in excluded}
    assert excluded_ids == {"run_999_bad", "neg", "run_777_discarded", "mismatch-a"}
    for r in excluded:
        assert r["invalid_reasons"], f"no invalid reasons for {r['run_id']}"
    by_id = {r["run_id"]: r for r in excluded}
    assert any("unreadable artifact" in r for r in by_id["run_999_bad"]["invalid_reasons"])
    assert any("negative command_response_ms" in r for r in by_id["neg"]["invalid_reasons"])
    assert any("discarded record: warm" in r for r in by_id["run_777_discarded"]["invalid_reasons"])
    assert any("hygiene flag mismatch" in r for r in by_id["mismatch-a"]["invalid_reasons"])

    analysis = ab.analyze(records + excluded, [])
    assert analysis["valid_count_a"] == 2
    assert analysis["run_count_a"] == 6
    assert len(analysis["excluded_a"]) == 4
    report = ab.render_report(analysis)
    assert "run_999_bad" in report
    assert "mismatch-a" in report


def test_experiment_record_shape_extracts():
    rec = _record()
    extracted = ab.extract_run(rec, arm_label="B", expected_flag="1")
    assert extracted["valid"] is True
    assert extracted["run_id"] == "rec-1"
    assert extracted["command_response_ms"] == 12100.0
    assert extracted["scheduling_ms"] == 2100.0
    # C3 primary resolved from final_reconciled_waterfall.non_scheduling_ms.
    assert extracted["non_scheduling_ms"] == pytest.approx(12100.0 - (1000.0 + 2100.0), abs=1e-3)
    assert extracted["non_scheduling_source"] == "reconciled"
    assert extracted["command_to_enqueue_ms"] == 1000.0
    assert extracted["scheduling_time_ms"] == 3100.0
    # Legacy placement-only metric is present but informational.
    assert extracted["legacy_placement_excluded_ms"] == 10000.0
    assert extracted["pre_python_snapshot_restore_ms"] == 1500.0
    assert extracted["application_restore_ms"] == 8500.0
    assert extracted["hygiene_event_present"] is True
    assert extracted["gc_collected"] == 12345.0
    assert extracted["snapshot_identity"] == "snap-B"
    assert extracted["hygiene_flag_ok"] is True
    assert extracted["cold"] is True
    assert extracted["cpu"] == "4"
    assert extracted["ram"] == "32"
    # Experiment-record shape also exposes the construction session when set.
    with_session = ab.extract_run(_record(session="sess-rec-B"), arm_label="B", expected_flag="1")
    assert with_session["restore_session_id"] == "sess-rec-B"


def test_no_claim_for_n1_p90_even_with_extremes():
    a = _extract([_run("a1", "A", 100000.0)], "A")
    b = _extract([_run("b1", "B", 100.0)], "B")
    analysis = ab.analyze(a, b)
    cls = ab.classify_metric(a, b, "application_restore_ms")
    assert cls["classification"] == "INSUFFICIENT DATA"
    assert "n<2" in cls["reason"]
    assert cls["delta_ms"] is None
    assert cls["stats_a"]["p90"] is None
    assert cls["stats_b"]["p90"] is None
    report = ab.render_report(analysis)
    assert "p90 only when n>=5" in report
    assert "| 5.000 |" not in report


def test_arm_flag_absent_unverified_but_valid():
    artifact = _run("nof-a1", "A", 8500.0)
    artifact.pop("effective_env")
    rec = ab.extract_run(artifact, arm_label="A", expected_flag="0")
    assert rec["valid"] is True
    assert rec["hygiene_flag_raw"] is None
    assert rec["hygiene_flag_ok"] is None
    analysis = ab.analyze([rec], [])
    assert analysis["protocol"]["flag_verified_a"] is None
    report = ab.render_report(analysis)
    assert "UNVERIFIED" in report


# ── Fix 1: snapshot freshness via container_session_id (+ baseline) (A–F) ──


def test_freshness_same_snapshot_identity_different_containers_pass():
    """A: identical snapshot_identity (stable model hash) + distinct
    container_session_id across arms -> FRESH PASS."""
    a = _extract([_run("a1", "A", 8500.0, container="cont-A", baseline="base-A",
                       session="restore-a1", snapshot_identity="snap-shared")], "A")
    b = _extract([_run("b1", "B", 8200.0, container="cont-B", baseline="base-B",
                       session="restore-b1", snapshot_identity="snap-shared")], "B")
    analysis = ab.analyze(a, b)
    p = analysis["protocol"]
    assert p["freshness_ready_a"] is True
    assert p["freshness_ready_b"] is True
    assert p["snapshot_per_arm_fresh"] is True
    assert p["snapshot_consistent_within_arm"] == {"A": True, "B": True}
    assert p["container_sessions_a"] == ["cont-A"]
    assert p["container_sessions_b"] == ["cont-B"]
    # snapshot_identity is lineage info only and identical across arms.
    assert p["snapshot_identities_a"] == ["snap-shared"]
    assert p["snapshot_identities_b"] == ["snap-shared"]


def test_freshness_same_container_across_arms_fails():
    """B: the same container_session_id on both arms -> FAIL."""
    a = _extract([_run("a1", "A", 8500.0, container="cont-same", baseline="base-shared")], "A")
    b = _extract([_run("b1", "B", 8200.0, container="cont-same", baseline="base-shared")], "B")
    analysis = ab.analyze(a, b)
    p = analysis["protocol"]
    assert p["freshness_ready_a"] is True
    assert p["freshness_ready_b"] is True
    assert p["snapshot_per_arm_fresh"] is False
    report = ab.render_report(analysis)
    assert "snapshot_per_arm_fresh" in report


def test_freshness_multiple_runs_one_container_per_arm_pass():
    """C: several valid runs per arm all sharing one construction container -> PASS."""
    a_runs = [_run(f"a{i}", "A", 8500.0 + i, container="cont-A", baseline="base-A",
                    session=f"restore-a{i}") for i in range(3)]
    b_runs = [_run(f"b{i}", "B", 8200.0 + i, container="cont-B", baseline="base-B",
                    session=f"restore-b{i}") for i in range(3)]
    analysis = ab.analyze(_extract(a_runs, "A"), _extract(b_runs, "B"))
    p = analysis["protocol"]
    assert p["freshness_ready_a"] is True
    assert p["freshness_ready_b"] is True
    assert p["snapshot_consistent_within_arm"] == {"A": True, "B": True}
    assert p["snapshot_per_arm_fresh"] is True
    assert p["container_sessions_a"] == ["cont-A"]
    assert p["container_sessions_b"] == ["cont-B"]


def test_freshness_multiple_containers_within_arm_fails():
    """D: two different construction containers inside one arm -> FAIL."""
    a_runs = [
        _run("a1", "A", 8500.0, container="cont-A1", baseline="base-A"),
        _run("a2", "A", 8600.0, container="cont-A2", baseline="base-A"),
    ]
    b_runs = [_run("b1", "B", 8200.0, container="cont-B", baseline="base-B")]
    analysis = ab.analyze(_extract(a_runs, "A"), _extract(b_runs, "B"))
    p = analysis["protocol"]
    assert p["freshness_ready_a"] is True
    assert p["snapshot_consistent_within_arm"]["A"] is False
    assert p["snapshot_consistent_within_arm"]["B"] is True
    assert p["container_sessions_a"] == ["cont-A1", "cont-A2"]


def test_freshness_missing_construction_identity_not_ready_fail_closed():
    """E: a valid run without container_session_id AND without baseline ->
    NOT READY, never silently fresh."""
    a = _extract([_run("a1", "A", 8500.0, container=None, baseline=None)], "A")
    b = _extract([_run("b1", "B", 8200.0, container="cont-B", baseline="base-B")], "B")
    analysis = ab.analyze(a, b)
    p = analysis["protocol"]
    assert p["freshness_ready_a"] is False
    assert p["freshness_ready_b"] is True
    assert p["snapshot_per_arm_fresh"] is None  # fail-closed: not silently fresh
    assert "container_session_id" in p["freshness_not_ready_reason"]
    report = ab.render_report(analysis)
    assert "NOT READY" in report
    assert "fail-closed" in report


def test_freshness_snapshot_identity_change_does_not_change_verdict():
    """F: changing only snapshot_identity (construction identity unchanged)
    must NOT change the freshness verdict."""

    def verdict(snap_a, snap_b):
        a = _extract([_run("a1", "A", 8500.0, container="cont-A", baseline="base-A",
                           snapshot_identity=snap_a)], "A")
        b = _extract([_run("b1", "B", 8200.0, container="cont-B", baseline="base-B",
                           snapshot_identity=snap_b)], "B")
        p = ab.analyze(a, b)["protocol"]
        return (
            p["snapshot_per_arm_fresh"],
            p["snapshot_consistent_within_arm"],
            p["freshness_ready_a"],
            p["freshness_ready_b"],
        )

    v1 = verdict("snap-X", "snap-Y")
    v2 = verdict("snap-X2", "snap-Y2")
    assert v1 == v2
    assert v1[0] is True
    assert v1[1] == {"A": True, "B": True}


# ── Real-artifact regressions (K–M) ────────────────────────────────────────


def test_freshness_same_construction_different_restore_ids_fails():
    """K: the exact bug case — two runs restoring the SAME construction
    (same container_session_id AND same runtime_state_generation_baseline)
    but carrying DIFFERENT per-restore restore_session_ids must NOT be
    treated as fresh."""
    a = _extract([
        _run("a1", "A", 8500.0, container="74aa5717dfed4bf7",
             baseline="ab86ef63ce1a4914b17f699cc3052a8a",
             session="0ba8891291e64a9aa91f97b2dbb617be")
    ], "A")
    b = _extract([
        _run("b1", "B", 8200.0, container="74aa5717dfed4bf7",
             baseline="ab86ef63ce1a4914b17f699cc3052a8a",
             session="3b112f97c90c434d852178594490f4e8")
    ], "B")
    analysis = ab.analyze(a, b)
    p = analysis["protocol"]
    assert p["freshness_ready_a"] is True
    assert p["freshness_ready_b"] is True
    # Same construction container -> NOT fresh (this is the regression).
    assert p["snapshot_per_arm_fresh"] is False
    assert p["container_sessions_a"] == ["74aa5717dfed4bf7"]
    assert p["container_sessions_b"] == ["74aa5717dfed4bf7"]
    report = ab.render_report(analysis)
    assert "snapshot_per_arm_fresh" in report


def test_freshness_different_containers_even_shared_restore_pattern_pass():
    """L: DIFFERENT container_session_id across arms -> FRESH PASS even when
    the per-restore restore_session_ids happen to look similar/shared."""
    a = _extract([
        _run("a1", "A", 8500.0, container="68f839ff0fd84534", baseline="base-A",
             session="restore-uuid-1")
    ], "A")
    b = _extract([
        _run("b1", "B", 8200.0, container="9d918f0a192243b8", baseline="base-B",
             session="restore-uuid-1")  # shared-looking restore id
    ], "B")
    analysis = ab.analyze(a, b)
    p = analysis["protocol"]
    assert p["freshness_ready_a"] is True
    assert p["freshness_ready_b"] is True
    assert p["snapshot_per_arm_fresh"] is True
    assert p["container_sessions_a"] == ["68f839ff0fd84534"]
    assert p["container_sessions_b"] == ["9d918f0a192243b8"]


def test_freshness_same_container_missing_baseline_not_ready():
    """M: same container_session_id across arms but missing baseline on a run
    -> NOT READY / explicit inconsistency, never silently fresh."""
    a = _extract([
        _run("a1", "A", 8500.0, container="cont-X", baseline=None)  # baseline missing
    ], "A")
    b = _extract([
        _run("b1", "B", 8200.0, container="cont-X", baseline="base-B")
    ], "B")
    analysis = ab.analyze(a, b)
    p = analysis["protocol"]
    assert p["freshness_ready_a"] is False
    assert p["snapshot_per_arm_fresh"] is None  # fail-closed
    assert "runtime_state_generation_baseline" in p["freshness_not_ready_reason"]
    report = ab.render_report(analysis)
    assert "NOT READY" in report


def test_freshness_same_container_inconsistent_baseline_not_ready():
    """M2: same container_session_id within an arm but DIFFERENT baselines
    across its runs -> NOT READY / explicit inconsistency."""
    a_runs = [
        _run("a1", "A", 8500.0, container="cont-X", baseline="base-A1"),
        _run("a2", "A", 8600.0, container="cont-X", baseline="base-A2"),
    ]
    b_runs = [_run("b1", "B", 8200.0, container="cont-Y", baseline="base-B")]
    analysis = ab.analyze(_extract(a_runs, "A"), _extract(b_runs, "B"))
    p = analysis["protocol"]
    assert p["freshness_ready_a"] is True
    assert p["freshness_ready_b"] is True
    assert p["snapshot_per_arm_fresh"] is None  # baseline corroboration failed
    assert "baseline" in p["freshness_not_ready_reason"]
    report = ab.render_report(analysis)
    assert "NOT READY" in report or "fail-closed" in report


# ── Fix 2: accepted C3 scheduling contract (G–J) ───────────────────────────


def test_c3_reference_arithmetic_reconciled_and_fallback():
    """G: reference C3 arithmetic — command_response=35168,
    command_to_enqueue=19158, placement=854.266 -> scheduling=20012.266 ->
    non-scheduling=15155.734, both via the reconciled field and via the C3
    fallback arithmetic."""
    reconciled = ab.extract_run(
        _run("g1", "A", 8500.0, cmd_response=35168.0, sched=854.266, enqueue=19158.0),
        arm_label="A", expected_flag="0",
    )
    assert reconciled["non_scheduling_ms"] == pytest.approx(15155.734, abs=0.01)
    assert reconciled["scheduling_time_ms"] == pytest.approx(20012.266, abs=0.01)
    assert reconciled["command_to_enqueue_ms"] == pytest.approx(19158.0, abs=0.01)
    assert reconciled["non_scheduling_source"] == "reconciled"
    # Same numbers must hold when the reconciled non_scheduling_ms field is
    # absent but the enqueue component remains (C3 fallback arithmetic).
    fallback_artifact = _run("g2", "A", 8500.0, cmd_response=35168.0, sched=854.266, enqueue=19158.0)
    fallback_artifact["waterfall_local"].pop("non_scheduling_ms", None)
    fallback_artifact["waterfall_local"].pop("scheduling_time_ms", None)
    fallback = ab.extract_run(fallback_artifact, arm_label="A", expected_flag="0")
    assert fallback["non_scheduling_ms"] == pytest.approx(15155.734, abs=0.01)
    assert fallback["scheduling_time_ms"] == pytest.approx(20012.266, abs=0.01)
    assert fallback["command_to_enqueue_ms"] == pytest.approx(19158.0, abs=0.01)
    assert fallback["non_scheduling_source"] == "fallback_arithmetic"


def test_c3_enqueue_change_affects_scheduling_not_runtime():
    """H: growing the enqueue delay moves scheduling_time while the underlying
    runtime stages and non_scheduling_ms stay invariant."""
    base = ab.extract_run(
        _run("h1", "A", 8500.0, cmd_response=35168.0, sched=854.266, enqueue=19158.0),
        arm_label="A", expected_flag="0",
    )
    delayed = ab.extract_run(
        _run("h2", "A", 8500.0, cmd_response=38168.0, sched=854.266, enqueue=22158.0),
        arm_label="A", expected_flag="0",
    )
    assert delayed["command_to_enqueue_ms"] == pytest.approx(base["command_to_enqueue_ms"] + 3000.0, abs=0.01)
    assert delayed["scheduling_time_ms"] == pytest.approx(base["scheduling_time_ms"] + 3000.0, abs=0.01)
    # non_scheduling_ms is invariant under an enqueue change.
    assert delayed["non_scheduling_ms"] == pytest.approx(base["non_scheduling_ms"], abs=0.01)
    # Underlying runtime stages unchanged.
    assert delayed["pre_python_snapshot_restore_ms"] == pytest.approx(
        base["pre_python_snapshot_restore_ms"], abs=0.01)
    assert delayed["application_restore_ms"] == pytest.approx(base["application_restore_ms"], abs=0.01)


def test_c3_different_enqueue_placement_identical_non_scheduling_zero_delta():
    """I: A/B with different enqueue/placement values but identical C3
    non_scheduling_ms reports a zero primary delta."""
    a_runs = [
        _run(f"a{i}", "A", 8500.0, cmd_response=35168.0, sched=854.266, enqueue=19158.0)
        for i in range(3)
    ]
    b_runs = [
        # enqueue 15000 + placement 3000 = 18000; total 33155.734
        # -> non_scheduling 15155.734, identical to arm A.
        _run(f"b{i}", "B", 8500.0, cmd_response=33155.734, sched=3000.0, enqueue=15000.0)
        for i in range(3)
    ]
    analysis = ab.analyze(_extract(a_runs, "A"), _extract(b_runs, "B"))
    c3 = analysis["metrics"]["non_scheduling_ms"]
    assert c3["count_a"] == 3
    assert c3["count_b"] == 3
    assert c3["delta_ms"] == 0.0
    assert "no measurable difference" in c3["reason"]
    # The legacy placement-only metric DOES move (informational context only).
    legacy = analysis["metrics"]["legacy_placement_excluded_ms"]
    assert legacy["delta_ms"] is not None and legacy["delta_ms"] != 0.0
    assert analysis["overall"]["classification"] == "INSUFFICIENT DATA"


def test_c3_old_artifact_legacy_partial_not_equated():
    """J: an old artifact without the C3 fields (no reconciled
    non_scheduling_ms, no command_to_enqueue_ms) is explicitly classified as
    legacy/partial — never silently treated as an equivalent C3 value."""
    a = ab.extract_run(
        _strip_c3(_run("j1", "A", 8500.0, cmd_response=12000.0, sched=2000.0)),
        arm_label="A", expected_flag="0",
    )
    b = ab.extract_run(
        _strip_c3(_run("j2", "B", 8200.0, cmd_response=12000.0, sched=2000.0)),
        arm_label="B", expected_flag="1",
    )
    assert a["non_scheduling_ms"] is None
    assert a["non_scheduling_source"] == ""
    assert a["legacy_placement_excluded_ms"] == 10000.0  # placement-only, legacy
    analysis = ab.analyze([a], [b])
    p = analysis["protocol"]
    assert p["c3_primary_available_a"] is False
    assert p["c3_primary_available_b"] is False
    c3 = analysis["metrics"]["non_scheduling_ms"]
    assert c3["classification"] == "INSUFFICIENT DATA"
    assert "metric missing" in c3["reason"]
    report = ab.render_report(analysis)
    assert "C3 primary" in report and "legacy" in report
    assert "legacy_placement_excluded_ms" in report


# ── Host / B1 / restore-tail stratification (additive, informational) ──────


def test_b1_decision_and_reload_extraction():
    """B1 decision + check_ms + invoked come from the runtime_state_reload_decision
    trace event; reload_runtime_state_ms comes from _restore_timing."""
    artifact = _run("b1-1", "B", 8500.0)
    artifact["result"]["trace"] = {
        "events": [
            {"name": "runtime_state_reload_decision",
             "metadata": {"decision": "reloaded_generation_mismatch",
                          "reason": "generation_mismatch", "check_ms": 1.47,
                          "runtime_state_reload_invoked": 1}},
        ]
    }
    artifact["result"]["_restore_timing"]["reload_runtime_state_ms"] = 125.5
    artifact["result"]["_restore_timing"]["reload_runtime_state_invoked"] = True
    rec = ab.extract_run(artifact, arm_label="B", expected_flag="1")
    assert rec["runtime_state_reload_decision"] == "reloaded_generation_mismatch"
    assert rec["runtime_state_reload_check_ms"] == 1.47
    assert rec["runtime_state_reload_invoked"] == 1
    assert rec["reload_runtime_state_ms"] == 125.5
    assert rec["valid"] is True


def test_host_fingerprint_extraction():
    """Host fingerprint prefers the trace-event hash; waterfall host_telemetry
    is the fallback (vendor/family/model joined) plus gpu_name."""
    artifact = _run("hf-1", "B", 8500.0)
    artifact["result"]["trace"] = {
        "events": [
            {"name": "host_hardware_fingerprint",
             "metadata": {"cpuinfo_fingerprint_hash": "abc123def456",
                          "cpu_model_name": "Intel Xeon"}},
        ]
    }
    rec = ab.extract_run(artifact, arm_label="B", expected_flag="1")
    assert rec["host_fingerprint"] == "abc123def456"
    assert rec["host_cpu_model"] == "Intel Xeon"

    artifact2 = _run("hf-2", "B", 8500.0)
    artifact2["waterfall_local"]["host_telemetry"] = {
        "cpu_vendor": "GenuineIntel", "cpu_family": "6", "cpu_model": "85",
        "gpu_name": "RTX",
    }
    rec2 = ab.extract_run(artifact2, arm_label="B", expected_flag="1")
    assert rec2["host_fingerprint"] == "GenuineIntel/6/85"
    assert rec2["host_cpu_model"] == "85"
    assert rec2["gpu_name"] == "RTX"


def test_restore_tail_extraction():
    """restore_gpu_state_ms + derived residual come from _restore_timing;
    restore_bootstrap_ms comes from the v2_bootstrap_restore events."""
    artifact = _run("rt-1", "B", 8500.0)
    artifact["result"]["_restore_timing"].update({
        "restore_total_ms": 16080.6,
        "restore_gpu_state_ms": 7704.2,
        "reload_runtime_state_ms": 125.5,
        "initialize_cuda_ms": 3.1,
    })
    rec = ab.extract_run(artifact, arm_label="B", expected_flag="1")
    assert rec["restore_gpu_state_ms"] == 7704.2
    assert rec["restore_residual_ms"] == round(16080.6 - (7704.2 + 125.5 + 3.1), 3)
    assert rec["restore_bootstrap_ms"] is None  # no events, nothing fabricated

    artifact2 = _run("rt-2", "B", 8500.0)
    artifact2["result"]["trace"] = {
        "events": [
            {"name": "v2_bootstrap_restore_start", "metadata": {}},
            {"name": "v2_bootstrap_restore_end", "metadata": {"duration_ms": 7853.4}},
        ]
    }
    rec2 = ab.extract_run(artifact2, arm_label="B", expected_flag="1")
    assert rec2["restore_bootstrap_ms"] == 7853.4
