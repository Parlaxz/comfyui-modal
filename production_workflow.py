"""Pure-module production workflow compilation, normalization, and analysis.

No Modal, Torch, ComfyUI server, filesystem, or GPU dependencies.
"""

import copy
import hashlib
import json
import threading
from collections import OrderedDict
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
COMPILER_SCHEMA_VERSION = 1
HASH_SCHEMA_VERSION = 1
PRODUCTION_PLAN_SCHEMA_VERSION = 1

# Canonical JSON serialisation
_CANONICAL_JSON_KWARGS = {
    "sort_keys": True,
    "separators": (",", ":"),
    "ensure_ascii": False,
    "allow_nan": False,
}


def _canonical_workflow_hash(workflow: dict) -> str:
    """SHA-256 of a workflow dict using canonical UTF-8 JSON encoding.

    Uses ``allow_nan=False`` so that NaN/Infinity values raise a
    ``ValueError`` and produce an empty hash (fail-closed) rather than
    silently producing a divergent hash.
    """
    try:
        encoded = json.dumps(workflow, **_CANONICAL_JSON_KWARGS)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    except Exception:
        return ""

_DEFAULT_PRODUCTION = {
    "enabled": True,
    "schema_version": COMPILER_SCHEMA_VERSION,
    "disable_sampler_previews": True,
    "quiet_execution_logs": True,
    "progress_min_interval_ms": 500,
    "strict_output_collection": True,
    "direct_output_sink": True,
    "metadata_mode": "none",
    "output_node_ids": [],
    "bypass_node_ids": [],
}

_TRUE_DEFAULTS = {
    "disable_sampler_previews": True,
    "quiet_execution_logs": True,
    "strict_output_collection": True,
    "direct_output_sink": True,
}

_DEFAULT_MISSING_KEYS = {
    "disable_sampler_previews",
    "quiet_execution_logs",
    "progress_min_interval_ms",
    "strict_output_collection",
    "direct_output_sink",
    "metadata_mode",
}

_OUTPUT_REWRITE_TARGETS = frozenset({
    "SaveImage",
    "PreviewImage",
    "SaveImageWithMetaData",
})

_DUPLICATE_OUTPUT_CAPABLE = frozenset({
    "SaveImage",
    "PreviewImage",
    "SaveImageWithMetaData",
})

_RGTHREE_COMPARER_TARGETS = frozenset({
    "Image Comparer (rgthree)",
})

# ---------------------------------------------------------------------------
# LRU Cache
# ---------------------------------------------------------------------------
_CACHE_MAXSIZE = 32


class _LRUDict:
    def __init__(self, maxsize):
        self._maxsize = maxsize
        self._data = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
                return self._data[key]
            return None

    def put(self, key, value):
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            if len(self._data) > self._maxsize:
                self._data.popitem(last=False)

    def __len__(self):
        with self._lock:
            return len(self._data)

    def clear(self):
        with self._lock:
            self._data.clear()


_topology_plan_cache = _LRUDict(_CACHE_MAXSIZE)


def _reset_cache():
    _topology_plan_cache.clear()


def _cache_size():
    return len(_topology_plan_cache)


def _compute_compiled_workflow_hash(compiled: dict) -> str:
    """SHA-256 of the compiled workflow dict. Delegates to canonical helper."""
    return _canonical_workflow_hash(compiled)


def _compute_source_workflow_hash(workflow: dict) -> str:
    """SHA-256 of the full source workflow dict. Delegates to canonical helper."""
    return _canonical_workflow_hash(workflow)


def _canonical_options_key(production: dict) -> str:
    """Canonical JSON serialization of the full normalized production options dict.

    Delegates to the same ``_CANONICAL_JSON_KWARGS`` used by
    ``_canonical_workflow_hash`` so that NaN/Infinity values raise a
    ``ValueError`` (fail-closed) rather than silently producing a
    divergent hash.
    """
    return json.dumps(production, **_CANONICAL_JSON_KWARGS)


def _compute_production_plan_hash(
    source_hash: str,
    compiled_hash: str,
    production: dict,
    *,
    allow_direct_output_rewrite: bool = True,
    allow_rgthree_comparer_rewrite: bool = True,
    stable: bool = False,
) -> str:
    """Deterministic hash covering the full production plan provenance.

    Includes source/compiled identities, every normalized production option,
    compiler/hash/plan schema versions, and context flags so any semantic
    change invalidates the plan hash.
    """
    raw = (
        f"source={source_hash}|compiled={compiled_hash}"
        f"|options={_canonical_options_key(production)}"
        f"|cv={COMPILER_SCHEMA_VERSION}|hv={HASH_SCHEMA_VERSION}"
        f"|pv={PRODUCTION_PLAN_SCHEMA_VERSION}"
        f"|dow={str(allow_direct_output_rewrite)}"
        f"|rgthree={str(allow_rgthree_comparer_rewrite)}"
        f"|stable={str(stable)}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ProductionPlan:
    """Frozen value object representing a complete production compilation result.

    Carries source and compiled workflows with their identities, the
    production report, and version/schema metadata.

    Compatibility: supports ``tuple`` unpacking ``plan.compiled, plan.report``
    via the iterator protocol so existing ``compiled, report = compile_*(…)``
    call sites continue to work during migration.
    """
    source_workflow: dict
    source_workflow_hash: str
    compiled_workflow: dict
    compiled_workflow_hash: str
    production_plan_hash: str
    source_output_node_ids: list = field(default_factory=list)
    compiled_output_node_ids: list = field(default_factory=list)
    production_options: dict = field(default_factory=dict)
    report: dict = field(default_factory=dict)
    compiler_version: int = COMPILER_SCHEMA_VERSION
    hash_schema_version: int = HASH_SCHEMA_VERSION
    production_plan_schema_version: int = PRODUCTION_PLAN_SCHEMA_VERSION
    # Schema aliases for backward compat during migration
    schema_version: int = COMPILER_SCHEMA_VERSION
    hash_schema: int = HASH_SCHEMA_VERSION

    def __iter__(self):
        """Compatibility iterator yielding (compiled_workflow, report).

        This allows existing ``compiled, report = compile_production_workflow(…)``
        call sites to continue working.  New code should use named fields:
        ``plan.compiled_workflow`` and ``plan.report``.
        """
        yield self.compiled_workflow
        yield self.report

    def __getitem__(self, index):
        """Compatibility subscript access for tuple-indexing [0] / [1].

        Allows existing callers that do ``result[1]`` to get the report
        without migrating to named fields.
        """
        if index == 0:
            return self.compiled_workflow
        if index == 1:
            return self.report
        raise IndexError("ProductionPlan subscript out of range")


# ---------------------------------------------------------------------------
# ID normalization helpers
# ---------------------------------------------------------------------------

def _normalize_ids(raw):
    seen = set()
    result = []
    for v in raw:
        s = str(v).strip()
        if s and s not in seen:
            seen.add(s)
            result.append(s)
    result.sort(key=_id_sort_key)
    return result


def _id_sort_key(s):
    try:
        return (0, int(s))
    except ValueError:
        return (1, s)


def _is_connection(value):
    if not isinstance(value, (list, tuple)):
        return False
    if len(value) != 2:
        return False
    node_id, slot = value
    return isinstance(node_id, (str, int)) and isinstance(slot, int)


def _extract_connection(value, normalized_ids):
    if not _is_connection(value):
        return None
    raw_node_id = value[0]
    slot = value[1]
    needle = str(raw_node_id).strip()
    if needle in normalized_ids:
        return (needle, slot)
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def normalize_production_options(modal_options: dict | None) -> dict:
    """Canonical normalizer for production options.

    Semantics
    ---------
    * ``None`` / ``{}`` / no ``production`` key          → ``enabled=True`` (defaults)
    * ``production={}`` / ``production.enabled`` omitted  → ``enabled=True`` (defaults)
    * ``production.enabled=false``                         → ``{"enabled": False}``
    * ``production.enabled=true`` (with or without IDs)   → ``enabled=True`` (normalized)

    Output ``output_node_ids`` may remain **empty** after normalization — the
    calling surface (Studio, Experiment) is responsible for deriving them before
    compilation.  The compiler itself raises a clear ``ValueError`` if it receives
    empty ``output_node_ids``.
    """
    # ── None / empty / absent — enabled=True with canonical defaults ──
    if not modal_options:
        return dict(_DEFAULT_PRODUCTION)

    production_raw = modal_options.get("production")

    # ── Legacy inline flat dict ──
    if production_raw is None:
        if "schema_version" in modal_options or "output_node_ids" in modal_options:
            production_raw = modal_options
        else:
            return dict(_DEFAULT_PRODUCTION)

    if not isinstance(production_raw, dict):
        raise TypeError("production options must be a dict when present")

    prod = dict(production_raw)

    # ── Explicit disabled ────────────────────────────────────────────
    if prod.get("enabled") is False:
        return {"enabled": False}

    # ── Enabled (explicit or implicit) — normalize defaults ──────────
    prod.setdefault("enabled", True)

    # Validate explicit schema_version when caller provides one
    sv = prod.get("schema_version")
    if sv is not None and sv != COMPILER_SCHEMA_VERSION:
        raise ValueError(
            f"production schema_version must be {COMPILER_SCHEMA_VERSION}, got {sv!r}"
        )
    prod["schema_version"] = COMPILER_SCHEMA_VERSION

    for key in _DEFAULT_MISSING_KEYS:
        if key not in prod:
            prod[key] = _TRUE_DEFAULTS.get(key, _DEFAULT_PRODUCTION[key])

    output_ids = prod.get("output_node_ids", [])
    if not isinstance(output_ids, (list, tuple)):
        raise TypeError("output_node_ids must be a list")
    prod["output_node_ids"] = _normalize_ids(output_ids)

    bypass_ids = prod.get("bypass_node_ids", [])
    if not isinstance(bypass_ids, (list, tuple)):
        raise TypeError("bypass_node_ids must be a list")
    prod["bypass_node_ids"] = _normalize_ids(bypass_ids)

    overlap = set(prod["output_node_ids"]) & set(prod["bypass_node_ids"])
    if overlap:
        raise ValueError(
            f"output_node_ids and bypass_node_ids overlap: {sorted(overlap)}"
        )
    return prod


def build_production_topology_hash(
    workflow: dict, production: dict, *, allow_direct_output_rewrite: bool = True
) -> str:
    parts = []
    parts.append(f"schema_v:{production.get('schema_version', 0)}")
    nid_map = _build_normalized_id_map(workflow)
    for nid in nid_map:
        original_key = nid_map[nid]
        node = workflow[original_key]
        parts.append(f"n:{nid}:{node.get('class_type', '?')}")
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        for key in sorted(inputs):
            value = inputs[key]
            conn = _extract_connection(value, nid_map)
            if conn is not None:
                parts.append(f"i:{key}:conn:{conn[0]}:{conn[1]}")
            elif _is_connection(value):
                parts.append(f"i:{key}:literal:{type(value).__name__}")
            else:
                parts.append(f"i:{key}:literal:{type(value).__name__}")
    for oid in sorted(production.get("output_node_ids", [])):
        parts.append(f"out:{oid}")
    for bid in sorted(production.get("bypass_node_ids", [])):
        parts.append(f"byp:{bid}")
    parts.append(f"dow:{bool(production.get('direct_output_sink', True))}")
    parts.append(f"arw:{bool(allow_direct_output_rewrite)}")
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compile_production_workflow(
    workflow: dict, production: dict, *, allow_direct_output_rewrite: bool, allow_rgthree_comparer_rewrite: bool = True, stable: bool = False
) -> ProductionPlan:
    original_count = len(workflow)
    nid_map = _build_normalized_id_map(workflow)
    output_ids = production.get("output_node_ids", [])
    bypass_ids = set(production.get("bypass_node_ids", []))

    for oid in output_ids:
        if oid not in nid_map:
            available = sorted(nid_map.keys())[:20]
            raise ValueError(
                f"output_node_id {oid!r} not found in workflow. "
                f"Available node IDs (first 20): {available}"
            )
    for oid in output_ids:
        if oid in bypass_ids:
            raise ValueError(f"output_node_id {oid!r} is also marked as bypassed")

    if not output_ids:
        raise ValueError(
            "output_node_ids must not be empty when production compilation is called. "
            "Derive output node IDs from the surface (preset outputNodeId, node binding, "
            "or caller-provided option) before compiling."
        )

    if not stable:
        for bid in bypass_ids:
            if bid in nid_map:
                original_key = nid_map[bid]
                node = workflow[original_key]
                ct = node.get("class_type", "?")
                raise ValueError(
                    f"Production bypass failed for node {bid} ({ct}). "
                    "ComfyUI could not serialize this node as a native bypass."
                )

    if stable:
        reachable = set(nid_map.keys())
        kept_ids = list(reachable)
    else:
        reachable = _collect_reachable(output_ids, workflow, nid_map)
        kept_ids = [nid for nid in nid_map if nid in reachable]

    topology_hash = build_production_topology_hash(
        workflow, production, allow_direct_output_rewrite=allow_direct_output_rewrite
    )

    source_workflow_hash = _compute_source_workflow_hash(workflow)
    cache_key = (
        topology_hash,
        source_workflow_hash,
        bool(stable),
        str(production.get("metadata_mode", "none")),
        bool(allow_rgthree_comparer_rewrite),
        bool(allow_direct_output_rewrite),
        bool(production.get("direct_output_sink", True)),
        int(production.get("schema_version", COMPILER_SCHEMA_VERSION)),
        COMPILER_SCHEMA_VERSION,
        HASH_SCHEMA_VERSION,
        PRODUCTION_PLAN_SCHEMA_VERSION,
    )
    cached = _topology_plan_cache.get(cache_key)

    if cached is not None:
        cached_kept_set = cached["kept_ids_set"]
        cached_rewritten = cached.get("rewritten_ids", ())
        cached_rgthree = cached.get("rgthree_rewritten_ids", ())
        cached_rewrite_plan = cached.get("rewrite_plan", {})
        compiled = OrderedDict()
        for nid in nid_map:
            if nid in cached_kept_set:
                original_key = nid_map[nid]
                compiled[nid] = _copy_node(workflow[original_key])
        rewritten_ids = []
        if allow_direct_output_rewrite and production.get("direct_output_sink", True):
            for oid in cached_rewritten:
                if oid in compiled:
                    _try_rewrite_output(oid, compiled, nid_map, rewritten_ids)
        rgthree_rewritten_ids = []
        if allow_direct_output_rewrite and allow_rgthree_comparer_rewrite and production.get("direct_output_sink", True):
            for oid in cached_rgthree:
                if oid in compiled:
                    _try_rewrite_rgthree_comparer(oid, compiled, nid_map, rgthree_rewritten_ids)
        removed_ids = [nid for nid in nid_map if nid not in cached_kept_set]
        duplicate_analysis = {}
        _selected_output_classes = {}
        for oid in output_ids:
            if oid in nid_map:
                orig_key = nid_map[oid]
                _selected_output_classes[oid] = workflow.get(orig_key, {}).get("class_type", "?")
        compiled_workflow_hash = _compute_compiled_workflow_hash(compiled)
        # The runner hash is the same as compiled hash when we execute the
        # compiled workflow.  Set here so downstream validation can compare.
        runner_workflow_hash = compiled_workflow_hash
        # compiled_output_node_ids = selected output IDs that survive in compiled
        _surviving_output_ids = [oid for oid in output_ids if oid in compiled]
        sf = bool(stable)
        ador = bool(allow_direct_output_rewrite)
        arcr = bool(allow_rgthree_comparer_rewrite)
        production_plan_hash = _compute_production_plan_hash(
            source_workflow_hash, compiled_workflow_hash,
            production,
            allow_direct_output_rewrite=ador,
            allow_rgthree_comparer_rewrite=arcr,
            stable=sf,
        )
        report = {
            "enabled": True,
            "schema_version": production.get("schema_version", 0),
            "compiler_version": COMPILER_SCHEMA_VERSION,
            "hash_schema_version": HASH_SCHEMA_VERSION,
            "production_plan_schema_version": PRODUCTION_PLAN_SCHEMA_VERSION,
            "original_node_count": original_count,
            "compiled_node_count": len(compiled),
            "removed_node_count": len(removed_ids),
            "kept_node_ids": list(compiled.keys()),
            "removed_node_ids": removed_ids,
            "output_node_ids": list(output_ids),
            "source_output_node_ids": list(output_ids),
            "compiled_output_node_ids": list(_surviving_output_ids),
            "bypass_node_ids": list(bypass_ids),
            "direct_output_rewritten_node_ids": rewritten_ids,
            "rgthree_comparer_rewritten_node_ids": rgthree_rewritten_ids,
            "topology_hash": topology_hash,
            "production_plan_hash": production_plan_hash,
            "source_workflow_hash": source_workflow_hash,
            "compiled_workflow_hash": compiled_workflow_hash,
            "runner_workflow_hash": runner_workflow_hash,
            "cache_hit": True,
            "duplicate_analysis": duplicate_analysis,
            "direct_output_sink_enabled": bool(production.get("direct_output_sink", True)),
            "allow_direct_output_rewrite": allow_direct_output_rewrite,
            "selected_output_classes": _selected_output_classes,
            "direct_output_rewritten_count": len(rewritten_ids),
            "rgthree_comparer_rewritten_count": len(rgthree_rewritten_ids),
            "direct_output_rewrite_allowed": allow_direct_output_rewrite,
        }
        compiled_wf = dict(compiled)
        return ProductionPlan(
            source_workflow=copy.deepcopy(workflow),
            source_workflow_hash=source_workflow_hash,
            compiled_workflow=copy.deepcopy(compiled_wf),
            compiled_workflow_hash=compiled_workflow_hash,
            production_plan_hash=production_plan_hash,
            source_output_node_ids=list(output_ids),
            compiled_output_node_ids=list(_surviving_output_ids),
            production_options=copy.deepcopy(production),
            report=copy.deepcopy(report),
            compiler_version=COMPILER_SCHEMA_VERSION,
            hash_schema_version=HASH_SCHEMA_VERSION,
            production_plan_schema_version=PRODUCTION_PLAN_SCHEMA_VERSION,
        )

    compiled = OrderedDict()
    for nid in kept_ids:
        original_key = nid_map[nid]
        compiled[nid] = _copy_node(workflow[original_key])

    rewritten_ids = []
    if allow_direct_output_rewrite and production.get("direct_output_sink", True):
        metadata_mode = production.get("metadata_mode", "none")
        if metadata_mode != "full":
            for oid in output_ids:
                _try_rewrite_output(oid, compiled, nid_map, rewritten_ids)

    rgthree_rewritten_ids = []
    if allow_direct_output_rewrite and allow_rgthree_comparer_rewrite and production.get("direct_output_sink", True):
        metadata_mode = production.get("metadata_mode", "none")
        if metadata_mode != "full":
            for oid in output_ids:
                _try_rewrite_rgthree_comparer(oid, compiled, nid_map, rgthree_rewritten_ids)

    removed_ids = [nid for nid in nid_map if nid not in reachable]

    _topology_plan_cache.put(cache_key, {
        "kept_ids_set": frozenset(compiled.keys()),
        "rewritten_ids": tuple(rewritten_ids),
        "rgthree_rewritten_ids": tuple(rgthree_rewritten_ids),
        "rewrite_plan": {
            str(oid): {
                "kind": "rgthree_image_comparer",
                "class_type": "ComfyModalProductionImageComparerOutput",
            }
            for oid in rgthree_rewritten_ids
        },
    })

    duplicate_analysis = analyze_duplicate_work(workflow)
    _selected_output_classes = {}
    for oid in output_ids:
        if oid in nid_map:
            orig_key = nid_map[oid]
            _selected_output_classes[oid] = workflow.get(orig_key, {}).get("class_type", "?")
    compiled_workflow_hash = _compute_compiled_workflow_hash(compiled)
    runner_workflow_hash = compiled_workflow_hash
    # compiled_output_node_ids = selected output IDs that survive in compiled
    _surviving_output_ids = [oid for oid in output_ids if oid in compiled]
    sf = bool(stable)
    ador = bool(allow_direct_output_rewrite)
    arcr = bool(allow_rgthree_comparer_rewrite)
    production_plan_hash = _compute_production_plan_hash(
        source_workflow_hash, compiled_workflow_hash,
        production,
        allow_direct_output_rewrite=ador,
        allow_rgthree_comparer_rewrite=arcr,
        stable=sf,
    )

    report = {
        "enabled": True,
        "schema_version": production.get("schema_version", 0),
        "compiler_version": COMPILER_SCHEMA_VERSION,
        "hash_schema_version": HASH_SCHEMA_VERSION,
        "production_plan_schema_version": PRODUCTION_PLAN_SCHEMA_VERSION,
        "original_node_count": original_count,
        "compiled_node_count": len(compiled),
        "removed_node_count": len(removed_ids),
        "kept_node_ids": list(compiled.keys()),
        "removed_node_ids": removed_ids,
        "output_node_ids": list(output_ids),
        "source_output_node_ids": list(output_ids),
        "compiled_output_node_ids": list(_surviving_output_ids),
        "bypass_node_ids": list(bypass_ids),
        "direct_output_rewritten_node_ids": rewritten_ids,
        "rgthree_comparer_rewritten_node_ids": rgthree_rewritten_ids,
        "topology_hash": topology_hash,
        "production_plan_hash": production_plan_hash,
        "source_workflow_hash": source_workflow_hash,
        "compiled_workflow_hash": compiled_workflow_hash,
        "runner_workflow_hash": runner_workflow_hash,
        "cache_hit": False,
        "duplicate_analysis": duplicate_analysis,
        "direct_output_sink_enabled": bool(production.get("direct_output_sink", True)),
        "allow_direct_output_rewrite": allow_direct_output_rewrite,
        "selected_output_classes": _selected_output_classes,
        "direct_output_rewritten_count": len(rewritten_ids),
        "rgthree_comparer_rewritten_count": len(rgthree_rewritten_ids),
        "direct_output_rewrite_allowed": allow_direct_output_rewrite,
    }
    compiled_wf = dict(compiled)
    return ProductionPlan(
        source_workflow=copy.deepcopy(workflow),
        source_workflow_hash=source_workflow_hash,
        compiled_workflow=copy.deepcopy(compiled_wf),
        compiled_workflow_hash=compiled_workflow_hash,
        production_plan_hash=production_plan_hash,
        source_output_node_ids=list(output_ids),
        compiled_output_node_ids=list(_surviving_output_ids),
        production_options=copy.deepcopy(production),
        report=copy.deepcopy(report),
        compiler_version=COMPILER_SCHEMA_VERSION,
        hash_schema_version=HASH_SCHEMA_VERSION,
        production_plan_schema_version=PRODUCTION_PLAN_SCHEMA_VERSION,
    )


def analyze_duplicate_work(workflow: dict) -> dict:
    nid_map = _build_normalized_id_map(workflow)

    output_groups = []
    seen_output_sources = {}
    for nid in nid_map:
        original_key = nid_map[nid]
        node = workflow[original_key]
        ct = node.get("class_type", "")
        if ct not in _DUPLICATE_OUTPUT_CAPABLE:
            continue
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        images_val = inputs.get("images")
        conn = _extract_connection(images_val, nid_map) if images_val is not None else None
        if conn is None:
            continue
        source_key = (conn[0], conn[1])
        if source_key not in seen_output_sources:
            seen_output_sources[source_key] = []
        seen_output_sources[source_key].append(nid)
    for source_key, members in seen_output_sources.items():
        if len(members) > 1:
            output_groups.append({
                "source_node_id": source_key[0],
                "source_slot": source_key[1],
                "member_node_ids": sorted(members),
            })

    vae_groups = []
    seen_vae_inputs = {}
    for nid in nid_map:
        original_key = nid_map[nid]
        node = workflow[original_key]
        ct = node.get("class_type", "")
        if "VAEDecode" not in ct:
            continue
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        samples_val = inputs.get("samples")
        latent_val = inputs.get("latent")
        vae_val = inputs.get("vae")
        samples_conn = _extract_connection(samples_val, nid_map) if samples_val is not None else None
        latent_conn = _extract_connection(latent_val, nid_map) if latent_val is not None else None
        vae_conn = _extract_connection(vae_val, nid_map) if vae_val is not None else None
        main_input_conn = samples_conn or latent_conn
        if main_input_conn is None:
            continue
        remaining = {}
        for k, v in inputs.items():
            if k in ("samples", "latent", "vae"):
                continue
            conn = _extract_connection(v, nid_map)
            if conn is not None:
                remaining[k] = ("conn", conn[0], conn[1])
            else:
                remaining[k] = ("literal", v)
        sig = (
            ct,
            "latent:" + str(main_input_conn),
            "vae:" + str(vae_conn),
            str(sorted(remaining.items())),
        )
        if sig not in seen_vae_inputs:
            seen_vae_inputs[sig] = []
        seen_vae_inputs[sig].append(nid)
    for sig, members in seen_vae_inputs.items():
        if len(members) > 1:
            vae_groups.append({
                "signature": sig,
                "member_node_ids": sorted(members),
            })

    clip_groups = []
    seen_clip_inputs = {}
    for nid in nid_map:
        original_key = nid_map[nid]
        node = workflow[original_key]
        ct = node.get("class_type", "")
        if "CLIPTextEncode" not in ct:
            continue
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        clip_val = inputs.get("clip")
        text_val = inputs.get("text")
        clip_conn = _extract_connection(clip_val, nid_map) if clip_val is not None else None
        text_str = text_val if isinstance(text_val, str) else str(text_val)
        sig = (
            ct,
            "clip:" + (str(clip_conn) if clip_conn else "none"),
            "text:" + text_str,
        )
        if sig not in seen_clip_inputs:
            seen_clip_inputs[sig] = []
        seen_clip_inputs[sig].append(nid)
    for sig, members in seen_clip_inputs.items():
        if len(members) > 1:
            clip_groups.append({
                "signature": sig,
                "member_node_ids": sorted(members),
            })

    return {
        "duplicate_output_groups": output_groups,
        "duplicate_vae_decode_groups": vae_groups,
        "duplicate_clip_encode_groups": clip_groups,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_normalized_id_map(workflow):
    nid_map = OrderedDict()
    for raw_id in workflow:
        nid = str(raw_id).strip()
        if nid:
            if nid in nid_map:
                raise ValueError(
                    f"Normalized node-ID collision: key {raw_id!r} and "
                    f"{nid_map[nid]!r} both resolve to {nid!r}"
                )
            nid_map[nid] = raw_id
    return nid_map


def _collect_reachable(output_ids, workflow, nid_map):
    reachable = set(output_ids)
    stack = list(output_ids)
    while stack:
        current = stack.pop()
        current_original = nid_map.get(current)
        if current_original is None:
            continue
        node = workflow.get(current_original)
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        for value in inputs.values():
            conn = _extract_connection(value, nid_map)
            if conn is not None:
                src_id = conn[0]
                if src_id not in reachable:
                    reachable.add(src_id)
                    stack.append(src_id)
    return reachable


def _copy_node(node):
    return {
        "class_type": node.get("class_type", ""),
        "inputs": dict(node.get("inputs", {})),
    }


def _try_rewrite_output(oid, compiled, nid_map, rewritten_ids):
    if oid not in compiled:
        return
    node = compiled[oid]
    ct = node.get("class_type", "")
    if ct not in _OUTPUT_REWRITE_TARGETS:
        return
    inputs = node.get("inputs", {})
    images_val = inputs.get("images")
    conn = _extract_connection(images_val, nid_map)
    if conn is None:
        return
    compiled[oid] = {
        "class_type": "ComfyModalProductionOutput",
        "inputs": {"images": images_val},
    }
    rewritten_ids.append(oid)


def _try_rewrite_rgthree_comparer(oid, compiled, nid_map, rewritten_ids):
    """Replace an rgthree Image Comparer with ComfyModalProductionImageComparerOutput.

    Returns True if the node was rewritten, False otherwise.
    """
    if oid not in compiled:
        return False
    node = compiled[oid]
    ct = node.get("class_type", "")
    if ct not in _RGTHREE_COMPARER_TARGETS:
        return False
    inputs = node.get("inputs", {})
    image_a_val = inputs.get("image_a")
    image_a_conn = _extract_connection(image_a_val, nid_map) if image_a_val is not None else None
    if image_a_conn is None:
        return False
    image_b_val = inputs.get("image_b")
    image_b_conn = _extract_connection(image_b_val, nid_map) if image_b_val is not None else None
    inputs_are_same = (image_a_conn is not None and image_a_conn == image_b_conn)
    new_inputs = {"image_a": image_a_val, "inputs_are_same": inputs_are_same}
    if image_b_conn is not None:
        new_inputs["image_b"] = image_b_val
    compiled[oid] = {
        "class_type": "ComfyModalProductionImageComparerOutput",
        "inputs": new_inputs,
    }
    rewritten_ids.append(oid)
    return True
