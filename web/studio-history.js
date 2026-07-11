// Modal Studio — History
//
// Gallery page backed by existing run/experiment data.
// Uses existing /comfymodal/run-history endpoint.
// Shows an image grid/gallery with clickable cards and a preview overlay/lightbox.
// Non-image runs get a fallback tile. Experiment grouping is preserved.
// Safe DOM rendering — no innerHTML for dynamic run data.
//
// Image URL resolution order (delegated to studio-run-normalizer.js):
//   1. extra.primary_asset_id  → /assets/<id>
//   2. run.asset_id            → /assets/<id>
//   3. run.output_path         → /studio/outputs/<path>

import { resolveRunImageUrl, hasRunImage } from "./studio-run-normalizer.js";

// ── Element helper (local, matches other modules) ─────────────────────────

function el(tag, props = {}, children = []) {
  const e = document.createElement(tag);
  for (const k in props) {
    if (k === "class") e.className = props[k];
    else if (k === "style") e.style.cssText = props[k];
    else if (k === "text") e.textContent = props[k];
    else if (k.startsWith("on") && typeof props[k] === "function") {
      e.addEventListener(k.slice(2).toLowerCase(), props[k]);
    } else if (k === "value") {
      e.value = props[k];
    } else if (k === "dataset") {
      Object.assign(e.dataset, props[k]);
    } else if (k === "disabled" || k === "checked" || k === "hidden" || k === "readonly" || k === "required") {
      if (props[k]) e.setAttribute(k, "");
      else e.removeAttribute(k);
    } else {
      e.setAttribute(k, props[k]);
    }
  }
  for (const c of (Array.isArray(children) ? children : [children])) {
    if (c == null) continue;
    e.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  }
  return e;
}

// ── Helpers ───────────────────────────────────────────────────────────────

function getRunExtra(run) {
  return (run && run.extra) || {};
}

function getRunStatus(run) {
  return run.status || run.state || "unknown";
}

function isCompleted(run) {
  const s = getRunStatus(run);
  return s === "completed" || s === "success" || s === "done";
}

function isFailed(run) {
  const s = getRunStatus(run);
  return s === "failed" || s === "error";
}

// ── Main renderer ─────────────────────────────────────────────────────────

export function renderHistory(state, context) {
  const container = el("div", { class: "comfymodal-studio-history" });
  const apiBase = (context && context.apiBase) || "/comfymodal";

  // Preview overlay state (local to this renderer)
  let previewRun = null;

  function renderPreviewOverlay() {
    // If no preview selected, remove any existing overlay
    const existing = container.querySelector(".comfymodal-studio-history-preview");
    if (existing) existing.remove();
    if (!previewRun) return;

    const imageUrl = resolveRunImageUrl(previewRun, apiBase);
    const extra = getRunExtra(previewRun);
    const rid = previewRun.id || previewRun.run_id || extra.experiment_id || "unknown";
    const status = getRunStatus(previewRun);
    const promptText = (extra.prompt || previewRun.prompt || rid).substring(0, 200);
    const time = previewRun.created_at || previewRun.started_at || previewRun.timestamp || previewRun.created || "";

    const overlay = el("div", {
      class: "comfymodal-studio-history-preview",
      onclick: function (e) {
        if (e.target === overlay) {
          previewRun = null;
          renderPreviewOverlay();
        }
      },
    }, [
      el("div", { class: "comfymodal-studio-history-preview-backdrop" }),
      el("div", { class: "comfymodal-studio-history-preview-content" }, [
        el("button", {
          class: "comfymodal-studio-history-preview-close",
          text: "\u00d7",
          onclick: function () {
            previewRun = null;
            renderPreviewOverlay();
          },
        }),
        imageUrl
          ? el("img", {
              src: imageUrl,
              class: "comfymodal-studio-history-preview-image",
              alt: promptText,
            })
          : el("div", {
              class: "comfymodal-studio-history-preview-noimage",
              text: "No image available",
            }),
        el("div", { class: "comfymodal-studio-history-preview-info" }, [
          el("div", { class: "comfymodal-studio-history-preview-status", text: status }),
          el("div", { class: "comfymodal-studio-history-preview-prompt", text: promptText }),
          time ? el("div", { class: "comfymodal-studio-history-preview-time", text: time }) : null,
        ]),
      ]),
    ]);
    container.appendChild(overlay);
  }

  function openPreview(run) {
    previewRun = run;
    renderPreviewOverlay();
  }

  // Loading state
  container.appendChild(el("div", {
    class: "comfymodal-studio-card",
    text: "Loading history...",
  }));

  function fetchAndRender() {
    // Clear
    while (container.firstChild) container.removeChild(container.firstChild);

    // Re-add loading
    container.appendChild(el("div", {
      class: "comfymodal-studio-card",
      text: "Loading history...",
    }));

    fetch(apiBase + "/run-history?limit=50")
      .then(function (res) {
        if (!res.ok) throw new Error("History request failed: " + res.status);
        return res.json();
      })
      .then(function (data) {
        while (container.firstChild) container.removeChild(container.firstChild);

        const runs = data.runs || data.run_history || (Array.isArray(data) ? data : null);
        if (!runs || (Array.isArray(runs) && runs.length === 0)) {
          container.appendChild(el("div", {
            class: "comfymodal-studio-card",
            text: "No run history yet. Runs will appear here once you create experiments.",
          }));
          return;
        }

        const runList = Array.isArray(runs) ? runs : [];

        // Group by experiment_id
        const grouped = {};
        const ungrouped = [];
        runList.forEach(function (run) {
          const extra = getRunExtra(run);
          const expId = run.experiment_id || run.experimentId || extra.experiment_id || null;
          if (expId) {
            if (!grouped[expId]) grouped[expId] = [];
            grouped[expId].push(run);
          } else {
            ungrouped.push(run);
          }
        });

        // Render each group
        Object.entries(grouped).forEach(function (_ref) {
          const expId = _ref[0];
          const groupRuns = _ref[1];
          const groupEl = renderGroup(expId, groupRuns, apiBase, openPreview);
          container.appendChild(groupEl);
        });

        // Render ungrouped
        if (ungrouped.length > 0) {
          const fallbackId = "ungrouped_" + Date.now();
          const groupEl = renderGroup(fallbackId, ungrouped, apiBase, openPreview);
          container.appendChild(groupEl);
        }
      })
      .catch(function (err) {
        while (container.firstChild) container.removeChild(container.firstChild);
        const errorCard = el("div", { class: "comfymodal-studio-card" });
        errorCard.appendChild(el("p", {
          style: "color:var(--color-danger)",
          text: "Failed to load history: " + err.message,
        }));
        errorCard.appendChild(el("button", {
          class: "comfymodal-secondary-btn",
          text: "Retry",
          style: "margin-top:8px",
          onclick: fetchAndRender,
        }));
        container.appendChild(errorCard);
      });
  }

  fetchAndRender();
  return container;
}

// ── Group renderer ────────────────────────────────────────────────────────

function renderGroup(expId, groupRuns, apiBase, openPreview) {
  const groupCard = el("div", {
    class: "comfymodal-studio-card",
    style: "margin-bottom:var(--space-md)",
  });

  const firstRun = groupRuns[0] || {};
  const extra = getRunExtra(firstRun);
  const studioMeta = firstRun.studio_meta || extra.studio_meta || (firstRun.metadata && firstRun.metadata.studio_meta) || {};
  const flatFeatureId = extra.studio_feature_id || "";
  const flatPresetId = extra.studio_preset_id || "";

  // ── Group header ────────────────────────────────────────────────────
  const groupHeader = el("div", {
    style: "display:flex;justify-content:space-between;align-items:center;margin-bottom:var(--space-sm);",
  });

  const groupTitle = el("strong");
  if (studioMeta.studio_feature_id || studioMeta.studio_preset_id || flatFeatureId || flatPresetId) {
    const featureLabel = studioMeta.studio_feature_id || flatFeatureId || "studio";
    const presetSource = studioMeta.studio_preset_id || flatPresetId || "";
    const presetLabel = presetSource ? presetSource.substring(0, 12) : "";
    groupTitle.textContent = "Studio " + featureLabel + (presetLabel ? " \u2014 " + presetLabel : "");
  } else {
    groupTitle.textContent = "Experiment: " + expId;
  }
  groupHeader.appendChild(groupTitle);

  // Stats
  const statsRow = el("div", {
    style: "display:flex;gap:8px;font-size:var(--font-size-xs);color:var(--color-text-muted);",
  });
  statsRow.appendChild(document.createTextNode(groupRuns.length + " run(s)"));
  const completedCount = groupRuns.filter(function (r) { return isCompleted(r); }).length;
  const failedCount = groupRuns.filter(function (r) { return isFailed(r); }).length;
  if (completedCount > 0) {
    statsRow.appendChild(el("span", {
      style: "color:var(--color-success, #4ade80)",
      text: "\u00b7 " + completedCount + " completed",
    }));
  }
  if (failedCount > 0) {
    statsRow.appendChild(el("span", {
      style: "color:var(--color-danger, #f87171)",
      text: "\u00b7 " + failedCount + " failed",
    }));
  }
  groupHeader.appendChild(statsRow);
  groupCard.appendChild(groupHeader);

  // ── Gallery grid ───────────────────────────────────────────────────
  const gallery = el("div", { class: "comfymodal-studio-history-gallery" });

  groupRuns.forEach(function (run) {
    const extra = getRunExtra(run);
    const hasImage = hasRunImage(run);
    const imageUrl = hasImage ? resolveRunImageUrl(run, apiBase) : null;
    const status = getRunStatus(run);
    const rid = run.id || run.run_id || extra.experiment_id || "unknown";
    const promptText = (extra.prompt || run.prompt || rid).substring(0, 60);
    const time = run.created_at || run.started_at || run.timestamp || run.created || "";

    // Card wrapper
    const card = el("div", {
      class: "comfymodal-studio-history-card"
        + (isCompleted(run) ? " completed" : "")
        + (isFailed(run) ? " failed" : ""),
      onclick: function () { openPreview(run); },
    });

    // Thumbnail or fallback
    if (imageUrl) {
      card.appendChild(el("img", {
        class: "comfymodal-studio-history-thumb",
        src: imageUrl,
        alt: promptText,
        loading: "lazy",
      }));
    } else {
      // Fallback tile for non-image runs
      const fallback = el("div", { class: "comfymodal-studio-history-fallback" });
      fallback.appendChild(el("span", {
        class: "comfymodal-studio-history-fallback-icon",
        text: "\u{1F5C4}",
      }));
      fallback.appendChild(el("span", {
        class: "comfymodal-studio-history-fallback-label",
        text: promptText.substring(0, 30),
      }));
      card.appendChild(fallback);
    }

    // Overlay with status/prompt on hover
    const overlay_el = el("div", { class: "comfymodal-studio-history-card-overlay" });
    overlay_el.appendChild(el("span", {
      class: "comfymodal-studio-history-card-status",
      text: status,
    }));
    overlay_el.appendChild(el("span", {
      class: "comfymodal-studio-history-card-prompt",
      text: promptText,
    }));
    if (time) {
      overlay_el.appendChild(el("span", {
        class: "comfymodal-studio-history-card-time",
        text: time,
      }));
    }
    card.appendChild(overlay_el);

    gallery.appendChild(card);
  });

  groupCard.appendChild(gallery);
  return groupCard;
}
