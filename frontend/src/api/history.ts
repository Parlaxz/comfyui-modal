import { requestJson } from "./http";

export interface HistoryOutput {
  index: number;
  outputId: string;
  assetId: string;
  logicalKey: string;
  thumbUrl: string;
  previewUrl: string;
  originalUrl: string;
  originalAvailable: boolean;
  width: number | null;
  height: number | null;
  filename: string;
}

export interface HistoryRecord {
  id: string;
  kind: "generation" | "experiment";
  status: string;
  workflow: string;
  workflowVersion: string;
  preset: string;
  prompt: string;
  startedAt: string | null;
  completedAt: string | null;
  durationMs: number | null;
  favorite: boolean;
  note: string;
  outputs: HistoryOutput[];
  featuredOutput: HistoryOutput | null;
  originalAvailable: boolean;
  replayCapable: boolean;
  raw: Record<string, unknown>;
}

export interface HistoryFeedResponse {
  status: string;
  items?: unknown[];
  records?: unknown[];
  next_cursor?: string | null;
  has_more?: boolean;
  [key: string]: unknown;
}

function unwrapItem(payload: unknown): unknown {
  if (!payload || typeof payload !== "object") return payload;
  const value = payload as Record<string, unknown>;
  return value.item ?? value.generation ?? value.experiment ?? payload;
}

function stringValue(record: Record<string, unknown>, ...keys: string[]): string {
  for (const key of keys) if (typeof record[key] === "string") return record[key] as string;
  return "";
}

function normalizeOutput(raw: unknown, index: number): HistoryOutput {
  const value = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  const assetId = stringValue(value, "asset_id", "assetId");
  const url = () => `/comfymodal/history-v2/assets/${encodeURIComponent(assetId)}`;
  return {
    index: typeof value.index === "number" ? value.index : index,
    outputId: stringValue(value, "output_id", "outputId"),
    assetId,
    logicalKey: stringValue(value, "logical_key", "logicalKey"),
    thumbUrl: stringValue(value, "thumb_url", "thumbnail_url") || url(),
    previewUrl: stringValue(value, "preview_url", "data_saver_url") || url(),
    originalUrl: stringValue(value, "original_url") || url(),
    originalAvailable: value.original_available !== false,
    width: typeof value.width === "number" ? value.width : null,
    height: typeof value.height === "number" ? value.height : null,
    filename: stringValue(value, "filename", "name"),
  };
}

export function normalizeHistoryRecord(raw: unknown): HistoryRecord {
  const value = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  const outputsRaw = Array.isArray(value.outputs) ? value.outputs : [];
  const outputs = outputsRaw.map((output, index) => normalizeOutput(output, index));
  return {
    id: stringValue(value, "id", "generation_id", "experiment_id", "run_id"),
    kind: value.kind === "experiment" || value.experiment_id ? "experiment" : "generation",
    status: stringValue(value, "status", "outcome") || "unknown",
    workflow: stringValue(value, "workflow", "workflow_name"),
    workflowVersion: stringValue(value, "workflow_version", "workflowVersion", "version_id"),
    preset: stringValue(value, "preset", "preset_name"),
    prompt: stringValue(value, "prompt", "positive_prompt"),
    startedAt: stringValue(value, "started_at", "created_at") || null,
    completedAt: stringValue(value, "completed_at", "finished_at") || null,
    durationMs: typeof value.duration_ms === "number" ? value.duration_ms : null,
    favorite: value.favorite === true,
    note: stringValue(value, "note"),
    outputs,
    featuredOutput: outputs[0] ?? null,
    originalAvailable: value.original_available !== false,
    replayCapable: value.replay_capable !== false,
    raw: value,
  };
}

export async function getHistoryFeed(params: Record<string, string | number | boolean | undefined> = {}) {
  const query = new URLSearchParams();
  const wireParams: Record<string, string | number | boolean | undefined> = { limit: 24, ...params };
  if (wireParams.sort !== undefined) {
    wireParams.order = wireParams.sort;
    delete wireParams.sort;
  }
  if (wireParams.favorite_only !== undefined) {
    wireParams.favorite = wireParams.favorite_only;
    delete wireParams.favorite_only;
  }
  for (const [key, value] of Object.entries(wireParams)) {
    if (value !== undefined && String(value) !== "") query.set(key, String(value));
  }
  return requestJson<HistoryFeedResponse>(`/history-v2/feed?${query}`);
}

export async function getGeneration(id: string) {
  return requestJson<unknown>(`/history-v2/generations/${encodeURIComponent(id)}`).then(unwrapItem);
}

export async function getExperiment(id: string) {
  return requestJson<unknown>(`/history-v2/experiments/${encodeURIComponent(id)}`).then(unwrapItem);
}

export async function setGenerationFavorite(id: string, favorite: boolean) {
  return requestJson<unknown>(`/history-v2/generations/${encodeURIComponent(id)}/favorite`, { method: "PATCH", body: { favorite } });
}

export async function setGenerationNote(id: string, note: string) {
  return requestJson<unknown>(`/history-v2/generations/${encodeURIComponent(id)}/note`, { method: "PATCH", body: { note } });
}

export async function deleteHistoryRecord(record: HistoryRecord) {
  const path = record.kind === "experiment" ? "experiments" : "generations";
  return requestJson<unknown>(`/history-v2/${path}/${encodeURIComponent(record.id)}`, { method: "DELETE" });
}
