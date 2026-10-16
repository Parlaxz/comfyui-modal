<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { Layers, Database, WandSparkles, RefreshCw } from "@lucide/vue";
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
const presetName = ref("");
const guidanceSha = ref("");
const guidanceMode = ref("txt2img");
const mappingText = ref("");

const wizardStepIndex = computed(() => Math.max(0, WIZARD_STEPS.indexOf(workflows.wizardDraft?.step ?? "feature-type")));
const wizardStep = computed(() => WIZARD_STEPS[wizardStepIndex.value]);

onMounted(async () => {
  await Promise.all([workflows.initialize(), infrastructure.initialize()]);
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
</script>

<template>
  <section :class="studioPageClass()" data-testid="vue-page-workflows">
    <StudioCard class="cmst:p-4">
      <div class="cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-3">
        <div><h2 class="cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2"><Layers class="cmst:size-5" aria-hidden="true" />Workflows & Models</h2><p class="cmst:text-sm cmst:opacity-80">Workflow/version state and shared infrastructure inventory remain separate authorities.</p></div>
        <div class="cmst:flex cmst:gap-2"><StudioButton :variant="tab === 'workflows' ? 'default' : 'outline'" size="sm" @click="tab = 'workflows'"><Layers class="cmst:size-4" />Workflows</StudioButton><StudioButton :variant="tab === 'models' ? 'default' : 'outline'" size="sm" @click="tab = 'models'"><Database class="cmst:size-4" />Models / Nodes</StudioButton></div>
      </div>
    </StudioCard>

    <template v-if="tab === 'workflows'">
      <StudioCard class="cmst:p-4">
        <div class="cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2">
          <input v-model="query" class="cmst:h-9 cmst:flex-1 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2" placeholder="Search workflows" aria-label="Search workflows" @keyup.enter="search" />
          <select v-model="workflows.tagFilter" class="cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm" aria-label="Filter by tag" @change="workflows.loadList()"><option value="">All tags</option></select>
          <label class="cmst:flex cmst:items-center cmst:gap-1 cmst:text-sm"><input v-model="workflows.favoritesOnly" type="checkbox" @change="workflows.loadList()" /> Favorites</label>
          <StudioButton size="sm" variant="secondary" @click="search">Search</StudioButton>
          <StudioButton size="sm" variant="outline" @click="workflows.loadList()"><RefreshCw class="cmst:size-4" /></StudioButton>
        </div>
        <div class="cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-2 cmst:sm:grid-cols-2">
          <button v-for="workflow in workflows.workflows" :key="workflow.workflow_id" type="button" class="cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:p-3 cmst:text-left cmst:hover:bg-cmst-secondary" :data-testid="`vue-workflow-${workflow.workflow_id}`" @click="selectWorkflow(workflow.workflow_id)"><strong>{{ workflow.name || workflow.workflow_id }}</strong><span class="cmst:block cmst:text-xs cmst:opacity-70">{{ workflow.folder || "No folder" }} · {{ workflow.latest_version_id || "No version" }}</span></button>
        </div>
        <p v-if="!workflows.workflows.length" class="cmst:mt-3 cmst:text-sm cmst:opacity-70">No workflows returned by the server.</p>
        <div class="cmst:mt-3">
          <h3 class="cmst:text-sm cmst:font-semibold">Import workflow</h3>
          <textarea v-model="importText" rows="3" class="cmst:mt-1 cmst:w-full cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:p-2 cmst:text-xs" placeholder='{"name": "...", "static_graph": {...}}' data-testid="vue-workflow-import-input" />
          <p v-if="importError" class="cmst:mt-1 cmst:text-xs cmst:text-red-300" role="alert">{{ importError }}</p>
          <StudioButton class="cmst:mt-2" size="sm" data-testid="vue-workflow-import" @click="doImport">Import</StudioButton>
        </div>
      </StudioCard>

      <StudioCard v-if="workflows.selectedWorkflow" class="cmst:p-4">
        <div class="cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-3">
          <div><h3 class="cmst:text-base cmst:font-semibold">{{ workflows.selectedWorkflow.name }}</h3><p class="cmst:text-xs cmst:opacity-70">Version {{ workflows.selectedVersion?.version ?? workflows.selectedVersion?.workflow_version_id }}</p></div>
          <div class="cmst:flex cmst:gap-2">
            <StudioButton size="sm" variant="outline" :data-testid="`vue-workflow-favorite-${workflows.selectedWorkflow.workflow_id}`" @click="workflows.toggleFavorite(workflows.selectedWorkflow!.workflow_id, !workflows.selectedWorkflow!.favorite)">★</StudioButton>
            <StudioButton size="sm" @click="openWizard"><WandSparkles class="cmst:size-4" />Setup wizard</StudioButton>
          </div>
        </div>
        <div class="cmst:mt-3 cmst:flex cmst:flex-wrap cmst:gap-2">
          <select :value="workflows.selectedVersion?.workflow_version_id ?? ''" class="cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm" aria-label="Select version" data-testid="vue-version-select" @change="workflows.selectVersion(($event.target as HTMLSelectElement).value)">
            <option v-for="version in workflows.versions" :key="version.workflow_version_id" :value="version.workflow_version_id">v{{ version.version ?? version.workflow_version_id }}</option>
          </select>
          <StudioButton size="sm" variant="outline" data-testid="vue-version-capture" @click="workflows.captureVersion({})">Capture version</StudioButton>
          <StudioButton size="sm" variant="outline" data-testid="vue-workflow-delete" @click="workflows.deleteSelectedWorkflow()">Delete workflow</StudioButton>
        </div>
        <div class="cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-2 cmst:sm:grid-cols-2">
          <label class="cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm">Name<input v-model="editName" class="cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2" /></label>
          <label class="cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm">Folder<input v-model="editFolder" class="cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2" /></label>
        </div>
        <StudioButton class="cmst:mt-2" size="sm" variant="secondary" data-testid="vue-workflow-save-meta" @click="saveMetadata">Save metadata</StudioButton>

        <div class="cmst:mt-4 cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-3">
          <div class="cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm">Mapping<br /><strong>{{ workflows.mapping ? "configured" : "not configured" }}</strong>
            <div class="cmst:mt-2"><StudioButton size="sm" variant="ghost" @click="workflows.loadMappingCandidates()">Load candidates</StudioButton></div>
            <pre v-if="workflows.mappingCandidates" class="cmst:mt-2 cmst:max-h-32 cmst:overflow-auto cmst:text-xs">{{ JSON.stringify(workflows.mappingCandidates, null, 1).slice(0, 800) }}</pre>
            <textarea v-model="mappingText" rows="3" class="cmst:mt-2 cmst:w-full cmst:rounded cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:p-2 cmst:text-xs" placeholder='{"bindings": {...}}' />
            <StudioButton class="cmst:mt-1" size="sm" data-testid="vue-mapping-save" @click="saveMappingEdit">Save mapping</StudioButton>
          </div>
          <div class="cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm">Dependencies<br /><strong>{{ workflows.dependencies ? "loaded" : "not loaded" }}</strong>
            <pre v-if="workflows.dependencies" class="cmst:mt-2 cmst:max-h-32 cmst:overflow-auto cmst:text-xs">{{ JSON.stringify(workflows.dependencies, null, 1).slice(0, 800) }}</pre>
          </div>
          <div class="cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm">Portability<br /><strong>{{ workflows.portability ? "analyzed" : "not analyzed" }}</strong>
            <div class="cmst:mt-2 cmst:flex cmst:gap-1">
              <StudioButton size="sm" variant="ghost" @click="workflows.recheckPortability()">Recheck</StudioButton>
              <StudioButton size="sm" variant="ghost" data-testid="vue-manifest-export" @click="workflows.exportManifest()">Export manifest</StudioButton>
            </div>
          </div>
        </div>

        <div class="cmst:mt-4">
          <h4 class="cmst:text-sm cmst:font-semibold">Presets (image-free configuration only)</h4>
          <div class="cmst:mt-2 cmst:flex cmst:gap-2">
            <input v-model="presetName" class="cmst:h-9 cmst:flex-1 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm" placeholder="Preset name" />
            <StudioButton size="sm" data-testid="vue-preset-create" @click="workflows.createPreset({ name: presetName || 'Untitled', studio_state: {} }); presetName = ''">Create preset</StudioButton>
          </div>
          <ul class="cmst:mt-2 cmst:text-sm">
            <li v-for="(preset, index) in workflows.presets" :key="index" class="cmst:flex cmst:items-center cmst:gap-2">
              <span>{{ String((preset as Record<string, unknown>).name || `preset ${index}`) }}</span>
              <StudioButton size="sm" variant="ghost" @click="workflows.removePreset(String((preset as Record<string, unknown>).preset_id || (preset as Record<string, unknown>).id || ''))">Delete</StudioButton>
            </li>
          </ul>
        </div>

        <div class="cmst:mt-4">
          <h4 class="cmst:text-sm cmst:font-semibold">Guidance mapping</h4>
          <div class="cmst:mt-2 cmst:flex cmst:flex-wrap cmst:gap-2">
            <input v-model="guidanceSha" class="cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm" placeholder="model sha256" />
            <select v-model="guidanceMode" class="cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm"><option value="txt2img">txt2img</option><option value="i2i">i2i</option></select>
            <StudioButton size="sm" variant="outline" @click="workflows.loadGuidance(guidanceSha, guidanceMode)">Load</StudioButton>
          </div>
        </div>
      </StudioCard>
    </template>

    <template v-else>
      <StudioCard class="cmst:p-4"><h3 class="cmst:text-sm cmst:font-semibold">Shared model inventory</h3><p class="cmst:mt-1 cmst:text-sm cmst:opacity-70">Owned by infrastructureStore; workflow dependencies reference this state.</p><div class="cmst:mt-3 cmst:text-sm">Models: {{ infrastructure.models.length }} · Custom nodes: {{ infrastructure.customNodes.length }}</div><div class="cmst:mt-3 cmst:flex cmst:gap-2"><StudioButton size="sm" variant="outline" @click="infrastructure.rescanModelsNow(true)">Rescan models</StudioButton><StudioButton size="sm" variant="outline" @click="infrastructure.refreshCustomNodesNow()">Refresh nodes</StudioButton></div></StudioCard>
    </template>

    <div v-if="workflows.wizardOpen" class="cmst:fixed cmst:inset-0 cmst:z-[70] cmst:flex cmst:items-center cmst:justify-center cmst:bg-black/60 cmst:p-6" data-state="open" data-testid="vue-workflow-wizard" tabindex="-1" @keydown.esc.stop="closeWizard"><StudioCard class="cmst:w-[min(42rem,94vw)] cmst:max-h-[90vh] cmst:overflow-auto cmst:p-5"><div class="cmst:flex cmst:items-center cmst:justify-between"><div><h2 class="cmst:text-lg cmst:font-semibold">Setup workflow</h2><p class="cmst:text-xs cmst:opacity-70">Step {{ wizardStepIndex + 1 }} of {{ WIZARD_STEPS.length }} · {{ wizardStep }}</p></div><StudioButton variant="ghost" size="sm" @click="closeWizard">Close</StudioButton></div><div class="cmst:mt-5 cmst:rounded-md cmst:bg-cmst-bg cmst:p-4"><template v-if="wizardStep === 'feature-type'"><h3 class="cmst:font-semibold">Feature Type</h3><p class="cmst:mt-2 cmst:text-sm cmst:opacity-75">Feature type is explicit and provider-neutral.</p><select class="cmst:mt-3 cmst:h-9 cmst:w-full cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:px-2" :value="workflows.wizardDraft?.featureType" @change="workflows.updateWizard({ featureType: ($event.target as HTMLSelectElement).value })"><option value="t2i">Text to Image</option><option value="i2i">Image to Image</option><option value="inpaint">Inpaint</option><option value="sketch">Sketch</option><option value="outpaint">Outpaint</option></select></template><template v-else-if="wizardStep === 'required-bindings'"><h3 class="cmst:font-semibold">Required Bindings</h3><p class="cmst:mt-2 cmst:text-sm cmst:opacity-75">Graph binding is explicit: underlying ComfyUI graph interaction is enabled while this step is active.</p><div class="cmst:mt-3 cmst:flex cmst:gap-2"><input v-model="bindingInput" class="cmst:h-9 cmst:flex-1 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:px-2" placeholder="Node/widget target" /><StudioButton size="sm" @click="captureBinding">Confirm binding</StudioButton></div><p v-if="wizardMessage" class="cmst:mt-2 cmst:text-xs">{{ wizardMessage }}</p></template><template v-else-if="wizardStep === 'exposed-controls'"><h3 class="cmst:font-semibold">Exposed Controls</h3><p class="cmst:mt-2 cmst:text-sm cmst:opacity-75">Workflow configuration controls live here — not a generic form builder.</p><div class="cmst:mt-3 cmst:flex cmst:gap-2"><input v-model="controlLabel" class="cmst:h-9 cmst:flex-1 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:px-2" placeholder="Control label" /><StudioButton size="sm" @click="addControl">Add control</StudioButton></div><ul class="cmst:mt-2 cmst:text-sm"><li v-for="(control, index) in (workflows.wizardDraft?.controls ?? [])" :key="index">· {{ String((control as Record<string, unknown>).label ?? control) }}</li></ul><div class="cmst:mt-3"><StudioButton size="sm" variant="outline" @click="captureOutput">Capture output binding</StudioButton></div></template><template v-else><h3 class="cmst:font-semibold">Details</h3><p class="cmst:mt-2 cmst:text-sm cmst:opacity-75">Review the explicit bindings before saving the version mapping.</p><pre class="cmst:mt-2 cmst:max-h-40 cmst:overflow-auto cmst:text-xs">{{ JSON.stringify({ bindings: workflows.wizardDraft?.bindings, output: workflows.wizardDraft?.outputBinding, controls: workflows.wizardDraft?.controls }, null, 1) }}</pre><p v-if="workflows.wizardError" class="cmst:mt-2 cmst:text-xs cmst:text-red-300" role="alert">{{ workflows.wizardError }}</p><StudioButton class="cmst:mt-3" size="sm" :disabled="workflows.wizardSaving" data-testid="vue-wizard-save" @click="saveWizard">{{ workflows.wizardSaving ? "Saving…" : "Save mapping" }}</StudioButton></template></div><div class="cmst:mt-4 cmst:flex cmst:justify-between"><StudioButton variant="outline" size="sm" :disabled="wizardStepIndex === 0" @click="previousWizardStep">Back</StudioButton><StudioButton size="sm" :disabled="wizardStepIndex === WIZARD_STEPS.length - 1" @click="nextWizardStep">Next</StudioButton></div></StudioCard></div>
  </section>
</template>
