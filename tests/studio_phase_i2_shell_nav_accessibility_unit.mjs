// Phase I2 — Shell navigation accessibility & responsive safety unit tests.
//
// Deterministic Node unit tests: no browser, no network, no GPU, no live
// generation. Uses the house DOM/fetch stub pattern (cf.
// studio_phase_f8_gpu_reset_unit.mjs) plus a module-resolution hook that
// redirects the ComfyUI host modules (`../../scripts/app.js` /
// `../../scripts/api.js`) to inert data: stubs so the real studio-shell.js
// can be mounted behaviorally outside ComfyUI.
//
// Covered I2 contracts (PHASE_I2 report §12):
//   1. shell topnav is a semantic <nav>
//   2. nav carries accessible label "Studio pages"
//   3. page selectors remain native <button> elements
//   4. active page gets aria-current="page"; inactive buttons never retain it
//   5. programmatic/alias page changes drive the same single page state
//   6. exactly five canonical page ids remain
//   7. routing isolated to studio-routing.js + shell lane (re-pointed for
//      I9; page modules stay routing-free, no router library)
//   8. shell root heading is h1 "Modal GPU"
//   9. dead _trapTab helper stays deleted
//  10. responsive nav CSS includes the frozen horizontal-overflow safety
//  11. no hamburger / second navigation architecture was added

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { registerHooks } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const WEB = path.join(ROOT, "web");
const readWeb = (name) => fs.readFileSync(path.join(WEB, name), "utf8");

function section(name) {
  console.log("PASS: " + name);
}

// ── Host-module resolution hook (ComfyUI app/api stubs) ───────────────────

const APP_STUB_URL =
  "data:text/javascript," +
  encodeURIComponent(
    'export const app={graph:null,canvas:null,registerExtension(){},unregisterExtension(){},handlePrompt(){},ui:{settings:{get(){return undefined},set(){},addSetting(){}}},extensionManager:{}};' +
      'if(typeof window!=="undefined"){window.app=app;}'
  );
const API_STUB_URL =
  "data:text/javascript," +
  encodeURIComponent(
    'export const api={addEventListener(){},removeEventListener(){},dispatchEvent(){return true},api_url(){return "/"}};export default api;'
  );

registerHooks({
  resolve(specifier, context, nextResolve) {
    if (/\/scripts\/app\.js$/.test(specifier)) {
      return { url: APP_STUB_URL, shortCircuit: true };
    }
    if (/\/scripts\/api\.js$/.test(specifier)) {
      return { url: API_STUB_URL, shortCircuit: true };
    }
    return nextResolve(specifier, context);
  },
});

// ── DOM / browser-environment stubs (house pattern) ───────────────────────

function matchesClass(node, cls) {
  return (" " + (node.className || "") + " ").indexOf(" " + cls + " ") !== -1;
}

function matchesSimple(node, selector) {
  if (/^[a-zA-Z][a-zA-Z0-9-]*$/.test(selector)) {
    return node.tagName === selector.toUpperCase();
  }
  if (selector.charAt(0) === ".") {
    return node.classList && node.classList.contains(selector.slice(1));
  }
  const attr = selector.match(/^\[([^=\]]+)(?:="([^"]*)")?\]$/);
  if (attr) {
    const name = attr[1];
    const expected = attr[2];
    const actual =
      name === "data-testid" ? node.dataset.testid : node.attributes[name];
    if (expected === undefined) return actual !== undefined && actual != null;
    return actual === expected;
  }
  return false;
}

function matchesSelector(node, selector) {
  // Support compound tag[attr="v"] selectors used by this unit.
  const compound = selector.match(/^([a-zA-Z][a-zA-Z0-9-]*)((?:\[.*\])+)$/);
  if (compound) {
    if (node.tagName !== compound[1].toUpperCase()) return false;
    const attrs = compound[2].match(/\[[^\]]*\]/g) || [];
    return attrs.every((a) => matchesSimple(node, a));
  }
  return matchesSimple(node, selector);
}

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
    insertBefore(child, ref) {
      child.parentNode = this;
      const i = ref ? this.children.indexOf(ref) : -1;
      if (i === -1) this.children.push(child);
      else this.children.splice(i, 0, child);
      return child;
    },
    contains(other) {
      let cur = other;
      while (cur) {
        if (cur === this) return true;
        cur = cur.parentNode;
      }
      return false;
    },
    get firstChild() {
      return this.children.length ? this.children[0] : null;
    },
    addEventListener(type, fn) {
      (this.listeners[type] = this.listeners[type] || []).push(fn);
    },
    removeEventListener(type, fn) {
      const arr = this.listeners[type];
      if (arr) {
        const i = arr.indexOf(fn);
        if (i !== -1) arr.splice(i, 1);
      }
    },
    dispatch(type) {
      for (const fn of (this.listeners[type] || []).slice()) {
        fn({ type, target: this, preventDefault() {}, key: "" });
      }
    },
    focus() {
      if (globalThis.document) globalThis.document.activeElement = this;
    },
    blur() {},
    scrollIntoView() {},
    setAttribute(name, v) {
      this.attributes[name] = String(v);
      if (name.startsWith("data-")) {
        // Mirror data-* attributes into dataset like a real DOM does.
        const key = name
          .slice(5)
          .replace(/-([a-z])/g, (_, c) => c.toUpperCase());
        this.dataset[key] = String(v);
      }
    },
    getAttribute(name) {
      return name in this.attributes ? this.attributes[name] : null;
    },
    removeAttribute(name) {
      delete this.attributes[name];
    },
    closest(selector) {
      let cur = this;
      while (cur) {
        if (matchesSelector(cur, selector)) return cur;
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
        for (const child of node.children || []) {
          if (matchesSelector(child, selector)) out.push(child);
          visit(child);
        }
      };
      visit(this);
      return out;
    },
    getBoundingClientRect() {
      return { top: 0, left: 0, right: 100, bottom: 100, width: 100, height: 100 };
    },
    get scrollTop() {
      return this._scrollTop || 0;
    },
    set scrollTop(v) {
      this._scrollTop = v;
    },
  };
  node.classList = {
    add(c) {
      if (!matchesClass(node, c))
        node.className = (node.className ? node.className + " " : "") + c;
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
      return node.children
        .map((c) => (c.textContent == null ? "" : c.textContent))
        .join("");
    },
    set(v) {
      ownText = String(v);
    },
  });
  return node;
}

function installBrowserStubs() {
  globalThis.document = {
    createElement: makeNode,
    createTextNode: (t) => ({ nodeType: 3, textContent: String(t), parentNode: null }),
    querySelector: () => null,
    querySelectorAll: () => [],
    addEventListener() {},
    removeEventListener() {},
    body: makeNode("body"),
    activeElement: null,
  };
  globalThis.window = {
    addEventListener() {},
    removeEventListener() {},
    location: { hash: "" },
  };
  globalThis.localStorage = {
    getItem: () => null,
    setItem() {},
    removeItem() {},
    clear() {},
  };
  globalThis.CustomEvent = class CustomEvent {
    constructor(type, init) {
      this.type = type;
      this.detail = init && init.detail;
    }
  };
  globalThis.requestAnimationFrame = (fn) => setTimeout(fn, 0);
}

function installFetch() {
  globalThis.fetch = async (url) => {
    const u = String(url);
    if (u.includes("/config")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          execution_mode: "v2",
          gpu: "g",
          default_gpu: "g",
          available_gpus: [],
          output_format: "original",
          quality: 75,
          webp_lossless_compression: "balanced",
          auto_save_local: false,
          save_folder: "",
          preview_method: "default",
          preview_codec: "jpeg",
          preview_quality: 90,
        }),
      };
    }
    if (u.includes("/presets")) {
      return { ok: true, status: 200, json: async () => ({ presets: [] }) };
    }
    if (u.includes("/feed")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({ items: [], records: [], next_cursor: null }),
      };
    }
    return {
      ok: true,
      status: 200,
      json: async () => ({
        items: [],
        records: [],
        results: [],
        workflows: [],
        versions: [],
        mappings: [],
        models: [],
        snapshots: [],
        workspaces: [],
        presets: [],
        next_cursor: null,
      }),
    };
  };
}

process.on("unhandledRejection", (r) => {
  console.log("UNHANDLED REJECTION:", r && (r.stack || r.message || String(r)));
  process.exit(1);
});

installBrowserStubs();
installFetch();

// ── Mount the real shell ──────────────────────────────────────────────────

const CANONICAL_PAGES = ["playground", "history", "workflows", "backend", "settings"];
const CANONICAL_LABELS = ["Playground", "History", "Workflows", "Backend", "Settings"];

const { mountStudioShell } = await import(
  pathToFileURL(path.join(WEB, "studio-shell.js"))
);

const rootEl = makeNode("div");
let contextSetPageCalls = 0;
const shellApi = mountStudioShell(rootEl, {
  apiBase: "/comfymodal",
  setPage: () => {
    contextSetPageCalls++;
  },
});

const nav = rootEl.querySelector(".comfymodal-studio-topnav");
assert.ok(nav, "topnav element must exist inside the mounted shell");

function navButtons() {
  return nav.querySelectorAll("button");
}
function currentPageButtons() {
  return nav.querySelectorAll('button[aria-current="page"]');
}

// 1 + 2 — semantic nav, accessible label, native buttons
assert.equal(nav.tagName, "NAV", "topnav must be a semantic <nav> element (I1 §3.1)");
section("shell topnav is a semantic <nav>");

assert.equal(
  nav.getAttribute("aria-label"),
  "Studio pages",
  'nav must expose aria-label "Studio pages"'
);
section("nav has accessible label \"Studio pages\"");

const buttons = navButtons();
assert.equal(buttons.length, 5, "exactly five page selector buttons");
for (const btn of buttons) {
  assert.equal(btn.tagName, "BUTTON", "page selectors must remain native buttons");
  assert.equal(btn.getAttribute("role"), null, "no role override on native buttons");
  assert.equal(btn.getAttribute("tabindex"), null, "native tab traversal preserved (no roving tabindex)");
}
section("page selectors remain native buttons (no role/tabindex overrides)");

// 3 + 6 — canonical pages, initial aria-current on Playground
assert.deepEqual(
  buttons.map((b) => b.getAttribute("data-page")),
  CANONICAL_PAGES,
  "canonical page ids and order must be Playground History Workflows Backend Settings"
);
assert.deepEqual(
  buttons.map((b) => b.textContent),
  CANONICAL_LABELS,
  "nav labels must be the five canonical page names"
);

let current = currentPageButtons();
assert.equal(current.length, 1, "exactly one aria-current at initial render");
assert.equal(
  current[0].getAttribute("data-page"),
  "playground",
  "initial current page must be Playground"
);
assert.ok(
  current[0].classList.contains("active"),
  ".active visual state follows the same page state"
);
section("active page exposes aria-current=\"page\" (initial Playground)");

// 4 — page change moves aria-current; inactive buttons lose it entirely
shellApi.setPage("history");
current = currentPageButtons();
assert.equal(current.length, 1, "exactly one aria-current after page change");
assert.equal(current[0].getAttribute("data-page"), "history");
for (const btn of navButtons()) {
  if (btn.getAttribute("data-page") !== "history") {
    assert.equal(
      btn.getAttribute("aria-current"),
      null,
      "inactive buttons must not retain a stale aria-current attribute"
    );
    assert.equal(btn.classList.contains("active"), false, "stale .active must clear too");
  }
}
section("setPage moves aria-current synchronously; inactive buttons lose it");

// 5 — programmatic/alias path drives the SAME state (modal-testing.js alias
// navigation invokes studioApi.setPage — the exported shell action).
shellApi.setPage("backend");
current = currentPageButtons();
assert.equal(current.length, 1);
assert.equal(current[0].getAttribute("data-page"), "backend");
assert.ok(current[0].classList.contains("active"));
section("programmatic/alias page changes use the same shell page-state path");

// 7 — routing ownership (re-pointed for I9, documented drift): the I2-era
// blanket ban on hash APIs in the shell lane files expired when I9 landed
// the frozen hash-routing contract. The truthful pins now are: routing
// lives ONLY in web/studio-routing.js + its two shell-lane consumers
// (studio-shell.js, modal-testing.js); every page module stays routing-free;
// and no router library exists anywhere in web/.
const shellSource = readWeb("studio-shell.js");
const testingSource = readWeb("modal-testing.js");
const ROUTING_OWNERS = ["studio-shell.js", "modal-testing.js", "studio-routing.js"];
const PAGE_FILES = [
  "studio-playground.js",
  "studio-history-v2.js",
  "history-v2-view-state.js",
  "studio-workflows.js",
  "studio-backend.js",
  "studio-settings.js",
];
for (const banned of ["pushState", "replaceState", "hashchange", "popstate", "location.hash"]) {
  for (const file of PAGE_FILES) {
    assert.equal(
      readWeb(file).includes(banned),
      false,
      `${file} must not contain ${banned} (routing is owned by the shell lane)`
    );
  }
}
const routingSource = readWeb("studio-routing.js");
for (const required of [
  "export function parseStudioHash",
  "export function serializeStudioHash",
  "export function routeHistoryAction",
]) {
  assert.ok(routingSource.includes(required), `studio-routing.js must export ${required}`);
}
const webDir = path.join(ROOT, "web");
for (const entry of fs.readdirSync(webDir)) {
  if (!entry.endsWith(".js")) continue;
  const src = fs.readFileSync(path.join(webDir, entry), "utf8");
  for (const lib of ['from "react-router', "from 'react-router", 'from "history"', "from 'history'"]) {
    assert.equal(src.includes(lib), false, `${entry} must not import a router library`);
  }
}
section("routing isolated to studio-routing.js + shell lane; page modules stay routing-free");

// 8 — shell root heading is the single h1 "Modal GPU"
const buildShellStart = testingSource.indexOf("function buildShell");
assert.notEqual(buildShellStart, -1);
const buildShellBlock = testingSource.slice(buildShellStart, buildShellStart + 900);
assert.ok(
  /el\("h1",\s*\{\s*id:\s*"comfymodal-studio-heading",\s*text:\s*"Modal GPU"/.test(
    buildShellBlock
  ),
  'buildShell header must be h1 "Modal GPU" with the frozen heading id'
);
assert.equal(
  /\bel\("h1"/.test(testingSource.replace(buildShellBlock, "")),
  false,
  "modal-testing.js must contain exactly one h1 construction (the shell root)"
);
section("shell root heading is h1 \"Modal GPU\"");

// 9 — dead _trapTab stays deleted (containment is inert-based)
for (const banned of ["_trapTab", "focusTrap", "tabTrap"]) {
  assert.equal(
    testingSource.includes(banned),
    false,
    `${banned} must stay deleted from modal-testing.js (I2)`
  );
}
assert.ok(
  testingSource.includes("_inertBackground(true)"),
  "live containment implementation (_inertBackground) must remain"
);
section("dead _trapTab helper is removed; inert containment intact");

// 10 — responsive horizontal-overflow safety valve present in nav CSS
const stylesSource = readWeb("studio-styles.js");
const topnavRuleStart = stylesSource.indexOf(".comfymodal-studio-topnav {");
assert.notEqual(topnavRuleStart, -1, "topnav CSS rule must exist");
const topnavRule = stylesSource.slice(topnavRuleStart, topnavRuleStart + 400);
assert.ok(
  /overflow-x:\s*auto/.test(topnavRule),
  "nav container CSS must keep the overflow-x:auto safety valve (I1 §3.2)"
);
assert.ok(
  !/flex-wrap/.test(topnavRule),
  "nav must stay a single row (no wrapping fallback)"
);
section("responsive nav CSS includes the frozen horizontal-overflow safety");

// 11 — no hamburger / second navigation architecture
const navCreations = [];
for (const [name, src] of [
  ["studio-shell.js", shellSource],
  ["modal-testing.js", testingSource],
]) {
  const matches = src.match(/\bel\(\s*["']nav["']/g) || [];
  navCreations.push(...matches.map(() => name));
}
assert.deepEqual(navCreations, ["studio-shell.js"], "exactly one nav element, built by the shell");
assert.equal(shellSource.toLowerCase().includes("hamburger"), false, "no hamburger UI");
assert.equal(testingSource.toLowerCase().includes("hamburger"), false, "no hamburger UI");
assert.equal(
  (shellSource.match(/comfymodal-studio-topnav/g) || []).filter(
    (occ, i, all) => true
  ).length >= 1,
  true,
  "frozen topnav class retained"
);
section("no hamburger or second navigation architecture added");

// Alias vocabulary regression (§14): the seven frozen redirects still land on
// canonical modern owners through the same setPage authority.
const aliasBlockMatch = testingSource.match(/const ALIAS_PAGE_MAP = \{([\s\S]*?)\};/);
assert.ok(aliasBlockMatch, "ALIAS_PAGE_MAP must remain in modal-testing.js");
const aliasPairs = {};
for (const m of aliasBlockMatch[1].matchAll(/(\w+):\s*"(\w+)"/g)) {
  aliasPairs[m[1]] = m[2];
}
assert.deepEqual(
  aliasPairs,
  {
    playground: "playground",
    dashboard: "backend",
    setup: "playground",
    profiles: "playground",
    results: "history",
    history: "history",
    settings: "settings",
  },
  "seven frozen alias redirects must be unchanged"
);
for (const target of Object.values(aliasPairs)) {
  assert.ok(
    CANONICAL_PAGES.includes(target),
    `alias target ${target} must be a canonical page`
  );
}
section("alias/compat vocabulary unchanged and lands on canonical pages");

// Let deferred render macrotasks settle, then finish green.
await new Promise((resolve) => setTimeout(resolve, 250));
console.log("PASS: phase-i2 shell/nav accessibility unit complete");
