"""Focused tests for the bounded ``[v2.conditioning_exact_hit_breakdown]``
line emitted by ``model_preload.execution_prefill``.

The formatter is a pure function over the always-on lookup diagnostics
recorded by ``clip_conditioning_cache.lookup_many`` plus the opt-gated
fields that appear under ``COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS=1``.
These tests verify the reconciliation identity, the fixed always-on key
set, and the present/absent opt-gated field behavior — no cache, key,
lock, or persistence behavior is exercised.
"""

from __future__ import annotations

from typing import Any

from comfymodal_runtime.model_preload import format_conditioning_exact_hit_breakdown

# Always-on emitted keys (fixed order per the instrumentation contract).
EXPECTED_ALWAYS_ON_KEYS: list[str] = [
    "request_id",
    "decision",
    "lookup_wall_ms",
    "total_ms",
    "key_build_ms",
    "lock_wait_ms",
    "manifest_read_ms",
    "manifest_bytes",
    "manifest_entries",
    "entry_lookup_ms",
    "header_bytes",
    "data_bytes",
    "lru_touch_ms",
    "lru_touch_mode",
    "opt",
    "children_ms",
    "residual_ms",
]

# Opt-gated fields appended only when present in the diagnostics dict.
OPT_GATED_KEYS: list[str] = [
    "entry_header_open_read_ms",
    "entry_header_parse_ms",
    "entry_header_validate_ms",
    "entry_data_open_read_ms",
    "entry_deserialize_ms",
    "deser_payload_sha_ms",
    "deser_tensor_sha_ms",
    "deser_tensor_rebuild_ms",
    "deser_materialize_ms",
    "deser_tensor_count",
    "deser_tensors_bytes",
    "hit_read_bytes",
    "hit_read_mbps",
]


def _synthetic_diag(with_opt: bool = False) -> dict[str, Any]:
    """Reconciliation-realistic synthetic lookup diagnostics.

    ``measured_children_ms`` is the sum of the always-on child timers and
    ``residual_ms`` is ``total_ms - children``, mirroring the arithmetic in
    ``clip_conditioning_cache.lookup_many``.
    """
    children_ms = (
        0.002   # lock_wait_ms
        + 0.0   # volume_reload_ms
        + 154.277  # manifest_read_ms
        + 0.201  # key_build_digest_ms
        + 192.304  # entry_lookup_ms
        + 30.526  # lru_touch_ms
    )
    total_ms = 377.71
    diag: dict[str, Any] = {
        "lock_wait_ms": 0.002,
        "volume_reload_ms": 0.0,
        "manifest_read_ms": 154.277,
        "manifest_read_bytes": 4096,
        "manifest_entries": 3,
        "key_build_digest_ms": 0.201,
        "entry_lookup_ms": 192.304,
        "header_bytes_read": 512,
        "data_bytes_read": 1048576,
        "lru_touch_ms": 30.526,
        "lru_touch_mode": "sync",
        "entries_requested": 2,
        "hit_count": 2,
        "miss_count": 0,
        "total_ms": total_ms,
        "measured_children_ms": round(children_ms, 3),
        "residual_ms": round(total_ms - children_ms, 3),
    }
    if with_opt:
        diag.update(
            {
                "entry_header_open_read_ms": 0.5,
                "entry_header_parse_ms": 0.3,
                "entry_header_validate_ms": 0.2,
                "entry_data_open_read_ms": 1.0,
                "entry_deserialize_ms": 2.5,
                "deser_payload_sha_ms": 0.7,
                "deser_tensor_sha_ms": 0.4,
                "deser_tensor_rebuild_ms": 1.2,
                "deser_materialize_ms": 3.1,
                "deser_tensor_count": 2,
                "deser_tensors_bytes": 2097152,
                "hit_read_bytes": 1049088,
                "hit_read_mbps": 1100.0,
            }
        )
    return diag


def _to_pairs(line: str) -> dict[str, str]:
    """Parse the space-separated ``key=value`` line (after the prefix)."""
    tokens = line.split()
    assert tokens[0] == "[v2.conditioning_exact_hit_breakdown]", tokens[0]
    pairs: dict[str, str] = {}
    for token in tokens[1:]:
        key, _, value = token.partition("=")
        pairs[key] = value
    return pairs


class TestReconciliation:
    def test_children_sum_plus_residual_equals_lookup_wall(self) -> None:
        diag = _synthetic_diag()
        line = format_conditioning_exact_hit_breakdown(
            diag,
            request_id="req-1",
            decision="exact_hit",
            lookup_wall_ms=diag["total_ms"],
        )
        pairs = _to_pairs(line)
        children = (
            float(pairs["lock_wait_ms"])
            + float(pairs["manifest_read_ms"])
            + float(pairs["key_build_ms"])
            + float(pairs["entry_lookup_ms"])
            + float(pairs["lru_touch_ms"])
        )
        residual = float(pairs["residual_ms"])
        lookup_wall = float(pairs["lookup_wall_ms"])
        # Emitted identity: children + residual == total == lookup_wall.
        assert round(children + residual, 3) == lookup_wall
        # Measured-children field agrees with the emitted child sum.
        assert float(pairs["children_ms"]) == round(children, 3)
        # Internal cache reconciliation also holds (volume_reload_ms == 0).
        assert round(children + residual, 3) == diag["total_ms"]


class TestAlwaysOnKeys:
    def test_all_always_on_keys_present(self) -> None:
        diag = _synthetic_diag()
        line = format_conditioning_exact_hit_breakdown(
            diag,
            request_id="req-always",
            decision="miss_stored",
            lookup_wall_ms=377.71,
        )
        pairs = _to_pairs(line)
        for key in EXPECTED_ALWAYS_ON_KEYS:
            assert key in pairs, f"missing always-on key: {key}"

    def test_always_on_values_map_from_diagnostics(self) -> None:
        diag = _synthetic_diag()
        line = format_conditioning_exact_hit_breakdown(
            diag,
            request_id="req-values",
            decision="exact_hit",
            lookup_wall_ms=377.71,
        )
        pairs = _to_pairs(line)
        assert pairs["request_id"] == "req-values"
        assert pairs["decision"] == "exact_hit"
        assert pairs["lookup_wall_ms"] == "377.71"
        assert pairs["total_ms"] == str(diag["total_ms"])
        assert pairs["key_build_ms"] == str(diag["key_build_digest_ms"])
        assert pairs["manifest_bytes"] == str(diag["manifest_read_bytes"])
        assert pairs["manifest_entries"] == str(diag["manifest_entries"])
        assert pairs["header_bytes"] == str(diag["header_bytes_read"])
        assert pairs["data_bytes"] == str(diag["data_bytes_read"])
        assert pairs["lru_touch_mode"] == "sync"
        assert pairs["opt"] == "1"

    def test_field_order_matches_contract(self) -> None:
        diag = _synthetic_diag(with_opt=True)
        line = format_conditioning_exact_hit_breakdown(
            diag,
            request_id="req-order",
            decision="exact_hit",
            lookup_wall_ms=377.71,
        )
        tokens = line.split()
        assert tokens[0] == "[v2.conditioning_exact_hit_breakdown]"
        keys = [t.partition("=")[0] for t in tokens[1:]]
        expected = (
            EXPECTED_ALWAYS_ON_KEYS[:14]  # request_id .. lru_touch_mode
            + ["opt"]
            + EXPECTED_ALWAYS_ON_KEYS[15:]  # children_ms, residual_ms
            + OPT_GATED_KEYS
        )
        assert keys == expected

    def test_request_id_falls_back_to_absent(self) -> None:
        diag = _synthetic_diag()
        line = format_conditioning_exact_hit_breakdown(
            diag, request_id="", decision="miss_not_stored", lookup_wall_ms=377.71
        )
        pairs = _to_pairs(line)
        assert pairs["request_id"] == "absent"


class TestOptGatedFields:
    def test_opt_fields_appended_when_present(self) -> None:
        diag = _synthetic_diag(with_opt=True)
        line = format_conditioning_exact_hit_breakdown(
            diag,
            request_id="req-opt",
            decision="exact_hit",
            lookup_wall_ms=diag["total_ms"],
        )
        pairs = _to_pairs(line)
        for key in OPT_GATED_KEYS:
            assert key in pairs, f"missing opt-gated key: {key}"
        assert pairs["hit_read_bytes"] == "1049088"
        assert pairs["hit_read_mbps"] == "1100.0"

    def test_opt_fields_omitted_when_absent(self) -> None:
        diag = _synthetic_diag(with_opt=False)
        line = format_conditioning_exact_hit_breakdown(
            diag,
            request_id="req-noopt",
            decision="exact_hit",
            lookup_wall_ms=diag["total_ms"],
        )
        pairs = _to_pairs(line)
        for key in OPT_GATED_KEYS:
            assert key not in pairs, f"unexpected opt-gated key: {key}"
        # Marker stays even without opt-gated fields.
        assert pairs["opt"] == "1"

    def test_opt_fields_omitted_when_absent_on_miss_decision(self) -> None:
        diag = _synthetic_diag(with_opt=False)
        for decision in ("miss_stored", "miss_not_stored"):
            line = format_conditioning_exact_hit_breakdown(
                diag,
                request_id=f"req-{decision}",
                decision=decision,
                lookup_wall_ms=diag["total_ms"],
            )
            pairs = _to_pairs(line)
            assert pairs["decision"] == decision
            for key in OPT_GATED_KEYS:
                assert key not in pairs, f"unexpected opt-gated key: {key}"
