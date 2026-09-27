// Modal Studio — History V2 Browser Download helper
//
// Explicit browser-side save of a MANAGED History asset to the user's normal
// browser-download destination.  This is NOT configured-folder Export: no
// server-side copy, no export_records write, no durable export state of any
// kind.  One click = exactly one managed-asset GET.
//
// Semantics (F3 Follow-Up A):
//   - Rendering never fetches anything; only an explicit click does.
//   - Preview and Original are distinct variants with distinct URLs and
//     distinct buttons; a Thumbnail is never labeled Preview.
//   - The response Blob MIME is the filename-extension authority.
//   - Failures are truthful and bounded: the button re-enables, the note
//     carries a short reason, retry stays available, and NO History state
//     (favorite/note/export) is touched.
//   - A per-button in-flight guard collapses rapid repeated clicks into one
//     asset GET without blocking downloads of other outputs/variants.
//
// Pure helpers are exported for Node unit tests; buildManagedAssetDownload
// Button requires a DOM and is exercised by the fake-browser suite.

// ── Variant vocabulary ───────────────────────────────────────────────────

const VARIANT_LABELS = {
  preview: "Download Preview",
  original: "Download Original",
  thumbnail: "Download Thumbnail",
};

const MIME_EXTENSIONS = {
  "image/webp": "webp",
  "image/png": "png",
  "image/jpeg": "jpg",
  "image/jpg": "jpg",
  "image/gif": "gif",
  "image/avif": "avif",
};

/**
 * Extension for a response MIME type.  The downloaded bytes' MIME is the
 * final authority; unknown image subtypes pass through sanitized, and a
 * missing/malformed MIME falls back to "png" (the project's canonical asset
 * format) rather than guessing from a URL or a Preview filename.
 */
export function mimeToExtension(mime) {
  const key = String(mime == null ? "" : mime).toLowerCase().split(";")[0].trim();
  if (MIME_EXTENSIONS[key]) return MIME_EXTENSIONS[key];
  if (key.indexOf("image/") === 0) {
    const sub = key.slice(6).replace(/[^a-z0-9]/g, "");
    if (sub) return sub;
  }
  return "png";
}

/** Filesystem-safe name fragment: invalid chars → "_", trimmed, bounded. */
export function sanitizeFilenamePart(value, maxLen) {
  const cap = maxLen != null ? maxLen : 60;
  return String(value == null ? "" : value)
    .trim()
    .replace(/[^a-zA-Z0-9._-]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, cap);
}

/**
 * Deterministic, collision-resistant download filename base.
 *
 * Preference order: a safe producer filename when provided (still suffixed
 * with output identity to prevent cross-output collisions), otherwise
 * workflow + seed + output index + variant + generation identity.  Never
 * timestamp-only; stable across re-renders and reloads.
 */
export function buildHistoryDownloadFilename(meta) {
  const m = meta && typeof meta === "object" ? meta : {};
  const parts = [];
  const producerSrc = String(m.producerFilename == null ? "" : m.producerFilename)
    .replace(/\\/g, "/")
    .split("/")
    .pop() || "";
  const producer = sanitizeFilenamePart(producerSrc.replace(/\.[^.]+$/, ""));
  if (producer) parts.push(producer);
  const workflow = sanitizeFilenamePart(m.workflow, 40);
  if (workflow) parts.push(workflow);
  if (m.seed != null && m.seed !== "") {
    const seed = sanitizeFilenamePart(String(m.seed), 24);
    if (seed) parts.push("seed" + seed);
  }
  if (m.outputIndex != null) parts.push("out" + String(m.outputIndex));
  parts.push(String(m.variant || "image"));
  const genId = sanitizeFilenamePart(m.generationId, 32);
  if (genId) parts.push(genId);
  const joined = parts.join("_");
  return (joined.length > 100 ? joined.slice(0, 100) : joined) || "modal_asset";
}

function _paintNote(testId, text) {
  if (!testId) return;
  try {
    const noteEl = document.querySelector('[data-testid="' + testId + '"]');
    if (noteEl) noteEl.textContent = text;
  } catch (err) { /* detached document — nothing to paint */ }
}

function _makeButton(attrs) {
  const btn = document.createElement("button");
  btn.type = "button";
  if (attrs.className) btn.className = attrs.className;
  if (attrs.testId) btn.setAttribute("data-testid", attrs.testId);
  btn.setAttribute("aria-label", attrs.label);
  btn.textContent = attrs.label;
  if (attrs.title) btn.title = attrs.title;
  return btn;
}

/**
 * Native download button for one managed asset variant.
 *
 * opts:
 *   url           managed asset URL (required — absent ⇒ returns null so no
 *                 dead Download control is ever rendered)
 *   variant       "preview" | "original" | "thumbnail"
 *   label         optional label override (defaults per variant)
 *   className     button classes (e.g. comfymodal-secondary-btn / menu-item)
 *   testId        deterministic data-testid
 *   filenameMeta  {workflow, generationId, seed, outputIndex, producerFilename}
 *   noteTestId    status-line testid receiving success/failure text
 *   onStarted     sync callback fired at click start (e.g. close a menu)
 *
 * Behavior contract: zero fetches at render time; one guarded fetch per
 * click; Blob-MIME extension; object-URL anchor revoked after trigger;
 * truthful bounded failure text; button always re-enables; no History or
 * export state is ever touched.
 */
export function buildManagedAssetDownloadButton(opts) {
  const o = opts || {};
  if (!o.url) return null;
  const variant = o.variant === "original" || o.variant === "thumbnail" ? o.variant : "preview";
  const label = o.label || VARIANT_LABELS[variant];
  let inFlight = false;

  const btn = _makeButton({
    className: o.className || "",
    testId: o.testId || "",
    label: label,
    title: o.title || ("Save this " + variant + " to your browser downloads"),
  });

  btn.addEventListener("click", async function () {
    if (inFlight || btn.disabled) return;
    inFlight = true;
    btn.disabled = true;
    const idleText = btn.textContent;
    btn.textContent = "Downloading\u2026";
    if (typeof o.onStarted === "function") {
      try { o.onStarted(); } catch (err) { /* menu close must not block */ }
    }
    try {
      const resp = await fetch(o.url);
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      const blob = await resp.blob();
      if (!blob || blob.size === 0) throw new Error("Empty asset response");
      const ext = mimeToExtension(blob.type);
      const filename = buildHistoryDownloadFilename(
        Object.assign({}, o.filenameMeta || {}, { variant: variant })
      ) + "." + ext;
      const objUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      setTimeout(function () {
        if (a.parentNode) a.parentNode.removeChild(a);
        URL.revokeObjectURL(objUrl);
      }, 100);
      _paintNote(o.noteTestId, "Downloaded " + filename);
    } catch (err) {
      const msg = err && err.message ? String(err.message) : "Download failed";
      _paintNote(o.noteTestId, ("Download failed: " + msg).slice(0, 140));
      btn.focus();
    } finally {
      inFlight = false;
      btn.disabled = false;
      btn.textContent = idleText;
    }
  });

  return btn;
}
