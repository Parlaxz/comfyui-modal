"""R41 Golden pipeline — deterministic LOCAL benchmark/evidence runner.

NO Modal deployment, NO remote calls, NO paid generation.  This tool proves,
on synthetic data, the properties that physical Modal runs must later
confirm after E40/R41 reconciliation:

  A. QD4 occupancy mechanics: configured=4, peak=4, time-weighted occupancy,
     bounded staging (8 x block_bytes pinned-equivalent slots).
  B. Source/H2D decoupling: with injected slow H2D the source plane still
     saturates at QD4; every below-QD interval is classified (backpressure /
     startup / tail) — unexplained starvation stays negligible.
  C. Golden timeline: one schedule for CLIP/UNET/VAE through ONE loader
     engine; exact event ordering; one read per role (registry-enforced);
     fallback can never be ACCEPTED_NOMINAL.

Usage:  python tools/golden_local_benchmark.py [--out PATH]
Output: JSON evidence document on stdout (and to --out when given).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from comfymodal_runtime.golden.contracts import (  # noqa: E402
    DEFAULT_CONDITIONING_CONTRACT,
    DestinationKind,
    InMemoryLedgerSink,
    JoinDecision,
    ModelRole,
    RuntimeStatus,
)
from comfymodal_runtime.golden.pipeline import (  # noqa: E402
    GoldenPipeline,
    RoleBinding,
    final_status,
)
from comfymodal_runtime.golden.qd_engine import (  # noqa: E402
    CpuCopyBackend,
    GoldenQD4Loader,
    QD4EngineConfig,
    parse_safetensors_header,
)
from comfymodal_runtime.golden.resource_scheduler import GoldenResourceScheduler  # noqa: E402
from comfymodal_runtime.golden.snapshot import assert_quiescent, build_snapshot_manifest  # noqa: E402

BLOCK_BYTES = 1024 * 1024
N_BLOCKS = 64  # 64 MiB synthetic model


def write_safetensors(path: Path, total_bytes: int) -> Path:
    header = {"blob": {"dtype": "U8", "shape": [total_bytes], "data_offsets": [0, total_bytes]}}
    header_bytes = json.dumps(header).encode("utf-8")
    chunk = bytes(range(251)) * ((1 << 16) // 250 + 1)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<Q", len(header_bytes)))
        fh.write(header_bytes)
        written = 0
        while written < total_bytes:
            n = min(len(chunk), total_bytes - written)
            fh.write(chunk[:n])
            written += n
    return path


def build_manifest(path: str, role: ModelRole) -> object:
    from comfymodal_runtime.golden.contracts import QDRangePlan, RoleManifest

    layout = parse_safetensors_header(path)
    plan = QDRangePlan.build(layout, BLOCK_BYTES, buffer_mode="contiguous")
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return RoleManifest(
        role=role,
        model_path=path,
        file_sha256=digest,
        layout=layout,
        identity_hash=digest[:32],
        destination_kind=DestinationKind.CONTIGUOUS_GPU_BUFFER,
        qd_range_plan=plan,
    )


def contiguous_destination(manifest):
    from comfymodal_runtime.golden.contracts import DestinationPlan
    import torch

    total = manifest.qd_range_plan.total_bytes
    return DestinationPlan(
        kind=DestinationKind.CONTIGUOUS_GPU_BUFFER,
        buffers=[torch.empty(total, dtype=torch.uint8)],
        buffer_bytes=[total],
    )


def scenario_a_qd4_mechanics(model_path: str) -> dict:
    # Inject realistic per-block source latency: physical 32 MiB preadv reads
    # take ~5-15 ms, so reads dominate and multi-worker overlap is the
    # steady state — unlike a GIL-bound instant-memcpy microbenchmark.
    from comfymodal_runtime.golden import qd_engine as _qe

    original_read = _qe._BlockReader.read_into

    def io_like_read(self, file_offset, mv, expected):
        time.sleep(0.004)
        return original_read(self, file_offset, mv, expected)

    _qe._BlockReader.read_into = io_like_read
    try:
        manifest = build_manifest(model_path, ModelRole.CLIP)
        backend = CpuCopyBackend()
        try:
            result = GoldenQD4Loader(QD4EngineConfig(), backend=backend).load(
                manifest, contiguous_destination(manifest), label="bench_a"
            )
        finally:
            backend.close()
    finally:
        _qe._BlockReader.read_into = original_read
    t = result.telemetry
    return {
        "scenario": "A_qd4_mechanics",
        "ok": result.ok,
        "configured_qd": t.configured_qd,
        "observed_max_outstanding": t.observed_max_outstanding,
        "planned_blocks": t.planned_block_count,
        "completion_count": t.completion_count,
        "bytes_total": t.bytes_total,
        "occupancy_samples": t.occupancy_samples,
        "fraction_time_at_target_qd": round(t.fraction_time_at_target_qd, 4),
        "time_below_qd_ms_by_reason": {k: round(v, 2) for k, v in t.time_below_qd_ms_by_reason.items()},
        "staging_slots": t.staging_slots,
        "pinned_bytes_bound": t.pinned_bytes,
        "aggregate_gbps_cpu_sim": round(t.aggregate_gbps, 3),
        "steady_state_gbps_cpu_sim": round(t.steady_state_gbps, 3),
        "source_latency_p50_ms": t.source_latency_p50_ms,
        "source_latency_p99_ms": t.source_latency_p99_ms,
        "first_completion_ms": round(t.first_completion_ms or 0.0, 3),
        "last_completion_ms": round(t.last_completion_ms or 0.0, 3),
        "thread_cpu_ms": t.thread_cpu_ms,
        "process_cpu_ms": t.process_cpu_ms,
    }


def scenario_b_slow_h2d_decoupling(model_path: str) -> dict:
    manifest = build_manifest(model_path, ModelRole.UNET)
    backend = CpuCopyBackend(copy_latency_s=lambda n: 0.02)
    try:
        result = GoldenQD4Loader(QD4EngineConfig(), backend=backend).load(
            manifest, contiguous_destination(manifest), label="bench_b"
        )
    finally:
        backend.close()
    t = result.telemetry
    legit = {"h2d_backpressure", "startup_ramp", "tail_drain"}
    unexplained_ms = sum(v for k, v in t.time_below_qd_ms_by_reason.items() if k not in legit)
    total_below_ms = sum(t.time_below_qd_ms_by_reason.values())
    # Same principled tolerance as the test suite: sub-interval GIL/scheduler
    # wake-up bubbles may straddle 1 ms occupancy samples; they must stay a
    # small minority of below-QD time, never a steady-state mode.
    unexplained_tolerance_ms = max(5.0, 0.10 * total_below_ms)
    return {
        "scenario": "B_slow_h2d_decoupling",
        "ok": result.ok,
        "injected_h2d_latency_ms_per_copy": 20,
        "observed_max_outstanding": t.observed_max_outstanding,
        "h2d_backpressure_events": t.h2d_backpressure_events,
        "h2d_backpressure_ms_total": round(t.h2d_backpressure_ms_total, 2),
        "free_slots_min": t.free_slots_min,
        "completed_waiting_h2d_max_depth": t.completed_waiting_h2d_max_depth,
        "unexplained_below_qd_ms": round(unexplained_ms, 2),
        "unexplained_tolerance_ms": round(unexplained_tolerance_ms, 2),
        "decoupling_proven": bool(
            result.ok
            and t.observed_max_outstanding == 4
            and t.h2d_backpressure_events >= 1
            and unexplained_ms <= unexplained_tolerance_ms
        ),
    }


def scenario_c_golden_timeline(model_path: str) -> dict:
    ledger = InMemoryLedgerSink()
    scheduler = GoldenResourceScheduler(ledger_sink=ledger)
    pipeline = GoldenPipeline(scheduler, ledger_sink=ledger, conditioning=DEFAULT_CONDITIONING_CONTRACT)
    loader = GoldenQD4Loader(QD4EngineConfig(), backend=CpuCopyBackend())

    def binding(role: ModelRole) -> RoleBinding:
        manifest = build_manifest(model_path, role)
        return RoleBinding(role=role, manifest=manifest, destination_factory=lambda: contiguous_destination(manifest))

    quiescence = assert_quiescent()
    snapshot_manifest = build_snapshot_manifest({role: build_manifest(model_path, role) for role in ModelRole})

    pipeline.begin_restore()
    pipeline.restore_ready()
    clip_result, _ = pipeline.run_role_load(ModelRole.CLIP, loader, binding(ModelRole.CLIP))
    pipeline.begin_clip_forward()
    pipeline.clip_storage_release_proof()
    prep = pipeline.unet_prepare(binding(ModelRole.UNET))
    early_commit_error = None
    try:
        pipeline.run_unet_commit(loader, binding(ModelRole.UNET))
    except Exception as exc:  # ForbiddenOverlapError expected before CLIP critical done
        early_commit_error = type(exc).__name__
    pipeline.clip_forward_complete()
    pipeline.clip_gpu_critical_done()
    unet_result, _ = pipeline.run_unet_commit(loader, binding(ModelRole.UNET))
    pipeline.sampling_started()
    pipeline.first_sampler_step_proven()
    vae_result, vae_owner = pipeline.run_vae_qd(loader, binding(ModelRole.VAE))
    demand = pipeline.vae_decode_demand()
    pipeline.complete_output()

    duplicate_read_rejected = False
    from comfymodal_runtime.golden.model_owner import GoldenModelOwner

    try:
        pipeline.registry.register(GoldenModelOwner(ModelRole.CLIP, "x"))
    except Exception:
        duplicate_read_rejected = True

    return {
        "scenario": "C_golden_timeline",
        "quiescent_at_capture": quiescence.quiescent,
        "snapshot_manifest_sha256_prefix": snapshot_manifest["manifest_sha256"][:16],
        "clip_ok": clip_result.ok,
        "unet_prepare_planned_blocks": prep["planned_blocks"],
        "early_unet_commit_blocked_by": early_commit_error,
        "unet_ok": unet_result.ok,
        "vae_ok": vae_result.ok,
        "vae_demand_decision": demand["decision"],
        "vae_demand_degraded": demand["degradation"] is not None,
        "duplicate_clip_owner_rejected": duplicate_read_rejected,
        "final_status": final_status(True, None).value,
        "degraded_status_example": final_status(True, demand["degradation"]).value if demand["degradation"] else None,
        "event_sequence": ledger.names(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    t0 = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="golden-bench-") as td:
        model_path = write_safetensors(Path(td) / "synthetic_model.safetensors", N_BLOCKS * BLOCK_BYTES)
        evidence = {
            "tool": "golden_local_benchmark",
            "note": "LOCAL SYNTHETIC EVIDENCE ONLY — no Modal throughput conclusions; "
            "physical measurement deferred to post-E40/R41 reconciliation.",
            "block_bytes": BLOCK_BYTES,
            "n_blocks": N_BLOCKS,
            "model_mib": N_BLOCKS,
            "scenarios": [
                scenario_a_qd4_mechanics(str(model_path)),
                scenario_b_slow_h2d_decoupling(str(model_path)),
                scenario_c_golden_timeline(str(model_path)),
            ],
            "wall_s": round(time.perf_counter() - t0, 2),
        }
    text = json.dumps(evidence, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
