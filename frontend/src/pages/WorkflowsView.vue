<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { Database, Import, Layers, RefreshCw, Search, Star, WandSparkles, X } from "@lucide/vue";
import { useWorkflowsStore } from "../stores/workflows";
import { useInfrastructureStore } from "../stores/infrastructure";
import { WIZARD_STEPS, requiredWizardRoles, optionalWizardRoles, wizardRoleDef, wizardRoleSuggestions } from "../api/workflows";
import StudioButton from "../components/StudioButton.vue";
import { studioPageClass } from "../components/studioPanels";

const workflows = useWorkflowsStore();
const infrastructure = useInfrastructureStore();
const query = ref("");
const tab = ref<"workflows" | "models">("workflows");
const controlLabel = ref("");
const wizardMessage = ref("");
const editName = ref("");
const editFolder = ref("");
const importText = ref("");
const importError = ref("");
const showImport = ref(false);
const presetName = ref("");
const guidanceSha = ref("");
const guidanceMode = ref("txt2img");
const mappingText = ref("");
const showManifestImport = ref(false);

const wizardStepIndex = computed(() => Math.max(0, WIZARD_STEPS.indexOf(workflows.wizardDraft?.step ?? "feature-type")));
const wizardStep = computed(() => WIZARD_STEPS[wizardStepIndex.value]);

// Display-only row secondary: folder, else first tag. Internal ids and
// "No folder" placeholders never surface in the library.
function workflowSecondary(workflow: { folder?: string; tags?: string[] }): string {
  if (workflow.folder) return workflow.folder;
  const tag = (workflow.tags ?? []).find((entry) => !!entry);
  return tag ?? "";
}

// Human version label for the detail header. Raw version hashes stay out of
// the default presentation (version switching lives in More actions).
const selectedVersionLabel = computed(() => {
  const version = workflows.selectedVersion as unknown as Record<string, unknown> | null;
  const numeric = version?.version;
  return typeof numeric === "number" ? `Version ${numeric}` : "";
});

// Human mapping summary for the detail surface. Reads the mapping defensively:
// newer drafts nest under .bindings, persisted legacy mappings are flat
// ({ prompt: {...} }) — both count as bindings except known meta keys.
// Raw JSON stays behind the Edit toggle and never dumps into the workspace.
const MAPPING_META_KEYS = new Set(["output", "outputBinding", "controls", "featureType", "step", "version"]);
const mappingSummary = computed(() => {
  const mapping = workflows.mapping as unknown as Record<string, unknown> | null;
  if (!mapping) return { configured: false, bindings: 0, controls: 0 };
  const nested = mapping.bindings;
  const bindings = nested && typeof nested === "object"
    ? Object.keys(nested).length
    : Object.keys(mapping).filter((key) => !MAPPING_META_KEYS.has(key)).length;
  const controls = mapping.controls;
  return {
    configured: true,
    bindings,
    controls: Array.isArray(controls) ? controls.length : 0,
  };
});

const showMappingEditor = ref(false);

// Display labels for the four engine steps. The WIZARD_STEPS values are the
// persisted engine contract (draft resume, graph binding) and never change;
// only these labels are presentational: 1 Feature / 2 Bindings / 3 Controls.
const WIZARD_STEP_LABELS: Record<string, string> = {
  "feature-type": "Feature",
  "required-bindings": "Bindings",
  "exposed-controls": "Controls",
  details: "Review",
};

const wizardStepLabel = computed(() => WIZARD_STEP_LABELS[wizardStep.value] ?? wizardStep.value);

const requiredBindingRoles = computed(() => requiredWizardRoles(workflows.wizardDraft?.featureType ?? "t2i"));
const optionalBindingRoles = computed(() => optionalWizardRoles(workflows.wizardDraft?.featureType ?? "t2i"));

// Display-only binding helpers. The graph-binding engine (capture callbacks,
// confirmed flags, draft shape) is untouched; these just read it for the
// Bound / Pending success treatment.
function bindingTarget(binding: unknown): string {
  if (!binding || typeof binding !== "object") return "graph target";
  const record = binding as Record<string, unknown>;
  return String(record.nodeTitle ?? record.target ?? record.nodeId ?? "graph target");
}

function bindingConfirmed(binding: unknown): boolean {
  if (!binding || typeof binding !== "object") return false;
  return (binding as Record<string, unknown>).confirmed === true;
}

onMounted(async () => {
  await Promise.all([workflows.initialize(), infrastructure.initialize()]);
  // Reload resume: a pending bounded draft reopens the wizard at its saved
  // step. Ordinary navigation never triggers this path.
  await workflows.maybeResumeWizard().catch(() => false);
});

async function search() {
  workflows.query = query.value;
  await workflows.loadList();
}

async function selectWorkflow(id: string) {
  await workflows.selectWorkflow(id);
  const wf = workflows.selectedWorkflow;
  editName.value = String(wf?.name ?? "");
  editFolder.value = String(wf?.folder ?? "");
}

function openWizard() {
  workflows.openWizard();
  window.__comfymodalSetGraphInteractionEnabled?.(true);
}

function closeWizard() {
  void window.__comfymodalCancelStudioGraphBinding?.();
  workflows.closeWizard();
  window.__comfymodalSetGraphInteractionEnabled?.(false);
}

// The inspector is body-teleported, so its own @keydown.esc only fires with
// focus inside it — but binding requires clicking the graph (focus leaves).
// While the wizard owns the session, a document-level Escape closes it from
// anywhere; portalled controls that already handled the key (defaultPrevented)
// win. The host capture listener defers to us via the data-state marker.
function onDocumentKeydown(event: KeyboardEvent) {
  if (event.key !== "Escape" || event.defaultPrevented) return;
  if (!workflows.wizardOpen) return;
  event.stopPropagation();
  closeWizard();
}

watch(
  () => workflows.wizardOpen,
  (open) => {
    if (open) document.addEventListener("keydown", onDocumentKeydown);
    else document.removeEventListener("keydown", onDocumentKeydown);
  },
);

onUnmounted(() => {
  document.removeEventListener("keydown", onDocumentKeydown);
});

async function captureBinding(bindingKey: string) {
  const label = wizardRoleDef(bindingKey).label;
  if (window.__comfymodalBeginStudioGraphBinding) {
    wizardMessage.value = `Click a node in the ComfyUI graph for ${label}…`;
    await window.__comfymodalBeginStudioGraphBinding({
      bindingKey,
      label,
      allowOutput: false,
      onCapture: (result) => {
        workflows.updateWizard({ bindings: { ...(workflows.wizardDraft?.bindings ?? {}), [bindingKey]: { ...result, confirmed: true } } });
        wizardMessage.value = `${label} bound to ${String(result.nodeTitle ?? result.nodeId ?? "graph target")}`;
      },
      onCancel: (reason) => { wizardMessage.value = reason; },
    });
    return;
  }
  workflows.updateWizard({ bindings: { ...(workflows.wizardDraft?.bindings ?? {}), [bindingKey]: { target: bindingKey, confirmed: true } } });
  wizardMessage.value = `${label} recorded without a live graph`;
}

function roleBinding(roleKey: string): unknown {
  const bindings = (workflows.wizardDraft?.bindings ?? {}) as Record<string, unknown>;
  return bindings[roleKey] ?? null;
}

async function viewRoleBinding(roleKey: string) {
  const binding = roleBinding(roleKey) as Record<string, unknown> | null;
  const nodeId = binding ? String(binding.nodeId ?? binding.node_id ?? "") : "";
  if (!nodeId || !window.__comfymodalViewStudioGraphNode) {
    wizardMessage.value = "Open the graph to locate this target";
    return;
  }
  const result = (await window.__comfymodalViewStudioGraphNode(nodeId).catch(() => null)) as { ok?: boolean; reason?: string } | null;
  wizardMessage.value = result && result.ok !== false
    ? `Centered ${wizardRoleDef(roleKey).label} on the graph`
    : String((result as { reason?: string } | null)?.reason || "Node not found on the canvas");
}

interface RoleSuggestion {
  nodeId: string | number;
  nodeType?: string;
  nodeTitle?: string;
  widgetName?: string;
}

const roleSuggestions = ref<Record<string, RoleSuggestion[]>>({});

async function suggestRoleBinding(roleKey: string) {
  if (!window.__comfymodalSuggestStudioGraphTargets) {
    wizardMessage.value = "Suggestions need the live graph";
    return;
  }
  const patterns = wizardRoleSuggestions(roleKey);
  if (!patterns.length) {
    wizardMessage.value = `No static hint for ${wizardRoleDef(roleKey).label} — capture against the exact input`;
    return;
  }
  try {
    const found = (await window.__comfymodalSuggestStudioGraphTargets(patterns, 3)) as RoleSuggestion[];
    roleSuggestions.value = { ...roleSuggestions.value, [roleKey]: Array.isArray(found) ? found : [] };
    if (!roleSuggestions.value[roleKey].length) wizardMessage.value = "No matching nodes on this graph";
  } catch {
    wizardMessage.value = "Suggestion lookup failed";
  }
}

async function viewSuggestedNode(nodeId: string | number) {
  if (!window.__comfymodalViewStudioGraphNode) return;
  await window.__comfymodalViewStudioGraphNode(String(nodeId)).catch(() => null);
}

// Save gate: required roles for the chosen feature type plus the output
// binding must be confirmed before the mapping can be saved.
const missingRequiredLabels = computed(() => {
  const featureType = workflows.wizardDraft?.featureType ?? "t2i";
  const missing = requiredWizardRoles(featureType)
    .filter((key) => !bindingConfirmed(roleBinding(key)))
    .map((key) => wizardRoleDef(key).label);
  if (!bindingConfirmed(workflows.wizardDraft?.outputBinding)) missing.push("Output");
  return missing;
});

async function captureOutput() {
  if (window.__comfymodalBeginStudioGraphBinding) {
    wizardMessage.value = "Click the output node in the ComfyUI graph…";
    await window.__comfymodalBeginStudioGraphBinding({
      bindingKey: "output",
      label: "output",
      allowOutput: true,
      onCapture: (result) => {
        workflows.updateWizard({ outputBinding: { ...result, confirmed: true } });
        wizardMessage.value = `Output bound to ${String(result.nodeTitle ?? result.nodeId ?? "graph target")}`;
      },
      onCancel: (reason) => { wizardMessage.value = reason; },
    });
    return;
  }
  workflows.updateWizard({ outputBinding: { target: "SaveImage.images", confirmed: true } });
  wizardMessage.value = "Output binding recorded";
}

async function saveWizard() {
  if (missingRequiredLabels.value.length > 0) {
    wizardMessage.value = `Still needed: ${missingRequiredLabels.value.join(", ")}`;
    return;
  }
  wizardMessage.value = "";
  try {
    await workflows.saveWizardMapping();
    wizardMessage.value = "Mapping saved";
    // Success closes the wizard inside the store without going through
    // closeWizard(): restore the normal inert Studio modal here, mirroring
    // the explicit-close path above.
    void window.__comfymodalCancelStudioGraphBinding?.();
    window.__comfymodalSetGraphInteractionEnabled?.(false);
  } catch (cause) {
    wizardMessage.value = cause instanceof Error ? cause.message : "Save failed";
  }
}

function nextWizardStep() {
  const next = WIZARD_STEPS[Math.min(WIZARD_STEPS.length - 1, wizardStepIndex.value + 1)];
  workflows.setWizardStep(next);
}

function previousWizardStep() {
  const previous = WIZARD_STEPS[Math.max(0, wizardStepIndex.value - 1)];
  workflows.setWizardStep(previous);
}

function addControl() {
  if (!controlLabel.value.trim()) return;
  const controls = [...(workflows.wizardDraft?.controls ?? []), { label: controlLabel.value.trim(), enabled: true }];
  workflows.updateWizard({ controls });
  controlLabel.value = "";
}

function presetKey(preset: unknown): string {
  const record = (preset ?? {}) as Record<string, unknown>;
  return String(record.preset_id || record.id || "");
}

const renamingPresetId = ref("");
const renameDraft = ref("");
const presetCopyTargets = ref<Record<string, string>>({});

function startPresetRename(preset: unknown) {
  renamingPresetId.value = presetKey(preset);
  renameDraft.value = String((preset as Record<string, unknown>).name || "");
}

async function savePresetRename(preset: unknown) {
  const id = presetKey(preset);
  const name = renameDraft.value.trim();
  renamingPresetId.value = "";
  if (!id || !name) return;
  await workflows.savePreset(id, { name }).catch(() => undefined);
}

async function copyPresetToVersion(preset: unknown) {
  const id = presetKey(preset);
  const target = presetCopyTargets.value[id];
  if (!id || !target) return;
  await workflows.copyPresetForward(id, target).catch(() => undefined);
}

const guidanceResult = ref<unknown>(null);

async function loadGuidanceEntry() {
  guidanceResult.value = null;
  try {
    guidanceResult.value = await workflows.loadGuidance(guidanceSha.value, guidanceMode.value);
  } catch {
    // Errors surface through store error state.
  }
}

async function removeGuidanceEntry() {
  if (!guidanceSha.value.trim()) return;
  await workflows.removeGuidance(guidanceSha.value.trim(), guidanceMode.value).catch(() => undefined);
  guidanceResult.value = null;
}

const manifestText = ref("");
const manifestError = ref("");

async function previewManifest() {
  manifestError.value = "";
  try {
    await workflows.previewManifestImport(JSON.parse(manifestText.value || "{}") as Record<string, unknown>);
  } catch (cause) {
    manifestError.value = cause instanceof Error ? cause.message : "Preview failed";
  }
}

async function commitManifest() {
  manifestError.value = "";
  try {
    await workflows.commitManifestImport(JSON.parse(manifestText.value || "{}") as Record<string, unknown>);
    manifestText.value = "";
  } catch (cause) {
    manifestError.value = cause instanceof Error ? cause.message : "Import failed";
  }
}

async function doImport() {
  importError.value = "";
  try {
    const body = JSON.parse(importText.value) as Record<string, unknown>;
    await workflows.importNewWorkflow(body);
    importText.value = "";
  } catch (cause) {
    importError.value = cause instanceof Error ? cause.message : "Import failed";
  }
}

async function saveMetadata() {
  await workflows.updateMetadata({ name: editName.value, folder: editFolder.value }).catch(() => undefined);
}

async function saveMappingEdit() {
  try {
    await workflows.saveMapping(JSON.parse(mappingText.value || "{}") as Record<string, unknown>);
  } catch {
    // Validation errors surface through store error state.
  }
}

interface DependencyRow {
  key: string;
  filename: string;
  folder: string;
  state: string;
  nonessential: boolean;
  hasSource: boolean;
  message: string;
  raw: Record<string, unknown>;
}

interface DependencyNodeRow {
  key: string;
  name: string;
  state: string;
  message: string;
  raw: Record<string, unknown>;
}

const dependencyPayload = computed(() => (workflows.dependencies ?? {}) as Record<string, unknown>);

const dependencyModelRows = computed<DependencyRow[]>(() => {
  const raw = dependencyPayload.value.models;
  if (!Array.isArray(raw)) return [];
  const nonessential = new Set(
    Array.isArray((dependencyPayload.value.nonessential_keys ?? dependencyPayload.value.nonessential) as unknown[])
      ? ((dependencyPayload.value.nonessential_keys ?? dependencyPayload.value.nonessential) as unknown[]).map(String)
      : [],
  );
  return raw
    .filter((item): item is Record<string, unknown> => !!item && typeof item === "object")
    .map((item, index) => {
      const key = String(item.key || item.filename || `model-${index}`);
      const sourceUrls = Array.isArray(item.source_urls) ? item.source_urls : [];
      return {
        key,
        filename: String(item.filename || key),
        folder: String(item.folder || ""),
        state: String(item.state || "unknown"),
        nonessential: nonessential.has(key),
        hasSource: sourceUrls.length > 0 || typeof item.remote_model === "object",
        message: workflows.dependencyInstallMessage[key] ?? "",
        raw: item,
      };
    })
    // Problems first: missing rows above the quiet installed bulk.
    .sort((a, b) => (a.state === "missing" ? 0 : 1) - (b.state === "missing" ? 0 : 1));
});

const dependencyNodeRows = computed<DependencyNodeRow[]>(() => {
  const raw = dependencyPayload.value.custom_nodes;
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((item): item is Record<string, unknown> => !!item && typeof item === "object")
    .map((item, index) => {
      const key = String(item.name || item.cnr_id || `node-${index}`);
      return {
        key,
        name: String(item.name || key),
        state: String(item.state || "unknown"),
        message: workflows.dependencyInstallMessage[key] ?? "",
        raw: item,
      };
    });
});

const dependencySummaryLine = computed(() => {
  if (!workflows.dependencies) return "not loaded";
  const modelRows = dependencyModelRows.value;
  const nodeRows = dependencyNodeRows.value;
  const requiredMissing = [
    ...modelRows.filter((row) => row.state === "missing" && !row.nonessential),
    ...nodeRows.filter((row) => row.state === "missing"),
  ].length;
  const optionalMissing = modelRows.filter((row) => row.state === "missing" && row.nonessential).length;
  const installed = [
    ...modelRows.filter((row) => row.state === "installed" || row.state === "ready"),
    ...nodeRows.filter((row) => row.state === "installed"),
  ].length;
  // The backend summary excludes nonessential rows from its missing count,
  // so derive truth from the visible rows: required-missing gates readiness,
  // optional-missing is reported explicitly instead of contradicting it.
  if (requiredMissing > 0) return `${installed} installed · ${requiredMissing} missing · attention`;
  if (optionalMissing > 0) return `${installed} installed · ${optionalMissing} optional missing · ready`;
  if (!modelRows.length && !nodeRows.length) return "no requirements";
  return `${installed} installed · ready`;
});

const runnableText = computed(() => {
  const state = workflows.versionState as Record<string, unknown> | null;
  if (state && typeof state.runnable === "boolean") {
    return state.runnable ? "Runnable" : "Not runnable — resolve dependencies";
  }
  const version = workflows.selectedVersion as unknown as Record<string, unknown> | null;
  if (version && typeof version.runnable === "boolean") {
    return version.runnable ? "Runnable" : "Not runnable — resolve dependencies";
  }
  return "";
});

const runnableOk = computed(() => runnableText.value === "Runnable");

async function toggleNonessential(key: string, value: boolean) {
  const current = new Set(
    dependencyModelRows.value.filter((row) => row.nonessential).map((row) => row.key),
  );
  if (value) current.add(key);
  else current.delete(key);
  await workflows.markNonessential([...current]).catch(() => undefined);
}

async function installDependencyModel(row: DependencyRow) {
  const source = row.raw.remote_model && typeof row.raw.remote_model === "object"
    ? (row.raw.remote_model as Record<string, unknown>)
    : row.raw;
  const url = String(source.url || source.download_url || "");
  const payload: Record<string, unknown> = url
    ? { url, filename: row.filename, save_path: row.folder }
    : { filename: row.filename, folder: row.folder };
  try {
    await infrastructure.installModel(payload);
  } catch {
    // Errors surface through the operations registry + infrastructure error.
  }
}

// Per-row explicit source URL for source-less missing rows (legacy parity:
// the URL goes to the existing backend install routes; never auto-fetched).
const rowSourceUrls = ref<Record<string, string>>({});

function modelTarget(row: DependencyRow): { url: string; savePath: string; viaManager: boolean } {
  return workflows.modelInstallTarget(row.raw);
}

function rowSourceUrl(row: DependencyRow): string {
  const sources = Array.isArray(row.raw.source_urls) ? row.raw.source_urls : [];
  return sources.map(String).find(Boolean) ?? "";
}

async function queueDependencyModel(row: DependencyRow, url: string) {
  const target = url.trim();
  if (!target) return;
  workflows.dependencyInstallMessage[row.key] = "Queueing…";
  try {
    await infrastructure.installModelRequest({ url: target, filename: row.filename, save_path: row.folder });
    workflows.dependencyInstallMessage[row.key] = "Queued for download";
  } catch (cause) {
    workflows.dependencyInstallMessage[row.key] = cause instanceof Error ? cause.message : "Queue failed";
  }
}

async function installDependencyModelUrl(row: DependencyRow, url: string) {
  const target = url.trim();
  if (!target) return;
  try {
    await infrastructure.installModel({ url: target, filename: row.filename, save_path: row.folder });
  } catch {
    // Errors surface through the operations registry + infrastructure error.
  }
}

// Contextual handoff: a dependency row opens the shared Model Library tab
// with the search prefilled to that filename. Filter on the canonical list —
// no second model-management implementation.
function findInLibrary(query: string) {
  workflows.libraryQuery = query;
  tab.value = "models";
}

// ── Model Library browser (shared infrastructure inventory) ──
const libraryType = ref("");
const libraryDetailKey = ref("");
const libraryNotes = ref<Record<string, string>>({});

const libraryModelTypes = computed(() => {
  const types = new Set<string>();
  for (const item of infrastructure.models) {
    const type = String(item.model_type || item.folder || "");
    if (type) types.add(type);
  }
  return [...types].sort();
});

const filteredLibraryModels = computed(() => {
  const query = workflows.libraryQuery.trim().toLowerCase();
  return infrastructure.models.filter((item) => {
    if (libraryType.value && String(item.model_type || item.folder || "") !== libraryType.value) return false;
    if (!query) return true;
    const haystack = [item.display_name, item.filename, item.folder, item.model_type, item.provider]
      .map((part) => String(part || "").toLowerCase()).join(" ");
    return haystack.includes(query);
  });
});

const filteredLibraryNodes = computed(() => {
  const query = workflows.libraryQuery.trim().toLowerCase();
  if (!query) return infrastructure.customNodes;
  return infrastructure.customNodes.filter((node) => {
    const classes = Array.isArray(node.classes) ? node.classes.map(String).join(" ") : "";
    const haystack = [node.title, node.name, node.id, classes].map((part) => String(part || "").toLowerCase()).join(" ");
    return haystack.includes(query);
  });
});

function formatBytes(value: unknown): string | null {
  const bytes = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(bytes) || bytes <= 0) return null;
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let scaled = bytes / 1024;
  let unit = 0;
  while (scaled >= 1024 && unit < units.length - 1) {
    scaled /= 1024;
    unit += 1;
  }
  return `${scaled >= 100 ? Math.round(scaled) : scaled.toFixed(1)} ${units[unit]}`;
}

async function saveLibraryModelMeta(model: Record<string, unknown>) {
  const key = String(model.model_id || model.filename || "");
  const note = (libraryNotes.value[key] ?? "").trim();
  if (!model.model_id || !note) return;
  try {
    await infrastructure.updateModelNotes(String(model.model_id), { notes: note });
    libraryNotes.value[key] = "";
  } catch {
    // Errors surface through the operations registry + infrastructure error.
  }
}

async function installDependencyNode(row: DependencyNodeRow) {
  await workflows.installDependencyNode(row.raw);
}
</script>

<template>
  <section :class="studioPageClass()" data-testid="vue-page-workflows">
    <!-- SETUP MODE: the Workflows editor is parked (v-else below) while the
      wizard owns the session — the ComfyUI graph is primary, the teleported
      inspector is its panel. Exit via the inspector close or Escape, which
      restore normal Studio through the existing closeWizard path. -->
    <template v-if="!workflows.wizardOpen">
    <!-- Page toolbar: title + search + filters + import. Flush on the page
      background — no hero band, no card. -->
    <div class="cmst:flex cmst:flex-wrap cmst:items-end cmst:justify-between cmst:gap-3">
      <div>
        <h1 class="cmst-type-view">Workflows</h1>
        <p class="cmst:mt-0.5 cmst:text-[13px] cmst:text-cmst-muted">
          {{ workflows.workflows.length }} workflows
        </p>
      </div>
      <div class="cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2">
        <select
          v-model="workflows.tagFilter"
          class="cmst-field"
          aria-label="Filter by tag"
          @change="workflows.loadList()"
        >
          <option value="">All tags</option>
        </select>
        <label class="cmst:flex cmst:cursor-pointer cmst:items-center cmst:gap-1.5 cmst:text-[13px] cmst:text-cmst-muted">
          <input v-model="workflows.favoritesOnly" type="checkbox" @change="workflows.loadList()" />
          Favorites
        </label>
        <StudioButton size="sm" variant="outline" data-testid="vue-workflow-import-toggle" @click="showImport = !showImport">
          <Import class="cmst:size-4" aria-hidden="true" />Import
        </StudioButton>
      </div>
    </div>

    <div v-if="showImport" class="cmst:flex cmst:flex-col cmst:gap-2 cmst:border-y cmst:border-solid cmst:border-cmst-border cmst:py-3">
      <label class="cmst:text-[13px] cmst:font-medium" for="vue-workflow-import-text">Import workflow JSON</label>
      <textarea
        id="vue-workflow-import-text"
        v-model="importText"
        rows="3"
        class="cmst-field cmst:font-mono cmst:text-xs"
        placeholder='{"name": "...", "static_graph": {...}}'
        data-testid="vue-workflow-import-input"
      />
      <p v-if="importError" class="cmst:text-xs cmst:text-cmst-danger" role="alert">{{ importError }}</p>
      <div><StudioButton size="sm" data-testid="vue-workflow-import" @click="doImport">Import</StudioButton></div>
    </div>

    <div class="cmst:grid cmst:grid-cols-1 cmst:gap-6 cmst:lg:grid-cols-[300px_minmax(0,1fr)]">
        <!-- Library rail: search + filter + dense rows. -->
        <div class="cmst:min-w-0">
          <div class="cmst:relative">
            <Search class="cmst:pointer-events-none cmst:absolute cmst:left-2.5 cmst:top-1/2 cmst:size-4 cmst:-translate-y-1/2 cmst:text-cmst-muted" aria-hidden="true" />
            <input
              v-model="query"
              class="cmst-field cmst:w-full cmst:pl-8"
              placeholder="Search workflows"
              aria-label="Search workflows"
              @keyup.enter="search"
            />
          </div>
          <div class="cmst:mt-2 cmst:flex cmst:items-center cmst:justify-between cmst:gap-2">
            <div class="cmst-seg" role="tablist" aria-label="Workflows or shared inventory">
              <button type="button" role="tab" class="cmst-seg-btn" :data-active="tab === 'workflows'" :aria-selected="tab === 'workflows'" @click="tab = 'workflows'">
                <Layers class="cmst:size-4" aria-hidden="true" />Workflows
              </button>
              <button type="button" role="tab" class="cmst-seg-btn" :data-active="tab === 'models'" :aria-selected="tab === 'models'" @click="tab = 'models'">
                <Database class="cmst:size-4" aria-hidden="true" />Models / Nodes
              </button>
            </div>
            <StudioButton size="sm" variant="ghost" aria-label="Refresh workflows" @click="workflows.loadList()">
              <RefreshCw class="cmst:size-4" aria-hidden="true" />
            </StudioButton>
          </div>
          <div v-if="tab === 'workflows'" role="listbox" aria-label="Workflows" class="cmst:mt-2 cmst:min-w-0">
          <button
            v-for="workflow in workflows.workflows"
            :key="workflow.workflow_id"
            type="button"
            role="option"
            class="cmst-object-row"
            :aria-selected="workflows.selectedWorkflow?.workflow_id === workflow.workflow_id"
            :data-testid="`vue-workflow-${workflow.workflow_id}`"
            @click="selectWorkflow(workflow.workflow_id)"
          >
            <span class="cmst:flex cmst:items-center cmst:gap-1.5">
              <Star
                v-if="workflow.favorite"
                class="cmst:size-3.5 cmst:shrink-0 cmst:fill-cmst-primary cmst:text-cmst-primary"
                aria-label="Favorite"
              />
              <strong class="cmst-type-object cmst:truncate">{{ workflow.name || "Untitled workflow" }}</strong>
            </span>
            <span v-if="workflowSecondary(workflow)" class="cmst-type-meta cmst:mt-0.5 cmst:block cmst:truncate">
              {{ workflowSecondary(workflow) }}
            </span>
          </button>
          <p v-if="!workflows.workflows.length" class="cmst:py-4 cmst:text-[13px] cmst:text-cmst-muted">
            No workflows returned by the server.
          </p>
          </div>
        </div>

      <template v-if="tab === 'workflows'">
        <!-- Detail surface: flat sections on hairlines, not nested cards. -->
        <div v-if="workflows.selectedWorkflow" class="cmst:w-full cmst:min-w-0 cmst:max-w-4xl">
          <div class="cmst:flex cmst:flex-wrap cmst:items-start cmst:justify-between cmst:gap-3">
            <div class="cmst:min-w-0">
              <h2 class="cmst-type-view cmst:truncate">{{ workflows.selectedWorkflow.name }}</h2>
              <p v-if="selectedVersionLabel" class="cmst-type-meta cmst:mt-0.5">
                {{ selectedVersionLabel }}
              </p>
              <p
                v-if="runnableText"
                class="cmst:mt-1.5 cmst:flex cmst:items-center cmst:gap-1.5 cmst:text-xs"
                :class="runnableOk ? 'cmst:text-cmst-ok' : 'cmst:text-cmst-warn'"
                data-testid="vue-version-runnable"
              >
                <span
                  class="cmst:inline-block cmst:size-1.5 cmst:rounded-full"
                  :class="runnableOk ? 'cmst:bg-cmst-ok' : 'cmst:bg-cmst-warn'"
                  aria-hidden="true"
                />
                {{ runnableText }}
              </p>
            </div>
            <div class="cmst:flex cmst:items-center cmst:gap-1.5">
              <button
                type="button"
                :data-testid="`vue-workflow-favorite-${workflows.selectedWorkflow.workflow_id}`"
                :aria-pressed="!!workflows.selectedWorkflow.favorite"
                aria-label="Toggle favorite"
                class="cmst:rounded-md cmst:p-1.5 cmst:hover:bg-cmst-hover"
                :class="workflows.selectedWorkflow.favorite ? 'cmst:text-cmst-primary' : 'cmst:text-cmst-muted'"
                @click="workflows.toggleFavorite(workflows.selectedWorkflow!.workflow_id, !workflows.selectedWorkflow!.favorite)"
              >
                <Star
                  class="cmst:size-4"
                  :class="workflows.selectedWorkflow.favorite ? 'cmst:fill-cmst-primary' : ''"
                  aria-hidden="true"
                />
              </button>
              <StudioButton size="sm" @click="openWizard">
                <WandSparkles class="cmst:size-4" aria-hidden="true" />Setup workflow
              </StudioButton>
              <details class="cmst:relative">
                <summary
                  class="cmst:cursor-pointer cmst:list-none cmst:rounded-md cmst:px-2 cmst:py-1.5 cmst:text-[13px] cmst:text-cmst-muted cmst:hover:bg-cmst-hover cmst:hover:text-cmst-fg [&::-webkit-details-marker]:cmst:hidden"
                  aria-label="More workflow actions"
                >
                  ···
                </summary>
                <div class="cmst:absolute cmst:right-0 cmst:z-20 cmst:mt-1 cmst:flex cmst:w-52 cmst:flex-col cmst:gap-2 cmst:rounded-lg cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-raised cmst:p-3 cmst:shadow-[var(--cmst-shadow-overlay)]">
                  <label class="cmst-field-label">Version
                    <select
                      :value="workflows.selectedVersion?.workflow_version_id ?? ''"
                      class="cmst-field cmst:w-full"
                      aria-label="Select version"
                      data-testid="vue-version-select"
                      @change="workflows.selectVersion(($event.target as HTMLSelectElement).value)"
                    >
                      <option v-for="version in workflows.versions" :key="version.workflow_version_id" :value="version.workflow_version_id">
                        v{{ version.version ?? version.workflow_version_id }}
                      </option>
                    </select>
                  </label>
                  <StudioButton size="sm" variant="outline" data-testid="vue-version-capture" @click="workflows.captureVersion({})">
                    Capture version
                  </StudioButton>
                  <StudioButton size="sm" variant="outline" data-testid="vue-workflow-delete" @click="workflows.deleteSelectedWorkflow()">
                    Delete workflow
                  </StudioButton>
                </div>
              </details>
            </div>
          </div>

          <div class="cmst:mt-3 cmst:rounded-xl cmst:bg-cmst-surface cmst:p-4">
            <div class="cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-2">
              <label class="cmst-field-label">Name<input v-model="editName" class="cmst-field" /></label>
              <label class="cmst-field-label">Folder<input v-model="editFolder" class="cmst-field" /></label>
            </div>
            <div class="cmst:mt-3">
              <StudioButton size="sm" variant="secondary" data-testid="vue-workflow-save-meta" @click="saveMetadata">
                Save metadata
              </StudioButton>
            </div>
          </div>

          <section aria-label="Mapping" class="cmst:mt-6">
            <h3 class="cmst-type-section">Mapping</h3>
            <p class="cmst-type-meta cmst:mt-0.5">
              {{ mappingSummary.configured ? `${mappingSummary.bindings} bindings · ${mappingSummary.controls} controls` : "not configured" }}
            </p>
            <div class="cmst:mt-2 cmst:flex cmst:gap-1.5">
              <StudioButton size="sm" variant="ghost" @click="workflows.loadMappingCandidates()">Load candidates</StudioButton>
              <StudioButton size="sm" variant="ghost" @click="showMappingEditor = !showMappingEditor">{{ showMappingEditor ? "Hide raw mapping" : "Edit raw mapping" }}</StudioButton>
            </div>
            <div v-if="showMappingEditor" class="cmst:mt-2">
              <pre v-if="workflows.mappingCandidates" class="cmst:mt-2 cmst:max-h-32 cmst:overflow-auto cmst:rounded cmst:bg-cmst-matte cmst:p-2 cmst:font-mono cmst:text-xs cmst:text-cmst-secondary-text">{{ JSON.stringify(workflows.mappingCandidates, null, 1).slice(0, 800) }}</pre>
              <textarea v-model="mappingText" rows="3" class="cmst-field cmst:mt-2 cmst:w-full cmst:font-mono cmst:text-xs" placeholder='{"bindings": {...}}' />
              <div class="cmst:mt-1.5"><StudioButton size="sm" variant="secondary" data-testid="vue-mapping-save" @click="saveMappingEdit">Save mapping</StudioButton></div>
            </div>
          </section>

          <section aria-label="Dependencies" class="cmst:mt-6" data-testid="vue-dependencies">
            <h3 class="cmst-type-section">Dependencies</h3>
            <p class="cmst-type-meta cmst:mt-0.5">{{ dependencySummaryLine }}</p>
            <ul class="cmst:mt-2 cmst:flex cmst:max-h-56 cmst:flex-col cmst:gap-1 cmst:overflow-auto">
              <li
                v-for="row in dependencyModelRows"
                :key="`model-${row.key}`"
                class="cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-x-2 cmst:gap-y-1 cmst:rounded-md cmst:px-2 cmst:py-2 cmst:text-[13px] cmst:hover:bg-cmst-hover"
                data-testid="dependency-model-row"
              >
                <span
                  class="cmst:inline-block cmst:size-1.5 cmst:shrink-0 cmst:rounded-full"
                  :class="row.state === 'missing' ? 'cmst:bg-cmst-danger' : row.state === 'ready' || row.state === 'installed' ? 'cmst:bg-cmst-ok' : 'cmst:bg-cmst-muted'"
                  aria-hidden="true"
                />
                <span class="cmst:min-w-0 cmst:flex-1">{{ row.filename }} <span class="cmst:text-cmst-muted">({{ row.folder }})</span></span>
                <span class="cmst-type-meta" data-testid="dependency-model-state">{{ row.state }}</span>
                <label class="cmst:flex cmst:items-center cmst:gap-1 cmst:text-xs cmst:text-cmst-muted" title="Optional: skip this file when checking or installing requirements">
                  <input type="checkbox" :checked="row.nonessential" @change="toggleNonessential(row.key, ($event.target as HTMLInputElement).checked)" />
                  Optional
                </label>
                <template v-if="row.state === 'missing'">
                  <a
                    v-if="rowSourceUrl(row)"
                    :href="rowSourceUrl(row)"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="cmst:text-xs cmst:text-cmst-muted cmst:hover:text-cmst-fg"
                  >source</a>
                  <template v-if="modelTarget(row).url">
                    <StudioButton size="sm" variant="ghost" data-testid="dependency-model-install-now" :title="modelTarget(row).viaManager ? 'Manager catalog match' : 'Direct source'" @click="installDependencyModel(row)">Install now</StudioButton>
                    <StudioButton size="sm" variant="ghost" data-testid="dependency-model-queue" @click="queueDependencyModel(row, modelTarget(row).url)">Queue install</StudioButton>
                  </template>
                  <template v-else>
                    <input
                      v-model="rowSourceUrls[row.key]"
                      class="cmst-field cmst:w-44 cmst:max-w-full cmst:font-mono cmst:text-xs"
                      placeholder="Paste source URL"
                      :aria-label="`Source URL for ${row.filename}`"
                      :data-testid="`dependency-model-url-${row.key}`"
                    />
                    <StudioButton size="sm" variant="ghost" data-testid="dependency-model-install-url" @click="installDependencyModelUrl(row, rowSourceUrls[row.key] ?? '')">Install</StudioButton>
                  </template>
                  <StudioButton size="sm" variant="ghost" data-testid="dependency-model-find" @click="findInLibrary(row.filename)">Find in library</StudioButton>
                </template>
                <span v-if="row.message" class="cmst:w-full cmst:text-xs cmst:text-cmst-muted" data-testid="dependency-model-install-note">{{ row.message }}</span>
              </li>
              <li
                v-for="row in dependencyNodeRows"
                :key="`node-${row.key}`"
                class="cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-x-2 cmst:gap-y-1 cmst:rounded-md cmst:px-2 cmst:py-2 cmst:text-[13px] cmst:hover:bg-cmst-hover"
                data-testid="dependency-node-row"
              >
                <span
                  class="cmst:inline-block cmst:size-1.5 cmst:shrink-0 cmst:rounded-full"
                  :class="row.state === 'missing' ? 'cmst:bg-cmst-danger' : 'cmst:bg-cmst-ok'"
                  aria-hidden="true"
                />
                <span class="cmst:min-w-0 cmst:flex-1">{{ row.name }} · {{ row.state }}</span>
                <template v-if="row.state === 'missing'">
                  <StudioButton v-if="workflows.resolveNodePlan(row.raw).kind !== 'none'" size="sm" variant="ghost" data-testid="dependency-node-install-now" @click="installDependencyNode(row)">Install now</StudioButton>
                  <StudioButton size="sm" variant="ghost" data-testid="dependency-node-find" @click="findInLibrary(row.name)">Find in registry</StudioButton>
                </template>
                <span v-if="row.message" class="cmst:w-full cmst:text-xs cmst:text-cmst-muted" data-testid="dependency-node-install-note">{{ row.message }}</span>
              </li>
            </ul>
          </section>

          <section aria-label="Portability" class="cmst:mt-6">
            <h3 class="cmst-type-section">Portability</h3>
            <p class="cmst-type-meta cmst:mt-0.5">{{ workflows.portability ? "analyzed" : "not analyzed" }}</p>
            <div class="cmst:mt-2 cmst:flex cmst:gap-1.5">
              <StudioButton size="sm" variant="ghost" @click="workflows.recheckPortability()">Recheck</StudioButton>
              <StudioButton size="sm" variant="ghost" data-testid="vue-manifest-export" @click="workflows.exportManifest()">Export manifest</StudioButton>
              <StudioButton size="sm" variant="ghost" data-testid="vue-manifest-import-toggle" @click="showManifestImport = !showManifestImport">Import manifest</StudioButton>
            </div>
            <div v-if="showManifestImport" class="cmst:mt-2">
              <label class="cmst-field-label">Manifest JSON
                <textarea v-model="manifestText" rows="3" class="cmst-field cmst:w-full cmst:font-mono cmst:text-xs" placeholder='{"workflows": [...]}' data-testid="vue-manifest-import-input" />
              </label>
              <p v-if="manifestError" class="cmst:mt-1 cmst:text-xs cmst:text-cmst-danger" role="alert">{{ manifestError }}</p>
              <pre v-if="workflows.manifestPreview" class="cmst:mt-2 cmst:max-h-32 cmst:overflow-auto cmst:rounded cmst:bg-cmst-matte cmst:p-2 cmst:font-mono cmst:text-xs cmst:text-cmst-secondary-text" data-testid="vue-manifest-preview">{{ JSON.stringify(workflows.manifestPreview, null, 1).slice(0, 800) }}</pre>
              <div class="cmst:mt-1.5 cmst:flex cmst:gap-1.5">
                <StudioButton size="sm" variant="secondary" data-testid="vue-manifest-preview" @click="previewManifest">Preview import</StudioButton>
                <StudioButton size="sm" variant="ghost" data-testid="vue-manifest-commit" :disabled="!workflows.manifestPreview" @click="commitManifest">Commit import</StudioButton>
              </div>
            </div>
          </section>

          <section aria-label="Presets" class="cmst:mt-6">
            <h3 class="cmst-type-section">Presets</h3>
            <p class="cmst-type-meta cmst:mt-0.5">image-free configuration only</p>
            <div class="cmst:mt-2 cmst:flex cmst:gap-2">
              <input v-model="presetName" class="cmst-field cmst:flex-1" placeholder="Preset name" aria-label="Preset name" />
              <StudioButton size="sm" variant="secondary" data-testid="vue-preset-create" @click="workflows.createPreset({ name: presetName || 'Untitled', studio_state: {} }); presetName = ''">Create preset</StudioButton>
            </div>
            <ul class="cmst:mt-1">
              <li
                v-for="(preset, index) in workflows.presets"
                :key="index"
                class="cmst:rounded-md cmst:px-2 cmst:py-1.5 cmst:text-[13px] cmst:hover:bg-cmst-hover"
              >
                <div class="cmst:flex cmst:items-center cmst:justify-between cmst:gap-2">
                  <template v-if="renamingPresetId === presetKey(preset)">
                    <input
                      v-model="renameDraft"
                      class="cmst-field cmst:min-w-0 cmst:flex-1 cmst:text-xs"
                      :aria-label="`Rename ${String((preset as Record<string, unknown>).name || 'preset')}`"
                      @keyup.enter="savePresetRename(preset)"
                      @keyup.esc="renamingPresetId = ''"
                    />
                    <StudioButton size="sm" variant="secondary" @click="savePresetRename(preset)">Save</StudioButton>
                    <StudioButton size="sm" variant="ghost" @click="renamingPresetId = ''">Cancel</StudioButton>
                  </template>
                  <template v-else>
                    <span class="cmst:truncate">{{ String((preset as Record<string, unknown>).name || `preset ${index}`) }}</span>
                    <span class="cmst:flex cmst:shrink-0 cmst:gap-1">
                      <StudioButton size="sm" variant="ghost" @click="startPresetRename(preset)">Rename</StudioButton>
                      <StudioButton size="sm" variant="ghost" @click="workflows.duplicateCurrentPreset(presetKey(preset))">Duplicate</StudioButton>
                      <StudioButton size="sm" variant="ghost" @click="workflows.removePreset(presetKey(preset))">Delete</StudioButton>
                    </span>
                  </template>
                </div>
                <div v-if="workflows.versions.length > 1" class="cmst:mt-1 cmst:flex cmst:items-center cmst:gap-1.5">
                  <span class="cmst:text-xs cmst:text-cmst-muted">Copy to</span>
                  <select
                    v-model="presetCopyTargets[presetKey(preset)]"
                    class="cmst-field cmst:min-w-0 cmst:flex-1 cmst:text-xs"
                    :aria-label="`Copy ${String((preset as Record<string, unknown>).name || 'preset')} to version`"
                  >
                    <option
                      v-for="version in workflows.versions"
                      :key="version.workflow_version_id"
                      :value="version.workflow_version_id"
                    >v{{ version.version ?? version.workflow_version_id }}</option>
                  </select>
                  <StudioButton size="sm" variant="ghost" @click="copyPresetToVersion(preset)">Copy</StudioButton>
                </div>
              </li>
            </ul>
          </section>

          <section aria-label="Guidance mapping" class="cmst:mt-6">
            <h3 class="cmst-type-section">Guidance mapping</h3>
            <div class="cmst:mt-2 cmst:flex cmst:flex-wrap cmst:gap-2">
              <input v-model="guidanceSha" class="cmst-field cmst:flex-1" placeholder="model sha256" aria-label="Model sha256" />
              <select v-model="guidanceMode" class="cmst-field" aria-label="Guidance mode">
                <option value="txt2img">txt2img</option>
                <option value="i2i">i2i</option>
              </select>
              <StudioButton size="sm" variant="outline" data-testid="vue-guidance-load" @click="loadGuidanceEntry">Load</StudioButton>
              <StudioButton v-if="guidanceResult" size="sm" variant="ghost" data-testid="vue-guidance-remove" @click="removeGuidanceEntry">Remove</StudioButton>
            </div>
            <pre v-if="guidanceResult" class="cmst:mt-2 cmst:max-h-32 cmst:overflow-auto cmst:rounded cmst:bg-cmst-matte cmst:p-2 cmst:font-mono cmst:text-xs cmst:text-cmst-secondary-text" data-testid="vue-guidance-result">{{ JSON.stringify(guidanceResult, null, 1).slice(0, 800) }}</pre>
          </section>
        </div>
        <p v-else class="cmst:py-8 cmst:text-[13px] cmst:text-cmst-muted">
          Select a workflow to inspect its versions, mapping, and dependencies.
        </p>
      </template>

      <template v-else>
        <div class="cmst:min-w-0">
          <h2 class="cmst-type-view">Shared models &amp; nodes</h2>
          <p class="cmst:mt-0.5 cmst:text-[13px] cmst:text-cmst-muted">Models: {{ infrastructure.models.length }} · Custom nodes: {{ infrastructure.customNodes.length }}</p>
          <div class="cmst:mt-3 cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2">
            <div class="cmst:relative cmst:min-w-0 cmst:flex-1">
              <Search class="cmst:pointer-events-none cmst:absolute cmst:left-2.5 cmst:top-1/2 cmst:size-4 cmst:-translate-y-1/2 cmst:text-cmst-muted" aria-hidden="true" />
              <input
                v-model="workflows.libraryQuery"
                class="cmst-field cmst:w-full cmst:pl-8"
                placeholder="Search models and nodes"
                aria-label="Search models and nodes"
                data-testid="vue-library-search"
              />
            </div>
            <select v-model="libraryType" class="cmst-field" aria-label="Filter by model type" data-testid="vue-library-type">
              <option value="">All types</option>
              <option v-for="type in libraryModelTypes" :key="type" :value="type">{{ type }}</option>
            </select>
            <StudioButton size="sm" variant="outline" data-testid="vue-library-rescan" @click="infrastructure.rescanModelsNow(true)">Rescan</StudioButton>
            <StudioButton size="sm" variant="outline" data-testid="vue-library-refresh-nodes" @click="infrastructure.refreshCustomNodesNow()">Refresh nodes</StudioButton>
          </div>

          <h3 class="cmst-type-section cmst:mt-5">Models <span class="cmst-type-meta">{{ filteredLibraryModels.length }}</span></h3>
          <ul class="cmst:mt-1 cmst:flex cmst:max-h-80 cmst:flex-col cmst:gap-1 cmst:overflow-auto" data-testid="vue-library-models">
            <li v-for="model in filteredLibraryModels" :key="String(model.model_id || model.filename)" class="cmst:rounded-md cmst:px-2 cmst:py-2 cmst:hover:bg-cmst-hover" data-testid="vue-library-model-row">
              <button
                type="button"
                class="cmst:flex cmst:w-full cmst:cursor-pointer cmst:items-center cmst:gap-2 cmst:bg-transparent cmst:text-left"
                :aria-expanded="libraryDetailKey === `model:${String(model.model_id || model.filename)}`"
                @click="libraryDetailKey = libraryDetailKey === `model:${String(model.model_id || model.filename)}` ? '' : `model:${String(model.model_id || model.filename)}`"
              >
                <span class="cmst-min-w-0 cmst:flex-1 cmst:truncate cmst:text-[13px] cmst:font-medium">{{ String(model.display_name || model.filename) }}</span>
                <span class="cmst-type-meta cmst:shrink-0">{{ String(model.model_type || model.folder || "") }}</span>
              </button>
              <div v-if="libraryDetailKey === `model:${String(model.model_id || model.filename)}`" class="cmst:mt-1 cmst:pl-1 cmst:text-xs cmst:text-cmst-muted">
                <p class="cmst-type-meta">{{ String(model.filename) }} · {{ String(model.folder || "") }}<template v-if="formatBytes(model.size)"> · {{ formatBytes(model.size) }}</template><template v-if="model.hash"> · hash {{ String(model.hash).slice(0, 12) }}</template></p>
                <p v-if="model.provider || model.revision" class="cmst-type-meta cmst:mt-0.5">{{ [model.provider, model.revision].filter(Boolean).join(" · ") }}</p>
                <p v-if="(workflows.modelUsage[String(model.filename)] ?? []).length" class="cmst-type-meta cmst:mt-0.5" :title="(workflows.modelUsage[String(model.filename)] ?? []).join(', ')">
                  Used by {{ (workflows.modelUsage[String(model.filename)] ?? []).length }} workflow{{ (workflows.modelUsage[String(model.filename)] ?? []).length === 1 ? "" : "s" }}
                  <button type="button" class="cmst:ml-1 cmst:text-cmst-secondary-text cmst:hover:text-cmst-fg" @click="tab = 'workflows'">View</button>
                </p>
                <p v-if="Array.isArray(model.tags) && model.tags.length" class="cmst-type-meta cmst:mt-0.5">Tags: {{ (model.tags as unknown[]).map(String).join(", ") }}</p>
                <p v-if="model.notes" class="cmst:mt-0.5 cmst:text-[13px] cmst:text-cmst-secondary-text">{{ String(model.notes) }}</p>
                <div class="cmst:mt-1.5 cmst:flex cmst:flex-wrap cmst:gap-1.5">
                  <input v-model="libraryNotes[String(model.model_id || model.filename)]" class="cmst-field cmst:min-w-0 cmst:flex-1 cmst:text-xs" placeholder="Note" :aria-label="`Note for ${String(model.filename)}`" />
                  <StudioButton size="sm" variant="ghost" @click="saveLibraryModelMeta(model)">Save note</StudioButton>
                </div>
              </div>
            </li>
            <li v-if="!filteredLibraryModels.length" class="cmst:py-3 cmst:text-[13px] cmst:text-cmst-muted">No models match.</li>
          </ul>

          <h3 class="cmst-type-section cmst:mt-5">Custom nodes <span class="cmst-type-meta">{{ filteredLibraryNodes.length }}</span></h3>
          <ul class="cmst:mt-1 cmst:flex cmst:max-h-80 cmst:flex-col cmst:gap-1 cmst:overflow-auto" data-testid="vue-library-nodes">
            <li v-for="node in filteredLibraryNodes" :key="String(node.name || node.id)" class="cmst:rounded-md cmst:px-2 cmst:py-2 cmst:hover:bg-cmst-hover" data-testid="vue-library-node-row">
              <button
                type="button"
                class="cmst:flex cmst:w-full cmst:cursor-pointer cmst:items-center cmst:gap-2 cmst:bg-transparent cmst:text-left"
                :aria-expanded="libraryDetailKey === `node:${String(node.name || node.id)}`"
                @click="libraryDetailKey = libraryDetailKey === `node:${String(node.name || node.id)}` ? '' : `node:${String(node.name || node.id)}`"
              >
                <span class="cmst-min-w-0 cmst:flex-1 cmst:truncate cmst:text-[13px] cmst:font-medium">{{ String(node.title || node.name || node.id) }}</span>
                <span v-if="node.version" class="cmst-type-meta cmst:shrink-0">{{ String(node.version) }}</span>
              </button>
              <div v-if="libraryDetailKey === `node:${String(node.name || node.id)}`" class="cmst:mt-1 cmst:pl-1 cmst:text-xs cmst:text-cmst-muted">
                <p v-if="node.repository_url" class="cmst-type-meta cmst:truncate">{{ String(node.repository_url) }}</p>
                <p v-if="node.installed_commit" class="cmst-type-meta cmst:mt-0.5">Commit {{ String(node.installed_commit).slice(0, 12) }}</p>
                <p v-if="Array.isArray(node.classes) && node.classes.length" class="cmst-type-meta cmst:mt-0.5">{{ (node.classes as unknown[]).slice(0, 8).map(String).join(" · ") }}<template v-if="(node.classes as unknown[]).length > 8"> · +{{ (node.classes as unknown[]).length - 8 }} more</template></p>
              </div>
            </li>
            <li v-if="!filteredLibraryNodes.length" class="cmst:py-3 cmst:text-[13px] cmst:text-cmst-muted">No custom nodes match.</li>
          </ul>
        </div>
      </template>
    </div>
    </template>

    <!-- Setup wizard: 1 Feature / 2 Bindings / 3 Controls / 4 Review.
      Step values are the persisted engine contract; labels are display only.
      Graph-binding engine (begin/cancel/capture callbacks) untouched.
      The wizard is a docked right inspector, NOT a modal: no backdrop, the
      ComfyUI graph stays visible and interactive while mapping controls.
      Teleported to <body> inside its own [data-studio-app] scope so the
      inspector escapes the host overlay's z-60 stacking context (ComfyUI
      canvas chrome paints at z-999/1200 and would cover it). The marker div
      below stays in the Vue root while the wizard is open so the host's
      nested-layer protocol keeps treating Escape as wizard-owned. -->
    <div v-if="workflows.wizardOpen" data-state="open" aria-hidden="true" style="display: none" />
    <Teleport to="body">
      <div data-studio-app>
        <aside
          v-if="workflows.wizardOpen"
          class="cmst-inspector"
      data-state="open"
      data-testid="vue-workflow-wizard"
      role="complementary"
      aria-label="Setup workflow"
      tabindex="-1"
      @keydown.esc.stop="closeWizard"
    >
      <div class="cmst-inspector-head">
        <div class="cmst:flex cmst:items-start cmst:justify-between cmst:gap-3">
          <div class="cmst:min-w-0">
            <h2 class="cmst-type-section cmst:truncate">Setup workflow</h2>
            <p class="cmst-type-meta cmst:mt-0.5">Step {{ wizardStepIndex + 1 }} of {{ WIZARD_STEPS.length }} · {{ wizardStepLabel }}</p>
          </div>
          <button
            type="button"
            aria-label="Close wizard"
            class="cmst-close-btn"
            @click="closeWizard"
          >
            <X class="cmst:size-4" aria-hidden="true" />
          </button>
        </div>
        <div class="cmst-progress-thin cmst:mt-2" aria-hidden="true">
          <span :style="{ width: `${Math.round(((wizardStepIndex + 1) / WIZARD_STEPS.length) * 100)}%` }" />
        </div>
      </div>

      <div class="cmst-inspector-body">
          <template v-if="wizardStep === 'feature-type'">
            <h3 class="cmst-type-object">1 · Feature</h3>
            <p class="cmst:mt-1 cmst:text-[13px] cmst:text-cmst-muted">Choose what this workflow does. This decides which bindings and controls the next steps ask for.</p>
            <label class="cmst-field-label cmst:mt-3">Feature type
              <select
                class="cmst-field cmst:w-full"
                :value="workflows.wizardDraft?.featureType"
                @change="workflows.updateWizard({ featureType: ($event.target as HTMLSelectElement).value })"
              >
                <option value="t2i">Text to Image</option>
                <option value="i2i">Image to Image</option>
                <option value="inpaint">Inpaint</option>
                <option value="sketch">Sketch</option>
                <option value="outpaint">Outpaint</option>
              </select>
            </label>
          </template>

          <template v-else-if="wizardStep === 'required-bindings'">
            <h3 class="cmst-type-object">2 · Bindings</h3>
            <p class="cmst:mt-1 cmst:text-[13px] cmst:text-cmst-muted">
              Bind each control to its graph target — click Capture, then click
              the node input in the ComfyUI graph.
            </p>
            <p v-if="dependencySummaryLine.includes('attention')" class="cmst:mt-2 cmst:text-xs cmst:text-cmst-warn" role="status">
              Dependencies need attention ({{ dependencySummaryLine }}) — bindings still work, but runs may fail until models arrive.
            </p>
            <h4 class="cmst-micro cmst:mt-4">Required</h4>
            <ul class="cmst:mt-1">
              <li
                v-for="roleKey in requiredBindingRoles"
                :key="roleKey"
                class="cmst:rounded-md cmst:px-2 cmst:py-2 cmst:hover:bg-cmst-hover"
                :data-testid="`vue-wizard-role-${roleKey}`"
              >
                <div class="cmst:flex cmst:items-center cmst:gap-2">
                  <span
                    class="cmst:inline-block cmst:size-1.5 cmst:shrink-0 cmst:rounded-full"
                    :class="bindingConfirmed(roleBinding(roleKey)) ? 'cmst:bg-cmst-ok' : 'cmst:bg-cmst-warn'"
                    aria-hidden="true"
                  />
                  <span class="cmst:min-w-0 cmst:flex-1 cmst:truncate cmst:text-[13px] cmst:font-medium">{{ wizardRoleDef(roleKey).label }}</span>
                  <StudioButton v-if="!bindingConfirmed(roleBinding(roleKey))" size="sm" variant="secondary" :data-testid="`vue-wizard-capture-${roleKey}`" @click="captureBinding(roleKey)">Capture</StudioButton>
                  <StudioButton v-else size="sm" variant="ghost" :data-testid="`vue-wizard-view-${roleKey}`" @click="viewRoleBinding(roleKey)">View</StudioButton>
                </div>
                <p class="cmst:mt-0.5 cmst:truncate cmst:text-xs cmst:text-cmst-muted">
                  <template v-if="bindingConfirmed(roleBinding(roleKey))">{{ bindingTarget(roleBinding(roleKey)) }}</template>
                  <template v-else>Look for: {{ wizardRoleDef(roleKey).hint }}</template>
                </p>
                <div v-if="!bindingConfirmed(roleBinding(roleKey)) && roleSuggestions[roleKey]?.length" class="cmst:mt-1 cmst:flex cmst:flex-wrap cmst:gap-1">
                  <button
                    v-for="suggestion in roleSuggestions[roleKey]"
                    :key="`${suggestion.nodeId}:${suggestion.widgetName || ''}`"
                    type="button"
                    class="cmst:rounded cmst:bg-cmst-raised cmst:px-1.5 cmst:py-0.5 cmst:font-mono cmst:text-[11px] cmst:text-cmst-secondary-text cmst:hover:text-cmst-fg"
                    :title="`Show ${suggestion.nodeTitle} on the graph`"
                    @click="viewSuggestedNode(suggestion.nodeId)"
                  >{{ suggestion.nodeTitle }}</button>
                </div>
                <div v-if="!bindingConfirmed(roleBinding(roleKey))" class="cmst:mt-1">
                  <StudioButton size="sm" variant="ghost" @click="suggestRoleBinding(roleKey)">Suggest targets</StudioButton>
                </div>
              </li>
            </ul>
            <h4 class="cmst-micro cmst:mt-4">Optional</h4>
            <ul class="cmst:mt-1">
              <li
                v-for="roleKey in optionalBindingRoles"
                :key="roleKey"
                class="cmst:rounded-md cmst:px-2 cmst:py-2 cmst:hover:bg-cmst-hover"
                :data-testid="`vue-wizard-role-${roleKey}`"
              >
                <div class="cmst:flex cmst:items-center cmst:gap-2">
                  <span
                    class="cmst:inline-block cmst:size-1.5 cmst:shrink-0 cmst:rounded-full"
                    :class="bindingConfirmed(roleBinding(roleKey)) ? 'cmst:bg-cmst-ok' : 'cmst:bg-cmst-muted'"
                    aria-hidden="true"
                  />
                  <span class="cmst:min-w-0 cmst:flex-1 cmst:truncate cmst:text-[13px]">{{ wizardRoleDef(roleKey).label }}</span>
                  <StudioButton v-if="!bindingConfirmed(roleBinding(roleKey))" size="sm" variant="ghost" :data-testid="`vue-wizard-capture-${roleKey}`" @click="captureBinding(roleKey)">Capture</StudioButton>
                  <StudioButton v-else size="sm" variant="ghost" :data-testid="`vue-wizard-view-${roleKey}`" @click="viewRoleBinding(roleKey)">View</StudioButton>
                </div>
              </li>
            </ul>
            <p v-if="wizardMessage" class="cmst:mt-2 cmst:text-xs cmst:text-cmst-secondary-text" role="status">{{ wizardMessage }}</p>
          </template>

          <template v-else-if="wizardStep === 'exposed-controls'">
            <h3 class="cmst-type-object">3 · Controls</h3>
            <p class="cmst:mt-1 cmst:text-[13px] cmst:text-cmst-muted">
              Add the controls this workflow exposes. Each control becomes one field
              (Steps, CFG, Seed) — not a generic form builder.
            </p>
            <div class="cmst:mt-3 cmst:flex cmst:gap-2">
              <input v-model="controlLabel" class="cmst-field cmst:flex-1" placeholder="Control label, e.g. Steps" aria-label="Control label" />
              <StudioButton size="sm" variant="secondary" @click="addControl">Add control</StudioButton>
            </div>
            <ul class="cmst:mt-2 cmst:text-[13px]">
              <li
                v-for="(control, index) in (workflows.wizardDraft?.controls ?? [])"
                :key="index"
                class="cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:py-1.5 first:cmst:border-t-0"
              >
                · {{ String((control as Record<string, unknown>).label ?? control) }}
              </li>
            </ul>
            <div class="cmst:mt-3 cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:pt-3">
              <p class="cmst:text-[13px] cmst:text-cmst-muted">
                Select the output node in the ComfyUI graph so runs know where images land.
                <span
                  v-if="workflows.wizardDraft?.outputBinding"
                  class="cmst:ml-1 cmst:rounded cmst:px-1.5 cmst:py-0.5 cmst:text-[11px] cmst:font-medium"
                  :class="bindingConfirmed(workflows.wizardDraft?.outputBinding) ? 'cmst:bg-cmst-ok/15 cmst:text-cmst-ok' : 'cmst:bg-cmst-warn/15 cmst:text-cmst-warn'"
                >{{ bindingConfirmed(workflows.wizardDraft?.outputBinding) ? "Bound" : "Pending" }}</span>
              </p>
              <div class="cmst:mt-2"><StudioButton size="sm" variant="outline" @click="captureOutput">Capture output binding</StudioButton></div>
            </div>
          </template>

          <template v-else>
            <h3 class="cmst-type-object">4 · Review</h3>
            <p class="cmst:mt-1 cmst:text-[13px] cmst:text-cmst-muted">Review the explicit bindings before saving the version mapping.</p>
            <pre class="cmst:mt-2 cmst:max-h-40 cmst:overflow-auto cmst:rounded cmst:bg-cmst-matte cmst:p-2 cmst:font-mono cmst:text-xs cmst:text-cmst-secondary-text">{{ JSON.stringify({ bindings: workflows.wizardDraft?.bindings, output: workflows.wizardDraft?.outputBinding, controls: workflows.wizardDraft?.controls }, null, 1) }}</pre>
            <p v-if="missingRequiredLabels.length" class="cmst:mt-2 cmst:text-xs cmst:text-cmst-warn" role="status" data-testid="vue-wizard-gate">
              Still needed: {{ missingRequiredLabels.join(", ") }} — bind them in step 2 before saving.
            </p>
            <p v-if="workflows.wizardError" class="cmst:mt-2 cmst:text-xs cmst:text-cmst-danger" role="alert">{{ workflows.wizardError }}</p>
            <p v-else-if="wizardMessage" class="cmst:mt-2 cmst:text-xs cmst:text-cmst-secondary-text" role="status">{{ wizardMessage }}</p>
            <div class="cmst:mt-3">
              <StudioButton size="sm" :disabled="workflows.wizardSaving || missingRequiredLabels.length > 0" data-testid="vue-wizard-save" @click="saveWizard">
                {{ workflows.wizardSaving ? "Saving…" : "Save mapping" }}
              </StudioButton>
            </div>
          </template>
        </div>

      <div class="cmst-inspector-foot">
          <StudioButton variant="ghost" size="sm" :disabled="wizardStepIndex === 0" @click="previousWizardStep">Back</StudioButton>
          <!-- One primary per region: the Review step owns Save mapping in
            the body above, so the footer only advances on steps 1–3. -->
          <StudioButton
            v-if="wizardStepIndex < WIZARD_STEPS.length - 1"
            size="sm"
            @click="nextWizardStep"
          >Next</StudioButton>
          <span v-else class="cmst-type-meta">Review → Save mapping</span>
      </div>
        </aside>
      </div>
    </Teleport>
  </section>
</template>
