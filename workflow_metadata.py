"""Deterministic prompt hashing, field summary extraction, and model-stack extraction."""

import hashlib
import json

# Canonical hashing: delegate to the single production_workflow implementation.
from production_workflow import _canonical_workflow_hash

# Canonical JSON serialisation constants (maintained here for backward
# compatibility with legacy callers; new code should use
# production_workflow._canonical_workflow_hash directly).
_CANONICAL_JSON_KWARGS = {
    "sort_keys": True,
    "separators": (",", ":"),
    "ensure_ascii": False,
    "allow_nan": False,
}

# ---------------------------------------------------------------------------
# Loader → (bucket key, input field) mappings for model-stack extraction
# ---------------------------------------------------------------------------
_LOADER_MAPPINGS: dict[str, tuple[str, str]] = {
    "CheckpointLoaderSimple": ("checkpoint", "ckpt_name"),
    "CheckpointLoader": ("checkpoint", "ckpt_name"),
    "UNETLoader": ("unet", "unet_name"),
    "CLIPLoader": ("clip", "clip_name"),
    "VAELoader": ("vae", "vae_name"),
    "LoraLoader": ("lora", "lora_name"),
    "LoraLoaderModelOnly": ("lora", "lora_name"),
    "ControlNetLoader": ("controlnet", "control_net_name"),
}


def normalize_flux_clip_pair(clip1: str, clip2: str) -> tuple[str, str]:
    """Return ComfyUI's expected FLUX DualCLIPLoader order."""
    a = clip1.lower()
    b = clip2.lower()
    a_is_t5 = "t5" in a
    b_is_clip_l = "clip_l" in b or "clip-l" in b or "clip-vit" in b
    if a_is_t5 and b_is_clip_l:
        return clip2, clip1
    return clip1, clip2


def prompt_sha256(prompt: dict) -> str:
    """Return a deterministic SHA-256 hex digest for a prompt dict.

    Delegates to ``production_workflow._canonical_workflow_hash`` so there is
    one canonical implementation.  Maintained here for backward compatibility;
    new callers should use ``_canonical_workflow_hash`` directly.
    """
    return _canonical_workflow_hash(prompt)


def summarize_prompt_fields(prompt: dict) -> dict:
    """Extract a flat summary of common scalar fields from a prompt.

    Scans every node's ``inputs`` dictionary (in prompt iteration order)
    for well-known generation parameters (seed, steps, cfg, width, height)
    and returns the **first** value encountered for each.  Because Python
    ``dict`` insertion order is preserved, the node that appears earliest
    in the prompt dict "wins" for each field.  Fields not present in any
    node are omitted from the result.
    """
    INTERESTING = {"seed", "steps", "cfg", "width", "height", "denoise"}
    summary: dict = {}
    for node in prompt.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        for key in INTERESTING:
            if key in inputs and key not in summary:
                summary[key] = inputs[key]
    return summary


def extract_model_stack(prompt: dict) -> dict[str, list[str]]:
    """Extract the set of model files referenced by loader nodes in *prompt*.

    Returns a dict mapping bucket names (``"checkpoint"``, ``"unet"``,
    ``"clip"``, ``"vae"``, ``"lora"``, ``"controlnet"``) to lists of
    model filenames.  Detected loaders include:

    * CheckpointLoaderSimple / CheckpointLoader → ``checkpoint`` / ``ckpt_name``
    * UNETLoader → ``unet`` / ``unet_name``
    * CLIPLoader → ``clip`` / ``clip_name``
    * VAELoader → ``vae`` / ``vae_name``
    * LoraLoader / LoraLoaderModelOnly → ``lora`` / ``lora_name``
    * ControlNetLoader → ``controlnet`` / ``control_net_name``
    """
    stack: dict[str, list[str]] = {}
    for node in prompt.values():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type", "")
        mapping = _LOADER_MAPPINGS.get(class_type)
        if mapping is None:
            continue
        bucket, field = mapping
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        value = inputs.get(field)
        # Accept non-empty strings only — empty/falsy placeholders are skipped
        if isinstance(value, str) and value != "":
            stack.setdefault(bucket, []).append(value)
    return stack


def extract_warmup_stack(prompt: dict) -> dict:
    """Extract the warmup-relevant model stack from a workflow prompt."""
    stack: dict = {
        "checkpoint": [], "unet": [], "clip": [], "vae": [],
        "clip_type": "flux", "clip_loader_class": None,
        "clip1": "", "clip2": "",
    }
    for node in prompt.values():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type", "")
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue

        if class_type in {"CheckpointLoaderSimple", "CheckpointLoader"}:
            value = inputs.get("ckpt_name")
            if isinstance(value, str) and value and value not in stack["checkpoint"]:
                stack["checkpoint"].append(value)
        elif class_type == "UNETLoader":
            value = inputs.get("unet_name")
            if isinstance(value, str) and value and value not in stack["unet"]:
                stack["unet"].append(value)
        elif class_type == "DualCLIPLoader":
            stack["clip_loader_class"] = "DualCLIPLoader"
            for key in ("clip_name1", "clip_name2"):
                value = inputs.get(key)
                if isinstance(value, str) and value and value not in stack["clip"]:
                    stack["clip"].append(value)
            v1 = inputs.get("clip_name1")
            v2 = inputs.get("clip_name2")
            if isinstance(v1, str) and v1:
                stack["clip1"] = v1
            if isinstance(v2, str) and v2:
                stack["clip2"] = v2
            clip_type = inputs.get("type", "")
            if isinstance(clip_type, str) and clip_type:
                stack["clip_type"] = clip_type
        elif class_type == "CLIPLoader":
            stack["clip_loader_class"] = "CLIPLoader"
            value = inputs.get("clip_name")
            if isinstance(value, str) and value and value not in stack["clip"]:
                stack["clip"].append(value)
            if isinstance(value, str) and value:
                stack["clip1"] = value
            stack["clip2"] = ""
            clip_type = inputs.get("type", "")
            if isinstance(clip_type, str) and clip_type:
                stack["clip_type"] = clip_type
        elif class_type == "VAELoader":
            value = inputs.get("vae_name")
            if isinstance(value, str) and value and value not in stack["vae"]:
                stack["vae"].append(value)
    return stack


def stack_to_warmup_profile(stack: dict) -> dict:
    """Convert an extracted warmup stack into a warmup profile."""
    if stack.get("checkpoint"):
        return {"mode": "checkpoint", "checkpoint": stack["checkpoint"][0]}
    if stack.get("unet") and stack.get("clip") and stack.get("vae"):
        clips = stack["clip"]
        clip_type = stack.get("clip_type", "flux")
        if stack.get("clip_loader_class") == "DualCLIPLoader":
            clip1 = stack.get("clip1", clips[0] if clips else "")
            clip2 = stack.get("clip2", "")
            clip1, clip2 = normalize_flux_clip_pair(clip1, clip2)
        else:
            clip1 = stack.get("clip1", clips[0] if clips else "")
            clip2 = ""
        return {
            "mode": "split",
            "unet": stack["unet"][0],
            "clip1": clip1,
            "clip2": clip2,
            "vae": stack["vae"][0],
            "clip_type": clip_type,
        }
    return {}


def warmup_profile_matches_stack(profile: dict, requested: dict) -> bool:
    """Return True when the requested stack matches the pinned warmup profile."""
    if not profile:
        return True
    mode = profile.get("mode")
    if mode == "checkpoint":
        checkpoint = profile.get("checkpoint", "")
        return bool(checkpoint) and checkpoint in requested.get("checkpoint", [])
    if mode == "split":
        clip2 = profile.get("clip2", "")
        return (
            profile.get("clip_type", "flux") == requested.get("clip_type", "flux")
            and profile.get("unet", "") in requested.get("unet", [])
            and profile.get("clip1", "") in requested.get("clip", [])
            and (not clip2 or clip2 in requested.get("clip", []))
            and profile.get("vae", "") in requested.get("vae", [])
        )
    return False


_MODEL_REF_MAPPINGS: dict[str, list[tuple[str, str]]] = {
    "CheckpointLoaderSimple": [("checkpoint", "ckpt_name")],
    "CheckpointLoader": [("checkpoint", "ckpt_name")],
    "UNETLoader": [("unet", "unet_name")],
    "CLIPLoader": [("clip", "clip_name")],
    "DualCLIPLoader": [("clip", "clip_name1"), ("clip", "clip_name2")],
    "VAELoader": [("vae", "vae_name")],
    "LoraLoader": [("lora", "lora_name")],
    "LoraLoaderModelOnly": [("lora", "lora_name")],
    "ControlNetLoader": [("controlnet", "control_net_name")],
}


def extract_workflow_model_refs(prompt: dict) -> list[dict[str, str]]:
    seen = set()
    refs = []
    for node in prompt.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        mappings = _MODEL_REF_MAPPINGS.get(node.get("class_type", ""), [])
        for role, field in mappings:
            value = inputs.get(field)
            if not isinstance(value, str) or not value:
                continue
            key = (role, value)
            if key in seen:
                continue
            seen.add(key)
            refs.append({"role": role, "filename": value})
    return refs
