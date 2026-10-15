// operations store — focused unit tests.
// Proves: start/patch/finish/fail/cancel/remove, operation isolation,
// and no domain transition logic (the registry records; callers own lifecycle).
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

  it("records caller-declared statuses without a transition engine", () => {
    const store = useOperationsStore();
    // A caller may report pending first, then running — or jump straight to
    // completed. The registry records; it never vetoes domain flow.
    const id = store.start({ kind: "workflow-import", label: "X", status: "pending" });
    store.patch(id, { status: "completed" });
    expect(store.get(id)!.status).toBe("completed");
    expect(store.get(id)!.finishedAt).toBeUndefined();
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

  it("starting with a terminal status records finishedAt immediately", () => {
    const store = useOperationsStore();
    const id = store.start({ kind: "other", label: "O", status: "completed" });
    const op = store.get(id)!;
    expect(op.status).toBe("completed");
    expect(typeof op.finishedAt).toBe("number");
    expect(store.active.map((o) => o.id)).not.toContain(id);
  });
});
