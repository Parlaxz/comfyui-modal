// Phase I3 — Shared UI primitives foundation (fake E2E).
//
// Permanent product coverage for the frozen I3 contract:
//   A. generic :focus-visible fallback visibly covers previously weak
//      keyboard families across THREE different page domains (workflow
//      tag-chip remove button, model-library row link, recent-runs carousel
//      Clear/close control), pointer activation produces NO permanent ring,
//      and focused controls show exactly one outline source (no double ring)
//   B. primitive DOM semantics mounted from the REAL modules in the REAL
//      browser environment: renderLoadingState status/live/spinner/label +
//      normalization, shared spinner keyframe resolution, generic copy-free
//      empty state, and the migrated statusBadge carrying live shared-chip
//      geometry
//   C. chip family separation: portability vs compatibility stay visually
//      distinct under identical tone while sharing pill geometry
//
// Component-runtime validation only — production pages are NOT modified to
// make this suite possible.

import { test, expect } from "@playwright/test";
import {
  setupFakeTest,
  seedHistory,
} from "./helpers.mjs";

const MODAL = ".comfymodal-studio-modal";
// The shell's own page container hosts every page surface in both the
// production dialog and the standalone fake harness.
const PAGE_HOST = '[data-testid="studio-page"]';

/** True when the currently focused element matches `selector`. */
async function activeMatches(page, selector) {
  return page.evaluate((sel) => {
    const el = document.activeElement;
    return !!el && typeof el.matches === "function" && el.matches(sel);
  }, selector);
}

/** Keyboard-walk (real Tab presses) until focus lands on `selector`. */
async function walkTo(page, selector, maxTabs = 220) {
  if (await activeMatches(page, selector)) return true;
  for (let i = 0; i < maxTabs; i++) {
    await page.keyboard.press("Tab");
    if (await activeMatches(page, selector)) return true;
  }
  return false;
}

/** Computed focus indication of the active element. */
async function focusRing(page) {
  return page.evaluate(() => {
    const cs = getComputedStyle(document.activeElement);
    return {
      width: cs.outlineWidth,
      style: cs.outlineStyle,
      color: cs.outlineColor,
      shadow: cs.boxShadow,
      tag: document.activeElement.tagName,
      label:
        document.activeElement.getAttribute("aria-label") ||
        (document.activeElement.textContent || "").trim().slice(0, 24),
    };
  });
}

test.describe("I3 shared UI primitives foundation", () => {
  test("A. focus-visible fallback covers three weak families; pointer gets no ring", async ({
    page,
  }) => {
    // Seed durable history BEFORE mount so the Playground recent-runs
    // carousel hydrates and its Clear/close controls render.
    const t = await setupFakeTest(page, {
      beforeMount: async ({ page: p, sessionId }) => {
        await seedHistory(p, sessionId, "history_v2_large");
      },
    });

    // ── Pointer contract FIRST (before any keyboard interaction):
    // mouse activation must not produce a permanent always-on ring. ──
    await page.locator(`.comfymodal-studio-topnav button[data-page="workflows"]`).click();
    const pointerRing = await focusRing(page);
    expect(pointerRing.style, "pointer focus must not create an outline ring").toBe("none");

    const proven = [];

    // ── Family 1: model-library row control (Workflows → Models). ──
    await t.gotoPage("workflows");
    await page.locator('[data-testid="wf-subnav-models"]').click();
    await expect(page.locator('[data-testid="models-page"]')).toBeVisible({ timeout: 10000 });
    let ok = await walkTo(page, '[data-testid="models-page"] a');
    if (ok) {
      const ring = await focusRing(page);
      expect(ring.width).toBe("2px");
      expect(ring.style).not.toBe("none");
      proven.push(`model-library-link (${ring.label})`);
    }

    // ── Family 2: recent-runs carousel Clear/close control (Playground). ──
    await t.gotoPage("playground");
    ok = await walkTo(page, ".comfymodal-studio-carousel-btn");
    if (ok) {
      const ring = await focusRing(page);
      expect(ring.width).toBe("2px");
      expect(ring.style).not.toBe("none");
      // Double-ring audit on this weak-family representative: the fallback
      // outline is the ONE ring — no box-shadow duplication beneath it.
      expect(ring.shadow).toBe("none");
      proven.push(`carousel-clear-close (${ring.label})`);
    }

    // ── Family 3 (LAST): workflow tag-chip remove button in the workflow
    // DETAIL view, where editable tag chips render. ──
    await t.gotoPage("workflows");
    // If the Workflows surface reopened in Model Library mode (persisted
    // module state), take its own back control to the library first.
    const modelsBack = page.locator('[data-testid="models-back"]');
    if (await modelsBack.count()) {
      await modelsBack.click();
    }
    await expect(page.locator('[data-testid="workflow-card"]').first()).toBeVisible({ timeout: 15000 });
    await page.locator('[data-testid="workflow-card"][data-workflow-id="wf_text2img"]').click();
    await expect(page.locator('[data-testid="workflow-detail-tags"]')).toBeVisible({ timeout: 10000 });
    ok = await walkTo(page, '.comfymodal-studio-wf-chip .chip-x');
    if (ok) {
      const ring = await focusRing(page);
      expect(ring.width).toBe("2px");
      expect(ring.style).not.toBe("none");
      proven.push(`workflow-tag-chip-remove (${ring.label})`);
    }

    // At least three distinct previously-weak families must be proven.
    expect(proven.length, `proven weak families: ${proven.join("; ")}`).toBeGreaterThanOrEqual(3);

    console.log("I3 focus fallback proven families:", proven.join(" | "));
  });

  test("B. primitive DOM semantics: loading, empty state, shared-chip badge", async ({
    page,
  }) => {
    await setupFakeTest(page);

    const facts = await page.evaluate(async () => {
      const out = {};
      const loadingMod = await import("/extensions/comfymodal-modal/studio-loading.js");
      const uiMod = await import("/extensions/comfymodal-modal/studio-ui.js");

      const host = document.createElement("div");
      host.id = "i3-fixture";
      document.querySelector('[data-testid="studio-page"]').appendChild(host);

      // ── renderLoadingState: frozen semantics ──
      const loading = loadingMod.renderLoadingState({ label: "Fetching history…", size: "inline", testid: "i3-loading" });
      host.appendChild(loading);
      const lcs = getComputedStyle(loading);
      out.loading = {
        cls: loading.classList.contains("cm-loading"),
        size: loading.getAttribute("data-size"),
        role: loading.getAttribute("role"),
        live: loading.getAttribute("aria-live"),
        busy: loading.hasAttribute("aria-busy"),
        testid: loading.getAttribute("data-testid"),
        labelText: loading.querySelector(".cm-loading-label").textContent,
        labelVisible: loading.querySelector(".cm-loading-label").getBoundingClientRect().height > 0,
        spinnerHidden: loading.querySelector(".cm-loading-spinner").getAttribute("aria-hidden") === "true",
        display: lcs.display,
      };

      // Spinner resolves the SINGLE shared keyframe at runtime.
      out.spinnerAnimation = getComputedStyle(loading.querySelector(".cm-loading-spinner")).animationName;

      // Normalization: blank label, unknown size, non-string testid.
      const junk = loadingMod.renderLoadingState({ label: "", size: "nope", testid: 99 });
      out.normalized = {
        size: junk.getAttribute("data-size"),
        label: junk.querySelector(".cm-loading-label").textContent,
        hasTestid: junk.hasAttribute("data-testid"),
      };

      // ── Generic empty state: caller-supplied copy only ──
      const actionBtn = document.createElement("button");
      actionBtn.type = "button";
      actionBtn.textContent = "Take snapshot";
      window.__i3Action = actionBtn;
      const empty = uiMod.renderEmptyState({
        title: "No snapshots yet",
        detail: "Capture one from the graph.",
        action: actionBtn,
        testid: "i3-empty",
      });
      host.appendChild(empty);
      out.empty = {
        cls: empty.classList.contains("cm-empty-state"),
        testid: empty.getAttribute("data-testid"),
        role: empty.getAttribute("role"),
        live: empty.getAttribute("aria-live"),
        titleClass: empty.querySelector(".cm-empty-state-title")?.className || "",
        titleText: empty.querySelector(".cm-empty-state-title")?.textContent || "",
        detailText: empty.querySelector(".cm-empty-state-detail")?.textContent || "",
        headingTags: empty.querySelectorAll("h1,h2,h3,h4,h5,h6").length,
        actionIdentity: empty.querySelector(".cm-empty-state-action").firstChild === window.__i3Action,
        bakedCopy:
          empty.textContent.includes("legacy discovery") ||
          empty.textContent.includes("No workflows") ||
          empty.textContent.includes("No models"),
      };

      // ── Migrated statusBadge: legacy classes + LIVE shared geometry ──
      const badge = uiMod.renderEmptyState ? uiMod.statusBadge("READY", "ok") : null;
      host.appendChild(badge);
      const bcs = getComputedStyle(badge);
      out.badge = {
        classes: badge.className,
        tone: badge.getAttribute("data-tone"),
        radius: bcs.borderRadius,
        display: bcs.display,
        fontSize: bcs.fontSize,
      };
      return out;
    });

    expect(facts.loading).toMatchObject({
      cls: true,
      size: "inline",
      role: "status",
      live: "polite",
      busy: false,
      testid: "i3-loading",
      labelText: "Fetching history…",
      labelVisible: true,
      spinnerHidden: true,
      display: "flex",
    });
    // One spinner implementation: the loader animates via comfymodal-spin.
    expect(facts.spinnerAnimation).toBe("comfymodal-spin");

    expect(facts.normalized).toEqual({ size: "page", label: "Loading…", hasTestid: false });

    expect(facts.empty.cls).toBe(true);
    expect(facts.empty.testid).toBe("i3-empty");
    expect(facts.empty.role).toBe(null);
    expect(facts.empty.live).toBe(null);
    expect(facts.empty.titleClass).toContain("cm-empty-state-title");
    expect(facts.empty.titleText).toBe("No snapshots yet");
    expect(facts.empty.detailText).toBe("Capture one from the graph.");
    expect(facts.empty.headingTags).toBe(0);
    expect(facts.empty.actionIdentity).toBe(true);
    expect(facts.empty.bakedCopy).toBe(false);

    // Shared-chip geometry is ACTIVE on the migrated badge.
    expect(facts.badge.classes).toContain("comfymodal-studio-status-badge");
    expect(facts.badge.classes).toContain("ok");
    expect(facts.badge.classes).toContain("cm-chip");
    expect(facts.badge.tone).toBe("ok");
    expect(facts.badge.radius).toBe("999px");
    expect(facts.badge.display).toBe("inline-flex");
    expect(facts.badge.fontSize).toBe("10px");
  });

  test("C. chip families stay distinct; single spinner keyframe at runtime", async ({
    page,
  }) => {
    await setupFakeTest(page);

    const facts = await page.evaluate(async () => {
      const host = document.createElement("div");
      host.id = "i3-fixture-c";
      document.querySelector('[data-testid="studio-page"]').appendChild(host);

      const mk = (cls, tone) => {
        const s = document.createElement("span");
        s.className = cls;
        s.setAttribute("data-tone", tone);
        s.textContent = "x";
        host.appendChild(s);
        return s;
      };
      const port = mk("cm-chip cm-chip--portability", "ok");
      const compat = mk("cm-chip cm-chip--compatibility", "ok");

      const pcs = getComputedStyle(port);
      const ccs = getComputedStyle(compat);
      return {
        sameGeometry: pcs.borderRadius === ccs.borderRadius && pcs.borderRadius === "999px",
        distinctBackground: pcs.backgroundColor !== ccs.backgroundColor,
        portBg: pcs.backgroundColor,
        compatBg: ccs.backgroundColor,
        keyframes: (() => {
          const names = [];
          for (const sheet of document.styleSheets) {
            let rules;
            try {
              rules = sheet.cssRules;
            } catch (e) {
              continue;
            }
            for (const rule of rules) {
              if (rule.type === CSSRule.KEYFRAMES_RULE) names.push(rule.name);
            }
          }
          return names;
        })(),
      };
    });

    expect(facts.sameGeometry, "both families share the pill geometry").toBe(true);
    expect(
      facts.distinctBackground,
      `portability=${facts.portBg} compatibility=${facts.compatBg} must stay distinct`
    ).toBe(true);

    // Exactly one spinner keyframe ships; the duplicate alias is gone.
    expect(facts.keyframes).toContain("comfymodal-spin");
    expect(facts.keyframes).not.toContain("cm-exp-spin");
  });
});
