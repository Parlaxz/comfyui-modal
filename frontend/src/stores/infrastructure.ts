// Infrastructure domain authority: workspaces, deployment, inventory, and
// shared model/custom-node state. Operations are domain-owned; the shared
// operationsStore receives only visible summaries.
import { defineStore } from "pinia";
import { computed, ref } from "vue";
import {
  activateWorkspace, getDeployLog, getDeployStatus, listCustomNodes,
  listModels, listWorkspaces, normalizeDeployStatus, refreshCustomNodes,
  refreshInventory, rescanModels, summarizeWorkspaces, triggerDeploy, isDeployUsable,
  type DeployStatus, type WorkspaceSummary,
} from "../api/infrastructure";
import { createCrossTabInvalidation, publishCrossTabInvalidation } from "../compatibility/crossTab";
import { createLatestTask } from "../async/latest";
import { pollUntil } from "../async/polling";
import { useOperationsStore } from "./operations";

export const useInfrastructureStore = defineStore("studio-infrastructure", () => {
  const deployState = ref("unknown");
  const deployMessage = ref<string | null>(null);
  const syncSummary = ref<string | null>(null);
  const workspaces = ref<WorkspaceSummary[]>([]);
  const activeWorkspaceId = ref<string | null>(null);
  const deployStatus = ref<DeployStatus>(normalizeDeployStatus(null));
  const deployLog = ref<unknown>(null);
  const models = ref<unknown[]>([]);
  const customNodes = ref<unknown[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);
  const inventoryTask = createLatestTask();
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
    models.value = result.value.modelResult.models ?? [];
    customNodes.value = result.value.nodeResult.custom_nodes ?? [];
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
    }
  }

  async function initialize(): Promise<void> {
    if (!stopCrossTab) {
      stopCrossTab = createCrossTabInvalidation((kind) => {
        if (kind === "workspace" && !loading.value) void load();
      });
    }
    if (!workspaces.value.length) await load();
  }

  async function selectWorkspace(id: string): Promise<void> {
    await activateWorkspace(id);
    await loadWorkspaces();
    publishCrossTabInvalidation("workspace");
  }

  async function deploy(): Promise<string> {
    const operations = useOperationsStore();
    const operationId = operations.start({ kind: "deploy", label: "Deploy workspace" });
    try {
      await triggerDeploy();
      operations.patch(operationId, { status: "running", message: "Deployment started" });
      const final = await pollUntil({
        intervalMs: 3000,
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
      operations.finish(operationId, final.message || "Deployment completed");
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "Deployment failed";
      operations.fail(operationId, message);
      throw cause;
    }
    return operationId;
  }

  async function refreshRemoteInventoryNow(): Promise<void> {
    await refreshInventory(0);
    await loadInventory();
    syncSummary.value = "inventory refreshed";
    publishCrossTabInvalidation("workspace");
  }

  async function rescanModelsNow(): Promise<void> {
    const result = await rescanModels(true);
    models.value = result.models ?? models.value;
    await loadInventory();
  }

  async function refreshCustomNodesNow(): Promise<void> {
    const result = await refreshCustomNodes();
    customNodes.value = result.custom_nodes ?? customNodes.value;
    await loadInventory();
  }

  async function loadLog(): Promise<void> {
    deployLog.value = await getDeployLog();
  }

  return {
    deployState, deployMessage, syncSummary, workspaces, activeWorkspaceId, activeWorkspace,
    deployStatus, deployLog, models, customNodes, loading, error,
    setDeploy, setSyncSummary, reset, load, initialize, loadWorkspaces, loadDeployment,
    loadInventory, selectWorkspace, deploy, refreshRemoteInventoryNow, rescanModelsNow,
    refreshCustomNodesNow, loadLog,
  };
});
