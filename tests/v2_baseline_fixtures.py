"""Sanitized V2 cold-start baseline rows for waterfall reconciliation tests.

Each row mirrors a real cold run's dispatch/restore/method-entry accounting
without any secrets, model paths, instance identifiers, or raw log content.
The rows are complete enough for ``build_waterfall`` to reconcile: every
stage's duration is derivable from the provided fields, so the platform row
(``dispatch_to_modal_entry_ms - restore_total_ms -
restore_end_to_modal_method_ms``) is fully attributed instead of leaking into
the generic residual.

Each fixture carries:
  - ``command_start_unix_ms`` / ``response_received_unix_ns``  (local clock)
  - ``request_origin_info`` boundaries for the two local rows
  - the three platform source fields (dispatch / restore / restore-to-method)
  - the application-stage duration fields that close the remaining gap
"""

from __future__ import annotations

BASELINE_ROW_1 = {
    "request_id": "v2-baseline-row-1",
    "identity": {
        "restored_instance_id": "ri-baseline-1",
        "gpu": "rtx-pro-6000",
        "restore_count": 1,
        "request_count": 1,
    },
    "command_start_unix_ms": 1000.0,
    "response_received_unix_ns": 54_006_038_000,
    "trace": {
        "events": [],
        "metadata": {
            "request_origin_info": {
                "ui_run_triggered_wall_unix_ms": 1000.0,
                "local_receive_wall_ns": 1_004_500_000,
                "modal_submission_attempt_wall_unix_ns": 1_010_000_000,
            }
        },
    },
    "dispatch_to_modal_entry_ms": 27096.038,
    "restore_total_ms": 1631.935,
    "restore_end_to_modal_method_ms": 104.897,
    "method_entry_to_graph_start_ms": 700.0,
    "executor_call_to_first_node_ms": 1200.0,
    "first_node_to_clip_ms": 900.0,
    "clip_to_sampler_node_ms": 1100.0,
    "sampler_node_to_sampler_start_ms": 300.0,
    "sampler_ms": 19000.0,
    "post_sampling_transition_ms": 500.0,
    "vae_decode_ms": 1100.0,
    "output_collection_ms": 900.0,
    "remote_return_ms": 200.0,
}

BASELINE_ROW_2 = {
    "request_id": "v2-baseline-row-2",
    "identity": {
        "restored_instance_id": "ri-baseline-2",
        "gpu": "rtx-pro-6000",
        "restore_count": 1,
        "request_count": 1,
    },
    "command_start_unix_ms": 2000.0,
    "response_received_unix_ns": 41_280_500_000,
    "trace": {
        "events": [],
        "metadata": {
            "request_origin_info": {
                "ui_run_triggered_wall_unix_ms": 2000.0,
                "local_receive_wall_ns": 2_003_000_000,
                "modal_submission_attempt_wall_unix_ns": 2_010_000_000,
            }
        },
    },
    "dispatch_to_modal_entry_ms": 18120.5,
    "restore_total_ms": 1487.2,
    "restore_end_to_modal_method_ms": 98.3,
    "method_entry_to_graph_start_ms": 650.0,
    "executor_call_to_first_node_ms": 980.0,
    "first_node_to_clip_ms": 760.0,
    "clip_to_sampler_node_ms": 940.0,
    "sampler_node_to_sampler_start_ms": 260.0,
    "sampler_ms": 15200.0,
    "post_sampling_transition_ms": 420.0,
    "vae_decode_ms": 950.0,
    "output_collection_ms": 810.0,
    "remote_return_ms": 180.0,
}

BASELINE_ROW_3 = {
    "request_id": "v2-baseline-row-3",
    "identity": {
        "restored_instance_id": "ri-baseline-3",
        "gpu": "rtx-pro-6000",
        "restore_count": 1,
        "request_count": 1,
    },
    "command_start_unix_ms": 500.0,
    "response_received_unix_ns": 48_069_700_000,
    "trace": {
        "events": [],
        "metadata": {
            "request_origin_info": {
                "ui_run_triggered_wall_unix_ms": 500.0,
                "local_receive_wall_ns": 502_800_000,
                "modal_submission_attempt_wall_unix_ns": 509_000_000,
            }
        },
    },
    "dispatch_to_modal_entry_ms": 24030.7,
    "restore_total_ms": 1510.4,
    "restore_end_to_modal_method_ms": 102.1,
    "method_entry_to_graph_start_ms": 690.0,
    "executor_call_to_first_node_ms": 1100.0,
    "first_node_to_clip_ms": 850.0,
    "clip_to_sampler_node_ms": 1020.0,
    "sampler_node_to_sampler_start_ms": 280.0,
    "sampler_ms": 17100.0,
    "post_sampling_transition_ms": 460.0,
    "vae_decode_ms": 1000.0,
    "output_collection_ms": 840.0,
    "remote_return_ms": 190.0,
}

# The three supplied baseline rows, each reconciled by tests/test_v2_waterfall.py.
BASELINE_ROWS = (BASELINE_ROW_1, BASELINE_ROW_2, BASELINE_ROW_3)

__all__ = ["BASELINE_ROW_1", "BASELINE_ROW_2", "BASELINE_ROW_3", "BASELINE_ROWS"]
