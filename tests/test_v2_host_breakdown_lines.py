"""Host-side provenance re-emission lines (RUN-1 gate).

Remote (Modal container) stdout never reaches the captured benchmark log, so
``tools/benchmark_v2_direct.py`` re-prints the prompt-executor / conditioning-
cache breakdowns and PNG provenance from the run artifact after every run.

Covered here (all pure, synthetic artifacts — no Modal, no network):
  - PE line: exec-to-cached children and residual reconcile to the parents,
    ``signature_keys_ms`` derivation, and ``absent`` handling when children
    are missing (partially and entirely).
  - CC line: core key/value mapping from ``lookup_diagnostics``, the decision
    event, and opt-gated fields appended only when present.
  - PNG line: encoder + descriptor values, with optional fields omitted.
  - Missing events / malformed artifacts → ``None`` (never raises).
"""

import unittest
from typing import Any

from tools.benchmark_v2_direct import (
    format_host_conditioning_breakdown,
    format_host_png_output,
    format_host_prompt_executor_breakdown,
)

_REQ = "req-host-lines-1"

def _pe_artifact(breakdown=None, extra_metadata=None):
    """Artifact with a prompt_executor_milestones event."""
    metadata = {
        "execution_start_to_cached_ms": 100.0,
        "cached_to_first_node_ms": 50.0,
    }
    if breakdown is not None:
        metadata["breakdown"] = breakdown
    if extra_metadata:
        metadata.update(extra_metadata)
    return {
        "request_id": _REQ,
        "full_trace": {
            "events": [
                {"name": "prompt_executor_milestones", "metadata": metadata},
            ]
        },
    }


_PE_BREAKDOWN = {
    "dynamic_prompt_ms": 10.0,
    "is_changed_ms": 5.0,
    "signature_keys_total_ms": 30.0,
    "seed_apply_ms": 10.0,
    "clean_unused_ms": 10.0,
    "cache_gather_ms": 15.0,
    "cleanup_gc_ms": 10.0,
    "c2f_topo_walk_ms": 20.0,
    "c2f_stage_ms": 10.0,
    "c2f_first_node_prefix_ms": 5.0,
}


def _cc_artifact(diagnostics=None, decision: str | None = "miss_stored", add_opt_fields=True):
    """Artifact with clip_conditioning_cache_lookup + decision events."""
    diag = {
        "total_ms": 205.364,
        "key_build_digest_ms": 0.18,
        "lock_wait_ms": 0.006,
        "manifest_read_ms": 205.124,
        "manifest_read_bytes": 1765,
        "manifest_entries": 11,
        "entry_lookup_ms": 0.002,
        "header_bytes_read": 0,
        "data_bytes_read": 0,
        "lru_touch_ms": 0.0,
        "lru_touch_mode": "sync",
        "measured_children_ms": 205.312,
        "residual_ms": 0.052,
    }
    if add_opt_fields:
        diag.update({
            "entry_header_open_read_ms": 1.5,
            "entry_header_parse_ms": 0.25,
            "entry_deserialize_ms": 3.0,
            "deser_tensor_count": 2,
            "deser_tensors_bytes": 65536,
            "hit_read_bytes": 4096,
            "hit_read_mbps": 250.0,
        })
    if diagnostics is not None:
        diag.update(diagnostics)
    events = [
        {
            "name": "clip_conditioning_cache_lookup",
            "metadata": {"lookup_wall_ms": 205.539, "lookup_diagnostics": diag},
        },
    ]
    if decision is not None:
        events.append(
            {"name": "clip_conditioning_cache_decision", "metadata": {"decision": decision}}
        )
    return {"request_id": _REQ, "full_trace": {"events": events}}


def _png_artifact(metadata=None, descriptor=None):
    """Artifact with an output_encode_end event + output_descriptor."""
    enc_meta = {"duration_ms": 169.476}
    if metadata:
        enc_meta.update(metadata)
    desc = {
        "asset_id": "abc123def456",
        "width": 1088,
        "height": 1920,
        "byte_count": 3129718,
        "filename": "out.png",
    }
    if descriptor is not None:
        desc.update(descriptor)
    return {
        "request_id": _REQ,
        "full_trace": {
            "events": [{"name": "output_encode_end", "metadata": enc_meta}]
        },
        "output_descriptor": [desc],
    }


def _png_duplicate_artifact(events, descriptor=None):
    """Artifact with multiple output_encode_end events + a descriptor."""
    desc = {
        "asset_id": "abc123def456",
        "width": 1088,
        "height": 1920,
        "byte_count": 3129718,
        "filename": "out.png",
    }
    if descriptor is not None:
        desc.update(descriptor)
    return {
        "request_id": _REQ,
        "full_trace": {"events": list(events)},
        "output_descriptor": [desc],
    }


def _parse(line):
    """Split a provenance line into {key: value}, skipping the tag token."""
    assert line is not None
    return dict(part.split("=", 1) for part in line.split(" ") if "=" in part)


class TestPromptExecutorBreakdownLine(unittest.TestCase):
    def test_full_breakdown_reconciles_to_parents(self):
        """Children + residual sum exactly to the milestone parents."""
        line = format_host_prompt_executor_breakdown(
            _pe_artifact(_PE_BREAKDOWN)
        )
        self.assertIsNotNone(line)
        self.assertTrue(str(line).startswith("[v2.prompt_executor_breakdown]"))
        parts = _parse(line)
        self.assertEqual(parts["request_id"], _REQ)
        self.assertEqual(parts["exec_to_cached_ms"], "100.0")
        self.assertEqual(parts["dynamic_prompt_ms"], "10.0")
        self.assertEqual(parts["is_changed_ms"], "5.0")
        # signature_keys_ms = signature_keys_total_ms - is_changed_ms = 25.0
        self.assertEqual(parts["signature_keys_ms"], "25.0")
        self.assertEqual(parts["seed_apply_ms"], "10.0")
        self.assertEqual(parts["clean_unused_ms"], "10.0")
        self.assertEqual(parts["cache_gather_ms"], "15.0")
        self.assertEqual(parts["cleanup_gc_ms"], "10.0")
        # 10 + 5 + 25 + 10 + 10 + 15 + 10 = 85 → 100 - 85 = 15
        self.assertEqual(parts["residual_ms"], "15.0")
        self.assertEqual(parts["c2f_cached_to_first_node_ms"], "50.0")
        self.assertEqual(parts["c2f_topo_walk_ms"], "20.0")
        self.assertEqual(parts["c2f_stage_ms"], "10.0")
        self.assertEqual(parts["c2f_first_node_prefix_ms"], "5.0")
        # 20 + 10 + 5 = 35 → 50 - 35 = 15
        self.assertEqual(parts["c2f_residual_ms"], "15.0")

    def test_partially_missing_children_render_absent_but_keep_residual(self):
        """A missing child renders ``absent`` yet the residual still emits
        from the PRESENT children (absent children are part of the residual)."""
        breakdown = dict(_PE_BREAKDOWN)
        del breakdown["seed_apply_ms"]  # exec-to-cached child missing
        del breakdown["c2f_stage_ms"]  # c2f child missing
        line = format_host_prompt_executor_breakdown(_pe_artifact(breakdown))
        parts = _parse(line)
        # Derived signature_keys_ms is still computable (both sources present).
        self.assertEqual(parts["signature_keys_ms"], "25.0")
        self.assertEqual(parts["seed_apply_ms"], "absent")
        # Present exec children: 10 + 5 + 25 + 10 + 15 + 10 = 75 → 100 − 75.
        self.assertEqual(parts["residual_ms"], "25.0")
        self.assertEqual(parts["c2f_stage_ms"], "absent")
        # Present c2f children: 20 + 5 = 25 → 50 − 25.
        self.assertEqual(parts["c2f_residual_ms"], "25.0")
        # Surviving fields still render.
        self.assertEqual(parts["exec_to_cached_ms"], "100.0")
        self.assertEqual(parts["c2f_topo_walk_ms"], "20.0")

    def test_missing_signature_sources_render_absent(self):
        """Without signature_keys_total_ms, signature_keys_ms is absent, but
        the exec residual still emits from the remaining present children."""
        breakdown = dict(_PE_BREAKDOWN)
        del breakdown["signature_keys_total_ms"]
        line = format_host_prompt_executor_breakdown(_pe_artifact(breakdown))
        parts = _parse(line)
        self.assertEqual(parts["signature_keys_ms"], "absent")
        # Present children: 10 + 5 + 10 + 10 + 15 + 10 = 60 → 100 − 60.
        self.assertEqual(parts["residual_ms"], "40.0")
        self.assertEqual(parts["is_changed_ms"], "5.0")

    def test_no_breakdown_dict_line_keeps_parents(self):
        """Without the breakdown dict the line still prints parents and
        renders every child as absent."""
        line = format_host_prompt_executor_breakdown(_pe_artifact())
        self.assertIsNotNone(line)
        parts = _parse(line)
        self.assertEqual(parts["request_id"], _REQ)
        self.assertEqual(parts["exec_to_cached_ms"], "100.0")
        self.assertEqual(parts["c2f_cached_to_first_node_ms"], "50.0")
        for key in (
            "dynamic_prompt_ms",
            "is_changed_ms",
            "signature_keys_ms",
            "seed_apply_ms",
            "clean_unused_ms",
            "cache_gather_ms",
            "cleanup_gc_ms",
            "residual_ms",
            "c2f_topo_walk_ms",
            "c2f_stage_ms",
            "c2f_first_node_prefix_ms",
            "c2f_residual_ms",
        ):
            self.assertEqual(parts[key], "absent")

    def test_run1_shape_seed_apply_absent_keeps_residuals(self):
        """RUN-1 regression: seed_apply_ms absent on the snapshot-restore
        request — the exec residual must still emit (parent − sum(present)),
        and a corrected (non-double-counted) c2f prefix keeps c2f_residual_ms
        in the ~0..-1ms band instead of the -138.269 full-window artifact."""
        breakdown = {
            "dynamic_prompt_ms": 0.005,
            "is_changed_ms": 0.483,
            "signature_keys_total_ms": 1409.064,
            # seed_apply_ms deliberately absent
            "clean_unused_ms": 0.017,
            "cache_gather_ms": 0.065,
            "cleanup_gc_ms": 4.666,
            "c2f_topo_walk_ms": 137.295,
            "c2f_stage_ms": 0.974,
            "c2f_first_node_prefix_ms": 0.0,  # corrected: post-staging remainder
        }
        line = format_host_prompt_executor_breakdown(
            _pe_artifact(
                breakdown,
                extra_metadata={
                    "execution_start_to_cached_ms": 1429.485,
                    "cached_to_first_node_ms": 137.443,
                },
            )
        )
        parts = _parse(line)
        self.assertEqual(parts["seed_apply_ms"], "absent")
        # 1429.485 − (0.005 + 0.483 + 1408.581 + 0.017 + 0.065 + 4.666)
        #              = 1429.485 − 1413.817 = 15.668 (the ~15.7 ms gap).
        self.assertEqual(parts["residual_ms"], "15.668")
        # 137.443 − (137.295 + 0.974 + 0.0) = -0.826 (overlap artifact band).
        self.assertEqual(parts["c2f_residual_ms"], "-0.826")
        # Never the -138.269 double-count shape.
        self.assertNotEqual(parts["c2f_residual_ms"], "-138.269")

    def test_missing_event_returns_none(self):
        """No milestones event → None, no raise."""
        artifact = {"request_id": _REQ, "full_trace": {"events": []}}
        self.assertIsNone(format_host_prompt_executor_breakdown(artifact))
        # Parents missing entirely → None (even with a breakdown dict present).
        no_parents = {
            "request_id": _REQ,
            "full_trace": {
                "events": [
                    {
                        "name": "prompt_executor_milestones",
                        "metadata": {"breakdown": dict(_PE_BREAKDOWN)},
                    }
                ]
            },
        }
        self.assertIsNone(format_host_prompt_executor_breakdown(no_parents))
        self.assertIsNone(format_host_prompt_executor_breakdown(None))
        self.assertIsNone(
            format_host_prompt_executor_breakdown(
                {"request_id": _REQ, "full_trace": "not-a-dict"}
            )
        )
        self.assertIsNone(
            format_host_prompt_executor_breakdown(
                {"request_id": _REQ, "full_trace": {"events": "not-a-list"}}
            )
        )

    def test_extra_keys_pass_through_after_fixed_fields(self):
        """RUN-1 gate: new metadata["breakdown"] keys (Task-1 signature-cache
        fields) are appended after the fixed fields, rendered key=value.
        None-valued extra keys are omitted entirely (never key=absent)."""
        breakdown: Any = dict(_PE_BREAKDOWN)
        breakdown.update({
            "signature_cache_requested": 1,
            "signature_cache_eligible": 1,
            "signature_cache_hit": 0,
            "signature_cache_source": "none",
            "signature_cache_key_hash": "539ba82f0c1d4e9a",
            "signature_cache_fallback": "no_entry",
            "signature_reuse_ms": None,
        })
        line = format_host_prompt_executor_breakdown(_pe_artifact(breakdown))
        self.assertIsNotNone(line)
        line_str = str(line)
        parts = _parse(line_str)
        self.assertEqual(parts["signature_cache_requested"], "1")
        self.assertEqual(parts["signature_cache_eligible"], "1")
        self.assertEqual(parts["signature_cache_hit"], "0")
        self.assertEqual(parts["signature_cache_source"], "none")
        self.assertEqual(parts["signature_cache_key_hash"], "539ba82f0c1d4e9a")
        self.assertEqual(parts["signature_cache_fallback"], "no_entry")
        # None extra is omitted entirely, not rendered key=absent.
        self.assertNotIn("signature_reuse_ms", parts)
        # Fixed fields unchanged and the extras come strictly AFTER the last
        # fixed field (c2f_residual_ms).
        fixed = line_str.rpartition("c2f_residual_ms=")[0]
        self.assertNotIn("signature_cache_", fixed)
        self.assertLess(
            line_str.index("c2f_residual_ms="), line_str.index("signature_cache_requested=")
        )

    def test_extra_keys_sorted_and_handled_keys_not_duplicated(self):
        """Extras appear in sorted order; signature_keys_total_ms (consumed by
        the signature_keys_ms derivation) and every fixed key never duplicate."""
        breakdown: Any = dict(_PE_BREAKDOWN)
        breakdown.update({
            "signature_cache_requested": 1,
            "signature_cache_source": "none",
            "zz_extra": 5.25,
        })
        line = format_host_prompt_executor_breakdown(_pe_artifact(breakdown))
        self.assertIsNotNone(line)
        line_str = str(line)
        parts = _parse(line_str)
        # Derived field unchanged; consumed source key never re-emitted.
        self.assertEqual(parts["signature_keys_ms"], "25.0")
        self.assertNotIn("signature_keys_total_ms", parts)
        # Extras after the fixed fields and mutually sorted.
        self.assertLess(
            line_str.index("signature_cache_requested="), line_str.index("signature_cache_source=")
        )
        self.assertLess(
            line_str.index("signature_cache_source="), line_str.index("zz_extra=")
        )
        self.assertEqual(parts["zz_extra"], "5.25")

    def test_extra_nested_all_scalar_subdict_flattened(self):
        """A nested all-scalar sub-dict in breakdown is flattened one level so
        its keys still surface as key=value."""
        breakdown: Any = dict(_PE_BREAKDOWN)
        breakdown["signature_memo"] = {
            "signature_cache_requested": 1,
            "signature_cache_source": "none",
        }
        line = format_host_prompt_executor_breakdown(_pe_artifact(breakdown))
        self.assertIsNotNone(line)
        parts = _parse(str(line))
        self.assertEqual(parts["signature_cache_requested"], "1")
        self.assertEqual(parts["signature_cache_source"], "none")


class TestConditioningBreakdownLine(unittest.TestCase):
    def test_core_and_opt_fields(self):
        """Core keys map from lookup_diagnostics; opt fields append."""
        line = format_host_conditioning_breakdown(_cc_artifact())
        self.assertIsNotNone(line)
        self.assertTrue(str(line).startswith("[v2.conditioning_exact_hit_breakdown]"))
        parts = _parse(line)
        self.assertEqual(parts["request_id"], _REQ)
        self.assertEqual(parts["decision"], "miss_stored")
        self.assertEqual(parts["lookup_wall_ms"], "205.539")
        self.assertEqual(parts["total_ms"], "205.364")
        self.assertEqual(parts["key_build_ms"], "0.18")
        self.assertEqual(parts["lock_wait_ms"], "0.006")
        self.assertEqual(parts["manifest_read_ms"], "205.124")
        self.assertEqual(parts["manifest_bytes"], "1765")
        self.assertEqual(parts["manifest_entries"], "11")
        self.assertEqual(parts["entry_lookup_ms"], "0.002")
        self.assertEqual(parts["header_bytes"], "0")
        self.assertEqual(parts["data_bytes"], "0")
        self.assertEqual(parts["lru_touch_ms"], "0.0")
        self.assertEqual(parts["lru_touch_mode"], "sync")
        self.assertEqual(parts["children_ms"], "205.312")
        self.assertEqual(parts["residual_ms"], "0.052")
        # Opt-gated fields appended when present.
        self.assertEqual(parts["entry_header_open_read_ms"], "1.5")
        self.assertEqual(parts["entry_header_parse_ms"], "0.25")
        self.assertEqual(parts["entry_deserialize_ms"], "3.0")
        self.assertEqual(parts["deser_tensor_count"], "2")
        self.assertEqual(parts["deser_tensors_bytes"], "65536")
        self.assertEqual(parts["hit_read_bytes"], "4096")
        self.assertEqual(parts["hit_read_mbps"], "250.0")

    def test_opt_fields_omitted_when_absent(self):
        """No opt fields → not present; missing decision → absent."""
        line = format_host_conditioning_breakdown(
            _cc_artifact(add_opt_fields=False, decision=None)
        )
        parts = _parse(line)
        self.assertEqual(parts["decision"], "absent")
        for key in (
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
        ):
            self.assertNotIn(key, parts)
        # Core fields still present.
        self.assertEqual(parts["total_ms"], "205.364")
        self.assertEqual(parts["manifest_entries"], "11")

    def test_prefetch_fields_pass_through_after_fixed_fields(self):
        """RUN-1 gate: new lookup_diagnostics keys (Task-2 prefetch /
        in-memory-cache fields, including the upcoming prefetch_reason) are
        appended after the fixed fields, rendered key=value."""
        line = format_host_conditioning_breakdown(_cc_artifact(
            {
                "prefetch_requested": 1,
                "prefetch_wall_ms": 2.5,
                "prefetch_overlap_ms": 1.25,
                "prefetch_source": "plan_time",
                "prefetch_reason": "stale_manifest",
                "manifest_memory_hit": 1,
                "payload_memory_hit": 0,
                "normal_lookup_fallback": 0,
            },
            add_opt_fields=False,
        ))
        self.assertIsNotNone(line)
        line_str = str(line)
        parts = _parse(line_str)
        self.assertEqual(parts["prefetch_requested"], "1")
        self.assertEqual(parts["prefetch_wall_ms"], "2.5")
        self.assertEqual(parts["prefetch_overlap_ms"], "1.25")
        self.assertEqual(parts["prefetch_source"], "plan_time")
        self.assertEqual(parts["prefetch_reason"], "stale_manifest")
        self.assertEqual(parts["manifest_memory_hit"], "1")
        self.assertEqual(parts["payload_memory_hit"], "0")
        self.assertEqual(parts["normal_lookup_fallback"], "0")
        # Extras come strictly AFTER the last fixed field (residual_ms).
        fixed = line_str.rpartition("residual_ms=")[0]
        self.assertNotIn("prefetch_", fixed)
        self.assertNotIn("manifest_memory_hit", fixed)

    def test_renamed_source_keys_not_duplicated(self):
        """Source-dict keys that are renamed on emit (key_build_digest_ms →
        key_build_ms, header_bytes_read → header_bytes, measured_children_ms →
        children_ms, manifest_read_bytes → manifest_bytes) are never
        re-emitted by the pass-through."""
        line = format_host_conditioning_breakdown(
            _cc_artifact(add_opt_fields=False)
        )
        self.assertIsNotNone(line)
        parts = _parse(str(line))
        self.assertEqual(parts["key_build_ms"], "0.18")
        self.assertNotIn("key_build_digest_ms", parts)
        self.assertEqual(parts["header_bytes"], "0")
        self.assertNotIn("header_bytes_read", parts)
        self.assertEqual(parts["children_ms"], "205.312")
        self.assertNotIn("measured_children_ms", parts)
        self.assertEqual(parts["manifest_bytes"], "1765")
        self.assertNotIn("manifest_read_bytes", parts)
        self.assertNotIn("data_bytes_read", parts)

    def test_extra_none_values_omitted(self):
        """None-valued extra keys are omitted entirely (never key=absent)."""
        line = format_host_conditioning_breakdown(_cc_artifact(
            {"prefetch_requested": 1, "prefetch_reason": None},
            add_opt_fields=False,
        ))
        self.assertIsNotNone(line)
        parts = _parse(str(line))
        self.assertEqual(parts["prefetch_requested"], "1")
        self.assertNotIn("prefetch_reason", parts)

    def test_nested_prefetch_subdict_flattened(self):
        """A nested all-scalar sub-dict in lookup_diagnostics (e.g. a future
        prefetch sub-dict) is flattened one level so its keys surface."""
        line = format_host_conditioning_breakdown(_cc_artifact(
            {"prefetch": {
                "prefetch_requested": 1,
                "prefetch_source": "plan_time",
            }},
            add_opt_fields=False,
        ))
        self.assertIsNotNone(line)
        parts = _parse(str(line))
        self.assertEqual(parts["prefetch_requested"], "1")
        self.assertEqual(parts["prefetch_source"], "plan_time")

    def test_missing_lookup_event_returns_none(self):
        """No lookup event → None, no raise."""
        artifact = {"request_id": _REQ, "full_trace": {"events": []}}
        self.assertIsNone(format_host_conditioning_breakdown(artifact))
        self.assertIsNone(format_host_conditioning_breakdown(None))


class TestPngOutputLine(unittest.TestCase):
    def test_full_line(self):
        """Encoder + descriptor values render; request_id prefixes."""
        line = format_host_png_output(
            _png_artifact(metadata={"compress_level": 6, "png_compress_ms": 100.5})
        )
        self.assertIsNotNone(line)
        self.assertTrue(str(line).startswith("[v2.png_output]"))
        parts = _parse(line)
        self.assertEqual(parts["request_id"], _REQ)
        self.assertEqual(parts["compress_level"], "6")
        self.assertEqual(parts["png_encode_ms"], "169.476")
        self.assertEqual(parts["png_compress_ms"], "100.5")
        self.assertEqual(parts["width"], "1088")
        self.assertEqual(parts["height"], "1920")
        self.assertEqual(parts["bytes"], "3129718")
        self.assertEqual(parts["sha"], "abc123def456")

    def test_optional_fields_omitted_when_absent(self):
        """compress_level / png_compress_ms / duration_ms omitted when absent."""
        line = format_host_png_output(
            _png_artifact(metadata={"duration_ms": 169.476})
        )
        parts = _parse(line)
        self.assertNotIn("compress_level", parts)
        self.assertNotIn("png_compress_ms", parts)
        self.assertEqual(parts["png_encode_ms"], "169.476")
        self.assertEqual(parts["width"], "1088")
        self.assertEqual(parts["sha"], "abc123def456")

    def test_duplicate_empty_then_populated_prefers_populated(self):
        """RUN-2 regression: a metadata-less legacy ``output_encode_end`` event
        (``metadata={}``) BEFORE the populated execution event must not hide the
        encoder fields — the line renders compress_level / png_encode_ms /
        png_compress_ms from the populated event regardless of order."""
        empty = {"name": "output_encode_end", "metadata": {}}
        populated = {
            "name": "output_encode_end",
            "metadata": {
                "duration_ms": 154.592,
                "compress_level": 1,
                "png_compress_ms": 149.492,
            },
        }
        line = format_host_png_output(_png_duplicate_artifact([empty, populated]))
        self.assertIsNotNone(line)
        parts = _parse(line)
        self.assertEqual(parts["compress_level"], "1")
        self.assertEqual(parts["png_encode_ms"], "154.592")
        self.assertEqual(parts["png_compress_ms"], "149.492")
        self.assertEqual(parts["width"], "1088")
        self.assertEqual(parts["height"], "1920")
        self.assertEqual(parts["bytes"], "3129718")
        self.assertEqual(parts["sha"], "abc123def456")

    def test_duplicate_populated_then_empty_still_works(self):
        """RUN-1c order (populated first, metadata-less legacy duplicate after)
        keeps producing the full encoder line."""
        empty = {"name": "output_encode_end", "metadata": {}}
        populated = {
            "name": "output_encode_end",
            "metadata": {
                "duration_ms": 156.965,
                "compress_level": 1,
                "png_compress_ms": 151.972,
            },
        }
        line = format_host_png_output(_png_duplicate_artifact([populated, empty]))
        self.assertIsNotNone(line)
        parts = _parse(line)
        self.assertEqual(parts["compress_level"], "1")
        self.assertEqual(parts["png_encode_ms"], "156.965")
        self.assertEqual(parts["png_compress_ms"], "151.972")

    def test_only_empty_encode_event_renders_descriptor_only(self):
        """No populated ``output_encode_end`` event → the descriptor-only line
        (width/height/bytes/sha) still renders as today, encoder fields omitted."""
        artifact = _png_duplicate_artifact(
            [{"name": "output_encode_end", "metadata": {}}]
        )
        line = format_host_png_output(artifact)
        self.assertIsNotNone(line)
        parts = _parse(line)
        self.assertNotIn("compress_level", parts)
        self.assertNotIn("png_encode_ms", parts)
        self.assertNotIn("png_compress_ms", parts)
        self.assertEqual(parts["width"], "1088")
        self.assertEqual(parts["height"], "1920")
        self.assertEqual(parts["bytes"], "3129718")
        self.assertEqual(parts["sha"], "abc123def456")

    def test_missing_event_or_descriptor_returns_none(self):
        """No encode event or no descriptor → None, no raise."""
        self.assertIsNone(
            format_host_png_output({"request_id": _REQ, "full_trace": {"events": []}})
        )
        no_descriptor = {
            "request_id": _REQ,
            "full_trace": {
                "events": [{"name": "output_encode_end", "metadata": {"duration_ms": 1.0}}]
            },
        }
        self.assertIsNone(format_host_png_output(no_descriptor))
        empty_descriptor = dict(no_descriptor, output_descriptor=[])
        self.assertIsNone(format_host_png_output(empty_descriptor))
        self.assertIsNone(format_host_png_output(None))

    def test_malformed_events_never_raise(self):
        """Non-dict events / non-dict descriptor entries degrade to None."""
        artifact = {
            "request_id": _REQ,
            "full_trace": {"events": ["junk", 42, None]},
            "output_descriptor": ["junk"],
        }
        self.assertIsNone(format_host_prompt_executor_breakdown(artifact))
        self.assertIsNone(format_host_conditioning_breakdown(artifact))
        self.assertIsNone(format_host_png_output(artifact))

    def test_raw_run_artifact_layout_fallback(self):
        """The raw _run_one artifact carries the trace under result.trace and
        the descriptors under result.asset_descriptors — all three lines must
        still resolve."""
        milestone = {
            "name": "prompt_executor_milestones",
            "metadata": {
                "execution_start_to_cached_ms": 100.0,
                "cached_to_first_node_ms": 50.0,
                "breakdown": dict(_PE_BREAKDOWN),
            },
        }
        lookup = {
            "name": "clip_conditioning_cache_lookup",
            "metadata": {
                "lookup_wall_ms": 205.539,
                "lookup_diagnostics": {
                    "total_ms": 205.364,
                    "key_build_digest_ms": 0.18,
                    "lock_wait_ms": 0.006,
                    "manifest_read_ms": 205.124,
                    "manifest_read_bytes": 1765,
                    "manifest_entries": 11,
                    "entry_lookup_ms": 0.002,
                    "header_bytes_read": 0,
                    "data_bytes_read": 0,
                    "lru_touch_ms": 0.0,
                    "lru_touch_mode": "sync",
                    "measured_children_ms": 205.312,
                    "residual_ms": 0.052,
                },
            },
        }
        decision = {
            "name": "clip_conditioning_cache_decision",
            "metadata": {"decision": "miss_stored"},
        }
        encode = {
            "name": "output_encode_end",
            "metadata": {"duration_ms": 169.476, "compress_level": 6},
        }
        artifact = {
            "request_id": _REQ,
            "result": {
                "trace": {"events": [lookup, decision, milestone, encode]},
                "asset_descriptors": [{
                    "asset_id": "abc123def456",
                    "width": 1088,
                    "height": 1920,
                    "byte_count": 3129718,
                    "filename": "out.png",
                }],
            },
        }
        pe_parts = _parse(format_host_prompt_executor_breakdown(artifact))
        self.assertEqual(pe_parts["exec_to_cached_ms"], "100.0")
        self.assertEqual(pe_parts["residual_ms"], "15.0")
        self.assertEqual(pe_parts["c2f_residual_ms"], "15.0")
        cc_parts = _parse(format_host_conditioning_breakdown(artifact))
        self.assertEqual(cc_parts["decision"], "miss_stored")
        self.assertEqual(cc_parts["total_ms"], "205.364")
        png_parts = _parse(format_host_png_output(artifact))
        self.assertEqual(png_parts["png_encode_ms"], "169.476")
        self.assertEqual(png_parts["width"], "1088")
        self.assertEqual(png_parts["sha"], "abc123def456")


if __name__ == "__main__":
    unittest.main()
