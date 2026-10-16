<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { History, RefreshCw, Search } from "@lucide/vue";
import { useRoute, useRouter } from "vue-router";
import { useHistoryStore } from "../stores/history";
import type { HistoryRecord } from "../api/history";
import StudioButton from "../components/StudioButton.vue";
import StudioCard from "../components/StudioCard.vue";
import ImageGrid from "../components/ImageGrid.vue";
import StudioViewer from "../components/StudioViewer.vue";
import HistoryPicker from "../components/HistoryPicker.vue";
import CompareViewer from "../components/CompareViewer.vue";
import { studioPageClass } from "../components/studioPanels";

const history = useHistoryStore();
const route = useRoute();
const router = useRouter();
const search = ref(history.query);
const pickerOpen = ref(false);

function routeFocus(): string | null {
  const focus = route.query.focus;
  return typeof focus === "string" && focus !== "" ? focus : null;
}

onMounted(async () => {
  await history.initialize();
  await history.applyRouteFocus(routeFocus());
});

watch(
  () => route.query.focus,
  (focus) => {
    void history.applyRouteFocus(typeof focus === "string" ? focus : null);
  },
);

let searchTimer: number | undefined;
watch(search, (value) => {
  window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(() => {
    history.setQuery(value);
    void history.loadFeed();
  }, 250);
});

async function selectRecord(record: HistoryRecord) {
  history.setFocus(record.id);
  await router.replace({ name: "history", query: { focus: record.id } });
  await history.loadDetail(record.id, record.kind);
  history.viewerOpen = true;
}

async function closeViewer() {
  history.viewerOpen = false;
  await router.replace({ name: "history" });
}

function toggleBulk(record: HistoryRecord, event: Event) {
  event.stopPropagation();
  history.toggleSelection(record);
}

function usePicked(record: HistoryRecord) {
  pickerOpen.value = false;
  void selectRecord(record);
}
</script>

<template>
  <section :class="studioPageClass()" data-testid="vue-page-history">
    <StudioCard class="cmst:p-4">
      <div class="cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-3">
        <div>
          <h2 class="cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2"><History class="cmst:size-5" aria-hidden="true" />History V2</h2>
          <p class="cmst:text-sm cmst:opacity-80">Server cursor stays authoritative; stale reads never commit.</p>
        </div>
        <div class="cmst:flex cmst:gap-2">
          <StudioButton variant="outline" size="sm" data-testid="vue-history-picker-open" @click="pickerOpen = true">Pick generation</StudioButton>
          <StudioButton variant="outline" size="icon" aria-label="Refresh history" :disabled="history.loading" @click="history.loadFeed()"><RefreshCw class="cmst:size-4" :class="history.loading ? 'cmst:animate-spin' : ''" /></StudioButton>
        </div>
      </div>
      <div class="cmst:mt-3 cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2">
        <label class="cmst:flex cmst:items-center cmst:gap-2 cmst:text-sm"><Search class="cmst:size-4" aria-hidden="true" /><input v-model="search" class="cmst:h-9 cmst:w-56 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2" placeholder="Search history" aria-label="Search history" data-testid="vue-history-search" /></label>
        <select :value="history.kindFilter" class="cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm" aria-label="Record kind" @change="history.setKindFilter(($event.target as HTMLSelectElement).value); history.loadFeed()">
          <option value="mixed">All kinds</option>
          <option value="generation">Generations</option>
          <option value="experiment">Experiments</option>
        </select>
        <select :value="history.statusFilter" class="cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm" aria-label="Status filter" @change="history.setStatusFilter(($event.target as HTMLSelectElement).value); history.loadFeed()">
          <option value="">All statuses</option>
          <option value="completed">Completed</option>
          <option value="failed">Failed</option>
          <option value="running">Running</option>
          <option value="canceled">Canceled</option>
        </select>
        <select v-model="history.sort" class="cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm" aria-label="Sort order" @change="history.setSort(history.sort); history.loadFeed()">
          <option value="newest">Newest</option>
          <option value="oldest">Oldest</option>
          <option value="fastest">Fastest</option>
          <option value="slowest">Slowest</option>
        </select>
        <label class="cmst:flex cmst:items-center cmst:gap-2 cmst:text-sm"><input v-model="history.favoriteOnly" type="checkbox" @change="history.setFavoriteOnly(history.favoriteOnly); history.loadFeed()" /> Favorites</label>
      </div>
    </StudioCard>

    <div v-if="history.error" class="cmst:rounded-md cmst:border cmst:border-solid cmst:border-red-400 cmst:p-3 cmst:text-sm cmst:text-red-300" role="alert">
      {{ history.error }}
      <StudioButton class="cmst:ml-2" size="sm" variant="outline" @click="history.loadFeed()">Retry</StudioButton>
    </div>
    <StudioCard v-if="history.loading && !history.records.length" class="cmst:p-6 cmst:text-sm">Loading History V2…</StudioCard>
    <StudioCard v-else-if="!history.records.length" class="cmst:p-6 cmst:text-sm cmst:opacity-75" data-testid="vue-history-empty">
      No History V2 records match this query.
      <StudioButton class="cmst:ml-2" size="sm" variant="outline" @click="history.setQuery(''); search = ''; history.setStatusFilter(''); history.setKindFilter('mixed'); history.loadFeed()">Clear filters</StudioButton>
    </StudioCard>
    <template v-else>
      <div class="cmst:flex cmst:items-center cmst:justify-between">
        <p class="cmst:text-xs cmst:opacity-70">{{ history.records.length }} records · {{ history.selection.length }} selected</p>
        <div class="cmst:flex cmst:gap-2">
          <StudioButton v-if="history.selection.length" size="sm" variant="outline" data-testid="vue-history-bulk-delete" @click="history.removeSelected()">Delete selected ({{ history.selection.length }})</StudioButton>
          <StudioButton v-if="history.selection.length" size="sm" variant="ghost" @click="history.clearSelection()">Clear selection</StudioButton>
        </div>
      </div>
      <ImageGrid :records="history.records" @select="selectRecord" />
      <div class="cmst:flex cmst:justify-center">
        <StudioButton v-if="history.hasMore" variant="outline" @click="history.loadFeed(true)">Load more</StudioButton>
      </div>
      <div class="cmst:flex cmst:flex-wrap cmst:gap-2">
        <StudioButton
          v-for="record in history.records.slice(0, 6)"
          :key="`bulk-${record.kind}-${record.id}`"
          size="sm"
          :variant="history.selection.includes(`${record.kind}:${record.id}`) ? 'default' : 'ghost'"
          :data-testid="`vue-history-select-${record.id}`"
          @click="toggleBulk(record, $event)"
        >
          {{ history.selection.includes(`${record.kind}:${record.id}`) ? "✓" : "+" }} {{ record.id.slice(0, 12) }}
        </StudioButton>
      </div>
    </template>

    <CompareViewer />
    <StudioViewer :record="history.selected" v-if="history.viewerOpen" @close="closeViewer" />
    <HistoryPicker v-if="pickerOpen" @select="usePicked" @cancel="pickerOpen = false" />
  </section>
</template>
