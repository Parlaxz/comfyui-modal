<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { RefreshCw, Search } from "@lucide/vue";
import { useRoute, useRouter } from "vue-router";
import { useHistoryStore } from "../stores/history";
import { useSettingsStore } from "../stores/settings";
import type { HistoryRecord } from "../api/history";
import StudioButton from "../components/StudioButton.vue";
import ImageGrid from "../components/ImageGrid.vue";
import StudioViewer from "../components/StudioViewer.vue";
import HistoryPicker from "../components/HistoryPicker.vue";
import CompareViewer from "../components/CompareViewer.vue";
import { studioPageClass } from "../components/studioPanels";

const history = useHistoryStore();
const settings = useSettingsStore();
const route = useRoute();
const router = useRouter();
const search = ref(history.query);
const pickerOpen = ref(false);

// Thumbnail density slider (Mix gallery pattern): writes the persisted
// Interface > history-columns preference through the existing store action.
const thumbColumns = computed({
  get: () => {
    const parsed = Number.parseInt(String(settings.columnsPreference ?? "4"), 10);
    return Number.isNaN(parsed) ? 4 : Math.min(8, Math.max(2, parsed));
  },
  set: (value: number) => settings.setHistoryColumns(String(value)),
});

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

function usePicked(record: HistoryRecord) {
  pickerOpen.value = false;
  void selectRecord(record);
}

function clearFilters() {
  history.setQuery("");
  search.value = "";
  history.setStatusFilter("");
  history.setKindFilter("mixed");
  void history.loadFeed();
}
</script>

<template>
  <section :class="studioPageClass()" data-testid="vue-page-history">
    <!-- Page toolbar: title + actions flush on the page background. -->
    <div class="cmst:flex cmst:flex-wrap cmst:items-end cmst:justify-between cmst:gap-3">
      <div>
        <h1 class="cmst-type-view">History</h1>
        <p class="cmst-type-meta cmst:mt-0.5">
          {{ history.records.length }} records · {{ history.selection.length }} selected
        </p>
      </div>
      <div class="cmst:flex cmst:items-center cmst:gap-1.5">
        <label class="cmst:flex cmst:items-center cmst:gap-2 cmst:text-xs cmst:text-cmst-muted">
          <span aria-hidden="true">Tiles</span>
          <input
            v-model.number="thumbColumns"
            type="range"
            min="2"
            max="8"
            step="1"
            aria-label="Thumbnail columns"
            data-testid="vue-history-thumb-size"
            class="cmst:accent-cmst-primary"
          />
          <span class="cmst-type-meta" aria-hidden="true">{{ thumbColumns }}</span>
        </label>
        <StudioButton variant="secondary" size="sm" data-testid="vue-history-picker-open" @click="pickerOpen = true">Pick generation</StudioButton>
        <StudioButton variant="ghost" size="icon" aria-label="Refresh history" :disabled="history.loading" @click="history.loadFeed()">
          <RefreshCw class="cmst:size-4" :class="history.loading ? 'cmst:animate-spin' : ''" aria-hidden="true" />
        </StudioButton>
      </div>
    </div>

    <!-- Compact filter row: controls separated by spacing, no band box. -->
    <div class="cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2">
      <div class="cmst:relative">
        <Search class="cmst:pointer-events-none cmst:absolute cmst:left-2.5 cmst:top-1/2 cmst:size-4 cmst:-translate-y-1/2 cmst:text-cmst-muted" aria-hidden="true" />
        <input v-model="search" class="cmst-field cmst:w-52 cmst:pl-8" placeholder="Search history" aria-label="Search history" data-testid="vue-history-search" />
      </div>
      <select :value="history.kindFilter" class="cmst-field" aria-label="Record kind" @change="history.setKindFilter(($event.target as HTMLSelectElement).value); history.loadFeed()">
        <option value="mixed">All kinds</option>
        <option value="generation">Generations</option>
        <option value="experiment">Experiments</option>
      </select>
      <select :value="history.statusFilter" class="cmst-field" aria-label="Status filter" @change="history.setStatusFilter(($event.target as HTMLSelectElement).value); history.loadFeed()">
        <option value="">All statuses</option>
        <option value="completed">Completed</option>
        <option value="failed">Failed</option>
        <option value="running">Running</option>
        <option value="canceled">Canceled</option>
      </select>
      <select v-model="history.sort" class="cmst-field" aria-label="Sort order" @change="history.setSort(history.sort); history.loadFeed()">
        <option value="newest">Newest</option>
        <option value="oldest">Oldest</option>
        <option value="fastest">Fastest</option>
        <option value="slowest">Slowest</option>
      </select>
      <label class="cmst:flex cmst:cursor-pointer cmst:items-center cmst:gap-1.5 cmst:text-[13px] cmst:text-cmst-muted">
        <input v-model="history.favoriteOnly" type="checkbox" @change="history.setFavoriteOnly(history.favoriteOnly); history.loadFeed()" />
        Favorites
      </label>
    </div>

    <div v-if="history.error" class="cmst:text-[13px] cmst:text-cmst-danger" role="alert">
      {{ history.error }}
      <StudioButton class="cmst:ml-2" size="sm" variant="ghost" @click="history.loadFeed()">Retry</StudioButton>
    </div>

    <p v-if="history.loading && !history.records.length" class="cmst:py-6 cmst:text-[13px] cmst:text-cmst-muted">
      Loading history…
    </p>
    <div v-else-if="!history.records.length" class="cmst:py-6 cmst:text-[13px] cmst:text-cmst-muted" data-testid="vue-history-empty">
      No records match this query.
      <StudioButton class="cmst:ml-2" size="sm" variant="ghost" @click="clearFilters">Clear filters</StudioButton>
    </div>
    <template v-else>
      <div v-if="history.selection.length" class="cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2">
        <span class="cmst-type-meta">{{ history.selection.length }} selected</span>
        <StudioButton size="sm" variant="outline" data-testid="vue-history-bulk-delete" @click="history.removeSelected()">Delete selected ({{ history.selection.length }})</StudioButton>
        <StudioButton size="sm" variant="ghost" @click="history.clearSelection()">Clear selection</StudioButton>
      </div>
      <ImageGrid :records="history.records" @select="selectRecord" />
      <div class="cmst:flex cmst:justify-center">
        <StudioButton v-if="history.hasMore" variant="outline" @click="history.loadFeed(true)">Load more</StudioButton>
      </div>
    </template>

    <!-- Detail surrounds stay page-level: compare + viewer stack in reading
      order without extra bordered wrappers (protected components untouched). -->
    <CompareViewer />
    <StudioViewer :record="history.selected" v-if="history.viewerOpen" @close="closeViewer" />
    <HistoryPicker v-if="pickerOpen" @select="usePicked" @cancel="pickerOpen = false" />
  </section>
</template>
