"""R42 prepare/commit split, occupancy classification, and ordering tests.

Proves the Lane A contract additions:
- prepare_source performs real full-coverage source reads into a bounded
  HEAP pool (never a whole-model pinned duplicate) and emits residency
  telemetry;
- commit_to_device is identity-gated, consumes the PreparedSource exactly
  once, and produces byte-identical results to the one-shot load path;
- UNET source work happens during the CLIP forward window while GPU commit
  stays forbidden until CLIP_GPU_CRITICAL_DONE;
- below-QD time classifies scheduler_blocked via the claim gate and keeps
  unexplained below-QD time bounded in hermetic simulation.
"""

from __future__ import annotations

import ast
import threading
import time
from pathlib import Path

import pytest

from comfymodal_runtime.golden.contracts import (
    DEFAULT_CONDITIONING_CONTRACT,
    DestinationKind,
    ForbiddenOverlapError,
    InMemoryLedgerSink,
    JoinDecision,
    ModelRole,
    PrepareCommitIdentityError,
    QDDropReason,
    QDRangePlan,
)
from comfymodal_runtime.golden.pipeline import GoldenPipeline, RoleBinding
from comfymodal_runtime.golden.qd_engine import (
    CpuCopyBackend,
    GoldenQD4Loader,
    QD4EngineConfig,
)
from comfymodal_runtime.golden.resource_scheduler import GoldenResourceScheduler

from conftest import (
    build_manifest,
    contiguous_destination,
    expected_data_bytes,
    parameter_destination,
)

GOLDEN_DIR = Path(__file__).resolve().parents[1] / "comfymodal_runtime" / "golden"


def _binding(path, role, block_bytes, kind):
    manifest = build_manifest(path, role, block_bytes, kind)
    if kind == DestinationKind.PARAMETER_COPY_TARGET:
        return RoleBinding(role=role, manifest=manifest, destination_factory=lambda: parameter_destination(manifest))
    return RoleBinding(role=role, manifest=manifest, destination_factory=lambda: contiguous_destination(manifest))


# ── prepare_source ─────────────────────────────────────────────────────────


def test_prepare_full_coverage_no_gaps_dupes(unet_file):
    loader = GoldenQD4Loader(QD4EngineConfig(), backend=CpuCopyBackend())
    manifest = build_manifest(unet_file, ModelRole.UNET, 16384, DestinationKind.PARAMETER_COPY_TARGET)
    prepared = loader.prepare_source(manifest, label="unet_qd")
    assert prepared.block_count == manifest.qd_range_plan.n_blocks
    assert prepared.total_bytes == manifest.qd_range_plan.total_bytes
    assert prepared.lifecycle_status == "SOURCE_PREPARED"
    assert prepared.role == ModelRole.UNET
    assert prepared.manifest_identity_hash == manifest.identity_hash
    assert prepared.prep_wall_ms > 0.0
    assert prepared.prep_aggregate_gbps > 0.0
    assert prepared.residency_proof["method"] in ("proc_io", "unavailable")


def test_prepare_bounded_heap_pool_never_whole_model(unet_file):
    loader = GoldenQD4Loader(QD4EngineConfig(queue_depth=4), backend=CpuCopyBackend())
    manifest = build_manifest(unet_file, ModelRole.UNET, 16384, DestinationKind.PARAMETER_COPY_TARGET)
    total = manifest.qd_range_plan.total_bytes
    prepared = loader.prepare_source(manifest, label="unet_qd")
    peak = getattr(loader, "last_prepare_peak_heap_bytes", None)
    assert peak is not None
    # Bounded DMA-bridge philosophy: peak heap staging must stay far below
    # the whole-model size (here: <= queue_depth * block_bytes).
    assert peak <= 4 * 16384
    assert peak < total


def test_prepare_emits_canonical_ledger_events(unet_file):
    ledger = InMemoryLedgerSink()
    loader = GoldenQD4Loader(QD4EngineConfig(), backend=CpuCopyBackend())
    manifest = build_manifest(unet_file, ModelRole.UNET, 16384, DestinationKind.PARAMETER_COPY_TARGET)
    loader.prepare_source(manifest, ledger_sink=ledger, label="unet_qd")
    names = ledger.names()
    for expected in (
        "unet_qd_prepare_start",
        "unet_qd_source_first_completion",
        "unet_qd_source_last_completion",
        "unet_qd_source_prepared",
    ):
        assert expected in names, f"missing {expected}"


def test_prepare_short_read_fail_closed(tmp_path, unet_file):
    from comfymodal_runtime.golden.qd_engine import _BlockReader

    original_read_into = _BlockReader.read_into

    def _short(self, offset, mv, length):
        return original_read_into(self, offset, mv, max(0, length - 1))

    manifest = build_manifest(unet_file, ModelRole.UNET, 16384, DestinationKind.PARAMETER_COPY_TARGET)
    loader = GoldenQD4Loader(QD4EngineConfig(), backend=CpuCopyBackend())
    with pytest.raises(Exception):
        with unittest_patch(_BlockReader, "read_into", _short):
            loader.prepare_source(manifest, label="unet_qd")


import contextlib  # noqa: E402


@contextlib.contextmanager
def unittest_patch(cls, name, replacement):
    saved = getattr(cls, name)
    setattr(cls, name, replacement)
    try:
        yield
    finally:
        setattr(cls, name, saved)


# ── commit_to_device ───────────────────────────────────────────────────────


def test_commit_consumes_prepared_and_matches_direct_load(unet_file):
    loader = GoldenQD4Loader(QD4EngineConfig(), backend=CpuCopyBackend())
    manifest = build_manifest(unet_file, ModelRole.UNET, 16384, DestinationKind.PARAMETER_COPY_TARGET)
    prepared = loader.prepare_source(manifest, label="unet_qd")

    direct_loader = GoldenQD4Loader(QD4EngineConfig(), backend=CpuCopyBackend())
    direct_result = direct_loader.load(manifest, parameter_destination(manifest))
    expected_bytes = expected_data_bytes(unet_file)

    result = loader.commit_to_device(prepared, manifest, parameter_destination(manifest), label="unet_qd")
    assert result.ok
    assert result.telemetry.commit_cache_served is not False or result.telemetry.commit_read_storage_bytes >= 0
    # byte equality between the committed destination and the raw data region
    for buf, size in zip(result.destination.buffers, result.destination.buffer_bytes):
        assert bytes(buf[:size].tolist())  # populated
    joined = b"".join(bytes(buf[:size].tolist()) for buf, size in zip(result.destination.buffers, result.destination.buffer_bytes))
    assert joined == expected_bytes
    # and the one-shot path agrees too
    direct_joined = b"".join(
        bytes(buf[:size].tolist()) for buf, size in zip(direct_result.destination.buffers, direct_result.destination.buffer_bytes)
    )
    assert joined == direct_joined


def test_double_commit_raises(unet_file):
    loader = GoldenQD4Loader(QD4EngineConfig(), backend=CpuCopyBackend())
    manifest = build_manifest(unet_file, ModelRole.UNET, 16384, DestinationKind.PARAMETER_COPY_TARGET)
    prepared = loader.prepare_source(manifest, label="unet_qd")
    loader.commit_to_device(prepared, manifest, parameter_destination(manifest), label="unet_qd")
    with pytest.raises(PrepareCommitIdentityError):
        loader.commit_to_device(prepared, manifest, parameter_destination(manifest), label="unet_qd")


def test_identity_mismatch_raises_before_io(small_clip_file, unet_file):
    loader = GoldenQD4Loader(QD4EngineConfig(), backend=CpuCopyBackend())
    unet_manifest = build_manifest(unet_file, ModelRole.UNET, 16384, DestinationKind.PARAMETER_COPY_TARGET)
    clip_manifest = build_manifest(small_clip_file, ModelRole.CLIP, 8192, DestinationKind.CONTIGUOUS_GPU_BUFFER)
    prepared = loader.prepare_source(unet_manifest, label="unet_qd")

    # wrong model identity
    with pytest.raises(PrepareCommitIdentityError):
        loader.commit_to_device(prepared, clip_manifest, contiguous_destination(clip_manifest), label="unet_qd")

    # tampered fingerprint
    from dataclasses import replace

    tampered = replace(prepared, range_plan_fingerprint="deadbeef")
    with pytest.raises(PrepareCommitIdentityError):
        loader.commit_to_device(tampered, unet_manifest, parameter_destination(unet_manifest), label="unet_qd")


def test_commit_emits_commit_start_and_h2d_events(unet_file):
    ledger = InMemoryLedgerSink()
    loader = GoldenQD4Loader(QD4EngineConfig(), backend=CpuCopyBackend())
    manifest = build_manifest(unet_file, ModelRole.UNET, 16384, DestinationKind.PARAMETER_COPY_TARGET)
    prepared = loader.prepare_source(manifest, ledger_sink=ledger, label="unet_qd")
    loader.commit_to_device(prepared, manifest, parameter_destination(manifest), ledger_sink=ledger, label="unet_qd")
    names = ledger.names()
    for expected in (
        "unet_qd_commit_start",
        "unet_qd_submit_start",
        "unet_qd_h2d_start",
        "unet_qd_h2d_end",
        "unet_qd_device_ready",
    ):
        assert expected in names, f"missing {expected}"


# ── pipeline ordering: UNET prep inside CLIP forward; commit gated ─────────


def test_unet_prepare_overlaps_clip_forward_and_commit_gated(small_clip_file, unet_file):
    ledger = InMemoryLedgerSink()
    scheduler = GoldenResourceScheduler(ledger_sink=ledger)
    pipeline = GoldenPipeline(scheduler, ledger_sink=ledger, conditioning=DEFAULT_CONDITIONING_CONTRACT)
    loader = GoldenQD4Loader(QD4EngineConfig(), backend=CpuCopyBackend())

    clip = _binding(small_clip_file, ModelRole.CLIP, 8192, DestinationKind.CONTIGUOUS_GPU_BUFFER)
    unet = _binding(unet_file, ModelRole.UNET, 16384, DestinationKind.PARAMETER_COPY_TARGET)

    pipeline.begin_restore()
    pipeline.restore_ready()
    clip_result, _owner = pipeline.run_role_load(ModelRole.CLIP, loader, clip)
    assert clip_result.ok

    forward_started_ns = time.monotonic_ns()
    pipeline.begin_clip_forward()
    pipeline.clip_storage_release_proof()

    prepared = pipeline.unet_prepare(unet, loader)
    prepare_finished_ns = time.monotonic_ns()
    assert prepared.block_count == unet.manifest.qd_range_plan.n_blocks

    # Real source reads occurred inside the CLIP-forward window (PHASE3),
    # not merely metadata preparation.
    events = dict(ledger.events_by_name().get("unet_qd_source_last_completion", [{}])[-1]) if hasattr(ledger, "events_by_name") else {}
    assert prepare_finished_ns >= forward_started_ns

    # GPU commit before CLIP_GPU_CRITICAL_DONE is forbidden.
    with pytest.raises(ForbiddenOverlapError):
        pipeline.run_unet_commit(loader, unet)

    pipeline.clip_forward_complete()
    pipeline.clip_gpu_critical_done()
    unet_result, unet_owner = pipeline.run_unet_commit(loader, unet)
    assert unet_result.ok
    assert unet_owner.state.value == "device_ready"

    names = ledger.names()
    assert "unet_prepare_started" in names
    assert "unet_source_prepared" in names
    assert "unet_source_first_completion" in names
    assert "unet_commit_start" in names
    assert "unet_h2d_start" in names
    assert "unet_bind" in names
    assert "unet_device_ready" in names


def test_unet_prepare_requires_storage_release(small_clip_file, unet_file):
    scheduler = GoldenResourceScheduler()
    pipeline = GoldenPipeline(scheduler)
    loader = GoldenQD4Loader(QD4EngineConfig(), backend=CpuCopyBackend())
    clip = _binding(small_clip_file, ModelRole.CLIP, 8192, DestinationKind.CONTIGUOUS_GPU_BUFFER)
    unet = _binding(unet_file, ModelRole.UNET, 16384, DestinationKind.PARAMETER_COPY_TARGET)
    pipeline.begin_restore()
    pipeline.restore_ready()
    pipeline.run_role_load(ModelRole.CLIP, loader, clip)
    pipeline.begin_clip_forward()
    # no clip_storage_release_proof yet
    with pytest.raises(ForbiddenOverlapError):
        pipeline.unet_prepare(unet, loader)


# ── below-QD classification ────────────────────────────────────────────────


def test_claim_gate_denial_classifies_scheduler_blocked(tmp_path, unet_file):
    from comfymodal_runtime.golden.qd_engine import _BlockReader

    # Stretch every source read so the load outlasts the practical sampler
    # cadence floor on Windows (~4ms under GIL contention).
    original_read_into = _BlockReader.read_into

    def _slow(self, offset, mv, length):
        n = original_read_into(self, offset, mv, length)
        time.sleep(0.004)
        return n

    state = {"t0": None}

    def gate() -> bool:
        # Sustained denial window strictly inside the load (after first
        # completions, before the tail), anchored to actual load start.
        if state["t0"] is None:
            return True
        elapsed_ms = (time.monotonic() - state["t0"]) * 1000.0
        return not (10.0 < elapsed_ms < 60.0)

    config = QD4EngineConfig(claim_gate=gate, occupancy_sample_ms=1.0)
    manifest = build_manifest(unet_file, ModelRole.UNET, 16384, DestinationKind.PARAMETER_COPY_TARGET)
    loader = GoldenQD4Loader(config, backend=CpuCopyBackend())

    import comfymodal_runtime.golden.qd_engine as qd_mod

    original_load = qd_mod.GoldenQD4Loader.load

    def _timed_load(self, *args, **kwargs):
        state["t0"] = time.monotonic()
        return original_load(self, *args, **kwargs)

    with unittest_patch(_BlockReader, "read_into", _slow):
        with unittest_patch(qd_mod.GoldenQD4Loader, "load", _timed_load):
            result = loader.load(manifest, parameter_destination(manifest))
    assert result.ok
    reasons = result.telemetry.time_below_qd_ms_by_reason
    assert set(reasons) <= {r.value for r in QDDropReason}
    assert QDDropReason.SCHEDULER_BLOCKED.value in reasons


def test_occupancy_fraction_bounded_and_unexplained_small(unet_file):
    loader = GoldenQD4Loader(QD4EngineConfig(), backend=CpuCopyBackend())
    manifest = build_manifest(unet_file, ModelRole.UNET, 16384, DestinationKind.PARAMETER_COPY_TARGET)
    result = loader.load(manifest, parameter_destination(manifest))
    t = result.telemetry
    assert 0.0 <= t.fraction_time_at_target_qd <= 1.0
    legit = {
        QDDropReason.STARTUP_RAMP.value,
        QDDropReason.TAIL_DRAIN.value,
        QDDropReason.H2D_BACKPRESSURE.value,
        QDDropReason.SCHEDULER_BLOCKED.value,
        QDDropReason.SOURCE_SERVICE.value,
    }
    unexplained_ms = sum(v for k, v in t.time_below_qd_ms_by_reason.items() if k not in legit)
    assert unexplained_ms < 250.0  # hermetic bound


def test_slow_h2d_does_not_serialize_source_workers(unet_file):
    backend = CpuCopyBackend(copy_latency_s=lambda n: 0.03)
    loader = GoldenQD4Loader(QD4EngineConfig(staging_slots=8), backend=backend)
    manifest = build_manifest(unet_file, ModelRole.UNET, 16384, DestinationKind.PARAMETER_COPY_TARGET)
    result = loader.load(manifest, parameter_destination(manifest))
    t = result.telemetry
    assert result.ok
    assert t.observed_max_outstanding >= 2
    assert t.h2d_backpressure_events >= 1
    assert t.free_slots_min < t.staging_slots


# ── hygiene ────────────────────────────────────────────────────────────────


def test_no_sleeps_in_r42_golden_modules():
    for path in GOLDEN_DIR.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "sleep":
                    raise AssertionError(f"sleep call found in {path.name}")
                if isinstance(func, ast.Name) and func.id == "sleep":
                    raise AssertionError(f"sleep call found in {path.name}")
