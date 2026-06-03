import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const MODAL_PREFIX = "/comfymodal";
const BENCHMARK_WORKFLOW_PATH = "/comfymodal/benchmark/workflow";
const BENCHMARK_WORKFLOW_ROUTE = BENCHMARK_WORKFLOW_PATH;

let _originalFetchApi = null;

function log(...args) {
  console.log("[comfyui-modal]", ...args);
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
    log("Extension loaded. Patching fetchApi...");

    if (typeof api.addEventListener === "function") {
      api.addEventListener("execution_success", (event) => {
        const detail = event?.detail || {};
        const trace = detail.trace;
        if (!trace) return;
        const t10ClientMs = Date.now();
        const suffix = ` client_event_recv_ms=${t10ClientMs}`;
        _logTrace(trace, suffix);
      });
    }

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
          options = {
            ...options,
            body: JSON.stringify(parsed),
          };
          void _saveBenchmarkWorkflow(parsed);
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
