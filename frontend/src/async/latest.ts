// Modal Studio Vue substrate — latest-read-wins primitive.
//
// Purpose: only the newest read tied to a changing selection/query may
// commit. When a second read starts, the first is superseded: its
// AbortSignal fires (so fetch/XHR can cancel physically) AND its result is
// marked stale even when physical cancellation is impossible.
//
// In this primitive, stale means exactly one thing:
//
//   "this result must not commit"
//
// It is intentionally broader than "a newer request superseded this one."
// Explicit owner cancellation (selection teardown, component teardown,
// route change) is normal control flow for selection-bound reads, so an
// explicitly aborted run also resolves stale — callers never need
// repetitive AbortError catch blocks just to ignore an intentionally
// canceled read. That guard-removal is the point of this module.
//
// Outcomes:
// - `{ stale: false, value }` — the newest read; commit it.
// - `{ stale: true }`         — superseded by a newer read, or explicitly
//                               aborted by the owner. Ignore silently; never
//                               throws, so fire-and-forget reads are safe.
// - throw                     — a GENUINE failure from the current,
//                               non-aborted invocation. Distinguishable from
//                               staleness; the caller owns it.
//
// Explicit `abort()` always settles the in-flight run promptly as stale,
// even when `load` ignores the signal — it never hangs. The optional
// reason is passed into the AbortController for transport/debug purposes
// only; it never surfaces to the caller.
//
// Intended future uses: selected workflow/version detail, History
// focus/query, inventory refresh, source-image ingest ownership.
//
// Do not use latest-wins blindly for mutations (async policy: mutations
// complete; latest-wins is for selection-bound reads).
//
// Deliberately NOT: retried, scheduled, prioritized, pooled,
// middleware-wrapped, mutation-aware, or a generic cancellation/error
// framework. If you need those, you need a different module.
//
// Example — no AbortError catch required:
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
  /**
   * Abort the in-flight read, if any: aborts the underlying AbortSignal
   * (passing `reason` through for transport/debug) and settles the run
   * promptly as `{ stale: true }`, even if `load` ignores the signal.
   * Never throws, never surfaces the reason. No-op when nothing runs.
   */
  abort: (reason?: unknown) => void;
  /** True while a read started by this task has not settled. */
  readonly pending: boolean;
}

interface InFlight {
  controller: AbortController;
  superseded: boolean;
}

/**
 * Create a latest-read-wins task.
 *
 * Rules:
 * - Only the newest `run()` can resolve `{ stale: false }`.
 * - A superseded `run()` resolves `{ stale: true }` — it is never mistaken
 *   for the current result, even if its promise resolves normally, and it
 *   never throws.
 * - The superseded invocation's AbortSignal is aborted when supported.
 * - Explicit `abort()` resolves the in-flight run stale, promptly and
 *   unconditionally — the abort reason stays inside the AbortController.
 * - A genuine failure from the CURRENT, non-aborted invocation rejects
 *   (distinguishable from staleness). A failure from a superseded or
 *   aborted invocation resolves stale.
 */
export function createLatestTask(): LatestTask {
  let generation = 0;
  let inFlight: InFlight | null = null;

  const task: LatestTask = {
    run: <T>(
      load: (signal: AbortSignal) => Promise<T>,
    ): Promise<LatestOutcome<T>> => {
      generation += 1;
      const mine = generation;
      const prev = inFlight;
      if (prev) {
        prev.superseded = true;
        prev.controller.abort();
      }
      const controller = new AbortController();
      const record: InFlight = { controller, superseded: false };
      // Settles the race below when THIS invocation's signal fires, no
      // matter what `load` does with (or without) the signal. Supersession
      // and explicit abort take the same stale path by design.
      let settleStale!: () => void;
      const aborted = new Promise<LatestOutcome<T>>((resolve) => {
        settleStale = () => resolve({ stale: true });
      });
      const onAbort = () => settleStale();
      controller.signal.addEventListener("abort", onAbort, { once: true });
      inFlight = record;
      const finish = () => {
        controller.signal.removeEventListener("abort", onAbort);
        if (inFlight === record) inFlight = null;
      };
      return (async (): Promise<LatestOutcome<T>> => {
        try {
          return await Promise.race([
            load(controller.signal).then((value): LatestOutcome<T> => {
              if (mine !== generation || record.superseded || controller.signal.aborted) {
                return { stale: true };
              }
              return { stale: false, value };
            }),
            aborted,
          ]);
        } catch (err) {
          if (record.superseded || mine !== generation || controller.signal.aborted) {
            return { stale: true };
          }
          throw err;
        } finally {
          finish();
        }
      })();
    },
    abort: (reason?: unknown) => {
      // No-op when nothing is in flight. abort(undefined) keeps the
      // default AbortError reason on the signal for transport/debug; the
      // LatestTask outcome is stale either way.
      inFlight?.controller.abort(reason);
    },
    get pending() {
      return inFlight !== null;
    },
  };
  return task;
}
