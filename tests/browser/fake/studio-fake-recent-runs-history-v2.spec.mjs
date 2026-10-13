// Modal Studio — Recent-runs filmstrip ← History V2 hydration (H13 Wave D).
//
// The Playground recent-runs filmstrip hydrates ONLY from
// GET /history-v2/feed?limit=50&order=newest&kind=mixed through
// createHistoryRepository({ mode: "v2" }).  This spec pins the mandated
// history-view behaviors against the deterministic fake backend:
//
//   - EVERY History V2 feed record appears newest-first, deduplicated — the
//     strip is a view of the History page, not a filtered subset.
//   - Single click → canvas; imageless-single click → History generation
//     detail; EXP click → History V2 modern detail page.
//   - Old migrated records follow truthful visibility rules
//     (scenario history_v2_wave_d).
//   - Imageless records keep a placeholder and never render a broken image.
//   - ZERO legacy routes are touched: no GET /run-history, /history,
//     /experiments hydration; no POST /studio/experiment creator; no
//     /experiments/{id} polls or /stop-now controls during pure navigation;
//     favorites/notes go ONLY to /history-v2/generations/{id}/favorite|note.
//
// Scenario 7 note (no global legacy-reopen fn): there is nothing meaningful
// to assert on window globals — loadExperimentIntoPlayground was DELETED from
// web/studio-playground.js, so the practical proof of "no legacy reopen path"
// is exactly the network absence (zero legacy GETs/POSTs below) plus DOM
// absence (zero experiment-grid-viewport mounts).  Both are asserted here.
//
// Scenarios 13/14 note: the live single-run scheduler snapshot poll (GET
// /comfymodal/experiments/{id} while a preset run is ACTIVE) is execution-path
// behavior owned by the run specs (studio-fake-workflow-run.spec.mjs et al.).
// THIS spec deliberately performs no preset single-run submission, so zero
// legacy poll/control traffic is expected during pure navigation.
//
// Gating details (G1-G6) remain owned by studio-fake-experiment-gating.spec.mjs;
// this file carries only one light end-to-end V2-creator submission mapping.

import { test, expect } from "@playwright/test";
import { setupFakeTest, enableExperimentMode, openExperimentManager } from "./helpers.mjs";

const ITEM = ".comfymodal-studio-carousel-item";
const EXP_ITEM = ".comfymodal-studio-carousel-item-experiment";
const GRID_VIEWPORT = '[data-testid="experiment-grid-viewport"]';

const LEGACY_HYDRATION_RES = [
  /\/comfymodal\/run-history/,
  /\/comfymodal\/history(\?|$)/,
  /\/comfymodal\/experiments($|\?)/,
];
const LEGACY_CREATOR_RE = /\/comfymodal\/studio\/experiment$/;
const V2_CREATE_RE = /\/comfymodal\/studio\/experiment-v2$/;
const LEGACY_POLL_RE = /\/comfymodal\/experiments\/.+$/;
const STOP_NOW_RE = /\/experiments\/[^/]+\/stop-now$/;
const FAVORITE_RE = /\/history-v2\/generations\/[^/]+\/favorite$/;
const NOTE_RE = /\/history-v2\/generations\/[^/]+\/note$/;
const LEGACY_ANNOTATION_RE = /run-history\/[^/]+\/annotations/;
const WF_SELECTOR = '[data-testid="workflow-selector"]';
const SUBMIT_BTN = '[data-testid="modern-experiment-submit-btn"]';

/**
 * Instrument every page request across mount + interactions.  Install BEFORE
 * setupFakeTest so mount-time hydration is covered too.
 */
function trackRoutes(page) {
  const buckets = {
    hydrationGets: [],
    creatorPosts: [],
    v2CreatePosts: [],
    stopNowPosts: [],
    pollGets: [],
    favoriteReqs: [],
    noteReqs: [],
    legacyAnnotationReqs: [],
  };
  const onRequest = (request) => {
    const url = request.url();
    const method = request.method();
    if (method === "GET" && LEGACY_HYDRATION_RES.some((re) => re.test(url))) {
      buckets.hydrationGets.push(method + " " + url);
    }
    if (method === "POST" && LEGACY_CREATOR_RE.test(url)) buckets.creatorPosts.push(url);
    if (method === "POST" && V2_CREATE_RE.test(url)) buckets.v2CreatePosts.push(url);
    if (method === "POST" && STOP_NOW_RE.test(url)) buckets.stopNowPosts.push(url);
    if (method === "GET" && LEGACY_POLL_RE.test(url)) buckets.pollGets.push(url);
    if (FAVORITE_RE.test(url)) buckets.favoriteReqs.push(url);
    if (NOTE_RE.test(url)) buckets.noteReqs.push(url);
    if (LEGACY_ANNOTATION_RE.test(url)) buckets.legacyAnnotationReqs.push(url);
  };
  page.on("request", onRequest);
  return { ...buckets, dispose() { page.off("request", onRequest); } };
}

/** Read filmstrip item identities from the DOM. */
async function readFilmstripDom(page) {
  return page.locator(ITEM).evaluateAll((els) =>
    els.map((el) => {
      const img = el.querySelector("img");
      return {
        id: el.getAttribute("data-id") || "",
        expid: el.getAttribute("data-expid") || "",
        imgSrc: img ? img.getAttribute("src") || "" : "",
        placeholder: !!el.querySelector(".comfymodal-studio-carousel-thumb-empty"),
      };
    })
  );
}

/** Map a DOM entry to its durable record id (data-id, expid, or asset-url prefix). */
function domIdOf(entry) {
  if (entry.id) return entry.id;
  if (entry.expid) return entry.expid;
  const m = entry.imgSrc.match(/\/assets\/([^/?]+)/);
  return m ? decodeURIComponent(m[1]).replace(/_o\d+_(thumb|preview)$/, "") : "";
}

/**
 * Compute the EXPECTED filmstrip contents from the same feed page the UI
 * hydrates from.  The strip shows EVERY feed record newest-first by
 * completedAt||startedAt, deduplicated by id — the same window the History
 * page reads, with no image/status filtering.
 */
async function expectedFilmstrip(page) {
  const res = await page.request.get("/comfymodal/history-v2/feed?limit=50&order=newest&kind=mixed");
  expect(res.ok()).toBe(true);
  const body = await res.json();
  const entries = [];
  for (const rec of body.items || []) {
    const ts = rec.completed_at || rec.started_at || rec.created_at || "";
    entries.push({ id: rec.id, ts });
  }
  entries.sort((a, b) => b.ts.localeCompare(a.ts));
  const seen = new Set();
  return entries.filter((e) => (seen.has(e.id) ? false : (seen.add(e.id), true)));
}

// ── Filmstrip hydration & ordering ───────────────────────────────────────

test.describe("Recent runs ← History V2 hydration & ordering", () => {
  test("1-4. singles + EXP items hydrate newest-first from History V2 without duplicates", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await expect(page.locator(ITEM).first()).toBeVisible({ timeout: 20000 });

      const dom = await readFilmstripDom(page);
      const domIds = dom.map(domIdOf);
      const expected = await expectedFilmstrip(page);

      // 3+4. DOM order == expected newest-first feed order, no dupes.
      expect(domIds).toEqual(expected.map((e) => e.id));
      expect(new Set(domIds).size).toBe(domIds.length);

      // 1. Generation items WITH images point at History V2 managed assets.
      const genEntries = dom.filter((d) => !d.expid && d.imgSrc);
      expect(genEntries.length).toBeGreaterThan(0);
      for (const g of genEntries) {
        expect(g.imgSrc).toMatch(/^\/comfymodal\/history-v2\/assets\//);
      }

      // 1b. Imageless records keep their place with a placeholder (same rule
      // as the History cards): failed/canceled/interrupted/no-output
      // generations are all present, with no img and a placeholder marker.
      for (const id of ["gen_failed", "gen_canceled", "gen_interrupted", "gen_no_image"]) {
        expect(domIds).toContain(id);
        const entry = dom.find((d) => domIdOf(d) === id);
        expect(entry.imgSrc).toBe("");
        expect(entry.placeholder).toBe(true);
      }

      // 2. Experiment items carry the EXP badge + data-expid.
      const expItem = page.locator(EXP_ITEM).first();
      await expect(expItem.locator(".comfymodal-studio-carousel-exp-badge")).toHaveText("EXP");
      expect(await expItem.getAttribute("data-expid")).toBeTruthy();

      // 3. First item is the newest record of the default seed.
      expect(domIds[0]).toBe("gen_ok");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("10. imageless records render placeholders (no broken img)", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await expect(page.locator(ITEM).first()).toBeVisible({ timeout: 20000 });

      // Every rendered thumb has a real src — placeholders carry no img at
      // all, so a missing src can never render broken.
      const srcs = await page.locator("img.comfymodal-studio-carousel-thumb").evaluateAll(
        (els) => els.map((el) => el.getAttribute("src") || "")
      );
      expect(srcs.length).toBeGreaterThan(0);
      for (const src of srcs) expect(src.trim()).not.toBe("");

      // gen_no_image is completed but produced NO outputs — it keeps its
      // newest-first place with a "No image" placeholder, exactly like its
      // History card.
      const dom = await readFilmstripDom(page);
      const domIds = dom.map(domIdOf);
      expect(domIds).toContain("gen_no_image");
      const noImage = dom.find((d) => domIdOf(d) === "gen_no_image");
      expect(noImage.imgSrc).toBe("");
      expect(noImage.placeholder).toBe(true);
      const noImageItem = page.locator(`${ITEM}[data-id="gen_no_image"]`);
      await expect(noImageItem.locator(".comfymodal-studio-carousel-thumb-empty")).toHaveText("No image");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("11. zero legacy hydration GETs across mount + interactions", async ({ page }) => {
    const tracker = trackRoutes(page);
    const fx = await setupFakeTest(page);
    try {
      await expect(page.locator(ITEM).first()).toBeVisible({ timeout: 20000 });

      // Interact: select a run, visit History, come back.
      await page.locator(ITEM).first().click();
      await fx.gotoPage("history");
      await expect(page.locator('[data-testid="history-v2-page"]')).toBeVisible({ timeout: 15000 });
      await fx.gotoPage("playground");
      await expect(page.locator(ITEM).first()).toBeVisible({ timeout: 15000 });

      expect(tracker.hydrationGets).toEqual([]);
      fx.assertNoConsoleErrors();
    } finally {
      tracker.dispose();
      fx.guard.dispose();
    }
  });

  test("12. zero legacy creator POSTs; engine creator log agrees", async ({ page }) => {
    const tracker = trackRoutes(page);
    const fx = await setupFakeTest(page);
    try {
      await expect(page.locator(ITEM).first()).toBeVisible({ timeout: 20000 });
      await page.locator(ITEM).first().click();

      expect(tracker.creatorPosts).toEqual([]);
      const state = await fx.getState();
      expect(
        state.experimentCreateRequests.filter((r) => r.route === "/comfymodal/studio/experiment")
      ).toEqual([]);
      fx.assertNoConsoleErrors();
    } finally {
      tracker.dispose();
      fx.guard.dispose();
    }
  });

  test("13+14. zero legacy poll GETs / stop-now POSTs during pure navigation", async ({ page }) => {
    const tracker = trackRoutes(page);
    const fx = await setupFakeTest(page);
    try {
      await expect(page.locator(ITEM).first()).toBeVisible({ timeout: 20000 });

      // Pure navigation/interaction only — NO preset single-run submission in
      // this spec (see header note about the live scheduler snapshot poll).
      await page.locator(ITEM).first().click();
      const expItem = page.locator(EXP_ITEM).first();
      await expItem.click();
      await expect(page.locator('[data-testid="history-v2-experiment-page"]')).toBeVisible({ timeout: 15000 });
      await fx.gotoPage("playground");
      await expect(page.locator(ITEM).first()).toBeVisible({ timeout: 15000 });

      expect(tracker.pollGets).toEqual([]);
      expect(tracker.stopNowPosts).toEqual([]);
      fx.assertNoConsoleErrors();
    } finally {
      tracker.dispose();
      fx.guard.dispose();
    }
  });
});

// ── Routing & annotations ────────────────────────────────────────────────

test.describe("Recent runs routing & annotations", () => {
  test("5. single click loads the full-size generation into the canvas", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      const genItem = page.locator(ITEM).filter({ has: page.locator('img[src*="gen_ok"]') }).first();
      await expect(genItem).toBeVisible({ timeout: 20000 });
      const itemSrc = await genItem.locator("img").getAttribute("src");

      await genItem.click();

      const canvas = page.locator('[data-testid="canvas-output"]');
      await expect(canvas).toBeVisible({ timeout: 10000 });
      const canvasSrc = await canvas.getAttribute("src");
      // The canvas loads the record's full-size display asset (the same
      // Preview > Original resolution the History detail uses) — never the
      // capped 256px carousel thumbnail.
      expect(canvasSrc).not.toBe(itemSrc);
      expect(canvasSrc).toMatch(/^\/comfymodal\/history-v2\/assets\//);
      const res = await page.request.get("/comfymodal/history-v2/feed?limit=50&order=newest&kind=mixed");
      expect(res.ok()).toBe(true);
      const rec = (await res.json().then((b) => b.items || [])).find((r) => r.id === "gen_ok");
      const feat = rec.outputs[rec.featured_output_index || 0] || rec.outputs[0];
      expect(canvasSrc).toBe(feat.preview_url || feat.original_url);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("6. EXP click routes to the History modern detail (never a grid)", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      const expItem = page.locator(EXP_ITEM).first();
      await expect(expItem).toBeVisible({ timeout: 20000 });
      await expItem.click();

      await expect(page.locator('[data-testid="history-v2-page"]')).toBeVisible({ timeout: 15000 });
      await expect(page.locator('[data-testid="history-v2-experiment-page"]')).toBeVisible({ timeout: 15000 });
      expect(await page.locator(GRID_VIEWPORT).count()).toBe(0);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("19. favorite + note write through /history-v2/generations only", async ({ page }) => {
    const tracker = trackRoutes(page);
    const fx = await setupFakeTest(page);
    try {
      const genItem = page.locator(ITEM).filter({ has: page.locator('img[src*="gen_ok"]') }).first();
      await expect(genItem).toBeVisible({ timeout: 20000 });
      await genItem.click();

      // Selecting a run reveals its metadata actions.
      const star = page.locator('[data-testid="favorite-star"]');
      await expect(star).toBeVisible({ timeout: 10000 });
      await star.click();
      await expect.poll(() => tracker.favoriteReqs.length, { timeout: 10000 }).toBe(1);
      expect(tracker.favoriteReqs[0]).toMatch(FAVORITE_RE);
      expect(tracker.favoriteReqs[0]).toContain("/generations/gen_ok/");
      expect(tracker.legacyAnnotationReqs).toEqual([]);

      // The note editor lives in a collapsible panel — open it first.
      await page.locator('[data-testid="note-toggle"]').click();
      const textarea = page.locator('[data-testid="note-textarea"]');
      await expect(textarea).toBeVisible({ timeout: 10000 });
      await textarea.fill("wave d durable note");
      await page.locator('[data-testid="note-save-btn"]').click();
      await expect.poll(() => tracker.noteReqs.length, { timeout: 10000 }).toBe(1);
      expect(tracker.noteReqs[0]).toMatch(NOTE_RE);
      expect(tracker.noteReqs[0]).toContain("/generations/gen_ok/");
      expect(tracker.legacyAnnotationReqs).toEqual([]);
      fx.assertNoConsoleErrors();
    } finally {
      tracker.dispose();
      fx.guard.dispose();
    }
  });

  test("15+16+20. light e2e: modern experiment submit hits ONLY /studio/experiment-v2", async ({ page }) => {
    // Full gating coverage lives in studio-fake-experiment-gating.spec.mjs
    // (G1-G6); this is the hydration-spec mapping proof that the creator
    // lane reachable from a hydrated Playground is V2-only.
    const tracker = trackRoutes(page);
    const fx = await setupFakeTest(page);
    try {
      await page.locator(WF_SELECTOR).selectOption("wf_text2img");
      await expect(page.locator('[data-testid="workflow-control-seed"]')).toBeVisible({ timeout: 10000 });
      await enableExperimentMode(page);
      const modal = await openExperimentManager(page);

      const btn = modal.locator(SUBMIT_BTN);
      await expect(btn).toBeEnabled({ timeout: 10000 });
      await btn.click();

      await expect.poll(() => tracker.v2CreatePosts.length, { timeout: 10000 }).toBe(1);
      expect(tracker.creatorPosts).toEqual([]);
      const state = await fx.getState();
      expect(state.experimentCreateRequests.filter((r) => r.route === "/comfymodal/studio/experiment-v2").length).toBe(1);
      expect(state.experimentCreateRequests.filter((r) => r.route === "/comfymodal/studio/experiment")).toEqual([]);
      fx.assertNoConsoleErrors();
    } finally {
      tracker.dispose();
      fx.guard.dispose();
    }
  });
});

// ── Legacy state safety & old-record visibility ──────────────────────────

test.describe("Legacy state safety & old-record visibility", () => {
  test("17. stale active browser state mounts the modern section only; nothing converted", async ({ page }) => {
    // Stale "active experiment" pointer + a legacy-looking draft predate the
    // mount.  Post-Wave-D this can only ever mount the modern (gated/runnable)
    // section — no legacy surface, no conversion POSTs of any kind.
    await page.addInitScript(() => {
      localStorage.setItem(
        "comfymodal.studio.experiment.active.v1",
        JSON.stringify({ experimentId: "exp_v2_stale_ghost" })
      );
      localStorage.setItem(
        "comfymodal.studio.experiment.draft.v1",
        JSON.stringify({ legacy: { featureId: "txt2img", axes: { seed: ["111", "222"] } } })
      );
    });
    const tracker = trackRoutes(page);
    const fx = await setupFakeTest(page);
    try {
      await enableExperimentMode(page);

      const surface = page.locator('[data-testid="experiment-run-surface"]');
      await expect(surface).toBeVisible({ timeout: 10000 });
      const modal = await openExperimentManager(page);
      await expect(modal.locator('[data-testid="experiment-v2-section"]')).toBeVisible();
      expect(await page.locator(GRID_VIEWPORT).count()).toBe(0);

      // Zero creator POSTs (legacy OR v2 — a stale pointer must not create),
      // zero stop-now, zero POSTs to any legacy route (nothing converted).
      expect(tracker.creatorPosts).toEqual([]);
      expect(tracker.v2CreatePosts).toEqual([]);
      expect(tracker.stopNowPosts).toEqual([]);

      // The stale ghost id only ever produces modern-surface reads.
      const state = await fx.getState();
      expect(state.experimentCreateRequests).toEqual([]);

      // The stale ghost fetch 404s by design (unknown id); allowlist the
      // browser's resource log line for it — the app handles it silently.
      fx.assertNoConsoleErrors(["Failed to load resource.*404"]);
    } finally {
      tracker.dispose();
      fx.guard.dispose();
    }
  });

  test("18. draft namespaces are untouched by playground navigation", async ({ page }) => {
    const DRAFT_KEY = "comfymodal.studio.experiment.draft.v1";
    const RESULTS_KEY = "comfymodal.studio.playground.results.v1";
    const DRAFT_VALUE = JSON.stringify({ keep: { featureId: "txt2img", axes: { seed: ["7"] } } });
    const RESULTS_VALUE = JSON.stringify({ preset_default: { keepMe: true } });
    await page.addInitScript(([draftKey, draftValue, resultsKey, resultsValue]) => {
      localStorage.setItem(draftKey, draftValue);
      localStorage.setItem(resultsKey, resultsValue);
    }, [DRAFT_KEY, DRAFT_VALUE, RESULTS_KEY, RESULTS_VALUE]);

    const fx = await setupFakeTest(page);
    try {
      // Navigate + click around: select a run, toggle experiment mode, visit
      // History and return.
      await expect(page.locator(ITEM).first()).toBeVisible({ timeout: 20000 });
      await page.locator(ITEM).first().click();
      await enableExperimentMode(page);
      await fx.gotoPage("history");
      await expect(page.locator('[data-testid="history-v2-page"]')).toBeVisible({ timeout: 15000 });
      await fx.gotoPage("playground");

      expect(await page.evaluate((k) => localStorage.getItem(k), DRAFT_KEY)).toBe(DRAFT_VALUE);
      expect(await page.evaluate((k) => localStorage.getItem(k), RESULTS_KEY)).toBe(RESULTS_VALUE);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("8+9. wave_d old records follow visibility rules; mirrored experiment opens in History", async ({ page }) => {
    let seeded = null;
    const fx = await setupFakeTest(page, {
      beforeMount: async ({ page: p, sessionId }) => {
        const res = await p.request.post("/__comfymodal_test/history-seed", {
          data: { sessionId, scenario: "history_v2_wave_d" },
        });
        expect(res.ok()).toBe(true);
        seeded = await res.json();
      },
    });
    expect(seeded).toMatchObject({ status: "ok", scenario: "history_v2_wave_d", v2: true });
    const tracker = trackRoutes(page);
    try {
      await expect(page.locator(ITEM).first()).toBeVisible({ timeout: 20000 });

      // Visibility rules: every migrated record appears newest-first — the
      // single WITH an image, the one WITHOUT an image (placeholder), and
      // the mirrored experiment; the modern generation (newest) is first.
      const dom = await readFilmstripDom(page);
      const domIds = dom.map(domIdOf);
      expect(domIds[0]).toBe("gen_wave_d_modern");
      expect(domIds).toContain("gen_wave_d_legacy_image");
      expect(domIds).toContain("exp_wave_d_legacy");
      expect(domIds).toContain("gen_wave_d_legacy_noimage");
      const legacyNoImage = dom.find((d) => domIdOf(d) === "gen_wave_d_legacy_noimage");
      expect(legacyNoImage.imgSrc).toBe("");
      expect(legacyNoImage.placeholder).toBe(true);

      // The imageless legacy single IS also viewable through the History
      // page search (same durable record, same detail).
      await fx.gotoPage("history");
      await expect(page.locator('[data-testid="history-v2-page"]')).toBeVisible({ timeout: 15000 });
      await page.locator('[data-testid="history-v2-search"]').fill("gen_wave_d_legacy_noimage");
      await expect(
        page.locator('.comfymodal-studio-history-v2-generation-card[data-id="gen_wave_d_legacy_noimage"]')
      ).toBeVisible({ timeout: 10000 });

      // The mirrored legacy experiment opens in the History modern detail.
      await fx.gotoPage("playground");
      const expItem = page.locator(`${ITEM}[data-expid="exp_wave_d_legacy"]`);
      await expect(expItem).toBeVisible({ timeout: 15000 });
      await expItem.click();
      await expect(page.locator('[data-testid="history-v2-page"]')).toBeVisible({ timeout: 15000 });
      await expect(page.locator('[data-testid="history-v2-experiment-page"]')).toBeVisible({ timeout: 15000 });
      expect(await page.locator(GRID_VIEWPORT).count()).toBe(0);

      expect(tracker.hydrationGets).toEqual([]);
      fx.assertNoConsoleErrors();
    } finally {
      tracker.dispose();
      fx.guard.dispose();
    }
  });
});
