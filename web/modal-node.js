import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { initSharedTracker, getSharedTracker, setNodeLabelResolver } from "./comfymodal-progress.js";

const MODAL_PREFIX = "/comfymodal";
const BENCHMARK_WORKFLOW_PATH = "/comfymodal/benchmark/workflow";
const BENCHMARK_WORKFLOW_ROUTE = BENCHMARK_WORKFLOW_PATH;
const STORAGE_KEY_OUTPUT_FORMAT = "comfymodal_output_format";
const STORAGE_KEY_OUTPUT_QUALITY = "comfymodal_quality";
const STORAGE_KEY_OUTPUT_WEBP_LC = "comfymodal_webp_lossless_compression";
const STORAGE_KEY_OUTPUT_AUTOSAVE = "comfymodal_auto_save_local";
const STORAGE_KEY_OUTPUT_SAVEFOLDER = "comfymodal_save_folder";
const STORAGE_KEY_OUTPUT_SIDECAR = "comfymodal_save_metadata_sidecar";
const DEFAULT_OUTPUT_SAVEFOLDER = "output/modal";

let _originalFetchApi = null;
const _modalNodeRuntime = {
  installed: false,
  listenerRemovers: [],
  fetchApiPatch: null,
};

function log(...args) {
  console.log("[comfyui-modal]", ...args);
}

function _normalizeOutputSaveFolder(savedFolder) {
  const normalized = String(savedFolder || "")
    .replace(/\\/g, "/")
    .replace(/^\.?\//, "")
    .replace(/\/+$/, "");
  if (!normalized) {
    return DEFAULT_OUTPUT_SAVEFOLDER;
  }
  if (normalized.toLowerCase() === "comfyui/output/modal") {
    return DEFAULT_OUTPUT_SAVEFOLDER;
  }
  return normalized;
}

function _readOutputSaveFolder() {
  const savedFolder = localStorage.getItem(STORAGE_KEY_OUTPUT_SAVEFOLDER);
  const normalized = _normalizeOutputSaveFolder(savedFolder);
  if (savedFolder !== normalized) {
    localStorage.setItem(STORAGE_KEY_OUTPUT_SAVEFOLDER, normalized);
  }
  return normalized;
}

function _trackApiListener(eventName, handler) {
  if (typeof api?.addEventListener !== "function") {
    return;
  }
  api.addEventListener(eventName, handler);
  _modalNodeRuntime.listenerRemovers.push(() => {
    if (typeof api.removeEventListener === "function") {
      api.removeEventListener(eventName, handler);
    }
  });
}

function _disposeModalNodeRuntime() {
  while (_modalNodeRuntime.listenerRemovers.length) {
    const dispose = _modalNodeRuntime.listenerRemovers.pop();
    try {
      dispose();
    } catch {}
  }
  if (_originalFetchApi && api?.fetchApi === _modalNodeRuntime.fetchApiPatch) {
    api.fetchApi = _originalFetchApi;
  }
  _modalNodeRuntime.fetchApiPatch = null;
  _modalNodeRuntime.installed = false;
}

function _getOutputOptions() {
  if (window._comfyModalOutputOptions && typeof window._comfyModalOutputOptions === "object") {
    if (window._comfyModalOutputOptions.save_folder !== undefined) {
      window._comfyModalOutputOptions.save_folder = _normalizeOutputSaveFolder(
        window._comfyModalOutputOptions.save_folder
      );
    }
    return window._comfyModalOutputOptions;
  }
  return {
    output_format: localStorage.getItem(STORAGE_KEY_OUTPUT_FORMAT) || "original",
    quality: parseInt(localStorage.getItem(STORAGE_KEY_OUTPUT_QUALITY), 10) || 75,
    webp_lossless_compression: localStorage.getItem(STORAGE_KEY_OUTPUT_WEBP_LC) || "balanced",
    auto_save_local: localStorage.getItem(STORAGE_KEY_OUTPUT_AUTOSAVE) === "true",
    save_folder: _readOutputSaveFolder(),
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
    _disposeModalNodeRuntime();

    // ── Progress Bar ────────────────────────────────────────────────────
    _pbCreate();

    // Set up node label resolver so shared progress module can resolve labels
    setNodeLabelResolver(function (nodeId) {
      try {
        const n = app?.graph?.getNodeById(Number(nodeId));
        if (n) return n.title || n.type;
      } catch {}
      return String(nodeId);
    });

    // Create shared progress tracker (singleton, safe for both modal-node and playground)
    const tracker = initSharedTracker(api);
    // Store reference for _execState interactions
    _modalNodeRuntime._tracker = tracker;

    // Subscribe tracker state to progress bar updates
    tracker.onProgress(function (s) {
      if (!_pb) return;

      switch (s.stage) {
        case "idle":
          _pbShowIdle();
          break;
        case "startup":
          _pbShowStartup(s.message || "Starting up...");
          break;
        case "generating":
          _pbShowProgress(
            s.queuePosition,
            s.overallPercent,
            s.samplerPercent,
            s.currentNodeLabel,
            s.totalNodes > 0 ? `${s.completedNodes}/${s.totalNodes}` : ""
          );
          break;
        case "done": {
          const finalNodeTimes = { ...s.perNodeDurations };
          _pbShowDone(s.elapsedMs, finalNodeTimes);
          break;
        }
        case "error":
          _pbShowError(s.error, s.elapsedMs);
          break;
      }

      // Update timing display in the bar
      if (s.stage === "generating" && s.startTime) {
        const elapsed = Date.now() - s.startTime;
        let t = _formatTime(elapsed);
        _pb.etaEl.textContent = t;
      }
    });

    // ── Legacy _execState bridge ────────────────────────────────────────
    // Keep _execState populated for downstream consumers that reference it
    // (e.g., fetchApi path for totalNodes counting)
    tracker.onProgress(function (s) {
      _execState.executing = s.stage === "generating" || s.stage === "startup";
      _execState.queue = s.queuePosition;
      _execState.totalNodes = s.totalNodes;
      _execState.currentNode = s.currentNodeId;
      _execState.nodeTimes = { ...s.perNodeDurations };
      _execState.totalMs = s.elapsedMs;
      _execState.startTime = s.startTime;
    });

    // ── End Progress Bar ────────────────────────────────────────────────

    _originalFetchApi = api.fetchApi.bind(api);
    const patchedFetchApi = async function (route, options = {}) {
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
          const baseOptions = { ..._getOutputOptions() };
          delete baseOptions.production;  // ensure clean start
          const productionEnabled = _getProductionEnabled();
          if (productionEnabled) {
            const prodOutputNodes = _getProdOutputNodes();
            if (prodOutputNodes.length === 0) {
              throw new Error("Simulate Production is enabled but no nodes are marked as Production Output. Right-click an output-capable node and select 'Mark as Production Output', or disable Simulate Production.");
            }
            const outputNodeIds = prodOutputNodes.map(n => String(n.id)).sort();
            // Validate output_node_ids exist in the serialized prompt keys
            const serializedKeys = parsed.prompt ? Object.keys(parsed.prompt) : [];
            const finalOutIds = serializedKeys.length > 0
              ? outputNodeIds.filter(id => serializedKeys.includes(id))
              : outputNodeIds;
            if (serializedKeys.length > 0 && finalOutIds.length === 0 && outputNodeIds.length > 0) {
              log("Production output node IDs not found in serialized prompt: " + outputNodeIds.join(", ") + ". Available keys: " + serializedKeys.join(", "));
              throw new Error("Production output nodes not found in serialized prompt. The canvas node IDs do not match the serialized workflow. Try re-saving the workflow or re-marking production outputs.");
            }
            if (finalOutIds.length < outputNodeIds.length) {
              const missing = outputNodeIds.filter(id => !serializedKeys.includes(id));
              throw new Error(
                "Production output nodes not found in serialized prompt: " + missing.join(", ") +
                ". Node IDs in canvas do not match serialized workflow. Re-save workflow or re-mark production outputs."
              );
            }
            baseOptions.production = {
              enabled: true,
              schema_version: 1,
              output_node_ids: finalOutIds,
              disable_sampler_previews: true,
              quiet_execution_logs: true,
              progress_min_interval_ms: 500,
              strict_output_collection: true,
              direct_output_sink: true,
              metadata_mode: "none",
              return_comparison_a: false
            };
          }
          parsed.modal_options = { ...(parsed.modal_options || {}), ...baseOptions };
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
              // Update shared tracker too
              if (_modalNodeRuntime._tracker && typeof _modalNodeRuntime._tracker.setTotalNodes === "function") {
                _modalNodeRuntime._tracker.setTotalNodes(nodeKeys.length);
              }
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
    api.fetchApi = patchedFetchApi;
    _modalNodeRuntime.fetchApiPatch = patchedFetchApi;
    _modalNodeRuntime.installed = true;

    log("fetchApi patched. All /prompt POST requests -> Modal GPU.");
  },
});

// ═══════════════════════════════════════════════════════════════════════════
// PRODUCTION MODE EXTENSION (Phase 2)
// ═══════════════════════════════════════════════════════════════════════════

const _OUTPUT_CAPABLE_CLASSES = new Set([
    "SaveImage", "PreviewImage", "SaveImageWithMetaData",
    "VHS_VideoCombine", "SaveAnimatedWEBP", "SaveAnimatedPNG",
    "Image Comparer (rgthree)",
]);

function _isOutputCapable(node) {
    if (!node || !node.type) return false;
    return _OUTPUT_CAPABLE_CLASSES.has(node.type);
}

function _getProductionEnabled() {
  return !!(app.graph?.extra?.comfymodal?.production_mode_enabled);
}

function _getCloudModeEnabled() {
  return window._comfyModalEnabled !== false;
}

function _getProdOutputNodes() {
  const result = [];
  if (!app.graph) return result;
  for (const node of app.graph._nodes) {
    if (node.properties?.comfymodal_production_output) {
      result.push(node);
    }
  }
  return result;
}

function _getBypassNodes() {
  const result = [];
  if (!app.graph) return result;
  for (const node of app.graph._nodes) {
    if (node.properties?.comfymodal_bypass_in_production) {
      result.push(node);
    }
  }
  return result;
}

function _showNodeSelector(candidates) {
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.style.cssText = "position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.7);z-index:99999;display:flex;align-items:center;justify-content:center;";
    const box = document.createElement("div");
    box.style.cssText = "background:#1e1e2e;border:1px solid #444;border-radius:8px;padding:24px;max-width:500px;width:90%;max-height:80vh;display:flex;flex-direction:column;";
    const titleEl = document.createElement("div");
    titleEl.style.cssText = "color:#ddd;font-size:15px;font-weight:600;margin-bottom:12px;";
    titleEl.textContent = "Select Production Output Nodes";
    const descEl = document.createElement("div");
    descEl.style.cssText = "color:#888;font-size:12px;margin-bottom:16px;line-height:1.5;";
    descEl.textContent = "At least one output-capable node must be marked as a production output. Select the nodes that should produce the final output:";
    const list = document.createElement("div");
    list.style.cssText = "flex:1;overflow-y:auto;display:flex;flex-direction:column;gap:4px;margin-bottom:16px;";
    const selected = new Set();
    for (const node of candidates) {
      const row = document.createElement("label");
      row.style.cssText = "display:flex;align-items:center;gap:8px;padding:6px 8px;background:#2a2a2a;border-radius:4px;cursor:pointer;";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.style.cssText = "width:16px;height:16px;accent-color:#3a6fcc;flex-shrink:0;";
      cb.addEventListener("change", () => {
        if (cb.checked) selected.add(node);
        else selected.delete(node);
      });
      const label = document.createElement("span");
      label.style.cssText = "font-size:12px;color:#ddd;flex:1;";
      label.textContent = `#${node.id} ${node.title || node.type} (${node.type || "?"})`;
      row.appendChild(cb);
      row.appendChild(label);
      list.appendChild(row);
    }
    const btnRow = document.createElement("div");
    btnRow.style.cssText = "display:flex;gap:8px;justify-content:flex-end;";
    const cancelBtn = document.createElement("button");
    cancelBtn.textContent = "Cancel";
    cancelBtn.style.cssText = "background:transparent;border:1px solid #555;color:#aaa;padding:6px 16px;border-radius:4px;cursor:pointer;font-size:13px;";
    const confirmBtn = document.createElement("button");
    confirmBtn.textContent = "Confirm";
    confirmBtn.style.cssText = "background:#3a6fcc;border:none;color:#fff;padding:6px 16px;border-radius:4px;cursor:pointer;font-size:13px;";
    function close(result) { overlay.remove(); document.removeEventListener("keydown", escHandler); resolve(result); }
    const escHandler = (e) => { if (e.key === "Escape") close([]); };
    document.addEventListener("keydown", escHandler);
    overlay.addEventListener("click", (e) => { if (e.target === overlay) close([]); });
    cancelBtn.onclick = () => close([]);
    confirmBtn.onclick = () => {
      if (selected.size === 0) return;
      close(Array.from(selected));
    };
    btnRow.appendChild(cancelBtn);
    btnRow.appendChild(confirmBtn);
    box.appendChild(titleEl);
    box.appendChild(descEl);
    box.appendChild(list);
    box.appendChild(btnRow);
    overlay.appendChild(box);
    document.body.appendChild(overlay);
  });
}

function _computeProductionSummary() {
  const graph = app.graph;
  if (!graph) return null;
  const outputNodes = _getProdOutputNodes();
  const bypassNodes = _getBypassNodes();
  const allNodes = graph._nodes || [];
  const outputIds = new Set(outputNodes.map(n => String(n.id)));
  const bypassIds = new Set(bypassNodes.map(n => String(n.id)));
  const kept = allNodes.filter(n => !bypassIds.has(String(n.id))).length;
  const removed = 0;
  const bypassed = bypassNodes.length;
  return {
    kept,
    removed,
    bypassed,
    outputs: outputNodes.length,
    outputIds: Array.from(outputIds).sort(),
    bypassIds: Array.from(bypassIds).sort(),
    samplerPreviews: "disabled",
    directOutputs: outputNodes.length,
  };
}

app.registerExtension({
  name: "comfyui.modal.production",

  async beforeRegisterNodeDef(nodeType, nodeData) {

    // ── Context menu ──
    const origGetExtraMenuOptions = nodeType.prototype.getExtraMenuOptions;
    nodeType.prototype.getExtraMenuOptions = function(_, options) {
      if (origGetExtraMenuOptions) {
        origGetExtraMenuOptions.call(this, _, options);
      }
      const isMarked = !!this.properties?.comfymodal_production_output;
      options.push(null);
      if (isMarked) {
          options.push({
            content: "Unmark Production Output",
            callback: () => {
              this.properties.comfymodal_production_output = false;
              app.graph.setDirtyCanvas(true, true);
            },
          });
        } else {
          options.push({
            content: "Mark as Production Output",
            callback: () => {
              if (!this.properties) this.properties = {};
              this.properties.comfymodal_production_output = true;
              app.graph.setDirtyCanvas(true, true);
            },
          });
        }
      const isBypassMarked = !!this.properties?.comfymodal_bypass_in_production;
      options.push(null);
      if (isBypassMarked) {
        options.push({
          content: "Do Not Bypass in Production",
          callback: () => {
            this.properties.comfymodal_bypass_in_production = false;
            app.graph.setDirtyCanvas(true, true);
          },
        });
      } else {
        options.push({
          content: "Bypass in Production",
          callback: () => {
            if (!this.properties) this.properties = {};
            this.properties.comfymodal_bypass_in_production = true;
            app.graph.setDirtyCanvas(true, true);
          },
        });
      }
    };

  },

  async setup() {
    log("Production mode extension loaded.");
  },
});
