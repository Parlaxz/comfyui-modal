// Playground experiment identity — Experiment V2 ownership contracts.
//
// Deterministic tests through the real store: stable experiment/cell
// identity, late foreign-event rejection, targeted per-cell retry (no
// retry-all), cancel/resume ownership, and frozen submitted definitions.
// Transport is stubbed at global fetch; no backend, no GPU.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { usePlaygroundStore } from "./playground";

function okJson(payload: unknown) {
  return (async () => ({
    ok: true,
    status: 200,
    text: async () => JSON.stringify(payload),
  })) as unknown as typeof fetch;
}

const RUN_CONTEXT = {
  status: "ok",
  workflow: { workflow_id: "wf-1", workflow_type: "t2i" },
  version: { workflow_version_id: "v-1", runnable: true },
  mapping: { bindings: {} },
  control_schema: {
    prompt: { label: "Prompt", control_kind: "text", required: true, default: "" },
  },
};

const posted: string[] = [];

beforeEach(() => {
  setActivePinia(createPinia());
  posted.length = 0;
  vi.stubGlobal(
    "fetch",
    (async (url: string) => {
      posted.push(String(url));
      return { ok: true, status: 200, text: async () => JSON.stringify({ status: "ok" }) };
    }) as unknown as typeof fetch,
  );
  try {
    localStorage.clear();
  } catch {
    /* storage-backed environments only */
  }
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function selectWithAxes() {
  const store = usePlaygroundStore();
  await store.selectWorkflow("wf-1", "", okJson(RUN_CONTEXT) as never);
  store.setControl("prompt", "sweep me");
  store.setAxis("prompt", { enabled: true, values: ["a", "b"] });
  return store;
}

describe("experiment definition freeze", () => {
  it("submits axes in deterministic order and freezes the definition", async () => {
    const store = await selectWithAxes();
    store.setAxis("zeta", { enabled: true, values: [1] });
    store.setAxis("alpha", { enabled: true, values: [2] });
    let seen: Record<string, unknown> | null = null;
    const fetchImpl = (async (_url: string, init?: RequestInit) => {
      seen = JSON.parse(String(init?.body)) as Record<string, unknown>;
      return {
        ok: true,
        status: 200,
        text: async () => JSON.stringify({ status: "ok", experiment_id: "exp-1" }),
      };
    }) as unknown as typeof fetch;
    const result = await store.submitExperimentDef({ fetchImpl });
    expect(result.ok).toBe(true);
    expect(Object.keys((seen as unknown as { axes: Record<string, unknown> }).axes)).toEqual([
      "alpha",
      "prompt",
      "zeta",
    ]);
    // Post-submit UI edits cannot mutate the submitted definition.
    store.setAxis("alpha", { enabled: true, values: [999] });
    expect(
      (store.lastSubmitted as unknown as { axes: Record<string, number[]> }).axes.alpha,
    ).toEqual([2]);
  });

  it("adopts the submitted experiment identity", async () => {
    const store = await selectWithAxes();
    await store.submitExperimentDef({
      fetchImpl: okJson({ status: "ok", experiment_id: "exp-7" }) as never,
    });
    expect(store.activeExperimentId).toBe("exp-7");
    expect(store.experimentCells).toEqual({});
  });
});

describe("experiment cell ownership + late events", () => {
  it("late events for a different experiment are rejected", async () => {
    const store = await selectWithAxes();
    await store.submitExperimentDef({
      fetchImpl: okJson({ status: "ok", experiment_id: "exp-ours" }) as never,
    });
    const applied = store.applyExperimentStatus({
      experiment_id: "exp-foreign",
      cells: [{ cell_id: "c1", status: "completed" }],
    });
    expect(applied).toBe(false);
    expect(store.experimentCells).toEqual({});
    expect(
      store.applyExperimentEvent({ experiment_id: "exp-foreign", cell_id: "c1", status: "failed" }),
    ).toBe(false);
    expect(store.experimentCells).toEqual({});
  });

  it("matching status payloads own their cells; terminal cells never regress on bare polls", async () => {
    const store = await selectWithAxes();
    await store.submitExperimentDef({
      fetchImpl: okJson({ status: "ok", experiment_id: "exp-1" }) as never,
    });
    expect(
      store.applyExperimentStatus({
        experiment_id: "exp-1",
        cells: [
          { cell_id: "c1", status: "running", attempt_id: "a1" },
          { cell_id: "c2", status: "queued" },
        ],
      }),
    ).toBe(true);
    expect(store.experimentCells.c1.status).toBe("running");
    // c1 completes…
    store.applyExperimentStatus({
      experiment_id: "exp-1",
      cells: [{ cell_id: "c1", status: "completed", attempt_id: "a1" }],
    });
    expect(store.experimentCells.c1.status).toBe("completed");
    // …a stale poll reporting the old attempt as running cannot regress it.
    store.applyExperimentStatus({
      experiment_id: "exp-1",
      cells: [{ cell_id: "c1", status: "running", attempt_id: "a1" }],
    });
    expect(store.experimentCells.c1.status).toBe("completed");
    // c2 untouched by the partial payload.
    expect(store.experimentCells.c2.status).toBe("queued");
  });

  it("retry targets exactly one failed cell (no retry-all)", async () => {
    const store = await selectWithAxes();
    await store.submitExperimentDef({
      fetchImpl: okJson({ status: "ok", experiment_id: "exp-1" }) as never,
    });
    store.applyExperimentStatus({
      experiment_id: "exp-1",
      cells: [
        { cell_id: "c1", status: "failed", attempt_id: "a1" },
        { cell_id: "c2", status: "failed", attempt_id: "a2" },
      ],
    });
    const result = await store.retryExperimentCell("c1");
    expect(result.ok).toBe(true);
    expect(posted).toEqual(["/comfymodal/history-v2/experiments/exp-1/cells/c1/retry"]);
    // Non-failed cells are not retryable; nothing else was posted.
    expect((await store.retryExperimentCell("c2")).ok).toBe(true);
    expect(posted.filter((url) => url.includes("c2"))).toHaveLength(1);
    expect(posted.some((url) => url.endsWith("/retry-all") || url.includes("retry_all"))).toBe(false);
  });

  it("retry of a non-failed cell is refused without transport", async () => {
    const store = await selectWithAxes();
    await store.submitExperimentDef({
      fetchImpl: okJson({ status: "ok", experiment_id: "exp-1" }) as never,
    });
    store.applyExperimentStatus({
      experiment_id: "exp-1",
      cells: [{ cell_id: "c1", status: "running", attempt_id: "a1" }],
    });
    expect((await store.retryExperimentCell("c1")).ok).toBe(false);
    expect(posted).toHaveLength(0);
  });

  it("cancel/resume target the active experiment only", async () => {
    const store = await selectWithAxes();
    expect((await store.cancelExperimentRun()).ok).toBe(false);
    await store.submitExperimentDef({
      fetchImpl: okJson({ status: "ok", experiment_id: "exp-9" }) as never,
    });
    expect((await store.cancelExperimentRun()).ok).toBe(true);
    expect((await store.resumeExperimentRun()).ok).toBe(true);
    expect(posted).toEqual([
      "/comfymodal/history-v2/experiments/exp-9/cancel",
      "/comfymodal/history-v2/experiments/exp-9/resume",
    ]);
  });
});
