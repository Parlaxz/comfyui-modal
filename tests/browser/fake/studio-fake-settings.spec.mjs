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
import { setupFakeTest } from "./helpers.mjs";

test.describe("Studio Settings (fake backend)", () => {
  test("16. deploy status renders the fake ready state", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("settings");
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
      const tracing2 = page.locator('[data-testid="settings-heavy-tracing"]');
      await expect(tracing2).toHaveValue("summary", { timeout: 10000 });
      await expect(page.locator('[data-testid="settings-restart-banner"]')).toBeHidden();
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });
});
