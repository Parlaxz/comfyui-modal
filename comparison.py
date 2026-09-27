"""Comparison Runner — profile management, mapping assistant, execution."""

import copy
import hashlib
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COMPARISON_DIRNAME = "comparison_profiles"

# Slot keys the system knows about
SLOT_KEYS = (
    "prompt",
    "negative_prompt",
    "seed",
    "steps",
    "guidance",
    "width",
    "height",
    "input_image",
    "sampler",
    "scheduler",
    "denoise",
    "unet_loader",
    "clip_loader",
    "vae_loader",
    "lora_loader",
    "lora_strength_model",
    "lora_strength_clip",
)

PROFILE_SCHEMA_VERSION = 2


class SubprofileError(ValueError):
    """Raised when a subprofile id is duplicated or otherwise invalid."""


class LoRASlotError(ValueError):
    """Raised when a LoRA selection is structurally invalid."""

# Node-class → slot heuristics
_CLASS_HEURISTICS: dict[str, list[tuple[str, str]]] = {
    # (slot_key, input_field)
    "CLIPTextEncode":        [("prompt", "text")],
    "CLIPTextEncodeFlux":    [("prompt", "text")],
    "T5TextEncode":          [("prompt", "text")],
    "Conditioning":          [("prompt", "conditioning_text")],  # rarely used directly
    "KSampler":              [("seed", "seed"), ("steps", "steps"), ("guidance", "cfg")],
    "KSamplerAdvanced":      [("seed", "seed"), ("steps", "steps"), ("guidance", "cfg")],
    "SamplerCustomAdvanced": [("seed", "noise_seed")],
    "RandomNoise":           [("seed", "noise_seed")],
    "BasicScheduler":        [("steps", "steps")],
    "FluxGuidance":          [("guidance", "guidance")],
    "CFGGuider":             [("guidance", "cfg")],
    "EmptyLatentImage":      [("width", "width"), ("height", "height")],
    "EmptySD3LatentImage":   [("width", "width"), ("height", "height")],
    "LoadImage":             [("input_image", "image")],
    # New: sampler/scheduler/denoise axes
    "KSampler": [
        ("seed", "seed"), ("steps", "steps"), ("guidance", "cfg"),
        ("sampler", "sampler"), ("scheduler", "scheduler"), ("denoise", "denoise"),
    ],
    "KSamplerAdvanced": [
        ("seed", "noise_seed"), ("sampler", "sampler"),
        ("scheduler", "scheduler"), ("denoise", "denoise"),
    ],
    "FluxGuidance": [("guidance", "guidance"), ("denoise", "denoise")],
    # New: loader categories (each can have multiple instances in a workflow)
    "UNETLoader": [("unet_loader", "unet_name")],
    "CLIPLoader": [("clip_loader", "clip_name")],
    "DualCLIPLoader": [("clip_loader", "clip_name1")],
    "TripleCLIPLoader": [("clip_loader", "clip_name1")],
    "VAELoader": [("vae_loader", "vae_name")],
    # New: LoRA slot chain
    "LoraLoader": [
        ("lora_loader", "lora_name"),
        ("lora_strength_model", "strength_model"),
        ("lora_strength_clip", "strength_clip"),
    ],
    "LoraLoaderModelOnly": [
        ("lora_loader", "lora_name"),
        ("lora_strength_model", "strength_model"),
    ],
}

# Title tag patterns  e.g.  @prompt  @seed  @width  @height  @input_image
_TAG_PATTERN = re.compile(r"@(\w+)")


def _default_comparison_config() -> dict:
    return {
        "execution_mode": "sequential",
        "max_parallel_jobs": 2,
        "last_seed_mode": "locked",
        "last_width": 1024,
        "last_height": 1024,
    }


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _profiles_root(comfyui_root: str) -> str:
    """Return the directory where comparison profiles are stored."""
    p = os.path.join(comfyui_root, "user", "default", "comfy-modal", COMPARISON_DIRNAME)
    os.makedirs(p, exist_ok=True)
    return p


def _profile_dir(profiles_root: str, profile_id: str) -> str:
    return os.path.join(profiles_root, profile_id)


def _profile_path(profiles_root: str, profile_id: str) -> str:
    return os.path.join(_profile_dir(profiles_root, profile_id), "profile.json")


def _workflow_api_path(profiles_root: str, profile_id: str) -> str:
    return os.path.join(_profile_dir(profiles_root, profile_id), "workflow_api.json")


def _workflow_ui_path(profiles_root: str, profile_id: str) -> str:
    return os.path.join(_profile_dir(profiles_root, profile_id), "workflow.json")


def _adapter_path(profiles_root: str, profile_id: str) -> str:
    return os.path.join(_profile_dir(profiles_root, profile_id), "adapter.json")


def _comparisons_root(comfyui_root: str) -> str:
    p = os.path.join(comfyui_root, "output", "modal", "comparisons")
    os.makedirs(p, exist_ok=True)
    return p


def _comparison_dir(comparisons_root: str, comparison_id: str) -> str:
    return os.path.join(comparisons_root, comparison_id)


# ---------------------------------------------------------------------------
# Workflow hashing
# ---------------------------------------------------------------------------

def _workflow_sha256(workflow: dict) -> str:
    """Canonical workflow identity hash.

    This is a workflow *identity* function, not a byte-level hash.
    Delegates to ``production_workflow._canonical_workflow_hash`` so there
    is one canonical implementation across the project.
    """
    from production_workflow import _canonical_workflow_hash
    return _canonical_workflow_hash(workflow)


# ---------------------------------------------------------------------------
# Model stack extraction (reimplements workflow_metadata.extract_model_stack
# locally so that comparison.py has no import coupling)
# ---------------------------------------------------------------------------

_LOADER_MAPPINGS: dict[str, tuple[str, str]] = {
    "CheckpointLoaderSimple": ("checkpoint", "ckpt_name"),
    "CheckpointLoader": ("checkpoint", "ckpt_name"),
    "UNETLoader": ("unet", "unet_name"),
    "CLIPLoader": ("clip", "clip_name"),
    "DualCLIPLoader": ("clip", "clip_name1"),
    "VAELoader": ("vae", "vae_name"),
    "LoraLoader": ("lora", "lora_name"),
    "LoraLoaderModelOnly": ("lora", "lora_name"),
    "ControlNetLoader": ("controlnet", "control_net_name"),
    "IPAdapterModelLoader": ("ipadapter", "ipadapter_model_name"),
}


def _extract_model_stack(workflow: dict) -> dict:
    stack: dict = {}
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        cls = node.get("class_type", "")
        mapping = _LOADER_MAPPINGS.get(cls)
        if mapping is None:
            continue
        bucket, field = mapping
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        val = inputs.get(field)
        if isinstance(val, str) and val:
            stack.setdefault(bucket, []).append(val)
    # Normalise clip into a flat list
    clips = []
    for key in ("clip",):
        for val in stack.pop(key, []):
            if val not in clips:
                clips.append(val)
    if clips:
        stack["clip"] = clips
    return {
        "checkpoint": stack.get("checkpoint", []),
        "unet": stack.get("unet", []),
        "clip": stack.get("clip", []),
        "vae": stack.get("vae", []),
        "lora": stack.get("lora", []),
        "controlnet": stack.get("controlnet", []),
        "ipadapter": stack.get("ipadapter", []),
    }


# ---------------------------------------------------------------------------
# Format normalisation (UI workflow → API format for detection)
# ---------------------------------------------------------------------------

def _ensure_api_format(workflow: dict) -> dict:
    """Convert a workflow dict to the flat API format ``{node_id: {class_type, inputs, _meta}}``
    regardless of whether the input is UI workflow format or API format.

    UI workflow format (from ``app.graphToPrompt().workflow``)::

        {"nodes": [{"id": 6, "type": "CLIPTextEncode", "title": "...",
                     "inputs": [{"name": "text", "link": null}],
                     "widgets_values": ["hello"]}], ...}

    API format (from ``app.graphToPrompt().output``)::

        {"6": {"class_type": "CLIPTextEncode", "inputs": {"text": "hello"}}}
    """
    # Detect UI format: has a top-level "nodes" list
    nodes_raw = workflow.get("nodes") if isinstance(workflow, dict) else None
    if isinstance(nodes_raw, list):
        result: dict[str, dict] = {}
        for node in nodes_raw:
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("id") or "")
            if not node_id:
                continue
            class_type = node.get("type", "")
            title = node.get("title", "") or ""
            # Build inputs dict from the inputs array + widgets_values
            inputs: dict = {}
            inp_list = node.get("inputs")
            if isinstance(inp_list, list):
                wv = node.get("widgets_values")
                wv_list = wv if isinstance(wv, list) else []
                wi = 0  # widget index
                for inp in inp_list:
                    if not isinstance(inp, dict):
                        continue
                    name = inp.get("name", "")
                    if not name:
                        continue
                    link = inp.get("link")
                    if link is not None:
                        # Connected input — store link marker (no value)
                        inputs[name] = None
                    else:
                        # Widget input — read from widgets_values
                        if wi < len(wv_list):
                            inputs[name] = wv_list[wi]
                            wi += 1
                        else:
                            inputs[name] = None
            node_entry: dict = {
                "class_type": class_type,
                "inputs": inputs,
                "_meta": {"title": title} if title else {},
            }
            result[node_id] = node_entry
        return result

    # Already API format — just ensure _meta.title is surfaced
    result = {}
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        title = ""
        _meta = node.get("_meta")
        if isinstance(_meta, dict):
            title = _meta.get("title", "") or ""
        node_title = node.get("title", "")
        if node_title:
            title = title or node_title
        result[node_id] = {
            "class_type": node.get("class_type", ""),
            "inputs": node.get("inputs", {}),
            "_meta": {"title": title} if title else {},
        }
    return result


# ---------------------------------------------------------------------------
# Slot auto-detection
# ---------------------------------------------------------------------------

def _detect_slots_from_title_tags(workflow: dict) -> dict:
    """Detect slots by scanning node titles for @tag patterns."""
    detected: dict[str, list[dict]] = {}
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        title = (node.get("_meta", {}) or {}).get("title", "") or node.get("title", "")
        if not title:
            continue
        tags = _TAG_PATTERN.findall(title.lower())
        if not tags:
            continue
        for tag in tags:
            if tag not in SLOT_KEYS:
                continue
            # Find a suitable input field
            inputs = node.get("inputs", {})
            if not isinstance(inputs, dict):
                continue
            if tag == "input_image":
                field = "image"
            elif tag in ("width", "height", "steps", "seed", "guidance", "cfg"):
                field = tag if tag != "cfg" else "cfg"
            elif tag == "resolution":
                field = "width"
            else:
                field = "text"
            if field == "cfg":
                field = "cfg"
            if field not in inputs:
                # try common alternatives
                candidates = {
                    "seed": ["seed", "noise_seed"],
                    "steps": ["steps"],
                    "guidance": ["cfg", "guidance"],
                    "width": ["width"],
                    "height": ["height"],
                }
                found_field = None
                for candidate in candidates.get(field, []):
                    if candidate in inputs:
                        found_field = candidate
                        break
                if not found_field:
                    # Still tag a reasonable slot so the user can adjust
                    first_input = next(iter(inputs.keys()), None)
                    if first_input is None:
                        continue
                    found_field = first_input
                field = found_field
            entry = {
                "node_id": str(node_id),
                "class_type": node.get("class_type", ""),
                "title": title,
                "field": field,
                "path": ["inputs", field],
                "reason": f"@{tag} tag",
            }
            detected.setdefault(tag, []).append(entry)
    return detected


def _detect_slots_from_class(workflow: dict) -> dict:
    """Detect slots by node class type heuristics."""
    detected: dict[str, list[dict]] = {}
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        cls = node.get("class_type", "")
        heuristics = _CLASS_HEURISTICS.get(cls, [])
        if not heuristics:
            continue
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        title = (node.get("_meta", {}) or {}).get("title", "") or node.get("title", "")
        for slot_key, field in heuristics:
            if field in inputs:
                entry = {
                    "node_id": str(node_id),
                    "class_type": cls,
                    "title": title,
                    "field": field,
                    "path": ["inputs", field],
                    "reason": f"{cls}.{field}",
                }
                detected.setdefault(slot_key, []).append(entry)
    return detected


def _detect_slots_from_title_text(workflow: dict) -> dict:
    """Detect slots by scanning node titles (non-tag text search)."""
    detected: dict[str, list[dict]] = {}
    trigger_words: dict[str, list[str]] = {
        "prompt": ["prompt", "positive"],
        "negative_prompt": ["negative"],
        "seed": ["seed"],
        "steps": ["steps", "step"],
        "guidance": ["guidance", "cfg"],
        "width": ["width"],
        "height": ["height"],
        "input_image": ["input image", "input_image", "upload image"],
    }
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        title = ((node.get("_meta", {}) or {}).get("title", "") or node.get("title", "") or "").lower()
        if not title:
            continue
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        for slot_key, words in trigger_words.items():
            if not any(w in title for w in words):
                continue
            if slot_key == "negative_prompt":
                field = "text"
            elif slot_key == "input_image":
                field = "image"
            elif slot_key in ("width", "height"):
                field = slot_key
            elif slot_key in ("guidance",):
                field = "cfg" if "cfg" in inputs else "guidance"
            elif slot_key == "seed":
                field = "seed" if "seed" in inputs else "noise_seed"
            else:
                field = "text"
            if field not in inputs:
                continue
            entry = {
                "node_id": str(node_id),
                "class_type": node.get("class_type", ""),
                "title": title,
                "field": field,
                "path": ["inputs", field],
                "reason": f'title contains "{title}"',
            }
            detected.setdefault(slot_key, []).append(entry)
    return detected


def detect_slots(workflow: dict) -> dict:
    """Auto-detect slot candidates across all strategies.

    Accepts either API-format (``{node_id: {class_type, inputs}}``) or
    UI-format (``{"nodes": [...]}``) workflows.

    Returns a dict like  {slot_key: [candidate, ...]}.
    """
    workflow = _ensure_api_format(workflow)

    # Priority 1: title tags (@prompt, @seed, etc.)
    by_tags = _detect_slots_from_title_tags(workflow)
    # Priority 2: class heuristics
    by_class = _detect_slots_from_class(workflow)
    # Priority 3: title text match
    by_title = _detect_slots_from_title_text(workflow)

    merged: dict[str, list[dict]] = {}
    # Tags first (highest priority)
    for key in SLOT_KEYS:
        merged[key] = list(by_tags.get(key, []))
    # Append class-based candidates not already present
    for key in SLOT_KEYS:
        existing_ids = {e["node_id"] for e in merged[key]}
        for candidate in by_class.get(key, []):
            if candidate["node_id"] not in existing_ids:
                merged[key].append(candidate)
                existing_ids.add(candidate["node_id"])
    # Append title-text candidates not already present
    for key in SLOT_KEYS:
        existing_ids = {e["node_id"] for e in merged[key]}
        for candidate in by_title.get(key, []):
            if candidate["node_id"] not in existing_ids:
                merged[key].append(candidate)
    return merged


# ---------------------------------------------------------------------------
# Capabilities inference
# ---------------------------------------------------------------------------

def _infer_capabilities(adapter: dict, workflow: dict) -> dict:
    slots = adapter.get("slots", {})
    has_img2img = bool(slots.get("input_image") and slots["input_image"].get("node_id"))
    return {
        "txt2img": True,
        "img2img": has_img2img,
        "supports_negative_prompt": bool(slots.get("negative_prompt") and slots["negative_prompt"].get("node_id")),
        "supports_resolution_override": bool(slots.get("width") and slots["width"].get("node_id")),
        "supports_steps_override": bool(slots.get("steps") and slots["steps"].get("node_id")),
        "supports_guidance_override": bool(slots.get("guidance") and slots["guidance"].get("node_id")),
        "supports_seed_override": bool(slots.get("seed") and slots["seed"].get("node_id")),
    }


# ---------------------------------------------------------------------------
# Profile CRUD
# ---------------------------------------------------------------------------

def _make_profile_id(name: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", name.lower().replace(" ", "_"))
    safe = re.sub(r"_+", "_", safe).strip("_")
    return safe or f"profile_{uuid.uuid4().hex[:8]}"


def create_profile(
    comfyui_root: str,
    name: str,
    workflow_api: dict,
    workflow: dict | None = None,
    adapter: dict | None = None,
) -> dict:
    """Save the current workflow as a comparison profile.

    *workflow_api* is the API-format JSON (used for execution).
    *workflow* is the UI-format JSON (used for title/tag detection).
    """
    profiles_root = _profiles_root(comfyui_root)
    profile_id = _make_profile_id(name)

    target_dir = _profile_dir(profiles_root, profile_id)
    os.makedirs(target_dir, exist_ok=True)

    if adapter is None:
        adapter = {
            "slots": {},
            "updated_at": datetime.now(tz=timezone.utc).isoformat(),
        }

    now = datetime.now(tz=timezone.utc).isoformat()
    workflow_hash = _workflow_sha256(workflow_api)
    model_stack = _extract_model_stack(workflow_api)
    capabilities = _infer_capabilities(adapter, workflow_api)

    profile = {
        "id": profile_id,
        "name": name,
        "schema_version": PROFILE_SCHEMA_VERSION,
        "workflow_hash": workflow_hash,
        "model_stack": model_stack,
        "slots": adapter.get("slots", {}),
        "loader_target_groups": [],
        "lora_slots": [],
        "subprofiles": [],
        "capabilities": capabilities,
        "created_at": now,
        "updated_at": now,
    }

    # Auto-detect loader target groups from workflow (Phase 2)
    detected_loaders = _detect_slots_from_class(workflow_api)
    default_groups = build_loader_target_groups_from_existing(detected_loaders)
    if default_groups:
        profile["loader_target_groups"] = default_groups

    # Write files
    _write_json(_profile_path(profiles_root, profile_id), profile)
    _write_json(_workflow_api_path(profiles_root, profile_id), workflow_api)
    if workflow:
        _write_json(_workflow_ui_path(profiles_root, profile_id), workflow)
    adapter["updated_at"] = now
    _write_json(_adapter_path(profiles_root, profile_id), adapter)

    return profile


def update_profile(
    comfyui_root: str,
    profile_id: str,
    updates: dict,
) -> dict | None:
    """Update profile metadata or adapter."""
    profiles_root = _profiles_root(comfyui_root)
    profile = _load_profile(profiles_root, profile_id)
    if profile is None:
        return None

    now = datetime.now(tz=timezone.utc).isoformat()
    profile["updated_at"] = now

    # Update name
    if "name" in updates and isinstance(updates["name"], str):
        profile["name"] = updates["name"]

    # Update adapter / slots
    slots = updates.get("slots")
    if slots is not None:
        _write_slots(profiles_root, profile_id, slots)
        profile["slots"] = slots

    # Update loader target groups (Phase 2)
    if "loader_target_groups" in updates:
        _groups = updates["loader_target_groups"]
        if not isinstance(_groups, list):
            raise ValueError("loader_target_groups must be a list")
        profile["loader_target_groups"] = _groups

    # Update LoRA slots (Phase 2)
    if "lora_slots" in updates:
        _lora_slots = updates["lora_slots"]
        if not isinstance(_lora_slots, list):
            raise ValueError("lora_slots must be a list")
        profile["lora_slots"] = _lora_slots

    # Update subprofiles (Phase 2)
    if "subprofiles" in updates:
        _subs = updates["subprofiles"]
        if not isinstance(_subs, list):
            raise ValueError("subprofiles must be a list")
        profile["subprofiles"] = _subs

    # Update workflow files if provided
    if "workflow_api" in updates:
        if not isinstance(updates["workflow_api"], dict):
            raise ValueError("workflow_api must be a dict")
        _write_json(_workflow_api_path(profiles_root, profile_id), updates["workflow_api"])
        _workflow_api = updates["workflow_api"]
    else:
        _workflow_api = _load_workflow_api(profiles_root, profile_id)
    if "workflow" in updates:
        if not isinstance(updates["workflow"], dict):
            raise ValueError("workflow must be a dict")
        _write_json(_workflow_ui_path(profiles_root, profile_id), updates["workflow"])

    # Recalc metadata from workflow_api (fresh copy if provided, otherwise re-read from disk)
    if _workflow_api:
        profile["workflow_hash"] = _workflow_sha256(_workflow_api)
        profile["model_stack"] = _extract_model_stack(_workflow_api)
        profile["capabilities"] = _infer_capabilities({"slots": profile.get("slots", {})}, _workflow_api)

    _write_json(_profile_path(profiles_root, profile_id), profile)
    return profile


def delete_profile(comfyui_root: str, profile_id: str) -> bool:
    """Delete a comparison profile and its files."""
    profiles_root = _profiles_root(comfyui_root)
    target_dir = _profile_dir(profiles_root, profile_id)
    if not os.path.isdir(target_dir):
        return False
    for fname in os.listdir(target_dir):
        fpath = os.path.join(target_dir, fname)
        try:
            if os.path.isfile(fpath):
                os.remove(fpath)
        except OSError:
            pass
    try:
        os.rmdir(target_dir)
    except OSError:
        return False
    return True


def duplicate_profile(comfyui_root: str, profile_id: str, new_name: str) -> dict | None:
    """Duplicate an existing profile with a new name."""
    profiles_root = _profiles_root(comfyui_root)
    profile = _load_profile(profiles_root, profile_id)
    if profile is None:
        return None
    workflow_api = _load_workflow_api(profiles_root, profile_id)
    if workflow_api is None:
        return None
    workflow_ui = _load_workflow_ui(profiles_root, profile_id)
    adapter = _load_adapter(profiles_root, profile_id)
    return create_profile(comfyui_root, new_name, workflow_api, workflow=workflow_ui, adapter=adapter)


def _attach_normalized_view(profile: dict) -> dict:
    """Attach an in-memory normalised runtime view to a profile dict.

    Uses ``experiment_setup_adapter.build_normalized_runtime_profile``
    to produce a lightweight view with ``profile_type``, capabilities,
    synthesised stacks, and LoRA config — without any disk I/O.
    The original profile dict is returned (modified in place).
    """
    try:
        from experiment_setup_adapter import build_normalized_runtime_profile
        profile["normalized"] = build_normalized_runtime_profile(profile)
    except Exception:
        profile["normalized"] = {
            "runtime_profile_type": "legacy_default",
            "capabilities": _infer_capabilities({}, {}),
            "synthesized_stacks": [],
            "lora_config": {"entries": [], "slot_count": 0},
            "dimensions": None,
        }
    return profile


def list_profiles(comfyui_root: str) -> list[dict]:
    """List all comparison profiles with their validation status and
    a normalised runtime view."""
    profiles_root = _profiles_root(comfyui_root)
    results = []
    if not os.path.isdir(profiles_root):
        return results
    for entry in sorted(os.listdir(profiles_root)):
        entry_path = os.path.join(profiles_root, entry)
        if not os.path.isdir(entry_path):
            continue
        profile = _load_profile(profiles_root, entry)
        if profile is None:
            continue
        profile = migrate_profile_to_v2(profile)
        validation = validate_profile(comfyui_root, entry)
        profile["validation"] = validation
        _attach_normalized_view(profile)
        results.append(profile)
    return results


def get_profile(comfyui_root: str, profile_id: str) -> dict | None:
    """Get a single profile with validation and a normalised runtime view."""
    profiles_root = _profiles_root(comfyui_root)
    profile = _load_profile(profiles_root, profile_id)
    if profile is None:
        return None
    profile = migrate_profile_to_v2(profile)
    profile["validation"] = validate_profile(comfyui_root, profile_id)
    _attach_normalized_view(profile)
    return profile


# ---------------------------------------------------------------------------
# Slot auto-detection (public API)
# ---------------------------------------------------------------------------

def auto_detect_slots(comfyui_root: str, profile_id: str) -> dict | None:
    """Auto-detect slots for a profile's workflow.

    Uses the UI-format workflow (``workflow.json``) for node title tag
    detection (``@prompt``, ``@seed``, etc.) and the API-format workflow
    (``workflow_api.json``) for class-based heuristics.  Returns merged
    candidates.
    """
    profiles_root = _profiles_root(comfyui_root)
    workflow_api = _load_workflow_api(profiles_root, profile_id)
    if workflow_api is None:
        return None

    workflow_ui = _load_workflow_ui(profiles_root, profile_id)
    if workflow_ui:
        candidates = detect_slots(workflow_ui)
        # Merge in class-based candidates from the API workflow (in case
        # the UI workflow doesn't have certain info).
        api_candidates = _detect_slots_from_class(workflow_api)
        for key, entries in api_candidates.items():
            existing_ids = {e["node_id"] for e in candidates.get(key, [])}
            for entry in entries:
                if entry["node_id"] not in existing_ids:
                    candidates.setdefault(key, []).append(entry)
        return candidates
    return detect_slots(workflow_api)


def set_slots(comfyui_root: str, profile_id: str, slots: dict) -> dict | None:
    """Manually set adapter slots for a profile."""
    profiles_root = _profiles_root(comfyui_root)
    profile = _load_profile(profiles_root, profile_id)
    if profile is None:
        return None
    _write_slots(profiles_root, profile_id, slots)
    profile["slots"] = slots
    now = datetime.now(tz=timezone.utc).isoformat()
    profile["updated_at"] = now
    workflow_api = _load_workflow_api(profiles_root, profile_id)
    if workflow_api:
        profile["capabilities"] = _infer_capabilities({"slots": slots}, workflow_api)
    _write_json(_profile_path(profiles_root, profile_id), profile)
    return profile


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_profile(comfyui_root: str, profile_id: str) -> dict:
    """Validate a profile's health.

    Returns::
        {"status": "ready"|"needs_mapping"|"invalid",
         "warnings": [...],
         "errors": [...]}
    """
    profiles_root = _profiles_root(comfyui_root)
    profile = _load_profile(profiles_root, profile_id)
    if profile is None:
        return {"status": "invalid", "errors": ["Profile not found"], "warnings": []}

    workflow_api = _load_workflow_api(profiles_root, profile_id)
    if workflow_api is None:
        return {"status": "invalid", "errors": ["Workflow API JSON not found"], "warnings": []}

    errors: list[str] = []
    warnings: list[str] = []
    slots = profile.get("slots", {})

    # Check required slots
    required = {
        "prompt": "Prompt mapping is required",
    }
    for key, msg in required.items():
        slot = slots.get(key, {})
        if not slot or not slot.get("node_id") or not slot.get("path"):
            errors.append(msg)

    # Validate each mapped slot
    for key, slot in slots.items():
        if not slot or not isinstance(slot, dict):
            continue
        node_id = slot.get("node_id", "")
        path = slot.get("path", [])
        if not node_id or not path:
            continue
        if node_id not in workflow_api:
            errors.append(f"Mapped node {node_id} ({key}) not found in workflow")
            continue
        node = workflow_api[node_id]
        if not isinstance(node, dict):
            continue
        # Navigate the path
        current = node
        path_ok = True
        for segment in path:
            if isinstance(current, dict) and segment in current:
                current = current[segment]
            else:
                path_ok = False
                break
        if not path_ok:
            errors.append(f"Mapped path {' > '.join(path)} not found in node {node_id} ({key})")

    # Check model stack has at least one model
    model_stack = profile.get("model_stack", {})
    has_any_model = any(v for v in model_stack.values())
    if not has_any_model:
        warnings.append("No models detected in workflow — may need resolving")

    # Check seed mapping for reproducibility
    seed_slot = slots.get("seed", {})
    if not seed_slot or not seed_slot.get("node_id"):
        warnings.append("No seed mapping — results may not be reproducible")

    if errors:
        status = "invalid"
    elif not slots or not slots.get("prompt", {}).get("node_id"):
        status = "needs_mapping"
    else:
        status = "ready"

    return {"status": status, "errors": errors, "warnings": warnings}


def validate_slot_value(value: str) -> str | None:
    """Validate a slot value; return error string or None."""
    if not value or not value.strip():
        return None
    v = value.strip()
    if len(v) > 50000:
        return "Value too long (max 50000 characters)"
    return None


# ---------------------------------------------------------------------------
# Comparison execution
# ---------------------------------------------------------------------------

def _inject_into_workflow(
    workflow: dict,
    slots: dict,
    shared_inputs: dict,
    skip_slots: set | None = None,
) -> dict:
    """Deep-clone workflow and inject shared values via slot mappings.

    *shared_inputs* keys: prompt, negative_prompt, seed, steps, guidance,
                          width, height, input_image
    *skip_slots*: optional set of slot keys to skip injection for
                  (e.g. ``{"steps", "guidance", "width", "height"}``
                  lets a profile keep its own values).
    """
    cloned = copy.deepcopy(workflow)
    skip = skip_slots or set()

    def _coerce(key: str, val):
        if key in ("seed",):
            try:
                return int(val)
            except (TypeError, ValueError):
                return val
        if key in ("width", "height", "steps"):
            try:
                return int(val)
            except (TypeError, ValueError):
                return val
        if key in ("guidance", "cfg"):
            try:
                return float(val)
            except (TypeError, ValueError):
                return val
        return val

    for slot_key, shared_value in shared_inputs.items():
        if slot_key in skip:
            continue
        if shared_value is None:
            continue
        # Empty string is meaningful for negative_prompt (clears workflow field).
        # Skip whitespace-only strings for all other slots.
        if isinstance(shared_value, str) and not shared_value.strip() and slot_key != "negative_prompt":
            continue
        slot = slots.get(slot_key)
        if not slot or not isinstance(slot, dict):
            continue
        node_id = slot.get("node_id", "")
        path = slot.get("path", [])
        if not node_id or not path:
            continue
        if node_id not in cloned:
            continue
        target = cloned[node_id]
        for segment in path[:-1]:
            if isinstance(target, dict) and segment in target:
                target = target[segment]
            else:
                break
        if isinstance(target, dict) and path[-1] in target:
            target[path[-1]] = _coerce(slot_key, shared_value)

    return cloned


def run_comparison(
    comfyui_root: str,
    prompt_text: str,
    seed: int,
    width: int,
    height: int,
    steps: int | None,
    guidance: float | None,
    negative_prompt: str | None,
    input_image: str | None,
    profile_ids: list[str],
    execution_mode: str = "sequential",
    max_parallel_jobs: int = 2,
    output_format: str = "original",
    quality: int = 75,
    webp_lossless_compression: str = "balanced",
    auto_save_local: bool = False,
    save_folder: str = "",
    save_metadata_sidecar: bool = True,
    per_profile_overrides: dict | None = None,
) -> dict:
    """Prepare and return comparison execution data.

    This does NOT execute Modal calls directly. It prepares the resolved
    workflows and metadata, which the caller (route) uses to submit via
    the existing run_prompt_stream pipeline.

    Returns a "comparison manifest" dict.
    """
    comparison_id = f"comparison_{uuid.uuid4().hex[:12]}"
    now = datetime.now(tz=timezone.utc).isoformat()
    profiles_root = _profiles_root(comfyui_root)

    shared_inputs: dict = {
        "prompt": prompt_text,
        "seed": seed,
        "width": width,
        "height": height,
    }
    if steps is not None:
        shared_inputs["steps"] = steps
    if guidance is not None:
        shared_inputs["guidance"] = guidance
    if negative_prompt is not None:
        shared_inputs["negative_prompt"] = negative_prompt
    if input_image:
        shared_inputs["input_image"] = input_image

    resolved_profiles: list[dict] = []
    for pid in profile_ids:
        profile = _load_profile(profiles_root, pid)
        if profile is None:
            resolved_profiles.append({
                "profile_id": pid,
                "profile_name": pid,
                "status": "error",
                "error": "Profile not found",
            })
            continue
        workflow_api = _load_workflow_api(profiles_root, pid)
        if workflow_api is None:
            resolved_profiles.append({
                "profile_id": pid,
                "profile_name": profile.get("name", pid),
                "status": "error",
                "error": "Workflow API JSON not found",
            })
            continue

        slots = profile.get("slots", {})

        # Validate required prompt mapping
        prompt_slot = slots.get("prompt", {})
        if not prompt_slot or not prompt_slot.get("node_id"):
            resolved_profiles.append({
                "profile_id": pid,
                "profile_name": profile.get("name", pid),
                "status": "error",
                "error": "No prompt slot mapping configured",
            })
            continue

        # Inject shared values (respecting per-profile overrides)
        override = (per_profile_overrides or {}).get(pid, {})
        skip_slots = set(override.get("skip_slots", []))
        try:
            resolved_workflow = _inject_into_workflow(workflow_api, slots, shared_inputs, skip_slots=skip_slots)
        except Exception as e:
            resolved_profiles.append({
                "profile_id": pid,
                "profile_name": profile.get("name", pid),
                "status": "error",
                "error": f"Workflow injection failed: {e}",
            })
            continue

        model_stack = profile.get("model_stack", {})
        workflow_hash = _workflow_sha256(workflow_api)

        resolved_profiles.append({
            "profile_id": pid,
            "profile_name": profile.get("name", pid),
            "status": "ready",
            "workflow": resolved_workflow,
            "workflow_hash": workflow_hash,
            "model_stack": model_stack,
            "slots": slots,
        })

    manifest = {
        "comparison_id": comparison_id,
        "created_at": now,
        "prompt": prompt_text,
        "negative_prompt": negative_prompt or "",
        "seed": seed,
        "width": width,
        "height": height,
        "steps": steps,
        "guidance": guidance,
        "input_image": input_image or "",
        "selected_profiles": profile_ids,
        "execution_mode": execution_mode,
        "max_parallel_jobs": max_parallel_jobs,
        "output_format": output_format,
        "quality": quality,
        "webp_lossless_compression": webp_lossless_compression,
        "auto_save_local": auto_save_local,
        "save_folder": save_folder,
        "save_metadata_sidecar": save_metadata_sidecar,
        "per_profile_overrides": per_profile_overrides or {},
        "results": [],
        "resolved_profiles": resolved_profiles,
    }

    return manifest


# ---------------------------------------------------------------------------
# Result persistence
# ---------------------------------------------------------------------------

def save_comparison_manifest(comfyui_root: str, manifest: dict) -> str:
    """Write the comparison manifest JSON to disk and return its path."""
    comp_root = _comparisons_root(comfyui_root)
    comp_dir = _comparison_dir(comp_root, manifest["comparison_id"])
    os.makedirs(comp_dir, exist_ok=True)

    path = os.path.join(comp_dir, "comparison.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, default=str)
    return path


def save_comparison_result(
    comfyui_root: str,
    comparison_id: str,
    result: dict,
    image_bytes: bytes | None = None,
) -> dict:
    """Save a single profile's result in the comparison folder.

    *result* dict should include at minimum:
        profile_id, profile_name, seed, status, error (if any)

    If *image_bytes* is provided, it is written as a file and the path
    is stored in the result metadata.
    """
    comp_root = _comparisons_root(comfyui_root)
    comp_dir = _comparison_dir(comp_root, comparison_id)
    os.makedirs(comp_dir, exist_ok=True)
    results_dir = os.path.join(comp_dir, "results")
    os.makedirs(results_dir, exist_ok=True)

    profile_id = result.get("profile_id", "unknown")
    now = datetime.now(tz=timezone.utc).isoformat()
    result["created_at"] = now

    out_path = None
    if image_bytes is not None:
        ext = ".webp"
        if result.get("output_format") == "jpeg":
            ext = ".jpg"
        elif result.get("output_format") == "original":
            ext = ".png"
        fname = f"{_make_profile_id(profile_id)}{ext}"
        out_path = os.path.join(results_dir, fname)
        with open(out_path, "wb") as f:
            f.write(image_bytes)
        result["output_path"] = out_path

    # Write per-result JSON
    meta_fname = f"{_make_profile_id(profile_id)}.json"
    meta_path = os.path.join(results_dir, meta_fname)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)
    result["metadata_path"] = meta_path

    return result


def get_comparison_results(comfyui_root: str, comparison_id: str) -> dict | None:
    """Load a comparison manifest by ID."""
    comp_root = _comparisons_root(comfyui_root)
    comp_dir = _comparison_dir(comp_root, comparison_id)
    path = os.path.join(comp_dir, "comparison.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def list_comparison_runs(comfyui_root: str) -> list[dict]:
    """List all completed comparison runs."""
    comp_root = _comparisons_root(comfyui_root)
    results = []
    if not os.path.isdir(comp_root):
        return results
    for entry in sorted(os.listdir(comp_root), reverse=True):
        entry_path = os.path.join(comp_root, entry)
        if not os.path.isdir(entry_path):
            continue
        manifest_path = os.path.join(entry_path, "comparison.json")
        if not os.path.isfile(manifest_path):
            continue
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            results.append({
                "comparison_id": manifest.get("comparison_id", entry),
                "created_at": manifest.get("created_at", ""),
                "prompt": manifest.get("prompt", ""),
                "seed": manifest.get("seed"),
                "profile_count": len(manifest.get("selected_profiles", [])),
                "results": manifest.get("results", []),
            })
        except (json.JSONDecodeError, OSError):
            continue
    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_profile(profiles_root: str, profile_id: str) -> dict | None:
    path = _profile_path(profiles_root, profile_id)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _load_workflow_api(profiles_root: str, profile_id: str) -> dict | None:
    path = _workflow_api_path(profiles_root, profile_id)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _load_workflow_ui(profiles_root: str, profile_id: str) -> dict | None:
    path = _workflow_ui_path(profiles_root, profile_id)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def get_workflow_nodes(comfyui_root: str, profile_id: str) -> dict | None:
    """Return ``{node_id: {class_type, title}}`` for every node in the
    profile's saved workflow API JSON.  Uses the UI workflow for titles
    when available.
    """
    profiles_root = _profiles_root(comfyui_root)
    api = _load_workflow_api(profiles_root, profile_id)
    if api is None:
        return None
    ui = _load_workflow_ui(profiles_root, profile_id)
    ui_titles: dict[str, str] = {}
    if ui and isinstance(ui.get("nodes"), list):
        for n in ui["nodes"]:
            if isinstance(n, dict):
                nid = str(n.get("id") or "")
                t = n.get("title", "")
                if nid and t:
                    ui_titles[nid] = t
    nodes: dict[str, dict] = {}
    for nid, node in api.items():
        if not isinstance(node, dict):
            continue
        ct = node.get("class_type", "")
        if not ct:
            continue
        title = ui_titles.get(nid, "")
        _meta = node.get("_meta")
        if isinstance(_meta, dict) and not title:
            title = _meta.get("title", "") or ""
        nodes[nid] = {"class_type": ct, "title": title}
    return nodes


def get_profile_workflow(comfyui_root: str, profile_id: str) -> dict | None:
    """Return saved workflow payload for a profile."""
    profiles_root = _profiles_root(comfyui_root)
    workflow_api = _load_workflow_api(profiles_root, profile_id)
    if workflow_api is None:
        return None
    workflow = _load_workflow_ui(profiles_root, profile_id)
    return {"workflow_api": workflow_api, "workflow": workflow}


def _load_adapter(profiles_root: str, profile_id: str) -> dict | None:
    path = _adapter_path(profiles_root, profile_id)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _write_json(path: str, data: dict) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    os.replace(tmp, path)


def _write_slots(profiles_root: str, profile_id: str, slots: dict) -> None:
    adapter = _load_adapter(profiles_root, profile_id) or {}
    adapter["slots"] = slots
    adapter["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
    _write_json(_adapter_path(profiles_root, profile_id), adapter)


# ---------------------------------------------------------------------------
# Config persistence for comparison-specific settings
# ---------------------------------------------------------------------------

def _comparison_config_path(comfyui_root: str) -> str:
    p = os.path.join(comfyui_root, "user", "default", "comfy-modal", "comparison_config.json")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


def load_comparison_config(comfyui_root: str) -> dict:
    path = _comparison_config_path(comfyui_root)
    if not os.path.isfile(path):
        return _default_comparison_config()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = dict(_default_comparison_config())
        merged.update(data)
        return merged
    except (json.JSONDecodeError, OSError):
        return _default_comparison_config()


def save_comparison_config(comfyui_root: str, config: dict) -> dict:
    path = _comparison_config_path(comfyui_root)
    merged = dict(_default_comparison_config())
    merged.update(config)
    _write_json(path, merged)
    return merged


# ── Phase 2: extended mappings ───────────────────────────────────────────

# Mapping summary keys (the profile-card UI consumes this)
MAPPING_SUMMARY_KEYS = (
    "prompt", "negative_prompt", "seed", "steps", "guidance",
    "width", "height", "input_image",
    "sampler", "scheduler", "denoise",
    "loader_target_groups", "lora_slots",
)


def compute_mapping_summary(profile: dict) -> dict:
    """Return a {key: bool} summary of what is mapped on a profile.

    The bool is True iff there is meaningful content for that category.
    For loader_target_groups and lora_slots, "meaningful" means non-empty.
    """
    slots = profile.get("slots", {}) or {}
    groups = profile.get("loader_target_groups", []) or []
    lora_slots = profile.get("lora_slots", []) or []
    out = {}
    for key in MAPPING_SUMMARY_KEYS:
        if key == "loader_target_groups":
            out[key] = bool(groups)
        elif key == "lora_slots":
            out[key] = bool(lora_slots)
        else:
            slot = slots.get(key) or {}
            out[key] = bool(slot.get("node_id") or slot.get("field"))
    return out


def build_loader_target_groups_from_existing(slots: dict) -> list:
    """Construct a single default group from existing per-category slot maps.

    Older profiles store loader mappings as flat ``unet_loader`` / ``clip_loader``
    / ``vae_loader`` slot lists. This helper promotes them into a single
    ``g_default`` group so the new loader-target-group code path can consume
    them without requiring the user to re-map.
    """
    def _norm(items):
        if items is None:
            return []
        if isinstance(items, dict):
            return [items] if items.get("node_id") else []
        if isinstance(items, list):
            return [i for i in items if isinstance(i, dict) and i.get("node_id")]
        return []

    unet = _norm(slots.get("unet_loader"))
    clip = _norm(slots.get("clip_loader"))
    vae = _norm(slots.get("vae_loader"))
    if not unet and not clip and not vae:
        return []
    return [{
        "id": "g_default",
        "label": "Default",
        "unet": unet,
        "clip": clip,
        "vae": vae,
    }]


def inject_loader_group(workflow: dict, group: dict, triple: dict) -> None:
    """Inject a resolved triple into all loader fields listed in ``group``.

    Each entry in ``group["unet"|"clip"|"vae"]`` is a ``{node_id, field}`` dict.
    The corresponding workflow node's ``inputs[field]`` is set to the matching
    value in ``triple`` ("unet", "clip", "vae"). Multiple loaders of the same
    category all receive the same value (this is the intended fan-out; the
    group exists precisely so the user has confirmed they want fan-out).
    """
    mapping = [("unet", triple.get("unet", "")),
               ("clip", triple.get("clip", "")),
               ("vae", triple.get("vae", ""))]
    for category, value in mapping:
        for entry in group.get(category, []) or []:
            node_id = str(entry.get("node_id", ""))
            field = entry.get("field", "")
            if not node_id or not field:
                continue
            node = workflow.get(node_id)
            if not isinstance(node, dict):
                continue
            inputs = node.setdefault("inputs", {})
            if isinstance(inputs, dict):
                inputs[field] = value


# ── Subprofile (alternate triple) management ─────────────────────────────

def add_subprofile(profile: dict, subprofile: dict) -> None:
    """Add a subprofile triple. Raises SubprofileError on duplicate id."""
    subs = profile.setdefault("subprofiles", [])
    sid = subprofile.get("id", "")
    if not sid:
        raise SubprofileError("subprofile id must be non-empty")
    for existing in subs:
        if existing.get("id") == sid:
            raise SubprofileError(f"duplicate subprofile id: {sid!r}")
    subs.append(dict(subprofile))


def remove_subprofile(profile: dict, subprofile_id: str) -> None:
    subs = profile.get("subprofiles", [])
    profile["subprofiles"] = [s for s in subs if s.get("id") != subprofile_id]


# ── LoRA slot validation ─────────────────────────────────────────────────

def validate_lora_selection_against_slots(profile: dict, selection: list) -> list:
    """Return a list of human-readable warnings for an invalid LoRA selection.

    ``selection`` is a list of ``(filename, [model_strengths], [clip_strengths])``
    tuples. The selection is valid iff it has at most as many LoRAs as the
    profile has mapped LoRA slots, and each strength list is a list of floats
    (an empty strength list is allowed for "No LoRA"; strength 0 is valid).
    """
    warnings: list = []
    slots = profile.get("lora_slots", []) or []
    slot_count = len(slots)
    if len(selection) > slot_count:
        warnings.append(
            f"LoRA selection has {len(selection)} entries but profile has "
            f"only {slot_count} mapped LoRA slot(s); selection exceeds capacity"
        )
    for idx, (filename, model_strs, clip_strs) in enumerate(selection):
        if not isinstance(model_strs, list) or not isinstance(clip_strs, list):
            warnings.append(f"slot {idx}: strengths must be lists, got "
                            f"model={type(model_strs).__name__} clip={type(clip_strs).__name__}")
            continue
        if len(model_strs) == 0 and len(clip_strs) == 0:
            # explicit "no values" is OK (UI inserts default at execution time)
            continue
        for j, v in enumerate(model_strs):
            try:
                float(v)
            except (TypeError, ValueError):
                warnings.append(f"slot {idx} model_strength[{j}] is not numeric: {v!r}")
        for j, v in enumerate(clip_strs):
            try:
                float(v)
            except (TypeError, ValueError):
                warnings.append(f"slot {idx} clip_strength[{j}] is not numeric: {v!r}")
    return warnings


# ── Profile schema migration ─────────────────────────────────────────────

def migrate_profile_to_v2(profile: dict) -> dict:
    """Promote a v1 (pre-Phase-2) profile to v2 in place.

    v1 had no loader_target_groups, lora_slots, or subprofiles. Existing
    per-category loader slot lists are promoted into a single default
    loader_target_group so they keep working without re-mapping.

    A v2 profile is returned unchanged.
    """
    version = int(profile.get("schema_version", 1))
    if version >= 2:
        return profile
    if version != 1:
        raise ValueError(f"unsupported profile schema_version={version}")
    slots = profile.get("slots", {}) or {}
    # Build default loader groups from existing flat mappings
    profile["loader_target_groups"] = build_loader_target_groups_from_existing(slots)
    profile.setdefault("lora_slots", [])
    profile.setdefault("subprofiles", [])
    profile["schema_version"] = 2
    return profile
