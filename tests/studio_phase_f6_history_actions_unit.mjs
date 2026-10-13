// Modal Studio — Phase F6 History Frontend Actions Unit Tests
//
// Executable behavioral tests for the F6 lane (Single Resume UI, truthful
// failed-Single Retry naming, replay-capability tolerance):
//   - deriveSingleResumeState eligibility truth table (durable state only,
//     tolerant to the concurrent F5 replay_capable projection)
//   - deriveRetryActionLabel conditional presentation ("Retry run" vs
//     "Retry Original") from durable attempt/asset history
//   - repository Single Resume contract: exact frozen route, bodyless POST,
//     machine-readable refusals, never /original or Experiment /resume
//   - UI wiring pins: one resume call site, verb-matrix separation
//
// No browser, no DOM, plain Node.
//
// Run: node tests/studio_phase_f6_history_actions_unit.mjs

import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import {
  createHistoryRepository,
  deriveSingleResumeState,
  deriveRetryActionLabel,
  normalizeDeleteResponse,
  normalizeExportResponse,
  normalizeFeedItem,
  normalizeHistoryOutput,
  normalizeLocalAssetResponse,
} from "../web/history-v2-repository.js";
import {
  setPendingPlaygroundBase,
  takePendingPlaygroundBase,
} from "../web/studio-playground-state.js";
import {
  viewerDateText,
  viewerFileSizeText,
  viewerFileSizeValue,
  viewerMergedParams,
  viewerResolutionText,
  viewerSnapshotText,
} from "../web/studio-ui.js";

const REPO_SRC = fs.readFileSync(
  path.join(import.meta.dirname, "..", "web", "history-v2-repository.js"),
  "utf8",
);
const DETAIL_SRC = fs.readFileSync(
  path.join(import.meta.dirname, "..", "web", "studio-history-v2-detail.js"),
  "utf8",
);
const EXPERIMENT_SRC = fs.readFileSync(
  path.join(import.meta.dirname, "..", "web", "studio-history-v2-experiment.js"),
  "utf8",
);

function section(name) {
  console.log("PASS: " + name);
}

function generation(overrides = {}) {
  return Object.assign({
    id: "gen_f6",
    kind: "generation",
    status: "interrupted",
    attempts: [{ mode: "preview", status: "interrupted", run_id: "run_a" }],
    featuredOutput: {},
  }, overrides);
}

/** Fetch stub capturing calls; responder returns {status, body}. */
function stubFetch(responder) {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async function (url, options) {
    calls.push({
      url: String(url),
      method: options && options.method ? options.method : "GET",
      body: options && options.body !== undefined ? options.body : null,
    });
    const r = responder(calls[calls.length - 1]);
    return {
      ok: (r.status || 200) >= 200 && (r.status || 200) < 300,
      status: r.status || 200,
      json: async () => r.body,
    };
  };
  return {
    calls,
    restore: function () { globalThis.fetch = original; },
  };
}

// ── 1. Single Resume eligibility truth table ─────────────────────────────

{
  assert.equal(deriveSingleResumeState(generation()).state, "resume",
    "durably interrupted ordinary Single offers Resume");

  for (const status of ["failed", "canceled", "completed", "running", "queued"]) {
    assert.equal(deriveSingleResumeState(generation({ status })).state, "hidden",
      status + " never offers Resume");
  }
  assert.equal(deriveSingleResumeState(null).state, "hidden");
  assert.equal(deriveSingleResumeState({}).state, "hidden", "no identity → hidden");
  assert.equal(deriveSingleResumeState(generation({ kind: "experiment" })).state, "hidden",
    "experiments resume through the Experiment surface");
  assert.equal(deriveSingleResumeState(generation({ experimentId: "exp_1" })).state, "hidden",
    "experiment-cell generations never offer Single Resume");

  // F5-tolerant replay capability: explicit false disables BEFORE click;
  // absent field falls back safely (the bodyless POST stays authoritative).
  assert.equal(deriveSingleResumeState(generation({ replayCapable: false })).state, "unavailable");
  assert.equal(deriveSingleResumeState(generation({ replay_capable: false })).state, "unavailable");
  assert.ok(deriveSingleResumeState(generation({ replayCapable: false })).reason.length > 0,
    "unavailable state carries a truthful reason");
  assert.equal(deriveSingleResumeState(generation({ replayCapable: true })).state, "resume");
  assert.equal(deriveSingleResumeState(generation({ replayCapable: null })).state, "resume",
    "absent projection → backend-safe fallback");
  const absent = generation();
  assert.equal("replayCapable" in absent, false);
  assert.equal(deriveSingleResumeState(absent).state, "resume");

  assert.equal(deriveSingleResumeState(generation({ irreproducible: true })).state, "unavailable",
    "irreproducible snapshots cannot be resumed");
  section("1. Single Resume eligibility truth table (durable state, F5-tolerant)");
}

// ── 2. Truthful Retry label derivation ───────────────────────────────────

{
  // Plain failed ordinary run: initial/current workflow Attempt simply failed.
  assert.equal(deriveRetryActionLabel(generation({
    status: "failed",
    attempts: [{ mode: "original", status: "failed", error: "boom" }],
    featuredOutput: {},
  })), "Retry run");

  // Preview succeeded then Generate Original failed → derivative story.
  assert.equal(deriveRetryActionLabel(generation({
    attempts: [
      { mode: "preview", status: "completed" },
      { mode: "original", status: "failed" },
    ],
  })), "Retry Original");

  // Prior successful Original retained after a later failed rerender.
  assert.equal(deriveRetryActionLabel(generation({
    attempts: [
      { mode: "original", status: "completed" },
      { mode: "original", status: "failed" },
    ],
  })), "Retry Original");

  // Retained usable Original asset makes the distinction meaningful.
  assert.equal(deriveRetryActionLabel(generation({
    attempts: [{ mode: "original", status: "failed" }],
    featuredOutput: { originalUrl: "/comfymodal/history-v2/assets/a" },
  })), "Retry Original");
  assert.equal(deriveRetryActionLabel(generation({
    attempts: [{ mode: "original", status: "failed" }],
    originalAvailable: true,
  })), "Retry Original");
  section("2. Retry label: plain failed run vs explicit Original lifecycle");
}

// ── 3. Repository Single Resume contract (exact frozen route) ────────────

{
  const stub = stubFetch(() => ({
    status: 200,
    body: {
      status: "ok", generation_id: "gen_f6", purpose: "resume",
      decision: "create_resume", reason: "interrupted_single",
      outcome: "resume_created", run_id: "run_r1",
      attempt_status: "queued", reused: false,
      executor: "canonical_execution.execute_plan",
    },
  }));
  try {
    const repo = await createHistoryRepository({ mode: "v2", apiBase: "/comfymodal" });
    const resp = await repo.resumeGeneration("gen_f6");
    assert.equal(stub.calls.length, 1, "exactly one request per explicit Resume");
    assert.equal(stub.calls[0].method, "POST");
    assert.equal(stub.calls[0].url,
      "/comfymodal/history-v2/generations/gen_f6/resume",
      "exact canonical Single Resume route");
    assert.equal(stub.calls[0].url.indexOf("/original"), -1,
      "never the Original route");
    assert.equal(stub.calls[0].url.indexOf("/experiments/"), -1,
      "never the Experiment resume route");
    assert.equal(stub.calls[0].body, null, "bodyless by contract — zero option delta");
    assert.equal(resp.accepted, true);
    assert.equal(resp.purpose, "resume");
    assert.equal(resp.outcome, "resume_created");
    assert.equal(resp.runId, "run_r1");
    assert.equal(resp.attemptStatus, "queued");
  } finally { stub.restore(); }
  section("3. resumeGeneration: exact bodyless POST to the frozen route");
}

// ── 4. Machine-readable Resume refusals normalize truthfully ─────────────

{
  const refusals = [
    [409, { status: "error", code: "generation_busy", message: "an attempt of this generation is already active" }],
    [409, { status: "error", code: "resume_not_available", message: "only an interrupted ordinary Single can be resumed" }],
    [409, { status: "error", code: "generation_not_reproducible", message: "generation snapshot is not reproducible" }],
    [503, { status: "error", code: "dispatch_unavailable", message: "no capable dispatcher is available for this generation" }],
    [404, { status: "error", code: "generation_not_found", message: "generation not found" }],
  ];
  for (const [status, body] of refusals) {
    const stub = stubFetch(() => ({ status, body }));
    try {
      const repo = await createHistoryRepository({ mode: "v2", apiBase: "/comfymodal" });
      const resp = await repo.resumeGeneration("gen_f6");
      assert.equal(resp.accepted, false, body.code + " is a refusal, never a success");
      assert.equal(resp.errorCode, body.code, "structured code preserved for the UI");
      assert.equal(resp.httpStatus, status);
    } finally { stub.restore(); }
  }
  section("4. busy / not-resumable / irreproducible / dispatch / not-found refusals");
}

// ── 5. Repository transport pins (no reconstruction, no fanout) ──────────

{
  const start = REPO_SRC.indexOf("function _v2ResumeGeneration");
  const end = REPO_SRC.indexOf("function _v2RetryOriginal");
  assert.ok(start >= 0 && end > start, "_v2ResumeGeneration exists before the retry fn");
  const fnSrc = REPO_SRC.slice(start, end);
  assert.equal(fnSrc.includes('"/resume"'), true, "frozen resume route string");
  assert.equal(fnSrc.includes("/original"), false, "never touches an Original route");
  assert.equal(fnSrc.split("fetch(").length - 1, 1, "one transport call — no fanout");
  assert.equal(fnSrc.includes("JSON.stringify"), false, "bodyless POST — nothing serialized");
  assert.equal(/rerender|prompt|workflow|params|negative|seed|preset/i.test(fnSrc.includes('"/resume"') ? fnSrc.replace(/\/\/[^\n]*/g, "") : fnSrc), false,
    "no request reconstruction in the resume transport");
  section("5. resume transport: one bodyless fetch, zero reconstruction");
}

// ── 6. UI verb-matrix wiring pins ────────────────────────────────────────

{
  // Exactly ONE Single-Resume call site, on the Generation detail only.
  assert.equal(DETAIL_SRC.split("repo.resumeGeneration(").length - 1, 1,
    "exactly one repo.resumeGeneration call site");
  assert.equal(EXPERIMENT_SRC.includes("repo.resumeGeneration"), false,
    "cells never invoke the Single Resume route");
  assert.equal(DETAIL_SRC.includes('"history-v2-resume-run"'), true,
    "Resume control carries a stable testid");
  assert.equal(DETAIL_SRC.includes("deriveSingleResumeState(record)"), true,
    "Resume visibility derives from durable state");
  assert.equal(DETAIL_SRC.includes("_startOriginalPolling()"), true,
    "accepted Resume drives durable refetch/poll (no optimistic Attempt)");

  // No local interrupted → running flip anywhere in the frontend lane.
  assert.equal(/\.status\s*=\s*["']running["']/.test(DETAIL_SRC), false,
    "detail never fabricates a running state locally");
  assert.equal(/\.status\s*=\s*["']running["']/.test(EXPERIMENT_SRC), false,
    "experiment page never fabricates a running state locally");

  // Failed branch keeps the dedicated retry dispatch (label may vary).
  const retryIdx = DETAIL_SRC.lastIndexOf('"history-v2-retry-original"');
  const failedBranch = DETAIL_SRC.slice(retryIdx, retryIdx + 600);
  assert.equal(failedBranch.includes("_runRetryOriginal()"), true,
    "failed phase still dispatches the dedicated retry action");
  assert.equal(failedBranch.includes("deriveRetryActionLabel(record)") === false, true);
  assert.equal(DETAIL_SRC.includes("deriveRetryActionLabel(record)"), true,
    "retry label derives from durable record state");
  assert.equal(DETAIL_SRC.includes('"Retry run"') || DETAIL_SRC.includes("Retry run"), true,
    "plain-failed wording present via the shared derivation");
  assert.equal(EXPERIMENT_SRC.includes("deriveRetryActionLabel(cell)"), true,
    "cell menu/pane shares the truthful retry label");
  section("6. Verb-matrix wiring: Resume / Retry run / Retry Original separated");
}

// ── 7. F10 configured-Export repository contract (frozen F9 route) ───────

{
  const stub = stubFetch(() => ({
    status: 200,
    body: {
      status: "ok", asset_id: "a1", export_state: "exported",
      saved: true, already_exported: false,
      destination_path: "/out/images/a1.png", metadata_path: null,
      byte_count: 64, file_ext: "png", mime_type: "image/png",
      exported_at: "2026-08-23T00:00:00Z",
    },
  }));
  try {
    const repo = await createHistoryRepository({ mode: "v2", apiBase: "/comfymodal" });
    const resp = await repo.exportAsset("a1");
    assert.equal(stub.calls.length, 1, "exactly one request per explicit Export");
    assert.equal(stub.calls[0].method, "POST");
    assert.equal(stub.calls[0].url, "/comfymodal/history-v2/assets/a1/export",
      "exact frozen F9 asset-scoped export route");
    assert.equal(stub.calls[0].body, null, "BODYLESS by contract — no generation/output/variant/Settings/filename");
    assert.ok(!stub.calls[0].url.includes("/run-history/"), "never the legacy Save route");
    assert.equal(resp.ok, true);
    assert.equal(resp.saved, true);
    assert.equal(resp.alreadyExported, false);
    assert.equal(resp.exportState, "exported");
    assert.equal(resp.destinationPath, "/out/images/a1.png");
    assert.equal(resp.byteCount, 64);
    assert.equal(resp.assetId, "a1");
  } finally { stub.restore(); }

  // already_exported is an idempotent SUCCESS, never an error.
  {
    const stub2 = stubFetch(() => ({
      status: 200,
      body: { status: "ok", asset_id: "a1", export_state: "exported", saved: false, already_exported: true },
    }));
    try {
      const repo = await createHistoryRepository({ mode: "v2", apiBase: "/comfymodal" });
      const resp = await repo.exportAsset("a1");
      assert.equal(resp.ok, true, "already_exported must not be treated as a failure");
      assert.equal(resp.alreadyExported, true);
      assert.equal(resp.saved, false);
    } finally { stub2.restore(); }
  }

  // Structured error envelopes normalize without discarding machine fields.
  for (const [status, body] of [
    [500, { status: "error", asset_id: "a1", reason: "source_unreadable", message: "remote source unavailable", export_state: "failed", partial: false }],
    [500, { status: "error", asset_id: "a1", reason: "record_persist_failed", message: "copy written but not recorded", export_state: "failed", partial: true }],
    [404, { status: "error", asset_id: "a1", reason: "asset_not_found", message: "asset not found", export_state: "not_exported", partial: false }],
  ]) {
    const stub3 = stubFetch(() => ({ status, body }));
    try {
      const repo = await createHistoryRepository({ mode: "v2", apiBase: "/comfymodal" });
      const resp = await repo.exportAsset("a1");
      assert.equal(resp.ok, false, "structured failures resolve ok:false (never throw)");
      assert.equal(resp.reason, body.reason, "machine reason preserved");
      assert.equal(resp.message, body.message, "backend message preserved");
      assert.equal(resp.partial, body.partial, "partial flag preserved");
      assert.equal(resp.exportState, body.export_state);
      assert.equal(resp.httpStatus, status);
    } finally { stub3.restore(); }
  }

  // Network failure resolves a truthful envelope — no unhandled rejection.
  {
    const original = globalThis.fetch;
    globalThis.fetch = async function () { throw new TypeError("fetch failed"); };
    try {
      const repo = await createHistoryRepository({ mode: "v2", apiBase: "/comfymodal" });
      const resp = await repo.exportAsset("a1");
      assert.equal(resp.ok, false);
      assert.equal(resp.reason, "network_error");
    } finally { globalThis.fetch = original; }
  }

  // No Asset identity → inert envelope, zero fetches.
  {
    const stub4 = stubFetch(() => ({ status: 200, body: { status: "ok" } }));
    try {
      const repo = await createHistoryRepository({ mode: "v2", apiBase: "/comfymodal" });
      const resp = await repo.exportAsset("");
      assert.equal(resp.ok, false);
      assert.equal(stub4.calls.length, 0, "absent variant never fetches");
    } finally { stub4.restore(); }
  }
  section("7. exportAsset: exact bodyless POST to /history-v2/assets/{id}/export, tolerant normalization");
}

// ── 8. F10 per-variant projection normalization ──────────────────────────

{
  const out = normalizeHistoryOutput({
    preview_asset_id: "p1", original_asset_id: "o1",
    preview_export_state: "exported", original_export_state: "missing",
    preview_url: "/comfymodal/history-v2/assets/p1",
  });
  assert.equal(out.previewAssetId, "p1");
  assert.equal(out.previewExportState, "exported");
  assert.equal(out.originalAssetId, "o1");
  assert.equal(out.originalExportState, "missing");

  // Absent fields → null (older payloads show NO Export action, not a guess).
  const bare = normalizeHistoryOutput({});
  assert.equal(bare.previewAssetId, "");
  assert.equal(bare.previewExportState, null);
  assert.equal(bare.originalAssetId, "");
  assert.equal(bare.originalExportState, null);

  // Unknown states normalize to null; canonical vocabulary accepted verbatim.
  assert.equal(normalizeHistoryOutput({ preview_export_state: "weird" }).previewExportState, null);
  assert.equal(normalizeHistoryOutput({ original_export_state: "NOT_EXPORTED" }).originalExportState, "not_exported");
  assert.equal(normalizeHistoryOutput({ original_export_state: "failed" }).originalExportState, "failed");

  // The backend projection is authoritative: no Asset ID is ever parsed from
  // URL text when the server provided none.
  const urlOnly = normalizeHistoryOutput({
    preview_url: "/comfymodal/history-v2/assets/sneaky_id",
    original_url: "/comfymodal/history-v2/assets/sneaky_orig",
  });
  assert.equal(urlOnly.previewAssetId, "");
  assert.equal(urlOnly.originalAssetId, "");

  // Frozen error-envelope normalization pins.
  const env = normalizeExportResponse(
    { status: "error", reason: "write_failed", message: "disk full", export_state: "failed", partial: true },
    { httpStatus: 500 },
  );
  assert.equal(env.ok, false);
  assert.equal(env.partial, true);
  assert.equal(env.reason, "write_failed");
  section("8. Per-variant Export projection: authoritative IDs/states, null when absent");
}

// ── 8b. Viewer-content projection: resolution + file size + workflow ──────
//
// A snapshot-less generation (no params, no workflow_name, no models) must
// still resolve resolution from asset-measured output dims, file size from
// the projected byte size, and workflow from the workflow_id fallback —
// and omit each row (never fabricate) when its source is absent.
{
  const dimOut = normalizeHistoryOutput({ preview_url: "/p", width: 1024, height: 768, byte_size: 1234 });
  assert.equal(dimOut.width, 1024);
  assert.equal(dimOut.height, 768);
  assert.equal(dimOut.byteSize, 1234);

  const bareOut = normalizeHistoryOutput({ preview_url: "/p" });
  assert.equal(bareOut.width, null);
  assert.equal(bareOut.height, null);
  assert.equal(bareOut.byteSize, null);

  // Resolution: params win, asset dims fill a snapshot-less record.
  assert.equal(viewerResolutionText({ width: 512, height: 512 }, {}), "512 \u00d7 512");
  const snapshotLess = normalizeFeedItem({
    id: "gen_nosnap", status: "completed",
    outputs: [{ preview_url: "/p", width: 1024, height: 768, byte_size: 1234 }],
    featured_output_index: 0,
  });
  assert.deepEqual(snapshotLess.params, {});
  assert.equal(viewerResolutionText(snapshotLess.params, snapshotLess), "1024 \u00d7 768");
  assert.equal(viewerFileSizeText(viewerFileSizeValue(snapshotLess)), "1.2 KB");
  assert.equal(viewerResolutionText({}, {}), "");
  assert.equal(viewerFileSizeValue({}), "");

  // Workflow falls back to the backend-sent workflow_id when no name exists.
  const idOnly = normalizeFeedItem({ id: "gen_wf", status: "completed", workflow_id: "wf_abc" });
  assert.equal(idOnly.workflow, "wf_abc");
  section("8b. Snapshot-less viewer content: asset resolution, file size, workflow_id fallback");
}

// ── 8c. Variant row + human dates ─────────────────────────────────────────
//
// The viewer answers "is this a preview?" with an always-visible Variant
// row (Preview/Original/Thumbnail label from the shared asset policy),
// and Started/Completed render as human dates, never raw ISO strings.
{
  const formatted = viewerDateText("2026-10-12T03:03:30Z");
  assert.match(formatted, /Oct/, "human month, not ISO");
  assert.doesNotMatch(formatted, /T\d\d:/, "no raw ISO timestamp");
  assert.equal(viewerDateText(""), "");

  const UI_SRC = fs.readFileSync(
    path.join(import.meta.dirname, "..", "web", "studio-ui.js"),
    "utf8",
  );
  const PLAYGROUND_SRC = fs.readFileSync(
    path.join(import.meta.dirname, "..", "web", "studio-playground.js"),
    "utf8",
  );
  assert.ok(UI_SRC.includes('["Variant", viewerFirst(opts.variant, "")]'),
    "shared overlay renders the Variant row from opts.variant");
  assert.ok(UI_SRC.includes('["Started", viewerDateText(record.startedAt)]'),
    "Started renders through viewerDateText (with seconds)");
  assert.ok(!UI_SRC.includes('["Completed"'),
    "Completed row removed (Started + Run duration pin the run)");
  assert.ok(UI_SRC.includes("variant: opts.variant"),
    "shell forwards variant to the shared overlay");
  assert.ok(DETAIL_SRC.includes("resolveViewerShellArgs(viewer, shellAdapters)"),
    "History detail variants flow through the shared builder");
  assert.ok(PLAYGROUND_SRC.includes("resolveViewerShellArgs(_viewer,"),
    "Playground variants flow through the shared builder");
  section("8c. Variant row threaded on both surfaces; Started human-formatted with seconds");
}

// ── 8d. Embedded-file recovery + file/advanced/note/styling ───────────────
//
// Detail outputs carry embedded_params/embedded_models recovered from the
// file's own prompt JSON: the params grid merges them at lowest priority
// (snapshot/controls always win), and empty model lists backfill from them.
// The File row (name + Open/Copy), Advanced accordion, separate Note
// accordion, and flat note editor are pinned by source (they need DOM);
// colors/prompt size likewise.
{
  const embOut = normalizeHistoryOutput({
    preview_url: "/p", filename: "gen.png", format: "png", path: "/data/gen.png",
    embedded_params: { seed: 23, steps: 25, sampler: "euler" },
    embedded_models: ["u.safetensors"],
  });
  assert.equal(embOut.filename, "gen.png");
  assert.equal(embOut.format, "png");
  assert.equal(embOut.path, "/data/gen.png");
  assert.deepEqual(embOut.embeddedParams, { seed: 23, steps: 25, sampler: "euler" });
  assert.deepEqual(embOut.embeddedModels, ["u.safetensors"]);

  // Embedded fills a snapshot-less grid…
  const thin = normalizeFeedItem({
    id: "gen_thin", status: "completed",
    outputs: [{
      preview_url: "/p", width: 768, height: 1376,
      embedded_params: { seed: 23, steps: 25, cfg: 1, sampler: "euler", scheduler: "simple", denoise: 1 },
      embedded_models: ["u.safetensors"],
    }],
    featured_output_index: 0,
  });
  const grid = viewerMergedParams(thin);
  assert.equal(grid.seed, 23);
  assert.equal(grid.steps, 25);
  assert.equal(grid.sampler, "euler");
  assert.deepEqual(thin.models, ["u.safetensors"]);
  assert.equal(viewerResolutionText(grid, thin), "768 \u00d7 1376");

  // …but never overrides snapshot/controls.
  const rich = normalizeFeedItem({
    id: "gen_rich", status: "completed",
    params: { seed: 99 },
    outputs: [{ preview_url: "/p", embedded_params: { seed: 23, steps: 25 } }],
    featured_output_index: 0,
  });
  assert.equal(viewerMergedParams(rich).seed, 99);
  assert.equal(viewerMergedParams(rich).steps, 25);

  // Snapshot lineage text states.
  assert.equal(viewerSnapshotText({ replayCapable: true }), "saved");
  assert.equal(viewerSnapshotText({ replayCapable: false, replayReason: "missing_request_snapshot" }),
    "not saved for this run");
  assert.equal(viewerSnapshotText({}), "");

  const UI_SRC = fs.readFileSync(
    path.join(import.meta.dirname, "..", "web", "studio-ui.js"),
    "utf8",
  );
  const STYLES_SRC = fs.readFileSync(
    path.join(import.meta.dirname, "..", "web", "studio-styles.js"),
    "utf8",
  );
  assert.ok(UI_SRC.includes("buildViewerFileRow(record, opts.fileActions)"),
    "File row mounted in the shared overlay");
  assert.ok(UI_SRC.includes('actionButton("viewer-file-open"'),
    "Open-file action rendered");
  assert.ok(UI_SRC.includes('actionButton("viewer-file-copy-path"'),
    "Copy-path action rendered");
  assert.ok(UI_SRC.includes("buildViewerAdvancedRows(record)"),
    "Advanced rows mounted in their own accordion");
  assert.ok(UI_SRC.includes('buildViewerAccordion("Advanced"'),
    "Advanced accordion exists");
  assert.ok(UI_SRC.includes('buildViewerAccordion("Note"'),
    "Note lives in its own accordion, not nested in Metadata");
  assert.ok(UI_SRC.includes("Request snapshot"),
    "snapshot state surfaced as lineage");
  assert.ok(!UI_SRC.includes('["Completed"'),
    "Completed row removed from Metadata");
  assert.ok(UI_SRC.includes('|| "Not recorded"'),
    "Workflow always renders, honestly marked when absent");
  assert.ok(UI_SRC.includes('data-testid": "viewer-prompt-copy'),
    "Copy prompt button rendered");
  assert.ok(UI_SRC.includes('data-testid": "viewer-use-as-base'),
    "Use-parameters-as-base button rendered");
  assert.ok(UI_SRC.includes('class: "comfymodal-studio-viewer-note-flat"'),
    "note editor is flat, not a nested card");
  assert.ok(STYLES_SRC.includes("background: #141414;"),
    "viewer content background");
  assert.ok(STYLES_SRC.includes("background: #191919;"),
    "viewer card background");
  assert.ok(STYLES_SRC.includes("background: transparent;"),
    "viewer stage transparent");
  assert.ok(STYLES_SRC.includes("font-size: 12px;"),
    "prompt text smaller");
  assert.ok(STYLES_SRC.includes("minmax(110px, 1fr)"),
    "params grid breathes");
  assert.ok(STYLES_SRC.includes("border-bottom: 1px solid #1e1e1e;"),
    "metadata spec-sheet separators");
  assert.ok(STYLES_SRC.includes("min-width: 112px;"),
    "metadata key column aligns");
  assert.ok(STYLES_SRC.includes(".comfymodal-studio-viewer-accordion-body[hidden]"),
    "collapsed accordion bodies stay hidden (flex must not beat [hidden])");
  section("8d. Embedded recovery merges lowest-priority; file/advanced/note/styling pinned");
}

// ── 8e. Native open / reveal asset actions ───────────────────────────────
//
// One bodyless POST each; empty ids never fetch; every outcome resolves a
// normalized envelope. The File row renders Open file / Open folder buttons
// only when an asset id and a fileActions adapter are present.
{
  const okRes = normalizeLocalAssetResponse(
    { status: "ok", asset_id: "ast_1", action: "open", path: "C:\\img.png" }, {});
  assert.equal(okRes.ok, true);
  assert.equal(okRes.action, "open");
  assert.equal(okRes.path, "C:\\img.png");
  const errRes = normalizeLocalAssetResponse(
    { status: "error", reason: "remote_asset", message: "remote" }, {});
  assert.equal(errRes.ok, false);
  assert.equal(errRes.reason, "remote_asset");

  const stub = stubFetch((call) => ({
    status: 200,
    body: {
      status: "ok",
      action: call.url.endsWith("/reveal") ? "reveal" : "open",
    },
  }));
  try {
    const repo = await createHistoryRepository({ mode: "v2", apiBase: "/comfymodal" });
    const opened = await repo.openAsset("ast_1");
    assert.equal(opened.ok, true);
    assert.equal(stub.calls.length, 1);
    assert.equal(stub.calls[0].url, "/comfymodal/history-v2/assets/ast_1/open");
    assert.equal(stub.calls[0].method, "POST");
    assert.equal(stub.calls[0].body, null, "BODYLESS by contract — no path from the client");
    const revealed = await repo.revealAsset("ast_1");
    assert.equal(stub.calls[1].url, "/comfymodal/history-v2/assets/ast_1/reveal");
    assert.equal(revealed.action, "reveal");
    const empty = await repo.openAsset("");
    assert.equal(empty.ok, false);
    assert.equal(stub.calls.length, 2, "empty asset id never fetches");
  } finally { stub.restore(); }

  const withId = normalizeHistoryOutput({ preview_url: "/p", asset_id: "ast_9" });
  assert.equal(withId.assetId, "ast_9");

  const UI_SRC = fs.readFileSync(
    path.join(import.meta.dirname, "..", "web", "studio-ui.js"),
    "utf8",
  );
  const DETAIL_SRC = fs.readFileSync(
    path.join(import.meta.dirname, "..", "web", "studio-history-v2-detail.js"),
    "utf8",
  );
  assert.ok(UI_SRC.includes('actionButton("viewer-file-reveal"'),
    "Open-folder action rendered");
  assert.ok(UI_SRC.includes("fileActions: extra.fileActions != null ? extra.fileActions : opts.fileActions"),
    "shell forwards fileActions on re-render");
  assert.ok(DETAIL_SRC.includes("revealAsset: function (assetId) { return repo.revealAsset(assetId); }"),
    "History detail wires reveal through the repository");
  section("8e. Native open/reveal: bodyless POSTs, normalized envelopes, wired File actions");
}

// ── 8f. Viewer Delete button ─────────────────────────────────────────────
//
// One bodyless DELETE per generation; empty ids never fetch; every outcome
// resolves a normalized envelope. The Run-line button is two-step
// (Delete → Confirm delete + Cancel), renders only with a deleteGeneration
// adapter and a record identity, and dismisses through the shell's own
// close after notifying onChanged.
{
  const okRes = normalizeDeleteResponse(
    { status: "ok", deleted: "gen_1" }, { generationId: "gen_1" });
  assert.equal(okRes.ok, true);
  assert.equal(okRes.deleted, true);
  assert.equal(okRes.generationId, "gen_1");
  const errRes = normalizeDeleteResponse(
    { status: "error", message: "generation not found" }, { httpStatus: 404 });
  assert.equal(errRes.ok, false);
  assert.equal(errRes.httpStatus, 404);

  const stub = stubFetch((call) => ({
    status: 200,
    body: { status: "ok", deleted: "gen_1" },
  }));
  try {
    const repo = await createHistoryRepository({ mode: "v2", apiBase: "/comfymodal" });
    const deleted = await repo.deleteGeneration("gen_1");
    assert.equal(deleted.ok, true);
    assert.equal(deleted.deleted, true);
    assert.equal(stub.calls.length, 1);
    assert.equal(stub.calls[0].url, "/comfymodal/history-v2/generations/gen_1");
    assert.equal(stub.calls[0].method, "DELETE");
    assert.equal(stub.calls[0].body, null, "BODYLESS by contract");
    const empty = await repo.deleteGeneration("");
    assert.equal(empty.ok, false);
    assert.equal(stub.calls.length, 1, "empty generation id never fetches");
  } finally { stub.restore(); }

  const UI_SRC = fs.readFileSync(
    path.join(import.meta.dirname, "..", "web", "studio-ui.js"),
    "utf8",
  );
  assert.ok(UI_SRC.includes("buildViewerDeleteButton(record, persistence,"),
    "Run line mounts the shared delete button");
  assert.ok(UI_SRC.includes('data-testid": "viewer-delete-confirm'),
    "two-step confirm rendered");
  assert.ok(UI_SRC.includes('data-testid": "viewer-delete-cancel'),
    "cancel rendered");
  assert.ok(UI_SRC.includes("onClose: close,"),
    "overlay dismisses through the shell's own close");
  section("8f. Viewer Delete: bodyless DELETE, normalized envelope, two-step button");
}

// ── 8g. "Use parameters as base" handoff ───────────────────────────────────
//
// The viewer button carries a shelf-keyed payload; the Playground applies it
// to its own shelf through the validated path, while History stashes the
// one-shot payload and navigates. The pending slot is exactly-once and
// in-memory (never resurrects after reload).
{
  // Pending slot: set → take once → gone; non-objects rejected.
  assert.equal(takePendingPlaygroundBase(), null);
  setPendingPlaygroundBase({ prompt: "fox", seed: 7 });
  setPendingPlaygroundBase(null);
  assert.equal(takePendingPlaygroundBase(), null, "null clears without applying");
  const payload = { prompt: "fox", seed: 7 };
  setPendingPlaygroundBase(payload);
  assert.equal(takePendingPlaygroundBase(), payload);
  assert.equal(takePendingPlaygroundBase(), null, "exactly once");
  setPendingPlaygroundBase("nope");
  assert.equal(takePendingPlaygroundBase(), null);

  const PLAYGROUND_SRC = fs.readFileSync(
    path.join(import.meta.dirname, "..", "web", "studio-playground.js"),
    "utf8",
  );
  const HISTORY_SRC = fs.readFileSync(
    path.join(import.meta.dirname, "..", "web", "studio-history-v2.js"),
    "utf8",
  );
  const DETAIL_SRC = fs.readFileSync(
    path.join(import.meta.dirname, "..", "web", "studio-history-v2-detail.js"),
    "utf8",
  );
  assert.ok(PLAYGROUND_SRC.includes("takePendingPlaygroundBase"),
    "shelf build consumes the pending base");
  assert.ok(PLAYGROUND_SRC.includes("_applyShelfBaseValues(state, payload"),
    "base applies through the validated shelf path");
  assert.ok(PLAYGROUND_SRC.includes("onUseAsBase: function (payload)"),
    "Playground preview applies to its own shelf");
  assert.ok(DETAIL_SRC.includes("onUseAsBase"),
    "History detail forwards the base callback");
  assert.ok(HISTORY_SRC.includes("setPendingPlaygroundBase(payload)"),
    "History stashes the payload for the shelf");
  assert.ok(HISTORY_SRC.includes('context.setPage("playground")'),
    "History navigates to the Playground after stashing");
  section("8g. Use-as-base: validated shelf apply on Playground, stash-and-navigate on History");
}

// ── 9. F10 UI wiring pins (Export ≠ Browser Download) ────────────────────

{
  const EXPORT_SRC = fs.readFileSync(
    path.join(import.meta.dirname, "..", "web", "history-v2-export.js"),
    "utf8",
  );
  const DOWNLOAD_HELPER_SRC = fs.readFileSync(
    path.join(import.meta.dirname, "..", "web", "history-v2-browser-download.js"),
    "utf8",
  );

  // Distinct action families with distinct testids in the detail overlay.
  assert.equal(DETAIL_SRC.includes('"history-v2-download-preview"'), true, "Browser Download Preview kept");
  assert.equal(DETAIL_SRC.includes('"history-v2-download-original"'), true, "Browser Download Original kept");
  assert.equal(DETAIL_SRC.includes('"history-v2-export-preview"'), true, "configured Export Preview added");
  assert.equal(DETAIL_SRC.includes('"history-v2-export-original"'), true, "configured Export Original added");
  assert.equal(DETAIL_SRC.includes('"history-v2-output-export-preview-"'), true, "per-output Export Preview menu items");
  assert.equal(DETAIL_SRC.includes('"history-v2-output-export-original-"'), true, "per-output Export Original menu items");
  assert.equal(DETAIL_SRC.includes('"history-v2-view-original"'), true, "View Original untouched");

  // The Export runner posts through the repository exactly once and refreshes
  // durably instead of mutating local state.
  assert.equal(DETAIL_SRC.split("repo.exportAsset(").length - 1, 1, "exactly one repo.exportAsset call site");
  assert.equal(DETAIL_SRC.includes("_runExport(feat.previewAssetId)"), true);
  assert.equal(DETAIL_SRC.includes("_runExport(feat.originalAssetId)"), true);
  assert.equal(/await reload\(\);/.test(DETAIL_SRC), true, "durable refetch after Export response");

  // Experiment cell parity via its own projected Asset IDs.
  assert.equal(EXPERIMENT_SRC.includes('"history-v2-cell-export-preview-"'), true);
  assert.equal(EXPERIMENT_SRC.includes('"history-v2-cell-export-original-"'), true);
  assert.equal(EXPERIMENT_SRC.split("repo.exportAsset(").length - 1, 1, "exactly one cell export call site");

  // Structural distinction: the Export helper never performs a browser blob
  // download; the Download helper never fires an export POST.
  assert.equal(EXPORT_SRC.includes("createObjectURL"), false, "Export never creates blob URLs");
  assert.equal(EXPORT_SRC.includes("a.download"), false, "Export never triggers anchor downloads");
  assert.equal(EXPORT_SRC.includes('method: "POST"') || EXPORT_SRC.includes("method:\"POST\""), false,
    "helper performs no transport itself — the repository owns the single POST");
  assert.equal(DOWNLOAD_HELPER_SRC.includes('"POST"'), false, "Download helper performs GETs only — never an export POST");
  assert.equal(DOWNLOAD_HELPER_SRC.includes("repo."), false, "Download helper never calls the repository");
  section("9. Export vs Download wiring: distinct controls, one POST per click, durable refresh");
}

console.log("PASS: studio phase f6 history actions unit tests");
