// Modal Studio Vue substrate — history store (Phase 1: minimal).
//
// Owns History focus/query identity. History V2 remains the authoritative
// durable history; this store carries only the selection slice the shell
// needs until the later History port.

import { defineStore } from "pinia";
import { ref } from "vue";

export const useHistoryStore = defineStore("studio-history", () => {
  const focusId = ref<string | null>(null);
  const query = ref("");

  function setFocus(id: string | null): void {
    focusId.value = id;
  }

  function setQuery(value: string): void {
    query.value = value;
  }

  function clear(): void {
    focusId.value = null;
    query.value = "";
  }

  return { focusId, query, setFocus, setQuery, clear };
});
