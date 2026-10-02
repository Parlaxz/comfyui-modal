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
  normalizeExportResponse,
  normalizeHistoryOutput,
} from "../web/history-v2-repository.js";

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
