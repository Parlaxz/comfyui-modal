<script setup lang="ts">
import type { HistoryRecord } from "../api/history";
import ImageCard from "./ImageCard.vue";

defineProps<{ records: HistoryRecord[] }>();
const emit = defineEmits<{ select: [record: HistoryRecord] }>();
</script>

<template>
  <div class="cmst:grid cmst:grid-cols-1 cmst:gap-3 cmst:sm:grid-cols-2 cmst:lg:grid-cols-3" data-testid="vue-history-grid">
    <ImageCard v-for="record in records" :key="`${record.kind}:${record.id}`" :record="record" @select="emit('select', $event)" />
  </div>
</template>
