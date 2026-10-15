// latest.ts — focused unit tests.
// Contract: stale means "this result must not commit" — broader than just
// supersession. Explicit owner cancellation resolves stale (never throws),
// so callers need no AbortError guards; only genuine current failures
// reject. Vectors: normal success, supersession, cooperating abort,
// ignoring abort, superseded cooperation, genuine failure, idle abort,
// pending clearing.
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
  it("1. normal current success resolves the current value", async () => {
    const task = createLatestTask();
    const outcome = await task.run(async () => "one");
    expect(outcome).toEqual({ stale: false, value: "one" });
    expect(task.pending).toBe(false);
  });

  it("2. newer run supersedes old: old stale, new current", async () => {
    const first = deferred<string>();
    const second = deferred<string>();
    let calls = 0;
    const task = createLatestTask();
    const next = () => {
      calls += 1;
      return calls === 1 ? first.promise : second.promise;
    };
    const p1 = task.run(next);
    expect(task.pending).toBe(true);
    const p2 = task.run(next);
    first.resolve("stale-value");
    second.resolve("current-value");
    const [o1, o2] = await Promise.all([p1, p2]);
    expect(o1).toEqual({ stale: true });
    expect(o2).toEqual({ stale: false, value: "current-value" });
  });

  it("3. cooperating fetch-like load rejects on abort, yet abort resolves stale", async () => {
    const onAbort = vi.fn();
    const gate = deferred<string>();
    const task = createLatestTask();
    const p = task.run(
      (signal) =>
        new Promise<string>((_resolve, reject) => {
          signal.addEventListener("abort", onAbort, { once: true });
          // Cooperating load: rejects with AbortError when the signal
          // fires, or with the gate's rejection otherwise.
          gate.promise.then(
            () => reject(new DOMException("Aborted", "AbortError")),
            reject,
          );
        }),
    );
    task.abort();
    expect(onAbort).toHaveBeenCalledTimes(1);
    gate.resolve("late");
    await expect(p).resolves.toEqual({ stale: true });
    expect(task.pending).toBe(false);
  });

  it("4. signal-ignoring never-settling load still settles promptly as stale", async () => {
    const task = createLatestTask();
    const p = task.run(() => new Promise<string>(() => {}));
    expect(task.pending).toBe(true);
    task.abort();
    await expect(p).resolves.toEqual({ stale: true });
    expect(task.pending).toBe(false);
  });

  it("5. superseded cooperating load resolves stale and never throws", async () => {
    const task = createLatestTask();
    const p1 = task.run(
      (signal) =>
        new Promise<string>((_resolve, reject) => {
          signal.addEventListener("abort", () =>
            reject(new DOMException("Aborted", "AbortError")),
          );
        }),
    );
    const p2 = task.run(async () => "current");
    await expect(p1).resolves.toEqual({ stale: true });
    await expect(p2).resolves.toEqual({ stale: false, value: "current" });
  });

  it("6. genuine current failure without cancellation rejects", async () => {
    const task = createLatestTask();
    await expect(
      task.run(async () => {
        throw new Error("boom-current");
      }),
    ).rejects.toThrow("boom-current");
    expect(task.pending).toBe(false);

    // A superseded failure stays stale, not an error.
    const first = deferred<string>();
    let calls = 0;
    const superseded = createLatestTask();
    const next = () => {
      calls += 1;
      return calls === 1 ? first.promise : Promise.resolve("new");
    };
    const q1 = superseded.run(next);
    const q2 = superseded.run(next);
    first.reject(new Error("boom-superseded"));
    await expect(q1).resolves.toEqual({ stale: true });
    await expect(q2).resolves.toEqual({ stale: false, value: "new" });
  });

  it("7. abort with nothing running is a harmless no-op", () => {
    const task = createLatestTask();
    expect(() => task.abort()).not.toThrow();
    expect(() => task.abort(new Error("reason"))).not.toThrow();
    expect(task.pending).toBe(false);
  });

  it("8. pending becomes false after explicit abort", async () => {
    const task = createLatestTask();
    const p = task.run(() => new Promise<string>(() => {}));
    expect(task.pending).toBe(true);
    task.abort();
    await expect(p).resolves.toEqual({ stale: true });
    expect(task.pending).toBe(false);
  });

  it("abort reason reaches the signal for transport/debug but stays out of the outcome", async () => {
    const task = createLatestTask();
    let observed: unknown = "unset";
    const p = task.run((signal) => {
      signal.addEventListener("abort", () => {
        observed = signal.reason;
      });
      return new Promise<string>(() => {});
    });
    const reason = new Error("owner-cancelled");
    task.abort(reason);
    await expect(p).resolves.toEqual({ stale: true });
    expect(observed).toBe(reason);
  });

  it("carries per-run arguments like a selection id", async () => {
    const task = createLatestTask();
    const read = (id: string) => task.run(async () => `detail:${id}`);
    expect(await read("wf_1")).toEqual({ stale: false, value: "detail:wf_1" });
    expect(await read("wf_2")).toEqual({ stale: false, value: "detail:wf_2" });
  });
});
