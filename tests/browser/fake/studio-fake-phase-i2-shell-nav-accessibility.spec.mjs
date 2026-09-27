// Phase I2 — Shell navigation accessibility & responsive safety (fake E2E).
//
// Permanent product coverage for the frozen I2 contract:
//   - semantic labelled <nav> ("Studio pages") with exactly five native
//     button page selectors in canonical order
//   - aria-current="page" tracks the single shell page-state authority
//     (click AND programmatic changes), never left stale on inactive pages
//   - keyboard-only operation (Tab / Shift+Tab traversal, Enter and Space
//     activation, visible :focus-visible indication)
//   - shell dialog regression: focus-in on open, Escape closes, focus
//     restored to the invoking control, background made inert
//   - exactly one shell h1 "Modal GPU"
//   - responsive safety: no document-level horizontal overflow at
//     1440/768/480; at 360 every page stays keyboard-reachable through the
//     nav's horizontal-scroll valve

import { test, expect } from "@playwright/test";
import {
  setupFakeTest,
  createSession,
  installConsoleGuard,
} from "./helpers.mjs";

const PAGE_ORDER = ["playground", "history", "workflows", "backend", "settings"];
const PAGE_LABELS = ["Playground", "History", "Workflows", "Backend", "Settings"];

const NAV = 'nav[aria-label="Studio pages"].comfymodal-studio-topnav';
const NAV_BUTTONS = `${NAV} button[data-page]`;

async function currentPages(page) {
  return page.evaluate(() => {
    return Array.from(
      document.querySelectorAll(
        '.comfymodal-studio-topnav button[aria-current="page"]'
      )
    ).map((b) => b.getAttribute("data-page"));
  });
}

async function expectSoleCurrent(page, pageId) {
  const currents = await currentPages(page);
  expect(currents).toEqual([pageId]);
  const stale = await page.evaluate(
    (id) =>
      Array.from(document.querySelectorAll(".comfymodal-studio-topnav button"))
        .filter((b) => b.getAttribute("data-page") !== id && b.hasAttribute("aria-current"))
        .length,
    pageId
  );
  expect(stale).toBe(0);
}

test.describe("I2 shell nav accessibility", () => {
  test("semantic labelled nav with five native buttons in canonical order", async ({
    page,
  }) => {
    await setupFakeTest(page);

    const nav = page.locator(NAV);
    await expect(nav).toBeVisible();
    await expect(nav).toHaveAttribute("aria-label", "Studio pages");

    const buttons = page.locator(NAV_BUTTONS);
    await expect(buttons).toHaveCount(5);
    await expect(buttons).toHaveText(PAGE_LABELS);

    const dataPages = await page.evaluate(() =>
      Array.from(document.querySelectorAll(".comfymodal-studio-topnav button")).map(
        (b) => b.getAttribute("data-page")
      )
    );
    expect(dataPages).toEqual(PAGE_ORDER);

    // Native button semantics: no role/tabindex overrides, no tablist widget.
    const overrides = await page.evaluate(() =>
      Array.from(document.querySelectorAll(".comfymodal-studio-topnav button")).filter(
        (b) => b.tagName !== "BUTTON" || b.hasAttribute("role") || b.hasAttribute("tabindex")
      ).length
    );
    expect(overrides).toBe(0);
    expect(await page.locator('[role="tablist"]').count()).toBe(0);

    // No hamburger / second navigation architecture.
    expect(await page.locator("nav").count()).toBe(1);
  });

  test("aria-current tracks the active page for click and programmatic changes", async ({
    page,
  }) => {
    const t = await setupFakeTest(page);

    await expectSoleCurrent(page, "playground");
    await expect(page.locator(`${NAV} button[data-page="playground"]`)).toHaveClass(
      /active/
    );

    // Click activation: History becomes the sole current page.
    await page.locator(`${NAV} button[data-page="history"]`).click();
    await expectSoleCurrent(page, "history");
    await expect(
      page.locator(`${NAV} button[data-page="playground"]`)
    ).not.toHaveAttribute("aria-current");

    // Programmatic change through the shell API (the same authority alias
    // navigation uses): Workflows becomes sole current page.
    await page.evaluate(() => window.__studioApi.setPage("workflows"));
    await expectSoleCurrent(page, "workflows");

    // And once more via another page (Backend).
    await t.gotoPage("backend");
    await expectSoleCurrent(page, "backend");
  });

  test("keyboard-only operation reaches and activates every page", async ({
    page,
  }) => {
    await setupFakeTest(page);

    // Tab from page start until focus lands inside the top nav.
    let reached = false;
    let focusedPage = null;
    for (let i = 0; i < 12 && !reached; i++) {
      await page.keyboard.press("Tab");
      reached = await page.evaluate(() => {
        const el = document.activeElement;
        return !!el && !!el.closest(".comfymodal-studio-topnav");
      });
    }
    expect(reached, "Tab must reach the top-level navigation").toBe(true);
    focusedPage = await page.evaluate(() =>
      document.activeElement.getAttribute("data-page")
    );
    expect(focusedPage).toBe("playground");

    // Visible keyboard focus indication (:focus-visible ring).
    const outline = await page.evaluate(() => {
      const cs = getComputedStyle(document.activeElement);
      return { width: cs.outlineWidth, style: cs.outlineStyle };
    });
    expect(outline.width).toBe("2px");
    expect(outline.style).not.toBe("none");

    // Enter activates the focused control (Playground → next tab stop History).
    await page.keyboard.press("Tab");
    focusedPage = await page.evaluate(() =>
      document.activeElement.getAttribute("data-page")
    );
    expect(focusedPage).toBe("history");
    await page.keyboard.press("Enter");
    await expectSoleCurrent(page, "history");

    // Shift+Tab back to Playground, Space activates it.
    await page.keyboard.press("Shift+Tab");
    focusedPage = await page.evaluate(() =>
      document.activeElement.getAttribute("data-page")
    );
    expect(focusedPage).toBe("playground");
    await page.keyboard.press(" ");
    await expectSoleCurrent(page, "playground");

    // Walk forward with Tab to Settings and activate with Space — every page
    // stays keyboard-operable without any pointer interaction.
    for (let i = 0; i < 4; i++) await page.keyboard.press("Tab");
    focusedPage = await page.evaluate(() =>
      document.activeElement.getAttribute("data-page")
    );
    expect(focusedPage).toBe("settings");
    await page.keyboard.press("Enter");
    await expectSoleCurrent(page, "settings");
    await expect(page.locator('[data-testid="studio-page"]')).toBeVisible();
  });

  test("shell dialog: focus-in, Escape close, focus restore, single h1", async ({
    page,
  }) => {
    const sessionId = await createSession(page);
    const guard = installConsoleGuard(page);
    await page.goto(`/?session=${encodeURIComponent(sessionId)}`, {
      waitUntil: "domcontentloaded",
    });
    await page.waitForFunction(
      () => typeof window.__mountStudioForTest === "function",
      null,
      { timeout: 15000 }
    );

    // Simulate the invoking launcher (sidebar/fallback equivalent), then open
    // Studio through the REAL modal-testing.js entry point.
    await page.evaluate(async () => {
      const mod = await import("/extensions/comfymodal-modal/modal-testing.js");
      const wrapper = document.createElement("div");
      const launcher = document.createElement("button");
      launcher.textContent = "Open Studio";
      launcher.id = "i2-invoker";
      wrapper.appendChild(launcher);
      document.body.appendChild(wrapper);
      launcher.focus();
      window.__i2Invoker = launcher;
      window.__i2Wrapper = wrapper;
      mod.open_testing_modal();
    });

    const dialog = page.locator(".comfymodal-studio-modal[role='dialog']");
    await expect(dialog).toBeVisible();
    await expect(dialog).toHaveAttribute("aria-modal", "true");
    await expect(dialog).toHaveAttribute(
      "aria-labelledby",
      "comfymodal-studio-heading"
    );

    // Focus moved inside the dialog on open.
    const focusInside = await page.evaluate(() => {
      const el = document.activeElement;
      return !!el && !!el.closest(".comfymodal-studio-modal");
    });
    expect(focusInside).toBe(true);

    // Exactly one shell h1 "Modal GPU"; the accessible name comes from it.
    await expect(dialog.locator("h1#comfymodal-studio-heading")).toHaveCount(1);
    await expect(dialog.locator("h1#comfymodal-studio-heading")).toHaveText(
      "Modal GPU"
    );

    // Background is inert while open.
    const inertWhileOpen = await page.evaluate(
      () => window.__i2Wrapper.hasAttribute("inert") &&
        window.__i2Wrapper.getAttribute("aria-hidden") === "true"
    );
    expect(inertWhileOpen).toBe(true);

    // Escape closes; focus returns to the invoking launcher; inert removed.
    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible();
    const restored = await page.evaluate(() => ({
      focusOnInvoker: document.activeElement === window.__i2Invoker,
      inertCleared: !window.__i2Wrapper.hasAttribute("inert"),
      ariaHiddenCleared: !window.__i2Wrapper.hasAttribute("aria-hidden"),
    }));
    expect(restored.focusOnInvoker).toBe(true);
    expect(restored.inertCleared).toBe(true);
    expect(restored.ariaHiddenCleared).toBe(true);
    guard.dispose();
  });

  test("responsive sweep: nav reachable at 360, no document overflow at 480+", async ({
    page,
  }) => {
    await setupFakeTest(page);

    const widths = [1440, 768, 480, 360];
    /** @type {Array<Record<string, unknown>>} */
    const matrix = [];

    for (const width of widths) {
      await page.setViewportSize({ width, height: 900 });
      await expect(page.locator(NAV)).toBeVisible();

      const m = await page.evaluate(() => {
        const se = document.scrollingElement;
        const nav = document.querySelector(".comfymodal-studio-topnav");
        const last = nav.querySelector('button[data-page="settings"]');
        return {
          width: window.innerWidth,
          docScrollWidth: se.scrollWidth,
          docClientWidth: se.clientWidth,
          navScrollWidth: nav.scrollWidth,
          navClientWidth: nav.clientWidth,
          navOverflowX: getComputedStyle(nav).overflowX,
          lastBtnInViewport:
            last.getBoundingClientRect().left >= 0 &&
            last.getBoundingClientRect().right <= window.innerWidth + 1,
        };
      });
      m.docOverflowPx = m.docScrollWidth - m.docClientWidth;
      m.navOverflowPx = m.navScrollWidth - m.navClientWidth;
      matrix.push(m);

      expect(m.docOverflowPx).toBe(0);

      // Last page remains keyboard-reachable and activatable at every width.
      await page.evaluate(() => {
        document
          .querySelector('.comfymodal-studio-topnav button[data-page="settings"]')
          .focus();
      });
      await page.keyboard.press("Enter");
      await expectSoleCurrent(page, "settings");
      await expect(page.locator('[data-testid="studio-page"]')).toBeVisible();
    }

    // At 360 the nav itself must permit horizontal scrolling (valve), and the
    // five controls stay reachable (proven above by activating the last one).
    const narrow = matrix[matrix.length - 1];
    expect(narrow.width).toBe(360);
    expect(narrow.navOverflowX).toBe("auto");

    console.log("I2 responsive sweep:");
    for (const m of matrix) {
      console.log(
        `  ${m.width}px  docOverflow=${m.docOverflowPx}px  nav ${m.navClientWidth}/${m.navScrollWidth}px (overflow=${m.navOverflowPx}px, overflow-x=${m.navOverflowX})  settingsReachable=yes`
      );
    }
  });
});
