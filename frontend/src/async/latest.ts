// Modal Studio Vue substrate — latest-read-wins primitive.
//
// Purpose: only the newest read tied to a changing selection/query may
// commit. When a second read starts, the first is superseded: its
// AbortSignal fires (so fetch/XHR can cancel physically) AND its result is
// marked stale even when physical cancellation is impossible.
//
// Intended future uses: selected workflow/version detail, History
// focus/query, inventory refresh, source-image ingest ownership.
//
// Do not use latest-wins blindly for mutations (async policy: mutations
// complete; latest-wins is for selection-bound reads).
//
// Deliberately NOT: retried, scheduled, prioritized, pooled,
// middleware-wrapped, or mutation-aware. If you need those, you need a
// different module.
//
// Example:
// ```ts
// const task = createLatestTask()
// const result = await task.run((signal) =>
//   workflowsApi.getVersion(versionId, { signal }),
// )
// if (result.stale) return
// state.version = result.value
// ```

export type LatestOutcome<T> =
  | { stale: false; value: T }
  | { stale: true };

export interface LatestTask {
  /**
   * Start a read. Supersedes (aborts + invalidates) any in-flight read.
   * Only the newest `run()` can resolve `{ stale: false }`.
   */
  run<T>(load: (signal: AbortSignal) => Promise<T>): Promise<LatestOutcome<T>>;
  /** Abort the in-flight read, if any. Its outcome (if observed) is stale. */
  abort: () => void;
  /** True while a read started by this task has not settled. */
  readonly pending: boolean;
}

/**
 * Create a latest-read-wins task.
 *
 * Rules:
 * - Only the newest `run()` can resolve `{ stale: false }`.
 * - A superseded `run()` resolves `{ stale: true }` — it is never mistaken
 *   for the current result, even if its promise resolves normally.
 * - The superseded invocation's AbortSignal is aborted when supported.
 * - A failure from the CURRENT invocation rejects (distinguishable from
 *   staleness). A failure from a SUPERSEDED invocation resolves stale.
 */
export function createLatestTask(): LatestTask {
  let generation = 0;
  let inFlight: AbortController | null = null;

  const task: LatestTask = {
    run: async <T>(
      load: (signal: AbortSignal) => Promise<T>,
    ): Promise<LatestOutcome<T>> => {
      generation += 1;
      const mine = generation;
      if (inFlight) inFlight.abort();
      const controller = new AbortController();
      inFlight = controller;
      try {
        const value = await load(controller.signal);
        if (mine !== generation || controller.signal.aborted) {
          return { stale: true };
        }
        return { stale: false, value };
      } catch (err) {
        if (mine !== generation) return { stale: true };
        throw err;
      } finally {
        if (inFlight === controller) inFlight = null;
      }
    },
    abort: () => {
      if (inFlight) inFlight.abort();
    },
    get pending() {
      return inFlight !== null;
    },
  };
  return task;
}
