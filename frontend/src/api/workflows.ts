import { requestJson } from "./http";

export interface WorkflowSummary { workflow_id: string; name: string; folder?: string; tags?: string[]; favorite?: boolean; latest_version_id?: string; [key: string]: unknown; }
export interface WorkflowVersion { workflow_version_id: string; workflow_id?: string; version?: number; state?: Record<string, unknown>; [key: string]: unknown; }
export interface WorkflowEnvelope { status: string; workflows?: WorkflowSummary[]; workflow?: WorkflowSummary; versions?: WorkflowVersion[]; [key: string]: unknown; }
export interface DependencyEnvelope { status: string; models?: unknown[]; custom_nodes?: unknown[]; summary?: unknown; [key: string]: unknown; }

function unwrap<T>(payload: T): T {
  if (!payload || typeof payload !== "object") return payload;
  const value = payload as Record<string, unknown>;
  if (Object.prototype.hasOwnProperty.call(value, "workflow")) return value.workflow as T;
  if (Object.prototype.hasOwnProperty.call(value, "version")) return value.version as T;
  if (Object.prototype.hasOwnProperty.call(value, "mapping")) return value.mapping as T;
  return payload;
}

export async function listWorkflows(params: { search?: string; tag?: string; folder?: string; favorite?: boolean } = {}) { const q = new URLSearchParams(); if (params.search) q.set("search", params.search); if (params.tag) q.set("tag", params.tag); if (params.folder) q.set("folder", params.folder); if (params.favorite) q.set("favorite", "1"); const suffix = q.toString() ? `?${q}` : ""; return requestJson<WorkflowEnvelope>(`/studio/workflows${suffix}`); }
export async function getWorkflow(id: string) { return requestJson<WorkflowEnvelope>(`/studio/workflows/${encodeURIComponent(id)}`).then((payload) => ({ ...payload, workflow: unwrap(payload) as unknown as WorkflowSummary })); }
export async function listVersions(id: string) { return requestJson<WorkflowEnvelope>(`/studio/workflows/${encodeURIComponent(id)}/versions`); }
export async function getVersion(id: string) { return requestJson<WorkflowEnvelope>(`/studio/workflows/versions/${encodeURIComponent(id)}`).then((payload) => unwrap(payload)); }
export async function getMapping(id: string) { return requestJson<unknown>(`/studio/workflows/versions/${encodeURIComponent(id)}/mapping`).then((payload) => unwrap(payload)); }
export async function getMappingCandidates(id: string) { return requestJson<unknown>(`/studio/workflows/versions/${encodeURIComponent(id)}/mapping/candidates`); }
export async function getDependencies(id: string) { return requestJson<DependencyEnvelope>(`/studio/workflows/versions/${encodeURIComponent(id)}/dependencies`); }
export async function getCompatibility(id: string) { return requestJson<unknown>(`/studio/workflows/versions/${encodeURIComponent(id)}/compatibility`); }
export async function getPortability(id: string) { return requestJson<unknown>(`/studio/workflows/versions/${encodeURIComponent(id)}/portability`); }
export async function listFolders() { return requestJson<unknown>("/studio/workflows/folders"); }
export async function listTags() { return requestJson<unknown>("/studio/workflows/tags"); }
export async function listPresets(versionId: string) { return requestJson<unknown>(`/studio/workflows/versions/${encodeURIComponent(versionId)}/presets`); }
export async function updateWorkflow(id: string, body: Record<string, unknown>) { return requestJson<unknown>(`/studio/workflows/${encodeURIComponent(id)}`, { method: "PATCH", body }); }
export async function createMappingRevision(versionId: string, body: Record<string, unknown>) { return requestJson<unknown>(`/studio/workflows/versions/${encodeURIComponent(versionId)}/mapping/revision`, { method: "POST", body }); }
export async function setNonessentialDependencies(workflowId: string, keys: string[]) { return requestJson<unknown>(`/studio/workflows/${encodeURIComponent(workflowId)}/dependencies/nonessential`, { method: "POST", body: { keys } }); }

export function normalizeWorkflowType(value: unknown): string {
  const type = String(value || "t2i").toLowerCase();
  return type === "txt2img" ? "t2i" : type;
}

export const WIZARD_STEPS = ["feature-type", "required-bindings", "exposed-controls", "details"] as const;
export type WizardStep = (typeof WIZARD_STEPS)[number];

export interface WizardDraft {
  v: 1;
  workflowId: string;
  versionId: string;
  step: WizardStep;
  featureType: string;
  bindings: Record<string, unknown>;
  outputBinding: Record<string, unknown> | null;
  controls: unknown[];
  details: Record<string, unknown>;
}

export function buildWizardDraft(input: Partial<WizardDraft>): WizardDraft {
  return {
    v: 1, workflowId: input.workflowId || "", versionId: input.versionId || "",
    step: input.step && WIZARD_STEPS.includes(input.step) ? input.step : "feature-type",
    featureType: input.featureType || "t2i", bindings: input.bindings || {},
    outputBinding: input.outputBinding || null, controls: Array.isArray(input.controls) ? input.controls.slice(0, 64) : [],
    details: input.details || {},
  };
}

export function parseWizardDraft(raw: string | null, workflowId: string, versionId: string): WizardDraft | null {
  if (!raw || raw.length > 12000) return null;
  try {
    const value = JSON.parse(raw) as Partial<WizardDraft>;
    if (value.v !== 1 || value.workflowId !== workflowId || value.versionId !== versionId) return null;
    return buildWizardDraft(value);
  } catch { return null; }
}
