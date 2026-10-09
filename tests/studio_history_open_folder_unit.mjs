// Modal Studio — History toolbar "Open folder" button.
//
// Deterministic Node unit tests: no browser, no network, no OS file manager.
// Uses the same standalone DOM/fetch stubs as
// studio_phase_f8_gpu_reset_unit.mjs (house pattern).
//
// Pins:
//  1. The History V2 toolbar renders an "Open folder" button immediately
//     beside "Clear all" (same toolbar row, adjacent sibling).
//  2. Clicking it POSTs the configured output save folder to
//     {apiBase}/open-folder — the same endpoint Settings → Outputs uses.
//  3. The path is the normalized output save folder: the default when unset,
//     and the user's stored preference (backslashes / trailing slash
//     normalized) when set.

import assert from "node:assert/strict";
import { renderHistoryV2 } from "../web/studio-history-v2.js";

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
      },
      getAttribute(name) {
        return name in this.attributes ? this.attributes[name] : null;
      },
      focus() {},
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
}

// Empty legacy feed probe + first page (the "auto" repository probes and then
// bridges onto /history; an empty page keeps the mount path deterministic).
function installFetch(extraRouter) {
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
      if (extraRouter) {
        const extra = extraRouter(call);
        if (extra) return extra;
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ items: [], total: 0, has_more: false }),
      };
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

function findByClass(root, cls) {
  const out = [];
  const visit = (node) => {
    if (matchesClass(node, cls)) out.push(node);
    for (const child of node.children || []) visit(child);
  };
  visit(root);
  return out;
}

// ── Tests ────────────────────────────────────────────────────────────────

async function mountHistory(saveFolder) {
  installBrowserStubs();
  if (saveFolder != null) {
    globalThis.localStorage.setItem("comfymodal_save_folder", saveFolder);
  }
  const net = installFetch();
  const root = renderHistoryV2(null, { apiBase: "/comfymodal" });
  await settle(net.inflight);
  return { root: root, calls: net.calls };
}

// 1. The button exists beside Clear all in toolbar row 1.
{
  const { root } = await mountHistory(null);
  const buttons = findByClass(root, "comfymodal-studio-history-v2-open-folder");
  assert.equal(buttons.length, 1, "exactly one Open folder button in the toolbar");

  const openBtn = buttons[0];
  assert.equal(openBtn.textContent, "Open folder");
  assert.equal(openBtn.getAttribute("type"), "button");
  assert.equal(openBtn.getAttribute("data-testid"), "history-v2-open-folder");

  // "Beside the clear all button": same parent row, adjacent sibling.
  const clearBtn = findByClass(root, "comfymodal-studio-history-v2-clear-all")[0];
  assert.ok(clearBtn, "Clear all button still rendered");
  assert.equal(openBtn.parentNode, clearBtn.parentNode, "same toolbar row");
  const row = openBtn.parentNode.children;
  assert.equal(row[row.indexOf(openBtn) + 1], clearBtn, "Open folder sits immediately beside Clear all");
  section("1. Open folder button renders beside Clear all in the toolbar row");
}

// 2. Click posts the default output folder to the shared open-folder endpoint.
{
  const { root, calls } = await mountHistory(null);
  const openBtn = findByClass(root, "comfymodal-studio-history-v2-open-folder")[0];
  openBtn.dispatch("click");
  await Promise.resolve();

  const posted = calls.filter((c) => c.url === "/comfymodal/open-folder");
  assert.equal(posted.length, 1, "exactly one open-folder POST");
  assert.equal(posted[0].method, "POST");
  assert.deepEqual(posted[0].body, { path: "output/modal" });
  section("2. Click POSTs the default output folder (output/modal) to /comfymodal/open-folder");
}

// 3. Click honors the stored save_folder preference, normalized.
{
  const { root, calls } = await mountHistory("output\\custom\\");
  const openBtn = findByClass(root, "comfymodal-studio-history-v2-open-folder")[0];
  openBtn.dispatch("click");
  await Promise.resolve();

  const posted = calls.filter((c) => c.url === "/comfymodal/open-folder");
  assert.equal(posted.length, 1, "exactly one open-folder POST");
  assert.deepEqual(posted[0].body, { path: "output/custom" });
  section("3. Click posts the stored save folder, normalized (backslash + trailing slash)");
}

console.log("ALL PASS: history toolbar open-folder button");
