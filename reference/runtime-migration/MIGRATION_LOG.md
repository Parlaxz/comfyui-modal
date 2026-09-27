# Migration log

## Phase 0 — reference and truth

- Current HEAD: `fe05aa7eadd06281ca8501a19aa38065fbd5999f`.
- Initial `git status --short`: clean.
- Initial `git diff --stat`: empty.
- Reference copies and hashes are generated under `reference/runtime-migration/`.
- `PORT_MAP.md` was created before implementation and is being filled from the
  read-only symbol verifier.
- The checkout contains no `comfymodal_runtime/` package yet.

### Specialist findings reconciled

- Symbol verifier: every mapped legacy symbol exists; current HEAD equals the
  audit anchor; the new destination modules are absent; `run_prompt_stream` is
  the widest integration seam; `set_active_warmup_profile` has a remote
  definition and a client wrapper.
- Test mapper: the smallest uncovered migration risks are the new output
  strategy chain, remote-authoritative restore publication, Modal lifecycle
  decorators, result materialization, and GPU restore ordering.
- Oracle plan review: approved the fixed architecture after assigning one
  writer per sensitive module, making the contracts-frozen gate measurable,
  splitting Direct/Playground/experiment integration, and adding module-import
  and trace-schema compatibility checks. The protected uncommitted work stays
  in place; no stash/reset/clean operation is used.

### Baseline evidence

See `PERF_RESULTS.md` for the existing three-run artifact, the truthful local
test run, unavailable Modal/Playwright conditions, and the six required
diagnostic answers. No algorithmic extraction is accepted until telemetry makes
backend, output source, Volume writes, and early-UNET state observable.

## Phase 1 — contracts and unified trace

- Added `comfymodal_runtime/contracts.py` with immutable `ExecutionOptions`,
  `ExecutionPlan`, `ModelRestoreKey`, `PrefillKey`, `RestorePlan`,
  `OutputStrategy`, `DeploymentIdentity`, and `TraceEvent` contracts.
- Added `comfymodal_runtime/trace.py` with dual-clock event collection and
  temporary legacy timing serializers/adapters.
- Kept `run_prompt_options.py` as a compatibility adapter backed by the typed
  options parser; existing dictionary shape and `actual_load` behavior remain.
- Added `tests/test_runtime_contracts.py` covering round trips, immutability,
  model/prefill separation, reference trace loading, and dual-clock events.
- Validation: `python -m pytest -q tests/test_runtime_contracts.py tests/test_run_prompt_options.py` — **25 passed**.
- Validation: `python -m py_compile` for the new package, adapter, and focused
  tests — passed.
- Phase review pending Oracle exact-diff check before parallel Phase 2 writers.

## Validation

Pending implementation milestones.
