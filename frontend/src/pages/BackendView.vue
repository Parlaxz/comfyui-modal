<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { RefreshCw } from "@lucide/vue";
import { useInfrastructureStore } from "../stores/infrastructure";
import { inferModelFilename } from "../api/infrastructure";
import StudioButton from "../components/StudioButton.vue";
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
const nodeSearch = ref("");
const modelUrl = ref("");
const modelFolder = ref("diffusion_models");
const modelInstallMessage = ref("");
const showLog = ref(false);

const TABS = ["workspaces", "deployment", "models", "nodes"] as const;

onMounted(async () => {
  await infrastructure.initialize().catch(() => undefined);
  await Promise.all([
    infrastructure.loadCredentials().catch(() => undefined),
    infrastructure.loadSyncStatus().catch(() => undefined),
  ]);
});

// Restrained dot for the Ready/Deploying/Failed/Idle hierarchy — words carry
// the state, the dot only tints it.
function deployDot(state: string): string {
  const s = state.toLowerCase();
  if (s === "ready" || s === "deployed" || s === "deployed_unwarmed" || s === "complete" || s === "completed" || s === "success") return "cmst:bg-cmst-ok";
  if (s === "failed" || s === "error") return "cmst:bg-cmst-danger";
  if (s === "deploying" || s === "running" || s === "pending" || s === "syncing" || s === "warming" || s === "unknown") return "cmst:bg-cmst-warn";
  return "cmst:bg-cmst-muted";
}

const deployProgress = computed(() => {
  const raw: unknown = (infrastructure.deployStatus as Record<string, unknown>)?.progress;
  if (typeof raw !== "number" || Number.isNaN(raw)) return null;
  return Math.min(100, Math.max(0, Math.round(raw <= 1 ? raw * 100 : raw)));
});

const filteredNodes = computed(() => {
  const query = nodeSearch.value.trim().toLowerCase();
  if (!query) return infrastructure.customNodes;
  return infrastructure.customNodes.filter((node) =>
    String(node.title || node.id || node.name || "").toLowerCase().includes(query),
  );
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
  modelInstallMessage.value = "Installing…";
  try {
    const url = modelUrl.value.trim();
    await infrastructure.installModel({ url, filename: inferModelFilename(url), save_path: modelFolder.value });
    modelInstallMessage.value = "Install request accepted.";
  } catch (cause) {
    modelInstallMessage.value = cause instanceof Error ? cause.message : "Install failed.";
  }
  modelUrl.value = "";
}
</script>

<template>
  <section :class="studioPageClass('cmst:mx-auto cmst:w-full cmst:max-w-6xl')" data-testid="vue-page-backend">
    <div v-if="infrastructure.error" class="cmst:text-[13px] cmst:text-cmst-danger" role="alert">
      {{ infrastructure.error }}
    </div>

    <!-- Page toolbar: title + reload flush on the page background. -->
    <div class="cmst:flex cmst:flex-wrap cmst:items-end cmst:justify-between cmst:gap-3">
      <div>
        <h1 class="cmst-type-view">Manage Modal</h1>
      </div>
      <StudioButton variant="ghost" size="icon" aria-label="Reload infrastructure" :disabled="infrastructure.loading" @click="infrastructure.load()">
        <RefreshCw class="cmst:size-4" :class="infrastructure.loading ? 'cmst:animate-spin' : ''" aria-hidden="true" />
      </StudioButton>
    </div>
    <p v-if="infrastructure.progress" class="cmst-type-meta" data-testid="vue-backend-progress" role="status">{{ infrastructure.progress }}</p>

    <!-- Section switch: one segmented track (shared pattern). -->
    <div class="cmst-seg" role="tablist" aria-label="Backend sections">
      <button
        v-for="id in TABS"
        :key="id"
        type="button"
        role="tab"
        class="cmst-seg-btn cmst:capitalize"
        :data-active="tab === id"
        :aria-selected="tab === id"
        :data-testid="`vue-backend-tab-${id}`"
        @click="tab = id"
      >
        {{ id }}
      </button>
    </div>

    <template v-if="tab === 'workspaces'">
      <!-- Workspaces as manageable objects: hairline rows, active obvious. -->
      <div role="listbox" aria-label="Workspaces" class="cmst:min-w-0">
        <button
          v-for="workspace in infrastructure.workspaces"
          :key="workspace.id"
          type="button"
          role="option"
          class="cmst-object-row"
          :aria-selected="selectedWorkspace === workspace.id"
          :data-testid="`vue-workspace-${workspace.id}`"
          @click="selectedWorkspace = workspace.id"
        >
          <span class="cmst:flex cmst:items-center cmst:gap-1.5">
            <span class="cmst-status-dot" :class="workspace.isActive ? 'cmst:bg-cmst-ok' : 'cmst:bg-cmst-muted'" aria-hidden="true" />
            <strong class="cmst-type-object cmst:truncate">{{ workspace.label }}</strong>
          </span>
          <span class="cmst-type-meta cmst:mt-0.5 cmst:block cmst:truncate">
            {{ workspace.isActive ? "Active" : "Idle" }} · last deploy: {{ workspace.lastDeployStatus }}
          </span>
        </button>
        <p v-if="!infrastructure.workspaces.length" class="cmst:py-4 cmst:text-[13px] cmst:text-cmst-muted">
          No workspaces returned by the server.
        </p>
      </div>
      <div class="cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-1.5">
        <StudioButton size="sm" variant="secondary" :disabled="!selectedWorkspace || infrastructure.busy" data-testid="vue-workspace-activate" @click="chooseWorkspace">Set Active</StudioButton>
        <StudioButton size="sm" variant="outline" :disabled="infrastructure.busy" @click="openAddForm">Add workspace</StudioButton>
        <StudioButton size="sm" variant="ghost" :disabled="!selectedWorkspace || infrastructure.busy" @click="openEditForm">Edit</StudioButton>
        <StudioButton size="sm" variant="ghost" :disabled="!selectedWorkspace || infrastructure.busy" data-testid="vue-workspace-swap" @click="startSwap">Swap</StudioButton>
      </div>

      <section v-if="formOpen" aria-label="Workspace form" class="cmst:mt-3 cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:pt-3" data-testid="vue-workspace-form">
        <h3 class="cmst-type-section">{{ editingId ? "Edit workspace" : "Add workspace" }}</h3>
        <div class="cmst:mt-3 cmst:flex cmst:max-w-md cmst:flex-col cmst:gap-2.5">
          <label class="cmst-field-label">Label<input v-model="formLabel" class="cmst-field" /></label>
          <label class="cmst-field-label">Token ID<input v-model="formTokenId" class="cmst-field cmst:font-mono" placeholder="ak-…" /></label>
          <label class="cmst-field-label">Token Secret<input v-model="formTokenSecret" type="password" class="cmst-field cmst:font-mono" placeholder="as-…" /></label>
        </div>
        <p v-if="formError" class="cmst:mt-2 cmst:text-xs cmst:text-cmst-danger" role="alert">{{ formError }}</p>
        <div class="cmst:mt-3 cmst:flex cmst:gap-1.5">
          <StudioButton size="sm" data-testid="vue-workspace-save" @click="saveWorkspaceForm">Save workspace</StudioButton>
          <StudioButton size="sm" variant="ghost" @click="formOpen = false">Cancel</StudioButton>
        </div>
      </section>

      <div v-if="infrastructure.swapConfirmRequired" class="cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:pt-3" data-testid="vue-swap-confirm">
        <p class="cmst:text-[13px]">A prompt is still running. Switch workspaces anyway?</p>
        <div class="cmst:mt-2 cmst:flex cmst:gap-1.5">
          <StudioButton size="sm" data-testid="vue-swap-confirm-yes" @click="infrastructure.confirmSwapInterrupt(selectedWorkspace)">Interrupt and switch</StudioButton>
          <StudioButton size="sm" variant="ghost" @click="infrastructure.cancelSwapDialog()">Cancel</StudioButton>
        </div>
      </div>
      <div v-if="infrastructure.swapReview" class="cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:pt-3" data-testid="vue-swap-review">
        <p class="cmst:text-[13px]">Select models to download to {{ infrastructure.swapReview.workspaceLabel }}:</p>
        <label v-for="item in infrastructure.swapReview.toInstall" :key="item.key" class="cmst:mt-1 cmst:flex cmst:cursor-pointer cmst:items-center cmst:gap-2 cmst:text-[13px]">
          <input v-model="reviewKeys" type="checkbox" :value="item.key" />
          <span class="cmst-type-meta">{{ item.filename }} · {{ item.folder }}</span>
        </label>
        <div class="cmst:mt-2 cmst:flex cmst:gap-1.5">
          <StudioButton size="sm" data-testid="vue-swap-review-go" @click="confirmReview">Start swap</StudioButton>
          <StudioButton size="sm" variant="ghost" @click="infrastructure.cancelSwapDialog()">Cancel</StudioButton>
        </div>
      </div>

      <section aria-label="Accounts and tokens" class="cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:pt-4">
        <h3 class="cmst-type-section">Accounts &amp; tokens</h3>
        <p class="cmst:mt-1 cmst:flex cmst:items-center cmst:gap-1.5 cmst:text-[13px]">
          <span class="cmst-status-dot" :class="infrastructure.authConnected ? 'cmst:bg-cmst-ok' : 'cmst:bg-cmst-muted'" aria-hidden="true" />
          Modal connection:
          <strong data-testid="vue-auth-status">{{ infrastructure.authConnected === null ? "unknown" : infrastructure.authConnected ? "connected" : "not configured" }}</strong>
        </p>
        <div class="cmst:mt-1">
          <div class="cmst-setting-row">
            <div class="cmst:min-w-0">
              <p class="cmst:text-[13px] cmst:font-medium">HuggingFace · <span data-testid="vue-cred-hf-state">{{ infrastructure.hfConfigured ? "configured" : "not configured" }}</span></p>
            </div>
            <div class="cmst:flex cmst:gap-1.5">
              <input v-model="hfToken" type="password" placeholder="hf_..." aria-label="HuggingFace token" class="cmst-field cmst:w-44" data-testid="vue-cred-hf-input" />
              <StudioButton size="sm" variant="secondary" data-testid="vue-cred-hf-save" @click="saveCredential('hf')">Save</StudioButton>
            </div>
          </div>
          <div class="cmst-setting-row">
            <div class="cmst:min-w-0">
              <p class="cmst:text-[13px] cmst:font-medium">Civitai · <span data-testid="vue-cred-civitai-state">{{ infrastructure.civitaiConfigured ? "configured" : "not configured" }}</span></p>
            </div>
            <div class="cmst:flex cmst:gap-1.5">
              <input v-model="civitaiToken" type="password" placeholder="Civitai API key" aria-label="Civitai token" class="cmst-field cmst:w-44" data-testid="vue-cred-civitai-input" />
              <StudioButton size="sm" variant="secondary" data-testid="vue-cred-civitai-save" @click="saveCredential('civitai')">Save</StudioButton>
            </div>
          </div>
        </div>
        <p v-if="credentialMessage" class="cmst:mt-2 cmst:text-xs cmst:text-cmst-muted" role="status">{{ credentialMessage }}</p>
      </section>

      <section aria-label="Manifest repair" class="cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:pt-4">
        <div class="cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-2">
          <h3 class="cmst-type-section">Manifest repair</h3>
          <StudioButton size="sm" variant="ghost" data-testid="vue-repair-scan" @click="infrastructure.scanRepair()">Scan issues</StudioButton>
        </div>
        <pre v-if="infrastructure.repairIssues" class="cmst:mt-2 cmst:max-h-48 cmst:overflow-auto cmst:rounded cmst:bg-cmst-matte cmst:p-2 cmst:font-mono cmst:text-xs cmst:text-cmst-secondary-text">{{ JSON.stringify(infrastructure.repairIssues, null, 2) }}</pre>
        <p v-if="infrastructure.repairMessage" class="cmst:mt-2 cmst:text-xs cmst:text-cmst-muted" role="status">{{ infrastructure.repairMessage }}</p>
      </section>
    </template>

    <template v-if="tab === 'deployment'">
      <section aria-label="Deployment readiness">
        <div class="cmst:flex cmst:flex-wrap cmst:items-start cmst:justify-between cmst:gap-3">
          <div class="cmst:min-w-0">
            <h3 class="cmst-type-section">Deployment readiness</h3>
            <p class="cmst:mt-1.5 cmst:flex cmst:items-center cmst:gap-1.5 cmst:text-[13px]">
              <span class="cmst-status-dot" :class="deployDot(infrastructure.deployStatus.state)" aria-hidden="true" />
              <strong data-testid="vue-deploy-state">{{ infrastructure.deployStatus.state }}</strong>
            </p>
            <p v-if="infrastructure.deployMessage" class="cmst:mt-1 cmst:text-[13px] cmst:text-cmst-muted">{{ infrastructure.deployMessage }}</p>
            <div v-if="deployProgress !== null" class="cmst:mt-2 cmst:w-56 cmst:max-w-full">
              <div class="cmst-progress-track" role="progressbar" :aria-valuenow="deployProgress" aria-valuemin="0" aria-valuemax="100">
                <div class="cmst-progress-fill" :style="{ width: `${deployProgress}%` }" />
              </div>
            </div>
          </div>
          <div class="cmst:flex cmst:flex-wrap cmst:gap-1.5">
            <StudioButton size="sm" :disabled="infrastructure.loading || !!infrastructure.deploymentOperationId" data-testid="vue-deploy" @click="deploy">Deploy</StudioButton>
            <StudioButton size="sm" variant="outline" data-testid="vue-deploy-refresh" @click="infrastructure.loadDeployment()">Refresh status</StudioButton>
            <StudioButton size="sm" variant="ghost" @click="showLog = !showLog">{{ showLog ? "Hide" : "Show" }} log</StudioButton>
          </div>
        </div>
        <pre v-if="showLog" class="cmst:mt-3 cmst:max-h-48 cmst:overflow-auto cmst:rounded cmst:bg-cmst-matte cmst:p-2 cmst:font-mono cmst:text-xs cmst:text-cmst-secondary-text">{{ infrastructure.deployLog ?? "Loading…" }}</pre>
        <div v-if="showLog && !infrastructure.deployLog" class="cmst:mt-2">
          <StudioButton size="sm" variant="ghost" @click="infrastructure.loadLog()">Load deployment log</StudioButton>
        </div>
      </section>

      <section aria-label="Custom-node sync" class="cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:pt-4">
        <div class="cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-2">
          <h3 class="cmst-type-section">Custom-node sync</h3>
          <StudioButton size="sm" variant="ghost" @click="infrastructure.loadSyncStatus()">Refresh status</StudioButton>
        </div>
        <pre v-if="infrastructure.customNodeSync" class="cmst:mt-2 cmst:max-h-48 cmst:overflow-auto cmst:rounded cmst:bg-cmst-matte cmst:p-2 cmst:font-mono cmst:text-xs cmst:text-cmst-secondary-text">{{ JSON.stringify(infrastructure.customNodeSync, null, 2) }}</pre>
        <div class="cmst:mt-2 cmst:flex cmst:flex-wrap cmst:gap-1.5">
          <StudioButton size="sm" variant="outline" data-testid="vue-node-push" @click="infrastructure.pushPlugins()">Push plugins (fast)</StudioButton>
          <StudioButton size="sm" variant="outline" data-testid="vue-node-rebuild" @click="infrastructure.rebuildDependencies()">Rebuild dependencies (slow)</StudioButton>
        </div>
      </section>
    </template>

    <template v-if="tab === 'models'">
      <section aria-label="Models">
        <div class="cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-2">
          <div>
            <h3 class="cmst-type-section">Models</h3>
            <p class="cmst-type-meta cmst:mt-0.5">{{ infrastructure.models.length }} installed</p>
          </div>
          <div class="cmst:flex cmst:gap-1.5">
            <input v-model="modelSearch" class="cmst-field cmst:w-48" placeholder="Search models" aria-label="Search models" @keyup.enter="infrastructure.loadInventory()" />
            <StudioButton size="sm" variant="outline" @click="infrastructure.rescanModelsNow(true)">Rescan</StudioButton>
          </div>
        </div>
        <div class="cmst:mt-2 cmst:max-h-64 cmst:overflow-auto" data-testid="vue-models-list">
          <div v-for="(model, index) in infrastructure.models" :key="index" class="cmst-data-row">
            <span class="cmst-status-dot cmst:bg-cmst-muted" aria-hidden="true" />
            <span class="cmst:min-w-0 cmst:flex-1 cmst:truncate">{{ String(model.filename || model.name || model.id || `model ${index}`) }}</span>
            <span class="cmst-type-meta cmst:truncate">{{ String(model.folder || model.type || "") }}</span>
          </div>
          <p v-if="!infrastructure.models.length" class="cmst:py-4 cmst:text-[13px] cmst:text-cmst-muted">No models installed.</p>
        </div>
        <div class="cmst:mt-3 cmst:flex cmst:flex-wrap cmst:gap-1.5">
          <input v-model="modelUrl" class="cmst-field cmst:min-w-0 cmst:flex-1" placeholder="Paste a direct model link" aria-label="Model URL" data-testid="vue-model-url" />
          <select v-model="modelFolder" class="cmst-field" aria-label="Model folder">
            <option value="diffusion_models">diffusion_models</option>
            <option value="vae">vae</option>
            <option value="clip">clip</option>
            <option value="loras">loras</option>
            <option value="upscale_models">upscale_models</option>
          </select>
          <StudioButton size="sm" data-testid="vue-model-install" @click="installFromUrl">Install</StudioButton>
        </div>
        <p v-if="modelInstallMessage" class="cmst:mt-2 cmst:text-xs cmst:text-cmst-muted" data-testid="vue-model-install-message" role="status">{{ modelInstallMessage }}</p>
      </section>
    </template>

    <template v-if="tab === 'nodes'">
      <section aria-label="Custom nodes">
        <div class="cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-2">
          <div>
            <h3 class="cmst-type-section">Custom nodes</h3>
            <p class="cmst-type-meta cmst:mt-0.5">{{ filteredNodes.length }} registered</p>
          </div>
          <div class="cmst:flex cmst:gap-1.5">
            <input v-model="nodeSearch" class="cmst-field cmst:w-48" placeholder="Search nodes" aria-label="Search nodes" />
            <StudioButton size="sm" variant="outline" @click="infrastructure.refreshCustomNodesNow()">Refresh registry</StudioButton>
          </div>
        </div>
        <div class="cmst:mt-2 cmst:max-h-64 cmst:overflow-auto" data-testid="vue-nodes-list">
          <div v-for="(node, index) in filteredNodes" :key="index" class="cmst-data-row">
            <span class="cmst-status-dot cmst:bg-cmst-muted" aria-hidden="true" />
            <span class="cmst:min-w-0 cmst:flex-1 cmst:truncate">{{ String(node.title || node.id || node.name || `node ${index}`) }}</span>
            <span class="cmst-type-meta cmst:truncate">{{ String(node.version || node.id || "") }}</span>
          </div>
          <p v-if="!filteredNodes.length" class="cmst:py-4 cmst:text-[13px] cmst:text-cmst-muted">No custom nodes match.</p>
        </div>
      </section>
    </template>
  </section>
</template>
