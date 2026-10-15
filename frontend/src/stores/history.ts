// History V2 is the shared browser authority for Generation/Experiment
// projections. Playground, picker, compare, and viewer surfaces should
// consume this store rather than build competing entity caches.
import { defineStore } from "pinia";
import { ref } from "vue";
import { definePersisted } from "../persistence/persistence";
import {
  deleteHistoryRecord, getExperiment, getGeneration, getHistoryFeed,
  normalizeHistoryRecord, setGenerationFavorite, setGenerationNote,
  type HistoryRecord,
} from "../api/history";
import { createLatestTask } from "../async/latest";
import { createCrossTabInvalidation, publishCrossTabInvalidation } from "../compatibility/crossTab";

const viewState = definePersisted("history.view.v2", { query: "", sort: "newest", favoriteOnly: false });

export const useHistoryStore = defineStore("studio-history", () => {
  const records = ref<HistoryRecord[]>([]);
  const selected = ref<HistoryRecord | null>(null);
  const focusId = ref<string | null>(null);
  const query = ref(viewState.read().query);
  const sort = ref(viewState.read().sort);
  const favoriteOnly = ref(viewState.read().favoriteOnly);
  const cursor = ref<string | null>(null);
  const hasMore = ref(false);
  const loading = ref(false);
  const error = ref<string | null>(null);
  const feedTask = createLatestTask();
  const detailTask = createLatestTask();
  let stopCrossTab: (() => void) | null = null;

  function setFocus(id: string | null): void { focusId.value = id; selected.value = records.value.find((item) => item.id === id) ?? selected.value; }
  function setQuery(value: string): void { query.value = value; viewState.write({ query: value, sort: sort.value, favoriteOnly: favoriteOnly.value }); }
  function setSort(value: string): void { sort.value = value; viewState.write({ query: query.value, sort: value, favoriteOnly: favoriteOnly.value }); }
  function setFavoriteOnly(value: boolean): void { favoriteOnly.value = value; viewState.write({ query: query.value, sort: sort.value, favoriteOnly: value }); }

  async function loadFeed(append = false): Promise<void> {
    loading.value = true;
    error.value = null;
    const result = await feedTask.run(async (signal) => {
      const response = await getHistoryFeed({ search: query.value, sort: sort.value, favorite_only: favoriteOnly.value, cursor: append ? cursor.value ?? undefined : undefined });
      if (signal.aborted) return null;
      return response;
    });
    if (result.stale || !result.value) return;
    const response = result.value;
    const items = (response.items ?? response.records ?? []).map(normalizeHistoryRecord);
    records.value = append ? records.value.concat(items) : items;
    cursor.value = response.next_cursor ?? null;
    hasMore.value = response.has_more === true || Boolean(cursor.value);
    loading.value = false;
  }

  async function loadDetail(id: string, kind: HistoryRecord["kind"] = "generation"): Promise<void> {
    const result = await detailTask.run(async (signal) => {
      const raw = kind === "experiment" ? await getExperiment(id) : await getGeneration(id);
      if (signal.aborted) return null;
      return raw;
    });
    if (result.stale || !result.value) return;
    const detail = normalizeHistoryRecord(result.value);
    selected.value = detail;
    const index = records.value.findIndex((item) => item.id === detail.id);
    if (index >= 0) records.value[index] = detail;
  }

  async function setFavorite(record: HistoryRecord, value: boolean): Promise<void> {
    await setGenerationFavorite(record.id, value);
    record.favorite = value;
    publishCrossTabInvalidation("history");
  }

  async function setNote(record: HistoryRecord, note: string): Promise<void> {
    await setGenerationNote(record.id, note);
    record.note = note;
    publishCrossTabInvalidation("history");
  }

  async function remove(record: HistoryRecord): Promise<void> {
    await deleteHistoryRecord(record);
    records.value = records.value.filter((item) => item.id !== record.id);
    if (selected.value?.id === record.id) selected.value = null;
    publishCrossTabInvalidation("history");
  }

  async function initialize(): Promise<void> {
    if (!stopCrossTab) stopCrossTab = createCrossTabInvalidation((kind) => { if (kind === "history") void loadFeed(); });
    if (!records.value.length) await loadFeed();
  }

  function clear(): void { records.value = []; selected.value = null; focusId.value = null; cursor.value = null; }

  return { records, selected, focusId, query, sort, favoriteOnly, cursor, hasMore, loading, error, setFocus, setQuery, setSort, setFavoriteOnly, loadFeed, loadDetail, setFavorite, setNote, remove, initialize, clear };
});
