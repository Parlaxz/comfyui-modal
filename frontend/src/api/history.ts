import { requestJson } from "./http";

export interface HistoryOutput {
  index: number;
  outputId: string;
  assetId: string;
  logicalKey: string;
  thumbUrl: string;
  previewUrl: string;
  dataSaverUrl: string;
  originalUrl: string;
  originalAvailable: boolean;
  width: number | null;
  height: number | null;
  filename: string;
  exportState: string;
}

export interface HistoryAttempt {
  index: number;
  status: string;
  error: string | null;
  [key: string]: unknown;
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
  featuredOutputIndex: number;
  originalAvailable: boolean;
  replayCapable: boolean;
  replayReason: string;
  attempts: HistoryAttempt[];
  errors: Array<{ code: string; message: string }>;
  params: Record<string, unknown>;
  timing: Record<string, unknown>;
  cells: HistoryRecord[];
  cover: Array<HistoryRecord | null>;
  axisLabels: { x: string; y: string };
  counts: { cells: number; results: number; failed: number; interrupted: number };
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
    dataSaverUrl: stringValue(value, "data_saver_url", "preview_url") || url(),
    originalUrl: stringValue(value, "original_url") || url(),
    originalAvailable: value.original_available !== false,
    width: typeof value.width === "number" ? value.width : null,
    height: typeof value.height === "number" ? value.height : null,
    filename: stringValue(value, "filename", "name"),
    exportState: stringValue(value, "export_state", "exportState") || "not_exported",
  };
}

function normalizeAttempt(raw: unknown, index: number): HistoryAttempt {
  const value = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  return {
    index,
    status: stringValue(value, "status", "outcome") || "unknown",
    error: stringValue(value, "error", "message") || null,
    ...value,
  };
}

/** Feed policy: Data Saver → thumbnail; detail/compare/download choose explicitly. */
export function selectFeedAsset(output: HistoryOutput): string {
  return output.dataSaverUrl || output.thumbUrl || output.originalUrl;
}

/** Detail policy: Data Saver → Original (when available) → thumbnail. */
export function selectDetailAsset(output: HistoryOutput): string {
  if (output.originalAvailable && output.originalUrl) return output.originalUrl;
  return output.dataSaverUrl || output.originalUrl || output.thumbUrl;
}

/** Compare policy: Original → Data Saver → thumbnail. */
export function selectCompareAsset(output: HistoryOutput): string {
  return output.originalUrl || output.dataSaverUrl || output.thumbUrl;
}

export function featuredIndexOf(raw: Record<string, unknown>, outputs: HistoryOutput[]): number {
  const direct = raw.featured_output_index;
  if (typeof direct === "number" && outputs[direct]) return direct;
  const nested = raw.featured_output;
  if (nested && typeof nested === "object") {
    const index = (nested as Record<string, unknown>).index;
    if (typeof index === "number" && outputs[index]) return index;
  }
  return 0;
}

export function normalizeHistoryRecord(raw: unknown): HistoryRecord {
  const value = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  const outputsRaw = Array.isArray(value.outputs) ? value.outputs : [];
  const outputs = outputsRaw.map((output, index) => normalizeOutput(output, index));
  const featuredIndex = featuredIndexOf(value, outputs);
  const cellsRaw = Array.isArray(value.cells) ? value.cells : [];
  const coverRaw = Array.isArray(value.cover) ? value.cover : [];
  const attemptsRaw = Array.isArray(value.attempts) ? value.attempts : [];
  const errorsRaw = Array.isArray(value.errors) ? value.errors : [];
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
    featuredOutput: outputs[featuredIndex] ?? outputs[0] ?? null,
    featuredOutputIndex: featuredIndex,
    originalAvailable: value.original_available !== false,
    replayCapable: value.replay_capable !== false,
    replayReason: stringValue(value, "replay_reason", "replayReason"),
    attempts: attemptsRaw.map((attempt, index) => normalizeAttempt(attempt, index)),
    errors: errorsRaw
      .filter((entry): entry is Record<string, unknown> => !!entry && typeof entry === "object")
      .map((entry) => ({ code: stringValue(entry, "code") || "error", message: stringValue(entry, "message") || "Unknown error" })),
    params: (value.params && typeof value.params === "object" ? value.params : {}) as Record<string, unknown>,
    timing: (value.timing && typeof value.timing === "object" ? value.timing : {}) as Record<string, unknown>,
    cells: cellsRaw.map((cell) => normalizeHistoryRecord(cell)),
    cover: coverRaw.map((cell) => (cell ? normalizeHistoryRecord(cell) : null)),
    axisLabels: {
      x: stringValue((value.axis_labels && typeof value.axis_labels === "object" ? value.axis_labels : {}) as Record<string, unknown>, "x"),
      y: stringValue((value.axis_labels && typeof value.axis_labels === "object" ? value.axis_labels : {}) as Record<string, unknown>, "y"),
    },
    counts: {
      cells: typeof value.true_cell_count === "number" ? value.true_cell_count : cellsRaw.length,
      results: typeof value.result_count === "number" ? value.result_count : 0,
      failed: typeof value.failed_count === "number" ? value.failed_count : 0,
      interrupted: typeof value.interrupted_count === "number" ? value.interrupted_count : 0,
    },
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

export async function setExperimentFavorite(id: string, favorite: boolean) {
  return requestJson<unknown>(`/history-v2/experiments/${encodeURIComponent(id)}/favorite`, { method: "PATCH", body: { favorite } });
}

export async function setGenerationNote(id: string, note: string) {
  return requestJson<unknown>(`/history-v2/generations/${encodeURIComponent(id)}/note`, { method: "PATCH", body: { note } });
}

export async function setExperimentNote(id: string, note: string) {
  return requestJson<unknown>(`/history-v2/experiments/${encodeURIComponent(id)}/note`, { method: "PATCH", body: { note } });
}

export async function setFeaturedOutput(id: string, outputIndex: number) {
  return requestJson<unknown>(`/history-v2/generations/${encodeURIComponent(id)}/featured`, { method: "PATCH", body: { output_index: outputIndex } });
}

export async function generateOriginal(id: string, opts: Record<string, unknown> = {}) {
  return requestJson<unknown>(`/history-v2/generations/${encodeURIComponent(id)}/original`, { method: "POST", body: opts });
}

export async function retryOriginal(id: string) {
  return requestJson<unknown>(`/history-v2/generations/${encodeURIComponent(id)}/original/retry`, { method: "POST" });
}

export async function resumeGeneration(id: string) {
  return requestJson<unknown>(`/history-v2/generations/${encodeURIComponent(id)}/resume`, { method: "POST" });
}

export async function resumeExperiment(id: string) {
  return requestJson<unknown>(`/history-v2/experiments/${encodeURIComponent(id)}/resume`, { method: "POST" });
}

export async function cancelExperiment(id: string) {
  return requestJson<unknown>(`/history-v2/experiments/${encodeURIComponent(id)}/cancel`, { method: "POST" });
}

export async function retryExperimentCell(experimentId: string, cellId: string) {
  return requestJson<unknown>(`/history-v2/experiments/${encodeURIComponent(experimentId)}/cells/${encodeURIComponent(cellId)}/retry`, { method: "POST" });
}

export async function bulkDeleteHistory(generationIds: string[], experimentIds: string[]) {
  return requestJson<unknown>("/history-v2/bulk-delete", { method: "POST", body: { generation_ids: generationIds, experiment_ids: experimentIds } });
}

export async function exportHistoryAsset(assetId: string) {
  return requestJson<unknown>(`/history-v2/assets/${encodeURIComponent(assetId)}/export`, { method: "POST" });
}

export async function openHistoryAsset(assetId: string) {
  return requestJson<unknown>(`/history-v2/assets/${encodeURIComponent(assetId)}/open`, { method: "POST" });
}

export async function revealHistoryAsset(assetId: string) {
  return requestJson<unknown>(`/history-v2/assets/${encodeURIComponent(assetId)}/reveal`, { method: "POST" });
}

/** Explicit single-asset browser download: exactly one GET, blob MIME decides the extension. */
export function mimeToExtension(mime: string): string {
  const normalized = mime.split(";")[0].trim().toLowerCase();
  if (normalized === "image/png") return "png";
  if (normalized === "image/jpeg") return "jpg";
  if (normalized === "image/webp") return "webp";
  if (normalized === "image/gif") return "gif";
  if (normalized === "image/bmp") return "bmp";
  return "png";
}

export function historyDownloadFilename(record: HistoryRecord, output: HistoryOutput, extension: string): string {
  const stem = [record.workflow || "generation", record.id, `output-${output.index}`]
    .map((part) => part.replace(/[^a-zA-Z0-9-_]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 48))
    .filter(Boolean)
    .join("-");
  return `${stem || "history-output"}.${extension}`;
}

export async function downloadHistoryAsset(
  record: HistoryRecord,
  output: HistoryOutput,
  variant: "original" | "dataSaver" | "thumbnail" = "original",
): Promise<void> {
  const url = variant === "original" ? output.originalUrl : variant === "dataSaver" ? output.dataSaverUrl : output.thumbUrl;
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Download failed with status ${response.status}`);
  const blob = await response.blob();
  const filename = historyDownloadFilename(record, output, mimeToExtension(blob.type));
  const objectUrl = URL.createObjectURL(blob);
  try {
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  } finally {
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  }
}

export async function deleteHistoryRecord(record: HistoryRecord) {
  const path = record.kind === "experiment" ? "experiments" : "generations";
  return requestJson<unknown>(`/history-v2/${path}/${encodeURIComponent(record.id)}`, { method: "DELETE" });
}
