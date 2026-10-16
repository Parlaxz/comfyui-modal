<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { Check, Database, Import, Layers, RefreshCw, Search, Star, WandSparkles, X } from "@lucide/vue";
import { useWorkflowsStore } from "../stores/workflows";
import { useInfrastructureStore } from "../stores/infrastructure";
import { WIZARD_STEPS } from "../api/workflows";
import StudioButton from "../components/StudioButton.vue";
import StudioCard from "../components/StudioCard.vue";
import { studioPageClass } from "../components/studioPanels";

const workflows = useWorkflowsStore();
const infrastructure = useInfrastructureStore();
const query = ref("");
const tab = ref<"workflows" | "models">("workflows");
const bindingInput = ref("");
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

const wizardStepIndex = computed(() => Math.max(0, WIZARD_STEPS.indexOf(workflows.wizardDraft?.step ?? "feature-type")));
const wizardStep = computed(() => WIZARD_STEPS[wizardStepIndex.value]);

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

async function captureBinding() {
  if (!bindingInput.value.trim()) return;
  const fallbackTarget = bindingInput.value.trim();
  if (window.__comfymodalBeginStudioGraphBinding) {
    wizardMessage.value = "Click a node in the ComfyUI graph…";
    await window.__comfymodalBeginStudioGraphBinding({
      bindingKey: "prompt",
      label: "prompt",
      allowOutput: false,
      onCapture: (result) => {
        workflows.updateWizard({ bindings: { ...(workflows.wizardDraft?.bindings ?? {}), prompt: { ...result, confirmed: true } } });
        wizardMessage.value = `Confirmed ${String(result.nodeTitle ?? result.nodeId ?? "graph target")}`;
      },
      onCancel: (reason) => { wizardMessage.value = reason; },
    });
    return;
  }
  workflows.updateWizard({ bindings: { ...(workflows.wizardDraft?.bindings ?? {}), prompt: { target: fallbackTarget, confirmed: true } } });
  wizardMessage.value = `Confirmed graph target ${fallbackTarget}`;
}

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
    });
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
  const summary = dependencyPayload.value.summary;
  if (summary && typeof summary === "object") {
    const record = summary as Record<string, unknown>;
    const installed = Number(record.installed ?? 0);
    const missing = Number(record.missing ?? 0);
    return `${installed} installed · ${missing} missing · ${missing === 0 ? "ready" : "attention"}`;
  }
  if (!workflows.dependencies) return "not loaded";
  return `${dependencyModelRows.value.length + dependencyNodeRows.value.length} requirements`;
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

async function installDependencyNode(row: DependencyNodeRow) {
  await workflows.installDependencyNode(row.raw);
}
</script>

<template>
  <section :class="studioPageClass()" data-testid="vue-page-workflows">
    <!-- Page toolbar: title + search + filters + import. Flush on the page
      background — no hero band, no card. -->
    <div class="cmst:flex cmst:flex-wrap cmst:items-end cmst:justify-between cmst:gap-3">
      <div>
        <h1 class="cmst-type-view">Workflows</h1>
        <p class="cmst:mt-0.5 cmst:text-[13px] cmst:text-cmst-muted">
          {{ workflows.workflows.length }} workflows · versions and shared model inventory stay separate
        </p>
      </div>
      <div class="cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2">
        <div class="cmst:relative">
          <Search class="cmst:pointer-events-none cmst:absolute cmst:left-2.5 cmst:top-1/2 cmst:size-4 cmst:-translate-y-1/2 cmst:text-cmst-muted" aria-hidden="true" />
          <input
            v-model="query"
            class="cmst-field cmst:w-52 cmst:pl-8"
            placeholder="Search workflows"
            aria-label="Search workflows"
            @keyup.enter="search"
          />
        </div>
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
        <StudioButton size="sm" variant="secondary" @click="search">Search</StudioButton>
        <StudioButton size="sm" variant="ghost" aria-label="Refresh workflows" @click="workflows.loadList()">
          <RefreshCw class="cmst:size-4" aria-hidden="true" />
        </StudioButton>
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

    <!-- Quiet view tabs: text + underline, never bright fill. -->
    <div role="tablist" aria-label="Workflows or shared inventory" class="cmst:flex cmst:border-b cmst:border-solid cmst:border-cmst-border">
      <button type="button" role="tab" class="cmst-quiet-tab" :aria-selected="tab === 'workflows'" @click="tab = 'workflows'">
        <span class="cmst:inline-flex cmst:items-center cmst:gap-1.5"><Layers class="cmst:size-4" aria-hidden="true" />Workflows</span>
      </button>
      <button type="button" role="tab" class="cmst-quiet-tab" :aria-selected="tab === 'models'" @click="tab = 'models'">
        <span class="cmst:inline-flex cmst:items-center cmst:gap-1.5"><Database class="cmst:size-4" aria-hidden="true" />Models / Nodes</span>
      </button>
    </div>

    <template v-if="tab === 'workflows'">
      <div class="cmst:grid cmst:grid-cols-1 cmst:gap-6 cmst:lg:grid-cols-[280px_minmax(0,1fr)]">
        <!-- Object list: hairline rows, restrained selection. -->
        <div role="listbox" aria-label="Workflows" class="cmst:min-w-0">
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
              <strong class="cmst-type-object cmst:truncate">{{ workflow.name || workflow.workflow_id }}</strong>
            </span>
            <span class="cmst-type-meta cmst:mt-0.5 cmst:block cmst:truncate">
              {{ workflow.folder || "No folder" }} · {{ workflow.latest_version_id || "No version" }}
            </span>
          </button>
          <p v-if="!workflows.workflows.length" class="cmst:py-4 cmst:text-[13px] cmst:text-cmst-muted">
            No workflows returned by the server.
          </p>
        </div>

        <!-- Detail surface: flat sections on hairlines, not nested cards. -->
        <div v-if="workflows.selectedWorkflow" class="cmst:min-w-0">
          <div class="cmst:flex cmst:flex-wrap cmst:items-start cmst:justify-between cmst:gap-3">
            <div class="cmst:min-w-0">
              <h2 class="cmst-type-section cmst:truncate">{{ workflows.selectedWorkflow.name }}</h2>
              <p class="cmst-type-meta cmst:mt-0.5">
                Version {{ workflows.selectedVersion?.version ?? workflows.selectedVersion?.workflow_version_id }}
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

          <div class="cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-2 cmst:sm:grid-cols-2">
            <label class="cmst-field-label">Name<input v-model="editName" class="cmst-field" /></label>
            <label class="cmst-field-label">Folder<input v-model="editFolder" class="cmst-field" /></label>
          </div>
          <div class="cmst:mt-2">
            <StudioButton size="sm" variant="secondary" data-testid="vue-workflow-save-meta" @click="saveMetadata">
              Save metadata
            </StudioButton>
          </div>

          <section aria-label="Mapping" class="cmst:mt-5 cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:pt-4">
            <h3 class="cmst-type-section">Mapping</h3>
            <p class="cmst-type-meta cmst:mt-0.5">{{ workflows.mapping ? "configured" : "not configured" }}</p>
            <div class="cmst:mt-2"><StudioButton size="sm" variant="ghost" @click="workflows.loadMappingCandidates()">Load candidates</StudioButton></div>
            <pre v-if="workflows.mappingCandidates" class="cmst:mt-2 cmst:max-h-32 cmst:overflow-auto cmst:rounded cmst:bg-cmst-matte cmst:p-2 cmst:font-mono cmst:text-xs cmst:text-cmst-secondary-text">{{ JSON.stringify(workflows.mappingCandidates, null, 1).slice(0, 800) }}</pre>
            <textarea v-model="mappingText" rows="3" class="cmst-field cmst:mt-2 cmst:w-full cmst:font-mono cmst:text-xs" placeholder='{"bindings": {...}}' />
            <div class="cmst:mt-1.5"><StudioButton size="sm" variant="secondary" data-testid="vue-mapping-save" @click="saveMappingEdit">Save mapping</StudioButton></div>
          </section>

          <section aria-label="Dependencies" class="cmst:mt-5 cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:pt-4" data-testid="vue-dependencies">
            <h3 class="cmst-type-section">Dependencies</h3>
            <p class="cmst-type-meta cmst:mt-0.5">{{ dependencySummaryLine }}</p>
            <ul class="cmst:mt-1 cmst:flex cmst:max-h-56 cmst:flex-col cmst:overflow-auto">
              <li
                v-for="row in dependencyModelRows"
                :key="`model-${row.key}`"
                class="cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-x-2 cmst:gap-y-1 cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:py-2 cmst:text-[13px] first:cmst:border-t-0"
                data-testid="dependency-model-row"
              >
                <span
                  class="cmst:inline-block cmst:size-1.5 cmst:shrink-0 cmst:rounded-full"
                  :class="row.state === 'missing' ? 'cmst:bg-cmst-danger' : row.state === 'ready' || row.state === 'installed' ? 'cmst:bg-cmst-ok' : 'cmst:bg-cmst-muted'"
                  aria-hidden="true"
                />
                <span class="cmst:min-w-0 cmst:flex-1">{{ row.filename }} <span class="cmst:text-cmst-muted">({{ row.folder }})</span></span>
                <span class="cmst-type-meta" data-testid="dependency-model-state">{{ row.state }}</span>
                <label class="cmst:flex cmst:items-center cmst:gap-1 cmst:text-xs cmst:text-cmst-muted">
                  <input type="checkbox" :checked="row.nonessential" @change="toggleNonessential(row.key, ($event.target as HTMLInputElement).checked)" />
                  nonessential
                </label>
                <StudioButton v-if="row.state === 'missing' && row.hasSource" size="sm" variant="ghost" data-testid="dependency-model-install-now" @click="installDependencyModel(row)">Install now</StudioButton>
                <span v-if="row.message" class="cmst:w-full cmst:text-xs cmst:text-cmst-muted" data-testid="dependency-model-install-note">{{ row.message }}</span>
              </li>
              <li
                v-for="row in dependencyNodeRows"
                :key="`node-${row.key}`"
                class="cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-x-2 cmst:gap-y-1 cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:py-2 cmst:text-[13px]"
                data-testid="dependency-node-row"
              >
                <span
                  class="cmst:inline-block cmst:size-1.5 cmst:shrink-0 cmst:rounded-full"
                  :class="row.state === 'missing' ? 'cmst:bg-cmst-danger' : 'cmst:bg-cmst-ok'"
                  aria-hidden="true"
                />
                <span class="cmst:min-w-0 cmst:flex-1">{{ row.name }} · {{ row.state }}</span>
                <StudioButton v-if="row.state === 'missing'" size="sm" variant="ghost" data-testid="dependency-node-install-now" @click="installDependencyNode(row)">Install now</StudioButton>
                <span v-if="row.message" class="cmst:w-full cmst:text-xs cmst:text-cmst-muted" data-testid="dependency-node-install-note">{{ row.message }}</span>
              </li>
            </ul>
          </section>

          <section aria-label="Portability" class="cmst:mt-5 cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:pt-4">
            <h3 class="cmst-type-section">Portability</h3>
            <p class="cmst-type-meta cmst:mt-0.5">{{ workflows.portability ? "analyzed" : "not analyzed" }}</p>
            <div class="cmst:mt-2 cmst:flex cmst:gap-1.5">
              <StudioButton size="sm" variant="ghost" @click="workflows.recheckPortability()">Recheck</StudioButton>
              <StudioButton size="sm" variant="ghost" data-testid="vue-manifest-export" @click="workflows.exportManifest()">Export manifest</StudioButton>
            </div>
          </section>

          <section aria-label="Presets" class="cmst:mt-5 cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:pt-4">
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
                class="cmst:flex cmst:items-center cmst:justify-between cmst:gap-2 cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:py-1.5 cmst:text-[13px] first:cmst:border-t-0"
              >
                <span class="cmst:truncate">{{ String((preset as Record<string, unknown>).name || `preset ${index}`) }}</span>
                <StudioButton size="sm" variant="ghost" @click="workflows.removePreset(String((preset as Record<string, unknown>).preset_id || (preset as Record<string, unknown>).id || ''))">Delete</StudioButton>
              </li>
            </ul>
          </section>

          <section aria-label="Guidance mapping" class="cmst:mt-5 cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:pt-4">
            <h3 class="cmst-type-section">Guidance mapping</h3>
            <div class="cmst:mt-2 cmst:flex cmst:flex-wrap cmst:gap-2">
              <input v-model="guidanceSha" class="cmst-field cmst:flex-1" placeholder="model sha256" aria-label="Model sha256" />
              <select v-model="guidanceMode" class="cmst-field" aria-label="Guidance mode">
                <option value="txt2img">txt2img</option>
                <option value="i2i">i2i</option>
              </select>
              <StudioButton size="sm" variant="outline" @click="workflows.loadGuidance(guidanceSha, guidanceMode)">Load</StudioButton>
            </div>
          </section>
        </div>
        <p v-else class="cmst:py-8 cmst:text-[13px] cmst:text-cmst-muted">
          Select a workflow to inspect its versions, mapping, and dependencies.
        </p>
      </div>
    </template>

    <template v-else>
      <StudioCard class="cmst:p-4">
        <h3 class="cmst-type-section">Shared model inventory</h3>
        <p class="cmst:mt-1 cmst:text-[13px] cmst:text-cmst-muted">Owned by infrastructureStore; workflow dependencies reference this state.</p>
        <div class="cmst:mt-3 cmst:text-[13px]">Models: {{ infrastructure.models.length }} · Custom nodes: {{ infrastructure.customNodes.length }}</div>
        <div class="cmst:mt-3 cmst:flex cmst:gap-2">
          <StudioButton size="sm" variant="outline" @click="infrastructure.rescanModelsNow(true)">Rescan models</StudioButton>
          <StudioButton size="sm" variant="outline" @click="infrastructure.refreshCustomNodesNow()">Refresh nodes</StudioButton>
        </div>
      </StudioCard>
    </template>

    <!-- Setup wizard: 1 Feature / 2 Bindings / 3 Controls / 4 Review.
      Step values are the persisted engine contract; labels are display only.
      Graph-binding engine (begin/cancel/capture callbacks) untouched. -->
    <div
      v-if="workflows.wizardOpen"
      class="cmst:fixed cmst:inset-0 cmst:z-[70] cmst:flex cmst:items-center cmst:justify-center cmst:bg-black/60 cmst:p-6"
      data-state="open"
      data-testid="vue-workflow-wizard"
      tabindex="-1"
      @keydown.esc.stop="closeWizard"
    >
      <StudioCard class="cmst:max-h-[90vh] cmst:w-[min(42rem,94vw)] cmst:overflow-auto cmst:p-5">
        <div class="cmst:flex cmst:items-start cmst:justify-between cmst:gap-3">
          <div>
            <h2 class="cmst-type-section">Setup workflow</h2>
            <p class="cmst-type-meta cmst:mt-0.5">Step {{ wizardStepIndex + 1 }} of {{ WIZARD_STEPS.length }} · {{ wizardStepLabel }}</p>
          </div>
          <button
            type="button"
            aria-label="Close wizard"
            class="cmst:rounded-md cmst:p-1.5 cmst:text-cmst-muted cmst:hover:bg-cmst-hover cmst:hover:text-cmst-fg"
            @click="closeWizard"
          >
            <X class="cmst:size-4" aria-hidden="true" />
          </button>
        </div>

        <ol class="cmst:mt-3 cmst:flex cmst:items-center cmst:gap-1" aria-label="Setup progress">
          <li v-for="(step, index) in WIZARD_STEPS" :key="step" class="cmst:flex cmst:flex-1 cmst:items-center cmst:gap-1.5">
            <span
              class="cmst:flex cmst:size-5 cmst:shrink-0 cmst:items-center cmst:justify-center cmst:rounded-full cmst:text-[11px] cmst:font-semibold"
              :class="index < wizardStepIndex ? 'cmst:bg-cmst-ok cmst:text-white' : index === wizardStepIndex ? 'cmst:bg-cmst-primary cmst:text-white' : 'cmst:bg-cmst-raised cmst:text-cmst-muted'"
              :aria-current="index === wizardStepIndex ? 'step' : undefined"
            >
              <Check v-if="index < wizardStepIndex" class="cmst:size-3" aria-hidden="true" />
              <span v-else>{{ index + 1 }}</span>
            </span>
            <span class="cmst:truncate cmst:text-xs" :class="index === wizardStepIndex ? 'cmst:font-medium cmst:text-cmst-fg' : 'cmst:text-cmst-muted'">
              {{ WIZARD_STEP_LABELS[step] ?? step }}
            </span>
          </li>
        </ol>

        <div class="cmst:mt-4 cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:pt-4">
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
              Select the prompt control in the ComfyUI graph — click the node input
              (for example, the Steps control on a KSampler node) — then confirm the binding here.
            </p>
            <div class="cmst:mt-3 cmst:flex cmst:gap-2">
              <input v-model="bindingInput" class="cmst-field cmst:flex-1" placeholder="Node input target" aria-label="Node input target" />
              <StudioButton size="sm" variant="secondary" @click="captureBinding">Confirm binding</StudioButton>
            </div>
            <ul v-if="Object.keys(workflows.wizardDraft?.bindings ?? {}).length" class="cmst:mt-3">
              <li
                v-for="(binding, key) in (workflows.wizardDraft?.bindings ?? {})"
                :key="String(key)"
                class="cmst:flex cmst:items-center cmst:gap-2 cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:py-1.5 cmst:text-[13px] first:cmst:border-t-0"
              >
                <span
                  class="cmst:inline-block cmst:size-1.5 cmst:shrink-0 cmst:rounded-full"
                  :class="bindingConfirmed(binding) ? 'cmst:bg-cmst-ok' : 'cmst:bg-cmst-warn'"
                  aria-hidden="true"
                />
                <span class="cmst:min-w-0 cmst:flex-1 cmst:truncate">{{ String(key) }} → {{ bindingTarget(binding) }}</span>
                <span
                  class="cmst:rounded cmst:px-1.5 cmst:py-0.5 cmst:text-[11px] cmst:font-medium"
                  :class="bindingConfirmed(binding) ? 'cmst:bg-cmst-ok/15 cmst:text-cmst-ok' : 'cmst:bg-cmst-warn/15 cmst:text-cmst-warn'"
                >{{ bindingConfirmed(binding) ? "Bound" : "Pending" }}</span>
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
            <p v-if="workflows.wizardError" class="cmst:mt-2 cmst:text-xs cmst:text-cmst-danger" role="alert">{{ workflows.wizardError }}</p>
            <p v-else-if="wizardMessage" class="cmst:mt-2 cmst:text-xs cmst:text-cmst-secondary-text" role="status">{{ wizardMessage }}</p>
            <div class="cmst:mt-3">
              <StudioButton size="sm" :disabled="workflows.wizardSaving" data-testid="vue-wizard-save" @click="saveWizard">
                {{ workflows.wizardSaving ? "Saving…" : "Save mapping" }}
              </StudioButton>
            </div>
          </template>
        </div>

        <div class="cmst:mt-4 cmst:flex cmst:items-center cmst:justify-between cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:pt-3">
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
      </StudioCard>
    </div>
  </section>
</template>
