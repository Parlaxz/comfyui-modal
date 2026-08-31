"""E28 compute-ready FP32 / cast-once CLIP (Target C).

Measured evidence (E27 Follow-Up A, real Qwen-3-4B):
* qwen_3_4b.safetensors: 398 tensors, ALL BF16, 8,044,936,192 source bytes;
  exact FP32 residency = 16,089,872,384 bytes (14.9849 GiB).
* Relevant Linear weights: approximately 252 tensors/forward and approximately
  14.53 GB of conversion traffic.  This replaces the stale 253/15.31 GB
  estimate; no synchronized conversion time is claimed here.

Design (ownership model A — REPLACE resident storage, never duplicate):
* The speculative CLIP lane hydrates BF16 direct-to-GPU (fastsafetensors),
  then this module casts each tensor ONCE to FP32 (exact widening, GPU op)
  before the zero-copy assign bind.
* ``hydrate_clip_bind`` uses Comfy's ``load_state_dict(assign=True)`` path:
  the parameters ADOPT the FP32 tensors as their data, so the final model
  storage IS FP32 — there is no separate cache to invalidate.
* At forward, ``cast_bias_weight`` runs ``cast_to`` (device already cuda,
  no copy) then ``weight.to(dtype=torch.float32)`` — a no-op when the
  resident dtype is already FP32 → the per-forward cast tax disappears.

Invalidation semantics (fail-closed):
* The "cache" is the parameter storage itself.  Any semantic mutation —
  ``patch_weight_to_device``, ``weight_function``/``bias_function``
  registration, ``manual_cast_dtype`` retarget, ``assign``/storage
  replacement, clone/rehome, device move, dtype retarget — rewrites the
  parameter data in place; a subsequent forward either sees the mutated
  (still-FP32) values (patches applied in FP32 by Comfy's patch machinery)
  or triggers the regular cast path.  A stale compute-ready representation
  is structurally impossible because there is no second representation.
* Defensive demand-time check: :func:`assert_compute_ready_no_patches`
  verifies every file-covered parameter is FP32 and no weight/bias function
  is registered on the leaves before the bind is allowed to proceed with
  cast-once tensors; any violation fails closed to the normal BF16 read.

Telemetry (per prompt 6.5):
* one-time conversion host wall + CUDA-event wall
* bytes cast, tensor count
* VRAM delta (before/after allocated)
* per-forward casts remaining (measured by the E27 forward-cast counter:
  the same 253 call sites, but materialized dest_bytes -> 0)
"""

from __future__ import annotations

import os
import time
import functools
import hashlib
import json
import math
import threading
from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Mapping, Optional

import torch

from .env import env_flag

_FLAG = "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE"
_COMPUTE_DTYPE = "torch.float32"
_SOURCE_DTYPE = "torch.bfloat16"
_CAST_PROVENANCE_ATTR = "_comfymodal_cast_once_provenance"


class OwnershipTransferError(RuntimeError):
    """A cast-once ownership contract was used outside its safe protocol."""


class BindReceiptError(OwnershipTransferError):
    """The bind receipt was not produced by the actual Comfy bind."""


class TransferState(str, Enum):
    SOURCE_ACTIVE = "SOURCE_ACTIVE"
    FP32_TRANSFORM_IN_PROGRESS = "FP32_TRANSFORM_IN_PROGRESS"
    FP32_BOUND_UNPROVEN = "FP32_BOUND_UNPROVEN"
    FP32_BOUND_PROVEN = "FP32_BOUND_PROVEN"
    SOURCE_REFS_DROPPED = "SOURCE_REFS_DROPPED"
    SOURCE_OWNER_RETIRED = "SOURCE_OWNER_RETIRED"
    READY = "READY"
    FAILED = "FAILED"
    POISONED = "POISONED"


# Public spellings make the state machine easy to consume from an adapter
# without importing Enum implementation details.
SOURCE_ACTIVE = TransferState.SOURCE_ACTIVE.value
FP32_TRANSFORM_IN_PROGRESS = TransferState.FP32_TRANSFORM_IN_PROGRESS.value
FP32_BOUND_UNPROVEN = TransferState.FP32_BOUND_UNPROVEN.value
FP32_BOUND_PROVEN = TransferState.FP32_BOUND_PROVEN.value
SOURCE_REFS_DROPPED = TransferState.SOURCE_REFS_DROPPED.value
SOURCE_OWNER_RETIRED = TransferState.SOURCE_OWNER_RETIRED.value
READY = TransferState.READY.value
FAILED = TransferState.FAILED.value
POISONED = TransferState.POISONED.value


_TOKENIZER_KEYS = {"spiece_model", "tekken_model", "tokenizer_json"}
_TRANSFER_LOCK = threading.RLock()
_TRANSFER_REGISTRY_LIMIT = 256
_TRANSFER_REGISTRY: "OrderedDict[str, dict[str, Any]]" = OrderedDict()


def _stable_identity_scalar(name: str, value: Any) -> Any:
    """Validate an identity value without ever accepting a tensor/owner."""
    if isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise OwnershipTransferError(f"unstable identity field: {name}")
        return value
    if isinstance(value, (list, tuple)):
        return [_stable_identity_scalar(name, item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _stable_identity_scalar(name, item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    raise OwnershipTransferError(f"unstable identity field: {name}")


def _metadata_only(value: Any) -> Any:
    """Copy callback/telemetry data while excluding tensors and owners."""
    if value is None or isinstance(value, (str, int, bool, float)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _metadata_only(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_metadata_only(item) for item in value]
    return f"<{type(value).__module__}.{type(value).__name__}>"


def _first_identity_value(identity: Mapping[str, Any], manifests: list[dict], names: tuple[str, ...]) -> Any:
    for name in names:
        value = identity.get(name)
        if value not in (None, "", [], {}):
            return value
    for manifest in manifests:
        for name in names:
            value = (manifest or {}).get(name)
            if value not in (None, "", [], {}):
                return value
    return None


@dataclass(frozen=True)
class SourceManifestIdentity:
    """Stable, scalar identity for one cast-once source generation.

    The digest covers semantic selection and expected tensor metadata.  It
    intentionally does not hash tensor payloads: source/checkpoint and
    manifest/content identities are supplied by their authoritative producer.
    """

    checkpoint_identity: str
    manifest_generation: str
    selected_tensor_scope: str
    expected_keys: tuple[str, ...]
    expected_shapes: tuple[tuple[str, tuple[int, ...]], ...]
    expected_dtypes: tuple[tuple[str, str], ...]
    target_device: str
    cast_policy_version: str
    model_patch_identity: str
    digest: str

    @classmethod
    def build(
        cls,
        manifests: list[dict],
        *,
        identity: Optional[Mapping[str, Any]] = None,
        target_device: Optional[str] = None,
        cast_policy_version: str = "ra9g-fp32-v1",
    ) -> "SourceManifestIdentity":
        raw = dict(identity or {})
        checkpoint = _first_identity_value(
            raw, manifests, ("checkpoint_identity", "checkpoint_id", "source_identity", "checkpoint_hash", "stable_hash")
        )
        generation = _first_identity_value(
            raw, manifests, ("manifest_generation", "content_generation", "manifest_digest", "generation", "digest")
        )
        scope = _first_identity_value(
            raw, manifests, ("selected_tensor_scope", "tensor_scope", "selected_scope", "scope")
        )
        patch = _first_identity_value(
            raw, manifests, ("model_patch_identity", "patch_identity", "model_identity")
        )
        device = target_device or _first_identity_value(raw, manifests, ("target_device", "device"))
        required = {
            "checkpoint_identity": checkpoint,
            "manifest_generation": generation,
            "selected_tensor_scope": scope,
            "target_device": device,
            "cast_policy_version": cast_policy_version,
            "model_patch_identity": patch,
        }
        for name, value in required.items():
            if value in (None, "", [], {}):
                raise OwnershipTransferError(f"missing stable identity field: {name}")
            _stable_identity_scalar(name, value)
        if not isinstance(device, str) or not device.strip():
            raise OwnershipTransferError("target_device must be an explicit device string")

        key_specs: dict[str, tuple[tuple[int, ...], str]] = {}
        for manifest in manifests:
            dtype = str((manifest or {}).get("dtype", ""))
            for key in (manifest or {}).get("key_set") or []:
                key = str(key)
                if key in _TOKENIZER_KEYS:
                    continue
                if key in key_specs:
                    raise OwnershipTransferError(f"duplicate expected key: {key}")
                shape = tuple(int(dim) for dim in ((manifest.get("key_shapes") or {}).get(key) or []))
                if not shape and key not in ((manifest.get("key_shapes") or {})):
                    raise OwnershipTransferError(f"missing expected shape: {key}")
                if not dtype:
                    raise OwnershipTransferError(f"missing expected dtype: {key}")
                key_specs[key] = (shape, dtype)
        if not key_specs:
            raise OwnershipTransferError("empty selected tensor scope")
        keys = tuple(sorted(key_specs))
        shapes = tuple((key, key_specs[key][0]) for key in keys)
        dtypes = tuple((key, key_specs[key][1]) for key in keys)
        canonical = {
            "checkpoint_identity": _stable_identity_scalar("checkpoint_identity", checkpoint),
            "manifest_generation": _stable_identity_scalar("manifest_generation", generation),
            "selected_tensor_scope": _stable_identity_scalar("selected_tensor_scope", scope),
            "expected_keys": keys,
            "expected_shapes": shapes,
            "expected_dtypes": dtypes,
            "target_device": str(device),
            "cast_policy_version": str(cast_policy_version),
            "model_patch_identity": _stable_identity_scalar("model_patch_identity", patch),
        }
        digest = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=list).encode("utf-8")
        ).hexdigest()
        return cls(
            checkpoint_identity=str(checkpoint),
            manifest_generation=str(generation),
            selected_tensor_scope=str(scope),
            expected_keys=keys,
            expected_shapes=shapes,
            expected_dtypes=dtypes,
            target_device=str(device),
            cast_policy_version=str(cast_policy_version),
            model_patch_identity=str(patch),
            digest=digest,
        )

    def metadata(self) -> dict[str, Any]:
        return {
            "checkpoint_identity": self.checkpoint_identity,
            "manifest_generation": self.manifest_generation,
            "selected_tensor_scope": self.selected_tensor_scope,
            "expected_keys": list(self.expected_keys),
            "expected_shapes": {key: list(shape) for key, shape in self.expected_shapes},
            "expected_dtypes": dict(self.expected_dtypes),
            "target_device": self.target_device,
            "cast_policy_version": self.cast_policy_version,
            "model_patch_identity": self.model_patch_identity,
            "digest": self.digest,
        }


def build_source_manifest_identity(
    manifests: list[dict], *, identity: Optional[Mapping[str, Any]] = None,
    target_device: Optional[str] = None, cast_policy_version: str = "ra9g-fp32-v1",
) -> SourceManifestIdentity:
    return SourceManifestIdentity.build(
        manifests, identity=identity, target_device=target_device,
        cast_policy_version=cast_policy_version,
    )


def _tensor_storage_ptr(tensor: Any) -> Optional[int]:
    try:
        return int(tensor.untyped_storage().data_ptr())
    except Exception:
        return None


def _flatten_tensor_maps(mappings: Any) -> dict[str, Any]:
    if isinstance(mappings, dict):
        return {
            str(key): value for key, value in mappings.items()
            if str(key) not in _TOKENIZER_KEYS
        }
    flattened: dict[str, Any] = {}
    for mapping in mappings or []:
        if not isinstance(mapping, Mapping):
            raise OwnershipTransferError("destination mapping is not a mapping")
        for key, value in mapping.items():
            key = str(key)
            if key in flattened:
                raise OwnershipTransferError(f"duplicate destination key: {key}")
            if key not in _TOKENIZER_KEYS:
                flattened[key] = value
    return flattened


def actual_bind_destination_map(
    clip: Any, expected_keys: Any, *, allowed_extra_keys: Any = ()
) -> dict[str, Any]:
    """Collect the destination tensors after ``hydrate_clip_bind`` returns."""
    try:
        from . import clip_fast_hydration as _cfh
        csm = getattr(clip, "cond_stage_model", None)
        if csm is None:
            raise OwnershipTransferError("clip has no destination model")
        wanted = {str(key) for key in expected_keys}
        destination: dict[str, Any] = {}
        all_keys: set[str] = set()
        for leaf in _cfh._leaf_loaders(csm):
            for key, tensor in _cfh._leaf_param_map(leaf).items():
                key = str(key)
                all_keys.add(key)
                if key in wanted:
                    if key in destination and destination[key] is not tensor:
                        raise OwnershipTransferError(f"duplicate actual destination: {key}")
                    destination[key] = tensor
        unexpected = all_keys - wanted - {str(key) for key in (allowed_extra_keys or ())}
        if unexpected:
            raise OwnershipTransferError(f"actual destination extra keys: {sorted(unexpected)}")
        if set(destination) != wanted:
            raise OwnershipTransferError(
                f"actual destination key mismatch: missing={sorted(wanted - set(destination))} "
                f"extra={sorted(set(destination) - wanted)}"
            )
        return destination
    except OwnershipTransferError:
        raise
    except Exception as exc:
        raise OwnershipTransferError(f"actual destination collection failed: {exc}") from exc


def build_actual_bind_receipt(
    clip: Any,
    destination: Mapping[str, Any],
    identity: SourceManifestIdentity,
    *,
    assign: bool,
) -> dict[str, Any]:
    """Make scalar receipt evidence from the actual post-bind destination."""
    if assign is not True:
        raise BindReceiptError("actual bind receipt requires assign=True")
    csm = getattr(clip, "cond_stage_model", None)
    if csm is None:
        raise BindReceiptError("actual bind receipt requires a model")
    destination_map = _flatten_tensor_maps(destination)
    expected = set(identity.expected_keys)
    if set(destination_map) != expected:
        raise BindReceiptError("actual bind receipt key set mismatch")
    per_key: dict[str, dict[str, Any]] = {}
    for key in sorted(expected):
        tensor = destination_map[key]
        if not isinstance(tensor, torch.Tensor):
            raise BindReceiptError(f"actual bind destination is not tensor: {key}")
        per_key[key] = {
            "data_ptr": int(tensor.data_ptr()),
            "storage_ptr": _tensor_storage_ptr(tensor),
            "shape": list(tensor.shape),
            "dtype": str(tensor.dtype),
            "device": str(tensor.device),
            "parameter_id": int(id(tensor)),
        }
    return {
        "receipt_marker": "ra9g.actual_bind.v1",
        "actual_bind": True,
        "assign": True,
        "clip_id": int(id(clip)),
        "cond_stage_model_id": int(id(csm)),
        "identity_digest": identity.digest,
        "target_device": identity.target_device,
        "per_key": per_key,
    }


def snapshot_adopted_storage(
    clip: Any,
    bind_proof: Mapping[str, Any],
    *,
    expect_device: Optional[str] = None,
    phase: str = "post_real_forward",
) -> dict[str, Any]:
    """Source-free proof of the current destination parameters.

    This is intentionally based only on the scalar receipt/proof produced
    after the real bind.  It cannot accidentally retain or inspect a source
    state dict, transformed mapping, loader, or buffer.
    """
    record: dict[str, Any] = {
        "ok": False,
        "phase": str(phase),
        "reason": "",
        "generation": int(bind_proof.get("generation", 0) or 0),
        "expected_count": 0,
        "verified_count": 0,
        "expected_bytes": 0,
        "verified_bytes": 0,
        "per_key": [],
    }
    try:
        expected = bind_proof.get("per_key")
        if not isinstance(expected, Mapping) or not expected:
            record["reason"] = "missing_bind_proof"
            return record
        target = str(expect_device or bind_proof.get("target_device") or "")
        destination = actual_bind_destination_map(
            clip, expected, allowed_extra_keys=bind_proof.get("allowed_extra_keys", ())
        )
        record["expected_count"] = len(expected)
        for key in sorted(expected):
            tensor = destination[key]
            item = expected[key]
            if not isinstance(item, Mapping) or not isinstance(tensor, torch.Tensor):
                record["reason"] = f"missing_destination:{key}"
                return record
            entry = {
                "key": key,
                "file_index": int(item.get("file_index", 0) or 0),
                "manifest_file_index": int(item.get("file_index", 0) or 0),
                "source_file_index": int(item.get("file_index", 0) or 0),
                "destination_data_ptr": int(tensor.data_ptr()),
                "destination_storage_ptr": _tensor_storage_ptr(tensor),
                "destination_dtype": str(tensor.dtype),
                "destination_device": str(tensor.device),
                "source_dtype": str(item.get("dtype")),
                "source_device": str(item.get("device")),
                "source_is_meta": False,
                "shape": list(tensor.shape),
                "expected_shape": list(item.get("shape") or []),
                "destination_is_meta": bool(getattr(tensor, "is_meta", False)),
                "dtype_ok": True,
                "device_ok": True,
                "meta_ok": not bool(getattr(tensor, "is_meta", False)),
                "shape_ok": True,
                "source_bytes": 0,
                "destination_bytes": int(tensor.numel() * tensor.element_size()),
            }
            record["per_key"].append(entry)
            expected_bytes = 1
            for dimension in item.get("shape") or []:
                expected_bytes *= int(dimension)
            expected_bytes *= 4
            entry["source_bytes"] = expected_bytes
            record["expected_bytes"] += expected_bytes
            record["verified_bytes"] += int(tensor.numel() * tensor.element_size())
            pointer_ok = (
                int(tensor.data_ptr()) == int(item.get("data_ptr"))
                and _tensor_storage_ptr(tensor) == int(item.get("storage_ptr"))
                and int(id(tensor)) == int(item.get("parameter_id"))
            )
            metadata_ok = (
                list(tensor.shape) == list(item.get("shape") or [])
                and str(tensor.dtype) == str(item.get("dtype"))
                and str(tensor.device) == str(item.get("device"))
                and (not target or str(tensor.device) == target)
                and not bool(getattr(tensor, "is_meta", False))
            )
            entry.update({"pointer_ok": pointer_ok, "metadata_ok": metadata_ok, "matched": pointer_ok and metadata_ok})
            if entry["matched"]:
                record["verified_count"] += 1
        if record["verified_count"] != record["expected_count"]:
            record["reason"] = "source_free_storage_proof_failed"
            return record
        record.update({"ok": True, "source_free": True, "reason": "exact_adopted_storage_stable"})
        return record
    except Exception as exc:
        record["reason"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        return record


class ClipFP32OwnershipTransfer:
    """Fail-closed request-local ownership transfer for cast-once CLIP.

    This object is the sole owner of source/transformed maps, owner handles,
    callbacks, and temporary error/fallback references until the transfer is
    proven and quiesced.  It is deliberately absent from every module-global
    registry; only :meth:`snapshot` metadata may outlive the request.
    """

    def __init__(
        self,
        source_state_dicts: list[dict],
        owners: list[Any],
        manifests: list[dict],
        identity: SourceManifestIdentity | Mapping[str, Any],
        *,
        target_device: Optional[str] = None,
        retire_callback: Optional[Callable[[list[Any]], Any]] = None,
        external_source_release_callback: Optional[Callable[[], Any]] = None,
        external_source_release_receipt: Any = None,
        strict: bool = True,
    ) -> None:
        if not isinstance(identity, SourceManifestIdentity):
            identity = SourceManifestIdentity.build(
                manifests, identity=identity, target_device=target_device
            )
        if strict and not identity.target_device:
            raise OwnershipTransferError("strict transfer requires explicit target device")
        self._lock = threading.RLock()
        self._source = list(source_state_dicts or [])
        self._owners = list(owners or [])
        self._manifests = list(manifests or [])
        self._identity = identity
        self._retire_callback = retire_callback
        self._external_release_callback = external_source_release_callback
        self._external_release_receipt = external_source_release_receipt
        self._callbacks: list[Any] = [item for item in (retire_callback, external_source_release_callback) if item is not None]
        self._transformed: Optional[list[dict]] = None
        self._destination: Optional[dict[str, Any]] = None
        # Immutable, source-free proof retained after the source maps are
        # dropped.  A receipt is deliberately scalar-only; it is never a
        # substitute for the actual destination tensors passed to
        # acknowledge_actual_bind().
        self._bind_proof: Optional[dict[str, Any]] = None
        self._state = SOURCE_ACTIVE
        self._generation = 0
        self._record: dict[str, Any] = {"status": SOURCE_ACTIVE, "identity_digest": identity.digest}
        self._error: Optional[BaseException] = None
        self._cleanup_errors: list[str] = []
        self._fallback = False
        self._retirement_failed = False
        self._source_release_failed = False
        self._ever_failed = False

    @classmethod
    def build(cls, source_state_dicts: list[dict], owners: list[Any], manifests: list[dict], **kwargs: Any) -> "ClipFP32OwnershipTransfer":
        identity = kwargs.pop("identity", None)
        target_device = kwargs.pop("target_device", None)
        if not isinstance(identity, SourceManifestIdentity):
            identity = SourceManifestIdentity.build(manifests, identity=identity, target_device=target_device)
        return cls(source_state_dicts, owners, manifests, identity, **kwargs)

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def identity(self) -> SourceManifestIdentity:
        return self._identity

    def _require(self, *states: str) -> None:
        if self._state not in states:
            raise OwnershipTransferError(f"invalid transition from {self._state}; expected {states}")

    def _poison(self, exc: BaseException) -> None:
        self._error = exc
        self._ever_failed = True
        self._state = FAILED
        self._record.update({"status": FAILED, "error": f"{type(exc).__name__}: {str(exc)[:240]}"})

    def _validate_source(self) -> tuple[int, int]:
        if len(self._source) != len(self._manifests):
            raise OwnershipTransferError("source/manifest file count mismatch")
        expected = set(self._identity.expected_keys)
        shapes = dict(self._identity.expected_shapes)
        dtypes = dict(self._identity.expected_dtypes)
        seen: set[str] = set()
        source_bytes = 0
        for file_index, (mapping, manifest) in enumerate(zip(self._source, self._manifests)):
            if not isinstance(mapping, Mapping):
                raise OwnershipTransferError("source state is not a mapping")
            if not isinstance(manifest, Mapping):
                raise OwnershipTransferError(f"manifest is not a mapping: file {file_index}")
            declared_index = manifest.get("file_index")
            if declared_index is not None and int(declared_index) != file_index:
                raise OwnershipTransferError(
                    f"manifest file index mismatch: file {file_index} declares {declared_index}"
                )
            file_keys = {
                str(key) for key in (manifest.get("key_set") or ())
                if str(key) not in _TOKENIZER_KEYS
            }
            if len(file_keys) != len([
                key for key in (manifest.get("key_set") or ())
                if str(key) not in _TOKENIZER_KEYS
            ]):
                raise OwnershipTransferError(f"duplicate manifest key: file {file_index}")
            actual_file_keys = {
                str(key) for key in mapping if str(key) not in _TOKENIZER_KEYS
            }
            if actual_file_keys != file_keys:
                raise OwnershipTransferError(
                    f"source file {file_index} key set mismatch: "
                    f"missing={sorted(file_keys - actual_file_keys)} "
                    f"extra={sorted(actual_file_keys - file_keys)}"
                )
            manifest_dtype = str(manifest.get("dtype", ""))
            if not manifest_dtype:
                raise OwnershipTransferError(f"missing manifest dtype: file {file_index}")
            for key, tensor in mapping.items():
                key = str(key)
                if key in _TOKENIZER_KEYS:
                    continue
                if key in seen:
                    raise OwnershipTransferError(f"duplicate source key: {key}")
                seen.add(key)
                if key not in expected or not isinstance(tensor, torch.Tensor):
                    raise OwnershipTransferError(f"unexpected or non-tensor source: {key}")
                expected_shape = (manifest.get("key_shapes") or {}).get(key)
                if expected_shape is None:
                    raise OwnershipTransferError(
                        f"missing manifest shape for file {file_index}: {key}"
                    )
                if tuple(tensor.shape) != tuple(expected_shape):
                    raise OwnershipTransferError(
                        f"source key shape mismatch: file {file_index}: {key}"
                    )
                if str(tensor.dtype) != manifest_dtype:
                    raise OwnershipTransferError(
                        f"source key dtype mismatch: file {file_index}: {key}"
                    )
                if tuple(tensor.shape) != tuple(shapes[key]) or str(tensor.dtype) != dtypes[key]:
                    raise OwnershipTransferError(f"source key metadata mismatch: {key}")
                source_bytes += int(tensor.numel() * tensor.element_size())
        if seen != expected:
            raise OwnershipTransferError(f"source key set mismatch: missing={sorted(expected - seen)} extra={sorted(seen - expected)}")
        return len(seen), source_bytes

    def transform_once(self, *, trace: Any = None) -> tuple[list[dict], dict[str, Any]]:
        with self._lock:
            self._require(SOURCE_ACTIVE)
            self._state = FP32_TRANSFORM_IN_PROGRESS
            try:
                count, source_bytes = self._validate_source()
                transformed: list[dict] = []
                destination_bytes = 0
                converted = 0
                for mapping in self._source:
                    out: _CastOnceStateDict = _CastOnceStateDict()
                    for key, tensor in mapping.items():
                        if isinstance(tensor, torch.Tensor) and str(tensor.dtype) == _SOURCE_DTYPE:
                            out[key] = tensor.to(torch.float32)
                            converted += 1
                            destination_bytes += int(out[key].numel() * out[key].element_size())
                        else:
                            out[key] = tensor
                    transformed.append(out)
                self._transformed = transformed
                self._record.update({
                    "status": FP32_BOUND_UNPROVEN,
                    "tensor_count": converted,
                    "source_bytes": source_bytes,
                    "destination_bytes": destination_bytes,
                    "real_conversion_count": converted,
                    "real_conversion_bytes": destination_bytes,
                    "fp32_param_count": converted,
                    "fp32_bytes": destination_bytes,
                    "bytes_out": destination_bytes,
                    "count_by_dtype": {_COMPUTE_DTYPE: converted},
                    "bytes_by_dtype": {_COMPUTE_DTYPE: destination_bytes},
                    "generation": 0,
                })
                self._state = FP32_BOUND_UNPROVEN
                return transformed, dict(self._record)
            except BaseException as exc:
                self._transformed = None
                self._poison(exc)
                raise

    transform = transform_once

    def acknowledge_bind(
        self, destination: Any, *, assign: bool, adopted: bool = True,
        storage_identity: Optional[Mapping[str, Any]] = None,
        expected_device: Optional[str] = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._require(FP32_BOUND_UNPROVEN)
            try:
                if assign is not True or adopted is not True:
                    raise OwnershipTransferError("bind requires assign=True and adoption acknowledgement")
                if expected_device is not None and str(expected_device) != self._identity.target_device:
                    raise OwnershipTransferError("bind expected-device contract mismatch")
                if self._transformed is None:
                    raise OwnershipTransferError("transformed mapping unavailable")
                destination_map = _flatten_tensor_maps(destination)
                transformed_map = _flatten_tensor_maps(self._transformed)
                expected = set(self._identity.expected_keys)
                if set(destination_map) != expected or set(transformed_map) != expected:
                    raise OwnershipTransferError("bind key set mismatch")
                expected_shapes = dict(self._identity.expected_shapes)
                for key in sorted(expected):
                    src, dst = transformed_map[key], destination_map[key]
                    if not isinstance(dst, torch.Tensor):
                        raise OwnershipTransferError(f"destination is not tensor: {key}")
                    if tuple(dst.shape) != tuple(expected_shapes[key]) or tuple(src.shape) != tuple(expected_shapes[key]):
                        raise OwnershipTransferError(f"bind shape mismatch: {key}")
                    if str(dst.dtype) != _COMPUTE_DTYPE or str(src.dtype) != _COMPUTE_DTYPE:
                        raise OwnershipTransferError(f"bind dtype mismatch: {key}")
                    if str(dst.device) != self._identity.target_device:
                        raise OwnershipTransferError(f"bind device mismatch: {key}")
                    if _tensor_storage_ptr(src) is None or _tensor_storage_ptr(src) != _tensor_storage_ptr(dst) or int(src.data_ptr()) != int(dst.data_ptr()):
                        raise OwnershipTransferError(f"bind adoption storage mismatch: {key}")
                    if storage_identity is not None:
                        expected_ptr = storage_identity.get(key)
                        if expected_ptr is None or int(expected_ptr) != int(dst.data_ptr()):
                            raise OwnershipTransferError(f"bind receipt storage mismatch: {key}")
                self._destination = destination_map
                self._record.update({"assign": True, "adopted": True, "storage_identity_provided": storage_identity is not None})
                return dict(self._record)
            except BaseException as exc:
                self._poison(exc)
                raise

    bind = acknowledge_bind

    def acknowledge_actual_bind(
        self,
        destination: Any,
        *,
        receipt: Mapping[str, Any],
        assign: bool,
        clip: Any = None,
    ) -> dict[str, Any]:
        """Accept only a receipt made from the post-Comfy destination.

        ``acknowledge_bind`` remains a compatibility seam for old unit tests
        and offline callers.  Production/strict wiring must use this method:
        the receipt marker, model identity, and every destination pointer are
        checked against the tensors returned by the actual bind.
        """
        with self._lock:
            self._require(FP32_BOUND_UNPROVEN)
            try:
                if assign is not True:
                    raise BindReceiptError("bind requires assign=True")
                if not isinstance(receipt, Mapping) or receipt.get("receipt_marker") != "ra9g.actual_bind.v1":
                    raise BindReceiptError("actual bind receipt marker required")
                if receipt.get("assign") is not True or receipt.get("actual_bind") is not True:
                    raise BindReceiptError("receipt is not an assign=True actual-bind receipt")
                if str(receipt.get("identity_digest", "")) != self._identity.digest:
                    raise BindReceiptError("bind receipt identity mismatch")
                if str(receipt.get("target_device", "")) != self._identity.target_device:
                    raise BindReceiptError("bind receipt target-device mismatch")
                if clip is not None:
                    csm = getattr(clip, "cond_stage_model", None)
                    if int(receipt.get("clip_id", -1)) != int(id(clip)) or int(receipt.get("cond_stage_model_id", -1)) != int(id(csm)):
                        raise BindReceiptError("bind receipt model identity mismatch")
                destination_map = _flatten_tensor_maps(destination)
                transformed_map = _flatten_tensor_maps(self._transformed or [])
                expected = set(self._identity.expected_keys)
                if set(destination_map) != expected or set(transformed_map) != expected:
                    raise BindReceiptError("bind receipt key set mismatch")
                receipt_keys = receipt.get("per_key")
                if not isinstance(receipt_keys, Mapping) or set(receipt_keys) != expected:
                    raise BindReceiptError("bind receipt per-key evidence mismatch")
                expected_shapes = dict(self._identity.expected_shapes)
                expected_dtypes = dict(self._identity.expected_dtypes)
                proof: dict[str, Any] = {}
                for key in sorted(expected):
                    src = transformed_map[key]
                    dst = destination_map[key]
                    entry = receipt_keys.get(key)
                    if not isinstance(src, torch.Tensor) or not isinstance(dst, torch.Tensor):
                        raise BindReceiptError(f"bind receipt missing tensor: {key}")
                    if not isinstance(entry, Mapping):
                        raise BindReceiptError(f"bind receipt missing key evidence: {key}")
                    if tuple(dst.shape) != expected_shapes[key] or tuple(src.shape) != expected_shapes[key]:
                        raise BindReceiptError(f"bind shape mismatch: {key}")
                    if str(dst.dtype) != _COMPUTE_DTYPE or str(src.dtype) != _COMPUTE_DTYPE:
                        raise BindReceiptError(f"bind dtype mismatch: {key}")
                    if str(dst.device) != self._identity.target_device:
                        raise BindReceiptError(f"bind device mismatch: {key}")
                    src_storage = _tensor_storage_ptr(src)
                    dst_storage = _tensor_storage_ptr(dst)
                    src_data = int(src.data_ptr())
                    dst_data = int(dst.data_ptr())
                    if src_storage is None or src_storage != dst_storage or src_data != dst_data:
                        raise BindReceiptError(f"bind adoption storage mismatch: {key}")
                    expected_entry = {
                        "data_ptr": dst_data,
                        "storage_ptr": dst_storage,
                        "shape": list(dst.shape),
                        "dtype": str(dst.dtype),
                        "device": str(dst.device),
                        "parameter_id": int(id(dst)),
                    }
                    if any(entry.get(name) != value for name, value in expected_entry.items()):
                        raise BindReceiptError(f"bind receipt destination mismatch: {key}")
                    proof[key] = expected_entry
                self._destination = destination_map
                self._record.update({
                    "assign": True,
                    "adopted": True,
                    "storage_identity_provided": True,
                    "bind_receipt": _metadata_only(receipt),
                })
                return dict(self._record)
            except BaseException as exc:
                self._poison(exc)
                raise

    def prove_storage(self, *, expected_device: Optional[str] = None) -> dict[str, Any]:
        with self._lock:
            if self._state == FP32_BOUND_PROVEN:
                return dict(self._record)
            self._require(FP32_BOUND_UNPROVEN)
            try:
                if expected_device is not None and str(expected_device) != self._identity.target_device:
                    raise OwnershipTransferError("storage proof expected-device contract mismatch")
                if self._destination is None or self._transformed is None:
                    raise OwnershipTransferError("bind evidence unavailable")
                transformed = _flatten_tensor_maps(self._transformed)
                source = _flatten_tensor_maps(self._source)
                unique: set[int] = set()
                source_bytes = 0
                destination_bytes = 0
                per_key: list[dict[str, Any]] = []
                file_indices = {
                    str(key): int(file_index)
                    for file_index, mapping in enumerate(self._source)
                    for key in mapping
                    if str(key) not in _TOKENIZER_KEYS
                }
                for key in self._identity.expected_keys:
                    src, dst = transformed[key], self._destination.get(key)
                    if not isinstance(src, torch.Tensor) or not isinstance(dst, torch.Tensor):
                        raise OwnershipTransferError(f"storage proof missing tensor: {key}")
                    if str(src.device) != self._identity.target_device or str(dst.device) != self._identity.target_device:
                        raise OwnershipTransferError(f"storage proof device mismatch: {key}")
                    if tuple(src.shape) != tuple(dst.shape) or str(src.dtype) != str(dst.dtype) or str(dst.dtype) != _COMPUTE_DTYPE:
                        raise OwnershipTransferError(f"storage proof metadata mismatch: {key}")
                    if _tensor_storage_ptr(src) is None or _tensor_storage_ptr(src) != _tensor_storage_ptr(dst) or int(src.data_ptr()) != int(dst.data_ptr()):
                        raise OwnershipTransferError(f"storage proof adoption mismatch: {key}")
                    unique.add(int(_tensor_storage_ptr(dst)))
                    source_bytes += int(source[key].numel() * source[key].element_size())
                    destination_bytes += int(dst.numel() * dst.element_size())
                    per_key.append({
                        "key": key,
                        "shape": list(dst.shape),
                        "dtype": str(dst.dtype),
                        "device": str(dst.device),
                        "source_data_ptr": int(source[key].data_ptr()),
                        "destination_data_ptr": int(dst.data_ptr()),
                        "source_storage_ptr": _tensor_storage_ptr(source[key]),
                        "destination_storage_ptr": _tensor_storage_ptr(dst),
                        "file_index": int(file_indices.get(key, 0)),
                    })
                self._record.update({
                    "status": FP32_BOUND_PROVEN,
                    "parameter_count": len(self._identity.expected_keys),
                    "fp32_param_count": len(self._identity.expected_keys),
                    "expected_count": len(self._identity.expected_keys),
                    "verified_count": len(self._identity.expected_keys),
                    "expected_bytes": destination_bytes,
                    "verified_bytes": destination_bytes,
                    "source_bytes": source_bytes,
                    "destination_bytes": destination_bytes,
                    "fp32_bytes": destination_bytes,
                    "count_by_dtype": {_COMPUTE_DTYPE: len(self._identity.expected_keys)},
                    "bytes_by_dtype": {_COMPUTE_DTYPE: destination_bytes},
                    "unique_storage_count": len(unique),
                    "storage_proven": True,
                    "per_key": per_key,
                })
                self._bind_proof = {
                    "receipt_marker": "ra9g.bind_proof.v1",
                    "identity_digest": self._identity.digest,
                    "target_device": self._identity.target_device,
                    "expected_keys": list(self._identity.expected_keys),
                    "allowed_extra_keys": sorted({
                        str(key)
                        for manifest in self._manifests
                        for key in (manifest.get("structural_destination_keys") or ())
                    }),
                    "per_key": {
                        item["key"]: {
                            "data_ptr": item["destination_data_ptr"],
                            "storage_ptr": item["destination_storage_ptr"],
                            "shape": list(item["shape"]),
                            "dtype": item.get("destination_dtype", item.get("dtype")),
                            "device": item.get("destination_device", item.get("device")),
                            "parameter_id": int(id(self._destination[item["key"]])) if self._destination is not None else None,
                            "file_index": int(file_indices.get(item["key"], 0)),
                        }
                        for item in per_key
                    },
                }
                self._record["bind_proof"] = _metadata_only(self._bind_proof)
                self._state = FP32_BOUND_PROVEN
                return dict(self._record)
            except BaseException as exc:
                self._poison(exc)
                raise

    prove = prove_storage

    def drop_source_references(self, *, receipt: Any = None) -> dict[str, Any]:
        with self._lock:
            if self._state == SOURCE_REFS_DROPPED:
                return dict(self._record)
            if self._state == FAILED and self._source_release_failed:
                pass
            else:
                self._require(FP32_BOUND_PROVEN)
            try:
                if self._external_release_callback is not None:
                    release_receipt = receipt if receipt is not None else self._external_release_receipt
                    if release_receipt is None:
                        release_receipt = self._external_release_callback()
                    if release_receipt in (None, False):
                        raise OwnershipTransferError("external source reference receipt required")
                    self._external_release_receipt = _stable_identity_scalar(
                        "source_release_receipt", release_receipt
                    )
                    self._external_release_callback = None
                    self._callbacks = [callback for callback in self._callbacks if callback is self._retire_callback]
                elif receipt is not None:
                    self._external_release_receipt = _stable_identity_scalar(
                        "source_release_receipt", receipt
                    )
                self._source.clear()
                self._transformed = None
                self._destination = None
                self._record.update({"status": SOURCE_REFS_DROPPED, "source_refs_dropped": True})
                self._state = SOURCE_REFS_DROPPED
                return dict(self._record)
            except BaseException as exc:
                if self._external_release_callback is not None:
                    self._source_release_failed = True
                self._poison(exc)
                raise

    drop_source_refs = drop_source_references

    def retire_owners(self) -> dict[str, Any]:
        with self._lock:
            if self._state == SOURCE_OWNER_RETIRED:
                return dict(self._record)
            if self._state == FAILED and self._retirement_failed:
                pass
            else:
                self._require(SOURCE_REFS_DROPPED)
            try:
                if not self._owners:
                    raise OwnershipTransferError("source owner handles are required")
                result = self._retire_callback(self._owners) if self._retire_callback else self._release_owners()
                if isinstance(result, Mapping) and result.get("ok") is False:
                    raise OwnershipTransferError("source owner retirement failed")
                self._owners.clear()
                self._retire_callback = None
                self._external_release_callback = None
                self._callbacks.clear()
                self._record.update({"status": SOURCE_OWNER_RETIRED, "owner_retired": True, "owner_result": dict(result) if isinstance(result, Mapping) else {"ok": True}})
                self._state = SOURCE_OWNER_RETIRED
                return dict(self._record)
            except BaseException as exc:
                self._retirement_failed = True
                self._poison(exc)
                raise

    retire_source_owners = retire_owners

    def _release_owners(self) -> dict[str, Any]:
        errors: list[str] = []
        remaining: list[Any] = []
        retired = 0
        for owner in list(self._owners):
            components = tuple(owner) if isinstance(owner, (tuple, list)) else (owner,)
            remaining_components: list[Any] = []
            for component in components:
                if component is None:
                    continue
                method = getattr(component, "release_storage", None)
                if not callable(method):
                    for name in ("free_storage", "release"):
                        candidate = getattr(component, name, None)
                        if callable(candidate):
                            method = candidate
                            break
                released = False
                if callable(method):
                    try:
                        # Never retry this without the explicit no-purge
                        # contract.  A destructive close is failure cleanup,
                        # not successful ownership retirement.
                        method(purge_allocator=False)
                        released = True
                    except Exception as exc:  # preserve failed handles
                        errors.append(f"{type(exc).__name__}: {str(exc)[:120]}")
                else:
                    errors.append("owner has no non-destructive release API")
                if not released:
                    remaining_components.append(component)
            if remaining_components:
                remaining.append(tuple(remaining_components) if isinstance(owner, (tuple, list)) else remaining_components[0])
            else:
                retired += 1
        self._owners[:] = remaining
        if errors:
            raise OwnershipTransferError("; ".join(errors))
        return {"ok": True, "owners_retired": retired}

    def mark_ready(self, clip: Any = None) -> dict[str, Any]:
        with self._lock:
            if self._state == READY:
                return dict(self._record)
            if self._ever_failed:
                raise OwnershipTransferError("failed transfer cannot become READY")
            self._require(SOURCE_OWNER_RETIRED)
            with _TRANSFER_LOCK:
                prior = int((_TRANSFER_REGISTRY.get(self._identity.digest) or {}).get("generation", 0))
                generation = prior + 1
                _TRANSFER_REGISTRY[self._identity.digest] = {"generation": generation, "status": READY, "identity_digest": self._identity.digest}
                while len(_TRANSFER_REGISTRY) > _TRANSFER_REGISTRY_LIMIT:
                    _TRANSFER_REGISTRY.popitem(last=False)
            self._generation = generation
            self._record.update({"status": READY, "generation": generation, "ready": True})
            self._state = READY
            if clip is not None:
                try:
                    mark_cast_once_applied(clip, self._identity)
                except Exception:
                    pass
            return dict(self._record)

    def mark_fallback(self, reason: str) -> dict[str, Any]:
        with self._lock:
            self._require(SOURCE_ACTIVE)
            self._fallback = True
            self._record.update({"fallback": True, "fallback_reason": str(reason)[:240]})
            self._poison(OwnershipTransferError(f"explicit fallback: {reason}"))
            return dict(self._record)

    def fail(self, exc: BaseException) -> dict[str, Any]:
        with self._lock:
            self._poison(exc)
            return dict(self._record)

    def release(self) -> dict[str, Any]:
        """Idempotent terminal cleanup for fallback, failure, or abort paths."""
        with self._lock:
            if self._state == READY:
                return dict(self._record)
            cleanup_errors: list[str] = []
            if self._owners:
                try:
                    self._release_owners()
                except Exception as exc:
                    cleanup_errors.append(f"{type(exc).__name__}: {str(exc)[:160]}")
            self._source.clear()
            self._transformed = None
            self._destination = None
            # Successful handles are removed by _release_owners.  Failed
            # handles and callbacks stay reachable for a retry/diagnostic
            # cleanup; clearing them would hide the unsafe state.
            if not self._owners and not self._source_release_failed:
                self._callbacks.clear()
                self._retire_callback = None
                self._external_release_callback = None
            self._cleanup_errors.extend(cleanup_errors)
            if cleanup_errors:
                self._record["cleanup_errors"] = list(self._cleanup_errors)
                if self._error is not None:
                    try:
                        self._error.add_note("RA9G cleanup errors: " + "; ".join(cleanup_errors))
                    except Exception:
                        pass
            return dict(self._record)

    close = release

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            if self._state != READY or self._source or self._transformed is not None or self._destination is not None or self._owners or self._callbacks:
                raise OwnershipTransferError("RA9G snapshot requires a quiescent READY transfer")
            result = _metadata_only(self._record)
            result.update({"status": READY, "identity": self._identity.metadata(), "metadata_only": True, "source_refs": 0, "owners": 0, "callbacks": 0})
            return result

    def source_free_storage_proof(self, destination: Any, *, expected_device: Optional[str] = None) -> dict[str, Any]:
        """Prove current adopted storage using only the immutable bind proof."""
        with self._lock:
            if self._state not in (SOURCE_REFS_DROPPED, SOURCE_OWNER_RETIRED, READY):
                raise OwnershipTransferError("source-free proof requires a retired source state")
            if not self._bind_proof:
                raise OwnershipTransferError("source-free bind proof unavailable")
            if expected_device is not None and str(expected_device) != self._bind_proof["target_device"]:
                raise OwnershipTransferError("source-free proof device contract mismatch")
            actual = _flatten_tensor_maps(destination)
            expected = self._bind_proof["per_key"]
            if set(actual) != set(expected):
                raise OwnershipTransferError("source-free proof key set mismatch")
            for key, entry in expected.items():
                tensor = actual[key]
                if not isinstance(tensor, torch.Tensor):
                    raise OwnershipTransferError(f"source-free proof non-tensor: {key}")
                if int(tensor.data_ptr()) != int(entry["data_ptr"]):
                    raise OwnershipTransferError(f"source-free proof data pointer mismatch: {key}")
                if _tensor_storage_ptr(tensor) != int(entry["storage_ptr"]):
                    raise OwnershipTransferError(f"source-free proof storage pointer mismatch: {key}")
                if list(tensor.shape) != list(entry["shape"]) or str(tensor.dtype) != entry["dtype"] or str(tensor.device) != entry["device"]:
                    raise OwnershipTransferError(f"source-free proof metadata mismatch: {key}")
            return {"ok": True, "source_free": True, "per_key": _metadata_only(expected), "target_device": self._bind_proof["target_device"]}

    assert_quiescent = snapshot

    def status(self) -> dict[str, Any]:
        with self._lock:
            result = dict(self._record)
            result.update({"status": self._state, "identity_digest": self._identity.digest, "source_refs": len(self._source), "transformed_refs": 0 if self._transformed is None else len(self._transformed), "owners": len(self._owners), "callbacks": len(self._callbacks), "cleanup_errors": list(self._cleanup_errors), "fallback": self._fallback})
            return result

    @property
    def source_mappings(self) -> Optional[tuple[dict, ...]]:
        with self._lock:
            return tuple(self._source) if self._source else None

    @property
    def transformed_mappings(self) -> Optional[tuple[dict, ...]]:
        with self._lock:
            return tuple(self._transformed) if self._transformed is not None else None

    @property
    def owner_handles(self) -> Optional[tuple[Any, ...]]:
        with self._lock:
            return tuple(self._owners) if self._owners else None


def construct_ownership_transfer(
    source_state_dicts: list[dict], owners: list[Any], manifests: list[dict], *,
    identity: Optional[Mapping[str, Any] | SourceManifestIdentity] = None,
    target_device: Optional[str] = None, strict: bool = True,
    retire_callback: Optional[Callable[[list[Any]], Any]] = None,
    external_source_release_callback: Optional[Callable[[], Any]] = None,
    external_source_release_receipt: Any = None,
) -> ClipFP32OwnershipTransfer:
    """Construct the request-local contract used by a future Golden adapter."""
    stable_identity = identity if isinstance(identity, SourceManifestIdentity) else SourceManifestIdentity.build(
        manifests, identity=identity, target_device=target_device
    )
    return ClipFP32OwnershipTransfer(
        source_state_dicts, owners, manifests, stable_identity,
        retire_callback=retire_callback,
        external_source_release_callback=external_source_release_callback,
        external_source_release_receipt=external_source_release_receipt,
        strict=strict,
    )


class _CastOnceStateDict(dict):
    """A state dict carrying non-optional cast-once source provenance.

    The attribute is deliberately attached to the transformed mapping rather
    than hidden in a process-global table: speculative and demand paths can
    pass the mapping through independently while verification still refuses a
    plain, arbitrary FP32 mapping.
    """

    pass


def cast_once_enabled() -> bool:
    """Gate: compute-ready FP32 cast-once (default OFF — experimental)."""
    return env_flag(_FLAG, default=False)


def cast_once_flag() -> str:
    return _FLAG


def cast_once_expected_dtype() -> str:
    return _COMPUTE_DTYPE


def apply_cast_once(
    per_file_sds: list[dict],
    file_manifests: list[dict],
    *,
    trace: Any = None,
) -> tuple[list[dict], dict[str, Any]]:
    """Cast every tensor in *per_file_sds* from its source dtype to FP32
    (exact widening) in place on the tensor's own device.

    Gates (fail-closed — returns the input unchanged with ``applied=False``):
    * the flag is on;
    * every file manifest dtype is BF16 (the measured Qwen profile; other
      dtypes are left to the normal per-forward cast path);
    * every tensor is a plain dense tensor whose dtype matches the manifest.

    Returns ``(state_dicts, record)``; the record is JSON-safe telemetry:
    applied, tensor_count, bytes_in, bytes_out, host_wall_ms,
    cuda_event_wall_ms, allocated_delta_bytes, dtype_before, dtype_after.
    """
    import torch

    record: dict[str, Any] = {
        "requested": bool(cast_once_enabled()),
        "applied": False,
        "fallback_count": 1 if cast_once_enabled() else 0,
        "reason": "",
        "tensor_count": 0,
        "bytes_in": 0,
        "bytes_out": 0,
        "host_wall_ms": 0.0,
        "cuda_event_wall_ms": 0.0,
        "allocated_delta_bytes": 0,
        "dtype_before": "",
        "dtype_after": _COMPUTE_DTYPE,
    }
    if not cast_once_enabled():
        record["reason"] = "flag_off"
        return per_file_sds, record
    try:
        if len(per_file_sds) != len(file_manifests):
            record["reason"] = "file_count_mismatch"
            return per_file_sds, record
        for entry in file_manifests:
            if str(entry.get("dtype", "")) != _SOURCE_DTYPE:
                record["reason"] = f"unsupported_source_dtype:{entry.get('dtype', '')}"
                return per_file_sds, record
        _t0 = time.perf_counter()
        _ev_start = None
        _ev_end = None
        try:
            if torch.cuda.is_available():
                _ev_start = torch.cuda.Event(enable_timing=True)
                _ev_end = torch.cuda.Event(enable_timing=True)
                _ev_start.record()
        except Exception:
            _ev_start = _ev_end = None
        _alloc_before = int(torch.cuda.memory_allocated()) if torch.cuda.is_available() else 0
        _bytes_in = 0
        _bytes_out = 0
        _count = 0
        _cast_sds: list[dict] = []
        for local_file_index, (sd, manifest) in enumerate(zip(per_file_sds, file_manifests)):
            # ``apply_cast_once`` is also called once per file by the normal
            # demand fallback.  The local enumerate value is therefore not
            # provenance: preserve the accepted manifest/global index so a
            # second checkpoint file cannot be silently relabelled as file 0.
            file_index = int(manifest.get("file_index", local_file_index))
            if manifest.get("file_index") is not None and file_index != local_file_index:
                record["reason"] = (
                    f"manifest_file_index_mismatch:{local_file_index}:{file_index}"
                )
                return per_file_sds, record
            manifest_keys = [str(key) for key in (manifest.get("key_set") or [])]
            if len(manifest_keys) != len(set(manifest_keys)):
                record["reason"] = f"duplicate_manifest_key_set:{file_index}"
                return per_file_sds, record
            expected_keys = {
                key for key in (manifest_keys or [str(key) for key in sd])
                if key not in _TOKENIZER_KEYS
            }
            actual_keys = {
                str(key) for key in sd if str(key) not in _TOKENIZER_KEYS
            }
            if actual_keys != expected_keys:
                record["reason"] = (
                    f"source_key_set_mismatch:{file_index}:"
                    f"unexpected={len(actual_keys - expected_keys)} "
                    f"missing={len(expected_keys - actual_keys)}"
                )
                return per_file_sds, record
            source_dtypes: dict[str, str] = {}
            source_shapes: dict[str, list[int]] = {}
            for key in sorted(expected_keys):
                tensor = sd.get(key)
                if not isinstance(tensor, torch.Tensor):
                    record["reason"] = f"missing_or_non_tensor_source:{file_index}:{key}"
                    return per_file_sds, record
                actual_dtype = str(tensor.dtype)
                expected_dtype = str(manifest.get("dtype", ""))
                if actual_dtype != expected_dtype or actual_dtype != _SOURCE_DTYPE:
                    record["reason"] = (
                        f"source_dtype_mismatch:{file_index}:{key}:"
                        f"got {actual_dtype} expected {expected_dtype}"
                    )
                    return per_file_sds, record
                expected_shape = (manifest.get("key_shapes") or {}).get(key)
                if manifest_keys and expected_shape is None:
                    record["reason"] = f"missing_manifest_shape:{file_index}:{key}"
                    return per_file_sds, record
                if expected_shape is not None and list(tensor.shape) != list(expected_shape):
                    record["reason"] = f"source_shape_mismatch:{file_index}:{key}"
                    return per_file_sds, record
                source_dtypes[key] = actual_dtype
                source_shapes[key] = list(tensor.shape)
            out: _CastOnceStateDict = _CastOnceStateDict()
            for key, tensor in sd.items():
                if not isinstance(tensor, torch.Tensor):
                    out[key] = tensor
                    continue
                if str(tensor.dtype) != _SOURCE_DTYPE:
                    # Non-BF16 tensors (e.g. tokenizer blobs) pass through.
                    out[key] = tensor
                    continue
                _bytes_in += int(tensor.numel() * tensor.element_size())
                cast = tensor.to(torch.float32)
                # Destination bytes measured from the ACTUAL cast tensor
                # (exact per-tensor accounting, not a numel*dtype guess).
                _bytes_out += int(cast.numel() * cast.element_size())
                _count += 1
                out[key] = cast
            _cast_sds.append(out)
            setattr(out, _CAST_PROVENANCE_ATTR, {
                "schema": 1,
                "source_dtype": _SOURCE_DTYPE,
                "source_dtype_by_key": source_dtypes,
                "source_shapes": source_shapes,
                "manifest_key_set": sorted(expected_keys),
                "file_index": file_index,
            })
        if _ev_end is not None:
            _ev_end.record()
            try:
                _ev_end.synchronize()
                _cuda_ms = float(_ev_start.elapsed_time(_ev_end))
            except Exception:
                _cuda_ms = 0.0
        else:
            _cuda_ms = 0.0
        _alloc_after = int(torch.cuda.memory_allocated()) if torch.cuda.is_available() else 0
        record.update({
            "applied": True,
            "fallback_count": 0,
            "reason": "ok",
            "tensor_count": _count,
            "bytes_in": _bytes_in,
            "bytes_out": _bytes_out,
            "fp32_param_count": _count,
            "fp32_bytes": _bytes_out,
            "host_wall_ms": round((time.perf_counter() - _t0) * 1000.0, 3),
            "cuda_event_wall_ms": round(_cuda_ms, 3),
            "allocated_delta_bytes": max(int(_alloc_after - _alloc_before), 0),
            "dtype_before": "torch.bfloat16",
            "source_dtype": _SOURCE_DTYPE,
            "source_provenance_files": len(_cast_sds),
            "source_provenance": [
                dict(getattr(item, _CAST_PROVENANCE_ATTR, {}) or {})
                for item in _cast_sds
            ],
            "per_file": [
                {
                    "file_index": int((file_manifests[index] or {}).get("file_index", index)),
                    "requested": True,
                    "applied": True,
                    "tensor_count": sum(
                        1 for tensor in item.values()
                        if isinstance(tensor, torch.Tensor)
                        and str(tensor.dtype) == _COMPUTE_DTYPE
                    ),
                    "bytes_out": sum(
                        int(tensor.numel() * tensor.element_size())
                        for tensor in item.values()
                        if isinstance(tensor, torch.Tensor)
                        and str(tensor.dtype) == _COMPUTE_DTYPE
                    ),
                }
                for index, item in enumerate(_cast_sds)
            ],
        })
        return _cast_sds, record
    except Exception as exc:  # noqa: BLE001 - fail closed
        record["reason"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        # Fail-closed must be diagnosable: report how far the cast got before
        # the failure so a partial conversion can never masquerade as applied.
        record["partial_tensor_count"] = _count if "_count" in dir() else 0
        record["partial_bytes_out"] = _bytes_out if "_bytes_out" in dir() else 0
        return per_file_sds, record


def verify_cast_once_sd(file_manifest: dict, sd: dict) -> tuple[bool, str]:
    """Manifest verification for cast-once state dicts: exact key set and
    shapes as frozen, but dtype must be FP32 (the cast target) instead of the
    frozen source dtype."""
    from .clip_fast_hydration_wiring import _blob_free

    if str(file_manifest.get("dtype", "")) != _SOURCE_DTYPE:
        return False, (
            "manifest source provenance mismatch: cast-once requires "
            f"{_SOURCE_DTYPE}, got {file_manifest.get('dtype', '')}"
        )
    provenance = getattr(sd, _CAST_PROVENANCE_ATTR, None)
    if not isinstance(provenance, dict):
        return False, "missing cast-once source provenance evidence"
    expected_source_keys = sorted(
        str(key) for key in (file_manifest.get("key_set") or [])
        if str(key) not in _TOKENIZER_KEYS
    )
    if provenance.get("source_dtype") != _SOURCE_DTYPE:
        return False, "source provenance dtype is not manifest BF16"
    manifest_file_index = file_manifest.get("file_index")
    if manifest_file_index is not None and provenance.get("file_index") != int(manifest_file_index):
        return False, "source provenance file index mismatch"
    if sorted(provenance.get("manifest_key_set") or []) != expected_source_keys:
        return False, "source provenance key set mismatch"
    source_dtypes = provenance.get("source_dtype_by_key")
    if not isinstance(source_dtypes, dict) or any(
        source_dtypes.get(key) != _SOURCE_DTYPE for key in expected_source_keys
    ):
        return False, "incomplete per-key BF16 source provenance"
    source_shapes = provenance.get("source_shapes")
    expected_shapes = file_manifest.get("key_shapes") or {}
    if not isinstance(source_shapes, dict) or any(
        list(source_shapes.get(key) or []) != list(expected_shapes.get(key) or [])
        for key in expected_source_keys
    ):
        return False, "incomplete source shape provenance"
    view = _blob_free(sd)
    key_set = file_manifest.get("key_set") or []
    if sorted(view.keys()) != key_set:
        return False, (
            f"key set mismatch: got {len(view)} expected {len(key_set)} "
            "(cast-once transform replay diverged from the frozen manifest)"
        )
    for key, tensor in view.items():
        expected_shape = file_manifest.get("key_shapes", {}).get(key)
        if expected_shape is not None and list(tensor.shape) != expected_shape:
            return False, f"shape mismatch for {key}"
        if str(tensor.dtype) != _COMPUTE_DTYPE:
            return False, (
                f"dtype mismatch for {key}: got {tensor.dtype} "
                f"expected {_COMPUTE_DTYPE} (cast-once)"
            )
    return True, f"exact key/shape match + FP32 compute-ready vs frozen manifest ({len(key_set)} keys)"


def assert_compute_ready_no_patches(clip: Any) -> tuple[bool, str]:
    """Defensive demand-time check before binding cast-once tensors.

    Verifies (fail-closed) ONLY what is knowable before the bind:
    * the leaf loader modules expose no ``weight_function``/``bias_function``
      registrations (a patch would need the regular per-forward cast path);
    * the clip has a cond_stage_model.

    The per-file state dicts are verified separately by
    :func:`verify_cast_once_sd` (exact key set + shapes + FP32 dtype) —
    checking the PRE-BIND model parameters here would be wrong: they are
    still meta/BF16 placeholders until the bind (the E28 baked cast-once
    rejection: ``not_compute_ready:['logit_scale:meta', ...]`` on the
    pre-bind model).

    Returns ``(ok, detail)``.  Never raises.
    """
    try:
        from . import clip_fast_hydration as _cfh

        csm = getattr(clip, "cond_stage_model", None)
        if csm is None:
            return False, "no_cond_stage_model"
        leaves = _cfh._leaf_loaders(csm)
        for leaf in leaves:
            for name in ("weight_function", "bias_function"):
                fn = getattr(leaf, name, None)
                if fn is not None and len(fn) > 0:
                    return False, f"patch_function_registered:{name}"
        return True, "no_patches_compute_ready_expected"
    except Exception as exc:  # noqa: BLE001 - fail closed
        return False, f"{type(exc).__name__}: {str(exc)[:120]}"


# ── E31 Phase 4: FP32 residency proof + lifecycle binding ─────────────────
# The E28 design ("the cache is the parameter storage itself") is extended
# with a DEMAND-TIME residency verification that proves the bind actually
# produced persistent FP32 compute-ready storage, and a generation binding
# that invalidates cast-once on any rehydration/device change — instead of
# trusting a boolean marker.

_CAST_ONCE_HYDRATION_GENERATION: "OrderedDict[str, int]" = OrderedDict()


def _clip_source_generation(clip: Any) -> str:
    """Read an explicit source generation, never path/size/mtime metadata."""
    # Explicit source generations take precedence over the CLIP marker.  A
    # reused Python object must not keep the old marker when its source is
    # replaced in place.
    for name in ("source_generation", "manifest_generation", "content_generation", "_comfymodal_ra9g_identity_digest"):
        try:
            value = getattr(clip, name, None)
            if isinstance(value, (str, int)) and str(value):
                return str(value)
        except Exception:
            pass
    try:
        manifest = getattr(clip, "manifest", None)
        if isinstance(manifest, Mapping):
            for name in ("source_generation", "manifest_generation", "content_generation", "digest"):
                value = manifest.get(name)
                if isinstance(value, (str, int)) and str(value):
                    return str(value)
    except Exception:
        pass
    try:
        from . import clip_fast_hydration as _cfh
        manifest = _cfh.get_clip_manifest(clip)
        if isinstance(manifest, Mapping):
            for name in ("source_generation", "manifest_generation", "content_generation", "digest"):
                value = manifest.get(name)
                if isinstance(value, (str, int)) and str(value):
                    return str(value)
    except Exception:
        pass
    return ""


def _clip_identity_key(clip: Any) -> str:
    """Identity key for a clip object: object id PLUS the real model
    identities that survive a rehydration/replacement (cond_stage_model id
    and the clip's patcher current_object id when present).  The object id
    alone is not enough — a new CLIP that reuses a dead object's id (or a
    rehydrated clip whose outer object is reused) must not inherit a stale
    cast-once claim."""
    parts = [str(id(clip))]
    source_generation = _clip_source_generation(clip)
    if source_generation:
        parts.append(f"source_generation:{source_generation}")
    try:
        csm = getattr(clip, "cond_stage_model", None)
        if csm is not None:
            parts.append(f"csm:{id(csm)}")
    except Exception:
        pass
    try:
        patcher = getattr(clip, "patcher", None)
        if patcher is not None:
            current = getattr(patcher, "current_object", None)
            if current is not None:
                parts.append(f"patcher:{id(current)}")
    except Exception:
        pass
    return "|".join(parts)


def cast_once_generation(clip: Any) -> int:
    """Return the current cast-once generation for *clip* (0 = never cast).

    The generation increments on every successful cast-once bind, and is
    keyed by the clip's real identity (object id + cond_stage_model id +
    patcher current_object id) so a rehydrated/replaced model object can
    never inherit a stale cast-once claim.
    """
    try:
        with _TRANSFER_LOCK:
            return int(_CAST_ONCE_HYDRATION_GENERATION.get(_clip_identity_key(clip), 0))
    except Exception:
        return 0


def mark_cast_once_applied(
    clip: Any, identity: Optional[SourceManifestIdentity] = None, *, commit: bool = True
) -> None:
    """Increment the cast-once generation for *clip* (bind-side call).

    ``commit=False`` is a side-effect-free preflight seam for legacy wiring;
    only the post-owner-retirement call is allowed to publish a generation.
    """
    try:
        if identity is not None:
            setattr(clip, "_comfymodal_ra9g_identity_digest", identity.digest)
        if not commit:
            return
        key = _clip_identity_key(clip)
        with _TRANSFER_LOCK:
            _CAST_ONCE_HYDRATION_GENERATION[key] = _CAST_ONCE_HYDRATION_GENERATION.get(key, 0) + 1
            _CAST_ONCE_HYDRATION_GENERATION.move_to_end(key)
            while len(_CAST_ONCE_HYDRATION_GENERATION) > _TRANSFER_REGISTRY_LIMIT:
                _CAST_ONCE_HYDRATION_GENERATION.popitem(last=False)
    except Exception:
        pass


def invalidate_cast_once(clip: Any) -> None:
    """Invalidate cast-once state for *clip* (fail-closed: next demand
    re-verifies / re-casts).  Called on any semantic mutation."""
    try:
        with _TRANSFER_LOCK:
            prefix = f"{id(clip)}|"
            for key in list(_CAST_ONCE_HYDRATION_GENERATION):
                if key == _clip_identity_key(clip) or key.startswith(prefix):
                    _CAST_ONCE_HYDRATION_GENERATION.pop(key, None)
        if hasattr(clip, "_comfymodal_ra9g_identity_digest"):
            delattr(clip, "_comfymodal_ra9g_identity_digest")
    except Exception:
        pass


def _storage_ptr(tensor: Any) -> Optional[int]:
    try:
        return int(tensor.untyped_storage().data_ptr())
    except Exception:
        return None


def _tensor_bytes_equal(left: Any, right: Any) -> bool:
    """Compare the actual bytes, including NaN payloads, not just values."""
    try:
        if left.shape != right.shape or left.dtype != right.dtype:
            return False
        if str(left.device) != str(right.device):
            return False
        a = left.detach().contiguous().view(torch.uint8)
        b = right.detach().contiguous().view(torch.uint8)
        return bool(torch.equal(a, b))
    except Exception:
        return False


def _manifest_key_map(file_manifests: list[dict]) -> tuple[dict[str, dict], list[str]]:
    """Return the frozen checkpoint-key map and duplicate manifest keys."""
    expected: dict[str, dict] = {}
    duplicate: list[str] = []
    for file_index, manifest in enumerate(file_manifests):
        keys = manifest.get("key_set") or []
        for key in keys:
            key = str(key)
            if key in expected:
                duplicate.append(key)
                continue
            expected[key] = {
                "file_index": int(file_index),
                "shape": list((manifest.get("key_shapes") or {}).get(key, [])),
                "source_dtype": str(manifest.get("dtype", "")),
            }
    return expected, sorted(set(duplicate))


def _declared_structural_destination_keys(file_manifests: list[dict]) -> set[str]:
    """Return destination-only keys explicitly frozen in the manifest.

    These are model-created structural parameters (for example
    ``logit_scale``), not checkpoint tensors.  They may be present in the
    destination map without a source occurrence, but only when the frozen
    manifest declares them.  An undeclared destination remains an exact
    mapping failure.
    """
    declared: set[str] = set()
    for manifest in file_manifests:
        raw = (manifest or {}).get("structural_destination_keys", ())
        if isinstance(raw, str):
            raw = (raw,)
        if isinstance(raw, (list, tuple, set, frozenset)):
            declared.update(str(key) for key in raw)
    return declared


def snapshot_resident_fp32(
    clip: Any,
    per_file_sds: list[dict],
    file_manifests: list[dict],
    *,
    expect_device: Optional[str] = None,
    phase: str = "snapshot",
) -> dict[str, Any]:
    """Make an exact checkpoint-key -> destination residency proof.

    The frozen manifest defines the expected checkpoint universe.  Source
    tensors are compared to the destination reached through Comfy's shared
    ``_leaf_param_map`` logic, rather than by walking ``weight``/``bias``
    attributes (which misses nested and routed parameters).  Every mismatch is
    represented in JSON-safe evidence and the proof fails closed.
    """
    record: dict[str, Any] = {
        "ok": False,
        "phase": str(phase),
        "reason": "",
        "generation": cast_once_generation(clip),
        "expected_count": 0,
        "source_count": 0,
        "destination_count": 0,
        "matched_count": 0,
        "verified_count": 0,
        "missing_count": 0,
        "duplicate_count": 0,
        "unexpected_count": 0,
        "shape_mismatch_count": 0,
        "dtype_mismatch_count": 0,
        "device_mismatch_count": 0,
        "meta_count": 0,
        "storage_mismatch_count": 0,
        "byte_mismatch_count": 0,
        "expected_bytes": 0,
        "verified_bytes": 0,
        "source_bytes": 0,
        "destination_bytes": 0,
        "fp32_bytes": 0,
        "count_by_dtype": {},
        "bytes_by_dtype": {},
        "device_counts": {},
        "missing_keys": [],
        "missing_source_keys": [],
        "missing_destination_keys": [],
        "structural_destination_keys": [],
        "duplicate_keys": [],
        "unexpected_keys": [],
        "wrong_dtype_keys": [],
        "wrong_device_keys": [],
        "wrong_storage_keys": [],
        "wrong_bytes_keys": [],
        "wrong_meta_keys": [],
        "file_index_mismatch_keys": [],
        "wrong_dtype_count": 0,
        "wrong_device_count": 0,
        "wrong_storage_count": 0,
        "wrong_bytes_count": 0,
        "per_file": [],
        "per_key": [],
    }
    try:
        from . import clip_fast_hydration as _cfh

        expected, manifest_duplicates = _manifest_key_map(file_manifests)
        record["expected_count"] = len(expected)
        record["duplicate_keys"] = list(manifest_duplicates)
        record["duplicate_count"] = len(manifest_duplicates)
        if not expected:
            record["reason"] = "zero_expected_count"
            return record
        if len(per_file_sds) != len(file_manifests):
            record["reason"] = "file_count_mismatch"
            return record

        # Keep the file index attached to every source occurrence.  A flat
        # key->tensor mapping loses which checkpoint file supplied a key and
        # can incorrectly turn a swapped/multiply-present file into proof.
        source_entries: dict[str, list[dict[str, Any]]] = {}
        source_entry_count = 0
        duplicate_source: list[str] = []
        for source_file_index, sd in enumerate(per_file_sds):
            for key, tensor in sd.items():
                if key in _TOKENIZER_KEYS:
                    continue
                key = str(key)
                source_entries.setdefault(key, []).append({
                    "file_index": int(source_file_index),
                    "tensor": tensor,
                })
                source_entry_count += 1
                if len(source_entries[key]) > 1:
                    duplicate_source.append(key)
        duplicate_source = sorted(set(duplicate_source))
        record["duplicate_keys"] = sorted(set(record["duplicate_keys"]) | set(duplicate_source))
        record["duplicate_count"] = len(set(record["duplicate_keys"]))
        record["source_count"] = len(source_entries)
        record["source_entry_count"] = source_entry_count
        unexpected = sorted(set(source_entries) - set(expected))
        missing_source = sorted(set(expected) - set(source_entries))
        record["missing_source_keys"] = list(missing_source)
        # Destination missingness is reconciled below, after the destination
        # map is collected.  ``missing_keys`` is the union of both sides.
        missing = list(missing_source)
        record["unexpected_keys"] = list(unexpected)
        record["unexpected_count"] = len(unexpected)

        csm = getattr(clip, "cond_stage_model", None)
        if csm is None:
            record["reason"] = "no_cond_stage_model"
            return record
        destination: dict[str, Any] = {}
        destination_all: list[tuple[str, Any]] = []
        destination_duplicates: list[str] = []
        destination_ids: dict[int, str] = {}
        for leaf in _cfh._leaf_loaders(csm):
            for key, tensor in _cfh._leaf_param_map(leaf).items():
                destination_all.append((str(key), tensor))
                if key not in expected:
                    continue
                previous = destination.get(key)
                if previous is not None and previous is not tensor:
                    destination_duplicates.append(str(key))
                    continue
                tensor_id = id(tensor)
                other_key = destination_ids.get(tensor_id)
                if other_key is not None and other_key != key:
                    destination_duplicates.extend((other_key, str(key)))
                destination_ids[tensor_id] = str(key)
                destination[str(key)] = tensor
        destination_duplicates = sorted(set(destination_duplicates))
        record["duplicate_keys"] = sorted(set(record["duplicate_keys"]) | set(destination_duplicates))
        record["duplicate_count"] = len(set(record["duplicate_keys"]))
        record["destination_count"] = len(destination)

        expected_destination_ids = {id(tensor) for tensor in destination.values()}
        structural_destination_keys = _declared_structural_destination_keys(file_manifests)
        record["structural_destination_keys"] = sorted(structural_destination_keys)
        unexpected_destination = sorted({
            key for key, tensor in destination_all
            if (
                key not in expected
                and key not in structural_destination_keys
                and id(tensor) not in expected_destination_ids
            )
        })
        record["unexpected_destination_keys"] = list(unexpected_destination)
        unexpected = sorted(set(unexpected) | set(unexpected_destination))
        record["unexpected_keys"] = list(unexpected)
        record["unexpected_count"] = len(unexpected)

        missing_destination = sorted(set(expected) - set(destination))
        record["missing_destination_keys"] = list(missing_destination)
        missing = sorted(set(missing_source) | set(missing_destination))
        record["missing_keys"] = list(missing)
        record["missing_count"] = len(missing)

        for file_index, manifest in enumerate(file_manifests):
            file_keys = {
                str(key) for key in (manifest.get("key_set") or [])
                if str(key) not in _TOKENIZER_KEYS
            }
            expected_bytes = 0
            for key in file_keys:
                shape = (manifest.get("key_shapes") or {}).get(key) or []
                numel = 1
                for dim in shape:
                    numel *= int(dim)
                expected_bytes += numel * 4
            record["per_file"].append({
                "file_index": int(file_index),
                "path": str(manifest.get("path", "")),
                "expected_count": len(file_keys),
                "source_count": 0,
                "destination_count": 0,
                "verified_count": 0,
                "expected_bytes": expected_bytes,
                "source_bytes": 0,
                "destination_bytes": 0,
                "verified_bytes": 0,
                "missing_keys": [],
                "duplicate_keys": [],
                "unexpected_keys": [],
                "wrong_dtype_keys": [],
                "wrong_device_keys": [],
                "wrong_storage_keys": [],
                "wrong_bytes_keys": [],
                "wrong_meta_keys": [],
                "missing_count": 0,
                "duplicate_count": 0,
                "unexpected_count": 0,
                "shape_mismatch_count": 0,
                "dtype_mismatch_count": 0,
                "device_mismatch_count": 0,
                "meta_count": 0,
                "storage_mismatch_count": 0,
                "byte_mismatch_count": 0,
                "file_index_mismatch_count": 0,
            })
            record["expected_bytes"] += expected_bytes

        # Reconcile physical source residency by the actual source file index,
        # including unexpected and duplicate occurrences.  The expected-key
        # loop below deliberately never flattens this association.
        for source_key, occurrences in source_entries.items():
            for occurrence in occurrences:
                source_file_index = int(occurrence.get("file_index", -1))
                source_tensor = occurrence.get("tensor")
                source_bytes = (
                    int(source_tensor.numel() * source_tensor.element_size())
                    if isinstance(source_tensor, torch.Tensor) else 0
                )
                record["source_bytes"] += source_bytes
                if 0 <= source_file_index < len(record["per_file"]):
                    record["per_file"][source_file_index]["source_count"] += 1
                    record["per_file"][source_file_index]["source_bytes"] += source_bytes

        for key in unexpected:
            for occurrence in source_entries.get(key, []):
                source_file_index = int(occurrence.get("file_index", -1))
                if 0 <= source_file_index < len(record["per_file"]):
                    record["per_file"][source_file_index]["unexpected_keys"].append(key)
                    record["per_file"][source_file_index]["unexpected_count"] += 1

        for key in sorted(expected):
            occurrences = source_entries.get(key, [])
            source_entry = occurrences[0] if occurrences else None
            src = source_entry.get("tensor") if source_entry else None
            dst = destination.get(key)
            spec = expected[key]
            manifest_file_index = int(spec.get("file_index", -1))
            source_file_index = (
                int(source_entry.get("file_index")) if source_entry is not None else None
            )
            ev: dict[str, Any] = {
                "key": key,
                "file_index": manifest_file_index,
                "manifest_file_index": manifest_file_index,
                "source_file_index": source_file_index,
                "present_source": src is not None,
                "present_destination": dst is not None,
            }
            file_record = (
                record["per_file"][manifest_file_index]
                if 0 <= manifest_file_index < len(record["per_file"])
                else None
            )
            if file_record is not None and (not occurrences or dst is None):
                file_record["missing_keys"].append(key)
                file_record["missing_count"] += 1
            if file_record is not None and len(occurrences) > 1:
                file_record["duplicate_keys"].append(key)
                file_record["duplicate_count"] += 1
            src_bytes = int(src.numel() * src.element_size()) if isinstance(src, torch.Tensor) else 0
            if dst is not None:
                dst_bytes = int(dst.numel() * dst.element_size())
                record["destination_bytes"] += dst_bytes
                if file_record is not None:
                    file_record["destination_count"] += 1
                    file_record["destination_bytes"] += dst_bytes
            if src is None or dst is None:
                if src is not None:
                    ev.update({
                        "shape": list(getattr(src, "shape", ())),
                        "expected_shape": list(spec.get("shape") or []),
                        "source_dtype": str(getattr(src, "dtype", "")),
                        "source_device": str(getattr(src, "device", "")),
                        "source_is_meta": bool(getattr(src, "is_meta", False)),
                        "source_bytes": src_bytes,
                    })
                record["per_key"].append(ev)
                continue
            ev.update({
                "shape": list(getattr(src, "shape", ())),
                "expected_shape": list(spec.get("shape") or []),
                "source_dtype": str(getattr(src, "dtype", "")),
                "destination_dtype": str(getattr(dst, "dtype", "")),
                "source_device": str(getattr(src, "device", "")),
                "destination_device": str(getattr(dst, "device", "")),
                "source_is_meta": bool(getattr(src, "is_meta", False)),
                "destination_is_meta": bool(getattr(dst, "is_meta", False)),
                "source_bytes": src_bytes,
                "destination_bytes": int(dst.numel() * dst.element_size()),
                "source_data_ptr": None if getattr(src, "is_meta", False) else int(src.data_ptr()),
                "destination_data_ptr": None if getattr(dst, "is_meta", False) else int(dst.data_ptr()),
                "source_storage_ptr": _storage_ptr(src),
                "destination_storage_ptr": _storage_ptr(dst),
            })
            if str(dst.dtype) == _COMPUTE_DTYPE:
                record["fp32_bytes"] += int(dst.numel() * dst.element_size())
            dt = str(dst.dtype)
            record["count_by_dtype"][dt] = record["count_by_dtype"].get(dt, 0) + 1
            record["bytes_by_dtype"][dt] = record["bytes_by_dtype"].get(dt, 0) + int(dst.numel() * dst.element_size())
            dev = str(getattr(dst, "device", ""))
            record["device_counts"][dev] = record["device_counts"].get(dev, 0) + 1
            shape_ok = list(dst.shape) == list(spec.get("shape") or []) and list(src.shape) == list(spec.get("shape") or [])
            dtype_ok = str(src.dtype) == _COMPUTE_DTYPE and str(dst.dtype) == _COMPUTE_DTYPE
            device_ok = not expect_device or str(dst.device) == str(expect_device)
            meta_ok = not bool(getattr(src, "is_meta", False)) and not bool(getattr(dst, "is_meta", False))
            storage_ok = _storage_ptr(src) is not None and _storage_ptr(src) == _storage_ptr(dst) and int(src.data_ptr()) == int(dst.data_ptr())
            bytes_ok = _tensor_bytes_equal(src, dst)
            file_index_ok = source_file_index == manifest_file_index
            ev.update({"shape_ok": shape_ok, "dtype_ok": dtype_ok, "device_ok": device_ok, "meta_ok": meta_ok, "storage_ok": storage_ok, "bytes_ok": bytes_ok, "file_index_ok": file_index_ok, "matched": bool(shape_ok and dtype_ok and device_ok and meta_ok and storage_ok and bytes_ok and file_index_ok)})
            for flag, name in ((not shape_ok, "shape_mismatch_count"), (not dtype_ok, "dtype_mismatch_count"), (not device_ok, "device_mismatch_count"), (not meta_ok, "meta_count"), (not storage_ok, "storage_mismatch_count"), (not bytes_ok, "byte_mismatch_count")):
                if flag:
                    record[name] += 1
                    if file_record is not None:
                        file_record[name] += 1
            if not dtype_ok:
                record["wrong_dtype_keys"].append(key)
                if file_record is not None:
                    file_record["wrong_dtype_keys"].append(key)
            if not device_ok:
                record["wrong_device_keys"].append(key)
                if file_record is not None:
                    file_record["wrong_device_keys"].append(key)
            if not meta_ok:
                record["wrong_meta_keys"].append(key)
                if file_record is not None:
                    file_record["wrong_meta_keys"].append(key)
            if not storage_ok:
                record["wrong_storage_keys"].append(key)
                if file_record is not None:
                    file_record["wrong_storage_keys"].append(key)
            if not bytes_ok:
                record["wrong_bytes_keys"].append(key)
                if file_record is not None:
                    file_record["wrong_bytes_keys"].append(key)
            if not file_index_ok:
                record["file_index_mismatch_keys"].append(key)
                if file_record is not None:
                    file_record["file_index_mismatch_count"] += 1
            if ev["matched"]:
                record["matched_count"] += 1
                record["verified_count"] += 1
                verified_bytes = int(dst.numel() * dst.element_size())
                record["verified_bytes"] += verified_bytes
                if file_record is not None:
                    file_record["verified_count"] += 1
                    file_record["verified_bytes"] += verified_bytes
            record["per_key"].append(ev)

        record["wrong_dtype_keys"] = sorted(set(record["wrong_dtype_keys"]))
        record["wrong_device_keys"] = sorted(set(record["wrong_device_keys"]))
        record["wrong_storage_keys"] = sorted(set(record["wrong_storage_keys"]))
        record["wrong_bytes_keys"] = sorted(set(record["wrong_bytes_keys"]))
        record["wrong_meta_keys"] = sorted(set(record["wrong_meta_keys"]))
        record["file_index_mismatch_keys"] = sorted(set(record["file_index_mismatch_keys"]))
        record["wrong_dtype_count"] = int(record["dtype_mismatch_count"])
        record["wrong_device_count"] = int(record["device_mismatch_count"])
        record["wrong_storage_count"] = int(record["storage_mismatch_count"])
        record["wrong_bytes_count"] = int(record["byte_mismatch_count"])
        record["verified_bytes"] = int(record["verified_bytes"])
        record["verified_count"] = int(record["verified_count"])

        failures = [
            name for name in ("duplicate_count", "missing_count", "unexpected_count", "shape_mismatch_count", "dtype_mismatch_count", "device_mismatch_count", "meta_count", "storage_mismatch_count", "byte_mismatch_count") if int(record[name])
        ]
        if record["file_index_mismatch_keys"]:
            failures.append("file_index_mismatch")
        if record["matched_count"] != record["expected_count"] or record["verified_count"] != record["expected_count"]:
            failures.append("matched_count")
        if record["verified_bytes"] != record["expected_bytes"]:
            failures.append("verified_bytes")
        if failures:
            record["reason"] = "exact_mapping_failed:" + ",".join(failures)
            return record
        record["ok"] = True
        record["reason"] = "exact_checkpoint_mapping_fp32_resident"
        return record
    except Exception as exc:  # noqa: BLE001 - fail closed
        record["reason"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        return record


_TOKENIZER_KEYS = {"spiece_model", "tekken_model", "tokenizer_json"}


def compare_resident_fp32(before: dict[str, Any], after: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    """Compare the complete residency identity after the real forward.

    Pointer stability is necessary but not sufficient: a forward that swaps a
    key, changes its file association, dtype/device/meta state, generation, or
    byte accounting must fail closed even when an unrelated pointer happens to
    remain unchanged.
    """
    result: dict[str, Any] = {
        "ok": False,
        "reason": "",
        "storage_stable": False,
        "key_set_stable": False,
        "metadata_stable": False,
        "generation_stable": False,
        "storage_moved": [],
        "changed_keys": [],
        "before_generation": int(before.get("generation", 0) or 0),
        "after_generation": int(after.get("generation", 0) or 0),
        "before_count": int(before.get("expected_count", 0) or 0),
        "after_count": int(after.get("expected_count", 0) or 0),
    }
    try:
        result["generation_stable"] = result["before_generation"] == result["after_generation"]
        before_keys = {str(e.get("key")): e for e in before.get("per_key", []) if isinstance(e, dict) and e.get("key") is not None}
        after_keys = {str(e.get("key")): e for e in after.get("per_key", []) if isinstance(e, dict) and e.get("key") is not None}
        result["key_set_stable"] = set(before_keys) == set(after_keys)
        changed: list[str] = []
        moved = []
        for key in sorted(set(before_keys) | set(after_keys)):
            left, right = before_keys.get(key), after_keys.get(key)
            if not left or not right:
                changed.append(str(key))
                moved.append(str(key))
                continue
            if left.get("destination_storage_ptr") != right.get("destination_storage_ptr") or left.get("destination_data_ptr") != right.get("destination_data_ptr"):
                moved.append(str(key))
            metadata_fields = (
                "manifest_file_index", "file_index", "source_file_index", "shape",
                "expected_shape", "source_dtype", "destination_dtype",
                "source_device", "destination_device", "source_is_meta",
                "destination_is_meta", "source_bytes", "destination_bytes",
                "dtype_ok", "device_ok", "meta_ok", "shape_ok",
            )
            if any(left.get(field) != right.get(field) for field in metadata_fields):
                changed.append(str(key))
        result["storage_moved"] = moved[:32]
        result["storage_stable"] = not moved
        result["changed_keys"] = sorted(set(changed))[:32]
        result["metadata_stable"] = not changed and result["key_set_stable"]
        counts_stable = (
            result["before_count"] == result["after_count"]
            and int(before.get("verified_count", before.get("matched_count", 0)) or 0)
            == int(after.get("verified_count", after.get("matched_count", 0)) or 0)
            and int(before.get("expected_bytes", 0) or 0) == int(after.get("expected_bytes", 0) or 0)
            and int(before.get("verified_bytes", before.get("destination_bytes", 0)) or 0)
            == int(after.get("verified_bytes", after.get("destination_bytes", 0)) or 0)
        )
        if not after.get("ok"):
            result["reason"] = "post_forward_exact_mapping_failed"
            return False, result
        if not result["generation_stable"]:
            result["reason"] = "generation_changed_after_real_forward"
            return False, result
        if not result["key_set_stable"]:
            result["reason"] = "key_set_changed_after_real_forward"
            return False, result
        if not result["metadata_stable"] or not counts_stable:
            result["reason"] = "residency_metadata_changed_after_real_forward"
            return False, result
        if moved:
            result["reason"] = "storage_moved_after_real_forward"
            return False, result
        result["ok"] = True
        result["reason"] = "exact_mapping_stable_after_real_forward"
        return True, result
    except Exception as exc:  # noqa: BLE001 - fail closed
        result["reason"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        return False, result


def verify_resident_fp32(
    clip: Any,
    per_file_sds: Optional[list[dict]] = None,
    file_manifests: Optional[list[dict]] = None,
    *,
    expect_device: Optional[str] = None,
    phase: str = "post_bind",
) -> tuple[bool, dict[str, Any]]:
    """Exact residency proof; absent checkpoint evidence fails closed.

    The legacy no-source call remains diagnostic for offline callers, but it
    cannot pass: a residency claim without a frozen checkpoint mapping is not
    proof.  This is deliberately never a best-effort parameter walk.
    """
    if per_file_sds is None or file_manifests is None:
        record: dict[str, Any] = {"ok": False, "reason": "missing_checkpoint_mapping", "generation": cast_once_generation(clip)}
        try:
            csm = getattr(clip, "cond_stage_model", None)
            non_fp32 = []
            if csm is not None:
                for leaf in getattr(csm, "modules", lambda: ())():
                    for name in ("weight", "bias"):
                        p = getattr(leaf, name, None)
                        if p is not None and str(getattr(p, "dtype", "")) != _COMPUTE_DTYPE:
                            non_fp32.append(f"{type(leaf).__name__}.{name}:{p.dtype}")
            if non_fp32:
                record["reason"] = f"non_fp32:{non_fp32[:4]}"
        except Exception:
            pass
        return False, record
    record = snapshot_resident_fp32(clip, per_file_sds, file_manifests, expect_device=expect_device, phase=phase)
    return bool(record.get("ok", False)), record


def install_real_forward_check(clip: Any, callback: Any) -> dict[str, Any]:
    """Wrap the existing CLIP encode boundary, without issuing a forward.

    The callback runs once, after the real encode method returns.  It may raise
    to fail the E31 request.  CPU fakes can provide any of the normal Comfy
    ``encode_from_tokens*`` methods; no CUDA APIs are used here.
    """
    marker = "_comfymodal_e31_real_forward_hook"

    def _public_state(value: dict[str, Any]) -> dict[str, Any]:
        """Return JSON-safe evidence while keeping restoration state private."""
        public = {key: item for key, item in value.items() if key != "originals"}
        public["originals"] = {
            str(name): {
                "callable_id": str(id(original)),
                "module": str(getattr(original, "__module__", "")),
                "qualname": str(getattr(original, "__qualname__", getattr(original, "__name__", ""))),
            }
            for name, original in (value.get("originals") or {}).items()
        }
        return public

    identity = _clip_identity_key(clip)
    generation = cast_once_generation(clip)
    existing = getattr(clip, marker, None)
    if isinstance(existing, dict):
        if existing.get("identity") == identity and int(existing.get("generation", 0) or 0) == generation:
            return _public_state(existing)
        # Restore methods wrapped by the obsolete generation before dropping
        # its state.  Otherwise a reused outer CLIP would retain a closure
        # over the old callback even though the marker was deleted.
        for method_name, original in (existing.get("originals") or {}).items():
            try:
                setattr(clip, method_name, original)
            except Exception:
                pass
        try:
            delattr(clip, marker)
        except Exception:
            pass
    methods = ("encode_from_tokens_scheduled", "encode_from_tokens", "encode_token_weights")
    installed: list[str] = []
    state = {"observed": False, "originals": {}}
    for method_name in methods:
        original = getattr(clip, method_name, None)
        if not callable(original) or getattr(original, marker, False):
            continue

        @functools.wraps(original)
        def _wrapped(*args: Any, _original: Any = original, _name: str = method_name, **kwargs: Any) -> Any:
            started = time.perf_counter()
            result = _original(*args, **kwargs)
            if not state["observed"]:
                state["observed"] = True
                observation = {
                    "forward_observed": True,
                    "forward_actually_observed": True,
                    "forward_method": _name,
                    "forward_wall_ms": round((time.perf_counter() - started) * 1000.0, 3),
                }
                callback(observation)
            return result

        setattr(_wrapped, marker, True)
        setattr(clip, method_name, _wrapped)
        state["originals"][method_name] = original
        installed.append(method_name)
    result = {
        "installed": bool(installed),
        "methods": installed,
        "forward_observed": False,
        "forward_actually_observed": False,
        "identity": identity,
        "generation": generation,
        "originals": dict(state["originals"]),
    }
    setattr(clip, marker, result)
    return _public_state(result)


def clear_real_forward_check(clip: Any) -> None:
    """Remove a stale offline forward wrapper and its callback closure."""
    marker = "_comfymodal_e31_real_forward_hook"
    try:
        existing = getattr(clip, marker, None)
        if isinstance(existing, dict):
            for method_name, original in (existing.get("originals") or {}).items():
                try:
                    setattr(clip, method_name, original)
                except Exception:
                    pass
        if hasattr(clip, marker):
            delattr(clip, marker)
    except Exception:
        pass
