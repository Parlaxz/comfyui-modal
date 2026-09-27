// Modal Studio — History V2 persisted status filter normalization tests
//
// Executable behavioral tests for the C16 persisted-filter fix:
//   - persisted view-state migration (legacy aliases → canonical wire statuses)
//   - canonical feed-record normalization (raw "success" → "completed")
//   - search + status combinations against the deterministic fixture dataset
//   - canonical statuses query output on the real v2 feed URL boundary
//
// No browser, no DOM, plain Node.  The view-state module reads/writes the
// global `localStorage`, which this file stubs with an in-memory map.
//
// Run: node tests/studio_history_v2_persisted_status_unit.mjs

import assert from "node:assert/strict";
import {
  loadHistoryViewState,
  saveHistoryViewState,
  normalizeViewState,
  STORAGE_KEY,
  VIEW_STATE_SCHEMA,
} from "../web/history-v2-view-state.js";
import {
  createHistoryRepository,
  normalizeFeedItem,
  normalizeStatuses,
} from "../web/history-v2-repository.js";
import { buildFixtureDataset, createFixtureRepository } from "../web/history-v2-fixtures.js";

// ── localStorage stub ────────────────────────────────────────────────────

function createStorage() {
  const store = new Map();
  return {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => { store.set(k, String(v)); },
    removeItem: (k) => { store.delete(k); },
    clear: () => { store.clear(); },
    raw: () => Object.fromEntries(store),
  };
}

const storage = createStorage();
globalThis.localStorage = storage;

/** Seed persisted view state with the exact shape the C15 UI wrote. */
function seedC15State(statuses, overrides) {
  const o = overrides || {};
  const state = {
    search: o.search != null ? o.search : "Smoke Test Workflow",
    filters: {
      kinds: o.kinds != null ? o.kinds : [],
      statuses: statuses,
      workflow: o.workflow != null ? o.workflow : "",
      preset: o.preset != null ? o.preset : "",
      favoriteOnly: false,
      dateFrom: "",
      dateTo: "",
      previewOnly: false,
      originalAvailable: false,
      hasImage: false,
    },
    sort: o.sort != null ? o.sort : "newest",
  };
  storage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function section(name) {
  console.log("PASS: " + name);
}

// ── 1. Fresh state (no persisted storage) ────────────────────────────────

{
  storage.clear();
  const fresh = loadHistoryViewState();
  assert.equal(fresh.schema, VIEW_STATE_SCHEMA, "fresh state carries the current schema");
  assert.equal(fresh.search, "", "fresh search is empty");
  assert.deepEqual(fresh.filters.statuses, [], "fresh statuses are empty (no explicit filter)");
  assert.equal(fresh.sort, "newest");

  const viaBoundary = normalizeViewState(undefined);
  assert.deepEqual(viaBoundary.filters.statuses, [], "undefined input normalizes to empty statuses");
  assert.equal(viaBoundary.search, "");
  section("1. Fresh state");
}

// ── 2. C15-shaped persisted state migrates to canonical statuses ────────
// A C15 save wrote the full visible set with "success" as the internal
// canonical ("success|running|partial" always visible + toggles).
{
  seedC15State(["success", "running", "partial", "failed"]);
  const migrated = loadHistoryViewState();
  assert.deepEqual(
    migrated.filters.statuses,
    ["completed", "running", "completed_with_failures", "failed"],
    "C15 aliases map to canonical wire statuses",
  );
  assert.equal(migrated.search, "Smoke Test Workflow", "search round-trips unchanged");
  assert.equal(migrated.schema, VIEW_STATE_SCHEMA);
  assert.equal(migrated.sort, "newest");

  // C15 default (no toggle enabled): success|running|partial.
  seedC15State(["success", "running", "partial"]);
  const def = loadHistoryViewState();
  assert.deepEqual(
    def.filters.statuses,
    ["completed", "running", "completed_with_failures"],
    "C15 default visible set migrates without inventing statuses",
  );

  // Direct boundary call, no localStorage involved.
  const viaBoundary = normalizeViewState({
    search: "Smoke Test Workflow",
    filters: { statuses: ["success", "running", "partial", "failed"] },
  });
  assert.deepEqual(
    viaBoundary.filters.statuses,
    ["completed", "running", "completed_with_failures", "failed"],
  );
  assert.equal(viaBoundary.search, "Smoke Test Workflow");
  section("2. C15-shaped persisted state");
}

// ── 3. Explicit completed-hidden state stays completed-hidden ────────────
{
  seedC15State(["running", "failed"]);
  const state = loadHistoryViewState();
  assert.deepEqual(
    state.filters.statuses,
    ["running", "failed"],
    "completed is not forced back into an explicit filter",
  );

  const viaBoundary = normalizeViewState({ filters: { statuses: ["interrupted", "canceled"] } });
  assert.deepEqual(
    viaBoundary.filters.statuses,
    ["interrupted", "canceled"],
    "any explicit exclusion survives normalization",
  );
  section("3. Explicit completed-hidden state");
}

// ── 4. Unknown obsolete aliases are ignored ──────────────────────────────
{
  seedC15State(["bogus", "obsolete_status"]);
  const state = loadHistoryViewState();
  assert.deepEqual(
    state.filters.statuses,
    [],
    "unknown aliases drop to an empty (inactive) filter, not an empty-but-active one",
  );
  assert.equal(state.search, "Smoke Test Workflow", "search survives an all-unknown status list");

  seedC15State(["success", "bogus"]);
  const mixed = loadHistoryViewState();
  assert.deepEqual(mixed.filters.statuses, ["completed"], "known aliases survive unknown ones");

  assert.deepEqual(normalizeStatuses(["weird", "nonsense"]), []);
  section("4. Unknown obsolete aliases");
}

// ── 5. Alias group mapping is canonical and deduped ──────────────────────
{
  assert.deepEqual(
    normalizeStatuses(["success", "succeeded", "successful", "completed", "complete", "done", "ok", "finished"]),
    ["completed"],
  );
  assert.deepEqual(normalizeStatuses(["failure", "error", "errored"]), ["failed"]);
  assert.deepEqual(normalizeStatuses(["cancelled", "cancel"]), ["canceled"]);
  assert.deepEqual(normalizeStatuses(["aborted", "abort", "stopped"]), ["interrupted"]);
  assert.deepEqual(normalizeStatuses(["pending", "queued", "in_progress", "processing", "active"]), ["running"]);
  assert.deepEqual(normalizeStatuses(["partial"]), ["completed_with_failures"]);
  assert.deepEqual(normalizeStatuses([" Success ", "Success"]), ["completed"], "case/whitespace tolerant");
  assert.deepEqual(normalizeStatuses(["success", "completed"]), ["completed"], "dedupes to canonical");
  assert.deepEqual(normalizeStatuses([]), [], "empty list stays empty");
  assert.deepEqual(normalizeStatuses(null), [], "null input yields empty");
  assert.deepEqual(normalizeStatuses("success"), [], "non-array input yields empty");
  section("5. Alias group mapping");
}

// ── 6. Feed-record normalization (raw "success" → "completed") ───────────
{
  const gen = normalizeFeedItem({ id: "g1", status: "success" });
  assert.equal(gen.kind, "generation");
  assert.equal(gen.status, "completed", "generation raw success normalizes to completed");

  const exp = normalizeFeedItem({ id: "e1", experiment_id: "e1", status: "partial" });
  assert.equal(exp.kind, "experiment");
  assert.equal(exp.status, "completed_with_failures", "experiment raw partial normalizes");

  assert.equal(normalizeFeedItem({ id: "g2", status: "completed" }).status, "completed");
  assert.equal(normalizeFeedItem({ id: "g3", status: "cancelled" }).status, "canceled");
  assert.equal(normalizeFeedItem({ id: "g4", status: "in_progress" }).status, "running");
  assert.equal(normalizeFeedItem({ id: "g5", status: "obsolete_status" }).status, "running",
    "unknown feed status falls back to running");

  const ds = buildFixtureDataset();
  const genCompleted = ds.generations.filter((g) => normalizeFeedItem(g).status === "completed").length;
  assert.equal(genCompleted, 14, "all 14 success fixture generations normalize to completed");
  const expCwf = ds.experiments.filter((e) => normalizeFeedItem(e).status === "completed_with_failures");
  assert.equal(expCwf.length, 1, "exp_005 (partial) normalizes to completed_with_failures");
  section("6. Feed-record normalization");
}

// ── 7. Search + status combinations against the fixture repository ───────
{
  const repo = createFixtureRepository();
  assert.equal((await repo.listFeed({ limit: 200 })).total, 35, "fixture has 35 records");

  assert.equal(
    (await repo.listFeed({ limit: 200, search: "portrait", statuses: ["completed"] })).total,
    10,
    "search 'portrait' + completed keeps all 10 Portrait Pro records",
  );
  assert.equal(
    (await repo.listFeed({ limit: 200, search: "portrait", statuses: ["failed"] })).total,
    0,
    "search 'portrait' + failed matches nothing",
  );
  assert.equal(
    (await repo.listFeed({ limit: 200, search: "clean", statuses: ["failed", "canceled", "running"] })).total,
    8,
    "search 'clean' + failed/canceled/running keeps the 8 Clean Workflow generations",
  );
  assert.equal(
    (await repo.listFeed({ limit: 200, search: "clean", statuses: ["completed", "completed_with_failures"] })).total,
    0,
    "search 'clean' + completed/cwf matches nothing (no completed Clean Workflow records)",
  );

  // Empty status semantics: no statuses means no status filtering.
  assert.equal(
    (await repo.listFeed({ limit: 200, search: "clean", statuses: [] })).total,
    9,
    "empty statuses list applies no status filter",
  );
  assert.equal(
    (await repo.listFeed({ limit: 200, statuses: [] })).total,
    35,
    "empty statuses returns the full dataset",
  );
  section("7. Search + status combinations");
}

// ── 8. Canonical statuses query output on the v2 feed URL boundary ───────
{
  const captured = [];
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    captured.push({ url: String(url), options: options || null });
    return {
      ok: true,
      status: 200,
      json: async () => ({
        items: [{ id: "g_ok", status: "success" }],
        total: 1,
        next_cursor: null,
        has_more: false,
      }),
    };
  };
  try {
    const repo = await createHistoryRepository({ mode: "v2", apiBase: "/comfymodal" });

    const page = await repo.listFeed({
      search: "Smoke Test Workflow",
      statuses: ["success", "bogus", "partial", "completed"],
      kinds: [],
      sort: "newest",
      limit: 24,
    });

    assert.equal(captured.length, 1, "exactly one feed request");
    const url = new URL(captured[0].url, "http://localhost");
    assert.equal(url.searchParams.get("search"), "Smoke Test Workflow", "search preserved verbatim");
    assert.equal(
      url.searchParams.get("statuses"),
      "completed,completed_with_failures",
      "statuses query is canonical: success→completed, bogus dropped, partial→completed_with_failures, deduped",
    );
    assert.equal(url.searchParams.get("order"), "newest");
    assert.equal(url.searchParams.get("kind"), "mixed");
    assert.equal(page.items[0].status, "completed", "raw success record normalizes through the feed path");

    // All-unknown statuses → the statuses param is omitted entirely.
    captured.length = 0;
    await repo.listFeed({ statuses: ["bogus"], limit: 24 });
    const url2 = new URL(captured[0].url, "http://localhost");
    assert.equal(url2.searchParams.get("statuses"), null, "unknown-only statuses send no statuses param");

    // The six supported V2 order forms; never emit "desc" as an order value.
    const six = ["newest", "oldest", "fastest", "slowest", "workflow_asc", "workflow_desc"];
    for (const sort of six) {
      captured.length = 0;
      await repo.listFeed({ sort, limit: 24 });
      const order = new URL(captured[0].url, "http://localhost").searchParams.get("order");
      assert.ok(six.indexOf(order) !== -1, "order must stay in the six supported V2 forms");
      assert.notEqual(order, "desc", "never emit 'desc' as the order value");
    }
  } finally {
    globalThis.fetch = realFetch;
  }
  section("8. Canonical statuses query output");
}

// ── 9. Save/load round-trip persists canonical statuses + schema ─────────
{
  storage.clear();
  saveHistoryViewState({
    search: "Smoke Test Workflow",
    filters: { statuses: ["success", "bogus", "partial", "failed"] },
    sort: "oldest",
  });
  const raw = JSON.parse(storage.getItem(STORAGE_KEY));
  assert.equal(raw.schema, VIEW_STATE_SCHEMA, "saved state is stamped with the current schema");
  assert.deepEqual(
    raw.filters.statuses,
    ["completed", "completed_with_failures", "failed"],
    "save writes canonical statuses only",
  );
  assert.equal(raw.search, "Smoke Test Workflow");

  const roundTrip = loadHistoryViewState();
  assert.deepEqual(
    roundTrip.filters.statuses,
    ["completed", "completed_with_failures", "failed"],
    "load after save round-trips canonical statuses",
  );
  assert.equal(roundTrip.search, "Smoke Test Workflow");
  section("9. Save/load round-trip");
}

console.log("PASS: studio history v2 persisted status unit tests");
