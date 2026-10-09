// Modal Studio — Settings tests against the deterministic fake backend.
//
// Settings (web/studio-settings.js) is a real Studio page backed by the fake
// engine's REST endpoints:
//   - refreshDeployStatus  (line ~848) GETs /comfymodal/deploy/status and
//     writes "state — message" into [data-testid="settings-deploy-state"].
//   - refreshProfileLevel  (line ~1088) GETs /comfymodal/profile/level for the
//     effective level; the Heavy tracing select ([data-testid=
//     "settings-heavy-tracing"]) POSTs {level} on change and rolls back on a
//     non-ok response.
//   - The restart banner ([data-testid="settings-restart-banner"]) shows when
//     localStorage "comfymodal_heavy_tracing" differs from the effective level.

import { test, expect } from "@playwright/test";
import {
  gotoPage,
  installConsoleGuard,
  openStudio,
  setupFakeTest,
} from "./helpers.mjs";

test.describe("Studio Settings (fake backend)", () => {
  test("16. deploy status renders the fake ready state", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("settings");
      await page.locator('#settings-tab-advanced').click();
      await expect(page.locator(".comfymodal-studio-settings")).toBeVisible({ timeout: 15000 });

      const deployState = page.locator('[data-testid="settings-deploy-state"]');
      await expect(deployState).toContainText("ready", { timeout: 10000 });
      await expect(deployState).toContainText("Fake deployment ready");
      await expect(deployState).not.toHaveText("Unknown");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("17. profile level control renders the server default (off)", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("settings");
      await page.locator('#settings-tab-advanced').click();
      await expect(page.locator(".comfymodal-studio-settings")).toBeVisible({ timeout: 15000 });

      const tracing = page.locator('[data-testid="settings-heavy-tracing"]');
      await expect(tracing).toBeVisible({ timeout: 10000 });
      await expect(tracing).toHaveValue("off");

      // The server agrees with the local default → no restart banner.
      await expect(page.locator('[data-testid="settings-restart-banner"]')).toBeHidden();
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("18. profile level mutation persists server-side and survives reload", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("settings");
      await page.locator('#settings-tab-advanced').click();
      const tracing = page.locator('[data-testid="settings-heavy-tracing"]');
      await expect(tracing).toBeVisible({ timeout: 10000 });

      await tracing.selectOption("summary");

      // Server-side persistence (per-session profile level).
      await expect
        .poll(async () => (await fx.getState()).profileLevel, {
          timeout: 10000,
          message: "profile level should be persisted server-side",
        })
        .toBe("summary");

      // Reload (same session): the control re-hydrates from localStorage and
      // the server still reports "summary" → consistent, no restart banner.
      await fx.reload();
      await fx.gotoPage("settings");
      await page.locator('#settings-tab-advanced').click();
      const tracing2 = page.locator('[data-testid="settings-heavy-tracing"]');
      await expect(tracing2).toHaveValue("summary", { timeout: 10000 });
      await expect(page.locator('[data-testid="settings-restart-banner"]')).toBeHidden();
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("19. five tabs expose the intended control groups", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("settings");
      const tabs = page.locator('.comfymodal-studio-settings-tabs [role="tab"]');
      await expect(tabs).toHaveText([
        "Generation",
        "Outputs",
        "Accounts & Tokens",
        "Interface",
        "Advanced",
      ]);
      await expect(page.locator('.comfymodal-studio-settings-section[data-section]')).toHaveCount(5);

      await expect(page.locator('[data-testid="settings-gpu"]')).toBeVisible();
      // The fake config deliberately has no GPU catalog and reports A10G.
      // An unmatched server value must fall back to a valid default rather
      // than becoming a blank select.
      await expect(page.locator('[data-testid="settings-gpu"]')).toHaveValue("rtx-pro-6000");
      await expect(page.locator('[data-testid="settings-golden-profile"]')).toBeVisible({ timeout: 10000 });

      await page.locator('#settings-tab-outputs').click();
      await expect(page.locator('[data-testid="settings-output-format"]')).toBeVisible({ timeout: 10000 });
      await expect(page.locator('[data-testid="settings-save-folder"]')).toBeVisible();

      await page.locator('#settings-tab-accounts').click();
      await expect(page.locator('[data-testid="backend-credentials"]')).toBeVisible();
      await expect(page.locator('[data-testid="backend-cred-hf-input"]')).toHaveAttribute("type", "password");

      await page.locator('#settings-tab-interface').click();
      await expect(page.locator('[data-testid="settings-history-columns"]')).toBeVisible();
      await expect(page.locator('[data-testid="settings-remote-inventory-refresh"]')).toBeVisible();

      await page.locator('#settings-tab-advanced').click();
      await expect(page.locator('[data-testid="settings-heavy-tracing"]')).toBeVisible();
      await expect(page.locator('[data-testid="settings-heavy-tracing"] option[value="trace_verbose"]')).toHaveText("Verbose trace");
      await expect(page.locator('[data-testid="settings-reset-all"]')).toBeVisible();
      await expect(page.locator('[data-testid="settings-open-workspaces"]')).toBeVisible();
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("20. Settings tabs support roving keyboard navigation and retain selection on sync", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const peer = await page.context().newPage();
    const peerGuard = installConsoleGuard(peer);
    try {
      await openStudio(peer, fx.sessionId);
      await fx.gotoPage("settings");
      await gotoPage(peer, "settings");

      const tabs = page.locator('.comfymodal-studio-settings-tabs [role="tab"]');
      await tabs.first().focus();
      await page.keyboard.press("End");
      await expect(page.locator('#settings-tab-advanced')).toHaveAttribute("aria-selected", "true");
      await expect(page.locator('[data-section="advanced"]')).toBeVisible();
      await page.keyboard.press("Home");
      await expect(page.locator('#settings-tab-generation')).toHaveAttribute("aria-selected", "true");
      await page.keyboard.press("ArrowRight");
      await expect(page.locator('#settings-tab-outputs')).toHaveAttribute("aria-selected", "true");

      await peer.locator('#settings-tab-interface').click();
      await expect(peer.locator('[data-section="interface"]')).toBeVisible();
      await page.locator('#settings-tab-advanced').click();
      await page.locator('[data-testid="settings-heavy-tracing"]').selectOption("detailed");
      await expect(peer.locator('#settings-tab-interface')).toHaveAttribute("aria-selected", "true", { timeout: 10000 });
      await expect(peer.locator('[data-section="interface"]')).toBeVisible();
      peerGuard.assertNoErrors();
      fx.assertNoConsoleErrors();
    } finally {
      peerGuard.dispose();
      await peer.close();
      fx.guard.dispose();
    }
  });

  test("21. search is global, empty-state is clearable, and clear restores the selected tab", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("settings");
      await page.locator('#settings-tab-interface').click();
      const search = page.locator('[data-testid="settings-search"]');
      const results = page.locator('[data-testid="settings-search-results"]');

      await search.fill("history");
      await expect(results).toContainText("Interface");
      await expect(page.locator('[data-section="interface"]')).toBeVisible();
      await expect(page.locator('[data-section="generation"]')).toBeHidden();

      await search.fill("no-such-settings-value");
      await expect(results).toHaveText("No settings match your search");
      await expect(page.locator('[data-section="interface"]')).toBeHidden();

      await page.locator('.comfymodal-settings-search-clear').click();
      await expect(search).toHaveValue("");
      await expect(results).toBeHidden();
      await expect(page.locator('#settings-tab-interface')).toHaveAttribute("aria-selected", "true");
      await expect(page.locator('[data-section="interface"]')).toBeVisible();
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("22. tab click and keyboard navigation during search clear search and show the category", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("settings");
      const search = page.locator('[data-testid="settings-search"]');
      await search.fill("history");
      await expect(page.locator('[data-section="interface"]')).toBeVisible();

      // Intended navigation behavior: selecting a category exits global search
      // and shows the complete category, rather than exposing an empty panel
      // with a stale result summary.
      await page.locator('#settings-tab-outputs').click();
      await expect(search).toHaveValue("");
      await expect(page.locator('[data-testid="settings-search-results"]')).toBeHidden();
      await expect(page.locator('[data-section="outputs"]')).toBeVisible();
      await expect(page.locator('[data-section="interface"]')).toBeHidden();
      await expect(page.locator('[data-testid="settings-output-format"]')).toBeVisible({ timeout: 10000 });

      // The same contract applies to roving keyboard navigation.
      await page.locator('#settings-tab-interface').click();
      await search.fill("history");
      await page.locator('#settings-tab-interface').focus();
      await page.keyboard.press("ArrowRight");
      await expect(search).toHaveValue("");
      await expect(page.locator('#settings-tab-advanced')).toHaveAttribute("aria-selected", "true");
      await expect(page.locator('[data-section="advanced"]')).toBeVisible();
    } finally {
      fx.guard.dispose();
    }
  });

  test("23. preferences persist and reset preserves user data", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("settings");
      await page.locator('#settings-tab-interface').click();
      const inventory = page.locator('[data-testid="settings-remote-inventory-refresh"]');
      await inventory.selectOption("60");
      await expect.poll(() => page.evaluate(() => localStorage.getItem("comfymodal_remote_inventory_refresh_interval_s"))).toBe("60");

      await fx.reload();
      await fx.gotoPage("settings");
      await page.locator('#settings-tab-interface').click();
      await expect(page.locator('[data-testid="settings-remote-inventory-refresh"]')).toHaveValue("60");

      await page.evaluate(() => {
        localStorage.setItem("comfymodal_gpu", "seeded-gpu");
        localStorage.setItem("comfymodal.studio.playground.drafts.v1", "user-draft");
      });
      await page.locator('#settings-tab-advanced').click();
      page.once("dialog", (dialog) => dialog.accept());
      await page.locator('[data-testid="settings-reset-all"]').click();
      await expect.poll(() => page.evaluate(() => localStorage.getItem("comfymodal_gpu"))).toBeNull();
      await expect.poll(() => page.evaluate(() => localStorage.getItem("comfymodal_remote_inventory_refresh_interval_s"))).toBeNull();
      expect(await page.evaluate(() => localStorage.getItem("comfymodal.studio.playground.drafts.v1"))).toBe("user-draft");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("24. Generation reset posts the accepted Golden null sentinel", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const configPosts = [];
    page.on("request", (request) => {
      if (request.method() === "POST" && /\/comfymodal\/config$/.test(request.url())) {
        configPosts.push(request.postDataJSON());
      }
    });
    try {
      await fx.gotoPage("settings");
      page.once("dialog", (dialog) => dialog.accept());
      await page.locator('[data-testid="settings-reset-generation"]').click();
      await expect.poll(() => configPosts.some((body) => body && body.golden_profile === null), { timeout: 10000 }).toBe(true);
      expect(configPosts.find((body) => body && body.golden_profile === null)).toEqual({ golden_profile: null });
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("25. settings deep-link focus aliases land on their owning tabs", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("settings");
      for (const [focus, expectedTab] of [
        ["history", "interface"],
        ["profiles", "generation"],
        ["accounts", "accounts"],
        ["credentials", "accounts"],
        ["tokens", "accounts"],
      ]) {
        await page.evaluate((value) => {
          window.location.hash = `#comfymodal=settings&focus=${value}`;
        }, focus);
        await expect(page.locator(`#settings-tab-${expectedTab}`)).toHaveAttribute("aria-selected", "true", { timeout: 5000 });
        await expect(page.locator(`[data-section="${expectedTab}"]`)).toBeVisible();
      }
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });
});
