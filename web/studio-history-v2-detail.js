// Modal Studio — History V2 Generation Detail
//
// Full-screen overlay for a single generation record: featured output,
// other-output thumbnails with "Set as featured", Preview / Original slots,
// parameters, exact metadata, attempts, errors, export state, notes,
// favorite, timing diagnostics, and the Generate Original action.
//
// Appended to document.body; Escape closes via registerLayerHandler
// (layer 3, matching the shared preview overlay).  All DOM via el().

import { el, registerLayerHandler, buildViewerShell, resolveViewerShellArgs } from "./studio-ui.js";
import { renderLoadingState } from "./studio-loading.js";
import { _formatDuration, resolveViewerInput } from "./studio-run-normalizer.js";
import {
  buildAddToCompareItem,
  openComparePair,
  shortIdTail,
  startCompare,
} from "./studio-image-compare.js";
import {
  deriveOriginalActionState,
  deriveRetryActionLabel,
  deriveSingleResumeState,
  generateOriginalEligibility,
  isDataSaverKind,
  isTerminalAttemptStatus,
  selectDetailAsset,
  selectFeedAsset,
} from "./history-v2-repository.js";
import { buildManagedAssetDownloadButton } from "./history-v2-browser-download.js";
import { buildConfiguredExportButton, exportResultNote } from "./history-v2-export.js";

// ── Constants / helpers ───────────────────────────────────────────────────

const DOWNLOAD_NOTE_TESTID = "history-v2-download-note";
const EXPORT_NOTE_TESTID = "history-v2-export-note";

const STATUS_LABELS = {
  completed: "Completed",
  completed_with_failures: "Completed with failures",
  failed: "Failed",
  canceled: "Canceled",
  interrupted: "Interrupted",
  running: "Running",
};

// Shared chip tones (I3 taxonomy): STATUS → data-tone.  Legacy status-*
// classes stay verbatim; status meaning never changes.
const STATUS_TONES = {
  completed: "ok",
  completed_with_failures: "warn",
  failed: "error",
  canceled: "neutral",
  interrupted: "warn",
  running: "running",
};

export function appendIfPresent(parent, child) {
  if (child) parent.appendChild(child);
}

// Kept as the History-facing name; the policy itself now lives with the
// other viewer-input logic (studio-run-normalizer.js) so History and the
// Playground preview resolve the displayed asset through one implementation.
export function selectGenerationDetailAsset(record) {
  return resolveViewerInput(record).output;
}

export function historyAttemptPurposeLabel(mode) {
  const key = mode == null ? "" : String(mode).toLowerCase();
  if (key === "original") return "Original";
  if (key === "preview" || key === "data_saver" || key === "data-saver" || key === "datasaver") return "Data Saver";
  return "Run";
}

function _statusChip(status) {
  const key = STATUS_LABELS[status] ? status : "running";
  const label = STATUS_LABELS[status] || status || "Running";
  return el("span", {
    class: "comfymodal-studio-history-v2-chip status-" + key + " cm-chip",
    "data-tone": STATUS_TONES[key] || "neutral",
    text: label,
  });
}

function _shortDateTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return String(iso);
  try {
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" })
      + ", " + d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  } catch (err) {
    return String(iso);
  }
}

function _hideOnError(e) {
  e.currentTarget.style.display = "none";
}

function _previewBadge() {
  return el("span", {
    class: "comfymodal-studio-history-v2-badge comfymodal-studio-history-v2-preview-badge",
    "data-testid": "history-v2-preview-badge",
    "data-variant": "data_saver",
    text: "Data Saver",
  });
}

function _servedVariantBadge(servedVariant) {
  const key = String(servedVariant || "").toLowerCase();
  if (key === "data_saver" || key === "datasaver" || key === "data-saver" || key === "preview") {
    return el("span", {
      class: "comfymodal-studio-history-v2-badge comfymodal-studio-history-v2-served-badge",
      "data-testid": "history-v2-served-variant",
      "data-variant": "data_saver",
      text: "Data Saver",
    });
  }
  if (key === "original") {
    return el("span", {
      class: "comfymodal-studio-history-v2-badge comfymodal-studio-history-v2-served-badge",
      "data-testid": "history-v2-served-variant",
      "data-variant": "original",
      text: "Original",
    });
  }
  return null;
}

// ── Main entry ────────────────────────────────────────────────────────────

export async function renderGenerationDetail(generationId, repo, callbacks) {
  const cbs = callbacks || {};
  // History and Playground mount this exact same shell with data only
  // (record, imageUrl, timing) plus a behavioral persistence adapter.
  // There are no cosmetic opts: fav star, note editor, and timing section
  // are fixed in studio-ui.js so the two surfaces cannot drift apart.
  // Shell inputs are assembled once, here, and reused for every re-render —
  // both surfaces build them through resolveViewerShellArgs, so a new input
  // can never land on one surface and not the other.
  var repoMode = null;
  try {
    repoMode = (typeof repo.getModeInfo === "function") ? repo.getModeInfo() : null;
  } catch (err) { repoMode = null; }
  var canDelete = !!(repoMode && repoMode.mode === "v2");
  const shellAdapters = {
    persistence: {
      setFavorite: function (rec, next) { return repo.setFavorite(rec.id, next); },
      setNote: function (rec, text) { return repo.setNote(rec.id, text); },
      onChanged: function () { if (typeof cbs.onChanged === "function") cbs.onChanged(); },
      deleteGeneration: canDelete
        ? function (rec) { return repo.deleteGeneration(rec.id); }
        : undefined,
    },
    fileActions: {
      openAsset: function (assetId) { return repo.openAsset(assetId); },
      revealAsset: function (assetId) { return repo.revealAsset(assetId); },
    },
    onUseAsBase: typeof callbacks.onUseAsBase === "function" ? callbacks.onUseAsBase : undefined,
    // Phase 10: image handoffs (Use as Current / Edit / Post / Upscale).
    // Pass-through only — the viewer buttons call these with {imageUrl} and
    // the page-level callbacks own stash + navigation. Absent = no button.
    onUseAsCurrent: typeof callbacks.onUseAsCurrent === "function" ? callbacks.onUseAsCurrent : undefined,
    onEdit: typeof callbacks.onEdit === "function" ? callbacks.onEdit : undefined,
    onPostProcess: typeof callbacks.onPostProcess === "function" ? callbacks.onPostProcess : undefined,
    onUpscale: typeof callbacks.onUpscale === "function" ? callbacks.onUpscale : undefined,
    // `close` is a hoisted function declaration below: the overlay's Delete
    // button dismisses through the shell's own close, which runs this full
    // surface cleanup (timers, layers, focus, onClose callback).
    onClose: function () { close(); },
  };
  const sharedShell = buildViewerShell(resolveViewerShellArgs(null, shellAdapters));
  const overlay = sharedShell.overlay;
  const content = sharedShell.contentEl;

  // ── Focus-in / restore plumbing (I1 §3.1 gap) ────────────────────────────
  //
  // On open, focus moves inside the dialog (close button — present in every
  // mount state: loading, not-found, detail).  The invoking element is
  // captured synchronously and focus returns to it on close; Escape/close
  // behavior itself is unchanged.  No second focus trap is built — shell
  // inert/layer behavior remains the authority.
  const _invoker = (function () {
    const ae = document.activeElement;
    return ae && typeof ae.focus === "function" && ae !== document.body ? ae : null;
  })();

  function _focusInitialControl() {
    const target = content.querySelector("button:not([disabled])");
    if (target && typeof target.focus === "function") {
      try { target.focus(); } catch (err) { /* non-focusable environment */ }
    }
  }

  // After any mount-state render, if the previously focused element was
  // destroyed by the re-render (focus silently dropped to <body>), bring
  // focus back inside the dialog.  Focus the user placed elsewhere INSIDE
  // the overlay is never stolen.
  function _ensureDialogFocus() {
    const ae = document.activeElement;
    if (!ae || !overlay.contains(ae)) _focusInitialControl();
  }

  function _restoreInvokerFocus() {
    let target = _invoker;
    if (!target || typeof target.focus !== "function") return;
    if (!target.isConnected && typeof target.getAttribute === "function") {
      // The durable refetch (onChanged → fetchFeed) may have rebuilt the feed
      // while the detail was open, detaching the original card.  Re-resolve
      // it by its stable testid+id identity instead of dropping focus.
      const tid = target.getAttribute("data-testid");
      const did = target.getAttribute("data-id");
      if (tid && did) {
        try {
          target = document.querySelector('[data-testid="' + tid + '"][data-id="' + did + '"]') || target;
        } catch (err) { /* keep original target */ }
      }
    }
    if (target.isConnected) {
      try { target.focus(); } catch (err) { /* detached mid-flight */ }
    }
  }

  // ── Close / Escape plumbing ────────────────────────────────────────────
  let _layerUnreg = null;
  let _closed = false;
  let _activeMenu = null;
  let _outsideHandler = null;
  let _originalPollTimer = null;
  let _pageAnchorObserver = null;

  function close(notify) {
    if (_closed) return;
    _closed = true;
    closeAnyMenu();
    if (_originalPollTimer) {
      clearTimeout(_originalPollTimer);
      _originalPollTimer = null;
    }
    if (_layerUnreg) {
      _layerUnreg();
      _layerUnreg = null;
    }
    if (_pageAnchorObserver) {
      _pageAnchorObserver.disconnect();
      _pageAnchorObserver = null;
    }
    sharedShell.close(false);
    _restoreInvokerFocus();
    if (notify !== false && typeof cbs.onClose === "function") cbs.onClose();
  }

  // The shared shell owns the actual DOM close behavior; these listeners
  // keep History's polling/menu/focus lifecycle in sync with it.
  sharedShell.closeButton.addEventListener("click", function () { close(); });
  sharedShell.backdrop.addEventListener("click", function () { close(); });

  _layerUnreg = registerLayerHandler(3, {
    escape: function () {
      // A menu being open is an inner layer: Escape closes the menu first.
      if (_activeMenu) {
        closeAnyMenu();
        return true;
      }
      close();
      return true;
    },
  });

  function makeCloseBtn() {
    return sharedShell.closeButton;
  }

  function clearContent() {
    while (content.firstChild) content.removeChild(content.firstChild);
  }

  // ── Overflow menu (Set as featured) ────────────────────────────────────
  function closeAnyMenu() {
    if (_activeMenu) {
      _activeMenu.remove();
      _activeMenu = null;
    }
    if (_outsideHandler) {
      document.removeEventListener("mousedown", _outsideHandler);
      _outsideHandler = null;
    }
  }

  function positionMenu(menu, anchor) {
    const r = anchor.getBoundingClientRect();
    menu.style.position = "fixed";
    menu.style.top = (r.bottom + 4) + "px";
    menu.style.left = Math.max(8, r.left) + "px";
  }

  function openOutputMenu(anchor, index) {
    closeAnyMenu();
    const menu = el("div", { class: "comfymodal-studio-history-v2-menu" });
    const featuredIndex = currentFeaturedIndex();
    const item = el("button", {
      class: "comfymodal-studio-history-v2-menu-item",
      type: "button",
      text: "Set as featured",
      disabled: index === featuredIndex,
      onclick: async function () {
        closeAnyMenu();
        try {
          await repo.setFeaturedOutput(generationId, index);
        } catch (err) { /* best effort — reload below still reconciles */ }
        if (typeof cbs.onChanged === "function") cbs.onChanged();
        reload();
      },
    });
    menu.appendChild(item);
    // Per-output Browser Download items (F3): each rendered logical output
    // downloads ITS OWN projected URLs — the featured output never redirects
    // another output's download.  Variant gating matches the featured slots:
    // Preview (else truthfully-labeled Thumbnail), and Original only when a
    // usable Original URL is projected (never for original_failed without a
    // retained winner).  One click = one managed-asset GET; no export state.
    const out = _outputByIndex(index);
    if (out) {
      // While a compare session is active, any eligible output image can
      // fill slot B (a further pick truthfully replaces B). Non-image
      // outputs expose nothing.
      const outAsset = selectFeedAsset(out);
      if (outAsset.url) {
        const compareItem = buildAddToCompareItem({
          descriptor: _compareDescriptor(outAsset.url, "Output " + (index + 1), "output", currentRecord),
          testId: "history-v2-output-add-to-compare-" + index,
          className: "comfymodal-studio-history-v2-menu-item cm-compare-menu-item",
        });
        if (compareItem) menu.appendChild(compareItem);
      }
      const meta = _downloadFilenameMeta(currentRecord, index);
      const previewBtn = buildManagedAssetDownloadButton({
        url: out.previewUrl || out.thumbUrl,
        variant: out.previewUrl ? "data_saver" : "thumbnail",
        className: "comfymodal-studio-history-v2-menu-item",
        testId: "history-v2-output-download-" + (out.previewUrl ? "preview" : "thumbnail") + "-" + index,
        filenameMeta: meta,
        noteTestId: DOWNLOAD_NOTE_TESTID,
        onStarted: closeAnyMenu,
      });
      if (previewBtn) menu.appendChild(previewBtn);
      const originalBtn = buildManagedAssetDownloadButton({
        url: out.originalUrl && !out.originalFailed ? out.originalUrl : "",
        variant: "original",
        className: "comfymodal-studio-history-v2-menu-item",
        testId: "history-v2-output-download-original-" + index,
        filenameMeta: meta,
        noteTestId: DOWNLOAD_NOTE_TESTID,
        onStarted: closeAnyMenu,
      });
      if (originalBtn) menu.appendChild(originalBtn);
      // Per-output configured-Export items (F10): each output exports ITS
      // OWN projected Preview/Original Asset ID — never a redirect through
      // the featured output, never a client-provided output index.  One
      // click sends only the selected Asset ID in the URL path.
      const previewExport = buildConfiguredExportButton({
        assetId: out.previewAssetId,
        exportState: out.previewExportState,
        variant: "data_saver",
        className: "comfymodal-studio-history-v2-menu-item",
        testId: "history-v2-output-export-preview-" + index,
        noteTestId: EXPORT_NOTE_TESTID,
        onExport: function () { return _runExport(out.previewAssetId); },
      });
      if (previewExport) menu.appendChild(previewExport);
      const originalExport = buildConfiguredExportButton({
        // A projected original Asset ID IS the usable retained winner (a
        // failed producer Attempt without a winner projects none) — so the
        // Asset ID alone decides availability, never URL text.
        assetId: out.originalAssetId,
        exportState: out.originalExportState,
        variant: "original",
        className: "comfymodal-studio-history-v2-menu-item",
        testId: "history-v2-output-export-original-" + index,
        noteTestId: EXPORT_NOTE_TESTID,
        onExport: function () { return _runExport(out.originalAssetId); },
      });
      if (originalExport) menu.appendChild(originalExport);
    }
    positionMenu(menu, anchor);
    menu.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeAnyMenu();
    });
    document.body.appendChild(menu);
    _activeMenu = menu;
    _outsideHandler = function onDown(ev) {
      if (!menu.contains(ev.target) && ev.target !== anchor && !anchor.contains(ev.target)) {
        closeAnyMenu();
      }
    };
    document.addEventListener("mousedown", _outsideHandler);
    item.focus();
  }

  // ── Detail builders ────────────────────────────────────────────────────
  let currentRecord = null;

  function currentFeaturedIndex() {
    return (currentRecord && currentRecord.featuredOutput && currentRecord.featuredOutput.index != null)
      ? currentRecord.featuredOutput.index
      : 0;
  }

  // Canonical logical-output lookup: outputs[] is the backend's canonical
  // grouping; match on the projected index (never array position alone).
  function _outputByIndex(index) {
    const outputs = (currentRecord && Array.isArray(currentRecord.outputs)) ? currentRecord.outputs : [];
    for (let i = 0; i < outputs.length; i++) {
      const out = outputs[i];
      if (out && (out.index != null ? out.index : i) === index) return out;
    }
    return null;
  }

  // Deterministic download filename identity: workflow + seed + output index
  // (+ generation tail).  The variant suffix and Blob-MIME extension are
  // appended by the shared download helper.
  function _downloadFilenameMeta(rec, outputIndex) {
    const r = rec || {};
    const params = r.params && typeof r.params === "object" ? r.params : {};
    return {
      workflow: r.workflow || "",
      generationId: r.id || "",
      seed: params.seed != null ? params.seed : "",
      outputIndex: outputIndex,
    };
  }

  function _row(key, value) {
    if (value == null || value === "") return null;
    return el("div", { class: "comfymodal-studio-history-v2-row" }, [
      el("span", { class: "comfymodal-studio-history-v2-row-key", text: key }),
      el("span", { class: "comfymodal-studio-history-v2-row-value", text: String(value) }),
    ]);
  }

  function _section(title, rows) {
    const children = (rows || []).filter(function (r) { return r != null; });
    if (children.length === 0) return null;
    return el("div", { class: "comfymodal-studio-history-v2-section" }, [
      el("div", { class: "comfymodal-studio-history-v2-section-title", text: title }),
    ].concat(children));
  }

  function buildOutputsRow(record) {
    const outputs = Array.isArray(record.outputs) ? record.outputs : [];
    const featuredIndex = (record.featuredOutput && record.featuredOutput.index != null)
      ? record.featuredOutput.index
      : 0;
    const wrap = el("div", { class: "comfymodal-studio-history-v2-section" }, [
      el("div", { class: "comfymodal-studio-history-v2-section-title", text: "Other outputs" }),
    ]);
    if (outputs.length === 0) {
      wrap.appendChild(el("div", { class: "comfymodal-studio-history-v2-row-value", text: "No outputs" }));
      return wrap;
    }
    const row = el("div", { class: "comfymodal-studio-history-v2-outputs-row" });
    outputs.forEach(function (out, i) {
      if (!out) return;
      const index = out.index != null ? out.index : i;
      const asset = selectFeedAsset(out);
      const wrapThumb = el("div", { class: "comfymodal-studio-history-v2-output-thumb-wrap" });
      const thumbEl = el("div", {
        class: "comfymodal-studio-history-v2-output-thumb" + (index === featuredIndex ? " featured" : ""),
        title: index === featuredIndex ? "Featured output" : "Output " + (index + 1),
      }, asset.url
        ? [el("img", { class: "comfymodal-studio-history-v2-thumb-img", src: asset.url, alt: "Output " + (index + 1), onerror: _hideOnError })]
        : [el("span", { class: "comfymodal-studio-history-v2-output-thumb-empty", text: asset.label })]);
      if (isDataSaverKind(asset.kind)) thumbEl.appendChild(_previewBadge());
      const menuBtn = el("button", {
        class: "comfymodal-studio-history-v2-menu-btn",
        type: "button",
        "aria-label": "Output " + (index + 1) + " actions",
        title: "Output actions",
        text: "\u22ef",
        onclick: function (e) {
          e.stopPropagation();
          openOutputMenu(menuBtn, index);
        },
      });
      wrapThumb.appendChild(thumbEl);
      wrapThumb.appendChild(menuBtn);
      row.appendChild(wrapThumb);
    });
    wrap.appendChild(row);
    return wrap;
  }

  // ── Compare entries (I5, lightweight A/B) ─────────────────────────────
  //
  // Client-only transient session over EXISTING projected URLs. The plain
  // "Compare" action preselects the displayed featured asset as A and
  // activates the compare tray (the user then picks B from any reachable
  // History output). Where a usable Original URL is ALREADY projected on
  // the record, "Compare with Original" offers the direct Preview↔Original
  // pair — Original bytes are fetched only by that explicit click, never
  // eagerly to populate comparison. Download/Export actions and all
  // favorite/note/replay semantics are untouched.

  function _compareDescriptor(url, kindLabel, kind, rec) {
    return {
      url: url,
      label: kindLabel,
      kind: kind,
      meta: "Generation " + shortIdTail(rec && rec.id),
      alt: (rec && rec.prompt) || kindLabel,
    };
  }

  function buildPreviewOriginalSlots(record) {
    const feat = record.featuredOutput || {};
    const slots = el("div", { class: "comfymodal-studio-history-v2-slots" });
    const meta = _downloadFilenameMeta(record, feat.index != null ? feat.index : 0);

    const displayed = selectDetailAsset(feat);
    const previewBody = displayed.url
      ? el("div", { class: "comfymodal-studio-history-v2-slot-image" }, [
        el("img", {
          class: "comfymodal-studio-history-v2-thumb-img",
          src: displayed.url,
          alt: displayed.label,
          onerror: _hideOnError,
        }),
      ])
      : el("div", { class: "comfymodal-studio-history-v2-slot-placeholder", text: "Preview pending" });
    if (isDataSaverKind(displayed.kind)) previewBody.appendChild(_previewBadge());
    const servedBadge = _servedVariantBadge(feat.servedVariant);
    if (servedBadge) previewBody.appendChild(servedBadge);

    // Browser Download for the displayed Preview variant.  A Thumbnail-only
    // output downloads truthfully labeled Thumbnail bytes — never renamed to
    // Preview.  Rendering this control performs ZERO asset GETs.
    const previewDownload = buildManagedAssetDownloadButton({
      url: feat.previewUrl || feat.thumbUrl || "",
      variant: feat.previewUrl ? "data_saver" : "thumbnail",
      className: "comfymodal-secondary-btn",
      testId: feat.previewUrl ? "history-v2-download-preview" : "history-v2-download-thumbnail",
      filenameMeta: meta,
      noteTestId: DOWNLOAD_NOTE_TESTID,
    });

    // Configured-folder Export for the Preview VARIANT (F10) — a distinct
    // action from Browser Download with its own truthful per-state label.
    // Absent Preview Asset ID ⇒ no Export control at all (older payloads
    // without the projection simply show nothing).
    const previewExport = buildConfiguredExportButton({
      assetId: feat.previewAssetId,
      exportState: feat.previewExportState,
      variant: "data_saver",
      className: "comfymodal-secondary-btn",
      testId: "history-v2-export-preview",
      noteTestId: EXPORT_NOTE_TESTID,
      onExport: function () { return _runExport(feat.previewAssetId); },
    });

    slots.appendChild(el("div", { class: "comfymodal-studio-history-v2-slot" }, [
      el("div", {
        class: "comfymodal-studio-history-v2-slot-title",
        text: displayed.kind === "thumbnail" ? "Thumbnail" : (displayed.kind === "original" ? "Original" : "Data Saver"),
      }),
      previewBody,
      previewDownload,
      previewExport,
      // Lightweight A/B compare entry (I5): only for a usable managed image.
      displayed.url
        ? el("button", {
          class: "comfymodal-secondary-btn",
          "data-testid": "history-v2-compare",
          type: "button",
          text: "Compare",
          title: "Compare this image with another History output (client-side only)",
          onclick: function () {
            startCompare({
              descriptor: _compareDescriptor(displayed.url, displayed.kind === "thumbnail" ? "Thumbnail" : (displayed.kind === "original" ? "Original" : "Data Saver"), displayed.kind, record),
              invoker: document.activeElement,
            });
          },
        })
        : null,
      // Direct Preview↔Original pair — offered only when a usable Original
      // URL is ALREADY projected on the record; the click itself is what
      // may load Original bytes (explicit user action, like View Original).
      displayed.url && feat.originalUrl && !feat.originalFailed
        ? el("button", {
          class: "comfymodal-secondary-btn",
          "data-testid": "history-v2-compare-original",
          type: "button",
          text: "Compare with Original",
          title: "Compare the displayed Data Saver with its retained Original",
          onclick: function () {
            // One top-level modal at a time: dismiss the detail viewer
            // through its existing close path before opening compare.
            close();
            openComparePair({
              a: _compareDescriptor(displayed.url, displayed.kind === "thumbnail" ? "Thumbnail" : "Data Saver", displayed.kind, record),
              b: _compareDescriptor(feat.originalUrl, "Original", "original", record),
              invoker: document.activeElement,
            });
          },
        })
        : null,
    ]));

    let originalBody = null;
    if (feat.originalUrl) {
      const wrap = el("div", { class: "comfymodal-studio-history-v2-original-view" });
      const status = el("div", {
        class: "comfymodal-studio-history-v2-slot-placeholder",
        text: "Original available",
      });
      const viewBtn = el("button", {
        class: "comfymodal-secondary-btn",
        "data-testid": "history-v2-view-original",
        type: "button",
        text: "View Original",
        onclick: function () {
          if (viewBtn.disabled) return;
          viewBtn.disabled = true;
          viewBtn.textContent = "Loading Original...";
          const image = el("img", {
            class: "comfymodal-studio-history-v2-original-img",
            src: feat.originalUrl,
            alt: "Original",
            onerror: function (e) {
              e.currentTarget.style.display = "none";
              status.textContent = "Original unavailable";
              viewBtn.disabled = false;
              viewBtn.textContent = "View Original";
            },
          });
          wrap.insertBefore(image, viewBtn);
          status.textContent = "Original loaded";
          viewBtn.textContent = "Original loaded";
        },
      });
      wrap.appendChild(status);
      wrap.appendChild(viewBtn);
      // Download Original is a SEPARATE explicit action from View Original:
      // it fetches + saves bytes without changing any display state, and is
      // offered only when a usable Original URL is projected (a failed
      // Original without a retained winner offers no dead download).
      const originalDownload = buildManagedAssetDownloadButton({
        url: feat.originalFailed ? "" : feat.originalUrl,
        variant: "original",
        className: "comfymodal-secondary-btn",
        testId: "history-v2-download-original",
        filenameMeta: meta,
        noteTestId: DOWNLOAD_NOTE_TESTID,
      });
      if (originalDownload) wrap.appendChild(originalDownload);
      originalBody = wrap;
    } else if (feat.originalFailed) {
      originalBody = el("div", { class: "comfymodal-studio-history-v2-slot-error", text: "Original generation failed \u2014 preview retained" });
    } else if (feat.originalAvailable) {
      originalBody = el("div", { class: "comfymodal-studio-history-v2-slot-placeholder", text: "Original available" });
    } else {
      originalBody = el("div", { class: "comfymodal-studio-history-v2-slot-placeholder", text: "No original" });
    }
    // Configured-folder Export Original (F10): independent third action kept
    // beside View Original / Download Original.  A projected original Asset
    // ID IS the usable retained winner (a failed producer Attempt without a
    // winner projects none), so the Asset ID alone decides availability.
    const originalExport = buildConfiguredExportButton({
      assetId: feat.originalAssetId,
      exportState: feat.originalExportState,
      variant: "original",
      className: "comfymodal-secondary-btn",
      testId: "history-v2-export-original",
      noteTestId: EXPORT_NOTE_TESTID,
      onExport: function () { return _runExport(feat.originalAssetId); },
    });
    slots.appendChild(el("div", { class: "comfymodal-studio-history-v2-slot" }, [
      el("div", { class: "comfymodal-studio-history-v2-slot-title", text: "Original" }),
      originalBody,
      originalExport,
    ]));

    // Shared bounded status line for every Browser Download on this detail
    // (featured slots + per-output menu items).  Never export wording —
    // browser download writes zero export state.
    slots.appendChild(el("div", {
      class: "comfymodal-studio-history-v2-action-note",
      "data-testid": DOWNLOAD_NOTE_TESTID,
      role: "status",
    }));

    // Separate bounded status line for configured-folder Export (F10) —
    // never conflated with the Browser Download note.
    slots.appendChild(el("div", {
      class: "comfymodal-studio-history-v2-action-note",
      "data-testid": EXPORT_NOTE_TESTID,
      role: "status",
    }));

    return slots;
  }

  // ── Generate / Retry Original (E4C/E4D) ─────────────────────────────────
  //
  // Two distinct Generation-scoped backend actions over the SAME immutable
  // snapshot: Generate Original POSTs /original (rerender flag only for the
  // explicit Generate Again action); Retry Original POSTs /original/retry
  // for a failed latest Attempt.  The browser never rebuilds the request and
  // never mutates Attempts client-side — durable state always comes from
  // reload/polling.  Preview is never replaced by a loading state — every
  // phase below keeps the left column (Preview/Thumbnail) untouched.

  let _originalInFlight = false;
  let _originalUnavailableNote = "";

  function _repoModeInfo() {
    try {
      return typeof repo.getModeInfo === "function" ? repo.getModeInfo() : null;
    } catch (err) {
      return null;
    }
  }

  function _startOriginalPolling() {
    if (_originalPollTimer || _closed) return;
    let ticks = 0;
    const tick = async function () {
      _originalPollTimer = null;
      if (_closed) return;
      ticks++;
      let fresh = null;
      try {
        fresh = await repo.getGeneration(generationId);
      } catch (err) {
        fresh = null;
      }
      if (_closed) return;
      if (fresh && !_isNotFound(fresh)) {
        const st = deriveOriginalActionState(fresh);
        const terminal = !st.latestAttempt || isTerminalAttemptStatus(st.latestAttempt.status);
        _renderDetail(fresh);
        if (terminal || ticks >= 150) {
          if (typeof cbs.onChanged === "function") cbs.onChanged();
          return;
        }
      } else if (ticks >= 150) {
        return;
      }
      _originalPollTimer = setTimeout(tick, 2000);
    };
    _originalPollTimer = setTimeout(tick, 2000);
  }

  // Shared runner for both Original actions: one in-flight guard, one POST,
  // truthful refusal handling, durable-state reload/poll afterwards.
  async function _postOriginalAction(send, actionLabel) {
    if (_originalInFlight || _closed) return;
    _originalInFlight = true;
    const btn = content.querySelector('[data-testid="history-v2-generate-original"]')
      || content.querySelector('[data-testid="history-v2-generate-again"]')
      || content.querySelector('[data-testid="history-v2-retry-original"]');
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Queuing\u2026";
    }
    let resp = null;
    let errMsg = "";
    try {
      resp = await send();
    } catch (err) {
      errMsg = err && err.message ? err.message : "Request failed";
    }
    _originalInFlight = false;
    if (_closed) return;

    const noteEl = content.querySelector('[data-testid="history-v2-generate-note"]');
    if (errMsg) {
      if (noteEl) noteEl.textContent = actionLabel + " failed: " + errMsg + " \u2014 preview retained.";
      reload();
      return;
    }
    if (resp && resp.accepted === false) {
      const outcome = resp.outcome ? String(resp.outcome) : "";
      if (outcome === "busy") {
        if (noteEl) noteEl.textContent = "Generation is busy \u2014 Preview retained. Original can start once the current run finishes.";
      } else if (outcome === "irreproducible" || resp.errorCode === "irreproducible") {
        _originalUnavailableNote = "This saved generation does not contain the exact immutable execution data required to generate an Original.";
      } else if (outcome === "retry_required") {
        // Machine-readable state transition from ordinary /original:
        // failed-only Original.  Never auto-retry and never loop back into
        // /original — re-render the durable failed state; Retry Original is
        // the explicit next user action.
        if (noteEl) {
          noteEl.textContent = resp.errorMessage || resp.message
            || "Original failed \u2014 use Retry Original to try again.";
        }
      } else {
        if (noteEl) {
          noteEl.textContent = resp.errorMessage || resp.message
            || actionLabel + " was not accepted \u2014 preview retained.";
        }
      }
      reload();
      return;
    }
    // accepted (new attempt or reused existing run): re-read durable state.
    // reused=true hydrates/polls the RETURNED run — no optimistic Attempt is
    // invented client-side; polling stops at a terminal attempt status.
    _startOriginalPolling();
    reload();
  }

  function _runGenerateOriginal(rerender) {
    return _postOriginalAction(function () {
      return repo.generateOriginal(generationId, rerender === true ? { rerender: true } : undefined);
    }, "Generate Original");
  }

  // E4D: explicit failed-Attempt retry — the dedicated /original/retry route,
  // same Generation identity, no rerender flag, exactly one POST per click.
  function _runRetryOriginal() {
    return _postOriginalAction(function () {
      return repo.retryOriginal(generationId);
    }, "Retry Original");
  }

  // ── Single Resume (F1A route / F6 frontend) ─────────────────────────────
  //
  // Explicit Resume of an INTERRUPTED ordinary Single: one bodyless POST to
  // /history-v2/generations/{id}/resume, no optimistic Attempt fabrication,
  // durable refetch/poll after server acknowledgment.  The frontend never
  // flips interrupted → running locally and never converts a refused Resume
  // into Retry — refusals surface truthfully and the button recovers.

  let _resumeInFlight = false;
  // Truthful refusal/network note for Resume.  The durable refetch after the
  // POST re-renders the section, so the message is carried across renders
  // and cleared on the next explicit click or a state change.
  let _resumeNoteOverride = "";

  async function _runResume() {
    if (_resumeInFlight || _originalInFlight || _closed) return;
    _resumeInFlight = true;
    _resumeNoteOverride = "";
    const btn = content.querySelector('[data-testid="history-v2-resume-run"]');
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Queuing\u2026";
    }
    let resp = null;
    let errMsg = "";
    try {
      resp = await repo.resumeGeneration(generationId);
    } catch (err) {
      errMsg = err && err.message ? err.message : "Request failed";
    }
    _resumeInFlight = false;
    if (_closed) return;

    if (errMsg) {
      _paintResumeNote("Resume failed: " + errMsg);
      reload();
      return;
    }
    if (resp && resp.accepted === false) {
      const errorCode = resp.errorCode ? String(resp.errorCode) : "";
      const outcome = resp.outcome ? String(resp.outcome) : "";
      if (outcome === "busy" || errorCode === "generation_busy") {
        _paintResumeNote("Generation is busy \u2014 an attempt is already active.");
      } else if (outcome === "irreproducible" || errorCode === "generation_not_reproducible") {
        _originalUnavailableNote = "This saved generation does not contain the exact immutable execution data required to resume.";
        _paintResumeNote(_originalUnavailableNote);
      } else if (errorCode === "dispatch_unavailable" || outcome === "dispatch_unavailable") {
        _paintResumeNote(resp.errorMessage || resp.message
          || "Resume is unavailable right now \u2014 no capable dispatcher is running. The interrupted run is retained.");
      } else if (errorCode === "resume_not_available" || errorCode === "generation_not_found") {
        _paintResumeNote(resp.errorMessage || resp.message || "This run can no longer be resumed.");
      } else {
        _paintResumeNote(resp.errorMessage || resp.message || "Resume was not accepted.");
      }
      reload();
      return;
    }
    // Accepted: durable refetch/poll renders the RETURNED attempt — no local
    // interrupted → running flip, no fabricated Attempt rows.
    _startOriginalPolling();
    reload();
  }

  function _paintResumeNote(text) {
    _resumeNoteOverride = text;
    const noteEl = content.querySelector('[data-testid="history-v2-generate-note"]');
    if (noteEl) noteEl.textContent = text;
  }

  // ── Configured-folder Export (F9 route / F10 frontend) ──────────────────
  //
  // Explicit server-side copy into the configured Studio output folder —
  // a THIRD distinct action beside View Original / Browser Download.  One
  // click = exactly one bodyless POST /history-v2/assets/{asset_id}/export;
  // no blob download, no legacy Save route, no local export-state mutation.
  // The durable refetch afterwards is the sole authority for exported /
  // missing / failed; the immediate response only paints a transient note.

  const _exportInFlight = new Set();

  async function _runExport(assetId) {
    const id = assetId == null ? "" : String(assetId);
    if (!id || _exportInFlight.has(id)) return null;
    _exportInFlight.add(id);
    let result = null;
    try {
      result = typeof repo.exportAsset === "function"
        ? await repo.exportAsset(id)
        : { ok: false, reason: "unavailable", message: "Export is not available in this repository mode" };
    } catch (err) {
      result = {
        ok: false,
        reason: "network_error",
        message: err && err.message ? err.message : "request failed",
      };
    }
    _exportInFlight.delete(id);
    if (_closed) return result;
    // Immediate truthful response while the durable refetch runs…
    _paintExportNote(exportResultNote(result));
    // …then the durable server projection re-renders exported/missing/failed.
    await reload();
    if (!_closed) _paintExportNote(exportResultNote(result));
    return result;
  }

  function _paintExportNote(text) {
    const noteEl = content.querySelector('[data-testid="' + EXPORT_NOTE_TESTID + '"]');
    if (noteEl) noteEl.textContent = text;
  }

  function buildGenerateSection(record) {
    const eligibility = generateOriginalEligibility(record, _repoModeInfo());
    const st = deriveOriginalActionState(record);
    const resume = deriveSingleResumeState(record);
    // F6 truthful retry naming: the /original/retry machinery is identical
    // for both labels — only the durable-state-derived presentation differs.
    const retryLabel = deriveRetryActionLabel(record);
    const note = el("div", {
      class: "comfymodal-studio-history-v2-action-note",
      "data-testid": "history-v2-generate-note",
      role: "status",
    });

    let btn = null;
    if (resume.state === "resume") {
      // Interrupted ordinary Single → Resume run.  The bodyless POST stays
      // authoritative; no option delta is sent and the output mode is never
      // altered in the frontend (Preview interrupted stays a Preview run).
      btn = el("button", {
        class: "comfymodal-primary-btn comfymodal-studio-history-v2-generate",
        "data-testid": "history-v2-resume-run",
        type: "button",
        text: "Resume",
        title: "Continues this interrupted run as a new attempt under the same generation.",
        onclick: function () { _runResume(); },
      });
      note.textContent = _resumeNoteOverride
        || "Run interrupted \u2014 Resume re-executes the saved request without changing it.";
    } else if (resume.state === "unavailable") {
      // Explicit replay-incapability projected durably (F5 replay_capable /
      // irreproducible): disabled with a truthful reason BEFORE any click.
      btn = el("button", {
        class: "comfymodal-primary-btn comfymodal-studio-history-v2-generate",
        "data-testid": "history-v2-resume-run",
        type: "button",
        text: "Resume unavailable",
        disabled: true,
        title: resume.reason,
      });
      note.textContent = resume.reason;
    } else if (!eligibility.eligible || _originalUnavailableNote) {
      const message = _originalUnavailableNote || eligibility.message;
      btn = el("button", {
        class: "comfymodal-primary-btn comfymodal-studio-history-v2-generate",
        "data-testid": "history-v2-generate-original",
        type: "button",
        text: "Generate Original unavailable",
        disabled: true,
        title: message,
      });
      note.textContent = message;
    } else if (st.phase === "active") {
      btn = el("button", {
        class: "comfymodal-primary-btn comfymodal-studio-history-v2-generate",
        "data-testid": "history-v2-generate-original",
        type: "button",
        text: "Generating Original\u2026",
        disabled: true,
      });
      note.textContent = "Original attempt "
        + (st.latestAttempt && st.latestAttempt.status ? String(st.latestAttempt.status) : "queued")
        + " \u2014 Preview retained.";
    } else if (st.phase === "success") {
      // An Original already exists: the default UI spends no extra execution.
      // Generate Again is the ONLY rerender path and always sends rerender=true.
      btn = el("button", {
        class: "comfymodal-secondary-btn comfymodal-studio-history-v2-generate",
        "data-testid": "history-v2-generate-again",
        type: "button",
        text: "Generate Again",
        title: "Rerun the frozen execution plan as a new Original attempt (rerender).",
        onclick: function () { _runGenerateOriginal(true); },
      });
      note.textContent = "Original available \u2014 use View Original to display it. Generate Again reruns it as a new attempt.";
    } else if (st.phase === "failed") {
      // Plain failed ordinary run → "Retry run"; explicit Original derivative
      // failure (Preview-then-Original story, prior success, or retained
      // usable Original) → "Retry Original".  Both POST /original/retry.
      const isPlainRun = retryLabel !== "Retry Original";
      btn = el("button", {
        class: "comfymodal-primary-btn comfymodal-studio-history-v2-generate",
        "data-testid": "history-v2-retry-original",
        type: "button",
        text: retryLabel,
        title: isPlainRun
          ? "Creates a new attempt on the backend under the same generation."
          : "Creates a new Original attempt on the backend under the same generation.",
        onclick: function () { _runRetryOriginal(); },
      });
      const latestError = st.latestAttempt && st.latestAttempt.error ? String(st.latestAttempt.error) : "";
      note.textContent = isPlainRun
        ? "Run failed." + (latestError ? " (" + latestError + ")" : "")
        : "Original failed \u2014 Preview retained."
          + (latestError ? " (" + latestError + ")" : "");
    } else if (st.busyGeneration) {
      // Preview still executing: non-destructive status, no retry spam.
      btn = el("button", {
        class: "comfymodal-primary-btn comfymodal-studio-history-v2-generate",
        "data-testid": "history-v2-generate-original",
        type: "button",
        text: "Generate Original",
        disabled: true,
        title: "Generation busy \u2014 wait for the current run to finish.",
      });
      note.textContent = "Generation busy \u2014 Preview still running.";
    } else {
      btn = el("button", {
        class: "comfymodal-primary-btn comfymodal-studio-history-v2-generate",
        "data-testid": "history-v2-generate-original",
        type: "button",
        text: "Generate Original",
        onclick: function () { _runGenerateOriginal(false); },
      });
    }

    return el("div", { class: "comfymodal-studio-history-v2-section" }, [
      el("div", { class: "comfymodal-studio-history-v2-section-title", text: "Actions" }),
      btn,
      note,
    ]);
  }

  // Full-width overflow sections: attempt history, errors, and the Generate
  // Original action sit below the timing flow, spanning the overlay body.
  // (The Run / Run Data / Metadata right column and the zoom stage both come
  // from the one shared viewer in studio-ui.js — there is no second overlay
  // implementation here.)
  function buildOverflowSections(record) {
    const sections = [];
    const attempts = Array.isArray(record.attempts) ? record.attempts : [];
    if (attempts.length > 0) {
      const sec = _section("Attempts", attempts.map(function (a, i) {
        return el("div", { class: "comfymodal-studio-history-v2-attempt" }, [
          el("div", { class: "comfymodal-studio-history-v2-attempt-line" }, [
            el("span", { class: "comfymodal-studio-history-v2-attempt-purpose", text: historyAttemptPurposeLabel(a.mode || a.purpose) }),
            _statusChip(a.status || "running"),
            a.startedAt ? el("span", { class: "comfymodal-studio-history-v2-row-value", text: _shortDateTime(a.startedAt) }) : null,
            a.durationMs != null ? el("span", { class: "comfymodal-studio-history-v2-row-value", text: _formatDuration(a.durationMs) }) : null,
          ]),
          a.error ? el("div", { class: "comfymodal-studio-history-v2-attempt-error", text: String(a.error) }) : null,
        ]);
      }));
      if (sec) { sec.classList.add("comfymodal-studio-history-v2-overflow-section"); sections.push(sec); }
    }
    const errors = Array.isArray(record.errors) ? record.errors : [];
    if (errors.length > 0) {
      // NOTE: children must be a FLAT array (like _section's .concat pattern);
      // el() only flattens one level, so a nested errors.map() array would
      // throw "parameter 1 is not of type 'Node'" and blank the overlay.
      sections.push(el("div", { class: "comfymodal-studio-history-v2-section comfymodal-studio-history-v2-section-error comfymodal-studio-history-v2-overflow-section" }, [
        el("div", { class: "comfymodal-studio-history-v2-section-title", text: "Errors" }),
      ].concat(errors.map(function (e) {
        const code = (e && e.code) ? e.code : "error";
        const message = (e && e.message) ? String(e.message) : "";
        return el("div", { class: "comfymodal-studio-history-v2-row comfymodal-studio-history-v2-error-line" },
          [el("span", { class: "comfymodal-studio-history-v2-row-key", text: code }),
           message ? el("span", { class: "comfymodal-studio-history-v2-row-value", text: message }) : null]);
      }))));
    }
    const generate = buildGenerateSection(record);
    generate.classList.add("comfymodal-studio-history-v2-overflow-section");
    sections.push(generate);
    return sections;
  }

  function _renderDetail(record) {
    currentRecord = record;
    closeAnyMenu();
    clearContent();
    // Same shared resolver every full-size output surface uses: one record
    // projection, one image policy, one timing source.
    const viewer = resolveViewerInput(record);
    const args = resolveViewerShellArgs(viewer, shellAdapters);
    sharedShell.render(args.record, args);
    _ensureDialogFocus();
  }

  function _renderLoading() {
    clearContent();
    content.appendChild(makeCloseBtn());
    content.appendChild(renderLoadingState({
      label: "Loading generation\u2026",
      size: "page",
      testid: "history-v2-detail-loading",
    }));
    _ensureDialogFocus();
  }

  function _renderNotFound() {
    clearContent();
    content.appendChild(makeCloseBtn());
    content.appendChild(el("div", { class: "comfymodal-studio-history-v2-state" }, [
      el("p", { text: "Generation not found" }),
      el("button", {
        class: "comfymodal-secondary-btn",
        type: "button",
        text: "Close",
        onclick: function () { close(); },
      }),
    ]));
    _ensureDialogFocus();
  }

  function _isNotFound(record) {
    if (!record) return true;
    // Only the repository's placeholder records (lookup failed / not found)
    // carry the load_failed / not_found sentinel error code.  A legitimate
    // failed zero-output generation also has errors (attempt_failed) and no
    // featured output, but must still render its real status/error/attempt/
    // metadata instead of the "Generation not found" placeholder.
    return Array.isArray(record.errors)
      && record.errors.some(function (e) {
        const code = e && e.code;
        return code === "load_failed" || code === "not_found";
      })
      && record.outputCount === 0
      && !(record.featuredOutput
        && (record.featuredOutput.previewUrl || record.featuredOutput.thumbUrl || record.featuredOutput.originalUrl));
  }

  async function reload() {
    let fresh = null;
    try {
      fresh = await repo.getGeneration(generationId);
    } catch (err) {
      fresh = null;
    }
    if (_closed) return;
    if (_isNotFound(fresh)) {
      _renderNotFound();
      return;
    }
    _renderDetail(fresh);
  }

  // ── Mount ───────────────────────────────────────────────────────────────
  // Routed-page anchor (I9A convergence): the overlay lives on document.body,
  // outside the shell's page container. A routed page swap (Back/Forward
  // through the hash authority) can unmount the History page while this
  // dialog is open; without an anchor, the stale full-screen dialog survives
  // over the newly mounted page and intercepts its pointer events. Anchored
  // to the LIVE History page root (the I5 compare-tray contract), it closes
  // itself the moment its page is torn down. Ordinary page switching is
  // unaffected: the modal backdrop blocks the nav while the dialog is open.
  const _pageAnchor =
    typeof document.querySelector === "function"
      ? document.querySelector('[data-testid="history-v2-page"]')
      : null;
  if (
    _pageAnchor &&
    _pageAnchor.parentNode &&
    typeof MutationObserver === "function"
  ) {
    _pageAnchorObserver = new MutationObserver(function () {
      if (_closed || _pageAnchor.isConnected) return;
      close();
    });
    _pageAnchorObserver.observe(_pageAnchor.parentNode, { childList: true });
  }

  document.body.appendChild(overlay);
  _renderLoading();

  let record = null;
  try {
    record = await repo.getGeneration(generationId);
  } catch (err) {
    record = null;
  }
  if (_closed) return overlay;
  if (_isNotFound(record)) {
    _renderNotFound();
    return overlay;
  }
  _renderDetail(record);

  return overlay;
}
