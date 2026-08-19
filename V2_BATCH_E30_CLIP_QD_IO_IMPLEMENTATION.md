# V2 Batch E30 — CLIP Cold I/O: Real QD Source Path and Restore-Contention-Safe Launch

**Agent**: E30 (CLIP COLD-I/O / TRUE-QD owner)
**Status (re-anchor 2026-08-19)**: `E30_CLIP_QD_IO = READY_FOR_V2CTL_REMOTE_GATE`
**Remote acceptance**: `REMOTE_ACCEPTANCE = NOT_YET_PROVEN`

This is the RE-ANCHORED report.  The earlier draft contained contradictory
statements about whether the production speculative CLIP path calls the QD
loader.  Every section below is reconciled against the CURRENT source (HEAD
`0ba7000bd5f3c7ed52e8d9e0facbc0c598eb6997` + uncommitted working tree) and is
labeled with a strict fact taxonomy:

| Label | Meaning |
|---|---|
| `CURRENT SOURCE FACT` | Verified against the working tree at re-anchor time |
| `HISTORICAL INTERMEDIATE STATE` | Was true at some earlier point in the batch; superseded |
| `LOCAL PROOF` | Proven by local tests/mechanics (no remote inference) |
| `REMOTE PROOF` | Proven by an authorized remote run |
| `UNPROVEN` | Not yet demonstrated; must not be claimed |

---

## 1. PHASE 0 — CURRENT SOURCE TRUTH (reconciled)

Captured at re-anchor start (2026-08-19):

```
HEAD      0ba7000bd5f3c7ed52e8d9e0facbc0c598eb6997  (e28: critical-path implementation)
branch    TESTING2
```

No branch / worktree / stash / reset / revert / clean / commit / push performed.
E29/E31/E32 working-tree files are preserved untouched.

### 1.1 The resolved contradiction

The prior report claimed simultaneously:
- (a) `speculative_clip_hydration.py` was modified to select `clip_qd_load` vs `_fastsafe_load` — **true** (working tree, uncommitted);
- (b) "No production module imports `clip_qd_reader`; nothing calls it" — **false at re-anchor** (the seam imports + calls it);
- (c) "integration hunk provided, NOT applied; `_run_speculative_read` currently calls `_fastsafe_load`" — **false at re-anchor**.

(a) is the `CURRENT SOURCE FACT`.  (b)/(c) were `HISTORICAL INTERMEDIATE
STATE` — the seam was applied to the working tree after those lines were
written, and the stale sections were not updated.  The reader module's own
docstring also still said "deliberately NOT applied" — fixed at re-anchor.

### 1.2 The active QD call site (CURRENT SOURCE FACT)

```
CURRENT_HEAD              = 0ba7000bd5f3c7ed52e8d9e0facbc0c598eb6997 (working tree uncommitted)
QD_CALL_SITE_PRESENT      = YES
QD_CALL_SITE_FILE         = comfymodal_runtime/speculative_clip_hydration.py
QD_CALL_SITE_FUNCTION     = _run_speculative_read (lane worker, per-file loop)
QD_GATE                   = COMFYMODAL_V2_CLIP_QD_READER (env_flag, default OFF)
FLAG_OFF_BEHAVIOR         = _wiring._fastsafe_load(path)  — byte-identical E28 path
FLAG_ON_BEHAVIOR          = clip_qd_load(path, trace, launch_policy=resolve_launch_policy())
FALLBACK_BEHAVIOR         = any clip_qd_load failure -> _emit("clip_qd_fallback") + _fastsafe_load(path)
```

Exact current source (working tree, `_run_speculative_read`):

```python
try:
    from .clip_qd_reader import clip_qd_load, clip_qd_reader_enabled
    if clip_qd_reader_enabled():
        from .clip_qd_reader import resolve_launch_policy
        print(f"[v2.clip_qd] entering E30 seam path={os.path.basename(str(path))}", flush=True)
        try:
            sd_raw, loader, fb = clip_qd_load(path, trace=trace, launch_policy=resolve_launch_policy())
        except Exception as _e30_exc:
            _emit("clip_qd_fallback", {...})   # explicit, diagnosable
            print(f"[v2.clip_qd] fallback reason=...", flush=True)
            sd_raw, loader, fb = _wiring._fastsafe_load(path)
        else:
            print(f"[v2.clip_qd] E30 load OK ...", flush=True)
            lane._qd_used = True
    else:
        sd_raw, loader, fb = _wiring._fastsafe_load(path)
except Exception:
    raise   # flag-OFF fastsafe failure propagates; never mislabeled as QD
```

`CURRENT SOURCE FACT`: the seam is ONLY in the speculative lane
(`_run_speculative_read`).  The demand-time hydrator
(`clip_fast_hydration_wiring._try_fast_hydrate`) does NOT call
`clip_qd_load`; its per-file read stays `_fastsafe_load`.  So with the flag
ON, a request whose speculative lane succeeds uses the QD reader; a lane
miss/failure falls back to the fastsafe demand read.  With the flag OFF,
both paths are byte-identical to E28.

### 1.3 Re-anchor fix applied to the seam

The pre-re-anchor seam wrapped BOTH branches in one `try/except`, so a
flag-OFF fastsafe failure was caught and mislabeled as a `clip_qd_fallback`
event (observed in the e25 regression suite).  Fixed at re-anchor: the
`except` now wraps only the `clip_qd_load` call; a flag-OFF fastsafe failure
propagates and never emits the E30 fallback event.  Added `lane._qd_used`
so the take record carries `qd_used: bool` — a QD-entered run is provable
from the record alone, and a non-QD run is provably not mislabeled.

---

## 2. Files changed (E30 ownership)

| File | Change | Status at re-anchor |
|---|---|---|
| `comfymodal_runtime/clip_qd_reader.py` | NEW genuine-QD reader (CPU + GPU), launch-policy API, E30 telemetry, `clip_qd_load` seam, E29-ledger ingestion | CURRENT SOURCE FACT |
| `comfymodal_runtime/speculative_clip_hydration.py` | E30 seam in `_run_speculative_read` (flag-gated), `qd_used` record, mislabel fix | CURRENT SOURCE FACT (uncommitted) |
| `comfymodal_runtime/clip_fast_hydration_wiring.py` | Demand-time `clip_qd_take`/`bind`/`owner_retained` events when `record.qd_used` | CURRENT SOURCE FACT (re-anchor) |
| `comfymodal_runtime/modal_app.py` | `_runtime_env` passthrough for 5 E30 flags + `run_env_probe` tuple | CURRENT SOURCE FACT (pre-existing, preserved) |
| `tests/test_e30_clip_qd_io.py` | 17 offline tests + re-anchor additions (QD1/2/4 matrix, mislabel, ledger, staging, alignment) | LOCAL PROOF |
| `tools/bench_e30_clip_qd.py`, `tools/e30_env_probe.py` | local benchmark + container env probe | LOCAL PROOF |
| `_e30_deploy_wrapper.bat` | LEGACY — marked DEPRECATED at re-anchor; not part of the future workflow | HISTORICAL INTERMEDIATE STATE |
| `config/v2/flag_registry.toml` | 5 E30 flags registered (metadata, not whitelist) | CURRENT SOURCE FACT (re-anchor) |
| `config/v2/profiles/e30-clip-qd.toml` | Fixed: real flag names + expected SHA | CURRENT SOURCE FACT (re-anchor) |
| `tests/test_v2ctl_config.py`, `tests/test_v2ctl_profiles.py` | Updated to the registered E30 flags | LOCAL PROOF |

E29/E31 orchestration files (`critical_path_ledger.py`, `gantt_canonical.py`,
`clip_fp32_cast_once.py`, `runtime_bootstrap.py`, `runtime_executor.py`,
`model_preload.py`, `benchmark_v2_direct.py`) are E29/E31 ownership —
preserved, not edited by E30.

---

## 3. Source / API audit (CURRENT SOURCE FACT)

### 3.1 E28 production CLIP loader path (exact call graph, re-anchor)

```
frozen manifest (attached at snapshot construction)
  -> speculative lane start (restore-time / plan-receipt reconcile)
  -> _run_speculative_read (speculative_clip_hydration.py)
       -> torch.cuda.is_initialized() bounded wait (CUDA readiness)
       -> stat/size freshness check vs frozen manifest
       -> FLAG? clip_qd_load(path, launch_policy=...)   <-- E30 seam (flag ON)
             -> read_file_qd_gpu: tensor-aligned queued pread (qd threads,
                disjoint ranges) -> bounded pinned staging (qd x block)
                -> async H2D -> ONE contiguous GPU buffer -> zero-copy views
             -> QdGpuOwner (loader facade) returned as (sd, loader, fb)
          |  else _wiring._fastsafe_load(path)           <-- E28 unchanged (flag OFF)
       -> _blob_free + _select_pipeline/_apply_pipeline (frozen manifest pipeline)
       -> optional FP32 cast-once (E28 Target C, E31 ownership)
  -> lane.owners/per_file_sds published; UNET release fired
  -> demand: take_speculative_read -> manifest verify -> hydrate_clip_bind
       (assign=True via Comfy's load_sd dispatch) -> owner_attach -> sync
```

### 3.2 fastsafetensors internals — thread count is NOT queue depth

`CURRENT SOURCE FACT` (from the installed 0.3.x source, unchanged since the
first draft): `nogds_file_reader.submit_read` (ext.cpp) round-robins
`thread_id % max_threads` and JOINS the previous thread in a slot before
launching the next.  `max_threads` = number of single-flight slots, NOT
queue depth; reads in a slot are fully serialized.  E30's QD reader
implements the E27 mechanism: `qd` independent worker threads, each with
its own bounded buffer, reading disjoint static ranges via `os.preadv`
(32 MiB syscalls) with a short-read retry loop.

---

## 4. E27 QD4 mechanism — exact reconstruction

`CURRENT SOURCE FACT` (E27 §5.5 table, unchanged):

| QD | block | wall ms | GB/s | CPU ms |
|---|---|---|---|---|
| QD1 cold | 32 MiB | 1047.3 | 7.68 | — |
| QD2 | 32 MiB | 403.0 | 19.96 | 70 |
| **QD4** | **32 MiB** | **191.4** | **42.03** | **30** |
| QD8 | 64 MiB | 178.8 | 45.00 | 220 |
| QD16 | 128 MiB | 399.1 | 20.16 | 1010 |

Adopted configuration: **QD4 / 32 MiB** (42 GB/s with only 30 ms CPU).

`UNPROVEN` (re-anchor): whether the CURRENT implementation reproduces these
exact numbers remotely — the previous remote runs did NOT capture
per-event/artifact proof (see §7).

---

## 5. True-QD design (Phase 1/2 re-audit)

`CURRENT SOURCE FACT`: the implemented reader matches the E27 mechanism:

- `qd` worker threads, each with its OWN buffer (`torch.empty(block_bytes,
  pin_memory=True)`, plain fallback) — 4 independent readers, 4 independent
  bounded buffers.
- STATIC disjoint range partition: `build_block_items` plans tensor-aligned
  blocks from the real safetensors header; `partition_coverage` proves no
  gap/overlap/missing tail.  Workers pull items from a shared queue (a
  bounded backlog, never a full-file host copy).
- 32 MiB block default (env-overridable `COMFYMODAL_V2_CLIP_QD_BLOCK_MIB`).
- Multiple simultaneous outstanding reads: `_ReaderState.outstanding` +
  `observed_max_outstanding` prove the true queue depth.
- Bounded staging = `qd x block_bytes` (e.g. 4×32 MiB = 128 MiB); GPU holds
  ONE contiguous destination buffer (`total_data_bytes`); tensors are
  zero-copy views over it (no second GPU copy).
- `read_file_qd` (CPU-only) and `read_file_qd_gpu` (full pipeline) both
  behind the same default-OFF gate.

The E28 fastsafetensors path is NOT equivalent to true QD — the C++ join
serialization makes it impossible without forking the compiled dependency.
This architectural conclusion still holds (`CURRENT SOURCE FACT`).

---

## 6. Queue-depth proof (LOCAL PROOF)

`_ReaderState` counts pulls vs completions under a lock:

- `configured_qd` (env, default 4), `observed_max_outstanding` (running max
  of outstanding pulls), `submit_count`, `completion_count`,
  `queue_backlog_max`, `first_completion_latency_ms`,
  `tail_completion_latency_ms`, per-block `{off, len, wall_ms, gbps,
  error}`, `steady_state_gbps`, `thread_cpu_ms`, `process_cpu_ms`,
  `per_read_errors`, `buffer_pool_wait_ms`.

`LOCAL PROOF` (Windows lseek-mode mechanics — NOT a Modal conclusion):

```
QD1: wall=203.7 ms gbps=2.64 obs_max=1 submit=32 done=32 errors=0
QD2: wall=148.9 ms gbps=3.61 obs_max=2 submit=32 done=32 errors=0
QD4: wall=104.0 ms gbps=5.16 obs_max=4 submit=32 done=32 errors=0
QD8: wall=105.3 ms gbps=5.10 obs_max=8 submit=32 done=32 errors=0
GPU pipeline (QD4/32): wall=129.2 ms h2d_dev=128.6 ms obs_max=4 cuda_delta=537 MB
```

Re-anchor tests add a QD1/QD2/QD4 mechanics matrix with a slow-read patch
proving `observed_max_outstanding == configured QD` at every depth, and a
bounded-staging test proving `pinned == qd x block` < file bytes on a file
larger than the staging budget.  `REMOTE PROOF` of `observed_max_outstanding
== 4` on a cold Modal volume: **NOT YET PROVEN**.

---

## 7. Previous remote runs — what they do NOT prove

The pre-re-anchor report's §16 listed 4 authorized deploys/requests.  After
reconciliation:

- `HISTORICAL INTERMEDIATE STATE`: the runs happened (deploys `e0443f3e…`,
  `c42eb4cb…`, `a9908bdc…`, `33081c68…`; requests STATUS OK, SHA matched).
- They do NOT prove `observed_max_outstanding == 4`, cold source < 800 ms,
  or device-ready wall: the full-trace downloader/handoff failed and the
  per-event/artifact capture never materialized.  The 9.3 s → 3.5 s CLIP
  encode difference between runs is `HISTORICAL INTERMEDIATE STATE`,
  non-diagnostic contextual evidence at most — NOT proof of QD (it is not
  attributable without the trace/artifact).
- `REMOTE PROOF`: container env carried the E30 gates (run_env_probe) and
  the output SHA matched `20b10e1f…e5260`.  That is all.

`UNPROVEN`: every acceptance metric of the future gate.

---

## 8. Default-OFF proof (LOCAL PROOF)

- `COMFYMODAL_V2_CLIP_QD_READER` parsed via `env_flag` → False when unset.
- `read_file_qd` / `read_file_qd_gpu` return `{"status": "disabled"}`
  before opening the file, importing torch paths, or spawning threads
  (tests: thread count unchanged, missing file not touched).
- Re-anchor fix: a flag-OFF fastsafe failure in the seam now propagates
  without emitting `clip_qd_fallback` — a non-QD run is provably not
  mislabeled (new test).
- No import-time CUDA touch, no changed source launch timing with the flag
  OFF.

---

## 9. Speculative ownership contract (LOCAL PROOF)

`tests/test_e30_clip_qd_io.py::SpeculativeOwnershipContractTests` (CUDA):

- one source read only; second take after a successful take returns None;
- exact manifest verification (sorted key-set, per-key shape/dtype/byte-size)
  before bind; mismatch → owners released, normal read loop runs;
- take-on-match; bind via `hydrate_clip_bind(assign=True)`; zero-copy
  storage proof (file-view data_ptr == bound param data_ptr);
- owner retained (`owner_attach`, `fastsafe_owner_present` after bind);
- cancellation/lifetime: `close_speculative_clip_lane` idempotent, no
  dangling lane, no stale pointer (owner close is the only release path);
- `record.qd_used` proof + source-side and demand-side
  `clip_qd_take`/`bind`/`owner_retained` events (trace + E29 ledger).

---

## 10. Launch policy (Phase 5) — separable, NOT wired

`validate_launch_policy(policy)` accepts exactly:

```
restore_earliest | after_restore_sensitive_phase | after_cuda_restore | method_entry
```

The reader never chooses a policy; the caller passes it (env default
`restore_earliest` = current behavior) and it is recorded in every
`clip_qd_source_submit_start` event.  The future remote A/B (ARM A:
restore-time start; ARM B: `after_cuda_restore`) is a caller-side decision.
E29 measures restore contention; E30 exposes clean launch seams and
telemetry only.  `UNPROVEN`: which policy is globally optimal.

---

## 11. E30 telemetry / E29 ledger integration (CURRENT SOURCE FACT)

E29 owns the canonical timeline; E30 only STAMPS its boundary events on the
shared monotonic axis via `critical_path_ledger.record_event` (never a
competing engine).  Re-anchor added `clip_qd_reader.ledger_event` and wired
it into every boundary:

```
clip_qd_source_submit_start / clip_qd_source_submit_end
clip_qd_read_begin / clip_qd_read_end            (aggregate, not per-block)
clip_qd_source_first_completion / clip_qd_source_last_completion
clip_qd_buffer_wait                              (per-slot event wait > 1 ms)
clip_qd_copy_to_device_start / clip_qd_copy_to_device_end
clip_qd_device_ready
clip_qd_owner_created
clip_qd_spec_record_publish
clip_qd_take / clip_qd_bind / clip_qd_owner_retained
```

`clip_qd_load` emits source-side take/bind/owner-retained with
`source_side=True`; the demand-time take/bind/owner-retained events fire in
`clip_fast_hydration_wiring._try_fast_hydrate` when `record.qd_used`, so the
end-to-end ownership chain is provable.  Per-block detail stays in
`stats["blocks"]` (structured) + optional artifact
(`COMFYMODAL_V2_CLIP_QD_ARTIFACT`); console emits one compact JSON summary
line per read.

---

## 12. v2ctl integration (Phase 3/4) — CURRENT SOURCE FACT

### 12.1 Flag lifecycle (registered in `config/v2/flag_registry.toml`)

| Flag | Type | Default | Consumed at | Change requires |
|---|---|---|---|---|
| `COMFYMODAL_V2_CLIP_QD_READER` | bool | 0 | restore (lane start) | deploy |
| `COMFYMODAL_V2_CLIP_QD_QD` | int 1..32 | 4 | restore (reader start) | deploy |
| `COMFYMODAL_V2_CLIP_QD_BLOCK_MIB` | int 1..4096 | 32 | restore (reader start) | deploy |
| `COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY` | enum (4 policies) | restore_earliest | restore (reader start) | deploy |
| `COMFYMODAL_V2_CLIP_QD_ARTIFACT` | path | "" | restore (reader end) | deploy |

Registry is metadata, NOT a whitelist — unknown flags still flow through as
unregistered.  `CURRENT SOURCE FACT`: the flags are deploy-baked via
`modal_app._runtime_env` + echoed in `run_env_probe`; they are NOT
request-carried (the reader consumes them at restore-time lane start, before
the request-time allowlist applies — a request-carried override would be
inconsistent, so none was added).

### 12.2 Profile

`config/v2/profiles/e30-clip-qd.toml` (re-anchor fix): the previous profile
set a stale `COMFYMODAL_V2_CLIP_QD_IO` key that nothing consumed.  It now
sets the 5 real flags (`READER=1, QD=4, BLOCK_MIB=32,
LAUNCH_POLICY=restore_earliest`), keeps `CLIP_FAST_HYDRATION=1` +
`CLIP_COLD_FORENSICS=1`, and pins the expected output SHA
`20b10e1f…e5260`.  Future remote command: `python tools/v2ctl.py gate
--profile e30-clip-qd ...`.

### 12.3 Deploy wrapper

`_e30_deploy_wrapper.bat` is LEGACY experimental scaffolding — marked
DEPRECATED at re-anchor, kept only because concurrent E29/E32 work may still
reference it, and NOT part of the future workflow.  No new experiment-
specific deploy wrappers will be created.

---

## 13. Exact tests run (re-anchor)

```
tests/test_e30_clip_qd_io.py                        (gate-off, mislabel fix,
                                                     QD1/2/4 matrix, parity,
                                                     alignment fallback,
                                                     bounded staging, ledger,
                                                     ownership contract)
tests/test_v2_clip_fast_hydration_production.py     (regression)
tests/test_e28_critical_path.py                     (regression)
tests/test_v2_e25_pre_graph_and_speculative.py      (regression; no QD
                                                     mislabel after fix)
tests/test_e27_followup_probe.py                    (regression)
tests/test_e27_forensics.py                         (regression)
tests/test_e31_clip_forward_fp32.py                 (E31 regression)
tests/test_v2ctl_config.py / test_v2ctl_profiles.py (v2ctl integration)
Combined: 171 passed, 1 skipped
py_compile: all touched files OK
git diff --check: clean
```

Note (pre-existing, E29 ownership): `tests/test_e29_critical_path_ledger.py`
has 4 failures (`RestorePhasePreservationTest` x2, `TraceSpanBridgeTest` x2)
in the current working tree — the ledger module's `begin_restore`/`begin_span`
routing does not match E29's tests.  These fail in isolation, were NOT caused
by E30 changes, and are E29's files to fix.

---

## 14. Remaining risks (explicit)

- Local ≠ remote: Windows lseek-mode numbers are mechanics validation only;
  the remote gate is the authoritative measurement.
- H2D ceiling: if PCIe/GPU copy bounds the pipeline, combined gains shrink;
  mitigated by async per-slot H2D + single contiguous destination.
- Restore contention: QD4 uses ~30 ms CPU / 191 ms wall (E27); the A/B
  exists to prove the source read does not stretch restore.
- fastsafetensors fork risk: none — E30 does not modify the installed C++.
- Region/page-cache variance: cold-run acceptance requires the fresh-
  instance proof (Fresh = YES).
- Alignment fallback: tensors not element-aligned relative to the GPU
  buffer take the re-read fallback — counted in `stats["fallback"]`; local
  parity test added; expected 0 on standard writers.

---

## 15. Success criteria — final verdict

- [x] Current source/report contradictions resolved (PHASE 0, §1)
- [x] Exact active QD call site proven (§1.2)
- [x] True QD mechanics (QD4, disjoint ranges, bounded staging, 32 MiB
      blocks) locally proven (§5, §6)
- [x] Flag OFF leaves production unchanged; no duplicate speculative read;
      bounded staging proven; exact safetensors parity proven (LOCAL PROOF)
- [x] Ownership/lifetime proven (LOCAL PROOF, §9)
- [x] v2ctl integration metadata prepared (registry + profile, §12)
- [x] Custom E30 deploy wrapper deprecated, out of the workflow (§12.3)
- [x] E29 can consume E30 timing events (ledger stamps, §11)
- [ ] A future v2ctl cold gate proves actual QD=4, observed outstanding=4,
      cold source wall, device-ready wall, exactness — **UNPROVEN**

**`E30_CLIP_QD_IO = READY_FOR_V2CTL_REMOTE_GATE`**
**`REMOTE_ACCEPTANCE = NOT_YET_PROVEN`**

---

## 16. Future remote gate (prepare only — no deploys until user permission)

Once E29 tracing is trustworthy, E32/v2ctl works, and the user grants
permission, run ONE proper cold gate:

```
python tools/v2ctl.py gate --profile e30-clip-qd ...
```

Acceptance (all must hold on a FRESH container):

- `Fresh = YES` (container_session_id / restore_count proof)
- QD path entered: `configured_qd = 4`, `observed_max_outstanding = 4`
- source bytes ≈ 8.045 GB; cold source wall < 800 ms (stretch < 500 ms)
- source→GPU-ready measured (E29 ledger events present); no duplicate read;
  speculative take succeeds; manifest exact; bound tensors exact
- exact output SHA `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`
- restore does not regress unexpectedly (E29 ledger)

If structurally invalid: STOP (no second confirmation run).  Only if valid:
one confirmation or the restore-launch A/B as justified.

`HISTORICAL INTERMEDIATE STATE` (do not reuse): `_e30_deploy_wrapper.bat`
and the old 4-deploy protocol.
