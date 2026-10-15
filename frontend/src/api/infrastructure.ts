import { requestJson } from "./http";

export interface WorkspaceSummary { id: string; label: string; isActive: boolean; lastDeployStatus: string; lastUsedAt: string | null; }
export interface WorkspaceEnvelope { status: string; active_workspace_id?: string | null; workspaces?: Array<Record<string, unknown>>; [key: string]: unknown; }
export interface DeployStatus { state: string; message: string; details: string; hasLog: boolean; available: boolean; [key: string]: unknown; }
export interface InventoryEnvelope { status: string; models?: unknown[]; custom_nodes?: unknown[]; [key: string]: unknown; }

export function summarizeWorkspaces(envelope: WorkspaceEnvelope) {
  const activeId = envelope.active_workspace_id ?? null;
  const rows = (envelope.workspaces ?? []).map((workspace) => { const id = String(workspace.id ?? ""); return { id, label: String(workspace.label ?? id), isActive: id !== "" && id === activeId, lastDeployStatus: String(workspace.last_deploy_status ?? "idle"), lastUsedAt: typeof workspace.last_used_at === "string" ? workspace.last_used_at : null }; });
  return { activeId, rows };
}
export function normalizeDeployStatus(data: unknown): DeployStatus { if (!data || typeof data !== "object") return { state: "unknown", message: "", details: "", hasLog: false, available: false }; const value = data as Record<string, unknown>; return { state: String(value.state ?? "unknown"), message: String(value.message ?? ""), details: String(value.details ?? ""), hasLog: Boolean(value.has_log), available: true, ...value }; }
export function isDeployUsable(state: string): boolean { return state === "ready" || state === "deployed_unwarmed"; }
export async function listWorkspaces() { return requestJson<WorkspaceEnvelope>("/workspaces"); }
export async function activateWorkspace(workspaceId: string) { return requestJson<WorkspaceEnvelope>("/workspaces/active", { method: "POST", body: { workspace_id: workspaceId } }); }
export async function getDeployStatus() { return normalizeDeployStatus(await requestJson<unknown>("/deploy/status")); }
export async function triggerDeploy() { return requestJson<{ status: string }>("/deploy", { method: "POST" }); }
export async function getDeployLog() { return requestJson<unknown>("/deploy/log"); }
export async function refreshInventory(maxAge?: number) { const suffix = maxAge === undefined ? "" : `?max_age=${encodeURIComponent(String(maxAge))}`; return requestJson<{ status: string; available?: boolean }>(`/studio/inventory/refresh${suffix}`); }
export async function listModels(params: { search?: string; type?: string; state?: string } = {}) { const query = new URLSearchParams(); if (params.search) query.set("search", params.search); if (params.type) query.set("type", params.type); if (params.state) query.set("state", params.state); const suffix = query.toString() ? `?${query}` : ""; return requestJson<InventoryEnvelope>(`/studio/models${suffix}`); }
export async function rescanModels(forceRehash = false) { return requestJson<InventoryEnvelope>("/studio/models/rescan", { method: "POST", body: { force_rehash: forceRehash } }); }
export async function listCustomNodes() { return requestJson<InventoryEnvelope>("/studio/custom-nodes"); }
export async function refreshCustomNodes() { return requestJson<InventoryEnvelope>("/studio/custom-nodes/refresh", { method: "POST" }); }
export async function requestWorkspaceSwap(payload: Record<string, unknown>) { return requestJson<Record<string, unknown>>("/workspaces/swap", { method: "POST", body: payload }); }
export async function getWorkspaceSwapStatus(swapId: string) { return requestJson<Record<string, unknown>>(`/workspaces/swap/${encodeURIComponent(swapId)}`); }
