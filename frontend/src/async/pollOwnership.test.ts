// Long-operation poll ownership — single-owner contract.
//
// Deterministic proof using the real primitives (pollUntil + operations
// registry + domain-owned AbortController), structured exactly like the
// infra deploy/swap owners: one domain owner, no duplicate loops on
// reentry, route navigation (no abort) never kills the operation, terminal
// /dispose stops the loop promptly with no extra status call, and domain
// success/failure semantics settle the registry.
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { pollUntil } from "./polling";
import { useOperationsStore } from "../stores/operations";

function tick(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

beforeEach(() => {
  setActivePinia(createPinia());
});

/** Minimal domain owner mirroring infra deploy()/pollSwap() structure. */
function createDomainOwner(statuses: string[]) {
  const operations = useOperationsStore();
  let operationId: string | null = null;
  let controller: AbortController | null = null;
  const run = vi.fn(async () => {
    const next = statuses.shift() ?? "ready";
    operations.patch(operationId!, { message: `Deployment: ${next}` });
    return next;
  });
  async function start(): Promise<string> {
    if (operationId) return operationId; // single owner: reentry reuses
    operationId = operations.start({ kind: "deploy", label: "Deploy" });
    controller = new AbortController();
    const signal = controller.signal;
    try {
      const final = await pollUntil({
        intervalMs: 1,
        signal,
        run,
        done: (value) => value === "ready" || value === "failed",
      });
      if (final !== "ready") throw new Error(`Deployment ended in ${final}`);
      operations.finish(operationId, "Deployment completed");
    } catch (cause) {
      operations.fail(operationId, cause instanceof Error ? cause.message : "failed");
      throw cause;
    } finally {
      operationId = null;
      controller = null;
    }
    return operationId ?? "";
  }
  function dispose(): void {
    controller?.abort();
  }
  return { start, dispose, run };
}

describe("poll ownership", () => {
  it("rerender/reentry never creates a second owner", async () => {
    const owner = createDomainOwner(["deploying", "ready"]);
    const first = owner.start();
    const second = owner.start(); // simulated rerender/reopen reentry
    await Promise.all([first, second]);
    expect(owner.run).toHaveBeenCalledTimes(2); // one loop, not two
  });

  it("terminal stops the loop with no extra status call", async () => {
    const owner = createDomainOwner(["ready"]);
    await owner.start();
    expect(owner.run).toHaveBeenCalledTimes(1);
  });

  it("dispose/abort stops the loop promptly with no zombie calls", async () => {
    const owner = createDomainOwner(["deploying", "deploying", "deploying", "ready"]);
    const pending = owner.start();
    await tick();
    const callsBeforeAbort = owner.run.mock.calls.length;
    expect(callsBeforeAbort).toBeGreaterThanOrEqual(1);
    owner.dispose();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
    const callsAfterAbort = owner.run.mock.calls.length;
    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(owner.run.mock.calls.length).toBe(callsAfterAbort); // no zombies
  });

  it("navigation without abort never kills the operation (domain owns lifetime)", async () => {
    const owner = createDomainOwner(["deploying", "ready"]);
    const pending = owner.start();
    // A route change performs no abort: the domain controller is untouched.
    await pending;
    const operations = useOperationsStore();
    expect(operations.all.filter((op) => op.status === "completed")).toHaveLength(1);
  });

  it("domain failure semantics settle the registry (failed, not silent)", async () => {
    const owner = createDomainOwner(["failed"]);
    await expect(owner.start()).rejects.toThrow("Deployment ended in failed");
    const operations = useOperationsStore();
    expect(operations.all.filter((op) => op.status === "failed")).toHaveLength(1);
  });
});
