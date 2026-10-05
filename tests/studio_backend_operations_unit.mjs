// Modal Studio H6 — Backend Operational Re-home unit tests.
//
// Deterministic Node unit tests: no browser, no network, no GPU, no live
// generation, no deploys. A minimal DOM stub supports the element shapes the
// Backend operational sections use; fetch is an in-memory router shim and
// setTimeout is a manual queue so polling loops never spin.
//
// Covered contracts (H6 §24):
//   WORKSPACE  1–8   list / active identity / exact activate request /
//                    activation-failure keeps prior server truth / exact
//                    add+edit contract / exact swap contract / export-import
//                    explicit-only / no secret material rendered
//   DEPLOY     9–14  status render / explicit deploy / explicit redeploy /
//                    double-click dedupe / no deploy on mount / bounded failure
//   AUTH       15–18 configured state / saved credential never echoed /
//                    exact submit route / failure leaks nothing
//   OWNERSHIP  19–22 no provider selector / no model-library install
//                    duplication / Backend Presets remain distinct / legacy
//                    panel untouched
//   WARMUP     23    retired warmup controls stay absent
//   OVERVIEW   24    read-only operational truth rows
//   I7         25–26 workspaces loading primitive / source pins for the I7
//                    polish lane (loading migration, dead-wrapper deletion,
//                    page h2, tab aria-current, chip geometry)

import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const ROOT = path.join(import.meta.dirname, "..");
const WEB = path.join(ROOT, "web");
const readWeb = (name) => fs.readFileSync(path.join(WEB, name), "utf8");

const backendSource = readWeb("studio-backend.js");
const workspacesSource = readWeb("studio-backend-workspaces.js");
const deploymentSource = readWeb("studio-backend-deployment.js");
const credentialsSource = readWeb("studio-backend-credentials.js");
const runtimeSource = readWeb("studio-backend-runtime.js");
const legacySettingsSource = readWeb("modal-settings.js");

function section(name) {
  console.log("PASS: " + name);
}

// ── Browser environment stubs ─────────────────────────────────────────────

function makeStyle() {
  const style = { cssText: "" };
  return new Proxy(style, {
    get(target, prop) {
      if (prop === "cssText") return target.cssText;
      if (prop in target) return target[prop];
      // Parse simple declarations out of cssText on demand.
      const m = target.cssText.match(new RegExp(String(prop) + "\\s*:\\s*([^;]+)", "i"));
      return m ? m[1].trim() : "";
    },
    set(target, prop, value) {
      if (prop === "cssText") {
        target.cssText = String(value);
        return true;
      }
      target[prop] = value;
      return true;
    },
  });
}

function makeNode(tag) {
  let ownText = "";
  const node = {
    tagName: String(tag || "div").toUpperCase(),
    children: [],
    parentNode: null,
    attributes: {},
    dataset: {},
    style: makeStyle(),
    listeners: {},
    className: "",
    value: "",
    disabled: false,
    checked: false,
    type: "",
    placeholder: "",
    appendChild(child) {
      child.parentNode = this;
      this.children.push(child);
      return child;
    },
    insertBefore(child, ref) {
      const i = ref ? this.children.indexOf(ref) : -1;
      child.parentNode = this;
      if (i === -1) this.children.push(child);
      else this.children.splice(i, 0, child);
      return child;
    },
    removeChild(child) {
      const i = this.children.indexOf(child);
      if (i !== -1) this.children.splice(i, 1);
      child.parentNode = null;
      return child;
    },
    remove() {
      if (this.parentNode) this.parentNode.removeChild(this);
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
        fn({ type, target: this, preventDefault() {}, stopPropagation() {} });
      }
    },
    focus() {},
    setAttribute(name, v) {
      this.attributes[name] = String(v);
      if (name === "data-testid") this.dataset.testid = String(v);
      if (name.startsWith("data-")) {
        const key = name.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase());
        this.dataset[key] = String(v);
      }
      if (name === "value") this.value = String(v);
      if (name === "disabled") this.disabled = true;
      if (name === "checked") this.checked = true;
      if (name === "type") this.type = String(v);
      if (name === "placeholder") this.placeholder = String(v);
    },
    removeAttribute(name) {
      delete this.attributes[name];
      if (name === "disabled") this.disabled = false;
      if (name === "checked") this.checked = false;
    },
    getAttribute(name) {
      return name in this.attributes ? this.attributes[name] : null;
    },
    querySelector(sel) {
      return this.querySelectorAll(sel)[0] || null;
    },
    querySelectorAll(selector) {
      const out = [];
      const visit = (node) => {
        for (const child of node.children) {
          if (!child.dataset) continue; // text nodes
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
      node.children.length = 0;
    },
  });
  return node;
}

function matchesClass(node, cls) {
  return (" " + (node.className || "") + " ").indexOf(" " + cls + " ") !== -1;
}

function matchesSelector(node, selector) {
  if (selector.charAt(0) === ".") return matchesClass(node, selector.slice(1));
  if (/^[a-zA-Z][a-zA-Z0-9]*$/.test(selector)) return node.tagName === selector.toUpperCase();
  const attr = selector.match(/^\[([^=\]]+)(?:="([^"]*)")?\]$/);
  if (!attr) return false;
  const name = attr[1];
  const expected = attr[2];
  const actual = name === "data-testid"
    ? node.dataset.testid
    : node.attributes[name];
  if (expected === undefined) return actual !== undefined && actual != null;
  return actual === expected;
}

function installBrowserStubs() {
  globalThis.document = {
    createElement(tag) { return makeNode(tag); },
    createTextNode(text) { return { nodeType: 3, textContent: String(text), parentNode: null }; },
    querySelector() { return null; },
    body: makeNode("body"),
  };
}

// Manual timer queue: callbacks are recorded, never auto-run.
function installManualTimers() {
  const queue = [];
  globalThis.setTimeout = (fn, _ms) => {
    queue.push(fn);
    return queue.length;
  };
  globalThis.clearTimeout = (id) => {
    queue[id - 1] = null;
  };
  return {
    flushAll: async () => {
      for (let round = 0; round < 25; round++) {
        const pending = queue.splice(0, queue.length);
        if (!pending.length) break;
        for (const fn of pending) {
          if (typeof fn === "function") await fn();
        }
        await new Promise((r) => setImmediate(r));
      }
    },
    pendingCount: () => queue.filter(Boolean).length,
  };
}

// ── Fetch shim ────────────────────────────────────────────────────────────

function installFetch(router) {
  const calls = [];
  const inflight = { count: 0 };
  globalThis.fetch = async (url, options) => {
    inflight.count++;
    try {
      const method = ((options && options.method) || "GET").toUpperCase();
      let body = null;
      if (options && typeof options.body === "string") {
        try { body = JSON.parse(options.body); } catch (_) { body = options.body; }
      }
      const call = { url: String(url), method, body };
      calls.push(call);
      const plan = router(call) || {};
      await Promise.resolve();
      return {
        ok: plan.ok !== false,
        status: plan.status || 200,
        json: async () => plan.payload,
      };
    } finally {
      inflight.count--;
    }
  };
  return {
    calls,
    inflight,
    async settle() {
      for (let i = 0; i < 100 && inflight.count > 0; i++) {
        await new Promise((r) => setImmediate(r));
      }
      for (let i = 0; i < 10; i++) await new Promise((r) => setImmediate(r));
    },
  };
}

const API = "/comfymodal";
const byTestid = (root, id) => root.querySelector(`[data-testid="${id}"]`);
const allByTestid = (root, id) => root.querySelectorAll(`[data-testid="${id}"]`);

function makeRegistry(activeId) {
  return {
    status: "ok",
    active_workspace_id: activeId,
    workspaces: [
      {
        id: "ws_1",
        label: "Studio A",
        token_id_masked: "ak-aaaa\u2026zzzz",
        token_secret_masked: "as-bbbb\u2026yyyy",
        last_used_at: 1730000000,
        last_deploy_status: "ready",
        notes: "",
      },
      {
        id: "ws_2",
        label: "Studio B",
        token_id_masked: "ak-cccc\u2026xxxx",
        token_secret_masked: "as-dddd\u2026wwww",
        last_used_at: null,
        last_deploy_status: "idle",
        notes: "",
      },
    ],
  };
}

function baseRouter(overrides) {
  const o = overrides || {};
  return function route(call) {
    const url = call.url;
    if (url.endsWith("/workspaces/active")) {
      if (o.activateFail) return { ok: false, status: 400, payload: { status: "error", message: "unknown workspace" } };
      const reg = makeRegistry(call.body.workspace_id);
      return { payload: { status: "ok", active_workspace_id: call.body.workspace_id, workspaces: reg.workspaces } };
    }
    if (call.method === "GET" && url.includes("/workspaces/swap/")) {
      if (o.swapHandler) return o.swapHandler(call);
      return { payload: o.swapStatus || { status: "running", phase: "downloading_models", download_message: "Fetching checkpoint.safetensors" } };
    }
    if (url.endsWith("/workspaces/swap") && call.method === "POST") {
      if (o.swapHandler) return o.swapHandler(call);
      return { payload: { status: "review_required", workspace_label: "Studio B", already_present: [], to_install: [{ folder: "checkpoints", filename: "a.safetensors", save_path: "checkpoints" }], to_remove: [], present_count: 0, install_count: 1 } };
    }
    if (url.endsWith("/workspaces") && call.method === "POST") {
      return { payload: { status: "ok", active_workspace_id: "ws_1", workspaces: makeRegistry("ws_1").workspaces } };
    }
    if (url.endsWith("/workspaces")) {
      return { payload: o.registry || makeRegistry("ws_1") };
    }
    if (url.endsWith("/deploy/status")) {
      return { payload: o.deployStatus || { state: "ready", message: "Fake deployment ready", has_log: true } };
    }
    if (url.endsWith("/deploy/log")) {
      return { payload: { log: "line1\nline2\nline3" } };
    }
    if (url.endsWith("/deploy") && call.method === "POST") {
      if (o.deployHandler) return o.deployHandler(call);
      return { payload: { status: "started" } };
    }
    if (url.endsWith("/auth/status")) {
      return { payload: { connected: o.authConnected !== false } };
    }
    if (url.endsWith("/hf-token") && call.method === "POST") {
      if (o.hfSaveFail) return { ok: false, status: 400, payload: { status: "error", message: "HF token must start with hf_" } };
      return { payload: { status: "ok" } };
    }
    if (url.endsWith("/hf-token")) {
      return { payload: { token: o.hfToken == null ? "hf_abcd1234..." : o.hfToken } };
    }
    if (url.endsWith("/civitai-token") && call.method === "POST") {
      return { payload: { status: "ok" } };
    }
    if (url.endsWith("/civitai-token")) {
      return { payload: { token: o.civitaiToken || "" } };
    }
    if (url.includes("/health")) {
      return { payload: { status: "ok", mode: "deploy" } };
    }
    if (url.endsWith("/manifest/repair/scan")) {
      return { payload: { status: "ok", issues: [] } };
    }
    if (url.endsWith("/manifest/repair/apply")) {
      return { payload: { status: "ok", entries: [], issues: [] } };
    }
    if (url.endsWith("/manifest/repair/delete-placeholder")) {
      return { payload: { status: "ok", removed: true, message: "Placeholder deleted." } };
    }
    return { payload: {} };
  };
}

async function mountWorkspaces(fetcher, timers) {
  const { renderWorkspacesSection } = await import("../web/studio-backend-workspaces.js");
  const root = document.createElement("div");
  const sectionEl = renderWorkspacesSection(root, API, { emit() {}, on() {} });
  await fetcher.settle();
  return { root, sectionEl };
}

async function mountDeployment(fetcher) {
  const { renderDeploymentSection } = await import("../web/studio-backend-deployment.js");
  const root = document.createElement("div");
  const sectionEl = renderDeploymentSection(root, API, { emit() {}, on() {} });
  await fetcher.settle();
  return { root, sectionEl };
}

async function mountCredentials(fetcher) {
  const { renderCredentialsSection } = await import("../web/studio-backend-credentials.js");
  const root = document.createElement("div");
  const sectionEl = renderCredentialsSection(root, API);
  await fetcher.settle();
  return { root, sectionEl };
}

// ── Tests ─────────────────────────────────────────────────────────────────

installBrowserStubs();
const realSetTimeout = globalThis.setTimeout;
const realClearTimeout = globalThis.clearTimeout;

try {
  // ── WORKSPACE ───────────────────────────────────────────────────────────

  // 1. List renders from server truth.
  {
    const fetcher = installFetch(baseRouter());
    const { root } = await mountWorkspaces(fetcher);
    const cards = allByTestid(root, "backend-workspace-card");
    assert.equal(cards.length, 2);
    assert.ok(cards[0].textContent.includes("Studio A"));
    assert.ok(cards[1].textContent.includes("Studio B"));
    section("W1. Workspace list renders from server registry");
  }

  // 2. Active identity renders truthfully (server-reported).
  {
    const fetcher = installFetch(baseRouter());
    const { root } = await mountWorkspaces(fetcher);
    const activeLabel = byTestid(root, "backend-workspaces-active-label");
    assert.ok(activeLabel, "active identity line present");
    assert.equal(activeLabel.textContent, "Studio A");
    const badges = allByTestid(root, "backend-workspace-card");
    const activeCard = badges.find((c) => c.textContent.includes("ACTIVE"));
    assert.ok(activeCard && activeCard.textContent.includes("Studio A"));
    section("W2. Active workspace identity renders from server truth");
  }

  // 3. Activate sends the exact existing request.
  {
    const fetcher = installFetch(baseRouter());
    const { root } = await mountWorkspaces(fetcher);
    const cards = allByTestid(root, "backend-workspace-card");
    cards[1].dispatch("click");
    const activateBtn = byTestid(root, "backend-workspace-activate");
    assert.equal(activateBtn.disabled, false);
    activateBtn.dispatch("click");
    await fetcher.settle();
    const post = fetcher.calls.find((c) => c.method === "POST" && c.url.endsWith("/workspaces/active"));
    assert.ok(post, "activation POST sent");
    assert.deepEqual(post.body, { workspace_id: "ws_2" });
    section("W3. Activate sends exact POST /workspaces/active contract");
  }

  // 4. Activation failure preserves prior server truth.
  {
    const fetcher = installFetch(baseRouter({ activateFail: true }));
    const { root } = await mountWorkspaces(fetcher);
    const cards = allByTestid(root, "backend-workspace-card");
    cards[1].dispatch("click");
    byTestid(root, "backend-workspace-activate").dispatch("click");
    await fetcher.settle();
    const activeLabel = byTestid(root, "backend-workspaces-active-label");
    assert.equal(activeLabel.textContent, "Studio A", "previous active stays visibly active");
    const activeCards = allByTestid(root, "backend-workspace-card");
    const stillActive = activeCards.find((c) => c.textContent.includes("ACTIVE"));
    assert.ok(stillActive && stillActive.textContent.includes("Studio A"));
    const progress = byTestid(root, "backend-workspaces-progress");
    assert.ok(progress.textContent.includes("Activation failed"));
    section("W4. Activation failure keeps previous server-truth active");
  }

  // 5. Add/Edit use the exact existing upsert contract.
  {
    const fetcher = installFetch(baseRouter());
    const { root } = await mountWorkspaces(fetcher);
    byTestid(root, "backend-workspace-add").dispatch("click");
    const form = byTestid(root, "backend-workspace-form");
    const inputs = form.querySelectorAll("input");
    inputs[0].value = "Studio C";
    inputs[1].value = "ak-newtoken";
    inputs[2].value = "as-newsecret";
    byTestid(root, "backend-workspace-save").dispatch("click");
    await fetcher.settle();
    const addPost = fetcher.calls.find((c) => c.method === "POST" && c.url.endsWith("/workspaces"));
    assert.deepEqual(addPost.body, { label: "Studio C", token_id: "ak-newtoken", token_secret: "as-newsecret", set_active: false });

    // Edit: blank token fields mean keep-current (legacy contract parity).
    const cards = allByTestid(root, "backend-workspace-card");
    cards[0].dispatch("click");
    byTestid(root, "backend-workspace-edit").dispatch("click");
    const editForm = byTestid(root, "backend-workspace-form");
    const editInputs = editForm.querySelectorAll("input");
    assert.equal(editInputs[0].value, "Studio A");
    assert.equal(editInputs[1].value, "");
    assert.equal(editInputs[2].value, "");
    byTestid(root, "backend-workspace-save").dispatch("click");
    await fetcher.settle();
    const posts = fetcher.calls.filter((c) => c.method === "POST" && c.url.endsWith("/workspaces"));
    assert.equal(posts.length, 2);
    assert.deepEqual(posts[1].body, { workspace_id: "ws_1", label: "Studio A", token_id: "", token_secret: "", set_active: false });
    section("W5. Add/Edit send exact POST /workspaces contracts");
  }

  // 6. Swap uses the exact existing multi-phase contract.
  {
    const seenSwapPosts = [];
    let pollCount = 0;
    const fetcher = installFetch(baseRouter({
      swapHandler(call) {
        if (call.method === "GET") {
          pollCount++;
          if (pollCount >= 2) {
            return { payload: { status: "ok", workspace_label: "Studio B", installed_model_count: 1, skipped_model_count: 0 } };
          }
          return { payload: { status: "running", phase: "downloading_models", download_message: "Fetching a.safetensors" } };
        }
        seenSwapPosts.push(call.body);
        if (seenSwapPosts.length === 1) {
          return { payload: { status: "confirm_required", message: "prompt execution is active" } };
        }
        if (seenSwapPosts.length === 2) {
          return { payload: { status: "review_required", workspace_label: "Studio B", already_present: [], to_install: [{ folder: "checkpoints", filename: "a.safetensors", save_path: "checkpoints" }], to_remove: [], present_count: 0, install_count: 1 } };
        }
        return { payload: { status: "started", swap_id: "swap_77", workspace_label: "Studio B" } };
      },
    }));
    const timers = installManualTimers();
    const { root } = await mountWorkspaces(fetcher, timers);

    const cards = allByTestid(root, "backend-workspace-card");
    cards[1].dispatch("click");
    byTestid(root, "backend-workspace-swap").dispatch("click");
    await fetcher.settle();

    // Phase 1: confirm_required → explicit interrupt confirmation.
    const confirmYes = byTestid(root, "backend-swap-confirm-yes");
    assert.ok(confirmYes, "interrupt confirmation surfaced");
    confirmYes.dispatch("click");
    await fetcher.settle();

    // Phase 2: review_required → select models and start.
    const goBtn = byTestid(root, "backend-swap-review-go");
    assert.ok(goBtn, "review dialog surfaced");
    const checkboxes = byTestid(root, "backend-swap-review-list").querySelectorAll("input");
    assert.equal(checkboxes.length, 1);
    assert.equal(checkboxes[0].checked, true);
    goBtn.dispatch("click");
    await fetcher.settle();

    assert.deepEqual(seenSwapPosts[0], { workspace_id: "ws_2" });
    assert.deepEqual(seenSwapPosts[1], { workspace_id: "ws_2", confirm_prompt_interrupt: true });
    assert.deepEqual(seenSwapPosts[2], { workspace_id: "ws_2", confirm: true, selected_keys: ["checkpoints/a.safetensors"] });

    // Phase 3: job polling until terminal, then server-truth re-read.
    await timers.flushAll();
    await fetcher.settle();
    const pollGets = fetcher.calls.filter((c) => c.method === "GET" && c.url.endsWith("/workspaces/swap/swap_77"));
    assert.ok(pollGets.length >= 2, "swap job polled via GET /workspaces/swap/{id}");
    const progress = byTestid(root, "backend-workspaces-progress");
    assert.ok(progress.textContent.includes("Done"), "bounded terminal success message");
    const registryReadsAfter = fetcher.calls.filter((c) => c.method === "GET" && c.url.endsWith("/workspaces")).length;
    assert.ok(registryReadsAfter >= 2, "server truth re-read after mutation");
    section("W6. Swap follows exact confirm/review/poll contract");
  }

  // 7. No workspace-registry export/import controls exist (no server route;
  //    documented gap — browser must not fabricate registry authority).
  {
    const fetcher = installFetch(baseRouter());
    const { root } = await mountWorkspaces(fetcher);
    const texts = root.textContent;
    assert.equal(texts.includes("Export Registry"), false);
    assert.equal(texts.includes("Import Registry"), false);
    assert.equal(workspacesSource.includes("workflow-manifest/export"), false);
    assert.equal(workspacesSource.includes("workflow-manifest/import"), false);
    section("W7. Registry export/import absent (explicit-action-only rule honored)");
  }

  // 8. Secret material is never rendered or attached to the DOM.
  {
    const fetcher = installFetch(baseRouter());
    const { root } = await mountWorkspaces(fetcher);
    const text = root.textContent;
    assert.equal(text.includes("ak-aaaa"), false, "masked token id never rendered");
    assert.equal(text.includes("as-bbbb"), false, "masked token secret never rendered");
    const jsonDom = JSON.stringify(root.attributes) + JSON.stringify(collectDatasets(root));
    assert.equal(jsonDom.includes("token_id_masked"), false);
    assert.equal(jsonDom.includes("token_secret"), false);
    section("W8. No secret fields rendered or stored in DOM datasets");
  }

  // ── DEPLOY ──────────────────────────────────────────────────────────────

  // 9. Status renders server-reported truth verbatim.
  {
    const fetcher = installFetch(baseRouter({
      deployStatus: { state: "deployed_unwarmed", message: "Deployed Studio A v9, manual warmup required", has_log: true },
    }));
    const { root } = await mountDeployment(fetcher);
    assert.equal(byTestid(root, "backend-deploy-state").textContent, "deployed_unwarmed");
    assert.equal(byTestid(root, "backend-deploy-message").textContent, "Deployed Studio A v9, manual warmup required");
    section("D9. Deploy status renders server truth without inference");
  }

  // 10. Deploy runs only on explicit action and hits the exact route.
  {
    const timers = installManualTimers();
    const fetcher = installFetch(baseRouter());
    const { root } = await mountDeployment(fetcher);
    byTestid(root, "backend-deploy-trigger").dispatch("click");
    await fetcher.settle();
    const posts = fetcher.calls.filter((c) => c.method === "POST" && c.url.endsWith("/deploy"));
    assert.equal(posts.length, 1);
    assert.ok(byTestid(root, "backend-deploy-result").textContent.includes("Deploy started"));
    section("D10. Deploy is explicit and sends POST /deploy");
  }

  // 11. Redeploy-and-Restart is explicit and begins with POST /deploy.
  {
    const timers = installManualTimers();
    const fetcher = installFetch(baseRouter());
    const { root } = await mountDeployment(fetcher);
    const btn = byTestid(root, "backend-deploy-restart");
    btn.dispatch("click");
    await fetcher.settle();
    const posts = fetcher.calls.filter((c) => c.method === "POST" && c.url.endsWith("/deploy"));
    assert.equal(posts.length, 1);
    assert.equal(btn.disabled, true, "restart flow visible in-flight state");
    section("D11. Redeploy+Restart explicit with in-flight state");
  }

  // 12. Double-click dedupe: rapid second click sends no second POST.
  {
    const timers = installManualTimers();
    const fetcher = installFetch(baseRouter());
    const { root } = await mountDeployment(fetcher);
    const btn = byTestid(root, "backend-deploy-trigger");
    btn.dispatch("click");
    btn.dispatch("click");
    btn.dispatch("click");
    await fetcher.settle();
    const posts = fetcher.calls.filter((c) => c.method === "POST" && c.url.endsWith("/deploy"));
    assert.equal(posts.length, 1);
    section("D12. Rapid clicks dedupe to a single deploy request");
  }

  // 13. Mounting never triggers a deploy.
  {
    const timers = installManualTimers();
    const fetcher = installFetch(baseRouter());
    await mountDeployment(fetcher);
    const posts = fetcher.calls.filter((c) => c.method === "POST" && c.url.endsWith("/deploy"));
    assert.equal(posts.length, 0);
    const gets = fetcher.calls.filter((c) => c.method === "GET" && c.url.endsWith("/deploy/status"));
    assert.equal(gets.length, 1, "mount performs read-only status fetch");
    section("D13. No deploy on mount (read-only status fetch only)");
  }

  // 14. Bounded failure state: message shown, buttons re-enabled.
  {
    const timers = installManualTimers();
    const fetcher = installFetch(baseRouter({
      deployHandler() {
        return { payload: { status: "error", message: "No active workspace configured" } };
      },
    }));
    const { root } = await mountDeployment(fetcher);
    byTestid(root, "backend-deploy-trigger").dispatch("click");
    await fetcher.settle();
    const result = byTestid(root, "backend-deploy-result");
    assert.ok(result.textContent.includes("No active workspace configured"));
    assert.equal(byTestid(root, "backend-deploy-trigger").disabled, false);
    section("D14. Bounded deploy failure state with re-enabled controls");
  }

  // ── AUTH ────────────────────────────────────────────────────────────────

  // 15. Configured / not-configured states render from presence only.
  {
    const fetcher = installFetch(baseRouter({ hfToken: "hf_abcd1234...", civitaiToken: "" }));
    const { root } = await mountCredentials(fetcher);
    assert.ok(byTestid(root, "backend-cred-hf-state").textContent.includes("CONFIGURED"));
    assert.ok(byTestid(root, "backend-cred-civitai-state").textContent.includes("NOT CONFIGURED"));
    section("A15. Credential configured/unconfigured states truthful");
  }

  // 16. Saved credential material is never echoed into the UI.
  {
    const fetcher = installFetch(baseRouter({ hfToken: "hf_abcd1234..." }));
    const { root } = await mountCredentials(fetcher);
    const text = root.textContent;
    assert.equal(text.includes("hf_abcd1234"), false, "masked prefix never rendered");
    assert.ok(byTestid(root, "backend-auth-badge").textContent.includes("CONNECTED"));
    section("A16. Saved credentials never echoed; auth status shown");
  }

  // 17. Submit posts the exact existing route/body.
  {
    const fetcher = installFetch(baseRouter());
    const { root } = await mountCredentials(fetcher);
    const input = byTestid(root, "backend-cred-hf-input");
    assert.equal(input.type, "password", "password semantics");
    input.value = "hf_test_token_123";
    byTestid(root, "backend-cred-hf-save").dispatch("click");
    await fetcher.settle();
    const post = fetcher.calls.find((c) => c.method === "POST" && c.url.endsWith("/hf-token"));
    assert.ok(post);
    assert.deepEqual(post.body, { token: "hf_test_token_123" });
    assert.equal(input.value, "", "input cleared after successful save");
    section("A17. Submit uses exact POST /hf-token contract");
  }

  // 18. Failure surfaces the server message and never the token.
  {
    const fetcher = installFetch(baseRouter({ hfSaveFail: true }));
    const { root } = await mountCredentials(fetcher);
    const input = byTestid(root, "backend-cred-hf-input");
    input.value = "hf_bad_token_999";
    byTestid(root, "backend-cred-hf-save").dispatch("click");
    await fetcher.settle();
    const result = byTestid(root, "backend-cred-hf-result");
    assert.equal(result.textContent, "HF token must start with hf_");
    assert.equal(result.textContent.includes("hf_bad_token_999"), false);
    const datasets = collectDatasets(root);
    assert.equal(JSON.stringify(datasets).includes("hf_bad_token_999"), false);
    section("A18. Failure message bounded; token never leaked");
  }

  // ── OWNERSHIP ───────────────────────────────────────────────────────────

  // 19. No portability/provider selector anywhere in modern Backend ops.
  {
    const sources = [backendSource, workspacesSource, deploymentSource, credentialsSource, runtimeSource];
    for (const src of sources) {
      for (const banned of ["runpod", "runcomfy", "comfy_cloud", "baseten", '"local"', "'local'"]) {
        assert.equal(src.toLowerCase().includes(banned.toLowerCase()), false, `banned provider vocabulary: ${banned}`);
      }
      assert.equal(src.includes("Providers"), false, "no Providers tab");
    }
    section("O19. No provider selector / portability targets in Backend");
  }

  // 20. No model-library/install duplication in Backend operations.
  {
    const sources = [workspacesSource, deploymentSource, credentialsSource, runtimeSource];
    for (const src of sources) {
      for (const banned of [
        "/studio/models",
        "install-request",
        "batch-install",
        "model/install",
        "models/inject",
        "manifest/install",
        "download-progress",
      ]) {
        assert.equal(src.includes(banned), false, `model-library concern leaked into Backend: ${banned}`);
      }
    }
    section("O20. Model Library ownership not duplicated in Backend");
  }

  // 21. Backend Presets and Snapshots are removed; Credentials moved to Settings.
  {
    assert.equal(backendSource.includes('"Backend Presets"'), false, "Backend Presets tab removed");
    assert.equal(backendSource.includes('"snapshots"'), false, "Snapshots tab removed");
    assert.equal(backendSource.includes('"overview"'), false, "Overview tab removed");
    assert.equal(backendSource.includes('"credentials"'), false, "Credentials tab removed from Manage Modal");
    assert.equal(backendSource.includes("./studio-backend-presets.js"), false, "preset module no longer wired");
    assert.equal(backendSource.includes("./studio-backend-snapshots.js"), false, "snapshot module no longer wired");
    assert.equal(backendSource.includes("Make Preset"), false, "Make Preset launcher removed");
    // Credentials now live in Settings.
    assert.ok(readWeb("studio-settings.js").includes("renderCredentialsSection"),
      "Settings owns the credentials section");
    section("O21. Backend Presets/Snapshots/Overview removed; Credentials in Settings");
  }

  // 22. H18 Wave G: the legacy settings overlay is deleted. modal-settings.js
  //     is the minimal canvas/shared compatibility module and must carry NO
  //     operational sections — modern Backend is the sole operations owner.
  {
    for (const marker of [
      "+ Add Workspace",
      "Swap Workspace",
      "Manifest Repair",
      "Deploy to Cloud",
      "Redeploy and Restart",
      "HuggingFace Token",
      "Civitai API Key",
    ]) {
      assert.equal(legacySettingsSource.includes(marker), false, `retired overlay control must stay deleted: ${marker}`);
    }
    assert.equal(legacySettingsSource.includes("studio-backend-workspaces"), false);
    assert.equal(legacySettingsSource.includes("studio-backend-deployment"), false);
    assert.equal(legacySettingsSource.includes("studio-backend-credentials"), false);
    section("O22. Legacy overlay retired; modal-settings.js carries zero operational sections");
  }

  // 23. Warmup verdict enforced structurally: retired controls are absent.
  {
    const sources = [backendSource, workspacesSource, deploymentSource, credentialsSource, runtimeSource];
    for (const src of sources) {
      assert.equal(src.includes("deploy-warmup"), false, "warmup routes not exposed");
      assert.equal(src.includes("Warmup"), false, "warmup actions not exposed");
    }
    section("O23. WARMUP=RETIRE honored (no warmup controls in modern Backend)");
  }

  // 24. Overview summarizes operational truth read-only.
  {
    const fetcher = installFetch(baseRouter({
      deployStatus: { state: "ready", message: "Fake deployment ready" },
    }));
    const { renderRuntimeSection } = await import("../web/studio-backend-runtime.js");
    const root = document.createElement("div");
    renderRuntimeSection(root, API, { emit() {}, on() {} });
    await fetcher.settle();
    assert.ok(byTestid(root, "backend-runtime-workspace").textContent.includes("Studio A"));
    assert.ok(byTestid(root, "backend-runtime-deploy").textContent.includes("ready"));
    assert.equal(byTestid(root, "backend-runtime-auth").textContent, "Connected");
    assert.equal(byTestid(root, "backend-runtime-health").textContent, "Ready");
    const posts = fetcher.calls.filter((c) => c.method === "POST");
    assert.equal(posts.length, 0, "overview is read-only on mount");
    section("O24. Runtime overview read-only with truthful readiness rows");
  }

  // ── Phase I7 — Backend accessibility / loading / polish ─────────────────

  // 25. Workspaces opens on the shared loading primitive and swaps to
  //     server truth when the registry arrives (no plain-text placeholder).
  {
    const fetcher = installFetch(baseRouter());
    const { renderWorkspacesSection } = await import("../web/studio-backend-workspaces.js");
    const root = document.createElement("div");
    renderWorkspacesSection(root, API, { emit() {}, on() {} });
    const loader = byTestid(root, "backend-workspaces-loading");
    assert.ok(loader, "loading primitive mounted before server truth");
    assert.equal(loader.getAttribute("role"), "status");
    assert.equal(loader.getAttribute("aria-live"), "polite");
    assert.equal(loader.getAttribute("data-size"), "inline");
    const spinner = loader.querySelector(".cm-loading-spinner");
    assert.ok(spinner, "decorative spinner present");
    assert.equal(spinner.getAttribute("aria-hidden"), "true");
    assert.equal(loader.querySelector(".cm-loading-label").textContent, "Loading workspaces\u2026");
    await fetcher.settle();
    assert.equal(byTestid(root, "backend-workspaces-loading"), null, "loader replaced by truth");
    assert.equal(byTestid(root, "backend-workspaces-active-label").textContent, "Studio A");
    section("I7-25. Workspaces loading state uses role=status primitive, then server truth");
  }

  // 26. Source truth: the surviving Backend list modules consume the shared
  //     loading primitive; the dead renderEmptyState glue wrapper stays
  //     deleted; page h2 / tab selection / chip geometry markers present.
  {
    for (const [name, testid] of [
      ["workspaces", "backend-workspaces-loading"],
    ]) {
      const src = readWeb("studio-backend-workspaces.js");
      assert.ok(src.includes('./studio-loading.js'), `${name} imports the shared primitive`);
      assert.ok(src.includes(`"${testid}"`), `${name} loader carries its own testid`);
      assert.ok(src.includes("renderLoadingState({"), `${name} calls renderLoadingState`);
    }
    // Dead wrapper stays deleted (I7); shared primitive keeps its generic API.
    assert.equal(backendSource.includes("renderEmptyState"), false);
    assert.ok(readWeb("studio-ui.js").includes("function renderEmptyState(options"));
    // Page h2 (visually hidden clip pattern), tab selection state, FILTER
    // chips on the shared geometry base.
    assert.ok(backendSource.includes('"data-testid": "backend-page-title"'));
    assert.ok(backendSource.includes("clip:rect(0 0 0 0)"));
    assert.ok(backendSource.includes('setAttribute("aria-current", "true")'));
    assert.ok(backendSource.includes('removeAttribute("aria-current")'));
    assert.ok(backendSource.includes('class: "comfymodal-studio-feature-chip cm-chip"'));
    assert.ok(backendSource.includes('"aria-pressed": "false"'));
    section("I7-26. Loading migration + dead-wrapper deletion + a11y markers pinned at source level");
  }
} finally {
  globalThis.setTimeout = realSetTimeout;
  globalThis.clearTimeout = realClearTimeout;
}

function collectDatasets(node) {
  const out = [];
  const visit = (n) => {
    if (n.dataset && Object.keys(n.dataset).length) out.push({ ...n.dataset });
    for (const c of n.children || []) visit(c);
  };
  visit(node);
  return out;
}

console.log("PASS: studio backend operations unit tests (H6)");
