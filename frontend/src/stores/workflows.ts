// Workflows domain authority. InfrastructureStore remains the shared model
// and custom-node inventory owner; this store owns workflow/version meaning,
// mappings, dependencies, compatibility, portability, and wizard draft state.
import { defineStore } from "pinia";
import { ref } from "vue";
import {
  getCompatibility, getDependencies, getMapping, getMappingCandidates, getPortability,
  getVersion, getWorkflow, listPresets, listVersions, listWorkflows, normalizeWorkflowType,
  parseWizardDraft, buildWizardDraft, updateWorkflow, type WizardDraft, type WizardStep,
  type WorkflowSummary, type WorkflowVersion,
} from "../api/workflows";
import { createLatestTask } from "../async/latest";
import { publishCrossTabInvalidation } from "../compatibility/crossTab";

const WIZARD_DRAFT_KEY = "comfymodal.studio.wizard.draft.v1";

export const useWorkflowsStore = defineStore("studio-workflows", () => {
  const workflows = ref<WorkflowSummary[]>([]);
  const selectedId = ref<string | null>(null);
  const selectedWorkflow = ref<WorkflowSummary | null>(null);
  const versions = ref<WorkflowVersion[]>([]);
  const selectedVersion = ref<WorkflowVersion | null>(null);
  const mapping = ref<unknown>(null);
  const mappingCandidates = ref<unknown>(null);
  const dependencies = ref<unknown>(null);
  const compatibility = ref<unknown>(null);
  const portability = ref<unknown>(null);
  const presets = ref<unknown[]>([]);
  const query = ref("");
  const loading = ref(false);
  const error = ref<string | null>(null);
  const wizardOpen = ref(false);
  const wizardDraft = ref<WizardDraft | null>(null);
  const detailTask = createLatestTask();

  function select(id: string | null): void { selectedId.value = id; }
  function clear(): void { selectedId.value = null; selectedWorkflow.value = null; versions.value = []; selectedVersion.value = null; }

  async function loadList(): Promise<void> {
    loading.value = true; error.value = null;
    try {
      const result = await listWorkflows({ search: query.value });
      workflows.value = result.workflows ?? [];
    } catch (cause) { error.value = cause instanceof Error ? cause.message : "Could not load workflows"; throw cause; }
    finally { loading.value = false; }
  }

  async function selectWorkflow(id: string): Promise<void> {
    selectedId.value = id;
    const result = await detailTask.run(async (signal) => {
      const [workflowResponse, versionsResponse] = await Promise.all([getWorkflow(id), listVersions(id)]);
      if (signal.aborted) return null;
      return { workflowResponse, versionsResponse };
    });
    if (result.stale || !result.value) return;
    selectedWorkflow.value = result.value.workflowResponse.workflow ?? null;
    versions.value = result.value.versionsResponse.versions ?? [];
    const latestId = selectedWorkflow.value?.latest_version_id;
    const latest = versions.value.find((item) => item.workflow_version_id === latestId) ?? versions.value.at(-1) ?? null;
    if (latest) await selectVersion(latest.workflow_version_id);
  }

  async function selectVersion(id: string): Promise<void> {
    const result = await detailTask.run(async (signal) => {
      const [versionResponse, mappingResponse, dependencyResponse, compatibilityResponse, portabilityResponse, presetsResponse] = await Promise.all([
        getVersion(id), getMapping(id), getDependencies(id), getCompatibility(id), getPortability(id), listPresets(id),
      ]);
      if (signal.aborted) return null;
      return { versionResponse, mappingResponse, dependencyResponse, compatibilityResponse, portabilityResponse, presetsResponse };
    });
    if (result.stale || !result.value) return;
    selectedVersion.value = result.value.versionResponse as unknown as WorkflowVersion;
    mapping.value = result.value.mappingResponse;
    mappingCandidates.value = null;
    dependencies.value = result.value.dependencyResponse;
    compatibility.value = result.value.compatibilityResponse;
    portability.value = result.value.portabilityResponse;
    const presetValue = result.value.presetsResponse as { presets?: unknown[] };
    presets.value = presetValue.presets ?? [];
  }

  async function loadMappingCandidates(): Promise<void> {
    if (selectedVersion.value) mappingCandidates.value = await getMappingCandidates(selectedVersion.value.workflow_version_id);
  }

  function openWizard(): void {
    const workflowId = selectedWorkflow.value?.workflow_id ?? "";
    const versionId = selectedVersion.value?.workflow_version_id ?? "";
    try { wizardDraft.value = parseWizardDraft(sessionStorage.getItem(WIZARD_DRAFT_KEY), workflowId, versionId) ?? buildWizardDraft({ workflowId, versionId, featureType: normalizeWorkflowType(selectedWorkflow.value?.workflow_type) }); } catch { wizardDraft.value = buildWizardDraft({ workflowId, versionId }); }
    wizardOpen.value = true;
  }

  function updateWizard(patch: Partial<WizardDraft>): void {
    if (!wizardDraft.value) return;
    wizardDraft.value = buildWizardDraft({ ...wizardDraft.value, ...patch });
    try { sessionStorage.setItem(WIZARD_DRAFT_KEY, JSON.stringify(wizardDraft.value)); } catch { /* bounded storage is best effort */ }
  }

  function setWizardStep(step: WizardStep): void { updateWizard({ step }); }

  function closeWizard(): void {
    wizardOpen.value = false;
    wizardDraft.value = null;
    try { sessionStorage.removeItem(WIZARD_DRAFT_KEY); } catch { /* best effort */ }
  }

  async function updateMetadata(patch: Record<string, unknown>): Promise<void> {
    if (!selectedId.value) return;
    await updateWorkflow(selectedId.value, patch);
    await loadList();
    await selectWorkflow(selectedId.value);
    publishCrossTabInvalidation("workflows");
  }

  return {
    workflows, selectedId, selectedWorkflow, versions, selectedVersion, mapping, mappingCandidates,
    dependencies, compatibility, portability, presets, query, loading, error, wizardOpen, wizardDraft,
    select, clear, loadList, selectWorkflow, selectVersion, loadMappingCandidates, openWizard,
    updateWizard, setWizardStep, closeWizard, updateMetadata,
  };
});
