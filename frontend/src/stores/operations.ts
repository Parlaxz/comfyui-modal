// Modal Studio Vue substrate — operation registry (presentation authority).
//
// operationStore is a REGISTRY, not an execution engine. Long-running
// visible work (future: deployment, download, generation, sync, reboot)
// publishes a small presentation summary here so any surface can render
// one consistent status. It never decides domain semantics:
//
//   operationStore = WHAT is visibly happening?
//   domain store   = WHAT does it mean?
//   API            = HOW do we talk to the backend?
//   async utility  = HOW do we safely wait/read?
//
// If you are introducing long-running visible work, look here first —
// but keep execution where it belongs:
//
// - Playground run correctness stays in the canonical run controller
//   (web/studio-playground-run.js + web/studio-run-model.js +
//   web/studio-run-adapters.js). That controller owns identity, event
//   adaptation, and terminal semantics. It may one day project a
//   presentation summary into this registry; the registry does not own,
//   drive, or second-guess runs. It never decides whether generation is
//   terminal, how websocket run identity works, what deploy status means,
//   whether reboot disconnect is expected, or what retry means.
// - Do NOT make every tiny request an operation.
// - Do NOT move domain-specific state into the registry.
// - Do NOT persist operation state (it is transient by design).
//
// Statuses are intentionally small: pending | running | completed |
// failed | canceled. There is no transition engine — but there IS one
// canonical path into terminal state: finish() → completed, fail() →
// failed, cancel() → canceled. start() creates active operations only and
// patch() moves between active states only; neither accepts a terminal
// status (enforced by ActiveOperationStatus, backed by a runtime guard).

import { defineStore } from "pinia";
import { computed, ref } from "vue";

export type OperationKind =
  | "generation"
  | "experiment"
  | "deploy"
  | "workspace-swap"
  | "model-download"
  | "node-sync"
  | "inventory-sync"
  | "workflow-import"
  | "other";

export type OperationStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "canceled";

/**
 * The only statuses an operation may carry while active. Terminal statuses
 * have exactly one canonical path each — finish()/fail()/cancel() — so
 * they are not expressible here. Enforced primarily by TypeScript; the
 * patch() runtime guard below backs it for plain-JS callers.
 */
export type ActiveOperationStatus = "pending" | "running";

export interface OperationRecord {
  id: string;
  kind: OperationKind;
  label: string;
  status: OperationStatus;
  progress?: number;
  message?: string;
  startedAt: number;
  finishedAt?: number;
  workspaceId?: string;
}

export interface StartOperationInput {
  kind: OperationKind;
  label: string;
  status?: ActiveOperationStatus;
  progress?: number;
  message?: string;
  workspaceId?: string;
}

export interface PatchOperationInput {
  kind?: OperationKind;
  label?: string;
  status?: ActiveOperationStatus;
  progress?: number;
  message?: string;
  workspaceId?: string;
}

// Terminal statuses are final: completed | failed | canceled.
// This is a single freeze guard, not a transition engine. It preserves one
// invariant the whole UI can rely on:
//
//   terminal status ⟺ finishedAt is set, and neither ever changes again.
//
// Without it, a late poll/fail call could regress a finished operation
// (failed → completed). First terminal wins; presentation fields
// (message/progress) may still be patched afterwards, e.g. a deploy tail
// arriving after the terminal poll. Status itself can only enter terminal
// through finish()/fail()/cancel().
const TERMINAL_STATUSES: ReadonlySet<OperationStatus> = new Set([
  "completed",
  "failed",
  "canceled",
]);

function isTerminal(status: OperationStatus): boolean {
  return TERMINAL_STATUSES.has(status);
}

let nextId = 0;

function newId(): string {
  nextId += 1;
  if (
    typeof crypto !== "undefined" &&
    typeof crypto.randomUUID === "function"
  ) {
    return `op_${crypto.randomUUID()}`;
  }
  return `op_${Date.now().toString(36)}_${nextId}`;
}

export const useOperationsStore = defineStore("studio-operations", () => {
  const byId = ref(new Map<string, OperationRecord>());

  const all = computed(() => [...byId.value.values()]);
  const active = computed(() =>
    all.value.filter((op) => op.status === "pending" || op.status === "running"),
  );

  function get(id: string): OperationRecord | undefined {
    return byId.value.get(id);
  }

  function start(input: StartOperationInput): string {
    const now = Date.now();
    const id = newId();
    const status: ActiveOperationStatus =
      input.status === "pending" ? "pending" : "running";
    byId.value.set(id, {
      id,
      kind: input.kind,
      label: input.label,
      status,
      progress: input.progress,
      message: input.message,
      startedAt: now,
      finishedAt: undefined,
      workspaceId: input.workspaceId,
    });
    return id;
  }

  function patch(id: string, input: PatchOperationInput): void {
    const existing = byId.value.get(id);
    if (!existing) return;
    const { status, ...rest } = input;
    const next = { ...existing, ...rest };
    // Status moves only between active states, and never out of terminal:
    // terminal entry has one canonical path each (finish/fail/cancel), so
    // a terminal value here is dropped, not applied. (The type system
    // forbids it at compile time; this guards plain-JS callers.)
    if (!isTerminal(existing.status) && status !== undefined && !isTerminal(status)) {
      next.status = status;
    }
    byId.value.set(id, next);
  }

  function settle(id: string, status: OperationStatus, message?: string): void {
    const existing = byId.value.get(id);
    // Unknown ids and already-terminal records are no-ops: first terminal
    // wins, so late duplicate polls cannot regress finished work.
    if (!existing || isTerminal(existing.status)) return;
    byId.value.set(id, {
      ...existing,
      status,
      message: message === undefined ? existing.message : message,
      finishedAt: Date.now(),
    });
  }

  function finish(id: string, message?: string): void {
    settle(id, "completed", message);
  }

  function fail(id: string, message?: string): void {
    settle(id, "failed", message);
  }

  function cancel(id: string, message?: string): void {
    settle(id, "canceled", message);
  }

  function remove(id: string): void {
    byId.value.delete(id);
  }

  function clear(): void {
    byId.value.clear();
  }

  return {
    byId,
    all,
    active,
    get,
    start,
    patch,
    finish,
    fail,
    cancel,
    remove,
    clear,
  };
});
