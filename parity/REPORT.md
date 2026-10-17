# Legacy-vs-Vue Parity Report

Generated from `parity/manifest.json` at 2026-10-17T17:29:00.455319+00:00 (sha 5a11c0565ca5d30ea0fa9b852ec06fd04a54fdd1).
The atomic manifest below is authoritative. The legacy smoke section at the end is
LEGACY SMOKE HARNESS OUTPUT — NOT PARITY VERDICTS and never enters totals.

## Totals by contract type

| scope | PASS | FAIL | UNKNOWN | NA | INTENTIONAL_CHANGE |
|---|---|---|---|---|---|
| product_behavior | 54 | 113 | 208 | 0 | 0 |
| migration_architecture | 8 | 0 | 0 | 0 | 2 |
| retirement | 0 | 0 | 0 | 9 | 0 |
| Total | 62 | 113 | 208 | 9 | 2 |

## Atomic matrix

| id | scope | area | behavior | status | required / current | reason |
|---|---|---|---|---|---|---|
| LATEST-READS | product_behavior | async | Workflow/version/detail reads use latest-wins primitive | UNKNOWN | RACE / UNIT | Primitive + wiring unit-tested; actual late-completion ordering unproven. |
| LATEST-HISTORY | product_behavior | async | History feed/detail reads use latest-wins; entity may update cache but never steal focus | UNKNOWN | RACE / STATIC | Primitive wired; no History-specific race test. |
| LATEST-REFRESH | product_behavior | async | Inventory/settings refresh reads use latest-wins | UNKNOWN | RACE / STATIC | Wiring exists; no store race tests. |
| LATEST-MUTATIONS | product_behavior | async | Mutations (favorite/note/delete/save) complete; navigation never cancels server write | UNKNOWN | INTEGRATION / STATIC | Primitive documents policy; mutation call sites not exhaustively verified. |
| LATEST-SHARED | product_behavior | async | Reads use shared latest.ts where newest-read-commit semantics match; specialized ownership tokens (owner identity, upload token, overlay invalidation) are legitimate where semantics differ | UNKNOWN | STATIC / STATIC | Per-site appropriateness unverified: sourceToken may be legitimate specialization, latest.ts gaps may exist. Needs review, not a rewrite mandate. |
| POLL-ABORT | product_behavior | async | Long-running operations (deploy, model install/download, node publication/rebuild, inventory/status): one domain owner; no duplicate poll loops; route navigation does NOT automatically kill the operation; rerender/reopen never creates a second owner; terminal/dispose/replacement stops the poll when appropriate; no zombie timers/listeners; domain owns success/failure semantics | PASS | RACE / STATIC,RACE | Single-owner contract proven with the real primitives (pollUntil + registry + domain AbortController): reentry reuses the owner, terminal/dispose stops with no zombie calls, navigation-without-abort never kills the run. Production owners (infra deploy/swap) hold the same guards in source (deploymentOperationId/swapOperationId single-flight). |
| POLL-TERMINAL | product_behavior | async | Polling terminates on done/abort (no runaway loop after rerender) | PASS | UNIT / UNIT | done()/abort termination directly tested. |
| POLL-RUN | product_behavior | async | Run progress/status integrated with run-controller identity and terminal semantics (controller owns semantics, not the generic poller) | PASS | INTEGRATION / STATIC,INTEGRATION | Run path integrated with controller identity/terminal semantics; the generic poller owns only mechanics and is not on the run path. |
| OPS-DUP-BUSY | product_behavior | operations | No second generic operation registry and no conflicting busy authority beside operationStore (domain runState/isBusy as semantic truth is allowed) | PASS | INTEGRATION / STATIC,INTEGRATION | Registry stays a visibility summary: runState projection and registry transitions proven non-conflicting (cancel/success settle both exactly once; terminal freeze backstops). |
| OPS-TERMINAL | product_behavior | operations | Terminal operation states freeze (first-wins, no regression) | PASS | UNIT / UNIT | Terminal freeze explicitly tested. |
| OPS-IDS | product_behavior | operations | Operation IDs unique; cleanup on terminal/remount | UNKNOWN | BROWSER / STATIC | Unique generation exists; lifecycle/remount behavior unproven. |
| WS-MIDOP | product_behavior | operations | Workspace switch mid-operation cannot retarget submitted request | UNKNOWN | RACE,REAL_BACKEND / STATIC | Run payloads carry no workspace by design (browser does not invent dispatch ownership; server dispatch owns the boundary). Dispatch-seam proof still needs a live backend; row stays UNKNOWN per batch policy. |
| WS-GUARD | product_behavior | operations | Accepted operation stays bound to its accepted workspace; switching active workspace changes future operations only; current operation never retargeted | PASS | RACE / STATIC,RACE | Accepted operation keeps its frozen workspace target across an active-workspace switch; patch() cannot retarget; future operations capture the new id. No blocking guard added (existing selectWorkspace behavior untouched). |
| OPS-ONE-ROOT | migration_architecture | operations | Exactly one Vue app root is mounted (no per-page apps) | PASS | STATIC / STATIC | Single host mount + single StudioApp root in source; structural. |
| OPS-ONE-PINIA | migration_architecture | operations | Exactly one Pinia instance in production source | PASS | STATIC / STATIC | One createPinia in production source (studio.ts:33); test files use isolated instances, which is correct. |
| OPS-ONE-REGISTRY | migration_architecture | operations | Exactly one generic operation registry exists | PASS | STATIC / STATIC | Reviewed: infrastructure.ts holds only single-flight id refs (deploymentOperationId/swapOperationId) and projects every visible summary into operations.* — no second registry exists. |
| OPS-NO-EXEC-AUTH | migration_architecture | operations | Operation registry never decides execution semantics (terminal, identity, status meaning, retry) | PASS | STATIC / STATIC | Module contract explicitly disclaims every execution decision; structural source proof adequate. |
| CANVAS-PROMPT | product_behavior | canvas compatibility | /prompt interception preserved for canvas path | UNKNOWN | REAL_BACKEND / STATIC | Deferred, no runtime proof. |
| CANVAS-PASSTHROUGH | product_behavior | canvas compatibility | Cloud/Local pass-through + enable/disable preserved | UNKNOWN | REAL_BACKEND / STATIC | Commented contract only; no enable-state implementation. |
| CANVAS-MARKERS | product_behavior | canvas compatibility | Production graph markers/bypass preserved | UNKNOWN | REAL_BACKEND / STATIC | Vue projection does not implement or test markers. |
| CANVAS-PROJECTION | product_behavior | canvas compatibility | Output options projected server -> legacy mirror one-way (never read back) | UNKNOWN | INTEGRATION / STATIC | Write path implemented; one-way effect on canvas unproven. |
| CANVAS-FALLBACK | product_behavior | canvas compatibility | localStorage fallback keys keep working during transition | UNKNOWN | INTEGRATION / STATIC | Fallback keys written; fallback behavior unproven. |
| CANVAS-CURRENT-SETTINGS | product_behavior | canvas compatibility | Canvas submission uses current Settings after projection | UNKNOWN | REAL_BACKEND / STATIC | Snapshot/global built; request integration is legacy-only. |
| CANVAS-POST-CLOSE | product_behavior | canvas compatibility | Studio close leaves canvas submission behavior unchanged | UNKNOWN | BROWSER / STATIC | No Vue close/cleanup evidence in compatibility/host code. |
| PERSIST-OPTIN | product_behavior | persistence | Durable state is explicit opt-in (never whole-store) | PASS | STATIC / STATIC | Opt-in helper contract adequate for this structural invariant. |
| PERSIST-PROHIBITED | product_behavior | persistence | Server entities / operation state / compare / run identity / pixels never persist | PASS | STATIC / STATIC | Helper contract prohibits; no entity persistence mechanism shown. |
| PERSIST-MALFORMED | product_behavior | persistence | Malformed JSON / old shapes fall back safely (Zod rejection) | PASS | UNIT / UNIT | Defensive parser + schema fallback directly tested. |
| PERSIST-RELOAD | product_behavior | persistence | Browser-only UI preferences restore on reload | UNKNOWN | BROWSER / STATIC | Persisted values exist; reload-restore behavior unproven. |
| XTAB-KINDS | product_behavior | cross-tab | Settings/workspace/history/workflows broadcast kind-only invalidation | UNKNOWN | BROWSER / STATIC | Equivalent vocabulary wired; no cross-tab test found. |
| XTAB-NO-ENTITIES | product_behavior | cross-tab | Messages carry invalidation only, never entity state | UNKNOWN | BROWSER / STATIC | Payload shape matches; receiver/refetch behavior untested. |
| XTAB-REFETCH | product_behavior | cross-tab | Receiving tab refetches server truth (no full-entity broadcast) | UNKNOWN | BROWSER / STATIC | Refetch-on-invalidate behavior unproven. |
| XTAB-CLEANUP | product_behavior | cross-tab | Listeners cleaned up on dispose; same-tab Pinia never relies on BroadcastChannel | UNKNOWN | BROWSER / STATIC | Removal implemented; cleanup test absent. |
| XTAB-NO-BUS | retirement | cross-tab | Same-tab recent-run entity bus retired (invalidation-only) | NA | STATIC / STATIC | Blueprint 4.1 explicitly retires the same-tab entity bus. |
| PERSIST-NO-SERVER-AUTH | product_behavior | persistence | Server /config and entity/operation state are never treated as browser authority on reload | PASS | STATIC / STATIC | No mechanism persists entities/operations as authority; structural invariant holds. |
| CMP-SELECT | product_behavior | compare | Select A and B images | UNKNOWN | BROWSER / STATIC | Slots store-backed; selection behavior unproven. |
| CMP-SWAP | product_behavior | compare | Replace/swap A/B | UNKNOWN | BROWSER / STATIC | Switch control visible in source; behavior unproven. |
| CMP-VIEWER | product_behavior | compare | Side-by-side viewer with divider control | UNKNOWN | BROWSER / STATIC | Wells rendered in source; viewer interaction unproven. |
| CMP-EXIT | product_behavior | compare | Exit compare clears transient state | UNKNOWN | BROWSER / STATIC | Clear path exists; behavior unproven. |
| CMP-DELETED | product_behavior | compare | Deleted record in compare slot renders explicit state | UNKNOWN | BROWSER / STATIC | Explicit state rendered in source; behavior unproven. |
| CMP-TRANSIENT | product_behavior | compare | Compare A/B never durably persists (transient two slots) | UNKNOWN | BROWSER / STATIC | No persistence mechanism found, but reload behavior unproven. |
| CMP-HANDOFF | product_behavior | compare | History/picker-to-compare handoff end to end | UNKNOWN | BROWSER / STATIC | Components exist separately; complete handoff undemonstrated. |
| WF-LIBRARY | product_behavior | workflows | Workflow library list + select + detail | UNKNOWN | BROWSER / STATIC | Wired in source; library behavior unproven. |
| WF-FILTERS | product_behavior | workflows | Search/folder/tag filters | UNKNOWN | BROWSER / STATIC | Filters + inventories present; behavior unproven. |
| WF-CRUD | product_behavior | workflows | Workflow create/update/delete | UNKNOWN | BROWSER / STATIC | Paths wired; behavior + persistence unproven. |
| WF-VERSIONS | product_behavior | workflows | Version list, select, capture | UNKNOWN | BROWSER / STATIC | Version paths exist; behavior unproven. |
| WF-MAPPING | product_behavior | workflows | Mapping save vs revision distinction + confirmation | UNKNOWN | BROWSER / STATIC | Store/API distinction found; confirmation UI incomplete. |
| WF-DEPS | product_behavior | workflows | Dependency data loaded into manager context | UNKNOWN | BROWSER / STATIC | Data loaded; visible detail behavior unproven. |
| WF-COMPAT | product_behavior | workflows | Compatibility + portability reports visible per version | UNKNOWN | BROWSER / STATIC | Reports loaded into state; visible UI + runtime unproven. |
| WF-MANIFEST | product_behavior | workflows | Manifest import/export round trip | UNKNOWN | BROWSER / STATIC | API functions exist; visible workflow unconfirmed. |
| WF-SHARED-SELECT | product_behavior | workflows | Selected version shared between Workflows and Playground | UNKNOWN | BROWSER / STATIC | Shared selection visible; cross-page behavior unproven. |
| WF-STALE-READ | product_behavior | workflows | Stale workflow/version reads cannot commit over newer selection | UNKNOWN | RACE / STATIC | Latest-task guards explicit; race behavior unproven. |
| WF-FOLDERS | product_behavior | workflows | Folder create + tag inventory persist | UNKNOWN | BROWSER / STATIC | Inventories exist; behavior unproven. |
| SRC-UPLOAD | product_behavior | edit/source | Source upload binds real filename into controls | UNKNOWN | BROWSER / STATIC | Upload path exists; runtime binding unproven. |
| SRC-LATEST-WINS | product_behavior | edit/source | Latest upload wins; token+owner guard discards stale completions | UNKNOWN | RACE / UNIT | Token+owner guard unit-tested; true concurrency race unproven. |
| SRC-OWNER-SWITCH | product_behavior | edit/source | Owner change (workflow/tool switch) invalidates pending upload | UNKNOWN | RACE / UNIT | Context-switch discard unit-tested; mid-upload switch race unproven. |
| SRC-FAIL-OWNER | product_behavior | edit/source | Upload failure surfaces only on current owner | UNKNOWN | BROWSER / STATIC | No runtime failure-path evidence. |
| SRC-FROM-HISTORY | product_behavior | edit/source | Source from History/previous generation binds real file | FAIL | BROWSER / STATIC | Browse event exists; end-to-end history-to-source binding absent. |
| SRC-DRAGDROP | product_behavior | edit/source | Drag/drop ingests source image | FAIL | BROWSER / STATIC | No Vue drag/drop evidence found. |
| SRC-PASTE | product_behavior | edit/source | Paste ingests source image | FAIL | BROWSER / STATIC | No Vue paste evidence found. |
| SRC-CLEAR-MASK | product_behavior | edit/source | Clear source also clears dependent mask/selection state | UNKNOWN | BROWSER / STATIC | Vue clear exists; legacy parity of dependent clearing unverified. |
| SRC-SHARED-IDENTITY | product_behavior | edit/source | Source identity shared correctly across Edit subtools | UNKNOWN | BROWSER / STATIC | Ownership refs exist; no cross-subtool identity test. |
| SEL-BRUSH | product_behavior | edit/select | Brush selection paints mask | FAIL | BROWSER / STATIC | No Vue selection editor. |
| SEL-ERASE | product_behavior | edit/select | Erase selection | FAIL | BROWSER / STATIC | No Vue evidence. |
| SEL-LASSO | product_behavior | edit/select | Lasso selection | FAIL | BROWSER / STATIC | No Vue evidence. |
| SEL-RECT | product_behavior | edit/select | Rectangle selection | FAIL | BROWSER / STATIC | No Vue evidence. |
| SEL-MASK-OPS | product_behavior | edit/select | Combine/add, grow, feather, invert mask ops | FAIL | BROWSER / STATIC | No Vue evidence. |
| SEL-UNDO | product_behavior | edit/select | Selection undo/redo/clear | FAIL | BROWSER / STATIC | No Vue evidence. |
| SEL-SAM3 | product_behavior | edit/select | SAM3 object selection (points/boxes) | FAIL | BROWSER / STATIC | No Vue SAM route/UI evidence. |
| SEL-DETECT | product_behavior | edit/select | SAM3 text/detect selection | FAIL | BROWSER / STATIC | No Vue Detect path. |
| SEL-OWNERSHIP | product_behavior | edit/select | Mask + source share widget identity in request | UNKNOWN | REAL_BACKEND / STATIC | Generic role detection is not shared-editor ownership proof; exact binding needs backend. |
| SEL-MASK-GATE | product_behavior | edit/select | Mask-required run gating blocks maskless inpaint submit | UNKNOWN | BROWSER / STATIC | No Select-specific mask gate; blocked-run behavior unproven. |
| SEL-CROPSTITCH | product_behavior | edit/select | Crop+Stitch execution method | FAIL | INTEGRATION / STATIC | No Vue method implementation. |
| SEL-COND-CROP | product_behavior | edit/select | Conditioning + Crop-Stitch method | FAIL | INTEGRATION / STATIC | No Vue method implementation. |
| SEL-DEDICATED | product_behavior | edit/select | Dedicated override method + method switching preserves mask/source | FAIL | INTEGRATION / STATIC | No Vue method state. |
| SEL-PAYLOAD | product_behavior | edit/select | Inpaint request serializes source, mask, method exactly | UNKNOWN | INTEGRATION / STATIC | Generic payload freeze is not Select mapping proof; needs exact capture. |
| SEL-STALE-MASK | product_behavior | edit/select | Source replacement clears stale mask/SAM result | UNKNOWN | BROWSER / STATIC | Clear path clears mask; replacement-path invalidation unproven. |
| EXPAND-GEOMETRY | product_behavior | edit/expand | Expand padding controls and geometry | FAIL | BROWSER / STATIC | No Vue Expand editor. |
| EXPAND-PAD | product_behavior | edit/expand | Pad Canvas method | FAIL | INTEGRATION / STATIC | No Vue method. |
| EXPAND-PRESERVE | product_behavior | edit/expand | Pad+Preserve method and Dedicated override | FAIL | INTEGRATION / STATIC | No Vue methods. |
| EXPAND-PAYLOAD | product_behavior | edit/expand | Expand geometry serializes into request; replacement invalidates stale state | FAIL | INTEGRATION / STATIC | No Vue serialization or state implementation. |
| EXPAND-PREVIEW | product_behavior | edit/expand | Expand preview reflects padding/geometry before run | UNKNOWN | BROWSER / STATIC | Central stage has image/status only; no Expand preview. |
| POST-ADJUST | product_behavior | post | Adjust tool controls + engine behavior + ownership | FAIL | BROWSER / STATIC | No specialized Adjust panel; generic controls only. |
| POST-COLOR | product_behavior | post | Color tool controls + engine behavior + ownership | FAIL | BROWSER / STATIC | No Vue evidence. |
| POST-DETAIL | product_behavior | post | Detail tool controls + engine behavior + ownership | FAIL | BROWSER / STATIC | No Vue evidence. |
| POST-EFFECTS | product_behavior | post | Effects tool controls + engine behavior + ownership | FAIL | BROWSER / STATIC | No Vue evidence. |
| POST-CROP | product_behavior | post | Crop tool controls + engine behavior + ownership | FAIL | BROWSER / STATIC | No Vue evidence. |
| POST-HEAL | product_behavior | post | Heal tool controls + engine behavior + ownership | FAIL | BROWSER / STATIC | No Vue evidence. |
| POST-LOOKS | product_behavior | post | Saved Looks owned separately from workflow presets | UNKNOWN | BROWSER / STATIC | Design contract exists; Vue Looks implementation absent. |
| POST-UPSCALE-PARKED | product_behavior | post | Upscale stays a placeholder; no invented execution | UNKNOWN | BROWSER / STATIC | Placeholder explicitly represented; disabled-state needs browser check. |
| CANVAS-BASE | product_behavior | canvas rule | Central stage holds image/content only in base state | UNKNOWN | BROWSER / STATIC | Source shows image/status branches; live DOM unproven. |
| CANVAS-SELECT | product_behavior | canvas rule | Select overlays render inside central stage, aligned to image | FAIL | BROWSER / STATIC | No Vue Select overlay exists. |
| CANVAS-EXPAND | product_behavior | canvas rule | Expand direct-manipulation overlays render inside stage | FAIL | BROWSER / STATIC | No Vue Expand overlay. |
| CANVAS-SKETCH | product_behavior | canvas rule | Sketch overlays are stage-local direct manipulation | FAIL | BROWSER / STATIC | Comment/state mention is not overlay evidence. |
| CANVAS-NO-CONTROLS | product_behavior | canvas rule | Post/inspector controls never persist inside central stage | UNKNOWN | BROWSER / STATIC | Placement structurally suggested (controls at :607); browser DOM unproven. |
| CANVAS-SWITCH | product_behavior | canvas rule | Tool switching preserves image identity without stale overlays | UNKNOWN | BROWSER / STATIC | Clear semantics exist; overlay lifecycle absent so transition unproven. |
| TXT-PROMPT | product_behavior | generate/text | Prompt + negative prompt entry and display | UNKNOWN | BROWSER / STATIC | Prompt roles render; entry/display behavior unproven. |
| TXT-PAYLOAD | product_behavior | generate/text | Text serialized into request with workflow/version ownership | UNKNOWN | INTEGRATION / STATIC | Payload mapping exists; accepted-by-backend shape unproven. |
| TXT-RESULT | product_behavior | generate/text | Generated result displays; recent History converges | UNKNOWN | BROWSER / STATIC | Identity-only projection exists; display + convergence unproven. |
| REF-ADD-REMOVE | product_behavior | generate/references | Add and remove references (ordered cards) | UNKNOWN | BROWSER / STATIC | Cards exist; interaction behavior unproven. |
| REF-REPLACE | product_behavior | generate/references | Replace a reference in place | FAIL | BROWSER / STATIC | Vue exposes add/remove only; no replace action. |
| REF-ORDER | product_behavior | generate/references | Multiple references keep order into payload | UNKNOWN | BROWSER / STATIC | Array order retained in source; ordering behavior unproven. |
| REF-WEIGHTS | product_behavior | generate/references | Reference strength/weight settings exist exactly for real Reference Methods that support them (no universal slider) | FAIL | BROWSER / STATIC | Vue has no reference-method UI at all, so method-conditional weights cannot exist. Part of the broader methods gap. |
| REF-DRAFT-PERSIST | product_behavior | generate/references | Reference draft metadata persists across reload | FAIL | BROWSER / STATIC | References not covered by Vue draft persistence. |
| REF-UPLOAD-RACE | product_behavior | generate/references | Reference upload ownership; stale reference upload discarded | UNKNOWN | RACE / STATIC | Reference upload path has no ownership/stale guard. |
| REF-SOURCE-SEPARATION | product_behavior | generate/references | Source image kept distinct from references in payload | UNKNOWN | INTEGRATION / STATIC | Separation exists in source; serialization behavior unproven. |
| REF-BINDING | product_behavior | generate/references | Reference candidate/method/binding structure matches mapping | UNKNOWN | REAL_BACKEND / STATIC | Vue sends filenames/items; legacy candidate/method/binding structure absent. |
| LAY-OPEN | product_behavior | generate/layout | Layout editor opens with boxes/captions/geometry | FAIL | BROWSER / STATIC | No Layout editor UI in Vue. |
| LAY-GEOMETRY | product_behavior | generate/layout | Layout geometry/coordinate conversion/resize | FAIL | BROWSER / STATIC | No layout model in Vue. |
| LAY-TEMPLATES | product_behavior | generate/layout | Layout templates, drafts, clear/reset persist | FAIL | BROWSER / STATIC | No layout template or draft state in Vue. |
| LAY-PAYLOAD | product_behavior | generate/layout | Layout serializes into request with image/base ownership | FAIL | INTEGRATION / STATIC | No layout field or request mutation path in Vue. |
| HIST-FEED | product_behavior | history | History V2 feed loads generations and experiments | UNKNOWN | BROWSER / STATIC | Feed call exists; loaded-and-rendered behavior unproven. |
| HIST-PAGINATION | product_behavior | history | Cursor pagination / load-more | UNKNOWN | BROWSER / STATIC | API shape present; visible load-more unconfirmed. |
| HIST-QUERY | product_behavior | history | Search, filter, sort wired to feed | UNKNOWN | BROWSER / STATIC | Controls wired; query-behavior needs browser proof. |
| HIST-VIEWSTATE | product_behavior | history | Filter/sort state persists across reload | UNKNOWN | BROWSER / STATIC | Viewstate persisted; reload-restore unproven. |
| HIST-FOCUS | product_behavior | history | Record focus state + focus route loads detail on demand | UNKNOWN | BROWSER / STATIC | Store + route focus implemented; focus behavior unproven. |
| HIST-STALE-FOCUS | product_behavior | history | Stale detail/query responses cannot steal focus | UNKNOWN | RACE / STATIC | Latest-task guards present; race behavior unproven. |
| HIST-FAVORITE | product_behavior | history | Favorite toggle with optimistic update + rollback + persistence | UNKNOWN | BROWSER / STATIC | Toggle path exists; user-visible toggle + persistence unproven. |
| HIST-NOTE | product_behavior | history | Note save on generation and experiment | UNKNOWN | BROWSER / STATIC | Note endpoints exist; save behavior unproven. |
| HIST-DELETE | product_behavior | history | Single delete with confirm + feed update | UNKNOWN | BROWSER / STATIC | Confirm + removal wired; behavior unproven. |
| HIST-BULK-DELETE | product_behavior | history | Bulk delete with selection | UNKNOWN | BROWSER / STATIC | Selection + bulk endpoint wired; behavior unproven. |
| HIST-RECENT | product_behavior | history | Recent runs converge with History (Playground strip) | PASS | INTEGRATION / STATIC,INTEGRATION | Run completion converges history recentRunIds (id-only, no entity cache); full entities converge via the existing History V2 feed. Visual strip is a later feature lane. |
| HIST-ORIGINAL | product_behavior | history | Generate Original and Retry Original are distinct actions/endpoints | UNKNOWN | BROWSER / STATIC | Separate actions exist; distinct user-visible behavior unproven. |
| HIST-RESUME | product_behavior | history | Single Resume resumes generation (not an Original action) | UNKNOWN | BROWSER / STATIC | Resume action exists; behavior unproven. |
| HIST-CELL-RETRY | product_behavior | history | Experiment cell retry from History | UNKNOWN | BROWSER / STATIC | Cell-ID path explicit; retry behavior unproven. |
| HIST-EXP-CANCEL-RESUME | product_behavior | history | Experiment cancel/resume from History | UNKNOWN | BROWSER / STATIC | Actions represented; behavior unproven. |
| HIST-DOWNLOAD-EXPORT | product_behavior | history | Browser Download (single asset, blob) vs configured-folder Export | UNKNOWN | BROWSER / STATIC | API/store paths found; click behavior + configured-export control unproven. |
| HIST-IMMUTABLE-REPLAY | product_behavior | history | Replay uses immutable execution params (browser never resends) | UNKNOWN | INTEGRATION / STATIC | Params normalized as record data; immutability unproven by test. |
| HIST-GEN-DETAIL | product_behavior | history | Generation detail renders full record | UNKNOWN | BROWSER / STATIC | Detail path exists; rendered behavior unproven. |
| HIST-EXP-DETAIL | product_behavior | history | Experiment detail renders cells/counts | UNKNOWN | BROWSER / STATIC | Model supports cells; full rendered detail unconfirmed. |
| HIST-COLUMNS | product_behavior | history | Column/density preferences respected + persisted | UNKNOWN | BROWSER / STATIC | Preference read exists; behavior + persistence unproven. |
| HIST-PICKER | product_behavior | history | History picker filters, paginates, focuses, hands selection | UNKNOWN | BROWSER / STATIC | Dialog exists; filtering/pagination/focus/handoff parity not evidenced. |
| HIST2-USE-CURRENT | product_behavior | history | History item hands off as current image | UNKNOWN | BROWSER / STATIC | Handoff accepted; Vue behavior unverified. |
| HIST2-EDIT-REF | product_behavior | history | History item hands off to Edit and to Use as Reference | UNKNOWN | BROWSER / STATIC | Handoffs accepted; Vue behavior unverified. |
| HIST2-POST-HANDOFF | product_behavior | history | History item hands off to Post Process with identity/metadata intact | UNKNOWN | BROWSER / STATIC | Handoff accepted; Vue behavior unverified. |
| HIST2-DELETED | product_behavior | history | Deleted history target yields clear unavailable state, never stale data, on handoff | UNKNOWN | BROWSER / STATIC | Deleted-state accepted; Vue behavior unverified. |
| CMP2-INTERACT | product_behavior | compare | Compare divider drags; pan/zoom affect viewport without corrupting selection | UNKNOWN | BROWSER / STATIC | Interactions accepted; Vue behavior unverified. |
| CMP2-FIT | product_behavior | compare | Compare offers Fit and 1:1 viewport scales | UNKNOWN | BROWSER / STATIC | View modes accepted; Vue behavior unverified. |
| CMP2-TRANSIENT-IO | product_behavior | compare | Transient compare inputs never become persistent history entries | UNKNOWN | BROWSER / STATIC | Transient lifecycle accepted; Vue behavior unverified. |
| CMP2-NO-REVIVAL | retirement | compare | Comparison Profiles/Runner stay retired (no revival) | NA | STATIC / STATIC | Retirement binding; absence holds in current Vue surface. |
| P12-IDENTITY | product_behavior | presets | Saved workflow keeps workflow identity, version identity, and saved-workflow identity vocabulary | UNKNOWN | BROWSER / STATIC | Identity accepted; Vue behavior unverified. |
| P12-REOPEN | product_behavior | presets | Reopen restores mode, subtool, and saved sidebar values semantically | UNKNOWN | BROWSER / STATIC | Reopen accepted; Vue behavior unverified. |
| P12-LABELS | product_behavior | presets | Display-label overrides and relabeling never alter semantic identity | UNKNOWN | BROWSER / STATIC | Label/identity split accepted; Vue behavior unverified. |
| P12-PROMPT | product_behavior | presets | Hidden task prompt, visible default prompt, preset-only/user-only/combined cases compose deterministically | UNKNOWN | BROWSER / STATIC | Composition accepted; Vue behavior unverified. |
| P12-METHOD | product_behavior | presets | Saved workflow keeps selected execution method identity where task-owned | UNKNOWN | BROWSER / STATIC | Method identity accepted; Vue behavior unverified. |
| P12-EMPTY-IMAGES | product_behavior | presets | Source/reference/mask images reopen empty; no stale image state restored | UNKNOWN | BROWSER / STATIC | Empty-reopen accepted; Vue behavior unverified. |
| P12-PROVENANCE | product_behavior | presets | Run-local overrides and replay provenance stay separate from saved identity; final submitted prompt traceable | UNKNOWN | BROWSER / STATIC | Separation accepted; Vue behavior unverified. |
| P13-CHAIN | product_behavior | integration | Current-image chaining works; explicit source replacement supersedes lineage | UNKNOWN | BROWSER / STATIC | Integration flow accepted; Vue end-to-end unverified. |
| P13-STALE | product_behavior | integration | Source/mode/subtool switches clear stale masks, overlays, and controls | UNKNOWN | BROWSER / STATIC | Cleanup accepted; Vue end-to-end unverified. |
| P13-FAMILIES | product_behavior | integration | T2I/I2I families separated; legacy specialized workflows stay compatible | UNKNOWN | BROWSER / STATIC | Family separation accepted; Vue cross-family unverified. |
| P13-HONEST | product_behavior | integration | Honest placeholders with gate reasons; truthful async status; actionable dependency failures | UNKNOWN | BROWSER / STATIC | Honesty contract accepted; Vue runtime paths unverified. |
| P13-IDENTITY | product_behavior | integration | Queue and Experiment identity stable across submission and reload | UNKNOWN | BROWSER / STATIC | Identity accepted; Vue queue/reload unverified. |
| P13-SNAPSHOT | product_behavior | integration | Queue snapshot carries subtool, methods, references, style, guidance, workflow/version, controls, request state | PASS | INTEGRATION / STATIC,INTEGRATION | Queue/enqueue path freezes the full Phase-13 snapshot (subtool, methods, references, style, guidance, layout, workflow/version, controls, request state); network capture proves the frozen payload reaches POST. |
| HOST-LAUNCHER | product_behavior | host/modal | Sidebar launcher opens Studio | UNKNOWN | BROWSER / STATIC | Both openers exist in source; no browser proof of launcher behavior. |
| HOST-FALLBACK | product_behavior | host/modal | Fallback launcher when sidebar registration unavailable | UNKNOWN | BROWSER / STATIC | Vue host assumes host caller; no independent fallback implemented or tested. |
| HOST-WINDOW-API | product_behavior | host/modal | window.open_testing_modal / window.close_testing_modal entrypoints preserved | UNKNOWN | BROWSER / STATIC | Entrypoint names not compared at runtime. |
| HOST-SINGLE-MOUNT | product_behavior | host/modal | Vue app mounts once, reused across opens | UNKNOWN | BROWSER / STATIC | Mount-count guard exists; not browser-verified. |
| HOST-FOCUS-CAPTURE | product_behavior | host/modal | Open captures trigger element | UNKNOWN | BROWSER / STATIC | Source shows capture, not runtime focus outcome. |
| HOST-FOCUS-RESTORE | product_behavior | host/modal | Close restores focus to opener | UNKNOWN | BROWSER / STATIC | No browser focus assertion found. |
| HOST-SCROLL-LOCK | product_behavior | host/modal | Body scroll locked while open, released on close | UNKNOWN | BROWSER / STATIC | CSS/source only; no repeated open/close browser test. |
| HOST-INERT | product_behavior | host/modal | Background inert + aria-hidden applied and restored (incl. pre-existing attrs) | UNKNOWN | BROWSER / STATIC | Restoration of pre-existing attributes needs runtime proof. |
| HOST-ARIA-MODAL | product_behavior | host/modal | aria-modal=true represents normal modal ownership | UNKNOWN | BROWSER / STATIC | No DOM-state browser evidence. |
| HOST-ESCAPE | product_behavior | host/modal | Escape closes topmost layer; nested portalled layers own Escape first | UNKNOWN | BROWSER / STATIC | No browser test for nested Escape ordering. |
| HOST-BACKDROP | product_behavior | host/modal | Backdrop click closes main modal | UNKNOWN | BROWSER / STATIC | No browser interaction evidence. |
| HOST-CLOSE-SUPPRESS | product_behavior | host/modal | Explicit close suppresses refresh auto-reopen | UNKNOWN | BROWSER / STATIC | Vue documents no auto-reopen (preview); no refresh test. |
| HOST-AUTOREOPEN | product_behavior | host/modal | Same-tab refresh auto-reopens Studio on last page (explicit close suppresses) | FAIL | BROWSER / STATIC | Vue preview explicitly skips auto-reopen; blueprint 2.2 MUST requires refresh/session reopen. |
| HOST-EXPLICIT-OPENER | product_behavior | host/modal | Reopen honors hash unless explicit opener supplies page | UNKNOWN | BROWSER / UNIT | Router precedence unit-tested; host opener integration unverified. |
| HOST-NO-DUP-ESC | product_behavior | host/modal | Repeated open/close does not duplicate Escape listeners | UNKNOWN | RACE / STATIC | Listener guards exist both sides; no race evidence. |
| HOST-NO-DUP-WIZ | product_behavior | host/modal | Repeated mount does not duplicate wizard listeners | UNKNOWN | RACE / STATIC | Vue guard exists; no race evidence. |
| HOST-WIZARD-MODE | product_behavior | host/modal | Wizard graph mode releases inert + aria-modal; close restores containment | UNKNOWN | BROWSER / STATIC | Seam exists; no browser proof with real wizard open. |
| HOST-CLOSE-BUTTON | product_behavior | host/modal | Single Studio close affordance; host fallback hidden after bundle ready | UNKNOWN | BROWSER / STATIC | No visual/focus browser verification. |
| HOST-LEGACY-RESTORE | product_behavior | host/modal | Close restores parked legacy overlay and host chrome | UNKNOWN | BROWSER / STATIC | Source-supported but unverified in mixed legacy/Vue runtime. |
| HOST-WIZARD-REOPEN | product_behavior | host/modal | Pending wizard draft forces reload back to Workflows so the draft can resume | UNKNOWN | BROWSER / STATIC | Vue session draft + resume exist in source; reload-forced reopen behavior unproven. |
| INFRA-WORKSPACES | product_behavior | manage modal | Workspace list + active workspace normalized | UNKNOWN | BROWSER / STATIC | Active ID + rows normalized; behavior unproven. |
| INFRA-SWITCH | product_behavior | manage modal | Workspace switch activates with rollback on failure | UNKNOWN | BROWSER / STATIC | Activation + rollback exist; behavior unproven. |
| INFRA-FROZEN-TARGET | product_behavior | manage modal | In-flight infra operation records frozen workspace target | UNKNOWN | RACE / STATIC | Frozen ID recorded for infra ops; race behavior unproven. |
| INFRA-DEPLOY | product_behavior | manage modal | Deploy/redeploy triggers; readiness/status/logs/failure-retry surface | UNKNOWN | REAL_BACKEND / STATIC | Actions + states wired; deploy behavior needs backend proof. |
| INFRA-REFRESH | product_behavior | manage modal | Inventory refresh with latest-wins; explicit UI refresh semantics | UNKNOWN | RACE / STATIC | Latest-wins protects reads; explicit refresh semantics unchecked. |
| INFRA-MODELS | product_behavior | manage modal | Model list renders presence states distinctly | UNKNOWN | BROWSER / STATIC | Lists display; presence-state mapping not evidenced. |
| INFRA-INSTALL | product_behavior | manage modal | Model install/download full status lifecycle in view | UNKNOWN | BROWSER / STATIC | Install exists; full lifecycle in view unverified. |
| INFRA-NODES | product_behavior | manage modal | Custom-node presence, publication, rebuild wired | UNKNOWN | REAL_BACKEND / STATIC | Refresh/sync/rebuild APIs exist; behavior unproven. |
| INFRA-CREDS | product_behavior | manage modal | Credentials save + status/failure visibility | UNKNOWN | BROWSER / STATIC | Status/save APIs exist; failure/visibility incomplete. |
| INFRA-OPVIS | product_behavior | manage modal | Long operations visible once with IDs/progress/failure (no duplicate busy) | UNKNOWN | BROWSER / STATIC | IDs/progress/failure surfaced; single-visibility + dedup unproven. |
| DEPS-STATES | product_behavior | dependencies | Dependency presence contract is exhaustive and distinct: local-present, Modal-workspace-present, missing, installing, unknown/unverified (each rendered distinctly, none double-counted) | FAIL | BROWSER / STATIC | Vue retains raw records with no normalized presence contract; installing/unknown not distinctly rendered. |
| DEPS-MODEL-GATE | product_behavior | dependencies | Missing-model blocks execution attempt (gate, not badge) | UNKNOWN | BROWSER / STATIC | Flagging surface exists; non-submittable gate needs runtime proof. |
| DEPS-NODE-GATE | product_behavior | dependencies | Missing-node gate honors skip_plan_validation interaction | UNKNOWN | BROWSER / STATIC | No matching Vue gate implementation located. |
| DEPS-STALE-REFRESH | product_behavior | dependencies | Stale inventory refresh never overwrites newer snapshot | UNKNOWN | RACE / STATIC | Latest-task wired; race behavior unproven. |
| MODEL-LIBRARY-PLACE | migration_architecture | manage modal | Model Library (inventory, presence, browsing, install/request, dependency visibility, refresh) lives in Manage Modal, not Workflows | PASS | STATIC / STATIC | Vue BackendView hosts model inventory/install/dependency surfaces; no Model Library in Workflows page. Structural placement holds. |
| PG-WORKFLOW-SELECT | product_behavior | playground | Workflow selection loads run context | UNKNOWN | BROWSER / STATIC | Selection + context load exist; no browser proof. |
| PG-PICKER-FILTERS | product_behavior | playground | Workflow picker offers search/folders (not bare select) | FAIL | BROWSER / STATIC | Vue Playground uses a plain select; no search/folder picker. |
| PG-VERSION-PICK | product_behavior | playground | Version picker lists versions; latest resolved on workflow change | UNKNOWN | BROWSER / STATIC | List + latest-resolution exist; behavior unproven in browser. |
| PG-VERSION-SWITCH | product_behavior | playground | Workflow/version switch reloads values; incompatible values dropped | PASS | UNIT / UNIT | Unit tests prove defaults resolution + incompatible-value drop on switch. |
| PG-SELECTION-PERSIST | product_behavior | playground | Workflow/version selection persists across reload | UNKNOWN | BROWSER / STATIC | Persisted identity exists; reload-restore unproven. |
| PG-DEFAULTS | product_behavior | playground | Control defaults resolve from graph/schema | PASS | UNIT / UNIT | Schema-default resolution directly unit-tested. |
| PG-MODEL-AUTOFILL | product_behavior | playground | UNET/CLIP/VAE autofill from captured workflow values | UNKNOWN | REAL_BACKEND / STATIC | Frontend schema-default path unproven for captured model values; backend run-context evidence required. |
| PG-MODEL-UNET | product_behavior | playground | UNET control is a model picker with populated choices | FAIL | BROWSER / STATIC | Vue renders model roles as text inputs / select-only-with-options; no picker. |
| PG-MODEL-CLIP | product_behavior | playground | CLIP control is a model picker with populated choices | FAIL | BROWSER / STATIC | Same picker gap as UNET. |
| PG-MODEL-VAE | product_behavior | playground | VAE control is a model picker with populated choices | FAIL | BROWSER / STATIC | Same picker gap as UNET. |
| PG-MODEL-OPTIONS | product_behavior | playground | Model dropdown choices populate from graph + backend inventory | FAIL | INTEGRATION / STATIC | Only schema enum options populate selects; model roles have no inventory-backed options. |
| PG-MODEL-ROLES | product_behavior | playground | Model roles registered in control catalog and drive controls | UNKNOWN | INTEGRATION / STATIC | Roles exist in Vue API catalog; that they drive controls with correct values is unproven. |
| PG-SEED-RANDOMIZE | product_behavior | playground | Seed randomize action produces a fresh draw (-1 = random semantics kept) | UNKNOWN | BROWSER / STATIC | Randomize button exists; bounds/rules differ (Vue random range) and fresh-draw behavior needs browser proof. |
| PG-SELECT | product_behavior | playground | Select controls render options and coerce values | UNKNOWN | BROWSER / STATIC | Enum selects render; coercion/selection behavior unproven. |
| PG-BOOLEAN | product_behavior | playground | Boolean/toggle controls emit booleans into payload | UNKNOWN | BROWSER / STATIC | Toggle renders; payload emission unproven. |
| PG-TEXT | product_behavior | playground | Prompt/multiline text entry into payload | UNKNOWN | BROWSER / STATIC | Textareas render; entry-to-payload behavior unproven in browser. |
| PG-ADV-DISCLOSURE | product_behavior | playground | Advanced is a collapsible disclosure (not a static group) | FAIL | BROWSER / STATIC | Advanced renders as an always-open group; no collapse affordance. |
| PG-ADV-PERSIST | product_behavior | playground | Advanced open/closed state persists | FAIL | BROWSER / STATIC | No disclosure state exists to persist. |
| PG-CONTROL-ORDER | product_behavior | playground | Controls follow user-defined order/rows | FAIL | BROWSER / STATIC | Vue has deterministic group order only; no user layout order. |
| PG-ORDER-PERSIST | product_behavior | playground | Control order/rows persist across reload | FAIL | BROWSER / STATIC | Vue persists values only; no order/row layout state. |
| PG-METHOD-SELECT | product_behavior | playground | Method selectors choose execution method and enter payload | FAIL | BROWSER / STATIC | Store holds workflowMethods but no selector UI or mutation path found. |
| PG-DIRTY | product_behavior | playground | Dirty-state semantics: preset dirty vs run-state reset | UNKNOWN | BROWSER / STATIC | Preset dirty present; broader legacy dirty/run-state reset semantics not evidenced. |
| PG-RUN-GATE | product_behavior | playground | Run enable/disable gate matrix (loading/error/runnable/required/busy/placeholder) | UNKNOWN | BROWSER / STATIC | Gate conditions exist; matrix behavior (incl. missing-model block) unproven. |
| PG-PAYLOAD | product_behavior | playground | Run request payload shape: workflow/version/controls identity to POST /studio/run | UNKNOWN | INTEGRATION / STATIC | Payload built and frozen; backend-accepted shape unproven without integration capture. |
| PG-FREEZE | product_behavior | playground | Submitted request frozen before async submission | PASS | UNIT / UNIT | Freeze-before-network directly unit-tested. |
| PG-NUM-MINMAX | product_behavior | playground | Numeric controls enforce min/max (HTML bounds + store validation + draft validation) | PASS | UNIT / UNIT | Bounds enforced in template, store validation, and draft validation; directly tested. |
| PG-NUM-STEP | product_behavior | playground | Numeric step behavior (stepper increments, e.g. step 8 for dimensions) | UNKNOWN | BROWSER / STATIC | Step attributes may render; stepper behavior unproven. |
| PG-SEED-RANGE | product_behavior | playground | Seed-specific range semantics (accepted min/max, -1 random) excluding the randomize action | UNKNOWN | BROWSER / STATIC | Seed bounds/rules differ (Vue random range); range behavior unproven. Randomize action is PG-SEED-RANDOMIZE. |
| POST2-LIGHT | product_behavior | post | Post provides Light controls (exposure/contrast/whites/blacks/shadows/highlights/brightness) | FAIL | BROWSER / STATIC | Accepted control parity; no Vue post workspace. |
| POST2-COLOR | product_behavior | post | Post provides Color controls (temp/tint/vibrance/saturation/hue) | FAIL | BROWSER / STATIC | Accepted control parity; no Vue implementation. |
| POST2-CURVES | product_behavior | post | Post provides Curves controls | FAIL | BROWSER / STATIC | Accepted control parity; no Vue implementation. |
| POST2-MIXER | product_behavior | post | Post provides Mixer and Grading controls | FAIL | BROWSER / STATIC | Accepted control parity; no Vue implementation. |
| POST2-DETAIL-FX | product_behavior | post | Post provides Detail (texture/clarity/dehaze/sharpen/structure) and Effects controls | FAIL | BROWSER / STATIC | Accepted control parity; no Vue implementation. |
| POST2-LUT | product_behavior | post | Post provides LUT library with import/use/favorites | FAIL | BROWSER / STATIC | Accepted LUT behavior; no Vue implementation. |
| POST2-CROP | product_behavior | post | Post provides Crop and Straighten controls | FAIL | BROWSER / STATIC | Accepted control parity; no Vue implementation. |
| POST2-HEAL-WB | product_behavior | post | Post provides Spot heal and white-balance picker tools | FAIL | BROWSER / STATIC | Accepted tool parity; no Vue implementation. |
| POST2-WORKFLOW | product_behavior | post | Post supports presets, filmstrip, batch apply, undo-redo, before/after, export | FAIL | BROWSER / STATIC | Accepted workspace behavior; no Vue implementation. |
| POST2-ORDER | product_behavior | post | Processing order heal -> color/curves/LUT -> dehaze -> spatial -> orient/straighten/crop | FAIL | BROWSER / STATIC | Accepted order; no Vue engine to verify. |
| POST2-RES | product_behavior | post | Preview capped at 1200px long side; export renders full resolution | FAIL | BROWSER / STATIC | Accepted resolution paths; no Vue implementation. |
| POST2-PERSIST | product_behavior | post | Accepted Post user state that is intentionally durable (recipe/current settings, saved Looks/presets, LUT favorites) remains available after migration, via existing keys or a bounded compatibility read/migration into the new persistence mechanism | FAIL | BROWSER / STATIC | Durable-data compatibility is the requirement, not exact storage-key identity — unless a remaining non-Vue consumer needs the exact key. If existing user data under comfymodal.studio.postprocess.* must survive, the port must read/migrate those keys. No Vue implementation exists. |
| POST-ENGINE-REUSE | migration_architecture | post | Post migration reuses/ports the existing TinyLuma-derived engine/editor via a thin Vue host/adaptation with fresh presentation. The processing engine is NEVER rebuilt feature-by-feature; Canvas 2D internals are not parity-scored. | PASS | STATIC / STATIC | Contract recorded and binding; POST2-* acceptance rows inherit it via implementation_invariant. Compliance is verified when the port lands. |
| QUEUE-IDS-FROZEN | product_behavior | queue | Workflow/version IDs frozen at enqueue | PASS | UNIT / UNIT | QueueItem stores both IDs; frozen-variants test green. |
| QUEUE-CONTROLS-FROZEN | product_behavior | queue | Controls deep-frozen at enqueue (later edits cannot leak) | PASS | UNIT / UNIT | freezeIntent deep-copy directly unit-tested. |
| QUEUE-EXTRAS-FROZEN | product_behavior | queue | Methods/references/layout/guidance frozen at enqueue | PASS | UNIT / STATIC,UNIT | QueueItem carries the full frozen intent (mode, subtool, methods, references, guidance, style, layout, output overrides); enqueue deep-freezes via captureIntent. |
| QUEUE-WORKSPACE-FROZEN | product_behavior | queue | Accepted queued execution target cannot be retargeted by a later active-workspace switch (server dispatch owns authority boundary) | UNKNOWN | RACE / STATIC | Browser side holds no workspace on queue items by design (no invented ownership; server dispatch owns the boundary). Dispatch-seam proof still needs a live backend; row stays UNKNOWN per batch policy. |
| QUEUE-MUTATION-RACE | product_behavior | queue | Later UI edits cannot mutate already-queued request (adversarial A-then-B) | PASS | RACE / UNIT,RACE | Adversarial A-then-B test: full UI rewrite before drain still submits the frozen A intent (explicit interleaving, no sleeps). |
| QUEUE-IDENTITY-CHECK | product_behavior | queue | Queued item executes with its own frozen workflow identity, version, and intent; same-workflow/different-version variants never merge; batch grouping never combines incompatible immutable identity | PASS | RACE / STATIC,RACE | Drain executes each item with its own frozen workflow/version/intent (submitQueuedItem never reads current UI); same-workflow/different-version items never merge (compatibility key); UI workflow switch before drain cannot substitute identity. |
| QUEUE-ORDER | product_behavior | queue | FIFO order preserved across drain | PASS | UNIT / STATIC,UNIT | FIFO proven: compatible triple batches in enqueue order; incompatible head items drain first with the remainder preserved. |
| QUEUE-REMOVE-CLEAR | product_behavior | queue | Remove and clear queue semantics | PASS | UNIT / STATIC,UNIT | Remove drops one item, clear drops all, drain on empty fails without submitting. |
| QUEUE-NO-REORDER | product_behavior | queue | No user-facing queue reorder on either side | PASS | STATIC / STATIC | Neither side offers reorder; absence holds on both. |
| EXP-SUBMIT-V2 | product_behavior | experiment | Experiment definition submitted through V2 endpoint | PASS | UNIT / UNIT | Endpoint contract directly tested. |
| EXP-AXIS-ORDER | product_behavior | experiment | Axis value ordering deterministic | PASS | UNIT / STATIC,UNIT | Submitted axes sorted deterministically by key; post-submit edits cannot mutate the frozen definition. |
| EXP-DEFINITION-FROZEN | product_behavior | experiment | Submitted experiment definition immutable post-submit | PASS | UNIT / STATIC,UNIT | Definition deep-frozen (sorted axes) before POST; lastSubmitted immutable under later UI edits. |
| EXP-CELL-IDS | product_behavior | experiment | Experiment + cell IDs own status lifecycle in UI state | PASS | RACE / STATIC,RACE | Active experiment id + per-cell status lifecycle in playground state; foreign experiment ids rejected; terminal cells never regress on bare polls. |
| EXP-NO-RETRY-ALL | product_behavior | experiment | Per-cell retry only; no automatic retry-all | UNKNOWN | BROWSER / STATIC | Cell-retry API exposed; absence of retry-all unproven in UI. |
| EXP-CANCEL-RESUME | product_behavior | experiment | Experiment cancel/resume with correct ownership | PASS | INTEGRATION / STATIC,INTEGRATION | Cancel/resume target the active experiment only through the history transport; single-flight guarded. |
| EXP-HISTORY-EXPOSURE | product_behavior | experiment | Experiment visible in History with results | UNKNOWN | INTEGRATION / STATIC | Normalization/actions exist; feed-to-Playground exposure unverified. |
| EXP-LATE-EVENT | product_behavior | experiment | Late events cannot claim a different experiment | PASS | RACE / STATIC,RACE | Status/event payloads for a different experiment id are rejected before reaching cell state. |
| REF2-METHODS | product_behavior | generate/references | Accepted methods: Multi-image Conditioning Slots, Reference Latent Chain, Dedicated Workflow | UNKNOWN | BROWSER / STATIC | Method taxonomy accepted; Vue method surface unverified. |
| REF2-NO-AUTO | product_behavior | generate/references | Method selection explicit; no Auto mode offered or implied | UNKNOWN | BROWSER / STATIC | No-Auto rule accepted; Vue method UI unverified. |
| REF2-MEMORY | product_behavior | generate/references | Selected method remembered per workflow | UNKNOWN | BROWSER / STATIC | Per-workflow memory accepted; Vue behavior unverified. |
| REF2-CAPACITY | product_behavior | generate/references | Reference capacity derived from workflow graph (not a fixed count) | UNKNOWN | BROWSER / STATIC | Graph-derived capacity accepted; Vue behavior unverified. |
| REF2-SOURCES | product_behavior | generate/references | Reference slots fill from Upload, Current, History sources | UNKNOWN | BROWSER / STATIC | Three sources accepted; Vue slot sourcing unverified. |
| REF2-IDENTITY | product_behavior | generate/references | Reference entries keep stable identity across slot operations | UNKNOWN | BROWSER / STATIC | Stable identity accepted; Vue behavior unverified. |
| REF2-THUMBS | product_behavior | generate/references | Entries show thumbnails; source image stays semantically distinct from references | UNKNOWN | BROWSER / STATIC | Thumbnails/distinction accepted; Vue behavior unverified. |
| GUI2-IDENTITY | product_behavior | generate/guidance | Guidance resolves against exact loaded model identity (not display label) | UNKNOWN | BROWSER / STATIC | Identity resolution accepted; Vue behavior unverified. |
| GUI2-HASH | product_behavior | generate/guidance | Hash/manifest identity outranks ambiguous names | UNKNOWN | BROWSER / STATIC | Precedence accepted; Vue behavior unverified. |
| GUI2-PROPOSE | product_behavior | generate/guidance | Recommendations proposed, never silently applied; Confirm and Change exposed | UNKNOWN | BROWSER / STATIC | Propose-not-trust accepted; Vue behavior unverified. |
| GUI2-REUSE | product_behavior | generate/guidance | Confirmed mapping reused across workflows sharing model identity; never silently replaced | UNKNOWN | BROWSER / STATIC | Reuse/no-replace accepted; Vue behavior unverified. |
| GUI2-PROVENANCE | product_behavior | generate/guidance | Provenance, controller/provider, weight filename and hash recorded | UNKNOWN | BROWSER / STATIC | Metadata accepted; Vue behavior unverified. |
| GUI2-PREPROCESSOR | product_behavior | generate/guidance | Required preprocessor explicit and preserved per mapping | UNKNOWN | BROWSER / STATIC | Preprocessor requirement accepted; Vue behavior unverified. |
| GUI2-FALLBACK | product_behavior | generate/guidance | Manual fallback available when no trusted mapping exists | UNKNOWN | BROWSER / STATIC | Fallback accepted; Vue behavior unverified. |
| GUI2-EXEC | product_behavior | generate/guidance | Backend receives guidance config; soft reference stays distinct from structural guidance | UNKNOWN | INTEGRATION / STATIC | Payload/backend distinction accepted; Vue behavior unverified. |
| ROUTE-CODEC | product_behavior | routing | Five canonical pages parse and serialize identically | PASS | UNIT / UNIT | All five route round trips directly unit-tested. |
| ROUTE-FOCUS-CODEC | product_behavior | routing | Focus values opaque, encoded, round-trip | PASS | UNIT / UNIT | Focus encoding/decoding directly tested. |
| ROUTE-FAILSOFT | product_behavior | routing | Unknown/malformed/unrelated hashes fail soft, never throw | PASS | UNIT / UNIT | Unrelated and malformed cases explicitly tested. |
| ROUTE-PUSH-REPLACE | product_behavior | routing | Page change pushes; same-page focus replaces; identical does nothing | PASS | UNIT / UNIT | History action matrix and writes directly tested. |
| ROUTE-BACK | product_behavior | routing | Back/Forward restores Studio page and focus | UNKNOWN | BROWSER / UNIT | Unit tests use fake history contract; no browser validation. |
| ROUTE-UNTOUCHED | product_behavior | routing | Unrelated host hashes never rewritten during init/navigation | PASS | UNIT / UNIT | Explicit unit coverage for untouched unrelated hashes. |
| ROUTE-OPENER-WINS | product_behavior | routing | Explicit programmatic opener beats stale hash for that invocation | UNKNOWN | BROWSER / UNIT | Pure router precedence tested; host opener integration not. |
| ROUTE-NO-REOPEN | product_behavior | routing | Close-then-hash does not auto-reopen Studio | UNKNOWN | BROWSER / STATIC | No browser test for close-then-hash sequence. |
| ROUTE-SETTINGS-FOCUS | product_behavior | routing | Settings focus selects the requested section (focus=outputs defect fixed, not removed) | FAIL | BROWSER / STATIC | Vue route adapter carries focus but no Settings section-focus behavior found. |
| ROUTE-FOCUS-SAFE | product_behavior | routing | Focus values never become executable markup | UNKNOWN | UNIT / STATIC | No explicit opaque-focus security test on Vue side. |
| RUN-FRESH-ID | product_behavior | run lifecycle | Fresh frontend run identity per Run click | PASS | RACE / STATIC,RACE | Fresh runId+requestId minted per beginRun; store executes every submit through the controller. |
| RUN-POST-AUTHORITY | product_behavior | run lifecycle | POST/result path is terminal authority (not websocket/progress) | PASS | INTEGRATION / STATIC,INTEGRATION | Direct POST result is terminal authority (completed/failed/accepted 3-way); scheduler-accepted stays non-terminal. |
| RUN-PROMPT-ID | product_behavior | run lifecycle | Prompt ID captured; foreign prompt terminal events rejected | PASS | RACE / STATIC,RACE | Prompt capture + foreign prompt terminal rejection proven by event-sequence tests. |
| RUN-EVENT-ORDER | product_behavior | run lifecycle | Progress before execution-start rejected; foreign experiment progress rejected | PASS | RACE / STATIC,RACE | Progress-before-execution-start rejected; locked-stream second start ignored; experiment events require matching id. |
| RUN-TERMINAL-LOCK | product_behavior | run lifecycle | Terminal state cannot regress; duplicate terminals deduplicated | PASS | RACE / STATIC,RACE | Terminal first-wins lock; duplicate terminals deduplicated; success/late-progress/failure ordering proven. |
| RUN-SNAPSHOT-DEDUP | product_behavior | run lifecycle | Snapshot/journal duplicate polls deduplicated | PASS | RACE / STATIC,RACE | Signature-gated snapshot polls; duplicate polls and duplicate terminal journal entries are no-ops. |
| RUN-GOLDEN-PRESENT | product_behavior | run lifecycle | Golden stage progress is presentation-only, never decides completion | PASS | INTEGRATION / STATIC,INTEGRATION | Golden progress is presentation-only state that can never complete a run; no Vue consumer decides terminality from it. |
| RUN-FAILURE-PATH | product_behavior | run lifecycle | Failure path preserves run identity and details | PASS | INTEGRATION / STATIC,INTEGRATION | Failure settles failed with the run identity and message preserved (no id clearing). |
| RUN-CANCEL | product_behavior | run lifecycle | Cancel is authoritative and race-safe (cancel-then-success cannot resurrect) | PASS | RACE / STATIC,RACE | Cancel wins the terminal lock first; late success/progress/terminal cannot resurrect; registry canceled exactly once. |
| RUN-LATE-EVENT | product_behavior | run lifecycle | Late prior-run events cannot hijack new run | PASS | RACE / STATIC,RACE | Late prior-run results/snapshots gated on caller runId; overlapping clicks rejected by the busy gate; controller tests prove stale-run rejection. |
| RUN-MIDRUN-SWITCH | product_behavior | run lifecycle | Navigation / workflow switch mid-run cannot mutate active run | PASS | RACE / STATIC,RACE | Workflow/version switch mid-run leaves controller identity and the frozen submitted payload untouched. |
| RUN-RESULT-ATTACH | product_behavior | run lifecycle | Result attaches to submitted run; recent History converges | PASS | INTEGRATION / STATIC,INTEGRATION | Authoritative completion records the generation id and converges history recentRunIds (id-only, no entity cache). |
| RUN-NO-DUP-CACHE | product_behavior | run lifecycle | Current generation stores identity only; entities resolve via History | PASS | UNIT / UNIT | Unit test asserts no second History cache. |
| RETIRED-RESULTS-CACHE | retirement | run lifecycle | Duplicate results.v1 entity cache retired, not ported | NA | STATIC / STATIC | Blueprint 4.1 explicitly retires this duplicate authority. |
| RUN-CONTROLLER-INTEGRATION | product_behavior | run lifecycle | Vue run path integrates/ports the accepted run-controller machinery (fresh run identity, event-source attach/detach, execution-start locking, stale/foreign rejection, prompt/Experiment filtering, journal dedupe, terminal freeze, authoritative result integration, Golden-presentation semantics) | PASS | INTEGRATION / STATIC,INTEGRATION | Vue run path integrates the accepted controller machinery (fresh identity, attach/detach, execution-start lock, stale/foreign rejection, prompt/experiment filtering, journal/snapshot dedupe, terminal freeze, direct-result authority, Golden-presentation semantics). |
| SEL2-TOOLS | product_behavior | edit/select | Select offers Brush, Lasso, Rectangle, Object, Detect tools | FAIL | BROWSER / STATIC | Accepted tool set; no Vue Select editor. |
| SEL2-ADD-SUB | product_behavior | edit/select | Mask ops Add, Subtract, Replace | FAIL | BROWSER / STATIC | Accepted ops; no Vue implementation. |
| SEL2-GROW | product_behavior | edit/select | Mask ops Grow, Shrink, Feather (radius-based) | FAIL | BROWSER / STATIC | Accepted ops; no Vue implementation. |
| SEL2-INVERT-HISTORY | product_behavior | edit/select | Mask ops Invert, Fill Holes, Clear; mask Undo/Redo round trip | FAIL | BROWSER / STATIC | Accepted ops/history; no Vue implementation. |
| SEL2-ERASE-EQ | product_behavior | edit/select | Erase is Brush + Subtract, not its own subsystem | UNKNOWN | BROWSER / STATIC | Equivalence unproven; no Vue editor to verify against. |
| SEL2-SOURCE-PATHS | product_behavior | edit/select | Select source via Upload, Current, History, drag-drop, paste | FAIL | BROWSER / STATIC | Five accepted paths; no Vue Select source acquisition. |
| SEL2-SOURCE-CLEAR | product_behavior | edit/select | Select source Replace/Clear; clear invalidates paint history (Undo cannot resurrect) | FAIL | BROWSER / STATIC | Accepted clear/invalidation; no Vue implementation. |
| SEL2-BASE-CLEAR | product_behavior | edit/select | Base change clears stale overlay strokes and mask state | FAIL | BROWSER / STATIC | Accepted reconciliation; no Vue implementation. |
| SEL2-MASK-SAVE | product_behavior | edit/select | Mask save carries mask into execution state | FAIL | BROWSER / STATIC | Accepted save path; no Vue implementation. |
| SEL2-COMPAT | product_behavior | edit/select | Select keeps legacy dedicated-inpaint compatibility alongside ordinary I2I | FAIL | BROWSER / STATIC | Accepted dual-path routing; no Vue implementation. |
| EXP2-SIDES | product_behavior | edit/expand | Expand exposes independent Top/Right/Bottom/Left values | FAIL | BROWSER / STATIC | Accepted side values; no Vue Expand UI. |
| EXP2-DRAG | product_behavior | edit/expand | Expand direct-manipulation preview alongside numeric controls | FAIL | BROWSER / STATIC | Accepted direct manipulation; no Vue implementation. |
| EXP2-METHODS | product_behavior | edit/expand | Expand methods Pad Canvas, Pad+Preserve, Dedicated Workflow | FAIL | BROWSER / STATIC | Accepted methods; no Vue method selector. |
| EXP2-NO-AUTO | product_behavior | edit/expand | Expand offers no Auto method | UNKNOWN | BROWSER / STATIC | No Expand UI exists to violate this yet; constraint recorded for implementation. |
| EXP2-MEMORY | product_behavior | edit/expand | Expand remembers method per workflow; stored workflow stays immutable | FAIL | BROWSER / STATIC | Accepted memory/immutability; no Vue implementation. |
| EXP2-RACE | product_behavior | edit/expand | Stale workflow responses cannot overwrite current Expand state | FAIL | RACE / STATIC | Accepted ownership boundary; no Vue implementation. |
| EXP2-I2I | product_behavior | edit/expand | Expand supports normal I2I workflows | FAIL | BROWSER / STATIC | Accepted I2I support; no Vue implementation. |
| SET-CONFIG-AUTH | product_behavior | settings | /config is durable server authority; UI reflects acknowledged state | UNKNOWN | INTEGRATION / STATIC | Read/save/reread implemented; authority behavior needs integration proof. |
| SET-GPU | product_behavior | settings | Selected GPU persists through /config | UNKNOWN | INTEGRATION / STATIC | GPU derives from config in source; behavior unproven. |
| SET-OUTPUTS | product_behavior | settings | Output settings save + project to canvas mirror one-way | UNKNOWN | INTEGRATION / STATIC | Patch/reread/projection exist; end-to-end behavior unproven. |
| SET-DATASAVER | product_behavior | settings | Data Saver semantics preserved end to end | UNKNOWN | BROWSER / STATIC | Projection exists; exact UI/save semantics unverified. |
| SET-SKIP-SEMANTICS | product_behavior | settings | skip_plan_validation exact key/value semantics (local 1/0 + server boolean) | UNKNOWN | INTEGRATION / STATIC | Shapes match in source; behavior unproven. |
| SET-MODEL-BLOCK | product_behavior | settings | Model-missing stays a blocker when skip_plan_validation is on | UNKNOWN | BROWSER / STATIC | No Vue missing-model gate found in inspected files. |
| SET-NODE-RELAX | product_behavior | settings | skip flag relaxes custom-node validation only | UNKNOWN | BROWSER / STATIC | Gate lives outside Settings implementation; unlocated. |
| SET-ROLLBACK | product_behavior | settings | Failed saves roll back to acknowledged server/browser state | UNKNOWN | INTEGRATION / STATIC | Reread/restore implemented; failure behavior unproven. |
| SET-ACK | product_behavior | settings | Successful mutation applies only after server acknowledgement (reread) | UNKNOWN | INTEGRATION / STATIC | Reread implemented; ack behavior unproven. |
| SET-CROSSTAB | product_behavior | settings | Cross-tab settings change invalidates and refetches (kind-only message) | UNKNOWN | BROWSER / STATIC | Publish visible; listener/refetch behavior not fully verified. |
| SET-BROWSER-PREFS | product_behavior | settings | Browser-only prefs persist; excluded from /config | UNKNOWN | BROWSER / STATIC | Separate persisted refs exist; reload behavior unproven. |
| SET-TRACING | product_behavior | settings | Tracing/profile selected vs effective level; failure rolls back | UNKNOWN | BROWSER / STATIC | Selected/effective split + restore implemented; behavior unproven. |
| GOLDEN-CATALOG | product_behavior | settings | Golden catalog + server selection with fallback | UNKNOWN | BROWSER / STATIC | Catalog/selection implemented; behavior unproven. |
| GOLDEN-SEPARATION | product_behavior | settings | Normal GPU, Golden profile, deploy config, active A/B kept distinct | UNKNOWN | INTEGRATION / STATIC | Distinct paths exist; no negative-write assertion; run-time consumption unevidenced. |
| GOLDEN-AB-NEXT-RUN | product_behavior | settings | Active A/B order applies to next run without redeploy | UNKNOWN | REAL_BACKEND / STATIC | API update exists; run-time consumption not evidenced. |
| GOLDEN-DEPLOY | product_behavior | settings | Golden deploy operation + status polling owned by Settings/infrastructure | UNKNOWN | REAL_BACKEND / STATIC | Polling + operation status exist; deploy behavior unproven. |
| SK2-TOOLS | product_behavior | generate/sketch | Sketch tools: brush, pencil, eraser, line, rectangle, circle, fill, eyedropper | FAIL | BROWSER / STATIC | Engine surface statically accepted; no Vue implementation. |
| SK2-SETTINGS | product_behavior | generate/sketch | Sketch settings: size, opacity, hardness, color, background, fill tolerance (pressure only if accepted) | FAIL | BROWSER / STATIC | Settings contract in engine state; no Vue implementation. |
| SK2-COMPOSITE | product_behavior | generate/sketch | Layer-composited rendering with bounded undo/redo history (cap 30) | FAIL | BROWSER / STATIC | Composite/history statically accepted; no Vue equivalent. |
| SK2-ZOOM | product_behavior | generate/sketch | Zoom in/out, Fit, wheel zoom, space/middle-mouse pan | FAIL | BROWSER / STATIC | Zoom/pan documented in header; no Vue implementation. |
| SK2-LAYERS | product_behavior | generate/sketch | Layers: add, delete, rename, visibility, opacity, reorder, duplicate, merge-down, flatten | FAIL | BROWSER / STATIC | Layer ops statically accepted; no Vue layer store. |
| SK2-BASE-LOCK | product_behavior | generate/sketch | Base layer index-zero, locked, protected from deletion/movement | FAIL | BROWSER / STATIC | Base protection statically accepted; no Vue implementation. |
| SK2-COMMIT | product_behavior | generate/sketch | Flattened sketch uploads as uniquely named source image with source commit hook | FAIL | INTEGRATION / STATIC | Upload/commit statically accepted; no Vue integration. |
| SK2-ROUTING | product_behavior | generate/sketch | Sketch routes to sketch editor; legacy inpaint/Select keep paint editor | FAIL | BROWSER / STATIC | Routing pins exist for legacy; Vue routing parity unproven and no editor exists. |
| SK2-SURFACE | product_behavior | generate/sketch | Sketch surface exposes the required canvas interaction, undo/redo, save/commit and mask-preview behavior through the Vue UI | FAIL | BROWSER / STATIC | Legacy selectors, test IDs, DOM shape, and exact wording are explicitly NOT migration requirements (fresh DOM/CSS/components allowed). Only product-meaningful behavior must survive. No Vue sketch surface exists. |
| SKETCH-ENGINE-REUSE | migration_architecture | generate/sketch | Sketch migration reuses/ports the existing ComfySketch-derived engine (engine, layers, composite, history, zoom/pan, flatten); only host/state seams are adapted, presentation is fresh. The drawing/layer engine is NEVER rewritten from scratch while it exists. | PASS | STATIC / STATIC | Contract recorded and binding; SK2-* acceptance rows inherit it via implementation_invariant. Compliance is verified when the port lands. |
| SK-OPEN | product_behavior | generate/sketch | Sketch editor opens with base image selection | UNKNOWN | BROWSER / STATIC | Base selection shell exists; no drawing surface, behavior unproven. |
| SK-STROKES | product_behavior | generate/sketch | Stroke creation, eraser, clear, undo/redo | FAIL | BROWSER / STATIC | Only a local stroke-count array; no editor operations. |
| SK-FLATTEN-UPLOAD | product_behavior | generate/sketch | Sketch flattens and uploads with sketch identity as source | FAIL | BROWSER / STATIC | No flatten path (no toBlob/toDataURL/uploadSketch); strokes local-only. |
| SK-BASE-SWITCH | product_behavior | generate/sketch | Base switch clears strokes/layers, preserves tool settings | UNKNOWN | BROWSER / STATIC | Explicit clearing wired in source; transition behavior unproven. |
| SK-SETTINGS-GUARD | product_behavior | generate/sketch | Sketch tool settings preserved; stale completion guarded | UNKNOWN | RACE / STATIC | No sketch settings or sketch-specific stale guard in Vue. |
| GUI-LOOKUP | product_behavior | generate/guidance | Guidance mapping lookup for workflow/version | FAIL | BROWSER / STATIC | Workflows store fetches mappings; Playground has no guidance lookup/use. |
| GUI-KEY | product_behavior | generate/guidance | Guidance keyed by exact (model_sha256, mode) | FAIL | INTEGRATION / STATIC | No model hash/mode handling in Vue. |
| GUI-MODES | product_behavior | generate/guidance | Guidance modes, unsupported states, and selection UI | FAIL | BROWSER / STATIC | No guidance UI, mode state, or unsupported-state rendering. |
| GUI-PAYLOAD | product_behavior | generate/guidance | Guidance mutates request and persists per version | FAIL | INTEGRATION / STATIC | applySubmissionExtras accepts guidance generically; no producer or persisted mapping state. |
| GUI-NO-BRANCH | product_behavior | generate/guidance | No model/provider-family frontend branching | PASS | STATIC / STATIC | No provider mentions in Vue source; invariant holds vacuously (no Guidance impl to branch in). |
| STY-CONTEXT | product_behavior | generate/style | Style browser visible only in Generate Text context, absent in Edit mode | FAIL | BROWSER / STATIC | Accepted browser test proves legacy context gating; no style-browser implementation in Vue. |
| STY-SHELL | product_behavior | generate/style | Style browser renders collapsed accordion with search, categories, grid, twelve catalog cards | FAIL | BROWSER / STATIC | Legacy shell and card count browser-verified; no Vue implementation. |
| STY-SEARCH | product_behavior | generate/style | Style search filters cards; clearing restores full catalog | FAIL | BROWSER / STATIC | Search behavior proven only on legacy surface; absent in Vue. |
| STY-CATEGORY | product_behavior | generate/style | Category filter shows member cards; All restores catalog | FAIL | BROWSER / STATIC | Category filtering proven by legacy test; no Vue equivalent. |
| STY-SELECT | product_behavior | generate/style | Style selection marks card pressed, exposes identity, composes prompt fragment | FAIL | BROWSER / STATIC | Selection/identity/composed-prompt accepted in test; missing in Vue. |
| STY-NONE | product_behavior | generate/style | None clears identity, effective prompt, pressed state, persisted selection | FAIL | BROWSER / STATIC | Clear behavior browser-proven on legacy UI; absent in Vue. |
| STY-PERSIST | product_behavior | generate/style | Style selection and favorites persist in localStorage style store | FAIL | BROWSER / STATIC | Persistence proven by legacy assertions; no Vue style store. |
| STY-FAVORITE | product_behavior | generate/style | Favorite toggle updates visual state and persisted favorites membership | FAIL | BROWSER / STATIC | Favorite toggling accepted by test; absent in Vue. |
| STY-WORKFLOW-KEPT | product_behavior | generate/style | Selected workflow unchanged while style selection updates prompt | UNKNOWN | BROWSER / STATIC | Test proves composition, not workflow identity; Vue has no style feature. |
| LAY2-SHELL | product_behavior | generate/layout | Layout editor shell mounts with canvas, dimensions, palette, region list, inspector, JSON preview | FAIL | BROWSER / STATIC | Shell covered by accepted test; no Vue layout editor. |
| LAY2-CREATE | product_behavior | generate/layout | Canvas drag-create makes regions, including forced creation over existing region | FAIL | BROWSER / STATIC | Drag-create proven only by legacy test; absent in Vue. |
| LAY2-TRANSFORM | product_behavior | generate/layout | Region select, move, resize via canvas handles | UNKNOWN | BROWSER / STATIC | Suite is authority but excerpt does not assert outcomes; Vue has no editor. |
| LAY2-TYPE-TEXT | product_behavior | generate/layout | Region switches Object/Text type; text regions keep exact entered text | FAIL | BROWSER / STATIC | Type/text serialization browser-proven; absent in Vue. |
| LAY2-JSON-PREVIEW | product_behavior | generate/layout | Descriptions and palette edits appear in structured layout JSON preview | FAIL | BROWSER / STATIC | Serialization accepted by test; no Vue layout preview. |
| LAY2-BBOX | product_behavior | generate/layout | Bboxes serialize as Ideogram y-min,x-min,y-max,x-max on a 0-1000 grid | FAIL | BROWSER / STATIC | Exact bbox assertion accepted; no Vue serializer. |
| LAY2-LIFECYCLE | product_behavior | generate/layout | Regions duplicate, reorder, delete, clear with serialized order preserved | FAIL | BROWSER / STATIC | Full lifecycle browser-proven on legacy editor; absent in Vue. |
| LAY2-OVERLAP | product_behavior | generate/layout | Alt-click cycles selection among overlapping regions | UNKNOWN | BROWSER / STATIC | Documented as covered but exact assertion unavailable; Vue has no editor. |
| LAY2-DIMS | product_behavior | generate/layout | Canvas dimensions and global/background descriptions update draft and JSON caption | FAIL | BROWSER / STATIC | Dimension/global behavior browser-proven; missing in Vue. |
| LAY2-SEND | product_behavior | generate/layout | Send to Prompt serializes layout and returns shell to Text with workflow unchanged | FAIL | BROWSER / STATIC | Round trip proven by test; absent in Vue. |
| LAY2-DRAFT | product_behavior | generate/layout | Layout draft survives supported reload/remount path | FAIL | BROWSER / STATIC | Draft persistence accepted; no Vue layout draft implementation. |
| STYLE-NO-OLD-CSS | product_behavior | styling | No legacy Studio CSS imported by Vue | PASS | STATIC / STATIC | Static import search supports isolation; old CSS is contractually retired. |
| STYLE-TAILWIND | product_behavior | styling | Tailwind utilities prefixed; no global Preflight | PASS | STATIC / STATIC | Source directly establishes prefix + theme/utilities only. |
| STYLE-PORTAL | product_behavior | styling | Portalled controls render into Studio-owned portal target | UNKNOWN | BROWSER / STATIC | Target + config exist; runtime containment unverified. |
| STYLE-ZINDEX | product_behavior | styling | Modal / in-app / portal z-index ordered; focus correct; responsive | UNKNOWN | BROWSER / STATIC | Numeric ordering static; overlap/focus/responsive needs browser matrix. |
| STYLE-HOST-SAFE | product_behavior | styling | Opening Vue Studio never alters external ComfyUI layout/styles | UNKNOWN | BROWSER / STATIC | No live-host style-leak evidence gathered in this audit. |
| STYLE-REDESIGN | migration_architecture | styling | Overall visual redesign vs legacy (not pixel parity) | INTENTIONAL_CHANGE | STATIC / STATIC | Blueprint explicitly replaces all old visual styling. |
| RETIRED-OLD-HISTORY | retirement | retired | Legacy History UI (studio-history.js) not carried forward | NA | STATIC / STATIC | Blueprint 12 explicitly retires legacy History UI; Vue calls History V2 directly. |
| RETIRED-COMPARE-PROFILES | retirement | retired | Comparison Profiles/Runner not resurrected | NA | STATIC / STATIC | Blueprint 12/17 retires Comparison Profiles/Runner. |
| RETIRED-V1-EXEC | retirement | retired | V1/shadow execution UI not carried forward | NA | STATIC / STATIC | Blueprint 12 retires V1/shadow execution UI. |
| RETIRED-PROVIDER-SEL | retirement | retired | Old provider-selector architecture not carried forward | NA | STATIC / STATIC | Blueprint 12 retires provider selector; scope is Modal workspace management. |
| RETIRED-SIX-TAB | retirement | retired | Old six/legacy-tab navigation not carried forward | NA | STATIC / STATIC | Blueprint 12 retires six/legacy-tab navigation; five pages only. |
| RETIRED-RETRY-ALL | retirement | retired | Automatic retry-all experiment behavior stays forbidden | NA | STATIC / STATIC | Blueprint 12/15 forbids automatic retry-all. |
| ARCH-VUE-ROUTER | migration_architecture | architecture | vue-router mechanism under frozen hash contract has explicit owner approval | PASS | STATIC / STATIC | Revised blueprint approves Vue Router with the frozen hash contract; source proves createRouter over a custom #comfymodal history. Behavioral URL compatibility stays on route rows. |
| ARCH-API-LAYER | migration_architecture | architecture | Raw page-level fetches consolidated into shared API layer | INTENTIONAL_CHANGE | STATIC / STATIC | Blueprint 12 explicitly moves raw fetches to the shared API layer. |
| WZ-OPEN-CLOSE | product_behavior | wizard | Wizard opens and closes/cancels with cleanup | UNKNOWN | BROWSER / STATIC | Store owns lifecycle; rendered modal behavior unproven. |
| WZ-SUG-UNET | product_behavior | wizard | Auto-suggest discovers UNET candidates in graph order | FAIL | BROWSER / STATIC | Legacy deterministic discovery vs Vue explicit Suggest button; autofill semantics differ. |
| WZ-SUG-CLIP | product_behavior | wizard | Auto-suggest discovers CLIP candidates in graph order | FAIL | BROWSER / STATIC | Same suggest-semantics gap as UNET. |
| WZ-SUG-VAE | product_behavior | wizard | Auto-suggest discovers VAE candidates in graph order | FAIL | BROWSER / STATIC | Same suggest-semantics gap as UNET. |
| WZ-PROPOSE | product_behavior | wizard | Auto-suggest discovers text candidates; suggestions stay proposals until explicit confirm | UNKNOWN | BROWSER / STATIC | Proposals-only contract documented; explicit-confirm click path unverified. |
| WZ-ROLES | product_behavior | wizard | Required/optional role catalogs enforced at save | UNKNOWN | BROWSER / STATIC | Catalogs exist; save-gate enforcement unproven. |
| WZ-CENTER | product_behavior | wizard | View centers graph on bound node | FAIL | BROWSER / STATIC | No Vue center-graph implementation wired. |
| WZ-HIGHLIGHT | product_behavior | wizard | View highlights node ~3s, cleared on re-render/close | FAIL | BROWSER / STATIC | No Vue highlight implementation. |
| WZ-GRAPH-MODE | product_behavior | wizard | Graph interactive while wizard open; inert + aria-modal released, restored after | FAIL | BROWSER / STATIC | Positive absence: host seam (setGraphInteractionEnabled/viewStudioGraphNode) exists but has no Vue wizard caller; no capture/cancel wiring found. Graph cannot be driven from the Vue wizard. |
| WZ-FOCUS | product_behavior | wizard | Wizard focus capture + aria-modal semantics | UNKNOWN | BROWSER / STATIC | No confirmed wizard aria-modal/focus-trap evidence. |
| WZ-CAPTURE | product_behavior | wizard | Actual node/widget capture binds exact graph target | UNKNOWN | REAL_BACKEND / STATIC | APIs/store exist; graph capture and visible save flow incomplete. |
| WZ-DRAFT | product_behavior | wizard | Mapping persists; draft survives reload scoped to version; reopen resumes step | UNKNOWN | BROWSER / STATIC | Session draft version-scoped; reload/reopen behavior unproven. |
| WZ-PORTAL | product_behavior | wizard | Wizard UI renders inside Studio portal target, not document.body | FAIL | STATIC / STATIC | Wizard teleports to body, violating portal containment contract. |
| PRESET-CRUD | product_behavior | presets | Preset create/apply/update/delete end to end | UNKNOWN | BROWSER / STATIC | API/store actions exist; full Vue preset UI CRUD unconfirmed. |
| PRESET-IDENTITY | product_behavior | presets | Active preset identity + dirty state tracked | UNKNOWN | BROWSER / STATIC | ID + dirty explicit in source; behavior unproven. |
| PRESET-VERSION | product_behavior | presets | Preset owned by workflow version; cross-version behavior correct | UNKNOWN | BROWSER / STATIC | Context key includes version; cross-version behavior unproven. |
| PRESET-APPLY | product_behavior | presets | Applying preset restores controls + output overrides | UNKNOWN | BROWSER / STATIC | Apply path exists; restore behavior unproven. |
| PRESET-NO-SETTINGS | product_behavior | presets | Preset output overrides never mutate global Settings | UNKNOWN | INTEGRATION / STATIC | Override is run intent in source; isolation unproven by test. |
| PRESET-IMAGEFREE | product_behavior | presets | Image pixels excluded per field (source/mask/references/sketch/outputs/compare/URLs) | PASS | UNIT / UNIT | Image-like keys stripped; exclusion directly unit-tested. |
| PRESET-CLEAR-STALE | product_behavior | presets | Preset apply clears stale output + source/reference ownership | PASS | UNIT / UNIT | Apply-clears-ownership directly unit-tested. |
| PRESET-CLEAR-EDITORS | product_behavior | presets | Stale editor/direct-manip state cleared on preset apply | UNKNOWN | BROWSER / STATIC | Source ownership clears; whole editor clearing unproven. |
| PRESET-LOOKS-SEPARATE | product_behavior | presets | Post Looks remain distinct from workflow presets | UNKNOWN | BROWSER / STATIC | Preset UI present; separate Looks behavior unevidenced (no Looks impl). |

## Product failures (ranked)

- broken core behavior: SEL-BRUSH, SEL-ERASE, SEL-LASSO, SEL-RECT, SEL-MASK-OPS, SEL-UNDO, SEL-SAM3, SEL-DETECT, SEL-CROPSTITCH, SEL-COND-CROP, SEL-DEDICATED, POST-ADJUST, POST-COLOR, POST-DETAIL, POST-EFFECTS, POST-CROP, POST-HEAL, LAY-OPEN, LAY-GEOMETRY, LAY-TEMPLATES, LAY-PAYLOAD, PG-PICKER-FILTERS, PG-MODEL-UNET, PG-MODEL-CLIP, PG-MODEL-VAE, PG-MODEL-OPTIONS, PG-ADV-DISCLOSURE, PG-ADV-PERSIST, PG-CONTROL-ORDER, PG-ORDER-PERSIST, PG-METHOD-SELECT, SEL2-TOOLS, SEL2-ADD-SUB, SEL2-GROW, SEL2-INVERT-HISTORY, SEL2-SOURCE-PATHS, SEL2-SOURCE-CLEAR, SEL2-BASE-CLEAR, SEL2-MASK-SAVE, SEL2-COMPAT, SK2-TOOLS, SK2-SETTINGS, SK2-COMPOSITE, SK2-ZOOM, SK2-LAYERS, SK2-BASE-LOCK, SK2-COMMIT, SK2-ROUTING, SK2-SURFACE, SK-STROKES, SK-FLATTEN-UPLOAD, GUI-LOOKUP, GUI-KEY, GUI-MODES, GUI-PAYLOAD, WZ-SUG-UNET, WZ-SUG-CLIP, WZ-SUG-VAE
- safety/race failure: EXP2-RACE
- missing feature: SRC-FROM-HISTORY, SRC-DRAGDROP, SRC-PASTE, EXPAND-GEOMETRY, EXPAND-PAD, EXPAND-PRESERVE, EXPAND-PAYLOAD, REF-REPLACE, REF-WEIGHTS, REF-DRAFT-PERSIST, HOST-AUTOREOPEN, DEPS-STATES, POST2-LIGHT, POST2-COLOR, POST2-CURVES, POST2-MIXER, POST2-DETAIL-FX, POST2-LUT, POST2-CROP, POST2-HEAL-WB, POST2-WORKFLOW, POST2-RES, POST2-PERSIST, ROUTE-SETTINGS-FOCUS, EXP2-SIDES, EXP2-DRAG, EXP2-METHODS, EXP2-MEMORY, EXP2-I2I, STY-CONTEXT, STY-SHELL, STY-SEARCH, STY-CATEGORY, STY-SELECT, STY-NONE, STY-PERSIST, STY-FAVORITE, LAY2-SHELL, LAY2-CREATE, LAY2-TYPE-TEXT, LAY2-JSON-PREVIEW, LAY2-BBOX, LAY2-DIMS, LAY2-SEND, LAY2-DRAFT, WZ-CENTER, WZ-HIGHLIGHT, WZ-GRAPH-MODE
- missing QoL: POST2-ORDER, LAY2-LIFECYCLE
- presentation difference: CANVAS-SELECT, CANVAS-EXPAND, CANVAS-SKETCH, WZ-PORTAL

## Unknowns (evidence required)

- LATEST-READS needs RACE (has UNIT): Primitive + wiring unit-tested; actual late-completion ordering unproven.
- LATEST-HISTORY needs RACE (has STATIC): Primitive wired; no History-specific race test.
- LATEST-REFRESH needs RACE (has STATIC): Wiring exists; no store race tests.
- LATEST-MUTATIONS needs INTEGRATION (has STATIC): Primitive documents policy; mutation call sites not exhaustively verified.
- LATEST-SHARED needs STATIC (has STATIC): Per-site appropriateness unverified: sourceToken may be legitimate specialization, latest.ts gaps may exist. Needs review, not a rewrite mandate.
- OPS-IDS needs BROWSER (has STATIC): Unique generation exists; lifecycle/remount behavior unproven.
- WS-MIDOP needs RACE,REAL_BACKEND (has STATIC): Run payloads carry no workspace by design (browser does not invent dispatch ownership; server dispatch owns the boundary). Dispatch-seam proof still needs a live backend; row stays UNKNOWN per batch policy.
- CANVAS-PROMPT needs REAL_BACKEND (has STATIC): Deferred, no runtime proof.
- CANVAS-PASSTHROUGH needs REAL_BACKEND (has STATIC): Commented contract only; no enable-state implementation.
- CANVAS-MARKERS needs REAL_BACKEND (has STATIC): Vue projection does not implement or test markers.
- CANVAS-PROJECTION needs INTEGRATION (has STATIC): Write path implemented; one-way effect on canvas unproven.
- CANVAS-FALLBACK needs INTEGRATION (has STATIC): Fallback keys written; fallback behavior unproven.
- CANVAS-CURRENT-SETTINGS needs REAL_BACKEND (has STATIC): Snapshot/global built; request integration is legacy-only.
- CANVAS-POST-CLOSE needs BROWSER (has STATIC): No Vue close/cleanup evidence in compatibility/host code.
- PERSIST-RELOAD needs BROWSER (has STATIC): Persisted values exist; reload-restore behavior unproven.
- XTAB-KINDS needs BROWSER (has STATIC): Equivalent vocabulary wired; no cross-tab test found.
- XTAB-NO-ENTITIES needs BROWSER (has STATIC): Payload shape matches; receiver/refetch behavior untested.
- XTAB-REFETCH needs BROWSER (has STATIC): Refetch-on-invalidate behavior unproven.
- XTAB-CLEANUP needs BROWSER (has STATIC): Removal implemented; cleanup test absent.
- CMP-SELECT needs BROWSER (has STATIC): Slots store-backed; selection behavior unproven.
- CMP-SWAP needs BROWSER (has STATIC): Switch control visible in source; behavior unproven.
- CMP-VIEWER needs BROWSER (has STATIC): Wells rendered in source; viewer interaction unproven.
- CMP-EXIT needs BROWSER (has STATIC): Clear path exists; behavior unproven.
- CMP-DELETED needs BROWSER (has STATIC): Explicit state rendered in source; behavior unproven.
- CMP-TRANSIENT needs BROWSER (has STATIC): No persistence mechanism found, but reload behavior unproven.
- CMP-HANDOFF needs BROWSER (has STATIC): Components exist separately; complete handoff undemonstrated.
- WF-LIBRARY needs BROWSER (has STATIC): Wired in source; library behavior unproven.
- WF-FILTERS needs BROWSER (has STATIC): Filters + inventories present; behavior unproven.
- WF-CRUD needs BROWSER (has STATIC): Paths wired; behavior + persistence unproven.
- WF-VERSIONS needs BROWSER (has STATIC): Version paths exist; behavior unproven.
- WF-MAPPING needs BROWSER (has STATIC): Store/API distinction found; confirmation UI incomplete.
- WF-DEPS needs BROWSER (has STATIC): Data loaded; visible detail behavior unproven.
- WF-COMPAT needs BROWSER (has STATIC): Reports loaded into state; visible UI + runtime unproven.
- WF-MANIFEST needs BROWSER (has STATIC): API functions exist; visible workflow unconfirmed.
- WF-SHARED-SELECT needs BROWSER (has STATIC): Shared selection visible; cross-page behavior unproven.
- WF-STALE-READ needs RACE (has STATIC): Latest-task guards explicit; race behavior unproven.
- WF-FOLDERS needs BROWSER (has STATIC): Inventories exist; behavior unproven.
- SRC-UPLOAD needs BROWSER (has STATIC): Upload path exists; runtime binding unproven.
- SRC-LATEST-WINS needs RACE (has UNIT): Token+owner guard unit-tested; true concurrency race unproven.
- SRC-OWNER-SWITCH needs RACE (has UNIT): Context-switch discard unit-tested; mid-upload switch race unproven.
- SRC-FAIL-OWNER needs BROWSER (has STATIC): No runtime failure-path evidence.
- SRC-CLEAR-MASK needs BROWSER (has STATIC): Vue clear exists; legacy parity of dependent clearing unverified.
- SRC-SHARED-IDENTITY needs BROWSER (has STATIC): Ownership refs exist; no cross-subtool identity test.
- SEL-OWNERSHIP needs REAL_BACKEND (has STATIC): Generic role detection is not shared-editor ownership proof; exact binding needs backend.
- SEL-MASK-GATE needs BROWSER (has STATIC): No Select-specific mask gate; blocked-run behavior unproven.
- SEL-PAYLOAD needs INTEGRATION (has STATIC): Generic payload freeze is not Select mapping proof; needs exact capture.
- SEL-STALE-MASK needs BROWSER (has STATIC): Clear path clears mask; replacement-path invalidation unproven.
- EXPAND-PREVIEW needs BROWSER (has STATIC): Central stage has image/status only; no Expand preview.
- POST-LOOKS needs BROWSER (has STATIC): Design contract exists; Vue Looks implementation absent.
- POST-UPSCALE-PARKED needs BROWSER (has STATIC): Placeholder explicitly represented; disabled-state needs browser check.
- CANVAS-BASE needs BROWSER (has STATIC): Source shows image/status branches; live DOM unproven.
- CANVAS-NO-CONTROLS needs BROWSER (has STATIC): Placement structurally suggested (controls at :607); browser DOM unproven.
- CANVAS-SWITCH needs BROWSER (has STATIC): Clear semantics exist; overlay lifecycle absent so transition unproven.
- TXT-PROMPT needs BROWSER (has STATIC): Prompt roles render; entry/display behavior unproven.
- TXT-PAYLOAD needs INTEGRATION (has STATIC): Payload mapping exists; accepted-by-backend shape unproven.
- TXT-RESULT needs BROWSER (has STATIC): Identity-only projection exists; display + convergence unproven.
- REF-ADD-REMOVE needs BROWSER (has STATIC): Cards exist; interaction behavior unproven.
- REF-ORDER needs BROWSER (has STATIC): Array order retained in source; ordering behavior unproven.
- REF-UPLOAD-RACE needs RACE (has STATIC): Reference upload path has no ownership/stale guard.
- REF-SOURCE-SEPARATION needs INTEGRATION (has STATIC): Separation exists in source; serialization behavior unproven.
- REF-BINDING needs REAL_BACKEND (has STATIC): Vue sends filenames/items; legacy candidate/method/binding structure absent.
- HIST-FEED needs BROWSER (has STATIC): Feed call exists; loaded-and-rendered behavior unproven.
- HIST-PAGINATION needs BROWSER (has STATIC): API shape present; visible load-more unconfirmed.
- HIST-QUERY needs BROWSER (has STATIC): Controls wired; query-behavior needs browser proof.
- HIST-VIEWSTATE needs BROWSER (has STATIC): Viewstate persisted; reload-restore unproven.
- HIST-FOCUS needs BROWSER (has STATIC): Store + route focus implemented; focus behavior unproven.
- HIST-STALE-FOCUS needs RACE (has STATIC): Latest-task guards present; race behavior unproven.
- HIST-FAVORITE needs BROWSER (has STATIC): Toggle path exists; user-visible toggle + persistence unproven.
- HIST-NOTE needs BROWSER (has STATIC): Note endpoints exist; save behavior unproven.
- HIST-DELETE needs BROWSER (has STATIC): Confirm + removal wired; behavior unproven.
- HIST-BULK-DELETE needs BROWSER (has STATIC): Selection + bulk endpoint wired; behavior unproven.
- HIST-ORIGINAL needs BROWSER (has STATIC): Separate actions exist; distinct user-visible behavior unproven.
- HIST-RESUME needs BROWSER (has STATIC): Resume action exists; behavior unproven.
- HIST-CELL-RETRY needs BROWSER (has STATIC): Cell-ID path explicit; retry behavior unproven.
- HIST-EXP-CANCEL-RESUME needs BROWSER (has STATIC): Actions represented; behavior unproven.
- HIST-DOWNLOAD-EXPORT needs BROWSER (has STATIC): API/store paths found; click behavior + configured-export control unproven.
- HIST-IMMUTABLE-REPLAY needs INTEGRATION (has STATIC): Params normalized as record data; immutability unproven by test.
- HIST-GEN-DETAIL needs BROWSER (has STATIC): Detail path exists; rendered behavior unproven.
- HIST-EXP-DETAIL needs BROWSER (has STATIC): Model supports cells; full rendered detail unconfirmed.
- HIST-COLUMNS needs BROWSER (has STATIC): Preference read exists; behavior + persistence unproven.
- HIST-PICKER needs BROWSER (has STATIC): Dialog exists; filtering/pagination/focus/handoff parity not evidenced.
- HIST2-USE-CURRENT needs BROWSER (has STATIC): Handoff accepted; Vue behavior unverified.
- HIST2-EDIT-REF needs BROWSER (has STATIC): Handoffs accepted; Vue behavior unverified.
- HIST2-POST-HANDOFF needs BROWSER (has STATIC): Handoff accepted; Vue behavior unverified.
- HIST2-DELETED needs BROWSER (has STATIC): Deleted-state accepted; Vue behavior unverified.
- CMP2-INTERACT needs BROWSER (has STATIC): Interactions accepted; Vue behavior unverified.
- CMP2-FIT needs BROWSER (has STATIC): View modes accepted; Vue behavior unverified.
- CMP2-TRANSIENT-IO needs BROWSER (has STATIC): Transient lifecycle accepted; Vue behavior unverified.
- P12-IDENTITY needs BROWSER (has STATIC): Identity accepted; Vue behavior unverified.
- P12-REOPEN needs BROWSER (has STATIC): Reopen accepted; Vue behavior unverified.
- P12-LABELS needs BROWSER (has STATIC): Label/identity split accepted; Vue behavior unverified.
- P12-PROMPT needs BROWSER (has STATIC): Composition accepted; Vue behavior unverified.
- P12-METHOD needs BROWSER (has STATIC): Method identity accepted; Vue behavior unverified.
- P12-EMPTY-IMAGES needs BROWSER (has STATIC): Empty-reopen accepted; Vue behavior unverified.
- P12-PROVENANCE needs BROWSER (has STATIC): Separation accepted; Vue behavior unverified.
- P13-CHAIN needs BROWSER (has STATIC): Integration flow accepted; Vue end-to-end unverified.
- P13-STALE needs BROWSER (has STATIC): Cleanup accepted; Vue end-to-end unverified.
- P13-FAMILIES needs BROWSER (has STATIC): Family separation accepted; Vue cross-family unverified.
- P13-HONEST needs BROWSER (has STATIC): Honesty contract accepted; Vue runtime paths unverified.
- P13-IDENTITY needs BROWSER (has STATIC): Identity accepted; Vue queue/reload unverified.
- HOST-LAUNCHER needs BROWSER (has STATIC): Both openers exist in source; no browser proof of launcher behavior.
- HOST-FALLBACK needs BROWSER (has STATIC): Vue host assumes host caller; no independent fallback implemented or tested.
- HOST-WINDOW-API needs BROWSER (has STATIC): Entrypoint names not compared at runtime.
- HOST-SINGLE-MOUNT needs BROWSER (has STATIC): Mount-count guard exists; not browser-verified.
- HOST-FOCUS-CAPTURE needs BROWSER (has STATIC): Source shows capture, not runtime focus outcome.
- HOST-FOCUS-RESTORE needs BROWSER (has STATIC): No browser focus assertion found.
- HOST-SCROLL-LOCK needs BROWSER (has STATIC): CSS/source only; no repeated open/close browser test.
- HOST-INERT needs BROWSER (has STATIC): Restoration of pre-existing attributes needs runtime proof.
- HOST-ARIA-MODAL needs BROWSER (has STATIC): No DOM-state browser evidence.
- HOST-ESCAPE needs BROWSER (has STATIC): No browser test for nested Escape ordering.
- HOST-BACKDROP needs BROWSER (has STATIC): No browser interaction evidence.
- HOST-CLOSE-SUPPRESS needs BROWSER (has STATIC): Vue documents no auto-reopen (preview); no refresh test.
- HOST-EXPLICIT-OPENER needs BROWSER (has UNIT): Router precedence unit-tested; host opener integration unverified.
- HOST-NO-DUP-ESC needs RACE (has STATIC): Listener guards exist both sides; no race evidence.
- HOST-NO-DUP-WIZ needs RACE (has STATIC): Vue guard exists; no race evidence.
- HOST-WIZARD-MODE needs BROWSER (has STATIC): Seam exists; no browser proof with real wizard open.
- HOST-CLOSE-BUTTON needs BROWSER (has STATIC): No visual/focus browser verification.
- HOST-LEGACY-RESTORE needs BROWSER (has STATIC): Source-supported but unverified in mixed legacy/Vue runtime.
- HOST-WIZARD-REOPEN needs BROWSER (has STATIC): Vue session draft + resume exist in source; reload-forced reopen behavior unproven.
- INFRA-WORKSPACES needs BROWSER (has STATIC): Active ID + rows normalized; behavior unproven.
- INFRA-SWITCH needs BROWSER (has STATIC): Activation + rollback exist; behavior unproven.
- INFRA-FROZEN-TARGET needs RACE (has STATIC): Frozen ID recorded for infra ops; race behavior unproven.
- INFRA-DEPLOY needs REAL_BACKEND (has STATIC): Actions + states wired; deploy behavior needs backend proof.
- INFRA-REFRESH needs RACE (has STATIC): Latest-wins protects reads; explicit refresh semantics unchecked.
- INFRA-MODELS needs BROWSER (has STATIC): Lists display; presence-state mapping not evidenced.
- INFRA-INSTALL needs BROWSER (has STATIC): Install exists; full lifecycle in view unverified.
- INFRA-NODES needs REAL_BACKEND (has STATIC): Refresh/sync/rebuild APIs exist; behavior unproven.
- INFRA-CREDS needs BROWSER (has STATIC): Status/save APIs exist; failure/visibility incomplete.
- INFRA-OPVIS needs BROWSER (has STATIC): IDs/progress/failure surfaced; single-visibility + dedup unproven.
- DEPS-MODEL-GATE needs BROWSER (has STATIC): Flagging surface exists; non-submittable gate needs runtime proof.
- DEPS-NODE-GATE needs BROWSER (has STATIC): No matching Vue gate implementation located.
- DEPS-STALE-REFRESH needs RACE (has STATIC): Latest-task wired; race behavior unproven.
- PG-WORKFLOW-SELECT needs BROWSER (has STATIC): Selection + context load exist; no browser proof.
- PG-VERSION-PICK needs BROWSER (has STATIC): List + latest-resolution exist; behavior unproven in browser.
- PG-SELECTION-PERSIST needs BROWSER (has STATIC): Persisted identity exists; reload-restore unproven.
- PG-MODEL-AUTOFILL needs REAL_BACKEND (has STATIC): Frontend schema-default path unproven for captured model values; backend run-context evidence required.
- PG-MODEL-ROLES needs INTEGRATION (has STATIC): Roles exist in Vue API catalog; that they drive controls with correct values is unproven.
- PG-SEED-RANDOMIZE needs BROWSER (has STATIC): Randomize button exists; bounds/rules differ (Vue random range) and fresh-draw behavior needs browser proof.
- PG-SELECT needs BROWSER (has STATIC): Enum selects render; coercion/selection behavior unproven.
- PG-BOOLEAN needs BROWSER (has STATIC): Toggle renders; payload emission unproven.
- PG-TEXT needs BROWSER (has STATIC): Textareas render; entry-to-payload behavior unproven in browser.
- PG-DIRTY needs BROWSER (has STATIC): Preset dirty present; broader legacy dirty/run-state reset semantics not evidenced.
- PG-RUN-GATE needs BROWSER (has STATIC): Gate conditions exist; matrix behavior (incl. missing-model block) unproven.
- PG-PAYLOAD needs INTEGRATION (has STATIC): Payload built and frozen; backend-accepted shape unproven without integration capture.
- PG-NUM-STEP needs BROWSER (has STATIC): Step attributes may render; stepper behavior unproven.
- PG-SEED-RANGE needs BROWSER (has STATIC): Seed bounds/rules differ (Vue random range); range behavior unproven. Randomize action is PG-SEED-RANDOMIZE.
- QUEUE-WORKSPACE-FROZEN needs RACE (has STATIC): Browser side holds no workspace on queue items by design (no invented ownership; server dispatch owns the boundary). Dispatch-seam proof still needs a live backend; row stays UNKNOWN per batch policy.
- EXP-NO-RETRY-ALL needs BROWSER (has STATIC): Cell-retry API exposed; absence of retry-all unproven in UI.
- EXP-HISTORY-EXPOSURE needs INTEGRATION (has STATIC): Normalization/actions exist; feed-to-Playground exposure unverified.
- REF2-METHODS needs BROWSER (has STATIC): Method taxonomy accepted; Vue method surface unverified.
- REF2-NO-AUTO needs BROWSER (has STATIC): No-Auto rule accepted; Vue method UI unverified.
- REF2-MEMORY needs BROWSER (has STATIC): Per-workflow memory accepted; Vue behavior unverified.
- REF2-CAPACITY needs BROWSER (has STATIC): Graph-derived capacity accepted; Vue behavior unverified.
- REF2-SOURCES needs BROWSER (has STATIC): Three sources accepted; Vue slot sourcing unverified.
- REF2-IDENTITY needs BROWSER (has STATIC): Stable identity accepted; Vue behavior unverified.
- REF2-THUMBS needs BROWSER (has STATIC): Thumbnails/distinction accepted; Vue behavior unverified.
- GUI2-IDENTITY needs BROWSER (has STATIC): Identity resolution accepted; Vue behavior unverified.
- GUI2-HASH needs BROWSER (has STATIC): Precedence accepted; Vue behavior unverified.
- GUI2-PROPOSE needs BROWSER (has STATIC): Propose-not-trust accepted; Vue behavior unverified.
- GUI2-REUSE needs BROWSER (has STATIC): Reuse/no-replace accepted; Vue behavior unverified.
- GUI2-PROVENANCE needs BROWSER (has STATIC): Metadata accepted; Vue behavior unverified.
- GUI2-PREPROCESSOR needs BROWSER (has STATIC): Preprocessor requirement accepted; Vue behavior unverified.
- GUI2-FALLBACK needs BROWSER (has STATIC): Fallback accepted; Vue behavior unverified.
- GUI2-EXEC needs INTEGRATION (has STATIC): Payload/backend distinction accepted; Vue behavior unverified.
- ROUTE-BACK needs BROWSER (has UNIT): Unit tests use fake history contract; no browser validation.
- ROUTE-OPENER-WINS needs BROWSER (has UNIT): Pure router precedence tested; host opener integration not.
- ROUTE-NO-REOPEN needs BROWSER (has STATIC): No browser test for close-then-hash sequence.
- ROUTE-FOCUS-SAFE needs UNIT (has STATIC): No explicit opaque-focus security test on Vue side.
- SEL2-ERASE-EQ needs BROWSER (has STATIC): Equivalence unproven; no Vue editor to verify against.
- EXP2-NO-AUTO needs BROWSER (has STATIC): No Expand UI exists to violate this yet; constraint recorded for implementation.
- SET-CONFIG-AUTH needs INTEGRATION (has STATIC): Read/save/reread implemented; authority behavior needs integration proof.
- SET-GPU needs INTEGRATION (has STATIC): GPU derives from config in source; behavior unproven.
- SET-OUTPUTS needs INTEGRATION (has STATIC): Patch/reread/projection exist; end-to-end behavior unproven.
- SET-DATASAVER needs BROWSER (has STATIC): Projection exists; exact UI/save semantics unverified.
- SET-SKIP-SEMANTICS needs INTEGRATION (has STATIC): Shapes match in source; behavior unproven.
- SET-MODEL-BLOCK needs BROWSER (has STATIC): No Vue missing-model gate found in inspected files.
- SET-NODE-RELAX needs BROWSER (has STATIC): Gate lives outside Settings implementation; unlocated.
- SET-ROLLBACK needs INTEGRATION (has STATIC): Reread/restore implemented; failure behavior unproven.
- SET-ACK needs INTEGRATION (has STATIC): Reread implemented; ack behavior unproven.
- SET-CROSSTAB needs BROWSER (has STATIC): Publish visible; listener/refetch behavior not fully verified.
- SET-BROWSER-PREFS needs BROWSER (has STATIC): Separate persisted refs exist; reload behavior unproven.
- SET-TRACING needs BROWSER (has STATIC): Selected/effective split + restore implemented; behavior unproven.
- GOLDEN-CATALOG needs BROWSER (has STATIC): Catalog/selection implemented; behavior unproven.
- GOLDEN-SEPARATION needs INTEGRATION (has STATIC): Distinct paths exist; no negative-write assertion; run-time consumption unevidenced.
- GOLDEN-AB-NEXT-RUN needs REAL_BACKEND (has STATIC): API update exists; run-time consumption not evidenced.
- GOLDEN-DEPLOY needs REAL_BACKEND (has STATIC): Polling + operation status exist; deploy behavior unproven.
- SK-OPEN needs BROWSER (has STATIC): Base selection shell exists; no drawing surface, behavior unproven.
- SK-BASE-SWITCH needs BROWSER (has STATIC): Explicit clearing wired in source; transition behavior unproven.
- SK-SETTINGS-GUARD needs RACE (has STATIC): No sketch settings or sketch-specific stale guard in Vue.
- STY-WORKFLOW-KEPT needs BROWSER (has STATIC): Test proves composition, not workflow identity; Vue has no style feature.
- LAY2-TRANSFORM needs BROWSER (has STATIC): Suite is authority but excerpt does not assert outcomes; Vue has no editor.
- LAY2-OVERLAP needs BROWSER (has STATIC): Documented as covered but exact assertion unavailable; Vue has no editor.
- STYLE-PORTAL needs BROWSER (has STATIC): Target + config exist; runtime containment unverified.
- STYLE-ZINDEX needs BROWSER (has STATIC): Numeric ordering static; overlap/focus/responsive needs browser matrix.
- STYLE-HOST-SAFE needs BROWSER (has STATIC): No live-host style-leak evidence gathered in this audit.
- WZ-OPEN-CLOSE needs BROWSER (has STATIC): Store owns lifecycle; rendered modal behavior unproven.
- WZ-PROPOSE needs BROWSER (has STATIC): Proposals-only contract documented; explicit-confirm click path unverified.
- WZ-ROLES needs BROWSER (has STATIC): Catalogs exist; save-gate enforcement unproven.
- WZ-FOCUS needs BROWSER (has STATIC): No confirmed wizard aria-modal/focus-trap evidence.
- WZ-CAPTURE needs REAL_BACKEND (has STATIC): APIs/store exist; graph capture and visible save flow incomplete.
- WZ-DRAFT needs BROWSER (has STATIC): Session draft version-scoped; reload/reopen behavior unproven.
- PRESET-CRUD needs BROWSER (has STATIC): API/store actions exist; full Vue preset UI CRUD unconfirmed.
- PRESET-IDENTITY needs BROWSER (has STATIC): ID + dirty explicit in source; behavior unproven.
- PRESET-VERSION needs BROWSER (has STATIC): Context key includes version; cross-version behavior unproven.
- PRESET-APPLY needs BROWSER (has STATIC): Apply path exists; restore behavior unproven.
- PRESET-NO-SETTINGS needs INTEGRATION (has STATIC): Override is run intent in source; isolation unproven by test.
- PRESET-CLEAR-EDITORS needs BROWSER (has STATIC): Source ownership clears; whole editor clearing unproven.
- PRESET-LOOKS-SEPARATE needs BROWSER (has STATIC): Preset UI present; separate Looks behavior unevidenced (no Looks impl).

## LEGACY SMOKE HARNESS OUTPUT — NOT PARITY VERDICTS

The 17 legacy differential scenarios below are diagnostic only. Their labels must not be
quoted as parity evidence and never enter the totals above.

- SMOKE::PG-MODEL-AUTOFILL [txt2img_basic]: UNKNOWN
- SMOKE::PG-MODEL-TYPE [txt2img_basic]: FAIL
- SMOKE::PG-MODEL-ROLES [txt2img_basic]: PASS
- SMOKE::PG-SEED [txt2img_basic]: PASS
- SMOKE::PG-ADVANCED [txt2img_basic]: FAIL
- SMOKE::PG-REORDER [txt2img_basic]: FAIL
- SMOKE::PG-VERSION-SWITCH [i2i_source]: PASS
- SMOKE::WZ-SUGGEST [wizard_graph]: FAIL
- SMOKE::WZ-GRAPH-OPS [wizard_graph]: FAIL
- SMOKE::WZ-SAVE-GATE [wizard_graph]: PASS
- SMOKE::SUB-SKETCH [i2i_source]: FAIL
- SMOKE::SUB-EDIT-MASK [inpaint_mask]: PASS — control-type parity only; exact-widget binding + mask-required gating need real-app proof
- SMOKE::GQ-EXPERIMENT [experiment_axes]: PASS — user reorder absent both sides; Vue adds a durable enqueue/remove/clear queue (superset, not legacy behavior)
- SMOKE::HV-RETRY-RESUME [txt2img_basic]: PASS — API-level parity only; per-card exposure of retry/resume/cancel/download needs runtime crawl
- SMOKE::RT-ROUTING [txt2img_basic]: PASS
- SMOKE::UP-GUARD [i2i_source]: PASS — legacy createUploadGuard vs Vue token+owner commitUpload; concurrent-overwrite race needs runtime proof
- SMOKE::DEPS-MISSING [missing_deps]: PASS — flagging surface only; non-submittable gating needs runtime proof
