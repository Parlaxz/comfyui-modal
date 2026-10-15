<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { History } from "@lucide/vue";
import { useHistoryStore } from "../stores/history";
import { createLatestTask } from "../async/latest";
import StudioButton from "../components/StudioButton.vue";
import StudioCard from "../components/StudioCard.vue";
import { studioPageClass } from "../components/studioPanels";

// Phase-1 placeholder: History V2 stays authoritative; the real History
// port comes later. This view proves the history store slice and gives
// `createLatestTask` a visible home: rapid focus changes supersede older
// simulated detail reads, and only the newest may commit.
//
// Focus also navigates (same page + new focus): the hash adapter turns
// that into a history REPLACE, so Back skips focus-only steps.

const router = useRouter();
const history = useHistoryStore();
const focusInput = ref("");
const committed = ref<string | null>(null);
const staleDrops = ref(0);

function fakeDetailRead(id: string, signal: AbortSignal): Promise<string> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => resolve(`detail:${id}`), 300);
    signal.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      },
      { once: true },
    );
  });
}

const detailTask = createLatestTask();

async function applyFocus() {
  const id = focusInput.value.trim();
  if (!id) return;
  history.setFocus(id);
  // Same-page focus change: the adapter replaces (not pushes) history.
  await router.push({ name: "history", query: { focus: id } });
  // No AbortError catch needed: superseded or aborted reads resolve
  // stale; only a genuine load failure would throw.
  const outcome = await detailTask.run((signal) => fakeDetailRead(id, signal));
  if (outcome.stale) {
    staleDrops.value += 1;
    return;
  }
  committed.value = outcome.value;
}
</script>

<template>
  <section :class="studioPageClass()" data-testid="vue-page-history">
    <StudioCard class="cmst:p-4">
      <h2 class="cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2">
        <History class="cmst:size-5" aria-hidden="true" />
        History (Phase-1 proof)
      </h2>
      <p class="cmst:text-sm cmst:opacity-80">
        Product functionality is intentionally not ported yet. Focus identity
        lives in the history store; detail reads go through the shared
        latest-read-wins primitive.
      </p>
      <div class="cmst:flex cmst:items-center cmst:gap-2 cmst:mt-3">
        <input
          v-model="focusInput"
          type="text"
          placeholder="Focus id (e.g. gen_123)"
          class="cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-transparent cmst:px-3 cmst:text-sm"
          data-testid="vue-history-focus-input"
        />
        <StudioButton
          variant="secondary"
          size="sm"
          data-testid="vue-history-focus-apply"
          @click="applyFocus"
        >
          Load focus
        </StudioButton>
      </div>
      <p class="cmst:text-sm cmst:mt-2">
        Store focus: <strong>{{ history.focusId ?? "none" }}</strong>
        · Committed read: <strong>{{ committed ?? "none" }}</strong>
        · Stale drops: <strong data-testid="vue-history-stale">{{ staleDrops }}</strong>
      </p>
      <p class="cmst:text-xs cmst:opacity-70">
        Tip: click “Load focus” rapidly with different ids — only the newest
        read commits; older ones are dropped as stale.
      </p>
    </StudioCard>
  </section>
</template>
