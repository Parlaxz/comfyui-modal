# OC8 — Golden-Candidate Telemetry Semantic Red Team

Date: 2026-08-25 · Mode: READ-ONLY independent red team. No deploy, no paid run, no source changes, no architecture selection. Only files created: this report + `OC8_TELEMETRY_BOUNDARY_TRUST_MATRIX_2026-08-25.csv`.

Scope: Restore · CLIP load · CLIP forward · UNET load · VAE prepare/decode · Output/first-durable · Teardown. Sampler internals excluded (only boundary stamps touched).

---

## 0. Evidence basis and disclosure

The referenced Phase-O/OB documents (O2–O7, OB timing/candidate matrices, OB7, OB8, "v2.1") are **not present on disk** in either lane checkout (`comfyui-modal`, `comfyui-modal-r42`) by filename, content grep, or git history. This red team therefore grounds every judgment in **primary evidence**: exact telemetry emitters in current source, raw run artifacts/logs, and the in-repo audits that carry the material numbers (E38B canonical contract audit, E29 ground-truth map, E39/E40 reports, K4/K5/R42B/R42C/R43/R44-series and K1 batch reports). Where a challenged claim originates from an O/OB document I could not read, the challenge is registered against the closest in-repo carrier of that claim and marked accordingly. All line references below were verified against the current checkout unless marked otherwise.

Governing rule applied throughout: a raw event proves *this emitter executed at this timestamp* — nothing more. Every material metric below is mapped to emitter/start/end/clock/children before classification.

---

## 1. Telemetry evidence inventory (emitters verified in source)

### 1.1 Clock domains (abridged from E38B §3, CONFIRMED)
D1 remote mono `time.monotonic_ns()` · D2 remote wall `time.time_ns()` · D3 remote process perf `perf_counter[_ns]()` · D4 GPU CUDA events · D6/D7 local host wall/mono · D8 Modal log-line timestamps (never valid vs D2/D6). Remote runtime is CPython 3.11/Linux where perf_counter and monotonic share one underlying clock (E38B §2/§7); cross-machine wall arithmetic remains banned (≥1.1 s host↔container offset proven by emit-after-return inversion, E38B §6).

### 1.2 Restore (all `comfymodal_runtime/modal_app.py`, enclosing `restore()`)
| Boundary | Site | Notes |
|---|---|---|
| `remote_python_resume_mono_ns` | :10132-10140 | TRUE first executable line of `restore()`; D1. `restore_method_start_mono_ns`/`…_wall_ns` set equal to it (:10141-10142). |
| ledger `modal_restore_entry` | :10164 | same stamp |
| `restore:early` span | open :10197-10205, start reset to entry stamp :10216-10218, close :10306-10315 | covers ledger/identity/manifest/callback-age setup through eviction-boundary entry |
| `restore:eviction` | close/open :10329-10340 | `_restore_eviction_boundary()`, retained-model handling, `_lazy_init_snapshot_state()` |
| `restore:snapshot` | close/open :10335→10386-10394 | snapshot-state/manifest availability, `clip_manifest_available` |
| `restore:preamble` | open :10386-10398, close :10714-10723 | CLIP demand install, invariant checks, identity/config/trace setup; **contains `_restore_perf_start` at :10456** |
| `restore:bootstrap` | open :10714-10723, close :10746-10756 | `self.bootstrap.restore(...)` |
| `restore:preload` | open :10746-10756, close :11901-11907 | preload bridge + preload/hydration work |
| `restore:finalize` | open :11901-11914, close :12035-12043 | finalization, timing publication |
| `restore_total_ms` (request path) | computed :10787/:11923 = `(perf_counter − _restore_perf_start)`; `_restore_perf_start = time.perf_counter()` at :10456 | **starts mid-preamble** — see Finding F2 |
| `restore_total_ms` (startup alias) | :9668-9696, `"lifecycle_method": "startup"` | measures STARTUP lifecycle (`_startup_perf`), written under the restore key |
| `restore_total_ms` (legacy) | `comfyapp.py:19683`, `:21331` (`_profile_ms(restore_start)`) | legacy/local harness producer |
| `CriticalPathSpan` accounting | `critical_path_ledger.py:282-445` | duration axis perf_counter_ns; child intervals UNIONED (:345-363); residual = duration − work − wait − sync − child_union, `UNATTRIBUTED` if >1 ms (:427-445); serial gaps labeled `UNATTRIBUTED` (:576-649); endpoints via `set_authoritative_endpoints` (:91-107) |

### 1.3 CLIP load
| Boundary | Site | Notes |
|---|---|---|
| `CLIP hydration` ledger span | `clip_fast_hydration_wiring.py:1241-1255` (enclosing `_try_fast_hydrate`) | D1 monotonic; whole fast-hydrate window: source read/speculative take/verify/bind/sync |
| `clip_device_ready` endpoint | `clip_fast_hydration_wiring.py:1728-1751` (`_emit_clip_loader_endpoint`, `CLIP_DEVICE_READY`) | fires after bind + bind-wait; **before** hydration span close (:1997-2001); does NOT await first encoder use |
| cache-hit mode | `clip_fast_hydration.py:873` `MODE_CACHE_HIT="conditioning_cache_hit_no_hydration"` | cache hit produces **no** hydration/forward interval |

### 1.4 CLIP forward
| Boundary | Site | Notes |
|---|---|---|
| `clip_forward` span | wrapper `_make_clip_span_wrapper("clip_forward", …)` on cond-stage outermost `encode_token_weights` (`model_preload.py:9284-9299` per K5:21); events `clip_forward_start/end` `clip_forward_forensics.py:259-295` | INSIDE: token weighting/embedding, transformer forward, pooling, output processing, fixed instrumentation preamble (ledger begin_span, clean-lane mark, mark_clip_forward_start, trace emit). OUTSIDE: tokenization, `load_models_gpu`, `set_clip_options`, conditioning-output conversion (K5:41-42) |
| execution-state/GPU-busy probes | `clip_forward_exec_state.py` (K5-added): `clip_forward_exec_state_start/_end` (42-field host/CUDA/exec/concurrent-prep-reader state), `clip_forward_phase_gpu_ms` (transformer-core + per-block GPU intervals) | the only licensed GPU-busy decomposition of the forward window |

### 1.5 UNET load
| Boundary | Site | Notes |
|---|---|---|
| `load_models_gpu` wrapper spans | `clip_cold_path_forensics.py:1087-1149` wrapping `model_management.load_models_gpu`; emits `*_start/_end` wall+mono+cpu clocks | interval = entire wrapped call: placement/H2D/casting/eviction/offload/bookkeeping **for all models passed** — emitter alone cannot prove "UNET-only" |
| fastsafe file→GPU | fastsafetensors transport stage timer (documented C9:145-147; measured K5:71) | setup / file→GPU / instantiate recorded separately |
| QD engine timers | `clip_qd_reader.py:1333,1784` (`clip_qd_stats`); UNET QD probe `unet_qd_probe.py:1675-1682` | D3/D10 paired host-issue + CUDA-event design (E38B §18 protects internals); **no production `<unet>_qd_stats` emitter found** |

### 1.6 VAE
| Boundary | Site | Notes |
|---|---|---|
| `VAE decode` ledger span | `model_preload.py:13893-13920` | wraps the `VAEDecode` node call incl. `_vae_decode_compute_scope`; excludes post-decode numpy/PIL/descriptor/persistence |
| `vae_decode_ms` local stage | `wall_clock_trace_v3.py:578-583` (t6a/t6b); legacy `benchmark_modal.py:357` uses t7_* pair | different producers, era drift |
| `VAELoader` node_timing | node-level trace (K4:104,155) | request-time Volume read when `COMFYMODAL_V2_VAE_SNAPSHOT=0` |
| pre-copy/join metrics | C5-era: `load_wall_ms`, `precopy_wall_ms`, `join_wait_ms`, `overlap_ms` | overlap bookkeeping, not decode |

### 1.7 Output / first-durable
| Boundary | Site | Notes |
|---|---|---|
| `remote_result_emit` | `modal_app.py:5412-5483` (`_stamp_remote_result_emit`) | wall+mono stamped immediately before yielding result into generator transport |
| `output_persist_done` + `first_durable_result` events; `result:assembly` close | `modal_app.py:19780-19827` | **all three reuse the same `_emit_mono` instant** as `remote_result_emit` |
| authoritative end | `critical_path_ledger.py:91-107,731-751` | serial axis `remote_python_resume_mono → first_durable_result_mono`, zero-gap w/ labeled residual |
| parent scopes | `executor:graph-execution`, `request:executor-run` | overlap children BY DESIGN (union accounting, E38B:91) |
| post-durable | `_deferred_commit_task/_pending/_diag` init :17872-17874; `_finalize_deferred_commit()` ~:16215-16344; terminal cleanup :17911-17925 | outside the serial axis |

### 1.8 Teardown
| Boundary | Site | Notes |
|---|---|---|
| terminal cleanup stamps | `terminal_cleanup_start/end_wall_unix_ns` + mono twins around `_run_terminal_cleanup_sync` (`V2_BATCH_A_G1_AND_TERMINAL_STAMPS_REPORT.md:113-119`, helper `modal_app.py:5059-5084`; current invocation :17906-17926) | synchronous cleanup/release/watcher-join/deferred-commit handling only |
| sampler `teardown_ms` | `comfyapp.py:15320-15332`, `_profiled_ksampler_sample` :16418-16442 | sampler-node teardown (adjacent, out of scope) |
| platform container stop/scale-down | uninstrumented | no in-process timer claims it |

---

## 2. Boundary trust matrix (summary — full per-pair detail in CSV)

Class definitions per brief. Highlights only; the CSV carries all ~35 pairs with emitter refs.

**EXACT_SEMANTIC_BOUNDARY** (name matches proven interval):
`remote_python_resume_mono_ns`; ledger `modal_restore_entry`; the seven `restore:*` phase spans individually; `restore_method_*_wall/mono` (= resume stamp → method exit); `clip_forward` span (as "inner encode_token_weights window"); `VAE decode` ledger span (as "wrapped VAEDecode node call"); `remote_result_emit` (as "handed to response stream"); `sampling` span endpoints; `snapshot_callback_age_at_restore_ms`.

**VALID_SUB_BOUNDARY** (true interval, narrower than the Golden-part contract):
`restore_total_ms` request-path variant (misses early+eviction+snapshot+preamble prefix); `CLIP hydration` (if contract = "ready for compute"); `clip_device_ready` (bind done, not first-use); E27 QD full-file transfer 1020.9; fastsafe file→GPU (C9 2172.92, K5 363-416, E28/R44E/J1 classes); R42 commit 878.5; J1 warm-commit 432/705/745; `output_persistence.end`/`first_durable_result` as end-of-assembly point; `terminal_cleanup` stamps.

**VALID_BUT_CONTAMINATED**:
`load_models_gpu` spans (interval exact, contents = ALL models passed + management overhead; "UNET-only" attribution requires artifact metadata not carried by the emitter).

**NAME_MISLEADING**:
`restore_total_ms` (three incompatible producers under one key — F1/F2); `first_durable_result` as a *durability* claim (shared-timestamp construction — F8/C4); `pre_sampler_ms` (aggregate of heterogeneous stages presented as one stage).

**CROSS_ERA_SEMANTICS_CHANGED**:
`restore_total_ms` (startup-alias era vs request-perf-subsection era vs comfyapp-profile era); `vae_decode_ms` (t7_* era vs t6a/t6b era vs ledger span era).

**REPORT_ONLY**:
`remote_python_resume_to_restore_start_ms`, `restore_end_to_modal_method_entry_ms` ("absent" string placeholders in C8-era timing JSONs though computable in current code, `canonical_execution.py:2822-2830,3135-3137`); Modal UI restore time (K1: USER_UI_REQUIRED).

**UNKNOWN**:
teardown ~2.455 ms and ~2560.334 ms (no emitter/artifact provenance found — F10); VAE "~89–98 ms" referent (candidates listed in F7d).

---

## 3. Cross-era semantic-equivalence map

| Equivalence set | Verdict | Proof |
|---|---|---|
| `first_durable_result_mono_ns` ↔ `first_durable_result` event ↔ `output_persistence.end` ↔ `result:assembly` end | SAME boundary (canonical runs) | one shared `_emit_mono` stamp, `modal_app.py:19780-19827`; E38B:85 Δ7.7 µs wall-axis confirmation |
| `first_durable_result` ↔ `remote_result_emit` | EQUIVALENT within µs by construction (same stamp reused); conceptually distinct (transport handoff vs durable claim) | :19781-19827 order |
| E37 `restore_method_ms` 678.233 ↔ Σ ledger restore children 660.598 (+17.6 UNATTRIBUTED) | SAME window (method wall = children union + residual) | E38B §8 |
| E37 `restore_total_ms` 303.653 ↔ bootstrap 250.764 + preload 0.947 + finalize 7.64 + post-:10456 preamble remainder | SAME sub-window (perf subsection), NOT the method window | arithmetic fit; F2 |
| K1/R43-era `restore_total_ms` (300.133 / 480.695 / 680.098 / 1670.909) ↔ E37 `restore_total_ms` 303.653 | NOT PROVEN equivalent — producer tag (`lifecycle_method`) must be read per artifact before comparing | F1/F3 |
| C9 fastsafe file→GPU 2172.92 ↔ K5 fastsafe file_to_gpu 363-416 ↔ E28 477 / R44E 624.7 / J1 median ~618 | SAME emitter FAMILY (fastsafe file→device stage) but different engine state (true-cold vs matched-placement vs armed-warm); comparable only within labeled state | C9:145-147, K5:71, R44J1:149 |
| E27 1020.9 (QD4 storage→pinned→H2D full file) ↔ fastsafe file→GPU classes | DIFFERENT emitters/engines (QD reader vs fastsafetensors); NOT interchangeable | E27:268 vs C9 |
| R42 commit 878.5 ↔ `load_models_gpu` 840.785 (E37) ↔ J1 warm-commit 432-745 | RELATED commit-phase classes, DIFFERENT mechanisms (native reread vs adoption vs warm join); do not trend across them | R43:187, E38B:91, R44J1:104,149 |
| ledger `VAE decode` 381.287 ↔ local `vae_decode_ms` 381.691 (same run) | NEAR-equivalent today, different producers; era drift documented | Lane C/D evidence |
| `submit2entry_ms` ⊇ `restore_total_ms` when `restore_included_in_submit2entry=true` | guarded; info-only copy emitted | `wall_clock_trace_v3.py:661-696,784-788` |

---

## 4. Confirmed safe metrics (licensed for Golden-total reasoning within their stated reading)

1. Canonical serial axis `remote_python_resume_mono → first_durable_result_mono` with union accounting + labeled UNATTRIBUTED (ledger construction makes naive double-count impossible *inside the ledger*).
2. Individual ledger children as tiling segments: `restore:*` phases, identity-capture, plan-deserialize, setup-schedule, `CLIP hydration`, `CLIP forward`, `load_models_gpu` instances, `sampling`, `VAE decode`, graph-tail, `result:assembly` — provided parents (`executor:graph-execution`, `request:executor-run`) are NEVER summed alongside them.
3. `restore_method_*` wall/mono pair (resume→exit) as the full restore-method window.
4. `clip_forward` span as the inner encode window (with the explicit understanding that it contains host-contention waits, see F5).
5. `VAE decode` span as wrapped-node decode time.
6. `remote_result_emit` as the response-handoff point.
7. `snapshot_callback_age_at_restore_ms` as a staleness indicator only.
8. `terminal_cleanup` start/end stamps as synchronous in-process cleanup time.

## 5. Confirmed partial metrics (valid intervals, incomplete for the part contract)

- `restore_total_ms` request-path variant (bootstrap-onward subsection; misses ≤~400 ms of candidate-owned restore work — F2).
- `CLIP hydration` span and `clip_device_ready` (source+bind complete; neither licenses "model ready for first compute" without the E31-style post-bind proof note).
- E27 QD full-file transfer 1020.9 (excludes metadata/plan/bind/instantiate).
- fastsafe file→GPU classes (excludes setup/instantiate/integrated assembly; C9 integrated load was 2743.4 vs 2172.92 stage).
- J1 warm-commit / R42 commit classes (commit phase only).
- `pre_sampler_ms` (real aggregate; cannot attribute to a single candidate part).
- C5 `precopy_wall_ms` 70.221 / `join_wait_ms` 0.008 (overlap bookkeeping; explicitly "not the same work" as a 759.0 ms full load — C5:115-118).

## 6. Contaminated / misleading metrics

1. **`restore_total_ms`** — three incompatible producers share one key: startup lifecycle alias (`modal_app.py:9668-9696`, `lifecycle_method:"startup"`), request-path perf subsection (start `:10456` mid-preamble, computed :10787/:11923), legacy comfyapp profile (`comfyapp.py:19683,21331`). E38B:189-193 already ruled it diagnostic-only; K1/K4 tables still consume it unqualified. Any cross-era restore comparison using this key un-tagged is invalid (mistake #10 realized).
2. **Request-path `restore_total_ms` "total" claim** — name says total; clock starts after `restore:early`(9.006)+`eviction`(343.996)+`snapshot`(4.086)+preamble-prefix had already run. In the E37 artifact the subsection reads 303.653 while the true method window is 678.233 (mistake #4: timer starts after required candidate work began — proven from source order + arithmetic fit).
3. **`load_models_gpu` spans as "UNET H2D"** — wrapper records whatever models management processed; 840.785 attribution to UNET alone requires the artifact's model-list metadata (mistake #1/#2 risk).
4. **CLIP forward treated as GPU compute cost** — span wall (1110.221 / 2037.941 / 1997-5283 classes) vs transformer-core GPU busy ~200-350 ms (K5:133); the difference is host contention (e.g., concurrent UNET prep reader) inside the span (mistake #13).
5. **`first_durable_result` as proof of physical durability** — stamped at the same instant as `remote_result_emit`; encode/handoff ordering (D14: output encode 158-190 ms before `close_workers_end`; handoff 85-115.5 ms) supports but does not prove persistence completion; no post-write acknowledgment boundary exists (see C4).
6. **`pre_sampler_ms` as a stage** — normalized aggregate (`benchmark_modal_e2e.py:2468` derives it from prompt-start→sampler-start); contains restore tail, plan/setup, CLIP work, UNET prep, gaps; R43's own legend defines it as "model construct+load+CLIP forward".
7. **Unprovenanced teardown numbers ~2.455 / ~2560.334** — no emitter tie found in either checkout; nearest literals are unrelated (2.4555 in E27 UNET probe JSON context; 2451.587 = a restore_total in `c4_armA_retry7.log`; sampler `teardown_ms` 6.986/32.824/5.715; terminal-cleanup example 78.16 ms).

## 7. Unresolved metrics

| Metric/claim | Why unresolved | Needed |
|---|---|---|
| teardown ~2.455 ms | no provenance | producing artifact + emitter, or drop |
| teardown ~2560.334 ms | no provenance | producing artifact + emitter, or drop |
| VAE "~89–98 ms" | ambiguous referent; candidates: `vae_snapshot_load 98.347 ms` (startup snapshot load, deploy logs), FAST_DISK 98.242, CUDA-context sync 89.691/89.868 | naming of the intended OB claim |
| durability semantics of `first_durable_result` | emitter construction cannot distinguish "assembly done" from "persistence acknowledged" | explicit post-write boundary (C4) |
| J1-era added timers inside restore vs after | `.v2ctl/k1_manifest/r42_diff_9a428fd_modal_app.patch` not readable from this checkout; R44J1 report confirms early-model-prep + quiet-forward machinery but not every timer placement | diff review in r42 lane |

## 8. Formal challenge records

Format: claim challenged → evidence → boundary/code/state deltas → strength → verdict → replacement wording.

**CH-01 — "restore_total_ms is the restore total."**
Evidence: `modal_app.py:10132-10142` (method start = resume stamp) vs `:10456` (perf start, inside preamble after early/eviction/snapshot closed at :10315/:10340/:10394) vs `:10787/:11923` (computation); E37 artifact carries BOTH `restore_total_ms=303.653` (K4:89) and `restore_method_ms=678.233` (E38B:187); 303.653 ≈ bootstrap 250.764+preload 0.947+finalize 7.64+preamble remainder (E38B:91). Same name, different code, different boundary. Strength: CONFIRMED (source order + artifact arithmetic). Verdict: **AMEND**. Replacement wording: "`restore_total_ms` (request path) is the perf-counter subsection of restore beginning mid-preamble (bootstrap-onward); the full restore-method window is `restore_method_ms` (resume→exit) and the tiled truth is the ledger `restore:*` children union plus labeled UNATTRIBUTED."

**CH-02 — "K1/R43 restore_total golden band 258–394 ms vs current-class 1671 ms."**
Evidence: K1:139-158 values sourced from `run_001_sample.json` boundaries whose producer tag is not quoted; startup-alias producer exists (`lifecycle_method:"startup"`); R43:145 mixes `restore_total` (+1255.3), `snapshot_restore` (1479 vs 227) and `restore_method` (1810 vs 318) in one attribution sentence. Same metric name, potentially different producers across compared eras. Strength: SUPPORTED (producer ambiguity proven possible; actual producer per artifact not re-derived here). Verdict: **AMEND** (direction of the K1 conclusion is untouched; the metric licensing is). Replacement wording: "restore recovery holds per `run_001_sample.json` restore-family fields, contingent on quoting the producer tag (`lifecycle_method`) and, where available, `restore_method`/ledger children for every compared run."

**CH-03 — "`load_models_gpu` 840.785 ms = UNET load/H2D."**
Evidence: wrapper `clip_cold_path_forensics.py:1087-1149` measures the whole `model_management.load_models_gpu` call for all models passed; no emitter field isolates UNET. Same boundary, wider code content than claimed. Strength: CONFIRMED (emitter scope). Verdict: **AMEND**. Replacement wording: "`load_models_gpu` 840.785 is the model-management commit interval at the UNET-commit position; contents include all models processed plus casting/offload/bookkeeping; UNET-only attribution requires the artifact's model metadata."

**CH-04 — "`first_durable_result` proves the result is durably persisted."**
Evidence: `modal_app.py:19780-19827` assigns `output_persist_done`, `first_durable_result`, and `result:assembly` close the SAME `_emit_mono` reused from `_stamp_remote_result_emit`; no post-write acknowledgment event exists; supporting-but-not-conclusive ordering in D14:71-73,119. Same code, contested semantic condition at end. Strength: SUPPORTED (construction proven; overclaim not proven). Verdict: **UNRESOLVED — KEEP pending Serial-Golden evidence** (do not relabel; require the missing boundary listed in §9-1 before using "durable" as a persistence guarantee in Golden acceptance prose).

**CH-05 — "UNET file→GPU numbers (E28 477 / R44E 624.7 / K5 363-416 / C9 2172.92) form one trend."**
Evidence: same stage name, different engine states: true-cold C9 2172.92 (integrated 2743.4), matched-placement K5 363-416, armed-warm J1 median ~618 recovering "the R44E exact 624.7 / E28 477 class" (R44J1:149). Different state, near-same code family. Strength: CONFIRMED (state labels in reports). Verdict: **SUPERSEDE** any single-trend reading. Replacement wording: "file→GPU classes are engine×state cells (fastsafe cold / matched-placement / armed-warm; QD-probe separately); compare only within labeled cells."

**CH-06 — "Teardown ≈2.455 ms / ≈2560.334 ms."**
Evidence: exhaustive literal search across both checkouts found no emitter or artifact binding (nearest unrelated hits enumerated in §6-7). Strength: CONFIRMED absence (bounded search disclosed in §0). Verdict: **UNRESOLVED** — supply provenance or exclude from Golden reasoning.

**CH-07 — "674.443 ms is a VAE-stage (prepare/decode) cost."**
Evidence: K4:104,155,206 — it is the `VAELoader` node executing at request time reading VAE from Volume under `COMFYMODAL_V2_VAE_SNAPSHOT=0`, positioned in the pre-CLIP graph segment (K4:132: occupant of first-node→CLIP-load-start). Raw duration correct; stage attribution differs (mistake #13). Strength: CONFIRMED. Verdict: **AMEND**. Replacement wording: "674.443 ms is request-time VAE source-load (residency-policy-dependent), realized in the graph before CLIP load; E37-era (`VAE_SNAPSHOT=1`) paid it once at startup instead."

**CH-08 — "CLIP hydration/device-ready = model ready for compute."**
Evidence: `clip_fast_hydration_wiring.py` — device_ready fires at bind completion (:1728-1751) before span close (:1997-2001); neither awaits first encoder use; E31 cast/proof semantics live after bind sync. Boundary narrower than "compute-ready". Strength: SUPPORTED. Verdict: **AMEND** (wording only). Replacement wording: "`clip_device_ready` licenses weights-on-device after bind+sync; first-compute readiness additionally rests on the E31-class post-bind proof path."

---

## 9. Exact missing boundary evidence needed during Serial Golden validation

1. **Post-write persistence acknowledgment** — an explicit emitter after the last durable byte leaves the process (upload/fsync/commit-complete), distinct from `remote_result_emit`, so `first_durable_result`'s durability claim is licensed or scoped to "response-durable".
2. **Producer tag on every `restore_total_ms`** — serialize `lifecycle_method` + start-stamp site next to the value wherever it is consumed in comparisons (K1/K4/R43-style tables).
3. **Model-list metadata inside each `load_models_gpu` span** — to license per-model attribution (UNET-only etc.) without re-opening artifacts.
4. **Standardized file→GPU cell labels** — `{engine, cache/prewarm state, placement class, bytes, GB/s}` attached to every file→GPU figure so E28/R44E/K5/C9/J1 classes cannot silently merge (they already exist informally in reports; make them emitter fields).
5. **GPU-busy subset requirement** — carry K5's `clip_forward_phase_gpu_ms` / exec-state capture in every Golden-cohort run so forward-wall-vs-GPU-busy never conflates again.
6. **Cache-hit markers mandatory** — when conditioning-cache hit suppresses hydration/forward intervals, the artifact must carry the `MODE_CACHE_HIT` marker wherever consumers expect those intervals (prevents silent-absence-read-as-zero).
7. **Teardown provenance** — terminal_cleanup stamps present + explicit statement that platform container stop/scale-down is outside application telemetry; provenance (artifact+emitter) for any quoted teardown totals (§7 rows).
8. **Restore-window completeness statement** — any "restore total" quote must state whether it covers early+eviction+snapshot (method wall / children union) or only the bootstrap-onward subsection.

## 10. Raw evidence appendix (primary citations)

- `modal_app.py`: 9668-9696 (startup alias), 10132-10230 (resume stamp, entry event, early-span reset, endpoint registration), 10306-10398 (early/eviction/snapshot/preamble boundaries), 10456 (`_restore_perf_start`), 10714-10756 (preamble/bootstrap/preload), 10782-10804 (error-path total), 11901-12043 (preload/finalize close, exit event), 11923-11944 (success-path total + method stamps), 15464-15528 & 19780-19838 (durable/result-assembly/emission ordering), 16215-16344 (deferred commit finalize), 17872-17926 (deferred-commit state init, terminal cleanup stamps).
- `critical_path_ledger.py`: 91-107 (authoritative endpoints), 282-445 (span class, union, residual, UNATTRIBUTED), 576-649 (serial gaps), 731-751 (resume→durable contract).
- `clip_fast_hydration_wiring.py`: 1241-1255 (hydration span), 1728-1751 (device-ready), 1997-2001 (span close). `clip_fast_hydration.py:873` (cache-hit mode).
- `clip_forward_forensics.py:259-295`; `model_preload.py:9284-9299` (per K5:21), 13893-13920 (`VAE decode` span). `clip_cold_path_forensics.py:1087-1149` (`load_models_gpu` wrapper). `clip_qd_reader.py:1333,1784`.
- `wall_clock_trace_v3.py`: 542-583 (stage pairs incl. restore/vae), 661-696 (double-count guard), 735-788 (fallback + info-only fields). `canonical_execution.py:2822-2830,3050-3071,3135-3137` (seam fields, local receipt).
- Reports: E38B:47-57 (clock domains), :71-91 (endpoint map + serial chain incl. 1149.953/0.803/1110.221/840.785/4748.2/57.792/381.287/166.932/9658.875/93.142/9746.282), :152 (≥1.1 s offset proof), :184-193 (restore-field reconciliation), :372-379 (final answers); E29:88-127,175-184,185-195; E39:237-280 ([30] first_durable_result); E40 item 10; K4:77-132,155,204-222 (restore_total 303.653, VAELoader 674.443, forward +927.72, pre-CLIP segment occupancy); K5:21,41-49,61-71,133 (forward span contents, PYTHON_RESUME_TO_FIRST_DURABLE, UNET file_to_gpu 363.260/415.655/406.694, GPU busy 200-350); R43:145,155,184-187 (restore attribution mix, R42 commit 878.5, E37 forward 1.110 s); R44J1:32-39,104,130,149,181-182 (J1 classes, warm-commit 432/705/745, E28 477 / R44E 624.7 recovery); C9:145-147,211,283 (2172.92 file→GPU, 21.89 setup, 0.57 instantiate, integrated 2743.4); C5:18-22,96-118,145-153 (70.221/0.008/759.0 "not the same work"); D14:28,71-73,119 (output encode 158-190, handoff 85-115.5); V2_BATCH_A_G1:113-119 + BATCH_A_ACCEPTANCE:188-189 (terminal-cleanup stamps; 78.16 ms example); K1:139-158 (cohort table, golden band 258-394); E27:268 (1020.9 QD transfer); E38L:38,69-90,346,573,724-749 (validity framing); SAMPLING_DEEP_DECOMPOSITION:85,90 (sampler teardown_ms — out of scope).
- Absence checks performed: O/OB docs (filename/content/git-history sweep of both checkouts); teardown 2.455/2560.334 (both checkouts, md/log/json/txt); production `<unet>_qd_stats` emitter; `postdurable_persist_fail_after_durable` runtime emitter; canonical `restore_ready` ledger event (only a residency-sample stage at `modal_app.py:11525-11528`).

— End of OC8 red team. No code, tests, profiles, or deployments modified.
