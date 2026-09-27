// H7 — Workflows Model Library parity unit tests.
//
// Deterministic Node coverage for the Workflows-owned Model Library /
// dependency surfaces (web/studio-model-library.js + the Dependencies region
// of web/studio-workflows.js).  Uses the same standalone DOM/fetch stubs as
// studio_phase_f8_gpu_reset_unit.mjs (house pattern).  No browser, no
// network, no Modal, no installs.
//
// Pins (H7 report §Test evidence):
//   1.  Parity classifications represented (canonical routes only)
//   2.  Authoritative list rendering (.studio_model_library.json via API)
//   3.  Missing dependency state
//   4.  Installed dependency state
//   5.  Model rescan is explicit-only (no scan on mount)
//   6.  Custom-node registry refresh is explicit-only + deduped
//   7.  Install requests require user action (model + custom node)
//   8.  No install/scan/refresh traffic on page load
//   9.  No automatic batch install (legacy raw routes absent from modern UI)
//   10. No install during portability check/import
//   11. Compatibility remains distinct from Portability
//   12. Version dependency context preserved (metadata chips fallback)
//   13. Failure state bounded (refresh/rescan failures never throw or wipe)
//   14. Request dedupe (in-flight refresh ignores re-clicks)
//   15. Legacy Models/Sync panel untouched (content pins)

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";
import {
  buildManagerModelIndex,
  buildManagerPackIndex,
  buildRemoteModelIndex,
  managerModelFolder,
  matchManagerModel,
  matchRemoteModel,
  normalizeManagerSavePath,
  overlayDependencyModel,
  overlayDependencyModels,
  parseManagerInstalled,
  performManagerInstall,
  renderModelLibraryView,
  renderDependencySection,
  resolveNodeInstall,
} from "../web/studio-model-library.js";
import { listRemoteModels, normalizeRemoteModelInventory } from "../web/studio-backend-api.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const WEB = path.join(ROOT, "web");
const readWeb = (name) => fs.readFileSync(path.join(WEB, name), "utf8");

const librarySource = readWeb("studio-model-library.js");
const workflowsSource = readWeb("studio-workflows.js");
const portabilitySource = readWeb("studio-portability.js");
const backendApiSource = readWeb("studio-backend-api.js");
const modalSettingsSource = readWeb("modal-settings.js");

function section(name) {
  console.log("PASS: " + name);
}

// ── DOM / browser-environment stubs (house pattern) ───────────────────────

function matchesClass(node, cls) {
  return (" " + (node.className || "") + " ").indexOf(" " + cls + " ") !== -1;
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
      href: "",
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
      click() {
        for (const fn of (this.listeners.click || []).slice()) {
          fn({ type: "click", target: this, currentTarget: this, preventDefault() {}, stopPropagation() {} });
        }
      },
      setAttribute(name, v) {
        this.attributes[name] = String(v);
        if (name === "data-testid") this.dataset.testid = String(v);
      },
      getAttribute(name) {
        return name in this.attributes ? this.attributes[name] : null;
      },
      removeAttribute(name) {
        delete this.attributes[name];
      },
      classList: {
        add(c) {
          if (!matchesClass(node, c)) node.className = (node.className ? node.className + " " : "") + c;
        },
        remove(c) {
          node.className = (" " + node.className + " ").replace(" " + c + " ", " ").trim();
        },
        toggle(c, force) {
          const has = matchesClass(node, c);
          const want = force === undefined ? !has : !!force;
          if (want) node.classList.add(c);
          else node.classList.remove(c);
          return want;
        },
        contains(c) {
          return matchesClass(node, c);
        },
      },
      get textContent() {
        if (ownText) return ownText;
        return node.children.map((c) => (c.textContent == null ? "" : c.textContent)).join("");
      },
      set textContent(v) {
        ownText = String(v);
      },
    };
    return node;
  }
  const body = makeNode("body");
  return {
    createElement(tag) {
      return makeNode(tag);
    },
    createTextNode(text) {
      return { nodeType: 3, textContent: String(text), parentNode: null };
    },
    body,
  };
}

globalThis.document = createDocumentStub();

/** Find every node in a tree carrying data-testid === testid. */
function findByTestId(root, testid) {
  const out = [];
  const visit = (node) => {
    if (!node || typeof node !== "object") return;
    if (node.dataset && node.dataset.testid === testid) out.push(node);
    for (const c of node.children || []) visit(c);
  };
  visit(root);
  return out;
}

function findOneByTestId(root, testid) {
  const hits = findByTestId(root, testid);
  assert.equal(hits.length, 1, "expected exactly one [data-testid=" + testid + "], got " + hits.length);
  return hits[0];
}

// ── fetch stub ────────────────────────────────────────────────────────────

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
      const call = { url: String(url), method: method, body: body };
      calls.push(call);
      await Promise.resolve();
      const payload = router(call);
      if (payload && payload.__fail) {
        return { ok: false, status: payload.__status || 500, json: async () => ({ status: "error", message: payload.__message || "boom" }), text: async () => JSON.stringify({ status: "error", message: payload.__message || "boom" }) };
      }
      return { ok: true, status: 200, json: async () => payload || {}, text: async () => (payload ? JSON.stringify(payload) : "") };
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

// ── Fixtures ──────────────────────────────────────────────────────────────

const MODELS_PAYLOAD = {
  status: "ok",
  scan_hint: "ok",
  total: 2,
  models: [
    {
      model_id: "ml_a", folder: "checkpoints", filename: "alpha.safetensors",
      display_name: "Alpha", model_type: "checkpoint", hash: "aaaa1111bbbb",
      size: 1024, installed: true, local_path: "/models/checkpoints/alpha.safetensors",
      source_urls: [], notes: "", tags: [],
    },
    {
      model_id: "ml_b", folder: "loras", filename: "beta.safetensors",
      display_name: "Beta", model_type: "lora", hash: null,
      size: 2048, installed: false, local_path: "",
      source_urls: ["https://example.com/beta"], notes: "", tags: [],
    },
  ],
};

const TYPES_PAYLOAD = { status: "ok", types: ["checkpoint", "lora"] };

const NODES_PAYLOAD = {
  status: "ok",
  core_classes: 3,
  custom_nodes: [
    {
      name: "ComfyUI-Example",
      install_path: "/custom_nodes/ComfyUI-Example",
      repo_url: "https://github.com/example/ComfyUI-Example",
      installed_commit: "deadbeef1234",
      classes: ["ExampleNode"],
      updated_at: "2026-01-01T00:00:00.000Z",
    },
  ],
};

const DEPS_PAYLOAD = {
  status: "ok",
  version_id: "wv_1",
  models: [
    { key: "checkpoints|alpha.safetensors", role: "checkpoint", filename: "alpha.safetensors", state: "installed", local_path: "/models/checkpoints/alpha.safetensors" },
    { key: "loras|beta.safetensors", role: "lora", filename: "beta.safetensors", state: "missing", source_urls: ["https://example.com/beta"] },
  ],
  custom_nodes: [
    { name: "MissingNode", state: "missing", repository_url: "https://github.com/example/MissingNode", required_revision: "" },
    { name: "InstalledNode", state: "installed", installed_commit: "abc1234abcd", repository_url: "https://github.com/example/InstalledNode" },
  ],
  summary: { ready: false, attention: 2 },
};

function defaultRouter(call) {
  const pathPart = call.url.replace(/^https?:\/\/[^/]+/, "");
  if (call.method === "GET" && pathPart.startsWith("/comfymodal/studio/models?") || (call.method === "GET" && pathPart === "/comfymodal/studio/models")) return MODELS_PAYLOAD;
  if (call.method === "GET" && pathPart === "/comfymodal/studio/models/types") return TYPES_PAYLOAD;
  if (call.method === "GET" && pathPart === "/comfymodal/studio/custom-nodes") return NODES_PAYLOAD;
  if (call.method === "POST" && pathPart === "/comfymodal/studio/models/rescan") return { status: "ok", summary: { total: 2 } };
  if (call.method === "POST" && pathPart === "/comfymodal/studio/custom-nodes/refresh") return NODES_PAYLOAD;
  if (call.method === "POST" && pathPart === "/comfymodal/studio/custom-nodes/install-request") {
    return { status: "ok", request: { name: call.body.name, approved: true }, note: "Approval recorded." };
  }
  if (call.method === "POST" && pathPart === "/comfymodal/studio/models/install-request") {
    return { status: "ok", request: { approved: true }, note: "Approval recorded." };
  }
  if (call.method === "POST" && pathPart === "/customnode/install/git_url") {
    return { status: "ok" };
  }
  if (call.method === "POST" && pathPart === "/comfymodal/model/install") {
    return { status: "ok", download_id: "dl_1" };
  }
  if (call.method === "GET" && pathPart.indexOf("/comfymodal/download/status/") === 0) {
    return { status: "ok", state: "complete" };
  }
  return {};
}

function makeView() {
  return {
    mode: "models",
    modelsData: {
      models: [],
      scanHint: "not_scanned",
      filters: { query: "", type: "", state: "" },
      types: [],
      customNodes: [],
      loading: false,
      _loaded: false,
    },
  };
}

/** Mount the Model Library view into a fresh container and wait for loads. */
async function mountLibrary(router) {
  const net = installFetch(router || defaultRouter);
  const container = globalThis.document.createElement("div");
  const view = makeView();
  const mount = () => {
    while (container.children.length) container.removeChild(container.children[0]);
    container.appendChild(renderModelLibraryView({ apiBase: "/comfymodal", view, refresh: mount }));
  };
  mount();
  await settle(net.inflight);
  return { net, container, view, remount: mount };
}

// ── 1–4. Rendering pins ───────────────────────────────────────────────────

{
  const { net, container } = await mountLibrary();

  // 2. Authoritative list rendering: rows come from the canonical list route.
  const rows = findByTestId(container, "model-row");
  assert.equal(rows.length, 2);
  assert.ok(rows[0].textContent.indexOf("alpha.safetensors") !== -1);
  assert.ok(rows[0].textContent.indexOf("aaaa1111bbbb") !== -1, "hash provenance rendered");
  assert.equal(net.calls.filter((c) => c.url.indexOf("/studio/models") !== -1 && c.method === "GET").length >= 1, true);
  section("2. Authoritative list rendering from the canonical models route");

  // Custom-node registry section renders the canonical registry row.
  const cnSection = findOneByTestId(container, "custom-nodes-section");
  assert.ok(cnSection.textContent.indexOf("ComfyUI-Example") !== -1, "registry node name rendered");
  assert.ok(cnSection.textContent.indexOf("deadbeef12") !== -1, "commit provenance rendered");
  assert.ok(cnSection.textContent.indexOf("1 class") !== -1, "class count rendered");
  section("3a. Custom-node registry browse renders canonical records");

  // 3+4. Dependency states.
  const deps = renderDependencySection({ dependency_metadata: null }, DEPS_PAYLOAD, null, {});
  const depRows = findByTestId(deps, "dependency-model-row");
  assert.equal(depRows.length, 2);
  const missingRow = depRows[1];
  assert.ok(missingRow.textContent.indexOf("Missing") !== -1);
  assert.equal(
    missingRow.textContent.indexOf("Not installed"),
    -1,
    "redundant Not installed detail is replaced by the state badge alone"
  );
  const missingBadge = findOneByTestId(missingRow, "dependency-model-state");
  assert.equal(missingBadge.textContent, "Missing");
  assert.equal(missingBadge.getAttribute("data-state"), "missing");
  const installedRow = depRows[0];
  assert.ok(installedRow.textContent.indexOf("Installed") !== -1);
  assert.ok(installedRow.textContent.indexOf("/models/checkpoints/alpha.safetensors") !== -1);
  const installedBadge = findOneByTestId(installedRow, "dependency-model-state");
  assert.equal(installedBadge.textContent, "Installed");
  assert.equal(installedBadge.getAttribute("data-state"), "installed");
  const nodeRows = findByTestId(deps, "dependency-node-row");
  assert.ok(nodeRows[0].textContent.indexOf("Missing") !== -1);
  assert.ok(nodeRows[1].textContent.indexOf("Installed") !== -1);
  section("3+4. Missing and installed dependency states render truthfully");

  // 8. No install/scan/refresh POSTs happened during any of the above mounts.
  const mutating = net.calls.filter((c) => c.method === "POST");
  assert.equal(mutating.length, 0, "mount must issue zero POSTs, saw: " + JSON.stringify(mutating));
  section("8. No install/scan/refresh traffic on page load");
}

// ── 5. Model rescan is explicit ───────────────────────────────────────────

{
  const { net, container } = await mountLibrary();
  assert.equal(net.calls.filter((c) => c.method === "POST" && c.url.indexOf("/models/rescan") !== -1).length, 0);
  const scanBtn = findOneByTestId(container, "models-rescan");
  assert.equal(scanBtn.disabled, false, "scan button enabled after load settles");
  scanBtn.click();
  await settle(net.inflight);
  assert.equal(net.calls.filter((c) => c.method === "POST" && c.url.indexOf("/models/rescan") !== -1).length, 1);
  section("5. Model rescan fires only from the explicit Scan models button");
}

// ── 6+14. Custom-node refresh explicit + dedupe ──────────────────────────

{
  const { net, container } = await mountLibrary();
  assert.equal(net.calls.filter((c) => c.method === "POST" && c.url.indexOf("/custom-nodes/refresh") !== -1).length, 0, "no auto refresh");

  const btn = findOneByTestId(container, "custom-nodes-refresh");
  // Simulate a double-click race: first click disables the button, so the
  // second dispatch must be ignored until the request settles.
  btn.click();
  btn.click();
  await settle(net.inflight);
  const refreshPosts = net.calls.filter((c) => c.method === "POST" && c.url.indexOf("/custom-nodes/refresh") !== -1);
  assert.equal(refreshPosts.length, 1, "in-flight refresh dedupes re-clicks");
  assert.equal(btn.disabled, false, "button re-enabled after completion");
  section("6+14. Custom-node refresh is explicit-only and request-deduped");
}

// ── 7. Install actions require user action ───────────────────────────────

{
  const { net } = await mountLibrary();
  const before = net.calls.filter((c) => c.method === "POST").length;

  // Custom-node install from a MISSING dependency row: exactly ONE
  // Manager-backed "Install now" — no record-only request, no second control.
  const deps = renderDependencySection({}, DEPS_PAYLOAD, null, { apiBase: "/comfymodal" });
  const installBtn = findOneByTestId(deps, "dependency-node-install-now");
  assert.equal(installBtn.textContent, "Install now");
  assert.equal(findByTestId(deps, "dependency-node-install-request").length, 0, "record-only request removed");
  assert.equal(findByTestId(deps, "dependency-node-manager-install").length, 0, "no second installer");
  assert.equal(findByTestId(deps, "dependency-node-find-registry").length, 0, "Find in registry removed");
  assert.equal(before, net.calls.filter((c) => c.method === "POST").length, "rendering alone posts nothing");
  installBtn.click();
  await settle(net.inflight);
  const managerInstalls = net.calls.filter((c) => c.method === "POST" && c.url.indexOf("/customnode/install/git_url") !== -1);
  assert.equal(managerInstalls.length, 1);
  assert.equal(managerInstalls[0].body.url, "https://github.com/example/MissingNode");
  assert.equal(net.calls.filter((c) => c.url.indexOf("/custom-nodes/install-request") !== -1).length, 0);
  const note = findOneByTestId(deps, "dependency-node-install-note");
  assert.ok(note.textContent.indexOf("Installed") !== -1, "Manager install outcome shown");
  section("7a. Custom-node install routes through Manager and is click-gated");

  // Model install request stays inside the detail dialog (existing flow).
  assert.ok(librarySource.indexOf("requestModelInstall") !== -1);
  assert.ok(librarySource.indexOf("Request download") !== -1);
  assert.ok(librarySource.indexOf("never fetched from here") !== -1, "approval-only copy retained");
  section("7b. Model download request remains the explicit detail-dialog flow");
}

// ── 7c/7d. Missing model rows expose exactly two explicit install actions ─

{
  const { net } = await mountLibrary();
  const deps = renderDependencySection({}, DEPS_PAYLOAD, null, { apiBase: "/comfymodal" });

  const queue = findByTestId(deps, "dependency-model-queue");
  const now = findByTestId(deps, "dependency-model-install-now");
  assert.equal(queue.length, 1, "only the missing model row offers Queue install");
  assert.equal(now.length, 1, "only the missing model row offers Install now");
  assert.equal(queue[0].textContent, "Queue install");
  assert.equal(now[0].textContent, "Install now");
  assert.equal(findByTestId(deps, "dependency-model-download").length, 0, "legacy single action removed");

  // Install now → synchronous single-item batch install.
  now[0].click();
  await settle(net.inflight);
  const batch = net.calls.filter((c) => c.method === "POST" && c.url.indexOf("/models/batch-install") !== -1);
  assert.equal(batch.length, 1);
  assert.deepEqual(batch[0].body.items, [{
    url: "https://example.com/beta", filename: "beta.safetensors", save_path: "",
  }]);
  section("7c. Install now issues one synchronous single-item batch install");

  // Queue install → async single install + status poll.
  queue[0].click();
  await settle(net.inflight);
  const queued = net.calls.filter((c) => c.method === "POST" && c.url.indexOf("/comfymodal/model/install") !== -1);
  assert.equal(queued.length, 1);
  assert.deepEqual(queued[0].body, { url: "https://example.com/beta", filename: "beta.safetensors", save_path: "" });
  assert.ok(
    net.calls.some((c) => c.method === "GET" && c.url.indexOf("/comfymodal/download/status/") !== -1),
    "status polled"
  );
  section("7d. Queue install polls the async download status");
}

// ── 7p. In-flight install transitions the row state badge ────────────────

{
  const { net } = await mountLibrary();
  const deps = renderDependencySection({}, DEPS_PAYLOAD, null, { apiBase: "/comfymodal" });
  const row = findByTestId(deps, "dependency-model-row")[1];
  const badge = findOneByTestId(row, "dependency-model-state");
  assert.equal(badge.textContent, "Missing");

  const queue = findOneByTestId(row, "dependency-model-queue");
  queue.click();
  // The SAME node reports the queue truth synchronously, before awaiting.
  assert.equal(badge.textContent, "Queued for download");
  assert.equal(badge.getAttribute("data-state"), "queued");
  await settle(net.inflight);
  assert.equal(
    net.calls.filter((c) => c.method === "POST" && c.url.indexOf("/comfymodal/model/install") !== -1).length,
    1
  );
  assert.ok(net.calls.some((c) => c.method === "GET" && c.url.indexOf("/comfymodal/download/status/") !== -1));
  // No owner refresh handler → the badge falls back to the last-known state
  // rather than staying stuck on the queued pseudo-state.
  assert.equal(badge.textContent, "Missing");
  section("7p. In-flight install transitions the row state badge to Queued for download");
}

// ── 7q. Source-less row installs from an explicit user-supplied URL ───────

{
  const { net } = await mountLibrary();
  const deps = {
    status: "ok",
    models: [
      {
        key: "vae|no_source.safetensors",
        role: "vae",
        filename: "no_source.safetensors",
        folder: "vae",
        state: "missing",
        source_urls: [],
      },
    ],
    custom_nodes: [],
    summary: { ready: false, attention: 1 },
  };
  const depsSection = renderDependencySection({}, deps, null, { apiBase: "/comfymodal" });
  const row = findOneByTestId(depsSection, "dependency-model-row");
  // No guessed source → neither existing action is offered.
  assert.equal(findByTestId(row, "dependency-model-queue").length, 0);
  assert.equal(findByTestId(row, "dependency-model-install-now").length, 0);
  const urlIn = findOneByTestId(row, "dependency-model-url-input");
  const urlBtn = findOneByTestId(row, "dependency-model-url-install");

  // Empty URL: explicit validation, zero requests.
  urlBtn.click();
  await settle(net.inflight);
  assert.equal(
    net.calls.filter((c) => c.method === "POST").length,
    0,
    "empty URL never posts"
  );
  assert.ok(
    findOneByTestId(row, "dependency-model-install-note").textContent.indexOf("Paste a model URL") !== -1,
    "empty-URL guidance shown"
  );

  // Explicit URL install reuses the legacy async route + status polling; the
  // browser only passes the URL — the backend downloads to the Modal volume.
  urlIn.value = "https://example.com/no_source.safetensors";
  const badge = findOneByTestId(row, "dependency-model-state");
  urlBtn.click();
  assert.equal(badge.textContent, "Downloading\u2026");
  await settle(net.inflight);
  const posts = net.calls.filter((c) => c.method === "POST" && c.url.indexOf("/comfymodal/model/install") !== -1);
  assert.equal(posts.length, 1);
  assert.deepEqual(posts[0].body, {
    url: "https://example.com/no_source.safetensors",
    filename: "no_source.safetensors",
    save_path: "vae",
  });
  assert.ok(
    net.calls.some((c) => c.method === "GET" && c.url.indexOf("/comfymodal/download/status/") !== -1),
    "status polled"
  );
  section("7q. Source-less row installs from an explicit user URL via the legacy route");
}

// ── 7e. CNR / class → Manager pack resolution ────────────────────────────
// A missing node whose report carries only a cnr_id (Donut-style) resolves to
// its Manager pack repository and exposes the single Manager install action.

{
  const { net } = await mountLibrary();
  const index = buildManagerPackIndex(
    {
      channel: "default",
      node_packs: {
        donutnodes: {
          title: "ComfyUI-DonutNodes",
          repository: "https://github.com/DonutsDelivery/ComfyUI-DonutNodes",
          state: "not-installed",
        },
      },
    },
    { donutnodes: [["DonutLoaderClass"], { title_aux: "ComfyUI-DonutNodes" }] }
  );
  assert.ok(index.packs.donutnodes, "pack key indexed");
  assert.ok(index.byClass.donutloaderclass, "class mapping indexed");

  const deps = {
    status: "ok",
    models: [],
    custom_nodes: [
      {
        name: "ComfyUI-DonutNodes",
        cnr_id: "donutnodes",
        state: "missing",
        repository_url: "",
        classes: ["DonutLoaderClass"],
      },
    ],
    summary: { ready: false, attention: 1 },
  };
  const depsSection = renderDependencySection({}, deps, null, {
    apiBase: "/comfymodal",
    managerPacks: index,
  });
  const btn = findOneByTestId(depsSection, "dependency-node-install-now");
  assert.equal(btn.textContent, "Install now");
  const nodeBadge = findOneByTestId(depsSection, "dependency-node-state");
  assert.equal(nodeBadge.textContent, "Missing");
  btn.click();
  // The row's OWN missing badge reads "Queued" while the install is in flight.
  assert.equal(nodeBadge.textContent, "Queued");
  await settle(net.inflight);
  // Settled install reconciles to the report's real state (no stale queued chip).
  assert.equal(nodeBadge.textContent, "Missing");
  // A matched Manager record installs through the CNR queue (blank version
  // metadata included) — never the git_url 403 gate.
  const queue = net.calls.filter(
    (c) => c.method === "POST" && c.url.indexOf("/manager/queue/install") !== -1
  );
  assert.equal(queue.length, 1);
  assert.equal(queue[0].body.id, "donutnodes");
  assert.equal(
    net.calls.filter((c) => c.url.indexOf("/customnode/install/git_url") !== -1).length,
    0,
    "matched CNR pack never uses git_url"
  );
  section("7e. Missing node CNR id resolves to its Manager pack install");
}

// No match → no guessed URL and no install action.
{
  const index = buildManagerPackIndex({ node_packs: {} }, {});
  const deps = {
    status: "ok",
    models: [],
    custom_nodes: [
      { name: "donutnodes", cnr_id: "donutnodes", state: "missing", repository_url: "", classes: ["DonutLoaderClass"] },
    ],
    summary: { ready: false, attention: 1 },
  };
  const depsSection = renderDependencySection({}, deps, null, { apiBase: "/comfymodal", managerPacks: index });
  assert.equal(findByTestId(depsSection, "dependency-node-install-now").length, 0, "no Manager match → no install");
  assert.equal(findByTestId(depsSection, "dependency-node-row").length, 1, "row still rendered");
  section("7f. No Manager match renders the row without a guessed install URL");
}

// An UNMATCHED pack with an explicit report repository keeps the security-gated
// git_url fallback (the only path that still uses it).
{
  const { net } = await mountLibrary();
  const index = buildManagerPackIndex({ node_packs: {} }, {});
  const deps = {
    status: "ok",
    models: [],
    custom_nodes: [
      { name: "ComfyUI-Missing", state: "missing", repository_url: "https://github.com/example/ComfyUI-Missing", classes: ["MissingClass"] },
    ],
    summary: { ready: false, attention: 1 },
  };
  const depsSection = renderDependencySection({}, deps, null, { apiBase: "/comfymodal", managerPacks: index });
  findOneByTestId(depsSection, "dependency-node-install-now").click();
  await settle(net.inflight);
  const git = net.calls.filter((c) => c.method === "POST" && c.url.indexOf("/customnode/install/git_url") !== -1);
  assert.equal(git.length, 1, "unmatched explicit repository uses git_url");
  assert.equal(git[0].body.url, "https://github.com/example/ComfyUI-Missing");
  assert.equal(
    net.calls.filter((c) => c.url.indexOf("/manager/queue/install") !== -1).length,
    0,
    "no Manager record → never the CNR queue"
  );
  section("7f-b. unmatched explicit repository keeps the git_url fallback");
}

// ── 7g. Path-like dependency filenames match Manager basenames ───────────

{
  const deps = {
    status: "ok",
    models: [
      {
        key: "lora|sub/dir/foo.safetensors",
        role: "lora",
        filename: "sub/dir/foo.safetensors",
        state: "missing",
        source_urls: [],
      },
    ],
    custom_nodes: [],
    summary: { ready: false, attention: 1 },
  };
  const depsSection = renderDependencySection({}, deps, null, {
    apiBase: "/comfymodal",
    managerModelsByFilename: {
      "foo.safetensors": {
        url: "https://example.com/foo.safetensors",
        savePath: "loras",
        installed: "False",
      },
    },
  });
  const row = findByTestId(depsSection, "dependency-model-row")[0];
  assert.equal(
    findByTestId(row, "dependency-model-install-now").length,
    1,
    "basename match supplies the Manager install URL"
  );
  section("7g. Path-like dependency filename matches the Manager catalog basename");
}

// ── Find-in-library contextual handoff ───────────────────────────────────

{
  let handed = null;
  const deps = renderDependencySection({}, DEPS_PAYLOAD, null, {
    onFindInLibrary: (filename) => { handed = filename; },
  });
  const findBtns = findByTestId(deps, "dependency-model-find");
  assert.equal(findBtns.length, 1, "only the missing model row offers the handoff");
  findBtns[0].click();
  assert.equal(handed, "beta.safetensors");
  // Installed rows never offer it.
  const noExtra = findByTestId(deps, "dependency-model-find");
  assert.equal(noExtra.length, 1);
  section("11b. Dependency row hands off to the single Model Library filter");
}

// ── 9. No automatic batch install / raw downloader in modern UI ──────────

{
  for (const [name, src] of [["studio-model-library.js", librarySource], ["studio-workflows.js", workflowsSource]]) {
    for (const banned of ["/models/batch-install", "/model/install", "/download/status", "/sync/models", "/runtime/resync", "inject-all"]) {
      assert.equal(src.includes(banned), false, name + " must not reference legacy raw route " + banned);
    }
  }
  section("9. Modern Model Library references no legacy raw/batch download routes");
}

// ── 10. Portability flows never install ──────────────────────────────────

{
  for (const banned of ["requestModelInstall", "requestCustomNodeInstall", "install-request", "batch-install"]) {
    assert.equal(portabilitySource.includes(banned), false, "studio-portability.js must not reference " + banned);
  }
  section("10. Portability check/import triggers no install requests");
}

// ── 11. Compatibility ≠ Portability (vocabulary + endpoints stay distinct) ─

{
  assert.ok(backendApiSource.indexOf("/compatibility`") !== -1 || backendApiSource.indexOf("`/studio/workflows/versions/${encodeURIComponent(versionId)}/compatibility`") !== -1, "compatibility endpoint exists");
  assert.ok(backendApiSource.indexOf("portabilityEndpointPath") !== -1, "portability endpoint builder exists");
  assert.notEqual(
    backendApiSource.indexOf("/compatibility`"),
    backendApiSource.indexOf("portabilityEndpointPath"),
    "distinct endpoint families"
  );
  assert.equal(librarySource.includes("portability"), false, "Model Library module carries no portability vocabulary");
  assert.ok(workflowsSource.indexOf('"Compatible models"') !== -1 || workflowsSource.indexOf("Compatible models") !== -1, "Compatibility chips keep their distinct label");
  section("11. Compatibility annotations remain distinct from Portability");
}

// ── 12. Version dependency context preserved ─────────────────────────────

{
  const version = {
    dependency_metadata: {
      model_stack: { checkpoint: ["krea.safetensors"] },
      node_classes: ["KSampler"],
    },
  };
  const deps = renderDependencySection(version, null, null, {});
  assert.ok(deps.textContent.indexOf("Model stack") !== -1);
  assert.ok(deps.textContent.indexOf("krea.safetensors") !== -1);
  assert.ok(deps.textContent.indexOf("Node classes") !== -1);
  assert.ok(deps.textContent.indexOf("KSampler") !== -1);
  section("12. Recorded dependency metadata still renders when live deps fail");
}

// ── 13. Failure states are bounded ───────────────────────────────────────

{
  const failingRouter = (call) => {
    const pathPart = call.url.replace(/^https?:\/\/[^/]+/, "");
    if (call.method === "POST" && pathPart.indexOf("/custom-nodes/refresh") !== -1) return { __fail: true, __message: "registry offline" };
    if (call.method === "POST" && pathPart.indexOf("/models/rescan") !== -1) return { __fail: true, __message: "scan exploded" };
    return defaultRouter(call);
  };
  const { net, container } = await mountLibrary(failingRouter);

  // Custom-node refresh failure: bounded error line, rows retained, no throw.
  const btn = findOneByTestId(container, "custom-nodes-refresh");
  btn.click();
  await settle(net.inflight);
  const cnSection = findOneByTestId(container, "custom-nodes-section");
  assert.ok(cnSection.textContent.indexOf("Refresh failed") !== -1);
  assert.ok(cnSection.textContent.indexOf("registry offline") !== -1);
  assert.ok(cnSection.textContent.indexOf("ComfyUI-Example") !== -1, "previous registry rows retained");
  assert.equal(btn.disabled, false, "button recovers after failure");

  // Rescan failure path (existing behavior pinned).
  const scanBtn = findOneByTestId(container, "models-rescan");
  scanBtn.click();
  await settle(net.inflight);
  assert.ok(container.textContent.indexOf("Scan failed") !== -1);
  section("13. Refresh/rescan failures show bounded errors without wiping data");
}

// ── 15. Legacy Models/Sync panel retired (H18 Wave G) ────────────────────

{
  // The legacy overlay that hosted the raw Models/Sync sections was deleted
  // in H18; modal-settings.js is now the minimal canvas/shared compatibility
  // module. No retired raw-installer authority may reappear anywhere.
  for (const pin of [
    'createCollapsibleSection("Sync"',
    'createCollapsibleSection("Models"',
    "/models/batch-install",
    "/models/inject-all",
    "/sync/models",
    "/sync/custom-nodes",
    "/runtime/resync",
    '"Create All Placeholders"',
  ]) {
    assert.equal(modalSettingsSource.includes(pin), false, "retired legacy Models/Sync residue must stay deleted: " + pin);
  }
  section("15. Legacy Models/Sync overlay stays retired (zero raw-installer authority)");
}

// ── 1. Parity classification representation (route authority map) ────────

{
  // Workflows owns ONLY the canonical library/dependency routes.
  for (const canonical of [
    "/studio/models",
    "/studio/custom-nodes",
    "requestModelInstall",
    "dependencies",
  ]) {
    assert.ok(librarySource.includes(canonical), "modern module uses canonical surface: " + canonical);
  }
  // Backend-operational legacy actions are NOT reproduced here (they belong
  // to the Backend lane): inject placeholders, volume delete, sync uploads.
  for (const operational of ["/models/inject", "DELETE", "/workflow-manifest/", "/manifest/"]) {
    assert.equal(librarySource.includes(operational), false, "Model Library must not reproduce backend-operational action " + operational);
  }
  section("1. Parity classifications represented in the owned module surface");
}

// ── 7h. Preemptions beat an exact class mapping ───────────────────────────

{
  const index = buildManagerPackIndex(
    {
      channel: "default",
      node_packs: {
        packA: { title: "PackA", repository: "https://github.com/ex/PackA", preemptions: ["SharedClass"] },
        packB: { title: "PackB", repository: "https://github.com/ex/PackB" },
      },
    },
    { packB: [["SharedClass"], {}] }
  );
  const plan = resolveNodeInstall(
    { name: "SharedClass", classes: ["SharedClass"], state: "missing" },
    index
  );
  // A matched Manager record queues through Manager, never the git_url gate,
  // even without version metadata; the resolution still picks PackA.
  assert.equal(plan.kind, "cnr");
  assert.equal(plan.pack.name, "PackA");
  section("7h. preemptions win over an exact class mapping");
}

// ── 7i. nodename_pattern regex resolves an unmapped class ────────────────

{
  const index = buildManagerPackIndex(
    { node_packs: { patternpack: { title: "PatternPack", repository: "https://github.com/ex/Pattern" } } },
    { patternpack: [["ExactClass"], { nodename_pattern: "^Donut.*Loader$" }] }
  );
  const exact = resolveNodeInstall({ name: "ExactClass", classes: ["ExactClass"], state: "missing" }, index);
  assert.equal(exact.kind, "cnr", "matched class record queues via Manager");
  assert.equal(exact.pack.name, "PatternPack");
  const plan = resolveNodeInstall({ name: "DonutXLoader", classes: ["DonutXLoader"], state: "missing" }, index);
  assert.equal(plan.kind, "cnr", "nodename_pattern match queues via Manager");
  assert.equal(plan.pack.name, "PatternPack");
  section("7i. nodename_pattern regex resolves an unmapped class");
}

// ── 7j. aux_id (full slug and basename) resolves to its pack ──────────────

{
  const index = buildManagerPackIndex(
    {
      node_packs: {
        "https://github.com/kijai/ComfyUI-KJNodes": {
          title: "ComfyUI-KJNodes",
          repository: "https://github.com/kijai/ComfyUI-KJNodes",
        },
      },
    },
    {}
  );
  for (const aux of ["kijai/ComfyUI-KJNodes", "ComfyUI-KJNodes"]) {
    const plan = resolveNodeInstall({ name: "KJNodes", aux_id: aux, state: "missing" }, index);
    assert.equal(plan.kind, "cnr", "aux id " + aux + " queues via Manager");
    assert.equal(plan.pack.name, "ComfyUI-KJNodes");
  }
  section("7j. aux_id (full slug and basename) resolves to its Manager pack");
}

// ── 7k. Pure-CNR pack installs via Manager queue (no git_url 403 gate) ────

{
  const { net } = await mountLibrary();
  const index = buildManagerPackIndex(
    {
      node_packs: {
        donutnodes: {
          title: "ComfyUI-DonutNodes",
          version: "1.2.3",
          install_type: "cnr",
          state: "not-installed",
        },
      },
    },
    { donutnodes: [["DonutLoaderClass"], { title_aux: "ComfyUI-DonutNodes" }] }
  );
  const plan = resolveNodeInstall(
    { name: "ComfyUI-DonutNodes", cnr_id: "donutnodes", classes: ["DonutLoaderClass"], state: "missing" },
    index
  );
  assert.equal(plan.kind, "cnr", "versioned CNR record queues instead of git_url");

  const deps = {
    status: "ok",
    models: [],
    custom_nodes: [
      {
        name: "ComfyUI-DonutNodes",
        cnr_id: "donutnodes",
        state: "missing",
        repository_url: "",
        classes: ["DonutLoaderClass"],
      },
    ],
    summary: { ready: false, attention: 1 },
  };
  const depsSection = renderDependencySection({}, deps, null, { apiBase: "/comfymodal", managerPacks: index });
  assert.equal(findByTestId(depsSection, "dependency-node-install-now").length, 1);
  assert.equal(findByTestId(depsSection, "dependency-node-no-target").length, 0);
  findOneByTestId(depsSection, "dependency-node-install-now").click();
  await settle(net.inflight);

  const queue = net.calls.filter((c) => c.method === "POST" && c.url.indexOf("/manager/queue/install") !== -1);
  assert.equal(queue.length, 1);
  assert.equal(queue[0].body.id, "donutnodes");
  assert.equal(queue[0].body.version, "1.2.3");
  assert.equal(queue[0].body.selected_version, "latest");
  assert.equal(queue[0].body.channel, "default");
  const start = net.calls.filter((c) => c.method === "POST" && c.url.indexOf("/manager/queue/start") !== -1);
  assert.equal(start.length, 1);
  assert.equal(
    net.calls.filter((c) => c.url.indexOf("/customnode/install/git_url") !== -1).length,
    0,
    "CNR install never touches the git_url 403 gate"
  );
  section("7k. pure-CNR pack installs via Manager queue (no git_url 403 gate)");
}

// ── 7l. Manager 403 on the CNR queue is surfaced truthfully ──────────────

{
  installFetch((call) => {
    if (call.method === "POST" && call.url.indexOf("/manager/queue/install") !== -1) {
      return { __fail: true, __status: 403, __message: "not allowed" };
    }
    return defaultRouter(call);
  });
  const res = await performManagerInstall({ kind: "cnr", pack: { cnrId: "x", version: "1", files: [] } });
  assert.equal(res.ok, false);
  assert.ok(res.message.indexOf("403") !== -1, "403 surfaced");
  section("7l. Manager 403 on the CNR queue is surfaced truthfully");
}

// ── 7l-b. Blank/unknown-version Manager pack never falls back to git_url ──
//
// Regression for the Manager 403 failure: a pack successfully resolved from
// the Manager catalog (cnr/aux/class/pattern) has a valid record but may carry
// blank or "unknown" version metadata. It must still install through Manager's
// queue with safe defaults — never the security-gated git_url route that 403s
// when git installs are disabled.

{
  const { net } = await mountLibrary();
  const index = buildManagerPackIndex(
    {
      channel: "default",
      node_packs: {
        donutnodes: {
          title: "ComfyUI-DonutNodes",
          install_type: "cnr",
          state: "not-installed",
          // No version / selected_version at all (blank metadata).
        },
        nightlypack: {
          title: "NightlyPack",
          version: "unknown",
          selected_version: "nightly",
          install_type: "cnr",
        },
      },
    },
    { donutnodes: [["DonutLoaderClass"], { title_aux: "ComfyUI-DonutNodes" }] }
  );

  const blank = resolveNodeInstall(
    { name: "ComfyUI-DonutNodes", cnr_id: "donutnodes", classes: ["DonutLoaderClass"], state: "missing" },
    index
  );
  assert.equal(blank.kind, "cnr", "blank-version Manager record queues CNR");
  const nightly = resolveNodeInstall({ name: "NightlyPack", cnr_id: "nightlypack", state: "missing" }, index);
  assert.equal(nightly.kind, "cnr", "unknown/nightly Manager record still queues CNR");

  const deps = {
    status: "ok",
    models: [],
    custom_nodes: [
      { name: "ComfyUI-DonutNodes", cnr_id: "donutnodes", state: "missing", repository_url: "", classes: ["DonutLoaderClass"] },
    ],
    summary: { ready: false, attention: 1 },
  };
  const depsSection = renderDependencySection({}, deps, null, { apiBase: "/comfymodal", managerPacks: index });
  findOneByTestId(depsSection, "dependency-node-install-now").click();
  await settle(net.inflight);
  const queue = net.calls.filter((c) => c.method === "POST" && c.url.indexOf("/manager/queue/install") !== -1);
  assert.equal(queue.length, 1, "blank-version matched pack queues once");
  assert.equal(queue[0].body.id, "donutnodes");
  assert.equal(queue[0].body.version, "unknown", "safe default version");
  assert.equal(queue[0].body.selected_version, "latest", "safe default selected_version");
  assert.equal(queue[0].body.channel, "default");
  assert.equal(
    net.calls.filter((c) => c.url.indexOf("/customnode/install/git_url") !== -1).length,
    0,
    "blank/unknown version never routes through the git_url 403 gate"
  );
  section("7l-b. blank/unknown-version Manager pack queues instead of git_url");
}

// ── 7m. Manager save_path default + role/type matching ───────────────────

{
  assert.equal(managerModelFolder("vae"), "vae");
  assert.equal(managerModelFolder("clip"), "text_encoders");
  assert.equal(managerModelFolder("unet"), "diffusion_models");
  assert.equal(normalizeManagerSavePath("default", "lora"), "loras");
  assert.equal(normalizeManagerSavePath("", "checkpoints"), "checkpoints");
  assert.equal(normalizeManagerSavePath("custom/sub", "vae"), "custom/sub");
  const map = { "foo.safetensors": { url: "u", savePath: "checkpoints", type: "checkpoints" } };
  assert.equal(
    matchManagerModel({ filename: "foo.safetensors", role: "lora" }, map),
    null,
    "cross-type basename rejected"
  );
  assert.ok(matchManagerModel({ filename: "foo.safetensors", role: "checkpoint" }, map), "same-type match kept");
  section("7m. Manager save_path default + role/type matching");
}

// ── 7n. Manager installed dict alone never proves classes loaded ──────────

{
  const index = buildManagerPackIndex({ node_packs: {} }, {});
  const deps = {
    status: "ok",
    models: [],
    custom_nodes: [
      { name: "PackX", cnr_id: "packx", state: "missing", repository_url: "", classes: ["PackX"] },
    ],
    summary: { ready: false, attention: 1 },
  };

  // Disabled Manager record, no install plan: the row stays missing and
  // explains the package is present but its classes are not loaded. It must
  // never render as "Installed".
  const disabled = renderDependencySection({}, deps, null, {
    apiBase: "/comfymodal",
    managerPacks: index,
    managerInstalled: [{ module: "packx_dir", cnr_id: "packx", aux_id: "", enabled: false, ver: "1" }],
  });
  assert.equal(findByTestId(disabled, "dependency-node-install-now").length, 0, "no plan → no install action");
  assert.equal(findByTestId(disabled, "dependency-node-manager-installed").length, 0, "Manager dict is not installed proof");
  const disabledNote = findOneByTestId(disabled, "dependency-node-manager-stale").textContent;
  assert.ok(disabledNote.indexOf("disabled") !== -1, "disabled truth preserved");
  assert.ok(disabledNote.indexOf("not loaded") !== -1, "classes-not-loaded truth");
  assert.ok(findOneByTestId(disabled, "dependency-node-row").textContent.indexOf("Missing") !== -1, "row stays missing");

  // Enabled Manager record, still no install plan: same missing truth.
  const enabled = renderDependencySection({}, deps, null, {
    apiBase: "/comfymodal",
    managerPacks: index,
    managerInstalled: [{ module: "packx_dir", cnr_id: "packx", aux_id: "", enabled: true, ver: "1" }],
  });
  assert.ok(findOneByTestId(enabled, "dependency-node-manager-stale").textContent.indexOf("not loaded") !== -1);
  assert.equal(findByTestId(enabled, "dependency-node-manager-installed").length, 0);
  assert.equal(findByTestId(enabled, "dependency-node-install-now").length, 0, "no target → no install action");

  // Manager record + resolvable plan: the installed dict must NOT suppress the
  // single Install now action; the explanatory note stays alongside it.
  const planIndex = buildManagerPackIndex(
    { node_packs: { packx: { title: "PackX", repository: "https://github.com/ex/PackX" } } },
    {}
  );
  const withPlan = renderDependencySection({}, deps, null, {
    apiBase: "/comfymodal",
    managerPacks: planIndex,
    managerInstalled: [{ module: "packx_dir", cnr_id: "packx", aux_id: "", enabled: true, ver: "1" }],
  });
  assert.equal(findByTestId(withPlan, "dependency-node-install-now").length, 1, "plan keeps the install action");
  assert.ok(findOneByTestId(withPlan, "dependency-node-manager-stale").textContent.indexOf("not loaded") !== -1);
  assert.ok(findOneByTestId(withPlan, "dependency-node-row").textContent.indexOf("Missing") !== -1, "still missing");

  // Explicit loaded-class proof is the only thing that reports the classes
  // loaded; it hides the install action.
  const loaded = renderDependencySection({}, deps, null, {
    apiBase: "/comfymodal",
    managerPacks: index,
    loadedClasses: ["PackX"],
  });
  assert.ok(findOneByTestId(loaded, "dependency-node-loaded").textContent.indexOf("loaded") !== -1);
  assert.equal(findByTestId(loaded, "dependency-node-install-now").length, 0, "loaded classes hide the install action");

  const auxDeps = {
    status: "ok",
    models: [],
    custom_nodes: [
      { name: "KJ", aux_id: "kijai/ComfyUI-KJNodes", state: "missing", repository_url: "", classes: [] },
    ],
    summary: { ready: false, attention: 1 },
  };
  const aux = renderDependencySection({}, auxDeps, null, {
    apiBase: "/comfymodal",
    managerPacks: index,
    managerInstalled: [{ module: "ComfyUI-KJNodes", cnr_id: "", aux_id: "ComfyUI-KJNodes", enabled: true }],
  });
  const auxNote = findOneByTestId(aux, "dependency-node-manager-stale").textContent;
  assert.equal(auxNote.indexOf("disabled"), -1, "enabled aux install is not reported disabled");
  assert.ok(auxNote.indexOf("not loaded") !== -1, "aux install still needs class-loaded proof");
  section("7n. Manager installed dict alone never proves classes loaded");
}

// ── 7o. Newly-surfaced UI-only classes resolve across CNR/aux/class/pattern ─
// The backend now unions full UI-graph node types into the dependency report
// (UI-only packs absent from the executable prompt). Each surfaced row must
// still resolve through the existing Manager index: direct CNR id, aux
// repo basename, grouped CNR pack, class mapping, and nodename_pattern — one
// "Install now" per pack, all via the CNR queue (never git_url).

{
  const { net } = await mountLibrary();
  const index = buildManagerPackIndex(
    {
      channel: "default",
      node_packs: {
        krea2_identity_edit: {
          title: "Krea 2 Identity Edit", version: "1.0.0", install_type: "cnr",
          repository: "https://github.com/krea/ComfyUI-IdentityEdit",
        },
        "https://github.com/Derfuu/ComfyUI_Derfuu_ComfyUI_Modded_Nodes": {
          title: "Derfuu Modded Nodes", version: "2.0.0", install_type: "cnr",
          repository: "https://github.com/Derfuu/ComfyUI_Derfuu_ComfyUI_Modded_Nodes",
        },
        bleh: {
          title: "ComfyUI-bleh", version: "1.1.0", install_type: "cnr",
          repository: "https://github.com/bleh/ComfyUI-bleh",
        },
        impact_subpack: {
          title: "ComfyUI Impact Subpack", version: "1.5.0", install_type: "cnr",
          repository: "https://github.com/ltdrdata/ComfyUI-Impact-Subpack",
        },
        patternpack: {
          title: "Seed Variance Enhancer", version: "3.0.0", install_type: "cnr",
          repository: "https://github.com/ex/SeedVariance",
        },
      },
    },
    {
      impact_subpack: [["ImpactSubpackNode"], {}],
      patternpack: [["UnmappedClass"], { nodename_pattern: "^SeedVarianceEnhancer$" }],
    }
  );

  const plans = [
    resolveNodeInstall({ cnr_id: "krea2_identity_edit", classes: ["Krea2IdentityEdit"], state: "missing" }, index),
    resolveNodeInstall({ aux_id: "Derfuu/ComfyUI_Derfuu_ComfyUI_Modded_Nodes", classes: ["DerfuuNode"], state: "missing" }, index),
    resolveNodeInstall({ cnr_id: "bleh", classes: ["BlehNodeA", "BlehNodeB"], state: "missing" }, index),
    resolveNodeInstall({ classes: ["ImpactSubpackNode"], state: "missing" }, index),
    resolveNodeInstall({ classes: ["SeedVarianceEnhancer"], state: "missing" }, index),
  ];
  for (const plan of plans) assert.equal(plan.kind, "cnr", "known Manager record queues CNR: " + plan.name);

  const deps = {
    status: "ok",
    models: [],
    custom_nodes: [
      { name: "Krea 2 Identity Edit", cnr_id: "krea2_identity_edit", state: "missing", repository_url: "", classes: ["Krea2IdentityEdit"] },
      { name: "Derfuu Modded Nodes", aux_id: "Derfuu/ComfyUI_Derfuu_ComfyUI_Modded_Nodes", state: "missing", repository_url: "", classes: ["DerfuuNode"] },
      { name: "ComfyUI-bleh", cnr_id: "bleh", state: "missing", repository_url: "", classes: ["BlehNodeA", "BlehNodeB"] },
      { name: "ComfyUI Impact Subpack", state: "missing", repository_url: "", classes: ["ImpactSubpackNode"] },
      { name: "Seed Variance Enhancer", state: "missing", repository_url: "", classes: ["SeedVarianceEnhancer"] },
    ],
    summary: { ready: false, attention: 5 },
  };
  const depsSection = renderDependencySection({}, deps, null, { apiBase: "/comfymodal", managerPacks: index });
  const rows = findByTestId(depsSection, "dependency-node-row");
  assert.equal(rows.length, 5, "one row per surfaced pack");
  for (const row of rows) {
    assert.equal(
      findByTestId(row, "dependency-node-install-now").length,
      1,
      "exactly one Install now for " + row.getAttribute("data-node-name")
    );
  }

  // The grouped CNR pack must queue once, never fall through to git_url.
  const blehRow = rows.find((r) => r.getAttribute("data-node-name") === "ComfyUI-bleh");
  findOneByTestId(blehRow, "dependency-node-install-now").click();
  await settle(net.inflight);
  const queue = net.calls.filter((c) => c.method === "POST" && c.url.indexOf("/manager/queue/install") !== -1);
  assert.equal(queue.length, 1, "grouped pack queues exactly once");
  assert.equal(queue[0].body.id, "bleh");
  assert.equal(
    net.calls.filter((c) => c.url.indexOf("/customnode/install/git_url") !== -1).length,
    0,
    "known Manager packs never touch the git_url gate"
  );
  section("7o. UI-only classes resolve CNR/aux/class/pattern with one queue install each");
}

// ── 16. Lazy workflow-detail Manager context is wired, never auto-installs ─

{
  // Only the workflow-detail host loads the Manager catalog, lazily, when a
  // missing item lacks a source; it reuses the shared pure builders.
  assert.ok(workflowsSource.includes("maybeLoadManagerContext"), "workflow detail owns the lazy Manager load");
  assert.ok(workflowsSource.includes("_depsNeedManager"), "load is gated on missing items without a source");
  for (const helper of ["getManagerVersion", "getManagerPackList", "getManagerMappings", "getManagerModels", "listManagerInstalled"]) {
    assert.ok(workflowsSource.includes(helper), "workflow detail reuses backend helper " + helper);
  }
  assert.ok(workflowsSource.includes("buildManagerPackIndex"), "pack index reuse");
  assert.ok(workflowsSource.includes("buildManagerModelIndex"), "model index reuse");
  assert.ok(workflowsSource.includes("parseManagerInstalled"), "installed-dict parse reuse");
  assert.equal(workflowsSource.includes("managerReboot"), false, "detail surface never reboots");
  assert.equal(workflowsSource.includes("/manager/reboot"), false, "detail surface never posts reboot");
  // The ordinary Model Library module must not fetch Manager itself.
  assert.equal(librarySource.includes("getManagerVersion"), false, "Model Library loads no Manager context");
  assert.equal(librarySource.includes("getManagerPackList"), false, "Model Library loads no Manager catalog");
  // Rows still perform installs only through the shared click-gated primitive.
  assert.ok(
    librarySource.indexOf("performManagerInstall(installPlan)") !== -1,
    "shared row performs the resolved plan on explicit click"
  );
  section("16. Workflow-detail Manager context is lazy, reused, and click-only");
}

// ── 17. buildManagerModelIndex: exact filename + basename + normalized save ─

{
  const index = buildManagerModelIndex([
    { filename: "sub/dir/foo.safetensors", url: "https://example.com/foo", save_path: "default", type: "lora", name: "Foo" },
    { filename: "bar.safetensors", url: "https://example.com/bar", save_path: "custom/sub", type: "vae" },
  ]);
  assert.equal(index["sub/dir/foo.safetensors"].savePath, "loras", "default save_path normalized");
  assert.ok(index["foo.safetensors"], "basename keyed");
  assert.equal(index["bar.safetensors"].savePath, "custom/sub", "explicit save_path preserved");
  assert.equal(matchManagerModel({ filename: "sub/dir/foo.safetensors", role: "lora" }, index).url, "https://example.com/foo");
  section("17. buildManagerModelIndex keys exact + basename with normalized save_path");
}

// ── 18. parseManagerInstalled: dict shape + disabled truth preserved ───────

{
  const records = parseManagerInstalled({
    pack_enabled: { ver: "1.0", cnr_id: "packa", aux_id: "", enabled: true },
    pack_disabled: { ver: "2.0", cnr_id: "packb", aux_id: "owner/repo", enabled: "false" },
    junk: "not-an-object",
  });
  assert.equal(records.length, 2, "only object values become records");
  const disabled = records.find((r) => r.module === "pack_disabled");
  assert.equal(disabled.enabled, false, "disabled stays false");
  assert.equal(disabled.cnr_id, "packb");
  const enabled = records.find((r) => r.module === "pack_enabled");
  assert.equal(enabled.enabled, true);
  assert.deepEqual(parseManagerInstalled(null), []);
  assert.deepEqual(parseManagerInstalled([{ module: "raw", enabled: false }]), [{ module: "raw", enabled: false }]);
  section("18. parseManagerInstalled normalizes the dict and preserves disabled truth");
}

// ── 19. Remote model-volume overlay: basename + role alias, size authority ──

{
  // Normalization flattens the folder-keyed /comfymodal/models payload and
  // coerces missing/junk sizes to 0 (remote size is the availability signal).
  const inventory = normalizeRemoteModelInventory({
    checkpoints: [
      {
        name: "krea2_turbo_bf16.safetensors",
        size: 26283332608,
        folder: "unet",
        local_placeholder: { is_placeholder: true, size: 0, exists: true },
      },
      { name: "zero.safetensors", size: 0, folder: "unet" },
      "not-an-object",
    ],
    loras: "not-a-list",
    vae: [{ name: "", size: 5 }],
  });
  assert.equal(inventory.length, 2, "only well-formed named entries survive");
  assert.equal(inventory[0].size, 26283332608);
  assert.equal(inventory[0].folder, "unet");
  assert.equal(inventory[1].size, 0, "zero/junk size coerced to 0");
  assert.deepEqual(normalizeRemoteModelInventory(null), []);

  const index = buildRemoteModelIndex(inventory);
  assert.ok(index.get("krea2_turbo_bf16.safetensors"), "basename keyed, lowercased");

  const deps = {
    status: "ok",
    models: [
      {
        key: "unet|krea2_turbo_bf16.safetensors",
        role: "unet",
        filename: "krea2_turbo_bf16.safetensors",
        state: "missing",
        folder: "diffusion_models",
        installed: false,
        local_placeholder: {
          is_placeholder: true,
          size: 0,
          exists: true,
          local_path: "C:/models/unet/krea2_turbo_bf16.safetensors",
        },
      },
      {
        key: "unet|zero.safetensors",
        role: "unet",
        filename: "zero.safetensors",
        state: "missing",
        folder: "unet",
        installed: false,
      },
      {
        key: "lora|absent.safetensors",
        role: "lora",
        filename: "absent.safetensors",
        state: "missing",
        folder: "loras",
        installed: false,
      },
    ],
    custom_nodes: [{ name: "SomeCustomClass", state: "installed" }],
    summary: { installed: 1, missing: 3, wrong_version: 0, unknown: 0, attention: 3, ready: false },
  };

  // Role alias: the dependency records diffusion_models while the remote
  // volume holds the same basename under unet — one identity for the unet role.
  assert.ok(matchRemoteModel(deps.models[0], index), "role alias resolves folder mismatch");
  assert.equal(matchRemoteModel(deps.models[2], index), null, "no remote entry matches");

  const overlaid = overlayDependencyModels(deps, index);
  assert.notEqual(overlaid, deps, "overlay returns a copy");
  assert.equal(deps.models[0].state, "missing", "input report is never mutated");
  const krea = overlaid.models.find((m) => m.filename === "krea2_turbo_bf16.safetensors");
  assert.equal(krea.state, "installed", "remote nonzero size upgrades the placeholder row");
  assert.equal(krea.remote_available, true);
  assert.equal(krea.remote_model.size, 26283332608);
  assert.equal(krea.remote_model.folder, "unet");
  assert.equal(krea.local_placeholder.is_placeholder, true, "local placeholder preserved as secondary");
  const zero = overlaid.models.find((m) => m.filename === "zero.safetensors");
  assert.equal(zero.state, "missing", "remote size 0 stays missing");
  assert.equal(zero.remote_available, false);
  assert.equal(
    overlaid.models.find((m) => m.filename === "absent.safetensors").state,
    "missing",
    "no remote entry stays missing"
  );
  // Summary recomputed from overlay state; the Download-all count derives from it.
  assert.equal(overlaid.summary.installed, 2, "installed = custom node + remote-available model");
  assert.equal(overlaid.summary.missing, 2);
  assert.equal(overlaid.summary.attention, 2);
  assert.equal(overlaid.summary.ready, false);

  // wrong_version keeps its compatibility signal even when remote is present.
  const wrong = overlayDependencyModel(
    { filename: "krea2_turbo_bf16.safetensors", role: "unet", state: "wrong_version", folder: "unet" },
    index
  );
  assert.equal(wrong.state, "wrong_version", "remote availability never masks a wrong version");
  assert.equal(wrong.remote_available, true);

  // Local placeholder detail comes from the remote annotation when the report
  // row carries none (the real dependency report has no local fields).
  const noLocal = overlayDependencyModel(
    { filename: "krea2_turbo_bf16.safetensors", role: "unet", state: "missing", folder: "unet" },
    index
  );
  assert.equal(noLocal.local_placeholder.size, 0, "remote local_placeholder surfaced");

  // A failed remote read keeps local truth: no index is a no-op.
  assert.equal(overlayDependencyModels(deps, null), deps, "null index preserves local truth");
  assert.equal(overlayDependencyModel(deps.models[0], null).state, "missing");

  // The overlaid row renders Installed with remote/local secondary detail and
  // no download/install action.
  const depSection = renderDependencySection({}, overlaid, null, { apiBase: "/comfymodal" });
  const rows = findByTestId(depSection, "dependency-model-row");
  const kreaRow = rows.find(
    (r) => r.getAttribute("data-model-key") === "unet|krea2_turbo_bf16.safetensors"
  );
  assert.ok(kreaRow, "overlaid row rendered");
  assert.equal(findOneByTestId(kreaRow, "dependency-model-state").textContent, "Installed");
  const remoteDetail = findOneByTestId(kreaRow, "dependency-model-remote");
  assert.ok(remoteDetail.textContent.indexOf("remote") !== -1, "remote size shown as secondary info");
  assert.ok(
    remoteDetail.textContent.indexOf("local placeholder") !== -1,
    "local placeholder shown as secondary info"
  );
  assert.equal(findByTestId(kreaRow, "dependency-model-queue").length, 0, "no download action");
  assert.equal(findByTestId(kreaRow, "dependency-model-install-now").length, 0);

  // The read-only API helper parses safely and fails soft to null.
  {
    const okNet = installFetch(() => ({
      checkpoints: [{ name: "krea2_turbo_bf16.safetensors", size: 9, folder: "unet" }],
    }));
    const ok = await listRemoteModels("/comfymodal");
    assert.equal(ok.length, 1, "successful remote read normalized");
    assert.ok(okNet.calls.every((c) => c.method === "GET"), "remote read is read-only");
    assert.equal(okNet.calls[0].url, "/comfymodal/models", "reads the remote inventory route");

    installFetch(() => ({ __fail: true, __status: 503, __message: "remote unavailable" }));
    assert.equal(await listRemoteModels("/comfymodal"), null, "remote error falls back to null");
  }

  // The helper never routes availability through object_info/sync/runtime.
  assert.ok(backendApiSource.indexOf('"/models"') !== -1, "listRemoteModels reads GET /models");
  for (const banned of ['"/object_info"', '"/sync/status"', '"/runtime/state"']) {
    assert.equal(backendApiSource.indexOf(banned), -1, "remote availability never consults " + banned);
  }
  section("19. Remote model-volume overlay: basename + role alias, nonzero size is authority");
}

console.log("ALL H7 MODEL LIBRARY PARITY UNIT TESTS PASSED");
