# Phase 13 — Final UI Report (Studio V3 convergence, minus parked Upscale)

- Base: `b612b3e4bbd4a43431b42d3f0f39f56881779fb1` · Branch: `feat/studio-v3-phase13-final`
  · Worktree: `.slim/worktrees/studio-v3-phase13-final`
- No designer involved (per owner instruction). No Upscale implemented. No merge to main.

## Summary

**Major improvements**
- Select/Inpaint conventional controls moved OUT of the absolute canvas overlay into shelf
  hosts (`inpaint-shelf-controls`, `expand-shelf-controls`); canvas keeps image + direct-manipulation
  overlays only. Post floating compare pill moved to a utility row (only divider stays on-image).
- Queue execution honesty: queued identity validated before run (mismatch blocks with visible reason);
  full request intent frozen in snapshot (subtool/methods/references/style/guidance); placeholders block
  honestly instead of degrading into silent ordinary runs.
- Saved-settings Load is a complete lifecycle transition (actual image/compare owners cleared, workspace remounts).
- Run-gate reasons mirrored from hover-only `title` into visible topbar lines; `role="status"` on async outcomes.
- Shared shelf vocabulary: `ShelfSectionTitle` (h4), `missingImageCopy()` ("No image available"),
  shared `STATUS_LABELS`, single `postStagedEmpty`, single `placeholderCopy`/`LATER_PHASE_SUFFIX` source.
- Preset vocabulary removed from user-facing copy (saved workflow / workflow edited / Looks); `preset`
  remains internal/testid/API only.
- Sketch TOOLS default expanded (1-click tool switching restored).

**Issues found**: 33 static-audit (P0:0, P1:6, P2:18, P3:9) + 11 Pass-C review findings (7 P1, 4 P2).
**Fixed**: all 6 audit P1s, all 7 review P1s, Sketch click regression, both canvas FAILs, 2 browser-spec
contract breaks. Remaining partials are copy/structure refinements documented below or explicitly deferred.
**Deferred with reason**: 6 bounded items (see Deferred section). No silent omissions.

**Clutter reductions (measured in code)**
- Select shelf: 6 stacked rows → max 3 visible (SAM row+chips+list in one `<details>`).
- Post: 3 empty states at different depths → one staged `postStagedEmpty`; 3 placeholder phrasings/testids → one.
- Generate: 4+ "later phase" phrasings → one `placeholderCopy` + 1-line notice + `<details>`.
- Guidance: status triple → headline + 1 detail line, identity hash behind `<details>`.
- Expand: status `<p>` with 4 meanings → single `role="status"` line + Retry CTA.

**Interaction-cost impact**: no common-path action costs more clicks (table below). Two accepted
secondary-path tradeoffs (Fit/zoom, effective-prompt/identity disclosures) are documented, not silent.

## Before/after table (code evidence — live screenshots deferred, see note)

No live-browser screenshots were captured in this phase: ComfyUI server processes hang unbounded in
this environment, so all lanes ran under bounded no-server rules and verification is static
(file:line) + unit-test evidence. Each row cites the changed location instead of screenshots.

| Surface | Before (evidence) | After (fix location) | Main fixes |
|---|---|---|---|
| Generate | bare `<p>` canvas empty; 2 dead-end notes; 4 later-phase phrasings | `studio-playground.js` renderEmptyState+CTA; note action buttons; `placeholderCopy` | GEN-01/02/03 fixed; breadcrumb added (GEN-04) |
| Edit | amber-overload stale note; tooltip-only preserved values | neutral note + Run-to-refresh (honest when blocked); inline read-only values | EDIT-01/02 |
| Select/Inpaint | 6-row panel + absolute canvas overlay chrome | shelf host, ≤3 visible rows, identity-keyed rehome | SEL-01/02/03, INP-01/02; canvas rule satisfied |
| Expand | untyped status `<p>`; form inside canvas-area | `role="status"` + Retry; form relocated to shelf | EXP-01/02 |
| Post | 5–6 deep nesting; triple empties; floating compare pill | staged empty; pill in utility row, divider only on-image | POST-01/02 (nesting depth deferred) |
| Styles | browser `null` off-context; 3 header conventions; 5+ row stack | collapsed stub; shared `ShelfSectionTitle`; preview in `<details>` | STY-01/02/03 |
| Sketch | shelf+center split; 2-click tool regression risk | TOOLS expanded default (1-click); CANVAS collapsed (documented) | SKT-01/02 |
| Layout | italic pseudo-labels; label-prefix Unplaced; triple hints | `nobbox`-only badge; single hint; real labels | LAY-01/02 |
| References | no heading; submit-time-only gates | shared title; over-limit flag; live inline gate line | REF-01/02 |
| Guidance | status triple; silent 6-cap; dead-end "Guided sampler" | headline+detail; cap disclosed; candidate validated pre-confirm | GUI-01/02 |
| History/Compare | 4 missing-image phrasings; reason-less disabled Compare | one `missingImageCopy()`; inline reason + gallery slots | HST-01/02, CMP-01 |
| Presets/vocab | preset/dirty/recipe in live copy, no surface | saved-workflow vocabulary; Looks for Post presets | PRS-01/02 |
| Topbar/queue | title-only gates; queue identity loss; wrong-workflow risk | visible reason lines; identity validation; intent freeze | TOP-01/02 |

## Issue inventory (33 audit + 11 review)

Audit P1s (all FIXED): TOP-01 run-gate mirroring · SEL-01 canvas relocation · INP-02 scoped copy ·
STY-01 context stub · SKT-01 collapse/restore · PRS-01 vocabulary.
Audit P2/P3: fixed per lane reports except explicitly deferred items below; PARTIAL remnants
(GEN-02 mapping-wizard link added; GEN-03 single source added; GEN-04 refresh added, <900px hide kept
intentionally; EDIT-01 honest-disabled; EXP-02 note travels with form; POST-01 routing+wording, depth
deferred; STY-01 stubs; LAY-01 geometry fix; GUI-02 cap disclosed; HST-01 all surfaces normalized;
PRS-01 all user-facing renamed; TOP-02 divider+labels).
Review P1s (all FIXED): queue wrong-workflow guard · queue intent freeze · Load lifecycle owners ·
Select lifecycle keying · Post pill removal · Post editor-leak gate · guidance confirm validation.
Review P2s (all FIXED): draft scoping · badge geometry · breadcrumb refresh (+documented responsive hide) ·
favorites keyboard button.

## Interaction-cost table

| Restructuring | Before | After | Verdict |
|---|---|---|---|
| Select mode/op/Save | 1 | 1 | unchanged (smart auto-open) |
| Sketch tool switch | 1 | 1 | restored (was regressed to 2 mid-phase) |
| Sketch Fit/zoom | 1 | 2 | ACCEPTED secondary tradeoff, documented in code |
| Style select | 1 | 1 | unchanged |
| Effective prompt inspect | 0 | 1 | accepted secondary tradeoff |
| Guidance identity inspect | 0 | 1 | accepted secondary tradeoff |
| Post look apply | 2 | 2 | unchanged |
| Compare existing path | 3 | 3 | unchanged (gallery route optional) |
| Queue valid run | 1 | 1 | unchanged; invalid now blocks honestly |
| STY-01 stub (was unreachable/null) | — | 1 | new affordance, not a regression |

## Deferred issues (bounded, explicit)

1. POST-01 outer nesting (panel>postHost>workspace>tabs>sections) — outer layers owned by
   playground shell; documented in-code. Reason: exceeds bounded scope; no behavior harm.
2. `_RUN_LABELS` ↔ experiment/status label sharing — documented. Reason: cross-lane file; labels
   already unified within each surface.
3. History status *tones* sharing (labels shared) — documented. Reason: tone vocabularies differ
   per surface; sharing forces false uniformity.
4. Live-browser screenshots: CAPTURED post-phase via the deterministic fake harness
   (`docs/phase13/after-{generate,select,sketch,post,history,layout}.png`, 1440x900, zero console
   errors). The dedicated Select/Inpaint path additionally exposed a residual host-gating gap during
   capture (controls fell back to center); fixed by extending the shelf-host condition to
   Edit→Select / Edit→Expand regardless of tool id, verified in the final `after-select.png`
   (Select controls in shelf, canvas image-only). Fresh-instance end-to-end smoke remains deferred —
   verification stands on fake-harness evidence + unit suites. Re-run live when a bounded live harness exists.
5. Narrow-viewport (200–333px shelf) wrap checks — untested live. Reason: same as 4.
6. Pre-existing stale specs left alone: compare `A —`/`B —` prefixes (`:135–136`), queue-manager
   seven-tool rail. Reason: pre-date Phase 13, unrelated to changed copy.

## Verification

- `node --check` on all touched JS + specs: PASS.
- Scoped JS suites: guidance 29/29 · workflow-run PASS · tool-types 13/13 · presets+layout 43/43 ·
  history presentation/persisted-status PASS · inpaint/expand/golden suites 83+18 PASS.
- Full `FAST_UNIT` harness crashes the Windows pytest worker at collection (access violation, exit
  3221225477) — pre-existing environment issue, also present on base; scoped equivalents used instead.
  Documented pre-existing failures (dependency_resolver, golden_parallel, model_library_routes,
  publication_serialization, runtime_env_generated; testing_shell_integration 20; backend 76-sampled)
  verified identical on stashed baseline or asserting on untouched files.
- Workflow immutability: no stored-workflow changes; queue guards add validation only.
- No auto-run introduced; no new console-error vectors (single `<p>` reason lines, no polling loops).
- Phase 11 branch untouched · main checkout untouched (verified) · no merge performed.
