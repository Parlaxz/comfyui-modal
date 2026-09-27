# PHASE H16 — WAVE F: SETTINGS BACKENDS CONSUMER REMOVAL (F-BE) — 2026-08-24

Lane: **H-WAVE F / F-BE** (parallel-safe with F-SRV per FD-22; disjoint files).
Contract authority: `PHASE_H5_CONSOLIDATION_CONTRACT_FREEZE_2026-08-23.md` §FD-8,
§FD-18 (exclusions), §FD-22 (file ownership); `PHASE_H5D_WAVE_E_CONVERGENCE_WAVE_F_FREEZE_2026-08-24.md`;
`PHASE_H14_LEGACY_SETTINGS_COMPARISON_RETIREMENT_2026-08-24.md`.

## 1. Pre-change consumer proof

Per FD-8 caller table, verified live before this batch:

| Caller | Route | Status |
|---|---|---|
| `web/studio-settings.js:724` (`refreshRuntimeCounts`, Backends count row) | GET `/studio/backends` | sole LIVE modern consumer |
| `getBackends`/`getCompareBackends` (`studio-backend-api.js:29/:42`) | GET (+`?kind=comparable`) | dead exports, zero callers (Wave G owns deletion) |
| Modern Backend page modules | any | zero consumers |
| fake-server.mjs GET mirror | GET only | compat mirror, untouched |

## 2. Exact row removed

`web/studio-settings.js` — Settings ▸ Advanced ▸ Runtime & Backend group:

- The `backendWrap` control row: label **"Backends"**, value span
  `"data-testid": "settings-runtime-backends"` (former lines 559–565).
- Group-level search metadata updated:
  `"data-search": "runtime backend deploy state snapshots presets backends"` →
  `"... snapshots presets"` (the trailing token belonged to the removed row).

A bounded marker comment records the removal site (FD-8) without reintroducing
the retired label token.

## 3. Exact fetch/state code removed

`refreshRuntimeCounts(base)` (former lines 714–730):

- Removed `const backendEl = sectionsHost.querySelector('[data-testid="settings-runtime-backends"]')`.
- Guard narrowed from `if (!snapEl && !presetEl && !backendEl)` to
  `if (!snapEl && !presetEl)`.
- Removed the third `Promise.all` leg `fetch(base + "/studio/backends")…`.
- Removed `backendData` destructuring and the `if (backendEl) …` count write.

No stale state field and no error handling for that fetch remains; there never
was a dedicated catch beyond the inline `.catch(() => ({}))`, which was part of
the removed leg. Presets fetch, Snapshots fetch, deploy-state fetch, preference
fetches, and Backend page behavior are untouched.

## 4. Proof no replacement built

No Providers / Targets / Modal-workspaces / Compatibility-Backends /
Comparison-Profiles row or any new count was added. No new API helper, no new
route consumer, no portability-target surface (local/modal/runpod/runcomfy/
comfy_cloud/baseten absent from Settings). Diff adds zero fetch calls to
`studio-settings.js`.

## 5. Remaining Runtime & Backend rows (recorded debt, unchanged)

1. Deploy state (`settings-deploy-state`)
2. Snapshots count (`settings-runtime-snapshots`)
3. Presets count (`settings-runtime-presets`)
4. "Open Backend tab" link (`settings-open-backend`, `context.setPage("backend")`)

Group title "Runtime & Backend" retained; whole-group removal stays later debt
per contract.

## 6. `/studio/backends` remaining-reference census (production `web/`)

| Location | Classification |
|---|---|
| `web/studio-backend-api.js:29` (`getBackends`) | dead export — Wave G |
| `web/studio-backend-api.js:42` (`getCompareBackends`) | dead export — Wave G |
| re-export wiring `studio-backend.js` | dead export wiring — Wave G |
| comment-only reference `studio-playground.js` (~:1150) | comment — Wave G |
| `web/studio-settings.js` removal-marker comment | comment only, no code reference |

**Live modern Settings fetch callers: ZERO.** Fake server GET mirror and tests
untouched (not owned). Dead exports intentionally left for Wave G.

## 7. Settings preference preservation

Frozen functionality intact and pinned green: GPU (`settings-gpu`), Preview
default/codec/quality, Outputs (format/quality/webp/auto-save/save-folder/
sidecar/open-folder), History grid columns, Interface panel-layout reset,
Heavy tracing + restart banner, Experiments informational note, Reset-all.
H12 guards hold: no Run mode, no engine selector, no `comfymodal_enabled`
writer/resetter (asserted by existing pins, still passing).

## 8. Test pin updates (owned file only: `tests/test_studio_backend.py`)

- `test_settings_advanced_runtime_backend_group`: testid pin flipped to
  `assertNotIn('"data-testid": "settings-runtime-backends"')`; deploy/snapshots/
  presets/Open-Backend pins kept.
- `test_settings_runtime_group_inventory_rows`: label pin flipped to
  `assertNotIn("Backends")`; Deploy state/Snapshots/Presets pins kept.
- `SettingsCountsTests.test_settings_runtime_counts_referenced`: now proves
  `"/studio/snapshots"` + `"/studio/presets"` present AND
  `assertNotIn('"/studio/backends"')` (no Settings-side fetch).

New assertions prove: row absent, label absent, fetch absent, Snapshots +
Presets counts present, deploy-state row and Open Backend navigation present,
rest of group unchanged. No unrelated backend tests rewritten.

## 9. Focused results

- `tests.test_studio_backend.SettingsContentTests` + `SettingsCountsTests`: **14/14 OK**
- Full `tests.test_studio_backend`: **286/286 OK**
- `tests.test_h14_wave_e_retirement`: **27/27 OK**
- Node unit `studio_phase_f4_settings_authority_unit.mjs`: **PASS**
- Node unit `studio_phase_f8_gpu_reset_unit.mjs`: **PASS**

## 10. Full gate (concurrent H15 truth)

`python tests/run_studio_tests.py --fake`:

```
python          run=1974  fail=0  error=0  skip=0
node-unit       run=21    fail=0  error=0  skip=0
fake-playwright run=1     fail=0  error=0  skip=0
ALL STUDIO LANES GREEN
```

Matches the starting baseline exactly (Python 1974 · Node 21 · Fake lane green;
211 specs inside the single Playwright lane). No failures targeted H15-owned
`__init__.py`/fake-server route regions; this lane edited neither.

## 11. Files modified by THIS lane only

- `web/studio-settings.js` (row + fetch leg + group data-search token)
- `tests/test_studio_backend.py` (three owned pins)
- `PHASE_H16_WAVE_F_SETTINGS_BACKENDS_CONSUMER_REMOVAL_2026-08-24.md` (this report)

Deploy: NONE · Live generation: NONE · GPU/Modal invocation: NONE · Commit/push: NONE · Branch/worktree/reset/revert/stash/clean: NONE
