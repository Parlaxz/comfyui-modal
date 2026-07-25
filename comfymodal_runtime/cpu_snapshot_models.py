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
