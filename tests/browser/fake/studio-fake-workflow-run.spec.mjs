// Modal Studio — Studio Workflow Run lane regression suite (fake backend).
//
// Drives the REAL Studio frontend (web/studio-playground.js modern workflow
// selector + web/studio-workflow-run.js) against the deterministic fake
// backend's Studio Workflow platform dataset (tests/browser/fake/fake-backend.mjs).
// Every assertion uses the actual DOM test-ids emitted by the implemented UI.
//
// Hard rules (tests/browser/fake/FAKE_BACKEND_GUIDE.md): fresh session per
// test via setupFakeTest, console guard before mount, auto-waiting locators
// / expect.poll instead of fixed sleeps, every test ends with a console-error
// check.
//
// Seeded platform (fake-backend.mjs): wf_text2img (versions wv1_latest v2 +
// wv1_old v1, presets wpres_a/wpres_b + wpres_old_a/wpres_old_b), wf_incomplete
// (wv_incomplete, state.runnable=false: missing mapping + missing custom node),
// wf_fail (runnable, POST always errors), wf_cancel / wf_interrupt (runnable,
// settle on the pending scenario terminal via the scenario engine).
//
// Adaptations to the ACTUAL UI (kept the spec intent):
//   - 0-preservation is exercised via the SEED control (required, min -1):
//     the STEPS control is required with min 1, so 0 there would legitimately
//     gate the run — the spec's "set steps to 0 and run" cannot execute.
//   - cfg 0.0 travels as JSON 0 (0 === 0.0 in JS) — the assertion checks the
//     NUMBER type survives verbatim.
//   - Workflows-page handoff is consumed IN THE SAME SESSION:
//     renderWorkflowSelector re-checks the one-shot handoff even when the
//     init promise is already settled, so clicking the workflows Run button
//     applies the exact workflow/version/preset immediately on the Playground
//     and clears the key. The reload in the test verifies the persisted
//     selection, not the handoff.
//   - Model-role enum options get three distinct suffixes: compatible+
//     installed → no suffix; compatible+missing → "(missing)"; known-
//     incompatible → "(incompatible)". Selecting a known-incompatible model
//     blocks Run (disabled button + verbatim "not compatible" reason in the
//     gating line) until a compatible model is selected.

import { test, expect } from "@playwright/test";
import { setupFakeTest } from "./helpers.mjs";

const RUN_BTN = '[data-testid="run-btn"]';
const WF_SELECTOR = '[data-testid="workflow-selector"]';
const VER_SELECTOR = '[data-testid="workflow-version-selector"]';
const PRESET_SELECTOR = '[data-testid="workflow-preset-selector"]';
const GATING = '[data-testid="workflow-run-gating"]';
const CONTROLS = '[data-testid="workflow-mapped-controls"]';

// ── Spec-scoped helpers ──────────────────────────────────────────────────

async function selectWorkflowOption(page, workflowId) {
  await page.locator(WF_SELECTOR).selectOption(workflowId);
  // The mapped-controls container only renders when the run-context bundle
  // arrives with a mapping; wait for a seed control as the hydration signal.
  await expect(page.locator('[data-testid="workflow-control-seed"]')).toBeVisible({ timeout: 10000 });
  await expect(page.locator(WF_SELECTOR)).toHaveValue(workflowId);
}

async function runModernAndWait(page, fx) {
  await expect(page.locator(RUN_BTN)).toBeEnabled({ timeout: 10000 });
  await page.locator(RUN_BTN).click();
  await fx.waitForStatus("Run completed", { timeout: 15000 });
}

/** Read the latest captured modern workflow-run body from session state. */
async function latestWorkflowRun(fx) {
  const state = await fx.getState();
  const runs = state.workflowRuns || [];
  return runs.length ? runs[runs.length - 1] : null;
}

async function readDiagnostics(page) {
  return page.evaluate(() => {
    if (window.__studioLastRunDiagnostics) return window.__studioLastRunDiagnostics;
    try {
      const api = window.__studioApi;
      if (api && typeof api.getState === "function") {
        const st = api.getState();
        if (st && st.playground && st.playground._runDiagnostics) {
          return st.playground._runDiagnostics;
        }
      }
    } catch (e) { /* best-effort */ }
    return null;
  });
}

// ── Suite ────────────────────────────────────────────────────────────────

test.describe("Studio Workflow Run (fake backend)", () => {
  test("1. workflow list loads into playground selectors", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      const selector = page.locator(WF_SELECTOR);
      await expect(selector).toBeVisible({ timeout: 10000 });
      // Options inside a closed <select> are reported hidden — assert the
      // option VALUES instead of visibility.
      const values = await selector.locator("option").evaluateAll((els) =>
        els.map((o) => o.getAttribute("value"))
      );
      expect(values).toContain("wf_text2img");
      expect(values).toContain("wf_incomplete");
      await expect(selector.locator('option[value="wf_text2img"]')).toHaveText(/Text2Img Workflow/);
      await expect(selector.locator('option[value="wf_incomplete"]')).toHaveText(/Incomplete Workflow/);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("2. current version field follows selected workflow", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await selectWorkflowOption(page, "wf_text2img");
      const versionField = page.locator(VER_SELECTOR);
      await expect(versionField.locator("option")).toHaveCount(0);
      await expect(versionField).toHaveAttribute("data-version-id", "wv1_latest");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("3. presets follow selected version", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await selectWorkflowOption(page, "wf_text2img");
      const presetSel = page.locator(PRESET_SELECTOR);
      const presets = await presetSel.locator("option").evaluateAll((els) =>
        els.map((o) => ({ value: o.getAttribute("value"), text: o.textContent }))
      );
      expect(presets.filter((o) => o.value !== "").map((o) => o.value)).toEqual([
        "wpres_a",
        "wpres_b",
      ]);
      // The workflow default preset (wpres_a) is auto-selected.
      await expect(presetSel).toHaveValue("wpres_a");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("4. current immutable version is read-only", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await selectWorkflowOption(page, "wf_text2img");
      // Default (latest) version preset seed.
      await expect(page.locator('[data-testid="workflow-input-seed"]')).toHaveValue("111");
      await expect(page.locator('[data-testid="workflow-input-steps"]')).toHaveValue("25");

      const versionField = page.locator(VER_SELECTOR);
      await expect(versionField).toHaveAttribute("data-version-id", "wv1_latest");
      await expect(versionField.locator("option")).toHaveCount(0);
      // The current version's defaults remain active; historical revisions
      // are retained for compatibility but are not Shelf choices.
      await expect(page.locator('[data-testid="workflow-input-seed"]')).toHaveValue("111");
      await expect(page.locator('[data-testid="workflow-input-steps"]')).toHaveValue("25");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("5. workflows-page Run handoff preserves exact version/preset", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("workflows");
      await expect(page.getByTestId("workflows-page")).toBeVisible({ timeout: 10000 });

      // Open wf_text2img detail.
      await page.locator('[data-testid="workflow-card"][data-workflow-id="wf_text2img"]').click();
      await expect(page.getByTestId("workflow-detail")).toBeVisible({ timeout: 15000 });

      // Select the older immutable version (v1) in the detail page.
      await page.locator('[data-version-id="wv1_old"]').click();
      await expect(page.getByTestId("run-button")).toBeEnabled({ timeout: 15000 });

      // The admin revision Run handoff preserves workflow + selected version
      // + that revision's default preset (wpres_old_a) and navigates to the Playground. The
      // handoff is consumed IN THE SAME SESSION: the Playground applies the
      // exact workflow/version/preset immediately (no reload needed) and shows
      // the "from Workflows" notice.
      await page.getByTestId("run-button").click();
      await expect(page.locator(WF_SELECTOR)).toHaveValue("wf_text2img", { timeout: 15000 });
      await expect(page.locator(VER_SELECTOR)).toHaveAttribute("data-version-id", "wv1_old");
      await expect(page.locator(PRESET_SELECTOR)).toHaveValue("wpres_old_a");
      await expect(page.locator('[data-testid="workflow-handoff-notice"]')).toBeVisible();

      // The one-shot handoff is consumed AND cleared from storage after the
      // successful application…
      const handoffAfter = await page.evaluate(() => {
        try { return localStorage.getItem("comfymodal.studio.playground.workflow-handoff.v1"); }
        catch (e) { return null; }
      });
      expect(handoffAfter).toBeNull();
      // …while the persistent workflow selection remains for future loads.
      const persisted = await page.evaluate(() => {
        try {
          const raw = localStorage.getItem("comfymodal.studio.playground.workflow.v1");
          return raw ? JSON.parse(raw) : null;
        } catch (e) { return null; }
      });
      expect(persisted).toBeTruthy();
      expect(persisted.workflowId).toBe("wf_text2img");
      expect(persisted.workflowVersionId).toBe("wv1_old");
      expect(persisted.presetId).toBe("wpres_old_a");

      // A full reload returns to the Workflow's current version. The explicit
      // historical handoff is not an ordinary Shelf restore path.
      await fx.reload();
      await expect(page.locator(WF_SELECTOR)).toHaveValue("wf_text2img", { timeout: 15000 });
      await expect(page.locator(VER_SELECTOR)).toHaveAttribute("data-version-id", "wv1_latest");
      await expect(page.locator(PRESET_SELECTOR)).toHaveValue("wpres_a");
      const handoffAfterReload = await page.evaluate(() => {
        try { return localStorage.getItem("comfymodal.studio.playground.workflow-handoff.v1"); }
        catch (e) { return null; }
      });
      expect(handoffAfterReload).toBeNull();
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("6. handoff key exists before Run navigation and is consumed exactly once", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("workflows");
      await expect(page.getByTestId("workflows-page")).toBeVisible({ timeout: 10000 });

      // Open wf_text2img detail and select the older immutable version.
      await page.locator('[data-testid="workflow-card"][data-workflow-id="wf_text2img"]').click();
      await expect(page.getByTestId("workflow-detail")).toBeVisible({ timeout: 15000 });
      await page.locator('[data-version-id="wv1_old"]').click();
      await expect(page.getByTestId("run-button")).toBeEnabled({ timeout: 15000 });

      // BEFORE Run: no handoff has been written yet.
      const handoffBefore = await page.evaluate(() => {
        try { return localStorage.getItem("comfymodal.studio.playground.workflow-handoff.v1"); }
        catch (e) { return null; }
      });
      expect(handoffBefore).toBeNull();

      // Run: the one-shot handoff is applied IN THE SAME SESSION and then
      // consumed (cleared from storage).
      await page.getByTestId("run-button").click();
      await expect(page.locator(WF_SELECTOR)).toHaveValue("wf_text2img", { timeout: 15000 });
      await expect(page.locator(VER_SELECTOR)).toHaveAttribute("data-version-id", "wv1_old");
      await expect(page.locator(PRESET_SELECTOR)).toHaveValue("wpres_old_a");
      await expect(page.locator('[data-testid="workflow-handoff-notice"]')).toBeVisible();

      const handoffAfter = await page.evaluate(() => {
        try { return localStorage.getItem("comfymodal.studio.playground.workflow-handoff.v1"); }
        catch (e) { return null; }
      });
      expect(handoffAfter).toBeNull();

      // A SECOND same-session Workflows→Playground navigation must NOT
      // re-apply the already-consumed handoff: run a different workflow and
      // confirm the NEW selection wins (no stale handoff reapplied).
      await fx.gotoPage("workflows");
      await expect(page.getByTestId("workflows-page")).toBeVisible({ timeout: 10000 });
      // The workflows page restores the previously opened detail in the same
      // session; return to the card list before opening a different workflow.
      await page.getByRole("button", { name: /Back to Workflows/ }).click();
      await expect(
        page.locator('[data-testid="workflow-card"][data-workflow-id="wf_text2img"]')
      ).toBeVisible({ timeout: 10000 });
      await page.locator('[data-testid="workflow-card"][data-workflow-id="wf_fail"]').click();
      await expect(page.getByTestId("workflow-detail")).toBeVisible({ timeout: 15000 });
      await page.locator('[data-version-id="wv_fail"]').click();
      await expect(page.getByTestId("run-button")).toBeEnabled({ timeout: 15000 });
      await page.getByTestId("run-button").click();
      await expect(page.locator(WF_SELECTOR)).toHaveValue("wf_fail", { timeout: 15000 });
      await expect(page.locator(VER_SELECTOR)).toHaveAttribute("data-version-id", "wv_fail");
      await expect(page.locator(PRESET_SELECTOR)).toHaveValue("wpres_fail");

      const handoffFinal = await page.evaluate(() => {
        try { return localStorage.getItem("comfymodal.studio.playground.workflow-handoff.v1"); }
        catch (e) { return null; }
      });
      expect(handoffFinal).toBeNull();
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("7. invalid handoff is consumed and handled explicitly", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      // Simulate a stale/bogus handoff (the referenced workflow no longer
      // exists): the Playground must consume the one-shot key even on failure
      // and never select the bogus workflow.
      await page.evaluate(() => {
        try {
          localStorage.setItem(
            "comfymodal.studio.playground.workflow-handoff.v1",
            JSON.stringify({ workflowId: "wf_does_not_exist", workflowVersionId: "", presetId: "" })
          );
        } catch (e) { /* ignore */ }
      });
      await fx.gotoPage("playground");

      // Consumed exactly once even on failure: the key is gone.
      await expect
        .poll(async () => {
          return page.evaluate(() => {
            try { return localStorage.getItem("comfymodal.studio.playground.workflow-handoff.v1"); }
            catch (e) { return null; }
          });
        }, { timeout: 10000, message: "invalid handoff should be consumed even on failure" })
        .toBeNull();

      // The bogus workflow is never selected: the selector stays empty.
      await expect(page.locator(WF_SELECTOR)).toHaveValue("");
      await expect(page.locator(WF_SELECTOR)).not.toHaveValue("wf_does_not_exist");

      // The failure is surfaced deterministically in the selector section
      // (_failWorkflowHandoff sets handoffError and clears the selection).
      await expect(page.locator('[data-testid="workflow-handoff-error"]')).toBeVisible({ timeout: 15000 });
      await expect(page.locator('[data-testid="workflow-handoff-error"]')).toContainText(
        "workflow has no versions",
        { timeout: 15000 }
      );

      // No page errors; the expected 404 resource log is allowlisted.
      expect(fx.guard.pageErrors.length).toBe(0);
      fx.assertNoConsoleErrors([/Failed to load resource/]);
    } finally {
      fx.guard.dispose();
    }
  });

  test("6. run-context consumed: controls for every schema role + exact enum", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await selectWorkflowOption(page, "wf_text2img");
      // One control group per mapping entry (12 roles).
      await expect(page.locator(CONTROLS).locator('[data-testid^="workflow-control-"]')).toHaveCount(12);
      const roles = await page.locator(CONTROLS).locator('[data-testid^="workflow-control-"]')
        .evaluateAll((els) => els.map((el) => el.getAttribute("data-testid").slice("workflow-control-".length)));
      expect(roles.sort()).toEqual([
        "bool_toggle", "cfg", "denoise", "height", "model", "negative_prompt",
        "prompt", "sampler", "scheduler", "seed", "steps", "width",
      ]);

      // Enum select options EXACTLY ["euler","dpmpp_2m","uni_pc"] — no extras.
      const samplerOptions = await page.locator('[data-testid="workflow-input-sampler"] option')
        .allTextContents();
      expect(samplerOptions).toEqual(["euler", "dpmpp_2m", "uni_pc"]);
      const schedulerOptions = await page.locator('[data-testid="workflow-input-scheduler"] option')
        .allTextContents();
      expect(schedulerOptions).toEqual(["normal", "karras", "sgm_uniform"]);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("7. 0 preserved verbatim as a number", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await selectWorkflowOption(page, "wf_text2img");
      // seed is required with min -1, so 0 is legal and must be transmitted
      // as the number 0 (not dropped/coerced/undefined).
      await page.locator('[data-testid="workflow-input-seed"]').fill("0");
      await expect(page.locator('[data-testid="workflow-input-seed"]')).toHaveValue("0");
      await expect(page.locator(GATING)).toHaveText("Ready to run", { timeout: 5000 });

      await runModernAndWait(page, fx);
      const run = await latestWorkflowRun(fx);
      expect(run).toBeTruthy();
      expect(run.controls.seed).toBe(0);
      expect(typeof run.controls.seed).toBe("number");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("8. 0.0 preserved as a number", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await selectWorkflowOption(page, "wf_text2img");
      await page.locator('[data-testid="workflow-input-cfg"]').fill("0");
      await expect(page.locator('[data-testid="workflow-input-cfg"]')).toHaveValue("0");
      await expect(page.locator(GATING)).toHaveText("Ready to run", { timeout: 5000 });

      await runModernAndWait(page, fx);
      const run = await latestWorkflowRun(fx);
      expect(run).toBeTruthy();
      expect(run.controls.cfg).toBe(0);
      expect(typeof run.controls.cfg).toBe("number");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("9. false preserved for the boolean role", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await selectWorkflowOption(page, "wf_text2img");
      // Default preset wpres_a sets bool_toggle=true; uncheck to false.
      const checkbox = page.locator('[data-testid="workflow-input-bool_toggle"]');
      await expect(checkbox).toBeChecked();
      await checkbox.uncheck();
      await expect(checkbox).not.toBeChecked();

      await runModernAndWait(page, fx);
      const run = await latestWorkflowRun(fx);
      expect(run).toBeTruthy();
      expect(run.controls.bool_toggle).toBe(false);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("10. incomplete workflow disables Run with verbatim backend reason", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await page.locator(WF_SELECTOR).selectOption("wf_incomplete");
      await expect(page.locator(VER_SELECTOR)).toHaveAttribute("data-version-id", "wv_incomplete", { timeout: 10000 });
      await expect(page.locator(RUN_BTN)).toBeDisabled({ timeout: 10000 });
      await expect(page.locator(GATING)).toContainText("missing mapping");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("11. missing dependency reason appears verbatim", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await page.locator(WF_SELECTOR).selectOption("wf_incomplete");
      await expect(page.locator(VER_SELECTOR)).toHaveAttribute("data-version-id", "wv_incomplete", { timeout: 10000 });
      await expect(page.locator(GATING)).toContainText("missing custom node 'SomeCustomClass'");
      await expect(page.locator(RUN_BTN)).toBeDisabled();
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("12. compatible installed model allowed", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await selectWorkflowOption(page, "wf_text2img");
      const modelSel = page.locator('[data-testid="workflow-input-model"]');
      await expect(modelSel).toBeVisible();
      // sd15_v2 is compatible + installed → no " (missing)" suffix.
      await expect(modelSel.locator('option[value="sd15_v2.safetensors"]')).toHaveText("sd15_v2.safetensors");
      await modelSel.selectOption("sd15_v2.safetensors");
      await expect(page.locator(GATING)).toHaveText("Ready to run", { timeout: 5000 });
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("13. compatible missing model surfaced with suffix", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await selectWorkflowOption(page, "wf_text2img");
      const modelSel = page.locator('[data-testid="workflow-input-model"]');
      // krea_model is compatible (in compatible_models) but not installed.
      await expect(modelSel.locator('option[value="krea_model.safetensors"]')).toHaveText(
        "krea_model.safetensors (missing)"
      );
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("14. known-incompatible model blocks Run until a compatible model is selected", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await selectWorkflowOption(page, "wf_text2img");
      const modelSel = page.locator('[data-testid="workflow-input-model"]');
      // evil_model is NOT in the workflow's compatible_models → the enum
      // option is classified known-incompatible and renders the distinct
      // "(incompatible)" suffix (compatible+missing still renders "(missing)").
      await expect(modelSel.locator('option[value="evil_model.safetensors"]')).toHaveText(
        "evil_model.safetensors (incompatible)"
      );

      // Selecting the incompatible option must block Run with a clear reason.
      await modelSel.selectOption("evil_model.safetensors");
      await expect(page.locator(RUN_BTN)).toBeDisabled({ timeout: 5000 });
      await expect(page.locator(GATING)).toContainText(
        "model 'evil_model.safetensors' is not compatible with this workflow version",
        { timeout: 5000 }
      );

      // Selecting a compatible model re-enables Run.
      await modelSel.selectOption("sd15_v2.safetensors");
      await expect(page.locator(RUN_BTN)).toBeEnabled({ timeout: 5000 });
      await expect(page.locator(GATING)).toHaveText("Ready to run", { timeout: 5000 });

      const compat = await page.evaluate(() => {
        const st = window.__studioApi.getState();
        return st && st.playground ? st.playground._workflowModelLibrary : null;
      });
      expect(Array.isArray(compat)).toBe(true);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("15. exact executable request pins the current version", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await selectWorkflowOption(page, "wf_text2img");
      await expect(page.locator(VER_SELECTOR)).toHaveAttribute("data-version-id", "wv1_latest");
      // The current version's default preset (wpres_a) is auto-selected.
      await expect(page.locator(PRESET_SELECTOR)).toHaveValue("wpres_a");

      // Override the prompt via the mapped control.
      await page.locator('[data-testid="workflow-input-prompt"]').fill("overridden modern prompt");
      await expect(page.locator('[data-testid="workflow-input-prompt"]')).toHaveValue(
        "overridden modern prompt"
      );

      await runModernAndWait(page, fx);
      const run = await latestWorkflowRun(fx);
      expect(run).toBeTruthy();
      expect(run.workflow_id).toBe("wf_text2img");
      expect(run.workflow_version_id).toBe("wv1_latest");
      expect(run.preset_id).toBe("wpres_a");
      expect(run.featureId).toBe("txt2img");
      expect(run.controls.prompt).toBe("overridden modern prompt");
      expect(run.metadata.workflow_name).toBe("Text2Img Workflow");
      expect(run.metadata.preset_name).toBe("Preset A");
      expect(run.metadata.workflow_hash).toBeTruthy();
      expect(run.metadata.source).toBe("studio_playground");

      // The modern lane never falls back to the legacy preset submission:
      // the captured request carries NO legacy preset_* identity keys and no
      // legacy experiment is created in the same session.
      expect(run.presetId).toBeUndefined();
      expect(run.preset).toBeUndefined();
      expect(run.presetLabel).toBeUndefined();
      const state = await fx.getState();
      expect(state.experiments.length).toBe(0);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("16. preset values applied without touching controls", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await selectWorkflowOption(page, "wf_text2img");
      await expect(page.locator(PRESET_SELECTOR)).toHaveValue("wpres_a");

      await runModernAndWait(page, fx);
      const run = await latestWorkflowRun(fx);
      expect(run).toBeTruthy();
      const c = run.controls;
      expect(c.seed).toBe(111);
      expect(c.steps).toBe(25);
      expect(c.prompt).toBe("preset A prompt");
      expect(c.negative_prompt).toBe("no A");
      expect(c.cfg).toBe(7.5);
      expect(c.sampler).toBe("euler");
      expect(c.scheduler).toBe("karras");
      expect(c.width).toBe(768);
      expect(c.height).toBe(768);
      expect(c.model).toBe("sd15_v2.safetensors");
      expect(c.bool_toggle).toBe(true);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("17. overrides applied after preset", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await selectWorkflowOption(page, "wf_text2img");
      // Preset seed is 111; override it.
      await page.locator('[data-testid="workflow-input-seed"]').fill("999");

      await runModernAndWait(page, fx);
      const run = await latestWorkflowRun(fx);
      expect(run).toBeTruthy();
      expect(run.controls.seed).toBe(999);
      // Unoverridden preset value still applied.
      expect(run.controls.steps).toBe(25);
      expect(run.controls.prompt).toBe("preset A prompt");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("18. topology not mutated in the executed workflow", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await selectWorkflowOption(page, "wf_text2img");
      await page.locator('[data-testid="workflow-input-steps"]').fill("31");
      await runModernAndWait(page, fx);

      // The fake server's history-v2 generation stores the executed
      // workflow_json derived from the version graph + applied controls.
      const run = await latestWorkflowRun(fx);
      expect(run).toBeTruthy();
      const detailRes = await page.request.get(
        `/comfymodal/history-v2/generations/${run.experimentId}?session=${fx.sessionId}`
      );
      expect(detailRes.ok()).toBe(true);
      const item = (await detailRes.json()).item;
      const nodeIds = Object.keys(item.workflow_json || {}).sort();
      expect(nodeIds).toEqual(["3", "4", "5", "6", "7", "8", "9"]);
      // Controls written into the mapped node inputs; graph topology intact.
      expect(item.workflow_json["3"].inputs.steps).toBe(31);
      expect(item.workflow_json["6"].inputs.text).toBe("preset A prompt");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("19. identity threaded into History V2", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await selectWorkflowOption(page, "wf_text2img");
      await runModernAndWait(page, fx);
      const run = await latestWorkflowRun(fx);
      expect(run).toBeTruthy();

      await fx.gotoPage("history");
      const card = page.locator(
        `.comfymodal-studio-history-v2-generation-card[data-id="${run.experimentId}"]`
      );
      await expect(card).toBeVisible({ timeout: 15000 });
      await expect(card.locator(".comfymodal-studio-history-v2-card-meta")).toContainText(
        "Text2Img Workflow"
      );

      // Detail overlay surfaces version + preset identity.
      await card.click();
      const overlay = page.locator('.comfymodal-studio-history-v2-overlay[aria-label="Generation detail"]');
      await expect(overlay).toBeVisible({ timeout: 10000 });
      await expect(overlay.locator(".comfymodal-studio-history-v2-row-key", { hasText: "Workflow" }).first())
        .toBeVisible();
      await expect(overlay).toContainText("Text2Img Workflow v2");
      await expect(overlay).toContainText("Preset A");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("20. history snapshot reflects the final request", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await selectWorkflowOption(page, "wf_text2img");
      // Change three params so the snapshot is not the preset default.
      await page.locator('[data-testid="workflow-input-seed"]').fill("321");
      await page.locator('[data-testid="workflow-input-steps"]').fill("17");
      await page.locator('[data-testid="workflow-input-cfg"]').fill("9.5");
      await runModernAndWait(page, fx);
      const run = await latestWorkflowRun(fx);
      expect(run).toBeTruthy();

      const detailRes = await page.request.get(
        `/comfymodal/history-v2/generations/${run.experimentId}?session=${fx.sessionId}`
      );
      expect(detailRes.ok()).toBe(true);
      const item = (await detailRes.json()).item;
      expect(item.params.seed).toBe(321);
      expect(item.params.steps).toBe(17);
      expect(item.params.cfg).toBe(9.5);
      expect(item.params.prompt === undefined || item.params.prompt === "").toBe(true);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("21. modern execution does not silently fall back", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await page.locator(WF_SELECTOR).selectOption("wf_incomplete");
      await expect(page.locator(VER_SELECTOR)).toHaveAttribute("data-version-id", "wv_incomplete", { timeout: 10000 });
      await expect(page.locator(RUN_BTN)).toBeDisabled({ timeout: 10000 });

      // Even a forced click on the disabled Run must never produce a modern
      // workflowRuns entry nor a legacy studio/run submission.
      await page.locator(RUN_BTN).click({ force: true });
      await page.waitForTimeout(600);
      const state = await fx.getState();
      expect(state.workflowRuns.length).toBe(0);
      // No legacy experiment either (the legacy run surface was untouched).
      expect(state.experiments.length).toBe(0);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("22. canonical success still works", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await selectWorkflowOption(page, "wf_text2img");
      await runModernAndWait(page, fx);
      await expect(page.locator('[data-testid="run-status-message"]')).toContainText("Run completed");
      await expect(page.locator(RUN_BTN)).toBeEnabled();
      const d = await readDiagnostics(page);
      expect(d && d.isTerminal).toBe(true);
      expect(d.status).toBe("completed");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("23. canonical failure shows the failed terminal", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await page.locator(WF_SELECTOR).selectOption("wf_fail");
      await expect(page.locator('[data-testid="workflow-control-seed"]')).toBeVisible({ timeout: 10000 });
      await expect(page.locator(RUN_BTN)).toBeEnabled({ timeout: 10000 });

      await page.locator(RUN_BTN).click();
      const section = page.locator(".comfymodal-studio-run-section");
      await expect(section).toContainText("Run Failed", { timeout: 15000 });
      await expect(section).toContainText("Simulated workflow execution failure");
      await expect(page.locator('[data-testid="error-dismiss-btn"]')).toBeVisible();
      // Never success.
      await expect(section).not.toContainText("Run completed");
      // The failed request was still captured (the modern lane never fell
      // back to a legacy surface).
      const run = await latestWorkflowRun(fx);
      expect(run && run.workflow_id).toBe("wf_fail");
      // The deliberate failure is logged by the run layer + a 400 resource
      // error — expected for this test.
      fx.assertNoConsoleErrors([/Failed to load resource/, /backend execution failure/, /execution failed/]);
    } finally {
      fx.guard.dispose();
    }
  });

  test("24. canceled run never displays success", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.setScenario("canceled");
      await selectWorkflowOption(page, "wf_cancel");
      await page.locator(RUN_BTN).click();

      await fx.waitForStatus("Run canceled.", { timeout: 20000 });
      const msg = page.locator('[data-testid="run-status-message"]').first();
      await expect(msg).toContainText("Run canceled.");
      const text = await msg.textContent();
      expect(text).not.toContain("Run completed");
      expect(text).not.toContain("completed successfully");
      await expect(page.locator(RUN_BTN)).toBeEnabled();

      const d = await readDiagnostics(page);
      expect(d && d.isTerminal).toBe(true);
      expect(d.status).toBe("canceled");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("25. interrupted run remains distinct from canceled", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.setScenario("interrupted");
      await selectWorkflowOption(page, "wf_interrupt");
      await page.locator(RUN_BTN).click();

      // Run-level terminal is canceled (backend vocabulary), but the CELL
      // carries explicit interruption evidence — never a completed status.
      await fx.waitForStatus("Run canceled.", { timeout: 20000 });
      const msg = page.locator('[data-testid="run-status-message"]').first();
      const text = await msg.textContent();
      expect(text.toLowerCase()).not.toContain("completed");
      await expect
        .poll(async () => {
          const d = await readDiagnostics(page);
          if (!d || !d.isTerminal || d.status !== "canceled") return false;
          const cells = d.cells || {};
          return Object.values(cells).some((c) => c && c.status === "interrupted");
        }, { timeout: 10000, message: "expected an interrupted cell distinct from plain canceled" })
        .toBe(true);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("26. sequential runs are isolated", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await selectWorkflowOption(page, "wf_text2img");

      // Run 1.
      await runModernAndWait(page, fx);
      const run1 = await latestWorkflowRun(fx);
      expect(run1).toBeTruthy();

      // Run 2 in the same session.
      await page.locator(RUN_BTN).click();
      await fx.waitForStatus("Run completed", { timeout: 15000 });
      const state = await fx.getState();
      expect(state.workflowRuns.length).toBe(2);
      const run2 = state.workflowRuns[1];
      expect(run2.runId).not.toBe(run1.runId);
      expect(run2.experimentId).not.toBe(run1.experimentId);

      // Distinct history generation records.
      const genIds = state.historyV2
        .filter((r) => r.kind === "generation" && r.id.startsWith("gen_wf_"))
        .map((r) => r.id);
      expect(genIds.length).toBe(2);
      expect(new Set(genIds).size).toBe(2);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("27. timing marks follow the modern-path canonical order", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await selectWorkflowOption(page, "wf_text2img");
      await runModernAndWait(page, fx);

      const d = await readDiagnostics(page);
      const marks = (d && d.marks) || [];
      expect(marks.length).toBeGreaterThan(0);
      const names = marks.map((m) => m.name);
      expect(names[0]).toBe("run_click");
      if (d && d.isTerminal) {
        expect(names[names.length - 1]).toBe("terminal");
      }
      // The modern path emits (in this order):
      // run_click < validation_start < validation_end < build_start <
      // build_end < http_invoked < backend_ack (< terminal).
      const expectedOrder = [
        "run_click",
        "validation_start",
        "validation_end",
        "build_start",
        "build_end",
        "http_invoked",
        "backend_ack",
        "terminal",
      ];
      const indexes = names.map((n) => expectedOrder.indexOf(n));
      expect(indexes.every((i) => i >= 0)).toBe(true);
      for (let i = 1; i < indexes.length; i++) {
        expect(indexes[i]).toBeGreaterThan(indexes[i - 1]);
      }
      for (const m of marks) {
        if (typeof m.deltaMs === "number") expect(m.deltaMs).toBeGreaterThanOrEqual(0);
      }
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("28. seeded experiment routes through History V2 detail; modern workflow lane untouched", async ({ page }) => {
    // H-WAVE D removed the legacy experiment grid entirely.  A V2 dataset
    // containing experiments is seeded through the fake API BEFORE mount
    // (harness-only write); the filmstrip EXP item must open the History V2
    // detail page, the retired grid viewport can never mount, and the modern
    // workflow lane must stay untouched.
    let seeded = null;
    const fx = await setupFakeTest(page, {
      beforeMount: async ({ page: p, sessionId }) => {
        const res = await p.request.post("/__comfymodal_test/history-seed", {
          data: { sessionId, scenario: "history_v2_large" },
        });
        expect(res.ok()).toBe(true);
        seeded = await res.json();
      },
    });
    expect(seeded).toMatchObject({ status: "ok", v2: true });
    const legacyCreates = [];
    const onRequest = (request) => {
      if (request.method() === "POST" && /\/comfymodal\/studio\/experiment$/.test(request.url())) {
        legacyCreates.push(request.url());
      }
    };
    page.on("request", onRequest);
    try {
      // Open the seeded experiment through the filmstrip EXP item.
      const item = page.locator(".comfymodal-studio-carousel-item-experiment").first();
      await expect(item).toBeVisible({ timeout: 20000 });
      await item.click();

      await expect(page.locator('[data-testid="history-v2-page"]')).toBeVisible({ timeout: 15000 });
      await expect(page.locator('[data-testid="history-v2-experiment-page"]')).toBeVisible({ timeout: 15000 });
      expect(await page.locator('[data-testid="experiment-grid-viewport"]').count()).toBe(0);

      // The UI itself never POSTed the legacy creator.
      expect(legacyCreates.length).toBe(0);

      // The modern workflow lane was not touched by the navigation.
      const state = await fx.getState();
      expect(state.workflowRuns.length).toBe(0);
      fx.assertNoConsoleErrors();
    } finally {
      page.off("request", onRequest);
      fx.guard.dispose();
    }
  });

  test("29. visible primary Run button is the only command target; hidden duplicate cannot hijack", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await selectWorkflowOption(page, "wf_text2img");
      await expect(page.locator(RUN_BTN)).toBeEnabled({ timeout: 10000 });

      // Inject a HIDDEN duplicate run-btn EARLIER in DOM order. If the
      // gating resolver used an unscoped first-match, the modern onclick
      // would be attached to this hidden node and the VISIBLE button would
      // keep its legacy handler — modern selection would be hijacked.
      await page.evaluate(() => {
        const dup = document.createElement("button");
        dup.setAttribute("data-testid", "run-btn");
        dup.style.display = "none";
        dup.textContent = "Run";
        dup.setAttribute("data-dup", "true");
        dup.addEventListener("click", () => { window.__hiddenDupClicked = true; });
        const runSection = document.querySelector(".comfymodal-studio-run-section");
        const panel = document.querySelector('[data-testid="control-panel"]');
        panel.insertBefore(dup, runSection);
        window.__hiddenDupClicked = false;
      });

      // Re-run gating resolution so _resolvePrimaryRunButton must pick the
      // VISIBLE button (model change → _syncWorkflowGating →
      // _syncRunButtonGating).
      await page.locator('[data-testid="workflow-input-model"]').selectOption("sd15_v2.safetensors");
      await expect(page.locator(GATING)).toHaveText("Ready to run", { timeout: 5000 });

      // Click the VISIBLE run button only.
      await page.locator(RUN_BTN).filter({ visible: true }).click();
      await fx.waitForStatus("Run completed", { timeout: 15000 });

      const run = await latestWorkflowRun(fx);
      expect(run).toBeTruthy();
      expect(run.workflow_id).toBe("wf_text2img");
      expect(run.workflow_version_id).toBe("wv1_latest");
      expect(run.preset_id).toBe("wpres_a");
      // The hidden duplicate was never the command target.
      const dupClicked = await page.evaluate(() => window.__hiddenDupClicked);
      expect(dupClicked).toBe(false);
      const state = await fx.getState();
      expect(state.experiments.length).toBe(0);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("30. legacy single-run still works when no modern workflow is selected", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.setScenario("success");
      // No modern workflow selection — the legacy preset lane is the only
      // command path (workflow selectors stay in their empty state).
      await expect(page.locator(WF_SELECTOR)).toHaveValue("", { timeout: 10000 });
      await page.locator('[data-testid="backend-select"]').selectOption("preset_default");
      await expect(page.locator('[data-testid="input-prompt"]')).toBeVisible({ timeout: 10000 });

      const runBtn = page.locator(RUN_BTN);
      await expect(runBtn).toBeEnabled({ timeout: 15000 });
      await runBtn.click();
      await fx.waitForStatus("Run completed", { timeout: 20000 });

      const state = await fx.getState();
      // A legacy experiment was created…
      expect(state.experiments.length).toBe(1);
      // …and the modern workflow lane was never touched.
      expect(state.workflowRuns.length).toBe(0);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });
});
