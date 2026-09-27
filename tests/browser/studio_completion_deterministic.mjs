// Modal Studio — E2E Deterministic Self-Test
//
// Tests pure helper functions that do NOT launch a browser.
//
// Required public contracts (per spec review):
//   makeRunIdentity(label)       → { prefix, artifactDir }
//   pollUntil(fn, predicate, opts) → polls until predicate returns truthy
//   cleanupGeneratedRecords(page, prefix, trackedIds)  → deletes matching records
//   writeDiagnostics(session)    → writes diagnostics.json under artifactDir
//   goToStudioPage(page, name)   → navigates to Studio page
//
// Mock page.evaluate uses argument-type dispatch (P4):
//   - string arg → list call (snapshots first, presets second)
//   - object arg with id → delete call
//   - object arg with method → apiJson call
// No function-source-string inspection.

import {
  makeRunIdentity, pollUntil, cleanupGeneratedRecords,
  writeDiagnostics, goToStudioPage, apiJson,
} from "./studio_e2e_helpers.mjs";
import { mkdtemp, rm, readFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";

let failures = 0;

function assert(condition, message) {
  if (!condition) { console.error("  FAIL:", message); failures++; }
  else { console.log("  PASS"); }
}

// ── Helpers ──────────────────────────────────────────────────────────────

// Clean deterministic page mock (P4).  Dispatches evaluate calls by
// argument type so tests never inspect function source strings.
//   call #1  (API_BASE string)    = list snapshots
//   call #2  (API_BASE string)    = list presets
//   calls 3+ ({id, ...} object)   = delete
function mockEvaluatePage(snapshots, presets) {
  let listCalls = 0;
  const deletedIds = [];
  const page = {
    evaluate: async (_fn, arg) => {
      // List call: argument is the API_BASE string
      if (typeof arg === "string") {
        listCalls++;
        if (listCalls === 1) return snapshots;
        return presets;
      }
      // Delete call: argument is {apiBase, type, id}
      if (arg && typeof arg === "object" && arg.id !== undefined) {
        deletedIds.push(arg.id);
        return true;
      }
      // Fallback (e.g., apiJson passes {method, pathname, body})
      if (arg && typeof arg === "object" && arg.method !== undefined) {
        return { ok: true, status: 200, data: { echoed: arg }, error: null };
      }
      return [];
    },
  };
  page._deletedIds = deletedIds;
  return page;
}

// Utility: build a blank mock locator
function mockLocator() {
  return { waitFor: async () => {}, click: async () => {} };
}

// ── makeRunIdentity ──────────────────────────────────────────────────────

console.log("\n=== makeRunIdentity ===");

console.log("Test 1: returns object with prefix and artifactDir");
const r = makeRunIdentity("completion");
assert(typeof r === "object" && r !== null, "should return an object");
assert(typeof r.prefix === "string", "prefix should be a string, got " + typeof r.prefix);
assert(typeof r.artifactDir === "string", "artifactDir should be a string, got " + typeof r.artifactDir);

console.log('Test 2: prefix begins "E2E-completion-"');
assert(r.prefix.startsWith("E2E-completion-"),
  'prefix "' + r.prefix + '" should start with "E2E-completion-"');

console.log('Test 3: artifactDir uses path.join segments (P5)');
assert(r.artifactDir.includes("studio-completion"),
  'artifactDir "' + r.artifactDir + '" should include "studio-completion"');
// Verify path.join was used (backslash on win32, forward on posix; just check separator)
const parts = r.artifactDir.split(/[/\\]/);
assert(parts.length >= 3, "artifactDir should have at least 3 path segments, got " + parts.length);

console.log("Test 4: consecutive calls produce unique prefixes");
const r2 = makeRunIdentity("completion");
assert(r.prefix !== r2.prefix, "two prefixes should differ");

console.log("Test 5: different labels produce different prefix starts");
const r3 = makeRunIdentity("warmup");
assert(r3.prefix.startsWith("E2E-warmup-"),
  'label "warmup" should produce prefix starting "E2E-warmup-", got "' + r3.prefix + '"');

console.log("Test 6: prefix has content after label segment");
const suffix = r.prefix.slice("E2E-completion-".length);
assert(suffix.length > 0, "prefix should have content after label segment");

// ── pollUntil ────────────────────────────────────────────────────────────

console.log("\n=== pollUntil ===");

console.log("Test 7: returns final value satisfying predicate");
let counter7 = 0;
const fn7 = async () => { counter7++; return counter7; };
const val7 = await pollUntil(fn7, (v) => v >= 3, { intervalMs: 5, timeoutMs: 500 });
assert(val7 >= 3, "should return value >= 3, got " + val7);

console.log("Test 8: throws on timeout");
let threw8 = false;
try {
  await pollUntil(async () => false, (v) => v, { intervalMs: 5, timeoutMs: 50 });
} catch (e) {
  threw8 = true;
}
assert(threw8, "should throw Error on timeout");

console.log("Test 9: works with synchronous fn");
let counter9 = 0;
const fn9 = () => { counter9++; return counter9; };
const val9 = await pollUntil(fn9, (v) => v >= 2, { intervalMs: 5, timeoutMs: 500 });
assert(val9 >= 2, "should return value >= 2, got " + val9);

// ── apiJson ──────────────────────────────────────────────────────────────

console.log("\n=== apiJson ===");

console.log("Test 10: returns structured response (P6)");
const apiMock = mockEvaluatePage([], []);
const apiResult = await apiJson(apiMock, "POST", "/test/path", { key: "val" });
assert(typeof apiResult === "object" && apiResult !== null, "should return an object");
assert(apiResult.ok === true, "ok should be true, got " + apiResult.ok);
assert(apiResult.status === 200, "status should be 200, got " + apiResult.status);
assert(apiResult.data && apiResult.data.echoed, "should include echoed data");
assert(apiResult.error === null, "error should be null, got " + JSON.stringify(apiResult.error));

console.log("Test 11: apiJson with missing body");
const apiResult2 = await apiJson(apiMock, "GET", "/test/path");
assert(apiResult2.ok === true, "GET with no body should still return ok=true");
assert(apiResult2.status === 200, "status should be 200");

// ── cleanupGeneratedRecords ──────────────────────────────────────────────

console.log("\n=== cleanupGeneratedRecords ===");

// Test 12: detailed return with attempted/deleted/failed/ids (P7)
console.log("Test 12: returns detailed result object (P7)");
const snapData12 = [
  { id: "explicit-tracked-1", name: "untouched-name" },
  { id: "snap-e2e",           name: "E2E-completion-foo" },
  { id: "snap-keep",          name: "keep-me" },
];
const presetData12 = [
  { id: "preset-keep", name: "keep-me" },
  { id: "preset-e2e",  name: "E2E-completion-bar" },
];
const page12 = mockEvaluatePage(snapData12, presetData12);
const result12 = await cleanupGeneratedRecords(page12, "E2E-completion-", ["explicit-tracked-1"]);
assert(typeof result12 === "object" && result12 !== null, "should return an object, got " + typeof result12);
assert(typeof result12.attempted === "number", "should have attempted count, got " + typeof result12.attempted);
assert(typeof result12.deleted === "number", "should have deleted count, got " + typeof result12.deleted);
assert(typeof result12.failed === "number", "should have failed count, got " + typeof result12.failed);
assert(Array.isArray(result12.ids), "should have ids array, got " + typeof result12.ids);

// Verify correct IDs were targeted
assert(result12.ids.includes("explicit-tracked-1"), "should include explicitly tracked ID");
assert(result12.ids.includes("snap-e2e"), "should include snap-e2e");
assert(result12.ids.includes("preset-e2e"), "should include preset-e2e");
assert(!result12.ids.includes("snap-keep"), "should NOT include snapp-keep");
assert(!result12.ids.includes("preset-keep"), "should NOT include preset-keep");

// Test 13: respects exact prefix (does not match partial prefix)
console.log("Test 13: respects exact prefix boundary");
const page13 = mockEvaluatePage(
  [
    { id: "s-other", name: "E2E-other-prefix" },
    { id: "s-match", name: "E2E-completion-match" },
  ],
  [{ id: "p-no-match", name: "no-prefix" }],
);
const result13 = await cleanupGeneratedRecords(page13, "E2E-completion-", []);
assert(result13.deleted === 1, "should delete exactly 1 record, got " + result13.deleted);
assert(result13.ids.length === 1, "should have 1 targeted id, got " + result13.ids.length);
assert(result13.ids[0] === "s-match", 'should delete only "s-match", got ' + result13.ids[0]);
assert(!result13.ids.includes("s-other"), "should NOT delete different prefix");
assert(!result13.ids.includes("p-no-match"), "should NOT delete no-prefix record");

// Test 14: handles empty data (no records)
console.log("Test 14: handles no records gracefully");
const page14 = mockEvaluatePage([], []);
const result14 = await cleanupGeneratedRecords(page14, "E2E-completion-", []);
assert(result14.attempted === 0, "attempted should be 0, got " + result14.attempted);
assert(result14.deleted === 0, "deleted should be 0, got " + result14.deleted);
assert(result14.failed === 0, "failed should be 0, got " + result14.failed);
assert(result14.ids.length === 0, "ids should be empty, got " + JSON.stringify(result14.ids));

// Test 15: verification step - deleted IDs are absent in re-list (P7 verify)
console.log("Test 15: reports verification after deletion");
let reListCallCount = 0;
let reListCallArg = null;
const verifySnaps = [{ id: "still-here", name: "keep" }];
const verifyPresets = [];
const verifyPage = {
  evaluate: async (_fn, arg) => {
    // First two calls = original list
    if (typeof arg === "string") {
      reListCallCount++;
      if (reListCallCount <= 2 && reListCallCount === 1) return [{ id: "to-delete", name: "E2E-completion-v" }];
      if (reListCallCount <= 2 && reListCallCount === 2) return [];
      // Re-list calls (after delete)
      if (reListCallCount === 3) { reListCallArg = "snapshots-verify"; return verifySnaps; }
      if (reListCallCount === 4) { reListCallArg = "presets-verify"; return verifyPresets; }
      return [];
    }
    // Delete call
    if (arg && typeof arg === "object" && arg.id !== undefined) {
      return true;
    }
    return [];
  },
};
const result15 = await cleanupGeneratedRecords(verifyPage, "E2E-completion-", []);
assert(result15.deleted === 1, "should delete 1 record, got " + result15.deleted);
// After deletion, the "to-delete" ID should be absent
assert(Array.isArray(result15.verifiedAbsent), "should have verifiedAbsent array");
assert(result15.verifiedAbsent.includes("to-delete"), "verifiedAbsent should include deleted ID");
assert(Array.isArray(result15.verificationFailed), "should have verificationFailed array");
assert(result15.verificationFailed.length === 0, "no verification failures expected");

// ── writeDiagnostics ─────────────────────────────────────────────────────

console.log("\n=== writeDiagnostics ===");

console.log("Test 16: writes diagnostics.json with session data");
const tmpDir = await mkdtemp(join(tmpdir(), "e2e-test-"));
try {
  const session = {
    prefix: "E2E-test-abc",
    artifactDir: tmpDir,
    diagnostics: {
      consoleErrors: ["err1"],
      pageErrors: ["pageerr1"],
      failedResponses: [{ url: "/comfymodal/test", status: 500 }],
    },
  };
  const written = await writeDiagnostics(session);
  assert(written.endsWith("diagnostics.json"),
    'path should end with diagnostics.json, got "' + written.slice(-20) + '"');
  const content = JSON.parse(await readFile(written, "utf-8"));
  assert(content.prefix === "E2E-test-abc", "diagnostics should include prefix");
  assert(Array.isArray(content.diagnostics?.consoleErrors), "diagnostics should include consoleErrors array");
  assert(content.diagnostics.pageErrors[0] === "pageerr1", "diagnostics should include pageErrors");
  assert(content.diagnostics.failedResponses[0].status === 500, "diagnostics should include failedResponses");
  assert(typeof content.timestamp === "string", "diagnostics should include timestamp");
} finally {
  await rm(tmpDir, { recursive: true, force: true });
}

// ── goToStudioPage ───────────────────────────────────────────────────────

console.log("\n=== goToStudioPage ===");

const mockResolved = mockLocator();

console.log("Test 17: goToStudioPage is a function");
assert(typeof goToStudioPage === "function", "goToStudioPage should be exported as a function");

console.log('Test 18: throws for invalid name "invalid"');
const page18 = { getByRole: () => mockResolved, locator: () => mockResolved };
let threw18 = false;
try { await goToStudioPage(page18, "invalid"); } catch (e) { threw18 = true; }
assert(threw18, 'should throw Error for "invalid"');

console.log("Test 19: lowercase names resolve correctly");
for (const name of ["playground", "history", "backend", "settings"]) {
  let err = null;
  try { await goToStudioPage({ getByRole: () => mockResolved, locator: () => mockResolved }, name); }
  catch (e) { err = e; }
  assert(err === null, 'name "' + name + '" should not throw');
}

console.log("Test 20: case-insensitive names resolve correctly");
for (const name of ["PLAYGROUND", "History", "BACKEND", "Settings"]) {
  let err = null;
  try { await goToStudioPage({ getByRole: () => mockResolved, locator: () => mockResolved }, name); }
  catch (e) { err = e; }
  assert(err === null, 'name "' + name + '" should not throw');
}

console.log("Test 21: nav button is looked up by canonical label");
let capturedLabel = null;
const capturingPage = {
  getByRole: (role, opts) => { capturedLabel = opts?.name; return mockResolved; },
  locator: () => mockResolved,
};
await goToStudioPage(capturingPage, "history");
assert(capturedLabel === "History", 'expected "History", got "' + capturedLabel + '"');
capturedLabel = null;
await goToStudioPage(capturingPage, "backend");
assert(capturedLabel === "Backend", 'expected "Backend", got "' + capturedLabel + '"');

console.log("Test 22: waits for data-testid='studio-page' and page root");
const capturedSelectors = [];
const selectorPage = {
  getByRole: () => mockResolved,
  locator: (sel) => { capturedSelectors.push(sel); return mockResolved; },
};
await goToStudioPage(selectorPage, "playground");
assert(capturedSelectors.some((s) => s.includes("[data-testid='studio-page']")),
  "should wait for [data-testid='studio-page']");
assert(capturedSelectors.some((s) => s.includes("studio-playground")),
  "should wait for .comfymodal-studio-playground");

// ── Report ───────────────────────────────────────────────────────────────

if (failures > 0) {
  console.error("\nRED: " + failures + " test(s) FAILED");
  process.exit(1);
} else {
  console.log("\nGREEN: All deterministic tests passed");
}
