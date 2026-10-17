# Oracle correction changelog (2026-10-17 freeze)

Starting point: 293-row v1 oracle (10/6/1 legacy smoke; PASS/FAIL/UNKNOWN/NOT_APPLICABLE/INTENTIONAL_CHANGE; scalar evidence ladder).

## Schema

- Evidence ladder replaced by evidence SETS: `required_evidence` / `current_evidence` arrays.
- Added `contract_type` (product_behavior / migration_architecture / retirement); counts separated.
- Added `authorities[]` ({kind, ref}) with precedence: owner decision → revised blueprint → accepted phase/tests → legacy impl.
- Added `implementation_invariant` (Sketch/Post reuse directives).
- `NOT_APPLICABLE` → `NA`; `test_or_trace` → `tests_or_traces[]`; dropped `source_contract` (folded into authorities).
- Old 17-case harness relabeled LEGACY SMOKE, quarantined under `legacy_smoke`, excluded from totals.

## Status corrections (mandated)

- ARCH-VUE-ROUTER UNKNOWN → PASS (revised blueprint approves Vue Router; no ruling needed).
- POLL-ABORT rewritten (no abort-on-navigate; one owner, no duplication, domain continues) → UNKNOWN.
- POLL-RUN rewritten as controller-integration contract → FAIL.
- OPS-DUP-BUSY rewritten (second registry / conflicting authority is the failure) → UNKNOWN.
- OPS-WS-ID DELETED (workspaceId optional per blueprint Operation shape).
- WS-GUARD rewritten (bound-target invariant, no blocking guard) → UNKNOWN.
- WS-MIDOP FAIL → UNKNOWN (server authority may own dispatch; needs RACE+REAL_BACKEND).
- QUEUE-WORKSPACE-FROZEN rewritten (non-retargetable accepted target) → UNKNOWN.
- QUEUE-IDENTITY-CHECK rewritten (own frozen identity; no incompatible batch merging) → FAIL (kept).
- PERSIST-MIGRATION DELETED (generic); PERSIST-RELOAD split (browser prefs UNKNOWN + new PERSIST-NO-SERVER-AUTH PASS).
- LATEST-SHARED rewritten (specialized tokens legitimate) → UNKNOWN.
- PG-NUMERIC-BOUNDS split → PG-NUM-MINMAX (PASS/UNIT), PG-NUM-STEP, PG-SEED-RANGE (UNKNOWN).
- REF-WEIGHTS rewritten method-conditional → FAIL (no method UI at all).
- DEPS-INSTALLING merged into exhaustive DEPS-STATES (FAIL kept).
- HOST-AUTOREOPEN split → refresh FAIL + new HOST-WIZARD-REOPEN UNKNOWN.
- WZ-GRAPH-MODE reworded to positive absence (seam unwired) → FAIL kept.
- OPS-REGISTRY split → OPS-ONE-ROOT, OPS-ONE-PINIA, OPS-NO-EXEC-AUTH (PASS/STATIC) + OPS-ONE-REGISTRY (UNKNOWN).
- RUN-CONTROLLER-INTEGRATION added → FAIL (no websocket/identity/terminal machinery in Vue; grep-verified).
- MODEL-LIBRARY-PLACE added → PASS (owner decision: Manage Modal, supersedes H5).

## Newly inventoried (omission sweep)

- Style Browser STY-* (9, FAIL) from style-browser spec; Layout LAY2-* (12) from layout spec; Sketch SK2-* (9, reuse invariant); Post POST2-* (13, reuse invariant); Select SEL2-* (12); Expand EXP2-* (8); References REF2-* (7); Guidance GUI2-* (9); History HIST2-* (4); Compare CMP2-* (4, incl. CMP2-NO-REVIVAL NA); Phase-12 P12-* (7); Phase-13 P13-* (6).
- Deduped against existing rows: dropped REF2-006/007-overlap equivalents, HIST2-004/005/006/007 (covered), P12-007 (covered), narrowed HIST2-003/008, P12-008, GUI2-008.

## Provenance established

- Sketch: comfyui-comfysketch, Vitor Silva (Mexes1978), MIT, https://github.com/Mexes1978/comfyui-comfysketch. Engine `web/studio-sketch-engine.js`; layers `-layers.js`; panels `-panels.js`; shell `-shell.js`.
- Post: TinyLuma-based per `web/studio-postprocess.js:1-13`; introduced commit `9b333d08`. Engine `:224-674`; shell `:720-1905`.
- Both families carry `implementation_invariant = reuse_existing_upstream_derived_engine`.

## Remaining UNKNOWNs

See `coverage.md` (BROWSER / RACE / REAL_BACKEND / INTEGRATION lists). Each row states exactly what evidence resolves it.

---

# Final cleanup freeze (2026-10-17, commit `test(studio): finalize Vue parity oracle contracts`)

- POLL-OWNER merged into POLL-ABORT (kept stable ID); contradiction removed. Correct invariant: one domain owner, no duplication, navigation never auto-kills, terminal/dispose stops, domain owns semantics.
- SK2-SURFACE rewritten from selector/wording freeze to behavioral surface requirement; reuse invariant kept.
- POST2-PIPELINE deleted as product_behavior (Canvas 2D internals not parity-scored); reuse invariant governs.
- POST2-PERSIST rewritten as durable-data compatibility (existing keys or bounded migration read), not key identity.
- Added SKETCH-ENGINE-REUSE + POST-ENGINE-REUSE family contracts (migration_architecture, PASS/STATIC as recorded binding directives). Existing SK2/POST2 granularity kept: acceptance surfaces, not rebuild tasks.
- Stale-contract sweep: two historical Vue-Router-restraint mentions reworded; no other live remnants (SET-SKIP exact-key, POLL-TERMINAL done/abort, correction-history notes all valid).
- Settled decisions untouched: Model Library in Manage Modal, Sketch/Post reuse, Upscale parked, Vue Router + operationStore approved, run-controller reuse, canvas separation, History V2, no Comparison revival.
- Guards added to builder: contradictory nav-poll policy (negation-aware), reused-engine DOM/copy freeze, post mechanism freeze; validator now also owns duplicate-ID detection.
- Docs: README distinguishes editable row sources vs generated compiled oracle; coverage overlap explained in README + coverage header; AUDIT_REPORT.md bannered as historical record.
