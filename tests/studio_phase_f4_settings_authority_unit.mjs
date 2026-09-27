// Modal Studio F4A — Modern Settings authority guard + truthful semantics.
//
// Deterministic Node unit tests: no browser, no network, no GPU, no live
// generation. A minimal DOM stub supports exactly the selector shapes
// web/studio-settings.js uses; fetch/localStorage/window are in-memory shims.
//
// Covered contracts:
//  1. Settings-key authority contract — every MODERN_SETTINGS_KEYS entry is
//     classified with real reader/writer evidence; stale reset-only keys
//     (comfymodal_global_concurrency, comfymodal_preview_auto_save) fail the
//     registry-equality check and must not appear anywhere in the source.
//     H12: comfymodal_enabled left the registry — modern Settings never
//     writes/resets it; the canvas keeps its own compatibility key.
//  2. Heavy-tracing restart banner reflects server persisted-vs-effective
//     truth (GET /profile/level {level, effective}); a stale/missing
//     localStorage value can never create a false banner.
//  3. GPU dropdown prefers the server-reported value over localStorage.
//  4. Modern Settings no longer writes the dead window._comfyModalGpu global.
//  5. H12: Run mode control and V1/V2 engine selector are retired; Reset All
//     no longer POSTs an engine value (GPU-only POST) and its disclosure copy
//     is truthful; durable user-data namespaces survive.
//  6. Preview/Output controls still load server values and save through the
//     shared output-preferences module.
//  7. Experiments section stays informational (fixed width 6, no controls).
//  8. Settings search keeps working after the stale-key cleanup.
//  9. H12: one-time engine migration notice renders when the server
//     surfaces engine_migration_notice.

import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { renderSettings } from "../web/studio-settings.js";

const ROOT = path.join(import.meta.dirname, "..");
const WEB = path.join(ROOT, "web");
const readWeb = (name) => fs.readFileSync(path.join(WEB, name), "utf8");

const settingsSource = readWeb("studio-settings.js");
const outputPrefsSource = readWeb("studio-output-preferences.js");
const playgroundSource = readWeb("studio-playground.js");
const playgroundStateSource = readWeb("studio-playground-state.js");
const modalNodeSource = readWeb("modal-node.js");
const historyV2Source = readWeb("studio-history-v2.js");

function section(name) {
  console.log("PASS: " + name);
}

// ── Source-level authority contract ───────────────────────────────────────

// Deliberate contract map: every modern Settings key must be classified here
// with at least one concrete reader/writer evidence pair. Evidence is checked
// against the named module's source, so removing a consumer without updating
// this map fails the test, and adding a reset-only key to
// MODERN_SETTINGS_KEYS without a classification fails the registry equality.
const SETTINGS_KEY_CONTRACT = {
  // H12: comfymodal_enabled is deliberately ABSENT — it left
  // MODERN_SETTINGS_KEYS with the Run-mode retirement. The canvas-era key is
  // owned by modal-node.js (window._comfyModalEnabled), asserted below.
  "comfymodal_gpu": {
    classification: "value-setting",
    evidence: [
      [settingsSource, 'localStorage.getItem("comfymodal_gpu"'],
      [settingsSource, 'localStorage.setItem("comfymodal_gpu"'],
    ],
  },
  "comfymodal_output_format": {
    classification: "value-setting",
    evidence: [[outputPrefsSource, 'OUTPUT_FORMAT: "comfymodal_output_format"']],
  },
  "comfymodal_quality": {
    classification: "value-setting",
    evidence: [[outputPrefsSource, 'QUALITY: "comfymodal_quality"']],
  },
  "comfymodal_webp_lossless_compression": {
    classification: "value-setting",
    evidence: [[outputPrefsSource, 'WEBP_LC: "comfymodal_webp_lossless_compression"']],
  },
  "comfymodal_auto_save_local": {
    classification: "value-setting",
    evidence: [[outputPrefsSource, 'AUTOSAVE: "comfymodal_auto_save_local"']],
  },
  "comfymodal_save_folder": {
    classification: "value-setting",
    evidence: [[outputPrefsSource, 'SAVEFOLDER: "comfymodal_save_folder"']],
  },
  "comfymodal_save_metadata_sidecar": {
    classification: "value-setting",
    evidence: [[outputPrefsSource, 'SIDECAR: "comfymodal_save_metadata_sidecar"']],
  },
  "comfymodal_preview_default": {
    classification: "value-setting",
    evidence: [
      [outputPrefsSource, 'PREVIEW_DEFAULT: "comfymodal_preview_default"'],
      [settingsSource, 'localStorage.getItem("comfymodal_preview_default"'],
    ],
  },
  "comfymodal_preview_codec": {
    classification: "value-setting",
    evidence: [
      [outputPrefsSource, 'PREVIEW_CODEC: "comfymodal_preview_codec"'],
      [settingsSource, 'localStorage.getItem("comfymodal_preview_codec"'],
    ],
  },
  "comfymodal_preview_quality": {
    classification: "value-setting",
    evidence: [
      [outputPrefsSource, 'PREVIEW_QUALITY: "comfymodal_preview_quality"'],
      [settingsSource, 'localStorage.getItem("comfymodal_preview_quality"'],
    ],
  },
  "comfymodal-studio-history-columns": {
    // F4C: consumed by the mounted History V2 feed grid (normalized 2–8,
    // default 6, applied as an inline CSS custom property on the page root).
    // The legacy History page reader was retired in Phase H9.
    classification: "value-setting",
    evidence: [
      [settingsSource, 'localStorage.setItem("comfymodal-studio-history-columns"'],
      [historyV2Source, '"comfymodal-studio-history-columns"'],
      [historyV2Source, "--comfymodal-studio-history-columns"],
    ],
  },
  "comfymodal_heavy_tracing": {
    classification: "value-setting",
    evidence: [
      [settingsSource, 'localStorage.getItem("comfymodal_heavy_tracing"'],
      [settingsSource, 'localStorage.setItem("comfymodal_heavy_tracing"'],
    ],
  },
  "comfymodal-studio-panel-width": {
    classification: "ui-preference",
    evidence: [[playgroundSource, '"comfymodal-studio-panel-width"']],
  },
  "comfymodal.studio.playground.carousel-cleared.v1": {
    classification: "ui-preference",
    evidence: [[playgroundStateSource, '"comfymodal.studio.playground.carousel-cleared.v1"']],
  },
};

function parseModernSettingsKeys(source) {
  const marker = "const MODERN_SETTINGS_KEYS = [";
  const start = source.indexOf(marker);
  assert.notEqual(start, -1, "MODERN_SETTINGS_KEYS registry missing");
  const end = source.indexOf("];", start);
  const body = source.slice(start + marker.length, end);
  return body.match(/"([^"]+)"/g).map((s) => s.slice(1, -1));
}

// ── DOM / browser-environment stubs ───────────────────────────────────────

function matchesClass(node, cls) {
  return (" " + (node.className || "") + " ").indexOf(" " + cls + " ") !== -1;
}

function matchesSelector(node, selector) {
  // Supported shapes only: '[data-testid="X"]', '[data-search]', '.class',
  // '[data-search]:not(.class)'.
  const notMatch = selector.match(/^([^:]+):not\(\.([^)]+)\)$/);
  let base = selector;
  let notClass = null;
  if (notMatch) {
    base = notMatch[1].trim();
    notClass = notMatch[2];
  }
  if (notClass && matchesClass(node, notClass)) return false;
  if (base.charAt(0) === ".") return matchesClass(node, base.slice(1));
  const attr = base.match(/^\[([^=\]]+)(?:="([^"]*)")?\]$/);
  if (attr) {
    const name = attr[1];
    const expected = attr[2];
    const actual = name === "data-testid"
      ? node.dataset.testid
      : name === "data-search"
        ? node.dataset.search
        : node.attributes[name];
    if (expected === undefined) return actual !== undefined && actual != null;
    return actual === expected;
  }
  return false;
}

function createDocumentStub() {
  function makeNode(tag) {
    let ownText = "";
    const node = {
      tagName: String(tag || "div").toUpperCase(),
      children: [],
      parentNode: null,
      attributes: {},
      dataset: {},
      style: {},
      listeners: {},
      className: "",
      value: "",
      disabled: false,
      checked: false,
      appendChild(child) {
        child.parentNode = this;
        this.children.push(child);
        return child;
      },
      removeChild(child) {
        const i = this.children.indexOf(child);
        if (i !== -1) this.children.splice(i, 1);
        child.parentNode = null;
        return child;
      },
      get firstChild() {
        return this.children.length ? this.children[0] : null;
      },
      addEventListener(type, fn) {
        (this.listeners[type] = this.listeners[type] || []).push(fn);
      },
      removeEventListener(type, fn) {
        const list = this.listeners[type];
        if (!list) return;
        const i = list.indexOf(fn);
        if (i !== -1) list.splice(i, 1);
      },
      dispatch(type) {
        for (const fn of (this.listeners[type] || []).slice()) {
          fn({ type: type, target: this, preventDefault() {} });
        }
      },
      setAttribute(name, v) {
        this.attributes[name] = String(v);
        if (name === "data-testid") this.dataset.testid = String(v);
        if (name === "data-search") this.dataset.search = String(v);
        if (name === "data-section") this.dataset.section = String(v);
        // Mirror boolean attributes onto their DOM properties the way a
        // browser does for freshly created (never-interacted) elements.
        if (name === "checked") this.checked = true;
        if (name === "disabled") this.disabled = true;
      },
      removeAttribute(name) {
        delete this.attributes[name];
        if (name === "checked") this.checked = false;
        if (name === "disabled") this.disabled = false;
      },
      getAttribute(name) {
        return name in this.attributes ? this.attributes[name] : null;
      },
      closest(selector) {
        let cur = this;
        while (cur) {
          if (selector.charAt(0) === "." && matchesClass(cur, selector.slice(1))) return cur;
          cur = cur.parentNode;
        }
        return null;
      },
      querySelector(sel) {
        return this.querySelectorAll(sel)[0] || null;
      },
      querySelectorAll(selector) {
        const out = [];
        const visit = (node) => {
          for (const child of node.children) {
            if (matchesSelector(child, selector)) out.push(child);
            visit(child);
          }
        };
        visit(this);
        return out;
      },
    };
    node.classList = {
      add(c) {
        if (!matchesClass(node, c)) node.className = (node.className ? node.className + " " : "") + c;
      },
      remove(c) {
        node.className = (" " + node.className + " ").replace(" " + c + " ", " ").trim();
      },
      toggle(c, force) {
        const has = matchesClass(node, c);
        const want = force === undefined ? !has : !!force;
        if (want && !has) node.classList.add(c);
        if (!want && has) node.classList.remove(c);
        return want;
      },
      contains(c) {
        return matchesClass(node, c);
      },
    };
    Object.defineProperty(node, "textContent", {
      get() {
        if (ownText) return ownText;
        return node.children.map((c) => (c.textContent == null ? "" : c.textContent)).join("");
      },
      set(v) {
        ownText = String(v);
      },
    });
    return node;
  }
  return {
    createElement(tag) {
      return makeNode(tag);
    },
    createTextNode(text) {
      return { nodeType: 3, textContent: String(text), parentNode: null };
    },
  };
}

function installBrowserStubs() {
  globalThis.document = createDocumentStub();
  const values = new Map();
  globalThis.localStorage = {
    getItem: (key) => (values.has(key) ? values.get(key) : null),
    setItem: (key, value) => {
      values.set(String(key), String(value));
    },
    removeItem: (key) => {
      values.delete(key);
    },
    clear: () => {
      values.clear();
    },
  };
  const windowListeners = {};
  globalThis.window = {
    addEventListener(type, fn) {
      (windowListeners[type] = windowListeners[type] || []).push(fn);
    },
    removeEventListener(type, fn) {
      const list = windowListeners[type];
      if (!list) return;
      const i = list.indexOf(fn);
      if (i !== -1) list.splice(i, 1);
    },
    dispatchEvent(event) {
      for (const fn of (windowListeners[event.type] || []).slice()) fn(event);
      return true;
    },
  };
  globalThis.CustomEvent = class CustomEvent {
    constructor(type, init) {
      this.type = type;
      this.detail = init && init.detail;
    }
  };
  let confirmMessage = null;
  globalThis.confirm = (message) => {
    _confirmMessage = message;
    return true;
  };
  return { storage: values, confirmBox: () => confirmMessage };
}

let _confirmMessage = null;
function currentConfirmMessage() {
  return _confirmMessage;
}

// ── Deterministic fetch shim ──────────────────────────────────────────────

function installFetch(router) {
  const calls = [];
  const inflight = { count: 0 };
  globalThis.fetch = async (url, options) => {
    inflight.count++;
    try {
      const method = ((options && options.method) || "GET").toUpperCase();
      let body = null;
      if (options && typeof options.body === "string") {
        try {
          body = JSON.parse(options.body);
        } catch (_) {
          body = options.body;
        }
      }
      const call = { url: String(url), method: method, body: body };
      calls.push(call);
      await Promise.resolve();
      // Route eagerly: a real server processes the request before the
      // response is delivered, and studio-settings.js does not always read
      // the POST response body.
      const payload = router(call);
      return { ok: true, status: 200, json: async () => payload };
    } finally {
      inflight.count--;
    }
  };
  return { calls: calls, inflight: inflight };
}

async function settle(inflight) {
  for (let i = 0; i < 100 && inflight.count > 0; i++) {
    await new Promise((resolve) => setImmediate(resolve));
  }
  for (let i = 0; i < 10; i++) {
    await new Promise((resolve) => setImmediate(resolve));
  }
}

function makeConfig(overrides) {
  return Object.assign(
    {
      execution_mode: "v2",
      execution_mode_locked: false,
      engine_migration_notice: null,
      gpu: "",
      default_gpu: "rtx-pro-6000",
      available_gpus: [
        { value: "gpu-a", label: "GPU A" },
        { value: "gpu-b", label: "GPU B" },
      ],
      output_format: "original",
      quality: 75,
      webp_lossless_compression: "balanced",
      auto_save_local: false,
      save_folder: "output/modal",
      save_metadata_sidecar: true,
      preview_default: "off",
      preview_codec: "webp",
      preview_quality: 70,
    },
    overrides || {},
  );
}

function makeRouter(config, profile) {
  return function route(call) {
    if (call.url.endsWith("/config")) {
      if (call.method === "POST") return { status: "ok" };
      return config;
    }
    if (call.url.endsWith("/profile/level")) {
      if (call.method === "POST") {
        profile.level = call.body.level;
        return { status: "ok", level: profile.level };
      }
      return { status: "ok", level: profile.level, effective: profile.effective };
    }
    if (call.url.endsWith("/deploy/status")) return { state: "ready", message: "fake" };
    if (call.url.endsWith("/studio/snapshots")) return { snapshots: [] };
    if (call.url.endsWith("/studio/presets")) return { presets: [] };
    if (call.url.endsWith("/studio/backends")) return { backends: [] };
    if (call.url.endsWith("/open-folder")) return { status: "ok" };
    return {};
  };
}

function renderPage() {
  const state = { settings: { activeLegacyTab: "", activeSection: "" } };
  const context = { apiBase: "/comfymodal", setPage() {} };
  return renderSettings(state, context);
}

const byTestid = (page, testid) => page.querySelector('[data-testid="' + testid + '"]');
const bannerDisplay = (page) => byTestid(page, "settings-restart-banner").style.display;

// ── Tests ─────────────────────────────────────────────────────────────────

const realSetTimeout = globalThis.setTimeout;
globalThis.setTimeout = () => 0;

try {
  // 1. Registry equals the authority contract exactly; every evidence pair
  //    exists; the two removed stale keys appear nowhere in modern Settings.
  const registryKeys = parseModernSettingsKeys(settingsSource).sort();
  const contractKeys = Object.keys(SETTINGS_KEY_CONTRACT).sort();
  assert.deepEqual(registryKeys, contractKeys);
  for (const [key, entry] of Object.entries(SETTINGS_KEY_CONTRACT)) {
    assert.ok(entry.classification, key + " missing classification");
    assert.ok(entry.evidence.length >= 1, key + " missing reader/writer evidence");
    for (const [source, needle] of entry.evidence) {
      assert.ok(
        source.includes(needle),
        key + " evidence gone from source: " + needle,
      );
    }
  }
  assert.equal(settingsSource.includes("comfymodal_global_concurrency"), false);
  assert.equal(settingsSource.includes("comfymodal_preview_auto_save"), false);
  section("1. Settings-key authority contract pins MODERN_SETTINGS_KEYS; stale keys gone");

  // 1b. H12: comfymodal_enabled never written/reset by modern Settings; the
  //     canvas compatibility consumer still exists in modal-node.js.
  assert.equal(settingsSource.includes("comfymodal_enabled"), false);
  assert.ok(
    modalNodeSource.includes("window._comfyModalEnabled"),
    "canvas consumer window._comfyModalEnabled must survive",
  );
  section("1b. comfymodal_enabled absent from modern Settings; canvas key consumer intact");

  // 2. Durable user-data namespaces are structurally outside the reset set.
  for (const durable of [
    "comfymodal.studio.playground.v1",
    "comfymodal.studio.playground.drafts.v1",
    "comfymodal.studio.playground.results.v1",
  ]) {
    assert.equal(registryKeys.includes(durable), false, durable + " must survive resets");
  }
  section("2. Durable product-data namespaces excluded from reset bookkeeping");

  // 3. Tracing banner truth model — persisted == effective → no banner,
  //    even with localStorage missing entirely (case A + D).
  installBrowserStubs();
  const profileA = { level: "detailed", effective: "detailed" };
  const fetchA = installFetch(makeRouter(makeConfig(), profileA));
  const pageA = renderPage();
  await settle(fetchA.inflight);
  assert.equal(bannerDisplay(pageA), "none");
  assert.equal(byTestid(pageA, "settings-heavy-tracing").value, "detailed");
  section("3. persisted==effective (detailed/detailed), LS missing → no banner");

  // 4. persisted != effective → restart banner (case B).
  installBrowserStubs();
  const profileB = { level: "off", effective: "detailed" };
  const fetchB = installFetch(makeRouter(makeConfig(), profileB));
  const pageB = renderPage();
  await settle(fetchB.inflight);
  assert.equal(bannerDisplay(pageB), "flex");
  section("4. persisted(off)!=effective(detailed) → restart banner");

  // 5. Stale localStorage cannot create a false banner (case D variant).
  installBrowserStubs();
  globalThis.localStorage.setItem("comfymodal_heavy_tracing", "off");
  const profileC = { level: "detailed", effective: "detailed" };
  const fetchC = installFetch(makeRouter(makeConfig(), profileC));
  const pageC = renderPage();
  await settle(fetchC.inflight);
  assert.equal(bannerDisplay(pageC), "none");
  section("5. Stale LS 'off' vs server detailed/detailed → no false banner");

  // 6. User change persists, then the banner follows refreshed server truth:
  //    off/off → select summary → POST ok → persisted=summary, effective=detailed.
  installBrowserStubs();
  const profileD = { level: "off", effective: "off" };
  const configD = makeConfig();
  const fetchD = installFetch(makeRouter(configD, profileD));
  const pageD = renderPage();
  await settle(fetchD.inflight);
  assert.equal(bannerDisplay(pageD), "none");
  const tracingD = byTestid(pageD, "settings-heavy-tracing");
  tracingD.value = "summary";
  tracingD.dispatch("change");
  await settle(fetchD.inflight);
  const postLevel = fetchD.calls.find(
    (c) => c.method === "POST" && c.url.endsWith("/profile/level"),
  );
  assert.deepEqual(postLevel.body, { level: "summary" });
  assert.equal(profileD.level, "summary");
  assert.equal(bannerDisplay(pageD), "flex");
  assert.equal(tracingD.value, "summary");
  section("6. Change → POST → refetch: banner shows genuine pending restart");

  // 7. GPU display authority: server value wins over localStorage; dead
  //    window global is never written (render or change).
  installBrowserStubs();
  globalThis.localStorage.setItem("comfymodal_gpu", "gpu-b");
  const configGpu = makeConfig({ gpu: "gpu-a" });
  const fetchE = installFetch(makeRouter(configGpu, { level: "off", effective: "off" }));
  const pageE = renderPage();
  await settle(fetchE.inflight);
  assert.equal(byTestid(pageE, "settings-gpu").value, "gpu-a");
  const gpuSelectE = byTestid(pageE, "settings-gpu");
  gpuSelectE.value = "gpu-b";
  gpuSelectE.dispatch("change");
  await settle(fetchE.inflight);
  const postGpu = fetchE.calls.find(
    (c) => c.method === "POST" && c.url.endsWith("/config"),
  );
  assert.deepEqual(postGpu.body, { gpu: "gpu-b" });
  assert.equal("_comfyModalGpu" in globalThis.window, false);
  assert.equal(settingsSource.includes("_comfyModalGpu"), false);
  section("7. Server GPU wins display conflict; dead _comfyModalGpu write removed");

  // 8. GPU fallback: without a server value a valid LS cache still displays.
  installBrowserStubs();
  globalThis.localStorage.setItem("comfymodal_gpu", "gpu-b");
  const fetchF = installFetch(
    makeRouter(makeConfig({ gpu: "" }), { level: "off", effective: "off" }),
  );
  const pageF = renderPage();
  await settle(fetchF.inflight);
  assert.equal(byTestid(pageF, "settings-gpu").value, "gpu-b");
  section("8. GPU LS cache used only when server reports no value");

  // 9. Reset All: truthful disclosure (no engine reset), GPU-only POST,
  //    settings keys cleared, durable namespaces untouched.
  installBrowserStubs();
  const seededSettingsKeys = [
    "comfymodal_gpu",
    "comfymodal_heavy_tracing",
    "comfymodal-studio-history-columns",
  ];
  for (const k of seededSettingsKeys) globalThis.localStorage.setItem(k, "seeded");
  globalThis.localStorage.setItem("comfymodal.studio.playground.drafts.v1", "user-drafts");
  globalThis.localStorage.setItem("comfymodal.studio.playground.results.v1", "user-results");
  const fetchG = installFetch(
    makeRouter(makeConfig(), { level: "summary", effective: "summary" }),
  );
  const pageG = renderPage();
  await settle(fetchG.inflight);
  byTestid(pageG, "settings-reset-all").dispatch("click");
  await settle(fetchG.inflight);
  const confirmText = currentConfirmMessage();
  assert.equal(confirmText.includes("execution engine"), false, "disclosure must not claim an engine reset");
  assert.ok(confirmText.includes("GPU selection is reset to the default"));
  assert.ok(confirmText.includes("are NOT affected"));
  const configPosts = fetchG.calls.filter(
    (c) => c.method === "POST" && c.url.endsWith("/config"),
  );
  const gpuResetPost = configPosts.find(
    (c) => c.body && c.body.gpu === "rtx-pro-6000",
  );
  assert.ok(gpuResetPost, "Reset All must POST the canonical default GPU");
  assert.deepEqual(
    gpuResetPost.body,
    { gpu: "rtx-pro-6000" },
    "Reset All GPU POST must be GPU-only (no execution_mode)",
  );
  for (const c of configPosts) {
    assert.equal(
      c.body && "execution_mode" in c.body,
      false,
      "No Reset All POST may carry execution_mode (engine forcing retired)",
    );
  }
  const levelPost = fetchG.calls.find(
    (c) => c.method === "POST" && c.url.endsWith("/profile/level") && c.body && c.body.level === "off",
  );
  assert.ok(levelPost, "Reset All must keep resetting the profile level");
  for (const k of seededSettingsKeys) {
    assert.equal(globalThis.localStorage.getItem(k), null, k + " must be cleared");
  }
  assert.equal(globalThis.localStorage.getItem("comfymodal.studio.playground.drafts.v1"), "user-drafts");
  assert.equal(globalThis.localStorage.getItem("comfymodal.studio.playground.results.v1"), "user-results");
  section("9. Reset All: GPU-only POST, truthful disclosure, durable data preserved");

  // 9b. H12: Run mode control and V1/V2 engine selector are retired from
  //     modern Settings; no retired-engine vocabulary is advertised.
  installBrowserStubs();
  const fetchG2 = installFetch(
    makeRouter(makeConfig(), { level: "off", effective: "off" }),
  );
  const pageG2 = renderPage();
  await settle(fetchG2.inflight);
  assert.equal(byTestid(pageG2, "settings-run-mode"), null);
  assert.equal(byTestid(pageG2, "settings-run-mode-cloud"), null);
  assert.equal(byTestid(pageG2, "settings-run-mode-local"), null);
  assert.equal(byTestid(pageG2, "settings-execution-engine"), null);
  assert.equal(byTestid(pageG2, "settings-execution-engine-status"), null);
  assert.equal(byTestid(pageG2, "settings-execution-engine-readiness"), null);
  assert.equal(settingsSource.includes("available_execution_modes"), false);
  assert.equal(settingsSource.includes("execution_readiness"), false);
  assert.equal(settingsSource.includes("V1 engine remains available"), false);
  assert.ok(byTestid(pageG2, "settings-gpu"), "GPU selector must remain");
  section("9b. Run mode + engine selector retired; GPU remains; no retired vocabulary");

  // 9c. H12: one-time migration notice renders when the server surfaces it.
  installBrowserStubs();
  const fetchG3 = installFetch(
    makeRouter(
      makeConfig({ engine_migration_notice: "Engine V1 retired; future runs use V2." }),
      { level: "off", effective: "off" },
    ),
  );
  const pageG3 = renderPage();
  await settle(fetchG3.inflight);
  const noticeEl = byTestid(pageG3, "settings-engine-migration-notice");
  assert.ok(noticeEl, "migration notice must render when surfaced");
  assert.match(noticeEl.textContent, /Engine V1 retired; future runs use V2\./);
  section("9c. Engine migration notice surfaced truthfully");

  // 10. Preview/Output controls load server values and still save through
  //     the shared output-preferences module (no Phase-E regression).
  installBrowserStubs();
  const fetchH = installFetch(
    makeRouter(makeConfig(), { level: "off", effective: "off" }),
  );
  const pageH = renderPage();
  await settle(fetchH.inflight);
  assert.equal(byTestid(pageH, "settings-output-format").value, "original");
  assert.equal(byTestid(pageH, "settings-quality").value, "75");
  assert.equal(byTestid(pageH, "settings-webp-lossless-compression").value, "balanced");
  assert.equal(byTestid(pageH, "settings-auto-save-local").checked, false);
  assert.equal(byTestid(pageH, "settings-save-folder").value, "output/modal");
  assert.equal(byTestid(pageH, "settings-save-metadata-sidecar").checked, true);
  assert.equal(byTestid(pageH, "settings-preview-default").value, "off");
  assert.equal(byTestid(pageH, "settings-preview-codec").value, "webp");
  assert.equal(byTestid(pageH, "settings-preview-quality").value, "70");
  const formatH = byTestid(pageH, "settings-output-format");
  formatH.value = "jpeg";
  formatH.dispatch("change");
  await settle(fetchH.inflight);
  const formatPost = fetchH.calls.find(
    (c) => c.method === "POST" && c.url.endsWith("/config") && c.body && c.body.output_format === "jpeg",
  );
  assert.ok(formatPost, "format change must POST merged output preferences");
  assert.equal(globalThis.localStorage.getItem("comfymodal_output_format"), "jpeg");
  const previewQualityH = byTestid(pageH, "settings-preview-quality");
  previewQualityH.value = "80";
  previewQualityH.dispatch("change");
  await settle(fetchH.inflight);
  const previewPost = fetchH.calls.find(
    (c) => c.method === "POST" && c.url.endsWith("/config") && c.body && c.body.preview_quality === 80,
  );
  assert.ok(previewPost, "preview quality change must POST");
  assert.equal(globalThis.localStorage.getItem("comfymodal_preview_quality"), "80");
  section("10. Preview/Output controls unaffected: server-first load, revert-safe save");

  // 11. Experiments section stays informational with no reset path.
  installBrowserStubs();
  const fetchI = installFetch(
    makeRouter(makeConfig(), { level: "off", effective: "off" }),
  );
  const pageI = renderPage();
  await settle(fetchI.inflight);
  const sectionsI = pageI.querySelectorAll(".comfymodal-studio-settings-section");
  const experiments = sectionsI.find((s) => s.dataset.section === "experiments");
  assert.ok(experiments, "Experiments section must exist");
  assert.equal(experiments.querySelectorAll("select").length, 0);
  assert.equal(byTestid(pageI, "settings-reset-experiments"), null);
  const infoText = JSON.stringify(experiments.textContent);
  // I7 frozen wording (I1 §3.6): user-facing copy, frozen value 6 preserved.
  assert.ok(infoText.includes("Experiments run up to 6 cells concurrently"));
  assert.ok(infoText.includes("Per-experiment overrides are not available"));
  section("11. Experiments fixed-concurrency informational UI intact");

  // 12. Search remains functional after stale-key cleanup.
  installBrowserStubs();
  const fetchJ = installFetch(
    makeRouter(makeConfig(), { level: "off", effective: "off" }),
  );
  const pageJ = renderPage();
  await settle(fetchJ.inflight);
  const searchJ = byTestid(pageJ, "settings-search");
  const resultsJ = byTestid(pageJ, "settings-search-results");
  searchJ.value = "gpu";
  searchJ.dispatch("input");
  assert.match(resultsJ.textContent, /^\d+ matching settings?$/);
  searchJ.value = "zzz-no-such-setting";
  searchJ.dispatch("input");
  assert.equal(resultsJ.textContent, "No settings match your search");
  searchJ.value = "";
  searchJ.dispatch("input");
  assert.equal(resultsJ.style.display, "none");
  section("12. Settings search functional; hidden/deleted controls absent");

  // ── Phase I7: page h2, unique reset names, frozen copy ──────────────────

  // 13. Truthful page h2 under the shell h1 (visually hidden, clip pattern).
  installBrowserStubs();
  const fetchK = installFetch(
    makeRouter(makeConfig(), { level: "off", effective: "off" }),
  );
  const pageK = renderPage();
  await settle(fetchK.inflight);
  const pageTitle = byTestid(pageK, "settings-page-title");
  assert.ok(pageTitle, "Settings page h2 must exist");
  assert.equal(pageTitle.tagName, "H2");
  assert.equal(pageTitle.textContent, "Settings");
  const titleCss = pageTitle.style.cssText || "";
  assert.ok(titleCss.includes("clip:rect(0 0 0 0)"), "h2 uses the clip offscreen pattern");
  assert.equal(titleCss.includes("display:none"), false, "h2 is never display:none");
  assert.equal(titleCss.includes("visibility:hidden"), false, "h2 is never visibility:hidden");
  // Exactly one h2 on the page; section headings remain h3.
  const headingWalk = [];
  (function walk(node) {
    if (!Array.isArray(node.children)) return;
    for (const c of node.children) {
      if (/^H[1-6]$/.test(c.tagName)) headingWalk.push(c.tagName);
      walk(c);
    }
  })(pageK);
  assert.equal(headingWalk.filter((t) => t === "H2").length, 1, "exactly one page-level h2");
  assert.ok(headingWalk.includes("H3"), "section headings stay h3");
  section("13. Settings page h2 truthful and visually hidden; hierarchy unchanged");

  // 14. Every section reset control carries a unique, section-identifying
  //     accessible name; the duplicated bare "Reset section" name is gone.
  installBrowserStubs();
  const fetchL = installFetch(
    makeRouter(makeConfig(), { level: "off", effective: "off" }),
  );
  const pageL = renderPage();
  await settle(fetchL.inflight);
  const resetControls = [];
  (function collectResets(node) {
    if (!Array.isArray(node.children)) return;
    for (const c of node.children) {
      if (
        c.tagName === "BUTTON" &&
        typeof c.dataset.testid === "string" &&
        c.dataset.testid.startsWith("settings-reset-")
      ) {
        resetControls.push(c);
      }
      collectResets(c);
    }
  })(pageL);
  // Section resets (Generation/Outputs/History/Interface/Advanced) plus the
  // Interface panel-layout control and the footer Reset-all.
  const names = resetControls.map((b) => b.getAttribute("aria-label") || b.textContent);
  const expectedSectionNames = [
    "Reset Generation section",
    "Reset Outputs section",
    "Reset History section",
    "Reset Interface section",
    "Reset Advanced section",
  ];
  for (const expected of expectedSectionNames) {
    assert.ok(names.includes(expected), "missing accessible name: " + expected);
  }
  assert.equal(
    new Set(names).size,
    names.length,
    "reset controls must have pairwise-unique accessible names, got: " + names.join(" | "),
  );
  for (const name of names) {
    assert.notEqual(name.trim(), "Reset section", "bare duplicate name must be gone");
  }
  // Behavior untouched: the Generation reset still routes through its testid.
  assert.ok(byTestid(pageL, "settings-reset-generation"), "generation reset control intact");
  section("14. Section resets expose unique per-section accessible names");

  // 15. Frozen wording rows render verbatim in the mounted page.
  const generalL = pageL.querySelectorAll(".comfymodal-studio-settings-section")
    .find((s) => s.dataset.section === "general");
  assert.ok(generalL);
  assert.ok(
    generalL.textContent.includes("Playground / History / Workflows / Backend / Settings."),
    "navigation row lists all five pages truthfully",
  );
  assert.equal(generalL.textContent.includes("Backend remains available"), false);
  const historyL = pageL.querySelectorAll(".comfymodal-studio-settings-section")
    .find((s) => s.dataset.section === "history");
  assert.ok(
    historyL.textContent.includes("Run history is stored locally and is kept until you delete it."),
    "run-history retention copy is user-facing",
  );
  section("15. Frozen navigation + run-history copy rendered verbatim");
} finally {
  globalThis.setTimeout = realSetTimeout;
}

console.log("PASS: studio phase F4A settings authority unit tests");
