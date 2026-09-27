// Modal Studio — Canonical run-lifecycle regression suite (fake backend).
//
// Pins the canonical single-run lifecycle contract of the Studio Playground
// integration (web/studio-playground.js): terminal status messaging,
// cancel/interrupt distinctions, duplicate/late/stale/foreign event
// isolation, sequential-run state isolation, and the run-click timing
// diagnostics marks.  Runs under playwright.fake.config.mjs against the
// deterministic fake backend — no ComfyUI instance required.
//
// Hard rules (tests/browser/fake/FAKE_BACKEND_GUIDE.md): fresh session per
// test via setupFakeTest, console guard installed before mount, auto-waiting
// locators / expect.poll instead of fixed sleeps, and every test ends with a
// console-error check.
//
// Scenario-behavior notes (tests/browser/fake/scenarios.mjs):
//   - `canceled`  → terminal snapshot status "cancelled" at 900ms + tracker
//     experiment.cancelled.  The UI must map it to "canceled" / "Run canceled.".
//   - `interrupted` → also reaches snapshot status "cancelled" (500ms), but
//     with an explicit cell.interrupted(reason:"interrupted") journal entry.
//     The backend has no run-level "interrupted" terminal (stopped/cancelled
//     is run-level; interruption is cell-level evidence), so the run shows
//     "Run canceled." while the cell stays marked interrupted.
//   - `execution_failure` → terminal status "failed_fatal" with the backend
//     error text "Cell execution failed: CUDA out of memory".
//   - `success` → terminal tracker event is experiment.event
//     type "experiment.completed" (NOT execution_success).
//   - The engine creates a fresh experiment per submit and never consumes
//     the pending scenario, so re-running in one session is supported.

import { test, expect } from "@playwright/test";
import {
  setupFakeTest,
  selectPreset,
  submitSingleRun,
} from "./helpers.mjs";

const SEEDED_PRESET_ID = "preset_default";

// Canonical order of timing marks written by the run-click diagnostics
// integration.  Marks may be a subset (e.g. validation_start/backend_ack are
// skipped in the fake harness), but the marks that ARE present must appear
// in this order with no interleaving and no duplicates; "terminal" is last
// when the run is terminal.
const CANONICAL_MARKS = [
  "run_click",
  "validation_start",
  "validation_end",
  "build_start",
  "build_end",
  "submit_entered",
  "http_invoked",
  "backend_ack",
  "first_running_event",
  "terminal",
];

const RUN_BTN = '[data-testid="run-btn"]';
const STATUS_MSG = '[data-testid="run-status-message"]';
const CANCEL_BTN = '[data-testid="cancel-run-btn"]';
const PROGRESS_SECTION = '[data-testid="progress-section"]';
const PROGRESS_STEP = '[data-testid="progress-step"]';
const PROGRESS_NODES = '[data-testid="progress-nodes"]';

// ── Spec-scoped helpers (do not extend helpers.mjs) ─────────────────────

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
    } catch (e) { /* diagnostics are best-effort */ }
    return null;
  });
}

function pollDiagnostics(page, predicate, opts = {}) {
  const { timeout = 15000, message = "diagnostics condition not met" } = opts;
  return expect
    .poll(async () => {
      const d = await readDiagnostics(page);
      return !!d && predicate(d);
    }, { timeout, message })
    .toBe(true);
}

async function readStatusMessageText(page) {
  const msg = page.locator(STATUS_MSG);
  if ((await msg.count()) === 0) return "";
  return ((await msg.first().textContent()) || "").trim();
}

function expectStatusMessage(page, expected) {
  return expect
    .poll(async () => readStatusMessageText(page), {
      timeout: 10000,
      message: `expected run status message "${expected}"`,
    })
    .toBe(expected);
}

/** Experiment id of the most recent run in the fake session. */
async function latestExperimentId(fx) {
  const state = await fx.getState();
  const exps = (state && state.experiments) || [];
  return exps.length > 0 ? exps[exps.length - 1].experiment_id : null;
}

test.describe("Studio Playground canonical lifecycle", () => {
  test("1. success run completes and reports success", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.setScenario("success");
      await selectPreset(page, SEEDED_PRESET_ID);
      await submitSingleRun(page);

      await fx.waitForStatus("Run completed", { timeout: 20000 });
      await expect(page.locator(STATUS_MSG)).toContainText("Run completed");
      await expect(page.locator(STATUS_MSG)).not.toContainText("Run canceled");
      await expect(page.locator(RUN_BTN)).toBeEnabled();

      // Diagnostics: terminal status completed with run_click → terminal marks.
      await pollDiagnostics(
        page,
        (d) => d.isTerminal === true && d.status === "completed",
        { timeout: 10000, message: "expected terminal completed diagnostics" }
      );
      const d = await readDiagnostics(page);
      expect(d.marks, "expected timing marks").toBeTruthy();
      const names = d.marks.map((m) => m.name);
      expect(names[0]).toBe("run_click");
      expect(names[names.length - 1]).toBe("terminal");
      expect(names.indexOf("run_click")).toBeLessThan(names.indexOf("terminal"));

      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("2. execution failure retains the backend error message", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.setScenario("execution_failure");
      await selectPreset(page, SEEDED_PRESET_ID);
      await submitSingleRun(page);

      const section = page.locator(".comfymodal-studio-run-section");
      await expect(section).toContainText("Run Failed", { timeout: 20000 });
      // The backend error text must survive end-to-end (scenarios.mjs
      // execution_failure: workerFailed message / failed_fatal error).
      const text = (await section.textContent()) || "";
      expect(text.toLowerCase()).toContain("out of memory");
      expect(text).toMatch(/Cell execution failed|Modal worker crashed/);
      // Retry affordance: the Run button is re-enabled after the failure.
      await expect(page.locator(RUN_BTN)).toBeEnabled();

      await pollDiagnostics(
        page,
        (d) => d.isTerminal === true && d.status === "failed",
        { timeout: 10000, message: "expected failed diagnostics" }
      );
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("3. canceled run never displays success", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.setScenario("canceled");
      await selectPreset(page, SEEDED_PRESET_ID);
      await submitSingleRun(page);

      await fx.waitForStatus("Run canceled.", { timeout: 20000 });
      await expectStatusMessage(page, "Run canceled.");
      const msg = await readStatusMessageText(page);
      expect(msg).not.toContain("Run completed");
      expect(msg).not.toContain("completed successfully");
      await expect(page.locator(RUN_BTN)).toBeEnabled();

      await pollDiagnostics(
        page,
        (d) => d.isTerminal === true && d.status === "canceled",
        { timeout: 10000, message: "expected canceled diagnostics" }
      );

      // The cancel affordance is gone at terminal (removed or hidden).
      const cancelBtn = page.locator(CANCEL_BTN);
      await expect
        .poll(async () => {
          if ((await cancelBtn.count()) === 0) return true;
          return !(await cancelBtn.isVisible().catch(() => false));
        }, { timeout: 10000, message: "expected the cancel button to be gone at terminal" })
        .toBe(true);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("4. interrupted run is distinct from canceled/completed", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.setScenario("interrupted");
      await selectPreset(page, SEEDED_PRESET_ID);
      await submitSingleRun(page);

      // The fake mirrors the REAL backend: a stopped/interrupted run settles
      // at run-level status "cancelled" (scheduler STATUS_STOPPED) — there is
      // NO run-level "interrupted" terminal in the backend vocabulary. The
      // interruption is explicit CELL-level evidence (cell.interrupted with
      // reason "interrupted"), which the canonical model keeps on the cell.
      // Run-level UI must therefore show canceled (never success), and the
      // cell must be marked interrupted.
      await fx.waitForStatus("Run canceled.", { timeout: 20000 });
      await expectStatusMessage(page, "Run canceled.");
      const msg = await readStatusMessageText(page);
      expect(msg.toLowerCase()).not.toContain("completed");
      expect(msg.toLowerCase()).not.toContain("successfully");

      // Cell-level interruption is preserved and distinct.
      await pollDiagnostics(
        page,
        (d) => {
          if (!d.isTerminal || d.status !== "canceled") return false;
          const cells = d.cells || {};
          return Object.keys(cells).length > 0
            && Object.values(cells).some((c) => c && c.status === "interrupted");
        },
        { timeout: 10000, message: "expected canceled run with interrupted cell" }
      );
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("5. duplicate completion signals render exactly one terminal", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.setScenario("success");
      await selectPreset(page, SEEDED_PRESET_ID);
      await submitSingleRun(page);

      // Duplicate the scenario's own terminal tracker signal (success emits
      // experiment.event type "experiment.completed") with the real
      // experiment id, injected BEFORE the 650ms terminal lands. Poll until
      // the experiment record exists — the submit POST is async.
      await expect
        .poll(async () => latestExperimentId(fx), {
          timeout: 15000,
          message: "expected the run's experiment record",
        })
        .toBeTruthy();
      const expId = await latestExperimentId(fx);
      await fx.injectEvent("experiment.event", {
        type: "experiment.completed",
        experiment_id: expId,
      });
      // Also duplicate the classic execution_success terminal signal with the
      // run's real prompt_id when it is still visible in the engine's queue.
      const state = await fx.getState();
      const execStart = (state.eventQueue || []).find((e) => e.type === "execution_start");
      const promptId = execStart && execStart.detail && execStart.detail.prompt_id;
      if (promptId) {
        await fx.injectEvent("execution_success", { prompt_id: promptId });
      }

      await fx.waitForStatus("Run completed", { timeout: 20000 });

      // One more duplicate AFTER terminal, then let any late handlers pump.
      await fx.injectEvent("experiment.event", {
        type: "experiment.completed",
        experiment_id: expId,
      });
      await page.waitForTimeout(400);

      await expect(page.locator(STATUS_MSG)).toHaveCount(1);
      await expect(page.locator(STATUS_MSG)).toContainText("Run completed");
      await expect(page.locator(RUN_BTN)).toBeEnabled();
      const viewLinks = page.locator('.comfymodal-studio-run-section a:has-text("View in History")');
      expect(await viewLinks.count()).toBeLessThanOrEqual(1);

      await pollDiagnostics(
        page,
        (d) => d.isTerminal === true && d.status === "completed",
        { timeout: 10000, message: "expected terminal completed diagnostics" }
      );
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("6. late sampler progress after completion is ignored", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.setScenario("success");
      await selectPreset(page, SEEDED_PRESET_ID);
      await submitSingleRun(page);

      await fx.waitForStatus("Run completed", { timeout: 20000 });

      // Late worker progress for the already-terminal run must not regress
      // the UI back into a running state.
      const expId = await latestExperimentId(fx);
      await fx.injectEvent("experiment.worker.progress", {
        experiment_id: expId,
        cell_key: "cell_0",
        checkpoint_id: "ckp_late",
        attempt_id: "att_late",
        total_nodes: 8,
        type: "sampler.step",
        step: 15,
        max: 20,
        message: "late sampler progress",
      });
      await page.waitForTimeout(400);

      await expect(page.locator(STATUS_MSG)).toContainText("Run completed");
      await expect(page.locator(RUN_BTN)).toBeEnabled();
      const btnText = ((await page.locator(RUN_BTN).textContent()) || "").trim();
      expect(btnText).not.toMatch(/Running|Submitted|Waiting|Queued/);
      await expect(page.locator(".comfymodal-studio-run-section")).not.toContainText("Running\u2026");
      await expect(page.locator(PROGRESS_SECTION)).not.toBeVisible();
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("7. out-of-order events still reach a clean terminal", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.setScenario("out_of_order");
      await selectPreset(page, SEEDED_PRESET_ID);
      await submitSingleRun(page);

      // cell.completed journal lands BEFORE the sampler tracker events, and
      // worker events keep arriving AFTER the terminal journal — the run must
      // still settle on a single completed terminal without errors.
      await fx.waitForStatus("Run completed", { timeout: 20000 });
      // Let post-terminal tracker events pump before asserting no errors.
      await page.waitForTimeout(300);
      await expect(page.locator(RUN_BTN)).toBeEnabled();
      await expect(page.locator(STATUS_MSG)).toContainText("Run completed");
      await pollDiagnostics(
        page,
        (d) => d.isTerminal === true && d.status === "completed",
        { timeout: 10000, message: "expected terminal completed diagnostics" }
      );
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("8. stale prior-run progress does not affect the next run", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.setScenario("success");
      await selectPreset(page, SEEDED_PRESET_ID);

      // Run 1 to completion.
      await submitSingleRun(page);
      await fx.waitForStatus("Run completed", { timeout: 20000 });
      await pollDiagnostics(page, (d) => d.isTerminal === true && d.status === "completed");
      const exp1 = await latestExperimentId(fx);
      expect(exp1).toBeTruthy();

      // Run 2 in the same session (the engine creates a fresh experiment per
      // submit and never consumes the pending scenario). Poll until the new
      // experiment exists — the submit POST is async and the click alone
      // does not guarantee the record is visible yet.
      await submitSingleRun(page);
      await expect
        .poll(async () => latestExperimentId(fx), {
          timeout: 15000,
          message: "expected a fresh experiment for run 2",
        })
        .not.toBe(exp1);
      const exp2 = await latestExperimentId(fx);
      expect(exp2).toBeTruthy();
      expect(exp2).not.toBe(exp1);

      // Inject stale progress carrying RUN 1's experiment id while run 2 is
      // active — run 2's UI must not be touched by it.
      await fx.injectEvent("experiment.worker.progress", {
        experiment_id: exp1,
        cell_key: "cell_0",
        checkpoint_id: "ckp_stale",
        attempt_id: "att_stale",
        total_nodes: 8,
        type: "sampler.step",
        step: 42,
        max: 20,
        message: "stale prior-run sampler progress",
      });

      // Run 2 progresses with its OWN sampler values only.
      await expect(page.locator(PROGRESS_STEP)).toContainText("Sampler:", { timeout: 15000 });
      const stepText = (await page.locator(PROGRESS_STEP).textContent()) || "";
      expect(stepText).not.toContain("42");
      await page.waitForTimeout(400);
      expect(((await page.locator(PROGRESS_STEP).textContent()) || "")).not.toContain("42");

      await fx.waitForStatus("Run completed", { timeout: 20000 });
      await pollDiagnostics(
        page,
        (d) => d.isTerminal === true && d.status === "completed" && d.experimentId === exp2,
        { timeout: 10000, message: "expected run 2 completed diagnostics" }
      );
      await expect(page.locator(RUN_BTN)).toBeEnabled();
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("9. foreign-experiment progress is ignored during a single run", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.setScenario("success");
      await selectPreset(page, SEEDED_PRESET_ID);
      await submitSingleRun(page);

      // A worker progress event for an unknown experiment id must not move
      // the sampler UI off the run's own values.
      await fx.injectEvent("experiment.worker.progress", {
        experiment_id: "e-foreign",
        cell_key: "cell_x",
        total_nodes: 8,
        type: "sampler.step",
        step: 42,
        max: 20,
        message: "foreign sampler progress",
      });

      // The run's own sampler progression (5/10/15/20 out of 20) must appear;
      // the foreign step 42 must never surface.
      await expect
        .poll(async () => {
          const t = (await page.locator(PROGRESS_STEP).textContent()) || "";
          const m = t.match(/Sampler: (\d+)\/20/);
          return m ? m[1] : "";
        }, {
          timeout: 10000,
          message: "expected the run's own sampler step values",
        })
        .toMatch(/^(5|10|15|20)$/);
      expect(((await page.locator(PROGRESS_STEP).textContent()) || "")).not.toContain("42");

      await fx.waitForStatus("Run completed", { timeout: 20000 });
      await pollDiagnostics(
        page,
        (d) => d.isTerminal === true && d.status === "completed",
        { timeout: 10000, message: "expected terminal completed diagnostics" }
      );
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("10. sampler and workflow node progress are isolated", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.setScenario("sampler_progress");
      await selectPreset(page, SEEDED_PRESET_ID);
      await submitSingleRun(page);

      await expect(page.locator(PROGRESS_SECTION)).toBeVisible({ timeout: 15000 });
      const stepEl = page.locator(PROGRESS_STEP);
      const nodesEl = page.locator(PROGRESS_NODES);

      // Sampler line shows the scenario's sampler values...
      await expect
        .poll(async () => (await stepEl.textContent()) || "", {
          timeout: 10000,
          message: "expected sampler step progress",
        })
        .toMatch(/Sampler: \d+\/20/);
      // ...and the workflow-nodes line shows its own completed/total (8 nodes
      // come from execution_start).  The two must not overwrite each other.
      await expect
        .poll(async () => (await nodesEl.textContent()) || "", {
          timeout: 10000,
          message: "expected workflow node progress",
        })
        .toMatch(/Nodes: \d+\/8/);
      expect(((await stepEl.textContent()) || "")).not.toMatch(/Nodes:/);
      expect(((await nodesEl.textContent()) || "")).not.toMatch(/Sampler:/);

      // Canonical truth (the DOM may freeze mid-burst because the terminal
      // re-render hides the section in the same pump batch): the sampler slot
      // must reach its own max 20 while the workflow slot keeps totalNodes 8.
      await pollDiagnostics(
        page,
        (d) => !!d.sampler && d.sampler.max === 20 && d.sampler.step === 20
          && !!d.progress && d.progress.totalNodes === 8,
        { timeout: 10000, message: "expected canonical sampler 20/20 + nodes 8" }
      );

      await fx.waitForStatus("Run completed", { timeout: 20000 });
      await pollDiagnostics(
        page,
        (d) => d.isTerminal === true && d.status === "completed",
        { timeout: 10000, message: "expected terminal completed diagnostics" }
      );
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("11. workflow node progress is not overwritten by sampler max", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.setScenario("sampler_progress");
      await selectPreset(page, SEEDED_PRESET_ID);
      await submitSingleRun(page);

      await expect(page.locator(PROGRESS_SECTION)).toBeVisible({ timeout: 15000 });
      const stepEl = page.locator(PROGRESS_STEP);
      const nodesEl = page.locator(PROGRESS_NODES);

      // Wait until the node line has landed with its own value.
      await expect
        .poll(async () => (await nodesEl.textContent()) || "", {
          timeout: 10000,
          message: "expected workflow node progress",
        })
        .toMatch(/Nodes: \d+\/8/);
      const nodesBefore = await nodesEl.textContent();

      // Sampler reaches its max in canonical state...
      await pollDiagnostics(
        page,
        (d) => !!d.sampler && d.sampler.max === 20 && d.sampler.step === 20,
        { timeout: 10000, message: "expected sampler to reach max" }
      );
      // ...while the workflow slot keeps its own completed/total — the sampler
      // max must never be absorbed into the nodes line.
      await pollDiagnostics(
        page,
        (d) => !!d.progress && d.progress.totalNodes === 8
          && d.progress.completedNodes !== 20,
        { timeout: 10000, message: "expected nodes progress preserved" }
      );
      // If the nodes line is still in the DOM (the section is removed at
      // terminal), it must keep its own value.
      if ((await nodesEl.count()) > 0) {
        expect(((await nodesEl.textContent()) || "")).toMatch(/Nodes: \d+\/8/);
        expect(await nodesEl.textContent()).toBe(nodesBefore);
      }

      await fx.waitForStatus("Run completed", { timeout: 20000 });
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("12. sequential runs do not share run state", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.setScenario("success");
      await selectPreset(page, SEEDED_PRESET_ID);

      // Run 1 → completed.
      await submitSingleRun(page);
      await fx.waitForStatus("Run completed", { timeout: 20000 });
      await pollDiagnostics(page, (d) => d.isTerminal === true && d.status === "completed");
      const exp1 = (await readDiagnostics(page)).experimentId;
      expect(exp1).toBeTruthy();

      // Run 2: click Run again — the button must leave the completed state.
      const runBtn = await submitSingleRun(page);
      await expect
        .poll(async () => ((await runBtn.textContent()) || "").trim(), {
          timeout: 10000,
          message: "expected run 2 to leave the completed state",
        })
        .toMatch(/Running|Submitted|Waiting|Queued/);
      // The old completion message must not linger.
      await expect
        .poll(async () => {
          const msg = page.locator(STATUS_MSG);
          const count = await msg.count();
          return count === 0 || !(((await msg.first().textContent()) || "").includes("Run completed"));
        }, {
          timeout: 10000,
          message: "expected the old completion message to be gone",
        })
        .toBe(true);

      // Run 2 completes on its own and reports a distinct experiment.
      await fx.waitForStatus("Run completed", { timeout: 20000 });
      const exp2 = (await readDiagnostics(page)).experimentId;
      expect(exp2).toBeTruthy();
      expect(exp2).not.toBe(exp1);
      await pollDiagnostics(
        page,
        (d) => d.isTerminal === true && d.status === "completed" && d.experimentId === exp2,
        { timeout: 10000, message: "expected run 2 completed diagnostics" }
      );
      await expect(runBtn).toBeEnabled();
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("13. timing marks follow the canonical order", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.setScenario("success");
      await selectPreset(page, SEEDED_PRESET_ID);
      await submitSingleRun(page);

      await fx.waitForStatus("Run completed", { timeout: 20000 });
      await pollDiagnostics(page, (d) => d.isTerminal === true && d.status === "completed");

      const d = await readDiagnostics(page);
      const marks = d.marks || [];
      expect(marks.length).toBeGreaterThan(0);
      expect(marks[0].name).toBe("run_click");
      if (d.isTerminal) {
        expect(marks[marks.length - 1].name).toBe("terminal");
      }
      const indexes = marks.map((m) => CANONICAL_MARKS.indexOf(m.name));
      expect(indexes.every((i) => i >= 0)).toBe(true);
      for (let i = 1; i < indexes.length; i++) {
        expect(indexes[i]).toBeGreaterThan(indexes[i - 1]);
      }
      for (const m of marks) {
        if (typeof m.deltaMs === "number") {
          expect(m.deltaMs).toBeGreaterThanOrEqual(0);
        }
      }
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("14. canceled run has no success messaging or View in History", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.setScenario("canceled");
      await selectPreset(page, SEEDED_PRESET_ID);
      await submitSingleRun(page);

      await fx.waitForStatus("Run canceled.", { timeout: 20000 });
      await expectStatusMessage(page, "Run canceled.");
      const section = page.locator(".comfymodal-studio-run-section");
      await expect(section).not.toContainText("View in History");
      expect(await section.locator('a:has-text("View in History")').count()).toBe(0);
      await expect(section).not.toContainText("Run completed");
      await expect(page.locator(RUN_BTN)).toBeEnabled();
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });
});
