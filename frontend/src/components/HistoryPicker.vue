<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useHistoryStore } from "../stores/history";
import type { HistoryRecord } from "../api/history";
import { selectFeedAsset } from "../api/history";
import StudioButton from "./StudioButton.vue";
import StudioCard from "./StudioCard.vue";
import { getStudioPortalTarget } from "./portalTarget";

const history = useHistoryStore();
const pickerSearch = ref("");
const portalTarget = ref<HTMLElement | null>(null);

onMounted(async () => {
  portalTarget.value = getStudioPortalTarget();
  await history.initialize();
});

const emit = defineEmits<{
  select: [record: HistoryRecord];
  cancel: [];
}>();

let timer: number | undefined;
function onSearch(value: string) {
  window.clearTimeout(timer);
  timer = window.setTimeout(() => {
    history.setQuery(value);
    void history.loadFeed();
  }, 250);
}

function choose(record: HistoryRecord) {
  emit("select", record);
}
</script>

<template>
  <Teleport :to="portalTarget ?? undefined">
    <div class="cmst:fixed cmst:inset-0 cmst:z-[70] cmst:flex cmst:items-center cmst:justify-center cmst:bg-black/60 cmst:p-6" data-state="open" data-testid="vue-history-picker" role="dialog" aria-modal="true" aria-label="Pick a History generation" tabindex="-1" @keydown.esc.stop="emit('cancel')">
      <StudioCard class="cmst:w-[min(48rem,94vw)] cmst:max-h-[86vh] cmst:overflow-auto cmst:p-4">
        <div class="cmst:flex cmst:items-center cmst:justify-between cmst:gap-2">
          <h2 class="cmst:text-base cmst:font-semibold">Pick from History</h2>
          <StudioButton variant="ghost" size="sm" data-testid="vue-picker-cancel" @click="emit('cancel')">Cancel</StudioButton>
        </div>
        <input v-model="pickerSearch" class="cmst:mt-3 cmst:h-9 cmst:w-full cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm" placeholder="Search generations" aria-label="Search generations" @input="onSearch(($event.target as HTMLInputElement).value)" />
        <div v-if="!history.records.length" class="cmst:mt-3 cmst:text-sm cmst:opacity-70" data-testid="vue-picker-empty">No generations match.</div>
        <div v-else class="cmst:mt-3 cmst:grid cmst:grid-cols-2 cmst:gap-2 cmst:sm:grid-cols-3">
          <button
            v-for="record in history.records"
            :key="`${record.kind}:${record.id}`"
            type="button"
            class="cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:p-2 cmst:text-left cmst:hover:bg-cmst-secondary"
            :data-testid="`vue-picker-option-${record.id}`"
            :aria-label="`Select ${record.workflow || record.id}`"
            @click="choose(record)"
          >
            <img v-if="record.featuredOutput" :src="selectFeedAsset(record.featuredOutput)" :alt="record.workflow || record.id" class="cmst:aspect-square cmst:w-full cmst:object-cover cmst:rounded" loading="lazy" />
            <span class="cmst:mt-1 cmst:block cmst:truncate cmst:text-xs">{{ record.workflow || record.id }}</span>
          </button>
        </div>
        <div class="cmst:mt-3 cmst:flex cmst:justify-center">
          <StudioButton v-if="history.hasMore" variant="outline" size="sm" @click="history.loadFeed(true)">Load more</StudioButton>
        </div>
      </StudioCard>
    </div>
  </Teleport>
</template>
