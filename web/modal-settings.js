import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const MODAL_PREFIX = "/comfymodal";

// Sections shown in the Models panel (order matters).
// "checkpoints" groups: checkpoints/ + diffusion_models/ + unet/
const FOLDERS = ["checkpoints", "loras", "vae", "controlnet", "upscale_models", "embeddings", "clip", "text_encoders"];

// Folders available in the "Add Model" download dropdown
const DOWNLOAD_FOLDERS = [
  "checkpoints",
  "diffusion_models",
  "unet",
  "loras",
  "vae",
  "controlnet",
  "upscale_models",
  "embeddings",
  "clip",
  "text_encoders",
  "model_patches",
  "clip_vision",
  "style_models",
  "vae_approx",
  "hypernetworks",
  "gligen",
  "photomaker",
  "latent_upscale_models",
  "audio_encoders",
  "frame_interpolation",
];

const STORAGE_KEY_GPU    = "comfymodal_gpu";
const STORAGE_KEY_ENABLED = "comfymodal_enabled";
const STORAGE_KEY_OUTPUT_FORMAT = "comfymodal_output_format";
const STORAGE_KEY_OUTPUT_QUALITY = "comfymodal_quality";
const STORAGE_KEY_OUTPUT_WEBP_LC = "comfymodal_webp_lossless_compression";
const STORAGE_KEY_OUTPUT_AUTOSAVE = "comfymodal_auto_save_local";
const STORAGE_KEY_OUTPUT_SAVEFOLDER = "comfymodal_save_folder";
const STORAGE_KEY_OUTPUT_SIDECAR = "comfymodal_save_metadata_sidecar";
const STORAGE_KEY_PRODUCTION = "comfymodal_production";
const DEFAULT_OUTPUT_SAVEFOLDER = "output/modal";

const STATUS = {
  UNKNOWN:    "unknown",
  CHECKING:   "checking",
  STARTING:   "starting",
  ONLINE:     "online",
  OFFLINE:    "offline",
  GENERATING: "generating",
};

let currentStatus = STATUS.UNKNOWN;
let dotEl = null;
let statusEl = null;
let modelListEl = null;
let modelsCollapsibleRef = null;
let injectAllBtn = null;
let statusBannerEl = null;
let statusBannerTextEl = null;
let _deployPollTimer = null;
let _deployState = "idle";
let _hasChanges = false;
let _deployWarning = "";
let _runtimeStatusText = "";
let _runtimeStatusPhase = "";
let _deployLogTimer = null;
let _deployLogInlineEl = null;
let _deployLogPreEl = null;
let _deploySuccessTimer = null;
let _prevDeployState = "idle";
let _showDeploySuccess = false;
let _logViewerMinimized = false;
let _showLogLinkEl = null;

// Transient production-plan evidence (last known from execution_success)
let _lastProductionEvidence = null;

// Download progress tracking
let _downloadProgressEl = null;
let _downloadProgressTrackEl = null;
let _downloadProgressPctEl = null;
let _downloadProgressInfoEl = null;
let _downloadPollTimer = null;
let _activeDownloadId = null;

const STATUS_STYLE = {
  [STATUS.UNKNOWN]:    { color: "#888",    label: "Unknown" },
  [STATUS.CHECKING]:   { color: "#f5a623", label: "Checking..." },
  [STATUS.STARTING]:   { color: "#6a9fd8", label: "Starting up" },
  [STATUS.ONLINE]:     { color: "#7ed321", label: "Ready (container running)" },
  [STATUS.OFFLINE]:    { color: "#888",    label: "Sleeping (will wake on use)" },
  [STATUS.GENERATING]: { color: "#4a90e2", label: "Generating..." },
};

function setGpuOptions(selectEl, options) {
  selectEl.innerHTML = "";
  for (const opt of options) {
    const el = document.createElement("option");
    el.value = opt.value;
    el.textContent = opt.label;
    selectEl.appendChild(el);
  }
}

function pickInitialGpu(config, storedGpu) {
  const values = new Set((config.available_gpus || []).map((opt) => opt.value));
  if (storedGpu && values.has(storedGpu)) return storedGpu;
  return config.gpu || config.default_gpu || "rtx-pro-6000";
}

// Sync GPU config on page load (used by setup() and buildPanel())
async function syncGpuConfig() {
  let config = { gpu: "rtx-pro-6000", default_gpu: "rtx-pro-6000", available_gpus: [] };
  try {
    const response = await api.fetchApi(`${MODAL_PREFIX}/config`);
    config = await response.json();
  } catch {}

  const storedGpu = localStorage.getItem(STORAGE_KEY_GPU) || "";
  const options = Array.isArray(config.available_gpus) ? config.available_gpus : [];
  const selectedGpu = pickInitialGpu(config, storedGpu);

  localStorage.setItem(STORAGE_KEY_GPU, selectedGpu);
  window._comfyModalGpu = selectedGpu;

  try {
    await api.fetchApi(`${MODAL_PREFIX}/config`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ gpu: selectedGpu }),
    });
  } catch {}

  return { config, selectedGpu, options };
}

function normalizeOutputSaveFolder(savedFolder) {
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

async function syncOutputOptions() {
  let config = {
    output_format: "original",
    quality: 75,
    webp_lossless_compression: "balanced",
    auto_save_local: false,
    save_folder: DEFAULT_OUTPUT_SAVEFOLDER,
    save_metadata_sidecar: true,
  };
  try {
    const response = await api.fetchApi(`${MODAL_PREFIX}/config`);
    config = { ...config, ...(await response.json()) };
  } catch {}

  const savedFolder = localStorage.getItem(STORAGE_KEY_OUTPUT_SAVEFOLDER);
  const migratedSavedFolder = normalizeOutputSaveFolder(savedFolder);
  if (savedFolder !== migratedSavedFolder) {
    localStorage.setItem(STORAGE_KEY_OUTPUT_SAVEFOLDER, migratedSavedFolder);
  }

  const outputOptions = {
    output_format: localStorage.getItem(STORAGE_KEY_OUTPUT_FORMAT) || config.output_format || "original",
    quality: parseInt(localStorage.getItem(STORAGE_KEY_OUTPUT_QUALITY), 10) || config.quality || 75,
    webp_lossless_compression: localStorage.getItem(STORAGE_KEY_OUTPUT_WEBP_LC) || config.webp_lossless_compression || "balanced",
    auto_save_local: localStorage.getItem(STORAGE_KEY_OUTPUT_AUTOSAVE) === "true"
      ? true
      : (config.auto_save_local === true),
    save_folder: migratedSavedFolder || normalizeOutputSaveFolder(config.save_folder),
    save_metadata_sidecar: localStorage.getItem(STORAGE_KEY_OUTPUT_SIDECAR) === "false"
      ? false
      : (config.save_metadata_sidecar !== false),
  };

  localStorage.setItem(STORAGE_KEY_OUTPUT_FORMAT, outputOptions.output_format);
  localStorage.setItem(STORAGE_KEY_OUTPUT_QUALITY, String(outputOptions.quality));
  localStorage.setItem(STORAGE_KEY_OUTPUT_WEBP_LC, outputOptions.webp_lossless_compression);
  localStorage.setItem(STORAGE_KEY_OUTPUT_AUTOSAVE, String(outputOptions.auto_save_local));
  localStorage.setItem(STORAGE_KEY_OUTPUT_SAVEFOLDER, outputOptions.save_folder);
  localStorage.setItem(STORAGE_KEY_OUTPUT_SIDECAR, String(outputOptions.save_metadata_sidecar));
  window._comfyModalOutputOptions = outputOptions;

  return outputOptions;
}

// --- Status Banner Logic ---
function updateStatusBanner() {
  if (!statusBannerEl || !statusBannerTextEl) return;
  let text = "";
  let bg = "#2a2a2a";
  let color = "#aaa";
  let animation = "";

  if (_showDeploySuccess) {
    text = "\u2713 Deploy succeeded";
    bg = "#1a5a1a";
    color = "#7ed321";
    animation = "successPulse 0.6s ease-in-out 2";
  } else if (_deployState === "deploying") {
    text = "Deploying...";
    bg = "#3d2e00";
    color = "#f5a623";
    animation = "statusPulse 1.5s ease-in-out infinite";
  } else if (_deployState === "error") {
    text = "Error";
    bg = "#3d1010";
    color = "#e05050";
  } else if (_hasChanges) {
    text = "Deploy needed";
    bg = "#3d2e00";
    color = "#f5a623";
  } else if (_deployState === "ready" && _deployWarning) {
    text = _deployWarning;
    bg = "#3d2e00";
    color = "#f5a623";
  } else if (_runtimeStatusText) {
    text = _runtimeStatusText;
    bg = _runtimeStatusPhase === "warmup" ? "#1b2438" : "#1a2a3a";
    color = "#6a9fd8";
    animation = "statusPulse 1.5s ease-in-out infinite";
  } else if (currentStatus === STATUS.ONLINE) {
    text = "Ready to generate";
    bg = "#1a3a1a";
    color = "#7ed321";
  } else if (currentStatus === STATUS.OFFLINE) {
    text = "Sleeping";
    bg = "#2a2a2a";
    color = "#888";
  } else {
    text = "Not deployed";
    bg = "#2a2a2a";
    color = "#888";
  }

  statusBannerEl.style.background = bg;
  statusBannerEl.style.color = color;
  statusBannerEl.style.animation = animation;
  statusBannerTextEl.textContent = text;
}

function setDeployBanner(state, message) {
  const prev = _prevDeployState;
  _prevDeployState = _deployState;
  _deployState = state;

  // Clear any pending success indicator when state changes
  if (state !== "ready" && _deploySuccessTimer) {
    clearTimeout(_deploySuccessTimer);
    _deploySuccessTimer = null;
    _showDeploySuccess = false;
  }

  if (state === "error") {
    stopDeployLogPoll();
    if (statusBannerTextEl) {
      statusBannerTextEl.textContent = "Error: " + (message || "Unknown error");
    }
    _logViewerMinimized = false;
    if (_showLogLinkEl) _showLogLinkEl.style.display = "none";
    toggleDeployLogViewer(true);
  } else if (state === "deploying") {
    _logViewerMinimized = false;
    if (_showLogLinkEl) _showLogLinkEl.style.display = "none";
    toggleDeployLogViewer(true);
    startDeployLogPoll();
  } else if (state === "ready" && prev === "deploying") {
    // Fresh deploy completed — show success indicator, stop log poll
    stopDeployLogPoll();
    _showDeploySuccess = true;
    if (_deploySuccessTimer) clearTimeout(_deploySuccessTimer);
    _deploySuccessTimer = setTimeout(() => {
      _showDeploySuccess = false;
      _deploySuccessTimer = null;
      updateStatusBanner();
    }, 4000);
    // Auto-collapse the log viewer after a brief delay
    setTimeout(() => toggleDeployLogViewer(false), 1200);
  }

  updateStatusBanner();
  updateDeployLogButton();
}

function updateDeployLogButton() {
  if (!statusBannerEl) return;
  const existing = statusBannerEl.querySelector("[data-deploy-log-btn]");
  if (_deployState === "error") {
    if (!existing) {
      const btn = document.createElement("button");
      btn.setAttribute("data-deploy-log-btn", "1");
      btn.textContent = "View Full Log";
      btn.style.cssText = `
        background: transparent; border: 1px solid #e05050; color: #e05050;
        padding: 3px 8px; border-radius: 4px; cursor: pointer; font-size: 11px;
        margin-left: 8px; font-weight: 600;
      `;
      btn.onclick = () => showDeployLogOverlay();
      statusBannerEl.appendChild(btn);
    }
  } else {
    if (existing) existing.remove();
  }
}

async function showDeployLogOverlay() {
  // Remove existing overlay if present
  const prev = document.getElementById("deploy-log-overlay");
  if (prev) prev.remove();

  const overlay = document.createElement("div");
  overlay.id = "deploy-log-overlay";
  overlay.style.cssText = `
    position: fixed; top: 0; left: 0; width: 100%; height: 100%;
    background: rgba(0,0,0,0.7); z-index: 99999;
    display: flex; align-items: center; justify-content: center;
  `;

  const modal = document.createElement("div");
  modal.style.cssText = `
    background: #1e1e2e; border: 1px solid #444; border-radius: 8px;
    width: 80%; max-width: 800px; max-height: 80vh;
    display: flex; flex-direction: column; overflow: hidden;
  `;

  const header = document.createElement("div");
  header.style.cssText = `
    display: flex; align-items: center; padding: 12px 16px;
    border-bottom: 1px solid #333; flex-shrink: 0;
  `;

  const title = document.createElement("span");
  title.style.cssText = "font-weight: 600; font-size: 14px; color: #ddd; flex: 1;";
  title.textContent = "Deploy Log";

  const closeBtn = document.createElement("button");
  closeBtn.textContent = "\u2715";
  closeBtn.style.cssText = `
    background: transparent; border: 1px solid #555; color: #aaa;
    width: 28px; height: 28px; border-radius: 4px; cursor: pointer;
    font-size: 14px; display: flex; align-items: center; justify-content: center;
  `;

  header.appendChild(title);
  header.appendChild(closeBtn);

  const body = document.createElement("div");
  body.style.cssText = "flex: 1; overflow-y: auto; padding: 16px; min-height: 0;";

  const pre = document.createElement("pre");
  pre.style.cssText = `
    margin: 0; font-size: 11px; color: #ccc; white-space: pre-wrap;
    word-break: break-all; font-family: monospace; line-height: 1.5;
  `;
  pre.textContent = "Loading...";
  body.appendChild(pre);

  modal.appendChild(header);
  modal.appendChild(body);
  overlay.appendChild(modal);
  document.body.appendChild(overlay);

  // Centralized close function to prevent listener leaks
  function close() {
    overlay.remove();
    document.removeEventListener("keydown", escHandler);
  }

  // Close on overlay background click
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) close();
  });

  // Close on Escape key
  const escHandler = (e) => {
    if (e.key === "Escape") close();
  };
  document.addEventListener("keydown", escHandler);

  // Close button
  closeBtn.onclick = () => close();

  // Fetch the log
  try {
    const resp = await api.fetchApi(`${MODAL_PREFIX}/deploy/log`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    pre.textContent = data.log || "(No log content available)";
  } catch (e) {
    pre.textContent = `Error loading log: ${e.message}`;
    pre.style.color = "#e05050";
  }
}

// ─── Inline Deploy Log Viewer ──────────────────────────────────────────
function createDeployLogInline() {
  const wrapper = document.createElement("div");
  wrapper.id = "deploy-log-inline";
  wrapper.style.cssText = `
    max-height: 0; overflow: hidden; transition: max-height 0.35s ease, opacity 0.35s ease;
    opacity: 0; border-radius: 6px; background: #111; margin-top: 6px;
    border: 1px solid #333;
  `;

  const inner = document.createElement("div");
  inner.style.cssText = "padding: 8px;";

  const headerRow = document.createElement("div");
  headerRow.style.cssText = `
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 6px;
  `;

  const label = document.createElement("span");
  label.style.cssText = "font-size: 11px; color: #888; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;";
  label.textContent = "Deploy Log";

  const headerActions = document.createElement("div");
  headerActions.style.cssText = "display: flex; align-items: center; gap: 6px;";

  const minimizeBtn = document.createElement("button");
  minimizeBtn.textContent = "\u2013";
  minimizeBtn.title = "Minimize";
  minimizeBtn.style.cssText = `
    background: transparent; border: 1px solid #555; color: #888;
    width: 18px; height: 18px; border-radius: 3px; cursor: pointer;
    font-size: 12px; padding: 0; display: flex; align-items: center; justify-content: center;
    line-height: 1;
  `;
  minimizeBtn.onclick = () => {
    _logViewerMinimized = true;
    toggleDeployLogViewer(false);
    if (_showLogLinkEl) _showLogLinkEl.style.display = "block";
  };

  const fullLogBtn = document.createElement("button");
  fullLogBtn.textContent = "View Full Log \u2197";
  fullLogBtn.style.cssText = `
    background: transparent; border: none; color: #6a9fd8; cursor: pointer;
    font-size: 10px; padding: 0; text-decoration: none;
  `;
  fullLogBtn.onclick = () => showDeployLogOverlay();

  headerActions.appendChild(minimizeBtn);
  headerActions.appendChild(fullLogBtn);

  headerRow.appendChild(label);
  headerRow.appendChild(headerActions);

  const pre = document.createElement("pre");
  pre.style.cssText = `
    margin: 0; font-size: 11px; color: #aaa; white-space: pre-wrap;
    word-break: break-all; font-family: monospace; line-height: 1.5;
    max-height: 120px; overflow-y: auto;
  `;
  pre.textContent = "Waiting for log output...";

  inner.appendChild(headerRow);
  inner.appendChild(pre);
  wrapper.appendChild(inner);

  _deployLogInlineEl = wrapper;
  _deployLogPreEl = pre;
  return wrapper;
}

function toggleDeployLogViewer(show) {
  if (!_deployLogInlineEl) return;
  if (show) {
    _deployLogInlineEl.style.maxHeight = "200px";
    _deployLogInlineEl.style.opacity = "1";
  } else {
    _deployLogInlineEl.style.maxHeight = "0";
    _deployLogInlineEl.style.opacity = "0";
  }
}

async function updateDeployLogInline() {
  if (!_deployLogPreEl) return;
  try {
    const resp = await api.fetchApi(`${MODAL_PREFIX}/deploy/log`);
    if (!resp.ok) return;
    const data = await resp.json();
    if (!data.log) return;
    const lines = data.log.split("\n");
    const tail = lines.slice(-50).join("\n");
    _deployLogPreEl.textContent = tail || "(empty log)";
    _deployLogPreEl.scrollTop = _deployLogPreEl.scrollHeight;
  } catch {
    // silent — poll will retry
  }
}

function startDeployLogPoll() {
  stopDeployLogPoll();
  updateDeployLogInline();
  _deployLogTimer = setTimeout(function pollLoop() {
    updateDeployLogInline().finally(() => {
      _deployLogTimer = setTimeout(pollLoop, 2000);
    });
  }, 2000);
}

function stopDeployLogPoll() {
  if (_deployLogTimer) {
    clearTimeout(_deployLogTimer);
    _deployLogTimer = null;
  }
}

/**
 * Custom confirm dialog overlay — avoids native confirm() which silently
 * returns false when the user has dismissed the "Prevent this page from
 * creating additional dialogs" checkbox.
 * @param {string} message - Confirmation prompt text
 * @returns {Promise<boolean>} resolves to true if confirmed, false if cancelled
 */
function showConfirm(message) {
  return showConfirmDialog(message);
}

function showConfirmDialog(message) {
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.id = "modal-confirm-overlay";
    overlay.style.cssText = `
      position: fixed; top: 0; left: 0; width: 100%; height: 100%;
      background: rgba(0,0,0,0.7); z-index: 99999;
      display: flex; align-items: center; justify-content: center;
    `;

    const box = document.createElement("div");
    box.style.cssText = `
      background: #1e1e2e; border: 1px solid #444; border-radius: 8px;
      padding: 24px; max-width: 420px; width: 90%;
    `;

    const msgEl = document.createElement("div");
    msgEl.style.cssText = "color: #ddd; font-size: 14px; margin-bottom: 20px; line-height: 1.5;";
    msgEl.textContent = message;

    const btnRow = document.createElement("div");
    btnRow.style.cssText = "display: flex; gap: 8px; justify-content: flex-end;";

    const cancelBtn = document.createElement("button");
    cancelBtn.textContent = "Cancel";
    cancelBtn.style.cssText = `
      background: transparent; border: 1px solid #555; color: #aaa;
      padding: 6px 16px; border-radius: 4px; cursor: pointer; font-size: 13px;
    `;

    const confirmBtn = document.createElement("button");
    confirmBtn.textContent = "Delete";
    confirmBtn.style.cssText = `
      background: #c53030; border: none; color: #fff;
      padding: 6px 16px; border-radius: 4px; cursor: pointer; font-size: 13px;
    `;

    btnRow.appendChild(cancelBtn);
    btnRow.appendChild(confirmBtn);
    box.appendChild(msgEl);
    box.appendChild(btnRow);
    overlay.appendChild(box);
    document.body.appendChild(overlay);

    function close(result) {
      overlay.remove();
      document.removeEventListener("keydown", escHandler);
      resolve(result);
    }

    const escHandler = (e) => {
      if (e.key === "Escape") close(false);
    };
    document.addEventListener("keydown", escHandler);

    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) close(false);
    });
    cancelBtn.onclick = () => close(false);
    confirmBtn.onclick = () => close(true);
  });
}

async function pollDeployStatus() {
  try {
    const resp = await api.fetchApi(`${MODAL_PREFIX}/deploy/status`);
    if (!resp.ok) return;
    const data = await resp.json();
    setDeployBanner(data.state, data.message);
    if (data.state === "deploying") {
      _deployPollTimer = setTimeout(pollDeployStatus, 3000);
    } else if (data.state === "ready") {
      _hasChanges = false;
      _deployWarning = data.warning ? data.message : "";
      updateStatusBanner();
    }
  } catch {
    // Transient error — re-arm so polling doesn't stop permanently
  }
  // Always re-arm if still in a non-terminal state
  if (_deployState === "deploying" || _deployState === "starting" || _deployState === "unknown") {
    _deployPollTimer = setTimeout(pollDeployStatus, 3000);
  }
}

function startDeployPoll() {
  if (_deployPollTimer) clearTimeout(_deployPollTimer);
  pollDeployStatus();
}

function setStatus(s) {
  currentStatus = s;
  if (dotEl) {
    const { color } = STATUS_STYLE[s] || STATUS_STYLE[STATUS.UNKNOWN];
    dotEl.style.background = color;
  }
  if (statusEl) {
    const { label } = STATUS_STYLE[s] || STATUS_STYLE[STATUS.UNKNOWN];
    statusEl.textContent = _runtimeStatusText || label;
  }
  updateStatusBanner();
}

function setRuntimeStatus(message, phase = "startup") {
  _runtimeStatusText = message || "";
  _runtimeStatusPhase = phase || "startup";
  if (_runtimeStatusText) {
    setStatus(STATUS.STARTING);
  } else {
    updateStatusBanner();
  }
}

async function checkHealth(ping = false) {
  setStatus(STATUS.CHECKING);
  try {
    const url = ping
      ? `${MODAL_PREFIX}/health?mode=ping`
      : `${MODAL_PREFIX}/health?mode=deploy`;
    const resp = await api.fetchApi(url);
    if (resp.ok) {
      const data = await resp.json();
      setStatus(data.status === "ok" ? STATUS.ONLINE : STATUS.OFFLINE);
    } else {
      const data = await resp.json().catch(() => ({}));
      if (data.status === "deploying") {
        setStatus(STATUS.CHECKING);
        if (statusEl) statusEl.textContent = "Deploying...";
      } else {
        setStatus(STATUS.OFFLINE);
      }
    }
  } catch {
    setStatus(STATUS.OFFLINE);
  }
}

api.addEventListener("execution_start", () => {
  if (!_runtimeStatusText) setStatus(STATUS.GENERATING);
});
api.addEventListener("executing", (e) => {
  if (e?.detail?.node === null) {
    setRuntimeStatus("");
    setStatus(STATUS.OFFLINE);
  } else {
    setRuntimeStatus("");
    setStatus(STATUS.GENERATING);
  }
});
api.addEventListener("execution_error", () => {
  setRuntimeStatus("");
  setStatus(STATUS.OFFLINE);
});
api.addEventListener("execution_success", (e) => {
  const detail = e?.detail || {};
  if (detail._production_evidence) {
    _lastProductionEvidence = detail._production_evidence;
    if (prodSummaryEl && prodToggle.checked) {
      _updateProductionSummary(prodSummaryEl);
    }
  }
});
api.addEventListener("progress", () => {
  // Keep status as GENERATING while progress events are flowing
  setRuntimeStatus("");
  if (currentStatus !== STATUS.GENERATING) setStatus(STATUS.GENERATING);
});
api.addEventListener("modal_status", (e) => {
  const detail = e?.detail || {};
  if (!detail.prompt_id) return;
  setRuntimeStatus(detail.message || "", detail.phase || "startup");
});

// --- Toast notification ---
function showToast(message, type) {
  const toast = document.createElement("div");
  toast.setAttribute("role", "alert");
  toast.setAttribute("aria-live", "polite");
  const bgMap = { success: "#1a3a1a", error: "#3d1010", info: "#1a2a3a" };
  const colorMap = { success: "#7ed321", error: "#e05050", info: "#6a9fd8" };
  toast.style.cssText = `
    position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%);
    background: ${bgMap[type] || bgMap.info}; color: ${colorMap[type] || colorMap.info};
    padding: 8px 16px; border-radius: 6px; font-size: 12px;
    z-index: 10000; pointer-events: none; opacity: 1;
    transition: opacity 0.5s ease; border: 1px solid ${colorMap[type] || colorMap.info};
  `;
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => { toast.style.opacity = "0"; }, 1500);
  setTimeout(() => { toast.remove(); }, 2100);
}

// --- Utility ---
function fmtSize(bytes) {
  if (bytes >= 1024 ** 3) return (bytes / 1024 ** 3).toFixed(2) + " GB";
  if (bytes >= 1024 ** 2) return (bytes / 1024 ** 2).toFixed(1) + " MB";
  return (bytes / 1024).toFixed(0) + " KB";
}

function describeLocalFile(info) {
  if (!info || info.error) return { label: "local unknown", color: "#888", border: "#444", title: info?.error || "Local file status unavailable" };
  if (info.is_real_file) {
    return {
      label: "local file",
      color: "#7ed321",
      border: "#295c16",
      title: "A real local model file already exists. It was not overwritten.",
    };
  }
  if (info.is_placeholder) {
    return {
      label: "placeholder",
      color: "#6a9fd8",
      border: "#36506d",
      title: "A 0-byte local placeholder already exists for this remote model.",
    };
  }
  return {
    label: "local missing",
    color: "#aaa",
    border: "#555",
    title: "No local file exists yet. Create a local placeholder if you want this model to appear in local ComfyUI dropdowns.",
  };
}

function debounce(fn, ms) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

// --- Collapsible section helper ---
function createCollapsibleSection(title, opts) {
  const { defaultOpen, badge, id } = opts || {};
  const wrapper = document.createElement("div");
  wrapper.style.cssText = "border-radius: 6px; background: #1e1e2e; overflow: hidden; flex-shrink: 0;";

  const header = document.createElement("div");
  header.style.cssText = `
    display: flex; align-items: center; gap: 8px; padding: 8px 10px;
    cursor: pointer; user-select: none;
  `;

  const chevron = document.createElement("span");
  chevron.style.cssText = "font-size: 10px; color: #888; transition: transform 0.2s ease; flex-shrink: 0;";
  chevron.textContent = "\u25B6";

  const titleEl = document.createElement("span");
  titleEl.style.cssText = "font-weight: 600; font-size: 13px; flex: 1;";
  titleEl.textContent = title;

  const badgeEl = document.createElement("span");
  badgeEl.style.cssText = "font-size: 10px; background: #3a3a4a; color: #aaa; padding: 1px 6px; border-radius: 8px; flex-shrink: 0;";
  badgeEl.textContent = badge != null ? badge : "0";

  header.appendChild(chevron);
  header.appendChild(titleEl);
  header.appendChild(badgeEl);

  const content = document.createElement("div");
  content.style.cssText = "max-height: 0; overflow: hidden; transition: max-height 0.3s ease; padding: 0 10px;";

  let isOpen = !!defaultOpen;

  function toggle() {
    isOpen = !isOpen;
    if (isOpen) {
      content.style.maxHeight = content.scrollHeight + 200 + "px";
      content.style.paddingBottom = "10px";
      chevron.style.transform = "rotate(90deg)";
    } else {
      content.style.maxHeight = "0";
      content.style.paddingBottom = "0";
      chevron.style.transform = "rotate(0deg)";
    }
  }

  function open() {
    if (!isOpen) toggle();
  }

  function updateBadge(val) {
    badgeEl.textContent = String(val);
  }

  function refreshHeight() {
    if (isOpen) {
      content.style.maxHeight = content.scrollHeight + 200 + "px";
    }
  }

  if (isOpen) {
    // start open
    setTimeout(() => {
      content.style.maxHeight = content.scrollHeight + 200 + "px";
      content.style.paddingBottom = "10px";
      chevron.style.transform = "rotate(90deg)";
    }, 0);
  }

  header.onclick = toggle;

  wrapper.appendChild(header);
  wrapper.appendChild(content);

  return { wrapper, content, header, updateBadge, open, toggle, refreshHeight };
}

// --- Models loading ---
async function loadModels() {
  if (!modelListEl) return;
  modelListEl.innerHTML = `<div style="color:#888;padding:8px 0;font-size:12px;">Loading...</div>`;
  try {
    const resp = await api.fetchApi(`${MODAL_PREFIX}/models`);
    if (resp.status === 503) {
      modelListEl.innerHTML = `<div style="color:#888;font-size:12px;line-height:1.6;">Modal app not deployed yet.<br>Click <b>Deploy to Cloud</b> above to get started.</div>`;
      if (modelsCollapsibleRef) modelsCollapsibleRef.refreshHeight();
      return;
    }
    if (!resp.ok) throw new Error(resp.status);
    const data = await resp.json();
    renderModelList(data);
  } catch (e) {
    modelListEl.innerHTML = "";
    const errDiv = document.createElement("div");
    errDiv.style.cssText = "color:#e05;font-size:12px;";
    errDiv.textContent = "Error loading models";
    const details = document.createElement("details");
    details.style.cssText = "font-size:11px;color:#888;margin-top:4px;";
    const summary = document.createElement("summary");
    summary.style.cssText = "cursor:pointer;color:#aaa;";
    summary.textContent = "Show details";
    const msgP = document.createElement("p");
    msgP.style.cssText = "margin:4px 0 0;font-family:monospace;";
    msgP.textContent = e.message;
    details.appendChild(summary);
    details.appendChild(msgP);
    modelListEl.appendChild(errDiv);
    modelListEl.appendChild(details);
    if (modelsCollapsibleRef) modelsCollapsibleRef.refreshHeight();
  }
}

function renderModelList(data) {
  modelListEl.innerHTML = "";

  let hasAny = false;
  for (const folder of FOLDERS) {
    const files = data[folder] || [];
    if (files.length === 0) continue;
    hasAny = true;

    const section = document.createElement("div");
    section.style.cssText = "margin-bottom: 10px;";

    const folderLabel = document.createElement("div");
    folderLabel.style.cssText = "font-size:11px; font-weight:600; color:#aaa; text-transform:uppercase; letter-spacing:0.05em; margin-bottom:4px;";
    folderLabel.textContent = folder;
    section.appendChild(folderLabel);

    for (const file of files) {
      const localInfo = file.local_placeholder || null;
      const localState = describeLocalFile(localInfo);
      const row = document.createElement("div");
      row.style.cssText = "display:flex; align-items:center; gap:6px; padding:4px 6px; border-radius:4px; background:#2a2a2a; margin-bottom:3px;";

      const name = document.createElement("span");
      name.style.cssText = "flex:1; font-size:12px; color:#ddd; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; direction:ltr; min-width:0;";
      name.title = file.name;
      name.textContent = file.name;

      const size = document.createElement("span");
      size.style.cssText = "font-size:11px; color:#666; flex-shrink:0;";
      size.textContent = fmtSize(file.size);

      const localBadge = document.createElement("span");
      localBadge.style.cssText = `font-size:10px; color:${localState.color}; background:#222; border:1px solid ${localState.border}; border-radius:3px; padding:0 4px; flex-shrink:0;`;
      localBadge.textContent = localState.label;
      localBadge.title = localState.title;

      if (file.folder && file.folder !== folder) {
        const badge = document.createElement("span");
        badge.style.cssText = "font-size:10px; color:#888; background:#333; border:1px solid #444; border-radius:3px; padding:0 4px; flex-shrink:0;";
        badge.textContent = file.folder;
        row.appendChild(name);
        row.appendChild(badge);
        row.appendChild(size);
        row.appendChild(localBadge);
      } else {
        row.appendChild(name);
        row.appendChild(size);
        row.appendChild(localBadge);
      }

      const injectBtn = document.createElement("button");
      injectBtn.style.cssText = "background: transparent; border: 1px solid #557; color: #99b; padding: 0 6px; height: 20px; border-radius: 3px; cursor: pointer; font-size: 10px; flex-shrink: 0; line-height: 1;";

      const updateInjectState = (info) => {
        const state = describeLocalFile(info);
        localBadge.style.color = state.color;
        localBadge.style.borderColor = state.border;
        localBadge.textContent = state.label;
        localBadge.title = state.title;

        if (info?.is_real_file) {
          injectBtn.textContent = "Local file";
          injectBtn.title = "A real local file already exists and will not be overwritten.";
          injectBtn.disabled = true;
          injectBtn.style.opacity = "0.7";
          injectBtn.style.cursor = "default";
        } else if (info?.is_placeholder) {
          injectBtn.textContent = "Placeholder";
          injectBtn.title = "A local 0-byte placeholder already exists.";
          injectBtn.disabled = true;
          injectBtn.style.opacity = "0.7";
          injectBtn.style.cursor = "default";
        } else {
          injectBtn.textContent = "Create local";
          injectBtn.title = "Create a 0-byte local placeholder so this remote model appears in local ComfyUI dropdowns.";
          injectBtn.disabled = false;
          injectBtn.style.opacity = "1";
          injectBtn.style.cursor = "pointer";
        }
      };

      updateInjectState(localInfo);

      injectBtn.onclick = async () => {
        injectBtn.disabled = true;
        injectBtn.textContent = "Creating...";
        try {
          const r = await api.fetchApi(`${MODAL_PREFIX}/models/inject`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ folder: file.folder ?? folder, filename: file.name }),
          });
          const result = await r.json();
          if (result.status !== "ok") throw new Error(result.message || "Placeholder creation failed");
          updateInjectState(result.placeholder);
          showToast(result.message || "Local placeholder created. Refresh ComfyUI if the dropdown does not update.", "success");
        } catch (e) {
          injectBtn.disabled = false;
          injectBtn.textContent = "Create local";
          showToast("Error: " + e.message, "error");
        }
      };

      const delBtn = document.createElement("button");
      delBtn.textContent = "\u2715";
      delBtn.title = `Delete ${file.name}`;
      delBtn.style.cssText = `
        background: transparent; border: 1px solid #555; color: #e05;
        width: 20px; height: 20px; border-radius: 3px; cursor: pointer;
        font-size: 11px; flex-shrink: 0; line-height: 1;
        display: flex; align-items: center; justify-content: center;
      `;
      delBtn.onclick = async () => {
        if (!(await showConfirmDialog(`Delete ${file.folder ?? folder}/${file.name}?`))) return;
        delBtn.disabled = true;
        delBtn.textContent = "\u2026";
        try {
          const r = await api.fetchApi(`${MODAL_PREFIX}/models/${file.folder ?? folder}/${encodeURIComponent(file.name)}`, { method: "DELETE" });
          const result = await r.json();
          if (result.status === "ok") {
            row.remove();
            showToast("Model deleted", "success");
          } else {
            alert(`Delete failed: ${result.message}`);
            delBtn.disabled = false;
            delBtn.textContent = "\u2715";
          }
        } catch (e) {
          alert(`Error: ${e.message}`);
          delBtn.disabled = false;
          delBtn.textContent = "\u2715";
        }
      };

      row.appendChild(injectBtn);
      row.appendChild(delBtn);
      section.appendChild(row);
    }

    modelListEl.appendChild(section);
  }

  if (!hasAny) {
    modelListEl.innerHTML = `<div style="color:#666;font-size:12px;padding:8px 0;">No models in volume.</div>`;
  }
  if (modelsCollapsibleRef) modelsCollapsibleRef.refreshHeight();
}

// --- Download queue ---
const downloadQueue = [];
let queueListEl = null;
let downloadAllBtn = null;
let batchStatusEl = null;

function renderQueueItem(entry) {
  const row = document.createElement("div");
  row.dataset.id = entry.id;
  row.style.cssText = "display:flex; align-items:center; gap:6px; padding:4px 6px; border-radius:4px; background:#2a2a2a; margin-bottom:3px;";

  const info = document.createElement("div");
  info.style.cssText = "flex:1; min-width:0;";

  const nameLine = document.createElement("div");
  nameLine.style.cssText = "font-size:12px; color:#ddd; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;";
  nameLine.textContent = `${entry.folder}/${entry.filename}`;
  nameLine.title = entry.url;

  const statusLine = document.createElement("div");
  statusLine.style.cssText = "font-size:10px; color:#888; margin-top:1px;";
  statusLine.textContent = "queued";
  statusLine.dataset.status = "queued";

  info.appendChild(nameLine);
  info.appendChild(statusLine);

  const removeBtn = document.createElement("button");
  removeBtn.textContent = "\u2715";
  removeBtn.style.cssText = `
    background: transparent; border: 1px solid #555; color: #888;
    width: 18px; height: 18px; border-radius: 3px; cursor: pointer;
    font-size: 10px; flex-shrink: 0; line-height: 1;
    display: flex; align-items: center; justify-content: center;
  `;
  removeBtn.onclick = () => {
    const idx = downloadQueue.findIndex(e => e.id === entry.id);
    if (idx !== -1) downloadQueue.splice(idx, 1);
    row.remove();
    syncDownloadAllBtn();
  };

  row.appendChild(info);
  row.appendChild(removeBtn);

  entry.statusEl = statusLine;
  entry.removeBtn = removeBtn;

  return row;
}

function syncDownloadAllBtn() {
  if (!downloadAllBtn) return;
  const queued = downloadQueue.filter(e => e.state === "queued").length;
  downloadAllBtn.disabled = queued === 0;
  downloadAllBtn.textContent = queued > 1
    ? `\u2B07 Download All (${queued})`
    : "\u2B07 Download Batch";
}

// --- Auth Panel ---
function buildAuthPanel(onConnected) {
  const wrap = document.createElement("div");
  wrap.style.cssText = "display:flex; flex-direction:column; gap:12px; padding:14px 16px; height:100%; box-sizing:border-box;";

  const title = document.createElement("div");
  title.style.cssText = "font-weight:600; font-size:14px;";
  title.textContent = "\u2601 Modal GPU";
  wrap.appendChild(title);

  const desc = document.createElement("div");
  desc.style.cssText = "font-size:12px; color:#aaa; line-height:1.6;";
  desc.innerHTML = `Connect your <a href="https://modal.com" target="_blank" rel="noopener noreferrer" style="color:#6a9fd8;">Modal</a> account to run generations on cloud GPUs.`;
  wrap.appendChild(desc);

  const steps = document.createElement("ol");
  steps.style.cssText = "font-size:12px; color:#aaa; line-height:1.8; padding-left:18px; margin:0;";
  steps.innerHTML = `
    <li>Create a free account at <a href="https://modal.com" target="_blank" rel="noopener noreferrer" style="color:#6a9fd8;">modal.com</a></li>
    <li>Go to <a href="https://modal.com/settings/tokens" target="_blank" rel="noopener noreferrer" style="color:#6a9fd8;">Settings \u2192 Tokens</a></li>
    <li>Create a new token and paste below</li>
  `;
  wrap.appendChild(steps);

  const pasteHint = document.createElement("div");
  pasteHint.style.cssText = "font-size:11px; color:#888; line-height:1.5;";
  pasteHint.innerHTML = `You can paste the full command directly:<br><span style="color:#666; font-family:monospace;">modal token set --token-id ak-... --token-secret as-...</span>`;
  wrap.appendChild(pasteHint);

  const pasteInput = document.createElement("input");
  pasteInput.type = "text";
  pasteInput.placeholder = "Paste full command or Token ID (ak-...)";
  pasteInput.style.cssText = inputStyle();
  wrap.appendChild(pasteInput);

  const labelInput = document.createElement("input");
  labelInput.type = "text";
  labelInput.placeholder = "Workspace label (for the dropdown)";
  labelInput.style.cssText = inputStyle();
  wrap.insertBefore(labelInput, pasteInput);

  const tokenSecretInput = document.createElement("input");
  tokenSecretInput.type = "password";
  tokenSecretInput.placeholder = "Token Secret  (as-...)  \u2014 auto-filled if pasted above";
  tokenSecretInput.style.cssText = inputStyle();
  wrap.appendChild(tokenSecretInput);

  function tryParseCommand(val) {
    const idMatch = val.match(/--token-id\s+(ak-\S+)/);
    const secretMatch = val.match(/--token-secret\s+(as-\S+)/);
    if (idMatch && secretMatch) {
      pasteInput.value = idMatch[1];
      tokenSecretInput.value = secretMatch[1];
      return true;
    }
    return false;
  }
  pasteInput.addEventListener("input", () => tryParseCommand(pasteInput.value));
  pasteInput.addEventListener("paste", (e) => {
    const pasted = (e.clipboardData || window.clipboardData).getData("text");
    if (tryParseCommand(pasted)) e.preventDefault();
  });

  const errorEl = document.createElement("div");
  errorEl.style.cssText = "font-size:11px; color:#e05050; min-height:14px;";
  wrap.appendChild(errorEl);

  const connectBtn = document.createElement("button");
  connectBtn.textContent = "Save Workspace";
  connectBtn.style.cssText = btnStyle("primary");
  connectBtn.onclick = async () => {
    const label = labelInput.value.trim() || "Primary Workspace";
    const token_id = pasteInput.value.trim();
    const token_secret = tokenSecretInput.value.trim();
    errorEl.textContent = "";
    if (!token_id || !token_secret) {
      errorEl.textContent = "Workspace label, token ID, and token secret are required.";
      return;
    }
    connectBtn.disabled = true;
    connectBtn.textContent = "Saving\u2026";
    try {
      const resp = await api.fetchApi(`${MODAL_PREFIX}/workspaces`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label, token_id, token_secret, set_active: true }),
      });
      const data = await resp.json();
      if (data.status !== "ok") throw new Error(data.message || "Workspace save failed");
      onConnected();
    } catch (e) {
      errorEl.textContent = `Error: ${e.message}`;
      connectBtn.disabled = false;
      connectBtn.textContent = "Save Workspace";
    }
  };
  wrap.appendChild(connectBtn);

  return wrap;
}

// --- Main Panel ---
function buildPanel() {
  const panel = document.createElement("div");
  panel.style.cssText = `
    font-size: 13px;
    color: var(--fg-color, #ddd);
    height: 100%;
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  `;

  // Inject keyframe animation for status pulse
  if (!document.getElementById("modal-settings-styles")) {
    const styleTag = document.createElement("style");
    styleTag.id = "modal-settings-styles";
    styleTag.textContent = `
      @keyframes statusPulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.6; }
      }
      @keyframes successPulse {
        0%, 100% { opacity: 1; transform: scale(1); }
        50% { opacity: 0.8; transform: scale(1.02); }
      }
      @keyframes cm-dl-pulse {
        0%, 100% { opacity: 0.5; }
        50% { opacity: 1; }
      }
    `;
    document.head.appendChild(styleTag);
  }

  // === STICKY HEADER AREA ===
  const stickyTop = document.createElement("div");
  stickyTop.style.cssText = "flex-shrink: 0; padding: 14px 16px 0; display: flex; flex-direction: column; gap: 10px;";

  // -- Status Banner --
  statusBannerEl = document.createElement("div");
  statusBannerEl.style.cssText = `
    padding: 8px 12px; border-radius: 6px; background: #2a2a2a;
    font-size: 12px; font-weight: 600; text-align: center; color: #888;
  `;
  statusBannerTextEl = document.createElement("span");
  statusBannerTextEl.textContent = "Not deployed";
  statusBannerEl.appendChild(statusBannerTextEl);
  stickyTop.appendChild(statusBannerEl);

  // -- Header Row: Title + Gear --
  const headerRow = document.createElement("div");
  headerRow.style.cssText = "display:flex; align-items:center; gap:8px;";

  const title = document.createElement("span");
  title.style.cssText = "font-weight:600; font-size:14px; letter-spacing:0.03em; flex:1;";
  title.textContent = "\u2601 Modal GPU";

  const testingBtn = document.createElement("button");
  testingBtn.textContent = "Testing Suite";
  testingBtn.title = "Open the Testing Suite";
  testingBtn.style.cssText = `
    background: transparent; border: 1px solid #3a6fcc; color: #6a9fd8;
    padding: 2px 10px; border-radius: 4px; cursor: pointer;
    font-size: 11px; flex-shrink: 0; font-weight: 600;
  `;
  testingBtn.onclick = () => {
    if (typeof window.open_testing_modal === "function") {
      window.open_testing_modal();
      if (typeof window.__comfyModalTestingMarkSecondaryLauncherRegistered === "function") {
        window.__comfyModalTestingMarkSecondaryLauncherRegistered();
      }
    }
  };

  const gearBtn = document.createElement("button");
  gearBtn.textContent = "\u2699";
  gearBtn.title = "Settings";
  gearBtn.style.cssText = `
    background: transparent; border: 1px solid #555; color: #aaa;
    width: 28px; height: 28px; border-radius: 4px; cursor: pointer;
    font-size: 16px; display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
  `;

  headerRow.appendChild(title);
  headerRow.appendChild(testingBtn);
  headerRow.appendChild(gearBtn);
  stickyTop.appendChild(headerRow);

  // -- Deploy Button (prominent) --
  const redeployBtn = document.createElement("button");
  redeployBtn.textContent = "Deploy to Cloud";
  redeployBtn.title = "Deploy or re-deploy comfyapp.py to Modal";
  redeployBtn.style.cssText = btnStyle("primary");
  redeployBtn.onclick = async () => {
    redeployBtn.disabled = true;
    redeployBtn.textContent = "Deploying...";
    setDeployBanner("deploying", ""); // immediate local state update
    try {
      await api.fetchApi(`${MODAL_PREFIX}/deploy`, { method: "POST" });
      startDeployPoll();
      showToast("Deploy started", "success");
    } catch (e) {
      setDeployBanner("error", e.message);
    }
    setTimeout(() => {
      redeployBtn.disabled = false;
      redeployBtn.textContent = "Deploy to Cloud";
    }, 3000);
  };
  stickyTop.appendChild(redeployBtn);

  // -- Redeploy + Restart combo button --
  const redeployRestartBtn = document.createElement("button");
  redeployRestartBtn.textContent = "Redeploy and Restart";
  redeployRestartBtn.title = "Redeploy to Modal, restart ComfyUI, and refresh";
  redeployRestartBtn.style.cssText = btnStyle("primary") + "background: #5a3fcc; border-color: #6a4fe0;";
  redeployRestartBtn.onclick = async () => {
    redeployBtn.disabled = true;
    redeployRestartBtn.disabled = true;
    redeployRestartBtn.textContent = "Deploying...";

    const updateStatus = (msg) => {
      redeployRestartBtn.textContent = msg;
    };

    // Step 1: Deploy
    setDeployBanner("deploying", "");
    try {
      const deployResp = await api.fetchApi(`${MODAL_PREFIX}/deploy`, { method: "POST" });
      if (!deployResp.ok) throw new Error("Deploy request failed: " + deployResp.status);
    } catch (e) {
      setDeployBanner("error", e.message);
      redeployBtn.disabled = false;
      redeployRestartBtn.disabled = false;
      redeployRestartBtn.textContent = "Redeploy and Restart";
      return;
    }

    // Step 2: Poll until deploy is ready
    updateStatus("Waiting for deploy...");
    let deployReady = false;
    const pollStart = Date.now();
    const POLL_TIMEOUT_MS = 10 * 60 * 1000; // 10 minutes max
    while (!deployReady && (Date.now() - pollStart) < POLL_TIMEOUT_MS) {
      await new Promise(r => setTimeout(r, 3000));
      try {
        const statusResp = await api.fetchApi(`${MODAL_PREFIX}/deploy/status`);
        if (statusResp.ok) {
          const data = await statusResp.json();
          if (data.state === "ready") {
            deployReady = true;
          } else if (data.state === "error") {
            throw new Error(data.message || "Deploy failed");
          }
          // "deploying" → keep polling
        }
      } catch (e) {
        if (e.message && !e.message.includes("fetch")) throw e;
        // Network errors during polling are ok — keep trying
      }
    }
    if (!deployReady) {
      redeployRestartBtn.textContent = "Deploy timed out";
      redeployBtn.disabled = false;
      redeployRestartBtn.disabled = false;
      setTimeout(() => { redeployRestartBtn.textContent = "Redeploy and Restart"; }, 3000);
      return;
    }

    // Step 3: Restart ComfyUI
    updateStatus("Restarting ComfyUI...");
    try {
      await api.fetchApi("/api/manager/restart", { method: "POST" });
    } catch {
      // Restart endpoint may close connection before responding — expected
    }

    // Step 4: Wait for server to come back up, then reload
    updateStatus("Waiting for restart...");
    // Generous timeout: ComfyUI can take several minutes to restart on Modal
    const RESTART_TIMEOUT_MS = 600 * 1000;
    const restartStart = Date.now();

    // Brief pause after restart command, then poll for server to be reachable
    await new Promise(r => setTimeout(r, 3000));
    let serverUp = false;
    while (!serverUp && (Date.now() - restartStart) < RESTART_TIMEOUT_MS) {
      await new Promise(r => setTimeout(r, 3000));
      try {
        const resp = await fetch("/api/object_info", { signal: AbortSignal.timeout(5000) });
        if (resp.ok) serverUp = true;
      } catch {}
    }

    if (!serverUp) {
      updateStatus("Server restart timed out — check logs");
      redeployRestartBtn.textContent = "Restart timed out";
      redeployRestartBtn.disabled = false;
      redeployBtn.disabled = false;
      setTimeout(() => { redeployRestartBtn.textContent = "Redeploy and Restart"; }, 5000);
      return;
    }

    // Flag for post-reload success banner
    try { sessionStorage.setItem("_comfymodal_redeploy_restart_done", "1"); } catch {}

    // Wait 10s for the ComfyUI server to stabilize before refreshing
    updateStatus("Server up — stabilizing 10s before reload...");
    await new Promise(r => setTimeout(r, 10000));

    updateStatus("Reloading...");
    location.reload();
  };
  stickyTop.appendChild(redeployRestartBtn);

  // Inline deploy log viewer (hidden by default, shown during deploy)
  const logViewer = createDeployLogInline();
  stickyTop.appendChild(logViewer);

  // Re-open link shown when the log viewer is minimized
  _showLogLinkEl = document.createElement("button");
  _showLogLinkEl.textContent = "+ Show deploy log";
  _showLogLinkEl.style.cssText = `
    display: none; background: transparent; border: 1px dashed #555; color: #888;
    padding: 4px 8px; border-radius: 4px; cursor: pointer; font-size: 11px;
    width: 100%; text-align: center;
  `;
  _showLogLinkEl.onclick = () => {
    _logViewerMinimized = false;
    _showLogLinkEl.style.display = "none";
    toggleDeployLogViewer(true);
  };
  stickyTop.appendChild(_showLogLinkEl);

  // -- Run Mode Toggle --
  const modeSection = document.createElement("div");
  modeSection.style.cssText = "display: flex; flex-direction: column; gap: 6px;";

  const modeLabel = document.createElement("div");
  modeLabel.style.cssText = "font-size: 12px; color: #aaa; font-weight: 600;";
  modeLabel.textContent = "Run on:";

  const modeToggle = document.createElement("div");
  modeToggle.style.cssText = "display: flex; border-radius: 6px; overflow: hidden; border: 1px solid #444;";

  const savedEnabled = localStorage.getItem(STORAGE_KEY_ENABLED);
  let isCloudMode = savedEnabled === null ? true : savedEnabled === "true";

  const cloudBtn = document.createElement("button");
  cloudBtn.textContent = "Cloud (Modal GPU)";
  cloudBtn.style.cssText = segmentBtnStyle(isCloudMode);

  const localBtn = document.createElement("button");
  localBtn.textContent = "Local (this PC)";
  localBtn.style.cssText = segmentBtnStyle(!isCloudMode);

  function updateModeToggle(cloud) {
    isCloudMode = cloud;
    cloudBtn.style.cssText = segmentBtnStyle(cloud);
    localBtn.style.cssText = segmentBtnStyle(!cloud);
    localStorage.setItem(STORAGE_KEY_ENABLED, String(cloud));
    window._comfyModalEnabled = cloud;
    updateModalSections(cloud);
  }

  cloudBtn.onclick = () => updateModeToggle(true);
  localBtn.onclick = () => updateModeToggle(false);

  modeToggle.appendChild(cloudBtn);
  modeToggle.appendChild(localBtn);

  const modeHint = document.createElement("div");
  modeHint.style.cssText = "font-size: 11px; color: #666; line-height: 1.4;";
  modeHint.textContent = "Cloud mode sends generations to Modal. Local mode runs on your machine.";

  modeSection.appendChild(modeLabel);
  modeSection.appendChild(modeToggle);
  modeSection.appendChild(modeHint);
  stickyTop.appendChild(modeSection);

  // Divider
  const topDivider = document.createElement("div");
  topDivider.style.cssText = "border-top: 1px solid #3a3a3a; margin-top: 4px;";
  stickyTop.appendChild(topDivider);

  panel.appendChild(stickyTop);

  // === SCROLLABLE CONTENT AREA ===
  const scrollContent = document.createElement("div");
  scrollContent.style.cssText = "flex: 1; overflow-y: auto; min-height: 0; padding: 10px 16px 16px; display: flex; flex-direction: column; gap: 16px;";

  // -- GPU Selector --
  const gpuSection = document.createElement("div");
  gpuSection.style.cssText = "display:flex; flex-direction:column; gap:6px;";

  const gpuRow = document.createElement("div");
  gpuRow.style.cssText = "display:flex; align-items:center; gap:8px;";

  const gpuLabel = document.createElement("span");
  gpuLabel.style.cssText = "font-size:12px; color:#aaa; font-weight:600; flex-shrink:0;";
  gpuLabel.textContent = "GPU";

  const gpuSelect = document.createElement("select");
  gpuSelect.style.cssText = inputStyle() + "flex:1; margin:0;";
  const storedGpu = localStorage.getItem(STORAGE_KEY_GPU) || "";
  window._comfyModalGpu = "rtx-pro-6000";

  gpuSelect.addEventListener("change", async () => {
    const gpu = gpuSelect.value;
    localStorage.setItem(STORAGE_KEY_GPU, gpu);
    window._comfyModalGpu = gpu;
    try {
      await api.fetchApi(`${MODAL_PREFIX}/config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ gpu }),
      });
    } catch {}
  });

  gpuRow.appendChild(gpuLabel);
  gpuRow.appendChild(gpuSelect);
  gpuSection.appendChild(gpuRow);

  const gpuHint = document.createElement("div");
  gpuHint.style.cssText = "font-size: 11px; color: #666; line-height: 1.4;";
  gpuHint.textContent = "You only pay while generating. Container shuts down when idle.";
  gpuSection.appendChild(gpuHint);

  // -- Status row --
  const statusRow = document.createElement("div");
  statusRow.style.cssText = "display:flex; align-items:center; gap:8px;";

  dotEl = document.createElement("span");
  dotEl.style.cssText = "width:9px; height:9px; border-radius:50%; background:#888; display:inline-block; flex-shrink:0;";
  statusEl = document.createElement("span");
  statusEl.style.cssText = "font-size:11px; color:#888; flex:1;";
  statusEl.textContent = "Unknown";

  const checkBtn = document.createElement("button");
  checkBtn.textContent = "Check Status";
  checkBtn.title = "Verify your Modal app is deployed and ready";
  checkBtn.style.cssText = btnStyle();
  checkBtn.onclick = () => checkHealth(false);

  const pingBtn = document.createElement("button");
  pingBtn.textContent = "Wake Up";
  pingBtn.title = "Start the GPU container (takes 1-3 min on first use)";
  pingBtn.style.cssText = btnStyle();
  pingBtn.onclick = async () => {
    pingBtn.disabled = true;
    pingBtn.textContent = "Waking...";
    await checkHealth(true);
    pingBtn.disabled = false;
    pingBtn.textContent = "Wake Up";
  };

  statusRow.appendChild(dotEl);
  statusRow.appendChild(statusEl);
  statusRow.appendChild(checkBtn);
  statusRow.appendChild(pingBtn);
  gpuSection.appendChild(statusRow);

  scrollContent.appendChild(gpuSection);

  // === EXECUTION ENGINE SECTION ===
  const engineSection = document.createElement("div");
  engineSection.style.cssText = "display:flex; flex-direction:column; gap:6px;";
  const engineLabel = document.createElement("span");
  engineLabel.style.cssText = "font-size:12px; color:#aaa; font-weight:600;";
  engineLabel.textContent = "Execution Engine";
  const engineSelect = document.createElement("select");
  engineSelect.style.cssText = inputStyle();
  const engineStatus = document.createElement("div");
  engineStatus.style.cssText = "font-size:11px; color:#666; line-height:1.4; min-height:14px;";
  const engineReadiness = document.createElement("div");
  engineReadiness.style.cssText = "font-size:10px; color:#666; line-height:1.4;";
  engineSection.appendChild(engineLabel);
  engineSection.appendChild(engineSelect);
  engineSection.appendChild(engineStatus);
  engineSection.appendChild(engineReadiness);

  function renderExecutionEngineConfig(config) {
    const modes = Array.isArray(config && config.available_execution_modes)
      ? config.available_execution_modes
      : [{ value: "v2", label: "V2 - Recommended" }, { value: "v1", label: "V1 - Legacy fallback" }];
    while (engineSelect.firstChild) engineSelect.removeChild(engineSelect.firstChild);
    modes.forEach((mode) => {
      const option = document.createElement("option");
      option.value = mode.value;
      option.textContent = mode.label;
      engineSelect.appendChild(option);
    });
    const current = (config && config.execution_mode) || "v2";
    engineSelect.value = current;
    window._comfyModalExecutionMode = current;
    const locked = !!(config && config.execution_mode_locked);
    engineSelect.disabled = locked;
    engineStatus.textContent = locked
      ? "Managed by COMFYMODAL_RUNTIME"
      : "Current engine: " + current.toUpperCase() + " - Applies to future runs only";
    engineStatus.style.color = locked ? "#f5a623" : "#666";
    const readiness = config && config.execution_readiness;
    if (readiness) {
      const v1 = readiness.v1 && readiness.v1.status || "unknown";
      const v2 = readiness.v2 && readiness.v2.status || "unknown";
      engineReadiness.textContent = "V1 deployment: " + v1 + " - V2 deployment: " + v2;
      if (v2 === "unavailable") engineReadiness.textContent += " (V2 - Deployment required)";
    }
  }

  api.fetchApi(`${MODAL_PREFIX}/config`).then((response) => response.json()).then(renderExecutionEngineConfig).catch(() => {
    renderExecutionEngineConfig({ execution_mode: "v2" });
    engineStatus.textContent = "Current engine: V2 - Applies to future runs only - server status unknown";
  });
  engineSelect.addEventListener("change", async () => {
    const selected = engineSelect.value;
    engineSelect.disabled = true;
    try {
      const response = await api.fetchApi(`${MODAL_PREFIX}/config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ execution_mode: selected }),
      });
      const data = await response.json();
      if (!response.ok || data.status === "error") throw new Error(data.message || "Could not save execution engine");
      window._comfyModalExecutionMode = selected;
      engineStatus.textContent = "Current engine: " + selected.toUpperCase() + " - Applies to future runs only";
      window.dispatchEvent(new CustomEvent("comfymodal:execution-mode-changed", { detail: data }));
    } catch (error) {
      engineStatus.textContent = error.message || "Could not save execution engine";
      engineStatus.style.color = "#e05050";
    } finally {
      engineSelect.disabled = false;
    }
  });
  const engineSyncHandler = (event) => {
    if (event && event.detail && event.detail.execution_mode) renderExecutionEngineConfig(event.detail);
  };
  window.addEventListener("comfymodal:execution-mode-changed", engineSyncHandler);
  scrollContent.appendChild(engineSection);

  // === OUTPUT OPTIONS SECTION (Collapsible) ===
  const _STORAGE_FORMAT = "comfymodal_output_format";
  const _STORAGE_QUALITY = "comfymodal_quality";
  const _STORAGE_WEBP_LC = "comfymodal_webp_lossless_compression";
  const _STORAGE_AUTOSAVE = "comfymodal_auto_save_local";
  const _STORAGE_SAVEFOLDER = "comfymodal_save_folder";
  const _STORAGE_SIDECAR = "comfymodal_save_metadata_sidecar";

  let _outFmtValue = localStorage.getItem(_STORAGE_FORMAT) || "original";
  let _qualValue = parseInt(localStorage.getItem(_STORAGE_QUALITY), 10) || 75;
  let _webpLcValue = localStorage.getItem(_STORAGE_WEBP_LC) || "balanced";
  let _autoSaveValue = localStorage.getItem(_STORAGE_AUTOSAVE) === "true";
  let _saveFolderValue = normalizeOutputSaveFolder(localStorage.getItem(_STORAGE_SAVEFOLDER));
  let _sidecarValue = localStorage.getItem(_STORAGE_SIDECAR) !== "false";

  function _persistOutputSettings() {
    localStorage.setItem(_STORAGE_FORMAT, _outFmtValue);
    localStorage.setItem(_STORAGE_QUALITY, _qualValue);
    localStorage.setItem(_STORAGE_WEBP_LC, _webpLcValue);
    localStorage.setItem(_STORAGE_AUTOSAVE, String(_autoSaveValue));
    localStorage.setItem(_STORAGE_SAVEFOLDER, _saveFolderValue);
    localStorage.setItem(_STORAGE_SIDECAR, String(_sidecarValue));
    window._comfyModalOutputOptions = {
      output_format: _outFmtValue,
      quality: _qualValue,
      webp_lossless_compression: _webpLcValue,
      auto_save_local: _autoSaveValue,
      save_folder: _saveFolderValue,
      save_metadata_sidecar: _sidecarValue,
    };
    // Sync to server — only update local/window state and notify
    // after a successful response.
    try {
      api.fetchApi(`${MODAL_PREFIX}/config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          output_format: _outFmtValue,
          quality: _qualValue,
          webp_lossless_compression: _webpLcValue,
          // Local-only: not forwarded to remote
          auto_save_local: _autoSaveValue,
          save_folder: _saveFolderValue,
          save_metadata_sidecar: _sidecarValue,
        }),
      }).then(function (resp) {
        if (resp && resp.ok) {
          try {
            window.dispatchEvent(new CustomEvent("comfymodal:output-preferences-changed", { detail: window._comfyModalOutputOptions }));
          } catch {}
        }
      }).catch(function () {
        // Server sync failure — local state preserved
      });
    } catch {}
  }

  // Init from server config — server is authoritative.
  // Apply all server values regardless of localStorage state so
  // initial sync always reflects the backend.
  (async () => {
    try {
      const r = await api.fetchApi(`${MODAL_PREFIX}/config`);
      const cfg = await r.json();
      if (cfg.output_format !== undefined) _outFmtValue = cfg.output_format;
      if (cfg.quality !== undefined) _qualValue = cfg.quality;
      if (cfg.webp_lossless_compression !== undefined) _webpLcValue = cfg.webp_lossless_compression;
      if (cfg.auto_save_local !== undefined) _autoSaveValue = Boolean(cfg.auto_save_local);
      if (cfg.save_folder) _saveFolderValue = normalizeOutputSaveFolder(cfg.save_folder);
      if (cfg.save_metadata_sidecar !== undefined) _sidecarValue = cfg.save_metadata_sidecar !== false;
      _persistOutputSettings();
    } catch {}
  })();

  const outputCollapsible = createCollapsibleSection("Output Options", { defaultOpen: false, badge: null });
  outputCollapsible.wrapper.querySelector("span:last-of-type").style.display = "none";
  const outContent = outputCollapsible.content;

  // -- Output format dropdown --
  const fmtRow = document.createElement("div");
  fmtRow.style.cssText = "display:flex; flex-direction:column; gap:4px; margin-bottom:8px;";

  const fmtLabel = document.createElement("span");
  fmtLabel.style.cssText = "font-size:12px; color:#aaa; font-weight:600;";
  fmtLabel.textContent = "Output format";

  const fmtSelect = document.createElement("select");
  fmtSelect.style.cssText = inputStyle();
  ["original", "webp_lossless", "webp_lossy", "jpeg"].forEach(v => {
    const opt = document.createElement("option");
    opt.value = v;
    opt.textContent = v === "original" ? "Original / PNG" : v === "webp_lossless" ? "WebP Lossless" : v === "webp_lossy" ? "WebP Lossy" : "JPEG";
    fmtSelect.appendChild(opt);
  });
  fmtSelect.value = _outFmtValue;

  fmtRow.appendChild(fmtLabel);
  fmtRow.appendChild(fmtSelect);
  outContent.appendChild(fmtRow);

  // -- Quality slider (visible for webp_lossy and jpeg) --
  const qualRow = document.createElement("div");
  qualRow.style.cssText = "display:flex; flex-direction:column; gap:4px; margin-bottom:8px;";

  const qualLabelRow = document.createElement("div");
  qualLabelRow.style.cssText = "display:flex; align-items:center; justify-content:space-between;";

  const qualLabel = document.createElement("span");
  qualLabel.style.cssText = "font-size:12px; color:#aaa; font-weight:600;";
  qualLabel.textContent = "Quality";

  const qualValueEl = document.createElement("span");
  qualValueEl.style.cssText = "font-size:11px; color:#888;";

  qualLabelRow.appendChild(qualLabel);
  qualLabelRow.appendChild(qualValueEl);

  const qualSlider = document.createElement("input");
  qualSlider.type = "range";
  qualSlider.min = "0";
  qualSlider.max = "100";
  qualSlider.step = "1";
  qualSlider.value = String(_qualValue);
  qualSlider.style.cssText = "width:100%; margin:0; accent-color:#3a6fcc;";
  qualValueEl.textContent = _qualValue;

  qualRow.appendChild(qualLabelRow);
  qualRow.appendChild(qualSlider);
  outContent.appendChild(qualRow);

  // -- WebP lossless compression dropdown --
  const wlcRow = document.createElement("div");
  wlcRow.style.cssText = "display:flex; flex-direction:column; gap:4px; margin-bottom:8px;";

  const wlcLabel = document.createElement("span");
  wlcLabel.style.cssText = "font-size:12px; color:#aaa; font-weight:600;";
  wlcLabel.textContent = "WebP lossless compression";

  const wlcSelect = document.createElement("select");
  wlcSelect.style.cssText = inputStyle();
  ["fast", "balanced", "max"].forEach(v => {
    const opt = document.createElement("option");
    opt.value = v;
    opt.textContent = v === "fast" ? "Fast" : v === "balanced" ? "Balanced" : "Max Compression";
    wlcSelect.appendChild(opt);
  });
  wlcSelect.value = _webpLcValue;

  wlcRow.appendChild(wlcLabel);
  wlcRow.appendChild(wlcSelect);
  outContent.appendChild(wlcRow);

  function _updateOutputVisibility() {
    const fmt = fmtSelect.value;
    qualRow.style.display = (fmt === "webp_lossy" || fmt === "jpeg") ? "" : "none";
    wlcRow.style.display = (fmt === "webp_lossless") ? "" : "none";
  }
  _updateOutputVisibility();

  fmtSelect.addEventListener("change", () => {
    _outFmtValue = fmtSelect.value;
    _updateOutputVisibility();
    _persistOutputSettings();
  });
  qualSlider.addEventListener("input", () => {
    _qualValue = parseInt(qualSlider.value, 10);
    qualValueEl.textContent = _qualValue;
    _persistOutputSettings();
  });
  wlcSelect.addEventListener("change", () => { _webpLcValue = wlcSelect.value; _persistOutputSettings(); });

  // -- Divider --
  const outDivider = document.createElement("div");
  outDivider.style.cssText = "border-top: 1px solid #3a3a3a; margin: 8px 0;";
  outContent.appendChild(outDivider);

  // -- Auto-save toggle --
  const autoSaveRow = document.createElement("div");
  autoSaveRow.style.cssText = "display:flex; align-items:center; gap:8px; margin-bottom:8px;";

  const autoSaveLabel = document.createElement("span");
  autoSaveLabel.style.cssText = "font-size:12px; color:#aaa; font-weight:600;";
  autoSaveLabel.textContent = "Auto-save outputs locally";

  const autoSaveToggle = document.createElement("input");
  autoSaveToggle.type = "checkbox";
  autoSaveToggle.checked = _autoSaveValue;
  autoSaveToggle.style.cssText = "width:16px; height:16px; accent-color:#3a6fcc;";

  autoSaveRow.appendChild(autoSaveToggle);
  autoSaveRow.appendChild(autoSaveLabel);
  outContent.appendChild(autoSaveRow);

  // -- Save folder --
  const saveFolderRow = document.createElement("div");
  saveFolderRow.style.cssText = "display:flex; flex-direction:column; gap:4px; margin-bottom:8px;";

  const saveFolderLabel = document.createElement("span");
  saveFolderLabel.style.cssText = "font-size:12px; color:#aaa; font-weight:600;";
  saveFolderLabel.textContent = "Save folder";

  const saveFolderInput = document.createElement("input");
  saveFolderInput.type = "text";
  saveFolderInput.value = _saveFolderValue;
  saveFolderInput.style.cssText = inputStyle();
  saveFolderInput.placeholder = DEFAULT_OUTPUT_SAVEFOLDER;

  saveFolderRow.appendChild(saveFolderLabel);
  saveFolderRow.appendChild(saveFolderInput);
  outContent.appendChild(saveFolderRow);

  // -- Sidecar checkbox --
  const sidecarRow = document.createElement("div");
  sidecarRow.style.cssText = "display:flex; align-items:center; gap:8px; margin-bottom:8px;";

  const sidecarToggle = document.createElement("input");
  sidecarToggle.type = "checkbox";
  sidecarToggle.checked = _sidecarValue;
  sidecarToggle.style.cssText = "width:16px; height:16px; accent-color:#3a6fcc;";

  const sidecarLabel = document.createElement("span");
  sidecarLabel.style.cssText = "font-size:12px; color:#aaa;";
  sidecarLabel.textContent = "Save metadata JSON sidecar";

  sidecarRow.appendChild(sidecarToggle);
  sidecarRow.appendChild(sidecarLabel);
  outContent.appendChild(sidecarRow);

  // -- Open output folder button --
  const openFolderBtn = document.createElement("button");
  openFolderBtn.textContent = "Open output folder";
  openFolderBtn.style.cssText = btnStyle() + "width:100%;";
  openFolderBtn.onclick = () => {
    const folder = normalizeOutputSaveFolder(saveFolderInput.value.trim() || DEFAULT_OUTPUT_SAVEFOLDER);
    try {
      api.fetchApi(`${MODAL_PREFIX}/open-folder`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: folder }),
      });
    } catch {}
  };
  outContent.appendChild(openFolderBtn);

  autoSaveToggle.addEventListener("change", () => { _autoSaveValue = autoSaveToggle.checked; _persistOutputSettings(); });
  saveFolderInput.addEventListener("change", () => {
    _saveFolderValue = normalizeOutputSaveFolder(saveFolderInput.value);
    saveFolderInput.value = _saveFolderValue;
    _persistOutputSettings();
  });
  sidecarToggle.addEventListener("change", () => { _sidecarValue = sidecarToggle.checked; _persistOutputSettings(); });

  function _updateProductionSummary(el) {
    try {
      const graph = app.graph;
      if (!graph) { el.textContent = "Disabled: no graph available"; return; }
      const outputNodes = [];
      const bypassNodes = [];
      for (const node of graph._nodes || []) {
        if (node.properties?.comfymodal_production_output) outputNodes.push(node);
        if (node.properties?.comfymodal_bypass_in_production) bypassNodes.push(node);
      }
      const allNodes = graph._nodes || [];
      const bypassIds = new Set(bypassNodes.map(n => String(n.id)));
      const kept = allNodes.filter(n => !bypassIds.has(String(n.id))).length;
      const nOutputs = outputNodes.length;
      const nBypass = bypassNodes.length;
      const nRemoved = 0;
      if (!prodToggle.checked) {
        el.textContent = "Disabled: production toggle off";
        return;
      }
      if (!graph._nodes || graph._nodes.length === 0) {
        el.textContent = "Disabled: no workflow loaded";
        return;
      }
      if (nOutputs === 0) {
        el.textContent = "";
        const errSpan = document.createElement("span");
        errSpan.style.color = "#e05050";
        errSpan.textContent = "Disabled: no production output selected";
        el.appendChild(errSpan);
        return;
      }
      // Check if options are attached to graph.extra (indicates settings UI was initialized)
      const extraProd = app.graph?.extra?.comfymodal?.production_mode_enabled;
      if (extraProd === undefined && nOutputs > 0) {
        // Options not yet attached to graph extra — this is a preview-only state
        el.textContent = "";
        const warnSpan = document.createElement("span");
        warnSpan.style.color = "#e8a020";
        warnSpan.textContent = "Options not attached: production not persisted";
        el.appendChild(warnSpan);
        return;
      }
      // Check if selected output IDs exist in serialized API prompt keys
      // (strict validation against the actual serialized graph)
      const serializedKeys = Object.keys(graph._nodes_by_id || {});
      const outputIds = outputNodes.map(n => String(n.id));
      // All output IDs must be valid keys in the serialized graph
      const missingInSerialized = outputIds.filter(id => !serializedKeys.includes(id));
      if (missingInSerialized.length > 0 && serializedKeys.length > 0) {
        el.textContent = "";
        const errSpan = document.createElement("span");
        errSpan.style.color = "#e05050";
        errSpan.textContent = "Selected output absent from serialized workflow: " + missingInSerialized.join(", ");
        el.appendChild(errSpan);
        return;
      }
      el.textContent = "";
      if (_lastProductionEvidence) {
        // Result-only state: plan was already used
        const ev = _lastProductionEvidence;
        const hashShort = (ev.production_plan_hash || "").substring(0, 8);
        const runnerHashShort = (ev.runner_workflow_hash || ev.executed_workflow_hash || "").substring(0, 8);
        const nProduced = ev.production_output_count != null ? ev.production_output_count : (ev.output_count || 0);
        const titleDiv = document.createElement("div");
        titleDiv.style.cssText = "font-weight:600;margin-bottom:2px;color:#7ed321;";
        titleDiv.textContent = "Plan ready: " + (ev.kept_count || 0) + " kept, " + (ev.removed_count || 0) + " removed, " + nProduced + "/1 outputs";
        el.appendChild(titleDiv);
        const lastRun = document.createElement("div");
        lastRun.style.cssText = "font-size:10px;color:#888;margin-bottom:4px;";
        lastRun.textContent = "Last run plan: " + hashShort + " | runner: " + runnerHashShort;
        el.appendChild(lastRun);
        const bypassedCount = ev.bypassed_count != null ? ev.bypassed_count : 0;
        el.appendChild(document.createTextNode("Bypassed: " + bypassedCount + " nodes"));
        if (ev.executed_workflow_hash && ev.executed_workflow_hash === ev.compiled_workflow_hash) {
          el.appendChild(document.createElement("br"));
          const okSpan = document.createElement("span");
          okSpan.style.color = "#7ed321";
          okSpan.textContent = "\u2713 Executed == compiled";
          el.appendChild(okSpan);
        } else if (ev.executed_workflow_hash && ev.compiled_workflow_hash) {
          el.appendChild(document.createElement("br"));
          const warnSpan = document.createElement("span");
          warnSpan.style.color = "#e8a020";
          warnSpan.textContent = "Warning: executed \u2260 compiled";
          el.appendChild(warnSpan);
        }
        // Show production_plan_used flag when present
        if (ev.production_plan_used) {
          el.appendChild(document.createElement("br"));
          const okSpan = document.createElement("span");
          okSpan.style.color = "#7ed321";
          okSpan.textContent = "\u2713 production_plan_used=true";
          el.appendChild(okSpan);
        }
      } else {
        // Preview: show counts but never say "ready"
        const titleDiv = document.createElement("div");
        titleDiv.style.cssText = "font-weight:600;margin-bottom:2px;";
        titleDiv.textContent = "Production preview (" + nOutputs + "/1 output)";
        el.appendChild(titleDiv);
        el.appendChild(document.createTextNode("Kept: " + kept + " nodes"));
        el.appendChild(document.createElement("br"));
        el.appendChild(document.createTextNode("Removed: " + nRemoved + " nodes (preview)"));
        el.appendChild(document.createElement("br"));
        el.appendChild(document.createTextNode("Bypassed: " + nBypass + " nodes"));
        el.appendChild(document.createElement("br"));
        el.appendChild(document.createTextNode("Outputs: " + nOutputs));
        el.appendChild(document.createElement("br"));
        el.appendChild(document.createTextNode("Sampler previews: disabled"));
        el.appendChild(document.createElement("br"));
        el.appendChild(document.createTextNode("Direct outputs: " + nOutputs));
      }
    } catch (e) {
      el.textContent = "";
      const errSpan = document.createElement("span");
      errSpan.style.color = "#e05050";
      errSpan.textContent = "Plan error: " + e.message;
      el.appendChild(errSpan);
    }
  }

  scrollContent.appendChild(outputCollapsible.wrapper);

  // ── Production Mode (always visible, not inside collapsed section) ──
  const prodDivider = document.createElement("div");
  prodDivider.style.cssText = "border-top: 1px solid #3a3a3a; margin: 8px 0;";
  scrollContent.appendChild(prodDivider);

  const prodRow = document.createElement("div");
  prodRow.style.cssText = "display:flex; align-items:center; gap:8px; margin-bottom:6px;";

  const prodToggle = document.createElement("input");
  prodToggle.type = "checkbox";
  prodToggle.id = "cm-prod-toggle";
  const _storedProd = app.graph?.extra?.comfymodal?.production_mode_enabled;
  prodToggle.checked = _storedProd !== undefined ? _storedProd : localStorage.getItem(STORAGE_KEY_PRODUCTION) === "true";
  prodToggle.style.cssText = "width:16px; height:16px; accent-color:#3a6fcc; flex-shrink:0;";

  const prodLabel = document.createElement("label");
  prodLabel.style.cssText = "font-size:12px; color:#aaa; font-weight:600;";
  prodLabel.textContent = "Simulate Production";
  prodLabel.setAttribute("for", "cm-prod-toggle");

  prodRow.appendChild(prodToggle);
  prodRow.appendChild(prodLabel);
  scrollContent.appendChild(prodRow);

  const prodSummaryEl = document.createElement("div");
  prodSummaryEl.style.cssText = "font-size:11px; color:#666; line-height:1.5; padding:6px 8px; background:#1a1a2a; border-radius:4px; border:1px solid #2a2a3a; display:" + (prodToggle.checked ? "" : "none") + ";";
  prodSummaryEl.textContent = "Production disabled";
  scrollContent.appendChild(prodSummaryEl);
  if (prodToggle.checked) {
    setTimeout(() => { _updateProductionSummary(prodSummaryEl); }, 100);
  }

  prodToggle.addEventListener("change", () => {
    if (!app.graph) return;
    if (!app.graph.extra) app.graph.extra = {};
    if (!app.graph.extra.comfymodal) app.graph.extra.comfymodal = {};
    app.graph.extra.comfymodal.production_mode_enabled = prodToggle.checked;
    localStorage.setItem(STORAGE_KEY_PRODUCTION, String(prodToggle.checked));
    if (prodToggle.checked) {
      prodSummaryEl.style.display = "";
      _updateProductionSummary(prodSummaryEl);
    } else {
      prodSummaryEl.style.display = "none";
      _lastProductionEvidence = null;
    }
    app.graph.setDirtyCanvas(true, true);
  });

  // === WORKSPACE SECTION (Collapsible) ===
  let currentSwapId = null;
  let swapPollTimer = null;

  const workspaceSection = createCollapsibleSection("Workspace", { defaultOpen: true, badge: null });
  const workspaceContent = workspaceSection.content;

  const workspaceSelect = document.createElement("select");
  workspaceSelect.style.cssText = inputStyle() + "width:100%; margin-bottom:8px;";
  workspaceContent.appendChild(workspaceSelect);

  const workspaceStatus = document.createElement("div");
  workspaceStatus.style.cssText = "font-size:11px; color:#888; min-height:16px; margin-bottom:8px;";
  workspaceContent.appendChild(workspaceStatus);

  const addWsBtn = document.createElement("button");
  addWsBtn.textContent = "+ Add Workspace";
  addWsBtn.style.cssText = btnStyle() + "margin-bottom:6px;";
  addWsBtn.onclick = () => openAddWorkspaceModal();
  workspaceContent.appendChild(addWsBtn);

  const editWsBtn = document.createElement("button");
  editWsBtn.textContent = "Edit Workspace";
  editWsBtn.style.cssText = btnStyle() + "margin-bottom:6px;";
  editWsBtn.disabled = true;
  workspaceContent.appendChild(editWsBtn);

  const swapBtn = document.createElement("button");
  swapBtn.textContent = "Swap Workspace";
  swapBtn.style.cssText = btnStyle("primary") + "margin-bottom:6px;";
  workspaceContent.appendChild(swapBtn);

  const repairBtn = document.createElement("button");
  repairBtn.textContent = "Manifest Repair";
  repairBtn.style.cssText = btnStyle() + "margin-bottom:6px;";
  workspaceContent.appendChild(repairBtn);

  const exportBtn = document.createElement("button");
  exportBtn.textContent = "Export Workflow Manifest";
  exportBtn.style.cssText = btnStyle() + "margin-bottom:6px;";
  workspaceContent.appendChild(exportBtn);

  const importBtn = document.createElement("button");
  importBtn.textContent = "Import Workflow Manifest";
  importBtn.style.cssText = btnStyle();
  workspaceContent.appendChild(importBtn);

  const installBtn = document.createElement("button");
  installBtn.textContent = "Install from Manifest";
  installBtn.title = "Download one or more manifest-tracked models to the current active workspace";
  installBtn.style.cssText = btnStyle("primary") + "margin-top:6px;";
  workspaceContent.appendChild(installBtn);

  const swapProgress = document.createElement("div");
  swapProgress.style.cssText = "font-size:11px; color:#aaa; margin-top:8px; min-height:32px;";
  workspaceContent.appendChild(swapProgress);

  // Helper: set swapProgress text with color via DOM (avoid innerHTML with dynamic data)
  function _setSwapProgress(text, color) {
    swapProgress.textContent = "";
    const span = document.createElement("span");
    span.style.color = color;
    span.textContent = text;
    swapProgress.appendChild(span);
  }

  // Persistent deploy log container (scroll-safe: textContent updates don't reset scroll)
  const deployLogPre = document.createElement("pre");
  deployLogPre.style.cssText = "display:none;margin:6px 0 0;padding:6px;background:#111;color:#aaa;font-size:10px;line-height:1.4;max-height:200px;overflow-y:auto;border-radius:4px;border:1px solid #333;white-space:pre-wrap;word-break:break-all;";
  workspaceContent.appendChild(deployLogPre);

  scrollContent.appendChild(workspaceSection.wrapper);

  async function loadWorkspaces() {
    const resp = await api.fetchApi(`${MODAL_PREFIX}/workspaces`);
    const data = await resp.json();
    const selectedId = workspaceSelect.value;
    workspaceSelect.innerHTML = "";
    (data.workspaces || []).forEach((workspace) => {
      const opt = document.createElement("option");
      opt.value = workspace.id;
      opt.textContent = workspace.label;
      if (workspace.id === selectedId || (!selectedId && workspace.id === data.active_workspace_id)) opt.selected = true;
      workspaceSelect.appendChild(opt);
    });
    if (!workspaceSelect.value && workspaceSelect.options.length) {
      workspaceSelect.selectedIndex = 0;
    }
    editWsBtn.disabled = !workspaceSelect.options.length;
    workspaceStatus.textContent = data.workspaces?.length
      ? `Active workspace: ${workspaceSelect.options[workspaceSelect.selectedIndex]?.textContent || "none"}`
      : "No saved Modal workspaces yet.";
  }

  async function openAddWorkspaceModal() {
    const overlay = document.createElement("div");
    overlay.style.cssText = "position:fixed; inset:0; background:rgba(0,0,0,0.65); display:flex; align-items:center; justify-content:center; z-index:10001;";
    overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.remove(); });
    const modal = document.createElement("div");
    modal.style.cssText = "width:min(460px, 90vw); background:#171717; border:1px solid #333; border-radius:8px; padding:16px; display:flex; flex-direction:column; gap:10px;";

    const title = document.createElement("div");
    title.style.cssText = "font-weight:600; font-size:14px; margin-bottom:4px;";
    title.textContent = "Add Modal Workspace";
    modal.appendChild(title);

    const labelInput = document.createElement("input");
    labelInput.type = "text";
    labelInput.placeholder = "Workspace label (e.g. Studio A)";
    labelInput.style.cssText = inputStyle();
    modal.appendChild(labelInput);

    const tokenIdInput = document.createElement("input");
    tokenIdInput.type = "text";
    tokenIdInput.placeholder = "Token ID (ak-...)";
    tokenIdInput.style.cssText = inputStyle();
    modal.appendChild(tokenIdInput);

    const tokenSecretInput = document.createElement("input");
    tokenSecretInput.type = "password";
    tokenSecretInput.placeholder = "Token Secret (as-...)";
    tokenSecretInput.style.cssText = inputStyle();
    modal.appendChild(tokenSecretInput);

    const errorEl = document.createElement("div");
    errorEl.style.cssText = "font-size:11px; color:#e05050; min-height:14px;";
    modal.appendChild(errorEl);

    const btnRow = document.createElement("div");
    btnRow.style.cssText = "display:flex; gap:8px; justify-content:flex-end;";

    const cancelBtn = document.createElement("button");
    cancelBtn.textContent = "Cancel";
    cancelBtn.style.cssText = btnStyle();
    cancelBtn.onclick = () => overlay.remove();
    btnRow.appendChild(cancelBtn);

    const saveBtn = document.createElement("button");
    saveBtn.textContent = "Save Workspace";
    saveBtn.style.cssText = btnStyle("primary");
    saveBtn.onclick = async () => {
      const label = labelInput.value.trim();
      const token_id = tokenIdInput.value.trim();
      const token_secret = tokenSecretInput.value.trim();
      errorEl.textContent = "";
      if (!label || !token_id || !token_secret) {
        errorEl.textContent = "All fields required.";
        return;
      }
      saveBtn.disabled = true;
      saveBtn.textContent = "Saving\u2026";
      try {
        const resp = await api.fetchApi(`${MODAL_PREFIX}/workspaces`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ label, token_id, token_secret, set_active: false }),
        });
        const data = await resp.json();
        if (data.status !== "ok") throw new Error(data.message || "Save failed");
        overlay.remove();
        showToast("Workspace saved.", "success");
        await loadWorkspaces();
      } catch (e) {
        errorEl.textContent = "Error: " + e.message;
      } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = "Save Workspace";
      }
    };
    btnRow.appendChild(saveBtn);
    modal.appendChild(btnRow);
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
    setTimeout(() => labelInput.focus(), 100);
  }

  async function openEditWorkspaceModal() {
    const selectedOption = workspaceSelect.options[workspaceSelect.selectedIndex];
    if (!selectedOption) return;
    const overlay = document.createElement("div");
    overlay.style.cssText = "position:fixed; inset:0; background:rgba(0,0,0,0.65); display:flex; align-items:center; justify-content:center; z-index:10001;";
    overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.remove(); });
    const modal = document.createElement("div");
    modal.style.cssText = "width:min(460px, 90vw); background:#171717; border:1px solid #333; border-radius:8px; padding:16px; display:flex; flex-direction:column; gap:10px;";

    const title = document.createElement("div");
    title.style.cssText = "font-weight:600; font-size:14px; margin-bottom:4px;";
    title.textContent = "Edit Modal Workspace";
    modal.appendChild(title);

    const labelInput = document.createElement("input");
    labelInput.type = "text";
    labelInput.placeholder = "Workspace label (e.g. Studio A)";
    labelInput.value = selectedOption.textContent || "";
    labelInput.style.cssText = inputStyle();
    modal.appendChild(labelInput);

    const tokenIdInput = document.createElement("input");
    tokenIdInput.type = "text";
    tokenIdInput.placeholder = "Token ID (ak-...) — Leave blank to keep current";
    tokenIdInput.style.cssText = inputStyle();
    modal.appendChild(tokenIdInput);

    const tokenSecretInput = document.createElement("input");
    tokenSecretInput.type = "password";
    tokenSecretInput.placeholder = "Token Secret (as-...) — Leave blank to keep current";
    tokenSecretInput.style.cssText = inputStyle();
    modal.appendChild(tokenSecretInput);

    const helpEl = document.createElement("div");
    helpEl.style.cssText = "font-size:11px; color:#888; min-height:14px;";
    helpEl.textContent = "Leave blank to keep current credentials.";
    modal.appendChild(helpEl);

    const errorEl = document.createElement("div");
    errorEl.style.cssText = "font-size:11px; color:#e05050; min-height:14px;";
    modal.appendChild(errorEl);

    const btnRow = document.createElement("div");
    btnRow.style.cssText = "display:flex; gap:8px; justify-content:flex-end;";

    const cancelBtn = document.createElement("button");
    cancelBtn.textContent = "Cancel";
    cancelBtn.style.cssText = btnStyle();
    cancelBtn.onclick = () => overlay.remove();
    btnRow.appendChild(cancelBtn);

    const saveBtn = document.createElement("button");
    saveBtn.textContent = "Save Workspace";
    saveBtn.style.cssText = btnStyle("primary");
    saveBtn.onclick = async () => {
      const label = labelInput.value.trim();
      const token_id = tokenIdInput.value.trim();
      const token_secret = tokenSecretInput.value.trim();
      errorEl.textContent = "";
      if (!label) {
        errorEl.textContent = "Workspace label required.";
        return;
      }
      saveBtn.disabled = true;
      saveBtn.textContent = "Saving…";
      try {
        const resp = await api.fetchApi(`${MODAL_PREFIX}/workspaces`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ workspace_id: selectedOption.value, label, token_id, token_secret, set_active: false }),
        });
        const data = await resp.json();
        if (data.status !== "ok") throw new Error(data.message || "Save failed");
        overlay.remove();
        showToast("Workspace updated.", "success");
        await loadWorkspaces();
        workspaceSelect.value = selectedOption.value;
      } catch (e) {
        errorEl.textContent = "Error: " + e.message;
      } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = "Save Workspace";
      }
    };
    btnRow.appendChild(saveBtn);
    modal.appendChild(btnRow);
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
    setTimeout(() => labelInput.focus(), 100);
  }

  editWsBtn.onclick = () => openEditWorkspaceModal();
  workspaceSelect.onchange = () => {
    editWsBtn.disabled = !workspaceSelect.options.length;
    workspaceStatus.textContent = workspaceSelect.options.length
      ? `Active workspace: ${workspaceSelect.options[workspaceSelect.selectedIndex]?.textContent || "none"}`
      : "No saved Modal workspaces yet.";
  };

  function setWorkspaceBusy(isBusy) {
    addWsBtn.disabled = isBusy;
    editWsBtn.disabled = isBusy || !workspaceSelect.options.length;
    swapBtn.disabled = isBusy;
    repairBtn.disabled = isBusy;
    installBtn.disabled = isBusy;
    exportBtn.disabled = isBusy;
    importBtn.disabled = isBusy;
    workspaceSelect.disabled = isBusy;
  }

  async function pollSwapJob() {
    if (!currentSwapId) return;
    const resp = await api.fetchApi(`${MODAL_PREFIX}/workspaces/swap/${currentSwapId}`);
    const data = await resp.json();
    // Hide deploy log in all phases; only the "deploying" handler shows it
    deployLogPre.style.display = "none";
    if (data.status === "running") {
      const phase = data.phase;
      let msg = "";
      if (phase === "downloading_models") {
        const cur = data.download_current_name || "";
        const done = data.download_completed || 0;
        const total = (data.download_total || 0) + (data.download_skipped || 0);
        const pct = data.download_pct_current || 0;
        const msg = data.download_message || "";
        const displayMsg = msg || `Preparing downloads… ${done}/${total}`;
        swapProgress.textContent = "";
        const textSpan = document.createElement("span");
        textSpan.style.color = "#f5a623";
        textSpan.textContent = displayMsg;
        swapProgress.appendChild(textSpan);
        const barOuter = document.createElement("div");
        barOuter.style.cssText = "margin-top:4px;width:100%;height:6px;background:#333;border-radius:3px;overflow:hidden;";
        const barInner = document.createElement("div");
        barInner.style.cssText = `width:${pct}%;height:100%;background:#f5a623;border-radius:3px;transition:width 0.5s;`;
        barOuter.appendChild(barInner);
        swapProgress.appendChild(barOuter);
      } else if (phase === "syncing_custom_nodes") {
        const syncMsg = data.sync_message || "Syncing custom nodes to Modal…";
        _setSwapProgress(syncMsg, "#f5a623");
        if (data.deploy_log_tail) {
          deployLogPre.textContent = data.deploy_log_tail;
          deployLogPre.style.display = "block";
        }
      } else if (phase === "deploying") {
        const msg = data.deploy_message || "Deploying workspace…";
        _setSwapProgress(msg, "#f5a623");
        if (data.deploy_log_tail) {
          deployLogPre.textContent = data.deploy_log_tail;
          deployLogPre.style.display = "block";
        } else {
          deployLogPre.style.display = "none";
        }
      } else {
        _setSwapProgress(`Phase: ${phase.replace(/_/g, " ")}`, "#f5a623");
      }
      swapPollTimer = setTimeout(pollSwapJob, 1000);
      return;
    }
    setWorkspaceBusy(false);
    if (data.status === "ok") {
      const dl = data.download_summary || `${data.installed_model_count} installed, ${data.skipped_model_count} skipped`;
      const removalNote = data.remove_summary ? ` ${data.remove_summary}.` : "";
      _setSwapProgress(`Done — ${data.workspace_label}: ${dl}.${removalNote} Custom nodes synced. Deploy started.`, "#7ed321");
      showToast("Workspace swap complete", "success");
      await loadWorkspaces();
      await loadModels();
      await loadSyncStatus();
      startDeployPoll();
      return;
    }
    if (data.status === "repair_required") {
      _setSwapProgress(`Swap blocked: ${data.message || "manifest repair required"}`, "#e07070");
      showToast("Manifest repair required before swap can continue", "info");
      await openManifestRepairModal(data.issues || []);
      return;
    }
    const errMsg = data.download_message || data.deploy_message || data.sync_message || data.error || data.message || "Workspace swap failed";
    _setSwapProgress(errMsg, "#e05050");
    showToast(errMsg, "error");
  }

  function inferSourceKind(url) {
    if (/huggingface\.co/i.test(url)) return "huggingface";
    if (/civitai\.com/i.test(url)) return "civitai";
    if (/^https?:\/\//i.test(url)) return "direct";
    return "unknown";
  }

  async function openManifestRepairModal(prefetchedIssues = null) {
    const scanResp = prefetchedIssues ? null : await api.fetchApi(`${MODAL_PREFIX}/manifest/repair/scan`, { method: "POST" });
    const scanData = prefetchedIssues ? { issues: prefetchedIssues } : await scanResp.json();
    const issues = scanData.issues || [];
    if (!issues.length) {
      showToast("No manifest issues found. The manifest is empty until you install models — use the Add Model section above to install and track models.", "info");
      return;
    }

    const overlay = document.createElement("div");
    overlay.style.cssText = "position:fixed; inset:0; background:rgba(0,0,0,0.65); display:flex; align-items:center; justify-content:center; z-index:10001;";
    overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.remove(); });
    const modal = document.createElement("div");
    modal.style.cssText = "width:min(1100px, 95vw); max-height:80vh; background:#171717; border:1px solid #333; border-radius:8px; display:flex; flex-direction:column; overflow:hidden;";

    const headerRow = document.createElement("div");
    headerRow.style.cssText = "padding:14px 16px 6px; font-weight:600; font-size:13px;";
    headerRow.textContent = "Manifest Repair";
    modal.appendChild(headerRow);

    const tableWrap = document.createElement("div");
    tableWrap.style.cssText = "flex:1; overflow-y:auto; padding:4px 16px; min-height:100px; max-height:55vh;";
    const table = document.createElement("table");
    table.style.cssText = "width:100%; border-collapse:collapse; font-size:12px;";
    const thead = document.createElement("thead");
    const hdr = document.createElement("tr");
    const colDefs = [
      { label: "Folder", width: "12%" },
      { label: "Filename", width: "22%" },
      { label: "URL", width: "30%" },
      { label: "Source", width: "11%" },
      { label: "Remove", width: "8%" },
      { label: "", width: "17%" },
    ];
    colDefs.forEach((c) => {
      const th = document.createElement("th");
      th.textContent = c.label;
      th.style.cssText = `text-align:left;position:sticky;top:0;background:#171717;padding:6px 4px 8px;font-weight:600;width:${c.width};white-space:nowrap;`;
      hdr.appendChild(th);
    });
    thead.appendChild(hdr);
    table.appendChild(thead);

    const body = document.createElement("tbody");
    const rows = issues.map((issue) => {
      const tr = document.createElement("tr");

      // Folder
      const folderTd = document.createElement("td");
      folderTd.style.cssText = "padding:5px 4px;vertical-align:middle;white-space:nowrap;";
      folderTd.textContent = issue.folder || "";
      tr.appendChild(folderTd);

      // Filename
      const nameTd = document.createElement("td");
      nameTd.style.cssText = "padding:5px 4px;vertical-align:middle;word-break:break-all;";
      nameTd.textContent = issue.filename || "";
      tr.appendChild(nameTd);

      // URL input
      const urlTd = document.createElement("td");
      urlTd.style.cssText = "padding:5px 4px;vertical-align:middle;";
      const urlInput = document.createElement("input");
      urlInput.type = "text";
      urlInput.value = issue.url || "";
      urlInput.placeholder = "https://huggingface.co/...";
      urlInput.style.cssText = inputStyle() + "width:100%;box-sizing:border-box;";
      urlInput.addEventListener("input", () => {
        const detected = inferSourceKind(urlInput.value);
        if (detected !== "unknown") sourceSelect.value = detected;
      });
      urlTd.appendChild(urlInput);
      tr.appendChild(urlTd);

      // Source select
      const sourceTd = document.createElement("td");
      sourceTd.style.cssText = "padding:5px 4px;vertical-align:middle;";
      const sourceSelect = document.createElement("select");
      sourceSelect.style.cssText = inputStyle() + "width:100%;box-sizing:border-box;";
      ["unknown", "huggingface", "civitai", "direct"].forEach((kind) => {
        const opt = document.createElement("option");
        opt.value = kind;
        opt.textContent = kind;
        if ((issue.source_kind || "unknown") === kind) opt.selected = true;
        sourceSelect.appendChild(opt);
      });
      sourceTd.appendChild(sourceSelect);
      tr.appendChild(sourceTd);

      // Remove checkbox
      const removeTd = document.createElement("td");
      removeTd.style.cssText = "padding:5px 4px;vertical-align:middle;text-align:center;";
      const removeCb = document.createElement("input");
      removeCb.type = "checkbox";
      removeCb.checked = !!issue.remove_on_swap;
      removeCb.title = "Remove from workspace on next swap";
      removeCb.style.cssText = "width:14px;height:14px;accent-color:#e07070;";
      removeTd.appendChild(removeCb);
      tr.appendChild(removeTd);

      // Delete button
      const actionTd = document.createElement("td");
      actionTd.style.cssText = "padding:5px 4px;vertical-align:middle;white-space:nowrap;";
      const delBtn = document.createElement("button");
      delBtn.textContent = "Delete";
      delBtn.style.cssText = "background:#4a1a1a;border:1px solid #6a2a2a;color:#e07070;padding:3px 8px;border-radius:3px;cursor:pointer;font-size:11px;line-height:1.4;";
      delBtn.onclick = async () => {
        delBtn.disabled = true;
        delBtn.textContent = "…";
        try {
          const resp = await api.fetchApi(`${MODAL_PREFIX}/manifest/repair/delete-placeholder`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ folder: issue.folder, filename: issue.filename }),
          });
          const data = await resp.json();
          if (!data.removed) {
            delBtn.disabled = false;
            delBtn.textContent = "Delete";
            showToast(data.message || `Couldn't delete ${issue.filename}`, "info");
            return;
          }
          tr.remove();
          const idx = rows.indexOf(rowItem);
          if (idx !== -1) rows.splice(idx, 1);
          showToast(`Deleted ${issue.filename}`, "info");
        } catch (e) {
          delBtn.disabled = false;
          delBtn.textContent = "Delete";
        }
      };
      actionTd.appendChild(delBtn);
      tr.appendChild(actionTd);

      body.appendChild(tr);
      const rowItem = { issue, urlInput, sourceSelect, removeCb, delBtn };
      return rowItem;
    });
    table.appendChild(body);
    tableWrap.appendChild(table);
    modal.appendChild(tableWrap);

    const footer = document.createElement("div");
    footer.style.cssText = "display:flex; gap:8px; justify-content:flex-end; padding:10px 16px 14px; flex-shrink:0;";
    const cancelBtn = document.createElement("button");
    cancelBtn.textContent = "Cancel";
    cancelBtn.style.cssText = btnStyle();
    cancelBtn.onclick = () => overlay.remove();
    const skipAllBtn = document.createElement("button");
    skipAllBtn.textContent = "Skip All";
    skipAllBtn.style.cssText = btnStyle();
    skipAllBtn.onclick = async () => {
      const updates = rows.map(({ issue }) => ({ folder: issue.folder, filename: issue.filename, skip: true }));
      await api.fetchApi(`${MODAL_PREFIX}/manifest/repair/apply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ updates }),
      });
      overlay.remove();
      showToast("Manifest repair skipped for selected rows.", "info");
    };
    const saveAllBtn = document.createElement("button");
    saveAllBtn.textContent = "Save All Valid";
    saveAllBtn.style.cssText = btnStyle("primary");
    saveAllBtn.onclick = async () => {
      const updates = rows
        .filter(({ urlInput, removeCb }) => urlInput.value.trim() || removeCb.checked)
        .map(({ issue, urlInput, sourceSelect, removeCb }) => ({
          folder: issue.folder,
          filename: issue.filename,
          url: urlInput.value.trim(),
          source_kind: sourceSelect.value,
          ...(removeCb.checked ? { remove: true } : {}),
        }));
      const resp = await api.fetchApi(`${MODAL_PREFIX}/manifest/repair/apply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ updates }),
      });
      const data = await resp.json();
      overlay.remove();
      showToast(data.issues.length ? "Manifest still has unresolved rows." : "Manifest repair saved.", data.issues.length ? "info" : "success");
    };
    footer.appendChild(cancelBtn);
    footer.appendChild(skipAllBtn);
    footer.appendChild(saveAllBtn);
    modal.appendChild(footer);
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
  }

  async function openImportConflictModal(conflicts, payload) {
    const resolutions = {};
    conflicts.forEach((item) => {
      resolutions[`${item.folder}/${item.filename}`] = window.confirm(`Use imported URL for ${item.filename}?\nLocal: ${item.local_url}\nImported: ${item.imported_url}`)
        ? "use_imported"
        : "keep_local";
    });
    const resp = await api.fetchApi(`${MODAL_PREFIX}/workflow-manifest/import`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.assign({}, payload, { conflict_resolutions: resolutions })),
    });
    return await resp.json();
  }

  swapBtn.onclick = async () => {
    setWorkspaceBusy(true);
    _setSwapProgress("Scanning workspace and manifest…", "#888");
    try {
      const scanResp = await api.fetchApi(`${MODAL_PREFIX}/workspaces/swap`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workspace_id: workspaceSelect.value }),
      });
      const scanData = await scanResp.json();
      if (scanData.status === "busy") {
        setWorkspaceBusy(false);
        _setSwapProgress(scanData.message || "Deploy already running — try again later.", "#888");
        return;
      }
      if (scanData.status === "error") {
        setWorkspaceBusy(false);
        _setSwapProgress(scanData.message || "Workspace swap failed.", "#e05050");
        return;
      }
      if (scanData.status === "confirm_required") {
        const ok = await showConfirm("A prompt is still running. Switch workspaces anyway?");
        if (!ok) {
          setWorkspaceBusy(false);
          _setSwapProgress("Swap cancelled.", "#888");
          return;
        }
        const retry = await api.fetchApi(`${MODAL_PREFIX}/workspaces/swap`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ workspace_id: workspaceSelect.value, confirm_prompt_interrupt: true }),
        });
        const retryData = await retry.json();
        if (retryData.status === "review_required") {
          await showSwapReviewDialog({ ...retryData, confirm_prompt_interrupt: true });
          return;
        }
        if (retryData.status === "repair_required") {
          setWorkspaceBusy(false);
          _setSwapProgress(retryData.message || "Swap blocked: manifest repair required.", "#e07070");
          await openManifestRepairModal(retryData.issues || []);
          return;
        }
        if (retryData.status === "busy" || retryData.status === "error") {
          setWorkspaceBusy(false);
          _setSwapProgress(retryData.message || "Workspace swap failed.", "#e05050");
          return;
        }
        currentSwapId = retryData.swap_id;
        _setSwapProgress("Swap started…", "#888");
        pollSwapJob();
        return;
      }
      if (scanData.status === "repair_required") {
        setWorkspaceBusy(false);
        _setSwapProgress(scanData.message || "Swap blocked: manifest repair required.", "#e07070");
        await openManifestRepairModal(scanData.issues || []);
        return;
      }
      if (scanData.status === "review_required") {
        await showSwapReviewDialog(scanData);
        return;
      }
      // Fallback: started directly (no review phase)
      currentSwapId = scanData.swap_id;
      _setSwapProgress("Preparing downloads…", "#f5a623");
      pollSwapJob();
    } catch (e) {
      setWorkspaceBusy(false);
      _setSwapProgress(`Error: ${e.message}`, "#e05050");
    }
  };

  async function showSwapReviewDialog(data) {
    const toInstall = data.to_install || [];
    const alreadyPresent = data.already_present || [];
    const toRemove = data.to_remove || [];
    const installCount = data.install_count || 0;
    const presentCount = data.present_count || 0;

    const overlay = document.createElement("div");
    overlay.style.cssText = "position:fixed; inset:0; background:rgba(0,0,0,0.65); display:flex; align-items:center; justify-content:center; z-index:10001;";
    overlay.addEventListener("click", (e) => { if (e.target === overlay) { overlay.remove(); setWorkspaceBusy(false); swapProgress.innerHTML = ""; } });

    const modal = document.createElement("div");
    modal.style.cssText = "width:min(660px, 95vw); max-height:75vh; background:#171717; border:1px solid #333; border-radius:8px; display:flex; flex-direction:column; overflow:hidden;";

    const header = document.createElement("div");
    header.style.cssText = "padding:16px 16px 8px; font-weight:600; font-size:13px;";
    header.textContent = "Workspace: ";
    const wsSpan = document.createElement("span");
    wsSpan.style.color = "#6a9fd8";
    wsSpan.textContent = data.workspace_label || "unknown";
    header.appendChild(wsSpan);
    modal.appendChild(header);

    const body = document.createElement("div");
    body.style.cssText = "flex:1; overflow-y:auto; padding:4px 16px 8px; font-size:12px; line-height:1.6; color:#ccc;";
    const addBodyText = (text, style = "") => {
      const row = document.createElement("div");
      row.textContent = text;
      row.style.cssText = style;
      body.appendChild(row);
      return row;
    };

    if (installCount === 0) {
      addBodyText(
        "All manifest models are already in the target workspace. Custom nodes will still be synced and a deploy will run.",
        "color:#aaa;"
      );
    } else {
      addBodyText(
        "Select models to download to target workspace:",
        "color:#f5a623;margin-bottom:6px;font-weight:600;"
      );
    }

    // Group toInstall by folder type
    const groupOrder = ["checkpoints", "unet", "diffusion_models", "clip", "text_encoders", "vae", "loras", "controlnet", "style_models", "upscale_models", "other"];
    function folderGroup(folder) { return groupOrder.includes(folder) ? folder : "other"; }
    const groups = {};
    toInstall.forEach((m) => {
      const g = folderGroup(m.save_path || m.folder || "other");
      if (!groups[g]) groups[g] = [];
      groups[g].push(m);
    });
    const sortedGroups = Object.keys(groups).sort((a, b) => groupOrder.indexOf(a) - groupOrder.indexOf(b));

    const checkItems = [];

    // Per-group checkboxes
    const groupCbs = {};
    sortedGroups.forEach((g) => {
      const items = groups[g];
      // Group header row with group select-all
      const headerRow = document.createElement("div");
      headerRow.style.cssText = "display:flex;align-items:center;gap:8px;padding:6px 0 2px;margin-top:4px;border-top:1px solid #2a2a2a;";
      const gCb = document.createElement("input");
      gCb.type = "checkbox";
      gCb.checked = true;
      gCb.style.cssText = "width:14px;height:14px;accent-color:#f5a623;flex-shrink:0;";
      const gLabel = document.createElement("span");
      gLabel.style.cssText = "color:#f5a623;font-weight:600;font-size:11px;text-transform:uppercase;";
      gLabel.textContent = `${g} (${items.length})`;
      headerRow.appendChild(gCb);
      headerRow.appendChild(gLabel);
      body.appendChild(headerRow);
      groupCbs[g] = gCb;

      // Model rows for this group
      items.forEach((m) => {
        const row = document.createElement("div");
        row.style.cssText = "display:flex;align-items:center;gap:8px;padding:2px 0 2px 22px;";
        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.checked = true;
        cb.style.cssText = "width:14px;height:14px;accent-color:#f5a623;flex-shrink:0;";
        const label = document.createElement("span");
        label.style.cssText = "color:#ddd;word-break:break-all;";
        label.textContent = m.filename || "?";
        row.appendChild(cb);
        row.appendChild(label);
        body.appendChild(row);
        checkItems.push({ cb, item: m, group: g });
        // When individual checkbox changes, update group cb state
        cb.addEventListener("change", () => {
          const allInGroup = checkItems.filter((x) => x.group === g);
          gCb.checked = allInGroup.every((x) => x.cb.checked);
          gCb.indeterminate = !gCb.checked && allInGroup.some((x) => x.cb.checked);
        });
      });

      // Group cb toggles all in group
      gCb.addEventListener("change", () => {
        checkItems.filter((x) => x.group === g).forEach((x) => { x.cb.checked = gCb.checked; });
        updateProceedBtn();
      });
    });

    // Global Select All / Deselect All buttons
    if (installCount > 0) {
      const bulkBar = document.createElement("div");
      bulkBar.style.cssText = "display:flex;gap:6px;margin:6px 0 2px;";
      const selectAllBtn = document.createElement("button");
      selectAllBtn.textContent = "Select All";
      selectAllBtn.style.cssText = "background:#2a5a2a;border:1px solid #3a7a3a;color:#7ed321;padding:2px 10px;border-radius:3px;cursor:pointer;font-size:10px;";
      selectAllBtn.onclick = () => { setAllCheckboxes(true); updateProceedBtn(); };
      const deselectAllBtn = document.createElement("button");
      deselectAllBtn.textContent = "Deselect All";
      deselectAllBtn.style.cssText = "background:#3a2a2a;border:1px solid #5a3a3a;color:#e07070;padding:2px 10px;border-radius:3px;cursor:pointer;font-size:10px;";
      deselectAllBtn.onclick = () => { setAllCheckboxes(false); updateProceedBtn(); };
      bulkBar.appendChild(selectAllBtn);
      bulkBar.appendChild(deselectAllBtn);
      body.appendChild(bulkBar);

      function setAllCheckboxes(checked) {
        checkItems.forEach((x) => { x.cb.checked = checked; });
        Object.keys(groupCbs).forEach((g) => {
          const allInGroup = checkItems.filter((x) => x.group === g);
          groupCbs[g].checked = allInGroup.every((x) => x.cb.checked);
          groupCbs[g].indeterminate = false;
        });
      }
    }

    // Already present section
    if (presentCount > 0) {
      addBodyText(
        `Already in target workspace (${presentCount}) — will be skipped:`,
        "color:#7ed321;margin-top:10px;margin-bottom:4px;font-weight:600;"
      );
      const alreadySlice = alreadyPresent.slice(0, 15);
      alreadySlice.forEach((m) => {
        addBodyText(`${m.folder || "?"}/${m.filename || "?"}`, "color:#888;padding-left:12px;font-size:11px;");
      });
      if (alreadyPresent.length > 15) {
        addBodyText(`… and ${alreadyPresent.length - 15} more`, "color:#666;padding-left:12px;font-size:11px;");
      }
    }

    // Remove section
    if (toRemove.length > 0) {
      addBodyText(
        `Marked for removal from target workspace (${toRemove.length}):`,
        "color:#e07070;margin-top:10px;margin-bottom:4px;font-weight:600;"
      );
      const removeSlice = toRemove.slice(0, 10);
      removeSlice.forEach((m) => {
        addBodyText(`${m.folder || "?"}/${m.filename || "?"}`, "color:#c88;padding-left:12px;font-size:11px;");
      });
      if (toRemove.length > 10) {
        addBodyText(`… and ${toRemove.length - 10} more`, "color:#966;padding-left:12px;font-size:11px;");
      }
    }

    addBodyText("After download: sync custom nodes → deploy", "color:#aaa;margin-top:10px;");
    modal.appendChild(body);

    const footer = document.createElement("div");
    footer.style.cssText = "display:flex; gap:8px; justify-content:flex-end; padding:8px 16px 14px; flex-shrink:0;";

    const cancelBtn = document.createElement("button");
    cancelBtn.textContent = "Cancel";
    cancelBtn.style.cssText = btnStyle();
    cancelBtn.onclick = () => { overlay.remove(); setWorkspaceBusy(false); swapProgress.innerHTML = ""; };
    footer.appendChild(cancelBtn);

    function countChecked() { return checkItems.filter((x) => x.cb.checked).length; }

    function updateProceedBtn() {
      const n = countChecked();
      if (installCount === 0) {
        proceedBtn.textContent = "Sync & Deploy";
      } else if (n === 0) {
        proceedBtn.textContent = "Nothing selected — skip all downloads";
      } else {
        proceedBtn.textContent = `Download Selected (${n} model${n !== 1 ? "s" : ""})`;
      }
      proceedBtn.disabled = false;
    }

    const proceedBtn = document.createElement("button");
    proceedBtn.style.cssText = btnStyle("primary");
    updateProceedBtn();

    proceedBtn.onclick = async () => {
      const selectedKeys = checkItems
        .filter((x) => x.cb.checked)
        .map((x) => `${x.item.save_path || x.item.folder || ""}/${x.item.filename || ""}`);
      const requestBody = {
        workspace_id: workspaceSelect.value,
        confirm: true,
        selected_keys: selectedKeys,
        confirm_prompt_interrupt: !!data.confirm_prompt_interrupt,
      };
      proceedBtn.disabled = true;
      proceedBtn.textContent = "Starting…";
      overlay.remove();
      _setSwapProgress("Starting swap…", "#888");
      try {
        const execResp = await api.fetchApi(`${MODAL_PREFIX}/workspaces/swap`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(requestBody),
        });
        let execData = await execResp.json();
        if (execData.status === "confirm_required") {
          const ok = await showConfirm("A prompt is still running. Switch workspaces anyway?");
          if (!ok) {
            setWorkspaceBusy(false);
            _setSwapProgress("Swap cancelled.", "#888");
            return;
          }
          const retryResp = await api.fetchApi(`${MODAL_PREFIX}/workspaces/swap`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ...requestBody, confirm_prompt_interrupt: true }),
          });
          execData = await retryResp.json();
        }
        if (execData.status === "started") {
          currentSwapId = execData.swap_id;
          _setSwapProgress("Starting downloads…", "#f5a623");
          pollSwapJob();
        } else if (execData.status === "repair_required") {
          setWorkspaceBusy(false);
          _setSwapProgress(execData.message || "Swap blocked: manifest repair required.", "#e07070");
          await openManifestRepairModal(execData.issues || []);
        } else {
          setWorkspaceBusy(false);
          _setSwapProgress(execData.message || "Swap failed to start.", "#e05050");
        }
      } catch (e) {
        setWorkspaceBusy(false);
        _setSwapProgress(`Error: ${e.message}`, "#e05050");
      }
    };
    footer.appendChild(proceedBtn);
    modal.appendChild(footer);
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
  }

  async function showManifestInstallDialog() {
    const resp = await api.fetchApi(`${MODAL_PREFIX}/manifest`);
    const data = await resp.json();
    const entries = data.entries || [];
    if (!entries.length) {
      showToast("No manifest entries found. Use Swap Workspace or Add Model to populate the manifest first.", "info");
      return;
    }
    const withUrl = entries.filter((e) => e.url);
    if (!withUrl.length) {
      showToast("No manifest entries have download URLs. Use Manifest Repair to add URLs first.", "info");
      return;
    }

    const workspaceId = workspaceSelect.value;
    if (!workspaceId) {
      showToast("Select a workspace first.", "info");
      return;
    }

    const overlay = document.createElement("div");
    overlay.style.cssText = "position:fixed; inset:0; background:rgba(0,0,0,0.65); display:flex; align-items:center; justify-content:center; z-index:10001;";
    overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.remove(); });

    const modal = document.createElement("div");
    modal.style.cssText = "width:min(660px, 95vw); max-height:75vh; background:#171717; border:1px solid #333; border-radius:8px; display:flex; flex-direction:column; overflow:hidden;";

    const header = document.createElement("div");
    header.style.cssText = "padding:16px 16px 8px; font-weight:600; font-size:13px;";
    header.textContent = "Install from Manifest";
    modal.appendChild(header);

    const body = document.createElement("div");
    body.style.cssText = "flex:1; overflow-y:auto; padding:4px 16px 8px; font-size:12px; line-height:1.6; color:#ccc;";

    const checkItems = [];
    const groupOrder = ["checkpoints", "unet", "diffusion_models", "clip", "text_encoders", "vae", "loras", "controlnet", "style_models", "upscale_models", "other"];
    function folderGroup(folder) { return groupOrder.includes(folder) ? folder : "other"; }
    const groups = {};
    withUrl.forEach((e) => {
      const g = folderGroup(e.folder || "other");
      if (!groups[g]) groups[g] = [];
      groups[g].push(e);
    });
    const sortedGroups = Object.keys(groups).sort((a, b) => groupOrder.indexOf(a) - groupOrder.indexOf(b));

    const groupCbs = {};
    sortedGroups.forEach((g) => {
      const items = groups[g];
      const hdr = document.createElement("div");
      hdr.style.cssText = "display:flex;align-items:center;gap:8px;padding:6px 0 2px;margin-top:4px;border-top:1px solid #2a2a2a;";
      const gCb = document.createElement("input");
      gCb.type = "checkbox";
      gCb.checked = true;
      gCb.style.cssText = "width:14px;height:14px;accent-color:#3a6fcc;flex-shrink:0;";
      const gLabel = document.createElement("span");
      gLabel.style.cssText = "color:#6a9fd8;font-weight:600;font-size:11px;text-transform:uppercase;";
      gLabel.textContent = `${g} (${items.length})`;
      hdr.appendChild(gCb);
      hdr.appendChild(gLabel);
      body.appendChild(hdr);
      groupCbs[g] = gCb;

      items.forEach((e) => {
        const row = document.createElement("div");
        row.style.cssText = "display:flex;align-items:center;gap:8px;padding:2px 0 2px 22px;";
        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.checked = true;
        cb.style.cssText = "width:14px;height:14px;accent-color:#3a6fcc;flex-shrink:0;";
        const label = document.createElement("span");
        label.style.cssText = "color:#ddd;word-break:break-all;";
        label.textContent = `${e.folder || "?"}/${e.filename || "?"}`;
        row.appendChild(cb);
        row.appendChild(label);
        body.appendChild(row);
        checkItems.push({ cb, item: e, group: g });

        cb.addEventListener("change", () => {
          const all = checkItems.filter((x) => x.group === g);
          gCb.checked = all.every((x) => x.cb.checked);
          gCb.indeterminate = !gCb.checked && all.some((x) => x.cb.checked);
        });
      });

      gCb.addEventListener("change", () => {
        checkItems.filter((x) => x.group === g).forEach((x) => { x.cb.checked = gCb.checked; });
        updateInstallBtn();
      });
    });

    // Select/Deselect all
    const bulkBar = document.createElement("div");
    bulkBar.style.cssText = "display:flex;gap:6px;margin:6px 0 2px;";
    const selectAllBtn = document.createElement("button");
    selectAllBtn.textContent = "Select All";
    selectAllBtn.style.cssText = "background:#2a5a2a;border:1px solid #3a7a3a;color:#7ed321;padding:2px 10px;border-radius:3px;cursor:pointer;font-size:10px;";
    selectAllBtn.onclick = () => { checkItems.forEach((x) => { x.cb.checked = true; }); Object.keys(groupCbs).forEach((g) => { groupCbs[g].checked = true; groupCbs[g].indeterminate = false; }); updateInstallBtn(); };
    const deselectAllBtn = document.createElement("button");
    deselectAllBtn.textContent = "Deselect All";
    deselectAllBtn.style.cssText = "background:#3a2a2a;border:1px solid #5a3a3a;color:#e07070;padding:2px 10px;border-radius:3px;cursor:pointer;font-size:10px;";
    deselectAllBtn.onclick = () => { checkItems.forEach((x) => { x.cb.checked = false; }); Object.keys(groupCbs).forEach((g) => { groupCbs[g].checked = false; groupCbs[g].indeterminate = false; }); updateInstallBtn(); };
    bulkBar.appendChild(selectAllBtn);
    bulkBar.appendChild(deselectAllBtn);
    body.appendChild(bulkBar);

    modal.appendChild(body);

    const footer = document.createElement("div");
    footer.style.cssText = "display:flex; gap:8px; justify-content:flex-end; padding:8px 16px 14px; flex-shrink:0;";

    const cancelBtn = document.createElement("button");
    cancelBtn.textContent = "Cancel";
    cancelBtn.style.cssText = btnStyle();
    cancelBtn.onclick = () => overlay.remove();
    footer.appendChild(cancelBtn);

    function updateInstallBtn() {
      const n = checkItems.filter((x) => x.cb.checked).length;
      installProceedBtn.textContent = n > 0 ? `Install Selected (${n} model${n !== 1 ? "s" : ""})` : "Nothing selected";
      installProceedBtn.disabled = n === 0;
    }

    const installProceedBtn = document.createElement("button");
    installProceedBtn.style.cssText = btnStyle("primary");
    updateInstallBtn();

    installProceedBtn.onclick = async () => {
      const selected = checkItems.filter((x) => x.cb.checked).map((x) => ({ folder: x.item.folder, filename: x.item.filename }));
      installProceedBtn.disabled = true;
      installProceedBtn.textContent = "Installing…";
      overlay.remove();
      _setSwapProgress("Installing from manifest…", "#888");
      try {
        const execResp = await api.fetchApi(`${MODAL_PREFIX}/manifest/install`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ items: selected, workspace_id: workspaceId }),
        });
        const execData = await execResp.json();
        if (execData.status === "ok" || execData.status === "partial") {
          const msg = execData.failure_count
            ? `${execData.success_count} installed, ${execData.failure_count} failed`
            : `${execData.success_count} model(s) installed successfully`;
          _setSwapProgress(`Done — ${msg}`, "#7ed321");
          showToast(msg, execData.failure_count ? "info" : "success");
          await loadModels();
        } else {
          _setSwapProgress(execData.message || "Install failed.", "#e05050");
        }
      } catch (e) {
        _setSwapProgress(`Error: ${e.message}`, "#e05050");
      }
    };
    footer.appendChild(installProceedBtn);
    modal.appendChild(footer);
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
  }

  repairBtn.onclick = () => openManifestRepairModal();

  installBtn.onclick = () => showManifestInstallDialog();

  exportBtn.onclick = async () => {
    const prompt = app.graph?.serialize?.() || {};
    const resp = await api.fetchApi(`${MODAL_PREFIX}/workflow-manifest/export`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt, workflow_name: app.graph?.extra?.workflow?.name || "" }),
    });
    const data = await resp.json();
    if (data.status === "repair_required") {
      await openManifestRepairModal(data.unresolved || []);
      return;
    }
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "workflow-manifest.json";
    link.click();
    URL.revokeObjectURL(url);
  };

  importBtn.onclick = async () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".json,application/json";
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) return;
      const payload = JSON.parse(await file.text());
      const resp = await api.fetchApi(`${MODAL_PREFIX}/workflow-manifest/import`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await resp.json();
      if (data.status === "conflict") {
        const resolved = await openImportConflictModal(data.conflicts, payload);
        if (resolved.status !== "ok") throw new Error(resolved.message || "Import conflict resolution failed");
        showToast(`Import complete: ${resolved.added.length} added, ${resolved.filled.length} filled.`, "success");
        return;
      }
      showToast(`Import complete: ${data.added.length} added, ${data.filled.length} filled.`, "success");
    };
    input.click();
  };

  // === SYNC SECTION (Collapsible) ===
  const syncCollapsible = createCollapsibleSection("Sync", { defaultOpen: true, badge: "..." });
  const syncContent = syncCollapsible.content;

  const syncHelp = document.createElement("div");
  syncHelp.style.cssText = "font-size: 11px; color: #888; line-height: 1.5; margin-bottom: 8px;";
  syncHelp.textContent = "Sync your local models and custom nodes to the Modal cloud.";
  syncContent.appendChild(syncHelp);

  // Status display
  const syncStatusEl = document.createElement("div");
  syncStatusEl.style.cssText = "font-size: 12px; color: #aaa; line-height: 1.6; margin-bottom: 10px; padding: 8px; background: #2a2a2a; border-radius: 4px;";
  syncStatusEl.textContent = "Loading sync status...";
  syncContent.appendChild(syncStatusEl);

  // Refresh status button
  const syncRefreshBtn = document.createElement("button");
  syncRefreshBtn.textContent = "\u21BA Refresh Status";
  syncRefreshBtn.style.cssText = btnStyle() + "margin-bottom: 8px; width: 100%;";
  syncRefreshBtn.onclick = () => loadSyncStatus();
  syncContent.appendChild(syncRefreshBtn);

  // Sync Models button
  const syncModelsBtn = document.createElement("button");
  syncModelsBtn.textContent = "\u2B06 Sync Models";
  syncModelsBtn.title = "Upload local models that are not yet on Modal";
  syncModelsBtn.style.cssText = btnStyle("primary") + "margin-bottom: 4px;";
  syncContent.appendChild(syncModelsBtn);

  const syncModelsStatus = document.createElement("div");
  syncModelsStatus.style.cssText = "font-size: 11px; color: #888; min-height: 14px; margin-bottom: 10px;";
  syncContent.appendChild(syncModelsStatus);

  // Sync Custom Nodes button
  const syncCNBtn = document.createElement("button");
  syncCNBtn.textContent = "\u2B06 Sync Custom Nodes";
  syncCNBtn.title = "Package and upload local custom nodes to Modal";
  syncCNBtn.style.cssText = btnStyle("primary") + "margin-bottom: 4px;";
  syncContent.appendChild(syncCNBtn);

  const syncCNStatus = document.createElement("div");
  syncCNStatus.style.cssText = "font-size: 11px; color: #888; min-height: 14px;";
  syncContent.appendChild(syncCNStatus);

  // Resync Remote Runtime button
  const resyncRuntimeBtn = document.createElement("button");
  resyncRuntimeBtn.textContent = "\u21BB Resync Remote Runtime";
  resyncRuntimeBtn.title = "Reload the running Modal ComfyUI so new models or custom nodes become visible";
  resyncRuntimeBtn.style.cssText = btnStyle("primary") + "margin-top: 8px; margin-bottom: 4px;";
  syncContent.appendChild(resyncRuntimeBtn);

  const resyncRuntimeStatus = document.createElement("div");
  resyncRuntimeStatus.style.cssText = "font-size: 11px; color: #888; min-height: 14px;";
  syncContent.appendChild(resyncRuntimeStatus);

  // Check Runtime State button (manual — not called automatically on sidebar open)
  const runtimeStateBtn = document.createElement("button");
  runtimeStateBtn.textContent = "\u2139 Check Runtime State";
  runtimeStateBtn.title = "Check if the remote runtime is stale and needs a resync";
  runtimeStateBtn.style.cssText = btnStyle("primary") + "margin-top: 8px; margin-bottom: 4px;";
  syncContent.appendChild(runtimeStateBtn);

  const runtimeStateStatus = document.createElement("div");
  runtimeStateStatus.style.cssText = "font-size: 11px; color: #888; min-height: 14px;";
  syncContent.appendChild(runtimeStateStatus);

  runtimeStateBtn.onclick = async () => {
    runtimeStateBtn.disabled = true;
    runtimeStateBtn.textContent = "Checking...";
    runtimeStateStatus.textContent = "";
    try {
      const resp = await api.fetchApi(`${MODAL_PREFIX}/runtime/state`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      if (data.stale === true) {
        runtimeStateStatus.style.color = "#f5a623";
        runtimeStateStatus.textContent = "\u26A0 Runtime is stale — use Resync to refresh.";
      } else {
        runtimeStateStatus.style.color = "#7ed321";
        runtimeStateStatus.textContent = "\u2713 Runtime is current.";
      }
    } catch (e) {
      runtimeStateStatus.style.color = "#e05050";
      runtimeStateStatus.textContent = "Error: " + e.message;
    }
    runtimeStateBtn.disabled = false;
    runtimeStateBtn.textContent = "\u2139 Check Runtime State";
  };

  // Button handlers
  syncModelsBtn.onclick = async () => {
    syncModelsBtn.disabled = true;
    syncModelsBtn.textContent = "Syncing Models...";
    syncModelsStatus.style.color = "#f5a623";
    syncModelsStatus.textContent = "Uploading models to Modal volume...";
    try {
      const resp = await api.fetchApi(`${MODAL_PREFIX}/sync/models`, { method: "POST" });
      const data = await resp.json();
      if (data.status === "ok") {
        syncModelsStatus.style.color = "#7ed321";
        syncModelsStatus.textContent = data.uploaded > 0
          ? `Done! ${data.uploaded}/${data.total} model(s) uploaded. Resync runtime if models don't appear.`
          : data.message || "All models already synced.";
        showToast(data.uploaded > 0 ? `${data.uploaded} model(s) synced!` : "Models already synced", "success");
        await loadSyncStatus();
        await loadModels();
      } else {
        throw new Error(data.message || "Sync failed");
      }
    } catch (e) {
      syncModelsStatus.style.color = "#e05050";
      syncModelsStatus.textContent = "Error: " + e.message;
      showToast("Sync failed: " + e.message, "error");
    }
    syncModelsBtn.disabled = false;
    syncModelsBtn.textContent = "\u2B06 Sync Models";
  };

  syncCNBtn.onclick = async () => {
    syncCNBtn.disabled = true;
    syncCNBtn.textContent = "Syncing Custom Nodes...";
    syncCNStatus.style.color = "#f5a623";
    syncCNStatus.textContent = "Packaging and uploading custom nodes...";
    try {
      const resp = await api.fetchApi(`${MODAL_PREFIX}/sync/custom-nodes`, { method: "POST" });
      const data = await resp.json();
      if (data.status === "ok") {
        const count = (data.nodes || []).length;
        syncCNStatus.style.color = "#7ed321";
        syncCNStatus.textContent = data.message
          ? data.message
          : `Done! ${count} custom node(s) synced. Runtime refreshed.`;
        showToast(data.message || `${count} custom node(s) synced!`, data.refresh_error ? "info" : "success");
        await loadSyncStatus();
      } else {
        throw new Error(data.message || "Sync failed");
      }
    } catch (e) {
      syncCNStatus.style.color = "#e05050";
      syncCNStatus.textContent = "Error: " + e.message;
      showToast("Sync failed: " + e.message, "error");
    }
    syncCNBtn.disabled = false;
    syncCNBtn.textContent = "\u2B06 Sync Custom Nodes";
  };

  resyncRuntimeBtn.onclick = async () => {
    resyncRuntimeBtn.disabled = true;
    resyncRuntimeBtn.textContent = "Resyncing...";
    resyncRuntimeStatus.style.color = "#f5a623";
    resyncRuntimeStatus.textContent = "Requesting runtime resync...";
    try {
      const resp = await api.fetchApi(`${MODAL_PREFIX}/runtime/resync`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scope: "all" }),
      });
      const data = await resp.json();
      if (data.status === "ok") {
        resyncRuntimeStatus.style.color = "#7ed321";
        resyncRuntimeStatus.textContent = data.message || "Runtime resynced successfully.";
        showToast("Runtime resynced!", "success");
        await loadSyncStatus();
        await loadModels();
      } else {
        throw new Error(data.message || "Resync failed");
      }
    } catch (e) {
      resyncRuntimeStatus.style.color = "#e05050";
      resyncRuntimeStatus.textContent = "Error: " + e.message;
      showToast("Resync failed: " + e.message, "error");
    }
    resyncRuntimeBtn.disabled = false;
    resyncRuntimeBtn.textContent = "\u21BB Resync Remote Runtime";
  };

  async function loadSyncStatus() {
    if (!syncStatusEl) return;
    syncStatusEl.style.color = "#aaa";
    syncStatusEl.textContent = "Loading...";
    try {
      const resp = await api.fetchApi(`${MODAL_PREFIX}/sync/status`);
      if (resp.status === 503) {
        syncStatusEl.innerHTML = '<span style="color:#888;">Deploy the app first to check sync status.</span>';
        syncCollapsible.refreshHeight();
        return;
      }
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      if (data.status !== "ok") throw new Error(data.message || "Unknown error");

      const ms = data.models || {};
      const cn = data.custom_nodes || {};
      const syncedModels = (ms.synced || []).length;
      const pendingModels = (ms.pending || []).length;
      const totalLocalModels = (ms.local || []).length;
      const syncedCN = (cn.synced || []).length;
      const pendingCN = (cn.pending || []).length;
      const totalLocalCN = (cn.local || []).length;

      syncStatusEl.textContent = "";

      const modelsDiv = document.createElement("div");
      modelsDiv.style.marginBottom = "4px";
      const modelsStrong = document.createElement("strong");
      modelsStrong.textContent = "Models: ";
      modelsDiv.appendChild(modelsStrong);
      modelsDiv.appendChild(document.createTextNode(`${syncedModels} synced / ${totalLocalModels} local `));
      if (pendingModels > 0) {
        const pendingSpan = document.createElement("span");
        pendingSpan.style.color = "#f5a623";
        pendingSpan.textContent = ` (${pendingModels} pending upload)`;
        modelsDiv.appendChild(pendingSpan);
      } else {
        const okSpan = document.createElement("span");
        okSpan.style.color = "#7ed321";
        okSpan.textContent = " \u2713";
        modelsDiv.appendChild(okSpan);
      }
      syncStatusEl.appendChild(modelsDiv);

      const cnDiv = document.createElement("div");
      const cnStrong = document.createElement("strong");
      cnStrong.textContent = "Custom Nodes: ";
      cnDiv.appendChild(cnStrong);
      cnDiv.appendChild(document.createTextNode(`${syncedCN} synced / ${totalLocalCN} local `));
      if (pendingCN > 0) {
        const pendingSpan = document.createElement("span");
        pendingSpan.style.color = "#f5a623";
        pendingSpan.textContent = ` (${pendingCN} pending upload)`;
        cnDiv.appendChild(pendingSpan);
      } else {
        const okSpan = document.createElement("span");
        okSpan.style.color = "#7ed321";
        okSpan.textContent = " \u2713";
        cnDiv.appendChild(okSpan);
      }
      syncStatusEl.appendChild(cnDiv);
      syncCollapsible.updateBadge(pendingModels + pendingCN > 0 ? `${pendingModels + pendingCN}` : "\u2713");
      syncCollapsible.refreshHeight();
    } catch (e) {
      syncStatusEl.style.color = "#e05050";
      syncStatusEl.textContent = "Error: " + e.message;
      syncCollapsible.refreshHeight();
    }
  }

  scrollContent.appendChild(syncCollapsible.wrapper);

  // === MODELS SECTION (Collapsible, default open) ===
  const modelsCollapsible = createCollapsibleSection("Models", { defaultOpen: true, badge: "..." });
  modelsCollapsibleRef = modelsCollapsible;
  const modelsContent = modelsCollapsible.content;

  const modelsHelp = document.createElement("div");
  modelsHelp.style.cssText = "font-size:11px; color:#888; line-height:1.5; margin-bottom:8px;";
  modelsHelp.textContent = "Create local 0-byte placeholders so Modal-only models appear in local ComfyUI dropdowns. Placeholders only work when Modal/cloud mode is enabled.";
  modelsContent.appendChild(modelsHelp);

  modelListEl = document.createElement("div");
  modelListEl.style.cssText = "max-height: 300px; overflow-y: auto; min-height: 0;";
  modelsContent.appendChild(modelListEl);

  const modelsBtnRow = document.createElement("div");
  modelsBtnRow.style.cssText = "display:flex; gap:6px; margin-top:8px; flex-wrap:wrap;";

  const refreshBtn = document.createElement("button");
  refreshBtn.textContent = "\u21BA Refresh";
  refreshBtn.style.cssText = btnStyle() + "flex:1;";
  refreshBtn.onclick = loadModels;

  injectAllBtn = document.createElement("button");
  injectAllBtn.textContent = "Create All Placeholders";
  injectAllBtn.title = "Create local placeholders for every remote model stored in Modal.";
  injectAllBtn.style.cssText = btnStyle() + "flex:1;";
  injectAllBtn.onclick = async () => {
    injectAllBtn.disabled = true;
    injectAllBtn.textContent = "Creating...";
    try {
      const resp = await api.fetchApi(`${MODAL_PREFIX}/models/inject-all`, { method: "POST" });
      const data = await resp.json();
      if (data.status !== "ok") throw new Error(data.message || "Create all placeholders failed");
      showToast(data.message || "Local placeholders created. Refresh ComfyUI if the dropdown does not update.", data.errors?.length ? "info" : "success");
      await loadModels();
    } catch (e) {
      showToast("Error: " + e.message, "error");
    }
    injectAllBtn.disabled = false;
    injectAllBtn.textContent = "Create All Placeholders";
  };

  modelsBtnRow.appendChild(refreshBtn);
  modelsBtnRow.appendChild(injectAllBtn);
  modelsContent.appendChild(modelsBtnRow);

  scrollContent.appendChild(modelsCollapsible.wrapper);

  // === ADD MODEL SECTION ===
  const addSection = document.createElement("div");
  addSection.style.cssText = "display:flex; flex-direction:column; gap:8px; background:#1e1e2e; border-radius:6px; padding:10px;";

  const addTitleRow = document.createElement("div");
  addTitleRow.style.cssText = "display:flex; align-items:center; gap:6px;";

  const addTitle = document.createElement("div");
  addTitle.style.cssText = "font-weight:600; font-size:13px; flex:1;";
  addTitle.textContent = "Add Model";

  const resumeBtn = document.createElement("button");
  resumeBtn.textContent = "\u21BA Get Download Progress";
  resumeBtn.title = "Check for active Modal downloads and resume progress tracking";
  resumeBtn.style.cssText = `
    background:transparent; border:1px solid #3a5a3a; color:#6a9fd8;
    padding:2px 6px; border-radius:3px; cursor:pointer; font-size:9px;
    flex-shrink:0; line-height:1.4;
  `;
  resumeBtn.onclick = checkActiveDownloads;

  addTitleRow.appendChild(addTitle);
  addTitleRow.appendChild(resumeBtn);
  addSection.appendChild(addTitleRow);

  const addHelp = document.createElement("div");
  addHelp.style.cssText = "font-size:11px; color:#888; line-height:1.4;";
  addHelp.textContent = "Download models to the Modal cloud volume. A matching local 0-byte placeholder is created automatically so the model can appear in local ComfyUI dropdowns. Refresh/restart ComfyUI if the dropdown does not update.";
  addSection.appendChild(addHelp);

  const urlInput = document.createElement("input");
  urlInput.type = "text";
  urlInput.placeholder = "Model URL (https://...)";
  urlInput.style.cssText = inputStyle();
  addSection.appendChild(urlInput);

  const row2 = document.createElement("div");
  row2.style.cssText = "display:flex; gap:6px;";

  const folderSelect = document.createElement("select");
  folderSelect.style.cssText = inputStyle() + "flex:1;";
  for (const f of DOWNLOAD_FOLDERS) {
    const opt = document.createElement("option");
    opt.value = f;
    opt.textContent = f;
    folderSelect.appendChild(opt);
  }

  const filenameInput = document.createElement("input");
  filenameInput.type = "text";
  filenameInput.placeholder = "filename.safetensors";
  filenameInput.style.cssText = inputStyle() + "flex:2;";

  row2.appendChild(folderSelect);
  row2.appendChild(filenameInput);
  addSection.appendChild(row2);

  // Download progress bar
  addSection.appendChild(createDownloadProgressBar());

  // Auto-detect filename on URL input (debounced)
  const autoDetectFilename = debounce(() => {
    const url = urlInput.value.trim();
    if (!url || filenameInput.value.trim()) return;
    try {
      const parts = new URL(url).pathname.split("/");
      const name = parts.filter(Boolean).pop() || "";
      if (name.includes(".")) filenameInput.value = decodeURIComponent(name);
    } catch {}
  }, 600);

  urlInput.addEventListener("input", autoDetectFilename);
  urlInput.addEventListener("blur", () => {
    const url = urlInput.value.trim();
    if (!url || filenameInput.value.trim()) return;
    try {
      const parts = new URL(url).pathname.split("/");
      const name = parts.filter(Boolean).pop() || "";
      if (name.includes(".")) filenameInput.value = decodeURIComponent(name);
    } catch {}
  });

  // Buttons row: Download (single) + Add to Batch
  const btnRow = document.createElement("div");
  btnRow.style.cssText = "display:flex; gap:6px;";

  const singleDownloadBtn = document.createElement("button");
  singleDownloadBtn.textContent = "Download";
  singleDownloadBtn.title = "Download this single model immediately";
  singleDownloadBtn.style.cssText = btnStyle("primary") + "flex:1;";
  singleDownloadBtn.onclick = async () => {
    let url = urlInput.value.trim();
    if (!url) return;
    if (!/^https?:\/\//i.test(url)) url = "https://" + url;
    if (!filenameInput.value.trim()) {
      try {
        const parts = new URL(url).pathname.split("/");
        const name = parts.filter(Boolean).pop() || "";
        if (name.includes(".")) filenameInput.value = decodeURIComponent(name);
      } catch {}
    }
    const filename = filenameInput.value.trim();
    const folder = folderSelect.value;
    if (!filename) return;

    singleDownloadBtn.disabled = true;
    singleDownloadBtn.textContent = "Starting...";
    try {
      const resp = await api.fetchApi(`${MODAL_PREFIX}/model/install`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, filename, save_path: folder }),
      });
      const data = await resp.json();
      if (data.status === "ok") {
        showDownloadProgress({ state: "starting", filename });
        startDownloadPoll(data.download_id, filename, folder);
        urlInput.value = "";
        filenameInput.value = "";
      } else {
        throw new Error(data.message || "Download failed");
      }
    } catch (e) {
      showToast("Error: " + e.message, "error");
      hideDownloadProgress();
    }
    singleDownloadBtn.disabled = false;
    singleDownloadBtn.textContent = "Download";
  };

  const addToQueueBtn = document.createElement("button");
  addToQueueBtn.textContent = "+ Add to Batch";
  addToQueueBtn.title = "Add to batch download queue";
  addToQueueBtn.style.cssText = btnStyle() + "flex:1;";
  addToQueueBtn.onclick = () => {
    let url = urlInput.value.trim();
    if (!url) return;
    if (!/^https?:\/\//i.test(url)) url = "https://" + url;
    if (!filenameInput.value.trim()) {
      try {
        const parts = new URL(url).pathname.split("/");
        const name = parts.filter(Boolean).pop() || "";
        if (name.includes(".")) filenameInput.value = decodeURIComponent(name);
      } catch {}
    }
    const filename = filenameInput.value.trim();
    const folder = folderSelect.value;
    if (!url || !filename) return;
    const entry = { id: Date.now() + Math.random(), url, filename, folder, state: "queued" };
    downloadQueue.push(entry);
    const row = renderQueueItem(entry);
    queueListEl.appendChild(row);
    urlInput.value = "";
    filenameInput.value = "";
    syncDownloadAllBtn();
    showToast("Added to batch", "info");
  };

  const enterSubmit = (e) => { if (e.key === "Enter") singleDownloadBtn.click(); };
  urlInput.addEventListener("keydown", enterSubmit);
  filenameInput.addEventListener("keydown", enterSubmit);

  btnRow.appendChild(singleDownloadBtn);
  btnRow.appendChild(addToQueueBtn);
  addSection.appendChild(btnRow);

  // Queue area
  const queueHeader = document.createElement("div");
  queueHeader.style.cssText = "font-size:11px; font-weight:600; color:#aaa; text-transform:uppercase; letter-spacing:0.05em; margin-top:4px;";
  queueHeader.textContent = "Batch Queue";
  addSection.appendChild(queueHeader);

  queueListEl = document.createElement("div");
  queueListEl.style.cssText = "max-height:100px; overflow-y:auto;";
  addSection.appendChild(queueListEl);

  batchStatusEl = document.createElement("div");
  batchStatusEl.style.cssText = "font-size:11px; color:#888; min-height:14px;";
  addSection.appendChild(batchStatusEl);

  downloadAllBtn = document.createElement("button");
  downloadAllBtn.textContent = "\u2B07 Download Batch";
  downloadAllBtn.disabled = true;
  downloadAllBtn.style.cssText = btnStyle("primary");
  downloadAllBtn.onclick = async () => {
    const pending = downloadQueue.filter(e => e.state === "queued");
    if (pending.length === 0) return;

    downloadAllBtn.disabled = true;
    batchStatusEl.style.color = "#f5a623";
    batchStatusEl.textContent = `Sending ${pending.length} download(s) to Modal...`;

    pending.forEach(e => {
      e.state = "running";
      if (e.statusEl) {
        e.statusEl.textContent = "\u23F3 downloading...";
        e.statusEl.style.color = "#f5a623";
      }
      if (e.removeBtn) e.removeBtn.disabled = true;
    });

    const items = pending.map(e => ({ url: e.url, filename: e.filename, save_path: e.folder }));

    try {
      const resp = await api.fetchApi(`${MODAL_PREFIX}/models/batch-install`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items }),
      });
      const data = await resp.json();

      if (data.status === "ok") {
        data.results.forEach((res, i) => {
          const entry = pending[i];
          if (!entry) return;
          entry.state = "done";
          if (entry.statusEl) {
            entry.statusEl.textContent = res.skipped ? "\u2713 already exists" : "\u2713 done";
            entry.statusEl.style.color = "#7ed321";
          }
        });
        batchStatusEl.style.color = "#7ed321";
        batchStatusEl.textContent = data.message || `Done - ${pending.length} model(s) downloaded.`;
        showToast(data.message || `${pending.length} model(s) downloaded!`, data.placeholder_errors?.length ? "info" : "success");
        await loadModels();
      } else {
        throw new Error(data.message || "Unknown error");
      }
    } catch (e) {
      pending.forEach(entry => {
        if (entry.state !== "done") {
          entry.state = "queued";
          if (entry.statusEl) {
            entry.statusEl.textContent = "\u2717 failed - re-queued";
            entry.statusEl.style.color = "#e05";
          }
          if (entry.removeBtn) entry.removeBtn.disabled = false;
        }
      });
      batchStatusEl.style.color = "#e05";
      batchStatusEl.textContent = `Error: ${e.message}`;
    }

    syncDownloadAllBtn();
  };
  addSection.appendChild(downloadAllBtn);

  scrollContent.appendChild(addSection);

  // === SETTINGS SECTION (Collapsible, at bottom) ===
  const settingsCollapsible = createCollapsibleSection("Settings", { defaultOpen: false, badge: null });
  settingsCollapsible.wrapper.querySelector("span:last-of-type").style.display = "none"; // hide badge for settings

  const settingsContent = settingsCollapsible.content;

  // -- HuggingFace Token --
  const hfTitle = document.createElement("div");
  hfTitle.style.cssText = "font-weight:600; font-size:12px; margin-bottom:4px;";
  hfTitle.textContent = "\uD83E\uDD17 HuggingFace Token";
  settingsContent.appendChild(hfTitle);

  const hfDesc = document.createElement("div");
  hfDesc.style.cssText = "font-size:11px; color:#888; line-height:1.5; margin-bottom:6px;";
  hfDesc.innerHTML = `Required only for gated/private models on HuggingFace (e.g., Flux, SDXL Turbo). Get your token at <a href="https://huggingface.co/settings/tokens" target="_blank" rel="noopener noreferrer" style="color:#6a9fd8;">huggingface.co/settings/tokens</a>`;
  settingsContent.appendChild(hfDesc);

  const hfRow = document.createElement("div");
  hfRow.style.cssText = "display:flex; gap:6px;";

  const hfInput = document.createElement("input");
  hfInput.type = "password";
  hfInput.placeholder = "hf_...";
  hfInput.style.cssText = inputStyle() + "flex:1;";

  const hfSaveBtn = document.createElement("button");
  hfSaveBtn.textContent = "Save";
  hfSaveBtn.style.cssText = btnStyle();

  hfRow.appendChild(hfInput);
  hfRow.appendChild(hfSaveBtn);
  settingsContent.appendChild(hfRow);

  const hfStatus = document.createElement("div");
  hfStatus.style.cssText = "font-size:11px; color:#888; min-height:14px; margin-top:4px;";
  settingsContent.appendChild(hfStatus);

  (async () => {
    try {
      const r = await api.fetchApi(`${MODAL_PREFIX}/hf-token`);
      const d = await r.json();
      if (d.token) {
        hfStatus.innerHTML = "";
        const badge = document.createElement("span");
        badge.style.cssText = "color:#7ed321; background:#1a3a1a; padding:2px 6px; border-radius:3px; font-size:10px;";
        badge.textContent = "Saved";
        const tokenSpan = document.createElement("span");
        tokenSpan.style.cssText = "color:#666; margin-left:6px;";
        tokenSpan.textContent = d.token;
        hfStatus.appendChild(badge);
        hfStatus.appendChild(tokenSpan);
      }
    } catch {}
  })();

  hfSaveBtn.onclick = async () => {
    const token = hfInput.value.trim();
    hfStatus.textContent = "";
    hfSaveBtn.disabled = true;
    try {
      const r = await api.fetchApi(`${MODAL_PREFIX}/hf-token`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token }),
      });
      const d = await r.json();
      if (d.status === "ok") {
        hfStatus.innerHTML = token
          ? `<span style="color:#7ed321; background:#1a3a1a; padding:2px 6px; border-radius:3px; font-size:10px;">Saved</span>`
          : `<span style="color:#888;">Cleared</span>`;
        hfInput.value = "";
        showToast(token ? "Token saved" : "Token cleared", "success");
      } else {
        hfStatus.style.color = "#e05";
        hfStatus.textContent = d.message || "Error saving token.";
      }
    } catch (e) {
      hfStatus.style.color = "#e05";
      hfStatus.textContent = `Error: ${e.message}`;
    }
    hfSaveBtn.disabled = false;
  };
  hfInput.addEventListener("keydown", (e) => { if (e.key === "Enter") hfSaveBtn.click(); });

  // -- Civitai API Key --
  const civitaiDivider = document.createElement("div");
  civitaiDivider.style.cssText = "border-top: 1px solid #3a3a3a; margin: 10px 0;";
  settingsContent.appendChild(civitaiDivider);

  const civitaiTitle = document.createElement("div");
  civitaiTitle.style.cssText = "font-weight:600; font-size:12px; margin-bottom:4px;";
  civitaiTitle.textContent = "\uD83C\uDFF0 Civitai API Key";
  settingsContent.appendChild(civitaiTitle);

  const civitaiDesc = document.createElement("div");
  civitaiDesc.style.cssText = "font-size:11px; color:#888; line-height:1.5; margin-bottom:6px;";
  civitaiDesc.innerHTML = `Required for gated/private/purchased models on Civitai. Get your key at <a href="https://civitai.com/user/account" target="_blank" rel="noopener noreferrer" style="color:#6a9fd8;">civitai.com/user/account</a>`;
  settingsContent.appendChild(civitaiDesc);

  const civitaiRow = document.createElement("div");
  civitaiRow.style.cssText = "display:flex; gap:6px;";

  const civitaiInput = document.createElement("input");
  civitaiInput.type = "password";
  civitaiInput.placeholder = "Civitai API Key";
  civitaiInput.style.cssText = inputStyle() + "flex:1;";

  const civitaiSaveBtn = document.createElement("button");
  civitaiSaveBtn.textContent = "Save";
  civitaiSaveBtn.style.cssText = btnStyle();

  civitaiRow.appendChild(civitaiInput);
  civitaiRow.appendChild(civitaiSaveBtn);
  settingsContent.appendChild(civitaiRow);

  const civitaiStatus = document.createElement("div");
  civitaiStatus.style.cssText = "font-size:11px; color:#888; min-height:14px; margin-top:4px;";
  settingsContent.appendChild(civitaiStatus);

  (async () => {
    try {
      const r = await api.fetchApi(`${MODAL_PREFIX}/civitai-token`);
      const d = await r.json();
      if (d.token) {
        civitaiStatus.innerHTML = "";
        const badge = document.createElement("span");
        badge.style.cssText = "color:#7ed321; background:#1a3a1a; padding:2px 6px; border-radius:3px; font-size:10px;";
        badge.textContent = "Saved";
        const tokenSpan = document.createElement("span");
        tokenSpan.style.cssText = "color:#666; margin-left:6px;";
        tokenSpan.textContent = d.token;
        civitaiStatus.appendChild(badge);
        civitaiStatus.appendChild(tokenSpan);
      }
    } catch {}
  })();

  civitaiSaveBtn.onclick = async () => {
    const token = civitaiInput.value.trim();
    civitaiStatus.textContent = "";
    civitaiSaveBtn.disabled = true;
    try {
      const r = await api.fetchApi(`${MODAL_PREFIX}/civitai-token`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token }),
      });
      const d = await r.json();
      if (d.status === "ok") {
        civitaiStatus.innerHTML = token
          ? `<span style="color:#7ed321; background:#1a3a1a; padding:2px 6px; border-radius:3px; font-size:10px;">Saved</span>`
          : `<span style="color:#888;">Cleared</span>`;
        civitaiInput.value = "";
        showToast(token ? "Civitai key saved" : "Civitai key cleared", "success");
      } else {
        civitaiStatus.style.color = "#e05";
        civitaiStatus.textContent = d.message || "Error saving key.";
      }
    } catch (e) {
      civitaiStatus.style.color = "#e05";
      civitaiStatus.textContent = `Error: ${e.message}`;
    }
    civitaiSaveBtn.disabled = false;
  };
  civitaiInput.addEventListener("keydown", (e) => { if (e.key === "Enter") civitaiSaveBtn.click(); });

  // -- Change API Key --
  const keyDivider = document.createElement("div");
  keyDivider.style.cssText = "border-top: 1px solid #3a3a3a; margin: 10px 0;";
  settingsContent.appendChild(keyDivider);

  const reimportKeyBtn = document.createElement("button");
  reimportKeyBtn.textContent = "\uD83D\uDD11 Change API Key";
  reimportKeyBtn.title = "Re-enter Modal API key";
  reimportKeyBtn.style.cssText = btnStyle() + "width: 100%;";
  reimportKeyBtn.onclick = () => {
    const container = panel.parentElement;
    if (!container) return;
    container.innerHTML = "";
    container.appendChild(buildAuthPanel(() => {
      container.innerHTML = "";
      container.appendChild(buildPanel());
      startDeployPoll();
    }));
  };
  settingsContent.appendChild(reimportKeyBtn);

  scrollContent.appendChild(settingsCollapsible.wrapper);

  // === LOCAL MODE NOTICE ===
  const localNotice = document.createElement("div");
  localNotice.style.cssText = "font-size:12px; color:#888; line-height:1.5; padding:12px; background:#1e1e2e; border-radius:6px; display:none; text-align:center;";
  localNotice.textContent = "Local mode: prompts go directly to ComfyUI. GPU routing is off.";
  scrollContent.appendChild(localNotice);

  panel.appendChild(scrollContent);

  // === Gear button opens settings section ===
  gearBtn.onclick = () => {
    settingsCollapsible.open();
    settingsCollapsible.wrapper.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  // === Modal sections toggle ===
  const modalSectionElements = [gpuSection, workspaceSection.wrapper, syncCollapsible.wrapper, modelsCollapsible.wrapper, addSection];

  function updateModalSections(enabled) {
    for (const el of modalSectionElements) {
      el.style.display = enabled ? "" : "none";
    }
    localNotice.style.display = enabled ? "none" : "block";
    gpuSelect.disabled = !enabled;
    checkBtn.disabled = !enabled;
    redeployBtn.disabled = !enabled;
    if (typeof redeployRestartBtn !== "undefined") redeployRestartBtn.disabled = !enabled;
  }

  updateModalSections(isCloudMode);
  window._comfyModalEnabled = isCloudMode;

  // Sync GPU config on load and populate dropdown
  (async () => {
    const { config, selectedGpu, options } = await syncGpuConfig();
    setGpuOptions(gpuSelect, options.length ? options : [{ value: selectedGpu, label: selectedGpu.toUpperCase() }]);
    gpuSelect.value = selectedGpu;
  })();

  startDeployPoll();
  loadModels();
  loadSyncStatus();
  loadWorkspaces();
  checkActiveDownloads();

  return panel;
}

// --- Download Progress Bar ---
function createDownloadProgressBar() {
  const wrap = document.createElement("div");
  wrap.id = "cm-download-progress";
  wrap.style.cssText = "display:none; flex-direction:column; gap:4px; padding:6px 8px; background:#1a2a1a; border:1px solid #2a4a2a; border-radius:4px;";

  const headerRow = document.createElement("div");
  headerRow.style.cssText = "display:flex; align-items:center; gap:6px;";

  const label = document.createElement("span");
  label.style.cssText = "font-size:10px; font-weight:600; color:#7ed321; text-transform:uppercase; letter-spacing:0.05em; flex:1;";
  label.textContent = "Downloading...";

  const cancelBtn = document.createElement("button");
  cancelBtn.textContent = "\u2715";
  cancelBtn.title = "Dismiss";
  cancelBtn.style.cssText = `
    background:transparent; border:1px solid #555; color:#888;
    width:16px; height:16px; border-radius:3px; cursor:pointer;
    font-size:9px; padding:0; display:flex; align-items:center; justify-content:center; line-height:1;
    flex-shrink:0;
  `;
  cancelBtn.onclick = () => hideDownloadProgress();

  headerRow.appendChild(label);
  headerRow.appendChild(cancelBtn);

  const track = document.createElement("div");
  track.style.cssText = "width:100%; height:8px; background:#222; border-radius:4px; overflow:hidden;";

  const fill = document.createElement("div");
  fill.style.cssText = "width:0%; height:100%; background:#4caf50; border-radius:4px; transition:width 0.3s ease;";

  track.appendChild(fill);

  const info = document.createElement("div");
  info.style.cssText = "font-size:10px; color:#aaa; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;";

  wrap.appendChild(headerRow);
  wrap.appendChild(track);
  wrap.appendChild(info);

  _downloadProgressEl = wrap;
  _downloadProgressTrackEl = fill;
  _downloadProgressPctEl = label;
  _downloadProgressInfoEl = info;

  return wrap;
}

function showDownloadProgress(state) {
  if (!_downloadProgressEl) return;
  _downloadProgressEl.style.display = "flex";

  if (state.state === "downloading") {
    const pct = state.pct || 0;
    _downloadProgressTrackEl.style.width = pct + "%";
    _downloadProgressPctEl.textContent = `Downloading  ${pct}%`;
    _downloadProgressInfoEl.textContent = `${state.filename || ""}  (${fmtSize((state.downloaded_mb || 0) * 1048576)} / ${fmtSize((state.total_mb || 0) * 1048576)})`;
    _downloadProgressEl.style.borderColor = "#2a4a2a";
    _downloadProgressEl.style.background = "#1a2a1a";
  } else if (state.state === "starting") {
    _downloadProgressTrackEl.style.width = "100%";
    _downloadProgressTrackEl.style.background = "#555";
    _downloadProgressTrackEl.style.animation = "cm-dl-pulse 1.5s ease-in-out infinite";
    _downloadProgressPctEl.textContent = "Starting download...";
    _downloadProgressInfoEl.textContent = state.filename || "";
    _downloadProgressEl.style.borderColor = "#3a3a2a";
    _downloadProgressEl.style.background = "#1a1a2a";
  } else if (state.state === "complete") {
    _downloadProgressTrackEl.style.width = "100%";
    _downloadProgressTrackEl.style.background = "#4caf50";
    _downloadProgressTrackEl.style.animation = "";
    _downloadProgressPctEl.textContent = "\u2713 Complete";
    _downloadProgressInfoEl.textContent = state.filename || "";
    _downloadProgressEl.style.borderColor = "#2a4a2a";
    _downloadProgressEl.style.background = "#1a3a1a";
    setTimeout(hideDownloadProgress, 4000);
  } else if (state.state === "error") {
    _downloadProgressTrackEl.style.width = "100%";
    _downloadProgressTrackEl.style.background = "#e05050";
    _downloadProgressTrackEl.style.animation = "";
    _downloadProgressPctEl.textContent = "\u2717 Failed";
    _downloadProgressInfoEl.textContent = state.error || "Download failed";
    _downloadProgressPctEl.style.color = "#e05050";
    _downloadProgressEl.style.borderColor = "#4a2a2a";
    _downloadProgressEl.style.background = "#2a1a1a";
    setTimeout(hideDownloadProgress, 8000);
  }
}

function hideDownloadProgress() {
  if (_downloadProgressEl) _downloadProgressEl.style.display = "none";
  if (_downloadProgressTrackEl) {
    _downloadProgressTrackEl.style.width = "0%";
    _downloadProgressTrackEl.style.background = "#4caf50";
    _downloadProgressTrackEl.style.animation = "";
  }
  if (_downloadProgressPctEl) {
    _downloadProgressPctEl.textContent = "Downloading...";
    _downloadProgressPctEl.style.color = "#7ed321";
  }
  _activeDownloadId = null;
}

function stopDownloadPoll() {
  if (_downloadPollTimer) {
    clearInterval(_downloadPollTimer);
    _downloadPollTimer = null;
  }
}

function startDownloadPoll(downloadId, filename, savePath) {
  stopDownloadPoll();
  _activeDownloadId = downloadId;
  _downloadPollTimer = setInterval(async () => {
    try {
      const resp = await api.fetchApi(`${MODAL_PREFIX}/download/status/${downloadId}`);
      if (!resp.ok) {
        if (resp.status === 404) {
          stopDownloadPoll();
          hideDownloadProgress();
        }
        return;
      }
      const data = await resp.json();
      if (data.state === "downloading" || data.state === "starting") {
        showDownloadProgress(data);
      } else if (data.state === "complete") {
        stopDownloadPoll();
        showDownloadProgress(data);
        showToast("Model downloaded successfully!", "success");
        loadModels();
      } else if (data.state === "error") {
        stopDownloadPoll();
        showDownloadProgress(data);
        showToast("Download failed: " + (data.error || "Unknown error"), "error");
      }
    } catch (e) {
      // Silently retry on next poll
    }
  }, 2000);
}

async function checkActiveDownloads() {
  try {
    const resp = await api.fetchApi(`${MODAL_PREFIX}/download/active`);
    if (!resp.ok) return;
    const data = await resp.json();
    if (data.status !== "ok") return;
    const active = data.active || {};
    const ids = Object.keys(active);
    if (ids.length > 0) {
      const firstId = ids[0];
      const first = active[firstId];
      showDownloadProgress(first);
      startDownloadPoll(firstId, first.filename, first.save_path);
      showToast("Resumed tracking download progress", "info");
    }
  } catch {
    // silent
  }
}

// --- Style helpers ---
function segmentBtnStyle(active) {
  if (active) {
    return `
      flex: 1; padding: 7px 0; border: none; cursor: pointer; font-size: 12px; font-weight: 600;
      background: #3a6fcc; color: #fff; transition: background 0.2s;
    `;
  }
  return `
    flex: 1; padding: 7px 0; border: none; cursor: pointer; font-size: 12px;
    background: #2a2a2a; color: #888; transition: background 0.2s;
  `;
}

function btnStyle(variant) {
  if (variant === "primary") {
    return `
      background: #3a6fcc; border: 1px solid #4a7fe0; color: #fff;
      padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 12px;
      width: 100%; font-weight: 600;
    `;
  }
  return `
    background: #3a3a3a; border: 1px solid #555; color: #ddd;
    padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 12px;
  `;
}

function inputStyle() {
  return `
    background: #222; border: 1px solid #444; color: #ddd;
    padding: 5px 8px; border-radius: 4px; font-size: 12px;
    width: 100%; box-sizing: border-box; outline: none;
  `;
}

// --- Reusable mount/open helpers for Testing Suite integration ---

/**
 * Mount the full legacy settings panel into the given container element.
 * This is used by the testing-suite's Settings tab to embed real settings UI.
 * @param {HTMLElement} containerEl
 * @returns {HTMLElement} the mounted panel element
 */
window.mountSettingsPanel = function mountSettingsPanel(containerEl) {
  if (!containerEl) throw new Error("mountSettingsPanel: containerEl required");
  containerEl.innerHTML = "";
  const panel = buildPanel();
  containerEl.appendChild(panel);
  return panel;
};

/**
 * Open the legacy settings panel as a full-page overlay (standalone use).
 * This preserves the legacy behavior while being callable from the testing suite.
 */
window.open_comfymodal_settings = function open_comfymodal_settings() {
  const existing = document.getElementById("comfymodal-settings-overlay");
  if (existing) {
    existing.style.display = "flex";
    return;
  }
  const overlay = document.createElement("div");
  overlay.id = "comfymodal-settings-overlay";
  overlay.style.cssText = `
    position: fixed; top: 0; left: 0; width: 100%; height: 100%;
    background: rgba(0,0,0,0.7); z-index: 99998;
    display: flex; align-items: center; justify-content: center;
  `;
  const modal = document.createElement("div");
  modal.style.cssText = `
    background: #1e1e2e; border: 1px solid #444; border-radius: 8px;
    width: 90%; max-width: 600px; max-height: 85vh;
    display: flex; flex-direction: column; overflow: hidden;
  `;
  const header = document.createElement("div");
  header.style.cssText = `
    display: flex; align-items: center; padding: 12px 16px;
    border-bottom: 1px solid #333; flex-shrink: 0;
  `;
  const title = document.createElement("span");
  title.style.cssText = "font-weight: 600; font-size: 14px; color: #ddd; flex: 1;";
  title.textContent = "Settings";
  const closeBtn = document.createElement("button");
  closeBtn.textContent = "\u2715";
  closeBtn.style.cssText = `
    background: transparent; border: 1px solid #555; color: #aaa;
    width: 28px; height: 28px; border-radius: 4px; cursor: pointer;
    font-size: 14px; display: flex; align-items: center; justify-content: center;
  `;
  header.appendChild(title);
  header.appendChild(closeBtn);
  const body = document.createElement("div");
  body.style.cssText = "flex: 1; overflow-y: auto; min-height: 0;";
  modal.appendChild(header);
  modal.appendChild(body);
  overlay.appendChild(modal);
  document.body.appendChild(overlay);

  // Mount the panel
  mountSettingsPanel(body);

  function closeOverlay() {
    overlay.style.display = "none";
    document.removeEventListener("keydown", escHandler);
  }
  const escHandler = (e) => { if (e.key === "Escape") closeOverlay(); };
  document.addEventListener("keydown", escHandler);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) closeOverlay(); });
  closeBtn.onclick = closeOverlay;
};

// --- Extension Registration ---
app.registerExtension({
  name: "comfyui.modal.settings",

  async setup() {
    // Idempotent setup: clean up any lingering timers from previous mounts
    stopDeployLogPoll();
    if (_deployPollTimer) {
      clearTimeout(_deployPollTimer);
      _deployPollTimer = null;
    }
    if (_deploySuccessTimer) {
      clearTimeout(_deploySuccessTimer);
      _deploySuccessTimer = null;
    }

    // Post-redeploy+restart success banner
    try {
      if (sessionStorage.getItem("_comfymodal_redeploy_restart_done") === "1") {
        sessionStorage.removeItem("_comfymodal_redeploy_restart_done");
        setTimeout(() => {
          showToast("\u2705 Redeploy + Restart complete — ComfyUI is fresh.", "success");
        }, 800);
      }
    } catch {}

    // Apply saved GPU config on page load (before sidebar is opened)
    syncGpuConfig();
    syncOutputOptions();

    // Legacy sidebar tab is hidden by default. Only register when explicitly
    // opted in via __comfyModalEnableLegacySidebarTabs (set by an admin/user script).
    // modal-testing.js provides the single primary entry under unified UI.
    if (window.__comfyModalEnableLegacySidebarTabs === true && app?.extensionManager?.registerSidebarTab) {
      app.extensionManager.registerSidebarTab({
        id: "modal-gpu",
        icon: "pi pi-cloud",
        title: "Modal GPU",
        tooltip: "Modal GPU model manager",
        type: "custom",
        render: async (el) => {
          el.style.height = "100%";

          async function mount() {
            el.innerHTML = "";
            try {
              const resp = await api.fetchApi(`${MODAL_PREFIX}/auth/status`);
              const { connected } = await resp.json();
              if (connected) {
                el.appendChild(buildPanel());
              } else {
                el.appendChild(buildAuthPanel(() => {
                  el.innerHTML = "";
                  el.appendChild(buildPanel());
                  startDeployPoll();
                }));
              }
            } catch {
              el.appendChild(buildPanel());
            }
          }

          await mount();
        },
      });
    }
  },
});
