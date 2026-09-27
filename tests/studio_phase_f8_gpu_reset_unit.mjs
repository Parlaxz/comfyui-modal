// F8 GPU Authority Consolidation — Reset semantics + display authority pins.
//
// Deterministic Node unit tests: no browser, no network, no GPU, no live
// services.  Uses the same standalone DOM/fetch stubs as
// studio_phase_f4_settings_authority_unit.mjs (house pattern).
//
// Pins:
//  1. Reset All POSTs the canonical default GPU to /config together with the
//     engine reset — the server-persisted GPU is reset, not just the browser
//     cache.
//  2. The Generation-section reset behaves identically (section reset and
//     Reset All are consistent).
//  3. The Reset All confirmation truthfully discloses the GPU reset.
//  4. Durable user-data namespaces stay outside the reset POSTs.
//  5. The legacy panel keeps its read-only server-first initialization:
//     loadGpuConfig() issues GET only, and exactly ONE gpu POST site exists
//     (the explicit-change path) — panel open stays zero-POST.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";
import { renderSettings } from "../web/studio-settings.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const WEB = path.join(ROOT, "web");
const readWeb = (name) => fs.readFileSync(path.join(WEB, name), "utf8");

const settingsSource = readWeb("studio-settings.js");
const modalSettingsSource = readWeb("modal-settings.js");

function section(name) {
  console.log("PASS: " + name);
}

// ── DOM / browser-environment stubs ───────────────────────────────────────

function matchesClass(node, cls) {
  return (" " + (node.className || "") + " ").indexOf(" " + cls + " ") !== -1;
}

function matchesSelector(node, selector) {
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
      dispatch(type) {
        for (const fn of (this.listeners[type] || []).slice()) {
          fn({ type: type, target: this, preventDefault() {} });
        }
      },
      setAttribute(name, v) {
        this.attributes[name] = String(v);
        if (name === "data-testid") this.dataset.testid = String(v);
        if (name === "data-search") this.dataset.search = String(v);
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

let _confirmMessage = null;

function installBrowserStubs() {
  globalThis.document = createDocumentStub();
  const values = new Map();
  globalThis.localStorage = {
    getItem: (key) => (values.has(key) ? values.get(key) : null),
    setItem: (key, value) => values.set(String(key), String(value)),
    removeItem: (key) => values.delete(key),
    clear: () => values.clear(),
  };
  globalThis.window = {
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent() {
      return true;
    },
  };
  globalThis.CustomEvent = class CustomEvent {
    constructor(type, init) {
      this.type = type;
      this.detail = init && init.detail;
    }
  };
  globalThis.confirm = (message) => {
    _confirmMessage = message;
    return true;
  };
}

function currentConfirmMessage() {
  return _confirmMessage;
}

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
      const payload = router(call) || {};
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
      gpu: "gpu-a",
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

// ── Tests ─────────────────────────────────────────────────────────────────

const realSetTimeout = globalThis.setTimeout;
globalThis.setTimeout = () => 0;

try {
  // 1. Reset All resets the SERVER-persisted GPU to the canonical default.
  //    H12: the POST is GPU-only — no engine value is sent (V2 is the only
  //    engine; forcing it would be a meaningless write).
  installBrowserStubs();
  globalThis.localStorage.setItem("comfymodal_gpu", "gpu-b");
  globalThis.localStorage.setItem("comfymodal.studio.playground.drafts.v1", "user-drafts");
  const configA = makeConfig({ gpu: "gpu-b" });
  const fetchA = installFetch(makeRouter(configA, { level: "off", effective: "off" }));
  const pageA = renderPage();
  await settle(fetchA.inflight);
  byTestid(pageA, "settings-reset-all").dispatch("click");
  await settle(fetchA.inflight);
  const resetAllPost = fetchA.calls.find(
    (c) => c.method === "POST" && c.url.endsWith("/config"),
  );
  assert.ok(resetAllPost, "Reset All must POST /config");
  assert.equal(
    resetAllPost.body.gpu,
    configA.default_gpu,
    "Reset All must POST the canonical default GPU so the server-persisted selection resets",
  );
  assert.equal(
    "execution_mode" in resetAllPost.body,
    false,
    "Reset All must NOT POST an execution_mode (engine forcing retired in H12)",
  );
  section("1. Reset All POSTs default GPU only (no engine reset) to /config");

  // 2. Confirmation copy truthfully discloses the GPU reset (and no longer
  //    claims an engine reset).
  assert.ok(
    currentConfirmMessage().includes("GPU selection is reset to the default"),
    "Reset All confirm must disclose the server GPU reset",
  );
  assert.equal(
    currentConfirmMessage().includes("execution engine"),
    false,
    "Reset All confirm must not claim an engine reset",
  );
  assert.ok(
    settingsSource.includes("GPU selection resets to the default"),
    "footer note must disclose the GPU reset",
  );
  section("2. Reset All disclosure mentions the GPU reset truthfully");

  // 3. Generation-section reset is consistent with Reset All.
  installBrowserStubs();
  const configB = makeConfig({ gpu: "gpu-b" });
  const fetchB = installFetch(makeRouter(configB, { level: "off", effective: "off" }));
  const pageB = renderPage();
  await settle(fetchB.inflight);
  byTestid(pageB, "settings-reset-generation").dispatch("click");
  await settle(fetchB.inflight);
  const generationPost = fetchB.calls.find(
    (c) => c.method === "POST" && c.url.endsWith("/config") && c.body && c.body.gpu,
  );
  assert.ok(generationPost, "Generation reset must POST /config with the default GPU");
  assert.equal(
    generationPost.body.gpu,
    configB.default_gpu,
    "Generation reset must also reset the persisted server GPU",
  );
  assert.equal(
    "execution_mode" in generationPost.body,
    false,
    "Generation reset must NOT POST an execution_mode",
  );
  section("3. Generation-section reset matches Reset All GPU semantics");

  // 4. Durable user data is never part of any reset request.
  installBrowserStubs();
  globalThis.localStorage.setItem("comfymodal.studio.playground.results.v1", "user-results");
  const fetchC = installFetch(makeRouter(makeConfig(), { level: "off", effective: "off" }));
  const pageC = renderPage();
  await settle(fetchC.inflight);
  byTestid(pageC, "settings-reset-all").dispatch("click");
  await settle(fetchC.inflight);
  assert.equal(globalThis.localStorage.getItem("comfymodal.studio.playground.results.v1"), "user-results");
  section("4. Durable namespaces survive Reset All");

  // 5. Legacy settings module (H18 Wave G): only the read-only GPU init
  //    loader remains; every explicit-change POST site is deleted.
  assert.ok(
    modalSettingsSource.includes("async function loadGpuConfig()"),
    "legacy GPU init loader must exist",
  );
  const loadGpuBody = modalSettingsSource.slice(
    modalSettingsSource.indexOf("async function loadGpuConfig()"),
  );
  assert.equal(
    loadGpuBody.includes('"POST"'),
    false,
    "GPU init sync must remain a zero-POST GET",
  );
  const gpuPostSites = modalSettingsSource.split("JSON.stringify({ gpu })").length - 1;
  assert.equal(
    gpuPostSites,
    0,
    "no explicit-change GPU POST site may remain in modal-settings.js (Wave G)",
  );
  assert.equal(
    modalSettingsSource.includes("_comfyModalGpu"),
    false,
    "dead window._comfyModalGpu global must stay removed",
  );
  section("5. Legacy module: zero-POST read-only GPU init preserved; no POST sites remain");

  // 6. Modern dropdown still displays the server value after a reset round
  //    trip (display authority unchanged by F8).
  installBrowserStubs();
  const fetchD = installFetch(makeRouter(makeConfig({ gpu: "gpu-a" }), { level: "off", effective: "off" }));
  const pageD = renderPage();
  await settle(fetchD.inflight);
  assert.equal(byTestid(pageD, "settings-gpu").value, "gpu-a");
  section("6. GPU dropdown still displays acknowledged server value");
} finally {
  globalThis.setTimeout = realSetTimeout;
}
console.log("ALL F8 GPU RESET UNIT SECTIONS PASSED");
