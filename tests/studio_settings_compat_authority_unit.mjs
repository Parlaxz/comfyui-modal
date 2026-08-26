// Settings compatibility authority behavioral unit (ex
// studio_legacy_settings_authority_unit.mjs; renamed H20 Wave G â€” the suite
// no longer tests any legacy panel, it pins the SURVIVING Settings/server
// authority + canvas compatibility surface).
//
// Proves the modal-settings.js GPU/output authority contract against REAL
// production source: the module-level GPU functions are evaluated from the
// actual file via a bounded `new Function` slice (imports and DOM-free), and
// output-preference semantics run against the real shared helper module.
//
// H18 Wave G: the overlay panel body is deleted. Only the read-only GPU
// init loader + sync guards remain in modal-settings.js; the explicit-change
// POST path (commitGpuSelection) and the deleted modal-comparison.js reader
// are pinned as absent.
//
// No browser, deployment, live generation, or GPU. Fetch/localStorage/window
// are deterministic in-memory shims.

import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import {
  getOutputPreferences,
  setOutputPreferences,
  syncOutputConfigFromServer,
} from "../web/studio-output-preferences.js";

const ROOT = path.join(import.meta.dirname, "..");
const settingsSource = fs.readFileSync(path.join(ROOT, "web", "modal-settings.js"), "utf8");
const nodeSource = fs.readFileSync(path.join(ROOT, "web", "modal-node.js"), "utf8");

function pass(name) {
  console.log("PASS: " + name);
}

// â”€â”€ shims â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function installStorage(seed) {
  const values = new Map(Object.entries(seed || {}));
  globalThis.localStorage = {
    getItem: (key) => (values.has(key) ? values.get(key) : null),
    setItem: (key, value) => { values.set(String(key), String(value)); },
    removeItem: (key) => { values.delete(key); },
    clear: () => { values.clear(); },
  };
  return values;
}

function installWindow() {
  const events = [];
  globalThis.window = {
    dispatchEvent: (event) => { events.push(event); return true; },
  };
  globalThis.CustomEvent = class CustomEvent {
    constructor(type, init) {
      this.type = type;
      this.detail = init && init.detail;
    }
  };
  return events;
}

// api.fetchApi shim: GET /config served from `getConfig`; POST responses are
// popped from `postQueue` (default { ok: true }). Errors can be queued too.
function makeApi({ getConfig, postQueue }) {
  const calls = [];
  const queue = postQueue || [];
  const api = {
    calls,
    fetchApi: async (url, options) => {
      const method = (options && options.method) || "GET";
      const body = options && options.body ? JSON.parse(options.body) : null;
      calls.push({ url: String(url), method, body });
      if (method === "GET") {
        if (getConfig instanceof Error) throw getConfig;
        return getConfig;
      }
      const next = queue.length ? queue.shift() : { ok: true, status: 200 };
      if (next instanceof Error) throw next;
      return next;
    },
  };
  return api;
}

function configResponse(cfg) {
  return { ok: true, status: 200, json: async () => cfg };
}

// Evaluate the REAL module-level GPU/sync functions from modal-settings.js.
// Slice bounds are literal markers; drift fails loudly here and in the
// Python structural suite.
function loadGpuModule(api, seed) {
  installStorage(seed);
  installWindow();
  const start = settingsSource.indexOf("function pickInitialGpu");
  const end = settingsSource.indexOf("// --- Toast notification ---");
  const slice = settingsSource.slice(start, end);
  const factory = new Function(
    "api",
    "localStorage",
    "window",
    "MODAL_PREFIX",
    "STORAGE_KEY_GPU",
    "syncOutputConfigFromServer",
    slice +
      "\nreturn { pickInitialGpu, loadGpuConfig," +
      " syncLegacyGpuConfigOnce, syncLegacyOutputPrefsOnce };",
  );
  return factory(api, globalThis.localStorage, globalThis.window, "/comfymodal", "comfymodal_gpu", syncOutputConfigFromServer);
}

async function withFreshGlobals(fn) {
  const previousStorage = globalThis.localStorage;
  const previousWindow = globalThis.window;
  try {
    await fn();
  } finally {
    globalThis.localStorage = previousStorage;
    globalThis.window = previousWindow;
  }
}

// â”€â”€ A. GPU authority (real sliced production code) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

await withFreshGlobals(async () => {
  // 1+2. Panel open performs ZERO GPU POST; server GPU wins stale LS.
  const api = makeApi({
    getConfig: configResponse({
      gpu: "h100",
      default_gpu: "rtx-pro-6000",
      available_gpus: [
        { value: "a100", label: "A100" },
        { value: "h100", label: "H100" },
      ],
    }),
  });
  const gpu = loadGpuModule(api, { comfymodal_gpu: "a100" });
  const result = await gpu.loadGpuConfig();
  assert.equal(result.selectedGpu, "h100"); // server beats stale LS
  assert.equal(globalThis.localStorage.getItem("comfymodal_gpu"), "h100");
  assert.ok(!api.calls.some((c) => c.method === "POST"), "page load must not POST GPU");
  assert.equal(api.calls.filter((c) => c.url.endsWith("/config") && c.method === "GET").length, 1);
  assert.equal(globalThis.window._comfyModalGpu, undefined); // dead write removed
  assert.deepEqual(result.options.map((o) => o.value), ["a100", "h100"]);
  pass("1. page load performs zero GPU POST (read-only init)");
  pass("2. server GPU wins stale localStorage at initialization");
});

await withFreshGlobals(async () => {
  // 6-fallback. Server unavailable â†’ stored choice displayed truthfully,
  // user value never erased, still zero POST.
  const api = makeApi({ getConfig: new Error("server down") });
  const gpu = loadGpuModule(api, { comfymodal_gpu: "a100" });
  const result = await gpu.loadGpuConfig();
  assert.equal(result.selectedGpu, "a100");
  assert.equal(globalThis.localStorage.getItem("comfymodal_gpu"), "a100");
  assert.ok(!api.calls.some((c) => c.method === "POST"));
  pass("6b. server-load failure falls back to stored GPU without erasing it");
});

await withFreshGlobals(async () => {
  // 3+4. H18 Wave G: the explicit-change POST path (commitGpuSelection /
  // getAcknowledgedGpu) is deleted â€” no GPU POST site may remain anywhere
  // in modal-settings.js (modern Settings owns the writer since F8).
  assert.equal(settingsSource.includes("commitGpuSelection"), false);
  assert.equal(settingsSource.includes("getAcknowledgedGpu"), false);
  assert.equal(settingsSource.split("JSON.stringify({ gpu })").length - 1, 0, "zero GPU POST sites");
  pass("3. explicit-change GPU POST path deleted (Wave G)");
  pass("4. no false-authority revert machinery remains (nothing can POST)");
});

await withFreshGlobals(async () => {
  // 12. Build/render lifecycle issues exactly ONE sync each for GPU + outputs.
  let outputSyncs = 0;
  const countingSync = async () => { outputSyncs += 1; };
  const api = makeApi({
    getConfig: configResponse({ gpu: "h100", available_gpus: [] }),
  });
  installStorage({});
  installWindow();
  const start = settingsSource.indexOf("function pickInitialGpu");
  const end = settingsSource.indexOf("// --- Toast notification ---");
  const factory = new Function(
    "api", "localStorage", "window", "MODAL_PREFIX", "STORAGE_KEY_GPU", "syncOutputConfigFromServer",
    settingsSource.slice(start, end) +
      "\nreturn { syncLegacyGpuConfigOnce, syncLegacyOutputPrefsOnce };",
  );
  const gpu = factory(api, globalThis.localStorage, globalThis.window, "/comfymodal", "comfymodal_gpu", countingSync);
  await Promise.all([gpu.syncLegacyGpuConfigOnce(), gpu.syncLegacyGpuConfigOnce()]);
  await gpu.syncLegacyGpuConfigOnce();
  await Promise.all([gpu.syncLegacyOutputPrefsOnce(), gpu.syncLegacyOutputPrefsOnce()]);
  await gpu.syncLegacyOutputPrefsOnce();
  const gets = api.calls.filter((c) => c.method === "GET").length;
  assert.equal(gets, 1, "repeated page loads share one GPU sync");
  assert.equal(outputSyncs, 1, "repeated page loads share one output sync");
  assert.ok(!api.calls.some((c) => c.method === "POST"));
  pass("12. no settings sync request duplicated across build/render lifecycle");
});

// â”€â”€ B. Output preferences through the shared helper (real module) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

const SERVER_A = {
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

function installFetch(handler) {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = handler;
  return () => { globalThis.fetch = originalFetch; };
}

await withFreshGlobals(async () => {
  // 5. Server output preferences win stale LS on successful read.
  const staleLS = {
    comfymodal_output_format: "jpeg",
    comfymodal_quality: "20",
    comfymodal_webp_lossless_compression: "max",
    comfymodal_auto_save_local: "true",
    comfymodal_save_folder: "stale/folder",
    comfymodal_save_metadata_sidecar: "false",
  };
  installStorage(staleLS);
  installWindow();
  let posts = 0;
  const restore = installFetch(async (url, options) => {
    const method = (options && options.method) || "GET";
    if (method === "POST") { posts += 1; }
    return configResponse(SERVER_A);
  });
  try {
    await syncOutputConfigFromServer();
    const prefs = getOutputPreferences();
    assert.equal(prefs.output_format, "original");
    assert.equal(prefs.quality, 75);
    assert.equal(prefs.webp_lossless_compression, "balanced");
    assert.equal(prefs.auto_save_local, false);
    assert.equal(prefs.save_folder, "output/modal");
    assert.equal(prefs.save_metadata_sidecar, true);
    assert.equal(posts, 0, "initial sync is read-only");
    assert.deepEqual(
      {
        output_format: globalThis.window._comfyModalOutputOptions.output_format,
        quality: globalThis.window._comfyModalOutputOptions.quality,
        save_folder: globalThis.window._comfyModalOutputOptions.save_folder,
      },
      { output_format: "original", quality: 75, save_folder: "output/modal" },
    );
  } finally {
    restore();
  }
  pass("5. server output preferences win stale localStorage (all six keys)");
});

await withFreshGlobals(async () => {
  // 6. Server-load failure â†’ LS/default fallback preserved truthfully.
  installStorage({
    comfymodal_output_format: "jpeg",
    comfymodal_quality: "20",
    comfymodal_auto_save_local: "true",
    comfymodal_save_metadata_sidecar: "false",
  });
  installWindow();
  const restore = installFetch(async () => { throw new Error("unreachable"); });
  try {
    await syncOutputConfigFromServer();
    const prefs = getOutputPreferences();
    assert.equal(prefs.output_format, "jpeg");
    assert.equal(prefs.quality, 20);
    assert.equal(prefs.auto_save_local, true);
    assert.equal(prefs.save_metadata_sidecar, false);
  } finally {
    restore();
  }
  pass("6. server-load failure uses stored/default fallback without erasing values");
});

await withFreshGlobals(async () => {
  // 7+9. Successful user edit updates server + cache + window global (+ event).
  installStorage({});
  const events = installWindow();
  const bodies = [];
  const restore = installFetch(async (url, options) => {
    const method = (options && options.method) || "GET";
    if (method === "POST") bodies.push(JSON.parse(options.body));
    return configResponse(SERVER_A);
  });
  try {
    await syncOutputConfigFromServer(); // establish acknowledged baseline A
    const merged = await setOutputPreferences({ output_format: "webp_lossy", quality: 88 });
    assert.equal(bodies.length, 1); // the initial sync is GET-only; this is the edit POST
    const editBody = bodies[bodies.length - 1];
    assert.equal(editBody.output_format, "webp_lossy");
    assert.equal(editBody.quality, 88);
    assert.equal(getOutputPreferences().output_format, "webp_lossy");
    assert.equal(getOutputPreferences().quality, 88);
    assert.equal(globalThis.window._comfyModalOutputOptions.output_format, "webp_lossy");
    assert.equal(globalThis.window._comfyModalOutputOptions.quality, 88);
    const event = events.findLast((e) => e.type === "comfymodal:output-preferences-changed");
    assert.ok(event, "success must notify listeners (Comparison/canvas surfaces)");
    assert.equal(event.detail.quality, 88);
    assert.equal(merged.save_folder, "output/modal");
  } finally {
    restore();
  }
  pass("7. successful output edit updates server, cache, window global, listeners");
  pass("9. _comfyModalOutputOptions remains available and accurate after sync/edit");
});

await withFreshGlobals(async () => {
  // 8. Failed output edit leaves NO false browser authority.
  installStorage({});
  installWindow();
  const restore = installFetch(async (url, options) => {
    if ((options && options.method) === "POST") return { ok: false, status: 500 };
    return configResponse(SERVER_A);
  });
  try {
    await syncOutputConfigFromServer(); // baseline A in LS + window
    const before = getOutputPreferences();
    const windowBefore = JSON.stringify(globalThis.window._comfyModalOutputOptions);
    await assert.rejects(
      setOutputPreferences({ output_format: "jpeg", quality: 33 }),
      /rejected/i,
    );
    const after = getOutputPreferences();
    assert.deepEqual(after, before, "LS must keep the prior acknowledged values");
    assert.equal(JSON.stringify(globalThis.window._comfyModalOutputOptions), windowBefore);
  } finally {
    restore();
  }
  pass("8. failed output edit does not leave false browser authority");
});

// â”€â”€ C. Compatibility contracts (structural, unmodified consumers) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

assert.ok(settingsSource.includes('from "./studio-output-preferences.js"'));
assert.ok(!settingsSource.includes("_comfyModalGpu"), "dead _comfyModalGpu writes removed");
assert.ok(nodeSource.includes("window._comfyModalOutputOptions"), "canvas reader intact");
assert.ok(nodeSource.includes('localStorage.getItem(STORAGE_KEY_OUTPUT_FORMAT)'), "canvas LS fallback intact");
// H18 Wave G: modal-comparison.js is deleted; its reader died with it and
// no web module may reference the deleted module.
assert.ok(!fs.existsSync(path.join(ROOT, "web", "modal-comparison.js")), "comparison module deleted");
for (const dirEntry of fs.readdirSync(path.join(ROOT, "web"))) {
  if (!dirEntry.endsWith(".js")) continue;
  const src = fs.readFileSync(path.join(ROOT, "web", dirEntry), "utf8");
  assert.ok(!src.includes("modal-comparison"), `${dirEntry} references deleted comparison module`);
}
pass("10. canvas compatibility contract structurally intact");
pass("11. Comparison reader retired with the deleted module (Wave G)");

console.log("ALL SETTINGS COMPAT AUTHORITY TESTS PASSED");
