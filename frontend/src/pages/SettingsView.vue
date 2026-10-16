<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { RefreshCw, Star } from "@lucide/vue";
import { useSettingsStore, SETTINGS_SECTIONS, type SettingsSection } from "../stores/settings";
import StudioButton from "../components/StudioButton.vue";
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
</script>

<template>
  <section :class="studioPageClass()" data-testid="vue-page-settings">
    <div v-if="settings.error" class="cmst:text-[13px] cmst:text-cmst-danger" role="alert">
      {{ settings.error }}
    </div>

    <!-- Page toolbar flush on the page background. -->
    <div class="cmst:flex cmst:flex-wrap cmst:items-end cmst:justify-between cmst:gap-3">
      <div>
        <h1 class="cmst-type-view">Settings</h1>
      </div>
      <StudioButton variant="ghost" size="icon" aria-label="Reload settings" :disabled="settings.loading" @click="settings.load().then(hydrateDrafts).catch(() => undefined)">
        <RefreshCw class="cmst:size-4" :class="settings.loading ? 'cmst:animate-spin' : ''" aria-hidden="true" />
      </StudioButton>
    </div>

    <!-- Category nav (left on wide) + single main pane. -->
    <div class="cmst:grid cmst:grid-cols-1 cmst:gap-6 cmst:lg:grid-cols-[180px_minmax(0,1fr)]">
      <nav aria-label="Settings sections" class="cmst-side-nav cmst:min-w-0 cmst:lg:border-r cmst:lg:border-solid cmst:lg:border-cmst-border cmst:lg:pr-4">
        <button
          v-for="section in SETTINGS_SECTIONS"
          :key="section"
          type="button"
          class="cmst-quiet-tab"
          :aria-selected="settings.activeSection === section"
          :aria-current="settings.activeSection === section ? 'true' : undefined"
          :data-testid="`vue-settings-tab-${section}`"
          @click="settings.setSection(section)"
        >
          <span class="cmst:capitalize">{{ section }}</span>
        </button>
      </nav>

      <div class="cmst:min-w-0 cmst:max-w-3xl">
        <template v-if="settings.activeSection === 'generation'">
          <div class="cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-2">
            <h2 class="cmst-type-section">Generation</h2>
            <StudioButton variant="ghost" size="sm" data-testid="vue-settings-reset-generation" @click="resetSection('generation')">Reset section</StudioButton>
          </div>
          <div class="cmst:mt-1">
            <div class="cmst-setting-row">
              <div class="cmst:min-w-0">
                <p class="cmst:text-[13px] cmst:font-medium">GPU</p>
                <p class="cmst:text-xs cmst:text-cmst-muted">Execution device for this workspace.</p>
              </div>
              <select v-model="gpuDraft" class="cmst-field cmst:w-56 cmst:max-w-full" data-testid="vue-settings-gpu" aria-label="GPU" @change="saveGpu">
                <option v-for="option in gpuOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
              </select>
            </div>
            <div class="cmst-setting-row">
              <div class="cmst:min-w-0">
                <p class="cmst:text-[13px] cmst:font-medium">Data Saver default</p>
                <p class="cmst:text-xs cmst:text-cmst-muted">Serve bandwidth-saving variants unless asked otherwise.</p>
              </div>
              <select v-model="dataSaverDefault" class="cmst-field cmst:w-56 cmst:max-w-full" aria-label="Data Saver default" @change="saveDataSaver">
                <option value="off">Off</option>
                <option value="on">On</option>
              </select>
            </div>
            <div class="cmst-setting-row">
              <div class="cmst:min-w-0">
                <p class="cmst:text-[13px] cmst:font-medium">Data Saver quality</p>
                <p class="cmst:text-xs cmst:text-cmst-muted">Quality level for Data Saver variants, 1–100.</p>
              </div>
              <input v-model.number="dataSaverQuality" type="number" min="1" max="100" class="cmst-field cmst:w-56 cmst:max-w-full" aria-label="Data Saver quality" @change="saveDataSaver" />
            </div>
            <div class="cmst-setting-row">
              <div class="cmst:min-w-0">
                <p class="cmst:text-[13px] cmst:font-medium">Golden profile</p>
                <p class="cmst:text-xs cmst:text-cmst-muted">Pinned known-good deployment profile.</p>
              </div>
              <select :value="settings.selectedGoldenProfile" class="cmst-field cmst:w-56 cmst:max-w-full" data-testid="vue-settings-golden-profile" aria-label="Golden profile" @change="settings.selectGoldenProfile(($event.target as HTMLSelectElement).value)">
                <option value="">None</option>
                <option v-for="profile in settings.goldenProfiles" :key="profile.name" :value="profile.name">{{ profile.name }}</option>
              </select>
            </div>
          </div>
          <p v-if="config?.engine_migration_notice" class="cmst:mt-2 cmst:text-xs cmst:text-cmst-muted">{{ config.engine_migration_notice }}</p>
        </template>

        <template v-if="settings.activeSection === 'outputs'">
          <div class="cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-2">
            <h2 class="cmst-type-section">Outputs</h2>
            <StudioButton variant="ghost" size="sm" data-testid="vue-settings-reset-outputs" @click="resetSection('outputs')">Reset section</StudioButton>
          </div>
          <div class="cmst:mt-1">
            <div class="cmst-setting-row">
              <div class="cmst:min-w-0">
                <p class="cmst:text-[13px] cmst:font-medium">Output format</p>
                <p class="cmst:text-xs cmst:text-cmst-muted">Saved image format. Original keeps the engine default.</p>
              </div>
              <select v-model="outputFormat" class="cmst-field cmst:w-56 cmst:max-w-full" aria-label="Output format">
                <option value="original">Original</option>
                <option value="png">PNG</option>
                <option value="jpeg">JPEG</option>
                <option value="webp">WebP</option>
              </select>
            </div>
            <div class="cmst-setting-row">
              <div class="cmst:min-w-0">
                <p class="cmst:text-[13px] cmst:font-medium">Quality</p>
                <p class="cmst:text-xs cmst:text-cmst-muted">Compression quality for lossy formats, 1–100.</p>
              </div>
              <input v-model.number="quality" type="number" min="1" max="100" class="cmst-field cmst:w-56 cmst:max-w-full" aria-label="Quality" />
            </div>
            <div class="cmst-setting-row">
              <div class="cmst:min-w-0">
                <p class="cmst:text-[13px] cmst:font-medium">WebP lossless compression</p>
                <p class="cmst:text-xs cmst:text-cmst-muted">Effort spent on lossless WebP encodes.</p>
              </div>
              <select v-model="webpLossless" class="cmst-field cmst:w-56 cmst:max-w-full" aria-label="WebP lossless compression">
                <option value="balanced">Balanced</option>
                <option value="fast">Fast</option>
                <option value="best">Best</option>
              </select>
            </div>
            <div class="cmst-setting-row">
              <div class="cmst:min-w-0">
                <p class="cmst:text-[13px] cmst:font-medium">Save folder</p>
                <p class="cmst:text-xs cmst:text-cmst-muted">Local destination for saved outputs.</p>
              </div>
              <input v-model="saveFolder" type="text" class="cmst-field cmst:w-56 cmst:max-w-full cmst:font-mono" aria-label="Save folder" />
            </div>
            <div class="cmst-setting-row">
              <div class="cmst:min-w-0">
                <p class="cmst:text-[13px] cmst:font-medium">Auto-save local</p>
                <p class="cmst:text-xs cmst:text-cmst-muted">Write a local copy of every output automatically.</p>
              </div>
              <input v-model="autoSaveLocal" type="checkbox" aria-label="Auto-save local" />
            </div>
            <div class="cmst-setting-row">
              <div class="cmst:min-w-0">
                <p class="cmst:text-[13px] cmst:font-medium">Save metadata sidecar</p>
                <p class="cmst:text-xs cmst:text-cmst-muted">Keep generation parameters alongside each file.</p>
              </div>
              <input v-model="saveMetadataSidecar" type="checkbox" aria-label="Save metadata sidecar" />
            </div>
          </div>
          <div class="cmst:mt-3">
            <StudioButton size="sm" variant="secondary" :disabled="settings.saving" data-testid="vue-settings-save-output" @click="saveOutputs">
              {{ settings.saving ? "Saving…" : "Save outputs" }}
            </StudioButton>
          </div>
        </template>

        <template v-if="settings.activeSection === 'accounts'">
          <h2 class="cmst-type-section">Accounts &amp; tokens</h2>
          <p class="cmst:mt-1 cmst:text-[13px] cmst:text-cmst-muted">Sign-in status lives in Manage Modal.</p>
          <div class="cmst:mt-1">
            <div v-for="profile in settings.goldenProfiles" :key="profile.name" class="cmst-data-row">
              <button
                type="button"
                class="cmst-icon-btn"
                :aria-pressed="settings.favoriteGoldenProfiles.includes(profile.name) ? 'true' : 'false'"
                :aria-label="`Toggle favorite for ${profile.name}`"
                :data-testid="`vue-golden-favorite-${profile.name}`"
                @click="settings.toggleGoldenFavorite(profile.name)"
              >
                <Star class="cmst:size-3.5" :class="settings.favoriteGoldenProfiles.includes(profile.name) ? 'cmst:fill-cmst-primary cmst:text-cmst-primary' : ''" aria-hidden="true" />
              </button>
              <span class="cmst:min-w-0 cmst:flex-1 cmst:truncate cmst:text-[13px]">{{ profile.name }}</span>
            </div>
            <p v-if="!settings.goldenProfiles.length" class="cmst:py-3 cmst:text-xs cmst:text-cmst-muted">Golden catalog not loaded yet.</p>
          </div>
        </template>

        <template v-if="settings.activeSection === 'interface'">
          <div class="cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-2">
            <h2 class="cmst-type-section">Interface</h2>
            <StudioButton variant="ghost" size="sm" @click="resetSection('interface')">Reset section</StudioButton>
          </div>
          <div class="cmst:mt-1">
            <div class="cmst-setting-row">
              <div class="cmst:min-w-0">
                <p class="cmst:text-[13px] cmst:font-medium">History grid columns</p>
                <p class="cmst:text-xs cmst:text-cmst-muted">Media grid density on the History page.</p>
              </div>
              <select :value="settings.columnsPreference" class="cmst-field cmst:w-56 cmst:max-w-full" aria-label="History grid columns" @change="settings.setHistoryColumns(($event.target as HTMLSelectElement).value)">
                <option v-for="n in [2,3,4,5,6,7,8]" :key="n" :value="String(n)">{{ n }}</option>
              </select>
            </div>
            <div class="cmst-setting-row">
              <div class="cmst:min-w-0">
                <p class="cmst:text-[13px] cmst:font-medium">Remote inventory refresh</p>
                <p class="cmst:text-xs cmst:text-cmst-muted">How often shared inventory re-syncs in the background.</p>
              </div>
              <select :value="settings.refreshIntervalPreference" class="cmst-field cmst:w-56 cmst:max-w-full" aria-label="Remote inventory refresh" @change="settings.setInventoryInterval(($event.target as HTMLSelectElement).value)">
                <option value="0">Off</option>
                <option value="60">1 minute</option>
                <option value="300">5 minutes</option>
                <option value="900">15 minutes</option>
                <option value="1800">30 minutes</option>
              </select>
            </div>
            <div class="cmst-setting-row">
              <div class="cmst:min-w-0">
                <p class="cmst:text-[13px] cmst:font-medium">Shell density</p>
                <p class="cmst:text-xs cmst:text-cmst-muted">Spacing rhythm for the Studio shell.</p>
              </div>
              <select :value="settings.density" class="cmst-field cmst:w-56 cmst:max-w-full" data-testid="vue-density-toggle" aria-label="Shell density" @change="settings.setDensity(($event.target as HTMLSelectElement).value as 'comfortable' | 'compact')">
                <option value="comfortable">Comfortable</option>
                <option value="compact">Compact</option>
              </select>
            </div>
          </div>
        </template>

        <template v-if="settings.activeSection === 'advanced'">
          <div class="cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-2">
            <h2 class="cmst-type-section">Advanced</h2>
            <StudioButton variant="ghost" size="sm" @click="resetSection('advanced')">Reset section</StudioButton>
          </div>
          <div class="cmst:mt-1">
            <div class="cmst-setting-row">
              <div class="cmst:min-w-0">
                <p class="cmst:text-[13px] cmst:font-medium">Heavy tracing</p>
                <p class="cmst:text-xs cmst:text-cmst-muted">
                  Requires ComfyUI restart.
                  <span v-if="settings.profileLevel !== settings.effectiveProfileLevel" data-testid="vue-settings-restart-banner">
                    Restart pending: selected {{ settings.profileLevel }}, effective {{ settings.effectiveProfileLevel }}.
                  </span>
                </p>
              </div>
              <select v-model="profileDraft" class="cmst-field cmst:w-56 cmst:max-w-full" aria-label="Heavy tracing" @change="saveProfile">
                <option value="off">Off</option>
                <option value="summary">Summary</option>
                <option value="detailed">Detailed</option>
                <option value="trace">Trace</option>
                <option value="trace_verbose">Verbose trace</option>
              </select>
            </div>
            <div class="cmst-setting-row">
              <div class="cmst:min-w-0">
                <p class="cmst:text-[13px] cmst:font-medium">Skip plan validation</p>
                <p class="cmst:text-xs cmst:text-cmst-muted">Temporary triage only. Re-enable after debugging.</p>
              </div>
              <input v-model="skipDraft" type="checkbox" data-testid="vue-settings-skip-validation" aria-label="Skip plan validation" @change="saveSkip" />
            </div>
          </div>
          <div class="cmst:mt-4 cmst:border-t cmst:border-solid cmst:border-cmst-border cmst:pt-3">
            <StudioButton variant="outline" size="sm" class="cmst:text-cmst-danger" data-testid="vue-settings-reset-all" @click="resetAll">
              {{ confirmResetAll ? "Confirm reset all settings" : "Reset all settings" }}
            </StudioButton>
            <p class="cmst:mt-1 cmst:text-xs cmst:text-cmst-muted">Resets only Settings-owned keys. Credentials and user data are not affected.</p>
          </div>
        </template>
      </div>
    </div>
  </section>
</template>
