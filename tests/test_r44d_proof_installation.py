"""R44D non-Golden proof-installation tests.

Covers the three R44D corrections that make the request-time FastSafe /
non-Golden composition produce truthful strict-proof telemetry:

1. ``modal_app.run_plan_stream`` installs the model_preload CLIP span
   wrappers composition-independently (source-level contract).
2. A real raw encode under a non-Golden composition emits the canonical
   forced-miss conditioning evidence (lookup hit=false + decision
   miss_not_stored) exactly once per request trace.
3. The E37 clean-lane validator scopes its QD4-transport block to
   QD-requested runs while keeping the universal forward-contract checks.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

from tools.v2_control.validation import E37CleanLaneProofValidator, RunRecord
from tests.v2ctl_fakes import FakeArtifactSet, FakeConfig, FakeFlag

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# 1) run_plan_stream installs the span wrappers for every v2 request
# ---------------------------------------------------------------------------


def test_run_plan_stream_installs_clip_spans_independently_of_golden():
    source = (ROOT / "comfymodal_runtime" / "modal_app.py").read_text(encoding="utf-8")
    install_pos = source.index("_r44d_install_clip_spans(trace=diagnostics)")
    r44b_pos = source.index("# ── R44B: first-class request-time FastSafe context")
    watcher_pos = source.index("_remote_watcher.start()")
    # Installed at request entry, after the watcher starts, BEFORE the R44B
    # lane opens, and outside any Golden/_gctx conditional block.
    assert watcher_pos < install_pos < r44b_pos
    assert "_install_clip_span_wrappers as _r44d_install_clip_spans" in source


# ---------------------------------------------------------------------------
# 2) raw-encode bypass emits canonical forced-miss evidence once per trace
# ---------------------------------------------------------------------------


class _RecordingTrace:
    def __init__(self):
        self.events: list[dict] = []
        self.request_id = "r44d-trace"

    def emit(self, name, phase="execution", metadata=None, **kwargs):
        self.events.append({"name": name, "metadata": dict(metadata or {})})

    def emit_at(self, name, wall_unix_ns=None, monotonic_ns=None, phase="execution", metadata=None, **kwargs):
        self.events.append({"name": name, "metadata": dict(metadata or {})})


@pytest.fixture()
def clip_span_harness(monkeypatch):
    """Install the real span wrappers over a fake comfy.sd.CLIP."""
    import comfymodal_runtime.model_preload as mp

    monkeypatch.setenv("COMFYMODAL_V2_E37_CLEAN_LANE", "1")
    monkeypatch.setenv("COMFYMODAL_V2_CLEAN_LANE", "1")

    calls: list[str] = []

    class FakeCLIP:
        def tokenize(self, text):
            calls.append("tokenize")
            return ("tokens",)

        def load_model(self):
            calls.append("load_model")

        def encode_from_tokens(self, tokens, **kwargs):
            calls.append("encode_from_tokens")
            return "COND"

        def encode_from_tokens_scheduled(self, tokens, **kwargs):
            calls.append("encode_from_tokens_scheduled")
            return "COND"

        def encode_token_weights(self, tokens):
            calls.append("encode_token_weights")
            return ("W",)

    fake_sd = types.ModuleType("comfy.sd")
    fake_sd.CLIP = FakeCLIP

    # Cheap snapshots + no-op pre-hook for the offline harness.
    fake_pf = type("_PF", (), {"unavailable": True})()
    monkeypatch.setattr(
        mp, "_clip_span_snapshot",
        lambda with_cuda=False: {
            "wall_unix_ns": 0,
            "counters": {"mono_ns": 0},
            "pagefaults": fake_pf,
        },
    )
    monkeypatch.setattr(mp, "_clip_raw_encode_pre_hook", lambda args, kwargs: None)

    status = mp._install_clip_span_wrappers(sd_mod=fake_sd, trace=None)
    assert status.get("clip_raw_encode") in ("installed", "already_installed")

    yield types.SimpleNamespace(
        mp=mp, cls=FakeCLIP, calls=calls,
        request_trace_var=mp._ACTIVE_REQUEST_TRACE,
    )
    mp.uninstall_for_tests() if hasattr(mp, "uninstall_for_tests") else None


def test_raw_encode_bypass_emits_forced_miss_evidence_once(clip_span_harness, monkeypatch):
    h = clip_span_harness
    trace = _RecordingTrace()
    token = h.request_trace_var.set(trace)
    try:
        assert h.cls().encode_from_tokens("tok") == "COND"
    finally:
        h.request_trace_var.reset(token)

    names = [e["name"] for e in trace.events]
    assert "clip_raw_encode_start" in names
    assert "clip_raw_encode_end" in names
    lookups = [e for e in trace.events if e["name"] == "clip_conditioning_cache_lookup"]
    decisions = [e for e in trace.events if e["name"] == "clip_conditioning_cache_decision"]
    assert len(lookups) == 1
    assert lookups[0]["metadata"]["hit"] is False
    assert lookups[0]["metadata"]["miss_count"] == 1
    assert lookups[0]["metadata"]["real_encode_request"] is True
    assert len(decisions) == 1
    assert decisions[0]["metadata"]["decision"] == "miss_not_stored"
    assert decisions[0]["metadata"]["encode_calls"] == 1


def test_raw_encode_bypass_dedupes_per_trace(clip_span_harness):
    h = clip_span_harness
    trace = _RecordingTrace()
    token = h.request_trace_var.set(trace)
    try:
        h.cls().encode_from_tokens("tok-a")
        h.cls().encode_from_tokens("tok-b")
    finally:
        h.request_trace_var.reset(token)
    decisions = [e for e in trace.events if e["name"] == "clip_conditioning_cache_decision"]
    assert len(decisions) == 1


def test_raw_encode_bypass_silent_under_golden(clip_span_harness, monkeypatch):
    import comfymodal_runtime.golden_runtime_bridge as grb

    h = clip_span_harness
    monkeypatch.setattr(grb, "current", lambda: object())
    trace = _RecordingTrace()
    token = h.request_trace_var.set(trace)
    try:
        h.cls().encode_from_tokens("tok")
    finally:
        h.request_trace_var.reset(token)
    assert not [e for e in trace.events if e["name"].startswith("clip_conditioning_cache")]


# ---------------------------------------------------------------------------
# 3) clean-lane validator scoping
# ---------------------------------------------------------------------------


def _clean_lane_record(tmp_path, proof_metadata):
    artifact = tmp_path / "run.json"
    artifact.write_text(json.dumps({
        "trace": {"events": [{"name": "clean_lane_proof", "metadata": proof_metadata}]},
    }), encoding="utf-8")
    config = FakeConfig(profile_name="r44-request-fastsafe")
    config.flags.append(FakeFlag("COMFYMODAL_V2_E37_CLEAN_LANE", "1"))
    record = RunRecord(
        run_fingerprint="r" * 64,
        deploy_fingerprint="d" * 64,
        profile=config.profile_name,
        target_app=config.target.app,
        target_class=config.target.class_name,
        fresh_required=True,
        expected_output_sha="x",
        artifacts=FakeArtifactSet(run_artifact=artifact),
        backend_ok=True,
        telemetry={},
        output_sha="x",
    )
    return record, config


def test_clean_lane_validator_non_qd_requires_forward_contract_only(tmp_path):
    proof = {
        "mode": "E37_CLEAN_LANE", "proof_version": 1,
        "ordering": {
            "restore_return_ns": 10, "plan_identity_complete_ns": 20,
            "forward_start_ns": 30, "forward_end_ns": 40,
        },
        "forbidden_activity_attempts": [],
        "thread_state": {"python_thread_count": 1},
        # NOTE: deliberately NO qd/volume/quiescence/phase_intervals fields:
        # definitionally absent when the QD reader arm is off (R44 FastSafe).
    }
    record, config = _clean_lane_record(tmp_path, proof)
    failures = E37CleanLaneProofValidator().validate(record, config)
    assert failures == []


def test_clean_lane_validator_qd_requested_still_demands_qd_proof(tmp_path):
    proof = {
        "mode": "E37_CLEAN_LANE", "proof_version": 1,
        "ordering": {
            "restore_return_ns": 10, "plan_identity_complete_ns": 20,
            "forward_start_ns": 30, "forward_end_ns": 40,
        },
        "forbidden_activity_attempts": [],
        "thread_state": {"python_thread_count": 1},
    }
    record, config = _clean_lane_record(tmp_path, proof)
    config.flags.append(FakeFlag("COMFYMODAL_V2_CLIP_QD_READER", "1"))
    failures = E37CleanLaneProofValidator().validate(record, config)
    text = "\n".join(failures)
    assert "CLEAN_LANE actual QD must be 4" in text
    assert "CLEAN_LANE Volume read identity/interval proof missing" in text
    assert "CLEAN_LANE quiescence proof missing or false" in text


def test_clean_lane_validator_missing_proof_still_fails(tmp_path):
    record, config = _clean_lane_record(tmp_path, {"mode": "WRONG"})
    failures = E37CleanLaneProofValidator().validate(record, config)
    assert any("mode/version" in f for f in failures)


def test_clean_lane_validator_bad_forward_order_fails_non_qd(tmp_path):
    proof = {
        "mode": "E37_CLEAN_LANE", "proof_version": 1,
        "ordering": {
            "restore_return_ns": 10, "plan_identity_complete_ns": 20,
            "forward_start_ns": 41, "forward_end_ns": 40,
        },
        "forbidden_activity_attempts": [],
        "thread_state": {"python_thread_count": 1},
    }
    record, config = _clean_lane_record(tmp_path, proof)
    failures = E37CleanLaneProofValidator().validate(record, config)
    assert any("ordering" in f for f in failures)
