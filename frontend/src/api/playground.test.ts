// Playground API glue — endpoint contract tests (mock fetch, no backend).
import { describe, expect, it, vi } from "vitest";
import {
  getRunContext,
  newRequestId,
  stopRun,
  submitBatch,
  submitExperiment,
  submitRun,
  uploadPlaygroundImage,
} from "./playground";

function jsonFetch(payload: unknown, ok = true, status = 200) {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  const fetchImpl = vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init });
    return { ok, status, text: async () => JSON.stringify(payload) } as Response;
  });
  return { fetchImpl: fetchImpl as unknown as typeof fetch, calls };
}

describe("playground api", () => {
  it("loads run-context for a workflow/version", async () => {
    const { fetchImpl, calls } = jsonFetch({ status: "ok", control_schema: {} });
    await getRunContext("wf-1", "v-2", fetchImpl);
    expect(calls[0].url).toBe("/comfymodal/studio/workflows/wf-1/run-context?version_id=v-2");
  });

  it("loads run-context without a version", async () => {
    const { fetchImpl, calls } = jsonFetch({ status: "ok" });
    await getRunContext("wf-1", "", fetchImpl);
    expect(calls[0].url).toBe("/comfymodal/studio/workflows/wf-1/run-context");
  });

  it("submits a single run to the frozen transport seam", async () => {
    const { fetchImpl, calls } = jsonFetch({ status: "ok", runId: "r-1" });
    const payload = {
      workflow_id: "wf",
      workflow_version_id: "v",
      featureId: "txt2img",
      workflow_type: "t2i",
      controls: { prompt: "a cat" },
    };
    await submitRun(payload, fetchImpl);
    expect(calls[0].url).toBe("/comfymodal/studio/run");
    expect(calls[0].init?.method).toBe("POST");
    expect(JSON.parse(String(calls[0].init?.body)).controls.prompt).toBe("a cat");
  });

  it("drains queue chunks through run_batch", async () => {
    const { fetchImpl, calls } = jsonFetch({ status: "ok" });
    await submitBatch(
      {
        profile: null,
        workflow_id: "wf",
        workflow_version_id: "v",
        request_id: "batch-1",
        modal_options: null,
        variants: [{ request_id: "var-1", controls: {} }],
      },
      fetchImpl,
    );
    expect(calls[0].url).toBe("/comfymodal/studio/run_batch");
  });

  it("submits experiments only to experiment-v2", async () => {
    const { fetchImpl, calls } = jsonFetch({ status: "ok", experiment_id: "e-1" });
    await submitExperiment({ workflow_id: "wf", axes: {} }, fetchImpl);
    expect(calls[0].url).toBe("/comfymodal/studio/experiment-v2");
  });

  it("cancels through the stop-now seam", async () => {
    const { fetchImpl, calls } = jsonFetch({ status: "ok" });
    await stopRun("r-9", fetchImpl);
    expect(calls[0].url).toBe("/comfymodal/studio/experiments/r-9/stop-now");
  });

  it("uploads through ComfyUI native /upload/image and returns the name", async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    const fetchImpl = vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init });
      return { ok: true, status: 200, json: async () => ({ name: "up_abc.png" }) };
    });
    const file = new File(["x"], "x.png", { type: "image/png" });
    const result = await uploadPlaygroundImage(file, fetchImpl as unknown as typeof fetch);
    expect(result).toEqual({ ok: true, filename: "up_abc.png" });
    expect(calls[0].url).toBe("/upload/image");
    expect(calls[0].init?.body).toBeInstanceOf(FormData);
  });

  it("reports failed uploads without throwing", async () => {
    const fetchImpl = vi.fn(async () => ({ ok: false, status: 500, json: async () => ({}) }));
    const file = new File(["x"], "x.png", { type: "image/png" });
    const result = await uploadPlaygroundImage(file, fetchImpl as unknown as typeof fetch);
    expect(result.ok).toBe(false);
  });

  it("mints unique request ids", () => {
    const ids = new Set([newRequestId("req"), newRequestId("req"), newRequestId("req")]);
    expect(ids.size).toBe(3);
  });
});
