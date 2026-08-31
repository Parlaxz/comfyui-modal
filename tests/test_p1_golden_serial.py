"""Focused offline/synthetic tests for comfymodal_runtime/golden_serial.py (P1).

These tests import ONLY the golden_serial module by file path (stdlib + torch
at module scope) and never import the full local runtime stack.  CUDA-specific
behavior is exercised through pure helpers and fakes; real-CUDA transport is
skipped when CUDA is unavailable.

Reconciled Phase 2 gate additions cover: distinct canonical workflow hash vs
expected output SHA (request setup must never conflate them), native
socket-major seeding/link resolution, PNG compression level 1, reopened
byte-count/SHA commit verification before TRUE_FIRST_DURABLE_RESULT, CLIP/VAE
pointer-identity adoption validation (float64 doubles when CUDA is absent),
single-read VAE transport, reconciled-nonzero QD throughput, fail-closed
empty/contaminated snapshot surfaces, and teardown telemetry semantics.

Reconciled-blocker additions cover: V3-like NodeOutput-shaped returns
(.result/.ui/.expand/.block_execution) normalized to socket-major cache with
exact downstream handoff and fail-closed block/expand, the exact
88 EmptySD3LatentImage -> 214 Any Switch -> 1242 sampler-dependency chain,
the dynamic-patcher preflight (legacy CoreModelPatcher rejected BEFORE
CLIP/VAE construction; CoreModelPatcher is ModelPatcherDynamic accepted),
native CLIP model_options plus a scoped meta initial-device seam (dynamic
patcher retained, state-dict copy preserving tensor data_ptrs), and explicit
VAE source dtype/device with the dynamic patcher while keeping the
one-header/one-payload no-reread proof.

Section 8c adds model-agnostic CLIP adoption scope-contract tests: the
generic helper is DISCOVERED at run time (never hard-coded) and every test
skips cleanly until the source writer exports it.  Fixtures are synthetic
CPU float64 torch.nn.Module trees (device_prefix='cpu', no CUDA required);
no Qwen paths or parameter names are encoded anywhere.
"""

from __future__ import annotations

import ast
import asyncio
import dataclasses
import hashlib
import importlib.util
import inspect
import json
import os
import struct
import sys
import threading
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "comfymodal_runtime" / "golden_serial.py"

# Reconciled Phase 2 gate contract constants (distinct by design).
CANONICAL_WORKFLOW_SHA256 = "e44389ea2eda82ba5e2328acc08307b6879ed6d4ea4b030727ab044704c0d3b5"
EXPECTED_OUTPUT_SHA256 = "8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e"


def _load_module():
    spec = importlib.util.spec_from_file_location("golden_serial_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("golden_serial_under_test", module)
    spec.loader.exec_module(module)
    return module


gs = _load_module()


# ── 1. Syntax/import + AST forbidden-project-import gate ───────────────────

ALLOWED_THIRD_PARTY = {
    "torch", "PIL", "numpy", "safetensors", "modal",
    # upstream ComfyUI modules
    "nodes", "folder_paths", "execution", "comfy", "comfy_execution",
    "comfy_api", "latent_preview", "node_helpers",
}
FORBIDDEN_ROOTS = {
    "comfymodal_runtime", "comfyapp", "modal_app", "golden",
    "timing", "profiler", "residency", "preload", "speculative",
}


def _collect_imports(tree: ast.AST):
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((alias.name, 0))
        elif isinstance(node, ast.ImportFrom):
            imports.append((node.module or "", node.level))
    return imports


def test_module_imports_cleanly_and_has_no_project_local_imports():
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(MODULE_PATH))  # syntax gate
    stdlib = set(sys.stdlib_module_names)
    for name, level in _collect_imports(tree):
        assert level == 0, f"relative import forbidden: level={level} name={name}"
        root = name.split(".")[0]
        assert root not in FORBIDDEN_ROOTS, f"forbidden project-local import: {name}"
        if root not in stdlib and root not in ALLOWED_THIRD_PARTY:
            raise AssertionError(f"import outside allowlist: {name}")


# ── 2. Required symbols + explicit top-level call order ────────────────────

REQUIRED_FUNCTIONS = [
    "golden_restore", "golden_request_setup", "golden_clip_load",
    "golden_clip_forward", "golden_unet_load", "golden_sampler_prepare",
    "golden_vae_load", "golden_sampling", "golden_sampler_tail",
    "golden_vae_decode", "golden_output", "golden_durable_commit",
    "golden_teardown", "golden_serial_execute", "golden_snapshot_content_proof",
]
REQUIRED_CLASSES = [
    "GoldenWorkflowContract", "GoldenRequest", "GoldenNodeMap",
    "GoldenTelemetryRecorder", "GoldenQDOwner", "GoldenSerialRunner",
    "PendingDurability", "GoldenFinalResult",
]


def test_required_functions_and_classes_exist():
    for name in REQUIRED_FUNCTIONS:
        fn = getattr(gs, name, None)
        assert callable(fn), name
        assert inspect_is_async(fn) == (name != "golden_snapshot_content_proof"), name
    for name in REQUIRED_CLASSES:
        assert hasattr(gs, name), name


def inspect_is_async(fn) -> bool:
    import inspect

    return inspect.iscoroutinefunction(fn)


def _walk_statements_in_order(body):
    for stmt in body:
        yield stmt
        for child_type in (ast.Try, ast.With, ast.AsyncWith, ast.If):
            if isinstance(stmt, child_type):
                for field_name in ("body", "handlers", "orelse", "finalbody"):
                    items = getattr(stmt, field_name, None)
                    if not items:
                        continue
                    if field_name == "handlers":
                        for handler in items:
                            yield from _walk_statements_in_order(handler.body)
                    else:
                        yield from _walk_statements_in_order(items)


def test_golden_serial_execute_calls_stages_in_exact_order():
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(
        node for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "golden_serial_execute"
    )
    calls = []
    for stmt in _walk_statements_in_order(fn.body):
        value = stmt.value if isinstance(stmt, ast.Expr) else None
        if isinstance(value, ast.Await):
            value = value.value
        if isinstance(value, ast.Call):
            func = value.func
            if isinstance(func, ast.Name) and func.id.startswith("golden_"):
                calls.append(func.id)
            elif isinstance(func, ast.Attribute) and func.attr == "mark_true_durable":
                calls.append("mark_true_durable")
    expected = list(gs.STAGE_ORDER) + ["mark_true_durable"]
    # teardown is called in finally after everything else
    assert calls[: len(expected)] == expected, calls
    assert calls[-1] == "golden_teardown", calls


def test_each_stage_marks_entry_once_and_end_ready_once():
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for stage in gs.STAGE_ORDER:
        node = functions[stage]
        begins = ends = 0
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                func = sub.func
                if isinstance(func, ast.Attribute) and func.attr == "begin_stage":
                    begins += 1
                if isinstance(func, ast.Attribute) and func.attr == "end_stage":
                    ends += 1
        assert begins == 1, stage
        assert ends == 1, stage


def test_teardown_excludes_broad_cleanup_calls():
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "golden_teardown"
    )
    forbidden_attrs = {"collect", "empty_cache", "unload_all_models", "purge_allocator",
                       "empty_cuda_cache", "release_storage"}
    for sub in ast.walk(fn):
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
            assert sub.func.attr not in forbidden_attrs, sub.func.attr


# ── 3. Telemetry names + seriality reconciliation ──────────────────────────


def test_telemetry_intervals_and_seriality_reconciliation():
    rec = gs.GoldenTelemetryRecorder()
    rec.begin_stage("golden_restore")
    rec.end_stage("golden_restore", ready=True)
    rec.begin_stage("golden_request_setup")
    rec.end_stage("golden_request_setup", ready=True)
    result = rec.reconcile_seriality()
    assert result["ok"] is True and result["count"] == 0
    intervals = rec.intervals
    assert intervals["golden_restore"].end_monotonic_ns <= intervals["golden_request_setup"].entry_monotonic_ns


def test_telemetry_detects_overlap_violation():
    class FakeClock:
        def __init__(self):
            self.value = 100

        def tick(self):
            self.value += 1
            return self.value

    clock = FakeClock()
    rec = gs.GoldenTelemetryRecorder(monotonic=clock.tick, wall=clock.tick)
    rec.begin_stage("golden_restore")
    rec.end_stage("golden_restore")
    # Force the next stage's ENTRY before the previous END (overlap).
    rec._intervals["golden_request_setup"] = gs.GoldenStageInterval(
        name="golden_request_setup",
        entry_monotonic_ns=rec.intervals["golden_restore"].entry_monotonic_ns,
        entry_wall_ns=0,
        end_monotonic_ns=rec.intervals["golden_restore"].end_monotonic_ns + 10,
        end_wall_ns=0,
        ok=True,
    )
    result = rec.reconcile_seriality()
    assert result["ok"] is False and result["count"] == 1
    assert "ENTRY" in result["violations"][0]


def test_telemetry_rejects_overlapping_open_stage_and_duplicate_entry():
    rec = gs.GoldenTelemetryRecorder()
    rec.begin_stage("golden_restore")
    with pytest.raises(RuntimeError, match="overlap"):
        rec.begin_stage("golden_request_setup")
    rec.end_stage("golden_restore")
    with pytest.raises(RuntimeError, match="duplicate"):
        rec.begin_stage("golden_restore")


def test_ra8_timing_aggregation_marks_overlap_and_keeps_stage_wall_separate():
    result = gs.aggregate_timing_intervals(
        [{"start_ns": 0, "end_ns": 10}, {"start_ns": 5, "end_ns": 20}],
        enclosing_start_ns=0,
        enclosing_end_ns=30,
    )
    assert result["sum_ns"] == 25
    assert result["union_ns"] == 20
    assert result["overlap_ns"] == 5
    assert result["wall_ns"] == 30
    assert result["residual_ns"] == 10
    assert result["non_additive"] is True


def test_ra8_vae_decomposition_and_page_fault_schema_are_offline():
    stats = {
        "role": "vae",
        "bytes_read": 128,
        "effective_source_gbps": 1.25,
        "effective_h2d_gbps": 2.5,
        "source_open_header_layout": {"header_layout_ns": 3},
        "staging": {"allocated_bytes": 64, "reuse_count": 2, "retained_bytes": 64},
        "source_reads": {"bytes": 128},
        "cpu_to_pinned_staging": {"bytes": 128},
        "h2d_enqueue": {"bytes": 128},
        "h2d_gpu_event": {"duration_ns": 51},
        "waits_quiescence": {"workers_joined": True},
    }
    faults = gs.page_fault_delta(
        {"minor_faults": 10, "major_faults": 2, "source": "test"},
        {"minor_faults": 17, "major_faults": 3, "source": "test"},
    )
    assert faults == {
        "available": True,
        "minor_delta": 7,
        "major_delta": 1,
        "minor_page_faults_delta": 7,
        "major_page_faults_delta": 1,
        "supporting_evidence_only": True,
        "source": "test",
    }
    result = gs.build_vae_load_decomposition(
        stage_start_ns=0,
        stage_end_ns=100,
        components=[{"name": "qd_transport", "start_ns": 0, "end_ns": 80}],
        transport_stats=stats,
        memory_before={"host": {"available": False}},
    )
    assert result["schema"] == "vae_load_decomposition_v1"
    assert result["clock"] == "perf_counter_ns"
    assert result["stage_wall_ns"] == 100
    assert result["transport"]["schema"] == "golden_qd_transport_diagnostics_v1"
    assert result["transport"]["source_bytes"] == 128
    assert result["transport"]["throughput"] == {
        "source_gbps": 1.25,
        "h2d_gbps": 2.5,
        "h2d_scope": "sum_of_copy_event_durations",
    }
    assert result["overlap"]["do_not_sum_components_for_stage_wall"] is True


def test_telemetry_persists_complete_json_atomically(tmp_path):
    rec = gs.GoldenTelemetryRecorder()
    rec.begin_stage("golden_restore")
    rec.end_stage("golden_restore", ready=True)
    rec.event("clip_qd_owner_created", role="clip")
    target = tmp_path / "telemetry.json"
    rec.persist(str(target))
    document = json.loads(target.read_text(encoding="utf-8"))
    assert document["schema"] == "golden_p1_telemetry_v1"
    assert {s["name"] for s in document["stages"]} == {"golden_restore"}
    assert document["events"][0]["name"] == "clip_qd_owner_created"
    assert document["seriality"]["ok"] is True
    assert document["telemetry_persistence"] == {"telemetry_persisted": True}
    leftovers = [p for p in os.listdir(tmp_path) if p.endswith(".tmp")]
    assert leftovers == []


def test_true_durable_requires_successful_commit_stage(tmp_path):
    pending = _write_pending(tmp_path)
    pending.committed = True
    rec = gs.GoldenTelemetryRecorder()
    with pytest.raises(RuntimeError, match="true_durable_requires"):
        rec.mark_true_durable()
    rec.begin_stage("golden_durable_commit")
    rec.end_stage("golden_durable_commit", ready=True)
    # TRUE_FIRST_DURABLE_RESULT requires the typed proof returned by the
    # post-commit reopen/stat/read/hash verification.
    rec.mark_reopen_verified(
        gs.verify_committed_object(pending, expected_sha256=pending.sha256)
    )
    rec.mark_true_durable()
    with pytest.raises(RuntimeError, match="already_marked"):
        rec.mark_true_durable()


# ── 4. QD block planning / coverage / safe offsets ─────────────────────────


def test_plan_source_regions_exact_coverage_qd4_block32():
    total = 32 * 1024 * 1024 * 10 + 12345  # 10 full blocks + tail
    regions = gs.plan_source_regions(8, total, 32 * 1024 * 1024, 4)
    assert len(regions) == 4
    items = [item for region in regions for item in region]
    ok, reason = gs.partition_coverage(
        [(off - 8, off - 8 + ln) for off, ln in items], total
    )
    assert ok, reason
    # deterministic static partition: contiguous per-worker forward-only runs
    for region in regions:
        offsets = [off for off, _ in region]
        assert offsets == sorted(offsets)


def test_partition_coverage_rejects_gaps_duplicates_and_missing_tail():
    assert gs.partition_coverage([(0, 5), (5, 10)], 10)[0] is True
    assert gs.partition_coverage([(0, 5), (6, 10)], 10)[0] is False   # gap
    assert gs.partition_coverage([(0, 6), (5, 10)], 10)[0] is False   # overlap/duplicate
    assert gs.partition_coverage([(0, 5)], 10)[0] is False            # missing tail
    assert gs.partition_coverage([], 0)[0] is True


def test_parse_safetensors_header_validates_offsets_dtype_shape_sizes(tmp_path):
    import struct

    header = {
        "w": {"dtype": "BF16", "shape": [2, 3], "data_offsets": [0, 12]},
        "__metadata__": {"format": "pt"},
    }
    hb = json.dumps(header).encode("utf-8")
    data = b"\x01" * 12
    good = tmp_path / "good.safetensors"
    good.write_bytes(struct.pack("<Q", len(hb)) + hb + data)
    parsed = gs.parse_safetensors_header(str(good))
    assert parsed["status"] == "ok"
    assert parsed["data_start"] == 8 + len(hb)
    assert parsed["total_data_bytes"] == 12

    bad_cases = {
        "truncated": b"\x00\x00",
        "bad_len": struct.pack("<Q", 999) + b"x",
        "size_mismatch": (lambda h: struct.pack("<Q", len(h)) + h + b"\x00" * 11)(
            json.dumps({"w": {"dtype": "BF16", "shape": [2, 3], "data_offsets": [0, 12]}}).encode()
        ),
        "bad_offset": (
            lambda h: struct.pack("<Q", len(h)) + h + b"\x00" * 24
        )(
            json.dumps({"w": {"dtype": "F32", "shape": [2], "data_offsets": [4, 12]}}).encode()
        ),
        "unsupported_dtype": (
            lambda h: struct.pack("<Q", len(h)) + h + b"\x00" * 4
        )(
            json.dumps({"w": {"dtype": "F8_E4M3", "shape": [1], "data_offsets": [0, 4]}}).encode()
        ),
        "non_contiguous": (
            lambda h: struct.pack("<Q", len(h)) + h + b"\x00" * 16
        )(
            json.dumps({
                "a": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]},
                "b": {"dtype": "F32", "shape": [1], "data_offsets": [8, 12]},
            }).encode()
        ),
    }
    for name, payload in bad_cases.items():
        p = tmp_path / f"{name}.safetensors"
        p.write_bytes(payload)
        parsed = gs.parse_safetensors_header(str(p))
        assert parsed["status"] == "error", name


# ── 5. Transport fail-closed paths (pure validators + CPU-safe pieces) ──────


def _planned_items():
    return [(0, 4), (4, 4)]


def _good_records():
    return [
        {"worker_id": 0, "off": 0, "planned_len": 4, "read_len": 4,
         "h2d_submitted_bytes": 4, "h2d_completed_bytes": 4},
        {"worker_id": 1, "off": 4, "planned_len": 4, "read_len": 4,
         "h2d_submitted_bytes": 4, "h2d_completed_bytes": 4},
    ]


def test_validate_transport_records_accepts_exact_run():
    ok, reason = gs.validate_transport_records(_good_records(), _planned_items(), 0, 8)
    assert ok, reason


def test_short_read_fails_closed():
    records = _good_records()
    records[1]["read_len"] = 2
    ok, reason = gs.validate_transport_records(records, _planned_items(), 0, 8)
    assert not ok and reason == "read_bytes_reconciliation"


def test_partial_h2d_fails_closed():
    records = _good_records()
    records[0]["h2d_completed_bytes"] = 0
    ok, reason = gs.validate_transport_records(records, _planned_items(), 0, 8)
    assert not ok and reason == "h2d_completed_reconciliation"


def test_duplicate_or_missing_region_fails_closed():
    records = _good_records() + [_good_records()[0]]
    ok, _ = gs.validate_transport_records(records, _planned_items(), 0, 8)
    assert not ok
    ok, _ = gs.validate_transport_records(_good_records()[:1], _planned_items(), 0, 8)
    assert not ok


def test_view_alignment_math_fail_closed():
    gs.check_view_alignment(0, 12, 2, [2, 3])
    with pytest.raises(RuntimeError, match="misaligned_offset"):
        gs.check_view_alignment(1, 12, 2, [6])
    with pytest.raises(RuntimeError, match="misaligned_length"):
        gs.check_view_alignment(0, 13, 2, [6])
    with pytest.raises(RuntimeError, match="length_mismatch"):
        gs.check_view_alignment(0, 10, 2, [6])


def test_zero_copy_view_requires_cuda_destination():
    buf = torch = __import__("torch").zeros(16, dtype=__import__("torch").uint8)
    with pytest.raises(RuntimeError, match="non_cuda_destination"):
        gs.make_zero_copy_view(buf, __import__("torch").float16, [4], 0, 8)


@pytest.mark.skipif(not __import__("torch").cuda.is_available(), reason="CUDA unavailable")
def test_real_qd_transport_roundtrip_synthetic_file():
    """Full physical transport on a synthetic safetensors file.  The payload is
    large enough that the reconciled throughput survives the production
    ``round(gbps, 4)`` quantization (a tiny file can round to 0.0 GB/s)."""
    import struct

    import torch

    n_floats = 1024 * 1024  # 4 MiB of F32 payload
    header = {
        "a": {"dtype": "F32", "shape": [n_floats], "data_offsets": [0, 4 * n_floats]},
        "b": {"dtype": "U8", "shape": [4], "data_offsets": [4 * n_floats, 4 * n_floats + 4]},
    }
    hb = json.dumps(header).encode("utf-8")
    payload = (bytes(range(256)) * ((4 * n_floats) // 256 + 1))[: 4 * n_floats] + b"abcd"
    path = Path(__import__("tempfile").gettempdir()) / "golden_qd_roundtrip.safetensors"
    path.write_bytes(struct.pack("<Q", len(hb)) + hb + payload)

    result = gs.read_file_qd_gpu(
        str(path), role="test", qd=2, block_bytes=1024 * 1024, diagnostics=True
    )
    try:
        sd = result["sd"]
        # Compare transport bytes, not float equality: the synthetic bit
        # pattern intentionally includes NaNs, which are unequal to themselves.
        actual_a = sd["a"].view(torch.uint8).cpu().numpy().tobytes()
        assert actual_a == payload[: 4 * n_floats]
        assert bytes(sd["b"].cpu().numpy()) == b"abcd"
        stats = result["stats"]
        assert stats["fallback"] == {"pin_fallback": 0, "alignment_tensor_count": 0}
        assert stats["bytes_read"] == len(payload)
        assert stats["record_reconciliation"]["ok"] is True
        assert stats["qd_source_gbps"] > 0  # throughput from reconciled nonzero bytes
        owner = result["owner"]
        assert owner.closed is False
        owner.close()
        owner.close()  # idempotent
        assert owner.closed is True
    finally:
        result["owner"].close()


# ── 6. Owner lifetime / idempotent close ───────────────────────────────────


def test_owner_lifetime_and_idempotent_close():
    owner = gs.GoldenQDOwner(gpu_buf=object(), slots=[object(), object()], device="cuda:0", role="unet")
    staging = owner.slots
    assert owner.closed is False
    owner.release_staging()
    assert owner.slots == [] and owner.closed is False
    owner.close()
    assert owner.closed is True
    owner.close()
    assert owner.closed is True
    assert staging  # original slot list was captured before release


# ── 7. No invisible fallback / no duplicate counters ───────────────────────


def test_stats_structurally_forbid_fallback_counters():
    # The transport's fallback dict is a fixed zero structure; verify the
    # source declares it as constant zeros (no code path can increment it).
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert '"pin_fallback": 0' in source
    assert '"alignment_tensor_count": 0' in source
    assert "alignment_extra_source_bytes" not in source  # historical fallback removed
    assert "_fallback_aligned_tensor_from_gpu" not in source


def test_single_source_read_counter_semantics():
    # One planned block list -> exactly one record per block; validator fails
    # on any duplicate, so double-reads cannot reconcile.
    records = _good_records()
    records.append(dict(records[0]))
    ok, reason = gs.validate_transport_records(records, _planned_items(), 0, 8)
    assert not ok and reason.startswith("block_count_or_identity")


# ── 8. UNET strict 453/453 pointer-identity validator with fakes └──────────


class _FakeModule:
    def __init__(self, tensors: dict):
        self._tensors = tensors

    def named_parameters(self):
        return list(self._tensors.items())

    def named_buffers(self):
        return []


def _build_fake_binding(count=453, copy_one=False, wrong_count=None):
    import torch

    n_expected = wrong_count if wrong_count is not None else count
    flat = torch.zeros(4096, dtype=torch.uint8)
    views = {}
    named = {}
    offset = 0
    for i in range(n_expected):
        view = flat[offset : offset + 8].view(torch.float32).view([2])
        views[f"layer.{i}.weight"] = view
        tensor = flat[offset : offset + 8].view(torch.float32).view([2])
        if copy_one and i == 0:
            tensor = tensor.clone()
        named[f"layer.{i}.weight"] = tensor
        offset += 8
    model = type("M", (), {})()
    model.diffusion_model = _FakeModule(named)
    return model, views


_CPU_FAKE_KW = {"expected_count": 453, "expected_dtype": __import__("torch").float32, "device_prefix": "cpu"}


def test_unet_validator_accepts_453_shared_storage_cpu_fake():
    model, views = _build_fake_binding()
    identity = gs.validate_unet_binding(model, views, **_CPU_FAKE_KW)
    assert identity["tensor_count"] == 453
    assert identity["same_storage_count"] == 453
    assert identity["copied_storage_count"] == 0


def test_unet_validator_rejects_wrong_count_copied_missing_leftover():
    model, views = _build_fake_binding(wrong_count=452)
    with pytest.raises(RuntimeError, match="unet_tensor_count"):
        gs.validate_unet_binding(model, views, **_CPU_FAKE_KW)

    model, views = _build_fake_binding(copy_one=True)
    with pytest.raises(RuntimeError, match="bind_copied_storage"):
        gs.validate_unet_binding(model, views, **_CPU_FAKE_KW)

    model, views = _build_fake_binding()
    del views["layer.7.weight"]  # model tensor with no QD view -> leftover
    with pytest.raises(RuntimeError, match="bind_leftover"):
        gs.validate_unet_binding(model, views, **_CPU_FAKE_KW)

    model, views = _build_fake_binding()
    views["extra.key"] = views["layer.0.weight"]  # view with no model tensor -> missing
    with pytest.raises(RuntimeError, match="bind_missing"):
        gs.validate_unet_binding(model, views, **_CPU_FAKE_KW)


def test_unet_validator_rejects_non_cuda_device_in_production_mode():
    model, views = _build_fake_binding()
    with pytest.raises(RuntimeError, match="bind_device"):
        gs.validate_unet_binding(
            model, views, expected_count=453,
            expected_dtype=__import__("torch").float32, device_prefix="cuda",
        )


# ── 8b. CLIP/VAE strict pointer-identity adoption via validate_qd_adoption ──


def _build_double_binding(count=5, copy_index=None):
    """CPU fake module binding using float64 doubles (CUDA unavailable
    offline); module tensors share storage with their QD views unless copied."""
    import torch

    flat = torch.zeros(count * 16, dtype=torch.uint8)
    views, named = {}, {}
    for i in range(count):
        # 16 bytes -> two float64 elements per entry
        view = flat[i * 16 : i * 16 + 16].view(torch.float64).view([2])
        tensor = flat[i * 16 : i * 16 + 16].view(torch.float64).view([2])
        if copy_index == i:
            tensor = tensor.clone()
        views[f"blk.{i}.w"] = view
        named[f"blk.{i}.w"] = tensor
    return _FakeModule(named), views


@pytest.mark.parametrize("role", ["clip", "vae"])
def test_role_validator_accepts_shared_storage_double_fake(role):
    module, views = _build_double_binding()
    identity = gs.validate_qd_adoption(role, [module], views, device_prefix="cpu")
    assert identity["tensor_count"] == 5
    assert identity["matched_count"] == 5
    assert identity["same_storage_count"] == 5
    assert identity["copied_storage_count"] == 0


@pytest.mark.parametrize("role", ["clip", "vae"])
def test_role_validator_rejects_copied_missing_extra_device_dtype_and_alias(role):
    import torch

    # copied data pointer: live pointer absent from the view-pointer set
    module, views = _build_double_binding(copy_index=2)
    with pytest.raises(RuntimeError, match="adoption_coverage_mismatch"):
        gs.validate_qd_adoption(role, [module], views, device_prefix="cpu")

    # model key with no QD view (exact coverage violated)
    module, views = _build_double_binding()
    del views["blk.3.w"]
    with pytest.raises(RuntimeError, match="adoption_coverage_mismatch"):
        gs.validate_qd_adoption(role, [module], views, device_prefix="cpu")

    # leftover view with no model tensor (distinct storage so it is an
    # unused-view coverage failure, not a duplicate alias)
    module, views = _build_double_binding()
    views["surprise.key"] = torch.zeros(16, dtype=torch.uint8).view(torch.float64).view([2])
    with pytest.raises(RuntimeError, match="adoption_coverage_mismatch"):
        gs.validate_qd_adoption(role, [module], views, device_prefix="cpu")

    # duplicate alias on the view side: two views, one data pointer
    module, views = _build_double_binding()
    views["alias.key"] = views["blk.0.w"]
    with pytest.raises(RuntimeError, match="adoption_view_duplicate_alias"):
        gs.validate_qd_adoption(role, [module], views, device_prefix="cpu")

    # duplicate alias on the live side: two model tensors, one data pointer
    module, views = _build_double_binding()
    module._tensors["dup.key"] = module._tensors["blk.0.w"]
    with pytest.raises(RuntimeError, match="adoption_live_duplicate_alias"):
        gs.validate_qd_adoption(role, [module], views, device_prefix="cpu")

    # wrong dtype at the SAME data pointer and shape: recast away from the
    # double view dtype without moving storage (both views start at ptr 0)
    flat = torch.zeros(16, dtype=torch.uint8)
    recast_module = _FakeModule({"only.w": flat[:8].view(torch.float32).view([2])})
    with pytest.raises(RuntimeError, match="adoption_dtype"):
        gs.validate_qd_adoption(
            role, [recast_module], {"only.w": flat.view(torch.float64).view([2])},
            device_prefix="cpu",
        )

    # wrong device prefix in production mode (cpu fakes vs required cuda)
    module, views = _build_double_binding()
    with pytest.raises(RuntimeError, match="adoption_device"):
        gs.validate_qd_adoption(role, [module], views, device_prefix="cuda")


# ── 8c. Model-agnostic generic CLIP adoption scope contract ────────────────
#
# Contract tests for the NEW generic (model-agnostic) CLIP adoption helper.
# The source writer lands this concurrently, so the helper is DISCOVERED at
# run time by export name/pattern instead of being hard-coded, and every test
# below skips cleanly until it is exported.  The generic contract pinned here:
#
#   1. A direct CLIP module whose full tensor set exactly matches all QD
#      views succeeds.
#   2. A nested wrapper chain whose deepest checkpoint module exactly matches
#      all QD views succeeds even when an outer wrapper carries one small
#      constructor-owned scalar; the SELECTED scope must be the deepest
#      matching module and telemetry must account for the scalar.
#   3. Differently named / multi-layer wrappers with several small extras
#      within generic limits succeed (proving no model-specific hardcoding).
#   4. Missing QD view, copied live tensor, unused extra QD view, duplicate
#      QD pointer, and duplicate live alias all fail.
#   5. Model-sized outer extras and too-many outer extras fail the bounded
#      policy.
#   6. Two disjoint candidate modules each holding the complete QD pointer
#      set fail as ambiguous; a normal parent/child candidate chain succeeds.
#   7. The existing deployment-shaped composition appears only as ONE
#      example — never as the validator's definition.
#
# All fixtures are small CPU float64 doubles via device_prefix='cpu'; no CUDA
# is required.  No Qwen paths or parameter names appear anywhere.

import torch as _torch  # sanctioned at module scope (see module docstring)

_GENERIC_HELPER_CANDIDATES = (
    "validate_generic_clip_adoption",
    "validate_clip_scope_adoption",
    "generic_clip_adoption",
    "clip_scope_adoption",
    "find_clip_adoption_scope",
    "select_clip_adoption_scope",
    "resolve_clip_adoption_scope",
    "adopt_clip_generic",
    "validate_qd_adoption_scoped",
    "select_adoption_scope",
    "select_and_validate_qd_adoption_scope",
)


def _resolve_generic_clip_helper():
    """Discover the exported generic CLIP adoption helper without hard-coding
    a single API: explicit plausible names first, then a pattern scan over the
    module exports (adoption + scope/generic/clip qualifier).  Skips while the
    source landing is still in flight."""
    for name in _GENERIC_HELPER_CANDIDATES:
        fn = getattr(gs, name, None)
        if callable(fn):
            return name, fn
    import re

    adoption = re.compile(r"adopt", re.IGNORECASE)
    qualifier = re.compile(r"clip|generic|scope|deepest|candidate|select", re.IGNORECASE)
    hits = []
    for name in getattr(gs, "__all__", ()):
        if name == "validate_qd_adoption":
            continue  # strict exact-coverage validator pinned by section 8b
        if adoption.search(name) and qualifier.search(name):
            fn = getattr(gs, name, None)
            if callable(fn):
                hits.append((name, fn))
    if len(hits) == 1:
        return hits[0]
    pytest.skip(
        "generic model-agnostic CLIP adoption helper not yet exported from "
        f"golden_serial (source landing in flight); pattern-scan candidates: "
        f"{[n for n, _ in hits] or 'none'}"
    )


def _call_generic_clip_helper(root, views):
    """Invoke the discovered helper by mapping (module tree, QD views,
    device_prefix='cpu') onto whatever parameter names it chose, via signature
    inspection.  Plural/collection parameter names receive [root]."""
    name, fn = _resolve_generic_clip_helper()
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):  # pragma: no cover - builtins only
        params = {}
    kwargs = {}
    module_bound = views_bound = False
    for pname in params:
        low = pname.lower()
        if not module_bound and any(
            token in low
            for token in ("module", "model", "root", "tree", "candidat", "target", "holder")
        ):
            kwargs[pname] = (
                [root] if any(token in low for token in ("modules", "candidates", "models")) else root
            )
            module_bound = True
        elif not views_bound and any(
            token in low for token in ("view", "sd", "state_dict", "statedict", "qd", "weights")
        ):
            kwargs[pname] = views
            views_bound = True
        elif low == "device_prefix":
            kwargs[pname] = "cpu"
        elif low == "tag":
            kwargs[pname] = "clip"
    if not (module_bound and views_bound):
        raise AssertionError(
            f"generic CLIP adoption helper `{name}` has an unmappable signature: "
            f"{list(params)}; expected one module-tree parameter and one QD "
            "views parameter"
        )
    return fn(**kwargs)


class _AdoptLeaf(_torch.nn.Module):
    def __init__(self, tensors):
        super().__init__()
        # torch forbids '.' inside registered parameter names, so live
        # registration uses flat valid names (p_0, p_1, ...) while the QD
        # views keep their arbitrary/dotted keys.  The production proof is
        # pure data-pointer identity, so registration names never matter.
        for index, tensor in enumerate(tensors.values()):
            self.register_parameter(
                f"p_{index}", _torch.nn.Parameter(tensor, requires_grad=False)
            )


class _AdoptWrapper(_torch.nn.Module):
    """Generic container: named children plus optional constructor-owned extra
    parameters that no QD view backs."""

    def __init__(self, children):
        super().__init__()
        for attr_name, child in children.items():
            setattr(self, attr_name, child)

    def with_extra(self, name, tensor):
        self.register_parameter(name, _torch.nn.Parameter(tensor, requires_grad=False))
        return self


def _scalar_extra():
    # A tiny constructor-owned scalar on fresh storage (never a QD view):
    # 16 bytes = two float64 elements.
    return _torch.zeros(16, dtype=_torch.uint8).view(_torch.float64).view([2])


def _build_adopt_tree(cls_name, count=4, copy_index=None, flat=None):
    """A uniquely-named leaf module plus matching QD views carved from ONE cpu
    uint8 buffer, so live tensors share storage with views unless copied."""
    if flat is None:
        flat = _torch.zeros(count * 16, dtype=_torch.uint8)
    views, named = {}, {}
    for i in range(count):
        seg = flat[i * 16 : (i + 1) * 16]
        views[f"blk.{i}.weight"] = seg.view(_torch.float64).view([2])
        tensor = seg.view(_torch.float64).view([2])
        if copy_index == i:
            tensor = tensor.clone()
        named[f"blk.{i}.weight"] = tensor
    cls = type(cls_name, (_AdoptLeaf,), {})
    return cls(named), views, flat


def _normalize_telemetry(raw):
    if isinstance(raw, tuple):
        for item in reversed(raw):
            if isinstance(item, dict):
                return item
    return raw


def _flatten_telemetry(obj, prefix=""):
    items = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            items.append((path, value))
            items.extend(_flatten_telemetry(value, path))
    elif isinstance(obj, (list, tuple)):
        for index, value in enumerate(obj):
            path = f"{prefix}[{index}]"
            items.append((path, value))
            items.extend(_flatten_telemetry(value, path))
    return items


def _assert_matched_count(raw, expected):
    result = _normalize_telemetry(raw)
    flat = _flatten_telemetry(result)
    hits = [
        key
        for key, value in flat
        if isinstance(value, int)
        and not isinstance(value, bool)
        and value == expected
        and any(token in key.lower() for token in ("matched", "tensor", "adopted", "coverage"))
    ]
    assert hits, (
        f"telemetry does not report a matched/adopted tensor count of {expected}; "
        f"flattened telemetry: {flat}"
    )


def _assert_extra_accounting(raw, expected):
    result = _normalize_telemetry(raw)
    flat = _flatten_telemetry(result)
    hits = [
        key
        for key, value in flat
        if "extra" in key.lower()
        and (
            (isinstance(value, int) and not isinstance(value, bool) and value == expected)
            or (isinstance(value, (list, tuple)) and len(value) == expected)
        )
    ]
    assert hits, (
        f"telemetry does not account for {expected} constructor-owned extra "
        f"tensor(s) under an 'extra'-keyed field; flattened telemetry: {flat}"
    )


def _assert_scope_identifies(raw, *tokens):
    result = _normalize_telemetry(raw)
    texts = [str(value) for _key, value in _flatten_telemetry(result)]
    assert any(token in text for token in tokens for text in texts), (
        f"telemetry does not identify the selected adoption scope by any of "
        f"{tokens}; strings seen: {texts}"
    )


def test_generic_clip_direct_module_exact_match_succeeds():
    _resolve_generic_clip_helper()  # skip cleanly until the source lands
    leaf, views, _flat = _build_adopt_tree("_DirectExactLeaf", count=4)
    result = _call_generic_clip_helper(leaf, views)
    _assert_matched_count(result, 4)


def test_generic_clip_nested_wrapper_selects_deepest_and_accounts_scalar():
    _resolve_generic_clip_helper()
    leaf, views, _flat = _build_adopt_tree("_DeepCheckpointLeaf", count=4)
    wrapper = _AdoptWrapper({"checkpoint_core": leaf}).with_extra(
        "gate_scalar", _scalar_extra()
    )
    result = _call_generic_clip_helper(wrapper, views)
    # matched set == exactly the deepest module's tensors (scalar excluded)
    _assert_matched_count(result, 4)
    # telemetry accounts for the one outer constructor-owned scalar
    _assert_extra_accounting(result, 1)
    # the selected scope must be identified as the DEEPEST matching module
    _assert_scope_identifies(result, "checkpoint_core", "_DeepCheckpointLeaf")


def test_generic_clip_differently_named_multilayer_extras_within_limits_succeeds():
    _resolve_generic_clip_helper()
    leaf, views, _flat = _build_adopt_tree("_StackCoreLeaf", count=6)
    mid = _AdoptWrapper({"inner_stack": leaf}).with_extra("rot_const", _scalar_extra())
    top = _AdoptWrapper({"backbone_holder": mid})
    top.with_extra("aux_scale", _scalar_extra()).with_extra("bias_zero", _scalar_extra())
    result = _call_generic_clip_helper(top, views)
    _assert_matched_count(result, 6)
    _assert_extra_accounting(result, 3)


def test_generic_clip_rejects_missing_qd_view():
    _resolve_generic_clip_helper()
    leaf, views, _flat = _build_adopt_tree("_MissingViewLeaf", count=8)
    del views["blk.2.weight"]  # live weight loses its QD view
    with pytest.raises(RuntimeError):
        _call_generic_clip_helper(leaf, views)


def test_generic_clip_rejects_copied_live_weight():
    _resolve_generic_clip_helper()
    # a cloned MODEL weight is model-sized residue: no scope matches exactly
    # and the bounded policy must never absorb it as a small extra
    leaf, views, _flat = _build_adopt_tree("_CopiedWeightLeaf", count=8, copy_index=1)
    with pytest.raises(RuntimeError):
        _call_generic_clip_helper(leaf, views)


def test_generic_clip_rejects_unused_extra_qd_view():
    _resolve_generic_clip_helper()
    leaf, views, _flat = _build_adopt_tree("_UnusedViewLeaf", count=4)
    views["surprise.weight"] = (
        _torch.zeros(16, dtype=_torch.uint8).view(_torch.float64).view([2])
    )
    with pytest.raises(RuntimeError):
        _call_generic_clip_helper(leaf, views)


def test_generic_clip_rejects_duplicate_qd_pointer():
    _resolve_generic_clip_helper()
    leaf, views, _flat = _build_adopt_tree("_DupViewLeaf", count=4)
    views["alias.weight"] = views["blk.0.weight"]  # two views, one storage
    with pytest.raises(RuntimeError):
        _call_generic_clip_helper(leaf, views)


def test_generic_clip_rejects_duplicate_live_alias():
    _resolve_generic_clip_helper()
    leaf, views, _flat = _build_adopt_tree("_DupLiveLeaf", count=4)
    # Two DISTINCT live Parameter objects sharing ONE data pointer.  (Register
    # the identical object twice would be silently deduped by torch's
    # named_parameters(), so the alias must be a fresh Parameter over the
    # same storage to reach the production pointer-identity check.)
    leaf.register_parameter(
        "dup_alias",
        _torch.nn.Parameter(leaf._parameters["p_0"].data, requires_grad=False),
    )
    with pytest.raises(RuntimeError):
        _call_generic_clip_helper(leaf, views)


def test_generic_clip_bounded_policy_rejects_model_sized_outer_extra():
    _resolve_generic_clip_helper()
    leaf, views, _flat = _build_adopt_tree("_BigExtraLeaf", count=4)
    wrapper = _AdoptWrapper({"checkpoint_core": leaf})
    # A single weight-like blob far beyond the production outer-extra byte
    # budget (4096 bytes) — orders of magnitude above any scalar extra and
    # never a tolerable constructor-owned residue.
    oversized = _torch.zeros(8192, dtype=_torch.uint8).view(_torch.float64).view([1024])
    wrapper.with_extra("oversized_aux", oversized)
    with pytest.raises(RuntimeError):
        _call_generic_clip_helper(wrapper, views)


def test_generic_clip_bounded_policy_rejects_too_many_outer_extras():
    _resolve_generic_clip_helper()
    leaf, views, _flat = _build_adopt_tree("_ManyExtrasLeaf", count=4)
    wrapper = _AdoptWrapper({"checkpoint_core": leaf})
    for i in range(32):  # far beyond any reasonable generic count bound
        wrapper.with_extra(f"tiny_aux_{i}", _scalar_extra())
    with pytest.raises(RuntimeError):
        _call_generic_clip_helper(wrapper, views)


def test_generic_clip_disjoint_complete_candidates_fail_ambiguous():
    _resolve_generic_clip_helper()
    leaf_a, views, flat = _build_adopt_tree("_LeftBranchLeaf", count=4)
    leaf_b, _v2, _f2 = _build_adopt_tree("_RightBranchLeaf", count=4, flat=flat)
    root = _AdoptWrapper({"left_branch": leaf_a, "right_branch": leaf_b})
    # both disjoint candidates hold the COMPLETE QD pointer set -> ambiguous
    with pytest.raises(RuntimeError):
        _call_generic_clip_helper(root, views)


def test_generic_clip_parent_child_candidate_chain_succeeds_deepest():
    _resolve_generic_clip_helper()
    leaf, views, _flat = _build_adopt_tree("_ChainCoreLeaf", count=4)
    mid = _AdoptWrapper({"chain_core": leaf})  # adds nothing of its own
    root = _AdoptWrapper({"mid_holder": mid})
    result = _call_generic_clip_helper(root, views)
    _assert_matched_count(result, 4)
    # nested candidates disambiguate by containment: deepest wins
    _assert_scope_identifies(result, "chain_core", "_ChainCoreLeaf")


def test_generic_clip_realworld_shaped_example_succeeds():
    """ONE example composed like the deployed shape (an outer holder exposing
    a cond-stage attribute around an inner checkpoint module).  This is a
    single example of the generic contract above — never its definition."""
    _resolve_generic_clip_helper()
    leaf, views, _flat = _build_adopt_tree("_ExampleCheckpointLeaf", count=5)
    inner = _AdoptWrapper({"example_core": leaf})
    outer = _AdoptWrapper({"cond_stage_model": inner}).with_extra(
        "norm_gate", _scalar_extra()
    )
    result = _call_generic_clip_helper(outer, views)
    _assert_matched_count(result, 5)
    _assert_extra_accounting(result, 1)
    _assert_scope_identifies(result, "example_core", "_ExampleCheckpointLeaf")


# ── 9. Serial runner semantics with fake nodes ─────────────────────────────


class _Recorder:
    def __init__(self):
        self.events = []
        self.lock = threading.Lock()


def _make_node_class(recorder, name, *, is_async=False, delay=0.0, returns=("out",)):
    class _Node:
        FUNCTION = "go"
        RETURN_TYPES = ("OUT",)
        OUTPUT_NODE = False

        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {}, "optional": {}}

        def go(self, **kwargs):
            with recorder.lock:
                recorder.events.append(f"{name}:start")
            if delay:
                __import__("time").sleep(delay)
            if is_async:
                async def _finish():
                    await asyncio.sleep(0.01)
                    with recorder.lock:
                        recorder.events.append(f"{name}:end")
                    return returns
                return _finish()
            with recorder.lock:
                recorder.events.append(f"{name}:end")
            return returns

    _Node.__name__ = name
    return _Node


def _fake_prompt(edges: dict):
    """edges: node_id -> {input_name: [src_node, socket]}"""
    prompt = {}
    for nid in edges:
        prompt[nid] = {"class_type": nid, "inputs": {k: list(v) for k, v in edges[nid].items()}}
    return prompt


def test_serial_runner_executes_dependencies_then_target_and_seeds_skip_execution():
    recorder = _Recorder()
    classes = {
        "dep": _make_node_class(recorder, "dep"),
        "target": _make_node_class(recorder, "target"),
        "seeded": _make_node_class(recorder, "seeded"),
    }
    prompt = _fake_prompt({
        "dep": {},
        "target": {"v": ["dep", 0]},
        "seeded": {},
    })
    runner = gs.GoldenSerialRunner(prompt, node_classes=classes)
    runner.seed("seeded", [["seed-value"]])

    async def main():
        runner.begin_scope(set())
        try:
            await runner.run_closure("target", include_target=True)
        finally:
            runner.end_scope()

    asyncio.run(main())
    assert recorder.events == ["dep:start", "dep:end", "target:start", "target:end"]
    summary = runner.executed_summary()
    assert ("seeded", "seeded", "prepare") not in summary
    assert runner.cache["target"].outputs == [["out"]]


def test_clip_node_67_seed_shape_and_text_link_resolution():
    """Native socket-major one-output seed shape: the seeded CLIPLoader is
    never executed, and CLIPTextEncode node 67 resolves its `text` link to the
    exact seeded object."""
    received = {}

    class FakeCLIPTextEncode67:
        FUNCTION = "go"
        RETURN_TYPES = ("CONDITIONING",)

        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {"text": ("CLIP",)}}

        def go(self, text):
            received["text"] = text
            return (f"cond:{text}",)

    prompt = {
        "66": {"class_type": "FakeCLIPLoader", "inputs": {}},
        "67": {"class_type": "FakeCLIPTextEncode67", "inputs": {"text": ["66", 0]}},
    }
    classes = {
        "FakeCLIPLoader": _make_node_class(_Recorder(), "FakeCLIPLoader"),
        "FakeCLIPTextEncode67": FakeCLIPTextEncode67,
    }
    runner = gs.GoldenSerialRunner(prompt, node_classes=classes)
    runner.seed("66", [["clip-native"]])  # one-output socket-major shape

    asyncio.run(runner.run_closure("67", include_target=True))

    assert received["text"] == "clip-native"
    assert runner.cache["67"].outputs == [["cond:clip-native"]]
    assert [nid for nid, _cls, _stage in runner.executed_summary()] == ["67"]


def test_final_image_branch_runs_175_then_1178_before_save_output_path():
    """The controlled SaveImage-equivalent output path consumes the image
    produced by the 175 -> 1178 chain, executed strictly in that order."""
    recorder = _Recorder()
    save_received = {}

    class GoldenSaveImage:
        FUNCTION = "go"
        RETURN_TYPES = ("OUT",)
        OUTPUT_NODE = True

        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {"images": ("IMAGE",)}}

        def go(self, images):
            with recorder.lock:
                recorder.events.append(("save", tuple(images)))
                save_received["images"] = images
            return {"ui": {"images": [{"filename": "golden.png"}]}, "result": ("saved",)}

    prompt = {
        "175": {"class_type": "Pre175", "inputs": {}},
        "1178": {"class_type": "Post1178", "inputs": {"img": ["175", 0]}},
        "1180": {"class_type": "GoldenSaveImage", "inputs": {"images": ["1178", 0]}},
    }
    classes = {
        "Pre175": _make_node_class(recorder, "Pre175"),
        "Post1178": _make_node_class(recorder, "Post1178"),
        "GoldenSaveImage": GoldenSaveImage,
    }
    runner = gs.GoldenSerialRunner(prompt, node_classes=classes)

    asyncio.run(runner.run_closure("1180", include_target=True))

    events = recorder.events
    # the recorder emits CLASS labels (Pre175/Post1178), not node ids
    assert events.index("Pre175:end") < events.index("Post1178:start")
    assert events.index("Post1178:end") < events.index(("save", tuple("out")))
    assert save_received["images"] == "out"  # exact 1178 output object
    assert runner.ui_outputs["1180"] == {"images": [{"filename": "golden.png"}]}


def test_serial_runner_awaits_async_node_before_next_starts():
    recorder = _Recorder()
    classes = {
        "slow_async": _make_node_class(recorder, "slow_async", is_async=True),
        "next": _make_node_class(recorder, "next"),
    }
    prompt = _fake_prompt({
        "slow_async": {},
        "next": {"v": ["slow_async", 0]},
    })
    runner = gs.GoldenSerialRunner(prompt, node_classes=classes)

    async def main():
        await runner.run_closure("next", include_target=True)

    asyncio.run(main())
    assert recorder.events.index("slow_async:end") < recorder.events.index("next:start")


def test_heavy_node_outside_assigned_stage_fails_closed():
    recorder = _Recorder()
    classes = {"VAELoader": _make_node_class(recorder, "VAELoader")}
    prompt = _fake_prompt({"VAELoader": {}})
    runner = gs.GoldenSerialRunner(prompt, node_classes=classes)

    async def main():
        runner.begin_scope(set())
        try:
            await runner.run_closure("VAELoader", include_target=True)
        finally:
            runner.end_scope()

    with pytest.raises(RuntimeError, match="heavy_node_outside_assigned_stage"):
        asyncio.run(main())


def test_input_is_list_and_output_is_list_semantics():
    recorder = _Recorder()

    class ListNode:
        FUNCTION = "go"
        RETURN_TYPES = ("OUT",)
        INPUT_IS_LIST = True
        OUTPUT_IS_LIST = (True,)

        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {"v": "OUT"}}

        def go(self, v):
            with recorder.lock:
                recorder.events.append(("listnode", tuple(v)))
            return (list(v),)

    prompt = _fake_prompt({"ListNode": {"v": ["src", 0]}, "src": {}})
    runner = gs.GoldenSerialRunner(prompt, node_classes={"ListNode": ListNode})
    runner.seed("src", [["a", "b"]])  # seeded multi-value socket

    async def main():
        await runner.run_closure("ListNode", include_target=True)

    asyncio.run(main())
    assert recorder.events == [("listnode", ("a", "b"))]
    assert runner.cache["ListNode"].outputs == [["a", "b"]]


def test_hidden_inputs_are_provided():
    class HiddenNode:
        FUNCTION = "go"
        RETURN_TYPES = ("OUT",)

        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {}, "hidden": {"unique_id": "UNIQUE_ID", "prompt": "PROMPT"}}

        def go(self, unique_id, prompt):
            return ((unique_id, bool(prompt)),)

    prompt = _fake_prompt({"HiddenNode": {}})
    runner = gs.GoldenSerialRunner(prompt, node_classes={"HiddenNode": HiddenNode})

    async def main():
        await runner.run_closure("HiddenNode", include_target=True)

    asyncio.run(main())
    outputs = runner.cache["HiddenNode"].outputs
    assert outputs == [[("HiddenNode", True)]]


def test_lazy_dependency_resolved_before_node_runs():
    recorder = _Recorder()

    class LazyConsumer:
        FUNCTION = "go"
        RETURN_TYPES = ("OUT",)

        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {"v": ["OUT", {"lazy": True}]}}

        def check_lazy_status(self, v=None):
            if v is None:
                return ["v"]
            return []

        def go(self, v):
            with recorder.lock:
                recorder.events.append(("consumer", v))
            return (v,)

    class LazySource:
        FUNCTION = "go"
        RETURN_TYPES = ("OUT",)

        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {}}

        def go(self):
            with recorder.lock:
                recorder.events.append(("source",))
            return ("lazy-value",)

    prompt = _fake_prompt({"LazyConsumer": {"v": ["LazySource", 0]}, "LazySource": {}})
    runner = gs.GoldenSerialRunner(prompt, node_classes={"LazyConsumer": LazyConsumer, "LazySource": LazySource})

    async def main():
        await runner.run_closure("LazyConsumer", include_target=True)

    asyncio.run(main())
    assert recorder.events == [("source",), ("consumer", "lazy-value")]


def test_lazy_status_naming_cached_link_does_not_retry_forever():
    class CachedLazyConsumer:
        FUNCTION = "go"
        RETURN_TYPES = ("OUT",)

        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {"v": ["OUT", {"lazy": True}]}}

        def check_lazy_status(self, v=None):
            return ["v"]

        def go(self, v):
            return (v,)

    prompt = _fake_prompt({"CachedLazyConsumer": {"v": ["CachedSource", 0]}, "CachedSource": {}})
    runner = gs.GoldenSerialRunner(
        prompt,
        node_classes={"CachedLazyConsumer": CachedLazyConsumer},
    )
    runner.seed("CachedSource", [["cached-value"]])

    asyncio.run(runner.run_closure("CachedLazyConsumer", include_target=True))

    assert runner.cache["CachedLazyConsumer"].outputs == [["cached-value"]]


def test_ui_outputs_collected():
    class UINode:
        FUNCTION = "go"
        RETURN_TYPES = ("OUT",)
        OUTPUT_NODE = True

        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {}}

        def go(self):
            return {"ui": {"images": [{"filename": "x.png"}]}, "result": ("ok",)}

    prompt = _fake_prompt({"UINode": {}})
    runner = gs.GoldenSerialRunner(prompt, node_classes={"UINode": UINode})

    async def main():
        await runner.run_closure("UINode", include_target=True)

    asyncio.run(main())
    assert runner.ui_outputs["UINode"] == {"images": [{"filename": "x.png"}]}
    assert runner.cache["UINode"].outputs == [["ok"]]


def test_resolve_golden_node_map_finds_canonical_nodes_and_fails_closed():
    prompt = {
        "1": {"class_type": "CLIPLoader", "inputs": {"clip_name": gs.CANONICAL_CLIP_NAME, "type": "lumina2"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "hi"}},
        "3": {"class_type": "UNETLoader", "inputs": {"unet_name": gs.CANONICAL_UNET_NAME}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": gs.CANONICAL_VAE_NAME}},
        "5": {"class_type": gs.CANONICAL_SAMPLER_CLASS, "inputs": {}},
        "6": {"class_type": "VAEDecode", "inputs": {}},
    }
    node_map = gs.resolve_golden_node_map(prompt)
    assert node_map.clip_loader_id == "1"
    assert node_map.sampler_id == "5"
    broken = dict(prompt)
    del broken["5"]
    with pytest.raises(RuntimeError, match="canonical_nodes_missing:sampler"):
        gs.resolve_golden_node_map(broken)


def _canonical_prompt():
    return {
        "1": {"class_type": "CLIPLoader", "inputs": {"clip_name": gs.CANONICAL_CLIP_NAME, "type": gs.CANONICAL_CLIP_TYPE}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "hi"}},
        "3": {"class_type": "UNETLoader", "inputs": {"unet_name": gs.CANONICAL_UNET_NAME}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": gs.CANONICAL_VAE_NAME}},
        "5": {"class_type": gs.CANONICAL_SAMPLER_CLASS, "inputs": {}},
        "6": {"class_type": "VAEDecode", "inputs": {}},
    }


class _FakeFolderPaths:
    def get_full_path_or_raise(self, folder: str, name: str) -> str:
        return f"/fake/{folder}/{name}"

    def get_folder_paths(self, folder: str) -> list:
        return [f"/fake/{folder}"]


def _setup_session(prompt, contract):
    session = object.__new__(gs.GoldenSession)
    session.recorder = gs.GoldenTelemetryRecorder()
    session.request = gs.GoldenRequest(request_id="r-setup", prompt=prompt)
    session.contract = contract
    session.node_classes = None
    session.node_map = None
    session.model_paths = {}
    session.runner = None
    return session


def test_request_setup_validates_workflow_hash_not_output_sha(monkeypatch):
    """The canonical request setup must compare the prompt against the
    contract's WORKFLOW hash only — never against the expected OUTPUT SHA.
    The synthetic workflow hash below differs from the output SHA constant,
    so success here proves no conflation."""
    prompt = _canonical_prompt()
    workflow_sha = gs.canonical_workflow_sha256(prompt)
    assert workflow_sha != EXPECTED_OUTPUT_SHA256
    contract = dataclasses.replace(gs.GoldenWorkflowContract(), workflow_sha256=workflow_sha)
    monkeypatch.delenv("COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK", raising=False)
    monkeypatch.setitem(sys.modules, "folder_paths", _FakeFolderPaths())
    node_map = asyncio.run(gs.golden_request_setup(_setup_session(prompt, contract)))
    assert node_map.clip_loader_id == "1"
    assert node_map.sampler_id == "5"


@pytest.mark.parametrize("env_value", [None, "1"], ids=["default", "enabled"])
def test_request_setup_fails_closed_on_workflow_hash_mismatch(monkeypatch, env_value):
    monkeypatch.setitem(sys.modules, "folder_paths", _FakeFolderPaths())
    if env_value is None:
        monkeypatch.delenv("COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK", raising=False)
    else:
        monkeypatch.setenv("COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK", env_value)
    contract = dataclasses.replace(gs.GoldenWorkflowContract(), workflow_sha256="0" * 64)
    with pytest.raises(RuntimeError, match="workflow_sha_mismatch"):
        asyncio.run(gs.golden_request_setup(_setup_session(_canonical_prompt(), contract)))


@pytest.mark.parametrize("env_value", ["0", "false"], ids=["zero", "false"])
def test_request_setup_rejects_disabled_workflow_hash_check(monkeypatch, env_value):
    monkeypatch.setitem(sys.modules, "folder_paths", _FakeFolderPaths())
    monkeypatch.setenv("COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK", env_value)
    prompt = _canonical_prompt()
    actual_sha = gs.canonical_workflow_sha256(prompt)
    contract = dataclasses.replace(gs.GoldenWorkflowContract(), workflow_sha256="0" * 64)
    session = _setup_session(prompt, contract)

    with pytest.raises(RuntimeError, match="workflow_hash_check_disabled"):
        asyncio.run(gs.golden_request_setup(session))

    hash_event = next(
        event for event in session.recorder.events
        if event["name"] == "golden_workflow_hash_check"
    )
    assert hash_event["fields"] == {
        "actual_sha256": actual_sha,
        "expected_sha256": "0" * 64,
        "attention_backend": None,
        "enabled": False,
        "bypassed": True,
    }
    details = session.recorder.intervals["golden_request_setup"].details
    assert details["error"].startswith("RuntimeError: workflow_hash_check_disabled")


# ── 10. VAE load/decode stage boundaries ───────────────────────────────────


def test_vae_decode_guard_requires_completed_tail_interval():
    session = object.__new__(gs.GoldenSession)
    session.recorder = gs.GoldenTelemetryRecorder()
    session.node_map = None
    session.runner = None
    session.vae = None

    async def main():
        await gs.golden_vae_decode(session)

    with pytest.raises(RuntimeError, match="vae_decode_requires_completed_sampler_tail"):
        asyncio.run(main())

    # With a completed tail but no runner wiring it still must fail closed —
    # but only AFTER the guard passed, proving ordering enforcement.
    session.recorder.begin_stage("golden_sampler_tail")
    session.recorder.end_stage("golden_sampler_tail", ready=True)
    with pytest.raises(RuntimeError):
        asyncio.run(main())


def test_stage_order_enforces_vae_load_before_sampling_and_decode_after_tail():
    rec = gs.GoldenTelemetryRecorder()
    for stage in (
        "golden_vae_load",
        "golden_sampling",
        "golden_sampler_tail",
        "golden_vae_decode",
    ):
        rec.begin_stage(stage)
        rec.end_stage(stage, ready=True)
    intervals = rec.intervals
    assert (
        intervals["golden_vae_load"].end_monotonic_ns
        <= intervals["golden_sampling"].entry_monotonic_ns
    )
    assert (
        intervals["golden_sampler_tail"].end_monotonic_ns
        <= intervals["golden_vae_decode"].entry_monotonic_ns
    )


def test_stage_order_full_walk_reconciles_and_restore_request_setup_handoff_enforced():
    """STAGE_ORDER matches the request_setup -> restore handoff: a full ordered
    walk reconciles cleanly, while an out-of-order restore ENTRY (before
    request_setup END) is reported against the previous stage's END."""
    rec = gs.GoldenTelemetryRecorder()
    for stage in gs.STAGE_ORDER:
        rec.begin_stage(stage)
        rec.end_stage(stage, ready=True)
    result = rec.reconcile_seriality()
    assert result["ok"] is True and result["count"] == 0

    clock_value = {"n": 100}

    def tick():
        clock_value["n"] += 10
        return clock_value["n"]

    bad = gs.GoldenTelemetryRecorder(monotonic=tick, wall=tick)
    bad.begin_stage("golden_request_setup")
    bad.end_stage("golden_request_setup")
    # restore ENTRY forced before request_setup END (broken handoff)
    bad._intervals["golden_restore"] = gs.GoldenStageInterval(
        name="golden_restore",
        entry_monotonic_ns=bad.intervals["golden_request_setup"].entry_monotonic_ns,
        entry_wall_ns=0,
        end_monotonic_ns=bad.intervals["golden_request_setup"].end_monotonic_ns + 5,
        end_wall_ns=0,
        ok=True,
    )
    result = bad.reconcile_seriality()
    assert result["ok"] is False and result["count"] == 1
    assert "golden_restore.END > golden_request_setup.ENTRY" in result["violations"][0]


# ── 10b. VAE transport performs exactly one header parse + one payload read ──


@pytest.mark.skipif(not __import__("torch").cuda.is_available(), reason="golden_vae_load requires CUDA")
def test_vae_load_performs_single_header_and_payload_read(tmp_path, monkeypatch):
    """The VAE stage must not perform a second header/payload read: the QD
    transport owns exactly one parse; the stage adds none.  The fake first
    stage exposes named_parameters()/named_buffers() whose tensors share
    storage with the QD views so the adoption proof passes."""
    import types

    import torch

    calls = {"qd": 0, "parse": 0}

    def counting_parse(path):
        calls["parse"] += 1
        return {"status": "ok", "header": {}, "data_start": 8, "total_data_bytes": 24}

    # One shared CUDA buffer; every view and live tensor aliases it so the
    # data-pointer sets match exactly.
    flat = torch.zeros(3 * 8, dtype=torch.uint8, device="cuda")
    views = {}
    named_params = []
    for i in range(2):
        views[f"w.{i}"] = flat[i * 8 : (i + 1) * 8].view(torch.float32).view([2])
        named_params.append((f"w.{i}", flat[i * 8 : (i + 1) * 8].view(torch.float32).view([2])))
    views["b.0"] = flat[16:24].view(torch.float32).view([2])
    named_buffers = [("b.0", flat[16:24].view(torch.float32).view([2]))]

    class _FakeFirstStage:
        def parameters(self):
            return [tensor for _name, tensor in named_params]

        def named_parameters(self):
            return list(named_params)

        def named_buffers(self):
            return list(named_buffers)

    fake_mp = _fake_model_patcher_module(dynamic=True)

    class _FakeVAE:
        working_dtypes = [torch.float32]
        first_stage_model = _FakeFirstStage()

        def __init__(self):
            # dynamic patcher instance with callable is_dynamic() -> True
            self.patcher = fake_mp.CoreModelPatcher()

        def throw_exception_if_invalid(self):
            pass

    fake_sd = types.SimpleNamespace(VAE=lambda sd, device, dtype, metadata: _FakeVAE())
    fake_comfy = types.SimpleNamespace(sd=fake_sd, model_patcher=fake_mp)

    def fake_qd_read(path, *, role, qd, block_bytes):
        calls["qd"] += 1
        counting_parse(path)  # the transport itself parses the header once
        return {
            "sd": dict(views),
            "owner": gs.GoldenQDOwner(gpu_buf=None, slots=[], device="cuda:0", role="vae"),
            "stats": {
                "gpu_bytes": 24,
                "source_read_count": 1,
                "h2d_completed_bytes": 24,
                "quiescence": {
                    "workers_joined": True,
                    "h2d_events_waited": True,
                    "copies_complete": True,
                    "operation_live": False,
                },
            },
        }

    monkeypatch.setitem(sys.modules, "comfy", fake_comfy)
    monkeypatch.setitem(sys.modules, "comfy.sd", fake_sd)
    monkeypatch.setitem(sys.modules, "comfy.model_patcher", fake_mp)
    monkeypatch.setattr(gs, "read_file_qd_gpu", fake_qd_read)
    monkeypatch.setattr(gs, "parse_safetensors_header", counting_parse)

    session = object.__new__(gs.GoldenSession)
    session.recorder = gs.GoldenTelemetryRecorder()
    session.model_paths = {"vae": str(tmp_path / "ae.safetensors")}
    session.contract = gs.GoldenWorkflowContract()
    session.vae_owner = None
    session.vae = None

    asyncio.run(gs.golden_vae_load(session))

    assert calls["qd"] == 1          # exactly one QD payload read
    assert calls["parse"] == 1       # no post-transport header reread
    assert session.vae is not None
    assert session.vae_owner is not None and session.vae_owner.role == "vae"


# ── 11. Output event → commit start/complete → true durable → result emit ──


class FakeAsyncVolume:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def commit(self):
        self.calls.append("commit")

        async def _do():
            self.calls.append("committed")
            if self.fail:
                raise RuntimeError("volume commit boom")

        return _do()


def _make_aio_volume():
    """Modal-style Volume: ``commit.aio`` is the async accessor; the sync
    ``commit()`` must never run when the Golden path awaits ``commit.aio()``."""

    class AioVolume:
        def __init__(self):
            self.calls = []

            async def _aio_impl():
                self.calls.append("committed_via_aio")

            def _sync_commit():
                self.calls.append("commit_sync_should_not_run")
                raise AssertionError("sync commit must not be used when .aio exists")

            _sync_commit.aio = _aio_impl
            self.commit = _sync_commit

    return AioVolume()


def _write_pending(tmp_path, payload=b"\x89PNG\r\n\x1a\n golden-bytes", *, sha=None, byte_count=None):
    """Real on-disk asset with a PendingDurability describing it; `sha` /
    `byte_count` overrides create deliberate mismatch cases."""
    mount_root = tmp_path / "volume"
    output_dir = mount_root / "output_assets"
    output_dir.mkdir(parents=True, exist_ok=True)
    asset = output_dir / "asset.png"
    asset.write_bytes(payload)
    return gs.PendingDurability(
        asset_abs_path=str(asset),
        volume_rel_path=f"output_assets/{asset.name}",
        sha256=sha if sha is not None else hashlib.sha256(payload).hexdigest(),
        byte_count=len(payload) if byte_count is None else byte_count,
        sidecar_path=str(output_dir / "asset.json"),
        volume_mount_root=str(mount_root),
    )


def test_durable_commit_success_event_ordering(tmp_path):
    """golden_durable_commit owns the commit and reopen proof events;
    OUTPUT_ENCODE_DONE / ASSET_WRITE_DONE belong to golden_output and the
    true-durable marker belongs to top-level integration."""
    pending = _write_pending(tmp_path)
    volume = FakeAsyncVolume()
    rec = gs.GoldenTelemetryRecorder()
    asyncio.run(
        gs.golden_durable_commit(
            volume, pending, rec, expected_sha256=pending.sha256
        )
    )
    names = [e["name"] for e in rec.events]
    assert names == [
        "VOLUME_COMMIT_START",
        "VOLUME_COMMIT_COMPLETE",
        "durable_reopen_verified",
        "DURABLE_COMMIT_SUBSPANS",
    ]
    assert pending.committed is True
    assert volume.calls == ["commit", "committed"]


def test_commit_reopen_verification_precedes_true_durable_result(tmp_path):
    """Commit must be followed by reopened byte-count/SHA verification of the
    persisted asset before TRUE_FIRST_DURABLE_RESULT can be stamped."""
    pending = _write_pending(tmp_path)
    rec = gs.GoldenTelemetryRecorder()
    asyncio.run(
        gs.golden_durable_commit(
            FakeAsyncVolume(), pending, rec, expected_sha256=pending.sha256
        )
    )
    assert pending.committed is True
    rec.mark_true_durable()
    names = [e["name"] for e in rec.events]
    assert (
        names.index(gs.EVENT_VOLUME_COMMIT_COMPLETE)
        < names.index(gs.EVENT_TRUE_FIRST_DURABLE_RESULT)
    )


def test_commit_reopen_accepts_output_expectation_warning(tmp_path):
    pending = _write_pending(tmp_path)
    recorder = gs.GoldenTelemetryRecorder()

    asyncio.run(
        gs.golden_durable_commit(
            FakeAsyncVolume(),
            pending,
            recorder,
            expected_sha256="f" * 64,
        )
    )

    assert pending.committed is True
    assert recorder.events[-1]["name"] == "DURABLE_COMMIT_SUBSPANS"
    recorder.mark_true_durable()


def test_durable_commit_exposes_full_nonnegative_decomposition_with_injected_clock(tmp_path):
    class Clock:
        def __init__(self):
            self.value = 100

        def tick(self):
            self.value += 1
            return self.value

    pending = _write_pending(tmp_path, payload=b"decomposition")
    clock = Clock()
    recorder = gs.GoldenTelemetryRecorder(monotonic=clock.tick, wall=clock.tick)
    asyncio.run(
        gs.golden_durable_commit(
            FakeAsyncVolume(), pending, recorder, expected_sha256=pending.sha256
        )
    )

    event = next(e for e in recorder.events if e["name"] == "DURABLE_COMMIT_SUBSPANS")
    fields = event["fields"]
    assert fields["clock"] == "recorder.monotonic_ns"
    assert "Volume.commit as one blocking call" in fields["blocking_commit_note"]
    spans = fields["durable_commit_subspans"]
    assert tuple(spans) == gs.DURABLE_COMMIT_SUBSPAN_NAMES
    assert all(span["duration_ns"] >= 0 for span in spans.values())
    starts = [span["start_monotonic_ns"] for span in spans.values()]
    ends = [span["end_monotonic_ns"] for span in spans.values()]
    assert all(start is not None and end is not None for start, end in zip(starts, ends))
    assert all(start <= end for start, end in zip(starts, ends))
    assert (
        spans["volume_commit_call_wall"]["end_monotonic_ns"]
        == spans["commit_return_to_reopen_start"]["start_monotonic_ns"]
    )
    assert "true_durable_result_marker_publication" not in spans


def test_true_durable_marker_is_separate_post_commit_span_and_event_snapshot_isolated(tmp_path):
    pending = _write_pending(tmp_path, payload=b"marker")
    recorder = gs.GoldenTelemetryRecorder()
    asyncio.run(
        gs.golden_durable_commit(
            FakeAsyncVolume(), pending, recorder, expected_sha256=pending.sha256
        )
    )
    subspans_event = next(
        e for e in recorder.events if e["name"] == "DURABLE_COMMIT_SUBSPANS"
    )
    before = json.loads(json.dumps(subspans_event["fields"]["durable_commit_subspans"]))

    recorder.mark_true_durable()

    assert subspans_event["fields"]["durable_commit_subspans"] == before
    assert "true_durable_result_marker_publication" not in before
    marker = next(
        e for e in recorder.events if e["name"] == "DURABLE_RESULT_MARKER_PUBLICATION"
    )
    assert marker["fields"]["subspan"] == "true_durable_result_marker_publication"
    assert marker["fields"]["outside_durable_commit_stage"] is True
    assert marker["fields"]["stage_boundary"] == "post_commit_result_marker"
    assert marker["fields"]["duration_ns"] >= 0


def test_durable_commit_failure_emits_failure_decomposition_payload(tmp_path):
    pending = _write_pending(tmp_path, payload=b"failure")
    recorder = gs.GoldenTelemetryRecorder()
    with pytest.raises(RuntimeError, match="volume commit boom"):
        asyncio.run(
            gs.golden_durable_commit(
                FakeAsyncVolume(fail=True),
                pending,
                recorder,
                expected_sha256=pending.sha256,
            )
        )
    event = next(e for e in recorder.events if e["name"] == "DURABLE_COMMIT_SUBSPANS")
    assert event["fields"]["outcome"] == "failure"
    assert "Volume.commit as one blocking call" in event["fields"]["blocking_commit_note"]
    assert event["fields"]["durable_commit_subspans"]["volume_commit_call_wall"]["duration_ns"] >= 0
    assert "true_durable_result_marker_publication" not in event["fields"]["durable_commit_subspans"]


def test_commit_reopen_sha_mismatch_blocks_true_durable(tmp_path):
    """The commit stage itself only commits; the reopened-object proof lives
    in verify_committed_object (top-level integration owns its ordering).
    A descriptor SHA != committed file bytes must fail that proof even though
    the volume commit succeeded."""
    pending = _write_pending(tmp_path, sha="ff" * 32)  # descriptor SHA != file bytes
    rec = gs.GoldenTelemetryRecorder()
    with pytest.raises(RuntimeError, match="durable_sha_mismatch"):
        asyncio.run(
            gs.golden_durable_commit(
                FakeAsyncVolume(), pending, rec, expected_sha256=pending.sha256
            )
        )
    assert pending.committed is False
    assert gs.EVENT_TRUE_FIRST_DURABLE_RESULT not in [e["name"] for e in rec.events]


def test_commit_reopen_byte_count_mismatch_blocks_true_durable(tmp_path):
    """A descriptor size != committed file size must fail the reopened-object
    proof even though the volume commit succeeded."""
    pending = _write_pending(tmp_path, byte_count=999)  # descriptor size != file size
    rec = gs.GoldenTelemetryRecorder()
    with pytest.raises(RuntimeError, match="durable_byte_count_mismatch"):
        asyncio.run(
            gs.golden_durable_commit(
                FakeAsyncVolume(), pending, rec, expected_sha256=pending.sha256
            )
        )
    assert pending.committed is False
    assert gs.EVENT_TRUE_FIRST_DURABLE_RESULT not in [e["name"] for e in rec.events]


def test_durable_commit_prefers_aio_accessor(tmp_path):
    pending = _write_pending(tmp_path, payload=b"a")
    volume = _make_aio_volume()
    rec = gs.GoldenTelemetryRecorder()
    asyncio.run(
        gs.golden_durable_commit(
            volume, pending, rec, expected_sha256=pending.sha256
        )
    )
    assert volume.calls == ["committed_via_aio"]
    assert pending.committed is True


def test_commit_failure_prevents_durable_and_result(tmp_path):
    pending = _write_pending(tmp_path, payload=b"a")
    volume = FakeAsyncVolume(fail=True)
    rec = gs.GoldenTelemetryRecorder()
    with pytest.raises(RuntimeError, match="volume commit boom"):
        asyncio.run(
            gs.golden_durable_commit(
                volume, pending, rec, expected_sha256=pending.sha256
            )
        )
    names = [e["name"] for e in rec.events]
    assert "VOLUME_COMMIT_COMPLETE" not in names
    assert "VOLUME_COMMIT_FAILED" in names
    assert pending.committed is False
    with pytest.raises(RuntimeError, match="true_durable_requires"):
        rec.mark_true_durable()


# ── 11b. Output encoding: compression level 1 + hash integrity ─────────────


def _png_array():
    import numpy as np

    return np.full((4, 6, 3), 127, dtype=np.uint8)


def test_io_bytes_png_uses_compression_level_1():
    captured = {}

    class FakeEncoded:
        def save(self, bio, **kwargs):
            captured.update(kwargs)

    class FakeImageModule:
        @staticmethod
        def fromarray(array):
            return FakeEncoded()

    gs.io_bytes_png(FakeImageModule, _png_array())
    assert captured.get("format") == "PNG"
    assert captured.get("compress_level") == 1


def test_io_bytes_png_matches_pil_compress_level_1_bytes():
    import io

    import numpy as np
    from PIL import Image

    rng = np.random.RandomState(7)
    arr = rng.randint(0, 255, size=(64, 64, 3), dtype=np.uint8)
    ours = gs.io_bytes_png(Image, arr)
    reference = io.BytesIO()
    Image.fromarray(arr).save(reference, format="PNG", compress_level=1)
    assert ours == reference.getvalue()
    assert ours.startswith(b"\x89PNG\r\n\x1a\n")


def test_golden_output_writes_asset_matching_pending_hash(tmp_path, caplog):
    """golden_output requires an initialized runner/node_map and the exact
    canonical output branch (VAEDecode -> Any Switch (rgthree) -> SaveImage).
    The configured expected SHA deliberately differs from the synthetic PNG:
    the output must still be written and the mismatch must be persisted as an
    explicit warning while the observed content hash remains authoritative."""
    import numpy as np
    import torch
    from PIL import Image

    save_executed = {"called": False}

    class FakeAnySwitch:
        FUNCTION = "go"
        RETURN_TYPES = ("IMAGE",)

        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {"any_02": ("*",)}, "optional": {}}

        def go(self, any_02):
            return (any_02,)  # exact pass-through

    class FakeSaveImage:
        FUNCTION = "save"
        RETURN_TYPES = ()

        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {"images": ("IMAGE",)}}

        def save(self, images):
            save_executed["called"] = True  # must NEVER run in golden_output
            raise AssertionError("SaveImage must not execute inside golden_output")

    prompt = _canonical_prompt()
    prompt["7"] = {"class_type": "Any Switch (rgthree)", "inputs": {"any_02": ["6", 0]}}
    prompt["8"] = {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "golden"}}
    node_map = gs.resolve_golden_node_map(prompt)
    assert node_map.vae_decode_id == "6"

    images = torch.rand(1, 8, 8, 3)
    runner = gs.GoldenSerialRunner(
        prompt,
        node_classes={"Any Switch (rgthree)": FakeAnySwitch, "SaveImage": FakeSaveImage},
    )
    runner.seed(node_map.vae_decode_id, [[images]])  # VAEDecode already cached

    # Expected bytes: identical upstream output encoding semantics (no metadata).
    first = np.clip(255.0 * images.numpy(), 0, 255).astype(np.uint8)[0]
    png_bytes = gs.io_bytes_png(Image, first)
    contract = dataclasses.replace(
        gs.GoldenWorkflowContract(),
        expected_output_png_sha256="f" * 64,
    )

    session = object.__new__(gs.GoldenSession)
    session.recorder = gs.GoldenTelemetryRecorder()
    session.request = gs.GoldenRequest(request_id="r-out", prompt=prompt)
    session.contract = contract
    mount_root = tmp_path / "volume"
    mount_root.mkdir()
    session.volume_mount_root = str(mount_root)
    session.output_root = str(mount_root / "output_assets")
    session.runner = runner
    session.node_map = node_map

    pending = asyncio.run(gs.golden_output(session))

    data = Path(pending.asset_abs_path).read_bytes()
    assert data == png_bytes
    observed_sha = hashlib.sha256(data).hexdigest()
    assert observed_sha == pending.sha256 != contract.expected_output_png_sha256
    assert len(data) == pending.byte_count
    assert pending.committed is False
    assert Path(pending.sidecar_path).exists()
    # only the pass-through switch executed; VAEDecode stayed cached and
    # SaveImage itself never ran
    assert [nid for nid, _cls, _stage in runner.executed_summary()] == ["7"]
    assert save_executed["called"] is False
    names = [e["name"] for e in session.recorder.events]
    warning = next(e for e in session.recorder.events if e["name"] == "OUTPUT_SHA_MISMATCH_WARNING")
    assert warning["fields"] == {
        "expected_sha": contract.expected_output_png_sha256,
        "observed_sha": observed_sha,
        "output_sha_match": False,
        "output_sha_warning": {
            "expected": contract.expected_output_png_sha256,
            "observed": observed_sha,
            "reason": "configured_output_sha_mismatch",
        },
    }
    assert any("Golden output SHA mismatch is warning-only" in record.message for record in caplog.records)
    stage = session.recorder.to_json_dict()["stages"][-1]
    assert stage["name"] == "golden_output"
    assert stage["details"]["output_sha_match"] is False
    assert stage["details"]["output_sha_warning"]["observed"] == observed_sha
    assert gs.EVENT_OUTPUT_ENCODE_DONE in names
    assert gs.EVENT_ASSET_WRITE_DONE in names


def test_final_result_requires_committed_pending_and_durable_mark(tmp_path):
    session = object.__new__(gs.GoldenSession)
    pending = _write_pending(tmp_path)
    session.pending_durability = pending
    session.recorder = gs.GoldenTelemetryRecorder()
    session.runner = None
    session.request = gs.GoldenRequest(request_id="r1", prompt={})
    with pytest.raises(RuntimeError, match="requires_committed_pending_durability"):
        session.build_final_result()
    session.pending_durability.committed = True
    with pytest.raises(RuntimeError, match="requires_true_durable_mark"):
        session.build_final_result()
    session.recorder.begin_stage("golden_durable_commit")
    session.recorder.end_stage("golden_durable_commit", ready=True)
    session.recorder.mark_reopen_verified(
        gs.verify_committed_object(pending, expected_sha256=pending.sha256)
    )
    session.recorder.mark_true_durable()
    result = session.build_final_result()
    assert result.true_durable is True


# ── 12. Snapshot proof: surfaces required, clean passes, contamination fails ──


def test_snapshot_proof_empty_surfaces_fail_closed():
    """No scanned surface means cleanliness was never observed: fail closed."""
    with pytest.raises(RuntimeError, match="snapshot_proof"):
        gs.golden_snapshot_content_proof()


def test_snapshot_proof_nonempty_clean_surface_passes_and_persists(tmp_path):
    proof = gs.golden_snapshot_content_proof(
        roots=[{"status": "clean"}],
        snapshot_size_bytes=1,
        persist_path=str(tmp_path / "proof.json"),
    )
    assert proof["surface_count"] == 1
    assert proof["tensor_count"] == 0
    assert proof["model_patcher_count"] == 0
    assert proof["qd_owner_count"] == 0
    for role in ("unet", "clip", "vae"):
        assert proof["roles"][role] == {"tensor_count": 0, "parameter_bytes": 0, "qd_owner_count": 0}
    saved = json.loads((tmp_path / "proof.json").read_text(encoding="utf-8"))
    assert saved["surface_count"] == 1
    assert saved["tensor_count"] == 0


def test_snapshot_proof_nonzero_fails_closed():
    import torch

    root = torch.zeros(4, dtype=torch.float32)
    with pytest.raises(RuntimeError, match="snapshot_proof_nonzero"):
        gs.golden_snapshot_content_proof(roots=[root], snapshot_size_bytes=1)


def test_snapshot_proof_counts_qd_owner_by_role():
    owner = gs.GoldenQDOwner(gpu_buf=None, slots=[], device="cuda:0", role="vae")
    with pytest.raises(RuntimeError, match="snapshot_proof_nonzero") as excinfo:
        gs.golden_snapshot_content_proof(roots=[owner], snapshot_size_bytes=1)
    message = str(excinfo.value)
    assert '"vae"' in message


def test_snapshot_proof_unavailable_surface_fails_closed():
    class Opaque:
        __slots__ = ()

    with pytest.raises(RuntimeError, match="surface_unavailable"):
        gs.golden_snapshot_content_proof(registries=[Opaque()], snapshot_size_bytes=1)


def test_snapshot_proof_fails_on_leaked_golden_worker_thread():
    release = threading.Event()
    leaked = threading.Thread(
        target=lambda: release.wait(10.0), name="golden-qd-gate-leak", daemon=True
    )
    leaked.start()
    try:
        with pytest.raises(RuntimeError, match="snapshot_proof_nonzero") as excinfo:
            gs.golden_snapshot_content_proof(roots=[{}], snapshot_size_bytes=1)
        assert "preload_worker_count" in str(excinfo.value)
    finally:
        release.set()
        leaked.join(timeout=5)
    # once the worker is gone the same surface proves clean again
    gs.golden_snapshot_content_proof(roots=[{}], snapshot_size_bytes=1)


def test_snapshot_proof_fails_on_leaked_future():
    loop = asyncio.new_event_loop()
    try:
        fut = loop.create_future()
        with pytest.raises(RuntimeError, match="snapshot_proof_nonzero") as excinfo:
            gs.golden_snapshot_content_proof(roots=[fut], snapshot_size_bytes=1)
        assert '"future_count": 1' in str(excinfo.value)
    finally:
        loop.close()


def test_snapshot_proof_does_not_mutate_roots():
    import copy

    import torch

    root = {"t": torch.zeros(3), "nested": {"list": [1, 2, 3]}}
    before = copy.deepcopy(root)
    with pytest.raises(RuntimeError):
        gs.golden_snapshot_content_proof(
            roots=[root], snapshot_size_bytes=gs._SNAPSHOT_PROOF_MAX_SIZE_BYTES
        )
    assert str(root) == str(before)
    assert root["nested"]["list"] == [1, 2, 3]


def test_snapshot_proof_fails_closed_on_bounded_nested_tensor_and_patcher_refs():
    class ModelPatcherLike:
        pass

    root = {"nested": {"tensor": _torch.zeros(2), "patcher": ModelPatcherLike()}}
    with pytest.raises(RuntimeError, match="snapshot_proof_nonzero") as error:
        gs.golden_snapshot_content_proof(roots=[root], snapshot_size_bytes=1)
    assert "tensor_count" in str(error.value)
    assert "model_patcher_count" in str(error.value)


def test_snapshot_proof_hostile_properties_are_not_invoked():
    class Hostile:
        def __init__(self):
            self.child = {"safe": {"value": 1}}

        @property
        def closed(self):
            raise AssertionError("arbitrary property was invoked")

        @property
        def read(self):
            raise AssertionError("arbitrary property was invoked")

    proof = gs.golden_snapshot_content_proof(roots=[Hostile()], snapshot_size_bytes=1)
    assert proof["tensor_count"] == 0


# ── 13. Contract constants ─────────────────────────────────────────────────


def test_contract_workflow_and_output_shas_are_distinct_canonical_values():
    """Reconciled Phase 2 gate: the contract carries BOTH the canonical
    workflow hash AND the expected output SHA as distinct frozen values."""
    contract = gs.GoldenWorkflowContract()
    assert contract.workflow_sha256 == CANONICAL_WORKFLOW_SHA256
    fields = {f.name: getattr(contract, f.name) for f in dataclasses.fields(contract)}
    output_sha_fields = [name for name, value in fields.items() if value == EXPECTED_OUTPUT_SHA256]
    assert output_sha_fields, (
        "contract must carry the expected output SHA "
        f"{EXPECTED_OUTPUT_SHA256}; fields={sorted(fields)}"
    )
    assert contract.workflow_sha256 != EXPECTED_OUTPUT_SHA256


def test_contract_constants_match_spec():
    contract = gs.GoldenWorkflowContract()
    assert contract.qd == 4
    assert contract.block_bytes == 32 * 1024 * 1024
    assert contract.expected_unet_tensor_count == 453
    assert contract.clip_name == "qwen_3_4b.safetensors"
    assert contract.unet_name == "z_image_turbo_bf16.safetensors"
    assert contract.vae_name == "ae.safetensors"


def test_workflow_sha_function_is_deterministic():
    prompt = {"1": {"class_type": "A", "inputs": {"x": 1}}}
    assert gs.canonical_workflow_sha256(prompt) == gs.canonical_workflow_sha256(prompt)


# ── 14. Teardown telemetry: completed END/ok persisted; failures unmasked ──


def _teardown_session(recorder, telemetry_path=None):
    session = object.__new__(gs.GoldenSession)
    session.recorder = recorder
    session.telemetry_path = telemetry_path
    session.clip_owner = None
    session.unet_owner = None
    session.vae_owner = None
    # Per-checkpoint owners introduced by ClipLoadSpec (init bypassed above).
    session.clip_owners = []
    # Required fail-closed proof boundary: a valid nonempty passive supplier.
    session.snapshot_proof = lambda: {"roots": [{}], "registries": [], "coordinators": []}
    session.snapshot_proof_result = None
    return session


def test_successful_teardown_ends_without_persisting_telemetry(tmp_path):
    rec = gs.GoldenTelemetryRecorder()
    rec.begin_stage("golden_vae_decode")
    rec.end_stage("golden_vae_decode", ready=True)
    target = tmp_path / "telemetry.json"
    session = _teardown_session(rec, str(target))

    asyncio.run(gs.golden_teardown(session))

    interval = rec.intervals["golden_teardown"]
    assert interval.ok is True
    assert interval.end_monotonic_ns is not None
    assert interval.ready_monotonic_ns is not None
    assert not target.exists()
    assert session.snapshot_proof_result is None
    event_names = [e["name"] for e in rec.events]
    assert "snapshot_proof_complete" not in event_names


def test_failed_execution_not_masked_by_teardown_failure(tmp_path, monkeypatch):
    """When execution fails and teardown also fails, the ORIGINAL execution
    error must surface — never the teardown error alone."""
    import torch

    monkeypatch.setitem(sys.modules, "folder_paths", _FakeFolderPaths())
    release = threading.Event()
    leaked = threading.Thread(
        target=lambda: release.wait(15.0), name="golden-qd-mask-gate", daemon=True
    )
    leaked.start()
    try:
        # Canonical prompt + matching workflow hash so request_setup succeeds
        # and the failure lands in restore (the leaked worker it detects).
        prompt = _canonical_prompt()
        contract = dataclasses.replace(
            gs.GoldenWorkflowContract(),
            workflow_sha256=gs.canonical_workflow_sha256(prompt),
        )
        request = gs.GoldenRequest(request_id="mask", prompt=prompt)
        with pytest.raises(RuntimeError) as excinfo:
            asyncio.run(
                gs.golden_serial_execute(
                    request, volume=object(), output_root=str(tmp_path / "out"),
                    contract=contract,
                )
            )
        message = str(excinfo.value)
        # restore fails first: CUDA absence, or the leaked worker it detects
        expected_marker = (
            "restore_preload_workers_present"
            if torch.cuda.is_available()
            else "cuda_unavailable"
        )
        assert expected_marker in message
        assert "teardown_workers_pending" not in message
    finally:
        release.set()
        leaked.join(timeout=5)


# ── 15. QD throughput computed from reconciled nonzero bytes ────────────────


def _refs_reconciled_bytes(value) -> bool:
    """True when the expression reads the reconciled counter, either as a
    bare local name or via the stats subscript (stats["bytes_read"])."""
    for n in ast.walk(value):
        if isinstance(n, ast.Name) and n.id == "bytes_read":
            return True
        if (
            isinstance(n, ast.Subscript)
            and isinstance(n.slice, ast.Constant)
            and n.slice.value == "bytes_read"
        ):
            return True
    return False


def test_qd_throughput_computed_after_reconciled_bytes():
    """qd_source_gbps must be derived from stats['bytes_read'] AFTER that
    counter is reconciled from records (nonzero), not from its initial zero."""
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "read_file_qd_gpu"
    )

    def _subscript_key(target):
        if not isinstance(target, ast.Subscript):
            return None
        sl = target.slice
        return sl.value if isinstance(sl, ast.Constant) else getattr(sl, "value", None)

    bytes_read_lines = []
    gbps_lines = []
    gbps_refs_bytes = False
    for node in ast.walk(fn):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            key = _subscript_key(target)
            if key == "bytes_read":
                bytes_read_lines.append(node.lineno)
            elif key == "qd_source_gbps":
                gbps_lines.append(node.lineno)
                gbps_refs_bytes = _refs_reconciled_bytes(node.value)
    assert bytes_read_lines and gbps_lines, "expected bytes_read + qd_source_gbps assignments"
    assert max(bytes_read_lines) < min(gbps_lines), (
        "qd_source_gbps must be computed after the reconciled bytes_read assignment"
    )
    assert gbps_refs_bytes, "qd_source_gbps must be derived from reconciled bytes_read"


# ── 16. V3-like NodeOutput normalization (runner-level) ────────────────────


from comfy_api.internal import _NodeOutputInternal as _UpstreamNodeOutputInternal


class _FakeNodeOutput(_UpstreamNodeOutputInternal):
    """V3-like NodeOutput fake (mirrors comfy_api.latest._io.NodeOutput:
    .result tuple, .ui, .expand, .block_execution) that subclasses the REAL
    upstream internal marker so the runner's strict isinstance contract is
    exercised end-to-end."""

    def __init__(self, result=(), ui=None, expand=None, block_execution=None):
        self.result = result
        self.ui = ui
        self.expand = expand
        self.block_execution = block_execution


def test_v3_nodeoutput_single_result_cached_socket_major_and_exact_handoff():
    """A node returning a NodeOutput-shaped object must be normalized: the one
    result is cached as a socket-major output ([[value]]) and the downstream
    link receives the EXACT latent dict object."""
    latent = {"samples": "latent-tensor-sentinel"}
    received = {}
    ui_payload = {"images": [{"filename": "v3.png"}]}

    class V3LatentProducer:
        FUNCTION = "go"
        RETURN_TYPES = ("LATENT",)
        OUTPUT_NODE = True

        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {}, "optional": {}}

        def go(self):
            return _FakeNodeOutput(result=(latent,), ui=ui_payload)

    class LatentConsumer:
        FUNCTION = "go"
        RETURN_TYPES = ("LATENT",)

        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {"latent": ("LATENT",)}}

        def go(self, latent):
            received["latent"] = latent
            return (latent,)

    prompt = _fake_prompt({
        "producer": {},
        "consumer": {"latent": ["producer", 0]},
    })
    runner = gs.GoldenSerialRunner(
        prompt, node_classes={"producer": V3LatentProducer, "consumer": LatentConsumer}
    )

    asyncio.run(runner.run_closure("consumer", include_target=True))

    assert runner.cache["producer"].outputs == [[latent]]  # socket-major single result
    assert runner.ui_outputs["producer"] == ui_payload
    assert received["latent"] is latent  # exact object handoff, no copy/rewrap
    assert [nid for nid, _c, _s in runner.executed_summary()] == ["producer", "consumer"]


def test_v3_block_execution_fails_closed_without_caching_or_downstream():
    """block_execution must fail closed in the Golden serial runner: no cached
    output for the blocking node and no downstream execution."""
    executed = []

    class V3Blocker:
        FUNCTION = "go"
        RETURN_TYPES = ("OUT",)

        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {}, "optional": {}}

        def go(self):
            return _FakeNodeOutput(result=("never",), block_execution="blocked by upstream")

    class NeverRuns:
        FUNCTION = "go"
        RETURN_TYPES = ("OUT",)

        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {"v": ("OUT",)}}

        def go(self, v):
            executed.append(v)
            return (v,)

    prompt = _fake_prompt({
        "blocker": {},
        "consumer": {"v": ["blocker", 0]},
    })
    runner = gs.GoldenSerialRunner(
        prompt, node_classes={"blocker": V3Blocker, "consumer": NeverRuns}
    )

    with pytest.raises(RuntimeError, match="(?i)block"):
        asyncio.run(runner.run_closure("consumer", include_target=True))

    assert "blocker" not in runner.cache
    assert executed == []


def test_v3_expand_fails_closed_no_dynamic_subgraph_execution():
    """expand must fail closed: the Golden runner does not demand generic
    dynamic graph execution, registers no subgraph nodes, caches nothing."""
    executed = []

    class V3Expander:
        FUNCTION = "go"
        RETURN_TYPES = ("OUT",)

        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {}, "optional": {}}

        def go(self):
            return _FakeNodeOutput(result=("x",), expand={"sub_1": {"class_type": "X", "inputs": {}}})

    class NeverRuns:
        FUNCTION = "go"
        RETURN_TYPES = ("OUT",)

        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {"v": ("OUT",)}}

        def go(self, v):
            executed.append(v)
            return (v,)

    prompt = _fake_prompt({
        "expander": {},
        "consumer": {"v": ["expander", 0]},
    })
    runner = gs.GoldenSerialRunner(
        prompt, node_classes={"expander": V3Expander, "consumer": NeverRuns}
    )

    with pytest.raises(RuntimeError, match="(?i)expand|subgraph|dynamic"):
        asyncio.run(runner.run_closure("consumer", include_target=True))

    assert "expander" not in runner.cache
    assert executed == []
    assert all(not str(nid).startswith("sub_") for nid in runner.prompt)


# ── 17. Exact chain: 88 EmptySD3LatentImage -> 214 Any Switch -> 1242 ──────


def test_chain_88_empty_latent_214_any_switch_1242_dependency_order_and_handoff():
    """Synthetic exact equivalent of the canonical chain 88 -> 214 -> 1242:
    strict serial order and exact object handoff of the latent dict produced
    by EmptySD3LatentImage through the Any Switch pass-through into the
    sampler dependency."""
    import torch

    order = []
    latent = {"samples": torch.zeros((1, 4, 8, 8))}
    received = {}

    class EmptySD3LatentImage:
        FUNCTION = "go"
        RETURN_TYPES = ("LATENT",)

        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {}, "optional": {}}

        def go(self):
            order.append("88")
            return (latent,)

    class AnySwitch:
        FUNCTION = "go"
        RETURN_TYPES = ("*",)

        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {"any_02": ("*",)}, "optional": {}}

        def go(self, any_02):
            order.append("214")
            return (any_02,)  # exact pass-through

    class ModelSamplingAuraFlow:  # sampler-dependency class shape (no 'Sampler' hint)
        FUNCTION = "go"
        RETURN_TYPES = ("OUT",)

        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {"any_02": ("*",)}}

        def go(self, any_02):
            order.append("1242")
            received["value"] = any_02
            return (any_02,)

    prompt = {
        "88": {"class_type": "EmptySD3LatentImage", "inputs": {}},
        "214": {"class_type": "Any Switch (rgthree)", "inputs": {"any_02": ["88", 0]}},
        "1242": {"class_type": "ModelSamplingAuraFlow", "inputs": {"any_02": ["214", 0]}},
    }
    runner = gs.GoldenSerialRunner(prompt, node_classes={
        "EmptySD3LatentImage": EmptySD3LatentImage,
        "Any Switch (rgthree)": AnySwitch,
        "ModelSamplingAuraFlow": ModelSamplingAuraFlow,
    })

    asyncio.run(runner.run_closure("1242", include_target=True))

    assert order == ["88", "214", "1242"]
    assert received["value"] is latent          # exact object handoff
    assert runner.cache["88"].outputs == [[latent]]
    assert runner.cache["214"].outputs == [[latent]]
    assert [nid for nid, _c, _s in runner.executed_summary()] == ["88", "214", "1242"]


# ── 18. Dynamic patcher preflight (CLIP/VAE construction boundary) ──────────


def _fake_model_patcher_module(dynamic: bool):
    """Injected fake comfy.model_patcher. Legacy upstream alias is
    ``CoreModelPatcher = ModelPatcher``; a working comfy-aimdo install rebinds
    ``CoreModelPatcher = ModelPatcherDynamic`` (main.py behavior)."""
    import types

    mod = types.ModuleType("comfy.model_patcher")

    class ModelPatcher:
        def __init__(self, *args, **kwargs):
            self.is_legacy_base = True

    class ModelPatcherDynamic(ModelPatcher):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

        def is_dynamic(self) -> bool:
            return True

    mod.ModelPatcher = ModelPatcher
    mod.ModelPatcherDynamic = ModelPatcherDynamic
    mod.CoreModelPatcher = ModelPatcherDynamic if dynamic else ModelPatcher
    return mod


def _install_fake_comfy(monkeypatch, fake_sd, fake_mp, fake_mm=None):
    import types

    if fake_mm is None:
        fake_mm = types.ModuleType("comfy.model_management")
        fake_mm.text_encoder_initial_device = lambda *args, **kwargs: "native"
    fake_comfy = types.ModuleType("comfy")
    fake_comfy.sd = fake_sd
    fake_comfy.model_patcher = fake_mp
    fake_comfy.model_management = fake_mm
    monkeypatch.setitem(sys.modules, "comfy", fake_comfy)
    monkeypatch.setitem(sys.modules, "comfy.sd", fake_sd)
    monkeypatch.setitem(sys.modules, "comfy.model_patcher", fake_mp)
    monkeypatch.setitem(sys.modules, "comfy.model_management", fake_mm)
    monkeypatch.setitem(sys.modules, "folder_paths", _FakeFolderPaths())


def test_clip_load_preflight_rejects_legacy_core_model_patcher_before_construction(monkeypatch):
    """Legacy CoreModelPatcher (= ModelPatcher, aimdo inactive) must fail
    closed BEFORE any CLIP construction is attempted."""
    import types

    import torch

    fake_mp = _fake_model_patcher_module(dynamic=False)
    constructed = {"count": 0}

    def _construct(*args, **kwargs):
        constructed["count"] += 1
        return types.SimpleNamespace()

    fake_sd = types.ModuleType("comfy.sd")
    fake_sd.load_text_encoder_state_dicts = _construct
    fake_sd.CLIPType = types.SimpleNamespace(LUMINA2="LUMINA2")
    _install_fake_comfy(monkeypatch, fake_sd, fake_mp)
    _stub_qd_transport(monkeypatch, {"w.0": torch.zeros(8)}, role="clip")

    session = _stage_session("clip", "/fake/qwen_3_4b.safetensors")

    with pytest.raises(RuntimeError, match="(?i)patcher|dynamic|legacy|aimdo"):
        asyncio.run(gs.golden_clip_load(session))
    assert constructed["count"] == 0


def test_clip_load_preflight_accepts_dynamic_patcher_and_reaches_construction(monkeypatch):
    """When CoreModelPatcher IS ModelPatcherDynamic the preflight passes and
    CLIP construction is reached (proven by a sentinel raised inside the fake
    constructor — no real comfy-aimdo required)."""
    import types

    import torch

    fake_mp = _fake_model_patcher_module(dynamic=True)

    class _ConstructionProbe(RuntimeError):
        pass

    def _construct(*args, **kwargs):
        raise _ConstructionProbe("preflight_passed_probe")

    fake_sd = types.ModuleType("comfy.sd")
    fake_sd.load_text_encoder_state_dicts = _construct
    fake_sd.CLIPType = types.SimpleNamespace(LUMINA2="LUMINA2")
    _install_fake_comfy(monkeypatch, fake_sd, fake_mp)
    _stub_qd_transport(monkeypatch, {"w.0": torch.zeros(8)}, role="clip")

    session = _stage_session("clip", "/fake/qwen_3_4b.safetensors")

    with pytest.raises(_ConstructionProbe):
        asyncio.run(gs.golden_clip_load(session))


@pytest.mark.skipif(
    not __import__("torch").cuda.is_available(),
    reason="golden_vae_load resolves the current CUDA device before construction",
)
def test_vae_load_preflight_rejects_legacy_core_model_patcher_before_vae_construction(monkeypatch):
    """Legacy CoreModelPatcher must fail closed BEFORE any VAE construction."""
    import types

    constructed = {"count": 0}

    class _MustNotConstruct:
        def __init__(self, *args, **kwargs):
            constructed["count"] += 1

    fake_sd = types.SimpleNamespace(VAE=_MustNotConstruct)
    fake_mp = _fake_model_patcher_module(dynamic=False)
    _install_fake_comfy(monkeypatch, fake_sd, fake_mp)
    _stub_qd_transport(monkeypatch, {}, role="vae")

    session = _stage_session("vae", "/fake/ae.safetensors")

    with pytest.raises(RuntimeError, match="(?i)patcher|dynamic|legacy|aimdo"):
        asyncio.run(gs.golden_vae_load(session))
    assert constructed["count"] == 0


@pytest.mark.skipif(
    not __import__("torch").cuda.is_available(),
    reason="golden_vae_load resolves the current CUDA device before construction",
)
def test_vae_load_preflight_accepts_dynamic_patcher_and_reaches_vae_construction(monkeypatch):
    """    CoreModelPatcher is ModelPatcherDynamic -> preflight passes and VAE
    construction is reached (sentinel probe inside the fake constructor)."""
    import types

    import torch

    class _ConstructionProbe(RuntimeError):
        pass

    class _ProbeVAE:
        def __init__(self, *args, **kwargs):
            raise _ConstructionProbe("preflight_passed_probe")

    fake_sd = types.SimpleNamespace(VAE=_ProbeVAE)
    fake_mp = _fake_model_patcher_module(dynamic=True)
    _install_fake_comfy(monkeypatch, fake_sd, fake_mp)
    # nonempty uniform QD view: the sentinel path still derives a source dtype
    _stub_qd_transport(monkeypatch, {"w.0": torch.zeros(8)}, role="vae")

    session = _stage_session("vae", "/fake/ae.safetensors")

    with pytest.raises(_ConstructionProbe):
        asyncio.run(gs.golden_vae_load(session))


# ── 19. Shared fakes for explicit loader-argument contracts ─────────────────


def _stub_qd_transport(monkeypatch, views, *, role):
    """Replace read_file_qd_gpu with a counting stub returning *views*."""
    owner = gs.GoldenQDOwner(gpu_buf=None, slots=[], device="cuda:0", role=role)
    calls = {"read": 0}

    def fake_read(path, *, role=role, qd=4, block_bytes=0):
        calls["read"] += 1
        return {
            "sd": dict(views),
            "owner": owner,
            "header_metadata": None,
            "stats": {
                "gpu_bytes": 48,
                "source_read_count": 1,
                "h2d_completed_bytes": 48,
                "quiescence": {
                    "workers_joined": True,
                    "h2d_events_waited": True,
                    "copies_complete": True,
                    "operation_live": False,
                },
            },
        }

    monkeypatch.setattr(gs, "read_file_qd_gpu", fake_read)
    return owner, calls


def _stage_session(path_key: str, path: str) -> gs.GoldenSession:
    session = object.__new__(gs.GoldenSession)
    session.recorder = gs.GoldenTelemetryRecorder()
    session.model_paths = {path_key: path}
    session.contract = gs.GoldenWorkflowContract()
    # ClipLoadSpec contract: loaders resolve from these, init bypassed above.
    session.clip_paths = [path] if path_key == "clip" else []
    session.clip_owners = []
    session.clip_owner = None
    session.clip = None
    session.vae_owner = None
    session.vae = None
    return session


def _cuda_bf16_views(count=3):
    """CUDA bf16 QD views carved from one shared buffer (16 bytes = 8 bf16)."""
    import torch

    flat = torch.zeros(count * 16, dtype=torch.uint8, device="cuda")
    views = {f"w.{i}": flat[i * 16 : (i + 1) * 16].view(torch.bfloat16).view([8]) for i in range(count)}
    return flat, views


def _alias_view(flat, index):
    """A distinct tensor aliasing the SAME storage offset as view w.<index>."""
    import torch

    return flat[index * 16 : (index + 1) * 16].view(torch.bfloat16).view([8])


class _AliasModule(_torch.nn.Module):
    """Real torch.nn.Module tree whose parameters share storage with the QD
    views.  Production scope selection traverses named_modules() /
    named_parameters() / named_buffers(), so this must be a genuine Module.
    Registration names are sanitized ('.' is forbidden by torch); the
    pointer aliases and every expectation are unaffected."""

    def __init__(self, tensors):
        super().__init__()
        for index, tensor in enumerate(tensors.values()):
            self.register_parameter(
                f"p_{index}", _torch.nn.Parameter(tensor, requires_grad=False)
            )


# ── 20. Native CLIP loader contract (model_options + pointer preservation) ──


@pytest.mark.skipif(
    not __import__("torch").cuda.is_available(),
    reason="requires CUDA for synthetic QD views",
)
def test_clip_loader_fake_asserts_native_model_options_and_state_dict_pointer_preservation(monkeypatch):
    """The CLIP stage must pass native model_options (empty for the canonical
    path), use a scoped meta initial-device seam, retain the dynamic patcher on
    the returned clip, and pass a COPY of the state dict whose tensors preserve
    the QD view data_ptrs exactly (upstream pops keys from the dict it receives)."""
    import types

    import torch

    flat, views = _cuda_bf16_views(3)
    owner, _calls = _stub_qd_transport(monkeypatch, views, role="clip")
    fake_mp = _fake_model_patcher_module(dynamic=True)
    fake_mm = types.ModuleType("comfy.model_management")
    native_initial_device = lambda *args, **kwargs: torch.device("cpu")
    fake_mm.text_encoder_initial_device = native_initial_device

    captured = {}

    def fake_load_text_encoder_state_dicts(
        state_dicts, embedding_directory=None, clip_type=None, model_options=None, disable_dynamic=False
    ):
        mo = model_options or {}
        sd_copy = state_dicts[0]
        captured["model_options"] = mo
        captured["initial_device"] = fake_mm.text_encoder_initial_device(
            torch.device("cuda"), torch.device("cpu"), 123
        )
        captured["is_copy"] = sd_copy is not views
        captured["ptr_preserved"] = set(sd_copy) == set(views) and all(
            int(t.data_ptr()) == int(views[k].data_ptr()) for k, t in sd_copy.items()
        )
        return types.SimpleNamespace(
            cond_stage_model=_AliasModule({f"w.{i}": _alias_view(flat, i) for i in range(len(views))}),
            patcher=fake_mp.CoreModelPatcher(),
            tokenize=lambda *a, **k: {"tokens": True},
            encode_from_tokens_scheduled=lambda *a, **k: "cond",
        )

    fake_sd = types.ModuleType("comfy.sd")
    fake_sd.load_text_encoder_state_dicts = fake_load_text_encoder_state_dicts
    fake_sd.CLIPType = types.SimpleNamespace(LUMINA2="LUMINA2")
    _install_fake_comfy(monkeypatch, fake_sd, fake_mp, fake_mm)

    session = _stage_session("clip", "/fake/qwen_3_4b.safetensors")
    clip = asyncio.run(gs.golden_clip_load(session))

    mo = captured["model_options"]
    assert captured["is_copy"], "state dict passed upstream must be a copy of the QD view dict"
    assert captured["ptr_preserved"], "state-dict copy must preserve every tensor data_ptr"
    # Native model_options contract and scoped initial-device seam.
    assert mo == {}
    assert captured["initial_device"] == torch.device("meta")
    assert fake_mm.text_encoder_initial_device is native_initial_device
    # dynamic patcher retained on the published clip
    assert fake_mp.CoreModelPatcher is fake_mp.ModelPatcherDynamic
    assert clip.patcher.__class__ is fake_mp.CoreModelPatcher
    assert getattr(clip, "_golden_qd_owner") is owner
    assert session.clip is clip
    event_names = [e["name"] for e in session.recorder.events]
    assert "clip_adoption_identity" in event_names
    assert "clip_published" in event_names


# ── 21. Explicit VAE loader contract (source dtype/device + dynamic patcher) ─


@pytest.mark.skipif(not __import__("torch").cuda.is_available(), reason="requires CUDA")
def test_vae_loader_fake_asserts_explicit_source_dtype_device_and_dynamic_patcher(monkeypatch):
    """The VAE stage must construct comfy.sd.VAE with an EXPLICIT source dtype
    and the current CUDA device, retain the dynamic patcher, and keep the
    one-header/one-payload proof: exactly one transport read and zero stage
    header rereads."""
    import types

    import torch

    flat, views = _cuda_bf16_views(3)
    owner, calls = _stub_qd_transport(monkeypatch, views, role="vae")
    fake_mp = _fake_model_patcher_module(dynamic=True)

    parse_calls = {"n": 0}

    def counting_parse(path):
        parse_calls["n"] += 1
        return {"status": "ok", "header": {}, "data_start": 8, "total_data_bytes": 48}

    monkeypatch.setattr(gs, "parse_safetensors_header", counting_parse)

    captured = {}

    class FakeVAE:
        def __init__(self, sd=None, device=None, config=None, dtype=None, metadata=None):
            captured.update(sd=sd, device=device, dtype=dtype, metadata=metadata)
            self.patcher = fake_mp.CoreModelPatcher()
            self.first_stage_model = _AliasModule(
                {f"w.{i}": _alias_view(flat, i) for i in range(len(views))}
            )
            self.working_dtypes = [torch.bfloat16]

        def throw_exception_if_invalid(self):
            pass

    fake_sd = types.SimpleNamespace(VAE=FakeVAE)
    _install_fake_comfy(monkeypatch, fake_sd, fake_mp)

    session = _stage_session("vae", "/fake/ae.safetensors")
    vae = asyncio.run(gs.golden_vae_load(session))

    # explicit source dtype/device contract
    assert captured["dtype"] == torch.bfloat16
    assert str(captured["device"]) == f"cuda:{torch.cuda.current_device()}"
    assert captured["sd"] is not views and set(captured["sd"]) == set(views)
    # dynamic patcher retained
    assert fake_mp.CoreModelPatcher is fake_mp.ModelPatcherDynamic
    assert vae.patcher.__class__ is fake_mp.CoreModelPatcher
    assert getattr(vae, "_golden_qd_owner") is owner
    assert session.vae is vae
    # one-header/one-payload: single transport read, no stage reread
    assert calls["read"] == 1
    assert parse_calls["n"] == 0


def test_sampler_prepare_only_inspects_nodes_executed_during_prep():
    class FakeRunner:
        def __init__(self):
            self.executed = [{
                "node_id": "67",
                "class_type": "CLIPTextEncode",
                "stage_class": "clip_forward",
            }]

        def seed(self, _node_id, _outputs):
            pass

        def begin_scope(self, _allowed):
            pass

        def end_scope(self):
            pass

        async def run_closure(self, _target_id, *, include_target):
            assert include_target is False
            self.executed.append({
                "node_id": "prep",
                "class_type": "PrepareNode",
                "stage_class": "prepare",
            })

    session = object.__new__(gs.GoldenSession)
    session.recorder = gs.GoldenTelemetryRecorder()
    session.runner = FakeRunner()
    session.node_map = gs.GoldenNodeMap("66", "67", "4", "3", "1242", "1178")
    session.clip = object()
    session.conditioning = object()
    session.patcher = object()

    session.recorder.begin_stage("golden_unet_load")
    session.recorder.end_stage("golden_unet_load", ready=True)
    details = asyncio.run(gs.golden_sampler_prepare(session))

    assert details["executed_nodes"] == ["prep"]
    assert session.recorder.intervals["golden_sampler_prepare"].details["executed_nodes"] == ["prep"]
