<script setup lang="ts">
import type { HistoryRecord } from "../api/history";
import StudioButton from "./StudioButton.vue";

defineProps<{ record: HistoryRecord | null }>();
const emit = defineEmits<{ close: [] }>();
</script>

<template>
  <div v-if="record" class="cmst:fixed cmst:inset-0 cmst:z-[72] cmst:flex cmst:items-center cmst:justify-center cmst:bg-black/70 cmst:p-6" data-testid="vue-history-viewer" @click.self="emit('close')">
    <div class="cmst:max-h-full cmst:w-[min(56rem,94vw)] cmst:overflow-auto cmst:rounded-lg cmst:bg-cmst-surface cmst:p-4">
      <div class="cmst:flex cmst:items-center cmst:justify-between cmst:gap-2">
        <div><h2 class="cmst:text-lg cmst:font-semibold">{{ record.workflow || record.id }}</h2><p class="cmst:text-xs cmst:opacity-70">{{ record.status }} · {{ record.kind }}</p></div>
        <StudioButton variant="outline" size="sm" @click="emit('close')">Close</StudioButton>
      </div>
      <img v-if="record.featuredOutput" :src="record.featuredOutput.previewUrl" :alt="record.workflow || record.id" class="cmst:mt-4 cmst:mx-auto cmst:max-h-[70vh] cmst:max-w-full cmst:object-contain" />
      <p v-else class="cmst:mt-4 cmst:text-sm cmst:opacity-70">No projected image asset.</p>
    </div>
  </div>
</template>
