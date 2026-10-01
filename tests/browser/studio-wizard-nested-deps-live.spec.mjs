// Modal Studio — Live nested-dependency + remote-availability acceptance probe.
//
// Opt-in live test (COMFYMODAL_LIVE_E2E=1) against a real ComfyUI + Studio
// backend. It proves two product contracts at once:
//
//   1. Backend dependency-source fix: a WorkflowVersion carrying its own
//      top-level `graph_json` nodes must STILL merge the owning Workflow's
//      `static_graph`, because the parent graph records nested model loaders
//      (inside `definitions.subgraphs` / `extra.groupNodes`) the version
//      capture never contains.
//   2. Remote model-volume authority: GET /comfymodal/models (Modal
//      list_models_cpu) is the availability authority. A dependency row whose
//      remote entry has size > 0 reads Installed even when the local file is
//      an intentional 0-byte placeholder; a remote size of 0 stays Missing.
//      The local placeholder is preserved as secondary information only.
//
// The concrete acceptance fixture is the Krea upscale workflow. Naming the
// fixture workflow/model here is intentional; production code stays generic.
//
// Acceptance assertions (all derived from live data):
//   * `krea2_turbo_bf16.safetensors` appears in the live dependency report (and
//     in the wizard's Dependencies step) — it only lives in a parent nested
//     subgraph, so its presence proves the parent graph was merged.
//   * The wizard captures a live `/comfymodal/models` response, and the model
//     row state follows the remote nonzero size, NOT the local placeholder size.
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

/** Lowercased basename of a model reference. */
function basenameOf(name) {
  const value = String(name || "").replace(/\\/g, "/");
  return value.slice(value.lastIndexOf("/") + 1).toLowerCase();
}

/** Flatten the live folder-keyed /comfymodal/models payload into entries. */
function flattenRemoteInventory(payload) {
  const out = [];
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return out;
  for (const folder of Object.keys(payload)) {
    const entries = payload[folder];
    if (!Array.isArray(entries)) continue;
    for (const item of entries) {
      if (!item || typeof item !== "object") continue;
      if (typeof item.name !== "string" || !item.name) continue;
      out.push(item);
    }
  }
  return out;
}

// ── Suite ────────────────────────────────────────────────────────────────

test.describe("Studio wizard nested dependencies (live)", () => {
  test.skip(!LIVE_ENABLED, "Set COMFYMODAL_LIVE_E2E=1 to enable live tests");

  test("remote size is the model authority and the wizard resumes", async ({
    page,
    request,
  }, testInfo) => {
    let guard;
    const evidence = { live: {}, mock: {} };

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

      // Recompute the "effective" merge source the fixed route exposes.
      const { real: nestedReal, virtual: nestedVirtual } = classifyUnionNestedOnly([
        versionGraph,
        parentGraph,
      ]);

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

      // Core fix proof: the parent-only nested model is present.
      const nestedModel = models.find((m) => m.filename === NESTED_ONLY_MODEL);
      expect(
        nestedModel,
        `parent-only nested model '${NESTED_ONLY_MODEL}' missing from dependency report`
      ).toBeTruthy();

      // ── Remote model volume is the availability authority ───────────
      const modelsRes = await request.get(`${COMFYUI_URL}/comfymodal/models`);
      expect(modelsRes.ok()).toBeTruthy();
      const remotePayload = await modelsRes.json();
      const remoteEntries = flattenRemoteInventory(remotePayload);
      const remoteEntry = remoteEntries.find((e) => basenameOf(e.name) === basenameOf(NESTED_ONLY_MODEL));
      expect(
        remoteEntry,
        `remote model inventory has no entry for ${NESTED_ONLY_MODEL}`
      ).toBeTruthy();
      const remoteSize = Number(remoteEntry.size) || 0;
      const remoteAvailable = remoteSize > 0;
      const localPlaceholder = remoteEntry.local_placeholder || null;
      const localPlaceholderSize = localPlaceholder ? Number(localPlaceholder.size) || 0 : null;
      // Exact expected UI state: remote size decides, NOT the local placeholder.
      const expectedBadge = remoteAvailable ? "Installed" : "Missing";

      // Best-effort local library record (secondary evidence only — the local
      // store is not the authority and may legitimately have no record).
      let localRecord = null;
      try {
        const localRes = await request.get(
          `${COMFYUI_URL}/comfymodal/studio/models?search=${encodeURIComponent(NESTED_ONLY_MODEL)}`
        );
        if (localRes.ok()) {
          localRecord = (((await localRes.json()).models) || []).find(
            (m) => m.filename === NESTED_ONLY_MODEL
          ) || null;
        }
      } catch (e) { /* local record is not authoritative */ }

      evidence.live = {
        label: "live_remote_authority",
        workflow_id: workflowId,
        version_id: versionId,
        remote_entry_found: !!remoteEntry,
        remote_entry_size: remoteSize,
        remote_entry_folder: remoteEntry.folder || "",
        remote_available: remoteAvailable,
        local_placeholder: localPlaceholder,
        local_placeholder_size: localPlaceholderSize,
        local_record_found: !!localRecord,
        local_record_size: localRecord ? localRecord.size : null,
        local_record_is_placeholder: localRecord ? !!localRecord.is_placeholder : null,
        nested_model_report_state: nestedModel.state,
        expected_ui_badge: expectedBadge,
        nested_real_classes: [...nestedReal.keys()].sort(),
        nested_virtual_classes: [...nestedVirtual].sort(),
        report_model_count: models.length,
        report_node_rows: nodeRows.length,
        unresolvable_contains_virtuals: unresolvable
          .map((u) => u && u.name)
          .filter((name) => VIRTUAL_PANEL_CLASSES.includes(name)),
      };

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

      // ── Intercept mutations; dependency availability is server-owned ──
      const seen = { gitUrl: [], reboot: 0, modelInstallPayloads: [], queueInstall: [] };
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

      // The dependency response already carries the remote authority; the
      // wizard must render that row without fetching the inventory itself.
      expect(nestedModel.remote_available).toBe(remoteAvailable);
      expect(Number(nestedModel.remote_model && nestedModel.remote_model.size) || 0).toBe(remoteSize);
      evidence.live.wizard_captured_remote_size = Number(
        nestedModel.remote_model && nestedModel.remote_model.size
      ) || 0;

      // ── The nested row state follows remote size, not the placeholder ─
      const modelRows = panel.locator('[data-testid="dependency-model-row"]');
      await expect(modelRows.first()).toBeVisible({ timeout: 60000 });
      const nestedRow = modelRows.filter({ hasText: NESTED_ONLY_MODEL });
      await expect(nestedRow).toHaveCount(1);
      const nestedBadge = nestedRow.locator('[data-testid="dependency-model-state"]');
      await expect(nestedBadge).toHaveText(expectedBadge, { timeout: 180000 });
      evidence.live.ui_nested_model_badge = await nestedBadge.textContent();

      if (remoteAvailable) {
        // Secondary local detail is preserved beside the Installed state; the
        // model row offers no download action.
        const remoteDetail = nestedRow.locator('[data-testid="dependency-model-remote"]');
        await expect(remoteDetail).toContainText("remote", { timeout: 30000 });
        if (localPlaceholder && localPlaceholder.is_placeholder) {
          await expect(remoteDetail).toContainText("local placeholder 0 B", { timeout: 30000 });
        }
        await expect(nestedRow.locator('[data-testid="dependency-model-queue"]')).toHaveCount(0);
        await expect(nestedRow.locator('[data-testid="dependency-model-install-now"]')).toHaveCount(0);
        evidence.live.ui_nested_model_remote_detail = await remoteDetail.textContent();
      }

      // Virtual panels must never render as dependency rows.
      const nodeRowNames = await panel
        .locator('[data-testid="dependency-node-row"]')
        .evaluateAll((rows) =>
          rows.map((r) => (r.getAttribute("data-node-name") || "") + "|" + r.textContent)
        );
      evidence.live.virtual_panel_rows = [];
      for (const cls of VIRTUAL_PANEL_CLASSES) {
        const present = nodeRowNames.some((text) => text.includes(cls));
        if (present) evidence.live.virtual_panel_rows.push(cls);
        expect(present, `virtual panel '${cls}' must not be a dependency row`).toBe(false);
      }

      // ── Reload on the Dependencies step resumes the same wizard ─────
      await page.reload({ waitUntil: "domcontentloaded" });
      await expect
        .poll(() => page.evaluate(() => typeof window.open_testing_modal === "function"), {
          timeout: 30000,
        })
        .toBe(true);
      evidence.live.reload_hash = await page.evaluate(() => window.location.hash);
      await page.evaluate(() => window.open_testing_modal());
      await expect(page.locator('[data-testid="studio-page"]')).toBeVisible({ timeout: 30000 });
      await expect(panel.locator('[data-testid="wizard-dependencies-continue"]')).toBeVisible({
        timeout: 60000,
      });
      evidence.live.resumed_step = "dependencies";

      // ── Queue-state subcase (deterministic mock route override) ─────
      // A remote-missing model (not in the remote inventory) keeps its Queue
      // install action; holding the request leaves "Queued for download".
      const mockDeps = {
        status: "ok",
        version_id: versionId,
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
        new RegExp(`/comfymodal/studio/workflows/versions/${versionId}/dependencies$`),
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
      await expect(mockRow).toHaveCount(1, { timeout: 30000 });
      const queueBtn = mockRow.locator('[data-testid="dependency-model-queue"]');
      await expect(queueBtn).toBeVisible();
      await queueBtn.click();
      await expect(
        mockRow.locator('[data-testid="dependency-model-state"]')
      ).toHaveText("Queued for download", { timeout: 10000 });

      evidence.mock = {
        label: "mock_route_override",
        reason:
          "a remote-missing model keeps its queue action; the dependencies response is overridden so the queue badge is deterministic",
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
