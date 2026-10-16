<script setup lang="ts">
import { computed } from "vue";
import { useHistoryStore } from "../stores/history";
import { selectCompareAsset } from "../api/history";
import StudioButton from "./StudioButton.vue";
import StudioCard from "./StudioCard.vue";

const history = useHistoryStore();
const pair = computed(() => history.compareRecords);

function urlOf(id: string | null, variant: "original" | "dataSaver"): string | null {
  const record = history.records.find((item) => item.id === id);
  const output = record?.featuredOutput;
  if (!output) return null;
  return variant === "original" ? selectCompareAsset(output) : output.dataSaverUrl || output.thumbUrl;
}
</script>

<template>
  <StudioCard v-if="pair.a || pair.b" class="cmst:p-4" data-testid="vue-compare">
    <div class="cmst:flex cmst:items-center cmst:justify-between">
      <h3 class="cmst:text-sm cmst:font-semibold">Compare (transient — never persisted)</h3>
      <div class="cmst:flex cmst:gap-2">
        <StudioButton variant="ghost" size="sm" data-testid="vue-compare-swap" @click="history.swapCompare()">Switch A/B</StudioButton>
        <StudioButton variant="ghost" size="sm" data-testid="vue-compare-clear" @click="history.clearCompare()">Clear</StudioButton>
      </div>
    </div>
    <div class="cmst:mt-3 cmst:grid cmst:grid-cols-2 cmst:gap-3">
      <figure v-for="slot in (['a', 'b'] as const)" :key="slot">
        <img
          v-if="urlOf(slot === 'a' ? history.compareA : history.compareB, 'original')"
          :src="urlOf(slot === 'a' ? history.compareA : history.compareB, 'original')!"
          :alt="`Compare ${slot.toUpperCase()}`"
          class="cmst:w-full cmst:rounded cmst:object-contain"
          :data-testid="`vue-compare-${slot}`"
        />
        <figcaption v-else class="cmst:text-xs cmst:opacity-60">Slot {{ slot.toUpperCase() }} empty or deleted.</figcaption>
      </figure>
    </div>
  </StudioCard>
</template>
