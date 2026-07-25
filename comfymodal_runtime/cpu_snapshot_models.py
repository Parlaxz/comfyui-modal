"""CPU snapshot model loading, validation, and retargeting.

This module produces a validated CpuSnapshotModels struct from a warmup
profile (mode=split only).  It loads CLIP and UNET sequentially with
gc.collect barriers, emits trace events, and supports validation and
device retargeting against the live ComfyUI model_management module.
"""

from __future__ import annotations

import gc
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .contracts import ModelRestoreKey
from .trace import RuntimeTrace

# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelFileFact:
    role: str  # "unet", "clip1", "clip2"
    path: str
    size_bytes: int
    mtime_ns: int


# Current policy version — increment when compute-policy semantics change
# so that old snapshots with stale/legacy defaults are rejected.
CPU_SNAPSHOT_UNET_POLICY_VERSION: int = 2


def _policy_identity(
    version: int,
    effective_weight_dtype: str,
    effective_compute_dtype: str,
    manual_cast_policy: str,
) -> str:
    """Deterministic identity derived from version and effective policies."""
    return (
        f"v{version}:"
        f"weight={effective_weight_dtype}:"
        f"compute={effective_compute_dtype}:"
        f"manual={manual_cast_policy}"
    )


@dataclass
class CpuSnapshotModels:
    model_key: ModelRestoreKey
    model_spec: dict[str, Any]
    normalized_profile: dict[str, Any]
    file_facts: tuple[ModelFileFact, ...]
    unet: Any = None
    clip: Any = None
    load_timings_ms: dict[str, float] = field(default_factory=dict)
    compute_policy: str = "default"
    policy_version: int = CPU_SNAPSHOT_UNET_POLICY_VERSION
    target_gpus: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

_LOADER_KEYS = frozenset({"mode", "unet", "clip1", "clip2", "clip_type", "weight_dtype"})


def _normalize_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    """Return only restore-relevant identity fields for mode=split.

    The field policy comes from the repository's canonical warmup-profile
    normalizer; this helper only projects its restore fields for Plan A.
    """
    raw = dict(profile) if isinstance(profile, Mapping) else {}
    if raw.get("clip2") is None:
        raw["clip2"] = ""
    from warmup_profile import _normalize_stable_profile

    stable = _normalize_stable_profile(raw)
    normalized: dict[str, Any] = {
        key: stable.get(key, "")
        for key in ("mode", "unet", "clip1", "clip2", "clip_type")
    }
    if raw.get("clip2") and normalized["clip2"] != raw["clip2"]:
        normalized["clip2"] = raw["clip2"].strip()
    if "weight_dtype" in stable:
        normalized["weight_dtype"] = stable["weight_dtype"]
    return normalized


def _build_model_key(normalized: dict[str, Any]) -> ModelRestoreKey:
    from .restore_plan import _build_dual_clip_identity

    clip1 = normalized["clip1"]
    clip2 = normalized.get("clip2", "")
    clip = _build_dual_clip_identity(clip1, clip2) if clip2 else clip1
    return ModelRestoreKey(
        unet_identity=normalized["unet"],
        clip_identity=clip,
        vae_identity="",
        clip_type=normalized["clip_type"],
    )


# ── Compute policy identity field ───────────────────────────────────
# This field in model_spec distinguishes the compute/manual-cast policy
# used during snapshot construction so that a snapshot built with one
# policy cannot match an identity that requested a different policy.
#   "default"  — no explicit override (legacy / non-BF16).
#   "bf16_native" — manual_cast_dtype=None, native BF16 compute.
_COMPUTE_POLICY_DEFAULT = "default"
_COMPUTE_POLICY_BF16_NATIVE = "bf16_native"


def _resolve_compute_policy(
    weight_dtype_str: str,
    *,
    target_gpus: tuple[str, ...] | None = None,
) -> str:
    """Determine the compute policy label for snapshot identity.

    Returns ``"bf16_native"`` when the effective dtype resolves to BF16
    AND the primary target GPU supports BF16 (so the model is built with
    native BF16 compute, no manual cast).  Uses primary target semantics
    consistently with ``resolve_unet_effective_dtype`` — fallback GPUs
    are NOT considered for policy resolution.

    Returns ``"default"`` otherwise.
    """
    from gpu_catalog import gpu_supports_bf16
    _primary = target_gpus[0] if target_gpus else ""
    if not _primary:
        return _COMPUTE_POLICY_DEFAULT
    # "default" weight_dtype on a BF16-capable primary → native
    if weight_dtype_str == "default" and gpu_supports_bf16(_primary):
        return _COMPUTE_POLICY_BF16_NATIVE
    # Explicit bf16 on a BF16-capable primary → native
    import torch as _torch
    _is_explicit_bf16 = (
        weight_dtype_str == "bfloat16"
        or weight_dtype_str == "bf16"
        or weight_dtype_str == str(_torch.bfloat16)
    )
    if _is_explicit_bf16 and gpu_supports_bf16(_primary):
        return _COMPUTE_POLICY_BF16_NATIVE
    return _COMPUTE_POLICY_DEFAULT


def _build_model_spec(normalized: dict[str, Any]) -> dict[str, Any]:
    """Build loaders from the normalized profile.

    Matches restore_plan.py shape: weight_dtype always present
    in the UNET loader ("default" when absent from profile).
    No node IDs, prompt fields, or hashes.

    NOTE: compute policy identity is stored separately on
    CpuSnapshotModels.compute_policy, NOT in model_spec.
    """
    unet_loader: dict[str, Any] = {
        "loader_class": "UNETLoader",
        "unet_name": normalized["unet"],
        "weight_dtype": normalized.get("weight_dtype", "default"),
    }
    clip_type = normalized.get("clip_type") or "stable_diffusion"
    if normalized.get("clip2"):
        clip_loader: dict[str, Any] = {
            "loader_class": "DualCLIPLoader",
            "clip_name1": normalized["clip1"],
            "clip_name2": normalized["clip2"],
            "type": clip_type,
            "device": "default",
        }
    else:
        clip_loader = {
            "loader_class": "CLIPLoader",
            "clip_name": normalized["clip1"],
            "type": clip_type,
            "device": "default",
        }
    return {
        "loaders": {
            "unet": [unet_loader],
            "clip": [clip_loader],
            "vae": [],
        },
    }


def _stat_file(role: str, filename: str, *, resolve_path: Callable[[str, str], str]) -> ModelFileFact:
    """Stat one model file through the resolve_path callback.

    Never reads or hashes file content — stat only.
    """
    resolved = resolve_path(role, filename)
    st = os.stat(resolved)
    return ModelFileFact(
        role=role,
        path=resolved,
        size_bytes=st.st_size,
        mtime_ns=int(st.st_mtime_ns if hasattr(st, "st_mtime_ns") else st.st_mtime * 1_000_000_000),
    )


# ---------------------------------------------------------------------------
# Tensor / shape validation helpers (private)
# ---------------------------------------------------------------------------


def _tensor_device_type(tensor: Any) -> str | None:
    """Return the lower-case device type of *tensor*, or None if not inspectable."""
    dev = getattr(tensor, "device", None)
    if dev is None:
        return None
    if isinstance(dev, str):
        return dev.strip().lower().split(":")[0]
    # torch.device or duck-typed
    dt = getattr(dev, "type", None)
    if dt is None:
        return str(dev).strip().lower().split(":")[0]
    return str(dt).strip().lower()


def _check_tensor_devices(module: Any, context: str = "") -> tuple[bool, str]:
    """Enumerate parameters and buffers from *module*; reject CUDA/meta tensors.

    Returns (True, "") if all tensors are safe, (False, reason) otherwise.
    Does NOT call torch.cuda APIs.
    """
    def check_collection(method_name: str, label: str) -> tuple[bool, str]:
        method = getattr(module, method_name, None)
        if not callable(method):
            return False, f"{context}{method_name} is not inspectable"
        try:
            try:
                values: Any = method(recurse=True)
            except TypeError:
                values = method()
            for entry in values:
                if isinstance(entry, tuple) and len(entry) == 2:
                    name, tensor = entry
                else:
                    name, tensor = "<unnamed>", entry
                if getattr(tensor, "is_meta", False):
                    return False, f"{context}{label} {name} is meta"
                dt = _tensor_device_type(tensor)
                if dt is not None and (dt.startswith("cuda") or dt == "meta"):
                    return False, f"{context}{label} {name} on {dt}"
        except Exception as exc:
            return False, f"{context}{method_name} could not be inspected: {exc}"
        return True, ""

    ok, reason = check_collection("named_parameters", "parameter")
    if not ok:
        return False, reason
    ok, reason = check_collection("named_buffers", "buffer")
    if not ok:
        return False, reason

    return True, ""


def _is_module_like(obj: Any) -> bool:
    """Check if *obj* looks like a torch.nn.Module (duck-typing)."""
    if obj is None:
        return False
    return (hasattr(obj, "named_parameters") and callable(obj.named_parameters)
            and hasattr(obj, "named_buffers") and callable(obj.named_buffers))


def _collect_unet_modules(obj: Any) -> list[tuple[str, Any]]:
    """Collect inspectable torch-like modules from a UNET wrapper."""
    result: list[tuple[str, Any]] = []
    model = getattr(obj, "model", None)
    if model is not None and _is_module_like(model):
        result.append(("model", model))
        dm = getattr(model, "diffusion_model", None)
        if dm is not None and _is_module_like(dm) and dm is not model:
            result.append(("model.diffusion_model", dm))
    elif model is not None:
        # model itself isn't a module — try diffusion_model directly
        dm = getattr(model, "diffusion_model", None)
        if dm is not None and _is_module_like(dm):
            result.append(("model.diffusion_model", dm))
    dm = getattr(obj, "diffusion_model", None)
    if dm is not None and _is_module_like(dm) and all(module is not dm for _, module in result):
        result.append(("diffusion_model", dm))
    return result


def _collect_clip_modules(obj: Any) -> list[tuple[str, Any]]:
    """Collect inspectable torch-like modules from a CLIP wrapper."""
    result: list[tuple[str, Any]] = []
    csm = getattr(obj, "cond_stage_model", None)
    if csm is not None and _is_module_like(csm):
        result.append(("cond_stage_model", csm))
        for sub_attr in ("clip_l", "clip_g"):
            sub = getattr(csm, sub_attr, None)
            if sub is not None and _is_module_like(sub) and sub is not csm:
                result.append((f"cond_stage_model.{sub_attr}", sub))
    elif csm is not None:
        for sub_attr in ("clip_l", "clip_g"):
            sub = getattr(csm, sub_attr, None)
            if sub is not None and _is_module_like(sub):
                result.append((f"cond_stage_model.{sub_attr}", sub))
    if not result:
        # Try clip_l / clip_g directly on obj
        for sub_attr in ("clip_l", "clip_g"):
            sub = getattr(obj, sub_attr, None)
            if sub is not None and _is_module_like(sub):
                result.append((sub_attr, sub))
    if not result:
        # Fallback to patcher.model
        patcher = getattr(obj, "patcher", None)
        if patcher is not None:
            pm = getattr(patcher, "model", None)
            if pm is not None and _is_module_like(pm):
                result.append(("patcher.model", pm))
    return result


def _is_valid_unet_patcher(obj: Any) -> tuple[bool, str]:
    """Validate UNET patcher shape and tensor devices.

    Returns (True, "") on success, (False, reason) on failure.
    """
    if not hasattr(obj, "model"):
        return False, "unet missing .model attribute"
    if not hasattr(obj, "load_device"):
        return False, "unet missing .load_device attribute"
    if not hasattr(obj, "offload_device"):
        return False, "unet missing .offload_device attribute"

    modules = _collect_unet_modules(obj)
    if not modules:
        return False, "unet cannot locate inspectable torch module"

    for name, mod in modules:
        ok, reason = _check_tensor_devices(mod, f"unet.{name}.")
        if not ok:
            return False, reason

    # Also verify load_device/offload_device strings are not CUDA/meta
    for attr_name in ("load_device", "offload_device"):
        dev = getattr(obj, attr_name, None)
        if dev is not None:
            dt = _tensor_device_type_of_value(dev)
            if dt is not None and (dt.startswith("cuda") or dt == "meta"):
                return False, f"unet.{attr_name} is {dt}"

    return True, ""


def _is_valid_clip_patcher(obj: Any) -> tuple[bool, str]:
    """Validate CLIP patcher shape and tensor devices.

    Returns (True, "") on success, (False, reason) on failure.
    """
    patcher = getattr(obj, "patcher", None)
    if patcher is None:
        return False, "clip missing .patcher attribute"
    if not hasattr(patcher, "load_device"):
        return False, "clip.patcher missing .load_device attribute"
    if not hasattr(patcher, "offload_device"):
        return False, "clip.patcher missing .offload_device attribute"

    tokenizer = getattr(obj, "tokenizer", None)
    if tokenizer is None:
        return False, "clip missing .tokenizer attribute"

    modules = _collect_clip_modules(obj)
    if not modules:
        return False, "clip cannot locate inspectable torch module"

    for name, mod in modules:
        ok, reason = _check_tensor_devices(mod, f"clip.{name}.")
        if not ok:
            return False, reason

    # Also verify load_device/offload_device strings
    for attr_name in ("load_device", "offload_device"):
        dev = getattr(patcher, attr_name, None)
        if dev is not None:
            dt = _tensor_device_type_of_value(dev)
            if dt is not None and (dt.startswith("cuda") or dt == "meta"):
                return False, f"clip.patcher.{attr_name} is {dt}"

    return True, ""


def _tensor_device_type_of_value(val: Any) -> str | None:
    """Extract device type string from a device value (string or torch.device)."""
    if val is None:
        return None
    if isinstance(val, str):
        return val.strip().lower().split(":")[0]
    dt = getattr(val, "type", None)
    if dt is None:
        return str(val).strip().lower().split(":")[0]
    return str(dt).strip().lower()


# ---------------------------------------------------------------------------
# BF16-native validation
# ---------------------------------------------------------------------------


def _build_detail_str(
    requested_weight_dtype: str = "",
    effective_weight_dtype: Any = None,
    effective_compute_dtype: Any = None,
    target_gpus: tuple[str, ...] | None = None,
) -> str:
    _parts: list[str] = []
    if requested_weight_dtype:
        _parts.append(f"requested_weight_dtype={requested_weight_dtype}")
    if effective_weight_dtype is not None:
        _parts.append(f"effective_weight_dtype={effective_weight_dtype}")
    if effective_compute_dtype is not None:
        _parts.append(f"effective_compute_dtype={effective_compute_dtype}")
    if target_gpus:
        _parts.append(f"target_gpus={','.join(target_gpus)}")
    return " ".join(_parts) + " " if _parts else ""


def validate_snapshot_unet_bf16_native(
    unet: Any,
    *,
    context: str = "",
    target_gpus: tuple[str, ...] | None = None,
    requested_weight_dtype: str = "",
    effective_weight_dtype: Any = None,
    effective_compute_dtype: Any = None,
    param_distribution: dict[str, Any] | None = None,
) -> None:
    """Strict post-construction validation for BF16-native compute policy.

    Resolves the real diffusion model via ``unet.model.diffusion_model``
    (ComfyUI ModelPatcher structure), then verifies:
      - ``manual_cast_dtype`` on the inner BaseModel is ``None`` (absent)
      - ``model_dtype()`` on the patcher returns bfloat16
      - All floating-point parameters are CPU bfloat16 (no CUDA/meta/fp32/mixed)
      - Non-zero floating parameters (detects uninspected state)

    Uses ``inspect_and_validate_snapshot_params`` with
    ``expected_dtype=None, require_cpu=False`` to capture the full parameter
    distribution first, then evaluates all invariants.

    Every failure includes all metadata fields.  Does not fail before
    distribution is obtained except when the diffusion model is uninspectable
    (distribution shows ``"unavailable"``).

    When *param_distribution* is provided (pre-computed), it is included
    directly rather than re-inspecting.
    """
    import torch as _torch

    _detail_str = _build_detail_str(
        requested_weight_dtype, effective_weight_dtype,
        effective_compute_dtype, target_gpus,
    )

    if unet is None:
        raise RuntimeError(
            f"{context}BF16-native validation failed: unet is None. "
            f"{_detail_str}"
        )

    # ── Resolve the actual diffusion model ─────────────────────────────
    _model = getattr(unet, "model", None)
    if _model is None:
        raise RuntimeError(
            f"{context}BF16-native validation failed: unet missing .model attribute. "
            f"{_detail_str}"
        )
    _dm = getattr(_model, "diffusion_model", _model)

    # ── Read manual_cast_dtype from inner BaseModel ────────────────────
    _manual = getattr(_model, "manual_cast_dtype", None)
    _manual_str = str(_manual) if _manual is not None else "none"

    # ── Read model_dtype() from patcher ────────────────────────────────
    _md_fn = getattr(unet, "model_dtype", None)
    _model_dtype_str: str = "absent"
    if callable(_md_fn):
        try:
            _md_val = _md_fn()
            _model_dtype_str = str(_md_val)
        except Exception:
            _model_dtype_str = "error"

    # ── Capture parameter distribution (full, no early raise) ──────────
    _distribution: dict[str, Any] | str = "unavailable"
    if param_distribution is not None:
        _distribution = param_distribution
    else:
        try:
            _distribution = inspect_and_validate_snapshot_params(
                _dm,
                expected_dtype=None,
                require_cpu=False,
                context=f"{context}dist:",
            )
        except Exception:
            _distribution = "unavailable"

    # ── Build full metadata string for all error messages ──────────────
    def _full_msg(checks: list[str]) -> str:
        _parts = [f"{context}BF16-native validation failed"]
        if checks:
            _parts.append("; ".join(checks))
        _parts.append(
            f"{_detail_str}"
            f"model_dtype={_model_dtype_str} "
            f"manual_cast_dtype={_manual_str} "
            f"param_distribution={_distribution}"
        )
        return " ".join(_parts)

    # ── Invariant 1: manual_cast_dtype must be None ────────────────────
    if _manual is not None:
        raise RuntimeError(_full_msg([
            f"manual_cast_dtype is {_manual!r}, expected None",
        ]))

    # ── Invariant 2: model_dtype() must be bfloat16 ────────────────────
    if _model_dtype_str not in (str(_torch.bfloat16), "torch.bfloat16"):
        raise RuntimeError(_full_msg([
            f"model_dtype={_model_dtype_str}, expected bfloat16",
        ]))

    # ── Invariant 3: non-zero floating params, all BF16 on CPU ─────────
    if isinstance(_distribution, str) and _distribution == "unavailable":
        raise RuntimeError(_full_msg([
            "diffusion model is uninspectable (no parameters accessible)",
        ]))

    _dist_count = _distribution.get("param_count", 0)
    _fp_dist = _distribution.get("param_dev_dtype_numel", {})
    _total_fp_numel = sum(_fp_dist.values())
    _bf16_cpu_numel = _fp_dist.get("cpu|torch.bfloat16", 0)
    _non_bf16 = {k: v for k, v in _fp_dist.items() if k != "cpu|torch.bfloat16"}
    _non_cpu = {k: v for k, v in _fp_dist.items()
                if not k.startswith("cpu|")}

    if _total_fp_numel == 0:
        raise RuntimeError(_full_msg([
            "zero floating-point parameters found (model state not inspected)",
            f"param_count={_dist_count}",
        ]))

    _checks: list[str] = []
    if _non_cpu:
        _checks.append(f"non-CPU devices: {dict(list(_non_cpu.items())[:10])}")
    if _non_bf16:
        _checks.append(f"non-BF16 floating params: {dict(list(_non_bf16.items())[:10])}")
    if _bf16_cpu_numel != _total_fp_numel:
        missing = _total_fp_numel - _bf16_cpu_numel
        _checks.append(
            f"bf16_numel={_bf16_cpu_numel}/{_total_fp_numel} "
            f"({missing} numel non-BF16 on CPU)"
        )

    if _checks:
        raise RuntimeError(_full_msg(_checks))


# ---------------------------------------------------------------------------
# Parameter distribution / validation helper
# ---------------------------------------------------------------------------


def inspect_and_validate_snapshot_params(
    model: Any,
    *,
    expected_dtype: Any = None,
    require_cpu: bool = True,
    context: str = "",
) -> dict[str, Any]:
    """Inspect ALL parameters of *model*, report distribution, and validate.

    Iterates every parameter in the model (not just the first), collecting
    device and dtype metadata across all parameters.  For floating-point
    parameters, also reports count/numel grouped by ``device|dtype``.

    Returns a dict with:
      - ``param_count``: total number of parameters.
      - ``total_param_numel``: total number of elements across all params.
      - ``param_dev_dtype_count``: ``{device|dtype: count}`` across all
        floating-point parameters.
      - ``param_dev_dtype_numel``: ``{device|dtype: numel}`` across all
        floating-point parameters.
      - ``param_distribution_hash``: SHA-256 of sorted ``(device, dtype,
        numel)`` tuples for deterministic change detection.

    Raises ``RuntimeError`` when:
      - *require_cpu* is True and any parameter's device type is not ``cpu``.
      - *expected_dtype* is not None and any floating-point parameter has a
        different dtype (stale-FP32 snapshot detection).

    This helper uses ``model.parameters()`` which returns ALL parameters
    including those nested in submodules.  It never mutates the model or
    calls CUDA synchronisation.
    """
    import hashlib
    _param_count = 0
    _total_param_numel = 0
    _fp_dev_dtype_count: dict[str, int] = {}
    _fp_dev_dtype_numel: dict[str, int] = {}
    _param_tuples: list[tuple[str, str, int]] = []
    _any_non_cpu: list[str] = []
    _total_fp = 0
    _fp_of_expected_dtype = 0

    try:
        for _p in model.parameters():
            _param_count += 1
            _numel = _p.numel()
            _total_param_numel += _numel
            _dev_str = str(_p.device)
            _dtype_str = str(_p.dtype)
            if _p.is_floating_point():
                _key = f"{_dev_str}|{_dtype_str}"
                _fp_dev_dtype_count[_key] = _fp_dev_dtype_count.get(_key, 0) + 1
                _fp_dev_dtype_numel[_key] = _fp_dev_dtype_numel.get(_key, 0) + _numel
                _param_tuples.append((_dev_str, _dtype_str, _numel))
                _total_fp += _numel
                if expected_dtype is not None and _p.dtype == expected_dtype:
                    _fp_of_expected_dtype += _numel
            if require_cpu:
                _dev_type = _dev_str.strip().lower().split(":")[0]
                if _dev_type != "cpu":
                    _any_non_cpu.append(_dev_str)
    except Exception as exc:
        raise RuntimeError(f"{context}parameter inspection failed: {exc}") from exc

    _param_tuples.sort(key=lambda _x: (_x[0], _x[1], _x[2]))
    _param_h = hashlib.sha256()
    for _dev, _dt, _n in _param_tuples:
        _param_h.update(f"{_dev}|{_dt}|{_n}\n".encode())

    result: dict[str, Any] = {
        "param_count": _param_count,
        "total_param_numel": _total_param_numel,
        "param_dev_dtype_count": dict(_fp_dev_dtype_count),
        "param_dev_dtype_numel": dict(_fp_dev_dtype_numel),
        "param_distribution_hash": _param_h.hexdigest(),
    }

    if _any_non_cpu:
        raise RuntimeError(
            f"{context}non-CPU parameters found: {_any_non_cpu[:5]}... "
            f"({len(_any_non_cpu)} total)"
        )

    if expected_dtype is not None and _total_fp > 0 and _fp_of_expected_dtype != _total_fp:
        raise RuntimeError(
            f"{context}floating-point parameter dtype mismatch: "
            f"expected {expected_dtype}, matching_numel={_fp_of_expected_dtype}, "
            f"total_floating_numel={_total_fp}. "
            f"Distribution: {dict(_fp_dev_dtype_count)}"
        )

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


# ── Object-ID keys excluded from semantic diff ─────────────────────────

_OBJECT_ID_KEYS: frozenset[str] = frozenset({
    "patcher_object_id",
    "model_object_id",
    "diffusion_model_object_id",
})

# ---------------------------------------------------------------------------
# UNET runtime-state collector, differ, and rehydration helper
# ---------------------------------------------------------------------------


def _first_tensor_info(iterator_fn: Callable[..., Any]) -> tuple[str, str]:
    """Inspect exactly the first item from *iterator_fn(recurse=True)*.

    Uses ``next(iter(...), None)`` — never calls ``list()``, never inspects
    a second tensor.  Returns ``(device_str, dtype_str)`` or
    ``("absent", "absent")`` on any failure.
    """
    try:
        it = iterator_fn(recurse=True)
        if it is None:
            return ("absent", "absent")
        entry = next(iter(it), None)
        if entry is None:
            return ("absent", "absent")
        if isinstance(entry, tuple) and len(entry) == 2:
            _name, tensor = entry
        else:
            tensor = entry
        _dev = str(getattr(tensor, "device", "absent"))
        _dtype = str(getattr(tensor, "dtype", "absent"))
        return (_dev, _dtype)
    except Exception:
        return ("absent", "absent")


def _safe_str(val: Any) -> str:
    """Return ``str(val)`` when *val* is not callable and not ``None``.

    Returns ``"absent"`` for callable objects, ``None``, or any exception.
    """
    if val is None:
        return "absent"
    if callable(val):
        return "absent"
    try:
        return str(val)
    except Exception:
        return "absent"


def _safe_str_of_attr(obj: Any, attr: str) -> str:
    """Safely stringify *getattr(obj, attr, None)*.

    Returns ``"absent"`` when the attribute is missing, callable, or
    cannot be converted to string.
    """
    val = getattr(obj, attr, None)
    return _safe_str(val)


def collect_unet_runtime_state(
    unet: Any,
    *,
    model_management: Any = None,
) -> dict[str, Any]:
    """Capture the current runtime state of a ComfyUI ModelPatcher for UNET.

    Returns a flat dict with the fields specified in the comfymodal
    runtime-state comparison protocol.  Inspects at most one parameter
    and one buffer (``next(iter(...))`` — never ``list()``).  No mutation,
    no CUDA synchronisation, no tensor content.

    For a real ``comfy.model_patcher.ModelPatcher``:

    * ``model_dtype`` is a **method** — called safely.
    * ``manual_cast_dtype`` / ``device`` / ``model_loaded_weight_memory`` /
      ``model_lowvram`` / ``lowvram_patch_counter`` live on ``.model``
      (patches a long-standing bug where the previous code read them
      from the wrong object).
    * ``transformer_options`` is nested under ``model_options``.
    * ``diffusion_model`` (on ``.model``) owns ``forward``.
    * ``loaded_models`` is a **function** call.
    """
    state: dict[str, Any] = {}

    _model = getattr(unet, "model", None)
    _dm = None
    if _model is not None:
        _dm = getattr(_model, "diffusion_model", None)
    elif hasattr(unet, "diffusion_model"):
        _dm = getattr(unet, "diffusion_model", None)

    _MISSING = object()

    # ── Type identities ───────────────────────────────────────────────
    state["patcher_type"] = type(unet).__qualname__ if not isinstance(unet, (int, float, bool, str, bytes)) else type(unet).__name__
    state["model_type"] = type(_model).__qualname__ if _model is not None else "absent"
    state["diffusion_model_type"] = type(_dm).__qualname__ if _dm is not None else "absent"

    # ── Object identities (included in raw records, excluded from diff) ─
    state["patcher_object_id"] = str(id(unet))
    state["model_object_id"] = str(id(_model)) if _model is not None else "absent"
    state["diffusion_model_object_id"] = str(id(_dm)) if _dm is not None else "absent"

    # ── Device attributes (on patcher) ────────────────────────────────
    state["load_device"] = _safe_str_of_attr(unet, "load_device")
    state["offload_device"] = _safe_str_of_attr(unet, "offload_device")

    # ── current_device = model.device (not from first parameter) ───────
    state["current_device"] = _safe_str(getattr(_model, "device", None)) if _model is not None else "absent"

    # ── First parameter / first buffer (diffusion_model first, model fallback) ─
    _inspect_module = _dm if _dm is not None else _model
    if _inspect_module is not None:
        _fp_dev, _fp_dtype = _first_tensor_info(_inspect_module.named_parameters)
        _fb_dev, _fb_dtype = _first_tensor_info(_inspect_module.named_buffers)
    else:
        _fp_dev, _fp_dtype = ("absent", "absent")
        _fb_dev, _fb_dtype = ("absent", "absent")
    state["first_parameter_device"] = _fp_dev
    state["first_parameter_dtype"] = _fp_dtype
    state["first_buffer_device"] = _fb_dev
    state["first_buffer_dtype"] = _fb_dtype

    # ── Model dtype fields ────────────────────────────────────────────
    # model_dtype is a method on the patcher; call it safely.
    _md_fn = getattr(unet, "model_dtype", None)
    if callable(_md_fn):
        try:
            state["model_dtype"] = str(_md_fn())
        except Exception:
            state["model_dtype"] = "absent"
    else:
        state["model_dtype"] = "absent"

    state["manual_cast_dtype"] = _safe_str_of_attr(_model, "manual_cast_dtype") if _model is not None else "absent"
    state["weight_dtype"] = _safe_str_of_attr(unet, "weight_dtype")

    # ── Options ───────────────────────────────────────────────────────
    _mo = getattr(unet, "model_options", _MISSING)
    if _mo is _MISSING:
        state["model_options_keys"] = "absent"
    elif isinstance(_mo, dict):
        state["model_options_keys"] = sorted(str(k) for k in _mo.keys())
    else:
        state["model_options_keys"] = "absent"
    # transformer_options is nested under model_options
    if isinstance(_mo, dict):
        _to = _mo.get("transformer_options", _MISSING)
        if isinstance(_to, dict):
            state["transformer_options_keys"] = sorted(str(k) for k in _to.keys())
        else:
            state["transformer_options_keys"] = "absent"
    else:
        state["transformer_options_keys"] = "absent"

    # ── Patch counters ────────────────────────────────────────────────
    _patches = getattr(unet, "patches", _MISSING)
    if _patches is _MISSING:
        state["patch_count"] = "absent"
    elif isinstance(_patches, dict):
        state["patch_count"] = len(_patches)
    else:
        state["patch_count"] = "absent"
    _obj_patches = getattr(unet, "object_patches", _MISSING)
    if _obj_patches is _MISSING:
        state["object_patch_count"] = "absent"
    elif isinstance(_obj_patches, dict):
        state["object_patch_count"] = len(_obj_patches)
    else:
        state["object_patch_count"] = "absent"

    # ── Model-level memory / lowvram (on .model) ──────────────────────
    state["model_loaded_weight_memory"] = _safe_str_of_attr(_model, "model_loaded_weight_memory") if _model is not None else "absent"
    state["model_lowvram"] = _safe_str_of_attr(_model, "model_lowvram") if _model is not None else "absent"
    state["model_lowvram_patch_counter"] = _safe_str_of_attr(_model, "lowvram_patch_counter") if _model is not None else "absent"

    # ── Forward function (from diffusion_model, not patcher) ──────────
    if _dm is not None:
        _forward = getattr(_dm, "forward", None)
    else:
        _forward = getattr(_model, "forward", None) if _model is not None else None
    if _forward is not None:
        _self = getattr(_forward, "__self__", None)
        state["forward_module"] = type(_self).__qualname__ if _self is not None else "absent"
        state["forward_qualname"] = str(getattr(_forward, "__qualname__", "absent"))
    else:
        state["forward_module"] = "absent"
        state["forward_qualname"] = "absent"

    # ── loaded_models membership (function call) ──────────────────────
    _loaded = "absent"
    if model_management is not None:
        try:
            _lm_fn = getattr(model_management, "loaded_models", None)
            if callable(_lm_fn):
                _lm = _lm_fn()
                if isinstance(_lm, (list, tuple)):
                    _present = any(_item is unet for _item in _lm)
                    _loaded = str(int(_present))
                else:
                    _loaded = "absent"
            else:
                _loaded = "absent"
        except Exception:
            _loaded = "absent"
    state["loaded_models_member"] = _loaded

    return state


def diff_unet_runtime_states(
    snapshot_state: dict[str, Any],
    normal_state: dict[str, Any],
) -> dict[str, Any]:
    """Return only semantically meaningful differing fields.

    **Excludes** machine-local object IDs (``patcher_object_id``,
    ``model_object_id``, ``diffusion_model_object_id``) that are
    never meaningful across processes.

    Keys present in both dicts whose string values differ are included.
    Keys present in only one dict are included with their value from the
    dict that has them.  Returns an empty dict when states are identical.
    """
    diff: dict[str, Any] = {}
    all_keys = set(snapshot_state.keys()) | set(normal_state.keys())
    for key in sorted(all_keys):
        if key in _OBJECT_ID_KEYS:
            continue
        sv = snapshot_state.get(key, "<missing>")
        nv = normal_state.get(key, "<missing>")
        if str(sv) != str(nv):
            diff[key] = {"snapshot": sv, "normal": nv}
    return diff


def collect_unet_forward_probe_state(
    unet: Any,
    *,
    diffusion_model: Any = None,
) -> dict[str, Any]:
    """Collect read-only diagnostic state from a UNET patcher and its
    diffusion model **immediately before** ``NextDiT.forward`` is called.

    The caller has already called ``load_models_gpu``.  This helper
    records identity, model-state fields, parameter/buffer distribution,
    forward-callable structure, and collector timing.

    **Safety (enforced by caller convention — never guaranteed at
    runtime)**: this function never calls ``.cpu()``, ``.cuda()``,
    ``.to()``, ``.item()``, ``.clone()``, ``.numpy()``,
    ``torch.cuda.synchronize()``, or ``load_models_gpu()``.  It never
    mutates models or tensors.

    Parameters
    ----------
    unet
        A ComfyUI ``ModelPatcher`` (or duck-typed equivalent) for a UNET.
    diffusion_model
        Optional explicit reference to the diffusion model (the
        ``torch.nn.Module`` that owns ``forward``).  When omitted the
        collector resolves it as ``unet.model.diffusion_model`` (then
        ``unet.diffusion_model`` as fallback).

    Returns
    -------
    dict[str, Any]
        Flat dictionary of probe fields (see module doctest or
        ``collect_unet_forward_probe_state`` tests for the full
        field list).
    """
    import hashlib
    import time

    _start_ns = time.monotonic_ns()

    state: dict[str, Any] = {}

    # ── Resolve diffusion_model ──────────────────────────────────────
    _model = getattr(unet, "model", None)
    _dm: Any = diffusion_model
    if _dm is None:
        if _model is not None:
            _dm = getattr(_model, "diffusion_model", None)
        if _dm is None:
            _dm = getattr(unet, "diffusion_model", None)

    # ── 1. Identity ──────────────────────────────────────────────────
    state["patcher_object_id"] = str(id(unet))
    state["patcher_type"] = type(unet).__qualname__

    state["model_object_id"] = str(id(_model)) if _model is not None else "absent"
    state["model_type"] = type(_model).__qualname__ if _model is not None else "absent"

    state["diffusion_model_object_id"] = str(id(_dm)) if _dm is not None else "absent"
    state["diffusion_model_type"] = type(_dm).__qualname__ if _dm is not None else "absent"

    # ── 2. Model state ───────────────────────────────────────────────
    state["load_device"] = _safe_str_of_attr(unet, "load_device")
    state["offload_device"] = _safe_str_of_attr(unet, "offload_device")

    _model_device = getattr(_model, "device", None) if _model is not None else None
    state["model_device"] = _safe_str(_model_device)

    # model_dtype() — callable method on patcher
    _md_fn = getattr(unet, "model_dtype", None)
    if callable(_md_fn):
        try:
            state["model_dtype"] = str(_md_fn())
        except Exception:
            state["model_dtype"] = "absent"
    else:
        state["model_dtype"] = "absent"

    state["manual_cast_dtype"] = (
        _safe_str_of_attr(_model, "manual_cast_dtype") if _model is not None else "absent"
    )
    state["model_loaded_weight_memory"] = (
        _safe_str_of_attr(_model, "model_loaded_weight_memory") if _model is not None else "absent"
    )
    state["model_lowvram"] = (
        _safe_str_of_attr(_model, "model_lowvram") if _model is not None else "absent"
    )
    state["lowvram_patch_counter"] = (
        _safe_str_of_attr(_model, "lowvram_patch_counter") if _model is not None else "absent"
    )

    # ── 3. Parameter distribution ────────────────────────────────────
    _param_count = 0
    _total_param_numel = 0
    _param_dev_dtype_count: dict[str, int] = {}
    _param_dev_dtype_numel: dict[str, int] = {}
    _param_tuples: list[tuple[str, str, int]] = []

    if _dm is not None:
        try:
            for _p in _dm.parameters():
                _param_count += 1
                _numel = _p.numel()
                _total_param_numel += _numel
                _key = f"{_p.device}|{_p.dtype}"
                _param_dev_dtype_count[_key] = _param_dev_dtype_count.get(_key, 0) + 1
                _param_dev_dtype_numel[_key] = _param_dev_dtype_numel.get(_key, 0) + _numel
                _param_tuples.append((str(_p.device), str(_p.dtype), _numel))
        except Exception:
            pass

    _param_tuples.sort(key=lambda _x: (_x[0], _x[1], _x[2]))
    _param_h = hashlib.sha256()
    for _dev, _dt, _n in _param_tuples:
        _param_h.update(f"{_dev}|{_dt}|{_n}\n".encode())

    state["param_count"] = _param_count
    state["total_param_numel"] = _total_param_numel
    state["param_dev_dtype_count"] = dict(_param_dev_dtype_count)
    state["param_dev_dtype_numel"] = dict(_param_dev_dtype_numel)
    state["param_distribution_hash"] = _param_h.hexdigest()

    # ── 4. Buffer distribution ───────────────────────────────────────
    _buffer_count = 0
    _total_buffer_numel = 0
    _buf_dev_dtype_count: dict[str, int] = {}
    _buf_dev_dtype_numel: dict[str, int] = {}
    _buf_tuples: list[tuple[str, str, int]] = []

    if _dm is not None:
        try:
            for _b in _dm.buffers():
                _buffer_count += 1
                _numel = _b.numel()
                _total_buffer_numel += _numel
                _key = f"{_b.device}|{_b.dtype}"
                _buf_dev_dtype_count[_key] = _buf_dev_dtype_count.get(_key, 0) + 1
                _buf_dev_dtype_numel[_key] = _buf_dev_dtype_numel.get(_key, 0) + _numel
                _buf_tuples.append((str(_b.device), str(_b.dtype), _numel))
        except Exception:
            pass

    _buf_tuples.sort(key=lambda _x: (_x[0], _x[1], _x[2]))
    _buf_h = hashlib.sha256()
    for _dev, _dt, _n in _buf_tuples:
        _buf_h.update(f"{_dev}|{_dt}|{_n}\n".encode())

    state["buffer_count"] = _buffer_count
    state["total_buffer_numel"] = _total_buffer_numel
    state["buffer_dev_dtype_count"] = dict(_buf_dev_dtype_count)
    state["buffer_dev_dtype_numel"] = dict(_buf_dev_dtype_numel)
    state["buffer_distribution_hash"] = _buf_h.hexdigest()

    # ── 5. Forward callable structure ────────────────────────────────
    _forward_fn = getattr(_dm, "forward", None) if _dm is not None else None
    if _forward_fn is not None:
        _self = getattr(_forward_fn, "__self__", None)
        state["forward_module"] = type(_self).__qualname__ if _self is not None else "absent"
        state["forward_qualname"] = str(getattr(_forward_fn, "__qualname__", "absent"))

        # Wrapper chain via __wrapped__ (max depth 8)
        _wrapper_chain: list[str] = []
        _seen: set[int] = set()
        _fn = _forward_fn
        for _ in range(8):
            _wrapped = getattr(_fn, "__wrapped__", None)
            if _wrapped is None:
                break
            _wrapped_id = id(_wrapped)
            if _wrapped_id in _seen:
                break
            _seen.add(_wrapped_id)
            _wq = str(getattr(_wrapped, "__qualname__", ""))
            _wrapper_chain.append(_wq)
            _fn = _wrapped

        _wc_h = hashlib.sha256()
        for _entry in _wrapper_chain:
            _wc_h.update(f"{_entry}\n".encode())

        state["wrapper_chain"] = list(_wrapper_chain)
        state["wrapper_chain_hash"] = _wc_h.hexdigest()
    else:
        state["forward_module"] = "absent"
        state["forward_qualname"] = "absent"
        state["wrapper_chain"] = []
        state["wrapper_chain_hash"] = hashlib.sha256().hexdigest()

    # ── 6. Collector metadata ────────────────────────────────────────
    _elapsed_ms = round((time.monotonic_ns() - _start_ns) / 1_000_000, 3)
    state["collector_duration_ms"] = _elapsed_ms

    return state


def rehydrate_cpu_snapshot_unet(
    unet: Any,
    *,
    model_management: Any,
    trace: Any = None,
) -> tuple[bool, str]:
    """Validate and re-target device attributes of a CPU-snapshot UNET.

    For this patch the helper must only:

    1. Validate that *unet* has ``.model``, ``.load_device``, and
       ``.offload_device`` attributes.
    2. Assign ``model_management.get_torch_device()`` to
       ``unet.load_device`` and ``model_management.unet_offload_device()``
       to ``unet.offload_device``.
    3. Emit pre/post runtime state when *trace* is provided.

    Returns ``(True, "ok")`` or ``(False, reason_string)``.

    Does **not** modify ``current_device``, change dtype/manual-cast
    fields, clear CacheDiT, call ``load_models_gpu``, reconstruct or
    reload the UNET, or copy state from another object.
    """
    # ── Pre-state ─────────────────────────────────────────────────────
    _pre_state = collect_unet_runtime_state(unet, model_management=model_management)

    # ── Validate shape ────────────────────────────────────────────────
    if not hasattr(unet, "model"):
        return False, "unet missing .model attribute"
    if not hasattr(unet, "load_device"):
        return False, "unet missing .load_device attribute"
    if not hasattr(unet, "offload_device"):
        return False, "unet missing .offload_device attribute"

    # ── Validate required model_management functions ──────────────────
    _gt = getattr(model_management, "get_torch_device", None)
    _uo = getattr(model_management, "unet_offload_device", None)
    if not callable(_gt):
        return False, "model_management.get_torch_device is not callable"
    if not callable(_uo):
        return False, "model_management.unet_offload_device is not callable"

    # ── Assign devices ────────────────────────────────────────────────
    try:
        unet.load_device = _gt()
        unet.offload_device = _uo()
    except Exception as exc:
        return False, f"device assignment failed: {exc}"

    # ── Post-state ────────────────────────────────────────────────────
    _post_state = collect_unet_runtime_state(unet, model_management=model_management)

    # Emit pre/post trace when available
    if trace is not None:
        try:
            _pre_state_safe = {k: str(v) for k, v in _pre_state.items()}
            _post_state_safe = {k: str(v) for k, v in _post_state.items()}
            _diff = diff_unet_runtime_states(_pre_state, _post_state)
            trace.emit(
                "unet_rehydrate_pre_state",
                metadata={"state": _pre_state_safe},
            )
            trace.emit(
                "unet_rehydrate_post_state",
                metadata={"state": _post_state_safe},
            )
            if _diff:
                _diff_safe = {
                    k: {"snapshot": str(v.get("snapshot", "")), "normal": str(v.get("normal", ""))}
                    for k, v in _diff.items()
                }
                trace.emit(
                    "unet_rehydrate_diff",
                    metadata={"diff": _diff_safe, "changed_fields": sorted(_diff.keys())},
                )
        except Exception:
            pass

    return True, "ok"


def identity_from_profile(
    profile: Mapping[str, Any],
    *,
    resolve_path: Callable[[str, str], str],
) -> tuple[ModelRestoreKey, dict[str, Any], tuple[ModelFileFact, ...]]:
    """Build a ModelRestoreKey, model_spec, and file facts from a warmup profile.

    NOTE: compute policy identity is NOT included in model_spec; it is
    stored separately on CpuSnapshotModels.compute_policy.

    Returns
    -------
    (ModelRestoreKey, model_spec_dict, file_facts_tuple)

    Raises
    ------
    ValueError
        When the profile is missing required fields, has an unsupported
        mode, or contains malformed configuration.
    """
    if not isinstance(profile, Mapping):
        raise ValueError("profile must be a Mapping")

    raw = dict(profile)
    mode_value = raw.get("mode", "")
    if not isinstance(mode_value, str) or not mode_value.strip():
        raise ValueError("profile mode is required and must be a non-empty string")
    mode = mode_value.strip()
    if mode != "split":
        raise ValueError(f"unsupported profile mode: {mode!r}; only 'split' is supported")

    def required_text(key: str) -> str:
        value = raw.get(key, "")
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"profile {key} is required and must be a non-empty string")
        return value.strip()

    unet = required_text("unet")
    clip1 = required_text("clip1")
    clip_type = required_text("clip_type")
    clip2 = raw.get("clip2", "")
    if clip2 is not None and not isinstance(clip2, str):
        raise ValueError("profile clip2 must be a string when provided")

    normalized = _normalize_profile(profile)
    model_key = _build_model_key(normalized)
    model_spec = _build_model_spec(normalized)

    # Stat files in deterministic role order: unet, clip1, clip2 (only when unique)
    facts: list[ModelFileFact] = [
        _stat_file("unet", normalized["unet"], resolve_path=resolve_path),
        _stat_file("clip1", normalized["clip1"], resolve_path=resolve_path),
    ]
    if normalized.get("clip2") and normalized["clip2"] != normalized["clip1"]:
        facts.append(_stat_file("clip2", normalized["clip2"], resolve_path=resolve_path))

    return (model_key, model_spec, tuple(facts))


def load_cpu_snapshot_models(
    profile: Mapping[str, Any],
    *,
    load_unet: Callable[..., Any],
    load_clip: Callable[..., Any],
    resolve_path: Callable[[str, str], str],
    trace: RuntimeTrace | None = None,
    target_gpus: tuple[str, ...] | None = None,
) -> CpuSnapshotModels:
    """Load CLIP and UNET from the given profile and return a validated snapshot.

    When *target_gpus* is provided (snapshot construction path), the
    returned ``CpuSnapshotModels`` carries a ``compute_policy`` attribute
    that distinguishes the compute/manual-cast policy so stale snapshots
    built with a different policy cannot match.  The model_spec does NOT
    contain compute_policy — matching uses the separate field.

    Load order: CLIP -> gc.collect -> UNET -> gc.collect.
    All loading happens under torch.no_grad().

    Callback invocation shapes:
      load_clip(name, type, device)           -- single CLIP
      load_clip(name1, name2, type, device)   -- dual CLIP
      load_unet(name, weight_dtype)            -- UNET
    """
    import torch

    start_ns = time.monotonic_ns()
    model_key_hash = ""
    normalized: dict[str, Any] = {}
    clip_obj: Any = None
    unet_obj: Any = None
    timings: dict[str, float] = {}
    active_object_type = ""
    active_basename = ""

    try:
        normalized = _normalize_profile(profile) if isinstance(profile, Mapping) else {}
        model_key, model_spec, facts = identity_from_profile(
            profile, resolve_path=resolve_path,
        )
        model_key_hash = model_key.stable_hash[:16]

        # --- CLIP load ---
        active_object_type = ""
        active_basename = os.path.basename(normalized["clip1"])
        if trace:
            trace.emit(
                "cpu_snapshot_clip_load_start",
                phase="restore",
                metadata={
                    "model_key_hash": model_key_hash,
                    "basename": active_basename,
                },
            )
        clip_start = time.monotonic_ns()
        with torch.no_grad():
            if normalized.get("clip2"):
                clip_obj = load_clip(
                    normalized["clip1"],
                    normalized["clip2"],
                    normalized.get("clip_type", "stable_diffusion"),
                    "default",
                )
            else:
                clip_obj = load_clip(
                    normalized["clip1"],
                    normalized.get("clip_type", "stable_diffusion"),
                    "default",
                )
        clip_end = time.monotonic_ns()
        clip_ms = round((clip_end - clip_start) / 1_000_000, 2)
        timings["clip_load_ms"] = clip_ms
        if trace:
            trace.emit(
                "cpu_snapshot_clip_load_end",
                phase="restore",
                metadata={
                    "model_key_hash": model_key_hash,
                    "object_type": type(clip_obj).__name__,
                    "basename": active_basename,
                    "duration_ms": clip_ms,
                },
            )

        gc.collect()

        # --- UNET load ---
        active_basename = os.path.basename(normalized["unet"])
        if trace:
            trace.emit(
                "cpu_snapshot_unet_load_start",
                phase="restore",
                metadata={
                    "model_key_hash": model_key_hash,
                    "basename": active_basename,
                },
            )
        unet_start = time.monotonic_ns()
        with torch.no_grad():
            unet_obj = load_unet(
                normalized["unet"],
                normalized.get("weight_dtype", "default"),
            )
        unet_end = time.monotonic_ns()
        unet_ms = round((unet_end - unet_start) / 1_000_000, 2)
        timings["unet_load_ms"] = unet_ms
        if trace:
            trace.emit(
                "cpu_snapshot_unet_load_end",
                phase="restore",
                metadata={
                    "model_key_hash": model_key_hash,
                    "object_type": type(unet_obj).__name__,
                    "basename": active_basename,
                    "duration_ms": unet_ms,
                },
            )

        gc.collect()

        # Derive compute policy from target_gpus (snapshot identity)
        _cp = _COMPUTE_POLICY_DEFAULT
        if target_gpus:
            _wd = normalized.get("weight_dtype", "default")
            _cp = _resolve_compute_policy(_wd, target_gpus=target_gpus)

        models = CpuSnapshotModels(
            model_key=model_key,
            model_spec=model_spec,
            normalized_profile=normalized,
            file_facts=facts,
            unet=unet_obj,
            clip=clip_obj,
            load_timings_ms=timings,
            compute_policy=_cp,
            policy_version=CPU_SNAPSHOT_UNET_POLICY_VERSION,
            target_gpus=target_gpus or (),
        )

        ok, reason = validate_cpu_snapshot_models(
            models,
            expected_key=model_key,
            expected_spec=model_spec,
            resolve_path=resolve_path,
        )
        if not ok:
            raise RuntimeError(f"snapshot validation failed: {reason}")

        total_ms = round((time.monotonic_ns() - start_ns) / 1_000_000, 2)
        if trace:
            trace.emit(
                "cpu_snapshot_models_ready",
                phase="restore",
                metadata={
                    "model_key_hash": model_key_hash,
                    "object_type": type(models).__name__,
                    "basename": active_basename,
                    "status": "ok",
                    "duration_ms": total_ms,
                },
            )

        return models

    except BaseException as exc:
        elapsed_ms = round((time.monotonic_ns() - start_ns) / 1_000_000, 2)
        if trace:
            obj_type = type(unet_obj).__name__ if unet_obj is not None else (
                type(clip_obj).__name__ if clip_obj is not None else active_object_type
            )
            trace.emit(
                "cpu_snapshot_models_failed",
                phase="restore",
                metadata={
                    "duration_ms": elapsed_ms,
                    "model_key_hash": model_key_hash,
                    "object_type": obj_type,
                    "basename": active_basename,
                    "status": "error",
                    "reason": str(exc),
                },
            )
        raise


def validate_cpu_snapshot_models(
    models: CpuSnapshotModels,
    *,
    expected_key: ModelRestoreKey,
    expected_spec: Mapping[str, Any],
    resolve_path: Callable[[str, str], str],
) -> tuple[bool, str]:
    """Validate a loaded CpuSnapshotModels struct.

    Compares all model_key fields, verifies model_spec structurally,
    confirms split-mode in normalized_profile, re-resolves and re-stats
    each file fact, and validates UNET/CLIP object shape and tensor safety.

    Returns (True, 'ok') on success or (False, reason_string) on failure.
    """
    # Identity check — all fields
    if models.model_key != expected_key:
        for field_name in (
            "unet_identity",
            "clip_identity",
            "vae_identity",
            "clip_type",
            "loader_configuration",
            "model_volume_generation",
            "optimization_loader_options",
        ):
            actual = getattr(models.model_key, field_name)
            expected = getattr(expected_key, field_name)
            if actual != expected:
                label = field_name.replace("_", " ")
                return (False, f"{label} mismatch: {actual!r} != {expected!r}")
        return (False, "model_key mismatch")

    # Model spec structural check
    if models.model_spec != dict(expected_spec):
        return (False, "model_spec mismatch")

    # Normalized profile check
    norm = models.normalized_profile
    if not isinstance(norm, Mapping):
        return (False, "normalized_profile is not a mapping")
    if norm.get("mode") != "split":
        return (False, f"normalized_profile mode is not 'split': {norm.get('mode')!r}")
    for field_name in ("unet", "clip1", "clip_type"):
        value = norm.get(field_name)
        if not isinstance(value, str) or not value.strip():
            return (False, f"normalized_profile {field_name} is not a non-empty string")
    from .restore_plan import _build_dual_clip_identity

    clip2 = norm.get("clip2", "")
    if clip2 is None:
        clip2 = ""
    if not isinstance(clip2, str):
        return (False, "normalized_profile clip2 is not a string")
    if clip2:
        normalized_clip_identity = _build_dual_clip_identity(norm["clip1"], clip2)
    else:
        normalized_clip_identity = norm["clip1"]
    if models.model_key.unet_identity != norm["unet"]:
        return (False, "normalized_profile unet does not match model_key")
    if models.model_key.clip_identity != normalized_clip_identity:
        return (False, "normalized_profile clips do not match model_key")

    # Verify exact single/dual loader structure when clip loaders are present.
    clip_loaders = models.model_spec.get("loaders", {}).get("clip", [])
    if clip_loaders:
        first = clip_loaders[0]
        if clip2:
            if first.get("loader_class") != "DualCLIPLoader":
                return (False, "model_spec should use DualCLIPLoader when clip2 supplied")
            if first.get("clip_name1") != norm["clip1"]:
                return (False, "model_spec clip_name1 mismatch")
            if first.get("clip_name2") != norm["clip2"]:
                return (False, "model_spec clip_name2 mismatch")
            if first.get("type") != norm.get("clip_type", ""):
                return (False, "model_spec clip type mismatch")
            if first.get("device") != "default":
                return (False, "model_spec clip device should be 'default'")
        else:
            if first.get("loader_class") != "CLIPLoader":
                return (False, "model_spec should use CLIPLoader when no clip2 supplied")
            if first.get("clip_name") != norm["clip1"]:
                return (False, "model_spec clip_name mismatch")

    # Unique file facts: only include clip2 when different from clip1
    if clip2 and clip2 != norm.get("clip1"):
        expected_roles = ("unet", "clip1", "clip2")
    else:
        expected_roles = ("unet", "clip1")
    actual_roles = tuple(fact.role for fact in models.file_facts)
    if actual_roles != expected_roles:
        return (False, f"file fact roles mismatch: {actual_roles!r} != {expected_roles!r}")

    # Re-resolve and re-stat each file fact
    for fact in models.file_facts:
        role = fact.role
        if role == "unet":
            filename = norm.get("unet")
        elif role == "clip1":
            filename = norm.get("clip1")
        elif role == "clip2":
            filename = norm.get("clip2")
        else:
            continue

        if not filename:
            return (False, f"role {role} has no filename in normalized_profile")

        try:
            current_path = resolve_path(role, filename)
        except Exception as e:
            return (False, f"resolve_path failed for {role}:{filename}: {e}")

        if not os.path.exists(current_path):
            return (False, f"resolved path does not exist: {current_path}")

        try:
            st = os.stat(current_path)
        except OSError as e:
            return (False, f"cannot stat {current_path}: {e}")

        if current_path != fact.path:
            return (False, f"resolved path mismatch for {role}: {current_path} != {fact.path}")

        if st.st_size != fact.size_bytes:
            return (False, f"file size mismatch for {role}: stored {fact.size_bytes} != current {st.st_size}")

        current_mtime = int(st.st_mtime_ns if hasattr(st, "st_mtime_ns") else st.st_mtime * 1_000_000_000)
        if fact.mtime_ns != 0 and current_mtime != 0 and fact.mtime_ns != current_mtime:
            return (False, f"file mtime mismatch for {role}")

    # Object non-None check
    if models.unet is None:
        return (False, "unet is None")
    if models.clip is None:
        return (False, "clip is None")

    # Shape and tensor safety
    ok, reason = _is_valid_unet_patcher(models.unet)
    if not ok:
        return (False, reason)

    ok, reason = _is_valid_clip_patcher(models.clip)
    if not ok:
        return (False, reason)

    # Policy version/identity validation — reject legacy/stale snapshots
    if models.policy_version == 0:
        return (False, "policy_version is 0 (legacy/unset); current version is "
                f"{CPU_SNAPSHOT_UNET_POLICY_VERSION}")
    if models.policy_version != CPU_SNAPSHOT_UNET_POLICY_VERSION:
        return (False, f"policy_version mismatch: stored={models.policy_version} "
                f"current={CPU_SNAPSHOT_UNET_POLICY_VERSION}")
    # Verify policy identity is consistent with resolved policy metadata
    _wd = models.normalized_profile.get("weight_dtype", "default")
    _tg = models.target_gpus
    _resolved_cp = models.compute_policy
    if _tg:
        _resolved_cp = _resolve_compute_policy(_wd, target_gpus=_tg)
        if _resolved_cp != models.compute_policy:
            return (False, f"compute_policy mismatch: stored={models.compute_policy} "
                    f"resolved={_resolved_cp} from weight_dtype={_wd} target_gpus={_tg}")

    # BF16-native compute policy validation (from models.compute_policy)
    if models.compute_policy == _COMPUTE_POLICY_BF16_NATIVE:
        try:
            validate_snapshot_unet_bf16_native(
                models.unet,
                context="validate_cpu_snapshot_models.",
                target_gpus=_tg or None,
                requested_weight_dtype=_wd,
                effective_weight_dtype=_resolved_cp,
                effective_compute_dtype=_resolved_cp,
            )
        except RuntimeError as _exc:
            return (False, str(_exc))

    return (True, "ok")


def retarget_cpu_snapshot_models(
    models: CpuSnapshotModels,
    *,
    model_management: Any,
) -> tuple[bool, str]:
    """Retarget model device attributes using ComfyUI's model_management.

    Sets load_device/offload_device on UNET and CLIP patchers.
    Never transfers model weights or selects hardcoded devices.

    Returns (True, 'ok') or (False, reason).
    """
    # Validate all 4 required functions exist and are callable
    required_funcs = [
        "get_torch_device",
        "unet_offload_device",
        "text_encoder_device",
        "text_encoder_offload_device",
    ]
    for func_name in required_funcs:
        func = getattr(model_management, func_name, None)
        if not callable(func):
            return (False, f"missing_model_management_function:{func_name}")

    # Pre-check all shapes before making any assignments
    ok_unet, _ = _is_valid_unet_patcher(models.unet)
    if not ok_unet:
        return (False, "unsupported_unet_shape")

    ok_clip, _ = _is_valid_clip_patcher(models.clip)
    if not ok_clip:
        return (False, "unsupported_clip_shape")

    # Verify patcher fields exist for assignment
    if not hasattr(models.unet, "load_device") or not hasattr(models.unet, "offload_device"):
        return (False, "unsupported_unet_shape")

    clip_patcher = getattr(models.clip, "patcher", None)
    if clip_patcher is None:
        return (False, "unsupported_clip_shape")
    if not hasattr(clip_patcher, "load_device") or not hasattr(clip_patcher, "offload_device"):
        return (False, "unsupported_clip_shape")

    # All checks passed - make device-policy assignments only.
    # UNET: delegate to rehydrate_cpu_snapshot_unet for instrumentation.
    ok_rehydrate, reason_rehydrate = rehydrate_cpu_snapshot_unet(
        models.unet, model_management=model_management,
    )
    if not ok_rehydrate:
        return (False, f"unet_rehydration_failed:{reason_rehydrate}")

    clip_patcher.load_device = model_management.text_encoder_device()
    clip_patcher.offload_device = model_management.text_encoder_offload_device()

    return (True, "ok")
