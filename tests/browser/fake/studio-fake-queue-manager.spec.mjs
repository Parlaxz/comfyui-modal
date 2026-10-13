// Queue topbar / manager / toast / persistence / experiment-manager popup.
// Covers UI behavior testable without workflow shelf hydration.
import { test, expect } from "@playwright/test";
import { setupFakeTest, openStudio } from "./helpers.mjs";

test.describe("queue UI verification", () => {
  test("topbar tools, queue radio, manager, toast, persistence", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await expect(page.locator('[data-testid="control-panel"]')).toBeVisible({ timeout: 15000 });
      await expect(page.locator('[data-testid="workspace-topbar"]')).toBeVisible({ timeout: 15000 });

      // 7 tool rail buttons, radio behavior + submenus.
      for (const id of ["t2i", "i2i", "inpaint", "outpaint", "sketch", "postprocess", "upscale"]) {
        await expect(page.locator(`[data-testid="studio-tool-${id}"]`)).toBeVisible();
      }
      await page.locator('[data-testid="studio-tool-i2i"]').click();
      await expect(page.locator('[data-testid="studio-tool-i2i"]')).toHaveAttribute("aria-pressed", "true");
      await expect(page.locator('[data-testid="studio-tool-t2i"]')).toHaveAttribute("aria-pressed", "false");
      await expect(page.locator('[data-testid="tool-submenu-i2i"]')).toBeVisible();
      await page.locator('[data-testid="studio-tool-t2i"]').click();
      await expect(page.locator('[data-testid="bg-fill-btn"]')).toBeVisible();
      await expect(page.locator('[data-testid="bg-fill-picker"]')).toBeAttached();

      // Queue/experiment radio.
      const queueToggle = page.locator('[data-testid="queue-toggle"]');
      const expToggle = page.locator('[data-testid="experiment-toggle"]');
      await queueToggle.click();
      await expect(queueToggle).toHaveAttribute("aria-pressed", "true");
      await expect(expToggle).toHaveAttribute("aria-pressed", "false");
      await expect(page.locator('[data-testid="run-btn"]')).toContainText("Queue");
      await expect(page.locator('[data-testid="run-queue-btn"]')).toBeVisible();
      await expToggle.click();
      await expect(queueToggle).toHaveAttribute("aria-pressed", "false");
      await expect(expToggle).toHaveAttribute("aria-pressed", "true");
      await queueToggle.click();
      await expect(queueToggle).toHaveAttribute("aria-pressed", "true");

      // Split-button history dropdown (empty state).
      await page.locator('[data-testid="queue-history-btn"]').click();
      const menu = page.locator('[data-testid="queue-history-menu"]');
      await expect(menu).toBeVisible();
      await expect(menu).toContainText("No batches yet");
      await page.keyboard.press("Escape");
      await expect(menu).toBeHidden();

      // Enqueue 2, toast appears and persists.
      await page.locator('[data-testid="run-btn"]').click();
      await page.locator('[data-testid="run-btn"]').click();
      await expect(page.locator('[data-testid="run-queue-btn"]')).toContainText("(2)");
      const toast = page.locator('[data-testid="queue-toast"]');
      await expect(toast).toBeVisible({ timeout: 5000 });
      await expect(toast).toContainText("1.");
      await toast.locator('[data-testid="queue-toast-close"]').click();
      await expect(toast).toBeHidden();
      await page.locator('[data-testid="run-btn"]').click();
      await expect(page.locator('[data-testid="queue-toast"]')).toBeVisible({ timeout: 5000 });

      // Manager: queued rows, reorder, detail toggle, delete.
      await page.locator('[data-testid="queue-view-btn"]').click();
      const manager = page.locator('[data-testid="queue-viewer"]');
      await expect(manager).toBeVisible();
      await expect(manager.locator('[data-testid^="queued-item-q_"]')).toHaveCount(3);
      const firstLabel = await manager.locator('[data-testid^="queued-item-label-"]').first().textContent();
      // Move first item down.
      await manager.locator('[data-testid="queue-move-down"]').first().click();
      const newFirst = await manager.locator('[data-testid^="queued-item-label-"]').first().textContent();
      expect(newFirst).not.toBe(firstLabel);
      // Move it back up (now second).
      await manager.locator('[data-testid="queue-move-down"]').first().click();
      // Detail toggle.
      const labelBtn = manager.locator('[data-testid^="queued-item-label-"]').first();
      await labelBtn.click();
      await expect(manager.locator('[data-testid^="queued-item-detail-"]').first()).toBeVisible();
      // Delete one.
      await manager.locator('[data-testid="queue-delete-btn"]').first().click();
      await expect(manager.locator('[data-testid^="queued-item-q_"]')).toHaveCount(2);
      await manager.locator('[data-testid="queue-viewer-close"]').click();
      await expect(manager).toBeHidden();

      // Persistence across reload (re-mount; localStorage queue survives).
      await page.reload();
      await openStudio(page, fx.sessionId);
      await expect(page.locator('[data-testid="workspace-topbar"]')).toBeVisible({ timeout: 15000 });
      await expect(page.locator('[data-testid="run-queue-btn"]')).toContainText("(2)", { timeout: 10000 });

      // Experiment manager popup.
      await page.locator('[data-testid="experiment-toggle"]').click();
      await expect(page.locator('[data-testid="experiment-manager-open"]')).toBeVisible({ timeout: 10000 });
      await page.locator('[data-testid="experiment-manager-open"]').click();
      const expModal = page.locator('[data-testid="experiment-manager"]');
      await expect(expModal).toBeVisible({ timeout: 10000 });
      await expect(expModal.locator('[data-testid="experiment-v2-section"]')).toBeVisible();
      await expect(expModal.locator('[data-testid="experiment-manager-summary"]')).toBeVisible();
      await expect(expModal.locator('[data-testid="experiment-manager-progress"]')).toBeVisible();
      await expModal.locator('[data-testid="experiment-manager-close"]').click();
      await expect(expModal).toBeHidden();

      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });
});
