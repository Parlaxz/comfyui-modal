// E4C Generate Original activation tests.
//
// Covers the frozen E3B2 contract consumption (POST
// /comfymodal/history-v2/generations/{generation_id}/original), the derived
// action states, retry/rerender semantics, reuse/busy/irreproducible
// handling, Experiment cell identity, and the E4B eager-Original
// prohibitions that must survive activation.
//
// No browser, no DOM, no deployment, no live generation.  fetch is stubbed;
// UI behavior is verified through exported pure helpers plus source-level
// guards (the established E4B test style).

import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import {
  createHistoryRepository,
  deriveOriginalActionState,
  generateOriginalEligibility,
  isTerminalAttemptStatus,
  normalizeOriginalGenerationResponse,
  selectDetailAsset,
  selectFeedAsset,
} from "../web/history-v2-repository.js";
import {
  historyAttemptPurposeLabel as generationAttemptPurposeLabel,
  selectGenerationDetailAsset,
} from "../web/studio-history-v2-detail.js";
import {
  historyAttemptPurposeLabel as cellAttemptPurposeLabel,
} from "../web/studio-history-v2-experiment.js";

const ROOT = path.join(import.meta.dirname, "..");
const repoSource = fs.readFileSync(path.join(ROOT, "web", "history-v2-repository.js"), "utf8");
const detailSource = fs.readFileSync(path.join(ROOT, "web", "studio-history-v2-detail.js"), "utf8");
const experimentSource = fs.readFileSync(path.join(ROOT, "web", "studio-history-v2-experiment.js"), "utf8");

function section(name) {
  console.log("PASS: " + name);
}

/** Stub global fetch with {status, body} or {__reject} responses. */
function stubFetch(handler) {
  const calls = [];
  const original = globalThis.fetch;
  globalThis.fetch = function (url, options) {
    const req = {
      url: String(url),
      method: (options && options.method) || "GET",
      body: options && options.body != null ? options.body : null,
    };
    calls.push(req);
    const res = handler(req) || {};
    if (res.__reject) return Promise.reject(res.__reject);
    const status = res.status || 200;
    return Promise.resolve({
      ok: status < 400,
      status: status,
      json: function () { return Promise.resolve(res.body !== undefined ? res.body : {}); },
    });
  };
  return {
    calls: calls,
    restore: function () { globalThis.fetch = original; },
  };
}

function generation(overrides = {}) {
  return Object.assign({
    id: "gen_e4c",
    kind: "generation",
    status: "completed",
    output_count: 1,
    outputs: [{ preview_url: "/preview" }],
    attempts: [{ mode: "preview", status: "completed", run_id: "run_preview" }],
  }, overrides);
}

const ORIGINAL_ROUTE = "/comfymodal/history-v2/generations/gen_e4c/original";

// ── 1-3. The POST contract ───────────────────────────────────────────────

{
  const stub = stubFetch(() => ({
    body: {
      status: "running", generation_id: "gen_e4c", run_id: "run_new",
      purpose: "original", attempt_status: "queued", reused: false,
    },
  }));
  try {
    const repo = await createHistoryRepository({ mode: "v2", apiBase: "/comfymodal" });
    const resp = await repo.generateOriginal("gen_e4c");
    assert.equal(stub.calls.length, 1, "exactly one POST per invocation");
    assert.equal(stub.calls[0].method, "POST");
    assert.equal(stub.calls[0].url, ORIGINAL_ROUTE, "frozen Generation-scoped route");
    assert.deepEqual(JSON.parse(stub.calls[0].body), {}, "no immutable params resent by default");
    assert.equal(resp.accepted, true);
    assert.equal(resp.purpose, "original");
    assert.equal(resp.attemptStatus, "queued");
    assert.equal(resp.generationId, "gen_e4c");
    assert.equal(resp.runId, "run_new");
    assert.equal(resp.reused, false);
    section("1. Preview-only Generate Original sends exactly one POST to the Generation route");
  } finally { stub.restore(); }
}

{
  const stub = stubFetch(() => ({ body: { accepted: true, attempt_status: "queued" } }));
  try {
    const repo = await createHistoryRepository({ mode: "v2", apiBase: "/comfymodal" });
    await repo.generateOriginal("gen_e4c", { rerender: true });
    assert.deepEqual(JSON.parse(stub.calls[0].body), { rerender: true }, "explicit rerender=true forwarded");
    await repo.generateOriginal("gen_e4c", { rerender: false });
    assert.deepEqual(JSON.parse(stub.calls[1].body), { rerender: false });
    section("2. Rerender flag is the only request field the browser adds");
  } finally { stub.restore(); }
}

{
  // The browser never reconstructs workflow/request data: the repository's
  // Generate Original implementation only builds {rerender}.
  const fnStart = repoSource.indexOf("function _v2GenerateOriginal");
  const fnEnd = repoSource.indexOf("}", repoSource.indexOf("encodeURIComponent(id) + \"/original\""));
  const fnSource = repoSource.slice(fnStart, fnEnd);
  assert.ok(fnStart >= 0, "Generate Original repository method exists");
  assert.equal(/prompt|workflow|params|negative/i.test(fnSource), false,
    "no workflow/request reconstruction in the browser");
  section("3. Repository method resends no immutable workflow parameters");
}

// ── 4-7. Derived states retain Preview through queued/running/success ────

{
  const idle = deriveOriginalActionState(generation());
  assert.equal(idle.phase, "idle");
  assert.equal(idle.hasPreview, true);
  const queued = deriveOriginalActionState(generation({
    attempts: [
      { mode: "preview", status: "completed" },
      { mode: "original", status: "queued", run_id: "run_o1" },
    ],
  }));
  assert.equal(queued.phase, "active", "queued Original attempt → active; Preview untouched");
  const running = deriveOriginalActionState(generation({
    attempts: [{ mode: "preview", status: "completed" }, { mode: "original", status: "running" }],
  }));
  assert.equal(running.phase, "active");
  section("4. Queued and running Original attempts keep Preview visible (phase=active)");
}

{
  const success = deriveOriginalActionState(generation({
    original_available: true,
    outputs: [{ preview_url: "/preview", original_url: "/original" }],
    attempts: [
      { mode: "preview", status: "completed" },
      { mode: "original", status: "completed", run_id: "run_o2" },
    ],
  }));
  assert.equal(success.phase, "success");
  assert.equal(success.originalAvailable, true);
  // Success does NOT auto-load Original bytes (E4B rule preserved): a
  // Preview keeps its URL; an Original-only record stays a placeholder.
  assert.equal(selectGenerationDetailAsset(
    { featuredOutput: { previewUrl: "/preview", originalUrl: "/original" } }).url, "/preview");
  const originalOnly = selectGenerationDetailAsset({ featuredOutput: { originalUrl: "/original" } });
  assert.equal(originalOnly.url, "", "Original-only success never eager-loads bytes");
  assert.equal(originalOnly.label, "Original available");
  section("5. Success shows Original available without eager-loading Original bytes");
}

{
  const failed = deriveOriginalActionState(generation({
    attempts: [
      { mode: "preview", status: "completed" },
      { mode: "original", status: "failed", error: "OOM" },
    ],
  }));
  assert.equal(failed.phase, "failed");
  assert.equal(failed.hasPreview, true, "failed Original retains Preview");
  // Retained prior success after a later failed rerender.
  const retained = deriveOriginalActionState(generation({
    original_available: true,
    outputs: [{ preview_url: "/preview", original_url: "/original" }],
    attempts: [
      { mode: "original", status: "completed", run_id: "run_ok" },
      { mode: "original", status: "failed", run_id: "run_retry", error: "GPU lost" },
    ],
  }));
  assert.equal(retained.phase, "success", "failed rerender does not destroy prior Original");
  assert.equal(retained.latestAttempt.status, "failed", "latest failed Attempt stays distinct");
  section("6. Failed Original/re-render retains Preview and prior Original availability");
}

{
  assert.equal(isTerminalAttemptStatus("completed"), true);
  assert.equal(isTerminalAttemptStatus("failed"), true);
  assert.equal(isTerminalAttemptStatus("canceled"), true);
  assert.equal(isTerminalAttemptStatus("interrupted"), true);
  assert.equal(isTerminalAttemptStatus("queued"), false);
  assert.equal(isTerminalAttemptStatus("running"), false);
  section("7. Terminal attempt statuses gate polling");
}

// ── 8-11. Reuse / busy / irreproducible responses ────────────────────────

{
  const activeReuse = normalizeOriginalGenerationResponse({
    status: "running", generation_id: "gen_e4c", run_id: "run_existing",
    purpose: "original", attempt_status: "running", reused: true,
  });
  assert.equal(activeReuse.accepted, true);
  assert.equal(activeReuse.reused, true, "active reuse hydrates the returned run");
  const successReuse = normalizeOriginalGenerationResponse({
    status: "completed", generation_id: "gen_e4c", run_id: "run_existing",
    purpose: "original", attempt_status: "completed", reused: true,
  });
  assert.equal(successReuse.reused, true);
  assert.equal(successReuse.attemptStatus, "completed");
  section("8. Reused responses are surfaced for hydration instead of new optimistic Attempts");
}

{
  const stub = stubFetch(() => ({ status: 409, body: { outcome: "busy", message: "generation busy" } }));
  try {
    const repo = await createHistoryRepository({ mode: "v2", apiBase: "/comfymodal" });
    const resp = await repo.generateOriginal("gen_e4c");
    assert.equal(resp.accepted, false);
    assert.equal(resp.outcome, "busy");
    assert.equal(resp.httpStatus, 409);
    section("9. Busy refusal is machine-readable and non-destructive");
  } finally { stub.restore(); }
}

{
  const stub = stubFetch(() => ({ status: 409, body: { outcome: "irreproducible" } }));
  try {
    const repo = await createHistoryRepository({ mode: "v2", apiBase: "/comfymodal" });
    const resp = await repo.generateOriginal("gen_e4c");
    assert.equal(resp.accepted, false);
    assert.equal(resp.outcome, "irreproducible");
    section("10. Irreproducible refusal is machine-readable");
  } finally { stub.restore(); }
}

{
  const stub = stubFetch(() => ({ status: 500, body: "boom" }));
  try {
    const repo = await createHistoryRepository({ mode: "v2", apiBase: "/comfymodal" });
    await assert.rejects(() => repo.generateOriginal("gen_e4c"),
      /HTTP 500/, "non-machine-readable failures reject truthfully");
    section("11. Opaque HTTP failures still surface truthfully");
  } finally { stub.restore(); }
}

// ── 12-14. Eligibility: legacy/incomplete History stays unavailable ──────

{
  const legacy = generateOriginalEligibility({ id: "gen_x" }, { mode: "bridge" });
  assert.equal(legacy.eligible, false);
  assert.equal(legacy.reason, "legacy");
  assert.match(legacy.message, /immutable execution data/);
  assert.equal(generateOriginalEligibility({ id: "gen_x" }, { mode: "fixture" }).eligible, false);
  const irreproducible = generateOriginalEligibility(
    { id: "gen_x", irreproducible: true }, { mode: "auto" });
  assert.equal(irreproducible.eligible, false);
  assert.equal(generateOriginalEligibility({ id: "gen_x" }, { mode: "auto" }).eligible, true);
  assert.equal(generateOriginalEligibility({}, { mode: "auto" }).eligible, false);
  section("12. Legacy/incomplete History cannot rebuild from current Workflow/Preset");
}

{
  assert.equal(detailSource.includes("_originalUnavailableNote"), true,
    "runtime irreproducible refusal disables the action for the session");
  assert.equal(detailSource.includes("generateOriginalEligibility(record, _repoModeInfo())"), true);
  assert.equal(experimentSource.includes("generateOriginalEligibility({ id: genId }, _repoModeInfo())"), true);
  section("13. Detail and Experiment consume the shared eligibility policy");
}

{
  // Missing Generation identity → no fetch at all.
  const stub = stubFetch(() => ({ body: {} }));
  try {
    const repo = await createHistoryRepository({ mode: "v2", apiBase: "/comfymodal" });
    const resp = await repo.generateOriginalForCell("");
    assert.equal(resp.accepted, false);
    assert.equal(resp.outcome, "unavailable");
    assert.equal(stub.calls.length, 0, "cells without a generation_id never hit the network");
    section("14. Cells without a Generation ID stay inert");
  } finally { stub.restore(); }
}

// ── 15-18. Retry / rerender / duplicate-click guards in the UI sources ───

{
  assert.equal(detailSource.includes('"history-v2-retry-original"'), true);
  // E4D final contract: failed latest Original → the DEDICATED /original/retry
  // route via repo.retryOriginal — never an ordinary /original re-post.
  assert.equal(detailSource.includes("function _runRetryOriginal()"), true,
    "explicit Retry action exists");
  assert.equal(detailSource.includes("repo.retryOriginal(generationId)"), true,
    "Retry calls the dedicated retry repository method");
  // Exactly ONE ordinary-generate call site remains: the idle Generate
  // Original action (Preview/no Original → POST /original).  The failed
  // phase must dispatch the dedicated retry action instead.
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
  assert.equal(detailSource.includes('"history-v2-generate-again"'), true);
  assert.equal(detailSource.includes("_runGenerateOriginal(true)"), true,
    "Generate Again is the explicit rerender=true action");
  assert.equal(detailSource.includes("let _originalInFlight = false;"), true);
  assert.equal(detailSource.includes("if (_originalInFlight || _closed) return;"), true,
    "duplicate clicks are guarded");
  assert.equal(detailSource.includes('text: "Generating Original\\u2026"'), true);
  assert.equal(detailSource.includes("disabled: true,\n        title: \"Generation busy"), true,
    "busy generation disables the action non-destructively");
  section("15. Detail Retry/Rerender/duplicate/busy controls");
}

{
  // Polling reuses getGeneration + full detail re-render; never a loading
  // screen, never a separate transport.
  assert.equal(detailSource.includes("repo.getGeneration(generationId)"), true);
  assert.equal(detailSource.includes("_startOriginalPolling"), true);
  const pollStart = detailSource.indexOf("function _startOriginalPolling");
  const pollEnd = detailSource.indexOf("async function _postOriginalAction");
  const pollSource = detailSource.slice(pollStart, pollEnd);
  assert.equal(/WebSocket|EventSource/.test(pollSource), false, "no separate websocket/SSE system");
  assert.equal(pollSource.includes("_renderDetail(fresh)"), true,
    "poll ticks re-render durable state (Preview retained)");
  assert.equal(pollSource.includes("_renderLoading"), false);
  section("16. Polling refreshes Generation detail until terminal without blanking Preview");
}

{
  assert.equal(experimentSource.includes("repo.generateOriginalForCell(genId"), true,
    "cell action passes the cell's generation_id (never the cell index)");
  assert.equal(experimentSource.split("repo.generateOriginalForCell(").length - 1, 1,
    "single call site — no browser fanout");
  assert.equal(experimentSource.includes("_cellGenerationId(cell)"), true);
  assert.equal(experimentSource.includes('"history-v2-cell-generate-original"'), true);
  assert.equal(experimentSource.includes("_startCellOriginalPolling"), true);
  assert.equal(experimentSource.includes("_rerenderPage(fresh)"), true,
    "experiment poll refreshes the page in place");
  section("17. Experiment cell action uses Generation identity with one call site");
}

{
  // Cell normalization preserves the cell's own Generation identity.
  const stub = stubFetch(() => ({
    body: {
      item: {
        experiment_id: "exp_e4c", status: "completed",
        cells: [{
          cell_id: "c0", status: "completed", generation_id: "gen_cell_0",
          outputs: [{ preview_url: "/cell-preview" }],
          attempts: [{ mode: "preview", status: "completed" }],
        }],
      },
    },
  }));
  try {
    const repo = await createHistoryRepository({ mode: "v2", apiBase: "/comfymodal" });
    const exp = await repo.getExperiment("exp_e4c");
    assert.equal(exp.cells[0].generationId, "gen_cell_0",
      "cell carries its existing generation_id for the Original action");
    section("18. Experiment cell normalization exposes generation_id");
  } finally { stub.restore(); }
}

// ── 19-21. E4B rules that must survive activation ─────────────────────────

{
  assert.equal(generationAttemptPurposeLabel("original"), "Original");
  assert.equal(generationAttemptPurposeLabel("preview"), "Preview");
  assert.equal(cellAttemptPurposeLabel("original"), "Original");
  assert.equal(detailSource.includes("historyAttemptPurposeLabel(a.mode || a.purpose)"), true);
  assert.equal(detailSource.includes('text: "Original"'), true);
  section("19. Purpose and status labels remain distinct");
}

{
  const remoteOnly = selectFeedAsset({ originalUrl: "/original" });
  assert.equal(remoteOnly.kind, "original");
  assert.equal(remoteOnly.url, "", "remote-only Original stays a placeholder");
  assert.equal(remoteOnly.label, "Original available");
  assert.equal(selectDetailAsset({ originalUrl: "/original" }).url, "");
  assert.equal(detailSource.includes('data-testid": "history-v2-view-original"'), true,
    "View Original remains explicit");
  const clickIndex = detailSource.indexOf('text: "View Original"');
  const srcIndex = detailSource.indexOf("src: feat.originalUrl");
  assert.ok(clickIndex >= 0 && clickIndex < srcIndex, "Original bytes load only on click");
  section("20. E4B remote-only placeholder and click-only Original loading remain correct");
}

{
  // No auto View Original after success: the success-phase note points at the
  // explicit control; nothing assigns originalUrl outside the click handler.
  assert.equal(detailSource.includes("use View Original to display it"), true);
  const assignments = detailSource.split(".src =").length - 1;
  assert.equal(assignments, 0, "no imperative Original src assignment outside el() creation");
  section("21. Generate Original success never triggers an eager Original request");
}
