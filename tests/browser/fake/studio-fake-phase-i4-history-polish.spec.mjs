// Phase I4 — History polish & shared-primitives migration (fake E2E).
//
// Permanent product coverage for the I4 contract:
//   A. truthful accessible page h2 "History" under the shell h1
//      (visually hidden via the clip pattern — never display:none /
//      visibility:hidden), plus migrated chips carrying the shared
//      cm-chip base with truthful data-tone values
//   B. loading primitive semantics on deterministic, injectable History
//      loading states (feed + generation detail): role="status",
//      aria-live="polite", decorative spinner, truthful labels
//   C. every simultaneously visible favorite control has a distinguishable
//      accessible name (record context), flipping truthfully on toggle
//   D. generation detail dialog: invoking card focused → open → focus is
//      INSIDE the dialog → Escape closes → focus restores to the invoker
//   E. experiment detail page-swap analog: loading primitive during fetch,
//      focus lands on Back after the swap, keyboard Back restores the feed
//      with a deterministic focus anchor
//   F. (Re-pointed by I5, documented drift): the generation detail now
//      owns the sanctioned lightweight Compare entry — this test proves
//      the RETIREMENT guard instead of absence: no Comparison Profiles,
//      no Comparison Runner, no old A/B slider module, no /comparison/run.
//
// Keyboard interaction is used wherever a user would use it (D, E).

import { test, expect } from "@playwright/test";
import { setupFakeTest } from "./helpers.mjs";

const OVERLAY = '.comfymodal-studio-history-v2-overlay[aria-label="Generation detail"]';

/**
 * Hold EVERY matching request until the returned release function is called,
 * then pass everything through deterministically.  The handler stays
 * installed for the whole test: calling page.unroute() while a held handler
 * is still awaiting makes Playwright fall back-handle the route, and the
 * later route.continue() would throw "Route is already handled".  Await the
 * helper itself so registration can never race the request.
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

async function activeElementFacts(page, overlaySelector) {
  return page.evaluate((sel) => {
    const ae = document.activeElement;
    if (!ae) return { tag: null };
    const ov = document.querySelector(sel);
    return {
      tag: ae.tagName,
      testid: ae.getAttribute ? ae.getAttribute("data-testid") : null,
      ariaLabel: ae.getAttribute ? ae.getAttribute("aria-label") : null,
      className: typeof ae.className === "string" ? ae.className : "",
      insideOverlay: !!ov && ov.contains(ae),
    };
  }, overlaySelector);
}

test.describe("I4 History polish & primitives migration", () => {
  test("A. truthful page h2 under the shell h1; chips carry cm-chip + data-tone", async ({
    page,
  }) => {
    const t = await setupFakeTest(page);
    try {
      await t.gotoPage("history");
      const h2 = page.locator('[data-testid="history-v2-page-title"]');
      await expect(h2).toHaveCount(1);
      await expect(h2).toHaveText("History");
      // Truthful hierarchy: the History feed carries exactly one heading —
      // the truthful page h2 — and no card title was promoted into a
      // heading.  (The standalone fake harness mounts mountStudioShell
      // WITHOUT the production dialog wrapper that carries the shell h1;
      // the h1↔h2 pairing in production is pinned by the I2 dialog spec.)
      const headingCensus = await page.evaluate(() => {
        const hs = Array.from(document.querySelectorAll("h1,h2,h3,h4,h5,h6"));
        return {
          count: hs.length,
          tags: hs.map((h) => h.tagName),
          testids: hs.map((h) => h.getAttribute("data-testid")),
        };
      });
      expect(headingCensus.count).toBe(1);
      expect(headingCensus.tags).toEqual(["H2"]);
      expect(headingCensus.testids).toEqual(["history-v2-page-title"]);

      // Accessible-but-visually-hidden: clip pattern, never display:none /
      // visibility:hidden / [hidden].
      const h2Style = await h2.evaluate((el) => {
        const cs = getComputedStyle(el);
        const r = el.getBoundingClientRect();
        return {
          display: cs.display,
          visibility: cs.visibility,
          clip: cs.clip,
          width: r.width,
          height: r.height,
          hiddenAttr: el.hasAttribute("hidden"),
        };
      });
      expect(h2Style.display).not.toBe("none");
      expect(h2Style.visibility).not.toBe("hidden");
      expect(h2Style.hiddenAttr).toBe(false);
      expect(h2Style.clip).toContain("rect(");
      expect(h2Style.width).toBeLessThanOrEqual(2);
      expect(h2Style.height).toBeLessThanOrEqual(2);

      // Migrated chips: legacy status-* classes preserved AND shared base +
      // truthful tones present.
      const completedChip = page.locator(
        ".comfymodal-studio-history-v2-chip.status-completed"
      ).first();
      await expect(completedChip).toBeVisible();
      await expect(completedChip).toHaveClass(/cm-chip/);
      await expect(completedChip).toHaveAttribute("data-tone", "ok");

      const runningChip = page.locator(
        ".comfymodal-studio-history-v2-chip.status-running"
      ).first();
      await expect(runningChip).toHaveAttribute("data-tone", "running", { timeout: 10000 });

      const interruptedChip = page.locator(
        ".comfymodal-studio-history-v2-chip.status-interrupted"
      ).first();
      await expect(interruptedChip).toHaveAttribute("data-tone", "warn");

      const failedChip = page.locator(
        ".comfymodal-studio-history-v2-chip.status-failed"
      );
      if ((await failedChip.count()) > 0) {
        await expect(failedChip.first()).toHaveAttribute("data-tone", "error");
      }
      t.assertNoConsoleErrors();
    } finally {
      t.guard.dispose();
    }
  });

  test("B. deterministic History loading states use the shared primitive semantics", async ({
    page,
  }) => {
    // Gates install AFTER mount (awaited registration): Playground's own
    // initial feed fetch has already completed, so the held request is the
    // one issued by the History page itself.
    const t = await setupFakeTest(page);
    try {
      const releaseFeed = await holdRequests(page, /\/comfymodal\/history-v2\/feed/);
      const releaseGen = await holdRequests(page, /\/comfymodal\/history-v2\/generations\//);

      await t.gotoPage("history");
      const feedLoading = page.locator('[data-testid="history-v2-loading"]');
      await expect(feedLoading).toBeVisible({ timeout: 10000 });
      await expect(feedLoading).toHaveAttribute("role", "status");
      await expect(feedLoading).toHaveAttribute("aria-live", "polite");
      await expect(feedLoading).toHaveAttribute("data-size", "page");
      await expect(feedLoading.locator(".cm-loading-spinner")).toHaveAttribute(
        "aria-hidden",
        "true"
      );
      await expect(feedLoading.locator(".cm-loading-label")).toHaveText("Loading history…");

      releaseFeed();
      await expect(
        page.locator('[data-testid="history-v2-generation-card"]').first()
      ).toBeVisible({ timeout: 15000 });
      await expect(feedLoading).toHaveCount(0);
      await expect(feedLoading).toHaveCount(0);

      // ── Generation detail loading: record fetch is still held. ──
      await page
        .locator('[data-testid="history-v2-generation-card"][data-id="gen_ok"]')
        .click();
      const overlay = page.locator(OVERLAY);
      await expect(overlay).toBeVisible({ timeout: 10000 });
      const detailLoading = page.locator('[data-testid="history-v2-detail-loading"]');
      await expect(detailLoading).toBeVisible();
      await expect(detailLoading).toHaveAttribute("role", "status");
      await expect(detailLoading).toHaveAttribute("aria-live", "polite");
      await expect(detailLoading.locator(".cm-loading-label")).toHaveText("Loading generation…");

      releaseGen();
      await expect(
        overlay.locator(".comfymodal-studio-history-v2-run-line")
      ).toBeVisible({ timeout: 15000 });
      await expect(detailLoading).toHaveCount(0);
      t.assertNoConsoleErrors();
    } finally {
      t.guard.dispose();
    }
  });

  test("C. all simultaneously visible favorite controls have distinguishable names", async ({
    page,
  }) => {
    const t = await setupFakeTest(page);
    try {
      await t.gotoPage("history");
      const stars = page.locator('[data-testid="history-v2-favorite-star"]');
      await expect(stars.first()).toBeVisible({ timeout: 15000 });
      const count = await stars.count();
      expect(count, "seeded feed renders many favorite stars").toBeGreaterThanOrEqual(5);

      const labels = await stars.evaluateAll((els) =>
        els.map((el) => el.getAttribute("aria-label"))
      );
      // Every name carries kind + record context, and no two visible stars
      // share an accessible name.
      for (const label of labels) {
        expect(label).toMatch(/^(Add|Remove) (generation|experiment) .+(to|from) favorites$/);
        expect(label).not.toMatch(/^Add to favorites$/);
        expect(label).not.toMatch(/^Remove from favorites$/);
      }
      expect(new Set(labels).size, `labels: ${labels.slice(0, 4).join(" | ")} …`).toBe(count);

      // Toggling flips the verb while keeping the record context stable.
      const first = stars.first();
      const before = await first.getAttribute("aria-label");
      await first.click();
      await expect(first).not.toHaveAttribute("aria-label", before, { timeout: 10000 });
      const after = await first.getAttribute("aria-label");
      if (before.startsWith("Add ")) {
        expect(after).toMatch(/^Remove /);
        expect(after.endsWith("from favorites")).toBe(true);
      } else {
        expect(after).toMatch(/^Add /);
        expect(after.endsWith("to favorites")).toBe(true);
      }
      // Context tail survives the flip.
      expect(after.length).toBeGreaterThan("Remove ".length + " from favorites".length);
      t.assertNoConsoleErrors();
    } finally {
      t.guard.dispose();
    }
  });

  test("D. generation detail: keyboard open focuses inside dialog; Escape restores invoker", async ({
    page,
  }) => {
    const t = await setupFakeTest(page);
    try {
      await t.gotoPage("history");
      const card = page.locator('[data-testid="history-v2-generation-card"][data-id="gen_ok"]');
      await expect(card).toBeVisible({ timeout: 15000 });

      // Invoking element focused, then opened by KEYBOARD.
      await card.focus();
      expect(await page.evaluate(() => document.activeElement)).toBeTruthy();
      await page.keyboard.press("Enter");

      const overlay = page.locator(OVERLAY);
      await expect(overlay).toBeVisible({ timeout: 10000 });
      // Focus moved INSIDE the dialog (close button — first enabled control).
      const facts = await activeElementFacts(page, OVERLAY);
      expect(facts.insideOverlay, `activeElement: ${facts.tag}/${facts.ariaLabel}`).toBe(true);
      expect(facts.ariaLabel).toBe("Close");

      // Escape closes through the unchanged layer registry…
      await page.keyboard.press("Escape");
      await expect(overlay).toHaveCount(0, { timeout: 10000 });
      // …and focus is restored to the exact invoking card.
      const restored = await page.evaluate(() => {
        const c = document.querySelector(
          '[data-testid="history-v2-generation-card"][data-id="gen_ok"]'
        );
        return document.activeElement === c;
      });
      expect(restored, "focus must return to the invoking card").toBe(true);
      t.assertNoConsoleErrors();
    } finally {
      t.guard.dispose();
    }
  });

  test("E. experiment detail: loading primitive, focus-in on swap, keyboard back anchor", async ({
    page,
  }) => {
    const t = await setupFakeTest(page);
    try {
      const releaseExp = await holdRequests(page, /\/comfymodal\/history-v2\/experiments\//);
      await t.gotoPage("history");

      const card = page.locator('[data-testid="history-v2-experiment-card"][data-id="exp_completed"]');
      await expect(card).toBeVisible({ timeout: 15000 });
      await card.focus();
      await page.keyboard.press("Enter");

      // Deterministic sub-page loading state uses the shared primitive.
      const expLoading = page.locator('[data-testid="history-v2-experiment-loading"]');
      await expect(expLoading).toBeVisible({ timeout: 10000 });
      await expect(expLoading).toHaveAttribute("role", "status");
      await expect(expLoading).toHaveAttribute("aria-live", "polite");
      await expect(expLoading.locator(".cm-loading-label")).toHaveText("Loading experiment…");

      releaseExp();
      await expect(page.locator('[data-testid="history-v2-experiment-page"]')).toBeVisible({
        timeout: 15000,
      });
      // Page-swap focus analog of the dialog fix: focus lands on the first
      // enabled control — Back to history.
      await expect(page.locator(".comfymodal-studio-history-v2-back")).toBeFocused();

      // Keyboard activation of Back rebuilds the feed and leaves a
      // deterministic focus anchor instead of dropping focus to <body>.
      await page.keyboard.press("Enter");
      await expect(
        page.locator('[data-testid="history-v2-generation-card"]').first()
      ).toBeVisible({ timeout: 15000 });
      await expect(page.locator('[data-testid="history-v2-search"]')).toBeFocused();
      t.assertNoConsoleErrors();
    } finally {
      t.guard.dispose();
    }
  });

  test("F. retirement guard: sanctioned Compare entry only — no retired Comparison product", async ({
    page,
  }) => {
    const t = await setupFakeTest(page);
    try {
      await t.gotoPage("history");
      const card = page.locator('[data-testid="history-v2-generation-card"][data-id="gen_ok"]');
      await expect(card).toBeVisible({ timeout: 15000 });
      await card.click();
      const overlay = page.locator(OVERLAY);
      await expect(overlay).toBeVisible({ timeout: 10000 });

      // The ONLY compare surface is the lightweight I5 entry: exactly one
      // plain Compare action in the detail, no retired-product vocabulary.
      await expect(overlay.locator('[data-testid="history-v2-compare"]')).toHaveCount(1);
      const bodyText = await page.evaluate(() => document.body.innerText);
      for (const retired of ["Comparison Profiles", "Comparison Runner", "/comparison/run"]) {
        expect(bodyText.includes(retired), `retired vocabulary must stay absent: ${retired}`).toBe(false);
      }
      expect(await page.evaluate(() => document.querySelectorAll("[class*='comparison-profile'], [class*='ab-slider'], [class*='comparison-runner']").length)).toBe(0);

      // The generic compare module exists now; the retired A/B module does not.
      const importProbe = await page.evaluate(async () => {
        const live = await import("/extensions/comfymodal-modal/studio-image-compare.js")
          .then(() => true)
          .catch(() => false);
        const retiredModule = await import("/extensions/comfymodal-modal/testing-dashboard/ab-slider.js")
          .then(() => false)
          .catch(() => true);
        return { live, retiredModule };
      });
      expect(importProbe.live).toBe(true);
      expect(importProbe.retiredModule).toBe(true);
      // The two deliberate probes above 404; allowlist that expected noise.
      t.assertNoConsoleErrors(["Failed to load resource.*404"]);
    } finally {
      t.guard.dispose();
    }
  });
});
