"""R44B Lane C: REQUEST-time UNET FastSafe direct-GPU pipeline (E28-tuned).

Installs an idempotent wrapper around ``nodes.NODE_CLASS_MAPPINGS["UNETLoader"]
.load_unet`` so the UNET is produced at REQUEST time through:

  1. CPU/page-cache source preparation (``ctx.arm_unet_source_prep``) that
     OVERLAPS whatever else runs — including the CLIP forward.
  2. The E28-proven FastSafe direct-GPU load
     (``unet_fastsafetensors._fs_fastsafe_load``: SafeTensorsFileLoader with
     max_threads=8, bbuf 512 KiB-kb pool, nogds, disable_cache; 256 MiB copy
     blocks; ``use_buf_register=False``) — all tuning comes from that
     module's env-driven defaults; NO tuning matrix lives here.
  3. CURRENT R42 native-parity detection + zero-copy adoption composed from
     ``model_preload._native_detection_input`` (convert_old_quants parity,
     prefix detection, only-strip-if-non-empty bare-key ZImage behavior,
     model_config_none fails closed) and the skeleton/patcher assign=True
     bind sequence proven in ``model_preload._make_golden_load_diffusion_model_wrapper``
     (same-storage data_ptr identity measured via
     ``model_preload._storage_identity_counts``), with the fastsafe
     loader/buffer owner retained on the patcher exactly as the restore-time
     pipeline does.

D15 STRUCTURAL GUARANTEE
========================
The D15 rule ("no UNET GPU activation/H2D while CLIP owns the GPU-critical
section") is enforced STRUCTURALLY here: the UNET GPU gate token
(``gpu_lane_coordination.begin_unet_gpu_phase``) is acquired ONLY around the
GPU-committing phase (FastSafe file→CUDA transfer + adoption bind).  The
source read / page-cache preparation / header+metadata work NEVER runs inside
the gate.  The gate itself is the race arbiter: it RAISES
``RuntimeError("unet_gpu_during_clip_critical")`` if the calling thread would
overlap the CLIP critical holder; this module catches that signal, waits for
the CLIP forward-done event (bounded), and retries exactly once.

Duplicate-load prevention: after a successful adoption the node wrapper
replaces the graph output (the native loader never executes for this
request); additionally the physical-load claim latch in the request context
(``ctx.claim_physical_load("unet")``) blocks any second owner from entering,
and a published result short-circuits re-entry.

No Golden imports; no RestorePreparation/coordinator usage; no changes to
model_preload.py / modal_app.py / comfyapp.py.
"""

from __future__ import annotations

import threading
import time
from typing import Any

# Sentinel attribute mirroring the V2LoaderBridge.install pattern
# (model_preload.V2LoaderBridge.install uses "_comfy_modal_v2_original").
_SENTINEL_ATTR = "_comfymodal_r44b_original"

# Bounded waits (fail-closed; not a tuning matrix).
_CLIP_FORWARD_WAIT_S = 120.0
_PREP_JOIN_TIMEOUT_S = 30.0

_INSTALL_LOCK = threading.Lock()
_INSTALLED = False


# ── Path resolution (identical to nodes.UNETLoader.load_unet) ─────────────


def _resolve_unet_path(unet_name: str) -> str:
    """Resolve exactly as the node does:
    ``folder_paths.get_full_path_or_raise("diffusion_models", unet_name)``
    (verified in ComfyUI nodes.py).  Raises RuntimeError when unresolvable."""
    import folder_paths as _fp

    name = str(unet_name or "")
    or_raise = getattr(_fp, "get_full_path_or_raise", None)
    if callable(or_raise):
        return str(or_raise("diffusion_models", name))
    get_full = getattr(_fp, "get_full_path", None)
    if callable(get_full):
        resolved = get_full("diffusion_models", name)
        if resolved:
            return str(resolved)
    raise RuntimeError("unet_path_unresolved")


def _canonical_native_arm() -> str:
    """The canonical native UNET arm name per loader_selection normalization
    (raw "native" normalizes to "native_comfy" for role=unet)."""
    try:
        from . import loader_selection as _ls

        return str(_ls.normalize_observed("unet", "native"))
    except Exception:
        return "native_comfy"


def _record_native_fallback(reason: str) -> None:
    try:
        from . import loader_selection as _ls

        arm = _canonical_native_arm()
        _ls.record_observed(
            "unet",
            arm,
            fallback_attempted=True,
            fallback_loader=arm,
            fallback_reason=str(reason)[:160],
        )
    except Exception:
        pass


# ── R42 native-parity adoption (composed from existing pieces) ────────────


def _adopt_fastsafe_cuda_storages(
    path: str,
    tensors: dict,
    loader: Any,
    fb: Any,
    model_options: dict,
    device_str: str,
    metrics: dict,
) -> tuple[Any, int, int]:
    """Bind FastSafe CUDA views into a natively-detected skeleton patcher.

    Routes through the CURRENT R42 native-parity detection
    (``model_preload._native_detection_input``) and mirrors the proven
    adoption sequence of ``_make_golden_load_diffusion_model_wrapper``:
    cheap config resolve -> cheap skeleton/patcher ->
    ``load_model_weights(assign=True)`` -> same-storage data_ptr identity ->
    owner retention -> demand verification.  Returns
    ``(patcher, matched, total)``.  Raises RuntimeError on ANY gate failure
    (caller fail-closes the loader/fb).
    """
    import torch
    from . import model_preload as _mp
    from . import unet_fastsafetensors as _fs

    t_adopt0 = time.monotonic_ns()

    # ── Header-only layout gates (parity with the golden demand wrapper) ──
    t_detect0 = time.monotonic_ns()
    header = _mp._c6_parse_safetensors_header(path)
    if not header:
        raise RuntimeError("header_unreadable")
    entries = [k for k in header if k != "__metadata__"]
    if any(".scaled_fp8" in k for k in entries):
        raise RuntimeError("scaled_fp8")
    dtypes = {str(header[k].get("dtype", "")) for k in entries}
    if len(dtypes) != 1:
        raise RuntimeError("non_uniform_dtype")
    view_dtype = _mp._c6_safetensors_dtype_map().get(next(iter(dtypes)))
    if view_dtype is None:
        raise RuntimeError("unknown_dtype")

    meta_sd = {
        k: torch.empty(tuple(header[k].get("shape") or []), dtype=view_dtype, device="meta")
        for k in entries
    }
    metadata = header.get("__metadata__")

    # ── R42 native-parity detection input ──
    prefix_fn = _mp._c6_comfy_fn("comfy.model_detection", "unet_prefix_from_state_dict")
    strip_fn = _mp._c6_comfy_fn("comfy.utils", "state_dict_prefix_replace")
    config_fn = _mp._c6_comfy_fn("comfy.model_detection", "model_config_from_unet")
    quant_fn = _mp._c6_comfy_fn("comfy.utils", "convert_old_quants")
    if not all(callable(x) for x in (prefix_fn, strip_fn, config_fn)):
        raise RuntimeError("missing_comfy_helper")
    detect_sd, detect_meta, prefix = _mp._native_detection_input(
        meta_sd, metadata, prefix_fn, strip_fn, quant_fn
    )
    model_config = config_fn(detect_sd, "", metadata=detect_meta)
    if model_config is None:
        # Fail closed (no payload retry exists at request time; the bare-key
        # ZImage case survives because the empty-strip guard keeps detect_sd
        # intact inside _native_detection_input).
        raise RuntimeError("model_config_none")
    metrics["header_detect_wall_ms"] = round(
        (time.monotonic_ns() - t_detect0) / 1e6, 3
    )

    # ── Cheap dtype resolve + skeleton construction ──
    t_skeleton0 = time.monotonic_ns()
    selected = model_options.get("dtype")
    if selected is None:
        unet_dtype_fn = _mp._c6_comfy_fn("comfy.model_management", "unet_dtype")
        if not callable(unet_dtype_fn):
            raise RuntimeError("unet_dtype_unavailable")
        selected = unet_dtype_fn(
            supported_dtypes=list(model_config.supported_inference_dtypes)
        )
    if selected != view_dtype:
        raise RuntimeError("inference_dtype_mismatch")
    manual_cast_fn = _mp._c6_comfy_fn("comfy.model_management", "unet_manual_cast")
    offload_fn = _mp._c6_comfy_fn("comfy.model_management", "unet_offload_device")
    load_device = (
        model_options.get("load_device")
        if model_options.get("load_device") is not None
        else torch.device(device_str)
    )
    offload_device = offload_fn() if callable(offload_fn) else torch.device("cpu")
    manual_cast = (
        manual_cast_fn(selected, load_device, model_config.supported_inference_dtypes)
        if callable(manual_cast_fn)
        else None
    )
    model_config.set_inference_dtype(selected, manual_cast)
    model = model_config.get_model(detect_sd, "")

    mp_cls = _mp._c6_comfy_fn("comfy.model_patcher", "CoreModelPatcher")
    if mp_cls is None:
        mp_cls = _mp._c6_comfy_fn("comfy.model_patcher", "ModelPatcher")
    if mp_cls is None:
        raise RuntimeError("patcher_unavailable")
    patcher = mp_cls(model, load_device=load_device, offload_device=offload_device)
    metrics["skeleton_wall_ms"] = round((time.monotonic_ns() - t_skeleton0) / 1e6, 3)

    # ── Zero-copy assign=True bind of the FastSafe CUDA storages ──
    t_bind0 = time.monotonic_ns()
    pref = str(prefix or "")
    views = {
        (k[len(pref):] if pref and k.startswith(pref) else k): v
        for k, v in tensors.items()
    }
    result = model.load_model_weights(dict(views), "", assign=True)
    missing = getattr(result, "missing_keys", None) if result is not None else None
    if missing:
        raise RuntimeError("missing_keys")
    metrics["bind_wall_ms"] = round((time.monotonic_ns() - t_bind0) / 1e6, 3)

    # Diffusion-level validation + MEASURED storage identity (R42A semantics).
    t_valid0 = time.monotonic_ns()
    inner_model = getattr(model, "diffusion_model", model)
    named = dict(inner_model.named_parameters())
    named.update(dict(inner_model.named_buffers()))
    for name, tensor in named.items():
        src = views.get(name)
        if src is not None and (
            tuple(tensor.shape) != tuple(src.shape)
            or tensor.dtype != src.dtype
            or not str(tensor.device).startswith("cuda")
        ):
            raise RuntimeError("bind_validation")
    identity_counts, _ptr_map = _mp._storage_identity_counts(named, views)
    matched = int(identity_counts.get("same_storage_count") or 0)
    total = int(identity_counts.get("tensor_count") or 0)
    metrics["storage_identity"] = dict(identity_counts)

    leftovers = sum(1 for name in named if name not in views)
    if leftovers:
        try:
            model.to(patcher.load_device)
        except Exception:
            pass

    # ── Owner retention (Gate 1): identical to the restore-time pipeline ──
    owner = _fs._FastsafeOwner(loader, fb)
    try:
        setattr(patcher, _fs._FS_OWNER_ATTR, owner)
    except Exception:
        raise RuntimeError("owner_attach_failed")

    # ── Demand verification step (GPU-ready contract) ──
    validation = _fs._fs_validate_final(inner_model, device_str)
    metrics["final_validation"] = validation
    if not validation.get("all_params_on_target") or int(
        validation.get("residual_meta_count") or 0
    ) != 0:
        raise RuntimeError("demand_verification_failed")

    metrics["identity_validation_wall_ms"] = round(
        (time.monotonic_ns() - t_valid0) / 1e6, 3
    )
    metrics["adopt_wall_ms"] = round((time.monotonic_ns() - t_adopt0) / 1e6, 3)
    return patcher, matched, total


# ── GPU phase (D15-gated) ─────────────────────────────────────────────────


def _run_gpu_phase(
    path: str,
    device_str: str,
    model_options: dict,
    rid: str,
    trace: Any,
    timings: dict,
    owner_holder: dict | None = None,
) -> tuple[Any, Any, Any]:
    """Acquire the D15 UNET GPU gate, run the FastSafe file→CUDA transfer and
    the adoption bind strictly inside it, release in finally.  Returns
    ``(patcher, loader, fb)`` on success; raises on failure.  ``owner_holder``
    (optional) receives loader/fb AS SOON AS they exist so the caller's
    fail-closed path can close them even when adoption raises mid-way."""
    from . import gpu_lane_coordination as coord
    from . import unet_fastsafetensors as _fs

    t_gate0 = time.monotonic_ns()
    token = coord.begin_unet_gpu_phase(rid, trace, reason="request_fastsafe")
    timings["gate_wait_ms"] = round((time.monotonic_ns() - t_gate0) / 1e6, 3)
    timings["gate_begin_mono_ns"] = time.monotonic_ns()
    ok = False
    loader = None
    fb = None
    try:
        transfer_started_ns = coord.unet_transfer_start(
            token, reason="request_fastsafe"
        )
        try:
            metrics: dict[str, Any] = {}
            tensors, loader, fb = _fs._fs_fastsafe_load(path, device_str, metrics)
            if owner_holder is not None:
                owner_holder["loader"] = loader
                owner_holder["fb"] = fb
            timings["fastsafe_metrics"] = metrics
            timings["file_to_gpu_wall_ms"] = metrics.get("fastsafe_file_gpu_wall_ms")
            patcher, matched, total = _adopt_fastsafe_cuda_storages(
                path, tensors, loader, fb, model_options, device_str, metrics
            )
            timings["adopt_ms"] = metrics.get("adopt_wall_ms")
            timings["storage_identity_matched"] = matched
            timings["storage_identity_total"] = total
            ok = True
            return patcher, loader, fb
        finally:
            try:
                coord.unet_transfer_end(
                    token, transfer_started_ns, success=ok, reason="request_fastsafe"
                )
            except Exception:
                pass
    finally:
        try:
            coord.end_unet_gpu_phase(token, success=ok)
        except Exception:
            pass


def _gpu_phase_with_arbitration(ctx: Any, owner_holder: dict, *args: Any) -> tuple[Any, Any, Any]:
    """Run the GPU phase with begin_unet_gpu_phase as the race arbiter: on
    ``RuntimeError("unet_gpu_during_clip_critical")``, wait for the CLIP
    forward-done event (bounded) and retry ONCE."""
    try:
        return _run_gpu_phase(*args, owner_holder=owner_holder)
    except RuntimeError as exc:
        if "unet_gpu_during_clip_critical" not in str(exc):
            raise
        evt = None
        try:
            evt = ctx.clip_forward_done_event()
        except Exception:
            evt = None
        if evt is not None:
            evt.wait(_CLIP_FORWARD_WAIT_S)
        return _run_gpu_phase(*args, owner_holder=owner_holder)


def _close_owner(loader: Any, fb: Any) -> None:
    """Fail-closed release of the fastsafe loader/device buffer."""
    try:
        if fb is not None:
            fb.close()
        elif loader is not None:
            loader.close()
    except Exception:
        pass
    try:
        import torch

        torch.cuda.empty_cache()
    except Exception:
        pass


# ── Wrapper body ──────────────────────────────────────────────────────────


def _fail_closed(
    ctx: Any,
    reason: str,
    loader: Any = None,
    fb: Any = None,
    ordering: str = "",
    timings: dict | None = None,
) -> None:
    """Single terminal fallback bookkeeping path.  Never raises."""
    _close_owner(loader, fb)
    short = str(reason)[:120]
    try:
        ctx.release_claim("unet", short)
    except Exception:
        pass
    try:
        ctx.record_terminal(f"unet_fastsafe_failed:{short}", role="unet")
    except Exception:
        pass
    _record_native_fallback(short)
    try:
        md = {"status": "fallback", "phase": "request", "reason": short}
        if ordering:
            md["ordering"] = ordering
        if timings:
            for key in ("file_to_gpu_wall_ms", "prepare_join_ms"):
                if timings.get(key) is not None:
                    md[key] = timings.get(key)
        ctx.telemetry("unet_fastsafe_fallback", **md)
    except Exception:
        pass


def _load_unet_via_fastsafe(
    ctx: Any, unet_name: str, weight_dtype: str, original: Any, instance: Any
) -> tuple:
    """Producer flow (spec C): claim -> descriptor -> self-arm prep ->
    D15-safe ordering decision -> gated GPU phase -> publish.  On ANY
    failure before successful adoption: fail-closed and call ORIGINAL."""
    import torch

    timings: dict[str, Any] = {}
    # Loader/fb become visible here AS SOON AS the FastSafe load creates
    # them, so ANY later failure (e.g. adoption gate) still fail-closes them.
    owner_holder: dict[str, Any] = {}
    rid = ""
    trace = None
    try:
        from . import model_preload as _mp

        trace = _mp._ACTIVE_REQUEST_TRACE.get()
        rid = str(getattr(trace, "request_id", "") or "")
    except Exception:
        trace = None
        rid = ""

    # C1: physical-load claim (another owner?).
    try:
        if not ctx.claim_physical_load("unet"):
            return original(instance, unet_name, weight_dtype)
    except Exception:
        return original(instance, unet_name, weight_dtype)

    ordering = ""
    try:
        # Capability guards FIRST (E28-proven _fs_eligible).  Ineligible is
        # NOT a fallback (mirrors _fs_try_pipeline semantics: no
        # fallback_attempted poisoning) — release and let ORIGINAL run.
        eligible, ineligible_reason = _fastsafe_eligible(unet_name, weight_dtype)
        if not eligible:
            try:
                ctx.release_claim("unet", f"ineligible:{ineligible_reason}")
            except Exception:
                pass
            try:
                ctx.record_terminal(
                    f"unet_fastsafe_ineligible:{ineligible_reason}", role="unet"
                )
            except Exception:
                pass
            return original(instance, unet_name, weight_dtype)
        model_options = _build_model_options(weight_dtype)

        # C2: descriptor (path resolution identical to the node's own logic).
        try:
            path = _resolve_unet_path(unet_name)
        except Exception:
            path = ""
        descriptor = None
        if path:
            try:
                from . import request_fastpath as _rfp

                descriptor = _rfp.build_descriptor(
                    "unet",
                    path,
                    target_device=f"cuda:{torch.cuda.current_device()}",
                )
            except Exception:
                descriptor = None
        if not path or descriptor is None:
            _fail_closed(ctx, "unet_descriptor_unavailable")
            return original(instance, unet_name, weight_dtype)
        try:
            ctx.set_descriptor("unet", descriptor)
        except Exception:
            pass

        # C3: self-arm CPU source prep NOW (idempotent in ctx; overlaps CLIP).
        try:
            ctx.arm_unet_source_prep([path])
        except Exception:
            pass

        # C4: ordering decision (deadlock-free by construction — the graph
        # executor is sequential).
        forward_evt = None
        forwarded = False
        clip_state = ""
        try:
            forward_evt = ctx.clip_forward_done_event()
            forwarded = bool(forward_evt.is_set()) if forward_evt is not None else False
        except Exception:
            forward_evt = None
        clip_state = str(getattr(ctx, "clip_state", "") or "")

        def _inline_after_prep() -> tuple:
            prepare_join_ms = None
            try:
                prep = ctx.join_unet_source_prep(timeout_s=_PREP_JOIN_TIMEOUT_S)
                prepare_join_ms = (
                    prep.get("wall_ms") if isinstance(prep, dict) else None
                )
                timings["prep"] = prep if isinstance(prep, dict) else None
            except Exception:
                timings["prep"] = None
            timings["prepare_join_ms"] = prepare_join_ms
            return _gpu_phase_with_arbitration(
                ctx, owner_holder, path,
                f"cuda:{torch.cuda.current_device()}",
                model_options, rid, trace, timings,
            )

        if forwarded or clip_state == "critical_done":
            # Case a: CLIP already forwarded — inline join + GPU phase.
            ordering = "after_clip"
            patcher, _loader, _fb = _inline_after_prep()
        elif forward_evt is not None and clip_state and clip_state not in (
            "pending",
            "none",
            "idle",
            "not_started",
        ):
            # Case b: clip loaded but forward not done — background
            # continuation waits for the forward-done event; the node wrapper
            # waits on ctx.result("unet").  SAFE: CLIPTextEncode executes
            # later in the same sequential graph and sets the event.
            ordering = "after_clip"

            def _continuation() -> None:
                try:
                    if forward_evt is not None and not forward_evt.wait(
                        _CLIP_FORWARD_WAIT_S
                    ):
                        raise RuntimeError("clip_forward_wait_timeout")
                    patcher, _cont_loader, _cont_fb = _inline_after_prep()
                    # R44D: case b returns from the wrapper before the C7
                    # bookkeeping runs, so record the observed FastSafe arm
                    # here (the physical transport DID execute).
                    try:
                        from . import loader_selection as _ls

                        _ls.record_observed("unet", "fastsafetensors")
                    except Exception:
                        pass
                    ctx.publish_result("unet", patcher)
                    try:
                        from . import gpu_lane_coordination as coord

                        coord.record_unet_ready(rid, trace, reason="request_fastsafe")
                    except Exception:
                        pass
                    _publish_success_telemetry(ctx, ordering, timings)
                except Exception as exc:
                    _fail_closed(
                        ctx, f"{type(exc).__name__}:{str(exc)[:100]}",
                        loader=owner_holder.get("loader"),
                        fb=owner_holder.get("fb"),
                        ordering=ordering, timings=timings,
                    )
                    try:
                        ctx.publish_result(
                            "unet",
                            {"_comfymodal_unet_fastsafe_error": str(exc)[:120]},
                        )
                    except Exception:
                        pass

            worker = threading.Thread(
                target=_continuation,
                name="comfymodal-request-unet-fastsafe",
                daemon=True,
            )
            worker.start()
            payload = None
            try:
                # Bounded wait matching the continuation's own bound: without
                # a timeout result() returns immediately and this wrapper
                # would fall back natively while the continuation still runs.
                payload = ctx.result("unet", timeout_s=_CLIP_FORWARD_WAIT_S)
            except Exception:
                payload = None
            if isinstance(payload, dict):
                # Continuation failed closed; fall through to ORIGINAL once.
                return original(instance, unet_name, weight_dtype)
            if payload is None:
                _fail_closed(ctx, "result_future_empty", ordering=ordering,
                             timings=timings)
                return original(instance, unet_name, weight_dtype)
            return (payload,)
        else:
            # Case c: UNETLoader arrived BEFORE the CLIP nodes — waiting would
            # deadlock.  Run the GPU phase INLINE NOW (no clip critical is
            # held, so begin_unet_gpu_phase succeeds; overlap is lost in this
            # ordering — correctness wins).
            ordering = "inline"
            try:
                ctx.telemetry(
                    "unet_request_ordering", mode="unet_first_serial"
                )
            except Exception:
                pass
            patcher, _loader, _fb = _inline_after_prep()

        # C7: success (cases a/c reach here; case b returned above).
        try:
            ctx.publish_result("unet", patcher)
        except Exception:
            pass
        try:
            from . import gpu_lane_coordination as coord

            coord.record_unet_ready(rid, trace, reason="request_fastsafe")
        except Exception:
            pass
        try:
            from . import loader_selection as _ls

            _ls.record_observed("unet", "fastsafetensors")
        except Exception:
            pass
        _publish_success_telemetry(ctx, ordering, timings)
        return (patcher,)
    except RuntimeError as exc:
        # Race-arbiter retry exhaustion or any adoption gate failure.
        _fail_closed(
            ctx, f"{type(exc).__name__}:{str(exc)[:100]}",
            loader=owner_holder.get("loader"), fb=owner_holder.get("fb"),
            ordering=ordering, timings=timings,
        )
        return original(instance, unet_name, weight_dtype)
    except Exception as exc:
        _fail_closed(
            ctx, f"{type(exc).__name__}:{str(exc)[:100]}",
            loader=owner_holder.get("loader"), fb=owner_holder.get("fb"),
            ordering=ordering, timings=timings,
        )
        return original(instance, unet_name, weight_dtype)


def _publish_success_telemetry(ctx: Any, ordering: str, timings: dict) -> None:
    try:
        matched = timings.get("storage_identity_matched")
        total = timings.get("storage_identity_total")
        fm = timings.get("fastsafe_metrics") or {}
        fwd_start = fwd_end = None
        try:
            fwd_start, fwd_end = ctx.clip_forward_window()
        except Exception:
            fwd_start = fwd_end = None
        stamps = None
        try:
            stamps = ctx.prep_stamps()
        except Exception:
            stamps = None
        prep_armed_at = prep_start = join_start = join_end = None
        if isinstance(stamps, dict):
            prep_armed_at = stamps.get("armed_at_mono_ns")
            prep_start = stamps.get("prep_start_mono_ns")
            join_start = stamps.get("prep_join_start_mono_ns")
            join_end = stamps.get("prep_join_end_mono_ns")
        overlap_ms = None
        overlap_pct = tail_fwd_end = tail_demand = None
        if None not in (prep_start, join_end, fwd_start, fwd_end):
            try:
                from .request_fastpath import interval_overlap_ms

                overlap_ms = interval_overlap_ms(prep_start, join_end, fwd_start, fwd_end)
                prep_span = max(int(join_end) - int(prep_start), 1)
                overlap_pct = round((float(overlap_ms or 0.0) * 1e6) / prep_span * 100.0, 2)
                tail_fwd_end = round(max(0, int(join_end) - int(fwd_end)) / 1e6, 3)
                tail_demand = round(max(0, int(join_start) - int(fwd_end)) / 1e6, 3)
            except Exception:
                overlap_ms = overlap_pct = tail_fwd_end = tail_demand = None
        ctx.telemetry(
            "unet_fastsafe_pipeline",
            status="ok",
            phase="request",
            file_to_gpu_wall_ms=timings.get("file_to_gpu_wall_ms"),
            prepare_join_ms=timings.get("prepare_join_ms"),
            adopt_ms=timings.get("adopt_ms"),
            storage_identity_matched=matched,
            storage_identity_total=total,
            owner_retained=True,
            ordering=ordering,
            fastsafe_setup_wall_ms=fm.get("fastsafe_setup_wall_ms"),
            fastsafe_copy_wall_ms=fm.get("fastsafe_file_gpu_wall_ms"),
            fastsafe_instantiate_wall_ms=fm.get("fastsafe_instantiate_wall_ms"),
            header_detect_wall_ms=fm.get("header_detect_wall_ms"),
            skeleton_wall_ms=fm.get("skeleton_wall_ms"),
            bind_wall_ms=fm.get("bind_wall_ms"),
            identity_validation_wall_ms=fm.get("identity_validation_wall_ms"),
            gate_wait_ms=timings.get("gate_wait_ms"),
            copied_count=(
                None if matched is None or total is None else max(0, int(total) - int(matched))
            ),
            bind_mode=(
                "same_storage"
                if (matched or 0) > 0 and (total or 0) > 0
                else "copy_cuda"
            ),
            final_validation_all_params_on_target=bool(
                (fm.get("final_validation") or {}).get("all_params_on_target")
            ),
            clip_forward_start_mono_ns=fwd_start,
            clip_forward_end_mono_ns=fwd_end,
            prep_armed_at_mono_ns=prep_armed_at,
            prep_start_mono_ns=prep_start,
            prep_join_start_mono_ns=join_start,
            prep_join_end_mono_ns=join_end,
            unet_prep_overlap_ms=overlap_ms,
            unet_prep_overlap_pct_of_prep=overlap_pct,
            unet_prep_tail_at_forward_end_ms=tail_fwd_end,
            unet_prep_tail_at_demand_ms=tail_demand,
        )
    except Exception:
        pass


def _weight_dtype_to_torch(weight_dtype: str) -> Any:
    """Mirror nodes.UNETLoader.load_unet's model_options['dtype'] mapping."""
    import torch

    wd = str(weight_dtype or "default")
    if wd == "fp8_e4m3fn":
        return getattr(torch, "float8_e4m3fn", None)
    if wd == "fp8_e4m3fn_fast":
        return getattr(torch, "float8_e4m3fn", None)
    if wd == "fp8_e5m2":
        return getattr(torch, "float8_e5m2", None)
    return None


def _build_model_options(weight_dtype: str) -> dict:
    """Exact nodes.UNETLoader.load_unet model_options construction."""
    model_options: dict[str, Any] = {}
    dtype = _weight_dtype_to_torch(weight_dtype)
    if dtype is not None:
        model_options["dtype"] = dtype
    if str(weight_dtype or "") == "fp8_e4m3fn_fast":
        model_options["fp8_optimizations"] = True
    return model_options


def _fastsafe_eligible(unet_name: str, weight_dtype: str) -> tuple[bool, str]:
    """E28-proven capability guards (unet_fastsafetensors._fs_eligible):
    ZImage family, value probe, high-VRAM, quant/custom-op/fp8 evidence,
    default weight_dtype, uniform supported dtype, CUDA + fastsafetensors
    availability.  Path resolution inside matches the node's own logic."""
    try:
        from . import unet_fastsafetensors as _fs

        return _fs._fs_eligible(
            None,
            {"unet_name": unet_name, "weight_dtype": weight_dtype},
            None,
        )
    except Exception:
        return (False, "eligibility_error")


# ── Installer ─────────────────────────────────────────────────────────────


def install_request_unet_fastsafe(trace: Any = None) -> bool:
    """Idempotently wrap ``NODE_CLASS_MAPPINGS["UNETLoader"].load_unet``.

    Mirrors the V2LoaderBridge.install sentinel pattern: the original method
    is stored on the wrapper under ``_comfymodal_r44b_original``.  Returns
    True when the wrapper was installed by THIS call, False when already
    installed (or the node class is unavailable)."""
    global _INSTALLED
    with _INSTALL_LOCK:
        try:
            import nodes as nodes_module
        except Exception:
            return False
        mapping = getattr(nodes_module, "NODE_CLASS_MAPPINGS", None)
        cls = mapping.get("UNETLoader") if isinstance(mapping, dict) else None
        if cls is None:
            return False
        current = getattr(cls, "load_unet", None)
        if current is None:
            return False
        if getattr(current, _SENTINEL_ATTR, None) is not None:
            return False
        original = getattr(current, "_comfy_modal_v2_original", None) or current

        def _wrapped_load_unet(self, unet_name, weight_dtype):
            # Fast path: no request context / feature disabled -> original.
            try:
                from . import request_fastpath as _rfp

                if not _rfp.enabled() or not _rfp.unet_enabled():
                    return original(self, unet_name, weight_dtype)
                ctx = _rfp.current()
                if ctx is None:
                    return original(self, unet_name, weight_dtype)
            except Exception:
                return original(self, unet_name, weight_dtype)
            return _load_unet_via_fastsafe(
                ctx, unet_name, weight_dtype, original, self
            )

        setattr(_wrapped_load_unet, _SENTINEL_ATTR, original)
        try:
            import functools

            _wrapped_load_unet = functools.wraps(current)(_wrapped_load_unet)
            setattr(_wrapped_load_unet, _SENTINEL_ATTR, original)
        except Exception:
            pass
        cls.load_unet = _wrapped_load_unet
        _INSTALLED = True
        if trace is not None:
            try:
                trace.emit(
                    "request_unet_fastsafe_installed",
                    phase="execution",
                    metadata={"sentinel": _SENTINEL_ATTR},
                )
            except Exception:
                pass
        return True


def uninstall_for_tests() -> bool:
    """Restore the original ``UNETLoader.load_unet`` (test-only)."""
    global _INSTALLED
    with _INSTALL_LOCK:
        try:
            import nodes as nodes_module
        except Exception:
            return False
        mapping = getattr(nodes_module, "NODE_CLASS_MAPPINGS", None)
        cls = mapping.get("UNETLoader") if isinstance(mapping, dict) else None
        if cls is None:
            return False
        current = getattr(cls, "load_unet", None)
        original = getattr(current, _SENTINEL_ATTR, None) if current is not None else None
        if original is None:
            return False
        cls.load_unet = original
        _INSTALLED = False
        return True
