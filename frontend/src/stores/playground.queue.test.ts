// Playground queue — frozen intent + identity/batching contracts.
//
// Deterministic tests through the real store + fake transport: enqueue
// freezes the full Phase-13 execution intent, later UI edits (including a
// workflow/version switch) cannot leak into queued items, and drain
// executes each item with ITS OWN identity without merging incompatible
// items into one backend batch.
import { beforeEach, describe, expect, it } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { queueCompatibilityKey, usePlaygroundStore } from "./playground";

function okJson(payload: unknown) {
  return (async () => ({
    ok: true,
    status: 200,
    text: async () => JSON.stringify(payload),
  })) as unknown as typeof fetch;
}

function contextFor(versionId: string, schema: Record<string, unknown> = {}) {
  return {
    status: "ok",
    workflow: { workflow_id: "wf-A", workflow_type: "t2i" },
    version: { workflow_version_id: versionId, runnable: true },
    mapping: { bindings: {} },
    control_schema: {
      prompt: { label: "Prompt", control_kind: "text", required: true, default: "" },
      ...schema,
    },
  };
}

beforeEach(() => {
  setActivePinia(createPinia());
  try {
    localStorage.clear();
  } catch {
    /* storage-backed environments only */
  }
});

describe("queue intent freeze", () => {
  it("freezes mode, subtool, methods, references, and overrides at enqueue", async () => {
    const store = usePlaygroundStore();
    await store.selectWorkflow("wf-A", "", okJson(contextFor("v-1")) as never);
    store.setControl("prompt", "original");
    store.setTool("generate", "references");
    store.addReference("ref-a.png");
    store.setOutputOverride({ output_format: "webp" });
    store.enqueueCurrent("first");
    // Later UI edits across every frozen dimension…
    store.setControl("prompt", "mutated");
    store.setTool("edit", "select");
    store.addReference("ref-b.png");
    store.setOutputOverride({ output_format: "png" });
    const item = store.queue[0];
    expect(item.intent.controls.prompt).toBe("original");
    expect(item.intent.subtool).toBe("references");
    expect(item.intent.mode).toBe("generate");
    expect(item.intent.references.map((entry) => entry.filename)).toEqual(["ref-a.png"]);
    expect(item.intent.outputOverrides).toEqual({ output_format: "webp" });
  });

  it("adversarial UI mutation cannot leak into the queued request", async () => {
    const store = usePlaygroundStore();
    await store.selectWorkflow("wf-A", "", okJson(contextFor("v-1")) as never);
    store.setControl("prompt", "A-intent");
    store.enqueueCurrent();
    // Adversarial A-then-B: rewrite the entire UI before the drain.
    store.setControl("prompt", "B-intent");
    let seen: Record<string, unknown> | null = null;
    const fetchImpl = (async (_url: string, init?: RequestInit) => {
      seen = JSON.parse(String(init?.body)) as Record<string, unknown>;
      return { ok: true, status: 200, text: async () => JSON.stringify({ status: "ok", runId: "r-q" }) };
    }) as unknown as typeof fetch;
    await store.drainQueue({ fetchImpl });
    const controls = (seen as unknown as { controls: { prompt: string } }).controls;
    expect(controls.prompt).toBe("A-intent");
  });

  it("freezes workflow identity even when the UI switches before drain", async () => {
    const store = usePlaygroundStore();
    await store.selectWorkflow("wf-A", "", okJson(contextFor("v-1")) as never);
    store.setControl("prompt", "queued-on-v1");
    store.enqueueCurrent();
    // Switch the live UI to a different workflow/version before draining.
    const other = {
      status: "ok",
      workflow: { workflow_id: "wf-B", workflow_type: "t2i" },
      version: { workflow_version_id: "v-9", runnable: true },
      mapping: { bindings: {} },
      control_schema: {
        prompt: { label: "Prompt", control_kind: "text", required: true, default: "" },
      },
    };
    await store.selectWorkflow("wf-B", "", okJson(other) as never);
    store.setControl("prompt", "live-on-wfB");
    const seen: Array<{ url: string; body: Record<string, unknown> }> = [];
    const fetchImpl = (async (url: string, init?: RequestInit) => {
      seen.push({ url, body: JSON.parse(String(init?.body)) as Record<string, unknown> });
      return { ok: true, status: 200, text: async () => JSON.stringify({ status: "ok", runId: "r-q" }) };
    }) as unknown as typeof fetch;
    await store.drainQueue({ fetchImpl });
    const run = seen.find((call) => call.url === "/comfymodal/studio/run");
    expect(run).toBeTruthy();
    expect(run!.body.workflow_id).toBe("wf-A");
    expect(run!.body.workflow_version_id).toBe("v-1");
    expect((run!.body.controls as Record<string, unknown>).prompt).toBe("queued-on-v1");
  });
});

describe("queue identity + batching", () => {
  it("same workflow but different versions never merge into one batch", async () => {
    const store = usePlaygroundStore();
    await store.selectWorkflow("wf-A", "", okJson(contextFor("v-1")) as never);
    store.setControl("prompt", "on-v1");
    store.enqueueCurrent();
    await store.selectWorkflow("wf-A", "", okJson(contextFor("v-2")) as never);
    store.setControl("prompt", "on-v2");
    store.enqueueCurrent();
    expect(store.queue).toHaveLength(2);
    expect(queueCompatibilityKey(store.queue[0])).not.toBe(queueCompatibilityKey(store.queue[1]));
    const seen: Array<{ url: string; body: Record<string, unknown> }> = [];
    const fetchImpl = (async (url: string, init?: RequestInit) => {
      seen.push({ url, body: JSON.parse(String(init?.body)) as Record<string, unknown> });
      return { ok: true, status: 200, text: async () => JSON.stringify({ status: "ok", runId: "r-x" }) };
    }) as unknown as typeof fetch;
    await store.drainQueue({ fetchImpl });
    // First drain executes v-1 alone; v-2 stays queued (never merged).
    const batches = seen.filter((call) => call.url === "/comfymodal/studio/run_batch");
    expect(batches).toHaveLength(0);
    expect(seen.filter((call) => call.url === "/comfymodal/studio/run")).toHaveLength(1);
    expect(store.queue).toHaveLength(1);
    expect(store.queue[0].workflowVersionId).toBe("v-2");
  });

  it("queued wfA still executes as wfA after the UI moves to wfB", async () => {
    const store = usePlaygroundStore();
    await store.selectWorkflow("wf-A", "", okJson(contextFor("v-1")) as never);
    store.setControl("prompt", "wfA intent");
    store.enqueueCurrent();
    const other = {
      status: "ok",
      workflow: { workflow_id: "wf-B", workflow_type: "t2i" },
      version: { workflow_version_id: "v-9", runnable: true },
      mapping: { bindings: {} },
      control_schema: {
        prompt: { label: "Prompt", control_kind: "text", required: true, default: "" },
      },
    };
    await store.selectWorkflow("wf-B", "", okJson(other) as never);
    // The queued item carries its own identity; the drain must not read
    // the current UI selection.
    const seen: Array<Record<string, unknown>> = [];
    const fetchImpl = (async (_url: string, init?: RequestInit) => {
      seen.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
      return { ok: true, status: 200, text: async () => JSON.stringify({ status: "ok", runId: "r-q" }) };
    }) as unknown as typeof fetch;
    await store.drainQueue({ fetchImpl });
    expect(seen).toHaveLength(1);
    expect(seen[0].workflow_id).toBe("wf-A");
  });

  it("compatible items batch together in FIFO order", async () => {
    const store = usePlaygroundStore();
    await store.selectWorkflow("wf-A", "", okJson(contextFor("v-1")) as never);
    const seen: Array<{ url: string; body: Record<string, unknown> }> = [];
    const fetchImpl = (async (url: string, init?: RequestInit) => {
      seen.push({ url, body: JSON.parse(String(init?.body)) as Record<string, unknown> });
      return { ok: true, status: 200, text: async () => JSON.stringify({ status: "ok" }) };
    }) as unknown as typeof fetch;
    for (const prompt of ["one", "two", "three"]) {
      store.setControl("prompt", prompt);
      store.enqueueCurrent();
    }
    await store.drainQueue({ fetchImpl });
    const batch = seen.find((call) => call.url === "/comfymodal/studio/run_batch");
    expect(batch).toBeTruthy();
    const variants = (batch!.body as { variants: Array<{ controls: { prompt: string } }> }).variants;
    expect(variants.map((variant) => variant.controls.prompt)).toEqual(["one", "two", "three"]);
    expect(store.queue).toHaveLength(0);
  });

  it("remove and clear drop queued items without submitting", async () => {
    const store = usePlaygroundStore();
    await store.selectWorkflow("wf-A", "", okJson(contextFor("v-1")) as never);
    store.setControl("prompt", "a");
    store.enqueueCurrent("a");
    store.setControl("prompt", "b");
    store.enqueueCurrent("b");
    const firstId = store.queue[0].id;
    store.removeQueued(firstId);
    expect(store.queue.map((item) => item.label)).toEqual(["b"]);
    store.clearQueue();
    expect(store.queue).toHaveLength(0);
    const result = await store.drainQueue({ fetchImpl: okJson({}) as never });
    expect(result.ok).toBe(false);
  });
});
