# PHASE H5 — STUDIO CONSOLIDATION CONTRACT FREEZE (2026-08-23)

**Batch type:** H5 = contract freeze / reconciliation only. No production code, no tests modified, no legacy deletions, no deploy, no Modal/GPU/live generation, no commit/push/branch/worktree/reset. Files modified by this batch: **this document only**.
**Authority:** This document is THE authoritative implementation contract for the remainder of Phase H (Studio Consolidation). Where H1/H2/H3/H4 preliminary classifications differ, the reconciled decisions HERE win. Later H implementation lanes must cite this contract; deviations require a new freeze batch.
**Inputs (read completely):** `PHASE_F_FINAL_CLOSURE_ZERO_CONTEXT_HANDOFF_2026-08-23.md`, `PHASE_G_FINAL_CLOSURE_ZERO_CONTEXT_HANDOFF_2026-08-23.md`, `PHASE_H1_LEGACY_V1_RETIREMENT_AUDIT_2026-08-23.md`, `PHASE_H2_RUN_MODE_SETTINGS_AUTHORITY_AUDIT_2026-08-23.md`, `PHASE_H3_REFERENCE_INTEGRITY_HISTORICAL_COMPATIBILITY_AUDIT_2026-08-23.md`, `PHASE_H4_STUDIO_NAVIGATION_SURFACE_OWNERSHIP_AUDIT_2026-08-23.md`.
**Source spot-verifications performed by H5 (contradiction checks only):** `execution_runtime.py` alias/env vocabulary (`_LEGACY_ALIASES` = v1/legacy/v2/shadow; unrecognized env logged-and-ignored), `studio_workflow_run.py:1556` hardcoded `"execution_mode": "v1"`, unregistered status of `tests/studio_legacy_settings_authority_unit.mjs` (absent from `tests/run_studio_tests.py` registration), `__init__.py:7330` "legacy compatibility / import-only" comment on `/studio/backends`.

---

## 0. VERDICT

`H5 COMPLETE — CONSOLIDATION CONTRACT FROZEN.`

H1/H2/H3/H4 contradictions are reconciled (§1). One Comparison fate, one execution model, one Settings scope, one Backend ownership, one Experiment authority, three distinctly named preset systems, one compatibility freeze, seven dependency-safe implementation waves, eleven writer lanes, one test-baseline decision, twenty-six must-preserve invariants, and an explicit Phase-I boundary are frozen below.

---

## 1. RECONCILED DECISIONS (audit contradictions resolved)

| # | Topic | H1 said | H2/H4 said | FROZEN |
|---|---|---|---|---|
| R1 | Comparison Profiles/Runner | LIVE unique capability → RE-HOME management UI | Superseded by Experiment mode; slot mutation conflicts with immutable Version+Mapping → RETIRE surface | **RETIRE the Comparison execution/product UI in Phase H** (H4's product direction) while preserving H1's data discipline: stored profiles, backend read compatibility, and legacy routes-as-read-only-compatibility survive hidden. A/B image slider is Phase-I. Full detail §7. |
| R2 | Canvas Production mode | Unique live canvas capability (KEEP) | "Must re-home or keep" | **Stays with the canvas compatibility layer for Phase H.** Not re-homed into Studio absent a real modern requirement. Must not block legacy Settings/navigation removal. §9. |
| R3 | Run mode Cloud/Local | UNKNOWN → defer to H2 | Option C (single-engine; remove S1) | **Option C frozen.** Modern Settings Run mode is retired; canvas key untouched. §4. |
| R4 | Settings General Run-mode row | (n/a) | H4 provisional "keep as preference" vs H2 "remove" | **REMOVE** — H2 Option C wins; zero modern consumers (F4 S1, reconfirmed by H2 §1). |
| R5 | V1 engine | RETIRE option, keep resolver shim; blockers enumerated | COMPATIBILITY_ONLY; same four blockers | **COMPATIBILITY-ONLY, SCHEDULED FOR RETIREMENT** in Wave C after Comparison/shadow blockers close per §5/§6. |
| H1-vs-H3 wave numbering | H1 proposed Waves 1–5 | Batch mandates Waves A–G | **Waves A–G (§25) supersede H1 §12**; H1's wave content is mapped into them. |
| R6 | Bridge History repository | "RETIRE (unreachable)" | H3: underlying legacy run-history routes/data are NOT deletion-ready | **Split decision:** bridge MODE may retire (programmatic-only); legacy run-history read routes/storage remain compatibility shims. §20. |
| R7 | Legacy experiment creator | RETIRE after H2 defines story | H3: consumers still exist (Playground hydration, polling) | **Scheduled retirement as NEW-write authority**, sequenced consumer-migration-first (§14 six-step order). |

---

## 2. FINAL TOP-LEVEL IA AND SURFACE OWNERSHIP (FROZEN)

Top nav remains exactly five surfaces, order unchanged: **Playground | History | Workflows | Backend | Settings** (`studio-shell.js` PAGES). **No new top-level tabs.**

### PLAYGROUND owns
- compose/run Single; compose/run Experiments (experiment-v2);
- Workflow/Version/Preset selection for running;
- immediate progress/results;
- recent-runs shortcut (filmstrip — contextual, not a second History authority);
- lightweight result actions (favorite star, quick note, Save output, compact duration line).

### HISTORY owns
- canonical durable feed/detail (History V2 is the SOLE durable History);
- Experiment result/detail;
- Resume / Retry / Generate Again / Generate Original;
- Original lifecycle (view/generate/failed-retained);
- Browser Download; configured-folder Export;
- durable notes/favorites;
- deep run diagnostics (Timing/Diagnostics sections).

### WORKFLOWS owns
- Workflow library; immutable Versions; Mapping; Workflow Presets;
- model dependencies; Model Library + custom-node dependency surfaces;
- model **Compatibility** (annotations — distinct concept, never merged with Portability);
- **Portability** (sole portability surface — Phase-G freeze intact: chips, panel, Export popover, Import dialog, checklist);
- manifest Import/Export.

### BACKEND owns
- Modal workspace/account identity; workspace CRUD/activation/swap; truthful active identity;
- deployment/redeployment controls; deploy status; runtime health/readiness;
- logs/warmup/repair operational controls;
- credentials/auth status;
- snapshots;
- **transitional Backend Presets** (`.studio_presets.json`) until their separate convergence authority is decided (§15B).

### SETTINGS owns preferences ONLY
- GPU default; Preview defaults; output preferences; History layout (grid columns); interface preferences; tracing LEVEL preference.
- Operational state/readouts belong in Backend, never Settings.

### Cross-surface rules
- Experiments remain: compose/run/live grid in Playground + durable results/detail/actions in History. No dedicated tab (frozen C2 constraint).
- Portability remains solely in Workflows. Model Compatibility remains distinct from Portability.
- Playground keeps only contextual shortcuts into History-owned semantics (star/note/save on the selected run); full record semantics live in History.

---

## 3. EXECUTION MODEL — H2 OPTION C FROZEN

Modern Studio is **SINGLE-ENGINE**. The canonical Studio execution engine is **Modal V2**.

There is NO modern: Local execution engine; generic Cloud provider selector; RunPod executor; RunComfy executor; Comfy Cloud executor; Baseten executor. Phase G's six targets (`local · modal · runpod · runcomfy · comfy_cloud · baseten`) are **ADVISORY portability targets only** (G closure §15/§33/§37 unchanged). **No provider selector is built during H.**

Naming guards (from H2 §15, binding on all H lanes):
1. Settings/Backend must never list the six target ids as selectable execution anything.
2. The target matrix stays strictly inside the Workflows Portability panel under its "Target readiness" title.
3. `/studio/backends` must not be repurposed as a provider registry (§19).
4. Backend must not grow a "providers" tab implying execution breadth the app does not have; its truthful scope is workspace/deployment/runtime status.
5. If product ever demands a visible mode pair, use "Modal" / "This machine" vocabulary — never "Cloud" (H2 §11).

---

## 4. MODERN RUN MODE — RETIRED

The modern Settings Cloud/Local "Run mode" is **RETIRED**. Reason: zero modern Studio consumers (F4 S1; H2 §1 verified); it controls only legacy canvas `/prompt` interception (`modal-node.js:678,841`).

Consequences (binding):
- Remove it from modern Settings in an implementation lane (Wave C).
- Stop writing/resetting `comfymodal_enabled` from modern Studio (key leaves `MODERN_SETTINGS_KEYS` and every reset list in the SAME change — F4A stale-key lesson).
- DO NOT delete or reinterpret the legacy browser key yet: canvas keeps reading `comfymodal_enabled` / `window._comfyModalEnabled` until canvas compatibility is separately retired.
- DO NOT map it to any new Studio concept (mapping would fabricate semantics — H2 §12.3).
- This eliminates the dangerous triple meaning of "Local" (portability target / canvas local pass-through / implied Studio execution mode). After S1 removal the collision shrinks to the legacy canvas + the Portability matrix, which stays title-scoped.

---

## 5. V1 STATUS — COMPATIBILITY-ONLY, SCHEDULED FOR RETIREMENT

Frozen: **V1 = COMPATIBILITY-ONLY AND SCHEDULED FOR RETIREMENT.** No product capability of V1 is lacking in Modal V2 (H2 §2/§5: V1 lacks everything modern; V2 lacks nothing). New modern Studio runs ultimately become V2-only.

V1 deletion cannot occur until its two remaining dependencies are resolved:
1. **legacy Comparison runner** (`/comparison/run` executes via V1 `run_prompt_stream`) — resolved by R1: Comparison retires; sequencing rule in §25 Wave C/E.
2. **shadow diagnostics** — retires with V1 (§6).

Additionally, persisted `execution_mode="v1"` requires the explicit idempotent migration of §12. **Do not remove V1 in the first H implementation wave.**

V1-only artifacts scheduled for removal in Wave C (per H2 §16 seams): `AVAILABLE_EXECUTION_MODES` v1 entry; both engine selects; `/config` acceptance of v1; canvas v1 branch; `handle_studio_run_async` non-V2 branch; `_workflow_legacy_run`; `LocalRemoteInvoker` + legacy scheduler registration; Reset-All engine forcing. `MODE_SHADOW` alias handling follows §6.

---

## 6. SHADOW STATUS + COMFYMODAL_RUNTIME OPS-LOCK DECISION

Frozen: **Shadow is diagnostic-only, non-user product behavior. It retires with V1.** Public Studio configuration must never expose shadow (already true: POST `/config` rejects shadow; only env/handcrafted requests reach it).

**Ops-lock decision (explicit, per H5 mandate to decide rather than leave accidental):**
- The `COMFYMODAL_RUNTIME` environment lock **mechanism is preserved** as an ops/internal escape hatch (precedence request-captured > env > persisted > default, unchanged).
- **Transition window** (Waves A–B, until V1 branch deletion lands): the env lock's accepted vocabulary remains today's `{v1, legacy, v2, shadow}` — needed for deterministic cross-engine diagnostics while both executors still exist.
- **At V1 branch deletion (Wave C completion), the env lock's accepted vocabulary intentionally COLLAPSES TO `{v2}`.** Values `v1`/`legacy`/`shadow` become logged-and-refused at resolution time (warning log + fall through to next precedence, which can only yield v2). Rationale: keeping retired vocabularies accepted after their executors are deleted would make the resolver return modes with no dispatch path — dishonest reachability. Shadow without a V1 executor is meaningless by construction.
- Public `/config` rejects `v1` (new at the retirement gate) and `shadow` (already) both before and after.
- In-flight/accepted requests are unaffected: capture-at-acceptance immutability holds; no retroactive rewrite of queued requests.
- `is_v2()`/`is_shadow()` dead helpers are removed in Wave B (zero callers, H1-verified); their removal does not change resolver behavior.

---

## 7. COMPARISON — FINAL FATE (resolves R1)

### PRODUCT DECISION: RETIRE the Comparison execution/product UI in Phase H.

Retire (Wave E):
- Comparison Profiles editor UI (`testing-profiles.js`);
- Comparison Runner UI + overlays (`modal-comparison.js` overlay builders; `testing-ab-slider.js` results workspace);
- Comparison overlays' entry buttons (Legacy Dashboard);
- canvas comparison slot context menu (`modal-comparison.js:_initContextMenu` — the always-on slot-mapping menu);
- legacy Comparison entry points (Dashboard buttons, programmatic window globals);
- the V1 dependency created solely for Comparison execution.

DO NOT:
- port the legacy Comparison execution model to V2;
- create a modern Comparison profile domain;
- reproduce slot-path graph mutation (conflicts with immutable WorkflowVersion + Mapping authority — G §37 invariant).

KEEP (hidden compatibility):
- stored comparison-profile data (`user/default/comfy-modal/comparison_profiles/<id>/…`, comparisons dir) — untouched;
- backend read compatibility needed for old records/tools (`/comparison/*` read paths) — retained as read-only compatibility where safe;
- legacy routes as read-only compatibility where safe.

No destructive migration of comparison data.

### A/B IMAGE SLIDER: DEFERRED TO PHASE I.
A lightweight two-image compare/slider in History or Experiment result space is useful but is a NEW UX capability, not required for Phase-H structural consolidation. **Phase H must not retain the entire old Comparison system merely to preserve the slider.**

---

## 8. LEGACY CANVAS — COMPATIBILITY SURFACE (FROZEN BOUNDARY)

The ComfyUI canvas `/prompt` interception is NOT part of modern Studio. It is a separate canvas-native compatibility path.

During Phase H KEEP:
- `/prompt` interception (`api.fetchApi` patch → `/comfymodal/prompt`);
- Cloud/Local canvas pass-through semantics (including the `comfymodal_enabled` gate);
- the output-option chain needed by canvas (`window._comfyModalOutputOptions` maintenance + 6 output LS keys — single shared-helper maintenance point, F deferral #4 upheld);
- Production-mode behavior where still functional (§9).

DO NOT:
- expose canvas Local as a Studio execution engine;
- migrate canvas graphs into WorkflowVersions automatically;
- rewrite historical graphs;
- delete the canvas execution path during early H waves.

Possible future canvas retirement is SEPARATE and must not block Studio consolidation. `comfymodal-progress.js` is shared modern infra (used by modal-node AND Playground) — KEEP, not legacy.

---

## 9. CANVAS PRODUCTION MODE

Production-mode marking ("Mark as Production Output" / "Bypass in Production", graph extra `comfymodal_production_mode_enabled`, LS `comfymodal_production`) **remains with the canvas compatibility layer for Phase H.** Do NOT re-home it into Studio unless a real modern product requirement emerges. It must not block removal of legacy Settings/navigation. (Resolves R2.)

---

## 10. BACKEND RE-HOME — HARD PREREQUISITES AND OPERATION CLASSIFICATIONS

**Hard prerequisite:** before retiring the legacy settings panel, modern Backend MUST gain parity for the still-needed operational controls (H1 §13 "must not remove yet" #6; H4 exit-checklist items 5–7). No legacy-panel removal lane may start while a REQUIRED row below is un-re-homed.

### 10.1 Required re-home categories (frozen minimum)

**Workspace** — list; active selection; add/edit where currently supported; swap; truthful active identity. (Server authority already singular: `.modal_workspaces.json` `active_workspace_id`; server-resolved at dispatch; browser never sends a workspace.)

**Deployment/runtime** — deploy/redeploy actions currently needed by users; deploy status; readiness/runtime health; logs/status diagnostics; warmup IF still legitimate (implementation lane must verify legitimacy, else classify RETIRE); repair actions that are not obsolete.

**Credentials/account** — auth status; HF token/auth-related controls that still have valid product use; secret handling must follow existing backend contracts (never echo secrets).

**Model operations — DIVIDED (do NOT blindly re-home all legacy model controls to Backend):** H4 places Model Library in Workflows. Inventory of legacy Models/Sync actions:
- model-library/dependency actions (browse, rescan, per-item install-request, notes, custom-node sync/refresh) → **Workflows / Model Library** (parity verify in Wave A3, then retire legacy duplicates);
- deployment/runtime operational model actions (e.g. remote volume/inject operations if genuinely required by deployment) → **Backend**, only if still genuinely required;
- obsolete duplicate download/install UI (bulk `/models/batch-install`, `/model/install` raw flows, download-progress polling) → **RETIRE** unless the Wave-A3 parity audit proves a real gap — and a proven gap re-homes into **Workflows Model Library**, not Backend.

No new duplicate model-installer authority is created anywhere.

### 10.2 Manifest-repair / workspace-repair operation classification (frozen)

Legend: KEEP_AND_REHOME_BACKEND / COMPATIBILITY_ONLY / RETIRE. Every old button is NOT inherently valuable; classifications use current route consumers and product semantics.

| Legacy-panel operation | Classification | Notes |
|---|---|---|
| Workspace list / active select / add / edit / swap | **KEEP_AND_REHOME_BACKEND** | Wave A1. Only UI writer today (H2 §9). |
| Workspace registry export/import | **KEEP_AND_REHOME_BACKEND** | Low priority; rides A1. |
| Deploy trigger / redeploy-and-restart | **KEEP_AND_REHOME_BACKEND** | Wave A2. Routes exist (`__init__.py` deploy family). Only working deploy UI is legacy (H4 #9). |
| Deploy status banner / poll / deploy log | **KEEP_AND_REHOME_BACKEND** | Wave A2. Settings keeps NO deploy readout after consolidation. |
| Warmup status / warmup invalidation | **KEEP_AND_REHOME_BACKEND** *(conditional)* | Wave A2 verifies warmup is still legitimate; if obsolete → RETIRE. |
| Deploy repair actions | **KEEP_AND_REHOME_BACKEND** where non-obsolete; else **RETIRE** | Per-action verdict recorded by the A2 lane. |
| Auth status / HF token controls | **KEEP_AND_REHOME_BACKEND** | Wave A2. Existing secret-handling contracts. |
| Model-manifest repair/rebuild (`/manifest*`) | **KEEP_AND_REHOME_BACKEND** pending non-obsolescence proof; if the A2 lane proves obsolete → **RETIRE** | Operational deployment-bootstrap concern, not a preference. |
| Model inject / inject-all | **RETIRE** as duplicate UI; if an operational remote-volume action proves genuinely required → **Backend** | Dependency-driven install already lives in Workflows install-request. |
| Bulk batch-install / raw download tooling + progress polling | **RETIRE** (gap-proven items → Workflows Model Library) | §24 pipeline distinction. |
| Snapshots CRUD | Already Backend — no move. | |
| Backend Presets management | Already Backend (transitional owner) — no move. | §15B. |

---

## 11. SETTINGS FINAL CONTRACT

### KEEP (after H)
GPU · Preview defaults · output preferences · History grid/layout · interface preference · tracing level.

### REMOVE
- Cloud/Local Run mode (Wave C, §4);
- V1/V2 Execution Engine selector — after V1 retirement (Wave C);
- Runtime & Backend operational readouts (deploy state row, snapshots/presets/backends counts, engine readiness line → Backend; Wave A2/E);
- entire Advanced Legacy group (Wave E, after exit checklist §21 gate);
- legacy counts/launchers whose owner has moved.

### Reset All after consolidation MUST
- reset GPU to canonical catalog default (hidden-GPU aware, server POST);
- reset outputs;
- reset Preview/preferences;
- reset tracing according to existing rules (persisted-vs-effective truth model, F4A);
- preserve durable namespaces (`playground.v1/drafts.v1/results.v1`, History view-state — outside reset set, F4A);
- NOT reset workspace/deploy state (never a Settings concern);
- NOT write `comfymodal_enabled`;
- NOT force `execution_mode` once V2 is the only public engine (Reset POST degrades to `{gpu: default}` alone; disclosure copy updated in the SAME change — H2 risk #6).

---

## 12. PERSISTED EXECUTION_MODE MIGRATION CONTRACT (design frozen; do not implement in H5)

Persisted `execution_mode = "v1"` migrates ONCE to `"v2"`:

- **idempotent** (migrating an already-"v2" value is a no-op);
- **persisted server value rewritten** (`.modal_settings.json["execution_mode"]`);
- **accepted/in-flight requests unaffected** (capture-at-acceptance immutability guarantees this);
- **one-time truthful notice surfaced** (logged + surfaced in Settings/Backend: "Engine V1 retired; future runs use V2");
- **unknown/invalid old values safely normalize to v2** (existing `normalize_mode → None → default v2` fallthrough kept, plus the same surfacing);
- **no silent transformation of `comfymodal_enabled`** (browser key untouched; never mapped to a new concept);
- **env-lock precedence preserved** according to §6 (env wins over persisted; post-collapse vocabulary `{v2}`).

Migration test obligations (Wave C lane): persisted v1→v2 rewrite; idempotent re-run; env-lock respected; unknown-value normalization; notice emitted once.

---

## 13. STUDIO_WORKFLOW_RUN V1 REMNANT

The hardcoded `"execution_mode": "v1"` / `"execution_mode_source": "default"` metadata pair around `studio_workflow_run.py:1556` (verified present today) is a **transitional implementation remnant inside the legacy workflow-single compilation dict**. It is removed **when the surrounding V1 branch is deleted** (Wave C). Do NOT patch it independently before the surrounding branch retirement if doing so would make legacy behavior dishonest (a "v2" label on a V1-executed legacy run would falsify history metadata).

---

## 14. LEGACY EXPERIMENT SURFACE — FATE AND ORDER

Frozen: **Modern Experiments are authoritative** = Playground experiment-v2 (compose/run/live grid) + History V2 Experiment records/actions. The legacy `/studio/experiment` creator and the `experiments/` JSON execution system are **scheduled for retirement as NEW-write authorities.** H3 proves current consumers still exist, therefore implementation ORDER is frozen:

1. remove the modern Playground fallback that creates legacy experiments (`experimentRunSurface() === "legacy"` path);
2. ensure every normal modern experiment path is experiment-v2;
3. migrate recent-runs hydration away from legacy experiment GETs (§23);
4. retire legacy Experiment UI creators (Setup/Results tabs);
5. freeze legacy Experiment data/routes READ-ONLY where required for old records;
6. only later remove dead scheduler/write paths.

**No destructive migration of old experiment data.** Mirrored terminal cells in History V2 stay valid regardless (self-contained generations). Legacy-engine lifecycle routes (`/experiments/compile|create|start|pause|stop-*|resume|clone|run-missing|checkpoints/*|cells/*|rerun*`) retire only together with the testing-suite surface that consumes them (H3 §10 #7).

---

## 15. LEGACY PRESET SYSTEMS — THREE DISTINCT AUTHORITIES (DO NOT CONFLATE)

Phase H must NOT simply rename all three "Workflow Presets."

**A. Workflow Presets** — Workflows authority; immutable-version-scoped; modern portable workflow concept (G authority chain: version-tied, mutable values). Owner: Workflows.

**B. Backend/Runtime Presets** — `.studio_presets.json` via `/studio/presets*`; currently consumed by the Playground non-workflow run path (`getRuntimePresets`/`listPresets` → `POST /studio/run` carries legacy `presetId`) and the Backend page + wizard. **Still LIVE. Remains transitional in Backend until a later explicit convergence decision.** Do NOT delete `.studio_presets.json` in early H — H3 identifies it as a live runtime authority and the highest-risk "legacy" store (History `preset_id` provenance spans BOTH namespaces depending on era; merging files would falsify provenance — H3 §6/§14 #4).

**C. Legacy prompt/image Comparison/setup presets** — `.presets/prompts|images` (`presets.py`); compatibility/legacy experiment substrate; **retire with the legacy experiment/comparison creator surfaces**; stored readers may remain for existing user presets.

---

## 16. HISTORY COMPATIBILITY — HARD FREEZE (MUST-PRESERVE INVARIANT)

History V2 is self-contained. **DO NOT ADD live lookups from History render/replay to:** Workflow store · Version store · Mapping store · Preset stores (either) · Model Library · custom-node registry · portability cache · compatibility annotations.

Replay authority remains: `request_snapshots.execution_plan_json` plus copied immutable snapshot provenance (validated in place; identity consistency across plan/request/preset-snapshot/generation; the ONE sanctioned external resolution is the active-workspace fallback for pre-workspace-id snapshots, §18). Adding any "freshness" lookup would convert today's deletion-tolerance into a new failure mode and violate Phase-F invariant 1. This is a MUST-preserve invariant (#6 of §28).

---

## 17. WORKFLOW DELETION

Public Workflow deletion remains OUT OF CURRENT H EARLY WAVES. If lifecycle deletion is implemented later: prefer archive/tombstone semantics (H3 §5 referential policy: soft archival flags, refuse-while-child-rows-exist guard, tombstones over erasure). **Never cascade into History.** Do not add delete merely to aid consolidation.

---

## 18. COMPATIBILITY ROUTES/STORES — MUST SURVIVE EARLY H (H3 DO-NOT-DELETE FREEZE)

At minimum, early Phase H MUST retain:

- `GET /comfymodal/run-history` (Playground recent-runs + bridge consume it today);
- `PATCH /comfymodal/run-history/{id}/annotations` (bridge + one-way migration source; F froze it);
- `GET /comfymodal/experiments` (Playground recent-runs consumes it);
- `/comfymodal/studio/presets*` + `.studio_presets.json` (live Playground runtime selection authority — highest-risk store);
- `POST /comfymodal/studio/run` (live single-run acceptance path freezing RequestSnapshots);
- `/comfymodal/studio/snapshots*` (Backend page mounted today);
- legacy experiment routes while any creator/reader consumes them;
- `.run_history` readers (`REGISTRY.history()`, `history_index.py`) + derived index;
- `legacy_mapping` table + dormant `LegacyMigrationSeam`;
- replay capability projection (`replay_capable` + machine-readable reasons) — never removed;
- workspace fallback for old snapshots (`_resolve_replay_workspace` / `_resolve_workspace_dict`);
- portability fail-open cache behavior (derived, TTL-free, non-gating; sidecar relocation only beside domain stores);
- `GET /history` unified platform feed (platform route; leave alone);
- `/studio/outputs/{filename}` + legacy output dir fallback (while legacy-run images render);
- model-compatibility endpoints/vocabulary distinct from portability; `compatible_models` stays on the write-once Version record.

**Do not conflate UI retirement with route/data deletion.** Removing a production route requires removing its fake-backend mirror + specs in the same contract change (H3 §13 #11).

---

## 19. /STUDIO/BACKENDS MISNOMER

Frozen: `/studio/backends` / `.studio_backends.json` represents **comparison-profile compatibility/import data** (source comment `__init__.py:7330` "legacy compatibility / import-only"; discovery folds comparison profiles in as "backends"). It is NOT: an execution provider registry; the modern Backend page authority; a future multi-provider abstraction. **Do not build new features on this name.**

Because modern Backend currently consumes discovery/count data (and Settings counts rows): keep compatibility initially. Future implementation (Wave F) replaces modern consumers with a truthfully named route/data seam, THEN demotes `/studio/backends` to a hidden read-only shim. Do not hard-delete it before consumers move.

---

## 20. DEAD SURFACES — SAFE RETIREMENT SET (Wave B)

First proven-safe deletion set (H1 reverse-import verified):

- orphaned `web/studio-history.js` (zero importers; relocate its still-tested pure helpers first; prune its structural tests in the same lane);
- hidden legacy sidebar tab REGISTRATIONS (`__comfyModalEnableLegacySidebarTabs` blocks in `modal-settings.js`/`modal-comparison.js`);
- dead `execution_runtime.is_v2`;
- dead `execution_runtime.is_shadow`;
- Legacy Dashboard UI tab (`testing-dashboard.js`);
- Legacy History UI tab (`testing-history.js`).

**Nuance (resolves R6):** the bridge History repository MODE itself is technically programmatic-only and retirement-ready, BUT its underlying legacy run-history routes/data are NOT deletion-ready. Thus: bridge MODE may later retire (collapse `HISTORY_V2_MODES`, e4c/e4d assertions updated in the same lane); legacy read routes/storage remain compatibility shims.

---

## 21. LEGACY SETTINGS EXIT SEQUENCE (FROZEN ORDER)

A. **Re-home** operational controls to Backend/Workflows (Waves A1/A2/A3 — gate: H4 checklist items 5/6/7 re-homed; 8/9 parity-verified; 10 copy rewritten + draft shim).
B. **Redirect** old openers to modern owners (§22).
C. **Remove** Settings Advanced Legacy group.
D. **Remove** standalone legacy Settings overlay (`open_comfymodal_settings` panel; disable `modal-settings.js` auto-open).
E. **Retain** route/data compatibility (§18).
F. **Later delete** unreachable modules (Wave G).

Do NOT delete `modal-settings.js` wholesale while the canvas/other modules still import useful shared behavior unless importer analysis proves safe (it shares `studio-output-preferences.js` wiring and canvas globals).

Dual-design-system conflict (two Escape stacks, z-index wars, focus-trap absence) is resolved by REMOVING legacy surfaces, not restyling them (H4 §14/§17).

---

## 22. OLD OPENERS / REDIRECTS (EXPECTED BEHAVIOR — implement in Wave B/E, not H5)

| Opener | Frozen redirect |
|---|---|
| sidebar "Open Legacy Settings" | → modern Settings or Backend depending context; preferably ELIMINATE the ambiguous generic opener after its callers are migrated |
| `open_testing_modal("dashboard")` | → Backend (operational dashboard intent) |
| `open_testing_modal("setup")` | → modern relevant owner or deprecation message; NEVER opens dead legacy Setup |
| `open_testing_modal("profiles")` | → Workflows/Experiments according to actual caller context; since Comparison UI retires, NEVER opens a recreated Comparison editor |
| `open_testing_modal("results")` | → History |
| `open_testing_modal("history")` | → History |
| `open_testing_modal("settings")` | → Settings |

If exact caller context makes a universal mapping unsafe, the implementing lane documents the safe compatibility behavior (e.g., deprecation toast naming the modern owner) instead of forcing a wrong landing. Feature-registry placeholder copy funneling users to "Settings > Legacy Setup" (`object_remove`/`object_replace`, LoRA help) is rewritten in the same wave (strongest user-facing legacy funnels, H4 §3).

---

## 23. PLAYGROUND RECENT-RUNS MIGRATION (required BEFORE legacy-feed GET retirement)

Future target (Wave D): Playground recent-runs stops hydrating from the three legacy feeds (`/run-history?limit=50`, `/history`, `/experiments`). Preferred modern authority: **History V2 feed / experiment projections**.

Requirements:
- preserve mixed Single + Experiment recent display;
- preserve click/open behavior (incl. EXP-badge reopen);
- NO second History authority;
- old historical rows remain visible through migrated History V2 data;
- legacy feeds remain compatibility-only after consumer removal.

This migration is REQUIRED before retiring legacy run-history/experiment GET dependencies (§18 items 1/3).

---

## 24. MODEL INSTALLATION PIPELINES

Two pipelines exist (H1 §3). Frozen ownership: **Workflows → Model Library/custom-node dependencies is the modern product owner.** Future implementation distinction:
- model install request driven by Workflow dependency resolution → **KEEP in Workflows**;
- legacy raw/batch model download tooling → evaluate each operation; do NOT automatically duplicate into Backend;
- deployment bootstrap/remote image preparation → **Backend if operational**.

No new duplicate model-installer authority (reinforces §10.1).

---

## 25. IMPLEMENTATION WAVES — FROZEN ORDER AND DEPENDENCIES

### H-WAVE A — ADDITIVE RE-HOME (no removals required to pass)
Goal: make modern surfaces complete before removing legacy UI. Parallel-safe sublanes:
- **A1** Backend workspace/account controls (workspace CRUD/select/swap/truthful identity; registry export/import).
- **A2** Backend deployment/runtime/credential controls (deploy/redeploy/status/log/warmup-if-legitimate/repair-if-non-obsolete; auth/HF token; manifest-repair verdict).
- **A3** Workflows Model Library parity for still-needed legacy Models/Sync actions (parity audit decides retire-vs-rehome per §10.1/§24).
- **A4** modern experiment-v2 fallback closure where independent (Playground legacy-experiment fallback removal — step 1 of §14, only where it does not depend on D-lane hydration work).

### H-WAVE B — SAFE DEAD SURFACE RETIREMENT + REDIRECTS
Includes: orphaned `studio-history.js` (+ helper relocation + its structural-test pruning); hidden sidebar registrations; dead `is_v2`/`is_shadow`; Legacy Dashboard/History tabs; redirect old openers (§22); remove legacy funnels in modern copy. Do NOT yet delete live compatibility routes/stores.

### H-WAVE C — EXECUTION CONSOLIDATION (after Comparison/shadow blockers are resolved by this contract + Wave E sequencing rule below)
- V1 public retirement (selector(s), `/config` v1 acceptance, `AVAILABLE_EXECUTION_MODES`);
- persisted v1→v2 migration (§12) + migration tests;
- shadow public/runtime retirement per §6 (env vocabulary collapse lands WITH branch deletion);
- remove modern Run mode (§4; key leaves reset sets same change);
- remove Execution Engine selector;
- remove V1 branches — EXCEPT the legacy executor path still referenced by the Comparison runner (see sequencing rule);
- Reset All cleanup (§11);
- ensure every new modern generation is V2.

**C/E sequencing rule (dependency-safe, resolves the C-before-E tension):** the Comparison Runner executes via the V1 `run_prompt_stream` path. Therefore Wave C's "remove V1 branches" EXCLUDES that path; it retires in Wave E together with Comparison UI retirement (or in a merged C/E sublane when file ownership permits — merging allowed, dependency violation never). After Wave E, residual V1 executor code is dead and is removed in Wave G.

### H-WAVE D — LEGACY EXPERIMENT / RECENT-RUN CONSUMER MIGRATION
- Playground recent-runs → History V2 (§23);
- eliminate legacy experiment creation fallback (§14 steps 1–2 remainder);
- remove modern consumers of legacy experiment/run-history feeds;
- retire legacy experiment creator UI (§14 step 4);
- freeze old data readers (§14 step 5).

### H-WAVE E — LEGACY SETTINGS / COMPARISON UI RETIREMENT (once re-homes + redirects verified)
- remove Settings Legacy group (exit-sequence step C);
- remove standalone legacy overlay (step D);
- retire Comparison UI/context-menu/runner (§7) + the V1 executor path per sequencing rule;
- keep readers/data hidden where required;
- remove dual overlay design-system conflict.

### H-WAVE F — COMPATIBILITY/API WRITE FREEZE (only when all modern consumers have moved)
- old routes become read-only shims;
- stop new writes to legacy stores (`.studio_backends.json` writes stop; legacy experiment/preset writes stop);
- replace misnamed `/studio/backends` modern consumers with truthfully named seam, then demote to hidden read-only shim (§19);
- declare inert archives.

### H-WAVE G — DEAD CODE / TEST CONSOLIDATION
- delete unreachable legacy modules (`testing-*` remnants, `modal-comparison.js` UI layer, legacy overlay builders, retired V1 executor residue);
- prune structural source-string tests of retired surfaces;
- register missing meaningful compatibility tests (incl. §27 test-fate execution);
- keep the deterministic gate green.

**Rules:** each wave strictly shrinks the next wave's consumer set; no wave requires destructive data migration; do not collapse into one giant patch; some Wave-B/E pieces may merge if file ownership permits, but NEVER violate dependencies (notably: A before E for re-homed controls; D before legacy-feed GET retirement; E's Comparison retirement before/at V1-branch deletion).

---

## 26. FILE OWNERSHIP PLAN (future independent writer lanes)

Rule: **avoid assigning the same production file to concurrent writers.** Shared files (`__init__.py`, `studio-backend-api.js`, `studio-output-preferences.js`, `web/studio-shell.js`) are REGION-SCOPED: a lane owns a named function/section region, additive-only elsewhere, and two lanes never hold the same file concurrently — sequential landing or explicit merge order.

| Lane | Owned files/regions | Scope |
|---|---|---|
| **L-BE1 Backend UI** | `web/studio-backend.js`, `web/studio-backend-presets.js`, `web/studio-backend-snapshots.js`, `web/studio-backend-capture.js`, new backend panel modules | Waves A1/A2 UI; truthful-named seam consumption in F |
| **L-BE2 Backend routes/services** | `modal_workspaces.py`; `__init__.py` regions: workspaces/deploy/auth/manifest/warmup route families | A1/A2 server side; `/config` execution_mode region coordinates with L-EXE sequentially |
| **L-WF Model Library** | `web/studio-model-library.js`, `web/studio-workflows.js` Models/Dependencies regions; `model_library_routes.py` | A3 parity; legacy Models/Sync retirement verdicts |
| **L-SET Settings** | `web/studio-settings.js` (General/Generation/Advanced regions); reset-set hygiene | Wave C S1/S2 removal; Advanced readout removal (E) |
| **L-EXE Execution runtime** | `execution_runtime.py`, `studio_run_adapter.py` (mode/invoker regions), `studio_workflow_run.py` (legacy run + :1556 remnant), `experiment_runner.py` (LocalRemoteInvoker), `__init__.py` canvas-v1 + `/config` mode regions | Wave C; env-vocabulary collapse |
| **L-PG Playground** | `web/studio-playground.js` (recent-runs/filmstrip/hydration regions), `web/studio-playground-state.js` | Wave D hydration migration |
| **L-EXP Experiment mode** | `web/studio-experiment-mode.js` (fallback closure), `experiment_modern_*` (read-only coordination) | A4/D |
| **L-DEAD Dead frontend** | `web/studio-history.js` (delete), `web/testing-dashboard.js`, `web/testing-history.js`, hidden-registration blocks of `modal-settings.js`/`modal-comparison.js`, `web/modal-testing.js` auto-open/alias-map regions | Wave B; redirects |
| **L-CMP Comparison** | `web/modal-comparison.js` (UI layer), `web/testing-profiles.js`, `web/testing-setup.js` (comparison parts), `web/testing-results.js`, `web/testing-ab-slider.js`, `web/studio-legacy.js` loader | Wave E retirement; backend `/comparison/*` read-only freeze coords with L-FRZ |
| **L-OVL Legacy overlay** | `web/modal-settings.js` (panel body), `web/testing-settings.js` | Wave E (after A-gate); merges with L-DEAD registration removal if ownership permits — otherwise sequential |
| **L-FRZ Route/write freeze** | `run_history.py`, `experiment_service.py` route regions, `studio_routes.py` backends family, `__init__.py` legacy-route tagging, fake-backend mirrors | Wave F |
| **L-TST Tests** | `tests/run_studio_tests.py` (registrations), structural `test_testing_*.py`, `test_testing_shell_integration.py` split, `studio_legacy_settings_authority_unit.mjs` fate (§27), new migration/compat tests | Wave G (+ per-wave registration additions) |

Conflict notes: `__init__.py` is touched by L-BE2, L-EXE, L-FRZ — region-scoped, never concurrent. `modal-settings.js` touched by L-DEAD (registrations) and L-OVL (panel) — merge into one lane OR strict sequencing (registrations first). `studio-backend-api.js` is shared modern infra — additive methods only, coordinated.

---

## 27. TEST GATE / BASELINE

Authoritative pre-H implementation baseline (inherited from G closure; H5 ran no tests and modified nothing):

```
python tests/run_studio_tests.py --fake
Python lane:        1991 / 1991
Node unit lane:     21 / 21 files
Fake Playwright:    192 / 192
```

**Unregistered-test decision (H1 finding):** `tests/studio_legacy_settings_authority_unit.mjs` exists but is NOT registered in the Node gate (verified absent from `tests/run_studio_tests.py` registration today).

**Fate: MIGRATE-THEN-REGISTER (executed in Wave G; no test edits in H5).** The test protects F4B server-authority invariants that OUTLIVE the legacy panel: server-first precedence through the shared helper, no write-on-open, single explicit-change POST site. Those assertions migrate into the registered modern authority lane (extension of `studio_phase_f4_settings_authority_unit.mjs` or a new registered file); legacy-panel-DOM-specific assertions die with the panel in Wave E. A meaningful authority test must not remain silently outside the gate; blind registration of soon-dead DOM assertions is rejected.

Related registry debts carried into Wave G (H1 §9): `test_run_history*.py` and comparison backend tests are outside `STUDIO_PY_MODULES` — register the ones protecting surviving compatibility, explicitly declare the rest out-of-gate; `test_testing_shell_integration.py` splits (shell parts KEEP, `studio-history.js` parts pruned with L11).

---

## 28. MUST-PRESERVE PHASE-H INVARIANTS (FROZEN LIST)

Violating any of these is a regression even where no test catches it directly.

1. Top nav remains five surfaces (Playground/History/Workflows/Backend/Settings); no new top-level tabs.
2. Modern Studio execution = Modal V2, single-engine.
3. Portability targets are advisory analysis, never execution engines.
4. WorkflowVersion remains immutable (write-once); Mapping insert-once.
5. History replay authority remains `RequestSnapshot.execution_plan_json`.
6. No live domain lookup is added to History render or replay (§16).
7. Legacy irreproducible rows remain honestly irreproducible (`replay_capable=false` truthfulness; no reconstruction ever).
8. No destructive historical-data migration (`.run_history`, `.experiments`, `.presets`, `.studio_snapshots.json`, `.studio_presets.json`, `history_v2.db`, comparison stores).
9. Workspace fallback for old snapshots retained until pre-workspace-id snapshots no longer exist in user data.
10. Settings owns preferences only.
11. Backend owns operational Modal state (workspace/deploy/runtime/credentials).
12. Workflows owns Model Library/dependencies/portability.
13. History V2 remains sole durable History.
14. Modern Experiments = Playground (compose/run/live) + History (records/actions); no third surface.
15. Comparison execution UI retires rather than being ported forward; no modern Comparison domain; no slot-path mutation.
16. Legacy canvas remains compatibility-only during H (interception, pass-through, output chain, production marking).
17. Old data readers may outlive old UI.
18. UI retirement does not imply store deletion.
19. No new legacy writes after their creator authority retires.
20. Model Compatibility ≠ Portability (distinct vocabularies/endpoints; `compatible_models` untouched on Versions).
21. Portability cache remains derived/non-gating/TTL-free.
22. GPU remains server-authoritative and frozen per plan (F8 chain unchanged; replay/resume/retry never reread it).
23. Replay/resume/retry never reread current Settings.
24. New modern runs eventually become V2-only (post Wave C).
25. A/B slider is Phase-I and is never justification to retain Comparison.
26. `.studio_presets.json` remains live until its Playground consumer is explicitly migrated (§15B/§18).

Plus inherited G §37 / F §7 invariants remain binding (manifest exactness, import atomicity, environment isolation, UNKNOWN-never-LOW, append-only attempts, managed-asset semantics, etc.).

---

## 29. PHASE-I DEFERRALS (OUT OF H — FROZEN BOUNDARY)

- A/B two-image slider (History/Experiment result space);
- `aria-current` nav polish / nav keyboard semantics;
- responsive nav redesign;
- heading hierarchy cleanup;
- generic loading component;
- chip visual taxonomy (incl. portability-vs-compatibility chip distinction);
- wording/verb polish ("Make Preset"/"New Preset"/label normalization; Settings info-row copy);
- URL/deep-link routing infrastructure;
- general focus-visible polish;
- cross-tab state sync;
- specific-entry model/custom-node deep links beyond already-landed basic behavior.

Phase H solves STRUCTURAL duplication, not final polish.

---

## 30. AUTHORITATIVE INPUT INDEX

- Handoffs: `PHASE_F_FINAL_CLOSURE_ZERO_CONTEXT_HANDOFF_2026-08-23.md`, `PHASE_G_FINAL_CLOSURE_ZERO_CONTEXT_HANDOFF_2026-08-23.md` (§37/§38 invariants inherited)
- Audits reconciled: `PHASE_H1_LEGACY_V1_RETIREMENT_AUDIT_2026-08-23.md`, `PHASE_H2_RUN_MODE_SETTINGS_AUTHORITY_AUDIT_2026-08-23.md`, `PHASE_H3_REFERENCE_INTEGRITY_HISTORICAL_COMPATIBILITY_AUDIT_2026-08-23.md`, `PHASE_H4_STUDIO_NAVIGATION_SURFACE_OWNERSHIP_AUDIT_2026-08-23.md`
- H5 spot-verifications: `execution_runtime.py` (aliases/env lock), `studio_workflow_run.py:1556`, `tests/run_studio_tests.py` (registration absence), `__init__.py:7330`

---

## FINAL VERDICT

`PHASE H5 COMPLETE — CONSOLIDATION CONTRACT FROZEN.`

Deploy / live / GPU / generation / commit / push by this batch: **NONE**.

---

# H5 FOLLOW-UP A — POST-WAVE-A1/A2/A3 CONTRACT ERRATA (APPENDED 2026-08-24)

**Batch type:** H5 contract follow-up / reconciliation only (same-batch H5 follow-up, per the "deviations require a new freeze batch" rule). READ-ONLY against production code and tests; no deploy, no Modal/GPU/live generation, no commit/push/branch/worktree/reset. Files modified: **this appendix** + `PHASE_H5A_WAVE_A_OPERATIONAL_RECONCILIATION_2026-08-24.md` (evidence detail; this appendix is authoritative).
**Trigger:** H6 (Backend re-home, Wave A1+A2) and H7 (Model Library parity, Wave A3) landed concurrently and produced post-freeze implementation evidence requiring reconciliation before Wave B. H8 remains outstanding.
**Supersession rule:** historical sections above remain readable and unmodified; the rows named below are explicitly superseded BY THIS APPENDIX ONLY.

## FA-1. WORKSPACE-REGISTRY EXPORT/IMPORT — CORRECTION (supersedes §10.2 row "Workspace registry export/import" and §25 A1 parenthetical)

Post-freeze verification (H6 finding, re-verified against source by this lane): **no legacy user-facing Workspace REGISTRY export/import operation exists, and no server route exports/imports `.modal_workspaces.json` as a registry.** The legacy buttons previously interpretable that way (`modal-settings.js:2084/2089`) are "Export Workflow Manifest"/"Import Workflow Manifest" calling `/workflow-manifest/export|import` — MODEL deployment-manifest portability operations (modernized as H7 F2/F3), a different concept. The workspace route family is exactly list/create/active/swap/swap-status (`__init__.py:4380–4524`); `modal_workspaces.py` has no export/import function.

**FROZEN:** `WORKSPACE_REGISTRY_EXPORT_IMPORT = NOT_AN_EXISTING_PRODUCT_CAPABILITY`

Consequences (binding): REMOVED from the Backend parity prerequisite; REMOVED from the legacy-panel exit-blocker list (dissolves H6 report §13 blocker #1); DO NOT create a route; DO NOT add browser-side JSON export/import; absence is NOT missing parity. If ever desired, it is NEW PRODUCT SCOPE, never Phase-H migration debt.

## FA-2. FINAL POST-WAVE-A LEDGER — H7 BACKEND_OPERATIONAL HANDOFF (supersedes the open handoff state in H7 §6 and H6 §13 blocker #2's unresolved portion)

H7's concurrent-time statement "the ten BACKEND_OPERATIONAL actions still have no modern home" was accurate at that lane's observation point and is hereby superseded by the converged H6/H7 reconciliation. Count note: the enumeration is ELEVEN conceptual operations (H7's prose said ten; its S1 row carries a split classification that made the count drift). Full evidence table: `PHASE_H5A_WAVE_A_OPERATIONAL_RECONCILIATION_2026-08-24.md` §2.

| # | Operation | Route(s) | FINAL CLASS | Modern replacement | Blocks legacy Settings retirement |
|---|---|---|---|---|---|
| M1 | Remote-volume inventory browse | `GET /comfymodal/models` | **RETIRE** (UI) | Model Library (`/studio/models`) + contextual swap plan; NO second browser (duplicate-authority ban intact) | NO |
| M2 | Create local placeholder | `POST /models/inject` | **RETIRE** (UI) | None user-facing; automatic/internal placeholder consumption by the canvas compatibility layer continues unaffected | NO |
| M3 | Create All Placeholders | `POST /models/inject-all` | **RETIRE** (UI) | Same as M2 | NO |
| M4 | Delete model from remote volume | `DELETE /models/{folder}/{filename}` | **RETIRE** (UI) | Workspace Swap review ("to_remove"); swap job calls `delete_model()` internally — function retained, route untouched compatibility | NO |
| F1 | Manifest repair | `POST /manifest/repair/*` | **MODERN_BACKEND** | Backend → Workspaces → bounded repair panel (swap hard-depends on `repair_required`, `__init__.py:4445–4503`) | NO |
| F4 | Install from manifest | `POST /manifest/install` | **RETIRE** (standalone UI) | Workspace Swap performs the install phase internally (Phase 3 `download_model_stream` over selected models); no raw second installer exposed | NO |
| S1 | Upload/sync-status comparison | `GET /sync/status` | **RETIRE** (upload-compare UI; installed-truth already MODERN_WORKFLOWS) | Model Library presence + custom-node registry; swap computes availability server-side | NO |
| S2 | Sync models (bulk upload) | `POST /sync/models` | **RETIRE** (standalone UI) | Workspace Swap (user-selected transfer with progress/summary); route untouched while legacy lives | NO |
| S3 | Sync custom nodes | `POST /sync/custom-nodes` | **RETIRE** (standalone UI) | Swap Phase 4 packages/uploads/redeploys/resyncs internally; Workflows owns install-request truth | NO |
| S4 | Runtime resync | `POST /runtime/resync` | **RETIRE** (standalone UI) | Redeploy and Restart (re-homed) + swap auto-resync (`resync_runtime("custom_nodes")` internal call retained) | NO |
| S5 | Runtime state/staleness | `GET /runtime/state` | **MODERN_BACKEND** | Backend Overview/readiness rows + deploy-status truth (incl. honest `deployed_unwarmed`); raw route stays server-side untouched, unconsumed; no duplicate Sync-section panel | NO |

**Tally: MODERN_BACKEND 2 · RETIRE 9 · MODERN_WORKFLOWS 0 · COMPATIBILITY_ONLY 0 · STILL_BLOCKED 0.**
No route is deleted or modified by this erratum (H5 §18: UI retirement does not imply route deletion); routes become Wave-F/G review candidates with the retiring legacy panel.

## FA-3. WARMUP ACCEPTANCE (resolves §10.2 conditional row)

H6's `WARMUP = RETIRE` is ACCEPTED as the authoritative post-Wave-A verdict. Evidence verified: warmup RUN executes through the V1-bound path (`__init__.py:7693–7779`); sole consumer-gate is the legacy aggregate-experiment scheduler (`gate_experiment_on_stored_generation`, :6100–6115, retiring per §14/R1); the legacy panel exposes NO warmup control (zero `deploy-warmup` references in `modal-settings.js`); V2 does not depend on it; `deployed_unwarmed` remains truthful state reporting displayed verbatim in modern Backend. Warmup work is not reopened.

## FA-4. AUTH / CREDENTIAL CLARIFICATION (confirms H6 COMPATIBILITY_ONLY)

Legacy global Change API Key (`buildAuthPanel` → `POST /auth/setup`) writes global `modal.toml` + upserts a "Primary" workspace + triggers a background deploy — a first-run bootstrap superseded by workspace-scoped credentials (Workspaces add/edit), Credentials connection truth, and HF/Civitai controls (all re-homed by H6). **FROZEN: legacy `/auth/setup` UI is NOT required parity for modern Backend and does not block legacy-panel exit. Its compatibility route is not deleted yet.**

## FA-5. REVISED LEGACY MODELS/SYNC EXIT-BLOCKER LEDGER

**NONE remain from the Models/Sync set.** Every live purpose is re-homed (F1, S5), superseded by the canonical Workspace Swap job (F4, S2, S3, S4, M4 removal path), owned by Workflows (M1 library truth, S1 installed-truth), or retired as obsolete UI (M2, M3). Do not manufacture blockers. Remaining whole-panel exit items OUTSIDE Models/Sync are unchanged: H4 item 10 (experiment Setup draft shim + feature-registry copy rewrite — A4/D lanes), item 11 (Comparison Profiles compatibility surface — Wave E per R1), redirects/removals (Waves B/E).

## FA-6. TEST-REGISTRATION DEBT (confirmed)

`tests/studio_backend_operations_unit.mjs` (H6) and `tests/studio_model_library_parity_unit.mjs` (H7) both exist and remain intentionally UNREGISTERED in `tests/run_studio_tests.py` (verified this lane). Both are Wave-G L-TST MIGRATE/REGISTER candidates per §27. The runner was not edited.

## FA-7. FULL-GATE STATUS

H6/H7 focused evidence = GREEN (per their reports; attribution of transient shared-tree failures to H8-owned Experiment files verified plausible — all flagged failures target `web/studio-experiment-mode.js` and experiment fake specs). Shared-tree final gate = **DEFERRED until H8 settles** (§26 condition). Not rerun by this follow-up.

## FA-8. WAVE-B ENTRY GATE

```
H5A_BACKEND_REHOME_READY       = YES
H5A_MODEL_LIBRARY_PARITY_READY = YES
H5A_EXPERIMENT_A4_PENDING      = YES
H5A_WAVE_B_GLOBAL_READY        = NO_PENDING_H8
```

This records the H6/H7 portion of the Wave-A prerequisite only; the global Wave-B gate awaits H8 settlement and the deferred shared-tree gate.

Deploy / live / GPU / generation / commit / push by this follow-up: **NONE**.

---

# H5 FOLLOW-UP B — POST-WAVE-B CONVERGENCE (APPENDED 2026-08-24)

**Batch type:** H5 contract follow-up / same-batch Wave-B reconciliation. No deploy, no Modal/GPU/live generation, no commit/push/branch/worktree/reset. The working tree was intentionally dirty (H9/H10/H11 all landed uncommitted in the shared tree). Files modified by this batch: **this appendix** + `PHASE_H5B_WAVE_B_CONVERGENCE_2026-08-24.md` (evidence detail; this appendix is authoritative). Zero production or test files modified.
**Trigger:** H9/H10/H11 landed concurrently and reported mutually inconsistent full-gate counts (1941 vs 1974-red vs 1991). This batch measured the converged tree directly and freezes ONE authoritative post-Wave-B truth before Wave C/D.

## FB-1. AUTHORITATIVE POST-WAVE-B SHARED-TREE GATE (measured by this batch, sole baseline going forward)

```
python tests/run_studio_tests.py --fake
  python             run=1941  fail=0    error=0    skip=0
  node-unit          run=21    fail=0    error=0    skip=0
  fake-playwright    PASS      (npm wrapper aggregate run=1)
```

Exact fake Playwright test count (obtained by running `npx playwright test --config=playwright.fake.config.mjs` once, since the wrapper does not expose counts): **199 passed / 199** — unchanged from the pre-B fake count of 199 (contract §27's historical "192" predates late-Phase-G additions; the operative pre-B figure was 199). Suite collection independently re-derived: `build_python_suite().countTestCases() == 1941`. This 1941/21/199 triple supersedes every prior number (1991, 1974, 192) as the Wave-C entry baseline.

## FB-2. 1941-VS-1991 RECONCILIATION (numerical ledger)

| Item | Δ | Evidence |
|---|---|---|
| Pre-Wave-B frozen baseline | 1991 | §27; re-observed by H11 |
| H9 retired in-gate assertions | −74 | itemized: timing −10, backend −15, shell-integration −24 net, ui-wired −25 net; verified still absent this batch (zero obsolete classes/assertions resurrected) |
| H10 net in-gate additions | +24 | H11 added ZERO tests (its entire diff = `execution_runtime.py` −12 lines), so the residual is H10's: 11 new `LegacyEntrypointRedirectTests` + rewritten guard/routing classes now totalling 23 tests in shell integration + net routing-pin updates; per-file pre-B split of the rewritten classes is unrecoverable post-hoc (no Wave-B commits exist), but the aggregate reconciles exactly |
| Accidental resurrection | 0 | sweep proves no retired file/test surface returned |
| **Current authoritative total** | **1941** | direct collection + green gate |

Per-file confirmation against H9's post-edit focused counts: timing 54, backend 283, shell 200, ui-wired 170 — all four match the current tree exactly.

**H11's 1991 explained:** temporally stale measurement, not resurrection and not wrapper cache. The runner builds its suite fresh from the explicit `STUDIO_PY_MODULES` allowlist on every invocation (no discovery cache); the only explanation consistent with a clean 1991 is that H11's gate ran BEFORE H9's production deletions and test prunings were on disk (with H9's deletions present, the then-current structural tests reading the deleted modules would have failed and the count would have dropped). H11's own change (`execution_runtime.py` −12) cannot move any count. H10's mid-flight 1974+29f+8e was likewise a partial-landing snapshot (net −17 at that moment); every red it saw targeted not-yet-landed/concurrent H9 deletions or the pre-existing out-of-gate pins (FB-5).

## FB-3. WAVE-B COMPLETION LEDGER (frozen)

| Requirement | Status |
|---|---|
| Orphaned History V1 frontend (`web/studio-history.js`) retired | COMPLETE |
| Hidden legacy sidebar registrations removed (zero `__comfyModalEnableLegacySidebarTabs` consumers; single `registerSidebarTab` site remains in `modal-testing.js`) | COMPLETE |
| Dead execution helpers `is_v2`/`is_shadow` retired (resolver untouched; V1/shadow behavior live until Wave C) | COMPLETE |
| Legacy Dashboard tab (`testing-dashboard.js`) retired | COMPLETE |
| Legacy History tab (`testing-history.js`) retired | COMPLETE |
| Old opener redirects (dashboard→Backend, setup→Playground+Experiment context, profiles→Playground+deprecation, results/history→History V2, settings→Settings; zero `activeLegacyTab` writes in `modal-testing.js`) | COMPLETE |
| Modern Legacy Setup funnel copy rewritten (feature-registry + playground notes; `navigateToLegacySetup` removed) | COMPLETE |

**Wave B = COMPLETE (all seven requirements).**

## FB-4. CONVERGED-TREE COEXISTENCE PROOFS (verified this batch)

1. **Retired files stay deleted:** `web/studio-history.js`, `web/testing-dashboard.js`, `web/testing-history.js` absent; no importer, no resurrected pinning test (all remaining test references are negative assertions/comments).
2. **Loader/alias coexistence (H9∩H10):** `studio-legacy.js LEGACY_MODULES` = setup/profiles/results/settings only (unknown tabs fail closed) AND `modal-testing.js ALIAS_PAGE_MAP` retains dashboard/setup/profiles/results/history/settings → modern owners. Legacy MODULE loader entries and external COMPATIBILITY aliases are distinct concepts; both hold simultaneously. `TAB_MODULES` reduced to the four surviving tabs; no `TAB_DASHBOARD`/`TAB_HISTORY`.
3. **Settings Legacy group integrity:** exactly Legacy Setup/Profiles/Results/Settings (+ temporary "Open Legacy Settings" opener). Dashboard/History entries gone; group itself retained for Wave E.
4. **Comparison intact for Wave E:** builders/mounts/overlay globals/canvas `_initContextMenu` in `modal-comparison.js`; full `/comfymodal/comparison/*` route family registered; stored-data compatibility untouched. Only hidden sidebar registrations were removed.
5. **Legacy overlay compat:** `window.open_comfymodal_settings` defined (`modal-settings.js:4155`), consumed only inside the Wave-E legacy surface (`testing-settings.js`); modern sidebar no longer routes to it.
6. **History compatibility freeze intact:** `GET /comfymodal/run-history` (+detail/logs/timing), annotations PATCH, save, `GET /comfymodal/history`, `/comfymodal/experiments` family, `.run_history` readers, `legacy_mapping` + `LegacyMigrationSeam`, replay-capability projection, `_resolve_replay_workspace`/`_resolve_workspace_dict` fallback — all present; no destructive migration.
7. **H8 invariant intact:** `experimentRunSurface()` offers no new legacy creator (legacy = view/control compat for already-active runs only); missing Workflow/Version/identity fails closed; valid new experiments use `POST /studio/experiment-v2`.
8. **Wave A preserved:** H6 Backend operational modules all present (`studio-backend-{workspaces,deployment,credentials,runtime,presets,snapshots,capture}.js`); H7 Model Library parity module + unit green. Shared-file merges did not clobber Wave A.
9. **No narrow merge repair was required:** zero Wave-B integration defects found; no production/test edits made by this batch.

## FB-5. OUT-OF-GATE FAILURE CLASSIFICATION (all Wave-B writers finished)

| Failure | Class | Basis |
|---|---|---|
| `test_task3_progress_annotations.py` tracker-membership ×5 (`SharedProgressConsumedByPlaygroundTests` ×4, `PlaygroundUsesScopedTrackerTests::test_imports_create_scoped_tracker`) | **B — PRE-EXISTING, unrelated to Wave B** | `git diff HEAD -- web/studio-playground.js` contains ONLY H10's copy edits; HEAD (2026-08-22, pre-H) already lacks every asserted symbol. Scoped-tracker wiring legitimately lives in `studio-experiment-mode.js` (`createScopedTracker`) with lifecycle refs in `studio-playground.js` state. Re-point assertions at current owners in Wave G L-TST. |
| `test_modal_workspace_ui_ast.py::test_production_summary_labels` | **B — PRE-EXISTING stale copy pin** | "Production plan" exists neither in HEAD nor anywhere in current `web/`; the feature row ("Sampler previews: disabled") still exists. Wave G prune/re-point candidate; do NOT patch production copy to satisfy it. |
| `test_modal_workspace_ui_ast.py::test_output_save_folder_defaults_are_normalized` | **D — from another completed phase change requiring reconciliation** | The F4A-era output-preferences consolidation (uncommitted pre-B work) moved `DEFAULT_OUTPUT_SAVEFOLDER` into the shared `studio-output-preferences.js`; `modal-settings.js` now imports it, so the literal `"output/modal"` legitimately no longer appears there. Invariant still honored via the shared authority. Test-side re-point belongs to that owner's reconciliation / Wave G; not an H9/H10/H11 regression. |

Class A count: **0** — no H9/H10/H11 edit broke any still-required invariant.

## FB-6. NEXT-WAVE DEPENDENCY ORDER (determination only; no implementation authorized)

**Conclusion: (C) Wave C and Wave D can safely run in parallel**, under the conditions below. Both are currently unblocked: C's Comparison/shadow blockers were dissolved by the frozen C/E sequencing rule (§25), and D's prerequisite (A4 fallback closure) is complete per H8.

Ownership conflict map:
- **Wave C files:** `execution_runtime.py`, `studio_run_adapter.py`, `studio_workflow_run.py` (incl. :1556 remnant with surrounding branch), `experiment_runner.py`, `__init__.py` canvas-v1 + `/config` + `AVAILABLE_EXECUTION_MODES` regions, `web/studio-settings.js` (Run-mode row, engine selector, reset set), persisted v1→v2 migration + tests.
- **Wave D files:** `web/studio-playground.js` (recent-runs/filmstrip/hydration regions), `web/studio-playground-state.js`, `web/studio-experiment-mode.js` (fallback remainder), legacy Experiment creator UI retirement in `testing-setup.js`/`testing-results.js`, fake-backend mirror updates.
- Production file sets are disjoint. Conditions: (1) `__init__.py` stays single-writer — D must remain consumer/UI-side; if any reader-freeze substep needs server edits, that substep sequences after C's `__init__.py` regions close; (2) `tests/run_studio_tests.py` registration edits are coordinated sequentially; (3) D's creator retirement shares `testing-setup.js`/`testing-results.js` with Wave E's Comparison parts (§26 L-CMP) — region-split or sequence that substep against E.

## FB-7. NEW AUTHORITATIVE BASELINE

```
POST-WAVE-B BASELINE (2026-08-24): Python 1941 · Node-unit 21 files · Fake Playwright 199
Supersedes: 1991 (pre-H / §27), 1974 (H10 mid-flight), 1941-as-unexplained (H9), 1991 (H11 stale)
```

Deploy / live / GPU / generation / commit / push by this follow-up: **NONE**.

---

# H5 FOLLOW-UP C — POST-WAVES-C/D CONVERGENCE & WAVE-E ENTRY FREEZE (APPENDED 2026-08-24)

**Batch type:** H5 contract follow-up / same-batch Waves-C/D reconciliation. READ-ONLY against production code and tests. No deploy, no Modal/GPU/live generation, no commit/push/branch/worktree/reset. Files modified by this batch: **this appendix** + `PHASE_H5C_WAVES_CD_CONVERGENCE_WAVE_E_FREEZE_2026-08-24.md` (evidence detail; this appendix is authoritative). Zero production or test files modified.
**Trigger:** H12 (Wave C) and H13 (Wave D) landed concurrently in the shared dirty tree and both reported green gates (1945/21/211). Before Wave E retires the Settings Legacy group, standalone overlay, Comparison UI, canvas Comparison menu, and Comparison execution path, ONE authoritative interpretation of the remaining route/executor seams is frozen — specifically so that Wave E cannot delete the live Single-run poll/cancel seams merely because their URLs contain `/experiments`, and cannot blur warmup into Comparison.

## FC-1. AUTHORITATIVE POST-WAVES-C/D GATE (measured by this batch, sole baseline going forward)

```
python tests/run_studio_tests.py --fake
  python             run=1945  fail=0    error=0    skip=0
  node-unit          run=21    fail=0    error=0    skip=0
  fake-playwright    PASS      (npm wrapper aggregate run=1)
npx playwright test --config=playwright.fake.config.mjs --reporter=line
  211 passed / 211
```

```
POST-WAVES-C/D BASELINE (2026-08-24): Python 1945 · Node-unit 21 files · Fake Playwright 211
Supersedes FB-7 (1941/21/199) as the Wave-E entry baseline.
Delta vs post-B: +4 Python / +12 fake = exactly H12 §14 + H13 §10 accounts; no unexplained drift.
```

C+D coexistence verified in the current tree (H12 markers: `AVAILABLE_EXECUTION_MODES` gone, `EXECUTION_MODE_RETIRED` guards, V2ExperimentInvoker-only scheduler, unconditional `_workflow_v2_run`, engine selectors gone, Reset `{gpu}`-only, legacy overlay non-interactive engine status, `/comparison/run`→`run_prompt_stream` intact; H13 markers: recent-runs = History-V2 `listFeed` only, zero legacy-feed hydration, `loadExperimentIntoPlayground` deleted, `experimentRunSurface()` unconditionally `"modern"`, creator/control retirement notices with zero POSTs from testing-results, Comparison-owned regions byte-intact). **Conflict found: NONE.**

## FC-2. "V2-ONLY EXECUTION" — SEMANTIC FREEZE (two axes, never conflate)

1. **EXECUTION ENGINE:** new model execution is Modal V2 only (acceptance → immutable ExecutionPlan → `execute_plan` → `ModalTransport`). No request can newly select v1/legacy/shadow. Comparison is the one temporarily-grandfathered direct execution seam until Wave E.
2. **ORCHESTRATION / STATUS STORAGE:** a route named `/experiments/{id}` is NOT a V1 execution engine. It is a scheduler/status-snapshot + cancellation-signalling transport over the legacy experiment-service REGISTRY (`.experiments/` store). It executes nothing. Future agents MUST NOT delete these routes because of their URL family.
3. **TRANSPORT ≠ EXECUTOR:** `modal_client.run_prompt_stream` remains the shared Modal streaming TRANSPORT for V2 (`execute_plan`→`ModalTransport`). What retires with Comparison/Warmup is the DIRECT UN-PLANNED invocation pattern. Never delete `modal_client.run_prompt_stream` as "the V1 executor"; never call its residual direct callers "a live V1 product path" after their product surfaces retire.

## FC-3. MODERN SINGLE RUN — TRACED CALL GRAPH AND SEAM CLASSIFICATION

Traced exactly (evidence: detail report §4): UI click → `POST /comfymodal/studio/run` (`__init__.py:7497`) → `handle_studio_run_async` (`studio_run_adapter.py:3848`; `direct=True` default, sole production caller passes no flag) → retired-mode guard → `playground_adapter_direct_run` → `PlaygroundService.execute` (`playground_service.py:744`: plan build :804, `_execute_plan`=V2 :830/:354–393, materialize, `_default_save_history` :404 → `.run_history` via `REGISTRY.history()` best-effort-mirrored into History V2 by `experiment_service.py:800–859`) → the HTTP response carries the COMPLETED result (`runId play_<hex>`, label-only `experimentId`, `direct_run:true`). Production NEVER returns a scheduler submission (`direct=False` has zero production callers).

Consequences (frozen facts): direct single runs write NO `.experiments/` scheduler state; `GET /experiments/{id}` (`__init__.py:6032`, reads `REGISTRY.store`) returns definition/snapshot/events for LEGACY aggregate experiments only and 404s for single-run ids; `stop-now` (`__init__.py:6491`) stops only a legacy aggregate-experiment SCHEDULER (or records a pending stop), never a V1 or V2 executor — for direct V2 runs it is a harmless 404 (in-flight cancellation of a synchronous direct run is not implemented server-side). History V2 is written independently of any of this.

| Seam | Classification | Rule |
|---|---|---|
| `GET /experiments/{id}` (single-run progress transport; wired via `_startPolling`→`getStudioRunStatus`, `studio-playground.js:88–197` + `studio-backend-api.js:156`) | **TRANSITIONAL_MODERN** | Wave E MUST NOT delete/disable/freeze. |
| `POST /experiments/{id}/stop-now` (single-run Cancel transport; `studio-playground.js:2838–2847` → `stopExperiment`) | **TRANSITIONAL_MODERN** | Wave E MUST NOT delete/disable/freeze. |

## FC-4. SINGLE ORCHESTRATION MIGRATION IS NOT PHASE-H BLOCKING

The Phase-H roadmap required hydration migration, creator/fallback closure, and renderer retirement — all DONE (H8/H13). Nothing requires replacing the Single progress/cancel transport because its route family is historically named `/experiments`. The Single path already has V2 execution + immutable plan + History-V2 durable record + one canonical UI; the route reuse is internal implementation reuse beneath one modern product path, not duplicate product authority.

**Classification: `LATER_INTERNAL_REFACTOR`.** Not REQUIRED_BEFORE_H_CLOSE; not a Wave-F blocker; do not invent a new scheduler for naming purity. Wave F must NOT freeze the two protected seams while they remain the Single path's wired transport.

## FC-5. `/experiments` ROUTE FAMILY — FINAL SPLIT (22 routes; per-route, never family-wide)

Frontend callers re-measured post-H13; no Python-internal HTTP callers exist (server consumes REGISTRY directly).

| Route | Frontend callers after H13 | Modern-live? | Legacy-UI-only? | Old-data read? | Zero-caller? | Wave E | Wave F | Wave G |
|---|---|---|---|---|---|---|---|---|
| GET `/experiments` | testing-results picker only | no | YES | yes | after E | — (consumer retires with group) | READ_ONLY_COMPAT | delete candidate |
| GET `/experiments/{id}` | **single-run poll (LIVE)** + testing-results reader + dead helper | **YES (poll seam)** | reader only | yes | — | **NONE — PROTECTED** | DO NOT freeze (INTERNAL_ONLY/MODERN_LIVE) | reader helpers die with tab; route stays |
| GET `/{id}/events` | testing-results only | no | YES | yes | after E | — | READ_ONLY_COMPAT | delete candidate |
| POST `/experiments/compile` | ZERO | no | — | no | YES now | — | ZERO_CALLER→inert | delete route+helper |
| POST `/experiments` (create) | ZERO | no | — | no | YES now | — | ZERO_CALLER→inert | delete route+helpers |
| POST `/{id}/start` | ZERO | no | — | no | YES now | — | ZERO_CALLER→inert | delete route+helpers |
| POST `/{id}/pause` · `/stop-after-current` · `/resume` · `/run-missing` · `/clone` | ZERO (controls removed H13) | no | — | no | YES now | — | ZERO_CALLER→inert | delete candidates |
| POST `/{id}/stop-now` | **single-run Cancel (LIVE)** | **YES (control seam)** | — | n/a | — | **NONE — PROTECTED** | DO NOT freeze (MODERN_LIVE) | stays |
| checkpoints continue/restart/restart-from/skip/unskip (+logs GET) | ZERO (logs GET = read compat) | no | YES | logs only | YES | — | writes inert; logs READ_ONLY_COMPAT | delete candidates |
| cells get/attempts GET · rerun POST · rerun-selected POST | ZERO | no | YES | gets only | YES | — | gets READ_ONLY_COMPAT; writes inert | delete candidates |
| (adjacent) POST `/studio/experiment` | ZERO (`runStudioExperiment` helper dead) | no | — | no | YES now | — | freeze | delete with helper |
| (adjacent) POST `/studio/experiment-v2` | modern D5 section | **YES** | — | — | — | keep | keep | keep |

## FC-6. WAVE-E ROUTE RULE (FROZEN)

Wave E is primarily **UI/product-surface retirement**. It may modify exactly one execution endpoint — `POST /comfymodal/comparison/run` — because leaving it executable would preserve a hidden direct V1 product execution seam. Wave E MUST NOT perform broad `/experiments*` route cleanup; legacy route/write freezing belongs to Wave F, except where disabling the hidden executable Comparison endpoint is necessary to complete the Wave-E product retirement. Deleting either protected Single seam in E violates this contract.

## FC-7. COMPARISON — EXACT WAVE-E DISPOSITION

Chain verified: `POST /comfymodal/comparison/run` (`__init__.py:5543`) → `_execute_comparison_profile` (:5222) → `run_prompt_stream` (:5306); sole web caller = Runner UI (`modal-comparison.js:1179`).

**FROZEN: `EXECUTION_RETIRE` via bounded truthful retired response** — endpoint ceases executing and returns a bounded JSON error naming the retirement (follow the `EXECUTION_MODE_RETIRED` precedent; implementer picks the exact 4xx verb consistent with existing conventions). Full route removal permitted ONLY with same-change `test_routes_registered` pin + fake-backend mirror updates (H3 §13 #11); the bounded-response form is preferred (smallest honest change, old clients get truth). `_execute_comparison_profile` → Wave G residue.

Per-route classification of all 17 `/comparison/*` routes: **READ_COMPAT** = profiles GET ×2, results GET ×2, workflow GET ×2, config GET, gallery GET, validate POST, detect-slots POST (non-persisting compute). **MUTATION_RETIRE** = profiles create/update/delete/duplicate, slots POST, config POST (actions land in Wave F; E removes the calling UI). **EXECUTION_RETIRE** = `/comparison/run` (Wave E). UNKNOWN = 0.

Stored data re-freeze: comparison profiles dirs, manifests/results, gallery assets untouched; no destructive migration; readers keep needed helpers; no writer preserved solely because a reader shares its file.

## FC-8. WARMUP DESTINATION (kept distinct from Comparison)

`run_prompt_stream` production caller census: (1) Comparison `_execute_comparison_profile` — product reachability ends at Wave E; (2) warmup route `__init__.py:7751` — RETIRE per FA-3; (3) `execute_modal_prompt` — dead post-H12 (test-consumed); (4) `LocalRemoteInvoker` — dead post-H12 (test-consumed); (5) `ModalTransport`/V2 — MODERN, KEEP.

**WARMUP → `WAVE_F`** (route/write-freeze review alongside the legacy-panel/experiment families) **with code deletion in `WAVE_G`. Explicitly NOT Wave E**: FA-3 deferred warmup to a later wave; warmup already has zero UI consumers so E gains nothing; the warmup region lives outside the Wave-E ownership lanes, and absorbing it would expand E's `__init__.py` blast radius beyond the frozen plan. Its last consumer-gate (`gate_experiment_on_stored_generation`, :6115–6132) belongs to the now-zero-caller legacy experiment start family (F freeze).

## FC-9. FOUR CONCEPTS THAT MUST NEVER BE MERGED (terminology freeze)

(1) product execution reachability — after E: zero V1-pattern product paths reachable from any user surface; (2) old executor code remaining on disk until G — existence ≠ reachability; (3) old routes remaining registered but retired/unreachable — registered ≠ executable product surface; (4) dead helper residue — deleted only in G with their tests. A surviving function definition after Wave E is NOT evidence that "Phase H failed to retire V1."

## FC-10. SETTINGS LEGACY GROUP — CONTENT AND PER-TAB WAVE-E FATES

Verified content (`studio-settings.js:590–632`): temporary "Open Legacy Settings" opener + exactly Setup/Profiles/Results/Settings via `renderLegacyView` → `studio-legacy.js` (LEGACY_MODULES = setup/profiles/results/settings; unknown tabs fail closed).

- **Setup** (creator-retired notice + Comparison profile CRUD residual + inert generationType/whatChanges/testValues form sections): **RETIRE/UNMOUNT whole tab** — after Comparison retirement nothing unique remains; inert forms are NOT ported; module file deletion Wave G.
- **Profiles** (Comparison Profiles editor): **RETIRE** — no modern replacement domain; disable mount/export/globals; stored readers/data survive; file unreachable until G.
- **Results** (read-only legacy Experiment display, ZERO POSTs + Comparison selection/A-B slider): **RETIRE from the Settings group** — History V2 is canonical and already projects migrated Singles + mirrored terminal Experiment cells (H13 §3); legacy records never mirrored stay accessible via hidden readers/data only (UI retirement ≠ data deletion; no entire Results UI is preserved merely because a hidden reader exists).
- **Settings** (embeds `mountSettingsPanel` + standalone launcher): **RETIRE** with the overlay (FC-11/FC-12).

A/B slider remains Phase-I (never ported as Comparison justification; invariant 25 stands).

## FC-11. STANDALONE OVERLAY + `open_comfymodal_settings` — FROZEN

No valid user-facing capability still requires `testing-settings.js`, `window.open_comfymodal_settings`, or the standalone overlay (workspace/deploy/credentials/manifest-repair → Backend H6; models → Workflows H7; run-mode/engine retired H12; obsolete ops retired FA-2; auth/setup not-required-parity FA-4). **Product blocker: NONE.** Wave E removes normal access + overlay UI and DELETES `window.open_comfymodal_settings` with the overlay — re-measured: its only callers are `testing-settings.js:90/109/173`, all inside the retiring surface; no redirect symbol needed (modern sidebar already routes modern). If an unexpected external consumer appears during E, prefer a bounded redirect to modern Settings over reopening retired UI.

## FC-12. MODAL-SETTINGS.JS SHARED-CODE SPLIT (region ownership for the Wave-E prompt)

- **A. Overlay/UI-only (E removes):** `open_comfymodal_settings` builder (:4107–4161); `mountSettingsPanel` exposure (:4095; sole external consumer is retiring testing-settings.js); panel-body operational sections that exist only inside `buildPanel()` (deploy banner/log/poll, models/sync lists, auth panel, workspace section, download-progress UI).
- **B. Canvas compatibility state/writers (E MUST preserve):** `window._comfyModalEnabled` semantics + persisted-key chain. The interactive toggle dies with the overlay, but canvas pass-through semantics (§8) require a bounded startup initialization reading the persisted `comfymodal_enabled` LS key into `window._comfyModalEnabled` so existing Local-mode users keep identical behavior (`modal-node.js:678/841` reads `!== false`; undefined defaults enabled).
- **C. Output-preference shared wiring (preserve):** `studio-output-preferences.js` imports/init; `syncLegacyOutputPrefsOnce` (:184).
- **D. Initialization required elsewhere (preserve, trimmed to B/C needs):** `syncLegacyGpuConfigOnce` (:176) read-only sync; extension registration/setup() hygiene (:4163–4199).
- **E. Dead residue (G deletes):** anything left unreachable after A's removal.

Do NOT delete `modal-settings.js` wholesale (§21 rule stands).

## FC-13. COMPARISON GLOBALS / CANVAS MENU — WAVE-E DELETION SET

Re-measured (all callers internal to `modal-comparison.js` + retiring legacy tabs): DELETE in E — `window.mountComparisonProfiles` (:1567), `window.mountComparisonRunner` (:1578), `window.openComparisonProfilesOverlay` (:1643), `window.openComparisonRunnerOverlay` (:1649), and the always-on Comparison slot context menu `_initContextMenu` (:1425, wraps `app.canvas.getNodeMenuOptions`). Canvas `/prompt` interception, Production mode, and all other canvas menu behavior remain untouched.

## FC-14. SETTINGS LEGACY GROUP REMOVAL GATE

Backend operational parity SATISFIED (H6/FA-2, zero blockers) · Model Library parity SATISFIED (H7/FA-5) · no legacy Experiment creator SATISFIED (H8+H13) · modern recent-runs migrated SATISFIED (H13) · Comparison scheduled to retire in the SAME Wave E SATISFIED (FC-7/FC-13) · redirects modern SATISFIED (H10/FB-3) · execution selector gone SATISFIED (H12) · workspace-registry fake blocker DISSOLVED (FA-1) · auth/setup not-required-parity SATISFIED (FA-4).

**`SETTINGS_LEGACY_GROUP_REMOVAL_READY = YES`** (proven row-by-row; no manufactured blockers).

## FC-15. HISTORY / OLD-DATA PRESERVATION (re-frozen)

Wave E must not alter: History V2 (schema/routes/writer/replay), `.run_history`, legacy experiment JSON, comparison stored data, RequestSnapshots, `legacy_mapping` + dormant `LegacyMigrationSeam`, replay-capability projection, workspace fallback, historical annotations, old images/assets. UI retirement ≠ data deletion; H3 §14 blockers all stand.

## FC-16. WAVE-E TEST GATE (design; the E lane must prove all 24)

1 Settings Legacy group absent · 2 standalone overlay cannot open (global deleted per FC-11) · 3 modern Settings opens · 4 Backend operational controls intact · 5 Workflows Model Library intact · 6 normal Studio aliases land modern · 7 Setup tab unmountable · 8 Profiles tab unmountable · 9 Results tab unmountable · 10 Settings legacy tab unmountable · 11 Comparison canvas menu absent (/prompt menu otherwise intact) · 12 Comparison overlay globals absent · 13 `/comparison/run` cannot execute (retired response; no `run_prompt_stream` reachable) · 14 stored Comparison profiles byte-identical · 15 Comparison read compatibility remains if frozen · 16 History old records remain · 17 canvas `/prompt` Local/Cloud unchanged (LS-key init shim per FC-12-B) · 18 canvas Production mode remains · 19 output options remain · 20 modern V2 execution remains · 21 H13 History-V2 recent-runs remains · 22 zero legacy Experiment creation · 23 live Single poll/Cancel remain (protected seams wired) · 24 no broad `/experiments` route deletion (registry unchanged except the optional same-change Comparison-run pin update).

## FC-17. WAVE-E FILE OWNERSHIP PLAN

`web/studio-settings.js` (Legacy-group region ONLY) · `web/studio-legacy.js` (loader surface) · `web/modal-settings.js` (overlay/UI regions ONLY; preserve FC-12-B/C/D) · `web/modal-comparison.js` (UI/overlay/context-menu regions) · `web/testing-setup.js` · `web/testing-profiles.js` · `web/testing-results.js` · `web/testing-settings.js` · `web/testing-ab-slider.js` (Phase-I feature NOT ported) · `web/modal-testing.js` (only lazy-tab/group cleanup; PRESERVE alias map + sidebar entry) · `__init__.py` (Comparison route region ONLY, single-writer) · comparison-specific tests/fakes (same-change registry pins only if the run route is removed). Avoid H12-complete execution-mode regions.

## FC-18. WAVE-F CONSEQUENCE MAP (post-prospective-E classification; do NOT implement in E)

READ_ONLY_COMPAT: `/comparison/*` reads (incl. validate/detect-slots) · `GET /experiments` · `/{id}/events` · checkpoint/cell GETs · `/run-history*` list/detail/logs/timing · annotations PATCH + save (until stale results.v1 population ages out). MUTATION_RETIRE→freeze: `/comparison/*` writers. INERT (retired in E): `POST /comparison/run`. ZERO_CALLER→freeze: compile/create/start/pause/resume/stop-after-current/run-missing/rerun*/clone · `POST /studio/experiment` · warmup (F decision lane; RETIRE confirmed FA-3). **MODERN_LIVE / INTERNAL_ONLY — DO NOT FREEZE: `GET /experiments/{id}` + `POST .../stop-now` (protected Single seams, FC-3/FC-4).** KEEP: `/history` unified platform feed · `/studio/experiment-v2` · `/history-v2/*` · `/studio/run` · presets/snapshots. `/studio/backends`: replace modern consumers with truthfully named seam then demote hidden read-only shim (§19). `/auth/setup`: compatibility route untouched; F/G review.

## FC-19. WAVE-G CONSEQUENCE MAP (caller-based residue; re-measured, none assumed)

Dead post-H12/E (delete WITH their dedicated tests): `direct_studio_run_completion` (`studio_run_adapter.py:3302`; zero production callers; consumed by registered `test_studio_direct_run`) · `execute_modal_prompt` (`canonical_execution.py:3615`) · `LocalRemoteInvoker` (`experiment_runner.py:1236`; test-consumed widely) · `_prepare_studio_run_context` (~:3081) + `_handle_studio_run_scheduler` (:3689) (reachable only via `direct=False`, zero production callers) · `_playground_runtime_mode` (:1910; re-measure at G) · `_execute_comparison_profile` (:5222, after E's retired response) · frontend dead helpers `runStudioExperiment`/`listExperiments`/`listRunHistory`/`setRunAnnotation`/`saveRunHistoryOutput` (`studio-backend-api.js`) and `testing-api.js` create/run/preview/get helpers (zero importers verified) · retired module files after E (`testing-{setup,profiles,results,settings}.js`, `testing-ab-slider.js`, `modal-comparison.js` UI layer, `studio-legacy.js`, modal-settings overlay regions, modal-testing lazy-tab remnants) · out-of-gate/stale tests (FC-20). NOT dead (never delete): `modal_client.run_prompt_stream` (V2 transport), `REGISTRY.history()` readers + `history_index.py`, `LegacyMigrationSeam`/`legacy_mapping`, replay projection, workspace fallback, `GET /history` platform feed.

## FC-20. CURRENT TEST-REGISTRATION DEBT (carried forward; NOTHING registered now)

Unregistered Node units (verified absent from `NODE_UNIT_FILES`): `studio_backend_operations_unit.mjs` (H6) · `studio_model_library_parity_unit.mjs` (H7) · `studio_legacy_settings_authority_unit.mjs` (MIGRATE-THEN-REGISTER, §27). Unregistered Python suites (verified absent from `STUDIO_PY_MODULES`): `test_phase8_execution_mode.py` (H12 rewrite) · `test_h12_v2_only_consolidation.py` (H12 new). Out-of-gate stale pins (Class B/D, H5B §6 unchanged): tracker-membership ×5 (`test_task3_progress_annotations`) · production-summary-label + output-savefolder-literal (`test_modal_workspace_ui_ast`). H12 reverse-order isolation artifact (`test_f8_gpu_authority` before `test_workflow_run_integration` leaks the `history_v2_writer` singleton) — L-TST note; gate order remains authoritative.

## FC-21. FINAL WAVE-E ENTRY VERDICT

**`WAVE E READY`**

No Phase-H-contract blocker remains. Items deferred to F/G (scheduler-route refactor, warmup route/code deletion, dead-helper deletion, test-registration debt) are explicitly out of E scope by this freeze and are NOT E blockers.

Deploy / live / GPU / generation / commit / push by this follow-up: **NONE**.

---

# H5 FOLLOW-UP D — POST-WAVE-E CONVERGENCE & WAVE-F ENTRY FREEZE (APPENDED 2026-08-24)

**Batch type:** H5 contract follow-up / same-batch post-Wave-E reconciliation. READ-ONLY against production code and tests except this appendix + `PHASE_H5D_WAVE_E_CONVERGENCE_WAVE_F_FREEZE_2026-08-24.md` (evidence detail; this appendix is authoritative). No deploy, no Modal/GPU/live generation, no commit/push/branch/worktree/reset/stash/clean, no stored-data change, no route frozen or deleted. The working tree was intentionally dirty (H14 Wave E landed uncommitted).
**Trigger:** Wave E (H14) retired the final legacy/Comparison PRODUCT surfaces. Before Wave F changes API writeability, ONE exact post-E contract is frozen — specifically so Wave F cannot freeze-by-name (e.g. mislabel the mutating run-history annotation/save routes as reads, or freeze the still-live Backend/Runtime Preset authority because its filename contains "studio").
**Inputs read completely:** this contract incl. Follow-Ups A/B/C, H5A, H5B, H5C, H12, H13, H14, H3. Current source re-measured directly (route decorators enumerated from `__init__.py`/`studio_routes.py`/`history_v2_routes.py`/`experiment_modern_routes.py`/`model_library_routes.py`; frontend call graphs re-traced from `web/*.js`; fake mirror inventory from `fake-server.mjs`).

## FD-1. AUTHORITATIVE POST-E GATE (measured by this batch, sole baseline going forward)

```
python tests/run_studio_tests.py --fake
  python             run=1974  fail=0    error=0    skip=0
  node-unit          run=21    fail=0    error=0    skip=0
  fake-playwright    run=1     fail=1    (wrapper aggregate)
npx playwright test --config=playwright.fake.config.mjs --reporter=line
  211 passed / 211   (direct count; re-run after one wrapper flake)
```

```
POST-WAVE-E BASELINE (2026-08-24): Python 1974 · Node-unit 21 files · Fake Playwright 211
Delta vs FC-1 (post-C/D 1945/21/211): +29 Python = exactly H14 §16's account (+27 new
test_h14_wave_e_retirement.py, +1 StudioLegacyContractTests split, +1 sidebar-guard pin);
Node ±0; Fake ±0. No unexplained drift.
```

Flake note: the wrapper's first fake lane run failed `studio-fake-lifecycle.spec.mjs:523` ("workflow node progress is not overwritten by sampler max", 20s wait timeout under parallel load); it passes in isolation AND the full direct config run is 211/211. Environmental parallel-load flake, not a regression; recorded for L-TST.

## FD-2. ROUTE-CLASS VOCABULARY (FROZEN — supersedes all earlier ad-hoc labels)

Every route below gets exactly ONE primary class:

| Class | Meaning |
|---|---|
| MODERN_LIVE | Required by current modern product behavior. |
| TRANSITIONAL_MODERN | Still called by modern product code; implementation debt refactorable later. |
| COMPAT_READ | Hidden compatibility route reading old data; must remain non-destructive. |
| COMPAT_WRITE | Hidden/transitional route that STILL legitimately writes because a surviving compatibility population/caller depends on it. |
| RETIRED_WRITE | Writer/action with zero legitimate callers; Wave F makes it inert. |
| RETIRED_EXECUTION | Execution endpoint already/permanently non-executing. |
| INTERNAL_ONLY | No product API ownership; used internally by surviving code. |
| ZERO_CALLER | No production caller and no compatibility requirement; eligible for later freeze/delete per wave ownership. |
| UNKNOWN | Insufficient evidence. |

UNKNOWN count across all tables below: **0**.

## FD-3. WAVE-E PRODUCT STATE — VERIFIED (§1 checklist)

All confirmed in current source: no Settings Legacy group (`renderLegacyView`/`activeLegacyTab` absent from `studio-settings.js`; only a retirement comment at :582–584) · no mountable legacy Setup/Profiles/Results/Settings tabs (loader registrations deleted; `studio-legacy.js` unreachable-dead) · no standalone overlay (`open_comfymodal_settings`/`mountSettingsPanel` referenced ONLY inside dead `testing-settings.js`) · no Comparison Profiles/Runner UI, overlay globals, or canvas menu (`modal-comparison.js:1387–1392` is a doc-comment only; extension registration deleted ⇒ builders unreachable) · `POST /comparison/run` registered and inert with truthful 410 `COMPARISON_RETIRED` (`__init__.py:5543–5563`, body not parsed) · stored Comparison data untouched (no comparison dirs repo-side; behavioral byte-integrity pinned by H14 tests) · Comparison READ_COMPAT intact (`GET /comparison/profiles` answers 200 from stored data — H14 test) · H10 alias routing intact (`ALIAS_PAGE_MAP` 7 aliases, `modal-testing.js:227`) · normal Studio sidebar intact (`PAGES` = Playground/History/Workflows/Backend/Settings, `studio-shell.js`) · canvas compatibility shim intact (`modal-settings.js:4125–4133` initializes `window._comfyModalEnabled` from persisted key).

**One discrepancy found (reported, NOT modified):** modern Settings ▸ Advanced still renders the **"Runtime & Backend" group** (deploy-state row + Snapshots/Presets/**Backends** count rows + "Open Backend tab" link; `studio-settings.js:528–580`, refreshed at :626–627), pinned green by `tests/test_studio_backend.py:392–407`. This contradicts H5 §2 ("operational state/readouts belong in Backend, never Settings") and §11's REMOVE list (Wave A2/E) — pre-existing contract debt that predates and survived E; H14 never claimed its removal. It is NOT a Wave-E regression and NOT a Wave-F blocker, but it is the ONE live modern consumer of `GET /studio/backends` (FD-8). Disposition: F removes exactly the Backends count row (FD-8); the remaining rows are recorded debt for G/later reconciliation.

## FD-4. RUN-HISTORY ANNOTATIONS/SAVE — CRITICAL CORRECTION (supersedes H14 §17 "READ_ONLY_COMPAT (shrinking)")

`PATCH /run-history/{id}/annotations` (`__init__.py:6918`) and `POST /run-history/{id}/save` (:6979) are **MUTATING routes** and are **COMPAT_WRITE with LIVE production callers** — not read-only, not merely shrinking:

- Exact callers (`web/studio-playground.js`): favorite → :3393, note → :3490, Save-output → :3802. Each branches on `nr._historyKind`: History-V2-backed records use the durable V2 authorities (`repo.setFavorite/setNote/exportAsset`); records WITHOUT `_historyKind` fall through to `updateRunAnnotation` (= PATCH annotations) / `saveRunOutput` (= POST save).
- When the legacy branch executes TODAY: (a) **fresh direct-run result panels** — `_handleDirectRunResult` builds the selected record via `normalizeStudioRun` (:2661), which sets NO `_historyKind`, so favorite/note/save on a just-completed run write to the freshly created `.run_history` row (`play_<hex>`); (b) **stale persisted selections** restored from localStorage `results.v1` via `loadRunResult` (:476/:883), which also lack the tag.
- Can a current user reach it? YES — both paths above are ordinary Playground interactions.
- Do History-V2-backed selections bypass it? YES (filmstrip records all carry `_historyKind` from `refreshRecentRuns` :345/:370).
- Does the stale population shrink naturally? Only (b); population (a) is recreated on every direct run. No one-time migration exists for either.
- Would freezing in F break existing behavior? YES — favorite/note/save on the Playground result panel would fail.

**FROZEN: both routes = COMPAT_WRITE. Wave F MUST NOT make them read-only or inert.** Future retirement condition (explicit): re-point the fresh-run result panel at the V2 authorities by tagging direct-run records as History-backed (or resolving `runId`→V2 generation) AND decide/expire the stale persisted-results population; once zero callers remain, a later wave may freeze. Until then they stay untouched.

## FD-5. RUN-HISTORY READ FAMILY = COMPAT_READ (×4)

GET `/run-history` (:6848) · GET `/run-history/{id}` (:6891) · GET `/{id}/logs` (:6899) · GET `/{id}/timing` (:6908). All read-only over `REGISTRY.history()`; zero destructive potential. Current callers: list = none (helper `listRunHistory` has zero importers; bridge feed uses `/history` unified); detail = opt-in bridge repository mode only (`history-v2-repository.js:883`, reachable solely via explicit `mode:"bridge"`/`window.__COMFYMODAL_HISTORY_MODE__` — programmatic, default is v2); logs/timing = none, and have NO History-V2 equivalent yet (H3 §10). Compatibility requirement stands: `.run_history` remains written by every modern run (Playground Stage 8) and rows never mirrored into V2 are readable only here. **Wave F preserves behavior; do not delete.**

## FD-6. BACKEND/RUNTIME PRESETS — STILL LIVE (resolves the H5 §15B vs §25-Wave-F wording conflict)

**`BACKEND_RUNTIME_PRESETS = MODERN_LIVE_TRANSITIONAL`.** Post-E consumers re-measured: Playground runtime selection (`getRuntimePresets` `studio-backend.js:49` wrapping `listPresets`→`GET /studio/presets`; consumed at `studio-playground.js:707/:1177/:3005`; dynamic `listPresets` imports :423/:2723) · Experiment mode (`studio-experiment-mode.js:137–138`) · Backend page "Backend Presets" tab with full CRUD (`studio-backend-presets.js` via `listPresets/createPreset/updatePreset/duplicatePreset/deletePreset`) · preset wizard (`studio-preset-wizard.js:866/:925`) · Settings counts row fetch (:723) · `POST /studio/run` carries `presetId` (runtime selection authority). No prior consumer disappeared in E.

Consequences (binding, supersede the generic §25 Wave-F bullet "legacy experiment/preset writes stop" FOR THIS STORE ONLY): EXCLUDE `/studio/presets*` writes from the Wave-F legacy-write freeze · DO NOT make `.studio_presets.json` read-only · DO NOT rename it Workflow Presets · DO NOT merge stores. Convergence to another preset authority requires a separate future contract (conditions: Playground selection + Backend UI + wizard migrated, and History mixed-era `preset_id` provenance re-verified per H3 §14 #4). The generic Wave-F "preset writes stop" wording continues to apply to the `.presets/prompts|images` comparison substrate (FD-16).

## FD-7. WORKFLOW PRESETS REMAIN DISTINCT (pinned)

Modern Workflow Presets stay version-scoped, Workflows-owned, served by `/studio/workflows/versions/{vid}/presets*` + `/studio/workflows/presets/*` (`studio-backend-api.js:530–578`) against `.studio_workflow_presets.json` — a different store, different routes, different concept from Backend/Runtime Presets (`.studio_presets.json` via `/studio/presets*`). No Wave-F action may merge, rename, or cross-freeze these concepts (H5 §15; invariant 26 extended).

## FD-8. `/STUDIO/BACKENDS` — EXACT CONSUMER DISPOSITION (outcome B/C hybrid)

Route family: GET list (:7258; folds comparison profiles in via `_discover_legacy_profiles_as_backends`) · POST create (:7290) · PATCH update (:7312) · DELETE (:7340) · POST duplicate (:7353) — all writing `.studio_backends.json`.

Exact caller table (post-E):

| Caller | Route | Status |
|---|---|---|
| `web/studio-settings.js:724` (Settings Runtime & Backend → Backends count row) | GET | **LIVE modern consumer** (count-only display) |
| `getBackends`/`getCompareBackends` (`studio-backend-api.js:26/:39`, re-exported `studio-backend.js:28/:32`) | GET (+`?kind=comparable`) | **ZERO callers** — dead exports (comment-only reference `studio-playground.js:1150`) |
| Modern Backend page (H6 modules) | any | ZERO consumers |
| fake-server.mjs:562 | GET | mirror only (no write mirrors exist) |
| Python-internal HTTP callers | any | NONE |

**FROZEN:** No truthful replacement seam is required — the sole consumer needs NO real data (it displays a count of a misnamed compatibility store, an operational readout that per H5 §11 never belonged in Settings). Wave F action, ONE change: (1) remove the Backends count row + its fetch leg from `studio-settings.js` and adjust the two test assertions pinning it (`test_studio_backend.py:398` testid pin, :407 label pin); (2) demote writes POST/PATCH/DELETE/duplicate → RETIRED_WRITE bounded error; (3) GET remains registered as hidden COMPAT_READ shim answering from stored data. Do NOT call any replacement a "provider" API; do NOT use Phase-G portability targets; do NOT build a new seam at all.

## FD-9. COMPARISON ROUTES — FINAL TABLE (17 registered; methods from decorators, semantics from handlers)

Frontend reachable callers post-E: **0 for every route** (all fetch sites live in inert `modal-comparison.js` residue or UNREACHABLE_DEAD `testing-profiles.js`/`testing-setup.js`). Internal Python HTTP callers: 0.

| # | Method | Path (:line) | Reads stored | Writes stored | Executes | Frontend callers | H14 class | H5D class |
|---|---|---|---|---|---|---|---|---|
| 1 | GET | /comparison/profiles (:5437) | Y | N | N | 0 | READ_COMPAT | **COMPAT_READ** |
| 2 | POST | /comparison/profiles (:5445) | N | Y | N | 0 | MUTATION_RETIRE | **RETIRED_WRITE** |
| 3 | GET | /comparison/profiles/{id} (:5461) | Y | N | N | 0 | READ_COMPAT | **COMPAT_READ** |
| 4 | PUT | /comparison/profiles/{id} (:5472) | N | Y | N | 0 | MUTATION_RETIRE | **RETIRED_WRITE** |
| 5 | DELETE | /comparison/profiles/{id} (:5484) | N | Y | N | 0 | MUTATION_RETIRE | **RETIRED_WRITE** |
| 6 | POST | .../duplicate (:5495) | N | Y | N | 0 | MUTATION_RETIRE | **RETIRED_WRITE** |
| 7 | POST | .../validate (:5510) | Y | **N** (pure compute) | N | 0 | READ_COMPAT | **COMPAT_READ** |
| 8 | POST | .../detect-slots (:5519) | Y | **N** (pure compute) | N | 0 | READ_COMPAT | **COMPAT_READ** |
| 9 | POST | .../slots (:5530) | N | Y | N | 0 | MUTATION_RETIRE | **RETIRED_WRITE** |
| 10 | POST | /comparison/run (:5543) | N | N | **N since E** | 0 | INERT | **RETIRED_EXECUTION** |
| 11 | GET | /comparison/results (:5565) | Y | N | N | 0 | READ_COMPAT | **COMPAT_READ** |
| 12 | GET | /comparison/results/{id} (:5573) | Y | N | N | 0 | READ_COMPAT | **COMPAT_READ** |
| 13 | GET | .../workflow/nodes (:5584) | Y | N | N | 0 | READ_COMPAT | **COMPAT_READ** |
| 14 | GET | .../workflow (:5595) | Y | N | N | 0 | READ_COMPAT | **COMPAT_READ** |
| 15 | GET | /comparison/config (:5606) | Y | N | N | 0 | READ_COMPAT | **COMPAT_READ** |
| 16 | POST | /comparison/config (:5614) | N | Y | N | 0 | MUTATION_RETIRE | **RETIRED_WRITE** |
| 17 | GET | /comparison/gallery/{id} (:5623) | Y | N | N | 0 | READ_COMPAT | **COMPAT_READ** |

Classification is by SEMANTICS: validate/detect-slots stay POST but are non-persisting compute → COMPAT_READ (do not force GET-only purity). No lazy repair/write-on-read exists in any read handler (verified: reads return computed/stored values only). Split: **COMPAT_READ 10 · RETIRED_WRITE 6 · RETIRED_EXECUTION 1.**

## FD-10. COMPARISON MUTATIONS — WAVE-F TARGET AND ERROR VOCABULARY

The six RETIRED_WRITE routes become bounded non-mutating responses: route stays REGISTERED (registry pins in `test_routes_registered.py` stay valid), request body need not be parsed, response = HTTP **409** `{"status":"error","error_code":"COMPARISON_READ_ONLY","message":"Comparison stores are read-only compatibility data (Phase H Wave F). Stored profiles and historical results remain readable."}`. Zero persistent mutation, zero manifest mutation, zero execution, stored data byte-identical. **Recommendation (frozen): use `COMPARISON_READ_ONLY` for data-write retirement and keep `COMPARISON_RETIRED` exclusively for execution retirement** — distinguishing write-retirement from execution-retirement is more truthful than overloading one code. 409 (conflict-with-frozen-state) is chosen over 410 because the underlying data still exists and remains readable; 410 stays reserved for gone capabilities.

## FD-11. COMPARISON RUN — RETIRED EXECUTION CONFIRMED

`POST /comparison/run` retains the H14 bounded 410 `COMPARISON_RETIRED` response with zero executor call, zero history write, zero profile mutation (body not parsed; proven by H14 route-level tests incl. stored-profile SHA-256 byte-integrity). Class **RETIRED_EXECUTION**. Wave F must NOT reactivate or repurpose it; whether G deletes the route (+ `_execute_comparison_profile` dead body + now-unused imports) remains a separate G decision with same-change pin/fake updates.

## FD-12. LEGACY EXPERIMENT FAMILY — FINAL TABLE (22 routes + adjacent)

Frontend reachable callers post-E: only the two protected seams. Legacy-UI readers died with E (`testing-results.js` unreachable). Python-internal HTTP callers: 0 (server consumes REGISTRY directly).

| Route (method, :line) | Frontend callers | Mutation | Execution/scheduler | H5D class | Wave-F action | Wave-G action |
|---|---|---|---|---|---|---|
| GET /experiments (:5881) | 0 (was testing-results picker) | N | N | **COMPAT_READ** | preserve | delete candidate |
| GET /experiments/{id} (:5910) | **LIVE poll seam** | N | N | **TRANSITIONAL_MODERN** `WAVE_F_DO_NOT_FREEZE = TRUE` | NONE — protected | stays |
| GET /{id}/events (:5927) | 0 | N | N | **COMPAT_READ** | preserve | delete candidate |
| POST /experiments/compile (:5734) | 0 | **N** (pure compute) | N | **ZERO_CALLER** (non-persisting) | may remain untouched or bounded-inert; no data risk | delete route+helper |
| POST /experiments (create, :5778) | 0 | Y (definition + History V2 ensure) | **Y** (starts scheduler) | **RETIRED_EXECUTION** | bounded retired response | delete candidates |
| POST /{id}/start (:5946) | 0 | Y | **Y** | **RETIRED_EXECUTION** | bounded retired response | delete candidates |
| POST /{id}/pause (:6347) | 0 | Y (scheduler state) | N | **RETIRED_WRITE** | bounded read-only error | delete candidate |
| POST /{id}/stop-after-current (:6358) | 0 | Y (scheduler state) | N | **RETIRED_WRITE** | bounded read-only error | delete candidate |
| POST /{id}/stop-now (:6369) | **LIVE Cancel seam** | Y (scheduler/pending-stop) | stops scheduler only | **TRANSITIONAL_MODERN** `WAVE_F_DO_NOT_FREEZE = TRUE` | NONE — protected | stays |
| POST /{id}/resume (:6389) | 0 | Y | **Y** (re-schedules) | **RETIRED_EXECUTION** | bounded retired response | delete candidate |
| POST /{id}/clone (:6401) | 0 | Y (new definition) | N | **RETIRED_WRITE** | bounded read-only error | delete candidate |
| POST /{id}/run-missing (:6481) | 0 | Y | **Y** | **RETIRED_EXECUTION** | bounded retired response | delete candidate |
| POST .../checkpoints/{cp}/continue·restart·restart-from (:6493/:6509/:6522) | 0 | Y | **Y** | **RETIRED_EXECUTION** | bounded retired response | delete candidates |
| POST .../checkpoints/{cp}/skip·unskip (:6535/:6551) | 0 | Y (cell flags) | N | **RETIRED_WRITE** | bounded read-only error | delete candidates |
| GET .../checkpoints/{cp}/logs (:6567) | 0 | N | N | **COMPAT_READ** | preserve | delete candidate |
| GET .../cells/{cell} (:6585) · /attempts (:6597) | 0 | N | N | **COMPAT_READ** | preserve | delete candidates |
| POST .../cells/{cell}/rerun (:6601) | 0 | Y | **Y** | **RETIRED_EXECUTION** | bounded retired response | delete candidate |
| POST /{id}/rerun-selected (:6614) | 0 | Y | **Y** | **RETIRED_EXECUTION** | bounded retired response | delete candidate |
| (adjacent) POST /studio/experiment (:7531) | 0 (`runStudioExperiment` zero importers) | Y (REGISTRY + History V2 ensure) | **Y** (starts scheduler) | **RETIRED_EXECUTION** | bounded retired response | delete with helper |
| (adjacent) POST /studio/experiment-v2 | modern D5 | — | — | **MODERN_LIVE** | keep | keep |

Zero-real-reader check (§15 mandate): every COMPAT_READ row above retains its stored-data inspection purpose for old records/tools; the one route with neither caller nor compat need was classified ZERO_CALLER (compile). Goal state after F: no new legacy Experiment state can be created/mutated and nothing executes through hidden API calls; historical `.experiments/` data untouched; Experiment-v2 unaffected.

## FD-13. PROTECTED SINGLE SEAMS — RE-VERIFIED

Current wiring confirmed: `GET /experiments/{id}` ← `_startPolling`→`getStudioRunStatus` (`studio-playground.js:121`; helper `studio-backend-api.js:157`) and `POST .../stop-now` ← Cancel→`stopExperiment` (`studio-playground.js:2845`; helper :169). Handlers unchanged (`__init__.py:5910` REGISTRY read; :6369 scheduler-stop/pending-stop/404). Both rows carry literal **`WAVE_F_DO_NOT_FREEZE = TRUE`**: Wave F must not alter method, status codes, response body, scheduler interaction, or frontend callers. Internal naming debt remains LATER_INTERNAL_REFACTOR (FC-4). Do NOT "clean up" these routes because adjacent `/experiments` routes retire.

## FD-14. WARMUP FAMILY — EXACT FREEZE DESIGN

| Route | Method/Path (:line) | Behavior | Callers | H5D class | Wave-F target |
|---|---|---|---|---|---|
| status | GET /deploy-warmup/status (:7588) | reads WarmupState snapshot | 0 (zero `deploy-warmup` references in web/) | **ZERO_CALLER** (diagnostic read; no compat requirement identified) | may remain as inert read OR bounded-inert; no data risk |
| run | POST /deploy-warmup/run (:7596) | resolves workflow (body or latest benchmark default) → **`run_prompt_stream` directly** → marks warmed/failed | 0 UI; deploy flow does NOT invoke it (deploy marks `deployed_unwarmed` and expects manual call, `__init__.py:1714–1742`) | **RETIRED_EXECUTION** | bounded 410 `WARMUP_RETIRED`; after F NO warmup route may trigger model execution |
| invalidate | POST /deploy-warmup/invalidate (:7674) | mutates warmup state file | 0 | **RETIRED_WRITE** | bounded 409 `WARMUP_RETIRED` |

The last warmup consumer-gate (`gate_experiment_on_stored_generation`, inside the zero-caller legacy experiment create/start family) freezes with FD-12. `WarmupState` itself stays: deploy flow writes `deployed_unwarmed` truth and modern Backend displays it verbatim (FA-3). **`modal_client.run_prompt_stream` itself REMAINS** — V2 transport (`execute_plan`→`ModalTransport`) uses the shared streaming transport; only the direct un-planned invocation pattern retires. Warmup code deletion = Wave G.

## FD-15. `/AUTH/SETUP` DISPOSITION

`POST /auth/setup` (:3577) validates ak-/as- tokens, writes GLOBAL `modal.toml`, upserts/activates a "Primary" workspace, and fires a background deploy thread. Post-E callers: **ZERO** (the legacy auth panel died with the overlay; zero `auth/setup` references in `web/`). No compatibility requirement identified — workspace-scoped credential APIs (Workspaces add/edit, Credentials status, HF/Civitai) fully own the function (FA-4/H6). **Class: RETIRED_WRITE.** Wave F may make it inert: bounded 409 `AUTH_SETUP_RETIRED`, zero file write, zero workspace mutation, zero background deploy. The global `modal.toml` FILE is untouched (still read by deployment flows); only the route retires. Workspace-scoped modern credential routes are excluded from F (FD-18).

## FD-16. `.PRESETS/PROMPTS·IMAGES` LEGACY SUBSTRATE (13 routes, :6636–6750)

Prompt family: GET list/`{id}` · POST create · PUT `{id}` · DELETE `{id}` · POST duplicate · POST import. Image family: GET list/`{id}` · POST create · PUT `{id}` · DELETE `{id}`. Sole frontend caller ever: `testing-setup.js` (UNREACHABLE_DEAD). Zero fake mirrors. These are H5 §15C's comparison/experiment substrate — THIS is the "legacy preset writes stop" target of the generic Wave-F wording. Classes: reads → **COMPAT_READ** (stored user prompt/image presets stay inspectable); writes → **RETIRED_WRITE** (bounded 409 `LEGACY_PRESETS_READ_ONLY`). Stored `.presets/` files untouched.

## FD-17. RETIRED-ROUTE RESPONSE STANDARD (FROZEN — implementers must not invent per-route semantics)

Two machine-readable classes, following the landed precedents (`COMPARISON_RETIRED` 410 from E; `EXECUTION_MODE_RETIRED` 400 pre-acceptance guards from H12, unchanged):

1. **EXECUTION retirement** — capability permanently gone:
   `HTTP 410` · `{"status":"error","error_code":"<FEATURE>_RETIRED","message":"<feature> was retired in Phase H (Wave F). <one truthful sentence about what remains readable/modern>."}`
   Codes: `COMPARISON_RETIRED` (already landed), `EXPERIMENT_RETIRED` (create/start/resume/run-missing/checkpoint continue/restart/restart-from/cells rerun/rerun-selected, `/studio/experiment`), `WARMUP_RETIRED` (warmup run).
2. **WRITE retirement on frozen/read-only compat data** — data survives, mutations refuse:
   `HTTP 409` · `{"status":"error","error_code":"<FEATURE>_READ_ONLY","message":"<store> is read-only compatibility data (Phase H Wave F). Stored records remain readable."}`
   Codes: `COMPARISON_READ_ONLY`, `EXPERIMENT_READ_ONLY` (pause/stop-after-current/clone/skip/unskip), `WARMUP_RETIRED` for invalidate (state file, 409), `BACKENDS_READ_ONLY`, `AUTH_SETUP_RETIRED`, `LEGACY_PRESETS_READ_ONLY`.

Requirements (all classes): deterministic; bounded JSON; no stack traces; no mutation before response; no background action; no deploy; no executor call; parse the body only if necessary (prefer the `comparison_run` precedent of not parsing). Status-code rationale: 410 = capability gone; 409 = state conflict with surviving readable data.

## FD-18. WAVE-F EXCLUSIONS — DO-NOT-TOUCH LIST (authoritative; paste into the implementation prompt)

- `GET /experiments/{id}` and `POST /experiments/{id}/stop-now` — `WAVE_F_DO_NOT_FREEZE = TRUE` (protected Single seams, FD-13)
- `POST /studio/experiment-v2` and the whole `/history-v2/experiments/*` modern family
- `POST /studio/run` (Single acceptance; freezes RequestSnapshots) and the V2 workflow lane of `handle_workflow_run_async`
- History V2 routes (`/history-v2/feed|generations/*|experiments/*|assets/*`) — schema, handlers, writer, replay
- `PATCH /run-history/{id}/annotations` and `POST /run-history/{id}/save` — COMPAT_WRITE (FD-4)
- `/run-history` read-family behavior (COMPAT_READ, FD-5)
- `/studio/presets*` ALL methods and `.studio_presets.json` (MODERN_LIVE_TRANSITIONAL, FD-6)
- Workflow Presets routes/stores (FD-7) and the whole Workflow domain (workflows/versions/mappings/tags/folders/import/export/portability/dependencies/compatibility)
- Workspace routes (`/workspaces*`), deploy/redeploy/status/log routes, credentials/auth-status/HF/Civitai routes, Model Library routes (`/studio/models*`, `/studio/custom-nodes*`), snapshots routes
- Canvas `POST /prompt` interception chain and `modal_client.run_prompt_stream`
- `GET /history` unified platform feed
- Comparison COMPAT_READ routes (FD-9 rows 1,3,7,8,11–15,17)
- `.run_history` readers (`REGISTRY.history()`, `history_index.py`), `legacy_mapping` + dormant `LegacyMigrationSeam`, replay-capability projection, workspace fallback, RequestSnapshots, portability cache, workspace registry, old assets — no migration/deletion of ANY stored data (FD-20)

## FD-19. FAKE-BACKEND PARITY OBLIGATIONS (H3 §13 #11; no fake edits in THIS batch)

| Route family | Fake handler today? | Spec coverage today? | Required Wave-F change |
|---|---|---|---|
| POST /studio/experiment | YES (mirror creates) | negative-only (zero-call pins) | mirror → retired response (same change as production freeze) |
| Comparison writers (6) | NO mirror | none | none required (no spec hits them); optional additive 409 mirror if a retirement spec is added |
| /comparison/run | NO mirror | H14 route-level Python tests only | none required |
| Experiment writers/executors (12) | NO mirror | registry pins only (`test_routes_registered.py`) | none required; optional additive 410/409 mirrors with new specs |
| Warmup ×3, /auth/setup | NO mirror | structural only | none required |
| .presets/prompts·images writers | NO mirror | registry pins only | none required |
| /studio/backends GET | YES mirror | Settings-page fetch consumes it | keep until G; harmless after the count row is removed |
| /studio/backends writers | NO mirror | none | none required |
| run-history reads + annotations/save | YES mirrors | recent-runs + lifecycle specs | MUST STAY (routes stay live per FD-4/FD-5) |
| /studio/presets* full CRUD | YES mirrors | backend presets + wizard + runtime specs | MUST STAY (live authority) |

Rule: any production behavior change on a mirrored route requires the fake mirror update in the SAME change; unmirrored retirements need no fake work unless a new spec exercises them.

## FD-20. HISTORY/DATA IMMUTABILITY (re-pinned for F)

Wave F must preserve byte-for-byte (no migration, no deletion, no rewrite): History V2 DB + RequestSnapshots · `.run_history` · legacy Experiment JSON (`.experiments/`) · Comparison profiles/manifests/results/gallery · `.studio_presets.json` · `.presets/` prompt/image presets · `.studio_backends.json` · Workflow domain stores · portability cache · workspace registry · old assets/images · warmup state file (invalidate/write routes go inert; the file itself is not deleted). Route freezing NEVER performs migration/deletion.

## FD-21. ROUTE-REGISTRY DECISIONS (per family, not generic)

Keep REGISTERED + inert (bounded responses) — external/old-client compatibility or router stability benefits, and `test_routes_registered.py` pins stay valid: ALL 17 `/comparison/*` · all legacy `/experiments*` writers/executors · `POST /studio/experiment` · warmup run/invalidate · `/auth/setup` · `.presets/prompts·images` writers · `/studio/backends` writers. Deletion is NOT a Wave-F action anywhere; Wave G may delete only where zero compatibility requirement holds AND same-change registry-pin/fake/spec updates land (candidates: compile, `.presets` family, warmup family, `/studio/experiment`, backends writers — re-measure callers at G).

## FD-22. WAVE-F FILE OWNERSHIP PLAN (collision-safe)

All server-side retirement regions live in `__init__.py` ⇒ **ONE serialized server lane**:

| Lane | Owned files | Scope |
|---|---|---|
| **F-SRV** (single writer, runs alone) | `__init__.py` (regions: comparison writers :5445–5541 · experiment writers/executors :5734–6630 except the two protected seams' handlers · `/studio/experiment` :7531 · warmup :7588–7678 · auth/setup :3577 · backends writers :7290–7372 · `.presets` writers :6640–6766) + `tests/browser/fake/fake-server.mjs` (POST /studio/experiment mirror parity) | apply FD-9/10/11/12/14/15/16/17 bounded responses; verify run-history/presets/backends-reads untouched |
| **F-BE** (parallel-safe: disjoint files) | `web/studio-settings.js` (Backends count row + fetch leg ONLY) + `tests/test_studio_backend.py` (adjust the two Runtime-group pins) | FD-8 consumer removal — must land in the same wave as F-SRV's backends-writer demotion (consumer removal first or same merge) |
| **F-TST** (after F-SRV lands) | NEW `tests/test_h5d_wave_f_freeze.py` (or equivalent) + `tests/run_studio_tests.py` registration (sequential, single-writer) | FD-23 matrix |

No two lanes hold the same file concurrently. `__init__.py` is NEVER concurrently writable — F-SRV is serialized by design. Protected-seam handlers and all FD-18 exclusions are outside every lane's owned regions.

## FD-23. WAVE-F TEST MATRIX (design; the F lane must prove all)

1. Each retired Comparison mutation returns 409 `COMPARISON_READ_ONLY` and writes zero bytes (stored-profile hash before/after). 2. Comparison read routes still answer from stored data. 3. `/comparison/run` still 410 `COMPARISON_RETIRED`. 4. Retired Experiment create/start/etc. return 410/409 per FD-17 and mutate nothing (REGISTRY store snapshot equality). 5. `/studio/experiment` cannot execute (410; zero scheduler creation). 6. experiment-v2 remains live (happy path green). 7. `GET /experiments/{id}` unchanged (200 shape + 404 unknown-id). 8. stop-now unchanged (scheduler stop / pending / 404 semantics). 9. Warmup run cannot execute after F (410; zero `run_prompt_stream` reachability — census pin). 10. V2 ModalTransport still streams through `run_prompt_stream` (existing V2 specs green). 11. run-history reads remain (list/detail/logs/timing answer). 12. annotations/save still write (COMPAT_WRITE preserved — regression guard against over-freezing). 13. Backend/Runtime Presets remain fully writable (CRUD spec green). 14. Workflow Presets unaffected. 15. Settings Backends count row absent + `/studio/backends` GET still answers (hidden shim) + no other consumer regressed. 16. auth/setup disposition truthful (409, zero `modal.toml` mtime change). 17. Stored files byte-identical under every retired write (hash sweep). 18. Fake mirror of `/studio/experiment` matches production retirement. 19. Full H12 V2-only suite green. 20. Full H13 recent-runs suite green. 21. H14 product-retirement suite green.

## FD-24. TEST-DEBT RE-MEASURE (carried forward; NOTHING registered by this batch)

Registered NOW: `tests/test_h14_wave_e_retirement.py` (`run_studio_tests.py:95`). Still UNREGISTERED: Python `test_phase8_execution_mode.py`, `test_h12_v2_only_consolidation.py`; Node `studio_backend_operations_unit.mjs`, `studio_model_library_parity_unit.mjs`, `studio_legacy_settings_authority_unit.mjs` (MIGRATE-THEN-REGISTER per §27). Out-of-gate stale pins unchanged: tracker-membership ×5 (`test_task3_progress_annotations`), Production-summary-label pin + output-savefolder-literal pin (`test_modal_workspace_ui_ast`), F8/workflow reverse-order isolation artifact, dirty-`comfyapp.py` environmental failures (BOM SyntaxError / packaging TypeError) noted by H14. All remain Wave-G L-TST items.

## FD-25. WAVE-G BOUNDARY (F must not absorb)

Wave F freezes API behavior ONLY. Deletion stays in G: dead module files (`testing-*`, `studio-legacy.js`, `modal-comparison.js` UI layer, modal-settings overlay regions), dead frontend helpers (`runStudioExperiment`, `listExperiments`, `listRunHistory`; `setRunAnnotation`/`saveRunOutput` only AFTER their COMPAT_WRITE callers retire — so not even in G's first pass), `run_prompt_stream` cleanup is FORBIDDEN (V2 transport), `LocalRemoteInvoker`/`execute_modal_prompt`/`direct_studio_run_completion` deletion, retired-route code deletion, broad test-registration cleanup, remaining Settings Runtime-&-Backend rows reconciliation. G updates the residue map only.

## FD-26. FINAL WAVE-F ENTRY VERDICT

**`WAVE F READY`**

No contract blocker remains: every route family has an exact class, an exact Wave-F action, and an exact response contract; the two transitional Single seams, the run-history COMPAT_WRITE pair, and the live Backend/Runtime Preset authority are explicitly excluded; `/studio/backends` demotion is sequenced behind its one bounded consumer removal inside the wave. Transitional status of any route is handled by exclusion, not blockage.

Deploy / live / GPU / generation / commit / push by this follow-up: **NONE**.

---

# H5 FOLLOW-UP E — POST-WAVE-F CONVERGENCE & WAVE-F CLOSURE (APPENDED 2026-08-25)

**Batch type:** H17 = Wave-F test registration / combined convergence / completion freeze (F-TST finalization). Ran AFTER both implementation writers (H15 F-SRV, H16 F-BE); no concurrent production writer. No deploy, no Modal invocation, no GPU/live generation, no commit/push/branch/worktree/reset/stash/clean; unrelated dirty-tree work untouched. Files modified by this batch: **this appendix** + `PHASE_H17_WAVE_F_TEST_CONVERGENCE_AND_CLOSURE_2026-08-25.md` (evidence detail; this appendix is authoritative) + `tests/run_studio_tests.py` (one registration) + `tests/test_h15_wave_f_server_freeze.py` (docstring registration-status correction only). Zero production code modified.
**Trigger:** H15 created `tests/test_h15_wave_f_server_freeze.py` (36 tests) but intentionally left it unregistered (F-TST owned registration). This lane verified the combined H15+H16 tree, audited and registered the suite, reconciled counts exactly, ran one authoritative gate, and froze the post-Wave-F baseline.
**Inputs read completely:** this contract incl. Follow-Ups A/B/C/D (FD-1…FD-26 remain the Wave-F contract), H5D, H14, H15, H16, H12/H13 where referenced by FD-23.

## FE-1. H15/H16 CONVERGENCE VERDICT

**COEXIST — conflict found: NONE.** Verified directly in the current tree: `__init__.py` carries exactly COMPARISON_READ_ONLY ×6, COMPARISON_RETIRED ×1, EXPERIMENT_RETIRED ×10, EXPERIMENT_READ_ONLY ×5, WARMUP_RETIRED ×2 routes (+1 docstring), AUTH_SETUP_RETIRED ×1, BACKENDS_READ_ONLY ×4, LEGACY_PRESETS_READ_ONLY ×8 — matching H15 §1's table route-for-route; protected seams (`GET /experiments/{id}`, `POST .../stop-now`) contain no freeze vocabulary and their handlers are byte-untouched (pinned by registered tests). `web/studio-settings.js` has zero `settings-runtime-backends` testids and zero `/studio/backends` fetches while Deploy state / Snapshots count / Presets count / Open-Backend link all survive (H16 §2/§3/§7), with no replacement row/API built (H16 §4). No implementation marker was missing; nothing was compensated or weakened.

## FE-2. FINAL ROUTE CLASSIFICATION LEDGER (post-F; FD-2 vocabulary; UNKNOWN = 0)

| Family | Final classification |
|---|---|
| Comparison (17 routes) | **COMPAT_READ ×10** (profiles GET ×2, validate, detect-slots, results ×2, workflow/nodes, workflow, config GET, gallery) · **RETIRED_WRITE ×6** (profiles create/PUT/DELETE/duplicate, slots, config POST → 409 `COMPARISON_READ_ONLY`) · **RETIRED_EXECUTION ×1** (`/comparison/run` stays 410 `COMPARISON_RETIRED`) |
| Legacy Experiment | **TRANSITIONAL_MODERN ×2 PROTECTED** (`GET /experiments/{id}`, `POST .../stop-now` — byte-untouched, `WAVE_F_DO_NOT_FREEZE=TRUE`) · **COMPAT_READ ×5** (list, events, checkpoint logs, cells/{cell}, attempts) · **ZERO_CALLER ×1** (`POST /experiments/compile`, pure compute, untouched per FD-12) · **RETIRED_EXECUTION ×9+1** (create, start, resume, run-missing, checkpoints continue/restart/restart-from, cells rerun, rerun-selected → 410; adjacent `POST /studio/experiment` → 410 before any side effect) · **RETIRED_WRITE ×5** (pause, stop-after-current, clone, skip, unskip → 409) · **MODERN_LIVE ×1** (`POST /studio/experiment-v2`, zero freeze codes in `experiment_modern_routes.py`) |
| run-history | **COMPAT_READ ×4** (list/detail/logs/timing) · **COMPAT_WRITE ×2** (`PATCH .../annotations`, `POST .../save` — proven still mutating by registered test) |
| Backend/Runtime Presets | **MODERN_LIVE_TRANSITIONAL** — full CRUD green end-to-end; zero freeze codes in `studio_routes.py`; `.studio_presets.json` untouched |
| Workflow Presets | **MODERN_LIVE** — distinct store/routes; zero freeze codes in `studio_workflow_routes.py`; no merge/rename/cross-freeze |
| `/studio/backends` | **GET (+`?kind=comparable`) COMPAT_READ** hidden shim answering stored data · **writers ×4 RETIRED_WRITE** (409 `BACKENDS_READ_ONLY`) · **modern frontend consumers = 0** (H16 removed the sole Settings consumer; dead exports remain G debt) |
| Warmup | **status ZERO_CALLER** (still reads 200 `{status,state}`) · **run RETIRED_EXECUTION** (410 `WARMUP_RETIRED`, zero streaming) · **invalidate RETIRED_WRITE** (409 `WARMUP_RETIRED`, state file byte/mtime-identical) |
| auth/setup | **RETIRED_WRITE** (409 `AUTH_SETUP_RETIRED`; zero modal.toml write, zero workspace upsert, zero deploy thread — tripwired) |
| Legacy prompt/image presets (`.presets/prompts·images`) | **reads ×4 COMPAT_READ** · **writes ×8 RETIRED_WRITE** (409 `LEGACY_PRESETS_READ_ONLY`; dir hash-identical) |

Protected exclusions re-verified unchanged (FD-18): experiment-v2, `/studio/run`, History V2 family, run-history pair + reads, `/studio/presets*`, Workflow Presets, workspaces/deploy/credentials/models/snapshots routes, canvas `/prompt` chain, `modal_client.run_prompt_stream` (V2 ModalTransport transport reference pinned), `GET /history`, Comparison COMPAT_READ set.

## FE-3. AUTHORITATIVE POST-WAVE-F GATE (measured by this batch, sole baseline going forward)

```
python tests/run_studio_tests.py --fake
  python             run=2010  fail=0    error=0    skip=0
  node-unit          run=21    fail=0    error=0    skip=0
  fake-playwright    PASS      (npm wrapper aggregate run=1)
npx playwright test --config=playwright.fake.config.mjs --reporter=line
  211 passed (4.1m)  / 211   (first attempt; NO flake occurrence this batch)
```

```
POST-WAVE-F BASELINE (2026-08-25): Python 2010 · Node-unit 21 files · Fake Playwright 211
Delta vs FD-1 baseline (1974/21/211): +36 Python = exactly the registered H15 suite;
Node ±0; Fake ±0. No unexplained drift.
```

## FE-4. H15 SUITE REGISTRATION DISPOSITION

All 36 tests audited individually: **33 UNIQUE_MEANINGFUL, 3 DUPLICATE_BUT_USEFUL** (`test_run_stays_410_comparison_retired` overlaps the H14 pin; `test_all_seventeen_comparison_routes_registered` overlaps `test_routes_registered` pins; `test_profile_list_contains_seeded_profile` partially subsumed by its sibling's ten-route check), **0 DUPLICATE_REDUNDANT, 0 STALE/WRONG**. Every test pins live post-F product/API behavior (response codes, zero mutation, route survival, protected seams, live-family exclusions) — none pins an obsolete source-string detail as its sole purpose. **All 36 registered unchanged** in `tests/run_studio_tests.py`, placed immediately after `tests.test_h14_wave_e_retirement` (same stub-server harness; same "loads `__init__.py` in-process after the Workflows block" ordering constraint — not an arbitrary placement).

Ordering/isolation proof: (A) H15 alone 36/36 OK · (B) predecessor H14+H15 = 63 OK · (C) H15+successor presets suites = 54 OK · (D) routes_registered+f8+h14+h15 = 165 OK · reverse probe H15→f8 = 77 OK. No global-state contamination introduced or found; the known historical F8/workflow reverse-order artifact is unrelated to this insertion point and remains G debt.

## FE-5. EXACT PYTHON COUNT LEDGER

```
  1974   starting registered baseline (FD-1, confirmed current pre-registration tree)
  + 36   newly registered: tests.test_h15_wave_f_server_freeze (all 36 kept)
  +  0   new tests elsewhere (H16 contract already fully covered by registered
         test_studio_backend pins — row absent, label absent, fetch absent,
         Snapshots/Presets/Deploy/Open-Backend preserved; no duplicate H16
         suite created, no combined assertion was missing)
  -  0   removed (no redundant pruning warranted)
  = 2010 FINAL  (independently proven: build_python_suite().countTestCases() == 2010
                 AND full-gate python lane run=2010 fail=0 error=0 skip=0)
```

## FE-6. FD-23 COVERAGE MAP — ALL 21 ROWS ACCOUNTED (summary)

1 Comparison mutations 409+zero-writes → H15 `ComparisonWriteFreezeTests` (registered) ✅ · 2 Comparison reads → H15 `ComparisonReadCompatTests` ✅ · 3 `/comparison/run` 410 → H15 + H14 pin ✅ · 4 Experiment retired 410/409 + REGISTRY snapshot equality → H15 `ExperimentRetirementTests` ✅ · 5 `/studio/experiment` cannot execute → H15 `StudioExperimentRetirementTests` ✅ · 6 experiment-v2 live → H15 + modern-experiment suite (104-test cohort green) ✅ · 7 detail unchanged → H15 `ProtectedSingleSeamTests` ✅ · 8 stop-now unchanged → H15 ✅ · 9 warmup cannot execute → H15 `WarmupFreezeTests` ✅ · 10 V2 uses `run_prompt_stream` → H15 census + transport pin ✅ · 11 run-history reads → H15 `LiveFamiliesRegressionTests` + fake specs ✅ · 12 annotations/save still write → same registered test (mutation proven) ✅ · 13 Backend/Runtime Presets writable → H15 CRUD + fake preset/wizard specs ✅ · 14 Workflow Presets unaffected → H15 + workflow suites ✅ · 15 Backends row absent + GET shim → H16 registered pins (`test_studio_backend.py:392–464`) + H15 GET-shim test ✅ · 16 auth/setup inert → H15 tripwired test ✅ · 17 byte-identical stores under retired writes → H15 hash sweeps (comparison store, experiments root, warmup file, `.presets/`, `.studio_backends.json`, `modal.toml`) ✅ · 18 fake mirror parity → H15 static parity test + runtime spec G5 (410 + harness-only seed endpoint) ✅ · 19 H12 V2-only green → direct-run this batch: `test_phase8_execution_mode` 41/41 + `test_h12_v2_only_consolidation` 21/21 (registration itself remains G debt; adequate surviving V2-only protection exists in-gate via H12-era guards + H15) ✅ · 20 H13 recent-runs green → fake-lane specs incl. `studio-fake-recent-runs-history-v2.spec.mjs` inside 211/211 + node units ✅ · 21 H14 retirement suite green → registered, 27/27 ✅.

## FE-7. REMAINING WAVE-G DEBT (re-measured 2026-08-25; NOT fixed by this batch)

- Out-of-gate stale pins STILL FAILING: tracker-membership ×5 (`test_task3_progress_annotations`, re-measured FAILED failures=5) · Production summary-label pin + output-savefolder literal pin (`test_modal_workspace_ui_ast.ModalProductionUiAstTests`, re-measured FAILED failures=2).
- Unregistered suites (all re-run GREEN directly this batch; registration stays G-owned): `test_phase8_execution_mode` 41/41 · `test_h12_v2_only_consolidation` 21/21 · Node `studio_backend_operations_unit.mjs` (H6) PASS · Node `studio_model_library_parity_unit.mjs` (H7) PASS · Node `studio_legacy_settings_authority_unit.mjs` ALL PASS (currently executes without pinning dead UI; MIGRATE-THEN-REGISTER disposition unchanged).
- Historical F8/workflow reverse-order isolation artifact: unchanged, unrelated to the new registration point.
- Dirty `comfyapp.py`: BOM bytes still present BUT previously-noted environmental failures RE-MEASURED GREEN this batch (`test_comfyapp_ast` 1/1 OK, `test_comfyapp_packaging` 14/14 OK) — recorded as resolved-in-current-tree, G re-verifies at cleanup.
- Dead residue deletion (per FD-25): `_execute_comparison_profile`, dead helpers, warmup code bodies, retired-route code, dead frontend exports (`getBackends`/`getCompareBackends` etc.), remaining Settings Runtime-&-Backend rows reconciliation, broad registration cleanup.

## FE-8. WAVE-F COMPLETION VERDICT

**`WAVE F COMPLETE.`**

H15+H16 coexist with zero conflicts; no protected route was over-frozen (protected Single seams, run-history COMPAT_WRITE pair, presets authorities, experiment-v2, History V2, canvas chain all proven live); every intended retired writer/executor is inert with the exact FD-17 response classes; the H15 compatibility suite is registered in the authoritative gate; all 21 FD-23 rows have authoritative coverage; the combined full gate is green (2010/21/wrapper-green) and the exact fake run is green (211/211, first attempt, flake count this batch = 0); the count ledger reconciles exactly (+36 = 2010). Known-flake note: the H5D wrapper timing flake did NOT recur; no timeout/assertion was weakened.

Deploy / live / GPU / generation / commit / push by this follow-up: **NONE**.

---

# H5 FOLLOW-UP F — POST-WAVE-G DELETION CONVERGENCE & TEST AUTHORITY (APPENDED 2026-08-25)

**Batch type:** H20 = Wave-G test consolidation / post-H18+H19 convergence / authoritative gate. Ran AFTER both Wave-G implementation writers (H18 frontend deletion, H19 execution-Python deletion); no concurrent production writer. No deploy, no Modal invocation, no GPU/live generation, no commit/push/branch/worktree/reset/stash/clean. Files modified by this batch: **this appendix** + `PHASE_H20_WAVE_G_TEST_CONSOLIDATION_AND_POST_DELETION_CONVERGENCE_2026-08-25.md` (evidence detail; this appendix is authoritative) + test files/runner listed in FF-3. Zero production code modified.
**Inputs read completely:** this contract incl. Follow-Ups A–E, H15, H17, H18, H19; H12/H13/H14 invariants where referenced by surviving tests.

## FF-1. H18∩H19 CONVERGENCE + PRE-H20 BASELINE

COEXIST — conflict found: NONE. All nine H18-deleted frontend files absent; `modal-settings.js` = 115-line minimal compatibility module; dead API helpers gone; `updateRunAnnotation`/`saveRunOutput`/`getStudioRunStatus`/`stopExperiment` survive; five-page shell + alias map intact; Comparison UI unreachable. All eight H19-deleted symbols have zero production def/class; `V2ExperimentInvoker`/`CheckpointStreamInvoker`/V2 `ModalTransport`/`run_prompt_stream` retained; H15 freeze-code census exact.

**Pre-H20 combined gate (measured): Python 1824 · Node 21 · Fake 211 — exactly 2010 −148 −38. No drift.**

## FF-2. AUTHORITATIVE POST-H20 GATE

```
python tests/run_studio_tests.py --fake
  python             run=2124  fail=0    error=0    skip=0
  node-unit          run=25    fail=0    error=0    skip=0
  fake-playwright    PASS      (wrapper aggregate)
npx playwright test --config=playwright.fake.config.mjs --reporter=line
  211 passed / 211   (direct exact count; green in all three direct runs this batch)
```
Gate run twice end-to-end (isolation changes landed). One wrapper-aggregate fake flake occurred on the second run (known parallel-load family, unchanged since FD-1); the immediate direct run and a bounded repeat were both 211/211 green. No assertion or timeout weakened.

```
POST-WAVE-G TEST-AUTHORITY BASELINE (2026-08-25): Python 2124 · Node-unit 25 files · Fake Playwright 211
```

## FF-3. REGISTRATION DECISIONS + COUNT LEDGER

Registered (Python): `test_phase8_execution_mode` (+41) · `test_h12_v2_only_consolidation` (+21, after Workflows block — stub-server harness constraint) · `test_studio_progress_annotations` (+71; renamed from `test_task3_progress_annotations`) · run-history authority family `test_run_history` + `test_task2_run_history_extensions` + `test_run_history_save` (+143; resolves the H5 §27 registration debt) · `test_modal_workspace_ui_ast` (+24; formerly-stale pins truthfully green post-H18). Registered (Node): `studio_backend_operations_unit.mjs` (H6) · `studio_model_library_parity_unit.mjs` (H7) · `studio_settings_compat_authority_unit.mjs` (renamed from `studio_legacy_settings_authority_unit.mjs`; MIGRATE-THEN-REGISTER debt RESOLVED via Option B) · `studio_phase_e4d_original_retry_unit.mjs`.

```
1824  pre-H20 combined baseline
 +41  phase8_execution_mode
 +21  h12_v2_only_consolidation
 +71  studio_progress_annotations (78 → 71: retired scoped-tracker premise deleted,
      stale wiring assertions re-pointed at the run-controller owner)
+143  run-history family
 +24  modal_workspace_ui_ast
 - 0  registered-suite deletions (image-packaging file was never registered)
= 2124 FINAL   (build_python_suite().countTestCases() == 2124 AND full-gate lane proof)

Node: 21 → 24 (H6 ops, H7 parity, settings-compat) → 25 (+ E4D retry). Fake: ±0.
```

Deleted test files: `tests/test_image_packaging_refactor.py` (DELETE_STALE — every pinned symbol absent at HEAD **and** worktree; its BOM setUpClass error had masked 37 latent failures; docstring debt item superseded by deletion). Deleted stale class: `PerInvocationMaterializationTests` from unregistered `tests/test_experiment_runner.py` (pins four comfyapp helpers absent at HEAD); suite now 73/73 green.

## FF-4. TRACKER-MEMBERSHIP ×5 VERDICT

All five = **TEST STALE (Class B)** — no product regression. The Playground no longer imports/subscribes to `comfymodal-progress.js`; progress is owned by `createPlaygroundRunController` (`studio-playground-run.js`, covered in-gate by `studio_playground_run_unit.mjs` + fake specs) with `_startPolling` fallback; the global shared tracker belongs to the canvas (`modal-node.js`). The failing assertions targeted the pre-Wave-D wiring. Fixed by re-pointing: new `PlaygroundProgressWiringTests` pins controller import/lifecycle/state-fields/no-global-subscription/polling-fallback; obsolete `PlaygroundUsesScopedTrackerTests` deleted. File renamed `test_studio_progress_annotations.py`, registered, 71/71 GREEN.

## FF-5. STALE AST / DOCSTRING / COMFYAPP RESOLUTION

- `test_modal_workspace_ui_ast`: 24/24 GREEN (retired-UI pins resolved by H18's deletion itself) → REGISTERED; no stale-pin label remains anywhere.
- Image-packaging: file DELETED (FF-3); docstring item closed by deletion with HEAD-evidence.
- Dirty comfyapp status: BOM present at HEAD **and** worktree (permanent property, not transient dirt). `test_comfyapp_ast` 1/1 and `test_comfyapp_packaging` 14/14 GREEN → removed from active debt. Remaining dirty-comfyapp-dependent failures elsewhere (`test_v2_16_20_patch`, audit-round labels) are pre-existing out-of-gate observations, not Studio-gate items.
- F8/workflow reverse-order artifact: REPRODUCED (f8→workflow fails `test_05_v2_handler_path`) and FIXED as **TEST_FIXTURE_LEAK ×2**: (1) un-restored `modal_client._current_gpu` write in `F8PlanFreezeTests` → addCleanup restore; (2) stub-server harness leaves fake `server` module in sys.modules, silently enabling the `history_v2_writer` singleton → `WorkflowRunIntegrationTests.setUp` now pins `set_writer_enabled(False)` explicitly (declared environment, no magic order). Matrix A/B/C/D/E all green post-fix.

## FF-6. CURRENT AUTHORITATIVE COVERAGE MATRIX (all rows registered)

Shell five-pages/aliases/single-sidebar → workspace_ui_ast + shell_integration + h14 · Playground Single-V2/presets/protected seams/run-history COMPAT_WRITE → direct_run + f8 + h15 + backend presets CRUD + playground units · Experiments modern/legacy-inert/seams → h15 + history_v2_modern_experiment + routes_registered · History V2 sole-authority/replay/favorite/note/export/irreproducibility → history_v2_* suites + e4c/e4d/F6/F3 units · Workflows immutable Version/Mapping/Workflow Presets/Model Library/Compatibility/Portability → workflow_domain/routes/metadata/run_integration + model_library* + portability* + H7 unit · Backend workspaces/deployment/readiness/credentials/Backend Presets/snapshots/repair → backend suites + H6 unit · Settings preferences-only/GPU/output authority/no old mode/no legacy UI → f8 + f4 unit + settings-compat unit + gpu_config pins + testing_settings_js · Canvas `/prompt`/pass-through/Production/output-options → phase8/h12 structural + workspace_ui_ast + modal-node pins · API freeze 409/410 matrix + byte-integrity → h15 hash sweeps · Execution V2-only/recognition-rejection-migration/ModalTransport→run_prompt_stream → phase8 + h12 + h14/h15 census pins.

## FF-7. REMAINING UNREGISTERED TEST DISPOSITIONS (zero "meaningful-but-unregistered")

NON_STUDIO (V2/runtime/Modal/deploy infra, ~200 modules incl. all `test_v2_*`, `test_runtime_*`, benchmarks, v2ctl): out of Studio gate scope by runner charter. KEEP_FOCUSED_ONLY: `test_experiment_runner` (73 green; legacy-scheduler-chain + CheckpointStreamInvoker units), `test_canonical_execution`, `test_run_prompt_options`, `test_warmup_profile_dedup`, `test_restore_timing_data_flow`, `test_production_*` family, `test_comfyapp_ast/packaging` (deploy infra), `test_workstream_e_patches` (worker-progress buffer units + retirement contract duplicated in-gate), `test_modal_settings_gpu_config` (REDUNDANT — same contract now behaviorally pinned by registered settings-compat + F8 units), `test_studio_workflow_manifest` + `test_studio_workflow_run_plan_identity` (identity matrix duplicated by registered workflow-run-integration + F8 freeze tests; one stale selected_gpu expectation fixed this batch), `test_history_index` (covered via registered run-history family), `test_experiment_modern_*`/`store`/`models`/`scheduler`/`setup_adapter`/`lease` (modern-experiment units; end-to-end authority covered in-gate by history_v2_modern_experiment + routes_registered). Browser `.mjs` harnesses under tests/browser are fake-lane/runtime internals. No UNKNOWN.

## FF-8. REMAINING WAVE-G PRODUCTION RESIDUE MAP (UNKNOWN = 0; nothing deleted by this batch)

| Item | Class |
|---|---|
| `_schedule_and_start` + legacy ExperimentScheduler/Runner chain | KEEP_MODERN (pinned seam; sole construction site of mandated V2ExperimentInvoker) |
| `V2ExperimentInvoker` | KEEP_MODERN (mandated survivor; only registered invoker) |
| `handle_studio_experiment` | DELETE_HELPER (zero production callers; route 410-inert before handler; still test-seam for h12 rejection pin — migrate test first) |
| `build_single_run_spec` | DELETE_HELPER (production-orphaned; de-pin registered compilation suites first) |
| `__init__._collect_input_images` | DELETE_HELPER (migrate to canonical_execution twin) |
| `createScopedTracker` export (NEW finding) | DELETE_HELPER candidate (zero production consumers; browser-harness-only) |
| RunTrace.MARK_OPTIONAL legacy span names | KEEP_COMPAT (trace-data vocabulary) |
| Registered-and-inert Comparison/Experiment/warmup/auth/presets/backends routes | ROUTE_PRUNE_CANDIDATE (see FF-9) |

## FF-9. ROUTE-PRUNING NECESSITY VERDICT

**NOT needed for correctness. Recommendation: KEEP_INERT_COMPAT for every retired route family during Phase H; DEFER_FUTURE_MAJOR for any physical pruning.** Basis: all retired writers/executors answer bounded truthful 409/410 with hash-proven zero mutation; registry pins valid; COMPAT_READ families retain stored-data reader value for old records/tools; fake mirrors exist only where live families require them (plus the intentional `/studio/experiment` parity mirror); the security/maintenance downside of inert shims is negligible versus the same-change pin/mirror/spec cascade physical deletion would trigger across ~40 routes. DELETE_IN_G: none required.

## FF-10. PHASE-H CLOSURE BLOCKER CHECK

**BLOCKS_H_CLOSURE: NONE.** No architectural duplication or dead authority violating Phase-H goals remains: single V2 engine enforced and pinned; Settings owns preferences only (authority singular); History V2 is sole durable History; Comparison UI retired with hidden compat reads intact; five-page shell stable; every §28 must-preserve invariant has registered coverage (FF-6).
**OPTIONAL_G_HYGIENE (non-blocking):** physical route pruning (FF-9); deferred-helper deletions with coordinated test migrations (FF-8); remaining Settings Runtime-&-Backend display rows (Deploy state/Snapshots/Presets counts — read-only consumers of live authorities; Backends row already removed by H16); harmless compatibility naming.
**PHASE_I:** A/B slider and the frozen §29 deferral list.

**WAVE G TEST CONSOLIDATION COMPLETE.**
Deploy / live / GPU / generation / commit / push by this follow-up: **NONE**.

---

# H5 FOLLOW-UP G — PHASE-H FINAL CLOSURE (APPENDED 2026-08-25)

**Batch type:** H21 = final Phase-H closure / independent verification / reconciliation only. READ-ONLY against production code and tests; no route pruned, no helper deleted, no shim removed, no Phase-I work started, no deploy/Modal/GPU/live generation/commit/push/branch/worktree/reset. Files modified by this batch: **this appendix**, `PHASE_H_FINAL_CLOSURE_2026-08-25.md`, `PHASE_H_FINAL_CLOSURE_ZERO_CONTEXT_HANDOFF_2026-08-25.md`. This appendix carries ONLY closure-level authoritative statements; full detail lives in the two closure documents.

## FG-1. FINAL GATE (authoritative closure measurement)

```
python tests/run_studio_tests.py --fake
  python             run=2124  fail=0    error=0    skip=0
  node-unit          run=25    fail=0    error=0    skip=0
  fake-playwright    PASS      (wrapper aggregate)
npx playwright test --config=playwright.fake.config.mjs --reporter=line
  211 passed / 211   (direct exact count; one known-flake occurrence on the first
                      direct run — studio-fake-lifecycle test 11 parallel-load
                      timeout — immediate direct rerun green; nothing weakened)
```

`PHASE_H_FINAL_GATE = Python 2124 · Node-unit 25 · Fake Playwright 211 exact.`

## FG-2. PHASE-H COMPLETION

**`PHASE H COMPLETE`.** All seven waves (A–G) reconciled to a completion ledger with no wave "mostly complete"; every §28 must-preserve invariant plus inherited F/G invariants carries registered coverage and ends PASS (zero UNKNOWN, zero unaccounted); no architectural duplication remains; no meaningful deterministic Studio suite remains simply unregistered (re-proven: ZERO); remaining hygiene explicitly non-blocking.

## FG-3. ROUTE PRUNING NOT REQUIRED

Re-verified against FF-9 factors on the closure tree: **`PHASE_H_ROUTE_PRUNING_REQUIRED = NO`.** KEEP_INERT_COMPAT stands for every retired route family; physical pruning is DEFER_FUTURE_MAJOR. No routes were deleted in H21.

## FG-4. OPTIONAL HYGIENE NON-BLOCKING

FF-8 residue (`handle_studio_experiment`, `build_single_run_spec`, `__init__._collect_input_images`, `createScopedTracker`, MARK_OPTIONAL span vocabulary, inert compatibility routes, residual Settings Runtime-&-Backend informational rows, `_schedule_and_start` chain) re-measured and frozen as OPTIONAL_DELETE / KEEP_COMPAT / FUTURE_MAJOR_API / FUTURE_ARCH_DECISION / OPTIONAL_G_HYGIENE respectively. None blocks closure or Phase I.

## FG-5. PHASE-I BOUNDARY

The §29 deferral list stands unchanged (A/B slider, nav/a11y polish, responsive nav, heading hierarchy, generic loading, chip taxonomy, wording polish, URL/deep-link routing, focus-visible, cross-tab sync, deeper entry links). Distinctions frozen: PHASE_I_PRODUCT_WORK vs OPTIONAL_G_HYGIENE vs FUTURE_MAJOR_API. Nothing from Phase I was implemented in H21.

## FG-6. ZERO-CONTEXT HANDOFF PATH

The exhaustive handoff for any fresh agent is **`PHASE_H_FINAL_CLOSURE_ZERO_CONTEXT_HANDOFF_2026-08-25.md`** (sections A–Z: purpose, inherited context, batch ledger, final architectures, route tables, deletions, test architecture, flakes, hygiene, Phase-I roadmap, consolidated do-not-break invariants, validation conventions, transitional seams, next safe starting point). The concise human status record is `PHASE_H_FINAL_CLOSURE_2026-08-25.md`.

Deploy / live / GPU / generation / commit / push by this follow-up: **NONE**.
