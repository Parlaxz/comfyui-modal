// Phase I10 - permanent same-origin cross-tab invalidation coverage.
//
// Each test uses two real pages in one browser context. The producer changes
// server state through the normal UI; the peer page must re-read that state.

import { test, expect } from "@playwright/test";
import {
  gotoPage,
  installConsoleGuard,
  openStudio,
  setupFakeTest,
} from "./helpers.mjs";

async function secondTab(page, sessionId) {
  const peer = await page.context().newPage();
  const guard = installConsoleGuard(peer);
  await openStudio(peer, sessionId);
  return { peer, guard };
}

test.describe("I10 cross-tab invalidation and refetch", () => {
  test("settings changes refetch in a second tab", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const { peer, guard } = await secondTab(page, fx.sessionId);
    try {
      await fx.gotoPage("settings");
      await gotoPage(peer, "settings");
      const level = page.locator('[data-testid="settings-heavy-tracing"]');
      const peerLevel = peer.locator('[data-testid="settings-heavy-tracing"]');
      await expect(level).toBeVisible();
      await expect(peerLevel).toBeVisible();
      await level.selectOption("detailed");
      await expect(peerLevel).toHaveValue("detailed", { timeout: 10000 });
      guard.assertNoErrors();
      fx.assertNoConsoleErrors();
    } finally {
      guard.dispose();
      await peer.close();
      fx.guard.dispose();
    }
  });

  test("Backend workspace changes refetch in a second tab", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const { peer, guard } = await secondTab(page, fx.sessionId);
    try {
      await fx.gotoPage("backend");
      await gotoPage(peer, "backend");
      await page.locator('[data-tab="workspaces"]').click();
      await peer.locator('[data-tab="workspaces"]').click();
      await expect(page.locator('[data-testid="backend-workspaces"]')).toBeVisible();
      await page.locator('[data-testid="backend-workspace-add"]').click();
      const form = page.locator('[data-testid="backend-workspace-form"]');
      await form.locator("input").nth(0).fill("Peer Workspace");
      await form.locator("input").nth(1).fill("ak-fake");
      await form.locator("input").nth(2).fill("as-fake");
      await form.locator('[data-testid="backend-workspace-save"]').click();
      await expect(peer.locator('[data-testid="backend-workspace-card"]')).toHaveCount(2, { timeout: 10000 });
      await expect(peer.locator('[data-testid="backend-workspaces-list"]')).toContainText("Peer Workspace");
      guard.assertNoErrors();
      fx.assertNoConsoleErrors();
    } finally {
      guard.dispose();
      await peer.close();
      fx.guard.dispose();
    }
  });

  test("History V2 annotation changes refetch in a second tab", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const { peer, guard } = await secondTab(page, fx.sessionId);
    try {
      await fx.gotoPage("history");
      await gotoPage(peer, "history");
      const star = page.locator('[data-testid="history-v2-favorite-star"]').first();
      const peerStar = peer.locator('[data-testid="history-v2-favorite-star"]').first();
      await expect(star).toBeVisible({ timeout: 15000 });
      await expect(peerStar).toHaveAttribute("aria-pressed", "false");
      await star.click();
      await expect(peerStar).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
      guard.assertNoErrors();
      fx.assertNoConsoleErrors();
    } finally {
      guard.dispose();
      await peer.close();
      fx.guard.dispose();
    }
  });

  test("Workflows changes refetch in a second tab", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const { peer, guard } = await secondTab(page, fx.sessionId);
    try {
      await fx.gotoPage("workflows");
      await gotoPage(peer, "workflows");
      const star = page.locator('[data-testid="workflow-card"]').nth(1).locator("button").first();
      const peerStar = peer.locator('[data-testid="workflow-card"]').nth(1).locator("button").first();
      await expect(star).toBeVisible({ timeout: 15000 });
      await expect(peerStar).toHaveAttribute("aria-pressed", "false");
      await star.click();
      await expect.poll(async () => page.evaluate(async () => {
        const response = await fetch("/comfymodal/studio/workflows");
        const body = await response.json();
        return body.workflows && body.workflows[1] && body.workflows[1].favorite === true;
      })).toBe(true);
      await expect(peerStar).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
      guard.assertNoErrors();
      fx.assertNoConsoleErrors();
    } finally {
      guard.dispose();
      await peer.close();
      fx.guard.dispose();
    }
  });
});
