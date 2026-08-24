# R44G1 — Dynamic Critical-Path Telemetry and Gantt Overhaul

Batch: R44G1 · Lane: OBSERVABILITY ONLY · Worktree `../comfyui-modal-r42` · Branch `r42-golden-reconciliation` · HEAD `0c59f46e3238f421378e8852ebc548da815b70af`
No commits/push/merge/reset/revert/clean/stash. No deploy. No Modal run. No paid requests. No runtime/model-path code touched.

Evidence basis: R44E request `v2-benchmark-0-d5df02fd8dba` artifacts at
`ComfyUI\comfymodal-data\benchmarks\runs\v2_2026-08-24_02-49-32\` (`run_0.json`, `run_001_sample.json`, `summary.json`),
plus `R44E_FASTSAFE_FULL_EVIDENCE_AND_DECOMPOSITION_REPORT.md`, `R44E_..._RAW_LOG.txt`, `R44E_R44D_EXISTING_EVIDENCE_INVENTORY.md`, `R44D_FASTSAFE_ACTIVATION_COLD_GATE_REPORT.md`.

---

## 1. Files / functions changed (ALL NEW FILES — zero edits to existing files)

| File | Status | Contents |
|---|---|---|
| `comfymodal_runtime/dynamic_gantt.py` | NEW (61,528 B) | The entire dynamic telemetry renderer (stdlib-only, no package imports so the CLI runs standalone) |
| `tools/render_dynamic_gantt.py` | NEW (3,638 B) | CLI: `python tools/render_dynamic_gantt.py <run_dir> [--windows ...] [--width N] [--out FILE]`; UTF-8 stdout reconfiguration for Windows cp1252 consoles |
| `tests/test_r44g1_dynamic_gantt.py` | NEW | 17 focused tests (§10) |
| `R44G1_DYNAMIC_GANTT_AND_TELEMETRY_REPORT.md` | NEW | This report |

Public API (pinned before implementation; tests written against it):

```python
GANTT_TITLE = "V2 DYNAMIC CRITICAL PATH GANTT"
@dataclass GanttRow: key, label, parent_key, kind("exact"|"broad"|"point"|"derived"|"container"),
                     role("critical"|"background"), lane, start_mono_ns, end_mono_ns,
                     duration_ms, source_refs:list[str], meta:dict
@dataclass DynamicPayload: request_id, rows, raw, anchors, warnings
load_run_artifacts(run_dir) -> DynamicPayload
build_rows(payload) -> list[GanttRow]            # pure, idempotent
compute_windows(payload, rows) -> dict[str,(start_mono_ns,end_mono_ns)]
render_window(rows, window_bounds, title, width_chars=110, origin_mono_ns=None) -> str
closure_reports(payload, rows) -> list[str]
completeness_matrix(payload) -> str
detect_label_conflicts(payload, rows) -> list[str]
critical_path_summary(payload, rows) -> str
render_full_report(payload, windows=None) -> str
render_run_dir(run_dir) -> str
truncate_label(label, limit=38) -> str           # deterministic long-label helper
```

Key internals (`dynamic_gantt.py`): `_derive_anchor_ns` / `_to_mono` (epoch↔mono unification), `_ev/_gt_span/_led_span/_samp` (multi-source event lookup), `_classify_clip_forward` (outer-vs-inner disambiguation), `_seq_places` (deterministic anchoring of timestamp-less exact durations), `build_rows` (registry-driven row construction + dynamic unregistered-activity discovery), `compute_windows` + `_auto_dense_window`, `_bar/_ruler/_row_line/render_window` (█-only rendering), `closure_reports` (containment/overlap/nesting validation), `completeness_matrix`, `detect_label_conflicts`, `critical_path_summary` (union-based), `render_full_report`.

Deliberate scoping decision: the live-harness auto-print wiring (one call to `render_full_report` next to the existing `attach_waterfall` sites in `canonical_execution.py` / `modal_client.py`, or post-run in `tools/benchmark_v2_direct.py`) was NOT installed because every one of those files is currently dirty under concurrent agents (R44F et al.). The renderer is fully wired locally via `render_run_dir`/CLI; integration is a one-line follow-up for the reconciliation owner. Nothing about measurement, model loading, deployment, or request execution changed.

## 2. Old Gantt weaknesses

1. **Misleading outer/inner conflation**: legacy mappers (`gantt_telemetry.py:185-186`, grouping in `gantt_canonical.py:65`) label the OUTER encode window `"CLIP forward"`. In R44E terms that presented a ~4.69 s wrapper as if it were the ~2.33 s transformer forward. This renderer can never reproduce that: when both evidences exist the only legal labels are `CLIP outer encode`, `CLIP load_models_gpu (exact)`, `CLIP inner forward`; a bare `CLIP forward` row label is a detected conflict.
2. **Static stage sets**: old paths assumed a fixed small set of stage names; sparse/native/Golden/fallback runs silently lost everything else. New renderer discovers whatever exists (registered OR unregistered) and renders only that.
3. **Fixed/arbitrary windows**: legacy fixed windows omitted important work (e.g., UNET source-prep overlap before UNETLoader demand). Windows now derive from actual event boundaries.
4. **No broad-vs-exact distinction**: broad transfer windows were substituted for exact physical copies (or vice versa) across batches. Both now always coexist with honest labels.
5. **No overlap semantics**: nothing distinguished serial critical work from hidden background activity; summing rows double-counted (e.g., prep under CLIP encode).
6. **Decomposition data buried in `run_0.json`**: agents had to mine JSON manually; closures/completeness now print directly.

## 3. Event-to-row architecture

`load_run_artifacts` normalizes ALL available sources into one payload (each source optional — graceful across native/Golden/FastSafe/sparse/fallback runs):

- `result.trace.events[]` — named mono-ns events incl. `clip_fast_load_start/end`, `unet_source_prep_armed/joined`, `unet_fastsafe_pipeline`, `clip_raw_encode_start/end`, inner/outer `clip_forward_end` variants
- GPU-lane trace rows (`UNET H2D`, `CLIP forward`, VAE/output rows) wherever stored (events list / gantt_telemetry spans / ledger spans)
- `result.gantt_telemetry.spans`, top-level + result `canonical_ledger` (spans/events/serial_ledger)
- `waterfall` / `waterfall_local` stages, `timing`, `result._restore_timing`, `result.phase_durations_ms`
- `pre_sampler_structured_report.cpu_owner_records` (incl. R44E CUDA-delta fields), `loader_selection` (fallback detection), t4–t8 epoch keys from `run_001_sample.json`

Clock domains unified: epoch-second t-keys converted via the constant anchor `A = wall_unix_ns − mono_ns` (derived from any dual-stamped pair, e.g. `remote_result_emit_*`), so every row shares ONE absolute monotonic timeline.

Registry (~30 canonical keys) maps source names/keys → `RowSpec(label, parent, kind, role, lane)`. Legacy alias rule: a span named `CLIP forward` resolves to `CLIP inner forward` when its duration matches inner evidence (±5%), or to `CLIP outer encode` when it matches the outer wrapper magnitude; when both exist, canonical triple naming is enforced. Anything not in the registry is STILL rendered — grouped as `(unregistered) <source-name>` background rows sorted by start — so unknown/future events are never silently dropped (dynamic discovery).

Timestamp-less exact durations (e.g. `fastsafe_copy_wall_ms`) receive deterministic estimated anchors (`meta["anchoring"]`: parent-start or sequential placement); the measured duration value itself is always shown verbatim and cited via `source_refs` (e.g. `trace.events:clip_fast_load_end.fastsafe_copy_wall_ms`).

## 4. Hierarchy design

Parents/children purely from registry relations among PRESENT rows (never hardcoded mandatory rows):

```
restore → restore bootstrap
request/setup → remote method setup, prompt executor cache setup, restore→method-entry gap
VAE loader (t4c)
CLIPLoader (t4 node) → descriptor/header · FastSafe setup · FastSafe copy · tensor views · Comfy construction
CLIP outer encode → CLIP load_models_gpu · CLIP inner forward
UNET source prep                      [background/broad]
UNETLoader (t4b node) → entry/prep join · gate wait · FastSafe setup · FastSafe copy · instantiate
                       · adoption → header detect · skeleton · bind · identity validation
UNET H2D (broad window)               [coexists with exact children]
sampler startup · sampling · post-sampling transition · VAE decode · output encode · result persistence
```

Children indent 2 spaces per depth level in every window render.

## 5. Dynamic-window algorithm

`compute_windows` derives each window strictly from present boundary events; a window whose boundaries are absent is skipped without error:

| Window | Start bound | End bound |
|---|---|---|
| FULL APPLICATION | restore-method start / ledger start | ledger end / result emit |
| MODEL PREPARATION / PRE-SAMPLER | method entry | sampler start |
| CLIP DETAIL | `t4_clip_load_start` | conditioning ready = max(t5_text_encode_end, clip_raw_encode end) |
| UNET DETAIL | min(prep armed, t4b start) — includes pre-demand overlap | max(t4b end, pipeline ts) |
| SAMPLER TRANSITION | sampler-node begin (t4b end class) | sampling start (entire node→sampling interval) |
| POST-SAMPLING / VAE | sampling end | output persistence end |
| AUTO-DENSE | deterministic: candidate clusters = maximal regions where ≥3 rows overlap within a 4 s sliding span; pick max (row count, then busy ms, then earliest start); expand to contain intersecting rows; clamp ≤ min(full span, 8 s) |

All seven rendered for the R44E artifact (§9).

## 6. Critical path vs overlapping activity

- Rows are classified `critical` or `background` at registry level (e.g. UNET source prep = background; node windows/exact ops = critical).
- Bars for ALL rows sit on the same absolute monotonic axis per window, so concurrency is visually obvious (UNET prep bar literally runs underneath the CLIP encode bars).
- For each background row: `overlap = |B ∩ union(critical)|`; `critical_path_contribution_ms = duration − overlap` (≥0). Overlapping rows are NEVER summed anywhere; the summary total is union-based coverage of critical rows only.
- Real-artifact precision note: prep wall 4827.587 ms, overlap with CLIP encode 4689.870 ms (97.15%), remaining tail 137.717 ms — of which ≈75.3 ms further overlaps the UNETLoader node entry segment (node starts at mono ≈225397.5M before prep join ends 225472.8M), so the TRUE uncovered contribution is **≈62.4 ms**, exactly what the renderer prints. This is more honest than the ≈0.14 s upper-bound framing.

## 7. Closure logic

Emits `CLIP NODE CLOSURE`, `CLIP ENCODE CLOSURE`, `UNET NODE CLOSURE` when components exist. Validation before any residual math:
(a) each component fits inside the parent (25 ms clock-skew tolerance);
(b) components pairwise non-overlapping (>1 ms overlap ⇒ `CANNOT SUM` + parallel listing, no residual claimed);
(c) nesting: a component contained in another listed component is dropped from the sum with an explicit note (no double counting);
(d) parent−Σcomponents printed as residual with pct; `✓ closes` only when residual <5% AND <250 ms.

R44E artifact results: CLIP node residual 181.1 ms (3.75%) ✓ · CLIP encode residual 75.8 ms (1.62%) ✓ · UNET node residual 0.0 ms (0.00%) ✓ with explicit notes that the transfer window decomposes into setup+copy+instantiate+adoption (740.8 ms, excluded from sum) and that adoption-grandchildren were dropped as nested.

## 8. Data completeness logic

Registry-driven checklist printed at report end. Each absent metric carries its expected event/key AND closest available proxy — never a bare "missing". On the R44E artifact: 15 PRESENT, 2 MISSING (`sampler-start decomposition` → proxy `waterfall.sampler_node_to_sampling`; `post-sampling decomposition` → proxy `waterfall.post_sampling_transition`) — matching reality, since only aggregate stages exist for those two intervals.

Label-conflict sanity checks (`detect_label_conflicts`): bare `CLIP forward` while both outer+inner exist; broad/exact substitution; duplicate labels scoped per `(parent_key,label)` (so CLIP and UNET may each legitimately own a "FastSafe copy (exact)"). Output: `LABEL CONFLICTS: none`.

## 9. Example rendering — EXISTING R44E artifact, COMPLETE output

Command: `python tools/render_dynamic_gantt.py "...\runs\v2_2026-08-24_02-49-32"` (captured verbatim, UTF-8, 354 lines):

```text
V2 DYNAMIC CRITICAL PATH GANTT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
request: v2-benchmark-0-d5df02fd8dba   profile: r44-request-fastsafe   artifact: run_0.json
loader fallback: none

── FULL APPLICATION ──────────────────────────────────────────────────────────────────────────────────────────
scale: 1 char = 276.8 ms | axis 18.8 s | origin = restore
····································································

Restore (application)                  │█                                                                   │ @+0.000s
  restore bootstrap                    │▋██▎                                                                │ 784.3 ms @+0.115s
(unregistered) restore method          │███▎                                                                │ 906.0 ms @+0.000s · [background]
(unregistered) restore:early           │▎                                                                   │ 62.5 ms @+0.000s · [background]
(unregistered) v2_startup_post_snapsh… │▊██▎                                                                │ 846.0 ms @+0.063s · [background]
(unregistered) restore:eviction        │▏                                                                   │ 24.9 ms @+0.063s · [background]
(unregistered) restore:snapshot        │▏                                                                   │ 0.032 ms @+0.088s · [background]
(unregistered) clip_manifest_available │▏                                                                   │ 0.004 ms @+0.088s · [background]
(unregistered) restore:preamble        │▏                                                                   │ 26.9 ms @+0.088s · [background]
(unregistered) v2_startup_snapshot_ex… │   ▏                                                                │ 0.562 ms @+0.872s · [background]
(unregistered) restore:preload         │   ▏                                                                │ 0.21 ms @+0.899s · [background]
(unregistered) restore:finalize        │   ▏                                                                │ 6.768 ms @+0.899s · [background]
request/setup                          │   ▌▊                                                               │ 373.6 ms @+0.956s
  remote method setup                  │   ▍                                                                │ 110.0 ms @+0.956s
  prompt executor cache setup          │   ▏▊                                                               │ 263.6 ms @+1.066s
(unregistered) request:identity-captu… │   ▏                                                                │ 0.113 ms @+0.956s · [background]
(unregistered) request:plan-deseriali… │   ▏                                                                │ 0.348 ms @+0.964s · [background]
(unregistered) request:setup-schedule  │   ▎                                                                │ 74.3 ms @+0.981s · [background]
(unregistered) request:executor-run    │   ▏████████████████████████████████████████████████████████████████│ 17,764 ms @+1.056s · [background]
(unregistered) pre_sampler_cache_key_… │   ▏                                                                │ 0.002 ms @+1.056s · [background]
(unregistered) executor:graph-executi… │   ▏███████████████████████████████████████████████████████████████▉│ 17,713 ms @+1.057s · [background]
(unregistered) v2_startup_first_promp… │   ▏███████████████████████████████████████████████████████████████▊│ 17,691 ms @+1.067s · [background]
VAE loader (t4c)                       │    ▏▉                                                              │ 324.4 ms @+1.333s
CLIPLoader (t4 node)                   │     ▏█████████████████▍                                            │ 4825.5 ms @+1.660s
  descriptor/header (exact)            │     ▏▏                                                             │ 27.5 ms @+1.660s
  FastSafe setup (exact)               │      ▏                                                             │ 11.3 ms @+1.688s
  FastSafe copy (exact)                │      ▉██████▏                                                      │ 1934.7 ms @+1.699s
  tensor views (exact)                 │             ▏                                                      │ 0.335 ms @+3.634s
  Comfy construction (exact)           │             ▉████████▊                                             │ 2670.5 ms @+3.634s
UNET source prep                       │                       ▋████████████████▉                           │ 4827.6 ms @+6.486s · [background]
CLIP outer encode                      │                       ▋████████████████▍                           │ 4689.9 ms @+6.486s
  CLIP load_models_gpu (exact)         │                       ▋███████▋                                    │ 2283.6 ms @+6.486s
  CLIP inner forward                   │                               ▏████████▍                           │ 2330.5 ms @+8.844s
(unregistered) clip_tokenize_end       │                       ▏                                            │ 47.1 ms @+6.499s · [background]
(unregistered) clip_scheduled_conditi… │                       ▍████████████████▍                           │ 4628.8 ms @+6.547s · [background]
(unregistered) clip_gpu_prepare_end    │                       ▍███████▉                                    │ 2288.4 ms @+6.555s · [background]
(unregistered) CLIP forward            │                               ▏████████▍                           │ 2329.3 ms @+8.844s · [background]
UNETLoader (t4b node)                  │                                        ▍██▋                        │ 819.5 ms @+11.238s
  entry/prep join (derived)            │                                        ▎                           │ 76.0 ms @+11.238s
  gate wait (exact)                    │                                        ▏                           │ 1.089 ms @+11.314s
  FastSafe setup (exact)               │                                        ▏                           │ 3.859 ms @+11.315s
  FastSafe copy (exact)                │                                        ▏██▏                        │ 624.7 ms @+11.319s
  instantiate (exact)                  │                                           ▏                        │ 0.354 ms @+11.944s
  adoption (exact)                     │                                           ▍                        │ 111.9 ms @+11.944s
    header detect                      │                                           ▏                        │ 5.526 ms @+11.944s
    skeleton                           │                                           ▎                        │ 80.8 ms @+11.950s
    bind                               │                                           ▏                        │ 13.7 ms @+12.031s
    identity validation                │                                           ▏                        │ 11.8 ms @+12.044s
UNET H2D (broad window)                │                                        ▏██▋                        │ 741.8 ms @+11.315s
sampler startup (node→sampling)        │                                           ▎█████▏                  │ 1461.5 ms @+12.123s
sampling                               │                                                 ▉████████████▌     │ 3727.4 ms @+13.584s
post-sampling transition               │                                                              ▌█▉   │ 649.9 ms @+17.312s
(unregistered) vae_decode_end          │                                                                ▏█▋ │ 494.4 ms @+17.962s · [background]
VAE decode                             │                                                                ▏█▋ │ 494.3 ms @+17.962s
(unregistered) output_encode_end       │                                                                  ▍▊│ 303.8 ms @+18.456s · [background]
output encode                          │                                                                  ▍▊│ 303.8 ms @+18.456s
result persistence                     │                                                                  ▍█│ 363.5 ms @+18.456s
(unregistered) result:assembly         │                                                                   ▎│ 59.6 ms @+18.760s · [background]
(unregistered) output_persist_end      │                                                                   ▏│ 9.343 ms @+18.760s · [background]
legend: █ busy bar (▏▎▍▌▋▊▉ sub-char precision); [background] marks off-critical-path activity; see CRITICAL PATH SUMMARY

── MODEL PREPARATION / PRE-SAMPLER ───────────────────────────────────────────────────────────────────────────
scale: 1 char = 185.7 ms | axis 12.6 s | origin = mono:0
····································································

request/setup                          │██▏                                                                 │ 373.6 ms @+0.000s
  remote method setup                  │▋                                                                   │ 110.0 ms @+0.000s
  prompt executor cache setup          │▍█▏                                                                 │ 263.6 ms @+0.110s
(unregistered) request:identity-captu… │▏                                                                   │ 0.113 ms @+0.000s · [background]
(unregistered) request:plan-deseriali… │▏                                                                   │ 0.348 ms @+0.008s · [background]
(unregistered) request:setup-schedule  │▍                                                                   │ 74.3 ms @+0.026s · [background]
(unregistered) request:executor-run    │▌███████████████████████████████████████████████████████████████████│ 17,764 ms @+0.100s · [background]
(unregistered) pre_sampler_cache_key_… │▏                                                                   │ 0.002 ms @+0.101s · [background]
(unregistered) executor:graph-executi… │▌███████████████████████████████████████████████████████████████████│ 17,713 ms @+0.101s · [background]
(unregistered) v2_startup_first_promp… │▍███████████████████████████████████████████████████████████████████│ 17,691 ms @+0.111s · [background]
VAE loader (t4c)                       │  ▉▊                                                                │ 324.4 ms @+0.378s
CLIPLoader (t4 node)                   │   ▎█████████████████████████▊                                      │ 4825.5 ms @+0.704s
  descriptor/header (exact)            │   ▏                                                                │ 27.5 ms @+0.704s
  FastSafe setup (exact)               │   ▏▏                                                               │ 11.3 ms @+0.732s
  FastSafe copy (exact)                │    ▉█████████▍                                                     │ 1934.7 ms @+0.743s
  tensor views (exact)                 │              ▏                                                     │ 0.335 ms @+2.678s
  Comfy construction (exact)           │              ▋█████████████▊                                       │ 2670.5 ms @+2.678s
UNET source prep                       │                             ▎█████████████████████████▊            │ 4827.6 ms @+5.530s · [background]
CLIP outer encode                      │                             ▎█████████████████████████▏            │ 4689.9 ms @+5.530s
  CLIP load_models_gpu (exact)         │                             ▎████████████▏                         │ 2283.6 ms @+5.530s
  CLIP inner forward                   │                                          ▌████████████▏            │ 2330.5 ms @+7.888s
(unregistered) clip_tokenize_end       │                             ▏▏                                     │ 47.1 ms @+5.543s · [background]
(unregistered) clip_scheduled_conditi… │                              ▉████████████████████████▏            │ 4628.8 ms @+5.591s · [background]
(unregistered) clip_gpu_prepare_end    │                              ▉███████████▌                         │ 2288.4 ms @+5.599s · [background]
(unregistered) CLIP forward            │                                          ▌████████████▏            │ 2329.3 ms @+7.888s · [background]
UNETLoader (t4b node)                  │                                                       ▋███▊        │ 819.5 ms @+10.282s
  entry/prep join (derived)            │                                                       ▍            │ 76.0 ms @+10.282s
  gate wait (exact)                    │                                                       ▏            │ 1.089 ms @+10.358s
  FastSafe setup (exact)               │                                                       ▏            │ 3.859 ms @+10.360s
  FastSafe copy (exact)                │                                                       ▎███▏        │ 624.7 ms @+10.363s
  instantiate (exact)                  │                                                           ▏        │ 0.354 ms @+10.988s
  adoption (exact)                     │                                                           ▋        │ 111.9 ms @+10.988s
    header detect                      │                                                           ▏        │ 5.526 ms @+10.988s
    skeleton                           │                                                           ▍        │ 80.8 ms @+10.994s
    bind                               │                                                           ▏        │ 13.7 ms @+11.075s
    identity validation                │                                                           ▏        │ 11.8 ms @+11.088s
UNET H2D (broad window)                │                                                       ▎███▊        │ 741.8 ms @+10.360s
sampler startup (node→sampling)        │                                                            ▉███████│ 1461.5 ms @+11.167s
legend: █ busy bar (▏▎▍▌▋▊▉ sub-char precision); [background] marks off-critical-path activity; see CRITICAL PATH SUMMARY

── CLIP DETAIL ───────────────────────────────────────────────────────────────────────────────────────────────
scale: 1 char = 139.9 ms | axis 9.5 s | origin = mono:0
····································································

(unregistered) request:executor-run    │████████████████████████████████████████████████████████████████████│ 17,764 ms @+-0.604s · [background]
(unregistered) executor:graph-executi… │████████████████████████████████████████████████████████████████████│ 17,713 ms @+-0.603s · [background]
(unregistered) v2_startup_first_promp… │████████████████████████████████████████████████████████████████████│ 17,691 ms @+-0.593s · [background]
CLIPLoader (t4 node)                   │██████████████████████████████████▌                                 │ 4825.5 ms @+0.000s
  descriptor/header (exact)            │▎                                                                   │ 27.5 ms @+0.000s
  FastSafe setup (exact)               │▏                                                                   │ 11.3 ms @+0.028s
  FastSafe copy (exact)                │▊█████████████▏                                                     │ 1934.7 ms @+0.039s
  tensor views (exact)                 │              ▏                                                     │ 0.335 ms @+1.974s
  Comfy construction (exact)           │              ▉██████████████████▏                                  │ 2670.5 ms @+1.974s
UNET source prep                       │                                  ▌█████████████████████████████████│ 4827.6 ms @+4.826s · [background]
CLIP outer encode                      │                                  ▌████████████████████████████████▉│ 4689.9 ms @+4.826s
  CLIP load_models_gpu (exact)         │                                  ▌███████████████▊                 │ 2283.6 ms @+4.826s
  CLIP inner forward                   │                                                   ▋███████████████▉│ 2330.5 ms @+7.184s
(unregistered) clip_tokenize_end       │                                  ▍                                 │ 47.1 ms @+4.839s · [background]
(unregistered) clip_scheduled_conditi… │                                  ▏████████████████████████████████▉│ 4628.8 ms @+4.887s · [background]
(unregistered) clip_gpu_prepare_end    │                                  ▏████████████████▍                │ 2288.4 ms @+4.895s · [background]
(unregistered) CLIP forward            │                                                   ▋███████████████▉│ 2329.3 ms @+7.184s · [background]
legend: █ busy bar (▏▎▍▌▋▊▉ sub-char precision); [background] marks off-critical-path activity; see CRITICAL PATH SUMMARY

── UNET DETAIL ───────────────────────────────────────────────────────────────────────────────────────────────
scale: 1 char = 81.9 ms | axis 5.6 s | origin = mono:0
····································································

(unregistered) request:executor-run    │████████████████████████████████████████████████████████████████████│ 17,764 ms @+-5.430s · [background]
(unregistered) executor:graph-executi… │████████████████████████████████████████████████████████████████████│ 17,713 ms @+-5.429s · [background]
(unregistered) v2_startup_first_promp… │████████████████████████████████████████████████████████████████████│ 17,691 ms @+-5.419s · [background]
UNET source prep                       │██████████████████████████████████████████████████████████▉         │ 4827.6 ms @+0.000s · [background]
CLIP outer encode                      │▉████████████████████████████████████████████████████████▎          │ 4689.9 ms @+0.000s
  CLIP load_models_gpu (exact)         │▉██████████████████████████▉                                        │ 2283.6 ms @+0.000s
  CLIP inner forward                   │                            ▎████████████████████████████▎          │ 2330.5 ms @+2.358s
(unregistered) clip_tokenize_end       │▋                                                                   │ 47.1 ms @+0.013s · [background]
(unregistered) clip_scheduled_conditi… │▎████████████████████████████████████████████████████████▎          │ 4628.8 ms @+0.061s · [background]
(unregistered) clip_gpu_prepare_end    │▏███████████████████████████▊                                       │ 2288.4 ms @+0.069s · [background]
(unregistered) CLIP forward            │                            ▎████████████████████████████▎          │ 2329.3 ms @+2.358s · [background]
UNETLoader (t4b node)                  │                                                         ▏██████████│ 819.5 ms @+4.752s
  entry/prep join (derived)            │                                                         ▏▉         │ 76.0 ms @+4.752s
  gate wait (exact)                    │                                                          ▏         │ 1.089 ms @+4.828s
  FastSafe setup (exact)               │                                                          ▏         │ 3.859 ms @+4.829s
  FastSafe copy (exact)                │                                                          ▏███████▋ │ 624.7 ms @+4.833s
  instantiate (exact)                  │                                                                  ▏ │ 0.354 ms @+5.458s
  adoption (exact)                     │                                                                  ▍▉│ 111.9 ms @+5.458s
    header detect                      │                                                                  ▏ │ 5.526 ms @+5.458s
    skeleton                           │                                                                  ▍▋│ 80.8 ms @+5.464s
    bind                               │                                                                   ▏│ 13.7 ms @+5.545s
    identity validation                │                                                                   ▏│ 11.8 ms @+5.558s
UNET H2D (broad window)                │                                                          ▏████████▉│ 741.8 ms @+4.829s
legend: █ busy bar (▏▎▍▌▋▊▉ sub-char precision); [background] marks off-critical-path activity; see CRITICAL PATH SUMMARY

── SAMPLER TRANSITION ────────────────────────────────────────────────────────────────────────────────────────
scale: 1 char = 22.5 ms | axis 1.5 s | origin = mono:0
····································································

(unregistered) request:executor-run    │████████████████████████████████████████████████████████████████████│ 17,764 ms @+-11.002s · [background]
(unregistered) executor:graph-executi… │████████████████████████████████████████████████████████████████████│ 17,713 ms @+-11.001s · [background]
(unregistered) v2_startup_first_promp… │████████████████████████████████████████████████████████████████████│ 17,691 ms @+-10.991s · [background]
sampler startup (node→sampling)        │  ▏█████████████████████████████████████████████████████████████████│ 1461.5 ms @+0.065s
legend: █ busy bar (▏▎▍▌▋▊▉ sub-char precision); [background] marks off-critical-path activity; see CRITICAL PATH SUMMARY

── POST-SAMPLING / VAE ───────────────────────────────────────────────────────────────────────────────────────
scale: 1 char = 22.2 ms | axis 1.5 s | origin = mono:0
····································································

(unregistered) request:executor-run    │████████████████████████████████████████████████████████████████████│ 17,764 ms @+-16.256s · [background]
(unregistered) executor:graph-executi… │█████████████████████████████████████████████████████████████████▊  │ 17,713 ms @+-16.255s · [background]
(unregistered) v2_startup_first_promp… │█████████████████████████████████████████████████████████████████▏  │ 17,691 ms @+-16.245s · [background]
post-sampling transition               │█████████████████████████████▎                                      │ 649.9 ms @+0.000s
(unregistered) vae_decode_end          │                             ▊█████████████████████▋                │ 494.4 ms @+0.650s · [background]
VAE decode                             │                             ▊█████████████████████▋                │ 494.3 ms @+0.650s
(unregistered) output_encode_end       │                                                   ▍█████████████▎  │ 303.8 ms @+1.145s · [background]
output encode                          │                                                   ▍█████████████▎  │ 303.8 ms @+1.145s
result persistence                     │                                                   ▍████████████████│ 363.5 ms @+1.145s
(unregistered) result:assembly         │                                                                 ▊██│ 59.6 ms @+1.448s · [background]
(unregistered) output_persist_end      │                                                                 ▍  │ 9.343 ms @+1.449s · [background]
legend: █ busy bar (▏▎▍▌▋▊▉ sub-char precision); [background] marks off-critical-path activity; see CRITICAL PATH SUMMARY

── AUTO-DENSE ────────────────────────────────────────────────────────────────────────────────────────────────
scale: 1 char = 117.6 ms | axis 8.0 s | origin = mono:0
····································································

Restore (application)                  │█                                                                   │ @+0.000s
  restore bootstrap                    │▏██████▋                                                            │ 784.3 ms @+0.115s
(unregistered) restore method          │███████▊                                                            │ 906.0 ms @+0.000s · [background]
(unregistered) restore:early           │▌                                                                   │ 62.5 ms @+0.000s · [background]
(unregistered) v2_startup_post_snapsh… │▌██████▊                                                            │ 846.0 ms @+0.063s · [background]
(unregistered) restore:eviction        │▎                                                                   │ 24.9 ms @+0.063s · [background]
(unregistered) restore:snapshot        │▏                                                                   │ 0.032 ms @+0.088s · [background]
(unregistered) clip_manifest_available │▏                                                                   │ 0.004 ms @+0.088s · [background]
(unregistered) restore:preamble        │▎                                                                   │ 26.9 ms @+0.088s · [background]
(unregistered) v2_startup_snapshot_ex… │       ▏                                                            │ 0.562 ms @+0.872s · [background]
(unregistered) restore:preload         │       ▏                                                            │ 0.21 ms @+0.899s · [background]
(unregistered) restore:finalize        │       ▏                                                            │ 6.768 ms @+0.899s · [background]
request/setup                          │        ▉██▎                                                        │ 373.6 ms @+0.956s
  remote method setup                  │        ▉▏                                                          │ 110.0 ms @+0.956s
  prompt executor cache setup          │         ▉█▎                                                        │ 263.6 ms @+1.066s
(unregistered) request:identity-captu… │        ▏                                                           │ 0.113 ms @+0.956s · [background]
(unregistered) request:plan-deseriali… │        ▏                                                           │ 0.348 ms @+0.964s · [background]
(unregistered) request:setup-schedule  │        ▋                                                           │ 74.3 ms @+0.981s · [background]
(unregistered) request:executor-run    │        ▏███████████████████████████████████████████████████████████│ 17,764 ms @+1.056s · [background]
(unregistered) pre_sampler_cache_key_… │        ▏                                                           │ 0.002 ms @+1.056s · [background]
(unregistered) executor:graph-executi… │        ▏███████████████████████████████████████████████████████████│ 17,713 ms @+1.057s · [background]
(unregistered) v2_startup_first_promp… │         ▉██████████████████████████████████████████████████████████│ 17,691 ms @+1.067s · [background]
VAE loader (t4c)                       │           ▋██▏                                                     │ 324.4 ms @+1.333s
CLIPLoader (t4 node)                   │              ▉████████████████████████████████████████▏            │ 4825.5 ms @+1.660s
  descriptor/header (exact)            │              ▎                                                     │ 27.5 ms @+1.660s
  FastSafe setup (exact)               │              ▏                                                     │ 11.3 ms @+1.688s
  FastSafe copy (exact)                │              ▌███████████████▉                                     │ 1934.7 ms @+1.699s
  tensor views (exact)                 │                              ▏                                     │ 0.335 ms @+3.634s
  Comfy construction (exact)           │                              ▏██████████████████████▋              │ 2670.5 ms @+3.634s
UNET source prep                       │                                                       ▉████████████│ 4827.6 ms @+6.486s · [background]
CLIP outer encode                      │                                                       ▉████████████│ 4689.9 ms @+6.486s
  CLIP load_models_gpu (exact)         │                                                       ▉████████████│ 2283.6 ms @+6.486s
(unregistered) clip_tokenize_end       │                                                       ▍            │ 47.1 ms @+6.499s · [background]
(unregistered) clip_scheduled_conditi… │                                                       ▍████████████│ 4628.8 ms @+6.547s · [background]
(unregistered) clip_gpu_prepare_end    │                                                       ▎████████████│ 2288.4 ms @+6.555s · [background]
legend: █ busy bar (▏▎▍▌▋▊▉ sub-char precision); [background] marks off-critical-path activity; see CRITICAL PATH SUMMARY

══ CLIP NODE CLOSURE ══
parent: CLIPLoader (t4 node)  4825.5 ms
  component descriptor/header (exact)                  27.5 ms
  component FastSafe setup (exact)                     11.3 ms
  component FastSafe copy (exact)                      1934.7 ms
  component tensor views (exact)                       0.335 ms
  component Comfy construction (exact)                 2670.5 ms
  sum(components)                               4644.4 ms
  residual                                      181.1 ms (3.75% of parent)
  ✓ closes (residual <5% and <250 ms)
══ CLIP ENCODE CLOSURE ══
parent: CLIP outer encode  4689.9 ms
  component CLIP load_models_gpu (exact)               2283.6 ms
  component CLIP inner forward                         2330.5 ms
  sum(components)                               4614.1 ms
  residual                                      75.8 ms (1.62% of parent)
  ✓ closes (residual <5% and <250 ms)
══ UNET NODE CLOSURE ══
parent: UNETLoader (t4b node)  819.5 ms
  component entry/prep join (derived)                  76.6 ms
  component gate wait (exact)                          1.089 ms
  component UNET H2D device transfer (exact window)    741.8 ms
  note: transfer decomposes into setup+copy+instantiate+adoption = 740.8 ms (nested in transfer; excluded from sum)
  note: dropped nested component(s) header detect (in adoption), skeleton (in adoption), bind (in adoption), identity validation (in adoption) (contained in another listed component)
  sum(components)                               819.5 ms
  residual                                      0 ms (0.00% of parent)
  ✓ closes (residual <5% and <250 ms)

LABEL CONFLICTS: none

══ TELEMETRY COMPLETENESS ══
CLIP descriptor                    PRESENT
CLIP exact copy                    PRESENT
CLIP construction                  PRESENT
CLIP storage identity              PRESENT
CLIP load_models_gpu               PRESENT
CLIP inner forward                 PRESENT
CLIP outer encode                  PRESENT
UNET source prep                   PRESENT
UNET exact copy                    PRESENT
UNET broad H2D                     PRESENT
UNET storage identity              PRESENT
sampler-start decomposition        MISSING (expected: fine-grained sampler-node→sampling sub-events; closest proxy: waterfall.sampler_node_to_sampling)
post-sampling decomposition        MISSING (expected: fine-grained post-sampling sub-events; closest proxy: waterfall.post_sampling_transition)
VAE decode                         PRESENT
output encode                      PRESENT
restore decomposition              PRESENT
request/setup decomposition        PRESENT

══ CRITICAL PATH SUMMARY ══
union-based critical path total: 18,514 ms (over 32 critical rows; overlapping rows NOT summed)
UNET source-prep overlap: 4689.870 ms (97.15% of prep) — background read hidden under CLIP encode
critical rows (time order):
  restore bootstrap                                      784.3 ms
  request/setup                                          373.6 ms
  remote method setup                                    110.0 ms
  prompt executor cache setup                            263.6 ms
  VAE loader (t4c)                                       324.4 ms
  descriptor/header (exact)                              27.5 ms
  CLIPLoader (t4 node)                                   4825.5 ms
  FastSafe setup (exact)                                 11.3 ms
  FastSafe copy (exact)                                  1934.7 ms
  tensor views (exact)                                   0.335 ms
  Comfy construction (exact)                             2670.5 ms
  CLIP outer encode                                      4689.9 ms
  CLIP load_models_gpu (exact)                           2283.6 ms
  CLIP inner forward                                     2330.5 ms
  entry/prep join (derived)                              76.0 ms
  UNETLoader (t4b node)                                  819.5 ms
  gate wait (exact)                                      1.089 ms
  UNET H2D (broad window)                                741.8 ms
  FastSafe setup (exact)                                 3.859 ms
  FastSafe copy (exact)                                  624.7 ms
  instantiate (exact)                                    0.354 ms
  adoption (exact)                                       111.9 ms
  header detect                                          5.526 ms
  skeleton                                               80.8 ms
  bind                                                   13.7 ms
  identity validation                                    11.8 ms
  sampler startup (node→sampling)                        1461.5 ms
  sampling                                               3727.4 ms
  post-sampling transition                               649.9 ms
  VAE decode                                             494.3 ms
  output encode                                          303.8 ms
  result persistence                                     363.5 ms
background:
  (unregistered) v2_startup_snap_true_enter_e…   activity_wall≈2642.6 ms · critical_path_contribution≈2642.6 ms
  (unregistered) v2_startup_custom_node_sourc…   activity_wall≈1534.9 ms · critical_path_contribution≈1534.9 ms
  (unregistered) v2_startup_comfyui_path_star…   activity_wall≈0.277 ms · critical_path_contribution≈0.277 ms
  (unregistered) v2_startup_backend_startup_e…   activity_wall≈46,598 ms · critical_path_contribution≈46,598 ms
  (unregistered) v2_startup_certificate_snaps…   activity_wall≈0.333 ms · critical_path_contribution≈0.333 ms
  (unregistered) v2_startup_dependency_valida…   activity_wall≈772.5 ms · critical_path_contribution≈772.5 ms
  (unregistered) v2_startup_cachedit_preparat…   activity_wall≈1995.4 ms · critical_path_contribution≈1995.4 ms
  (unregistered) restore method                  activity_wall≈906.0 ms · critical_path_contribution≈121.7 ms
  (unregistered) restore:early                   activity_wall≈62.5 ms · critical_path_contribution≈62.5 ms
  (unregistered) v2_startup_post_snapshot_res…   activity_wall≈846.0 ms · critical_path_contribution≈61.7 ms
  (unregistered) restore:eviction                activity_wall≈24.9 ms · critical_path_contribution≈24.9 ms
  (unregistered) restore:snapshot                activity_wall≈0.032 ms · critical_path_contribution≈0.032 ms
  (unregistered) clip_manifest_available         activity_wall≈0.004 ms · critical_path_contribution≈0.004 ms
  (unregistered) restore:preamble                activity_wall≈26.9 ms · critical_path_contribution≈26.9 ms
  (unregistered) v2_startup_snapshot_executio…   activity_wall≈0.562 ms · critical_path_contribution≈0 ms
  (unregistered) restore:preload                 activity_wall≈0.21 ms · critical_path_contribution≈0.21 ms
  (unregistered) restore:finalize                activity_wall≈6.768 ms · critical_path_contribution≈6.768 ms
  (unregistered) request:identity-capture        activity_wall≈0.113 ms · critical_path_contribution≈0 ms
  (unregistered) request:plan-deserialize        activity_wall≈0.348 ms · critical_path_contribution≈0 ms
  (unregistered) request:setup-schedule          activity_wall≈74.3 ms · critical_path_contribution≈0 ms
  (unregistered) request:executor-run            activity_wall≈17,764 ms · critical_path_contribution≈134.7 ms
  (unregistered) pre_sampler_cache_key_build     activity_wall≈0.002 ms · critical_path_contribution≈0 ms
  (unregistered) executor:graph-execution        activity_wall≈17,713 ms · critical_path_contribution≈134.7 ms
  (unregistered) v2_startup_first_prompt_exec…   activity_wall≈17,691 ms · critical_path_contribution≈134.7 ms
  UNET source prep                               activity_wall≈4827.6 ms · critical_path_contribution≈62.4 ms
  (unregistered) clip_tokenize_end               activity_wall≈47.1 ms · critical_path_contribution≈0 ms
  (unregistered) clip_scheduled_conditioning_…   activity_wall≈4628.8 ms · critical_path_contribution≈0 ms
  (unregistered) clip_gpu_prepare_end            activity_wall≈2288.4 ms · critical_path_contribution≈0 ms
  (unregistered) CLIP forward                    activity_wall≈2329.3 ms · critical_path_contribution≈0 ms
  (unregistered) vae_decode_end                  activity_wall≈494.4 ms · critical_path_contribution≈0 ms
  (unregistered) output_encode_end               activity_wall≈303.8 ms · critical_path_contribution≈0.001 ms
  (unregistered) result:assembly                 activity_wall≈59.6 ms · critical_path_contribution≈0 ms
  (unregistered) output_persist_end              activity_wall≈9.343 ms · critical_path_contribution≈0 ms
legend: critical = on the measured critical path; background = wall time largely overlapping critical coverage; contribution = wall − overlap with the critical union
```

Ground-truth reconciliation on this artifact (all match within rounding): CLIP node 4825.536 · descriptor 27.547 · FastSafe copy 1934.712 · construction 2670.544 · load_models_gpu(CLIP) 2283.612 · inner forward 2330.498 · outer encode 4689.879 · UNET node 819.495 · broad H2D 741.786 · exact copy 624.677 · adoption 111.888 · prep overlap 4689.870 ms / 97.15% · sampling 3727.396 · VAE decode 494.346.

Known cosmetic limitations (disclosed, do not affect correctness): (1) restore-phase `v2_startup_*` phase durations lack mono timestamps, get sequential estimated anchors in the restore region, and therefore show contribution≈wall there — they are clearly tagged `[background]`/`(unregistered)` and excluded from the union-based critical total; (2) long container rows (e.g. `request:executor-run`) legitimately cross several window boundaries and appear clipped with negative @offsets — honest evidence of rows that started before the window; (3) the raw legacy event name `CLIP forward` survives only as an `(unregistered)` background evidence row (2329.3 ms ≈ inner) while the CANONICAL rows carry the mandated names — raw evidence preserved per Goal 10, ambiguity eliminated per Goal 8.

## 10. Exact local test counts

| Suite | Result |
|---|---|
| `tests/test_r44g1_dynamic_gantt.py` (NEW, 17 tests) | **17 passed, 0 failed** |
| `tests/test_v2_waterfall.py` + `tests/test_v2_waterfall_contract.py` (run-only, never edited) | **68 passed, 0 failed** |

New-suite coverage (one test each unless noted): sparse native trace · rich R44E-like trace w/ ground-truth durations · outer-vs-inner naming (no bare `CLIP forward`) · broad H2D + exact copy coexistence · closure residual math · completeness matrix PRESENT/MISSING-with-proxies · dynamic window derivation · absent-boundary graceful skip · deterministic rendering · ASCII bars never `=` (bar segments restricted to `{█,▏▎▍▌▋▊▉,space}`) · fallback-run header · UNET-prep/CLIP-compute overlap (display-rounded + exact-ns assertions; contribution 137.718 ms on synthetic timestamps) · CANNOT SUM branch (over-sum fixture) + nested-drop branch · truncate_label determinism · long-label layout width · no-data graceful render (all MISSING + proxies) · real-artifact integration (skipif-absent; ran against the real R44E dir).

## 11. Measured rendering overhead (existing R44E artifact)

`render_run_dir` full report, 2 warmups + 12 timed iterations: **min 13.62 / median 16.34 / max 22.10 ms** (first-call ≈66 ms includes module import). Determinism verified: two renders produce byte-identical SHA-256. Pure presentation over already-collected telemetry — no sampling, synchronization, filesystem scans beyond reading the two artifact JSONs, GPU sync, or model introspection.

## 12. Concurrent-file overlap assessment with R44F

- R44F-owned/concurrently-dirty set (30 tracked-modified files incl. `modal_app.py`, `model_preload.py`, `v2_waterfall.py`, `runtime_executor.py`, `tools/benchmark_v2_direct.py`, `tests/test_v2_waterfall*.py`, plus untracked `request_clip_fastsafe.py` etc.): **ZERO overlap** — byte-identical before/after both lanes (verified via `git status --short` at batch start, between lanes, and at close; the tracked-M set never changed).
- R44G1 wrote exactly three new files (`comfymodal_runtime/dynamic_gantt.py`, `tools/render_dynamic_gantt.py`, `tests/test_r44g1_dynamic_gantt.py`) plus this report — no shared path with R44F's CLIP zero-copy work (`tests/test_r44f_clip_zero_copy.py`) or the R44G2/R44G3 lanes' report files.
- `request_clip_fastsafe.py` and all CLIP-construction code: never opened for edit, only ever read as black-box telemetry producers via persisted event names.
- Follow-up for the reconciliation owner (not done here to avoid concurrent-edit conflicts): wire `render_full_report(payload)` printing beside the existing waterfall attach sites (`canonical_execution.py` attach_waterfall call sites / `modal_client.py`) or post-run in `tools/benchmark_v2_direct.py` — one import + one call, gated like `COMFYMODAL_V2_GANTT_TELEMETRY` if desired.

## 13. Verdict fields

```text
R44G1_DYNAMIC_GANTT_IMPLEMENTED = YES
R44G1_HIERARCHICAL_ROWS = YES
R44G1_OVERLAP_VISIBLE = YES
R44G1_CLIP_LABEL_AMBIGUITY_FIXED = YES
R44G1_BROAD_VS_EXACT_DISTINGUISHED = YES
R44G1_CLOSURE_REPORTS_IMPLEMENTED = YES
R44G1_COMPLETENESS_MATRIX_IMPLEMENTED = YES
R44G1_EXISTING_R44E_RENDERS_CORRECTLY = YES
R44G1_RUNTIME_BEHAVIOR_CHANGED = NO
R44G1_REMOTE_RUN_PERFORMED = NO
R44G1_READY_FOR_RECONCILIATION = YES
```

— R44G1 observability lane, stopped after local implementation/tests/report. No deploy, no Modal, no commits.
