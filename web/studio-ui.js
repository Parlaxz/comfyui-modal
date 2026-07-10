// Modal Studio — Shared UI Helpers
//
// Element builder, status badges, and legacy empty state renderer shared
// across Backend page modules.

// ── Element helper ────────────────────────────────────────────────────────

export function el(tag, props = {}, children = []) {
  const e = document.createElement(tag);
  for (const k in props) {
    if (k === "class") e.className = props[k];
    else if (k === "style") e.style.cssText = props[k];
    else if (k === "text") e.textContent = props[k];
    else if (k.startsWith("on") && typeof props[k] === "function") {
      e.addEventListener(k.slice(2).toLowerCase(), props[k]);
    } else if (k === "value") {
      e.value = props[k];
    } else if (k === "disabled" || k === "checked" || k === "hidden" || k === "readonly" || k === "required") {
      // Boolean HTML attributes must use the DOM property, not setAttribute,
      // because setAttribute("disabled", false) sets disabled="false" which still disables.
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

// ── Status badge helper ──────────────────────────────────────────────────

export function statusBadge(text, kind) {
  const cls = kind === "ok" ? "comfymodal-studio-status-badge ok"
    : kind === "warn" ? "comfymodal-studio-status-badge warn"
    : kind === "error" ? "comfymodal-studio-status-badge error"
    : "comfymodal-studio-status-badge neutral";
  return el("span", { class: cls, text: text });
}

// ── Legacy empty state renderer ──────────────────────────────────────────
// Kept for backward compatibility with tests that reference it from the
// backend module.

export function renderEmptyState(listContent, detailPanel, context, state) {
  while (detailPanel.firstChild) detailPanel.removeChild(detailPanel.firstChild);
  const emptyCard = el("div", { class: "comfymodal-studio-card" }, [
    el("p", { text: "No backends configured via legacy discovery.", style: "font-weight:600;margin:0 0 8px;color:#888;" }),
    el("p", { text: "Use the Snapshots or Backend Presets tabs above.", style: "font-size:12px;color:#555;margin:0 0 8px;" }),
  ]);
  while (listContent.firstChild) listContent.removeChild(listContent.firstChild);
  listContent.appendChild(emptyCard);
}
