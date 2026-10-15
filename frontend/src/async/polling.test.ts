// polling.ts — focused unit tests.
// Proves: repeats until predicate succeeds, returns final value, abort
// stops promptly, no call after terminal result, errors propagate.
import { describe, expect, it, vi } from "vitest";
import { pollUntil } from "./polling";

describe("pollUntil", () => {
  it("repeats until predicate succeeds and returns the final value", async () => {
    const seen: number[] = [];
    const result = await pollUntil({
      intervalMs: 5,
      run: async (_signal, attempt) => {
        seen.push(attempt);
        return attempt >= 3 ? "done" : "waiting";
      },
      done: (v) => v === "done",
    });
    expect(result).toBe("done");
    expect(seen).toEqual([1, 2, 3]);
  });

  it("does not call again after a terminal result", async () => {
    const run = vi.fn(async () => "done");
    const result = await pollUntil({ intervalMs: 1, run, done: (v) => v === "done" });
    expect(result).toBe("done");
    expect(run).toHaveBeenCalledTimes(1);
  });

  it("abort stops polling promptly, even mid-interval", async () => {
    const controller = new AbortController();
    const run = vi.fn(async () => "waiting");
    const started = Date.now();
    const pending = pollUntil({
      intervalMs: 60_000,
      signal: controller.signal,
      run,
      done: (v) => v === "done",
    });
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
    expect(Date.now() - started).toBeLessThan(1000);
    expect(run).toHaveBeenCalledTimes(1);
  });

  it("already-aborted signal never calls run", async () => {
    const controller = new AbortController();
    controller.abort();
    const run = vi.fn(async () => "done");
    await expect(
      pollUntil({ intervalMs: 1, signal: controller.signal, run, done: () => true }),
    ).rejects.toMatchObject({ name: "AbortError" });
    expect(run).not.toHaveBeenCalled();
  });

  it("thrown callback errors propagate unchanged (fail-fast policy)", async () => {
    const failure = new Error("status endpoint blew up");
    const run = vi.fn(async () => {
      throw failure;
    });
    await expect(
      pollUntil({ intervalMs: 1, run, done: () => false }),
    ).rejects.toBe(failure);
    expect(run).toHaveBeenCalledTimes(1);
  });
});
