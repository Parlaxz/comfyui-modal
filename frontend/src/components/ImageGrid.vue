<script setup lang="ts">
import { computed } from "vue";
import type { HistoryRecord } from "../api/history";
import { useSettingsStore } from "../stores/settings";
import ImageCard from "./ImageCard.vue";

const props = defineProps<{ records: HistoryRecord[] }>();
const emit = defineEmits<{ select: [record: HistoryRecord] }>();

const settings = useSettingsStore();

// Honor the Interface > history-columns preference; minmax(0,1fr) keeps the
// grid overflow-free at any width without a second mobile tree.
const columns = computed(() => {
  const parsed = Number.parseInt(String(settings.columnsPreference ?? "4"), 10);
  if (Number.isNaN(parsed)) return 4;
  return Math.min(8, Math.max(2, parsed));
});
</script>

<template>
  <div
    class="cmst:grid cmst:gap-3"
    :style="{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }"
    data-testid="vue-history-grid"
  >
    <ImageCard
      v-for="record in props.records"
      :key="`${record.kind}:${record.id}`"
      :record="record"
      @select="emit('select', $event)"
    />
  </div>
</template>
