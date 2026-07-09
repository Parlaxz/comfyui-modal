"""Local-side experiment runner.

Owns the per-checkpoint worker loop. One checkpoint is processed by one
worker_invocation; a checkpoint is never split across workers. The actual
remote execution is delegated to a `_RemoteInvoker` implementation
(LocalRemoteInvoker wraps the existing modal_client.run_prompt_stream
surface; the future comfyapp.py run_checkpoint_stream will provide a
single-invocation implementation that satisfies the same protocol).

Conventions:
- Every event appended to the journal includes (experiment_id, revision,
  journal sequence, event_id, checkpoint_id, cell_key, attempt_id,
  worker_invocation_id, payload).
- "Expensive prefix" = (workflow_hash, triple_id, lora_selection_id). The
  runner passes `expensive_prefix_changed=True|False` to the invoker on
  each call; the invoker uses it to decide whether to reload models/LoRAs.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Protocol

from worker_control import (
    ControlBackend,
    ModalDictControlBackend,
    control_key,
)


# ── Module-level helpers ──────────────────────────────────────────────────

_NODE_DIR = os.path.dirname(os.path.abspath(__file__))

# Supported MIME types and extensions for experiment i2i images
_SUPPORTED_IMAGE_MIMES = frozenset({
    "image/png", "image/jpeg", "image/webp", "image/gif", "image/bmp",
})

_SUPPORTED_IMAGE_EXTS = frozenset({
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp",
})


def _ext_to_mime(ext: str) -> str:
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
    }.get(ext.lower(), "image/png")


def _validate_image_mime(mime: str) -> None:
    """Raise ValueError if MIME type is not supported for experiment i2i."""
    if mime not in _SUPPORTED_IMAGE_MIMES:
        raise ValueError(
            f"Unsupported input image MIME type: {mime!r}. "
            f"Supported: {', '.join(sorted(_SUPPORTED_IMAGE_MIMES))}"
        )


def _build_remote_input_payload(
    content_hash: str,
    blob_bytes: bytes,
    mime: str,
    ext: str,
    remote_filename: str,
    node_id: str,
    field: str,
) -> dict:
    """Build the canonical experiment-cell input-image payload.

    Returns a dict with every field needed by the remote materializer:
      - data (base64-encoded bytes)
      - content_hash
      - original_filename
      - mime_type
      - extension
      - node_id
      - field

    The returned dict is stored under cell['input_images'][remote_filename].
    """
    import base64 as _b64
    return {
        "data": _b64.b64encode(blob_bytes).decode("ascii"),
        "content_hash": content_hash,
        "original_filename": f"exp_input_{content_hash[:8]}{ext}",
        "mime_type": mime,
        "extension": ext,
        "node_id": node_id,
        "field": field,
    }


def _resolve_preset_image(content_hash: str) -> dict | None:
    """Resolve a content-addressed preset image blob.

    Returns a dict with:
        "bytes": bytes (binary data)
        "mime": str (MIME type)
        "ext": str (file extension, e.g. '.png')
        "path": str (local filesystem path)
    or None if the blob is missing.

    Raises ValueError on hash mismatch (blob found but SHA-256 does not
    match the requested *content_hash*).
    """
    if not content_hash:
        return None
    from presets import blob_path_for
    for ext in sorted(_SUPPORTED_IMAGE_EXTS):
        blob = blob_path_for(root=_NODE_DIR, content_hash=content_hash, file_ext=ext)
        if blob and blob.exists():
            data = blob.read_bytes()
            actual_hash = hashlib.sha256(data).hexdigest()
            if actual_hash != content_hash:
                raise ValueError(
                    f"Content hash mismatch for blob {blob.name}: "
                    f"expected {content_hash}, got {actual_hash}"
                )
            return {"bytes": data, "mime": _ext_to_mime(ext), "ext": ext, "path": str(blob)}
    return None


# ── Workflow injection (authoritative resolve_and_inject_cell) ────────────

@dataclass
class ResolvedCellExecution:
    """Fully resolved cell with all values injected into the workflow.

    Fields capture every value that was injected (or left as workflow-owned)
    so the runner and remote invoker can log, trace, and forward them.
    """
    workflow: dict
    workflow_hash: str
    positive_prompt: str
    negative_prompt: str
    unet: str
    clip: str
    vae: str
    lora_chain: list[dict]
    sampler: str
    scheduler: str
    steps: int
    guidance: float
    denoise: float
    seed: int
    width: int
    height: int
    resolved_axis: dict  # actual values after injection (captures workflow-owned)
    input_image: dict | None = None
    input_image_info: dict | None = None
    output_policy: dict = field(default_factory=dict)


def _find_slot_by_category(profile_slots: dict, category: str) -> dict | None:
    """Return the first slot entry matching the given category key.

    ``profile_slots`` is a ``{category_name: {node_id, field, path}}`` dict
    (the profile's ``slots`` field from ``comparison.py``).
    """
    slot = profile_slots.get(category)
    if slot and isinstance(slot, dict) and slot.get("node_id"):
        return slot
    return None


def _get_slots_by_category(profile_slots: dict, category_prefix: str) -> list[dict]:
    """Return all slot entries whose category key starts with a given prefix."""
    return [
        v for k, v in profile_slots.items()
        if isinstance(v, dict) and v.get("node_id") and k.startswith(category_prefix)
    ]


def _set_path_value(workflow: dict, slot: dict, value: Any) -> None:
    """Set *value* at the path described by *slot* in *workflow*.

    *slot* must have ``node_id`` and ``path`` (e.g. ``["inputs", "text"]``).
    """
    node_id = slot.get("node_id", "")
    path = slot.get("path", ["inputs", slot.get("field", "")])
    if not node_id or not path:
        return
    node = workflow.get(node_id)
    if not isinstance(node, dict):
        return
    target = node
    for segment in path[:-1]:
        if isinstance(target, dict) and segment in target:
            target = target[segment]
        else:
            return
    if isinstance(target, dict) and path[-1] in target:
        target[path[-1]] = value


def _validate_path(workflow: dict, node_id: str, path: list,
                   slot_key: str, profile_id: str) -> None:
    """Validate that *path* resolves in the workflow node. Raises
    ``MissingMappedField`` or ``InvalidMappedPath`` on failure."""
    node = workflow.get(node_id)
    if not isinstance(node, dict):
        raise MissingMappedNode(
            f"profile {profile_id!r}: {slot_key} slot node {node_id!r} "
            f"not found in workflow",
            profile_id=profile_id, node_id=node_id,
        )
    current = node
    for segment in path:
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        else:
            raise InvalidMappedPath(
                f"profile {profile_id!r}: {slot_key} slot path "
                f"{' > '.join(str(p) for p in path)} cannot be resolved "
                f"in node {node_id!r}: segment {segment!r} not found",
                profile_id=profile_id, node_id=node_id,
                field=str(segment),
            )


def _set_field(workflow: dict, node_id: str, field: str, value: Any) -> None:
    """Set ``workflow[node_id].inputs[field] = value``, creating inputs if needed."""
    node = workflow.get(node_id)
    if not isinstance(node, dict):
        return
    inputs = node.setdefault("inputs", {})
    if isinstance(inputs, dict):
        inputs[field] = value


def _workflow_sha256(workflow: dict) -> str:
    normalized = json.dumps(workflow, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def resolve_and_inject_cell(
    profile_workflow: dict,
    profile_slots: dict,
    loader_target_groups: list[dict],
    lora_slots: list[dict],
    cell: dict,
    preset_resolver: Callable[[str], dict | None] | None = None,
) -> ResolvedCellExecution:
    """Resolve and inject one cell's values into the profile workflow.

    Parameters
    ----------
    profile_workflow:
        The API-format workflow dict to mutate (a deep copy is made internally).
    profile_slots:
        Flat ``{category: {node_id, field, path}}`` dict from the profile.
    loader_target_groups:
        List of loader group dicts, each with ``id``, ``unet``, ``clip``, ``vae``.
    lora_slots:
        List of LoRA slot dicts, each with ``slot_index``, ``lora_node_id``,
        ``lora_field``, ``model_strength_node_id/field``, ``clip_strength_node_id/field``.
    cell:
        The experiment cell dict from the matrix compiler output.
    preset_resolver:
        Optional ``Callable[[content_hash], dict|None]`` that returns an image
        descriptor ``{"path": ..., "bytes": ..., "mime": ...}`` or ``None``.

    Returns
    -------
    ResolvedCellExecution with the fully injected workflow and extracted values.
    """
    from matrix_compiler import is_workflow_owned, resolve_axis_value

    wf = copy.deepcopy(profile_workflow)
    axis_values = cell.get("axis_values", {})
    triple = cell.get("triple", {})
    profile_id = cell.get("profile_id", "")

    # ── D2: Preflight mapping validation before any injection ──────
    # Validate prompt slot exists
    pos_slot = _find_slot_by_category(profile_slots, "prompt")
    if not pos_slot:
        raise MissingPromptSlot(
            f"profile {profile_id!r} has no prompt slot mapping configured",
            profile_id=profile_id,
        )
    # Validate prompt slot node exists in workflow
    pos_node_id = str(pos_slot.get("node_id", ""))
    if pos_node_id not in wf:
        raise MissingMappedNode(
            f"profile {profile_id!r}: prompt slot node {pos_node_id!r} "
            f"not found in workflow",
            profile_id=profile_id, node_id=pos_node_id,
        )
    # Validate prompt slot path
    pos_path = pos_slot.get("path", [])
    if pos_path:
        _validate_path(wf, pos_node_id, pos_path, "prompt", profile_id)

    # Validate negative prompt slot if cell has a negative value
    neg_prompt = cell.get("negative_prompt", "")
    if not is_workflow_owned(neg_prompt) and neg_prompt is not None:
        neg_slot = _find_slot_by_category(profile_slots, "negative_prompt")
        if neg_slot:
            neg_node_id = str(neg_slot.get("node_id", ""))
            if neg_node_id not in wf:
                raise MissingMappedNode(
                    f"profile {profile_id!r}: negative_prompt slot node "
                    f"{neg_node_id!r} not found in workflow",
                    profile_id=profile_id, node_id=neg_node_id,
                )
            neg_path = neg_slot.get("path", [])
            if neg_path:
                _validate_path(wf, neg_node_id, neg_path, "negative_prompt", profile_id)

    # Validate loader target group
    group_id = cell.get("loader_target_group_id", "g_default")
    if loader_target_groups:
        group = next((g for g in loader_target_groups if g.get("id") == group_id), None)
        if group is None:
            available = ", ".join(g.get("id", "?") for g in loader_target_groups)
            raise MissingLoaderTargetGroup(
                f"profile {profile_id!r}: loader_target_group {group_id!r} "
                f"not found. Available groups: {available}",
                profile_id=profile_id, group_id=group_id,
            )

    # Validate LoRA slots
    lora_signature = cell.get("lora_signature", []) or []
    if lora_signature and not lora_slots:
        raise MissingLoRASlot(
            f"profile {profile_id!r}: cell has {len(lora_signature)} LoRA entry(ies) "
            f"but profile has no lora_slots configured",
            profile_id=profile_id,
        )
    if len(lora_signature) > len(lora_slots):
        raise InvalidLoRASlotCapacity(
            f"profile {profile_id!r}: cell has {len(lora_signature)} LoRA entries "
            f"but profile has only {len(lora_slots)} slot(s)",
            profile_id=profile_id,
        )

    # ── 1. Inject prompt ───────────────────────────────────────────
    if pos_slot:
        _set_path_value(wf, pos_slot, cell.get("prompt", ""))

    # ── 2. Inject negative prompt ──────────────────────────────────
    # D2: Heuristic fallback (CLIPTextEncode scan) removed from execution
    # path.  Only the explicit negative_prompt slot is used.  The mapping
    # assistant UI still has heuristics for auto-detection.
    neg_prompt = cell.get("negative_prompt", "")
    if is_workflow_owned(neg_prompt):
        pass  # Don't touch the workflow's existing negative prompt
    elif neg_prompt is not None:  # includes explicit empty string
        neg_slot = _find_slot_by_category(profile_slots, "negative_prompt")
        if neg_slot:
            _set_path_value(wf, neg_slot, neg_prompt)
        else:
            raise MissingNegativePromptSlot(
                f"profile {profile_id!r}: cell has explicit negative prompt but "
                f"profile has no negative_prompt slot configured",
                profile_id=profile_id,
            )

    # ── 3. Inject model triple into loader target group ────────────
    group_id = cell.get("loader_target_group_id", "g_default")
    group = next((g for g in loader_target_groups if g.get("id") == group_id), None)
    if group is None:
        if loader_target_groups:
            # Groups exist but requested one is not found — that's an error
            available = ", ".join(g.get("id", "?") for g in loader_target_groups)
            raise ValueError(
                f"loader_target_group {group_id!r} not found. "
                f"Available groups: {available}"
            )
        # No groups configured at all — skip triple injection
    if group:
        for category in ("unet", "clip", "vae"):
            entries = group.get(category, []) or []
            value = str(triple.get(category, "")) if triple.get(category) else ""
            for entry in entries:
                nid = entry.get("node_id", "")
                field = entry.get("field", "")
                if nid and field:
                    _set_field(wf, nid, field, value)

    # ── 4. Inject LoRA chain ───────────────────────────────────────
    lora_signature = cell.get("lora_signature", []) or []
    for idx, lora_entry in enumerate(lora_signature):
        file_name = str(lora_entry[0]) if len(lora_entry) > 0 else ""
        model_str = float(lora_entry[1]) if len(lora_entry) > 1 else 0.0
        clip_str = float(lora_entry[2]) if len(lora_entry) > 2 else 0.0
        if idx < len(lora_slots):
            slot = lora_slots[idx]
            if slot.get("lora_node_id") and slot.get("lora_field"):
                _set_field(wf, slot["lora_node_id"], slot["lora_field"], file_name)
            if slot.get("model_strength_node_id") and slot.get("model_strength_field"):
                _set_field(wf, slot["model_strength_node_id"], slot["model_strength_field"], model_str)
            if slot.get("clip_strength_node_id") and slot.get("clip_strength_field"):
                _set_field(wf, slot["clip_strength_node_id"], slot["clip_strength_field"], clip_str)
    # Clear remaining unused lora slots (set strength to 0 to bypass)
    for idx in range(len(lora_signature), len(lora_slots)):
        slot = lora_slots[idx]
        if slot.get("model_strength_node_id") and slot.get("model_strength_field"):
            _set_field(wf, slot["model_strength_node_id"], slot["model_strength_field"], 0.0)
        if slot.get("clip_strength_node_id") and slot.get("clip_strength_field"):
            _set_field(wf, slot["clip_strength_node_id"], slot["clip_strength_field"], 0.0)

    # ── 5. Inject sampler values ───────────────────────────────────
    for axis_key, slot_key in [
        ("seed", "seed"),
        ("steps", "steps"),
        ("guidance", "guidance"),
        ("sampler", "sampler"),
        ("scheduler", "scheduler"),
        ("denoise", "denoise"),
    ]:
        val = resolve_axis_value(axis_values, axis_key)
        if val is not None:
            # Coerce types
            if axis_key in ("seed", "steps"):
                val = int(val)
            elif axis_key in ("guidance", "denoise"):
                val = float(val)
            else:
                val = str(val)
            slot = _find_slot_by_category(profile_slots, slot_key)
            if slot:
                _set_path_value(wf, slot, val)

    # ── 6. Inject resolution ───────────────────────────────────────
    resolution = axis_values.get("resolution")
    if not is_workflow_owned(resolution) and isinstance(resolution, (list, tuple)) and len(resolution) == 2:
        width, height = int(resolution[0]), int(resolution[1])
        w_slot = _find_slot_by_category(profile_slots, "width")
        h_slot = _find_slot_by_category(profile_slots, "height")
        if w_slot:
            _set_path_value(wf, w_slot, width)
        if h_slot:
            _set_path_value(wf, h_slot, height)

    # ── 7. Inject input image (i2i) ────────────────────────────────
    input_image_data = None
    image_hash = cell.get("input_image_hash", "")
    if image_hash and preset_resolver is not None:
        resolved = preset_resolver(image_hash)
        if resolved is None:
            raise ValueError(
                f"Preset image blob not found for content hash {image_hash!r}. "
                "Upload the image to a preset before running the experiment."
            )
        if isinstance(resolved, dict):
            # Verify content hash before proceeding
            blob_bytes = resolved.get("bytes")
            if blob_bytes:
                actual_hash = hashlib.sha256(blob_bytes).hexdigest()
                if actual_hash != image_hash:
                    raise ValueError(
                        f"Content hash mismatch for input image: "
                        f"expected {image_hash}, got {actual_hash}"
                    )
            # Validate MIME type before proceeding
            mime = resolved.get("mime", "image/png")
            ext = resolved.get("ext", ".png")
            _validate_image_mime(mime)

            input_image_data = resolved
            load_slot = _find_slot_by_category(profile_slots, "input_image")

            # Build canonical remote filename: exp_<hash_prefix><ext>
            remote_filename = f"exp_{image_hash[:12]}{ext}"

            # Inject the REMOTE filename into the workflow (not the local path)
            if load_slot:
                _set_path_value(wf, load_slot, remote_filename)

            # Build canonical payload on the cell for remote transfer
            node_id = load_slot.get("node_id", "") if load_slot else ""
            field = load_slot.get("field", "") if load_slot else ""
            payload = _build_remote_input_payload(
                content_hash=image_hash,
                blob_bytes=resolved["bytes"],
                mime=mime,
                ext=ext,
                remote_filename=remote_filename,
                node_id=node_id,
                field=field,
            )
            cell["input_images"] = {remote_filename: payload}

    # ── 8. Read back actual resolved values ─────────────────────────
    resolved_axis: dict[str, Any] = {}
    for axis_key, slot_key in [
        ("seed", "seed"), ("steps", "steps"), ("guidance", "guidance"),
        ("sampler", "sampler"), ("scheduler", "scheduler"), ("denoise", "denoise"),
    ]:
        slot = _find_slot_by_category(profile_slots, slot_key)
        if slot:
            nid = slot.get("node_id", "")
            field = slot.get("field", "")
            actual = wf.get(nid, {}).get("inputs", {}).get(field, "")
            resolved_axis[axis_key] = actual
        else:
            resolved_axis[axis_key] = axis_values.get(axis_key, "")

    # Read back width/height
    w_slot = _find_slot_by_category(profile_slots, "width") or _find_slot_by_category(profile_slots, "latent_image")
    h_slot = _find_slot_by_category(profile_slots, "height") or _find_slot_by_category(profile_slots, "latent_image")
    if w_slot:
        resolved_axis["width"] = wf.get(w_slot.get("node_id", ""), {}).get("inputs", {}).get(w_slot.get("field", ""), 0)
    if h_slot:
        resolved_axis["height"] = wf.get(h_slot.get("node_id", ""), {}).get("inputs", {}).get(h_slot.get("field", ""), 0)

    # Read back actual triple values after injection
    group_id = cell.get("loader_target_group_id", "g_default")
    resolved_axis["unet"] = str(triple.get("unet", ""))
    resolved_axis["clip"] = str(triple.get("clip", ""))
    resolved_axis["vae"] = str(triple.get("vae", ""))

    # Read back actual LoRA chain after injection
    resolved_axis["lora_chain"] = [
        {"file": e[0], "model_strength": float(e[1]) if len(e) > 1 else 0.0,
         "clip_strength": float(e[2]) if len(e) > 2 else 0.0}
        for e in (cell.get("lora_signature") or [])
    ]

    # ── 10. Compute workflow hash & build result ───────────────────
    wf_hash = _workflow_sha256(wf)

    return ResolvedCellExecution(
        workflow=wf,
        workflow_hash=wf_hash,
        positive_prompt=cell.get("prompt", ""),
        negative_prompt=cell.get("negative_prompt", ""),
        unet=str(triple.get("unet", "")),
        clip=str(triple.get("clip", "")),
        vae=str(triple.get("vae", "")),
        lora_chain=resolved_axis["lora_chain"],
        sampler=str(resolve_axis_value(axis_values, "sampler") or ""),
        scheduler=str(resolve_axis_value(axis_values, "scheduler") or ""),
        steps=int(resolve_axis_value(axis_values, "steps") or 0),
        guidance=float(resolve_axis_value(axis_values, "guidance") or 0.0),
        denoise=float(resolve_axis_value(axis_values, "denoise") or 0.0),
        seed=int(resolve_axis_value(axis_values, "seed") or 0),
        width=int(resolve_axis_value(axis_values, "width") or 0),
        height=int(resolve_axis_value(axis_values, "height") or 0),
        resolved_axis=resolved_axis,
        input_image=input_image_data,
        output_policy=cell.get("output_policy", {}),
    )


# ── Structured mapping error classes ──────────────────────────────────────

class MappingError(LookupError):
    """Base class for all preflight mapping validation errors."""
    def __init__(self, message: str, *, profile_id: str = "",
                 group_id: str = "", node_id: str = "", field: str = ""):
        self.profile_id = profile_id
        self.group_id = group_id
        self.node_id = node_id
        self.field = field
        super().__init__(message)


class MissingLoaderTargetGroup(MappingError):
    """Raised when a cell references a loader_target_group that does not exist
    in the profile's group list."""


class MissingMappedNode(MappingError):
    """Raised when a slot references a node_id that does not exist in the
    profile workflow."""


class MissingMappedField(MappingError):
    """Raised when a slot references a field that does not exist on the
    mapped node."""


class InvalidMappedPath(MappingError):
    """Raised when the slot path cannot be resolved against the workflow node."""


class MissingPromptSlot(MappingError):
    """Raised when no prompt slot is configured on the profile."""


class MissingNegativePromptSlot(MappingError):
    """Raised when a negative is provided but no negative_prompt slot exists."""


class MissingImageSlot(MappingError):
    """Raised when an input image is needed but no input_image slot exists."""


class MissingLoRASlot(MappingError):
    """Raised when a cell has LoRA entries but the profile has no lora_slots."""


class InvalidLoRASlotCapacity(MappingError):
    """Raised when a cell has more LoRA entries than the profile has slots."""


# ── Public types ─────────────────────────────────────────────────────────

class ExperimentRunnerError(RuntimeError):
    pass


@dataclass(frozen=True)
class CheckpointRequest:
    checkpoint_id: str
    profile_id: str
    loader_target_group_id: str
    workflow_hash: str
    workflow: dict
    triple: dict


@dataclass
class CheckpointStreamEvent:
    type: str
    payload: dict = field(default_factory=dict)


# ── _RemoteInvoker protocol ──────────────────────────────────────────────

class _RemoteInvoker(Protocol):
    """Protocol for the remote executor. Implemented by LocalRemoteInvoker
    in production; tests use a FakeInvoker."""

    async def open_worker(self, worker_invocation_id: str, checkpoint_id: str,
                          profile_id: str, workflow: dict, triple: dict) -> None: ...

    async def run_cell(self, worker_invocation_id: str, cell: dict) -> dict: ...

    async def close_worker(self, worker_invocation_id: str) -> None: ...

    async def cancel_worker(self, worker_invocation_id: str) -> None: ...

    async def request_pause(self, worker_invocation_id: str) -> None: ...

    async def request_stop_after_current(self, worker_invocation_id: str) -> None: ...


# ── ExperimentRunner ─────────────────────────────────────────────────────

class ExperimentRunner:
    def __init__(self, *, store, leases, invoker, compilation, max_containers: int = 1) -> None:
        if not isinstance(compilation, dict):
            raise ExperimentRunnerError("compilation must be a dict")
        self._store = store
        self._leases = leases
        self._invoker = invoker
        self._compilation = compilation
        self._max_containers = max_containers
        self._stop_event = asyncio.Event()
        self._stop_mode: str = ""  # "stop_now" or ""
        self._pause_requested: bool = False  # set by scheduler.pause()
        # Phase 11: track active workers so stop_now can cancel them
        self._active_workers: dict[str, str] = {}  # worker_invocation_id -> checkpoint_id
        if not compilation.get("cells"):
            return  # nothing to do
        if max_containers < 1:
            raise ExperimentRunnerError("max_containers must be >= 1")

    async def stop_now(self) -> None:
        self._stop_mode = "stop_now"
        self._stop_event.set()
        exp_id = self._compilation.get("experiment_id", "")
        # ── Fix: atomically invalidate all active leases BEFORE cancel.
        #     This creates a cancellation boundary: any late events
        #     arriving at validate_and_accept will be rejected because
        #     the lease status is no longer "claimed" and the generation
        #     has been bumped.
        for wid, ck_id in list(self._active_workers.items()):
            try:
                self._leases.invalidate(exp_id, ck_id)
            except Exception as exc:
                print(f"[comfyui-modal] invalidate lease for {ck_id} failed: {exc}")
        # Phase 5: cancel all active workers (writes stop_now control)
        for wid in list(self._active_workers.keys()):
            try:
                await self._invoker.cancel_worker(wid)
            except Exception as exc:
                print(f"[comfyui-modal] cancel_worker({wid}) failed: {exc}")

    async def request_pause(self) -> None:
        """Set control state to pause_after_current for each active worker."""
        for wid in list(self._active_workers.keys()):
            try:
                await self._invoker.request_pause(wid)
            except Exception:
                pass

    async def request_stop_after_current(self) -> None:
        """Set control state to stop_after_current for each active worker."""
        for wid in list(self._active_workers.keys()):
            try:
                await self._invoker.request_stop_after_current(wid)
            except Exception:
                pass

    async def run(self) -> dict:
        if not self._compilation.get("cells"):
            return {"completed": 0, "failed": 0, "interrupted": 0}

        await self._emit("experiment.started", {
            "experiment_id": self._compilation["experiment_id"],
            "revision": self._compilation["revision"],
            "total_cells": len(self._compilation["cells"]),
        })

        # Group cells by checkpoint
        cells_by_ck: dict[str, list] = {}
        for cell in self._compilation["cells"]:
            cells_by_ck.setdefault(cell["checkpoint_id"], []).append(cell)

        # Schedule checkpoints up to max_containers concurrently
        sem = asyncio.Semaphore(self._max_containers)
        tasks = []
        for ck in self._compilation["checkpoints"]:
            tasks.append(asyncio.create_task(
                self._run_checkpoint(ck, cells_by_ck[ck["id"]], sem)))

        # Wait for all to settle (Stop now will cause early return via the
        # _stop_event check inside _run_checkpoint)
        await asyncio.gather(*tasks, return_exceptions=True)

        # ── Fix: tally from visible snapshot state (cell_visible), not raw
        #     event counts.  This ensures failed→successful retries count as
        #     completed only (not completed+failed), superseded attempts are
        #     excluded, and counts never exceed total cells.
        total_cells = len(self._compilation.get("cells", []))
        snap = self._store.rebuild_snapshot(total_cells=total_cells)
        counters = snap.get("counters", {})
        completed = counters.get("completed", 0)
        failed = counters.get("failed", 0)
        interrupted = counters.get("interrupted", 0)
        await self._emit("experiment.stopped" if self._stop_mode else "experiment.completed", {
            "completed": completed,
            "failed": failed,
            "interrupted": interrupted,
            "total_cells": total_cells,
        })
        return {"completed": completed, "failed": failed, "interrupted": interrupted, "total_cells": total_cells}

    async def _run_checkpoint(self, ck: dict, cells: list, sem: asyncio.Semaphore) -> None:
        async with sem:
            worker_invocation_id = f"w_{uuid.uuid4().hex[:8]}"
            # Identity values used throughout, including finally cleanup.
            # Initialise early so the finally block can access them.
            dep_gen = self._compilation.get("deployment_generation", "")
            exp_id = self._compilation.get("experiment_id", "")
            ck_id = ck["id"]
            lease_generation = 0
            try:
                lease = self._leases.claim(exp_id, ck["id"], worker_invocation_id)
                worker_invocation_id = lease["worker_invocation_id"]
                lease_generation = lease["lease_generation"]
                # Phase 11: track active worker for stop_now cancellation
                self._active_workers[worker_invocation_id] = ck["id"]

                # ── Phase 2: pre-generate ALL attempt IDs and persist ──
                attempt_ids_by_cell: dict = {}
                for cell in cells:
                    attempt_id = f"a_{uuid.uuid4().hex[:8]}"
                    attempt_ids_by_cell[cell.get("cell_key", "")] = attempt_id
                    cell["attempt_id"] = attempt_id
                    await self._emit("cell.attempt_created", {
                        "exp_id": exp_id,
                        "cell_key": cell.get("cell_key", ""),
                        "checkpoint_id": ck["id"],
                        "lease_generation": lease_generation,
                        "worker_invocation_id": worker_invocation_id,
                        "attempt_id": attempt_id,
                    })
                # All attempt-created events are now durable before remote begins

                await self._emit("checkpoint.claimed", {
                    "checkpoint_id": ck["id"],
                    "lease_generation": lease_generation,
                    "worker_invocation_id": worker_invocation_id,
                })

                # ── Phase 3: resolve and inject cell values with real i2i image resolver ──
                profile_slots = ck.get("slots", {})
                loader_target_groups = ck.get("loader_target_groups", [])
                lora_slots = ck.get("lora_slots", [])
                for cell in cells:
                    resolved = resolve_and_inject_cell(
                        profile_workflow=ck.get("workflow", {}),
                        profile_slots=profile_slots,
                        loader_target_groups=loader_target_groups,
                        lora_slots=lora_slots,
                        cell=cell,
                        preset_resolver=_resolve_preset_image,
                    )
                    cell["_resolved_workflow"] = resolved.workflow
                    # Also add resolved values for the remote invoker
                    cell["_resolved_prompt"] = resolved.positive_prompt
                    cell["_resolved_negative"] = resolved.negative_prompt
                    cell["_resolved_unet"] = resolved.unet
                    cell["_resolved_clip"] = resolved.clip
                    cell["_resolved_vae"] = resolved.vae
                    cell["_resolved_lora_chain"] = resolved.lora_chain
                    # input_images is already built inside resolve_and_inject_cell.
                    # The canonical payload lives at cell["input_images"]; it is
                    # consumed directly by LocalRemoteInvoker.run_cell and the
                    # remote-side run_checkpoint_stream / _materialize_input_images.
                    # Remove any stale _input_images field from a previous version.
                    cell.pop("_input_images", None)
                    cell.pop("_input_image_b64", None)
                    cell.pop("_input_image_mime", None)

                # If the invoker is a CheckpointStreamInvoker, configure
                # it with the full cell list so the deployed side can run
                # the entire checkpoint inside one Modal invocation.
                if hasattr(self._invoker, "configure_checkpoint"):
                    self._invoker.configure_checkpoint(
                        checkpoint_id=ck["id"],
                        lease_generation=lease_generation,
                        experiment_id=self._compilation.get("experiment_id", ""),
                        revision=self._compilation.get("revision", 0),
                        deployment_generation=self._compilation.get("deployment_generation", ""),
                        workflow=ck.get("workflow", {}),
                        triple=ck.get("triple", {}),
                        lora_chain=ck.get("lora_chain", {}),
                        cells=cells,
                    )
                await self._invoker.open_worker(
                    worker_invocation_id, ck["id"], ck["profile_id"],
                    workflow=ck.get("workflow", {}),
                    triple=ck["triple"],
                )
                ck_failures = 0
                ck_completed = 0
                prev_prefix: tuple | None = None
                for cell in cells:
                    if self._stop_event.is_set():
                        # ── Fix: do not emit local cell.interrupted here.
                        #     Remaining cells stay pending (no terminal event).
                        #     The validated terminal-event path (invoker
                        #     cancellation, control backend, or stream event
                        #     sink) handles any required interruption recording.
                        continue
                    prefix = (cell.get("workflow_hash", ""),
                              cell.get("triple_id", ""),
                              cell.get("lora_selection_id", ""))
                    expensive_prefix_changed = (prev_prefix != prefix)
                    prev_prefix = prefix
                    attempt_id = cell.get("attempt_id", f"a_{uuid.uuid4().hex[:8]}")
                    result = await self._invoker.run_cell(worker_invocation_id, cell)
                    # Fix B: terminal events (cell.completed, cell.failed,
                    # cell.interrupted) are emitted ONLY by the stream
                    # event sink (_on_remote_event) when using the
                    # CheckpointStreamInvoker. We keep only the counters
                    # for the checkpoint-level summary emit below.
                    if result.get("status") == "completed":
                        ck_completed += 1
                    elif result.get("status") == "interrupted":
                        pass
                    else:
                        ck_failures += 1
                # Determine checkpoint completion type
                if self._pause_requested:
                    final_type = "checkpoint.paused"
                elif self._stop_mode == "stop_now":
                    final_type = "checkpoint.stopped"
                elif ck_failures > 0:
                    final_type = "checkpoint.completed_with_failures"
                else:
                    final_type = "checkpoint.completed"
                await self._emit(final_type, {
                    "checkpoint_id": ck["id"],
                    "completed": ck_completed,
                    "failed": ck_failures,
                    "lease_generation": lease_generation,
                    "worker_invocation_id": worker_invocation_id,
                })
            except Exception as exc:
                await self._emit("checkpoint.failed_fatal", {
                    "checkpoint_id": ck["id"],
                    "error": str(exc),
                })
            finally:
                self._active_workers.pop(worker_invocation_id, None)
                try:
                    self._leases.release(exp_id, ck_id, worker_invocation_id)
                except Exception:
                    pass
                try:
                    await self._invoker.close_worker(worker_invocation_id)
                except Exception:
                    pass
                # Clear shared control record for this worker after
                # terminal completion so stale pause/stop records do
                # not leak to future invocations.  The 5-component
                # identity ensures we only clear THIS invocation's
                # control record.
                if hasattr(self._invoker, "_control_backend"):
                    try:
                        await self._invoker._control_backend.clear_control(
                            dep_gen, exp_id, ck_id,
                            worker_invocation_id, lease_generation,
                        )
                    except Exception:
                        pass

    async def _emit(self, event_type: str, payload: dict) -> None:
        ev = self._store.append_event({
            "type": event_type,
            "payload": payload,
        })
        # In a real runner, also send via PromptServer.send_sync here.
        # Tests verify the journal append; UI integration is Phase 9.


# ── LocalRemoteInvoker (production wrapper) ─────────────────────────────

class LocalRemoteInvoker:
    """Production implementation of _RemoteInvoker. Wraps the existing
    modal_client.run_prompt_stream surface."""

    def __init__(self, modal_run_prompt_stream):
        self._run_prompt_stream = modal_run_prompt_stream

    async def open_worker(self, worker_invocation_id, checkpoint_id, profile_id,
                          workflow, triple) -> None:
        return None

    async def run_cell(self, worker_invocation_id, cell) -> dict:
        try:
            # Extract canonical input_images payload dict.
            # In the new format, values are dicts with "data" key for base64.
            # Convert to the simpler {filename: b64data} dict that run_prompt_stream expects.
            raw = cell.get("input_images") or {}
            flat = {}
            for filename, entry in raw.items():
                if isinstance(entry, dict) and "data" in entry:
                    flat[filename] = entry["data"]
                elif isinstance(entry, str):
                    flat[filename] = entry
            result = await self._run_prompt_stream(
                workflow=cell.get("_resolved_workflow", cell.get("_workflow", {})),
                input_images=flat if flat else None,
            )
            return {"status": "completed", "result": result}
        except Exception as exc:
            return {"status": "failed", "error": str(exc)}

    async def close_worker(self, worker_invocation_id) -> None:
        return None

    async def cancel_worker(self, worker_invocation_id) -> None:
        return None

    async def request_pause(self, worker_invocation_id: str) -> None:
        return None

    async def request_stop_after_current(self, worker_invocation_id: str) -> None:
        return None


# ── CheckpointStreamInvoker (real single-invocation) ─────────────────────

class CheckpointStreamInvoker:
    """Production implementation of _RemoteInvoker that calls the
    deployed-side ``run_checkpoint_stream`` method. The Modal container
    stays alive for the entire checkpoint; cells are streamed back as
    events. The runner's `run_cell` calls are routed into one open
    per-checkpoint generator; events are forwarded to the runner via a
    per-worker asyncio.Queue that the runner drains.

    Fix E: all state is per-worker (``self._workers[worker_id]``) so
    that multiple concurrent checkpoints do not overwrite each other.

    Uses a ``ControlBackend`` instance (default ``ModalDictControlBackend``)
    for shared pause/stop coordination visible to both local and remote code.
    """

    def __init__(self, run_checkpoint_stream, *, experiment_id="",
                 stream_event_sink=None, control_backend=None):
        """``stream_event_sink`` is an optional async callable that
        receives every event yielded by the deployed primitive. The
        runner may use it to forward events to a journal or to the
        PromptServer event bridge.

        ``experiment_id`` is the owning experiment; it is used to key
        control records in the shared backend so that control for one
        experiment never affects another.

        ``control_backend`` is the shared backend instance; defaults to
        ``ModalDictControlBackend()`` for production. Tests inject
        ``FakeDictControlBackend``.
        """
        self._run_checkpoint_stream = run_checkpoint_stream
        self._experiment_id = experiment_id
        self._stream_event_sink = stream_event_sink
        self._control_backend: ControlBackend = (
            control_backend if control_backend is not None else ModalDictControlBackend()
        )
        # Per-worker state dict: worker_id -> dict
        self._workers: dict[str, dict] = {}
        # Payloads stored by checkpoint_id in configure_checkpoint,
        # claimed by open_worker to avoid races (Fix E).
        self._pending_payloads: dict[str, dict] = {}

    # ── Internal helpers ──────────────────────────────────────────

    def _worker_payload(self, worker_invocation_id: str) -> dict:
        """Return the payload dict for a worker, or empty dict."""
        w = self._workers.get(worker_invocation_id)
        if w is not None and w.get("payload"):
            return w["payload"]
        return {}

    def _derive_identity(self, worker_invocation_id: str) -> tuple:
        """Return the 5-component identity tuple (deployment_generation,
        experiment_id, checkpoint_id, worker_invocation_id, lease_generation)
        for use with ``control_key()`` and backend methods."""
        payload = self._worker_payload(worker_invocation_id)
        return (
            payload.get("deployment_generation", ""),
            payload.get("experiment_id", self._experiment_id),
            payload.get("checkpoint_id", ""),
            worker_invocation_id,
            payload.get("lease_generation", 0),
        )

    # ── Worker lifecycle ──────────────────────────────────────────

    async def open_worker(self, worker_invocation_id, checkpoint_id, profile_id,
                          workflow, triple) -> None:
        payload = self._pending_payloads.pop(checkpoint_id, None)
        self._workers[worker_invocation_id] = {
            "payload": payload,
            "drive_task": None,
            "queue": asyncio.Queue(),
            "cancelled": False,
            "generator": None,
        }

    async def _drive(self, worker_invocation_id, checkpoint_id,
                     lease_generation, workflow, triple, lora_chain, cells):
        """Internal helper: iterate the deployed generator and dispatch
        events to the per-worker queue and the optional event sink.

        Goal 5: enriches ``cell.completed`` events with complete resolved
        cell metadata so that ``_on_remote_event`` and run history have
        every value without depending on later lookups.
        """
        w = self._workers.get(worker_invocation_id)
        if w is None:
            return
        # Extract run metadata from the payload so experiment_id, revision,
        # and deployment_generation flow through to the remote call.
        payload = w.get("payload") or {}
        exp_id = payload.get("experiment_id", self._experiment_id)
        revision = payload.get("revision", 0)
        deployment_generation = payload.get("deployment_generation", "")

        # Goal 5: pre-build a cell-key -> resolved-metadata lookup so we
        # can enrich every cell.completed event without linear scanning.
        _cell_meta: dict[str, dict] = {}
        for c in cells:
            if not isinstance(c, dict):
                continue
            ck = c.get("cell_key", "")
            if not ck:
                continue
            ax = c.get("axis_values", {}) or {}
            resolution = ax.get("resolution", [0, 0]) or [0, 0]
            _cell_meta[ck] = {
                "prompt": c.get("_resolved_prompt", c.get("prompt", "")),
                "negative_prompt": c.get("_resolved_negative", c.get("negative_prompt", "")),
                "seed": ax.get("seed", 0),
                "steps": ax.get("steps", 0),
                "guidance": ax.get("guidance", 0.0),
                "sampler": ax.get("sampler", ""),
                "scheduler": ax.get("scheduler", ""),
                "denoise": ax.get("denoise", 1.0),
                "width": int(resolution[0]) if len(resolution) > 0 else 0,
                "height": int(resolution[1]) if len(resolution) > 1 else 0,
                "unet": c.get("_resolved_unet", ""),
                "clip": c.get("_resolved_clip", ""),
                "vae": c.get("_resolved_vae", ""),
                "lora_chain": c.get("_resolved_lora_chain", []),
                "workflow_hash": c.get("workflow_hash", ""),
                # B7: deployment-wide metadata
                "deployment_generation": deployment_generation,
                "revision": revision,
                "output_policy": c.get("output_policy", {}),
            }

        gen = self._run_checkpoint_stream(
            checkpoint_id=checkpoint_id,
            worker_invocation_id=worker_invocation_id,
            lease_generation=lease_generation,
            workflow=workflow,
            triple=triple,
            lora_chain=lora_chain,
            cells=cells,
            experiment_id=exp_id,
            revision=revision,
            deployment_generation=deployment_generation,
        )
        w["generator"] = gen
        try:
            async for event in gen:
                et = event.get("type", "")
                data = event.get("data", {}) or {}
                cell_key = data.get("cell_key", "")

                # Goal 5: enrich cell.completed events with resolved metadata
                if et == "cell.completed" and cell_key in _cell_meta:
                    for mk, mv in _cell_meta[cell_key].items():
                        data.setdefault(mk, mv)

                if self._stream_event_sink is not None:
                    try:
                        await self._stream_event_sink(event)
                    except Exception:
                        pass

                if et == "cell.completed":
                    await w["queue"].put(
                        (cell_key, "completed", data)
                    )
                elif et == "cell.failed":
                    await w["queue"].put(
                        (cell_key, "failed", data)
                    )
                elif et == "cell.interrupted":
                    await w["queue"].put(
                        (cell_key, "interrupted", data)
                    )
                elif et == "checkpoint.completed":
                    await w["queue"].put(
                        ("__done__", "checkpoint_completed", data)
                    )
                    return
        except asyncio.CancelledError:
            if w["generator"] is not None:
                try:
                    await w["generator"].aclose()
                except Exception:
                    pass
                w["generator"] = None
            raise
        except Exception as exc:
            try:
                await w["queue"].put(
                    ("__done__", "checkpoint_failed", {"error": str(exc)})
                )
            except Exception:
                pass
        finally:
            w["generator"] = None

    async def run_cell(self, worker_invocation_id, cell) -> dict:
        w = self._workers.get(worker_invocation_id)
        if w is None:
            return {"status": "interrupted", "cell_key": cell.get("cell_key", "")}
        q = w["queue"]
        if w["drive_task"] is None:
            payload = w["payload"]
            if payload is None:
                return {"status": "completed", "result": None}
            w["drive_task"] = asyncio.create_task(
                self._drive(
                    worker_invocation_id,
                    payload["checkpoint_id"],
                    payload["lease_generation"],
                    payload["workflow"],
                    payload["triple"],
                    payload.get("lora_chain", {}),
                    payload["cells"],
                )
            )
        if w["cancelled"]:
            return {"status": "interrupted", "cell_key": cell.get("cell_key", "")}
        # Loop until we receive either the matching cell_key event or a terminal sentinel.
        # Never return "pending" — _run_checkpoint would count that as a failure.
        target_key = cell.get("cell_key", "")
        while True:
            cell_key, status, data = await q.get()
            if cell_key == "__done__":
                return {"status": status, "data": data}
            if cell_key == target_key:
                return {"status": status, "data": data}
            # Mismatched event: put it back and try again.
            await q.put((cell_key, status, data))

    async def close_worker(self, worker_invocation_id) -> None:
        """Clean up a worker.  Cancels the drive task and clears the
        shared control record so stale pause/stop state does not leak."""
        # Derive identity BEFORE popping — _derive_identity reads worker payload.
        ident = self._derive_identity(worker_invocation_id)
        w = self._workers.pop(worker_invocation_id, None)
        if w is None:
            return
        dt = w.get("drive_task")
        if dt is not None and not dt.done():
            dt.cancel()
            try:
                await dt
            except (asyncio.CancelledError, Exception):
                pass
        # Clear control record after terminal completion
        try:
            await self._control_backend.clear_control(*ident)
        except Exception:
            pass

    # ── Control methods (exposed invoker API) ─────────────────────

    async def request_pause(self, worker_invocation_id: str) -> None:
        """Set control to pause_after_current with full 5-component identity."""
        dep_gen, exp_id, ck_id, wid, lease_gen = self._derive_identity(worker_invocation_id)
        await self._control_backend.set_control(dep_gen, exp_id, ck_id, wid, lease_gen, "pause_after_current")

    async def request_stop_after_current(self, worker_invocation_id: str) -> None:
        """Set control to stop_after_current with full 5-component identity."""
        dep_gen, exp_id, ck_id, wid, lease_gen = self._derive_identity(worker_invocation_id)
        await self._control_backend.set_control(dep_gen, exp_id, ck_id, wid, lease_gen, "stop_after_current")

    async def cancel_worker(self, worker_invocation_id) -> None:
        """Cancel the remote Modal generator (Fix F).

        Sets the local cancelled flag, writes stop_now control with
        full 5-component identity, cancels the drive task, closes the
        remote generator, and clears the control record so stale state
        does not leak.
        """
        w = self._workers.get(worker_invocation_id)
        if w is None:
            return
        w["cancelled"] = True
        dep_gen, exp_id, ck_id, wid, lease_gen = self._derive_identity(worker_invocation_id)
        # Write stop_now control with full identity
        try:
            await self._control_backend.set_control(dep_gen, exp_id, ck_id, wid, lease_gen, "stop_now")
        except Exception:
            pass
        # Cancel the drive task so the async-for loop is interrupted.
        dt = w.get("drive_task")
        if dt is not None and not dt.done():
            dt.cancel()
        # Close the remote generator explicitly.
        gen = w.get("generator")
        if gen is not None:
            try:
                await gen.aclose()
            except Exception:
                pass
            w["generator"] = None
        # Push a sentinel so any blocked run_cell call returns.
        await w["queue"].put(("__done__", "cancelled", {}))
        # Clear control record after cancellation cleanup.
        try:
            await self._control_backend.clear_control(
                dep_gen, exp_id, ck_id, wid, lease_gen
            )
        except Exception:
            pass

    # ── Payload configuration ─────────────────────────────────────

    def configure_checkpoint(self, **payload) -> None:
        """Store the cell list and metadata that ``run_checkpoint_stream``
        needs.  Must be called before the first ``run_cell`` for the
        checkpoint.

        Fix E: stored by checkpoint_id so multiple concurrent checkpoints
        do not overwrite each other.

        The payload is extended with experiment_id, revision, and
        deployment_generation so that ``_drive`` can forward them to the
        remote call.
        """
        ck_id = str(payload.get("checkpoint_id", ""))
        if ck_id:
            enriched = dict(payload)
            enriched.setdefault("experiment_id", self._experiment_id)
            enriched.setdefault("revision", 0)
            enriched.setdefault("deployment_generation", "")
            self._pending_payloads[ck_id] = enriched
