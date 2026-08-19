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

// 15-16. E4A sparse safety remains intact and Generate Original stays deferred.
{
  const parent = { children: [], appendChild(child) { this.children.push(child); } };
  appendIfPresent(parent, null);
  appendIfPresent(parent, { nodeType: 1 });
  assert.equal(parent.children.length, 1);
  assert.equal(detailSource.includes("appendIfPresent(col, buildParamsSection(record))"), true);
  assert.equal(detailSource.includes('text: "No outputs"'), true);
  section("15. E4A sparse and empty-output detail safety remains green");

  assert.equal(detailSource.includes("repo.generateOriginal"), false);
  assert.equal(detailSource.includes("Generate Original (unavailable)"), true);
  assert.equal(experimentSource.includes("Generate Original (unavailable)"), true);
  section("16. Generate Original sends no frontend request before E3B2");
}

console.log("PASS: studio phase E History presentation unit tests");
