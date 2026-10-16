<script setup lang="ts">
import { computed, ref } from "vue";
import { FlaskConical, Play } from "@lucide/vue";
import { usePlaygroundStore } from "../stores/playground";
import { useOperationsStore } from "../stores/operations";
import StudioButton from "../components/StudioButton.vue";
import StudioCard from "../components/StudioCard.vue";
import { studioPageClass } from "../components/studioPanels";

// Phase-1 placeholder: the real Playground port comes later. This view
// proves the playground store slice and demonstrates the operationStore
// with a harmless LOCAL synthetic operation (progress timer only — no
// Modal deployment/GPU work of any kind).

const playground = usePlaygroundStore();
const operations = useOperationsStore();

const runningDemoId = ref<string | null>(null);
const demoProgress = computed(() => {
  if (!runningDemoId.value) return null;
  return operations.get(runningDemoId.value)?.progress ?? null;
});

function runSyntheticOperation() {
  if (runningDemoId.value) return;
  const id = operations.start({
    kind: "other",
    label: "Synthetic local proof operation",
    status: "running",
    progress: 0,
    message: "Counting to ten locally — no backend involved.",
  });
  runningDemoId.value = id;
  let tick = 0;
  const timer = setInterval(() => {
    tick += 1;
    if (tick >= 10) {
      clearInterval(timer);
      operations.finish(id, "Synthetic proof completed.");
      runningDemoId.value = null;
      return;
    }
    operations.patch(id, { progress: tick / 10, message: `Local tick ${tick}/10` });
  }, 150);
}
</script>

<template>
  <section :class="studioPageClass()" data-testid="vue-page-playground">
    <StudioCard class="cmst:p-4">
      <h2 class="cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2">
        <FlaskConical class="cmst:size-5" aria-hidden="true" />
        Playground (Phase-1 proof)
      </h2>
      <p class="cmst:text-sm cmst:opacity-80">
        Product functionality is intentionally not ported yet. This view proves
        the playground slice and a harmless local demo operation.
      </p>
      <label class="cmst:flex cmst:items-center cmst:gap-2 cmst:text-sm cmst:mt-3">
        <input
          type="checkbox"
          :checked="playground.experimentMode"
          @change="playground.setExperimentMode(($event.target as HTMLInputElement).checked)"
        />
        Experiment mode (playground store)
      </label>
    </StudioCard>

    <StudioCard class="cmst:p-4">
      <h3 class="cmst:text-sm cmst:font-semibold">operationStore demo</h3>
      <p class="cmst:text-sm cmst:opacity-80">
        A synthetic local operation publishes presentation state into the
        shared registry. Active operations: {{ operations.active.length }}.
      </p>
      <div class="cmst:flex cmst:items-center cmst:gap-3 cmst:mt-3">
        <StudioButton
          variant="default"
          size="sm"
          :disabled="runningDemoId !== null"
          @click="runSyntheticOperation"
        >
          <Play aria-hidden="true" />
          Run synthetic operation
        </StudioButton>
        <span v-if="demoProgress !== null" class="cmst:text-sm" data-testid="vue-op-progress">
          {{ Math.round((demoProgress ?? 0) * 100) }}%
        </span>
      </div>
      <ul class="cmst:mt-3 cmst:flex cmst:flex-col cmst:gap-1 cmst:text-sm">
        <li v-for="op in operations.all.slice(-5)" :key="op.id" data-testid="vue-op-row">
          <strong>{{ op.label }}</strong>
          — {{ op.status }}<span v-if="op.message"> — {{ op.message }}</span>
        </li>
      </ul>
    </StudioCard>
  </section>
</template>
