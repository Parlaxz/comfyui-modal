# OC5 — Batch VAE Candidate-Specific Timing-Completeness Audit

Date: 2026-08-25
Mode: READ-ONLY audit. No deploy, no paid run, no source change, no architecture selection, no recommendation.
Scope: what the historical VAE timings actually represent, per candidate, against contracts derived from the actual code.
Companion artifact: `OC5_VAE_TIMING_CLAIMS_2026-08-25.csv` (one row per timing claim).

---

## 0. Audit posture and mandated disclosures

- **Named Phase-O artifacts NOT FOUND.** The task's READ list cites a "Phase-O reconciled SoT", "v2.1", "O5/O6/O7/O8", "OB5 VAE evidence/candidate matrices", and "OB7/OB8 findings". No file or content matching `Phase-O`, `PHASE_O`, `OC1..OC5`, `OB5`, `OB7`, `OB8`, or a "v2.1 SoT" exists in either workspace clone (`comfyui-modal`, `comfyui-modal-r42`), including `.slim/`, `docs/`, `reports/`, `.v2ctl/`, and all `*.md|*.txt|*.json` sweeps (searches: filename globs + full-text greps for `Phase-O`, `OB5`, `OB7`, `OB8`, `reconciled SoT`, `O5`–`O8`). The only hits for `O5`–`O8` tokens are unrelated (E38A snapshot-reachability matrix rows; runtime shape `snapshot_model_order=O0`). These inputs are recorded as **NOT_FOUND_IN_WORKSPACE** in §1; nothing below depends on them. All findings are grounded in the artifacts that do exist.
- **K4 674.443 ms is raw-backed** (canonical-ledger `node_timing_*` rows with exact mono_ns bounds) — therefore it is **NOT** held at REPORT_ONLY.
- One delegated code-exploration citation (`cpu_snapshot_models.py:2526-2554` "`vae_load_ms`" restore timer) **failed direct verification by grep in both repo copies** and was discarded. Snapshot-side composition cost is instead carried from the K4-cited E37-era startup event (`cpu_snapshot_vae_load` 1135.19 ms), which is report-tier citing run artifacts. The existence/location of a current-code snapshot-composition timer is recorded as an open gap (§9-G4).
- No milliseconds are inferred anywhere. Every number is quoted with its source boundary pair or declared uninstrumented.

---

## 1. Evidence inventory

Legend: tier RAW = canonical ledger / node_timing / reconciliation metadata from run artifacts; TIER-REPORT = batch report quoting run artifacts verbatim; AUDIT = independent audit observation over artifacts; DESIGN = frozen design contract (no measurement).

### 1.1 Found and used

| # | Artifact | Repo | Role in this audit | Tier |
|---|---|---|---|---|
| A1 | `E37_CLEAN_LANE_ALGORITHM_RECOVERY_REPORT.md` | comfyui-modal | E37 candidate context | REPORT |
| A2 | `V2_BATCH_C5_VAE_FIRST_STEP_AB_REPORT.md` | comfyui-modal | C5 Arm A/B primary numbers, event sequences, waterfalls | TIER-REPORT (verbatim artifacts) |
| A3 | `V2_BATCH_C5_VAE_SAMPLING_OVERLAP_REPORT.md` | comfyui-modal | C5 implementation contract (worker phases, invariants) | REPORT |
| A4 | `V2_BATCH_D18_VAE_SOFT_EMPTY_CACHE_GATE.md` | comfyui-modal | post-sampling→decode memory-management gate semantics | TIER-REPORT |
| A5 | `E38O_INDEPENDENT_FULL_REPOSITORY_AUDIT.md` §16 | comfyui-modal | late-mode transition decomposition (57.8 / 381 / 167) | AUDIT |
| A6 | `K1_GOLDEN_RESTORE_QUIESCENCE_SEAM_RECOVERY_REPORT.md` | comfyui-modal | K1 scope (VAE untouched); quiescence seam context | REPORT |
| A7 | `R41_DETERMINISTIC_GOLDEN_QD4_PIPELINE_REPORT.md` + `R41_E40_RECONCILIATION_MANIFEST.md` (M-03) | comfyui-modal | Golden QD VAE class design contract (arming, demand join, overlap matrix) | DESIGN |
| A8 | `K4_PYTHON_TO_DURABLE_TRUTH_AND_E37_DELTA_REPORT.md` | comfyui-modal-r42 | E37 timeline + K1R1/current-native timeline, delta table, 674.443 raw bounds | TIER-REPORT (raw mono_ns pairs cited) |
| A9 | `R42_E40_R41_GOLDEN_RECONCILIATION_REPORT.md` | comfyui-modal-r42 | R42 Golden QD VAE gate/cohort telemetry (88.881 / 98.1 / bind 32.53 / decode 376.9–387.6) | TIER-REPORT (raw events) |
| A10 | `R42B_GOLDEN_LIFECYCLE_FORENSICS.md` | comfyui-modal-r42 | degraded dual-path VAE lifecycle forensics (schedule denial → two logical loads) | FORENSIC (CONFIRMED/SUPPORTED labels) |
| A11 | `comfymodal_runtime/model_preload.py`, `cpu_snapshot_models.py`, `loader_selection.py`, `clip_qd_reader.py`, `config/v2/profiles/*.toml` | both repos | code-derived contracts (§3), config truth | CODE |
| A12 | ComfyUI core `nodes.py` (`VAELoader`, `VAEDecode`) | core checkout (hashed via r42 relative path) | native loader/decode contract | CODE |

### 1.2 Referenced by the brief, NOT_FOUND_IN_WORKSPACE

| Item searched | Method | Result |
|---|---|---|
| Phase-O reconciled SoT | glob `*PHASE_O*`, `*OC[0-9]*`; grep `Phase-O`, `Phase O` across both repos (md/txt/json) | no match |
| v2.1 SoT | filename patterns `V2.1/V21/v2.1`; content `v2.1 SoT` | no match (only `docs/V2_CANONICAL_DEPLOY_RUN_CONTROL_PLANE.md`, a v2 design spec, exists) |
| O5 / O6 / O7 / O8 reports | token grep `\bO5\b…\bO8\b` in md | only E38A matrix row "O5 = QD final GPU destination + staging buffers" and Gantt label `O5'` in `V2_GRAPH_CERT_SETUP_DECOMPOSITION.md` — not standalone reports |
| OB5 VAE evidence/candidate matrices | grep `OB5`, `OB[0-9]` | no match |
| OB7 / OB8 findings | grep `OB7`, `OB8` | no match |

Consequence: any statement in this audit that the missing documents would have owned (e.g., an authoritative candidate registry) is re-derived here from found evidence and marked as such. Cross-batch corroboration: sibling same-day outputs `OC6_OUTPUT_DURABILITY_TIMING_COMPLETENESS_2026-08-25.md` (§ evidence inventory: "Phase-O SoT + v2.1 | **NOT FOUND**") and `OC8_GOLDEN_CANDIDATE_TELEMETRY_SEMANTIC_RED_TEAM_2026-08-25.md` (preamble) independently record the same corpus as absent — the absence is a workspace-wide condition, not a search failure of this batch.

---

## 2. Candidate list

| ID | Candidate | Strategy class | Config truth (as evidenced) |
|---|---|---|---|
| CAND-1 | **E37 snapshot-resident VAE** (run `v2_2026-08-21_22-35-45`, GCP us-south1) | snapshot residency + late activation; request-time exposed work ≈ join only | `COMFYMODAL_V2_VAE_SNAPSHOT=1`, `VAE_ACTIVATION_MODE=late` era (K4 §6; E38O §16) |
| CAND-2 | **Historical R42 QD VAE class** (Golden QD4; gates `gate_20260823-162708_8bf17955`, `gate_20260823-181257_9127112e`) | request-time descriptor + producer armed at first-sampler-step + single QD pass + strict adoption/bind before decode | profile `r42-golden-qd4.toml`: `COMFYMODAL_V2_VAE_SNAPSHOT="0"` |
| CAND-3 | **C5 transfer-only overlap** (runs `v2_2026-08-14_20-11-03` Arm A / `_20-26-02` Arm B) | A: sampling_end full-load worker on critical path; B: first-step side-stream pre-copy during sampling + lane-bound rebind after sampling_end | one-off env override `sampling_first_step`; default unchanged |
| CAND-4 | **Current native/request-time VAELoader path** (r44-request-fastsafe era; REF `v2_2026-08-25_02-55-12`, K1R1 `v2_2026-08-25_06-51-50`) | request-time Volume read inside graph `VAELoader`; no snapshot residency | profile `r44-request-fastsafe.toml` sets no `VAE_SNAPSHOT` key ⇒ default 0 (K4 §11.3); cwd `production.toml` still `VAE_SNAPSHOT="1"` + `late` |
| CAND-5 | **K4 674.443 ms claim** | same mechanism as CAND-4 (the claim IS the CAND-4 VAELoader node_timing row); audited separately because the brief flagged it | — |
| CAND-6 | **R42B degraded dual-path** (request `v2-benchmark-0-803bb5dc3fd3`) | schedule-denied Golden window → native fallback loader AND later Golden QD pass; decode joins owner but native model-management load still runs at decode | `r42-golden-qd4` + `MODEL_PRELOAD=0`; Class-B DEGRADED run |
| CAND-7 | **Late-mode transition family** (E38O §16 observation over E37-era runs; D18 bounded remote decomposition) | generic `load_models_gpu(vae)` wrap between sampling_end and decode | `late` mode |

Excluded after triage (with reason): `run_vae_250/500/winner4` logs (unlabeled legacy arms, no report-tier decomposition found in this pass — listed in §9-G6); conditioning-cache material (not VAE state).

---

## 3. Contracts derived from code (not assumed)

Code surface verified this session (cwd repo unless noted): `model_preload.py:13822,13894-13916,14411-14450,14526-14571,19857-19868,19903-19928,20401,20854-20991,21382+`; `cpu_snapshot_models.py:1080-1097,1306-1339,1388-1449,2447-2684,2672,2809-2818`; `loader_selection.py:25-60`; `clip_qd_reader.py` (no VAE symbols); ComfyUI core `nodes.py:293-318,731-824`.

### 3.1 GOLDEN_VAE_PREP completion — what must be TRUE before decode may safely start

Derived clauses (each traced to code):

P1. **Exact-object identity resolved and stable.** Demand resolution selects, in order: exact snapshot VAE → snapshot container VAE → snapshot loader output → captured graph `VAELoader` output (`model_preload.py:14477-14517`); the activation key records VAE object id, patcher id, identity, compute dtype, policy, device (`:20057-20061`, `:20073-20125`).
P2. **Valid wrapper shape**: `.patcher`, `.patcher.load_device`, `.patcher.offload_device`, inspectable `.first_stage_model` (`cpu_snapshot_models.py:1315-1325`).
P3. **No meta/CUDA-invalid tensors** under snapshot validation; every first-stage tensor device checked (`:1327-1329`, rejects CUDA/meta patcher device values `:1329-1337`); floating params/buffers converted to policy dtype with marker recorded (`:1388-1444`).
P4. **Storage registry present** when a snapshot VAE is constructed (`registry = storage_registry or build_unique_storage_registry(vae)`, `:1449`; stored post-validation `:2615-2657`).
P5. **GPU/cache activation terminal-ready** for active modes: emitted only after identity / target-device / dtype / cache-membership (model-management `current_loaded_models` inspection) / residency validation (`model_preload.py:20413-20423`, `:20176-20185`).
P6. **Overlap path additionally**: every non-CUDA param/buffer CPU→CUDA copied on a side stream, stream waited, mutation lane acquired as owner `VAE`, narrow `.data` rebind performed, GPU residency + terminal `ready` recorded (`:20973-21115`). Model explicitly never mutated during sampling (`:20873-20886`).
P7. **Demand join completes before graph decode proceeds**: `_join_vae_early_activation()` waits `_future.result()`; failure falls back to the unchanged graph loader (`:14526-14571`, hook returns `_LOADER_MISS` `:14411-14450`).
P8. **CPU prefetch joined before GPU mutation**: decode demand hook waits bounded native VAE CPU prefetch; `prefetch_vae_storage()` is CPU address/page prefetch only, not Torch/CUDA load (`:14440-14449`; `cpu_snapshot_models.py:797-804`).
P9. **Device-wide completion boundary (late/sampling_end path)**: native `VAE.decode` calls `load_models_gpu([self.patcher], …)` before the decode kernel, whose `free_memory` may invoke `soft_empty_cache` = `torch.cuda.synchronize(); empty_cache(); ipc_collect()` unconditionally (D18 source pinning: `comfy/model_management.py:843-940,1944-1960`; `comfy/sd.py:1045-1071`). D18 establishes there is **no** device-wide synchronize at the `sampling_end` event itself; the later model-management barrier is the first proven device-wide completion boundary on that path.

Not found in code (stated as absence): a VAE-specific "first user"/owner-registration beyond the mutation-lane owner `"VAE"`; an explicit insertion into `comfy.model_management.current_loaded_models` inside the overlap worker (it marks `cache_present=True` after rebinding, `:21096`).

### 3.2 GOLDEN_VAE_DECODE completion — what must be TRUE before output may start

D1. `vae.decode(latent)` returns; nested latent unbound; 5-D output reshaped to image batches (core `nodes.py:310-318`).
D2. The runtime wrapper brackets the original node call: `vae_decode_start` emitted, `_decode_wall_start = time.monotonic_ns()` immediately before `original(node, …)`, duration computed in `finally` (`model_preload.py:13894-13916`). The interval covers the wrapped call including core post-processing — not later response delivery.
D3. `post_vae_decode` stamped immediately after the span; a graph-tail span opens for remaining output-node work (`:13923-13952`).
D4. Absence (stated): no CPU-transfer or image-save hook inside `VAEDecode.decode`; response serialization/save lives elsewhere, so "decode complete" ≠ "output start" — the graph tail and output encode sit between them.

### 3.3 Entry states per strategy (from code)

- **Snapshot-resident**: `CpuSnapshotModels.vae` may exist, constructed `comfy.sd.VAE`, policy-validated, storage-registry-backed (`:2447-2684`). Late mode adds no activation future/join; the original graph demand path serves VAE (`model_preload.py:19836-19847`, `:19865-19869`). The GPU-resident state consumed at decode was produced earlier (restore/prep) — that production is **precondition debt**, not free.
- **Sampling-end activation**: full-load worker submitted at the authoritative sampling-end boundary through coordinator/mutation lane (`:20726-20832`).
- **First-step overlap**: transfer-only worker during sampling + post-sampling bind (P6). Current code retains the mode (`_VAE_ACTIVATION_MODE_SAMPLING_FIRST_STEP` in VALID/ACTIVE sets, `:19857-19868`; scheduler `schedule_vae_early_activation_at_first_step` `:21382+`); `schedule_vae_early_activation_at_sampling_end` remains a no-op in that mode to preserve exactly-one-activation.
- **Native/request VAELoader**: reads VAE file from Volume, `comfy.sd.VAE(sd=sd, metadata=metadata)` construction, `throw_exception_if_invalid()`, returns into cache (core `nodes.py:795-824`); no explicit loader timer exists inside `nodes.py` — request-time visibility comes from runtime `node_timing` rows.
- **Golden QD (historical)**: nonblocking header-shaped `vae_descriptor_load`; producer armed at `first_sampler_step_proven`; single QD pass; strict adoption (exact names/shapes/count, floating dtype cast) binds payload into the module before decode (`R42A` §A2/A5; `golden_runtime_bridge.bind_vae_payload`).

---

## 4. Bespoke candidate narratives

### CAND-1 — E37 snapshot-resident VAE

Strategy: pay VAE composition once at startup; keep it resident; expose ≈nothing at request time. Evidence (all from K4's raw-timeline reconstruction of run `v2_2026-08-21_22-35-45`, plus E38O §16):

- Startup/restore-phase debt: `cpu_snapshot_vae_load` **1135.19 ms** once at startup (K4 §6, citing E37-era artifacts). This is the snapshot-composition consequence — candidate precondition debt. It is not part of any request-time number.
- Request-time exposure: **no request-time VAE read existed** (K4 §6: between first node and CLIPTextEncode enter there is only 1.2 ms). Post-sampler→VAE gap of **769.7 ms** is UNINSTRUMENTED in the E37 era ("no events in 769.7 ms").
- Decode: **381.691 ms** ledger span (226283542857→226665233757), with **"VAE lmg 57.79 ms overlapping"** — the generic `load_models_gpu(vae)` transition overlaps the decode span rather than serializing ahead of it. E38O §16 independently decomposes the same family: lmg(vae)=57.8 + decode=381 + graph-tail=167, and explains that the ~0.8 s transition vs the historical ~70 ms physical copy is generic model-management wrapping, not a new physical copy.

Completeness reading: decode-part completeness TOTAL (span-bounded). Prep-part completeness UNKNOWN for the request axis — the 769.7 ms gap was never decomposed, so what serialized prep existed (if any) cannot be stated. The snapshot debt (1135.19 ms) is real but lives outside every request-time metric; treating E37's request-time VAE cost as "~382 ms decode + ~58 ms transition" is valid only if the startup debt and the uninstrumented gap are explicitly scoped out — they were not, in any found document.

### CAND-2 — Historical R42 QD VAE class (~89–98 ms)

Strategy: request-time header descriptor; producer armed at first-step proof; ONE QD read+H2D pass; strict adoption binds weights into the module before decode.

Exactly what ~89–98 ms covered (raw events):

- Gate#3 (`gate_20260823-162708_8bf17955`): descriptor return wall **17.747 ms** (`mode=golden_descriptor`); producer armed exactly once at `first_sampler_step_proven`; **single QD pass 88.881 ms @3.772 GB/s, bytes=335,278,732, blocks 10/10** (§5, §16). In the SAME run the bind attempt failed on `KeyError('assigned_count')` AFTER successful value bind — a false-fallback defect (D1), fixed post-gate.
- Final gate (`gate_20260823-181257_9127112e`): descriptor return **30.76 ms**; **VAE QD 98.1 @3.418 GB/s**; **bind 32.5 ok** (`vae_adoption_complete assigned_count=244 cast_count=244 wall_ms=32.53`, `vae_bind_end ok=true`, owner ADOPTED, decode joined `bound_before_decode`); **VAE decode 376.9 ms**; cohort Run-1 row repeats QD 98.1 / bind 32.5 / decode 376.9 (§15, §16-D1, §C4).
- Boundary anatomy (R42B event names, healthy-run analogues): `vae_qd_submit_start → vae_qd_source_complete → vae_qd_h2d_end → vae_device_ready`. The 88.9–98.1 ms figure is the submit_start→device_ready window of the single QD pass (source read through readiness publication). It does NOT include: descriptor return (~17.7–30.8 ms), arming wait until first-step proof, adoption/bind (~32.5–36.7 ms measured separately), or decode (~376.9–387.6 ms).

Raw-vs-report tier: these are raw canonical-ledger events quoted through batch reports; R42B independently confirms the event vocabulary and byte counts on a different request. Verdict: the ~89–98 ms is REAL but PARTIAL prep coverage — it is the transport pass only. Bind/rebind happened elsewhere (adoption step), and its omission makes "89–98 ms total VAE cost" wrong by construction.

### CAND-3 — C5 transfer-only overlap (~70.2 ms pre-copy / ~0.008 ms demand join)

Arm B (`v2_2026-08-14_20-26-02`, sampling_first_step, opt-in env):

- Candidate-owned work during sampling: **precopy_wall_ms = 70.221 ms** (34.7 MB; gpu_allocated_delta_bytes=34,693,120), phase-1 side-stream copy, no lane, no mutation (report §4/§6, reconciliation metadata). This is physical work, distinct from join.
- Demand join: **join_wait_ms = 0.008**, lane_wait 0.0 — decode did not wait.
- Worker idle wait: **sampling_end_wait_ms = 3,705.41** inside **overlap_ms = 3,775.785** — off the critical path BY CONSTRUCTION, but it means the rendered waterfall row "VAE load/H2D = 3.750 s" spans load_start→terminal including that intentional wait; the report itself declares that row **not cross-arm comparable**.
- Decode: stage **416.631 ms** (waterfall) / event **417.056 ms**. Output SHA identical to Arm A (`20b10e1f…e5260`).
- Scope caveat (in-source): B's 70.2 ms is transfer-only; A's 759.0 ms is full-load-worker scope. "759 → 70 moved under sampling" is explicitly rejected by the report; only the ~70 ms/34.7 MB H2D genuinely moved.

Arm A (`v2_2026-08-14_20-11-03`, sampling_end): **load_wall_ms = 759.034** (`residency_status=resident_full`, `vae_prepare_start/end` present) ON the critical path; **lane_wait 1.903**; **consumed join_wait 29.565**; activation segment ≈ 759.0 + 1.9 + 29.6 ≈ **790.5 ms** (report arithmetic); decode stage **376.190** / event **376.602**.

Snapshot-state accounting for B: the pre-copy copies "the snapshot-restored VAE inner model" — i.e., B's cheap request-time exposure presupposes the snapshot-restored CPU state produced earlier (restore/prep side, not timed in this experiment). B's preparation work therefore cannot be serialized into the request without either (a) importing that snapshot-state debt into the serialized total, or (b) explicitly scoping it out. The report scopes it out silently by comparing against A's full-load scope instead; this audit makes the scoping explicit.

Current-code status: the first-step machinery still exists (`model_preload.py:19857-19868`, `:21382+`, worker `:20854`); production default remained `sampling_end` at C5 time; the CURRENT cwd `production.toml` resolves `VAE_ACTIVATION_MODE="late"` with `VAE_SNAPSHOT="1"` — i.e., neither C5 arm is today's default in the main clone.

### CAND-4 — Current native/request-time VAELoader path

Profile truth: `r44-request-fastsafe.toml` (r42 repo) sets NO `VAE_SNAPSHOT` key ⇒ default 0; K4 states `VAE_SNAPSHOT=0` in "the current profile". The main clone's `production.toml` still carries `VAE_SNAPSHOT="1"`/`late` — the two clones currently disagree; both facts recorded.

Mechanism: graph `VAELoader` executes at request time (K1R1 order: Any Switch → VAELoader(1277) → CLIPLoader…): file read from Modal Volume + `comfy.sd.VAE` construction + validation (core `nodes.py:795-824`). The reported timing ends with a decode-ready VAE object returned into the executor cache; the later `load_models_gpu(vae)` transition at decode is separate and (in K1R1) not separately surfaced for VAE.

Timings: see CAND-5. Loader-timer boundary: `node_timing` rows bracket node enter→exit; work before the timer (none VAE-specific found) and after it (cache insertion; decode-time model-management transition) are outside it. Decode-ready at timer end: YES (validated object returned).

### CAND-5 — K4 ~674.443 ms claim

RAW-backed, not REPORT_ONLY: canonical `node_timing` row for `VAELoader id=1277`, mono bounds **75216876845 → 75891319705** (K4 §4/§6, run `v2_2026-08-25_06-51-50`, K1 selected path). Same-class observations: REF same-region `v2_2026-08-25_02-55-12` **758.632 ms** (GCP us-east1); AWS placements **2588.817 / 1544.201 ms** (K1 Runs 2/3). Derived placement in K4's delta table: segment S6 (+666.37 ms vs E37) whose occupant is this VAELoader row plus executor cache/setup occupants (H1: VAELoader 674.4 + executor cache/setup 242.2 + invoke 15.1 across the wider plan_received→CLIP-source-start window).

Completeness: TOTAL as a node-execution measurement (read+construct+validate inside the node). PARTIAL as a serialized-prep figure: it excludes the decode-time `load_models_gpu(vae)` transition and any prefetch; and it is a *consequence* of `VAE_SNAPSHOT=0` — the residency decision moved the E37 startup debt (1135.19 ms once) into a per-request 674–759 ms (region-stable on GCP us-east1, inflating further on AWS). Contamination: NONE_PROVEN within the node interval; MIXED only in derived segment S6 (multiple occupants).

### CAND-6 — R42B degraded dual-path (bind/rebind cautionary evidence)

Request `v2-benchmark-0-803bb5dc3fd3` (Class-B DEGRADED, CONFIRMED by forensic labels):

- `golden_vae_schedule_denied` (`attempts=0`, `phase2_clip_qd4`, `vae_qd_window_timeout`) → native fallback VAELoader served the initial demand after a ~15.4 s window miss (summary `t4c_vae_load≈15.415 s` — a deadline/window artifact, NOT work; attempts=0 proves no Golden source attempt in it).
- Golden VAE worker then ran ANYWAY after `first_sampler_step_proven`: QD events `vae_qd_submit_start`(156545596251) → `vae_qd_source_complete`(+78.29 ms) → `vae_qd_h2d_end`(+144.79 ms) → `vae_device_ready`(+148.01 ms), 335,278,732 bytes, CPU destination staging.
- At decode (`vae_decode_start` 161068669239, 4,375.064 ms after device_ready) the ledger records a SEPARATE native `ModelPatcher` graph load (**59.505 ms** host duration, invocation 3, contains_registered_unet=0) and decode duration **450.862 ms**. Golden→native adoption was not implemented/evidenced: TWO logical VAE load paths ran; second physical read UNKNOWN (UNOBSERVABLE).

This candidate demonstrates the failure mode the adoption contract (CAND-2 final gate) exists to prevent, and shows a summary field (`t4c_vae_load`) that must never be read as work.

### CAND-7 — Late-mode transition family (E38O/D18)

On the late path, between `sampling_end` and decode: D18 pins pinned-source order (sampler wrapper finally → `sampling_end` emit → lane release → VAE activation submission → worker `load_models_gpu([patcher])` → `VAEDecode.decode` → native `vae.decode` internally calls `load_models_gpu` again) and proves the ~0.9–1.0 s post-sampling wall is a VAE `load_models_gpu` memory-management gate whose internal split among `torch.cuda.synchronize` / `empty_cache` / `ipc_collect` was NOT established (decomposition telemetry implemented; attribution left open). E38O §16 measures the same family as lmg(vae)=57.8 ms overlapping decode + graph-tail 167 ms on E37-era runs — note the two observations describe different runs/configurations and are not forced into one decomposition here.

---

## 5. Timing-completeness findings (classification)

Axes: MEASURED_OPERATION_COMPLETENESS ∈ {TOTAL, PARTIAL, UNKNOWN} — does the number cover the whole operation its name implies? GOLDEN_PART ∈ {prep, decode, restore-debt, join, gap, transport} with COVERAGE. CONTAMINATION ∈ {NONE_PROVEN, EXTERNAL_BLOCKING, UNRELATED_WORK, MIXED, UNKNOWN}. Full per-row detail in the CSV.

| Claim (short) | Op-completeness | Golden part / coverage | Contamination |
|---|---|---|---|
| E37 cpu_snapshot_vae_load 1135.19 ms | PARTIAL (composition event; internal phases unknown) | restore-debt / PARTIAL | UNKNOWN (startup context, co-tenants unmeasured) |
| E37 VAE decode 381.691 ms | TOTAL (ledger span) | decode / TOTAL | NONE_PROVEN |
| E37 lmg(vae) 57.79 ms | PARTIAL (transition wrap) | prep / PARTIAL | MIXED (overlaps decode span) |
| E37 post-sampler→VAE gap 769.7 ms | UNKNOWN (uninstrumented) | gap / UNKNOWN | UNKNOWN |
| R42A g3 descriptor 17.747 ms | TOTAL (descriptor return only, as named) | prep / PARTIAL (skeleton, not weights) | NONE_PROVEN |
| R42A g3 QD pass 88.881 ms | TOTAL (submit→device_ready pass) | transport / TOTAL-for-pass; prep / PARTIAL overall | NONE_PROVEN (interval); run-level MIXED (false-fallback bind defect same run) |
| Final-gate QD 98.1 ms | TOTAL (pass) | transport / TOTAL-for-pass; prep / PARTIAL overall | NONE_PROVEN |
| Final-gate bind 32.53 ms | TOTAL (adoption op) | prep / PARTIAL (adoption only) | NONE_PROVEN |
| R42 decodes 387.6 / 376.9 / 442.8 | TOTAL (spans) | decode / TOTAL | NONE_PROVEN |
| R42B t4c_vae_load ≈15,415 ms | UNKNOWN (window/deadline artifact; attempts=0 ⇒ not work) | gap / UNKNOWN | EXTERNAL_BLOCKING (window timeout) |
| R42B Golden QD ≈148.0 ms (submit→device_ready) | TOTAL (pass, CPU-destination staging) | transport / TOTAL-for-pass | UNRELATED_WORK at run level (duplicate logical path ran) |
| R42B native graph load 59.505 ms | TOTAL (host duration) | prep / PARTIAL | MIXED (native model-management concurrent w/ decode demand; duplicate logical path) |
| C5-A load_wall 759.034 ms | TOTAL (full-load worker scope, as labeled) | prep / PARTIAL-of-serialized-contract (excludes decode-side transition; includes prep/restore scope) | NONE_PROVEN |
| C5-A join 29.565 / lane 1.903 | TOTAL (join ops) | join / TOTAL | NONE_PROVEN |
| C5-B precopy 70.221 ms | TOTAL (transfer-only scope, as labeled) | transport / TOTAL; prep / PARTIAL overall | NONE_PROVEN |
| C5-B sampling_end_wait 3705.41 / overlap 3775.785 | TOTAL (idle-wait intervals) | gap / N-A (off critical path by construction) | EXTERNAL_BLOCKING (intentional wait for sampling_end) |
| C5-B join 0.008 ms | TOTAL | join / TOTAL | NONE_PROVEN |
| C5 waterfall B row "3.750 s" | UNKNOWN as comparable metric (declared non-comparable in-source) | mixed-row | MIXED (includes intentional wait) |
| K1R1/K4 VAELoader 674.443 ms | TOTAL (node execution) | prep / PARTIAL (excludes decode-side lmg transition; per-request residency choice) | NONE_PROVEN |
| REF 758.632 / AWS 2588.817 / 1544.201 | TOTAL (same class) | prep / PARTIAL | NONE_PROVEN |
| K4 S6 delta +666.37 | DERIVED (segment subtraction) | prep / PARTIAL | MIXED (multi-occupant segment) |
| K1R1 decode 349.256/349.298/349.135 | TOTAL (three evidence rows differ at 0.16 ms scale; retained as-found) | decode / TOTAL | NONE_PROVEN |
| D18 ~0.9–1.0 s post-sampling gate | PARTIAL (gate identified; internal split NOT established) | prep / PARTIAL | UNKNOWN (which of sync/empty_cache/ipc_collect consumes wall) |
| E38O 57.8+381+167 family | PARTIAL (audit decomposition) | prep+decode+tail | NONE_PROVEN (per its own audit) |

---

## 6. Snapshot/overlap accounting

**Snapshot candidates (CAND-1; CAND-3-Arm-B presupposition; cwd production.toml config).**
Snapshot residency does NOT mean zero-cost VAE. Debt ledger:

- Composition/restoration consequence: 1135.19 ms once at startup (E37-era, `cpu_snapshot_vae_load`) + restore-phase policy/validation work (code P2–P4) that is not separately request-visible.
- Request-time exposed work: tiny BY DESIGN (E37: no request read; C5-B: join 0.008 ms).
- Rule applied: demand-time totals for snapshot candidates are NOT called inclusive unless the startup debt and the uninstrumented inter-stage gaps are explicitly scoped out. No found document scoped them out explicitly; therefore E37-style request figures are classified PARTIAL-with-debt throughout.
- Serialization caveat (fact, not recommendation): a snapshot candidate's preparation cannot be fully serialized into a request without changing its semantics — its defining work happens before the request axis. Stating the fact; no position taken.

**Overlap candidates (CAND-3-B; historical R41/R42 arming design).**

- Physical work during sampling: 70.221 ms / 34.7 MB side-stream copy (measured, C5-B). Design-level: R41 freezes `SAMPLING + VAE_QD = CONDITIONAL (armed only by FIRST_SAMPLER_STEP_PROVEN)` and `VAE_GPU_MUTATION + SAMPLING = DENY` (overlap matrix), and lists "VAE QD4 during sampling slack: measurable perturbation or not" as an OPEN probe — never answered by any found artifact.
- Demand join ≠ physical work: join 0.008 ms is the wait at consumption; it must not be summed with, or substituted for, the overlapped transfer.
- Historical overlap exposure (e.g., overlap_ms=3,775.785) is NOT a serialized total; it is dominated by intentional idle waiting (3,705.41 ms).

**Native loaders (CAND-4/5).** Reported loader timing ends WITH a decode-ready VAE (construction + validation inside the node). Work after the timer but before safe decode start: the model-management transition (P9) — present for every path, separately visible only where instrumented (E37-era lmg(vae) 57.8; D18 gate family).

**Bind/rebind paths (CAND-2 adoption; CAND-6 failure mode).** Healthy R42: strict adoption binds payload into the module pre-decode (32.53 ms, `bound_before_decode`). Degraded R42B: adoption absent → two logical loads (Golden QD pass + native graph load 59.505 ms) — the state in which "QD pass time" understates realized prep by an unmeasured duplicate-work term (physical duplication UNOBSERVABLE).

---

## 7. Cross-candidate comparable-boundary table

Boundaries: **B0** prep-start (candidate begins producing decode-ready state) · **B1** decode-safe-start (Contract A/P1–P9 satisfied) · **B2** decode-end (`vae.decode` returns) · **B3** output-start (post_vae_decode stamped; graph tail begins).

| Candidate/run | B0→B1 evidence | B1→B2 (decode) | B2→B3 (tail) | Comparable? |
|---|---|---|---|---|
| E37 snapshot-late | NOT MEASURED (gap 769.7 uninstrumented; debt at startup 1135.19) | 381.691 (span) | 167 (E38O family) | decode-only |
| R42 gate#3 | descriptor 17.747 + arming-wait + QD 88.881 (bind defective that run) | 387.6 | not decomposed | partial chain |
| R42 final gate | descriptor 30.76 + QD 98.1 + bind 32.53 (bound_before_decode) | 376.9 | output collection 8.7 | closest to full B0→B3 chain |
| R42B degraded | denied-window artifact 15,415 (not work) + QD 148.0 + native graph load 59.505 | 450.862 | not decomposed | NO (dual-path) |
| C5 Arm A | load_wall 759.034 + lane 1.903 + join 29.565 (critical path) | 376.190 stage / 376.602 event | inside "post-sampling/VAE transition 731.5" + output encode 239.2 | A-arm chain yes |
| C5 Arm B | precopy 70.221 (under sampling) + join 0.008 | 416.631 stage / 417.056 event | inside transition 991.5 (host-confounded) | B≠A scope (declared) |
| K1R1 current-native | VAELoader node 674.443 (+ cache/setup occupants in wider windows) | 349.256 event / 349.298 span / 349.135 node | output encode 230.917 → persist 6.335 → assembly 45.896 | decode/tail yes; prep partial |

Only the R42 final gate and C5 Arm A approach a complete B0→B3 measured chain, and they measure DIFFERENT strategies — cross-candidate totals are not constructed here.

---

## 8. Candidate result table

| Candidate | Headline number(s) | What they actually cover | Measured-op completeness | Golden-part coverage | Contamination | Overlap required | Snapshot-state debt | Cache state at entry | Exactness evidence |
|---|---|---|---|---|---|---|---|---|---|
| E37 snapshot-resident | decode 381.691; lmg(vae) 57.79; startup composition 1135.19; gap 769.7 | decode span; transition wrap; once-only composition; unmeasured gap | decode TOTAL; prep UNKNOWN; debt PARTIAL | decode TOTAL; prep UNKNOWN | NONE_PROVEN (decode) / UNKNOWN (gap) | no (resident) | YES (producer of entry state) | snapshot registry + model-management cache (post-restore) | ledger mono pair; report-cited startup event |
| R42 QD gate#3 | QD 88.881 @3.772 GB/s; descriptor 17.747; decode 387.6 | transport pass; skeleton return; decode span | pass TOTAL; prep PARTIAL | prep PARTIAL (bind defective run) | interval NONE_PROVEN; run MIXED | yes (armed at first step) | no (VAE_SNAPSHOT=0) | Golden owner registry | raw events |
| R42 QD final gate | QD 98.1 @3.418; bind 32.53 ok; decode 376.9; descriptor 30.76 | transport + adoption + decode | pass/bind/decode each TOTAL; prep-chain near-TOTAL | prep TOTAL-ish (chain), decode TOTAL | NONE_PROVEN | yes | no | Golden owner ADOPTED, bound_before_decode | raw events + adoption telemetry |
| R42B degraded | t4c ≈15,415 (artifact); QD 148.0; native load 59.505; decode 450.862 | window timeout (attempts=0); staged pass; duplicate logical load | UNKNOWN / TOTAL / TOTAL | prep MIXED-dual-path | EXTERNAL_BLOCKING + UNRELATED_WORK(dual-path) + UNKNOWN(physical dup) | attempted, denied then late | no | split: native cache + Golden owner never adopted | CONFIRMED ledger events |
| C5 Arm A | 759.034 + 1.903 + 29.565 (≈790.5 seg); decode 376.2/376.6 | full-load worker prep on critical path; join ops; decode | prep-worker TOTAL-as-scoped; serialized-prep PARTIAL | prep PARTIAL (of Contract A whole) | NONE_PROVEN | no | indirect (source=snapshot_vae) | resident_full + cache_present=true | reconciliation metadata + events |
| C5 Arm B | precopy 70.221 (34.7 MB); join 0.008; idle-wait 3705.41; overlap 3775.785; decode 416.6/417.1 | transfer-only physical work; join; intentional wait | transfer TOTAL-as-scoped; prep PARTIAL | transport TOTAL; prep PARTIAL | NONE_PROVEN (work) / EXTERNAL_BLOCKING (wait row) | yes | presupposed (snapshot-restored inner model copied) | gpu_resident post-rebind; cache_present=true | reconciliation (worker+consumed) + SHA parity |
| Current native (K1R1/REF/AWS) | 674.443 / 758.632 / 2588.817 / 1544.201; decode 349.256± | full node execution incl. Volume read+construct+validate | node TOTAL; serialized-prep PARTIAL | prep PARTIAL | NONE_PROVEN | no | inverted: residency debt moved INTO request | executor cache post-node | node_timing mono pairs |
| K4 674.443 claim | same row as above + S6 +666.37 derived | node row; multi-occupant segment | TOTAL / DERIVED-MIXED | prep PARTIAL | interval NONE_PROVEN; segment MIXED | no | n/a (is the debt realization) | executor cache | node_timing bounds 75216876845→75891319705 |

---

## 9. Evidence gaps for future serial testing (facts only, no recommendation)

- G1 — E37-era post-sampler→VAE gap (769.7 ms) has no internal decomposition; any serialized prep/decode split for that era is impossible from artifacts.
- G2 — No matched-host A/B exists for C5 (us-east1 vs us-east4, n=1/arm); direction of the ≤~70 ms effect unresolvable from found evidence.
- G3 — R42 five-run cohort halted at 1 valid run (control-plane generation nondeterminism); variance for the 88.9–98.1 ms class unknown.
- G4 — No verified current-code timer was found for snapshot VAE composition/restoration (a delegated citation failed verification; the 1135.19 ms figure is E37-era report-tier). Location/emitter of any modern equivalent unresolved.
- G5 — R42B-class physical duplication (second disk/H2D) UNOBSERVABLE from ledgers; adoption-miss cost cannot be quantified.
- G6 — Legacy unlabeled arms (`run_vae_250.log`, `run_vae_500.log`, `run_vae_winner4.log` at r42 root) were not reconciled to any candidate in this pass.
- G7 — FastSafe/QD runtime tuning values confirmed unprovable from artifacts (K4 §7 stands; carried here because it bounds transport comparability).
- G8 — D18's which-call-consumes-the-wall question (sync vs empty_cache vs ipc_collect) remains open; affects any future serialized PREP accounting on the late/sampling_end path.
- G9 — The named Phase-O/v2.1/OB corpus is absent; if it exists elsewhere, its candidate matrices should supersede this audit's §2 registry.

---

## 10. Raw appendix (verbatim anchors)

All quotes verbatim from the hashed artifacts:

- K4 §4: `| — | VAELoader(1277) node: **674.443 ms** (reads VAE from Volume; VAE_SNAPSHOT=0) | 75216876845→75891319705 | node_timing |`
- K4 §6: `E37's VAE was snapshot-resident (COMFYMODAL_V2_VAE_SNAPSHOT=1, startup 'cpu_snapshot_vae_load' 1135.19 ms) so no request-time VAE read existed.` · `post-sampler→VAE gap (UNINSTRUMENTED in E37 era — no events in 769.7 ms)` · `VAE decode 381.691 ms (VAE lmg 57.79 ms overlapping)`
- C5 AB §4: `| VAE load wall ('load_wall_ms') | **759.0 ms** (full-load worker) | **70.2 ms** (transfer-only pre-copy) | −688.8 ms |` ; `| consumed join_wait_ms | 29.565 | **0.008** | −29.6 ms |` ; §5.6: `A's VAE activation segment at sampling_end (load 759.0 + lane 1.9 + join 29.6 ≈ **790.5 ms**)`
- C5 AB §10: `The B waterfall's 'VAE load/H2D 3.750 s' detail row includes the intentional 3.7 s sampling_end wait (overlapped) — not cross-arm comparable`
- R42A recon §5: `'vae_loader_return mode=golden_descriptor wall=17.747ms' … single QD pass 88.9ms; decode joins owner` ; §16: `QD wall=88.881ms gbps=3.772 bytes=335278732 blocks=10/10`
- R42A §15: `VAE QD 98.1 @3.418 GB/s; VAE bind 32.5 ok; VAE decode 376.9` ; §16-D1: `vae_adoption_complete assigned_count=244 cast_count=244 wall_ms=32.53 with vae_bind_end ok=true … decode joined bound_before_decode`
- R42B §4: `vae_qd_submit_start 156,545,596,251 … vae_qd_source_complete 156,623,886,547 … vae_qd_h2d_end 156,690,383,726 … vae_device_ready 156,693,605,565 … VAE native graph load … 59.505 ms host duration … vae_decode_end 161,519,529,636 Decode duration 450.862 ms` ; §2.1: `records attempts=0 … a window/deadline miss, not a failed Golden source attempt`
- D18 verdict: `do not establish which of torch.cuda.synchronize, torch.cuda.empty_cache, or torch.cuda.ipc_collect consumes the approximately 0.9-1.0 second wall`
- E38O §16: `transition 'load_models_gpu(vae)=57.8 ms' + 'VAE decode=381 ms' + 'graph-tail=167 ms'. The ~0.8 s transition … explained by generic model-management load_models_gpu wrapping, not a new physical copy.`
- Code: `registry = storage_registry or build_unique_storage_registry(vae)` (cpu_snapshot_models.py:1449) ; `_precopy_start_ns = time.monotonic_ns()` (model_preload.py:20945) ; `_decode_wall_start = time.monotonic_ns()` (model_preload.py:13910)
- Profiles: `production.toml: COMFYMODAL_V2_VAE_SNAPSHOT="1"; COMFYMODAL_V2_VAE_ACTIVATION_MODE="late"; COMFYMODAL_V2_VAE_POLICY="v1"` · `r42-golden-qd4.toml: COMFYMODAL_V2_VAE_SNAPSHOT="0"` · `r44-request-fastsafe.toml: no VAE key`

---

## 11. Code/body hashes (SHA-256)

Inputs (cwd repo unless prefixed):

```
a8a93bb47077c4a5ea5d8d4dc5eea0397d95381ce8e13e0a3a0962ed15918687  E37_CLEAN_LANE_ALGORITHM_RECOVERY_REPORT.md
c419e971acd5c635fd03d70e49f1949e46d0b889cf575feb83b8a8a61e298f9a  V2_BATCH_C5_VAE_FIRST_STEP_AB_REPORT.md
d2b61a4b9cf46db3e222fa308a1133ad7e57ccdf042b2f9d174645dfc162dbf5  V2_BATCH_C5_VAE_SAMPLING_OVERLAP_REPORT.md
803e324bf0a6c329d49ef0b015e24557313f9cd3327730396a9098b58e1cd7a2  V2_BATCH_D18_VAE_SOFT_EMPTY_CACHE_GATE.md
2f1822f36d1214483662b0d8882dc531bbdbb6dc9d4fbf1bd568f23f047e8b26  E38O_INDEPENDENT_FULL_REPOSITORY_AUDIT.md
e2372a7cdb2ec9f431bda49569cd729b825d3fd4a12ab8e4612813448b567307  K1_GOLDEN_RESTORE_QUIESCENCE_SEAM_RECOVERY_REPORT.md
263801de6212e4fa03a481a150638321f8c9f097ed9b8e55d0e690285c76989c  R41_E40_RECONCILIATION_MANIFEST.md
4006cf0d5e9867c777c9d9d2e58b79fcea174d273e3a8a7ed937f0404e2d6ba4  R41_DETERMINISTIC_GOLDEN_QD4_PIPELINE_REPORT.md
4affe1e06a3acc240418584d4e08a2210243b7de3f50e3ffe73c177c8eceeeed  comfymodal_runtime/model_preload.py
118627388a996a898d34c6034d65a20e72bd66dd30d70651e01351619ec20b8d  comfymodal_runtime/cpu_snapshot_models.py
2f3a25186ac380b3d53e8873473be43eccc05961cc017815d479e5ff46746910  comfymodal_runtime/loader_selection.py
719d7de9c3edf12da8125b1cadb47da2389b604ce3aa3e845e2f61e92b4e55c3  comfymodal_runtime/clip_qd_reader.py
85da533db7de865e6fe3846fdc08369cd2ba1864f5a3ef5314e41478f6f96ea2  config/v2/profiles/production.toml
523400fe897212c828021547fa4d4c9a2070c81a4e97d402f3c682bc85189054  r42/K4_PYTHON_TO_DURABLE_TRUTH_AND_E37_DELTA_REPORT.md
dc8f9c3afbd3a0eb141095f1651ec8ee6879a844f5bbdcf1ec3110c59bb07c5c  r42/R42_E40_R41_GOLDEN_RECONCILIATION_REPORT.md
7646077ad16803aa12b196dfef984826746815a0ed3c867b63e09bb471da0a4c  r42/R42B_GOLDEN_LIFECYCLE_FORENSICS.md
6776b87481b9db9ab262b93645acb2815fe5852451c898fd6793680c8a95e185  r42/R42_GOLDEN_GATE_REMOTE_RAW_LOG.txt
4ec199d2be75c65370d35ab38b2d17a46cdd37b8bca3a35dee8a00bfad628287  r42/R42_GOLDEN_COHORT_REMOTE_RAW_LOG.txt
98cb8f589a15f9b44e2b39f8c9a8bff47b932af76011b5d2bba91ebd1a677bbd  r42/config/v2/profiles/r44-request-fastsafe.toml
14335467d0d298f2d35711e50b4159ccaca32af5580b571d045d9176a6094f86  r42/config/v2/profiles/r42-golden-qd4.toml
1c32bce5f8c9c998766f5b4f4c4fe1ed81b3f79b023e061341b1bf0e174f307b  nodes.py (ComfyUI core, hashed via r42 checkout)
```

Outputs: the SHA-256 of this MD and of `OC5_VAE_TIMING_CLAIMS_2026-08-25.csv` are recorded in the session transcript immediately after writing (a file cannot contain its own hash; no other file was created to carry them).

— END OF OC5 AUDIT —