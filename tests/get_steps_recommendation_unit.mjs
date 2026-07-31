// Modal Studio — getRecommendedSteps / Seed Insertion Unit Tests
//
// Executable behavioral tests that import and run the actual module
// functions. No browser required.
//
// Run: node tests/get_steps_recommendation_unit.mjs

import {
  getRecommendedSteps,
  getRecommendedStepsStatus,
  getLastFiniteSeed,
  cryptoRandomSeed,
} from "../web/studio-feature-registry.js";

let failures = 0;
let passed = 0;

function assert(condition, message) {
  if (!condition) {
    console.error("  FAIL:", message);
    failures++;
  } else {
    console.log("  PASS");
    passed++;
  }
}

function makeState(overrides = {}) {
  return {
    playground: {
      featureId: "txt2img",
      selectedBackendId: "preset_1",
      _currentPreset: null,
      _runningExperimentConfig: null,
      ...overrides,
    },
  };
}

function makePreset(defaults) {
  return { id: "preset_1", label: "P1", defaults: defaults || {} };
}

// ── Test 1: Preset-backed recommendation available before any run ────────

console.log("\n=== Test 1: preset-backed recommendation (before runs) ===");

{
  const state = makeState({ _currentPreset: makePreset({ steps: 24 }) });
  const rec = getRecommendedSteps(state);
  assert(rec === 24, `expected 24 from preset defaults, got ${rec}`);
}

// ── Test 2: Hidden (null) when no trustworthy source ─────────────────────

console.log("\n=== Test 2: no trustworthy source -> null ===");

{
  const state = makeState({ _currentPreset: makePreset({}) });
  assert(getRecommendedSteps(state) === null, "no preset steps default -> null");
}

{
  const state = makeState({ _currentPreset: makePreset({ steps: 500 }) });
  assert(getRecommendedSteps(state) === null, "out-of-schema-range steps -> null");
}

{
  const state = makeState({ _currentPreset: makePreset({ steps: 0 }) });
  assert(getRecommendedSteps(state) === null, "steps below min -> null");
}

{
  const noPlayground = {};
  assert(getRecommendedSteps(noPlayground) === null, "missing playground -> null");
}

// ── Test 3: Updates when the selection (preset) changes ──────────────────

console.log("\n=== Test 3: recommendation follows current preset ===");

{
  const state = makeState({ _currentPreset: makePreset({ steps: 30 }) });
  assert(getRecommendedSteps(state) === 30, "switching presets updates recommendation to 30");
}

// ── Test 4: Captured workflow config only trusted for the current selection

console.log("\n=== Test 4: captured run config trust rules ===");

{
  // Captured config for the SAME preset is the most trustworthy source.
  const state = makeState({
    _currentPreset: makePreset({ steps: 24 }),
    _runningExperimentConfig: {
      controls: { steps: 18 },
      presetIds: ["preset_1"],
      featureId: "txt2img",
    },
  });
  assert(getRecommendedSteps(state) === 18, "captured config for current preset wins");
}

{
  // Captured config for a DIFFERENT preset is stale -> fall back to preset.
  const state = makeState({
    _currentPreset: makePreset({ steps: 24 }),
    _runningExperimentConfig: {
      controls: { steps: 18 },
      presetIds: ["preset_other"],
      featureId: "txt2img",
    },
  });
  assert(getRecommendedSteps(state) === 24, "stale captured config ignored -> preset default");
}

{
  // Captured config for a different feature is stale too.
  const state = makeState({
    _currentPreset: makePreset({ steps: 24 }),
    _runningExperimentConfig: {
      controls: { steps: 18 },
      presetIds: ["preset_1"],
      featureId: "object_remove",
    },
  });
  assert(getRecommendedSteps(state) === 24, "stale feature captured config ignored");
}

// ── Test 5: getRecommendedStepsStatus hide/disable ───────────────────────

console.log("\n=== Test 5: recommended-steps status (hide/disable) ===");

{
  const state = makeState({ _currentPreset: makePreset({}) });
  const status = getRecommendedStepsStatus(state, ["20"]);
  assert(status.value === null && status.reason === "", "no recommendation -> hidden (null value)");
}

{
  const state = makeState({ _currentPreset: makePreset({ steps: 24 }) });
  const applied = getRecommendedStepsStatus(state, ["24"]);
  assert(applied.value === 24 && applied.reason !== "", "single value already recommended -> disabled");
  const applicable = getRecommendedStepsStatus(state, ["24", "10"]);
  assert(applicable.value === 24 && applicable.reason === "", "mixed values -> enabled");
  const empty = getRecommendedStepsStatus(state, []);
  assert(empty.value === 24 && empty.reason === "", "no values -> enabled");
}

// ── Test 6: last finite seed semantics ───────────────────────────────────

console.log("\n=== Test 6: getLastFiniteSeed scans from the end ===");

{
  assert(getLastFiniteSeed(["100", "50"]) === 50, "last entry wins over max (100,50 -> 50)");
  assert(getLastFiniteSeed(["100", "50", "49"]) === 49, "last entry wins (100,50,49 -> 49)");
  assert(getLastFiniteSeed(["100", ""]) === 100, "blanks skipped (100,'' -> 100)");
  assert(getLastFiniteSeed(["", ""]) === null, "all blank -> null");
  assert(getLastFiniteSeed([]) === null, "empty list -> null");
  assert(getLastFiniteSeed(["-1"]) === -1, "-1 is finite");
  assert(getLastFiniteSeed("nope") === null, "non-array -> null");
}

// ── Test 7: crypto random seed range ─────────────────────────────────────

console.log("\n=== Test 7: cryptoRandomSeed bounds ===");

{
  const max = 2147483647;
  let allInRange = true;
  for (let i = 0; i < 200; i++) {
    const v = cryptoRandomSeed(max);
    if (!Number.isInteger(v) || v < 0 || v > max) {
      allInRange = false;
      console.error("  out of range value:", v);
      break;
    }
  }
  assert(allInRange, "all draws are integers within [0, max]");
  assert(cryptoRandomSeed(0) === 0, "max 0 always yields 0");
}

// ── Report ───────────────────────────────────────────────────────────────

console.log(`\n${passed} passed, ${failures} failed`);
if (failures > 0) {
  console.error(`RED: ${failures} test(s) FAILED`);
  process.exit(1);
} else {
  console.log("GREEN: All steps recommendation / seed insertion helper tests passed");
}
