# V2 Batch E12 - Generic Checkpoint Prewarm Reader

Date: 2026-08-16

Scope: a generic, stdlib-only, default-OFF checkpoint/safetensors prewarm
reader that issues a single cooperative daemon-thread sequential read pass over
a request's physical checkpoint paths during the unrelated-setup window, then
hard-bounded joins/abandons before the native demand loader begins. Delivered
as a standalone module with **no production wiring** (see TOP_RISK and the
integration section below).

## Lifecycle Audit Findings (from the established repository audit)

The prewarm feature is only meaningful if it runs *after* authoritative
physical paths are known and *before* the native demand schedule, and only
while unrelated setup is still running. The audit anchors:

- **PREWARM_EARLIEST_SAFE_START** = request plan receipt, after authoritative
  physical paths are resolved. Anchor: `comfymodal_runtime/modal_app.py:16675-16689`
  (`ExecutionPlan.from_dict(...)` at 16675, then the existing execution-UNET
  schedule at 16689). At this point the plan exists and model identity is
  derivable, so request-specific physical paths can be resolved.
- **DEMAND_LOADER_BEGIN** = `comfymodal_runtime/model_preload.py:13348`
  `_load_unet` (the physical UNET loader), with the demand schedule at
  `modal_app.py:16689`. The prewarm guard must stop/join (or abandon) strictly
  before this point so the demand loader never contends with the reader.
- **AVAILABLE_OVERLAP_WINDOW** = after paths are known / plan receipt and
  before the existing demand schedule, only while unrelated setup runs. The
  reader overlaps *unrelated setup* (never the demand loader); this is exactly
  what `prewarm_overlap_with_setup_ms` measures.

### Why restore is not safe for request-specific paths

`modal_app.py:9938` (`self._restore_plan = None`) shows restore is
snapshot/lifecycle-only: it never reads a globally shared current plan, and
request-specific model/workflow decisions arrive only with `run_plan_stream`.
There is therefore **no restore plan** from which to derive request-specific
physical paths at restore time, so prewarm cannot be anchored there.

### Why the generic module is delivered without production wiring

- Wiring would collide with the E11 staged-transport integration surface.
- Model names still need authoritative resolution to physical paths via
  `folder_paths.get_full_path_or_raise` before `start()` is called; that
  resolution is not yet wired.
- The module is intentionally a *generic physical-path API* so integration can
  resolve names → paths and call `start(paths)` / `before_demand_load()`.

## Implementation

`comfymodal_runtime/checkpoint_prewarm.py`

- **Generic path-list API**: `resolve_prewarm_paths(paths)` returns a
  deterministic, first-occurrence de-duplicated physical path list (accepts
  `str`/`os.PathLike`, drops `None`); telemetry preserves that list as
  `prewarm_files` and also exposes `prewarm_file_count`.
- **`CheckpointPrewarmer`** lifecycle: `start(paths)` →
  (`mark_setup_start`/`mark_setup_end` for overlap telemetry) →
  `before_demand_load()` (alias `stop_and_join_before_demand()`). One-shot:
  after the demand guard runs, `start()` refuses to restart.
- **Default OFF**: `COMFYMODAL_V2_CHECKPOINT_PREWARM=0` (absent/`0` → off).
  Bounds parsed from `COMFYMODAL_V2_CHECKPOINT_PREWARM_MAX_MB=0` and
  `COMFYMODAL_V2_CHECKPOINT_PREWARM_MAX_MS=0`; `0`/absent/invalid/negative
  fail closed to *no bound*, which is only meaningful once the feature is
  explicitly enabled.
- **One daemon reader thread**, controlled `Event`, single reusable buffer of
  exactly 8 MiB (default `DEFAULT_CHUNK_BYTES = 8 * 1024 * 1024`, matching
  `modal_app.py:_VOLUME_READ_CHUNK_BYTES` at `modal_app.py:4955`).
- **Unbuffered binary + `readinto`**: `open(path, "rb", buffering=0)` and
  `readinto` into the reusable buffer, so no checkpoint payload is retained in
  Python state. No O_DIRECT, DONTNEED, GDS, io_uring, mmap, or pinned memory.
  `posix_fadvise(POSIX_FADV_SEQUENTIAL)` is advisory-only (best-effort, ignored
  on Windows) and never telemetry-claimed as residency.
- **Bounds**: `max_bytes` total and `max_wall_ms` wall; the stop event is
  checked between chunks and between files.
- **Fail-open**: missing/unreadable files are recorded (`prewarm_open_errors`,
  `prewarm_read_errors`, stop reason `completed_with_errors`) and skipped;
  remaining deterministic paths are still walked; a later demand load is never
  blocked by a prewarm failure.
- **Hard-bounded join**: `before_demand_load()` stops and joins with
  `join_timeout_ms` (default 1000 ms, clamped to 60 s; dedicated env
  `COMFYMODAL_V2_CHECKPOINT_PREWARM_JOIN_MS`). On timeout the prewarm is
  *abandoned* (state retired, buffer dropped) and demand proceeds; the worker
  is daemon and cooperative, so it never wedges inference.
- **Telemetry** (`as_dict()`): `prewarm_enabled`, `prewarm_started`,
  `prewarm_start_at`, `prewarm_stop_at`, `prewarm_files`, `prewarm_bytes`,
  `prewarm_read_calls`, `prewarm_wall_ms`, `prewarm_thread_cpu_ms` (when
  available), `prewarm_stop_reason`, `prewarm_join_ms`,
  `prewarm_overlap_with_setup_ms`, `demand_loader_start_at`,
  `prewarm_finished_before_demand`. Monotonic timestamps. Truthful naming:
  `prewarm_bytes` / `bytes_read_for_prewarm` = bytes *read by the prewarm
  reader*, never a residency/cache claim.
- **No retained payload**: the buffer is cleared on worker completion and on
  abandon from the prewarmer object state; a bounded worker-local buffer can
  remain only until an uninterruptible filesystem read returns. Idempotent
  stop/join and disabled/no-path cases are handled.

The byte bound is exact: the final `readinto` target is a bounded memoryview,
so `prewarm_bytes` never exceeds `max_bytes`.

## Module API (exact)

```python
from comfymodal_runtime.checkpoint_prewarm import CheckpointPrewarmer, resolve_prewarm_paths

prewarmer = CheckpointPrewarmer(
    enabled=None,          # None -> COMFYMODAL_V2_CHECKPOINT_PREWARM (default OFF)
    max_bytes=None,        # None -> COMFYMODAL_V2_CHECKPOINT_PREWARM_MAX_MB (0 = no bound)
    max_wall_ms=None,      # None -> COMFYMODAL_V2_CHECKPOINT_PREWARM_MAX_MS (0 = no bound)
    chunk_bytes=8 * 1024 * 1024,
    join_timeout_ms=None,  # None -> COMFYMODAL_V2_CHECKPOINT_PREWARM_JOIN_MS (default 1000)
)

paths = resolve_prewarm_paths(["/abs/a.safetensors", "/abs/b.safetensors"])  # dedup, ordered
prewarmer.mark_setup_start()          # optional: open the unrelated-setup window
started = prewarmer.start(paths)      # True only when a worker actually started
prewarmer.mark_setup_end()            # optional: close the unrelated-setup window
joined = prewarmer.before_demand_load()  # stop/join or abandon; then demand may run
snapshot = prewarmer.as_dict()        # truthful telemetry
```

## Integration Locations (future, E13+)

- Resolve request model names → physical paths via
  `folder_paths.get_full_path_or_raise` at plan receipt
  (`modal_app.py:16675-16689`).
- `start(paths)` immediately after paths are resolved (overlapping unrelated
  setup).
- `before_demand_load()` immediately before the native demand schedule
  (`modal_app.py:16689` / `model_preload.py:13348` `_load_unet`).

## Local Evidence

Focused offline tests only; no Modal, no deploy, no paid workload.

```
TESTS = 27 E12 tests (tests/test_v2_e12_checkpoint_prewarm.py)
COVERAGE = start/stop, cancellation mid-file, max-bytes, max-time,
           join-timeout abandon, missing file fail-open, dedup,
           deterministic multi-file order, no retained payload,
           demand guard before normal loader, failure does not block loader,
           synthetic slow-reader overlap (overlap with unrelated setup,
           no demand overlap with active reader), env parsing, telemetry keys
PY_COMPILE = PASS (comfymodal_runtime/checkpoint_prewarm.py,
                   tests/test_v2_e12_checkpoint_prewarm.py)
REMOTE_RUNS = 0
COMMIT = none
READY_FOR_INTEGRATION = YES
```

## E12 Completion Matrix

```
E12_COMPLETE
PREWARM_IMPLEMENTED = YES (standalone generic module + focused tests)
EARLIEST_SAFE_START = request plan receipt after authoritative physical paths are resolved; modal_app.py:16675-16689
DEMAND_LOADER_BEGIN = model_preload.py:13348 (_load_unet physical read), scheduled from modal_app.py:16689
PREWARM_READER_THREADS = 1
READ_SIZE_BYTES = 8388608 (8 MiB)
STOP_JOIN_BEFORE_DEMAND_PROVEN = YES (27 local tests, including bounded timeout/abandon)
MAX_BYTES_SUPPORTED = YES (exact total-byte cap)
MAX_MS_SUPPORTED = YES (wall-time cap)
LOCAL_OVERLAP_PROOF = YES (synthetic slow-reader test overlaps unrelated setup and proves demand starts after guard)
LOCAL_TESTS = 27 passed
PYCOMPILE = PASS
REMOTE_RUNS=0
COMMIT=none
READY_FOR_INTEGRATION = YES
TOP_RISK = authoritative model-name-to-physical-path resolution and insertion before native demand scheduling without colliding with E11
```

Local test command:

```
python -m pytest tests/test_v2_e12_checkpoint_prewarm.py -q
# -> 27 passed
```

## Top Risk

**Authoritative path resolution / insertion before native demand scheduling.**
The module is correct and tested in isolation, but its value depends on
integration resolving model names to physical paths via
`folder_paths.get_full_path_or_raise` and inserting `start()` /
`before_demand_load()` at the audited anchors (`modal_app.py:16675-16689`,
`model_preload.py:13348`) without colliding with E11. That wiring is
deliberately out of scope here.
