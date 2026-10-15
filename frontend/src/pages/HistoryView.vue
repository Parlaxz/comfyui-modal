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
import { studioPageClass } from "../components/studioPanels";

const history = useHistoryStore();
const route = useRoute();
const router = useRouter();
const search = ref(history.query);
const viewerOpen = ref(false);

onMounted(async () => {
  await history.initialize();
  const focus = typeof route.query.focus === "string" ? route.query.focus : null;
  if (focus) {
    history.setFocus(focus);
    await history.loadDetail(focus);
  }
});

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
  viewerOpen.value = true;
}
</script>

<template>
  <section :class="studioPageClass()" data-testid="vue-page-history">
    <StudioCard class="cmst:p-4">
      <div class="cmst:flex cmst:flex-wrap cmst:items-center cmst:justify-between cmst:gap-3">
        <div>
          <h2 class="cmst:text-lg cmst:font-semibold cmst:flex cmst:items-center cmst:gap-2"><History class="cmst:size-5" aria-hidden="true" />History V2</h2>
          <p class="cmst:text-sm cmst:opacity-80">History V2 is the Vue production data source; the server cursor remains authoritative.</p>
        </div>
        <StudioButton variant="outline" size="icon" aria-label="Refresh history" :disabled="history.loading" @click="history.loadFeed()"><RefreshCw class="cmst:size-4" :class="history.loading ? 'cmst:animate-spin' : ''" /></StudioButton>
      </div>
      <div class="cmst:mt-3 cmst:flex cmst:flex-wrap cmst:items-center cmst:gap-2">
        <label class="cmst:flex cmst:items-center cmst:gap-2 cmst:text-sm"><Search class="cmst:size-4" aria-hidden="true" /><input v-model="search" class="cmst:h-9 cmst:w-64 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2" placeholder="Search history" data-testid="vue-history-search" /></label>
        <select v-model="history.sort" class="cmst:h-9 cmst:rounded-md cmst:border cmst:border-solid cmst:border-cmst-border cmst:bg-cmst-bg cmst:px-2 cmst:text-sm" @change="history.setSort(history.sort); history.loadFeed()"><option value="newest">Newest</option><option value="oldest">Oldest</option><option value="fastest">Fastest</option><option value="slowest">Slowest</option></select>
        <label class="cmst:flex cmst:items-center cmst:gap-2 cmst:text-sm"><input v-model="history.favoriteOnly" type="checkbox" @change="history.setFavoriteOnly(history.favoriteOnly); history.loadFeed()" /> Favorites</label>
      </div>
    </StudioCard>

    <div v-if="history.error" class="cmst:rounded-md cmst:border cmst:border-solid cmst:border-red-400 cmst:p-3 cmst:text-sm cmst:text-red-300" role="alert">{{ history.error }}</div>
    <StudioCard v-if="history.loading && !history.records.length" class="cmst:p-6 cmst:text-sm">Loading History V2…</StudioCard>
    <StudioCard v-else-if="!history.records.length" class="cmst:p-6 cmst:text-sm cmst:opacity-75">No History V2 records match this query.</StudioCard>
    <ImageGrid v-else :records="history.records" @select="selectRecord" />
    <StudioButton v-if="history.hasMore" variant="outline" class="cmst:self-center" @click="history.loadFeed(true)">Load more</StudioButton>
    <StudioViewer :record="history.selected" v-if="viewerOpen" @close="viewerOpen = false" />
  </section>
</template>
