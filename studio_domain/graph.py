"""Graph introspection for the Workflow domain.

Pure functions over capture dicts — no ComfyUI runtime required. Where the
ComfyUI ``nodes`` module is available it is probed lazily (inside functions,
guarded) to recover graph-provided metadata (enum choices, min/max/step,
multiline); otherwise metadata is inferred from widget values alone.

Never hardcode generic sampler/scheduler lists: enum options always come
from the graph itself (node definitions or the captured widget value).
"""

from __future__ import annotations

import copy
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
    # Some custom text nodes expose their positive text widget as ``prompt``
    # rather than ComfyUI's usual ``text``.  Keep the internal graph role
    # consistent with the other positive-text candidates.
    "prompt": "positive_prompt",
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


#: Entry kinds that bind a control to a node input (as opposed to a node
#: output). All of them must resolve through :func:`resolve_binding_target`.
INPUT_BINDING_KINDS = frozenset({"node_input", "widget", "node"})


def _top_level_nodes_by_id(ui_graph: Any) -> dict[str, dict[str, Any]]:
    """Map top-level UI node id → node dict (outer containers only).

    Inner subgraph nodes reuse local ids that collide across definitions, so
    outer-container lookup must never use the recursive ``iter_graph_nodes``
    walk — only the top-level ``nodes`` list.
    """
    out: dict[str, dict[str, Any]] = {}
    try:
        nodes = ui_graph.get("nodes") if isinstance(ui_graph, dict) else None
        if not isinstance(nodes, list):
            return out
        for node in nodes:
            if not isinstance(node, dict):
                continue
            nid = node.get("id")
            if nid is None:
                continue
            out[str(nid)] = node
    except Exception:
        pass
    return out


def _subgraph_defs_by_id(ui_graph: Any) -> dict[str, dict[str, Any]]:
    """Map subgraph definition id → definition dict.

    Handles ``definitions.subgraphs`` as a list or dict (ComfyUI frontend
    uses a list; be tolerant). Never raises.
    """
    out: dict[str, dict[str, Any]] = {}
    try:
        if not isinstance(ui_graph, dict):
            return out
        definitions = ui_graph.get("definitions")
        if not isinstance(definitions, dict):
            return out
        subgraphs = definitions.get("subgraphs")
        if isinstance(subgraphs, dict):
            items = list(subgraphs.values())
        elif isinstance(subgraphs, (list, tuple)):
            items = list(subgraphs)
        else:
            return out
        for sg in items:
            if not isinstance(sg, dict):
                continue
            sg_id = sg.get("id")
            if sg_id is None:
                continue
            out[str(sg_id)] = sg
    except Exception:
        pass
    return out


def _subgraph_links(subgraph_def: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize subgraph links to dicts with origin/target ids and slots.

    ComfyUI serializes subgraph links either as dicts
    (``{id, origin_id, origin_slot, target_id, target_slot}``) or as legacy
    lists (``[id, origin_id, origin_slot, target_id, target_slot]``). Never
    raises.
    """
    out: list[dict[str, Any]] = []
    try:
        links = subgraph_def.get("links")
        if not isinstance(links, (list, tuple)):
            return out
        for link in links:
            try:
                if isinstance(link, dict):
                    out.append({
                        "origin_id": link.get("origin_id"),
                        "origin_slot": link.get("origin_slot"),
                        "target_id": link.get("target_id"),
                        "target_slot": link.get("target_slot"),
                    })
                elif isinstance(link, (list, tuple)) and len(link) >= 5:
                    out.append({
                        "origin_id": link[1],
                        "origin_slot": link[2],
                        "target_id": link[3],
                        "target_slot": link[4],
                    })
            except Exception:
                continue
    except Exception:
        pass
    return out


def _outer_input_index(outer_node: dict[str, Any], input_name: str) -> Optional[int]:
    """Index of ``input_name`` in an outer subgraph container's inputs list.

    Matches by slot ``name``, ``widget.name``, or human ``label``
    (case-insensitive label fallback covers wizard widget names like
    ``seed_1`` vs inner ``seed``). Returns None when absent. Never raises.
    """
    try:
        if not isinstance(outer_node, dict) or not input_name:
            return None
        ui_inputs = outer_node.get("inputs")
        if not isinstance(ui_inputs, list):
            return None
        lowered = str(input_name).lower()
        for idx, entry in enumerate(ui_inputs):
            if not isinstance(entry, dict):
                continue
            if entry.get("name") == input_name:
                return idx
            widget = entry.get("widget")
            if isinstance(widget, dict) and widget.get("name") == input_name:
                return idx
        for idx, entry in enumerate(ui_inputs):
            if not isinstance(entry, dict):
                continue
            label = entry.get("label")
            if isinstance(label, str) and label.lower() == lowered:
                return idx
    except Exception:
        pass
    return None


def _inner_input_name_by_slot(
    subgraph_def: dict[str, Any], inner_id_str: str, target_slot: Any
) -> Optional[str]:
    """Input name of an inner subgraph node at ``target_slot`` (list order)."""
    try:
        try:
            slot_idx = int(target_slot)
        except (TypeError, ValueError):
            return None
        for node in subgraph_def.get("nodes") or []:
            if not isinstance(node, dict):
                continue
            if str(node.get("id")) != inner_id_str:
                continue
            ui_inputs = node.get("inputs")
            if not isinstance(ui_inputs, list):
                return None
            if 0 <= slot_idx < len(ui_inputs):
                entry = ui_inputs[slot_idx]
                if isinstance(entry, dict) and isinstance(entry.get("name"), str):
                    return str(entry["name"])
            return None
    except Exception:
        pass
    return None


def _resolve_outer_widget_to_expanded(
    prompt: dict[str, Any],
    ui_graph: Any,
    outer_id_str: str,
    input_name: str,
) -> Optional[tuple[str, str]]:
    """Map an outer subgraph widget to its expanded executable target.

    Returns ``(expanded_node_id, inner_input_name)`` like ``"30:10"`` /
    ``"unet_name"`` when the outer container's widget feeds an inner node
    through the subgraph ``inputNode`` (``-10``) links and that expanded node
    exists in the prompt. Returns None when not a subgraph outer binding.
    Never raises.
    """
    try:
        if not isinstance(prompt, dict) or not outer_id_str or not input_name:
            return None
        if ":" in outer_id_str:
            return None
        top_nodes = _top_level_nodes_by_id(ui_graph)
        outer_node = top_nodes.get(outer_id_str)
        if not isinstance(outer_node, dict):
            return None
        defs = _subgraph_defs_by_id(ui_graph)
        if not defs:
            return None
        outer_type = outer_node.get("type")
        sg = defs.get(str(outer_type)) if outer_type is not None else None
        if not isinstance(sg, dict):
            return None
        outer_idx = _outer_input_index(outer_node, input_name)
        if outer_idx is None:
            return None
        input_node = sg.get("inputNode")
        input_node_id = (
            input_node.get("id") if isinstance(input_node, dict) else -10
        )
        for link in _subgraph_links(sg):
            try:
                if str(link.get("origin_id")) != str(input_node_id):
                    continue
                origin_slot = link.get("origin_slot")
                if origin_slot is None:
                    continue
                try:
                    if int(origin_slot) != int(outer_idx):
                        continue
                except (TypeError, ValueError):
                    continue
                target_id = link.get("target_id")
                if target_id is None:
                    continue
                inner_id_str = str(target_id)
                inner_input = _inner_input_name_by_slot(
                    sg, inner_id_str, link.get("target_slot")
                )
                if not inner_input:
                    continue
                expanded = f"{outer_id_str}:{inner_id_str}"
                node = prompt.get(expanded)
                if not isinstance(node, dict):
                    continue
                inputs = node.get("inputs")
                if isinstance(inputs, dict) and inner_input in inputs:
                    return (expanded, inner_input)
            except Exception:
                continue
    except Exception:
        pass
    return None


def _expanded_candidates_for_inner(
    prompt: dict[str, Any], inner_id_str: str, input_name: str
) -> list[str]:
    """Expanded prompt keys for an inner-local subgraph node id.

    Matches keys ending in ``":{inner_id}"`` whose executable inputs contain
    ``input_name``. Never raises.
    """
    out: list[str] = []
    try:
        if not isinstance(prompt, dict) or not inner_id_str or ":" in inner_id_str:
            return out
        suffix = f":{inner_id_str}"
        for key, node in prompt.items():
            try:
                if not isinstance(key, str) or not key.endswith(suffix):
                    continue
                if not isinstance(node, dict):
                    continue
                inputs = node.get("inputs")
                if isinstance(inputs, dict) and input_name in inputs:
                    out.append(key)
            except Exception:
                continue
    except Exception:
        pass
    return out


def subgraph_resolve_output(
    prompt: dict[str, Any], ui_graph: Any, output_node_id: Any
) -> Optional[str]:
    """Resolve a wizard output node id to its executable prompt key.

    Handles expanded ids directly, outer subgraph containers (via the
    subgraph ``outputNode`` mapping), and inner-local ids (unique suffix
    match). Returns the expanded key or None. Never raises.
    """
    try:
        oid = str(output_node_id or "")
        if not oid or not isinstance(prompt, dict):
            return None
        if oid in prompt:
            return oid
        if ":" in oid:
            return None
        top_nodes = _top_level_nodes_by_id(ui_graph)
        outer_node = top_nodes.get(oid)
        if isinstance(outer_node, dict):
            defs = _subgraph_defs_by_id(ui_graph)
            outer_type = outer_node.get("type")
            sg = defs.get(str(outer_type)) if outer_type is not None else None
            if isinstance(sg, dict):
                output_node = sg.get("outputNode")
                output_node_id_inner = (
                    output_node.get("id") if isinstance(output_node, dict) else -20
                )
                for link in _subgraph_links(sg):
                    try:
                        if str(link.get("target_id")) != str(output_node_id_inner):
                            continue
                        inner_id_str = str(link.get("origin_id"))
                        expanded = f"{oid}:{inner_id_str}"
                        if expanded in prompt:
                            return expanded
                    except Exception:
                        continue
        suffix = f":{oid}"
        matches = [
            key for key in prompt.keys()
            if isinstance(key, str) and key.endswith(suffix)
        ]
        if len(matches) == 1:
            return matches[0]
    except Exception:
        pass
    return None


def subgraph_node_present(
    prompt: dict[str, Any], ui_graph: Any, node_id: Any
) -> bool:
    """True when ``node_id`` is executable directly or via subgraph mapping."""
    try:
        nid = str(node_id or "")
        if not nid or not isinstance(prompt, dict):
            return False
        if nid in prompt:
            return True
        if ":" in nid:
            return False
        top_nodes = _top_level_nodes_by_id(ui_graph)
        if nid in top_nodes:
            outer_node = top_nodes[nid]
            defs = _subgraph_defs_by_id(ui_graph)
            outer_type = outer_node.get("type") if isinstance(outer_node, dict) else None
            if isinstance(outer_type, str) and outer_type in defs:
                prefix = f"{nid}:"
                for key in prompt.keys():
                    if isinstance(key, str) and key.startswith(prefix):
                        return True
        suffix = f":{nid}"
        for key in prompt.keys():
            if isinstance(key, str) and key.endswith(suffix):
                return True
    except Exception:
        pass
    return False


def resolve_binding_target(
    prompt: dict[str, Any],
    node_id: Any,
    input_name: str,
    *,
    ui_graph: Any = None,
    node_def_provider: Optional[Callable[[str], Optional[tuple]]] = None,
) -> dict[str, Any]:
    """Resolve a (node_id, input_name) binding against every place a ComfyUI
    value can live — generically, with no per-node-type knowledge.

    A binding is *resolvable* only when ``input_name`` is a key of the
    node's executable ``inputs`` dict, because that is the single location
    both gating (``services.derive_version_state``) and execution
    (``studio_workflow_run.apply_workflow_values_to_prompt``) read and
    write. ``location`` additionally reports where else the name was found
    so callers can explain *why* a binding fails (e.g. a pure-widget or
    hidden-state value that never reaches the executable prompt).

    Subgraph workflows expand inner nodes to ``"<outer>:<inner>"`` prompt
    keys (ComfyUI ``graphToPrompt``). Wizard bindings captured from the live
    canvas use UI ids — an outer container id (``"30"``) or an inner-local id
    (``"10"``) — neither of which appears verbatim in the prompt. When the
    direct lookup fails and a UI graph is available, resolution additionally
    tries the outer-widget → expanded mapping (via subgraph ``inputNode``
    links) and the unique inner-local → expanded suffix match, reporting the
    normalized ``expanded_node_id`` / ``expanded_input_name`` on success.

    Returns a dict with:

    * ``resolvable`` — True only when the name is an executable-input key.
    * ``location`` — ``"inputs"`` / ``"node_def"`` / ``"ui_widget"`` / None.
    * ``linked`` / ``upstream_node_id`` — True and the source node id when
      the executable input is a ``[node_id, slot]`` connection spec, meaning
      writing the control replaces that link.
    * ``node_present`` — False when the node id is absent from the prompt.
    * ``node_def_available`` — whether a node definition could be probed.
    * ``expanded_node_id`` / ``expanded_input_name`` / ``via_subgraph`` —
      normalized executable target when resolution went through a subgraph.

    Never raises.
    """
    node_id_str = str(node_id)
    result: dict[str, Any] = {
        "resolvable": False,
        "location": None,
        "linked": False,
        "upstream_node_id": None,
        "node_present": False,
        "node_def_available": False,
    }
    try:
        node = prompt.get(node_id_str) if isinstance(prompt, dict) else None
        if isinstance(node, dict):
            result["node_present"] = True
            inputs = node.get("inputs")
            if isinstance(inputs, dict) and input_name in inputs:
                result["resolvable"] = True
                result["location"] = "inputs"
                value = inputs.get(input_name)
                if _is_connection_spec(value):
                    result["linked"] = True
                    try:
                        result["upstream_node_id"] = str(value[0])  # type: ignore[index]
                    except Exception:
                        pass
                return result

            provider = node_def_provider or _probe_node_def
            try:
                probed = provider(str(node.get("class_type", "")))
                if isinstance(probed, tuple) and len(probed) == 2:
                    result["node_def_available"] = True
                    for defs_dict in probed:
                        if isinstance(defs_dict, dict) and input_name in defs_dict:
                            result["location"] = "node_def"
                            return result
            except Exception:
                pass

            if _ui_node_has_widget(ui_graph, node_id_str, input_name):
                result["location"] = "ui_widget"
            return result
        # Direct node absent: try subgraph-aware resolution before failing.
        if isinstance(prompt, dict) and ui_graph is not None and ":" not in node_id_str:
            expanded = _resolve_outer_widget_to_expanded(
                prompt, ui_graph, node_id_str, input_name
            )
            if expanded is not None:
                expanded_id, expanded_input = expanded
                target_node = prompt.get(expanded_id)
                if isinstance(target_node, dict):
                    result["node_present"] = True
                    result["resolvable"] = True
                    result["location"] = "inputs"
                    result["expanded_node_id"] = expanded_id
                    result["expanded_input_name"] = expanded_input
                    result["via_subgraph"] = "outer"
                    target_inputs = target_node.get("inputs")
                    value = target_inputs.get(expanded_input) if isinstance(target_inputs, dict) else None
                    if _is_connection_spec(value):
                        result["linked"] = True
                        try:
                            result["upstream_node_id"] = str(value[0])  # type: ignore[index]
                        except Exception:
                            pass
                    return result
            candidates = _expanded_candidates_for_inner(
                prompt, node_id_str, input_name
            )
            if len(candidates) == 1:
                expanded_id = candidates[0]
                target_node = prompt.get(expanded_id)
                result["node_present"] = True
                result["resolvable"] = True
                result["location"] = "inputs"
                result["expanded_node_id"] = expanded_id
                result["expanded_input_name"] = input_name
                result["via_subgraph"] = "inner"
                value = None
                if isinstance(target_node, dict):
                    target_inputs = target_node.get("inputs")
                    if isinstance(target_inputs, dict):
                        value = target_inputs.get(input_name)
                if _is_connection_spec(value):
                    result["linked"] = True
                    try:
                        result["upstream_node_id"] = str(value[0])  # type: ignore[index]
                    except Exception:
                        pass
                return result
            if len(candidates) > 1:
                result["subgraph_candidates"] = candidates
            elif subgraph_node_present(prompt, ui_graph, node_id_str):
                result["node_present"] = True

            provider = node_def_provider or _probe_node_def
            try:
                probed_outer = None
                top_nodes = _top_level_nodes_by_id(ui_graph)
                outer_node = top_nodes.get(node_id_str)
                if isinstance(outer_node, dict):
                    probed_outer = provider(str(outer_node.get("type", "")))
                if isinstance(probed_outer, tuple) and len(probed_outer) == 2:
                    result["node_def_available"] = True
            except Exception:
                pass
            if _ui_node_has_widget(ui_graph, node_id_str, input_name):
                result["location"] = "ui_widget"
            return result
        # No subgraph context (or already-expanded id): generic UI-widget
        # reporting for the absent node. ``node`` is not a dict here (the
        # dict case returned above); this is the terminal fall-through.
        if _ui_node_has_widget(ui_graph, node_id_str, input_name):
            result["location"] = "ui_widget"
        return result
    except Exception:
        return result


def _ui_node_has_widget(ui_graph: Any, node_id_str: str, input_name: str) -> bool:
    """True when the UI/static graph shows a widget named ``input_name`` on
    the node — via its ``inputs`` slot list (``name`` or ``widget.name``) or
    a dict entry inside ``widgets_values``.

    Structural check only; knows nothing about specific node types.
    """
    try:
        for node in iter_graph_nodes(ui_graph):
            if not isinstance(node, dict):
                continue
            if str(node.get("id")) != node_id_str:
                continue
            ui_inputs = node.get("inputs")
            if isinstance(ui_inputs, list):
                for entry in ui_inputs:
                    if not isinstance(entry, dict):
                        continue
                    if entry.get("name") == input_name:
                        return True
                    widget = entry.get("widget")
                    if isinstance(widget, dict) and widget.get("name") == input_name:
                        return True
            widgets_values = node.get("widgets_values")
            if isinstance(widgets_values, list):
                for value in widgets_values:
                    if isinstance(value, dict) and input_name in value:
                        return True
            return False
    except Exception:
        pass
    return False


def find_binding_candidates(
    prompt: dict[str, Any],
    input_name: str,
    *,
    ui_graph: Any = None,
    node_def_provider: Optional[Callable[[str], Optional[tuple]]] = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """List resolvable (node_id, input_name) bindings for ``input_name``.

    Executable-input matches come first (in prompt order), node-def-only
    declarations second. Used to suggest alternatives when a binding fails
    validation. Generic — no role or node-type knowledge. Never raises.
    """
    candidates: list[dict[str, Any]] = []
    try:
        if not isinstance(prompt, dict) or not input_name:
            return candidates
        for nid, node in prompt.items():
            if len(candidates) >= limit:
                break
            if not isinstance(node, dict):
                continue
            inputs = node.get("inputs")
            if isinstance(inputs, dict) and input_name in inputs:
                value = inputs.get(input_name)
                upstream: Any = None
                if _is_connection_spec(value):
                    try:
                        upstream = str(value[0])  # type: ignore[index]
                    except Exception:
                        upstream = None
                candidates.append({
                    "node_id": str(nid),
                    "input_name": input_name,
                    "via": "inputs",
                    "linked": bool(_is_connection_spec(value)),
                    "upstream_node_id": upstream,
                })
        if len(candidates) >= limit:
            return candidates
        provider = node_def_provider or _probe_node_def
        for nid, node in prompt.items():
            if len(candidates) >= limit:
                break
            if not isinstance(node, dict):
                continue
            if any(c["node_id"] == str(nid) for c in candidates):
                continue
            try:
                probed = provider(str(node.get("class_type", "")))
            except Exception:
                continue
            if not (isinstance(probed, tuple) and len(probed) == 2):
                continue
            for defs_dict in probed:
                if isinstance(defs_dict, dict) and input_name in defs_dict:
                    candidates.append({
                        "node_id": str(nid),
                        "input_name": input_name,
                        "via": "node_def",
                        "linked": False,
                        "upstream_node_id": None,
                    })
                    break
    except Exception:
        pass
    return candidates


def _probe_node_def(
    class_type: str,
) -> Optional[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]:
    """Lazily probe the ComfyUI node registry for input definitions.

    Returns ``(required, optional, hidden)`` dicts of input name → type
    spec, or ``None`` when the registry is unavailable or the class is
    unknown. Never raises.
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
            dict(spec.get("hidden") or {}),
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
        if (
            len(spec) == 2
            and isinstance(spec[0], (list, tuple))
            and isinstance(spec[1], dict)
        ):
            options = dict(spec[1])
            options.setdefault("enum", list(spec[0]))
            return "ENUM", options
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
    node_def_provider: Optional[Callable[[str], Optional[tuple]]] = None,
) -> tuple[dict[str, MappingEntry], str]:
    """Derive candidate mapping entries + output node id from a capture.

    * ``node_def_provider`` — optional ``callable(class_type) -> (required,
      optional)`` used to recover graph metadata. Defaults to a lazy probe
      of the ComfyUI node registry.
    * Returns ``(entries: {role: MappingEntry}, output_node_id: str)``.
      Entries carry node_id/input_name; metadata (enum/min/max/step/kind)
      comes from the graph — never from hardcoded lists.
    """
    capture = capture or {}
    prompt = extract_executable_prompt(capture.get("api_prompt_json") or {})
    # UI-format captures can retain an API prompt produced by an older
    # ComfyUI/widget ordering.  The graph is the source of truth for those
    # captures; regenerate it before deriving bindings so candidates and their
    # metadata point at the prompt that will actually be executed.
    graph_json = capture.get("graph_json")
    if is_ui_workflow_format(graph_json):
        regenerated = ui_graph_to_api_prompt(
            graph_json, node_def_provider=node_def_provider
        )
        if regenerated:
            prompt = regenerated
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
            # Hidden defs (len-3 providers) never become mapping controls;
            # only required/optional participate here.
            if isinstance(probed, tuple) and len(probed) in (2, 3):
                defs = (dict(probed[0] or {}), dict(probed[1] or {}))
        except Exception:
            defs = None

        for input_name, value in inputs.items():
            if _is_connection_spec(value):
                continue
            if (
                value is None
                and defs is not None
                and input_name in defs[1]
            ):
                continue
            role = _INPUT_ROLE_HINTS.get(input_name)
            if role is None:
                if input_name in _TEXT_ROLES:
                    role = input_name
                elif input_name in (
                    "text", "string", "prompt", "positive_prompt", "negative_prompt",
                ):
                    role = "negative_prompt" if text_count > 0 else "positive_prompt"
                else:
                    continue
            if input_name in ("text", "string", "prompt") or role in _TEXT_ROLES:
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
            # An empty negative prompt is valid input to every text encoder
            # (upstream tokenizers even substitute a blank for it), so the
            # negative role is never required even when the node declares
            # the slot required. The positive prompt keeps the def's flag.
            entry.required = (
                role != "negative_prompt"
                and defs is not None
                and any(input_name in defs_dict for defs_dict in defs)
            )
            entries[role] = entry

    return entries, output_node_id


def _probe_return_types(class_type: str) -> Optional[list]:
    """Lazily probe the ComfyUI node registry for RETURN_TYPES.

    Returns the RETURN_TYPES list, or ``None`` when the registry is
    unavailable or the class is unknown. Never raises. Mirrors the
    guarded lazy-probe pattern of :func:`_probe_node_def`.
    """
    try:
        import nodes  # type: ignore[import-not-found]
    except Exception:
        return None
    try:
        cls = nodes.NODE_CLASS_MAPPINGS.get(str(class_type or ""))
        if cls is None:
            return None
        returns = getattr(cls, "RETURN_TYPES", None)
        if not isinstance(returns, (list, tuple)):
            return None
        return list(returns)
    except Exception:
        return None


def node_has_image_output(class_type: str, *, return_types_provider=None) -> bool:
    """True when ``class_type`` can emit images.

    Fixed allowlist (``OUTPUT_NODE_CLASSES``) plus runtime capability:
    a node whose ``RETURN_TYPES`` contains ``IMAGE`` is output-capable
    regardless of whether its class is known to the allowlist (custom
    compare/preview nodes such as RGThree or Pixaroma variants). The
    registry is probed lazily so registry-less contexts keep working.
    Never raises.
    """
    name = str(class_type or "")
    if not name:
        return False
    if name in OUTPUT_NODE_CLASSES:
        return True
    try:
        returns = None
        if callable(return_types_provider):
            returns = return_types_provider(name)
        elif return_types_provider is None:
            returns = _probe_return_types(name)
        if not isinstance(returns, (list, tuple)):
            return False
        return any(str(r).upper() == "IMAGE" for r in returns)
    except Exception:
        return False


def derive_output_node_ids_from_prompt(
    prompt: Any, *, explicit_output_id: str = "", return_types_provider=None
) -> list:
    """All image-capable node ids in graph order; explicit mapping output first.

    Unlike :func:`derive_mapping_candidates` (single first-allowlist-match
    ``output_node_id``), this collects EVERY node able to emit images so
    result collection is not limited to three hardcoded classes. Order is
    graph order with the explicit mapping output hoisted first when present.
    Deduped. Never raises.
    """
    ids: list = []
    try:
        items = prompt.items() if isinstance(prompt, dict) else []
        for node_id, node in items:
            if not isinstance(node, dict):
                continue
            if node_has_image_output(
                str(node.get("class_type", "") or ""),
                return_types_provider=return_types_provider,
            ):
                nid = str(node_id)
                if nid and nid not in ids:
                    ids.append(nid)
    except Exception:
        pass
    explicit = str(explicit_output_id or "")
    if explicit and explicit in ids:
        ids = [explicit] + [i for i in ids if i != explicit]
    return ids


def derive_output_node_ids(
    capture: Any, *, explicit_output_id: str = "", return_types_provider=None
) -> list:
    """Capture-shaped wrapper around :func:`derive_output_node_ids_from_prompt`.

    Applies the same UI-graph regeneration as :func:`derive_mapping_candidates`
    so candidates point at the prompt that will actually execute. Never raises.
    """
    try:
        capture = capture or {}
        prompt = extract_executable_prompt(capture.get("api_prompt_json") or {})
        graph_json = capture.get("graph_json")
        if is_ui_workflow_format(graph_json):
            regenerated = ui_graph_to_api_prompt(graph_json)
            if regenerated:
                prompt = regenerated
        return derive_output_node_ids_from_prompt(
            prompt,
            explicit_output_id=explicit_output_id,
            return_types_provider=return_types_provider,
        )
    except Exception:
        return []


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


def ui_graph_has_nested_containers(graph_json: Any) -> bool:
    """True when a UI graph nests executable nodes below containers.

    Covers current subgraph definitions (``definitions.subgraphs``) and
    legacy group nodes (``extra.groupNodes``). ``ui_graph_to_api_prompt``
    only converts the top-level ``nodes`` list, so regenerating the prompt
    from such a graph would silently drop the nested nodes — callers that
    rebuild runtime state from the UI graph must keep the stored expanded
    prompt instead. Never raises.
    """
    try:
        if not isinstance(graph_json, dict):
            return False
        definitions = graph_json.get("definitions")
        if isinstance(definitions, dict):
            subgraphs = definitions.get("subgraphs")
            if isinstance(subgraphs, dict) and subgraphs:
                return True
            if isinstance(subgraphs, (list, tuple)) and len(subgraphs) > 0:
                return True
        extra = graph_json.get("extra")
        if isinstance(extra, dict):
            group_nodes = extra.get("groupNodes")
            if isinstance(group_nodes, dict) and group_nodes:
                return True
            if isinstance(group_nodes, (list, tuple)) and len(group_nodes) > 0:
                return True
    except Exception:
        pass
    return False


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
    node_def_provider: Optional[Callable[[str], Optional[tuple]]] = None,
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
            hidden_defs: dict[str, Any] = {}
            try:
                probed = provider(class_type_str)
                if isinstance(probed, tuple) and len(probed) in (2, 3):
                    defs = (dict(probed[0] or {}), dict(probed[1] or {}))
                    if len(probed) == 3 and isinstance(probed[2], dict):
                        hidden_defs = dict(probed[2] or {})
            except Exception:
                defs = None

            inputs: dict[str, Any] = {}
            consumed_defs: set[str] = set()

            def _ui_entry_for(path: str) -> dict[str, Any] | None:
                entry = ui_by_name.get(path)
                if entry is not None:
                    return entry
                if "." in path:
                    return ui_by_name.get(path.rsplit(".", 1)[-1])
                return None

            def _connection_for(path: str) -> list[Any] | None:
                ui_entry = _ui_entry_for(path)
                if not isinstance(ui_entry, dict) or ui_entry.get("link") is None:
                    return None
                slot = next(
                    (s for s, entry in ui_by_slot.items() if entry is ui_entry),
                    None,
                )
                conn = targets.get((node_id_str, slot)) if slot is not None else None
                return [conn[0], conn[1]] if conn is not None else None

            def _consume_dynamic_input(
                path: str,
                spec: Any,
            ) -> None:
                type_name, options = _parse_type_spec(spec)
                ui_entry = _ui_entry_for(path)
                if isinstance(ui_entry, dict) and ui_entry.get("link") is not None:
                    if "widget" in ui_entry:
                        _next_widget()
                    if options.get("control_after_generate"):
                        _next_widget()
                    inputs[path] = _connection_for(path)
                    return

                if type_name.startswith("COMFY_DYNAMICCOMBO"):
                    selected = _next_widget()
                    inputs[path] = selected
                    selected_option = next(
                        (
                            option for option in (options.get("options") or [])
                            if isinstance(option, dict)
                            and option.get("key") == selected
                        ),
                        None,
                    )
                    option_inputs = (
                        selected_option.get("inputs", {})
                        if isinstance(selected_option, dict)
                        else {}
                    )
                    for child_defs in (
                        option_inputs.get("required", {}),
                        option_inputs.get("optional", {}),
                    ):
                        if not isinstance(child_defs, dict):
                            continue
                        for child_name, child_spec in child_defs.items():
                            _consume_dynamic_input(
                                f"{path}.{child_name}", child_spec
                            )
                    return

                inputs[path] = _next_widget()
                if options.get("control_after_generate"):
                    _next_widget()

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
                            # ComfyUI retains a widget value even after that
                            # input is linked (e.g. KSampler seed). Consume it
                            # to preserve positional widget alignment, but keep
                            # the graph link authoritative in the API prompt.
                            if "widget" in ui_entry:
                                _next_widget()
                            if options.get("control_after_generate"):
                                _next_widget()
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
                        elif type_name.startswith("COMFY_DYNAMICCOMBO"):
                            _consume_dynamic_input(input_name, spec)
                        elif _is_widget_input(ui_entry, type_name, options):
                            inputs[input_name] = _next_widget()
                            if options.get("control_after_generate"):
                                _next_widget()
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

            # Hidden inputs (frontend-injected state such as Pixaroma seed /
            # orientation state) have no widgets or slots, so nothing above
            # fills them. Recover them from the UI node's stored
            # properties (case-insensitive, verbatim — exactly what the
            # frontend would inject), else from an explicit schema default.
            # Otherwise leave them missing so downstream validation still
            # fails closed. Never consumes widgets or invents values.
            if hidden_defs:
                properties = node.get("properties")
                lowered_props = (
                    {str(k).lower(): v for k, v in properties.items()}
                    if isinstance(properties, dict) else {}
                )
                for hidden_name, hidden_spec in hidden_defs.items():
                    if hidden_name in inputs:
                        continue
                    prop_value = lowered_props.get(str(hidden_name).lower())
                    if isinstance(prop_value, str):
                        inputs[hidden_name] = prop_value
                        continue
                    _, hidden_options = _parse_type_spec(hidden_spec)
                    hidden_default = hidden_options.get("default")
                    if hidden_default is not None:
                        inputs[hidden_name] = copy.deepcopy(hidden_default)

            prompt[node_id_str] = {"class_type": class_type_str, "inputs": inputs}
        except Exception:
            continue
    return prompt
