# Golden Parallel Minimal Restore — Implementation Report

**Date:** 2026-09-11
**Status:** locally complete, committed on an isolated worktree. **No deploy, no remote run, no Volume mutation.**

---

## 1. Worktree isolation

| Item | Value |
|---|---|
| Worktree path | `C:\Users\parla\.config\superpowers\worktrees\comfyui-modal\golden-minimal-restore` |
| Branch | `exp/golden-minimal-restore` |
| Starting base SHA | `c3aceb348b3687d3a9b87ee5fe1c3781040d2488` (committed tip of `TESTING2`) |
| Isolated from | main worktree `...\custom_nodes\comfyui-modal` on `TESTING2` |

The loader-process lane is active **in the main worktree** (`TESTING2`), which has uncommitted edits to
`comfymodal_runtime/golden_loader_process.py`, `comfymodal_runtime/golden_parallel.py`,
`comfymodal_runtime/modal_app.py`, and `config/v2/flag_registry.toml`, plus untracked evidence/audit docs.
A new worktree was created from the **committed** base `c3aceb3`; the loader lane's worktree, branch,
uncommitted state, deployment, and evidence were **not** read-modify-written, not cherry-picked, and not deployed.
No Modal command, remote request, publisher, or Volume mutation was performed.

---

## 2. Implementation

| Item | Value |
|---|---|
| Flag | `COMFYMODAL_GOLDEN_MINIMAL_RESTORE` |
| Default | `0` / `False` (legacy selected when unset) |
| Routing seam | `comfymodal_runtime/modal_app.py:12860` (early `if` inside `restore()`, after the resume-boundary timestamps, before any legacy probe/observability/ledger work) |

### Files changed (commit 1)

| File | Change |
|---|---|
| `comfymodal_runtime/modal_app.py` | accessor `_golden_minimal_restore_enabled()` (~3550); 4 helper methods (12596–12836); routing seam (12860–12876); flag forwarding in the class-env bridge (5415–5416) |
| `comfymodal_runtime/config_authority.py:137` | `_spec("COMFYMODAL_GOLDEN_MINIMAL_RESTORE", "bool", False, EXECUTION_POLICY, ...)` |
| `config/v2/flag_registry.toml:226-232` | `[[flag]]` entry, `default="0"`, `consumed_at="restore"`, `change_requires="deploy"` |

### Functions added (all on `ModalRuntimeEntrypoint`)

- `_golden_minimal_reset_container_state() -> str`
- `_golden_minimal_restore_logical_gpu_state() -> None`
- `_golden_minimal_assert_models_generation() -> dict`
- `_golden_minimal_restore(...) -> dict` — the minimal entry called by the seam.

The legacy 2,293-line `restore()` body is **unchanged**; only an early-return branch was inserted at its top.

---

## 3. Minimal restore call graph (flag ON)

AST-built reachable tree (static proof, `modal_app.py`):

```
restore()                       # @modal.enter(snap=False) at modal_app.py:24040
  └─ _golden_minimal_restore_enabled()          env_flag(..., default=False)
      └─ _golden_minimal_restore()
          ├─ _golden_minimal_reset_container_state()        [state reset]
          ├─ _golden_minimal_restore_logical_gpu_state()    [logical GPU repair]
          ├─ _golden_minimal_assert_models_generation()     [models guard]
          ├─ _mark()                                        [minimal telemetry]
          ├─ uuid / time / os / print / dict.update         [minimal telemetry/identity]
          ├─ set_model_load_identity()                      [restore identity]
          └─ set_restore_return_marker()                    [resume→FRR boundary]
```

Nothing else executes before READY. `set_restore_return_marker` internally captures host/pid metadata
(the standard existing boundary marker); no hardware fingerprinting is performed.

---

## 4. What is intentionally absent

Static reachability proof (see §7) found **NONE** of the following reachable from `_golden_minimal_restore`:

custom-node sync/publish · runtime-state manifest verification · folder warming · CUDA `synchronize` ·
`get_device_name` · `get_total_memory` · `psutil.virtual_memory` · `memory_stats`/`mem_get_info` ·
CriticalPathLedger · Gantt telemetry · restore spans · snapshot-manifest capture · CPU-snapshot activation ·
CacheDiT/RES4LYF restore prep (only the two guard dicts are `.clear()`ed) · preload bridge / UNET defer ·
speculative CLIP lane · clean-lane · teardown diagnostics · `_initialize_cuda_context` ·
`_restore_in_process_gpu_state` · `Volume.reload()`.

These are separated from the legacy path by the early return, not moved into another called function.

---

## 5. Logical GPU state

### Retained (necessary)

| Mutation | Reason |
|---|---|
| `comfy.cli_args.args.cpu = False` | snapshot was built under `force_cpu_during_snapshot`; placement would stay CPU |
| `comfy.model_management.cpu_state = CPUState.GPU` | backend captured `cpu_state=CPU`; drives device selection |
| `comfy.model_management.DISABLE_SMART_MEMORY = False` | restores normal placement policy |
| `comfy.model_management.vram_state = VRAMState.HIGH_VRAM` | snapshot captured CPU/low state; needed for GPU model placement |

### Removed from the old helper (`_restore_in_process_gpu_state`, `comfyapp.py:20197`)

`torch.cuda.is_available()`, `torch.cuda.current_device()`, `get_torch_device()`,
`apply_frozen_total_vram_or_none()`, `get_total_memory()`, `psutil.virtual_memory()`,
`total_vram`/`total_ram` assignment, `_gpu_restore_deferred`/`_gpu_restore_status` writes.

Deliberate consequence (to be measured by the A/B): `total_vram`/`total_ram` may remain at snapshot
values until the first genuine GPU use; if a snapshotted `_gpu_restore_deferred=True` is present,
`_ensure_gpu_ready_for_request` will perform the deferred repair at first request. Either way the cost is
observable rather than paid pre-readiness.

---

## 6. Models guard

```python
decision = self.bootstrap._decide_models_reload()          # runtime_bootstrap.py:1552
if str(decision.get("decision","")) != "skipped_generation_match":
    raise RuntimeError("golden_minimal_restore_models_generation_check_failed:" + reason)
```

`_decide_models_reload` is the **existing** guard: it compares the mounted `models_generation.json`
against the snapshot baseline (`bootstrap.state.snapshot_models_generation`, captured at startup at
`runtime_bootstrap.py:1532`). On the normal match path it performs **one small JSON read + one `isdir`** and
returns `skipped_generation_match` (no Volume RPC, no tree walk, no hashing, no repair).

Fail-closed: empty baseline, unreadable record, unknown reason, or a proven mismatch all raise; the minimal
path never auto-reloads and never repairs. If a Golden deployment lacks the baseline, the treatment fails
explicitly — which is the intended evidence, not a silent fallback.

---

## 6.1 First-request GPU-repair trace (`_gpu_restore_deferred`) — no change required

**Question:** does the minimal path cause the first Golden Parallel request to invoke
`_restore_in_process_gpu_state()`, `_initialize_cuda_context()`, `get_total_memory()`, or any equivalent
legacy GPU-repair?

**Verdict: No. The deferred request-side path is not reached; therefore no code change was made.**

Trace from snapshot capture to first request (line numbers in this worktree):

**Snapshot capture (`snap=True`)**
- `modal_app.py:11362` `startup()` → `self.bootstrap.startup(snapshot=True)`. `RuntimeBootstrap.startup`
  (`runtime_bootstrap.py:1307+`) runs models/runtime-state/custom-node/baseline/backend/sage steps and
  **never** calls the `restore_gpu_state` / `initialize_cuda` callbacks — those are invoked only inside
  `RuntimeBootstrap.restore()` (`runtime_bootstrap.py:2068-2119`).
- `_force_cpu_during_snapshot` (`comfyapp.py:17530`) only monkey-patches `torch.cuda.is_available` /
  `current_device` and import guards; it does not touch `_gpu_restore_deferred`.
- The only writer that makes the flag truthy is `_mark_gpu_restore_deferred` (`comfyapp.py:20043-20045`).
  Its callers are `_refresh_gpu_snapshot_memory` (called only from `comfyapp.restore:21122`),
  `_restore_in_process_gpu_state`, `_ensure_gpu_ready_for_request`, and `comfyapp.restore`. None executes
  during `snap=True` startup in the modal_app runtime.
- There is no `__init__` default for the attribute ⇒ it is **absent** in the snapshot.

**Minimal restore (flag ON)**
- The seam (`modal_app.py:12860`) returns before `self.bootstrap.restore()` (`modal_app.py:13476`), so the
  `restore_gpu_state` / `initialize_cuda` callbacks (`modal_app.py:10682/10685`) never fire.
- The minimal helpers never read or write `_gpu_restore_deferred` / `_gpu_restore_status`.

**First Golden Parallel request**
- `modal_app.py:23405` calls `legacy_api._ensure_gpu_ready_for_request()`.
- `_ensure_gpu_ready_for_request` (`comfyapp.py:20127`) returns immediately at `:20131-20132` because
  `getattr(self, "_gpu_restore_deferred", False)` is falsy.
- Consequently `_restore_in_process_gpu_state()` (`comfyapp.py:20135`) and the following
  `_initialize_cuda_context()` (`:20142`) are **not** called, and `get_total_memory()` (only reachable
  inside those and `_refresh_gpu_snapshot_memory`) is **not** called.

**Reader audit / equivalents**
- Every runtime read of `_gpu_restore_deferred` uses `getattr(..., False)` (`comfyapp.py:20131, 21146,
  21221`); absence is safely falsy.
- No other call to `_restore_in_process_gpu_state`, `_initialize_cuda_context`, or `_warmup_cuda` exists on
  the Golden Parallel request path.
- No `_mark_gpu_restore_deferred` / `_refresh_gpu_snapshot_memory` / `_warmup_cuda` reference exists in
  `modal_app.py`.

This confirms the intended treatment: CUDA first-touch happens **naturally on the first genuine model/GPU
operation** (e.g. ComfyUI's `get_torch_device()` during model work), not in restore and not in request setup.

**Defensive note (not implemented, per instruction):** the minimal path relies on the snapshot not carrying
`_gpu_restore_deferred=True`, which holds for the CPU-snapshot Golden deploy (attribute absent) and for a
warm-container second restore under this same path (still falsy). If a future snapshot shape ever carried it
truthy, the minimal correction would be to set, in `_golden_minimal_restore_logical_gpu_state`,
`legacy_api._gpu_restore_deferred = False` and `legacy_api._gpu_restore_status = {"status":"ok","cuda_available":1}`.
This was **not** added because the deferred path is not invoked and eager CUDA initialization must remain out
of the minimal path.

---

## 7. Local validation

All read-only / local; no deploy.

| Check | Result |
|---|---|
| `python -m py_compile comfymodal_runtime/modal_app.py comfymodal_runtime/config_authority.py` | OK |
| TOML parse `config/v2/flag_registry.toml` | 136 flags; `COMFYMODAL_GOLDEN_MINIMAL_RESTORE` present; default `0` |
| `env_flag` semantics (unset / `1` / `0`) | `False / True / False` → legacy selected when unset |
| AST static proof (`gmr_static_proof.py`) | RESULT=PASS — forbidden reachable tokens: NONE; seam precedes the CLIP probe; guard/gpu contract checks pass |
| `pytest tests/test_minimal_restore.py` | 6 passed |
| `pytest tests/test_v2ctl_registry.py tests/test_v2ctl_config.py tests/test_e40_canonical_authority.py tests/test_v2ctl_fingerprints.py` | 170 passed |

**Genuine product-contract failures:** none.
**Historical/structural tests that assert legacy restore internals:** none were run or broken by this change
(the legacy `restore()` body is untouched).

**After the §6.1 trace (no code change):** the same checks were re-run on the unchanged tree — `py_compile`
OK, AST static proof PASS (forbidden reachable tokens NONE), `tests/test_minimal_restore.py` 6 passed.

Independent review: `@oracle` found **no BLOCKER**. Its two hardening notes (silently swallowed
return marker; silently swallowed legacy-barrier reset) were adopted before commit: the return marker is now
unguarded (matching the legacy call site), and the reset returns a `legacy_api_reset` status recorded in
telemetry.

---

## 8. Concurrent-lane reconciliation risks (not resolved here)

Expected to conflict when the loader-process lane's final commits are reconciled into this branch:

| File / region | Overlap |
|---|---|
| `comfymodal_runtime/modal_app.py` | accessor region (~3546), class-env bridge (~5412-5416, adjacent to the loader-process forwarding block), and the top of `restore()` (~12838-12876) |
| `config/v2/flag_registry.toml` | loader-process `[[flag]]` entry (~216-223) is immediately adjacent to the new entry (~226-232) |
| `comfymodal_runtime/config_authority.py` | loader-process adds no `_spec`; new `_spec` sits next to `COMFYMODAL_MINIMAL_RESTORE` (~137) |

Not touched by this lane: `golden_loader_process.py`, `golden_parallel.py`, and any loader-process logic.
Both lanes edit `modal_app.py`; reconcile deliberately, preserving the early-return seam and the loader lane's
`restore()`/lifecycle changes.

---

## 9. Commits

| # | SHA | Summary |
|---|---|---|
| 1 | `789e93957386f29909712954bde29bffdda55487` | `feat: default-OFF Golden Parallel minimal restore path` |
| 2 | `3014eb6192ffa456ec1ab563c640f3cc5c040305` | `docs: Golden minimal restore implementation report` |
| 3 | *(this trace-addendum commit)* | `docs: prove deferred GPU-repair path is not invoked under minimal restore` |

Final HEAD after commit 2 is recorded in the handoff message.

---

## 10. Remote next step (do NOT execute here)

After the loader lane finishes, commits, and its work is reconciled into this branch:

- **CONTROL:** deploy with `COMFYMODAL_GOLDEN_MINIMAL_RESTORE` unset (legacy restore).
- **TREATMENT:** set `COMFYMODAL_GOLDEN_MINIMAL_RESTORE=1` in the Golden Parallel deploy environment via the
  same config-owned mechanism that already carries `COMFYMODAL_GOLDEN_LOADER_PROCESS` (the class-env bridge
  forwards it to the container; the runtime accessor defaults to OFF). Rebuild/redeploy through the canonical
  v2ctl path; do **not** use raw `modal deploy`.
- **Confirmation:** treatment logs must contain `[v2.golden_minimal_restore] status=ok ...`; control must not.
- Same Golden Parallel workflow/config for both arms. Measure `Python/resume → restore entry`,
  `restore total`, `logical GPU repair`, `models check`, first CUDA cost, CLIP load/forward, UNET load,
  sampling, VAE load, decode, and `Python/resume → FIRST_RESULT_READY`. A faster restore that only shifts the
  same latency into CLIP/UNET is **not** a win.

---

## Auditability

- Worktree: `C:\Users\parla\.config\superpowers\worktrees\comfyui-modal\golden-minimal-restore`
- Branch: `exp/golden-minimal-restore`
- Starting HEAD: `c3aceb348b3687d3a9b87ee5fe1c3781040d2488`
- Commit 1 HEAD: `789e93957386f29909712954bde29bffdda55487`
- Report path: `GOLDEN_MINIMAL_RESTORE_IMPLEMENTATION_2026-09-11.md` (this file)
- Changed files: `comfymodal_runtime/modal_app.py`, `comfymodal_runtime/config_authority.py`,
  `config/v2/flag_registry.toml`
- Local validation artifact: `%LOCALAPPDATA%\Temp\opencode\gmr_static_proof.py` (outside the repo; not committed)
