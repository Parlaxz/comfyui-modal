// Phase-E wire-contract tests against the real History V2 frontend normalizer.
//
// These tests intentionally do not call a Generate Original endpoint. The
// response object below is the frozen placeholder contract for a later E3B/E4B
// implementation; the current frontend remains unavailable by design.

import assert from "node:assert/strict";
import { normalizeFeedItem } from "../web/history-v2-repository.js";

const ASSET_PREFIX = "/comfymodal/history-v2/assets/";

function generation(overrides = {}) {
  return Object.assign({
    id: "gen_phase_e",
    kind: "generation",
    status: "completed",
    workflow_name: "Phase E Workflow",
    preset_name: "Phase E Preset",
    prompt: "phase e contract",
    created_at: "2026-08-10T12:00:00.000Z",
    outputs: [{
      index: 0,
      thumb_url: `${ASSET_PREFIX}thumb`,
      preview_url: `${ASSET_PREFIX}preview`,
      original_url: "",
      original_failed: false,
    }],
    output_count: 1,
    preview_only: true,
    original_available: false,
  }, overrides);
}

function section(name) {
  console.log("PASS: " + name);
}

// Preview-only state is normalized as image-bearing and original-unavailable.
{
  const record = normalizeFeedItem(generation());
  assert.equal(record.kind, "generation");
  assert.equal(record.previewOnly, true);
  assert.equal(record.originalAvailable, false);
  assert.equal(record.featuredOutput.previewUrl, `${ASSET_PREFIX}preview`);
  assert.equal(record.featuredOutput.originalUrl, "");
  assert.equal(record.featuredOutput.originalFailed, false);
  section("preview-only normalization");
}

// A failed Original is visible without replacing the Preview.
{
  const record = normalizeFeedItem(generation({
    preview_only: true,
    original_failed: true,
    outputs: [{
      index: 0,
      thumb_url: `${ASSET_PREFIX}thumb-failed`,
      preview_url: `${ASSET_PREFIX}preview-failed`,
      original_url: "",
      original_failed: true,
    }],
  }));
  assert.equal(record.featuredOutput.previewUrl, `${ASSET_PREFIX}preview-failed`);
  assert.equal(record.featuredOutput.originalFailed, true);
  assert.equal(record.originalAvailable, false);
  section("failed Original retains Preview");
}

// A successful Original remains the preferred available output.
{
  const record = normalizeFeedItem(generation({
    preview_only: false,
    original_available: true,
    outputs: [{
      index: 0,
      thumb_url: `${ASSET_PREFIX}thumb-original`,
      preview_url: `${ASSET_PREFIX}preview-original`,
      original_url: `${ASSET_PREFIX}original`,
      original_failed: false,
    }],
  }));
  assert.equal(record.previewOnly, false);
  assert.equal(record.originalAvailable, true);
  assert.equal(record.featuredOutput.originalUrl, `${ASSET_PREFIX}original`);
  assert.equal(record.featuredOutput.originalFailed, false);
  section("successful Original preference");
}

// The browser-facing payload never contains a producer modal:// URI.
{
  const record = normalizeFeedItem(generation({
    preview_only: false,
    original_available: true,
    outputs: [{
      index: 0,
      thumb_url: "",
      preview_url: "",
      original_url: `${ASSET_PREFIX}remote-original`,
      original_failed: false,
    }],
  }));
  assert.equal(record.featuredOutput.originalUrl, `${ASSET_PREFIX}remote-original`);
  assert.equal(JSON.stringify(record).includes("modal://"), false);
  section("managed remote Original URL projection");
}

// One-definition Experiment request shape: Preview options are frozen in the
// definition; matrix cells and concurrency remain server-owned.
{
  const body = {
    experiment_id: "exp_phase_e",
    name: "Phase E Preview Sweep",
    definition: {
      modal_options: { enabled: true, codec: "webp", quality: 70 },
      axes: { seed: { values: [111, 222] } },
    },
  };
  assert.deepEqual(Object.keys(body).sort(), ["definition", "experiment_id", "name"]);
  assert.deepEqual(body.definition.modal_options, { enabled: true, codec: "webp", quality: 70 });
  assert.equal(Object.prototype.hasOwnProperty.call(body, "cells"), false);
  assert.equal(Object.prototype.hasOwnProperty.call(body, "concurrency"), false);
  section("one-definition frozen Experiment shape");
}

// Future E3B/E4B response shape only. No frontend consumer or fake endpoint is
// introduced by this test.
{
  const response = {
    status: "ok",
    generation_id: "gen_phase_e",
    run_id: "run_phase_e_original",
    purpose: "original",
    mode: "original",
    attempt_status: "queued",
    reused: false,
  };
  assert.deepEqual(Object.keys(response).sort(), [
    "attempt_status", "generation_id", "mode", "purpose", "reused", "run_id", "status",
  ]);
  assert.equal(response.mode, "original");
  assert.equal(response.purpose, "original");
  section("Generate Original placeholder response");
}
