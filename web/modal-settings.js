import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
// Shared server-first output-preference authority (same module the modern
// Studio Settings surface uses): one normalization, one default set, one
// persist/revert path for both visible settings surfaces.
import { syncOutputConfigFromServer } from "./studio-output-preferences.js";

const MODAL_PREFIX = "/comfymodal";

const STORAGE_KEY_GPU    = "comfymodal_gpu";
const STORAGE_KEY_ENABLED = "comfymodal_enabled";

function pickInitialGpu(config, storedGpu) {
  const values = new Set((config.available_gpus || []).map((opt) => opt.value));
  if (storedGpu && values.has(storedGpu)) return storedGpu;
  return config.gpu || config.default_gpu || "rtx-pro-6000";
}

// Read-only GPU initialization. Loading the page must never mutate server
// state — only an explicit user selection POSTs a GPU (modern Settings owns
// that writer since F8).
async function loadGpuConfig() {
  let config = { gpu: "rtx-pro-6000", default_gpu: "rtx-pro-6000", available_gpus: [] };
  let loaded = false;
  try {
    const response = await api.fetchApi(`${MODAL_PREFIX}/config`);
    if (response.ok) {
      config = await response.json();
      loaded = true;
    }
  } catch {}

  const options = Array.isArray(config.available_gpus) ? config.available_gpus : [];
  let selectedGpu;
  if (loaded) {
    // Server wins over stale localStorage on a successful read.
    selectedGpu = pickInitialGpu(config, "");
    try { localStorage.setItem(STORAGE_KEY_GPU, selectedGpu); } catch {}
  } else {
    // Server unavailable — fall back truthfully to the stored choice
    // (never erase user values; only default when nothing is stored).
    const storedGpu = localStorage.getItem(STORAGE_KEY_GPU) || "";
    selectedGpu = storedGpu || pickInitialGpu(config, "");
  }

  return { config, selectedGpu, options };
}

// Build/render lifecycle guard: one read-only settings sync per page load
// instead of issuing duplicate requests on every mount.
let _legacyGpuSyncPromise = null;
function syncLegacyGpuConfigOnce() {
  if (!_legacyGpuSyncPromise) {
    _legacyGpuSyncPromise = loadGpuConfig();
  }
  return _legacyGpuSyncPromise;
}

let _legacyOutputSyncPromise = null;
function syncLegacyOutputPrefsOnce() {
  if (!_legacyOutputSyncPromise) {
    _legacyOutputSyncPromise = syncOutputConfigFromServer();
  }
  return _legacyOutputSyncPromise;
}

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

// H18 Wave G: the retired legacy overlay body (buildPanel + deploy/models/
// sync/auth/download sections and their style helpers) is deleted. This
// module is now only the canvas/shared compatibility surface:
//   - window._comfyModalEnabled startup semantics (canvas pass-through gate)
//   - output-preference shared wiring (studio-output-preferences.js)
//   - read-only GPU/settings synchronization
//   - post-redeploy+restart success banner (written by modern Backend
//     deployment flows on page reload)

// --- Extension Registration ---
app.registerExtension({
  name: "comfyui.modal.settings",

  async setup() {
    // Post-redeploy+restart success banner
    try {
      if (sessionStorage.getItem("_comfymodal_redeploy_restart_done") === "1") {
        sessionStorage.removeItem("_comfymodal_redeploy_restart_done");
        setTimeout(() => {
          showToast("\u2705 Redeploy + Restart complete — ComfyUI is fresh.", "success");
        }, 800);
      }
    } catch {}

    // Read-only settings sync on page load (before any panel is opened).
    // No GPU POST: loading the page or opening a panel must not mutate server
    // state — explicit user selections are the only GPU writers.
    syncLegacyGpuConfigOnce();
    syncLegacyOutputPrefsOnce();

    // H14 Wave E canvas-compatibility shim (H5C §15-B): the legacy panel used
    // to initialize window._comfyModalEnabled from the persisted
    // comfymodal_enabled key when it was built. With the overlay retired,
    // startup performs that same bounded initialization so canvas
    // pass-through semantics (modal-node.js reads `!== false`; undefined
    // defaults enabled) stay byte-for-byte semantically equivalent. Same
    // precedence as before: absent key → enabled (cloud); "false" → local.
    try {
      const savedEnabled = localStorage.getItem(STORAGE_KEY_ENABLED);
      window._comfyModalEnabled = savedEnabled === null ? true : savedEnabled === "true";
    } catch {}
  },
});
