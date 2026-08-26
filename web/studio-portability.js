// Modal Studio — Workflow Portability UI (Phase G12)
//
// Frontend product lane for Workflow portability: summary chips, the
// version-scoped Portability panel, the six-target readiness matrix, and the
// separate source-environment reproducibility section.
//
// Authority contract (G5 freeze): the backend report is the SOLE authority.
// This module never recomputes risk, never infers freshness from timestamps,
// and never reinterprets UNKNOWN targets. Wire risk values are lowercase;
// display labels are capitalized. Absent data renders truthfully as
// "Not analyzed" / "Unknown" — never as a green Low.

import { el } from "./studio-ui.js";

// ── Frozen vocabularies ───────────────────────────────────────────────────

export const PORTABILITY_TARGET_ORDER = [
  "local",
  "modal",
  "runpod",
  "runcomfy",
  "comfy_cloud",
  "baseten",
];

export const TARGET_LABELS = {
  local: "Local",
  modal: "Modal",
  runpod: "RunPod",
  runcomfy: "RunComfy",
  comfy_cloud: "Comfy Cloud",
  baseten: "Baseten",
};

const RISK_LEVELS = ["low", "medium", "high", "unknown"];

// ── Pure helpers ──────────────────────────────────────────────────────────

/** Lowercase wire value; anything unrecognized is Unknown (never guessed). */
export function normalizeRiskLevel(value) {
  const key = String(value == null ? "" : value).toLowerCase();
  return RISK_LEVELS.indexOf(key) !== -1 ? key : "unknown";
}

/** Display label for a wire risk value. */
export function riskLabel(level) {
  const v = normalizeRiskLevel(level);
  return v.charAt(0).toUpperCase() + v.slice(1);
}

/** Badge kind for a wire risk value. Unknown stays neutral, never green. */
export function riskKind(level) {
  const v = normalizeRiskLevel(level);
  if (v === "low") return "ok";
  if (v === "medium") return "warn";
  if (v === "high") return "error";
  return "neutral";
}

/**
 * Normalize the optional G11 Workflow summary field.
 * Absent/malformed → null (same interpretation as an explicit null).
 * stale: true | false | null (null = cached result, freshness not verified).
 */
export function normalizePortabilitySummary(raw) {
  if (!raw || typeof raw !== "object") return null;
  if (!raw.risk_level && raw.risk_level !== "") return null;
  const stale = raw.stale === true ? true : raw.stale === false ? false : null;
  const count = Number(raw.issue_count);
  return {
    versionId: String(raw.version_id || ""),
    riskLevel: normalizeRiskLevel(raw.risk_level),
    issueCount: Number.isFinite(count) && count >= 0 ? count : 0,
    stale,
    analyzedAt: raw.analyzed_at ? String(raw.analyzed_at) : null,
  };
}

/**
 * Chip presentation state from a normalized summary.
 * null summary → Not analyzed. Stale/unchecked are visibly distinct and
 * never presented as unquestionably current.
 */
export function chipStateFromSummary(summary) {
  if (!summary) {
    return {
      label: "Not analyzed",
      kind: "neutral",
      title:
        "Portability has not been analyzed yet. Open the workflow and run Check portability.",
    };
  }
  const base = riskLabel(summary.riskLevel);
  const kind = riskKind(summary.riskLevel);
  let label = base;
  let title =
    "Portability risk " + base + " \u00b7 " + summary.issueCount +
    " issue" + (summary.issueCount === 1 ? "" : "s") +
    ". Click to open the portability panel.";
  if (summary.stale === true) {
    label += " \u00b7 Stale";
    title =
      "Portability risk " + base + " (cached result is STALE and requires a recheck)" +
      " \u00b7 " + summary.issueCount + " issue" + (summary.issueCount === 1 ? "" : "s") +
      ". Click to open the portability panel.";
  } else if (summary.stale === null) {
    label += " \u00b7 Needs check";
    title =
      "Portability risk " + base + " (cached result, current freshness not verified)" +
      " \u00b7 " + summary.issueCount + " issue" + (summary.issueCount === 1 ? "" : "s") +
      ". Click to open the portability panel.";
  }
  return { label, kind, title };
}

/**
 * Deep-link target for an issue row, using only EXISTING product surfaces.
 * Returns "models" when the Model Library sub-view (which lists both models
 * and custom nodes) is the reliable destination; otherwise null so the
 * backend fix_hint renders as plain text instead of a broken link.
 */
export function issueDeepLink(issue) {
  const subject = issue && issue.subject ? String(issue.subject) : "";
  const code = issue && issue.code ? String(issue.code) : "";
  if (subject === "models") return "models";
  if (subject === "custom_nodes") return "models";
  if (
    code === "dependency_missing" ||
    code === "dependency_wrong_revision" ||
    code === "model_hash_unpinned" ||
    code === "custom_node_unpinned"
  ) {
    return "models";
  }
  return null;
}

function _shortHash(h) {
  const s = String(h || "");
  return s.length > 10 ? s.slice(0, 10) : s;
}

function _severityText(sev) {
  const v = normalizeRiskLevel(sev) === "unknown" ? "" : sev;
  const key = String(v).toLowerCase();
  if (key === "high" || key === "medium" || key === "low") {
    return key.charAt(0).toUpperCase() + key.slice(1);
  }
  return "Info";
}

// ── Issue rows ────────────────────────────────────────────────────────────

/**
 * Render canonical issue objects (G5 §6): severity text + message + fix_hint.
 * Backend fix text is rendered verbatim; the frontend never invents fixes.
 * Evidence is not dumped by default.
 */
export function renderIssueRows(issues, testId, onDeepLink) {
  const wrap = el("div", {
    class: "comfymodal-studio-portability-issues",
    "data-testid": testId || "portability-issues",
  });
  const list = Array.isArray(issues) ? issues : [];
  if (list.length === 0) {
    wrap.appendChild(el("p", {
      class: "comfymodal-studio-dependencies-note",
      text: "No issues were reported for this version.",
    }));
    return wrap;
  }
  list.forEach((issue) => {
    const row = el("div", {
      class: "comfymodal-studio-portability-issue severity-" + normalizeRiskLevel(issue && issue.severity),
      "data-testid": "portability-issue-row",
    });
    row.appendChild(el("span", {
      class: "comfymodal-studio-portability-issue-severity",
      text: _severityText(issue && issue.severity),
    }));
    const body = el("div", { class: "comfymodal-studio-portability-issue-body" });
    body.appendChild(el("span", {
      class: "comfymodal-studio-portability-issue-message",
      text: String((issue && issue.message) || ""),
    }));
    const hint = String((issue && issue.fix_hint) || "");
    if (hint) {
      body.appendChild(el("span", {
        class: "comfymodal-studio-portability-issue-hint",
        text: "Fix hint: " + hint,
      }));
    }
    // Deep-link only where a reliable product surface exists; otherwise the
    // backend fix_hint above stays plain text (never a broken link).
    const linkTarget = issueDeepLink(issue);
    if (linkTarget === "models" && typeof onDeepLink === "function") {
      body.appendChild(el("button", {
        type: "button",
        class: "comfymodal-studio-version-reasons-toggle",
        "data-testid": "portability-issue-link",
        text: "View in Model Library",
        onclick: () => onDeepLink(linkTarget),
      }));
    }
    row.appendChild(body);
    wrap.appendChild(row);
  });
  return wrap;
}

// ── Target matrix ─────────────────────────────────────────────────────────

/**
 * Exactly six target rows in frozen order, driven ONLY by the backend
 * report. Reasons resolve through the global issues pool by code
 * (reference-by-code model); advice lines render verbatim.
 */
export function renderTargetMatrix(report) {
  const table = el("div", {
    class: "comfymodal-studio-portability-targets",
    "data-testid": "portability-target-matrix",
    role: "table",
    "aria-label": "Target readiness",
  });
  const issuesByCode = {};
  (Array.isArray(report && report.issues) ? report.issues : []).forEach((i) => {
    if (i && i.code) issuesByCode[i.code] = i;
  });
  const targets = (report && report.targets) || {};

  const head = el("div", { class: "comfymodal-studio-portability-target-head", role: "row" }, [
    el("span", { class: "comfymodal-studio-workflows-sidebar-label", text: "Target" }),
    el("span", { class: "comfymodal-studio-workflows-sidebar-label", text: "Readiness" }),
    el("span", { class: "comfymodal-studio-workflows-sidebar-label", text: "Notes" }),
  ]);
  table.appendChild(head);

  PORTABILITY_TARGET_ORDER.forEach((tid) => {
    const t = targets[tid] || null;
    const level = t ? normalizeRiskLevel(t.risk_level) : "unknown";
    const row = el("div", {
      class: "comfymodal-studio-portability-target-row",
      "data-testid": "portability-target-" + tid,
      role: "row",
    });
    row.appendChild(el("span", {
      class: "comfymodal-studio-portability-target-name",
      text: TARGET_LABELS[tid] || tid,
    }));
    row.appendChild(el("span", {
      class: "comfymodal-studio-status-badge " + riskKind(level),
      "data-testid": "portability-target-risk-" + tid,
      text: riskLabel(level),
    }));
    const notes = el("div", { class: "comfymodal-studio-portability-target-notes" });
    const codes = t && Array.isArray(t.issue_codes) ? t.issue_codes : [];
    codes.forEach((code) => {
      const issue = issuesByCode[code];
      if (issue && issue.message) {
        notes.appendChild(el("span", {
          class: "comfymodal-studio-portability-target-reason",
          text: String(issue.message),
        }));
      }
    });
    const advice = t && Array.isArray(t.advice) ? t.advice : [];
    advice.forEach((a) => {
      if (a) notes.appendChild(el("span", {
        class: "comfymodal-studio-portability-target-advice",
        text: String(a),
      }));
    });
    if (!codes.length && !advice.length) {
      notes.appendChild(el("span", {
        class: "comfymodal-studio-portability-target-advice",
        text: level === "unknown"
          ? "Capability unknown \u2014 no defensible determination available."
          : "No target-specific findings.",
      }));
    }
    row.appendChild(notes);
    table.appendChild(row);
  });
  return table;
}

// ── Environment section (distinct from workflow risk) ─────────────────────

const ENV_EXPLAINER =
  "Workflow portability evaluates moving this WorkflowVersion elsewhere; " +
  "source environment reproducibility evaluates how exactly the CURRENT " +
  "source runtime itself can be reproduced. The two are independent.";

/**
 * DISTINCT section: never recolors the workflow chip and never forces any
 * target's risk (POLICY_ENVIRONMENT_ISOLATION).
 */
export function renderEnvironmentSection(report) {
  const env = (report && report.environment) || null;
  const section = el("div", {
    class: "comfymodal-studio-portability-environment",
    "data-testid": "portability-environment",
  });
  section.appendChild(el("h4", {
    class: "comfymodal-studio-editor-block-title",
    text: "Source environment reproducibility",
  }));
  section.appendChild(el("p", {
    class: "comfymodal-studio-dependencies-note",
    text: ENV_EXPLAINER,
  }));
  if (!env) {
    section.appendChild(el("p", {
      class: "comfymodal-studio-dependencies-note",
      text: "No environment reproducibility information was returned.",
    }));
    return section;
  }
  const level = normalizeRiskLevel(env.risk_level);
  section.appendChild(el("div", { class: "comfymodal-studio-portability-env-risk" }, [
    el("span", { class: "comfymodal-studio-workflows-sidebar-label", text: "Reproducibility" }),
    el("span", {
      class: "comfymodal-studio-status-badge " + riskKind(level),
      "data-testid": "portability-environment-risk",
      text: riskLabel(level),
    }),
  ]));
  const issues = Array.isArray(env.issues) ? env.issues : [];
  if (issues.length) section.appendChild(renderIssueRows(issues, "portability-environment-issues"));
  return section;
}

// ── Panel ─────────────────────────────────────────────────────────────────

function _countsLine(report) {
  const counts = (report && report.counts) || {};
  const parts = [];
  [["high", "high"], ["medium", "medium"], ["low", "low"]].forEach(([k, label]) => {
    const n = Number(counts[k]);
    if (Number.isFinite(n) && n > 0) parts.push(n + " " + label);
  });
  return parts.length ? parts.join(", ") : "no issues by severity";
}

function _staleLine(report) {
  if (!report) return "";
  if (report.stale === true) {
    return "This is a STALE cached result \u2014 it requires a recheck.";
  }
  if (report.stale === false) return "Current cached result.";
  return "Cached result \u2014 current freshness was not verified.";
}

/**
 * Version-scoped Portability panel.
 *
 * opts: { report, priorStale, error, checking, workflowName, versionNumber,
 *         versionId, onCheck, onExportRequest, onChecklist, exportBusy }
 */
export function renderPortabilityPanel(opts) {
  const o = opts || {};
  const report = o.report || null;
  const checking = !!o.checking;

  const section = el("div", {
    class: "comfymodal-studio-section",
    "data-testid": "portability-panel",
    tabindex: "-1",
  });
  section.appendChild(el("div", { class: "comfymodal-studio-section-head" }, [
    el("h3", { class: "comfymodal-studio-section-title", text: "Portability" }),
    el("div", { class: "comfymodal-studio-workflows-header-actions" }, [
      el("button", {
        type: "button",
        class: "comfymodal-secondary-btn",
        "data-testid": "portability-check-button",
        text: checking ? "Checking\u2026" : report ? "Recheck portability" : "Check portability",
        disabled: checking,
        "aria-busy": checking ? "true" : "false",
        onclick: () => { if (typeof o.onCheck === "function") o.onCheck(); },
      }),
      el("button", {
        type: "button",
        class: "comfymodal-secondary-btn",
        "data-testid": "portability-export-button",
        text: o.exportBusy ? "Exporting\u2026" : "Export workflow",
        disabled: !!o.exportBusy,
        onclick: () => { if (typeof o.onExportRequest === "function") o.onExportRequest(); },
      }),
      el("button", {
        type: "button",
        class: "comfymodal-secondary-btn",
        "data-testid": "portability-checklist-button",
        text: "Download portability checklist",
        disabled: !report,
        onclick: () => { if (report && typeof o.onChecklist === "function") o.onChecklist(); },
      }),
    ]),
  ]));

  if (o.error) {
    section.appendChild(el("div", {
      class: "comfymodal-studio-notice error",
      "data-testid": "portability-error",
      role: "status",
      text: String(o.error),
    }));
  }

  if (!report) {
    section.appendChild(el("p", {
      class: "comfymodal-studio-dependencies-note",
      "data-testid": "portability-not-analyzed",
      text: checking
        ? "Checking portability\u2026"
        : "Not analyzed yet. Run Check portability to analyze this immutable version.",
    }));
    return section;
  }

  // Summary block — scoped to THIS immutable version, never the mutable workflow.
  const summary = el("div", {
    class: "comfymodal-studio-portability-summary",
    "data-testid": "portability-summary",
  });
  summary.appendChild(el("div", { class: "comfymodal-studio-portability-summary-row" }, [
    el("span", { class: "comfymodal-studio-workflows-sidebar-label", text: "Version" }),
    el("span", {
      class: "comfymodal-studio-portability-version-context",
      "data-testid": "portability-version-context",
      text: "v" + (o.versionNumber != null ? o.versionNumber : "?") +
        " \u00b7 " + String(o.versionId || report.version_id || ""),
    }),
    el("span", {
      class: "comfymodal-studio-status-badge " + riskKind(report.risk_level),
      "data-testid": "portability-risk",
      text: riskLabel(report.risk_level),
    }),
    el("span", {
      class: "comfymodal-studio-portability-counts",
      text: (Number(report.issue_count) || 0) + " issue" +
        ((Number(report.issue_count) || 0) === 1 ? "" : "s") +
        " (" + _countsLine(report) + ")",
    }),
  ]));
  const metaBits = [];
  if (report.graph_hash) metaBits.push("graph " + _shortHash(report.graph_hash));
  if (report.analyzed_at) metaBits.push("analyzed " + String(report.analyzed_at));
  metaBits.push(_staleLine(report));
  if (o.priorStale) metaBits.push("Showing the PRIOR report after a failed recheck.");
  summary.appendChild(el("div", {
    class: "comfymodal-studio-portability-meta",
    "data-testid": "portability-meta",
    text: metaBits.filter(Boolean).join(" \u00b7 "),
  }));
  if (report.rule_version) {
    summary.appendChild(el("div", {
      class: "comfymodal-studio-portability-meta",
      text: "Rules: " + String(report.rule_version),
    }));
  }
  section.appendChild(summary);

  const issues = Array.isArray(report.issues) ? report.issues : [];
  if (issues.length) {
    const block = el("div", { class: "comfymodal-studio-editor-block" });
    block.appendChild(el("h4", { class: "comfymodal-studio-editor-block-title", text: "Issues" }));
    block.appendChild(renderIssueRows(issues, "portability-issues", o.onDeepLink));
    section.appendChild(block);
  }

  const targetsBlock = el("div", { class: "comfymodal-studio-editor-block" });
  targetsBlock.appendChild(el("h4", {
    class: "comfymodal-studio-editor-block-title",
    text: "Target readiness",
  }));
  targetsBlock.appendChild(renderTargetMatrix(report));
  section.appendChild(targetsBlock);

  section.appendChild(renderEnvironmentSection(report));
  return section;
}
