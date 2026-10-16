<script setup lang="ts">
import { computed } from "vue";
import { useHistoryStore } from "../stores/history";
import { selectCompareAsset } from "../api/history";
import StudioButton from "./StudioButton.vue";
import StudioCard from "./StudioCard.vue";

const history = useHistoryStore();
const pair = computed(() => history.compareRecords);

function recordFor(id: string | null) {
  return history.records.find((item) => item.id === id) ?? null;
}

function urlOf(id: string | null): string | null {
  const output = recordFor(id)?.featuredOutput;
  if (!output) return null;
  return selectCompareAsset(output);
}

function captionFor(slot: "a" | "b"): string {
  const id = slot === "a" ? history.compareA : history.compareB;
  const record = recordFor(id);
  if (!record) return `Slot ${slot.toUpperCase()} empty or deleted.`;
  return `${slot.toUpperCase()} · ${record.workflow || record.id}`;
}
</script>

<template>
  <StudioCard v-if="pair.a || pair.b" class="cmst:p-4" data-testid="vue-compare">
    <div class="cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-2">
      <div class="cmst:min-w-0">
        <h3 class="cmst-type-section">Compare</h3>
        <p class="cmst-type-meta cmst:mt-0.5">transient — never persisted</p>
      </div>
      <div class="cmst:flex cmst:gap-1.5">
        <StudioButton variant="ghost" size="sm" data-testid="vue-compare-swap" @click="history.swapCompare()">Switch A/B</StudioButton>
        <StudioButton variant="ghost" size="sm" data-testid="vue-compare-clear" @click="history.clearCompare()">Clear</StudioButton>
      </div>
    </div>
    <!-- Side-by-side wells on matte; images are never double-wrapped in
      bordered boxes — the well is the only frame. -->
    <div class="cmst:mt-3 cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-2">
      <figure v-for="slot in (['a', 'b'] as const)" :key="slot" class="cmst:min-w-0">
        <div class="cmst-media-well cmst:flex cmst:aspect-[4/3] cmst:items-center cmst:justify-center">
          <img
            v-if="urlOf(slot === 'a' ? history.compareA : history.compareB)"
            :src="urlOf(slot === 'a' ? history.compareA : history.compareB)!"
            :alt="`Compare ${slot.toUpperCase()}`"
            class="cmst:max-h-full cmst:max-w-full cmst:object-contain"
            :data-testid="`vue-compare-${slot}`"
          />
          <span v-else class="cmst:px-3 cmst:text-center cmst:text-xs cmst:text-cmst-muted">Slot {{ slot.toUpperCase() }} empty or deleted.</span>
        </div>
        <figcaption class="cmst-type-meta cmst:mt-1 cmst:truncate">{{ captionFor(slot) }}</figcaption>
      </figure>
    </div>
  </StudioCard>
</template>
