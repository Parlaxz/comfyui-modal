"""Deterministic prompt hashing, field summary extraction, and model-stack extraction."""

import hashlib
import json

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


def prompt_sha256(prompt: dict) -> str:
    """Return a deterministic SHA-256 hex digest for a prompt dict.

    Uses ``json.dumps`` with ``sort_keys=True`` so that semantically
    identical prompts differing only in key ordering produce the same hash.
    """
    normalized = json.dumps(prompt, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


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
