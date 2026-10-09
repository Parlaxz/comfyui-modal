// Shared image-viewer input contract (Playground preview ↔ History detail).
//
// Both surfaces that show one output at full size must resolve the SAME
// viewer inputs from the SAME underlying data: the canonical record, the
// displayed image variant, and the timing payload. These tests pin that
// contract at the pure-function level (no DOM, no browser, no network).
//
// Regression guard for the drift this file exists to prevent: the Playground
// preview used to re-shape the History record locally (its own timing merge,
// its own prompt/params precedence, and the raw canvas URL), so the same run
// rendered differently in the two overlays.

import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import {
  normalizeFeedItem,
} from "../web/history-v2-repository.js";
import {
  buildViewerRecordFromRun,
  generationIdForLegacyRunId,
  normalizeStudioRun,
  resolveViewerInput,
} from "../web/studio-run-normalizer.js";
import { selectGenerationDetailAsset } from "../web/studio-history-v2-detail.js";
import { viewerMergedParams } from "../web/studio-ui.js";

const ROOT = path.join(import.meta.dirname, "..");
const playgroundSource = fs.readFileSync(path.join(ROOT, "web", "studio-playground.js"), "utf8");
const playgroundStateSource = fs.readFileSync(path.join(ROOT, "web", "studio-playground-state.js"), "utf8");
const detailSource = fs.readFileSync(path.join(ROOT, "web", "studio-history-v2-detail.js"), "utf8");

function section(name) {
  console.log("PASS: " + name);
}

// Canonical controls shared by both fixture shapes below.
const CONTROLS = {
  prompt: "A blue fox beside a silver lake",
  negative_prompt: "blurry, low detail",
  seed: 1006800347249813,
  steps: 20,
  cfg: 7,
  guidance: 7,
  sampler: "euler",
  scheduler: "normal",
  denoise: 1,
  width: 1024,
  height: 1024,
};
// Flat legacy timing keys — the shape the backend stores in timing_summary /
// run-history timings. Each maps 1:1 onto a viewer timing bucket.
const TIMINGS = {
  end_to_end_total_ms: 4523,
  studio_queue_ms: 210,
  model_load_ms: 120,
  clip_encode_ms: 450,
  sampling_ms: 3200,
  vae_decode_ms: 280,
  image_io_ms: 60,
};
const STARTED_AT = "2026-01-01T00:00:00.000Z";
const COMPLETED_AT = "2026-01-01T00:00:04.523Z";

// A History V2 generation record as the backend projects it (index rows carry
// duration_ms and timing_summary; the detail payload adds outputs[]).
function historyRaw() {
  return {
    id: "gen_1",
    run_id: "gen_1",
    kind: "generation",
    status: "completed",
    duration_ms: 4523,
    workflow: "SDXL Portrait",
    workflow_version: 4,
    prompt: CONTROLS.prompt,
    negative_prompt: CONTROLS.negative_prompt,
    started_at: STARTED_AT,
    completed_at: COMPLETED_AT,
    models: ["sdxl-base.safetensors"],
    tags: ["portrait"],
    controls: CONTROLS,
    timing_summary: TIMINGS,
    outputs: [{
      preview_url: "/comfymodal/assets/preview_1",
      thumb_url: "/comfymodal/assets/thumb_1",
      original_url: "/comfymodal/assets/original_1",
    }],
  };
}

// The same run as a local run-history entry (no History V2 projection yet).
function localRun() {
  const rawEntry = {
    run_id: "gen_1",
    kind: "playground_run",
    status: "completed",
    duration_ms: 4523,
    workflow_name: "SDXL Portrait",
    prompt: CONTROLS.prompt,
    negative_prompt: CONTROLS.negative_prompt,
    started_at: STARTED_AT,
    completed_at: COMPLETED_AT,
    timings: TIMINGS,
    output_path: "",
    asset_id: "asset_1",
    extra: {
      prompt: CONTROLS.prompt,
      negative_prompt: CONTROLS.negative_prompt,
      resolved_controls: CONTROLS,
      requested_controls: CONTROLS,
      studio_preset_label: "SDXL Portrait",
      studio_feature_id: "txt2img",
    },
  };
  return normalizeStudioRun(rawEntry, "/comfymodal");
}

// ── 1. One asset policy for both surfaces ────────────────────────────────
{
  const preview = resolveViewerInput({
    featuredOutput: { previewUrl: "/p", thumbUrl: "/t", originalUrl: "/o" },
  });
  assert.equal(preview.imageUrl, "/p", "Preview is the display derivative first");
  assert.equal(selectGenerationDetailAsset({
    featuredOutput: { previewUrl: "/p", thumbUrl: "/t" },
  }).url, "/p");

  const both = resolveViewerInput({
    featuredOutput: { previewUrl: "", thumbUrl: "/t", originalUrl: "/o" },
  });
  assert.equal(both.imageUrl, "/o", "Original beats a capped thumbnail when both project");

  const originalOnly = resolveViewerInput({
    featuredOutput: { originalUrl: "/o" },
  });
  assert.equal(originalOnly.imageUrl, "", "Original-only never eagerly fetches bytes");
  assert.equal(originalOnly.output.label, "Original available");

  const recordedOriginal = resolveViewerInput({
    originalAvailable: true,
    featuredOutput: {},
  });
  assert.equal(recordedOriginal.imageUrl, "", "originalAvailable alone stays a placeholder");

  section("1. Shared asset policy (Preview > Original beside thumb > placeholder)");
}

// ── 2. Caller-known image covers a record with no projected variant ──────
{
  const input = resolveViewerInput({ featuredOutput: {} }, "/comfymodal/assets/asset_1");
  assert.equal(input.imageUrl, "/comfymodal/assets/asset_1");
  const projected = resolveViewerInput(
    { featuredOutput: { previewUrl: "/p" } }, "/comfymodal/assets/asset_1",
  );
  assert.equal(projected.imageUrl, "/p", "a projected variant wins over the fallback URL");
  const nullFallback = resolveViewerInput({ featuredOutput: {} }, null);
  assert.equal(nullFallback.imageUrl, "");
  section("2. Fallback image URL only fills an unprojected record");
}

// ── 3. History record → viewer inputs (unchanged behavior) ───────────────
{
  const record = normalizeFeedItem(historyRaw());
  const input = resolveViewerInput(record);
  assert.equal(input.imageUrl, "/comfymodal/assets/preview_1");
  assert.equal(input.timing, record.timing, "timing passes through untouched");
  assert.deepEqual(Object.keys(input.timing).sort(), Object.keys(TIMINGS).sort());
  assert.equal(input.record.status, record.status);
  assert.equal(input.record.runId, record.runId);
  assert.equal(input.record.controls, record.controls);
  assert.equal(input.record.fullRenderFailed, false);
  assert.deepEqual(selectGenerationDetailAsset(record), input.output,
    "History detail asset selection IS the shared policy");
  section("3. History record resolves the same viewer inputs as before");
}

// ── 4. PARITY: a local run and a History record of that run agree ────────
//
// This is the contract the user-visible overlays depend on: identical status,
// identity, prompt, dates, controls grid, timing buckets, and image.
{
  const history = normalizeFeedItem(historyRaw());
  const run = localRun();
  const runRecord = buildViewerRecordFromRun(run, "/comfymodal/assets/asset_1");
  assert.ok(runRecord, "a run produces a viewer record");

  const historyInput = resolveViewerInput(history);
  const runInput = resolveViewerInput(runRecord, "/comfymodal/assets/asset_1");

  // Parity is a property of the PROJECTED records the viewer renders — the
  // raw shapes legitimately differ (a durable record projects asset variants,
  // a run projects one image), and projecting is what erases that difference.
  assert.deepEqual(runInput.record.fullRenderFailed, historyInput.record.fullRenderFailed);
  assert.deepEqual(viewerMergedParams(runInput.record), viewerMergedParams(historyInput.record),
    "the projected controls grid resolves identically on both surfaces");
  assert.equal(runInput.imageUrl, "/comfymodal/assets/asset_1");

  // Identity / status / timestamps
  assert.equal(runRecord.status, history.status);
  assert.equal(runRecord.status, "completed");
  assert.equal(runRecord.runId, history.runId);
  assert.equal(runRecord.runId, "gen_1");
  assert.equal(runRecord.prompt, history.prompt);
  assert.equal(runRecord.negativePrompt, history.negativePrompt);
  assert.equal(runRecord.workflow, history.workflow);
  assert.equal(runRecord.startedAt, history.startedAt);
  assert.equal(runRecord.completedAt, history.completedAt);
  assert.equal(runRecord.durationMs, history.durationMs);
  assert.equal(runInput.timing.end_to_end_total_ms, historyInput.timing.end_to_end_total_ms);

  // Controls grid: same rows with the same values (the grid re-orders known
  // keys itself, so key order is not part of the contract).
  // What the grid actually renders: buildViewerParamsGrid skips prompt keys
  // (the prompt renders in its own accordion), leaving the ordered controls.
  const gridKeys = ["seed", "steps", "cfg", "guidance", "sampler", "scheduler",
    "denoise", "width", "height"];
  const runGrid = {};
  const historyGrid = {};
  gridKeys.forEach(function (key) {
    runGrid[key] = viewerMergedParams(runInput.record)[key];
    historyGrid[key] = viewerMergedParams(historyInput.record)[key];
  });
  assert.deepEqual(runGrid, {
    seed: CONTROLS.seed, steps: CONTROLS.steps, cfg: CONTROLS.cfg,
    guidance: CONTROLS.guidance, sampler: CONTROLS.sampler,
    scheduler: CONTROLS.scheduler, denoise: CONTROLS.denoise,
    width: CONTROLS.width, height: CONTROLS.height,
  });
  assert.deepEqual(runGrid, historyGrid, "the rendered grid matches History's");

  // Every timing bucket the History flow renders is fed by the run's flow too.
  for (const key of ["studio_queue_ms", "model_load_ms", "clip_encode_ms",
    "sampling_ms", "vae_decode_ms", "image_io_ms", "end_to_end_total_ms"]) {
    assert.equal(runInput.timing[key], TIMINGS[key], "timing bucket key " + key);
  }
  section("4. Local run and History record produce identical viewer inputs");
}

// ── 5. No fabrication from thin air ──────────────────────────────────────
{
  const runRecord = buildViewerRecordFromRun(localRun(), "");
  assert.deepEqual(runRecord.models, [], "a local run projects no model list");
  assert.deepEqual(runRecord.tags, [], "a local run projects no tags");
  assert.equal(runRecord.favorite, false);
  assert.equal(runRecord.note, "");
  const empty = buildViewerRecordFromRun(null, "/img");
  assert.equal(empty, null, "no run → no record");
  const bare = buildViewerRecordFromRun({}, "/img");
  assert.equal(resolveViewerInput(bare, "/img").imageUrl, "/img");
  section("5. Absent fields stay absent (nothing invented)");
}

// ── 6. A History-sourced run is already canonical ────────────────────────
{
  const history = normalizeFeedItem(historyRaw());
  const asRun = Object.assign({}, history, { _historyKind: "generation" });
  const passed = buildViewerRecordFromRun(asRun, "/canvas.png");
  assert.equal(passed, asRun, "already-canonical records pass through untouched");
  assert.equal(resolveViewerInput(passed).imageUrl, "/comfymodal/assets/preview_1",
    "projected assets survive the run path");
  const noVariant = buildViewerRecordFromRun(
    { id: "gen_2", featuredOutput: {} }, "/canvas.png",
  );
  assert.equal(resolveViewerInput(noVariant).imageUrl, "/canvas.png",
    "a variant-less canonical record gains the caller image as its preview");
  section("6. Canonical (History-sourced) records keep their projection");
}

// ── 7. Source guards: one call path, no local re-shaping ─────────────────
{
  assert.equal(playgroundSource.includes("buildViewerRecordFromRun(_run, outputUrl)"), true);
  assert.equal(playgroundSource.includes("resolveViewerInput(_record, outputUrl)"), true);
  assert.equal(playgroundSource.includes("_viewer.imageUrl"), true);
  assert.equal(playgroundSource.includes("_viewer.timing"), true);
  assert.equal(playgroundSource.includes("normalizeFeedItem("), false,
    "the Playground no longer re-normalizes History records locally");
  assert.equal(playgroundSource.includes("historyGenerationIdForRunId"), false,
    "no frontend derivation of backend identities");
  assert.equal(detailSource.includes("const viewer = resolveViewerInput(record);"), true,
    "History detail renders through the shared resolver too");
  assert.equal(detailSource.includes("imageUrl: viewer.imageUrl"), true);
  assert.equal(detailSource.includes("imageUrl: displayed.url"), false,
    "history no longer resolves the displayed asset with its own copy");
  section("7. Both surfaces mount the shell through the shared resolver");
}

// ── 8. The run→record bridge travels with the run ─────────────────────────
//
// A run id is not a generation id and nothing else links the two, so the
// backend stamps the generation id at record time and the frontend carries
// it on every run object: responses, normalized runs, persisted runs, and the
// preview resolver all read the same field.
{
  assert.equal(normalizeStudioRun({ id: "r_1", history_generation_id: "gen_abc" }).generationId, "gen_abc");
  assert.equal(normalizeStudioRun({ id: "r_1", extra: { historyGenerationId: "gen_def" } }).generationId, "gen_def");
  assert.equal(normalizeStudioRun({ id: "r_1" }).generationId, "");
  assert.equal(playgroundSource.includes("history_generation_id: result.historyGenerationId"), true,
    "direct-run results bridge the backend-stamped generation id");
  assert.equal(playgroundStateSource.includes("generationId: runData.generationId || null"), true,
    "persisted runs keep the bridge across reloads");
  assert.equal(playgroundSource.includes("run.generationId || run.historyGenerationId || run.history_generation_id"), true,
    "the preview resolves the bridged id before any scan");
  section("8. generationId rides every run object end to end");
}

console.log("\nAll shared viewer-input contract tests passed.");

// ── 9. Legacy run-id derivation matches production exactly ────────────────
//
// Values pinned against history_v2_writer._gen_id (production's own
// function).  A mismatch here means the preview can never find old runs.
{
  assert.equal(await generationIdForLegacyRunId("r_wf_001"), "gen_c858af8d8d23");
  assert.equal(await generationIdForLegacyRunId("r_0cdd2cb20a01"), "gen_29f81d90d876");
  assert.equal(await generationIdForLegacyRunId("play_abc123"), "gen_f8243727269f");
  assert.equal(await generationIdForLegacyRunId("r_wf_001", "experiment_cell"), null,
    "experiment cells derive differently — never guess");
  assert.equal(await generationIdForLegacyRunId(""), null);
  assert.equal(await generationIdForLegacyRunId(null), null);
  section("9. Legacy run-id derivation matches production exactly");
}
