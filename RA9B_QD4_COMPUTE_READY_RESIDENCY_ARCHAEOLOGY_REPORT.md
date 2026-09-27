# RA9B — QD4 Compute-Ready Residency Archaeology Report

**Repository:** `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal`

**Scope:** read-only reconstruction of the QD4, FastSafe, compute-ready CLIP,
Golden Serial, and Golden dispatcher histories. This report is the only file
written for RA9B. No source/config/test/skill file was changed; no deploy, run,
branch, worktree, reset, stash, clean, revert, or checkout was performed.

## 0. Evidence discipline and repository state

The initial parent observation was `TESTING2` at `02f1845` (`golden path v1.1`)
with a dirty tree containing concurrent work. During this investigation the
concurrent checkout was observed at `7f9a19e` (`some data`), still dirty. Those
changes are not attributed to RA9B and were not reset or otherwise altered.

The Codebase Memory project is
`C-Users-parla-OneDrive-Documents-AI-HUB-ComfyUI-June-Install-ComfyUI-custom_nodes-comfyui-modal`,
generation `2026-08-20T20:45:51Z`. `V2_BATCH_E28...` was graph-skipped because
of a parse timeout; where graph and report labels differ, the raw source,
embedded run JSON, logs, and the exact report text are authoritative.

### Classification vocabulary

* **TOTAL** — total for the explicitly named measured operation, from its
  documented start boundary to its documented end boundary. It is not silently
  promoted to a larger lifecycle.
* **PARTIAL** — a real component or suffix/prefix of the target lifecycle.
* **CONTAMINATED** — the interval includes quantified external waiting,
  unrelated work, or mixed boundaries.
* **UNKNOWN** — the proposed number/boundary cannot be reproduced from the
  available artifact/source evidence.
* **BROKEN** — the run/counter/path did not execute the named operation or ended
  in a correctness/lifecycle failure.

Every timing below states whether it is total or partial in this sense.

## 1. Chronology: source and architecture changes

### 1.1 E27/E30 QD transport evidence

The historical implementation lineage is anchored by commit
`8e49d758c02e243e364eb3c3922cae747827c1de` (`8e49d75`, E27/E30-era state).
The raw implementation evidence is `V2_BATCH_E30_CLIP_QD_IO_IMPLEMENTATION.md`
and the source it describes, `comfymodal_runtime/clip_qd_reader.py`.

The decisive QD4 result was **191.4 ms**, **42.03 GB/s**, with approximately
**30 ms CPU** for the full source operation. QD1 was **1047.3 ms / 7.68 GB/s**;
QD2 **403.0 ms / 19.96 GB/s**; QD8 **178.8 ms / 45 GB/s**, but approximately
**220 ms CPU**; QD16 regressed. These are **TOTAL for the measured QD source
transport operation**, not TOTAL for model construction, bind, validation,
adoption, or sampler readiness. The `clip_qd_reader.py` module documents the
QD4 line as `QD4 / 32 MiB ≈ 42.03 GB/s (191 ms, 30 ms CPU)` at lines 22–28 and
the short-read retry implementation uses `os.preadv` at lines 258–273.

The architecture was: static disjoint safetensors ranges; four source workers;
`os.preadv` with retry; one bounded pinned buffer per worker; asynchronous H2D
into a contiguous destination with tensor views; and staging sized
`qd * block = 128 MiB` for the historical four-worker reader. The header was
parsed once for tensor-aligned blocks and coverage checks. Those are structural
claims, not a full-stage timing claim.

The local **QD4 104.0 ms, `obs_max=4`** observation is **TOTAL only for that
local measured operation** and **PARTIAL/UNKNOWN as remote evidence**: it is not
proof of remote Modal throughput.

E27's UNET transport probe, raw artifact `_e27_unet_qd_evidence.json`, reported:

```text
storage_plus_h2d_wall_ms = 1020.8782
bytes                   = 12,309,817,472
h2d_device_ms           ≈ 1020.7964
host_issue_ms           = 5.6668
throughput              ≈ 12.06 GB/s
```

That is **TOTAL for the probe's storage-plus-H2D operation**, but **PARTIAL for
UNET readiness**. It excludes construction, bind, owner retention, validation,
patcher/model-management registration, residual-meta handling, and sampler
work. `E27_FIVE_TARGET_CRITICAL_PATH_FORENSICS.md` §4.3 and
`unet_qd_probe.py:1006–1094` establish the probe boundary.

### 1.2 E28 FastSafe pipeline

E28 is commit `0ba7000bd5f3c7ed52e8d9e0facbc0c598eb6997` (`0ba7000`, critical
path implementation). The later checkpoint commit
`36b895db1992fde285735ac9e59c63bb238a6e0a` (`36b895d`, E37/E38 checkpoint)
contains the source/report state used for the later audit. The source boundary
is `comfymodal_runtime/unet_fastsafetensors.py`.

The functions `_fs_try_pipeline`, `_fs_fastsafe_load`, `_fs_meta_construct`,
and `_fs_validate_final` implement a timer that starts before eligibility,
configuration, and header work. Worker A performs meta construction while
Worker B performs FastSafe file→GPU loading. The pipeline joins both workers,
validates and binds, performs the residual-meta sweep and final `.to()`, waits
for readiness, retains the loader/buffer owner, and runs the patcher only after
sync/validation. In the current source, the corresponding post-join and bind
chain is visible at `unet_fastsafetensors.py:1690–2019`; final validation and
owner attachment are at `:1965–2017`.

Thus the **total pipeline timer is TOTAL for the named FastSafe pipeline**, not
necessarily TOTAL for the complete serialized `load_models_gpu` handoff unless
that demand boundary is included. It includes header/config, A/B worker work,
join, validation, bind, residual sweep, final `.to()`, sync, final validation,
patcher, and owner attachment. It does not retroactively include a later
sampler-side handoff that its artifact did not measure.

E28's exact evidence from `V2_BATCH_E28_CRITICAL_PATH_IMPLEMENTATION_AND_VALIDATION.md`
§§1, 3–4 is:

* FastSafe file→GPU: **2014 ms → 477 ms** after changing the bounce buffer to
  512 MiB; pipeline **12.53 s → 4.46 s**. The file→GPU number is **TOTAL for
  `copy_files_to_device`**, **PARTIAL for UNET readiness**.
* Historical D15 gate: **250 ms → 0.1 ms** after moving the token from the
  whole read to only the GPU-committing section. This is **TOTAL for the named
  gate wait**, not a model-load total.
* The first final Gantt reported restore **4.49 s**, CLIP hydration **319 ms**,
  CLIP forward **5.59 s**, UNET H2D **0.2 ms**, sampling **4.70 s**, VAE
  **346 ms**, and output **171 ms**. Each is **TOTAL only for its named span**;
  the Gantt is not a proof that these spans are disjoint or that any one is a
  complete model lifecycle.
* The same report records contaminated fence waits of
  `unet_gpu_commit_wait_ms=5746.928 ms` and `3794.59 ms` in later final-form
  runs. They are external CLIP-fence waits, not UNET transport capability.

### 1.3 C9 first-touch FastSafe

`V2_BATCH_C9_FASTSAFETENSORS_INTEGRATION_REPORT.md` is the C9 object/report.
Its valid run path is `v2_2026-08-15_18-32-47`, with exact output SHA
`20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`.

Exact C9 telemetry, report lines 137–156 and 208–218:

```text
header/config wall       = 14.49 ms
value probe              = 0.94 ms
meta_get_model           = 2292.86 ms
sampling fix             = 12.61 ms
fastsafe setup           = 21.89 ms
fastsafe_file_gpu_wall   = 2172.92 ms (5.67 GB/s)
instantiate              = 0.57 ms
bind                    = 9.54 ms
final sweep+to           = 43.45 ms
final sync              = 0.05 ms
total pipeline           = 2743.40 ms
native reference         = 4605.3 ms
saving                   = 1861.9 ms / 40.4%
fallback                 = 0
native reread            = 0
```

`meta_get_model=2292.86 ms` and `fastsafe_file_gpu_wall=2172.92 ms` are
**TOTAL for their named calls**, **PARTIAL for the pipeline**. `bind=9.54 ms`,
final validation **43.45 ms**, and final sync **0.05 ms** have the same rule.
`total pipeline=2743.40 ms` is **TOTAL for C9's named pipeline**, with no proven
external fence contamination, but **PARTIAL for an end-to-end serialized
UNET load claim** because this run lacks the demand-side `load_models_gpu`
decomposition. C9 proves a measured complete FastSafe pipeline and exact
output; it does **not** prove a 1–1.5 s UNET lifecycle.

The owner is not optional: C9's report lines 87–104 show that
`FilesBufferOnDevice` owns the GPU backing buffer, views are valid only while
it remains open, and `_comfymodal_fastsafe_owner` is retained on the patcher.

### 1.4 E36/E37 and OC4 correction of apparent fast UNET numbers

`E36_FULL_CRITICAL_PATH_REPORT.md` records valid QD4 source walls
**2654.1844 ms** (ARM-A) and **2885.5178 ms** (ARM-B), with first durable
**17926.783 ms** and **18734.476 ms**, respectively, at lines 176–181. The
**52.9724 s** snapshot-creation run is invalid and excluded. There was no
UNET FastSafe source interval in E36. E37's **1043.5138 ms** source wall is
CLIP, not UNET.

The E36 QD4 source walls are **TOTAL for the measured QD source operation** and
**PARTIAL for UNET readiness**. The first-durable values are **TOTAL for the
named first-durable request boundary**, but not a UNET load total.

OC4 (`OC4_UNET_TIMING_COMPLETENESS_2026-08-25.md`) makes the boundary explicit:

* E27's `1020.8782 ms` is **TOTAL for the probe**, **PARTIAL for
  GoldenUnetLoad**.
* C9's `2743.40 ms` is **TOTAL for the C9 pipeline**, **PARTIAL for the full
  sampler handoff**.
* E28's `452.8152/465.0659 ms` FastSafe file→GPU values are **TOTAL for those
  file→GPU calls**, **PARTIAL for readiness**.
* E28 pipeline totals **6870.45/5995.19 ms** are **TOTAL for the measured
  pipeline operation but CONTAMINATED/MIXED** by
  `5746.928/3794.59 ms` CLIP-fence waits; they are not UNET transport totals.
* E37 `load_models_gpu=840.785 ms` and `ModelPatcher=837.042 ms` are **TOTAL
  for the demand-time model-management operation**, **PARTIAL for UNET load**:
  `traversal=11.046 ms + patch_weight=4.913 ms + residual=821.083 ms`.
  The snapshot already supplied CPU-resident weights; there was no source read,
  construction, or patcher creation in that interval.
* E39's source interval was **1418.6 ms aggregate 5.67 GB/s, steady 1.63
  GB/s**. It is **TOTAL for that source interval**, **PARTIAL for readiness**.

The reports' brief rate context remains: E37/old E39/R41 QD4 used roughly
12.31 GB, with about **283 ms** source and about **100 ms CPU** in the best
historical brief; other source observations were **30–43 GB/s**. E39's
integrated source wall was **1418.6 ms**. These are not interchangeable
boundaries and are not a complete UNET result.

### 1.5 Golden history and current remote limitation

R41's base is `0c59f46e3238f421378e8852ebc548da815b70af` and its implementation
commit is `2187c5e144de3cfd7e5a7546d9235b954ea2e6cd` (`2187c5e`, parent
`0c59f46`). Occupancy amendment commit `442f18d` is later R41 work. The R41
report explicitly says no Modal deployment was performed and physical speed is
unobservable.

The best complete remote Golden structural observation supplied for this
archaeology is a **1.804 s UNET load**. Its output SHA failed, so it is
**TOTAL only for the named observed load span but BROKEN/NOT acceptance-valid**;
it cannot set `FASTEST_VALID_UNET_LOAD_MS`. The remote CLIP range was
**1.38–7.37 s**, UNET **1.80–2.69 s**, and forward **1.36–1.78 s**. Each range
is **TOTAL only for its named artifact span**, but **BROKEN as acceptance
evidence** because the output SHA was invalid. Same-storage exact adoption and
durability were structurally proven, but output correctness was not.

The latest RV2 deployment stopped at S4 publication:

```text
expected_generation = e9c604ad4d43e95a
result_generation   = 7fc71a1f6e08ad80
readback_generation = null
```

This is a **BROKEN/UNKNOWN control-plane state**, not runtime evidence. The raw
locations are `RV2B_REMOTE_BASELINE_RAW_LOG.md`,
`RV2B_REMOTE_GOLDEN_BASELINE_RAW_LOG.md`,
`RV2B_REMOTE_GOLDEN_BASELINE_TRUTH_REPORT.md`, and
`RV2B_REMOTE_MEASUREMENT_RAW_EVIDENCE_20260830T000000Z\campaign.log` plus its
complete readable/UTF-8 siblings. RA9B does not deploy or retry it.

## 2. R41 dispatcher versus current Golden Serial

### 2.1 What R41 actually changed

Historical R41 commit `2187c5e`, parent `0c59f46`, added
`comfymodal_runtime/golden/qd_engine.py`. The historical implementation at
`qd_engine.py:350–510` contains `GoldenQD4Loader` and `_StagingRing`: source
workers publish ready items; a dispatcher owns H2D issue/reap and ring release.
Source workers never inspect completion events. This is a **TOTAL structural
claim** about the scheduler topology, not a timing claim.

That topology removes the specific read → H2D completion wait → next-read
coupling. R41's local synthetic proof is only structural: injected slow H2D
kept observed source QD at four and classified bounded-ring backpressure. The
report `R41_DETERMINISTIC_GOLDEN_QD4_PIPELINE_REPORT.md:81–90,193–201` states
that physical GB/s conclusions are deliberately absent; its lines 203–210
leave Modal-volume throughput, real occupancy, and device-event semantics
unresolved. R41 report lines 193–210 also state physical Modal validation was
unresolved.

### 2.2 Current Golden Serial coupling

Current `comfymodal_runtime/golden_serial.py` is self-contained and strictly
serial:

* `_qd_gpu_worker` at `:2043–2138` waits for the previous slot event before the
  next `_read_at`; the exact wait is `:2060–2075`.
* `read_file_qd_gpu` at `:2184–2603` allocates `qd * 2` slots, joins all
  workers, waits all outstanding events, reconciles records, creates views,
  and retains an owner.
* The final event drain is `:2381–2395`; `_require_transport_quiescence` at
  `:2587–2603` requires joined workers, waited events, complete copies, no live
  operation, and no registered Golden QD thread.
* `golden_serial_execute` at `:6764–6868` calls restore, setup, CLIP load,
  CLIP forward, UNET load, sampler preparation, VAE load, sampling, decode,
  output, durable commit, and teardown in one visibly serial order.

The current source therefore lost the dispatcher when QD became self-contained.
The current per-slot wait is a **TOTAL wait for that event-wait operation** and
**PARTIAL/CONTAMINATING for source transport** when it stalls the producer. It
is not itself a global device sync.

Retained before/after data cannot establish physical causality:

* E37: CLIP source **1043.5138 ms**, aggregate **7.71 GB/s**; H2D host issue
  **127.4 ms**, CUDA event **27.3 ms**.
* E39: source **1418.6 ms**, aggregate **5.67 GB/s**, steady **1.63 GB/s**.
* R41 synthetic injected slow-H2D: source progress/backpressure only; no
  physical before/after total.

The correct classification of R41 versus current timing causality is
**UNKNOWN**. R41 was not present in the fastest 1–1.5 s observations; it was a
later proposal/synthetic proof and must not receive historical credit for those
observations.

### 2.3 Lifetime/correctness constraints from RA9A

`RA9A_QD_SHARED_PINNED_STAGING_ARCHITECTURE_REPORT.md` identifies why a blind
dispatcher resurrection is unsafe:

1. `golden_clip_load` can retain an earlier successful owner only in a local
   list until all checkpoints succeed (`golden_serial.py:4379–4439`); a later
   failure can leak that transaction.
2. `GoldenQDOwner.release_staging()` only clears Python references
   (`golden_serial.py:1795–1835`); it does not prove worker, queue, callback,
   producer, or CUDA-event quiescence.
3. Slot reuse requires producer retirement, a recorded completion event whose
   query/synchronize proves completion, no queue/callback/reader reference, and
   a locked lease transition. Worker join alone is insufficient.
4. Shared staging must never release adopted CUDA backing storage. `assign=True`
   makes model parameter views depend on the model owner, not on the short-lived
   staging lease.
5. Snapshot state excludes readers, events, owners, queues, and pinned buffers;
   serialized snapshot bytes remain unobservable. A request pool cannot be
   snapshot state.
6. R41/E40 integration seams were unmerged. The R41 report's reconciliation
   manifest requires CLIP routing, UNET adoption at `load_models_gpu`, VAE join,
   ledger/status mapping, and profile truth before remote validation.

These are correctness and lifetime reasons, not evidence of a throughput gain.

## 3. CLIP: QD, compute-ready FP32, and timing boundaries

### 3.1 E37/OC2/OC3 CLIP timing

`E37_CLEAN_LANE_ALGORITHM_RECOVERY_REPORT.md:26–44` reports QD source wall
**1043.5138 ms**, **240/240** blocks, `conditioning=miss_not_stored`, and
`encode_calls=1`. The Golden plan records approximately **1.15 s** at its
planning references (E37 report lines 289/1245 in the embedded plan material).
OC2's closest total proxy was source submit **1043.514 ms**, device-ready
approximately **1080.424 ms**, and hydration/publication **1149.953 ms**.
These are **TOTAL for their respective named source/device/hydration spans**,
but **PARTIAL for CLIP source→adoption→encode**: no enclosing source,
publication, model adoption, and encode wall exists.

OC3's forward interval **1110.221 ms** brackets only `encode_token_weights`.
Tokenize was **8.125 ms**, model management **0.803 ms**, and cache/publication
were outside that interval. It is **TOTAL for the named `encode_token_weights`
operation**, **PARTIAL for CLIP forward**, and does not prove GPU-busy time.
Earlier approximate **1.11 s** and **2.27 s** combined figures are
**UNKNOWN/CONTAMINATED**, not arithmetic totals. `FULL_RUN_LOGS.md:2122,2134`
contains an unrelated `CLIPTextEncode` around **2.277 s**; it cannot be added to
OC3.

### 3.1a Omitted historical/current CLIP paths

The R44F negative control is documented by
`R44F_CLIP_ZERO_COPY_ADOPTION_REPORT.md` and
`R44F_CLIP_ZERO_COPY_ADOPTION_RAW_LOG.txt`. It reports
`reason=native_adoption_ineligible` and
`detail=dtype_parity_mismatch:file_0:BF16` where the expected dtype was
`torch.float16`. Runtime status was **DEGRADED** with an empty loader. Although
the output SHA matched, this is **BROKEN/NOT acceptance-valid for CLIP zero-copy
adoption**: it proves neither native adoption nor zero-copy residency. The
native CLIP `load_models_gpu` wall was **2299.661 ms** with a CUDA delta of
**8,101,709,312 bytes**; those are **TOTAL for the named native call**, not a
zero-copy or compute-ready CLIP result. The accompanying UNET control had
same-storage **453/453**, `copied=0`, owner retained, and file→GPU
**629.2175 ms**. That is **TOTAL for the named file→GPU call** and a positive
structural UNET storage-control result, but **PARTIAL for UNET readiness** and
not CLIP evidence.

OC2/D12/modern request-FastSafe evidence is in
`OC2_CLIP_LOAD_TIMING_COMPLETENESS_2026-08-25.md`. Hydration totals were
**4362.2/1533.5/1952.9 ms**; file→GPU was **1401.9–1850.5 ms**, **PARTIAL**
for readiness. The **4362.2 ms** total is **CONTAMINATED** by approximately
**2.85–2.89 s** of shared-GPU wait. Modern request-FastSafe file→GPU values
were **1566.653/2433.150/2283.353 ms**, with pathological
**26390.147 ms**; construction/bind was **255.707–384.932 ms**. No explicit
CUDA synchronization or scoped event establishes H2D completion at
publication, so that completion boundary is **UNKNOWN**. These labels do not
establish acceptance; fallback identity and exact output validity remain
required.

E26 speculative hydration, also covered by the OC2 report, read from the
producer before demand. Its exposed demand values **2429.8/2075.5 ms** measure
join+verify+bind, not the producer read, so they are **PARTIAL** rather than
hydration totals. Cycle 1 duplicated the full read because the lane was
unconsumed. This is **CONTAMINATED/UNKNOWN** as a source→adoption result until
duplicate-read, fallback, and output-validity state are proven; the label is
not acceptance evidence.

### 3.2 E31 cast-once facts and broken counter

`V2_BATCH_E31_CLIP_FORWARD_FP32.md:94–176,180–223,260–297` establishes the
actual dtype flow: BF16 resident weights, FP32 compute/manual-cast, **252 real
Linear weight conversions per forward**, approximately **73 small RMSNorm
casts**, and **15,311,175,680 FP32 destination bytes per forward**. The
reported **~2.03 s** counter region is **BROKEN** as a whole-forward timer:
the GPU forward was absent from that counter/pre-fill boundary. The **707–784
ms** cast region is **TOTAL for that measured cast-counter region**, **PARTIAL
for the forward**, and cannot be called forward wall.

The local exact cast-once design in `clip_fp32_cast_once.py:85–265` widens BF16
to FP32 once, then `assign=True` adopts the FP32 tensors. E31 lines 260–297
describe the exact local proof: approximately **10.7 → 2.2 ms** cast wall,
approximately **8 GB** additional resident VRAM, and zero repeated real
conversions in the local second-forward test. This is **TOTAL for the local
cast operation/second-forward proof**, **PARTIAL for remote CLIP forward**, and
not a current Golden acceptance result.

The old E28 “~8 ms saving” conclusion is not safe to reuse: E31 lines 170–176
state that its `cuda_event_wall_ms=0.0` came from a back-to-back unsynchronized
event pair and contradicted the cast wall. That historical claim is **BROKEN**.

Current Golden `clip_fp32_cast_once.py` and `golden/model_owner.py` show an
ownership-transfer shape, but no obvious current Golden equivalent of the
complete E31 remote experiment. If enabled, current code replaces BF16
parameter storage with FP32 rather than retaining both copies; a failed cast
returns to the BF16 normal path. Invalidation is keyed to rehydrate/device/model
generation and patch mutation. Current repeated-cast equivalence is therefore
**UNKNOWN/UNPROVEN**, not accepted from E31's older path.

Valid compute-ready predicates are: source storage is unchanged; dtype and
device are unchanged; patch state is unchanged; parameters are unchanged; model
generation/identity is unchanged; and the owner retaining the adopted storage
outlives every consumer. A claim fails closed if any predicate is unknown.

### 3.3 Four cast design choices

* **A — two copies:** simplest fallback, but adds roughly one model-sized GPU
  copy and creates stale-copy invalidation risk. Reject as the default.
* **B — ownership transfer:** widen once and make the adopted FP32 tensor the
  parameter storage; preserve owner lifetime and fail-closed invalidation.
  This is preferred when exact output and VRAM budget pass.
* **C — direct compute dtype:** retain BF16 storage and ask the operator path
  to compute FP32 without a persistent FP32 parameter representation. This
  avoids a second model copy but requires operator/runtime support and still
  needs exact timing.
* **D — hybrid:** widen only compute-relevant leaves. It reduces VRAM but
  complicates manifest, dtype, patch, and validity proofs.

No design gets historical speed credit. Prefer no two model-sized GPU copies.

## 4. Current architecture and accidental serialization

### 4.1 CLIP dispatch and clean lane

Current `model_preload.py:14252–14263` `_load_clip` calls the original loader.
Fast hydration is separately installed by
`clip_fast_hydration_wiring.py:2917–3015` through `install_demand_wrapper`.
The clean lane at `clip_fast_hydration_wiring.py:1319–1442` requires QD4,
joins readers, waits H2D, checks coverage, and publishes the owner before bind.
Failure at `:2004–2048` resets, closes owners, purges, and returns/raises via
the native path; this is fail-closed and observable.

The production profile has CLIP fast hydration disabled. Native fast-disk UNET
is enabled, GPU fast return is enabled, and the registry defaults CLIP QD,
CLIP/FastSafe, and UNET FastSafe to disabled. `config/v2/profiles/production.toml:31–50`
records the production values. E37 profiles enable CLIP fast and choose QD4
**or** FastSafe, not both.

### 4.2 UNET dispatch and owner mapping

`model_preload.py:14084–14165` selects pinned-ring → meta-direct → FastSafe →
native. FastSafe's GPU gate is after source work at
`unet_fastsafetensors.py:1720–1782`; validation/adoption is
`:1859–2032`. Exact-residency fast return may skip original bookkeeping only
after proof at `model_preload.py:4102–4173,4560–4565`.

The old E38 owner-key mismatch is fixed, not a current regression:
`comfyapp.py:1523–1531,12546–12571` maps CLIP to `restore_preload` through
`RESTORE_ROLE_OWNER_MAP`. This fixes identity/lifetime reconciliation but is
not a latency measurement.

### 4.3 Sync and wait inventory

The following is a conservative **source-site count**, not a runtime invocation
count. A runtime count depends on which arm, number of slots, number of
records, CUDA availability, and fallback path actually execute.

**Seven explicit `torch.cuda.synchronize` call sites in the current relevant
loader/readiness code:**

1. `clip_fast_hydration.py:523–529` — `hydrate_meta_assign` completion.
2. `clip_fast_hydration.py:548–564` — `hydrate_safetensors_cuda` completion.
3. `clip_fast_hydration.py:645–652` — FastSafe fallback when scoped readiness is
   disabled.
4. `clip_fast_hydration.py:709–716` — pinned-staging fallback completion.
5. `clip_fast_hydration_wiring.py:1716–1725` — CLIP bind completion when the
   scoped event path is disabled.
6. `model_preload.py:16465–16509`, especially `:16506` — device-wide CLIP
   load-device synchronization fallback.
7. `unet_fastsafetensors.py:1948–1962`, especially `:1956` — UNET final
   device-wide fallback when scoped readiness is disabled.

These are sync primitives, not proof that all seven execute in one run.
Scoped alternatives use stream/event waits: CLIP wiring `:1716–1722`, FastSafe
copy readiness `unet_fastsafetensors.py:1789–1806`, and final readiness
`:1948–1953`. They are not counted as global synchronizations.

**Per-slot host waits:** current Golden Serial has two distinct wait sites:
`golden_serial.py:2063–2075` before reusing a worker's slot and
`:2381–2395` for the final outstanding-event drain. Both call
`_wait_event_host_ns` at `:1837–1850`, which calls `event.synchronize()` only
when `query()` is incomplete. `_require_transport_quiescence` at
`:2587–2603` is a proof check, not another sync primitive.

**Header/metadata duplication:** historical direct QD parses the header once
for its transport. Current `read_file_qd_gpu` parses once per transport at
`golden_serial.py:2213–2229`, while separate roles/loaders/fallbacks can each
parse their own input. The source does **not** prove a single duplicate parse
count across a request, so duplicated header/metadata parses are **UNKNOWN**;
no count is invented.

### 4.4 Required versus accidental serialization

Required serialization is the Golden Serial heavy-stage order, CLIP
GPU-critical work before UNET commit, ownership/validation/final readiness
sync, and durable commit after reopened-byte validation. The current executor
order is visible at `golden_serial.py:6811–6829` and is a **TOTAL structural
ordering claim**.

Accidental or avoidable serialization is: UNET source reads coupled to each
worker's previous H2D event; broad device sync where a correctly scoped event
would suffice; and a successful fast path still risking original-loader,
fallback, or duplicate-read work unless its owner/adoption and failure state
are observable. These are candidate improvements, not measured savings.

## 5. CLIP-left-shift design (candidate Golden Overlapped only)

Preserve CLIP as the first GPU-critical lane. After restore/setup, UNET may
prepare source-side state: open source handles, parse/validate immutable
headers, build a range plan, read source bytes, and fill CPU/pinned staging.
The earliest legal overlap point is after restore/setup proves that those
operations touch only source handles/CPU staging. No UNET H2D, pointer adoption,
`.to()`, patcher mutation, device mutation, or GPU commit may occur before the
CLIP GPU-critical completion fence.

UNET GPU commit may begin only after CLIP GPU-critical completion, source
ownership/release proof, all readers joined, and the scheduler grants the
UNET H2D/GPU mutation domains. There is no hidden overlap in Golden Serial;
this is a design for a separately named **Golden Overlapped** path. R41's
encoded structure permits CLIP forward + UNET metadata preparation, but does
not prove the physical overlap or its latency.

## 6. Regression/delta table

The following eleven items are the explicitly enumerated QD/compute-ready
regression or architecture deltas counted in the required return line.

| # | Exact difference | Likely impact | Correctness/lifetime rationale | Safe restoration candidate |
|---:|---|---|---|---|
| 1 | E27 QD4 had four static workers and bounded per-worker staging; current Serial waits a prior slot event before each next read (`golden_serial.py:2063–2075`). | H2D latency can starve source QD and reduce steady throughput. | Reuse is safe only after event completion; current proof is correct but coupled. | Lease/generation slots first; then measure a dispatcher separately. |
| 2 | R41 `GoldenQD4Loader`/`_StagingRing` dispatcher (`2187c5e`, `qd_engine.py:350–510`) is absent from current self-contained Serial. | Removes source/transfer decoupling; physical gain remains unproven. | Dispatcher needs queue drain, producer retirement, cancellation, and ownership. | Reconcile R41 seams and run physical exact-SHA cohort; do not copy code blindly. |
| 3 | E28 FastSafe was an accepted experiment; current dispatch is gated/default-off (`model_preload.py:14114–14161`, production profile); R44F native adoption was ineligible on a BF16/FP16 parity mismatch. | Production does not receive the measured FastSafe path; a matched output can still be degraded/native rather than zero-copy. | Native fallback must be observable and degraded, never mislabeled nominal. | Profile-gated FastSafe after exact source/owner/fallback gates. |
| 4 | E31 cast-once local design exists, but current Golden equivalence/repeated-current proof is unclear. | Per-forward conversion may remain, or FP32 VRAM may be spent without proven gain. | Validity requires dtype/device/patch/parameter/generation/owner predicates. | Re-run synchronized current A/B; prefer ownership transfer, not two copies. |
| 5 | Historical CLIP QD path exists; production profile sets fast hydration/QD off (`production.toml:48–50`); OC2/D12/modern request-FastSafe hydration totals and file→GPU spans are boundary-incomplete. | Production CLIP retains native load cost; modern publication H2D completion is **UNKNOWN** without explicit sync/event proof. | QD must finish, reconcile, and publish before bind; fallback and output validity must be explicit, not inferred from a timing label. | Enable only in a source-matched, exact-SHA profile. |
| 6 | E26 speculative CLIP overlap can join/take an in-flight read; clean lane deliberately reads synchronously (`clip_fast_hydration_wiring.py:1288–1324`); cycle 1 duplicated the full read when its lane was unconsumed. | Source latency shifts into the demand path and can be counted outside the exposed demand timer. | A bounded join is safe only with one owner and a failed-lane fallback. | Restore-time source prepare with explicit join/adopt and no duplicate read. |
| 7 | Old restore owner mismatch was fixed by `RESTORE_ROLE_OWNER_MAP` (`comfyapp.py:1523–1531`). | The prior mismatch could cause duplicate ownership or missed adoption. | Unified identity/lifetime namespace is required. | Keep mapping; add identity assertions, not a timing optimization. |
| 8 | Broad `torch.cuda.synchronize` sites remain beside scoped event alternatives. | Device-wide waits can serialize unrelated work. | Scoped waits are valid only with a recorded event and stream ordering proof. | Instrument both arms and replace only after device-ready exactness proof. |
| 9 | Historical header-once QD versus multiple current role/loader boundaries. | Possible parse overhead or inconsistent metadata ownership. | A header may be reused only as immutable, identity-keyed metadata. | Request-scoped immutable header/plan ownership, with parse-count telemetry. |
| 10 | Current clean lane has explicit join/coverage/owner publication and native reset/fallback (`:1319–1442`, `:2004–2048`); older paths could hide fallback. | Timings can describe a fallback or duplicate read while labeled fast. | Fallback must fail closed and never be acceptance-nominal. | Require execution identity, fallback=0, source/H2D byte reconciliation, and owner proof. |
| 11 | Golden Serial has no hidden overlap; proposed CLIP-left-shift/Golden Overlapped is not current runtime. | Safe overlap opportunity is currently unrealized. | GPU mutation and UNET H2D must wait for CLIP critical completion. | Add explicit scheduler states and fences, then measure full entry→return. |

## 7. Proposed RA9 experiment matrix — design only, do not run

These are proposals, not executed work. Ratings are qualitative evidence-based
priorities, not historical performance claims.

### 7.1 Separate experiment families

**Family P — shared pinned pool (memory/lifetime experiment):** implement a
request-scoped lease pool, initially serial-exclusive. Use eight 32 MiB slots
(268,435,456 bytes), with capacity classes keyed by block size, pin policy,
and device/NUMA placement. Keep each role's CUDA backing owner separate. Pool
return requires joined producers, every H2D event complete, queue/callback
retirement, exact reconciliation, and locked lease transition. Poison the
pool/request on uncertain state. This can reduce allocation/page-lock churn and
serial peak from approximately three retained owners (up to 805,306,368 bytes)
to one pool, but **does not prove throughput gain**.

**Family D — transfer dispatcher (throughput experiment):** separate source
workers from H2D issue/reap using a bounded ready queue and ring. A source worker
must never inspect a completion event; only bounded-ring backpressure may block
it. This is the R41 structural idea, but it is unsafe until transaction owner
registration, cancellation/error draining, queue retirement, slot poisoning,
and adoption reconciliation are implemented. It must not be merged into Serial
as an unmeasured “optimization.”

| Rank | Experiment arm | Latency gain | Correctness risk | Complexity | VRAM/pinned cost | Likelihood based on evidence |
|---:|---|---|---|---|---|---|
| 1 | P0 serial-exclusive lease pool, no dispatcher | Low/unknown; allocation churn only | Low if quiescence is mandatory | Medium | 256 MiB pinned bound | Medium for memory hygiene, low for latency |
| 2 | D0 dispatcher with 8-slot ring, QD4, no CLIP/UNET overlap | Potentially high if event coupling explains E39 1.63 GB/s steady rate | High | High | 256 MiB pinned plus same CUDA destination | Plausible mechanism; physical gain unknown |
| 3 | P1 pool + explicit two-role admission, still serial | Low/unknown | Medium | Medium/high | 512 MiB if two full QD4 leases | Medium for future capacity, not throughput |
| 4 | D1 dispatcher + P1, CLIP-first then UNET source prepare | Potentially highest critical-path gain | Very high | Very high | Explicitly budgeted multi-transport capacity | Candidate only; no historical causality |
| 5 | Scoped event/readiness arm versus broad sync control | Unknown to modest; could remove unrelated waits | Medium | Medium | No model-sized copy; event bookkeeping | Plausible but requires device-semantic proof |
| 6 | Current FastSafe/cast-once exact current A/B control | Unknown; C9 pipeline was 2743.40 ms and E31 remote equivalence unclear | Medium/high | Medium | Cast-once adds about 8 GB GPU if enabled | Must be measured, not inferred |

### 7.2 Boundary-safe instrumentation and acceptance gates

Every arm must record, on one monotonic axis:

1. function-entry to function-return wall, without pre-timer work or omitted
   first pass; restore/setup, header/config, source open, source reads, staging,
   H2D issue, H2D completion, construction, bind/adoption, validation, owner
   publication, demand handoff, final sync, and post-timer sync boundaries;
2. source/header parse count and identity; exact source bytes/read count;
3. H2D submitted and completed bytes, per-slot generation, event wait wall,
   queue depth, occupancy, free slots, backpressure, and dispatcher/worker
   retirement;
4. owner identity, owner state, backing storage pointer identity, owner
   lifetime through first consumer use, and staging release proof;
5. device-ready only after final required synchronization/event ordering;
6. execution identity, fallback count/reason, native reread count, duplicate
   owner/read count, and validation/adoption result;
7. full stage wall from function entry through return, with no first-pass
   omission, pre-timer setup omission, or post-timer synchronization hidden.

Acceptance requires all of the following for a nominal result: source-matched
remote physical evidence; the currently resolved, source-matched canonical
output SHA; no fallback; one source/header ownership record; exact read and H2D
byte reconciliation; one owner identity with proven lifetime; device-ready
after the final fence; and a full entry→return wall. C9's
`20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260` is C9
artifact evidence only, not a universal current acceptance SHA. Archaeology
records a canonical-output conflict: `golden_serial.py` has
`8a9244...`, the Golden plan has `20b10e...`, the operations skill has
`454dbd...`, and RA2B observed `bfb360...`. Until that conflict is resolved
against the current source, current cohorts are **UNKNOWN/BROKEN**, not
acceptance-valid. A timing with a matched SHA but failed deployment,
provenance, readback, fallback, or loader/adoption proof is not acceptance-valid.
A local synthetic dispatcher result is structural only. A cohort must separately
report cold state, region/provider, source wall, aggregate and steady GB/s,
time-weighted occupancy, H2D wait, backpressure, and all degradation records.

## 8. Final findings

1. No proven historical complete UNET load in the **1–1.5 s** range exists.
   E27 is a transport probe; C9 is a complete named FastSafe pipeline but
   2743.40 ms and missing demand handoff; E28 totals are fence-contaminated;
   E37 is CPU-snapshot demand movement; current Golden's 1.804 s observation
   failed output-SHA acceptance.
2. The fastest useful QD4 numbers are real transport/source capabilities, not
   compute-ready residency proof. The missing boundary is not cosmetic: model
   construction, assign/adoption, final validation, owner retention, and the
   serialized sampler handoff determine whether the model can safely be used.
3. R41's dispatcher is a credible structural answer to one coupling mechanism,
   but it has no physical total before/after proof and has unresolved ownership
   and failure-drain seams. A shared pool is safer as the first experiment, but
   is a memory/lifetime optimization, not a throughput conclusion.
4. Current Golden Serial deliberately exposes a strict order and quiescence
   proof. Any overlap must be a separately gated Golden Overlapped design with
   explicit ownership and exact output acceptance.

RA9B_COMPLETE=YES
HISTORICAL_UNET_1_TO_1_5S_EVIDENCE=UNPROVEN
FASTEST_VALID_UNET_LOAD_MS=UNKNOWN
FASTEST_VALID_CLIP_LOAD_MS=UNKNOWN
FASTEST_VALID_CLIP_FORWARD_MS=UNKNOWN
REPEATED_CAST_CURRENT_STATUS=UNPROVEN
QD_REGRESSIONS_IDENTIFIED=11
GLOBAL_SYNCS_IDENTIFIED=7
RA9_EXPERIMENT_MATRIX_READY=YES
REPORT=RA9B_QD4_COMPUTE_READY_RESIDENCY_ARCHAEOLOGY_REPORT.md
