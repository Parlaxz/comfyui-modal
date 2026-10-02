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

# Generic fallback for nonstandard custom loaders (e.g. Donut loaders) whose
# class/input names are outside _MODEL_REF_MAPPINGS. A value is only treated
# as a model ref when BOTH hold: the input name or node class contains a
# model-indicating token, AND the value carries a recognized model extension.
# This keeps arbitrary prompt text and URLs out of the dependency report.
_MODEL_TOKEN_ROLES: tuple[tuple[str, str], ...] = (
    ("controlnet", "controlnet"),
    ("checkpoint", "checkpoint"),
    ("lycoris", "lora"),
    ("lora", "lora"),
    ("unet", "unet"),
    ("diffusion", "unet"),
    ("text_encoder", "clip"),
    ("text-encoder", "clip"),
    ("clip", "clip"),
    ("vae", "vae"),
)

_MODEL_EXTENSIONS: tuple[str, ...] = (
    ".safetensors",
    ".ckpt",
    ".pt",
    ".pth",
    ".bin",
    ".gguf",
    ".onnx",
    ".sft",
)


def _model_role_hint(text: str) -> str:
    """Return the model role implied by a name, or "" when it does not."""
    if not isinstance(text, str) or not text:
        return ""
    lowered = text.lower()
    for token, role in _MODEL_TOKEN_ROLES:
        if token in lowered:
            return role
    if "model" in lowered or "filename" in lowered:
        return "model"
    return ""


def _generic_model_filename(value) -> str:
    """Return a model filename/path from a value, else "".

    Rejects non-strings, blanks, URLs, and values without a recognized model
    extension. Path-like values are accepted (the extension still applies).
    """
    if not isinstance(value, str):
        return ""
    candidate = value.strip()
    if not candidate:
        return ""
    lowered = candidate.lower()
    if lowered.startswith(("http://", "https://", "data:", "//")):
        return ""
    if not any(lowered.endswith(ext) for ext in _MODEL_EXTENSIONS):
        return ""
    return candidate


def _generic_model_ref(class_type, input_name, value) -> dict[str, str] | None:
    """Best-effort model ref for a custom loader input, or None.

    Requires a model-indicating input name or class; the role prefers the
    input name over the class and falls back to "model".
    """
    role = _model_role_hint(input_name) or _model_role_hint(class_type)
    if not role:
        return None
    filename = _generic_model_filename(value)
    if not filename:
        return None
    return {"role": role, "filename": filename}


def extract_workflow_model_refs(prompt: dict) -> list[dict[str, str]]:
    seen = set()
    refs = []
    for node in prompt.values():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type", "")
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        mappings = _MODEL_REF_MAPPINGS.get(class_type, [])
        mapped_fields = {field for _role, field in mappings}
        for role, field in mappings:
            value = inputs.get(field)
            if not isinstance(value, str) or not value:
                continue
            key = (role, value)
            if key in seen:
                continue
            seen.add(key)
            refs.append({"role": role, "filename": value})
        # Generic fallback for custom loader inputs not covered above.
        for input_name, value in inputs.items():
            if input_name in mapped_fields:
                continue
            ref = _generic_model_ref(class_type, input_name, value)
            if ref is None:
                continue
            key = (ref["role"], ref["filename"])
            if key in seen:
                continue
            seen.add(key)
            refs.append(ref)
    return refs


# ── Recursive UI-graph node traversal ────────────────────────────────────
#
# ComfyUI nests real nodes below group/subgraph containers: legacy group
# nodes under ``extra.groupNodes`` (a dict of id → graph), current subgraph
# definitions under ``definitions.subgraphs`` (a list/dict of graphs), and
# equivalent nested containers. Scanning only the top-level ``nodes`` list
# misses those nodes, so every graph consumer walks the whole capture.

def _is_graph_node(value) -> bool:
    """True for a real graph-node row, never a slot/link/widget dict.

    A node carries a non-empty UI ``type`` or API ``class_type`` plus
    graph-node fields. Slot definitions share ``type`` but lack a node
    ``properties`` dict and an ``inputs``/``outputs`` pair; link rows carry
    ``origin_id``/``target_id``. Both are rejected so they are never reported
    as dependencies.
    """
    if not isinstance(value, dict):
        return False
    node_type = value.get("type")
    class_type = value.get("class_type")
    has_type = isinstance(node_type, str) and bool(node_type.strip())
    has_class_type = isinstance(class_type, str) and bool(class_type.strip())
    if not (has_type or has_class_type):
        return False
    inputs = value.get("inputs")
    if has_class_type and not has_type and isinstance(inputs, dict):
        return True  # API-format node row
    if "origin_id" in value or "target_id" in value:
        return False  # link row shares a ``type`` but is not a node
    if isinstance(value.get("properties"), dict):
        return True
    for key in ("widgets_values", "widgets_values_named", "widgetsValuesNamed"):
        if key in value:
            return True
    return isinstance(inputs, list) and isinstance(value.get("outputs"), list)


def iter_graph_nodes(graph):
    """Yield every real graph node reachable in a UI/static graph capture.

    Walks nested ``extra.groupNodes``, ``definitions.subgraphs``, group
    structures and any equivalent nested dict/list container. Only graph-node
    rows are yielded (see :func:`_is_graph_node`); slot definitions, link rows
    and widget-value dicts are traversed but never returned. Nodes are
    deduplicated by object identity, so a container reachable from two paths
    yields its nodes once. Never raises: non-graph input yields nothing.
    """
    if not isinstance(graph, (dict, list)):
        return
    seen: set[int] = set()
    stack = [graph]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            if id(current) in seen:
                continue
            seen.add(id(current))
            if _is_graph_node(current):
                yield current
            stack.extend(current.values())
        elif isinstance(current, list):
            if id(current) in seen:
                continue
            seen.add(id(current))
            stack.extend(current)


# ── Captured UI/static graph widget metadata ─────────────────────────────
#
# API prompts carry connected values, but a stored UI graph also records
# widget values by name on standard and custom loader nodes. Reshaping those
# named fields into a synthetic prompt lets the exact same loader mappings and
# model-token/extension guards apply, so a custom loader's named widget file
# is recovered without loosening URL/prompt rejection.

def _graph_node_has_identity(node: dict) -> bool:
    properties = node.get("properties")
    if not isinstance(properties, dict):
        return False
    for key in ("cnr_id", "aux_id"):
        value = properties.get(key)
        if isinstance(value, str) and value.strip():
            return True
    return False


def _has_nonempty_collection(value) -> bool:
    if isinstance(value, (list, tuple, dict)):
        return len(value) > 0
    return False


def _is_virtual_graph_node(node: dict) -> bool:
    """True for a frontend-only panel: empty inputs/outputs, no pack identity."""
    if _graph_node_has_identity(node):
        return False
    return (
        not _has_nonempty_collection(node.get("inputs"))
        and not _has_nonempty_collection(node.get("outputs"))
    )


def _named_widget_values(node: dict) -> dict[str, object]:
    """Collect name → value widget fields recorded on a captured graph node.

    Supports ``widgets_values_named`` / ``widgetsValuesNamed`` dicts, a dict
    ``widgets_values`` (some exporters key by input name), and a ``widgets``
    list of ``{name, value}`` entries. Positional ``widgets_values`` lists are
    intentionally ignored — they carry no reliable input names.
    """
    out: dict[str, object] = {}
    for key in ("widgets_values_named", "widgetsValuesNamed"):
        data = node.get(key)
        if isinstance(data, dict):
            for name, value in data.items():
                if isinstance(name, str) and name and name not in out:
                    out[name] = value
    values = node.get("widgets_values")
    if isinstance(values, dict):
        for name, value in values.items():
            if isinstance(name, str) and name and name not in out:
                out[name] = value
    widgets = node.get("widgets")
    if isinstance(widgets, list):
        for widget in widgets:
            if not isinstance(widget, dict):
                continue
            name = widget.get("name")
            if not isinstance(name, str) or not name or name in out:
                continue
            if "value" in widget:
                out[name] = widget.get("value")
            elif isinstance(widget.get("widget"), dict) and "value" in widget["widget"]:
                out[name] = widget["widget"]["value"]
    return out


def _is_disabled_graph_node(node) -> bool:
    """True for a graph node ComfyUI will not execute.

    ``mode`` is ComfyUI's own per-node execution state: 0 = ALWAYS,
    2 = NEVER (muted), 4 = BYPASS. A muted/bypassed node is not on the
    critical path, so the models it names are not dependencies of the
    workflow. A missing or unrecognised ``mode`` counts as enabled, because
    only an explicit opt-out may relax readiness.
    """
    if not isinstance(node, dict):
        return False
    mode = node.get("mode")
    if isinstance(mode, bool) or not isinstance(mode, int):
        return False
    return mode in (2, 4)


def extract_ui_graph_model_refs(graph_json) -> list[dict[str, str]]:
    """Extract model refs from named widget metadata on a captured UI graph.

    Each node's named widget fields are reshaped into a synthetic prompt node
    and passed through :func:`extract_workflow_model_refs`, so standard loader
    mappings and the generic custom-loader model-token/extension guards both
    apply. Nodes nested in group/subgraph containers are included. Virtual
    panels (empty inputs/outputs, no pack identity) and nodes ComfyUI will not
    execute (muted/bypassed) are skipped, so their metadata can never surface as
    a model. Never raises.
    """
    if not isinstance(graph_json, dict):
        return []
    synthetic: dict[str, dict] = {}
    for index, node in enumerate(iter_graph_nodes(graph_json)):
        if not isinstance(node, dict):
            continue
        class_type = node.get("type")
        if not isinstance(class_type, str) or not class_type:
            continue
        if _is_virtual_graph_node(node) or _is_disabled_graph_node(node):
            continue
        inputs = _named_widget_values(node)
        if not inputs:
            continue
        # Keys are only a uniqueness guard: nested subgraphs reuse local node
        # ids, and `extract_workflow_model_refs` reads values, not keys.
        synthetic["graph_%d" % index] = {"class_type": class_type, "inputs": inputs}
    if not synthetic:
        return []
    return extract_workflow_model_refs(synthetic)
