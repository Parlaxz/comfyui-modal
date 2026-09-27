"""API prompt preflight validation for comfyui-modal.

Pure Python — does NOT import ComfyUI, torch, modal, or any GPU code.
Safe to run locally before Modal is invoked.

Call ``assert_valid_api_prompt_structure(prompt)`` before sending any
workflow to Modal.
"""

# UI workflow JSON fields that should NOT appear in API prompt format.
# When a node has these WITHOUT class_type, it is likely a UI workflow
# that was accidentally submitted instead of API prompt JSON.
_UI_WORKFLOW_SIGNALS = frozenset({
    "widgets_values",
    "pos",
    "size",
    "flags",
    "order",
    "mode",
})

# Top-level keys in a UI workflow that indicate it is NOT an API prompt.
_UI_TOP_LEVEL_SIGNALS = frozenset({
    "nodes",
    "links",
    "groups",
    "version",
    "extra",
})


def _coerce_node_id(key) -> str:
    """Safely convert a prompt-key (node ID) to a string for error messages."""
    if isinstance(key, (int, float)):
        return str(int(key))
    if isinstance(key, str):
        return f"'{key}'"
    return repr(key)


def validate_api_prompt_structure(prompt: object) -> list[str]:
    """Validate that ``prompt`` is a well-formed ComfyUI API prompt dict.

    Returns a list of error strings.  An empty list means the prompt
    is structurally valid (does **not** guarantee all node classes are
    registered or that the graph is acyclic).
    """
    errors: list[str] = []

    if not isinstance(prompt, dict):
        errors.append(
            "Invalid API prompt: top-level prompt must be a dict of "
            f"node_id -> node_spec, got {type(prompt).__name__}"
        )
        return errors

    if not prompt:
        errors.append("Invalid API prompt: prompt is empty.")
        return errors

    # ── Check for UI workflow JSON at top level ──────────────────────
    # API prompt format is a flat dict of node_id -> node_spec.
    # UI workflow JSON uses "nodes" / "links" top-level keys.
    if _UI_TOP_LEVEL_SIGNALS & set(prompt.keys()):
        errors.append(
            "Invalid API prompt: this looks like UI workflow JSON "
            "(contains 'nodes', 'links', or other UI-only keys). "
            "Export the workflow as API prompt JSON (Copy Prompt → API Format)."
        )
        return errors

    for node_id, node_spec in prompt.items():
        nid = _coerce_node_id(node_id)

        # ── Node spec must be a dict ──────────────────────────────────
        if not isinstance(node_spec, dict):
            errors.append(
                f"Invalid API prompt: node {nid} value must be a dict, "
                f"got {type(node_spec).__name__}"
            )
            continue

        has_class_type = "class_type" in node_spec
        ct = node_spec.get("class_type")

        # ── Detect UI-workflow-style nodes that slipped in ────────────
        # UI nodes have fields like widgets_values, pos, size, flags,
        # order, mode.  If one of these exists but class_type is missing,
        # this is a corrupt/UI node in the API prompt.
        _has_ui_signals = bool(_UI_WORKFLOW_SIGNALS & set(node_spec.keys()))

        if not has_class_type:
            if _has_ui_signals:
                errors.append(
                    f"Invalid API prompt: node {nid} looks like a UI node "
                    f"(has 'pos', 'size', or other UI-only fields) but has "
                    f"no 'class_type'. Re-export the workflow as API prompt "
                    f"JSON or remove the corrupt/UI-only node."
                )
            else:
                errors.append(
                    f"Invalid API prompt: node {nid} has no class_type. "
                    f"Re-export workflow as API prompt JSON or remove the "
                    f"corrupt/UI-only node."
                )
            continue

        # ── class_type must be a non-empty string ─────────────────────
        if not isinstance(ct, str) or ct.strip() == "":
            errors.append(
                f"Invalid API prompt: node {nid} 'class_type' must be a "
                f"non-empty string, got "
                f"{type(ct).__name__ if ct is not None else 'null'}: "
                f"{ct!r}"
            )
            continue

        # ── inputs is mandatory ───────────────────────────────────────
        if "inputs" not in node_spec:
            errors.append(
                f"Invalid API prompt: node {nid} (class_type='{ct}') "
                f"has no inputs object."
            )
            continue

        inputs = node_spec["inputs"]
        if not isinstance(inputs, dict):
            errors.append(
                f"Invalid API prompt: node {nid} (class_type='{ct}') "
                f"inputs must be an object/dict, got "
                f"{type(inputs).__name__}"
            )
            continue

    return errors


def validate_class_types_exist(prompt: dict, available_types: set[str]) -> list[str]:
    """Check that every class_type referenced in *prompt* exists in *available_types*.

    Returns a list of missing class types (empty = all present).
    """
    missing: set[str] = set()
    for node_spec in prompt.values():
        if not isinstance(node_spec, dict):
            continue
        ct = node_spec.get("class_type")
        if isinstance(ct, str) and ct and ct not in available_types:
            missing.add(ct)
    return sorted(missing)


def assert_valid_api_prompt_structure(prompt: object) -> None:
    """Validate API prompt structure and raise RuntimeError on failure.

    Raises ``RuntimeError`` with all errors joined by ``"; "`` if any exist.
    """
    errors = validate_api_prompt_structure(prompt)
    if errors:
        raise RuntimeError(
            "Workflow preflight validation failed: "
            + "; ".join(errors)
        )
