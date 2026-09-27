// Modal Studio — E2E Test Fixtures
//
// Self-contained fixtures for Studio browser tests.  Does NOT import
// studio_e2e_helpers.mjs (which uses prefix-based cleanup).
// Cleanup is strictly ID-only — no listing, no name-prefix deletion.
//
// Usage:
//   import { openStudio, installConsoleGuard, buildLiveSnapshotPayload } from "./studio-fixtures.mjs";

import { randomBytes } from "node:crypto";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

// ── Paths ─────────────────────────────────────────────────────────────────

const __dirname = dirname(fileURLToPath(import.meta.url));
const NODE_ROOT = join(__dirname, "..", "..");

// ── createOwnerPrefix ─────────────────────────────────────────────────────

/**
 * Generate a unique owner prefix for this test run.
 *
 * Format: "pw-<timestamp>_<randomhex>"
 * Use with createOwnedRecords() to tag all records owned by a test.
 *
 * @returns {string} Unique prefix like "pw-1a2b3c_d4e5f6g7"
 */
export function createOwnerPrefix() {
  const ts = Date.now().toString(36);
  const rand = randomBytes(5).toString("hex");
  return `pw-${ts}_${rand}`;
}

// ── createOwnedRecords ───────────────────────────────────────────────────

/**
 * Create an empty owned-records container.
 *
 * Returns { snapshotIds: string[], presetIds: string[] }.
 * Populate by calling createOwnedSnapshotAndPresets and pass to
 * cleanupOwnedRecords for teardown.
 *
 * @returns {{ snapshotIds: string[], presetIds: string[] }}
 */
export function createOwnedRecords() {
  return { snapshotIds: [], presetIds: [] };
}

// ── installConsoleGuard ──────────────────────────────────────────────────

/**
 * Install console/page-error listeners on *page*.
 *
 * Collects `pageerror` events and `console.error` calls into internal
 * arrays.  Returns an assertion function that, when called, throws if any
 * errors were collected (optionally filtered by explicit ignore patterns).
 *
 * The assertion function **must be called by the spec** to verify no
 * unexpected errors occurred during the test.  Ignore patterns are
 * NOT configured by default — callers that need them must document the
 * pattern and why in the caller code.
 *
 * @param {import("playwright").Page} page
 * @returns {{
 *   assertNoErrors: function(ignorePatterns?: string[]): void,
 *   consoleErrors: string[],
 *   pageErrors: string[],
 *   dispose: function(): void,
 * }}
 */
export function installConsoleGuard(page) {
  /** @type {string[]} */
  const consoleErrors = [];
  /** @type {string[]} */
  const pageErrors = [];

  const onConsole = (msg) => {
    if (msg.type() === "error") {
      consoleErrors.push(msg.text());
    }
  };
  const onPageError = (err) => {
    pageErrors.push(err.message);
  };

  page.on("console", onConsole);
  page.on("pageerror", onPageError);

  /**
   * Assert that no console.error or pageerror occurred.
   *
   * @param {string[]} [ignorePatterns=[]] - Optional list of regex source
   *   strings.  An error is ignored if ANY pattern matches.  Callers must
   *   document each pattern.
   * @throws {Error} If any (non-ignored) errors were collected.
   */
  function assertNoErrors(ignorePatterns = []) {
    const compiled = ignorePatterns.map((p) => new RegExp(p));

    const filteredConsole = consoleErrors.filter(
      (e) => !compiled.some((re) => re.test(e))
    );
    const filteredPage = pageErrors.filter(
      (e) => !compiled.some((re) => re.test(e))
    );

    const all = [];
    for (const e of filteredConsole) all.push(`[console.error] ${e}`);
    for (const e of filteredPage) all.push(`[pageerror] ${e}`);

    if (all.length > 0) {
      throw new Error(
        `Console/page errors detected:\n${all.join("\n")}`
      );
    }
  }

  /**
   * Remove listeners from the page. Call during teardown to avoid
   * leaking listeners across tests sharing the same page object.
   */
  function dispose() {
    page.off("console", onConsole);
    page.off("pageerror", onPageError);
  }

  return { assertNoErrors, consoleErrors, pageErrors, dispose };
}

// ── openStudio ───────────────────────────────────────────────────────────

/**
 * Navigate to the ComfyUI app and open the Modal Studio.
 *
 * Steps:
 *   1. Navigate to baseURL (waits for domcontentloaded).
 *   2. If `[data-testid="studio-page"]` is already present (e.g. after
 *      reload with state persistence), return immediately.
 *   3. Otherwise click the "Modal GPU" sidebar entry.
 *   4. Click the "Open Studio" button.
 *   5. Wait for `[data-testid="studio-page"]` (up to 10 s).
 *
 * @param {import("playwright").Page} page
 * @param {string} [baseURL] - URL to navigate to.  Defaults to
 *   process.env.COMFYUI_URL or page.url().
 * @returns {Promise<void>}
 */
export async function openStudio(page, baseURL) {
  const url = baseURL || process.env.COMFYUI_URL || page.url();
  if (!url || url === "about:blank") {
    throw new Error(
      "openStudio: no baseURL provided and page is not yet navigated. " +
      "Set COMFYUI_URL env or pass baseURL."
    );
  }

  await page.goto(url, { waitUntil: "domcontentloaded" });

  // Robust: if Studio is already open after reload, skip opening steps.
  const alreadyOpen = await page
    .locator('[data-testid="studio-page"]')
    .isVisible()
    .catch(() => false);
  if (alreadyOpen) return;

  // Primary: use the public launcher function exposed by modal-testing.js.
  // This is the direct API — calling it mounts the Studio overlay.
  const hasLauncher = await page.evaluate(() => {
    return typeof window.open_testing_modal === "function";
  });
  if (hasLauncher) {
    await page.evaluate(() => window.open_testing_modal());
    await page.locator('[data-testid="studio-page"]').waitFor({ timeout: 15_000 });
    return;
  }

  // Fallback: click the sidebar "Modal GPU" entry, then click "Open Studio".
  const sidebarEntry = page.getByRole("button", { name: /Modal GPU/ }).first();
  await sidebarEntry.waitFor({ timeout: 15_000 });
  await sidebarEntry.click();
  const openBtn = page.getByRole("button", { name: /Open Studio/i }).first();
  await openBtn.waitFor({ timeout: 10_000 });
  await openBtn.click();
  await page.locator('[data-testid="studio-page"]').waitFor({ timeout: 10_000 });
}

// ── cleanupOwnedRecords ──────────────────────────────────────────────────

/**
 * Delete all records in *owned* via the Studio API.
 *
 * Presets are deleted FIRST, then snapshots.  Only IDs in
 * `owned.presetIds` and `owned.snapshotIds` are touched — no listing,
 * no prefix/name matching.
 *
 * HTTP 404 responses are silently ignored (record may have already been
 * archived by the test).  Any other error is collected and reported.
 *
 * @param {import("@playwright/test").APIRequestContext} request - Playwright
 *   APIRequestContext (or any object with a `.delete(url)` method returning
 *   `{ ok(): boolean, status(): number }`).
 * @param {string} baseURL - Base URL of the ComfyUI instance.
 * @param {{ snapshotIds: string[], presetIds: string[] }} owned - Records
 *   to delete.
 * @returns {Promise<{ deleted: number, failures: { id: string, status: number, error?: string }[] }>}
 * @throws {Error} If any failure other than 404 occurs.
 */
export async function cleanupOwnedRecords(request, baseURL, owned) {
  const failures = [];
  let deleted = 0;

  // Delete presets first (they reference snapshots)
  for (const id of owned.presetIds) {
    if (!id) continue;
    try {
      const res = await request.delete(
        `${baseURL}/comfymodal/studio/presets/${encodeURIComponent(id)}`
      );
      if (res.status() === 404) continue; // already gone
      if (!res.ok()) {
        failures.push({ id, status: res.status() });
      } else {
        deleted++;
      }
    } catch (err) {
      failures.push({ id, status: -1, error: err.message });
    }
  }

  // Then delete snapshots
  for (const id of owned.snapshotIds) {
    if (!id) continue;
    try {
      const res = await request.delete(
        `${baseURL}/comfymodal/studio/snapshots/${encodeURIComponent(id)}`
      );
      if (res.status() === 404) continue; // already gone
      if (!res.ok()) {
        failures.push({ id, status: res.status() });
      } else {
        deleted++;
      }
    } catch (err) {
      failures.push({ id, status: -1, error: err.message });
    }
  }

  if (failures.length > 0) {
    const detail = failures
      .map((f) => `  ${f.id}: HTTP ${f.status}${f.error ? ` (${f.error})` : ""}`)
      .join("\n");
    throw new Error(
      `cleanupOwnedRecords: ${failures.length} deletion failure(s):\n${detail}`
    );
  }

  return { deleted, failures };
}

// ── createOwnedSnapshotAndPresets ─────────────────────────────────────────

/**
 * Create snapshots and presets via the browser's fetch API.
 *
 * Each iteration creates:
 *   - One snapshot (txt2img, minimal runnable payload)
 *   - One preset linked to that snapshot
 *
 * IDs of created records are pushed into *owned*.
 *
 * @param {import("playwright").Page} page
 * @param {string} prefix - Owner prefix for naming (from createOwnerPrefix).
 * @param {number} count - Number of snapshot+preset pairs to create.
 * @param {{ snapshotIds: string[], presetIds: string[] }} owned - Container
 *   to append created IDs into.
 * @returns {Promise<void>}
 */
export async function createOwnedSnapshotAndPresets(page, prefix, count, owned) {
  for (let i = 0; i < count; i++) {
    const snapshotName = `${prefix}-snapshot-${i}`;
    const presetLabel = `${prefix}-preset-${i}`;

    // 1. Create the snapshot via POST
    const snapResult = await page.evaluate(async (payload) => {
      try {
        const res = await fetch("/comfymodal/studio/snapshots", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!res.ok) return { error: `HTTP ${res.status}` };
        const data = await res.json();
        return data.snapshot || data;
      } catch (err) {
        return { error: err.message };
      }
    }, {
      name: snapshotName,
      compatibleFeatures: ["txt2img"],
      graphJson: { "1": { class_type: "CLIPTextEncode", inputs: { text: "test" } } },
      apiPromptJson: {
        "1": { class_type: "CLIPTextEncode", inputs: { text: "" } },
      },
      nodeBindings: {
        prompt: { kind: "widget", nodeId: "1", widgetName: "text" },
      },
      outputNodeId: "1",
      source: "manual",
    });

    if (snapResult.error) {
      throw new Error(
        `createOwnedSnapshotAndPresets: snapshot POST failed at index ${i}: ${snapResult.error}`
      );
    }

    const snapshotId = snapResult.id;
    if (!snapshotId) {
      throw new Error(
        `createOwnedSnapshotAndPresets: no id in snapshot response at index ${i}`
      );
    }
    owned.snapshotIds.push(snapshotId);

    // 2. Create the preset linked to this snapshot via POST
    const presetResult = await page.evaluate(async (payload) => {
      try {
        const res = await fetch("/comfymodal/studio/presets", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!res.ok) return { error: `HTTP ${res.status}` };
        const data = await res.json();
        return data.preset || data;
      } catch (err) {
        return { error: err.message };
      }
    }, {
      label: presetLabel,
      snapshotId,
      compatibleFeatures: ["txt2img"],
      defaults: {
        seed: 42,
        steps: 20,
        guidance: 7.0,
        sampler: "euler",
        scheduler: "normal",
        denoise: 1.0,
      },
    });

    if (presetResult.error) {
      throw new Error(
        `createOwnedSnapshotAndPresets: preset POST failed at index ${i}: ${presetResult.error}`
      );
    }

    const presetId = presetResult.id;
    if (!presetId) {
      throw new Error(
        `createOwnedSnapshotAndPresets: no id in preset response at index ${i}`
      );
    }
    owned.presetIds.push(presetId);
  }
}

// ── buildLiveSnapshotPayload ─────────────────────────────────────────────

/**
 * Read clean_workflow.json and build a snapshot-compatible payload.
 *
 * Scans the workflow for:
 *   - A KSampler node (class_type matching /ksampler/i)
 *   - At least one CLIPTextEncode node
 *   - A SaveImage or PreviewImage output node
 *
 * Returns bindings mapping Studio control IDs to KSampler/CLIP widgets:
 * prompt, seed, steps, guidance (→ KS cfg),
 * sampler (→ KS sampler_name), scheduler, denoise, output.
 * negative_prompt binding is only included when at least two distinct
 * CLIPTextEncode nodes exist in the workflow.
 *
 * The workflow is read from `<custom-node-root>/clean_workflow.json`.
 * Both bare workflows (node-ID-keyed dict) and API-prompt wrapper format
 * (`{ prompt: {...}, ... }`) are supported.
 *
 * @param {string} [workflowPath] - Path to clean_workflow.json.  Defaults
 *   to `<NODE_ROOT>/clean_workflow.json`.
 * @returns {{
 *   snapshotPayload: object,
 *   bindings: object,
 *   ksamplerNodeId: string,
 *   clipEncodeNodeIds: string[],
 *   outputNodeId: string,
 * }}
 * @throws {Error} If any required node type is missing.
 */
export function buildLiveSnapshotPayload(workflowPath) {
  const path = workflowPath || join(NODE_ROOT, "clean_workflow.json");

  /** @type {object} */
  let raw;
  try {
    raw = JSON.parse(readFileSync(path, "utf-8"));
  } catch (err) {
    throw new Error(
      `buildLiveSnapshotPayload: cannot read workflow at ${path}: ${err.message}`
    );
  }

  // Support both bare workflow and API-prompt wrapper
  const workflow =
    raw && typeof raw === "object" && !Array.isArray(raw)
      ? (raw.prompt && typeof raw.prompt === "object" && !Array.isArray(raw.prompt)
          ? raw.prompt
          : raw)
      : raw;

  // ── Find KSampler ──────────────────────────────────────────────────
  const ksamplerEntries = Object.entries(workflow).filter(
    ([_id, node]) =>
      node &&
      typeof node === "object" &&
      typeof node.class_type === "string" &&
      /ksampler/i.test(node.class_type)
  );

  if (ksamplerEntries.length === 0) {
    throw new Error(
      `buildLiveSnapshotPayload: no KSampler node found in workflow ` +
      `(scanned ${Object.keys(workflow).length} nodes). ` +
      `Expected a node with class_type containing "KSampler" (e.g. KSampler, ClownsharKSampler_Beta).`
    );
  }
  const [ksamplerNodeId, ksamplerNode] = ksamplerEntries[0];

  // ── Find CLIPTextEncode nodes (need at least 2) ─────────────────────
  const clipEncodeEntries = Object.entries(workflow).filter(
    ([_id, node]) =>
      node &&
      typeof node === "object" &&
      node.class_type === "CLIPTextEncode"
  );

  if (clipEncodeEntries.length < 1) {
    throw new Error(
      `buildLiveSnapshotPayload: found ${clipEncodeEntries.length} CLIPTextEncode node(s), ` +
      `need at least 1. Workflow path: ${path}. ` +
      `Node IDs found: ${clipEncodeEntries.map(([id]) => id).join(", ") || "none"}.`
    );
  }
  const clipEncodeNodeIds = clipEncodeEntries.map(([id]) => id);

  // The first CLIPTextEncode is used for prompt binding.
  // negative_prompt binding is only included when a distinct second
  // CLIPTextEncode node exists (binding both prompt and negative_prompt
  // to the same widget is incorrect — see feature-registry.js controls).
  const promptNodeId = clipEncodeNodeIds[0];
  const hasDistinctNegative = clipEncodeNodeIds.length >= 2;
  const negativeNodeId = hasDistinctNegative ? clipEncodeNodeIds[1] : null;

  // Verify that the prompt node has an inputs.text field (widget or connection)
  const promptNode = clipEncodeEntries[0][1];
  const promptInputs = promptNode?.inputs || {};
  if (!("text" in promptInputs)) {
    throw new Error(
      `buildLiveSnapshotPayload: CLIPTextEncode node ${promptNodeId} has no "text" input. ` +
      `Available inputs: ${Object.keys(promptInputs).join(", ") || "none"}.`
    );
  }

  // ── Find SaveImage or PreviewImage ──────────────────────────────────
  const outputEntries = Object.entries(workflow).filter(
    ([_id, node]) =>
      node &&
      typeof node === "object" &&
      (node.class_type === "SaveImage" || node.class_type === "PreviewImage")
  );

  if (outputEntries.length === 0) {
    throw new Error(
      `buildLiveSnapshotPayload: no SaveImage or PreviewImage node found. ` +
      `At least one image output node is required for snapshots.`
    );
  }
  const [outputNodeId] = outputEntries[0];

  // ── Read KSampler input fields for widget bindings ──────────────────
  const kInputs = ksamplerNode?.inputs || {};

  // Supported binding keys and their corresponding widget names.
  // Studio control IDs (feature-registry.js) are the binding keys;
  // KSampler widget names are the widgetName values.
  //   sampler (control) → sampler_name (KSampler widget)
  const samplerBindingKeys = {
    seed: "seed",
    steps: "steps",
    guidance: "cfg",       // guidance (control) → cfg (KSampler widget)
    sampler: "sampler_name", // sampler (control) → sampler_name (KSampler widget)
    scheduler: "scheduler",
    denoise: "denoise",
  };

  // Verify KSampler has the expected inputs
  const missingInputs = Object.values(samplerBindingKeys).filter(
    (key) => !(key in kInputs)
  );
  if (missingInputs.length > 0) {
    throw new Error(
      `buildLiveSnapshotPayload: KSampler node ${ksamplerNodeId} missing expected inputs: ` +
      `${missingInputs.join(", ")}. Available: ${Object.keys(kInputs).join(", ") || "none"}.`
    );
  }

  // ── Build bindings ──────────────────────────────────────────────────
  // Binding keys are Studio control IDs (see studio-feature-registry.js):
  //   prompt, negative_prompt, seed, steps, guidance, sampler, scheduler, denoise, output
  // widgetName values are the KSampler/CLIPTextEncode input field names.
  //
  // negative_prompt is only included when a distinct second CLIPTextEncode
  // node exists.  Binding both to the same widget is incorrect.
  const bindings = {
    prompt: { kind: "widget", nodeId: promptNodeId, widgetName: "text" },
    seed: { kind: "widget", nodeId: ksamplerNodeId, widgetName: "seed" },
    steps: { kind: "widget", nodeId: ksamplerNodeId, widgetName: "steps" },
    guidance: { kind: "widget", nodeId: ksamplerNodeId, widgetName: "cfg" },
    sampler: { kind: "widget", nodeId: ksamplerNodeId, widgetName: "sampler_name" },
    scheduler: { kind: "widget", nodeId: ksamplerNodeId, widgetName: "scheduler" },
    denoise: { kind: "widget", nodeId: ksamplerNodeId, widgetName: "denoise" },
    output: { kind: "output", nodeId: outputNodeId },
  };

  if (hasDistinctNegative) {
    bindings.negative_prompt = {
      kind: "widget", nodeId: negativeNodeId, widgetName: "text",
    };
  }

  // ── Build snapshot payload ─────────────────────────────────────────
  const snapshotPayload = {
    name: "Live Workflow Snapshot",
    compatibleFeatures: ["txt2img"],
    graphJson: workflow,
    apiPromptJson: workflow,
    nodeBindings: bindings,
    outputNodeId,
    modelSummary: "Live workflow import",
    source: "manual",
    controlSchemas: {},
  };

  return {
    snapshotPayload,
    bindings,
    ksamplerNodeId,
    clipEncodeNodeIds,
    outputNodeId,
  };
}
