# CLIP-Forward Overlap via Non-Monolithic Loaders

Labels: wayfinder:map

## Destination

Decomposed Golden loaders with an explicit UNET preflight / transport / adoption seam (Golden Serial scheduling byte-for-byte frozen) plus a decided, safe CLIP-forward ∥ UNET-load overlap boundary, ready to hand off to the original 5-run true-cold validation with exact SHA and critical-path reconciliation.

## Notes

Domain: Golden Serial control vs optimized/parallel orchestration; CLIP/UNET load, QD2 source, H2D, CUDA streams/events, allocator/OOM, telemetry/ledger, deployment guardrails. Consult `comfy-modal-core`, `comfymodal-golden-ops`, `verification-planning`, `codebase-memory`, `unlazy`, plus `grilling` + `domain-modeling` for grilling tickets and `research` for research tickets. Standing preferences: work in normal repo on branch `TESTING2`, no new worktree, preserve all pre-existing dirty state, do not modify RES4LYF or external custom nodes, never use raw modal deploy/history (use `v2ctl`), Golden Serial stays the frozen control and is never renamed or redirected, plan-only map (execution hands off after decisions). Starting lineage anchor: `2ce937672725d1c261b13bd2877ec3a024de9d2c`. Optimized path lives at `comfymodal_runtime/golden_parallel.py` (`golden_p1_parallel`, `run_golden_parallel_stream`). Glossary lives in this effort, not the Studio `CONTEXT.md`: seam vs lane vs stage vs ledger vs barrier vs both-ready.

## Decisions so far

- [Allocator Headroom and OOM Fail-Closed Rule](issues/04-allocator-oom-rule.md): Overlap admits only on combined-peak headroom with explicit margin; no purges/resets in-window; OOM/degraded both fail closed.
- [Transport Lane Ownership Proof](issues/02-transport-lane-ownership.md): Only resource-backed dispatcher/static_e27 proves a request-local lane; legacy/decoupled/CPU-prefetch rejected; join+drain plus quiescence gates adoption.
<!-- one line per closed ticket: gist + link; open tickets are found by frontier query, not listed here -->

## Not yet specified

- Exact H2D-vs-CLIP-forward contention outcome and whether H2D stays in the overlap window or drains after forward.
- Lane execution shape once ownership is proven (worker thread vs executor vs stream-ordered transport handle; drain/cancel proof).
- What, if anything, beyond the UNET seam must be extracted as a shared primitive without refactoring Serial wholesale.
- Both-ready → sampler-prepare handoff detail and whether VAE/sampler interactions need their own later map.
- Production promotion rule for the optimized path after validation (tag move is explicitly not this map).

## Out of scope

- Golden Serial scheduling changes, renames, or silent redirects; moving the canonical tag.
- QD2 worker count / extent size / storage throughput / backing allocation; CLIP H2D optimization; UNET transport optimization itself; UNET H2D micro-optimization beyond the in-or-out decision.
- VAE overlap, sampler optimization, NextDiT, compile, CacheDiT optimization, external plugins, post-FRR billing, broad architecture cleanup.
- The next optimization after this overlap; the map ends at a handoff-ready decision set.

## Comments
