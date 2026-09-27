// Modal Studio — History Experiment Cancel parity + cell-menu focus (F1B).
//
// Focused fake-backend coverage for the two F1 audit findings owned by this
// lane:
//
//   1. History Experiment Cancel parity
//      - active (queued/running) experiments expose Cancel; terminal ones do
//        not expose an enabled Cancel that can only fail
//      - one explicit click = exactly ONE POST .../experiments/{id}/cancel
//      - success re-renders from the refetched DURABLE record (no optimistic
//        canceled state); canceled cells show canceled; action disappears
//      - running-cell refusal (503 CANCELLATION_UNAVAILABLE) leaves the
//        experiment truthfully running, surfaces the structured message,
//        and the control recovers/re-enables
//      - closing detail / Escape / navigating away send ZERO cancel requests
//      - experiment favorite + note survive the post-cancel refresh
//
//   2. Cell ⋮ menu ReferenceError fix
//      - opening a cell menu previously crashed on an unbound item.focus()
//        (ReferenceError pageerror; menu mounted but focus step threw)
//      - now: no errors, menu renders, the first actionable control
//        (Generate Original) receives focus, Escape closes, reopen works,
//        and the F2A Generation-backed cell favorite stays intact.
//
// Fake parity note: cancelModernExperiment mirrors production cancel
// semantics; remote_cancel_available=false (test control) reproduces the
// production 503 CANCELLATION_UNAVAILABLE path where queued cells still
// cancel atomically while running cells remain durable.

import { test, expect } from "@playwright/test";
import { setupFakeTest } from "./helpers.mjs";

const BASE_DEFINITION = {
  name: "F1B Cancel Sweep",
  feature_id: "txt2img",
  axis_labels: { x: "seed", y: "steps" },
  axes: { seed: { enabled: true, values: [111, 222] } },
  defaults: { seed: 1000, steps: 20 },
  prompts: [{ text: "deterministic fake prompt", negative: "" }],
  workflows: [
    {
      workflow_id: "wf_text2img",
      workflow_version_id: "wv1_latest",
      preset_id: "wpres_a",
      workflow_name: "Text2Img Workflow",
      preset_name: "Preset A",
    },
  ],
};

async function createExperiment(page, sessionId, experimentId, seedValues) {
  const definition = JSON.parse(JSON.stringify(BASE_DEFINITION));
  if (seedValues) definition.axes = { seed: { enabled: true, values: seedValues } };
  const res = await page.request.post("/comfymodal/studio/experiment-v2", {
    data: { sessionId, experiment_id: experimentId, name: "F1B Cancel Sweep", definition },
  });
  expect(res.status()).toBe(200);
  return res.json();
}

async function setCellStates(page, sessionId, experimentId, cells) {
  const res = await page.request.post("/__comfymodal_test/modern-experiment-state", {
    data: { sessionId, experiment_id: experimentId, cells },
  });
  expect(res.status()).toBe(200);
  return res.json();
}

function setRemoteCancel(page, sessionId, experimentId, available) {
  return page.request.post("/__comfymodal_test/modern-experiment-state", {
    data: { sessionId, experiment_id: experimentId, remote_cancel_available: available },
  });
}

/** Counts POSTs to the modern cancel route while letting them through. */
async function countCancelPosts(page) {
  const counter = { n: 0 };
  await page.route("**/history-v2/experiments/*/cancel", async (route) => {
    counter.n += 1;
    await route.continue();
  });
  return counter;
}

async function openExperimentDetail(page, experimentCardId) {
  const card = page.locator(`.comfymodal-studio-history-v2-experiment-card[data-id="${experimentCardId}"]`);
  await expect(card).toBeVisible({ timeout: 15000 });
  await card.click();
  await expect(page.locator('[data-testid="history-v2-experiment-page"]')).toBeVisible({ timeout: 10000 });
  return card;
}

test.describe("Studio History V2 experiment cancel + cell menu (fake backend, F1B)", () => {

  test("C1. active experiment shows Cancel; one click sends exactly one request and refreshes durable state", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      const expId = "exp_f1b_cancel_queued";
      const created = await createExperiment(page, fx.sessionId, expId);
      expect(created.aggregate_status).toBe("running"); // queued>0 → running per truth table

      const counter = await countCancelPosts(page);
      await fx.gotoPage("history");
      await openExperimentDetail(page, expId);

      // Active aggregate → Cancel available and enabled.
      const cancelBtn = page.locator('[data-testid="history-v2-experiment-cancel"]');
      await expect(cancelBtn).toBeVisible();
      await expect(cancelBtn).toBeEnabled();

      await cancelBtn.click();

      // Exactly ONE explicit POST for one click.
      await expect.poll(() => counter.n, { timeout: 10000 }).toBe(1);

      // Durable refresh: every cell shows canceled from server truth.
      const chips = page.locator('[data-testid="history-v2-experiment-cell"] .comfymodal-studio-history-v2-chip');
      await expect.poll(async () => {
        const texts = [];
        for (let i = 0; i < await chips.count(); i++) texts.push(await chips.nth(i).textContent());
        return texts.every((t) => t === "Canceled");
      }, { timeout: 10000 }).toBe(true);

      // Aggregate chip flips to Canceled; counts line reflects zero results.
      await expect(page.locator(".comfymodal-studio-history-v2-experiment-title-row .comfymodal-studio-history-v2-chip"))
        .toHaveText("Canceled", { timeout: 10000 });

      // No longer eligible → the action disappears (never an enabled stub).
      await expect(cancelBtn).toBeHidden({ timeout: 10000 });

      // No fabricated second scheduler/action: still exactly one request.
      await page.waitForTimeout(300);
      expect(counter.n).toBe(1);

      // Server-side durable truth matches what the UI rendered.
      const state = await fx.getState();
      const exp = state.modernExperiments.find((e) => e.experiment_id === expId);
      expect(exp.counts.canceled).toBe(2);
      expect(exp.aggregate_status).toBe("canceled");

      fx.assertNoConsoleErrors([/Failed to load resource/]);
    } finally {
      fx.guard.dispose();
    }
  });

  test("C2. terminal completed experiment exposes no enabled Cancel; close/Escape/navigation send zero cancel requests", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      const counter = await countCancelPosts(page);
      await fx.gotoPage("history");

      // Default session seed carries the terminal exp_completed.
      await openExperimentDetail(page, "exp_completed");

      const cancelBtn = page.locator('[data-testid="history-v2-experiment-cancel"]');
      await expect(cancelBtn).toBeHidden();

      // Escape on the detail page → no cancel request.
      await page.keyboard.press("Escape");
      await page.waitForTimeout(200);

      // Closing detail via Back → no cancel request.
      await page.getByRole("button", { name: "\u2190 Back to history" }).click();
      await expect(page.locator('[data-testid="history-v2-page"]')).toBeVisible({ timeout: 10000 });

      // Navigating away mid-detail → no cancel request either.
      await openExperimentDetail(page, "exp_completed");
      await fx.gotoPage("playground");
      await page.waitForTimeout(200);

      expect(counter.n).toBe(0);
      fx.assertNoConsoleErrors([/Failed to load resource/]);
    } finally {
      fx.guard.dispose();
    }
  });

  test("C3. running-cell 503 CANCELLATION_UNAVAILABLE keeps truthful running state, shows failure, recovers", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      const expId = "exp_f1b_cancel_running";
      await createExperiment(page, fx.sessionId, expId, [111, 222, 333]);
      // cell_0 completed, cell_1 running, cell_2 queued.
      await setCellStates(page, fx.sessionId, expId, [
        { cell_id: "cell_0", status: "completed" },
        { cell_id: "cell_1", status: "running" },
        { cell_id: "cell_2", status: "queued" },
      ]);
      // Production parity switch: no truthful remote-cancel primitive.
      await setRemoteCancel(page, fx.sessionId, expId, false);

      const counter = await countCancelPosts(page);
      await fx.gotoPage("history");
      await openExperimentDetail(page, expId);

      const cancelBtn = page.locator('[data-testid="history-v2-experiment-cancel"]');
      await expect(cancelBtn).toBeVisible();
      await expect(cancelBtn).toBeEnabled();
      await cancelBtn.click();

      // Exactly one refusal POST.
      await expect.poll(() => counter.n, { timeout: 10000 }).toBe(1);

      // Truthful durable state after the refetch: the experiment REMAINS
      // running; the running cell was never marked canceled; only the
      // queued cell flipped to canceled (backend atomic queued cancel).
      const titleChip = page.locator(".comfymodal-studio-history-v2-experiment-title-row .comfymodal-studio-history-v2-chip");
      await expect(titleChip).toHaveText("Running", { timeout: 10000 });
      const runningChip = page.locator(
        '[data-testid="history-v2-experiment-cell"][data-key="cell_1"] .comfymodal-studio-history-v2-chip'
      );
      await expect(runningChip).toHaveText("Running");

      // Concise truthful failure text (structured code preserved through the
      // repository normalization — no human-text parsing).
      const note = page.locator('[data-testid="history-v2-experiment-cancel-note"]');
      await expect(note).toContainText("unavailable", { timeout: 10000 });

      // Cancellation remains eligible → the button recovered/re-enabled.
      await expect(cancelBtn).toBeVisible();
      await expect(cancelBtn).toBeEnabled();

      // No unhandled rejection; the 503 resource error is the allowlisted
      // browser network log line only.
      fx.assertNoConsoleErrors([/Failed to load resource/]);

      // Durable server truth matches the UI exactly.
      const state = await fx.getState();
      const exp = state.modernExperiments.find((e) => e.experiment_id === expId);
      expect(exp.cells.find((c) => c.cell_id === "cell_1").status).toBe("running");
      expect(exp.cells.find((c) => c.cell_id === "cell_2").status).toBe("canceled");
      expect(exp.aggregate_status).toBe("running");
    } finally {
      fx.guard.dispose();
    }
  });

  test("C4. experiment favorite and note survive the post-cancel durable refresh", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      const expId = "exp_f1b_cancel_annotations";
      await createExperiment(page, fx.sessionId, expId);
      const favRes = await page.request.patch(
        `/comfymodal/history-v2/experiments/${encodeURIComponent(expId)}/favorite`,
        { data: { sessionId: fx.sessionId, favorite: true } }
      );
      expect(favRes.status()).toBe(200);
      const noteRes = await page.request.patch(
        `/comfymodal/history-v2/experiments/${encodeURIComponent(expId)}/note`,
        { data: { sessionId: fx.sessionId, note: "keep me after cancel" } }
      );
      expect(noteRes.status()).toBe(200);

      await fx.gotoPage("history");
      await openExperimentDetail(page, expId);

      const headerStar = page.locator(
        ".comfymodal-studio-history-v2-experiment-title-row .comfymodal-studio-history-v2-fav"
      );
      await expect(headerStar).toHaveAttribute("aria-pressed", "true");
      const notes = page.locator('textarea[aria-label="Note for this experiment"]');
      await expect(notes).toHaveValue("keep me after cancel");

      await page.locator('[data-testid="history-v2-experiment-cancel"]').click();

      // Refreshed page still renders both annotations from durable truth.
      await expect(
        page.locator(".comfymodal-studio-history-v2-experiment-title-row .comfymodal-studio-history-v2-fav")
      ).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
      await expect(notes).toHaveValue("keep me after cancel", { timeout: 10000 });

      // Full reload: the same truth comes back from the server (no local
      // cache involved).  After a successful cancel the aggregate is
      // "canceled", which the feed hides by default — reveal it first.
      await fx.reload();
      await fx.gotoPage("history");
      const toolbar = page.locator(".comfymodal-studio-history-v2-toolbar");
      await expect(toolbar.locator('button[data-status="canceled"]')).toBeVisible({ timeout: 10000 });
      await toolbar.locator('button[data-status="canceled"]').click();
      await openExperimentDetail(page, expId);
      await expect(
        page.locator(".comfymodal-studio-history-v2-experiment-title-row .comfymodal-studio-history-v2-fav")
      ).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
      await expect(notes).toHaveValue("keep me after cancel", { timeout: 10000 });
      fx.assertNoConsoleErrors([/Failed to load resource/]);
    } finally {
      fx.guard.dispose();
    }
  });

  test("M1. cell ⋮ menu opens with zero errors, focuses the first actionable control, reopens, and F2A favorite stays Generation-backed", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      const seeded = await fx.seedHistory("history_v2_phase_e_original");
      expect(seeded).toMatchObject({ status: "ok", scenario: "history_v2_phase_e_original" });

      await fx.gotoPage("history");
      await openExperimentDetail(page, "exp_phase_e_original");

      // Select the cell (keyboard activation — matrix centers can sit offscreen).
      const cells = page.locator('[data-testid="history-v2-experiment-cell"]');
      await expect(cells.first()).toBeVisible({ timeout: 10000 });
      await cells.nth(0).focus();
      await page.keyboard.press("Enter");
      const paneStar = page.locator('[data-testid="history-v2-cell-detail"] [data-testid="history-v2-cell-favorite"]');
      await expect(paneStar).toBeVisible({ timeout: 10000 });

      // F2A regression guard: the pane star drives the GENERATION favorite.
      await paneStar.click();
      await expect(paneStar).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
      let state = await fx.getState();
      expect(state.historyV2.find((r) => r.id === "gen_phase_e_original_cell_0").favorite).toBe(true);
      expect(state.historyV2.find((r) => r.id === "exp_phase_e_original").favorite).toBe(false);

      // Open the cell ⋮ menu — the path that previously threw
      // "ReferenceError: item is not defined".
      const menuBtn = cells.nth(0).locator(".comfymodal-studio-history-v2-menu-btn");
      await menuBtn.click();
      const menu = page.locator(".comfymodal-studio-history-v2-menu");
      await expect(menu).toBeVisible({ timeout: 5000 });

      // The intended first actionable control receives focus.
      const focusedTestid = await page.evaluate(
        () => (document.activeElement && document.activeElement.getAttribute("data-testid")) || ""
      );
      expect(focusedTestid).toBe("history-v2-cell-generate-original");

      // Menu stayed mounted with its action intact; no duplicate open.
      await expect(menu.locator('[data-testid="history-v2-cell-generate-original"]')).toHaveCount(1);
      fx.assertNoConsoleErrors();

      // Escape closes (existing convention)…
      await page.keyboard.press("Escape");
      await expect(menu).toHaveCount(0);
      fx.assertNoConsoleErrors();

      // …and the menu can reopen cleanly with focus restored.
      await menuBtn.click();
      await expect(menu).toBeVisible({ timeout: 5000 });
      const focusedAgain = await page.evaluate(
        () => (document.activeElement && document.activeElement.getAttribute("data-testid")) || ""
      );
      expect(focusedAgain).toBe("history-v2-cell-generate-original");

      // Invoke the safe existing menu action: Generate Original posts through
      // the cell's generation identity and surfaces its pending label.
      await menu.locator('[data-testid="history-v2-cell-generate-original"]').click();
      // gridNoteEl is the FIRST body-level action note (the F6 cell-download
      // note is a second sibling); scope to it explicitly.
      const gridNote = page.locator(
        '.comfymodal-studio-history-v2-experiment-body > .comfymodal-studio-history-v2-action-note'
      ).first();
      await expect(gridNote).toHaveText("Generating Original\u2026", { timeout: 10000 });

      state = await fx.getState();
      expect(state.historyV2.find((r) => r.id === "gen_phase_e_original_cell_0").favorite).toBe(true);
      fx.assertNoConsoleErrors([/Failed to load resource/]);
    } finally {
      fx.guard.dispose();
    }
  });
});
