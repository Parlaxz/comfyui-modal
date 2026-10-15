// Modal Studio Vue substrate — workflows store (Phase 1: minimal).
//
// Owns workflow-library selection identity. Full library state arrives
// with the later Workflows port.

import { defineStore } from "pinia";
import { ref } from "vue";

export const useWorkflowsStore = defineStore("studio-workflows", () => {
  const selectedId = ref<string | null>(null);

  function select(id: string | null): void {
    selectedId.value = id;
  }

  function clear(): void {
    selectedId.value = null;
  }

  return { selectedId, select, clear };
});
