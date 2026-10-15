<script setup lang="ts">
import { computed, ref } from "vue";
import { Settings, RefreshCw } from "@lucide/vue";
import { useSettingsStore } from "../stores/settings";
import StudioButton from "../components/StudioButton.vue";
import StudioCard from "../components/StudioCard.vue";
import { studioPageClass } from "../components/studioPanels";

const settings = useSettingsStore();
const selectedQuality = ref(75);
const selectedSaveFolder = ref("");
const selectedProfile = ref("off");

const config = computed(() => settings.config);
const gpuOptions = computed(() => config.value?.available_gpus ?? []);

async function saveOutputSettings() {
  await settings.save({
    quality: Number(selectedQuality.value),
    save_folder: selectedSaveFolder.value,
  });
}

async function setGpu(event: Event) {
  const value = (event.target as HTMLSelectElement).value;
  await settings.save({ gpu: value });
}

async function setSkipPlanValidation(event: Event) {
  await settings.save({ skip_plan_validation: (event.target as HTMLInputElement).checked });
}

async function setProfile() {
  await settings.setProfile(selectedProfile.value);
}
</script>

<template>
  <section :class="studioPageClass()" data-testid="vue-page-settings">
    <div v-if="settings.error" class="cmst:rounded-md cmst:border cmst:border-solid cmst:border-red-400 cmst:p-3 cmst:text-sm cmst:text-red-300" role="alert">
      {{ settings.error }}
    </div>

    <StudioCard class="cmst:p-4">
      <div class="cmst:flex cmst:items-center cmst:justify-between cmst:gap-3">
        <div>
          <h2 class="cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2">
            <Settings class="cmst:size-5" aria-hidden="true" />
            Settings
          </h2>
          <p class="cmst:text-sm cmst:opacity-80">
            Server-backed Settings authority. Vue reads `/config` and projects
            proven output values one-way to legacy canvas consumers.
          </p>
        </div>
        <StudioButton variant="outline" size="icon" aria-label="Reload settings" :disabled="settings.loading" @click="settings.load">
          <RefreshCw class="cmst:size-4" :class="settings.loading ? 'cmst:animate-spin' : ''" aria-hidden="true" />
        </StudioButton>
      </div>
      <p class="cmst:mt-3 cmst:text-sm">
        Active section: <strong>{{ settings.activeSection }}</strong>
        <span v-if="settings.config"> · server config loaded</span>
      </p>
    </StudioCard>

    <StudioCard class="cmst:p-4">
      <h3 class="cmst:text-sm cmst:font-semibold">Generation</h3>
      <div class="cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-2">
        <label class="cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm">
          GPU
          <select
            :value="config?.gpu ?? ''"
            class="cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2"
            data-testid="vue-settings-gpu"
            @change="setGpu"
          >
            <option v-for="gpu in gpuOptions" :key="gpu.value" :value="gpu.value">{{ gpu.label }}</option>
          </select>
        </label>
        <label class="cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm">
          Profile/tracing level
          <select v-model="selectedProfile" class="cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2" @change="setProfile">
            <option value="off">Off</option>
            <option value="summary">Summary</option>
            <option value="detailed">Detailed</option>
            <option value="trace">Trace</option>
            <option value="trace_verbose">Trace verbose</option>
          </select>
        </label>
      </div>
    </StudioCard>

    <StudioCard class="cmst:p-4">
      <h3 class="cmst:text-sm cmst:font-semibold">Outputs / Data Saver</h3>
      <div class="cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-2">
        <label class="cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm">
          Quality
          <input v-model.number="selectedQuality" type="number" min="1" max="100" class="cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2" />
        </label>
        <label class="cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm">
          Save folder
          <input v-model="selectedSaveFolder" type="text" class="cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2" />
        </label>
      </div>
      <div class="cmst:mt-3 cmst:flex cmst:items-center cmst:gap-3">
        <StudioButton size="sm" :disabled="settings.saving" data-testid="vue-settings-save-output" @click="saveOutputSettings">
          {{ settings.saving ? "Saving…" : "Save output settings" }}
        </StudioButton>
        <span class="cmst:text-xs cmst:opacity-70">Server truth is reread after every save.</span>
      </div>
    </StudioCard>

    <StudioCard class="cmst:p-4">
      <h3 class="cmst:text-sm cmst:font-semibold">Advanced</h3>
      <label class="cmst:mt-3 cmst:flex cmst:items-center cmst:gap-2 cmst:text-sm">
        <input type="checkbox" :checked="config?.skip_plan_validation ?? false" @change="setSkipPlanValidation" />
        Skip plan validation (preserves current backend semantics)
      </label>
      <p class="cmst:mt-2 cmst:text-xs cmst:opacity-70">Execution mode remains server-owned and V2-only.</p>
    </StudioCard>
  </section>
</template>
