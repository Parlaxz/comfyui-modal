// Modal Studio — Cold Benchmark
//
// Sequential cold-start benchmark that measures full Modal execution
// latency across three back-to-back Studio runs with enforced gaps.
// Gated by COMFYMODAL_COLD_BENCHMARK=1.

import { test, expect } from "@playwright/test";
import { writeFileSync } from "node:fs";
import {
  buildLiveSnapshotPayload,
  openStudio,
  createOwnedRecords,
  cleanupOwnedRecords,
} from "./studio-fixtures.mjs";

const COLD_ENABLED = process.env.COMFYMODAL_COLD_BENCHMARK === "1";
const COMFYUI_URL = process.env.COMFYUI_URL || "http://127.0.0.1:8188";
const WORKFLOW_PATH =
  process.env.COMFYMODAL_BENCHMARK_WORKFLOW || "clean_workflow.json";

// ── Module-level pre-check (only when cold benchmark enabled) ─────────────

let builderResult = null;
let builderError = null;
let defaults = null;

if (COLD_ENABLED) {
  try {
    builderResult = buildLiveSnapshotPayload(WORKFLOW_PATH);
    const ks =
      builderResult.snapshotPayload.graphJson[builderResult.ksamplerNodeId];
    const inputs = ks.inputs;
    defaults = {
      seed: typeof inputs.seed === "number" ? inputs.seed : 42,
      steps: (() => {
        if (Array.isArray(inputs.steps)) {
          const connectedNode =
            builderResult.snapshotPayload.graphJson[inputs.steps[0]];
          if (connectedNode?.inputs?.value !== undefined)
            return connectedNode.inputs.value;
        }
        return typeof inputs.steps === "number" ? inputs.steps : 20;
      })(),
      guidance: typeof inputs.cfg === "number" ? inputs.cfg : 7.0,
      sampler:
        typeof inputs.sampler_name === "string"
          ? inputs.sampler_name
          : "euler",
      scheduler:
        typeof inputs.scheduler === "string" ? inputs.scheduler : "normal",
      denoise: typeof inputs.denoise === "number" ? inputs.denoise : 1.0,
    };
  } catch (e) {
    builderError = e.message || String(e);
  }

  if (builderError) {
    throw new Error(
      `buildLiveSnapshotPayload pre-check FAILED: ${builderError}`
    );
  }
}

// ── Tests ──────────────────────────────────────────────────────────────────

test.describe("Studio Cold Benchmark", () => {
  test.skip(
    !COLD_ENABLED,
    "Set COMFYMODAL_COLD_BENCHMARK=1 to enable cold benchmark"
  );

  const BENCHMARK_TIMEOUT_MS = parseInt(
    process.env.COMFYMODAL_BENCHMARK_TIMEOUT_MS || "1200000",
    10
  );

  test("3 sequential cold runs with enforced gaps", async ({ page, request }, testInfo) => {
    test.setTimeout(BENCHMARK_TIMEOUT_MS);

    const { snapshotPayload } = builderResult;
    const owned = createOwnedRecords();
    const promptBase = `cold-${Date.now().toString(36)}`;
    const runs = [];
    const gapMs = 25000;
    let testError = null;

    try {
      // ── Create snapshot ──────────────────────────────────────────────
      const snapRes = await request.post(
        `${COMFYUI_URL}/comfymodal/studio/snapshots`,
        { data: { ...snapshotPayload, name: `${promptBase}-snap` } }
      );
      expect(snapRes.ok()).toBeTruthy();
      const snapBody = await snapRes.json();
      expect(snapBody.status).toBe("ok");
      expect(snapBody.snapshot).toBeTruthy();
      expect(snapBody.snapshot.id).toBeTruthy();
      const snapshotId = snapBody.snapshot.id;
      owned.snapshotIds.push(snapshotId);

      // ── Create preset ────────────────────────────────────────────────
      const preRes = await request.post(
        `${COMFYUI_URL}/comfymodal/studio/presets`,
        {
          data: {
            label: `${promptBase}-preset`,
            snapshotId,
            compatibleFeatures: ["txt2img"],
            defaults,
          },
        }
      );
      expect(preRes.ok()).toBeTruthy();
      const preBody = await preRes.json();
      expect(preBody.status).toBe("ok");
      expect(preBody.preset).toBeTruthy();
      expect(preBody.preset.id).toBeTruthy();
      expect(preBody.preset.status).toBe("runnable");
      const presetId = preBody.preset.id;
      owned.presetIds.push(presetId);

      // ── Three sequential UI runs ─────────────────────────────────────
      for (let i = 0; i < 3; i++) {
        const runStart = Date.now();

        await openStudio(page, COMFYUI_URL);
        await page
          .locator('[data-testid="control-panel"]')
          .waitFor({ state: "visible", timeout: 15000 });

        // Select owned preset
        const select = page.locator('[data-testid="backend-select"]');
        await select.waitFor({ state: "visible", timeout: 15000 });
        await expect(
          select.locator(`option[value="${presetId}"]`)
        ).toHaveCount(1, { timeout: 15000 });
        await select.selectOption(presetId);

        // Fill prompt
        const promptText = `${promptBase}-run-${i + 1}`;
        const promptInput = page.locator('[data-testid="input-prompt"]');
        await promptInput.waitFor({ state: "visible", timeout: 10000 });
        await promptInput.fill(promptText);

        // Fill every visible scalar control from the KSampler defaults
        for (const ctrl of [
          "steps",
          "guidance",
          "denoise",
          "seed",
          "sampler",
          "scheduler",
        ]) {
          const el = page.locator(`[data-testid="input-${ctrl}"]`);
          await el.waitFor({ state: "visible", timeout: 10000 });
          const tag = await el.evaluate((n) => n.tagName);
          const val = defaults[ctrl];
          if (tag === "SELECT") {
            await el.selectOption(String(val));
          } else {
            await el.fill(String(val));
          }
        }

        // Capture POST /comfymodal/studio/run response
        const runRespPromise = page.waitForResponse(
          (resp) =>
            resp.url().includes("/comfymodal/studio/run") &&
            resp.request().method() === "POST"
        );

        const runBtn = page.locator('[data-testid="run-btn"]');
        await expect(runBtn).toBeEnabled({ timeout: 10000 });
        await runBtn.click();

        const runResp = await runRespPromise;
        const runBody = await runResp.json();
        if (!runResp.ok()) {
          throw new Error(
            `Run ${i + 1} POST failed: ${JSON.stringify(runBody)}`
          );
        }
        expect(runBody.status).toBe("ok");
        expect(runBody.runId).toBeTruthy();
        const runId = runBody.runId;
        const historyId = runBody.runHistoryId || runId;

        // Wait for canvas output
        await expect(
          page.locator('[data-testid="canvas-output"]')
        ).toBeVisible({ timeout: BENCHMARK_TIMEOUT_MS });

        // Wait for timing card and extract text
        const timingCard = page.locator('[data-testid="timing-card"]');
        await expect(timingCard).toBeVisible({ timeout: 15000 });
        const timingText = await timingCard.textContent();

        // Fetch /comfymodal/run-history/{historyId}/timing and assert payload
        const tRes = await request.get(
          `${COMFYUI_URL}/comfymodal/run-history/${historyId}/timing`
        );
        expect(tRes.ok()).toBeTruthy();
        const timingData = await tRes.json();
        expect(timingData.status).toBe("ok");
        expect(timingData.timing).toBeTruthy();
        expect(typeof timingData.timing).toBe("object");
        expect(typeof timingData.timing.restore_total_ms).toBe("number");
        expect(Number.isFinite(timingData.timing.restore_total_ms)).toBe(true);
        expect(timingData.timing.restore_total_ms).toBeGreaterThan(0);
        // Production-plan correctness is part of benchmark acceptance
        const wp = timingData.timing._restore_timing?.warmup_profile;
        expect(wp).toBeTruthy();
        expect(wp._production_enabled).toBe(true);
        expect(wp._production_plan_hash).toBeTruthy();
        expect(typeof wp._production_plan_hash).toBe("string");
        expect(wp._production_plan_hash.length).toBeGreaterThan(0);
        expect(wp._production_compiled_workflow_hash).toBeTruthy();
        expect(typeof wp._production_compiled_workflow_hash).toBe("string");
        expect(wp._production_compiled_workflow_hash.length).toBeGreaterThan(0);

        const runEntry = {
          index: i + 1,
          runId,
          historyId,
          snapshotId,
          presetId,
          prompt: promptText,
          runStart,
          runEnd: Date.now(),
          responseBody: runBody,
          timingCardText: timingText,
          timingData,
        };
        runs.push(runEntry);

        // Write per-run JSON via testInfo.outputPath
        const ts = runStart.toString(36);
        writeFileSync(
          testInfo.outputPath(`cold-run-${i + 1}-${ts}.json`),
          JSON.stringify(runEntry, null, 2),
          "utf-8"
        );

        // Enforce gap before next run start (runs 1 and 2 only)
        if (i < 2) {
          const nextTarget = runStart + gapMs;
          const now = Date.now();
          if (now < nextTarget) {
            await new Promise((r) => setTimeout(r, nextTarget - now));
          }
        }
      }

      // ── Write summary JSON ───────────────────────────────────────────
      const summaryTs = Date.now().toString(36);
      const gaps = runs.slice(1).map((r, i) => ({
        fromStart: runs[i].runStart,
        toStart: r.runStart,
        elapsedMs: r.runStart - runs[i].runStart,
      }));
      const summary = {
        workflow: WORKFLOW_PATH,
        builderResult: {
          ksamplerNodeId: builderResult.ksamplerNodeId,
          clipEncodeNodeIds: builderResult.clipEncodeNodeIds,
          outputNodeId: builderResult.outputNodeId,
          bindings: builderResult.bindings,
        },
        defaults,
        gapMs,
        runs,
        gaps,
      };
      writeFileSync(
        testInfo.outputPath(`cold-benchmark-summary-${summaryTs}.json`),
        JSON.stringify(summary, null, 2),
        "utf-8"
      );

      // ── Assertions ───────────────────────────────────────────────────
      for (const r of runs) {
        expect(r.responseBody.status).toBe("ok");
        expect(r.runId).toBeTruthy();
        expect(r.timingCardText).toBeTruthy();
        expect(r.timingCardText).toMatch(/\d+\.?\d*\s*(ms|s|m)/i);
      }

      for (const g of gaps) {
        expect(g.elapsedMs).toBeGreaterThanOrEqual(20000);
      }
    } catch (e) {
      testError = e;
    } finally {
      // Cleanup only the created preset and snapshot IDs
      try {
        await cleanupOwnedRecords(request, COMFYUI_URL, owned);
      } catch (e) {
        if (testError) {
          throw new AggregateError(
            [testError, e],
            "Test failed and cleanup also failed"
          );
        }
        throw e;
      }
    }

    if (testError) throw testError;
  });
});
