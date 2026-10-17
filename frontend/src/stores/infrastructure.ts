// Infrastructure domain authority: workspaces, deployment, inventory, and
// shared model/custom-node state. Operations are domain-owned; the shared
// operationsStore receives only visible summaries. Cross-tab invalidation
// refetches server truth; entities are never replicated.
import { defineStore } from "pinia";
import { computed, ref } from "vue";
import {
  activateWorkspace,
  applyManifestRepairs,
  buildSwapConfirmPayload,
  deleteManifestPlaceholder,
  getAuthStatus,
  getCredentialStatus,
  getCustomNodeSyncOperationStatus,
  getCustomNodeSyncStatus,
  getDeployLog,
  getDeployStatus,
  getRuntimeHealth,
  getWorkspaceSwapStatus,
  installSingleModel,
  isDeployUsable,
  listCustomNodes,
  listModels,
  listWorkspaces,
  modelDownloadStatus,
  normalizeDeployStatus,
  refreshCustomNodes,
  refreshInventory,
  requestCustomNodeInstall,
  requestModelInstall,
  requestWorkspaceSwap,
  rescanModels,
  saveCredentialToken,
  scanManifestIssues,
  summarizeWorkspaces,
  swapPhaseMessage,
  triggerDeploy,
  triggerPushPlugins,
  triggerRebuildDependencies,
  updateModelRecord,
  upsertWorkspace,
  credentialConfigured,
  type DeployStatus,
  type WorkspaceSummary,
} from "../api/infrastructure";
import { createCrossTabInvalidation, publishCrossTabInvalidation } from "../compatibility/crossTab";
import { createLatestTask } from "../async/latest";
import { pollUntil } from "../async/polling";
import { useOperationsStore } from "./operations";

export interface SwapReview {
  workspaceLabel: string;
  toInstall: Array<{ key: string; filename: string; folder: string }>;
  installCount: number;
  presentCount: number;
  removeCount: number;
}

export const useInfrastructureStore = defineStore("studio-infrastructure", () => {
  const deployState = ref("unknown");
  const deployMessage = ref<string | null>(null);
  const syncSummary = ref<string | null>(null);
  const workspaces = ref<WorkspaceSummary[]>([]);
  const activeWorkspaceId = ref<string | null>(null);
  const deployStatus = ref<DeployStatus>(normalizeDeployStatus(null));
  const deployLog = ref<unknown>(null);
  const models = ref<Array<Record<string, unknown>>>([]);
  const modelTypes = ref<unknown[]>([]);
  const customNodes = ref<Array<Record<string, unknown>>>([]);
  const customNodeSync = ref<Record<string, unknown> | null>(null);
  const loading = ref(false);
  const error = ref<string | null>(null);
  const busy = ref(false);
  const progress = ref<string | null>(null);
  const swapReview = ref<SwapReview | null>(null);
  const swapConfirmRequired = ref(false);
  const authConnected = ref<boolean | null>(null);
  const hfConfigured = ref(false);
  const civitaiConfigured = ref(false);
  const repairIssues = ref<unknown>(null);
  const repairMessage = ref<string | null>(null);
  const health = ref<Record<string, unknown> | null>(null);
  const inventoryTask = createLatestTask();
  const deploymentAbort = ref<AbortController | null>(null);
  const deploymentOperationId = ref<string | null>(null);
  const swapOperationId = ref<string | null>(null);
  let pendingReload = false;
  let stopCrossTab: (() => void) | null = null;

  const activeWorkspace = computed(() => workspaces.value.find((item) => item.isActive) ?? null);

  function setDeploy(state: string, message?: string | null): void {
    deployState.value = state;
    deployMessage.value = message ?? null;
  }

  function setSyncSummary(summary: string | null): void {
    syncSummary.value = summary;
  }

  function reset(): void {
    deployState.value = "unknown";
    deployMessage.value = null;
    syncSummary.value = null;
  }

  function setProgress(text: string | null): void {
    progress.value = text;
  }

  async function loadWorkspaces(): Promise<void> {
    const summary = summarizeWorkspaces(await listWorkspaces());
    workspaces.value = summary.rows;
    activeWorkspaceId.value = summary.activeId;
  }

  async function loadDeployment(): Promise<void> {
    deployStatus.value = await getDeployStatus();
    deployState.value = deployStatus.value.state;
    deployMessage.value = deployStatus.value.message || null;
  }

  async function loadInventory(): Promise<void> {
    const result = await inventoryTask.run(async (signal) => {
      const [modelResult, nodeResult] = await Promise.all([listModels(), listCustomNodes()]);
      if (signal.aborted) return null;
      return { modelResult, nodeResult };
    });
    if (result.stale || !result.value) return;
    const modelList = result.value.modelResult.models;
    models.value = (Array.isArray(modelList) ? modelList : []).filter(
      (item): item is Record<string, unknown> => !!item && typeof item === "object",
    );
    const nodeList = result.value.nodeResult.custom_nodes;
    customNodes.value = (Array.isArray(nodeList) ? nodeList : []).filter(
      (item): item is Record<string, unknown> => !!item && typeof item === "object",
    );
  }

  async function load(): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      await Promise.all([loadWorkspaces(), loadDeployment(), loadInventory()]);
      syncSummary.value = "server inventory loaded";
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : "Could not load infrastructure";
      throw cause;
    } finally {
      loading.value = false;
      if (pendingReload) {
        pendingReload = false;
        void load();
      }
    }
  }

  async function initialize(): Promise<void> {
    if (!stopCrossTab) {
      stopCrossTab = createCrossTabInvalidation((kind) => {
        if (kind !== "workspace") return;
        if (loading.value) {
          pendingReload = true;
          return;
        }
        void load();
      });
    }
    if (!workspaces.value.length) await load();
  }

  async function saveWorkspace(payload: Record<string, unknown>): Promise<void> {
    busy.value = true;
    try {
      const envelope = await upsertWorkspace(payload);
      const summary = summarizeWorkspaces(envelope);
      workspaces.value = summary.rows;
      activeWorkspaceId.value = summary.activeId;
      publishCrossTabInvalidation("workspace");
    } finally {
      busy.value = false;
    }
  }

  async function selectWorkspace(id: string): Promise<void> {
    if (deploymentOperationId.value || swapOperationId.value) {
      throw new Error("Cannot change workspace while an operation is active");
    }
    busy.value = true;
    const previous = workspaces.value;
    try {
      const envelope = await activateWorkspace(id);
      if (!envelope || envelope.status !== "ok") {
        throw new Error(String((envelope as Record<string, unknown>)?.message || "Activation failed"));
      }
      const summary = summarizeWorkspaces(envelope);
      workspaces.value = summary.rows;
      activeWorkspaceId.value = summary.activeId;
      setProgress(`Active workspace is now ${summary.rows.find((row) => row.isActive)?.label || id}.`);
      await loadDeployment();
      publishCrossTabInvalidation("workspace");
    } catch (cause) {
      workspaces.value = previous;
      throw cause;
    } finally {
      busy.value = false;
    }
  }

  async function startSwap(targetId: string, extra?: Record<string, unknown>): Promise<void> {
    const operations = useOperationsStore();
    if (deploymentOperationId.value || swapOperationId.value) {
      throw new Error("Another operation is already active");
    }
    busy.value = true;
    swapConfirmRequired.value = false;
    swapReview.value = null;
    const frozenWorkspaceId: string | undefined = activeWorkspaceId.value ?? undefined;
    const operationId = operations.start({
      kind: "workspace-swap",
      label: "Swap workspace",
      workspaceId: frozenWorkspaceId,
    });
    swapOperationId.value = operationId;
    const controller = new AbortController();
    const deadline = window.setTimeout(() => controller.abort(), 30 * 60 * 1000);
    try {
      const data = await requestWorkspaceSwap({ workspace_id: targetId, ...(extra || {}) });
      const status = String(data.status || "");
      if (status === "busy") throw new Error(String(data.message || "Deploy already running — try again later."));
      if (status === "error") throw new Error(String(data.message || "Workspace swap failed."));
      if (status === "confirm_required") {
        swapConfirmRequired.value = true;
        operations.patch(operationId, { status: "pending", message: "Confirmation required" });
        return;
      }
      if (status === "repair_required") {
        operations.fail(operationId, String(data.message || "manifest repair required"));
        await scanRepair();
        throw new Error(String(data.message || "manifest repair required"));
      }
      if (status === "review_required") {
        const toInstall = (Array.isArray(data.to_install) ? data.to_install : []).map((item) => {
          const entry = item as Record<string, unknown>;
          return {
            key: `${String(entry.save_path || entry.folder || "")}/${String(entry.filename || "")}`,
            filename: String(entry.filename || ""),
            folder: String(entry.folder || entry.save_path || ""),
          };
        });
        swapReview.value = {
          workspaceLabel: String(data.workspace_label || targetId),
          toInstall,
          installCount: Number(data.install_count || toInstall.length),
          presentCount: Number(data.present_count || 0),
          removeCount: Array.isArray(data.to_remove) ? (data.to_remove as unknown[]).length : 0,
        };
        operations.patch(operationId, { status: "pending", message: "Review required" });
        return;
      }
      if (status === "started" && data.swap_id) {
        await pollSwap(String(data.swap_id), operationId, controller.signal, frozenWorkspaceId);
        return;
      }
      throw new Error(String(data.message || "Unexpected swap response."));
    } catch (cause) {
      if (swapConfirmRequired.value || swapReview.value) throw cause;
      const message = cause instanceof Error ? cause.message : "Workspace swap failed";
      operations.fail(operationId, message);
      setProgress(message);
      throw cause;
    } finally {
      window.clearTimeout(deadline);
      if (!swapConfirmRequired.value && !swapReview.value) swapOperationId.value = null;
      busy.value = false;
    }
  }

  async function confirmSwapInterrupt(targetId: string): Promise<void> {
    swapConfirmRequired.value = false;
    swapOperationId.value = null;
    await startSwap(targetId, { confirm_prompt_interrupt: true });
  }

  async function confirmSwapReview(targetId: string, selectedKeys: string[]): Promise<void> {
    const pendingId = swapOperationId.value;
    swapReview.value = null;
    swapOperationId.value = null;
    if (pendingId) {
      const operations = useOperationsStore();
      operations.cancel(pendingId, "Superseded by review confirmation");
    }
    await startSwap(targetId, buildSwapConfirmPayload(targetId, selectedKeys));
  }

  async function cancelSwapDialog(): Promise<void> {
    const pendingId = swapOperationId.value;
    swapConfirmRequired.value = false;
    swapReview.value = null;
    swapOperationId.value = null;
    busy.value = false;
    if (pendingId) {
      useOperationsStore().cancel(pendingId, "Swap cancelled.");
    }
    setProgress("Swap cancelled.");
  }

  async function pollSwap(
    swapId: string,
    operationId: string,
    signal: AbortSignal,
    frozenWorkspaceId: string | undefined,
  ): Promise<void> {
    const operations = useOperationsStore();
    try {
      await pollUntil({
        intervalMs: 1000,
        signal,
        run: async () => {
          const data = await getWorkspaceSwapStatus(swapId);
          operations.patch(operationId, { message: swapPhaseMessage(data) || "Working…" });
          setProgress(swapPhaseMessage(data) || "Working…");
          return data;
        },
        done: (data) => String(data.status || "") !== "running",
      }).then((data) => {
        const status = String(data.status || "");
        if (status === "ok") {
          const label = String(data.workspace_label || "workspace");
          operations.finish(operationId, `Swap done — ${label}. Deploy started.`);
          setProgress(`Done — ${label}. Deploy started.`);
        } else if (status === "repair_required") {
          operations.fail(operationId, String(data.message || "manifest repair required"));
          void scanRepair();
          throw new Error(String(data.message || "manifest repair required"));
        } else if (status === "not_found") {
          throw new Error("Swap status unavailable.");
        } else {
          throw new Error(
            String(data.message || data.error || data.deploy_message || "Workspace swap failed"),
          );
        }
      });
      if (frozenWorkspaceId && activeWorkspaceId.value !== frozenWorkspaceId) {
        // The swap retargeted the active workspace; reread everything.
      }
      await loadWorkspaces();
      await loadDeployment();
      publishCrossTabInvalidation("workspace");
    } catch (cause) {
      if (!swapConfirmRequired.value && !swapReview.value) {
        const message = cause instanceof Error ? cause.message : "Workspace swap failed";
        try {
          operations.fail(operationId, message);
        } catch {
          // Already terminal.
        }
        setProgress(message);
      }
      throw cause;
    } finally {
      swapOperationId.value = null;
    }
  }

  async function deploy(): Promise<string> {
    const operations = useOperationsStore();
    if (deploymentOperationId.value) return deploymentOperationId.value;
    if (swapOperationId.value) throw new Error("Cannot deploy while a swap is active");
    const targetWorkspaceId = activeWorkspaceId.value ?? undefined;
    const operationId = operations.start({
      kind: "deploy",
      label: "Deploy workspace",
      workspaceId: targetWorkspaceId,
    });
    deploymentOperationId.value = operationId;
    const controller = new AbortController();
    deploymentAbort.value = controller;
    const deadline = window.setTimeout(() => controller.abort(new DOMException("Deployment polling timed out", "TimeoutError")), 10 * 60 * 1000);
    try {
      await triggerDeploy();
      operations.patch(operationId, { status: "running", message: "Deployment started" });
      const final = await pollUntil({
        intervalMs: 3000,
        signal: controller.signal,
        run: async () => {
          const status = await getDeployStatus();
          deployStatus.value = status;
          deployState.value = status.state;
          deployMessage.value = status.message || null;
          operations.patch(operationId, { message: status.message || `Deployment: ${status.state}` });
          return status;
        },
        done: (status) => status.state === "ready" || status.state === "deployed_unwarmed" || (status.state !== "deploying" && status.state !== "starting" && status.state !== "unknown"),
      });
      if (!isDeployUsable(final.state)) throw new Error(final.message || `Deployment ended in ${final.state}`);
      if (targetWorkspaceId && activeWorkspaceId.value !== targetWorkspaceId) throw new Error("Deployment target workspace changed");
      operations.finish(operationId, final.message || "Deployment completed");
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "Deployment failed";
      operations.fail(operationId, message);
      throw cause;
    } finally {
      window.clearTimeout(deadline);
      deploymentAbort.value = null;
      deploymentOperationId.value = null;
    }
    return operationId;
  }

  async function loadCredentials(): Promise<void> {
    const [auth, hf, civitai] = await Promise.all([
      getAuthStatus().catch(() => null),
      getCredentialStatus("hf").catch(() => null),
      getCredentialStatus("civitai").catch(() => null),
    ]);
    authConnected.value = !!(auth && (auth as Record<string, unknown>).connected === true);
    hfConfigured.value = credentialConfigured(hf);
    civitaiConfigured.value = credentialConfigured(civitai);
  }

  async function saveCredential(kind: "hf" | "civitai", token: string): Promise<string> {
    const response = (await saveCredentialToken(kind, token)) as Record<string, unknown>;
    if (!response || response.status !== "ok") {
      throw new Error(String(response?.message || response?.error || "Save failed."));
    }
    await loadCredentials();
    return token ? "Saved." : "Cleared.";
  }

  async function scanRepair(): Promise<void> {
    repairMessage.value = null;
    const result = await scanManifestIssues();
    repairIssues.value = result;
  }

  async function applyRepair(updates: unknown): Promise<void> {
    repairMessage.value = null;
    const result = await applyManifestRepairs(updates);
    repairMessage.value = String((result as Record<string, unknown>).message || "Repairs applied.");
    repairIssues.value = result;
  }

  async function deletePlaceholder(folder: string, filename: string): Promise<void> {
    await deleteManifestPlaceholder(folder, filename);
    await scanRepair();
  }

  async function loadSyncStatus(): Promise<void> {
    customNodeSync.value = await getCustomNodeSyncStatus();
  }

  async function pushPlugins(): Promise<void> {
    const operations = useOperationsStore();
    const operationId = operations.start({ kind: "node-sync", label: "Push custom-node plugins" });
    try {
      await triggerPushPlugins();
      operations.finish(operationId, "Plugins pushed");
      await loadSyncStatus();
      publishCrossTabInvalidation("workspace");
    } catch (cause) {
      operations.fail(operationId, cause instanceof Error ? cause.message : "Push failed");
      throw cause;
    }
  }

  async function rebuildDependencies(): Promise<void> {
    const operations = useOperationsStore();
    const operationId = operations.start({ kind: "node-sync", label: "Rebuild custom-node dependencies" });
    try {
      const response = await triggerRebuildDependencies();
      const syncId = String((response as Record<string, unknown>).sync_id || (response as Record<string, unknown>).syncId || "");
      if (syncId) {
        await pollUntil({
          intervalMs: 3000,
          run: async () => {
            const status = await getCustomNodeSyncOperationStatus(syncId);
            operations.patch(operationId, { message: String(status.message || "Rebuilding…") });
            return status;
          },
          done: (status) => String(status.status || "") !== "running",
        });
      }
      operations.finish(operationId, "Dependencies rebuilt");
      await loadSyncStatus();
      publishCrossTabInvalidation("workspace");
    } catch (cause) {
      operations.fail(operationId, cause instanceof Error ? cause.message : "Rebuild failed");
      throw cause;
    }
  }

  async function installModel(item: Record<string, unknown>): Promise<void> {
    const operations = useOperationsStore();
    const operationId = operations.start({ kind: "model-download", label: `Download ${String(item.filename || item.url || "model")}` });
    try {
      const response = (await installSingleModel(item)) as Record<string, unknown>;
      const downloadId = String(response.download_id || response.downloadId || "");
      if (!downloadId) {
        operations.finish(operationId, "Install request accepted");
        await loadInventory();
        return;
      }
      await pollUntil({
        intervalMs: 2000,
        run: async () => {
          const status = await modelDownloadStatus(downloadId);
          operations.patch(operationId, {
            progress: typeof status.progress === "number" ? status.progress : undefined,
            message: String(status.message || "Downloading…"),
          });
          return status;
        },
        done: (status) => String(status.status || "") !== "running",
      }).then((status) => {
        if (String(status.status || "") === "error") {
          throw new Error(String(status.message || "Download failed"));
        }
      });
      operations.finish(operationId, "Download complete");
      await loadInventory();
      publishCrossTabInvalidation("workspace");
    } catch (cause) {
      operations.fail(operationId, cause instanceof Error ? cause.message : "Download failed");
      throw cause;
    }
  }

  async function installModelRequest(body: Record<string, unknown>): Promise<void> {
    await requestModelInstall(body);
    await loadInventory();
  }

  async function installCustomNode(body: Record<string, unknown>): Promise<void> {
    await requestCustomNodeInstall(body);
    await loadInventory();
  }

  async function updateModelNotes(modelId: string, body: { notes?: string; tags?: string[]; source_urls?: string[] }): Promise<void> {
    await updateModelRecord(modelId, body as Record<string, unknown>);
    await loadInventory();
  }

  async function refreshRemoteInventoryNow(): Promise<void> {
    await refreshInventory(0);
    await loadInventory();
    syncSummary.value = "inventory refreshed";
    publishCrossTabInvalidation("workspace");
  }

  async function rescanModelsNow(forceRehash = true): Promise<void> {
    const result = await rescanModels(forceRehash);
    models.value = Array.isArray(result.models)
      ? (result.models as unknown[]).filter((item): item is Record<string, unknown> => !!item && typeof item === "object")
      : models.value;
    await loadInventory();
  }

  async function refreshCustomNodesNow(): Promise<void> {
    const result = await refreshCustomNodes();
    customNodes.value = Array.isArray(result.custom_nodes)
      ? (result.custom_nodes as unknown[]).filter((item): item is Record<string, unknown> => !!item && typeof item === "object")
      : customNodes.value;
    await loadInventory();
  }

  async function loadLog(): Promise<void> {
    deployLog.value = await getDeployLog();
  }

  async function loadHealth(): Promise<void> {
    health.value = await getRuntimeHealth();
  }

  return {
    deployState, deployMessage, syncSummary, workspaces, activeWorkspaceId, activeWorkspace,
    deployStatus, deployLog, models, modelTypes, customNodes, customNodeSync,
    loading, error, busy, progress, swapReview, swapConfirmRequired,
    authConnected, hfConfigured, civitaiConfigured,
    repairIssues, repairMessage, health,
    deploymentOperationId, swapOperationId,
    setDeploy, setSyncSummary, reset, load, initialize,
    loadWorkspaces, loadDeployment, loadInventory,
    saveWorkspace, selectWorkspace,
    startSwap, confirmSwapInterrupt, confirmSwapReview, cancelSwapDialog,
    deploy, loadCredentials, saveCredential,
    scanRepair, applyRepair, deletePlaceholder,
    loadSyncStatus, pushPlugins, rebuildDependencies,
    installModel, installModelRequest, installCustomNode, updateModelNotes,
    refreshRemoteInventoryNow, rescanModelsNow,
    refreshCustomNodesNow, loadLog, loadHealth,
  };
});
