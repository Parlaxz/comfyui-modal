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
// failed | canceled. There is no transition engine — callers own their
// lifecycle and simply report it via start/patch/finish/fail/cancel.

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
  status?: OperationStatus;
  progress?: number;
  message?: string;
  workspaceId?: string;
}

export type PatchOperationInput = Partial<
  Pick<OperationRecord, "kind" | "label" | "status" | "progress" | "message" | "workspaceId">
>;

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
    byId.value.set(id, {
      id,
      kind: input.kind,
      label: input.label,
      status: input.status ?? "running",
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
    byId.value.set(id, { ...existing, ...input });
  }

  function settle(id: string, status: OperationStatus, message?: string): void {
    const existing = byId.value.get(id);
    if (!existing) return;
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
