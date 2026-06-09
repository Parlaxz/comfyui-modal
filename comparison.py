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
)

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
    normalized = json.dumps(workflow, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


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
        "workflow_hash": workflow_hash,
        "model_stack": model_stack,
        "slots": adapter.get("slots", {}),
        "capabilities": capabilities,
        "created_at": now,
        "updated_at": now,
    }

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

    # Re-read workflow API JSON to recalc capabilities and model stack
    workflow_api = _load_workflow_api(profiles_root, profile_id)
    if workflow_api:
        profile["workflow_hash"] = _workflow_sha256(workflow_api)
        profile["model_stack"] = _extract_model_stack(workflow_api)
        profile["capabilities"] = _infer_capabilities({"slots": profile.get("slots", {})}, workflow_api)

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


def list_profiles(comfyui_root: str) -> list[dict]:
    """List all comparison profiles with their validation status."""
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
        validation = validate_profile(comfyui_root, entry)
        profile["validation"] = validation
        results.append(profile)
    return results


def get_profile(comfyui_root: str, profile_id: str) -> dict | None:
    """Get a single profile with validation."""
    profiles_root = _profiles_root(comfyui_root)
    profile = _load_profile(profiles_root, profile_id)
    if profile is None:
        return None
    profile["validation"] = validate_profile(comfyui_root, profile_id)
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
        if shared_value is None or (isinstance(shared_value, str) and not shared_value.strip()):
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
    if negative_prompt:
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
