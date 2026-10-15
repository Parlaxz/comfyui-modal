// Modal Studio — Shared History gallery picker
//
// One gallery picker used by every surface that needs a History image:
//   - pair mode: the topbar Compare picker (A/B slots, Swap, Compare)
//   - single mode: "Browse history" for image inputs (highlight, Use image)
//
// Data comes only from createHistoryRepository + listFeed with the same
// query shape as the History page (search/statuses/kinds/favoriteOnly/
// hasImage/sort/limit/cursor). Card thumbnails render through the feed
// asset policy (thumbUrl then previewUrl, never an eager Original) via the
// shared buildHistoryCard renderer from studio-history-v2.js, while pick
// descriptors resolve the full-resolution compare URL (Original first) so
// the compare view never upscales a 256px thumbnail.
//
// Copy uses grounded plain words only: "Compare images", "Select A",
// "Select B", "Use image", "Back", "Change A", "Change B", "Swap",
// "Current canvas", "Current canvas (no image)".

import { el, registerLayerHandler } from "./studio-ui.js";
import { createHistoryRepository, selectCompareAsset } from "./history-v2-repository.js";
import { buildHistoryCard } from "./studio-history-v2.js";

const PICKER_LIMIT = 24;

// In-memory filter retention across Change-A/B reopenings within one
// comparison flow (module memory only — never persisted). The viewer passes
// retainFilters with the live pair; a fresh topbar open (no initials)
// starts clean.
let _retainedFilters = null;

// Mirror of the History feed's short date/time (local module copy so the
// picker never depends on feed internals beyond buildHistoryCard).
function _pickDateTime(iso) {
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

// Descriptor label (<=80 chars, matching normalizeImageDescriptor): workflow
// name first, then a truncated prompt, then the honest fallback.
function _pickLabel(record) {
  const rec = record && typeof record === "object" ? record : {};
  let label = "";
  if (typeof rec.workflow === "string" && rec.workflow.trim()) label = rec.workflow.trim();
  else if (typeof rec.prompt === "string" && rec.prompt.trim()) label = rec.prompt.trim().slice(0, 60);
  if (!label) label = "History image";
  if (label.length > 80) label = label.slice(0, 80);
  return label;
}

// Descriptor meta (<=120 chars): "Oct 14, 2:58 AM · Qwen Edit" style from
// startedAt + workflow name.
function _pickMeta(record) {
  const rec = record && typeof record === "object" ? record : {};
  const parts = [];
  const when = _pickDateTime(rec.startedAt);
  if (when) parts.push(when);
  if (typeof rec.workflow === "string" && rec.workflow.trim()) parts.push(rec.workflow.trim());
  const meta = parts.join(" \u00b7 ");
  return meta.length > 120 ? meta.slice(0, 120) : meta;
}

// A History record becomes a pick only when the compare policy resolves a
// usable full-resolution asset URL for it (Original > Data Saver > Thumbnail
// from already-projected URLs — no eager fetch; card GRID rendering still
// shows lightweight thumbs via buildHistoryCard).
function _recordPick(record) {
  if (!record || typeof record !== "object") return null;
  const asset = selectCompareAsset(record.featuredOutput || {});
  if (!asset.url) return null;
  return {
    url: asset.url,
    label: _pickLabel(record),
    meta: _pickMeta(record),
    record: record,
    current: false,
  };
}

// Caller-supplied initials are plain {url,label,meta} descriptors (e.g.
// from getCompareState()): accept them as picks without a record.
function _asPick(initial) {
  if (!initial || typeof initial !== "object") return null;
  const url = typeof initial.url === "string" ? initial.url.trim() : "";
  if (!url) return null;
  let label = typeof initial.label === "string" && initial.label.trim() ? initial.label.trim() : "Image";
  if (label.length > 80) label = label.slice(0, 80);
  let meta = typeof initial.meta === "string" ? initial.meta.trim() : "";
  if (meta.length > 120) meta = meta.slice(0, 120);
  return {
    url: url,
    label: label,
    meta: meta,
    record: initial.record && typeof initial.record === "object" ? initial.record : null,
    current: !!initial.current,
  };
}

/**
 * Open the shared History gallery picker.
 *
 *   mode: "single" | "pair"
 *   initialA / initialB: optional {url,label,meta} descriptors (pair only)
 *   armedSide: optional "a" | "b" preselecting which pair side the next
 *     card click replaces (viewer Change-A/Change-B entry)
 *   retainFilters: when true with a live pair, restore the previous
 *     query/filters/sort kept in module memory (Change-A/B reopen)
 *   currentCanvasUrl: thumbnail URL for the "Current canvas" first card
 *     ("" renders the honest disabled "Current canvas (no image)" state)
 *   apiBase: History API base for the repository
 *   testid: base testid for single-mode dialog/panel testids
 *     (<base>-history-dialog / <base>-history-panel); pair mode always
 *     uses the compare-picker testids
 *   title: optional panel title override
 *   historyItems: optional [{url,label}] fallback when the repository
 *     cannot load (truthfully labeled, same as the previous browser)
 *   onConfirm: single mode → onConfirm(pick {url,label,meta,record});
 *     pair mode → onConfirm(pickA, pickB)
 *   onClose: optional dismissal callback
 */
export function openHistoryPicker(options) {
  const opts = options && typeof options === "object" ? options : {};
  const pair = opts.mode === "pair";
  const base = typeof opts.testid === "string" && opts.testid ? opts.testid : "shelf-image";
  const selected = { a: pair ? _asPick(opts.initialA) : null, b: pair ? _asPick(opts.initialB) : null };
  // Viewer Change-A/Change-B entry names the side the next card click
  // replaces; otherwise the emptier side is armed (B when A is filled).
  const wantSide = opts.armedSide === "a" || opts.armedSide === "b" ? opts.armedSide : null;
  let armed = wantSide || (selected.a && !selected.b ? "b" : "a");
  let records = [];
  let cursor = null;
  let hasMore = false;
  let request = 0;
  let repoPromise = null;
  let dupTimer = null;
  // Restore the retained query only for a live-pair reopen (Change/Back);
  // a fresh topbar open carries no initials and starts clean.
  const restoreFilters = !!(pair && opts.retainFilters && selected.a && selected.b && _retainedFilters);

  function getRepo() {
    if (!repoPromise) {
      try {
        repoPromise = Promise.resolve(createHistoryRepository({ apiBase: opts.apiBase || "/comfymodal" }));
      } catch (err) {
        repoPromise = Promise.reject(err);
      }
    }
    return repoPromise;
  }

  const overlay = el("div", {
    class: pair
      ? "comfymodal-studio-compare-picker-overlay comfymodal-studio-history-gallery-overlay"
      : "comfymodal-studio-history-dialog-overlay comfymodal-studio-history-gallery-overlay",
    "data-testid": pair ? "compare-picker" : base + "-history-dialog",
    role: "dialog",
    "aria-label": pair ? "Choose images to compare" : "Choose an image from history",
  });
  overlay.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,0.72);z-index:10100;"
    + "display:flex;align-items:center;justify-content:center;padding:clamp(12px,3vw,40px);";
  const panel = el("div", {
    class: pair
      ? "comfymodal-studio-history-gallery comfymodal-studio-compare-picker"
      : "comfymodal-studio-history-gallery comfymodal-studio-history-dialog",
    "data-testid": pair ? "compare-picker-panel" : base + "-history-panel",
  });
  panel.style.cssText = "background:#111;border:1px solid #2a2a2a;border-radius:8px;padding:12px;"
    + "max-width:min(1120px,94vw);width:100%;max-height:88vh;display:flex;flex-direction:column;"
    + "overflow:auto;gap:10px;";

  const heading = el("h2", {
    text: typeof opts.title === "string" && opts.title ? opts.title : (pair ? "Compare images" : "Choose an image"),
    style: "margin:0;font-size:15px;",
  });
  const instruction = el("p", {
    class: "comfymodal-studio-history-gallery-instruction",
    "data-testid": "history-picker-instruction",
    text: pair ? "Choose image A. Click a slot to choose which side to replace." : "Select an image, then Use image.",
    style: "margin:0;font-size:11px;color:#888;",
  });

  // Pair-only A/B slot buttons: clicking a slot arms that side.
  const slots = el("div", {
    class: "comfymodal-studio-history-gallery-slots",
    hidden: !pair,
    // NOTE: hidden alone does not hide against an inline display:flex
    // (inline style beats the UA [hidden] rule), so single mode sets
    // display:none explicitly.
    style: pair ? "display:flex;gap:8px;" : "display:none;",
  });
  const slotEls = {};
  function makeSlot(side) {
    const key = side.toLowerCase();
    const button = el("button", {
      type: "button",
      class: "comfymodal-studio-history-gallery-slot",
      "data-testid": "history-picker-slot-" + key,
      "aria-pressed": armed === key ? "true" : "false",
      text: side === "A" ? "Select A" : "Select B",
      style: "flex:1;display:flex;align-items:center;gap:6px;text-align:left;",
    });
    button.addEventListener("click", function () { armed = key; clearDup(); paint(); });
    slotEls[key] = button;
    return button;
  }
  if (pair) {
    slots.appendChild(makeSlot("A"));
    slots.appendChild(makeSlot("B"));
  }

  // Controls row: search, status (All/Completed/Failed), favorites-only,
  // sort (Newest/Oldest).
  const toolbar = el("div", {
    class: "comfymodal-studio-history-gallery-toolbar",
    style: "display:flex;gap:8px;flex-wrap:wrap;",
  });
  const search = el("input", {
    type: "search",
    class: "comfymodal-input",
    placeholder: "Search history",
    "aria-label": "Search history",
    "data-testid": "history-picker-search",
  });
  const status = el("select", {
    class: "comfymodal-input",
    "aria-label": "Filter by status",
    "data-testid": "history-picker-filter-status",
  }, [
    el("option", { value: "", text: "All statuses" }),
    el("option", { value: "completed", text: "Completed" }),
    el("option", { value: "failed", text: "Failed" }),
  ]);
  const favLabel = el("label", {
    style: "display:flex;align-items:center;gap:4px;font-size:11px;color:#aaa;",
  });
  const favOnly = el("input", {
    type: "checkbox",
    "aria-label": "Favorites only",
    "data-testid": "history-picker-filter-fav",
  });
  favLabel.appendChild(favOnly);
  favLabel.appendChild(el("span", { text: "Favorites only" }));
  const sort = el("select", {
    class: "comfymodal-input",
    "aria-label": "Sort history",
    "data-testid": "history-picker-sort",
  }, [
    el("option", { value: "newest", text: "Newest" }),
    el("option", { value: "oldest", text: "Oldest" }),
  ]);
  toolbar.appendChild(search);
  toolbar.appendChild(status);
  toolbar.appendChild(favLabel);
  toolbar.appendChild(sort);
  // Change-A/B reopen within one comparison flow keeps the previous
  // query/filters/sort (module memory only, never persisted).
  if (restoreFilters && _retainedFilters) {
    try {
      if (typeof _retainedFilters.search === "string") search.value = _retainedFilters.search;
      if (typeof _retainedFilters.status === "string") status.value = _retainedFilters.status;
      favOnly.checked = !!_retainedFilters.favOnly;
      if (typeof _retainedFilters.sort === "string" && _retainedFilters.sort) sort.value = _retainedFilters.sort;
    } catch (err) { /* defaults stand */ }
  }
  function rememberFilters() {
    if (!pair) return;
    _retainedFilters = {
      search: search.value || "",
      status: status.value || "",
      favOnly: !!favOnly.checked,
      sort: sort.value || "newest",
    };
  }

  const stateEl = el("div", {
    class: "comfymodal-studio-history-gallery-state",
    "data-testid": "history-picker-count",
    text: "Loading history\u2026",
    style: "font-size:12px;color:#888;",
  });
  // Duplicate-pick notice (also the pair-conflict explanation): hidden
  // until a pick already on the other side is rejected.
  const dupEl = el("div", {
    class: "comfymodal-studio-history-gallery-dup",
    "data-testid": "history-picker-dup-message",
    text: "",
    hidden: true,
    role: "status",
    style: "font-size:12px;color:#e8b34b;",
  });
  // Reuse the History feed grid CSS pattern with the picker density.
  // The grid is the panel's own scroller (header/toolbar/footer stay
  // fixed); bottom padding reserves space so the footer never covers
  // last-row card text.
  const grid = el("div", {
    class: "comfymodal-studio-history-v2-grid comfymodal-studio-history-gallery-grid",
    "data-testid": "history-picker-grid",
  });
  grid.style.cssText = "grid-template-columns:repeat(auto-fill,minmax(150px,1fr));"
    + "overflow:auto;flex:1 1 auto;min-height:120px;padding-bottom:12px;";
  const moreBtn = el("button", {
    type: "button",
    class: "comfymodal-secondary-btn",
    text: "Load more",
    "data-testid": "history-picker-more",
    hidden: true,
  });

  // Sticky bottom bar: Cancel, Swap (pair only), Confirm.
  const cancelBtn = el("button", {
    type: "button",
    class: "comfymodal-secondary-btn",
    text: "Cancel",
    "data-testid": pair ? "compare-picker-close" : "history-picker-cancel",
  });
  // Alias for the other mode's Cancel testid: pair mode keeps
  // compare-picker-close while documenting history-picker-cancel (and vice
  // versa), so the Cancel control stays addressable on both surfaces.
  cancelBtn.setAttribute("data-testid-alias", pair ? "history-picker-cancel" : "compare-picker-close");
  const swapBtn = el("button", {
    type: "button",
    class: "comfymodal-secondary-btn",
    text: "Swap",
    "data-testid": "history-picker-swap",
    hidden: !pair,
    disabled: true,
  });
  const confirmBtn = el("button", {
    type: "button",
    class: "comfymodal-primary-btn",
    text: pair ? "Compare" : "Use image",
    "data-testid": pair ? "compare-start" : "history-picker-confirm",
    disabled: true,
  });
  // Single-mode selection summary beside Use image: compact thumbnail +
  // label of the picked image, hidden until something is picked.
  // NOTE: hidden alone does not hide against an inline display:flex
  // (inline style beats the UA [hidden] rule), so the hidden state sets
  // display:none explicitly and paint() restores display:flex.
  const singleSel = el("span", {
    class: "comfymodal-studio-history-gallery-selection",
    "data-testid": "history-picker-selection",
    hidden: true,
    style: "display:none;align-items:center;gap:6px;font-size:11px;color:#aaa;"
      + "margin-right:auto;max-width:50%;overflow:hidden;",
  });
  const foot = el("div", {
    class: "comfymodal-studio-history-gallery-footer",
    style: "display:flex;gap:8px;justify-content:flex-end;align-items:center;position:sticky;bottom:0;"
      + "background:#111;padding:8px 0 0;",
  }, [singleSel, cancelBtn, swapBtn, confirmBtn]);

  const head = el("div", {
    class: "comfymodal-studio-history-gallery-head",
    style: "display:flex;flex-direction:column;gap:8px;position:sticky;top:0;background:#111;z-index:3;padding-bottom:2px;",
  }, [el("div", {}, [heading, instruction]), slots]);
  // Header/toolbar stay fixed while the grid scrolls internally, so the
  // panel itself never scrolls.
  panel.style.overflow = "hidden";
  toolbar.style.cssText += "position:sticky;top:0;background:#111;z-index:3;";
  panel.appendChild(head);
  panel.appendChild(toolbar);
  panel.appendChild(stateEl);
  panel.appendChild(dupEl);
  panel.appendChild(grid);
  panel.appendChild(moreBtn);
  panel.appendChild(foot);
  overlay.appendChild(panel);
  document.body.appendChild(overlay);

  // Card elements are created once per load and updated in place by paint()
  // (badges/highlights), so focus is never destroyed by re-rendering.
  let cardEls = [];

  function canvasUrl() {
    return typeof opts.currentCanvasUrl === "string" ? opts.currentCanvasUrl : "";
  }

  function pickSide(pick) {
    if (!pick || !pick.url) return null;
    if (selected.a && selected.a.url === pick.url) return "a";
    if (pair && selected.b && selected.b.url === pick.url) return "b";
    return null;
  }

  function clearDup() {
    try {
      if (dupTimer) { clearTimeout(dupTimer); dupTimer = null; }
    } catch (err) { /* noop */ }
    dupEl.textContent = "";
    dupEl.setAttribute("hidden", "");
  }

  function showDup(text) {
    dupEl.textContent = text;
    dupEl.removeAttribute("hidden");
    try {
      if (dupTimer) clearTimeout(dupTimer);
      dupTimer = setTimeout(clearDup, 4000);
    } catch (err) { /* persistent until next action */ }
  }

  function slotText(side, value) {
    if (!value) return side === "a" ? "Select A" : "Select B";
    return side.toUpperCase() + " \u2014 " + value.label
      + (value.meta ? " \u00b7 " + value.meta : "");
  }

  function paintInstruction() {
    if (!pair) return;
    var side = armed === "b" ? "B" : "A";
    var filled = !!selected[armed];
    var lead = !filled
      ? (armed === "b" ? "Choose image B" : "Choose image A")
      : "Choose a replacement for " + side;
    instruction.textContent = lead + ". Click a slot to choose which side to replace.";
  }

  function paint() {
    if (pair) {
      paintInstruction();
      ["a", "b"].forEach(function (side) {
        const value = selected[side];
        const btn = slotEls[side];
        if (!btn) return;
        while (btn.firstChild) btn.removeChild(btn.firstChild);
        if (value && value.url) {
          try {
            const thumb = document.createElement("img");
            thumb.setAttribute("src", value.url);
            thumb.setAttribute("alt", "");
            thumb.setAttribute("aria-hidden", "true");
            thumb.style.cssText = "width:28px;height:28px;object-fit:cover;border-radius:4px;flex:none;";
            btn.appendChild(thumb);
          } catch (err) { /* text-only fallback */ }
        }
        btn.appendChild(document.createTextNode(slotText(side, value)));
        btn.setAttribute("aria-pressed", armed === side ? "true" : "false");
        // Armed target clarity: the side the next click replaces carries
        // a clear accent outline.
        try {
          if (armed === side) {
            btn.style.outline = "2px solid #4da3ff";
            btn.style.outlineOffset = "1px";
          } else {
            btn.style.outline = "";
            btn.style.outlineOffset = "";
          }
        } catch (err) { /* decorative only */ }
      });
      swapBtn.disabled = !(selected.a && selected.b);
      confirmBtn.disabled = !(selected.a && selected.b && selected.a.url !== selected.b.url);
      singleSel.setAttribute("hidden", "");
      singleSel.style.display = "none";
    } else {
      confirmBtn.disabled = !(selected.a && selected.a.url);
      // Single-select clarity: compact thumbnail + label beside Use image.
      while (singleSel.firstChild) singleSel.removeChild(singleSel.firstChild);
      if (selected.a && selected.a.url) {
        try {
          const thumb = document.createElement("img");
          thumb.setAttribute("src", selected.a.url);
          thumb.setAttribute("alt", "");
          thumb.setAttribute("aria-hidden", "true");
          thumb.style.cssText = "width:24px;height:24px;object-fit:cover;border-radius:4px;flex:none;";
          singleSel.appendChild(thumb);
        } catch (err) { /* label-only fallback */ }
        singleSel.appendChild(document.createTextNode(selected.a.label || "Selected image"));
        singleSel.removeAttribute("hidden");
        singleSel.style.display = "flex";
      } else {
        singleSel.setAttribute("hidden", "");
        singleSel.style.display = "none";
      }
    }
    cardEls.forEach(function (entry) {
      const side = pickSide(entry.pick);
      const cardEl = entry.el;
      cardEl.setAttribute("aria-selected", side ? "true" : "false");
      if (!pair) {
        // Single mode: the picked card carries a visible checkmark.
        const want = selected.a && entry.pick && entry.pick.url === selected.a.url
          ? "history-picker-selected" : null;
        const mark = cardEl.querySelector('[data-testid="history-picker-selected"]');
        if (mark && (!want || mark.getAttribute("data-testid") !== want)) mark.remove();
        if (want && !cardEl.querySelector('[data-testid="' + want + '"]')) {
          try { cardEl.style.position = "relative"; } catch (err) { /* best-effort */ }
          cardEl.appendChild(el("span", {
            class: "comfymodal-studio-history-picker-check",
            "data-testid": want,
            text: "\u2713",
            "aria-hidden": "true",
            style: "position:absolute;top:6px;right:6px;background:#1c7c3c;color:#fff;"
              + "border-radius:50%;font-size:12px;font-weight:700;line-height:1;"
              + "width:20px;height:20px;display:flex;align-items:center;justify-content:center;z-index:2;",
          }));
        }
        return;
      }
      const badge = cardEl.querySelector('[data-testid="history-picker-badge-a"],[data-testid="history-picker-badge-b"]');
      const want = side ? "history-picker-badge-" + side : null;
      if (badge && (!want || badge.getAttribute("data-testid") !== want)) badge.remove();
      if (want && !cardEl.querySelector('[data-testid="' + want + '"]')) {
        const marker = el("span", {
          class: "comfymodal-studio-history-picker-badge",
          "data-testid": want,
          text: side.toUpperCase(),
          style: "position:absolute;top:6px;left:6px;background:#0a0a0a;color:#fff;"
            + "border:1px solid #555;border-radius:4px;font-size:11px;font-weight:700;"
            + "padding:1px 6px;z-index:2;",
        });
        try { cardEl.style.position = "relative"; } catch (err) { /* best-effort */ }
        cardEl.appendChild(marker);
      }
    });
  }

  function choose(pick) {
    if (!pick || !pick.url) return;
    if (!pair) {
      selected.a = pick;
    } else {
      if (selected[armed] && selected[armed].url === pick.url) return;
      // Same-image dead end: a pick already on the other side is
      // rejected with an explanation — the pair is preserved.
      const other = armed === "a" ? "b" : "a";
      if (selected[other] && selected[other].url === pick.url) {
        showDup("Already selected as " + other.toUpperCase()
          + ". Choose another image for " + armed.toUpperCase() + ".");
        return;
      }
      clearDup();
      selected[armed] = pick;
      if (armed === "a") armed = "b";
    }
    paint();
  }

  // Empty canvas: with no current image there is no dead grid card — a
  // compact note lives outside the grid instead. With a canvas URL the
  // first grid card stays (Change reopenings preserve it via
  // currentCanvasUrl).
  function currentCanvasNote() {
    return el("div", {
      class: "comfymodal-studio-history-gallery-canvas-note",
      "data-testid": "history-picker-current",
      text: "Current canvas (no image)",
      style: "font-size:11px;color:#666;",
    });
  }

  function currentCanvasCard() {
    const url = canvasUrl();
    const has = !!url;
    const cardEl = el("article", {
      class: "comfymodal-studio-history-v2-card comfymodal-studio-history-v2-generation-card"
        + (has ? "" : " is-disabled"),
      "data-testid": "history-picker-current",
      "data-gallery-url": url || "",
      tabindex: has ? "0" : "-1",
      role: "button",
      "aria-selected": "false",
      "aria-disabled": has ? "false" : "true",
      "aria-label": has ? "Current canvas" : "Current canvas (no image)",
    });
    if (has) {
      cardEl.appendChild(el("img", {
        class: "comfymodal-studio-history-v2-thumb-img",
        src: url,
        alt: "Current canvas",
        loading: "lazy",
      }));
    } else {
      cardEl.appendChild(el("div", {
        class: "comfymodal-studio-history-v2-noimage",
        text: "No image",
      }));
    }
    cardEl.appendChild(el("strong", { text: has ? "Current canvas" : "Current canvas (no image)" }));
    if (has) {
      const pick = { url: url, label: "Current canvas", meta: "", record: null, current: true };
      cardEl.addEventListener("click", function () { choose(pick); });
      cardEl.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); choose(pick); }
      });
      cardEls.push({ el: cardEl, pick: pick });
    }
    return cardEl;
  }

  function recordCard(record) {
    const pick = _recordPick(record);
    if (!pick) return null;
    const side = pickSide(pick);
    const cardEl = buildHistoryCard(record, {
      repo: pickerRepo,
      testid: "history-picker-card",
      statusChipMode: "failed-only",
      promptLimit: 140,
      badge: side,
      onClick: function () { choose(pick); },
    });
    cardEl.setAttribute("data-gallery-url", pick.url);
    cardEls.push({ el: cardEl, pick: pick });
    return cardEl;
  }

  let pickerRepo = null;

  function render() {
    while (grid.firstChild) grid.removeChild(grid.firstChild);
    cardEls = [];
    // Compact canvas note (no-image case) lives outside the grid; remove
    // any stale one before re-adding.
    try {
      const staleNote = panel.querySelector('[data-testid="history-picker-current"]');
      if (staleNote && staleNote.parentNode !== grid) staleNote.parentNode.removeChild(staleNote);
    } catch (err) { /* best-effort */ }
    if (canvasUrl()) {
      grid.appendChild(currentCanvasCard());
    } else {
      panel.insertBefore(currentCanvasNote(), grid);
    }
    let shown = 0;
    records.forEach(function (record) {
      const cardEl = recordCard(record);
      if (cardEl) {
        grid.appendChild(cardEl);
        shown += 1;
      }
    });
    // Lightweight result count near the controls ("N images" unfiltered,
    // "N matches" once a query/filter/sort narrows the feed).
    const filtered = !!(search.value || status.value || (favOnly && favOnly.checked));
    if (shown === 0 && !canvasUrl()) {
      stateEl.hidden = false;
      stateEl.textContent = "No matching history images.";
    } else {
      stateEl.hidden = false;
      stateEl.textContent = shown + (filtered ? " matches" : " images");
    }
    moreBtn.hidden = !hasMore;
    paint();
  }

  function load(reset) {
    const token = ++request;
    if (reset) {
      records = [];
      cursor = null;
      hasMore = false;
      cardEls = [];
      while (grid.firstChild) grid.removeChild(grid.firstChild);
    }
    stateEl.hidden = false;
    stateEl.textContent = "Loading history\u2026";
    moreBtn.hidden = true;
    getRepo().then(function (repo) {
      pickerRepo = repo;
      return repo.listFeed({
        limit: PICKER_LIMIT,
        cursor: reset ? null : cursor,
        search: search.value || "",
        kinds: ["generation"],
        statuses: status.value ? [status.value] : [],
        favoriteOnly: !!favOnly.checked,
        hasImage: true,
        sort: sort.value || "newest",
      });
    }).then(function (page) {
      if (token !== request) return;
      const items = (page && page.items) || [];
      records = reset ? items.slice() : records.concat(items);
      cursor = page ? page.nextCursor : null;
      hasMore = page ? (page.hasMore != null ? !!page.hasMore : !!page.nextCursor) : false;
      render();
      if (records.length === 0 && !(opts.historyItems || []).length) {
        stateEl.hidden = false;
        stateEl.textContent = "No matching history images.";
      }
    }).catch(function () {
      if (token !== request) return;
      // Truthful fallback: caller-supplied items only, never demo data.
      const fallback = Array.isArray(opts.historyItems) ? opts.historyItems : [];
      records = reset ? [] : records;
      if (reset) {
        records = fallback
          .filter(function (item) { return item && item.url; })
          .map(function (item, i) {
            return {
              id: "fallback-" + i,
              status: "completed",
              workflow: item.label || "",
              prompt: item.label || "",
              startedAt: "",
              favorite: false,
              featuredOutput: { thumbUrl: item.url },
            };
          });
      }
      render();
    });
  }

  let debounce = null;
  // Previously focused element: focus moves into the picker on open and
  // is restored on dismiss (viewer Change flow returns to its button).
  let openerFocus = null;
  try {
    openerFocus = document.activeElement && document.activeElement.focus
      ? document.activeElement : null;
  } catch (err) { openerFocus = null; }
  search.addEventListener("input", function () {
    rememberFilters();
    if (debounce) clearTimeout(debounce);
    debounce = setTimeout(function () { load(true); }, 200);
  });
  status.addEventListener("change", function () { rememberFilters(); load(true); });
  favOnly.addEventListener("change", function () { rememberFilters(); load(true); });
  sort.addEventListener("change", function () { rememberFilters(); load(true); });
  moreBtn.addEventListener("click", function () { if (hasMore) load(false); });
  cancelBtn.addEventListener("click", close);
  overlay.addEventListener("click", function (e) { if (e.target === overlay) close(); });
  swapBtn.addEventListener("click", function () {
    const t = selected.a;
    selected.a = selected.b;
    selected.b = t;
    clearDup();
    paint();
  });
  confirmBtn.addEventListener("click", function () {
    if (pair) {
      if (!(selected.a && selected.b && selected.a.url !== selected.b.url)) return;
      rememberFilters();
      if (typeof opts.onConfirm === "function") {
        try { opts.onConfirm(selected.a, selected.b); } catch (err) { /* caller handles */ }
      }
    } else {
      if (!(selected.a && selected.a.url)) return;
      if (typeof opts.onConfirm === "function") {
        try { opts.onConfirm(selected.a); } catch (err) { /* caller handles */ }
      }
    }
    close();
  });

  function close() {
    if (unregisterLayer) { try { unregisterLayer(); } catch (err) { /* noop */ } unregisterLayer = null; }
    rememberFilters();
    if (debounce) clearTimeout(debounce);
    if (dupTimer) { try { clearTimeout(dupTimer); } catch (err) { /* noop */ } dupTimer = null; }
    if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
    // Restore focus to the opener (null-safe: the viewer teardown may
    // have detached it).
    try {
      if (openerFocus && openerFocus.isConnected) openerFocus.focus();
    } catch (err) { /* best-effort */ }
    if (typeof opts.onClose === "function") {
      try { opts.onClose(); } catch (err) { /* best-effort */ }
    }
  }
  // Shared capture-phase layer registry ABOVE the compare view (layer 3):
  // one Escape dismisses only the top surface. The registry skips
  // editable-focused events, so a bubble-phase fallback on the overlay
  // covers Escape from the search box (the registry already consumed and
  // stopped non-editable Escapes, so this never double-dismisses).
  let unregisterLayer = null;
  try {
    unregisterLayer = registerLayerHandler(4, {
      escape: function () {
        close();
        return true;
      },
    });
  } catch (err) { unregisterLayer = null; }
  overlay.addEventListener("keydown", function (e) {
    if (e && e.key === "Escape") {
      try { e.stopPropagation(); } catch (err) { /* noop */ }
      close();
    }
  });
  paint();
  load(true);
  // Focus into the picker on open (search first so results are
  // immediately filterable; Escape still dismisses via the fallback).
  try {
    if (search && typeof search.focus === "function") search.focus();
    else if (cancelBtn && typeof cancelBtn.focus === "function") cancelBtn.focus();
  } catch (err) { /* best-effort */ }
  return {
    close: close,
    getSelection: function () { return { a: selected.a, b: selected.b }; },
  };
}
