"""Tests for PromptExecutor signature-key memoization (V2 optimization, Task 1).

Covers the pure module (encode/decode round-trips, identity, persistence,
memo-hit application) and the executor-facing ineligibility path.  No
ComfyUI imports — a local ``to_hashable`` mirror stands in for
``comfy_execution.caching.to_hashable`` so the memo round-trip is verified
against the exact structural semantics the original computation uses.
"""

from __future__ import annotations

import asyncio
import itertools
import math
import os
from collections.abc import Mapping, Sequence
from unittest import mock

import pytest

from comfymodal_runtime.prompt_signature_cache import (
    SCHEMA_VERSION,
    apply_memo_hit,
    build_node_memo_entry,
    canonical_inputs_hash,
    decode_hashable,
    encode_hashable,
    encode_is_changed,
    load_signature_memo,
    memo_identity,
    memo_path,
    memo_entry_source,
    reconstruct_signature,
    reset_store,
    save_signature_memo,
    set_store,
    get_store,
    topo_lazy_get,
    topo_lazy_pending_count,
    topo_lazy_persist,
    topo_lazy_set,
)


# ── Local mirrors of comfy_execution.caching semantics ──────────────────


class _Unhashable:
    def __init__(self) -> None:
        self.value = float("NaN")


def _to_hashable(obj):
    """Mirror comfy_execution.caching.to_hashable."""
    if isinstance(obj, (int, float, str, bool, bytes, type(None))):
        return obj
    if isinstance(obj, Mapping):
        return frozenset((_to_hashable(k), _to_hashable(v)) for k, v in sorted(obj.items()))
    if isinstance(obj, Sequence):
        return frozenset(zip(itertools.count(), [_to_hashable(i) for i in obj]))
    return _Unhashable()


def _immediate_signature(node, is_changed_value):
    """Mirror get_immediate_node_signature's structural list (simplified)."""
    signature = [node["class_type"], is_changed_value]
    for key in sorted((node.get("inputs") or {}).keys()):
        signature.append((key, node["inputs"][key]))
    return signature


def _compute_node_signature(prompt, node_id, is_changed_values):
    """Mirror get_node_signature for a flat prompt (no ancestor links)."""
    node = prompt[node_id]
    sig = [_immediate_signature(node, is_changed_values.get(node_id, False))]
    return _to_hashable(sig)


class _FakeDynPrompt:
    def __init__(self, prompt):
        self.prompt = prompt

    def has_node(self, node_id):
        return node_id in self.prompt

    def get_node(self, node_id):
        return self.prompt[node_id]


class _FakeIsChanged:
    def __init__(self, values=None):
        self.values = values or {}

    async def get(self, node_id):
        return self.values.get(node_id, False)


def _run(coro):
    return asyncio.run(coro)


def _base_prompt():
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sd15.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "a cat", "clip": ("1", 0)}},
        "3": {"class_type": "KSampler", "inputs": {"steps": 20, "seed": 7, "model": ("1", 0)}},
    }


def _identity(**overrides):
    base = {
        "workflow_hash": "wf-hash-1",
        "source_workflow_hash": "src-hash-1",
        "deployment_combined_hash": "dep-hash-1",
        "custom_node_generation": "gen-1",
        "registry_proof": {"nodes": {"CheckpointLoaderSimple": "v1"}},
    }
    base.update(overrides)
    return memo_identity(
        workflow_hash=base["workflow_hash"],
        source_workflow_hash=base["source_workflow_hash"],
        deployment_combined_hash=base["deployment_combined_hash"],
        custom_node_generation=base["custom_node_generation"],
        registry_proof=base["registry_proof"],
    )


# ── 1. encode/decode round-trips ────────────────────────────────────────


@pytest.mark.parametrize(
    "value",
    [
        {"a": 1, "b": [1, 2, 3], "c": {"d": "x", "e": None}},
        [1, "two", 3.0, False, None, [4, {"k": "v"}]],
        ("tuple", 1, {"nested": [1, 2]}),
        3.14159,
        42,
        "string",
        True,
        False,
        None,
        b"\x00\x01\xff",
        {"k": (1, 2, 3), "l": [{"m": b"raw"}]},
    ],
)
def test_round_trip_structural_equality(value):
    decoded = decode_hashable(encode_hashable(value))
    assert decoded == _to_hashable(value)


def _contains_nan(value) -> bool:
    """Recursively check for a NaN float inside a decoded hashable structure."""
    if isinstance(value, float):
        return math.isnan(value)
    if isinstance(value, frozenset):
        return any(_contains_nan(e) for e in value)
    if isinstance(value, tuple):
        return any(_contains_nan(e) for e in value)
    return False


def test_round_trip_nan_preserves_nan_semantics():
    # A bare NaN value round-trips to a float NaN.
    decoded_nan = decode_hashable(encode_hashable(float("nan")))
    assert isinstance(decoded_nan, float)
    assert math.isnan(decoded_nan)
    # NaN inside collections: the decoded structure carries the NaN (never a
    # silently-matched value), so the key keeps its always-miss semantics.
    for value in ([float("nan")], {"k": float("nan")}):
        decoded = decode_hashable(encode_hashable(value))
        original = _to_hashable(value)
        assert _contains_nan(decoded)
        # Self-inequality: two DIFFERENT nan-bearing objects of identical
        # shape never compare equal — identical to the original to_hashable
        # behavior (and since hash(nan) is id-based, even the hash differs —
        # a stronger miss).  A cache keyed by one never matches the other.
        assert decoded != original


def test_round_trip_unhashable_becomes_nan():
    # ComfyUI's to_hashable maps non-primitive/non-collection objects to
    # Unhashable() whose value is float("NaN"); the memo encodes it as NaN.
    encoded = encode_hashable(_Unhashable())
    assert encoded == {"__nan__": True}
    decoded = decode_hashable(encoded)
    assert isinstance(decoded, float)
    assert math.isnan(decoded)


def test_encode_is_changed_nan_compare():
    # NaN-safe comparison helper: two NaN evaluations compare equal.
    assert encode_is_changed(float("nan")) == encode_is_changed(float("nan"))
    assert encode_is_changed(False) == encode_is_changed(False)
    assert encode_is_changed(False) is False
    assert encode_is_changed(float("nan")) != encode_is_changed(True)


def test_signature_round_trip_matches_to_hashable():
    # A realistic signature list (the shape get_node_signature builds).
    raw = ["KSampler", False, ("steps", 20), ("seed", 7), ("model", ("ANCESTOR", 0, 0))]
    original = _to_hashable(raw)
    decoded = decode_hashable(encode_hashable(original))
    assert decoded == original
    assert hash(decoded) == hash(original)


# ── 2. memo hit produces keys identical to the original computation ─────


def test_memo_hit_keys_identical_to_original():
    reset_store()
    prompt = _base_prompt()
    identity = _identity()
    identity_hash = identity["identity_hash"]

    # Original computation (ground truth).
    original_keys = {nid: _compute_node_signature(prompt, nid, {}) for nid in prompt}
    original_subcache = {nid: (nid, prompt[nid]["class_type"]) for nid in prompt}

    # Seed the memo store the way a compute-miss write-back would.
    nodes = {}
    for nid, node in prompt.items():
        nodes[nid] = build_node_memo_entry(
            class_type=node["class_type"],
            is_changed_value=False,
            signature_value=original_keys[nid],
            inputs_hash=canonical_inputs_hash(node.get("inputs") or {}),
        )
    set_store(identity_hash, {"nodes": nodes})

    keys: dict = {}
    subcache_keys: dict = {}
    dyn = _FakeDynPrompt(prompt)
    isc = _FakeIsChanged({})
    hit, reason = _run(
        apply_memo_hit(
            keys=keys,
            subcache_keys=subcache_keys,
            node_ids=list(prompt.keys()),
            get_node=dyn.get_node,
            has_node=dyn.has_node,
            get_is_changed=isc.get,
            identity_hash=identity_hash,
        )
    )
    assert hit is True
    assert reason == ""
    assert keys == original_keys
    assert subcache_keys == original_subcache


def test_memo_hit_nan_is_changed_verified_via_cache():
    reset_store()
    # A node whose IS_CHANGED is constant NaN (SystemNotification-like).
    prompt = {"1": {"class_type": "SystemNotification", "inputs": {"message": "x"}}}
    identity_hash = _identity()["identity_hash"]
    original_keys = {nid: _compute_node_signature(prompt, nid, {"1": float("nan")}) for nid in prompt}
    nodes = {
        "1": build_node_memo_entry(
            class_type="SystemNotification",
            is_changed_value=float("nan"),
            signature_value=original_keys["1"],
            inputs_hash=canonical_inputs_hash(prompt["1"].get("inputs") or {}),
        )
    }
    set_store(identity_hash, {"nodes": nodes})

    keys, subcache_keys = {}, {}
    dyn = _FakeDynPrompt(prompt)
    isc = _FakeIsChanged({"1": float("nan")})  # still NaN on this request
    hit, reason = _run(
        apply_memo_hit(
            keys=keys, subcache_keys=subcache_keys, node_ids=["1"],
            get_node=dyn.get_node, has_node=dyn.has_node,
            get_is_changed=isc.get, identity_hash=identity_hash,
        )
    )
    assert hit is True
    # The NaN round-tripped: the reconstructed key contains a real NaN and is
    # never equal to the original key (always-miss semantics preserved —
    # identical to the original computation's own key behavior).
    assert _contains_nan(keys["1"])
    assert keys["1"] != original_keys["1"]


# ── 3-5. identity drift → miss ──────────────────────────────────────────


def _apply_with(identity_hash, prompt=None):
    prompt = prompt or _base_prompt()
    keys, subcache_keys = {}, {}
    dyn = _FakeDynPrompt(prompt)
    isc = _FakeIsChanged({})
    return _run(
        apply_memo_hit(
            keys=keys, subcache_keys=subcache_keys, node_ids=list(prompt.keys()),
            get_node=dyn.get_node, has_node=dyn.has_node,
            get_is_changed=isc.get, identity_hash=identity_hash,
        )
    )


def test_changed_workflow_hash_is_miss():
    reset_store()
    set_store(_identity()["identity_hash"], {"nodes": {"1": {}}})
    other = _identity(workflow_hash="wf-hash-2")
    hit, reason = _apply_with(other["identity_hash"])
    assert hit is False
    assert reason == "no_entry"
    assert other["identity_hash"] != _identity()["identity_hash"]


def test_changed_custom_node_generation_is_miss():
    reset_store()
    set_store(_identity()["identity_hash"], {"nodes": {"1": {}}})
    other = _identity(custom_node_generation="gen-2")
    hit, reason = _apply_with(other["identity_hash"])
    assert hit is False
    assert reason == "no_entry"


def test_changed_registry_proof_is_miss():
    reset_store()
    set_store(_identity()["identity_hash"], {"nodes": {"1": {}}})
    other = _identity(registry_proof={"nodes": {"CheckpointLoaderSimple": "v2"}})
    assert other["identity_hash"] != _identity()["identity_hash"]
    hit, reason = _apply_with(other["identity_hash"])
    assert hit is False
    assert reason == "no_entry"


# ── 6. changed is_changed → fallback (original path) ────────────────────


def test_changed_is_changed_falls_back():
    reset_store()
    prompt = {"1": {"class_type": "SystemNotification", "inputs": {"message": "x"}}}
    identity_hash = _identity()["identity_hash"]
    sig = _compute_node_signature(prompt, "1", {"1": float("nan")})
    nodes = {
        "1": build_node_memo_entry(
            class_type="SystemNotification",
            is_changed_value=float("nan"),
            signature_value=sig,
            inputs_hash=canonical_inputs_hash(prompt["1"].get("inputs") or {}),
        )
    }
    set_store(identity_hash, {"nodes": nodes})

    # THIS request the node's is_changed drifted away from NaN.
    dyn = _FakeDynPrompt(prompt)
    isc = _FakeIsChanged({"1": True})
    hit, reason = _run(
        apply_memo_hit(
            keys={}, subcache_keys={}, node_ids=["1"],
            get_node=dyn.get_node, has_node=dyn.has_node,
            get_is_changed=isc.get, identity_hash=identity_hash,
        )
    )
    assert hit is False
    assert reason == "is_changed_mismatch:1"
    # Fallback must not have mutated the caller's key dicts.
    # (Original path is taken by the executor patch when hit is False.)


# ── 7. corrupt/malformed memo file → {} → compute path ──────────────────


def test_corrupt_memo_file_loads_empty(tmp_path):
    bad = tmp_path / "memo.json"
    bad.write_text("{definitely not json", encoding="utf-8")
    assert load_signature_memo(str(bad)) == {}

    malformed = tmp_path / "memo2.json"
    malformed.write_text('{"schema_version": 1, "entries": "nope"}', encoding="utf-8")
    assert load_signature_memo(str(malformed)) == {}

    assert load_signature_memo("") == {}
    assert load_signature_memo(str(tmp_path / "missing.json")) == {}

    # Empty store → memo attempt reports no_entry → compute path.
    reset_store()
    hit, reason = _apply_with(_identity()["identity_hash"])
    assert hit is False
    assert reason == "no_entry"


# ── 8. empty/incomplete identity → ineligible ───────────────────────────


def test_empty_identity_ineligible():
    ident = memo_identity(workflow_hash="")
    assert ident["complete"] is False

    ident2 = memo_identity(workflow_hash="wf", deployment_combined_hash="", custom_node_generation="g")
    assert ident2["complete"] is False

    ident3 = memo_identity(workflow_hash="wf", deployment_combined_hash="d", custom_node_generation="g")
    assert ident3["complete"] is True
    # source_workflow_hash absent → still complete (defaults deterministically).
    assert ident3["identity"]["source_workflow_hash"] == ""


def test_missing_identity_in_state_is_ineligible():
    from comfymodal_runtime import runtime_executor as rex

    state: dict = {}
    with mock.patch.dict(os.environ, {"COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE": "1"}):
        plan = rex._memo_plan_from_state(state)
    assert plan is None
    assert state["opt_exec_signature_memo_eligible"] is False
    assert state["opt_exec_signature_memo_fallback"] == "missing_identity"

    state2: dict = {"opt_exec_signature_memo_identity": {"workflow_hash": "w"}}
    with mock.patch.dict(os.environ, {"COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE": "1"}):
        plan2 = rex._memo_plan_from_state(state2)
    assert plan2 is None
    assert state2["opt_exec_signature_memo_fallback"] == "incomplete_identity"

    # Flag off → no memo attempt at all, requested=False recorded by patch.
    state3: dict = {}
    with mock.patch.dict(os.environ, {"COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE": "0"}):
        plan3 = rex._memo_plan_from_state(state3)
    assert plan3 is None
    assert state3["opt_exec_signature_memo_eligible"] is False


def test_complete_identity_yields_plan_and_key_hash():
    from comfymodal_runtime import runtime_executor as rex

    reset_store()
    state: dict = {
        "opt_exec_signature_memo_identity": {
            "workflow_hash": "wf",
            "deployment_combined_hash": "d",
            "custom_node_generation": "g",
        }
    }
    with mock.patch.dict(os.environ, {"COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE": "1"}):
        plan = rex._memo_plan_from_state(state)
    assert isinstance(plan, str) and plan
    assert state["opt_exec_signature_memo_eligible"] is True
    assert state["opt_exec_signature_memo_key_hash"] == plan
    assert state["opt_exec_signature_memo_key_hash"] == memo_identity(
        workflow_hash="wf", deployment_combined_hash="d", custom_node_generation="g"
    )["identity_hash"]


# ── 8b. env-gate default semantics (unset → enabled, "0" → disabled) ─────
# The COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE gate is default-ENABLED: an unset
# variable arms the memo (subject to the complete-identity check); an explicit
# "0" disables it; an explicit "1" enables it.  These tests drive the REAL
# runtime_executor helpers with the real env_flag parser (no env_flag patch).


def _complete_memo_state() -> dict:
    return {
        "opt_exec_signature_memo_identity": {
            "workflow_hash": "wf",
            "deployment_combined_hash": "d",
            "custom_node_generation": "g",
        }
    }


def test_signature_memo_env_unset_defaults_enabled(monkeypatch):
    """UNSET → enabled (production default): the executor gate passes and a
    complete identity yields a memo plan with eligible=True."""
    from comfymodal_runtime import runtime_executor as rex

    monkeypatch.delenv("COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE", raising=False)
    # The import guard is satisfied (the memo module is importable in tests).
    assert rex._psc_memo_path is not None
    assert rex._signature_memo_enabled() is True
    reset_store()
    state = _complete_memo_state()
    plan = rex._memo_plan_from_state(state)
    assert isinstance(plan, str) and plan
    assert state["opt_exec_signature_memo_eligible"] is True
    assert state["opt_exec_signature_memo_key_hash"] == plan


def test_signature_memo_env_unset_ineligible_when_identity_missing(monkeypatch):
    """UNSET still fails closed on a MISSING identity: the memo is not armed
    and the fallback reason is recorded (never a fabricated hit)."""
    from comfymodal_runtime import runtime_executor as rex

    monkeypatch.delenv("COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE", raising=False)
    state: dict = {}
    plan = rex._memo_plan_from_state(state)
    assert plan is None
    assert state["opt_exec_signature_memo_eligible"] is False
    assert state["opt_exec_signature_memo_fallback"] == "missing_identity"


def test_signature_memo_env_zero_disables(monkeypatch):
    """Explicit "0" → disabled: no memo attempt even with a complete identity."""
    from comfymodal_runtime import runtime_executor as rex

    monkeypatch.setenv("COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE", "0")
    assert rex._signature_memo_enabled() is False
    state = _complete_memo_state()
    plan = rex._memo_plan_from_state(state)
    assert plan is None
    assert state["opt_exec_signature_memo_eligible"] is False


def test_signature_memo_env_one_enables(monkeypatch):
    """Explicit "1" → enabled: the memo plan is returned for a complete
    identity (matches the pre-existing explicit-"1" behavior)."""
    from comfymodal_runtime import runtime_executor as rex

    monkeypatch.setenv("COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE", "1")
    assert rex._signature_memo_enabled() is True
    reset_store()
    state = _complete_memo_state()
    plan = rex._memo_plan_from_state(state)
    assert isinstance(plan, str) and plan
    assert state["opt_exec_signature_memo_eligible"] is True


# ── 9. NaN round-trip preserves always-miss semantics ───────────────────


def test_nan_round_trip_preserves_always_miss_semantics():
    # Original computation of a NaN-bearing signature yields a frozenset that
    # NEVER matches anything (NaN != NaN in frozenset comparison).  The
    # reconstructed memo key must behave identically in a dict lookup.
    prompt = {"1": {"class_type": "SystemNotification", "inputs": {}}}
    original_key = _compute_node_signature(prompt, "1", {"1": float("nan")})

    encoded = encode_hashable(original_key)
    decoded = decode_hashable(encoded)

    assert isinstance(decoded, frozenset)
    cache = {original_key: "hit"}  # type: ignore[dict-item]  # runtime-hashable frozenset
    # Always-miss semantics: the reconstructed key (a different object of the
    # same shape, NaN inside) never matches — and a freshly rebuilt identical
    # shape never matches either.  Same behavior as the original ComfyUI key.
    assert cache.get(decoded) is None
    rebuilt = _compute_node_signature(prompt, "1", {"1": float("nan")})
    assert cache.get(rebuilt) is None
    assert cache.get(original_key) == "hit"  # only the SAME object matches


# ── 10. atomic save / load round-trip; failures do not raise ────────────


def test_save_load_round_trip(tmp_path):
    memo = {
        "hashA": {
            "nodes": {
                "1": {
                    "class_type": "KSampler",
                    "is_changed": False,
                    "signature": {"t": "fz", "items": []},
                    "inputs_hash": "abc123",
                }
            }
        }
    }
    path = tmp_path / "memo.json"
    save_signature_memo(str(path), memo)
    assert path.exists()
    loaded = load_signature_memo(str(path))
    assert loaded == memo

    # Schema version is stamped in the file.
    import json

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["schema_version"] == SCHEMA_VERSION


def test_save_failure_does_not_raise(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file", encoding="utf-8")
    save_signature_memo(str(blocker / "memo.json"), {"hashA": {"nodes": {}}})
    save_signature_memo("", {"hashA": {"nodes": {}}})
    # No exception raised; memo_path() fails closed when env root unset.
    assert memo_path() == ""


def test_store_source_tracking(tmp_path):
    reset_store()
    assert memo_entry_source("hashA") == "none"

    # compute source: set without disk load.
    set_store("hashA", {"nodes": {}})
    assert memo_entry_source("hashA") == "compute"
    assert get_store("hashA") == {"nodes": {}}

    # volume source: an entry present in the file at load time.
    reset_store()
    identity = _identity()
    with mock.patch.dict(
        os.environ, {"COMFYMODAL_V2_STATE_VOLUME_ROOT": str(tmp_path)}
    ):
        from comfymodal_runtime import prompt_signature_cache as psc

        save_signature_memo(
            psc.memo_path(),
            {identity["identity_hash"]: {"nodes": {"1": {"class_type": "X"}}}},
        )
        loaded = load_signature_memo(psc.memo_path())
        assert loaded == {identity["identity_hash"]: {"nodes": {"1": {"class_type": "X"}}}}

        psc.reset_store()
        psc.load_store_from_disk()
        assert memo_entry_source(identity["identity_hash"]) == "volume"


# ── 11. Topo-lazy section (deterministic cached→first-node fix) ──────────
# Per-identity {class_type: {input_name: {"lazy": bool}}} flags.  Fail-closed:
# absent/malformed → None (original path); old entries without "topo_lazy"
# load fine; persistence is atomic + best-effort; identity mismatch never
# crashes.


def test_topo_lazy_get_set_round_trip():
    reset_store()
    identity = _identity()["identity_hash"]
    assert topo_lazy_get(identity, "CheckpointLoaderSimple", "ckpt_name") is None

    topo_lazy_set(identity, "CheckpointLoaderSimple", "ckpt_name", True)
    topo_lazy_set(identity, "CheckpointLoaderSimple", "unet_name", False)
    topo_lazy_set(identity, "CLIPLoader", "clip_name", True)

    assert topo_lazy_get(identity, "CheckpointLoaderSimple", "ckpt_name") is True
    assert topo_lazy_get(identity, "CheckpointLoaderSimple", "unet_name") is False
    assert topo_lazy_get(identity, "CLIPLoader", "clip_name") is True
    # Unknown class / input → None (never a fabricated bool).
    assert topo_lazy_get(identity, "Missing", "x") is None
    assert topo_lazy_get(identity, "CheckpointLoaderSimple", "missing_input") is None
    # The signature nodes section is never touched by topo_lazy_set (a fresh
    # identity starts with an empty nodes section).
    assert get_store(identity) == {"nodes": {}, "topo_lazy": {
        "CheckpointLoaderSimple": {"ckpt_name": {"lazy": True}, "unet_name": {"lazy": False}},
        "CLIPLoader": {"clip_name": {"lazy": True}},
    }}
    assert topo_lazy_pending_count(identity) == 3


def test_topo_lazy_set_fresh_identity_keeps_nodes_section():
    reset_store()
    identity = _identity()["identity_hash"]
    set_store(identity, {"nodes": {"1": {"class_type": "X"}}})
    topo_lazy_set(identity, "X", "y", True)
    entry = get_store(identity)
    assert entry["nodes"] == {"1": {"class_type": "X"}}
    assert topo_lazy_get(identity, "X", "y") is True
    # Overwrite of an existing flag is reflected.
    topo_lazy_set(identity, "X", "y", False)
    assert topo_lazy_get(identity, "X", "y") is False


def test_topo_lazy_persist_writes_and_reloads(tmp_path):
    reset_store()
    identity = _identity()["identity_hash"]
    # Seed a full entry (nodes + topo_lazy) the way a RUN-1 compute-miss
    # would, then persist and reload from disk.
    set_store(identity, {"nodes": {"1": {"class_type": "X"}}})
    topo_lazy_set(identity, "CheckpointLoaderSimple", "ckpt_name", True)
    topo_lazy_set(identity, "CLIPLoader", "clip_name", False)
    with mock.patch.dict(
        os.environ, {"COMFYMODAL_V2_STATE_VOLUME_ROOT": str(tmp_path)}
    ):
        from comfymodal_runtime import prompt_signature_cache as psc

        psc.topo_lazy_persist(identity)
        path = psc.memo_path()
        assert path and os.path.exists(path)

        loaded = load_signature_memo(path)
        entry = loaded[identity]
        assert entry["nodes"] == {"1": {"class_type": "X"}}
        assert entry["topo_lazy"] == {
            "CheckpointLoaderSimple": {"ckpt_name": {"lazy": True}},
            "CLIPLoader": {"clip_name": {"lazy": False}},
        }
        # Schema version is stamped as before.
        import json

        raw = json.loads(open(path, encoding="utf-8").read())
        assert raw["schema_version"] == SCHEMA_VERSION

        # A fresh in-memory store reloading the file serves the lazy flags.
        psc.reset_store()
        psc.load_store_from_disk()
        assert psc.topo_lazy_get(identity, "CheckpointLoaderSimple", "ckpt_name") is True
        assert psc.topo_lazy_get(identity, "CLIPLoader", "clip_name") is False
        assert psc.topo_lazy_pending_count(identity) == 2


def test_topo_lazy_old_format_loads_fine(tmp_path):
    # Entries WITHOUT a topo_lazy section (pre-fix format) load and serve
    # None (original path) without crashing.
    reset_store()
    identity = _identity()["identity_hash"]
    set_store(identity, {"nodes": {"1": {"class_type": "X"}}})
    with mock.patch.dict(
        os.environ, {"COMFYMODAL_V2_STATE_VOLUME_ROOT": str(tmp_path)}
    ):
        from comfymodal_runtime import prompt_signature_cache as psc

        psc.persist_store()
        psc.reset_store()
        psc.load_store_from_disk()
    assert psc.topo_lazy_get(identity, "X", "y") is None
    assert psc.topo_lazy_pending_count(identity) == 0
    # The nodes section is still served for the signature memo.
    entry = get_store(identity)
    assert entry["nodes"] == {"1": {"class_type": "X"}}


def test_topo_lazy_identity_mismatch_fail_closed():
    # A DIFFERENT identity hash never sees another identity's lazy flags and
    # never raises.
    reset_store()
    identity_a = _identity(workflow_hash="wf-a")["identity_hash"]
    identity_b = _identity(workflow_hash="wf-b")["identity_hash"]
    topo_lazy_set(identity_a, "X", "y", True)
    assert topo_lazy_get(identity_b, "X", "y") is None
    assert topo_lazy_pending_count(identity_b) == 0
    # Malformed store shapes never raise and return None / 0.
    set_store(identity_b, {"nodes": "junk"})
    assert topo_lazy_get(identity_b, "X", "y") is None
    assert topo_lazy_pending_count(identity_b) == 0
    set_store(identity_b, {"topo_lazy": "junk"})
    assert topo_lazy_get(identity_b, "X", "y") is None
    assert topo_lazy_pending_count(identity_b) == 0
    set_store(identity_b, {"topo_lazy": {"X": {"y": "not-a-dict"}}})
    assert topo_lazy_get(identity_b, "X", "y") is None
    set_store(identity_b, {"topo_lazy": {"X": {"y": {"lazy": "yes"}}}})
    assert topo_lazy_get(identity_b, "X", "y") is None
