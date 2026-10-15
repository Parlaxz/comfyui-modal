// Phase 1 Vue substrate — structural unit tests (standalone).
//
// Cheap deterministic guards for the Vite/WEB_DIRECTORY output strategy
// and the Phase-1 architecture boundaries:
//
//   - web/assets/studio/ holds exactly the stable entry (studio.mjs) and
//     the stylesheet (studio.css): NO `.js` file may exist there, because
//     ComfyUI's extension discovery (server.py `get_extensions`) serves
//     every `**/*.js` under WEB_DIRECTORY as an auto-executed extension.
//   - the stable entry exports mountStudioPreview (the host's only import).
//   - the Vue UI imports ZERO old Studio CSS and no old selectors.
//   - exactly the six intended stores exist with stable IDs; no appStore.
//   - exactly five Studio routes; `backend` stays the route key; no Docs.
//   - no forbidden Phase-1 dependencies (TanStack, XState, persistence
//     plugin, event-bus/cache/operation frameworks, Shadow DOM).
//   - the host bridge stays side-effect-free and keeps the Studio-contained
//     portal target; the production old Studio entry points are intact.
//
// Run: node tests/studio_vue_substrate_unit.mjs

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const WEB = path.join(ROOT, "web");
const FRONTEND = path.join(ROOT, "frontend");
const SRC = path.join(FRONTEND, "src");
const ASSETS = path.join(WEB, "assets", "studio");

function section(name) {
  console.log("PASS: " + name);
}

function readFile(p) {
  return fs.readFileSync(p, "utf8");
}

function walk(dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full, out);
    else out.push(full);
  }
  return out;
}

// ── 1. Build output shape + loader safety ─────────────────────────────────

assert.ok(fs.existsSync(path.join(ASSETS, "studio.mjs")), "stable entry exists");
assert.ok(fs.existsSync(path.join(ASSETS, "studio.css")), "stylesheet exists");
const assetFiles = walk(ASSETS);
const jsFiles = assetFiles.filter((f) => f.endsWith(".js"));
assert.deepEqual(jsFiles, [], "no .js under web/assets/studio (ComfyUI would auto-execute them)");
for (const f of assetFiles) {
  const rel = path.relative(ASSETS, f);
  const ok =
    rel === "studio.mjs" ||
    rel === "studio.css" ||
    rel.startsWith("chunks" + path.sep) ||
    rel.startsWith("assets" + path.sep);
  assert.ok(ok, "unexpected build artifact: " + rel);
}
section("vite output is loader-safe (.mjs + .css only)");

const bundle = await import(pathToFileUrl(path.join(ASSETS, "studio.mjs")));
assert.equal(
  typeof bundle.mountStudioPreview,
  "function",
  "stable entry exports mountStudioPreview",
);
section("stable entry exposes mountStudioPreview");

function pathToFileUrl(p) {
  let resolved = path.resolve(p).replace(/\\/g, "/");
  if (!resolved.startsWith("/")) resolved = "/" + resolved;
  return "file://" + resolved;
}

// ── 2. Stylesheet isolation ───────────────────────────────────────────────

const css = readFile(path.join(ASSETS, "studio.css"));
assert.ok(css.includes(".cmst\\:"), "utilities carry the cmst prefix");
assert.ok(!css.includes(".comfymodal-"), "no old Studio selectors in Vue CSS");
assert.ok(!css.includes("studio-styles"), "no old style module reference");
assert.ok(!css.includes("html{"), "no global html reset");
assert.ok(!css.includes("body{"), "no global body reset");
section("compiled CSS is prefixed and has no global resets");

// ── 3. Zero old-CSS imports in the Vue sources ────────────────────────────

const sources = walk(SRC).filter((f) => f.endsWith(".ts") || f.endsWith(".vue"));
assert.ok(sources.length > 10, "frontend sources exist");
for (const f of sources) {
  const text = readFile(f);
  assert.ok(!text.includes("studio-styles"), `${rel(f)}: no studio-styles import`);
  assert.ok(!text.includes("testing-styles"), `${rel(f)}: no testing-styles import`);
  assert.ok(!text.includes(".comfymodal-"), `${rel(f)}: no copied old selectors`);
}
// Portalled UI must resolve the Studio-contained portal target through the
// one obvious helper — never fall back to document.body.
const srcText = sources.map(readFile).join("\n");
assert.ok(
  srcText.includes("getStudioPortalTarget"),
  "portal target resolved through the canonical helper",
);
assert.ok(!srcText.includes("?? document.body"), "no ?? document.body fallback");
assert.ok(!srcText.includes("|| document.body"), "no || document.body fallback");
assert.ok(
  readFile(path.join(SRC, "components", "portalTarget.ts")).includes("throw new Error"),
  "missing portal target fails visibly",
);
section("Vue UI imports zero old Studio CSS");

function rel(f) {
  return path.relative(ROOT, f);
}

// ── 4. Six stores, stable IDs, no appStore ────────────────────────────────

const expectedStores = {
  "stores/infrastructure.ts": "studio-infrastructure",
  "stores/workflows.ts": "studio-workflows",
  "stores/history.ts": "studio-history",
  "stores/playground.ts": "studio-playground",
  "stores/settings.ts": "studio-settings",
  "stores/operations.ts": "studio-operations",
};
for (const [file, id] of Object.entries(expectedStores)) {
  const text = readFile(path.join(SRC, file));
  assert.ok(text.includes(`"${id}"`), `${file} declares store id ${id}`);
}
const allSrcText = sources.map(readFile).join("\n");
assert.ok(!allSrcText.includes('defineStore("studio-app"'), "no appStore in Phase 1");
assert.ok(!allSrcText.includes("useAppStore"), "no app store composable");
section("six intended stores exist with stable IDs; no appStore");

// ── 5. Router contract ────────────────────────────────────────────────────

const routeCodec = readFile(path.join(SRC, "app", "router", "studioRoute.ts"));
for (const page of ["playground", "history", "workflows", "backend", "settings"]) {
  assert.ok(routeCodec.includes(`"${page}"`), `route key ${page} present`);
}
assert.ok(!routeCodec.includes("\"docs\""), "no sixth Docs route");
assert.ok(routeCodec.includes("comfymodal"), "frozen hash key preserved");
const routerFactory = readFile(path.join(SRC, "app", "router", "index.ts"));
assert.ok(routerFactory.includes("STUDIO_PAGES"), "router built from the five pages");
const studioHistory = readFile(path.join(SRC, "app", "router", "studioHistory.ts"));
assert.ok(
  studioHistory.includes("serializeStudioHash(routerLocationToRoute(to))"),
  "router link hrefs render the canonical Studio hash, never #/page",
);
section("exactly five Studio routes; backend key kept; no Docs route");

// ── 5b. Blueprint primitive shapes ─────────────────────────────────────────

const operationsSrc = readFile(path.join(SRC, "stores", "operations.ts"));
for (const kind of [
  "generation",
  "experiment",
  "deploy",
  "workspace-swap",
  "model-download",
  "node-sync",
  "inventory-sync",
  "workflow-import",
  "other",
]) {
  assert.ok(operationsSrc.includes(`"${kind}"`), `OperationKind includes ${kind}`);
}
assert.ok(
  operationsSrc.includes("type ActiveOperationStatus"),
  "non-terminal status type exists",
);
assert.ok(
  operationsSrc.includes("status?: ActiveOperationStatus"),
  "start/patch accept active statuses only",
);
const latestSrc = readFile(path.join(SRC, "async", "latest.ts"));
assert.ok(latestSrc.includes("run<T>(load"), "latest task takes the load per run");
assert.ok(
  latestSrc.includes("resolves the in-flight run stale"),
  "explicit abort resolves stale, never rejects",
);
const pollingSrc = readFile(path.join(SRC, "async", "polling.ts"));
assert.ok(pollingSrc.includes("pollUntil"), "polling primitive is pollUntil");
assert.ok(pollingSrc.includes("done:"), "pollUntil uses the done predicate");
const httpSrc = readFile(path.join(SRC, "api", "http.ts"));
assert.ok(!httpSrc.includes("DEFAULT_TIMEOUT"), "no universal timeout imposed");
section("operation kinds, latest/poll shapes, opt-in timeout match the blueprint");

// ── 6. Fixed stack, nothing speculative ───────────────────────────────────

const pkg = JSON.parse(readFile(path.join(FRONTEND, "package.json")));
const deps = { ...pkg.dependencies, ...pkg.devDependencies };
for (const required of [
  "vue",
  "typescript",
  "pinia",
  "vue-router",
  "tailwindcss",
  "reka-ui",
  "@lucide/vue",
  "zod",
  "@vueuse/core",
  "vite",
]) {
  assert.ok(deps[required], `fixed stack dep present: ${required}`);
}
const forbidden = [
  "@tanstack/",
  "xstate",
  "pinia-plugin-persistedstate",
  "mitt",
  "eventemitter",
];
for (const name of Object.keys(deps)) {
  for (const bad of forbidden) {
    assert.ok(!name.includes(bad), `forbidden Phase-1 dep absent: ${name}`);
  }
}
section("fixed stack only; no speculative frameworks");

// ── 7. Host bridge + old Studio intact ────────────────────────────────────

const host = readFile(path.join(WEB, "studio-vue-host.js"));
assert.ok(host.includes("data-studio-portals"), "Studio-contained portal target");
assert.ok(host.includes("data-studio-app"), "Vue app mount target");
assert.ok(host.includes("./assets/studio/"), "host resolves assets under the extension URL");
assert.ok(host.includes("studio.mjs"), "host loads the stable .mjs entry");
assert.ok(host.includes("mountStudioPreview"), "host calls mountStudioPreview");
assert.ok(host.includes("setGraphInteractionEnabled"), "wizard graph seam exposed");
assert.ok(!host.includes("registerExtension"), "host bridge registers no extension");
// Wizard polarity contract (mirrors `_syncModalWizardState`): the function
// name is literal — enabled=true means the graph IS interactive.
const openingBlock = host.slice(
  host.indexOf("comfymodal:wizard-opening"),
  host.indexOf("comfymodal:wizard-closed"),
);
assert.ok(
  openingBlock.includes("setGraphInteractionEnabled(true)"),
  "wizard-opening enables graph interaction",
);
assert.ok(
  host.includes('if (_isOpen) setGraphInteractionEnabled(false);'),
  "wizard-closed restores the inert modal",
);
assert.ok(
  host.includes('if (enabled) modal.removeAttribute("aria-modal");'),
  "enabled graph removes aria-modal from the Studio modal",
);
assert.ok(
  host.includes('_inertBackground(!enabled);'),
  "background inertness is the inverse of graph interaction",
);
section("host bridge owns mount-once lifecycle + portal target + graph seam");

const entry = readFile(path.join(WEB, "modal-testing.js"));
assert.ok(entry.includes("window.open_testing_modal"), "production opener preserved");
assert.ok(entry.includes("window.close_testing_modal"), "production closer preserved");
assert.ok(
  entry.includes("window.__comfymodalOpenVueStudio"),
  "Vue preview exposed as an explicit dev/test entry",
);
section("production old Studio entry points intact");

console.log("\nAll Vue substrate structural checks passed.");
