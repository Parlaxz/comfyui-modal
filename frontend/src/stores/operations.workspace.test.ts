// Operations workspace binding — accepted-target immutability.
//
// Deterministic proof that an accepted operation stays bound to the
// workspace it was accepted in: switching the active workspace changes
// future operations only, and patch() can never retarget an accepted
// operation. Mirrors the infra deploy/swap frozen-target capture.
import { beforeEach, describe, expect, it } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useOperationsStore } from "./operations";

beforeEach(() => {
  setActivePinia(createPinia());
});

describe("workspace target binding", () => {
  it("accepted operation stays bound to A after the active workspace moves to B", () => {
    const operations = useOperationsStore();
    // Accepted while workspace A is active (frozen at acceptance, as infra
    // deploy/swap capture activeWorkspaceId into start()).
    const opA = operations.start({ kind: "deploy", label: "Deploy", workspaceId: "ws-A" });
    // User switches the active workspace to B.
    const opB = operations.start({ kind: "deploy", label: "Deploy", workspaceId: "ws-B" });
    // Completion of A still belongs to A; B belongs to B.
    operations.finish(opA, "done");
    expect(operations.get(opA)?.workspaceId).toBe("ws-A");
    expect(operations.get(opB)?.workspaceId).toBe("ws-B");
  });

  it("patch() can never retarget an accepted operation", () => {
    const operations = useOperationsStore();
    const op = operations.start({ kind: "deploy", label: "Deploy", workspaceId: "ws-A" });
    operations.patch(op, { message: "still working", workspaceId: "ws-B" });
    expect(operations.get(op)?.workspaceId).toBe("ws-A");
    expect(operations.get(op)?.message).toBe("still working");
  });

  it("operations without a workspace stay workspace-free (no invented ownership)", () => {
    const operations = useOperationsStore();
    const op = operations.start({ kind: "generation", label: "Generation" });
    expect(operations.get(op)?.workspaceId).toBeUndefined();
    operations.patch(op, { message: "Running…" });
    expect(operations.get(op)?.workspaceId).toBeUndefined();
  });
});
