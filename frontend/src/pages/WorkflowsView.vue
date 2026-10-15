<script setup lang="ts">
import { ref } from "vue";
import { Layers } from "@lucide/vue";
import { useWorkflowsStore } from "../stores/workflows";
import { pollUntil } from "../async/polling";
import StudioButton from "../components/StudioButton.vue";
import StudioCard from "../components/StudioCard.vue";
import { studioPageClass } from "../components/studioPanels";

// Phase-1 placeholder: the real Workflows port comes later. This view
// proves the workflows store slice and gives the shared `poll` primitive
// a visible home: a harmless local status simulation, polled until done.

const workflows = useWorkflowsStore();
const selectedInput = ref("");
const pollStatus = ref("idle");
const pollAttempts = ref(0);

async function runLocalPoll() {
  pollStatus.value = "polling…";
  pollAttempts.value = 0;
  let ticks = 0;
  const result = await pollUntil({
    intervalMs: 120,
    run: async (_signal, attempt) => {
      pollAttempts.value = attempt;
      ticks += 1;
      return ticks >= 3 ? "ready" : "warming";
    },
    done: (value) => value === "ready",
  });
  pollStatus.value = result;
}
</script>

<template>
  <section :class="studioPageClass()" data-testid="vue-page-workflows">
    <StudioCard class="cmst:p-4">
      <h2 class="cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2">
        <Layers class="cmst:size-5" aria-hidden="true" />
        Workflows (Phase-1 proof)
      </h2>
      <p class="cmst:text-sm cmst:opacity-80">
        Product functionality is intentionally not ported yet. Selection
        identity lives in the workflows store.
      </p>
      <div class="cmst:flex cmst:items-center cmst:gap-2 cmst:mt-3">
        <input
          v-model="selectedInput"
          type="text"
          placeholder="Workflow id"
          class="cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-transparent cmst:px-3 cmst:text-sm"
        />
        <StudioButton
          variant="secondary"
          size="sm"
          @click="workflows.select(selectedInput.trim() || null)"
        >
          Select
        </StudioButton>
      </div>
      <p class="cmst:text-sm cmst:mt-2">
        Store selection: <strong>{{ workflows.selectedId ?? "none" }}</strong>
      </p>
    </StudioCard>

    <StudioCard class="cmst:p-4">
      <h3 class="cmst:text-sm cmst:font-semibold">polling demo (local only)</h3>
      <p class="cmst:text-sm cmst:opacity-80">
        Repeats a local status check until the completion predicate holds.
      </p>
      <div class="cmst:flex cmst:items-center cmst:gap-3 cmst:mt-3">
        <StudioButton
          variant="outline"
          size="sm"
          data-testid="vue-poll-run"
          @click="runLocalPoll"
        >
          Start local poll
        </StudioButton>
        <span class="cmst:text-sm" data-testid="vue-poll-status">
          {{ pollStatus }} ({{ pollAttempts }} attempts)
        </span>
      </div>
    </StudioCard>
  </section>
</template>
