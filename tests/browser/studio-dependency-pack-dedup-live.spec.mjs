// Modal Studio — Live duplicate dependency-pack acceptance probe.
//
// Opt-in live test (COMFYMODAL_LIVE_E2E=1) against a real ComfyUI + Studio
// backend. It proves the dependency-pack canonicalisation contract end to end:
// a version whose classes resolve to several local registry records that all
// share one physical install path must render ONE dependency row for that pack.
//
// Live evidence that motivated this test: the resolver returned three separate
// `donutnodes` rows (same install_path/commit, distinct class subsets and
// mixed cnr/aux identity), and one `DonutReferenceStudio` row with the same
// path and no identity. The physical directory is one pack, so it must be one
// row.
//
// The concrete acceptance fixture is the Krea upscale workflow's donutnodes
// pack. Naming the fixture workflow/version/pack directory here is intentional;
// production code stays generic and hardcodes nothing.
//
// Acceptance assertions (all derived from live data):
//   * No two `custom_nodes` rows share a nonempty install path.
//   * Exactly one row carries the donutnodes physical pack, and it holds the
//     class that previously surfaced with no identity (DonutReferenceStudio).
//   * The dependency DOM renders exactly one row per physical install path and
//     exactly one row for the donutnodes pack.
//
// Every Manager / model mutation route is intercepted and fulfilled locally.
// Nothing is installed or rebooted.

import { writeFileSync } from "node:fs";
import { test, expect } from "@playwright/test";
import { installConsoleGuard, openStudio } from "./studio-fixtures.mjs";

const LIVE_ENABLED = process.env.COMFYMODAL_LIVE_E2E === "1";
const COMFYUI_URL = process.env.COMFYUI_URL || "http://127.0.0.1:8188";

// Concrete acceptance fixture (see header).
const FIXTURE_WORKFLOW_ID = "wf_7cbe640f042f4a3e";
const FIXTURE_VERSION_ID = "wv_3f7e1ec12fe14545";
const DONUT_PACK_DIRNAME = "donutnodes";
// One representative class from each previously-duplicated record: proving all
// three landed on the single row is the regression signal.
const MERGED_CLASS_MARKERS = [
  "DonutReferenceStudio", // the record that surfaced with no cnr/aux identity
  "DonutEditStudio",
  "DonutLoRALoader",
];

function normalizePath(value) {
  let text = String(value || "").replace(/\\/g, "/");
  text = text.replace(/\/+/g, "/");
  if (text.length > 1) text = text.replace(/\/$/, "");
  return text.toLowerCase();
}

function basenameOf(value) {
  const normalized = normalizePath(value);
  const idx = normalized.lastIndexOf("/");
  return idx === -1 ? normalized : normalized.slice(idx + 1);
}

test.describe("Studio dependency pack dedup (live)", () => {
  test.skip(!LIVE_ENABLED, "Set COMFYMODAL_LIVE_E2E=1 to enable live tests");

  test("one dependency row per physical pack install path", async ({
    page,
    request,
  }, testInfo) => {
    let guard;
    const evidence = { live: {} };

    try {
      // ── Live API truth ───────────────────────────────────────────────
      const wfRes = await request.get(
        `${COMFYUI_URL}/comfymodal/studio/workflows/${encodeURIComponent(
          FIXTURE_WORKFLOW_ID
        )}`
      );
      expect(wfRes.ok()).toBeTruthy();
      const workflow = (await wfRes.json()).workflow || {};

      const depsRes = await request.get(
        `${COMFYUI_URL}/comfymodal/studio/workflows/versions/${encodeURIComponent(
          FIXTURE_VERSION_ID
        )}/dependencies`
      );
      expect(depsRes.ok()).toBeTruthy();
      const deps = await depsRes.json();
      const rows = Array.isArray(deps.custom_nodes) ? deps.custom_nodes : [];
      expect(rows.length, "dependency report has no custom-node rows").toBeGreaterThan(0);

      // One physical install path is one row.
      const paths = rows.map((r) => normalizePath(r.install_path)).filter(Boolean);
      expect(
        new Set(paths).size,
        `duplicate install_path rows: ${JSON.stringify(paths)}`
      ).toBe(paths.length);

      // Exactly one row for the fixture's donutnodes pack, holding the class
      // that used to appear on a separate identity-less row.
      const donutRows = rows.filter((r) => basenameOf(r.install_path) === DONUT_PACK_DIRNAME);
      expect(
        donutRows.length,
        `expected exactly one ${DONUT_PACK_DIRNAME} pack row`
      ).toBe(1);
      const donut = donutRows[0];
      expect(donut.state).toBe("installed");
      for (const marker of MERGED_CLASS_MARKERS) {
        expect(
          donut.classes || [],
          `merged ${DONUT_PACK_DIRNAME} row is missing ${marker}`
        ).toContain(marker);
      }
      const rowsWithDonutClass = rows.filter((r) =>
        (r.classes || []).some((c) => String(c).startsWith("Donut"))
      );
      expect(rowsWithDonutClass.length).toBe(1);

      evidence.live.api = {
        report_node_rows: rows.length,
        install_paths: paths,
        unique_install_paths: new Set(paths).size,
        donut_row_count: donutRows.length,
        donut_classes: donut.classes || [],
        rows_with_donut_class: rowsWithDonutClass.length,
      };

      // ── Intercept every mutation route BEFORE the UI opens ──────────
      await page.route("**/manager/version", (route) =>
        route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ version: "probe" }) })
      );
      await page.route("**/customnode/installed", (route) =>
        route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({}) })
      );
      await page.route("**/customnode/getlist**", (route) =>
        route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ channel: "default", node_packs: {} }) })
      );
      await page.route("**/customnode/getmappings**", (route) =>
        route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({}) })
      );
      await page.route("**/externalmodel/getlist**", (route) =>
        route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ models: [] }) })
      );
      await page.route("**/manager/queue/install", (route) =>
        route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) })
      );
      await page.route("**/customnode/install/git_url", (route) =>
        route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) })
      );
      await page.route("**/manager/reboot", (route) =>
        route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) })
      );
      await page.route("**/comfymodal/models/batch-install", (route) =>
        route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) })
      );
      await page.route("**/comfymodal/models/rescan", (route) =>
        route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", summary: {} }) })
      );

      // ── UI: open the fixture workflow and select the donut version ──
      await openStudio(page, COMFYUI_URL);
      guard = installConsoleGuard(page);
      await page.locator('.comfymodal-studio-topnav [data-page="workflows"]').click();
      await expect(page.locator('[data-testid="workflows-page"]')).toBeVisible({ timeout: 20000 });

      const search = page.locator('[data-testid="workflows-search"]');
      await expect(search).toBeVisible({ timeout: 10000 });
      await search.fill(workflow.name || "");
      const card = page.locator(
        `[data-testid="workflow-card"][data-workflow-id="${FIXTURE_WORKFLOW_ID}"]`
      );
      await expect(card).toBeVisible({ timeout: 20000 });
      await card.click();
      await expect(page.locator('[data-testid="workflow-detail"]')).toBeVisible({ timeout: 15000 });

      const versionItem = page.locator(
        `[data-testid="version-item"][data-version-id="${FIXTURE_VERSION_ID}"]`
      );
      await expect(versionItem).toBeVisible({ timeout: 15000 });
      await versionItem.click();

      const nodeRows = page.locator('[data-testid="dependency-node-row"]');
      await expect(nodeRows.first()).toBeVisible({ timeout: 60000 });
      await expect
        .poll(() => nodeRows.count(), { timeout: 60000 })
        .toBe(rows.length);

      const domRows = await nodeRows.evaluateAll((elements) =>
        elements.map((el) => {
          const pathEl = el.querySelector(".comfymodal-studio-dependency-path");
          return {
            name: el.getAttribute("data-node-name") || "",
            path: pathEl ? pathEl.textContent || "" : "",
          };
        })
      );

      const domPaths = domRows.map((r) => normalizePath(r.path)).filter(Boolean);
      expect(
        new Set(domPaths).size,
        `duplicate DOM install_path rows: ${JSON.stringify(domPaths)}`
      ).toBe(domPaths.length);
      const domDonut = domRows.filter((r) => basenameOf(r.path) === DONUT_PACK_DIRNAME);
      expect(
        domDonut.length,
        `expected exactly one ${DONUT_PACK_DIRNAME} dependency row in the DOM`
      ).toBe(1);

      evidence.live.dom = {
        node_rows: domRows.length,
        install_paths: domPaths,
        unique_install_paths: new Set(domPaths).size,
        donut_row_count: domDonut.length,
        donut_row_name: domDonut[0].name,
        donut_row_path: domDonut[0].path,
      };

      guard.assertNoErrors([
        "Failed to load resource",
        "already registered",
        // Pre-existing host noise unrelated to the dependency section.
        "ComfyApp graph accessed before initialization",
        "vite:preloadError",
        "Failed to fetch dynamically imported module",
      ]);

      const evidencePath = testInfo.outputPath("dependency-pack-dedup-live-evidence.json");
      writeFileSync(evidencePath, JSON.stringify(evidence, null, 2));
      console.log("[dependency-pack-dedup-live] evidence:", evidencePath);
      console.log("[dependency-pack-dedup-live] summary:", JSON.stringify(evidence, null, 2));
    } finally {
      if (guard) guard.dispose();
    }
  });
});
