// Modal Studio F4C — History V2 Grid Columns consumer tests.
//
// Deterministic Node coverage for the modern Settings control
// "Settings → History → Grid columns" (localStorage key
// comfymodal-studio-history-columns, range 2–8, default 6):
//   - canonical normalization (missing/empty/NaN/float/below/above/malformed)
//   - mounted History V2 consumption guards (root carries the CSS variable
//     and data attribute; studio-styles.js grid rule resolves track count
//     from it; the legacy page reader is untouched)
//   - responsive semantics: a faithful simulation of the shipped CSS
//     auto-fill/max() formula proves every N yields 1..N tracks everywhere
//     and EXACTLY N tracks on ordinary desktop widths, never zero/invalid.
//
// Rendered-browser proof lives in tests/browser/fake/studio-fake-history-v2.spec.mjs
// (tests 18–21). No browser, no network here.

import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import {
  HISTORY_COLUMNS_KEY,
  HISTORY_COLUMNS_MIN,
  HISTORY_COLUMNS_MAX,
  HISTORY_COLUMNS_DEFAULT,
  normalizeHistoryColumns,
} from "../web/studio-history-v2.js";

const ROOT = path.join(import.meta.dirname, "..");
const WEB = path.join(ROOT, "web");
const readWeb = (name) => fs.readFileSync(path.join(WEB, name), "utf8");

const feedSource = readWeb("studio-history-v2.js");
const stylesSource = readWeb("studio-styles.js");
const settingsSource = readWeb("studio-settings.js");

function section(name) {
  console.log("PASS: " + name);
}

// In-memory localStorage stub mirroring the persisted-status unit style.
function createStorage() {
  const store = new Map();
  return {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => { store.set(k, String(v)); },
    removeItem: (k) => { store.delete(k); },
    clear: () => { store.clear(); },
  };
}

// ── 1–8. Canonical normalization ──────────────────────────────────────────

{
  const storage = createStorage();
  globalThis.localStorage = storage;

  // 1. Missing key → default 6 (production reads via localStorage.getItem).
  storage.clear();
  assert.equal(normalizeHistoryColumns(localStorage.getItem(HISTORY_COLUMNS_KEY)), 6);
  assert.equal(normalizeHistoryColumns(undefined), 6);
  section("1. Missing key normalizes to the default 6");

  // 2-5. Every valid boundary and mid value round-trips.
  assert.equal(normalizeHistoryColumns("2"), 2);
  section("2. Valid minimum 2 is honored");

  assert.equal(normalizeHistoryColumns("4"), 4);
  section("3. Valid 4 is honored");

  assert.equal(normalizeHistoryColumns("6"), 6);
  section("4. Valid default 6 is honored");

  assert.equal(normalizeHistoryColumns("8"), 8);
  section("5. Valid maximum 8 is honored");

  // 6. Below range clamps up to 2.
  assert.equal(normalizeHistoryColumns("0"), 2);
  assert.equal(normalizeHistoryColumns("1"), 2);
  assert.equal(normalizeHistoryColumns("-9"), 2);
  section("6. Below-range values clamp to 2");

  // 7. Above range clamps down to 8.
  assert.equal(normalizeHistoryColumns("9"), 8);
  assert.equal(normalizeHistoryColumns("42"), 8);
  assert.equal(normalizeHistoryColumns("999"), 8);
  section("7. Above-range values clamp to 8");

  // 8. Malformed input falls back to 6; floating point truncates exactly the
  //    way the Settings reader's parseInt does ("4.75" → 4), then clamps.
  assert.equal(normalizeHistoryColumns("abc"), 6);
  assert.equal(normalizeHistoryColumns(""), 6);
  assert.equal(normalizeHistoryColumns(null), 6);
  assert.equal(normalizeHistoryColumns("   "), 6);
  assert.equal(normalizeHistoryColumns({}), 6);
  assert.equal(normalizeHistoryColumns("4.75"), 4);
  assert.equal(normalizeHistoryColumns("2.5"), 2);
  assert.equal(normalizeHistoryColumns("8.9"), 8);
  assert.equal(normalizeHistoryColumns("0.5"), 2);

  // Corrupt/unavailable storage must degrade to the default, never throw:
  // the production reader wraps getItem in try/catch and returns null.
  const readerStart = feedSource.indexOf("function _readStoredColumns()");
  assert.notEqual(readerStart, -1, "_readStoredColumns reader missing");
  const readerBody = feedSource.slice(readerStart, readerStart + 400);
  assert.match(readerBody, /try\s*\{/);
  assert.match(readerBody, /catch\s*\(/);
  const throwingStorage = { getItem() { throw new Error("corrupt"); } };
  globalThis.localStorage = throwingStorage;
  let caught = null;
  let value = null;
  try {
    value = normalizeHistoryColumns(
      (() => { try { return localStorage.getItem(HISTORY_COLUMNS_KEY); } catch (e) { caught = e; return null; } })()
    );
  } finally {
    globalThis.localStorage = storage;
  }
  assert.ok(caught, "throwing storage surfaced the error to the guard");
  assert.equal(value, 6, "corrupt storage falls back to the default");
  section("8. Malformed/floating-point/corrupt state is safe (fallback 6)");
}

// ── 9. Mounted History V2 consumes the real setting ───────────────────────

{
  // The key contract matches across writer (Settings) and consumer (V2).
  assert.ok(
    settingsSource.includes('localStorage.setItem("comfymodal-studio-history-columns"'),
    "Settings must remain the writer of the columns key",
  );
  assert.ok(feedSource.includes('"comfymodal-studio-history-columns"'),
    "History V2 must reference the real settings key");

  // The mount applies the normalized value as an inline CSS custom property
  // plus a data attribute on the history page root.
  assert.ok(feedSource.includes("normalizeHistoryColumns(_readStoredColumns())"),
    "renderHistoryV2 must normalize the stored value at mount");
  assert.ok(feedSource.includes('"--comfymodal-studio-history-columns: " + gridColumns'),
    "the page root must carry the columns CSS variable inline");
  assert.ok(feedSource.includes('"data-grid-columns": String(gridColumns)'),
    "the page root must expose the resolved count as data-grid-columns");

  // The feed grid rule resolves its track count from the variable with the
  // documented default; the fixed legacy auto-fill-only rule is gone.
  assert.ok(stylesSource.includes("var(--comfymodal-studio-history-columns, 6)"),
    "grid rule must consume the columns variable with default 6");
  assert.match(stylesSource, /repeat\(\s*auto-fill,\s*minmax\(\s*max\(/s,
    "grid rule must use the auto-fill + max() responsive form");

  // The legacy History page reader was retired with the dead module in
  // Phase H9; the mounted V2 feed is the sole consumer of the key.
  section("9. Mounted History V2 consumes comfymodal-studio-history-columns");
}

// ── 10. Responsive semantics: simulate the shipped CSS formula ────────────

{
  // Constants mirrored from .comfymodal-studio-history-v2-grid in
  // studio-styles.js; the assertions below pin the source to them so the
  // simulation can never drift from the shipped rule.
  assert.match(stylesSource, /max\(\s*132px,/, "132px usability floor missing");
  assert.ok(stylesSource.includes("(100% - (var(--comfymodal-studio-history-columns, 6) - 1) * 12px)"),
    "gap-compensated share calc missing (gap must stay 12px)");
  assert.ok(stylesSource.includes("- 0.5px"), "rounding guard missing");
  assert.match(stylesSource, /@media \(max-width: 720px\)[\s\S]*?comfymodal-studio-history-v2-grid[\s\S]*?minmax\(230px, 1fr\)/,
    "narrow-viewport legacy density override missing");

  const GAP = 12;
  const FLOOR = 132;
  const GUARD = 0.5;
  function trackCount(containerWidth, n) {
    const share = (containerWidth - (n - 1) * GAP) / n;
    const minTrack = Math.max(FLOOR, share - GUARD);
    return Math.floor((containerWidth + GAP) / (minTrack + GAP));
  }

  // Ordinary desktop widths must produce EXACTLY N columns for every N.
  const desktopWidths = [1164, 1240, 1400, 1920];
  for (const w of desktopWidths) {
    for (let n = HISTORY_COLUMNS_MIN; n <= HISTORY_COLUMNS_MAX; n++) {
      assert.equal(trackCount(w, n), n,
        "desktop width " + w + " must honor " + n + " columns");
    }
  }

  // Narrow containers reflow to fewer equal columns but never zero/invalid.
  const narrowWidths = [280, 320, 420, 600, 900];
  for (const w of narrowWidths) {
    for (let n = HISTORY_COLUMNS_MIN; n <= HISTORY_COLUMNS_MAX; n++) {
      const c = trackCount(w, n);
      assert.ok(Number.isInteger(c), "track count must be an integer");
      assert.ok(c >= 1, "width " + w + " N=" + n + " collapsed to zero columns");
      assert.ok(c <= n, "width " + w + " N=" + n + " exceeded the requested count");
      assert.ok(w / c >= FLOOR - 1, "width " + w + " N=" + n + " crushed cards below the floor");
    }
  }
  section("10. Responsive rule yields exactly N desktop columns; narrow widths stay usable");
}

// ── 11. Constants contract ────────────────────────────────────────────────

{
  assert.equal(HISTORY_COLUMNS_KEY, "comfymodal-studio-history-columns");
  assert.equal(HISTORY_COLUMNS_MIN, 2);
  assert.equal(HISTORY_COLUMNS_MAX, 8);
  assert.equal(HISTORY_COLUMNS_DEFAULT, 6);
  section("11. Key/range/default match the F4A Settings authority contract");
}

console.log("PASS: studio history v2 grid columns unit tests");
