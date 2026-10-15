// Modal Studio Vue substrate — playground store (Phase 1: minimal).
//
// Owns Playground mode identity (feature + experiment mode). Run
// correctness stays in the canonical run controller
// (web/studio-playground-run.js + web/studio-run-model.js +
// web/studio-run-adapters.js); this store never executes or tracks runs.

import { defineStore } from "pinia";
import { ref } from "vue";

export const usePlaygroundStore = defineStore("studio-playground", () => {
  const featureId = ref("txt2img");
  const experimentMode = ref(false);

  function setFeature(id: string): void {
    featureId.value = id;
  }

  function setExperimentMode(enabled: boolean): void {
    experimentMode.value = enabled;
  }

  return { featureId, experimentMode, setFeature, setExperimentMode };
});
