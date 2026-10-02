// Phase I9 — Studio hash routing unit tests (standalone).
//
// Deterministic Node coverage for web/studio-routing.js (pure parse /
// serialize / history-decision helpers) plus narrow source pins that keep
// the routing contract truthful in its consumers:
//   - frozen hash format #comfymodal=<page>[&focus=<id>]
//   - canonical five pages only; everything else fails soft
//   - malformed percent encoding never throws
//   - exactly one focus value; unknown extra params ignored
//   - serialize/parse round-trip on identifier values
//   - route-history decision matrix (seed / push / replace / none)
//   - routing isolated to studio-routing.js + the two shell-lane files;
//     page modules stay routing-free; no router library anywhere
//
// NOT registered during the parallel I5/I9 window (single-writer rule);
// registered in tests/run_studio_tests.py NODE_UNIT_FILES by convergence
// lane I9A (2026-08-25).
// Run: node tests/studio_phase_i9_routing_unit.mjs

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const WEB = path.join(ROOT, "web");
const readWeb = (name) => fs.readFileSync(path.join(WEB, name), "utf8");

function section(name) {
  console.log("PASS: " + name);
}

import { parseStudioHash, serializeStudioHash, routeHistoryAction, ROUTE_PAGES } from "../web/studio-routing.js";

// ── 1. Canonical pages ────────────────────────────────────────────────────

assert.deepEqual(ROUTE_PAGES, ["playground", "history", "workflows", "backend", "settings"]);
for (const page of ROUTE_PAGES) {
  const r = parseStudioHash("#comfymodal=" + page);
  assert.equal(r.matched, true, page);
  assert.equal(r.page, page);
  assert.equal(r.focus, null);
}
section("canonical five pages parse without focus");

// ── 2. Focus parsing ──────────────────────────────────────────────────────

assert.deepEqual(parseStudioHash("#comfymodal=history&focus=gen_x"), {
  matched: true, page: "history", focus: "gen_x",
});
assert.deepEqual(parseStudioHash("comfymodal=workflows&focus=wf_x"), {
  matched: true, page: "workflows", focus: "wf_x",
});
assert.deepEqual(parseStudioHash("#comfymodal=backend&focus=deployment"), {
  matched: true, page: "backend", focus: "deployment",
});
// Encoded focus decodes to the identifier.
assert.equal(parseStudioHash("#comfymodal=settings&focus=my%20section").focus, "my section");
// Empty focus value → treated as absent.
assert.equal(parseStudioHash("#comfymodal=history&focus=").focus, null);
// Focus segment without "=" is ignored; unknown extra params ignored.
assert.equal(parseStudioHash("#comfymodal=history&focus").focus, null);
const extras = parseStudioHash("#comfymodal=playground&foo=1&focus=a&bar=2");
assert.equal(extras.matched, true);
assert.equal(extras.page, "playground");
assert.equal(extras.focus, "a");
// Exactly ONE focus: the first wins.
assert.equal(parseStudioHash("#comfymodal=history&focus=one&focus=two").focus, "one");
section("optional single focus parses; extra params ignored");

// ── 3. Fail-soft inputs (never throw) ─────────────────────────────────────

for (const bad of [
  "",
  "#",
  "#dashboard",
  "#other=1",
  "comfymodal",
  "comfymodal=",
  "#comfymodal",
  "#comfymodal=bogus",
  "#COMFYMODAL=history",           // case-sensitive canonical ids
  "#prefix&comfymodal=history",    // head segment must carry the key
  "#comfymodal=history/../../etc",
]) {
  const r = parseStudioHash(bad);
  assert.equal(r.matched, false, JSON.stringify(bad));
}
// Malformed percent encoding must never throw…
assert.doesNotThrow(() => parseStudioHash("#comfymodal=%ZZ"));
assert.doesNotThrow(() => parseStudioHash("#comfymodal=history&focus=%E0%A4%A"));
// …and degrades truthfully: unusable page drops the whole route, unusable
// focus keeps the page route.
assert.equal(parseStudioHash("#comfymodal=%ZZ").matched, false);
const malformedFocus = parseStudioHash("#comfymodal=history&focus=%E0%A4%A");
assert.equal(malformedFocus.matched, true);
assert.equal(malformedFocus.page, "history");
assert.equal(malformedFocus.focus, null);
assert.equal(parseStudioHash(null).matched, false);
assert.equal(parseStudioHash(undefined).matched, false);
assert.equal(parseStudioHash(42).matched, false);
section("unrelated/unknown/malformed hashes fail soft without throwing");

// ── 4. Serialization ──────────────────────────────────────────────────────

assert.equal(serializeStudioHash({ page: "history" }), "#comfymodal=history");
assert.equal(serializeStudioHash({ page: "history", focus: null }), "#comfymodal=history");
assert.equal(serializeStudioHash({ page: "history", focus: "" }), "#comfymodal=history");
assert.equal(serializeStudioHash({ page: "settings", focus: "outputs" }), "#comfymodal=settings&focus=outputs");
assert.equal(serializeStudioHash({ page: "nope", focus: "x" }), "");
assert.equal(serializeStudioHash(null), "");
assert.equal(serializeStudioHash({}), "");
assert.equal(serializeStudioHash({ page: "history", focus: "a b/c?d&e#f" }), "#comfymodal=history&focus=" + encodeURIComponent("a b/c?d&e#f"));
section("serialization is canonical and percent-encodes focus");

// ── 5. Round-trip ─────────────────────────────────────────────────────────

const SAMPLE_IDS = [
  "gen_ok", "exp_completed", "deployment", "outputs",
  "id with spaces", "slashed/id", "q?mark", "amp&ersand", "eq=sign",
  "pct%2520double", "unicode-gén-id", "hash#tag",
];
for (const page of ROUTE_PAGES) {
  const bare = serializeStudioHash({ page });
  assert.deepEqual(parseStudioHash(bare), { matched: true, page, focus: null });
  for (const id of SAMPLE_IDS) {
    const hash = serializeStudioHash({ page, focus: id });
    const back = parseStudioHash(hash);
    assert.equal(back.matched, true, hash);
    assert.equal(back.page, page, hash);
    assert.equal(back.focus, id, hash);
  }
}
section("serialize→parse round-trips every page × identifier corpus");

// ── 6. Route-history decision matrix ──────────────────────────────────────

const P = (page, focus = null) => ({ page, focus });
assert.equal(routeHistoryAction(null, P("history")), "replace"); // seed before first push
assert.equal(routeHistoryAction(P("playground"), P("history")), "push"); // page change
assert.equal(routeHistoryAction(P("history"), P("workflows")), "push");
assert.equal(routeHistoryAction(P("history"), P("history")), "none"); // no-op re-render
assert.equal(routeHistoryAction(P("history"), P("history", "gen_x")), "replace"); // selection identity
assert.equal(routeHistoryAction(P("history", "gen_x"), P("history", "gen_y")), "replace");
assert.equal(routeHistoryAction(P("history", "gen_x"), P("history", "gen_x")), "none");
assert.equal(routeHistoryAction(P("history", "gen_x"), P("history")), "replace"); // focus dropped
assert.equal(routeHistoryAction(P("history"), null), "none"); // unrelated host hash: hands off
assert.equal(routeHistoryAction(P("history"), P("bogus")), "none");
assert.equal(routeHistoryAction(null, null), "none");
section("route-history decision: seed/push/replace/none matrix exact");

// ── 7. Consumer wiring pins (source IS the contract) ─────────────────────

const shellSource = readWeb("studio-shell.js");
const testingSource = readWeb("modal-testing.js");

// Shell lane imports the pure helpers; parser feeds the open/reopen paths.
assert.ok(shellSource.includes('from "./studio-routing.js"'), "shell imports studio-routing.js");
assert.ok(testingSource.includes('from "./studio-routing.js"'), "modal-testing imports studio-routing.js");
assert.ok(shellSource.includes("parseStudioHash"), "shell parses Back/Forward hashes");
assert.ok(shellSource.includes("serializeStudioHash"), "shell serializes managed routes");
assert.ok(shellSource.includes("routeHistoryAction"), "shell uses the decision helper");
assert.ok(shellSource.includes('requestHistoryRecordFocus') && shellSource.includes('from "./studio-history-v2.js"'),
  "history focus rides the existing H13 seam import");

// Single authority: nav aria-current still derives from state.activePage.
assert.ok(shellSource.includes("aria-current") && shellSource.includes("state.activePage"),
  "aria-current remains derived from state.activePage");
assert.equal((shellSource.match(/addEventListener\("hashchange"/g) || []).length, 1,
  "exactly one hashchange listener, owned by the shell");
assert.ok(shellSource.includes('removeEventListener("hashchange"'), "destroy() removes the listener");

// Alias opener precedence documented at the mount site.
assert.ok(
  testingSource.includes("ALIAS_PAGE_MAP[tabName]") && testingSource.includes("initialRoute"),
  "explicit alias intent is passed as the shell initialRoute (wins over stale hash)"
);
assert.ok(testingSource.includes("parseStudioHash"), "reopen path honors a present Studio hash");

// Page modules stay routing-free.
const PAGE_FILES = [
  "studio-playground.js",
  "studio-playground-state.js",
  "studio-history-v2.js",
  "studio-history-v2-detail.js",
  "studio-history-v2-experiment.js",
  "history-v2-view-state.js",
  "studio-workflows.js",
  "studio-backend.js",
  "studio-settings.js",
  "studio-ui.js",
];
for (const banned of ["pushState", "replaceState", "hashchange", "popstate", "location.hash"]) {
  for (const file of PAGE_FILES) {
    assert.equal(readWeb(file).includes(banned), false, `${file} must not contain ${banned}`);
  }
}

// No router library / routing dependency anywhere in web/.
for (const entry of fs.readdirSync(WEB)) {
  if (!entry.endsWith(".js")) continue;
  const src = fs.readFileSync(path.join(WEB, entry), "utf8");
  for (const lib of ['from "react-router', "from 'react-router", 'require("history"', 'from "history"', 'from "@reduxjs', "vuex", "wouter"]) {
    assert.equal(src.includes(lib), false, `${entry} must not reference router/state-library ${lib}`);
  }
}

// The routing helper itself stays dependency-free and DOM-free.
const routingSource = readWeb("studio-routing.js");
assert.equal((routingSource.match(/^import /gm) || []).length, 0, "studio-routing.js has zero imports");
for (const banned of ["document.", "window.", "localStorage", "fetch(", "innerHTML"]) {
  assert.equal(routingSource.includes(banned), false, `studio-routing.js must not use ${banned}`);
}
section("routing isolated to studio-routing.js + shell lane; consumers pinned");
console.log("phase-i9 routing unit complete");
