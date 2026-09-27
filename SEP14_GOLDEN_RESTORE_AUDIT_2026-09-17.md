# Sep-14 Golden core restore cleanup

Authoritative baseline: `03ce24916958596717220167db496b1215544d09`  
Implementation commit: `41af7fc6b0ce761ec5f1343a0fac68f81e787ff3`  
Worktree: `.slim/worktrees/authoritative-golden-core-sep14`

## WRONG-BASE REFERENCE

The first pass was performed in the main checkout:

`C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal`

It started from later HEAD `390e7d87bec77a995471f8c15f841cf88ed2b8c0` and produced
implementation commits `9fdbae4`, `a36d1f1`, and `711f7cf`, plus the first audit
report and evidence. That work was not transplanted.

Surviving investigative value:

- the distinction between restore pollution, snapshot pollution, and first-request pollution;
- the indirect `/proc` host probe in `set_restore_return_marker`;
- the existence of restore-time folder warming, CLIP probing, and identity diagnostics;
- the test/evidence workflow and invalid remote-attempt paths.

Those findings were rechecked against the authoritative worktree. No final
correctness claim is based solely on the wrong-base source.

## AUTHORITATIVE SEP-14 BEFORE

Frozen Core reference: `Core docs/9-14-26 golden standard.md`, whose runtime
source is `RUN_SOURCE_HEAD=03ce249...` plus its recorded dirty-state patch.
The frozen target is `ModalRuntimeEntrypointV2.run_golden_parallel_stream`,
profile `golden_p1_parallel_io_v2_c0_persistent_fds_preadv_sickness_v2`, Testing
1 / `(default)`, with six separate `--run-count 1` requests in the standard
protocol.

The actual snapshot restore entrypoint on this exact source is:

`comfymodal_runtime/modal_app.py:13167` — `ModalRuntimeEntrypoint.restore()`.

Before the cleanup, the default flag was false at `modal_app.py:3864-3871`, so
restore fell through to the legacy body. The mode split for serial vs parallel
occurred later at request execution (`run_golden_parallel_stream:23321` and
`_run_golden_stream_impl:23358`); restore itself did not branch on `golden_mode`.

### Exact reachable legacy restore operations

| Operation | Exact source | Reachability/resource | Decision |
|---|---|---|---|
| Restore boundary clocks | `modal_app.py:13179-13188` | unconditional; clocks only | Keep |
| Restore CLIP probe | `modal_app.py:13206-13234`, helper `:3437+` | flag-gated; thread, `preadv`, 128 MiB buffers | Suppress on Golden legacy escape |
| Ledger/Gantt/spans | `modal_app.py:13240-13331` | unconditional/gated; in-memory telemetry | Not entered by minimal path |
| Snapshot manifest | `modal_app.py:13362-13397` | `COMFYMODAL_V2_SNAPSHOT_MANIFEST`; filesystem/object traversal | Not entered by minimal path |
| Eviction/lazy snapshot state | `modal_app.py:13408-13440` | legacy lifecycle; possible `/proc`, GC, trim | Not entered by minimal path |
| Host/cgroup/rusage diagnostics | `modal_app.py:13530-13569` | legacy; `/proc`, cgroup, rusage, thread policy | Not entered by minimal path |
| Runtime/bootstrap setup | `modal_app.py:13577-13863`, `runtime_bootstrap.py:2026` | backend construction; conditional GPU/Sage/generation/Volume work | Not entered by minimal path |
| Folder warming | `modal_app.py:13604-13644` | unconditional daemon thread; recursive folder/Volume scans | Suppress on Golden legacy escape |
| Custom-node identity diagnostic | `modal_app.py:13847+` | diagnostic resolver/read and verbose print | Suppress on Golden legacy escape |
| CPU snapshot retarget/preload | `modal_app.py:14042-15032` | conditional on restore plan/snapshot state; scans, futures, workers | Not entered by minimal path; retained for legacy/request lifecycle |
| Restore finalization | `modal_app.py:15046-15421` | IDs, traces, summaries, host probe, marker | Replaced by minimal finalization |

The audit confirmed no custom-node synchronization callback was configured:
`RuntimeBootstrap` receives `sync_custom_nodes=None` and
`read_current_custom_node_identity=None`. Generation guards are local,
fail-closed checks; Volume reload is conditional on mismatch/unknown state.

## AUTHORITATIVE CHANGES

1. Golden profiles (`golden_p1` and `golden_p1_*`) now default to the existing
   minimal restore helper when the explicit flag is absent. An explicit
   non-empty `COMFYMODAL_GOLDEN_MINIMAL_RESTORE=0/false/off/no` remains a
   legacy rollback/debug opt-out; non-Golden profiles remain legacy.
2. Removed the minimal-restore canary and its helper stack from this exact
   source. It had performed rusage/fault/context-switch reads, thread
   enumeration, `/proc/self/task/*/schedstat`, and cgroup memory reads.
3. Minimal restore now performs only mutable-state reset, logical GPU-state
   repair, the existing models-generation guard, identity/return telemetry, and
   fail-closed error handling. The pre-captured snapshot proof is projected but
   not recomputed.
4. Minimal return-marker telemetry opts out of `_capture_host_info()` so it does
   not read `/proc/sys/kernel/random/boot_id`; legacy callers retain the default
   host-info behavior.
5. Golden explicit legacy escape suppresses the CLIP probe, folder warmer, and
   custom-node identity diagnostic. Non-Golden legacy behavior is unchanged.

No profile TOML, flag default, Modal destination, runtime/container setting,
model loader, QD/block-size/transport behavior, sampler, workflow, or Core-doc
file was changed.

## AUTHORITATIVE SEP-14 AFTER

For Golden profiles, the reachable restore graph is now:

```text
restore()                             modal_app.py:13167
  -> boundary clocks                 :13179-13188
  -> _golden_minimal_restore         :12956-13165
       -> reset container-local state
       -> logical GPU-state repair   (no torch.cuda probe/sync/query)
       -> _decide_models_reload      runtime_bootstrap.py:1569
            -> one models_generation.json read + isdir
            -> exact match required; otherwise raise
       -> minimal identity/duration/return telemetry
       -> return
```

There is no restore-time thread/executor, recursive scan, Volume reconciliation,
model/path discovery, preload, transport construction, pinned allocation,
CUDA initialization, stream/event creation, cgroup/rusage canary, or flight
recorder in this default path. The first real model/CUDA work remains request
owned. Explicit legacy opt-out remains available for rollback/debug, but its
Golden-only pollution probes are suppressed.

## SNAPSHOT / FIRST-REQUEST SEPARATION

Snapshot capture was not broadened or rewritten. The Sep-14 capture path remains
startup-owned: imported runtime/custom-node state, bootstrap identities/proofs,
passive quiescence, and the existing Golden content proof. Model/transport
capture candidates remain separate experiment work.

The minimal branch returns before the legacy restore body and before the
post-restore speculative CLIP lane. No removed restore operation was moved into
CLIP/request setup by this implementation.

## REGRESSION GUARD

`tests/test_golden_minimal_restore_validity.py` now covers:

- Golden profile default routing, including `golden_p1_parallel`;
- explicit false legacy override and non-Golden legacy behavior;
- exact minimal allowlist and fail-closed generation guard;
- absence of canary, `/proc`, cgroup, rusage, thread, warming, preload,
  transport, and CUDA-probe calls;
- marker host-probe opt-out with legacy default preservation;
- Golden legacy pollution gates.

## LOCAL EVIDENCE

- Guard: **20 passed**, max test wall 821 ms:
  `C:\Users\parla\AppData\Local\Temp\opencode\sep14_golden_restore_guard_20260917.log`
- Existing minimal restore contract: **6 passed**:
  `C:\Users\parla\AppData\Local\Temp\opencode\sep14_golden_restore_contract_20260917.log`
- Compilation: exit 0:
  `C:\Users\parla\AppData\Local\Temp\opencode\sep14_golden_restore_compile_20260917.log`
- `git diff --check`: passed before commit.
- Authoritative source audit: this worktree and exact line ranges listed above.

No Modal deploy or Modal request was performed from this authoritative lane.

## RESULT

- Authoritative worktree: `.slim/worktrees/authoritative-golden-core-sep14`
- Exact starting commit: `03ce24916958596717220167db496b1215544d09`
- Resulting implementation commit: `41af7fc6b0ce761ec5f1343a0fac68f81e787ff3`
- Changed implementation files:
  - `comfymodal_runtime/modal_app.py`
  - `comfymodal_runtime/model_preload.py`
  - `tests/test_golden_minimal_restore_validity.py`
- Wrong-base investigation remains preserved in the original worktree and its
  prior report/evidence; it was not reset, deleted, or cherry-picked.
