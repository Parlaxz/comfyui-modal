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


@dataclass
class CpuSnapshotModels:
    model_key: ModelRestoreKey
    model_spec: dict[str, Any]
    normalized_profile: dict[str, Any]
    file_facts: tuple[ModelFileFact, ...]
    unet: Any = None
    clip: Any = None
    load_timings_ms: dict[str, float] = field(default_factory=dict)


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
    if "weight_dtype" in stable:
        normalized["weight_dtype"] = stable["weight_dtype"]
    return normalized


def _build_model_key(normalized: dict[str, Any]) -> ModelRestoreKey:
    clip = normalized["clip1"]
    if normalized.get("clip2"):
        clip = f"{normalized['clip1']}||{normalized['clip2']}"
    return ModelRestoreKey(
        unet_identity=normalized["unet"],
        clip_identity=clip,
        vae_identity="",
        clip_type=normalized["clip_type"],
    )


def _build_model_spec(normalized: dict[str, Any]) -> dict[str, Any]:
    """Build loaders from the normalized profile.

    Matches restore_plan.py shape: weight_dtype always present
    in the UNET loader ("default" when absent from profile).
    No node IDs, prompt fields, or hashes.
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
# Public API
# ---------------------------------------------------------------------------


def identity_from_profile(
    profile: Mapping[str, Any],
    *,
    resolve_path: Callable[[str, str], str],
) -> tuple[ModelRestoreKey, dict[str, Any], tuple[ModelFileFact, ...]]:
    """Build a ModelRestoreKey, model_spec, and file facts from a warmup profile.

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

    # Stat files in deterministic role order: unet, clip1, clip2
    facts: list[ModelFileFact] = [
        _stat_file("unet", normalized["unet"], resolve_path=resolve_path),
        _stat_file("clip1", normalized["clip1"], resolve_path=resolve_path),
    ]
    if normalized.get("clip2"):
        facts.append(_stat_file("clip2", normalized["clip2"], resolve_path=resolve_path))

    return (model_key, model_spec, tuple(facts))


def load_cpu_snapshot_models(
    profile: Mapping[str, Any],
    *,
    load_unet: Callable[..., Any],
    load_clip: Callable[..., Any],
    resolve_path: Callable[[str, str], str],
    trace: RuntimeTrace | None = None,
) -> CpuSnapshotModels:
    """Load CLIP and UNET from the given profile and return a validated snapshot.

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

        models = CpuSnapshotModels(
            model_key=model_key,
            model_spec=model_spec,
            normalized_profile=normalized,
            file_facts=facts,
            unet=unet_obj,
            clip=clip_obj,
            load_timings_ms=timings,
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
    clip2 = norm.get("clip2", "")
    if clip2 is None:
        clip2 = ""
    if not isinstance(clip2, str):
        return (False, "normalized_profile clip2 is not a string")
    if clip2 == norm["clip1"] and clip2:
        return (False, "normalized_profile clip2 was not collapsed")
    normalized_clip_identity = norm["clip1"]
    if clip2:
        normalized_clip_identity = f"{normalized_clip_identity}||{clip2}"
    if models.model_key.unet_identity != norm["unet"]:
        return (False, "normalized_profile unet does not match model_key")
    if models.model_key.clip_identity != normalized_clip_identity:
        return (False, "normalized_profile clips do not match model_key")
    expected_roles = ("unet", "clip1") + (("clip2",) if clip2 else ())
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
    models.unet.load_device = model_management.get_torch_device()
    models.unet.offload_device = model_management.unet_offload_device()
    clip_patcher.load_device = model_management.text_encoder_device()
    clip_patcher.offload_device = model_management.text_encoder_offload_device()

    return (True, "ok")
