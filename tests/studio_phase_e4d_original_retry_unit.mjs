// E4D Original Retry wiring tests.
//
// Covers the final E3B2 retry contract consumption: a failed latest Original
// derives the explicit Retry Original action, which POSTs the DEDICATED
// /comfymodal/history-v2/generations/{generation_id}/original/retry route
// (bodyless) — never an ordinary /original re-post.  retry_required returned
// by ordinary /original is a machine-readable state transition that never
// auto-retries and never loops.  Generate Again stays /original +
// rerender:true; Experiment cells retry through their own generation_id on
// the same route; duplicate-click guards, durable-state polling, Preview
// retention, and the E4B eager-Original prohibitions all survive.
//
// No browser, no DOM, no deployment, no live generation.  fetch is stubbed;
// UI behavior is verified through exported pure helpers plus source-level
// guards (the established E4B/E4C test style).

import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import {
  createHistoryRepository,
  deriveOriginalActionState,
  generateOriginalEligibility,
  normalizeOriginalGenerationResponse,
  selectDetailAsset,
} from "../web/history-v2-repository.js";
import {
  selectGenerationDetailAsset,
} from "../web/studio-history-v2-detail.js";

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
    id: "gen_e4d",
    kind: "generation",
    status: "completed",
    output_count: 1,
    outputs: [{ preview_url: "/preview" }],
    attempts: [{ mode: "preview", status: "completed", run_id: "run_preview" }],
  }, overrides);
}

const RETRY_ROUTE = "/comfymodal/history-v2/generations/gen_e4d/original/retry";

// ── 1. Failed latest Original derives Retry Original ─────────────────────

{
  const failed = deriveOriginalActionState(generation({
    attempts: [
      { mode: "preview", status: "completed" },
      { mode: "original", status: "failed", run_id: "run_o1", error: "OOM" },
    ],
  }));
  assert.equal(failed.phase, "failed", "failed latest Original → Retry phase");
  assert.equal(failed.hasPreview, true, "failed Original retains Preview");
  assert.equal(failed.latestAttempt.status, "failed");
  assert.equal(failed.latestAttempt.error, "OOM", "failed Attempt stays visible with its error");
  assert.equal(detailSource.includes('"history-v2-retry-original"'), true,
    "Retry Original control exists on Generation detail");
  assert.equal(experimentSource.includes('"Retry Original"'), true,
    "Retry Original control exists for Experiment cells");
  section("1. Failed latest Original derives the explicit Retry Original action");
}

// ── 2. Explicit Retry performs exactly one POST to /original/retry ───────

{
  const stub = stubFetch(() => ({
    body: {
      status: "ok", outcome: "original_created", generation_id: "gen_e4d",
      run_id: "run_retry_1", purpose: "original", attempt_status: "queued", reused: false,
    },
  }));
  try {
    const repo = await createHistoryRepository({ mode: "v2", apiBase: "/comfymodal" });
    const resp = await repo.retryOriginal("gen_e4d");
    assert.equal(stub.calls.length, 1, "exactly one request per explicit Retry");
    assert.equal(stub.calls[0].method, "POST");
    assert.equal(stub.calls[0].url.endsWith("/original/retry"), true,
      "dedicated failed-Attempt retry route");
    assert.equal(stub.calls[0].url, RETRY_ROUTE);
    assert.equal(stub.calls.filter((c) => c.url.endsWith("/original")).length, 0,
      "ordinary /original is NOT called for explicit Retry");
    assert.equal(stub.calls[0].body, null,
      "retry sends NO body — no rerender flag, no request reconstruction");
    assert.equal(resp.accepted, true);
    assert.equal(resp.generationId, "gen_e4d", "same Generation identity round-trips");
    assert.equal(resp.runId, "run_retry_1");
    assert.equal(resp.purpose, "original");
    assert.equal(resp.attemptStatus, "queued");
    assert.equal(resp.reused, false);
    assert.equal(resp.outcome, "original_created");
    section("2. Retry Original calls /original/retry exactly once (never ordinary /original)");
  } finally { stub.restore(); }
}

// ── 3. The retry repository method reconstructs nothing ──────────────────

{
  const fnStart = repoSource.indexOf("function _v2RetryOriginal");
  assert.ok(fnStart >= 0, "retry repository method exists");
  // H20 Wave G: bound the slice to the end of the retry function itself.
  // Slicing to EOF broke when the F3 asset-export helper was added after it
  // in history-v2-repository.js (its fetch is unrelated to Retry).
  const nextFn = repoSource.indexOf("\nfunction ", fnStart + 1);
  const fnSource = repoSource.slice(fnStart, nextFn === -1 ? undefined : nextFn);
  assert.equal(/rerender|prompt|workflow|params|negative|seed|preset/i.test(fnSource), false,
    "no workflow/request reconstruction and no rerender flag in the retry method");
  assert.equal(fnSource.includes('"/original/retry"'), true);
  assert.equal(fnSource.split("fetch(").length - 1, 1,
    "one transport call — no fanout, no second Generation");
  assert.equal(fnSource.includes("JSON.stringify"), false, "bodyless POST by contract");
  section("3. Retry repository method sends no workflow data and no rerender flag");
}

// ── 4. Generate Again and first Generate keep the ordinary route ─────────

{
  const stub = stubFetch(() => ({ body: { accepted: true, attempt_status: "queued" } }));
  try {
    const repo = await createHistoryRepository({ mode: "v2", apiBase: "/comfymodal" });
    await repo.generateOriginal("gen_e4d");
    await repo.generateOriginal("gen_e4d", { rerender: true });
    assert.equal(stub.calls.length, 2);
    assert.ok(stub.calls.every((c) => c.url.endsWith("/original")),
      "both generate actions use the ordinary /original route");
    assert.equal(stub.calls.filter((c) => c.url.indexOf("/original/retry") !== -1).length, 0,
      "generate actions never touch the retry route");
    assert.deepEqual(JSON.parse(stub.calls[0].body), {}, "first Generate Original sends {}");
    assert.deepEqual(JSON.parse(stub.calls[1].body), { rerender: true },
      "Generate Again STILL sends rerender:true");
    section("4. Generate Again stays /original + rerender:true; first Generate stays /original");
  } finally { stub.restore(); }
}

// ── 5. Ordinary /original can truthfully return retry_required ───────────

{
  const stub = stubFetch(() => ({
    body: {
      status: "ok", outcome: "retry_required", generation_id: "gen_e4d",
      run_id: "run_failed", purpose: "original", attempt_status: "failed", reused: false,
    },
  }));
  try {
    const repo = await createHistoryRepository({ mode: "v2", apiBase: "/comfymodal" });
    const resp = await repo.generateOriginal("gen_e4d");
    assert.equal(stub.calls.length, 1);
    assert.equal(resp.accepted, false,
      "retry_required is a machine-readable refusal despite HTTP 200");
    assert.equal(resp.outcome, "retry_required");
    assert.equal(resp.attemptStatus, "failed", "durable failed Attempt state is surfaced");
    // Code-based refusals normalize truthfully too.
    const irreproducible = normalizeOriginalGenerationResponse(
      { status: "error", code: "generation_not_reproducible", message: "snapshot not reproducible" },
      { httpStatus: 409, generationId: "gen_e4d", purpose: "original" });
    assert.equal(irreproducible.accepted, false);
    assert.equal(irreproducible.outcome, "irreproducible");
    section("5. retry_required from ordinary /original is a refusal/state transition, never success");
  } finally { stub.restore(); }
}

// ── 6. retry_required never auto-retries and never loops ─────────────────

{
  // Detail runner: handles retry_required without invoking any Original POST.
  const runStart = detailSource.indexOf("async function _postOriginalAction");
  const runEnd = detailSource.indexOf("function _runGenerateOriginal");
  assert.ok(runStart >= 0 && runEnd > runStart, "shared detail runner exists");
  const runner = detailSource.slice(runStart, runEnd);
  assert.equal(runner.includes('outcome === "retry_required"'), true,
    "retry_required handled explicitly");
  assert.equal(runner.includes("_runRetryOriginal"), false,
    "retry_required does NOT automatically invoke Retry");
  assert.equal(runner.includes("repo.retryOriginal"), false);
  assert.equal(runner.includes("repo.generateOriginal"), false,
    "no loop back into ordinary /original");
  assert.equal(runner.split("reload()").length - 1 >= 1, true,
    "refusal path re-reads durable state instead of re-posting");

  // Cell runner: identical guarantees.
  const cellStart = experimentSource.indexOf("async function _postCellOriginalAction");
  const cellEnd = experimentSource.indexOf("function _runCellGenerateOriginal");
  assert.ok(cellStart >= 0 && cellEnd > cellStart, "shared cell runner exists");
  const cellRunner = experimentSource.slice(cellStart, cellEnd);
  assert.equal(cellRunner.includes('outcome === "retry_required"'), true);
  assert.equal(cellRunner.includes("_runCellRetryOriginal"), false);
  assert.equal(cellRunner.includes("repo.retryOriginalForCell"), false);
  assert.equal(cellRunner.includes("repo.generateOriginalForCell"), false);

  // Single call sites: explicit user actions are the ONLY retry invocations.
  assert.equal(detailSource.split("repo.retryOriginal(").length - 1, 1,
    "one detail retry call site");
  assert.equal(detailSource.split("_runRetryOriginal").length - 1, 2,
    "_runRetryOriginal referenced only by definition + failed-phase onclick");
  assert.equal(detailSource.includes('onclick: function () { _runRetryOriginal(); }'), true,
    "only the failed-phase button dispatches Retry");
  assert.equal(experimentSource.split("repo.retryOriginalForCell(").length - 1, 1,
    "one cell retry call site — no browser fanout");
  assert.equal(experimentSource.split("_runCellRetryOriginal(").length - 1, 2,
    "_runCellRetryOriginal referenced only by definition + failed-phase dispatch");
  section("6. retry_required never auto-invokes Retry and never loops /original");
}

// ── 7. Duplicate Retry clicks are guarded ────────────────────────────────

{
  assert.equal(detailSource.includes("let _originalInFlight = false;"), true);
  assert.equal(detailSource.includes("if (_originalInFlight || _closed) return;"), true,
    "detail single-flight guard");
  assert.equal(experimentSource.includes("if (!genId || _inFlightOriginal[genId]) return;"), true,
    "cell single-flight guard keyed by generation id");
  assert.equal(experimentSource.includes("disabled: disabled || !!_inFlightOriginal[genId]"), true,
    "in-flight cell control renders disabled");
  assert.equal(detailSource.includes('btn.textContent = "Queuing\\u2026";'), true,
    "in-flight detail control shows Queuing… and is disabled");
  section("7. Duplicate Retry click creates at most one frontend request");
}

// ── 8. Same Generation identity end-to-end (Single + cell) ───────────────

{
  const stub = stubFetch(() => ({ body: { accepted: true, attempt_status: "queued" } }));
  try {
    const repo = await createHistoryRepository({ mode: "v2", apiBase: "/comfymodal" });
    await repo.retryOriginal("gen_same_id");
    await repo.retryOriginalForCell("gen_cell_9");
    assert.equal(stub.calls.length, 2);
    assert.equal(stub.calls[0].url,
      "/comfymodal/history-v2/generations/gen_same_id/original/retry");
    assert.equal(stub.calls[1].url,
      "/comfymodal/history-v2/generations/gen_cell_9/original/retry",
      "cell retry uses the CELL'S OWN generation_id — never an index or experiment id");
    assert.ok(stub.calls.every((c) => c.url.indexOf("/history-v2/generations/") !== -1
      && c.url.endsWith("/original/retry")),
      "Generation-scoped retry routes only — no new Generation created client-side");
    // Missing identity stays inert.
    const inert = await repo.retryOriginal("");
    assert.equal(inert.accepted, false);
    assert.equal(stub.calls.length, 2, "no fetch without a Generation identity");
    section("8. Retry keeps the same Generation ID for Single and Experiment cells");
  } finally { stub.restore(); }
}

// ── 9. Failed Attempt immutable; new Attempt loaded from backend state ───

{
  assert.equal(detailSource.includes(".status ="), false,
    "no client-side attempt/status mutation on detail");
  assert.equal(experimentSource.includes(".status ="), false,
    "no client-side attempt/status mutation in the experiment grid");
  // Polling reuses the existing E4C architecture and re-renders durable data.
  assert.equal(detailSource.includes("repo.getGeneration(generationId)"), true);
  assert.equal(detailSource.includes("_renderDetail(fresh)"), true,
    "poll ticks render fresh backend state (new Attempt appears from backend)");
  assert.equal(detailSource.split("function _startOriginalPolling").length - 1, 1,
    "single polling architecture reused — no second poll system");
  assert.equal(/WebSocket|EventSource/.test(detailSource), false);
  assert.equal(experimentSource.includes("repo.getExperiment(experimentId)"), true);
  assert.equal(experimentSource.includes("_rerenderPage(fresh)"), true);
  assert.equal(experimentSource.split("function _startCellOriginalPolling").length - 1, 1);
  section("9. Failed Attempt stays immutable; retry state comes from durable backend data");
}

// ── 10-11. Preview retained through queued/running/failed retry states ───

{
  const queued = deriveOriginalActionState(generation({
    attempts: [
      { mode: "preview", status: "completed" },
      { mode: "original", status: "failed", run_id: "run_o1" },
      { mode: "original", status: "queued", run_id: "run_o2" },
    ],
  }));
  assert.equal(queued.phase, "active", "queued Retry Attempt → active");
  assert.equal(queued.hasPreview, true, "Preview remains visible while Retry is queued");
  assert.equal(queued.latestAttempt.run_id, "run_o2", "new Retry Attempt is the latest");
  const running = deriveOriginalActionState(generation({
    attempts: [
      { mode: "preview", status: "completed" },
      { mode: "original", status: "running", run_id: "run_o2" },
    ],
  }));
  assert.equal(running.phase, "active");
  assert.equal(running.hasPreview, true);
  // Prior successful Original survives a later failed rerender.
  const retained = deriveOriginalActionState(generation({
    original_available: true,
    outputs: [{ preview_url: "/preview", original_url: "/original" }],
    attempts: [
      { mode: "original", status: "completed", run_id: "run_ok" },
      { mode: "original", status: "failed", run_id: "run_bad", error: "GPU lost" },
    ],
  }));
  assert.equal(retained.phase, "success", "earlier successful Original remains available");
  assert.equal(retained.originalAvailable, true);
  assert.equal(retained.latestAttempt.status, "failed", "failed Attempt remains distinct");
  section("10-11. Preview retained while Retry runs; prior success survives later failure");
}

// ── 12. Successful Retry still does not eager-load Original ──────────────

{
  const placeholder = selectGenerationDetailAsset({ featuredOutput: { originalUrl: "/original" } });
  assert.equal(placeholder.url, "", "success never eager-loads Original bytes");
  assert.equal(placeholder.label, "Original available");
  assert.equal(selectDetailAsset({ originalUrl: "/original" }).url, "");
  assert.equal(detailSource.includes('data-testid": "history-v2-view-original"'), true,
    "View Original remains explicit");
  const clickIndex = detailSource.indexOf('text: "View Original"');
  const srcIndex = detailSource.indexOf("src: feat.originalUrl");
  assert.ok(clickIndex >= 0 && clickIndex < srcIndex, "Original bytes load only on click");
  assert.equal(detailSource.split(".src =").length - 1, 0, "no imperative src assignment");
  section("12. Retry success preserves click-only Original loading (E4B rule)");
}

// ── 13. Truthful refusals on the retry route ─────────────────────────────

{
  const cases = [
    [409, { status: "error", code: "generation_busy", message: "a preview attempt of this generation is still active" }, "busy"],
    [409, { status: "error", code: "retry_not_available", message: "generate original is not available for this generation state" }, ""],
    [503, { status: "error", code: "dispatch_unavailable", message: "dispatch registration failed" }, ""],
    [404, { status: "error", code: "generation_not_found", message: "no such generation" }, ""],
  ];
  for (const [status, body, expectedOutcome] of cases) {
    const stub = stubFetch(() => ({ status, body }));
    try {
      const repo = await createHistoryRepository({ mode: "v2", apiBase: "/comfymodal" });
      const resp = await repo.retryOriginal("gen_e4d");
      assert.equal(resp.accepted, false, body.code + " is a truthful refusal");
      assert.equal(resp.httpStatus, status);
      assert.equal(resp.errorCode, body.code, "backend error code preserved");
      assert.equal(resp.errorMessage, body.message, "backend message preserved");
      if (expectedOutcome) assert.equal(resp.outcome, expectedOutcome);
    } finally { stub.restore(); }
  }
  {
    const stub = stubFetch(() => ({ status: 500, body: "boom" }));
    try {
      const repo = await createHistoryRepository({ mode: "v2", apiBase: "/comfymodal" });
      await assert.rejects(() => repo.retryOriginal("gen_e4d"),
        /HTTP 500/, "opaque HTTP failures reject truthfully");
    } finally { stub.restore(); }
  }
  section("13. Busy/refusal/opaque errors remain truthful on /original/retry");
}

// ── 14. Legacy/irreproducible gate remains truthful ──────────────────────

{
  assert.equal(generateOriginalEligibility({ id: "gen_x" }, { mode: "bridge" }).eligible, false);
  assert.equal(generateOriginalEligibility({ id: "gen_x" }, { mode: "fixture" }).eligible, false);
  assert.equal(generateOriginalEligibility(
    { id: "gen_x", irreproducible: true }, { mode: "auto" }).eligible, false);
  assert.equal(generateOriginalEligibility({ id: "gen_x" }, { mode: "auto" }).eligible, true);
  section("14. Legacy/irreproducible generations still cannot retry or rebuild");
}

// ── 15. Experiment cell parity: failed phase dispatches the retry route ──

{
  assert.equal(experimentSource.includes('action = "retry"'), true,
    "failed phase selects the retry action");
  assert.equal(experimentSource.includes('if (action === "retry") _runCellRetryOriginal(genId);'), true,
    "cell menu/pane dispatch the dedicated retry runner");
  assert.equal(experimentSource.includes("_cellGenerationId(cell)"), true,
    "identity comes from the cell's own generation_id");
  assert.equal(experimentSource.includes("function buildCellOriginalAction(cell, rec, variant)"), true,
    "menu and pane share one builder — one dispatch, no fanout");
  assert.equal(experimentSource.includes('"Retrying Original\\u2026"'), true,
    "cell retry shows its own pending label");
  section("15. Experiment cell Retry uses generationId on the same /original/retry route");
}
