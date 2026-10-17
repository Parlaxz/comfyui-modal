# Studio Vue Parity Oracle — methodology

## What this is

An executable inventory of every accepted Studio behavior the Vue migration must preserve, plus the architecture contracts and retirements that bound it. Future implementation works against `manifest.json`; nothing else here is authority.

## Files

- `tools/parity_oracle/rows/*.json` — editable contract source. Edit these, then regenerate.
- `manifest.json` — generated canonical COMPILED oracle (authoritative runtime artifact, not the editable source). Never hand-edit; regenerate via `python -m tools.parity_oracle.run`.
- `REPORT.md`, `coverage.md` — generated views. Never hand-edit.
- `REPORT.md` — generated totals + matrix + ranked failures + unknowns. Never hand-edit.
- `coverage.md` — generated evidence-gap lists. Never hand-edit.
- `AUDIT_REPORT.md` — curated narrative from the discovery audit (background, not authority).
- `CHANGELOG.md` — what changed in the oracle and why.
- `ORACLE_FREEZE.json`, `behavior_inventory.json`, `qol_ledger.json`, `corpus/`, `ARCHITECTURE.md`, `RUNTIME_CRAWL.md` — supporting inputs/notes.
- `tools/parity_oracle/rows/*.json` — row sources (one domain per file). Edit these, then regenerate.
- `tools/parity_oracle/scenarios.py` + adapters — the legacy 17-case differential smoke harness. Diagnostic only; its labels are quarantined under `legacy_smoke` and never enter totals.

## Row schema (v2)

`id, contract_type, area, behavior, authorities, required_evidence, current_evidence, status, reason, legacy_evidence, vue_evidence, tests_or_traces, implementation_invariant, notes`.

- `contract_type`: `product_behavior` | `migration_architecture` | `retirement`. Product and architecture parity are counted separately.
- `authorities`: ordered per precedence — owner decision, revised `docs/VUE_MIGRATION_BLUEPRINT.md`, accepted phase/tests, legacy implementation, older docs only if unreplaced.
- Evidence is a SET, not a ladder: `required_evidence: ["BROWSER","RACE"]` means both. `current_evidence` lists what actually exists.
- `status`: PASS (required ⊆ current) · FAIL (required behavior positively contradicted or absent — code absence with `["STATIC"]` suffices to prove a missing editor) · UNKNOWN (evidence cannot decide) · NA · INTENTIONAL_CHANGE (binding newer decision cited).
- `implementation_invariant`: reuse/port directives (Sketch: ComfySketch-derived engine; Post: TinyLuma-derived engine). Never rewrite either from scratch.

## Commands

```text
python -m tools.parity_oracle.run          # regenerate manifest + reports
python tools/parity_oracle/negative_controls.py   # prove the harness catches breaks
pytest tests/test_parity_oracle.py -m fast_unit   # guard test
```

## Evidence groups overlap

`coverage.md` counts evidence requirements, not unique unresolved rows. Because evidence is a set, one row appears in every group it still needs (e.g. a row needing `["BROWSER","RACE"]` is listed under both). Never sum the groups; `manifest.json` counts are the row totals.

## Rules for editors

1. Add rows, don't reinterpret old ones silently — record corrections in `CHANGELOG.md`.
2. Never hand-type PASS. The builder rejects PASS where required ⊄ current.
3. Never quote legacy smoke labels as parity evidence.
4. Keep rows atomic: one independently-failing behavior per row.
5. Cite the real authority per row, not just "blueprint".
