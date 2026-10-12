// Studio tool-type frontend unit tests (no browser, no network).
//
// Covers: shared Tool Input catalog across five workflow types, truthful
// run-payload workflow types, wizard feature definitions, and image field
// block registration. Run: node --test tests/studio_tool_types_unit.mjs

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

import {
  BINDABLE_INPUTS,
  OUTPUT_BINDING,
  T2I_REQUIRED_INPUTS,
  getWorkflowInputKeys,
  normalizeWorkflowType,
} from "../web/studio-bindable-inputs.js";

import {
  buildRunPayload,
  resolveFeatureId,
  resolveWorkflowType,
  validateMappedValues,
  isImageControlRole,
} from "../web/studio-workflow-run.js";

import { FIELD_BLOCKS } from "../web/studio-field-blocks.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const readWeb = (name) => fs.readFileSync(path.join(ROOT, "web", name), "utf8");

test("T2I required inputs unchanged", () => {
  assert.deepEqual([...T2I_REQUIRED_INPUTS], ["prompt", "seed", "model_unet", "vae", "clip"]);
});

test("shared inputs reused across all five tools", () => {
  for (const role of ["prompt", "seed", "model_unet", "vae", "clip"]) {
    for (const tool of ["t2i", "i2i", "inpaint", "sketch", "outpaint"]) {
      assert.ok(BINDABLE_INPUTS[role].requiredFor.includes(tool), `${role} shared by ${tool}`);
    }
  }
  assert.ok(!BINDABLE_INPUTS.i2i_prompt, "no per-tool prompt duplicate");
  assert.ok(!BINDABLE_INPUTS.inpaint_prompt, "no per-tool prompt duplicate");
});

test("source image and mask are first-class image inputs", () => {
  assert.equal(BINDABLE_INPUTS.source_image.block, "image");
  assert.deepEqual([...BINDABLE_INPUTS.source_image.requiredFor], ["i2i", "inpaint", "sketch", "outpaint"]);
  assert.deepEqual([...BINDABLE_INPUTS.mask.requiredFor], ["inpaint"]);
  assert.deepEqual([...getWorkflowInputKeys("inpaint", true)].sort(), [...INPAINT_SORTED()]);
});

function INPAINT_SORTED() {
  return ["clip", "mask", "model_unet", "prompt", "seed", "source_image", "vae"].sort();
}

test("workflow-type aliases normalize", () => {
  assert.equal(normalizeWorkflowType("txt2img"), "t2i");
  assert.equal(normalizeWorkflowType("img2img"), "i2i");
  assert.equal(normalizeWorkflowType("image_edit"), "i2i");
  assert.equal(normalizeWorkflowType("inpaint"), "inpaint");
});

test("output required for all tools", () => {
  for (const tool of ["t2i", "i2i", "inpaint", "sketch", "outpaint"]) {
    assert.ok(OUTPUT_BINDING.requiredFor.includes(tool));
  }
});

test("run payload reports truthful workflow type", () => {
  const t2i = { workflowId: "w", workflowVersionId: "v", workflowName: "n", controlValues: {}, runContext: { workflow: { workflow_type: "t2i" } } };
  assert.equal(resolveFeatureId(t2i), "txt2img");
  const inp = { workflowId: "w", workflowVersionId: "v", workflowName: "n", controlValues: {}, runContext: { workflow: { workflow_type: "inpaint" } } };
  assert.equal(resolveWorkflowType(inp), "inpaint");
  assert.equal(resolveFeatureId(inp), "inpaint");
  const payload = buildRunPayload("", inp, {}, {});
  assert.equal(payload.featureId, "inpaint");
  assert.equal(payload.workflow_type, "inpaint");
  assert.equal(payload.metadata.workflow_type, "inpaint");
});

test("image inputs ignore stale directory-listing enums", () => {
  assert.ok(isImageControlRole("source_image", { control_kind: "enum", enum_options: ["old.png"] }));
  assert.ok(isImageControlRole("mask", { control_kind: "file" }));
  assert.ok(isImageControlRole("anything", { control_kind: "image" }));
  assert.ok(!isImageControlRole("sampler", { control_kind: "enum", enum_options: ["euler"] }));
  const schema = {
    source_image: { semantic_role: "source_image", control_kind: "image", enum_options: ["old_a.png"], required: true },
    sampler: { semantic_role: "sampler", control_kind: "enum", enum_options: ["euler"], required: false },
  };
  const fresh = validateMappedValues({ source_image: "studio-current-fresh.png", sampler: "euler" }, schema);
  assert.deepEqual(fresh.errors, []);
  assert.equal(fresh.values.source_image, "studio-current-fresh.png");
  const badSampler = validateMappedValues({ sampler: "nope" }, schema);
  assert.ok(badSampler.errors.some((e) => e.field === "sampler"), "closed sampler vocabulary stays strict");
});

test("image field block registered", () => {
  assert.ok(FIELD_BLOCKS.image, "image block exists");
  assert.equal(typeof FIELD_BLOCKS.image.render, "function");
});

test("wizard offers five tools with shared-profile save gates", () => {
  const src = readWeb("studio-workflow-setup-wizard.js");
  for (const id of ["txt2img", "i2i", "inpaint", "sketch", "outpaint"]) {
    assert.ok(src.includes(`"${id}"`), `wizard offers ${id}`);
  }
  assert.ok(src.includes("source_image"), "wizard suggests source image");
  assert.ok(src.includes("collectRequiredBindings(state.selectedFeatures)"), "save gate derives from shared profiles");
});

test("wizard persists the selected workflow type", () => {
  const src = readWeb("studio-workflow-setup-wizard.js");
  assert.ok(src.includes("updateWorkflow"), "wizard can persist workflow type");
  assert.ok(src.includes("_persistWorkflowType"), "type persisted on mapping save");
  assert.ok(src.includes("initialWorkflowType"), "edit mapping initializes from stored type");
});

test("playground has one tool strip and tool editors", () => {
  const src = readWeb("studio-playground.js");
  assert.ok(src.includes("studio-tool-strip"), "tool strip exists");
  assert.ok(src.includes("STUDIO_TOOLS"), "tool catalog exists");
  for (const id of ["t2i", "i2i", "inpaint", "sketch", "outpaint"]) {
    assert.ok(src.includes(`"${id}"`), `tool ${id} listed`);
  }
  assert.ok(src.includes("_renderPaintEditor"), "paint editor exists");
  assert.ok(src.includes("_renderOutpaintEditor"), "outpaint editor exists");
  assert.ok(src.includes("_renderToolEditor"), "tool editor dispatch exists");
  assert.ok(src.includes("shelf-prompt-mode-"), "structured prompt mode exists");
  assert.ok(!src.includes("_commitToolValue"), "editor saves use the validated commit path");
  assert.ok(src.includes("uniqueImageName"), "uploads use unique filenames");
  assert.ok(src.includes("_syncActiveToolToSelection"), "selection syncs the active tool");
  assert.ok(src.includes("_storeStructuredParts"), "structured field breakdown is preserved");
  assert.ok(src.includes("_applyWorkspaceCarry"), "workspace values carry across workflows");
  assert.ok(src.includes("_rememberedToolWorkflow"), "each tool remembers its workflow");
  assert.ok(src.includes("_runSelectionFlow"), "selection paths share one carry flow");
});

test("workflows page shows type filter and badge", () => {
  const src = readWeb("studio-workflows.js");
  assert.ok(src.includes("workflows-type-filter"), "type filter exists");
  assert.ok(src.includes("workflow-card-type"), "type badge exists");
});
