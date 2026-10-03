// Modal Studio — Settings E2E Tests
//
// Tests the redesigned seven-section Settings page (web/studio-settings.js)
// against the in-memory mock API. Mock is installed BEFORE navigation per
// isolation contract.
//
// DOM contract under test:
//   - Seven sections: div.comfymodal-studio-settings-section[data-section=...]
//   - Search input filters [data-search] rows and hides empty sections
//   - Outputs host populates asynchronously from /comfymodal/config
//   - Persistence is localStorage-backed (flat keys) + POST /comfymodal/config
//   - "Reset all settings" clears only MODERN_SETTINGS_KEYS (user data intact)
//   - Legacy settings panels are reachable through the Advanced section
//   - Heavy-tracing banner reflects stored-vs-effective level mismatch

import { test, expect } from "@playwright/test";
import { installConsoleGuard, openStudio } from "./studio-fixtures.mjs";
import { installStudioMockApi } from "./studio-mock-api.mjs";

const COMFYUI_URL = process.env.COMFYUI_URL || "http://127.0.0.1:8188";

// App-level noise patterns (see studio-features.spec.mjs) — unrelated to the
// pipeline under test; uncaught pageerrors are still always reported.
const APP_NOISE_PATTERNS = [
  "already registered",        // sibling lanes re-register extension names
  "vite:preloadError",         // ComfyUI app preload failures
  "Failed to load resource",   // app-internal 404s (/lm/settings, pysssss)
  "ComfyApp graph accessed",   // app startup before a graph is loaded
];

// ── Helpers ────────────────────────────────────────────────────────────────

async function waitVisible(locator, timeout = 15000) {
  await locator.waitFor({ state: "visible", timeout });
  return locator;
}

/** Open the studio and navigate to the Settings page. */
async function openSettings(page) {
  await openStudio(page, COMFYUI_URL);
  await waitVisible(page.locator('[data-testid="studio-page"]'));
  await page.locator('[data-page="settings"]').click();
  await waitVisible(page.locator('[data-section="general"]'));
}

/** Read a localStorage key from the page. */
function readLocalStorage(page, key) {
  return page.evaluate((k) => localStorage.getItem(k), key);
}

// ── Tests ──────────────────────────────────────────────────────────────────

test.describe("Studio Settings (redesigned)", () => {
  test.beforeEach(async ({ page }) => {
    await installStudioMockApi(page);
  });

  // ── Test 1: Section layout ───────────────────────────────────────────────
  test("renders all seven settings sections", async ({ page }) => {
    let guard;
    try {
      await openSettings(page);
      guard = installConsoleGuard(page);

      // Seven data-section sections, one per id
      const sections = page.locator(".comfymodal-settings-sections [data-section]");
      await expect(sections).toHaveCount(7, { timeout: 10000 });
      for (const id of [
        "general", "generation", "outputs", "history",
        "experiments", "interface", "advanced",
      ]) {
        await expect(page.locator(`[data-section="${id}"]`)).toHaveCount(1);
      }

      // Search input with the expected placeholder
      const search = page.locator('[data-testid="settings-search"]');
      await expect(search).toBeVisible();
      await expect(search).toHaveAttribute("placeholder", "Search settings...");

      guard.assertNoErrors(APP_NOISE_PATTERNS);
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 2: Search filtering ─────────────────────────────────────────────
  test("search filters rows and sections", async ({ page }) => {
    let guard;
    try {
      await openSettings(page);
      guard = installConsoleGuard(page);

      const search = page.locator('[data-testid="settings-search"]');
      const general = page.locator('[data-section="general"]');
      const experiments = page.locator('[data-section="experiments"]');
      const advanced = page.locator('[data-section="advanced"]');
      const results = page.locator('[data-testid="settings-search-results"]');

      // "concurrent" → Experiments visible, General hidden
      // (the row copy reads "...cells concurrently", so search the stem)
      await search.fill("concurrent");
      await expect(experiments).toBeVisible({ timeout: 5000 });
      await expect(general).toBeHidden();

      // "legacy" → Advanced visible (contains the legacy group), General hidden
      await search.fill("legacy");
      await expect(advanced).toBeVisible({ timeout: 5000 });
      await expect(general).toBeHidden();

      // Clearing restores every section
      await search.fill("");
      await expect(general).toBeVisible({ timeout: 5000 });
      await expect(advanced).toBeVisible();

      // No matches → the empty-state line
      await search.fill("zzzznope");
      await expect(results).toHaveText("No settings match your search");
      await expect(general).toBeHidden();

      guard.assertNoErrors(APP_NOISE_PATTERNS);
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 3: Output preference saves immediately ──────────────────────────
  test("output preference saves immediately", async ({ page }) => {
    let guard;
    try {
      await openSettings(page);

      // Wait for the async outputs host to populate
      const formatSelect = page.locator('[data-testid="settings-output-format"]');
      await formatSelect.waitFor({ state: "visible", timeout: 15000 });
      guard = installConsoleGuard(page);

      await formatSelect.selectOption("webp_lossy");

      // Dual-write contract: localStorage + shared window object
      await expect
        .poll(() => readLocalStorage(page, "comfymodal_output_format"))
        .toBe("webp_lossy");
      await expect
        .poll(() =>
          page.evaluate(() =>
            window._comfyModalOutputOptions
              ? window._comfyModalOutputOptions.output_format
              : null
          )
        )
        .toBe("webp_lossy");

      guard.assertNoErrors(APP_NOISE_PATTERNS);
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 4: Settings persist across reload ───────────────────────────────
  test("settings persist across reload", async ({ page }) => {
    let guard;
    try {
      await openSettings(page);
      const previewQuality = page.locator('[data-testid="settings-preview-quality"]');
      await previewQuality.waitFor({ state: "visible", timeout: 15000 });
      guard = installConsoleGuard(page);

      // Range input: set value + dispatch change (the page listens for change)
      await page.evaluate(() => {
        const el = document.querySelector('[data-testid="settings-preview-quality"]');
        el.value = "80";
        el.dispatchEvent(new Event("change", { bubbles: true }));
      });
      await expect
        .poll(() => readLocalStorage(page, "comfymodal_preview_quality"))
        .toBe("80");

      // Drop the guard across reload so app startup noise is not captured,
      // then re-assert with a fresh guard.
      guard.dispose();
      await page.reload({ waitUntil: "domcontentloaded" });
      await openSettings(page);
      guard = installConsoleGuard(page);

      const pqAfter = page.locator('[data-testid="settings-preview-quality"]');
      await pqAfter.waitFor({ state: "visible", timeout: 15000 });
      await expect(pqAfter).toHaveValue("80");
      await expect
        .poll(() => readLocalStorage(page, "comfymodal_preview_quality"))
        .toBe("80");

      guard.assertNoErrors(APP_NOISE_PATTERNS);
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 5: Per-section reset restores defaults ──────────────────────────
  test("reset section restores defaults", async ({ page }) => {
    let guard;
    try {
      await openSettings(page);
      const columns = page.locator('[data-testid="settings-history-columns"]');
      await waitVisible(columns);
      guard = installConsoleGuard(page);

      await columns.selectOption("4");
      await expect
        .poll(() => readLocalStorage(page, "comfymodal-studio-history-columns"))
        .toBe("4");

      // Reset History → select returns to default 6 and the key is removed
      await page.locator('[data-testid="settings-reset-history"]').click();
      await expect(columns).toHaveValue("6", { timeout: 5000 });
      await expect
        .poll(() => readLocalStorage(page, "comfymodal-studio-history-columns"))
        .toBeNull();

      guard.assertNoErrors(APP_NOISE_PATTERNS);
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 6: Reset all requires confirmation and preserves user data ──────
  test("reset all requires confirmation and preserves user data", async ({ page }) => {
    let guard;
    try {
      await openSettings(page);
      guard = installConsoleGuard(page);

      // Reset-all has two distinct contracts, asserted separately:
      //
      // 1. Cleared and left absent. Stale reset-only keys
      //    (comfymodal_global_concurrency, comfymodal_preview_auto_save) were
      //    removed from the registry in F4A and must stay absent — pinned by
      //    tests/studio_phase_f4_settings_authority_unit.mjs.
      const clearedKeys = [
        "comfymodal_gpu",
        "comfymodal-studio-history-columns",
        "comfymodal_heavy_tracing",
        "comfymodal-studio-panel-width",
        "comfymodal.studio.playground.carousel-cleared.v1",
      ];
      // 2. Cleared, then deliberately re-seeded to the documented default,
      //    because reset-all calls setOutputPreferences(OUTPUT_DEFAULTS) and
      //    the preview defaults so the outputs host renders real values.
      const reseededKeys = {
        comfymodal_preview_default: "off",
        comfymodal_preview_codec: "webp",
        comfymodal_preview_quality: "70",
      };
      // User-data namespaces that MUST survive a reset
      const userDataKeys = [
        "comfymodal.studio.playground.drafts.v1",
        "comfymodal_comparison_selected_profiles",
        // H12 retired Run mode: modern Settings has no writer and no resetter
        // for the canvas key, so reset-all must leave it alone. Pinned by
        // tests/studio_phase_f4_settings_authority_unit.mjs (1b).
        "comfymodal_enabled",
      ];

      const seededKeys = Object.keys(reseededKeys);

      await page.evaluate(
        ({ seededKeys, clearedKeys, userDataKeys }) => {
          for (const k of clearedKeys.concat(seededKeys)) localStorage.setItem(k, "seeded");
          for (const k of userDataKeys) localStorage.setItem(k, "user-data-value");
        },
        { seededKeys, clearedKeys, userDataKeys }
      );

      // Accept the confirmation dialog (Playwright auto-dismisses otherwise,
      // which would make confirm() return false and skip the reset).
      page.once("dialog", (dialog) => dialog.accept());
      await page.locator('[data-testid="settings-reset-all"]').click();

      // Cleared keys are gone
      for (const key of clearedKeys) {
        await expect
          .poll(() => readLocalStorage(page, key))
          .toBeNull();
      }

      // Re-seeded keys hold their documented defaults, not the seeded value
      for (const [key, expected] of Object.entries(reseededKeys)) {
        await expect
          .poll(() => readLocalStorage(page, key))
          .toBe(expected);
      }

      // User data is untouched
      for (const key of userDataKeys) {
        await expect
          .poll(() => readLocalStorage(page, key))
          .toBe("user-data-value");
      }

      guard.assertNoErrors(APP_NOISE_PATTERNS);
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 7: Modern and legacy output settings stay synchronized ──────────
  test("modern and legacy output settings stay synchronized", async ({ page }) => {
    let guard;
    try {
      await openSettings(page);
      const formatSelect = page.locator('[data-testid="settings-output-format"]');
      await formatSelect.waitFor({ state: "visible", timeout: 15000 });
      guard = installConsoleGuard(page);

      await formatSelect.selectOption("jpeg");

      // The same localStorage key + window object the legacy panel writes to —
      // one source of truth for both surfaces.
      await expect
        .poll(() => readLocalStorage(page, "comfymodal_output_format"))
        .toBe("jpeg");
      const windowFormat = await page.evaluate(
        () => window._comfyModalOutputOptions && window._comfyModalOutputOptions.output_format
      );
      expect(windowFormat).toBe("jpeg");
      await expect(formatSelect).toHaveValue("jpeg");

      guard.assertNoErrors(APP_NOISE_PATTERNS);
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 9: Restart-required banner ──────────────────────────────────────
  test("restart-required indicator", async ({ page }) => {
    let guard;
    try {
      await openSettings(page);
      guard = installConsoleGuard(page);

      const banner = page.locator('[data-testid="settings-restart-banner"]');
      const tracing = page.locator('[data-testid="settings-heavy-tracing"]');

      // Server truth model: persisted == effective → banner hidden.
      await expect(banner).toBeHidden({ timeout: 10000 });

      // Selecting trace persists a new level while the process keeps running
      // the old one, so persisted != effective → banner shows.
      await tracing.selectOption("trace");
      await expect(banner).toBeVisible({ timeout: 5000 });

      // Back to off: persisted == effective again → banner hides.
      await tracing.selectOption("off");
      await expect(banner).toBeHidden({ timeout: 5000 });

      guard.assertNoErrors(APP_NOISE_PATTERNS);
    } finally {
      if (guard) guard.dispose();
    }
  });
});
