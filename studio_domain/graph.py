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
from workflow_metadata import (
    extract_model_stack,
    extract_ui_graph_model_refs,
    iter_graph_nodes,
)

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


_CORE_CNR_IDS = ("comfy-core", "comfyui-core")


def _identity_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _pack_identity_of(node: Any) -> dict[str, str]:
    """Return a node's captured non-core pack identity, or {} when absent.

    ComfyUI-Manager annotates UI nodes with ``properties.cnr_id`` (registry
    pack) or ``properties.aux_id`` (git/aux pack) plus ``properties.ver``.
    Core ids are ignored so they never become a fake pack. Only explicit
    identity fields are kept; a bare version on a core node yields {}.
    """
    if not isinstance(node, dict):
        return {}
    properties = node.get("properties")
    if not isinstance(properties, dict):
        return {}
    cnr_id = _identity_text(properties.get("cnr_id"))
    if cnr_id.lower() in _CORE_CNR_IDS:
        cnr_id = ""
    aux_id = _identity_text(properties.get("aux_id"))
    version = _identity_text(
        properties.get("ver")
        or properties.get("selected_version")
        or properties.get("version")
    )
    if not cnr_id and not aux_id:
        return {}
    identity: dict[str, str] = {}
    if cnr_id:
        identity["cnr_id"] = cnr_id
    if aux_id:
        identity["aux_id"] = aux_id
    if version:
        identity["version"] = version
    return identity


def _merge_identity(
    current: dict[str, str], incoming: dict[str, str]
) -> dict[str, str]:
    """Keep the first-seen value per identity key (existing behavior)."""
    if not current:
        return dict(incoming)
    merged = dict(current)
    for key in ("cnr_id", "aux_id", "version"):
        if not merged.get(key) and incoming.get(key):
            merged[key] = incoming[key]
    return merged


def _graph_node_types(graph: Any) -> set[str]:
    """Valid ``type`` values recorded anywhere in a UI/static graph.

    Walks nested group/subgraph containers, not just the top-level ``nodes``
    list, so Manager-missing nodes nested under ``extra.groupNodes`` /
    ``definitions.subgraphs`` still surface as dependencies.
    """
    classes: set[str] = set()
    for node in iter_graph_nodes(graph):
        node_type = node.get("type")
        if isinstance(node_type, str) and node_type:
            classes.add(node_type)
    return classes


def _collect_pack_identities(
    prompt: dict[str, Any], graph_json: Any, static_graph: Any = None
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    """Map node ids and class types to captured pack identities.

    The UI (static) graph carries ``properties.cnr_id``/``aux_id``; the
    executable API prompt usually does not, so the two are indexed separately
    and matched by node id first, then by class type. Both the ``graph_json``
    capture and its ``static_graph`` alias are scanned so identities survive
    whichever key the caller populated.
    """
    by_id: dict[str, dict[str, str]] = {}
    by_class: dict[str, dict[str, str]] = {}
    for graph in (graph_json, static_graph):
        # Nested group/subgraph nodes carry the same cnr_id/aux_id as top-level
        # nodes; collecting them here keeps Manager-missing nested packs
        # groupable by identity.
        for node in iter_graph_nodes(graph):
            identity = _pack_identity_of(node)
            if not identity:
                continue
            node_id = node.get("id")
            if node_id is not None:
                key = str(node_id)
                by_id[key] = _merge_identity(by_id.get(key, {}), identity)
            node_type = node.get("type")
            if isinstance(node_type, str) and node_type:
                by_class[node_type] = _merge_identity(
                    by_class.get(node_type, {}), identity
                )
    for node_id, node in prompt.items():
        identity = _pack_identity_of(node)
        if not identity:
            continue
        key = str(node_id)
        by_id[key] = _merge_identity(by_id.get(key, {}), identity)
        class_type = node.get("class_type") if isinstance(node, dict) else None
        if isinstance(class_type, str) and class_type:
            by_class[class_type] = _merge_identity(
                by_class.get(class_type, {}), identity
            )
    return by_id, by_class


def extract_dependency_metadata(capture: dict[str, Any]) -> dict[str, Any]:
    """Extract dependency metadata (model stack + node classes + pack ids).

    ``custom_node_requirements[class_type]`` preserves the pack identity
    recorded on the captured UI graph (``cnr_id``, ``aux_id``, ``version``) so
    the resolver and Manager install flow can resolve a missing class back to
    its pack.
    """
    api_prompt_json = (capture or {}).get("api_prompt_json") or {}
    prompt = extract_executable_prompt(api_prompt_json)
    graph_json = (capture or {}).get("graph_json")
    static_graph = (capture or {}).get("static_graph")
    node_classes: set[str] = set()
    for node in prompt.values():
        if isinstance(node, dict) and node.get("class_type"):
            node_classes.add(str(node["class_type"]))
    # ComfyUI-Manager scans the full UI graph, but the executable prompt drops
    # UI-only nodes and nodes whose pack/code is missing. Union the captured
    # graph node types so those dependencies still surface (the resolver's
    # shape classifier keeps true virtual panels out of the missing count).
    for graph in (graph_json, static_graph):
        node_classes |= _graph_node_types(graph)
    identity_by_id, identity_by_class = _collect_pack_identities(
        prompt, graph_json, static_graph
    )
    custom_node_requirements: dict[str, dict[str, str]] = {}
    for node_id, node in prompt.items():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type")
        if not class_type:
            continue
        class_type = str(class_type)
        identity = identity_by_id.get(str(node_id)) or identity_by_class.get(class_type)
        if identity:
            custom_node_requirements[class_type] = dict(identity)
    # Graph-only classes (UI/static nodes absent from the executable prompt)
    # still keep their captured pack identity so the resolver can group and
    # install them.
    for class_type in node_classes:
        if class_type in custom_node_requirements:
            continue
        identity = identity_by_class.get(class_type)
        if identity:
            custom_node_requirements[class_type] = dict(identity)
    model_stack = extract_model_stack(prompt)
    # Older API prompts can omit a custom loader's named widget value; the
    # persisted UI/static graph still records it. Merge those refs through the
    # same guards so custom loaders contribute models without treating prompt
    # text, URLs, or virtual panels as models.
    for graph_key in ("graph_json", "static_graph"):
        for ref in extract_ui_graph_model_refs((capture or {}).get(graph_key)):
            role = str(ref.get("role", ""))
            filename = ref.get("filename")
            if not isinstance(filename, str) or not filename:
                continue
            bucket = model_stack.setdefault(role, [])
            if filename not in bucket:
                bucket.append(filename)
    return {
        "model_stack": model_stack,
        "node_classes": sorted(node_classes),
        "custom_node_requirements": custom_node_requirements,
    }


def is_ui_workflow_format(graph_json: Any) -> bool:
    """True when graph_json is a ComfyUI UI-format workflow (nodes list).

    UI exports (file import, canvas save) carry ``{"nodes": [...], "links":
    [...]}``; API captures carry ``{node_id: {class_type, inputs}}``.
    """
    return (
        isinstance(graph_json, dict)
        and isinstance(graph_json.get("nodes"), list)
    )


_WIDGET_TYPE_NAMES = frozenset({
    "INT", "FLOAT", "NUMBER", "STRING", "BOOLEAN", "COMBO", "ENUM",
})


def _is_widget_input(ui_entry: Any, type_name: str, options: dict[str, Any]) -> bool:
    """Decide whether a node-def input is widget-backed.

    The UI ``inputs`` array marks widget-backed slots explicitly with a
    ``widget`` key; otherwise fall back to the type-spec heuristic (scalar /
    combo specs are widgets, custom UPPERCASE slot types are links).
    """
    if isinstance(ui_entry, dict) and "widget" in ui_entry:
        return True
    if type_name in _WIDGET_TYPE_NAMES:
        return True
    if not isinstance(options, dict):
        return False
    return any(
        key in options
        for key in ("min", "max", "step", "multiline", "enum", "options")
    )


def ui_graph_to_api_prompt(
    graph_json: Any,
    *,
    node_def_provider: Optional[Callable[[str], Optional[tuple[dict, dict]]]] = None,
) -> dict[str, dict[str, Any]]:
    """Convert a ComfyUI UI-format workflow to an API-format prompt.

    Maps each UI node ``{id, type, inputs: [{name, link, widget?}],
    widgets_values}`` to ``{node_id: {class_type, inputs}}`` using the same
    positional widget semantics as the canvas (``comparison._ensure_api_format``
    pattern): linked slots become ``[origin_id, origin_slot]`` connection
    specs and consume no widget value; unconnected widget-backed inputs
    consume ``widgets_values`` in node-def order. Pure-widget nodes (empty
    UI ``inputs`` array, e.g. seed/sampler selectors) resolve through the
    node-def input order, which requires the registry (or an injected
    provider); without defs their values are unrecoverable and skipped.

    Never raises on malformed graphs — unparseable nodes/links are skipped.
    """
    if not is_ui_workflow_format(graph_json):
        return {}
    nodes = graph_json.get("nodes") or []
    links = graph_json.get("links") or []

    # Index links by (target_id, target_slot) → (origin_id, origin_slot).
    targets: dict[tuple[str, int], tuple[str, int]] = {}
    if isinstance(links, list):
        for link in links:
            try:
                if not isinstance(link, (list, tuple)) or len(link) < 5:
                    continue
                _lid, origin_id, origin_slot, target_id, target_slot = link[:5]
                targets[(str(target_id), int(target_slot))] = (
                    str(origin_id), int(origin_slot)
                )
            except (TypeError, ValueError):
                continue

    prompt: dict[str, dict[str, Any]] = {}
    provider = node_def_provider or _probe_node_def
    for node in nodes:
        try:
            if not isinstance(node, dict):
                continue
            node_id = node.get("id")
            class_type = node.get("type")
            if node_id is None or not class_type:
                continue
            node_id_str = str(node_id)
            class_type_str = str(class_type)

            ui_inputs = node.get("inputs")
            ui_by_name: dict[str, dict[str, Any]] = {}
            ui_by_slot: dict[int, dict[str, Any]] = {}
            if isinstance(ui_inputs, list):
                for slot, entry in enumerate(ui_inputs):
                    if not isinstance(entry, dict):
                        continue
                    name = entry.get("name")
                    if isinstance(name, str) and name:
                        ui_by_name[name] = entry
                    ui_by_slot[slot] = entry

            widgets_values = node.get("widgets_values")
            widget_pool = list(widgets_values) if isinstance(widgets_values, list) else []
            wi = 0

            def _next_widget() -> Any:
                nonlocal wi
                if wi < len(widget_pool):
                    value = widget_pool[wi]
                    wi += 1
                    return value
                return None

            defs: tuple[dict, dict] | None = None
            try:
                probed = provider(class_type_str)
                if isinstance(probed, tuple) and len(probed) == 2:
                    defs = (dict(probed[0] or {}), dict(probed[1] or {}))
            except Exception:
                defs = None

            inputs: dict[str, Any] = {}
            consumed_defs: set[str] = set()
            if defs is not None:
                for defs_dict in defs:
                    for input_name, spec in defs_dict.items():
                        if input_name in consumed_defs:
                            continue
                        consumed_defs.add(input_name)
                        type_name, options = _parse_type_spec(spec)
                        ui_entry = ui_by_name.get(input_name)
                        link = ui_entry.get("link") if isinstance(ui_entry, dict) else None
                        if link is not None and isinstance(ui_entry, dict):
                            # Linked slot: resolve origin via slot index.
                            slot = next(
                                (s for s, e in ui_by_slot.items() if e is ui_entry),
                                None,
                            )
                            conn = targets.get((node_id_str, slot)) if slot is not None else None
                            if conn is not None:
                                inputs[input_name] = [conn[0], conn[1]]
                            else:
                                inputs[input_name] = None
                        elif _is_widget_input(ui_entry, type_name, options):
                            inputs[input_name] = _next_widget()
                        else:
                            inputs[input_name] = None

            # Slots the defs did not cover (unknown class or def drift):
            # linked slots still resolve; widget-backed unconnected slots
            # consume positionally (comparison._ensure_api_format pattern).
            for name, ui_entry in ui_by_name.items():
                if name in inputs:
                    continue
                link = ui_entry.get("link")
                if link is not None:
                    slot = next(
                        (s for s, e in ui_by_slot.items() if e is ui_entry),
                        None,
                    )
                    conn = targets.get((node_id_str, slot)) if slot is not None else None
                    inputs[name] = [conn[0], conn[1]] if conn is not None else None
                elif "widget" in ui_entry:
                    inputs[name] = _next_widget()
                else:
                    inputs[name] = None

            prompt[node_id_str] = {"class_type": class_type_str, "inputs": inputs}
        except Exception:
            continue
    return prompt
