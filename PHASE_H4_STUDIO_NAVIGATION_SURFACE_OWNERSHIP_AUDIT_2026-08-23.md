# PHASE H4 — Modern Studio Navigation, Surface Ownership & UX Consolidation Audit (2026-08-23)

Lane: H4 (Studio consolidation — navigation, surface ownership, transitional UX). Read-only audit of the CURRENT shared working tree. No production/test edits, no deploy/live/GPU, no git actions. H1 (code-level legacy inventory), H2 (exact Run-mode semantics), H3 (stored-reference compatibility) run concurrently; H4 owns navigation, tab/feature ownership, duplicate entry points, surface boundaries, and removal/re-home recommendations.

Evidence is repo-relative with line references. Primary sources: `web/studio-shell.js`, `web/modal-testing.js`, `web/studio-{playground,history-v2,workflows,backend,settings,legacy,feature-registry,model-library,portability,experiment-mode}.js`, `web/modal-{node,settings,comparison}.js`, `web/testing-*.js`, route files (`studio_routes.py`, `studio_workflow_routes.py`, `model_library_routes.py`, `__init__.py`), and frozen Phase C2/F/G contracts (`STUDIO_MODERN_EXPERIMENT_MIGRATION_PLAN.md`, `PHASE_F_FINAL_CLOSURE_ZERO_CONTEXT_HANDOFF_2026-08-23.md`, `PHASE_G4_PORTABILITY_PRODUCT_ARCHITECTURE_AUDIT_2026-08-23.md`).

---

## 0. Verdict (TL;DR)

1. **The top nav already matches the intended modern IA** — exactly `Playground | History | Workflows | Backend | Settings` (`studio-shell.js:20-26`). The intent drift is *inside* the surfaces, not in the tab set: Settings hosts six embeddable legacy tabs plus a standalone legacy overlay, Backend lacks the operational controls users actually need (deploy/workspace/credentials), and Workflows/Backend split preset ownership across two systems.
2. **One canonical History and one canonical portability surface already exist** (History V2 since Phase F; Workflows since Phase G). Navigation honors both freezes. What remains is retiring the legacy mirrors that still point around them.
3. **The single largest consolidation gap is Settings**: it is simultaneously user preferences (correct), an operational runtime readout (belongs to Backend), and the host shell for the entire legacy testing suite (must exit in H).
4. Recommended final IA: **Playground | History | Workflows | Backend | Settings**, Experiments as a Playground mode with results in History, legacy Settings/canvas/comparison surfaces retired behind a sequenced re-home → redirect → remove-nav → retain-reader → delete-code transition.

---

## 1. Current Navigation Map

### 1.1 Top-level tabs (the only modern nav)

Source: `studio-shell.js:20-26` (`PAGES`), rendered as buttons in `comfymodal-studio-topnav` (`:131-141`), active state via `.active` class (`:125-129`).

| # | Label | Component | Visible conditions | Notes |
|---|---|---|---|---|
| 1 | Playground | `renderPlayground` (`studio-playground.js:626`) | always | default `activePage` (`studio-shell.js:30`) |
| 2 | History | `renderHistoryV2` (`studio-history-v2.js`) | always | Phase-F canonical surface |
| 3 | Workflows | `renderWorkflows` (`studio-workflows.js:366`) | always | Phase-G portability surface |
| 4 | Backend | `renderBackend` (`studio-backend.js:139`) | always | presets + snapshots |
| 5 | Settings | `renderSettings` (`studio-settings.js:162`) | always | hosts legacy tabs |

- **Route/state model**: pure in-memory `state.activePage`; **no URL routing, no browser history, no deep links**. Page switching re-renders the whole page container with scroll restoration (`studio-shell.js:62-123`).
- **Keyboard**: shell registers a layer-2 Escape handler (`modal-testing.js:258-267,298-305`) via the layered key system (`studio-ui.js:11-31`: fullscreen 5 → zoom 4 → preview 3 → dialog 2). Focus trap on Tab (`modal-testing.js:17-36`); focus moves into the modal on open and returns to the trigger element on close (`modal-testing.js:275-276,388-391`).
- **Mobile/responsive**: CSS breakpoints at 480/720/768 px exist (`studio-styles.js:69,1695,3437,3454,3813,4638,5598`); the shell itself has no responsive nav behavior (no collapse/hamburger).
- **Accessibility gaps (recorded, Phase-I class)**: nav buttons carry no `aria-current="page"`; active state is visual-only.

### 1.2 Entry points into the Studio modal

| Entry point | Source | Target |
|---|---|---|
| ComfyUI sidebar tab "Modal GPU" | `modal-testing.js:546-559` | panel with **Open Studio** + **Open Legacy Settings** buttons (`buildSidebarPanel`, `:471-493`) |
| Fallback launcher button "Modal GPU" | `modal-testing.js:497-504` (when sidebar API unavailable) | opens Studio |
| Global `window.open_testing_modal(tabName)` | `modal-testing.js:229,588` | opens Studio at mapped page |
| `comfymodal.open-section` DOM event | listener `modal-testing.js:574-577`, handler `:506-520`; dispatched by `testing-settings.js:106,150` | opens **Settings** page and scrolls to `[data-section=…]` |
| Legacy auto-open on module load | `modal-settings.js:1248-1249` (`window.open_testing_modal()`) | opens Studio at Playground |
| Canvas right-click "☁ Modal: Set as comparison ▶" | `modal-comparison.js:1550-1555` | comparison slot submenu (legacy) |
| `window.open_comfymodal_settings()` | `modal-settings.js:4155-4209` | **standalone legacy settings overlay** (outside the Studio shell) |
| `window.openComparisonProfilesOverlay` / `openComparisonRunnerOverlay` | `modal-comparison.js:1643-1653` | standalone legacy comparison overlays |

### 1.3 Hidden / legacy navigation

- **Opt-in legacy sidebar tabs** (registered only when `window.__comfyModalEnableLegacySidebarTabs === true`): "Modal GPU" model-manager panel (`modal-settings.js:4246-4269`), "Comparison Profiles" and runner tabs (`modal-comparison.js:1663-1688`). Off by default.
- **Legacy tab-name alias map** in `open_testing_modal` (`modal-testing.js:244-252`): `dashboard/setup/profiles/results → Settings (+activeLegacyTab)`, `history → History`, `settings → Settings`. This is the compat shim that keeps old callers working.
- **Legacy group inside Settings → Advanced** (`studio-settings.js:632-675`): "Open Legacy Settings" button + clickable list `Legacy Dashboard / Setup / Profiles / Results / History / Settings`, each mounting a `testing-*.js` module through `renderLegacyView` → `context.mountLegacyTab` (`studio-settings.js:1167-1195`, `studio-legacy.js:32-69`).
- **Orphaned module**: `web/studio-history.js` (History V1, ~65 KB) is imported by **nothing at runtime**; only two test files read its source as text (`tests/studio_history_v2_grid_columns_unit.mjs:35`, `tests/studio_phase_f4_settings_authority_unit.mjs:38`). Dead code retained for string assertions.

---

## 2. Feature Ownership Matrix

Legend — Surfaces: **P**layground, **H**istory(V2), **W**orkflows, **B**ackend, **S**ettings, **L**egacy (tabs/overlays/canvas menus). "Secondary OK" = a contextual shortcut/pointer in a second surface is acceptable.

| Feature | Current surfaces | Recommended single owner | Secondary entry allowed? | Reason |
|---|---|---|---|---|
| Run generation (single) | P (Run button, `studio-playground.js:2909+`); L canvas `/prompt` interception (`modal-node.js:672-809`) | **Playground** | Contextual: History "Generate Again"/"Resume" (`studio-history-v2-detail.js:977,1008,1018`) | Composition+run is Playground's core; History reruns are record-driven shortcuts into the same pipeline |
| Experiment run | P experiment mode (`studio-experiment-mode.js`, "Run Experiment" `:963-998,1966,2030`); L Setup/Results tabs | **Playground (mode)** | History detail Retry/Resume/Cancel cell actions (`studio-history-v2-experiment.js:640-693,1107`) | Frozen C2 constraint: experiments live inside Playground; History owns result-space actions |
| Workflow management (versions, mapping, tags, folders) | W detail (`studio-workflows.js:1766-2286`); P selectors consume | **Workflows** | P "Open Workflows" link (`studio-playground.js:1584`) | Authority chain Workflow→Version→Mapping is W's domain (G4 §2.1) |
| Workflow portability (manifest import/export, check, checklist) | W only (`studio-workflows.js:1863-2054`, `studio-portability*.js`) | **Workflows** | No | Phase-G freeze: sole portability surface |
| Workflow Presets | W presets section/editor (`studio-workflows.js:2289-2708`); P consumes via run-context | **Workflows** | P selector (consumption only) | G4 authority chain; editing belongs with versions/mapping |
| Backend/runtime Presets ("Backend Presets") | B tabs (`studio-backend.js:210`); P "Backend" selector consumes (`studio-playground.js:785,1257`) | **Backend** (transitional) — converge on Workflow Presets long-term | P consumption | Two preset systems exist (C2 §1.4); B presets remain the non-workflow runtime path until convergence |
| Presets (legacy prompt/image, `presets.py`) | L setup tab internals | none (compatibility-only) | No | Legacy experiment substrate; superseded by modern experiment path |
| History (feed/detail) | H; L History tab (`testing-history.js`); P recent-runs filmstrip | **History V2** | P filmstrip = contextual shortcut (keep) | Phase-F freeze; filmstrip is session-scoped convenience, not a second store |
| Original generation | H detail "Generate Original"/"View Original" (`studio-history-v2-detail.js:495-1018`) | **History** | No | Record-driven replay is a history action (E3/F1 semantics) |
| Download / Export | H detail per-output Browser Download + configured Export (`studio-history-v2-detail.js:214-269`); P metadata "Save output" (`studio-playground.js:5292-5333`) | **History** | P "Save output" = single-output shortcut (keep) | F3/F10 froze download/export semantics in History |
| Experiments (results/detail) | H experiment detail; P experiment grid viewport; L Results tab | **History** (results) + **P** (live grid during run) | No | Same data, two phases of one flow; L Results retires |
| Model management (library, rescan, details, install request, notes) | W → Model Library sub-view (`studio-workflows.js:654-666`, `studio-model-library.js`); L panel Models section (`modal-settings.js:3401`) | **Workflows → Model Library** | Dependencies section links from version detail | One library UI over `/studio/models*` routes; legacy Models section duplicates it with older UX |
| Custom nodes | L Sync section (`modal-settings.js:3152`); W Dependencies (custom node rows, `studio-model-library.js:557,627`) | **Workflows → Model Library/Dependencies** | No | Registry routes already unified under `model_library_routes.py` |
| Workspace (Modal account workspaces CRUD/select) | L panel Workspace section only (`modal-settings.js:2050-2323`) | **Backend** (re-home required) | No | No modern home today; operational account state |
| Deployment/backend status + deploy/redeploy | L panel deploy buttons + banner/poll (`modal-settings.js:1271-1292`); S Advanced read-only deploy state (`studio-settings.js:585-591,857-869`); L Dashboard hero (`testing-dashboard.js:117-133`) | **Backend** (re-home actions; S readout moves or links) | No | Users cannot deploy from any modern surface — functional regression if legacy dies first |
| Runtime health / readiness | S Generation engine readiness line (`studio-settings.js:755-765`); L Dashboard workers/last-run | **Backend** | S may keep engine *preference* only | Readiness is operational state, not preference |
| GPU selection | S Generation (`studio-settings.js:469-471,813-855`); L panel GPU selector (`modal-settings.js:1474`) | **Settings** (preference; server `/config` is truth) | No | H2 owns exact Run-mode semantics; both current writers hit the same endpoint, so consolidation is safe |
| Run mode (Cloud/Local) | S General segmented control (`studio-settings.js:409-441`); L panel Run Mode toggle (`modal-settings.js:1417`) | **Settings** | No | Duplicate writers of `comfymodal_enabled`; keep one |
| Execution engine (v1/v2) | S Generation (`studio-settings.js:448-486`); L panel engine section (`modal-settings.js:1548-1611`) | **Settings** (label semantics deferred to H2) | No | Duplicate POST `/config execution_mode` |
| Output settings (format/quality/save folder/sidecar/auto-save) | S Outputs (`studio-settings.js:489-1092`); L Output Options (`modal-settings.js:1692`) | **Settings** | No | Both already share `studio-output-preferences.js` dual-write authority |
| Preview settings | S Generation (default) + Outputs (codec/quality) | **Settings** | No | Already consolidated server-side |
| History layout (grid columns) | S History (`studio-settings.js:497-513`) consumed by H (`studio-history-v2.js:31-63`) | **Settings** | No | Correct pattern: preference in S, consumption in H |
| Diagnostics/tracing | S Advanced heavy tracing + restart banner (`studio-settings.js:550-676,1094-1158`); L deploy logs | **Settings** (level preference) + **Backend** (logs/live diagnostics) | No | Split preference vs operational logs |
| Model compatibility (annotations) | W detail "Compatible models" chips (`studio-workflows.js:1596-1599`) + version compatibility routes (`model_library_routes.py`) | **Workflows** | No | Distinct concept from portability (§13) |
| Favorites / notes | H detail + feed filters; P favorite star + note editor on selected run (`studio-playground.js:4920-5007`); W workflow favorite (`studio-workflows.js:589`) | **History** (runs) / **Workflows** (workflows) | P star/note = contextual edit of selected run (keep) | Same annotation APIs, record-scoped owners |
| Credentials (HF token, auth status) | L panel only (`modal-settings.js:1082,3698-3777`) | **Backend** (re-home required) | No | Account/provider concern, not user preference |

---

## 3. Playground — Should Own / Should Not Own

**Owns (confirmed by code):**
- Composing and running a request: feature tabs (`renderFeatureTabs:5107`), preset/workflow/version selectors (`:785-790,1257,1492-1568`), derived controls (`:793-941`), Run/Cancel (`renderRunButton:2909`), progress (`renderProgressSection:3288`).
- Current Workflow/Preset selection incl. gating line and handoff to Workflows when nothing is selected (`_workflowGatingLineEl:1570-1594`).
- Immediate run feedback: canvas output, live-return control (`renderLiveReturnControl:5183`), running-config freeze panel (`renderRunningConfigPanel:3379`).
- Experiment mode as an overlay on the same controls (toggle at panel top, `:770-782`) — per frozen C2 constraint.
- Session-scoped "Recent runs" filmstrip as a contextual bridge back into just-made results (`renderFilmstrip:5613`), including EXP-badged experiment reopen via `loadExperimentIntoPlayground`.
- Lightweight result actions on the selected run: favorite star, note editor, "Save output", timing card (`renderMetadataSection:5212-5333`).

**Should NOT own (drift found):**
- **Full note editing + favorite toggling duplicated from History detail** — acceptable as contextual shortcut, but P writes through `updateRunAnnotation` while H owns presentation semantics; keep P's copies minimal (star + quick note) and link to History for the full record. Currently P's note editor is a complete second implementation (`renderNoteEditor:4967`).
- **Timing/diagnostics card** (`timingStages` block, `:5335+`) — diagnostic depth belongs to History detail (which already renders Timing/Diagnostics sections); P should keep only the compact duration line.
- **Placeholder features pointing users to legacy**: `object_remove`/`object_replace` specs say *"Use Settings > Legacy Setup for the full experiment suite"* (`studio-feature-registry.js:22,32`) and LoRA help text says *"Configured in Settings > Legacy Setup"* (`:166`). These are the strongest remaining **user-facing funnels into legacy Settings** and must be re-worded when legacy exits.
- Nothing else mislives here; the "Go to Backend tab to create presets" pointer (`:830-837`) is correct cross-surface navigation.

## 4. History — Final Ownership

**Preserves (all present in V2 code):**
- Feed: search, kind filter (All/Generations/Experiments), status toggles with always-visible guarantees, boolean filters (favorite/preview/original/has-image), workflow/preset/date filters, sort, paginated sparse cards (`studio-history-v2.js:633-884`, repository adapter).
- Detail: per-output Browser Download + configured-folder Export with truthful variant labeling (`studio-history-v2-detail.js:214-269,439-460`), Set as featured, Note, Other outputs, Original slot (view / generate / failed-retained states), Parameters, Diagnostics, Timing, Resume, Generate Again, Generate Original, Favorite, Errors (`:361-1147`).
- Experiments: one card in the feed; dedicated experiment detail page with cells, per-cell retry, experiment retry/resume/cancel, note (`studio-history-v2-experiment.js`).
- Notes/favorites: durable via repository annotations; feed refetches on detail mutation (`studio-history-v2.js:590-601`).

**Should NOT own:** configuration. Today the only setting that lives here is none — grid columns correctly lives in Settings and is consumed read-only (`studio-history-v2.js:31-63`). The hidden "Demo data" mode banner (`:657-663`) is fixture-mode signaling, not a user feature; ensure it can never render outside fake/test mode. No configuration functions currently leak into History — this surface is already clean.

## 5. Workflows — Final Ownership

**Preserves Phase G (all present):**
- Versioning: Versions section with capture-new-version (`studio-workflows.js:1766-1845`); immutable-version revision flow for mapping edits ("Save as New Workflow Version", `:2142`).
- Mapping: role rows, candidates, immutability-confirming editor (`:2056-2286`).
- Workflow Presets: create/duplicate/edit/delete/set-default/bulk-copy-forward (`:2289-2708`).
- Run context: Run bar hands off to Playground ("Opens the Playground with this version's controls.", `:1707-1765`).
- Model compatibility: compatible-models chips + PATCH-able annotations (`:1596-1599`; `model_library_routes.py` compatibility endpoints).
- Portability: Check / Export manifest / Checklist, six-target readiness matrix, environment risk, stale-cache chips (`:1863-2054`; `studio-portability.js`, `studio-portability-checklist.js`); manifest import with dry-run preview (`renderImportManifestDialog:1004-1368`).

**Duplicated elsewhere that must point INTO Workflows:**
- **Backend "Make Preset" wizard** captures the *current ComfyUI graph* into snapshot+preset (`studio-backend.js:110-135`) while Workflows "Import" captures the same graph into workflow+version (`renderImportDialog:831-1002`). Two graph-capture entry points creating two parallel object families. Recommendation: keep both objects short-term (they serve different run paths) but make Backend's wizard explicitly the "runtime preset" path and add a pointer "Want versioned, portable workflows? Use Workflows → Import." Long-term: converge on Workflow Presets and demote Backend presets to compatibility-only.
- **Model Library placement**: it is a sub-view of Workflows (`_view.mode === "models"`, `:388-390`, sub-nav `:654-666`) — correct owner; no other modern surface links to it. Legacy Models/Sync sections must redirect here (§10).

## 6. Backend — Should Own

Current content: "Make Preset" action + two tabs (**Backend Presets** | **Snapshots**) with list/detail/forms (`studio-backend.js:139-236`, `studio-backend-presets.js`, `studio-backend-snapshots.js`).

Recommended ownership after H:
- **Modal workspace/account**: workspace select/create/edit/delete (re-home from legacy panel `modal-settings.js:2050-2323`); auth/connection status (`buildAuthPanel:1082`).
- **Deployment status + actions**: deploy / redeploy-and-restart, deploy state banner, deploy log, warmup status (re-home from `modal-settings.js:1271-1611`; routes already exist: `__init__.py:4334-4368,7693-7779`).
- **Runtime health**: engine readiness (v1/v2 deployment status currently rendered inside Settings Generation, `studio-settings.js:755-765`), worker/last-run telemetry (currently only in legacy Dashboard).
- **Provider/backend diagnostics**: deploy logs, warmup invalidation, HF token + credentials (`modal-settings.js:3698-3777`).
- **Snapshots** (already here) and **Backend Presets** (transitional owner, §5).
- Model/custom-node management stays in **Workflows → Model Library** (architecture supports it there; routes are shared).

**Misplaced in Backend today:** nothing material — the gap is omission (deploy/workspace/credentials absent), not clutter. Do not decide Run-mode labels here; that is H2's lane (Settings General keeps the Cloud/Local preference; Backend only reflects resulting connection state).

## 7. Settings — Should Own

Principle: user preference/configuration only; no operational dashboards.

Audit of current seven sections:
| Section | Verdict |
|---|---|
| General (Run mode) | Keep (preference). Info row text mentioning nav is stale once IA settles — copy pass in Phase I |
| Generation (Engine, GPU, Preview default) | Keep as *preferences*. Move the **readiness line** to Backend; keep the engine/GPU selectors (H2 decides final labels) |
| Outputs | Keep — canonical preference surface, correct dual-write module |
| History (grid columns) | Keep — model example of S-owns-preference / H-consumes |
| Experiments (informational) | Keep as info-only or fold into Interface; harmless |
| Interface (panel layout reset) | Keep |
| Advanced | **Split.** Heavy tracing level = keep (preference with server persistence). The whole **"Runtime & Backend" group** (deploy state, snapshots/presets/backends counts, "Open Backend tab" link — `studio-settings.js:578-630`) is operational state → move to Backend. The entire **"Legacy" group** (`:632-675`) → remove after exit checklist (§10) completes |

Anything that is actually Backend operational state: deploy state row, runtime inventory counts, engine readiness. All flagged above.

## 8. Experiments — Final Placement

**Recommendation: Playground mode (composition/live grid) + History child surface (results/detail). No dedicated top-level tab.**

Evidence:
- Frozen C2 constraint: "Experiments live inside Playground… History displays one Experiment card with its cells" (`STUDIO_MODERN_EXPERIMENT_MIGRATION_PLAN.md` §0).
- Implementation already matches: toggle atop Playground control panel (`studio-playground.js:770-782`), experiment grid replaces workspace during runs (`renderWorkspace:5076-5084`), filmstrip EXP badges reopen experiments (`:5743-5745`), History V2 has kind filter + full experiment detail (`studio-history-v2-experiment.js`).
- A third surface (legacy Results tab, `testing-results.js`) duplicates live monitoring + adds the A/B comparison workspace; it retires with the legacy suite (§12).
- Domain semantics untouched per brief; only placement affirmed.

## 9. Duplicate Entry Points

| # | Action | Appears in | Decision | Rationale |
|---|---|---|---|---|
| 1 | Workflow import (capture current graph) | W Import dialog; B "Make Preset" wizard | **Keep both, clarify labels** (different artifacts); add cross-pointer | Different object families today; convergence is post-H |
| 2 | Manifest import/export | W only | Canonical (W) | Phase-G freeze |
| 3 | Workflow run | P Run (with W/P selectors); W Run bar handoff | **Keep both** — W's is a redirect/handoff, P is canonical executor | Handoff pattern already correct |
| 4 | Model management | W Model Library; L panel Models; L Sync | **Canonical W; retire L** after parity check (install-request exists in both) | Same backing routes |
| 5 | Settings access | S tab; sidebar "Open Legacy Settings"; S→Advanced legacy group; L Dashboard "Settings" quick action; gear button in L panel | **Canonical S page; redirect/retire all legacy openers** | Four paths into legacy config is the core H4 defect |
| 6 | Export/download | H detail (canonical); P "Save output" | **Keep both** — P is single-output contextual shortcut | F3/F10 semantics intact |
| 7 | Experiment open | P filmstrip EXP item; H experiment card; L Results | **Keep P + H; retire L Results** | P = live/session, H = record |
| 8 | Backend config (GPU/engine/run-mode) | S page; L panel equivalents | **Canonical S; retire L duplicates** | Identical endpoints; dual writers risk drift |
| 9 | Deploy | L panel buttons; L Dashboard hero; S read-only state | **Re-home actions to B; S drops readout** | Only working deploy UI is legacy today |
| 10 | Comparison | L Profiles tab; L overlays; canvas context menu; L Results A/B workspace | **Retire surface** (§12) after Experiment-mode coverage verified | Superseded for preset comparison; A/B image compare re-home decision below |
| 11 | History | H V2 page; L History tab; P filmstrip | **Canonical H; retire L tab; keep filmstrip** | Filmstrip is session-contextual |
| 12 | Notes/favorites | H detail; P metadata; W favorite | **Keep** (record-scoped owners) | No second store involved |

## 10. Legacy Settings Exit Checklist

Goal: a user never needs legacy Settings after Phase H. Every current reason, with status:

| # | Reason a user still enters legacy Settings | Modern replacement | Status / action |
|---|---|---|---|
| 1 | Run mode Cloud/Local | S General | ✅ replaced — remove L toggle |
| 2 | Execution engine v1/v2 | S Generation | ✅ replaced — remove L section |
| 3 | GPU selection | S Generation | ✅ replaced — remove L selector |
| 4 | Output format/quality/folder/sidecar/auto-save | S Outputs | ✅ replaced (shared authority module) — remove L collapsible |
| 5 | Deploy / Redeploy+Restart / deploy log / warmup | ❌ none | ⚠️ **RE-HOME to Backend first** (routes exist) |
| 6 | Workspace select/create/edit/delete | ❌ none | ⚠️ **RE-HOME to Backend** |
| 7 | HF token / auth-status credentials | ❌ none | ⚠️ **RE-HOME to Backend** |
| 8 | Models browse/download/add | Partial (W Model Library: rescan, install-request, notes) | ⚠️ **Verify parity** (Add-Model folder list, download progress) then retire L Models |
| 9 | Custom nodes sync/refresh | W Dependencies + registry routes | ⚠️ Verify refresh/install-request UI parity, then retire L Sync |
| 10 | Legacy experiment Setup (drafts, model stacks, LoRA baseline) | P experiment mode | ⚠️ Blocked by placeholder features (`object_remove/replace` registry copy directs users to Legacy Setup) — rewrite copy; keep draft-state shim until features land |
| 11 | Legacy Profiles (comparison profiles) | None modern | ⚠️ Compatibility-only (§12) — hide, retain reader |
| 12 | Legacy Results (live experiment monitor + A/B) | P grid + H experiment detail | ✅ replaced except A/B slider (§12) |
| 13 | Legacy History | H V2 | ✅ replaced |
| 14 | Legacy Dashboard (deploy hero, metrics) | B (after #5) | ✅ after re-home |
| 15 | Logs & diagnostics | S heavy tracing (level) + B deploy log (after #5) | ✅ after re-home |

**Concrete "legacy Settings removable" gate** = items 5, 6, 7 re-homed; 8, 9 parity-verified; 10 copy rewritten + draft shim in place; 11–14 retired or redirected. Until then, the Settings→Advanced→Legacy group and sidebar "Open Legacy Settings" must stay.

## 11. Legacy Canvas Exit Checklist

"If the legacy canvas UX were hidden tomorrow, what is lost?" — classified:

| Capability | Where | Classification |
|---|---|---|
| Native-canvas Generate routed to Modal (`/prompt` interception) | `modal-node.js:672-809` | **compatibility-only** — ComfyUI-native graph users' path; modern Playground independent. Hide = those users lose cloud routing |
| Canvas progress bar + timing | `modal-node.js:584-656` | **already replaced** for Studio runs (P progress section); **not needed** for canvas-native runs unless #1 kept |
| Production mode: Mark as Production Output / Bypass menus + validation | `modal-node.js:821-1007` | **must re-home or keep** — unique capability (Simulate Production), no modern equivalent |
| "Set as comparison" context menu | `modal-comparison.js:1423-1558` | **compatibility-only** → retires with Comparison (§12) |
| Benchmark workflow snapshot capture | `modal-node.js:560-575` | **not needed** (internal telemetry) |
| Auto-open Studio modal on load | `modal-settings.js:1248-1249` | **not needed** — surprising behavior; retire early |
| Legacy sidebar tabs (opt-in) | `modal-settings.js:4246`, `modal-comparison.js:1663-1688` | **already replaced** — keep opt-in flag one transition, then delete |
| `comfymodal-progress.js` shared tracker | used by modal-node AND Playground | **keep** — shared infra, not legacy |

Do not remove anything in H; this table feeds the H-transition sequence.

## 12. Comparison UX — Retire / Re-home / Keep

**What the old Comparison surface uniquely does:** saves the current graph as a *comparison profile* with slot mappings (`@prompt`, `@seed` token injection via node titles, `modal-comparison.js:579`), runs identical inputs across N profiles, renders a results gallery + A/B slider (`testing-results.js:1153-1207`, `testing-ab-slider.js`).

**Compared against modern surfaces:**
- *History detail*: single-record outputs; no cross-run A/B or shared-input sweep. Does not cover it.
- *Experiment mode (Compare Presets)*: covers the dominant use case — same inputs across multiple presets/axes — with better semantics (immutable versions + mapping instead of slot-path mutation). G4 §2 evidence: comparison profiles mutate graphs via slot paths against legacy presets, contradicting the frozen immutable-Version/Mapping authority.
- *Image grid*: experiment grid covers N-way visual scanning.
- *Featured/output navigation*: History detail handles per-output browsing.

**Recommendation:**
- **Retire** the Comparison Profiles/Runner surface and its three entry points (Profiles tab, overlays, canvas menu) — its profiling role is superseded by Experiment mode; its slot-mutation mechanics conflict with the frozen domain chain.
- **Re-home (Phase I candidate, not H)**: the A/B *image* slider as a lightweight compare of two outputs inside History detail or the experiment grid — the one genuinely missing modern capability (evidence: no cross-output slider exists outside `testing-ab-slider.js`).
- **Keep (compatibility-only, hidden)**: backend comparison routes + stored profiles readable (H3 lane owns stored-reference safety); no nav entry, no canvas menu.

## 13. Portability vs Compatibility Naming

Phase-G freeze preserved in code: **Portability** = version-scoped export/readiness ("Portability risk …", six-target matrix, `studio-portability.js:90-111,290`); **model Compatibility** = `compatible_models` chips + version compatibility annotations (`studio-workflows.js:1596-1599`). Assessment:

- Both concepts render on the same workflow detail page (chips in sidebar; Portability section below Dependencies). Wording itself is disjoint — no label collision found ("Portability" never describes models; "Compatible models" never describes environments).
- Residual confusion risk: the card-level **portability chip** and the detail **compatible-models chips** look alike (same chip component family). This is a Phase-I visual-distinction task, not a renaming task. **No renaming recommended.**

## 14. UX Consistency (consolidation-level only)

Inconsistencies that make surfaces feel like different products (polish items excluded):

1. **Two design systems coexist**: modern `el()`-built pages (layer-managed dialogs, `data-testid` discipline, aria-pressed chips) vs legacy modules (innerHTML-era patterns, manual ESC handlers, `z-index: 99998/99999` overlays, `showToast`). Opening a legacy overlay *on top of* the Studio modal creates two independent Escape stacks (shell layer-2 handler + overlay's own `document.addEventListener("keydown")`) — the exact class of conflict the layer system was built to prevent.
2. **Dialog patterns differ**: modern dialogs get focus trap + inert background + focus restore (`modal-testing.js:17-66`); legacy overlays (`open_comfymodal_settings`, comparison overlays) have none.
3. **Heading hierarchy**: Workflows renders an `h2` title; Playground/History/Backend/Settings have no page heading (the only `h2` is the shell's "Modal GPU"). Settings uses `h3` sections + `h4` groups; Backend uses unlabeled tab buttons.
4. **Verb drift for the same concept**: "Make Preset" (B) vs "New Preset" (W) vs "Capture new version" (W); "Import" vs "Import workflow manifest"; two unrelated buttons both labeled "Open Legacy Settings".
5. **Error surfacing**: modern pages use inline status lines/banners; legacy uses toasts; Settings mixes `confirm()` dialogs with transient spans.
6. **Loading states**: legacy `bootstrapLoader` skeleton vs modern bare "Loading…" paragraphs.
7. **Chip semantics**: feature chips are true `aria-pressed` buttons (B features grid); status/portability chips are static spans — semantically fine but visually near-identical (feeds §13 risk).
8. **ESC/focus**: solid in the shell; broken (duplicated handlers, no restore) in every legacy overlay.

Items 1–2 and 8 are *structural* (H-relevant: they exist only because legacy surfaces are still mounted); 3–7 are Phase-I polish.

## 15. Final Information Architecture (proposal — do not implement)

**Top-level tabs (order unchanged):**

| Tab | Owns | Stops owning |
|---|---|---|
| **Playground** | Compose + run single generations and experiments; workflow/version/preset selection; run controls & live progress; recent-runs strip; quick result actions (favorite/note/save) | Deep diagnostics (→ History detail); legacy funnels in copy |
| **History** | Canonical feed + generation/experiment detail; Browser Download; configured Export; Original lifecycle; notes/favorites; Resume/Retry/Generate-Again/Original | Nothing (already clean) |
| **Workflows** | Workflow library; versions; mapping; Workflow Presets; Model Library + dependencies + custom nodes; model compatibility; portability + manifest import/export; run handoff | — |
| **Backend** | Modal account/auth + workspace; deploy/redeploy + status/log/warmup; runtime health/readiness; snapshots; Backend Presets (transitional); credentials; provider diagnostics | — |
| **Settings** | Preferences only: run mode, engine/GPU/preview defaults, outputs, history layout, interface, tracing level | Runtime & Backend readouts (→ Backend); entire Legacy group (→ removed) |

- **Experiments live**: Playground mode (compose/run/live grid) + History child surface (records/detail). No top-level tab.
- **Disappears**: legacy Settings overlay + its four openers; six legacy tabs; legacy Dashboard; legacy Results (incl. A/B workspace pending §12 re-home); legacy History; comparison Profiles/Runner + canvas menu; legacy sidebar tabs; `studio-history.js` V1 dead module; modal-settings auto-open.
- **Redirects**: `open_testing_modal("setup|profiles|results|dashboard")` alias map retained → lands on modern equivalents; "Open Legacy Settings" buttons → `setPage("settings")`; feature-registry placeholder copy → Workflows/roadmap wording; Backend preset wizard gains "for versioned portable workflows use Workflows → Import" pointer.
- **Remains compatibility-only but hidden**: comparison profile reader (backend routes + stored data, H3-governed); legacy setup draft store (until placeholder features ship); legacy canvas `/prompt` interception + production-mode menus (canvas-native path) — hidden from Studio nav, not deleted.

## 16. Transition Strategy (sequenced, no giant deletion patch)

1. **H-a · Re-home (additive)**: build Backend account/deploy/workspace/credentials/diagnostics panels from existing routes; verify Model Library parity for legacy Models/Sync. No removals yet — legacy stays usable.
2. **H-b · Redirect (shim)**: repoint "Open Legacy Settings" (sidebar + Settings group) to `setPage("settings")`; rewrite feature-registry legacy copy; keep `open_testing_modal` alias map and `mountLegacyTab` machinery intact but unreferenced from primary nav.
3. **H-c · Remove nav entries**: drop Settings→Advanced→Legacy group; drop sidebar legacy button; disable modal-settings auto-open; legacy sidebar tabs stay opt-in-off. Legacy becomes reachable only via direct globals (compat).
4. **H-d · Retain readers**: backend comparison/legacy-experiment routes stay read-only; stored references validated by H3 before any store retirement.
5. **H-e · Delete dead code (later batch, with test updates)**: `studio-history.js`, `testing-*.js` modules, `modal-comparison.js` UI layer, legacy overlay builders, and the test files that assert on their source strings — each deletion accompanied by its test-lane edits so the deterministic gate (`tests/run_studio_tests.py --fake` + `npm run test:fake`) stays green per batch.

Each step is independently shippable and reversible; steps a–b are purely additive/redirective and carry near-zero regression risk.

## 17. Phase I Boundary

**Phase H (structural consolidation)**: everything in §15–16 — ownership moves, redirects, nav removals, re-homes, dead-surface retirement, resolving the dual-design-system coexistence by *removing* legacy surfaces (not restyling them).

**Phase I (final polish), explicitly deferred from H**: `aria-current` and nav keyboard semantics; page-heading hierarchy; verb/label normalization pass; toast/banner/error-pattern unification; loading-state components; chip visual taxonomy (incl. portability-vs-compatibility distinction); responsive nav behavior; focus-visible polish; copywriting; A/B compare feature in History (new capability, §12); URL deep-links/routing (new infrastructure, product decision).

---

## Appendix A — Key file map (evidence index)

| Surface | Files |
|---|---|
| Shell/nav | `web/studio-shell.js` |
| Bootstrap/entry | `web/modal-testing.js` |
| Playground | `web/studio-playground.js`, `studio-playground-run.js`, `studio-playground-state.js`, `studio-experiment-mode.js`, `studio-feature-registry.js` |
| History | `web/studio-history-v2.js`, `-detail.js`, `-experiment.js`, `history-v2-*.js` |
| Workflows | `web/studio-workflows.js`, `studio-portability.js`, `studio-portability-checklist.js`, `studio-workflow-run.js`, `studio-model-library.js` |
| Backend | `web/studio-backend.js`, `-presets.js`, `-snapshots.js`, `-capture.js`, `studio-preset-wizard.js` |
| Settings | `web/studio-settings.js`, `studio-output-preferences.js` |
| Legacy | `web/modal-settings.js`, `modal-comparison.js`, `studio-legacy.js`, `testing-*.js` |
| Canvas extension | `web/modal-node.js`, `comfymodal-progress.js` |
| Routes | `__init__.py` (config/deploy/profile/open-folder), `studio_routes.py` (snapshots/presets), `studio_workflow_routes.py`, `model_library_routes.py`, `history_v2_routes.py`, `experiment_modern_routes.py` |
