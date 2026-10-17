# Old Studio → Vue Parity Matrix

Method: legacy implementation code + old tests + live Vue DOM/network + live
backend responses. Legacy UI was NOT opened live (code/tests/reports evidence;
marked where live-old proof is unavailable). Status key: PARITY /
PARITY_BUT_DIFFERENT_PRESENTATION / MISSING_UI / MISSING_BEHAVIOR / BUG /
INTENTIONALLY_RETIRED / BACKEND_OPERATIONAL.

## 1. Workflow dependencies

| Old action | Old owner / endpoint | Vue equivalent | Status |
|---|---|---|---|
| Missing sourced model: Queue install + Install now + source link | studio-model-library.js renderModelInstallControls; backend install routes | RESTORED: source link + Install now + Queue install + Find in library | PARITY |
| Missing source-less model: Manager catalog match → install; explicit URL input + install | same; managerModelsByFilename basename match | RESTORED: basename-safe match (api/manager port), per-row URL input, Find in library | PARITY |
| Missing model: Find in library (prefilled query handoff) | openModelLibraryFiltered | RESTORED: libraryQuery + Models tab search + detail | PARITY |
| Missing node: Manager safe match → Install now; else Find in registry | resolveNodeInstall kind gate; openRegistryFiltered | RESTORED: gated install + registry handoff to library search | PARITY |
| Installed row: path/folder + remote detail, no install | same | PARITY (detail lighter) | PARITY_BUT_DIFFERENT_PRESENTATION |
| Optional (nonessential) toggle, user-scoped | _setNonessential + user-source set | PARITY (markNonessential + refetch) | PARITY |
| Summary installed/missing/ready | backend summary EXCLUDES nonessential missing | FIXED: derived from rows (`N installed · M missing · attention` / `N installed · K optional missing · ready`) | PARITY |
| Refresh dependencies | refreshDependencies | Implicit on version select; no manual refresh | MISSING_UI (minor) |

## 2. Model Library (Workflows Models/Nodes tab)

| Old action | Vue equivalent | Status |
|---|---|---|
| Browse registered models + search + type filter + state filter | Counts + two buttons only | RESTORED: search + type filter + detail + rescan + registry (state filter N/A: inventory is installed-only) | PARITY |
| Model detail (folder, hash, size, provider/revision, remote, notes/tags) | None | RESTORED: provenance + note editor | PARITY |
| Notes/tags/source-URL edit (updateModel route exists) | None | RESTORED: note editor via PATCH /studio/models/:id | PARITY |
| Explicit rescan (+full rehash where applicable) | None in tab (Manage has Rescan) | RESTORED in tab (force rehash) | PARITY |
| Custom-node registry browse + refresh | Refresh only | RESTORED: searchable browse + detail + refresh | PARITY |
| Safe custom-node install path in library | Via dep rows only | Install stays on dep rows (safe-match gated); library is browse/detail | PARITY_BUT_DIFFERENT_PRESENTATION |
| Used-by N workflows / workflow-context navigation | None seen | LIKELY MISSING (verify against old library before close-out) |
| No auto-scan/install on render | loadInventory is app-level, tab projects | PARITY |

## 3. Setup wizard

| Old behavior | Vue equivalent | Status |
|---|---|---|
| Feature-type role sets (t2i/i2i/inpaint/sketch/outpaint required + optional) + output | Code-owned catalog ported (api/workflows); Bindings step lists required/optional per type | PARITY |
| Per-role graph capture with exact node/widget target | Generalized captureBinding(key); engine unchanged | PARITY |
| Graph-backed suggestions (proposals, never auto-bind) | Suggest per role via host seam → candidate chips → click centers node | PARITY (verified live: empty-graph honest message) |
| View/center/highlight bound node | View button via host viewStudioGraphNode | PARITY (verified live: "Centered Prompt on the graph") |
| Required save gate (required roles + output) | Review gate text + disabled Save + saveWizard guard | PARITY |
| Output binding | Pre-existing captureOutput in Controls step | PARITY |
| Exposed-controls config | Free-label add (legacy maps bound roles; Vue free entry) | PARITY_BUT_DIFFERENT_PRESENTATION |
| Edit-existing-mapping deep link | Mapping section raw editor | PARITY_BUT_DIFFERENT_PRESENTATION |
| Dependencies step in version-setup mode | Step contract frozen (feature/bindings/controls/review); deps-attention note inside Bindings step | PARITY_BUT_DIFFERENT_PRESENTATION (deliberate: no engine reorder) |
| Draft resume/persist + graph restore on cancel/save | Pre-existing maybeResumeWizard + closeWizard host restore | PARITY |
| Escape from graph focus | Document-level Escape while wizard owns session (teleport-safe) | PARITY (new; fixed a real gap found by tests) |

## 4. Portability / manifest

| Old action | Vue equivalent | Status |
|---|---|---|
| Check/Recheck + risk state + reasons | recheckPortability + summary line | PARITY_BUT_DIFFERENT_PRESENTATION (reasons depth TBD) |
| Manifest export | exportManifest | PARITY |
| Manifest import: dry-run preview + explicit commit | store has previewManifestImport/commitManifestImport; NO UI | RESTORED: paste-JSON → Preview → explicit Commit in Portability section | PARITY |
| Preset include/exclude choice on import | No preset-scoped import option in old UI either (manifest-level flow) | INTENTIONALLY_RETIRED (no evidence of per-preset choice) |

## 5. Presets / guidance / versions

| Old action | Vue equivalent | Status |
|---|---|---|
| Create + delete preset | createPreset/removePreset + UI | PARITY |
| Update/edit/duplicate/copy preset | None seen | RESTORED: inline rename + Duplicate + copy-to-version select | PARITY |
| Guidance mapping load/view/remove | loadGuidance + UI | RESTORED: result view + Remove (saveGuidance/removeGuidance wired) | PARITY |
| Version select / capture | select + captureVersion + UI | PARITY |
| Metadata/folder/tags/favorite edit | updateMetadata + UI | PARITY |
| Import workflow JSON | importNewWorkflow + UI | PARITY |
| Delete workflow | deleteSelectedWorkflow + UI | PARITY |

## 6. History

Verified against history-v2 suites (18/18) + live browser: feed filters,
search, sort, favorite-only, pagination, favorite/note persist, bulk delete,
replay/original/retry/resume, download/export, picker, compare A/B + swap,
experiment resume/cancel, cell detail, viewer/picker Escape layering.
Status: PARITY (no churn; viewer/picker owned by teammate files, untouched).

## 7. Manage Modal

Verified: workspaces list/active/add/edit, token semantics preserved in
saveWorkspace, set active, swap + prompt-running confirm + review, progress,
repair scan/apply/placeholder-delete (editor restored this pass), deploy
status/progress/log, credentials (masked, never raw), models/nodes inventory,
node sync + rebuild. Status: PARITY.

## 8. Settings

Verified: GPU, output format/quality, WebP, save location, auto-save,
sidecar, Data Saver pair, skip validation, tracing profiles, Golden catalog +
selection + favorites, Golden GPU order A/B + active swap (restored this
pass), interface prefs (columns, refresh interval, density), section reset +
reset-all with ownership boundaries, accounts handoff line. Status: PARITY.
