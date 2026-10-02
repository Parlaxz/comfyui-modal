// Phase I7 — Backend & Settings accessibility, loading and copy polish (fake E2E).
//
// Permanent product coverage for the I7 contract:
//   A. truthful accessible page h2 "Backend" / "Settings" under the shell h1
//      (visually hidden via the clip pattern — never display:none /
//      visibility:hidden); no card title was promoted into a heading
//   B. the three Backend loading sites (presets / snapshots / workspaces) use
//      the shared I3 loading primitive: role="status", aria-live="polite",
//      decorative spinner, truthful labels — fetches, readiness state,
//      deployment state, empty/error distinctions untouched
//   C. every visible Settings reset control has a pairwise-unique
//     section-identifying accessible name (no bare "Reset section" family)
//   D. the frozen I1 §3.6 wording rows render verbatim (five-page navigation
//      list incl. Backend; run-history retention; experiment concurrency 6)
//   E. Backend tab navigation stays keyboard operable and exposes a truthful
//      selection state (aria-current on the active view-switcher button)
//   F. status badges inherit the shared cm-chip base automatically and FILTER
//      feature chips adopt cm-chip geometry while keeping aria-pressed
//   G. no retired Settings control reappears and no /studio/backends fetch
//      is issued by Settings (H16 FD-8 stays closed)
//
// The fake engine does not implement the H6 operational routes (/workspaces,
// /auth/status, /health), so tests that reach the operational Backend surface
// mock them at the route level with truthful payloads — no live/GPU/deploy.

import { test, expect } from "@playwright/test";
import { setupFakeTest } from "./helpers.mjs";

function workspaceRegistry() {
  return {
    status: "ok",
    active_workspace_id: "ws_1",
    workspaces: [
      {
        id: "ws_1",
        label: "Studio A",
        token_id_masked: "ak-aaaa\u2026zzzz",
        token_secret_masked: "as-bbbb\u2026yyyy",
        last_used_at: 1730000000,
        last_deploy_status: "ready",
        notes: "",
      },
      {
        id: "ws_2",
        label: "Studio B",
        token_id_masked: "ak-cccc\u2026xxxx",
        token_secret_masked: "as-dddd\u2026wwww",
        last_used_at: null,
        last_deploy_status: "idle",
        notes: "",
      },
    ],
  };
}

/**
 * Mock the three operational GET probes the fake engine does not implement.
 * Installed AFTER the Studio mount so Playground's own fetches are never
 * intercepted; only Backend-page surfaces consume these.
 */
async function mockBackendOpsRoutes(page) {
  await page.route(/\/comfymodal\/workspaces(\?.*)?$/, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(workspaceRegistry()),
    }),
  );
  await page.route(/\/comfymodal\/auth\/status$/, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ connected: true }),
    }),
  );
  await page.route(/\/comfymodal\/health\?mode=deploy$/, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "ok" }),
    }),
  );
}

/**
 * Hold EVERY matching request until release() is called, then either proxy it
 * to the real (fake-server) endpoint or — when `fulfillBody` is given —
 * fulfill deterministically (used where the fake engine has no endpoint).
 * Same lifecycle discipline as the I4 helper: register before the triggering
 * navigation/click, never unroute while held.
 */
async function holdThenProxy(page, pattern, fulfillBody = null) {
  let releaseFn = null;
  let released = false;
  const gate = new Promise((resolve) => { releaseFn = resolve; });
  await page.route(pattern, async (route) => {
    if (!released) await gate;
    if (fulfillBody !== null) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(fulfillBody),
      });
      return;
    }
    const response = await route.fetch();
    await route.fulfill({ response });
  });
  return () => {
    released = true;
    if (releaseFn) releaseFn();
  };
}

async function expectOffscreenHeading(page, testid, text) {
  const h2 = page.locator(`[data-testid="${testid}"]`);
  await expect(h2).toHaveCount(1);
  await expect(h2).toHaveText(text);
  const style = await h2.evaluate((el) => {
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
  // Accessible-but-visually-hidden: clip pattern, never display:none /
  // visibility:hidden / [hidden].
  expect(style.display).not.toBe("none");
  expect(style.visibility).not.toBe("hidden");
  expect(style.hiddenAttr).toBe(false);
  expect(style.clip).toContain("rect(");
  expect(style.width).toBeLessThanOrEqual(2);
  expect(style.height).toBeLessThanOrEqual(2);
  return h2;
}

test.describe("I7 Backend & Settings accessibility/loading/copy polish", () => {
  test("A. truthful page h2 on Backend and Settings; hierarchy unchanged", async ({
    page,
  }) => {
    const t = await setupFakeTest(page);
    try {
      await mockBackendOpsRoutes(page);
      await t.gotoPage("backend");

      // Backend: exactly one heading in the default (Overview) view — the
      // visually-hidden page h2. No card/section title became a heading.
      const backendH2 = await expectOffscreenHeading(page, "backend-page-title", "Backend");
      await expect(backendH2).toHaveClass(/comfymodal-studio-backend-page-title/);
      const backendCensus = await page.evaluate(() =>
        Array.from(document.querySelectorAll("h1,h2,h3,h4,h5,h6")).map((h) => h.tagName),
      );
      expect(backendCensus).toEqual(["H2"]);

      // Settings: sole h2 is the page title; the seven sections stay h3 and
      // the Runtime & Backend group stays h4 (frozen hierarchy).
      await t.gotoPage("settings");
      await expectOffscreenHeading(page, "settings-page-title", "Settings");
      const settingsCensus = await page.evaluate(() => {
        const hs = Array.from(document.querySelectorAll("h1,h2,h3,h4,h5,h6"));
        return {
          tags: hs.map((h) => h.tagName),
          texts: hs.map((h) => h.textContent.trim()),
        };
      });
      expect(settingsCensus.tags.filter((tag) => tag === "H2")).toEqual(["H2"]);
      expect(settingsCensus.tags.filter((tag) => tag === "H3").length).toBe(7);
      expect(settingsCensus.tags.filter((tag) => tag === "H4")).toEqual(["H4"]);
      expect(settingsCensus.texts).not.toContain("Backend");
      t.assertNoConsoleErrors();
    } finally {
      t.guard.dispose();
    }
  });

  test("B. Backend presets/snapshots/workspaces loading states use the shared primitive", async ({
    page,
  }) => {
    const t = await setupFakeTest(page);
    try {
      // Mocks first, gates second: later-registered routes win, so the gates
      // below must shadow the ops mocks they overlap with (/workspaces).
      // Gates installed after mount: Playground's own initial fetches are
      // already done; these hold the Backend-page requests only.
      await mockBackendOpsRoutes(page);
      const releasePresets = await holdThenProxy(page, /\/comfymodal\/studio\/presets$/);
      const releaseSnapshots = await holdThenProxy(page, /\/comfymodal\/studio\/snapshots$/);
      // The fake engine has no /workspaces endpoint — the gate fulfills the
      // registry envelope itself (server-truth shape, mocked transport).
      const releaseWorkspaces = await holdThenProxy(
        page,
        /\/comfymodal\/workspaces$/,
        workspaceRegistry(),
      );

      await t.gotoPage("backend");

      // ── Backend Presets ──
      await page.locator('.comfymodal-studio-backend-tab[data-tab="presets"]').click();
      const presetsLoading = page.locator('[data-testid="backend-presets-loading"]');
      await expect(presetsLoading).toBeVisible({ timeout: 10000 });
      await expect(presetsLoading).toHaveAttribute("role", "status");
      await expect(presetsLoading).toHaveAttribute("aria-live", "polite");
      await expect(presetsLoading).toHaveAttribute("data-size", "page");
      await expect(presetsLoading.locator(".cm-loading-spinner")).toHaveAttribute("aria-hidden", "true");
      await expect(presetsLoading.locator(".cm-loading-label")).toHaveText("Loading presets…");

      releasePresets();
      await expect(
        page.locator('[data-testid^="preset-card-"]').first(),
      ).toBeVisible({ timeout: 15000 });
      await expect(presetsLoading).toHaveCount(0);

      // ── Snapshots ──
      await page.locator('.comfymodal-studio-backend-tab[data-tab="snapshots"]').click();
      const snapshotsLoading = page.locator('[data-testid="backend-snapshots-loading"]');
      await expect(snapshotsLoading).toBeVisible({ timeout: 10000 });
      await expect(snapshotsLoading).toHaveAttribute("role", "status");
      await expect(snapshotsLoading).toHaveAttribute("aria-live", "polite");
      await expect(snapshotsLoading.locator(".cm-loading-label")).toHaveText("Loading snapshots…");

      releaseSnapshots();
      await expect(
        page.locator(".comfymodal-studio-snapshot-card").first(),
      ).toBeVisible({ timeout: 15000 });
      await expect(snapshotsLoading).toHaveCount(0);

      // ── Workspaces (mocked registry envelope; server-authoritative UI) ──
      await page.locator('.comfymodal-studio-backend-tab[data-tab="workspaces"]').click();
      const workspacesLoading = page.locator('[data-testid="backend-workspaces-loading"]');
      await expect(workspacesLoading).toBeVisible({ timeout: 10000 });
      await expect(workspacesLoading).toHaveAttribute("role", "status");
      await expect(workspacesLoading).toHaveAttribute("aria-live", "polite");
      await expect(workspacesLoading).toHaveAttribute("data-size", "inline");
      await expect(workspacesLoading.locator(".cm-loading-label")).toHaveText("Loading workspaces…");

      releaseWorkspaces();
      await expect(
        page.locator('[data-testid="backend-workspaces-active-label"]'),
      ).toHaveText("Studio A", { timeout: 15000 });
      await expect(workspacesLoading).toHaveCount(0);

      // Readiness truth intact: active card carries its server-truth badge.
      const activeCard = page.locator('[data-testid="backend-workspace-card"]', {
        hasText: "Studio A",
      }).first();
      await expect(activeCard.locator(".comfymodal-studio-status-badge")).toContainText("ACTIVE");
      t.assertNoConsoleErrors();
    } finally {
      t.guard.dispose();
    }
  });

  test("C. Settings reset controls have pairwise-unique accessible names", async ({
    page,
  }) => {
    const t = await setupFakeTest(page);
    try {
      await t.gotoPage("settings");
      const resets = page.locator("button[data-testid^='settings-reset-']");
      await expect(resets.first()).toBeVisible({ timeout: 15000 });

      const names = await resets.evaluateAll((els) =>
        els.map((el) => el.getAttribute("aria-label") || el.textContent.trim()),
      );
      // Section resets identify their section; panel-layout and Reset-all keep
      // their own distinct concise names.
      for (const expected of [
        "Reset Generation section",
        "Reset Outputs section",
        "Reset History section",
        "Reset Interface section",
        "Reset Advanced section",
      ]) {
        expect(names, `missing accessible name: ${expected}`).toContain(expected);
      }
      expect(names).toContain("Reset all settings");
      expect(new Set(names).size).toBe(names.length);
      // Visual text may stay concise; the bare duplicated name must be gone
      // from the ACCESSIBLE NAME of every control.
      for (const name of names) {
        expect(name.trim()).not.toBe("Reset section");
      }
      // Visible button text unchanged (concise label preserved).
      const visibleTexts = await resets.evaluateAll((els) =>
        els.map((el) => el.textContent.trim()),
      );
      expect(visibleTexts.filter((txt) => txt === "Reset section").length).toBe(5);
      t.assertNoConsoleErrors();
    } finally {
      t.guard.dispose();
    }
  });

  test("D. frozen wording rows render verbatim in Settings", async ({ page }) => {
    const t = await setupFakeTest(page);
    try {
      await t.gotoPage("settings");
      const host = page.locator(".comfymodal-settings-sections");
      await expect(host).toBeVisible({ timeout: 15000 });

      await expect(
        host.getByText("Primary navigation: Playground / History / Workflows / Backend / Settings."),
      ).toHaveCount(1);
      await expect(host.getByText("Run history is stored locally and is kept until you delete it.")).toHaveCount(1);
      await expect(
        host.getByText("Experiments run up to 6 cells concurrently. Per-experiment overrides are not available."),
      ).toHaveCount(1);

      // Retired implementation-speak phrasing stays gone.
      await expect(host.getByText(/no retention limit setting exists today/)).toHaveCount(0);
      await expect(host.getByText(/fixed global backend width/)).toHaveCount(0);
      await expect(host.getByText(/Backend remains available in navigation/)).toHaveCount(0);

      // Frozen vocabulary preserved: preset systems keep their names.
      await expect(host.getByText(/Workflow Presets/)).toHaveCount(0); // not renamed INTO settings copy
      const runtimeGroupText = await page
        .locator(".comfymodal-settings-group", { hasText: "Runtime & Backend" })
        .textContent();
      expect(runtimeGroupText).toContain("Deploy state");
      expect(runtimeGroupText).toContain("Snapshots");
      expect(runtimeGroupText).toContain("Presets");
      t.assertNoConsoleErrors();
    } finally {
      t.guard.dispose();
    }
  });

  test("E. Backend tabs stay keyboard operable with truthful selection state", async ({
    page,
  }) => {
    const t = await setupFakeTest(page);
    try {
      await mockBackendOpsRoutes(page);
      await t.gotoPage("backend");

      const tabs = page.locator(".comfymodal-studio-backend-tab");
      await expect(tabs.first()).toBeVisible({ timeout: 15000 });
      const tabCount = await tabs.count();
      expect(tabCount).toBe(6);

      // Native buttons: sequential keyboard traversal reaches every tab.
      await tabs.first().focus();
      for (let i = 1; i < tabCount; i++) {
        await page.keyboard.press("Tab");
        await expect(tabs.nth(i)).toBeFocused();
      }

      // Keyboard activation switches the view AND moves aria-current.
      const workspacesTab = tabs.nth(1);
      await workspacesTab.focus();
      await page.keyboard.press("Enter");
      await expect(page.locator('[data-testid="backend-workspaces"]')).toBeVisible({ timeout: 10000 });
      await expect(workspacesTab).toHaveAttribute("aria-current", "true");
      await expect(tabs.nth(0)).not.toHaveAttribute("aria-current");
      await expect(tabs.nth(2)).not.toHaveAttribute("aria-current");

      // Exactly one aria-current across the tab strip at any time.
      const currentCount = await page
        .locator('.comfymodal-studio-backend-tab[aria-current="true"]')
        .count();
      expect(currentCount).toBe(1);

      // Enter back on Overview restores it through the keyboard only.
      await tabs.nth(0).focus();
      await page.keyboard.press("Enter");
      await expect(page.locator('[data-testid="backend-runtime"]')).toBeVisible({ timeout: 10000 });
      await expect(tabs.nth(0)).toHaveAttribute("aria-current", "true");
      await expect(workspacesTab).not.toHaveAttribute("aria-current");
      t.assertNoConsoleErrors();
    } finally {
      t.guard.dispose();
    }
  });

  test("F. chip geometry: status badges inherit cm-chip; feature chips keep FILTER semantics", async ({
    page,
  }) => {
    const t = await setupFakeTest(page);
    try {
      await mockBackendOpsRoutes(page);
      await t.gotoPage("backend");

      // Status badge (workspace ACTIVE) carries the shared base + tone from
      // the globally migrated statusBadge().
      await page.locator('.comfymodal-studio-backend-tab[data-tab="workspaces"]').click();
      const activeBadge = page
        .locator('[data-testid="backend-workspace-card"] .comfymodal-studio-status-badge')
        .first();
      await expect(activeBadge).toBeVisible({ timeout: 15000 });
      await expect(activeBadge).toHaveClass(/cm-chip/);
      await expect(activeBadge).toHaveAttribute("data-tone", "ok");
      const badgeGeometry = await activeBadge.evaluate((el) => {
        const cs = getComputedStyle(el);
        return { radius: cs.borderRadius, display: cs.display };
      });
      expect(badgeGeometry.radius).toBe("999px");
      expect(badgeGeometry.display).toBe("inline-flex");

      // Feature chips (FILTER): cm-chip geometry adopted, aria-pressed kept,
      // no compatibility-family mislabel.
      await page.locator('.comfymodal-studio-backend-tab[data-tab="presets"]').click();
      const chip = page
        .locator('[data-testid="backend-detail"] .comfymodal-studio-feature-chip')
        .first();
      await expect(chip).toBeVisible({ timeout: 15000 });
      await expect(chip).toHaveClass(/cm-chip/);
      await expect(chip).not.toHaveClass(/cm-chip--compatibility/);
      await expect(chip).toHaveAttribute("aria-pressed", "true"); // txt2img preselected on seeded preset

      const chipGeometry = await chip.evaluate((el) => {
        const cs = getComputedStyle(el);
        return {
          radius: cs.borderRadius,
          // Inside the flex chip-grid the declared inline-flex BLOCKIFIES to
          // flex (CSS display spec) — radius/padding carry the cm-chip base.
          padding: cs.padding,
        };
      });
      expect(chipGeometry.radius).toBe("999px");
      expect(chipGeometry.padding).toBe("2px 8px");

      // Toggling still flips truthful pressed state (FILTER behavior intact).
      await chip.click();
      await expect(chip).toHaveAttribute("aria-pressed", "false");
      await chip.click();
      await expect(chip).toHaveAttribute("aria-pressed", "true");
      t.assertNoConsoleErrors();
    } finally {
      t.guard.dispose();
    }
  });

  test("G. no retired Settings control reappears; no /studio/backends fetch", async ({
    page,
  }) => {
    const t = await setupFakeTest(page);
    try {
      const seenUrls = [];
      page.on("request", (req) => seenUrls.push(req.url()));

      await t.gotoPage("settings");
      await expect(page.locator(".comfymodal-studio-settings")).toBeVisible({ timeout: 15000 });
      // Let async refreshes land before judging the recorded traffic.
      await expect(page.locator('[data-testid="settings-deploy-state"]')).toContainText("ready", {
        timeout: 10000,
      });
      await expect(page.locator('[data-testid="settings-gpu"]')).toBeVisible();

      // No retired control testids anywhere on the mounted page.
      for (const retired of [
        "settings-run-mode",
        "settings-execution-engine",
        "settings-runtime-backends",
        "settings-global-concurrency",
      ]) {
        expect(await page.locator(`[data-testid="${retired}"]`).count()).toBe(0);
      }

      // Preferences-only authority: GPU + preview remain; deploy/snapshot/
      // preset rows are informational; no provider selector, no legacy UI.
      await expect(page.getByRole("button", { name: /providers/i })).toHaveCount(0);
      await expect(page.locator(".comfymodal-studio-settings").getByText("Legacy Settings")).toHaveCount(0);
      await expect(page.locator('[data-testid="settings-reset-all"]')).toBeVisible();

      // The retired compatibility count fetch must NOT reappear in traffic.
      const backendFetches = seenUrls.filter((url) => url.includes("/studio/backends"));
      expect(backendFetches, `observed: ${backendFetches.join(", ")}`).toEqual([]);
      t.assertNoConsoleErrors();
    } finally {
      t.guard.dispose();
    }
  });
});
