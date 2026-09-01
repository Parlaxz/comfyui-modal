"""Generic capability-based fast hydration for ComfyUI CLIP-style text
encoders (standalone safetensors, first-cold use on Modal-like storage).

The helper is GENERIC: it never inspects a model name (no "if model == Qwen"
style gates).  Instead it derives, for an arbitrary candidate, a set of
capabilities from the state dict and the target module, and answers:

    eligibility                = bool
    reason                     = str
    preferred hydration mode   = str
    fallback mode              = str

Hydration modes (candidate paths A-F from the Batch D3 design):

    cpu_standard      (A) current Comfy CPU mmap -> plain load_state_dict
                          (copy_ semantics, parameter identity preserved).
                          Always available; the fallback for everything.
    safetensors_cuda  (B) safetensors.load_file(device="cuda") + assign=True.
                          Host-staged internally (one pinned/pageable copy),
                          NOT zero-copy; result tensors are ordinary torch
                          tensors with safe lifetimes.
    fastsafetensors   (C) direct-to-GPU read via fastsafetensors
                          SafeTensorsFileLoader.  Tensors are zero-copy views
                          over an internal GPU buffer; the loader+buffer MUST
                          outlive the tensors and close() must never be
                          called while tensors are live (owner attached to
                          the model).
    pinned_staging    (D) bounded queue-depth read -> pinned host staging ->
                          async H2D (non_blocking) under a global semaphore.
    meta_assign       (E) meta-constructed model structure + assign=True:
                          checkpoint tensors BECOME the parameters
                          (zero-copy; checkpoint dtype/device win).
    (F) multiple files under ONE global I/O budget is provided by
        plan_qd_budget() / hydrate_many().

assign=True semantics (verified against PyTorch source): setattr replaces the
module parameter with the checkpoint tensor wrapped as nn.Parameter;
requires_grad is taken from the module; shapes must match and dtypes must
match (no conversion is performed), so assign-compatibility is a gate.

Quantization/custom-op markers that invalidate direct-GPU hydration:
"*comfy_quant" keys, "scaled_fp8" keys, safetensors "_quantization_metadata".
Key transforms that create new tensors (in_proj splitting, text_projection
transpose) are detected by gate_transform_identity and reported as a
transform cost — they do not block hydration, but they rule out the
zero-copy direct modes.

DEFAULT_QD_BASE is a LOCAL probe default (this host's NVMe measured
QD8 preadv = 40.72 GB/s in the project's unet_qd_probe battery).  No final
queue depth is hardcoded: it MUST be re-tuned against remote volume storage
before production use.

Only dependency is torch; fastsafetensors is imported optionally.
"""

from __future__ import annotations

import concurrent.futures
import functools
import importlib.util
import os
import threading
import time

import torch
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, cast

SUPPORTED_DTYPES = (torch.float16, torch.float32, torch.bfloat16)
DEFAULT_QD_BASE = 8
_PATCH_STATE_KEYS = (
    "patches",
    "lora",
    "lora_weights",
    "model_patches",
    "model_patch_replace",
    "control_after_generate",
)
_FASTSAFE_OWNER_ATTR = "_clip_fh_fastsafe_owner"
_FASTSAFE_MAX_COPY_BLOCK_BYTES = 1 << 30
_FASTSAFE_THREADS = 16
_SUPER_CHAIN_MAX_DEPTH = 4
_TOKENIZER_BLOB_KEYS = ("spiece_model", "tekken_model", "tokenizer_json")

HYDRATION_MODES = {
    "cpu_standard": "Current Comfy behavior: CPU mmap tensors bound with plain "
    "load_state_dict (copy_ semantics, parameter identity preserved). Always "
    "available; the fallback for every candidate.",
    "safetensors_cuda": "safetensors.load_file(device='cuda') then "
    "load_state_dict(assign=True). Host-staged internally (not zero-copy); "
    "resulting CUDA tensors are ordinary torch tensors with safe lifetimes.",
    "fastsafetensors": "Direct-to-GPU read via fastsafetensors "
    "SafeTensorsFileLoader. Zero-copy views over an internal GPU buffer; "
    "owner (loader+buffer) is attached to the model so GPU fragment memory "
    "dies with the model; close() is only ever called on failure.",
    "staged_safetensors": "Optional Phase-E staged safetensors read and H2D "
        "pipeline; committed tensors are bound through the generic CLIP "
        "assign=True dispatch contract and staged storage is owner-retained.",
    "pinned_staging": "Bounded queue-depth read into pinned host staging with "
    "async (non_blocking) H2D under a global semaphore.",
    "meta_assign": "Meta-constructed model structure + load_state_dict(assign=True): "
    "checkpoint tensors become the parameters (zero-copy).",
}


@dataclass
class GateResult:
    passed: bool
    detail: str


@dataclass
class CandidateAssessment:
    eligible: bool
    reason: str
    preferred_hydration_mode: str
    fallback_hydration_mode: str
    gates: dict[str, GateResult] = field(default_factory=dict)
    capabilities: dict[str, bool] = field(default_factory=dict)


@dataclass
class HydrationReport:
    mode: str
    wall_ms: float
    phases: dict[str, float] = field(default_factory=dict)
    peak_cuda_alloc_delta_bytes: Optional[int] = None
    peak_rss_delta_bytes: Optional[float] = None
    zero_copy: bool = False
    zero_copy_evidence: str = ""
    notes: list[str] = field(default_factory=list)


@dataclass
class BudgetPlan:
    qd_base: int
    n_files: int
    per_file_qd: int
    total_cap: int
    policy_note: str


@dataclass
class HydrateManyResult:
    name: str
    model: Any
    report: HydrationReport
    assessment: Optional[CandidateAssessment]


# ── capability gates ───────────────────────────────────────────────────────


def gate_plain_tensor_storage(sd: dict) -> GateResult:
    non_tensor = [k for k, v in sd.items() if not isinstance(v, torch.Tensor)]
    if not non_tensor:
        return GateResult(True, f"{len(sd)} entries, all plain torch.Tensor")
    return GateResult(
        False,
        f"non-tensor entries ({len(non_tensor)}): {non_tensor[:8]} — e.g. "
        "tokenizer blobs consumed before binding; strip them before the "
        "weight bind step",
    )


def gate_uniform_dtype(sd: dict, supported: tuple = SUPPORTED_DTYPES) -> GateResult:
    dtypes = {v.dtype for v in sd.values() if isinstance(v, torch.Tensor)}
    if not dtypes:
        return GateResult(False, "no tensor entries in state dict")
    if len(dtypes) > 1:
        return GateResult(
            False,
            f"mixed dtypes {sorted(str(d) for d in dtypes)} — assign requires "
            "a single uniform dtype (no conversion is performed)",
        )
    (dt,) = dtypes
    if dt not in supported:
        return GateResult(
            False,
            f"dtype {dt} not in supported set {[str(d) for d in supported]}",
        )
    return GateResult(True, f"uniform dtype {dt}")


def gate_no_quant_transform(sd: dict, metadata: Optional[dict] = None) -> GateResult:
    bad = [k for k in sd if "comfy_quant" in k or "scaled_fp8" in k]
    if metadata and metadata.get("_quantization_metadata"):
        bad.append("_quantization_metadata")
    if not bad:
        return GateResult(True, "no quantization / custom-op markers present")
    return GateResult(
        False,
        f"quantization/custom-op markers present: {bad} — direct-GPU bind "
        "cannot satisfy these transforms",
    )


def gate_transform_identity(raw_sd: dict, transformed_sd: dict) -> GateResult:
    renamed = [k for k in transformed_sd if k not in raw_sd]
    dropped = [k for k in raw_sd if k not in transformed_sd]
    new_tensors = []
    for k in transformed_sd:
        if k in raw_sd:
            a = raw_sd[k]
            b = transformed_sd[k]
            if not (
                isinstance(a, torch.Tensor)
                and isinstance(b, torch.Tensor)
                and a.data_ptr() == b.data_ptr()
                and a.shape == b.shape
                and a.dtype == b.dtype
            ):
                new_tensors.append(k)
    if not renamed and not new_tensors:
        return GateResult(True, "transform is identity: no renamed keys, no new tensors")
    return GateResult(
        False,
        "transform is non-identity: renamed_keys="
        f"{renamed[:8]} new_tensor_keys={new_tensors[:8]} dropped_keys={dropped[:8]} "
        "(transform cost — direct zero-copy GPU modes ruled out, "
        "assign-based modes still usable)",
    )


def gate_assign_compatible(model: Any, sd: dict) -> GateResult:
    msd = model.state_dict()
    matched = 0
    missing = 0
    unexpected = 0
    shape_mismatch = 0
    dtype_mismatch = 0
    for k, p in msd.items():
        if k in sd:
            s = sd[k]
            if isinstance(s, torch.Tensor):
                if p.shape == s.shape:
                    if p.dtype == s.dtype:
                        matched += 1
                    else:
                        dtype_mismatch += 1
                else:
                    shape_mismatch += 1
            else:
                unexpected += 1
        else:
            missing += 1
    for k in sd:
        if k not in msd:
            unexpected += 1
    problems = []
    if shape_mismatch:
        problems.append(f"{shape_mismatch} shape mismatches")
    if dtype_mismatch:
        problems.append(f"{dtype_mismatch} dtype mismatches (assign does not convert)")
    passed = matched > 0 and not problems
    detail = (
        f"{matched} matched, {missing} missing, {unexpected} unexpected"
        + (f"; " + "; ".join(problems) if problems else "")
        + (" (strict=False semantics: missing/unexpected are warnings)" if passed else "")
    )
    return GateResult(passed, detail)


def gate_meta_compatible(model: Any) -> GateResult:
    params = list(model.parameters())
    if not params:
        return GateResult(False, "model has no parameters")
    off_meta = [p for p in params if p.device.type != "meta"]
    if not off_meta:
        return GateResult(True, f"all {len(params)} parameters on meta device")
    return GateResult(
        False,
        f"{len(off_meta)}/{len(params)} parameters NOT on meta device "
        "(structure was materialized; meta_assign still works but loses the "
        "skip-alloc advantage)",
    )


def gate_direct_cuda_compatible(sd: dict, cuda_ok: Optional[bool] = None) -> GateResult:
    ok = torch.cuda.is_available() if cuda_ok is None else bool(cuda_ok)
    dtypes = {v.dtype for v in sd.values() if isinstance(v, torch.Tensor)}
    dtype_ok = dtypes <= set(SUPPORTED_DTYPES)
    if ok and dtype_ok:
        return GateResult(True, f"CUDA available ({torch.cuda.get_device_name(0)})")
    if not ok:
        return GateResult(False, "CUDA not available")
    return GateResult(False, f"dtypes {sorted(str(d) for d in dtypes)} not directly loadable to CUDA")


def gate_patch_state_absent(model_options: Optional[dict]) -> GateResult:
    if not model_options:
        return GateResult(True, "no model_options")
    found = [k for k in _PATCH_STATE_KEYS if k in model_options]
    if not found:
        return GateResult(True, f"model_options present without patch keys {list(_PATCH_STATE_KEYS)}")
    return GateResult(
        True,
        f"patch/LoRA state present: {found} — applied downstream at "
        "patch_model() time, does not block direct hydration, but the model "
        "will be mutated after the bind",
    )


# ── assessment ─────────────────────────────────────────────────────────────


def assess_candidate(
    sd: dict,
    model: Any,
    *,
    model_options: Optional[dict] = None,
    transform: Optional[Callable[[dict], dict]] = None,
    metadata: Optional[dict] = None,
    cuda_ok: Optional[bool] = None,
    file_path: Optional[Any] = None,
) -> CandidateAssessment:
    g_storage = gate_plain_tensor_storage(sd)
    g_dtype = gate_uniform_dtype(sd)
    g_quant = gate_no_quant_transform(sd, metadata)
    transformed = transform(sd) if transform is not None else dict(sd)
    g_identity = gate_transform_identity(sd, transformed)
    g_assign = gate_assign_compatible(model, transformed)
    g_meta = gate_meta_compatible(model)
    g_cuda = gate_direct_cuda_compatible(sd, cuda_ok)
    g_patch = gate_patch_state_absent(model_options)

    eligible = (
        g_storage.passed
        and g_dtype.passed
        and g_quant.passed
        and g_assign.passed
    )

    has_path = file_path is not None
    fastsafe_ok = _fastsafe_module() is not None
    preferred = "cpu_standard"
    if eligible:
        if g_cuda.passed and g_identity.passed and g_assign.passed and has_path:
            if fastsafe_ok:
                preferred = "fastsafetensors"
            else:
                preferred = "safetensors_cuda"
        elif g_meta.passed:
            preferred = "meta_assign"
        else:
            preferred = "cpu_standard"

    if eligible:
        reasons = []
        if g_identity.passed:
            reasons.append("identity transform")
        else:
            reasons.append("non-identity transform (reported cost)")
        if g_meta.passed:
            reasons.append("meta structure")
        if g_cuda.passed:
            reasons.append("direct-CUDA capable")
        if "patch/LoRA" in g_patch.detail:
            reasons.append("patch state present (downstream)")
        reason = (
            f"eligible: {', '.join(reasons)}; preferred {preferred} with "
            "zero-copy assign"
        )
    else:
        failed = [
            name
            for name, g in (
                ("plain_tensor_storage", g_storage),
                ("uniform_dtype", g_dtype),
                ("no_quant_transform", g_quant),
                ("assign_compatible", g_assign),
            )
            if not g.passed
        ]
        reason = (
            f"not eligible for direct hydration: gate(s) {failed} failed "
            f"({g_assign.detail}); fallback cpu_standard preserves current "
            "Comfy behavior unchanged"
        )

    capabilities = {
        "plain_tensor_storage": g_storage.passed,
        "uniform_dtype": g_dtype.passed,
        "no_quant_transform": g_quant.passed,
        "transform_identity": g_identity.passed,
        "transform_new_tensors": not g_identity.passed,
        "assign_compatible": g_assign.passed,
        "meta_compatible": g_meta.passed,
        "direct_cuda_compatible": g_cuda.passed,
        "single_file": True,
        "patch_state_absent": "patch/LoRA" not in g_patch.detail,
        "dtype_compatible": g_assign.passed,
    }

    return CandidateAssessment(
        eligible=eligible,
        reason=reason,
        preferred_hydration_mode=preferred,
        fallback_hydration_mode="cpu_standard",
        gates={
            "plain_tensor_storage": g_storage,
            "uniform_dtype": g_dtype,
            "no_quant_transform": g_quant,
            "transform_identity": g_identity,
            "assign_compatible": g_assign,
            "meta_compatible": g_meta,
            "direct_cuda_compatible": g_cuda,
            "patch_state_absent": g_patch,
        },
        capabilities=capabilities,
    )


# ── hydration modes ────────────────────────────────────────────────────────


def _cuda_peak_delta(baseline_alloc: Optional[int]) -> Optional[int]:
    if baseline_alloc is None or not torch.cuda.is_available():
        return None
    try:
        peak = torch.cuda.max_memory_allocated()
        return max(int(peak - int(baseline_alloc)), 0)
    except Exception:
        return None


_PSUTIL_MOD = None


def _psutil_module():
    global _PSUTIL_MOD
    if _PSUTIL_MOD is None:
        _PSUTIL_MOD = (
            importlib.import_module("psutil")
            if importlib.util.find_spec("psutil") is not None
            else False
        )
    return _PSUTIL_MOD or None


def _rss_mb() -> Optional[float]:
    mod = _psutil_module()
    if mod is None:
        return None
    try:
        return float(mod.Process().memory_info().rss) / 1048576.0
    except Exception:
        return None


def _rss_delta_mb(before: Optional[float]) -> Optional[float]:
    if before is None:
        return None
    after = _rss_mb()
    if after is None:
        return None
    return round(after - before, 3)


def _cuda_baseline() -> Optional[int]:
    if not torch.cuda.is_available():
        return None
    try:
        torch.cuda.reset_peak_memory_stats()
        return int(torch.cuda.memory_allocated())
    except Exception:
        return None


def _zero_copy_evidence(source: dict, model: Any, sample_limit: int = 8) -> tuple[bool, str]:
    sd = model.state_dict()
    keys = [k for k in source if k in sd and isinstance(source[k], torch.Tensor)]
    if not keys:
        return False, "no shared keys to prove"
    sample = keys[:sample_limit]
    matched = 0
    for k in sample:
        s = source[k]
        d = sd[k]
        if (
            s.data_ptr() == d.data_ptr()
            and s.shape == d.shape
            and s.dtype == d.dtype
            and s.untyped_storage().data_ptr() == d.untyped_storage().data_ptr()
        ):
            matched += 1
    ok = matched == len(sample)
    evidence = (
        f"zero-copy: {matched}/{len(sample)} sampled keys share storage with "
        f"the source tensors (e.g. {sample[0] if sample else 'n/a'})"
    )
    return ok, evidence


def hydrate_cpu_standard(model: Any, sd: dict, *, strict: bool = False) -> tuple[Any, HydrationReport]:
    t0 = time.perf_counter()
    baseline = _cuda_baseline()
    rss_before = _rss_mb()
    before = {k: p.data_ptr() for k, p in model.state_dict().items()}
    model.load_state_dict(sd, strict=strict)
    after = {k: p.data_ptr() for k, p in model.state_dict().items()}
    identity_preserved = bool(before) and all(before[k] == after[k] for k in before)
    if not identity_preserved:
        raise AssertionError("cpu_standard fallback changed parameter identity — Comfy semantics broken")
    wall = (time.perf_counter() - t0) * 1000.0
    report = HydrationReport(
        mode="cpu_standard",
        wall_ms=round(wall, 3),
        phases={"bind_ms": round(wall, 3)},
        peak_cuda_alloc_delta_bytes=_cuda_peak_delta(baseline),
        peak_rss_delta_bytes=_rss_delta_mb(rss_before),
        zero_copy=False,
        zero_copy_evidence="copy_ semantics: destination parameter storage is reused (identity preserved), values copied",
        notes=[
            "exactly current Comfy behavior: load_state_dict(strict=False) "
            "with CPU tensors; parameter identity preserved; no device move"
        ],
    )
    return model, report


def hydrate_meta_assign(model: Any, sd: dict) -> tuple[Any, HydrationReport]:
    t0 = time.perf_counter()
    baseline = _cuda_baseline()
    rss_before = _rss_mb()
    model.load_state_dict(sd, strict=False, assign=True)
    torch.cuda.synchronize() if torch.cuda.is_available() else None
    wall = (time.perf_counter() - t0) * 1000.0
    ok, evidence = _zero_copy_evidence(sd, model)
    report = HydrationReport(
        mode="meta_assign",
        wall_ms=round(wall, 3),
        phases={"bind_ms": round(wall, 3)},
        peak_cuda_alloc_delta_bytes=_cuda_peak_delta(baseline),
        peak_rss_delta_bytes=_rss_delta_mb(rss_before),
        zero_copy=ok,
        zero_copy_evidence=evidence,
        notes=[
            "checkpoint tensors became the parameters via assign=True; "
            "no duplicate CPU payload; no allocation if sd tensors were "
            "already on the target device"
        ],
    )
    return model, report


def hydrate_safetensors_cuda(
    file_path: Any, model: Any, *, assign: bool = True
) -> tuple[Any, HydrationReport]:
    import safetensors.torch

    baseline = _cuda_baseline()
    rss_before = _rss_mb()
    t_load = time.perf_counter()
    sd = safetensors.torch.load_file(str(file_path), device="cuda")
    load_ms = (time.perf_counter() - t_load) * 1000.0
    t_bind = time.perf_counter()
    model.load_state_dict(sd, strict=False, assign=assign)
    bind_ms = (time.perf_counter() - t_bind) * 1000.0
    t_sync = time.perf_counter()
    torch.cuda.synchronize()
    sync_ms = (time.perf_counter() - t_sync) * 1000.0
    wall = round(load_ms + bind_ms + sync_ms, 3)
    ok, evidence = _zero_copy_evidence(sd, model)
    report = HydrationReport(
        mode="safetensors_cuda",
        wall_ms=wall,
        phases={"load_gpu_ms": round(load_ms, 3), "bind_ms": round(bind_ms, 3), "sync_ms": round(sync_ms, 3)},
        peak_cuda_alloc_delta_bytes=_cuda_peak_delta(baseline),
        peak_rss_delta_bytes=_rss_delta_mb(rss_before),
        zero_copy=ok,
        zero_copy_evidence=evidence,
        notes=[
            "safetensors.load_file(device='cuda') stages through host memory "
            "internally (one pinned/pageable copy + DMA) — not zero-copy "
            "read, but the file never lands as a full CPU tensor set; "
            "resulting CUDA tensors are ordinary torch tensors with safe "
            "lifetimes"
        ],
    )
    return model, report


def _fastsafe_module():
    try:
        if importlib.util.find_spec("fastsafetensors") is not None:
            import fastsafetensors

            return fastsafetensors
    except Exception:
        return None
    return None


class _FastsafeOwner:
    __slots__ = ("loader", "fb")

    def __init__(self, loader: Any, fb: Any):
        self.loader = loader
        self.fb = fb


def hydrate_fastsafetensors(
    file_path: Any, model: Any, *, max_threads: int = _FASTSAFE_THREADS
) -> tuple[Any, HydrationReport]:
    mod = _fastsafe_module()
    if mod is None:
        raise RuntimeError(
            "fastsafetensors is not installed — pip install fastsafetensors; "
            "fall back to safetensors_cuda or cpu_standard"
        )
    cls = getattr(mod, "SafeTensorsFileLoader", None)
    if not callable(cls):
        raise RuntimeError("fastsafetensors.SafeTensorsFileLoader unavailable")
    from . import gpu_lane_coordination as _gpu_coord

    baseline = _cuda_baseline()
    rss_before = _rss_mb()
    t_setup = time.perf_counter()
    device_str = f"cuda:{torch.cuda.current_device()}"
    loader = cast(Any, cls(None, device_str, max_threads=max_threads, nogds=True, disable_cache=True))
    copy_event = None
    scoped_readiness = _gpu_coord.scoped_cuda_readiness_enabled()
    try:
        loader.add_filenames({0: [str(file_path)]})
        setup_ms = (time.perf_counter() - t_setup) * 1000.0
        t_copy = time.perf_counter()
        fb = loader.copy_files_to_device(
            use_buf_register=False,
            max_copy_block_size=_FASTSAFE_MAX_COPY_BLOCK_BYTES,
        )
        if scoped_readiness:
            copy_event = _gpu_coord.record_copy_event("clip")
            if copy_event is None:
                raise RuntimeError("scoped_copy_event_unavailable")
        copy_ms = (time.perf_counter() - t_copy) * 1000.0
        t_inst = time.perf_counter()
        keys = list(loader.get_keys())
        sd = {k: fb.get_tensor(k) for k in keys}
        inst_ms = (time.perf_counter() - t_inst) * 1000.0
        t_bind = time.perf_counter()
        model.load_state_dict(sd, strict=False, assign=True)
        bind_ms = (time.perf_counter() - t_bind) * 1000.0
        t_sync = time.perf_counter()
        if scoped_readiness:
            if not _gpu_coord.wait_copy_event("clip", copy_event):
                raise RuntimeError("scoped_copy_event_wait_failed")
        else:
            _gpu_coord.record_device_wide_sync("clip")
            torch.cuda.synchronize()
        sync_ms = (time.perf_counter() - t_sync) * 1000.0
        setattr(model, _FASTSAFE_OWNER_ATTR, _FastsafeOwner(loader, fb))
        ok, evidence = _zero_copy_evidence(sd, model)
        report = HydrationReport(
            mode="fastsafetensors",
            wall_ms=round(setup_ms + copy_ms + inst_ms + bind_ms + sync_ms, 3),
            phases={
                "setup_ms": round(setup_ms, 3),
                "copy_gpu_ms": round(copy_ms, 3),
                "instantiate_ms": round(inst_ms, 3),
                "bind_ms": round(bind_ms, 3),
                "sync_ms": round(sync_ms, 3),
            },
            peak_cuda_alloc_delta_bytes=_cuda_peak_delta(baseline),
            peak_rss_delta_bytes=_rss_delta_mb(rss_before),
            zero_copy=ok,
            zero_copy_evidence=evidence,
            notes=[
                "direct-to-GPU read; tensors are zero-copy views over an "
                "internal GPU buffer; loader+buffer attached to the model as "
                f"{_FASTSAFE_OWNER_ATTR} — GPU fragment memory dies with the "
                "model; close() is never called while tensors are live",
            ],
        )
        return model, report
    except Exception:
        try:
            loader.close()
        except Exception:
            pass
        torch.cuda.empty_cache()
        raise


def hydrate_pinned_staging(
    file_path: Any, model: Any, *, qd: int = 4, chunk_mb: int = 128
) -> tuple[Any, HydrationReport]:
    import safetensors

    if not torch.cuda.is_available():
        raise RuntimeError("pinned_staging requires CUDA")
    qd = max(1, int(qd))
    baseline = _cuda_baseline()
    rss_before = _rss_mb()
    t_read = time.perf_counter()
    sem = threading.Semaphore(qd)

    def _worker(sf: Any, k: str) -> tuple[str, torch.Tensor]:
        with sem:
            cpu_t = sf.get_tensor(k)
            pinned = cpu_t.pin_memory()
            return k, pinned.to("cuda", non_blocking=True)

    with safetensors.safe_open(str(file_path), framework="pt") as sf:
        keys = list(sf.keys())
        with concurrent.futures.ThreadPoolExecutor(max_workers=qd) as ex:
            pairs = list(ex.map(lambda k: _worker(sf, k), keys))
    read_ms = (time.perf_counter() - t_read) * 1000.0
    t_bind = time.perf_counter()
    sd = dict(pairs)
    model.load_state_dict(sd, strict=False, assign=True)
    bind_ms = (time.perf_counter() - t_bind) * 1000.0
    t_sync = time.perf_counter()
    torch.cuda.synchronize()
    sync_ms = (time.perf_counter() - t_sync) * 1000.0
    ok, evidence = _zero_copy_evidence(sd, model)
    report = HydrationReport(
        mode="pinned_staging",
        wall_ms=round(read_ms + bind_ms + sync_ms, 3),
        phases={
            "read_transfer_ms": round(read_ms, 3),
            "bind_ms": round(bind_ms, 3),
            "sync_ms": round(sync_ms, 3),
        },
        peak_cuda_alloc_delta_bytes=_cuda_peak_delta(baseline),
        peak_rss_delta_bytes=_rss_delta_mb(rss_before),
        zero_copy=ok,
        zero_copy_evidence=evidence,
        notes=[
            f"bounded pinned staging: qd={qd} worker transfers under a "
            "global semaphore, per-tensor pin_memory + non_blocking H2D; "
            "staging memory bounded by qd x largest tensor (per-tensor "
            "chunking below the tensor level is a future refinement)",
        ],
    )
    return model, report


_DISPATCH = {
    "cpu_standard": hydrate_cpu_standard,
    "meta_assign": hydrate_meta_assign,
    "safetensors_cuda": hydrate_safetensors_cuda,
    "fastsafetensors": hydrate_fastsafetensors,
    "pinned_staging": hydrate_pinned_staging,
}

_PATH_MODES = ("safetensors_cuda", "fastsafetensors", "pinned_staging")


def hydrate_auto(
    file_path_or_sd: Any,
    model: Any,
    *,
    model_options: Optional[dict] = None,
    transform: Optional[Callable[[dict], dict]] = None,
    metadata: Optional[dict] = None,
) -> tuple[Any, HydrationReport, CandidateAssessment]:
    import safetensors.torch

    has_path = isinstance(file_path_or_sd, (str, os.PathLike))
    if has_path:
        file_path = str(file_path_or_sd)
        sd = safetensors.torch.load_file(file_path, device="cpu")
    else:
        file_path = None
        sd = dict(file_path_or_sd)
    assessment = assess_candidate(
        sd,
        model,
        model_options=model_options,
        transform=transform,
        metadata=metadata,
        file_path=file_path,
    )
    mode = assessment.preferred_hydration_mode
    try:
        if mode == "cpu_standard":
            model, report = hydrate_cpu_standard(model, sd)
        elif mode == "meta_assign":
            model, report = hydrate_meta_assign(model, sd)
        else:
            model, report = _DISPATCH[mode](file_path, model)
        return model, report, assessment
    except Exception as exc:
        model, report = hydrate_cpu_standard(model, sd)
        report.mode = "cpu_standard(fallback)"
        report.notes.append(
            f"preferred mode {mode} failed ({type(exc).__name__}: {str(exc)[:160]}); "
            "fell back to cpu_standard — Comfy default behavior unchanged"
        )
        return model, report, assessment


# ── multiple-file scheduling (mode F) ──────────────────────────────────────


def plan_qd_budget(
    n_files: int, qd_base: int = DEFAULT_QD_BASE, min_per_file: int = 1
) -> BudgetPlan:
    n = max(1, int(n_files))
    base = max(1, int(qd_base))
    per_file = max(int(min_per_file), base // n)
    total_cap = min(n * per_file, base + 2)
    policy_note = (
        f"1 file -> full budget QD{base}; {n} files -> split budget "
        f"(QD{base} // {n} = QD{per_file} per file, clamped to min {int(min_per_file)}), "
        f"total concurrent cap {total_cap}. qd_base={base} is a LOCAL probe "
        "default (this host NVMe: QD8 preadv = 40.72 GB/s); it MUST be "
        "re-tuned against remote volume storage — no final queue depth is "
        "hardcoded without remote A/B evidence."
    )
    return BudgetPlan(
        qd_base=base,
        n_files=n,
        per_file_qd=per_file,
        total_cap=total_cap,
        policy_note=policy_note,
    )


def hydrate_many(
    files: list,
    model_factory: Callable[[str], Any],
    *,
    qd_base: int = DEFAULT_QD_BASE,
    mode: str = "auto",
) -> tuple[list[HydrateManyResult], float]:
    if mode != "auto":
        raise RuntimeError("hydrate_many currently supports mode='auto' only")
    paths = [str(f) for f in files]
    names = [Path(p).stem for p in paths]
    plan = plan_qd_budget(len(paths), qd_base)
    sem = threading.Semaphore(plan.total_cap)
    t0 = time.perf_counter()

    def _run(name: str, path: str) -> HydrateManyResult:
        with sem:
            model = model_factory(name)
            model, report, assessment = hydrate_auto(path, model)
            return HydrateManyResult(name=name, model=model, report=report, assessment=assessment)

    workers = max(1, min(len(paths), plan.total_cap))
    results: list[HydrateManyResult] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        future_map = {ex.submit(_run, n, p): (n, p) for n, p in zip(names, paths)}
        by_index: dict[tuple[str, str], HydrateManyResult] = {}
        for fut in concurrent.futures.as_completed(future_map):
            by_index[future_map[fut]] = fut.result()
        results = [by_index[(n, p)] for n, p in zip(names, paths)]
    total_wall_ms = (time.perf_counter() - t0) * 1000.0
    return results, round(total_wall_ms, 3)


# ── Production API (D3 wiring) ─────────────────────────────────────────────
# Generic, capability-based operations used by clip_fast_hydration_wiring on
# real Comfy CLIP objects.  Everything here only reads generic attributes
# (cond_stage_model, patcher, can_assign_sd convention, named_parameters).

EXCLUDED_WEIGHTS_MARKER = "_comfymodal_clip_fh_excluded_weights"
MANIFEST_ATTR = "_comfymodal_clip_fh_manifest"
HYDRATED_MARKER = "_comfymodal_clip_fh_hydrated"
HYDRATION_FINGERPRINT_ATTR = "_comfymodal_clip_fh_hydration_fingerprint"
DEMAND_WRAPPER_MARKER = "_comfymodal_clip_fh_demand_wrapped"
OWNER_ATTR = "_comfymodal_clip_fh_owner"
STAGED_OWNER_ATTR = "_comfymodal_clip_fh_staged_owner"
GPU_COORDINATION_MARKER = "_comfymodal_gpu_critical_coordination"

MODE_NATIVE = "native_cpu_h2d"
MODE_FASTSAFE = "fastsafetensors_direct_gpu"
MODE_STAGED = "staged_safetensors"
MODE_RESIDENT = "already_resident"
MODE_CACHE_HIT = "conditioning_cache_hit_no_hydration"

# Explicit hydration-state taxonomy (D6 follow-up).  The demand path must
# NEVER treat CPU residency alone as hydration; these labels let telemetry
# distinguish *why* a clip is (or is not) already hydrated:
# EXCLUDED_PLACEHOLDER  — structure exists, physical payload stripped.
# CPU_NATIVE_MATERIALIZED — full checkpoint weights live on CPU (native load
#                           or CPU-assign bind) with no D3 record yet.
# GPU_FAST_HYDRATED      — D3 fastsafetensors GPU buffers assigned, owner kept.
# GPU_NATIVE_LOADED      — native Comfy movement/materialization on GPU.
# INVALID/PARTIAL        — anything else (mixed devices, meta without the
#                           excluded marker, empty structure, etc).
STATE_EXCLUDED_PLACEHOLDER = "EXCLUDED_PLACEHOLDER"
STATE_CPU_NATIVE_MATERIALIZED = "CPU_NATIVE_MATERIALIZED"
STATE_GPU_FAST_HYDRATED = "GPU_FAST_HYDRATED"
STATE_GPU_NATIVE_LOADED = "GPU_NATIVE_LOADED"
STATE_INVALID = "INVALID/PARTIAL"


def strip_clip_weights(clip: Any) -> dict[str, Any]:
    """Replace every parameter of ``clip.cond_stage_model`` with a meta
    tensor of the same shape/dtype/requires_grad, in place.

    Keeps buffers (small, e.g. position_ids) and the whole structure;
    removes only the large physical parameter payload.  Marks the clip with
    EXCLUDED_WEIGHTS_MARKER so validators can tolerate meta parameters.
    Returns JSON-safe stats.
    """
    reset_clip_hydration_for_bind(clip)
    csm = getattr(clip, "cond_stage_model", None)
    if csm is None or not hasattr(csm, "named_parameters"):
        raise RuntimeError("clip has no inspectable cond_stage_model")
    count = 0
    bytes_before = 0
    for name, param in csm.named_parameters():
        bytes_before += int(param.numel()) * int(param.element_size())
        meta = torch.empty(param.shape, dtype=param.dtype, device="meta")
        owner_module = csm
        parts = name.split(".")
        for part in parts[:-1]:
            owner_module = getattr(owner_module, part)
        setattr(owner_module, parts[-1], torch.nn.Parameter(meta, requires_grad=bool(param.requires_grad)))
        count += 1
    setattr(clip, EXCLUDED_WEIGHTS_MARKER, True)
    return {
        "params_replaced": count,
        "payload_bytes_removed": bytes_before,
        "meta": True,
    }


def clip_weights_excluded(clip: Any) -> bool:
    return bool(getattr(clip, EXCLUDED_WEIGHTS_MARKER, False))


def clip_hydrated(clip: Any) -> bool:
    """Marker-only predicate: True iff the D3 hydration marker is set.

    CPU residency alone NEVER satisfies this predicate.  A model whose
    parameters were fully materialized on CPU (e.g. a stripped structure
    restored and natively reloaded) still returns False until an explicit D3
    hydration records the marker.  The demand wrapper must NOT use this as a
    residency check — it distinguishes the actual materialization via
    ``clip_hydration_state`` (CPU_NATIVE_MATERIALIZED vs GPU_*).
    """
    if not bool(getattr(clip, HYDRATED_MARKER, False)):
        return False
    # The marker is only a publish bit.  Re-check the narrow identity facts
    # that make it meaningful before allowing a demand to return success.
    return hydration_claim_valid(clip)


def mark_clip_hydrated(clip: Any) -> None:
    setattr(clip, HYDRATED_MARKER, True)
    try:
        setattr(clip, HYDRATION_FINGERPRINT_ATTR, clip_hydration_fingerprint(clip))
    except Exception:
        # A marker without a proof fingerprint is not reusable.
        setattr(clip, HYDRATED_MARKER, False)


def _storage_identity(param: Any) -> tuple[Any, ...]:
    try:
        storage = param.untyped_storage()
        storage_ptr = int(storage.data_ptr())
    except Exception:
        storage_ptr = None
    try:
        data_ptr = None if bool(getattr(param, "is_meta", False)) else int(param.data_ptr())
    except Exception:
        data_ptr = None
    return (
        id(param),
        storage_ptr,
        data_ptr,
        tuple(int(x) for x in getattr(param, "shape", ())),
        str(getattr(param, "dtype", "")),
        str(getattr(param, "device", "")),
    )


def clip_hydration_fingerprint(clip: Any) -> tuple[Any, ...]:
    """Return the small identity/fingerprint guard for a published claim.

    This intentionally excludes parameter values.  It catches replacement or
    movement of parameter storage and the patch/manual-cast registrations that
    change the meaning of a compute-ready bind, without adding a tensor scan
    to every demand.
    """
    csm = getattr(clip, "cond_stage_model", None)
    params: list[tuple[Any, ...]] = []
    if csm is not None and callable(getattr(csm, "named_parameters", None)):
        for name, param in csm.named_parameters():
            params.append((str(name), *_storage_identity(param)))
    registrations: list[tuple[Any, ...]] = []
    if csm is not None and callable(getattr(csm, "modules", None)):
        for module in csm.modules():
            for attr in ("weight_function", "bias_function"):
                value = getattr(module, attr, None)
                if value is None:
                    continue
                if isinstance(value, (list, tuple)):
                    facts = tuple((type(item).__name__, id(item)) for item in value)
                else:
                    facts = ((type(value).__name__, id(value)),)
                registrations.append((id(module), attr, facts))
            if hasattr(module, "manual_cast_dtype"):
                registrations.append((id(module), "manual_cast_dtype", str(getattr(module, "manual_cast_dtype", None))))
    patcher = getattr(clip, "patcher", None)
    if patcher is not None:
        current_object = getattr(patcher, "current_object", None)
        registrations.append((
            id(patcher),
            "current_object_identity",
            id(current_object) if current_object is not None else None,
        ))
        for attr in ("manual_cast_dtype", "load_device", "offload_device", "current_device"):
            if hasattr(patcher, attr):
                registrations.append((id(patcher), attr, str(getattr(patcher, attr, None))))
    return (tuple(params), tuple(registrations))


def invalidate_stale_hydration_claim(clip: Any) -> bool:
    """Clear a stale marker/generation/callback, returning whether it was stale."""
    if not bool(getattr(clip, HYDRATED_MARKER, False)):
        return False
    expected = getattr(clip, HYDRATION_FINGERPRINT_ATTR, None)
    try:
        current = clip_hydration_fingerprint(clip)
    except Exception:
        current = None
    if expected is not None and current == expected:
        return False
    try:
        reset_clip_hydration_for_bind(clip)
    except Exception:
        setattr(clip, HYDRATED_MARKER, False)
    return True


def hydration_claim_valid(clip: Any) -> bool:
    return not invalidate_stale_hydration_claim(clip)


def reset_clip_hydration_for_bind(clip: Any) -> None:
    """Invalidate all bind-scoped E31 state before replacing parameters.

    A reused outer CLIP object is not evidence of a reused model.  Clear the
    marker, cast generation, and any pending outer-forward callback before a
    new bind so a stale callback can never certify the new storage.
    """
    try:
        setattr(clip, HYDRATED_MARKER, False)
        if hasattr(clip, HYDRATION_FINGERPRINT_ATTR):
            delattr(clip, HYDRATION_FINGERPRINT_ATTR)
    except Exception:
        pass
    try:
        from .clip_fp32_cast_once import invalidate_cast_once
        from .clip_fp32_cast_once import clear_real_forward_check

        invalidate_cast_once(clip)
        clear_real_forward_check(clip)
    except Exception:
        pass
    csm = getattr(clip, "cond_stage_model", None)
    previous_csm = getattr(clip, "_comfymodal_e31_bound_cond_stage_model", None)
    for owner in (clip, csm, previous_csm):
        if owner is None:
            continue
        for attr in (
            "_comfymodal_e31_real_forward_hook",
            "_comfymodal_e31_pending_forward_callback",
        ):
            try:
                if hasattr(owner, attr):
                    delattr(owner, attr)
            except Exception:
                pass
    try:
        if hasattr(clip, "_comfymodal_e31_bound_cond_stage_model"):
            delattr(clip, "_comfymodal_e31_bound_cond_stage_model")
    except Exception:
        pass


def clip_hydration_state(clip: Any) -> dict[str, Any]:
    """Pure, side-effect-free hydration-state snapshot for *clip*.

    Never calls CUDA APIs, never allocates, never mutates the clip.  Every
    sub-probe is individually guarded so this NEVER raises — even for
    partially-constructed or foreign objects.  Output is JSON-safe (ints,
    bools, strings only).

    Returned dict:

      * ``params`` — counts of ``clip.cond_stage_model`` named parameters by
        device class (cpu/cuda/meta/other); ``is_meta`` wins over the raw
        device type for the meta class.
      * ``bytes``  — logical parameter bytes (numel x element_size) per
        device class plus total.
      * ``excluded_marker`` / ``hydrated`` / ``manifest_present`` /
        ``manifest_eligible`` — the D3 marker/manifest booleans.
      * ``fastsafe_owner_present`` — an attached fastsafetensors owner
        (patcher OWNER_ATTR list or a module ``_FASTSAFE_OWNER_ATTR``).
      * ``patcher`` — load_device / offload_device / current_device (str)
        and model_loaded_weight_memory (int) when a patcher exists.
      * ``cached_patcher_init`` — whether patcher.cached_patcher_init exists.
      * ``state`` — the canonical label from STATE_*.

    Canonical classification (in priority order):

      1. every parameter on cuda -> GPU_FAST_HYDRATED when a fastsafe owner
         is present, else GPU_NATIVE_LOADED;
      2. excluded marker AND (all params meta OR zero logical bytes) ->
         EXCLUDED_PLACEHOLDER;
      3. every parameter on cpu (no meta/cuda/other leftovers) with logical
         bytes > 0 -> CPU_NATIVE_MATERIALIZED;
      4. otherwise -> INVALID/PARTIAL.

    "Full" means the WHOLE checkpoint: a model mixing devices (cpu+cuda,
    cpu+meta, etc.) is partial and classifies as INVALID/PARTIAL — never as
    CPU_NATIVE_MATERIALIZED.

    IMPORTANT SEMANTIC (D6 root-cause class): a fully CPU-materialized model
    classifies as CPU_NATIVE_MATERIALIZED — never GPU_*, and never a
    "resident" label.  ``clip_hydrated`` (the marker) and this function
    together let the demand wrapper distinguish already_gpu_fast_hydrated /
    already_gpu_native_resident / cpu_materialized_requires_hydration /
    excluded_requires_hydration in telemetry.
    """
    snapshot: dict[str, Any] = {
        "params": {"total": 0, "cpu": 0, "cuda": 0, "meta": 0, "other": 0},
        "bytes": {"total": 0, "cpu": 0, "cuda": 0, "meta": 0, "other": 0},
        "excluded_marker": False,
        "manifest_present": False,
        "manifest_eligible": False,
        "hydrated": False,
        "fastsafe_owner_present": False,
        "patcher": {
            "load_device": None,
            "offload_device": None,
            "current_device": None,
            "model_loaded_weight_memory": None,
        },
        "cached_patcher_init": False,
        "state": STATE_INVALID,
    }
    csm = None
    try:
        csm = getattr(clip, "cond_stage_model", None)
        if csm is not None and hasattr(csm, "named_parameters"):
            for _name, param in csm.named_parameters():
                try:
                    is_meta = bool(getattr(param, "is_meta", False))
                    numel = int(getattr(param, "numel", lambda: 0)())
                    elem = int(getattr(param, "element_size", lambda: 0)())
                    nbytes = numel * elem
                    dev_type = getattr(getattr(param, "device", None), "type", "") or ""
                    if is_meta or dev_type == "meta":
                        cls = "meta"
                    elif dev_type == "cpu":
                        cls = "cpu"
                    elif dev_type == "cuda":
                        cls = "cuda"
                    else:
                        cls = "other"
                    snapshot["params"][cls] += 1
                    snapshot["params"]["total"] += 1
                    snapshot["bytes"][cls] += nbytes
                    snapshot["bytes"]["total"] += nbytes
                except Exception:
                    continue
    except Exception:
        pass
    try:
        snapshot["excluded_marker"] = bool(getattr(clip, EXCLUDED_WEIGHTS_MARKER, False))
    except Exception:
        pass
    try:
        snapshot["hydrated"] = bool(getattr(clip, HYDRATED_MARKER, False))
    except Exception:
        pass
    try:
        manifest = getattr(clip, MANIFEST_ATTR, None)
        snapshot["manifest_present"] = manifest is not None
        snapshot["manifest_eligible"] = (
            bool((manifest or {}).get("eligible")) if isinstance(manifest, dict) else False
        )
    except Exception:
        pass
    try:
        if csm is not None:
            for module in csm.modules():
                if getattr(module, _FASTSAFE_OWNER_ATTR, None) is not None:
                    snapshot["fastsafe_owner_present"] = True
                    break
    except Exception:
        pass
    try:
        patcher = getattr(clip, "patcher", None)
        if patcher is not None:
            owners = getattr(patcher, OWNER_ATTR, None)
            if owners:
                snapshot["fastsafe_owner_present"] = True
            for attr in ("load_device", "offload_device", "current_device"):
                try:
                    value = getattr(patcher, attr, None)
                    snapshot["patcher"][attr] = str(value) if value is not None else None
                except Exception:
                    pass
            try:
                mem = getattr(patcher, "model_loaded_weight_memory", None)
                snapshot["patcher"]["model_loaded_weight_memory"] = (
                    int(mem) if mem is not None else None
                )
            except Exception:
                pass
            try:
                snapshot["cached_patcher_init"] = (
                    getattr(patcher, "cached_patcher_init", None) is not None
                )
            except Exception:
                pass
    except Exception:
        pass

    p = snapshot["params"]
    total = int(p["total"])
    if total > 0 and p["cuda"] == total:
        snapshot["state"] = (
            STATE_GPU_FAST_HYDRATED
            if snapshot["fastsafe_owner_present"]
            else STATE_GPU_NATIVE_LOADED
        )
    elif snapshot["excluded_marker"] and (
        (total > 0 and p["meta"] == total) or int(snapshot["bytes"]["total"]) == 0
    ):
        snapshot["state"] = STATE_EXCLUDED_PLACEHOLDER
    elif (
        total > 0
        and p["cpu"] > 0
        and p["meta"] == 0
        and p["cuda"] == 0
        and p["other"] == 0
    ):
        snapshot["state"] = STATE_CPU_NATIVE_MATERIALIZED
    return snapshot


def get_clip_manifest(clip: Any) -> Optional[dict]:
    return getattr(clip, MANIFEST_ATTR, None)


def attach_clip_manifest(clip: Any, manifest: Optional[dict]) -> None:
    if manifest is None:
        return
    setattr(clip, MANIFEST_ATTR, dict(manifest))


def _leaf_loaders(cond_stage_model: Any) -> list[Any]:
    """Modules with a callable ``load_sd`` whose descendants have none."""
    leaves: list[Any] = []
    for module in cond_stage_model.modules():
        load_sd = getattr(module, "load_sd", None)
        if not callable(load_sd):
            continue
        child_loader = any(
            callable(getattr(child, "load_sd", None))
            for child in module.modules()
            if child is not module
        )
        if not child_loader:
            leaves.append(module)
    return leaves


def _str_consts(code: Any) -> tuple:
    return tuple(c for c in code.co_consts if isinstance(c, str))


def _code_mentions(code: Any, name: str) -> bool:
    """True when ``name`` appears anywhere in ``code``'s bytecode metadata:
    as a name (``co_names``), as a string literal (top-level ``co_consts``),
    or as a keyword-argument name (a tuple const — CPython >= 3.11 stores
    keyword names for a call in a ``co_consts`` tuple, e.g. the
    ``('strict', 'assign')`` tuple of Comfy's canonical load_sd body)."""
    if name in code.co_names:
        return True
    for c in code.co_consts:
        if isinstance(c, str):
            if c == name:
                return True
        elif isinstance(c, tuple):
            if name in c:
                return True
    return False


def _is_trivial_super_forward(code: Any) -> bool:
    """True when ``code`` is the bytecode shape of a pure
    ``return super().load_sd(sd)`` forwarding body (e.g.
    comfy/sdxl_clip.py:16-17 ``SDXLClipG.load_sd``): a ``super`` call with
    no ``can_assign_sd`` / ``load_state_dict`` reference — the leaf defers
    entirely to the next MRO ``load_sd``."""
    if code is None:
        return False
    if "super" not in code.co_names:
        return False
    if "load_sd" not in code.co_names:
        return False
    if _code_mentions(code, "can_assign_sd"):
        return False
    if "load_state_dict" in code.co_names:
        return False
    return True


def _resolve_leaf_load_sd(leaf: Any) -> tuple[Optional[Any], str]:
    """Effective ``load_sd`` bytecode for a dispatch leaf, resolving trivial
    ``return super().load_sd(sd)`` forwarders through the class ``__mro__``.

    Returns ``(code, note)``: ``code`` is the leaf's own body when it is a
    meaningful implementation, or the first non-forward ``load_sd`` body
    found by walking the MRO (bounded to ``_SUPER_CHAIN_MAX_DEPTH`` levels;
    fail closed = ``code`` None beyond that or when the source class is not
    in the MRO).  ``note`` records what was resolved."""
    load_sd = getattr(leaf, "load_sd", None)
    code = getattr(load_sd, "__code__", None)
    if code is None:
        return None, "no bytecode"
    if not _is_trivial_super_forward(code):
        return code, "direct"
    func = getattr(load_sd, "__func__", None)
    mro = list(getattr(type(leaf), "__mro__", ()) or ())
    if func is None or not mro:
        return None, "unresolvable super() forward (no defining class in __mro__)"
    try:
        start = next(i for i, k in enumerate(mro) if k.__dict__.get("load_sd") is func)
    except StopIteration:
        return None, "load_sd source class not found in __mro__"
    for klass in mro[start + 1 : start + 1 + _SUPER_CHAIN_MAX_DEPTH]:
        resolved = klass.__dict__.get("load_sd")
        if resolved is None:
            continue
        resolved_code = getattr(resolved, "__code__", None)
        if resolved_code is None:
            return None, "super() chain body lacks bytecode"
        if not _is_trivial_super_forward(resolved_code):
            return resolved_code, f"super() chain resolved at {klass.__name__}"
        # Nested trivial forward: keep walking the chain.
    return None, f"super() chain unresolved after {_SUPER_CHAIN_MAX_DEPTH} MRO levels"


def can_assign_sd_supported(clip: Any) -> tuple[bool, str]:
    """Probe: every dispatch leaf forwards ``assign=`` to
    ``load_state_dict`` honoring the ``can_assign_sd`` convention.

    A leaf is considered capable when its EFFECTIVE ``load_sd`` body — its
    own, or, for a trivial ``return super().load_sd(sd)`` forward (e.g.
    SDXLClipG.load_sd, comfy/sdxl_clip.py:16-17), the resolved next-MRO body
    (e.g. SDClipModel.load_sd, comfy/sd1_clip.py:308-309) — both references
    the attribute name ``can_assign_sd`` (as a name or string literal) AND
    provably forwards ``assign=`` to ``load_state_dict`` (``load_state_dict``
    name present with ``assign`` present as a name or constant — Comfy's
    canonical body stores the keyword names in a ``co_consts`` tuple on
    Python >= 3.11).  Capability-based: no model names.  Unresolvable
    chains fail closed (unsupported).
    """
    csm = getattr(clip, "cond_stage_model", None)
    if csm is None:
        return False, "no cond_stage_model"
    leaves = _leaf_loaders(csm)
    if not leaves:
        return False, "no dispatch leaves found"
    unsupported: list[str] = []
    for leaf in leaves:
        code, note = _resolve_leaf_load_sd(leaf)
        if code is None:
            unsupported.append(f"{type(leaf).__module__}.{type(leaf).__name__} ({note})")
            continue
        honors_flag = _code_mentions(code, "can_assign_sd")
        forwards_assign = "load_state_dict" in code.co_names and _code_mentions(
            code, "assign"
        )
        if not (honors_flag and forwards_assign):
            unsupported.append(f"{type(leaf).__module__}.{type(leaf).__name__}")
    if unsupported:
        return False, f"leaves not honoring can_assign_sd: {unsupported}"
    return True, f"{len(leaves)} dispatch leaves honor can_assign_sd"


def _leaf_param_map(leaf: Any) -> dict[str, Any]:
    """Map load_sd-receivable names to parameters for one dispatch leaf.

    Comfy leaves forward the file state dict directly to an inner module
    (e.g. SDClipModel.load_sd -> transformer.load_state_dict), so the file
    keys are the inner module's names while ``leaf.state_dict()`` prefixes
    them with the leaf attribute path.  Keep the actual parameter/buffer
    objects when the upstream Module API supports it; ownership proofs use
    object identity to distinguish aliases from constructor-owned state.
    Both the exact names and the first-component-stripped names are mapped
    (exact wins)."""
    try:
        sd = leaf.state_dict(keep_vars=True)
    except TypeError:
        # Small Comfy-compatible leaves may expose the older no-argument form.
        sd = leaf.state_dict()
    mapping: dict[str, Any] = {}
    for key, tensor in sd.items():
        mapping[key] = tensor
        if "." in key:
            stripped = key.split(".", 1)[1]
            mapping.setdefault(stripped, tensor)
    return mapping


def _leaf_candidate_key_sets(leaf: Any) -> set[frozenset]:
    """Candidate receivable key sets for one leaf: exact state-dict names
    and every first-component-stripped variant."""
    keys = set(leaf.state_dict().keys())
    candidates = {frozenset(keys)}
    firsts = sorted({k.split(".", 1)[0] for k in keys if "." in k})
    for first in firsts:
        stripped = frozenset(k.split(".", 1)[1] for k in keys if k.startswith(first + "."))
        if stripped:
            candidates.add(stripped)
    return candidates


def verify_leaf_routing(clip: Any, per_file_key_sets: list[set]) -> tuple[bool, str]:
    """Generic routing check: every file's transformed key set must be a
    subset of at least one dispatch leaf's receivable names (exact or
    first-component-stripped)."""
    csm = getattr(clip, "cond_stage_model", None)
    if csm is None:
        return False, "no cond_stage_model"
    leaves = _leaf_loaders(csm)
    if not leaves:
        return False, "no dispatch leaves found"
    for i, keys in enumerate(per_file_key_sets):
        matched = False
        for leaf in leaves:
            for candidate in _leaf_candidate_key_sets(leaf):
                if keys <= candidate:
                    matched = True
                    break
            if matched:
                break
        if not matched:
            return False, f"file {i}: no leaf accepts key set (size {len(keys)})"
    return True, f"{len(per_file_key_sets)} file key sets route to {len(leaves)} leaves"


def _zero_copy_evidence_clip(csm: Any, source: dict, sample_limit: int = 8) -> tuple[bool, str]:
    """Leaf-aware zero-copy proof: file keys are leaf-receivable (often
    first-component-stripped) while the structure state dict is leaf-prefixed,
    so the comparison runs through each dispatch leaf's key map."""
    matched = 0
    total = 0
    samples: list[str] = []
    for leaf in _leaf_loaders(csm):
        param_map = _leaf_param_map(leaf)
        for key, tensor in source.items():
            if key in _TOKENIZER_BLOB_KEYS:
                # Structural tokenizer payload (spiece_model / tekken_model /
                # tokenizer_json): consumed at CLIP.__init__ via .get(), never
                # a bound parameter — exclude from the zero-copy proof.
                continue
            dst = param_map.get(key)
            if dst is None:
                continue
            total += 1
            if (
                tensor.data_ptr() == dst.data_ptr()
                and tensor.shape == dst.shape
                and tensor.dtype == dst.dtype
                and tensor.untyped_storage().data_ptr() == dst.untyped_storage().data_ptr()
            ):
                matched += 1
                if len(samples) < sample_limit:
                    samples.append(key)
    ok = total > 0 and matched == total
    evidence = (
        f"zero-copy: {matched}/{total} keys share storage across dispatch "
        f"leaves (e.g. {samples[0] if samples else 'n/a'})"
    )
    return ok, evidence


def hydrate_clip_bind(
    clip: Any,
    per_file_sds: list[dict],
    *,
    require_no_meta: bool = False,
    expect_device: Optional[str] = None,
) -> tuple[bool, str]:
    """Bind GPU/CPU file tensors into the CLIP structure via Comfy's own
    ``load_sd`` dispatch with the ``can_assign_sd`` convention forced True.

    Mirrors comfy.sd.CLIP.load_sd's list path (sd.py:417-428) with
    can_assign=True: the checkpoint tensors BECOME the parameters
    (zero-copy).  Returns (ok, evidence); raises on shape/dtype mismatch.
    """
    csm = getattr(clip, "cond_stage_model", None)
    if csm is None:
        raise RuntimeError("clip has no cond_stage_model")
    # Every assign/copy bind is a semantic storage replacement boundary, not
    # only the FP32 experiment.  Reset before the first load so a reused outer
    # CLIP cannot inherit a marker, generation, or pending callback.
    try:
        reset_clip_hydration_for_bind(clip)
    except Exception:
        pass
    csm.can_assign_sd = True
    for module in csm.modules():
        module.can_assign_sd = True
    for sd in per_file_sds:
        csm.load_sd(sd)
    source: dict[str, Any] = {}
    for sd in per_file_sds:
        source.update(sd)
    ok, evidence = _zero_copy_evidence_clip(csm, source)
    if not ok:
        return False, f"zero-copy bind proof failed: {evidence}"
    if require_no_meta:
        metas: list[str] = []
        for leaf in _leaf_loaders(csm):
            param_map = _leaf_param_map(leaf)
            for key in source:
                dst = param_map.get(key)
                if dst is not None and getattr(dst, "is_meta", False):
                    metas.append(key)
        if metas:
            return False, f"{len(metas)} file-covered parameters still meta after bind: {metas[:4]}"
    if expect_device is not None:
        off: list[str] = []
        for leaf in _leaf_loaders(csm):
            param_map = _leaf_param_map(leaf)
            for key in source:
                dst = param_map.get(key)
                if dst is not None and str(dst.device) != expect_device:
                    off.append(key)
        if off:
            return False, f"parameters not on {expect_device}: {off[:4]}"
    return True, evidence


def install_gpu_critical_coordination(clip: Any) -> str:
    """Wrap generic CLIP load/encode boundaries for D15 coordination."""
    try:
        from . import gpu_lane_coordination as _coord
    except Exception:
        return "unavailable"
    if not _coord.enabled():
        return "disabled"
    load_is_wrapped = bool(
        getattr(getattr(clip, "load_model", None), GPU_COORDINATION_MARKER, False)
    )
    encode_is_wrapped = all(
        not callable(getattr(type(clip), method_name, None))
        or bool(
            getattr(getattr(clip, method_name, None), GPU_COORDINATION_MARKER, False)
        )
        for method_name in ("encode_from_tokens_scheduled", "encode_from_tokens")
    )
    if getattr(clip, GPU_COORDINATION_MARKER, False) and load_is_wrapped and encode_is_wrapped:
        return "already_installed"

    installed = 0
    load_model = getattr(clip, "load_model", None)
    if callable(load_model) and not load_is_wrapped:

        @functools.wraps(load_model)
        def _coordinated_load_model(*args: Any, **kwargs: Any) -> Any:
            from .fast_cold_orchestration import SourceFenceFailure

            try:
                from .fast_cold_orchestration import before_clip_demand

                manifest = getattr(clip, MANIFEST_ATTR, None) or {}
                if not before_clip_demand(
                    trace=_coord._resolve_trace(None),
                    paths=[
                        entry.get("path", "")
                        for entry in manifest.get("files", [])
                        if isinstance(entry, dict)
                    ],
                ):
                    raise SourceFenceFailure(
                        "structural_source_fence_failure:clip"
                    )
            except SourceFenceFailure:
                raise
            except Exception:
                pass
            token = _coord.begin_clip_hydration(cache_state="cache_miss_or_direct")
            success = False
            try:
                result = load_model(*args, **kwargs)
                success = True
                return result
            finally:
                _coord.end_clip_hydration(token, success=success)

        setattr(_coordinated_load_model, GPU_COORDINATION_MARKER, True)
        setattr(clip, "load_model", _coordinated_load_model)
        installed += 1

    for method_name in ("encode_from_tokens_scheduled", "encode_from_tokens"):
        if (
            not callable(getattr(type(clip), method_name, None))
            or bool(
                getattr(getattr(clip, method_name, None), GPU_COORDINATION_MARKER, False)
            )
        ):
            continue

        def _coordinated_encode(
            *args: Any, _method_name: str = method_name, **kwargs: Any
        ) -> Any:
            token = _coord.begin_clip_encode(cache_state="cache_miss")
            success = False
            try:
                method = getattr(type(clip), _method_name, None)
                if not callable(method):
                    return None
                result = method(clip, *args, **kwargs)
                success = True
                return result
            finally:
                _coord.end_clip_encode(token, success=success)

        setattr(_coordinated_encode, GPU_COORDINATION_MARKER, True)
        setattr(clip, method_name, _coordinated_encode)
        installed += 1

    if installed == 0:
        return "unavailable"
    setattr(clip, GPU_COORDINATION_MARKER, True)
    return "installed"


def install_demand_wrapper(clip: Any, hydrator: Callable[[Any], None]) -> bool:
    """Install an instance-level ``load_model`` wrapper on *clip*.

    The wrapper runs *hydrator* before the current class-level
    ``CLIP.load_model`` — i.e. exactly at each encode demand.  The hydrator
    is idempotent (it checks the hydrated marker itself), so repeated
    demands re-record the current source mode (already_resident) without
    re-hydrating.  Cache-hit requests never encode, never call
    ``load_model``, and therefore never hydrate.  Idempotent install.

    Order-independence: the class-level ``load_model`` is resolved AT CALL
    TIME (never snapshotted at install), so D3 composes correctly whether a
    class-level wrapper (e.g. D2 forensics on ``encode_token_weights``-style
    class methods) is installed before or after this install — both orders
    fire both wrappers.
    """
    if getattr(clip, DEMAND_WRAPPER_MARKER, False):
        return False
    if not callable(getattr(type(clip), "load_model", None)):
        return False

    def _wrapped(tokens=None, **kwargs):
        # Re-entrancy guard: the instance attribute (_wrapped) shadows the
        # class attribute, so calling type(clip).load_model(clip, tokens)
        # runs the CURRENT class method directly and never recurses into
        # this wrapper.  Resolving at call time (not install time) chains D3
        # to whatever class-level wrapper is present right now.
        # D3-side entry checkpoint: fire the wiring helper (lazily imported
        # to avoid a circular import) exactly once per demand, before any
        # hydration decision.  The helper is gated on the D3 flags and is a
        # strict no-op when they are off — zero behavior change.
        try:
            from comfymodal_runtime.clip_fast_hydration_wiring import (
                clip_state_checkpoint as _checkpoint,
            )

            _checkpoint(None, "clip_load_model_entry", clip)
        except Exception:
            pass
        cls_load_model = getattr(type(clip), "load_model", None)
        hydrator(clip)
        if not callable(cls_load_model):
            return None
        if tokens is None:
            return cls_load_model(clip, **kwargs)
        return cls_load_model(clip, tokens, **kwargs)

    setattr(_wrapped, DEMAND_WRAPPER_MARKER, True)
    setattr(clip, DEMAND_WRAPPER_MARKER, True)
    clip.load_model = _wrapped
    return True


def owner_attach(clip: Any, loader: Any, fb: Any) -> None:
    """Attach a fastsafetensors (loader, buffer) owner to the patcher so the
    GPU fragment memory dies with the patcher/model lifetime.  Multiple
    owners (one per file) accumulate in a single list."""
    patcher = getattr(clip, "patcher", None)
    if patcher is None:
        raise RuntimeError("clip has no patcher to own the fastsafe buffer")
    owners = getattr(patcher, OWNER_ATTR, None)
    if owners is None:
        owners = []
        setattr(patcher, OWNER_ATTR, owners)
    owners.append(_FastsafeOwner(loader, fb))


def retire_source_owners(
    owners: list[tuple[Any, Any]], *, bf16_bytes: int = 0, fp32_bytes: int = 0,
    clip: Any = None,
) -> dict[str, Any]:
    """Retire source buffers after an independent FP32 bind.

    Cast-once tensors do not borrow the BF16 fastsafe allocation.  Prefer the
    loader/buffer's non-destructive storage release API, if present; never call
    ``close`` or ``empty_cache`` on this successful hot path.  Discard/error
    cleanup continues to use the existing close path.
    """
    before = len(owners)
    release_calls = 0
    retired = 0
    statuses: list[dict[str, Any]] = []
    total_bf16 = int(max(0, bf16_bytes))
    total_fp32 = int(max(0, fp32_bytes))
    seen: set[int] = set()
    source_component_ids = {
        id(item)
        for owner in owners
        for item in (tuple(owner) if isinstance(owner, (tuple, list)) else (owner,))
        if item is not None
    }
    for index, owner in enumerate(list(owners)):
        components = tuple(owner) if isinstance(owner, (tuple, list)) else (owner,)
        component_status: list[dict[str, Any]] = []
        released_for_owner = False
        owner_bytes = total_bf16 // max(before, 1) + (total_bf16 % max(before, 1) if index == 0 else 0)
        owner_fp32 = total_fp32 // max(before, 1) + (total_fp32 % max(before, 1) if index == 0 else 0)
        for item in components:
            if item is None or id(item) in seen:
                continue
            seen.add(id(item))
            method = getattr(item, "release_storage", None)
            method_name = "release_storage"
            if not callable(method):
                for name in ("free_storage", "release_buffer", "release"):
                    candidate = getattr(item, name, None)
                    if callable(candidate):
                        method, method_name = candidate, name
                        break
            status: dict[str, Any] = {
                "component_id": str(id(item)),
                "method": method_name if callable(method) else None,
                "released": False,
                "error": "" if callable(method) else "no_release_api",
            }
            if callable(method):
                try:
                    # Successful E31 retirement must prove the explicit
                    # no-purge contract.  Retrying without the keyword could
                    # invoke an implementation that purges or calls
                    # empty_cache, so an incompatible API fails closed.
                    method(purge_allocator=False)
                    status["released"] = True
                    release_calls += 1
                    released_for_owner = True
                except TypeError:
                    status["error"] = "release_api_requires_explicit_no_purge"
                except Exception as exc:
                    status["error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
            component_status.append(status)
        # A source owner is retired only when every distinct backing
        # component has a successful release.  Releasing just the loader while
        # leaving its buffer live would make the E31 FP32 claim unsafe.
        owner_retired = bool(component_status) and all(
            bool(item.get("released")) for item in component_status
        )
        if owner_retired:
            retired += 1
        statuses.append({
            "owner_index": index,
            "status": "retired" if owner_retired else "not_retired",
            "released": owner_retired,
            "component_count": len(component_status),
            "release_call_count": sum(1 for item in component_status if item.get("released")),
            "bytes_before": owner_bytes,
            "bytes_after": 0 if owner_retired else owner_bytes,
            "fp32_bytes": owner_fp32,
            "components": component_status,
        })
    all_retired = before > 0 and retired == before
    if all_retired:
        # The cast-once parameters no longer borrow these owners.  Remove the
        # references from both the caller's source list and any patcher list;
        # do not close or purge on this successful hot path.
        owners.clear()
        if clip is not None:
            patcher = getattr(clip, "patcher", None)
            attached = getattr(patcher, OWNER_ATTR, None) if patcher is not None else None
            if isinstance(attached, list):
                attached[:] = [
                    item for item in attached
                    if id(item) not in source_component_ids
                    and id(getattr(item, "loader", None)) not in source_component_ids
                    and id(getattr(item, "fb", None)) not in source_component_ids
                ]
                try:
                    if not attached:
                        delattr(patcher, OWNER_ATTR)
                except Exception:
                    pass
    return {
        "ok": all_retired,
        "owner_count_before": int(before),
        "owner_count_after": int(before - retired),
        "owner_bytes_before": total_bf16,
        "owner_bytes_after": sum(int(item["bytes_after"]) for item in statuses),
        "owners_retired": int(retired),
        "owners_failed": int(before - retired),
        "release_calls": int(release_calls),
        "bf16_bytes": total_bf16,
        "fp32_bytes": total_fp32,
        "per_owner": statuses,
    }


def staged_owner_attach(clip: Any, owner: Any) -> None:
    patcher = getattr(clip, "patcher", None)
    if patcher is None:
        raise RuntimeError("clip has no patcher to own staged storage")
    owners = getattr(patcher, STAGED_OWNER_ATTR, None)
    if owners is None:
        owners = []
        setattr(patcher, STAGED_OWNER_ATTR, owners)
    owners.append(owner)


def _close_staged_owner(owner: Any) -> None:
    if owner is None:
        return
    if isinstance(owner, (tuple, list)):
        for item in owner:
            _close_staged_owner(item)
        return
    close = getattr(owner, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass


def release_owner(clip: Any) -> bool:
    """Release all fastsafetensors owners attached to the clip's patcher.

    Only call when the clip/patcher is being discarded: closing the buffers
    invalidates any tensors still referencing them.
    """
    patcher = getattr(clip, "patcher", None)
    if patcher is None:
        return False
    # Owner retirement/discard is a re-hydration boundary.  Do not leave an
    # E31 marker or callback claiming storage whose backing owner is gone.
    reset_clip_hydration_for_bind(clip)
    owners = getattr(patcher, OWNER_ATTR, None)
    staged_owners = getattr(patcher, STAGED_OWNER_ATTR, None)
    if not owners and not staged_owners:
        return False
    if owners:
        for owner in owners:
            try:
                owner.loader.close()
            except Exception:
                pass
        try:
            delattr(patcher, OWNER_ATTR)
        except Exception:
            pass
    if staged_owners:
        for owner in staged_owners:
            _close_staged_owner(owner)
        try:
            delattr(patcher, STAGED_OWNER_ATTR)
        except Exception:
            pass
    try:
        torch.cuda.empty_cache()
    except Exception:
        pass
    return True
