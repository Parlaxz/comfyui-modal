// Phase I3 — Shared UI primitives foundation unit tests.
//
// Deterministic Node tests: no browser, no network, no GPU, no live
// generation. Uses the house DOM stub pattern (cf.
// studio_phase_i2_shell_nav_accessibility_unit.mjs) and imports the REAL
// production modules (web/studio-loading.js, web/studio-ui.js) plus
// source-text contracts for web/studio-styles.js.
//
// Covered I3 contracts (PHASE_I1 freeze; PHASE_I3 report):
//   Loading    — frozen renderLoadingState API + deterministic input
//                normalization + decorative spinner semantics
//   Chips      — shared .cm-chip base + data-tone system + distinct
//                portability/compatibility family hooks + live statusBadge
//                migration preserving legacy classes
//   Focus      — frozen generic :focus-visible fallback with accent token,
//                no broad :focus replacement
//   EmptyState — generic copy-free primitive (no baked-in legacy domain
//                copy, no auto heading/alert/live), CSS base present
//   Scope      — image-viewer helpers untouched, non-History page loading/
//                chip/empty-state call sites unmigrated (History consumed
//                them in I4), no routing/BroadcastChannel/Compare additions

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const WEB = path.join(ROOT, "web");
const readWeb = (name) => fs.readFileSync(path.join(WEB, name), "utf8");

function section(name) {
  console.log("PASS: " + name);
}

// ── DOM / browser-environment stubs (house pattern, minimal) ──────────────

function makeNode(tag) {
  let ownText = "";
  const node = {
    tagName: String(tag || "div").toUpperCase(),
    children: [],
    parentNode: null,
    attributes: {},
    dataset: {},
    style: {},
    className: "",
    appendChild(child) {
      child.parentNode = this;
      this.children.push(child);
      return child;
    },
    removeChild(child) {
      const i = this.children.indexOf(child);
      if (i !== -1) this.children.splice(i, 1);
      child.parentNode = null;
      return child;
    },
    get firstChild() {
      return this.children.length ? this.children[0] : null;
    },
    setAttribute(name, v) {
      this.attributes[name] = String(v);
      if (name.startsWith("data-")) {
        const key = name.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase());
        this.dataset[key] = String(v);
      }
    },
    getAttribute(name) {
      return name in this.attributes ? this.attributes[name] : null;
    },
    hasAttribute(name) {
      return name in this.attributes;
    },
    removeAttribute(name) {
      delete this.attributes[name];
    },
    get textContent() {
      if (ownText) return ownText;
      return node.children.map((c) => (c.textContent == null ? "" : c.textContent)).join("");
    },
    set textContent(v) {
      ownText = String(v);
      node.children = [];
    },
  };
  return node;
}

globalThis.document = {
  createElement: makeNode,
  createTextNode: (t) => ({ nodeType: 3, textContent: String(t), parentNode: null }),
};

// ── Real production modules under stubs ───────────────────────────────────

const loading = await import(pathToFileURL(path.join(WEB, "studio-loading.js")));
const ui = await import(pathToFileURL(path.join(WEB, "studio-ui.js")));

const stylesSource = readWeb("studio-styles.js");
const uiSource = readWeb("studio-ui.js");
const loadingSource = readWeb("studio-loading.js");
const shellSource = readWeb("studio-shell.js");
const testingSource = readWeb("modal-testing.js");

function classesOf(el) {
  return new Set(String(el.className || "").split(/\s+/).filter(Boolean));
}

function childrenOf(el) {
  return el.children;
}

// ═══ 1–7. Loading primitive ══════════════════════════════════════════════

// 1 — default render structure
{
  const root = loading.renderLoadingState();
  assert.equal(root.tagName, "DIV", "root must be a div element");
  assert.ok(classesOf(root).has("cm-loading"), 'root must carry class "cm-loading"');
  assert.equal(root.getAttribute("data-size"), "page", "default size is page");
  const kids = childrenOf(root);
  assert.equal(kids.length, 2, "root contains exactly spinner + label");
  assert.ok(classesOf(kids[0]).has("cm-loading-spinner"), "first child is the spinner");
  assert.ok(classesOf(kids[1]).has("cm-loading-label"), "second child is the label");
  section("1. default render: cm-loading root, page size, spinner+label order");
}

// 2 — status semantics
{
  const root = loading.renderLoadingState({});
  assert.equal(root.getAttribute("role"), "status", 'role="status" is required');
  assert.equal(root.getAttribute("aria-live"), "polite", 'aria-live="polite" is required');
  assert.equal(root.hasAttribute("aria-busy"), false, "no global aria-busy on the root");
  section("2. role=status + aria-live=polite, no aria-busy");
}

// 3 — decorative spinner
{
  const root = loading.renderLoadingState();
  const spinner = childrenOf(root)[0];
  assert.equal(spinner.getAttribute("aria-hidden"), "true", "spinner is aria-hidden");
  section("3. decorative spinner carries aria-hidden=true");
}

// 4 — labels: default and supplied
{
  assert.equal(
    childrenOf(loading.renderLoadingState())[1].textContent,
    "Loading\u2026",
    "default label is exactly 'Loading…'"
  );
  const custom = loading.renderLoadingState({ label: "Fetching history\u2026" });
  assert.equal(childrenOf(custom)[1].textContent, "Fetching history\u2026", "supplied label passes through verbatim");
  section("4. default label 'Loading…' and exact supplied label");
}

// 5 — sizes
{
  assert.equal(
    loading.renderLoadingState({ size: "inline" }).getAttribute("data-size"),
    "inline",
    "valid inline size preserved"
  );
  assert.equal(loading.renderLoadingState({ size: "bogus" }).getAttribute("data-size"), "page", "unknown size normalizes to page");
  assert.equal(loading.renderLoadingState({ size: 42 }).getAttribute("data-size"), "page", "non-string size normalizes to page");
  assert.equal(loading.renderLoadingState({}).getAttribute("data-size"), "page", "missing size defaults to page");
  section("5. size normalization: inline preserved, unknown/non-string → page");
}

// 6 — testid behavior
{
  const withId = loading.renderLoadingState({ testid: "history-loading" });
  assert.equal(withId.getAttribute("data-testid"), "history-loading", "string testid is set");
  const junkNum = loading.renderLoadingState({ testid: 42 });
  assert.equal(junkNum.hasAttribute("data-testid"), false, "numeric testid ignored (not stringified)");
  const junkObj = loading.renderLoadingState({ testid: {} });
  assert.equal(junkObj.hasAttribute("data-testid"), false, "object testid ignored");
  section("6. testid set only for non-empty strings; non-string testids ignored");
}

// 7 — malformed options never throw
{
  for (const bad of [null, undefined, 7, "string", [], () => {}]) {
    const root = loading.renderLoadingState(bad);
    assert.ok(root && root.tagName === "DIV", `no throw for ${String(bad)} options`);
    assert.equal(childrenOf(root)[1].textContent, "Loading\u2026");
  }
  section("7. harmless malformed UI options normalize deterministically (never throw)");
}

// 8 — dependency-light module
{
  assert.equal(
    /^\s*import\s/m.test(loadingSource),
    false,
    "studio-loading.js must stay import-free (cycle-proof, dependency-light)"
  );
  section("8. studio-loading.js is import-free (no circular-dependency risk)");
}

// ═══ 9. One shared spinner implementation ═════════════════════════════════

{
  const keyframes = stylesSource.match(/@keyframes\s+([\w-]+)/g) || [];
  const spinKeyframes = keyframes.filter((k) => /spin/i.test(k));
  assert.deepEqual(
    spinKeyframes,
    ["@keyframes comfymodal-spin"],
    "exactly ONE spinner keyframe definition may exist (comfymodal-spin)"
  );
  const loadingRuleStart = stylesSource.indexOf(".cm-loading-spinner {");
  assert.notEqual(loadingRuleStart, -1, ".cm-loading-spinner rule must exist");
  const loadingRule = stylesSource.slice(loadingRuleStart, loadingRuleStart + 500);
  assert.ok(
    /animation:\s*comfymodal-spin\b/.test(loadingRule),
    ".cm-loading-spinner must reuse the single comfymodal-spin keyframe"
  );
  // Wizard behavior untouched.
  const wizardRuleStart = stylesSource.indexOf(".comfymodal-studio-wizard-spinner {");
  const wizardRule = stylesSource.slice(wizardRuleStart, wizardRuleStart + 400);
  assert.ok(
    /animation:\s*comfymodal-spin\s+0\.8s\s+linear\s+infinite/.test(wizardRule),
    "wizard spinner animation declaration unchanged"
  );
  assert.ok(/border-top-color:\s*var\(--color-accent,\s*#5a7fdb\)/.test(wizardRule), "wizard spinner visual unchanged");
  section("9. one shared spinner keyframe; loader reuses it; wizard visually unchanged");
}

// ═══ 10–13. Chip base + tones + families + statusBadge ════════════════════

// 10 — shared chip base exists with geometry-only ownership
{
  const chipStart = stylesSource.indexOf(".cm-chip {");
  assert.notEqual(chipStart, -1, ".cm-chip base rule must exist");
  const chipBlock = stylesSource.slice(chipStart, stylesSource.indexOf("}", chipStart));
  for (const prop of ["display: inline-flex", "border-radius: 999px", "font-size: 10px"]) {
    assert.ok(chipBlock.includes(prop), `.cm-chip owns ${prop}`);
  }
  assert.equal(
    /\[data-tone/.test(chipBlock),
    false,
    ".cm-chip base itself must NOT communicate semantic state"
  );
  section("10. shared .cm-chip geometry-only base exists");
}

// 11 — all six frozen tones exist
{
  for (const tone of ["neutral", "ok", "warn", "error", "running", "meta"]) {
    assert.ok(
      stylesSource.includes(`.cm-chip[data-tone="${tone}"]`),
      `tone selector .cm-chip[data-tone="${tone}"] must exist`
    );
  }
  section("11. all six shared tones exist (neutral/ok/warn/error/running/meta)");
}

// 12 — portability and compatibility family hooks remain distinct
{
  const portSel = ".cm-chip.cm-chip--portability";
  const compatSel = ".cm-chip.cm-chip--compatibility";
  const portStart = stylesSource.indexOf(portSel);
  const compatStart = stylesSource.indexOf(compatSel);
  assert.notEqual(portStart, -1, "portability family hook must exist");
  assert.notEqual(compatStart, -1, "compatibility family hook must exist");
  const portBlock = stylesSource.slice(portStart, stylesSource.indexOf("}", portStart));
  const compatBlock = stylesSource.slice(compatStart, stylesSource.indexOf("}", compatStart));
  assert.ok(
    /background:\s*transparent/.test(portBlock),
    "portability stays outline-pill family (transparent fill)"
  );
  assert.ok(
    !/background:\s*transparent/.test(compatBlock),
    "compatibility is NOT the transparent outline family"
  );
  assert.ok(
    /background:\s*var\(--color-accent-muted/.test(compatBlock),
    "compatibility keeps its filled toggle-family presentation"
  );
  section("12. portability vs compatibility family hooks present and visually distinct");
}

// 13 — live statusBadge adopts the shared base truthfully
{
  const okBadge = ui.statusBadge("READY", "ok");
  const okCls = classesOf(okBadge);
  assert.ok(okCls.has("cm-chip"), "badge carries shared chip base");
  assert.ok(okCls.has("comfymodal-studio-status-badge"), "legacy badge class preserved");
  assert.ok(okCls.has("ok"), "legacy kind modifier preserved");
  assert.equal(okBadge.getAttribute("data-tone"), "ok", "ok maps to ok tone");

  assert.equal(ui.statusBadge("DEGRADED", "warn").getAttribute("data-tone"), "warn", "warn → warn");
  assert.equal(ui.statusBadge("FAILED", "error").getAttribute("data-tone"), "error", "error → error");
  assert.equal(ui.statusBadge("CONFIGURED", "neutral").getAttribute("data-tone"), "neutral", "neutral → neutral");
  const unknown = ui.statusBadge("WEIRD", "not-a-kind");
  assert.equal(unknown.getAttribute("data-tone"), "neutral", "unknown kinds land on neutral (truthful default)");
  assert.ok(classesOf(unknown).has("neutral"), "legacy neutral modifier kept for unknown kinds");
  assert.equal(
    uiSource.includes("status-badge"),
    true,
    'studio-ui.js still contains "status-badge" (existing structural test dependency)'
  );
  section("13. statusBadge emits shared base+tone with truthful mapping, legacy classes preserved");
}

// ═══ 14–16. Focus-visible fallback ════════════════════════════════════════

{
  const fallbackStart = stylesSource.indexOf(".comfymodal-studio :is(button, [role=\"button\"], [tabindex=\"0\"], a):focus-visible");
  assert.notEqual(fallbackStart, -1, "frozen generic focus-visible selector must exist verbatim");
  const blockEnd = stylesSource.indexOf("}", fallbackStart);
  const block = stylesSource.slice(fallbackStart, blockEnd);
  assert.ok(
    /outline:\s*2px\s+solid\s+var\(--color-accent,\s*#5a7fdb\)/.test(block),
    "fallback uses the existing accent token at 2px"
  );
  assert.ok(/outline-offset:\s*2px/.test(block), "fallback offset is 2px");
  assert.ok(
    stylesSource.includes(".comfymodal-studio-modal :is(button, [role=\"button\"], [tabindex=\"0\"], a):focus-visible"),
    "real Studio dialog root is covered alongside the literal frozen scope"
  );
  assert.ok(
    stylesSource.includes(".comfymodal-studio-pagecontainer :is(button, [role=\"button\"], [tabindex=\"0\"], a):focus-visible"),
    "shell page container arm covers page surfaces in dialog AND standalone harness"
  );
  section("14. frozen generic focus-visible fallback exists (frozen scope + real roots)");
}

{
  // No broad :focus replacement was introduced by I3: every :focus rule that
  // existed before remains field-scoped; the new region only adds :focus-visible.
  const i3Region = stylesSource.slice(stylesSource.indexOf("Phase I3 — Shared UI primitives foundation"));
  assert.equal(
    /[^-]:focus \{/.test(i3Region),
    false,
    "I3 shared region must not add bare :focus rules"
  );
  const beforeFocusCount = (readWeb("studio-styles.js").match(/:focus[^-]/g) || []).length;
  const baselineFocusRules = [
    ".comfymodal-studio-model-picker:focus {",
  ];
  for (const rule of baselineFocusRules) {
    assert.ok(stylesSource.includes(rule), `pre-existing field :focus rule retained: ${rule}`);
  }
  assert.ok(beforeFocusCount >= 1);
  section("15. no broad :focus replacement introduced; pre-existing field rules intact");
}

{
  // Existing specific focus rules survive alongside the fallback.
  for (const sel of [
    ".comfymodal-studio-topnav button:focus-visible",
    ".comfymodal-studio-history-card:focus-visible",
    ".comfymodal-studio-backend-tab:focus-visible",
    ".comfymodal-studio-portability-chip:focus-visible",
    ".comfymodal-studio-carousel-item:focus-visible",
  ]) {
    assert.ok(stylesSource.includes(sel), `specific focus rule retained: ${sel}`);
  }
  section("16. existing specific :focus-visible rules remain (clean cascade override)");
}

// ═══ 17–20. Generic empty-state primitive ═════════════════════════════════

{
  // Legacy copy must be dead everywhere in the shared helper.
  for (const banned of [
    "No backends configured via legacy discovery.",
    "Use the Snapshots or Backend Presets tabs above.",
    "No workflows",
    "No models",
  ]) {
    assert.equal(
      uiSource.includes(banned),
      false,
      `generic empty-state primitive must not contain baked-in copy: "${banned}"`
    );
  }

  // Title/detail behavior.
  const full = ui.renderEmptyState({ title: "No snapshots yet", detail: "Take a snapshot to begin.", testid: "snapshots-empty" });
  assert.ok(classesOf(full).has("cm-empty-state"), "root carries cm-empty-state");
  assert.equal(full.getAttribute("data-testid"), "snapshots-empty", "optional testid honored");
  const kids = childrenOf(full);
  assert.equal(kids.length, 2);
  assert.ok(classesOf(kids[0]).has("cm-empty-state-title"), "title element present");
  assert.equal(kids[0].tagName, "DIV", "title is NOT a heading level (page owner decides hierarchy)");
  assert.equal(kids[0].textContent, "No snapshots yet", "title shows caller copy");
  assert.ok(classesOf(kids[1]).has("cm-empty-state-detail"), "detail element present");
  assert.equal(kids[1].textContent, "Take a snapshot to begin.", "detail shows caller copy");

  // Optional action appended WITHOUT cloning.
  const btn = makeNode("button");
  btn.setAttribute("type", "button");
  const withAction = ui.renderEmptyState({ title: "T", action: btn });
  const actionWrap = childrenOf(withAction)[1];
  assert.ok(classesOf(actionWrap).has("cm-empty-state-action"), "action wrapper present");
  assert.equal(actionWrap.firstChild, btn, "action node appended without cloning");

  // Blank detail omitted; missing title omitted; no alert/live semantics ever.
  const minimal = ui.renderEmptyState({ title: "Only title" });
  assert.equal(childrenOf(minimal).length, 1, "blank/absent detail renders nothing");
  const noTitle = ui.renderEmptyState({ detail: "d" });
  assert.equal(childrenOf(noTitle).length, 1, "blank/absent title renders nothing");
  assert.ok(classesOf(childrenOf(noTitle)[0]).has("cm-empty-state-detail"));
  for (const el of [full, withAction, minimal, noTitle]) {
    assert.equal(el.getAttribute("role"), null, "no role=alert on empty state");
    assert.equal(el.getAttribute("aria-live"), null, "no aria-live on empty state");
    for (const child of childrenOf(el)) {
      assert.ok(
        ["DIV", "BUTTON", "SPAN"].indexOf(child.tagName) !== -1,
        `empty-state children must not auto-assign heading levels (got ${child.tagName})`
      );
    }
  }
  section("17. generic copy-free empty-state API behaves per freeze (title/detail/action/testid)");
}

{
  for (const cls of [".cm-empty-state {", ".cm-empty-state-title {", ".cm-empty-state-detail {", ".cm-empty-state-action {"]) {
    assert.ok(stylesSource.includes(cls), `empty-state CSS base must include ${cls}`);
  }
  section("18. shared empty-state CSS base present (minimal, no redesign)");
}

// ═══ 19–21. Scope guards ══════════════════════════════════════════════════

{
  // Image-viewer helpers (I5-reserved) keep their defining markers intact.
  for (const marker of [
    "export function createZoomableImageEl(imageUrl, alt, opts)",
    "export function createImagePreviewOverlay(opts)",
    '"comfymodal-studio-zoom-wrap"',
    '"comfymodal-studio-preview-overlay"',
    "zoomable-image",
  ]) {
    assert.ok(uiSource.includes(marker), `image-viewer marker intact: ${marker}`);
  }
  section("19. image-viewer helpers byte-markers intact (I5 reserved)");
}

{
  // Staged migration guard (I3 §20), updated by I4, I6, I7 and I8 (documented
  // drift, same precedent as I2's re-pointed pin): the History lane (I4)
  // consumed renderLoadingState/renderEmptyState in its own files, the I7
  // Backend/Settings lane migrated the three Backend loading sites
  // (presets/snapshots/workspaces), the I6 Workflows/Models lane
  // migrated the workflows/model-library sites, and the I8 Playground lane
  // migrated its capabilities/recent-runs sites. Those verbatim pins and
  // no-reference entries are retired. Settings legitimately has zero loading
  // sites — static page — so no page module remains on this guard.
  const expectations = [];
  for (const [file, needle] of expectations) {
    assert.ok(readWeb(file).includes(needle), `${file} still owns its loading site (${needle}) — zero premature migration`);
  }
  // And no non-migrated page module references the new primitives yet.
  // (studio-backend-presets/snapshots/workspaces migrated by I7;
  // studio-workflows.js + studio-model-library.js migrated by I6;
  // studio-playground.js + studio-experiment-mode.js migrated by I8;
  // studio-settings.js legitimately has zero loading sites — static page.)
  for (const file of [
    "studio-settings.js",
  ]) {
    assert.equal(
      readWeb(file).includes("studio-loading.js"),
      false,
      `${file} must not import studio-loading.js yet (downstream lane work)`
    );
    assert.equal(readWeb(file).includes("renderLoadingState"), false, `${file} must not call renderLoadingState yet`);
  }
  // I7 truth: the three Backend modules now import the shared primitive,
  // and Settings remains static with none.
  for (const file of [
    "studio-backend-presets.js",
    "studio-backend-snapshots.js",
    "studio-backend-workspaces.js",
  ]) {
    assert.ok(readWeb(file).includes("./studio-loading.js"), `${file} consumes the shared loading primitive (I7)`);
  }
  section("20. page loading sites migrated (History I4, Backend I7, Workflows/Models I6, Playground I8)");
}

{
  for (const [name, src] of [["studio-ui.js", uiSource], ["studio-loading.js", loadingSource], ["studio-styles.js", stylesSource]]) {
    for (const banned of ["BroadcastChannel", "hashchange", "pushState", "replaceState", "studio-image-compare"]) {
      assert.equal(src.includes(banned), false, `${name} must not contain ${banned}`);
    }
  }
  section("21. no routing / BroadcastChannel / Compare implementation added by I3");
}

console.log("PASS: phase-i3 shared primitives foundation unit complete");
