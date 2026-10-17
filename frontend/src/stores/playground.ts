// Modal Studio Vue — playground store (Phase 5).
//
// Owns Playground application state: mode/subtool, selected workflow/version,
// control draft, source/reference image ownership, output override intent,
// preset identity, submission state, queue collection, and experiment draft.
//
// Authority boundaries (frozen):
// - run identity / terminal semantics: backend + run controller contracts.
// - finished entities: historyStore. Models/nodes: infrastructureStore.
// - global settings: settingsStore (Playground only reads them).
// - visible long-running work projection: operationsStore (registry only).
// - this store never executes, polls, or caches History entities.

import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { definePersisted } from "../persistence/persistence";
import {
  getRunContext,
  newRequestId,
  stopRun,
  submitBatch,
  submitExperiment,
  submitRun as postSingleRun,
  uploadPlaygroundImage,
  type BatchVariant,
  type ControlSchemaEntry,
  type RunPayload,
} from "../api/playground";
import { createLatestTask } from "../async/latest";
import { useOperationsStore } from "./operations";

export type PlaygroundMode = "generate" | "edit" | "post";

export const PLAYGROUND_SUBTOOLS: Record<PlaygroundMode, readonly string[]> = {
  generate: ["text", "references", "layout", "sketch", "guidance"],
  edit: ["text", "references", "select", "expand", "sketch"],
  post: ["adjust", "color", "detail", "effects", "crop", "heal", "upscale"],
};

/** Later-phase placeholder: visible but execution-disabled (Upscale parked). */
export const PLAYGROUND_PLACEHOLDERS: readonly string[] = ["upscale"];

/** Preset image keys are never captured (mirrors web/studio-presets.js). */
const PRESET_IMAGE_KEYS = new Set(
  [
    "image",
    "images",
    "imageurl",
    "imagedata",
    "source",
    "source_image",
    "sourceimage",
    "mask",
    "references",
    "reference",
    "sketch",
  ].map((key) => key.toLowerCase()),
);

const MODEL_FILE_ROLES = new Set(["model_unet", "model", "unet", "clip", "vae", "model_clip", "model_vae"]);

export interface QueueItem {
  id: string;
  label: string;
  workflowId: string;
  workflowVersionId: string;
  controlValues: Record<string, unknown>;
}

export interface ExperimentAxis {
  enabled: boolean;
  values: unknown[];
  insertMode?: string;
}

export interface PlaygroundRunState {
  status: "idle" | "submitting" | "running" | "succeeded" | "failed" | "canceled";
  message: string;
  runId: string;
  experimentId: string;
  detail?: unknown;
}

/** Deep-freeze the submission intent so later UI edits cannot mutate it.
 *
 * Payloads must be JSON-serializable by contract (they are POST bodies).
 * structuredClone is preferred, but Vue reactive proxies read out of a
 * store cannot be structured-cloned, so an uncloneable value falls back to
 * a JSON snapshot — which preserves the freeze for every legal payload.
 */
export function freezeIntent<T>(value: T): T {
  try {
    if (typeof structuredClone === "function") return structuredClone(value);
  } catch {
    /* fall through to the JSON snapshot below */
  }
  return JSON.parse(JSON.stringify(value)) as T;
}

/** Strip image-like keys so presets stay image-free. */
export function stripImageKeys(values: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(values)) {
    if (PRESET_IMAGE_KEYS.has(key.toLowerCase())) continue;
    out[key] = value;
  }
  return out;
}

export function isImageRole(key: string, entry?: ControlSchemaEntry): boolean {
  if (key === "source_image" || key === "mask") return true;
  return entry?.control_kind === "image";
}

export function isModelFileRole(key: string, entry?: ControlSchemaEntry): boolean {
  if (MODEL_FILE_ROLES.has(key)) return true;
  if (!entry || typeof entry !== "object") return false;
  return entry.control_kind === "file" || entry.control_kind === "model";
}

export function defaultValuesFromSchema(
  schema: Record<string, ControlSchemaEntry>,
  graphValues?: Record<string, unknown>,
): Record<string, unknown> {
  const values: Record<string, unknown> = {};
  for (const [role, entry] of Object.entries(schema)) {
    if (!entry || typeof entry !== "object") continue;
    const graphValue = graphValues?.[role];
    if (graphValue !== undefined) {
      values[role] = graphValue;
      continue;
    }
    if (entry.default !== undefined) values[role] = entry.default;
    else if (Array.isArray(entry.enum_options) && entry.enum_options.length) {
      values[role] = entry.enum_options[0];
    }
  }
  return values;
}

/** Validate draft values against the schema without coercion. */
export function validateDraft(
  values: Record<string, unknown>,
  schema: Record<string, ControlSchemaEntry>,
): Array<{ field: string; message: string }> {
  const errors: Array<{ field: string; message: string }> = [];
  for (const [key, value] of Object.entries(values)) {
    const entry = schema[key];
    if (!entry) {
      errors.push({ field: key, message: `unknown control '${key}'` });
      continue;
    }
    if (
      !isImageRole(key, entry) &&
      !isModelFileRole(key, entry) &&
      Array.isArray(entry.enum_options) &&
      entry.enum_options.length &&
      value !== undefined &&
      value !== null &&
      !entry.enum_options.some((opt) => opt === value)
    ) {
      errors.push({ field: key, message: "must be one of the available options" });
    }
    if (typeof value === "number") {
      if (typeof entry.minimum === "number" && value < entry.minimum) {
        errors.push({ field: key, message: `must be >= ${entry.minimum}` });
      }
      if (typeof entry.maximum === "number" && value > entry.maximum) {
        errors.push({ field: key, message: `must be <= ${entry.maximum}` });
      }
    }
    if (entry.required && (value === undefined || value === null || (typeof value === "string" && value.trim() === ""))) {
      errors.push({ field: key, message: "required" });
    }
  }
  for (const [key, entry] of Object.entries(schema)) {
    if (entry?.required && !Object.prototype.hasOwnProperty.call(values, key)) {
      errors.push({ field: key, message: `missing required control '${key}'` });
    }
  }
  return errors;
}

const draftPersisted = (workflowId: string, versionId: string) =>
  definePersisted<Record<string, unknown>>(
    `playground.draft.${workflowId}.${versionId}`,
    {},
  );

const persistedSelection = definePersisted<{ workflowId: string; versionId: string }>(
  "playground.selection.v1",
  { workflowId: "", versionId: "" },
);

/** Last generation id per workflow/version (id only — the entity stays in historyStore). */
const persistedGeneration = definePersisted<{ key: string; generationId: string }>(
  "playground.current-generation.v1",
  { key: "", generationId: "" },
);

export const usePlaygroundStore = defineStore("studio-playground", () => {
  // Phase-1 identity (kept for compatibility).
  const featureId = ref("txt2img");
  const experimentMode = ref(false);
  // Queue/experiment are a radio pair (legacy invariant): enabling one clears
  // the other. queueMode wins only when experimentMode is off.
  const queueMode = ref(false);

  // Modes / subtools.
  const activeMode = ref<PlaygroundMode>("generate");
  const activeSubtool = ref("text");

  // Workflow selection + run context.
  const workflowId = ref(persistedSelection.read().workflowId);
  const versionId = ref(persistedSelection.read().versionId);
  const runContext = ref<Record<string, unknown> | null>(null);
  const schema = ref<Record<string, ControlSchemaEntry>>({});
  const controlValues = ref<Record<string, unknown>>({});
  const contextStatus = ref<"idle" | "loading" | "ready" | "error">("idle");
  const contextError = ref("");
  const contextReasons = ref<string[]>([]);
  const runnable = ref(false);
  const selectionGen = ref(0);

  // Source image ownership: {ownerKey, token}. A delayed upload commits only
  // when both still match the live selection (latest-wins, stale discard).
  const sourceOwnerKey = ref("");
  const sourceToken = ref(0);
  const sourceUploading = ref(false);
  const sourceError = ref("");

  // References (ordered companion cards) + workflow method patch.
  const references = ref<Array<{ id: string; filename: string }>>([]);
  const workflowMethods = ref<Record<string, unknown>>({});

  // Output override: run intent only. Never written to Settings.
  const outputOverride = ref<Record<string, unknown>>({});

  // Preset identity.
  const presetId = ref<string | null>(null);
  const presetDirty = ref(false);

  // Submission state (projection; backend remains truth).
  const runState = ref<PlaygroundRunState>({
    status: "idle",
    message: "",
    runId: "",
    experimentId: "",
  });
  const currentGenerationId = ref<string | null>(null);
  const lastSubmitted = ref<RunPayload | null>(null);
  const submittedSource = ref("");

  // Queue collection (frozen variants).
  const queue = ref<QueueItem[]>([]);

  // Experiment draft: axes over schema controls.
  const experimentAxes = ref<Record<string, ExperimentAxis>>({});

  const contextTask = createLatestTask();

  const contextKey = computed(() => `${workflowId.value}::${versionId.value}`);
  const draftErrors = computed(() => validateDraft(controlValues.value, schema.value));
  const gateReason = computed((): string | null => {
    if (contextStatus.value === "loading") return "Loading workflow…";
    if (contextStatus.value === "error") return contextError.value || "Workflow unavailable";
    if (!workflowId.value) return "Select a workflow to begin";
    if (!runnable.value) {
      return contextReasons.value[0] || "This workflow is not runnable yet";
    }
    const missing = draftErrors.value.find((item) => item.message === "required" || item.message.startsWith("missing"));
    if (missing) return `Fill in ${missing.field} to generate`;
    if (PLAYGROUND_PLACEHOLDERS.includes(activeSubtool.value)) {
      return "This tool arrives in a later phase — execution is disabled";
    }
    if (isBusy.value) return "A run is already in flight";
    return null;
  });
  const isBusy = computed(() => runState.value.status === "submitting" || runState.value.status === "running");
  const queueCount = computed(() => queue.value.length);
  const enabledAxes = computed(() =>
    Object.entries(experimentAxes.value).filter(([, axis]) => axis.enabled && axis.values.length > 0),
  );

  function persistSelection(): void {
    persistedSelection.write({ workflowId: workflowId.value, versionId: versionId.value });
  }

  function persistDraft(): void {
    if (!workflowId.value || !versionId.value) return;
    try {
      draftPersisted(workflowId.value, versionId.value).write({ ...controlValues.value });
    } catch {
      /* persistence is best-effort */
    }
  }

  function setFeature(id: string): void {
    featureId.value = id;
  }

  function setExperimentMode(enabled: boolean): void {
    experimentMode.value = enabled;
    if (enabled) queueMode.value = false;
  }

  function setQueueMode(enabled: boolean): void {
    queueMode.value = enabled;
    if (enabled) experimentMode.value = false;
  }

  function setTool(mode: PlaygroundMode, subtool: string): void {
    activeMode.value = mode;
    activeSubtool.value = subtool;
  }

  function setControl(role: string, value: unknown): void {
    controlValues.value = { ...controlValues.value, [role]: value };
    presetDirty.value = true;
    persistDraft();
  }

  function resetDraft(): void {
    controlValues.value = defaultValuesFromSchema(schema.value);
    references.value = [];
    workflowMethods.value = {};
    outputOverride.value = {};
    presetDirty.value = false;
    clearSourceOwnership();
    persistDraft();
  }

  function clearSourceOwnership(): void {
    sourceOwnerKey.value = "";
    sourceToken.value += 1;
    sourceUploading.value = false;
    sourceError.value = "";
  }

  /** Direct source assignment under the live owner key (picker, replace). */
  function setSource(filename: string, ownerKey: string): void {
    sourceOwnerKey.value = ownerKey;
    controlValues.value = { ...controlValues.value, source_image: filename };
    presetDirty.value = true;
    persistDraft();
  }

  function clearSource(): void {
    const next = { ...controlValues.value };
    delete next.source_image;
    delete next.mask;
    controlValues.value = next;
    clearSourceOwnership();
    persistDraft();
  }

  /** Begin an async upload; the returned token must match at completion. */
  function beginUpload(ownerKey: string): number {
    sourceOwnerKey.value = ownerKey;
    sourceToken.value += 1;
    sourceUploading.value = true;
    sourceError.value = "";
    return sourceToken.value;
  }

  /** Commit an upload only when token + owner still match (stale discard). */
  function commitUpload(token: number, ownerKey: string, filename: string): boolean {
    if (token !== sourceToken.value || ownerKey !== sourceOwnerKey.value) return false;
    sourceUploading.value = false;
    controlValues.value = { ...controlValues.value, source_image: filename };
    presetDirty.value = true;
    persistDraft();
    return true;
  }

  function failUpload(token: number, ownerKey: string, message: string): void {
    if (token !== sourceToken.value || ownerKey !== sourceOwnerKey.value) return;
    sourceUploading.value = false;
    sourceError.value = message;
  }

  async function uploadSource(file: File): Promise<boolean> {
    const owner = contextKey.value;
    const token = beginUpload(owner);
    const result = await uploadPlaygroundImage(file);
    if (!result.ok || !result.filename) {
      failUpload(token, owner, result.message || "Upload failed");
      return false;
    }
    return commitUpload(token, owner, result.filename);
  }

  function addReference(filename: string): void {
    references.value = [...references.value, { id: newRequestId("ref"), filename }];
    presetDirty.value = true;
  }

  function removeReference(id: string): void {
    references.value = references.value.filter((item) => item.id !== id);
    presetDirty.value = true;
  }

  function setOutputOverride(patch: Record<string, unknown>): void {
    outputOverride.value = { ...outputOverride.value, ...patch };
    presetDirty.value = true;
  }

  function clearOutputOverride(): void {
    outputOverride.value = {};
    presetDirty.value = true;
  }

  /** Apply a version preset: image-free, clears stale ownership. */
  function applyPreset(state: Record<string, unknown> | null, id: string | null): void {
    const controls =
      state && typeof state.controls === "object"
        ? (state.controls as Record<string, unknown>)
        : {};
    const clean = stripImageKeys(controls);
    controlValues.value = { ...defaultValuesFromSchema(schema.value), ...clean };
    references.value = [];
    outputOverride.value = {};
    clearSourceOwnership();
    rememberGeneration(null);
    presetId.value = id;
    presetDirty.value = false;
    persistDraft();
  }

  async function selectWorkflow(
    nextWorkflowId: string,
    nextVersionId = "",
    fetchImpl?: typeof fetch,
  ): Promise<{ ok: boolean; error?: string }> {
    const gen = (selectionGen.value += 1);
    workflowId.value = nextWorkflowId;
    versionId.value = nextVersionId;
    runContext.value = null;
    schema.value = {};
    controlValues.value = {};
    contextReasons.value = [];
    contextError.value = "";
    runnable.value = false;
    clearSourceOwnership();
    references.value = [];
    contextStatus.value = "loading";
    persistSelection();
    const result = await contextTask.run(async (signal) => {
      const data = await getRunContext(nextWorkflowId, nextVersionId, fetchImpl);
      if (signal.aborted) return null;
      return data;
    });
    if (result.stale || !result.value) return { ok: false, error: "superseded" };
    if (gen !== selectionGen.value) return { ok: false, error: "superseded" };
    const data = result.value;
    if (!data || data.status !== "ok") {
      contextStatus.value = "error";
      contextError.value = "Could not load workflow";
      return { ok: false, error: contextError.value };
    }
    const nextSchema =
      (data.control_schema as Record<string, ControlSchemaEntry>) ?? {};
    const resolvedVersionId =
      (data.version as Record<string, unknown> | undefined)?.workflow_version_id;
    if (typeof resolvedVersionId === "string" && resolvedVersionId) {
      versionId.value = resolvedVersionId;
      persistSelection();
    }
    runContext.value = data as unknown as Record<string, unknown>;
    schema.value = nextSchema;
    const reasons: string[] = Array.isArray(
      (data.version as Record<string, unknown> | undefined)?.reasons,
    )
      ? ((data.version as Record<string, unknown>).reasons as string[])
      : [];
    if ((data.version as Record<string, unknown> | undefined)?.runnable !== true && !reasons.length) {
      reasons.push("This workflow is not runnable yet");
    }
    if (!data.mapping) reasons.push("missing mapping");
    contextReasons.value = reasons;
    runnable.value = reasons.length === 0;
    contextStatus.value = "ready";
    // Draft precedence: saved draft over graph defaults; unknown keys dropped.
    let draft: Record<string, unknown> = {};
    try {
      draft = draftPersisted(workflowId.value, versionId.value).read();
    } catch {
      draft = {};
    }
    const defaults = defaultValuesFromSchema(nextSchema);
    const merged: Record<string, unknown> = { ...defaults };
    for (const [key, value] of Object.entries(draft)) {
      if (Object.prototype.hasOwnProperty.call(nextSchema, key)) merged[key] = value;
    }
    controlValues.value = merged;
    contextError.value = "";
    // Restore the last generation id for this exact context (id only; the
    // entity always resolves through historyStore).
    try {
      const saved = persistedGeneration.read();
      currentGenerationId.value =
        saved.key === contextKey.value && saved.generationId ? saved.generationId : null;
    } catch {
      currentGenerationId.value = null;
    }
    return { ok: true };
  }

  function buildPayload(modalOptions?: Record<string, unknown>): RunPayload {
    return {
      workflow_id: workflowId.value,
      workflow_version_id: versionId.value,
      featureId: featureId.value,
      workflow_type: String(
        (runContext.value?.workflow as Record<string, unknown> | undefined)?.workflow_type ?? "t2i",
      ),
      controls: freezeIntent({ ...controlValues.value }),
      modal_options: modalOptions ? freezeIntent({ ...modalOptions }) : undefined,
      profile_name: null,
      request_id: newRequestId("req"),
      metadata: {
        source: "studio_playground_vue",
        workflow_id: workflowId.value,
        workflow_version_id: versionId.value,
      },
      trace: {},
    };
  }

  function applySubmissionExtras(
    payload: RunPayload,
    extras: { method?: unknown; references?: unknown; guidance?: unknown; style?: unknown },
  ): void {
    if (extras.method) payload.studio_method = extras.method;
    if (extras.references) payload.studio_references = extras.references;
    if (extras.guidance) payload.guidance = extras.guidance;
    if (extras.style) {
      payload.studio_style = extras.style;
      const composed = (extras.style as Record<string, unknown>).composed;
      if (typeof composed === "string") {
        payload.controls = { ...payload.controls, prompt: composed };
      }
    }
  }

  async function submitRun(
    options: {
      modalOptions?: Record<string, unknown>;
      method?: unknown;
      references?: unknown;
      guidance?: unknown;
      style?: unknown;
      fetchImpl?: typeof fetch;
      onDone?: (record: { id: string }) => void;
    } = {},
  ): Promise<{ ok: boolean; error?: string }> {
    const gate = gateReason.value;
    if (gate) return { ok: false, error: gate };
    // Freeze the full intent BEFORE any await: later UI edits must not leak in.
    const payload = buildPayload(options.modalOptions);
    applySubmissionExtras(payload, {
      method: options.method,
      references:
        options.references ??
        (references.value.length
          ? { items: freezeIntent(references.value.map((item) => item.filename)), methods: workflowMethods.value }
          : undefined),
      guidance: options.guidance,
      style: options.style,
    });
    lastSubmitted.value = freezeIntent(payload);
    submittedSource.value = String(payload.controls.source_image ?? "");
    const operations = useOperationsStore();
    const opId = operations.start({
      kind: "generation",
      label: "Generation",
      status: "running",
      message: "Submitting…",
    });
    runState.value = { status: "submitting", message: "Submitting…", runId: "", experimentId: "" };
    try {
      const result = await postSingleRun(payload, options.fetchImpl);
      const runId = String(result.runId ?? result.run_id ?? result.id ?? "");
      rememberGeneration(runId || null);
      runState.value = {
        status: "running",
        message: "Running…",
        runId,
        experimentId: "",
        detail: result,
      };
      operations.patch(opId, { message: "Running…" });
      if (result.status === "ok" || result.direct_run) {
        runState.value = { status: "succeeded", message: "Run completed", runId, experimentId: "", detail: result };
        operations.finish(opId, "Run completed");
        if (runId) options.onDone?.({ id: runId });
        return { ok: true };
      }
      runState.value = { status: "running", message: "Running…", runId, experimentId: "", detail: result };
      return { ok: true };
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "Submission failed";
      runState.value = { status: "failed", message, runId: "", experimentId: "" };
      operations.fail(opId, message);
      return { ok: false, error: message };
    }
  }

  function enqueueCurrent(label?: string): { ok: boolean; error?: string } {
    if (!workflowId.value) return { ok: false, error: "Select a workflow first" };
    queue.value = [
      ...queue.value,
      {
        id: newRequestId("q"),
        label: label || `Variant ${queue.value.length + 1}`,
        workflowId: workflowId.value,
        workflowVersionId: versionId.value,
        controlValues: freezeIntent({ ...controlValues.value }),
      },
    ];
    return { ok: true };
  }

  function removeQueued(id: string): void {
    queue.value = queue.value.filter((item) => item.id !== id);
  }

  function clearQueue(): void {
    queue.value = [];
  }

  async function drainQueue(
    options: { modalOptions?: Record<string, unknown>; fetchImpl?: typeof fetch } = {},
  ): Promise<{ ok: boolean; error?: string }> {
    if (!queue.value.length) return { ok: false, error: "Queue is empty" };
    if (isBusy.value) return { ok: false, error: "A run is already in flight" };
    const chunk = queue.value.filter(
      (item) => item.workflowId === queue.value[0].workflowId,
    );
    const rest = queue.value.filter((item) => item.workflowId !== queue.value[0].workflowId);
    queue.value = rest;
    // Singleton chunks reuse the single-run path (which owns its own busy
    // gate); only true batches publish batch presentation state first.
    if (chunk.length === 1) {
      const single = chunk[0];
      controlValues.value = { ...single.controlValues };
      return submitRun({ modalOptions: options.modalOptions, fetchImpl: options.fetchImpl });
    }
    const operations = useOperationsStore();
    const opId = operations.start({
      kind: "generation",
      label: `Batch (${chunk.length})`,
      status: "running",
      message: `Batch running: 0 of ${chunk.length} complete`,
    });
    runState.value = {
      status: "running",
      message: `Batch running: 0 of ${chunk.length} complete`,
      runId: "",
      experimentId: "",
    };
    try {
      const variants: BatchVariant[] = chunk.map((item) => ({
        request_id: newRequestId("variant"),
        controls: freezeIntent(item.controlValues),
      }));
      await submitBatch(
        {
          profile: null,
          workflow_id: chunk[0].workflowId,
          workflow_version_id: chunk[0].workflowVersionId,
          request_id: newRequestId("batch"),
          modal_options: options.modalOptions ? freezeIntent({ ...options.modalOptions }) : null,
          variants,
        },
        options.fetchImpl,
      );
      runState.value = { status: "succeeded", message: "Batch submitted", runId: "", experimentId: "" };
      operations.finish(opId, "Batch submitted");
      return { ok: true };
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "Batch failed";
      runState.value = { status: "failed", message, runId: "", experimentId: "" };
      operations.fail(opId, message);
      return { ok: false, error: message };
    }
  }

  function setAxis(controlId: string, patch: Partial<ExperimentAxis>): void {
    const current = experimentAxes.value[controlId] ?? { enabled: false, values: [] };
    experimentAxes.value = { ...experimentAxes.value, [controlId]: { ...current, ...patch } };
  }

  function clearAxes(): void {
    experimentAxes.value = {};
  }

  async function submitExperimentDef(
    options: { modalOptions?: Record<string, unknown>; fetchImpl?: typeof fetch } = {},
  ): Promise<{ ok: boolean; error?: string }> {
    if (enabledAxes.value.length === 0) return { ok: false, error: "Enable at least one sweep axis" };
    const gate = gateReason.value;
    if (gate && gate !== "A run is already in flight") return { ok: false, error: gate };
    const base = buildPayload(options.modalOptions);
    const payload = freezeIntent({
      ...base,
      axes: Object.fromEntries(enabledAxes.value.map(([id, axis]) => [id, axis.values])),
    });
    lastSubmitted.value = payload as unknown as RunPayload;
    const operations = useOperationsStore();
    const opId = operations.start({ kind: "experiment", label: "Experiment", status: "running" });
    runState.value = { status: "submitting", message: "Submitting experiment…", runId: "", experimentId: "" };
    try {
      const result = await submitExperiment(payload, options.fetchImpl);
      const experimentId = String(result.experiment_id ?? result.experimentId ?? result.id ?? "");
      rememberGeneration(experimentId || null);
      runState.value = { status: "running", message: "Experiment running…", runId: "", experimentId, detail: result };
      operations.patch(opId, { message: "Experiment running…" });
      return { ok: true };
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "Experiment submission failed";
      runState.value = { status: "failed", message, runId: "", experimentId: "" };
      operations.fail(opId, message);
      return { ok: false, error: message };
    }
  }

  async function cancelRun(fetchImpl?: typeof fetch): Promise<void> {
    const id = runState.value.experimentId || runState.value.runId;
    runState.value = { ...runState.value, status: "canceled", message: "Run canceled" };
    if (id) {
      try {
        await stopRun(id, fetchImpl);
      } catch {
        /* cancel is best-effort */
      }
    }
  }

  function rememberGeneration(generationId: string | null): void {
    currentGenerationId.value = generationId;
    try {
      persistedGeneration.write({ key: contextKey.value, generationId: generationId ?? "" });
    } catch {
      /* persistence is best-effort */
    }
  }

  function noteSucceeded(generationId: string): void {
    rememberGeneration(generationId);
    runState.value = { ...runState.value, status: "succeeded", message: "Run completed" };
  }

  function noteFailed(message: string): void {
    runState.value = { ...runState.value, status: "failed", message };
  }

  return {
    featureId,
    experimentMode,
    queueMode,
    activeMode,
    activeSubtool,
    workflowId,
    versionId,
    runContext,
    schema,
    controlValues,
    contextStatus,
    contextError,
    contextReasons,
    runnable,
    sourceOwnerKey,
    sourceUploading,
    sourceError,
    references,
    workflowMethods,
    outputOverride,
    presetId,
    presetDirty,
    runState,
    currentGenerationId,
    lastSubmitted,
    submittedSource,
    queue,
    experimentAxes,
    contextKey,
    draftErrors,
    gateReason,
    isBusy,
    queueCount,
    enabledAxes,
    setFeature,
    setExperimentMode,
    setQueueMode,
    setTool,
    setControl,
    resetDraft,
    setSource,
    clearSource,
    beginUpload,
    commitUpload,
    failUpload,
    uploadSource,
    addReference,
    removeReference,
    setOutputOverride,
    clearOutputOverride,
    applyPreset,
    selectWorkflow,
    buildPayload,
    submitRun,
    enqueueCurrent,
    removeQueued,
    clearQueue,
    drainQueue,
    setAxis,
    clearAxes,
    submitExperimentDef,
    cancelRun,
    noteSucceeded,
    noteFailed,
  };
});
