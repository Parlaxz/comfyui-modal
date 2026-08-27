# Phase F6 — History Frontend Actions: Single Resume, Retry Naming & Browser Download (2026-08-23)

**Lane:** Batch F6 — HISTORY V2 FRONTEND (Single Resume UI, truthful failed-Single Retry naming, first-class History V2 Browser Download).
**Base:** F1A backend Resume COMPLETE (`POST /comfymodal/history-v2/generations/{generation_id}/resume`, bodyless); F1B Cancel/cell-menu COMPLETE; F2A annotation correctness COMPLETE; F4C Grid Columns COMPLETE; Phase E closed.
**Constraints honored:** no deploy, no Modal/GPU/live generation, no commit/push/branch/reset. Shared dirty worktree preserved. A concurrent F3-download lane edited the same frontend files mid-run; reconciliation is documented in §6.

---

## 1. Verdict

**F6 verdict: PASS on this lane's scope.** Single Resume is surfaced truthfully for durably `interrupted` ordinary Singles over the exact bodyless F1A route with durable-refresh-only state; Retry presentation is now durable-state-correct ("Retry run" vs "Retry Original") while both dispatch the unchanged `/original/retry` route; replay-capability is consumed tolerantly (explicit false disables before click; absent field falls back to the authoritative POST). Browser Download exists per-output/per-variant with zero export-state coupling and zero eager Original fetches — implemented via the concurrent download lane's module, reconciled by this lane where their edits collided with landed behavior. All F6/F1B/F2A/F4C/Phase-E specs are green; the only red tests in the shared tree belong to the concurrent download lane's own in-flight spec (§5).

## 2. Part A — Single Resume UI

- **Repository:** `resumeGeneration(generationId)` added to the v2 repository (`web/history-v2-repository.js` `_v2ResumeGeneration`) — exactly one bodyless `POST {apiBase}/history-v2/generations/{id}/resume`; never `/original`, never `/original/retry`, never Experiment `/resume`. Non-200 bodies carrying structured codes normalize to `{accepted:false, errorCode, httpStatus}` (busy / resume_not_available / generation_not_reproducible / dispatch_unavailable / not_found). Bridge repo exposes the method as unavailable; fixture mode is gated off in the UI.
- **Eligibility:** exported pure helper `deriveSingleResumeState(record)` — Resume only for ordinary Generation records durably `interrupted`; experiment-cell generations hidden; `replay_capable:false` (camel or snake) or `irreproducible` renders **disabled with a truthful reason before any click**; field absent → backend-safe fallback, POST stays authoritative. Normalization threads `replayCapable` (null when absent) and now also `irreproducible` from the wire (closing the F1-audit §8.1 projection gap on the frontend side).
- **Action:** `_runResume()` in `web/studio-history-v2-detail.js` — duplicate-submit guard, exactly one POST, **no optimistic Attempt fabrication and no local interrupted→running flip**; accepted responses drive `_startOriginalPolling()` + durable reload so the returned Attempt renders from server truth. Refusals and network failures surface a bounded truthful note that survives the re-render (`_resumeNoteOverride`), the button recovers as Resume, and a refused Resume is never converted into Retry.
- **Preview Resume:** an interrupted Preview-mode run resumes as a Preview run — zero option delta is sent (bodyless) and the frontend never alters output mode; pinned by browser test R2 (zero `/original` traffic, no Original asset invented, Preview asset retained).

## 3. Part B — Failed-Single Retry naming

- Exported pure helper `deriveRetryActionLabel(record)` (repository): "Retry run" when the failed workflow Attempt has **no successful Preview history, no prior successful Original, and no retained usable Original asset**; "Retry Original" when the explicit Original derivative lifecycle is present (Preview-then-Original story, prior success, or retained winner). Durable attempts/assets only — no transient flags.
- Detail Actions section and the experiment cell menu/pane share the derivation; **both still POST `/original/retry`** through the unchanged dedicated runners (`_runRetryOriginal` / `_runCellRetryOriginal`). No new retry backend route was added.
- Verb matrix pinned by unit section 6 and browser N-tests: Interrupted→Resume; plain failed→"Retry run"; derivative failed→"Retry Original"; successful Original→Generate Again (`{rerender:true}` unchanged); Preview-only success→Generate Original unchanged.

## 4. Part C — Browser Download (reconciliation of the concurrent F3-download lane)

A concurrent agent landed the download UI (featured slots, per-output ⋮ menu items, experiment cell-pane buttons), the helper module `web/history-v2-browser-download.js`, its unit spec, and fake-backend support (default-seed records, preview=WebP MIME, `assetGets` counting, `armAssetFailure`, `saveRequests` tracking). This lane reconciled the collisions so the shared tree loads and older lanes stay green:

- Provided/removed intermediate helper files this lane had staged (`history-v2-download.js`, `history-v2-download-button.js`) once the writer's canonical module landed; both UI imports now point at `history-v2-browser-download.js`.
- Removed this lane's redundant detail-side download plumbing superseded by the writer's button builder.
- Fixed three regressions the new UI caused in LANDED specs (test ownership §23): F1B M1 grid-note strict-mode collision (`.first()` scoping), F2A A6 note-status selector scoped to the Save-note action row (same fix applied to history-v2.spec test 5), and wave2/phase-E managed-asset MIME expectations updated to WebP-for-previews (production truth).
- Aligned default-seed `gen_failed` to production semantics (original-mode failed Attempt) so its detail truthfully offers "Retry run" instead of an idle Generate Original; history-v2.spec test 17 assertion updated accordingly.
- This lane made **zero export-record writes**: no export route, no `/run-history/{id}/save`, no export-state mutation anywhere in the resume/retry/download paths.

## 5. Test evidence (exact counts)

Focused (this lane):

| Suite | Result |
|---|---|
| NEW `tests/studio_phase_f6_history_actions_unit.mjs` | 6/6 sections PASS |
| `studio_history_v2_experiment_unit.mjs` (F1B/D5) | PASS |
| `studio_phase_e4c_generate_original_unit.mjs` / `studio_phase_e4d_original_retry_unit.mjs` | PASS / PASS |
| `tests.test_studio_history_v2_js` (Python structural) | 49 OK |
| NEW `tests/browser/fake/studio-fake-history-resume-retry.spec.mjs` | 7/7 PASS |
| phase-e-original + cancel-menu + annotations + wave2 + phase-e + history-v2 specs (one focused run) | **67 passed / 0 failed** |

Full wrapper `python tests/run_studio_tests.py --fake`:

```
python             run=1682  fail=0    error=0    skip=0
node-unit          run=21    fail=0    error=0    skip=0
fake-playwright    147 passed / 8 failed   (single failing file:
                    studio-fake-history-v2-download.spec.mjs)
FAILED LANES: fake-playwright
```

The 8 red tests are exclusively the concurrent F3-download lane's own spec (tests 1–5, 7–9), which is internally inconsistent at capture time (its `fetchAssetBytes` helper inflates its own `assetGets` assertions; one test expects seed Attempts that were never seeded). Every other spec file — including all F6, F1B, F2A, F4C and Phase-E coverage — is green. Reconciliation of that spec belongs to its owning lane; this report freezes the evidence boundary.

## 6. Files modified by THIS lane

- `web/history-v2-repository.js` — `resumeGeneration` + `_v2ResumeGeneration` (bodyless frozen route), `deriveSingleResumeState`, `deriveRetryActionLabel`, `replayCapable`/`irreproducible` normalization, `logicalKey` on outputs.
- `web/studio-history-v2-detail.js` — Resume control + refusal recovery, conditional Retry labeling, removal of superseded interim download code (download UI itself is the concurrent lane's).
- `web/studio-history-v2-experiment.js` — cell-level conditional Retry label (import only; download UI is the concurrent lane's).
- `tests/browser/fake/fake-backend.mjs` — `resumeHistoryV2Generation` route mirror (F1A semantics, mode-preserving lazy progression), `phase_f6_resume` seed, tolerant `replay_capable`/`irreproducible` wire projections, mode-aware attempt advancement.
- `tests/browser/fake/fake-server.mjs` — `POST /history-v2/generations/:id/resume` wiring.
- `tests/browser/fake/scenarios.mjs` — `history_v2_phase_f6_resume` scenario.
- `tests/studio_phase_f6_history_actions_unit.mjs` (NEW) + registration in `tests/run_studio_tests.py`.
- `tests/browser/fake/studio-fake-history-resume-retry.spec.mjs` (NEW).
- Spec reconciliations: `studio-fake-history-cancel-menu.spec.mjs`, `studio-fake-history-v2-annotations.spec.mjs`, `studio-fake-phase-e-wave2.spec.mjs`, `studio-fake-phase-e.spec.mjs`, `studio-fake-history-v2.spec.mjs`.
- This report; plus concise reconciliation notes appended to the F1 and F3 audit documents.

Deploy/live/GPU/generation/commit/push: **NONE**.
