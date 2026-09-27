// Modal Studio — Shared loading-state primitive (Phase I3).
//
// Dependency-light by design: direct DOM construction, zero imports.
// Importing el() from studio-ui.js would buy nothing here and would make
// every future consumer of this module pull the whole shared-UI graph;
// keeping this file import-free also makes circular dependencies
// structurally impossible.
//
// Frozen interface (PHASE_I1 freeze §Loading):
//   renderLoadingState({ label = "Loading…", size = "page" | "inline", testid? })
//
// The returned root is an HTMLElement carrying:
//   class "cm-loading", data-size="page|inline",
//   role="status", aria-live="polite"
// and containing a decorative spinner (aria-hidden) plus a visible label.
// The element itself is the announced status — do NOT add aria-busy here.

function _normalizeLabel(value) {
  if (typeof value === "string" && value.trim() !== "") return value;
  return "Loading\u2026";
}

export function renderLoadingState(options = {}) {
  const opts = options && typeof options === "object" ? options : {};
  const label = _normalizeLabel(opts.label);
  const size = opts.size === "inline" ? "inline" : "page";

  const root = document.createElement("div");
  root.className = "cm-loading";
  root.setAttribute("data-size", size);
  root.setAttribute("role", "status");
  root.setAttribute("aria-live", "polite");

  // Non-string testid is ignored rather than stringified into junk.
  if (typeof opts.testid === "string" && opts.testid !== "") {
    root.setAttribute("data-testid", opts.testid);
  }

  const spinner = document.createElement("span");
  spinner.className = "cm-loading-spinner";
  spinner.setAttribute("aria-hidden", "true");

  const labelEl = document.createElement("span");
  labelEl.className = "cm-loading-label";
  labelEl.textContent = label;

  root.appendChild(spinner);
  root.appendChild(labelEl);
  return root;
}
