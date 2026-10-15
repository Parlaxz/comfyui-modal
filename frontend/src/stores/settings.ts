// Modal Studio Vue substrate — settings store (Phase 1: minimal).
//
// Owns the active settings section plus ONE harmless persisted UI
// preference (shell density) that demonstrates the explicit persistence
// helper with Zod validation. Full settings arrive with the later port;
// no server entities or operation state are persisted here.

import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { z } from "zod";
import { definePersisted } from "../persistence/persistence";
import { getConfig, getProfileLevel, updateConfig, updateProfileLevel, type StudioConfig } from "../api/settings";
import { projectCanvasCompatibility } from "../compatibility/canvas";
import { createCrossTabInvalidation, publishCrossTabInvalidation } from "../compatibility/crossTab";

const densitySchema = z.enum(["comfortable", "compact"]);
type Density = z.infer<typeof densitySchema>;

const densityPersisted = definePersisted<Density>(
  "shell.density",
  "comfortable",
  densitySchema,
);

export const useSettingsStore = defineStore("studio-settings", () => {
  const activeSection = ref("studio");
  const density = ref<Density>(densityPersisted.read());
  const config = ref<StudioConfig | null>(null);
  const profileLevel = ref("off");
  const loading = ref(false);
  const saving = ref(false);
  const error = ref<string | null>(null);
  const bootstrapped = ref(false);
  let stopCrossTab: (() => void) | null = null;

  const gpu = computed(() => config.value?.gpu ?? "");
  const outputPreferences = computed(() => config.value ? {
    output_format: config.value.output_format,
    quality: config.value.quality,
    webp_lossless_compression: config.value.webp_lossless_compression,
    auto_save_local: config.value.auto_save_local,
    save_folder: config.value.save_folder,
    save_metadata_sidecar: config.value.save_metadata_sidecar,
    data_saver_default: config.value.data_saver_default,
    data_saver_codec: config.value.data_saver_codec,
    data_saver_quality: config.value.data_saver_quality,
  } : null);

  async function load(): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      const [nextConfig, profile] = await Promise.all([getConfig(), getProfileLevel()]);
      config.value = nextConfig;
      profileLevel.value = profile.effective || profile.level;
      projectCanvasCompatibility(nextConfig);
      bootstrapped.value = true;
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : "Could not load Settings";
      throw cause;
    } finally {
      loading.value = false;
    }
  }

  async function save(patch: Record<string, unknown>): Promise<void> {
    saving.value = true;
    error.value = null;
    try {
      await updateConfig(patch);
      // Server response is not assumed to be a complete config: reread the
      // server authority, then project compatibility values one way.
      const nextConfig = await getConfig();
      config.value = nextConfig;
      projectCanvasCompatibility(nextConfig);
      publishCrossTabInvalidation("settings");
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : "Could not save Settings";
      throw cause;
    } finally {
      saving.value = false;
    }
  }

  async function setProfile(level: string): Promise<void> {
    await updateProfileLevel(level);
    profileLevel.value = level;
    publishCrossTabInvalidation("settings");
  }

  async function initialize(): Promise<void> {
    if (!stopCrossTab) {
      stopCrossTab = createCrossTabInvalidation((kind) => {
        if (kind === "settings" && !loading.value) void load();
      });
    }
    if (!bootstrapped.value) await load();
  }

  function setSection(section: string): void {
    activeSection.value = section;
  }

  function setDensity(value: Density): void {
    density.value = value;
    densityPersisted.write(value);
  }

  function reset(): void {
    activeSection.value = "studio";
    density.value = "comfortable";
    densityPersisted.write("comfortable");
  }

  return {
    activeSection, density, config, profileLevel, loading, saving, error, bootstrapped,
    gpu, outputPreferences, load, initialize, save, setProfile,
    setSection, setDensity, reset,
  };
});
