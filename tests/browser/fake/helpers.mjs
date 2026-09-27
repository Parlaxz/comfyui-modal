// Modal Studio — shared helpers for the fake-backend Playwright suite.
//
// Everything here talks to the fake backend (tests/browser/fake/) through
// page.request (test-control endpoints) and drives the real Studio UI in
// the harness page (/?session=<id> → window.__mountStudioForTest()).
//
// The de-facto per-test entrypoint is `setupFakeTest(page)` — fresh session,
// console guard installed BEFORE mount, Studio mounted, returns a small bag
// of pre-bound helpers.  Future agents should extend this file (and
// setupFakeTest) rather than duplicating logic in individual specs.

import { expect } from "@playwright/test";

export const FAKE_PORT = Number(process.env.STUDIO_FAKE_PORT || 8377);
export const FAKE_BASE_URL = `http://127.0.0.1:${FAKE_PORT}`;

// ── Test-control API (session/scenario/history/emit/state) ───────────────

export async function createSession(page) {
  const res = await page.request.post("/__comfymodal_test/session");
  if (!res.ok()) throw new Error(`createSession failed: HTTP ${res.status()}`);
  const body = await res.json();
  if (!body || !body.sessionId) throw new Error("createSession: no sessionId in response");
  return body.sessionId;
}

export async function setScenario(page, sessionId, scenario, overrides) {
  const data = { scenario, sessionId };
  if (overrides) data.overrides = overrides;
  const res = await page.request.post("/__comfymodal_test/scenario", { data });
  if (!res.ok()) throw new Error(`setScenario("${scenario}") failed: HTTP ${res.status()}`);
  return res.json();
}

export async function seedHistory(page, sessionId, scenario) {
  const res = await page.request.post("/__comfymodal_test/history-seed", {
    data: { scenario, sessionId },
  });
  if (!res.ok()) throw new Error(`seedHistory("${scenario}") failed: HTTP ${res.status()}`);
  return res.json();
}

export async function injectEvent(page, sessionId, type, detail) {
  const res = await page.request.post("/__comfymodal_test/emit", {
    data: { sessionId, type, detail },
  });
  if (!res.ok()) throw new Error(`injectEvent("${type}") failed: HTTP ${res.status()}`);
  return res.json();
}

export async function getFakeState(page, sessionId) {
  const res = await page.request.get(`/__comfymodal_test/state?session=${encodeURIComponent(sessionId)}`);
  if (!res.ok()) throw new Error(`getFakeState failed: HTTP ${res.status()}`);
  return res.json();
}

/**
 * Create a second runnable preset via the fake REST API.  The fake session
 * seeds exactly ONE preset (`preset_default`), but experiment mode gates its
 * Run button on 2+ unique presets — so tests that drive experiments create a
 * compare snapshot+preset pair.  Must run BEFORE the app's first preset fetch
 * (web/studio-backend.js caches runtime presets per apiBase), i.e. before
 * mounting the Studio or before any interaction that triggers a fetch.
 */
export async function createComparePreset(page, sessionId) {
  const snapRes = await page.request.post("/comfymodal/studio/snapshots", {
    data: {
      sessionId,
      name: "Fake Compare Snapshot",
      compatibleFeatures: ["txt2img"],
      graphJson: {},
      apiPromptJson: {},
      nodeBindings: {
        prompt: { kind: "widget", nodeId: "1", widgetName: "text" },
        steps: { kind: "widget", nodeId: "1", widgetName: "text" },
      },
      outputNodeId: "1",
      source: "manual",
    },
  });
  if (!snapRes.ok()) throw new Error(`createComparePreset: snapshot POST HTTP ${snapRes.status()}`);
  const snapBody = await snapRes.json();
  const snapshotId = snapBody.snapshot && snapBody.snapshot.id;
  if (!snapshotId) throw new Error("createComparePreset: no snapshot id in response");

  const presRes = await page.request.post("/comfymodal/studio/presets", {
    data: {
      sessionId,
      label: "Fake Compare Preset",
      snapshotId,
      compatibleFeatures: ["txt2img"],
      defaults: { seed: 7, steps: 20, guidance: 7, sampler: "euler", scheduler: "normal", denoise: 1 },
    },
  });
  if (!presRes.ok()) throw new Error(`createComparePreset: preset POST HTTP ${presRes.status()}`);
  const presBody = await presRes.json();
  const presetId = presBody.preset && presBody.preset.id;
  if (!presetId) throw new Error("createComparePreset: no preset id in response");
  return presetId;
}

// ── Studio mounting / navigation ─────────────────────────────────────────

/**
 * Mount the Studio against the fake backend for a session.
 *
 * The Studio's History page (web/studio-history-v2.js) reads
 * window.__COMFYMODAL_HISTORY_MODE__ to pick its repository.  The default is
 * "auto" — the real HTTP adapter backed by the fake engine's
 * /comfymodal/history-v2/* endpoints (see fake-backend.mjs / fake-server.mjs).
 * "fixture" opts into the frontend's own deterministic in-memory dataset
 * (web/history-v2-fixtures.js) and remains available as an explicit opt-in
 * via `{ historyMode: "fixture" }`.  When historyMode is "auto" (the
 * default) we deliberately do NOT set the flag, so studio-history-v2.js
 * falls through to its own "auto" default.
 */
export async function openStudio(page, sessionId, options = {}) {
  const historyMode = options.historyMode || "auto";
  if (historyMode === "fixture") {
    await page.addInitScript(() => {
      window.__COMFYMODAL_HISTORY_MODE__ = "fixture";
    });
  }

  await page.goto(`/?session=${encodeURIComponent(sessionId)}`, { waitUntil: "domcontentloaded" });
  // The harness defines __mountStudioForTest() from a module script; wait
  // for it so we never race the module graph.
  await page.waitForFunction(() => typeof window.__mountStudioForTest === "function", null, {
    timeout: 15000,
  });
  await page.evaluate(() => window.__mountStudioForTest());
  await expect(page.locator('[data-testid="studio-page"]')).toBeVisible({ timeout: 15000 });
  await expect(page.locator('.comfymodal-studio-topnav button[data-page="playground"]')).toBeVisible({
    timeout: 5000,
  });
}

export async function gotoPage(page, pageName) {
  const navBtn = page.locator(`.comfymodal-studio-topnav button[data-page="${pageName}"]`);
  if ((await navBtn.count()) === 0) {
    await page.evaluate((name) => {
      if (window.__studioApi && typeof window.__studioApi.setPage === "function") {
        window.__studioApi.setPage(name);
      }
    }, pageName);
  } else {
    await navBtn.click();
  }
  await expect(page.locator('[data-testid="studio-page"]')).toBeVisible({ timeout: 5000 });
}

// ── Playground single-run interaction ────────────────────────────────────

export async function selectPreset(page, presetId) {
  const select = page.locator('[data-testid="backend-select"]');
  await expect(select).toBeEnabled({ timeout: 15000 });
  await select.selectOption(String(presetId));
  // The change handler re-renders the control panel; wait for the prompt
  // control to confirm the preset hydrated.
  await expect(page.locator('[data-testid="input-prompt"]')).toBeVisible({ timeout: 10000 });
}

export async function submitSingleRun(page) {
  const runBtn = page.locator('[data-testid="run-btn"]');
  await expect(runBtn).toBeEnabled({ timeout: 15000 });
  await runBtn.click();
  return runBtn;
}

// ── Experiment-mode interaction ──────────────────────────────────────────

export async function enableExperimentMode(page) {
  const toggle = page.locator('[data-testid="experiment-toggle"]');
  await toggle.waitFor({ state: "visible", timeout: 10000 });
  if ((await toggle.textContent()).trim() === "Experiment") {
    await toggle.click();
  }
  await page.locator('[data-testid="experiment-mode"]').waitFor({ state: "visible", timeout: 10000 });
}

export async function selectComparePreset(page, presetId) {
  const cb = page.locator(`[data-testid="compare-preset-${presetId}"]`).first();
  // Preset rows load async; the checkbox is in the DOM (hidden) once loaded.
  await cb.waitFor({ state: "attached", timeout: 10000 });

  // Expand every collapsible summary in Compare Presets.  Group summaries
  // appear asynchronously after the main one opens, so retry until the
  // checkbox is actually visible.  (Collapsed content is display:none.)
  await expect
    .poll(async () => {
      const sections = page.locator(
        '[data-testid="compare-backends"] button.comfymodal-studio-collapsible-summary'
      );
      const count = await sections.count();
      let anyCollapsed = false;
      for (let i = 0; i < count; i++) {
        const s = sections.nth(i);
        if ((await s.getAttribute("aria-expanded")) !== "true") {
          anyCollapsed = true;
          await s.click();
        }
      }
      const visible = await cb.isVisible().catch(() => false);
      return visible && !anyCollapsed;
    }, { timeout: 10000, message: `compare preset ${presetId} checkbox did not become visible` })
    .toBe(true);

  if (!(await cb.isChecked())) {
    await cb.check();
    await expect(cb).toBeChecked({ timeout: 5000 });
  }
}

export async function submitExperiment(page) {
  const runBtn = page.locator('[data-testid="run-experiment-inline-btn"]');
  await expect(runBtn).toBeVisible({ timeout: 10000 });
  await expect(runBtn).toBeEnabled({ timeout: 10000 });
  await runBtn.click();
  return runBtn;
}

// ── Status / polling helpers ─────────────────────────────────────────────

export async function waitForStatus(page, text, opts = {}) {
  const { timeout = 15000 } = opts;
  await expect
    .poll(async () => {
      const sections = page.locator(
        ".comfymodal-studio-run-section, [data-testid='experiment-run-section']"
      );
      const count = await sections.count();
      for (let i = 0; i < count; i++) {
        const t = await sections.nth(i).textContent().catch(() => "");
        if (t && t.includes(text)) return true;
      }
      return false;
    }, { timeout, message: `expected run status text "${text}" to appear` })
    .toBe(true);
}

export function pollUntil(page, fn, opts = {}) {
  const { timeout = 15000, message = "condition not met" } = opts;
  return expect.poll(() => fn(page), { timeout, message }).toBe(true);
}

// ── Console guard ────────────────────────────────────────────────────────

export function installConsoleGuard(page) {
  const consoleErrors = [];
  const pageErrors = [];
  const onConsole = (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  };
  const onPageError = (err) => pageErrors.push(String(err && err.message ? err.message : err));
  page.on("console", onConsole);
  page.on("pageerror", onPageError);

  return {
    get consoleErrors() {
      return [...consoleErrors];
    },
    get pageErrors() {
      return [...pageErrors];
    },
    /** Throws if any console.error/pageerror was collected, minus allowlist. */
    assertNoErrors(allowlist = []) {
      const re = allowlist.map((p) => new RegExp(p));
      const bad = [];
      for (const e of consoleErrors) if (!re.some((r) => r.test(e))) bad.push(`[console.error] ${e}`);
      for (const e of pageErrors) if (!re.some((r) => r.test(e))) bad.push(`[pageerror] ${e}`);
      if (bad.length > 0) {
        throw new Error(`Console/page errors detected:\n${bad.join("\n")}`);
      }
    },
    dispose() {
      page.off("console", onConsole);
      page.off("pageerror", onPageError);
    },
  };
}

export function expectNoConsoleErrors(guard, allowlist = []) {
  guard.assertNoErrors(allowlist);
}

// ── Standard per-test setup ──────────────────────────────────────────────

/**
 * Fresh session + console guard (before mount) + Studio mount, returning
 * pre-bound helpers.  `beforeMount` runs after session creation but before
 * the Studio is mounted — use it for setup that must happen before the app's
 * first fetch (e.g. createComparePreset, because web/studio-backend.js
 * caches runtime presets).  `historyMode` controls the History V2 repository
 * ("auto" default — real HTTP adapter against the fake /comfymodal/history-v2
 * endpoints; "fixture" opts into the frontend's in-memory dataset).
 */
export async function setupFakeTest(page, { beforeMount, historyMode } = {}) {
  const sessionId = await createSession(page);
  const guard = installConsoleGuard(page);
  if (beforeMount) await beforeMount({ page, sessionId });
  await openStudio(page, sessionId, { historyMode });
  return {
    sessionId,
    guard,
    historyMode: historyMode || "auto",
    assertNoConsoleErrors: (allowlist = []) => guard.assertNoErrors(allowlist),
    setScenario: (scenario, overrides) => setScenario(page, sessionId, scenario, overrides),
    seedHistory: (scenario) => seedHistory(page, sessionId, scenario),
    injectEvent: (type, detail) => injectEvent(page, sessionId, type, detail),
    getState: () => getFakeState(page, sessionId),
    gotoPage: (name) => gotoPage(page, name),
    /** Full reload (goto + remount) in the same session. */
    reload: () => openStudio(page, sessionId, { historyMode }),
    waitForStatus: (text, opts) => waitForStatus(page, text, opts),
  };
}
