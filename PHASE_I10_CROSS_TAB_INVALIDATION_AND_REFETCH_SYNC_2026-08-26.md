# PHASE I10 - CROSS-TAB INVALIDATION AND REFETCH SYNC (2026-08-26)

**Batch type:** Phase-I implementation lane 10. Executed directly on the shared dirty working tree. Existing unrelated changes were preserved. No deploy, live Modal run, GPU run, commit, push, reset, revert, stash, branch, or worktree operation was performed.

## 1. VERDICT

## `I10 COMPLETE - PHASE I IMPLEMENTATION COMPLETE`

This records implementation and deterministic verification only. It is not a claim of formal Phase-I closure.

## 2. IMPLEMENTED CONTRACT

`web/studio-sync.js` is the single cross-tab invalidation module.

- One shared `BroadcastChannel("comfymodal-studio")` per page/module instance.
- Allowed kinds are exactly `settings`, `workspace`, `history`, and `workflows`.
- Messages contain only `{ kind, at }`; `at` must be a non-negative integer.
- Invalid kinds, malformed messages, unavailable browser support, constructor failures, post failures, and listener failures fail soft.
- Publishing never synchronously delivers the message back to the publishing channel.
- Subscribers receive only their selected kind and can unsubscribe.
- Node's optional `BroadcastChannel.unref()` prevents standalone unit tests from being held open; browsers do not expose this method and are unchanged.

## 3. PRODUCER COVERAGE

Successful server-backed mutations publish after persistence succeeds. Failed mutations do not publish.

- `web/studio-backend-api.js` classifies centralized non-GET mutations into `history`, `workflows`, or `workspace` and publishes only after an accepted response.
- `web/studio-output-preferences.js` publishes `settings` after the config POST and local/window state update succeed.
- `web/history-v2-repository.js` publishes `history` after successful annotation, favorite, featured-output, and related durable writes.

## 4. CONSUMER COVERAGE

Each page subscribes only while its mounted root is connected. On a relevant invalidation it marks the page stale, re-reads server truth, and clears the stale marker when the refresh settles.

- `web/studio-settings.js` rebuilds Settings from current state.
- `web/studio-backend.js` refreshes the active Backend section/list.
- `web/studio-history-v2.js` refetches the current History V2 feed through the repository adapter.
- `web/studio-workflows.js` reloads the current library, detail, or model surface without changing the user's current mode.

No polling, `storage` event fallback, payload replication, routing synchronization, or second state authority was added.

## 5. TEST COVERAGE

New unit test:

- `tests/studio_phase_i10_cross_tab_sync_unit.mjs`
  - strict channel and four-kind schema
  - invalid message rejection
  - no self-delivery
  - listener failure isolation
  - kind filtering
  - unsubscribe behavior

New permanent fake-browser test:

- `tests/browser/fake/studio-fake-phase-i10-cross-tab-sync.spec.mjs`
  - Settings mutation refetches a second tab
  - Backend workspace mutation refetches a second tab
  - History V2 favorite mutation refetches a second tab
  - Workflows favorite mutation refetches a second tab

Fake backend support was added only to make the existing UI mutation paths deterministic for the two-tab proof:

- `tests/browser/fake/fake-backend.mjs`
- `tests/browser/fake/fake-server.mjs`

The I10 unit was registered in `tests/run_studio_tests.py`.

## 6. VERIFICATION EVIDENCE

Combined registered gate:

```text
python tests/run_studio_tests.py --fake
  python             run=2133  fail=0  error=0  skip=0
  node-unit          run=30    fail=0  error=0  skip=0
  fake-playwright    PASS
ALL STUDIO LANES GREEN
```

Direct fake-browser run:

```text
npm run test:fake
  275 passed (3.9m)
```

Additional checks:

- `node --check web/studio-sync.js` passed.
- `node tests/studio_phase_i10_cross_tab_sync_unit.mjs` passed.
- `git diff --check` reported no diff errors; only existing LF/CRLF conversion warnings.

The Python lane emits expected existing test diagnostics for intentionally corrupt temporary stores, retired execution modes, and route-registration harnesses; the lane completed `OK` with zero failures and zero errors.

## 7. DEFERRED / NOT CLAIMED

- No live ComfyUI browser session or real multi-window manual check was run; the permanent two-page same-origin fake-browser proof is the verification path used here.
- No production Python/server changes were required for this client-side invalidation contract.
- Existing unrelated dirty-worktree changes remain untouched and are not attributed to I10.
- This report does not declare formal Phase-I closure.

## 8. FILES

I10 implementation and verification files:

- `web/studio-sync.js`
- `web/studio-backend-api.js`
- `web/studio-output-preferences.js`
- `web/history-v2-repository.js`
- `web/studio-settings.js`
- `web/studio-backend.js`
- `web/studio-history-v2.js`
- `web/studio-workflows.js`
- `tests/studio_phase_i10_cross_tab_sync_unit.mjs`
- `tests/browser/fake/studio-fake-phase-i10-cross-tab-sync.spec.mjs`
- `tests/browser/fake/fake-backend.mjs`
- `tests/browser/fake/fake-server.mjs`
- `tests/run_studio_tests.py`
- `PHASE_I10_CROSS_TAB_INVALIDATION_AND_REFETCH_SYNC_2026-08-26.md`
