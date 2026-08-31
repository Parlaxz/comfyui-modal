# SW5 Golden Core Invariant Regression Shield

## Scope

`tests/test_golden_core_invariant_shield.py` is an offline, TEST-ONLY shield.
It does not deploy, call Modal, initialize CUDA, or modify runtime/configuration
source. Existing P1/P2/RA9C tests remain the detailed implementation suites;
this file covers cross-cutting invariants at their public/source boundaries.

## Focused validation

```text
python -m pytest -q tests/test_golden_core_invariant_shield.py
```

The current focused run completed with **24 passed, 2 skipped**. The skips are the nested-symlink
and root-symlink checks when this Windows filesystem does not permit symlink
creation. No combined regression run is claimed here; the parent is the
validation owner.

## Exact shield counts

```text
INVARIANTS_AUDITED: 15
NEW_REGRESSION_ASSERTIONS: 50
CURRENT_CONTRACT_VIOLATIONS_FOUND: 1
```

`NEW_REGRESSION_ASSERTIONS` counts the new source-level `assert` statements
and `with pytest.raises` checks in this shield (a parametrized assertion body
counts once, not once per parameter). `CURRENT_CONTRACT_VIOLATIONS_FOUND`
counts the one observed legacy `modal_app.py` deferred-commit-after-yield
behavior. Strict Golden Serial has **0** current contract violations; the
legacy behavior is reported separately and is not treated as strict Golden
evidence.

The suite exercises:

| # | Checklist invariant | Evidence |
| --- | --- | --- |
| 1 | Golden adapter dispatch | AST proves exactly one `golden_serial_execute` call and no plan/prompt/legacy/generic executor call; the check selects neither QD arm. |
| 2 | Golden Serial stage order | `STAGE_ORDER` exactly matches the current heavy-stage order and VAE load precedes sampling. |
| 3 | Heavy-stage QD boundaries | CLIP, UNET, and VAE each source-check transport quiescence before `end_stage`. |
| 4 | Telemetry interval uniqueness | Overlap and duplicate stage entry are rejected with distinct recorder errors. |
| 5 | UNET adoption | Source requires `load_model_weights(..., assign=True)`, validates binding, and retains the owner; CPU fake validation proves same storage and rejects copies. |
| 6 | Staging ownership | `release_staging` releases slots only, never backing storage; explicit owner close remains idempotent. |
| 7 | Snapshot model surfaces | Active model patcher, QD owner, and open reader fail closed. |
| 8 | Snapshot request surfaces | A live worker/thread and pending asyncio future fail closed, with deterministic cleanup and no worker leak. |
| 9 | Capture exclusion | A second capture re-arms exactly one excluded follow-up, then eligibility returns. |
| 10 | Output SHA policy | `ReadyOutputArtifact` and reopened pending content remain the byte/hash authority; configured expected SHA is tested as a separate enforceable policy outcome. |
| 11 | Durable marker gating | True durability requires a successful commit stage and the private typed reopen proof; a dict-shaped impostor is rejected. |
| 12 | Teardown scope | Golden teardown source has no broad GC, unload, allocator purge, storage release, broad CUDA sync, or model transfer. |
| 13 | Sampling diagnostics | Path-loaded deep profiling defaults/normalizes to off; only explicit `steps`/`blocks` opt in, independently of low-overhead diagnostics. |
| 14 | S4 full generation | A semantic JSON change changes full publication generation while the narrow source-file identity remains unchanged. |
| 15 | S4 root/symlink policy | The source wrapper realpaths only its expected root; root symlink behavior is conditional on host support and inner symlink content is rejected. |

## Existing source observations / follow-up

These are deliberately not patched by SW5. They are reported rather than
hidden by weakening the shield:

1. The legacy `modal_app.py` stream has a deferred commit after its result
   event is yielded. This is the one counted current source observation
   (`CURRENT_CONTRACT_VIOLATIONS_FOUND: 1`), but it is not strict Golden Serial
   and is not used as evidence for the strict durable endpoint.
2. `GoldenQDOwner.release_staging()` only clears slots by design. Its callers
   perform the transport proof before stage return; it is not counted as a
   contradiction because staging release must not clear live backing storage.
3. The multi-checkpoint CLIP failure path must continue to retain every owner
   from transport success through teardown, including when a later checkpoint
   or constructor fails. The current session transaction-owner registry is the
   intended mechanism and should remain covered by the existing P1 tests.

## Non-goals

- No CUDA throughput or Modal cache claim.
- No replacement for P1/P2/RA9C integration coverage.
- No source/configuration fixes, executor redesign, shared pool/dispatcher, or
  history/commit-specific assertions.
- No combined regression result claim; parent validation owns that run.
