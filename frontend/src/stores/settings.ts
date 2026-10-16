// Modal Studio Vue substrate — settings store (Phase 2: server authority).
//
// Owns server /config reality plus intentional browser preferences. The
// server is authoritative after bootstrap; the one-way canvas projection
// carries proven output values to legacy non-Vue readers. Reset actions own
// exactly the bounded modern-settings key set — never Playground data,
// History entities, run identity, or image ownership.

import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { z } from "zod";
import { definePersisted } from "../persistence/persistence";
import {
  getConfig,
  getGoldenDeployStatus,
  getProfileLevel,
  listGoldenProfiles,
  triggerGoldenDeploy,
  updateConfig,
  updateGoldenGpuOrder,
  updateProfileLevel,
  type StudioConfig,
} from "../api/settings";
import { projectCanvasCompatibility } from "../compatibility/canvas";
import { createCrossTabInvalidation, publishCrossTabInvalidation } from "../compatibility/crossTab";
import { createLatestTask } from "../async/latest";
import { pollUntil } from "../async/polling";
import { useOperationsStore } from "./operations";

const densitySchema = z.enum(["comfortable", "compact"]);
type Density = z.infer<typeof densitySchema>;

const densityPersisted = definePersisted<Density>(
  "shell.density",
  "comfortable",
  densitySchema,
);

/** Bounded modern-settings key registry (mirrors the legacy authority list). */
export const MODERN_SETTINGS_KEYS = [
  "comfymodal_gpu",
  "comfymodal_output_format",
  "comfymodal_quality",
  "comfymodal_webp_lossless_compression",
  "comfymodal_auto_save_local",
  "comfymodal_save_folder",
  "comfymodal_save_metadata_sidecar",
  "comfymodal_preview_default",
  "comfymodal_preview_codec",
  "comfymodal_preview_quality",
  "comfymodal_data_saver_default",
  "comfymodal_data_saver_codec",
  "comfymodal_data_saver_quality",
  "comfymodal-studio-history-columns",
  "comfymodal_heavy_tracing",
  "comfymodal.studio.golden.profile.v1",
  "comfymodal-studio-panel-width",
  "comfymodal.studio.playground.carousel-cleared.v1",
  "comfymodal_remote_inventory_refresh_interval_s",
  "comfymodal_skip_plan_validation",
] as const;

export const SETTINGS_SECTIONS = [
  "generation",
  "outputs",
  "accounts",
  "interface",
  "advanced",
] as const;

export type SettingsSection = (typeof SETTINGS_SECTIONS)[number];

function readLocal(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeLocal(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Best-effort preference write.
  }
}

function removeLocal(keys: readonly string[]): void {
  for (const key of keys) {
    try {
      localStorage.removeItem(key);
    } catch {
      // Best-effort preference removal.
    }
  }
}

export interface GoldenProfile {
  name: string;
  [key: string]: unknown;
}

export const useSettingsStore = defineStore("studio-settings", () => {
  const activeSection = ref<SettingsSection>("generation");
  const density = ref<Density>(densityPersisted.read());
  const config = ref<StudioConfig | null>(null);
  const profileLevel = ref("off");
  const effectiveProfileLevel = ref("off");
  const loading = ref(false);
  const saving = ref(false);
  const error = ref<string | null>(null);
  const bootstrapped = ref(false);
  const goldenProfiles = ref<GoldenProfile[]>([]);
  const goldenError = ref<string | null>(null);
  const goldenDeployState = ref<Record<string, unknown> | null>(null);
  const goldenDeploying = ref(false);
  let pendingReload = false;
  let stopCrossTab: (() => void) | null = null;

  const goldenSelected = definePersisted<string>("golden.profile", "", z.string());
  const goldenFavorites = definePersisted<string[]>(
    "golden.favorites",
    [],
    z.array(z.string()),
  );
  const historyColumns = definePersisted<string>("history.columns", "6");
  const inventoryInterval = definePersisted<string>("inventory.interval", "300");

  const selectedGoldenProfile = ref(goldenSelected.read());
  const favoriteGoldenProfiles = ref<string[]>(goldenFavorites.read());
  const columnsPreference = ref(historyColumns.read());
  const refreshIntervalPreference = ref(inventoryInterval.read());

  const gpu = computed(() => config.value?.gpu ?? "");
  const goldenGpuOrder = computed<Record<string, string>>(() => {
    const raw = config.value?.golden_gpu_order;
    return raw && typeof raw === "object" ? (raw as Record<string, string>) : {};
  });

  async function load(): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      const [nextConfig, profile] = await Promise.all([getConfig(), getProfileLevel()]);
      config.value = nextConfig;
      profileLevel.value = profile.level;
      effectiveProfileLevel.value = profile.effective || profile.level;
      projectCanvasCompatibility(nextConfig);
      bootstrapped.value = true;
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : "Could not load Settings";
      throw cause;
    } finally {
      loading.value = false;
      if (pendingReload) {
        pendingReload = false;
        void load();
      }
    }
  }

  async function save(patch: Record<string, unknown>): Promise<void> {
    saving.value = true;
    error.value = null;
    try {
      await updateConfig(patch);
      const nextConfig = await getConfig();
      config.value = nextConfig;
      projectCanvasCompatibility(nextConfig);
      publishCrossTabInvalidation("settings");
    } catch (cause) {
      // Revert to server truth on failure so the UI never shows a value
      // the server rejected.
      try {
        config.value = await getConfig();
      } catch {
        // Keep the last acknowledged config when even the reread fails.
      }
      error.value = cause instanceof Error ? cause.message : "Could not save Settings";
      throw cause;
    } finally {
      saving.value = false;
    }
  }

  async function setProfile(level: string): Promise<void> {
    const previous = profileLevel.value;
    profileLevel.value = level;
    writeLocal("comfymodal_heavy_tracing", level);
    try {
      await updateProfileLevel(level);
      const profile = await getProfileLevel();
      effectiveProfileLevel.value = profile.effective || profile.level;
      publishCrossTabInvalidation("settings");
    } catch (cause) {
      profileLevel.value = previous;
      writeLocal("comfymodal_heavy_tracing", previous);
      throw cause;
    }
  }

  async function setSkipPlanValidation(enabled: boolean): Promise<void> {
    const previous = readLocal("comfymodal_skip_plan_validation");
    writeLocal("comfymodal_skip_plan_validation", enabled ? "1" : "0");
    try {
      await save({ skip_plan_validation: enabled });
    } catch (cause) {
      if (previous === null) {
        try {
          localStorage.removeItem("comfymodal_skip_plan_validation");
        } catch {
          // Best effort.
        }
      } else {
        writeLocal("comfymodal_skip_plan_validation", previous);
      }
      throw cause;
    }
  }

  async function loadGolden(): Promise<void> {
    goldenError.value = null;
    try {
      const catalog = (await listGoldenProfiles()) as {
        status?: string;
        profiles?: GoldenProfile[];
        defaultProfile?: string;
        message?: string;
      };
      if (!catalog || catalog.status !== "ok" || !Array.isArray(catalog.profiles)) {
        throw new Error(
          (catalog && (catalog.message as string)) || "invalid catalog response",
        );
      }
      const names = new Set(
        catalog.profiles.filter((p) => p && typeof p.name === "string").map((p) => p.name),
      );
      goldenProfiles.value = catalog.profiles.filter((p) => p && names.has(p.name));
      const serverSelected =
        (config.value as unknown as Record<string, unknown> | null)?.golden_profile;
      const serverName = typeof serverSelected === "string" ? serverSelected : "";
      if (names.has(serverName)) {
        selectedGoldenProfile.value = serverName;
      } else if (!names.has(selectedGoldenProfile.value)) {
        const fallback =
          typeof catalog.defaultProfile === "string" && names.has(catalog.defaultProfile)
            ? catalog.defaultProfile
            : "";
        selectedGoldenProfile.value = fallback;
      }
      goldenSelected.write(selectedGoldenProfile.value);
      if (selectedGoldenProfile.value) {
        goldenDeployState.value = (await getGoldenDeployStatus(
          selectedGoldenProfile.value,
        )) as Record<string, unknown>;
      }
    } catch (cause) {
      goldenError.value = cause instanceof Error ? cause.message : "Could not load Golden profiles";
      throw cause;
    }
  }

  function selectGoldenProfile(name: string): void {
    selectedGoldenProfile.value = name;
    goldenSelected.write(name);
  }

  function toggleGoldenFavorite(name: string): void {
    const next = favoriteGoldenProfiles.value.includes(name)
      ? favoriteGoldenProfiles.value.filter((item) => item !== name)
      : [...favoriteGoldenProfiles.value, name];
    favoriteGoldenProfiles.value = next;
    goldenFavorites.write(next);
  }

  async function setGoldenGpuOrder(profile: string, order: string): Promise<void> {
    await updateGoldenGpuOrder(profile, order);
    const nextConfig = await getConfig();
    config.value = nextConfig;
    publishCrossTabInvalidation("settings");
  }

  async function deployGoldenProfile(profile: string): Promise<string> {
    const operations = useOperationsStore();
    const operationId = operations.start({ kind: "deploy", label: `Deploy Golden ${profile}` });
    goldenDeploying.value = true;
    try {
      await triggerGoldenDeploy(profile);
      await pollUntil({
        intervalMs: 2000,
        run: async () => {
          const payload = (await getGoldenDeployStatus(profile)) as {
            state?: string;
            output?: string;
            message?: string;
          };
          const state = String(payload?.state ?? "unknown");
          operations.patch(operationId, { message: `Golden deploy: ${state}` });
          return payload;
        },
        done: (payload) => payload?.state === "done" || payload?.state === "failed",
      }).then((payload) => {
        if (payload?.state === "failed") {
          throw new Error(String(payload.output || payload.message || "Golden deploy failed"));
        }
        goldenDeployState.value = payload as Record<string, unknown>;
      });
      operations.finish(operationId, "Golden deploy finished");
      await loadGolden();
    } catch (cause) {
      operations.fail(
        operationId,
        cause instanceof Error ? cause.message : "Golden deploy failed",
      );
      throw cause;
    } finally {
      goldenDeploying.value = false;
    }
    return operationId;
  }

  function setHistoryColumns(value: string): void {
    columnsPreference.value = value;
    historyColumns.write(value);
  }

  function setInventoryInterval(value: string): void {
    refreshIntervalPreference.value = value;
    inventoryInterval.write(value);
  }

  async function resetSection(section: SettingsSection): Promise<void> {
    if (section === "generation") {
      removeLocal(["comfymodal_gpu", "comfymodal_preview_default", "comfymodal_preview_codec", "comfymodal_preview_quality", "comfymodal_data_saver_default", "comfymodal_data_saver_codec", "comfymodal_data_saver_quality"]);
      const fallbackGpu = config.value?.default_gpu || "rtx-pro-6000";
      await save({ gpu: fallbackGpu, golden_profile: null });
      selectGoldenProfile("");
    } else if (section === "outputs") {
      removeLocal(["comfymodal_output_format", "comfymodal_quality", "comfymodal_webp_lossless_compression", "comfymodal_auto_save_local", "comfymodal_save_folder", "comfymodal_save_metadata_sidecar"]);
      await save({
        output_format: "original",
        quality: 75,
        webp_lossless_compression: "balanced",
        auto_save_local: false,
        save_metadata_sidecar: true,
      });
    } else if (section === "interface") {
      removeLocal(["comfymodal-studio-panel-width", "comfymodal.studio.playground.carousel-cleared.v1", "comfymodal_remote_inventory_refresh_interval_s", "comfymodal-studio-history-columns"]);
      setHistoryColumns("6");
      setInventoryInterval("300");
    } else if (section === "advanced") {
      removeLocal(["comfymodal_heavy_tracing", "comfymodal_skip_plan_validation"]);
      await setProfile("off").catch(() => undefined);
      await save({ skip_plan_validation: false }).catch(() => undefined);
    }
    publishCrossTabInvalidation("settings");
  }

  async function resetAll(): Promise<void> {
    removeLocal(MODERN_SETTINGS_KEYS);
    selectGoldenProfile("");
    favoriteGoldenProfiles.value = [];
    goldenFavorites.write([]);
    setHistoryColumns("6");
    setInventoryInterval("300");
    const fallbackGpu = config.value?.default_gpu || "rtx-pro-6000";
    await save({ gpu: fallbackGpu, golden_profile: null }).catch(() => undefined);
    await setProfile("off").catch(() => undefined);
    await save({ skip_plan_validation: false }).catch(() => undefined);
    await load().catch(() => undefined);
  }

  async function initialize(): Promise<void> {
    if (!stopCrossTab) {
      stopCrossTab = createCrossTabInvalidation((kind) => {
        if (kind !== "settings") return;
        if (loading.value) {
          pendingReload = true;
          return;
        }
        void load();
      });
    }
    if (!bootstrapped.value) await load();
    writeLocal("comfymodal_heavy_tracing", profileLevel.value);
  }

  function setSection(section: string): void {
    if ((SETTINGS_SECTIONS as readonly string[]).includes(section)) {
      activeSection.value = section as SettingsSection;
    }
  }

  function setDensity(value: Density): void {
    density.value = value;
    densityPersisted.write(value);
  }

  function reset(): void {
    activeSection.value = "generation";
    density.value = "comfortable";
    densityPersisted.write("comfortable");
  }

  const configTask = createLatestTask();

  async function loadSubresource<T>(load: (signal: AbortSignal) => Promise<T>): Promise<T | null> {
    const result = await configTask.run(load);
    return result.stale ? null : result.value;
  }

  return {
    activeSection, density, config, profileLevel, effectiveProfileLevel,
    loading, saving, error, bootstrapped,
    goldenProfiles, goldenError, goldenDeployState, goldenDeploying,
    selectedGoldenProfile, favoriteGoldenProfiles,
    columnsPreference, refreshIntervalPreference,
    gpu, goldenGpuOrder, outputPreferences: computed(() => config.value ? {
      output_format: config.value.output_format,
      quality: config.value.quality,
      webp_lossless_compression: config.value.webp_lossless_compression,
      auto_save_local: config.value.auto_save_local,
      save_folder: config.value.save_folder,
      save_metadata_sidecar: config.value.save_metadata_sidecar,
      data_saver_default: config.value.data_saver_default,
      data_saver_codec: config.value.data_saver_codec,
      data_saver_quality: config.value.data_saver_quality,
    } : null),
    load, initialize, save, setProfile, setSkipPlanValidation,
    loadGolden, selectGoldenProfile, toggleGoldenFavorite,
    setGoldenGpuOrder, deployGoldenProfile,
    setHistoryColumns, setInventoryInterval,
    resetSection, resetAll,
    loadSubresource,
    setSection, setDensity, reset,
  };
});
