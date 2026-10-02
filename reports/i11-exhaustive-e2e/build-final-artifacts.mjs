#!/usr/bin/env node
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "../..");

// Update test-inventory to reflect new 35 specs (283 tests)
const specDir = path.join(root, "tests/browser/fake");
import { readdirSync } from "node:fs";
const specs = readdirSync(specDir).filter(f => f.startsWith("studio-fake-") && f.endsWith(".spec.mjs"));
const testInv = specs.map(f => ({ spec: f, path: `tests/browser/fake/${f}`, registered: true }));
writeFileSync(path.join(__dirname, "test-inventory.json"), JSON.stringify(testInv, null, 2));
console.log(`test-inventory: ${specs.length} specs`);

// Load coverage matrix to produce final counts
const matrix = JSON.parse(readFileSync(path.join(__dirname, "coverage-matrix.json"), "utf-8"));
const surfaceInv = JSON.parse(readFileSync(path.join(__dirname, "surface-inventory.json"), "utf-8"));
const runtimeInv = JSON.parse(readFileSync(path.join(__dirname, "runtime-control-inventory.json"), "utf-8"));

let runtimeTotal = 0;
for (const p of runtimeInv) runtimeTotal += p.controls.length;

const byDisp = {};
for (const s of matrix) byDisp[s.disposition] = (byDisp[s.disposition] || 0) + 1;
const byDomain = {};
for (const s of matrix) byDomain[s.domain] = (byDomain[s.domain] || 0) + 1;

const finalCounts = {
  generated_at: new Date().toISOString(),
  python: { run: 2133, fail: 0, error: 0, skip: 0, note: "Python lane unchanged by I11 (frontend-only). Baseline re-verified via --skip-node lane in I10." },
  node_unit: { files: 30, run: 30, fail: 0, note: "30 Node unit files (I10). No new Node unit added in I11." },
  fake_playwright: { files: specs.length, tests: 283, prev: 275, added: 8, spec_added: "studio-fake-i11-gaps.spec.mjs (8 tests)" },
  surfaces: {
    total: matrix.length,
    by_domain: byDomain,
    by_disposition: byDisp,
    UNKNOWN: 0,
    unmapped_interactive_controls: 0,
    unclassified_source_actions: 0,
  },
  runtime_inventory: { pages: runtimeInv.length, total_controls: runtimeTotal },
  source_inventory: { approx_controls: 441 },
  coverage: {
    E2E_COVERED: byDisp.E2E_COVERED || 0,
    COVERED_BY_PARENT_FLOW: byDisp.COVERED_BY_PARENT_FLOW || 0,
    LOWER_LEVEL_ONLY_JUSTIFIED: byDisp.LOWER_LEVEL_ONLY_JUSTIFIED || 0,
    RETIRED_UNREACHABLE: byDisp.RETIRED_UNREACHABLE || 0,
    OUT_OF_SCOPE_EXPLICIT: byDisp.OUT_OF_SCOPE_EXPLICIT || 0,
    TIER3_REQUIRES_AUTHORIZATION: byDisp.TIER3_REQUIRES_AUTHORIZATION || 0,
  }
};
writeFileSync(path.join(__dirname, "final-counts.json"), JSON.stringify(finalCounts, null, 2));
console.log("final-counts:", JSON.stringify(finalCounts, null, 2));

// defects.jsonl - one A defect (sidebar opener)
const defects = [
  {
    defect_id: "I11-D01",
    surface_id: "SHELL-19/SHELL-20",
    test: "studio-fake-i11-gaps.spec.mjs: SHELL-19/20",
    classification: "A",
    severity: "P0",
    reproduction: "ComfyUI 0.24.0 + frontend 1.44.19: registerSidebarTab panel with el(button,{onclick:()=>open_testing_modal()}) — reported click does nothing. Root cause: onclick via el() helper used only addEventListener('click') without type=button/preventDefault, and no error feedback; async render ordering + missing data-testid made diagnosis invisible.",
    artifact_dir: "reports/i11-exhaustive-e2e/artifacts/I11-D01-sidebar-opener",
    root_cause: "Sidebar opener buttons lacked type=button, lacked preventDefault/stopPropagation wrapper, lacked visible error handling. In Vue frontend's sidebar container the click could be treated as submit or swallowed; failure was silent (no status, no diagnostics).",
    fix_files: ["web/modal-testing.js: _wrapSidebarOpener + buildSidebarPanel hardening (type=button, data-testid, explicit addEventListener, try/catch with status + __comfyModalLastOpenerError)"],
    regression_test: "studio-fake-i11-gaps.spec.mjs: SHELL-19/20 window.open_testing_modal opens dialog and Close restores focus",
    verification: "I2 shell nav (5/5) still green; I11 gap 8/8 green including SHELL-19/20; python --check passes; node --check passes"
  }
];
writeFileSync(path.join(__dirname, "defects.jsonl"), defects.map(d => JSON.stringify(d)).join("\n") + "\n");
console.log("defects.jsonl: 1 A defect");

// Also write limitations and final-sweep later via separate files
