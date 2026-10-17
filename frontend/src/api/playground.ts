// Modal Studio Vue — Playground API glue (Phase 5).
//
// Thin endpoint wrappers at the existing API boundary. No new backend,
// no new execution semantics: the run controller contracts live in
// web/studio-playground-run.js + web/studio-run-model.js +
// web/studio-run-adapters.js and are consumed here as plain HTTP.
//
// Endpoints (proven by web/studio-backend-api.js):
//   GET  /studio/workflows/:id/run-context  (control schema + version state)
//   POST /studio/run                         (single generation)
//   POST /studio/run_batch                   (queue drain, variants chunk)
//   POST /studio/experiment-v2               (experiment definition)
//   POST /studio/experiments/:id/stop-now    (cancel, legacy stop path)
//   POST /studio/uploads                     (source/reference image upload)
import { requestJson } from "./http";

export interface RunContextEnvelope {
  status: string;
  workflow?: Record<string, unknown>;
  version?: Record<string, unknown>;
  state?: Record<string, unknown>;
  mapping?: unknown;
  control_schema?: Record<string, ControlSchemaEntry>;
  [key: string]: unknown;
}

export interface ControlSchemaEntry {
  node_id?: string | number;
  input_name?: string;
  label?: string;
  group?: string;
  control_kind?: string;
  data_type?: string;
  required?: boolean;
  enabled?: boolean;
  default?: unknown;
  minimum?: number;
  maximum?: number;
  step?: number;
  enum_options?: unknown[];
  [key: string]: unknown;
}

export interface RunPayload {
  workflow_id: string;
  workflow_version_id: string;
  featureId: string;
  workflow_type: string;
  controls: Record<string, unknown>;
  modal_options?: Record<string, unknown>;
  studio_method?: unknown;
  studio_references?: unknown;
  guidance?: unknown;
  studio_style?: unknown;
  profile_name?: string | null;
  request_id?: string;
  metadata?: Record<string, unknown>;
  trace?: Record<string, unknown>;
}

export interface BatchVariant {
  request_id: string;
  controls: Record<string, unknown>;
}

export interface BatchPayload {
  profile: string | null;
  workflow_id: string;
  workflow_version_id: string;
  request_id: string;
  modal_options?: Record<string, unknown> | null;
  variants: BatchVariant[];
}

export async function getRunContext(
  workflowId: string,
  versionId = "",
  fetchImpl?: typeof fetch,
) {
  let path = `/studio/workflows/${encodeURIComponent(workflowId)}/run-context`;
  if (versionId) path += `?version_id=${encodeURIComponent(versionId)}`;
  return requestJson<RunContextEnvelope>(path, {}, fetchImpl);
}

export async function submitRun(payload: RunPayload, fetchImpl?: typeof fetch) {
  return requestJson<Record<string, unknown>>("/studio/run", { method: "POST", body: payload }, fetchImpl);
}

export async function submitBatch(payload: BatchPayload, fetchImpl?: typeof fetch) {
  return requestJson<Record<string, unknown>>("/studio/run_batch", { method: "POST", body: payload }, fetchImpl);
}

export async function submitExperiment(
  payload: Record<string, unknown>,
  fetchImpl?: typeof fetch,
) {
  return requestJson<Record<string, unknown>>(
    "/studio/experiment-v2",
    { method: "POST", body: payload },
    fetchImpl,
  );
}

export async function stopRun(id: string, fetchImpl?: typeof fetch) {
  return requestJson<Record<string, unknown>>(
    `/studio/experiments/${encodeURIComponent(id)}/stop-now`,
    { method: "POST", body: {} },
    fetchImpl,
  );
}

/** Image upload uses ComfyUI's native upload transport (never JSON-flattened).
 * Mirrors web/studio-field-blocks.js uploadImageBlob: FormData with the
 * file plus overwrite=false, filename resolved from the response. */
export async function uploadPlaygroundImage(
  file: File,
  fetchImpl: typeof fetch = fetch,
): Promise<{ ok: boolean; filename?: string; message?: string }> {
  const form = new FormData();
  form.append("image", file, file.name || "studio-image.png");
  form.append("overwrite", "false");
  let response: Response;
  try {
    response = await fetchImpl("/upload/image", { method: "POST", body: form });
  } catch {
    return { ok: false, message: "Image upload request failed" };
  }
  if (!response.ok) return { ok: false, message: `Upload failed with status ${response.status}` };
  try {
    const payload = (await response.json()) as Record<string, unknown>;
    const files = payload.files;
    const filename =
      typeof payload.name === "string"
        ? payload.name
        : Array.isArray(files) && typeof files[0] === "string"
          ? files[0]
          : undefined;
    if (!filename) return { ok: false, message: "Upload returned no filename" };
    return { ok: true, filename };
  } catch {
    return { ok: false, message: "Upload returned an unreadable response" };
  }
}

export function newRequestId(prefix: string): string {
  try {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID();
    }
  } catch {
    /* fall through to Math-based id */
  }
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}
