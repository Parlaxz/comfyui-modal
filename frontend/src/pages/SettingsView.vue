<script setup lang="ts">
import { Settings } from "@lucide/vue";
import { useSettingsStore } from "../stores/settings";
import StudioButton from "../components/StudioButton.vue";
import StudioCard from "../components/StudioCard.vue";
import { studioPageClass } from "../components/studioPanels";

// Phase-1 placeholder: the real Settings port comes later. This view proves
// the settings store slice and the ONE persisted Phase-1 preference (shell
// density, Zod-validated via the explicit persistence helper).

const settings = useSettingsStore();

function toggleDensity() {
  settings.setDensity(settings.density === "compact" ? "comfortable" : "compact");
}
</script>

<template>
  <section :class="studioPageClass()" data-testid="vue-page-settings">
    <StudioCard class="cmst:p-4">
      <h2 class="cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2">
        <Settings class="cmst:size-5" aria-hidden="true" />
        Settings (Phase-1 proof)
      </h2>
      <p class="cmst:text-sm cmst:opacity-80">
        Product functionality is intentionally not ported yet. Section
        identity lives in the settings store.
      </p>
      <p class="cmst:text-sm cmst:mt-2">
        Active section: <strong>{{ settings.activeSection }}</strong>
      </p>
    </StudioCard>

    <StudioCard class="cmst:p-4">
      <h3 class="cmst:text-sm cmst:font-semibold">Persisted preference proof</h3>
      <p class="cmst:text-sm cmst:opacity-80">
        Shell density survives reload via the explicit persistence helper
        (Zod-validated; malformed data falls back to
        <code>comfortable</code>).
      </p>
      <div class="cmst:flex cmst:items-center cmst:gap-3 cmst:mt-3">
        <StudioButton
          variant="outline"
          size="sm"
          data-testid="vue-density-toggle"
          @click="toggleDensity"
        >
          Toggle density
        </StudioButton>
        <span class="cmst:text-sm" data-testid="vue-density-value">
          {{ settings.density }}
        </span>
      </div>
    </StudioCard>
  </section>
</template>
