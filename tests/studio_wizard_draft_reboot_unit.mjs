// Modal Studio — setup-wizard draft persistence + reboot reconnect unit tests.
//
// Deterministic Node coverage (no browser, no network, no real timers) for the
// two behavior contracts added to the version-setup wizard:
//
//   PERSISTENCE  bounded namespaced draft schema (build/parse/apply), identity
//                matching (stale ids ignored softly), feature/binding/detail
//                payloads, and the wizard/workflows wiring that stores,
//                resumes, and clears it.
//   REBOOT       managerRebootAndWait treats the expected connection drop as
//                success and decides completion from the bounded reconnect
//                probes (/system_stats then /manager/version); failure is only
//                reported after the timeout. Never auto-reboots.
//
// Run: node tests/studio_wizard_draft_reboot_unit.mjs

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  WIZARD_DRAFT_KEY,
  WIZARD_DRAFT_SCHEMA,
  WIZARD_DRAFT_MAX_CHARS,
  buildWizardDraft,
  parseWizardDraft,
  applyWizardDraft,
  managerRebootAndWait,
} from "../web/studio-backend-api.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const readWeb = (name) => fs.readFileSync(path.join(ROOT, "web", name), "utf8");

function section(name) {
  console.log("PASS: " + name);
}

// ── Fixtures ──────────────────────────────────────────────────────────────

function baseState(overrides) {
  return Object.assign({
    isVersionSetup: true,
    step: "features",
    workflowId: "wf_abc",
    workflowVersionId: "ver_123",
    selectedFeatures: ["txt2img"],
    bindings: {
      seed: { nodeId: 42, nodeType: "KSampler", nodeTitle: "K", widgetName: "seed" },
      prompt: { nodeId: 7, nodeType: "CLIPTextEncode", nodeTitle: "P", inputName: "text" },
    },
    details: { name: "My Setup", description: "about" },
  }, overrides || {});
}

function makeClock(start) {
  let t = typeof start === "number" ? start : 0;
  return {
    now: () => t,
    sleep: (ms) => { t += ms; return Promise.resolve(); },
    advance: (ms) => { t += ms; },
    get time() { return t; },
  };
}

// ── 1. Draft schema is namespaced + bounded ───────────────────────────────

assert.equal(WIZARD_DRAFT_KEY, "comfymodal.studio.wizard.draft.v1");
assert.ok(/^comfymodal\./.test(WIZARD_DRAFT_KEY), "draft key is namespaced");
assert.equal(WIZARD_DRAFT_SCHEMA, 1);
section("1. draft key is namespaced and schema-versioned");

// ── 2. build → parse round-trip ───────────────────────────────────────────

const state = baseState({ step: "bindings" });
const draft = buildWizardDraft(state);
assert.equal(draft.v, WIZARD_DRAFT_SCHEMA);
assert.equal(draft.workflowId, "wf_abc");
assert.equal(draft.workflowVersionId, "ver_123");
assert.equal(draft.step, "bindings");
assert.deepEqual(draft.selectedFeatures, ["txt2img"]);
assert.equal(draft.bindings.seed.nodeId, 42);
assert.equal(draft.bindings.seed.widgetName, "seed");
assert.equal(draft.bindings.prompt.inputName, "text");
assert.equal(draft.details.name, "My Setup");
assert.ok(JSON.stringify(draft).length <= WIZARD_DRAFT_MAX_CHARS, "serialized draft is bounded");

const parsed = parseWizardDraft(JSON.stringify(draft));
const { at: _ignored, ...draftWithoutTimestamp } = draft;
assert.deepEqual(parsed, draftWithoutTimestamp);
section("2. build → parse round-trips identity, step, bindings, details");

// ── 3. Non-version-setup wizards are never drafted ────────────────────────

assert.equal(buildWizardDraft({ isVersionSetup: false, workflowId: "wf", workflowVersionId: "v" }), null);
assert.equal(buildWizardDraft(null), null);
assert.equal(buildWizardDraft({ isVersionSetup: true, workflowId: "", workflowVersionId: "v" }), null);
section("3. only version-setup wizards produce a draft");

// ── 4. Bounds: features, bindings, detail strings are capped ──────────────

const bigBindings = {};
for (let i = 0; i < 40; i++) {
  bigBindings["k" + i] = { nodeId: i, widgetName: "w" };
}
const big = buildWizardDraft(baseState({
  bindings: bigBindings,
  selectedFeatures: Array.from({ length: 20 }, (_, i) => "f" + i),
  details: { name: "n".repeat(1000), description: "d".repeat(9000) },
}));
assert.ok(Object.keys(big.bindings).length <= 16, "binding keys capped");
assert.ok(big.selectedFeatures.length <= 8, "features capped");
assert.ok(big.details.name.length <= 200, "name capped");
assert.ok(big.details.description.length <= 2000, "description capped");
assert.ok(JSON.stringify(big).length <= WIZARD_DRAFT_MAX_CHARS, "bounds keep JSON under the cap");
section("4. draft is bounded (bindings/features/detail strings)");

// ── 5. Unusable bindings are dropped (mirrors the save gate) ──────────────

const dropped = buildWizardDraft(baseState({
  bindings: {
    seed: { nodeId: 1 },
    valid: { nodeId: 2, outputIndex: 0 },
    empty: {},
    nil: null,
  },
}));
assert.deepEqual(Object.keys(dropped.bindings).sort(), ["valid"]);
assert.equal(dropped.bindings.valid.outputIndex, 0);
section("5. node-only / empty bindings never enter the draft");

// ── 6. Malformed + stale drafts fail soft ─────────────────────────────────

for (const bad of [null, undefined, "", "not json", "{}", "[]", JSON.stringify({ v: 99 })]) {
  assert.equal(parseWizardDraft(bad), null, JSON.stringify(bad));
}
assert.equal(
  parseWizardDraft(JSON.stringify({ v: 1, workflowId: "wf", workflowVersionId: "" })),
  null,
  "missing version identity rejected"
);
assert.equal(parseWizardDraft("x".repeat(WIZARD_DRAFT_MAX_CHARS * 3)), null, "oversized raw rejected");
// Valid identity but junk sub-fields degrade to empty, never throw.
const junk = parseWizardDraft(JSON.stringify({
  v: 1, workflowId: "wf", workflowVersionId: "v", step: 5,
  selectedFeatures: "nope", bindings: { a: { nodeId: 1 } }, details: 7,
}));
assert.equal(junk.step, "");
assert.deepEqual(junk.selectedFeatures, []);
assert.deepEqual(junk.bindings, {});
assert.deepEqual(junk.details, { name: "", description: "" });
section("6. malformed/oversized drafts are dropped; junk fields degrade softly");

// ── 7. applyWizardDraft matches identity and fills a fresh state ──────────

const fresh = baseState({ step: "features", selectedFeatures: [], bindings: {}, details: { name: "", description: "" } });
const ok = applyWizardDraft(fresh, parsed, ["features", "dependencies", "bindings", "details"]);
assert.equal(ok, true);
assert.equal(fresh.step, "bindings");
assert.deepEqual(fresh.selectedFeatures, ["txt2img"]);
assert.equal(fresh.bindings.seed.widgetName, "seed");
assert.equal(fresh.details.name, "My Setup");
assert.equal(fresh.details.description, "about");

// Stale id: a draft for another workflow/version is ignored, not applied.
const stale = baseState({ workflowVersionId: "ver_other", step: "features", bindings: {}, selectedFeatures: [], details: { name: "", description: "" } });
assert.equal(applyWizardDraft(stale, parsed, ["features", "dependencies", "bindings", "details"]), false);
assert.equal(stale.step, "features");
assert.deepEqual(stale.bindings, {});

// Unknown step falls back to the fresh default.
const unknownStep = baseState({ step: "features", bindings: {}, selectedFeatures: [], details: { name: "", description: "" } });
applyWizardDraft(unknownStep, Object.assign({}, parsed, { step: "bogus" }), ["features", "dependencies", "bindings", "details"]);
assert.equal(unknownStep.step, "features");
section("7. apply matches identity, applies step/bindings/details, ignores stale ids");

// ── 8. Reboot probe treats the connection drop as success ─────────────────

async function runReboot(opts) {
  const clock = makeClock();
  const calls = { reboot: 0, system: 0, manager: 0 };
  const phases = [];
  const res = await managerRebootAndWait(Object.assign({
    now: clock.now,
    sleep: clock.sleep,
    timeoutMs: 100,
    intervalMs: 10,
    reboot: async () => { calls.reboot += 1; throw new Error("socket dropped"); },
    onPhase: (p) => phases.push(p),
  }, opts(calls)));
  return { res, calls, phases, clock };
}

// (a) POST drops, system fails twice then answers, Manager fails once then
// answers → success, and the reboot throw is never treated as failure.
{
  let systemLeft = 2;
  let managerLeft = 1;
  const { res, calls, phases } = await runReboot((calls) => ({
    expectManager: true,
    probeSystem: async () => { calls.system += 1; if (systemLeft-- > 0) throw new Error("refused"); return { ok: true }; },
    probeManager: async () => { calls.manager += 1; if (managerLeft-- > 0) return { ok: false, status: 503 }; return { ok: true }; },
  }));
  assert.equal(res.ok, true);
  assert.equal(res.phase, "ready");
  assert.equal(calls.reboot, 1);
  assert.deepEqual(phases, ["reconnect", "manager"]);
}
section("8. reboot POST drop + bounded reconnect probes resolve as success");

// (b) ComfyUI never answers → bounded reconnect failure.
{
  const { res, calls, clock } = await runReboot((calls) => ({
    expectManager: true,
    probeSystem: async () => { calls.system += 1; return null; },
    probeManager: async () => { calls.manager += 1; return { ok: true }; },
  }));
  assert.equal(res.ok, false);
  assert.equal(res.phase, "reconnect");
  assert.equal(calls.manager, 0, "manager phase skipped while unreachable");
  assert.ok(calls.system <= 12, "reconnect polling is bounded");
  assert.ok(clock.time >= 100, "failure waits the full timeout");
}
section("9. no reconnect → bounded failure, never an unbounded loop");

// (c) ComfyUI returns but Manager never does → manager-phase failure.
{
  const { res, calls } = await runReboot((calls) => ({
    expectManager: true,
    probeSystem: async () => { calls.system += 1; return { ok: true }; },
    probeManager: async () => { calls.manager += 1; return { ok: false, status: 404 }; },
  }));
  assert.equal(res.ok, false);
  assert.equal(res.phase, "manager");
  assert.ok(calls.system >= 1);
  assert.ok(calls.manager <= 12, "manager polling is bounded");
}
section("10. reconnected ComfyUI + absent Manager → bounded manager failure");

// (d) Manager was not detected before the reboot → no Manager poll at all.
{
  const { res, calls, phases } = await runReboot((calls) => ({
    expectManager: false,
    probeSystem: async () => { calls.system += 1; return { ok: true }; },
    probeManager: async () => { calls.manager += 1; return { ok: false }; },
  }));
  assert.equal(res.ok, true);
  assert.equal(calls.manager, 0);
  assert.deepEqual(phases, ["reconnect"]);
}
section("11. Manager-absent reboots succeed on the system probe alone");

// (e) A reboot POST that resolves OK is still decided by the probes.
{
  const { res, calls } = await runReboot((calls) => ({
    expectManager: false,
    reboot: async () => { calls.reboot += 1; return { ok: true, status: 200 }; },
    probeSystem: async () => { calls.system += 1; return { ok: false, status: 500 }; },
  }));
  assert.equal(res.ok, false);
  assert.equal(res.phase, "reconnect");
}
section("12. a clean POST response alone never claims success");

// ── 13. Default probes hit /system_stats then /manager/version ────────────

{
  const originalFetch = globalThis.fetch;
  const urls = [];
  globalThis.fetch = async (url) => {
    const u = String(url);
    urls.push(u);
    const body = u.indexOf("/system_stats") !== -1 ? "{}" : JSON.stringify({ version: "x" });
    return {
      ok: true,
      status: 200,
      text: async () => body,
      json: async () => JSON.parse(body),
    };
  };
  try {
    const res = await managerRebootAndWait({
      timeoutMs: 50,
      intervalMs: 1,
      expectManager: true,
      reboot: async () => { throw new Error("socket dropped"); },
    });
    assert.equal(res.ok, true);
    assert.ok(urls.indexOf("/system_stats") !== -1, "default system probe used");
    assert.ok(urls.indexOf("/manager/version") !== -1, "default manager probe used");
  } finally {
    globalThis.fetch = originalFetch;
  }
}
section("13. default reboot probes poll /system_stats then /manager/version");

// ── 14. Consumer wiring pins (source is the contract) ─────────────────────

const wizardSource = readWeb("studio-workflow-setup-wizard.js");
const workflowsSource = readWeb("studio-workflows.js");

assert.ok(wizardSource.includes("managerRebootAndWait"), "wizard uses the bounded reboot-and-wait helper");
assert.ok(wizardSource.includes("saveWizardDraft(state)"), "wizard persists a draft from render");
assert.ok(wizardSource.includes("WIZARD_DRAFT_KEY") && wizardSource.includes("sessionStorage"), "wizard owns sessionStorage");
assert.ok(wizardSource.includes("_wireInstallStatus(depSection, state)"), "dependency rows get in-flight status");
assert.ok(wizardSource.includes("_reconcileInstallStatus(state)"), "refresh reconciles in-flight status");
assert.ok(wizardSource.includes("state.modelInstalls") && wizardSource.includes("state.nodeInstalls"), "model+node in-flight maps live in wizard state");
assert.ok(wizardSource.includes("clearWizardDraft()"), "close/save clears the draft");

assert.ok(workflowsSource.includes("maybeResumeSetupWizard"), "workflows page resumes on refresh");
assert.ok(workflowsSource.includes("readWizardDraft"), "resume reads the bounded draft");
// Resume is gated on a real browser reload, not the URL hash: ComfyUI's graph
// loader can overwrite location.hash with the active workflow UUID.
assert.ok(workflowsSource.includes("_pageWasReloaded"), "resume is gated on a real browser reload");
assert.ok(workflowsSource.includes("_wizardResumeAttempted"), "resume fires at most once per page load");
assert.ok(workflowsSource.includes("openVersionSetupWizard(wfId, verId, null)"), "resume reopens the same wizard");
assert.equal(workflowsSource.includes("replaceState"), false, "page module stays URL-routing-free");
section("14. wizard/workflows wiring pinned to the persisted draft + status contract");

console.log("studio_wizard_draft_reboot_unit complete");
