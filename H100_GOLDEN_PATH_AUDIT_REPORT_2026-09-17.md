# H100 Golden path audit — transfer geometry, CLIP load, and CLIP forward

Offline-only audit. No deployment, Modal invocation, request, optimization, or
new performance campaign was performed.

## 1. Executive findings

### Why H100 has approximately 4x more copy submissions

The difference is real 1:1 accounting, not telemetry inflation and not a
Golden copy-path code change.

- H100 effective geometry: 32 MiB source blocks, 8 x 32 MiB slots, 256 MiB
  arena, aggregation disabled.
- RTX effective geometry: 128 MiB source/H2D blocks, 4 x 128 MiB slots, 512
  MiB shared arena, aggregation disabled.
- Equal CLIP bytes therefore produce 243 H100 submissions versus 61 RTX
  submissions: ratio 3.98x. UNET is 370 versus 93: ratio 3.98x.
- The nominal run-identity field `transport_block_bytes=33554432` is not the
  effective RTX geometry. Raw `source_block_bytes`, `h2d_target_bytes`, slot
  size, arena size, and submission sizes are authoritative.

### What consumes the approximately 1.15 s CLIP-load residual

For H100, the residual is the median of per-request:

```text
golden_clip_load wall - SOURCE_TOTAL_WALL_MS = 1147.85 ms
```

It is not active H2D, source syscall time, a second read, cast-once, or a
post-source tail. It is the untimed remainder of the enclosing load stage:

```text
skeleton/meta model construction
adoption and pointer/storage validation
compute-ready identity proof
Python/bookkeeping gaps
transport quiescence proof-read and close-out
```

The code makes skeleton construction and the repeated adoption/proof traversal
the leading supported tenants, but the retained H100 corpus has no phase-level
timers for their internal split. No exact percentage is justified.

### What consumes `golden_clip_forward`

The whole wall is proven slow relative to the RTX population: H100 median
2122.65 ms versus RTX 1435.99 ms, +47.8%. No part inside it is proven slow.

The H100 deployment had `COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS=0`. Therefore
tokenization, graph-wrapper, encoder hooks, conversion telemetry, page-fault
telemetry, and forward decomposition were not recorded. The function contains
explicit `UNPROVEN` admissions for device preparation, first-use CUDA/library
initialization, and model-manager activity. The sampler control is faster and
tighter on H100, so the forward delta is not evidence that H100 sustained GPU
compute is intrinsically slower.

### What remains unknown about sickness

The two named mirror-image examples prove a stage-local source stall, not its
resource cause:

- CANADA-2: CLIP source 1.0308 GB/s and sick; UNET 6.2561 GB/s and healthy.
- sines-2: CLIP 6.0340 GB/s and healthy; UNET 0.9740 GB/s and sick.

Both sick streams become sick after healthy reads, have alternating isolated
episodes, and recover before the final read. Retained per-read events do not
contain FD, thread, slot, stream/event handle, or per-read QD occupancy, so no
specific pre-onset resource transition can be proven.

## 2. Identity and evidence scope

- Audit worktree: `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal`
- Starting commit: `711f7cfb932e2d44f7dc285441e9cd5f827cdd30`; worktree was dirty
  with unrelated pre-existing changes.
- Audited H100 source: `d1fffd2f5da108f0a718ea80da56152ae29f9c57`.
- RTX archaeology reference: `03ce24916958596717220167db496b1215544d09`.
- H100 deployment: app `batch-tripwire-v2-p2hb2`, profile
  `golden_p1_parallel`, method `run_golden_parallel_stream`, H100 80GB HBM3,
  static E27, nominal 32 MiB block, 8 staging slots.
- H100 source/deployment evidence: `.slim/worktrees/authoritative-golden-core-sep14/.v2ctl/deployments/receipt_5_668b088e9a8c4d03b2f4c6eda50666e5e85306ac47d7824557e796230a09d1c0.json`, matching deploy manifest, and `.v2ctl/source-probes/probe_5_668b088e9a8c4d03b2f4c6eda50666e5e85306ac47d7824557e796230a09d1c0.json`.
- H100 raw corpus: `.slim/worktrees/authoritative-golden-core-sep14/artifacts/phase_p1_parallel_golden_v1/cohort_*/{attempt_0.json,attempt_0_events.json,manifest.json,summary.json}`.
- H100 dossiers: `.slim/worktrees/authoritative-golden-core-sep14/H100_GOLDEN_RUNS_EMAIL_2026-09-17.md` and `H100_GOLDEN_RUNS_FULL_2026-09-17.md`.
- RTX raw index: `GOLDEN_HISTORICAL_RUNS_MASTER.json/.csv`; raw attempts are
  the `raw_path` values named by its rows, principally under
  `.slim/worktrees/golden-io-v2/artifacts/phase_p1_parallel_golden_v1/`.
- Existing forensic extractor: `tools/analysis/h100_vs_rtx_forensics.py`.
- Existing canonical derived evidence: `reports/h100_vs_rtx_forensics_2026-09-17/`.
- Resulting audit commit: none.

## 3. Transfer geometry

### Raw proof

H100 CLIP request `golden-p1-0-bd8ea2348bd5`, cohort
`cohort_2026-09-17_17-24-49_79e86b`:

```text
source_bytes                  8,044,936,192
source_block_bytes               33,554,432
source_read_count / blocks             243
h2d_submit / completion count          243
GPU_COPY_COUNT                         243
GPU_COPY_BYTES                8,044,936,192
arena_bytes                    268,435,456
slots                                 8
slot_bytes                      33,554,432
aggregated submissions                  0
non-aggregated submissions            243
tail submissions                        7
source opens                            4
```

RTX CLIP raw request `golden-p1-0-aec31a04f8fa`, cohort
`cohort_2026-09-14_20-11-01_d05f19`, commit `03ce249`:

```text
source_bytes                  8,044,936,192
source_block / H2D target       134,217,728
source_read_count / blocks              61
h2d submit / completion count           61
GPU_COPY_COUNT                          61
GPU_COPY_BYTES                8,044,936,192
arena_bytes                    536,870,912
slots                                  4
slot_bytes                       134,217,728
aggregated submissions                   0
non-aggregated submissions             61
tail submissions                         3
source opens                             0
```

The same relationship holds for UNET: H100 370 submissions versus RTX 93.
The H100/RTX derived decomposition independently reports the same 3.98x ratio.
Actual average bytes per accepted submission are approximately 33.10 MB H100
versus 131.88 MB RTX for CLIP; header offset and the final partial block make
these slightly below nominal block sizes.

### Call graph and accounting

```text
parse safetensors header
  -> plan_source_regions(total_bytes, block_bytes, qd)
  -> region items / producer dispatch queue
  -> preadv/readinto source buffer
  -> staging-pool slot
  -> _take_submission()
       -> single lease because aggregation is disabled
  -> _MeasuredCudaBackend.submit_h2d[_ticket]
  -> CudaTransferBackend submission/event
  -> submit counters and GPU_COPY_BYTES/COUNT
  -> event harvest/completion counters
```

Relevant current-source locations in the deployed worktree:

- `golden_serial.py:3413-3433`: `plan_source_regions`.
- `golden_serial.py:5677-5678`: region items enter dispatch.
- `golden_serial.py:5714-5745`: measured CUDA backend submission wrapper.
- `golden_serial.py:5760-5769`: `TransportConfig`; `h2d_target_bytes=block_bytes`,
  `aggregation_enabled=False`.
- `golden_qd_transport.py:2024-2129`: `_take_submission`; multi-lease
  aggregation requires a target larger than one block.
- `golden_qd_transport.py:2206-2247`: submit and submission accounting.
- `golden_qd_transport.py:1855-1856,1948-1949`: completion accounting.

Both paths classify one accepted backend copy as one submission. Both have
zero aggregated submissions and reconciled submitted/completed bytes. This is
not an event-count inflation artifact.

### Why geometry differs

The `03ce249..d1fffd2` diff has no change to `golden_serial.py`,
`golden_qd_transport.py`, or the copy backend. The effective geometry is
selected from the transport resource/slot geometry (`resources.slot_bytes`),
not merely the requested run-identity block field. The RTX deployment retained
a 128 MiB/512 MiB shared-arena C0 geometry; H100 retained 32 MiB/256 MiB/8-slot
static-E27 geometry.

The remaining archaeology gap is which RTX profile/resource construction set
the effective 128 MiB geometry despite its nominal 32 MiB identity field. That
is a deployment/profile-resource provenance question, not evidence of a
different H100 copy implementation.

Reducing H100 submissions to 128 MiB-like geometry is a valid geometry question
but not a justified optimization yet. It changes source read concurrency,
pinned arena pressure, burst size, tail behavior, and sickness exposure. H100
load is source/syscall dominated, so fewer CUDA submissions alone do not
address the proven wall.

## 4. CLIP-load residual

### Non-overlapping accounting

H100 medians from raw-derived per-run differences:

| component | median ms | interpretation |
|---|---:|---|
| enclosing `golden_clip_load` | 3673.50 | authoritative stage wall |
| source wall | 1927.21 | source read/transport wall |
| syscall union | 1923.80 | source wall is syscall-dominated |
| source minus syscall | 3.53 | small source instrumentation residual |
| H2D span | 1875.98 | overlaps source; not additive |
| active copy | 245.82 | actual copy-engine active time |
| copy idle inside H2D span | 1698.72 | stream waiting/starvation |
| post-source H2D tail | 2.73 | negligible |
| load minus source | **1147.85** | correct residual; median of per-run differences |

Do not calculate the residual as a difference of medians and then add nested
H2D terms. H2D span and active copy are inside/overlapping the source wall.

### Code-reachable contents of the residual

Current `golden_serial.py:11011-11704` takes the H100 BF16-control path:

1. resolve BF16 residency; cast-once arm is present but not taken;
2. one `read_file_qd_gpu` source/H2D lifecycle;
3. source dtype and dynamic patcher checks;
4. shallow state-dict copies and model options construction;
5. `comfy.sd.load_text_encoder_state_dicts([dict(sd)...])` meta-skeleton
   construction with `assign=True` adoption;
6. owner publication (`setattr` plus `session.clip` assignment);
7. combined-view construction;
8. `select_and_validate_qd_adoption_scope`: module/parameter/buffer pointer
   traversal, pointer-set comparison, containment and outer-extra validation;
9. `_clip_compute_identity` / `_clip_scope_snapshot`: per-tensor storage,
   pointer, device, dtype and patcher-state proof over roughly 398 tensors;
10. adoption/published events, prefetch readiness, transport quiescence
    proof-read, close-out and untimed Python bookkeeping.

### Classification

| candidate | classification | evidence |
|---|---|---|
| source/syscall | PROVEN excluded from residual | source minus syscall is ~3.5 ms |
| active H2D | PROVEN excluded as additive cause | active copy is nested in source/H2D span |
| post-source H2D tail | PROVEN negligible | ~2.7 ms |
| second read/H2D | PROVEN absent | one transport lifecycle; no fallback/re-read |
| FP32 cast-once | PROVEN absent | H100 BF16 control; cast telemetry `NOT RUN` |
| R44F native zero-copy adoption | PROVEN irrelevant | native adoption was ineligible in that historical batch |
| skeleton/meta construction | SUPPORTED leading contributor | enclosed by `skeleton_patcher_construction`; Qwen model build/adopt work |
| adoption/pointer/storage proof | SUPPORTED leading contributor | repeated module/tensor pointer traversals and strict validation |
| compute-ready identity proof | POSSIBLE | explicit span exists, but no populated H100 phase timing |
| Python copies/dicts/events/bookkeeping | POSSIBLE | reachable, untimed, shape-dependent |
| allocator/page-fault cost | POSSIBLE/UNRESOLVED | page-fault diagnostics were disabled |
| exact internal split | UNRESOLVED | H100 phase timing rows were not emitted |

The residual is therefore **multiple components**, led by constructor and
adoption/proof work. It is not justified to call it unavoidable model
construction, duplicated work, or an H100 silicon cost. RTX has no equivalent
source/H2D residual decomposition, so no cross-GPU residual claim is possible.

## 5. Exact `golden_clip_forward` boundary

Deployed source: `.slim/worktrees/authoritative-golden-core-sep14/comfymodal_runtime/golden_serial.py:12044-12397`.
The authoritative wall is recorder `begin_stage("golden_clip_forward")` at
12054 through `end_stage`/`fail_stage` at 12347/12383, not merely the encoder
kernel interval.

```text
golden_clip_forward
  -> stage open / CLIP_FORWARD_START
  -> optional page-fault/timing prologue
  -> clip_forward_entry_setup
       runner.seed; compute scope; patcher; before pointer/storage snapshot
  -> explicit unproven admissions
       device cast, projection layers, cache, model-manager, first-use CUDA
  -> runner scope
  -> optional cast_to conversion observer
  -> optional structural and selected-scope hooks
  -> optional tokenize and encode wrappers
  -> clip_graph_node_wrapper
       runner.run_closure(CLIPTextEncode)
         -> tokenize (CPU)
         -> encode_from_tokens_scheduled
         -> Qwen transformer forwards
         -> comfy.model_management.cast_to calls
         -> attention/MLP/norm kernels in upstream ComfyUI
  -> clip_post_forward_sync_wait
       runner futures/tasks quiescence only; no torch CUDA synchronize
  -> compute-dtype derivation and conversion bookkeeping
  -> conditioning packaging from runner cache
  -> after snapshot/materialization recheck
  -> timing/event/bookkeeping and stage close
  -> return conditioning
```

The H100 corpus ran with stage diagnostics off. Thus the following were not
measured: tokenization span, graph wrapper span, encoder hooks, cast counts and
bytes, first CUDA submit/completion, page faults, materialization split,
forward decomposition, and compute dtype. The only proven slow part is the
whole enclosing wall.

The H100 forward median is 2122.65 ms versus RTX 1435.99 ms. Sampling is a
control: H100 median 3891.69 ms versus RTX 4665.62 ms, with tight H100 spread.
This weakens an intrinsic H100 compute explanation but does not identify the
forward sub-interval.

## 6. First-use initialization

The minimal restore path introduced after the RTX ancestor deliberately performs
logical GPU repair and a models-generation guard without CUDA probing, device
synchronization, transport creation, pinned allocation, preload, or folder warm.
It therefore **defers** request-time first-use work; it does not remove it.

| candidate | current classification |
|---|---|
| CUDA context / allocator / cuBLAS or library initialization | request-dependent, exact placement unresolved |
| first encode kernel/autotune/JIT | request-dependent first-use; SM90-specific JIT unproven |
| baked Sage/CUDA package | imageable, but H100 sm_90a bake coverage unproven |
| attention/backend first-use | request-dependent; no forward backend boundary |
| tokenization and prompt-shaped encode | request-dependent |
| loaded CLIP GPU state | request-dependent; not carried by model-free snapshot |
| conditioning packaging and telemetry | request-dependent |
| minimal restore repair/generation check | restore-only |

No first-use item is proven to be safely imageable or snapshotable in the
deployed true-cold configuration. Moving any such work before the timer would
be an endpoint change, not an optimization proof.

## 7. Existing proposed instrumentation audit

Existing patch:
`reports/h100_vs_rtx_forensics_2026-09-17/proposed_clip_forward_boundaries.patch`.
It is unapplied and was validated with `git apply --check` against `d1fffd2`.

It preserves order and adds no synchronization when enabled; CUDA events are
resolved after the already-required host quiescence boundary. With the gate off
it is not a semantic no-op: it adds cheap Python dispatch calls at hooks/cast
sites. With the gate on it adds two CUDA events and recorder CPU timestamps.

It is insufficient for this audit because it does not split tokenization,
graph-wrapper execution, patch/device preparation, CUDA initialization,
attention/backend setup, later encoder forwards, conditioning packaging, or
bookkeeping. Its `first_cuda_submit` is an observed-op proxy, not a context/JIT
boundary, and its first CUDA pair can represent a cast or encoder hook.

A corrected, unapplied patch is retained at
`reports/h100_golden_path_audit_2026-09-17/proposed_clip_and_load_boundaries.patch`
with its README. It passed `git apply --check` against `d1fffd2` and throwaway
copy compilation/CPU-smoke validation. It must be reviewed before any
application; no patch has been applied or deployed. Its honest limitation is
that tokenization/encoder/cast proxy marks depend on existing stage-diagnostic
wrappers, so missing marks are reported rather than fabricated when diagnostics
are off.

## 8. Source sickness and state transitions

At 500 ms, the retained H100 population verifies:

| role | born-sick | becomes-sick | never-sick | final read sick |
|---|---:|---:|---:|---:|
| CLIP | 3 | 3 | 5 | 0 |
| UNET | 1 | 3 | 7 | 0 |

Both named cases are `becomes_sick + alternating`, with isolated sick reads:

- CANADA-2 CLIP: first >=500 ms at read 5, 803.80 ms; 9 sick reads; max
  3927.61 ms; UNET has no >=500 ms read.
- sines-2 UNET: first >=500 ms at read 5, 3101.37 ms; 10 sick reads; max
  3101.37 ms; CLIP has no >=500 ms read.

The sick role is the slow-source/slow-load role in both, while active H2D
throughput remains in the normal 30–46 GB/s band. No onset discontinuity is
visible in the retained fields: no error, retry, short read, byte-size anomaly,
provenance switch, or producer-rotation break. Record-level arena, stream/event
counts, allocation counts, adoption, reconciliation, E27 proof, and quiescence
are the same shape between sick and healthy sibling stages.

The retained per-read schema has only destination/source offsets, producer and
region IDs, byte counts, retry/error flags, and syscall timestamps. It has no
FD, thread ID, slot, stream/event handle, per-read QD occupancy, lease-wait, or
backpressure timeline. The causal pre-onset state transition is therefore
UNRESOLVED. Cross-stage quiescence is clean, but host interference windows and
allocation timing are not retained.

## 9. SHA authority audit

The three values have different owners:

| value | owner | consequence |
|---|---|---|
| `ab3c08…7104f` | frozen v2ctl CLI/profile expectation in the H100 evidence bundle | outer manifest exact-output validity failure only |
| `790c30…0e89d` | serial-Golden `EXPECTED_OUTPUT_PNG_SHA256` / `golden_p1.toml` | in-run warning/validity expectation; not transport/runtime control |
| `3a6a03…24577` | H100 actual output and current parallel ComfyKitchen expectation | actual H100 bytes; deterministic across 11 runs |

The frozen H100 parallel profile carried `ab3c08…`; the deployed runtime emitted
the serial-Golden `790c30…` as its nested expected value, while actual bytes
were `3a6a03…`. The current main parallel profile now names `3a6a03…`, but
that is not the profile frozen into the H100 deployment.

The validator plumbing treats these mismatches as warning/validity-only for
non-durable output; it does not change pixels, transport, or timing. Workflow
SHA is independent. Do not redefine the expected SHA in this audit.

## 10. Restore/state audit

The H100 minimal-restore change is performance-relevant for restore placement
but is not a load/forward explanation:

- Python restore totals are near equal: RTX 3.289 ms, H100 3.387 ms.
- Restore resets mutable state, repairs logical GPU state, checks the models
  generation file, and returns without creating transport owners or warming
  CLIP.
- CUDA readiness is deferred to request work rather than removed.
- Model management is narrowed to an exact-match guard; no model hydration or
  Volume discovery occurs in restore.
- Sage/backend logical settings and workflow SHA are unchanged; compute dtype
  and Sage resolution remain unproven.
- Pinned arena/stream state is request-local, explaining no cross-stage owner
  carryover, but not the 4x geometry choice itself.

## 11. Theory matrix

| theory | result | evidence |
|---|---|---|
| 4x copies are telemetry inflation | CONTRADICTED | submitted/completed bytes/counts reconcile; zero aggregation both paths |
| H100 copy code changed after RTX | CONTRADICTED | no Golden transport/copy-path diff in `03ce249..d1fffd2` |
| effective block/arena geometry changed | SUPPORTED | raw 32 MiB/256 MiB H100 versus 128 MiB/512 MiB RTX |
| fewer submissions automatically improve load | UNRESOLVED | changes source concurrency and sickness exposure |
| CLIP residual is source or copy | CONTRADICTED | source/syscall residual ~3.5 ms; active copy nested and small |
| CLIP residual is cast-once | CONTRADICTED | BF16 control; cast-once `NOT RUN` |
| CLIP residual is constructor/adoption/proof | SUPPORTED | exact reachable spans and pointer traversals; no phase timers |
| CLIP forward is pure GPU compute | CONTRADICTED | boundary contains CPU/wrapper/bookkeeping; diagnostics off |
| H100 forward kernels intrinsically slow | UNRESOLVED/WEAKENED | sampler faster; no forward sub-boundaries |
| SM90 JIT/library init causes forward delta | POSSIBLE, UNRESOLVED | explicit unproven admission; no init/JIT boundary |
| sickness is a fixed bad H100 host rate | CONTRADICTED | CLIP/UNET mirror-image reversals in same request |
| sickness is tied to specific FD/QD/event | UNRESOLVED | required identifiers absent from raw schema |
| restore causes load/forward regression | WEAKENED | restore near-equal and no model/transport work |
| SHA mismatch corrupts performance rows | CONTRADICTED | deterministic actual output and successful reconciled transport; exactness remains invalid |

## 12. Minimum future instrumentation

No optimization is justified yet. The smallest missing evidence is:

1. CLIP-load phase timestamps for source-open/read, skeleton construction,
   owner publish, storage adoption, compute-ready proof, final sync/return.
2. CLIP-forward timestamps for tokenization, graph wrapper, CPU setup, first
   observed CUDA operation, first completion, encoder begin/end, existing
   quiescence, conditioning packaging, and return.
3. Per-read FD/thread/slot/stream/event/QD occupancy fields only if the sickness
   cause must be localized further; existing records cannot answer that question.

These should be added as proposed, gated instrumentation only. They must not
change QD, block size, source geometry, workflow, model, sampler, Sage,
attention backend, execution order, or endpoint placement. No campaign is
recommended until those boundaries are reviewed.

## 13. Audit artifact manifest

- Report: `H100_GOLDEN_PATH_AUDIT_REPORT_2026-09-17.md`.
- Existing raw-derived script: `tools/analysis/h100_vs_rtx_forensics.py`.
- Existing derived data: `reports/h100_vs_rtx_forensics_2026-09-17/`.
- Existing forward patch audited but not applied:
  `reports/h100_vs_rtx_forensics_2026-09-17/proposed_clip_forward_boundaries.patch`.
- Corrected proposed patch: `reports/h100_golden_path_audit_2026-09-17/proposed_clip_and_load_boundaries.patch`, with `proposed_clip_and_load_boundaries_README.md`; validated offline against `d1fffd2`, not applied or deployed.
- H100 raw paths: `.slim/worktrees/authoritative-golden-core-sep14/artifacts/phase_p1_parallel_golden_v1/cohort_*/` and the deployment/source-probe paths listed in §2.
- RTX raw paths: `raw_path` entries in `GOLDEN_HISTORICAL_RUNS_MASTER.json/.csv`, principally `.slim/worktrees/golden-io-v2/artifacts/phase_p1_parallel_golden_v1/cohort_*/`.
- No files in the deployed H100 source or RTX archaeology worktrees were
  modified. No QD/block/model/workflow/backend/sampler/Sage/container setting
  was changed. No frozen 20+20 experiment was touched.

## 14. Unresolved assumptions

- The exact RTX deployment/profile/resource provenance that selected effective
  128 MiB blocks is not in the retained comparison row.
- The internal 1.15 s CLIP-load split has no existing H100 phase timers.
- The forward patch’s first-CUDA event is a proxy, not a context/JIT proof.
- H100 sm_90a JIT/bake coverage and actual compute dtype remain unproven.
- Retained sickness events cannot identify the causal FD/QD/slot/thread/event
  transition.
- H100 exact-output expectation authority is still not redefined; the three
  values remain separately recorded.
