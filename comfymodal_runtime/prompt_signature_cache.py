"""PromptExecutor signature-key memoization (V2 optimization, Task 1).

Pure, stdlib-only, import-safe without ComfyUI.  Mirrors the structural
semantics of ``comfy_execution.caching.to_hashable`` so a memo entry can
reconstruct cache keys that are structurally equal (hence hash-equal) to the
originally computed values.

The memo is ADVISORY: every read failure / partial write / identity mismatch /
is_changed drift must fall back to the ORIGINAL ``CacheKeySetInputSignature
.add_keys`` computation — never raise, never weaken correctness.  A memo hit
only skips key computation; cache setup, clean_unused, and the gather lookup
walk still run (cheap).

NaN round-trip: JSON cannot carry NaN, so ``float("nan")`` and ComfyUI's
``Unhashable`` sentinel both encode to ``{"__nan__": true}`` and decode back
to ``float("nan")``.  A silent NaN→matching-key change would ALTER cache
behavior, so the always-miss semantics must be preserved exactly.

No I/O at import time; all persistence functions are best-effort and never
raise.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

SCHEMA_VERSION = 1

_MEMO_FILE_NAME = "prompt_signature_memo.json"

# Module-level advisory store: {identity_hash: entry} where each entry is a
# dict like {"nodes": {node_id: {"class_type", "is_changed", "signature",
# "inputs_hash"}}}.  Populated by load_store_from_disk(); consulted by the
# executor patch; updated on compute.  Loaded at most once per container.
_MEMO_STORE: dict[str, dict[str, Any]] = {}
_MEMO_LOADED = False
_MEMO_DISK_KEYS: set[str] = set()


# ── Canonical hashing (byte-identical to comfymodal_runtime.contracts) ──


def _thaw(value: Any) -> Any:
    """Mirror ``contracts._thaw`` so ``stable_hash`` is byte-identical."""
    if isinstance(value, Mapping):
        return {str(k): _thaw(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_thaw(v) for v in value]
    return value


def stable_hash(value: Any) -> str:
    """sha256 of canonical JSON — identical to ``contracts.stable_hash``.

    Kept local so this module stays pure and self-contained.
    """
    encoded = json.dumps(
        _thaw(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


# ── Memo identity ────────────────────────────────────────────────────────


def memo_identity(
    *,
    workflow_hash: str = "",
    source_workflow_hash: str = "",
    deployment_combined_hash: str = "",
    custom_node_generation: str = "",
    registry_proof: Any = None,
    schema_version: int = SCHEMA_VERSION,
) -> dict[str, Any]:
    """Build the canonical request identity for signature memoization.

    Returns a dict with ``identity`` (component fields), ``identity_hash``
    (stable hash over all fields) and ``complete`` (bool — the identity is
    usable only when every strong component is present; empty/incomplete
    identities must make the caller ineligible, never a memo attempt).
    """
    identity = {
        "workflow_hash": str(workflow_hash or ""),
        "source_workflow_hash": str(source_workflow_hash or ""),
        "deployment_combined_hash": str(deployment_combined_hash or ""),
        "custom_node_generation": str(custom_node_generation or ""),
        "registry_proof_hash": stable_hash(registry_proof or {}),
        "schema_version": int(schema_version or SCHEMA_VERSION),
    }
    complete = bool(
        identity["workflow_hash"]
        and identity["deployment_combined_hash"]
        and identity["custom_node_generation"]
    )
    return {
        "identity": identity,
        "identity_hash": stable_hash(identity),
        "complete": complete,
    }


# ── Encode / decode (mirrors comfy_execution.caching.to_hashable) ────────


def _sort_key(item: Any) -> str:
    """Canonical total-order key for frozenset items (JSON string compare)."""
    return json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _encode_element(value: Any) -> Any:
    """Encode one value into a JSON-encodable structure.

    Primitives pass through (bool before int — bool subclasses int); Mapping
    and Sequence collapse to ``{"t": "fz", "items": [[k, v], ...]}`` exactly
    like ``to_hashable``; float NaN and unencodable objects map to
    ``{"__nan__": true}`` (always-miss semantics preserved).
    """
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return {"__nan__": True}
        if math.isinf(value):
            return {"__float__": "inf" if value > 0 else "-inf"}
        return value
    if isinstance(value, bytes):
        return {"__bytes__": base64.b64encode(value).decode("ascii")}
    if isinstance(value, frozenset):
        # Already-hashable output of to_hashable: frozenset of (k, v) pairs.
        items: list[Any] = []
        for elem in value:
            if isinstance(elem, tuple) and len(elem) == 2:
                items.append([_encode_element(elem[0]), _encode_element(elem[1])])
            else:  # pragma: no cover - to_hashable only emits 2-tuples
                items.append([_encode_element(elem), {"__none__": True}])
        items.sort(key=_sort_key)
        return {"t": "fz", "items": items}
    if isinstance(value, Mapping):
        items = [
            [_encode_element(k), _encode_element(v)]
            for k, v in sorted(value.items())
        ]
        return {"t": "fz", "items": items}
    if isinstance(value, Sequence):
        items = [[i, _encode_element(v)] for i, v in enumerate(value)]
        return {"t": "fz", "items": items}
    # Unhashable / unsupported objects carry float-NaN semantics.
    return {"__nan__": True}


def _decode_element(encoded: Any) -> Any:
    """Inverse of ``_encode_element`` (reconstructs hashable values)."""
    if isinstance(encoded, dict):
        if encoded.get("t") == "fz":
            items = encoded.get("items") or []
            return frozenset(
                (_decode_element(it[0]), _decode_element(it[1]))
                for it in items
                if isinstance(it, list) and len(it) == 2
            )
        if encoded.get("__nan__") is True:
            return float("nan")
        if "__bytes__" in encoded:
            try:
                return base64.b64decode(encoded["__bytes__"])
            except Exception:
                return float("nan")
        if "__float__" in encoded:
            try:
                return float(encoded["__float__"])
            except (TypeError, ValueError):
                return float("nan")
        if "__none__" in encoded:
            return None
        # Unknown dict → NaN semantics (never happens in practice).
        return float("nan")
    return encoded


def encode_hashable(value: Any) -> Any:
    """Encode *value* (raw or already-hashable) into a JSON-encodable form.

    ``decode_hashable(encode_hashable(value))`` is structurally equal to
    ``to_hashable(value)`` for every to_hashable-supported input (frozenset
    equality is structural ⇒ identical hash ⇒ identical cache-key behavior).
    """
    return _encode_element(value)


def decode_hashable(encoded: Any) -> Any:
    """Decode an encoded value back to the original hashable structure."""
    return _decode_element(encoded)


def encode_value(value: Any) -> Any:
    """Alias of ``encode_hashable`` (NaN-safe comparison helper)."""
    return encode_hashable(value)


def encode_is_changed(value: Any) -> Any:
    """NaN-safe encode for IS_CHANGED values (NaN round-trips as NaN)."""
    return encode_hashable(value)


def reconstruct_signature(entry: Mapping[str, Any]) -> Any:
    """Decode a stored ``signature`` back to the original hashable (frozenset)."""
    return decode_hashable(entry.get("signature"))


# ── Per-node memo entry helpers ──────────────────────────────────────────


def canonical_inputs_hash(inputs: Any) -> str:
    """Cheap canonical hash of a node's ``inputs`` dict.

    sha256 of ``json.dumps(inputs, sort_keys=True, separators=(",", ":"),
    default=str)`` — any input change flips the hash, so a stale memo entry
    for a drifted prompt is detected without re-running signature building.
    """
    if not isinstance(inputs, Mapping):
        inputs = {}
    return hashlib.sha256(
        json.dumps(
            inputs,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def build_node_memo_entry(
    class_type: str,
    is_changed_value: Any,
    signature_value: Any,
    inputs_hash: str,
) -> dict[str, Any]:
    """Build the stored per-node memo entry.

    ``signature_value`` is the already-hashable value (``to_hashable``
    output) that the original computation placed in ``keys[node_id]``;
    ``is_changed_value`` is the raw IS_CHANGED value used during that
    computation.  Both are encoded so the entry is JSON-serializable and
    NaN-safe.
    """
    return {
        "class_type": str(class_type),
        "is_changed": encode_is_changed(is_changed_value),
        "signature": encode_hashable(signature_value),
        "inputs_hash": str(inputs_hash),
    }


# ── Persistence (advisory, best-effort, atomic) ──────────────────────────


def memo_path() -> str:
    """Resolve the memo file path under COMFYMODAL_V2_STATE_VOLUME_ROOT.

    Returns "" (fail closed — no persistence) when the env root is unset.
    """
    root = os.environ.get("COMFYMODAL_V2_STATE_VOLUME_ROOT", "").strip()
    if not root:
        return ""
    return os.path.join(root, _MEMO_FILE_NAME)


def load_signature_memo(path: str) -> dict[str, Any]:
    """Read the memo file into ``{identity_hash: entry}``.  Any error → {}.

    Corrupt/malformed files never raise; callers treat an empty result as a
    full miss and take the original computation path.
    """
    if not path:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        entries = data.get("entries") if isinstance(data, Mapping) else None
        if not isinstance(entries, Mapping):
            return {}
        return {str(k): v for k, v in entries.items() if isinstance(v, Mapping)}
    except Exception:
        return {}


def save_signature_memo(path: str, memo: Mapping[str, Any]) -> None:
    """Atomically persist the memo (tmp + uuid4 + flush + fsync + replace).

    Best-effort: never raises.  A partial write can never corrupt the prior
    file because ``os.replace`` is atomic.
    """
    if not path:
        return
    try:
        payload = {"schema_version": SCHEMA_VERSION, "entries": dict(memo)}
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = f"{path}.{uuid.uuid4().hex}.tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, sort_keys=True, separators=(",", ":"))
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
            os.replace(tmp, path)
        finally:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass
    except Exception:
        pass


def persist_store(path: str | None = None) -> None:
    """Persist the whole module store (best-effort, never raises)."""
    if path is None:
        path = memo_path()
    if not path:
        return
    save_signature_memo(path, _MEMO_STORE)


# ── Module-level store ───────────────────────────────────────────────────


def set_store(identity_hash: str, entry: Mapping[str, Any]) -> None:
    """Insert/replace one identity entry in the module store."""
    _MEMO_STORE[str(identity_hash)] = dict(entry)


def get_store(identity_hash: str) -> dict[str, Any] | None:
    """Return the identity entry, or None when absent."""
    entry = _MEMO_STORE.get(str(identity_hash))
    return entry if isinstance(entry, dict) else None


def memo_entry_source(identity_hash: str) -> str:
    """Where the entry came from: ``volume`` | ``compute`` | ``none``."""
    key = str(identity_hash)
    if key in _MEMO_DISK_KEYS:
        return "volume"
    if key in _MEMO_STORE:
        return "compute"
    return "none"


def load_store_from_disk(path: str | None = None) -> dict[str, Any]:
    """Load the memo file into the module store exactly once (tolerant)."""
    global _MEMO_LOADED
    if _MEMO_LOADED:
        return _MEMO_STORE
    if path is None:
        path = memo_path()
    if path:
        loaded = load_signature_memo(path)
        if loaded:
            _MEMO_STORE.update(loaded)
            _MEMO_DISK_KEYS.update(loaded.keys())
    _MEMO_LOADED = True
    return _MEMO_STORE


def reset_store() -> None:
    """Clear the module store (test/teardown helper; not used in prod)."""
    global _MEMO_LOADED
    _MEMO_STORE.clear()
    _MEMO_DISK_KEYS.clear()
    _MEMO_LOADED = False


# ── Topo-lazy section (deterministic cached→first-node fix) ──────────────
# Per-identity record of each node class's linked-input lazy flags, shaped
# ``{identity_hash: {"nodes": {...}, "topo_lazy": {class_type: {input_name:
# {"lazy": bool}}}}}``.  The lazy flag is a STRUCTURAL property of the node
# class definition's ``INPUT_TYPES`` spec — registry-proof-gated through the
# same identity_hash as the signature memo — so replaying it from the store
# is semantically safe: the ``TopologicalSort`` walk consumes ONLY
# ``extra_info["lazy"]`` from ``get_input_info``.  This is what makes the
# cached→first-node window deterministic on memo-hit runs (no cold
# ``INPUT_TYPES`` / folder-listing cost).  ADVISORY and fail-closed: any
# missing/malformed entry returns ``None`` and the caller takes the ORIGINAL
# path.  Old entries without ``topo_lazy`` load fine (treated as absent);
# the ``nodes`` section behavior is untouched.  All persistence is
# best-effort (atomic tmp+fsync+os.replace) and never raises.


def topo_lazy_get(identity_hash: str, class_type: str, input_name: str) -> bool | None:
    """Return the stored lazy flag for ``(class_type, input_name)``.

    ``None`` when the identity entry, the topo_lazy section, the class
    section, or the record is absent/malformed (or the stored flag is not a
    bool) — the caller must take the original path then.  Never raises.
    """
    try:
        entry = _MEMO_STORE.get(str(identity_hash))
        if not isinstance(entry, dict):
            return None
        section = entry.get("topo_lazy")
        if not isinstance(section, dict):
            return None
        class_section = section.get(str(class_type))
        if not isinstance(class_section, dict):
            return None
        record = class_section.get(str(input_name))
        if not isinstance(record, dict):
            return None
        lazy = record.get("lazy")
        return lazy if isinstance(lazy, bool) else None
    except Exception:
        return None


def topo_lazy_set(identity_hash: str, class_type: str, input_name: str, lazy: bool) -> None:
    """Mutate the module store with one ``(class_type, input_name)`` lazy flag.

    Does NOT persist — call :func:`topo_lazy_persist` for the atomic disk
    write.  Never raises; failures leave the store unchanged.
    """
    try:
        key = str(identity_hash)
        entry = _MEMO_STORE.get(key)
        if not isinstance(entry, dict):
            entry = {"nodes": {}}
            _MEMO_STORE[key] = entry
        section = entry.get("topo_lazy")
        if not isinstance(section, dict):
            section = {}
            entry["topo_lazy"] = section
        class_section = section.get(str(class_type))
        if not isinstance(class_section, dict):
            class_section = {}
            section[str(class_type)] = class_section
        class_section[str(input_name)] = {"lazy": bool(lazy)}
    except Exception:
        pass


def topo_lazy_persist(identity_hash: str) -> None:
    """Atomically persist the whole module store (best-effort, never raises).

    Reuses the existing :func:`persist_store` helper so the identity's
    topo_lazy section lands under the SAME atomic write (and schema_version
    stamp) as the signature-memo nodes section.  *identity_hash* is accepted
    for a symmetric API; the whole store is what is written.
    """
    try:
        persist_store()
    except Exception:
        pass


def topo_lazy_pending_count(identity_hash: str) -> int:
    """Count the stored ``(class_type, input_name)`` lazy entries for the identity.

    For evidence only (e.g. the breakdown's ``topo_lazy_pending`` after a
    persist); 0 when the identity entry or its topo_lazy section is absent
    or malformed.  Never raises.
    """
    try:
        entry = _MEMO_STORE.get(str(identity_hash))
        if not isinstance(entry, dict):
            return 0
        section = entry.get("topo_lazy")
        if not isinstance(section, dict):
            return 0
        total = 0
        for class_section in section.values():
            if isinstance(class_section, dict):
                total += sum(
                    1 for record in class_section.values() if isinstance(record, dict)
                )
        return total
    except Exception:
        return 0


# ── Memo-hit application (the executor patch consults this) ──────────────


async def apply_memo_hit(
    *,
    keys: dict[str, Any],
    subcache_keys: dict[str, Any],
    node_ids: Any,
    get_node: Any,
    has_node: Any,
    get_is_changed: Any,
    identity_hash: str,
) -> tuple[bool, str]:
    """Try to satisfy an ``add_keys``-style pass from the memo store.

    Mirrors ``CacheKeySetInputSignature.add_keys`` node iteration (skip keys
    already present; skip unknown nodes).  For every requested node:

      * stored ``inputs_hash`` must equal the CURRENT prompt node's canonical
        inputs hash (cheap integrity check);
      * when the stored ``is_changed`` is not ``False``, it must equal a
        re-evaluated ``await get_is_changed(node_id)`` (encoded both sides so
        NaN compares correctly).

    On a full hit, populates ``keys[node_id]`` (via ``reconstruct_signature``)
    and ``subcache_keys[node_id] = (node_id, class_type)`` and returns
    ``(True, "")``.  Any mismatch/error returns ``(False, reason)`` and the
    caller must take the ORIGINAL computation path.  Never raises.
    """
    try:
        entry = get_store(identity_hash)
        if entry is None:
            return False, "no_entry"
        nodes_entry = entry.get("nodes") if isinstance(entry, dict) else None
        if not isinstance(nodes_entry, dict):
            return False, "malformed_entry"

        pending: dict[Any, tuple[Any, str]] = {}
        for nid in node_ids:
            if nid in keys:
                continue
            try:
                if not has_node(nid):
                    continue
                node = get_node(nid)
            except Exception:
                return False, "dynprompt_error"
            node_entry = nodes_entry.get(str(nid))
            if not isinstance(node_entry, dict):
                return False, f"missing_node_entry:{nid}"
            if str(node_entry.get("class_type", "")) != str(node.get("class_type", "")):
                return False, f"class_type_mismatch:{nid}"
            if str(node_entry.get("inputs_hash", "")) != canonical_inputs_hash(
                node.get("inputs") or {}
            ):
                return False, f"inputs_hash_mismatch:{nid}"
            stored_isc = node_entry.get("is_changed")
            if stored_isc is not False:
                try:
                    current_isc = await get_is_changed(nid)
                except Exception:
                    return False, f"is_changed_error:{nid}"
                if stored_isc != encode_is_changed(current_isc):
                    return False, f"is_changed_mismatch:{nid}"
            signature = reconstruct_signature(node_entry)
            if not isinstance(signature, frozenset):
                return False, f"malformed_signature:{nid}"
            pending[nid] = (signature, str(node.get("class_type", "")))

        # Atomic commit: apply only after every node verified.
        for nid, (signature, class_type) in pending.items():
            keys[nid] = signature
            subcache_keys[nid] = (nid, class_type)
        return True, ""
    except Exception:
        return False, "memo_hit_exception"
