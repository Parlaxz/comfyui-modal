"""Request-scoped generic fast-loader composition over shared Golden cores.

Generic (non-canonical) v2 plan runs execute arbitrary graphs through the
upstream executor with native per-node file reads.  This module lets those
runs reuse THE SAME Golden loader implementations (imported, never copied)
for supported loader nodes:

* classify each loader node (supported / unsupported + reason),
* invoke the unmodified ``golden_*_load`` stage functions with a REAL
  ``GoldenSession`` built for the generic request,
* insert the adopted model objects into the executor output cache so the
  native node functions hit cache and skip their file reads,
* retain QD owners for exactly the request duration, then release them
  WITHOUT touching the shared dispatcher or any canonical lifecycle.

Activation is strictly generic-path: the installer is only ever called from
the v2 plan-execution flow, which canonical Golden runs never enter (they
would trip ``golden_prompt_executor_forbidden``).  Every failure — unsupported
contract, missing file, loader error — falls back to the native path and is
recorded per node.  Nothing here mutates canonical behavior.

Phase 1 covers CLIPLoader only (the slowest loader on measured workloads).
VAELoader and UNETLoader classify explicitly so their status is observable;
UNET scaled-FP8 in particular is contractually rejected by the shared core
and must stay native.

Two shared source-read arms are attempted in order, both imported never
copied:

* ``qd4_demand`` (first): the canonical ``clip_qd_load`` demand reader —
  self-contained per call (workers joined before return, no persistent
  pool), so it is immune to persistent-pool poisoning.  Construction
  mirrors the native CLIPLoader recipe exactly over the same shared
  ``comfy.sd.load_text_encoder_state_dicts`` delegation; only the
  file-read step is fast.
* ``m2_transport`` (fallback): the persistent M2 singleton via the
  unmodified ``golden_clip_load`` stage.  Currently fails closed
  fleet-wide (persistent source pool poisoned by a cancelled dispatcher
  handoff); kept so a healthy pool is used when available.
"""

from __future__ import annotations

import os
import time
import json
from typing import Any, Callable, Mapping, Sequence

from .golden_aimdo_activation import activate_golden_dynamic_vram


# Loader classes this composition knows how to classify.  Only CLIPLoader
# has a composed fast path today; the rest report explicit reasons.
_KNOWN_LOADER_CLASSES = frozenset({
    "CLIPLoader",
    "DualCLIPLoader",
    "VAELoader",
    "UNETLoader",
    "CheckpointLoader",
    "CheckpointLoaderSimple",
})

# Roles mirror the canonical role map so accounting stays comparable.
_ROLE_MAP = {
    "CLIPLoader": "clip",
    "DualCLIPLoader": "clip",
    "VAELoader": "vae",
    "UNETLoader": "unet",
    "CheckpointLoader": "checkpoint",
    "CheckpointLoaderSimple": "checkpoint",
}


def classify_loader_node(
    class_type: str,
    inputs: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Classify one loader node for shared-core composition (pure logic).

    Returns ``{"supported": bool, "role": str, "reason": str, ...}``.
    Supported means: attempt the shared Golden core; anything else means run
    the native node function untouched.  Never raises.
    """
    class_type = str(class_type or "")
    inputs = inputs if isinstance(inputs, dict) else {}
    role = _ROLE_MAP.get(class_type, "?")
    unsupported = {"supported": False, "role": role, "reason": ""}
    if class_type not in _KNOWN_LOADER_CLASSES:
        unsupported["reason"] = "unknown_loader_class"
        return unsupported
    if class_type in ("CheckpointLoader", "CheckpointLoaderSimple"):
        unsupported["reason"] = "checkpoint_not_role_separable"
        return unsupported
    if class_type == "DualCLIPLoader":
        unsupported["reason"] = "dual_clip_deferred"
        return unsupported
    if class_type == "UNETLoader":
        unsupported["reason"] = "unet_deferred"
        return unsupported
    if class_type == "VAELoader":
        unsupported["reason"] = "vae_deferred"
        return unsupported
    # CLIPLoader from here on.
    clip_name = inputs.get("clip_name")
    if not isinstance(clip_name, str) or not clip_name.strip():
        unsupported["reason"] = "clip_name_missing"
        return unsupported
    device = inputs.get("device", "default")
    if isinstance(device, str) and device.strip().lower() == "cpu":
        return dict(supported=False, role=role,
                    reason="explicit_cpu_device_respected")
    clip_type = inputs.get("type", "stable_diffusion")
    if not isinstance(clip_type, str) or not clip_type.strip():
        clip_type = "stable_diffusion"
    return dict(supported=True, role=role, reason="",
                clip_name=str(clip_name), clip_type=str(clip_type),
                device=str(device or "default"))


def resolve_clip_type_shared(name: str) -> Any:
    """Resolve a CLIPType via the shared Golden resolver (no fallback here)."""
    from .golden_serial import resolve_clip_type

    return resolve_clip_type(name)


def _default_path_resolver(folder: str, filename: str) -> str | None:
    """Resolve a model filename to an absolute path via folder_paths."""
    try:
        import folder_paths

        path = folder_paths.get_full_path(folder, filename)
        if path and os.path.isfile(path):
            return path
        return None
    except Exception:
        return None


class GenericLoaderHolder:
    """Retains generic-composition sessions/owners for one request.

    QD owners backing adopted models must outlive executor cache use.
    Release happens exactly once at request end via :meth:`close`, which
    releases single owners WITHOUT shutting down the shared dispatcher.
    Idempotent and never raises.
    """

    def __init__(self) -> None:
        self._sessions: list[Any] = []
        self._owners: list[Any] = []
        self._closed = False

    def retain(self, session: Any, owners: Sequence[Any] | None = None) -> None:
        if session is not None:
            self._sessions.append(session)
        for owner in list(owners or []):
            if owner is not None:
                self._owners.append(owner)

    def close(self) -> dict[str, Any]:
        """Release retained single owners. Never touches the dispatcher."""
        result = {"released": 0, "errors": 0}
        if self._closed:
            result["already_closed"] = True
            return result
        self._closed = True
        for owner in self._owners:
            try:
                release = getattr(owner, "release_storage", None)
                if callable(release):
                    release()
                else:
                    close = getattr(owner, "close", None)
                    if callable(close):
                        close()
                result["released"] += 1
            except Exception:
                result["errors"] += 1
        self._owners.clear()
        self._sessions.clear()
        return result


def build_generic_clip_session(
    *,
    clip_filenames: Sequence[str],
    clip_type: str,
    folder: str,
    request_id: str,
    volume: Any = None,
    request_extra: Mapping[str, Any] | None = None,
) -> Any:
    """Build a REAL GoldenSession adapted for one generic CLIP load.

    Uses the same session/contract/spec classes as canonical runs; only the
    inputs differ (actual node filenames/type instead of frozen canonical
    values).  No golden_serial.py changes required.
    """
    from .golden_serial import (
        ClipLoadSpec,
        GoldenRequest,
        GoldenSession,
        GoldenWorkflowContract,
    )

    names = tuple(str(n) for n in (clip_filenames or []) if str(n or "").strip())
    if not names:
        raise ValueError("generic_clip_filenames_missing")
    spec = ClipLoadSpec(
        checkpoint_names=names,
        clip_type=str(clip_type or "stable_diffusion"),
        folder=str(folder or "text_encoders"),
    )
    contract = GoldenWorkflowContract(clip_spec=spec)
    extra = dict(request_extra or {})
    extra.setdefault("generic_loader_composition", True)
    extra.setdefault("golden_mode", "serial")
    request = GoldenRequest(
        request_id=str(request_id or "generic-clip"),
        prompt={},
        extra_data=extra,
    )
    session = GoldenSession(
        request,
        volume=volume,
        contract=contract,
    )
    return session


async def compose_generic_clip_load(
    *,
    clip_filenames: Sequence[str],
    clip_type: str,
    folder: str,
    request_id: str,
    path_resolver: Callable[[str, str], str | None] | None = None,
    volume: Any = None,
) -> dict[str, Any]:
    """Load CLIP via the SHARED Golden core (same code canonical runs use).

    Returns ``{"ok": True, "clip": ..., "session": ..., "owners": [...],
    " elapsed_ms": ...}`` or ``{"ok": False, "reason": ...}``.  Never raises:
    every failure must fall back to the native node function.
    """
    started_ns = time.monotonic_ns()
    resolve = path_resolver or _default_path_resolver
    try:
        names = [str(n) for n in (clip_filenames or []) if str(n or "").strip()]
        if not names:
            return {"ok": False, "reason": "clip_filenames_missing"}
        resolved: list[str] = []
        for name in names:
            path = resolve(folder, name)
            if not path:
                return {"ok": False, "reason": f"clip_path_unresolvable:{name}"}
            resolved.append(path)
        from .golden_serial import golden_clip_load

        session = build_generic_clip_session(
            clip_filenames=names,
            clip_type=clip_type,
            folder=folder,
            request_id=request_id,
            volume=volume,
        )
        # The stage reads full paths from the session (same as canonical).
        session.clip_paths = list(resolved)
        clip = await golden_clip_load(session)
        owners = list(getattr(session, "clip_owners", None) or [])
        elapsed_ms = (time.monotonic_ns() - started_ns) / 1_000_000.0
        return {
            "ok": True,
            "clip": clip,
            "session": session,
            "owners": owners,
            "elapsed_ms": elapsed_ms,
            "reason": "",
        }
    except Exception as exc:  # noqa: BLE001 - fallback contract: never raise
        elapsed_ms = (time.monotonic_ns() - started_ns) / 1_000_000.0
        return {
            "ok": False,
            "reason": f"{type(exc).__name__}:{str(exc)[:200]}",
            "elapsed_ms": elapsed_ms,
        }


def _ensure_stage_dynamic_vram(
    trace_emit: Callable[..., Any] | None, request_id: str
) -> tuple[bool, str]:
    """Ensure DynamicVRAM activation before golden stage loads.

    Calls the sanctioned ``activate_golden_dynamic_vram`` (the
    main.py-equivalent rebind the CLI sequence never performs on workers;
    idempotent per process, verified, fail-closed).  Golden CLIP/VAE
    stages reject requests without it (``*_dynamic_core_model_patcher_
    required``).  Returns ``(True, detail)`` when active, ``(False,
    reason)`` otherwise — both mean native fallback, never raise.  The
    only shared-state effect is the sanctioned activation itself, which
    canonical requests perform on these workers as a matter of course.
    """
    try:
        evidence = activate_golden_dynamic_vram()
        if isinstance(evidence, dict) and (
            evidence.get("activated") or evidence.get("already_activated")
        ):
            return True, (
                "already" if evidence.get("already_activated") else "activated"
            )
        reason = ""
        if isinstance(evidence, dict):
            reason = str(evidence.get("reason") or "gate_not_set")
        _emit_trace(
            trace_emit, "generic_dynamic_vram", outcome="skipped",
            reason=reason or "dynamic_vram_gate_not_set",
            request_id=str(request_id or ""),
        )
        return False, reason or "dynamic_vram_gate_not_set"
    except Exception as exc:  # noqa: BLE001 - activation is best-effort here
        detail = f"{type(exc).__name__}:{str(exc)[:150]}"
        _emit_trace(
            trace_emit, "generic_dynamic_vram", outcome="failed",
            reason=detail, request_id=str(request_id or ""),
        )
        return False, detail


async def compose_generic_clip_load_stage(
    *,
    clip_filenames: Sequence[str],
    clip_type: str,
    folder: str,
    request_id: str,
    path_resolver: Callable[[str, str], str | None] | None = None,
    volume: Any = None,
) -> dict[str, Any]:
    """Load CLIP via the SHARED ``golden_clip_load`` stage with the shared
    model transport (same selection as canonical runs: the session carries
    no source-policy override, so an enabled shared transport serves the
    read; every container is fresh, so no cross-run pool state exists).

    Same shared construction/adoption/proof as canonical runs; only the
    source-read arm differs (session-local policy, no environment toggle).
    Mixed-dtype files take the stage's observable proof-downgrade path
    instead of failing outright.  Returns ``{"ok": True, "clip": ...,
    "session": ..., "owners": [...], "source_arm": "golden_clip", ...}``
    or ``{"ok": False, "reason": ...}``.  Never raises.
    """
    started_ns = time.monotonic_ns()
    resolve = path_resolver or _default_path_resolver
    try:
        names = [str(n) for n in (clip_filenames or []) if str(n or "").strip()]
        if not names:
            return {"ok": False, "reason": "clip_filenames_missing",
                    "source_arm": "golden_clip"}
        resolved: list[str] = []
        for name in names:
            path = resolve(folder, name)
            if not path:
                return {"ok": False,
                        "reason": f"clip_path_unresolvable:{name}",
                        "source_arm": "golden_clip"}
            resolved.append(path)
        from .golden_serial import golden_clip_load

        session = build_generic_clip_session(
            clip_filenames=names,
            clip_type=clip_type,
            folder=folder,
            request_id=request_id,
            volume=volume,
        )
        # No source-policy override: the session takes the canonical
        # transport selection (shared transport when enabled), exactly
        # like canonical runs.  Every container is fresh, so no
        # cross-run pool state exists to isolate from.
        vram_ok, vram_detail = _ensure_stage_dynamic_vram(None, request_id)
        if not vram_ok:
            elapsed_ms = (time.monotonic_ns() - started_ns) / 1_000_000.0
            return {"ok": False,
                    "reason": f"dynamic_vram_unavailable:{vram_detail}",
                    "elapsed_ms": elapsed_ms,
                    "source_arm": "golden_clip"}
        # The stage reads full paths from the session (same as canonical).
        session.clip_paths = list(resolved)
        # QD publication must produce ordinary mutable tensors: the executor
        # runs under inference mode, and the legacy transport plus the
        # assign=True adoption perform in-place updates that inference
        # tensors forbid.  Mirrors the clip_qd_reader publication boundary
        # (same requirement, same guard).  Stage-local only.
        import torch as _torch

        with _torch.inference_mode(False):
            clip = await golden_clip_load(session)
        owners = list(getattr(session, "clip_owners", None) or [])
        # Post-construction de-quant walk (same as the QD4 arm): drops _v
        # offload-view markers that crash the low-VRAM gather path on
        # quantized-storage / wider-compute layers, and normalizes
        # hostile-shape quantized linears.  Operates on OUR object only.
        _stage_layer_report = force_plain_hostile_linears(
            clip, tag="stage-clip")
        _log_clip_placement("stage", clip)
        elapsed_ms = (time.monotonic_ns() - started_ns) / 1_000_000.0
        return {
            "ok": True,
            "clip": clip,
            "session": session,
            "owners": owners,
            "elapsed_ms": elapsed_ms,
            "reason": "",
            "source_arm": "golden_clip",
            "fp8_layer_dequant": _stage_layer_report,
        }
    except Exception as exc:  # noqa: BLE001 - fallback contract: never raise
        elapsed_ms = (time.monotonic_ns() - started_ns) / 1_000_000.0
        try:
            import traceback as _traceback_mod

            _tb_text = _traceback_mod.format_exc(limit=12)
        except Exception:
            _tb_text = ""
        return {
            "ok": False,
            "reason": (
                f"{type(exc).__name__}:{str(exc)[:200]}"
                + (f" | tb:{_tb_text[-1200:]}" if _tb_text else "")
            ),
            "elapsed_ms": elapsed_ms,
            "source_arm": "golden_clip",
        }


def build_generic_unet_session(
    *,
    unet_filename: str,
    request_id: str,
    folder: str = "diffusion_models",
    volume: Any = None,
    request_extra: Mapping[str, Any] | None = None,
) -> Any:
    """Build a REAL GoldenSession adapted for one generic UNET load.

    Mirrors the canonical request setup: contract carries the real
    filename with ``expected_unet_tensor_count=0`` (the supported
    derive-from-model mode for caller-selected replacement UNETs —
    same value canonical setup uses for non-canonical models), full
    paths go on ``session.model_paths``, and transport selection is
    canonical (no source-policy override).
    No golden_serial.py changes required.
    """
    from .golden_serial import (
        GoldenRequest,
        GoldenSession,
        GoldenWorkflowContract,
    )

    name = str(unet_filename or "").strip()
    if not name:
        raise ValueError("generic_unet_filename_missing")
    contract = GoldenWorkflowContract(
        unet_name=name,
        expected_unet_tensor_count=0,
    )
    extra = dict(request_extra or {})
    extra.setdefault("generic_loader_composition", True)
    extra.setdefault("golden_mode", "serial")
    request = GoldenRequest(
        request_id=str(request_id or "generic-unet"),
        prompt={},
        extra_data=extra,
    )
    session = GoldenSession(
        request,
        volume=volume,
        contract=contract,
    )
    # No source-policy override: canonical transport selection applies,
    # exactly like canonical runs (see the CLIP composer above).
    session.canonical_models = False
    return session


def build_generic_vae_session(
    *,
    vae_filename: str,
    request_id: str,
    folder: str = "vae",
    volume: Any = None,
    request_extra: Mapping[str, Any] | None = None,
) -> Any:
    """Build a REAL GoldenSession adapted for one generic VAE load.

    Same shape as :func:`build_generic_unet_session`: real filename on
    the contract, full path on ``session.model_paths``, canonical
    transport selection.  No golden_serial.py changes required.
    """
    from .golden_serial import (
        GoldenRequest,
        GoldenSession,
        GoldenWorkflowContract,
    )

    name = str(vae_filename or "").strip()
    if not name:
        raise ValueError("generic_vae_filename_missing")
    contract = GoldenWorkflowContract(
        vae_name=name,
    )
    extra = dict(request_extra or {})
    extra.setdefault("generic_loader_composition", True)
    extra.setdefault("golden_mode", "serial")
    request = GoldenRequest(
        request_id=str(request_id or "generic-vae"),
        prompt={},
        extra_data=extra,
    )
    session = GoldenSession(
        request,
        volume=volume,
        contract=contract,
    )
    # No source-policy override: canonical transport selection applies,
    # exactly like canonical runs (see the CLIP composer above).
    session.canonical_models = False
    return session


async def compose_generic_unet_load_qd(
    *,
    unet_filenames: Sequence[str],
    folder: str = "diffusion_models",
    request_id: str,
    path_resolver: Callable[[str, str], str | None] | None = None,
) -> dict[str, Any]:
    """Load UNET via the SHARED QD demand reader plus native construction.

    Mirrors the live-proven QD4-CLIP recipe, transposed to diffusion
    models: the canonical ``clip_qd_load`` reader moves bytes (it is
    file-type agnostic; dtype membership is validated by the shared map),
    ``*.comfy_quant`` descriptors ride CPU-only, real safetensors header
    metadata flows into the shared upstream
    ``comfy.sd.load_diffusion_model_state_dict`` delegation, and the
    result carries the native ``cached_patcher_init`` shape.  No golden
    stage is entered, so file contracts that the stage rejects
    (scaled-FP8 / mixed dtypes) load with native semantics — identical
    correctness to today, minus the file re-read.  Never raises.
    """
    started_ns = time.monotonic_ns()
    resolve = path_resolver or _default_path_resolver
    try:
        names = [str(n) for n in (unet_filenames or []) if str(n or "").strip()]
        if not names:
            return {"ok": False, "reason": "unet_filenames_missing",
                    "source_arm": "qd_unet_demand"}
        if len(names) > 1:
            return {"ok": False, "reason": "unet_multi_checkpoint_deferred",
                    "source_arm": "qd_unet_demand"}
        path = resolve(folder, names[0])
        if not path:
            return {"ok": False,
                    "reason": f"unet_path_unresolvable:{names[0]}",
                    "source_arm": "qd_unet_demand"}
        t_resolved_ns = time.monotonic_ns()
        from .clip_qd_reader import clip_qd_load, qd_config

        cfg = qd_config() or {}
        qd_value = int(cfg.get("qd", 0) or 0)
        block_mib = int(cfg.get("block_mib", 0) or 0)
        launch_policy = str(cfg.get("launch_policy", "") or "")
        if not bool(cfg.get("enabled")):
            return {"ok": False, "reason": "qd_unet_gate_disabled",
                    "source_arm": "qd_unet_demand"}
        if qd_value != 4:
            return {"ok": False,
                    "reason": f"qd_unet_gate_qd_not_4:{qd_value}",
                    "source_arm": "qd_unet_demand"}
        if block_mib < 1 or not launch_policy:
            return {"ok": False, "reason": "qd_unet_gate_config_incomplete",
                    "source_arm": "qd_unet_demand"}
        t_gated_ns = time.monotonic_ns()
        sd, loader, owner = clip_qd_load(
            path,
            qd=qd_value,
            block_mib=block_mib,
            trace=None,
            launch_policy=launch_policy,
            artifact_path=cfg.get("artifact_path") or None,
        )
        t_read_ns = time.monotonic_ns()
        sd = _cpu_native_quant_markers(sd)
        import comfy.sd

        file_metadata: dict[str, Any] = {}
        try:
            if str(path).lower().endswith((".safetensors", ".sft")):
                from safetensors import safe_open as _safe_open

                with _safe_open(path, framework="pt", device="cpu") as _hdr:
                    _meta = _hdr.metadata()
                    if isinstance(_meta, dict):
                        file_metadata = dict(_meta)
        except Exception:
            file_metadata = {}
        t_prep_ns = time.monotonic_ns()
        # Selective FP8->BF16 upcast (generic shape rule): hostile-shape FP8
        # weights become plain BF16 BEFORE the loader's internal
        # convert_old_quants, and the metadata copy is scrubbed of them so
        # no descriptor is re-attached.  Aligned FP8 stays native.
        _install_fp8_fallback_log_guard()
        sd, file_metadata, fp8_upcast_report = selective_fp8_bf16_upcast(
            sd, file_metadata)
        vram_ok, vram_detail = _ensure_stage_dynamic_vram(None, request_id)
        if not vram_ok:
            elapsed_ms = (time.monotonic_ns() - started_ns) / 1_000_000.0
            return {"ok": False,
                    "reason": f"dynamic_vram_unavailable:{vram_detail}",
                    "elapsed_ms": elapsed_ms,
                    "source_arm": "qd_unet_demand"}
        import torch as _torch_unet_qd

        with _torch_unet_qd.inference_mode(False):
            patcher = comfy.sd.load_diffusion_model_state_dict(
                sd,
                model_options={},
                metadata=file_metadata or None,
            )
        if patcher is None:
            elapsed_ms = (time.monotonic_ns() - started_ns) / 1_000_000.0
            return {"ok": False, "reason": "unet_model_config_undetected",
                    "elapsed_ms": elapsed_ms,
                    "source_arm": "qd_unet_demand"}
        try:
            patcher.cached_patcher_init = (
                comfy.sd.load_diffusion_model,
                (path, {}),
            )
        except Exception:
            pass
        # Post-construction de-quant walk: loader fusion can build hostile
        # GEMM dims no file scan can see.  Generic shape rule on OUR object.
        fp8_layer_report = force_plain_hostile_linears(patcher, tag="unet")
        t_construct_ns = time.monotonic_ns()
        elapsed_ms = (t_construct_ns - started_ns) / 1_000_000.0
        phases = {
            "resolve_ms": round((t_resolved_ns - started_ns) / 1_000_000.0, 1),
            "gate_ms": round((t_gated_ns - t_resolved_ns) / 1_000_000.0, 1),
            "read_ms": round((t_read_ns - t_gated_ns) / 1_000_000.0, 1),
            "prep_ms": round((t_prep_ns - t_read_ns) / 1_000_000.0, 1),
            "construct_ms": round((t_construct_ns - t_prep_ns) / 1_000_000.0, 1),
        }
        owners = [o for o in (loader, owner) if o is not None]
        return {
            "ok": True,
            "loaded": patcher,
            "session": None,
            "owners": owners,
            "elapsed_ms": elapsed_ms,
            "reason": "",
            "source_arm": "qd_unet_demand",
            "phases": phases,
            "fp8_selective_upcast": fp8_upcast_report,
            "fp8_layer_dequant": fp8_layer_report,
        }
    except Exception as exc:  # noqa: BLE001 - fallback contract: never raise
        elapsed_ms = (time.monotonic_ns() - started_ns) / 1_000_000.0
        try:
            import traceback as _traceback_mod

            _tb_text = _traceback_mod.format_exc(limit=12)
        except Exception:
            _tb_text = ""
        return {
            "ok": False,
            "reason": (
                f"{type(exc).__name__}:{str(exc)[:200]}"
                + (f" | tb:{_tb_text[-1200:]}" if _tb_text else "")
            ),
            "elapsed_ms": elapsed_ms,
            "source_arm": "qd_unet_demand",
        }


async def compose_generic_unet_load(
    *,
    unet_filenames: Sequence[str],
    folder: str = "diffusion_models",
    request_id: str,
    path_resolver: Callable[[str, str], str | None] | None = None,
    volume: Any = None,
) -> dict[str, Any]:
    """Load UNET via the SHARED ``golden_unet_load`` stage (imported).

    Scaled-FP8 / non-uniform / unknown-dtype files are rejected by the
    stage contract itself (clean fallback reason, never an exception
    here).  Returns ``{"ok": True, "loaded": patcher, "session": ...,
    "owners": [...], "source_arm": "golden_unet", ...}`` or ``{"ok":
    False, "reason": ...}``.  Never raises.
    """
    started_ns = time.monotonic_ns()
    resolve = path_resolver or _default_path_resolver
    try:
        names = [str(n) for n in (unet_filenames or []) if str(n or "").strip()]
        if not names:
            return {"ok": False, "reason": "unet_filenames_missing",
                    "source_arm": "golden_unet"}
        if len(names) > 1:
            return {"ok": False, "reason": "unet_multi_checkpoint_deferred",
                    "source_arm": "golden_unet"}
        path = resolve(folder, names[0])
        if not path:
            return {"ok": False,
                    "reason": f"unet_path_unresolvable:{names[0]}",
                    "source_arm": "golden_unet"}
        # Header survey for contract diagnosis (proves the file's real
        # composition in the trace when the stage rejects it).
        header_info = _describe_safetensors_header(path)
        try:
            _hd = header_info if isinstance(header_info, dict) else {}
            _dtypes = ",".join(
                f"{k}:{v}" for k, v in sorted((_hd.get("dtypes") or {}).items()))
            header_bit = (
                f" | header:{_hd.get('tensors')}t[{_dtypes}]"
                f"sfp8x{_hd.get('scaled_fp8_key_count', 0)}"
                f"qmeta={int(bool(_hd.get('has_quantization_metadata')))}"
            ) if _hd.get("ok") else ""
        except Exception:
            header_bit = ""
            header_info = {"ok": False}
        from .golden_serial import golden_unet_load

        session = build_generic_unet_session(
            unet_filename=names[0],
            request_id=request_id,
            folder=folder,
            volume=volume,
        )
        session.model_paths = {"unet": path}
        vram_ok, vram_detail = _ensure_stage_dynamic_vram(None, request_id)
        if not vram_ok:
            elapsed_ms = (time.monotonic_ns() - started_ns) / 1_000_000.0
            return {"ok": False,
                    "reason": f"dynamic_vram_unavailable:{vram_detail}",
                    "elapsed_ms": elapsed_ms,
                    "source_arm": "golden_unet"}
        # Same inference-mode guard as the CLIP stage path: ordinary mutable
        # tensors for transport publication and assign=True adoption.
        import torch as _torch_unet

        with _torch_unet.inference_mode(False):
            patcher = await golden_unet_load(session)
        owners = [
            o for o in [getattr(session, "unet_owner", None)]
            if o is not None
        ]
        elapsed_ms = (time.monotonic_ns() - started_ns) / 1_000_000.0
        return {
            "ok": True,
            "loaded": patcher,
            "header": header_info,
            "session": session,
            "owners": owners,
            "elapsed_ms": elapsed_ms,
            "reason": "",
            "source_arm": "golden_unet",
        }
    except Exception as exc:  # noqa: BLE001 - fallback contract: never raise
        elapsed_ms = (time.monotonic_ns() - started_ns) / 1_000_000.0
        try:
            import traceback as _traceback_mod

            _tb_text = _traceback_mod.format_exc(limit=12)
        except Exception:
            _tb_text = ""
        return {
            "ok": False,
            "reason": (
                f"{type(exc).__name__}:{str(exc)[:200]}"
                + (f" | tb:{_tb_text[-1200:]}" if _tb_text else "")
                + (header_bit if "header_bit" in locals() else "")
            ),
            "elapsed_ms": elapsed_ms,
            "source_arm": "golden_unet",
        }


async def compose_generic_vae_load(
    *,
    vae_filenames: Sequence[str],
    folder: str = "vae",
    request_id: str,
    path_resolver: Callable[[str, str], str | None] | None = None,
    volume: Any = None,
) -> dict[str, Any]:
    """Load VAE via the SHARED ``golden_vae_load`` stage (imported).

    Same outcome shape as :func:`compose_generic_unet_load` with
    ``source_arm="golden_vae"``; the native tuple is ``(vae,)``.  Never
    raises.
    """
    started_ns = time.monotonic_ns()
    resolve = path_resolver or _default_path_resolver
    try:
        names = [str(n) for n in (vae_filenames or []) if str(n or "").strip()]
        if not names:
            return {"ok": False, "reason": "vae_filenames_missing",
                    "source_arm": "golden_vae"}
        if len(names) > 1:
            return {"ok": False, "reason": "vae_multi_checkpoint_deferred",
                    "source_arm": "golden_vae"}
        path = resolve(folder, names[0])
        if not path:
            return {"ok": False,
                    "reason": f"vae_path_unresolvable:{names[0]}",
                    "source_arm": "golden_vae"}
        from .golden_serial import golden_vae_load

        session = build_generic_vae_session(
            vae_filename=names[0],
            request_id=request_id,
            folder=folder,
            volume=volume,
        )
        session.model_paths = {"vae": path}
        vram_ok, vram_detail = _ensure_stage_dynamic_vram(None, request_id)
        if not vram_ok:
            elapsed_ms = (time.monotonic_ns() - started_ns) / 1_000_000.0
            return {"ok": False,
                    "reason": f"dynamic_vram_unavailable:{vram_detail}",
                    "elapsed_ms": elapsed_ms,
                    "source_arm": "golden_vae"}
        # Same inference-mode guard as the CLIP stage path: ordinary mutable
        # tensors for transport publication and assign=True adoption.
        import torch as _torch_vae

        with _torch_vae.inference_mode(False):
            vae = await golden_vae_load(session)
        owners = [
            o for o in [getattr(session, "vae_owner", None)]
            if o is not None
        ]
        elapsed_ms = (time.monotonic_ns() - started_ns) / 1_000_000.0
        return {
            "ok": True,
            "loaded": vae,
            "session": session,
            "owners": owners,
            "elapsed_ms": elapsed_ms,
            "reason": "",
            "source_arm": "golden_vae",
        }
    except Exception as exc:  # noqa: BLE001 - fallback contract: never raise
        elapsed_ms = (time.monotonic_ns() - started_ns) / 1_000_000.0
        try:
            import traceback as _traceback_mod

            _tb_text = _traceback_mod.format_exc(limit=12)
        except Exception:
            _tb_text = ""
        return {
            "ok": False,
            "reason": (
                f"{type(exc).__name__}:{str(exc)[:200]}"
                + (f" | tb:{_tb_text[-1200:]}" if _tb_text else "")
            ),
            "elapsed_ms": elapsed_ms,
            "source_arm": "golden_vae",
        }


def _cpu_native_quant_markers(state_dict: Any) -> Any:
    """Move ``*.comfy_quant`` descriptor tensors to CPU (metadata, not weights).

    Quantized releases ship per-layer JSON descriptors under
    ``<layer>.comfy_quant`` keys; loaders read them via ``.numpy()``,
    which forbids CUDA tensors (the exact live failure).  The
    descriptors are byte-sized metadata consumed (popped) at
    construction and never adopted as parameters, so CPU placement
    preserves zero-copy weight adoption exactly.  Duck-typed (no torch
    import needed); returns the input untouched on anything unexpected.
    Never raises.
    """
    try:
        if not isinstance(state_dict, dict):
            return state_dict
        for key in list(state_dict.keys()):
            if not str(key).endswith(".comfy_quant"):
                continue
            tensor = state_dict[key]
            to = getattr(tensor, "to", None)
            is_cuda = getattr(tensor, "is_cuda", False)
            if callable(to) and bool(is_cuda):
                try:
                    state_dict[key] = to("cpu")
                except Exception:
                    continue
        return state_dict
    except Exception:
        return state_dict


# cuBLAS FP8 GEMM requires 16-element alignment on the logical M/N/K dims.
# Model files pin static weight shapes, so any FP8 weight whose static
# (out, in) dims break alignment fails EVERY cuBLAS FP8 attempt at runtime
# (observed live: n in {3396, 283, 4379} -> CUBLAS_STATUS_NOT_SUPPORTED ->
# per-op dequant fallback, hundreds of times per sample).  The batch dim M
# is dynamic per run and cannot be covered at load; N/K are static and can.
_FP8_GEMM_ALIGN = 16
_FP8_SELECTIVE_UPCAST_ENV = "COMFYMODAL_V2_FP8_SELECTIVE_UPCAST"
_FP8_DTYPES = ("float8_e4m3fn", "float8_e5m2")
_FP8_QUANT_SUFFIXES = (".comfy_quant", ".weight_scale", ".input_scale",
                       ".scale_weight", ".scale_input")

_fp8_log_guard_installed = False
_fp8_log_guard_drops = 0
_fp8_log_guard_unique_cap = 25
_fp8_log_guard_seen: set[str] = set()


def _fp8_native_shape_ok(shape: Any) -> bool:
    """True when static GEMM dims satisfy cuBLAS FP8 alignment (pure logic).

    Generic shape rule only: Linear/Conv weight layout ``(out, in, ...)``
    needs ``out % 16 == 0 and in % 16 == 0``.  Anything unknown or
    non-matrix (biases, norms) returns True so the caller leaves it
    untouched (fail-safe direction).  Never raises.
    """
    try:
        dims = tuple(int(d) for d in (shape or ()))
    except Exception:
        return True
    if len(dims) < 2:
        return True
    try:
        n, k = dims[0], dims[1]
    except Exception:
        return True
    if n <= 0 or k <= 0:
        return True
    return (n % _FP8_GEMM_ALIGN == 0) and (k % _FP8_GEMM_ALIGN == 0)


def _is_weight_matrix(key: Any, tensor: Any) -> bool:
    """True for candidate weights: ``*.weight``, ndim>=2 (any dtype)."""
    try:
        if not str(key or "").endswith(".weight"):
            return False
        shape = getattr(tensor, "shape", None)
        return shape is not None and len(tuple(shape)) >= 2
    except Exception:
        return False


# File dtypes whose hostile-shape layers are de-quantized to plain compute
# (their quant config is stripped so loaders take the plain branch).
_PLAINABLE_DTYPES = frozenset({
    "torch.bfloat16", "torch.float16", "torch.float32",
    "bfloat16", "float16", "float32",
})


def _log_clip_placement(tag: Any, clip: Any) -> None:
    """One worker-log line with CLIP patcher/offload state (diagnostic).

    Compares stage-built vs QD-built objects: load/offload devices,
    dynamic patcher flag, and a sample weight's device/dtype.  Never
    raises.
    """
    try:
        patcher = getattr(clip, "patcher", clip)
        model = getattr(patcher, "model", patcher)
        sample = None
        try:
            for param in model.parameters():
                sample = param
                break
        except Exception:
            sample = None
        try:
            dynamic = patcher.is_dynamic()
        except Exception:
            dynamic = "?"
        print(
            "[v2.clip_placement] tag={} model={} load_device={} "
            "offload_device={} dynamic={} w_device={} w_dtype={}".format(
                tag, type(model).__name__,
                getattr(patcher, "load_device", "?"),
                getattr(patcher, "offload_device", "?"), dynamic,
                getattr(sample, "device", "?"),
                getattr(sample, "dtype", "?")),
            flush=True)
    except Exception:
        pass


def _log_upcast_report(report: Any) -> None:
    """One worker-log line per upcast pass (visible in remote logs).

    The outcome dict does not propagate to the result payload, so this
    print is the observable proof of what the shape rule did.  Never
    raises.
    """
    try:
        rep = report if isinstance(report, dict) else {}
        print(
            "[v2.fp8_selective_upcast] enabled={} candidates={} upcast={} "
            "stripped={} bytes={} reverted={} skipped={} ms={}".format(
                rep.get("enabled"), rep.get("candidates"),
                rep.get("upcast_count"), rep.get("stripped_count"),
                rep.get("upcast_bytes"),
                len(rep.get("reverted") or []),
                len(rep.get("skipped") or []),
                rep.get("elapsed_ms")),
            flush=True)
    except Exception:
        pass


def _is_fp8_tensor(tensor: Any) -> bool:
    """True for FP8-dtype tensors of any shape/name (force-mode scope)."""
    try:
        if tensor is None:
            return False
        return "float8" in str(getattr(tensor, "dtype", "")).lower()
    except Exception:
        return False


def selective_fp8_bf16_upcast(
    state_dict: Any,
    metadata: Any = None,
    *,
    force_all_fp8: bool = False,
    ignore_env: bool = False,
) -> tuple[Any, Any, dict[str, Any]]:
    """De-quantize cuBLAS-hostile layers at load (generic, shape-ruled).

    For every ``*.weight`` matrix whose static shape fails
    :func:`_fp8_native_shape_ok`, removes the layer from the FP8 runtime
    path so no cuBLAS FP8 attempt can fail on it:

    * FP8 weights are folded to BF16 (``weight.to(bf16) * scale``);
    * BF16/FP16/FP32 weights are left byte-identical — only their quant
      config is stripped (in-sd descriptors/scales plus the
      ``_quantization_metadata`` entry), because loaders wrap ANY
      descriptor-carrying layer into runtime-quantized FP8 linears
      regardless of file dtype (verified in ``comfy/ops.py``: descriptor
      present -> quantized layout, absent -> plain parameter).

    Aligned layers pass through untouched and keep native FP8 execution.
    A layer is committed ONLY when fully neutralized; otherwise it is
    reverted.  File-agnostic: no filenames, no model lists.

    ``force_all_fp8`` normalizes EVERY FP8 tensor (not just hostile-shape
    weights) for stage-level source plans, where any QT module would trap
    on the meta-device bind.  ``ignore_env`` bypasses the kill-switch
    (the caller stage's own mode gate is the authority instead).

    Returns ``(sd, metadata, report)``.  Never raises.
    """
    report: dict[str, Any] = {
        "enabled": False, "candidates": 0, "upcast_count": 0,
        "upcast_bytes": 0, "stripped_count": 0,
        "reverted": [], "skipped": [],
        "elapsed_ms": 0.0,
    }
    started_ns = time.monotonic_ns()
    try:
        if not ignore_env and str(os.environ.get(
                _FP8_SELECTIVE_UPCAST_ENV, "1")).strip() != "1":
            report["elapsed_ms"] = (
                (time.monotonic_ns() - started_ns) / 1_000_000.0)
            _log_upcast_report(report)
            return state_dict, metadata, report
        if not isinstance(state_dict, dict):
            report["skipped"].append("state_dict_not_dict")
            report["elapsed_ms"] = (
                (time.monotonic_ns() - started_ns) / 1_000_000.0)
            _log_upcast_report(report)
            return state_dict, metadata, report
        import torch as _torch_upcast

        layers_meta: Any = None
        meta_copy = dict(metadata) if isinstance(metadata, dict) else {}
        try:
            raw = meta_copy.get("_quantization_metadata")
            if isinstance(raw, str) and raw:
                parsed = json.loads(raw)
                if isinstance(parsed, dict) and isinstance(
                        parsed.get("layers"), dict):
                    layers_meta = dict(parsed["layers"])
        except Exception:
            layers_meta = None
        upcast_prefixes: list[str] = []
        committed: list[tuple[str, dict[str, Any]]] = []
        for key in list(state_dict.keys()):
            tensor = state_dict.get(key)
            bare_fp8 = bool(force_all_fp8) and _is_fp8_tensor(tensor)
            if not bare_fp8 and not _is_weight_matrix(key, tensor):
                continue
            try:
                report["candidates"] += 1
            except Exception:
                pass
            try:
                shape = tuple(int(d) for d in tuple(tensor.shape))
            except Exception:
                report["skipped"].append(f"{key}:shape unreadable")
                continue
            if not force_all_fp8 and _fp8_native_shape_ok(shape):
                continue
            if str(key).endswith(".weight"):
                prefix = str(key)[: -len(".weight")]
            else:
                prefix = str(key)
            try:
                dtype_name = str(getattr(tensor, "dtype", "")).lower()
            except Exception:
                dtype_name = ""
            is_fp8 = "float8" in dtype_name
            if not is_fp8 and dtype_name not in _PLAINABLE_DTYPES:
                report["skipped"].append(f"{key}:dtype {dtype_name or '?'}")
                continue
            scale = None
            for suffix in (".weight_scale", ".scale_weight"):
                candidate = state_dict.get(prefix + suffix)
                if candidate is not None:
                    scale = candidate
                    break
            saved: dict[str, Any] = {key: tensor}
            for suffix in _FP8_QUANT_SUFFIXES:
                qkey = prefix + suffix
                if qkey in state_dict:
                    saved[qkey] = state_dict[qkey]
            has_insd_config = any(
                (prefix + s) in state_dict for s in _FP8_QUANT_SUFFIXES)
            has_meta_config = (isinstance(layers_meta, dict)
                               and prefix in layers_meta)
            if not is_fp8 and not has_insd_config and not has_meta_config:
                # Plain already: no descriptor can quantize this layer.
                report["skipped"].append(f"{key}:already_plain")
                continue
            try:
                if is_fp8:
                    w = tensor.to(_torch_upcast.bfloat16)
                    if scale is not None:
                        s = scale.to(device=w.device,
                                     dtype=_torch_upcast.bfloat16)
                        w = w * s
                    state_dict[key] = w
                for suffix in _FP8_QUANT_SUFFIXES:
                    state_dict.pop(prefix + suffix, None)
            except Exception as exc:
                for qkey, original in saved.items():
                    try:
                        state_dict[qkey] = original
                    except Exception:
                        pass
                report["skipped"].append(f"{key}:{type(exc).__name__}")
                continue
            residual = [qkey for qkey in state_dict
                        if str(qkey).startswith(prefix)
                        and any(str(qkey).endswith(s)
                                for s in _FP8_QUANT_SUFFIXES)]
            if residual:
                for qkey, original in saved.items():
                    try:
                        state_dict[qkey] = original
                    except Exception:
                        pass
                report["reverted"].append(
                    f"{key}:residual={len(residual)}")
                continue
            try:
                committed.append((prefix, saved))
                upcast_prefixes.append(prefix)
                if is_fp8:
                    report["upcast_count"] += 1
                    report["upcast_bytes"] += int(tensor.nelement())
                else:
                    report["stripped_count"] += 1
            except Exception:
                pass
        if isinstance(layers_meta, dict) and upcast_prefixes:
            try:
                scrubbed = {k: v for k, v in layers_meta.items()
                            if k not in upcast_prefixes}
                reparsed = {"layers": scrubbed}
                meta_copy["_quantization_metadata"] = json.dumps(reparsed)
            except Exception:
                # Scrub failed: the loader would re-attach descriptors, so
                # restore every committed layer instead of misbuilding.
                for prefix, saved in committed:
                    for qkey, original in saved.items():
                        try:
                            state_dict[qkey] = original
                        except Exception:
                            pass
                    try:
                        report["reverted"].append(f"{prefix}:scrub_failed")
                    except Exception:
                        pass
                report["upcast_count"] = 0
                report["upcast_bytes"] = 0
                report["stripped_count"] = 0
        report["enabled"] = True
        report["elapsed_ms"] = round(
            (time.monotonic_ns() - started_ns) / 1_000_000.0, 1)
        _log_upcast_report(report)
        return state_dict, meta_copy, report
    except Exception:
        try:
            report["elapsed_ms"] = round(
                (time.monotonic_ns() - started_ns) / 1_000_000.0, 1)
        except Exception:
            pass
        _log_upcast_report(report)
        return state_dict, metadata, report


def _is_quantized_weight(tensor: Any) -> bool:
    """True only for actually-quantized weights (not plain dense tensors).

    ``torch.Tensor.dequantize`` exists on EVERY tensor (quantized-ops
    method), so mere attribute presence is not a signal.  Quantized means
    torch-quantized storage, an FP8 dtype, or a kitchen-style wrapper
    exposing dequantize without torch quantized storage.
    """
    try:
        if tensor is None:
            return False
        if bool(getattr(tensor, "is_quantized", False)):
            return True
        dtype_name = str(getattr(tensor, "dtype", "")).lower()
        if "float8" in dtype_name:
            return True
        if "quantiz" in type(tensor).__name__.lower():
            return True
        return False
    except Exception:
        return False


def _resolve_module_root(obj: Any) -> Any | None:
    """Best-effort nn.Module root for a constructed model holder."""
    try:
        for candidate in (obj, getattr(obj, "model", None),
                          getattr(getattr(obj, "patcher", None),
                                  "model", None)):
            if candidate is not None and hasattr(candidate, "named_modules"):
                return candidate
    except Exception:
        pass
    return None


def _weight_static_shape(weight: Any) -> tuple[int, ...] | None:
    try:
        shape = getattr(weight, "shape", None)
        if shape is None:
            return None
        dims = tuple(int(d) for d in tuple(shape))
        return dims if len(dims) >= 2 else None
    except Exception:
        return None


def force_plain_hostile_linears(root: Any, tag: str = "") -> dict[str, Any]:
    """De-quantize hostile-shape linears on a CONSTRUCTED model (generic).

    Loader fusion/reshape can build quantized linears whose runtime GEMM
    dims break cuBLAS FP8 alignment even though every FILE weight is clean
    (observed live: out_features in {3396, 283, 4379}).  Those layers fail
    EVERY cuBLAS FP8 attempt and fall back per-op, hundreds of times per
    sample.  This walk finds them post-construction by SHAPE (any model,
    any file): any module whose weight's static ``(out, in)`` fails
    :func:`_fp8_native_shape_ok` and which is quantized (layout set or
    de-quantizable weight) gets its weight replaced by its de-quantized
    plain tensor with the layout nulled — numerically identical to today's
    per-op fallback, minus all of its overhead.  Aligned quantized layers
    keep native FP8.  Additionally, any module carrying a ``_v`` offload-view
    marker has it removed: ``_v`` forces the streaming gather path, whose
    buffers are sized from stored dtype and crash on quantized-storage /
    wider-compute combinations (observed live: FP8-stored, BF16-computed
    gather needs exactly 2x the buffer).  Without the marker the module
    takes the plain resident path — identical math to the working
    non-staged construction.  Operates on OUR constructed object only; no
    library code is touched.  Never raises.
    """
    report: dict[str, Any] = {
        "tag": str(tag or ""), "walked": 0, "normalized": 0,
        "unmarked": 0, "names": [], "elapsed_ms": 0.0,
    }
    started_ns = time.monotonic_ns()
    try:
        import torch as _torch_walk

        target = _resolve_module_root(root)
        if target is None:
            return report
        with _torch_walk.inference_mode(False):
            try:
                modules = list(target.named_modules())
            except Exception:
                return report
            for name, mod in modules:
                try:
                    report["walked"] += 1
                    try:
                        has_offload_view = hasattr(mod, "_v")
                    except Exception:
                        has_offload_view = False
                    if has_offload_view:
                        try:
                            delattr(mod, "_v")
                        except Exception:
                            pass
                        else:
                            report["unmarked"] += 1
                            if len(report["names"]) < 10:
                                try:
                                    report["names"].append(
                                        "unmarked:" + str(name or "?"))
                                except Exception:
                                    pass
                    weight = getattr(mod, "weight", None)
                    data = getattr(weight, "data", None)
                    quant_weight = None
                    for candidate in (weight, data):
                        if _is_quantized_weight(candidate):
                            quant_weight = candidate
                            break
                    layout_set = (
                        getattr(mod, "layout_type", None) is not None)
                    if quant_weight is None and not layout_set:
                        continue
                    shape = _weight_static_shape(
                        quant_weight if quant_weight is not None
                        else weight)
                    if shape is None:
                        out_f = getattr(mod, "out_features", None)
                        in_f = getattr(mod, "in_features", None)
                        try:
                            shape = (int(out_f), int(in_f))
                        except Exception:
                            continue
                    if _fp8_native_shape_ok(shape):
                        continue
                    if (quant_weight is not None and callable(
                            getattr(quant_weight, "dequantize", None))):
                        try:
                            plain = quant_weight.dequantize()
                        except Exception:
                            continue
                        try:
                            module_weight = _torch_walk.nn.Parameter(
                                plain, requires_grad=False)
                        except Exception:
                            continue
                        try:
                            mod.weight = module_weight
                        except Exception:
                            continue
                    try:
                        mod.layout_type = None
                    except Exception:
                        pass
                    try:
                        mod.quant_format = None
                    except Exception:
                        pass
                    try:
                        mod._full_precision_mm = True
                    except Exception:
                        pass
                    report["normalized"] += 1
                    if len(report["names"]) < 10:
                        try:
                            report["names"].append(str(name or "?"))
                        except Exception:
                            pass
                except Exception:
                    continue
        report["elapsed_ms"] = round(
            (time.monotonic_ns() - started_ns) / 1_000_000.0, 1)
        try:
            print(
                "[v2.fp8_layer_dequant] tag={} walked={} normalized={} "
                "unmarked={} names={} ms={}".format(
                    report["tag"], report["walked"],
                    report["normalized"], report["unmarked"],
                    report["names"],
                    report["elapsed_ms"]),
                flush=True)
        except Exception:
            pass
        return report
    except Exception:
        try:
            report["elapsed_ms"] = round(
                (time.monotonic_ns() - started_ns) / 1_000_000.0, 1)
        except Exception:
            pass
        return report


def _install_fp8_fallback_log_guard() -> bool:
    """Cap comfy_kitchen FP8-fallback WARNING spam (process logging only).

    Attaches a counting filter to the ``comfy_kitchen.tensor.fp8`` logger:
    the first 25 UNIQUE fallback shapes pass (each distinct (m, n, k)
    config is diagnostic gold), repeats are dropped, and every 100th drop
    prints a magnitude line.  No library code is touched; process-local
    logging configuration only.  Idempotent.  Never raises.
    """
    global _fp8_log_guard_installed
    if _fp8_log_guard_installed:
        return True
    try:
        import logging as _logging

        logger = _logging.getLogger("comfy_kitchen.tensor.fp8")

        class _CapFallbackSpam(_logging.Filter):
            def filter(self, record: Any) -> bool:
                global _fp8_log_guard_drops
                try:
                    msg = str(record.getMessage())
                    if "falling back to dequantization" not in msg:
                        return True
                    if msg in _fp8_log_guard_seen:
                        _fp8_log_guard_drops += 1
                        if _fp8_log_guard_drops % 100 == 0:
                            try:
                                print(
                                    "[v2.fp8_fallback] suppressed={} "
                                    "unique_shapes={}".format(
                                        _fp8_log_guard_drops,
                                        len(_fp8_log_guard_seen)),
                                    flush=True)
                            except Exception:
                                pass
                        return False
                    if len(_fp8_log_guard_seen) < _fp8_log_guard_unique_cap:
                        _fp8_log_guard_seen.add(msg)
                        return True
                    _fp8_log_guard_drops += 1
                    return False
                except Exception:
                    pass
                return True

        logger.addFilter(_CapFallbackSpam())
        _fp8_log_guard_installed = True
        return True
    except Exception:
        return False


def _describe_safetensors_header(path: Any) -> dict[str, Any]:
    """Header-only safetensors survey (no payload read).

    Returns dtype histogram, ``scaled_fp8`` key inventory, and
    quantization-metadata presence for stage-contract diagnosis (e.g.
    designing mixed/FP8 UNET adoption from the file's real composition).
    Header JSON is kilobytes; the multi-GB payload is never touched.
    Never raises.
    """
    try:
        with open(str(path), "rb") as handle:
            prefix = handle.read(8)
            if len(prefix) < 8:
                return {"ok": False, "reason": "truncated_header"}
            size = int.from_bytes(prefix, "little")
            if size <= 0 or size > 64 * 1024 * 1024:
                return {"ok": False, "reason": "bad_header_len"}
            header = json.loads(handle.read(size).decode("utf-8"))
        if not isinstance(header, dict):
            return {"ok": False, "reason": "header_not_object"}
        histogram: dict[str, int] = {}
        scaled_keys: list[str] = []
        quantized_keys = 0
        total = 0
        for key, info in header.items():
            if key == "__metadata__":
                continue
            total += 1
            key_text = str(key)
            entry = info if isinstance(info, dict) else {}
            dtype = str(entry.get("dtype", "?"))
            histogram[dtype] = histogram.get(dtype, 0) + 1
            if "scaled_fp8" in key_text:
                scaled_keys.append(key_text)
            if (
                key_text.endswith(".comfy_quant")
                or key_text.endswith(".weight_scale")
                or key_text.endswith(".input_scale")
                or key_text.endswith(".scale_weight")
                or key_text.endswith(".scale_input")
                or "scaled_fp8" in key_text
            ):
                quantized_keys += 1
        metadata = header.get("__metadata__") or {}
        metadata = metadata if isinstance(metadata, dict) else {}
        return {
            "ok": True,
            "tensors": total,
            "dtypes": histogram,
            "scaled_fp8_keys": scaled_keys[:25],
            "scaled_fp8_key_count": len(scaled_keys),
            "quantized_key_count": quantized_keys,
            "has_quantization_metadata": "_quantization_metadata" in metadata,
            "metadata_keys": sorted(str(k) for k in metadata.keys())[:25],
        }
    except Exception as exc:  # noqa: BLE001 - survey is best-effort
        return {"ok": False, "reason": f"{type(exc).__name__}"}


def _plain_source_native_decline(
    *, folder: str, filename: str, source_arm: str,
) -> dict[str, Any] | None:
    """Decline substitution only for a proven plain model header.

    Gated on the overlap switch: declining only wins when the overlap
    machinery is active to cover the read ahead of demand; standalone it
    merely converts an upfront stage load into deferred native
    first-touch cost inside the sampler.  Missing or unreadable headers
    deliberately return ``None`` so the current stage path remains the
    safe fallback for unknown source formats.  The survey reads only the
    safetensors length prefix and JSON header, never the payload.  Never
    raises.
    """
    if not _overlap_switch_enabled():
        return None
    started_ns = time.monotonic_ns()
    try:
        path = _default_path_resolver(folder, filename)
        if not path:
            return None
        details = _describe_safetensors_header(path)
        if not isinstance(details, dict) or not details.get("ok"):
            return None
        dtypes = {
            str(dtype).upper()
            for dtype in (details.get("dtypes") or {})
        }
        plain_dtypes = {"BF16", "F16", "F32"}
        if (
            dtypes
            and dtypes <= plain_dtypes
            and not int(details.get("quantized_key_count") or 0)
            and not int(details.get("scaled_fp8_key_count") or 0)
            and not bool(details.get("has_quantization_metadata"))
        ):
            return {
                "ok": False,
                "reason": "plain_source_native_optimal",
                "source_arm": source_arm,
                "elapsed_ms": (time.monotonic_ns() - started_ns) / 1_000_000.0,
            }
    except Exception:
        # Header failures must continue toward the existing stage behavior.
        return None
    return None


def _native_torch_file_reader(path: str) -> tuple[Any, Any]:
    """Read one model file exactly like the native loaders (lazy import)."""
    from comfy.utils import load_torch_file as _read

    return _read(path, return_metadata=True)


def _native_unet_binder() -> tuple[Any, Any]:
    """Native UNET constructor pair (lazy import, never modified)."""
    from comfy.sd import load_diffusion_model as _reload
    from comfy.sd import load_diffusion_model_state_dict as _construct

    return _construct, _reload


def _advise_sequential_source(path: str, size_bytes: int) -> dict[str, Any]:
    """Best-effort whole-file readahead hint (advisory only, never raises).

    With mmap-backed readers the payload stays on disk until first touch;
    a WILLNEED hint lets the kernel page it in ahead of binding without
    duplicating tensors or changing any torch semantics.  Unavailable
    (e.g. non-POSIX platforms) or failed hints simply skip: the prepared
    source stays valid, only the warming is lost.
    """
    outcome: dict[str, Any] = {
        "status": "skipped_platform",
        "advised_bytes": 0,
    }
    try:
        advise = getattr(os, "posix_fadvise", None)
        willneed = getattr(os, "POSIX_FADV_WILLNEED", None)
        if advise is None or willneed is None or not callable(advise):
            return outcome
        fd = os.open(path, os.O_RDONLY)
        try:
            advise(fd, 0, 0, willneed)
        finally:
            try:
                os.close(fd)
            except Exception:
                pass
    except Exception as exc:  # noqa: BLE001 - advisory only
        outcome["status"] = f"advise_failed:{type(exc).__name__}"
        return outcome
    outcome["status"] = "advised"
    try:
        outcome["advised_bytes"] = int(size_bytes or 0)
    except Exception:
        pass
    return outcome


def _prepare_generic_unet_source(
    *,
    folder: str,
    filename: str,
    path_resolver: Callable[[str, str], str | None] | None = None,
    reader: Callable[[str], tuple[Any, Any]] | None = None,
) -> dict[str, Any]:
    """Prepare a UNET source for later executor-thread binding (pure IO).

    Mirrors the native read half of ``UNETLoader``: resolve, stat for a
    bind-time identity check, read via ``load_torch_file`` semantics,
    then issue a best-effort readahead hint so a later bind faults from
    page cache.  No tensor is constructed, no cache is touched, no
    model-management global changes.  Never raises.
    """
    started_ns = time.monotonic_ns()

    def _fail(reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "reason": str(reason),
            "sd": None,
            "metadata": None,
            "path": None,
            "size_bytes": 0,
            "mtime_ns": 0,
            "advise_status": "not_attempted",
            "advised_bytes": 0,
            "elapsed_ms": (time.monotonic_ns() - started_ns) / 1_000_000.0,
        }

    try:
        name = str(filename or "").strip()
        if not name:
            return _fail("unet_filename_missing")
        resolve = path_resolver or _default_path_resolver
        path = resolve(str(folder or ""), name)
        if not path:
            return _fail(f"source_path_unresolvable:{name}")
        try:
            st = os.stat(path)
            size_bytes = int(st.st_size)
            mtime_ns = int(st.st_mtime_ns)
        except Exception:
            return _fail("source_stat_failed")
        read = reader or _native_torch_file_reader
        try:
            sd, metadata = read(path)
        except Exception as exc:  # noqa: BLE001 - source failure is data
            return _fail(f"{type(exc).__name__}:{str(exc)[:120]}")
        if not isinstance(sd, dict):
            return _fail("source_not_mapping")
        advise = _advise_sequential_source(path, size_bytes)
        return {
            "ok": True,
            "reason": "",
            "sd": sd,
            "metadata": metadata,
            "path": path,
            "size_bytes": size_bytes,
            "mtime_ns": mtime_ns,
            "advise_status": str(advise.get("status") or ""),
            "advised_bytes": int(advise.get("advised_bytes") or 0),
            "elapsed_ms": (time.monotonic_ns() - started_ns) / 1_000_000.0,
        }
    except Exception as exc:  # noqa: BLE001 - prepare contract: never raise
        return _fail(type(exc).__name__)


def _bind_generic_unet_source(
    *,
    prepared: Any,
    model_options: Mapping[str, Any] | None = None,
    constructor: Callable[..., Any] | None = None,
    reloader: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Bind a prepared UNET source to a real MODEL (executor thread only).

    Consumes the exact ``sd`` object preparation read (no second payload
    read by construction) through the native construction tail, then
    stamps the identical ``cached_patcher_init`` the native loader sets
    so downstream reload semantics match.  The source file is re-statted:
    any size/mtime change since preparation declines instead of binding
    stale bytes.  Never raises; failure means the caller takes the
    established native route (which raises identically, as before).
    """
    started_ns = time.monotonic_ns()

    def _fail(reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "reason": str(reason),
            "model": None,
            "elapsed_ms": (time.monotonic_ns() - started_ns) / 1_000_000.0,
        }

    try:
        if not isinstance(prepared, Mapping):
            return _fail("prepared_not_mapping")
        sd = prepared.get("sd")
        if not isinstance(sd, dict):
            return _fail("prepared_sd_missing")
        path = str(prepared.get("path") or "")
        if not path:
            return _fail("prepared_path_missing")
        try:
            st = os.stat(path)
            if (int(st.st_size) != int(prepared.get("size_bytes") or -1)
                    or int(st.st_mtime_ns) != int(
                        prepared.get("mtime_ns") or -1)):
                return _fail("source_changed")
        except Exception:
            return _fail("source_restat_failed")
        options = dict(model_options or {})
        construct, reload = (
            (constructor, reloader)
            if constructor is not None and reloader is not None
            else _native_unet_binder()
        )
        try:
            model = construct(
                sd, model_options=dict(options),
                metadata=prepared.get("metadata"))
        except Exception as exc:  # noqa: BLE001 - construction is data
            return _fail(f"{type(exc).__name__}:{str(exc)[:120]}")
        if model is None:
            return _fail("model_type_undetected")
        try:
            model.cached_patcher_init = (reload, (path, dict(options)))
        except Exception:
            return _fail("patcher_init_failed")
        return {
            "ok": True,
            "reason": "",
            "model": model,
            "path": path,
            "elapsed_ms": (time.monotonic_ns() - started_ns) / 1_000_000.0,
        }
    except Exception as exc:  # noqa: BLE001 - bind contract: never raise
        return _fail(type(exc).__name__)


async def compose_generic_clip_load_qd4(
    *,
    clip_filenames: Sequence[str],
    clip_type: str,
    folder: str,
    request_id: str,
    path_resolver: Callable[[str, str], str | None] | None = None,
) -> dict[str, Any]:
    """Load CLIP via the SHARED QD4 demand reader (canonical clean-lane arm).

    Uses the same ``clip_qd_load`` the canonical clean-lane demand path uses
    (imported, never copied).  It is self-contained per call — workers are
    joined before return and it owns no persistent pool — so it is immune
    to the persistent-pool poisoning that fails the M2 singleton
    (``PoolPoisonedError:cancelled dispatcher handoff was not completed``).

    Construction mirrors the native CLIPLoader recipe exactly: the same
    shared ``comfy.sd.load_text_encoder_state_dicts`` delegation with the
    same ``cached_patcher_init`` shape; only the file-read step is fast.
    No manifest pipeline is applied (native loads apply none).  QD owners
    are returned for request-scoped retention; the caller releases them via
    the holder without touching any shared lifecycle.

    Returns the same outcome shape as :func:`compose_generic_clip_load`
    plus ``source_arm="qd4_demand"``.  Never raises.
    """
    started_ns = time.monotonic_ns()
    resolve = path_resolver or _default_path_resolver
    try:
        names = [str(n) for n in (clip_filenames or []) if str(n or "").strip()]
        if not names:
            return {"ok": False, "reason": "clip_filenames_missing",
                    "source_arm": "qd4_demand"}
        if len(names) > 1:
            return {"ok": False, "reason": "qd4_multi_checkpoint_deferred",
                    "source_arm": "qd4_demand"}
        path = resolve(folder, names[0])
        if not path:
            return {"ok": False,
                    "reason": f"clip_path_unresolvable:{names[0]}",
                    "source_arm": "qd4_demand"}
        t_resolved_ns = time.monotonic_ns()
        from .clip_qd_reader import clip_qd_load, qd_config

        cfg = qd_config() or {}
        qd_value = int(cfg.get("qd", 0) or 0)
        block_mib = int(cfg.get("block_mib", 0) or 0)
        launch_policy = str(cfg.get("launch_policy", "") or "")
        if not bool(cfg.get("enabled")):
            return {"ok": False, "reason": "qd4_gate_disabled",
                    "source_arm": "qd4_demand"}
        if qd_value != 4:
            return {"ok": False,
                    "reason": f"qd4_gate_qd_not_4:{qd_value}",
                    "source_arm": "qd4_demand"}
        if block_mib < 1 or not launch_policy:
            return {"ok": False, "reason": "qd4_gate_config_incomplete",
                    "source_arm": "qd4_demand"}
        t_gated_ns = time.monotonic_ns()
        sd, loader, owner = clip_qd_load(
            path,
            qd=qd_value,
            block_mib=block_mib,
            trace=None,
            launch_policy=launch_policy,
            artifact_path=cfg.get("artifact_path") or None,
        )
        t_read_ns = time.monotonic_ns()
        # Quant descriptors must be CPU (loaders call .numpy() on them);
        # weights stay GPU views (zero-copy preserved).
        sd = _cpu_native_quant_markers(sd)
        import comfy.sd
        from comfy.utils import convert_old_quants

        # Mirror the native recipe: convert_old_quants runs whenever the
        # (default, empty) model_options carry no custom_operations.  The
        # native path passes REAL safetensors header metadata, which carries
        # _quantization_metadata for scaled-FP8 weights; passing {} skips
        # the .comfy_quant attachment and the constructor rejects raw F8
        # tensors (observed live).  Header-only parse: no second payload
        # read (tensors stay lazy; only the JSON header is touched).
        model_options: dict[str, Any] = {}
        file_metadata: dict[str, Any] = {}
        try:
            if str(path).lower().endswith((".safetensors", ".sft")):
                from safetensors import safe_open as _safe_open

                with _safe_open(path, framework="pt", device="cpu") as _hdr:
                    _meta = _hdr.metadata()
                    if isinstance(_meta, dict):
                        file_metadata = dict(_meta)
        except Exception:
            file_metadata = {}
        sd, _qd_metadata = convert_old_quants(
            sd, model_prefix="", metadata=file_metadata
        )
        # Selective FP8->BF16 upcast (generic shape rule): hostile-shape FP8
        # weights become plain BF16 so no cuBLAS FP8 attempt can fail on
        # them at runtime.  Descriptors were attached above, so the helper
        # pops them with the scales.  Aligned FP8 stays native.
        _install_fp8_fallback_log_guard()
        sd, _upcast_metadata, fp8_upcast_report = selective_fp8_bf16_upcast(
            sd, file_metadata)
        clip_type_obj = resolve_clip_type_shared(clip_type)
        try:
            import folder_paths

            embedding_directory = folder_paths.get_folder_paths("embeddings")
        except Exception:
            embedding_directory = None
        t_prep_ns = time.monotonic_ns()
        clip = comfy.sd.load_text_encoder_state_dicts(
            [sd],
            embedding_directory=embedding_directory,
            clip_type=clip_type_obj,
            model_options=model_options,
        )
        try:
            clip.patcher.cached_patcher_init = (
                comfy.sd.load_clip_model_patcher,
                ([path], embedding_directory, clip_type_obj, model_options),
            )
        except Exception:
            pass
        # Post-construction de-quant walk: loader fusion can build hostile
        # GEMM dims no file scan can see.  Generic shape rule on OUR object.
        fp8_layer_report = force_plain_hostile_linears(clip, tag="clip")
        _log_clip_placement("qd4", clip)
        t_construct_ns = time.monotonic_ns()
        elapsed_ms = (t_construct_ns - started_ns) / 1_000_000.0
        phases = {
            "resolve_ms": round((t_resolved_ns - started_ns) / 1_000_000.0, 1),
            "gate_ms": round((t_gated_ns - t_resolved_ns) / 1_000_000.0, 1),
            "read_ms": round((t_read_ns - t_gated_ns) / 1_000_000.0, 1),
            "prep_ms": round((t_prep_ns - t_read_ns) / 1_000_000.0, 1),
            "construct_ms": round((t_construct_ns - t_prep_ns) / 1_000_000.0, 1),
        }
        owners = [o for o in (loader, owner) if o is not None]
        return {
            "ok": True,
            "clip": clip,
            "session": None,
            "owners": owners,
            "elapsed_ms": elapsed_ms,
            "reason": "",
            "source_arm": "qd4_demand",
            "phases": phases,
            "fp8_selective_upcast": fp8_upcast_report,
            "fp8_layer_dequant": fp8_layer_report,
        }
    except Exception as exc:  # noqa: BLE001 - fallback contract: never raise
        elapsed_ms = (time.monotonic_ns() - started_ns) / 1_000_000.0
        return {
            "ok": False,
            "reason": f"{type(exc).__name__}:{str(exc)[:200]}",
            "elapsed_ms": elapsed_ms,
            "source_arm": "qd4_demand",
        }


def _cache_entry_for(obj: Any) -> Any | None:
    """Build a CacheEntry shaped exactly like the residency seeder's."""
    try:
        from execution import CacheEntry as _CacheEntry
    except Exception:
        return None
    try:
        outputs_list = [[v] for v in obj] if isinstance(obj, (tuple, list)) else [[obj]]
        return _CacheEntry(ui={}, outputs=outputs_list)
    except Exception:
        return None


async def insert_loader_cache_entry(
    outputs_cache: Any,
    cache_key_set: Any,
    node_id: str,
    obj: Any,
) -> dict[str, str]:
    """Insert one loaded object into the executor output cache (verified).

    Mirrors the residency seeder's insert+verify shape.  Returns a decision
    dict; never raises — failure means the native node simply executes.
    """
    node_id = str(node_id or "")
    try:
        data_key = cache_key_set.get_data_key(node_id) if cache_key_set is not None else None
    except Exception:
        data_key = None
    if data_key is None:
        return {"decision": "cache_key_missing", "node_id": node_id}
    entry = _cache_entry_for(obj)
    if entry is None:
        return {"decision": "cache_insert_failed", "node_id": node_id}
    try:
        await outputs_cache.set(node_id, entry)
        retrieved = await outputs_cache.get(node_id)
    except Exception:
        return {"decision": "cache_insert_failed", "node_id": node_id}
    if retrieved is None:
        return {"decision": "cache_insert_failed", "node_id": node_id}
    return {"decision": "seeded", "node_id": node_id}


async def compose_loaders_for_workflow(
    *,
    workflow: Mapping[str, Any],
    outputs_cache: Any,
    cache_key_set: Any,
    holder: GenericLoaderHolder,
    request_id: str,
    trace_emit: Callable[..., Any] | None = None,
    path_resolver: Callable[[str, str], str | None] | None = None,
) -> dict[str, dict[str, Any]]:
    """Attempt shared-core loads for eligible loader nodes, seed the cache.

    Runs AFTER the executor's set_prompt (cache keys exist).  For each
    CLIPLoader node: skip when already cached, classify, compose via the
    shared core, insert on success.  Every outcome is recorded per node;
    native execution always remains the fallback.  Never raises.
    """
    results: dict[str, dict[str, Any]] = {}
    seen_paths: dict[str, Any] = {}

    def _emit(name: str, **fields: Any) -> None:
        try:
            if callable(trace_emit):
                trace_emit(name, phase="execution", metadata=dict(fields))
        except Exception:
            pass

    try:
        nodes = workflow.items() if isinstance(workflow, Mapping) else []
    except Exception:
        return results
    for raw_nid, node in nodes:
        try:
            node_id = str(raw_nid or "")
            if not node_id or not isinstance(node, Mapping):
                continue
            class_type = str(node.get("class_type", "") or "")
            inputs = node.get("inputs")
            if not isinstance(inputs, dict):
                inputs = {}
            classification = classify_loader_node(class_type, inputs)
            if not classification.get("supported"):
                if class_type in _KNOWN_LOADER_CLASSES:
                    results[node_id] = {
                        "requested": "shared_core",
                        "actual": "native",
                        "reason": str(classification.get("reason") or "unsupported"),
                    }
                continue
            # Skip nodes the residency/snapshot path (or an earlier node)
            # already satisfied - never reload covered work.
            try:
                existing = await outputs_cache.get(node_id)
            except Exception:
                existing = None
            if existing is not None:
                results[node_id] = {
                    "requested": "shared_core",
                    "actual": "cache_hit",
                    "reason": "already_cached",
                }
                continue
            clip_name = str(classification.get("clip_name") or "")
            clip_type = str(classification.get("clip_type") or "stable_diffusion")
            path_key = f"text_encoders/{clip_name}"
            if path_key in seen_paths:
                obj = seen_paths[path_key]
                outcome: dict[str, Any] = {
                    "ok": True, "clip": obj, "session": None,
                    "owners": [], "elapsed_ms": 0.0, "reason": "dedup_within_request",
                }
            else:
                # QD4 demand first (self-contained, pool-poison immune),
                # M2 singleton second (healthy pool used when available).
                outcome = await compose_generic_clip_load_qd4(
                    clip_filenames=[clip_name],
                    clip_type=clip_type,
                    folder="text_encoders",
                    request_id=request_id,
                    path_resolver=path_resolver,
                )
                if not outcome.get("ok"):
                    qd4_reason = str(outcome.get("reason") or "qd4_failed")
                    m2_outcome = await compose_generic_clip_load(
                        clip_filenames=[clip_name],
                        clip_type=clip_type,
                        folder="text_encoders",
                        request_id=request_id,
                        path_resolver=path_resolver,
                    )
                    m2_outcome.setdefault("source_arm", "m2_transport")
                    if not m2_outcome.get("ok"):
                        m2_outcome["reason"] = (
                            f"{qd4_reason}|{m2_outcome.get('reason')}"
                        )
                    outcome = m2_outcome
                if outcome.get("ok") and outcome.get("clip") is not None:
                    seen_paths[path_key] = outcome["clip"]
            if not outcome.get("ok") or outcome.get("clip") is None:
                results[node_id] = {
                    "requested": "shared_core",
                    "actual": "native",
                    "reason": str(outcome.get("reason") or "compose_failed"),
                    "elapsed_ms": outcome.get("elapsed_ms", 0.0),
                    "source_arm": str(outcome.get("source_arm") or "unknown"),
                }
                _emit("generic_loader_composition", node_id=node_id,
                      role="clip", requested="shared_core", actual="native",
                      reason=str(outcome.get("reason") or "compose_failed"),
                      source_arm=str(outcome.get("source_arm") or "unknown"))
                continue
            # Retain owners even when no session exists (the QD4 arm returns
            # session=None with live QD owners); dropping them frees backing
            # storage while the cache still references it.
            if outcome.get("session") is not None or outcome.get("owners"):
                holder.retain(outcome.get("session"), outcome.get("owners"))
            decision = await insert_loader_cache_entry(
                outputs_cache, cache_key_set, node_id, outcome["clip"],
            )
            if decision.get("decision") == "seeded":
                results[node_id] = {
                    "requested": "shared_core",
                    "actual": "shared_core",
                    "reason": "",
                    "elapsed_ms": outcome.get("elapsed_ms", 0.0),
                    "source_arm": str(outcome.get("source_arm") or "unknown"),
                }
            else:
                results[node_id] = {
                    "requested": "shared_core",
                    "actual": "native",
                    "reason": str(decision.get("decision") or "cache_insert_failed"),
                    "elapsed_ms": outcome.get("elapsed_ms", 0.0),
                    "source_arm": str(outcome.get("source_arm") or "unknown"),
                }
            _emit("generic_loader_composition", node_id=node_id,
                  role="clip", requested="shared_core",
                  actual=results[node_id]["actual"],
                  reason=results[node_id]["reason"],
                  source_arm=str(outcome.get("source_arm") or "unknown"))
        except Exception as exc:  # noqa: BLE001 - per-node isolation
            try:
                results[str(raw_nid or "?")] = {
                    "requested": "shared_core",
                    "actual": "native",
                    "reason": f"{type(exc).__name__}:{str(exc)[:120]}",
                }
            except Exception:
                pass
    return results


def install_generic_loader_hook(
    executor: Any,
    workflow: Mapping[str, Any] | None,
    holder: GenericLoaderHolder,
    trace_emit: Callable[..., Any] | None,
    request_id: str,
) -> Callable[[], None] | None:
    """Wrap the executor output-cache ``set_prompt`` with generic composition.

    The wrapper calls through to whatever ``set_prompt`` is currently
    installed (the snapshot seeder's wrapper or the original), so snapshot
    residency keeps priority, then attempts shared-core loads for loader
    nodes the cache still misses.  Returns a restore callable (never None
    when installed).  Installation failure returns None and leaves the
    executor untouched — native behavior is always the fallback.
    """
    try:
        caches = getattr(executor, "caches", None)
        outputs_cache = getattr(caches, "outputs", None) if caches is not None else None
        original_set_prompt = getattr(outputs_cache, "set_prompt", None)
        if not callable(original_set_prompt):
            return None
        workflow_snapshot = dict(workflow) if isinstance(workflow, Mapping) else {}

        async def generic_set_prompt(*args: Any, **kwargs: Any) -> Any:
            result = await original_set_prompt(*args, **kwargs)
            try:
                await compose_loaders_for_workflow(
                    workflow=workflow_snapshot,
                    outputs_cache=outputs_cache,
                    cache_key_set=getattr(outputs_cache, "cache_key_set", None),
                    holder=holder,
                    request_id=str(request_id or ""),
                    trace_emit=trace_emit,
                )
            except Exception:
                pass
            return result

        outputs_cache.set_prompt = generic_set_prompt  # type: ignore[method-assign]

        def _restore() -> None:
            try:
                if getattr(outputs_cache, "set_prompt", None) is generic_set_prompt:
                    outputs_cache.set_prompt = original_set_prompt
            except Exception:
                pass

        return _restore
    except Exception:
        return None


# ── Phase 1 dispatch substitution ─────────────────────────────────────
# Role-driven node substitution at the upstream dispatch boundary
# (``execution.get_output_data``): when the executor demands a role-bound
# loader node, the imported golden stage runs INSTEAD of the native node
# function and its result is returned in the exact merged output shape the
# executor would have produced.  Anything unbound, class-mismatched,
# list-mapped, or stage-failed executes natively.  Samplers are never
# substituted (owner decision); forward replacement arrives in phase 2.
#
# Request scoping: the wrapper is installed once per generic request and
# restored in the request finally-block.  The container runs one request
# at a time (same single-flight assumption as the existing per-run
# registries); a second install while active is refused, never nested.

_ROLE_SUBSTITUTION_LOADER_CLASSES: dict[str, frozenset] = {
    "clip": frozenset({"CLIPLoader"}),
    "unet": frozenset({"UNETLoader"}),
    "model_unet": frozenset({"UNETLoader"}),
    "vae": frozenset({"VAELoader"}),
}

_ACTIVE_DISPATCH_CTX: dict[str, Any] | None = None


def _emit_trace(trace_emit: Callable[..., Any] | None, name: str, **fields: Any) -> None:
    try:
        if callable(trace_emit):
            trace_emit(name, phase="execution", metadata=dict(fields))
    except Exception:
        pass


def _invert_role_bindings(role_bindings: Any) -> dict[str, str]:
    """Map node_id -> substitutable role. First claim wins. Never raises."""
    inverted: dict[str, str] = {}
    try:
        items = role_bindings.items() if isinstance(role_bindings, Mapping) else []
        for role, binding in items:
            role = str(role or "")
            if role not in _ROLE_SUBSTITUTION_LOADER_CLASSES:
                continue
            nid = ""
            if isinstance(binding, Mapping):
                nid = str(binding.get("node_id") or "")
            elif isinstance(binding, (str, int)):
                nid = str(binding)
            if nid and nid not in inverted:
                inverted[nid] = role
    except Exception:
        pass
    return inverted


_GENERIC_OVERLAP_ENV = "COMFYMODAL_V2_GENERIC_OVERLAP"

_OVERLAP_FORWARD_CLASSES = frozenset({"CLIPTextEncode"})

_OVERLAP_UNET_ROLES = ("unet", "model_unet")


def _overlap_switch_enabled() -> bool:
    """Deploy-owned switch for generic load overlap (default off)."""
    try:
        return str(os.environ.get(_GENERIC_OVERLAP_ENV, "0")).strip() == "1"
    except Exception:
        return False


def _overlap_ineligible(reason: str) -> dict[str, Any]:
    return {
        "eligible": False,
        "clip_node_id": None,
        "unet_node_id": None,
        "forward_node_id": None,
        "deferral_allowed": False,
        "identification": "",
        "reason": str(reason or "unknown"),
    }


def _overlap_upstream_ids(
    workflow: Mapping[str, Any], start_id: str,
) -> set[str]:
    """All static upstream node ids of one executable-prompt node.

    Follows ``[node_id, slot]`` link values only; SetNode/GetNode named
    pipes are intentionally invisible (callers must treat absence as
    unknown, never as proof of independence).  Never raises.
    """
    seen: set[str] = set()
    try:
        stack = [str(start_id)]
        guard = 0
        while stack and guard < 100000:
            guard += 1
            node = workflow.get(stack.pop())
            if not isinstance(node, Mapping):
                continue
            inputs = node.get("inputs")
            if not isinstance(inputs, Mapping):
                continue
            for value in inputs.values():
                if (
                    isinstance(value, (list, tuple))
                    and len(value) >= 1
                    and isinstance(value[0], (str, int))
                    and str(value[0]) in workflow
                    and str(value[0]) not in seen
                ):
                    seen.add(str(value[0]))
                    stack.append(str(value[0]))
    except Exception:
        pass
    return seen


def _derive_generic_overlap_plan(
    *, workflow: Any, role_bindings: Any,
) -> dict[str, Any]:
    """Derive the load-overlap triple for one request (pure logic).

    Returns ``eligible`` with ``clip_node_id`` (always set when
    eligible), optional ``unet_node_id`` / ``forward_node_id``, and
    ``deferral_allowed`` (UNET-loader deferral is safe: UNET is not a
    static ancestor of the forward node).  The forward id is timing
    information only — nothing executes early, so misidentification
    costs overlap, never correctness.  Ambiguity degrades to
    clip-first ordering (forward None) rather than failing.  Never
    raises.
    """
    try:
        node_roles = _invert_role_bindings(role_bindings)
        if not node_roles:
            return _overlap_ineligible("no_eligible_roles")
        if not isinstance(workflow, Mapping):
            return _overlap_ineligible("workflow_not_mapping")
        wf = {str(k): v for k, v in workflow.items()}
        clip_nid = next(
            (nid for nid, role in node_roles.items() if role == "clip"),
            "",
        )
        if not clip_nid:
            return _overlap_ineligible("clip_binding_missing")
        clip_node = wf.get(clip_nid)
        if (
            not isinstance(clip_node, Mapping)
            or str(clip_node.get("class_type") or "")
            not in _ROLE_SUBSTITUTION_LOADER_CLASSES.get("clip", frozenset())
        ):
            return _overlap_ineligible("clip_binding_unresolvable")
        unet_nid = next(
            (nid for nid, role in node_roles.items()
             if role in _OVERLAP_UNET_ROLES),
            "",
        )
        unet_node = wf.get(unet_nid) if unet_nid else None
        if (
            not unet_nid
            or not isinstance(unet_node, Mapping)
            or str(unet_node.get("class_type") or "")
            not in _ROLE_SUBSTITUTION_LOADER_CLASSES.get(
                node_roles.get(unet_nid, "unet"), frozenset())
        ):
            return {
                "eligible": True,
                "clip_node_id": clip_nid,
                "unet_node_id": None,
                "forward_node_id": None,
                "deferral_allowed": False,
                "identification": "derived",
                "reason": "unet_binding_unresolvable",
            }
        candidates = []
        for raw_nid in sorted(wf.keys(), key=str):
            node = wf.get(raw_nid)
            if not isinstance(node, Mapping):
                continue
            if str(node.get("class_type") or "") not in _OVERLAP_FORWARD_CLASSES:
                continue
            inputs = node.get("inputs")
            if not isinstance(inputs, Mapping):
                continue
            ref = inputs.get("clip")
            if (
                isinstance(ref, (list, tuple))
                and len(ref) >= 1
                and str(ref[0]) == clip_nid
            ):
                candidates.append(str(raw_nid))
        if len(candidates) != 1:
            return {
                "eligible": True,
                "clip_node_id": clip_nid,
                "unet_node_id": unet_nid,
                "forward_node_id": None,
                "deferral_allowed": False,
                "identification": "derived",
                "reason": ("forward_not_found"
                           if not candidates else "ambiguous_forward"),
            }
        fwd = candidates[0]
        if unet_nid in _overlap_upstream_ids(wf, fwd):
            return {
                "eligible": True,
                "clip_node_id": clip_nid,
                "unet_node_id": unet_nid,
                "forward_node_id": fwd,
                "deferral_allowed": False,
                "identification": "derived",
                "reason": "unet_ancestor_of_forward",
            }
        return {
            "eligible": True,
            "clip_node_id": clip_nid,
            "unet_node_id": unet_nid,
            "forward_node_id": fwd,
            "deferral_allowed": True,
            "identification": "derived",
            "reason": "",
        }
    except Exception as exc:  # noqa: BLE001 - planner contract: never raise
        return _overlap_ineligible(type(exc).__name__)


def _select_substitution(
    ctx: Mapping[str, Any],
    unique_id: Any,
    obj: Any,
    input_data_all: Any,
) -> dict[str, Any] | None:
    """Decide substitution for one dispatch. Returns a decision or None.

    Decision requires: node claimed by a substitutable role AND the live
    node object's class matching that role's loader class AND scalar
    (non-list-mapped) inputs — mapping semantics stay native.  Class
    mismatch is recorded (a stale binding must never retarget silently).
    Never raises.
    """
    try:
        node_id = str(unique_id)
        role = (ctx.get("node_roles") or {}).get(node_id)
        if not role:
            return None
        actual_class = type(obj).__name__ if obj is not None else ""
        if actual_class not in _ROLE_SUBSTITUTION_LOADER_CLASSES.get(role, ()):
            _emit_trace(
                ctx.get("trace_emit"), "generic_dispatch_substitution",
                node_id=node_id, role=role, requested="shared_core",
                actual="native", reason=f"class_mismatch:{actual_class}",
            )
            return None
        resolved: dict[str, Any] = {}
        inputs = input_data_all if isinstance(input_data_all, dict) else {}
        for key, value in inputs.items():
            if isinstance(value, (list, tuple)):
                if len(value) != 1:
                    return None
                resolved[str(key)] = value[0]
            else:
                resolved[str(key)] = value
        return {"role": role, "node_id": node_id, "inputs": resolved}
    except Exception:
        return None


async def _substitute_unet_vae_loader(
    *, role: str, inputs: Any, request_id: str
) -> dict[str, Any]:
    """Shared UNET/VAE tail for dispatch substitution (imported stages).

    Returns ``{"ok": True, "tuple": (...), "owners": [...], "source_arm":
    ...}`` or ``{"ok": False, "reason": ...}``.  Stage contracts reject
    unsupported files (scaled-FP8 UNET, non-uniform dtypes) with clean
    reasons; the caller falls back to native.  Never raises.
    """
    try:
        given = inputs if isinstance(inputs, dict) else {}
        if role in ("unet", "model_unet"):
            unet_name = str(given.get("unet_name") or "").strip()
            if not unet_name:
                return {"ok": False, "reason": "unet_name_missing"}
            # Native UNETLoader casts post-load for explicit weight_dtype;
            # the shared stage never receives that input, so only the
            # default passes through (anything else stays native).
            weight_dtype = str(given.get("weight_dtype") or "default").strip().lower()
            if weight_dtype not in ("", "default"):
                return {"ok": False,
                        "reason": f"unet_explicit_weight_dtype_native:{weight_dtype}"}
            # NOTE (overlap retired): plain sources used to decline here so
            # a warming prefetch could cover the native read.  Generic loads
            # now take the canonical shared transport directly, so every
            # source stays on the stage path; native remains the failure
            # fallback below, never a routing decision.
            outcome = await compose_generic_unet_load(
                unet_filenames=[unet_name],
                folder="diffusion_models",
                request_id=request_id,
            )
            try:
                print(
                    "[v2.generic_attempt_walls] role=unet walls={}".format(
                        json.dumps([{
                            "arm": str(outcome.get("source_arm")
                                       or "golden_unet"),
                            "ok": bool(outcome.get("ok")),
                            "elapsed_ms": float(
                                outcome.get("elapsed_ms") or 0.0),
                            "reason": str(outcome.get("reason") or ""),
                        }])[:500]),
                    flush=True)
            except Exception:
                pass
            if not outcome.get("ok"):
                _stage_reason = str(outcome.get("reason") or "stage_failed")
                outcome = await compose_generic_unet_load_qd(
                    unet_filenames=[unet_name],
                    folder="diffusion_models",
                    request_id=request_id,
                )
                outcome.setdefault("source_arm", "qd_unet_demand")
                if not outcome.get("ok"):
                    outcome["reason"] = (
                        f"{_stage_reason}|{outcome.get('reason') or 'qd_failed'}"
                    )
        elif role == "vae":
            vae_name = str(given.get("vae_name") or "").strip()
            if not vae_name:
                return {"ok": False, "reason": "vae_name_missing"}
            outcome = await compose_generic_vae_load(
                vae_filenames=[vae_name],
                folder="vae",
                request_id=request_id,
            )
        else:
            return {"ok": False, "reason": f"{role}_deferred"}
        if not outcome.get("ok") or outcome.get("loaded") is None:
            return {
                "ok": False,
                "reason": str(outcome.get("reason") or "compose_failed"),
                "source_arm": str(outcome.get("source_arm") or "unknown"),
                "elapsed_ms": outcome.get("elapsed_ms", 0.0),
            }
        return {
            "ok": True,
            "tuple": (outcome["loaded"],),
            "owners": list(outcome.get("owners") or []),
            "source_arm": str(outcome.get("source_arm") or "unknown"),
            "elapsed_ms": outcome.get("elapsed_ms", 0.0),
        }
    except Exception as exc:  # noqa: BLE001 - substitution contract: never raise
        return {"ok": False, "reason": f"{type(exc).__name__}:{str(exc)[:150]}"}


def _kitchen_policy_backend() -> str:
    """Deploy-owned attention selection for generic runs (never raises).

    Mirrors the profile intent: when the deployment selects
    ``comfy_kitchen``, generic native sampling runs under the same
    shared attention scope canonical sampling uses.  Anything else
    means native attention untouched.
    """
    try:
        return str(os.environ.get(
            "COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND", "") or "").strip().lower()
    except Exception:
        return ""


def _kitchen_scope_for(patcher: Any, backend: str) -> Any:
    """Return the shared attention scope (imported, never copied)."""
    from .golden_serial import attention_backend_scope

    return attention_backend_scope(patcher, backend)


def _is_sampler_node(obj: Any, input_data_all: Any) -> bool:
    """True for sampler-like nodes carrying a model input. Never raises."""
    try:
        if "sampler" not in type(obj).__name__.lower():
            return False
        if not isinstance(input_data_all, dict):
            return False
        model = input_data_all.get("model")
        if isinstance(model, (list, tuple)):
            return len(model) > 0 and model[0] is not None
        return model is not None
    except Exception:
        return False


async def _run_native_with_kitchen_option(
    active: Mapping[str, Any],
    prompt_id: Any,
    unique_id: Any,
    obj: Any,
    input_data_all: Any,
    original: Any,
    *,
    execution_block_cb: Any = None,
    pre_execute_cb: Any = None,
    v3_data: Any = None,
) -> Any:
    """Native execution with kitchen attention forced for sampler nodes.

    Samplers are NEVER replaced (owner decision): the original native
    call runs, wrapped in the shared attention scope when the deployment
    selects ``comfy_kitchen``.  Scope-setup failure falls back to the
    bare native call with a skipped event; node errors propagate
    unchanged (the scope restores via its own finally).  Never raises
    itself.
    """
    node_id = str(unique_id)
    try:
        if not _is_sampler_node(obj, input_data_all):
            # Generic node wall for the single gantt: every non-sampler,
            # non-substituted node execution gets one span so nothing on
            # the critical path is invisible. Classes already covered by
            # dedicated spans (paired-event VAE/output spans, loader and
            # sampler substitution spans, inner LLM span) are skipped to
            # avoid double bars. Measurement only; never alters dispatch.
            try:
                _cls_name = type(obj).__name__
            except Exception:
                _cls_name = ""
            _skip_prefixes = (
                "VAEDecode",
                "ComfyModalProductionOutput",
                "ComfyModalProductionImageComparerOutput",
                "TextGenerate",
                "CLIPLoader",
                "UNETLoader",
                "VAELoader",
                "DualCLIPLoader",
                "CheckpointLoader",
            )
            if _cls_name and not _cls_name.startswith(_skip_prefixes):
                try:
                    import time as _node_time
                    _node_start_ns = int(_node_time.monotonic_ns())
                except Exception:
                    _node_time = None  # type: ignore[assignment]
                    _node_start_ns = 0
                try:
                    return await original(
                        prompt_id, unique_id, obj, input_data_all,
                        execution_block_cb=execution_block_cb,
                        pre_execute_cb=pre_execute_cb, v3_data=v3_data,
                    )
                finally:
                    try:
                        if _node_time is not None and _node_start_ns:
                            _node_end_ns = int(_node_time.monotonic_ns())
                            if _node_end_ns >= _node_start_ns:
                                from .gantt_telemetry import (
                                    register_gantt_span as _node_register_span,
                                )
                                _upper = _cls_name.upper()
                                if "ENCODE" in _upper or "CLIP" in _upper:
                                    _node_lane = "CPU"
                                elif "SAMPL" in _upper:
                                    _node_lane = "GPU"
                                else:
                                    _node_lane = "MAIN"
                                _node_register_span(
                                    f"{_cls_name} (node {node_id})",
                                    start_mono_ns=_node_start_ns,
                                    end_mono_ns=_node_end_ns,
                                    lane=_node_lane,
                                    metadata={
                                        "node_id": node_id,
                                        "node_class": _cls_name,
                                    },
                                )
                    except Exception:
                        pass
            return await original(
                prompt_id, unique_id, obj, input_data_all,
                execution_block_cb=execution_block_cb,
                pre_execute_cb=pre_execute_cb, v3_data=v3_data,
            )
    except Exception:
        return await original(
            prompt_id, unique_id, obj, input_data_all,
            execution_block_cb=execution_block_cb,
            pre_execute_cb=pre_execute_cb, v3_data=v3_data,
        )
    # Sampler execution: timed wall for the single gantt. Measurement
    # only: never alters dispatch, fallback, or error semantics.
    try:
        import time as _samp_time
        _samp_start_ns = int(_samp_time.monotonic_ns())
    except Exception:
        _samp_time = None  # type: ignore[assignment]
        _samp_start_ns = 0

    def _record_sampling_span() -> None:
        try:
            if _samp_time is None or not _samp_start_ns:
                return
            _samp_end_ns = int(_samp_time.monotonic_ns())
            if _samp_end_ns < _samp_start_ns:
                return
            from .gantt_telemetry import register_gantt_span as _samp_register_span
            _samp_register_span(
                "sampling",
                start_mono_ns=_samp_start_ns,
                end_mono_ns=_samp_end_ns,
                lane="GPU",
                metadata={"node_id": node_id},
            )
        except Exception:
            pass

    try:
        if _kitchen_policy_backend() != "comfy_kitchen":
            try:
                return await original(
                    prompt_id, unique_id, obj, input_data_all,
                    execution_block_cb=execution_block_cb,
                    pre_execute_cb=pre_execute_cb, v3_data=v3_data,
                )
            finally:
                _record_sampling_span()
        model = input_data_all.get("model")
        patcher = model[0] if isinstance(model, (list, tuple)) else model
        try:
            scope = _kitchen_scope_for(patcher, "comfy_kitchen")
        except Exception as setup_exc:
            _emit_trace(
                active.get("trace_emit"), "generic_kitchen_attention",
                node_id=node_id, requested="comfy_kitchen",
                outcome="skipped",
                reason=f"scope_setup:{type(setup_exc).__name__}",
            )
            try:
                return await original(
                    prompt_id, unique_id, obj, input_data_all,
                    execution_block_cb=execution_block_cb,
                    pre_execute_cb=pre_execute_cb, v3_data=v3_data,
                )
            finally:
                _record_sampling_span()
        with scope as scope_state:
            try:
                result = await original(
                    prompt_id, unique_id, obj, input_data_all,
                    execution_block_cb=execution_block_cb,
                    pre_execute_cb=pre_execute_cb, v3_data=v3_data,
                )
            finally:
                _record_sampling_span()
        try:
            selected = str((scope_state or {}).get("selected_callable", ""))
            calls = int((scope_state or {}).get("calls", 0) or 0)
        except Exception:
            selected, calls = "", 0
        _emit_trace(
            active.get("trace_emit"), "generic_kitchen_attention",
            node_id=node_id, requested="comfy_kitchen",
            outcome="engaged", selected=selected, calls=calls,
        )
        return result
    except Exception:
        _record_sampling_span()
        return await original(
            prompt_id, unique_id, obj, input_data_all,
            execution_block_cb=execution_block_cb,
            pre_execute_cb=pre_execute_cb, v3_data=v3_data,
        )


async def _run_substituted_loader(
    *, role: str, node_id: str, inputs: Mapping[str, Any], ctx: Mapping[str, Any]
) -> dict[str, Any]:
    """Execute the golden stage for one role-bound loader node.

    Arms per role, all imported shared code, strict native fallback:
    ``clip`` (shared stage first: proven working end to end on FP8
    sources since the quant-marker and real-device fixes; QD4 second),
    ``unet`` / ``model_unet`` and ``vae`` (their stages via a shared
    helper).  Returns ``{"ok": True, ...}`` or ``{"ok": False, ...}``.
    Never raises.
    """
    request_id = str(ctx.get("request_id") or "")
    try:
        given = inputs if isinstance(inputs, dict) else {}
        if role != "clip":
            return await _substitute_unet_vae_loader(
                role=role, inputs=given, request_id=request_id)
        classification = classify_loader_node(
            "CLIPLoader", inputs if isinstance(inputs, dict) else {}
        )
        if not classification.get("supported"):
            return {"ok": False,
                    "reason": str(classification.get("reason") or "unsupported")}
        # Shared-stage-first routing: the stage owns FP8 sources end to
        # end since the quant-marker and real-device fixes (proven live).
        # QD4 second.  Keep both attempt walls so a slow invocation cannot
        # hide a failed first arm.
        attempt_walls: list[dict[str, Any]] = []
        try:
            stage_outcome = await compose_generic_clip_load_stage(
                clip_filenames=[str(classification.get("clip_name") or "")],
                clip_type=str(classification.get("clip_type") or "stable_diffusion"),
                folder="text_encoders",
                request_id=request_id,
            )
        except Exception as exc:  # noqa: BLE001 - fallback contract
            stage_outcome = {"ok": False,
                             "reason": f"{type(exc).__name__}:{str(exc)[:150]}",
                             "source_arm": "golden_clip",
                             "elapsed_ms": 0.0}
        attempt_walls.append({
            "arm": str(stage_outcome.get("source_arm") or "golden_clip"),
            "ok": bool(stage_outcome.get("ok")),
            "elapsed_ms": float(stage_outcome.get("elapsed_ms") or 0.0),
            "reason": str(stage_outcome.get("reason") or ""),
        })
        if stage_outcome.get("ok") and stage_outcome.get("clip") is not None:
            stage_outcome["attempt_walls"] = attempt_walls
            try:
                print(
                    "[v2.generic_attempt_walls] role=clip walls={}".format(
                        json.dumps(attempt_walls)[:600]),
                    flush=True)
            except Exception:
                pass
            return {
                "ok": True,
                "tuple": (stage_outcome["clip"],),
                "owners": list(stage_outcome.get("owners") or []),
                "source_arm": str(stage_outcome.get("source_arm") or "unknown"),
                "elapsed_ms": stage_outcome.get("elapsed_ms", 0.0),
                "attempt_walls": attempt_walls,
            }
        try:
            outcome = await compose_generic_clip_load_qd4(
                clip_filenames=[str(classification.get("clip_name") or "")],
                clip_type=str(classification.get("clip_type") or "stable_diffusion"),
                folder="text_encoders",
                request_id=request_id,
            )
        except Exception as exc:  # noqa: BLE001 - fallback contract
            outcome = {"ok": False,
                       "reason": f"{type(exc).__name__}:{str(exc)[:150]}",
                       "source_arm": "qd4_demand",
                       "elapsed_ms": 0.0}
        attempt_walls.append({
            "arm": str(outcome.get("source_arm") or "qd4_demand"),
            "ok": bool(outcome.get("ok")),
            "elapsed_ms": float(outcome.get("elapsed_ms") or 0.0),
            "reason": str(outcome.get("reason") or ""),
        })
        outcome["attempt_walls"] = attempt_walls
        try:
            print(
                "[v2.generic_attempt_walls] role=clip walls={}".format(
                    json.dumps(attempt_walls)[:600]),
                flush=True)
        except Exception:
            pass
        if not outcome.get("ok"):
            stage_reason = str(stage_outcome.get("reason") or "stage_failed")
            outcome["reason"] = (
                f"{stage_reason}|{outcome.get('reason') or 'qd4_failed'}"
            )
        if not outcome.get("ok") or outcome.get("clip") is None:
            return {
                "ok": False,
                "reason": str(outcome.get("reason") or "compose_failed"),
                "source_arm": str(outcome.get("source_arm") or "unknown"),
                "elapsed_ms": outcome.get("elapsed_ms", 0.0),
                "attempt_walls": attempt_walls,
            }
        return {
            "ok": True,
            "tuple": (outcome["clip"],),
            "owners": list(outcome.get("owners") or []),
            "source_arm": str(outcome.get("source_arm") or "unknown"),
            "elapsed_ms": outcome.get("elapsed_ms", 0.0),
            "phases": dict(outcome.get("phases") or {}),
            "attempt_walls": attempt_walls,
        }
    except Exception as exc:  # noqa: BLE001 - substitution contract: never raise
        return {"ok": False, "reason": f"{type(exc).__name__}:{str(exc)[:150]}"}


def _overlap_select_pick(
    *, available: Any, clip_node_id: Any, unet_node_id: Any,
    forward_node_id: Any, deferral_allowed: bool, dispatched: Any,
) -> dict[str, Any]:
    """Pure pick-policy decision (no executor access).

    Returns ``{"action": "pick", "node_id": ...}`` to force one ready
    node, ``{"action": "exclude", "node_id": ...}`` to pick via the
    original policy from the ready set minus that node, or
    ``{"action": "original"}`` to leave ordering untouched.  Deferral
    only ever postpones the UNET loader while other ready nodes exist
    (finite drain: it still dispatches), and only when UNET is proven
    not to gate the forward node — misidentification costs overlap,
    never correctness.  Never raises.
    """
    try:
        avail = [str(n) for n in (available or [])]
        done = set(str(n) for n in (dispatched or ()))
        clip = str(clip_node_id or "")
        unet = str(unet_node_id or "")
        fwd = str(forward_node_id or "")
        if clip and clip in avail and clip not in done:
            return {"action": "pick", "node_id": clip}
        if (bool(deferral_allowed) and unet and fwd
                and unet in avail and fwd not in done):
            if fwd in avail:
                return {"action": "pick", "node_id": fwd}
            if [n for n in avail if n != unet]:
                return {"action": "exclude", "node_id": unet}
        return {"action": "original", "node_id": None}
    except Exception:
        return {"action": "original", "node_id": None}


def _overlap_advise_model(*, folder: Any, filename: Any) -> dict[str, Any]:
    """Resolve + stat + advise one model file (pure IO hint, never raises).

    Content-agnostic page-cache warming for a later load of the same
    path: safe regardless of snapshot/cache validity (the kernel drops
    unused or invalidated pages freely) and skipped cleanly where the
    platform lacks the hint.  Never reads tensor payloads.
    """
    started_ns = time.monotonic_ns()

    def _fail(reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "reason": str(reason),
            "path": None,
            "size_bytes": 0,
            "advise_status": "not_attempted",
            "advised_bytes": 0,
            "elapsed_ms": (time.monotonic_ns() - started_ns) / 1_000_000.0,
        }

    try:
        name = str(filename or "").strip()
        if not name:
            return _fail("filename_missing")
        path = _default_path_resolver(str(folder or ""), name)
        if not path:
            return _fail(f"source_path_unresolvable:{name}")
        try:
            size_bytes = int(os.stat(path).st_size)
        except Exception:
            return _fail("source_stat_failed")
        advise = _advise_sequential_source(path, size_bytes)
        return {
            "ok": True,
            "reason": "",
            "path": path,
            "size_bytes": size_bytes,
            "advise_status": str(advise.get("status") or ""),
            "advised_bytes": int(advise.get("advised_bytes") or 0),
            "elapsed_ms": (time.monotonic_ns() - started_ns) / 1_000_000.0,
        }
    except Exception as exc:  # noqa: BLE001 - hint contract: never raise
        return _fail(type(exc).__name__)


def _install_overlap_pick_policy(
    *, trace_emit: Callable[..., Any] | None, request_id: str,
    get_ctx: Callable[[], Any],
) -> Callable[[], None] | None:
    """Wrap ExecutionList.ux_friendly_pick_node per request (save/restore).

    Mirrors the repo's established ExecutionList patch discipline: the
    original is restored only if the wrapper is still installed, and any
    failure (including a missing graph module) means no policy with the
    stock ordering untouched.  The wrapper consults the live request
    context on every pick, so teardown (context cleared) degrades to
    passthrough even before restore runs.  Never raises.
    """
    try:
        try:
            from comfy_execution.graph import ExecutionList as _ExecList
        except Exception:
            return None
        orig = getattr(_ExecList, "ux_friendly_pick_node", None)
        if not callable(orig):
            return None
        if getattr(orig, "__overlap_wrapped__", False):
            return None

        def _wrapped_pick(self: Any, node_list: Any) -> Any:
            try:
                ctx = get_ctx()
                plan = (ctx or {}).get("overlap_plan") or {}
                if not plan.get("eligible"):
                    return orig(self, node_list)
                avail = [str(n) for n in (node_list or [])]
                done = set((ctx or {}).get("dispatched_nodes") or set())
                decision = _overlap_select_pick(
                    available=avail,
                    clip_node_id=plan.get("clip_node_id"),
                    unet_node_id=plan.get("unet_node_id"),
                    forward_node_id=plan.get("forward_node_id"),
                    deferral_allowed=bool(plan.get("deferral_allowed")),
                    dispatched=done)
                action = str(decision.get("action") or "original")
                if action == "pick":
                    _emit_trace(trace_emit, "generic_overlap_pick",
                                request_id=str(request_id or ""),
                                action="pick",
                                node_id=str(decision.get("node_id") or ""))
                    return decision.get("node_id")
                if action == "exclude":
                    rest = [n for n in avail
                            if n != str(decision.get("node_id") or "")]
                    if rest:
                        _emit_trace(trace_emit, "generic_overlap_pick",
                                    request_id=str(request_id or ""),
                                    action="exclude",
                                    node_id=str(decision.get("node_id") or ""))
                        return orig(self, rest)
                return orig(self, node_list)
            except Exception:
                return orig(self, node_list)

        _wrapped_pick.__overlap_wrapped__ = True  # type: ignore[attr-defined]
        _ExecList.ux_friendly_pick_node = _wrapped_pick  # type: ignore[method-assign]

        def _restore_pick() -> None:
            try:
                if (getattr(_ExecList, "ux_friendly_pick_node", None)
                        is _wrapped_pick):
                    _ExecList.ux_friendly_pick_node = orig  # type: ignore[method-assign]
            except Exception:
                pass

        return _restore_pick
    except Exception:
        return None


def install_execution_dispatch_substitution(
    *,
    role_bindings: Any,
    holder: GenericLoaderHolder | None,
    trace_emit: Callable[..., Any] | None,
    request_id: str,
    workflow: Any = None,
) -> Callable[[], None] | None:
    """Wrap upstream ``execution.get_output_data`` with role substitution.

    Installs once per generic request; returns a restore callable that
    reinstalls the original and clears the request window (call it in the
    request finally-block).  Returns None when there is nothing eligible,
    when already installed, or when installation fails — native behavior
    is always the fallback.  Only loader roles substitute; every other
    node passes through untouched.
    """
    global _ACTIVE_DISPATCH_CTX
    try:
        import execution as _execution_mod
    except Exception:
        _emit_trace(trace_emit, "generic_dispatch_install", outcome="skipped",
                    reason="execution_import_failed",
                    request_id=str(request_id or ""))
        return None
    try:
        original = getattr(_execution_mod, "get_output_data", None)
        merge_fn = getattr(_execution_mod, "merge_result_data", None)
        if not callable(original) or not callable(merge_fn):
            _emit_trace(trace_emit, "generic_dispatch_install", outcome="skipped",
                        reason="dispatch_boundary_missing",
                        request_id=str(request_id or ""))
            return None
        if _ACTIVE_DISPATCH_CTX is not None:
            _emit_trace(trace_emit, "generic_dispatch_install", outcome="skipped",
                        reason="already_active",
                        request_id=str(request_id or ""))
            return None
        node_roles = _invert_role_bindings(role_bindings)
        if not node_roles:
            try:
                _received = sorted(
                    str(k) for k in (role_bindings.keys()
                                     if isinstance(role_bindings, Mapping) else [])
                )
            except Exception:
                _received = []
            _emit_trace(trace_emit, "generic_dispatch_install", outcome="skipped",
                        reason="no_eligible_roles",
                        roles_received=",".join(_received)[:200],
                        request_id=str(request_id or ""))
            return None
        ctx: dict[str, Any] = {
            "request_id": str(request_id or ""),
            "node_roles": node_roles,
            "holder": holder,
            "trace_emit": trace_emit,
            "original": original,
            "merge_fn": merge_fn,
            "module": _execution_mod,
        }
        # Overlap plan (Phase 1: derive + observe only, no scheduling).
        # Default-off switch: disabled means the planner never runs and the
        # context carries a documenting ineligible plan.  No worker, read,
        # allocation, or cache change happens in either case.
        overlap_plan: dict[str, Any] = _overlap_ineligible("overlap_disabled")
        if _overlap_switch_enabled():
            overlap_plan = _derive_generic_overlap_plan(
                workflow=workflow, role_bindings=role_bindings)
            _emit_trace(trace_emit, "generic_overlap_plan",
                        request_id=str(request_id or ""),
                        eligible=bool(overlap_plan.get("eligible")),
                        clip_node_id=overlap_plan.get("clip_node_id"),
                        unet_node_id=overlap_plan.get("unet_node_id"),
                        forward_node_id=overlap_plan.get("forward_node_id"),
                        deferral_allowed=bool(
                            overlap_plan.get("deferral_allowed")),
                        reason=str(overlap_plan.get("reason") or ""))
        ctx["overlap_plan"] = overlap_plan
        ctx["overlap_pick_restore"] = None
        if overlap_plan.get("eligible"):
            # Warm both model files while setup runs: content-agnostic
            # page-cache hints, harmless when unused or invalidated.
            try:
                wf_nodes = workflow if isinstance(workflow, Mapping) else {}
                _adv_targets: list[tuple[str, str, Any]] = []
                _clip_node = wf_nodes.get(
                    str(overlap_plan.get("clip_node_id") or ""))
                if isinstance(_clip_node, Mapping):
                    _clip_inputs = _clip_node.get("inputs")
                    if isinstance(_clip_inputs, Mapping):
                        _adv_targets.append((
                            "clip", "text_encoders",
                            _clip_inputs.get("clip_name")))
                _unet_id = str(overlap_plan.get("unet_node_id") or "")
                if _unet_id:
                    _unet_node = wf_nodes.get(_unet_id)
                    if isinstance(_unet_node, Mapping):
                        _unet_inputs = _unet_node.get("inputs")
                        if isinstance(_unet_inputs, Mapping):
                            _adv_targets.append((
                                "model_unet", "diffusion_models",
                                _unet_inputs.get("unet_name")))
                for _role, _folder, _filename in _adv_targets:
                    if not isinstance(_filename, str) or not _filename.strip():
                        continue
                    _adv = _overlap_advise_model(
                        folder=_folder, filename=_filename)
                    _emit_trace(trace_emit, "generic_overlap_advise",
                                request_id=str(request_id or ""),
                                role=_role,
                                ok=bool(_adv.get("ok")),
                                advise_status=str(
                                    _adv.get("advise_status") or ""),
                                size_bytes=int(_adv.get("size_bytes") or 0),
                                elapsed_ms=float(_adv.get("elapsed_ms") or 0.0),
                                reason=str(_adv.get("reason") or ""))
            except Exception:
                pass
            try:
                ctx["overlap_pick_restore"] = _install_overlap_pick_policy(
                    trace_emit=trace_emit,
                    request_id=str(request_id or ""),
                    get_ctx=lambda: _ACTIVE_DISPATCH_CTX)
            except Exception:
                ctx["overlap_pick_restore"] = None
        _ACTIVE_DISPATCH_CTX = ctx

        async def _substituting_get_output_data(
            prompt_id: Any,
            unique_id: Any,
            obj: Any,
            input_data_all: Any,
            execution_block_cb: Any = None,
            pre_execute_cb: Any = None,
            v3_data: Any = None,
        ) -> Any:
            active = _ACTIVE_DISPATCH_CTX
            if active is None:
                return await original(
                    prompt_id, unique_id, obj, input_data_all,
                    execution_block_cb=execution_block_cb,
                    pre_execute_cb=pre_execute_cb, v3_data=v3_data,
                )
            try:
                _ov_plan = active.get("overlap_plan") or {}
                if _ov_plan.get("eligible"):
                    _disp = active.get("dispatched_nodes")
                    if _disp is None:
                        _disp = set()
                        active["dispatched_nodes"] = _disp
                    _disp.add(str(unique_id))
            except Exception:
                pass
            decision = _select_substitution(active, unique_id, obj, input_data_all)
            if decision is None:
                return await _run_native_with_kitchen_option(
                    active, prompt_id, unique_id, obj, input_data_all,
                    original,
                    execution_block_cb=execution_block_cb,
                    pre_execute_cb=pre_execute_cb, v3_data=v3_data,
                )
            try:
                import time as _time
                _sub_start_ns = int(_time.monotonic_ns())
            except Exception:
                _time = None  # type: ignore[assignment]
                _sub_start_ns = 0
            sub = await _run_substituted_loader(
                role=str(decision["role"]), node_id=str(decision["node_id"]),
                inputs=decision["inputs"], ctx=active,
            )
            try:
                if _time is not None and _sub_start_ns:
                    _sub_end_ns = int(_time.monotonic_ns())
                    _role_norm = str(decision["role"]).strip().lower()
                    if _role_norm in ("clip",):
                        _span_name, _span_lane = "CLIP load", "STORAGE"
                    elif _role_norm in ("unet", "model_unet"):
                        _span_name, _span_lane = "UNET load", "STORAGE"
                    elif _role_norm in ("vae",):
                        _span_name, _span_lane = "VAE load", "MODEL-MGMT"
                    else:
                        _span_name, _span_lane = "", ""
                    if _span_name and _sub_end_ns >= _sub_start_ns:
                        from .gantt_telemetry import register_gantt_span as _register_span
                        _register_span(
                            _span_name,
                            start_mono_ns=_sub_start_ns,
                            end_mono_ns=_sub_end_ns,
                            lane=_span_lane,
                            metadata={
                                "node_id": str(decision["node_id"]),
                                "role": str(decision["role"]),
                                "source_arm": str(sub.get("source_arm") or "unknown"),
                                "ok": bool(sub.get("ok")),
                            },
                        )
            except Exception:
                pass
            if not sub.get("ok"):
                _emit_trace(
                    active.get("trace_emit"), "generic_dispatch_substitution",
                    node_id=str(decision["node_id"]), role=str(decision["role"]),
                    requested="shared_core", actual="native",
                    reason=str(sub.get("reason") or "substitute_failed"),
                    source_arm=str(sub.get("source_arm") or "unknown"),
                )
                return await original(
                    prompt_id, unique_id, obj, input_data_all,
                    execution_block_cb=execution_block_cb,
                    pre_execute_cb=pre_execute_cb, v3_data=v3_data,
                )
            try:
                owners = sub.get("owners") or []
                if owners and active.get("holder") is not None:
                    active["holder"].retain(None, owners)
            except Exception:
                pass
            try:
                output = merge_fn([sub["tuple"]], obj)
            except Exception as merge_exc:
                _emit_trace(
                    active.get("trace_emit"), "generic_dispatch_substitution",
                    node_id=str(decision["node_id"]), role=str(decision["role"]),
                    requested="shared_core", actual="native",
                    reason=f"merge_failed:{type(merge_exc).__name__}",
                    source_arm=str(sub.get("source_arm") or "unknown"),
                )
                return await original(
                    prompt_id, unique_id, obj, input_data_all,
                    execution_block_cb=execution_block_cb,
                    pre_execute_cb=pre_execute_cb, v3_data=v3_data,
                )
            _emit_trace(
                active.get("trace_emit"), "generic_dispatch_substitution",
                node_id=str(decision["node_id"]), role=str(decision["role"]),
                requested="shared_core", actual="shared_core",
                reason="", source_arm=str(sub.get("source_arm") or "unknown"),
                elapsed_ms=sub.get("elapsed_ms", 0.0),
                phases=sub.get("phases", {}),
            )
            return output, {}, False, False

        _execution_mod.get_output_data = _substituting_get_output_data  # type: ignore[method-assign]

        def _restore_dispatch() -> None:
            global _ACTIVE_DISPATCH_CTX
            try:
                _pick_restore = ctx.get("overlap_pick_restore")
                if callable(_pick_restore):
                    _pick_restore()
            except Exception:
                pass
            try:
                mod = ctx.get("module")
                if mod is not None and getattr(
                    mod, "get_output_data", None
                ) is _substituting_get_output_data:
                    mod.get_output_data = ctx.get("original")
            except Exception:
                pass
            _ACTIVE_DISPATCH_CTX = None

        _emit_trace(trace_emit, "generic_dispatch_install", outcome="installed",
                    roles=len(node_roles),
                    role_nodes=",".join(
                        f"{nid}:{role}" for nid, role in sorted(node_roles.items())
                    )[:300],
                    request_id=str(request_id or ""))
        return _restore_dispatch
    except Exception:
        return None
