// Phase I6 — Workflows / Models / Portability polish (fake E2E).
//
// Permanent product coverage for the frozen I6 contract:
//   - heading hierarchy: exactly one shell h1 ("Modal GPU"), page-level h2
//     ("Workflows" / "Model Library"), workflow detail name demoted to h3
//     (was a second application h1)
//   - loading migration onto the shared renderLoadingState primitive
//     (role=status, aria-live=polite, truthful labels)
//   - wf/model chips adopt the shared cm-chip geometry + truthful tones
//   - Portability stays its own visually distinct family (cm-chip--portability)
//     and never collapses into Compatibility/identity presentation
//   - the duplicated "Portability: …" accessible names become distinguishable
//     per workflow
//   - missing custom-node dependency rows expose exactly ONE Manager-backed
//     "Install now" action (no record-only request, no Find-in-registry)
//   - missing model dependency rows expose exactly two explicit install
//     actions ("Queue install" / "Install now")
//   - model "Used by N workflows · View" derives from ALREADY-loaded
//     dependency payloads and navigates the EXISTING Workflows filters
//   - no duplicate installer authority anywhere in these flows

import { test, expect } from "@playwright/test";
import {
  setupFakeTest,
  createSession,
  installConsoleGuard,
} from "./helpers.mjs";

const CARD = (id) => `[data-testid="workflow-card"][data-workflow-id="${id}"]`;
const NAV_WORKFLOWS = '.comfymodal-studio-topnav button[data-page="workflows"]';

/**
 * Hold EVERY matching request until the returned release function is called,
 * then pass everything through deterministically.  The handler stays
 * installed for the whole test: calling page.unroute() while a held handler
 * is still awaiting makes Playwright fall back-handle the route, and the
 * later route.continue() would throw "Route is already handled" (same
 * precedent as the I4 spec's helper).
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

function trackPosts(page, pattern) {
  const hits = [];
  const onReq = (r) => {
    if (r.method() === "POST" && pattern.test(r.url())) hits.push(r.url());
  };
  page.on("request", onReq);
  return { hits, dispose: () => page.off("request", onReq) };
}

/** Add a MISSING custom node to whatever dependencies payload is served. */
async function stubMissingNode(page, name, exactRegistryMatch = false) {
  const pattern = "**/studio/workflows/versions/*/dependencies";
  const handler = async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    payload.custom_nodes.push({
      name,
      state: "missing",
      repository_url: exactRegistryMatch ? "" : "https://github.com/example/" + name,
      required_revision: "",
      installed_commit: "",
    });
    payload.summary.attention = (payload.summary.attention || 0) + 1;
    await route.fulfill({ response, json: payload });
  };
  await page.route(pattern, handler);
  return () => page.unroute(pattern, handler);
}

test.describe("I6 Workflows / Models polish", () => {
  test("A. one shell h1, page h2, detail h3 — full heading hierarchy", async ({ page }) => {
    // Drive the REAL production dialog entry so the shell h1 participates.
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
    await page.evaluate(async () => {
      const mod = await import("/extensions/comfymodal-modal/modal-testing.js");
      mod.open_testing_modal();
    });
    const dialog = page.locator(".comfymodal-studio-modal[role='dialog']");
    await expect(dialog).toBeVisible({ timeout: 15000 });

    // Exactly one h1 in the whole application: the shell header.
    await expect(page.locator("h1")).toHaveCount(1);
    await expect(page.locator("h1")).toHaveText("Modal GPU");

    // Library view: exactly one h2 ("Workflows"); card names are h3, never h1/h2.
    await page.locator(NAV_WORKFLOWS).click();
    await expect(page.getByTestId("workflows-page")).toBeVisible({ timeout: 15000 });
    await expect(page.locator('[data-testid="workflow-card"]').first()).toBeVisible({ timeout: 15000 });
    const libCensus = await page.evaluate(() => {
      const hs = Array.from(document.querySelectorAll("h1, h2, h3"));
      return {
        h1: hs.filter((h) => h.tagName === "H1").map((h) => h.textContent.trim()),
        h2: hs.filter((h) => h.tagName === "H2").map((h) => h.textContent.trim()),
        cardNameTags: Array.from(
          document.querySelectorAll('[data-testid="workflow-card"] .comfymodal-studio-workflow-card-name')
        ).map((el) => el.tagName),
      };
    });
    expect(libCensus.h1).toEqual(["Modal GPU"]);
    expect(libCensus.h2).toEqual(["Workflows"]);
    expect(libCensus.cardNameTags.length).toBeGreaterThan(0);
    for (const tag of libCensus.cardNameTags) expect(tag).toBe("H3");

    // Detail view: the workflow name is now an H3 (formerly a second h1);
    // no h1/h2 may appear inside the detail surface.
    await page.locator(CARD("wf_text2img")).click();
    await expect(page.getByTestId("workflow-detail")).toBeVisible({ timeout: 15000 });
    const detailName = page.getByTestId("workflow-detail-name");
    await expect(detailName).toHaveText("Text2Img Workflow");
    expect(await detailName.evaluate((el) => el.tagName)).toBe("H3");
    const detailCensus = await page.evaluate(() => {
      const detail = document.querySelector('[data-testid="workflow-detail"]');
      return {
        docH1: document.querySelectorAll("h1").length,
        inside: Array.from(detail.querySelectorAll("h1, h2, h3")).map((h) => h.tagName),
      };
    });
    expect(detailCensus.docH1).toBe(1);
    expect(detailCensus.inside.length).toBeGreaterThan(0);
    expect(detailCensus.inside).not.toContain("H1");
    expect(detailCensus.inside).not.toContain("H2");

    // Model Library sub-view: page-level h2 title under the shell h1;
    // the Custom nodes group stays an h3 beneath it.
    await page.getByRole("button", { name: /Back to Workflows/ }).click();
    await expect(page.locator(CARD("wf_text2img"))).toBeVisible({ timeout: 15000 });
    await page.getByTestId("wf-subnav-models").click();
    await expect(page.getByTestId("models-page")).toBeVisible({ timeout: 15000 });
    const modelsTitle = page.getByTestId("models-page-title");
    await expect(modelsTitle).toHaveText("Model Library");
    expect(await modelsTitle.evaluate((el) => el.tagName)).toBe("H2");
    const modelsCensus = await page.evaluate(() => {
      const pageEl = document.querySelector('[data-testid="models-page"]');
      return Array.from(pageEl.querySelectorAll("h2, h3")).map((h) => ({
        tag: h.tagName,
        title: h.textContent.trim(),
      }));
    });
    expect(modelsCensus[0]).toEqual({ tag: "H2", title: "Model Library" });
    expect(modelsCensus).toContainEqual({ tag: "H3", title: "Custom nodes" });
    guard.dispose();
  });

  test("B. shared loading primitive on workflows, detail, version, mapping, models", async ({ page }) => {
    const t = await setupFakeTest(page);
    page.on("response", (r) => { if (r.status() >= 400) console.log("[I6B] HTTP", r.status(), r.url()); });
    try {
      // ── Library loading ──
      const releaseWorkflows = await holdRequests(page, /\/comfymodal\/studio\/workflows$/);
      await t.gotoPage("workflows");
      const libLoading = page.locator('[data-testid="workflows-loading"]');
      await expect(libLoading).toBeVisible({ timeout: 10000 });
      await expect(libLoading).toHaveAttribute("role", "status");
      await expect(libLoading).toHaveAttribute("aria-live", "polite");
      await expect(libLoading).toHaveAttribute("data-size", "page");
      await expect(libLoading.locator(".cm-loading-spinner")).toHaveAttribute("aria-hidden", "true");
      await expect(libLoading.locator(".cm-loading-label")).toHaveText("Loading workflows…");
      releaseWorkflows();
      await expect(page.locator('[data-testid="workflow-card"]').first()).toBeVisible({ timeout: 15000 });

      // ── Detail + selected-version loading (held workflow + version fetch) ──
      const releaseDetail = await holdRequests(page, /\/comfymodal\/studio\/workflows\/wf_text2img$/);
      const releaseVersion = await holdRequests(page, /\/studio\/workflows\/versions\/wv1_latest$/);
      await page.locator(CARD("wf_text2img")).click();
      const detailLoading = page.locator('[data-testid="workflow-detail-loading"]');
      await expect(detailLoading).toBeVisible({ timeout: 10000 });
      await expect(detailLoading).toHaveAttribute("role", "status");
      await expect(detailLoading.locator(".cm-loading-label")).toHaveText("Loading workflow…");
      releaseDetail();
      await expect(page.getByTestId("workflow-detail-name")).toBeVisible({ timeout: 15000 });
      const versionLoading = page.locator('[data-testid="workflow-version-loading"]');
      await expect(versionLoading).toBeVisible({ timeout: 10000 });
      await expect(versionLoading).toHaveAttribute("data-size", "inline");
      await expect(versionLoading).toHaveAttribute("role", "status");
      await expect(versionLoading.locator(".cm-loading-label")).toHaveText("Loading selected version…");
      releaseVersion();
      await expect(page.getByTestId("run-button")).toBeVisible({ timeout: 15000 });

      // ── Mapping candidates loading (held; unmapped workflow) ──
      const releaseCandidates = await holdRequests(page, /\/mapping\/candidates/);
      await page.getByRole("button", { name: /Back to Workflows/ }).click();
      await expect(page.locator(CARD("wf_incomplete"))).toBeVisible({ timeout: 15000 });
      await page.locator(CARD("wf_incomplete")).click();
      await expect(page.getByTestId("workflow-detail")).toBeVisible({ timeout: 15000 });
      await page.getByRole("button", { name: "Set up Mapping" }).click();
      const mappingLoading = page.locator('[data-testid="mapping-loading"]');
      await expect(mappingLoading).toBeVisible({ timeout: 10000 });
      await expect(mappingLoading).toHaveAttribute("role", "status");
      await expect(mappingLoading.locator(".cm-loading-label")).toHaveText("Loading mapping…");
      releaseCandidates();
      await expect(page.getByTestId("mapping-candidates")).toBeVisible({ timeout: 15000 });

      // ── Model Library first-open loading (held) ──
      const releaseModels = await holdRequests(page, /\/comfymodal\/studio\/models$/);
      await page.getByRole("button", { name: /Back to Workflows/ }).click();
      await expect(page.locator(CARD("wf_incomplete"))).toBeVisible({ timeout: 15000 });
      await page.getByTestId("wf-subnav-models").click();
      const modelsLoading = page.locator('[data-testid="models-loading"]');
      await expect(modelsLoading).toBeVisible({ timeout: 10000 });
      await expect(modelsLoading).toHaveAttribute("role", "status");
      await expect(modelsLoading.locator(".cm-loading-label")).toHaveText("Loading models…");
      releaseModels();
      await expect(page.locator('[data-testid="model-row"]').first()).toBeVisible({ timeout: 15000 });
      // The deterministic fake does not implement /mapping/candidates (the
      // loading-state hold above proves the primitive before the honest 404
      // lands); the production route is covered by Python route tests. The
      // two resource-load 404s are that known harness gap.
      t.assertNoConsoleErrors(["Failed to load resource.*404"]);
    } finally {
      t.guard.dispose();
    }
  });

  test("C. wf/model chips share cm-chip geometry; portability stays its own family", async ({ page }) => {
    const t = await setupFakeTest(page);
    try {
      await t.gotoPage("workflows");
      await expect(page.locator('[data-testid="workflow-card"]').first()).toBeVisible({ timeout: 15000 });

      // Identity chip (tag) carries shared base + neutral tone.
      const tagChip = page.locator(`${CARD("wf_text2img")} .comfymodal-studio-wf-chip`).first();
      await expect(tagChip).toHaveClass(/cm-chip/);
      await expect(tagChip).toHaveAttribute("data-tone", "neutral");
      const tagGeo = await tagChip.evaluate((el) => {
        const cs = getComputedStyle(el);
        return { radius: cs.borderRadius, display: cs.display };
      });
      // NOTE: inside the flex tags container the value blockifies to "flex"
      // (CSS Flexbox §4); the shared base's inline-flex shows on standalone
      // chips. Geometry + class prove the shared base here.
      expect(tagGeo.radius).toBe("999px");
      expect(tagGeo.display).toMatch(/^(inline-)?flex$/);

      // Portability chip keeps its DISTINCT outline family marker + tone.
      const portChip = page.locator(`${CARD("wf_text2img")} [data-testid="portability-chip"]`);
      await expect(portChip).toHaveClass(/cm-chip--portability/);
      await expect(portChip).toHaveAttribute("data-tone", "neutral");
      const portBg = await portChip.evaluate((el) => getComputedStyle(el).backgroundColor);
      expect(portBg).toBe("rgba(0, 0, 0, 0)"); // outline pill, never filled

      // Model Library badges: capability tones (installed→ok, missing→warn),
      // type stays identity/neutral — all on shared pill geometry.
      await page.getByTestId("wf-subnav-models").click();
      await expect(page.getByTestId("models-page")).toBeVisible({ timeout: 10000 });
      const installedBadge = page
        .locator('[data-testid="model-row"][data-model-id="ml_sd15_v2"] .comfymodal-studio-model-badge')
        .filter({ hasText: "Installed" });
      await expect(installedBadge).toHaveClass(/cm-chip/);
      await expect(installedBadge).toHaveAttribute("data-tone", "ok");
      const missingBadge = page
        .locator('[data-testid="model-row"][data-model-id="ml_krea"] .comfymodal-studio-model-badge')
        .filter({ hasText: "Missing" });
      await expect(missingBadge).toHaveAttribute("data-tone", "warn");
      const typeBadge = page
        .locator('[data-testid="model-row"][data-model-id="ml_krea"] .comfymodal-studio-model-badge')
        .filter({ hasText: "checkpoint" });
      await expect(typeBadge).toHaveAttribute("data-tone", "neutral");
      const badgeGeo = await missingBadge.evaluate((el) => getComputedStyle(el).borderRadius);
      expect(badgeGeo).toBe("999px");

      // Compatibility annotations (Compatible models chips in detail) remain
      // a DIFFERENT presentation from portability: filled identity chip.
      await page.getByTestId("models-back").click();
      await page.locator(CARD("wf_text2img")).click();
      await expect(page.getByTestId("workflow-detail")).toBeVisible({ timeout: 15000 });
      const compatBlock = page.locator(".comfymodal-studio-workflows-tags")
        .filter({ hasText: "Compatible models" });
      await expect(compatBlock).toBeVisible({ timeout: 10000 });
      const compatChip = compatBlock.locator(".comfymodal-studio-wf-chip").first();
      await expect(compatChip).toBeVisible();
      const compatBg = await compatChip.evaluate((el) => getComputedStyle(el).backgroundColor);
      expect(compatBg).not.toBe("rgba(0, 0, 0, 0)");
      t.assertNoConsoleErrors();
    } finally {
      t.guard.dispose();
    }
  });

  test("D. all simultaneously rendered portability controls have distinguishable names", async ({ page }) => {
    const t = await setupFakeTest(page);
    try {
      await t.gotoPage("workflows");
      await expect(page.locator('[data-testid="workflow-card"]').first()).toBeVisible({ timeout: 15000 });
      const labels = await page.evaluate(() =>
        Array.from(document.querySelectorAll('[data-testid="portability-chip"]')).map((el) =>
          el.getAttribute("aria-label")
        )
      );
      expect(labels.length).toBeGreaterThan(1);
      expect(new Set(labels).size).toBe(labels.length);
      for (const label of labels) {
        expect(label).toMatch(/^Portability for .+: .+\. Opens the portability panel\.$/);
      }

      // The detail chip is context-named too (workflow + version scope).
      await page.locator(CARD("wf_incomplete")).click();
      await expect(page.getByTestId("workflow-detail")).toBeVisible({ timeout: 15000 });
      const detailLabel = await page
        .getByTestId("portability-detail-chip")
        .getAttribute("aria-label");
      expect(detailLabel).toContain("Incomplete Workflow");
      expect(detailLabel).toMatch(/v\d+/);
      t.assertNoConsoleErrors();
    } finally {
      t.guard.dispose();
    }
  });

  test("E. missing custom-node row exposes one Manager install; no install on render", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const installs = trackPosts(page, /install-request|models\/download/);
    try {
      const unstub = await stubMissingNode(page, "ComfyUI-Missing");

      await fx.gotoPage("workflows");
      await expect(page.getByTestId("workflows-page")).toBeVisible({ timeout: 10000 });
      await page.locator(CARD("wf_fake")).click();
      await expect(page.getByTestId("workflow-detail")).toBeVisible({ timeout: 15000 });

      const missingRow = page.getByTestId("dependency-node-row").filter({ hasText: "ComfyUI-Missing" });
      await expect(missingRow).toContainText("Missing", { timeout: 10000 });

      // Exactly ONE install action, Manager-backed; no record-only request
      // and no Find-in-registry alternate.
      await expect(missingRow.getByTestId("dependency-node-install-now")).toHaveText("Install now");
      await expect(missingRow.getByTestId("dependency-node-install-request")).toHaveCount(0);
      await expect(missingRow.getByTestId("dependency-node-find-registry")).toHaveCount(0);
      await expect(missingRow.getByTestId("dependency-node-manager-install")).toHaveCount(0);

      // Rendering alone fired zero installer requests.
      expect(installs.hits).toEqual([]);
      fx.assertNoConsoleErrors();
      unstub();
    } finally {
      installs.dispose();
      fx.guard.dispose();
    }
  });

  test("G. model handoff highlights exact row; 'Used by' navigates filtered workflows", async ({ page }) => {
    const t = await setupFakeTest(page);
    try {
      await t.gotoPage("workflows");
      await expect(page.locator('[data-testid="workflow-card"]').first()).toBeVisible({ timeout: 15000 });

      // No reverse-usage claims before any dependency payload was loaded.
      await page.getByTestId("wf-subnav-models").click();
      await expect(page.getByTestId("models-page")).toBeVisible({ timeout: 10000 });
      await expect(page.locator('[data-testid="model-used-by"]')).toHaveCount(0);
      await page.getByTestId("models-back").click();

      // Opening a detail loads its dependencies → the session index learns
      // that this workflow references krea_model.safetensors.
      await page.locator(CARD("wf_fake")).click();
      await expect(page.getByTestId("workflow-detail")).toBeVisible({ timeout: 15000 });
      await expect(page.getByTestId("dependency-status")).toContainText("attention", { timeout: 10000 });

      await page.getByRole("button", { name: /Back to Workflows/ }).click();
      await expect(page.locator(CARD("wf_fake"))).toBeVisible({ timeout: 15000 });
      await page.getByTestId("wf-subnav-models").click();

      // Only the referenced model carries the derived usage line.
      const kreaRow = page.locator('[data-testid="model-row"][data-model-id="ml_krea"]');
      await expect(kreaRow.getByTestId("model-used-by")).toContainText(
        "Used by 1 workflow", { timeout: 10000 }
      );
      await expect(kreaRow.getByTestId("model-used-by-view")).toHaveText("View");
      const sd15Row = page.locator('[data-testid="model-row"][data-model-id="ml_sd15_v2"]');
      await expect(sd15Row.getByTestId("model-used-by")).toHaveCount(0);

      // Dependency-row handoff still prefills the search AND highlights the
      // exact matching row.
      await page.getByTestId("models-back").click();
      await page.locator(CARD("wf_fake")).click();
      await expect(page.getByTestId("workflow-detail")).toBeVisible({ timeout: 15000 });
      const kreaDep = page.getByTestId("dependency-model-row").filter({ hasText: "krea_model.safetensors" });
      await kreaDep.getByTestId("dependency-model-find").click();
      await expect(page.getByTestId("models-page")).toBeVisible({ timeout: 10000 });
      await expect(page.getByTestId("models-search")).toHaveValue("krea_model.safetensors");
      await expect(page.locator('[data-testid="model-row"][data-model-match="true"]')).toHaveCount(1);

      // "Used by · View" navigates the EXISTING Workflows view filtered to
      // the dependent workflow, with a truthful scope notice.
      await kreaRow.getByTestId("model-used-by-view").click();
      await expect(page.getByTestId("workflows-page")).toBeVisible({ timeout: 10000 });
      const notice = page.getByTestId("workflows-usage-focus");
      await expect(notice).toContainText("krea_model.safetensors");
      await expect(notice).toContainText("loaded in this session");
      await expect(page.locator('[data-testid="workflow-card"]')).toHaveCount(1);
      await expect(page.locator(CARD("wf_fake"))).toBeVisible();

      // Clearing the notice restores the full library.
      await notice.getByRole("button", { name: "Clear used-by filter" }).click();
      await expect(page.getByTestId("workflows-usage-focus")).toHaveCount(0);
      expect(await page.locator('[data-testid="workflow-card"]').count()).toBeGreaterThan(1);
      t.assertNoConsoleErrors();
    } finally {
      t.guard.dispose();
    }
  });

  test("H. no duplicate installer authority across library, registry, and dialogs", async ({ page }) => {
    const t = await setupFakeTest(page);
    try {
      const unstub = await stubMissingNode(page, "ComfyUI-Missing");
      await t.gotoPage("workflows");
      await expect(page.locator('[data-testid="workflow-card"]').first()).toBeVisible({ timeout: 15000 });

      // Library rows expose NO installer; the download request lives only in
      // the model detail dialog (exactly one section per dialog).
      await page.getByTestId("wf-subnav-models").click();
      await expect(page.getByTestId("models-page")).toBeVisible({ timeout: 10000 });
      await expect(page.locator('[data-testid="model-download-request"]')).toHaveCount(0);
      await page.locator('[data-testid="model-row"][data-model-id="ml_krea"]').getByTestId("model-details").click();
      await expect(page.getByTestId("model-detail-dialog")).toBeVisible({ timeout: 10000 });
      await expect(page.getByTestId("model-download-section")).toHaveCount(1);
      await page.getByTestId("model-detail-dialog")
        .locator('.comfymodal-studio-dialog-actions button', { hasText: "Cancel" }).click();

      // Version-scoped dependency section: the missing node row exposes
      // exactly ONE Manager-backed install action; the missing model row
      // exposes exactly the two explicit install actions. No record-only
      // request and no Find-in-registry alternate.
      await page.getByTestId("models-back").click();
      await page.locator(CARD("wf_fake")).click();
      await expect(page.getByTestId("workflow-detail")).toBeVisible({ timeout: 15000 });
      await expect(page.getByTestId("dependency-node-install-now")).toHaveCount(1);
      await expect(page.getByTestId("dependency-node-install-request")).toHaveCount(0);
      await expect(page.getByTestId("dependency-node-find-registry")).toHaveCount(0);
      await expect(page.getByTestId("dependency-node-manager-install")).toHaveCount(0);
      await expect(page.getByTestId("dependency-model-queue")).toHaveCount(1);
      await expect(page.getByTestId("dependency-model-install-now")).toHaveCount(1);
      await expect(page.getByTestId("dependency-model-download")).toHaveCount(0);
      t.assertNoConsoleErrors();
      unstub();
    } finally {
      t.guard.dispose();
    }
  });
});
