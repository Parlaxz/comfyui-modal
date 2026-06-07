import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const MODAL_PREFIX = "/comfymodal";
const BENCHMARK_WORKFLOW_PATH = "/comfymodal/benchmark/workflow";
const BENCHMARK_WORKFLOW_ROUTE = BENCHMARK_WORKFLOW_PATH;
const STORAGE_KEY_OUTPUT_FORMAT = "comfymodal_output_format";
const STORAGE_KEY_OUTPUT_QUALITY = "comfymodal_quality";
const STORAGE_KEY_OUTPUT_WEBP_LC = "comfymodal_webp_lossless_compression";
const STORAGE_KEY_OUTPUT_AUTOSAVE = "comfymodal_auto_save_local";
const STORAGE_KEY_OUTPUT_SAVEFOLDER = "comfymodal_save_folder";
const STORAGE_KEY_OUTPUT_SIDECAR = "comfymodal_save_metadata_sidecar";

let _originalFetchApi = null;

function log(...args) {
  console.log("[comfyui-modal]", ...args);
}

function _getOutputOptions() {
  if (window._comfyModalOutputOptions && typeof window._comfyModalOutputOptions === "object") {
    return window._comfyModalOutputOptions;
  }
  return {
    output_format: localStorage.getItem(STORAGE_KEY_OUTPUT_FORMAT) || "original",
    quality: parseInt(localStorage.getItem(STORAGE_KEY_OUTPUT_QUALITY), 10) || 75,
    webp_lossless_compression: localStorage.getItem(STORAGE_KEY_OUTPUT_WEBP_LC) || "balanced",
    auto_save_local: localStorage.getItem(STORAGE_KEY_OUTPUT_AUTOSAVE) === "true",
    save_folder: localStorage.getItem(STORAGE_KEY_OUTPUT_SAVEFOLDER) || "ComfyUI/output/modal/",
    save_metadata_sidecar: localStorage.getItem(STORAGE_KEY_OUTPUT_SIDECAR) !== "false",
  };
}

// ─── Progress Bar ────────────────────────────────────────────────────────
// Self-contained progress/status bar that replaces the dependency on
// rgthree's <rgthree-progress-bar>. Uses ComfyUI's native execution events
// plus the custom modal_status event for startup-phase feedback.
//
// Placement:
//   If .comfyui-body-top exists (new ComfyUI frontend), appends there.
//   Otherwise falls back to fixed positioning at the top of the page.
// ─────────────────────────────────────────────────────────────────────────

let _pb = null; // { el, nodesBar, stepsBar, labelEl, container, state }

const PB_STATE = { IDLE: 0, STARTUP: 1, GENERATING: 2, ERROR: 3, DONE: 4 };

function _pbInjectStyles() {
  if (document.getElementById("cm-pb-styles")) return;
  const s = document.createElement("style");
  s.id = "cm-pb-styles";
  s.textContent = `
#cm-pb {
  --cm-pb-h: 16px;
  --cm-pb-font: 10px;
  --cm-pb-bg: rgba(18,18,18,0.92);
  --cm-pb-text: #ccc;
  --cm-pb-node: #2e7d32;
  --cm-pb-step: #1b5e20;
  --cm-pb-startup: #1565c0;
  --cm-pb-error: #b71c1c;
  --cm-pb-done: #2e7d32;

  position: relative;
  z-index: 999;
  height: var(--cm-pb-h);
  font-size: var(--cm-pb-font);
  width: 100%;
  overflow: hidden;
  background: var(--cm-pb-bg);
  box-sizing: border-box;
  display: none;
  font-family: system-ui, -apple-system, sans-serif;
  line-height: var(--cm-pb-h);
  color: var(--cm-pb-text);
  cursor: default;
  transition: opacity 0.25s ease;
}
#cm-pb.-show { display: block; }
#cm-pb.-idle  { display: none; }
#cm-pb.-error { --cm-pb-bg: rgba(30,8,8,0.95); }

#cm-pb .cm-pb-track {
  position: absolute;
  inset: 0;
  display: flex;
  pointer-events: none;
}
#cm-pb .cm-pb-bar {
  position: absolute;
  left: 0; top: 0;
  height: 100%;
  width: 0%;
  transition: width 80ms ease-out;
}
#cm-pb .cm-pb-bar.nodes {
  background: var(--cm-pb-node);
  z-index: 1;
}
#cm-pb .cm-pb-bar.steps {
  background: var(--cm-pb-step);
  z-index: 2;
  opacity: 0.6;
}
#cm-pb .cm-pb-bar.startup {
  background: var(--cm-pb-startup);
  z-index: 1;
  width: 100%;
  animation: cm-pb-pulse 1.6s ease-in-out infinite;
}
#cm-pb .cm-pb-bar.error {
  background: var(--cm-pb-error);
  z-index: 1;
  width: 100%;
  opacity: 0.7;
}
#cm-pb .cm-pb-bar.done {
  background: var(--cm-pb-done);
  z-index: 1;
  width: 100%;
  transition: opacity 0.4s ease;
}
#cm-pb .cm-pb-label {
  position: relative;
  z-index: 3;
  padding: 0 8px;
  height: var(--cm-pb-h);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-shadow: 0 1px 2px rgba(0,0,0,0.8);
  display: flex;
  align-items: center;
  gap: 6px;
}
#cm-pb .cm-pb-label .cm-pb-dot {
  display: inline-block;
  width: 7px; height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
#cm-pb .cm-pb-label .cm-pb-text {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
}
#cm-pb .cm-pb-label .cm-pb-eta {
  flex-shrink: 0;
  opacity: 0.6;
  font-size: 9px;
  font-variant-numeric: tabular-nums;
  min-width: 40px;
  text-align: right;
}
#cm-pb.-fixed {
  position: fixed;
  top: 0; left: 0;
}

@keyframes cm-pb-pulse {
  0%, 100% { opacity: 0.5; }
  50% { opacity: 1; }
}
@keyframes cm-pb-done-flash {
  0% { opacity: 1; }
  70% { opacity: 1; }
  100% { opacity: 0; }
}
`;
  document.head.appendChild(s);
}

function _pbCreate() {
  if (_pb) return;
  _pbInjectStyles();

  const container = document.createElement("div");
  container.id = "cm-pb";

  const track = document.createElement("div");
  track.className = "cm-pb-track";

  const nodesBar = document.createElement("div");
  nodesBar.className = "cm-pb-bar nodes";
  const stepsBar = document.createElement("div");
  stepsBar.className = "cm-pb-bar steps";

  track.appendChild(nodesBar);
  track.appendChild(stepsBar);

  const label = document.createElement("div");
  label.className = "cm-pb-label";

  const dot = document.createElement("span");
  dot.className = "cm-pb-dot";

  const text = document.createElement("span");
  text.className = "cm-pb-text";
  text.textContent = "Idle";

  const eta = document.createElement("span");
  eta.className = "cm-pb-eta";

  label.appendChild(dot);
  label.appendChild(text);
  label.appendChild(eta);
  container.appendChild(track);
  container.appendChild(label);

  const top = document.querySelector(".comfyui-body-top");
  if (top) {
    top.appendChild(container);
  } else {
    container.classList.add("-fixed");
    document.body.appendChild(container);
  }

  _pb = { el: container, nodesBar, stepsBar, labelEl: text, dotEl: dot, etaEl: eta, state: PB_STATE.IDLE };
}

function _pbSetState(state) {
  if (!_pb) return;
  const cls = _pb.el.classList;
  cls.remove("-show", "-idle", "-error");
  _pb.state = state;
  if (state === PB_STATE.IDLE) {
    cls.add("-idle");
  } else {
    cls.add("-show");
  }
}

function _pbShowIdle() {
  if (!_pb) return;
  _pbSetState(PB_STATE.IDLE);
  _pb.nodesBar.style.width = "0%";
  _pb.stepsBar.style.width = "0%";
  _pb.nodesBar.className = "cm-pb-bar nodes";
  _pb.stepsBar.className = "cm-pb-bar steps";
  _pb.labelEl.textContent = "Idle";
  _pb.etaEl.textContent = "";
  _pb.dotEl.style.background = "#666";
}

function _pbShowStartup(message) {
  if (!_pb) return;
  _pbSetState(PB_STATE.STARTUP);
  _pb.nodesBar.className = "cm-pb-bar startup";
  _pb.stepsBar.className = "cm-pb-bar";
  _pb.nodesBar.style.width = "";
  _pb.stepsBar.style.width = "0%";
  _pb.labelEl.textContent = message || "Starting up...";
  _pb.etaEl.textContent = "";
  _pb.dotEl.style.background = "#1565c0";
}

function _pbShowProgress(queue, nodePct, stepPct, nodeLabel, stepLabel) {
  if (!_pb) return;
  _pbSetState(PB_STATE.GENERATING);

  if (nodePct == null) {
    // Indeterminate — no step progress yet (model loading, VAE decode, etc.)
    _pb.nodesBar.className = "cm-pb-bar nodes";
    _pb.nodesBar.style.width = "100%";
    _pb.nodesBar.style.opacity = "0.25";
    _pb.stepsBar.className = "cm-pb-bar steps";
    _pb.stepsBar.style.width = "0%";
  } else {
    _pb.nodesBar.className = "cm-pb-bar nodes";
    _pb.nodesBar.style.opacity = "";
    _pb.nodesBar.style.width = Math.max(0, Math.min(100, nodePct)) + "%";
    _pb.stepsBar.className = "cm-pb-bar steps";
    if (stepPct != null) {
      _pb.stepsBar.style.width = Math.max(0, Math.min(100, stepPct)) + "%";
    } else {
      _pb.stepsBar.style.width = "0%";
    }
  }

  const pct = nodePct != null && nodePct > 0 ? ` ${Math.round(nodePct)}%` : "";
  const queueText = queue > 0 ? `Q:${queue}` : "";
  const nodeText = nodeLabel ? ` ${nodeLabel}` : "";
  const stepText = stepLabel ? ` (${stepLabel})` : "";
  _pb.labelEl.textContent = `${queueText}${nodeText}${stepText}${pct}`.trim() || "Generating...";
  // etaEl is updated live by _startTimer interval — do not touch it here
  _pb.dotEl.style.background = "#2e7d32";
}

function _pbShowError(msg, totalMs) {
  if (!_pb) return;
  _pbSetState(PB_STATE.ERROR);
  _pb.nodesBar.className = "cm-pb-bar error";
  _pb.stepsBar.className = "cm-pb-bar";
  _pb.nodesBar.style.width = "100%";
  _pb.stepsBar.style.width = "0%";
  _pb.labelEl.textContent = msg || "Error";
  _pb.etaEl.textContent = totalMs ? _formatTime(totalMs) : "";
  _pb.dotEl.style.background = "#b71c1c";
}

function _pbShowDone(totalMs, nodeTimes) {
  if (!_pb) return;
  _pbSetState(PB_STATE.DONE);
  _pb.nodesBar.className = "cm-pb-bar done";
  _pb.stepsBar.className = "cm-pb-bar";
  _pb.nodesBar.style.width = "100%";
  _pb.stepsBar.style.width = "0%";

  // Build summary text with total + per-node breakdown
  let summary = `Done  ${_formatTime(totalMs)}`;
  if (nodeTimes && Object.keys(nodeTimes).length > 0) {
    const entries = Object.entries(nodeTimes)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 4);
    const parts = entries.map(([id, dur]) => `${_formatTime(dur)} ${_getNodeLabel(id)}`);
    summary += `  \u00b7  ${parts.join("  \u00b7  ")}`;
  }
  _pb.labelEl.textContent = summary;
  _pb.etaEl.textContent = "";
  _pb.dotEl.style.background = "#2e7d32";
  // Keep everything visible for 10s, then fade out
  _pb.el.style.animation = "none";
  _pb.el.style.opacity = "1";
  setTimeout(() => {
    if (!_pb) return;
    _pb.el.style.transition = "opacity 0.6s ease";
    _pb.el.style.opacity = "0";
    setTimeout(() => {
      if (!_pb) return;
      _pb.el.style.transition = "";
      _pb.el.style.opacity = "";
      _pbShowIdle();
    }, 600);
  }, 10000);
}

// ─── Node label resolution ──────────────────────────────────────────────
function _getNodeLabel(nodeId) {
  try {
    const n = app?.graph?.getNodeById(Number(nodeId));
    if (n) return n.title || n.type;
  } catch {}
  return String(nodeId);
}

// ─── Live timing ────────────────────────────────────────────────────────
function _formatTime(ms) {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  const m = Math.floor(ms / 60000);
  const s = (ms % 60000) / 1000;
  return `${m}m ${s.toFixed(0)}s`;
}

function _startTimer() {
  _stopTimer();
  _execState.timerInterval = setInterval(() => {
    if (!_execState.startTime || !_pb) return;
    const now = Date.now();
    _execState.totalMs = now - _execState.startTime;
    _execState.nodeMs = _execState.nodeStartTime ? now - _execState.nodeStartTime : 0;
    // Update timing display — doesn't touch labelEl which shows progress
    let t = _formatTime(_execState.totalMs);
    if (_execState.nodeMs > 0) {
      t += ` \u00b7 ${_formatTime(_execState.nodeMs)}`;
    }
    _pb.etaEl.textContent = t;
  }, 100);
}

function _stopTimer() {
  if (_execState.timerInterval) {
    clearInterval(_execState.timerInterval);
    _execState.timerInterval = null;
  }
}

// Track current execution state
let _execState = {
  executing: false, nodesSeen: new Set(),
  currentNode: null, step: 0, maxStep: 0, queue: 0,
  startTime: null,         // Date.now() when execution_start fires
  nodeStartTime: null,     // Date.now() when executing(node) fires
  nodeTimes: {},           // { [nodeId]: durationMs } per-node wall-clock
  totalMs: 0, nodeMs: 0,
  totalNodes: 0,           // set from intercepted prompt payload
  timerInterval: null,
};

function _resetExecState() {
  _stopTimer();
  _execState = {
    executing: false, nodesSeen: new Set(),
    currentNode: null, step: 0, maxStep: 0, queue: 0,
    startTime: null, nodeStartTime: null,
    nodeTimes: {},
    totalMs: 0, nodeMs: 0,
    totalNodes: _execState.totalNodes || 0,
    timerInterval: null,
  };
}

// t0 (browser pressed Generate).  We capture both monotonic
// (performance.now) and wall-clock (Date.now) so the server side can
// align timestamps even when there is no shared clock.
function _captureT0() {
  const perfMs = performance.now();
  const dateMs = Date.now();
  return {
    t0_perf_ms: perfMs,
    t0_perf_now_ms: dateMs,
    t0_client_press_ms: dateMs,
  };
}

function _logTrace(trace, suffix = "") {
  if (!trace || !trace.deltas_ms) return;
  const d = trace.deltas_ms;
  const summary = [
    `t0→t1=${d.t0_to_t1 ?? "?"}ms`,
    `t1→t2=${d.t1_to_t2 ?? "?"}ms`,
    `t2→t3=${d.t2_to_t3 ?? "?"}ms`,
    `cold=${d.t2_to_t3 ?? "?"}ms`,
    `validate=${d.t3_to_t3b ?? "?"}ms`,
    `clip_load=${d.clip_load ?? "?"}ms`,
    `clip_encode=${d.clip_encode ?? "?"}ms`,
    `sampler=${d.sampler ?? "?"}ms`,
    `vae_decode=${d.vae_decode ?? "?"}ms`,
    `image_io=${d.image_io ?? "?"}ms`,
    `graph_overhead=${d.graph_overhead ?? "?"}ms`,
    `inference_total=${d.inference_total ?? "?"}ms`,
    `t9→t10=${d.t9_to_t10 ?? "?"}ms`,
    `total=${d.modal_to_browser ?? "?"}ms`,
  ].join(" ");
  console.log(
    `[comfyui-modal.timing] prompt=${trace.prompt_id || "-"} ${summary}${suffix}`
  );
}

async function _saveBenchmarkWorkflow(payload) {
  if (!_originalFetchApi || !payload || typeof payload !== "object") {
    return;
  }
  try {
    await _originalFetchApi(BENCHMARK_WORKFLOW_ROUTE, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
  } catch {
    // Silent by design: benchmark snapshot capture must never block or
    // visibly affect the normal generate flow.
  }
}

app.registerExtension({
  name: "comfyui.modal",

  async setup() {
    log("Extension loaded. Setting up progress bar & patching fetchApi...");

    // ── Progress Bar ────────────────────────────────────────────────────
    _pbCreate();

    if (typeof api.addEventListener === "function") {
      api.addEventListener("execution_start", () => {
        // The Modal container streams execution_start through its progress
        // queue too, so this can fire twice.  Guard against re-entry.
        if (_execState.executing) return;
        _resetExecState();
        _execState.executing = true;
        _execState.startTime = Date.now();
        _startTimer();
      });

      api.addEventListener("executing", (e) => {
        // ComfyUI frontend API passes nodeId directly as e.detail, NOT
        // wrapped in {node: ...}.  Accept both shapes for compatibility.
        const detail = e?.detail;
        const node = (detail != null && typeof detail === "object") ? detail.node : detail;
        if (node === null || node === undefined) {
          return;
        }
        // Record previous node's wall-clock duration before switching
        if (_execState.currentNode != null && _execState.nodeStartTime) {
          const prevDur = Date.now() - _execState.nodeStartTime;
          _execState.nodeTimes[String(_execState.currentNode)] = prevDur;
        }
        _execState.currentNode = node;
        _execState.nodeStartTime = Date.now();
        _execState.nodeMs = 0;
        // Show node label + node-level progress while we wait for step data
        const nodeLabel = _getNodeLabel(node);
        const doneCount = _execState.nodesSeen.size;
        const total = _execState.totalNodes;
        const nodePct = total > 0 ? (doneCount / total) * 100 : null;
        _pbShowProgress(
          _execState.queue,
          nodePct,
          null,
          nodeLabel,
          total > 0 ? `${doneCount}/${total}` : ""
        );
        // Reset step counter — the new node hasn't started its steps yet
        _execState.step = 0;
        _execState.maxStep = 0;
      });

      api.addEventListener("progress", (e) => {
        const d = e?.detail || {};
        // ComfyUI sends this field as `value`, not `step`. Accept both.
        if (d.step != null || d.value != null) {
          _execState.step = d.step ?? d.value;
          _execState.maxStep = d.max ?? d.max_step ?? d.maxStep ?? _execState.maxStep;
        }
        if (d.queue != null) _execState.queue = d.queue;
        if (_execState.executing) {
          const hasSteps = _execState.maxStep > 0 && _execState.step != null;
          const pct = hasSteps ? (_execState.step / _execState.maxStep) * 100 : null;
          const label = _getNodeLabel(_execState.currentNode);
          _pbShowProgress(
            _execState.queue,
            pct,
            pct,
            label,
            hasSteps ? `${_execState.step}/${_execState.maxStep}` : ""
          );
        }
      });

      api.addEventListener("execution_cached", (e) => {
        const nodes = e?.detail?.nodes;
        if (Array.isArray(nodes)) {
          for (const n of nodes) _execState.nodesSeen.add(n);
        }
      });

      api.addEventListener("execution_success", (event) => {
        _execState.executing = false;
        _stopTimer();
        const total = _execState.totalMs || (_execState.startTime ? Date.now() - _execState.startTime : 0);
        const finalNodeTimes = { ..._execState.nodeTimes };
        // Include current node's time if still running
        if (_execState.currentNode != null && _execState.nodeStartTime) {
          finalNodeTimes[String(_execState.currentNode)] = Date.now() - _execState.nodeStartTime;
        }
        _pbShowDone(total, finalNodeTimes);
        _resetExecState();

        const detail = event?.detail || {};
        const trace = detail.trace;
        if (!trace) return;
        const t10ClientMs = Date.now();
        const suffix = ` client_event_recv_ms=${t10ClientMs}`;
        _logTrace(trace, suffix);
      });

      api.addEventListener("execution_error", (e) => {
        _execState.executing = false;
        _stopTimer();
        const total = _execState.totalMs || (_execState.startTime ? Date.now() - _execState.startTime : 0);
        const msg = e?.detail?.message || "Execution error";
        _pbShowError(msg, total);
        _resetExecState();
        setTimeout(() => _pbShowIdle(), 4000);
      });

      api.addEventListener("modal_status", (e) => {
        const d = e?.detail || {};
        if (!d.prompt_id) return;
        if (d.phase === "startup" || d.phase === "warmup") {
          _pbShowStartup(d.message || "Starting up...");
        }
      });
    } else {
      log("WARNING: api.addEventListener not available, progress bar disabled");
    }

    // ── End Progress Bar ────────────────────────────────────────────────

    _originalFetchApi = api.fetchApi.bind(api);
    api.fetchApi = async function (route, options = {}) {
      const isPromptPost =
        options.method === "POST" &&
        (route === "/prompt" || route === "prompt");

      if (isPromptPost) {
        const enabled = window._comfyModalEnabled !== false;
        if (!enabled) {
          return _originalFetchApi(route, options);
        }
        // ── t0: browser pressed Generate.  Inject both into the
        // body so the local server can re-stamp t1/t2 and the Modal
        // server can re-stamp t3..t9.
        const t0 = _captureT0();
        log(
          `Intercepted /prompt POST -> routing to Modal GPU (t0_perf_ms=${t0.t0_perf_ms.toFixed(1)})`
        );
        const body = options.body;
        let parsed;
        try {
          parsed = typeof body === "string" ? JSON.parse(body) : body;
        } catch {
          parsed = null;
        }
        if (parsed && typeof parsed === "object") {
          parsed.t0_perf_ms = t0.t0_perf_ms;
          parsed.t0_perf_now_ms = t0.t0_perf_now_ms;
          parsed.t0_client_press_ms = t0.t0_client_press_ms;
          parsed.modal_options = _getOutputOptions();
          options = {
            ...options,
            body: JSON.stringify(parsed),
          };
          void _saveBenchmarkWorkflow(parsed);
          // Count total execution nodes from the prompt payload
          const nodeMap = parsed.prompt || parsed.output || parsed;
          if (nodeMap && typeof nodeMap === "object") {
            const nodeKeys = Object.keys(nodeMap).filter(k => {
              const v = nodeMap[k];
              return v && typeof v === "object" && v.class_type;
            });
            if (nodeKeys.length > 0) {
              _execState.totalNodes = nodeKeys.length;
            }
          }
        }
        return _originalFetchApi(`${MODAL_PREFIX}/prompt`, options);
      }

      if (
        options.method === "POST" &&
        (route === "/model/install" || route === "model/install")
      ) {
        log("Intercepted model/install -> routing to Modal Volume download");
        return _originalFetchApi(`${MODAL_PREFIX}/model/install`, options);
      }

      return _originalFetchApi(route, options);
    };

    log("fetchApi patched. All /prompt POST requests -> Modal GPU.");
  },
});
