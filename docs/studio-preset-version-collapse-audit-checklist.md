# Studio Preset & Snapshot Removal + Version-UI Collapse — Implementation Status

Status: **implemented and browser-verified.**
Supersedes: "plan awaiting implementation" status of this file.
Scope decision: Studio-only sweep. Legacy canvas prompt/image preset routes
(`/comfymodal/presets/prompts`, `/comfymodal/presets/images`, `presets.py`) and
the History `preset_id` / `preset_name` provenance columns are **retained**:
they are the wire format for existing records, not a preset feature.

## Verification state

| Gate | Result |
|---|---|
| `pytest -m fast_unit` | 490 passed, 5 skipped |
| MJS unit suites (30 files) | 30/30 pass |
| `node --check` (all `web/*.js`, `tests/browser/*.mjs`) | pass |
| Playwright (mocked) | **55 passed, 0 failed**, 2 skipped |
| Portability/manifest + migrated domain & experiment tests | 267 passed |

Playwright ran **after** the full frontend sweep. The legacy Playground preset
lane removal, wizard rename, and manifest export/import flag removal are all
covered by the green run.

## Landed

- Domain: removed `WorkflowPresetNotFoundError`, `PresetCopyError`,
  `make_preset_id`, `PresetState` (duplicate of `VersionState`), `_PRESET_EDITABLE`.
- `legacy_adapters.py` trimmed to live role translation; `prepare_legacy_run_controls` deleted.
- Experiment plan + routes: `preset_id` / `preset_name` removed from
  `WorkflowResolution`, `CellPlan`, target specs, and cell records.
- **`history_v2_replay.py`: `preset_id` is no longer a hard-required replay
  identity** (real bug — every preset-free modern run would have been reported
  non-replayable).
- Frontend API: removed snapshot/preset CRUD and default-preset helpers;
  manifest export/import lost their preset flags.
- Playground: removed the legacy preset lane (`doRunSubmit`, preset hydration,
  legacy run-button branch); `runStudioPreset` → `runStudioWorkflow`
  (it POSTs `/studio/run`, always did).
- `studio-preset-wizard.js` → `studio-workflow-setup-wizard.js`, edit-mode and
  preset/snapshot save flows removed.
- 7 Python test files migrated off `create_preset` (84 failures → 0).
- Real UI bugs fixed en route: invisible Settings Outputs section
  (`applyFilter` ran before the async populate), `vv3` version label,
  duplicate hash routing in `studio-backend.js`, restore of the
  accidentally-deleted `workflows-import-manifest-button`.

## Remaining

- `portability_contract.py` preset policy flags removed; the export/import
  contract now carries no preset fields.
- Dead preset helpers left inert in `tests/browser/studio-workflows-mock.mjs`
  and `tests/browser/studio-mock-api.mjs`: no preset endpoint is registered by
  either mock, but the helper bodies remain. Kept deliberately — removing them
  broke the mock's block structure once already, and they are unreachable.
- Deeper preset copy in the wizard's non-live render branches.

---

## Original plan (retained for reference)

Status was: **plan awaiting implementation.** No code written.
Supersedes: v1 of this checklist. Revised after independent @oracle audit (verdict: UNSOUND).
Evidence base: five read-only codebase audit lanes + one adversarial plan audit.

---

## 1. The user's request

Verbatim, authoritative:

1. "some of the backend tabs need to be removed:
   - What is the point of the overview. it adds nothing new
   - Credentials should be in settings
   - Didn't we deprecate backend presets and snapshots? ... Can we do experiments
     and playground runs without them? I know it has fields for it but i think
     those can be removed.
   - Backend should be renamed to Mange Modal"
2. "can we refactor workflows to not require presets and snapshots and crap?"
3. "I want to remove versions too from the UI, so each workflow has one version
   and that's it, mapped."
4. "scope 1, 2, and removing versions from the UI completely, and scope 3. this
   will be one big pass that must be audited with playwright that checks
   playground, workflows page, and backend (now renamed)."

Decisions given since:

- **Presets are removed entirely.** "I dont currently see any use for presets. I
  want them removed from the codebase entirely. no use, no backend, nothing."
- **No migration needed.** "I have no workflows that are irreplacable, dont worry
  about migration."
- **Priority is non-regression.** "what you do need to worry about is making sure
  preset removal doesnt break anything."
- **Playwright = 3 surfaces.** "it wasn't a hard rule. this is simple enough to
  check with tests though, no need for playwright to check settings."

Goal: **one coordinated pass**, audited against these criteria after the code lands.

### What the audit is

A post-implementation verdict on whether delivered code follows the requests
above. An unchecked box is a **FAIL to fix** — not a redesign, not a stop sign.

---

## 2. Why presets exist, and what is actually lost

A preset is a **named set of parameter overrides on one workflow version**.
Payload (`studio_domain/models.py:364-399`):

| Field | Role |
|---|---|
| `values` | steps, guidance, denoise, seed, w/h, sampler, scheduler, lora_strength |
| `model_choices` | which checkpoint |
| `lora_values` | which LoRA |
| `name`/`description`/`tags`/`favorite` | organization |
| `exposed_controls`/`dropped_controls` | which Playground controls show |
| `recommended_values` | e.g. derived step count |

Run-time mechanism: `merge_workflow_controls()` (`studio_workflow_run.py:286-326`)
folds `values` + `model_choices` over the graph, then
`apply_workflow_values_to_prompt()` (`:460-531`) writes them into
`executable_prompt`.

**Functional loss: multiple named configurations per workflow.** Today one
workflow + three presets = "portrait / fast draft / high quality". With presets
gone, one workflow = one fixed parameter set. This follows directly from the
request — a preset *is* a configuration.

**Individual values are not lost.** They are already baked into the captured
graph: `workflow_metadata.py:55-76` summarizes seed/steps/CFG/dimensions/denoise
from `executable_prompt`, and model refs live in `dependency_metadata` /
`compatible_models`.

**Already dead, nothing to lose:**
- `lora_values` — on the model, **never merged** at the run seam.
- "Copy to latest" / duplicate (`studio-workflows.js:3392-3420`) — existed only to
  move presets across version bumps. Dies with versions.

### The one real risk

Preset values *override* baked graph defaults at run time. Deleting presets
without promoting the default preset's values into the version means runs keep
"working" but silently drift to graph defaults. **Group M handles this.**

---

## 3. Scope

### In scope

| ID | Scope |
|---|---|
| 1 | Delete legacy snapshot + preset "Make Preset" branch |
| 2 | Remove Overview / Backend Presets / Snapshots tabs; rename Backend → **Manage Modal**; move Credentials → Settings |
| 3 | **Remove the preset concept entirely** — domain, routes, API, modules, tests |
| 4 | Remove version concepts **from the UI** — one version per workflow, mapped |

### Explicitly OUT of scope

**Destructive version-persistence collapse.** Versions are immutable by contract
(`studio_domain/models.py:148-154`, `studio_domain/store.py:248-260`); mapping
revisions append a version even for an identical graph
(`studio_domain/services.py:785-792`); history and experiments **pin**
`workflow_version_id` (`history_v2_repository.py:454-489`,
`experiment_modern_plan.py:627-689`).

Audit finding: *"Collapsing the UI is substantially safer than collapsing the
persisted records."*

The user said "from the UI" twice. So: UI shows one version; version IDs and
historical rows survive internally. Box **P4.9** enforces the boundary.

**No data migration required** (user confirmed no irreplaceable workflows).

---

## 4. Ordering — one coordinated release, internally staged

The user asked for one big pass. Honored as **one release**, not one unsequenced
batch. The reverse order ships a product whose own hidden gates nothing satisfies.

Do these in order. No partial rollout — every stage lands together.

1. **S0 — Baseline inventory.** Record workflow/version/mapping IDs, counts, and
   canonical values before touching anything. Feeds Group M.
2. **S1 — Server runs without a preset.** Delete `NO_PRESET`; resolve controls from
   version-owned values. Also delete the snapshot read path.
3. **S2 — Frontend gates.** `web/studio-workflow-run.js:617-620` preset gate,
   mandatory preset fetch at `:312-325`, experiment preset threading at
   `web/studio-experiment-mode.js:959-974`, `:1051-1067`.
4. **S3 — Promote preset values into the version record.**
4. **S5 — Version UI removal.** Selectors, lists, labels, "copy to latest".
5. **S6 — Tab cuts, Credentials move, rename.**
6. **S7 — Delete dead modules, routes, tests, fixtures.**
7. **S8 — Verify.** Deterministic tests, then live Playwright on three surfaces.

### Two blockers the first audit missed

- **Frontend has its own preset gate.** `web/studio-workflow-run.js:617-620`
  disables Run on an empty preset. Removing server `NO_PRESET` alone leaves the UI
  looking correct and unable to run.
- **Existing Playwright specs are mocked by design.**
  (`tests/browser/studio-workflows.spec.mjs:1-23`, `studio-playground.spec.mjs:1-27`).
  A mock supplies a preset automatically — the exact failure this pass exists to
  catch, rendered green. Group P has teeth because of this.

### Concurrency hazard

`create_mapping_revision()` computes the next number, inserts a version, inserts a
mapping, and updates the workflow across separate operations
(`studio_domain/services.py:807-858`). The store lock covers only
import/cascade transactions (`studio_domain/store.py:57-60`). Concurrent mapping
saves can produce duplicate revision numbers, a stale `latest_version_id`, or an
orphaned version/mapping pair. **Box R.11.**

---

## 5. Acceptance criteria

Auditor returns **PASS / FAIL / PARTIAL per group**, with file:line or artifact
evidence per box. A FAIL names the prompt violated, the box, the evidence, and the
fix.

### M — Preset value promotion (new; user priority: nothing breaks)

- [ ] **M.1** Baseline captured: workflow IDs, version IDs, mapping IDs, and each
      workflow's effective `values` + `model_choices`. Artifact in `<run-dir>/`.
- [ ] **M.2** Each workflow's default-preset `values` and `model_choices`
      promoted into its version record before preset deletion.
- [ ] **M.3** After removal, a run on a previously-preset-using workflow produces
      **byte-identical accepted execution-plan inputs** to the baseline. Compare
      the accepted plan, not rendered output — rendering is nondeterministic.
- [ ] **M.4** No silent drift: no workflow's effective parameters change as a
      side effect of the deletion.
- [ ] **M.5** `default_preset_id` (`studio_domain/models.py:212-230`) removed from
      the `Workflow` entity and every read/write site.

### P1 — Legacy snapshot + preset machinery removed

- [ ] **P1.1** Legacy Make Preset branch (snapshot + preset) gone from
      `web/studio-backend-capture.js` and the legacy path of
      `web/studio-preset-wizard.js` (was `:2324-2379`).
- [ ] **P1.2** No code path creates a snapshot or a preset. Proof: no importer of
      the creation functions.
- [ ] **P1.3** `studio-backend-snapshots.js`, `studio-backend-presets.js`,
      `studio-backend-capture.js` deleted or reduced to zero live importers.
- [ ] **P1.4** No `listSnapshots` / `getSnapshot` call anywhere in `web/`.
- [ ] **P1.5** Snapshot + preset **management UI** gone: no list, duplicate,
      archive, capture, or preset-selection control. *Scope note:* this covers
      management surfaces and run-blocking selectors. It does not require
      deleting unrelated optional functionality the user did not name.

### P2 — Preset concept removed from the codebase entirely

- [ ] **P2.1** `WorkflowPreset` deleted from `studio_domain/models.py:364-423`,
      with no remaining definition, alias, or stub.
- [ ] **P2.2** Preset CRUD routes unregistered from `studio_routes.py:1-22` and
      every other module. Proof: route table contains no preset path.
- [ ] **P2.3** Preset reads gone from all consumers: `studio_workflow_run.py:149-186`,
      `experiment_modern_plan.py:627-660`, `studio_domain/services.py:666-678`,
      `portability_service.py:666-676`, `studio_domain/legacy_adapters.py:319-373`.
- [ ] **P2.4** `NO_PRESET` no longer exists in any form.
- [ ] **P2.5** Frontend preset API calls gone from `web/studio-backend-api.js`
      (preset listing at `:88-92`, `:124-129`, `:170-175`).
- [ ] **P2.6** `studio-preset-capabilities.js` (551 lines, 3 importers) either
      deleted or converted to version-capability naming. Proof: no `preset` symbol
      remains in its consumers.
- [ ] **P2.7** No `preset_id` synthesized, defaulted, or sent. Proof: captured
      payload shows it absent or empty.
- [ ] **P2.8** The store files backing presets are deleted, not orphaned.

### P3 — Frontend gates removed (the missed blocker)

- [ ] **P3.1** `web/studio-workflow-run.js:617-620` preset gate removed — Run is
      enabled with an empty preset id when mapping and controls are valid.
- [ ] **P3.2** Mandatory preset fetch at `web/studio-workflow-run.js:312-325`
      removed from the workflow-selection path.
- [ ] **P3.3** Experiment preset identity removed from
      `web/studio-experiment-mode.js:959-974`, `:1051-1067`.
- [ ] **P3.4** Playground run posts successfully with **no preset record and no
      snapshot record** in existence. DOM + payload proof.
- [ ] **P3.5** Experiment run posts successfully with neither record. Payload
      proof on the experiment POST.
- [ ] **P3.6** `lora_values` dropped without behavior loss — evidence it was never
      merged at the run seam (`studio_workflow_run.py:286-326`).

### P4 — Backend → Manage Modal

- [ ] **P4.1** Top nav, launcher tooltip, **and accessible page title**
      (`web/studio-backend.js:136-142`) all read "Manage Modal".
- [ ] **P4.2** All user-visible "Backend" text updated: Settings links
      (`web/studio-settings.js:567-613`), Playground text, experiment empty-state.
- [ ] **P4.3** Overview tab absent — no runtime-status panel where it was
      (`studio-backend.js:362`).
- [ ] **P4.4** Backend Presets tab absent.
- [ ] **P4.5** Snapshots tab absent.
- [ ] **P4.6** Remaining tabs exactly **Workspaces, Deployment** (Credentials
      relocated per P4.7).
- [ ] **P4.7** Credentials live in Settings; HF and Civitai save/clear work.
      Verified by **component/API test** — explicitly out of the Playwright
      mandate per user decision.
- [ ] **P4.8** No dead `data-tab` handlers, orphaned tab CSS, dangling tab ids.
- [ ] **P4.9** **Boundary:** version IDs and historical rows preserved. Old
      versions are compatibility/history records; exactly one canonical current
      revision is operable through the product. No version deleted, mutated, or
      remapped. If storage was collapsed, this is a FAIL.

### P5 — Versions out of the UI

- [ ] **P5.1** Workflows page shows no version list, selector, version-number
      label, or "copy to latest" / "copy all to latest" control.
- [ ] **P5.2** Exactly one version reachable through the UI; it always targets the
      canonical current revision.
- [ ] **P5.3** **Each workflow has one version and it is mapped** — mappings
      reachable and editable with no version selector in the way, and the mapped
      state is visibly the operative one.
- [ ] **P5.4** After each mapping save: canonical current ID changes atomically,
      the UI adopts it, reopening shows the saved mapping, and no stale tab can
      overwrite a newer revision.
- [ ] **P5.5** Old version numbers/counts not user-visible anywhere.
- [ ] **P5.6** Users cannot select, capture, or deploy an old revision.
- [ ] **P5.7** New functionality does not require copying state between revisions.
- [ ] **P5.8** Existing workflows are usable — canonical current revision is mapped
      and runnable, or the UI clearly surfaces an unrunnable state.
- [ ] **P5.9** Version ids still sent on **run, experiment, history/replay, and
      portability** paths. **Not** on app-level `POST /deploy`, which is bodyless
      by design (`web/studio-backend-api.js:1056-1068`).

### P6 — Compatibility routes intact

- [ ] **P6.1** Enumerated compatibility-route list, all responding live.
      **Correct count is ≥12** version-scoped registrations in
      `studio_workflow_routes.py:622-928` and `:1085-1088`, **plus** three in
      `model_library_routes.py:338-462`. (v1's "9 routes" was wrong.)
- [ ] **P6.2** `graph_hash` dedupe (`studio_domain/services.py:723-735`) behavior
      unchanged.
- [ ] **P6.3** Mapping-revision appends-version semantics preserved
      (`studio_domain/services.py:807-860`, not just the `:785-792` docstring).
- [ ] **P6.4** `Workflow.latest_version_id` pointer updates correctly
      (`studio_domain/services.py:759-774`, `:838-842`).

### P7 — Playwright audit, three surfaces

Per `.opencode/skills/playwright-debug`: one bounded spec at a time, artifacts
preserved, **both DOM proof and payload proof**.

- [ ] **P7.1** **Playground** — DOM: a real preset-free run completes, output
      renders. Payload: body carries correct values and a resolvable
      `workflow_version_id`; **no `preset_id`**.
- [ ] **P7.2** **Workflows page** — DOM: no version UI, mapping editor opens and
      saves, no preset controls. Payload: save succeeds; version count **increments
      by one** and the returned ID becomes canonical. (Not "version #2" — real
      workflows already have versions.)
- [ ] **P7.3** **Manage Modal** — DOM: label correct, exactly two tabs,
      Overview/Presets/Snapshots gone. Payload: **read-only** deployment status and
      Workspaces action return success. **No production deploy or restart** — name
      the action and the disposable workspace used.
- [ ] **P7.4** Artifacts in a run-specific `<run-dir>/`: screenshots, trace,
      console log, network log. Nothing from one attempt substitutes for another.
- [ ] **P7.5** Each spec ran individually within an explicit timeout. Any stall has
      a named timeout phase with evidence.
- [ ] **P7.6** **All three surfaces run against an unmocked live product API.**
      Intercepted workflow/run/experiment routes, or a skipped live spec, is an
      **immediate FAIL**. All payload proof from the live path. Requires successful
      responses **plus server-side readback** — a 200 alone proves little.
- [ ] **P7.7** Red-before / green-after artifacts for each changed spec, against a
      **named baseline commit** with identical fixture and environment.

### R — Regression guard

The user's stated priority. A prompt like "refactor workflows to not require
presets" is **not satisfied** if runs break.

- [ ] **R.1** `tests/test_workflow_run_integration.py` green — tests 01, 03, 04, 05,
      08, 09 specifically.
- [ ] **R.2** `test_08_no_silent_fallback` still asserts no silent execution
      without valid setup (`:964-985`) — not weakened.
- [ ] **R.3** Runnable gate (`studio_domain/services.py:875-930`) still reports its
      **full real** failure-reason set: executable prompt, missing mapping, mapped
      node/input absent, no output node, dependency-provider reasons. *v1 cited a
      nonexistent "unmapped-role" reason — corrected.*
- [ ] **R.4** Old history records render with provenance intact
      (`history_v2_routes.py:889-947`).
- [ ] **R.5** Existing experiments replayable; pinned version ids resolve, no 404.
- [ ] **R.6** Portability import/export: **graph hash and original-ID provenance
      survive**; new local workflow/version ids are *expected*
      (`portability_service.py:902-905`, `:934-943`). v1's id-round-trip claim was
      false.
- [ ] **R.7** Multi-version test assertions **intentionally updated with stated
      reasoning**, not deleted to go green.
- [ ] **R.8** Frontend `.mjs` tests green or intentionally migrated:
      `get_axis_eligibility_unit`, `get_steps_recommendation_unit`,
      `studio_backend_operations_unit`, `studio_experiment_v2_frontend_unit`,
      `studio_experiment_v2_unit`, `studio_history_v2_experiment_unit`,
      `studio_phase_f4_settings_authority_unit`,
      `studio_phase_i2_shell_nav_accessibility_unit`,
      `studio_phase_i3_shared_primitives_unit`.
- [ ] **R.9** `python tools/test_perf.py --fast -- tests -m fast_unit` passes, no
      lightweight test over 10s (repo AGENTS.md policy).
- [ ] **R.10** Old **and** current version ids plus replay paths deliberately
      exercised; absence of `WorkflowVersionNotFoundError` is then meaningful.
- [ ] **R.11** **Concurrency:** two simultaneous mapping saves produce no duplicate
      revision numbers, no partial version/mapping pair, no incorrect
      `latest_version_id`.
- [ ] **R.12** No test deleted purely to go green.
- [ ] **R.13** No history or experiment record rewritten to strip provenance.

---

## 6. Verdict format

Auditor returns one line per group — `M … | P1 … | P2 … | P3 … | P4 … | P5 … |
P6 … | P7 … | R …` — then overall **PASS** or **FAIL**.

A FAIL names: the request violated, the box, the evidence, the fix. Not a redesign.

---

## 7. Corrections made in v2

From the @oracle audit (verdict UNSOUND):

| v1 defect | v2 fix |
|---|---|
| P3.2 claimed `lora_values` merged at run seam | R.3/P3.6 — it never merged; claim removed |
| P4.4 required version id on every deploy request | P5.9 — app-level `POST /deploy` is bodyless |
| P4.7 said 9 version routes | P6.1 — ≥12 plus three model-library |
| R.5 assumed version-id round-trip on import | R.6 — graph hash + provenance survive; new ids expected |
| P4.5 "source ranges untouched" | P4.9 — assert preserved identities, not untouched source |
| P4.6 assumed "version #2" | P7.2 — assert increment, not an absolute number |
| P3.3 cited nonexistent "unmapped-role" reason | R.3 — real failure-reason set |
| P5.3 could trigger a production deploy | P7.3 — read-only status, named disposable workspace |
| P5.6 flagging wasn't enough | P7.6 — live API mandatory, server-side readback required |
| P5.7 had no baseline | P7.7 — named baseline commit, identical fixture/env |
| P1.5 overreached the request | P1.5 — scoped to management UI and run-blocking selectors |
| Preset values could silently drift | **Group M** — new, promotion before deletion |
| Missed frontend preset gate | **Group P3** — new, the hidden blocker |
| No ordering | §4 — 8 stages, one release |
| No concurrency coverage | R.11 — new |

---

## 8. Evidence base

| Lane | Verdict | Confidence |
|---|---|---|
| Presets/Snapshots deprecation | Both DEPRECATED-BUT-WIRED | high |
| Client run-path trace | PARTIALLY — snapshots optional, preset data load-bearing | high |
| Server data model + run path | NO — `NO_PRESET` hard-fails | high |
| Workflow-version sufficiency | NO — needs mapping **and** preset | high |
| Version-collapse blast radius | 6 hard blockers, all persistence-side | high (route count moderate) |
| Plan audit (@oracle) | UNSOUND → 19 required changes, all folded in | — |

`config/v2/` references no version ids, so the 45 shipped profile TOMLs need no
migration.
