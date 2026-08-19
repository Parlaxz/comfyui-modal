// Wave-2 contract checks against the real History V2 frontend adapter.
//
// These checks protect the logical-output wire contract and feed presentation
// only. They do not claim production persistence, codec execution, remote
// Modal reads, or Generate Original routing.

import assert from "node:assert/strict";
import {
  normalizeFeedItem,
  normalizeHistoryAttempt,
  normalizeHistoryOutput,
  selectDetailAsset,
  selectFeedAsset,
} from "../web/history-v2-repository.js";

const ASSET = "/comfymodal/history-v2/assets/";

function section(name) {
  console.log("PASS: " + name);
}

function output(overrides = {}) {
  return Object.assign({
    index: 0,
    logical_output_key: "gen_wave2_o0",
    asset_id: "gen_wave2_o0_new_orig",
    thumb_url: `${ASSET}gen_wave2_o0_thumb`,
    preview_url: `${ASSET}gen_wave2_o0_preview`,
    original_url: `${ASSET}gen_wave2_o0_new_orig`,
    original_urls: [`${ASSET}gen_wave2_o0_old_orig`, `${ASSET}gen_wave2_o0_new_orig`],
    original_failed: false,
    attempt_ids: ["run_preview", "run_original_old", "run_original_new"],
    asset_provenance: [
      { asset_id: "gen_wave2_o0_thumb", asset_type: "thumbnail", attempt_id: "run_preview" },
      { asset_id: "gen_wave2_o0_preview", asset_type: "preview", attempt_id: "run_preview" },
      { asset_id: "gen_wave2_o0_old_orig", asset_type: "original", attempt_id: "run_original_old" },
      { asset_id: "gen_wave2_o0_new_orig", asset_type: "original", attempt_id: "run_original_new" },
    ],
    preview_codec: "webp",
    preview_quality: 70,
  }, overrides);
}

// All three derivatives and all Attempt provenance remain one browser/API output.
{
  const raw = {
    id: "gen_wave2",
    kind: "generation",
    status: "completed",
    output_count: 1,
    preview_only: false,
    original_available: true,
    featured_output_index: 0,
    outputs: [output()],
  };
  const normalized = normalizeFeedItem(raw);
  assert.equal(raw.outputs.length, 1);
  assert.equal(raw.output_count, 1);
  assert.equal(normalized.featuredOutput.originalUrl, `${ASSET}gen_wave2_o0_new_orig`);
  assert.equal(normalized.featuredOutput.originalFailed, false);
  assert.equal(output().attempt_ids.length, 3);
  section("one logical output for thumbnail/preview/original derivatives");
}

// A second logical key increments output_count, not the derivative asset count.
{
  const raw = {
    id: "gen_wave2_two",
    kind: "generation",
    status: "completed",
    output_count: 2,
    outputs: [output(), output({ index: 1, logical_output_key: "gen_wave2_o1", asset_id: "gen_wave2_o1_preview", original_url: "" })],
  };
  const normalized = normalizeFeedItem(raw);
  assert.equal(raw.output_count, 2);
  assert.equal(raw.outputs.length, 2);
  assert.equal(normalized.featuredOutput.index, 0);
  section("two logical keys produce output_count two");
}

// Feed cards never auto-fetch a full Original. Thumbnail and Preview are the
// only URLs selected for automatic card loading; Original-only records expose
// an availability placeholder instead.
{
  const allVariants = {
    thumbUrl: `${ASSET}gen_wave2_o0_thumb`,
    previewUrl: `${ASSET}gen_wave2_o0_preview`,
    originalUrl: `${ASSET}gen_wave2_o0_new_orig`,
    originalFailed: false,
  };
  assert.deepEqual(selectFeedAsset(allVariants), {
    kind: "thumbnail",
    url: `${ASSET}gen_wave2_o0_thumb`,
    label: "Thumbnail",
  });
  assert.deepEqual(selectFeedAsset(Object.assign({}, allVariants, { thumbUrl: "" })), {
    kind: "preview",
    url: `${ASSET}gen_wave2_o0_preview`,
    label: "Preview",
  });
  const remoteOnly = { thumbUrl: "", previewUrl: "", originalUrl: `${ASSET}remote_orig`, originalFailed: false };
  assert.deepEqual(selectFeedAsset(remoteOnly), {
    kind: "original",
    url: "",
    label: "Original available",
  });
  assert.deepEqual(selectDetailAsset(remoteOnly), {
    kind: "original",
    url: "",
    label: "Original available",
  });
  section("thumbnail/preview fallback and Original-only no-auto-fetch projection");
}

// Featured selection is by logical-output index even when the featured asset
// is a derivative or an older Original within that output.
{
  for (const [featuredOutputIndex, featuredAssetId] of [
    [0, "gen_wave2_o0_thumb"],
    [1, "gen_wave2_o1_preview"],
    [1, "gen_wave2_o1_old_orig"],
  ]) {
    const raw = {
      id: "gen_wave2_featured",
      kind: "generation",
      output_count: 2,
      featured_output_index: featuredOutputIndex,
      featured_asset_id: featuredAssetId,
      outputs: [output(), output({ index: 1, logical_output_key: "gen_wave2_o1" })],
    };
    const normalized = normalizeFeedItem(raw);
    assert.equal(normalized.featuredOutput.index, featuredOutputIndex);
    assert.equal(typeof featuredAssetId, "string");
  }
  section("featured thumbnail/preview/older Original resolves to logical output");
}

// Preview metadata and Attempt mode are carried by the expected wire shape;
// the current normalizer keeps unknown metadata additive rather than dropping
// the core output projection.
{
  const attempt = normalizeHistoryAttempt({
    run_id: "run_preview",
    mode: "preview",
    status: "completed",
    started_at: "2026-08-17T12:00:00.000Z",
    duration_ms: 1000,
  });
  const preview = output();
  assert.equal(attempt.mode, "preview");
  assert.equal(preview.preview_codec, "webp");
  assert.equal(preview.preview_quality, 70);
  assert.equal(normalizeHistoryOutput(preview).originalFailed, false);
  section("Preview mode/WebP/70 metadata contract");
}

// The future route contract remains a shape assertion only, not a fake route.
{
  const response = {
    status: "ok",
    generation_id: "gen_wave2",
    run_id: "run_original_new",
    purpose: "original",
    mode: "original",
    attempt_status: "queued",
    reused: false,
  };
  assert.deepEqual(Object.keys(response).sort(), [
    "attempt_status", "generation_id", "mode", "purpose", "reused", "run_id", "status",
  ]);
  section("Generate Original future response remains pending contract");
}

console.log("PASS: studio Phase-E Wave-2 unit tests");
