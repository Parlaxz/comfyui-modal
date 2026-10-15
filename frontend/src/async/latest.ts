// Modal Studio Vue substrate — latest-read-wins primitive.
//
// Purpose: only the newest read tied to a changing selection/query may
// commit. When a second read starts, the first is superseded: its
// AbortSignal fires (so fetch/XHR can cancel physically) AND its result is
// marked stale even when physical cancellation is impossible.
//
// Three sharply distinct outcomes, never conflated:
// - `{ stale: false, value }` — the newest read; commit it.
// - `{ stale: true }`         — superseded by a newer read; ignore silently.
//                               Never throws, so fire-and-forget reads are safe.
// - throw                     — the CURRENT read failed, or the owner
//                               explicitly aborted it via `abort()`.
//                               Catch `AbortError` (by name) for explicit
//                               cancellation; anything else is a real failure.
//
// Explicit `abort()` always settles the in-flight run (rejecting with the
// abort reason) even when `load` ignores the signal — it never hangs and
// never resolves stale, because an explicitly aborted newest read was NOT
// superseded by anything. Supersession always resolves stale, never throws.
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
// try {
//   const result = await task.run((signal) =>
//     workflowsApi.getVersion(versionId, { signal }),
//   )
//   if (result.stale) return
//   state.version = result.value
// } catch (err) {
//   if (err instanceof DOMException && err.name === "AbortError") return
//   throw err
// }
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
   * Abort the in-flight read, if any. The aborted run REJECTS with the
   * abort reason (an `AbortError` DOMException by default) — it does not
   * resolve stale, and it settles even if `load` ignores the signal.
   * No-op when nothing is in flight.
   */
  abort: (reason?: unknown) => void;
  /** True while a read started by this task has not settled. */
  readonly pending: boolean;
}

interface InFlight {
  controller: AbortController;
  superseded: boolean;
  onAbort: () => void;
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
 * - A failure from the CURRENT invocation rejects (distinguishable from
 *   staleness). A failure from a SUPERSEDED invocation resolves stale.
 * - Explicit `abort()` rejects the in-flight run with the abort reason,
 *   deterministically, whether or not `load` cooperates.
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
      const record: InFlight = {
        controller,
        superseded: false,
        onAbort: () => {},
      };
      // Settles the race below when THIS invocation's signal fires, no
      // matter what `load` does with (or without) the signal.
      let rejectOnAbort!: (reason: unknown) => void;
      const aborted = new Promise<never>((_resolve, reject) => {
        rejectOnAbort = reject;
      });
      // Prevent an unhandled rejection when `load` settles first: the race
      // attaches handlers to both branches, and this no-op catch covers the
      // window before the race subscribes... (race subscribes synchronously,
      // so this is strictly belt-and-braces for abort() racing settle).
      aborted.catch(() => {});
      record.onAbort = () => {
        rejectOnAbort(controller.signal.reason);
      };
      controller.signal.addEventListener("abort", record.onAbort, { once: true });
      inFlight = record;
      const finish = () => {
        controller.signal.removeEventListener("abort", record.onAbort);
        if (inFlight === record) inFlight = null;
      };
      return (async (): Promise<LatestOutcome<T>> => {
        try {
          const value = await Promise.race([load(controller.signal), aborted]);
          if (mine !== generation || record.superseded || controller.signal.aborted) {
            return { stale: true };
          }
          return { stale: false, value };
        } catch (err) {
          if (record.superseded || mine !== generation) return { stale: true };
          throw err;
        } finally {
          finish();
        }
      })();
    },
    abort: (reason?: unknown) => {
      // No-op when nothing is in flight. abort(undefined) keeps the
      // default AbortError reason.
      inFlight?.controller.abort(reason);
    },
    get pending() {
      return inFlight !== null;
    },
  };
  return task;
}
