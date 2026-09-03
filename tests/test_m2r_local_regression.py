"""M2R offline regression fixtures for the persisted Golden report contract."""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

import pytest

from comfymodal_runtime.full_trace_report import generate_full_trace_report
from comfymodal_runtime.golden_human_report import (
    ClockDomainError,
    render_full_console,
    render_overall_timeline,
    render_stage_artifact,
)

pytestmark = pytest.mark.fast_unit


def _x(name: str, start_us: int, duration_us: int, *, args: dict[str, Any] | None = None) -> dict[str, Any]:
    event: dict[str, Any] = {
        "ph": "X", "name": name, "ts": start_us, "dur": duration_us,
        "pid": 1, "tid": 1,
    }
    if args:
        event["args"] = args
    return event


def _session(
    tmp_path: Path,
    *,
    events: list[dict[str, Any]],
    runtime_result: dict[str, Any] | None = None,
    session_events: list[dict[str, Any]] | None = None,
    trace_config: dict[str, Any] | None = None,
) -> Path:
    raw = tmp_path / "raw"
    raw.mkdir(parents=True)
    (raw / "viztracer.json.gz").write_bytes(gzip.compress(json.dumps({
        "traceEvents": events,
        "metadata": {"dump_counter": len(events), "tracer_args": {"entry_capacity": 1000}},
    }).encode()))
    if runtime_result is not None:
        (raw / "runtime_result_summary.json").write_text(json.dumps(runtime_result), encoding="utf-8")
    if session_events is not None:
        (raw / "session_events.jsonl").write_text(
            "\n".join(json.dumps(event) for event in session_events), encoding="utf-8"
        )
    if trace_config is not None:
        (raw / "trace_config.json").write_text(json.dumps(trace_config), encoding="utf-8")
    return tmp_path


def _load_report(session: Path) -> dict[str, Any]:
    generate_full_trace_report(session)
    return json.loads((session / "derived" / "report_data.json").read_text(encoding="utf-8"))


def _golden_events(*, sampling_duration_us: int = 40_000) -> list[dict[str, Any]]:
    names = (
        "golden_restore", "golden_request_setup", "golden_clip_load",
        "golden_clip_forward", "golden_unet_load", "golden_sampler_prepare",
        "golden_vae_load", "golden_sampling", "golden_sampler_tail",
        "golden_vae_decode", "golden_output",
    )
    return [
        _x("golden_serial_execute", 0, 1_000_000),
        *[_x(
            name, (index + 1) * 50_000,
            sampling_duration_us if name == "golden_sampling" else 40_000,
        ) for index, name in enumerate(names)],
    ]


def _transport_record(stage: str, role: str) -> dict[str, Any]:
    return {
        "name": stage,
        "role": role,
        "actual_source": {
            "role": role,
            "SOURCE_TOTAL_WALL_MS": 22.0,
            "H2D_TOTAL_WALL_MS": 31.0,
            "h2d_submitted_bytes": 128,
            "h2d_completed_bytes": 128,
            "h2d_reconciliation_complete": True,
            "actual_source_events": [{"producer_id": 0, "start_ns": 100, "end_ns": 200}],
            "h2d_events": [{"token": 0, "start_ns": 120, "end_ns": 180}],
        },
    }


def _sampling_payload(*, residual_ms: float = 0.0) -> dict[str, Any]:
    origin = 10_000_000_000
    per_eval = [
        {
            "index": index, "step": min(index // 2, 7), "row": index,
            "compute_or_skip": "compute", "start_monotonic_ns": origin + index * 10_000_000,
            "end_monotonic_ns": origin + index * 10_000_000 + 5_000_000,
        }
        for index in range(17)
    ]
    return {
        "schema_version": 1,
        "level": "steps",
        "status": "ok",
        "steps": 8,
        "evals": {"count": 17, "per_eval": per_eval},
        "sampling_window": {
            "start_monotonic_ns": origin,
            "end_monotonic_ns": origin + 200_000_000,
        },
        "timeline_steps": [
            {"step_index": index, "start_ns": origin + index * 20_000_000,
             "end_ns": origin + (index + 1) * 20_000_000}
            for index in range(8)
        ],
        "alignment": {
            "clock": "monotonic_ns", "source": "golden_sampling",
            "monotonic_origin_ns": origin, "golden_origin_ms": 400.0,
        },
        "reconciliation": {"sampling_residual_ms": residual_ms},
    }


def test_canonical_spans_drive_overall_union_and_residual(tmp_path: Path):
    report = _load_report(_session(tmp_path, events=_golden_events()))
    profile = report["golden_profile"]
    assert {span["name"] for span in profile["canonical_spans"]} >= {
        "golden_clip_load", "golden_clip_forward", "golden_unet_load",
        "golden_sampler_prepare", "golden_vae_load", "golden_sampling",
        "golden_vae_decode",
    }
    overall = render_overall_timeline(report)
    accounting = next(line for line in overall.splitlines() if line.startswith("ACCOUNTING"))
    assert "canonical_stage_union 320.0ms" in accounting
    assert "residual_pct 68.0%" in accounting


def test_transport_is_load_only_and_ambiguous_identity_is_unavailable(tmp_path: Path):
    stages = [
        _transport_record("golden_clip_load", "clip"),
        _transport_record("golden_unet_load", "unet"),
        _transport_record("golden_vae_load", "vae"),
    ]
    report = _load_report(_session(
        tmp_path, events=_golden_events(),
        runtime_result={"golden_telemetry": {"stages": [
            {"name": item["name"], "details": {"transport_stats": item}}
            for item in stages
        ]}},
    ))
    assert report["source_h2d_transport"]["by_stage"]["golden_clip_load"]["status"] == "available"
    for stage, title, role in (
        ("golden_clip_forward", "CLIP FORWARD", "clip"),
        ("golden_sampling", "SAMPLING", "sampling"),
        ("golden_vae_decode", "VAE DECODE", "vae_decode"),
    ):
        text = render_stage_artifact(report, title, stage, role=role)
        assert "TRANSPORT (nested)" not in text
    ambiguous = _load_report(_session(
        tmp_path / "ambiguous", events=_golden_events(),
        runtime_result={"golden_telemetry": {"stages": [
            {"name": "golden_clip_load", "details": {"transport_stats": _transport_record("golden_clip_load", "vae")}},
        ]}},
    ))
    assert ambiguous["source_h2d_transport"]["by_stage"]["golden_clip_load"]["status"] == "unavailable"


def test_sampling_roundtrip_preserves_window_timestamps_alignment_and_rows(tmp_path: Path):
    payload = json.loads(json.dumps(_sampling_payload()))
    report = _load_report(_session(
        tmp_path, events=_golden_events(sampling_duration_us=250_000),
        session_events=[{"event": "sampling_deep_profile", "metadata": payload}],
    ))
    rows = report["golden_profile"]["sampling_temporal_rows"]
    assert sum(row["label"].startswith("eval ") for row in rows) == 17
    assert sum(row["label"].startswith("step ") for row in rows) == 8
    assert report["sampling_deep_profile"]["status"] == "available"
    text = (tmp_path / "derived" / "golden_sampling_breakdown.txt").read_text(encoding="utf-8")
    assert "step 0" in text and "eval step:0" in text


def test_vae_parent_and_cross_evidence_residual_only_classification(tmp_path: Path):
    payload = _sampling_payload(residual_ms=75.0)
    report = _load_report(_session(
        tmp_path, events=_golden_events(),
        session_events=[{"event": "sampling_deep_profile", "metadata": payload}],
        runtime_result={"golden_telemetry": {"stages": [{
            "name": "golden_vae_load", "details": {"transport_stats": _transport_record("golden_vae_load", "vae")},
        }]}},
    ))
    vae = next(span for span in report["golden_profile"]["canonical_spans"] if span["name"] == "golden_vae_load")
    assert vae["wall_ms"] == 40.0
    assert vae["classification"] in {"CROSS_EVIDENCE_DECOMPOSED", "PARTIALLY_DECOMPOSED"}
    unresolved = report["unresolved_over_50ms"]
    assert all(row["name"] not in {"golden_vae_load", "golden_sampling"} for row in unresolved)
    assert {row["name"] for row in unresolved} >= {"sampling residual"}


def test_module_and_vae_decode_node_records_survive_envelope_report(tmp_path: Path):
    report = _load_report(_session(
        tmp_path, events=_golden_events(),
        runtime_result={
            "golden_telemetry": {"stages": [{"name": "golden_clip_forward", "details": {
                "clip_forward_decomposition": {"module_records": [{
                    "qualified_name": "clip.encoder.layer.0",
                    "start_monotonic_ns": 1_000_000_000,
                    "end_monotonic_ns": 1_060_000_000,
                }]},
            }}]},
            "node_timing_records": [{
                "node_id": "3", "class_type": "VAEDecode",
                "start_monotonic_ns": 2_000_000_000,
                "end_monotonic_ns": 2_060_000_000,
            }],
        },
    ))
    assert report["clip_module_records_status"] == "available"
    assert "clip.encoder.layer.0 inclusive 60.0ms" in render_stage_artifact(
        report, "CLIP FORWARD", "golden_clip_forward", role="clip"
    )
    vae_text = render_stage_artifact(report, "VAE DECODE", "golden_vae_decode", role="vae_decode")
    assert "VAEDecode node row: persisted" in vae_text
    assert "VAEDecode inclusive 60.0ms" in vae_text


def test_renderer_contracts_width_point_cross_clock_and_persisted_projection(tmp_path: Path):
    report = _load_report(_session(tmp_path, events=_golden_events()))
    console = render_full_console(report)
    persisted = (tmp_path / "derived" / "golden_profiler_console.txt").read_text(encoding="utf-8")
    assert console.replace("\r\n", "\n") == persisted.replace("\r\n", "\n")
    for line in console.splitlines():
        if "|" in line and "█" in line:
            assert len(line.split("|")[1]) == 100
    with pytest.raises(ClockDomainError):
        render_overall_timeline({"golden_profile": {"root": {
            "start_ms": 0, "end_ms": 100, "wall_ms": 100, "clock_domain": "cuda",
            "children": [],
        }}}, clock_domain="host_monotonic")
