// Phase I9A — I5 × I9 convergence (fake E2E, permanent).
//
// Convergence-specific behavioral proof that the A/B image compare (I5) and
// the hash-routing authority (I9) coexist without interference:
//   K. deep-link into a History generation → compare interactions leave the
//      canonical route untouched → closing Compare leaves the detail valid →
//      closing the detail clears the stale focus identity from the URL
//      (I9A shell-owned clearRouteFocus) → Back/Forward stay deterministic →
//      a routed page swap auto-closes the body-level detail overlay →
//      leaving History tears the compare session down → returning never
//      resurrects stale compare state
//   L. after a focused detail is closed, cached modal reopen and reload-
//      reopen honor the CLEARED route (no dismissed-record resurrection)
//      while fresh deep links keep working (I9 spec E contract)
//   M. Settings `focus=outputs` routes truthfully; the section-level focus
//      miss is the documented I7-owned limitation deferred by I9A (see
//      PHASE_I9A report §Settings) — this test pins the routing-side
//      fail-soft contract only.
//
import { test, expect } from "@playwright/test";
import { createSession, installConsoleGuard } from "./helpers.mjs";

const NAV = 'nav[aria-label="Studio pages"].comfymodal-studio-topnav';
const OVERLAY = '.comfymodal-studio-history-v2-overlay[aria-label="Generation detail"]';

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

async function openViaTestingModal(page, sessionId, hash) {
  await page.goto(`/?session=${encodeURIComponent(sessionId)}${hash}`, {
    waitUntil: "domcontentloaded",
  });
  await page.waitForFunction(
    () => typeof window.__mountStudioForTest === "function",
    null,
    { timeout: 15000 }
  );
  await page.evaluate(async () => {
    const mod = await import("/extensions/comfymodal-modal/modal-testing.js");
    window.__i9aModal = mod;
    mod.open_testing_modal();
  });
  await expect(page.locator(".comfymodal-studio-modal[role='dialog']")).toBeVisible();
}

async function hashOf(page) {
  return page.evaluate(() => window.location.hash);
}

async function soleCurrentIs(page, pageId) {
  const currents = await page.evaluate(() =>
    Array.from(
      document.querySelectorAll('.comfymodal-studio-topnav button[aria-current="page"]')
    ).map((b) => b.getAttribute("data-page"))
  );
  expect(currents).toEqual([pageId]);
}

test.describe("I9A I5 x I9 convergence", () => {
  test("K. deep link → compare → slider → close → URL truth → Back/Forward → teardown", async ({
    page,
  }) => {
    const sessionId = await createSession(page);
    const guard = installConsoleGuard(page);
    try {
      // 1. Route directly to a History generation.
      await openDirectShell(page, sessionId, "#comfymodal=history&focus=gen_ok");
      await expect(page.locator(OVERLAY)).toBeVisible({ timeout: 15000 });

      // 2. Open Compare (preselects A) and fill B from an output menu.
      await page.locator('[data-testid="history-v2-compare"]').click();
      await page
        .locator(OVERLAY)
        .locator(".comfymodal-studio-history-v2-menu-btn")
        .nth(0)
        .click();
      await page.locator('[data-testid="history-v2-output-add-to-compare-0"]').click();
      await expect(page.locator('[data-testid="cm-compare-tray-b"]')).toHaveText(/^B: Output 1/);

      // 3. URL routing remains canonical during all compare activity.
      expect(await hashOf(page)).toBe("#comfymodal=history&focus=gen_ok");

      // 4. Operate the slider.
      await page.locator('[data-testid="cm-compare-open"]').click();
      await expect(page.locator('[data-testid="cm-compare-overlay"]')).toBeVisible();
      const slider = page.locator('[data-testid="cm-compare-slider"]');
      await expect(slider).toBeFocused();
      await page.keyboard.press("ArrowRight");
      await expect(slider).toHaveAttribute("aria-valuenow", "55");
      expect(await hashOf(page)).toBe("#comfymodal=history&focus=gen_ok");

      // 5. Close Compare — session cleared…
      await page.keyboard.press("Escape");
      await expect(page.locator('[data-testid="cm-compare-overlay"]')).toHaveCount(0);
      await expect(page.locator('[data-testid="cm-compare-tray"]')).toHaveCount(0);

      // 6. …underlying History detail remains fully valid.
      await expect(
        page.locator(OVERLAY).locator(".comfymodal-studio-history-v2-run-line")
      ).toBeVisible();

      // Closing the focused detail drops the stale focus identity from the
      // URL through the shell authority (I9A): no resurrect-on-reopen lie.
      await page.keyboard.press("Escape");
      await expect(page.locator(OVERLAY)).toHaveCount(0);
      await expect.poll(() => hashOf(page)).toBe("#comfymodal=history");

      // 7. Back/Forward stay deterministic — and the cleared route no longer
      // resurrects the dismissed detail on Back.
      await page.locator(`${NAV} button[data-page="workflows"]`).click();
      await expect(page).toHaveURL(/#comfymodal=workflows$/);
      await page.goBack();
      await expect(page).toHaveURL(/#comfymodal=history$/);
      await expect(page.locator(OVERLAY)).toHaveCount(0);
      await soleCurrentIs(page, "history");
      await page.goForward();
      await expect(page).toHaveURL(/#comfymodal=workflows$/);

      // 8. Focused-entry semantics stay deterministic and the body-level
      // detail overlay can never outlive its page across routed swaps.
      // A fresh focus entry (user-editable URL) re-applies the record…
      await page.evaluate(() => {
        window.location.hash = "#comfymodal=history&focus=gen_ok";
      });
      await expect(page).toHaveURL(/#comfymodal=history&focus=gen_ok$/);
      await expect(page.locator(OVERLAY)).toBeVisible();
      // …Back off the focused entry lands on the previous (Workflows)
      // entry; the History page unmounts and the anchor contract
      // auto-closes the dialog instead of orphaning it.
      await page.goBack();
      await expect(page).toHaveURL(/#comfymodal=workflows$/);
      await expect(page.locator(OVERLAY)).toHaveCount(0);
      await soleCurrentIs(page, "workflows");
      // Forward re-applies the focused entry truthfully.
      await page.goForward();
      await expect(page).toHaveURL(/#comfymodal=history&focus=gen_ok$/);
      await expect(page.locator(OVERLAY)).toBeVisible();
      // A routed swap to ANOTHER page while the dialog is open tears the
      // stale overlay down instead of leaving it over the new page.
      await page.evaluate(() => {
        window.location.hash = "#comfymodal=workflows";
      });
      await expect(page).toHaveURL(/#comfymodal=workflows$/);
      await expect(page.locator(OVERLAY)).toHaveCount(0);
      await soleCurrentIs(page, "workflows");

      // 9. No Compare session survives leaving History (tray-only live
      // session — the module-entry path used by I5 spec G/J — so the nav
      // stays reachable while the session is active).
      await page.locator(`${NAV} button[data-page="history"]`).click();
      await expect(
        page.locator('[data-testid="history-v2-generation-card"]').first()
      ).toBeVisible({ timeout: 15000 });
      const assetUrl = await page
        .locator("img.comfymodal-studio-history-v2-thumb-img")
        .first()
        .getAttribute("src");
      await page.evaluate(async ({ url }) => {
        const m = await import("/extensions/comfymodal-modal/studio-image-compare.js");
        m.startCompare({ descriptor: { url, label: "Preview", kind: "preview" } });
      }, { url: assetUrl });
      await expect(page.locator('[data-testid="cm-compare-tray"]')).toBeVisible();
      await page.locator(`${NAV} button[data-page="workflows"]`).click();
      await expect(page).toHaveURL(/#comfymodal=workflows$/);
      await expect(page.locator('[data-testid="cm-compare-tray"]')).toHaveCount(0);
      await expect(page.locator('[data-testid="cm-compare-overlay"]')).toHaveCount(0);

      // 10. Returning to History does not resurrect stale compare state.
      await page.locator(`${NAV} button[data-page="history"]`).click();
      await expect(page.locator('[data-testid="history-v2-page"]').first()).toBeAttached();
      await expect(page.locator('[data-testid="cm-compare-tray"]')).toHaveCount(0);
      await expect(page.locator('[data-testid="cm-compare-overlay"]')).toHaveCount(0);
      guard.assertNoErrors();
    } finally {
      guard.dispose();
    }
  });

  test("L. cleared focus survives cached modal reopen and reload-reopen", async ({ page }) => {
    const sessionId = await createSession(page);
    const guard = installConsoleGuard(page);
    try {
      // Fresh deep link still opens the record (I9 E contract preserved).
      await openViaTestingModal(page, sessionId, "#comfymodal=history&focus=gen_ok");
      await expect(page.locator(OVERLAY)).toBeVisible({ timeout: 15000 });

      // User dismisses it: the route drops its focus identity.
      await page.keyboard.press("Escape");
      await expect(page.locator(OVERLAY)).toHaveCount(0);
      await expect.poll(() => hashOf(page)).toBe("#comfymodal=history");

      // Cached close/reopen: the dismissed record stays dismissed.
      await page.locator(".comfymodal-testing-close").first().click();
      await expect(page.locator(".comfymodal-studio-modal[role='dialog']")).toBeHidden();
      await page.evaluate(async () => {
        window.__i9aModal.open_testing_modal();
      });
      await expect(page.locator(".comfymodal-studio-modal[role='dialog']")).toBeVisible();
      await soleCurrentIs(page, "history");
      await expect(page.locator(OVERLAY)).toHaveCount(0);
      expect(await hashOf(page)).toBe("#comfymodal=history");

      // Reload then reopen: same truthful outcome.
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
      await expect(page.locator(OVERLAY)).toHaveCount(0);
      expect(await hashOf(page)).toBe("#comfymodal=history");
      guard.assertNoErrors();
    } finally {
      guard.dispose();
    }
  });

  test("M. settings focus=outputs routes truthfully; section-focus miss is the documented I7 deferral", async ({
    page,
  }) => {
    const sessionId = await createSession(page);
    const guard = installConsoleGuard(page);
    try {
      await openViaTestingModal(page, sessionId, "#comfymodal=settings&focus=outputs");
      await soleCurrentIs(page, "settings");
      await expect(page.locator('[data-testid="settings-page-title"]')).toBeAttached();
      expect(await hashOf(page)).toBe("#comfymodal=settings&focus=outputs");

      // The Outputs section wrapper exists and its preference rows populate
      // asynchronously. Known deferred limitation (I7-owned surface): the
      // mount-time search filter hides rowless sections and is not re-run
      // after population, so scrollIntoView cannot land on `outputs` until
      // an owning-lane fix re-runs the filter — routing itself fails soft
      // and shows no false state.
      const section = page.locator('[data-section="outputs"]');
      await expect(section).toBeAttached();
      await expect
        .poll(
          async () =>
            page.locator('[data-testid="settings-outputs-host"] > *').count(),
          { timeout: 10000, message: "outputs rows never populated" }
        )
        .toBeGreaterThan(0);
      guard.assertNoErrors();
    } finally {
      guard.dispose();
    }
  });
});
