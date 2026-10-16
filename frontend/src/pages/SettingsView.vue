<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { Settings, RefreshCw } from "@lucide/vue";
import { useSettingsStore, SETTINGS_SECTIONS, type SettingsSection } from "../stores/settings";
import StudioButton from "../components/StudioButton.vue";
import StudioCard from "../components/StudioCard.vue";
import { studioPageClass } from "../components/studioPanels";

const settings = useSettingsStore();
const quality = ref(75);
const saveFolder = ref("");
const outputFormat = ref("original");
const webpLossless = ref("balanced");
const autoSaveLocal = ref(false);
const saveMetadataSidecar = ref(true);
const dataSaverDefault = ref("off");
const dataSaverQuality = ref(70);
const profileDraft = ref("off");
const gpuDraft = ref("");
const skipDraft = ref(false);
const confirmResetAll = ref(false);

const config = computed(() => settings.config);
const gpuOptions = computed(() => config.value?.available_gpus ?? []);

function hydrateDrafts() {
  const c = config.value;
  if (!c) return;
  quality.value = c.quality;
  saveFolder.value = c.save_folder;
  outputFormat.value = c.output_format;
  webpLossless.value = c.webp_lossless_compression;
  autoSaveLocal.value = c.auto_save_local;
  saveMetadataSidecar.value = c.save_metadata_sidecar;
  dataSaverDefault.value = c.data_saver_default;
  dataSaverQuality.value = c.data_saver_quality;
  profileDraft.value = settings.profileLevel;
  gpuDraft.value = c.gpu;
  skipDraft.value = c.skip_plan_validation;
}

onMounted(async () => {
  await settings.initialize().catch(() => undefined);
  await settings.loadGolden().catch(() => undefined);
  hydrateDrafts();
});

async function saveOutputs() {
  await settings.save({
    output_format: outputFormat.value,
    quality: Number(quality.value),
    webp_lossless_compression: webpLossless.value,
    auto_save_local: autoSaveLocal.value,
    save_folder: saveFolder.value,
    save_metadata_sidecar: saveMetadataSidecar.value,
    data_saver_default: dataSaverDefault.value,
    data_saver_quality: Number(dataSaverQuality.value),
  }).catch(() => undefined);
  hydrateDrafts();
}

async function saveGpu() {
  await settings.save({ gpu: gpuDraft.value }).catch(() => undefined);
  hydrateDrafts();
}

async function saveDataSaver() {
  await settings.save({
    data_saver_default: dataSaverDefault.value,
    data_saver_quality: Number(dataSaverQuality.value),
  }).catch(() => undefined);
  hydrateDrafts();
}

async function saveSkip() {
  await settings.setSkipPlanValidation(skipDraft.value).catch(() => undefined);
  hydrateDrafts();
}

async function saveProfile() {
  await settings.setProfile(profileDraft.value).catch(() => undefined);
  hydrateDrafts();
}

async function resetSection(section: SettingsSection) {
  await settings.resetSection(section);
  hydrateDrafts();
}

async function resetAll() {
  if (!confirmResetAll.value) {
    confirmResetAll.value = true;
    return;
  }
  confirmResetAll.value = false;
  await settings.resetAll();
  hydrateDrafts();
}

function tabClass(section: SettingsSection): string {
  const active = settings.activeSection === section;
  return (
    "cmst:rounded-md cmst:px-3 cmst:py-2 cmst:text-sm cmst:font-medium cmst:border cmst:border-solid " +
    (active
      ? "cmst:bg-cmst-secondary cmst:text-cmst-fg cmst:border-cmst-border"
      : "cmst:bg-transparent cmst:text-cmst-muted cmst:border-transparent cmst:hover:bg-cmst-secondary")
  );
}
</script>

<template>
  <section :class="studioPageClass()" data-testid="vue-page-settings">
    <div v-if="settings.error" class="cmst:rounded-md cmst:border cmst:border-solid cmst:border-red-400 cmst:p-3 cmst:text-sm cmst:text-red-300" role="alert">
      {{ settings.error }}
    </div>

    <StudioCard class="cmst:p-4">
      <div class="cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-3">
        <div>
          <h2 class="cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2">
            <Settings class="cmst:size-5" aria-hidden="true" />
            Settings
          </h2>
          <p class="cmst:text-sm cmst:opacity-80">Server-backed authority. Failed saves revert to server truth.</p>
        </div>
        <StudioButton variant="outline" size="icon" aria-label="Reload settings" :disabled="settings.loading" @click="settings.load().then(hydrateDrafts).catch(() => undefined)">
          <RefreshCw class="cmst:size-4" :class="settings.loading ? 'cmst:animate-spin' : ''" aria-hidden="true" />
        </StudioButton>
      </div>
      <nav aria-label="Settings sections" class="cmst:mt-3 cmst:flex cmst:flex-wrap cmst:gap-1">
        <button
          v-for="section in SETTINGS_SECTIONS"
          :key="section"
          type="button"
          :class="tabClass(section)"
          :aria-current="settings.activeSection === section ? 'true' : undefined"
          :data-testid="`vue-settings-tab-${section}`"
          @click="settings.setSection(section)"
        >
          {{ section }}
        </button>
      </nav>
    </StudioCard>

    <StudioCard v-if="settings.activeSection === 'generation'" class="cmst:p-4">
      <div class="cmst:flex cmst:items-center cmst:justify-between">
        <h3 class="cmst:text-sm cmst:font-semibold">Generation</h3>
        <StudioButton variant="ghost" size="sm" data-testid="vue-settings-reset-generation" @click="resetSection('generation')">Reset section</StudioButton>
      </div>
      <label class="cmst:mt-3 cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm">
        GPU
        <select v-model="gpuDraft" class="cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2" data-testid="vue-settings-gpu" @change="saveGpu">
          <option v-for="option in gpuOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
        </select>
      </label>
      <div class="cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-3">
        <label class="cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm">
          Data Saver default
          <select v-model="dataSaverDefault" class="cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2" @change="saveDataSaver">
            <option value="off">Off</option>
            <option value="on">On</option>
          </select>
        </label>
        <label class="cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm">
          Data Saver quality
          <input v-model.number="dataSaverQuality" type="number" min="1" max="100" class="cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2" @change="saveDataSaver" />
        </label>
        <div class="cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm">
          Golden profile
          <select :value="settings.selectedGoldenProfile" class="cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2" data-testid="vue-settings-golden-profile" @change="settings.selectGoldenProfile(($event.target as HTMLSelectElement).value)">
            <option value="">None</option>
            <option v-for="profile in settings.goldenProfiles" :key="profile.name" :value="profile.name">{{ profile.name }}</option>
          </select>
        </div>
      </div>
      <p v-if="config?.engine_migration_notice" class="cmst:mt-2 cmst:text-xs cmst:opacity-70">{{ config.engine_migration_notice }}</p>
    </StudioCard>

    <StudioCard v-if="settings.activeSection === 'outputs'" class="cmst:p-4">
      <div class="cmst:flex cmst:items-center cmst:justify-between">
        <h3 class="cmst:text-sm cmst:font-semibold">Outputs</h3>
        <StudioButton variant="ghost" size="sm" data-testid="vue-settings-reset-outputs" @click="resetSection('outputs')">Reset section</StudioButton>
      </div>
      <div class="cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-2">
        <label class="cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm">
          Output format
          <select v-model="outputFormat" class="cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2">
            <option value="original">Original</option>
            <option value="png">PNG</option>
            <option value="jpeg">JPEG</option>
            <option value="webp">WebP</option>
          </select>
        </label>
        <label class="cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm">
          Quality
          <input v-model.number="quality" type="number" min="1" max="100" class="cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2" />
        </label>
        <label class="cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm">
          WebP lossless compression
          <select v-model="webpLossless" class="cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2">
            <option value="balanced">Balanced</option>
            <option value="fast">Fast</option>
            <option value="best">Best</option>
          </select>
        </label>
        <label class="cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm">
          Save folder
          <input v-model="saveFolder" type="text" class="cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2" />
        </label>
      </div>
      <div class="cmst:mt-3 cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-4 cmst:text-sm">
        <label class="cmst:flex cmst:items-center cmst:gap-2">
          <input v-model="autoSaveLocal" type="checkbox" />
          Auto-save local
        </label>
        <label class="cmst:flex cmst:items-center cmst:gap-2">
          <input v-model="saveMetadataSidecar" type="checkbox" />
          Save metadata sidecar
        </label>
        <StudioButton size="sm" :disabled="settings.saving" data-testid="vue-settings-save-output" @click="saveOutputs">
          {{ settings.saving ? "Saving…" : "Save outputs" }}
        </StudioButton>
      </div>
    </StudioCard>

    <StudioCard v-if="settings.activeSection === 'accounts'" class="cmst:p-4">
      <h3 class="cmst:text-sm cmst:font-semibold">Accounts &amp; Tokens</h3>
      <p class="cmst:mt-1 cmst:text-sm cmst:opacity-80">Credential status lives in Manage Modal. Golden favorites are a browser-only preference here.</p>
      <div class="cmst:mt-3 cmst:flex cmst:flex-wrap cmst:gap-2">
        <button
          v-for="profile in settings.goldenProfiles"
          :key="profile.name"
          type="button"
          class="cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:px-3 cmst:py-1 cmst:text-sm"
          :aria-pressed="settings.favoriteGoldenProfiles.includes(profile.name) ? 'true' : 'false'"
          :data-testid="`vue-golden-favorite-${profile.name}`"
          @click="settings.toggleGoldenFavorite(profile.name)"
        >
          {{ settings.favoriteGoldenProfiles.includes(profile.name) ? "★" : "☆" }} {{ profile.name }}
        </button>
      </div>
      <p v-if="!settings.goldenProfiles.length" class="cmst:mt-2 cmst:text-xs cmst:opacity-70">Golden catalog not loaded yet.</p>
    </StudioCard>

    <StudioCard v-if="settings.activeSection === 'interface'" class="cmst:p-4">
      <div class="cmst:flex cmst:items-center cmst:justify-between">
        <h3 class="cmst:text-sm cmst:font-semibold">Interface</h3>
        <StudioButton variant="ghost" size="sm" @click="resetSection('interface')">Reset section</StudioButton>
      </div>
      <div class="cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-3">
        <label class="cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm">
          History grid columns
          <select :value="settings.columnsPreference" class="cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2" @change="settings.setHistoryColumns(($event.target as HTMLSelectElement).value)">
            <option v-for="n in [2,3,4,5,6,7,8]" :key="n" :value="String(n)">{{ n }}</option>
          </select>
        </label>
        <label class="cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm">
          Remote inventory refresh
          <select :value="settings.refreshIntervalPreference" class="cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2" @change="settings.setInventoryInterval(($event.target as HTMLSelectElement).value)">
            <option value="0">Off</option>
            <option value="60">1 minute</option>
            <option value="300">5 minutes</option>
            <option value="900">15 minutes</option>
            <option value="1800">30 minutes</option>
          </select>
        </label>
        <label class="cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm">
          Shell density
          <select :value="settings.density" class="cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2" data-testid="vue-density-toggle" @change="settings.setDensity(($event.target as HTMLSelectElement).value as 'comfortable' | 'compact')">
            <option value="comfortable">Comfortable</option>
            <option value="compact">Compact</option>
          </select>
        </label>
      </div>
    </StudioCard>

    <StudioCard v-if="settings.activeSection === 'advanced'" class="cmst:p-4">
      <div class="cmst:flex cmst:items-center cmst:justify-between">
        <h3 class="cmst:text-sm cmst:font-semibold">Advanced</h3>
        <StudioButton variant="ghost" size="sm" @click="resetSection('advanced')">Reset section</StudioButton>
      </div>
      <label class="cmst:mt-3 cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm">
        Heavy tracing
        <select v-model="profileDraft" class="cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2" @change="saveProfile">
          <option value="off">Off</option>
          <option value="summary">Summary</option>
          <option value="detailed">Detailed</option>
          <option value="trace">Trace</option>
          <option value="trace_verbose">Verbose trace</option>
        </select>
      </label>
      <p class="cmst:mt-1 cmst:text-xs cmst:opacity-70">
        Requires ComfyUI restart.
        <span v-if="settings.profileLevel !== settings.effectiveProfileLevel" data-testid="vue-settings-restart-banner">
          Restart pending: selected {{ settings.profileLevel }}, effective {{ settings.effectiveProfileLevel }}.
        </span>
      </p>
      <label class="cmst:mt-3 cmst:flex cmst:items-center cmst:gap-2 cmst:text-sm">
        <input v-model="skipDraft" type="checkbox" data-testid="vue-settings-skip-validation" @change="saveSkip" />
        Skip plan validation (temporary triage only)
      </label>
      <div class="cmst:mt-4 cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:pt-3">
        <StudioButton variant="outline" size="sm" data-testid="vue-settings-reset-all" @click="resetAll">
          {{ confirmResetAll ? "Confirm reset all settings" : "Reset all settings" }}
        </StudioButton>
        <p class="cmst:mt-1 cmst:text-xs cmst:opacity-70">Resets only Settings-owned keys. Credentials and user data are not affected.</p>
      </div>
    </StudioCard>
  </section>
</template>
