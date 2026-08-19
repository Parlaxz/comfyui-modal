"""Graph introspection for the Workflow domain.

Pure functions over capture dicts — no ComfyUI runtime required. Where the
ComfyUI ``nodes`` module is available it is probed lazily (inside functions,
guarded) to recover graph-provided metadata (enum choices, min/max/step,
multiline); otherwise metadata is inferred from widget values alone.

Never hardcode generic sampler/scheduler lists: enum options always come
from the graph itself (node definitions or the captured widget value).
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from production_workflow import _canonical_workflow_hash
from workflow_metadata import extract_model_stack

from .models import (
    GraphHashError,
    MappingEntry,
    OUTPUT_NODE_CLASSES,
)

# Heuristic role mapping: input name → canonical semantic role.
_INPUT_ROLE_HINTS: dict[str, str] = {
    "seed": "seed",
    "steps": "steps",
    "cfg": "cfg",
    "guidance": "cfg",
    "sampler_name": "sampler",
    "scheduler": "scheduler",
    "ckpt_name": "model",
    "unet_name": "model",
    "clip_name": "model",
    "clip_name1": "model",
    "clip_name2": "model",
    "vae_name": "model",
    "denoise": "denoise",
    "width": "width",
    "height": "height",
    "image": "source_image",
    "mask": "mask",
}

_TEXT_ROLES = ("positive_prompt", "negative_prompt")

_VALUE_TYPE_TO_DATA_TYPE: dict[str, str] = {
    "boolean": "BOOLEAN",
    "integer": "INT",
    "number": "FLOAT",
    "string": "STRING",
    "multiline": "STRING",
    "enum": "ENUM",
    "image": "IMAGE",
}


def extract_executable_prompt(api_prompt_json: Any) -> dict[str, Any]:
    """Return the executable prompt dict from an api-prompt capture.

    Prefers the ``output`` key when both ``workflow`` and ``output`` are
    dicts (ComfyUI API format); otherwise returns the dict itself.
    """
    if not isinstance(api_prompt_json, dict):
        return {}
    output = api_prompt_json.get("output")
    workflow = api_prompt_json.get("workflow")
    if isinstance(output, dict) and isinstance(workflow, dict):
        return output
    return api_prompt_json


def graph_hash_from_capture(capture: dict[str, Any]) -> str:
    """Canonical SHA-256 of the executable prompt of a graph capture.

    Raises ``GraphHashError`` when the canonical hash cannot be computed
    (fail-closed, mirroring ``_canonical_workflow_hash`` semantics).
    """
    api_prompt_json = (capture or {}).get("api_prompt_json") or {}
    executable = extract_executable_prompt(api_prompt_json)
    digest = _canonical_workflow_hash(executable)
    if not digest:
        raise GraphHashError("cannot compute graph hash for capture")
    return digest


def node_exists(prompt: dict[str, Any], node_id: Any) -> bool:
    return str(node_id) in prompt


def class_type_of(prompt: dict[str, Any], node_id: Any) -> str:
    node = prompt.get(str(node_id))
    if isinstance(node, dict):
        return str(node.get("class_type", ""))
    return ""


def input_exists(prompt: dict[str, Any], node_id: Any, input_name: str) -> bool:
    node = prompt.get(str(node_id))
    if not isinstance(node, dict):
        return False
    inputs = node.get("inputs")
    return isinstance(inputs, dict) and input_name in inputs


def _probe_node_def(
    class_type: str,
) -> Optional[tuple[dict[str, Any], dict[str, Any]]]:
    """Lazily probe the ComfyUI node registry for input definitions.

    Returns ``(required, optional)`` dicts of input name → type spec, or
    ``None`` when the registry is unavailable or the class is unknown.
    Never raises.
    """
    try:
        import nodes  # type: ignore[import-not-found]
    except Exception:
        return None
    try:
        cls = nodes.NODE_CLASS_MAPPINGS.get(class_type)
        if cls is None:
            return None
        spec = cls.INPUT_TYPES()
        if not isinstance(spec, dict):
            return None
        return (
            dict(spec.get("required") or {}),
            dict(spec.get("optional") or {}),
        )
    except Exception:
        return None


def infer_control_kind(
    value: Any,
    *,
    multiline_hint: bool = False,
    data_type: str = "",
    enum_options: Optional[list] = None,
) -> str:
    """Infer the Studio control kind from a graph value/type.

    ``0`` and ``False`` are valid values and never treated as missing.
    """
    if data_type in {"IMAGE", "MASK", "LATENT"}:
        return "image"
    if enum_options:
        return "enum"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, (list, tuple)):
        return "enum"
    if isinstance(value, str):
        return "multiline" if (len(value) > 200 or multiline_hint) else "string"
    if isinstance(value, dict) and value.get("class_type"):
        return "node"
    return "string"


def _parse_type_spec(spec: Any) -> tuple[str, dict[str, Any]]:
    """Parse a ComfyUI input type spec into ``(type_name, options)``.

    Handles: plain str; ``(type, options_dict)``; ``(type,)``; enum tuple
    of strings; bare dict of options.
    """
    if isinstance(spec, str):
        return spec, {}
    if isinstance(spec, (list, tuple)):
        if not spec:
            return "", {}
        if isinstance(spec[0], str) and len(spec) == 2 and isinstance(spec[1], dict):
            return spec[0], dict(spec[1])
        if len(spec) == 1 and isinstance(spec[0], str):
            return spec[0], {}
        # ComfyUI enum form: (["a", "b"],) — one-tuple wrapping the choices.
        if len(spec) == 1 and isinstance(spec[0], (list, tuple)):
            return "ENUM", {"enum": list(spec[0])}
        if all(isinstance(item, str) for item in spec):
            return "ENUM", {"enum": list(spec)}
        return "", {}
    if isinstance(spec, dict):
        return "", dict(spec)
    return "", {}


def _entry_metadata_from_spec(
    role: str,
    value: Any,
    type_name: str,
    options: dict[str, Any],
) -> MappingEntry:
    """Build a MappingEntry from a parsed node-def type spec."""
    entry = MappingEntry(semantic_role=role, node_id="", input_name="")
    entry.data_type = type_name or _VALUE_TYPE_TO_DATA_TYPE.get(
        infer_control_kind(value), ""
    )
    enum_options = options.get("enum")
    if enum_options and isinstance(enum_options, (list, tuple)):
        entry.enum_options = [str(o) for o in enum_options]
        entry.control_kind = "enum"
        entry.data_type = "ENUM"
    elif type_name == "BOOLEAN" or isinstance(value, bool):
        entry.control_kind = "boolean"
        entry.data_type = "BOOLEAN"
    elif type_name == "INT" or isinstance(value, int):
        entry.control_kind = "integer"
        entry.data_type = "INT"
    elif type_name == "FLOAT" or isinstance(value, float):
        entry.control_kind = "number"
        entry.data_type = "FLOAT"
    elif type_name == "IMAGE" or type_name == "MASK" or type_name == "LATENT":
        entry.control_kind = "image"
        entry.data_type = type_name
    else:
        entry.control_kind = infer_control_kind(
            value,
            multiline_hint=bool(options.get("multiline")),
            data_type=type_name,
        )
        if entry.control_kind == "multiline":
            entry.multiline = True
    if "min" in options and options["min"] is not None:
        entry.minimum = float(options["min"])
    if "max" in options and options["max"] is not None:
        entry.maximum = float(options["max"])
    if "step" in options and options["step"] is not None:
        entry.step = float(options["step"])
    if entry.control_kind == "string" and role in {"model", "source_image"}:
        entry.control_kind = "file" if role == "model" else "image"
    return entry


def _fallback_entry(role: str, value: Any) -> MappingEntry:
    """Build a MappingEntry from the captured widget value alone."""
    control_kind = infer_control_kind(value)
    entry = MappingEntry(
        semantic_role=role,
        node_id="",
        input_name="",
        control_kind=control_kind,
    )
    entry.data_type = _VALUE_TYPE_TO_DATA_TYPE.get(control_kind, "")
    if control_kind == "multiline":
        entry.multiline = True
    if control_kind == "string" and role in {"model", "source_image"}:
        entry.control_kind = "file" if role == "model" else "image"
    return entry


def _is_connection_spec(value: Any) -> bool:
    """True for ComfyUI connection specs like ``["937", 0]``."""
    return (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and isinstance(value[0], str)
    )


def derive_mapping_candidates(
    capture: dict[str, Any],
    *,
    node_def_provider: Optional[Callable[[str], Optional[tuple[dict, dict]]]] = None,
) -> tuple[dict[str, MappingEntry], str]:
    """Derive candidate mapping entries + output node id from a capture.

    * ``node_def_provider`` — optional ``callable(class_type) -> (required,
      optional)`` used to recover graph metadata. Defaults to a lazy probe
      of the ComfyUI node registry.
    * Returns ``(entries: {role: MappingEntry}, output_node_id: str)``.
      Entries carry node_id/input_name; metadata (enum/min/max/step/kind)
      comes from the graph — never from hardcoded lists.
    """
    prompt = extract_executable_prompt((capture or {}).get("api_prompt_json") or {})
    entries: dict[str, MappingEntry] = {}
    output_node_id = ""
    text_count = 0

    for node_id, node in prompt.items():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type", ""))
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        if class_type in OUTPUT_NODE_CLASSES and not output_node_id:
            output_node_id = str(node_id)

        defs: tuple[dict, dict] | None = None
        provider = node_def_provider or _probe_node_def
        try:
            probed = provider(class_type)
            if isinstance(probed, tuple) and len(probed) == 2:
                defs = (dict(probed[0] or {}), dict(probed[1] or {}))
        except Exception:
            defs = None

        for input_name, value in inputs.items():
            if _is_connection_spec(value):
                continue
            role = _INPUT_ROLE_HINTS.get(input_name)
            if role is None:
                if input_name in _TEXT_ROLES:
                    role = input_name
                elif input_name in (
                    "text", "string", "positive_prompt", "negative_prompt",
                ):
                    role = "negative_prompt" if text_count > 0 else "positive_prompt"
                else:
                    continue
            if input_name in ("text", "string") or role in _TEXT_ROLES:
                text_count += 1
            if role == "model" and role in entries:
                continue  # one model role per mapping
            if role in entries:
                continue  # first occurrence wins

            type_name, options = ("", {})
            if defs is not None:
                for defs_dict in defs:
                    if input_name in defs_dict:
                        type_name, options = _parse_type_spec(defs_dict[input_name])
                        break
            if type_name or options:
                entry = _entry_metadata_from_spec(role, value, type_name, options)
            else:
                entry = _fallback_entry(role, value)
            entry.node_id = str(node_id)
            entry.input_name = input_name
            entry.display_name = input_name
            entry.required = any(
                input_name in defs_dict for defs_dict in defs
            ) if defs is not None else False
            entries[role] = entry

    return entries, output_node_id


def extract_dependency_metadata(capture: dict[str, Any]) -> dict[str, Any]:
    """Extract dependency metadata (model stack + node classes) from a capture."""
    prompt = extract_executable_prompt((capture or {}).get("api_prompt_json") or {})
    node_classes: set[str] = set()
    for node in prompt.values():
        if isinstance(node, dict) and node.get("class_type"):
            node_classes.add(str(node["class_type"]))
    return {
        "model_stack": extract_model_stack(prompt),
        "node_classes": sorted(node_classes),
    }
