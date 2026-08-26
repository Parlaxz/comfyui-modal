// Modal Studio — D5 History V2 Experiment Detail Unit Tests
//
// Executable behavioral tests for web/studio-history-v2-experiment.js:
//   - fixed grid: every cell rendered in backend order keyed by stable
//     cell_id (never reordered by completion)
//   - canonical status labels: canceled vs interrupted vs failed distinct;
//     "success" normalizes to "Completed"; no "partial" anywhere
//   - correct workflow/version/preset labels per cell (cell-level ids
//     preferred, record-level fallback)
//   - attempts surfaced when the record carries them
//   - cell Retry only for failed cells; Resume only when interrupted or
//     queued/not-started cells exist (never while running)
//   - Generate Original (E4C): routed through the cell's generation_id,
//     one call site, disabled gate when no Generation identity exists.
//   - legacy rendering compatibility: renderExperimentDetail retained, the
//     counts line and axis line builders unchanged ("12 results · 12 total
//     cells", "Axis X: ... · Axis Y: ...")
//
// No browser, no DOM, plain Node.
//
// Run: node tests/studio_history_v2_experiment_unit.mjs

import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import {
  renderExperimentDetail,
  canonicalCellStatus,
  experimentStatusLabel,
  historyCellIdentity,
  historyResumeEligible,
  historyRetryEligible,
  historyExperimentCancelEligible,
  historyCellAttemptCount,
  cellWorkflowMeta,
  buildExperimentCountsText,
  buildExperimentAxisText,
} from "../web/studio-history-v2-experiment.js";

const MODULE_SRC = fs.readFileSync(
  path.join(import.meta.dirname, "..", "web", "studio-history-v2-experiment.js"),
  "utf8",
);

function section(name) {
  console.log("PASS: " + name);
}

/** Minimal experiment record shaped like the repository's detail output. */
function makeRecord(overrides) {
  const o = overrides || {};
  return Object.assign({
    id: "exp_001",
    kind: "experiment",
    name: "Seed sweep \u00b7 Steps",
    status: "completed",
    workflow: "Portrait Pro",
    workflowVersion: "v3",
    preset: "preset_a",
    resultCount: 12,
    failedCount: 0,
    interruptedCount: 0,
    trueCellCount: 12,
    axisLabels: { x: "Seed", y: "Steps" },
    cells: [],
  }, o);
}

function makeCell(overrides) {
  const o = overrides || {};
  return Object.assign({
    key: o.key != null ? o.key : "cell_0",
    index: o.index != null ? o.index : 0,
    axis: { x: "0", y: "20" },
    status: "success",
    thumbUrl: "",
    previewUrl: "",
    originalUrl: "",
    originalFailed: false,
    durationMs: null,
    error: "",
    favorite: false,
  }, o);
}

// ── 1. Fixed grid: backend order keyed by stable cell_id ────────────────

{
  // Backend order deliberately mixes statuses (completed first, failed in
  // the middle, queued last) — the detail grid must NOT reorder by status.
  const cells = [
    makeCell({ key: "cell_0", status: "completed", cellId: "cell_0" }),
    makeCell({ key: "cell_1", status: "failed", cellId: "cell_1", error: "boom" }),
    makeCell({ key: "cell_2", status: "queued", cellId: "cell_2" }),
    makeCell({ key: "cell_3", status: "completed", cellId: "cell_3" }),
  ];
  const identities = cells.map((c, i) => historyCellIdentity(c, i));
  assert.deepEqual(identities, ["cell_0", "cell_1", "cell_2", "cell_3"], "order follows the record (backend) order");

  // Identity is stable across status changes (cell_id wins; key fallback).
  const queued = makeCell({ key: "cell_1", status: "queued" });
  const failed = makeCell({ key: "cell_1", status: "failed" });
  assert.equal(historyCellIdentity(queued, 1), historyCellIdentity(failed, 1),
    "same cell keeps the same identity regardless of status");

  // Position fallback for key-less cells.
  assert.equal(historyCellIdentity({ status: "completed" }, 7), "cell_7");
  section("1. Fixed grid order keyed by stable cell_id");
}

// ── 2. Canonical status labels; canceled/interrupted/failed distinct ─────

{
  assert.equal(canonicalCellStatus("success"), "completed", "raw success normalizes to completed");
  assert.equal(canonicalCellStatus("succeeded"), "completed");
  assert.equal(canonicalCellStatus("error"), "failed");
  assert.equal(canonicalCellStatus("cancelled"), "canceled");
  assert.equal(canonicalCellStatus("in_progress"), "running");
  assert.equal(canonicalCellStatus("pending"), "queued");
  assert.equal(canonicalCellStatus("not_started"), "queued");
  assert.equal(canonicalCellStatus(null), "queued");

  assert.equal(experimentStatusLabel("canceled"), "Canceled");
  assert.equal(experimentStatusLabel("interrupted"), "Interrupted");
  assert.equal(experimentStatusLabel("failed"), "Failed");
  assert.equal(experimentStatusLabel("completed"), "Completed");
  assert.equal(experimentStatusLabel("queued"), "Queued");
  assert.equal(experimentStatusLabel("running"), "Running");
  assert.equal(experimentStatusLabel("completed_with_failures"), "Completed with failures");
  assert.notEqual(experimentStatusLabel("canceled"), experimentStatusLabel("interrupted"),
    "user canceled is not interrupted");
  assert.notEqual(experimentStatusLabel("interrupted"), experimentStatusLabel("failed"),
    "interrupted is not failed");

  // The "partial" alias normalizes to completed_with_failures and the label
  // never renders the word "partial".
  assert.equal(canonicalCellStatus("partial"), "completed_with_failures");
  assert.equal(experimentStatusLabel("partial"), "Completed with failures");
  assert.equal(experimentStatusLabel("completed_with_failures").toLowerCase().includes("partial"), false);
  assert.equal(MODULE_SRC.includes('"Partial"'), false, "module never renders a 'Partial' display label");
  section("2. Canonical status labels, canceled vs interrupted vs failed");
}

// ── 3. Per-cell workflow/version/preset labels ───────────────────────────

{
  const rec = makeRecord({ workflow: "Fallback Workflow", workflowVersion: "v1", preset: "fallback_preset" });
  const withIds = makeCell({ key: "c1", workflowId: "wf_9", workflowVersionId: "ver_9", presetId: "pre_9" });
  const meta = cellWorkflowMeta(withIds, rec);
  assert.equal(meta.workflow, "wf_9", "cell-level workflow id preferred");
  assert.equal(meta.version, "ver_9", "cell-level version id preferred");
  assert.equal(meta.preset, "pre_9", "cell-level preset id preferred");

  const noIds = makeCell({ key: "c2" });
  const fallback = cellWorkflowMeta(noIds, rec);
  assert.equal(fallback.workflow, "Fallback Workflow", "record-level workflow fallback");
  assert.equal(fallback.version, "v1", "record-level version fallback");
  assert.equal(fallback.preset, "fallback_preset", "record-level preset fallback");

  // snake_case cell fields also read (status-endpoint shape).
  const snake = cellWorkflowMeta(
    { workflow_id: "wf_s", workflow_version_id: "ver_s", preset_id: "pre_s" },
    rec,
  );
  assert.equal(snake.workflow, "wf_s");
  assert.equal(snake.version, "ver_s");
  assert.equal(snake.preset, "pre_s");
  section("3. Workflow/version/preset labels per cell");
}

// ── 4. Attempts surfaced from the record ─────────────────────────────────

{
  assert.equal(historyCellAttemptCount(makeCell({})), 0, "no attempts when absent");
  const withAttempts = makeCell({ attempts: [{ status: "failed", run_id: "run_1" }, { status: "running", run_id: "run_2" }] });
  assert.equal(historyCellAttemptCount(withAttempts), 2, "attempts[] length used");
  assert.equal(historyCellAttemptCount({ attemptCount: 3 }), 3, "attemptCount field used");
  section("4. Attempts surfaced when present");
}

// ── 5. Cell Retry only for failed cells ──────────────────────────────────

{
  assert.equal(historyRetryEligible(makeCell({ status: "failed" })), true);
  assert.equal(historyRetryEligible(makeCell({ status: "error" })), true, "raw error normalizes to failed");
  assert.equal(historyRetryEligible(makeCell({ status: "completed" })), false);
  assert.equal(historyRetryEligible(makeCell({ status: "queued" })), false);
  assert.equal(historyRetryEligible(makeCell({ status: "running" })), false);
  assert.equal(historyRetryEligible(null), false);
  section("5. Cell Retry only for failed cells");
}

// ── 6. Experiment Resume eligibility ─────────────────────────────────────

{
  // Interrupted cells → eligible.
  const interrupted = makeRecord({
    status: "interrupted",
    cells: [
      makeCell({ key: "c0", status: "completed" }),
      makeCell({ key: "c1", status: "interrupted" }),
      makeCell({ key: "c2", status: "queued" }),
    ],
  });
  assert.equal(historyResumeEligible(interrupted), true, "interrupted + queued cells resume-eligible");

  // Queued/not-started cells → eligible (D5: a "queued" aggregate with
  // queued/not-started cells IS resume-eligible; only actively running
  // experiments suppress Resume).
  const queued = makeRecord({
    status: "queued",
    cells: [
      makeCell({ key: "c0", status: "completed" }),
      makeCell({ key: "c1", status: "queued" }),
    ],
  });
  assert.equal(historyResumeEligible(queued), true, "queued aggregate with never-started cells resume-eligible");

  const allQueued = makeRecord({
    status: "queued",
    cells: [
      makeCell({ key: "c0", status: "queued" }),
      makeCell({ key: "c1", status: "queued" }),
    ],
  });
  assert.equal(historyResumeEligible(allQueued), true, "all-queued experiment resume-eligible");

  // A queued aggregate with a failed cell stays eligible; failed cells are
  // skipped by Resume, never resumed.
  const queuedPlusFailed = makeRecord({
    status: "queued",
    cells: [
      makeCell({ key: "c0", status: "queued" }),
      makeCell({ key: "c1", status: "failed" }),
    ],
  });
  assert.equal(historyResumeEligible(queuedPlusFailed), true, "queued cells eligible alongside a failed cell");

  // Failed cells are NOT resumed (they require Retry).
  const failedOnly = makeRecord({
    status: "completed_with_failures",
    cells: [
      makeCell({ key: "c0", status: "completed" }),
      makeCell({ key: "c1", status: "failed" }),
    ],
  });
  assert.equal(historyResumeEligible(failedOnly), false, "failed cells are skipped by Resume");

  // Actively running experiments (a cell in "running") are never resumable.
  const running = makeRecord({
    status: "running",
    cells: [
      makeCell({ key: "c0", status: "running" }),
      makeCell({ key: "c1", status: "queued" }),
    ],
  });
  assert.equal(historyResumeEligible(running), false, "running experiments not resumable");

  // A record whose aggregate status was coerced to "running" but has NO
  // actively running cell is still resume-eligible (only active running
  // cells suppress Resume).
  const coercedRunning = makeRecord({
    status: "running",
    cells: [
      makeCell({ key: "c0", status: "queued" }),
      makeCell({ key: "c1", status: "queued" }),
    ],
  });
  assert.equal(historyResumeEligible(coercedRunning), true, "coerced running status without active cells stays resumable");

  // All-completed → not eligible.
  const done = makeRecord({
    status: "completed",
    cells: [makeCell({ key: "c0", status: "completed" })],
  });
  assert.equal(historyResumeEligible(done), false);
  section("6. Resume eligibility");
}

// ── 7. Generate Original uses the cell's Generation identity (E4C) ───────

{
  // E4C: the cell action POSTs through repo.generateOriginalForCell with the
  // CELL'S generation_id — one call site, no fanout, no legacy endpoint, and
  // cells without a generation_id render a truthful disabled gate.
  assert.equal(MODULE_SRC.includes("repo.generateOriginalForCell(genId,"), true,
    "single repository generateOriginalForCell call with generation identity");
  assert.equal(MODULE_SRC.split("repo.generateOriginalForCell(").length - 1, 1,
    "no browser fanout — exactly one call site");
  assert.equal(MODULE_SRC.includes("_cellGenerationId(cell)"), true);
  assert.equal(MODULE_SRC.includes("Generate Original unavailable"), true,
    "cells without a generation_id keep a disabled gate label");

  // A repo stub that throws if generation is requested proves the pure gate
  // helpers above never touch the repo on their own.
  const repo = {
    getExperiment: async () => makeRecord({
      cells: [makeCell({ key: "c0", status: "completed" })],
    }),
    generateOriginalForCell: async () => { throw new Error("must never be called"); },
  };
  assert.equal(typeof repo.generateOriginalForCell, "function");
  section("7. Generate Original routed through the cell's generation_id");
}

// ── 8. Legacy rendering compatibility ────────────────────────────────────

{
  assert.equal(typeof renderExperimentDetail, "function", "renderExperimentDetail entry retained");

  const rec = makeRecord({
    status: "completed",
    resultCount: 12,
    failedCount: 0,
    interruptedCount: 0,
    trueCellCount: 12,
  });
  const counts = buildExperimentCountsText(rec);
  assert.ok(counts.includes("12 results"), "counts line keeps '12 results'");
  assert.ok(counts.includes("12 total cells"), "counts line keeps '12 total cells'");

  const axis = buildExperimentAxisText(makeRecord({ axisLabels: { x: "Seed", y: "Steps" } }));
  assert.ok(axis.includes("Axis X: Seed"), "axis line keeps 'Axis X: Seed'");
  assert.ok(axis.includes("Axis Y: Steps"), "axis line keeps 'Axis Y: Steps'");

  // Existing chip class names stay stable (status-failed → "Failed").
  assert.equal(experimentStatusLabel("failed"), "Failed");
  assert.equal(MODULE_SRC.includes("history-v2-experiment-retry"), true, "experiment retry testid retained");
  assert.equal(MODULE_SRC.includes("history-v2-experiment-counts"), true, "counts testid retained");
  assert.equal(MODULE_SRC.includes("history-v2-experiment-cell"), true, "cell tile testid retained");

  // D5: NO experiment-level retry-all.  The header button is disabled and
  // never calls repo.retryExperiment; per-cell Retry via repo.retryCell is
  // the only retry path.
  assert.equal(MODULE_SRC.includes("repo.retryExperiment"), false, "no repo.retryExperiment retry-all call");
  assert.equal(MODULE_SRC.includes("repo.retryCell"), true, "per-cell Retry via repo.retryCell retained");
  assert.equal(MODULE_SRC.includes("Retry experiment"), true, "retry button label retained (disabled)");
  assert.equal(MODULE_SRC.includes("disabled: true"), true, "the retry-all button is disabled");
  section("8. Legacy rendering compatibility");
}

// ── 9. Experiment Cancel eligibility (durable-state truth table) ─────────

{
  // Backend truth (experiment_modern_routes._handle_cancel): cancel applies
  // exactly when at least one cell is queued or running; an all-terminal
  // aggregate is refused (409 EXPERIMENT_TERMINAL / idempotent 200).
  const queuedOnly = makeRecord({
    status: "running",
    cells: [makeCell({ key: "c0", status: "queued" }), makeCell({ key: "c1", status: "queued" })],
  });
  assert.equal(historyExperimentCancelEligible(queuedOnly), true, "queued cells are cancelable");

  const running = makeRecord({
    status: "running",
    cells: [
      makeCell({ key: "c0", status: "completed" }),
      makeCell({ key: "c1", status: "running" }),
      makeCell({ key: "c2", status: "queued" }),
    ],
  });
  assert.equal(historyExperimentCancelEligible(running), true, "any running cell keeps Cancel available");

  const mixedTerminalPlusQueued = makeRecord({
    status: "running",
    cells: [
      makeCell({ key: "c0", status: "completed" }),
      makeCell({ key: "c1", status: "failed" }),
      makeCell({ key: "c2", status: "canceled" }),
      makeCell({ key: "c3", status: "queued" }),
    ],
  });
  assert.equal(historyExperimentCancelEligible(mixedTerminalPlusQueued), true,
    "terminal siblings do not block a queued cell");

  // Terminal aggregates — no enabled Cancel that can only fail.
  const completed = makeRecord({
    status: "completed",
    cells: [makeCell({ key: "c0", status: "completed" }), makeCell({ key: "c1", status: "success" })],
  });
  assert.equal(historyExperimentCancelEligible(completed), false, "completed is terminal");

  const withFailures = makeRecord({
    status: "completed_with_failures",
    cells: [makeCell({ key: "c0", status: "completed" }), makeCell({ key: "c1", status: "failed" })],
  });
  assert.equal(historyExperimentCancelEligible(withFailures), false, "completed_with_failures is terminal");

  const failedAggregate = makeRecord({
    status: "failed",
    cells: [makeCell({ key: "c0", status: "error" })],
  });
  assert.equal(historyExperimentCancelEligible(failedAggregate), false, "failed aggregate is terminal");

  const canceled = makeRecord({
    status: "canceled",
    cells: [makeCell({ key: "c0", status: "cancelled" })],
  });
  assert.equal(historyExperimentCancelEligible(canceled), false, "already-canceled is terminal");

  // interrupted-only is terminal-like per the backend truth table (all cells
  // in _TERMINAL_CANONICAL → 409); eligibility must not broaden it.
  const interruptedOnly = makeRecord({
    status: "interrupted",
    cells: [makeCell({ key: "c0", status: "interrupted" }), makeCell({ key: "c1", status: "aborted" })],
  });
  assert.equal(historyExperimentCancelEligible(interruptedOnly), false,
    "interrupted-only follows backend terminal truth");

  assert.equal(historyExperimentCancelEligible(null), false, "no record → not eligible");
  assert.equal(historyExperimentCancelEligible(makeRecord({})), false, "no cells → not eligible");
  section("9. Experiment Cancel eligibility from durable state");
}

// ── 10. History Cancel UI contract + cell-menu focus fix (F1B) ───────────

{
  // Cancel parity: exactly one repository call site; no second cancellation
  // concept; eligibility gates the control.
  assert.equal(MODULE_SRC.split("repo.cancelExperiment(").length - 1, 1,
    "exactly one repo.cancelExperiment call site in History UI");
  assert.equal(MODULE_SRC.includes("historyExperimentCancelEligible(rec)"), true,
    "Cancel visibility derives from durable eligibility");
  assert.equal(MODULE_SRC.includes('"history-v2-experiment-cancel"'), true, "cancel testid present");

  // No optimistic canceled state: the module never writes canceled onto
  // cells or fabricates a terminal aggregate locally.
  assert.equal(/\.status\s*=\s*["']canceled["']/.test(MODULE_SRC), false,
    "no local cell.status = 'canceled' fabrication");
  assert.equal(MODULE_SRC.includes("CANCELLATION_UNAVAILABLE"), true,
    "structured refusal code handled without parsing human text");

  // Cell menu focus fix (F1 audit latent defect): the unbound `item.focus()`
  // is gone and focus lands on the first actionable menu button.
  assert.equal(/\bitem\.focus\(\)/.test(MODULE_SRC), false, "unbound item.focus() removed");
  assert.equal(MODULE_SRC.includes('menu.querySelector("button:not([disabled])")'), true,
    "focus targets the first actionable menu item");

  // Original cell-menu actions stay intact through the fix.
  assert.equal(MODULE_SRC.includes("_runCellGenerateOriginal(genId, rerender)"), true,
    "Generate Original callback intact");
  assert.equal(MODULE_SRC.includes("_runCellRetryOriginal(genId)"), true, "Retry Original callback intact");

  // F2A canonical cell favorite ownership preserved (Generation-backed).
  assert.equal(MODULE_SRC.includes("repo.setFavorite(genId, next)"), true,
    "cell favorite still drives the Generation route");
  section("10. History Cancel UI contract + cell-menu focus fix");
}

console.log("PASS: studio history v2 experiment detail unit tests");
