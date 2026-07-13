// Modal Studio — E2E Test Helpers
//
// Shared utilities for Modal Studio browser-based E2E tests.
// Pure helper functions (makeRunIdentity, pollUntil) can be tested
// without launching a browser.  Functions that interact with Playwright
// or the live app require a running ComfyUI instance.
//
// Isolation contract:
//   - Each test gets a fresh BrowserContext and artifact directory.
//   - Cleanup only affects IDs explicitly tracked or records whose
//     user-visible name/label begins with the exact supplied prefix.
//   - Unrelated data is never touched.

import { chromium } from "playwright";
import { randomUUID } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";

// ── Defaults ─────────────────────────────────────────────────────────────

const DEFAULT_POLL_INTERVAL_MS = 500;
const DEFAULT_POLL_TIMEOUT_MS = 30_000;
const API_BASE = "/comfymodal";

// ── makeRunIdentity ──────────────────────────────────────────────────────

/**
 * Generate a unique run identity.
 *
 * Returns { prefix, artifactDir } where:
 *   - prefix  begins with "E2E-<label>-<timestamp>_<random>"
 *   - artifactDir is a unique artifact directory path containing
 *     "studio-completion" for easy recognition
 *
 * @param {string} label - Short label for this run session (e.g. "completion").
 * @returns {{ prefix: string, artifactDir: string }}
 */
export function makeRunIdentity(label) {
  const timestamp = Date.now().toString(36);
  const rand = randomUUID().replace(/-/g, "").substring(0, 12);
  const prefix = "E2E-" + label + "-" + timestamp + "_" + rand;
  // P5: build artifactDir with path.join for Windows consistency
  const artifactDir = join(".e2e-artifacts", "studio-completion", prefix);
  return { prefix, artifactDir };
}

// ── launchIsolatedSession ────────────────────────────────────────────────

/**
 * Launch an isolated Playwright browser session.
 *
 * Creates:
 *   - A unique artifact directory (from makeRunIdentity).
 *   - A fresh Browser and isolated BrowserContext.
 *   - Diagnostics collectors for console errors, page errors, and
 *     failed responses (HTTP >= 400 on /comfymodal/ paths).
 *   - Navigates to baseUrl.
 *
 * P0: If newContext / newPage / goto fails after the browser is launched,
 * the browser is closed before the error propagates.
 *
 * P2: Console error entries include the message text AND safe argument
 * data (count + string representations) where available, without risking
 * listener exceptions.
 *
 * Returns the session object containing browser, context, page,
 * prefix, artifactDir, and diagnostics.
 *
 * @param {object} opts
 * @param {string}  opts.baseUrl   - ComfyUI base URL to navigate to.
 * @param {string}  opts.label     - Label passed to makeRunIdentity.
 * @param {boolean} [opts.headless=true] - Launch headless.
 * @returns {Promise<{
 *   browser: import("playwright").Browser,
 *   context: import("playwright").BrowserContext,
 *   page:    import("playwright").Page,
 *   prefix:      string,
 *   artifactDir: string,
 *   diagnostics: { consoleErrors: object[], pageErrors: string[], failedResponses: object[] }
 * }>}
 */
export async function launchIsolatedSession({ baseUrl, label, headless = true }) {
  const identity = makeRunIdentity(label);
  const { prefix, artifactDir } = identity;

  // Ensure artifact directory exists
  await mkdir(artifactDir, { recursive: true });

  // P0: browser must be closed if any setup step after launch fails
  const browser = await chromium.launch({ headless });
  try {
    const context = await browser.newContext();
    const page = await context.newPage();

    // Diagnostics collector
    const diagnostics = {
      // P2: console errors include text AND safe arg data
      consoleErrors: [],
      pageErrors: [],
      failedResponses: [],
    };

    page.on("console", (msg) => {
      if (msg.type() === "error") {
        const entry = { text: msg.text(), argCount: 0, argPreview: [] };
        try {
          const args = msg.args();
          entry.argCount = args.length;
          entry.argPreview = args.map(function (a) {
            try { return String(a); } catch { return "<error>"; }
          });
        } catch {
          // msg.args() may throw if the page is already destroyed
        }
        diagnostics.consoleErrors.push(entry);
      }
    });

    page.on("pageerror", (err) => {
      diagnostics.pageErrors.push(err.message);
    });

    page.on("response", (response) => {
      const url = response.url();
      if (response.status() >= 400 && url.includes("/comfymodal/")) {
        diagnostics.failedResponses.push({
          url: url,
          status: response.status(),
          statusText: response.statusText(),
        });
      }
    });

    // Navigate to the ComfyUI instance
    await page.goto(baseUrl, { waitUntil: "domcontentloaded" });

    return {
      browser,
      context,
      page,
      prefix,
      artifactDir,
      diagnostics,
    };
  } catch (err) {
    // P0: close the browser on setup failure
    await browser.close().catch(function () {});
    throw err;
  }
}

// ── apiJson ──────────────────────────────────────────────────────────────

/**
 * Perform an API JSON request via page.evaluate.
 *
 * P6: Returns structured `{ ok, status, data, error }` rather than
 * collapsing all failures to null.
 *
 * @param {import("playwright").Page} page - Playwright page.
 * @param {string} method - HTTP method (GET, POST, PATCH, DELETE, etc.).
 * @param {string} pathname - API path (e.g. "/comfymodal/studio/presets").
 * @param {object} [body] - JSON-serializable request body.
 * @returns {Promise<{ ok: boolean, status: number, data: object|null, error: string|null }>}
 */
export async function apiJson(page, method, pathname, body) {
  return page.evaluate(async function (opts) {
    var fetchOpts = { method: opts.method, headers: { "Content-Type": "application/json" } };
    if (opts.body !== undefined) {
      fetchOpts.body = JSON.stringify(opts.body);
    }
    try {
      var res = await fetch(opts.pathname, fetchOpts);
      var data = res.ok ? await res.json() : null;
      return { ok: res.ok, status: res.status, data: data, error: res.ok ? null : res.statusText };
    } catch (err) {
      return { ok: false, status: 0, data: null, error: err.message };
    }
  }, { method: method, pathname: pathname, body: body });
}

// ── openStudio ───────────────────────────────────────────────────────────

/**
 * Open the Modal Studio modal from the ComfyUI sidebar.
 *
 * P1/P3: Uses role-scoped locator as primary probe
 * (getByRole("button", ...)) with a fast minimal-timeout fallback instead
 * of a fixed 5s penalty on each getByText probe.
 *
 * Supports both "Modal Studio" and "Modal Testing" entry labels for
 * backward compatibility during the redesign migration.
 *
 * After opening, asserts that Playground, History, Backend, and
 * Settings nav items are visible in the Studio shell.
 *
 * @param {import("playwright").Page} page - Playwright page.
 * @returns {Promise<void>}
 */
export async function openStudio(page) {
  // Primary: role-scoped locator matching either label
  var clicked = false;

  // Try role-scoped probe first
  var roleEntry = page.getByRole("button", { name: /Modal Studio|Modal Testing/i });
  try {
    await roleEntry.waitFor({ state: "visible", timeout: 2000 });
    await roleEntry.click();
    clicked = true;
  } catch {
    // Fallback: short timeout on a few known selectors instead of
    // a fixed 5s penalty per getByText probe
    var fallbackSelectors = [
      '[data-testid="modal-studio-entry"]',
      '[data-testid="modal-testing-entry"]',
      ".comfymodal-sidebar-entry",
    ];
    for (var i = 0; i < fallbackSelectors.length; i++) {
      try {
        var fb = page.locator(fallbackSelectors[i]).first();
        await fb.waitFor({ state: "visible", timeout: 1000 });
        await fb.click();
        clicked = true;
        break;
      } catch {
        // continue to next fallback
      }
    }
  }

  if (!clicked) {
    throw new Error("Could not find Modal Studio or Modal Testing sidebar entry");
  }

  // Wait for the Studio shell container
  var shell = page.locator(
    ".comfymodal-studio-playground, .comfymodal-studio-modal"
  ).first();
  await shell.waitFor({ timeout: 10_000 });

  // Assert top nav items are visible
  var navLabels = ["Playground", "History", "Backend", "Settings"];
  for (var j = 0; j < navLabels.length; j++) {
    await page.getByText(navLabels[j], { exact: true }).waitFor({ timeout: 5000 });
  }
}

// ── goToStudioPage ────────────────────────────────────────────────────────

/**
 * Navigate to a specific Studio page by clicking the top nav button.
 *
 * Accepts case-insensitive names or canonical labels:
 *   "playground", "history", "backend", "settings"
 *   (or any casing: "PLAYGROUND", "History", etc.)
 *
 * After clicking the nav button, waits for:
 *   1. An element with `[data-testid='studio-page']` — the generic
 *      page mount point.
 *   2. The page root element `.comfymodal-studio-<name>` (e.g.
 *      `.comfymodal-studio-playground`).
 *
 * @param {import("playwright").Page} page - Playwright page.
 * @param {string} name - Case-insensitive page name.
 * @returns {Promise<void>}
 */
export async function goToStudioPage(page, name) {
  var norm = name.toLowerCase().trim();
  var LABEL_MAP = {
    playground: "Playground",
    history: "History",
    backend: "Backend",
    settings: "Settings",
  };
  var label = LABEL_MAP[norm];
  if (!label) {
    throw new Error(
      'Unknown Studio page: "' + name + '". Valid: playground, history, backend, settings'
    );
  }

  // Click the nav button with the exact canonical label
  var navButton = page.getByRole("button", { name: label, exact: true });
  await navButton.waitFor({ timeout: 10_000 });
  await navButton.click();

  // Wait for the generic studio-page mount point
  await page.locator("[data-testid='studio-page']").waitFor({ timeout: 10_000 });

  // Wait for the page root element
  var pageRoot = ".comfymodal-studio-" + norm;
  await page.locator(pageRoot).waitFor({ timeout: 10_000 });
}

// ── screenshot ────────────────────────────────────────────────────────────

/**
 * Take a full-page screenshot and save it under the artifact directory.
 *
 * The file is saved at `<artifactDir>/<name>`.
 *
 * @param {import("playwright").Page} page - Playwright page.
 * @param {string} artifactDir - Artifact directory path.
 * @param {string} name - File name (e.g. "step-1.png").
 * @returns {Promise<string>} The full path the screenshot was saved to.
 */
export async function screenshot(page, artifactDir, name) {
  var filePath = join(artifactDir, name);
  await page.screenshot({ path: filePath, fullPage: true });
  return filePath;
}

// ── pollUntil ────────────────────────────────────────────────────────────

/**
 * Poll an async function until a predicate is satisfied.
 *
 * Unlike the old Playwright-bound pollUntil, this version accepts a
 * generic async producer function and a predicate — no browser dependency.
 *
 * @param {Function} fn - Async (or sync) function returning a value.
 * @param {Function} predicate - Function(value) => truthy if done.
 * @param {object} [options]
 * @param {number} [options.intervalMs=500] - Poll interval in milliseconds.
 * @param {number} [options.timeoutMs=30000] - Max total poll time.
 * @returns {Promise<*>} The value that satisfied the predicate.
 * @throws {Error} If timeout is reached without a truthy value.
 */
export async function pollUntil(fn, predicate, options) {
  if (!options) options = {};
  var intervalMs = options.intervalMs || DEFAULT_POLL_INTERVAL_MS;
  var timeoutMs = options.timeoutMs || DEFAULT_POLL_TIMEOUT_MS;
  var deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    var result = await fn();
    if (predicate(result)) return result;
    await new Promise(function (resolve) { setTimeout(resolve, intervalMs); });
  }

  throw new Error("pollUntil timed out");
}

// ── writeDiagnostics ─────────────────────────────────────────────────────

/**
 * Write diagnostics data as JSON to a session's artifact directory.
 *
 * The file is written to `<session.artifactDir>/diagnostics.json`.
 * Includes the session prefix, timestamp, and diagnostics object.
 *
 * @param {object} session - Session object from launchIsolatedSession.
 * @param {string} session.prefix
 * @param {string} session.artifactDir
 * @param {object} session.diagnostics - { consoleErrors, pageErrors, failedResponses }
 * @returns {Promise<string>} The full path to the written diagnostics file.
 */
export async function writeDiagnostics(session) {
  var artifactDir = session.artifactDir;
  var diagnostics = session.diagnostics;
  var prefix = session.prefix;
  var data = {
    prefix: prefix,
    timestamp: new Date().toISOString(),
    diagnostics: {
      consoleErrors: diagnostics.consoleErrors || [],
      pageErrors: diagnostics.pageErrors || [],
      failedResponses: diagnostics.failedResponses || [],
    },
  };
  var filePath = join(artifactDir, "diagnostics.json");
  await writeFile(filePath, JSON.stringify(data, null, 2), "utf-8");
  return filePath;
}

// ── cleanupGeneratedRecords ──────────────────────────────────────────────

/**
 * Delete Studio records created during an E2E session.
 *
 * Only touches:
 *   1. Records whose IDs are in `trackedIds` (explicitly tracked).
 *   2. Records whose user-visible name/label begins with the exact
 *      supplied `prefix` string.
 *
 * Operates via Studio snapshot and preset APIs only.  All unrelated
 * records are preserved.
 *
 * P7: Returns detailed result including attempted/deleted/failed counts
 * and the full list of targeted IDs.  After deletion, re-lists records
 * to verify the deleted IDs are absent.
 *
 * @param {import("playwright").Page} page - Playwright page (for evaluate).
 * @param {string} prefix - Exact E2E prefix (e.g. "E2E-completion-abc123").
 * @param {string[]} trackedIds - IDs explicitly tracked during the session.
 * @returns {Promise<{
 *   attempted: number,
 *   deleted: number,
 *   failed: number,
 *   ids: string[],
 *   failedIds: string[],
 *   verifiedAbsent: string[],
 *   verificationFailed: string[],
 * }>}
 */
export async function cleanupGeneratedRecords(page, prefix, trackedIds) {
  // List all snapshots
  var snapshots = await page.evaluate(async function (apiBase) {
    try {
      var r = await fetch(apiBase + "/studio/snapshots");
      if (!r.ok) return [];
      var data = await r.json();
      return data.snapshots || [];
    } catch {
      return [];
    }
  }, API_BASE);

  // List all presets
  var presets = await page.evaluate(async function (apiBase) {
    try {
      var r = await fetch(apiBase + "/studio/presets");
      if (!r.ok) return [];
      var data = await r.json();
      return data.presets || [];
    } catch {
      return [];
    }
  }, API_BASE);

  var trackedSet = new Set(trackedIds);
  var toDelete = [];

  // Snapshots: delete if tracked or name starts with prefix
  for (var si = 0; si < snapshots.length; si++) {
    var s = snapshots[si];
    if (!s || !s.id) continue;
    if (trackedSet.has(s.id)) {
      toDelete.push({ type: "snapshot", id: s.id });
    } else if (typeof s.name === "string" && s.name.startsWith(prefix)) {
      toDelete.push({ type: "snapshot", id: s.id });
    }
  }

  // Presets: delete if tracked or name starts with prefix
  for (var pi = 0; pi < presets.length; pi++) {
    var p = presets[pi];
    if (!p || !p.id) continue;
    if (trackedSet.has(p.id)) {
      toDelete.push({ type: "preset", id: p.id });
    } else if (typeof p.name === "string" && p.name.startsWith(prefix)) {
      toDelete.push({ type: "preset", id: p.id });
    }
  }

  // P7: track detailed results
  var result = {
    attempted: 0,
    deleted: 0,
    failed: 0,
    ids: [],
    failedIds: [],
    verifiedAbsent: [],
    verificationFailed: [],
  };

  // Delete each matched record
  for (var di = 0; di < toDelete.length; di++) {
    var item = toDelete[di];
    result.attempted++;
    result.ids.push(item.id);

    var ok = await page.evaluate(async function (opts) {
      try {
        var url = opts.apiBase + "/studio/" + opts.type + "s/" + encodeURIComponent(opts.id);
        var r = await fetch(url, { method: "DELETE" });
        return r.ok;
      } catch {
        return false;
      }
    }, { apiBase: API_BASE, type: item.type, id: item.id });

    if (ok) {
      result.deleted++;
    } else {
      result.failed++;
      result.failedIds.push(item.id);
    }
  }

  // P7 verify: re-list to confirm deleted IDs are absent
  if (result.deleted > 0) {
    var remainingSnapshots = await page.evaluate(async function (apiBase) {
      try {
        var r = await fetch(apiBase + "/studio/snapshots");
        if (!r.ok) return [];
        var data = await r.json();
        return data.snapshots || [];
      } catch {
        return [];
      }
    }, API_BASE);

    var remainingPresets = await page.evaluate(async function (apiBase) {
      try {
        var r = await fetch(apiBase + "/studio/presets");
        if (!r.ok) return [];
        var data = await r.json();
        return data.presets || [];
      } catch {
        return [];
      }
    }, API_BASE);

    var remainingIds = [];
    for (var rsi = 0; rsi < remainingSnapshots.length; rsi++) {
      if (remainingSnapshots[rsi] && remainingSnapshots[rsi].id) {
        remainingIds.push(remainingSnapshots[rsi].id);
      }
    }
    for (var rpi = 0; rpi < remainingPresets.length; rpi++) {
      if (remainingPresets[rpi] && remainingPresets[rpi].id) {
        remainingIds.push(remainingPresets[rpi].id);
      }
    }

    var remainingSet = new Set(remainingIds);
    for (var ri = 0; ri < result.ids.length; ri++) {
      var tid = result.ids[ri];
      if (remainingSet.has(tid)) {
        result.verificationFailed.push(tid);
      } else {
        result.verifiedAbsent.push(tid);
      }
    }
  }

  return result;
}
