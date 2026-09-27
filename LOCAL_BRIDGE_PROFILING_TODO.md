# Local Bridge Profiling — Completion Status

## What's Implemented

The local bridge code lives in `__init__.py`. The following v4 instrumentation has been added:

### `/comfymodal/prompt` route handler
- `t0_client_press` — earliest known press timestamp
- `t1_local_bridge_received` — route handler entered
- `t1a_local_payload_parse_start` / `t1b_local_payload_parse_end` — around JSON payload parsing
- `t1c_local_preflight_start` / `t1d_local_preflight_end` — around API prompt validation
- `t2_local_modal_submit_start` — before queue enqueue
- `_client_trace` dict built and attached to extra_data with: trace_id, events list, stages dict

### `_execute_job` function
Uses the existing `Trace` class (via `trace.mark()`) which now also feeds into v4 events via `TraceV4`.

### Baselining
- `t10_local_materialized` — already present from `trace.mark("t10_local_materialized")`
- `t10b_local_save_start` / `t10c_local_save_end` — already present

## Not Yet Implemented (Additional Instrumentation Needed)

### Local-side detailed materialization breakdown
The `_execute_job` function in `__init__.py` performs:
- base64 decode of each image entry (lines ~1049-1059)
- file write to local output directory
- per-node `_send("executed", ...)` events

These should be wrapped with:
- `t9_local_remote_result_received` — when `_modal_result` is assigned
- `t9a_local_result_deserialize_start` / `t9b_local_result_deserialize_end` — around result JSON decode
- `t9c_local_base64_decode_start` / `t9d_local_base64_decode_end` — around base64 decode loop
- `t9e_local_file_write_start` / `t9f_local_file_write_end` — around file write loop
- `t10a_local_response_to_comfy_start` / `t10b_local_response_to_comfy_end` — before/after `_send("execution_success", ...)`

### browser/UI-level timestamps
- `t11_local_ui_done` — requires client-side JavaScript instrumentation in the ComfyUI frontend
- `t0_client_press` is sent from the browser in the request body — this is already working

### Active profile write timing
- `t1e_active_profile_write_start` / `t1f_active_profile_write_end` — should wrap the `set_active_warmup_profile()` call in `_execute_job` (around line ~902-912)

### Clock skew estimation
The `estimate_clock_skew()` function exists in `profiler_trace_v4.py` but needs:
- `t2_local_modal_submit_start` (local wall time)
- `t2c_first_remote_event_received` (local receives first remote streaming event)
- `t3_modal_entry` (remote wall time, available in returned trace)

## Priority Order for Remaining Work

1. **High**: Materialization breakdown (t9a-t9f, t10a-t10b) — closes the ~5-6s explanation gap
2. **Medium**: Active profile write timing (t1e-t1f)
3. **Low**: Clock skew estimation
4. **Lowest**: Browser UI-side t11

## How the `_client_trace` Dict Flows

```
__init__.py (local bridge)
    │  Builds _client_trace dict with:
    │    trace_id, events[...], stages{t0, t1, t2}
    │  Attaches to extra_data["_client_trace"]
    ▼
comfyapp.py (Modal remote)
    │  Receives via trace param (which contains _client_trace)
    │  Merges into wall_clock_trace_v3
    ▼
__init__.py (local bridge receives result)
    │  wall_clock_trace is in result["wall_clock_trace"]
    ▼
benchmark_modal_e2e.py (benchmark harness)
    │  Parses wall_clock_trace from result
    │  Computes critical path, deltas, explanations
```

## Testing the Flow

To verify the trace flows end-to-end:

1. Set `COMFYMODAL_PROFILE_LEVEL=detailed` (or `trace` or `trace_verbose`)
2. Run a normal generation via ComfyUI frontend
3. Check the returned JSON result for:
   - `result["wall_clock_trace"]` — full wall clock trace with all stage timestamps
   - `result["_wall_clock_summary"]` — compact summary
   - `result["trace"]["stages"]` — timing_trace stages
4. Look for `[wall_trace.summary]` log line in the Modal container logs
