// Modal Studio — Live nested-dependency acceptance probe.
//
// Opt-in live test (COMFYMODAL_LIVE_E2E=1) against a real ComfyUI + Studio
// backend. It proves the backend dependency-source fix: a WorkflowVersion
// carrying its own top-level `graph_json` nodes must STILL merge the owning
// Workflow's `static_graph`, because the parent graph records nested model
// loaders and UI-only / Manager-missing node classes the version capture never
// contains (inside `definitions.subgraphs` / `extra.groupNodes`).
//
// The concrete acceptance fixture is the Krea upscale workflow. Naming the
// fixture workflow here is intentional; production code stays generic.
//
// Acceptance assertions (all derived from live data):
//   * The Model Library is reconciled with disk first (POST models/rescan), so
//     a real file in any canonical model folder — including models/unet — is
//     represented by a record. That reconciliation is a scan, not a download.
//   * `krea2_turbo_bf16.safetensors` appears in the live dependency report (and
//     in the wizard's Dependencies step) — it only lives in a parent nested
//     subgraph, so its presence proves the parent graph was merged. Its state
//     must agree with the local model-library record: Installed for a real
//     nonzero file, Missing for a zero-byte placeholder.
//   * DonutLatestPreview / DonutModelDownloads / DonutWorkflowPanel never appear
//     as dependency rows (frontend-only virtual panels).
//   * A browser reload while on the Dependencies step resumes the same wizard at
//     the same step (bounded draft + URL marker).
//   * Holding the model queue request leaves the visible badge reading exactly
//     "Queued for download" (mock route override; labelled as mock evidence).
//
// Every Manager / model mutation route is intercepted and fulfilled locally.
// Nothing is installed or rebooted.

import { writeFileSync } from "node:fs";
import { test, expect } from "@playwright/test";
import { installConsoleGuard, openStudio } from "./studio-fixtures.mjs";

const LIVE_ENABLED = process.env.COMFYMODAL_LIVE_E2E === "1";
const COMFYUI_URL = process.env.COMFYUI_URL || "http://127.0.0.1:8188";

// Concrete acceptance fixture (see header).
const FIXTURE_WORKFLOW_NAME = "krea2TurboWorkflowUpscale_v40Beta";
const FIXTURE_WORKFLOW_ID = "wf_7cbe640f042f4a3e";
const NESTED_ONLY_MODEL = "krea2_turbo_bf16.safetensors";
const VIRTUAL_PANEL_CLASSES = [
  "DonutLatestPreview",
  "DonutModelDownloads",
  "DonutWorkflowPanel",
];

const IDENTIFIER_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;

// Report state -> the exact state badge text rendered by the wizard.
const STATE_BADGE_TEXT = {
  installed: "Installed",
  missing: "Missing",
  wrong_version: "Wrong version",
  unknown: "Unknown",
};

// ── Generic recursive graph walk (mirrors the production iterator) ───────

function isGraphNode(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const nodeType = value.type;
  const classType = value.class_type;
  const hasType = typeof nodeType === "string" && nodeType.trim() !== "";
  const hasClassType = typeof classType === "string" && classType.trim() !== "";
  if (!hasType && !hasClassType) return false;
  const inputs = value.inputs;
  if (
    hasClassType &&
    !hasType &&
    inputs &&
    typeof inputs === "object" &&
    !Array.isArray(inputs)
  ) {
    return true; // API-format node
  }
  if ("origin_id" in value || "target_id" in value) return false; // link row
  if (value.properties && typeof value.properties === "object" && !Array.isArray(value.properties)) {
    return true;
  }
  if ("widgets_values" in value || "widgets_values_named" in value || "widgetsValuesNamed" in value) {
    return true;
  }
  return Array.isArray(inputs) && Array.isArray(value.outputs);
}

function walkGraphNodes(root) {
  const out = [];
  const seen = new Set();
  const stack = [root];
  while (stack.length) {
    const current = stack.pop();
    if (!current || typeof current !== "object") continue;
    if (seen.has(current)) continue;
    seen.add(current);
    if (Array.isArray(current)) {
      for (const item of current) stack.push(item);
      continue;
    }
    if (isGraphNode(current)) out.push(current);
    for (const key of Object.keys(current)) stack.push(current[key]);
  }
  return out;
}

function identityOf(node) {
  const props = node && node.properties;
  if (!props || typeof props !== "object") return "";
  const cnr = typeof props.cnr_id === "string" ? props.cnr_id.trim() : "";
  const aux = typeof props.aux_id === "string" ? props.aux_id.trim() : "";
  return cnr || aux || "";
}

function isNonEmptyCollection(value) {
  return !!value && typeof value === "object" && Object.keys(value).length > 0;
}

/**
 * Nested-only classes across a UNION of graphs (version graph + parent graph).
 * A class is nested-only when no top-level node of either graph declares it.
 * Real = carries pack identity or a non-empty inputs/outputs slot.
 */
function classifyUnionNestedOnly(graphs) {
  const topLevelTypes = new Set();
  for (const graph of graphs) {
    for (const n of (graph && Array.isArray(graph.nodes) ? graph.nodes : [])) {
      if (isGraphNode(n) && typeof n.type === "string" && n.type) topLevelTypes.add(n.type);
    }
  }
  const real = new Map(); // class -> identity
  const virtual = new Set();
  for (const graph of graphs) {
    for (const node of walkGraphNodes(graph)) {
      const cls = node.type;
      if (typeof cls !== "string" || !cls || topLevelTypes.has(cls)) continue;
      if (!IDENTIFIER_RE.test(cls)) continue; // UUID subgraph proxies are artifacts
      const identity = identityOf(node);
      if (identity || isNonEmptyCollection(node.inputs) || isNonEmptyCollection(node.outputs)) {
        if (!real.has(cls)) real.set(cls, identity);
        virtual.delete(cls);
      } else if (!real.has(cls)) {
        virtual.add(cls);
      }
    }
  }
  return { real, virtual };
}

// ── Suite ────────────────────────────────────────────────────────────────

test.describe("Studio wizard nested dependencies (live)", () => {
  test.skip(!LIVE_ENABLED, "Set COMFYMODAL_LIVE_E2E=1 to enable live tests");

  test("version graph merges parent nested deps and the wizard resumes", async ({
    page,
    request,
  }, testInfo) => {
    let guard;
    const evidence = {
      live: {},
      mock: {},
    };

    try {
      // ── Live backend discovery ───────────────────────────────────────
      const listRes = await request.get(`${COMFYUI_URL}/comfymodal/studio/workflows`);
      expect(listRes.ok()).toBeTruthy();
      const workflows = ((await listRes.json()).workflows) || [];
      const fixture =
        workflows.find((w) => w.workflow_id === FIXTURE_WORKFLOW_ID) ||
        workflows.find((w) => w.name === FIXTURE_WORKFLOW_NAME);
      expect(fixture, "acceptance fixture workflow not found in live store").toBeTruthy();
      const workflowId = fixture.workflow_id;
      const versionId = fixture.latest_version_id || "";
      expect(versionId, "fixture workflow has no latest version").toBeTruthy();

      const detailRes = await request.get(
        `${COMFYUI_URL}/comfymodal/studio/workflows/${encodeURIComponent(workflowId)}`
      );
      expect(detailRes.ok()).toBeTruthy();
      const workflow = (await detailRes.json()).workflow || {};

      const ctxRes = await request.get(
        `${COMFYUI_URL}/comfymodal/studio/workflows/${encodeURIComponent(
          workflowId
        )}/run-context?version_id=${encodeURIComponent(versionId)}`
      );
      expect(ctxRes.ok()).toBeTruthy();
      const versionGraph = ((await ctxRes.json()).version || {}).graph_json || {};
      const parentGraph = workflow.static_graph || {};

      // Reconcile the Model Library with disk before resolving. The
      // dependency resolver reads records only (it never scans), and the
      // real unet file is not a synthetic fixture: it must be represented by
      // a real scan for its row to derive Installed. This is a reconciliation
      // read of the models tree, not a download or install.
      const rescanRes = await request.post(
        `${COMFYUI_URL}/comfymodal/studio/models/rescan`,
        { data: {} }
      );
      expect(rescanRes.ok()).toBeTruthy();
      const rescanSummary = (await rescanRes.json()).summary || {};

      // Recompute the "effective" merge source the fixed route exposes.
      const sourceGraphs = [versionGraph, parentGraph];
      const { real: nestedReal, virtual: nestedVirtual } = classifyUnionNestedOnly(sourceGraphs);

      const depsRes = await request.get(
        `${COMFYUI_URL}/comfymodal/studio/workflows/versions/${encodeURIComponent(
          versionId
        )}/dependencies`
      );
      expect(depsRes.ok()).toBeTruthy();
      const deps = await depsRes.json();
      const models = Array.isArray(deps.models) ? deps.models : [];
      const nodeRows = Array.isArray(deps.custom_nodes) ? deps.custom_nodes : [];
      const unresolvable = Array.isArray(deps.unresolvable) ? deps.unresolvable : [];

      // The local model-library record is authoritative for the expected state.
      // It must exist: an installed (or placeholder) real file in any canonical
      // model folder, including models/unet, is reconciled into the library.
      const localRes = await request.get(
        `${COMFYUI_URL}/comfymodal/studio/models?search=${encodeURIComponent(NESTED_ONLY_MODEL)}`
      );
      expect(localRes.ok()).toBeTruthy();
      const localRecords = ((await localRes.json()).models) || [];
      const localRecord = localRecords.find((m) => m.filename === NESTED_ONLY_MODEL);
      expect(
        localRecord,
        `model library has no record for ${NESTED_ONLY_MODEL} after rescan`
      ).toBeTruthy();
      const localInstalled = !!(localRecord && localRecord.installed);
      const localIsPlaceholder = !!(localRecord && localRecord.is_placeholder);

      // Core fix proof: the parent-only nested model is present.
      const nestedModel = models.find((m) => m.filename === NESTED_ONLY_MODEL);
      expect(
        nestedModel,
        `parent-only nested model '${NESTED_ONLY_MODEL}' missing from dependency report`
      ).toBeTruthy();

      evidence.live = {
        label: "live",
        workflow_id: workflowId,
        version_id: versionId,
        rescan_summary: rescanSummary,
        local_record_found: !!localRecord,
        local_record_installed: localInstalled,
        local_record_is_placeholder: localIsPlaceholder,
        local_record_size: localRecord ? localRecord.size : null,
        local_record_folder: localRecord ? localRecord.folder : null,
        nested_model_state: nestedModel.state,
        nested_real_classes: [...nestedReal.keys()].sort(),
        nested_virtual_classes: [...nestedVirtual].sort(),
        report_model_count: models.length,
        report_node_rows: nodeRows.length,
        report_classes: [...new Set(nodeRows.flatMap((r) => r.classes || []))].sort(),
        virtual_panel_rows: [],
        unresolvable_contains_virtuals: unresolvable
          .map((u) => u && u.name)
          .filter((name) => VIRTUAL_PANEL_CLASSES.includes(name)),
      };

      // State contract: an existing nonzero file resolves Installed; a 0-byte
      // placeholder (the live repo carries one) resolves Missing. Either way
      // the report must agree with the authoritative library record.
      if (localInstalled) {
        expect(nestedModel.state).toBe("installed");
      } else {
        expect(
          localIsPlaceholder,
          "record is neither installed nor a zero-byte placeholder"
        ).toBe(true);
        expect(nestedModel.state).toBe("missing");
      }

      // Generic nested-only real classes must have resolved from the union.
      const reportClasses = new Set(nodeRows.flatMap((row) => row.classes || []));
      const missingNested = [...nestedReal.keys()].filter((cls) => !reportClasses.has(cls));
      expect(
        missingNested,
        `nested classes missing from dependency report: ${missingNested.join(", ")}`
      ).toEqual([]);
      for (const cls of nestedVirtual) {
        expect(
          reportClasses.has(cls),
          `nested virtual panel '${cls}' must never be a dependency row`
        ).toBe(false);
      }

      // ── Intercept every mutation route BEFORE the UI opens ──────────
      const seen = { gitUrl: [], reboot: 0, modelInstallPayloads: [], queueInstall: [] };
      await page.route("**/manager/version", (route) =>
        route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ version: "probe" }) })
      );
      await page.route("**/customnode/installed", (route) =>
        route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({}) })
      );
      await page.route("**/customnode/getlist**", (route) =>
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ channel: "default", node_packs: {} }),
        })
      );
      await page.route("**/customnode/getmappings**", (route) =>
        route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({}) })
      );
      await page.route("**/externalmodel/getlist**", (route) =>
        route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ models: [] }) })
      );
      await page.route("**/manager/queue/install", (route) => {
        seen.queueInstall.push(route.request().postDataJSON());
        return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
      });
      await page.route("**/manager/queue/start", (route) =>
        route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) })
      );
      await page.route("**/customnode/install/git_url", (route) => {
        seen.gitUrl.push(route.request().postDataJSON());
        return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
      });
      await page.route("**/manager/reboot", (route) => {
        seen.reboot += 1;
        return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
      });
      // Model mutation routes are never reached by the live phase; intercept
      // them so no bytes are ever fetched.
      await page.route("**/comfymodal/models/batch-install", (route) =>
        route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) })
      );
      await page.route("**/comfymodal/models/rescan", (route) =>
        route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", summary: {} }) })
      );

      // ── UI: open the fixture workflow's setup wizard ────────────────
      await openStudio(page, COMFYUI_URL);
      guard = installConsoleGuard(page);
      await page.locator('.comfymodal-studio-topnav [data-page="workflows"]').click();
      await expect(page.locator('[data-testid="workflows-page"]')).toBeVisible({ timeout: 20000 });

      const search = page.locator('[data-testid="workflows-search"]');
      await expect(search).toBeVisible({ timeout: 10000 });
      await search.fill(workflow.name || FIXTURE_WORKFLOW_NAME);

      const card = page.locator(
        `[data-testid="workflow-card"][data-workflow-id="${workflowId}"]`
      );
      await expect(card).toBeVisible({ timeout: 20000 });
      await card.click();
      await expect(page.locator('[data-testid="workflow-detail"]')).toBeVisible({ timeout: 15000 });
      await page.locator('[data-testid="mapping-setup-button"]').click();
      const panel = page.locator(".comfymodal-studio-wizard-panel");
      await expect(panel).toBeVisible({ timeout: 15000 });

      await panel.locator(".comfymodal-studio-wizard-feature-card").first().click();
      await panel.locator('[data-testid="wizard-features-continue"]').click();
      await expect(panel.locator('[data-testid="wizard-dependencies-continue"]')).toBeVisible({
        timeout: 20000,
      });

      // ── The nested parent-only model must be rendered in the UI ─────
      const modelRows = panel.locator('[data-testid="dependency-model-row"]');
      await expect(modelRows.first()).toBeVisible({ timeout: 30000 });
      const nestedRow = modelRows.filter({ hasText: NESTED_ONLY_MODEL });
      await expect(nestedRow).toHaveCount(1);
      const nestedBadge = nestedRow.locator('[data-testid="dependency-model-state"]');
      await expect(nestedBadge).toHaveText(STATE_BADGE_TEXT[nestedModel.state] || "Unknown");
      if (localInstalled) {
        await expect(nestedBadge).toHaveText("Installed");
      }
      evidence.live.ui_nested_model_badge = await nestedBadge.textContent();

      // Virtual panels must never render as dependency rows.
      const nodeRowNames = await panel
        .locator('[data-testid="dependency-node-row"]')
        .evaluateAll((rows) =>
          rows.map((r) => (r.getAttribute("data-node-name") || "") + "|" + r.textContent)
        );
      for (const cls of VIRTUAL_PANEL_CLASSES) {
        const present = nodeRowNames.some((text) => text.includes(cls));
        if (present) evidence.live.virtual_panel_rows.push(cls);
        expect(present, `virtual panel '${cls}' must not be a dependency row`).toBe(false);
      }
      expect(evidence.live.virtual_panel_rows).toEqual([]);

      // ── Reload on the Dependencies step resumes the same wizard ─────
      await page.reload({ waitUntil: "domcontentloaded" });
      await expect
        .poll(() => page.evaluate(() => typeof window.open_testing_modal === "function"), {
          timeout: 30000,
        })
        .toBe(true);
      evidence.live.reload_hash = await page.evaluate(() => window.location.hash);
      evidence.live.reload_draft = await page.evaluate(() => {
        try {
          return sessionStorage.getItem("comfymodal.studio.wizard.draft.v1");
        } catch (e) {
          return null;
        }
      });
      await page.evaluate(() => window.open_testing_modal());
      await expect(page.locator('[data-testid="studio-page"]')).toBeVisible({ timeout: 30000 });
      evidence.live.mounted_hash = await page.evaluate(() => window.location.hash);
      console.log(
        "[nested-deps-live] reload diagnostics:",
        JSON.stringify({
          reload_hash: evidence.live.reload_hash,
          reload_draft: evidence.live.reload_draft,
          mounted_hash: evidence.live.mounted_hash,
        })
      );
      await expect(panel.locator('[data-testid="wizard-dependencies-continue"]')).toBeVisible({
        timeout: 30000,
      });
      evidence.live.resumed_step = "dependencies";
      evidence.live.resumed_after_reload = true;

      // ── Queue-state subcase (deterministic mock route override) ─────
      // The live nested model has no local library source URL, so it exposes no
      // "Queue install" action. Exercise the queue badge contract with a
      // deterministic dependencies override instead; everything else (click,
      // in-flight tracking, badge) runs through the live UI.
      const mockVersionId = versionId;
      const mockDeps = {
        status: "ok",
        version_id: mockVersionId,
        models: [
          {
            key: "unet|mock_hold_model.safetensors",
            role: "unet",
            filename: "mock_hold_model.safetensors",
            state: "missing",
            folder: "unet",
            source_urls: ["https://example.invalid/mock_hold_model.safetensors"],
            installed: false,
          },
        ],
        custom_nodes: [],
        unresolvable: [],
        summary: { installed: 0, missing: 1, wrong_version: 0, unknown: 0, attention: 1, ready: false },
      };
      await page.route(
        new RegExp(
          `/comfymodal/studio/workflows/versions/${mockVersionId}/dependencies$`
        ),
        (route) =>
          route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify(mockDeps),
          })
      );
      // Hold the queue request open so the badge cannot be replaced.
      await page.route("**/comfymodal/model/install", (route) => {
        seen.modelInstallPayloads.push(route.request().postDataJSON());
        // Intentionally never fulfilled: holds the in-flight "queued" state.
      });

      await panel.locator('[data-testid="wizard-dependencies-refresh"]').click();
      const mockRow = panel
        .locator('[data-testid="dependency-model-row"]')
        .filter({ hasText: "mock_hold_model.safetensors" });
      await expect(mockRow).toHaveCount(1, { timeout: 20000 });
      const queueBtn = mockRow.locator('[data-testid="dependency-model-queue"]');
      await expect(queueBtn).toBeVisible();
      await queueBtn.click();
      await expect(
        mockRow.locator('[data-testid="dependency-model-state"]')
      ).toHaveText("Queued for download", { timeout: 10000 });

      evidence.mock = {
        label: "mock_route_override",
        reason:
          "live nested model has no local library source URL, so the queue action is exercised with a deterministic dependencies response",
        queue_badge: "Queued for download",
        model_install_payloads: seen.modelInstallPayloads,
      };

      // No mutation ever left the page.
      expect(seen.gitUrl, "install must never fall back to the git_url route").toEqual([]);
      expect(seen.reboot, "probe must never reboot ComfyUI").toBe(0);
      expect(seen.queueInstall, "no custom-node install may fire").toEqual([]);
      guard.assertNoErrors([
        "Failed to load resource",
        "already registered",
        // Pre-existing host noise unrelated to this wizard: an Impact-Pack
        // chunk fails to dynamic-import, and ComfyUI reads ComfyApp before its
        // graph is initialized. Neither originates in the Studio flow under
        // test, so they are explicitly excluded rather than silently masked.
        "ComfyApp graph accessed before initialization",
        "vite:preloadError",
        "Failed to fetch dynamically imported module",
      ]);

      const evidencePath = testInfo.outputPath("nested-deps-live-evidence.json");
      writeFileSync(evidencePath, JSON.stringify(evidence, null, 2));
      console.log("[nested-deps-live] evidence:", evidencePath);
      console.log("[nested-deps-live] summary:", JSON.stringify(evidence, null, 2));
    } finally {
      if (guard) guard.dispose();
    }
  });
});
