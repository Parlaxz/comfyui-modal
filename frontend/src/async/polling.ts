// Modal Studio Vue substrate — small polling primitive.
//
// Purpose: delete repeated polling boilerplate without stealing domain
// semantics. The utility owns delay, abort handling, loop lifecycle, and
// generic repeat mechanics. The domain owns the endpoint, interpretation,
// success/failure messages, retry/refusal semantics, and operationStore
// updates.
//
// Example:
// ```ts
// await pollUntil({
//   signal,
//   intervalMs: 2000,
//   run: () => goldenApi.getDeployStatus(profile),
//   done: (value) => value.state === "done" || value.state === "failed",
// })
// ```
//
// Deliberately NOT a scheduler and NOT domain-aware: this module knows
// nothing about deployments, downloads, or sync. Thrown callback errors
// propagate to the caller (documented policy: fail fast — the caller owns
// retry semantics). Do not build a polling scheduler framework.

export interface PollUntilOptions<T> {
  /** Delay between attempts once the previous attempt settled. */
  intervalMs: number;
  /** When aborted, polling stops promptly with an AbortError. */
  signal?: AbortSignal;
  /** One status attempt. Receives the abort signal and 1-based attempt. */
  run: (signal: AbortSignal | undefined, attempt: number) => Promise<T>;
  /** Return the value as soon as this returns true. */
  done: (value: T) => boolean;
  /** Optional hook observed per attempt (1-based). Test/UX aid only. */
  onAttempt?: (attempt: number) => void;
}

function throwIfAborted(signal?: AbortSignal): void {
  if (signal && signal.aborted) {
    throw new DOMException("Polling aborted", "AbortError");
  }
}

function sleepAbortable(ms: number, signal?: AbortSignal): Promise<void> {
  if (signal && signal.aborted) {
    return Promise.reject(new DOMException("Polling aborted", "AbortError"));
  }
  if (!signal) return new Promise((resolve) => setTimeout(resolve, ms));
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      reject(new DOMException("Polling aborted", "AbortError"));
    };
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

/**
 * Call `run` until `done(value)` is true, then return that value.
 *
 * Guarantees: no call happens after a terminal result; abort stops polling
 * promptly (even mid-interval); callback errors propagate unchanged.
 */
export async function pollUntil<T>(options: PollUntilOptions<T>): Promise<T> {
  const { intervalMs, signal, run, done, onAttempt } = options;
  let attempt = 0;
  for (;;) {
    throwIfAborted(signal);
    attempt += 1;
    if (onAttempt) onAttempt(attempt);
    const value = await run(signal, attempt);
    if (done(value)) return value;
    await sleepAbortable(intervalMs, signal);
  }
}
