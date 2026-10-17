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
export async function createWorkflow(body: Record<string, unknown>) { return requestJson<unknown>("/studio/workflows", { method: "POST", body }); }
export async function importWorkflow(body: Record<string, unknown>) { return requestJson<unknown>("/studio/workflows/import", { method: "POST", body }); }
export async function deleteWorkflow(id: string) { return requestJson<unknown>(`/studio/workflows/${encodeURIComponent(id)}`, { method: "DELETE" }); }
export async function createWorkflowFolder(path: string) { return requestJson<unknown>("/studio/workflows/folders", { method: "POST", body: { path } }); }
export async function captureWorkflowVersion(workflowId: string, capture: Record<string, unknown>) { return requestJson<unknown>(`/studio/workflows/${encodeURIComponent(workflowId)}/versions`, { method: "POST", body: capture }); }
export async function getVersionState(id: string) { return requestJson<unknown>(`/studio/workflows/versions/${encodeURIComponent(id)}/state`); }
export async function createMapping(versionId: string, body: Record<string, unknown>) { return requestJson<unknown>(`/studio/workflows/versions/${encodeURIComponent(versionId)}/mapping`, { method: "POST", body }); }
export async function createMappingRevision(versionId: string, body: Record<string, unknown>) { return requestJson<unknown>(`/studio/workflows/versions/${encodeURIComponent(versionId)}/mapping/revision`, { method: "POST", body }); }
export async function setNonessentialDependencies(workflowId: string, keys: string[]) { return requestJson<unknown>(`/studio/workflows/${encodeURIComponent(workflowId)}/dependencies/nonessential`, { method: "POST", body: { keys } }); }
export async function updateCompatibility(versionId: string, body: Record<string, unknown>) { return requestJson<unknown>(`/studio/workflows/versions/${encodeURIComponent(versionId)}/compatibility`, { method: "PATCH", body }); }
export async function getMethodCompat(workflowId: string, versionId: string) { return requestJson<unknown>(`/studio/method-compat?workflow_id=${encodeURIComponent(workflowId)}&version_id=${encodeURIComponent(versionId)}`); }
export async function listVersionPresets(versionId: string) { return requestJson<{ status: string; presets?: unknown[] }>(`/studio/workflows/versions/${encodeURIComponent(versionId)}/presets`); }
export async function createVersionPreset(versionId: string, body: Record<string, unknown>) { return requestJson<unknown>(`/studio/workflows/versions/${encodeURIComponent(versionId)}/presets`, { method: "POST", body }); }
export async function updatePreset(presetId: string, body: Record<string, unknown>) { return requestJson<unknown>(`/studio/workflows/presets/${encodeURIComponent(presetId)}`, { method: "PATCH", body }); }
export async function deletePreset(presetId: string) { return requestJson<unknown>(`/studio/workflows/presets/${encodeURIComponent(presetId)}`, { method: "DELETE" }); }
export async function duplicatePreset(presetId: string, body: Record<string, unknown> = {}) { return requestJson<unknown>(`/studio/workflows/presets/${encodeURIComponent(presetId)}/duplicate`, { method: "POST", body }); }
export async function copyPresetToVersion(presetId: string, workflowVersionId: string) { return requestJson<unknown>(`/studio/workflows/presets/${encodeURIComponent(presetId)}/copy-to-version`, { method: "POST", body: { workflow_version_id: workflowVersionId } }); }
export async function getGuidanceMapping(modelSha256: string, mode: string) { return requestJson<unknown>(`/studio/guidance-mappings?model_sha256=${encodeURIComponent(modelSha256)}&mode=${encodeURIComponent(mode)}`); }
export async function saveGuidanceMapping(record: Record<string, unknown>) { return requestJson<unknown>("/studio/guidance-mappings", { method: "POST", body: { mapping: record } }); }
export async function deleteGuidanceMapping(modelSha256: string, mode: string) { return requestJson<unknown>(`/studio/guidance-mappings?model_sha256=${encodeURIComponent(modelSha256)}&mode=${encodeURIComponent(mode)}`, { method: "DELETE" }); }
export async function fetchWorkflowManifestExport(versionId: string): Promise<{ ok: boolean; blob?: Blob; filename?: string; message?: string }> {
  const response = await fetch(`/comfymodal/studio/workflows/versions/${encodeURIComponent(versionId)}/export`);
  if (!response.ok) return { ok: false, message: `Export failed with status ${response.status}` };
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = /filename="?([^";]+)"?/.exec(disposition);
  return { ok: true, blob, filename: match ? match[1].trim() : "manifest.json" };
}
export async function importWorkflowManifest(body: unknown, dryRun = true) {
  return requestJson<unknown>(`/studio/workflows/import-manifest?dry_run=${dryRun ? "1" : "0"}`, { method: "POST", body: body as Record<string, unknown> });
}

export function normalizeWorkflowType(value: unknown): string {
  const type = String(value || "t2i").toLowerCase();
  return type === "txt2img" ? "t2i" : type;
}

export const WIZARD_STEPS = ["feature-type", "required-bindings", "exposed-controls", "details"] as const;
export type WizardStep = (typeof WIZARD_STEPS)[number];

// ── Semantic binding roles (code-owned catalog) ─────────────────────
// Port of web/studio-bindable-inputs.js role sets + the static
// ROLE_SUGGESTIONS hints from web/studio-workflow-setup-wizard.js: the finite
// vocabulary a workflow field can map to. The workflow type decides which
// roles are required/optional; the output binding is always required.
export interface WizardRoleDef {
  key: string;
  label: string;
  /** Static "look for" hint shown on unbound rows (node type → widget). */
  hint: string;
}

const WIZARD_ROLE_DEFS: Record<string, WizardRoleDef> = {
  prompt: { key: "prompt", label: "Prompt", hint: "CLIPTextEncode · text" },
  seed: { key: "seed", label: "Seed", hint: "KSampler · seed" },
  step_count: { key: "step_count", label: "Step count", hint: "KSampler · steps" },
  cfg_scale: { key: "cfg_scale", label: "CFG scale", hint: "KSampler · cfg" },
  sampler: { key: "sampler", label: "Sampler", hint: "KSampler · sampler_name" },
  width: { key: "width", label: "Width", hint: "EmptyLatentImage · width" },
  height: { key: "height", label: "Height", hint: "EmptyLatentImage · height" },
  model_unet: { key: "model_unet", label: "Model", hint: "UNETLoader · unet_name" },
  vae: { key: "vae", label: "VAE", hint: "VAELoader · vae_name" },
  clip: { key: "clip", label: "CLIP", hint: "CLIPLoader · clip_name" },
  source_image: { key: "source_image", label: "Source image", hint: "LoadImage · image" },
  mask: { key: "mask", label: "Mask", hint: "Bind the exact input this workflow reads" },
  output: { key: "output", label: "Output", hint: "SaveImage · images" },
};

const WIZARD_REQUIRED_ROLES: Record<string, string[]> = {
  t2i: ["prompt", "seed", "model_unet", "vae", "clip"],
  i2i: ["prompt", "seed", "model_unet", "vae", "clip", "source_image"],
  inpaint: ["prompt", "seed", "model_unet", "vae", "clip", "source_image", "mask"],
  sketch: ["prompt", "seed", "model_unet", "vae", "clip", "source_image"],
  outpaint: ["prompt", "seed", "model_unet", "vae", "clip", "source_image"],
};

const WIZARD_OPTIONAL_ROLES: Record<string, string[]> = {
  t2i: ["step_count", "cfg_scale", "sampler", "width", "height"],
  i2i: ["step_count", "cfg_scale", "sampler", "width", "height", "mask"],
  inpaint: ["step_count", "cfg_scale", "sampler", "width", "height"],
  sketch: ["step_count", "cfg_scale", "sampler", "width", "height", "mask"],
  outpaint: ["step_count", "cfg_scale", "sampler", "width", "height", "mask"],
};

export function wizardRoleDef(key: string): WizardRoleDef {
  return WIZARD_ROLE_DEFS[key] ?? { key, label: key, hint: "" };
}

export function requiredWizardRoles(featureType: string): string[] {
  return WIZARD_REQUIRED_ROLES[normalizeWorkflowType(featureType)] ?? WIZARD_REQUIRED_ROLES.t2i;
}

export function optionalWizardRoles(featureType: string): string[] {
  return WIZARD_OPTIONAL_ROLES[normalizeWorkflowType(featureType)] ?? WIZARD_OPTIONAL_ROLES.t2i;
}

// Static per-role "look for" patterns for graph-backed suggestions (port of
// the legacy ROLE_SUGGESTIONS map). Proposals only — binding always requires
// an explicit graph click.
const WIZARD_ROLE_SUGGESTIONS: Record<string, Array<{ nodeType: string; widget?: string }>> = {
  prompt: [{ nodeType: "CLIPTextEncode", widget: "text" }],
  seed: [{ nodeType: "KSampler", widget: "seed" }],
  step_count: [{ nodeType: "KSampler", widget: "steps" }],
  cfg_scale: [{ nodeType: "KSampler", widget: "cfg" }],
  sampler: [{ nodeType: "KSampler", widget: "sampler_name" }],
  width: [{ nodeType: "EmptyLatentImage", widget: "width" }],
  height: [{ nodeType: "EmptyLatentImage", widget: "height" }],
  model_unet: [{ nodeType: "UNETLoader", widget: "unet_name" }, { nodeType: "CheckpointLoaderSimple", widget: "ckpt_name" }],
  vae: [{ nodeType: "VAELoader", widget: "vae_name" }, { nodeType: "CheckpointLoaderSimple", widget: "ckpt_name" }],
  clip: [{ nodeType: "CLIPLoader", widget: "clip_name" }, { nodeType: "CheckpointLoaderSimple", widget: "ckpt_name" }],
  source_image: [{ nodeType: "LoadImage", widget: "image" }],
  mask: [],
  output: [{ nodeType: "SaveImage" }, { nodeType: "PreviewImage" }],
};

export function wizardRoleSuggestions(roleKey: string): Array<{ nodeType: string; widget?: string }> {
  return WIZARD_ROLE_SUGGESTIONS[roleKey] ?? [];
}

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
