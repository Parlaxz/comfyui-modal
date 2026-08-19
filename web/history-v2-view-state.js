// Modal Studio — History V2 View State
//
// localStorage persistence for the History V2 search / filter / sort UI
// state.  Pure logic — no DOM.  Resilient to missing localStorage and
// corrupt JSON (falls back to an in-memory object).  Every read returns a
// deep copy so callers can mutate the returned object freely.
//
// Persisted status filters are normalized to the canonical History V2 wire
// statuses at the load boundary (see normalizeViewState), so states saved by
// older releases ("success"/"partial" era) migrate deterministically while
// search and every other user choice round-trip unchanged.

import { normalizeStatuses } from "./history-v2-repository.js";

// ── Public constants ─────────────────────────────────────────────────────

export const STORAGE_KEY = "comfymodal.history.v2.viewstate";

// Bumped whenever the persisted shape changes; normalizeViewState is the
// migration boundary that brings older persisted states forward.
export const VIEW_STATE_SCHEMA = 2;

// The default feed hides these statuses.
export const DEFAULT_HIDDEN_STATUSES = ["failed", "canceled"];

// ── Internal memory fallback ─────────────────────────────────────────────

let _memoryState = null;

function _defaultViewState() {
  return {
    schema: VIEW_STATE_SCHEMA,
    search: "",
    filters: {
      kinds: [],
      statuses: [],
      workflow: "",
      preset: "",
      favoriteOnly: false,
      dateFrom: "",
      dateTo: "",
      previewOnly: false,
      originalAvailable: false,
      hasImage: false,
    },
    sort: "newest",
  };
}

function _firstStr(v) {
  return v != null && v !== "" ? String(v) : "";
}

// Deep copy / defensive re-shape of a stored state object so unknown or
// partial payloads never leak malformed fields into the UI.  Status filters
// are migrated to canonical wire statuses here (the deterministic boundary).
function _clone(state) {
  const s = state && typeof state === "object" ? state : {};
  const filters = s.filters && typeof s.filters === "object" ? s.filters : {};
  return {
    schema: VIEW_STATE_SCHEMA,
    search: _firstStr(s.search),
    filters: {
      kinds: Array.isArray(filters.kinds) ? filters.kinds.slice() : [],
      statuses: normalizeStatuses(filters.statuses),
      workflow: _firstStr(filters.workflow),
      preset: _firstStr(filters.preset),
      favoriteOnly: !!filters.favoriteOnly,
      dateFrom: _firstStr(filters.dateFrom),
      dateTo: _firstStr(filters.dateTo),
      previewOnly: !!filters.previewOnly,
      originalAvailable: !!filters.originalAvailable,
      hasImage: !!filters.hasImage,
    },
    sort: _firstStr(s.sort) || "newest",
  };
}

/**
 * Deterministic persisted-view-state normalization / migration boundary.
 * Maps legacy status aliases to canonical wire statuses, drops unknown
 * obsolete aliases, and stamps the current schema.  Search and every other
 * valid user choice are preserved verbatim.
 * @param {object|null|undefined} state
 * @returns {object} normalized view state
 */
export function normalizeViewState(state) {
  return _clone(state);
}

/**
 * Load the persisted History V2 view state.
 * Returns a deep copy on every call.  Falls back to an in-memory object
 * when localStorage is missing, JSON is corrupt, or nothing was stored.
 * @returns {object} view state
 */
export function loadHistoryViewState() {
  let stored = null;
  try {
    if (typeof localStorage !== "undefined" && localStorage) {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) stored = JSON.parse(raw);
    }
  } catch (err) {
    stored = null; // corrupt JSON / storage unavailable → memory fallback
  }
  if (stored && typeof stored === "object") {
    _memoryState = _clone(stored);
  } else if (!_memoryState) {
    _memoryState = _defaultViewState();
  }
  return _clone(_memoryState);
}

/**
 * Best-effort persist of the view state.  Never throws.
 * @param {object} state
 */
export function saveHistoryViewState(state) {
  try {
    if (typeof localStorage !== "undefined" && localStorage) {
      const snapshot = state && typeof state === "object" ? _clone(state) : _defaultViewState();
      localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
    }
  } catch (err) {
    // best effort — ignore write failures
  }
}
