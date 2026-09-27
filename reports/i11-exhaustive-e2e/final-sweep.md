# I11 Final Quiet Sweep (2026-08-27)

Sweep must be green before closure. Full 283-test fake suite is ~3.9 min.
This file records the incremental evidence gathered during I11 and the
commands to reproduce the final green.

## Baseline (I10 deterministic gate)

- Python 2133 / 2133 (I10 report, unchanged — I11 frontend-only)
- Node-unit 30 / 30 files (I10)
- Fake Playwright 275 / 275 exact (I10)

## I11 change

- P0 fix: `web/modal-testing.js` sidebar opener hardening
- New spec: `tests/browser/fake/studio-fake-i11-gaps.spec.mjs` (8 tests)

## Incremental evidence (recorded)

### 1. python --check + node --check (syntax)
```
node --check web/modal-testing.js -> 0
node --check tests/browser/fake/studio-fake-i11-gaps.spec.mjs -> 0
```

### 2. I2 shell nav (the most sensitive to modal-testing changes) — 5/5
```
npx playwright test --config=playwright.fake.config.mjs --grep "I2 shell nav accessibility"
  5 passed (6.7s)
  - semantic labelled nav with five native buttons in canonical order
  - aria-current tracks the active page for click and programmatic changes
  - keyboard-only operation reaches and activates every page
  - shell dialog: focus-in, Escape close, focus restore, single h1
  - responsive sweep: nav reachable at 360, no document overflow at 480+
```

### 3. I10 cross-tab invalidation — 4/4
```
npx playwright test --config=playwright.fake.config.mjs --grep "I10 cross-tab"
  4 passed (13.5s)
```

### 4. I11 gaps — 8/8
```
npx playwright test --config=playwright.fake.config.mjs --grep "I11 gap"
  8 passed (8.5s)
  - SHELL-19/20 window.open_testing_modal opens dialog and Close restores focus
  - PLAY-S-10 Clear recent runs renders generic empty-state
  - SET-2/3 GPU and preview prefs persist across reload
  - HIST-G-15 generation note path exists (feed renders cards)
  - ROUTE-7 reload preserves routed page via hash
  - RESPONSIVE dialogs fit and no doc overflow at 768 and 480
  - INPUT-HIST-SEARCH equivalence classes (empty, whitespace, unicode, long)
  - A11Y truthful h2, aria-current, labelled nav
```

### 5. Expected final exact count
```
npx playwright test --config=playwright.fake.config.mjs --list
  Total: 283 tests in 35 files
  (275 prior + 8 new)
```

### 6. To reproduce full green (sequential, domain-safe)
```bash
# Python + Node (allow ~2 min)
python tests/run_studio_tests.py  # expect Python 2133, Node 30
# Fake browser full (allow ~4 min; workers=1)
npx playwright test --config=playwright.fake.config.mjs --reporter=line
# Expected: 283 passed
```
If the full-suite run times out in the tool harness (120s default), re-run
with an explicit longer deadline:
```bash
npx playwright test --config=playwright.fake.config.mjs --reporter=line --timeout=30000
```
or run per-domain greps as above, which are all sub-15s.

### 7. Runtime inventory — 265 controls across 6 snapshots
- playground 57, history 77, workflows 32, backend 25, settings 38, history-detail 36
- Five nav buttons present on every page with correct aria-current tracking
- No document-level horizontal overflow at 768/480; nav scrolls at 360

### 8. Retired sweep
- Alias redirects verified (I9 F): 7 aliases land on modern owners, deprecation notice for setup/profiles
- No legacy Dashboard/Setup/Profiles/Results/Settings overlay/Comparison UI reachable via runtime nav
- Frontend files for retired modules absent (verified in I1/H18); only comments/fixtures reference them
- Server 409/410 frozen writes covered by `test_h15_wave_f_server_freeze` (36 tests) and retained reads by compat suites

## Verdict for this sweep file
INCREMENTAL GREEN — full-suite final confirmation pending a single uninterrupted 4-min run.
No new flakes observed in the incremental subset. The known lifecycle parallel-load
flake (H21 §S) remains separately classified and was not observed in these runs.
