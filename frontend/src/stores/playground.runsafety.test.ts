// Playground run lifecycle — shared execution safety contracts.
//
// Deterministic integration tests through the real store + controller +
// fake transport. No sleeps, no browser, no backend: ordering is proven by
// explicitly sequenced awaits/deferreds.
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useHistoryStore } from "./history";
import { useOperationsStore } from "./operations";
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

function deferredJson() {
  let resolve!: (payload: unknown) => void;
  const seen: Array<{ url: string; body: unknown }> = [];
  const fetchImpl = (async (url: string, init?: RequestInit) => {
    seen.push({ url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    const payload = await new Promise<unknown>((inner) => {
      resolve = inner;
    });
    return { ok: true, status: 200, text: async () => JSON.stringify(payload) };
  }) as unknown as typeof fetch;
  return { fetchImpl, seen, respond: (payload: unknown) => resolve(payload) };
}

async function selectRunnable() {
  const store = usePlaygroundStore();
  await store.selectWorkflow("wf-1", "", okJson(RUN_CONTEXT) as never);
  store.setControl("prompt", "hello");
  return store;
}

beforeEach(() => {
  setActivePinia(createPinia());
  try {
    localStorage.clear();
  } catch {
    /* storage-backed environments only */
  }
});

describe("run identity + terminal ownership", () => {
  it("mints a fresh run identity per click", async () => {
    const store = await selectRunnable();
    await store.submitRun({ fetchImpl: okJson({ status: "ok", runId: "r-1", direct_run: true }) as never });
    const first = store.runState.runId;
    expect(first).toBeTruthy();
    await store.submitRun({ fetchImpl: okJson({ status: "ok", runId: "r-2", direct_run: true }) as never });
    expect(store.runState.runId).toBeTruthy();
    expect(store.runState.runId).not.toBe(first);
  });

  it("cancel then late success cannot resurrect the run", async () => {
    const store = await selectRunnable();
    const gate = deferredJson();
    const pending = store.submitRun({ fetchImpl: gate.fetchImpl });
    await Promise.resolve();
    expect(store.runState.status).toBe("submitting");
    const runId = store.runState.runId;
    await store.cancelRun();
    expect(store.runState.status).toBe("canceled");
    expect(store.runState.runId).toBe(runId);
    gate.respond({ status: "ok", runId: "backend-late", direct_run: true });
    const result = await pending;
    expect(result.ok).toBe(false);
    expect(store.runState.status).toBe("canceled");
    expect(store.runState.runId).toBe(runId);
  });

  it("success then late progress/failure cannot regress the run", async () => {
    const store = await selectRunnable();
    await store.submitRun({ fetchImpl: okJson({ status: "ok", runId: "r-1", direct_run: true }) as never });
    expect(store.runState.status).toBe("succeeded");
    store.noteFailed("late failure");
    expect(store.runState.status).toBe("succeeded");
    store.noteSucceeded("late-other");
    expect(store.runState.status).toBe("succeeded");
  });

  it("duplicate terminal settles once (first terminal wins)", async () => {
    const store = await selectRunnable();
    await store.submitRun({ fetchImpl: okJson({ status: "ok", runId: "r-1", direct_run: true }) as never });
    expect(store.runState.status).toBe("succeeded");
    store.noteFailed("second terminal");
    expect(store.runState.status).toBe("succeeded");
    expect(store.runState.message).toBe("Run completed");
  });

  it("failure preserves the run identity and details", async () => {
    const store = await selectRunnable();
    const result = await store.submitRun({
      fetchImpl: okJson({ status: "error", message: "GPU busy" }) as never,
    });
    expect(result.ok).toBe(false);
    expect(store.runState.status).toBe("failed");
    expect(store.runState.runId).toBeTruthy();
    expect(store.runState.message).toBe("GPU busy");
  });

  it("an overlapping click cannot hijack the in-flight run (busy gate)", async () => {
    const store = await selectRunnable();
    const first = deferredJson();
    const firstPending = store.submitRun({ fetchImpl: first.fetchImpl });
    await Promise.resolve();
    const firstRunId = store.runState.runId;
    expect(firstRunId).toBeTruthy();
    // A second click while the first run is in flight is rejected: the
    // active run keeps its identity and the late first result still
    // completes it (no cross-run hijack in either direction).
    const rejected = await store.submitRun({ fetchImpl: okJson({ status: "ok", runId: "other" }) as never });
    expect(rejected.ok).toBe(false);
    expect(store.runState.runId).toBe(firstRunId);
    first.respond({ status: "ok", runId: "first-backend", direct_run: true });
    await firstPending;
    expect(store.runState.status).toBe("succeeded");
    expect(store.runState.runId).toBe(firstRunId);
  });

  it("workflow switch mid-run cannot mutate the active run", async () => {
    const store = await selectRunnable();
    const gate = deferredJson();
    const pending = store.submitRun({ fetchImpl: gate.fetchImpl });
    await Promise.resolve();
    const runId = store.runState.runId;
    // User switches workflow while the run is in flight.
    const other = {
      ...RUN_CONTEXT,
      version: { workflow_version_id: "v-9", runnable: true },
      control_schema: { strength: { label: "Strength", default: 0.5 } },
    };
    await store.selectWorkflow("wf-1", "", okJson(other) as never);
    // The active run keeps its identity; the submitted payload keeps the
    // original workflow/version.
    expect(store.runState.runId).toBe(runId);
    gate.respond({ status: "ok", runId: "r-mid", direct_run: true });
    await pending;
    expect(store.runState.status).toBe("succeeded");
    expect(store.lastSubmitted?.workflow_version_id).toBe("v-1");
  });
});

describe("authoritative result + history convergence", () => {
  it("successful run converges into history recent ids (id only)", async () => {
    const store = await selectRunnable();
    const history = useHistoryStore();
    await store.submitRun({ fetchImpl: okJson({ status: "ok", runId: "gen-42", direct_run: true }) as never });
    expect(store.currentGenerationId).toBe("gen-42");
    expect(history.recentRunIds.map((entry) => entry.id)).toContain("gen-42");
    // No entity cached in history records by the run path.
    expect(history.records.find((record) => record.id === "gen-42")).toBeUndefined();
  });

  it("failed run does not converge a history entry", async () => {
    const store = await selectRunnable();
    const history = useHistoryStore();
    await store.submitRun({ fetchImpl: okJson({ status: "error", message: "nope" }) as never });
    expect(store.runState.status).toBe("failed");
    expect(history.recentRunIds).toHaveLength(0);
  });

  it("cancel marks the shared operation registry canceled exactly once", async () => {
    const store = await selectRunnable();
    const gate = deferredJson();
    const pending = store.submitRun({ fetchImpl: gate.fetchImpl });
    await Promise.resolve();
    const operations = useOperationsStore();
    await store.cancelRun();
    gate.respond({ status: "ok", runId: "late", direct_run: true });
    await pending;
    const canceled = operations.all.filter((op) => op.status === "canceled");
    expect(canceled).toHaveLength(1);
    expect(store.runState.status).toBe("canceled");
    void vi;
  });
});
