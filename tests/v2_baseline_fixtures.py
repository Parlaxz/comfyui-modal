"""Sanitized V2 cold-start baseline rows for waterfall reconciliation tests.

Each row mirrors one of the three user-supplied true-cold runs.  The exact
supplied values are preserved verbatim:

  - command-to-response total (``command_start_unix_ms`` ->
    ``response_received_unix_ns``)
  - ``dispatch_to_modal_entry_ms``
  - ``restore_total_ms``
  - ``restore_end_to_modal_method_ms``
  - provider/region placement (GCP/us-east4, AWS/us-east-2)

The platform row is derived exactly as
``dispatch_to_modal_entry_ms - restore_total_ms -
restore_end_to_modal_method_ms`` and is always positive, so known platform
time is fully attributed instead of leaking into the generic residual.

Remaining accounted application/output fields (remote method setup, prompt
executor setup, CLIP/sampler-node pre-sampler spans, sampling, post-sampling
transition, VAE, output persistence, and remote return) are clearly
sanitized deterministic values chosen so the accounted total reconciles to
exactly the supplied total (reconciliation == 0, well inside
``max(50ms, 0.5% total)``).

``BASELINE_EXPECTED`` carries the exact supplied values per run so tests
assert fixture totals and exact source values, not merely self-consistency.
"""

from __future__ import annotations

# ── Run 1 ── GCP / us-east-4 ──────────────────────────────────────────────
# Supplied: total 18494.000ms, dispatch 8361.423ms, restore 469.297ms,
# restore-to-method 13.397ms.
BASELINE_ROW_1 = {
    "request_id": "v2-baseline-row-1",
    "identity": {
        "restored_instance_id": "ri-baseline-1",
        "gpu": "rtx-pro-6000",
        "restore_count": 1,
        "request_count": 1,
        "cloud": "GCP",
        "region": "us-east4",
    },
    "command_start_unix_ms": 1000.0,
    "response_received_unix_ns": 19_494_000_000,
    "trace": {
        "events": [],
        "metadata": {
            "request_origin_info": {
                "ui_run_triggered_wall_unix_ms": 1000.0,
                "local_receive_wall_ns": 1_004_000_000,
                "modal_submission_attempt_wall_unix_ns": 1_016_000_000,
            }
        },
    },
    "dispatch_to_modal_entry_ms": 8361.423,
    "restore_total_ms": 469.297,
    "restore_end_to_modal_method_ms": 13.397,
    "method_entry_to_graph_start_ms": 240.0,
    "executor_call_to_first_node_ms": 320.0,
    "first_node_to_clip_ms": 210.0,
    "clip_to_sampler_node_ms": 480.0,
    "sampler_node_to_sampler_start_ms": 90.0,
    "sampler_ms": 6956.577,
    "post_sampling_transition_ms": 260.0,
    "vae_decode_ms": 810.0,
    "output_collection_ms": 540.0,
    "remote_return_ms": 210.0,
}

# ── Run 2 ── AWS / us-east-2 ──────────────────────────────────────────────
# Supplied: total 18628.000ms, dispatch 5685.895ms, restore 701.322ms,
# restore-to-method 29.368ms.
BASELINE_ROW_2 = {
    "request_id": "v2-baseline-row-2",
    "identity": {
        "restored_instance_id": "ri-baseline-2",
        "gpu": "rtx-pro-6000",
        "restore_count": 1,
        "request_count": 1,
        "cloud": "AWS",
        "region": "us-east-2",
    },
    "command_start_unix_ms": 2000.0,
    "response_received_unix_ns": 20_628_000_000,
    "trace": {
        "events": [],
        "metadata": {
            "request_origin_info": {
                "ui_run_triggered_wall_unix_ms": 2000.0,
                "local_receive_wall_ns": 2_005_000_000,
                "modal_submission_attempt_wall_unix_ns": 2_019_000_000,
            }
        },
    },
    "dispatch_to_modal_entry_ms": 5685.895,
    "restore_total_ms": 701.322,
    "restore_end_to_modal_method_ms": 29.368,
    "method_entry_to_graph_start_ms": 310.0,
    "executor_call_to_first_node_ms": 420.0,
    "first_node_to_clip_ms": 270.0,
    "clip_to_sampler_node_ms": 620.0,
    "sampler_node_to_sampler_start_ms": 120.0,
    "sampler_ms": 9073.105,
    "post_sampling_transition_ms": 340.0,
    "vae_decode_ms": 890.0,
    "output_collection_ms": 640.0,
    "remote_return_ms": 240.0,
}

# ── Run 3 ── AWS / us-east-2 ──────────────────────────────────────────────
# Supplied: total 27179.000ms, dispatch 10229.069ms, restore 2930.539ms,
# restore-to-method 86.642ms.
BASELINE_ROW_3 = {
    "request_id": "v2-baseline-row-3",
    "identity": {
        "restored_instance_id": "ri-baseline-3",
        "gpu": "rtx-pro-6000",
        "restore_count": 1,
        "request_count": 1,
        "cloud": "AWS",
        "region": "us-east-2",
    },
    "command_start_unix_ms": 500.0,
    "response_received_unix_ns": 27_679_000_000,
    "trace": {
        "events": [],
        "metadata": {
            "request_origin_info": {
                "ui_run_triggered_wall_unix_ms": 500.0,
                "local_receive_wall_ns": 506_000_000,
                "modal_submission_attempt_wall_unix_ns": 524_000_000,
            }
        },
    },
    "dispatch_to_modal_entry_ms": 10229.069,
    "restore_total_ms": 2930.539,
    "restore_end_to_modal_method_ms": 86.642,
    "method_entry_to_graph_start_ms": 410.0,
    "executor_call_to_first_node_ms": 560.0,
    "first_node_to_clip_ms": 330.0,
    "clip_to_sampler_node_ms": 780.0,
    "sampler_node_to_sampler_start_ms": 160.0,
    "sampler_ms": 11995.931,
    "post_sampling_transition_ms": 420.0,
    "vae_decode_ms": 1150.0,
    "output_collection_ms": 820.0,
    "remote_return_ms": 300.0,
}

# Exact supplied source values per run, in the same order as BASELINE_ROWS.
# Tests assert these verbatim (totals and source fields), not self-consistency.
BASELINE_EXPECTED = (
    {
        "total_ms": 18494.000,
        "dispatch_to_modal_entry_ms": 8361.423,
        "restore_total_ms": 469.297,
        "restore_end_to_modal_method_ms": 13.397,
        "platform_ms": 7878.729,
        "cloud": "GCP",
        "region": "us-east4",
    },
    {
        "total_ms": 18628.000,
        "dispatch_to_modal_entry_ms": 5685.895,
        "restore_total_ms": 701.322,
        "restore_end_to_modal_method_ms": 29.368,
        "platform_ms": 4955.205,
        "cloud": "AWS",
        "region": "us-east-2",
    },
    {
        "total_ms": 27179.000,
        "dispatch_to_modal_entry_ms": 10229.069,
        "restore_total_ms": 2930.539,
        "restore_end_to_modal_method_ms": 86.642,
        "platform_ms": 7211.888,
        "cloud": "AWS",
        "region": "us-east-2",
    },
)

# The three supplied baseline rows, each reconciled by tests/test_v2_waterfall.py.
BASELINE_ROWS = (BASELINE_ROW_1, BASELINE_ROW_2, BASELINE_ROW_3)

__all__ = [
    "BASELINE_ROW_1",
    "BASELINE_ROW_2",
    "BASELINE_ROW_3",
    "BASELINE_EXPECTED",
    "BASELINE_ROWS",
]
