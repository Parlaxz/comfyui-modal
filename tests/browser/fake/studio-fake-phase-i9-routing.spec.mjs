// Phase I9 — Studio hash routing, deep links, Back/Forward & stale-guard
// (fake E2E, permanent).
//
// Permanent product coverage for the frozen I9 contract:
//   A. page changes serialize to the canonical hash (#comfymodal=<page>)
//      while aria-current keeps tracking the single shell authority
//   B. browser Back returns to the previous Studio page (content +
//      aria-current agree)
//   C. browser Forward re-applies the newer page
//   D. a copied/reloaded URL carrying #comfymodal=history is honored by the
//      next open_testing_modal() invocation (host reload closes the modal;
//      reopen honors the hash)
//   E. History deep-link focus opens the durable record; invalid/deleted
//      ids fail soft (page still opens, no crash)
//   F. explicit programmatic alias opener wins over a stale URL hash and
//      serializes the resulting modern canonical route
//   G. Settings section focus scrolls to [data-section]; unknown sections
//      fail soft
//   H. late recent-runs responses can never re-render Playground over the
//      active page (both the filmstrip reload path and the unguarded
//      run-completion hydration path are pinned)
//   I. unrelated host hashes are never hijacked or corrupted
//
// No router library: local history/hash APIs only.

import { test, expect } from "@playwright/test";
import {
  createSession,
  installConsoleGuard,
  selectPreset,
  seedHistory,
  setupFakeTest,
  submitSingleRun,
  waitForStatus,
} from "./helpers.mjs";

const NAV = 'nav[aria-label="Studio pages"].comfymodal-studio-topnav';

const PAGE_MARKERS = {
  playground: '[data-testid="playground-page-title"]',
  history: '[data-testid="history-v2-page"]',
  workflows: '[data-testid="workflows-page"]',
  backend: '[data-testid="backend-page"]',
  settings: '[data-testid="settings-page-title"]',
};

async function expectSoleCurrent(page, pageId) {
  const currents = await page.evaluate(() =>
    Array.from(
      document.querySelectorAll('.comfymodal-studio-topnav button[aria-current="page"]')
    ).map((b) => b.getAttribute("data-page"))
  );
  expect(currents).toEqual([pageId]);
}

async function expectActivePage(page, pageId) {
  await expectSoleCurrent(page, pageId);
  await expect(page.locator(PAGE_MARKERS[pageId]).first()).toBeAttached();
}

/**
 * Assert the active page IS `pageId` and the page container carries no
 * Playground takeover — used after releasing held responses so a stale
 * continuation flip can never hide behind a passing earlier poll.
 */
async function expectHistorySurvives(page) {
  await expectSoleCurrent(page, "history");
  const state = await page.evaluate(() => {
    const current = document.querySelector(
      '.comfymodal-studio-topnav button[aria-current="page"]'
    );
    const container = document.querySelector('[data-testid="studio-page"]');
    return {
      current: current ? current.getAttribute("data-page") : null,
      hasHistory: !!container && !!container.querySelector('[data-testid="history-v2-page"]'),
      hasPlayground: !!container && (!!container.querySelector('[data-testid="feature-tabs"]') ||
        !!container.querySelector('[data-testid="playground-page-title"]')),
    };
  });
  expect(state).toEqual({ current: "history", hasHistory: true, hasPlayground: false });
}

/**
 * Hold EVERY matching request until the returned release function is called,
 * then pass everything through deterministically (same pattern as the I4/I6
 * specs — never unroute while a handler is still awaiting the gate).
 */
async function holdRequests(page, pattern) {
  let releaseFn = null;
  let released = false;
  const gate = new Promise((resolve) => { releaseFn = resolve; });
  await page.route(pattern, async (route) => {
    if (!released) await gate;
    await route.continue();
  });
  return () => {
    released = true;
    if (releaseFn) releaseFn();
  };
}

/**
 * Navigate a FRESH page directly to a deep link and mount the shell once —
 * mirrors a copied URL opened in ComfyUI (the shell resolves location.hash
 * at mount).
 */
async function openDirectShell(page, sessionId, hash) {
  await page.goto(`/?session=${encodeURIComponent(sessionId)}${hash}`, {
    waitUntil: "domcontentloaded",
  });
  await page.waitForFunction(
    () => typeof window.__mountStudioForTest === "function",
    null,
    { timeout: 15000 }
  );
  await page.evaluate(() => window.__mountStudioForTest());
  await expect(page.locator('[data-testid="studio-page"]')).toBeVisible();
}

/**
 * Open Studio through the REAL production entry point (modal-testing.js)
 * without the direct-shell harness mount, so opener/routing semantics run
 * exactly as in ComfyUI.
 */
async function openViaTestingModal(page, sessionId, { hash = "", alias } = {}) {
  const url = `/?session=${encodeURIComponent(sessionId)}${hash}`;
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(
    () => typeof window.__mountStudioForTest === "function",
    null,
    { timeout: 15000 }
  );
  await page.evaluate(async (aliasName) => {
    const mod = await import("/extensions/comfymodal-modal/modal-testing.js");
    window.__i9Modal = mod;
    mod.open_testing_modal(aliasName);
  }, alias);
  await expect(page.locator(".comfymodal-studio-modal[role='dialog']")).toBeVisible();
}

test.describe("I9 hash routing, deep links & stale navigation guard", () => {
  test("A. page switches write the canonical hash; aria-current follows", async ({
    page,
  }) => {
    const t = await setupFakeTest(page);
    try {
      // No studio hash is written merely by opening Studio.
      await page.locator(`${NAV} button[data-page="history"]`).click();
      await expect(page).toHaveURL(/#comfymodal=history$/);
      await expectActivePage(page, "history");

      await page.locator(`${NAV} button[data-page="workflows"]`).click();
      await expect(page).toHaveURL(/#comfymodal=workflows$/);
      await expectActivePage(page, "workflows");

      // Same-page re-render mechanisms (programmatic setPage) must not spam
      // new entries or corrupt the hash. (Backend is avoided entirely in
      // this spec: the fake server intentionally lacks several Backend-page
      // endpoints and its page would 404-console.)
      await page.evaluate(() => window.__studioApi.setPage("workflows"));
      await expect(page).toHaveURL(/#comfymodal=workflows$/);
      await expectActivePage(page, "workflows");
      t.assertNoConsoleErrors();
    } finally {
      t.guard.dispose();
    }
  });

  test("B/C. Back returns to the previous Studio page; Forward reapplies", async ({
    page,
  }) => {
    const t = await setupFakeTest(page);
    try {
      await page.locator(`${NAV} button[data-page="history"]`).click();
      await expect(page).toHaveURL(/#comfymodal=history$/);
      await page.locator(`${NAV} button[data-page="workflows"]`).click();
      await expect(page).toHaveURL(/#comfymodal=workflows$/);
      await expectActivePage(page, "workflows");

      // Back â†’ History.
      await page.goBack();
      await expect(page).toHaveURL(/#comfymodal=history$/);
      await expectActivePage(page, "history");
      await expect(page.locator('[data-testid="history-v2-page-title"]')).toHaveText("History");

      // Forward â†’ Workflows again.
      await page.goForward();
      await expect(page).toHaveURL(/#comfymodal=workflows$/);
      await expectActivePage(page, "workflows");

      // Back twice more lands on the seeded Playground entry, still inside
      // the Studio (never leaving ComfyUI mid-stack).
      await page.goBack(); // workflows â†’ history
      await expectActivePage(page, "history");
      await page.goBack(); // history â†’ seeded playground entry
      await expect(page).toHaveURL(/#comfymodal=playground$/);
      await expectActivePage(page, "playground");
      t.assertNoConsoleErrors();
    } finally {
      t.guard.dispose();
    }
  });

  test("D. copied/reloaded #comfymodal=history is honored by the next open", async ({
    page,
  }) => {
    const sessionId = await createSession(page);
    const guard = installConsoleGuard(page);
    try {
      await openViaTestingModal(page, sessionId, { hash: "#comfymodal=history" });

      // Deep link honored: History is the landing page with canonical state.
      await expectSoleCurrent(page, "history");
      await expect(page.locator(PAGE_MARKERS.history)).toBeVisible();
      const hashAfterOpen = await page.evaluate(() => window.location.hash);
      expect(hashAfterOpen).toBe("#comfymodal=history");

      // Host reload closes the modal (expected); reopening honors the hash.
      await page.reload({ waitUntil: "domcontentloaded" });
      await page.waitForFunction(
        () => typeof window.__mountStudioForTest === "function",
        null,
        { timeout: 15000 }
      );
      await page.evaluate(async () => {
        const mod = await import("/extensions/comfymodal-modal/modal-testing.js");
        mod.open_testing_modal();
      });
      await expect(page.locator(".comfymodal-studio-modal[role='dialog']")).toBeVisible();
      await expectSoleCurrent(page, "history");
      await expect(page.locator(PAGE_MARKERS.history)).toBeVisible();
      guard.assertNoErrors();
    } finally {
      guard.dispose();
    }
  });

  test("E. History focus deep link opens the record; invalid id fails soft", async ({
    page,
  }) => {
    // Self-contained page: the DEFAULT session seed already carries the
    // durable record "gen_ok", so the deep link resolves at mount.
    const sessionId = await createSession(page);
    const guard = installConsoleGuard(page);
    try {
      await openDirectShell(page, sessionId, "#comfymodal=history&focus=gen_ok");

      await expectSoleCurrent(page, "history");
      const overlay = page.locator(
        '.comfymodal-studio-history-v2-overlay[aria-label="Generation detail"]'
      );
      await expect(overlay).toBeVisible();
      // Hash stays canonical (encoded round-trip).
      expect(await page.evaluate(() => window.location.hash)).toBe(
        "#comfymodal=history&focus=gen_ok"
      );

      // Escape closes the detail; the feed behind remains usable.
      await page.keyboard.press("Escape");
      await expect(overlay).not.toBeVisible();
      guard.assertNoErrors();
    } finally {
      guard.dispose();
    }
  });

  test("E2. unknown/deleted focus id fails soft: History opens, no crash", async ({
    page,
  }) => {
    const sessionId = await createSession(page);
    const guard = installConsoleGuard(page);
    try {
      await openDirectShell(page, sessionId, "#comfymodal=history&focus=gen_deleted_xyz");

      await expectSoleCurrent(page, "history");
      await expect(page.locator(PAGE_MARKERS.history)).toBeVisible();
      // Truthful not-found placeholder (fail soft, never fabricated content).
      const overlay = page.locator(
        '.comfymodal-studio-history-v2-overlay[aria-label="Generation detail"]'
      );
      await expect(overlay).toBeVisible();
      await expect(overlay.getByText("Generation not found")).toBeVisible();
      // Closing restores a working History page.
      await overlay.getByRole("button", { name: "Close" }).last().click();
      await expect(overlay).not.toBeVisible();
      await expect(page.locator(PAGE_MARKERS.history)).toBeVisible();
      // The failed lookup legitimately surfaces as one resource 404; the
      // repository catches it and the UI fails soft (no page errors).
      guard.assertNoErrors(["Failed to load resource"]);
    } finally {
      guard.dispose();
    }
  });

  test("F. explicit alias opener wins over a stale hash and serializes the modern route", async ({
    page,
  }) => {
    const sessionId = await createSession(page);
    const guard = installConsoleGuard(page);
    try {
      // Stale hash points at Backend…
      await openViaTestingModal(page, sessionId, {
        hash: "#comfymodal=backend",
        alias: "results",
      });
      // …but the explicit legacy-compatible alias wins this invocation and
      // lands on the modern owner (results â†’ History V2).
      await expectSoleCurrent(page, "history");
      await expect(page.locator(PAGE_MARKERS.history)).toBeVisible();
      // Canonical modern route serialized; legacy vocabulary never exposed.
      expect(await page.evaluate(() => window.location.hash)).toBe("#comfymodal=history");
      guard.assertNoErrors();
    } finally {
      guard.dispose();
    }
  });

  test("G. Settings section focus scrolls to the section; unknown fails soft", async ({
    page,
  }) => {
    const sessionId = await createSession(page);
    const guard = installConsoleGuard(page);
    try {
      // "advanced" carries synchronous content rows (GPU control), so it
      // is visible at mount in the fake harness. ("outputs" populates its
      // rows asynchronously and is a pre-existing I7-owned surface.)
      await openViaTestingModal(page, sessionId, {
        hash: "#comfymodal=settings&focus=advanced",
      });
      await expectSoleCurrent(page, "settings");
      await expect(page.locator(PAGE_MARKERS.settings)).toBeAttached();

      const advanced = page.locator('[data-section="advanced"]');
      await expect(advanced).toBeVisible();
      // The scroll container actually scrolled toward the section…
      const pageContainer = page.locator(".comfymodal-studio-pagecontainer");
      await expect
        .poll(
          async () =>
            page.evaluate(() => {
              const pc = document.querySelector(".comfymodal-studio-pagecontainer");
              return pc ? pc.scrollTop : 0;
            }),
          { timeout: 5000, message: "settings page container did not scroll" }
        )
        .toBeGreaterThan(100);
      // …and the section ended anchored in view: its top is inside the
      // viewport and the container sits at its maximum scroll position
      // (truthful block:start end state for the LAST section — content
      // below it is shorter than the viewport).
      await expect
        .poll(async () => {
          return page.evaluate(() => {
            const adv = document.querySelector('[data-section="advanced"]');
            const pc = document.querySelector(".comfymodal-studio-pagecontainer");
            if (!adv || !pc) return null;
            const r = adv.getBoundingClientRect();
            const maxScroll = pc.scrollHeight - pc.clientHeight;
            return {
              topInView: r.y >= -1 && r.y <= window.innerHeight - 40,
              atMax: Math.abs(pc.scrollTop - maxScroll) <= 2,
            };
          });
        }, { timeout: 5000, message: "advanced section not anchored in view after focus scroll" })
        .toEqual({ topInView: true, atMax: true });
      expect(await page.evaluate(() => window.location.hash)).toBe(
        "#comfymodal=settings&focus=advanced"
      );

      // Unknown section id: Settings still opens normally (fail soft).
      await page.evaluate(() => {
        window.location.hash = "#comfymodal=settings&focus=no_such_section";
      });
      await expectSoleCurrent(page, "settings");
      await expect(page.locator(PAGE_MARKERS.settings)).toBeAttached();
      guard.assertNoErrors();
    } finally {
      guard.dispose();
    }
  });

  test("H1. late recent-runs filmstrip response cannot re-render Playground over History", async ({
    page,
  }) => {
    // Hold BEFORE mount so the initial Playground filmstrip fetch hangs.
    const releaseFeed = await holdRequests(page, /\/comfymodal\/history-v2\/feed/);
    const t = await setupFakeTest(page);
    try {
      // Guarantee visible feed content once released (test-control endpoint,
      // not intercepted by page.route).
      await t.seedHistory("history_v2_phase_e");

      // Playground mounted with its recent-runs fetch HELD.
      await expect(page.locator('[data-testid="playground-recent-runs-loading"]')).toBeVisible();

      // Navigate to History (its own feed is held too — loading state).
      await page.locator(`${NAV} button[data-page="history"]`).click();
      await expectSoleCurrent(page, "history");

      // Release the delayed responses.
      await releaseFeed();

      // Wait until History's own released feed actually rendered content —
      // by that point the stale Playground continuation (same released
      // batch) has fired; then re-assert with a settle window.
      await expect
        .poll(
          () => page.locator(".comfymodal-studio-history-v2-card").count(),
          { timeout: 10000, message: "History feed never rendered after release" }
        )
        .toBeGreaterThan(0);
      await page.waitForTimeout(300);
      await expectHistorySurvives(page);
      t.assertNoConsoleErrors();
    } finally {
      t.guard.dispose();
    }
  });

  test("H2. late run-completion hydration cannot force Playground over History", async ({
    page,
  }) => {
    const t = await setupFakeTest(page);
    try {
      await t.seedHistory("history_v2_phase_e");
      // Hold ONLY the recent-runs feed from now on (after the initial mount
      // fetch settled), then drive a real single run to completion so the
      // completion handler starts a SECOND, delayed hydration.
      await selectPreset(page, "preset_default");
      const releaseFeed = await holdRequests(page, /\/comfymodal\/history-v2\/feed/);

      await submitSingleRun(page);
      await waitForStatus(page, "Run completed");

      // Completion fired while the feed was held â†’ its hydration promise is
      // pending. Navigate away BEFORE releasing it.
      await page.locator(`${NAV} button[data-page="history"]`).click();
      await expectSoleCurrent(page, "history");

      // Release the delayed Playground response.
      await releaseFeed();

      // Wait for History's released feed content, then re-assert after a
      // settle window: the stale continuation (same released batch) has had
      // its chance and must have been dropped by the generation guard.
      await expect
        .poll(
          () => page.locator(".comfymodal-studio-history-v2-card").count(),
          { timeout: 10000, message: "History feed never rendered after release" }
        )
        .toBeGreaterThan(0);
      await page.waitForTimeout(300);
      await expectHistorySurvives(page);
      await page.waitForTimeout(200);
      await expectHistorySurvives(page);
      t.assertNoConsoleErrors();
    } finally {
      t.guard.dispose();
    }
  });

  test("I. unrelated host hashes are ignored, never hijacked or corrupted", async ({
    page,
  }) => {
    const t = await setupFakeTest(page);
    try {
      await page.locator(`${NAV} button[data-page="history"]`).click();
      await expect(page).toHaveURL(/#comfymodal=history$/);

      // Some OTHER part of the host app sets an unrelated hash.
      await page.evaluate(() => {
        window.location.hash = "#host-panel=open";
      });
      await expect(page).toHaveURL(/#host-panel=open$/);
      // Studio neither reacts nor corrupts anything: still on History.
      await expectSoleCurrent(page, "history");
      await expect(page.locator(PAGE_MARKERS.history)).toBeVisible();

      // Back through the unrelated hash returns to the managed Studio entry.
      await page.goBack();
      await expect(page).toHaveURL(/#comfymodal=history$/);
      await expectSoleCurrent(page, "history");

      // Forward to the unrelated hash again: ignored, Studio untouched.
      await page.goForward();
      await expect(page).toHaveURL(/#host-panel=open$/);
      await expectSoleCurrent(page, "history");
      await expect(page.locator(PAGE_MARKERS.history)).toBeVisible();
      t.assertNoConsoleErrors();
    } finally {
      t.guard.dispose();
    }
  });
});
