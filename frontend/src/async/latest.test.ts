// latest.ts — focused unit tests.
// Proves: normal completion, supersede-makes-stale, stale results never
// mistaken for current, AbortSignal fires for superseded invocations,
// failures distinguishable from staleness.
import { describe, expect, it, vi } from "vitest";
import { createLatestTask } from "./latest";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (err: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("createLatestTask", () => {
  it("first invocation may complete normally", async () => {
    const task = createLatestTask();
    const outcome = await task.run(async () => "one");
    expect(outcome).toEqual({ stale: false, value: "one" });
    expect(task.pending).toBe(false);
  });

  it("second invocation makes the first stale; stale result cannot commit", async () => {
    const first = deferred<string>();
    const second = deferred<string>();
    let calls = 0;
    const task = createLatestTask();
    const p1 = task.run((_signal) => {
      calls += 1;
      return calls === 1 ? first.promise : second.promise;
    });
    expect(task.pending).toBe(true);
    const p2 = task.run((_signal) => {
      calls += 1;
      return calls === 1 ? first.promise : second.promise;
    });
    first.resolve("stale-value");
    second.resolve("current-value");
    const [o1, o2] = await Promise.all([p1, p2]);
    expect(o1).toEqual({ stale: true });
    expect(o2).toEqual({ stale: false, value: "current-value" });
  });

  it("carries per-run arguments like a selection id", async () => {
    const task = createLatestTask();
    const read = (id: string) => task.run(async () => `detail:${id}`);
    expect(await read("wf_1")).toEqual({ stale: false, value: "detail:wf_1" });
    expect(await read("wf_2")).toEqual({ stale: false, value: "detail:wf_2" });
  });

  it("aborts the superseded invocation signal when supported", async () => {
    const seen: AbortSignal[] = [];
    const gate = deferred<string>();
    const task = createLatestTask();
    const p1 = task.run((signal) => {
      seen.push(signal);
      return gate.promise;
    });
    const p2 = task.run((signal) => {
      seen.push(signal);
      return gate.promise;
    });
    expect(seen[0].aborted).toBe(true);
    expect(seen[1].aborted).toBe(false);
    gate.resolve("v");
    await expect(p1).resolves.toEqual({ stale: true });
    await expect(p2).resolves.toEqual({ stale: false, value: "v" });
  });

  it("current failures reject; superseded failures resolve stale", async () => {
    // Current failure propagates (distinguishable from staleness).
    const failing = createLatestTask();
    await expect(
      failing.run(async () => {
        throw new Error("boom-current");
      }),
    ).rejects.toThrow("boom-current");

    // Superseded failure is stale, not an error.
    const first = deferred<string>();
    let calls = 0;
    const task = createLatestTask();
    const next = () => {
      calls += 1;
      return calls === 1 ? first.promise : Promise.resolve("new");
    };
    const p1 = task.run(next);
    const p2 = task.run(next);
    first.reject(new Error("boom-superseded"));
    await expect(p1).resolves.toEqual({ stale: true });
    await expect(p2).resolves.toEqual({ stale: false, value: "new" });
  });

  it("explicit abort marks the in-flight read stale-capable", async () => {
    const onAbort = vi.fn();
    const gate = deferred<string>();
    const task = createLatestTask();
    const p = task.run((signal) => {
      signal.addEventListener("abort", onAbort, { once: true });
      return gate.promise;
    });
    task.abort();
    expect(onAbort).toHaveBeenCalledTimes(1);
    gate.resolve("late");
    // Aborted run was never superseded by a newer generation, but its own
    // signal fired, so it must not present as current.
    await expect(p).resolves.toEqual({ stale: true });
  });
});
