// History V2 is the shared browser authority for Generation/Experiment
// projections. Playground, picker, compare, and viewer surfaces consume
// this store rather than building competing entity caches. The server
// remains ultimate truth; this store is its browser projection.
import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { definePersisted } from "../persistence/persistence";
import {
  bulkDeleteHistory,
  cancelExperiment,
  deleteHistoryRecord,
  downloadHistoryAsset,
  exportHistoryAsset,
  generateOriginal,
  getExperiment,
  getGeneration,
  getHistoryFeed,
  normalizeHistoryRecord,
  openHistoryAsset,
  resumeExperiment,
  resumeGeneration,
  retryExperimentCell,
  retryOriginal,
  revealHistoryAsset,
  selectCompareAsset,
  selectDetailAsset,
  selectFeedAsset,
  setExperimentFavorite,
  setExperimentNote,
  setFeaturedOutput,
  setGenerationFavorite,
  setGenerationNote,
  type HistoryOutput,
  type HistoryRecord,
} from "../api/history";
import { createLatestTask } from "../async/latest";
import { createCrossTabInvalidation, publishCrossTabInvalidation } from "../compatibility/crossTab";

const viewState = definePersisted("history.view.v2", { query: "", sort: "newest", favoriteOnly: false, kind: "mixed", status: "" });

export const useHistoryStore = defineStore("studio-history", () => {
  const records = ref<HistoryRecord[]>([]);
  const selectedId = ref<string | null>(null);
  const focusId = ref<string | null>(null);
  const query = ref(viewState.read().query);
  const sort = ref(viewState.read().sort);
  const favoriteOnly = ref(viewState.read().favoriteOnly);
  const kindFilter = ref(viewState.read().kind);
  const statusFilter = ref(viewState.read().status);
  const cursor = ref<string | null>(null);
  const hasMore = ref(false);
  const loading = ref(false);
  const error = ref<string | null>(null);
  const detailError = ref<string | null>(null);
  const compareA = ref<string | null>(null);
  const compareB = ref<string | null>(null);
  // Recent run convergence (HIST-RECENT): id-only references to runs the
  // Playground completed in this session. The entities themselves always
  // resolve through records (History V2 authority); this list never caches
  // entities, so Playground stays free of a second Generation cache.
  const recentRunIds = ref<Array<{ id: string; kind: HistoryRecord["kind"] }>>([]);
  const selection = ref<Set<string>>(new Set());
  const viewerOpen = ref(false);
  const actionMessage = ref<string | null>(null);
  const feedTask = createLatestTask();
  const detailTask = createLatestTask();
  let pendingReload = false;
  let stopCrossTab: (() => void) | null = null;

  const selected = computed(() => records.value.find((item) => item.id === selectedId.value) ?? null);
  const focused = computed(() => records.value.find((item) => item.id === focusId.value) ?? selected.value);
  const compareRecords = computed(() => ({
    a: records.value.find((item) => item.id === compareA.value) ?? null,
    b: records.value.find((item) => item.id === compareB.value) ?? null,
  }));
  const selectionList = computed(() => [...selection.value]);

  function persistView(): void {
    viewState.write({ query: query.value, sort: sort.value, favoriteOnly: favoriteOnly.value, kind: kindFilter.value, status: statusFilter.value });
  }

  function setFocus(id: string | null): void {
    focusId.value = id;
    if (id) selectedId.value = id;
  }

  function setQuery(value: string): void {
    query.value = value;
    persistView();
  }

  function setSort(value: string): void {
    sort.value = value;
    persistView();
  }

  function setFavoriteOnly(value: boolean): void {
    favoriteOnly.value = value;
    persistView();
  }

  function setKindFilter(value: string): void {
    kindFilter.value = value;
    persistView();
  }

  function setStatusFilter(value: string): void {
    statusFilter.value = value;
    persistView();
  }

  function upsertRecord(record: HistoryRecord): void {
    const index = records.value.findIndex((item) => item.id === record.id && item.kind === record.kind);
    if (index >= 0) records.value[index] = record;
    else records.value.unshift(record);
  }

  function dropRecord(kind: HistoryRecord["kind"], id: string): void {
    records.value = records.value.filter((item) => !(item.id === id && item.kind === kind));
    if (selectedId.value === id) selectedId.value = null;
    if (focusId.value === id) focusId.value = null;
    if (compareA.value === id) compareA.value = null;
    if (compareB.value === id) compareB.value = null;
    selection.value.delete(`${kind}:${id}`);
  }

  /**
   * Shared run-result ownership entry point (HIST-RECENT / RUN-RESULT-ATTACH).
   * Called by the Playground run controller path on authoritative completion.
   * Records the id only — never an entity — so no second Generation cache
   * can form here. Feed refresh (server truth) converges the full record.
   */
  function noteRunResult(id: string, kind: HistoryRecord["kind"] = "generation"): void {
    if (!id) return;
    recentRunIds.value = [{ id, kind }, ...recentRunIds.value.filter((entry) => entry.id !== id)].slice(0, 20);
  }

  async function loadFeed(append = false): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      const result = await feedTask.run(async (signal) => {
        const response = await getHistoryFeed({
          search: query.value,
          order: sort.value,
          favorite: favoriteOnly.value ? true : undefined,
          kind: kindFilter.value === "mixed" ? undefined : kindFilter.value,
          status: statusFilter.value || undefined,
          cursor: append ? cursor.value ?? undefined : undefined,
        });
        if (signal.aborted) return null;
        return response;
      });
      if (result.stale || !result.value) return;
      const response = result.value;
      const items = (response.items ?? response.records ?? []).map(normalizeHistoryRecord);
      records.value = append ? records.value.concat(items) : items;
      cursor.value = response.next_cursor ?? null;
      hasMore.value = response.has_more === true || Boolean(cursor.value);
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : "Could not load History V2";
      throw cause;
    } finally {
      loading.value = false;
      if (pendingReload) {
        pendingReload = false;
        void loadFeed();
      }
    }
  }

  async function loadDetail(id: string, kind: HistoryRecord["kind"] = "generation"): Promise<void> {
    detailError.value = null;
    try {
      const result = await detailTask.run(async (signal) => {
        const raw = kind === "experiment" ? await getExperiment(id) : await getGeneration(id);
        if (signal.aborted) return null;
        return raw;
      });
      if (result.stale || !result.value) return;
      upsertRecord(normalizeHistoryRecord(result.value));
      selectedId.value = id;
    } catch (cause) {
      detailError.value = cause instanceof Error ? cause.message : "Could not load History detail";
      throw cause;
    }
  }

  /** Route focus is authoritative: same id/kind the URL names, loaded on demand. */
  async function applyRouteFocus(id: string | null): Promise<void> {
    setFocus(id);
    if (!id) return;
    const known = records.value.find((item) => item.id === id);
    await loadDetail(id, known?.kind ?? "generation");
  }

  async function setFavorite(record: HistoryRecord, value: boolean): Promise<void> {
    const previous = record.favorite;
    record.favorite = value;
    try {
      if (record.kind === "experiment") await setExperimentFavorite(record.id, value);
      else await setGenerationFavorite(record.id, value);
      publishCrossTabInvalidation("history");
    } catch (cause) {
      record.favorite = previous;
      throw cause;
    }
  }

  async function setNote(record: HistoryRecord, note: string): Promise<void> {
    const previous = record.note;
    record.note = note;
    try {
      if (record.kind === "experiment") await setExperimentNote(record.id, note);
      else await setGenerationNote(record.id, note);
      publishCrossTabInvalidation("history");
    } catch (cause) {
      record.note = previous;
      throw cause;
    }
  }

  async function setFeatured(record: HistoryRecord, outputIndex: number): Promise<void> {
    await setFeaturedOutput(record.id, outputIndex);
    await loadDetail(record.id, record.kind);
    publishCrossTabInvalidation("history");
  }

  async function remove(record: HistoryRecord): Promise<void> {
    await deleteHistoryRecord(record);
    dropRecord(record.kind, record.id);
    publishCrossTabInvalidation("history");
  }

  function toggleSelection(record: HistoryRecord): void {
    const key = `${record.kind}:${record.id}`;
    const next = new Set(selection.value);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    selection.value = next;
  }

  function clearSelection(): void {
    selection.value = new Set();
  }

  async function removeSelected(): Promise<void> {
    const generationIds: string[] = [];
    const experimentIds: string[] = [];
    for (const key of selection.value) {
      const separator = key.indexOf(":");
      const kind = key.slice(0, separator);
      const id = key.slice(separator + 1);
      if (kind === "experiment") experimentIds.push(id);
      else generationIds.push(id);
    }
    if (!generationIds.length && !experimentIds.length) return;
    await bulkDeleteHistory(generationIds, experimentIds);
    for (const id of generationIds) dropRecord("generation", id);
    for (const id of experimentIds) dropRecord("experiment", id);
    clearSelection();
    publishCrossTabInvalidation("history");
  }

  async function runReplayAction(
    record: HistoryRecord,
    action: "original" | "retry" | "resume",
  ): Promise<unknown> {
    let result: unknown;
    if (action === "original") result = await generateOriginal(record.id);
    else if (action === "retry") result = await retryOriginal(record.id);
    else result = await resumeGeneration(record.id);
    actionMessage.value = `${action} accepted for ${record.id}`;
    publishCrossTabInvalidation("history");
    return result;
  }

  async function runExperimentAction(
    record: HistoryRecord,
    action: "resume" | "cancel",
    cellId?: string,
  ): Promise<unknown> {
    let result: unknown;
    if (action === "resume") result = await resumeExperiment(record.id);
    else if (cellId) result = await retryExperimentCell(record.id, cellId);
    else result = await cancelExperiment(record.id);
    await loadDetail(record.id, "experiment");
    publishCrossTabInvalidation("history");
    return result;
  }

  async function exportAsset(output: HistoryOutput): Promise<unknown> {
    const result = await exportHistoryAsset(output.assetId);
    output.exportState = "exported";
    return result;
  }

  function selectCompare(which: "a" | "b", id: string | null): void {
    if (which === "a") compareA.value = id;
    else compareB.value = id;
  }

  function swapCompare(): void {
    const next = compareA.value;
    compareA.value = compareB.value;
    compareB.value = next;
  }

  function clearCompare(): void {
    compareA.value = null;
    compareB.value = null;
  }

  async function initialize(): Promise<void> {
    if (!stopCrossTab) {
      stopCrossTab = createCrossTabInvalidation((kind) => {
        if (kind !== "history") return;
        if (loading.value) {
          pendingReload = true;
          return;
        }
        void loadFeed();
      });
    }
    if (!records.value.length) await loadFeed();
  }

  function clear(): void {
    records.value = [];
    selectedId.value = null;
    focusId.value = null;
    cursor.value = null;
    compareA.value = null;
    compareB.value = null;
    selection.value = new Set();
  }

  return {
    records, selected, selectedId, focused, focusId, query, sort, favoriteOnly,
    kindFilter, statusFilter, cursor, hasMore, loading, error, detailError,
    compareA, compareB, compareRecords, selection: selectionList, viewerOpen,
    actionMessage, recentRunIds,
    setFocus, setQuery, setSort, setFavoriteOnly, setKindFilter, setStatusFilter,
    upsertRecord, noteRunResult,
    loadFeed, loadDetail, applyRouteFocus,
    setFavorite, setNote, setFeatured, remove,
    toggleSelection, clearSelection, removeSelected,
    runReplayAction, runExperimentAction,
    exportAsset, openHistoryAsset, revealHistoryAsset, downloadHistoryAsset,
    selectCompare, swapCompare, clearCompare,
    selectFeedAsset, selectDetailAsset, selectCompareAsset,
    initialize, clear,
  };
});
