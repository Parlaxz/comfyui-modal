# V2 Pre-Python Snapshot Regression — Reconstruction, Static Diff, Manifests, and Same-Image A/B Plan

> Work performed directly on `main` at HEAD `36ad995` (working tree was clean).
> No branches, worktrees, or subagents were used.  No paid Modal deployment or
> run was performed.  This report stops before the approved-bounded-experiment
> gate and asks for approval to execute the A/B in §5.

## 0. Bottom line

1. **The historical pre-Python boundary is reconstructed from raw artifacts,
   not from the report's differently-named summary metrics.**  On the same
   exact boundary (command/submission → `restore()` first line), the preserved
   08-05 runs show **18 cold draws at 2.6–4.5 s** (best 2.62 s) — matching the
   task's "approximately 3–4 seconds" — while tonight's 08-06 runs drew
   **6.8–21.6 s** on every valid cold run.  The report's historical
   "0.18–0.38 s first-event" values are a *different* boundary (first remote
   event emitted after resume) and are **not** equivalent to
   submission → remote_python_resume; they are excluded from this analysis.
2. **The snapshot-producing code (startup `snap=True` path and the entire
   import-time surface) is statically *nearly identical* between the last-fast
   image and current `main`.**  The audit found:
   - No new module-level threads, executors, registries, caches, or retained
     model references at import time (verified by module-level scan of every
     runtime module and the diff of module-level executed statements).
   - `VAE_SNAPSHOT` and runtime-shape (TBASE/O0) wiring were **already active
     in the last-fast image** (`6547496`, 08-05 18:43 — contains
     `_load_cpu_snapshot_vae`), so they are **not** the regression.
   - All 08-06 additions (exclusive ownership, rehoming, page-path, backing,
     host diagnostics, variance, quiesced transfer, waterfall stages) are
     request-time gated and add nothing to the captured snapshot — except the
     `unet_backing` **module import itself** (import-clean; 2 constants) and
     tiny module-level constants.
3. **The strongest code-side correlate of the regression is therefore the
   *image/snapshot identity churn per deploy*** — every 08-06 deploy rebuilt
   the image (3 new source modules: `unet_backing.py`, `thread_cpu_sampler.py`,
   `rehoming_experiment.py`, plus code additions), creating a brand-new
   snapshot identity, while the fast era reused a days-old image/snapshot
   identity.  This is the mechanism by which "image age" appeared to correlate
   with scheduling; it is confounded with code, which is exactly why the
   same-image A/B in §5 is the decisive test.
4. **Tooling added (all default-off):** snapshot-build manifest capture
   (`COMFYMODAL_V2_SNAPSHOT_MANIFEST=1`) at pre-capture and first-restored-line
   boundaries, an immediate-return `run_entry_probe` remote method, and a
   lean-snapshot gate (`COMFYMODAL_V2_LEAN_SNAPSHOT=1`) that reproduces the
   last-fast import surface.  Local tests: **52 passed** (11 new + 41 related).

## 1. Historical boundary reconstruction (same exact boundary)

### 1.1 Boundary definition

The metric under study is **submission → first Python line of `restore()`**
(= pre-Python Modal scheduling + snapshot restore).  In the current format it
is `total_wall_stages.stage_modal_scheduling_ms`; in the 08-05 artifact format
it is `timing.command_start_to_restore_start_ms` (command start → restore
start).  Both are local-wall → remote-restore-first-line deltas, so they are
the same boundary family.  The report's "first-event" column
(`submission_to_first_remote_event_ms`-style) measures the first remote trace
event **after** Python resumed and is systematically smaller; it is not the
pre-Python stage.

### 1.2 Preserved raw distribution (08-05, same boundary)

Extracted from every preserved `run_0.json` under
`C:\Users\parla\.config\superpowers\worktrees\comfymodal-data\benchmarks\runs`
(app `stable-modal-comfy-v2-shadow`, TBASE/O0, CPU 16 / 49152 MiB):

| metric | value |
|---|---:|
| cold runs with cmd→restore measured | 132 |
| min (best draw) | **2.62 s** |
| draws < 5 s | 29 (22 %) |
| draws 2.5–4.5 s ("historical 3–4 s" band) | **18** |
| median of all 132 | 7.43 s |
| max (snapshot-rebuild runs) | 190.98 s |

The task's "historical ≈ 3–4 s" is exactly the fast tail of this distribution;
the fast era repeatedly drew that band.  Tonight's 08-06 runs drew **6.8–21.6 s**
on all 6 valid cold runs (attempts preserved in
`%LOCALAPPDATA%\comfymodal-data\benchmarks\runs\v2_2026-08-06_22-49-13_ownership`
… `23-06-21_ownership`).

### 1.3 Last known-good snapshot configuration (reconstructed)

| axis | value | source |
|---|---|---|
| commit at image build | `6547496` (08-05 18:43) / `8faa106` (16:17); fast 05:56 session ≈ `18fbe2b`/`25b8562` (08-05 23:09–23:11) | git log dates vs artifact times |
| app | `stable-modal-comfy-v2-shadow` (07-26 lineage) / `stable-modal-comfy-v2-variance-shadow` | report §2 + run identity |
| image | `im-DIhSnbyohJ7y4zku8oiWVY`, `im-19DF7wXDBXML1Blz0gZH9g`, 05:56 session transfer image | report §2, V2_TRANSFER_AND_PLATFORM_GAP_REPORT |
| env profile | production; `CPU_MODEL_SNAPSHOT=1`, `VAE_SNAPSHOT=1` (bat since 08-03 `e28192f`), CLIP cache on, `UNET_ACTIVATION_MODE=late`, `VAE_ACTIVATION_MODE=sampling_end` | bat at `6547496` (verified) |
| runtime shape | TBASE / O0, CPU 16, memory 49152 MiB, `enable_memory_snapshot=True` | run identity + `_resolve_enable_memory_snapshot` |
| provider/region | unpinned (fast era); 05:56 session region-pinned us-east4 | reports |
| snapshot capture path | `startup(snap=True)` → `load_cpu_snapshot_models` (UNET+CLIP+VAE on CPU, `DISABLE_MMAP=True`) → `_close_snapshot_build_pools` → pre-import CacheDiT family → return | code at `6547496` (verified identical to current) |
| imports before capture | `comfymodal_runtime.*` incl. `variance_diagnostics` (import-clean); **no** `unet_backing`, `thread_cpu_sampler`, `rehoming_experiment` | module-level diff `6547496` vs current |
| retained models at capture | UNET + CLIP + VAE CPU tensors (`self._cpu_snapshot_models`) | startup code |
| native threads at capture | torch thread policy applied; no sampler threads (all request-time) | `ThreadCpuSampler` instantiation sites |

### 1.4 What changed between last-fast and current (import-time, captured)

Module-level executed-statement diff (`6547496` → `36ad995`):

| module | new module-level items | captured? |
|---|---|---|
| `modal_app.py` | `from .unet_backing import (…)` (4 names), `_REGION_PIN_ALLOWLIST`, `_CLOUD_PIN_ALLOWLIST` | yes (module import + 2 frozensets) |
| `model_preload.py` | `from .unet_backing import (…)` (10 names), `_GRAPH_JOIN_TIMEOUT_S`, `_QUIESCE_WAIT_TIMEOUT_S`, `_QUIESCE_STATE_POLL_S`, `_OWNERSHIP_EMIT_GATE=False` | yes (module import + 4 constants) |
| `unet_backing.py` (new) | `_SYNTH_H2D_BYTES`, `_PAGE_SIZE_CACHE=0` | yes (import-clean) |
| `thread_cpu_sampler.py` (new) | constants only; thread starts only in `ThreadCpuSampler.start()` (request-time gated) | no (never imported at module level) |
| `rehoming_experiment.py` (new) | none at module level | no (lazy import in method) |
| `variance_diagnostics.py` | unchanged module-level surface | already present in last-fast image |

**Verdict:** the captured snapshot composition changed only by the
`unet_backing` module import (2 constants, no side effects) plus tiny
constants — not by threads, executors, registries, or retained storage.  The
startup(snap=True) path is unchanged in structure and in retained models.

## 2. Ranked suspects (by mechanism: captured RSS / mappings / threads / restore metadata)

| rank | suspect | mechanism | strength |
|---|---|---|---|
| 1 | **Snapshot identity churn per deploy** (image rebuilds: 3 new source modules + code additions → new image layers → brand-new snapshot each deploy; fast era reused a days-old image) | Modal restore/scheduling treats new snapshot identities differently (cache/pool affinity); this is the mechanism underlying the observed "image age" correlation | **strong — primary candidate**; directly testable by the same-image A/B §5 |
| 2 | **`unet_backing` module-level import** (only true code-side capture delta) | +1 module, +1 mapping, tiny constants in captured snapshot | weak-moderate; isolated by lean arm B |
| 3 | Module-level constants (`_REGION_PIN_ALLOWLIST`, `_CLOUD_PIN_ALLOWLIST`, ownership/quiesce constants) | negligible bytes; negligible mappings | weak |
| 4 | Exclusive ownership / rehoming / page-path / backing / host-diag / variance / quiesced / waterfall request-time machinery | request-time gated OFF; nothing retained at capture | **excluded by static evidence** (still measured by manifest to confirm) |
| 5 | VAE snapshot retention | present in last-fast image too | **excluded** |
| 6 | Runtime-shape thread policy (TBASE/O0) | present since 08-04, in last-fast image too | **excluded** |
| 7 | `_WATERFALL`/`_POST_DELIVERY` module singletons | present since 07-09 | **excluded** |

Decision rule (from the task): if lean arm B ≈ current arm A, the culprit is
snapshot identity / image composition (suspect 1), and the next controlled
comparison is **historical snapshot composition vs current composition** —
never "wait for the pool."

## 3. Snapshot-build manifest tooling (default OFF)

New module `comfymodal_runtime/snapshot_build_manifest.py`, gated by
`COMFYMODAL_V2_SNAPSHOT_MANIFEST=1` (never enabled on measured latency runs).

Captures at each boundary (JSON-safe, bounded, never raises):

- RSS / VmHWM / VmSize / VmData / Threads (`/proc/self/status`)
- `/proc/self/smaps_rollup`
- mapping totals: total / anonymous / file-backed, top 60 paths by count
- imported module names (up to 4000)
- native thread count (`/proc/self/task`) + Python thread names (64)
- child processes (up to 32)
- open FDs: total + top 40 targets by `readlink`
- Torch intra/inter-op thread settings
- retained CLIP/UNET/VAE identities + storage bytes (from `_cpu_snapshot_models`)
- registered global executors/futures (module scan, bounded 32)
- GC object counts + top-24 type histogram
- Modal class/image/resource identity (image id, cloud, region, app, container session)

**Hook points** (both inside `comfymodal_runtime/modal_app.py`, gated):

1. `startup(snap=True)` — immediately before the snapshot-capture return
   (`before_capture` stage), after `_close_snapshot_build_pools` and model
   eviction logic.
2. `restore(snap=False)` — at the TRUE first executable line of `restore()`,
   immediately after `remote_python_resume_wall_ns` (`first_restored_line`).
3. `run_entry_probe` — optional `entry_probe` stage for the A/B.

Manifests are printed as `[v2.snapshot_manifest]` lines and stored in
`latest_manifests()` for offline diffing.  Local example (Windows host, `/proc`
absent — degrades gracefully; on Modal Linux it is fully populated):

```
[v2.snapshot_manifest] stage=before_capture rss_kb=None hwm_kb=None vmsize_kb=None mappings=None anon=None file=None native_threads=None py_threads=1 modules=101 fds=None children=0 gc_objects=155470 executors=0 image= cloud= region=
```

## 4. Files changed (this session)

| file | change |
|---|---|
| `comfymodal_runtime/snapshot_build_manifest.py` | **new** — default-off manifest capture module |
| `comfymodal_runtime/modal_app.py` | pre-capture + first-restored-line manifest hooks (gated); `run_entry_probe` method + registration (`_METHODS_TO_WRAP`, `_modal.method()`); lean-snapshot gate with stubs; `COMFYMODAL_V2_SNAPSHOT_MANIFEST`/`COMFYMODAL_V2_LEAN_SNAPSHOT` env passthrough + probe keys |
| `comfymodal_runtime/model_preload.py` | lean-snapshot gate with behavior-identical stubs for the 10 `unet_backing` names |
| `tools/run_ownership_rehoming_study.py` | new `snapshot-ab` mode: env assertion (incl. lean/manifest gates) + `run_entry_probe` N times, `submission_to_entry_wall_ms`, per-attempt artifacts, summary; new `--arm/--expect-lean/--expect-manifest` args |
| `deploy_and_run_ownership_rehoming.py` | new `snapshot-ab` mode: deploy arm current/lean (same image lineage, region-pinnable, `--no-deploy`/`--deploy-only`/`--manifest`) + study wiring |
| `tests/test_v2_snapshot_build_manifest.py` | **new** — 11 tests (gating, full-surface JSON-safety, retained-model capture, mapping bounds, lean-gate stubs via subprocess isolation) |

**Tests:** `python run_tests.py tests.test_v2_snapshot_build_manifest tests.test_v2_waterfall tests.test_v2_unet_early_activation` → **52 passed**.
The 22 failures in `test_v2_observability_instrumentation` are pre-existing at
HEAD (verified identical on a clean checkout via stash).

## 5. Decisive same-image A/B — proposed protocol (NOT yet run)

> **Stop here for approval.**  This section is the bounded experiment plan;
> nothing in it has been executed.

### 5.1 Design

One deployment per arm, **same `modal.Image` (same code revision, same
`V2_SOURCE_MODULES`, same base image), same resources (RTX PRO 6000, CPU 16,
memory 49152 MiB, TBASE/O0), same provider/region (region-pinned us-east4,
GCP), same test window, interleaved**.  Arms differ only in deployment env:

- **Arm A — current snapshot composition:** `LEAN_SNAPSHOT=0`, ownership ON,
  all diagnostics OFF (production default path, exactly what ran tonight).
- **Arm B — lean production snapshot:** `LEAN_SNAPSHOT=1` (defers the only
  new import-time module, reproducing the last-fast import surface), ownership
  ON, all diagnostics OFF.

Both arms expose `run_entry_probe` (literal-first-line timestamp, immediate
return) and optionally `run_env_probe` (gate assertion) and the manifest
hooks (composition evidence only, not on measured probes).

### 5.2 Commands (after approval)

```bat
rem Arm A (current composition)
python deploy_and_run_ownership_rehoming.py snapshot-ab current --region us-east4
rem Arm B (lean composition) — same image lineage, env differs
python deploy_and_run_ownership_rehoming.py snapshot-ab lean --region us-east4
rem Composition evidence (excluded from latency): repeat with --manifest
python deploy_and_run_ownership_rehoming.py snapshot-ab current --region us-east4 --manifest --no-deploy
python deploy_and_run_ownership_rehoming.py snapshot-ab lean --region us-east4 --manifest --no-deploy
```

Each arm: container env assertion (abort on mismatch) → skip-first 2
(snapshot builder + immediately following) → **3 valid entry probes**, 25 s
gaps, 6 max attempts.  Primary comparison: `submission_to_entry_wall_ms`
per arm.  No full image-generation calls until the entry winner is known.

### 5.3 Attempt budget (paid)

| item | count | est. cost each |
|---|---:|---:|
| arm A deploy (image likely cached from tonight) | 1 | ~1–3 min build if cache miss |
| arm B deploy (env-only diff; image content identical → cache hit) | 1 | ~0 |
| entry probes arm A (2 excluded + 3 valid, max 6) | ≤6 | ~1 cold container each |
| entry probes arm B (same) | ≤6 | ~1 cold container each |
| manifest composition runs (2 per arm, `--no-deploy`) | ≤4 | ~1 cold container each |
| **total cold requests** | **≤22** | ~13.5 s ceiling each |

Early stop: abort an arm after 2 valid probes ≥ 13 500 ms on `run_entry_probe`
round-trip is not the gate — the gate is the entry delta; stop after 6
attempts or 3 valid probes per arm, whichever first.

### 5.4 Decision rules

- **Lean wins** (B returns near the historical 3–4 s band and clearly beats
  A in the same window): make the production snapshot path lean by default;
  preserve diagnostics outside the snapshot; then 3 controlled full cold
  generations, then the final 6 unpinned cold generations (gates: 6/6 ≤ 13.5 s,
  median ≤ 12.5 s, pre-Python ≤ 3.5 s pref / none > 4.5 s, post-Python ≤ 9.5 s,
  join ≤ 1 s, exactly one migration, all ownership/correctness invariants).
- **Both arms equal:** suspect 1 confirmed (snapshot identity/image
  composition); next controlled comparison is historical snapshot composition
  (reuse of the last-fast image lineage) vs current composition — not pool
  luck.

## 6. Final SHA

Work is uncommitted on `main` at HEAD **`36ad995`** (clean before this
session).  Staged/working changes: the 4 modified + 2 new files in §4.
Final SHA to be recorded after user review/commit approval.

## 7. Remaining uncertainty

1. The 05:56 fast session's exact image/commit cannot be recovered from disk
   (run dirs deleted); its code state is inferred as `18fbe2b`/`25b8562`-era
   from commit timestamps.  The A/B does not depend on this inference.
2. Cross-process wall-clock reconciliation (local submission vs remote entry)
   has sub-100 ms skew risk; the same technique is used in every historical
   and current run, so A-vs-B comparison is unaffected.
3. Manifest capture on `/proc`-less hosts degrades to `None`; on Modal Linux
   containers it is fully populated — composition evidence must come from the
   remote container, not the local test host.
