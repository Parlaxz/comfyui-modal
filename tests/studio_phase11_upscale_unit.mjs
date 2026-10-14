// Modal Studio — Phase 11 Upscale contract unit tests.
//
// Tests + dependency declarations only: locks the real Phase 11 contract
// owned by web/studio-playground-state.js (panel prefs), 
// web/studio-backend-api.js (Run wiring), studio_upscale_run.py and the
// vosr2/seedvr2 adapters (backend literals + fail-closed dep errors).
//
// No browser, no DOM, no network, no GPU, no deploys. Imports only the
// DOM-free state module with an in-memory localStorage stub (the Phase 3
// methods precedent); everything else is read-only source guards, so this
// phase never modifies web/ or runtime logic.
//
// Run: node tests/studio_phase11_upscale_unit.mjs

import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import {
  SHELL_PLACEHOLDERS,
  UPSCALE_METHODS,
  UPSCALE_METHOD_LABELS,
  loadUpscalePrefs,
  saveUpscalePrefs,
  shellGateReason,
} from "../web/studio-playground-state.js";

const ROOT = path.join(import.meta.dirname, "..");
const WEB = path.join(ROOT, "web");
const readWeb = (name) => fs.readFileSync(path.join(WEB, name), "utf8");
const readRoot = (name) => fs.readFileSync(path.join(ROOT, name), "utf8");

function section(name) {
  console.log("PASS: " + name);
}

const _mem = new Map();
globalThis.localStorage = {
  getItem: (key) => (_mem.has(String(key)) ? _mem.get(String(key)) : null),
  setItem: (key, value) => {
    _mem.set(String(key), String(value));
  },
  removeItem: (key) => {
    _mem.delete(String(key));
  },
  clear: () => {
    _mem.clear();
  },
};

const PREFS_KEY = "comfymodal.studio.upscale.v1";
// Defaults mirror the backend contract: VOSR2, scale 4, explicit seed 0,
// VOSR2 tile edge 512 (no random sentinel, no auto).
const DEFAULTS = { method: "vosr2", scale: 4, seed: 0, tileSize: 512 };

// ── 1. Method selection: explicit literals, no auto ─────────────────────────

{
  assert.deepEqual([...UPSCALE_METHODS], ["vosr2", "seedvr2"]);
  assert.deepEqual({ ...UPSCALE_METHOD_LABELS }, { vosr2: "VOSR2", seedvr2: "SeedVR2" });
  assert.ok(!UPSCALE_METHODS.includes("auto"), "no auto literal");
  _mem.clear();
  assert.deepEqual(loadUpscalePrefs(), DEFAULTS);
  section("U1. Panel methods are exactly vosr2|seedvr2 with VOSR2 default");
}

// ── 2. Pref validation: unknown methods/keys ignored, ranges enforced ───────

{
  _mem.clear();
  // "auto" is not persistable: unknown methods keep the stored default.
  saveUpscalePrefs({ method: "auto", scale: 2 });
  assert.equal(loadUpscalePrefs().method, "vosr2");
  assert.equal(loadUpscalePrefs().scale, 2);
  // Unknown keys never persist.
  saveUpscalePrefs({ bogusKey: "nope", method: "seedvr2" });
  const loaded = loadUpscalePrefs();
  assert.equal(loaded.method, "seedvr2");
  assert.ok(!("bogusKey" in loaded));
  // Out-of-range values fall back to the stored base; tile_size alias honored.
  _mem.clear();
  saveUpscalePrefs({ scale: 99, seed: -1, tileSize: 0 });
  assert.deepEqual(loadUpscalePrefs(), DEFAULTS);
  saveUpscalePrefs({ tile_size: 256 });
  assert.equal(loadUpscalePrefs().tileSize, 256);
  saveUpscalePrefs({ seed: 4294967296 });
  assert.equal(loadUpscalePrefs().seed, 0);
  section("U2. Prefs reject auto/unknown keys and clamp ranges");
}

// ── 3. Pref persistence: round-trip + malformed recovery ────────────────────

{
  _mem.clear();
  saveUpscalePrefs({ method: "seedvr2", scale: 2, seed: 7, tileSize: 512 });
  assert.deepEqual(loadUpscalePrefs(), { method: "seedvr2", scale: 2, seed: 7, tileSize: 512 });
  assert.ok(JSON.parse(_mem.get(PREFS_KEY)).method === "seedvr2");
  _mem.set(PREFS_KEY, "{oops-not-json");
  assert.deepEqual(loadUpscalePrefs(), DEFAULTS);
  _mem.set(PREFS_KEY, "[1,2,3]");
  assert.deepEqual(loadUpscalePrefs(), DEFAULTS);
  section("U3. Prefs round-trip and recover to defaults on corruption");
}

// ── 4. Backend literal parity (single source of truth) ─────────────────────

{
  const run = readRoot("studio_upscale_run.py");
  assert.ok(run.includes('UPSCALE_METHODS = ("vosr2", "seedvr2")'), "py literals pinned");
  assert.ok(run.includes('"studio_upscale_vosr2"') && run.includes('"studio_upscale_seedvr2"'), "remote entrypoints pinned");
  assert.ok(run.includes("COMFYMODAL_UPSCALE_APP_NAME"), "config-owned app env pinned");
  const vosr = readRoot("studio_upscale_vosr2.py");
  const seedvr = readRoot("studio_upscale_seedvr2.py");
  assert.ok(vosr.includes('ERROR_CODE = "VOSR2_UNAVAILABLE"'), "vosr2 fail-closed code");
  assert.ok(seedvr.includes('ERROR_CODE = "SEEDVR2_UNAVAILABLE"'), "seedvr2 fail-closed code");
  const deps = readRoot("studio_upscale_deps.py");
  assert.ok(deps.includes("from studio_upscale_run import"), "deps re-export runtime contract");
  for (const banned of ["import torch", "import modal", "import comfy", "import folder_paths", "import nodes"]) {
    assert.equal(deps.includes(banned), false, `heavy import leaked into deps: ${banned}`);
  }
  const lock = readRoot("upscale_dependency_lock.txt");
  for (const marker of ["vosr2", "seedvr2", "studio_upscale_vosr2", "studio_upscale_seedvr2",
    "COMFYMODAL_VOSR2_WEIGHTS", "COMFYMODAL_SEEDVR2_WEIGHTS", "COMFYMODAL_UPSCALE_APP_NAME"]) {
    assert.ok(lock.includes(marker), `lock missing ${marker}`);
  }
  section("U4. JS/Python literals, dep codes, and lock manifest agree");
}

// ── 5. Run wiring: upscale unblocked, other Post stays local ────────────────

{
  assert.equal(
    shellGateReason("post", "upscale"),
    "Upscale runs from the Run Upscale button in the panel below.",
    "upscale runs via explicit panel Run (never auto, never blocked)",
  );
  assert.ok(
    (shellGateReason("post", "color") || "").includes("runs locally"),
    "other Post categories still run locally",
  );
  assert.ok(!SHELL_PLACEHOLDERS.includes("upscale"), "upscale left the placeholder set");
  assert.ok(SHELL_PLACEHOLDERS.includes("references") && SHELL_PLACEHOLDERS.includes("guidance"));

  const api = readWeb("studio-backend-api.js");
  assert.ok(api.includes("export async function runStudioUpscale"), "upscale entry point exported");
  assert.ok(api.includes('"/studio/upscale"'), "dedicated upscale route posted");
  assert.ok(api.includes("source_image"), "flat backend contract body");
  assert.ok(api.includes("STUDIO_UPSCALE_ERROR"), "failure error code plumbed");
  assert.ok(api.includes("error_code"), "backend error codes surfaced, not swallowed");
  section("U5. Upscale Run wired explicitly; placeholder honesty kept for the rest");
}

// ── 6. Correct input + backend payload shape at source level ────────────────

{
  // The backend owns validation: source_image required basename
  // (traversal-safe), params carry method + source_image + scale.
  assert.ok(runSourceHas("UPSCALE_SOURCE_REQUIRED"), "source required");
  assert.ok(runSourceHas("UPSCALE_BAD_SOURCE"), "traversal refused");
  assert.ok(runSourceHas('"source_image": source_image'), "params carry source");
  assert.ok(runSourceHas('"method": method'), "params carry method");
  assert.ok(runSourceHas('"scale": scale_value'), "params carry scale");
  assert.ok(runSourceHas("UPSCALE_UNKNOWN_METHOD"), "auto rejected by code");
  assert.ok(runSourceHas("(no Auto)"), "no-auto promise in message");
  section("U6. Input is the current image filename; payload carries method+source+scale");

  function runSourceHas(marker) {
    return readRoot("studio_upscale_run.py").includes(marker);
  }
}

// ── 7. Materialization + provenance shape at source level ───────────────────

{
  const run = readRoot("studio_upscale_run.py");
  for (const marker of ['"output_paths"', '"primary_asset_id"', '"meta"',
    '"upscale_method"', '"source_asset"', '"timings"', '"load_ms"',
    '"inference_ms"', 'studio-upscale-', '"runId"']) {
    assert.ok(run.includes(marker), `materialization missing ${marker}`);
  }
  assert.ok(run.includes("Never mutates the stored workflow"), "no-mutation promise");
  // History provenance (additive): repository normalizes backend-projected
  // {method, scale, seed, ...} keys; detail renders one Upscale section
  // with truthful method labels only when present.
  const historyRepo = readWeb("history-v2-repository.js");
  const historyDetail = readWeb("studio-history-v2-detail.js");
  assert.ok(historyRepo.includes("upscale: _firstObject(out.upscale, out.upscale_info, out.upscaleInfo)"), "output-level provenance keys");
  assert.ok(historyRepo.includes("raw.upscale_info"), "record-level provenance keys");
  assert.ok(historyDetail.includes("function _buildUpscaleSection(record)"), "provenance section builder");
  assert.ok(historyDetail.includes('"history-v2-upscale"'), "provenance section testid");
  assert.ok(historyDetail.includes('method === "seedvr2" ? "SeedVR2"'), "SeedVR2 label");
  assert.ok(historyDetail.includes('method === "vosr2" ? "VOSR2"'), "VOSR2 label");
  section("U7. Materialization/provenance shape locked; History carries method/provenance");
}

// ── 8. No workflow mutation; Generate/Edit unaffected ───────────────────────

{
  const run = readRoot("studio_upscale_run.py");
  const workflowLines = run.split("\n").filter((l) => l.toLowerCase().includes("workflow"));
  assert.equal(workflowLines.length, 2, "only the two no-mutation docstring promises");
  for (const name of ["studio_workflow_run.py", "studio_golden_run.py"]) {
    const src = readRoot(name);
    for (const marker of ["vosr2", "seedvr2", "studio_upscale", "UPSCALE_", "upscale_method"]) {
      assert.equal(src.includes(marker), false, `Generate/Edit path untouched: ${name} / ${marker}`);
    }
  }
  const queueSpec = readRoot("tests/browser/fake/studio-fake-queue-manager.spec.mjs");
  assert.ok(queueSpec.includes("upscale"), "queue manager still lists the upscale tool mode");
  section("U8. Workflow JSON unmutated; Generate/Edit paths unaffected");
}

console.log("PASS: studio phase-11 upscale contract unit tests");
