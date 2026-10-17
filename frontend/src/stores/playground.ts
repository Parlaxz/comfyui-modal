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
import { createRunController } from "../run/runController";
import { useHistoryStore } from "./history";
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

/** Complete frozen execution intent for one queued item (Phase-13 scope).
 *
 * The rule: once queued, later UI edits cannot change what that queue item
 * means. The snapshot covers workflow identity + every task-owned request
 * input the legacy Phase-13 queue froze (mode/subtool, controls, execution
 * methods, references, style, guidance, layout, run overrides). Editor
 * internals that are not request inputs are deliberately excluded.
 */
export interface QueuedRunIntent {
  mode: PlaygroundMode;
  subtool: string;
  controls: Record<string, unknown>;
  methods: Record<string, unknown>;
  references: Array<{ id: string; filename: string }>;
  guidance: unknown;
  style: unknown;
  layout: unknown;
  outputOverrides: Record<string, unknown>;
}

export interface QueueItem {
  id: string;
  label: string;
  workflowId: string;
  workflowVersionId: string;
  /** Frozen at enqueue; later UI edits cannot leak in (same object). */
  controlValues: Record<string, unknown>;
  /** Full frozen execution intent (controlValues === intent.controls). */
  intent: QueuedRunIntent;
}

/** Batch-compatibility key: only items with identical immutable execution
 * identity may share one backend batch. Same workflow but a different
 * version (or different execution methods) never merges.
 */
export function queueCompatibilityKey(item: Pick<QueueItem, "workflowId" | "workflowVersionId" | "intent">): string {
  return `${item.workflowId}::${item.workflowVersionId}::${stableStringify(item.intent.methods)}`;
}

/** Deterministic key-order stringify for small intent records. */
export function stableStringify(value: unknown): string {
  if (value === null || value === undefined) return "null";
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`;
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>)
      .filter(([, entry]) => entry !== undefined)
      .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
    return `{${entries.map(([key, entry]) => `${JSON.stringify(key)}:${stableStringify(entry)}`).join(",")}}`;
  }
  const serialized = JSON.stringify(value);
  return typeof serialized === "string" ? serialized : String(value);
}

/** Non-controls intent equality: batch chunks share everything but controls. */
export function queueNonControlsMatch(left: QueueItem, right: QueueItem): boolean {
  const strip = (intent: QueuedRunIntent) => {
    const { controls: _controls, ...rest } = intent;
    return rest;
  };
  return stableStringify(strip(left.intent)) === stableStringify(strip(right.intent));
}

export interface ExperimentAxis {
  enabled: boolean;
  values: unknown[];
  insertMode?: string;
}

export type ExperimentCellStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "canceled"
  | "interrupted";

const EXPERIMENT_TERMINAL: ReadonlySet<ExperimentCellStatus> = new Set([
  "completed",
  "failed",
  "canceled",
  "interrupted",
]);

export interface ExperimentCellState {
  status: ExperimentCellStatus;
  attemptId: string | null;
  runId: string | null;
  error?: string | null;
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

  // Shared run controller: the semantic owner of run identity, event
  // filtering, and terminal decisions (ported from
  // web/studio-playground-run.js). The store projects controller state
  // into runState/operationsStore but never decides terminality itself.
  // selectWorkflow/controls edits never touch the controller, so a
  // mid-run UI switch cannot mutate the active run.
  const runController = createRunController();
  // operationsStore id for the currently active run (for precise patching;
  // the registry's own terminal freeze is the backstop).
  const activeOperationId = ref<string | null>(null);

  // Experiment execution identity (Experiment V2 semantics): one active
  // experiment id plus per-cell status lifecycle. Late events carrying a
  // different experiment id are rejected; retry targets a single failed
  // cell (no retry-all). Transport stays in ../api/history.
  const activeExperimentId = ref<string | null>(null);
  const experimentCells = ref<Record<string, ExperimentCellState>>({});
  const experimentActionBusy = ref(false);
  // Cells the user explicitly asked to retry: only these may transition
  // out of a terminal status, and only into a NEW attempt identity.
  const pendingExperimentRetry = ref(new Set<string>());

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

  /** Project controller truth into runState (projection only, never a decision). */
  function syncRunStateFromController(message?: string): void {
    const status = runController.getStatus();
    const runId = runController.getRunId() ?? "";
    const experimentId = runController.getSnapshot().experimentId ?? "";
    const failure = runController.getFailureMessage();
    if (status === "completed") {
      runState.value = { status: "succeeded", message: message ?? "Run completed", runId, experimentId };
    } else if (status === "failed") {
      runState.value = { status: "failed", message: message ?? failure ?? "Run failed", runId, experimentId };
    } else if (status === "canceled") {
      runState.value = { status: "canceled", message: message ?? "Run canceled", runId, experimentId };
    } else if (status === null || status === "created") {
      runState.value = { status: "idle", message: message ?? "", runId: "", experimentId: "" };
    } else {
      runState.value = {
        status: status === "submitting" ? "submitting" : "running",
        message: message ?? runState.value.message,
        runId,
        experimentId,
      };
    }
  }

  /** Capture the full current execution intent, frozen (Phase-13 scope). */
  function captureIntent(): QueuedRunIntent {
    return freezeIntent<QueuedRunIntent>({
      mode: activeMode.value,
      subtool: activeSubtool.value,
      controls: { ...controlValues.value },
      methods: { ...workflowMethods.value },
      references: references.value.map((item) => ({ ...item })),
      guidance: undefined,
      style: undefined,
      layout: undefined,
      outputOverrides: { ...outputOverride.value },
    });
  }

  /**
   * Execute one frozen payload through the shared run controller.
   * The payload's own workflow/version identity is used; the current UI
   * selection is never consulted here, so queued items survive UI switches.
   */
  async function executeRunPayload(
    payload: RunPayload,
    options: { fetchImpl?: typeof fetch; onDone?: (record: { id: string }) => void } = {},
  ): Promise<{ ok: boolean; error?: string }> {
    const runId = runController.beginRun();
    const operations = useOperationsStore();
    const opId = operations.start({
      kind: "generation",
      label: "Generation",
      status: "running",
      message: "Submitting…",
    });
    activeOperationId.value = opId;
    runController.applySubmissionAck();
    runController.attach();
    runState.value = { status: "submitting", message: "Submitting…", runId, experimentId: "" };
    try {
      const result = await postSingleRun(payload, options.fetchImpl);
      if (runController.getRunId() !== runId) {
        // A newer run began while this POST was in flight; this result is
        // stale and must not touch the active run (late prior-run guard).
        operations.cancel(opId, "Superseded by a newer run");
        return { ok: false, error: "superseded" };
      }
      const backendRunId = String(result.runId ?? result.run_id ?? result.id ?? "");
      const promptId = result.prompt_id ?? result.promptId ?? null;
      runController.setBackendIds({
        promptId: promptId != null ? String(promptId) : null,
        experimentId: null,
      });
      const outcome = runController.applyDirectResult(result, runId);
      if (outcome === "completed") {
        rememberGeneration(backendRunId || null);
        const message = "Run completed";
        syncRunStateFromController(message);
        operations.finish(opId, message);
        activeOperationId.value = null;
        if (backendRunId) {
          try {
            useHistoryStore().noteRunResult(backendRunId, "generation");
          } catch {
            /* history convergence is best-effort; the run already completed */
          }
          options.onDone?.({ id: backendRunId });
        }
        return { ok: true };
      }
      if (outcome === "failed") {
        const message = runController.getFailureMessage() ?? "Run failed";
        syncRunStateFromController(message);
        operations.fail(opId, message);
        activeOperationId.value = null;
        return { ok: false, error: message };
      }
      if (outcome === "accepted") {
        // Scheduler path: acknowledged, completion arrives via later
        // events/snapshot through the controller (runId preserved).
        runState.value = {
          status: "running",
          message: "Running…",
          runId,
          experimentId: "",
        };
        operations.patch(opId, { message: "Running…" });
        return { ok: true };
      }
      // "ignored": the run was canceled (or superseded) while POST was in
      // flight. Cancel is authoritative — never resurrect.
      syncRunStateFromController();
      activeOperationId.value = null;
      return { ok: false, error: "Run canceled" };
    } catch (cause) {
      if (runController.getRunId() !== runId || runController.isTerminal()) {
        // Superseded or already terminal (e.g. canceled): the terminal
        // decision stands; never resurrect from a transport error.
        syncRunStateFromController();
        return { ok: false, error: "superseded" };
      }
      const message = cause instanceof Error ? cause.message : "Submission failed";
      runController.applyLocalError(message);
      syncRunStateFromController(message);
      operations.fail(opId, message);
      activeOperationId.value = null;
      return { ok: false, error: message };
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
    return executeRunPayload(payload, { fetchImpl: options.fetchImpl, onDone: options.onDone });
  }

  /**
   * Execute one queued item with ITS OWN frozen identity (workflow id,
   * version id, and full intent). The current UI selection is not read.
   */
  async function submitQueuedItem(
    item: QueueItem,
    options: { modalOptions?: Record<string, unknown>; fetchImpl?: typeof fetch } = {},
  ): Promise<{ ok: boolean; error?: string }> {
    const intent = item.intent;
    const payload: RunPayload = freezeIntent<RunPayload>({
      workflow_id: item.workflowId,
      workflow_version_id: item.workflowVersionId,
      featureId: featureId.value,
      workflow_type: String(
        (runContext.value?.workflow as Record<string, unknown> | undefined)?.workflow_type ?? "t2i",
      ),
      controls: { ...intent.controls },
      modal_options: options.modalOptions ? freezeIntent({ ...options.modalOptions }) : undefined,
      profile_name: null,
      request_id: newRequestId("req"),
      metadata: {
        source: "studio_playground_vue_queue",
        workflow_id: item.workflowId,
        workflow_version_id: item.workflowVersionId,
        queue_id: item.id,
      },
      trace: {},
    });
    if (intent.methods && Object.keys(intent.methods).length) {
      payload.studio_method = freezeIntent(intent.methods);
    }
    if (intent.references.length) {
      payload.studio_references = {
        items: freezeIntent(intent.references.map((entry) => entry.filename)),
        methods: freezeIntent(intent.methods),
      };
    }
    if (intent.guidance !== undefined) payload.guidance = freezeIntent(intent.guidance);
    if (intent.style !== undefined) {
      payload.studio_style = freezeIntent(intent.style);
    }
    if (Object.keys(intent.outputOverrides).length) {
      payload.modal_options = freezeIntent({
        ...(payload.modal_options ?? {}),
        ...intent.outputOverrides,
      });
    }
    lastSubmitted.value = freezeIntent(payload);
    submittedSource.value = String(payload.controls.source_image ?? "");
    return executeRunPayload(payload, { fetchImpl: options.fetchImpl });
  }

  function enqueueCurrent(label?: string): { ok: boolean; error?: string } {
    if (!workflowId.value) return { ok: false, error: "Select a workflow first" };
    // Freeze the full execution intent now: later UI edits (controls,
    // methods, references, overrides, or even a workflow/version switch)
    // cannot mutate what this queued item means.
    const intent = captureIntent();
    const item: QueueItem = {
      id: newRequestId("q"),
      label: label || `Variant ${queue.value.length + 1}`,
      workflowId: workflowId.value,
      workflowVersionId: versionId.value,
      controlValues: intent.controls,
      intent,
    };
    queue.value = [...queue.value, item];
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
    // Group only the leading FIFO run of mutually compatible identity.
    // Same workflow + same version + same execution methods may batch;
    // anything else waits for a later drain (never silently merged).
    const key = queueCompatibilityKey(queue.value[0]);
    const chunk = queue.value.filter((item) => queueCompatibilityKey(item) === key);
    const rest = queue.value.filter((item) => queueCompatibilityKey(item) !== key);
    queue.value = rest;
    // Only a fully identical non-controls intent may share one backend
    // batch call (run_batch variants carry controls only); otherwise the
    // head item runs as a singleton with its own identity.
    const batchable =
      chunk.length > 1 && chunk.every((item) => queueNonControlsMatch(item, chunk[0]));
    if (!batchable) {
      return submitQueuedItem(chunk[0], { modalOptions: options.modalOptions, fetchImpl: options.fetchImpl });
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
        controls: freezeIntent(item.intent.controls),
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
    // Deterministic axis order (sorted keys) + deep freeze: the submitted
    // definition is immutable post-submit; later UI edits cannot leak in.
    const orderedAxes = Object.fromEntries(
      enabledAxes.value
        .slice()
        .sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0))
        .map(([id, axis]) => [id, freezeIntent(axis.values)]),
    );
    const payload = freezeIntent({
      ...base,
      axes: orderedAxes,
    });
    lastSubmitted.value = payload as unknown as RunPayload;
    const operations = useOperationsStore();
    const opId = operations.start({ kind: "experiment", label: "Experiment", status: "running" });
    runState.value = { status: "submitting", message: "Submitting experiment…", runId: "", experimentId: "" };
    try {
      const result = await submitExperiment(payload, options.fetchImpl);
      const experimentId = String(result.experiment_id ?? result.experimentId ?? result.id ?? "");
      rememberGeneration(experimentId || null);
      activeExperimentId.value = experimentId || null;
      experimentCells.value = {};
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

  /** Normalize one raw experiment status/cell payload into cell ownership state. */
  function reconcileExperimentCells(cells: unknown[]): void {
    for (const raw of cells) {
      if (!raw || typeof raw !== "object") continue;
      const record = raw as Record<string, unknown>;
      const cellId = String(record.cell_id ?? record.cellId ?? record.key ?? "");
      if (!cellId) continue;
      const statusRaw = String(record.status ?? record.state ?? "queued").toLowerCase();
      const status: ExperimentCellStatus = (
        ["queued", "running", "completed", "failed", "canceled", "interrupted"] as const
      ).includes(statusRaw as ExperimentCellStatus)
        ? (statusRaw as ExperimentCellStatus)
        : "queued";
      const attemptId =
        record.attempt_id != null
          ? String(record.attempt_id)
          : record.attemptId != null
            ? String(record.attemptId)
            : null;
      const runId = record.run_id != null ? String(record.run_id) : record.runId != null ? String(record.runId) : null;
      const previous = experimentCells.value[cellId];
      if (previous && EXPERIMENT_TERMINAL.has(previous.status)) {
        // Terminal first-wins per cell: a bare status poll can never regress
        // a terminal cell; only an explicit retry (new attempt identity,
        // armed via retryExperimentCell) reopens it.
        if (attemptId !== null && attemptId !== previous.attemptId) {
          const armed = pendingExperimentRetry.value.has(cellId);
          if (!armed) continue;
          pendingExperimentRetry.value.delete(cellId);
        } else {
          continue;
        }
      }
      experimentCells.value = {
        ...experimentCells.value,
        [cellId]: {
          status,
          attemptId,
          runId,
          error: record.error != null ? String(record.error) : null,
        },
      };
    }
  }

  /**
   * Apply one experiment status payload. Ownership filter: payloads for a
   * different experiment are rejected and never mutate this experiment's
   * cells (late-event routing safety).
   */
  function applyExperimentStatus(payload: {
    experiment_id?: unknown;
    experimentId?: unknown;
    id?: unknown;
    cells?: unknown;
  }): boolean {
    const incomingId = String(payload.experiment_id ?? payload.experimentId ?? payload.id ?? "");
    if (!incomingId || activeExperimentId.value === null) {
      if (!incomingId) return false;
      // No active experiment yet: adopt only when idle (first-wins after).
      if (activeExperimentId.value !== null && incomingId !== activeExperimentId.value) return false;
      activeExperimentId.value = incomingId;
    }
    if (incomingId !== activeExperimentId.value) return false; // foreign experiment
    const cells = Array.isArray(payload.cells) ? payload.cells : [];
    reconcileExperimentCells(cells);
    return true;
  }

  /**
   * Apply one experiment event. Foreign experiment ids are dropped before
   * they reach cell state.
   */
  function applyExperimentEvent(event: {
    experiment_id?: unknown;
    experimentId?: unknown;
    cell_id?: unknown;
    cellId?: unknown;
    status?: unknown;
    state?: unknown;
    attempt_id?: unknown;
    attemptId?: unknown;
  }): boolean {
    const incomingId = String(event.experiment_id ?? event.experimentId ?? "");
    if (!incomingId || incomingId !== activeExperimentId.value) return false;
    const cellId = String(event.cell_id ?? event.cellId ?? "");
    if (!cellId) return false;
    reconcileExperimentCells([
      {
        cell_id: cellId,
        status: event.status ?? event.state ?? "running",
        attempt_id: event.attempt_id ?? event.attemptId ?? undefined,
      },
    ]);
    return true;
  }

  /**
   * Retry exactly one failed cell (per-cell retry only; retry-all stays
   * forbidden). Single-flight per cell; arms a new-attempt transition for
   * that cell only.
   */
  async function retryExperimentCell(cellId: string): Promise<{ ok: boolean; error?: string }> {
    const id = String(cellId);
    const cell = experimentCells.value[id];
    if (activeExperimentId.value === null) return { ok: false, error: "No active experiment" };
    if (!cell || cell.status !== "failed") return { ok: false, error: "Cell is not failed" };
    if (experimentActionBusy.value) return { ok: false, error: "Another experiment action is in flight" };
    experimentActionBusy.value = true;
    pendingExperimentRetry.value.add(id);
    try {
      const { retryExperimentCell: retryCellApi } = await import("../api/history");
      await retryCellApi(activeExperimentId.value, id);
      return { ok: true };
    } catch (cause) {
      pendingExperimentRetry.value.delete(id);
      return { ok: false, error: cause instanceof Error ? cause.message : "Cell retry failed" };
    } finally {
      experimentActionBusy.value = false;
    }
  }

  async function cancelExperimentRun(): Promise<{ ok: boolean; error?: string }> {
    if (activeExperimentId.value === null) return { ok: false, error: "No active experiment" };
    if (experimentActionBusy.value) return { ok: false, error: "Another experiment action is in flight" };
    experimentActionBusy.value = true;
    try {
      const { cancelExperiment: cancelApi } = await import("../api/history");
      await cancelApi(activeExperimentId.value);
      return { ok: true };
    } catch (cause) {
      return { ok: false, error: cause instanceof Error ? cause.message : "Experiment cancel failed" };
    } finally {
      experimentActionBusy.value = false;
    }
  }

  async function resumeExperimentRun(): Promise<{ ok: boolean; error?: string }> {
    if (activeExperimentId.value === null) return { ok: false, error: "No active experiment" };
    if (experimentActionBusy.value) return { ok: false, error: "Another experiment action is in flight" };
    experimentActionBusy.value = true;
    try {
      const { resumeExperiment: resumeApi } = await import("../api/history");
      await resumeApi(activeExperimentId.value);
      return { ok: true };
    } catch (cause) {
      return { ok: false, error: cause instanceof Error ? cause.message : "Experiment resume failed" };
    } finally {
      experimentActionBusy.value = false;
    }
  }

  async function cancelRun(fetchImpl?: typeof fetch): Promise<void> {
    // Cancel is authoritative: the controller wins the terminal lock FIRST,
    // so any late success/progress/terminal event or late POST resolution
    // afterwards cannot resurrect the run. The registry cancel + backend
    // stop are best-effort notifications, not decisions.
    const id = runState.value.experimentId || runState.value.runId;
    runController.cancel();
    syncRunStateFromController("Run canceled");
    const opId = activeOperationId.value;
    activeOperationId.value = null;
    if (opId) {
      try {
        useOperationsStore().cancel(opId, "Run canceled");
      } catch {
        /* registry is terminal-frozen; best-effort */
      }
    }
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
    // Run-local transient display (id only; the entity lives in
    // historyStore). Terminal decisions stay with the controller: a late
    // success after cancel/failure cannot resurrect the run.
    rememberGeneration(generationId);
    if (!runController.isTerminal()) {
      runController.applySnapshot("completed");
    }
    syncRunStateFromController();
  }

  function noteFailed(message: string): void {
    // Terminal lock enforced: duplicate/late failures after a first
    // terminal decision are ignored, never regressed.
    if (!runController.isTerminal()) {
      runController.applyLocalError(message);
    }
    syncRunStateFromController();
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
    activeExperimentId,
    experimentCells,
    experimentActionBusy,
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
    submitQueuedItem,
    enqueueCurrent,
    removeQueued,
    clearQueue,
    drainQueue,
    queueCompatibilityKey,
    setAxis,
    clearAxes,
    submitExperimentDef,
    applyExperimentStatus,
    applyExperimentEvent,
    retryExperimentCell,
    cancelExperimentRun,
    resumeExperimentRun,
    cancelRun,
    noteSucceeded,
    noteFailed,
  };
});
