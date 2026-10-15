<script setup lang="ts">
import type { HistoryRecord } from "../api/history";
import StudioCard from "./StudioCard.vue";

defineProps<{ record: HistoryRecord }>();
const emit = defineEmits<{ select: [record: HistoryRecord] }>();
</script>

<template>
  <StudioCard class="cmst:overflow-hidden cmst:cursor-pointer" @click="emit('select', record)">
    <img v-if="record.featuredOutput" :src="record.featuredOutput.thumbUrl" :alt="record.workflow || record.id" class="cmst:block cmst:aspect-square cmst:w-full cmst:object-cover" loading="lazy" />
    <div class="cmst:p-3 cmst:text-sm">
      <div class="cmst:flex cmst:items-center cmst:justify-between cmst:gap-2">
        <strong class="cmst:truncate">{{ record.workflow || record.id }}</strong>
        <span class="cmst:text-xs cmst:opacity-70">{{ record.status }}</span>
      </div>
      <p class="cmst:mt-1 cmst:truncate cmst:text-xs cmst:opacity-70">{{ record.id }}</p>
    </div>
  </StudioCard>
</template>
