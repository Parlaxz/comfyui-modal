// Workflows domain authority. InfrastructureStore remains the shared model
// and custom-node inventory owner; this store owns workflow/version meaning,
// mappings, dependencies, compatibility, portability, and wizard draft state.
import { defineStore } from "pinia";
import { ref } from "vue";
import {
  captureWorkflowVersion, copyPresetToVersion, createMapping, createMappingRevision,
  createWorkflow, createWorkflowFolder, deletePreset, deleteWorkflow, deleteGuidanceMapping,
  duplicatePreset, fetchWorkflowManifestExport, getCompatibility, getDependencies,
  getGuidanceMapping, getMapping, getMappingCandidates, getMethodCompat, getPortability,
  getVersion, getVersionState, getWorkflow, importWorkflow, importWorkflowManifest,
  listFolders, listTags, listVersionPresets, listVersions, listWorkflows,
  normalizeWorkflowType, parseWizardDraft, buildWizardDraft, saveGuidanceMapping,
  setNonessentialDependencies, updateCompatibility, updatePreset, createVersionPreset,
  updateWorkflow, type WizardDraft, type WizardStep,
  type WorkflowSummary, type WorkflowVersion,
} from "../api/workflows";
import { createLatestTask } from "../async/latest";
import { createCrossTabInvalidation, publishCrossTabInvalidation } from "../compatibility/crossTab";
import { useOperationsStore } from "./operations";
import {
  buildManagerPackIndex,
  getManagerMappings,
  getManagerPackList,
  performManagerInstall,
  resolveNodeInstall,
  type ManagerPackIndex,
} from "../api/manager";
import { useInfrastructureStore } from "./infrastructure";

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
  const folders = ref<unknown>(null);
  const tags = ref<unknown>(null);
  const tagFilter = ref("");
  const folderFilter = ref("");
  const favoritesOnly = ref(false);
  const query = ref("");
  const loading = ref(false);
  const error = ref<string | null>(null);
  const wizardOpen = ref(false);
  const wizardDraft = ref<WizardDraft | null>(null);
  const wizardSaving = ref(false);
  const wizardError = ref<string | null>(null);
  const versionState = ref<unknown>(null);
  const methodCompat = ref<unknown>(null);
  const manifestPreview = ref<unknown>(null);
  const detailTask = createLatestTask();
  const managerIndex = ref<ManagerPackIndex | null>(null);
  const dependencyInstallMessage = ref<Record<string, string>>({});
  let stopCrossTab: (() => void) | null = null;

  function select(id: string | null): void { selectedId.value = id; }
  function clear(): void { selectedId.value = null; selectedWorkflow.value = null; versions.value = []; selectedVersion.value = null; }

  async function loadList(): Promise<void> {
    loading.value = true; error.value = null;
    try {
      const [result, folderResult, tagResult] = await Promise.all([
        listWorkflows({ search: query.value, tag: tagFilter.value || undefined, folder: folderFilter.value || undefined, favorite: favoritesOnly.value || undefined }),
        listFolders().catch(() => null),
        listTags().catch(() => null),
      ]);
      workflows.value = result.workflows ?? [];
      folders.value = folderResult;
      tags.value = tagResult;
    } catch (cause) { error.value = cause instanceof Error ? cause.message : "Could not load workflows"; throw cause; }
    finally { loading.value = false; }
  }

  async function initialize(): Promise<void> {
    if (!stopCrossTab) {
      stopCrossTab = createCrossTabInvalidation((kind) => {
        if (kind === "workflows" && !loading.value) void loadList();
      });
    }
    if (!workflows.value.length) await loadList();
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
      const [versionResponse, mappingResponse, dependencyResponse, compatibilityResponse, portabilityResponse, presetsResponse, stateResponse] = await Promise.all([
        getVersion(id), getMapping(id), getDependencies(id), getCompatibility(id), getPortability(id), listVersionPresets(id), getVersionState(id),
      ]);
      if (signal.aborted) return null;
      return { versionResponse, mappingResponse, dependencyResponse, compatibilityResponse, portabilityResponse, presetsResponse, stateResponse };
    });
    if (result.stale || !result.value) return;
    selectedVersion.value = result.value.versionResponse as unknown as WorkflowVersion;
    mapping.value = result.value.mappingResponse;
    mappingCandidates.value = null;
    dependencies.value = result.value.dependencyResponse;
    compatibility.value = result.value.compatibilityResponse;
    portability.value = result.value.portabilityResponse;
    versionState.value = result.value.stateResponse;
    const presetValue = result.value.presetsResponse as { presets?: unknown[] };
    presets.value = presetValue.presets ?? [];
    if (selectedWorkflow.value && id) {
      methodCompat.value = await getMethodCompat(selectedWorkflow.value.workflow_id, id).catch(() => null);
    }
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

  /** Reload resume (mirrors the legacy once-per-load rule): on a real page
    reload with a bounded draft pending, reopen the wizard at its saved step
    for the same workflow/version. Ordinary in-app navigation never resumes. */
  function pageWasReloaded(): boolean {
    try {
      const entries = typeof performance !== "undefined" && typeof performance.getEntriesByType === "function"
        ? performance.getEntriesByType("navigation")
        : [];
      const kind = entries && entries[0] && (entries[0] as unknown as Record<string, unknown>).type;
      if (kind) return kind === "reload" || kind === "back_forward";
      const legacy = (performance as unknown as { navigation?: { type?: number } }).navigation;
      return !!legacy && legacy.type !== 0;
    } catch {
      return false;
    }
  }

  async function maybeResumeWizard(): Promise<boolean> {
    if (wizardOpen.value || !pageWasReloaded()) return false;
    let raw: string | null = null;
    try {
      raw = sessionStorage.getItem(WIZARD_DRAFT_KEY);
    } catch {
      return false;
    }
    if (!raw) return false;
    let draft: WizardDraft | null = null;
    try {
      const parsed = JSON.parse(raw) as Partial<WizardDraft>;
      if (parsed.v !== 1 || !parsed.workflowId || !parsed.versionId) return false;
      draft = buildWizardDraft(parsed);
    } catch {
      return false;
    }
    try {
      await selectWorkflow(draft.workflowId);
    } catch {
      return false;
    }
    if (selectedVersion.value?.workflow_version_id !== draft.versionId) return false;
    wizardDraft.value = draft;
    wizardOpen.value = true;
    return true;
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

  async function toggleFavorite(id: string, value: boolean): Promise<void> {
    await updateWorkflow(id, { favorite: value });
    await loadList();
    publishCrossTabInvalidation("workflows");
  }

  async function createNewWorkflow(body: Record<string, unknown>): Promise<void> {
    await createWorkflow(body);
    await loadList();
    publishCrossTabInvalidation("workflows");
  }

  async function importNewWorkflow(body: Record<string, unknown>): Promise<void> {
    const operations = useOperationsStore();
    const operationId = operations.start({ kind: "workflow-import", label: "Import workflow" });
    try {
      await importWorkflow(body);
      operations.finish(operationId, "Workflow imported");
      await loadList();
      publishCrossTabInvalidation("workflows");
    } catch (cause) {
      operations.fail(operationId, cause instanceof Error ? cause.message : "Import failed");
      throw cause;
    }
  }

  async function deleteSelectedWorkflow(): Promise<void> {
    if (!selectedId.value) return;
    await deleteWorkflow(selectedId.value);
    clear();
    await loadList();
    publishCrossTabInvalidation("workflows");
  }

  async function createFolder(path: string): Promise<void> {
    await createWorkflowFolder(path);
    await loadList();
  }

  async function captureVersion(capture: Record<string, unknown>): Promise<void> {
    if (!selectedId.value) return;
    await captureWorkflowVersion(selectedId.value, capture);
    await selectWorkflow(selectedId.value);
    publishCrossTabInvalidation("workflows");
  }

  /** Canonical mapping save: create for the first mapping, revision afterwards. */
  async function saveMapping(payload: Record<string, unknown>): Promise<void> {
    const versionId = selectedVersion.value?.workflow_version_id;
    if (!versionId) throw new Error("No version selected");
    const existing = mapping.value as Record<string, unknown> | null;
    const hasMapping = !!existing && typeof existing.mapping_id === "string";
    if (hasMapping) {
      await createMappingRevision(versionId, payload);
    } else {
      await createMapping(versionId, payload);
    }
    await selectVersion(versionId);
    publishCrossTabInvalidation("workflows");
  }

  async function markNonessential(keys: string[]): Promise<void> {
    if (!selectedId.value) return;
    await setNonessentialDependencies(selectedId.value, keys);
    if (selectedVersion.value) await selectVersion(selectedVersion.value.workflow_version_id);
  }

  /** Lazy Manager pack index (loaded once; shared by all dependency rows). */
  async function loadManagerIndex(): Promise<ManagerPackIndex | null> {
    if (managerIndex.value) return managerIndex.value;
    try {
      const [packsResponse, mappingsResponse] = await Promise.all([
        getManagerPackList(),
        getManagerMappings(),
      ]);
      const packs = ((packsResponse?.data ?? {}) as Record<string, unknown>).node_packs;
      const mappings = ((mappingsResponse?.data ?? {}) as Record<string, unknown>);
      managerIndex.value = buildManagerPackIndex(
        (packs ?? {}) as Record<string, Record<string, unknown>>,
        mappings as Record<string, unknown>,
      );
    } catch {
      managerIndex.value = null;
    }
    return managerIndex.value;
  }

  /** Explicit per-row custom-node install through ComfyUI-Manager. Never reboots. */
  async function installDependencyNode(node: Record<string, unknown>): Promise<void> {
    const key = String(node.name || node.cnr_id || "node");
    const index = await loadManagerIndex();
    const plan = resolveNodeInstall(node, index);
    dependencyInstallMessage.value = { ...dependencyInstallMessage.value, [key]: "Installing…" };
    const result = await performManagerInstall(plan);
    dependencyInstallMessage.value = { ...dependencyInstallMessage.value, [key]: result.message };
    if (result.ok) {
      const infrastructure = useInfrastructureStore();
      await infrastructure.loadInventory().catch(() => undefined);
    }
  }

  async function saveCompatibility(patch: Record<string, unknown>): Promise<void> {
    if (!selectedVersion.value) return;
    await updateCompatibility(selectedVersion.value.workflow_version_id, patch);
    await selectVersion(selectedVersion.value.workflow_version_id);
  }

  async function recheckPortability(): Promise<void> {
    if (selectedVersion.value) {
      portability.value = await getPortability(selectedVersion.value.workflow_version_id);
    }
  }

  async function exportManifest(): Promise<void> {
    if (!selectedVersion.value) return;
    const result = await fetchWorkflowManifestExport(selectedVersion.value.workflow_version_id);
    if (!result.ok || !result.blob) throw new Error(result.message || "Export failed");
    const url = URL.createObjectURL(result.blob);
    try {
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = result.filename || "manifest.json";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
    } finally {
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
  }

  async function previewManifestImport(body: unknown): Promise<unknown> {
    const result = await importWorkflowManifest(body, true);
    manifestPreview.value = result;
    return result;
  }

  async function commitManifestImport(body: unknown): Promise<void> {
    await importWorkflowManifest(body, false);
    manifestPreview.value = null;
    await loadList();
    publishCrossTabInvalidation("workflows");
  }

  /** Image-free contract: strip pixel/blob/object-URL fields before persisting. */
  function sanitizePresetState(state: Record<string, unknown>): Record<string, unknown> {
    const clean: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(state)) {
      if (value instanceof Blob) continue;
      if (typeof value === "string" && (value.startsWith("blob:") || value.startsWith("data:image/"))) continue;
      if (key === "sourceImage" || key === "referenceImages" || key === "mask" || key === "sketch" || key === "generatedImages" || key === "compareImages") continue;
      clean[key] = value;
    }
    return clean;
  }

  async function createPreset(body: { name: string; description?: string; tags?: string[]; studio_state: Record<string, unknown> }): Promise<void> {
    if (!selectedVersion.value) return;
    await createVersionPreset(selectedVersion.value.workflow_version_id, {
      ...body,
      studio_state: sanitizePresetState(body.studio_state),
    });
    await selectVersion(selectedVersion.value.workflow_version_id);
  }

  async function savePreset(presetId: string, body: Record<string, unknown>): Promise<void> {
    const payload = body.studio_state && typeof body.studio_state === "object"
      ? { ...body, studio_state: sanitizePresetState(body.studio_state as Record<string, unknown>) }
      : body;
    await updatePreset(presetId, payload);
    if (selectedVersion.value) await selectVersion(selectedVersion.value.workflow_version_id);
  }

  async function removePreset(presetId: string): Promise<void> {
    await deletePreset(presetId);
    if (selectedVersion.value) await selectVersion(selectedVersion.value.workflow_version_id);
  }

  async function duplicateCurrentPreset(presetId: string, name?: string): Promise<void> {
    await duplicatePreset(presetId, name ? { name } : {});
    if (selectedVersion.value) await selectVersion(selectedVersion.value.workflow_version_id);
  }

  async function copyPresetForward(presetId: string, workflowVersionId: string): Promise<void> {
    await copyPresetToVersion(presetId, workflowVersionId);
    publishCrossTabInvalidation("workflows");
  }

  async function loadGuidance(modelSha256: string, mode: string): Promise<unknown> {
    return getGuidanceMapping(modelSha256, mode);
  }

  async function saveGuidance(record: Record<string, unknown>): Promise<void> {
    await saveGuidanceMapping(record);
  }

  async function removeGuidance(modelSha256: string, mode: string): Promise<void> {
    await deleteGuidanceMapping(modelSha256, mode);
  }

  /** Wizard final save: validates confirmed bindings + output, persists mapping. */
  async function saveWizardMapping(): Promise<void> {
    const draft = wizardDraft.value;
    if (!draft) throw new Error("No wizard draft");
    const bindings = draft.bindings || {};
    const confirmed = Object.values(bindings).filter(
      (entry) => entry && typeof entry === "object" && (entry as Record<string, unknown>).confirmed === true,
    );
    if (!confirmed.length) throw new Error("Confirm at least one graph binding first");
    if (!draft.outputBinding) throw new Error("Capture the output binding first");
    wizardSaving.value = true;
    wizardError.value = null;
    try {
      await saveMapping({
        feature_type: draft.featureType,
        bindings: draft.bindings,
        output_binding: draft.outputBinding,
        controls: draft.controls,
        details: draft.details,
      });
      try {
        sessionStorage.removeItem(WIZARD_DRAFT_KEY);
      } catch {
        // Best effort.
      }
      wizardDraft.value = null;
      wizardOpen.value = false;
    } catch (cause) {
      wizardError.value = cause instanceof Error ? cause.message : "Mapping save failed";
      throw cause;
    } finally {
      wizardSaving.value = false;
    }
  }

  return {
    workflows, selectedId, selectedWorkflow, versions, selectedVersion, mapping, mappingCandidates,
    dependencies, compatibility, portability, presets, folders, tags,
    tagFilter, folderFilter, favoritesOnly,
    versionState, methodCompat, manifestPreview,
    query, loading, error, wizardOpen, wizardDraft, wizardSaving, wizardError,
    select, clear, loadList, initialize, selectWorkflow, selectVersion, loadMappingCandidates, openWizard,
    updateWizard, setWizardStep, closeWizard, updateMetadata, maybeResumeWizard,
    toggleFavorite, createNewWorkflow, importNewWorkflow, deleteSelectedWorkflow,
    createFolder, captureVersion, saveMapping,
    markNonessential, saveCompatibility, recheckPortability, loadManagerIndex,
    installDependencyNode, dependencyInstallMessage,
    exportManifest, previewManifestImport, commitManifestImport,
    sanitizePresetState, createPreset, savePreset, removePreset,
    duplicateCurrentPreset, copyPresetForward,
    loadGuidance, saveGuidance, removeGuidance,
    saveWizardMapping,
  };
});
