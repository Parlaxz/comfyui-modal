<script setup lang="ts">
import type { HistoryRecord } from "../api/history";
import { selectFeedAsset } from "../api/history";
import { useHistoryStore } from "../stores/history";
import StudioCard from "./StudioCard.vue";

defineProps<{ record: HistoryRecord }>();
const emit = defineEmits<{ select: [record: HistoryRecord] }>();
const history = useHistoryStore();

async function toggleFavorite(record: HistoryRecord, event: Event) {
  event.stopPropagation();
  await history.setFavorite(record, !record.favorite).catch(() => undefined);
}
</script>

<template>
  <StudioCard class="cmst:overflow-hidden">
    <button
      type="button"
      class="cmst:block cmst:w-full cmst:cursor-pointer cmst:bg-transparent cmst:p-0 cmst:text-left"
      :aria-label="`Open ${record.workflow || record.id}`"
      :data-testid="`vue-history-card-${record.id}`"
      @click="emit('select', record)"
      @keydown.enter="emit('select', record)"
    >
      <img v-if="record.featuredOutput" :src="selectFeedAsset(record.featuredOutput)" :alt="record.workflow || record.id" class="cmst:block cmst:aspect-square cmst:w-full cmst:object-cover" loading="lazy" />
    </button>
    <div class="cmst:flex cmst:items-center cmst:justify-between cmst:gap-2 cmst:p-3 cmst:text-sm">
      <div class="cmst:min-w-0">
        <strong class="cmst:block cmst:truncate">{{ record.workflow || record.id }}</strong>
        <span class="cmst:block cmst:truncate cmst:text-xs cmst:opacity-70">{{ record.status }} · {{ record.kind }}</span>
      </div>
      <button
        type="button"
        class="cmst:shrink-0 cmst:rounded cmst:px-2 cmst:py-1 cmst:text-base"
        :aria-pressed="record.favorite ? 'true' : 'false'"
        :aria-label="record.favorite ? `Remove ${record.id} from favorites` : `Add ${record.id} to favorites`"
        :data-testid="`vue-history-favorite-${record.id}`"
        @click="toggleFavorite(record, $event)"
      >
        {{ record.favorite ? "★" : "☆" }}
      </button>
    </div>
  </StudioCard>
</template>
