# PHASE H10 — LEGACY ENTRY-POINT REDIRECTS, HIDDEN REGISTRATION RETIREMENT & MODERN COPY CLEANUP (2026-08-24)

**Batch type:** H-WAVE B implementation (H5 §20 dead-surface retirement subset + §22 redirects + §21-B redirect step). No deploy, no Modal/GPU/live generation, no commit/push/branch/worktree/reset. H9 and H11 ran concurrently in the shared tree; no H9/H11-owned file was edited to resolve their churn.

**Authority:** `PHASE_H5_CONSOLIDATION_CONTRACT_FREEZE_2026-08-23.md` §20 (hidden sidebar registrations), §22 (old-opener redirect table), §21 step B (redirect old openers), §7/§15 (Comparison non-recreation), §14/H8 (Experiment authority), H4 §3 (feature-registry legacy funnels), H5A errata FA-5.

---

## 0. VERDICT

`H10 COMPLETE — old opener aliases land on modern owners, hidden legacy sidebar registrations are gone with zero remaining flag consumers, normal Studio sidebar remains, misleading Legacy Setup copy is rewritten truthfully, Comparison code/data/routes and the legacy overlay compatibility global are intact. PASS (with concurrent-churn failures attributed to H9/H11, see §10).`

---

## 1. OPENER CALLER INVENTORY (measured before behavior change)

| Caller | Alias/global | Intent | Disposition |
|---|---|---|---|
| `modal-testing.js` sidebar panel "Open Studio" / fallback launcher | `open_testing_modal()` (no arg) | generic Studio open | unchanged |
| `modal-settings.js` legacy panel "Testing Suite" button (`:1248`) | `open_testing_modal()` (no arg) | generic Studio open | unchanged (compat launcher, pinned by test) |
| `modal-testing.js` `handleOpenSection` (listener for `comfymodal.open-section`, dispatched by `testing-settings.js`) | `"settings"` | modern Settings section scroll | unchanged → Settings |
| `modal-testing.js` studioContext `onRun` (legacy Setup tab run start) | `"results"` | watch run results | **rewritten**: results alias now lands on History V2 |
| `modal-testing.js` sidebar panel "Open Legacy Settings" button | `window.open_comfymodal_settings()` | generic escape hatch | **replaced** with "Open Settings" → Studio Settings page |
| `testing-dashboard.js` New Experiment / Open Setup hero | `"setup"` | experiment composition | caller deleted by H9 mid-flight; alias contract still frozen (external scripts may call it) |
| `testing-dashboard.js` Resume/Open Results | `"results"` | results viewing | caller deleted by H9; alias frozen → History |
| `testing-dashboard.js` Comparison Profiles button | `"profiles"` (+overlay fallback) | profile management | caller deleted by H9; alias frozen → Playground + deprecation |
| `testing-dashboard.js` Settings button | `open_comfymodal_settings()` | preferences | caller deleted by H9 |
| `window.__comfyModalEnableLegacySidebarTabs === true` blocks | n/a | opt-in duplicate sidebar tabs | **removed** (both files) |

Aliases are NOT interchangeable: `dashboard` = operational intent → Backend; `setup` = experiment composition → Playground(+Experiment context); `profiles` = retired Comparison management → Playground + truthful deprecation; `results`/`history` = durable records → History V2; `settings` = preferences → Settings.

## 2. EXACT ALIAS MAP (frozen, `web/modal-testing.js` `ALIAS_PAGE_MAP`)

```
playground → playground
dashboard  → backend      (H6 re-homed operational launchpad)
setup      → playground   (+ existing in-memory experimentMode=true + bounded deprecation notice)
profiles   → playground   (+ bounded deprecation notice; NO Comparison editor mount)
results    → history      (History V2)
history    → history      (History V2; never bridges studio-history.js/testing-history.js)
settings   → settings
```

No dead `activeLegacyTab` is set anywhere in `modal-testing.js` (zero occurrences; both cached-shell and fresh-shell paths route through `_applyLegacyAliasNavigation`). Contextual Experiment reopen for `results` is NOT attempted — shell navigation APIs expose no safe experiment-id deep open, so History landing per contract.

## 3. SETUP BEHAVIOR

Preferred option implemented: opens Playground AND surfaces the existing Experiment-mode context by setting the pre-existing in-memory `state.playground.experimentMode = true` flag (same flag the Playground toggle writes; nothing persisted, no new state semantics, no synthesis, no auto-run). A bounded auto-dismissing deprecation banner (`data-testid="alias-deprecation-notice"`, 6 s) states: "Legacy Setup has retired. Experiments now live in Playground → Experiment mode." No deep-link infrastructure created.

## 4. PROFILES BEHAVIOR

Single historical caller intent was Comparison-profile management, which has no modern owner (Wave E retires the domain). Mapping differs from setup deliberately: lands on Playground WITHOUT toggling Experiment mode (management intent ≠ execution intent) and shows a bounded deprecation banner naming the truthful owners: "Comparison Profiles have retired. Preset comparisons live in Playground → Experiment mode; workflow configuration lives in Workflows." Never opens a Comparison editor; no universal forced mapping beyond this single evidenced caller class.

## 5. DASHBOARD / HISTORY / RESULTS / SETTINGS REDIRECTS

- `dashboard` → Backend page (cards not recreated).
- `history`/`results` → History V2 page; no import of `studio-history.js`/`testing-history.js` anywhere in the redirect path.
- `settings` → modern Settings.
- `/prompt` canvas compatibility untouched.

## 6. HIDDEN SIDEBAR RETIREMENT + FLAG CLEANUP

- `web/modal-settings.js`: opt-in "Modal GPU" registration block removed.
- `web/modal-comparison.js`: opt-in "Comparison Profiles" + "Comparison Runner" registration blocks removed.
- `__comfyModalEnableLegacySidebarTabs` now has **zero readers/writers in web/** (verified by sweep); dead-flag handling removed per §11. Zero-production-consumer proof pinned in `LegacySettingsSidebarGuardTests` / `LegacyComparisonSidebarGuardTests`.
- Normal Studio sidebar entry (`comfymodal-testing-suite` in `modal-testing.js`) remains — the only `registerSidebarTab` call site left in web/.
- Comparison implementation intact: `buildProfilesTab`, `buildRunnerTab`, `mountComparisonProfiles/Runner`, overlay globals, `_initContextMenu` canvas menu, backend routes/data — untouched (Wave E).

## 7. REMAINING DIRECT COMPATIBILITY GLOBALS (intentional)

- `window.open_comfymodal_settings` (modal-settings.js) — kept; remaining callers are inside the Wave-E legacy surface (`testing-settings.js` standalone links).
- `window.open_testing_modal` / `window.close_testing_modal` — kept (external script compat).
- `window.openComparisonProfilesOverlay` / `openComparisonRunnerOverlay` — kept (Wave E).
- `window.__comfyModalUnifiedUI` — kept.

## 8. FEATURE-REGISTRY COPY CHANGES (modern funnels only)

| Location | Before | After |
|---|---|---|
| `studio-feature-registry.js` object_remove/object_replace `placeholderReason` | "…Use Settings > Legacy Setup for the full experiment suite." | "Image-edit tools are not available in the modern Playground yet." |
| `studio-feature-registry.js` lora `helpText` | "…Configured in Settings > Legacy Setup." | "LoRA model to apply. Not configurable in the modern Playground yet." |
| `studio-playground.js` static-select note (LoRA) | "Configure in Legacy Setup" | "Not available in the modern Playground yet." |
| `studio-playground.js` `navigateToLegacySetup()` action | dead helper funneling to Settings▸Legacy Setup (zero callers) | removed |

Truthfulness rule honored: no modern capability is claimed that does not exist. The Settings▸Advanced▸Legacy group itself is NOT removed (Wave E), so its internal labels remain by design.

## 9. AUTO-OPEN VERDICT (§14)

The historically flagged `modal-settings.js:1248-1249` "auto-open on module load" does NOT exist in the current tree: those lines are the "Testing Suite" **button's onclick handler** inside `buildPanel()` (user-initiated). No module-load invocation of `open_testing_modal`/`open_comfymodal_settings` exists in any web/ module. Verdict: **nothing to remove; no surprising auto-open side effect present.** All non-UI initialization (`syncLegacyGpuConfigOnce`/`syncLegacyOutputPrefsOnce`, poll cleanup, redeploy banner) untouched.

## 10. TESTS

Focused additions/updates (all green):
- NEW `LegacyEntrypointRedirectTests` (11 tests): dashboard→Backend, history→History, results→History, settings→Settings, setup never mounts Legacy Setup (+deprecation present), profiles never recreates Comparison editor, zero `activeLegacyTab`, normal sidebar entry remains, compat global remains, no provider vocabulary/no network I/O in opener, no Legacy Setup funnel in modern copy.
- REWRITTEN `LegacyComparisonSidebarGuardTests` / `LegacySettingsSidebarGuardTests`: flag absent, zero `registerSidebarTab`, Comparison helpers/overlays/canvas menu intact, overlay global preserved.
- REWRITTEN `RootCauseCachedShellLegacyRoutingTests`: zero `activeLegacyTab` occurrences.
- UPDATED routing pins in `StudioBackendContractTests`, `test_studio_backend.LegacyRoutingTests`, `test_testing_ui_wired`, `test_modal_workspace_ui_ast` (sidebar opens modern Settings).
- `tests/run_studio_tests.py` NOT edited.

Full gate (`python tests/run_studio_tests.py --fake`) at H10 execution time, shared tree with H9/H11 mid-flight:

```
python             run=1974  fail=29   error=8    skip=0
node-unit          run=21    fail=0    error=0    skip=0
fake-playwright    PASS      (run=1 npm lane, 0 failed)
FAILED LANES: python
```

Baseline was Python 1991 / Node 21 / Fake 199. Attribution of every python failure/error (35 unique tests): exclusively H9/H11 concurrent churn — `test_history_*`/`test_preview_*` (read deleted `studio-history.js`), `test_dashboard_*` (deleted `testing-dashboard.js`), `test_settings_legacy_mentions_all_old_tabs`/`test_settings_legacy_section` (H9 trimmed Legacy Dashboard/History list items), `test_studio_legacy_references_old_tab_modules`, and `test_production_summary_labels`/`test_output_save_folder_defaults_are_normalized` (pre-existing working-tree removals of `DEFAULT_OUTPUT_SAVEFOLDER`/"Production plan" regions in `modal-settings.js` owned by another lane). **Zero failures touch H10 scope** (aliases, redirects, sidebar flags, copy, compat globals). Python count delta −17 = H9's concurrent structural-test pruning.

## 11. FILES MODIFIED BY THIS LANE

Production:
- `web/modal-testing.js` — ALIAS_PAGE_MAP + deprecation notices + alias navigation helper; onRun→History; sidebar "Open Settings"; comment updates.
- `web/modal-settings.js` — hidden sidebar registration block removed (region-scoped; panel/overlay body untouched).
- `web/modal-comparison.js` — hidden Profiles/Runner sidebar registrations removed (overlays/canvas menu/builders untouched).
- `web/studio-feature-registry.js` — placeholder/help copy rewrite.
- `web/studio-playground.js` — static-select note rewrite; dead `navigateToLegacySetup` removed; one comment.

Tests:
- `tests/test_testing_shell_integration.py`, `tests/test_studio_backend.py`, `tests/test_testing_ui_wired.py`, `tests/test_modal_workspace_ui_ast.py`.

Report: this document.

## 12. INTENTIONALLY LEFT FOR WAVE E

- Standalone legacy Settings overlay + `window.open_comfymodal_settings` global.
- Settings ▸ Advanced ▸ Legacy group (incl. its "Open Legacy Settings" button and remaining list items).
- Comparison UI retirement (overlays, canvas context menu, builders) + V1 executor path per C/E sequencing rule.
- Dead `mountLazyTab`/`TAB_MODULES` in `modal-testing.js` (unreachable; Wave G dead-code deletion).
- Legacy tab modules still on disk (`testing-setup/profiles/results/settings.js`) — H9 owns dashboard/history deletions.

Deploy / live / GPU / generation / commit / push by this batch: **NONE**.
