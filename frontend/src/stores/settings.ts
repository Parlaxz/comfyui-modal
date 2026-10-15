// Modal Studio Vue substrate — settings store (Phase 1: minimal).
//
// Owns the active settings section plus ONE harmless persisted UI
// preference (shell density) that demonstrates the explicit persistence
// helper with Zod validation. Full settings arrive with the later port;
// no server entities or operation state are persisted here.

import { defineStore } from "pinia";
import { ref } from "vue";
import { z } from "zod";
import { definePersisted } from "../persistence/persistence";

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

  return { activeSection, density, setSection, setDensity, reset };
});
