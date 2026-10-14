"""Studio Phase 9 Guidance backend (V1): exact-identity structural guidance.

Backend only (no web/UI).  V1 implements exactly one mechanism adapter:
``CONTROLNET_CONDITIONING``.  All other mechanism strings are refused honestly
(contracts frozen, not implemented).

Product invariant (rejection-grade): NO runtime branch on model family,
provider, checkpoint, or filename.  The only dispatch in this module is
``ADAPTERS[mapping["mechanism"]]``.  All provider/checkpoint/license knowledge
lives in mapping *data rows* (see ``suggest`` / ``evidence`` /
``controller.source_url`` / ``controller.license``), which NOTHING in this
module reads for decisions -- a test poisons those fields to prove it.

Pipeline (execution-copy only; the stored workflow is never mutated):

    stored workflow -> deepcopy -> resolve identity -> load confirmed mapping
    -> discover anchors (or verify a confirmed anchor binding)
    -> adapt the copy -> validate the copy -> execute -> discard the copy

Any refusal blocks the run honestly; nothing ever runs silently unguided.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from model_library import _sha256_file
from studio_store import StudioJsonStore
from studio_workflow_manifest import graph_hash

# ── Vocabulary ─────────────────────────────────────────────────────────────

#: Generic guidance modes.  New modes extend this tuple in data when evidence
#: exists; there is deliberately no ``lineart`` entry in V1.
GUIDANCE_MODES: tuple[str, ...] = ("canny", "depth", "pose")

#: The single implemented V1 mechanism.  Other mechanism names are valid
#: mapping *data* but dispatch to an honest ``unknown_mechanism`` refusal.
MECHANISM_CONTROLNET_CONDITIONING = "CONTROLNET_CONDITIONING"

#: Message used whenever exact model identity cannot be established.
IDENTITY_UNKNOWN_MESSAGE = (
    "Studio cannot identify this model exactly and will not guess from "
    "its filename"
)

_MAPPING_FILENAME = ".studio_guidance_mappings.json"


# ── Refusal ────────────────────────────────────────────────────────────────


class GuidanceRefusal:
    """Structured fail-closed outcome shared by discovery/adapters/executor.

    ``candidates`` feeds bounded-confirmation UI (e.g. anchor picks) -- it is
    never an automatic choice.
    """

    def __init__(
        self,
        reason: str,
        detail: str = "",
        candidates: list[dict[str, Any]] | None = None,
    ) -> None:
        self.reason = str(reason)
        self.detail = str(detail)
        self.candidates = list(candidates or [])

    def to_dict(self) -> dict[str, Any]:
        return {
            "refused": True,
            "reason": self.reason,
            "detail": self.detail,
            "candidates": [dict(c) for c in self.candidates],
        }

    def __bool__(self) -> bool:
        return True


def is_refusal(value: Any) -> bool:
    """Return True when *value* is a :class:`GuidanceRefusal`."""
    return isinstance(value, GuidanceRefusal)


# ── Mapping store ──────────────────────────────────────────────────────────


def _normalize_mode(mode: Any) -> str:
    return str(mode or "").strip().lower()


def _normalize_sha(sha: Any) -> str:
    return str(sha or "").strip().lower()


def validate_mapping(record: Any) -> list[str]:
    """Return a list of schema problems (empty == valid and confirmable).

    Required shape (keys beyond these are preserved untouched)::

        mechanism: non-empty string
        controller: {checkpoint (required), folder, checkpoint_sha256, ...}
        nodes: {loader, apply, preprocessor (all required)}
        conditioning: {strength, start, end (all numbers)}
        confirmed: True (user-confirmed records only)
    """
    issues: list[str] = []
    if not isinstance(record, dict):
        return ["mapping must be a dict"]
    if not str(record.get("mechanism") or "").strip():
        issues.append("mechanism must be a non-empty string")
    controller = record.get("controller")
    if not isinstance(controller, dict):
        issues.append("controller must be a dict")
    elif not str(controller.get("checkpoint") or "").strip():
        issues.append("controller.checkpoint must be a non-empty string")
    nodes = record.get("nodes")
    if not isinstance(nodes, dict):
        issues.append("nodes must be a dict")
    else:
        for slot in ("loader", "apply", "preprocessor"):
            if not str(nodes.get(slot) or "").strip():
                issues.append(f"nodes.{slot} must be a non-empty string")
    conditioning = record.get("conditioning")
    if not isinstance(conditioning, dict):
        issues.append("conditioning must be a dict")
    else:
        for slot in ("strength", "start", "end"):
            value = conditioning.get(slot)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                issues.append(f"conditioning.{slot} must be a number")
    if record.get("confirmed") is not True:
        issues.append("mapping must be user-confirmed (confirmed: true)")
    mode = _normalize_mode(record.get("mode"))
    if mode and mode not in GUIDANCE_MODES:
        issues.append(f"unsupported mode: {mode!r} (supports {', '.join(GUIDANCE_MODES)})")
    return issues


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class GuidanceMappingStore:
    """Tiny key-value record file keyed STRICTLY by ``(model_sha256, mode)``.

    Ops: :meth:`get` / :meth:`save` / :meth:`delete`, plus revision/audit on
    save.  There are no family/provider queries and no workflow-id lookup --
    by construction (the signatures accept nothing else).
    """

    FILENAME = _MAPPING_FILENAME

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.store = StudioJsonStore(self.root / self.FILENAME)

    # -- key ---------------------------------------------------------------
    @staticmethod
    def _key(model_sha256: str, mode: str) -> tuple[str, str]:
        return (_normalize_sha(model_sha256), _normalize_mode(mode))

    # -- ops ---------------------------------------------------------------
    def get(self, model_sha256: str, mode: str) -> dict[str, Any] | None:
        """Return a copy of the confirmed record for the exact key, or None."""
        want = self._key(model_sha256, mode)
        for row in self.store.read():
            if not isinstance(row, dict):
                continue
            if (str(row.get("model_sha256", "")), _normalize_mode(row.get("mode"))) == want:
                return copy.deepcopy(row)
        return None

    def save(self, record: dict[str, Any]) -> dict[str, Any]:
        """Persist a user-confirmed record; bumps revision + audit stamp.

        Raises ``ValueError`` when the record is not confirmable (see
        :func:`validate_mapping`).  Never invents identity or evidence rows.
        """
        issues = validate_mapping(record)
        if issues:
            raise ValueError(f"invalid guidance mapping: {'; '.join(issues)[:300]}")
        saved = copy.deepcopy(record)
        saved["model_sha256"] = _normalize_sha(saved.get("model_sha256"))
        saved["mode"] = _normalize_mode(saved.get("mode"))
        previous = self.get(saved["model_sha256"], saved["mode"])
        try:
            prev_rev = int((previous or {}).get("audit", {}).get("mapping_revision", 0))
        except (TypeError, ValueError):
            prev_rev = 0
        audit = dict(saved.get("audit") or {})
        audit["mapping_revision"] = prev_rev + 1
        audit["confirmed_at"] = _now_iso()
        saved["audit"] = audit

        def _mutate(rows: list[dict]) -> None:
            for i, existing in enumerate(rows):
                if not isinstance(existing, dict):
                    continue
                if (
                    str(existing.get("model_sha256", "")),
                    _normalize_mode(existing.get("mode")),
                ) == (saved["model_sha256"], saved["mode"]):
                    rows[i] = saved
                    return
            rows.append(saved)

        self.store.update(_mutate)
        return copy.deepcopy(saved)

    def delete(self, model_sha256: str, mode: str) -> bool:
        """Remove the exact-key record; return True when one existed."""
        want = self._key(model_sha256, mode)
        removed = [False]

        def _mutate(rows: list[dict]) -> None:
            for i, existing in enumerate(rows):
                if not isinstance(existing, dict):
                    continue
                if (
                    str(existing.get("model_sha256", "")),
                    _normalize_mode(existing.get("mode")),
                ) == want:
                    del rows[i]
                    removed[0] = True
                    return

        self.store.update(_mutate)
        return removed[0]


# ── Identity seam ──────────────────────────────────────────────────────────


def resolve_model_identity(
    folder: str,
    filename: str,
    library_records: list[dict[str, Any]],
) -> dict[str, Any] | GuidanceRefusal:
    """Resolve a workflow loader ``(folder, filename)`` to a verified SHA-256.

    Looks up Model Library records by the exact ``(folder, filename)`` key,
    then re-hashes the file on disk via :func:`model_library._sha256_file`.
    The stored record hash must match the fresh digest, otherwise the file
    was replaced (same filename, different model) and reuse is blocked.

    Rename-same-hash reuses naturally (mapping lookup is by digest, not by
    name); same-filename-changed-hash never reuses.  Unresolvable input
    returns a structured refusal -- never a filename guess.
    """
    folder_s = str(folder or "")
    filename_s = str(filename or "")
    matches = [
        r
        for r in (library_records or [])
        if isinstance(r, dict)
        and str(r.get("folder", "")) == folder_s
        and str(r.get("filename", "")) == filename_s
    ]
    if not matches:
        return GuidanceRefusal("identity_unresolvable", IDENTITY_UNKNOWN_MESSAGE)
    for record in matches:
        local_path = str(record.get("local_path", "") or "")
        if not local_path:
            continue
        digest = _sha256_file(local_path)
        if not digest:
            continue
        stored = str(record.get("hash", "") or "").strip().lower()
        if stored and stored != digest.lower():
            return GuidanceRefusal(
                "model_content_changed",
                "This filename now refers to a different model "
                f"(record {stored[:12]} vs file {digest[:12]}); "
                "the confirmed mapping will not be reused.",
            )
        return {
            "model_sha256": digest.lower(),
            "model_record_id": str(record.get("model_id", "") or ""),
            "folder": folder_s,
            "filename": filename_s,
        }
    return GuidanceRefusal("identity_unresolvable", IDENTITY_UNKNOWN_MESSAGE)


# ── Anchor discovery (generic structural walk) ─────────────────────────────

#: Class-type substrings marking a graph as already carrying guidance-type
#: conditioning with unclear composition order.  These name generic graph
#: shapes (mechanism markers), never model families or providers.
_ALREADY_CONTROLLED_MARKERS: tuple[str, ...] = (
    "controlnet",
    "control_lora",
    "controllora",
    "modelpatch",
    "ipadapter",
    "kontext",
)


def _as_link(value: Any) -> tuple[str, int] | None:
    """Return ``(node_id, output_index)`` for ComfyUI API link values."""
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        node_id, index = value[0], value[1]
        if isinstance(node_id, (str, int)) and isinstance(index, int) and not isinstance(
            index, bool
        ):
            return (str(node_id), index)
    return None


def _node_inputs(node: Any) -> dict[str, Any]:
    if isinstance(node, dict) and isinstance(node.get("inputs"), dict):
        return node["inputs"]
    return {}


def discover_anchors(
    workflow: dict[str, Any],
) -> dict[str, Any] | GuidanceRefusal:
    """Walk connection tuples and return one anchor set, or a Refusal.

    A generation sampler is a node with both ``positive`` and ``negative``
    conditioning inputs (structural shape, not a name list).  Exactly one
    such node must exist; its ``model`` edge and both conditioning producers
    must resolve to real links.  Graphs already carrying guidance-type
    conditioning refuse with the offending node named.
    """
    if not isinstance(workflow, dict) or not workflow:
        return GuidanceRefusal("empty_workflow", "The workflow has no nodes.")
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        lowered = str(node.get("class_type", "") or "").lower()
        for marker in _ALREADY_CONTROLLED_MARKERS:
            if marker in lowered:
                return GuidanceRefusal(
                    "already_controlled",
                    f"Node {node_id} ({node.get('class_type', '')}) already "
                    "carries guidance-type conditioning with unclear "
                    "composition order; refusing to chain automatically.",
                )
    standards = []
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        inputs = _node_inputs(node)
        if "positive" in inputs and "negative" in inputs:
            standards.append((str(node_id), node))
    if len(standards) > 1:
        return GuidanceRefusal(
            "multiple_samplers",
            "More than one generation sampler is present; "
            "confirm which one to guide.",
            candidates=[
                {"node_id": nid, "class_type": str(n.get("class_type", ""))}
                for nid, n in standards
            ],
        )
    if not standards:
        customs = []
        for node_id, node in workflow.items():
            if not isinstance(node, dict):
                continue
            inputs = _node_inputs(node)
            if "conditioning" in inputs or (
                "model" in inputs and ("samples" in inputs or "latent" in inputs)
            ):
                customs.append((str(node_id), node))
        if customs:
            return GuidanceRefusal(
                "custom_sampler",
                "The generation node does not expose a standard "
                "positive/negative conditioning contract; refusing to guess.",
                candidates=[
                    {"node_id": nid, "class_type": str(n.get("class_type", ""))}
                    for nid, n in customs
                ],
            )
        return GuidanceRefusal(
            "no_sampler",
            "No generation sampler with positive/negative conditioning found.",
        )
    sampler_id, sampler = standards[0]
    return _anchors_for_sampler(workflow, sampler_id, sampler)


def _anchors_for_sampler(
    workflow: dict[str, Any],
    sampler_id: str,
    sampler: dict[str, Any],
) -> dict[str, Any] | GuidanceRefusal:
    inputs = _node_inputs(sampler)
    edges: dict[str, tuple[str, int]] = {}
    for slot in ("positive", "negative", "model"):
        link = _as_link(inputs.get(slot))
        if link is None:
            return GuidanceRefusal(
                "conditioning_not_found" if slot != "model" else "model_edge_not_found",
                f"Sampler {sampler_id} input {slot!r} is not a resolvable link; "
                "refusing to guess the conditioning entry.",
            )
        target_id, _ = link
        if target_id not in workflow:
            return GuidanceRefusal(
                "conditioning_not_found" if slot != "model" else "model_edge_not_found",
                f"Sampler {sampler_id} input {slot!r} points at missing "
                f"node {target_id!r}.",
            )
        edges[slot] = link
    return {
        "sampler_id": sampler_id,
        "sampler_class": str(sampler.get("class_type", "") or ""),
        "positive": {"node_id": edges["positive"][0], "output": edges["positive"][1]},
        "negative": {"node_id": edges["negative"][0], "output": edges["negative"][1]},
        "model": {"node_id": edges["model"][0], "output": edges["model"][1]},
        "binding_id": f"anchor:{sampler_id}",
    }


def resolve_anchors(
    workflow: dict[str, Any],
    anchor_binding: dict[str, Any] | None = None,
) -> dict[str, Any] | GuidanceRefusal:
    """Return anchors for *workflow*, honouring a confirmed binding.

    A binding pins ``{"sampler_id", "graph_hash"}``.  When the stored graph
    hash no longer matches (graph edited after confirmation) the binding is
    stale and execution refuses until re-confirmed.
    """
    if anchor_binding is None:
        return discover_anchors(workflow)
    if not isinstance(anchor_binding, dict):
        return GuidanceRefusal("invalid_anchor_binding", "Anchor binding is malformed.")
    sampler_id = str(anchor_binding.get("sampler_id", "") or "")
    bound_hash = str(anchor_binding.get("graph_hash", "") or "")
    try:
        current_hash = graph_hash(workflow)
    except Exception:
        return GuidanceRefusal("invalid_workflow", "The workflow cannot be hashed.")
    if not sampler_id or not bound_hash:
        return GuidanceRefusal("invalid_anchor_binding", "Anchor binding is malformed.")
    if bound_hash != current_hash:
        return GuidanceRefusal(
            "stale_anchor_binding",
            f"Confirmed anchor {sampler_id!r} no longer matches the edited "
            "workflow; re-confirm before running.",
        )
    node = workflow.get(sampler_id)
    if not isinstance(node, dict):
        return GuidanceRefusal(
            "stale_anchor_binding",
            f"Confirmed anchor {sampler_id!r} is gone from the workflow; "
            "re-confirm before running.",
        )
    inputs = _node_inputs(node)
    if "positive" not in inputs or "negative" not in inputs:
        return GuidanceRefusal(
            "custom_sampler",
            f"Confirmed anchor {sampler_id!r} no longer exposes a standard "
            "positive/negative conditioning contract.",
        )
    return _anchors_for_sampler(workflow, sampler_id, node)


# ── Adapter: CONTROLNET_CONDITIONING ─────────────────────────────────────────

_STRING_SLOT_TYPES = frozenset({"STRING", "COMBO"})


def _required_slots(object_info: Any, class_type: str) -> dict[str, Any]:
    try:
        spec = (object_info or {}).get(class_type, {})
        block = spec.get("input", {}) if isinstance(spec, dict) else {}
        merged: dict[str, Any] = {}
        for section in ("required", "optional"):
            part = block.get(section, {})
            if isinstance(part, dict):
                merged.update(part)
        return merged
    except Exception:
        return {}


def _slot_type(decl: Any) -> str:
    if isinstance(decl, (list, tuple)) and decl:
        first = decl[0]
        if isinstance(first, str):
            return first
        if isinstance(first, (list, tuple)) and first and isinstance(first[0], str):
            return first[0]
        return ""
    if isinstance(decl, str):
        return decl
    if isinstance(decl, dict):
        inner = decl.get("type", "")
        return inner if isinstance(inner, str) else ""
    return ""


def _find_typed_slot(slots: dict[str, Any], want_type: str) -> str | None:
    for name, decl in slots.items():
        if _slot_type(decl).upper() == want_type:
            return name
    return None


def _find_string_slot(slots: dict[str, Any]) -> str | None:
    for name, decl in slots.items():
        if _slot_type(decl).upper() in _STRING_SLOT_TYPES:
            return name
    for name in slots:
        lowered = str(name).lower()
        if "name" in lowered or "path" in lowered or "file" in lowered:
            return name
    return None


def _next_node_id(workflow: dict[str, Any]) -> str:
    used = {str(k) for k in workflow}
    try:
        peak = max(int(k) for k in used if str(k).lstrip("-").isdigit())
        candidate = peak + 1
    except ValueError:
        candidate = len(used) + 1
    while str(candidate) in used:
        candidate += 1
    return str(candidate)


def _controlnet_conditioning_adapter(
    graph_copy: dict[str, Any],
    anchors: dict[str, Any],
    mapping: dict[str, Any],
    guide_image: Any,
    object_info: dict[str, Any] | None,
) -> dict[str, Any] | GuidanceRefusal:
    """Wire preprocessor + controller loader + two Apply nodes into the copy.

    Reads ONLY ``nodes.*``, ``controller.checkpoint``/``controller.folder``,
    and ``conditioning.*`` from the mapping, plus structural anchors.  One
    Apply node carries the positive conditioning, a second carries the
    negative; both share the controller output and the preprocessed guide.
    """
    nodes = mapping.get("nodes") if isinstance(mapping, dict) else None
    controller = mapping.get("controller") if isinstance(mapping, dict) else None
    conditioning = (
        mapping.get("conditioning") if isinstance(mapping, dict) else None
    )
    if not isinstance(nodes, dict) or not isinstance(controller, dict):
        return GuidanceRefusal("invalid_mapping", "Mapping nodes/controller malformed.")
    loader_cls = str(nodes.get("loader", "") or "")
    apply_cls = str(nodes.get("apply", "") or "")
    preproc_cls = str(nodes.get("preprocessor", "") or "")
    checkpoint = str(controller.get("checkpoint", "") or "")
    if not loader_cls or not apply_cls or not preproc_cls:
        return GuidanceRefusal(
            "invalid_mapping", "Mapping nodes.loader/apply/preprocessor required."
        )
    if not checkpoint:
        return GuidanceRefusal(
            "controller_checkpoint_missing",
            "The confirmed mapping names no controller checkpoint file.",
        )
    info = object_info if isinstance(object_info, dict) else {}
    for cls in (loader_cls, apply_cls, preproc_cls):
        if cls not in info:
            return GuidanceRefusal(
                "missing_node",
                f"Node {cls!r} is not installed (absent from object_info).",
            )
    loader_slots = _required_slots(info, loader_cls)
    apply_slots = _required_slots(info, apply_cls)
    preproc_slots = _required_slots(info, preproc_cls)

    checkpoint_slot = _find_string_slot(loader_slots)
    if checkpoint_slot is None:
        return GuidanceRefusal(
            "slot_mismatch",
            f"Loader {loader_cls!r} has no checkpoint filename input slot.",
        )
    control_slot = _find_typed_slot(apply_slots, "CONTROL_NET") or (
        "control_net" if "control_net" in apply_slots else None
    )
    image_slot = _find_typed_slot(apply_slots, "IMAGE") or (
        "image" if "image" in apply_slots else None
    )
    cond_slot = _find_typed_slot(apply_slots, "CONDITIONING") or (
        "conditioning" if "conditioning" in apply_slots else None
    )
    for want, found in (
        ("CONTROL_NET", control_slot),
        ("IMAGE", image_slot),
        ("CONDITIONING", cond_slot),
    ):
        if found is None:
            return GuidanceRefusal(
                "slot_mismatch",
                f"Apply {apply_cls!r} is missing a {want!r} input slot.",
            )
    assert control_slot is not None
    assert image_slot is not None
    assert cond_slot is not None
    if "strength" not in apply_slots:
        return GuidanceRefusal(
            "slot_mismatch",
            f"Apply {apply_cls!r} is missing the 'strength' input slot.",
        )
    pre_image_slot = _find_typed_slot(preproc_slots, "IMAGE") or (
        "image" if "image" in preproc_slots else None
    )
    if pre_image_slot is None:
        return GuidanceRefusal(
            "slot_mismatch",
            f"Preprocessor {preproc_cls!r} has no IMAGE input slot.",
        )

    if isinstance(guide_image, dict):
        guide_id = str(guide_image.get("node_id", "") or "")
        guide_out = guide_image.get("output", 0)
        guide_out = guide_out if isinstance(guide_out, int) else 0
    else:
        guide_id = str(guide_image or "")
        guide_out = 0
    if not guide_id or guide_id not in graph_copy:
        return GuidanceRefusal(
            "guide_image_missing",
            f"Guide image node {guide_id!r} is not present in the workflow copy.",
        )

    if not isinstance(conditioning, dict):
        return GuidanceRefusal("invalid_mapping", "Mapping conditioning malformed.")
    try:
        strength = float(conditioning["strength"])
        start = float(conditioning["start"])
        end = float(conditioning["end"])
    except (KeyError, TypeError, ValueError):
        return GuidanceRefusal(
            "invalid_mapping", "Mapping conditioning strength/start/end malformed."
        )

    sampler_id = str(anchors.get("sampler_id", "") or "")
    sampler = graph_copy.get(sampler_id)
    if not isinstance(sampler, dict):
        return GuidanceRefusal(
            "stale_anchor_binding",
            f"Anchor sampler {sampler_id!r} is gone from the workflow copy.",
        )
    pos_link = list(anchors.get("positive", {}).values())
    neg_link = list(anchors.get("negative", {}).values())
    try:
        pos_ref = [str(anchors["positive"]["node_id"]), int(anchors["positive"]["output"])]
        neg_ref = [str(anchors["negative"]["node_id"]), int(anchors["negative"]["output"])]
    except (KeyError, TypeError, ValueError):
        return GuidanceRefusal("invalid_anchors", "Anchor conditioning refs malformed.")
    _ = pos_link, neg_link

    pre_id = _next_node_id(graph_copy)
    graph_copy[pre_id] = {
        "class_type": preproc_cls,
        "inputs": {pre_image_slot: [guide_id, guide_out]},
    }
    load_id = _next_node_id(graph_copy)
    graph_copy[load_id] = {
        "class_type": loader_cls,
        "inputs": {checkpoint_slot: checkpoint},
    }
    pos_id = _next_node_id(graph_copy)
    pos_inputs: dict[str, Any] = {
        control_slot: [load_id, 0],
        image_slot: [pre_id, 0],
        cond_slot: pos_ref,
        "strength": strength,
    }
    if "start_percent" in apply_slots:
        pos_inputs["start_percent"] = start
    if "end_percent" in apply_slots:
        pos_inputs["end_percent"] = end
    graph_copy[pos_id] = {"class_type": apply_cls, "inputs": pos_inputs}
    neg_id = _next_node_id(graph_copy)
    neg_inputs: dict[str, Any] = dict(pos_inputs)
    neg_inputs[cond_slot] = neg_ref
    graph_copy[neg_id] = {"class_type": apply_cls, "inputs": neg_inputs}

    sampler_inputs = sampler.get("inputs")
    if not isinstance(sampler_inputs, dict):
        return GuidanceRefusal(
            "conditioning_not_found",
            f"Sampler {sampler_id} has no writable inputs in the copy.",
        )
    sampler_inputs["positive"] = [pos_id, 0]
    sampler_inputs["negative"] = [neg_id, 0]
    return graph_copy


#: Mechanism dispatch: plain dict, no registry/plugin/dynamic loading.
ADAPTERS: dict[str, Any] = {
    MECHANISM_CONTROLNET_CONDITIONING: _controlnet_conditioning_adapter,
}


def apply_guidance(
    graph_copy: dict[str, Any],
    anchors: dict[str, Any],
    mapping: dict[str, Any],
    guide_image: Any,
    object_info: dict[str, Any] | None = None,
) -> dict[str, Any] | GuidanceRefusal:
    """Dispatch ``ADAPTERS[mapping["mechanism"]]``; unknown names refuse."""
    mechanism = ""
    if isinstance(mapping, dict):
        mechanism = str(mapping.get("mechanism", "") or "")
    adapter = ADAPTERS.get(mechanism)
    if adapter is None:
        return GuidanceRefusal(
            "unknown_mechanism",
            f"No adapter is registered for mechanism {mechanism!r}.",
        )
    return adapter(graph_copy, anchors, mapping, guide_image, object_info)


def validate_guided_copy(
    graph_copy: dict[str, Any],
    object_info: dict[str, Any] | None = None,
) -> list[str]:
    """Structural validation of a mutated copy: link integrity + class types."""
    issues: list[str] = []
    if not isinstance(graph_copy, dict) or not graph_copy:
        return ["workflow copy is empty"]
    for node_id, node in graph_copy.items():
        if not isinstance(node, dict):
            issues.append(f"node {node_id} is malformed")
            continue
        class_type = node.get("class_type")
        if not isinstance(class_type, str) or not class_type:
            issues.append(f"node {node_id} has no class_type")
        elif isinstance(object_info, dict) and object_info and class_type not in object_info:
            issues.append(f"node {node_id} class_type {class_type!r} is not installed")
        inputs = node.get("inputs", {})
        if isinstance(inputs, dict):
            for slot, value in inputs.items():
                link = _as_link(value)
                if link is not None and link[0] not in graph_copy:
                    issues.append(
                        f"node {node_id} input {slot!r} points at missing "
                        f"node {link[0]!r}"
                    )
    return issues


# ── Execution-copy hook ────────────────────────────────────────────────────


def guidance_provenance(
    *,
    mode: str,
    model_sha256: str,
    mapping: dict[str, Any] | None,
    anchors: dict[str, Any] | None,
    anchor_binding: dict[str, Any] | None = None,
    refusal: GuidanceRefusal | None = None,
) -> dict[str, Any]:
    """Build generic history provenance fields (no provider-specific fields)."""
    controller = (mapping or {}).get("controller") or {}
    conditioning = (mapping or {}).get("conditioning") or {}
    nodes = (mapping or {}).get("nodes") or {}
    audit = (mapping or {}).get("audit") or {}
    provenance: dict[str, Any] = {
        "mode": _normalize_mode(mode),
        "model_sha256": _normalize_sha(model_sha256),
        "mechanism": str((mapping or {}).get("mechanism", "") or ""),
        "controller_checkpoint": str(controller.get("checkpoint", "") or ""),
        "controller_checkpoint_sha256": str(
            controller.get("checkpoint_sha256", "") or ""
        ),
        "controller_folder": str(controller.get("folder", "") or ""),
        "preprocessor": str(nodes.get("preprocessor", "") or ""),
        "mapping_revision": audit.get("mapping_revision", 0),
        "anchor_binding_id": str(
            ((anchor_binding or {}).get("binding_id", ""))
            or ((anchors or {}).get("binding_id", ""))
            or ""
        ),
        "sampler_id": str((anchors or {}).get("sampler_id", "") or ""),
        "strength": conditioning.get("strength"),
        "start": conditioning.get("start"),
        "end": conditioning.get("end"),
    }
    if refusal is not None:
        provenance["refusal_reason"] = refusal.reason
        if refusal.detail:
            provenance["refusal_detail"] = refusal.detail[:300]
    return provenance


def attach_guidance_provenance(
    meta: dict[str, Any], provenance: dict[str, Any] | None
) -> dict[str, Any]:
    """Attach generic guidance provenance onto a history meta dict (in place)."""
    if isinstance(meta, dict) and isinstance(provenance, dict) and provenance:
        meta["guidance_provenance"] = copy.deepcopy(provenance)
    return meta


def build_guided_execution_copy(
    stored_workflow: dict[str, Any],
    *,
    mode: str,
    model_folder: str,
    model_filename: str,
    library_records: list[dict[str, Any]],
    mapping_store: GuidanceMappingStore,
    guide_image: Any,
    object_info: dict[str, Any] | None = None,
    anchor_binding: dict[str, Any] | None = None,
) -> dict[str, Any] | GuidanceRefusal:
    """Deepcopy -> identity -> mapping -> anchors -> adapt -> validate.

    Returns ``{"ok": True, "workflow": <copy>, "provenance": {...}}`` or a
    :class:`GuidanceRefusal`.  The stored workflow is never mutated.
    """
    normalized_mode = _normalize_mode(mode)
    if normalized_mode not in GUIDANCE_MODES:
        return GuidanceRefusal(
            "unsupported_mode",
            f"Guidance supports {', '.join(GUIDANCE_MODES)} -- "
            f"it does not support {str(mode)!r}.",
        )
    identity = resolve_model_identity(model_folder, model_filename, library_records)
    if is_refusal(identity):
        assert isinstance(identity, GuidanceRefusal)
        return identity
    assert isinstance(identity, dict)
    sha = str(identity["model_sha256"])
    mapping = mapping_store.get(sha, normalized_mode)
    if mapping is None:
        return GuidanceRefusal(
            "no_confirmed_mapping",
            "No user-confirmed guidance mapping exists for this exact model "
            "and mode; Studio will not guess one.",
        )
    if mapping.get("confirmed") is not True:
        return GuidanceRefusal(
            "mapping_unconfirmed",
            "The stored guidance mapping is not user-confirmed.",
        )
    graph_copy = copy.deepcopy(stored_workflow)
    anchors = resolve_anchors(graph_copy, anchor_binding)
    if is_refusal(anchors):
        assert isinstance(anchors, GuidanceRefusal)
        return anchors
    assert isinstance(anchors, dict)
    adapted = apply_guidance(graph_copy, anchors, mapping, guide_image, object_info)
    if is_refusal(adapted):
        assert isinstance(adapted, GuidanceRefusal)
        return adapted
    assert isinstance(adapted, dict)
    problems = validate_guided_copy(adapted, object_info)
    if problems:
        return GuidanceRefusal(
            "guided_copy_invalid",
            "; ".join(problems)[:300],
        )
    return {
        "ok": True,
        "workflow": adapted,
        "provenance": guidance_provenance(
            mode=normalized_mode,
            model_sha256=sha,
            mapping=mapping,
            anchors=anchors,
            anchor_binding=anchor_binding,
        ),
    }


# ── Feature-status gate (Guidance-engaged RUN blocking) ────────────────────

#: Guidance states that block RUN through the shared feature-status gate.
#: ``ready=True`` means the mapping + anchors validated; anything else blocks.
def guidance_feature_block(guidance_state: Any) -> dict[str, str] | None:
    """Return a ``blocked`` feature status when engaged guidance is not ready.

    Returns None when guidance is absent, not engaged, or ready -- leaving
    the existing gate untouched.
    """
    if not isinstance(guidance_state, dict):
        return None
    if not guidance_state.get("engaged"):
        return None
    if guidance_state.get("ready") is True:
        return None
    reason = str(
        guidance_state.get("reason")
        or guidance_state.get("refusal_reason")
        or "guidance engaged but not ready"
    )
    return {"status": "blocked", "reason": reason[:300]}
