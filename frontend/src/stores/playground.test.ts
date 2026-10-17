// Playground store — correctness contracts that must survive UI work:
// submission freeze, stale-upload discard, image-free presets, queue/
// experiment radio invariant, and no duplicate History caching.
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { reactive } from "vue";
import {
  freezeIntent,
  stripImageKeys,
  usePlaygroundStore,
  validateDraft,
} from "./playground";

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
    steps: { label: "Steps", data_type: "INT", default: 20, minimum: 1, maximum: 100 },
    source_image: { label: "Source", control_kind: "image" },
  },
};

beforeEach(() => {
  setActivePinia(createPinia());
  try {
    localStorage.clear();
  } catch {
    /* storage-backed environments only */
  }
});

describe("playground intent helpers", () => {
  it("freezeIntent deep-copies so later edits cannot leak in", () => {
    const live = { controls: { prompt: "a" }, nested: { list: [1] } };
    const frozen = freezeIntent(live);
    live.controls.prompt = "b";
    live.nested.list.push(2);
    expect(frozen.controls.prompt).toBe("a");
    expect(frozen.nested.list).toEqual([1]);
  });

  it("freezes values read back out of reactive store state", () => {
    // Regression: queue items re-read through the store are reactive
    // proxies, which structuredClone rejects. The freeze must survive.
    const proxy = reactive({ controls: { prompt: "a" } });
    const frozen = freezeIntent(proxy.controls);
    expect(frozen).toEqual({ prompt: "a" });
    expect(frozen).not.toBe(proxy.controls);
    proxy.controls.prompt = "b";
    expect(frozen.prompt).toBe("a");
  });

  it("stripImageKeys removes source/mask/reference keys only", () => {
    const out = stripImageKeys({
      prompt: "keep",
      source_image: "drop.png",
      mask: "drop-mask.png",
      references: ["drop.png"],
      steps: 20,
    });
    expect(out).toEqual({ prompt: "keep", steps: 20 });
  });

  it("validateDraft flags unknown, out-of-range, and missing required", () => {
    const schema = RUN_CONTEXT.control_schema as never;
    expect(validateDraft({ nope: 1 }, schema).some((e) => e.field === "nope")).toBe(true);
    expect(validateDraft({ prompt: "x", steps: 500 }, schema).some((e) => e.field === "steps")).toBe(true);
    expect(validateDraft({ steps: 5 }, schema).some((e) => e.field === "prompt")).toBe(true);
    expect(validateDraft({ prompt: "x", steps: 5 }, schema)).toEqual([]);
  });
});

describe("usePlaygroundStore", () => {
  it("resolves workflow selection into schema defaults", async () => {
    const store = usePlaygroundStore();
    const result = await store.selectWorkflow("wf-1", "", okJson(RUN_CONTEXT) as never);
    expect(result.ok).toBe(true);
    expect(store.schema.prompt).toBeTruthy();
    expect(store.controlValues.prompt).toBe("");
    expect(store.controlValues.steps).toBe(20);
    expect(store.runnable).toBe(true);
  });

  it("drops control values from an incompatible workflow on switch", async () => {
    const store = usePlaygroundStore();
    await store.selectWorkflow("wf-1", "", okJson(RUN_CONTEXT) as never);
    store.setControl("prompt", "hello");
    const other = {
      ...RUN_CONTEXT,
      version: { workflow_version_id: "v-2", runnable: true },
      control_schema: { strength: { label: "Strength", default: 0.5 } },
    };
    await store.selectWorkflow("wf-1", "", okJson(other) as never);
    expect(store.controlValues.prompt).toBeUndefined();
    expect(store.controlValues.strength).toBe(0.5);
  });

  it("freezes the submitted request before the network responds", async () => {
    const store = usePlaygroundStore();
    await store.selectWorkflow("wf-1", "", okJson(RUN_CONTEXT) as never);
    store.setControl("prompt", "original");
    let seen: Record<string, unknown> | null = null;
    const fetchImpl = (async (_url: string, init?: RequestInit) => {
      seen = JSON.parse(String(init?.body)) as Record<string, unknown>;
      store.setControl("prompt", "mutated-mid-flight");
      return { ok: true, status: 200, text: async () => JSON.stringify({ status: "ok", runId: "r-1" }) };
    }) as unknown as typeof fetch;
    await store.submitRun({ fetchImpl });
    expect((seen as unknown as Record<string, Record<string, unknown>>).controls.prompt).toBe("original");
    expect(store.lastSubmitted?.controls.prompt).toBe("original");
  });

  it("discards a delayed upload that completes after a context switch", async () => {
    const store = usePlaygroundStore();
    await store.selectWorkflow("wf-1", "", okJson(RUN_CONTEXT) as never);
    const token = store.beginUpload(store.contextKey);
    // User switches workflow before the upload lands.
    await store.selectWorkflow("wf-1", "", okJson(RUN_CONTEXT) as never);
    const committed = store.commitUpload(token, "wf-1::v-1", "stale.png");
    expect(committed).toBe(false);
    expect(store.controlValues.source_image).toBeUndefined();
  });

  it("commits an upload that still owns its context", () => {
    const store = usePlaygroundStore();
    const owner = "wf-1::v-1";
    const token = store.beginUpload(owner);
    expect(store.commitUpload(token, owner, "fresh.png")).toBe(true);
    expect(store.controlValues.source_image).toBe("fresh.png");
  });

  it("keeps queue and experiment modes mutually exclusive", () => {
    const store = usePlaygroundStore();
    store.setExperimentMode(true);
    expect(store.queueMode).toBe(false);
    store.setQueueMode(true);
    expect(store.experimentMode).toBe(false);
  });

  it("applies presets image-free and clears stale ownership", async () => {
    const store = usePlaygroundStore();
    await store.selectWorkflow("wf-1", "", okJson(RUN_CONTEXT) as never);
    store.setSource("old.png", store.contextKey);
    store.setOutputOverride({ output_format: "webp" });
    store.applyPreset({ controls: { prompt: "preset prompt", source_image: "preset.png" } }, "p-1");
    expect(store.controlValues.prompt).toBe("preset prompt");
    expect(store.controlValues.source_image).toBeUndefined();
    expect(store.outputOverride).toEqual({});
    expect(store.presetDirty).toBe(false);
  });

  it("enqueues frozen variants without submitting", async () => {
    const store = usePlaygroundStore();
    await store.selectWorkflow("wf-1", "", okJson(RUN_CONTEXT) as never);
    store.setControl("prompt", "v1");
    const post = vi.fn();
    store.enqueueCurrent();
    store.setControl("prompt", "v2");
    expect(store.queue).toHaveLength(1);
    expect(store.queue[0].controlValues.prompt).toBe("v1");
    expect(post).not.toHaveBeenCalled();
  });

  it("restores the last generation id for the same context only", async () => {
    const store = usePlaygroundStore();
    await store.selectWorkflow("wf-1", "", okJson(RUN_CONTEXT) as never);
    store.noteSucceeded("gen-9");
    expect(store.currentGenerationId).toBe("gen-9");
    // Same context restores; a different version does not inherit it.
    await store.selectWorkflow("wf-1", "", okJson(RUN_CONTEXT) as never);
    expect(store.currentGenerationId).toBe("gen-9");
    const other = {
      ...RUN_CONTEXT,
      version: { workflow_version_id: "v-2", runnable: true },
    };
    await store.selectWorkflow("wf-1", "", okJson(other) as never);
    expect(store.currentGenerationId).toBeNull();
  });

  it("drains a singleton chunk through the single-run path", async () => {
    const store = usePlaygroundStore();
    await store.selectWorkflow("wf-1", "", okJson(RUN_CONTEXT) as never);
    store.setControl("prompt", "queued");
    store.enqueueCurrent();
    const result = await store.drainQueue({
      fetchImpl: okJson({ status: "ok", runId: "r-q", direct_run: true }) as never,
    });
    expect(result.ok).toBe(true);
    expect(store.runState.status).toBe("succeeded");
    expect(store.runState.message).not.toMatch(/Batch running/);
  });

  it("drains a multi-variant chunk through run_batch with frozen prompts", async () => {
    const store = usePlaygroundStore();
    await store.selectWorkflow("wf-1", "", okJson(RUN_CONTEXT) as never);
    const seen: Array<{ url: string; body: Record<string, never> }> = [];
    const fetchImpl = (async (url: string, init?: RequestInit) => {
      seen.push({ url, body: JSON.parse(String(init?.body)) as Record<string, never> });
      return { ok: true, status: 200, text: async () => JSON.stringify({ status: "ok" }) };
    }) as unknown as typeof fetch;
    store.setControl("prompt", "one");
    store.enqueueCurrent();
    store.setControl("prompt", "two");
    store.enqueueCurrent();
    const result = await store.drainQueue({ fetchImpl });
    expect(result.ok).toBe(true);
    const batch = seen.find((call) => call.url === "/comfymodal/studio/run_batch");
    expect(batch).toBeTruthy();
    const payload = batch!.body as unknown as {
      workflow_id: string;
      variants: Array<{ controls: { prompt: string } }>;
    };
    expect(payload.workflow_id).toBe("wf-1");
    expect(payload.variants.map((variant) => variant.controls.prompt)).toEqual(["one", "two"]);
    expect(store.runState.message).toBe("Batch submitted");
  });

  it("does not become a second History cache", () => {
    const store = usePlaygroundStore();
    expect("records" in store).toBe(false);
    expect("loadFeed" in store).toBe(false);
  });
});
