# Plan: Studio Workflow Legacy Absorption

Scope: studio-workflow-legacy-absorption
Depth: tree 2 (leaves plus root-level integration gates; no branch — strictly sequential pipeline)
Mode: orchestrated

## Contract

- Interfaces: abs-1 defines legacy→workflow adapters (legacy preset payloads to workflow preset/run-context shapes; single run contract through workflow run-context plus run route); exact function names documented in code and status log for downstream lanes; WorkflowDomainStore/API remains the single durable authority; no old-data migration.
- Ownership: disjoint sets per leaf below; abs lanes supersede closed scope `studio-workflow-experiment-friction-reduction` for overlapping files (all its leases released, no concurrent writers); abs gates re-verify every touched area.
- Dependencies: abs-1 → abs-2 → abs-3 strictly sequential (later lanes consume abs-1's adapter surface).
- Host launch mode: Claude background Agents through the native task dispatcher.
- Wave policy: single-lane sequential waves 1, 2, 3; maximum 1 concurrent writer.
- Toolchain: Node/npm from `package.json`, Python project environment, Windows PowerShell, repository root as CWD. Playwright mocked bounds 600s explicit; pytest bounds 120-300s.
- Approval-timeout map (binding discipline — every invocation touching a ledger uses its row timeout): abs-1 default (120); abs-2 600; abs-3 600; root 1500.
- Conventions: no second authority; no migration; deletion only with caller proof; publication exclusions stay; no Backend/Preset concepts in user flow at end.
- Manual review: parent reviews adapter surface, UI removal, output placement, and gates.

## Current contract inventory

Contract revision: 1.

| ID | Required outcome or constraint | Owner | Observing gate or manual review | Disposition | Revision |
|---|---|---|---|---|---|
| C1 | Legacy-preset to workflow adapters plus single run contract | abs-1 | leaf-abs-1:G1, G2 | ACTIVE | 1 |
| C2 | Management UI on workflow routes with workflow-scoped counts and cache | abs-2 | leaf-abs-2:G1 | ACTIVE | 1 |
| C3 | No Backend/Preset UI in user flow | abs-2 | leaf-abs-2:G3 | ACTIVE | 1 |
| C4 | Shelf and Experiment run on workflow APIs with output placement preserved | abs-3 | leaf-abs-3:G1 | ACTIVE | 1 |
| C5 | Deletions ship with caller proof; publication exclusions intact | abs-3 | leaf-abs-3:G3 | ACTIVE | 1 |
| C6 | Absorption notes recorded in spec and checklist docs | parent | root:G5 | ACTIVE | 1 |

## State vocabulary

Leaf states: WAITING, READY, IN-FLIGHT, VERIFIED, or ABANDONED.

## Tree

Use this tree only for parent-child topology and ledger paths.

- 1 Studio Workflow Legacy Absorption .............. GATES.md
  - 1.1 Domain adapters ........................... gates/leaf-abs-1.md
  - 1.2 Management UI ............................. gates/leaf-abs-2.md
  - 1.3 Runtime consumers and deletion ............ gates/leaf-abs-3.md

## Leaf dispatch table

| Leaf | Owns | Needs | Tier | Planned wave | State |
|---|---|---|---|---|---|
| abs-1 | `studio_domain/store.py`, `studio_domain/services.py`, `studio_workflow_routes.py`, `studio_workflow_run.py`, `studio_run_adapter.py`, `studio_domain/legacy_adapters.py`, `tests/test_workflow_domain.py`, `tests/test_legacy_preset_adapter_unit.py` | - | judgment | 1 | VERIFIED |
| abs-2 | `web/studio-backend-api.js`, `web/studio-backend.js`, `web/studio-backend-presets.js`, `web/studio-preset-wizard.js`, `web/studio-workflows.js`, `tests/browser/studio-workflows.spec.mjs`, `tests/browser/fake/fake-server.mjs`, `tests/browser/studio-workflows-mock.mjs`, `tests/browser/studio-mock-api.mjs` | abs-1 | judgment | 2 | IN-FLIGHT |
| abs-3 | `web/studio-playground.js`, `web/studio-experiment-mode.js`, `web/studio-workflow-run.js`, `web/studio-settings.js`, `web/studio-shell.js`, `tests/browser/studio-playground.spec.mjs`, `tests/browser/studio-experiment.spec.mjs` | abs-2 | judgment | 3 | WAITING |

## Status log

Append lifecycle events with `node C:\Users\parla\.config\opencode\skills\unlazy\scripts\gate-check.mjs --scope studio-workflow-legacy-absorption --log "event"`.
