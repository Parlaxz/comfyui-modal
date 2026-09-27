# PHASE H2 — RUN MODE, BACKEND SELECTION & SETTINGS AUTHORITY CONSOLIDATION AUDIT (2026-08-23)

**Lane:** Phase H batch H2 — READ-ONLY audit. No production/test edits, no deploy/live/Modal/GPU, no commit/push/branch/worktree/reset. No subagents. H1/H3/H4 run concurrently in the shared tree.
**Question:** What should the FINAL modern execution/settings control model be after legacy/V1 consolidation?
**Authoritative inputs:** `PHASE_F_FINAL_CLOSURE_ZERO_CONTEXT_HANDOFF_2026-08-23.md` (§6 F4/F8), `PHASE_F4_SETTINGS_CONSUMER_AUTHORITY_AUDIT_2026-08-22.md` (incl. F4A/B/C + F8 appends), `PHASE_G_FINAL_CLOSURE_ZERO_CONTEXT_HANDOFF_2026-08-23.md` (§15/§16/§37/§38), plus direct source verification in the current tree (all line refs below re-read today).

---

## 1. CURRENT RUN-MODE VOCABULARY — FULL MAP

| Concept | UI label(s) | State key | API field | Persistence | Dispatch consequence |
|---|---|---|---|---|---|
| **Run mode** | Settings → General "Run mode: Cloud / Local" (`settings-run-mode-cloud/local`, `studio-settings.js:409-438`); legacy twin "Run on: Cloud (Modal GPU) / Local (this PC)" (`modal-settings.js:1421-1460`) | LS `comfymodal_enabled` ("true"=Cloud, default) + `window._comfyModalEnabled` | NONE (never sent to server) | Browser only | ONLY consumer: canvas `/prompt` interception gate (`modal-node.js:678,841`). Local → POST passes through to local ComfyUI queue; Cloud → redirected to `/comfymodal/prompt` (Modal). Modern Studio surfaces never consult it (F4 S1, reconfirmed). |
| **Execution Engine** | Settings → Generation select V2—Recommended / V1—Legacy (`settings-execution-engine`, `studio-settings.js:448-466`); duplicate select in legacy panel (`modal-settings.js:1550-1623`) | `window._comfyModalExecutionMode` (display cache) | `execution_mode` in GET/POST `/comfymodal/config`; captured into request `modal_options.execution_mode` by `loadModalOptions()` (`studio-output-preferences.js:311-332`) | Server `.modal_settings.json["execution_mode"]` (default v2, `__init__.py:897-913`) | `execution_runtime.resolve_execution_mode()` precedence: request-captured → `COMFYMODAL_RUNTIME` env lock → persisted → default v2 (`execution_runtime.py:94-146`). Captured immutable per submission on Single (`studio_run_adapter.py:3934-3966`), Workflow (`studio_workflow_run.py:1676-1720`), Experiment (`studio_run_adapter.py:2586-2596`), canvas (`__init__.py:2488-2496`). Selects V2 plan executor vs V1 legacy executor. |
| **Shadow** | none (not user-selectable; POST /config rejects it, `execution_runtime.py:161-177`) | none | reachable only via env `COMFYMODAL_RUNTIME=shadow` or handcrafted request | none | Builds the V2 ExecutionPlan for comparison, executes exactly one V1 generation (`studio_run_adapter.py:3983-3993`; `__init__.py:2547-2548`). Diagnostic-only. |
| **GPU** | Settings → Generation GPU select (`settings-gpu`); legacy panel dropdown (server-first post-F4B) | LS `comfymodal_gpu` (display cache only) | GET `/config` → `{gpu, persisted_gpu, default_gpu, available_gpus}`; POST `/config {gpu}` | Server `.modal_settings.json["gpu"]` (F8) | Frozen per-plan at acceptance via `resolve_request_gpu()`; replay/resume/retry reuse frozen metadata; transport fallback env/hardcoded only when nothing captured. |
| **Workspace** | Legacy panel → Workspace section only (`modal-settings.js:2050-2137`: select/add/edit/swap/repair/export/import/install). NO modern-surface control. | server registry `_WORKSPACES_FILE` `active_workspace_id` (`modal_workspaces.py:11,116-135`) | GET/POST `/comfymodal/workspaces`, POST `/workspaces/active`, POST `/workspaces/swap` | `.modal_workspaces.json` registry | Resolved SERVER-side once at dispatch (`_active_workspace()`, `__init__.py:7528-7530`); browser never sends a workspace; threads through plans as `workspace_id`. |
| **"Backend" (page)** | Shell nav "Backend" (`studio-shell.js:24`) = Backend Presets + Snapshots tabs (`studio-backend.js:170-210`) | `.studio_presets.json` / snapshots stores | `/studio/presets/*`, snapshots routes | own stores | Execution-preset/graph-capture management. NOT an execution backend selector. |
| **"Backends" (legacy store)** | none visible (Settings Advanced read-only counts) | `.studio_backends.json` | `/comfymodal/studio/backends*` (`__init__.py:7330-7477`, header comment: "legacy compatibility / import-only") | compatibility bridge | Discovers comparison profiles as "backends". A misnomer: these are comparison profiles, not execution engines. |
| **Portability targets** | Workflows → Portability panel "Target readiness" matrix: Local / Modal / RunPod / RunComfy / Comfy Cloud / Baseten (`studio-portability.js:18-32,214+`) | derived cache `.studio_portability_reports.json` | version-scoped portability GET | derived-only sidecar | ADVISORY ANALYSIS ONLY — zero execution capability behind any row (G closure §15: "No six execution engines were added"). |

---

## 2. FINAL EXECUTION ENGINES — WHAT ACTUALLY EXISTS (traced to executors)

| Route/mode state | Final executor | Classification |
|---|---|---|
| Modern Studio Single/Workflow/Experiment with resolved mode = **v2** | `PlaygroundService.execute` / `build_workflow_execution_plan` / `V2ExperimentInvoker` → immutable `ExecutionPlan` → `execute_plan` → `ModalTransport` → `Cls.from_name(...)` `ModalRuntimeEntrypointV2.run_plan_stream` (`modal_transport.py:387,664,884,1111-1312`) | **CANONICAL Modal V2** — the only engine with modern semantics |
| Canvas `/comfymodal/prompt` with mode = **v2/shadow** | same V2 executor (`__init__.py:2550-2560`) | canonical V2 (canvas entry) |
| Any surface with resolved mode = **v1** | `direct_studio_run_completion` → `execute_modal_prompt` (`studio_run_adapter.py:3347,3434`) / `LocalRemoteInvoker` → `modal_client.run_prompt_stream` → per-GPU deployed classes `ComfyAPI_<GPU>` (`gpu_catalog.py:125-139`, `modal_client.py:241-341`) | **LEGACY V1** — remote Modal, no immutable plan |
| Canvas `/prompt` with Run mode = **Local** | local ComfyUI's own queue (interception bypassed, `modal-node.js:678-681,796`) | **LOCAL COMFYUI** — legacy-canvas-only notion |
| mode = **shadow** | V1 executor + V2 plan comparison | diagnostic adapter, not a product engine |
| RunPod / RunComfy / Comfy Cloud / Baseten | **no executor exists** | historical/analysis-only (portability targets) |

**Does V1 provide anything modern V2 cannot?** No product capability was found that V2 lacks. V1-only dependencies are: (a) the legacy Comparison runner (`/comfymodal/comparison/run` executes via `run_prompt_stream`, `__init__.py:5530`; confirmed by `tests/test_audit_round7.py::test_comparison_profile_passes_workspace_to_run_prompt_stream`); (b) the per-GPU deployed-class deployment topology (a deployment model, not a capability); (c) shadow diagnostics. V1 runs produce submission-time history records that enter History V2 as irreproducible rows (no `execution_plan_json` → `replay_capable=false`, no Resume/Retry).

## 3. LOCAL SEMANTICS (proven, not inferred)

- Modern Studio NEVER runs against local ComfyUI. Every Playground/Workflow/Experiment dispatch goes to Modal (V1 or V2) via the server; there is no local-execution branch in `handle_studio_run_async` / `handle_workflow_run_async` / `handle_studio_experiment`.
- "Local" exists ONLY as the canvas pass-through when `window._comfyModalEnabled === false`.
- Local runs use NO canonical ExecutionPlan, produce NO modern History (no RequestSnapshot, no Preview/Original, no assets pipeline), support NO WorkflowVersion/Preset semantics, NO Experiments, NO GPU freeze (local hardware is whatever the machine has).
- Verdict: Local is a **compatibility surface of the legacy canvas**, not a first-class product. The Settings hint "Cloud mode sends generations to Modal. Local mode runs on your machine." is literally true only for the canvas and misleadingly implies a Studio-wide switch.

## 4. CLOUD SEMANTICS

- "Cloud" today means exactly one thing: **Modal**, scoped to the selected workspace. There is no generic remote-execution abstraction: both engines hardcode Modal lookups (`APP_NAME` classes for V1; `ModalRuntimeEntrypointV2` for V2).
- It is not provider selection, not per-run backend choice, and not workspace selection (workspace is resolved server-side independently).
- The label's meaning has drifted: it was introduced as the inverse of "Local" for the canvas redirect, but reads today as if a Cloud/Local *provider* choice existed.
- **Phase G boundary (hard requirement):** the six portability targets are advisory readiness rows inside the Workflows Portability panel. They must NOT become a provider selector, and no UI naming may imply RunPod/RunComfy/Comfy Cloud/Baseten can execute anything. Current naming risk: the matrix rows "Local" and "Modal" reuse the same words as the Settings Run mode; the panel is correctly titled "Target readiness", which is the only thing keeping the two vocabularies apart. Any future Run-mode UI must not render these six names as selectable engines.

## 5. V1 STATUS

- **Normal UI entry point:** Settings → Generation → Execution Engine = "V1 — Legacy" (two writer surfaces: modern Settings + legacy panel). With engine=v1, ALL modern surfaces silently downgrade: Single → `direct_studio_run_completion`; Workflow → `_workflow_legacy_run` (submission-time history, `studio_workflow_run.py:1412-1614`); Experiment → legacy scheduler `LocalRemoteInvoker` (`experiment_runner.py`); canvas → `execute_modal_prompt`.
- **API routes:** same routes (`/studio/run`, `/studio/experiment`, `/comfymodal/prompt`); mode is resolved server-side, so V1 is reachable without any dedicated route.
- **Executor:** `execute_modal_prompt` / `run_prompt_stream` → per-GPU Modal classes.
- **History behavior:** submission-time record bridged one-way into History V2 at creation; irreproducible (`replay_capable=false`); no Resume/Retry/Generate Original; no Preview/Original variants; export/download still work on whatever assets materialize.
- **Features unavailable in V2:** none found (§2). Features unavailable in V1 that V2 has: everything modern (immutable replay, resume, preview/original, durable experiments, GPU freeze, workflow identity).
- **Tests:** `test_phase8_execution_mode.py` pins resolver/capture/lock semantics (mode vocabulary itself, not V1's value); no test asserts V1-specific product value.
- **Actual product dependency:** Comparison runner (legacy canvas A/B) and shadow diagnostics are the only V1-dependent behaviors found.
- **Classification: COMPATIBILITY_ONLY** — removable after (a) Comparison runner decision (retire or re-home), (b) shadow retirement, (c) persisted `execution_mode:"v1"` migration, (d) removal of the v1 option from both engine selects and `AVAILABLE_EXECUTION_MODES`. Blockers are enumerated here; removal itself belongs to H1/lane-owned implementation, NOT H2.

## 6. V2 STATUS (the future Cloud authority — proven)

- Accepted ExecutionPlan: runtime-derived at dispatch, immutable per run; exact round-trip validation on every replay (`PHASE_F` §7 invariant 1).
- WorkflowVersion/Preset: full support — workflow runs resolve bundle → merge preset controls STRICT → `build_workflow_execution_plan` freezes identity + GPU + output intent (`studio_workflow_run.py:524-680`).
- History V2: first-class — running→terminal writes, RequestSnapshot with `execution_plan_json`, per-variant asset projection, replay/resume/retry actions.
- Preview/Original: supported end-to-end (mode conversion rules frozen; Resume preserves frozen mode).
- Experiments: `V2ExperimentInvoker` builds every cell plan with the same frozen GPU; durable cells; resume/cancel/retry parity (F1A/F1B).
- GPU selection: frozen at acceptance; transport receives it (F8).
- Workspace/deploy identity: `request_metadata.workspace_id` from the server-resolved active workspace; `modal://` asset references carry workspace id.
- Failure behavior: fail-closed acceptance (invalid GPU/controls rejected truthfully); replay fails closed for missing/mismatched plans.

## 7. SETTINGS AUTHORITY TABLE (exhaustive; F4/F8 authority where closed)

| Setting | UI control | Persisted where | Server authority | Request freeze point | Consumer | Legacy duplicate | Can legacy writer retire? |
|---|---|---|---|---|---|---|---|
| GPU | Settings S3 select | LS `comfymodal_gpu` (cache) + `.modal_settings.json["gpu"]` | YES — POST `/config {gpu}`, catalog-validated, restart-seeded (F8) | `resolve_request_gpu()` at acceptance → plan `request_metadata.selected_gpu` | plan → transport; canvas `get_gpu()` | legacy panel dropdown (server-first, one explicit-change POST); dead `window._comfyModalGpu` already removed | YES — retire dropdown + LS cache with legacy panel; authority unaffected |
| Execution/run mode (engine) | Settings S2 select | `.modal_settings.json["execution_mode"]` | YES — resolver chain, env lock honored | captured into `modal_options.execution_mode` at submit; immutable per request | all four dispatch sites | legacy panel engine select (same server authority, second writer) | YES — retire with legacy panel; single Settings writer remains |
| Run mode (Cloud/Local) | Settings S1 segmented | LS `comfymodal_enabled` + window global | NONE | n/a (never reaches server) | canvas redirect gate ONLY | IS the legacy twin (modern copy mirrors legacy key) | YES — no modern consumer; safe to remove from modern Settings now, canvas behavior is H1's |
| Workspace | NONE in modern Settings; legacy panel section | `.modal_workspaces.json` active_workspace_id | YES — server resolves at dispatch | captured once at route entry (`_active_workspace()`) | plans, transports, `modal://` assets | legacy panel is the ONLY writer UI | Must RE-HOME to Backend page BEFORE legacy panel retirement (else workspace selection becomes API-only) |
| Preview enabled (default) | Settings S4 | LS + `.modal_settings.json["preview_default"]` | YES (server-first sync) | snapshot → `output_mode=preview` in immutable plan | plan builders (Single/Workflow/Experiment cells) | none beyond shared helper | n/a |
| Preview codec | Settings S11 | LS + server (`webp` single-option) | YES | frozen into preview conversion options | conversion pipeline | none | n/a |
| Preview quality | Settings S12 | LS + server (1–100) | YES | frozen (`contracts.py:556`) | conversion pipeline | none | n/a |
| Output save folder | Settings S9 | LS + server | YES | generation-time snapshot AND save/export-time LIVE read (F9 uses live `_load_modal_settings`) | auto-save materialization; export service | legacy panel outputs (aligned server-first in F4B) | YES — retire with legacy panel |
| Output format | Settings S5 | LS + server | YES | snapshot (generation) + live (save/export) | remote conversion + local materialization | legacy panel twin | YES |
| Output quality | Settings S6 | LS + server (0–100) | YES | same dual timing | same | legacy panel twin | YES |
| WebP lossless | Settings S7 | LS + server | YES | same | same | legacy panel twin | YES |
| Metadata sidecar | Settings S10 | LS + server | YES | same | materialization + export | legacy panel twin | YES |
| Auto-save local | Settings S8 | LS + server | YES | generation-time snapshot | `result_delivery.materialize_modal_result` | legacy panel twin | YES |
| Grid columns | Settings S14 | LS `comfymodal-studio-history-columns` | NO (browser-only by design) | mount-time read | History V2 grid (F4C) | orphan legacy reader `studio-history.js:517-519` | YES — legacy reader retires with legacy History |
| Tracing/diagnostics | Settings S17 | LS + `.profile_config.json` via POST `/profile/level` | YES (persisted vs effective truth model, F4A) | n/a (process-level, restart-required) | profiler modules | `wall_clock_trace_v3.py` private copy (consistent post-restart) | leave ownership as-is (diagnostics-owned) |
| Experiment concurrency | NONE (info row) | NONE | backend-fixed `EXPERIMENT_CONCURRENCY = 6` | n/a | modern scheduler | stale keys removed in F4A | done |
| History visibility/filter | History view-state namespace (`history-v2-view-state.js`) | LS (durable namespace) | NO | n/a | History V2 | none | n/a — outside reset set by contract |
| Auto-save drafts / playground state | implicit | `comfymodal.studio.playground.v1/drafts.v1/results.v1` | NO | n/a | Playground | none | n/a — durable namespaces preserved by Reset All contract |
| V1-only settings | none remain | — | — | — | — | F4A removed `global_concurrency`/`preview_auto_save` | done |

## 8. GPU INVARIANT (preserved from Phase F — do not regress)

Selection precedence: explicit per-request `gpu` → `modal_options.gpu` → canonical persisted/default server GPU → transport env/hardcoded fallback ONLY when nothing captured. Frozen per-plan at acceptance; Generate Original / Retry / Resume / Experiment Retry/Resume dispatch saved plans WITHOUT a gpu kwarg and never reread Settings. **H2 recommendation must not introduce any Settings reread during replay/resume/retry.**

Legacy GPU UI that can disappear WITHOUT affecting authority: the legacy-panel GPU dropdown (server-first reader + one explicit-change POST — duplicated control, not duplicate authority), the LS `comfymodal_gpu` display cache (once its last readers retire with the legacy panel), and any residual window-global writes. None of these is authoritative; the server chain is the sole authority.

## 9. WORKSPACE AUTHORITY

- Store: ONE server registry (`.modal_workspaces.json`, `active_workspace_id`) — healthy single-authority persistence.
- Write paths: POST `/comfymodal/workspaces` (upsert, optional set_active), POST `/comfymodal/workspaces/active`, swap flow commit. Multiple ROUTES, but exactly ONE UI writer today: the legacy settings panel's Workspace section.
- Runtime consumption: server-side capture at dispatch; requests never carry a workspace; per-request override does not exist (the `workspace` handler parameters are fed internally, not from the browser).
- **Recommendation (do not implement in H2):** the Backend page becomes the canonical workspace surface (credentials, active selection, swap, deploy state already live adjacent to it: deploy status/routes, snapshots, presets). Settings must not gain a workspace control. Before H1 removes the legacy panel, the Workspace section must be re-homed, otherwise workspace management becomes API-only — a regression trap.

## 10. BACKEND PAGE VS SETTINGS — OWNERSHIP BOUNDARY

Derived from current functionality:

| Belongs in SETTINGS (user preferences) | Belongs in BACKEND (runtime/deployment identity & status) |
|---|---|
| GPU default for future runs (user-facing compute preference; availability shown truthfully) | Workspace credentials/selection/swap/deploy state |
| Preview defaults (on/off, codec, quality) | Deployment readiness/read-only mirrors currently surfaced as Settings Advanced rows (deploy state, snapshots/presets/backends counts) |
| Output format/quality/WebP/auto-save/folder/sidecar | Snapshots & Presets management (already there) |
| Grid columns, tracing level, panel layout | Engine deployment readiness detail (V1/V2 app/class readiness) |
| (transitional) Execution Engine until V1 retirement completes | Portability stays in WORKFLOWS (G §38 — do not move) |

Controls currently in the wrong place:
1. **Workspace section inside the legacy settings panel** — deployment identity buried in a preferences panel scheduled for retirement; belongs on Backend.
2. **Settings Advanced read-only deploy/backend-count rows** — tolerable as mirrors, but their natural home is Backend; at minimum they must never become writable there.
3. **The word "Backends" for comparison-profile compatibility store** (`/studio/backends`, `.studio_backends.json`) — a misnomer that collides with the Backend page and with any future provider vocabulary; rename/retire under H1's legacy cleanup, do not build on it.
4. **Run mode (S1)** — gates nothing modern; belongs neither in Settings nor Backend in its current form (see §11).

## 11. RUN-MODE REDESIGN OPTIONS

**Option A — "Execution: Local / Modal", V1 eliminated.**
Semantic truth: high ("Modal" names the actual remote; "Local" would finally mean local execution). UX clarity: good, but only if Local becomes REAL for Studio (plan/history semantics on local queue) — that is a new product, not a consolidation. Migration cost: high (build local-execution semantics) or dishonest (keep Local as canvas-only while labeling it a Studio mode). History/replay: unchanged for Modal; undefined for Local. Experiments: Modal-only. Settings complexity: one mode control retained. Extensibility: neutral.

**Option B — "Execution: Local / Cloud", Cloud backend = Modal.**
Semantic truth: low-medium — "Cloud" is marketing-vague and now collides with G's portability targets (users will ask why RunPod/Comfy Cloud aren't selectable "Clouds"). UX clarity: familiar but misleading. Migration cost: low (rename only). History/replay/Experiments: unchanged. Settings complexity: same as A. Extensibility: pretends multi-provider without any provider abstraction — worst fit with G's hard requirement.

**Option C — Single-engine Studio: no persistent Run mode; Modal V2 is the only Studio execution engine.**
Semantic truth: highest — proven reality: modern Studio has exactly one execution backend (Modal V2 after V1 retirement) and zero modern consumers of Run mode. "Local" is demoted to what it actually is: a legacy canvas behavior, documented as such, owned by H1's canvas cleanup. No per-run backend selector is needed because there is nothing to select (per-run selection without a second backend is pure UI cost). GPU remains the only execution-affecting user setting. `COMFYMODAL_RUNTIME` env lock survives as the ops escape hatch. Migration cost: lowest of the honest options (remove S1 from modern Settings; retire S2 after V1 elimination; keep canvas pass-through untouched). History/replay: strengthened (every new row reproducible). Experiments: already V2-only in practice. Settings complexity: reduced by two controls. Extensibility: when a second real backend ever exists, introduce per-run/explicit selection THEN, with real semantics — not before.

**Comparison:** C wins semantic truth, migration cost, History stability, and Settings complexity; A wins only if local Studio execution becomes a roadmap product (it is not today); B loses on truth and G-alignment.

**RECOMMENDATION: Option C.** Concretely: (1) remove Run mode (S1) from modern Settings (no modern consumer; keep the legacy canvas key behavior untouched for H1 to retire with the canvas); (2) eliminate V1 + shadow from the resolver's public vocabulary after the §5 blockers close, leaving V2 as the only Studio engine; (3) GPU stays in Settings as the sole execution preference; (4) workspace/deploy identity moves to Backend; (5) never render the six portability targets as engines. If product later demands a visible mode pair, use Option A's vocabulary ("Modal" / "This machine") — never B's "Cloud".

## 12. STATE MIGRATION STRATEGY (design only — do not implement)

Requirements: no silent switching of existing users to a different execution backend; unsupported old values get an explicit safe fallback; no stale key remains authoritative; migration idempotent.

1. **Persisted `execution_mode:"v1"`** (in `.modal_settings.json`): at load, normalize-and-migrate ONCE to `"v2"` with (a) a logged, surfaced one-time notice in Settings/Backend ("Engine V1 retired; future runs use V2"), (b) rewrite of the persisted key, (c) in-flight/accepted requests unaffected (capture-at-acceptance already makes this impossible to mutate mid-flight). Idempotent: migrating an already-"v2" value is a no-op. Env lock (`COMFYMODAL_RUNTIME`) continues to win over everything — ops deployments are never silently flipped.
2. **Unknown/garbage `execution_mode` values:** existing `normalize_mode → None → default v2` fallthrough already provides the safe fallback; keep it and add the same surfacing.
3. **LS `comfymodal_enabled`:** cease being written by modern Settings; leave the existing key inert for the canvas era (deletion belongs to H1's canvas retirement). Never map its value onto any new concept — it never affected Studio, so mapping would fabricate semantics.
4. **LS `comfymodal_gpu`:** retain strictly as display cache until the legacy panel retires, then delete key + readers together (F8 guard test pattern extends naturally).
5. **No stale key remains authoritative:** extend the F4A authority guard test so every removed key is asserted absent from writers, and every surviving key keeps classified reader/writer evidence.
6. **Reset-set hygiene:** keys leaving `MODERN_SETTINGS_KEYS` (e.g. `comfymodal_enabled`) must leave the reset lists in the same change (the F4A stale-key lesson).

## 13. RESET ALL — CURRENT BEHAVIOR AND FINAL SEMANTICS

Current (verified `studio-settings.js:261-359`): clears exactly `MODERN_SETTINGS_KEYS` (15 keys; durable namespaces preserved); POSTs `{execution_mode:"v2", gpu:<catalog default>}` (Generation reset AND Reset All); resets outputs via `setOutputPreferences(OUTPUT_DEFAULTS)`; profile level → off; confirmation copy discloses engine-V2 and GPU resets (F8 truthful disclosure).

Final expected semantics after consolidation:
- PRESERVE: server-truth resets (POST /config), GPU reset to catalog default (hidden-GPU aware), output defaults, tracing → off, durable-namespace survival, truthful disclosure copy.
- CEASE: resetting/writing `comfymodal_enabled` (key leaves the reset set with S1's removal); forcing `execution_mode` once the setting itself retires (the POST degrades to `{gpu: default}` alone — engine reset becomes meaningless when only one engine exists); any reset of workspace/deploy state (never was, and must never become, a Settings concern).

## 14. PLAYGROUND / WORKFLOWS / EXPERIMENT PARITY UNDER THE RECOMMENDED MODEL

| Surface | V2 today | After Option C |
|---|---|---|
| Single Playground | ✓ (plan freeze, preview/original, history) | unchanged; v1 branch deleted |
| Workflow run | ✓ (bundle + preset STRICT + plan identity) | unchanged; `_workflow_legacy_run` deleted |
| Experiment run | ✓ (V2 invoker, frozen per-cell GPU, durable cells) | unchanged; `LocalRemoteInvoker` path deleted |
| History replay/resume/retry | ✓ V2-only by design (immutable plans; legacy rows honestly irreproducible) | unchanged; no NEW irreproducible rows ever again |

Mode supported on one surface but not another (current asymmetries that consolidation resolves or must decide):
- **Local execution:** canvas-only — demoted/documented (Option C), never a Studio mode.
- **Preview/Original + Resume:** V2-only — acceptable; V1 rows truthfully lack them.
- **Comparison runner (canvas A/B):** V1-only — THE one genuine blocker requiring a product decision before V1 deletion (retire the feature, or re-home it onto V2 plans). H2 flags it; does not decide implementation.
- **Shadow diagnostics:** cross-engine but non-product — retires with V1.

## 15. PORTABILITY IS NOT EXECUTION — NAMING GUARDS

Phase G added six advisory targets, not six engines (G closure §15, §33 "Six provider execution engines" rejected; §37 invariants 11–14, 24). Violations/near-violations to guard during H:
1. Settings/Backend must never list `local/modal/runpod/runcomfy/comfy_cloud/baseten` as selectable execution anything.
2. The words "Local" and "Modal" appear in BOTH the Run-mode control and the target matrix; after Option C removes S1, the collision shrinks to the legacy canvas — keep the matrix strictly inside the Portability panel under its "Target readiness" title.
3. The legacy `/studio/backends` "backends" (comparison profiles) must not be repurposed as a provider registry.
4. The Backend page must not grow a "providers" tab implying execution breadth the app does not have; its truthful scope is workspace/deployment/runtime status.

## 16. IMPLEMENTATION SEAMS (for the implementing lane; NOT executed by H2)

- `execution_runtime.py`: collapse `AVAILABLE_EXECUTION_MODES`; make `validate_config_payload` reject `v1` (migration gate); keep alias normalization for idempotent migration; keep env lock.
- `__init__.py`: `/config` GET/POST execution_mode handling + `_default_modal_settings`; startup migration notice; canvas v1 branch (~line 2561) removal; `/studio/backends` family tagging.
- `studio_run_adapter.py`: `handle_studio_run_async` non-V2 branch; `_schedule_and_start` invoker split; `direct_studio_run_completion` retention decision (still used by workflow legacy path only after cleanup).
- `studio_workflow_run.py`: `_workflow_legacy_run` removal.
- `experiment_runner.LocalRemoteInvoker` + legacy scheduler registration: removal owner per H1 boundaries.
- `web/studio-settings.js`: delete S1 section + `comfymodal_enabled` from keys/resets; retire S2 after V1 elimination; Reset All POST shape.
- `web/modal-settings.js`: run-mode toggle, engine select, GPU dropdown retirement; Workspace section re-home to `web/studio-backend.js` BEFORE panel removal.
- Tests to evolve: `test_phase8_execution_mode.py`, `test_f8_gpu_authority.py`, `studio_phase_f4_settings_authority_unit.mjs`, `studio_phase_f8_gpu_reset_unit.mjs`, plus a new migration test (persisted v1 → v2, idempotent, env-lock respected).

## 17. RISKS

1. **Biggest semantic risk — "Local" ambiguity:** three distinct meanings today (portability target, canvas pass-through, implied Studio mode). Removing S1 (Option C) eliminates the worst ambiguity; renaming instead (Options A/B) perpetuates it.
2. **Silent engine flip:** migrating persisted `v1` users to `v2` changes remote execution behavior; must be explicit, disclosed, idempotent, and env-lock-respecting (§12.1).
3. **Workspace orphaning:** deleting the legacy panel before re-homing Workspace removes the only selection UI.
4. **Comparison runner breakage:** V1 retirement silently kills canvas A/B comparison unless decided first (§14).
5. **Provider-suggestion drift:** any future UI that renders portability targets near execution controls risks users believing RunPod/Comfy Cloud etc. execute workflows; G's vocabulary discipline must be enforced in code review and tests.
6. **Reset-copy drift:** disclosure copy references "execution engine … V2" — must be updated in the same change as engine-setting retirement or it becomes a false statement.

---

**Audit-only batch:** files modified = this report only. Deploy / live / GPU / commit / push: **NONE**.
