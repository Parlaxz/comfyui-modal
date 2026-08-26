// Modal Studio E4A Preview Settings and sparse-detail contract tests.
//
// No browser, deployment, live generation, or GPU. Fetch and localStorage are
// deterministic in-memory shims; sparse detail coverage also checks the shared
// nullable-child guard directly.

import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import {
  PREVIEW_DEFAULTS,
  buildModalOptions,
  buildPreviewModalOptions,
  getOutputPreferences,
  loadModalOptions,
  setOutputPreferences,
} from "../web/studio-output-preferences.js";
import {
  buildModernExperimentDefinition,
  detachModernExperiment,
  executeModernExperimentRun,
} from "../web/studio-experiment-mode.js";
import { appendIfPresent } from "../web/studio-history-v2-detail.js";

const ROOT = path.join(import.meta.dirname, "..");
const settingsSource = fs.readFileSync(path.join(ROOT, "web", "studio-settings.js"), "utf8");
const detailSource = fs.readFileSync(path.join(ROOT, "web", "studio-history-v2-detail.js"), "utf8");
const configSource = fs.readFileSync(path.join(ROOT, "__init__.py"), "utf8");

function section(name) {
  console.log("PASS: " + name);
}

function installStorage() {
  const values = new Map();
  globalThis.localStorage = {
    getItem: (key) => (values.has(key) ? values.get(key) : null),
    setItem: (key, value) => { values.set(String(key), String(value)); },
    removeItem: (key) => { values.delete(key); },
    clear: () => { values.clear(); },
  };
  return values;
}

function installWindow() {
  globalThis.window = {
    _comfyModalOutputOptions: {},
    _comfyModalExecutionMode: "v2",
    dispatchEvent: () => true,
  };
  globalThis.CustomEvent = class CustomEvent {
    constructor(type, init) {
      this.type = type;
      this.detail = init && init.detail;
    }
  };
}

function makeState() {
  return {
    activePage: "playground",
    playground: {
      featureId: "txt2img",
      controls: { prompt: "base prompt", negative_prompt: "" },
      experimentAxes: { steps: { enabled: true, values: [20, 28] } },
      _workflowRun: {
        workflowId: "wf_1",
        workflowVersionId: "ver_1",
        presetId: "preset_1",
        workflowName: "Portrait Pro",
        presetName: "preset_a",
        controlValues: { steps: 20, seed: 42 },
        runContext: { workflow: { id: "wf_1" } },
      },
    },
  };
}

const storage = installStorage();
installWindow();
let remoteConfig = {
  execution_mode: "v2",
  output_format: "original",
  quality: 75,
  webp_lossless_compression: "balanced",
  auto_save_local: false,
  save_folder: "output/modal",
  save_metadata_sidecar: true,
  preview_default: "off",
  preview_codec: "webp",
  preview_quality: 70,
};
const calls = [];
const originalFetch = globalThis.fetch;
globalThis.fetch = async (url, options) => {
  const request = {
    url: String(url),
    method: (options && options.method) || "GET",
    body: options && options.body ? JSON.parse(options.body) : null,
  };
  calls.push(request);
  if (request.method === "POST" && request.url.endsWith("/studio/experiment-v2")) {
    return {
      ok: true,
      status: 200,
      json: async () => ({
        status: "ok",
        experiment_id: "exp_e4a",
        item: {
          status: "completed",
          total: 1,
          counts: { queued: 0, running: 0, completed: 1, failed: 0, canceled: 0, interrupted: 0 },
          cells: [{ cell_id: "cell_0", status: "completed" }],
        },
      }),
    };
  }
  if (request.url.includes("/history-v2/experiments/exp_e4a/status")) {
    return {
      ok: true,
      status: 200,
      json: async () => ({
        status: "ok",
        item: {
          status: "completed",
          total: 1,
          counts: { queued: 0, running: 0, completed: 1, failed: 0, canceled: 0, interrupted: 0 },
          cells: [{ cell_id: "cell_0", status: "completed" }],
        },
      }),
    };
  }
  return { ok: true, status: 200, json: async () => remoteConfig };
};

try {
  // 1. Canonical defaults are OFF/WebP/70.
  storage.clear();
  assert.deepEqual(PREVIEW_DEFAULTS, {
    preview_default: "off",
    preview_codec: "webp",
    preview_quality: 70,
  });
  assert.deepEqual(
    buildPreviewModalOptions(getOutputPreferences()),
    { preview_default: "off", preview_enabled: false, preview_codec: "webp", preview_quality: 70 },
  );
  section("1. Preview defaults OFF/WebP/70");

  // 2. Shared persistence includes Preview fields and preserves failure reversion.
  await setOutputPreferences({ preview_default: "on", preview_codec: "webp", preview_quality: 70 });
  assert.equal(storage.get("comfymodal_preview_default"), "on");
  assert.equal(storage.get("comfymodal_preview_codec"), "webp");
  assert.equal(storage.get("comfymodal_preview_quality"), "70");
  assert.equal(calls.at(-1).body.preview_default, "on");
  assert.equal(calls.at(-1).body.preview_quality, 70);
  const beforeRejected = getOutputPreferences();
  await assert.rejects(
    setOutputPreferences({ preview_quality: 101 }),
    /Invalid preview_quality/,
  );
  assert.deepEqual(getOutputPreferences(), beforeRejected);
  section("2. Shared Preview persistence and failure reversion");

  // 3. Server-backed config values are captured into one immutable options object.
  remoteConfig = { ...remoteConfig, preview_default: "on", preview_codec: "webp", preview_quality: 70 };
  const captured = await loadModalOptions("/comfymodal");
  assert.equal(captured.preview_enabled, true);
  assert.equal(captured.preview_codec, "webp");
  assert.equal(captured.preview_quality, 70);
  const singleCaptured = await loadModalOptions("/comfymodal");
  storage.set("comfymodal_preview_default", "off");
  assert.equal(singleCaptured.preview_enabled, true);
  assert.equal(singleCaptured.preview_default, "on");
  section("3. Single captures Preview settings at request time");

  // 4. Experiment carries the same copied options object with no fanout/concurrency.
  const state = makeState();
  const definition = buildModernExperimentDefinition(state, { modalOptions: singleCaptured });
  assert.deepEqual(definition.definition.modal_options, singleCaptured);
  assert.equal("concurrency" in definition, false);
  assert.equal("concurrency" in definition.definition, false);
  assert.equal("cells" in definition, false);
  const modernResult = await executeModernExperimentRun(state, {}, { apiBase: "/comfymodal" });
  assert.equal(modernResult.status, "ok");
  const modernPosts = calls.filter((call) => call.method === "POST" && call.url.endsWith("/studio/experiment-v2"));
  assert.equal(modernPosts.length, 1);
  assert.deepEqual(modernPosts[0].body.definition.modal_options, singleCaptured);
  assert.equal(calls.filter((call) => call.method === "POST" && call.url.endsWith("/studio/experiment")).length, 0);
  detachModernExperiment(state);
  section("4. One frozen Experiment options object, one POST, no fanout/concurrency");

  // 5. The active Settings surface no longer presents an inert concurrency input.
  assert.equal(settingsSource.includes('data-testid": "settings-global-concurrency"'), false);
  assert.equal(settingsSource.includes("Experiments run up to 6 cells concurrently"), true);
  assert.equal(settingsSource.includes('data-testid": "settings-preview-auto-save"'), false);
  assert.equal(configSource.includes('"preview_default"'), true);
  assert.equal(configSource.includes('"preview_codec"'), true);
  assert.equal(configSource.includes('"preview_quality"'), true);
  assert.equal(configSource.includes('not in ("off", "on")'), true);
  assert.equal(configSource.includes('_preview_quality < 1'), true);
  section("5. Truthful global concurrency UI and validated config fields");

  // 6. Sparse detail sections ignore null children and preserve empty-output paths.
  const parent = { children: [], appendChild(child) { this.children.push(child); } };
  appendIfPresent(parent, null);
  appendIfPresent(parent, { nodeType: 1 });
  assert.equal(parent.children.length, 1);
  assert.equal(detailSource.includes("appendIfPresent(col, buildParamsSection(record))"), true);
  assert.equal(detailSource.includes('text: "No outputs"'), true);
  assert.equal(detailSource.includes("No image"), true);
  assert.equal(detailSource.includes("Original generation failed"), true);
  section("6. Sparse, empty, and failed detail records keep safe placeholders");
} finally {
  globalThis.fetch = originalFetch;
  delete globalThis.localStorage;
  delete globalThis.window;
  delete globalThis.CustomEvent;
}

console.log("PASS: studio phase E Preview settings unit tests");
