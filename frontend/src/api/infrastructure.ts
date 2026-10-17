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
export async function updateModelRecord(modelId: string, body: Record<string, unknown>) { return requestJson<Record<string, unknown>>(`/studio/models/${encodeURIComponent(modelId)}`, { method: "PATCH", body }); }
export async function refreshCustomNodes() { return requestJson<InventoryEnvelope>("/studio/custom-nodes/refresh", { method: "POST" }); }
export async function upsertWorkspace(payload: Record<string, unknown>) { return requestJson<WorkspaceEnvelope>("/workspaces", { method: "POST", body: payload }); }
export async function requestWorkspaceSwap(payload: Record<string, unknown>) { return requestJson<Record<string, unknown>>("/workspaces/swap", { method: "POST", body: payload }); }
export async function getWorkspaceSwapStatus(swapId: string) { return requestJson<Record<string, unknown>>(`/workspaces/swap/${encodeURIComponent(swapId)}`); }
export function buildSwapConfirmPayload(workspaceId: string, selectedKeys: string[]) { return { workspace_id: workspaceId, confirm: true, selected_keys: selectedKeys.slice() }; }
export function swapPhaseMessage(data: Record<string, unknown> | null | undefined): string {
  const phase = String((data && data.phase) || "");
  if (phase === "downloading_models") {
    const msg = String((data && data.download_message) || "");
    const done = Number((data && data.download_completed) || 0);
    const total = Number((data && data.download_total) || 0) + Number((data && data.download_skipped) || 0);
    return msg || `Preparing downloads… ${done}/${total}`;
  }
  if (phase === "syncing_custom_nodes") return String((data && data.sync_message) || "Syncing custom nodes to Modal…");
  if (phase === "deploying") return String((data && data.deploy_message) || "Deploying workspace…");
  return phase ? `Phase: ${phase.replace(/_/g, " ")}` : "";
}
export async function getCustomNodeSyncStatus() { return requestJson<Record<string, unknown>>("/studio/custom-nodes/sync-status"); }
export async function triggerPushPlugins() { return requestJson<Record<string, unknown>>("/studio/custom-nodes/sync", { method: "POST" }); }
export async function triggerRebuildDependencies() { return requestJson<Record<string, unknown>>("/studio/custom-nodes/sync/rebuild-dependencies", { method: "POST" }); }
export async function getCustomNodeSyncOperationStatus(syncId: string) { return requestJson<Record<string, unknown>>(`/studio/custom-nodes/sync/status/${encodeURIComponent(syncId)}`); }
export async function installSingleModel(item: Record<string, unknown>) { return requestJson<Record<string, unknown>>("/model/install", { method: "POST", body: item }); }
/** Pure: infer a model filename from a pasted download URL (mirrors the legacy helper). */
export function inferModelFilename(url: string): string {
  const clean = String(url || "").split("?")[0].split("#")[0];
  const segment = clean.split("/").filter(Boolean).pop() || "";
  try {
    return decodeURIComponent(segment);
  } catch {
    return segment;
  }
}
export async function modelDownloadStatus(downloadId: string) { return requestJson<Record<string, unknown>>(`/download/status/${encodeURIComponent(downloadId || "")}`); }
export async function requestModelInstall(body: Record<string, unknown>) { return requestJson<Record<string, unknown>>("/studio/models/install-request", { method: "POST", body }); }
export async function requestCustomNodeInstall(body: Record<string, unknown>) { return requestJson<Record<string, unknown>>("/studio/custom-nodes/install-request", { method: "POST", body }); }
export async function scanManifestIssues() { return requestJson<Record<string, unknown>>("/manifest/repair/scan", { method: "POST" }); }
export async function applyManifestRepairs(updates: unknown) { return requestJson<Record<string, unknown>>("/manifest/repair/apply", { method: "POST", body: { updates } }); }
export async function deleteManifestPlaceholder(folder: string, filename: string) { return requestJson<Record<string, unknown>>("/manifest/repair/delete-placeholder", { method: "POST", body: { folder, filename } }); }
export async function getAuthStatus() { return requestJson<Record<string, unknown>>("/auth/status"); }
export async function getCredentialStatus(kind: "hf" | "civitai") { return requestJson<Record<string, unknown>>(kind === "civitai" ? "/civitai-token" : "/hf-token"); }
export async function saveCredentialToken(kind: "hf" | "civitai", token: string) { return requestJson<Record<string, unknown>>(kind === "civitai" ? "/civitai-token" : "/hf-token", { method: "POST", body: { token } }); }
export function credentialConfigured(data: unknown): boolean { return !!(data && typeof data === "object" && typeof (data as Record<string, unknown>).token === "string" && (data as Record<string, unknown>).token !== ""); }
export async function getRuntimeHealth() { return requestJson<Record<string, unknown>>("/health?mode=deploy"); }
