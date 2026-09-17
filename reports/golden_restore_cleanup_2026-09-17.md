# Golden snapshot restore cleanup audit

Date: 2026-09-17  
Implementation commit: `9fdbae45b7d6dbccaeda9009d0c93ff9f36f9f19`  
App requested for remote validation: `golden-restore-minimal-20260917`

## BEFORE

The real post-snapshot Python entrypoint was `ModalRuntimeEntrypoint.restore()`
at `comfymodal_runtime/modal_app.py:12562`. The Golden Serial profile did not
select the separate minimal helper by default: `_golden_minimal_restore_enabled`
at `modal_app.py:3550-3557` defaulted false.

### Legacy restore call graph actually reachable before this change

| Operation | Location | Condition | Resource/work class | Correctness | Disposition |
|---|---|---|---|---|---|
| Resume and restore timing stamps | `modal_app.py:12579-12583` | Unconditional | Clocks only | Defines the restore boundary | Kept |
| Restore CLIP QD2 probe source resolution and thread | `modal_app.py:12601-12629` | `COMFYMODAL_RESTORE_CLIP_READ_PROBE` | File `stat/open/preadv`, two worker buffers, non-daemon thread | Diagnostic only | Removed from Golden Serial via gate |
| Observability/ledger/Gantt setup | `modal_app.py:12635-12726` | Mostly unconditional; diagnostics gated | In-memory trace/ledger; optional manifest | Timing/evidence only | Not reached by minimal path |
| Eviction boundary | `modal_app.py:12820-12835`, helper `:9546` | Unconditional legacy path | `/proc` memory probe; optional idle/sleep, GC, `malloc_trim` | Required only for legacy retained-model release | Not reached by minimal path |
| Torch thread-limit enforcement | `modal_app.py:13040-13048` | Unconditional legacy path | Torch thread calls and `/proc/self/task` | Legacy lifecycle policy | Not reached by minimal path |
| Folder warming thread | `modal_app.py:13000-13035` | Unconditional before change | Recursive registered-folder filesystem/Volume scans on daemon thread | Advisory only; could overlap first request | Removed from Golden Serial via gate |
| Runtime configuration and bootstrap | `modal_app.py:12981`, `:13200`; `runtime_bootstrap.py:1984-2624` | Unconditional legacy path | Backend construction; conditional GPU repair, Sage fallback, generation guards, Volume reloads | Legacy correctness | Not reached by minimal path |
| Custom-node identity diagnostic | `modal_app.py:13235-13258` | Unconditional before change | `_resolve_custom_nodes_generation`; possible Volume/filesystem work; verbose print | Diagnostic only | Removed from Golden Serial via gate |
| Models/runtime generation guards | `runtime_bootstrap.py:1552`, `:1696` and restore flow | Conditional mismatch/missing | Local marker reads, `isdir`, conditional Volume reload | Correctness-critical fail-closed guards | Replaced in minimal Golden path by the single models guard |
| CPU snapshot retarget/preload tail | `modal_app.py:13442-14427` | Guarded by `_restore_plan is not None` | Potential model/path scans, futures, transport/preload | Request-plan work, not restore work | Proved unreachable because restore sets `_restore_plan=None` at `:13180`; retained for request/legacy paths |
| Post-restore speculative CLIP lane | `modal_app.py:14588-14616` | Feature-gated | Background CLIP work after `modal_restore_exit` | Not restore correctness | Not part of minimal path; existing ordering retained |
| Final legacy summaries/host probes | `modal_app.py:14645+` | Legacy return path | Diagnostics and read-only CUDA allocation query | Evidence only | Not reached by minimal path |

### Minimal helper before routing change

`modal_app.py:12408-12560` already implemented the intended narrow sequence:

1. `_golden_minimal_reset_container_state()` (`:12307-12366`)
2. `_golden_minimal_restore_logical_gpu_state()` (`:12368-12385`)
3. `_golden_minimal_assert_models_generation()` (`:12387-12406`)
4. minimal timing/identity/return-marker telemetry
5. fail-closed raise on any failed reset, repair, or generation decision

It was simply not the default Golden Serial route.

## CHANGES

1. Golden Serial now selects the existing minimal helper by default. An explicit
   `COMFYMODAL_GOLDEN_MINIMAL_RESTORE` value still overrides the profile:
   truthy selects minimal, falsy selects the legacy rollback/debug path. Non-
   Golden containers remain legacy by default (`modal_app.py:3550-3563`).
2. Golden Serial legacy escape also suppresses the restore CLIP probe, folder
   warming, and custom-node identity diagnostic (`modal_app.py:12631`,
   `:13045`, `:13254`). Non-Golden legacy behavior remains available.
3. Minimal restore passes `include_host_info=False` to
   `set_restore_return_marker` (`modal_app.py:12541-12546`). The marker helper
   preserves its legacy default `True`, but minimal restore no longer reads
   Linux `/proc/sys/kernel/random/boot_id` through `_capture_host_info`
   (`model_preload.py:9934-9965`).
4. Added a compact source-contract guard in
   `tests/test_golden_minimal_restore_validity.py` covering routing, the minimal
   allowlist, fail-closed generation behavior, marker host-probe opt-out, and
   Golden legacy pollution gates.

These changes do not alter Modal decorators, image/container configuration,
model-loading algorithms, transport semantics, sampler behavior, workflow
behavior, or request execution.

## AFTER

### Golden Serial restore call graph

`modal_app.py:12562`  
`->` boundary clocks (`:12587-12591`)  
`->` `_golden_minimal_restore()` (`:12592-12608`)  
`->` `_golden_minimal_reset_container_state()` (`:12307`)  
`->` `_golden_minimal_restore_logical_gpu_state()` (`:12368`)  
`->` `_golden_minimal_assert_models_generation()` (`:12387`)  
`  ->` `RuntimeBootstrap._decide_models_reload()` (`runtime_bootstrap.py:1552-1597`): one local `models_generation.json` read plus `os.path.isdir`; exact match required  
`->` minimal telemetry and identity marker (`modal_app.py:12438-12560`)  
`->` return

The logical GPU repair only changes ComfyUI's logical CPU/GPU state. It does
not call `torch.cuda`, query device capacity, synchronize, allocate pinned
memory, create streams/events, or construct transport resources.

## REMOVED COST

- No restore-time custom-node reconciliation, generation reconstruction, tree
  hashing, manifest rebuilding, or Volume synchronization is reachable in the
  Golden Serial minimal route.
- No restore-time folder scan/warming thread is launched.
- No restore-time CLIP probe thread or speculative source I/O is launched.
- No restore-time `/proc` boot-ID host probe is performed by minimal telemetry.
- No preload futures, executor creation, background model load, pinned arena,
  buffer-view, reader-worker, stream, event, or persistent-FD construction is
  reachable from the minimal helper.
- No accidental CUDA initialization or capacity query is introduced. The first
  real CUDA use remains owned by request/model loading.

## FIRST-REQUEST CHECK

The removed operations are not moved into CLIP setup by this change. The Golden
minimal branch returns before the legacy restore body, including the legacy
post-restore speculative CLIP lane. The existing request-side paths remain in
their original owners (`modal_app.py:21007-21162`,
`model_preload.py:19266+`, and the CLIP hydration modules); they were not moved
or expanded by this cleanup.

The source guard asserts that the minimal helper contains none of the restore
preload/warm/transport/thread symbols. Local remote execution proof could not
be collected because deployment was blocked before a remote container started
(see Remote validation below).

## SNAPSHOT CAPTURE

The separate capture audit found the following state:

### Required / retained

- CPU-sterility context and Golden's model-free capture path.
- Imported ComfyUI/custom-node modules, registered nodes, PromptExecutor, and
  DummyServer required by the snapshotted runtime.
- Bootstrap generation/certificate/seed/deployment proof state used for
  correctness and request validation.
- Passive Golden quiescence proof and the existing content proof.
- Mounted Volume files are not serialized into the snapshot.

### Safe candidates, not changed here

- Diagnostic snapshot manifests and allocator-hygiene measurements.
- Optional model-eviction machinery whose default is off.
- Diagnostic restore CLIP probe staging.
- Duplicate retained timing/proof projections.

These need a separate snapshot-size/lifecycle experiment. Presnapshot loader/
I/O workers and any retained model/bridge/transport state were deliberately not
removed without runtime evidence.

## REGRESSION GUARD

`tests/test_golden_minimal_restore_validity.py` now fails if:

- Golden Serial stops defaulting to minimal or the explicit legacy override is
  lost;
- minimal restore gains filesystem/Volume, custom-node, warming/preload,
  transport/thread, legacy repair, diagnostic, or CUDA-probe calls;
- the single models-generation guard or fail-closed raise disappears;
- minimal telemetry reintroduces the host `/proc` probe;
- the Golden legacy escape can launch the probe, folder warmer, or custom-node
  identity resolver.

## LOCAL VERIFICATION

- Guard: 10 passed; max test wall 385 ms; output:
  `C:\Users\parla\AppData\Local\Temp\opencode\golden_restore_guard_20260917.log`
- Existing minimal restore contract: 6 passed; output:
  `C:\Users\parla\AppData\Local\Temp\opencode\golden_restore_minimal_contract_20260917.log`
- Python compilation: passed; output:
  `C:\Users\parla\AppData\Local\Temp\opencode\golden_restore_compile_20260917.log`
- `git diff --check`: passed before commit.

The P2 profile test was diagnosed once with the bounded test-performance tool.
It timed out during test-module import, before collection, while existing
`comfyapp.py` publication hashing read the custom-node tree
(`publication_policy.py:393-423`); it did not execute the changed restore path.

## REMOTE VALIDATION

Requested remote validation was attempted through the required public command:

`python tools/v2ctl.py golden deploy --app golden-restore-minimal-20260917`

It failed before deployment with the workspace error “has exceeded its spend
limit”. No Golden request, snapshot-capture request, source probe, or six-run
cohort was launched. Raw diagnostics:

- `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\deployment_diagnostics\deploy_20260917T111604Z_89830078d34f.stderr.log`
- `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\deployment_diagnostics\deploy_20260917T111604Z_89830078d34f.stdout.log`

Post-failure `golden status` reported no deployment manifest, no remote checks,
and `ready=False`. Six remote runs therefore remain unperformed rather than
being represented as passing or failing observations.

## WORKTREE / ARTIFACTS

- Worktree: `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal`
- Implementation commit: `9fdbae45b7d6dbccaeda9009d0c93ff9f36f9f19`
- Changed implementation files:
  - `comfymodal_runtime/modal_app.py`
  - `comfymodal_runtime/model_preload.py`
  - `tests/test_golden_minimal_restore_validity.py`
- This report: `reports/golden_restore_cleanup_2026-09-17.md`
- Existing unrelated worktree changes were not staged or modified.
- Raw source-audit evidence is the exact source paths and line ranges listed in
  the BEFORE/AFTER tables; no Modal request artifacts exist because deployment
  was blocked.
