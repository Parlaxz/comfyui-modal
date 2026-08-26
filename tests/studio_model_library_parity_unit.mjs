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
  renderModelLibraryView,
  renderDependencySection,
} from "../web/studio-model-library.js";

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
        return { ok: false, status: payload.__status || 500, json: async () => ({ status: "error", message: payload.__message || "boom" }) };
      }
      return { ok: true, status: 200, json: async () => payload || {} };
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
  assert.ok(missingRow.textContent.indexOf("Not installed") !== -1);
  const installedRow = depRows[0];
  assert.ok(installedRow.textContent.indexOf("Installed") !== -1);
  assert.ok(installedRow.textContent.indexOf("/models/checkpoints/alpha.safetensors") !== -1);
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

// ── 7. Install requests require user action ──────────────────────────────

{
  const { net, container } = await mountLibrary();
  const before = net.calls.filter((c) => c.method === "POST").length;

  // Custom-node install request from a MISSING dependency row.
  const deps = renderDependencySection({}, DEPS_PAYLOAD, null, { apiBase: "/comfymodal" });
  const reqBtn = findOneByTestId(deps, "dependency-node-install-request");
  assert.equal(before, net.calls.filter((c) => c.method === "POST").length, "rendering alone posts nothing");
  reqBtn.click();
  await settle(net.inflight);
  const installReqs = net.calls.filter((c) => c.method === "POST" && c.url.indexOf("/custom-nodes/install-request") !== -1);
  assert.equal(installReqs.length, 1);
  assert.equal(installReqs[0].body.name, "MissingNode");
  assert.equal(installReqs[0].body.repo_url, "https://github.com/example/MissingNode");
  const note = findOneByTestId(deps, "dependency-node-install-note");
  assert.ok(note.textContent.indexOf("nothing was installed") !== -1, "approval-only disclosure shown");
  section("7a. Custom-node install request is click-gated and approval-only");

  // Model install request stays inside the detail dialog (existing flow).
  assert.ok(librarySource.indexOf("requestModelInstall") !== -1);
  assert.ok(librarySource.indexOf("Request download") !== -1);
  assert.ok(librarySource.indexOf("never fetched from here") !== -1, "approval-only copy retained");
  section("7b. Model download request remains the explicit detail-dialog flow");
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
    "install-request",
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

console.log("ALL H7 MODEL LIBRARY PARITY UNIT TESTS PASSED");
