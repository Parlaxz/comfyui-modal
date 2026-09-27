// Modal Studio — Declarative Fake-Backend Scenarios
//
// Pure data/definitions for the deterministic fake backend
// (fake-backend.mjs).  Each entry in `SCENARIOS` describes a scenario a
// test can select via POST /__comfymodal_test/scenario before submitting a
// Studio run or experiment.  The engine turns these definitions into
// journal events (polled via GET /comfymodal/experiments/:id) and
// tracker-bus events (dispatched via the harness api stub pump).
//
// PLACEHOLDER TOKENS
//   Timeline/journal/tracker payloads may reference tokens that the engine
//   resolves against the experiment it creates at submit time:
//     {experiment_id}  {run_id}  {run_history_id}  {prompt_id}
//     {checkpoint_N}   {attempt_N}   {cell_key_N}   {asset_N}
//     {preview_asset_N}  {output_N}
//   N is a 0-based index (cell index for checkpoints/attempts/assets,
//   flat output index across all cells).  Keeping ids out of the
//   definitions keeps scenarios data-only and deterministic.
//
// SCENARIO FIELDS
//   kind            "single" | "experiment" | "seed"
//   cellCount       number of cells (experiment kind)
//   outputsPerCell  outputs generated per cell (default 1)
//   axes            {axisName: [values...]} → compilation.cells axis_values
//   submit          { delay?, error? } — delay simulates a slow HTTP
//                   response; error makes POST /studio/run return HTTP 400
//                   {status:"error", message, error_code, ...}.
//   initialStatus   snapshot status right after submit ("queued"/"running"…)
//   initialJournal  journal events appended at submit
//   initialTracker  tracker events queued at submit
//   steps           [ { at: "submit"|"poll:N"|{ms:N}, status?, journal?,
//                       tracker? } ] — applied at submit, on the Nth poll
//                   of the experiment, or on a timer N ms after submit.
//   terminal        { delay, status, journal, tracker } — applied on a
//                   timer delay ms after submit (unless a poll/step already
//                   reached a terminal snapshot status).
//   registerAssets  default true; set false to disable asset registration
//   missingAssets   tokens (e.g. "{asset_0}") whose assets/outputs are NOT
//                   registered so /comfymodal/assets/:id returns 404.
//   seed            descriptor for kind:"seed" used by seedHistory().
//
// CONTRACT NOTE (preview vs original)
//   The production web UI does not contain a distinct "preview output
//   preference" feature: output_format values are original/webp_lossless/
//   webp_lossy/jpeg (see web/studio-output-preferences.js and
//   web/modal-settings.js), and "preview" in the UI means the lightbox
//   overlay.  The preview_result / original_result / original_rerender_failure
//   scenarios therefore model the realistic payload SHAPE of a run that
//   materializes a low-cost preview image alongside the original: the
//   cell.completed journal carries both `preview_asset_id` (small,
//   always served) and `primary_asset_id` (original, 404 on rerender
//   failure).  Test writers should assert on asset URL serving (200 vs 404)
//   and on primary vs preview asset ids in journal payloads.

const PNG_META = { /* engine provides deterministic bytes; nothing here */ };

// ── Journal event builders ──────────────────────────────────────────────
//
// These return data only; `{token}` placeholders are resolved by the engine.

function started(totalCells) {
  return {
    type: "experiment.started",
    payload: { experiment_id: "{experiment_id}", revision: 1, total_cells: totalCells },
  };
}

function created(totalCells, axes) {
  const cells = [];
  const combos = axes ? cartesian(axes) : [];
  for (let i = 0; i < totalCells; i++) {
    cells.push({
      cell_key: `{cell_key_${i}}`,
      axis_values: combos.length > 0 ? (combos[i % combos.length] || {}) : {},
    });
  }
  return {
    type: "experiment.created",
    payload: {
      experiment_id: "{experiment_id}",
      revision: 1,
      total_cells: totalCells,
      compilation: { cells },
    },
  };
}

function cartesian(axes) {
  const names = Object.keys(axes);
  let out = [{}];
  for (const name of names) {
    const values = Array.isArray(axes[name]) ? axes[name] : [];
    const next = [];
    for (const acc of out) {
      for (const v of values) next.push(Object.assign({}, acc, { [name]: v }));
    }
    out = next;
  }
  return out;
}

function attemptCreated(cellIdx) {
  return {
    type: "cell.attempt_created",
    payload: {
      cell_key: `{cell_key_${cellIdx}}`,
      checkpoint_id: `{checkpoint_${cellIdx}}`,
      attempt_id: `{attempt_${cellIdx}}`,
      status: "pending",
    },
  };
}

const COMPLETE_TRACE = {
  trace: {
    deltas_ms: {
      end_to_end_total_ms: 4523,
      sampling_ms: 3200,
      clip_encode_ms: 450,
      vae_decode_ms: 280,
      model_load_ms: 120,
    },
    trace_version: "2.0.0",
  },
  timing_quality: "complete",
};

function cellCompleted(cellIdx, opts = {}) {
  const payload = {
    cell_key: `{cell_key_${cellIdx}}`,
    checkpoint_id: `{checkpoint_${cellIdx}}`,
    attempt_id: `{attempt_${cellIdx}}`,
    timing_payload: opts.timing_payload || COMPLETE_TRACE,
  };
  if (opts.outputPaths) payload.output_paths = opts.outputPaths;
  else payload.output_paths = [`{output_${cellIdx}}`];
  if (opts.primaryAssetId !== false) {
    payload.primary_asset_id = opts.primaryAssetId || `{asset_${cellIdx}}`;
  }
  if (opts.previewAssetId) payload.preview_asset_id = opts.previewAssetId;
  if (opts.extra) Object.assign(payload, opts.extra);
  return { type: "cell.completed", payload };
}

function cellFailed(cellIdx, message, extra = {}) {
  return {
    type: "cell.failed",
    payload: Object.assign(
      {
        cell_key: `{cell_key_${cellIdx}}`,
        checkpoint_id: `{checkpoint_${cellIdx}}`,
        attempt_id: `{attempt_${cellIdx}}`,
        error: message,
        timing_payload: COMPLETE_TRACE,
      },
      extra
    ),
  };
}

function cellInterrupted(cellIdx, reason = "cancelled") {
  return {
    type: "cell.interrupted",
    payload: {
      cell_key: `{cell_key_${cellIdx}}`,
      checkpoint_id: `{checkpoint_${cellIdx}}`,
      attempt_id: `{attempt_${cellIdx}}`,
      reason,
    },
  };
}

function cellSkipped(cellIdx, reason = "depends_on_failed_cell") {
  return {
    type: "cell.skipped",
    payload: {
      cell_key: `{cell_key_${cellIdx}}`,
      checkpoint_id: `{checkpoint_${cellIdx}}`,
      attempt_id: `{attempt_${cellIdx}}`,
      reason,
    },
  };
}

function completed(completedCount, failedCount, interruptedCount, totalCells) {
  return {
    type: "experiment.completed",
    payload: {
      completed: completedCount,
      failed: failedCount,
      interrupted: interruptedCount,
      total_cells: totalCells,
    },
  };
}

function failedFatal(completedCount, failedCount, interruptedCount, totalCells, error) {
  return {
    type: "experiment.failed_fatal",
    payload: {
      completed: completedCount,
      failed: failedCount,
      interrupted: interruptedCount,
      total_cells: totalCells,
      error,
    },
  };
}

function cancelled(completedCount, failedCount, interruptedCount, totalCells) {
  return {
    type: "experiment.cancelled",
    payload: {
      completed: completedCount,
      failed: failedCount,
      interrupted: interruptedCount,
      total_cells: totalCells,
    },
  };
}

function experimentError(message) {
  return {
    type: "experiment.error",
    payload: { experiment_id: "{experiment_id}", error: message, message },
  };
}

// ── Tracker (api-bus) event builders ────────────────────────────────────

function executionStart(totalNodes = 8, samplerMaximum = 20) {
  return {
    type: "execution_start",
    detail: { prompt_id: "{prompt_id}", total_nodes: totalNodes, sampler_maximum: samplerMaximum },
  };
}

function executionSuccess() {
  return { type: "execution_success", detail: { prompt_id: "{prompt_id}" } };
}

function modalStatus(phase, message) {
  return { type: "modal_status", detail: { prompt_id: "{prompt_id}", phase, message } };
}

function progressQueue(queue) {
  return { type: "progress", detail: { value: 0, max: 20, queue } };
}

function workerStatus(cellIdx, phase, message) {
  return {
    type: "experiment.worker.progress",
    detail: {
      experiment_id: "{experiment_id}",
      cell_key: `{cell_key_${cellIdx}}`,
      checkpoint_id: `{checkpoint_${cellIdx}}`,
      attempt_id: `{attempt_${cellIdx}}`,
      total_nodes: 8,
      type: "status",
      phase,
      message,
    },
  };
}

function cellExecuting(cellIdx, node, message) {
  return {
    type: "experiment.worker.progress",
    detail: {
      experiment_id: "{experiment_id}",
      cell_key: `{cell_key_${cellIdx}}`,
      checkpoint_id: `{checkpoint_${cellIdx}}`,
      attempt_id: `{attempt_${cellIdx}}`,
      total_nodes: 8,
      type: "cell.executing",
      node,
      message,
    },
  };
}

function samplerStep(cellIdx, step, max = 20) {
  return {
    type: "experiment.worker.progress",
    detail: {
      experiment_id: "{experiment_id}",
      cell_key: `{cell_key_${cellIdx}}`,
      checkpoint_id: `{checkpoint_${cellIdx}}`,
      attempt_id: `{attempt_${cellIdx}}`,
      total_nodes: 8,
      type: "sampler.step",
      step,
      max,
      message: `Sampling ${step}/${max}`,
    },
  };
}

function workerFailed(cellIdx, message) {
  return {
    type: "experiment.worker.progress",
    detail: {
      experiment_id: "{experiment_id}",
      cell_key: `{cell_key_${cellIdx}}`,
      checkpoint_id: `{checkpoint_${cellIdx}}`,
      attempt_id: `{attempt_${cellIdx}}`,
      total_nodes: 8,
      type: "cell.failed",
      message,
    },
  };
}

function experimentEvent(type, extra = {}) {
  return {
    type: "experiment.event",
    detail: Object.assign({ type, experiment_id: "{experiment_id}" }, extra),
  };
}

// ── Shared step templates ───────────────────────────────────────────────

function samplerBurst(cellIdx, startMs, count = 20, max = 20, gap = 40) {
  const steps = [];
  for (let s = 1; s <= count; s++) {
    steps.push({ at: { ms: startMs + s * gap }, tracker: [samplerStep(cellIdx, s, max)] });
  }
  return steps;
}

function restorePhases() {
  // modal_status startup phases dispatch→entry→restore→custom_nodes→gpu→
  // warmup→backend_init→backend_ready→auto_save→startup (each 150ms apart).
  const phases = [
    ["dispatch", "Dispatching to Modal"],
    ["entry", "Entering entrypoint"],
    ["restore", "Restoring snapshot runtime"],
    ["custom_nodes", "Loading custom nodes"],
    ["gpu", "Allocating GPU"],
    ["warmup", "Warming up"],
    ["backend_init", "Initializing backend"],
    ["backend_ready", "Backend ready"],
    ["auto_save", "Auto-save configured"],
    ["startup", "Startup complete"],
  ];
  return phases.map(([phase, message], i) => ({
    at: { ms: 100 + i * 150 },
    tracker: [modalStatus(phase, message)],
  }));
}

// ── Single-run scenarios ────────────────────────────────────────────────

const success = {
  kind: "single",
  initialStatus: "running",
  initialJournal: [started(1)],
  initialTracker: [executionStart(), modalStatus("dispatch", "Dispatching to Modal")],
  steps: [
    { at: { ms: 120 }, tracker: [workerStatus(0, "warmup", "Warming GPU")] },
    { at: { ms: 220 }, journal: [attemptCreated(0)], tracker: [cellExecuting(0, "4", "KSampler")] },
    { at: { ms: 300 }, tracker: [samplerStep(0, 5), samplerStep(0, 10)] },
    { at: { ms: 380 }, tracker: [samplerStep(0, 15)] },
    { at: { ms: 460 }, tracker: [samplerStep(0, 20)] },
  ],
  terminal: {
    delay: 650,
    status: "completed",
    journal: [cellCompleted(0), completed(1, 0, 0, 1)],
    tracker: [cellExecuting(0, "8", "VAEDecode"), experimentEvent("experiment.completed")],
  },
};

const validation_failure = {
  kind: "single",
  submit: {
    error: {
      status: "error",
      message: "Workflow validation failed: sampler 'bogus' is not valid for this snapshot.",
      error_code: "STUDIO_VALIDATION_ERROR",
      error: {
        code: "STUDIO_VALIDATION_ERROR",
        operation: "workflow_validation",
        detail: "Sampler must be one of euler, dpmpp_2m, dpmpp_sde.",
      },
    },
  },
  initialJournal: [experimentError("Workflow validation failed: sampler 'bogus' is not valid for this snapshot.")],
  initialTracker: [experimentEvent("experiment.error", { error: "Workflow validation failed" })],
  terminal: { delay: 50, status: "error" },
};

const execution_failure = {
  kind: "single",
  initialStatus: "running",
  initialJournal: [started(1)],
  initialTracker: [executionStart(), workerStatus(0, "warmup", "Executing cell")],
  steps: [
    { at: { ms: 200 }, journal: [attemptCreated(0)], tracker: [cellExecuting(0, "4", "KSampler")] },
    {
      at: { ms: 380 },
      journal: [cellFailed(0, "Modal worker crashed: torch.cuda.OutOfMemoryError: CUDA out of memory")],
      tracker: [workerFailed(0, "Cell execution failed: CUDA out of memory")],
    },
  ],
  terminal: {
    delay: 520,
    status: "failed_fatal",
    journal: [failedFatal(0, 1, 0, 1, "Cell execution failed: CUDA out of memory")],
    tracker: [experimentEvent("experiment.failed_fatal", { error: "Cell execution failed: CUDA out of memory" })],
  },
};

const canceled = {
  kind: "single",
  initialStatus: "running",
  initialJournal: [started(1)],
  initialTracker: [executionStart()],
  steps: [{ at: { ms: 200 }, journal: [attemptCreated(0)], tracker: [cellExecuting(0, "4", "KSampler")] }],
  terminal: {
    delay: 900,
    status: "cancelled",
    journal: [cellInterrupted(0, "cancelled"), cancelled(0, 0, 1, 1)],
    tracker: [experimentEvent("experiment.cancelled", { message: "Run cancelled by user" })],
  },
};

const interrupted = {
  kind: "single",
  initialStatus: "running",
  initialJournal: [started(1)],
  initialTracker: [executionStart()],
  steps: [
    { at: { ms: 150 }, journal: [attemptCreated(0)], tracker: [cellExecuting(0, "4", "KSampler")] },
    {
      at: { ms: 350 },
      journal: [cellInterrupted(0, "interrupted")],
      tracker: [],
    },
  ],
  terminal: {
    delay: 500,
    status: "cancelled",
    journal: [cancelled(0, 0, 1, 1)],
    tracker: [experimentEvent("experiment.cancelled", { message: "Run interrupted" })],
  },
};

const slow_submission = {
  kind: "single",
  initialStatus: "queued",
  initialJournal: [started(1)],
  initialTracker: [executionStart(), modalStatus("dispatch", "Dispatching"), modalStatus("entry", "Entering container")],
  steps: [
    { at: { ms: 200 }, tracker: [progressQueue(1), workerStatus(0, "queue", "Waiting in queue (position 1)")] },
    { at: { ms: 500 }, tracker: [progressQueue(0), modalStatus("restore", "Restoring snapshot")], status: "running" },
    { at: { ms: 700 }, journal: [attemptCreated(0)], tracker: [cellExecuting(0, "4", "KSampler")] },
    { at: { ms: 900 }, tracker: [samplerStep(0, 10)] },
  ],
  terminal: {
    delay: 1400,
    status: "completed",
    journal: [cellCompleted(0), completed(1, 0, 0, 1)],
    tracker: [experimentEvent("experiment.completed")],
  },
};

const slow_queue = {
  kind: "single",
  initialStatus: "queued",
  initialJournal: [started(1)],
  initialTracker: [executionStart(), modalStatus("dispatch", "Dispatching")],
  steps: [
    { at: { ms: 150 }, tracker: [workerStatus(0, "queue", "Queued (position 3)")] },
    { at: { ms: 300 }, tracker: [modalStatus("entry", "Entering entrypoint"), workerStatus(0, "queue", "Queued (position 2)")] },
    { at: { ms: 500 }, tracker: [modalStatus("restore", "Restoring runtime"), progressQueue(1)] },
    { at: { ms: 800 }, tracker: [modalStatus("custom_nodes", "Loading custom nodes"), workerStatus(0, "warmup", "Warming GPU")], status: "running" },
    { at: { ms: 950 }, journal: [attemptCreated(0)], tracker: [cellExecuting(0, "4", "Sampling")] },
  ],
  terminal: {
    delay: 1300,
    status: "completed",
    journal: [cellCompleted(0), completed(1, 0, 0, 1)],
    tracker: [experimentEvent("experiment.completed")],
  },
};

const slow_restore = {
  kind: "single",
  initialStatus: "running",
  initialJournal: [started(1)],
  initialTracker: [executionStart(), modalStatus("dispatch", "Dispatching")],
  steps: [
    { at: { ms: 100 }, tracker: [modalStatus("entry", "Entering entrypoint")] },
    // restore is intentionally LONG (900ms) — the defining feature of this scenario
    { at: { ms: 200 }, tracker: [modalStatus("restore", "Restoring snapshot runtime")] },
    { at: { ms: 1100 }, tracker: [modalStatus("custom_nodes", "Loading custom nodes")] },
    { at: { ms: 1250 }, tracker: [modalStatus("gpu", "Allocating GPU")] },
    { at: { ms: 1400 }, tracker: [modalStatus("warmup", "Warming up")] },
    { at: { ms: 1550 }, tracker: [modalStatus("backend_init", "Initializing backend"), workerStatus(0, "warmup", "Warming")] },
    { at: { ms: 1700 }, tracker: [modalStatus("backend_ready", "Backend ready")] },
    { at: { ms: 1850 }, tracker: [modalStatus("auto_save", "Auto-save configured")] },
    { at: { ms: 1950 }, tracker: [modalStatus("startup", "Startup complete")] },
    { at: { ms: 2050 }, journal: [attemptCreated(0)], tracker: [cellExecuting(0, "4", "KSampler")] },
  ],
  terminal: {
    delay: 2300,
    status: "completed",
    journal: [cellCompleted(0), completed(1, 0, 0, 1)],
    tracker: [experimentEvent("experiment.completed")],
  },
};

const sampler_progress = {
  kind: "single",
  initialStatus: "running",
  initialJournal: [started(1)],
  initialTracker: [executionStart(), workerStatus(0, "warmup", "Warming GPU")],
  steps: [
    { at: { ms: 200 }, journal: [attemptCreated(0)], tracker: [cellExecuting(0, "4", "KSampler")] },
    ...samplerBurst(0, 240, 20, 20, 40),
  ],
  terminal: {
    delay: 1250,
    status: "completed",
    journal: [cellCompleted(0), completed(1, 0, 0, 1)],
    tracker: [experimentEvent("experiment.completed")],
  },
};

// Preview-vs-original family — see CONTRACT NOTE at the top of this file.
const preview_result = {
  kind: "single",
  outputsPerCell: 2, // output_0 = preview, output_1 = original
  initialStatus: "running",
  initialJournal: [started(1)],
  initialTracker: [executionStart(), workerStatus(0, "warmup", "Generating preview")],
  steps: [
    { at: { ms: 200 }, journal: [attemptCreated(0)], tracker: [cellExecuting(0, "4", "Preview pass")] },
    { at: { ms: 350 }, tracker: [samplerStep(0, 8), samplerStep(0, 16)] },
    {
      at: { ms: 500 },
      tracker: [workerStatus(0, "materialize", "Preview generated, materializing original")],
    },
  ],
  terminal: {
    delay: 800,
    status: "completed",
    // Both preview (small, served) and original (full, served) are present.
    journal: [
      cellCompleted(0, {
        outputPaths: ["{output_0}", "{output_1}"],
        previewAssetId: "{preview_asset_0}",
        extra: { output_format: "original", has_preview: true },
      }),
      completed(1, 0, 0, 1),
    ],
    tracker: [experimentEvent("experiment.completed")],
  },
};

const original_result = {
  kind: "single",
  initialStatus: "running",
  initialJournal: [started(1)],
  initialTracker: [executionStart(), workerStatus(0, "warmup", "Warming GPU")],
  steps: [
    { at: { ms: 200 }, journal: [attemptCreated(0)], tracker: [cellExecuting(0, "4", "KSampler")] },
    { at: { ms: 350 }, tracker: [samplerStep(0, 10)] },
  ],
  terminal: {
    delay: 700,
    status: "completed",
    journal: [cellCompleted(0, { extra: { output_format: "original" } }), completed(1, 0, 0, 1)],
    tracker: [experimentEvent("experiment.completed")],
  },
};

const original_rerender_failure = {
  kind: "single",
  outputsPerCell: 2, // output_0 = preview (served), output_1 = original (404)
  initialStatus: "running",
  initialJournal: [started(1)],
  initialTracker: [executionStart(), workerStatus(0, "warmup", "Generating preview")],
  steps: [
    { at: { ms: 200 }, journal: [attemptCreated(0)], tracker: [cellExecuting(0, "4", "Preview pass")] },
    { at: { ms: 400 }, tracker: [samplerStep(0, 12)] },
  ],
  terminal: {
    delay: 750,
    status: "completed",
    journal: [
      cellCompleted(0, {
        outputPaths: ["{output_0}", "{output_1}"],
        previewAssetId: "{preview_asset_0}",
        extra: {
          output_format: "webp_lossless",
          original_render_failed: true,
          original_render_error: "Failed to rerender original output: asset upload timed out",
        },
      }),
      completed(1, 0, 0, 1),
    ],
    tracker: [experimentEvent("experiment.completed")],
  },
  // The original asset and its output file are NOT registered → 404.
  missingAssets: ["{asset_0}", "{output_1}"],
};

const multi_output = {
  kind: "single",
  outputsPerCell: 3,
  initialStatus: "running",
  initialJournal: [started(1)],
  initialTracker: [executionStart(), workerStatus(0, "warmup", "Warming GPU")],
  steps: [
    { at: { ms: 200 }, journal: [attemptCreated(0)], tracker: [cellExecuting(0, "4", "KSampler")] },
    { at: { ms: 380 }, tracker: [samplerStep(0, 12)] },
  ],
  terminal: {
    delay: 650,
    status: "completed",
    journal: [
      cellCompleted(0, { outputPaths: ["{output_0}", "{output_1}", "{output_2}"] }),
      completed(1, 0, 0, 1),
    ],
    tracker: [experimentEvent("experiment.completed")],
  },
};

const out_of_order = {
  kind: "single",
  initialStatus: "running",
  initialJournal: [started(1)],
  initialTracker: [executionStart()],
  steps: [
    // cell.completed journal lands BEFORE sampler progress is dispatched
    { at: { ms: 150 }, journal: [cellCompleted(0)], status: "running" },
    { at: { ms: 300 }, tracker: [cellExecuting(0, "4", "KSampler"), samplerStep(0, 5), samplerStep(0, 10)] },
  ],
  terminal: {
    delay: 450,
    status: "completed",
    journal: [completed(1, 0, 0, 1)],
    tracker: [],
  },
  postTerminalTracker: [
    // worker events arrive AFTER the terminal journal was already polled
    experimentEvent("experiment.completed"),
    samplerStep(0, 15),
    cellExecuting(0, "8", "VAEDecode"),
    modalStatus("startup", "Late startup status"),
  ],
};

const duplicate_progress = {
  kind: "single",
  initialStatus: "running",
  initialJournal: [started(1)],
  initialTracker: [executionStart()],
  steps: [
    { at: { ms: 150 }, journal: [attemptCreated(0)], tracker: [cellExecuting(0, "4", "KSampler")] },
    // identical sampler step emitted twice
    { at: { ms: 300 }, tracker: [samplerStep(0, 10), samplerStep(0, 10)] },
    // identical cell.executing emitted twice
    { at: { ms: 400 }, tracker: [cellExecuting(0, "4", "KSampler")] },
  ],
  terminal: {
    delay: 600,
    status: "completed",
    journal: [cellCompleted(0), cellCompleted(0), completed(1, 0, 0, 1)],
    tracker: [experimentEvent("experiment.completed")],
  },
};

// ── Experiment scenarios ────────────────────────────────────────────────

function experimentDef(cellCount, opts = {}) {
  const def = {
    kind: "experiment",
    cellCount,
    axes: opts.axes,
    initialStatus: "running",
    initialJournal: [created(cellCount, opts.axes), started(cellCount)],
    initialTracker: [executionStart()],
    steps: [],
    terminal: {
      delay: opts.terminalDelay || 700,
      status: opts.terminalStatus || "completed",
      journal: [completed(cellCount - (opts.failedCells || 0), opts.failedCells || 0, 0, cellCount)],
      tracker: [experimentEvent("experiment.completed")],
    },
  };
  for (let i = 0; i < cellCount; i++) {
    const base = 150 + i * (opts.cellGap || 120);
    def.steps.push({ at: { ms: base }, journal: [attemptCreated(i)], tracker: [cellExecuting(i, "4", "KSampler")] });
    def.steps.push({
      at: { ms: base + 80 },
      journal: [cellCompleted(i)],
      tracker: [samplerStep(i, 12)],
    });
  }
  return def;
}

const experiment_two_cell = experimentDef(2, { axes: { seed: ["111", "222"] }, terminalDelay: 700 });

const experiment_large = experimentDef(8, {
  axes: { seed: ["101", "202", "303", "404"], steps: ["12", "24"] },
  cellGap: 100,
  terminalDelay: 1300,
});

const experiment_one_failed_cell = (() => {
  const def = experimentDef(3, { cellGap: 120, terminalDelay: 900, failedCells: 1 });
  // Replace cell_1 completion with a failure
  const steps = def.steps.map((s, idx) => {
    const journal = (s.journal || []).map((ev) => {
      if (ev.type === "cell.completed" && ev.payload && ev.payload.cell_key === "{cell_key_1}") {
        return cellFailed(1, "Cell 1 failed: worker restart exceeded retry budget (3 tries)");
      }
      return ev;
    });
    return Object.assign({}, s, { journal });
  });
  def.steps = steps;
  // Track the failure on the api bus too
  def.steps.push({ at: { ms: 500 }, tracker: [workerFailed(1, "Cell 1 failed: retry budget exceeded")] });
  return def;
})();

const delayed_cells = (() => {
  const def = experimentDef(3, { cellGap: 120, terminalDelay: 3600 });
  // Cells complete at very different times (200ms / 1500ms / 3200ms)
  def.steps = [
    { at: { ms: 150 }, journal: [attemptCreated(0)], tracker: [cellExecuting(0, "4", "KSampler")] },
    { at: { ms: 220 }, journal: [cellCompleted(0)], tracker: [samplerStep(0, 12)] },
    { at: { ms: 1400 }, journal: [attemptCreated(1)], tracker: [cellExecuting(1, "4", "KSampler")] },
    { at: { ms: 1500 }, journal: [cellCompleted(1)], tracker: [samplerStep(1, 12)] },
    { at: { ms: 3100 }, journal: [attemptCreated(2)], tracker: [cellExecuting(2, "4", "KSampler")] },
    { at: { ms: 3200 }, journal: [cellCompleted(2)], tracker: [samplerStep(2, 12)] },
  ];
  return def;
})();

// H8 reopen-compat scenario: same shape as delayed_cells but with completions
// spaced WIDER than the Playground's 3s poll cadence, so a UI observing at
// its natural cadence deterministically sees partial states before the
// terminal (used by the post-H8 legacy-reopen compatibility specs).
const delayed_cells_wide = (() => {
  const def = experimentDef(3, { cellGap: 120, terminalDelay: 12000 });
  def.steps = [
    { at: { ms: 150 }, journal: [attemptCreated(0)], tracker: [cellExecuting(0, "4", "KSampler")] },
    { at: { ms: 300 }, journal: [cellCompleted(0)], tracker: [samplerStep(0, 12)] },
    { at: { ms: 4300 }, journal: [attemptCreated(1)], tracker: [cellExecuting(1, "4", "KSampler")] },
    { at: { ms: 4500 }, journal: [cellCompleted(1)], tracker: [samplerStep(1, 12)] },
    { at: { ms: 8800 }, journal: [attemptCreated(2)], tracker: [cellExecuting(2, "4", "KSampler")] },
    { at: { ms: 9000 }, journal: [cellCompleted(2)], tracker: [samplerStep(2, 12)] },
  ];
  return def;
})();

// ── History seed scenarios (kind:"seed", consumed by seedHistory) ────────

const history_large = {
  kind: "seed",
  seed: {
    count: 300,
    statuses: ["completed", "failed", "cancelled", "in_progress", "queued"],
    imageEvery: 2, // every other record carries an image asset
    presetCount: 4,
    favoriteEvery: 9,
    startOffsetMs: 0,
  },
};

const history_missing_image = {
  kind: "seed",
  seed: {
    count: 40,
    statuses: ["completed", "completed", "failed"],
    imageEvery: 1,
    presetCount: 2,
    // Asset ids referenced by records are intentionally NOT registered → 404.
    // Unique prefix avoids accidental collisions with assets registered by
    // other scenarios/seeds in the same session.
    registerAssets: false,
    assetIdPrefix: "missing_asset_seed_",
  },
};

const history_duplicate_filenames = {
  kind: "seed",
  seed: {
    count: 12,
    statuses: ["completed", "completed", "completed"],
    presetCount: 2,
    // All records share one output filename (registered once).
    sharedOutputFilename: "dupe_shared.png",
    sharedAssetId: "asset_dupe_shared",
  },
};

const history_legacy = {
  kind: "seed",
  seed: {
    count: 25,
    // Only id/status/created_at — no extra, no output, no prompt.
    legacy: true,
  },
};

// History V2 large seed: consumed by seedHistory() via the `v2` flag.
// The engine builds a deterministic 60-generation + 20-experiment dataset
// (ids gen_v2_lg_000..059 / exp_v2_lg_000..019) with spread timestamps,
// mixed statuses, varied workflows/presets, some duration_ms null, some
// preview-only — enough for 3+ mixed pages of 24.
const history_v2_large = {
  kind: "seed",
  v2: "large",
};

// Phase E contract seed. This is fake-only deterministic state: it mirrors the
// History V2 wire shape, while the remote origin is intentionally hidden behind
// the managed History asset URL just as production should do.
const history_v2_phase_e = {
  kind: "seed",
  v2: "phase_e",
};

// Wave-2 fake-only state adds logical-output identity and retained derivative
// provenance. It is not proof that the production projection has landed.
const history_v2_phase_e_wave2 = {
  kind: "seed",
  v2: "phase_e_wave2",
};

// Generate Original (E3B2) decision-matrix seed: one record per frozen route
// outcome (create / active reuse / successful reuse / retry / busy /
// irreproducible) plus an Experiment cell generation for same-Generation
// parity. The route behavior itself lives in fake-backend.mjs.
const history_v2_phase_e_original = {
  kind: "seed",
  v2: "phase_e_original",
};

// F6 Single Resume / Retry-naming seed: one record per durable eligibility
// state of the frozen F1A resume route plus the conditional retry labels.
const history_v2_phase_f6_resume = {
  kind: "seed",
  v2: "phase_f6_resume",
};

// H13 Wave D old-record visibility seed: two migrated-legacy-style
// generations (irreproducible:true; replay_capable absent on one and
// explicitly false on the other; copied workflow_name labels; one WITH a
// retained image, one WITHOUT), one mirrored legacy experiment (copied
// definition labels + cover cells), and one modern generation newer than
// every migrated record.  Consumed by _buildV2Seed(session, "wave_d").
const history_v2_wave_d = {
  kind: "seed",
  v2: "wave_d",
};

export const SCENARIOS = {
  // single-run
  success,
  validation_failure,
  execution_failure,
  canceled,
  interrupted,
  slow_submission,
  slow_queue,
  slow_restore,
  sampler_progress,
  preview_result,
  original_result,
  original_rerender_failure,
  multi_output,
  out_of_order,
  duplicate_progress,
  // experiments
  experiment_two_cell,
  experiment_large,
  experiment_one_failed_cell,
  delayed_cells,
  delayed_cells_wide,
  // history seeds
  history_large,
  history_missing_image,
  history_duplicate_filenames,
  history_legacy,
  history_v2_large,
  history_v2_phase_e,
  history_v2_phase_e_wave2,
  history_v2_phase_e_original,
  history_v2_phase_f6_resume,
  history_v2_wave_d,
};

export const SCENARIO_NAMES = Object.keys(SCENARIOS);

export function getScenario(name) {
  return SCENARIOS[name] || null;
}

export { PNG_META };
