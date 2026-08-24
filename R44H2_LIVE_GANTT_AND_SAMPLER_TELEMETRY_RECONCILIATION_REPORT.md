# R44H2 — Live Dynamic Gantt Integration and Sampler/Post-Sampling Telemetry Reconciliation

Batch: R44H2 · Lane: OBSERVABILITY RECONCILIATION ONLY · Worktree `../comfyui-modal-r42` · Branch `r42-golden-reconciliation` · HEAD `0c59f46e3238f421378e8852ebc548da815b70af` (unchanged; no commits/push/merge/reset/revert/clean/stash)
No deploy. No Modal run. No paid request. No runtime/model-path behavior change.
Authorities consumed in full: `R44G1_DYNAMIC_GANTT_AND_TELEMETRY_REPORT.md`, `comfymodal_runtime/dynamic_gantt.py`, `tools/render_dynamic_gantt.py`, `tests/test_r44g1_dynamic_gantt.py`, `R44G3_SAMPLER_AND_POSTSAMPLING_FORENSICS_REPORT.md`, `R44G2_MODEL_TRANSFER_THROUGHPUT_FORENSICS_REPORT.md`, `R44E_FASTSAFE_FULL_EVIDENCE_AND_DECOMPOSITION_REPORT.md`, `R44F_CLIP_ZERO_COPY_ADOPTION_REPORT.md`.

---

## 1. G1 integration point chosen — and why it is non-critical-path

**Chosen point:** `tools/benchmark_v2_direct.py`, inside `_run_one(...)`, immediately AFTER the per-run artifact is committed to disk (`run_<index>.json` write + full-trace handoff block). A best-effort block calls the NEW `render_artifact_file(output_dir, f"run_{index}.json")` and writes `dynamic_gantt_run_<index>.txt` next to the artifact, printing one bounded pointer line with the measured host-side render cost. Any failure prints `[v2.dynamic_gantt] render skipped: …` and never affects the run.

**Why non-critical-path:** rendering happens host-side, post-artifact, on already-persisted JSON. Zero remote execution time is spent rendering log lines (the batch's preferred principle); the remote request path is untouched. Raw structured artifacts remain the source of truth; the dynamic report is a derived view. Per-run file naming (`dynamic_gantt_run_<index>.txt`) keeps multi-run campaigns unambiguous. Supporting API addition: `load_run_artifacts(run_dir, run_file=None)` (backward compatible) + `render_artifact_file()`.

Every benchmark run now automatically produces: raw artifacts (unchanged) → legacy waterfall (retained) → **V2 DYNAMIC CRITICAL PATH GANTT** → closure reports → completeness matrix → critical-path summary + new STAGE SUMMARY, all in `dynamic_gantt_run_<index>.txt` and reproducible via `python tools/render_dynamic_gantt.py <run_dir>`.

## 2. Files / functions changed

| File | Change |
|---|---|
| `comfymodal_runtime/sampler_telemetry.py` | **NEW.** Request-scoped boundary recorder: node entry / true sampling_start / first eval / per-step ticks / tail closure; guarded window-bounded sub-timing patches (`gc.collect`, `copy.deepcopy`, `Tensor.cpu`); `load_models_gpu` seam stamps + caller classification; `resolve_sampling_start()` backfill resolver; `emit_durable_events(trace)` one-shot emitter. Env kill-switch `COMFYMODAL_V2_SAMPLER_TELEMETRY=0`. |
| `comfymodal_runtime/runtime_executor.py` | `_build_sampling_wrapper._wrapper`: mirrors `sampling_start`/`sampling_end` into the telemetry store; `_step_callback`: per-step tick note (every callback). `_patched_load_models_gpu`: R44H2 seam — mono stamps for EVERY call incl. the post-cutoff VAE call; when the caller is the sampler's internal model-management call, idempotently re-installs `ensure_sampling_timing_wrapper` + `register_unet_forward_probe` on the EXACT patcher about to be sampled. `_CpuTimer`: additive `start_mono_ns`/`end_mono_ns`/`caller` record fields (parseable line format unchanged). `_patched_exec_node` finally: closes the tail at TRUE node return (`_t_end`, never cutoff-clipped) and emits durable events via `_ACTIVE_REQUEST_TRACE`. |
| `comfyapp.py` | `_begin_profiled_node` (sampler branch): mono/perf entry stamps + `note_sampler_node_entry`. `_note_progress_event`: mono stamps + wrapper-independent tick feed. `_finish_profiled_node` (sampler branch): tail close + true-mono stash into stage windows. |
| `comfymodal_runtime/modal_app.py` | pre-sampler stages assembly: tracks whether the durable `sampling_start` event was found; adds store fallback (TRUE sources only); new additive key `sampling_start_source` ∈ {`authoritative_wrapper`,`proxy_first_progress`,`wrapper_runtime_store`,`unavailable`} in BOTH pre_sampler_stages payloads. Existing keys untouched. |
| `comfymodal_runtime/v2_waterfall.py` | `sampler_node_to_sampling` resolution: TRUE `sampling_start` event first; metadata interval second; progress-derived `sampler_start` fallback retained but explicitly annotated `source_fields += ("proxy:first_progress_callback_not_true_sampling_start",)` (frozen-dataclass-safe via `dataclasses.replace`). |
| `comfymodal_runtime/gantt_telemetry.py` | Legacy output warning: `render_gantt_trace` / `render_gantt_windows` append, adjacent to any render containing the legacy span: `WARNING: LEGACY "CLIP forward" = outer encode wrapper (NOT the inner transformer forward); use DYNAMIC GANTT for inner transformer forward.` (two lines, ≤100 cols to honor e27 width contract). Persisted span NAME unchanged (schema stability; `test_e27_gantt_telemetry.py:85` consumer intact). |
| `comfymodal_runtime/unet_forward_probe.py` | One guarded hook: where `unet_first_cuda_op` is emitted, also feeds `sampler_telemetry.note_first_eval()` (first UNDERLYING denoiser evaluation ≠ first progress callback). |
| `comfymodal_runtime/dynamic_gantt.py` | Registry/renderer/completeness extensions (§8–§10 below); `load_run_artifacts(run_file=)`; `render_artifact_file()`; `stage_summary()`. |
| `tools/benchmark_v2_direct.py` | Integration block (§1). |
| `tests/test_r44h2_sampler_telemetry_gantt.py` | **NEW**, 16 tests covering spec items A–J. |
| `tests/test_r44g1_dynamic_gantt.py` | Three expectation updates REQUIRED by the H2 spec (documented in §11): `"sampling"` row label → `"progress sampling"`; legacy interval assertion → PROXY label assertion; empty-payload MISSING count 17 → 27. All other G1 semantics untouched; 17/17 green. |

Forbidden areas untouched: `request_clip_fastsafe.py`, CLIP construction/adoption logic, CLIP dtype selection, FastSafe transport, UNET loading/adoption behavior. The lmg-seam re-install is telemetry-only (idempotent wrapper/probe registration that already existed elsewhere); it changes no loading or adoption decision.

## 3. True sampling_start persistence (R44G3 item 1)

R44E root cause (artifact-verified): `sampling_start` 0 hits, `first_sampler_step` 0, `unet_first_cuda_op` 0 in `run_0.json`, while `clip_forward_end`/`vae_decode_start`/`sampler_lane_wait_start` persisted ⇒ the entire patcher-attached instrumentation family missed because the FastSafe/adoption-era sampling patcher is not the object wrapped at load time (comfy resolves SAMPLER_SAMPLE wrappers from a clone of the guider's model_options at `samplers.py:1220-1229`; a fresh post-load patcher carries none).

Fix (defense-in-depth, no forbidden edits):
1. **Seam re-install** — SharkSampler.main itself calls comfy `load_models_gpu([diffusion model])` ~100 ms before `guider.sample`; our existing `_patched_load_models_gpu` sees that exact patcher and idempotently installs the SAMPLER_SAMPLE timing wrapper + first-forward probe there. Wrapper then fires at `guider.sample` entry ⇒ `sampling_start` lands BEFORE the deep sampler call, durably, in `result.trace.events`.
2. **Request-scoped store** — the wrapper's emission is mirrored into `sampler_telemetry`; `resolve_sampling_start()` prefers trace event → store → milestone proxy (labeled).
3. **Backfill** — `pre_sampler_stages.sampling_start_monotonic_ns` populated from the authoritative event whenever it exists (never invented, never first-progress), plus new `sampling_start_source` provenance key; waterfall consumes it via the existing metadata-interval candidate.

## 4. Sampler event architecture (R44G3 items 2–5)

All timestamp-only; no added sync anywhere.

| Event | Boundary | Key fields |
|---|---|---|
| `sampling_start` (existing, now durable) | wrapper entry before deep sampler call | mono_ns, node_id, steps, request_id (+ sigmas_len, latent dtype/device, default_dtype best-effort) |
| `sampler_prep_phase` | sampler NODE entry → true sampling start (= SharkSampler.main-entry→pre-`guider.sample` equivalent) | start/end mono, wall_ms, dtype/default_dtype, sigmas_len, latent dtype/device, ids |
| `sampler_first_eval_start` | first underlying denoiser evaluation (fed by the probe's first-CUDA-op hook) | mono_ns, node_id, step_index=0 |
| `sampler_step_ticks` | ONE compact event per request | count + `steps:[{i,mono_ns,progress}]` (lower overhead than 8 events; dual-fed from wrapper callback AND comfyapp progress so it survives even without the wrapper) |
| `sampler_tail` | last progress callback → sampler NODE return (closed at exec-node finally using true `_t_end`) | start/end mono, wall_ms + sub-timings below |

Stage semantics reported (spec §7 names): `sampler orchestration/prep` → `first-eval startup` → `first-step latency` → `progress sampling` → `RES4LYF sampler post-loop tail`. Without a true start, the legacy interval renders as `sampler node→first progress (PROXY — incl. prep + first step)` — never a bare "sampler startup".

## 5. Sampler-tail sub-timing architecture (R44G3 item 9)

Window-bounded, fail-safe host timers installed when the sampler-context `load_models_gpu` seam fires and removed at tail close (idempotent; first close wins):
`gc_collect_ms/_count` (wraps `gc.collect`), `state_info_deepcopy_ms/_count` (wraps `copy.deepcopy`), `cpu_transfer_wall_ms/_bytes/_count` (wraps `Tensor.cpu` — times the ACTUAL call; `.cpu()`'s implicit synchronization belongs to the call, NO second synchronize added), plus derived `subtiming_other_ms = wall − (gc+deepcopy+cpu)`. Each wrapper accumulates only its own call duration under the module lock ⇒ no double counting (unit-tested, including nested-call and double-finish cases).

## 6. VAE CPU-owner enrichment (R44G3 item 6)

`_CpuTimer` records now carry `start_mono_ns`/`end_mono_ns`; `_patched_load_models_gpu` sets `caller` from the live node context (`VAEDecode` → `caller="vae_decode"`, sampler-class → `caller="sampler_prep"`). Additionally, the POST-CUTOFF early-return path — which previously dropped the VAE-decode `load_models_gpu` entirely whenever the wrapper fired — now still persists mono stamps + wall into the telemetry store, so `vae_load_models_gpu_ts` exists in every run. Pre-sampler metric-clipping semantics are unchanged.

## 7. Console-ring outcome — DEFERRED

Existing infrastructure is host-side only (`tools/v2_control/backend.py` `console_capture`, currently null): it captures LOCAL runner console, not container stdout. The R44G3 gap is REMOTE stdout around the sampler window (e.g. `CacheDiT Transformer class: NextDiT`). Capturing it safely requires a process-wide stdout/stderr tee inside the remote runtime — an invasive change to shared logging paths owned by concurrent dirty edits (modal_app/comfyapp), with real risk to the terminal-handoff path. Per the batch's explicit allowance, **item 7 is deferred, documented, and does not block items 1–6.**

## 8. Dynamic Gantt registry changes

* New canonical rows (exact children of new `Sampler node` container): `sampler orchestration/prep`, `first-eval startup`, `first-step latency`, `progress sampling` (relabelled from bare `sampling`), and `RES4LYF sampler post-loop tail` (exact child of broad `post-sampling transition`, kind now `broad` parent/proxy per §8 of the spec) + `executor dispatch → VAEDecode` derived row when the gap is measurable (>0–5 s window).
* Overlap/nesting safety: detailed rows nest under containers; the broad post-sampling parent coexists with the exact tail child; union-based critical totals never sum overlapping rows; new event names added to `_CONSUMED_EVENT_ALIASES` so they can never double-render as `(unregistered)` duplicates.
* Legacy interval (no true start): PROXY-labeled row with `meta.proxy=True`.
* R44F structural facts: `clip_fastsafe_skip` renders as a point row carrying reason/detail; header now prints RuntimeStatus DEGRADED (+reasons), per-role `loader observed status: <role>=UNOBSERVED`, and an explicit note that with the arm skipped, CLIP rows describe the FALLBACK native path — not zero-copy adoption. No future R44H1 event names hardcoded; unknown events still flow through dynamic discovery.

## 9. Completeness matrix extension

Added entries (each PRESENT or MISSING with exact expected key + closest proxy): `sampling wrapper start (true)`, `sampler prep phase`, `first eval start`, `first progress`, `per-step ticks`, `sampler tail`, `tail GC split`, `tail deepcopy split`, `tail CPU transfer split`, `VAE load_models_gpu mono timestamps`. Existing `sampler-start decomposition` / `post-sampling decomposition` flip to PRESENT when the new evidence exists. Empty-payload MISSING count 17 → 27 (G1 test updated accordingly).

## 10. Critical-path summary improvements

New `stage_summary(payload, rows)` section appended to every full report:

```
CLIP    loader / model-device prepare / inner transformer forward / outer encode wrapper
UNET    source prep activity (+ computed uncovered contribution = wall − overlap) /
        exact transfer / adoption / broad H2D window
SAMPLER node entry → true sampling_start … post-loop tail   (legacy interval shown as [PROXY …])
VAE     loader / decode / load_models_gpu (caller=vae_decode)
```

Boundary semantics are printed inline; no agent needs to reverse-engineer t6 again.

## 11. Local test counts

| Suite | Result |
|---|---|
| `tests/test_r44h2_sampler_telemetry_gantt.py` (NEW) | **16 passed** |
| `tests/test_r44g1_dynamic_gantt.py` | **17 passed** (3 expectations updated per H2 spec, see §2) |
| `test_v2_waterfall.py` + `test_v2_waterfall_contract.py` | **68 passed** |
| `test_v2_unet_forward_probe.py`, `test_r44e_evidence_durability.py`, `test_native_fast_disk_unet_loader.py`, `test_e27_gantt_telemetry.py`, `test_e29_gantt_canonical.py` | included in combined run |
| **Combined required run (all of the above)** | **217 passed / 0 failed** |
| `py_compile` (all touched modules incl. comfyapp/modal_app) | clean |

R44H1-owned CLIP suites were NOT run (respected lane boundary).

## 12. Rendering / event overhead (measured locally)

* Real R44E artifact (394-line full report): load 10.3 ms + render 9.9 ms; `render_artifact_file` end-to-end 23.0 ms — host-side only.
* Synthetic rich fixture: 10.2 ms render.
* Tick recording: 2000 ticks ≪ 500 ms budget (asserted); 8-step cohort cost is microseconds (two dict appends + clock read per callback).
* Sub-timing wrappers: one perf_counter read + lock-guarded integer add per call; installed only inside the sampler-node window.
* Remote critical-path cost of new telemetry: timestamp reads only; no sync/empty_cache/IO/introspection/serialization added.

## 13. Example renders

**(a) EXISTING R44E artifact** (`v2_2026-08-24_02-49-32`, no new events — honest degradation): legacy interval now renders `sampler node→first progress (PROXY — incl. prep + first step) 1461.5 ms`; completeness shows all ten new sampler entries MISSING with exact expected keys and the `proxy_first_progress` proxy named; SAMPLER DETAIL window appears; STAGE SUMMARY labels the legacy row `[PROXY — end boundary is FIRST PROGRESS, not sampling start]`. Full text: `.opencode/tmp_r44e_dynamic_gantt.txt`.

**(b) Synthetic/new-event fixture** (R44E-shaped + H2 events; full text `.opencode/tmp_h2_fixture_gantt.txt`):

```
── SAMPLER DETAIL ──
Sampler node                        │████████████████████████████████████│ 5677.2 ms @+0.000s
  sampler orchestration/prep        │█▍                                 │ 120.0 ms @+0.000s
post-sampling transition            │                       ▊███████    │ 650.1 ms @+5.027s
  RES4LYF sampler post-loop tail    │                       ▊███████    │ 649.8 ms @+5.027s
  executor dispatch → VAEDecode     │                             ▏     │ 0.3 ms @+5.677s

══ TELEMETRY COMPLETENESS ══
sampling wrapper start (true)      PRESENT
sampler prep phase                 PRESENT
first eval start                   PRESENT
per-step ticks                     PRESENT
sampler tail                       PRESENT
tail GC split                      PRESENT      (210.5 ms)
tail deepcopy split                PRESENT      (95.2 ms)
tail CPU transfer split            PRESENT      (180.0 ms / 12,345,678 B)
VAE load_models_gpu mono timestamps PRESENT

══ STAGE SUMMARY (canonical boundary semantics) ══
SAMPLER
  node entry → true sampling_start (orchestrati…   120.0 ms
  post-loop tail (last progress → node return)     649.8 ms
```

(The unit suite additionally proves the full five-way split incl. `first-eval startup` 1080 ms and `first-step latency` 100 ms when t6 keys are present.)

## 14. Concurrent-file overlap assessment (R44H1)

Pre-existing dirty set preserved byte-for-byte outside my scoped edits. Shared dirty files touched by me with ADDITIVE, localized blocks only: `runtime_executor.py` (wrapper/lmg/CpuTimer/exec-node — no CLIP/adoption logic), `modal_app.py` (pre_sampler_stages keys), `comfyapp.py` (sampler-phase hooks), `benchmark_v2_direct.py` (post-artifact block), `v2_waterfall.py` (one stage branch). `request_clip_fastsafe.py`, `clip_*`, `request_unet_fastsafe.py` untouched. My only cross-lane surface is the lmg-seam re-install, which calls R44H1-neutral, pre-existing idempotent helpers and alters no eligibility/adoption decision. All shared files were re-read immediately before each edit; combined-suite runs stayed green throughout.

## 15. Exact checklist for the NEXT PAID GATE

1. Deploy current tree; run ONE cold gate on `r44-request-fastsafe` (controls frozen).
2. In `run_0.json` verify presence of: `sampling_start`, `unet_first_cuda_op`, `sampler_prep_phase`, `sampler_first_eval_start`, `sampler_step_ticks` (count == steps), `sampler_tail` (with gc/deepcopy/cpu splits), `vae_decode_start`, and `pre_sampler_stages.sampling_start_monotonic_ns != null` with `sampling_start_source="authoritative_wrapper"`.
3. Confirm `dynamic_gantt_run_0.txt` exists beside the artifact and shows the five-way SAMPLER split + `RES4LYF sampler post-loop tail` + ten PRESENT sampler completeness rows.
4. Waterfall: `sampler_node_to_sampling` ≈ node→true-start (~110–150 ms expected historically); `sampling` = true-start→wrapper-return; proxy annotation absent.
5. Read the diagnosis directly off STAGE SUMMARY: prep-vs-first-eval split decides Rank-1 priming vs Rank-2 tail work (R44G3 §12) — no source reverse-engineering needed.
6. If `sampling_start` is STILL absent: check `[comfymodal] ensure_sampling_timing_wrapper failed` / probe install logs around the sampler `load_models_gpu` line before touching any loader code.

---

```text
R44H2_DYNAMIC_GANTT_LIVE_WIRED = YES
R44H2_LEGACY_CLIP_LABEL_FIXED_OR_WARNED = YES   (explicit adjacent warning; persisted span name kept for schema/consumer stability)
R44H2_TRUE_SAMPLING_START_DURABLE = YES
R44H2_SAMPLER_PREP_EVENT = YES
R44H2_FIRST_EVAL_EVENT = YES
R44H2_PER_STEP_TIMESTAMPS = YES
R44H2_SAMPLER_TAIL_EVENT = YES
R44H2_SAMPLER_TAIL_SUBTIMINGS = YES
R44H2_VAE_LOAD_MODELS_GPU_TIMESTAMPS = YES
R44H2_CONSOLE_RING_PERSISTED = DEFERRED         (host-side-only infra; remote stdout tee would be invasive — documented above)
R44H2_COMPLETENESS_MATRIX_EXTENDED = YES
R44H2_RUNTIME_PERFORMANCE_BEHAVIOR_CHANGED = NO
R44H2_REMOTE_RUN_PERFORMED = NO
R44H2_READY_FOR_RECONCILIATION = YES
```

STOP. No deploy. No Modal run performed.
