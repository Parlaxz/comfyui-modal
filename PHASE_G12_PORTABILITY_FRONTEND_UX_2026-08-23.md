# PHASE G12 — Workflow Portability Frontend UX (2026-08-23)

**Batch:** G12 · **Type:** frontend/fake-browser product implementation · **Mode:** mounted Workflows UI + fake-backend parity + tests + this document. No production Python touched, no deploy/live/GPU/generation/commit/push/branch.

**Files touched by THIS lane:**

| File | Status |
|---|---|
| `web/studio-portability.js` | NEW — pure helpers (risk normalization, summary chip states, issue deep-link resolution) + panel/target-matrix/environment renderers |
| `web/studio-portability-checklist.js` | NEW — pure deterministic Markdown checklist generator + filename builder |
| `web/studio-backend-api.js` | MODIFIED — `getVersionPortability`, `fetchWorkflowManifestExport` (bytes + Content-Disposition), `importWorkflowManifest` (dry_run/policy wire), pure endpoint builders |
| `web/studio-workflows.js` | MODIFIED — card/detail chips, version-scoped Portability section, Check/Recheck, Export popover (presets default OFF), checklist download, manifest-import dialog (mandatory dry-run → preview → explicit commit) |
| `web/studio-styles.js` | MODIFIED — G12 portability CSS block (chips, issues, target grid, environment separation) |
| `tests/browser/fake/fake-backend.mjs` | MODIFIED — seeded G5 contract payloads (matrix/low/high/unknown_main), export/import engines with request logs, one-shot 409 credential refusal, atomic-failure simulation, chip-summary derivation, stale seeded summary on `wf_incomplete`, `dumpState` extras |
| `tests/browser/fake/fake-server.mjs` | MODIFIED — portability/export/import-manifest routes + 3 test-control endpoints |
| `tests/studio_workflow_run_unit.mjs` | MODIFIED (already-registered Workflow unit) — sections 9–12: normalization, risk presentation, chip states, checklist determinism/content, endpoint construction |
| `tests/browser/fake/studio-fake-workflow-portability.spec.mjs` | NEW — 16 fake Playwright tests |
| `tests/browser/fake/FAKE_BACKEND_GUIDE.md` | MODIFIED — §3.9 portability fake contract |

Untouched per ownership boundary: all `portability_*.py`, `studio_workflow_routes.py`, workflow domain/store files, `tests/run_studio_tests.py`, History, Settings, Modal/runtime/GPU/performance. G11-owned backend/cache files were not read-modified; the frontend treats `portability_summary` as optional per the shared contract (absent ≡ null).

---

## 1. Verdict

**G12 PASS.** Workflows visibly owns Portability end-to-end in the mounted UI: every workflow card and the detail header carry a native-button risk chip that opens the version-scoped Portability panel; the panel renders the backend report truthfully (summary risk, severity-tagged issues with verbatim fix hints, exactly six target rows in frozen order, and a visually separate Source-environment reproducibility section); Export downloads the backend-built manifest with presets default OFF; Import always dry-runs before an explicit commit with explicit preset policies; a derived, clearly non-authoritative checklist downloads as `.md`. All four risk states render distinctly, stale/needs-check/not-analyzed never masquerade as current, UNKNOWN is neutral everywhere, and no browser-side risk engine exists.

## 2. List summary UX (G11 chip contract)

`normalizePortabilitySummary` maps the optional `portability_summary` field to `{versionId, riskLevel, issueCount, stale(true|false|null), analyzedAt}`; absent/malformed ≡ null → **"Not analyzed"** neutral chip. `stale=false` → plain risk label + count; `stale=true` → **"… · Stale"** with title "cached result is STALE and requires a recheck"; `stale=null` → **"… · Needs check"** with title "freshness not verified". Chips are `<button>`s (keyboard operable) whose click opens the workflow detail; every chip carries explanatory `title`/`aria-label` text — never color-only. The fake derives fresh summaries from served reports (`stale:false`) so the G11 cache/list shape is proven from the frontend without client inference.

## 3. Portability panel

Version-scoped (`renderPortabilityPanel`): shows exact `v<N> · <version_id>` context, abbreviated graph hash, `analyzed_at`, stale-state sentence, counts by severity, `rule_version`, global issue rows (severity text + message + backend `fix_hint` verbatim; bounded deep-link button "View in Model Library" only for models/custom-node subjects — otherwise fix_hint stays text), and the six-target matrix. Check/Recheck calls exactly `GET /versions/{id}/portability`; pending state disables only that control with `aria-busy`; rapid clicks dedupe via an in-flight guard; success refetches the Workflow summary so cache-backed chips update; failure shows a bounded truthful message, keeps any prior report marked "PRIOR report after a failed recheck", restores focus, and never raises unhandled rejections. Version switch resets the panel to Not-analyzed (corresponding report only).

## 4. Target matrix & environment separation

Exactly six rows in frozen order (`local, modal, runpod, runcomfy, comfy_cloud, baseten` → Local/Modal/RunPod/RunComfy/Comfy Cloud/Baseten), rendered ONLY from the report: risk badge text, reasons resolved through the global issues pool by code (reference-by-code model), advice lines verbatim. Unknown targets stay Unknown with the explanation "Capability unknown — no defensible determination available." The environment block is a distinct bordered section titled **Source environment reproducibility** with the one-sentence explainer ("moving this WorkflowVersion elsewhere" vs "how exactly the CURRENT source runtime itself can be reproduced") and its own risk badge — it never recolors the workflow chip or any target (G5 POLICY_ENVIRONMENT_ISOLATION).

## 5. Export flow

Detail-panel action `Export workflow` opens a small confirm popover: checkbox **Include workflow presets** default OFF; confirm calls `GET /versions/{id}/export?include_presets=0|1`. Response bytes download via Blob anchor using the server's Content-Disposition filename (deterministic fallback if the header is missing). 404 / 409 / network failures render bounded truthful messages — the 409 message explains export was blocked to avoid embedding credential-like values, never echoes values, never suggests disabling security — and restore focus to the Export button. No Workflow/version/preset mutation and no run request is issued (asserted). Double-click dedupe holds at the app layer; note: Chromium internally re-requests attachment responses for its download manager (invisible to page events), so server-side hit-count assertions are differential while user-facing dedupe is asserted on page network requests + single download event.

## 6. Import preview/commit

Entry point `Import workflow manifest` (library header) opens a dialog with a JSON file picker (no ZIP). Flow is mandatory: file → exactly one `POST import-manifest?dry_run=1` → preview → explicit `Import workflow` → `POST ?dry_run=0` with body = manifest + `import_presets`/`apply_default_preset`. There is no bypass: the commit control does not exist until a valid preview is rendered. Preview keeps four truths separate: Manifest Valid/Invalid (+version), Structural readiness, Dependency availability ("Import is allowed, but the Workflow may not run until dependencies are resolved. Nothing is installed automatically."), and Portability risk — plus proposed name, existing name matches, will-create counts, ALL returned issues in a readable list, and security findings. Invalid previews disable commit entirely; malformed JSON is sent verbatim so the backend stays the authority. A >10 MiB client precheck blocks the send locally (backend 413 remains authoritative). Commit failure keeps the preview, shows the reason plus "Nothing was created. You can retry.", refocuses the commit button, and retry succeeds once the one-shot failure is disarmed. Success shows created Workflow/Version #1/Mapping/preset count plus a small provenance area (foreign ids labeled informational-only, never used for navigation), then opens the new local Workflow — never auto-running it.

## 7. Preset policies

`Import workflow presets` defaults OFF (disabled when the manifest carries none); `Apply imported default preset` defaults OFF and stays disabled unless presets are imported AND the preview reports `has_default_preset_candidate`. Unchecking presets clears apply-default. Commit transmits the exact chosen pair (fake logs prove `{false,false}` defaults and `{true,true}` explicit selections; production parity fields per G5 §8.2/G9).

## 8. Security / no-install guarantees

The frontend reads the selected file as text only to send it; it never fetches manifest URLs, unzips, installs nodes/models, or executes embedded strings. Browser specs assert ZERO requests matching `/studio/run`, `install-request`, model-download, or custom-node-install patterns across whole import/export/check flows. Export never mutates anything (read-only proven by write-tracker).

## 9. Checklist

`buildPortabilityChecklist` deterministically derives Markdown (stable section order: header → Summary → Issue counts → Issues+fix rows → Dependency notes → Target readiness → Source environment reproducibility → Import expectations → Provenance incl. rule_version/analyzed_at), invents no dependency facts absent from the report, emits no secrets, labels itself explicitly "NOT the canonical workflow manifest", and downloads as `<workflow>-v<N>-portability-checklist.md` via the reused `sanitizeFilenamePart` helper. Unit-pinned: byte-determinism, section order, six target names/order, fix hints verbatim, Medium-workflow/High-environment coexistence, no `undefined`/object dumps, dangerous filename sanitization.

## 10. Fake contract & accessibility

Fake seeds exact predetermined payloads only (no rule logic): modes `matrix|low|high|unknown_main` armable via `POST /__comfymodal_test/portability`; export arms a one-shot credential 409; import arms preview scenarios (`valid|invalid|missing_deps`) and a one-shot atomic commit failure; `dumpState` exposes `portabilityRequests/manifestExports/manifestImports`. Accessibility: native buttons/checkbox/file input/dialog roles, keyboard operation, visible labels, disabled+aria-busy busy states, focus recovery on failed check/export/commit, severity and risk always present as text, target matrix readable without color.

## 11. Test evidence

- Node units (registered `studio_workflow_run_unit.mjs`, extended): **12 sections pass** (8 existing + 4 new G12).
- New fake spec `studio-fake-workflow-portability.spec.mjs`: **16/16 passed** (list chips incl. Needs-check, panel LOW/MEDIUM/HIGH/UNKNOWN, matrix+environment, dedupe, version switch, request failure, export matrix, import dry-run/policies/failures/413/too-large).
- Focused regression (portability + workflow-run + models specs): **47/47 passed**.
- Full fake Playwright suite: **192/192 passed** (3.5 min).
- Full gate `python tests/run_studio_tests.py --fake`: **python 1991/1991 · node-unit 21/21 files · fake-playwright PASS — ALL STUDIO LANES GREEN**. (A stray benign `NoneType: None` line prints before the node lane; python lane reports fail=0 error=0 — concurrent-lane noise, not investigated per ownership.)
- §39 note: the G4-flagged duplicate `getVersionCompatibility` definitions no longer exist in `studio-backend-api.js` (single definition, line ~651) — cleanup already satisfied; no change made.

## 12. Remaining Phase-G work (other lanes only)

- G11 reconciliation: list-endpoint `portability_summary` enrichment landing in production `_enrich_workflow_summary`; runner registration for G6–G10 test modules.
- Production deep links could later target specific Model Library entries (currently the reliable sub-view surface is used).
- Optional: delete-workflow capability for import rollback UX (G4 gap, backend lane).

Deploy/live/GPU/generation/commit/push: **NONE**.

*G12 complete.*
