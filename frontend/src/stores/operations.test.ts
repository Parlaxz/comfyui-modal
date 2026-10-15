// operations store — focused unit tests.
// Proves: start/patch/finish/fail/cancel/remove, operation isolation, one
// canonical terminal path (finish/fail/cancel only), and no domain
// transition logic (the registry records; callers own lifecycle).
import { beforeEach, describe, expect, it } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useOperationsStore } from "./operations";

beforeEach(() => {
  setActivePinia(createPinia());
});

describe("useOperationsStore", () => {
  it("starts an operation with a presentation record", () => {
    const store = useOperationsStore();
    const id = store.start({ kind: "deploy", label: "Deploy golden profile" });
    const op = store.get(id);
    expect(op).toMatchObject({
      id,
      kind: "deploy",
      label: "Deploy golden profile",
      status: "running",
    });
    expect(op!.progress).toBeUndefined();
    expect(op!.message).toBeUndefined();
    expect(op!.workspaceId).toBeUndefined();
    expect(typeof op!.startedAt).toBe("number");
    expect(op!.finishedAt).toBeUndefined();
    expect(store.active.map((o) => o.id)).toContain(id);
  });

  it("patches presentation fields without touching identity", () => {
    const store = useOperationsStore();
    const id = store.start({ kind: "node-sync", label: "Sync" });
    const before = store.get(id)!;
    store.patch(id, { progress: 0.5, message: "halfway" });
    const after = store.get(id)!;
    expect(after.progress).toBe(0.5);
    expect(after.message).toBe("halfway");
    expect(after.startedAt).toBe(before.startedAt);
    expect(after.status).toBe("running");
  });

  it("finish/fail/cancel settle with finishedAt and leave active", () => {
    const store = useOperationsStore();
    const done = store.start({ kind: "inventory-sync", label: "A" });
    const bad = store.start({ kind: "model-download", label: "B" });
    const dropped = store.start({ kind: "other", label: "C" });
    store.finish(done, "ok");
    store.fail(bad, "boom");
    store.cancel(dropped);
    expect(store.get(done)!.status).toBe("completed");
    expect(store.get(bad)!.status).toBe("failed");
    expect(store.get(bad)!.message).toBe("boom");
    expect(store.get(dropped)!.status).toBe("canceled");
    for (const id of [done, bad, dropped]) {
      expect(typeof store.get(id)!.finishedAt).toBe("number");
    }
    expect(store.active).toHaveLength(0);
    expect(store.all).toHaveLength(3);
  });

  it("isolates operations: unknown ids are no-ops, remove drops one", () => {
    const store = useOperationsStore();
    const keep = store.start({ kind: "generation", label: "keep" });
    const drop = store.start({ kind: "experiment", label: "drop" });
    expect(store.get(keep)!.id).not.toBe(store.get(drop)!.id);
    store.patch("nope", { message: "ignored" });
    store.finish("nope");
    store.remove("nope");
    expect(store.all).toHaveLength(2);
    store.remove(drop);
    expect(store.get(drop)).toBeUndefined();
    expect(store.get(keep)!.label).toBe("keep");
  });

  it("optional pending start stays active with no finishedAt", () => {
    const store = useOperationsStore();
    const id = store.start({ kind: "deploy", label: "Queued", status: "pending" });
    const op = store.get(id)!;
    expect(op.status).toBe("pending");
    expect(op.finishedAt).toBeUndefined();
    expect(store.active.map((o) => o.id)).toContain(id);
  });

  it("patch moves pending <-> running, never into terminal state", () => {
    const store = useOperationsStore();
    const id = store.start({ kind: "workflow-import", label: "X", status: "pending" });
    store.patch(id, { status: "running" });
    expect(store.get(id)!.status).toBe("running");
    expect(store.get(id)!.finishedAt).toBeUndefined();
    store.patch(id, { status: "pending" });
    expect(store.get(id)!.status).toBe("pending");
  });

  it("freezes terminal records: first terminal wins, never regresses", () => {
    const store = useOperationsStore();
    const done = store.start({ kind: "deploy", label: "D" });
    store.finish(done, "ok");
    const finishedAt = store.get(done)!.finishedAt;
    expect(typeof finishedAt).toBe("number");
    // Late duplicate terminal calls cannot regress finished work.
    store.fail(done, "late boom");
    store.cancel(done, "late cancel");
    store.finish(done, "late ok");
    expect(store.get(done)!.status).toBe("completed");
    expect(store.get(done)!.message).toBe("ok");
    expect(store.get(done)!.finishedAt).toBe(finishedAt);

    const bad = store.start({ kind: "deploy", label: "E" });
    store.fail(bad, "boom");
    store.finish(bad, "actually fine");
    expect(store.get(bad)!.status).toBe("failed");
    expect(store.get(bad)!.message).toBe("boom");
  });

  it("patch cannot resurrect a terminal record, but may update its message", () => {
    const store = useOperationsStore();
    const id = store.start({ kind: "node-sync", label: "S" });
    store.cancel(id);
    store.patch(id, { status: "running", progress: 0.5, message: "tail arrived" });
    const op = store.get(id)!;
    expect(op.status).toBe("canceled");
    expect(typeof op.finishedAt).toBe("number");
    expect(op.message).toBe("tail arrived");
    expect(op.progress).toBe(0.5);
  });

  it("types reject terminal statuses on start and patch", () => {
    const store = useOperationsStore();
    const id = store.start({ kind: "deploy", label: "D", status: "pending" });
    // @ts-expect-error - start() creates active operations only; terminal
    // entry runs through finish()/fail()/cancel().
    const invalid = store.start({ kind: "deploy", label: "X", status: "canceled" });
    expect(store.get(invalid)!.status).toBe("running");
    expect(store.get(invalid)!.finishedAt).toBeUndefined();
    // @ts-expect-error - patch() moves between active states only, never
    // into terminal state.
    store.patch(id, { status: "completed" });
    // @ts-expect-error - same for the remaining terminal values.
    store.patch(id, { status: "failed" });
    // The rejected calls still execute at runtime (types are erased), where
    // patch() drops terminal values; the valid record is unaffected.
    expect(store.get(id)!.status).toBe("pending");
    expect(store.get(id)!.finishedAt).toBeUndefined();
  });
});
