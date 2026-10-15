<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ServerCog, RefreshCw } from "@lucide/vue";
import { useInfrastructureStore } from "../stores/infrastructure";
import StudioButton from "../components/StudioButton.vue";
import StudioCard from "../components/StudioCard.vue";
import { studioPageClass } from "../components/studioPanels";

const infrastructure = useInfrastructureStore();
const selectedWorkspace = ref("");
const showLog = ref(false);
const modelCount = computed(() => infrastructure.models.length);
const nodeCount = computed(() => infrastructure.customNodes.length);

onMounted(() => {
  if (!infrastructure.workspaces.length) void infrastructure.initialize();
});

async function chooseWorkspace() {
  if (selectedWorkspace.value) await infrastructure.selectWorkspace(selectedWorkspace.value);
}

async function deploy() {
  await infrastructure.deploy();
}
</script>

<template>
  <section :class="studioPageClass()" data-testid="vue-page-backend">
    <div v-if="infrastructure.error" class="cmst:rounded-md cmst:border cmst:border-solid cmst:border-red-400 cmst:p-3 cmst:text-sm cmst:text-red-300" role="alert">
      {{ infrastructure.error }}
    </div>

    <StudioCard class="cmst:p-4">
      <div class="cmst:flex cmst:items-center cmst:justify-between cmst:gap-3">
        <div>
          <h2 class="cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2">
            <ServerCog class="cmst:size-5" aria-hidden="true" />
            Manage Modal
          </h2>
          <p class="cmst:text-sm cmst:opacity-80">Route key remains <code>backend</code>. Workspace and readiness state come from the server.</p>
        </div>
        <StudioButton variant="outline" size="icon" aria-label="Reload infrastructure" :disabled="infrastructure.loading" @click="infrastructure.load">
          <RefreshCw class="cmst:size-4" :class="infrastructure.loading ? 'cmst:animate-spin' : ''" aria-hidden="true" />
        </StudioButton>
      </div>
    </StudioCard>

    <StudioCard class="cmst:p-4">
      <h3 class="cmst:text-sm cmst:font-semibold">Workspaces</h3>
      <div class="cmst:mt-3 cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2">
        <select v-model="selectedWorkspace" class="cmst:h-9 cmst:min-w-52 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2" data-testid="vue-workspace-select">
          <option value="">{{ infrastructure.activeWorkspace?.label ?? "Select workspace" }}</option>
          <option v-for="workspace in infrastructure.workspaces" :key="workspace.id" :value="workspace.id">
            {{ workspace.label }}{{ workspace.isActive ? " (active)" : "" }}
          </option>
        </select>
        <StudioButton size="sm" variant="secondary" :disabled="!selectedWorkspace" data-testid="vue-workspace-activate" @click="chooseWorkspace">
          Activate workspace
        </StudioButton>
      </div>
      <p class="cmst:mt-2 cmst:text-xs cmst:opacity-70">Active ID: {{ infrastructure.activeWorkspaceId ?? "none" }}</p>
    </StudioCard>

    <StudioCard class="cmst:p-4">
      <div class="cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-3">
        <div>
          <h3 class="cmst:text-sm cmst:font-semibold">Deployment readiness</h3>
          <p class="cmst:mt-1 cmst:text-sm">State: <strong data-testid="vue-deploy-state">{{ infrastructure.deployStatus.state }}</strong></p>
          <p v-if="infrastructure.deployMessage" class="cmst:text-sm cmst:opacity-80">{{ infrastructure.deployMessage }}</p>
        </div>
        <div class="cmst:flex cmst:gap-2">
          <StudioButton size="sm" :disabled="infrastructure.loading" data-testid="vue-deploy" @click="deploy">Deploy / redeploy</StudioButton>
          <StudioButton size="sm" variant="outline" @click="showLog = !showLog">{{ showLog ? "Hide" : "Show" }} log</StudioButton>
        </div>
      </div>
      <pre v-if="showLog" class="cmst:mt-3 cmst:max-h-48 cmst:overflow-auto cmst:rounded-md cmst:bg-cmst-bg cmst:p-3 cmst:text-xs">{{ infrastructure.deployLog ?? "Loading…" }}</pre>
      <StudioButton v-if="showLog && !infrastructure.deployLog" class="cmst:mt-2" size="sm" variant="ghost" @click="infrastructure.loadLog">Load deployment log</StudioButton>
    </StudioCard>

    <StudioCard class="cmst:p-4">
      <h3 class="cmst:text-sm cmst:font-semibold">Shared inventory</h3>
      <p class="cmst:mt-1 cmst:text-sm cmst:opacity-80">Models: {{ modelCount }} · Custom nodes: {{ nodeCount }}</p>
      <div class="cmst:mt-3 cmst:flex cmst:flex-wrap cmst:gap-2">
        <StudioButton size="sm" variant="outline" @click="infrastructure.refreshRemoteInventoryNow">Refresh remote inventory</StudioButton>
        <StudioButton size="sm" variant="outline" @click="infrastructure.rescanModelsNow">Rescan models</StudioButton>
        <StudioButton size="sm" variant="outline" @click="infrastructure.refreshCustomNodesNow">Refresh custom nodes</StudioButton>
      </div>
      <p class="cmst:mt-2 cmst:text-xs cmst:opacity-70">{{ infrastructure.syncSummary ?? "Not loaded" }}</p>
    </StudioCard>
  </section>
</template>
