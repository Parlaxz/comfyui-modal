// Modal Studio — Portability Checklist generator (Phase G12)
//
// DETERMINISTIC, DERIVED advice rendered from a backend portability report.
// The checklist is NOT the canonical artifact — the Studio Workflow Manifest
// remains the single authority (G5 §12). This module never invents dependency
// facts that the report does not carry and never emits secret values.
//
// Pure module: no DOM access. Safe to import in Node unit tests.

import { sanitizeFilenamePart } from "./history-v2-browser-download.js";
import {
  PORTABILITY_TARGET_ORDER,
  TARGET_LABELS,
  normalizeRiskLevel,
  riskLabel,
} from "./studio-portability.js";

const CHECKLIST_NOTE =
  "Derived advice generated from the backend portability report. " +
  "This checklist is NOT the canonical workflow manifest; the manifest " +
  "(.workflow.json) remains the artifact of record.";

function _mdEscape(text) {
  return String(text == null ? "" : text)
    .replace(/\r?\n/g, " ")
    .trim();
}

function _issueLine(issue) {
  const sev = riskLabel(issue && issue.severity);
  const msg = _mdEscape(issue && issue.message);
  const hint = _mdEscape(issue && issue.fix_hint);
  let line = "- [" + sev + "] " + msg;
  if (hint) line += " _Fix hint:_ " + hint;
  return line;
}

/**
 * Build the deterministic Markdown checklist.
 *
 * inputs: { report, workflowName, versionNumber }
 * Section order is stable: header/summary → issues → dependency notes →
 * target matrix → environment → import expectations → provenance.
 */
export function buildPortabilityChecklist(inputs) {
  const i = inputs || {};
  const report = i.report || {};
  const workflowName = String(i.workflowName || "Workflow");
  const versionNumber = i.versionNumber != null ? String(i.versionNumber) : "?";
  const lines = [];

  // Workflow / version
  lines.push("# Portability checklist \u2014 " + _mdEscape(workflowName) + " v" + versionNumber);
  lines.push("");
  lines.push(_mdEscape(CHECKLIST_NOTE));
  lines.push("");

  // Summary risk
  lines.push("## Summary");
  lines.push("");
  lines.push("- Workflow portability risk: **" + riskLabel(report.risk_level) + "**");
  const count = Number(report.issue_count);
  lines.push("- Issues: " + (Number.isFinite(count) ? count : 0));
  if (report.stale === true) lines.push("- Report state: STALE (requires recheck)");
  else if (report.stale === false) lines.push("- Report state: current cached result");
  else lines.push("- Report state: freshness not verified");
  lines.push("");

  // Issue counts by severity
  const counts = report.counts || {};
  lines.push("## Issue counts");
  lines.push("");
  lines.push("- High: " + (Number(counts.high) || 0));
  lines.push("- Medium: " + (Number(counts.medium) || 0));
  lines.push("- Low: " + (Number(counts.low) || 0));
  lines.push("");

  // Issues + fix rows
  lines.push("## Issues");
  lines.push("");
  const issues = Array.isArray(report.issues) ? report.issues : [];
  if (issues.length === 0) {
    lines.push("- None reported.");
  } else {
    issues.forEach((issue) => lines.push(_issueLine(issue)));
  }
  lines.push("");

  // Dependency notes — only from facts present in the report.
  lines.push("## Dependency notes");
  lines.push("");
  const depIssues = issues.filter((x) => {
    const s = x && x.subject ? String(x.subject) : "";
    return s === "models" || s === "custom_nodes";
  });
  const unresolved = report.signals && Number(report.signals.unresolved_node_count);
  if (depIssues.length === 0 && !(Number.isFinite(unresolved) && unresolved > 0)) {
    lines.push("- No dependency findings were included in the report.");
  } else {
    depIssues.forEach((x) => lines.push(_issueLine(x)));
    if (Number.isFinite(unresolved) && unresolved > 0) {
      lines.push("- Unresolved node types: " + unresolved);
    }
  }
  lines.push("");

  // Target matrix
  lines.push("## Target readiness");
  lines.push("");
  const targets = report.targets || {};
  PORTABILITY_TARGET_ORDER.forEach((tid) => {
    const t = targets[tid];
    const level = t ? riskLabel(t.risk_level) : "Unknown";
    const advice = t && Array.isArray(t.advice) ? t.advice.map(_mdEscape).filter(Boolean) : [];
    let row = "- " + (TARGET_LABELS[tid] || tid) + ": **" + level + "**";
    if (advice.length) row += " \u2014 " + advice.join("; ");
    lines.push(row);
  });
  lines.push("");

  // Source environment reproducibility (separate dimension)
  lines.push("## Source environment reproducibility");
  lines.push("");
  const env = report.environment || null;
  lines.push(
    "- Reproducibility of the CURRENT source runtime: **" +
      (env ? riskLabel(env.risk_level) : "Unknown") + "**"
  );
  lines.push(
    "- Note: this evaluates the source runtime itself, not this WorkflowVersion's portability."
  );
  if (env && Array.isArray(env.issues) && env.issues.length) {
    env.issues.forEach((x) => lines.push(_issueLine(x)));
  }
  lines.push("");

  // Import expectations
  lines.push("## Import expectations");
  lines.push("");
  lines.push("- Importing a manifest creates a NEW Workflow with Version #1, a Mapping, and optional presets.");
  lines.push("- Missing dependencies do not block import; the imported Workflow may not run until they are resolved.");
  lines.push("- Nothing is installed, fetched, or executed during import.");
  lines.push("");

  // Provenance
  lines.push("## Provenance");
  lines.push("");
  lines.push("- Version id: " + _mdEscape(report.version_id || ""));
  if (report.graph_hash) lines.push("- Graph hash: " + _mdEscape(String(report.graph_hash).slice(0, 10)));
  lines.push("- Rule version: " + _mdEscape(report.rule_version || ""));
  lines.push("- Analyzed at: " + _mdEscape(report.analyzed_at || ""));
  lines.push("");

  return lines.join("\n") + "\n";
}

/**
 * Deterministic checklist filename:
 * `<workflow>-v<N>-portability-checklist.md` with sanitized parts.
 */
export function buildChecklistFilename(workflowName, versionNumber) {
  const name = sanitizeFilenamePart(workflowName, 40) || "workflow";
  const v = String(versionNumber != null ? versionNumber : "0").replace(/[^0-9]/g, "") || "0";
  return name + "-v" + v + "-portability-checklist.md";
}
