// Modal Studio — History V2 Configured-Folder Export helper
//
// Explicit server-side copy of a MANAGED History asset into the configured
// Studio output folder (frozen F9 route: bodyless POST
// /history-v2/assets/{asset_id}/export).  This is NOT Browser Download: no
// blob is fetched, no anchor is clicked, nothing is saved by the browser —
// and it is NOT the legacy Save route.  One click = exactly one export POST;
// durable state afterwards comes from the explicit detail refetch, never
// from a local optimistic flip.
//
// Per-variant states (backend-authoritative):
//   not_exported → enabled "Export <Variant>"
//   exported     → disabled "<Variant> exported" (redundant action suppressed)
//   missing      → enabled "Export <Variant> again"  (never "never exported")
//   failed       → enabled "Retry export <Variant>"
// Absent variant (no Asset ID projected) renders NO control at all.
//
// Pure helpers are exported for Node unit tests; buildConfiguredExportButton
// requires a DOM and is exercised by the fake-browser suite.

// ── Variant vocabulary ───────────────────────────────────────────────────

const VARIANT_NOUNS = {
  preview: "Preview",
  original: "Original",
};

/**
 * Derive the configured-Export action for one variant from its durable
 * export state (null/unknown state → not_exported semantics only when an
 * asset exists; callers gate on assetId BEFORE calling).
 * @param {string|null|undefined} state canonical export state
 * @param {"preview"|"original"} variant
 * @returns {{kind: "export"|"exported"|"again"|"retry", label: string, disabled: boolean}}
 */
export function deriveExportAction(state, variant) {
  const noun = VARIANT_NOUNS[variant] || "Asset";
  const key = state == null ? "" : String(state);
  if (key === "exported") {
    return { kind: "exported", label: noun + " exported", disabled: true };
  }
  if (key === "missing") {
    return { kind: "again", label: "Export " + noun + " again", disabled: false };
  }
  if (key === "failed") {
    return { kind: "retry", label: "Retry export " + noun, disabled: false };
  }
  return { kind: "export", label: "Export " + noun, disabled: false };
}

/** Bounded truthful note text for one normalized export result. */
export function exportResultNote(result) {
  const r = result && typeof result === "object" ? result : {};
  if (r.partial) {
    return ("Export partially failed \u2014 " + (r.message || r.reason || "the copy could not be fully recorded")
      + ". The saved state below was refreshed.").slice(0, 180);
  }
  if (!r.ok) {
    return ("Export failed: " + (r.message || r.reason || "request failed")).slice(0, 180);
  }
  if (r.alreadyExported) {
    return ("Already exported \u2014 " + (r.destinationPath || "existing copy reused")).slice(0, 180);
  }
  return ("Exported to " + (r.destinationPath || "the configured output folder")).slice(0, 180);
}

function _paintNote(testId, text) {
  if (!testId) return;
  try {
    const noteEl = document.querySelector('[data-testid="' + testId + '"]');
    if (noteEl) noteEl.textContent = text;
  } catch (err) { /* detached document — nothing to paint */ }
}

/**
 * Native configured-Export button for one managed asset variant.
 *
 * opts:
 *   assetId      projected Asset ID (required — absent ⇒ null so an absent
 *                variant never renders a dead Export control)
 *   exportState  durable per-variant export state (may be null)
 *   variant      "preview" | "original"
 *   className    button classes (comfymodal-secondary-btn / menu-item)
 *   testId       deterministic data-testid
 *   title        optional tooltip (defaults to the folder-export wording)
 *   noteTestId   status-line testid receiving success/failure text
 *   onExport     async () => normalized export result — performs EXACTLY ONE
 *                guarded POST (the page runner owns dedupe + durable refetch)
 *
 * Behavior contract: zero requests at render time; per-button in-flight
 * guard collapses rapid duplicate clicks into one POST without blocking
 * other outputs/variants; already_exported paints success; partial paints a
 * distinct truthful failure; the button recovers after success AND failure;
 * no blob download, no anchor click, no local export-state mutation.
 */
export function buildConfiguredExportButton(opts) {
  const o = opts || {};
  if (!o.assetId) return null;
  const variant = o.variant === "original" ? "original" : "preview";
  const action = deriveExportAction(o.exportState, variant);
  let inFlight = false;

  const btn = document.createElement("button");
  btn.type = "button";
  if (o.className) btn.className = o.className;
  if (o.testId) btn.setAttribute("data-testid", o.testId);
  btn.setAttribute("aria-label", action.label);
  btn.textContent = action.label;
  btn.title = o.title
    || "Copy this " + variant + " into the configured Studio output folder (not a browser download)";
  btn.disabled = !!action.disabled;

  btn.addEventListener("click", async function () {
    if (inFlight || btn.disabled) return;
    inFlight = true;
    btn.disabled = true;
    const idleText = btn.textContent;
    btn.textContent = "Exporting\u2026";
    let result = null;
    try {
      result = typeof o.onExport === "function" ? await o.onExport() : null;
    } catch (err) {
      // The runner resolves envelopes; this is a last-resort guard so a
      // click can never produce an unhandled rejection.
      result = { ok: false, reason: "network_error", message: err && err.message ? err.message : "request failed" };
    }
    _paintNote(o.noteTestId, exportResultNote(result));
    if (btn.isConnected) {
      inFlight = false;
      btn.disabled = false;
      btn.textContent = idleText;
      if (result && !result.ok) btn.focus();
    }
  });

  return btn;
}
