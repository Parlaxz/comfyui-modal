<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { RefreshCw, Star, X } from "@lucide/vue";
import { useRouter } from "vue-router";
import { useSettingsStore, SETTINGS_SECTIONS, type SettingsSection } from "../stores/settings";
import StudioButton from "../components/StudioButton.vue";

const settings = useSettingsStore();
const router = useRouter();
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

// Active GPU order display for the selected Golden profile (legacy parity:
// order A/B summaries + runtime-active radio, no redeploy on swap).
const goldenOrderProfile = computed(() => {
  const name = settings.selectedGoldenProfile;
  if (!name) return null;
  return settings.goldenProfiles.find((profile) => profile.name === name) ?? null;
});

const goldenActiveOrder = computed(() => {
  const name = settings.selectedGoldenProfile;
  return (name && settings.goldenGpuOrder[name]) || "A";
});

function goldenOrderText(order: unknown): string {
  const list = (Array.isArray(order) ? order : []).map(String);
  if (!list.length) return "—";
  return list.map((value) => {
    const match = gpuOptions.value.find((option) => String(option.value).toLowerCase() === value.toLowerCase());
    return match?.label || match?.value || value;
  }).join(" → ");
}
const closeBtn = ref<HTMLElement | null>(null);

// Closing the Preferences layer returns to a deterministic Studio home.
// push (not back): the route stays canonical and Back reopens Settings,
// matching page-change history semantics.
function closeSettings(): void {
  void router.push({ name: "playground" });
}

// Escape closes this layer only; the host defers via the dialog role, and
// portalled controls that already handled the key (defaultPrevented) win.
function onDocumentKeydown(event: KeyboardEvent) {
  if (event.key !== "Escape" || event.defaultPrevented) return;
  event.stopPropagation();
  closeSettings();
}

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
  closeBtn.value?.focus();
  document.addEventListener("keydown", onDocumentKeydown);
});

onUnmounted(() => {
  document.removeEventListener("keydown", onDocumentKeydown);
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
  <!-- Settings presents as a Preferences sheet layered over Studio: the
    route stays canonical (#comfymodal=settings, Settings store owns state),
    only the presentation is modal. Close returns to Playground; Escape
    closes this layer (host defers via the dialog role), never Studio. -->
  <section class="cmst:block cmst:min-h-[60vh]" data-testid="vue-page-settings">
    <div class="cmst-settings-backdrop" aria-hidden="true" />
    <div
      class="cmst-settings-sheet"
      role="dialog"
      aria-modal="true"
      aria-label="Settings"
      tabindex="-1"
    >
      <div class="cmst-settings-head">
        <h1 class="cmst-type-view">Settings</h1>
        <div class="cmst:flex cmst:items-center cmst:gap-1">
          <button
            type="button"
            class="cmst-icon-btn"
            aria-label="Reload settings"
            :disabled="settings.loading"
            data-testid="vue-settings-reload"
            @click="settings.load().then(hydrateDrafts).catch(() => undefined)"
          >
            <RefreshCw class="cmst:size-4" :class="settings.loading ? 'cmst:animate-spin' : ''" aria-hidden="true" />
          </button>
          <button
            ref="closeBtn"
            type="button"
            class="cmst-close-btn"
            aria-label="Close settings"
            data-testid="vue-settings-close"
            @click="closeSettings"
          >
            <X class="cmst:size-4" aria-hidden="true" />
          </button>
        </div>
      </div>
      <div v-if="settings.error" class="cmst:px-5 cmst:pt-2 cmst:text-[13px] cmst:text-cmst-danger" role="alert">
        {{ settings.error }}
      </div>

      <!-- Category nav + single main pane. -->
      <div class="cmst-settings-body">
      <nav aria-label="Settings sections" class="cmst-side-nav cmst:min-w-0 cmst:lg:pr-2">
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
            <div v-if="goldenOrderProfile" class="cmst-setting-row">
              <div class="cmst-min-w-0">
                <p class="cmst:text-[13px] cmst:font-medium">Active GPU order</p>
                <p class="cmst-type-meta cmst:mt-0.5">A: {{ goldenOrderText(goldenOrderProfile.gpu_order_a) }}</p>
                <p v-if="(goldenOrderProfile.gpu_order_b as unknown[] | undefined)?.length" class="cmst-type-meta cmst:mt-0.5">B: {{ goldenOrderText(goldenOrderProfile.gpu_order_b) }}</p>
              </div>
              <div class="cmst:flex cmst:items-center cmst:gap-3" role="radiogroup" aria-label="Active GPU order">
                <label class="cmst:flex cmst:cursor-pointer cmst:items-center cmst:gap-1.5 cmst:text-[13px]">
                  <input type="radio" name="vue-golden-order" value="A" :checked="goldenActiveOrder !== 'B'" data-testid="vue-settings-golden-order-a" @change="settings.setGoldenGpuOrder(goldenOrderProfile.name, 'A')" />
                  A
                </label>
                <label v-if="(goldenOrderProfile.gpu_order_b as unknown[] | undefined)?.length" class="cmst:flex cmst:cursor-pointer cmst:items-center cmst:gap-1.5 cmst:text-[13px]">
                  <input type="radio" name="vue-golden-order" value="B" :checked="goldenActiveOrder === 'B'" data-testid="vue-settings-golden-order-b" @change="settings.setGoldenGpuOrder(goldenOrderProfile.name, 'B')" />
                  B
                </label>
              </div>
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
    </div>
  </section>
</template>
