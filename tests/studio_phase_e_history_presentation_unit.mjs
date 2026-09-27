// E4B History presentation contract tests.
//
// These tests cover pure asset selection/normalization and source-level guards
// for the DOM-only rendering paths. They never start a browser or request an
// Original asset.

import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import {
  normalizeFeedItem,
  normalizeHistoryAttempts,
  selectDetailAsset,
  selectFeedAsset,
} from "../web/history-v2-repository.js";
import { selectGenerationFeedAsset } from "../web/studio-history-v2.js";
import {
  appendIfPresent,
  historyAttemptPurposeLabel as generationAttemptPurposeLabel,
  selectGenerationDetailAsset,
} from "../web/studio-history-v2-detail.js";
import {
  historyAttemptPurposeLabel as cellAttemptPurposeLabel,
  selectExperimentCellAsset,
} from "../web/studio-history-v2-experiment.js";

const ROOT = path.join(import.meta.dirname, "..");
const feedSource = fs.readFileSync(path.join(ROOT, "web", "studio-history-v2.js"), "utf8");
const detailSource = fs.readFileSync(path.join(ROOT, "web", "studio-history-v2-detail.js"), "utf8");
const experimentSource = fs.readFileSync(path.join(ROOT, "web", "studio-history-v2-experiment.js"), "utf8");

function section(name) {
  console.log("PASS: " + name);
}

function output(overrides = {}) {
  return Object.assign({
    thumbUrl: "",
    previewUrl: "",
    originalUrl: "",
    originalFailed: false,
  }, overrides);
}

function generation(overrides = {}) {
  return Object.assign({
    id: "gen_e4b",
    kind: "generation",
    status: "completed",
    output_count: 1,
    outputs: [output()],
  }, overrides);
}

// 1-4. Feed policy: thumbnail, Preview fallback, then deliberate state.
{
  assert.deepEqual(selectFeedAsset(output({ thumbUrl: "/thumb" })), {
    kind: "thumbnail", url: "/thumb", label: "Thumbnail",
  });
  assert.equal(selectGenerationFeedAsset({ featuredOutput: output({ thumbUrl: "/thumb" }) }).kind, "thumbnail");
  section("1. Feed uses Thumbnail first");

  assert.deepEqual(selectFeedAsset(output({ previewUrl: "/preview" })), {
    kind: "preview", url: "/preview", label: "Preview",
  });
  assert.equal(selectGenerationFeedAsset({ featuredOutput: output({ previewUrl: "/preview" }) }).kind, "preview");
  section("2. Feed falls back to Preview");

  const originalOnly = selectFeedAsset(output({ originalUrl: "/original" }));
  assert.equal(originalOnly.url, "", "feed never selects Original bytes");
  assert.equal(originalOnly.kind, "original");
  assert.equal(feedSource.includes("src: asset.url"), true);
  assert.equal(feedSource.includes("src: slot.originalUrl"), false);
  section("3. Feed never auto-loads Original");

  assert.deepEqual(selectFeedAsset(output({ originalUrl: "/original" })), {
    kind: "original", url: "", label: "Original available",
  });
  assert.equal(selectFeedAsset(output({ originalAvailable: true })).label, "Original available");
  assert.deepEqual(selectFeedAsset(output()), {
    kind: "none", url: "", label: "No image",
  });
  section("4. Original-only feed uses an intentional placeholder");
}

// 5-7. Experiment grid/cover uses the same lightweight policy.
{
  assert.equal(selectExperimentCellAsset(output({ thumbUrl: "/cell-thumb" })).kind, "thumbnail");
  assert.equal(experimentSource.includes("selectExperimentCellAsset(cell)"), true);
  section("5. Experiment cell uses Thumbnail");

  assert.equal(selectExperimentCellAsset(output({ previewUrl: "/cell-preview" })).kind, "preview");
  assert.equal(experimentSource.includes('src: asset.url'), true);
  section("6. Experiment cell falls back to Preview");

  const cellOriginal = selectExperimentCellAsset(output({ originalUrl: "/cell-original" }));
  assert.equal(cellOriginal.url, "");
  assert.equal(cellOriginal.label, "Original available");
  assert.equal(experimentSource.includes("_cellAssetPlaceholder(asset)"), true);
  section("7. Experiment Original-only cell uses a placeholder");
}

// 8-10. Detail prefers Preview, then Thumbnail, and only loads Original on click.
{
  assert.deepEqual(selectDetailAsset(output({ previewUrl: "/preview", thumbUrl: "/thumb" })), {
    kind: "preview", url: "/preview", label: "Preview",
  });
  assert.equal(selectGenerationDetailAsset({ featuredOutput: output({ previewUrl: "/preview" }) }).kind, "preview");
  section("8. Detail automatically displays Preview");

  assert.equal(selectGenerationDetailAsset({ featuredOutput: output({ originalUrl: "/original" }) }).url, "");
  assert.equal(detailSource.includes("src: feat.originalUrl"), true, "Original loader remains available in the click handler");
  assert.equal(detailSource.includes('text: "View Original"'), true);
  assert.equal(detailSource.includes('data-testid": "history-v2-view-original"'), true);
  section("9. Detail does not auto-load Original");

  const clickIndex = detailSource.indexOf('text: "View Original"');
  const originalSourceIndex = detailSource.indexOf("src: feat.originalUrl");
  assert.ok(clickIndex >= 0 && clickIndex < originalSourceIndex, "Original src is created after the explicit action");
  section("10. Existing Original loads only after View Original");
}

// 11-14. Badge and failure/attempt purpose semantics.
{
  assert.equal(selectFeedAsset(output({ previewUrl: "/preview" })).kind, "preview");
  assert.equal(selectFeedAsset(output({ thumbUrl: "/thumb", previewUrl: "/preview" })).kind, "thumbnail");
  assert.equal(feedSource.includes('asset.kind === "preview"'), true);
  assert.equal(detailSource.includes('displayed.kind === "preview"'), true);
  assert.equal(experimentSource.includes('asset.kind === "preview"'), true);
  assert.equal(feedSource.includes(".webp"), false);
  assert.equal(detailSource.includes(".webp"), false);
  section("11. Preview badge follows asset purpose, never file extension");

  const failed = normalizeFeedItem(generation({
    preview_only: true,
    outputs: [output({ previewUrl: "/preview", originalFailed: true })],
  }));
  assert.equal(failed.featuredOutput.previewUrl, "/preview");
  assert.equal(failed.featuredOutput.originalFailed, true);
  assert.equal(selectDetailAsset(failed.featuredOutput).kind, "preview");
  assert.equal(detailSource.includes("Original failed \\u2014 preview retained"), true);
  section("12. Failed Original retains Preview and failure state");

  const retained = normalizeFeedItem(generation({
    original_available: true,
    outputs: [output({ originalUrl: "/original", originalFailed: false })],
  }));
  const attempts = normalizeHistoryAttempts([
    { mode: "original", status: "completed", run_id: "run_success" },
    { mode: "original", status: "failed", run_id: "run_retry", error: "OOM" },
  ]);
  assert.equal(retained.featuredOutput.originalUrl, "/original");
  assert.equal(retained.featuredOutput.originalFailed, false);
  assert.equal(attempts[1].mode, "original");
  assert.equal(attempts[1].status, "failed");
  section("13. Retained Original stays available after failed retry");

  assert.equal(generationAttemptPurposeLabel("preview"), "Preview");
  assert.equal(generationAttemptPurposeLabel("original"), "Original");
  assert.equal(cellAttemptPurposeLabel("preview"), "Preview");
  assert.equal(cellAttemptPurposeLabel("original"), "Original");
  assert.equal(detailSource.includes("historyAttemptPurposeLabel(a.mode || a.purpose)"), true);
  assert.equal(experimentSource.includes("historyAttemptPurposeLabel(a && (a.mode || a.purpose))"), true);
  section("14. Attempt purpose labels remain distinct from status");
}

// 15-16. E4A sparse safety remains intact; E4C activates Generate Original
// without regressing the eager-Original prohibitions.
{
  const parent = { children: [], appendChild(child) { this.children.push(child); } };
  appendIfPresent(parent, null);
  appendIfPresent(parent, { nodeType: 1 });
  assert.equal(parent.children.length, 1);
  assert.equal(detailSource.includes("appendIfPresent(col, buildParamsSection(record))"), true);
  assert.equal(detailSource.includes('text: "No outputs"'), true);
  section("15. E4A sparse and empty-output detail safety remains green");

  // E4C/E4D: the actions POST through the repository's frozen Generation
  // routes — Retry Original uses the dedicated /original/retry method; the
  // ordinary /original route stays for Generate/Generate Again.  Original
  // bytes are still assigned only inside the View Original handler.
  assert.equal(detailSource.split("_runGenerateOriginal(false)").length - 1, 1,
    "ordinary first Generate keeps exactly one /original call site");
  {
    const retryBtnIndex = detailSource.lastIndexOf('"history-v2-retry-original"');
    const failedBranch = detailSource.slice(retryBtnIndex, retryBtnIndex + 500);
    assert.equal(failedBranch.includes("_runRetryOriginal()"), true,
      "failed phase dispatches the dedicated retry action");
    assert.equal(failedBranch.includes("_runGenerateOriginal"), false,
      "the Retry control never posts ordinary /original");
  }
  assert.equal(detailSource.includes("repo.retryOriginal(generationId)"), true,
    "Retry Original calls the dedicated retry repository method");
  assert.equal(detailSource.includes("repo.generateOriginal(generationId,"), true);
  assert.equal(experimentSource.includes("repo.generateOriginalForCell(genId,"), true);
  assert.equal(experimentSource.includes("repo.retryOriginalForCell(genId)"), true,
    "cell Retry uses the dedicated retry repository method");
  assert.equal(detailSource.includes("src: feat.originalUrl"), true,
    "Original loader remains click-only inside View Original");
  const clickIndex = detailSource.indexOf('text: "View Original"');
  const originalSourceIndex = detailSource.indexOf("src: feat.originalUrl");
  assert.ok(clickIndex >= 0 && clickIndex < originalSourceIndex);
  section("16. Generate Original is backend-routed; Original loading stays explicit");
}

// 17-23. I4 History polish: shared-primitives migration + accessibility
// contracts (PHASE_I4; I1 freeze §3.1/§3.3/§3.4/§3.5).  Source pins where the
// source IS the contract; runtime behavior is proven by the fake E2E spec.
{
  // ── Loading primitive migration (truthful labels, frozen semantics). ──
  assert.equal(feedSource.includes('from "./studio-loading.js"'), true,
    "feed imports the shared loading primitive");
  assert.equal(detailSource.includes('from "./studio-loading.js"'), true,
    "generation detail imports the shared loading primitive");
  assert.equal(experimentSource.includes('from "./studio-loading.js"'), true,
    "experiment detail imports the shared loading primitive");
  assert.equal(feedSource.includes('label: "Loading history\\u2026"'), true);
  assert.equal(feedSource.includes('testid: "history-v2-loading"'), true);
  assert.equal(feedSource.includes('label: "Loading experiment\\u2026"'), true);
  assert.equal(feedSource.includes('testid: "history-v2-experiment-loading"'), true);
  assert.equal(detailSource.includes('label: "Loading generation\\u2026"'), true);
  assert.equal(detailSource.includes('testid: "history-v2-detail-loading"'), true);
  assert.equal(experimentSource.includes('label: "Loading experiment\\u2026"'), true);
  assert.equal(experimentSource.includes('testid: "history-v2-experiment-detail-loading"'), true);
  // The bare generic label never regresses onto History surfaces.
  for (const [name, src] of [["feed", feedSource], ["detail", detailSource], ["experiment", experimentSource]]) {
    assert.equal(src.includes('text: "Loading\\u2026"'), false,
      `${name} must not render a context-free "Loading..." anymore`);
  }
  // Load more button state stays custom (I1 §3.4: stays custom).
  assert.equal(feedSource.includes('text: loading ? "Loading\\u2026" : "Load more"'), true,
    "Load more button keeps its own stateful label");
  section("17. History loading sites consume renderLoadingState with truthful labels");

  // ── Chip migration: cm-chip base + truthful data-tone, legacy classes
  //    preserved verbatim, status meaning unchanged. ──
  const toneMap = /completed:\s*"ok"|completed_with_failures:\s*"warn"|failed:\s*"error"/;
  for (const [name, src] of [["feed", feedSource], ["detail", detailSource], ["experiment", experimentSource]]) {
    assert.equal(src.includes('+ " cm-chip"'), true, `${name} chips carry the shared base class`);
    assert.equal(src.includes("STATUS_TONES"), true, `${name} maps tones from actual vocabulary`);
    assert.equal(toneMap.test(src), true, `${name} tone map covers ok/warn/error`);
    assert.equal(src.includes('class: "comfymodal-studio-history-v2-chip status-" + key + " cm-chip"'), true,
      `${name} preserves the legacy status-* class verbatim`);
  }
  assert.equal(experimentSource.includes('queued: "running"'), true,
    "queued/pending cells map to the running tone");
  section("18. History status chips adopt cm-chip + data-tone without dropping legacy classes");

  // ── Page heading: truthful h2 under the shell h1, visually hidden via the
  //    clip pattern (never display:none / visibility:hidden / hidden). ──
  assert.equal(feedSource.includes('el("h2"'), true, "feed renders an h2");
  assert.equal(feedSource.includes('text: "History"'), true, "h2 text is the truthful page title");
  assert.equal(feedSource.includes('"data-testid": "history-v2-page-title"'), true);
  assert.equal(feedSource.includes("clip:rect(0 0 0 0)"), true, "offscreen clip pattern used");
  const styleIdx = feedSource.indexOf("PAGE_TITLE_OFFSCREEN_STYLE =");
  const styleBlock = feedSource.slice(styleIdx, styleIdx + 300);
  assert.equal(/display:\s*none/.test(styleBlock), false, "no display:none");
  assert.equal(/visibility:\s*hidden/.test(styleBlock), false, "no visibility:hidden");
  // Feed page mount AND back-navigation rebuild both carry the heading.
  assert.equal(feedSource.split("root.appendChild(_pageHeading())").length - 1, 2,
    "heading present on initial mount and feed rebuild");
  // Card titles are NOT promoted into headings.
  assert.equal(feedSource.includes('el("h3"'), false, "cards stay styled text, not headings");
  section("19. History page carries an accessible visually-hidden h2");

  // ── Empty-state migration: ordinary emptiness via the copy-free
  //    primitive, caller-owned copy and action preserved. ──
  assert.equal(feedSource.includes("renderEmptyState({"), true);
  assert.equal(feedSource.includes('title: "No history matches your filters"'), true,
    "record-specific empty copy preserved");
  assert.equal(feedSource.includes('text: "Clear filters"'), true, "Clear filters action preserved");
  assert.equal(feedSource.includes('testid: "history-v2-empty"'), true);
  // Tiny sub-component placeholders stay bespoke (deliberately not forced).
  assert.equal(feedSource.includes("_assetPlaceholder(asset, cls)"), true);
  assert.equal(detailSource.includes("comfymodal-studio-history-v2-output-thumb-empty"), true);
  assert.equal(experimentSource.includes("_cellAssetPlaceholder(asset)"), true);
  section("20. Feed-level empty state uses renderEmptyState; tiny placeholders stay bespoke");

  // ── Favorite accessible names: record context on every star family. ──
  assert.equal(feedSource.includes("_favoriteAccessibleName(record"), true,
    "feed stars use the contextual name builder");
  assert.equal(feedSource.includes('slice(-6)'), true,
    "only short id tails are exposed, never full UUIDs");
  assert.equal(feedSource.includes('"Remove " : "Add "'), true);
  assert.equal(experimentSource.includes('"Add experiment to favorites"'), true,
    "experiment header star names its kind");
  assert.equal(experimentSource.includes('_cellFavoriteName(value)'), true,
    "per-cell stars get cell context");
  assert.equal(experimentSource.includes('"Add generation for "'), true);
  section("21. Favorite controls gain distinguishable record/cell context");

  // ── Generation detail focus-in + invoker restore (Escape path intact). ──
  assert.equal(detailSource.includes("_invoker"), true, "invoker captured at open");
  assert.equal(detailSource.includes("_ensureDialogFocus()"), true,
    "every mount-state render re-asserts dialog focus");
  assert.equal(detailSource.includes('_restoreInvokerFocus();'), true,
    "close restores focus to the invoking element");
  assert.equal(detailSource.includes('content.querySelector("button:not([disabled])")'), true,
    "focus-in targets the close button present in all states");
  assert.equal(detailSource.includes("_startOriginalPolling"), true,
    "polling machinery untouched by the focus plumbing");
  section("22. Generation detail moves focus in on open and restores it on close");

  // ── Experiment detail focus-in (page-swap analog) lives at the swap site.
  assert.equal(feedSource.includes('page.querySelector("button:not([disabled])")'), true,
    "experiment page focuses its first enabled control after the swap");
  assert.equal(feedSource.includes("searchInput.focus()"), true,
    "back-navigation returns a deterministic keyboard anchor");
  section("23. Experiment detail open/back keyboard anchors pinned");
}

console.log("PASS: studio phase E History presentation unit tests");
