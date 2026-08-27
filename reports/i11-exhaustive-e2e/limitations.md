# I11 Limitations — Tier-3 and Explicit Out-of-Scope

## TIER3_NOT_RUN_REQUIRES_EXPLICIT_LIVE_AUTHORIZATION

No live Modal/GPU execution was performed in I11. Default per Shared Tree Safety
rules. The following critical claims require explicit user authorization for true
external Modal execution and are therefore NOT counted as fake-tested:

- `T3-MODAL-001` End-to-end Single run through real ModalTransport/run_prompt_stream
  to GPU and back (cold start, sampler, VAE decode timing)
- `T3-MODAL-002` End-to-end Experiment V2 through real Modal scheduler (6-way concurrency)
- `T3-MODAL-003` Canvas /prompt interception against real ComfyUI graph -> Modal V2
  with real model weights
- `T3-MODAL-004` Backend deploy/redeploy against real Modal workspace
- `T3-MODAL-005` History persistence across real server restart (sqlite durability
  under real process lifecycle)

Fake/local integration proves the dispatch boundary, request contract, response
shapes, and UI state transitions, but not GPU inference correctness. Classified
`TIER3_NOT_RUN_REQUIRES_EXPLICIT_LIVE_AUTHORIZATION` per section V.

## OUT_OF_SCOPE_EXPLICIT (intentionally not URL / not synced)

These are frozen Phase-I deferrals per handoffs and are NOT UNKNOWN:

- `ROUTE-014` experiment-kind URL ambiguity (History focus `kind=experiment` not in hash) — I9A deferral
- `ROUTE-015` Workflows focus seam (workflow/version focus not in hash) — Handoff deferral
- `ROUTE-016` Backend focus seam (deployment/workspace focus not in hash) — Handoff deferral
- `ROUTE-017` Settings Outputs hash-focus miss — known I9A defect retained per prompt instruction ("Known deferred Settings outputs hash-focus defect remains classified according to I9A. Do not silently fix")
- `SYNC-012` Route independence (no cross-tab route/hash sync) — intentional per I10 contract (no routing sync)
- `SYNC-013/014` Compare/draft/filter/run-state never sync — intentional per studio-sync.js contract

## RETIRED_UNREACHABLE (proven via negative sweep + Python 409/410)

11 retired UI surfaces + 4 retired-route classes are verified unreachable from
reachable UI and via bounded 409/410 handlers. See surface-inventory RETIRED_ rows.

## LOWER_LEVEL_ONLY_JUSTIFIED (3 rows)

- Canvas Graph mark-as-Production + bypass-in-production graph mutation — requires real ComfyUI LiteGraph; contract proved via Python server + fake dispatch boundary.
- GPU frozen-per-plan authority — proved via Python f8_gpu_authority suite; UI only presents server-authoritative value.
- Canvas /prompt V2 dispatch boundary — graph-dependent; fake server proves request chain.

No other Tier-3 claim blocks Phase-I closure. If live Modal is later authorized,
run the existing T3 suites and attach logs under `reports/i11-exhaustive-e2e/artifacts/`.
