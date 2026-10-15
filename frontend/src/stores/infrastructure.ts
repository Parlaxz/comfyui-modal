// Modal Studio Vue substrate — infrastructure store (Phase 1: minimal).
//
// Owns the backend/deploy/sync health snapshot. Full deploy/sync state
// arrives with the later Manage-Modal port; Phase 1 keeps a representative
// slice so the shell can prove store ownership and rendering.

import { defineStore } from "pinia";
import { ref } from "vue";

export const useInfrastructureStore = defineStore("studio-infrastructure", () => {
  const deployState = ref("unknown");
  const deployMessage = ref<string | null>(null);
  const syncSummary = ref<string | null>(null);

  function setDeploy(state: string, message?: string | null): void {
    deployState.value = state;
    deployMessage.value = message ?? null;
  }

  function setSyncSummary(summary: string | null): void {
    syncSummary.value = summary;
  }

  function reset(): void {
    deployState.value = "unknown";
    deployMessage.value = null;
    syncSummary.value = null;
  }

  return { deployState, deployMessage, syncSummary, setDeploy, setSyncSummary, reset };
});
