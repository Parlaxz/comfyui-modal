# Phase F4 — Studio Settings Consumer & Legacy Read Audit (2026-08-22)

**Lane:** Phase F batch F4 — READ-ONLY exhaustive Settings-consumer audit.
**Baseline:** Phase E COMPLETE (`PHASE_E_FINAL_CLOSURE_2026-08-22.md`; deterministic gate green: Python 1609 / Node 16 / Fake Playwright 126, wrapper exit 0; E7 live green).
**Constraints honored:** no production/test edits, no deploy, no Modal/GPU/live generation, no commit/push/branch/worktree, no reset/revert/stash/clean. Worktree left dirty per spec. No subagents used.

---

## 1. Executive verdict

**F4 verdict: the Settings domain is fundamentally HEALTHY post-Phase-E — every Preview and Output setting now has one sane authority path — but the audit proves 2 stale reset-only keys, 1 inert legacy-only setting still presented as modern, 2 PARTIAL settings whose consumers do not cover the modern Studio surfaces (GPU worst), and one false-positive restart banner.**

The seven-section architecture (General, Generation, Outputs, History, Experiments, Interface, Advanced) is intact in `web/studio-settings.js`. The single biggest stale authority problem is **GPU**: three competing frontend authorities (server in-memory `_current_gpu`, localStorage `comfymodal_gpu`, dead `window._comfyModalGpu`) plus proof that modern Studio V2 runs consume **none** of them (they fall back to `COMFYMODAL_V2_GPU` env or hardcoded `rtx-pro-6000`). Preview settings have exactly one authority path and need no rework. Experiment concurrency is correctly backend-fixed at 6 with the UI control removed; only a stale reset key remains. Reset All is safe for user data but has two narrow defects (forces engine to v2; never resets server-side GPU).

Counts: **14 user-visible value settings audited** (+3 actions, +7 read-only/nav rows). **10 fully CONSUMED**, **2 PARTIAL** (Run mode, GPU), **1 LEGACY-ONLY/INERT** (Grid columns), **2 STALE keys** (`comfymodal_global_concurrency`, `comfymodal_preview_auto_save`), **3 duplicated-authority clusters** (legacy settings precedence, window globals, GPU triple authority).

---

## 2. Complete settings inventory (seven-section architecture confirmed)

Sections render General → Generation → Outputs → History → Experiments → Interface → Advanced plus footer Reset All (`web/studio-settings.js:655-679`). Every control row carries `data-search`; search filters units and hides empty sections (`applyFilter`, lines 203–228).

| # | Section | Control | testid | Kind |
|---|---------|---------|--------|------|
| S1 | General | Run mode Cloud/Local | `settings-run-mode-*` | value |
| S2 | Generation | Execution Engine (v2/v1) | `settings-execution-engine` | value |
| S3 | Generation | GPU | `settings-gpu` | value |
| S4 | Generation | Preview default | `settings-preview-default` | value |
| S5 | Outputs | Format | `settings-output-format` | value |
| S6 | Outputs | Quality (0–100) | `settings-quality` | value |
| S7 | Outputs | WebP lossless compression | `settings-webp-lossless-compression` | value |
| S8 | Outputs | Auto-save original outputs locally | `settings-auto-save-local` | value |
| S9 | Outputs | Save folder | `settings-save-folder` | value |
| S10 | Outputs | Save metadata JSON sidecar | `settings-save-metadata-sidecar` | value |
| S11 | Outputs | Preview codec (webp only) | `settings-preview-codec` | value |
| S12 | Outputs | Preview quality (1–100) | `settings-preview-quality` | value |
| S13 | Outputs | Open output folder | `settings-open-folder` | action |
| S14 | History | Grid columns (2–8) | `settings-history-columns` | value |
| S15 | Experiments | *(none — info row only)* | — | info |
| S16 | Interface | Reset panel layout | `settings-reset-panel-layout` | action |
| S17 | Advanced | Heavy tracing level | `settings-heavy-tracing` | value |
| S18 | Advanced | Deploy state / Snapshots / Presets / Backends counts | `settings-deploy-state`, `settings-runtime-*` | read-only |
| S19 | Advanced | Open Backend tab; Legacy tabs ×6 | `settings-open-backend`, `settings-legacy-*` | nav |

---

## 3. Authority map (per setting)

Legend: LS = localStorage key; SRV = server persistence (`.modal_settings.json` unless noted); SNAP = request-time snapshot; RT = runtime consumer.

### S1 Run mode — PARTIAL (legacy-consumer only)
- Default Cloud. LS `comfymodal_enabled`; window `_comfyModalEnabled`; no SRV.
- Write: `studio-settings.js:401-409`; legacy twin `modal-settings.js:1434-1450`.
- RT consumer: ONLY `web/modal-node.js:678,841` — gates whether canvas `/prompt` POSTs redirect to Modal. Modern Studio requests never consult it.
- Init gap: window var set from LS only when legacy panel builds (`modal-settings.js:3924`); otherwise canvas stays Cloud even when LS says Local.
- Changing it does NOT change modern Studio behavior.

### S2 Execution Engine — CONSUMED / WORKING
- SRV `execution_mode` via POST `/comfymodal/config` (`__init__.py:4680-4697`); GET returns resolved mode/source/locked/readiness (`__init__.py:4578-4611`).
- Authority chain `execution_runtime.resolve_execution_mode`: request-captured → `COMFYMODAL_RUNTIME` env lock → persisted → default v2 (`execution_runtime.py:94-146`). Captured immutable per submission (`studio_run_adapter.py:3889-3904`; canvas `__init__.py:2430-2434`).
- UI truthfully states "Applies to future runs only" / "Managed by COMFYMODAL_RUNTIME". Immediate (next request).

### S3 GPU — PARTIAL + DUPLICATED AUTHORITY + RESTART-REVERT (biggest stale problem)
- Three competing authorities:
  1. Server in-memory `modal_client._current_gpu` (POST `/config {gpu}` → `set_gpu`, `modal_client.py:348-357`); initializes to `DEFAULT_GPU` at import, NEVER persisted → silently reverts to `rtx-pro-6000` on ComfyUI restart.
  2. LS `comfymodal_gpu` — dropdown preselection only (`studio-settings.js:794-798`; `modal-settings.js:121-125`); can display a choice the server no longer holds after restart.
  3. `window._comfyModalGpu` — written by both surfaces (`studio-settings.js:808,815`; `modal-settings.js:126,1499`), read by NOTHING (dead write).
- Runtime consumers:
  - Canvas V1: `get_gpu()` fallback (`__init__.py:4004` region).
  - Canvas V2/shadow plan: `extra_data.get("gpu") or get_gpu()` (`__init__.py:2441,2528,2662`).
  - Modern Studio paths: NOT consumed. Routes extract only top-level `body.gpu` (`__init__.py:7446`) which the frontend never sends; `handle_studio_experiment` has NO gpu parameter (`studio_run_adapter.py:4021-4028`); `V2ExperimentInvoker` gets `gpu=None` → plan `selected_gpu=""` → transport falls back to `COMFYMODAL_V2_GPU` env or hardcoded `"rtx-pro-6000"` (`v2_experiment_invoker.py:124,145`; `canonical_execution.py:2497`; `modal_transport.py:561,575`). `modal_options.gpu` (present via `/config` merge) is read by nothing downstream.
- Deployment coupling: per-GPU Modal classes must already be deployed (`gpu_catalog.py:125-139`); availability-dependent, not redeploy-triggering.

### S4 Preview default — CONSUMED / WORKING (Phase-E proven)
- LS `comfymodal_preview_default` + SRV `preview_default` (validated `__init__.py:4658-4660`; normalized `:1063-1071`).
- SNAP: `loadModalOptions()` → `buildPreviewModalOptions()` emits `preview_enabled` (`studio-output-preferences.js:291-304`); attached to Single (`studio-playground.js:2842,2865`), Workflow run (`:2228` + `buildRunPayload:642-664`), Experiment definition (`studio-experiment-mode.js:1540,1789`).
- Freeze: `contracts.normalize_output_intent_options` / `ExecutionOptions.from_legacy` map `preview_enabled→output_mode=preview` (`contracts.py:541-569,667-675`); carried into plan, `request_metadata.output_mode/variant` (`playground_service.py:209-268`; `studio_workflow_run.py:586-597`) and Experiment cell plans.

### S5–S10 Ordinary output settings — CONSUMED / WORKING (two consumption timings)
- LS + SRV keys of the same names; defaults from `output_converter.DEFAULTS` / `output_saver.DEFAULTS` (`__init__.py:897-910`).
- (a) Generation-time snapshot via request `modal_options`: remote V1 conversion (`comfyapp.py:16528-16531`), V2 remote conversion via `from_legacy` (`contracts.py:654-666`), local materialization auto-save/folder/sidecar/format (`v2_experiment_invoker.py:181-190` → `result_delivery.materialize_modal_result:492-515`).
- (b) Save-time LIVE server read: run-detail Save action loads `_load_modal_settings()` (`__init__.py:7050` → `save_run_history_output`, `studio_run_adapter.py:2185-2230`) — intentional second timing.
- These belong to ordinary Original output; Preview overrides format/quality/effort only in preview mode (effort frozen `fast` regardless of S7 — correct per E2D).

### S11 Preview codec — CONSUMED (single-option webp end-to-end; `studio-output-preferences.js:61-63`; `__init__.py:4661-4663`).
### S12 Preview quality — CONSUMED. 1–100 validated both ends; frozen into preview conversion (`contracts.py:556`); default 70 = `DEFAULT_PREVIEW_QUALITY` (`contracts.py:407`). The E-closure "quality 70" is the DEFAULT, not a hardcode; user values flow through.

### S13 Open output folder — CONSUMED action. Reads current `save_folder` → POST `/open-folder` (output/input root allowlist, `studio-settings.js:1013-1029`; `__init__.py:4701-4741`).

### S14 Grid columns — LEGACY-ONLY / INERT for the modern surface
- LS `comfymodal-studio-history-columns` (Settings offers 2–8, default 6).
- Sole reader: `web/studio-history.js:517-519` (LEGACY History page). The shell mounts History V2 (`studio-shell.js:13,22` → `renderHistoryV2`), whose grid is fixed CSS `repeat(auto-fill, minmax(230px,1fr))` (`studio-styles.js:3786-3790`) and never reads the key. Setting has zero effect on the product's actual History surface.

### S17 Heavy tracing — CONSUMED, RESTART REQUIRED (communicated), banner bug
- LS `comfymodal_heavy_tracing` + POST `/profile/level` → `.profile_config.json` (`__init__.py:5082-5127`). Effective level captured at module import (`profiler_trace_v4.py:42-61`); POST does not call `set_profile_level` → restart genuinely required; badge/banner honest in principle.
- BUG: banner shows when `stored !== effective` (`studio-settings.js:1067-1070`). Current `.profile_config.json` has `level: "detailed"` while UI default stored is "off" → banner permanently displays "requires a restart" although the user changed nothing.
- Backend duplication: `wall_clock_trace_v3.py:59` keeps its own `_PROFILE_LEVEL` copy (same file, consistent only after restart).

### S18/S19 read-only rows & nav — informational consumers of `/deploy/status`, `/studio/snapshots|presets|backends`; no authority risk.

---

## 4. Preview settings

Phase E proved global default/codec/quality + request-time freeze; this audit confirms ONE sane authority path remains: Settings dual-write (server-authoritative on sync, revert-on-failure) → `loadModalOptions()` snapshot at submit → frozen `output_mode` + `output_conversion_options` in immutable plan. No duplicate legacy reads found that can override it. Remaining benign duplication: `studio-settings.getPreviewPrefs()` re-implements `_readPreviewPreferences()` identically (used only for post-reset window sync) — same logic, same defaults, no divergence possible today; collapse optional in Phase F.

## 5. Output / export settings

- Ordinary Original output: S5–S10 (see §3a/§3b timings). Remote conversion honors them; local materialization honors auto-save/folder/sidecar; explicit Save uses live server values.
- Preview: S4/S11/S12 override format/quality/effort ONLY under `output_mode=preview`; never conflated with Original.
- Export: there is NO separate export pipeline; "export" == explicit Save (§3b) + Open output folder (S13). Filename behavior is internal (`unique_path` + idempotent save state), not user-configurable — no setting implies otherwise.
- No auto-save-to-cloud or filename-template settings exist (nothing inert to audit there).

## 6. Experiment settings

Modern concurrency is backend-fixed: `EXPERIMENT_CONCURRENCY = 6` (`experiment_modern_scheduler.py:57`); doc header states payload overrides are ignored; frontend sends no concurrency field (`studio-experiment-mode.js:1495,2131`; `studio-backend-api.js:181`). The Experiments section renders an info row only (`studio-settings.js:490-496`).

CURRENT STATE of the formerly-inert global concurrency control: **REMOVED from the UI** (no visible control anywhere in `web/*.js`); **STALE KEY REMAINS**: `comfymodal_global_concurrency` survives only in `MODERN_SETTINGS_KEYS` + Experiments section reset (`studio-settings.js:54,290`) — no writer, no reader, frontend or backend. Classification: removed (control) + stale remnant (key).

## 7. Runtime / backend settings

| Setting | Owner | Status |
|---|---|---|
| Execution Engine (S2) | Modern Studio-owned (persisted, resolver-canonical) | transitional-safe; V1 retirement is Phase H |
| GPU (S3) | Legacy-canvas-owned de facto; modern Studio ignores it | dangerous to re-home without threading fix (Lane C) |
| Heavy tracing (S17) | Diagnostics-owned (`.profile_config.json`, env override) | restart-required; leave ownership as-is |
| Deploy state / Snapshots / Presets / Backends counts | Backend-page systems (read-only mirrors) | Phase H owns; do not touch |
| `.modal_settings.json` | Canonical server settings store; excluded from Modal image bake (`comfyapp.py:6869,6900`) | healthy |
| Separate V2 performance architecture (profiles, runtime flags, preload/warmup blocks in `.profile_config.json`) | V2-perf owned | explicitly out of scope |

## 8. Stale / hardcoded reads (each proven for override capability)

1. `comfymodal_global_concurrency` — reset-only key, zero readers/writers. Cannot override anything. Remove from key list.
2. `comfymodal_preview_auto_save` — reset-only key (`studio-settings.js:52`), zero readers/writers (E4 removed the control). Remove from key list.
3. `window._comfyModalGpu` — dead write (never read). Harmless but misleading; delete or wire.
4. `window._comfyModalOutputOptions` — third cache. Readers: `modal-node.js:87-104` (canvas request fallback when window unset → falls to LS constants `original/75/balanced`), `modal-comparison.js:1163` (legacy Comparison runner). Can diverge from server only when localStorage holds stale cross-session values AND no settings surface ever synced; low probability, real. Compatibility fallback — keep for canvas path in F, mark for H.
5. Legacy `modal-settings.js syncOutputOptions()` precedence is localStorage-FIRST (`modal-settings.js:173-184`) vs modern server-first (`studio-output-preferences.js:199-243`) — duplicated authority with different conflict resolution between two visible surfaces (Advanced → Legacy tabs). Also `_persistOutputSettings` writes LS BEFORE server confirmation (`:1646-1686`) unlike modern revert-on-failure.
6. `modal-settings.js syncGpuConfig()` POSTs `{gpu}` on legacy panel BUILD (`:114-137`) — merely opening the legacy panel mutates server GPU state (side-effect write).
7. Hardcoded defaults audit: `75` appears as fallback in `modal-node.js:98`, `modal-settings.js:175,1640`, `studio-output-preferences.js:101`, backend `DEFAULT_OUTPUT_QUALITY`/`_CONVERTER_DEFAULTS` — all agree and are fallback-only (never override a persisted/snapshotted value). `70` likewise (`PREVIEW_DEFAULTS` ×3, `DEFAULT_PREVIEW_QUALITY`, `parseInt(...) || 70` at `studio-settings.js:1005`). `rtx-pro-6000` hardcodes: UI fallbacks (benign) and `modal_transport.py:561,575` (the effective modern-Studio GPU default — see S3). None of these can bypass canonical settings EXCEPT the transport fallback, which IS the effective value when nothing threads a GPU.
8. Direct `.modal_settings.json` consumers: only `__init__._load/_save_modal_settings` (cached, atomic tmp+replace) + diagnostic tool `tools/inspect_modal_model_storage.py`. `execution_runtime` receives the dict, never reads the file. Healthy single-writer model.
9. Stale Backend-page state: none feeding Settings values (Settings Advanced rows are read-only fetches).

---

## 9. Reset semantics

Per-section resets (`studio-settings.js:251-305`):
- general: removes `comfymodal_enabled` only.
- generation: removes `comfymodal_gpu`, `comfymodal_preview_default`; server-resets preview_default; POSTs `{execution_mode:"v2"}` (forces engine back to V2 — overreach if the user deliberately chose V1; silently ignored on 409 lock).
- outputs: removes 6 output keys + preview codec/quality; `setOutputPreferences(OUTPUT_DEFAULTS)` re-persists the full merged set to LS+server; syncs window global. Coherent.
- history / experiments / interface / advanced: key removals (+ profile level → off for advanced). Matches each section's keys.

Reset All (`runResetAll`, `studio-settings.js:313-343`): confirm dialog explicitly promises Workflows / run History / snapshots / presets / drafts / assets are NOT affected — TRUE in code:
- Clears exactly `MODERN_SETTINGS_KEYS` (16 flat keys, lines 40-58). Verified none are user-data namespaces: playground selection/drafts/results live under `comfymodal.studio.playground.v1|drafts.v1|results.v1` (`studio-playground-state.js:9-11`) and History V2 view-state under its own key (`history-v2-view-state.js`) — all preserved.
- Server side: output prefs reset via `setOutputPreferences(OUTPUT_DEFAULTS)`; engine forced to v2; profile level → off.

Defects (narrow):
1. OVERREACH: forces `execution_mode=v2` (Generation-reset AND Reset All) — a deliberate V1 choice is silently discarded by a "settings reset".
2. REACH-UNDER: clears LS `comfymodal_gpu` but never resets server `_current_gpu` (no POST) — post-reset GPU unchanged until restart while the UI shows default.
3. Stale keys inside the reset set (§8 items 1–2) prove no test pins this list to real consumers.

## 10. Restart / redeploy semantics

| Setting | Effective | UI communicates |
|---|---|---|
| S2 Engine | next request (captured per submission) | YES ("Applies to future runs only") |
| S3 GPU | immediate for canvas paths; NEVER for modern Studio; silently reverts to default on ComfyUI restart (in-memory only) | NO restart-revert hint; display can diverge from effective |
| S4, S5–S12 Preview+Output | next submission (snapshot); Save action uses live values | adequate ("new submissions" wording on Preview default) |
| S14 Grid columns | immediate (LS) but inert on modern History | n/a |
| S17 Heavy tracing | ComfyUI RESTART required | YES badge + banner — but banner false-positives when `.profile_config.json` level ≠ UI stored value (currently detailed vs off → permanent banner with no user change) |
| Redeploy-required settings | NONE in Settings (GPU class availability is deployment-dependent, not redeploy-triggering) | n/a |

Settings that APPEAR immediate but are not: GPU (restart-revert + modern-surface blindness) is the only offender.

---

## 11. Product surface consumer map

| Surface | Consumes from Settings |
|---|---|
| Playground Single | modal_options snapshot: execution_mode, preview_* (plan freeze), output_format/quality/webp_lc (conversion), auto_save/folder/sidecar (materialization). NOT run mode, NOT GPU select, NOT grid columns |
| Playground Experiment | same snapshot via `definition.modal_options`; concurrency fixed 6; per-cell plans frozen |
| Workflow Run | same as Single (`buildRunPayload`) |
| History | Save action consumes LIVE server output settings; View Original explicit fetch; grid columns NOT consumed (V2) |
| Canvas (legacy ComfyUI graph) | run mode (redirect gate), GPU (`get_gpu`), output options via window-global/LS fallback |
| Model Library / Workflows pages | no Settings consumption (correct) |
| Deployment/backend | execution_mode persisted; readiness displayed; nothing in Settings triggers a deploy |
| Output/export | save-time live read (§3b) + open-folder action |

A setting with no consumer would be inert: exactly one found — Grid columns (legacy-only consumer).

## 12. Legacy consumers

| Consumer | Reads | Verdict |
|---|---|---|
| `modal-node.js _getOutputOptions` | window global → LS fallback | compatibility fallback; still AUTHORITATIVE for canvas runs when the global is unset; keep in F; Phase H owns canvas retirement |
| `modal-comparison.js:1163` | window global | legacy Comparison runner; works today; Phase H re-home |
| `studio-history.js` columns key | LS | legacy page not mounted by shell; dead for the product surface; retire or repoint in F |
| `modal-settings.js` output/GPU/run-mode twins | same LS keys + `/config` | DUPLICATED AUTHORITY surface (Settings → Advanced → Legacy embeds it); align precedence in F or accept as sanctioned legacy until H |
| `execution_runtime` persisted-mode fallback | `.modal_settings.json` | sanctioned compatibility; Phase H owns V1/shadow retirement |
| Backend-page systems (deploy/presets/snapshots/backends) | own stores | intentionally out of F scope |

No modern surface reads deprecated localStorage keys beyond the above; no old config-file keys outside `.modal_settings.json` / `.profile_config.json` feed behavior.

## 13. Test coverage map

Existing deterministic coverage:
- Persistence/server-sync/reset structure: `test_studio_backend.SettingsContentTests` (13 structural), fake spec `studio-fake-settings.spec.mjs` (deploy status; profile-level render + persistence + reload), `test_testing_settings_js.py` (legacy structural), `test_modal_settings_gpu_config.py`.
- Preview settings: `tests/studio_phase_e_preview_settings_unit.mjs` (normalize/build/loadModalOptions/experiment carries modal_options), `test_e2d_preview_method_contract` (9), `test_phase_e_contract` (global defaults), E7 reconciliation suites.
- Engine semantics: `test_phase8_execution_mode.py` (resolver precedence, capture, lock).
- Single snapshot / Experiment freeze: `studio_playground_run_unit.mjs`, `studio_experiment_v2_*`, `test_experiment_modern_plan`, wave-2 contracts.

Gaps (each maps to an F4 finding):
1. No test pins `MODERN_SETTINGS_KEYS` to actual consumers → stale keys drifted in (`global_concurrency`, `preview_auto_save`).
2. No test proves Grid columns affects ANY mounted surface (it cannot — History V2 ignores it).
3. No test pins GPU consumption per surface; the modern-Studio-ignores-GPU gap is unpinned either way.
4. No restart-banner truthfulness test against a non-default `.profile_config.json` (the false-positive is invisible to the fake backend, which reports "off").
5. No Reset All assertion that server GPU stays untouched / engine-forced-to-v2 is intended behavior.
6. No stale-key migration/cleanup contract test.

---

## 14. Exact Phase-F fixes (NOT implemented)

- **F1 — stale keys** (`web/studio-settings.js`): remove `"comfymodal_global_concurrency"` and `"comfymodal_preview_auto_save"` from `MODERN_SETTINGS_KEYS` and from the Experiments-section reset list (lines 54, 290). Add a guard test asserting every key in the list has ≥1 reader or writer.
- **F2 — restart banner truthfulness** (`web/studio-settings.js:1064-1101`): compare stored LS value against the server-reported PERSISTED level (`GET /profile/level` already returns both `level` and `effective`); show "requires restart" only when they differ.
- **F3 — Grid columns** (`web/studio-history-v2.js` + `web/studio-settings.js`): EITHER consume `comfymodal-studio-history-columns` in the V2 grid (inline `grid-template-columns: repeat(N, 1fr)`, clamp 2–8, re-render on change) OR relabel/hide as legacy-only. Recommended: consume (small, honest).
- **F4 — GPU authority consolidation** (largest; split):
  - F4a backend persistence: add `"gpu"` to `_default_modal_settings()`; on load, seed `modal_client._current_gpu`; POST `/config {gpu}` writes both (`__init__.py`, `modal_client.py`). Kills the silent restart-revert.
  - F4b modern-surface threading: extract GPU from `modal_options.gpu` (already present via `/config` merge) or top-level body in the studio run/experiment/workflow routes and thread through `handle_studio_run_async` / `handle_studio_experiment` → invokers → plan `selected_gpu` (`__init__.py:7446-7528`, `studio_run_adapter.py`, `v2_experiment_invoker.py`).
  - F4c frontend cleanup: delete dead `window._comfyModalGpu` writes or make a real reader; make the dropdown display the SERVER value (`cfg.gpu`) rather than LS when they conflict (`web/studio-settings.js`, `web/modal-settings.js`).
- **F5 — legacy precedence alignment** (`web/modal-settings.js`): route legacy output-options sync through `studio-output-preferences.js` (server-first, revert-on-failure); stop `syncGpuConfig()` from POSTing GPU on panel build. If too invasive pre-H, minimum: fix localStorage-first precedence for `auto_save_local`/`save_metadata_sidecar`.
- **F6 — Reset All semantics** (`web/studio-settings.js`): decide and document whether engine-forced-to-v2 belongs in a settings reset (recommend: keep, but surface it in the confirm copy); add server-GPU reset once F4a lands.

## 15. Items explicitly deferred to Phase H

1. V1 engine retirement and removal of the v1 option from S2 (incl. shadow remnants).
2. Run mode Cloud/Local semantics for modern Studio surfaces (S1 currently gates only the canvas path).
3. Legacy Settings panel (`modal-settings.js`) and the six legacy tabs — full retirement/re-home (F5 is only an alignment stopgap).
4. Legacy Comparison runner reading `window._comfyModalOutputOptions`.
5. Legacy History page (`studio-history.js`) including its columns consumer, if F3 chooses "relabel" instead of "consume".
6. Backend-page systems (deploy/presets/snapshots/backends management) staying outside Settings ownership.
7. Canvas `/prompt` interception path (`modal-node.js`) and its window-global fallbacks.

---

## Implementation plan — independent file-ownership lanes

| Lane | Files owned | Work | Depends on |
|---|---|---|---|
| L-A settings-page | `web/studio-settings.js` | F1, F2, F6 (+ dropdown server-value display part of F4c) | none |
| L-B history-v2 | `web/studio-history-v2.js` | F3 (consume columns) | none (coordinate label with L-A if relabel chosen) |
| L-C gpu-backend | `__init__.py`, `modal_client.py` | F4a | none |
| L-C2 gpu-threading | `__init__.py` (routes), `studio_run_adapter.py`, `comfymodal_runtime/v2_experiment_invoker.py` | F4b | F4a |
| L-D legacy-panel | `web/modal-settings.js` | F5 | none |
| L-E tests | new/updated deterministic tests per §13 gaps 1–6 | guard tests for each lane | lands with each lane |

L-A, L-B, L-C(+C2), L-D are file-disjoint and can run in parallel; L-E assertions attach per lane. No lane touches V2 performance architecture or Backend-page systems.

---

**Audit-only batch:** files modified = this report only. Deploy / live / GPU / commit: NONE.

## F4 Implementation Follow-Up B — Legacy Settings Authority Alignment

- **Old precedence:** `web/modal-settings.js` previously preferred localStorage over `/comfymodal/config` for output format, quality, WebP compression, auto-save, save folder, and metadata sidecar settings, then wrote local/browser state before server confirmation.
- **New precedence:** legacy output synchronization now routes through `web/studio-output-preferences.js`. A successful server read overwrites stale localStorage; server-unavailable reads preserve the current localStorage/default fallback. User edits POST first and publish localStorage, `window._comfyModalOutputOptions`, and the change event only after success; rejected edits restore the prior acknowledged widget state.
- **GPU panel behavior:** legacy initialization is read-only and uses the successful server GPU over stale localStorage. The former panel-open GPU POST was removed. An explicit dropdown change still performs one GPU POST; failure keeps the prior acknowledged cache/state and restores the displayed selection.
- **Sync lifecycle:** GPU and output initialization use once-per-page-load guards shared by `setup()` and `buildPanel()`, preventing duplicate synchronization caused by build/render lifecycle calls.
- **Globals:** dead legacy `window._comfyModalGpu` writes were removed after reconfirming there are no current readers. `window._comfyModalOutputOptions` remains available and is maintained by the shared helper after acknowledgment.
- **Compatibility:** canvas V1/V2 compatibility was preserved: `modal-node.js` still reads the output-options global with its localStorage/default fallback. Comparison compatibility was preserved: `modal-comparison.js` still reads the output-options global.
- **Focused tests:** `tests/test_modal_settings_gpu_config.py` passed 13/13; `tests/studio_legacy_settings_authority_unit.mjs` passed all 13 authority/compatibility checks; legacy Settings structural tests passed 12/12; shared output-preference tests passed; `node --check web/modal-settings.js` passed.
- **Full gate:** `python tests/run_studio_tests.py --fake` passed: Python 1609, Node unit 17, fake Playwright 1; all lanes reported zero failures/errors.
- **Remaining Phase-H work:** retire/re-home the legacy Settings panel and legacy tabs, re-home Comparison and canvas compatibility paths, and remove remaining legacy globals only after their consumers are retired. GPU backend persistence and modern Studio GPU threading remain outside this lane.

---

## F4 Implementation Follow-Up A — Modern Settings Cleanup

**Lane:** F4A — modern Settings page only (`web/studio-settings.js` + settings-specific tests). Legacy panel, History V2 frontend, and History/replay/scheduler Python untouched. No deploy / Modal / GPU / live generation / commit / push / branch / reset. Worktree left dirty per spec. No subagents used.

### Verdict

**F4A PASS.** Both stale keys are gone from modern Settings authority/reset bookkeeping; the Heavy-tracing restart banner now answers "does the persisted level differ from what the current process is executing?" using server truth only; the GPU dropdown prefers server-reported value over localStorage; the dead modern `window._comfyModalGpu` writes are removed (zero readers confirmed repo-wide before removal); Reset All truthfully discloses the execution-engine V2 reset. Preview/Output semantics unchanged and regression-tested.

### Changes

1. **Stale keys removed** — `comfymodal_global_concurrency` and `comfymodal_preview_auto_save` deleted from `MODERN_SETTINGS_KEYS`. The Experiments section reset (whose only content was the stale concurrency key) is removed entirely: the Experiments section is informational-only (backend-fixed width 6) and now renders no reset button instead of a misleading no-op one. `buildSectionHeader` accepts no-reset sections.
2. **Settings-key authority guard test** — `tests/studio_phase_f4_settings_authority_unit.mjs` pins `MODERN_SETTINGS_KEYS` to a deliberate contract map where every key carries a classification plus concrete reader/writer evidence substrings checked against real module sources (`studio-settings.js`, `studio-output-preferences.js`, `modal-node.js`, `studio-playground.js`, `studio-playground-state.js`, `studio-history.js`). Adding a reset-only key without classification, or deleting a consumer without updating evidence, fails the gate. Also asserts both stale keys appear nowhere in `studio-settings.js`, and that durable namespaces (`playground.v1/drafts.v1/results.v1`) stay outside the reset set.
3. **Tracing banner truth model** — `refreshProfileLevel` now stores `persistedTracingLevel`/`effectiveTracingLevel` from `GET /profile/level` (`{level, effective}`) and shows the banner iff both are known and differ. The browser-stored selection never participates, killing the permanent false positive when `.profile_config.json` holds `detailed` while an unsynced browser default says `off` (audit case D). After a user change the select POSTs then re-fetches server truth, so the banner reflects authoritative persisted-vs-effective (case B). The select displays server-persisted value unless the user is mid-edit; localStorage remains a pure user-selection cache and is not rewritten from GETs. Profiler runtime semantics unchanged — restart remains genuinely required.
4. **GPU display authority** — `refreshGpuConfig` selects `cfg.gpu` when present and valid against `available_gpus`; localStorage `comfymodal_gpu` is consulted only as a cache when the server reports no usable value; fallback chain unchanged otherwise. Server A + LS B → displays A. This is DISPLAY ONLY: modern Studio execution still does not consume the selection (backend persistence/threading remain pending in lanes L-C/L-C2).
5. **Dead modern GPU global removed** — both `window._comfyModalGpu` writes deleted from `studio-settings.js` after repo-wide inspection confirmed zero readers (legacy-panel copies in `modal-settings.js` belong to the concurrent legacy lane). Not replaced with any other global.
6. **Reset All copy** — confirmation dialog now states "The execution engine is reset to the default V2 mode."; footer note adds "The execution engine resets to V2." Engine-forced-to-v2 POST behavior preserved exactly; nothing in the copy claims server-side GPU reset (server `_current_gpu` remains in-memory/unpersisted — documented mismatch below).
7. **Test updates** — mocked-project spec `tests/browser/studio-settings.spec.mjs` Reset-All seed list drops the two stale keys (they are no longer cleared by design); new unit module registered in `run_studio_tests.py` NODE_UNIT_FILES.

### Unresolved (explicitly out of this lane)

- Backend GPU persistence + restart-revert (L-C) and modern-surface GPU threading (L-C2): Reset All still clears only the LS GPU cache; server `_current_gpu` is untouched until that lane lands. No new copy claims otherwise.
- Grid Columns consumption on mounted History V2 (L-B) — setting remains legacy-consumer-only, deliberately classified in the contract map.
- Legacy `modal-settings.js` precedence/GPU-build POST (L-D) and its own `window._comfyModalGpu` writes.

### Tests (all deterministic, no paid/live)

- New `tests/studio_phase_f4_settings_authority_unit.mjs`: 12 sections PASS — registry/contract equality, stale-key absence, durable-namespace exclusion, banner cases A/B/D + change→refetch case B', GPU server-wins + LS-fallback + dead-global absence, Reset All disclosure/POSTs/preservation, Preview+Output load/save regression, Experiments informational integrity, search functionality.
- Existing focused: `studio_phase_e_preview_settings_unit.mjs` 6/6 PASS; `tests.test_studio_backend` + `tests.test_testing_settings_js` 310/310 OK.
- Full wrapper `python tests/run_studio_tests.py --fake`: python 1609/1609 OK, node-unit 17/17 PASS (incl. new F4A module), fake Playwright 132 passed (incl. fake-settings 16–18 under the new banner model). One transient python failure and one transient fake-lane failure observed during the first combined run while concurrent F1/F2 lanes were mid-edit; clean re-runs of each lane were fully green and no other lane's file was touched to achieve it.

### Remaining F4 work

L-B Grid Columns consumption; L-C GPU backend persistence; L-C2 GPU threading into studio run/experiment routes; L-D legacy panel alignment; Phase-H items per §15.

Deploy / live / GPU / commit / push: NONE.

---

## F4 Implementation Follow-Up C — Modern History Grid Columns Consumer

**Lane:** F4C — mounted History V2 Grid Columns consumer (`web/studio-history-v2.js` + `web/studio-styles.js` + focused History/Settings tests). History/replay/scheduler Python, notes/favorites semantics, Experiment-detail frontend, and Settings authority logic untouched. No deploy / Modal / GPU / live generation / commit / push / branch / reset. Worktree left dirty per spec. No subagents used.

### Verdict

**F4C PASS.** S14 Grid Columns moves from `LEGACY-ONLY / INERT` to **CONSUMED / WORKING**: the modern Settings control now visibly drives the product's actual History surface (mounted `renderHistoryV2` feed grid), with truthful normalization, usable responsive reflow, same-tab application without reload, and zero regression to search/filter/sort/pagination/favorite/detail state.

### Previous inert state

Settings wrote `comfymodal-studio-history-columns` (2–8, default 6); the sole reader was the orphaned legacy `studio-history.js:517-519`, while the shell-mounted History V2 used a fixed `repeat(auto-fill, minmax(230px, 1fr))` (`studio-styles.js`) and never read the key (§3 S14).

### Final consumer

- `renderHistoryV2` reads the key once per mount via a try/catch-guarded localStorage reader (corrupt/unavailable storage → `null`), normalizes it, and applies the result as an inline CSS custom property `--comfymodal-studio-history-columns` plus a `data-grid-columns` attribute on the history page root.
- The feed grid rule resolves its track count from that variable: `repeat(auto-fill, minmax(max(132px, calc((100% - (N-1)*12px)/N - 0.5px)), 1fr))`. The calc term is one track's exact gap-compensated share (gap pinned at 12px; 0.5px rounding guard), so auto-fill produces EXACTLY N tracks on ordinary desktop widths while the 132px floor reflows to fewer equal columns on narrow containers instead of crushing cards. A `@media (max-width: 720px)` override restores the pre-setting legacy density (`minmax(230px, 1fr)`) outright on narrow viewports.
- No second setting, no Settings change, no legacy-page modification, no polling loop, no global state framework, no BroadcastChannel.

### Normalization

Exported `normalizeHistoryColumns(raw)` shares the Settings control semantics: `parseInt` truncation (floats truncate exactly as Settings reads them), NaN/empty/malformed → default 6, clamp below-range → 2, above-range → 8. Malformed persisted state can never break rendering.

### Same-tab behavior

The shell re-renders the active page on every tab activation (`studio-shell.js setPage → renderActivePage` fully remounts History V2), so reading at mount is sufficient: changing Grid columns in Settings and returning to History applies the new value with no browser reload (proven by an in-page no-reload marker in the browser test). Cross-tab live sync remains optional and is not implemented (no storage-event listener existed before; reload/remount always reflects persisted value).

### State preservation

Presentation-only: no view-state, filter, sort, pagination/cursor, favorite/note, detail-overlay, or Experiment code path consults or mutates the column value. F2A favorite-star failure-recovery code preserved verbatim. Card DOM structure, roles, tabindex, star semantics, focus order, and document order are unchanged.

### Tests

- New `tests/studio_history_v2_grid_columns_unit.mjs` (registered in NODE_UNIT_FILES): 11 sections PASS — missing→6, valid 2/4/6/8, below→2, above→8, malformed/float/corrupt-safe, mounted-consumption source guards (key literal, inline CSS var, data attribute, styles rule consumption, legacy reader untouched), a faithful simulation of the shipped CSS formula proving every N yields integer 1..N tracks everywhere and EXACTLY N on desktop widths ≥1164px container, and the key/range/default constants contract.
- Fake Playwright `studio-fake-history-v2.spec.mjs` tests 18–21: rendered computed-style proof that seeded "4" yields 4 real grid tracks and Settings changes 6→4→8 apply on tab return without reload (plus reload persistence); persisted-value remount seeding; search/filter/favorite/document-order/card role+tabindex+keyboard-activation survival across layout updates; narrow-viewport (480px) reflow to fewer usable tracks (≥200px each, never zero/invalid).
- `tests/studio_phase_f4_settings_authority_unit.mjs` S14 contract entry updated to classification `value-setting` with History V2 consumer evidence (guard not loosened; key unchanged). 12/12 PASS.
- Visual baseline `history-grid-fake-chromium-win32.png` regenerated for the intentional default-6 desktop layout change (documented regeneration workflow).

### Full gate

Final clean run `python tests/run_studio_tests.py --fake`: **python 1642/1642 OK (0 fail/error/skip), node-unit 18/18 PASS, fake Playwright PASS (141 tests, 17 files) — ALL STUDIO LANES GREEN.** Two transient fake-lane failures observed in an intermediate run while the concurrent F1 lane was mid-edit (`studio-fake-history-cancel-menu.spec.mjs` C4 — F1B-owned untracked spec whose seeded record was absent from the feed; `studio-fake-workflow-run.spec.mjs` test 2) plus one fake-server-unavailable direct npm run (`createSession failed: HTTP ...` mass failure); all passed cleanly on rerun with zero changes to any F1-owned file.

### Classification

Grid Columns (S14): **CONSUMED / WORKING** on the modern surface. Remaining F4 GPU work: L-C backend persistence (restart-revert) and L-C2 modern-surface GPU threading remain open.

Deploy / live / GPU / commit / push: NONE.

---

## F8 GPU Authority Consolidation

**Lane:** Phase F batch F8 — GPU Settings/Backend/Runtime-threading ownership (`__init__.py`, `modal_client.py` surface, `studio_run_adapter.py`, `studio_workflow_run.py`, `comfymodal_runtime/playground_service.py`, `web/studio-settings.js`, new deterministic tests). History V2 files, Export files, and all V2 performance architecture untouched. No deploy / Modal / GPU / live generation / commit / push. No subagents used.

### Verdict

**F8 PASS on its own lane.** The four remaining GPU defects from §3-S3 are closed: server GPU persists across ComfyUI restart, modern Studio Single/Workflow/Experiment submissions freeze the selected GPU into their immutable ExecutionPlans, transport receives the frozen selection instead of silently substituting the hardcoded default, and Reset All resets the persisted/server GPU. Legacy canvas behavior is preserved and strengthened (restart-stable).

### Final authority chain

```
Settings UI (POST /config {gpu})
  → validated (catalog membership) → modal_client.set_gpu (server effective)
  → _save_modal_settings → .modal_settings.json["gpu"]   (atomic tmp+replace)
GET /config returns { gpu (effective), persisted_gpu, default_gpu, available_gpus }
New Studio submission:
  resolve_request_gpu() ONCE at acceptance
  → ExecutionPlan.request_metadata["selected_gpu"] (frozen)
  → execute_plan(gpu=None) falls back to plan metadata
  → ModalTransport receives selected_gpu (cache identity + handle_lookup_gpu diagnostics)
Replay/resume/retry: saved plan metadata reused verbatim; current Settings never consulted.
```

### Precedence (documented contract)

1. **Explicit per-request override** — top-level `gpu` when supplied and valid (normalized via `normalize_gpu_value`; must exist in `GPU_BY_VALUE`, else acceptance fails truthfully with `ValueError`/400).
2. **`modal_options.gpu`** captured from canonical server Settings when supplied and valid.
3. **Canonical persisted/default server GPU** — `modal_client.get_gpu()`, seeded from `.modal_settings.json` at startup.
4. **Transport env/hardcoded fallback** — ONLY when nothing was captured (`selected_gpu == ""`): `COMFYMODAL_V2_GPU` env, else `rtx-pro-6000`. `COMFYMODAL_V2_GPU` remains deploy-time primary AND transport fallback; it is NOT a runtime lock overriding an explicit selection (inspected, preserved).

A later Settings change never mutates an accepted plan: the value is frozen into `request_metadata` at build time; only future submissions capture the new value.

### Restart behavior

`_seed_server_gpu_from_settings()` runs once at startup (after workspace resolver install): persisted valid GPU → initializes `_current_gpu`; missing/non-string/invalid-retired values normalize truthfully to the catalog default (`get_default_gpu()`); nonsense is never persisted or served. GET /config reports both `gpu` (effective) and `persisted_gpu` so display can never diverge silently.

### POST /config semantics

validate → update server effective selection → persist canonical settings → return acknowledged GPU. Persistence failure rolls the in-memory value back (no split-brain) and returns 500 with a truthful message; GET stays aligned with actual authority. Additionally, `_save_modal_settings` is now read-modify-write against current state: partial POSTs (output-only or engine-only) can no longer silently reset unrelated persisted keys (pre-existing latent clobber hazard that would have reverted GPU on every output-settings save).

### Capture threading per surface

- **Single**: route → `handle_studio_run_async` resolves once → `playground_adapter_direct_run(gpu=...)` → `PlaygroundService.execute` forwards to builders accepting `gpu` (signature-inspected; pre-F8 injected fakes unaffected) → `_default_build_execution_plan` freezes `request_metadata.selected_gpu` (both production and non-production branches). The browser sends NO top-level GPU; one captured source (server Settings) suffices.
- **Workflow Run**: `handle_workflow_run_async` resolves once → V2 path freezes via `build_workflow_execution_plan(..., gpu=...)`; v1/shadow path threads to `direct_studio_run_completion` → `execute_modal_prompt` → V1 class lookup.
- **Experiment**: `/studio/experiment` extracts `body.gpu` → `handle_studio_experiment(gpu=...)` resolves once → `_schedule_and_start(gpu=...)` → `V2ExperimentInvoker(gpu=...)` builds EVERY cell plan with the same frozen GPU. No per-cell/per-axis GPU introduced; no concurrency/settings UI added.
- **Diagnostics**: `trace_ctx.selected_gpu` + `selected_gpu_source` (`request` | `modal_options` | `server_settings`) recorded at acceptance; plan metadata carries `selected_gpu`; transport logs `handle_lookup_gpu`. No secrets, no new telemetry system.

### Replay / resume / retry

Generate Original, Retry Original, Generate Again, Single Resume, Experiment Retry/Resume dispatch saved plans through `execute_plan(plan)` WITHOUT a gpu kwarg; the executor's existing fallback reads the plan's frozen `request_metadata.selected_gpu`. Replay correlation builders copy request metadata verbatim (only approved correlation keys change), so the saved GPU survives round-trips and `validate_replay_delta` stays green. Changing GPU today affects FUTURE new submissions only.

### Availability (fail-closed)

Unsupported/retired selections fail truthfully at acceptance (catalog-membership validation; 400/error dict) and are never silently substituted. Per-GPU deployed-class availability remains call-time (Modal lookup) for V1 and deploy-time env for V2 — existing product contract unchanged; no silent hardware substitution added.

### Reset semantics

Reset All AND Generation-section reset now POST `{execution_mode:"v2", gpu:<default_gpu>}` where `<default_gpu>` is fetched from GET /config (`default_gpu`, hidden-GPU aware) with an `rtx-pro-6000` fallback: browser cache cleared + server effective reset + persisted reset + UI refresh shows the acknowledged default. Confirmation copy and footer note truthfully disclose the GPU reset. Durable namespaces (playground/drafts/results/history view-state) remain untouched; Preview/output reset behavior unchanged. Legacy panel keeps read-only server-first init (zero POST on open; exactly one explicit-change POST site).

### Legacy compatibility

Canvas V1/V2 keep `get_gpu()` / `extra_data.get("gpu")` paths — now restart-stable because the server selection persists. No window globals reintroduced; `window._comfyModalGpu` stays removed.

### Tests (all deterministic, no paid/live)

- New `tests/test_f8_gpu_authority.py` (40 tests, registered in STUDIO_PY_MODULES after the Workflows block): persistence (default config, POST persists, restart simulation via cache-drop + re-seed, invalid rejected 400, persistence-failure rollback 500, partial-save preservation, retired/non-string normalization), precedence resolution, Single capture/immutability/future-submission, Workflow capture + plan freeze (both branches), Experiment scheduler threading + invoker cell consistency, Generate Original/Retry/Resume preservation + replay-dispatch never reads current Settings, transport boundary (plan→transport A, non-empty not substituted, explicit override wins, empty→env/hardcoded fallback only, unsupported fails closed).
- New `tests/studio_phase_f8_gpu_reset_unit.mjs` (6 sections, registered in NODE_UNIT_FILES): Reset All + Generation reset POST default GPU, disclosure copy, durable-namespace survival, legacy panel zero-POST-open pin, dropdown display authority.
- Runner robustness fix (`tests/run_studio_tests.py`): subprocess decoding switched to UTF-8/replace and stdout reconfigured — Playwright/spec output containing non-cp1252 bytes previously crashed the fake lane with `stdout=None` before any test ran.

### Gate results (this lane's final run)

- Focused: `tests.test_f8_gpu_authority` 40/40 PASS; combined focused set (F8 + studio backend + routes + workflow integration + replay core + generate-original + F1A resume + canonical execution + phase8 engine) 577/577 PASS in gate order.
- Full wrapper `python tests/run_studio_tests.py --fake`: **python 1682/1682 OK (0 fail/error/skip); node-unit 21/21 PASS; fake Playwright 147 passed / 8 failed** — all 8 failures are asset-GET-count assertions inside `studio-fake-history-v2-download.spec.mjs` (History V2/Export lanes, actively mid-edit by concurrent Phase-F agents in this shared tree; zero GPU/Settings/reset surface involved; an earlier same-day run before those lanes' latest edits passed 140/140).

### Files modified by THIS lane

`__init__.py`, `studio_run_adapter.py`, `studio_workflow_run.py`, `comfymodal_runtime/playground_service.py`, `web/studio-settings.js`, `tests/test_f8_gpu_authority.py` (new), `tests/studio_phase_f8_gpu_reset_unit.mjs` (new), `tests/run_studio_tests.py` (registrations + UTF-8 runner robustness), this report. `modal_client.py` required no changes (existing `set_gpu`/`get_gpu` retained).

Deploy / live / GPU / commit / push: NONE.
