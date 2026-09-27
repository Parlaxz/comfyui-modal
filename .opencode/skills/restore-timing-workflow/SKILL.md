---
name: restore-timing-workflow
description: Use when restore_timing key is absent from ComfyUI history meta, when edits to __init__.py don't take effect, when benchmark runs fail at deploy step, or when debugging the Modal-to-local data flow for prompt execution timing.
---

# Restore Timing Workflow

## Data Flow Overview

When a prompt runs through comfyui-modal, timing data flows through these layers:

```
Modal Container (comfyapp.py)
  │
  │ restore() → self._last_restore_timing = {restore_total_ms, warmup_preload_ms, ...}
  │ run_prompt() returns {"_restore_timing": ..., "trace": ..., "images": ..., "videos": ...}
  │
  ▼
Local ComfyUI (__init__.py)
  │
  │ _execute_job() calls modal_client.run_prompt()
  │   → extracts result["_restore_timing"]
  │   → adds it to _meta dict: _meta["restore_timing"] = result.get("_restore_timing", {})
  │   → calls _finish_job(meta=_meta)
  │
  │ _finish_job() creates history_result = {"outputs": ..., "meta": dict(meta)}
  │   → pq.task_done(item_id, history_result, status=status)
  │   → ComfyUI stores in prompt_queue.history[prompt_id] = {"outputs": ..., "meta": ...}
  │
  ▼
HTTP API
  │
  │ GET /history/{prompt_id} returns the stored entry
  │ benchmark_modal.py calls _poll_history(prompt_id) to read it
  │   → entry["meta"]["restore_timing"] contains the restore breakdown
  │   → _write_summary() extracts and saves it
```

## The .pyc Cache Trap

**Most common reason edits don't take effect:** ComfyUI loads compiled bytecode (`.pyc`) from `__pycache__/` at startup. The `.pyc` is compiled only once when the module is first imported. Subsequent edits to `__init__.py` have NO EFFECT until ComfyUI is restarted AND the `.pyc` is deleted.

**Symptoms:**
- You edit `__init__.py` to add `"restore_timing"` to the meta dict
- Diagnostic prints/file-writes you add never appear
- Old behavior persists despite clear source changes
- The `.pyc` timestamp is older than your edits

**Fix:**
```powershell
# 1. Kill ComfyUI
Stop-Process -Id $pid -Force
Start-Sleep -Seconds 2

# 2. Delete the stale bytecode cache
Remove-Item -Path "ComfyUI\custom_nodes\comfyui-modal\__pycache__\__init__.cpython-313.pyc" -Force

# 3. Restart ComfyUI
python -s ComfyUI\main.py --listen 127.0.0.1 --port 8188 --windows-standalone-build --disable-auto-launch
```

**Verify the fix:** Check the `.pyc` was recompiled after restart — its `LastWriteTime` should be AFTER your edits:
```powershell
Get-ChildItem -Path "ComfyUI\custom_nodes\comfyui-modal\__pycache__\__init__*.pyc"
```

## Diagnostic Techniques

### Problem: `print()` output is invisible

When ComfyUI runs in a subprocess (e.g., via `Start-Process -RedirectStandardOutput` or `subprocess.DEVNULL`), `print()` calls from custom node code go to the captured stream — NOT the console. Additionally, ComfyUI's custom logging system intercepts stdout for `comfyui.log`.

**Solution: File-write diagnostics**

Instead of `print()`, write to a file in the node directory:

```python
_dbg_path = os.path.join(_NODE_DIR, "_debug.log")
with open(_dbg_path, "a", encoding="utf-8") as _f:
    _f.write(f"[{time.time():.3f}] meta keys={list(meta.keys())}\n")
```

This works regardless of how ComfyUI was started, because files survive process boundaries.

### Problem: Stale ComfyUI log

The `user/comfyui.log` may be from a previous ComfyUI instance. The current instance might have its stdout redirected. **Check the file timestamp** against when you started ComfyUI.

### Key inspection points for restore_timing data flow

1. **Modal side** — Check `comfyapp.py` line ~2526 for `DEBUG result keys=[... '_restore_timing'...]` in Modal logs (`modal logs comfyui`)
2. **Local reception** — Add file-write diagnostic at `__init__.py:670` (where `_rt_val = result.get("_restore_timing")`) to verify Modal returned it
3. **Meta assembly** — Add file-write at `__init__.py:678-684` (where `_meta` dict is built) to verify `restore_timing` key is in the meta before `_finish_job`
4. **History persistence** — Check `__init__.py:470` where `history_result = {"outputs": outputs, "meta": dict(meta or {})}` — the `dict()` call makes a shallow copy

## Running Benchmarks

### Quick test (for validating restore_timing)

```python
# _test_flow.py pattern:
snapshot = json_req("GET /comfymodal/benchmark/workflow")
payload = {"prompt": snapshot["payload"]["prompt"], "client_id": str(uuid4())}
result = json_req("POST /comfymodal/prompt", payload)
prompt_id = result["prompt_id"]
# Poll /history/{prompt_id} until available
entry = data[prompt_id]
meta = entry.get("meta", {})
print("Has restore_timing:", "restore_timing" in meta)
```

### Full benchmark (benchmark_modal.py)

**Control-plane rule:** For current deployment or benchmark work, use the
authoritative `python tools/v2ctl.py` flow (`deploy-run`, `run`, and `gate` with
the resolved profile). Do not invoke legacy BAT wrappers directly or substitute
the default/restore-only app. Record the v2ctl manifests and resolved flags.
The BAT workaround below is retained only for explicitly requested legacy
reproduction.

**Known issues:**
- `benchmark_modal.py run2` terminates existing ComfyUI and redeploys Modal via a batch script
- The batch script (`redeploy_modal_and_run_comfyui.bat`) can hang on Windows due to `'charmap' codec` encoding errors when Modal outputs Unicode chars (✓)
- The benchmark may also fail if the saved workflow snapshot is stale/wrong

**Workaround for deploy failures:**
```powershell
# 1. Deploy Modal manually first
modal deploy ComfyUI\custom_nodes\comfyui-modal\comfyapp.py

# 2. Start ComfyUI manually
python -s ComfyUI\main.py --listen 127.0.0.1 --port 8188 --windows-standalone-build --disable-auto-launch

# 3. Save the benchmark workflow
# (POST Flux workflow to /comfymodal/benchmark/workflow)

# 4. Run the test flow
python -s ComfyUI\custom_nodes\comfyui-modal\_test_flow.py
```

### Benchmark artifact structure

Each run creates a timestamped directory in `benchmark_runs/YYYY-MM-DD_HH-MM-SS/`:
- `workflow_snapshot.json` — the workflow that was submitted
- `benchmark.log` — step-by-step log
- `run1_response.json` — full history entry for cold prompt
- `run1_trace.json` — extracted timing trace
- `run2_response.json` — full history entry for warm prompt
- `run2_trace.json` — extracted timing trace
- `summary.json` — aggregated metrics including restore timing
- `summary.md` — human-readable summary

## Key Files Reference

| File | Role |
|------|------|
| `comfyapp.py` (Modal side) | `restore()` at line ~2324 sets `self._last_restore_timing` with 6 phase timers. `run_prompt()` at line ~2467 returns `_restore_timing` in the result dict. |
| `__init__.py` (local side) | `_execute_job()` at line ~672 extracts `_restore_timing` from Modal result and builds `_meta` dict. `_finish_job()` at line ~470 stores via `pq.task_done()`. Routes registered at line ~700+. |
| `modal_client.py` | `run_prompt()` wrapper — passes workflow to Modal's `ComfyAPI.*.remote()`. |
| `benchmark_modal.py` | Benchmark harness — loads snapshot, deploys, submits prompts, polls history, writes artifacts. |
| `timing_trace.py` | `Trace` class with `mark()`/`summary()` for instrumentation. |
| `latest_benchmark_workflow.json` | Persistent snapshot of the last workflow submitted to the benchmark endpoint. |

## Restore Timing Phase Reference

| Phase | Typical (cold) | Description |
|-------|---------------|-------------|
| `restore_total_ms` | 10,000–12,500 | Total time from container resume to ready |
| `warmup_preload_ms` | 7,000–10,500 (78–83%) | Model loading: CLIP → UNet → VAE into ComfyUI model cache |
| `sage_runtime_ms` | 1,600–1,700 (16–17%) | SageAttention detection and patching |
| `cuda_warmup_ms` | 280–370 (3–4%) | CUDA context initialization + torch CUDA warmup |
| `gpu_state_ms` | 160–190 (1–2%) | GPU state restoration (env vars, memory tracking) |
| `ensure_models_ms` | ~0 (0%) | Model file existence check |

## Common Pitfalls

1. **Stale bytecode** — Most common. Always delete `__pycache__/` + restart after editing `__init__.py`.
2. **Benchmark deploy hangs** — Batch script has `'charmap'` encoding issues with Unicode output. Deploy manually.
3. **Wrong workflow snapshot** — Benchmark may pick up an SD1.5 or other stale workflow. Always verify hash matches expected Flux workflow (`e9d91c5322e1`).
4. **ComfyUI process zombie** — `netstat -ano | Select-String ":8188"` may show a ghost process. Use `Stop-Process -Id $pid -Force` + verify port freed before restarting.
5. **Debug prints invisible** — `print()` from custom node code goes to ComfyUI's log system or captured stdout, not console. Use file-write diagnostics instead.
