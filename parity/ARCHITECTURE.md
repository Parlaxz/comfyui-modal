# Parity oracle architecture

One scenario definition (`tools/parity_oracle/scenarios.py`), two adapters, semantic traces, comparator.

- `legacy_adapter.py` builds the EXPECTED trace from legacy source facts (bindable catalog, field blocks, ROLE_SUGGESTIONS, shelf keys, routing) + corpus fixture.
- `vue_adapter.py` builds the ACTUAL trace from Vue source facts (PlaygroundControls.vue, stores, api, pages, router) + same fixture.
- `trace.py` is the shared semantic contract (controls, types, values, options, order, collapse, route, storage, API, intent, wizard, graph ops, final state). No implementation details compared.
- `comparator.py` classifies per-field PASS/FAIL/UNKNOWN and rolls up; PASS requires exact match on every check. It never emits INTENTIONAL_DIFFERENCE/RETIRED — those need explicit Ahmed approval recorded in manifest fields.
- `run.py` executes all scenarios and GENERATES `parity/manifest.json` + `parity/REPORT.md`. The report is never hand-edited truth; it is derived output.
- Visible-but-inert affordances are FAIL by construction: the Vue adapter reports what is actually rendered/wired, so a tab that opens without behavior mismatches the legacy trace.
