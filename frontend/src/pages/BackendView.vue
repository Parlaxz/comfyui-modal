<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ServerCog, RefreshCw } from "@lucide/vue";
import { useInfrastructureStore } from "../stores/infrastructure";
import StudioButton from "../components/StudioButton.vue";
import StudioCard from "../components/StudioCard.vue";
import { studioPageClass } from "../components/studioPanels";

const infrastructure = useInfrastructureStore();
const tab = ref<"workspaces" | "deployment" | "models" | "nodes">("workspaces");
const selectedWorkspace = ref("");
const formOpen = ref(false);
const formLabel = ref("");
const formTokenId = ref("");
const formTokenSecret = ref("");
const formError = ref("");
const editingId = ref("");
const reviewKeys = ref<string[]>([]);
const hfToken = ref("");
const civitaiToken = ref("");
const credentialMessage = ref("");
const modelSearch = ref("");
const modelUrl = ref("");
const modelFolder = ref("diffusion_models");
const showLog = ref(false);

onMounted(async () => {
  await infrastructure.initialize().catch(() => undefined);
  await Promise.all([
    infrastructure.loadCredentials().catch(() => undefined),
    infrastructure.loadSyncStatus().catch(() => undefined),
  ]);
});

async function chooseWorkspace() {
  if (selectedWorkspace.value) {
    await infrastructure.selectWorkspace(selectedWorkspace.value).catch(() => undefined);
  }
}

function openAddForm() {
  editingId.value = "";
  formLabel.value = "";
  formTokenId.value = "";
  formTokenSecret.value = "";
  formError.value = "";
  formOpen.value = true;
}

function openEditForm() {
  const row = infrastructure.workspaces.find((item) => item.id === selectedWorkspace.value);
  if (!row) return;
  editingId.value = row.id;
  formLabel.value = row.label;
  formTokenId.value = "";
  formTokenSecret.value = "";
  formError.value = "";
  formOpen.value = true;
}

async function saveWorkspaceForm() {
  formError.value = "";
  if (!formLabel.value.trim()) {
    formError.value = "Workspace label required.";
    return;
  }
  if (!editingId.value && (!formTokenId.value.trim() || !formTokenSecret.value.trim())) {
    formError.value = "Token ID and Token Secret are required.";
    return;
  }
  try {
    await infrastructure.saveWorkspace(
      editingId.value
        ? { workspace_id: editingId.value, label: formLabel.value.trim(), token_id: formTokenId.value.trim(), token_secret: formTokenSecret.value.trim(), set_active: false }
        : { label: formLabel.value.trim(), token_id: formTokenId.value.trim(), token_secret: formTokenSecret.value.trim(), set_active: false },
    );
    formOpen.value = false;
  } catch (cause) {
    formError.value = cause instanceof Error ? cause.message : "Save failed.";
  }
}

async function startSwap() {
  if (selectedWorkspace.value) {
    await infrastructure.startSwap(selectedWorkspace.value).catch(() => undefined);
  }
}

async function confirmReview() {
  await infrastructure.confirmSwapReview(selectedWorkspace.value, reviewKeys.value).catch(() => undefined);
}

async function deploy() {
  await infrastructure.deploy().catch(() => undefined);
}

async function saveCredential(kind: "hf" | "civitai") {
  credentialMessage.value = "";
  try {
    const message = await infrastructure.saveCredential(kind, kind === "hf" ? hfToken.value : civitaiToken.value);
    credentialMessage.value = message;
    hfToken.value = "";
    civitaiToken.value = "";
  } catch (cause) {
    credentialMessage.value = cause instanceof Error ? cause.message : "Save failed.";
  }
}

async function installFromUrl() {
  if (!modelUrl.value.trim()) return;
  await infrastructure.installModel({ url: modelUrl.value.trim(), folder: modelFolder.value }).catch(() => undefined);
  modelUrl.value = "";
}
</script>

<template>
  <section :class="studioPageClass()" data-testid="vue-page-backend">
    <div v-if="infrastructure.error" class="cmst:rounded-md cmst:border cmst:border-solid cmst:border-red-400 cmst:p-3 cmst:text-sm cmst:text-red-300" role="alert">
      {{ infrastructure.error }}
    </div>

    <StudioCard class="cmst:p-4">
      <div class="cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-3">
        <div>
          <h2 class="cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2">
            <ServerCog class="cmst:size-5" aria-hidden="true" />
            Manage Modal
          </h2>
          <p class="cmst:text-sm cmst:opacity-80">Route key remains <code>backend</code>. Server truth only.</p>
        </div>
        <div class="cmst:flex cmst:gap-2">
          <StudioButton
            v-for="id in (['workspaces', 'deployment', 'models', 'nodes'] as const)"
            :key="id"
            :variant="tab === id ? 'default' : 'outline'"
            size="sm"
            :data-testid="`vue-backend-tab-${id}`"
            @click="tab = id"
          >
            {{ id }}
          </StudioButton>
          <StudioButton variant="outline" size="icon" aria-label="Reload infrastructure" :disabled="infrastructure.loading" @click="infrastructure.load()">
            <RefreshCw class="cmst:size-4" :class="infrastructure.loading ? 'cmst:animate-spin' : ''" aria-hidden="true" />
          </StudioButton>
        </div>
      </div>
      <p v-if="infrastructure.progress" class="cmst:mt-2 cmst:text-sm" data-testid="vue-backend-progress">{{ infrastructure.progress }}</p>
    </StudioCard>

    <template v-if="tab === 'workspaces'">
      <StudioCard class="cmst:p-4">
        <h3 class="cmst:text-sm cmst:font-semibold">Workspaces</h3>
        <div class="cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-2 cmst:sm:grid-cols-2">
          <button
            v-for="workspace in infrastructure.workspaces"
            :key="workspace.id"
            type="button"
            class="cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:p-3 cmst:text-left cmst:hover:bg-cmst-secondary"
            :data-testid="`vue-workspace-${workspace.id}`"
            @click="selectedWorkspace = workspace.id"
          >
            <strong>{{ workspace.label }}</strong>
            <span class="cmst:block cmst:text-xs cmst:opacity-70">
              {{ workspace.isActive ? "Active workspace" : `Idle · last deploy: ${workspace.lastDeployStatus}` }}
            </span>
          </button>
        </div>
        <div class="cmst:mt-3 cmst:flex cmst:flex-wrap cmst:gap-2">
          <StudioButton size="sm" variant="secondary" :disabled="!selectedWorkspace || infrastructure.busy" data-testid="vue-workspace-activate" @click="chooseWorkspace">Set Active</StudioButton>
          <StudioButton size="sm" variant="outline" :disabled="infrastructure.busy" @click="openAddForm">+ Add Workspace</StudioButton>
          <StudioButton size="sm" variant="outline" :disabled="!selectedWorkspace || infrastructure.busy" @click="openEditForm">Edit Workspace</StudioButton>
          <StudioButton size="sm" :disabled="!selectedWorkspace || infrastructure.busy" data-testid="vue-workspace-swap" @click="startSwap">Swap Workspace</StudioButton>
        </div>
        <div v-if="formOpen" class="cmst:mt-3 cmst:max-w-md cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:p-3" data-testid="vue-workspace-form">
          <label class="cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm">Label<input v-model="formLabel" class="cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:px-2" /></label>
          <label class="cmst:mt-2 cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm">Token ID<input v-model="formTokenId" class="cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:px-2" placeholder="ak-…" /></label>
          <label class="cmst:mt-2 cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm">Token Secret<input v-model="formTokenSecret" type="password" class="cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-surface cmst:px-2" placeholder="as-…" /></label>
          <p v-if="formError" class="cmst:mt-2 cmst:text-xs cmst:text-red-300" role="alert">{{ formError }}</p>
          <div class="cmst:mt-2 cmst:flex cmst:gap-2">
            <StudioButton size="sm" data-testid="vue-workspace-save" @click="saveWorkspaceForm">Save Workspace</StudioButton>
            <StudioButton size="sm" variant="ghost" @click="formOpen = false">Cancel</StudioButton>
          </div>
        </div>
        <div v-if="infrastructure.swapConfirmRequired" class="cmst:mt-3 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:p-3" data-testid="vue-swap-confirm">
          <p class="cmst:text-sm">A prompt is still running. Switch workspaces anyway?</p>
          <div class="cmst:mt-2 cmst:flex cmst:gap-2">
            <StudioButton size="sm" data-testid="vue-swap-confirm-yes" @click="infrastructure.confirmSwapInterrupt(selectedWorkspace)">Interrupt and Switch</StudioButton>
            <StudioButton size="sm" variant="ghost" @click="infrastructure.cancelSwapDialog()">Cancel</StudioButton>
          </div>
        </div>
        <div v-if="infrastructure.swapReview" class="cmst:mt-3 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:p-3" data-testid="vue-swap-review">
          <p class="cmst:text-sm">Select models to download to {{ infrastructure.swapReview.workspaceLabel }}:</p>
          <label v-for="item in infrastructure.swapReview.toInstall" :key="item.key" class="cmst:mt-1 cmst:flex cmst:items-center cmst:gap-2 cmst:text-sm">
            <input v-model="reviewKeys" type="checkbox" :value="item.key" />
            {{ item.filename }} ({{ item.folder }})
          </label>
          <div class="cmst:mt-2 cmst:flex cmst:gap-2">
            <StudioButton size="sm" data-testid="vue-swap-review-go" @click="confirmReview">Start Swap</StudioButton>
            <StudioButton size="sm" variant="ghost" @click="infrastructure.cancelSwapDialog()">Cancel</StudioButton>
          </div>
        </div>
      </StudioCard>

      <StudioCard class="cmst:p-4">
        <h3 class="cmst:text-sm cmst:font-semibold">Accounts &amp; Tokens</h3>
        <p class="cmst:mt-1 cmst:text-sm cmst:opacity-80">
          Modal connection: <strong data-testid="vue-auth-status">{{ infrastructure.authConnected === null ? "unknown" : infrastructure.authConnected ? "connected" : "not configured" }}</strong>
        </p>
        <div class="cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-2">
          <div>
            <p class="cmst:text-sm">HuggingFace: <strong data-testid="vue-cred-hf-state">{{ infrastructure.hfConfigured ? "configured" : "not configured" }}</strong></p>
            <div class="cmst:mt-1 cmst:flex cmst:gap-2">
              <input v-model="hfToken" type="password" placeholder="hf_..." class="cmst:h-9 cmst:flex-1 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2" data-testid="vue-cred-hf-input" />
              <StudioButton size="sm" data-testid="vue-cred-hf-save" @click="saveCredential('hf')">Save</StudioButton>
            </div>
          </div>
          <div>
            <p class="cmst:text-sm">Civitai: <strong data-testid="vue-cred-civitai-state">{{ infrastructure.civitaiConfigured ? "configured" : "not configured" }}</strong></p>
            <div class="cmst:mt-1 cmst:flex cmst:gap-2">
              <input v-model="civitaiToken" type="password" placeholder="Civitai API Key" class="cmst:h-9 cmst:flex-1 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2" data-testid="vue-cred-civitai-input" />
              <StudioButton size="sm" data-testid="vue-cred-civitai-save" @click="saveCredential('civitai')">Save</StudioButton>
            </div>
          </div>
        </div>
        <p v-if="credentialMessage" class="cmst:mt-2 cmst:text-xs">{{ credentialMessage }}</p>
      </StudioCard>

      <StudioCard class="cmst:p-4">
        <div class="cmst:flex cmst:items-center cmst:justify-between">
          <h3 class="cmst:text-sm cmst:font-semibold">Manifest repair</h3>
          <StudioButton size="sm" variant="outline" data-testid="vue-repair-scan" @click="infrastructure.scanRepair()">Scan issues</StudioButton>
        </div>
        <pre v-if="infrastructure.repairIssues" class="cmst:mt-2 cmst:max-h-48 cmst:overflow-auto cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-xs">{{ JSON.stringify(infrastructure.repairIssues, null, 2) }}</pre>
        <p v-if="infrastructure.repairMessage" class="cmst:mt-2 cmst:text-xs">{{ infrastructure.repairMessage }}</p>
      </StudioCard>
    </template>

    <template v-if="tab === 'deployment'">
      <StudioCard class="cmst:p-4">
        <div class="cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-3">
          <div>
            <h3 class="cmst:text-sm cmst:font-semibold">Deployment readiness</h3>
            <p class="cmst:mt-1 cmst:text-sm">State: <strong data-testid="vue-deploy-state">{{ infrastructure.deployStatus.state }}</strong></p>
            <p v-if="infrastructure.deployMessage" class="cmst:text-sm cmst:opacity-80">{{ infrastructure.deployMessage }}</p>
          </div>
          <div class="cmst:flex cmst:flex-wrap cmst:gap-2">
            <StudioButton size="sm" :disabled="infrastructure.loading || !!infrastructure.deploymentOperationId" data-testid="vue-deploy" @click="deploy">Deploy</StudioButton>
            <StudioButton size="sm" variant="outline" data-testid="vue-deploy-refresh" @click="infrastructure.loadDeployment()">Refresh Status</StudioButton>
            <StudioButton size="sm" variant="outline" @click="showLog = !showLog">{{ showLog ? "Hide" : "Show" }} Log</StudioButton>
          </div>
        </div>
        <pre v-if="showLog" class="cmst:mt-3 cmst:max-h-48 cmst:overflow-auto cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-xs">{{ infrastructure.deployLog ?? "Loading…" }}</pre>
        <StudioButton v-if="showLog && !infrastructure.deployLog" class="cmst:mt-2" size="sm" variant="ghost" @click="infrastructure.loadLog()">Load deployment log</StudioButton>
      </StudioCard>

      <StudioCard class="cmst:p-4">
        <div class="cmst:flex cmst:items-center cmst:justify-between">
          <h3 class="cmst:text-sm cmst:font-semibold">Custom-node sync</h3>
          <StudioButton size="sm" variant="outline" @click="infrastructure.loadSyncStatus()">Refresh status</StudioButton>
        </div>
        <pre v-if="infrastructure.customNodeSync" class="cmst:mt-2 cmst:max-h-48 cmst:overflow-auto cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-xs">{{ JSON.stringify(infrastructure.customNodeSync, null, 2) }}</pre>
        <div class="cmst:mt-2 cmst:flex cmst:flex-wrap cmst:gap-2">
          <StudioButton size="sm" variant="outline" data-testid="vue-node-push" @click="infrastructure.pushPlugins()">Push plugins (FAST)</StudioButton>
          <StudioButton size="sm" variant="outline" data-testid="vue-node-rebuild" @click="infrastructure.rebuildDependencies()">Rebuild dependencies (SLOW)</StudioButton>
        </div>
      </StudioCard>
    </template>

    <template v-if="tab === 'models'">
      <StudioCard class="cmst:p-4">
        <div class="cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-2">
          <h3 class="cmst:text-sm cmst:font-semibold">Models ({{ infrastructure.models.length }})</h3>
          <div class="cmst:flex cmst:gap-2">
            <input v-model="modelSearch" class="cmst:h-9 cmst:w-48 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm" placeholder="Search models" @keyup.enter="infrastructure.loadInventory()" />
            <StudioButton size="sm" variant="outline" @click="infrastructure.rescanModelsNow(true)">Rescan</StudioButton>
          </div>
        </div>
        <ul class="cmst:mt-3 cmst:flex cmst:max-h-64 cmst:flex-col cmst:gap-1 cmst:overflow-auto cmst:text-sm" data-testid="vue-models-list">
          <li v-for="(model, index) in infrastructure.models" :key="index" class="cmst:rounded cmst:bg-cmst-bg cmst:px-2 cmst:py-1 cmst:text-xs">
            {{ String(model.filename || model.name || model.id || `model ${index}`) }}
            <span class="cmst:opacity-60"> · {{ String(model.folder || model.type || "") }}</span>
          </li>
        </ul>
        <div class="cmst:mt-3 cmst:flex cmst:flex-wrap cmst:gap-2">
          <input v-model="modelUrl" class="cmst:h-9 cmst:flex-1 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm" placeholder="Paste a direct model link" data-testid="vue-model-url" />
          <select v-model="modelFolder" class="cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm">
            <option value="diffusion_models">diffusion_models</option>
            <option value="vae">vae</option>
            <option value="clip">clip</option>
            <option value="loras">loras</option>
            <option value="upscale_models">upscale_models</option>
          </select>
          <StudioButton size="sm" data-testid="vue-model-install" @click="installFromUrl">Install</StudioButton>
        </div>
      </StudioCard>
    </template>

    <template v-if="tab === 'nodes'">
      <StudioCard class="cmst:p-4">
        <div class="cmst:flex cmst:items-center cmst:justify-between">
          <h3 class="cmst:text-sm cmst:font-semibold">Custom nodes ({{ infrastructure.customNodes.length }})</h3>
          <StudioButton size="sm" variant="outline" @click="infrastructure.refreshCustomNodesNow()">Refresh registry</StudioButton>
        </div>
        <ul class="cmst:mt-3 cmst:flex cmst:max-h-64 cmst:flex-col cmst:gap-1 cmst:overflow-auto cmst:text-sm" data-testid="vue-nodes-list">
          <li v-for="(node, index) in infrastructure.customNodes" :key="index" class="cmst:rounded cmst:bg-cmst-bg cmst:px-2 cmst:py-1 cmst:text-xs">
            {{ String(node.title || node.id || node.name || `node ${index}`) }}
          </li>
        </ul>
      </StudioCard>
    </template>
  </section>
</template>
