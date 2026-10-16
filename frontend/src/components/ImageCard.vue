<script setup lang="ts">
import { computed } from "vue";
import { ImageOff, Star, Check } from "@lucide/vue";
import type { HistoryRecord } from "../api/history";
import { selectFeedAsset } from "../api/history";
import { useHistoryStore } from "../stores/history";
import StudioCard from "./StudioCard.vue";

const props = defineProps<{ record: HistoryRecord }>();
const emit = defineEmits<{ select: [record: HistoryRecord] }>();
const history = useHistoryStore();

const selectionKey = computed(() => `${props.record.kind}:${props.record.id}`);
const selected = computed(() => history.selection.includes(selectionKey.value));

function formatDuration(ms: number | null): string | null {
  if (typeof ms !== "number" || ms < 0) return null;
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

const dimensions = computed(() => {
  const output = props.record.featuredOutput;
  if (!output || typeof output.width !== "number" || typeof output.height !== "number") return null;
  return `${output.width}×${output.height}`;
});

async function toggleFavorite(event: Event) {
  event.stopPropagation();
  await history.setFavorite(props.record, !props.record.favorite).catch(() => undefined);
}

function toggleSelect(event: Event) {
  event.stopPropagation();
  history.toggleSelection(props.record);
}
</script>

<template>
  <StudioCard class="cmst:group cmst:overflow-hidden">
    <!-- Media to the edge on matte; footer below holds title + meta only. -->
    <div class="cmst-media-well cmst:relative">
      <button
        type="button"
        class="cmst:block cmst:w-full cmst:cursor-pointer cmst:bg-transparent cmst:p-0 cmst:text-left"
        :aria-label="`Open ${record.workflow || record.id}`"
        :data-testid="`vue-history-card-${record.id}`"
        @click="emit('select', record)"
        @keydown.enter="emit('select', record)"
      >
        <img
          v-if="record.featuredOutput"
          :src="selectFeedAsset(record.featuredOutput)"
          :alt="record.workflow || record.id"
          class="cmst:block cmst:aspect-square cmst:w-full cmst:object-cover"
          loading="lazy"
        />
        <span v-else class="cmst:flex cmst:aspect-square cmst:w-full cmst:items-center cmst:justify-center cmst:text-cmst-muted" aria-hidden="true">
          <ImageOff class="cmst:size-[18px]" />
        </span>
      </button>
      <!-- Contextual hover actions: favorite + bulk select. Pinned visible
        when active; keyboard reachable via focus-within. -->
      <div
        class="cmst-hover-actions cmst:absolute cmst:right-1.5 cmst:top-1.5 cmst:flex cmst:gap-1"
        :class="record.favorite || selected ? 'cmst-hover-actions-pinned' : ''"
      >
        <button
          type="button"
          class="cmst-icon-btn cmst:bg-cmst-raised/90"
          :aria-pressed="record.favorite ? 'true' : 'false'"
          :aria-label="record.favorite ? `Remove ${record.id} from favorites` : `Add ${record.id} to favorites`"
          :data-testid="`vue-history-favorite-${record.id}`"
          @click="toggleFavorite($event)"
        >
          <Star class="cmst:size-3.5" :class="record.favorite ? 'cmst:fill-cmst-primary cmst:text-cmst-primary' : ''" aria-hidden="true" />
        </button>
        <button
          type="button"
          class="cmst-icon-btn cmst:bg-cmst-raised/90"
          :aria-pressed="selected ? 'true' : 'false'"
          :aria-label="selected ? `Deselect ${record.id}` : `Select ${record.id}`"
          :data-testid="`vue-history-select-${record.id}`"
          @click="toggleSelect($event)"
        >
          <Check class="cmst:size-3.5" :class="selected ? 'cmst:text-cmst-primary' : ''" aria-hidden="true" />
        </button>
      </div>
    </div>
    <button
      type="button"
      class="cmst:block cmst:w-full cmst:cursor-pointer cmst:bg-transparent cmst:px-2.5 cmst:py-2 cmst:text-left"
      :aria-label="`Open ${record.workflow || record.id}`"
      @click="emit('select', record)"
    >
      <span class="cmst-type-object cmst:block cmst:truncate">{{ record.workflow || record.id }}</span>
      <span class="cmst-type-meta cmst:mt-0.5 cmst:block cmst:truncate">{{ record.status }} · {{ record.kind }}<template v-if="dimensions"> · {{ dimensions }}</template><template v-if="formatDuration(record.durationMs)"> · {{ formatDuration(record.durationMs) }}</template></span>
    </button>
  </StudioCard>
</template>
