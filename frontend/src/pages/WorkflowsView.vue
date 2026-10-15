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
const selectedInput = ref("");
const bindingInput = ref("");
const wizardMessage = ref("");

const wizardStepIndex = computed(() => Math.max(0, WIZARD_STEPS.indexOf(workflows.wizardDraft?.step ?? "feature-type")));
const wizardStep = computed(() => WIZARD_STEPS[wizardStepIndex.value]);

onMounted(async () => {
  await Promise.all([workflows.loadList(), infrastructure.initialize()]);
});

async function search() {
  workflows.query = query.value;
  await workflows.loadList();
}

async function selectWorkflow(id: string) {
  selectedInput.value = id;
  await workflows.selectWorkflow(id);
}

function openWizard() {
  workflows.openWizard();
  window.__comfymodalSetGraphInteractionEnabled?.(true);
}

function closeWizard() {
  workflows.closeWizard();
  window.__comfymodalSetGraphInteractionEnabled?.(false);
}

function captureBinding() {
  if (!bindingInput.value.trim()) return;
  workflows.updateWizard({ bindings: { ...(workflows.wizardDraft?.bindings ?? {}), prompt: { target: bindingInput.value.trim(), confirmed: true } } });
  wizardMessage.value = `Confirmed graph target ${bindingInput.value.trim()}`;
}

function nextWizardStep() {
  const next = WIZARD_STEPS[Math.min(WIZARD_STEPS.length - 1, wizardStepIndex.value + 1)];
  workflows.setWizardStep(next);
}

function previousWizardStep() {
  const previous = WIZARD_STEPS[Math.max(0, wizardStepIndex.value - 1)];
  workflows.setWizardStep(previous);
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
        <div class="cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2"><input v-model="query" class="cmst:h-9 cmst:flex-1 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2" placeholder="Search workflows" @keyup.enter="search" /><StudioButton size="sm" variant="secondary" @click="search">Search</StudioButton><StudioButton size="sm" variant="outline" @click="workflows.loadList"><RefreshCw class="cmst:size-4" /></StudioButton></div>
        <div class="cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-2 cmst:sm:grid-cols-2">
          <button v-for="workflow in workflows.workflows" :key="workflow.workflow_id" type="button" class="cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:p-3 cmst:text-left cmst:hover:bg-cmst-secondary" :data-testid="`vue-workflow-${workflow.workflow_id}`" @click="selectWorkflow(workflow.workflow_id)"><strong>{{ workflow.name || workflow.workflow_id }}</strong><span class="cmst:block cmst:text-xs cmst:opacity-70">{{ workflow.folder || "No folder" }} · {{ workflow.latest_version_id || "No version" }}</span></button>
        </div>
        <p v-if="!workflows.workflows.length" class="cmst:mt-3 cmst:text-sm cmst:opacity-70">No workflows returned by the server.</p>
      </StudioCard>

      <StudioCard v-if="workflows.selectedWorkflow" class="cmst:p-4">
        <div class="cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-3"><div><h3 class="cmst:text-base cmst:font-semibold">{{ workflows.selectedWorkflow.name }}</h3><p class="cmst:text-xs cmst:opacity-70">Version {{ workflows.selectedVersion?.version ?? workflows.selectedVersion?.workflow_version_id }}</p></div><StudioButton size="sm" @click="openWizard"><WandSparkles class="cmst:size-4" />Setup wizard</StudioButton></div>
        <div class="cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-3"><div class="cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm">Mapping<br /><strong>{{ workflows.mapping ? "configured" : "not configured" }}</strong></div><div class="cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm">Dependencies<br /><strong>{{ workflows.dependencies ? "loaded" : "not loaded" }}</strong></div><div class="cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-sm">Portability<br /><strong>{{ workflows.portability ? "analyzed" : "not analyzed" }}</strong></div></div>
      </StudioCard>
    </template>

    <template v-else>
      <StudioCard class="cmst:p-4"><h3 class="cmst:text-sm cmst:font-semibold">Shared model inventory</h3><p class="cmst:mt-1 cmst:text-sm cmst:opacity-70">Owned by infrastructureStore; workflow dependencies reference this state.</p><div class="cmst:mt-3 cmst:text-sm">Models: {{ infrastructure.models.length }} · Custom nodes: {{ infrastructure.customNodes.length }}</div><div class="cmst:mt-3 cmst:flex cmst:gap-2"><StudioButton size="sm" variant="outline" @click="infrastructure.rescanModelsNow">Rescan models</StudioButton><StudioButton size="sm" variant="outline" @click="infrastructure.refreshCustomNodesNow">Refresh nodes</StudioButton></div></StudioCard>
    </template>

    <div v-if="workflows.wizardOpen" class="cmst:fixed cmst:inset-0 cmst:z-[70] cmst:flex cmst:items-center cmst:justify-center cmst:bg-black/60 cmst:p-6" data-testid="vue-workflow-wizard"><StudioCard class="cmst:w-[min(42rem,94vw)] cmst:p-5"><div class="cmst:flex cmst:items-center cmst:justify-between"><div><h2 class="cmst:text-lg cmst:font-semibold">Setup workflow</h2><p class="cmst:text-xs cmst:opacity-70">Step {{ wizardStepIndex + 1 }} of {{ WIZARD_STEPS.length }} · {{ wizardStep }}</p></div><StudioButton variant="ghost" size="sm" @click="closeWizard">Close</StudioButton></div><div class="cmst:mt-5 cmst:rounded-md cmst:bg-cmst-bg cmst:p-4"><template v-if="wizardStep === 'feature-type'"><h3 class="cmst:font-semibold">Feature Type</h3><p class="cmst:mt-2 cmst:text-sm cmst:opacity-75">Feature type is explicit and provider-neutral.</p><select class="cmst:mt-3 cmst:h-9 cmst:w-full cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:px-2" :value="workflows.wizardDraft?.featureType" @change="workflows.updateWizard({ featureType: ($event.target as HTMLSelectElement).value })"><option value="t2i">Text to Image</option><option value="i2i">Image to Image</option><option value="inpaint">Inpaint</option><option value="sketch">Sketch</option><option value="outpaint">Outpaint</option></select></template><template v-else-if="wizardStep === 'required-bindings'"><h3 class="cmst:font-semibold">Required Bindings</h3><p class="cmst:mt-2 cmst:text-sm cmst:opacity-75">Graph binding is explicit: underlying ComfyUI graph interaction is enabled while this step is active.</p><div class="cmst:mt-3 cmst:flex cmst:gap-2"><input v-model="bindingInput" class="cmst:h-9 cmst:flex-1 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:px-2" placeholder="Node/widget target" /><StudioButton size="sm" @click="captureBinding">Confirm binding</StudioButton></div><p v-if="wizardMessage" class="cmst:mt-2 cmst:text-xs">{{ wizardMessage }}</p></template><template v-else-if="wizardStep === 'exposed-controls'"><h3 class="cmst:font-semibold">Exposed Controls</h3><p class="cmst:mt-2 cmst:text-sm cmst:opacity-75">Control selection is stored in the bounded session draft.</p></template><template v-else><h3 class="cmst:font-semibold">Details</h3><p class="cmst:mt-2 cmst:text-sm cmst:opacity-75">Review the explicit bindings before saving the version mapping.</p></template></div><div class="cmst:mt-4 cmst:flex cmst:justify-between"><StudioButton variant="outline" size="sm" :disabled="wizardStepIndex === 0" @click="previousWizardStep">Back</StudioButton><StudioButton size="sm" :disabled="wizardStepIndex === WIZARD_STEPS.length - 1" @click="nextWizardStep">Next</StudioButton></div></StudioCard></div>
  </section>
</template>
