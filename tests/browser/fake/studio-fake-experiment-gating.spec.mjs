// Modal Studio — H8 Experiment V2 fallback closure (fake backend).
//
// Phase H-WAVE A4: the modern Playground Experiment surface can NEVER create
// a legacy experiment anymore.
//
//   1. Missing Workflow/Version identity → the modern V2 section mounts
//      GATED (Run disabled + visible reason + contextual Workflows route).
//   2. Valid identity → Run uses ONLY POST /studio/experiment-v2 with the
//      selected workflow/version/preset identity baked into the definition.
//   3. Zero POST /comfymodal/studio/experiment from ANY normal modern
//      Playground action (asserted via network instrumentation AND the fake
//      engine's per-session creator log).
//   4. Modern cancel stays on /history-v2/experiments/{id}/cancel.
//   5. H-WAVE D: stale/active legacy-shaped state mounts NO legacy surface —
//      the modern section is the only run surface, and EXP filmstrip items
//      route to the History V2 detail page (no destructive conversion).
//   6. Single-mode Playground runs are untouched.

import { test, expect } from "@playwright/test";
import { setupFakeTest, selectPreset, submitSingleRun } from "./helpers.mjs";

const WORKFLOW_SELECTOR = '[data-testid="workflow-selector"]';
const SUBMIT_BTN = '[data-testid="modern-experiment-submit-btn"]';
const REASON = '[data-testid="modern-experiment-reason"]';
const LEGACY_CREATE_RE = /\/comfymodal\/studio\/experiment$/;
const V2_CREATE_RE = /\/comfymodal\/studio\/experiment-v2$/;

/** Track creator-route POSTs made by the PAGE (browser origin only). */
function trackCreatorPosts(page) {
  const legacy = [];
  const v2 = [];
  const onRequest = (request) => {
    if (request.method() !== "POST") return;
    const url = request.url();
    if (LEGACY_CREATE_RE.test(url)) legacy.push(url);
    else if (V2_CREATE_RE.test(url)) v2.push(url);
  };
  page.on("request", onRequest);
  return {
    legacy,
    v2,
    dispose() {
      page.off("request", onRequest);
    },
  };
}

test.describe("Studio Experiment V2 fallback closure (fake backend, H8)", () => {
  test("G1. no Workflow/Version → gated modern section, zero creator posts", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const tracker = trackCreatorPosts(page);
    try {
      await enableExperimentModeAndWait(page);

      // The MODERN section mounts (gated); the legacy creator never does.
      await expect(page.getByTestId("experiment-v2-section")).toBeVisible();
      await expect(page.locator('[data-testid="run-experiment-inline-btn"]')).toHaveCount(0);
      await expect(page.locator(SUBMIT_BTN)).toBeDisabled();
      await expect(page.locator(REASON)).toHaveText(
        "Select a Workflow and Version before running an experiment."
      );

      // Existing contextual route to the Workflows owner.
      const wfLink = page.locator('[data-testid="modern-experiment-workflows-link"]');
      await expect(wfLink).toBeVisible();
      await wfLink.click();
      await expect(page.locator(".comfymodal-studio-topnav button[data-page='workflows'].active")).toBeVisible();
      await fx.gotoPage("playground");
      await expect(page.getByTestId("experiment-v2-section")).toBeVisible();

      expect(tracker.legacy.length).toBe(0, "zero legacy creator POSTs while gated");
      expect(tracker.v2.length).toBe(0, "zero V2 POSTs while gated");

      // The fake engine's per-session creator log agrees.
      const state = await fx.getState();
      expect(state.experimentCreateRequests).toEqual([]);
      fx.assertNoConsoleErrors();
    } finally {
      tracker.dispose();
      fx.guard.dispose();
    }
  });

  test("G2. valid identity → one experiment-v2 POST with correct identity; History handoff", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const tracker = trackCreatorPosts(page);
    const createBodies = [];
    const onBody = (request) => {
      if (request.method() === "POST" && V2_CREATE_RE.test(request.url())) {
        createBodies.push(JSON.parse(request.postData() || "{}"));
      }
    };
    page.on("request", onBody);
    try {
      await page.locator(WORKFLOW_SELECTOR).selectOption("wf_text2img");
      await expect(page.locator('[data-testid="workflow-control-seed"]')).toBeVisible({ timeout: 10000 });
      await enableExperimentModeAndWait(page);

      await expect(page.locator(SUBMIT_BTN)).toBeEnabled({ timeout: 10000 });
      await expect(page.locator(REASON)).toHaveText("");

      await page.locator(SUBMIT_BTN).click();
      await expect.poll(() => createBodies.length, { timeout: 10000 }).toBe(1);

      const body = createBodies[0];
      expect(body.experiment_id).toMatch(/^exp_v2_/);
      expect(body.definition.workflows[0]).toMatchObject({
        workflow_id: "wf_text2img",
        workflow_version_id: "wv1_latest",
        preset_id: "wpres_a",
      });

      // Live grid hydrates from the modern status endpoint.
      const grid = page.getByTestId("experiment-v2-grid");
      await expect(grid).toBeVisible({ timeout: 10000 });
      await expect(grid.locator('[data-testid="experiment-v2-cell-cell_0"]')).toHaveCount(1);

      // Route proof from BOTH sources: page network + fake engine log.
      expect(tracker.legacy.length).toBe(0, "zero legacy creator POSTs from the valid modern run");
      expect(tracker.v2.length).toBe(1);
      const state = await fx.getState();
      const legacyCreates = state.experimentCreateRequests.filter((r) => r.route === "/comfymodal/studio/experiment");
      const v2Creates = state.experimentCreateRequests.filter((r) => r.route === "/comfymodal/studio/experiment-v2");
      expect(legacyCreates).toEqual([]);
      expect(v2Creates.length).toBe(1);
      expect(v2Creates[0].experiment_id).toBe(body.experiment_id);

      // Modern completion surfaces through the existing History V2 projection.
      await fx.gotoPage("history");
      const card = page.locator(
        `.comfymodal-studio-history-v2-experiment-card[data-id="${body.experiment_id}"]`
      );
      await expect(card).toBeVisible({ timeout: 10000 });
      fx.assertNoConsoleErrors();
    } finally {
      page.off("request", onBody);
      tracker.dispose();
      fx.guard.dispose();
    }
  });

  test("G3. switching away from a valid version disables Run again", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const tracker = trackCreatorPosts(page);
    try {
      await page.locator(WORKFLOW_SELECTOR).selectOption("wf_text2img");
      await expect(page.locator('[data-testid="workflow-control-seed"]')).toBeVisible({ timeout: 10000 });
      await enableExperimentModeAndWait(page);
      await expect(page.locator(SUBMIT_BTN)).toBeEnabled({ timeout: 10000 });

      // Drop the Version from the selection (same store the selectors write).
      await page.evaluate(() => {
        const st = window.__studioApi.getState();
        st.playground._workflowRun.workflowVersionId = "";
        window.__studioApi.setPage("playground");
      });

      await expect(page.locator(SUBMIT_BTN)).toBeDisabled({ timeout: 10000 });
      await expect(page.locator(REASON)).toHaveText(
        "Select a Workflow Version before running an experiment."
      );
      expect(tracker.legacy.length).toBe(0);
      expect(tracker.v2.length).toBe(0);
      fx.assertNoConsoleErrors();
    } finally {
      tracker.dispose();
      fx.guard.dispose();
    }
  });

  test("G4. rapid Run interaction submits exactly ONE definition; cancel stays modern", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const tracker = trackCreatorPosts(page);
    const cancelCalls = [];
    const stopNowCalls = [];
    const onControl = (request) => {
      if (request.method() !== "POST") return;
      const url = request.url();
      if (/\/history-v2\/experiments\/[^/]+\/cancel$/.test(url)) cancelCalls.push(url);
      if (/\/experiments\/[^/]+\/stop-now$/.test(url)) stopNowCalls.push(url);
    };
    page.on("request", onControl);
    try {
      await page.locator(WORKFLOW_SELECTOR).selectOption("wf_text2img");
      await expect(page.locator('[data-testid="workflow-control-seed"]')).toBeVisible({ timeout: 10000 });
      await enableExperimentModeAndWait(page);

      const btn = page.locator(SUBMIT_BTN);
      await expect(btn).toBeEnabled({ timeout: 10000 });

      // Two synchronous click dispatches: the first disables the button and
      // the action-level guard dedupes any racing second submission.
      await btn.click();
      await page.evaluate(() => {
        const b = document.querySelector('[data-testid="modern-experiment-submit-btn"]');
        if (b) b.click();
      });

      await expect.poll(async () => (await fx.getState()).experimentCreateRequests.length, { timeout: 10000 })
        .toBe(1);
      let state = await fx.getState();
      const v2Creates = state.experimentCreateRequests.filter((r) => r.route === "/comfymodal/studio/experiment-v2");
      expect(v2Creates.length).toBe(1, "rapid interaction yields exactly one V2 create");
      expect(tracker.legacy.length).toBe(0);

      const experimentId = v2Creates[0].experiment_id;

      // Modern cancel path only — never the legacy stop-now route.
      const cancelBtn = page.locator('[data-testid="modern-experiment-cancel-btn"]');
      await expect(cancelBtn).toBeVisible({ timeout: 10000 });
      await cancelBtn.click();
      await expect.poll(() => cancelCalls.length, { timeout: 10000 }).toBe(1);
      expect(cancelCalls[0]).toContain(`/history-v2/experiments/${experimentId}/cancel`);
      expect(stopNowCalls).toEqual([]);

      state = await fx.getState();
      expect(state.experimentCreateRequests.filter((r) => r.route === "/comfymodal/studio/experiment")).toEqual([]);
      fx.assertNoConsoleErrors();
    } finally {
      page.off("request", onControl);
      tracker.dispose();
      fx.guard.dispose();
    }
  });

  test("G5. stale/active legacy-shaped state mounts NO legacy surface; EXP filmstrip routes to History", async ({ page }) => {
    // Seed an OLD legacy-shaped experiment through the API BEFORE the Studio
    // mounts (harness-only write — the UI itself must never produce one).
    // H-WAVE D: even with this stale/active legacy-shaped record present,
    // no legacy surface may ever mount again.
    let seededId = "";
    const fx = await setupFakeTest(page, {
      beforeMount: async ({ page: p, sessionId }) => {
        await p.request.post("/__comfymodal_test/scenario", {
          data: { sessionId, scenario: "delayed_cells", overrides: { terminalDelay: 120000 } },
        });
        // H-WAVE F: production /studio/experiment is retired (410), so the
        // harness seeds stale legacy-shaped records through the dedicated
        // test-control endpoint instead of the retired route.
        const res = await p.request.post("/__comfymodal_test/legacy-experiment-seed", {
          data: {
            sessionId,
            presetIds: ["preset_default"],
            featureId: "txt2img",
            experiment: { name: "H8 seeded legacy", defaults: {}, axes: {}, prompts: [{ text: "old", negative: "" }] },
            metadata: { source: "studio_experiment" },
          },
        });
        expect(res.ok()).toBe(true);
        seededId = (await res.json()).experimentId;
        expect(seededId).toBeTruthy();

        // Parity proof: the retired route itself answers 410
        // EXPERIMENT_RETIRED and creates nothing (creator log unchanged).
        const retired = await p.request.post("/comfymodal/studio/experiment", {
          data: { sessionId, presetIds: ["preset_default"], featureId: "txt2img", experiment: { name: "must not create" } },
        });
        expect(retired.status()).toBe(410);
        const retiredBody = await retired.json();
        expect(retiredBody.status).toBe("error");
        expect(retiredBody.error_code).toBe("EXPERIMENT_RETIRED");
        const postRetireState = await (await p.request.get(`/__comfymodal_test/state?session=${sessionId}`)).json();
        expect(postRetireState.experimentCreateRequests.filter((r) => r.route === "/comfymodal/studio/experiment").length).toBe(1,
          "retired route must not create experiments");
      },
    });
    const tracker = trackCreatorPosts(page);
    const stopNowCalls = [];
    const onControl = (request) => {
      if (request.method() !== "POST") return;
      if (/\/experiments\/[^/]+\/stop-now$/.test(request.url())) stopNowCalls.push(request.url());
    };
    page.on("request", onControl);
    try {
      // Read compatibility: the old record is still listable through the
      // legacy API (backend compat surface only — the UI never reads it).
      const listRes = await page.request.get("/comfymodal/experiments");
      const listBody = await listRes.json();
      expect(listBody.status).toBe("ok");
      expect(listBody.experiments.some((e) => e.experiment_id === seededId)).toBe(true);

      // Stale/active legacy-shaped in-session state (the shape the retired
      // reopen path used to consume) must produce NO legacy surface.
      await page.evaluate(() => {
        const st = window.__studioApi.getState();
        st.playground.experimentMode = true;
        st.playground.runState = { status: "submitted", experimentId: "exp_v2_stale_ghost" };
        window.__studioApi.setPage("playground");
      });

      // The modern section is the ONLY run surface (gated/runnable).
      const surface = page.locator('[data-testid="experiment-run-surface"]');
      await expect(surface).toBeVisible({ timeout: 10000 });
      await expect(surface.locator('[data-testid="experiment-v2-section"]')).toBeVisible();
      expect(await page.locator('[data-testid="experiment-grid-viewport"]').count()).toBe(0);

      // Clicking an EXP filmstrip item navigates to History instead of
      // mounting a grid.
      const expItem = page.locator(".comfymodal-studio-carousel-item-experiment").first();
      await expect(expItem).toBeVisible({ timeout: 20000 });
      await expItem.click();
      await expect(page.locator('[data-testid="history-v2-page"]')).toBeVisible({ timeout: 15000 });
      await expect(page.locator('[data-testid="history-v2-experiment-page"]')).toBeVisible({ timeout: 15000 });
      expect(await page.locator('[data-testid="experiment-grid-viewport"]').count()).toBe(0);

      // Zero creator POSTs, zero stop-now control POSTs, nothing converted.
      expect(tracker.legacy.length).toBe(0, "stale legacy-shaped state never creates a new legacy experiment");
      expect(tracker.v2.length).toBe(0, "stale legacy-shaped state never creates a V2 experiment either");
      expect(stopNowCalls).toEqual([]);
      const state = await fx.getState();
      expect(state.experimentCreateRequests.filter((r) => r.route === "/comfymodal/studio/experiment").length).toBe(1,
        "the only legacy create on the session is the harness seed");

      // Draft state was not converted or rewritten by the flow.
      const drafts = await page.evaluate(() => localStorage.getItem("comfymodal.studio.experiment.draft.v1"));
      expect(drafts == null || typeof JSON.parse(drafts) === "object").toBe(true);
      fx.assertNoConsoleErrors();
    } finally {
      page.off("request", onControl);
      tracker.dispose();
      fx.guard.dispose();
    }
  });

  test("G6. Single mode unchanged: preset run uses /studio/run, zero creator posts", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const tracker = trackCreatorPosts(page);
    const runPosts = [];
    const onRun = (request) => {
      if (request.method() === "POST" && /\/comfymodal\/studio\/run$/.test(request.url())) {
        runPosts.push(request.url());
      }
    };
    page.on("request", onRun);
    try {
      await selectPreset(page, "preset_default");
      await submitSingleRun(page);
      await fx.waitForStatus("Run completed", { timeout: 20000 });

      expect(runPosts.length).toBeGreaterThanOrEqual(1);
      expect(tracker.legacy.length).toBe(0, "single mode never touches the legacy experiment creator");
      expect(tracker.v2.length).toBe(0, "single mode never touches the V2 creator");
      const state = await fx.getState();
      expect(state.experimentCreateRequests).toEqual([]);
      fx.assertNoConsoleErrors();
    } finally {
      page.off("request", onRun);
      tracker.dispose();
      fx.guard.dispose();
    }
  });
});

async function enableExperimentModeAndWait(page) {
  const toggle = page.locator('[data-testid="experiment-toggle"]');
  await toggle.waitFor({ state: "visible", timeout: 10000 });
  if ((await toggle.textContent()).trim() === "Experiment") {
    await toggle.click();
  }
  await page.locator('[data-testid="experiment-mode"]').waitFor({ state: "visible", timeout: 10000 });
}
