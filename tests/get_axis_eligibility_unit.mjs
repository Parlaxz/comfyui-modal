// Modal Studio — getAxisEligibilityForPresets Unit Tests
//
// Executable behavioral tests that import and run the actual module
// function with normalized preset fixtures. No browser required.
//
// Run: node tests/get_axis_eligibility_unit.mjs

import { getAxisEligibilityForPresets } from "../web/studio-preset-capabilities.js";

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

function assertIncluded(arr, item, label) {
  assert(arr.includes(item), `${label}: expected [${arr.join(", ")}] to include "${item}"`);
}

function assertNotIncluded(arr, item, label) {
  assert(!arr.includes(item), `${label}: expected [${arr.join(", ")}] to NOT include "${item}"`);
}

function assertReasonsMissing(result, ctrlId, label) {
  const reasons = result.reasons || {};
  assert(!reasons[ctrlId], `${label}: expected no reason for "${ctrlId}", got "${reasons[ctrlId]}"`);
}

function assertReasonContains(result, ctrlId, substring, label) {
  const reasons = result.reasons || {};
  const reason = reasons[ctrlId];
  assert(
    reason && reason.includes(substring),
    `${label}: expected reason for "${ctrlId}" to contain "${substring}", got "${reason}"`,
  );
}

// ── Fixture helpers ─────────────────────────────────────────────────────

function makePreset(overrides = {}) {
  return {
    id: "p-" + Math.random().toString(36).slice(2, 8),
    label: "Test Preset",
    status: "runnable",
    archived: false,
    compatibleFeatures: ["txt2img"],
    nodeBindings: {},
    ...overrides,
  };
}

function binding(nodeId, widgetName) {
  return { nodeId, widgetName: widgetName || "value", kind: "widget" };
}

// ── Test 1: Two runnable presets both support steps ─────────────────────

console.log("\n=== Test 1: Two runnable presets with steps binding ===");

{
  const p1 = makePreset({
    label: "Preset A",
    nodeBindings: { steps: binding("3") },
  });
  const p2 = makePreset({
    label: "Preset B",
    nodeBindings: { steps: binding("5") },
  });

  const result = getAxisEligibilityForPresets([p1, p2], "txt2img");

  assert(Array.isArray(result), "result should be an array");
  assertIncluded(result, "steps", "steps should be eligible");
  assertReasonsMissing(result, "steps", "steps should have no ineligibility reason");
}

// ── Test 2: One preset missing steps — ineligible with reason ───────────

console.log("\n=== Test 2: One preset missing steps binding ===");

{
  const p1 = makePreset({
    label: "Preset With Steps",
    nodeBindings: { steps: binding("3") },
  });
  const p2 = makePreset({
    label: "Preset Without Steps",
    nodeBindings: {}, // no steps binding
  });

  const result = getAxisEligibilityForPresets([p1, p2], "txt2img");

  assert(Array.isArray(result), "result should be an array");
  assertNotIncluded(result, "steps", "steps should NOT be eligible");
  assertReasonContains(result, "steps", "Preset Without Steps", "reason should name the missing preset");
  assertReasonContains(result, "steps", "Steps", "reason should mention the control label");
}

// ── Test 3: Non-runnable/archived presets don't block runnable pair ─────

console.log("\n=== Test 3: Non-runnable/archived presets ignored ===");

{
  const runnable1 = makePreset({
    label: "Runnable A",
    nodeBindings: { steps: binding("3") },
  });
  const runnable2 = makePreset({
    label: "Runnable B",
    nodeBindings: { steps: binding("5") },
  });
  const nonRunnable = makePreset({
    label: "Non-runnable",
    status: "needs_bindings",
    nodeBindings: {}, // no steps
  });
  const archived = makePreset({
    label: "Archived",
    archived: true,
    nodeBindings: {}, // no steps
  });
  const wrongFeature = makePreset({
    label: "Wrong Feature",
    compatibleFeatures: ["object_remove"],
    nodeBindings: {}, // no steps
  });

  // Pass ALL presets — function must filter to only runnable+compatible
  const result = getAxisEligibilityForPresets(
    [runnable1, nonRunnable, runnable2, archived, wrongFeature],
    "txt2img",
  );

  assert(Array.isArray(result), "result should be an array");
  assertIncluded(result, "steps", "steps should be eligible despite non-runnable/archived/unrelated presets");
  assertReasonsMissing(result, "steps", "steps should have no ineligibility reason");

  // Other controls (prompt, guidance, etc.) will have reasons because the
  // runnable presets don't have those bindings. The key check: those reasons
  // should reference a RUNNABLE preset (not the non-runnable or archived one),
  // confirming only runnable+compatible presets drive the eligibility computation.
  const reasons = result.reasons || {};
  let allReasonsValid = true;
  for (const [ctrlId, reason] of Object.entries(reasons)) {
    // Reasons should NOT mention "Non-runnable" or "Archived" or "Wrong Feature"
    if (reason.includes("Non-runnable") || reason.includes("Archived") || reason.includes("Wrong Feature")) {
      console.error(`  FAIL: reason for "${ctrlId}" mentions non-runnable/archived: "${reason}"`);
      allReasonsValid = false;
    }
    // Reasons SHOULD mention one of the runnable preset labels
    if (!reason.includes("Runnable A") && !reason.includes("Runnable B")) {
      console.error(`  FAIL: reason for "${ctrlId}" does not mention a runnable preset: "${reason}"`);
      allReasonsValid = false;
    }
  }
  assert(allReasonsValid, "all ineligibility reasons reference runnable presets only");
}

// ── Test 4: orRequiredBindingKeys alias resolves correctly ──────────────

console.log("\n=== Test 4: orRequiredBindingKeys alias resolution ===");

{
  // For object_remove, the "instruction" control is satisfied by EITHER
  // "instruction" OR "prompt" binding (see _getBindingKeysForControl):
  //   _getBindingKeysForControl("instruction", "object_remove")
  //   → ["instruction", "prompt"]
  //
  // Preset A has only "prompt" (no "instruction" key).
  // Preset B has only "instruction" (no "prompt" key).
  // With old raw `bindings["instruction"]`, preset A would fail.
  // With isControlBound, both pass via the alias resolution.

  const p1 = makePreset({
    label: "Prompt Only",
    compatibleFeatures: ["object_remove"],
    nodeBindings: {
      prompt: binding("1"), // no "instruction" key
    },
  });
  const p2 = makePreset({
    label: "Instruction Only",
    compatibleFeatures: ["object_remove"],
    nodeBindings: {
      instruction: binding("2"), // no "prompt" key
    },
  });

  const result = getAxisEligibilityForPresets([p1, p2], "object_remove");

  assert(Array.isArray(result), "result should be an array");
  assertIncluded(result, "instruction",
    "instruction should be eligible via orRequired alias (prompt stands in for instruction)");
  assertReasonsMissing(result, "instruction",
    "instruction should have no ineligibility reason");

  // Also verify prompt is separately eligible (both presets have it directly
  // or via the instruction key — though p2 only has instruction, not prompt).
  // isControlBound(p, "prompt", "object_remove") → ["prompt"] → p2 has no
  // prompt key, so prompt would not be eligible.
  // The test focuses on instruction specifically.
}

// ── Report ──────────────────────────────────────────────────────────────

console.log(`\n${passed} passed, ${failures} failed`);
if (failures > 0) {
  console.error(`RED: ${failures} test(s) FAILED`);
  process.exit(1);
} else {
  console.log("GREEN: All getAxisEligibilityForPresets behavioral tests passed");
}
