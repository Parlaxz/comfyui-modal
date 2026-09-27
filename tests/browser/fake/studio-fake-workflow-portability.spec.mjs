// Phase G12 — Workflow Portability frontend UX against the fake backend.
//
// Proves the mounted Workflows product lane: summary chips (not-analyzed /
// fresh / stale / needs-check), the version-scoped Portability panel, the
// six-target matrix, source-environment separation, manifest Export
// (presets default OFF), mandatory dry-run Import with explicit preset
// policies, and the no-install/no-run guarantees.
//
// The fake serves SEEDED contract payloads only — no rule logic is simulated
// client- or fake-side.

import { test, expect } from "@playwright/test";
import { setupFakeTest } from "./helpers.mjs";

const CARD = (id) => `[data-testid="workflow-card"][data-workflow-id="${id}"]`;

function trackRequests(page, pattern) {
  const hits = [];
  const onReq = (r) => {
    if (pattern.test(r.url())) hits.push({ url: r.url(), method: r.method() });
  };
  page.on("request", onReq);
  return { hits, dispose: () => page.off("request", onReq) };
}

/** Track non-GET requests matching pattern (mutations/writes/runs/installs). */
function trackWrites(page, pattern) {
  const inner = trackRequests(page, pattern);
  return {
    get hits() {
      return inner.hits.filter((h) => h.method !== "GET");
    },
    dispose: inner.dispose,
  };
}

async function setPortabilityMode(page, sessionId, mode) {
  const res = await page.request.post("/__comfymodal_test/portability", {
    data: { sessionId, mode },
  });
  expect(res.ok()).toBeTruthy();
}

async function armExportFail(page, sessionId, mode) {
  const res = await page.request.post("/__comfymodal_test/portability-export-fail", {
    data: { sessionId, mode },
  });
  expect(res.ok()).toBeTruthy();
}

async function armManifestImport(page, sessionId, data) {
  const res = await page.request.post("/__comfymodal_test/import-manifest-arm", {
    data: { sessionId, ...data },
  });
  expect(res.ok()).toBeTruthy();
}

function makeManifestFile() {
  const manifest = {
    manifest_version: 1,
    workflow: { display: { name: "Portrait Pro" }, graph_hash: "ab01" },
    version: { version_number: 4, graph_json: {}, api_prompt_json: {} },
    mapping: { entries: [] },
    presets: [
      { preset_id: "p1", name: "Preset One", values: {}, is_default: true },
      { preset_id: "p2", name: "Preset Two", values: {} },
    ],
    models: [],
    custom_nodes: [],
    assets: [],
    metadata: {},
  };
  return { name: "portrait-pro.workflow.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(manifest)) };
}

// ── List chips ────────────────────────────────────────────────────────────

test.describe("G12 portability list chips", () => {
  test("28. null summary → Not analyzed; after Check → Medium chip appears", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("workflows");
      const chip = page.locator(`${CARD("wf_text2img")} [data-testid="portability-chip"]`);
      await expect(chip).toHaveText("Not analyzed");

      // Open the workflow and run Check portability (default armed mode: matrix → medium).
      await page.locator(CARD("wf_text2img")).click();
      await expect(page.getByTestId("workflow-detail")).toBeVisible({ timeout: 15000 });
      await page.getByTestId("portability-check-button").click();
      await expect(page.getByTestId("portability-risk")).toHaveText("Medium", { timeout: 15000 });

      // Back to the library: the refetched list carries the fresh Medium chip.
      await page.getByRole("button", { name: /Back to Workflows/ }).click();
      await expect(page.locator(CARD("wf_text2img"))).toBeVisible({ timeout: 15000 });
      await expect(page.locator(`${CARD("wf_text2img")} [data-testid="portability-chip"]`)).toHaveText("Medium");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("29. seeded stale=true renders Stale; fresh check clears it", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("workflows");
      const chip = page.locator(`${CARD("wf_incomplete")} [data-testid="portability-chip"]`);
      await expect(chip).toHaveText(/Medium · Stale/);

      await page.locator(CARD("wf_incomplete")).click();
      await expect(page.getByTestId("workflow-detail")).toBeVisible({ timeout: 15000 });
      await page.getByTestId("portability-check-button").click();
      await expect(page.getByTestId("portability-risk")).toHaveText("Medium", { timeout: 15000 });
      await expect(page.getByTestId("portability-meta")).toContainText("Current cached result");

      // Refreshed summary is stale=false in the backend-derived list too.
      await page.getByRole("button", { name: /Back to Workflows/ }).click();
      await expect(page.locator(`${CARD("wf_incomplete")} [data-testid="portability-chip"]`)).toHaveText("Medium", { timeout: 15000 });

      const state = await fx.getState();
      expect(state.portabilityRequests.length).toBe(1);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("29b. seeded stale=null renders Needs check, never unquestionably current", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("workflows");
      const chip = page.locator(`${CARD("wf_interrupt")} [data-testid="portability-chip"]`);
      await expect(chip).toHaveText(/Low · Needs check/);
      // The explanation marks freshness as unverified.
      expect(await chip.getAttribute("title")).toContain("not verified");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("30. UNKNOWN main risk + UNKNOWN target stay neutral with explanation", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await setPortabilityMode(page, fx.sessionId, "unknown_main");
      await fx.gotoPage("workflows");
      await page.locator(CARD("wf_cancel")).click();
      await expect(page.getByTestId("workflow-detail")).toBeVisible({ timeout: 15000 });
      await page.getByTestId("portability-check-button").click();

      const risk = page.getByTestId("portability-risk");
      await expect(risk).toHaveText("Unknown", { timeout: 15000 });
      await expect(risk).toHaveClass(/neutral/);
      const targetRisk = page.getByTestId("portability-target-risk-runcomfy");
      await expect(targetRisk).toHaveText("Unknown");
      await expect(targetRisk).toHaveClass(/neutral/);
      await expect(page.getByTestId("portability-issues")).toContainText("could not make a defensible portability determination");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });
});

// ── Panel / matrix / environment ──────────────────────────────────────────

test.describe("G12 portability panel", () => {
  test("31+32. Medium workflow + High environment separate; six exact target rows", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("workflows");
      await page.locator(CARD("wf_text2img")).click();
      await expect(page.getByTestId("workflow-detail")).toBeVisible({ timeout: 15000 });
      await page.getByTestId("portability-check-button").click();
      await expect(page.getByTestId("portability-risk")).toHaveText("Medium", { timeout: 15000 });

      // Environment is rendered as its own distinct section with its own HIGH.
      const env = page.getByTestId("portability-environment");
      await expect(env).toBeVisible();
      await expect(env).toContainText("Source environment reproducibility");
      await expect(page.getByTestId("portability-environment-risk")).toHaveText("High");
      // The main workflow risk stays Medium — environment never recolors it.
      await expect(page.getByTestId("portability-risk")).toHaveText("Medium");

      // Exactly six target rows, frozen order, backend risks verbatim.
      const rows = [
        ["local", "Low"],
        ["modal", "Low"],
        ["runpod", "Medium"],
        ["runcomfy", "Unknown"],
        ["comfy_cloud", "High"],
        ["baseten", "Medium"],
      ];
      for (const [tid, label] of rows) {
        await expect(page.getByTestId(`portability-target-${tid}`)).toContainText(label);
      }
      // Backend-provided advice renders verbatim (rendering-only assertion).
      await expect(page.getByTestId("portability-target-comfy_cloud")).toContainText(
        "Comfy Cloud allows only curated nodes"
      );
      await expect(page.getByTestId("portability-target-runpod")).toContainText(
        "custom Docker image with pinned custom nodes"
      );
      // Issue rows carry severity + fix hints.
      await expect(page.getByTestId("portability-issues")).toContainText("Fix hint: Pin the installed revisions before exporting.");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("35a. rapid-click dedupe sends exactly one portability GET", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("workflows");
      await page.locator(CARD("wf_text2img")).click();
      await expect(page.getByTestId("workflow-detail")).toBeVisible({ timeout: 15000 });
      await expect(page.getByTestId("portability-check-button")).toBeEnabled();
      await page.evaluate(() => {
        const btn = document.querySelector('[data-testid="portability-check-button"]');
        btn.click();
        btn.click();
      });
      await expect(page.getByTestId("portability-risk")).toHaveText("Medium", { timeout: 15000 });
      const state = await fx.getState();
      expect(state.portabilityRequests.length).toBe(1);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("35b. version switch shows only the corresponding report", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("workflows");
      await page.locator(CARD("wf_text2img")).click();
      await expect(page.getByTestId("workflow-detail")).toBeVisible({ timeout: 15000 });
      await page.getByTestId("portability-check-button").click();
      await expect(page.getByTestId("portability-version-context")).toContainText("wv1_latest", { timeout: 15000 });

      // Switch to the older immutable version → panel resets truthfully.
      await page.locator('[data-version-id="wv1_old"]').click();
      await expect(page.getByTestId("portability-not-analyzed")).toBeVisible({ timeout: 15000 });
      await expect(page.getByTestId("portability-risk")).toHaveCount(0);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("35d. armed LOW and HIGH reports render their distinct states", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await setPortabilityMode(page, fx.sessionId, "low");
      await fx.gotoPage("workflows");
      await page.locator(CARD("wf_cancel")).click();
      await expect(page.getByTestId("workflow-detail")).toBeVisible({ timeout: 15000 });
      await page.getByTestId("portability-check-button").click();
      const risk = page.getByTestId("portability-risk");
      await expect(risk).toHaveText("Low", { timeout: 15000 });
      await expect(risk).toHaveClass(/ok/);
      await expect(page.getByTestId("portability-issues")).toHaveCount(0);

      // Recheck with HIGH armed: state flips truthfully, no client inference.
      await setPortabilityMode(page, fx.sessionId, "high");
      await page.getByTestId("portability-check-button").click();
      await expect(risk).toHaveText("High", { timeout: 15000 });
      await expect(risk).toHaveClass(/error/);
      await expect(page.getByTestId("portability-issues")).toContainText(
        "Required checkpoint 'krea_model.safetensors' is missing"
      );
      await expect(page.getByTestId("portability-issues")).toContainText(
        "Fix hint: Add the model to the Model Library with a source URL."
      );
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("35c. request failure shows bounded error; retry succeeds", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("workflows");
      await page.locator(CARD("wf_cancel")).click();
      await expect(page.getByTestId("workflow-detail")).toBeVisible({ timeout: 15000 });

      await page.route("**/versions/wv_cancel/portability", (route) =>
        route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ status: "error", message: "analysis exploded" }),
        })
      );
      await page.getByTestId("portability-check-button").click();
      await expect(page.getByTestId("portability-error")).toContainText("Could not check portability", { timeout: 15000 });
      await expect(page.getByTestId("portability-error")).toContainText("analysis exploded");

      await page.unroute("**/versions/wv_cancel/portability");
      await page.getByTestId("portability-check-button").click();
      await expect(page.getByTestId("portability-risk")).toHaveText("Medium", { timeout: 15000 });
      // The armed 500 legitimately logs a resource-load console error.
      fx.assertNoConsoleErrors(["Failed to load resource.*500"]);
    } finally {
      fx.guard.dispose();
    }
  });
});

// ── Export ────────────────────────────────────────────────────────────────

test.describe("G12 manifest export", () => {
  test("33. presets default OFF, toggle sends 1, filename honored, dedupe, credential 409", async ({ page }) => {
    const fx = await setupFakeTest(page);
    // Exports are GETs; any write against workflows/run would be a mutation.
    const mutations = trackWrites(page, /\/comfymodal\/studio\/(workflows|run)/);
    // Chromium re-requests attachment responses internally for the download
    // manager (invisible to page events), so USER-facing dedupe is asserted
    // on PAGE requests + download events; the server log carries the
    // include_presets truth differentially.
    const exportReqs = trackRequests(page, /\/export\?include_presets=/);
    const countExports = async () => (await fx.getState()).manifestExports.length;
    try {
      await fx.gotoPage("workflows");
      await page.locator(CARD("wf_text2img")).click();
      await expect(page.getByTestId("workflow-detail")).toBeVisible({ timeout: 15000 });

      // Open the export popover.
      await page.getByTestId("portability-export-button").click();
      const cb = page.getByTestId("portability-export-include-presets");
      await expect(cb).not.toBeChecked();

      // Double-click dedupe: one user click-worth of work only.
      let before = await countExports();
      const dlPromise = page.waitForEvent("download");
      await page.evaluate(() => {
        const btn = document.querySelector('[data-testid="portability-export-confirm"]');
        btn.click();
        btn.click();
      });
      const dl = await dlPromise;
      expect(dl.suggestedFilename()).toBe("Text2Img_Workflow-v2-ab010101.workflow.json");
      expect(exportReqs.hits.length).toBe(1);
      let state = await fx.getState();
      expect(state.manifestExports.length).toBeGreaterThanOrEqual(before + 1);
      expect(state.manifestExports[state.manifestExports.length - 1].include_presets).toBe(false);

      // Toggle presets ON → query include_presets=1.
      before = await countExports();
      await page.getByTestId("portability-export-include-presets").check();
      const dlPromise2 = page.waitForEvent("download");
      await page.getByTestId("portability-export-confirm").click();
      const dl2 = await dlPromise2;
      expect(dl2.suggestedFilename()).toBe("Text2Img_Workflow-v2-ab010101.workflow.json");
      expect(exportReqs.hits.length).toBe(2);
      state = await fx.getState();
      expect(state.manifestExports.length).toBeGreaterThanOrEqual(before + 1);
      expect(state.manifestExports[state.manifestExports.length - 1].include_presets).toBe(true);

      // No workflow mutation / run request fired by exports.
      expect(mutations.hits).toEqual([]);

      // One-shot credential refusal: truthful message, no secret echoed, no
      // security disabling suggested, then the next attempt succeeds.
      before = await countExports();
      await armExportFail(page, fx.sessionId, "credential");
      await page.getByTestId("portability-export-confirm").click();
      await expect(page.getByTestId("portability-export-error")).toContainText("credential-like values", { timeout: 15000 });
      expect(await countExports()).toBe(before); // refusal is not an export
      await page.getByTestId("portability-export-confirm").click();
      await expect(page.getByTestId("portability-export-done")).toBeVisible({ timeout: 15000 });
      // The armed 409 legitimately logs a resource-load console error.
      fx.assertNoConsoleErrors(["Failed to load resource.*409"]);
    } finally {
      mutations.dispose();
      exportReqs.dispose();
      fx.guard.dispose();
    }
  });
});

// ── Import ────────────────────────────────────────────────────────────────

test.describe("G12 manifest import", () => {
  test("34. dry-run first, invalid blocks commit, deps allow commit, preset policies, success opens", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const runs = trackRequests(page, /\/comfymodal\/studio\/run(\?|$)|install-request|models\/download|custom-nodes\/install/);
    try {
      await fx.gotoPage("workflows");
      await page.getByTestId("workflows-import-manifest-button").click();
      const dialog = page.getByTestId("import-manifest-dialog");
      await expect(dialog).toBeVisible();

      // File selection alone sends exactly ONE dry-run and NO commit.
      await page.getByTestId("import-manifest-file").setInputFiles(makeManifestFile());
      await expect(page.getByTestId("import-manifest-preview")).toBeVisible({ timeout: 15000 });
      let state = await fx.getState();
      expect(state.manifestImports.length).toBe(1);
      expect(state.manifestImports[0].dry_run).toBe(true);

      // Separated truths all render.
      await expect(page.getByTestId("import-manifest-validity")).toHaveText("Valid");
      await expect(page.getByTestId("import-manifest-dependencies")).toContainText("All resolved");
      await expect(page.getByTestId("import-manifest-portability")).toHaveText("Medium");
      await expect(page.getByTestId("import-manifest-will-create")).toContainText("2 presets");
      await expect(page.getByTestId("import-manifest-proposed-name")).toContainText("Portrait Pro (imported)");
      await expect(page.getByTestId("import-manifest-proposed-name")).toContainText("existing workflows with a matching name: Portrait Pro");

      // Preset policies default OFF; apply-default gated behind presets + candidate.
      const presetsCb = page.getByTestId("import-manifest-presets");
      const defaultCb = page.getByTestId("import-manifest-apply-default");
      await expect(presetsCb).not.toBeChecked();
      await expect(defaultCb).toBeDisabled();
      await presetsCb.check();
      await expect(defaultCb).toBeEnabled();
      await expect(defaultCb).not.toBeChecked();
      await defaultCb.check();

      // Commit sends the EXACT policy pair.
      await page.getByTestId("import-manifest-commit").click();
      await expect(page.getByTestId("import-manifest-success")).toBeVisible({ timeout: 15000 });
      state = await fx.getState();
      expect(state.manifestImports.length).toBe(2);
      expect(state.manifestImports[1]).toEqual({
        dry_run: false,
        import_presets: true,
        apply_default_preset: true,
      });
      await expect(page.getByTestId("import-manifest-created")).toContainText("2 presets");
      await expect(page.getByTestId("import-manifest-provenance")).toContainText("foreign ids");

      // Success opens the NEW local workflow; nothing auto-runs.
      await page.getByTestId("import-manifest-open").click();
      await expect(page.getByTestId("workflow-detail")).toBeVisible({ timeout: 15000 });
      await expect(page.getByTestId("workflow-detail-name")).toHaveText("Portrait Pro (imported)");
      expect(runs.hits).toEqual([]);
      fx.assertNoConsoleErrors();
    } finally {
      runs.dispose();
      fx.guard.dispose();
    }
  });

  test("34b. invalid manifest shows ALL issues and no commit control path", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await armManifestImport(page, fx.sessionId, { preview_mode: "invalid" });
      await fx.gotoPage("workflows");
      await page.getByTestId("workflows-import-manifest-button").click();
      await page.getByTestId("import-manifest-file").setInputFiles(makeManifestFile());
      await expect(page.getByTestId("import-manifest-preview")).toBeVisible({ timeout: 15000 });

      await expect(page.getByTestId("import-manifest-validity")).toHaveText("Invalid");
      const issues = page.getByTestId("import-manifest-issues");
      await expect(issues).toContainText("graph hash mismatch");
      await expect(issues).toContainText("unknown root section 'extras'");
      await expect(issues).toContainText("preset 'Preset B' has no values object");
      await expect(page.getByTestId("import-manifest-commit")).toBeDisabled();

      const state = await fx.getState();
      expect(state.manifestImports.length).toBe(1); // dry-run only, no commit attempt possible
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("34c. missing dependencies still allow commit with explicit note", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await armManifestImport(page, fx.sessionId, { preview_mode: "missing_deps" });
      await fx.gotoPage("workflows");
      await page.getByTestId("workflows-import-manifest-button").click();
      await page.getByTestId("import-manifest-file").setInputFiles(makeManifestFile());
      await expect(page.getByTestId("import-manifest-preview")).toBeVisible({ timeout: 15000 });

      await expect(page.getByTestId("import-manifest-validity")).toHaveText("Valid");
      await expect(page.getByTestId("import-manifest-dependencies")).toContainText("need attention");
      await expect(page.getByTestId("import-manifest-deps-note")).toContainText(
        "Import is allowed, but the Workflow may not run until dependencies are resolved"
      );
      await expect(page.getByTestId("import-manifest-commit")).toBeEnabled();
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("34d. commit failure keeps preview recoverable; defaults are OFF", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await armManifestImport(page, fx.sessionId, { commit_fail_once: true });
      await fx.gotoPage("workflows");
      await page.getByTestId("workflows-import-manifest-button").click();
      await page.getByTestId("import-manifest-file").setInputFiles(makeManifestFile());
      await expect(page.getByTestId("import-manifest-preview")).toBeVisible({ timeout: 15000 });

      // Defaults OFF end-to-end: commit without touching any checkbox.
      await page.getByTestId("import-manifest-commit").click();
      await expect(page.getByTestId("import-manifest-commit-error")).toContainText("Simulated atomic import failure", { timeout: 15000 });
      await expect(page.getByTestId("import-manifest-commit-error")).toContainText("Nothing was created");
      await expect(page.getByTestId("import-manifest-preview")).toBeVisible();

      // Retry where safe: disarm server-side, then succeed.
      await armManifestImport(page, fx.sessionId, { commit_fail_once: false });
      await page.getByTestId("import-manifest-commit").click();
      await expect(page.getByTestId("import-manifest-success")).toBeVisible({ timeout: 15000 });
      const state = await fx.getState();
      const commits = state.manifestImports.filter((i) => !i.dry_run);
      expect(commits.length).toBe(2);
      expect(commits[0]).toEqual({ dry_run: false, import_presets: false, apply_default_preset: false });
      expect(commits[1]).toEqual({ dry_run: false, import_presets: false, apply_default_preset: false });
      // The armed 500 legitimately logs a resource-load console error.
      fx.assertNoConsoleErrors(["Failed to load resource.*500"]);
    } finally {
      fx.guard.dispose();
    }
  });

  test("34f. server 413 is handled truthfully; no commit follows", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      // Backend 413 remains authoritative even when the client guard passes.
      await page.route("**/studio/workflows/import-manifest*", (route) =>
        route.fulfill({
          status: 413,
          contentType: "application/json",
          body: JSON.stringify({ status: "error", message: "manifest payload exceeds 10485760 bytes" }),
        })
      );
      await fx.gotoPage("workflows");
      await page.getByTestId("workflows-import-manifest-button").click();
      await page.getByTestId("import-manifest-file").setInputFiles(makeManifestFile());
      await expect(page.getByTestId("import-manifest-preview-error")).toContainText(
        "manifest payload exceeds", { timeout: 15000 }
      );
      await expect(page.getByTestId("import-manifest-commit")).toHaveCount(0);
      const state = await fx.getState();
      expect(state.manifestImports.length).toBe(0);
      fx.assertNoConsoleErrors(["Failed to load resource.*413"]);
    } finally {
      fx.guard.dispose();
    }
  });

  test("34e. >10 MiB client guard sends nothing", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("workflows");
      await page.getByTestId("workflows-import-manifest-button").click();
      const big = Buffer.alloc(10 * 1024 * 1024 + 1, 0x7b);
      await page.getByTestId("import-manifest-file").setInputFiles({
        name: "big.workflow.json", mimeType: "application/json", buffer: big,
      });
      await expect(page.getByTestId("import-manifest-too-large")).toBeVisible({ timeout: 15000 });
      const state = await fx.getState();
      expect(state.manifestImports.length).toBe(0);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });
});
