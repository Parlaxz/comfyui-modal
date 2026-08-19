// Modal Studio — History V2 Generation Detail
//
// Full-screen overlay for a single generation record: featured output,
// other-output thumbnails with "Set as featured", Preview / Original slots,
// parameters, exact metadata, attempts, errors, export state, notes,
// favorite, timing diagnostics, and the Generate Original action.
//
// Appended to document.body; Escape closes via registerLayerHandler
// (layer 3, matching the shared preview overlay).  All DOM via el().

import { el, registerLayerHandler } from "./studio-ui.js";
import { _formatDuration } from "./studio-run-normalizer.js";
import { selectDetailAsset, selectFeedAsset } from "./history-v2-repository.js";

// ── Constants / helpers ───────────────────────────────────────────────────

const STATUS_LABELS = {
  completed: "Completed",
  completed_with_failures: "Completed with failures",
  failed: "Failed",
  canceled: "Canceled",
  interrupted: "Interrupted",
  running: "Running",
};

const PARAM_KEYS = [
  ["seed", "Seed"],
  ["steps", "Steps"],
  ["cfg", "CFG"],
  ["guidance", "Guidance"],
  ["sampler", "Sampler"],
  ["scheduler", "Scheduler"],
  ["denoise", "Denoise"],
  ["width", "Width"],
  ["height", "Height"],
];

const TIMING_ROWS = [
  ["endToEndMs", "End-to-end"],
  ["modelLoadMs", "Model load"],
  ["clipEncodeMs", "Prompt encoding"],
  ["samplingMs", "Sampling"],
  ["vaeDecodeMs", "VAE decode"],
];

export function appendIfPresent(parent, child) {
  if (child) parent.appendChild(child);
}

export function selectGenerationDetailAsset(record) {
  const feat = record && record.featuredOutput ? record.featuredOutput : {};
  return selectDetailAsset(Object.assign({}, feat, {
    originalAvailable: !!(feat.originalAvailable || (record && record.originalAvailable)),
  }));
}

export function historyAttemptPurposeLabel(mode) {
  const key = mode == null ? "" : String(mode).toLowerCase();
  if (key === "original") return "Original";
  if (key === "preview") return "Preview";
  return "Run";
}

function _statusChip(status) {
  const key = STATUS_LABELS[status] ? status : "running";
  const label = STATUS_LABELS[status] || status || "Running";
  return el("span", { class: "comfymodal-studio-history-v2-chip status-" + key, text: label });
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
    text: "Preview",
  });
}

// ── Main entry ────────────────────────────────────────────────────────────

export async function renderGenerationDetail(generationId, repo, callbacks) {
  const cbs = callbacks || {};

  const overlay = el("div", {
    class: "comfymodal-studio-history-v2-overlay",
    role: "dialog",
    "aria-modal": "true",
    "aria-label": "Generation detail",
  });

  const backdrop = el("div", { class: "comfymodal-studio-history-v2-overlay-backdrop" });
  overlay.appendChild(backdrop);

  const content = el("div", { class: "comfymodal-studio-history-v2-overlay-content" });
  overlay.appendChild(content);

  // ── Close / Escape plumbing ────────────────────────────────────────────
  let _layerUnreg = null;
  let _closed = false;
  let _activeMenu = null;
  let _outsideHandler = null;

  function close(notify) {
    if (_closed) return;
    _closed = true;
    closeAnyMenu();
    if (_layerUnreg) {
      _layerUnreg();
      _layerUnreg = null;
    }
    if (overlay.parentNode) overlay.remove();
    if (notify !== false && typeof cbs.onClose === "function") cbs.onClose();
  }

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

  backdrop.addEventListener("click", function () { close(); });

  function makeCloseBtn() {
    return el("button", {
      class: "comfymodal-studio-history-v2-overlay-close",
      "aria-label": "Close",
      type: "button",
      text: "\u00d7",
      onclick: function () { close(); },
    });
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

  function _favStar(record) {
    const star = el("button", {
      type: "button",
      class: "comfymodal-studio-history-v2-fav",
      "aria-label": record.favorite ? "Remove from favorites" : "Add to favorites",
      "aria-pressed": record.favorite ? "true" : "false",
      title: record.favorite ? "Remove from favorites" : "Add to favorites",
      text: record.favorite ? "\u2605" : "\u2606",
    });
    star.addEventListener("click", async function () {
      const next = !record.favorite;
      try {
        await repo.setFavorite(record.id, next);
        record.favorite = next;
      } catch (err) { /* keep current state on failure */ }
      star.textContent = record.favorite ? "\u2605" : "\u2606";
      star.setAttribute("aria-pressed", record.favorite ? "true" : "false");
      star.setAttribute("aria-label", record.favorite ? "Remove from favorites" : "Add to favorites");
      if (typeof cbs.onChanged === "function") cbs.onChanged();
    });
    return star;
  }

  function buildNotesSection(record) {
    const sec = el("div", { class: "comfymodal-studio-history-v2-section" }, [
      el("div", { class: "comfymodal-studio-history-v2-section-title", text: "Note" }),
    ]);
    const textarea = el("textarea", {
      class: "comfymodal-studio-history-v2-notes",
      "aria-label": "Note for this generation",
    });
    textarea.value = record.note || "";
    const statusEl = el("span", { class: "comfymodal-studio-history-v2-action-note" });
    const saveBtn = el("button", {
      class: "comfymodal-secondary-btn",
      type: "button",
      text: "Save note",
      onclick: async function () {
        saveBtn.disabled = true;
        try {
          await repo.setNote(record.id, textarea.value);
          record.note = textarea.value;
          statusEl.textContent = "Saved";
        } catch (err) {
          statusEl.textContent = "Save failed";
        }
        saveBtn.disabled = false;
        if (typeof cbs.onChanged === "function") cbs.onChanged();
      },
    });
    const row = el("div", { class: "comfymodal-studio-history-v2-action-row" }, [saveBtn, statusEl]);
    sec.appendChild(textarea);
    sec.appendChild(row);
    return sec;
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
      if (asset.kind === "preview") thumbEl.appendChild(_previewBadge());
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

  function buildPreviewOriginalSlots(record) {
    const feat = record.featuredOutput || {};
    const slots = el("div", { class: "comfymodal-studio-history-v2-slots" });

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
    if (displayed.kind === "preview") previewBody.appendChild(_previewBadge());

    slots.appendChild(el("div", { class: "comfymodal-studio-history-v2-slot" }, [
      el("div", {
        class: "comfymodal-studio-history-v2-slot-title",
        text: displayed.kind === "thumbnail" ? "Thumbnail" : "Preview",
      }),
      previewBody,
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
      originalBody = wrap;
    } else if (feat.originalFailed) {
      originalBody = el("div", { class: "comfymodal-studio-history-v2-slot-error", text: "Original generation failed \u2014 preview retained" });
    } else if (feat.originalAvailable) {
      originalBody = el("div", { class: "comfymodal-studio-history-v2-slot-placeholder", text: "Original available" });
    } else {
      originalBody = el("div", { class: "comfymodal-studio-history-v2-slot-placeholder", text: "No original" });
    }
    slots.appendChild(el("div", { class: "comfymodal-studio-history-v2-slot" }, [
      el("div", { class: "comfymodal-studio-history-v2-slot-title", text: "Original" }),
      originalBody,
    ]));

    return slots;
  }

  function buildLeftColumn(record) {
    const col = el("div", { class: "comfymodal-studio-history-v2-overlay-left" });
    const feat = record.featuredOutput || {};
    const displayed = selectGenerationDetailAsset(record);
    if (displayed.url) {
      const imageWrap = el("div", { class: "comfymodal-studio-history-v2-featured-wrap" }, [el("img", {
        class: "comfymodal-studio-history-v2-featured-img",
        src: displayed.url,
        alt: record.prompt || "Featured output",
        onerror: _hideOnError,
      })]);
      if (displayed.kind === "preview") imageWrap.appendChild(_previewBadge());
      col.appendChild(imageWrap);
    } else {
      col.appendChild(el("div", {
        class: "comfymodal-studio-history-v2-featured-tile comfymodal-studio-history-v2-noimage",
        "data-asset-kind": displayed.kind,
      }, [el("span", { text: displayed.label || "No image" })]));
    }
    if (feat.originalFailed) {
      col.appendChild(el("div", {
        class: "comfymodal-studio-history-v2-badge",
        "data-testid": "history-v2-original-failed-badge",
        text: "Original failed \u2014 preview retained",
      }));
    }
    col.appendChild(buildOutputsRow(record));
    col.appendChild(buildPreviewOriginalSlots(record));
    return col;
  }

  function buildParamsSection(record) {
    const params = record.params && typeof record.params === "object" ? record.params : {};
    const items = [];
    PARAM_KEYS.forEach(function (entry) {
      const v = params[entry[0]];
      if (v == null || v === "") return;
      items.push(el("div", { class: "comfymodal-studio-history-v2-param" }, [
        el("div", { class: "comfymodal-studio-history-v2-param-key", text: entry[1] }),
        el("div", { class: "comfymodal-studio-history-v2-param-value", text: String(v) }),
      ]));
    });
    if (items.length === 0) return null;
    return el("div", { class: "comfymodal-studio-history-v2-section" }, [
      el("div", { class: "comfymodal-studio-history-v2-section-title", text: "Parameters" }),
      el("div", { class: "comfymodal-studio-history-v2-params-table" }, items),
    ]);
  }

  function buildTimingSection(record) {
    const timing = record.timing;
    const placeholder = el("div", {
      class: "comfymodal-studio-history-v2-timing-placeholder",
      "data-testid": "history-v2-timing-placeholder",
      text: "Diagnostics pending",
    });
    if (!timing || typeof timing !== "object") {
      return el("div", { class: "comfymodal-studio-history-v2-section" }, [
        el("div", { class: "comfymodal-studio-history-v2-section-title", text: "Timing" }),
        placeholder,
      ]);
    }
    let rows = [];
    if (Array.isArray(timing.stages) && timing.stages.length > 0) {
      rows = timing.stages.map(function (s) {
        if (!s || !s.label) return null;
        if (s.durationMs == null) return null;
        return _row(s.label, _formatDuration(s.durationMs));
      }).filter(function (r) { return r != null; });
    }
    if (rows.length === 0) {
      rows = TIMING_ROWS.map(function (entry) {
        const v = timing[entry[0]];
        if (v == null) return null;
        return _row(entry[1], _formatDuration(v));
      }).filter(function (r) { return r != null; });
    }
    return el("div", { class: "comfymodal-studio-history-v2-section" }, [
      el("div", { class: "comfymodal-studio-history-v2-section-title", text: "Timing" }),
    ].concat(rows.length > 0 ? rows : [placeholder]));
  }

  function _exportStateLabel(value) {
    if (value == null || value === "") return "";
    if (value === "none") return "Not exported";
    const s = String(value).replace(/[_-]+/g, " ");
    return s.charAt(0).toUpperCase() + s.slice(1);
  }

  function buildGenerateSection(record) {
    const note = el("div", { class: "comfymodal-studio-history-v2-action-note", text: "Generate Original is not available yet." });
    const btn = el("button", {
      class: "comfymodal-primary-btn comfymodal-studio-history-v2-generate",
      "data-testid": "history-v2-generate-original",
      type: "button",
      text: "Generate Original (unavailable)",
      disabled: true,
      title: "Generate Original is not available in this release.",
    });
    return el("div", { class: "comfymodal-studio-history-v2-section" }, [
      el("div", { class: "comfymodal-studio-history-v2-section-title", text: "Actions" }),
      btn,
      note,
    ]);
  }

  function buildRightColumn(record) {
    const col = el("div", { class: "comfymodal-studio-history-v2-overlay-right" });

    // 1. Status + timestamp + duration
    const runLine = el("div", { class: "comfymodal-studio-history-v2-run-line" }, [
      _statusChip(record.status),
      record.startedAt ? el("span", { class: "comfymodal-studio-history-v2-row-value", text: _shortDateTime(record.startedAt) }) : null,
      record.durationMs != null ? el("span", { class: "comfymodal-studio-history-v2-row-value", text: _formatDuration(record.durationMs) }) : null,
    ]);
    col.appendChild(el("div", { class: "comfymodal-studio-history-v2-section" }, [
      el("div", { class: "comfymodal-studio-history-v2-section-title", text: "Run" }),
      runLine,
    ]));

    // 2. Workflow + preset
    const wf = (record.workflow || "") + (record.workflowVersion ? " v" + record.workflowVersion : "");
    appendIfPresent(col, _section("Workflow", [
      _row("Workflow", wf),
      _row("Preset", record.preset),
    ]));

    // 3. Parameters
    appendIfPresent(col, buildParamsSection(record));

    // 4. Exact metadata
    appendIfPresent(col, _section("Metadata", [
      _row("Run ID", record.runId || record.id),
      _row("Models", Array.isArray(record.models) ? record.models.join(", ") : ""),
      _row("Tags", Array.isArray(record.tags) ? record.tags.join(", ") : ""),
      _row("Started", record.startedAt),
      _row("Completed", record.completedAt),
    ]));

    // 5. Attempt history
    const attempts = Array.isArray(record.attempts) ? record.attempts : [];
    if (attempts.length > 0) {
      appendIfPresent(col, _section("Attempts", attempts.map(function (a, i) {
        return el("div", { class: "comfymodal-studio-history-v2-attempt" }, [
          el("div", { class: "comfymodal-studio-history-v2-attempt-line" }, [
            el("span", { class: "comfymodal-studio-history-v2-attempt-purpose", text: historyAttemptPurposeLabel(a.mode || a.purpose) }),
            _statusChip(a.status || "running"),
            a.startedAt ? el("span", { class: "comfymodal-studio-history-v2-row-value", text: _shortDateTime(a.startedAt) }) : null,
            a.durationMs != null ? el("span", { class: "comfymodal-studio-history-v2-row-value", text: _formatDuration(a.durationMs) }) : null,
          ]),
          a.error ? el("div", { class: "comfymodal-studio-history-v2-attempt-error", text: String(a.error) }) : null,
        ]);
      })));
    }

    // 6. Errors
    const errors = Array.isArray(record.errors) ? record.errors : [];
    if (errors.length > 0) {
      // NOTE: children must be a FLAT array (like _section's .concat pattern);
      // el() only flattens one level, so a nested errors.map() array would
      // throw "parameter 1 is not of type 'Node'" and blank the overlay.
      col.appendChild(el("div", { class: "comfymodal-studio-history-v2-section comfymodal-studio-history-v2-section-error" }, [
        el("div", { class: "comfymodal-studio-history-v2-section-title", text: "Errors" }),
      ].concat(errors.map(function (e) {
        const code = (e && e.code) ? e.code : "error";
        const message = (e && e.message) ? String(e.message) : "";
        return el("div", { class: "comfymodal-studio-history-v2-row comfymodal-studio-history-v2-error-line" },
          [el("span", { class: "comfymodal-studio-history-v2-row-key", text: code }),
           message ? el("span", { class: "comfymodal-studio-history-v2-row-value", text: message }) : null]);
      }))));
    }

    // 7. Export state
    const exportLabel = _exportStateLabel(record.exportState);
    appendIfPresent(col, _section("Export", [_row("State", exportLabel)]));

    // 8. Notes
    col.appendChild(buildNotesSection(record));

    // 9. Favorite
    col.appendChild(el("div", { class: "comfymodal-studio-history-v2-section" }, [
      el("div", { class: "comfymodal-studio-history-v2-section-title", text: "Favorite" }),
      el("div", { class: "comfymodal-studio-history-v2-action-row" }, [_favStar(record)]),
    ]));

    // 10. Timing
    col.appendChild(buildTimingSection(record));

    // 11. Generate Original
    col.appendChild(buildGenerateSection(record));

    return col;
  }

  function buildDetailBody(record) {
    const body = el("div", { class: "comfymodal-studio-history-v2-overlay-body" });
    body.appendChild(buildLeftColumn(record));
    body.appendChild(buildRightColumn(record));
    return body;
  }

  function _renderDetail(record) {
    currentRecord = record;
    clearContent();
    content.appendChild(makeCloseBtn());
    content.appendChild(buildDetailBody(record));
  }

  function _renderLoading() {
    clearContent();
    content.appendChild(makeCloseBtn());
    content.appendChild(el("div", { class: "comfymodal-studio-history-v2-state", text: "Loading\u2026" }));
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
