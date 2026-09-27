"""Custom-nodes generation parity: decision + report formatting.

Pure module (no comfy/modal imports) so the construction-time reconciliation
logic in ``modal_app.sync_custom_nodes`` is unit-testable without Modal or a
ComfyUI runtime.

Background
----------
The image bakes the production custom nodes and records
``production_custom_node_generation`` in the baked dependency manifest
(``/opt/comfymodal/custom_node_deps_baked.json``).  The custom-nodes Volume
(``comfyui-custom-nodes``) mirrors that source tree and carries a persisted
``generation`` record (``/root/custom_nodes_vol/.comfymodal_control/
custom_nodes_generation.json``).  That record is content-derived but is only
rewritten by the local volume-sync flow (V1) or in-container when the record
is missing, so a V2 deploy can leave a stale record behind even when the
underlying tree is identical.  ``build_parity_report`` turns the baked /
persisted / actual-tree generations observed during the construction-time
full sync into a single deterministic report whose
``proof_generation_match`` predicts whether the ``[v2.deployment_proof]``
freeze will observe ``gen_ok=1`` (the freeze compares baked vs
``state.custom_node_generation``, which is the instance/persisted token —
never a fresh content hash).
"""

from typing import Any, Mapping

__all__ = [
    "build_parity_report",
    "should_update_persisted_record",
    "format_parity_line",
]


def _clean(value: Any) -> str:
    """Normalize a generation token to a string (falsy -> "")."""
    return str(value or "")


def _match(a: Any, b: Any) -> bool | None:
    """Equality of two operands, or None when either operand is falsy."""
    if not a or not b:
        return None
    return str(a) == str(b)


# Deterministic key order shared by the report dict and the log line.
_PARITY_KEY_ORDER = (
    "baked_generation",
    "persisted_generation",
    "pre_sync_actual_generation",
    "post_sync_actual_generation",
    "persisted_source",
    "sync_performed",
    "sync_direction",
    "sync_reason",
    "baked_matches_persisted",
    "baked_matches_pre_sync_actual",
    "baked_matches_post_sync_actual",
    "persisted_matches_post_sync_actual",
    "final_authoritative_generation",
    "final_authority_source",
    "proof_freeze_generation",
    "proof_generation_match",
)


def build_parity_report(
    *,
    baked_generation: Any,
    persisted_generation: Any,
    pre_sync_actual_generation: Any,
    post_sync_actual_generation: Any,
    persisted_source: Any,
    sync_performed: Any,
    sync_direction: Any,
    sync_reason: Any,
) -> dict[str, Any]:
    """Build the custom-nodes generation parity report.

    ``*_actual_generation`` values are the content-derived generation of the
    runtime custom-nodes tree observed before / after the volume->container
    sync during construction.  ``final_authority_source``:
    * ``"baked_image"`` when the post-sync ACTUAL tree matches the baked
      generation (the authoritative tree equals the deployed source);
    * ``"volume_tree"`` when a post-sync ACTUAL exists but differs from the
      baked generation (mismatched code — proof will fail closed);
    * ``"persisted_record"`` / ``"baked_image"`` / ``"unknown"`` when no
      post-sync ACTUAL was observed.

    ``proof_freeze_generation`` is always the baked generation: that is the
    token ``[v2.deployment_proof]`` must observe for ``gen_ok=1``.
    """
    baked = _clean(baked_generation)
    persisted = _clean(persisted_generation)
    pre_sync_actual = _clean(pre_sync_actual_generation)
    post_sync_actual = _clean(post_sync_actual_generation)

    if post_sync_actual:
        if post_sync_actual == baked:
            final_authoritative_generation = baked
            final_authority_source = "baked_image"
        else:
            final_authoritative_generation = post_sync_actual
            final_authority_source = "volume_tree"
    else:
        if persisted:
            final_authoritative_generation = persisted
            final_authority_source = "persisted_record"
        elif baked:
            final_authoritative_generation = baked
            final_authority_source = "baked_image"
        else:
            final_authoritative_generation = ""
            final_authority_source = "unknown"

    return {
        "baked_generation": baked,
        "persisted_generation": persisted,
        "pre_sync_actual_generation": pre_sync_actual,
        "post_sync_actual_generation": post_sync_actual,
        "persisted_source": _clean(persisted_source),
        "sync_performed": bool(sync_performed),
        "sync_direction": _clean(sync_direction),
        "sync_reason": _clean(sync_reason),
        "baked_matches_persisted": _match(baked, persisted),
        "baked_matches_pre_sync_actual": _match(baked, pre_sync_actual),
        "baked_matches_post_sync_actual": _match(baked, post_sync_actual),
        "persisted_matches_post_sync_actual": _match(persisted, post_sync_actual),
        "final_authoritative_generation": final_authoritative_generation,
        "final_authority_source": final_authority_source,
        "proof_freeze_generation": baked,
        "proof_generation_match": _match(baked, final_authoritative_generation),
    }


def should_update_persisted_record(
    *, persisted_generation: Any, actual_generation: Any
) -> bool:
    """Content-verified stale-record repair decision.

    True iff *actual_generation* is non-empty AND (the persisted record is
    empty OR differs from the actual).  Never accepts a token without
    content proof: an empty actual always returns False.
    """
    actual = _clean(actual_generation)
    if not actual:
        return False
    persisted = _clean(persisted_generation)
    return (not persisted) or (persisted != actual)


def _format_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def format_parity_line(report: Mapping[str, Any]) -> str:
    """Single-line ``[v2.custom_node_generation_parity] key=value ...``.

    Bools render as 1/0, None as ``-``, in a deterministic key order.
    """
    parts = ["[v2.custom_node_generation_parity]"]
    for key in _PARITY_KEY_ORDER:
        parts.append(f"{key}={_format_value(report.get(key))}")
    return " ".join(parts)
