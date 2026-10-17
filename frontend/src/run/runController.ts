// Modal Studio Vue — run controller (shared execution spine).
//
// TypeScript port of the accepted run-controller semantics owned by:
//   web/studio-playground-run.js (identity, event-source attach/detach,
//     execution-start lock, stale/foreign rejection, terminal freeze,
//     snapshot/journal dedupe, direct-result authority, Golden-present)
//   web/studio-run-model.js      (canonical terminal first-wins lock)
//   web/studio-run-adapters.js   (event adaptation)
//
// The controller is the semantic owner of run lifecycle. The playground
// store projects controller state into runState/operationsStore; neither
// the store nor the operations registry may decide terminality.
//
// Rules (ported 1:1, behavior first):
//   - Every beginRun() allocates a fresh frontend runId (+ requestId).
//     Sequential runs never share state.
//   - The ws stream locks onto the first execution_start; later
//     execution_start events are ignored while locked. Prompt-ID-carrying
//     terminal/modal events must match the captured prompt ID.
//   - Progress/executing events before any execution_start are stale and
//     dropped. Experiment events must carry this controller's experiment
//     ID; single runs (no experiment ID) drop ALL experiment events.
//   - Terminal first-wins: completed/failed/canceled/interrupted. The first
//     terminal decision is final; later success/progress/terminal events
//     (including cancel-then-success) cannot resurrect or regress it.
//   - Snapshot polls are signature-gated: identical adapted content is a
//     no-op (duplicate journal entries deduplicated).
//   - The direct POST result is terminal authority (not websocket/progress).
//   - Golden progress is presentation-only and can never complete a run.
//   - detach() drops the event source (navigation/dispose/new-run safety);
//     a detached controller rejects events until the next beginRun().
//   - Late events from a prior run (different runId) never hijack the
//     active run: handleWsEvent carries no runId because the bus delivers
//     typeless details, so prompt/experiment filtering + the ws lock are
//     the guards; direct-result/snapshot application is additionally
//     gated on the caller's runId matching the active run.
//
// Pure TypeScript, no DOM access, unit-testable in plain Node/vitest.

export type RunTerminalStatus = "completed" | "failed" | "canceled" | "interrupted";

export type RunActiveStatus =
  | "created"
  | "submitting"
  | "queued"
  | "executing"
  | "running";

export type RunStatus = RunActiveStatus | RunTerminalStatus;

export const RUN_TERMINAL_STATUSES: ReadonlySet<string> = new Set([
  "completed",
  "failed",
  "canceled",
  "interrupted",
]);

export function isRunTerminal(status: string): boolean {
  return RUN_TERMINAL_STATUSES.has(status);
}

/** Minimal websocket-event detail shape the controller filters on. */
export interface RunWsDetail {
  type?: unknown;
  prompt_id?: unknown;
  experiment_id?: unknown;
  [key: string]: unknown;
}

export interface BackendIds {
  promptId?: string | null;
  experimentId?: string | null;
}

export interface DirectResult {
  status?: unknown;
  direct_run?: unknown;
  run_id?: unknown;
  runId?: unknown;
  id?: unknown;
  error?: unknown;
  message?: unknown;
  [key: string]: unknown;
}

function newId(prefix: string): string {
  try {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID();
    }
  } catch {
    /* fall through */
  }
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

const TERMINAL_FROM_WS: Record<string, RunTerminalStatus> = {
  execution_success: "completed",
  execution_error: "failed",
  execution_interrupted: "interrupted",
};

export interface RunControllerSnapshot {
  runId: string | null;
  requestId: string | null;
  status: RunStatus | null;
  terminal: boolean;
  attached: boolean;
  promptId: string | null;
  experimentId: string | null;
  goldenNote: string | null;
}

export function createRunController() {
  let runId: string | null = null;
  let requestId: string | null = null;
  let status: RunStatus | null = null;
  let terminal = false;
  let attached = false;
  let disposed = false;
  let capturedPromptId: string | null = null;
  let experimentId: string | null = null;
  let wsLocked = false;
  let lastSnapshotSig: string | null = null;
  let goldenNote: string | null = null;
  let failureMessage: string | null = null;
  const subscribers = new Set<(snap: RunControllerSnapshot) => void>();

  function getSnapshot(): RunControllerSnapshot {
    return {
      runId,
      requestId,
      status,
      terminal,
      attached,
      promptId: capturedPromptId,
      experimentId,
      goldenNote,
    };
  }

  function notify(): void {
    const snap = getSnapshot();
    for (const fn of subscribers) {
      try {
        fn(snap);
      } catch {
        /* subscriber errors are isolated */
      }
    }
  }

  /** Terminal first-wins lock. Returns true when this call won the lock. */
  function settleTerminal(next: RunTerminalStatus, message?: string | null): boolean {
    if (terminal || disposed || runId === null) return false;
    terminal = true;
    status = next;
    if (message != null) failureMessage = String(message);
    attached = false;
    notify();
    return true;
  }

  function setActive(next: RunActiveStatus): void {
    if (terminal || disposed || runId === null) return;
    status = next;
    notify();
  }

  return {
    /** Begin a new run: fresh identity, all locks reset. Returns the runId. */
    beginRun(): string {
      attached = false;
      runId = newId("run");
      requestId = newId("req");
      status = "created";
      terminal = false;
      capturedPromptId = null;
      experimentId = null;
      wsLocked = false;
      lastSnapshotSig = null;
      goldenNote = null;
      failureMessage = null;
      notify();
      return runId;
    },

    /** Attach backend identity after the submission response. */
    setBackendIds(ids: BackendIds): void {
      if (ids.promptId != null && String(ids.promptId) !== "") {
        capturedPromptId = String(ids.promptId);
      }
      if (ids.experimentId != null && String(ids.experimentId) !== "") {
        experimentId = String(ids.experimentId);
      }
    },

    /** Submission acknowledged (scheduler path): non-terminal progress. */
    applySubmissionAck(): void {
      setActive("submitting");
    },

    /**
     * Attach the event source for this run. Detached automatically on
     * terminal, on dispose, and on the next beginRun().
     */
    attach(): void {
      if (disposed || runId === null || terminal) return;
      attached = true;
    },

    /** Detach the event source (navigation/dispose safety). */
    detach(): void {
      attached = false;
    },

    /**
     * Handle one websocket event detail. Identity-filtered exactly like
     * the legacy controller; returns true when the event advanced state.
     */
    handleWsEvent(detail: RunWsDetail | null | undefined): boolean {
      if (!detail || typeof detail !== "object" || disposed || terminal || runId === null) return false;
      if (!attached) return false;
      const type = String(detail.type ?? "");

      if (type === "execution_start") {
        if (wsLocked) return false; // stream already locked to an earlier execution
        if (detail.prompt_id != null && String(detail.prompt_id) !== "") {
          capturedPromptId = String(detail.prompt_id);
        }
        wsLocked = true;
        setActive("executing");
        return true;
      }

      // Prompt-ID mismatch → foreign execution, never touches this run.
      if (
        (type === "execution_success" || type === "execution_error" || type === "modal_status") &&
        detail.prompt_id != null &&
        capturedPromptId !== null &&
        String(detail.prompt_id) !== capturedPromptId
      ) {
        return false;
      }

      // Terminal ws events before any execution_start are stale events
      // from a previous execution and must not complete this run.
      if (
        (type === "execution_success" ||
          type === "execution_error" ||
          type === "execution_interrupted") &&
        !wsLocked
      ) {
        return false;
      }

      // Executing/progress streams only belong to a locked ws execution.
      if (!wsLocked && (type === "executing" || type === "progress" || type === "progress_state")) {
        return false;
      }

      // Experiment-gated event namespaces are rejected without a matching
      // experiment identity (single runs drop all of them).
      if (type === "experiment.worker.progress" || type === "experiment.event") {
        const expId = detail.experiment_id != null ? String(detail.experiment_id) : null;
        if (expId === null || experimentId === null || expId !== experimentId) return false;
      }

      const terminalStatus = TERMINAL_FROM_WS[type];
      if (terminalStatus) {
        return settleTerminal(terminalStatus);
      }
      if (type === "executing" || type === "progress" || type === "progress_state") {
        setActive("executing");
        return true;
      }
      return false;
    },

    /**
     * Apply one status/snapshot poll. Signature-gated: repeated polls and
     * duplicate terminal journal entries are no-ops. `callerRunId` gates
     * late prior-run polls (must equal the active runId).
     */
    applySnapshot(
      snapshotStatus: unknown,
      options: { callerRunId?: string | null; journalSignature?: string } = {},
    ): boolean {
      if (disposed || terminal || runId === null) return false;
      if (options.callerRunId !== undefined && options.callerRunId !== runId) return false; // late prior-run poll
      const normalized = String(snapshotStatus ?? "").toLowerCase();
      const sig = `${normalized}::${options.journalSignature ?? ""}`;
      if (sig === lastSnapshotSig) return false; // duplicate poll
      lastSnapshotSig = sig;
      if (normalized === "completed" || normalized === "succeeded" || normalized === "success") {
        return settleTerminal("completed");
      }
      if (normalized === "failed" || normalized === "error") {
        return settleTerminal("failed");
      }
      if (normalized === "canceled" || normalized === "cancelled") {
        return settleTerminal("canceled");
      }
      if (normalized === "interrupted") {
        return settleTerminal("interrupted");
      }
      if (normalized !== "") setActive("running");
      return true;
    },

    /**
     * Apply the direct POST result. Returns the outcome:
     * - "completed" | "failed": terminal authority won by this call;
     * - "accepted": acknowledged but still running (scheduler path —
     *   completion arrives later via events/snapshot);
     * - "ignored": late prior-run result, or the run is already terminal
     *   (first terminal wins: cancel-then-success stays canceled).
     */
    applyDirectResult(
      result: DirectResult | null | undefined,
      callerRunId?: string | null,
    ): "completed" | "failed" | "accepted" | "ignored" {
      if (!result || disposed || runId === null) return "ignored";
      if (callerRunId !== undefined && callerRunId !== runId) return "ignored"; // late prior-run result
      if (terminal) return "ignored"; // first terminal wins (cancel-then-success stays canceled)
      const statusRaw = String(result.status ?? "").toLowerCase();
      if (
        result.direct_run === true ||
        statusRaw === "ok" ||
        statusRaw === "completed" ||
        statusRaw === "succeeded"
      ) {
        return settleTerminal("completed") ? "completed" : "ignored";
      }
      if (statusRaw === "error" || statusRaw === "failed") {
        const message =
          typeof result.error === "string"
            ? result.error
            : typeof result.message === "string"
              ? result.message
              : "Run failed";
        return settleTerminal("failed", message) ? "failed" : "ignored";
      }
      // Accepted by the scheduler; the run continues via events/snapshot.
      setActive("running");
      return "accepted";
    },

    /** Local (non-backend) failure: validation or timeout. */
    applyLocalError(message: string): boolean {
      if (terminal || disposed || runId === null) return false;
      return settleTerminal("failed", message);
    },

    /** Cancel is authoritative: wins the terminal lock unless already terminal. */
    cancel(): boolean {
      return settleTerminal("canceled", "Run canceled");
    },

    /**
     * Golden stage progress: presentation only. Never decides terminality
     * and never throws into the run lifecycle.
     */
    noteGoldenProgress(note: string): void {
      try {
        if (typeof note === "string") goldenNote = note;
      } catch {
        /* progress display must not break the run */
      }
    },

    getRunId(): string | null {
      return runId;
    },

    getRequestId(): string | null {
      return requestId;
    },

    getStatus(): RunStatus | null {
      return status;
    },

    getFailureMessage(): string | null {
      return failureMessage;
    },

    isTerminal(): boolean {
      return terminal;
    },

    isAttached(): boolean {
      return attached;
    },

    getSnapshot,

    subscribe(fn: (snap: RunControllerSnapshot) => void): () => void {
      if (typeof fn === "function") subscribers.add(fn);
      return () => {
        subscribers.delete(fn);
      };
    },

    /** Dispose the controller: detach source, drop subscribers. */
    dispose(): void {
      disposed = true;
      attached = false;
      subscribers.clear();
    },
  };
}

export type RunController = ReturnType<typeof createRunController>;
