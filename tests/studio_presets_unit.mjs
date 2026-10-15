// Modal Studio — Phase 12 Presets frontend unit tests.
//
// Executable behavioral tests for the DOM-free preset core
// (web/studio-presets.js): allowlist serialization, dirty-state image
// exclusion, hydration image-clearing, schema/legacy-compat, no-leakage with
// pre-existing session images, and method/reference/guidance restoration.
//
// Section shapes mirror the backend contract (studio_domain/preset_state.py
// — the server stays the authority): all nine sections always emitted, flat
// native layout, pair-or-null method/reference overrides, string mapping
// revisions, object guidance controllers, frozen post recipe scalars, flat
// output options.
//
// No browser, no DOM, plain Node.
//
// Run: node --test tests/studio_presets_unit.mjs

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  PRESET_SCHEMA_VERSION,
  PRESET_STATE_MAX_BYTES,
  PRESET_SECTIONS,
  capturePresetState,
  validatePresetState,
  planPresetHydration,
  neutralPresetSection,
  presetDraftKey,
  buildPresetSavePayload,
  composePresetStylePrompt,
  resolvePresetPrompt,
  isImageKey,
  isImageLikeValue,
  isBackendImageValue,
} from "../web/studio-presets.js";

const SHA64 = "a".repeat(64);

function richOwnerSnapshots() {
  return {
    core: {
      positive_prompt: "a lighthouse",
      negative_prompt: "blurry",
      controls: { steps: 28, cfg: 7, prompt: "a lighthouse", width: 1024 },
      activeMode: "generate",
      activeSubtool: "text",
      skipTextGenerate: false,
    },
    styles: { setId: "curated", selectedId: "cinematic", basePrompt: "a lighthouse" },
    layout: {
      high_level_description: "hero shot",
      background: "coast",
      style_mode: "photo",
      aesthetics: "",
      lighting: "dusk",
      photo: "",
      medium: "",
      art_style: "",
      color_palette: ["#112233"],
      width: 1024,
      height: 1024,
      bgBrightness: 25,
      boxes: [
        {
          id: "b1",
          type: "text",
          x: 0.1,
          y: 0.1,
          w: 0.5,
          h: 0.2,
          desc: "title",
          text: "HELLO",
          color_palette: ["#ff0000"],
          nobbox: false,
          locked: false,
        },
      ],
    },
    methods: {
      inpaintMethod: "crop_stitch",
      inpaintOverride: { workflow_id: "wf_1", workflow_version_id: "wv_1" },
      expandMethod: "pad_preserve",
      expandOverride: null,
      padTop: 0,
      padRight: 256,
      padBottom: 0,
      padLeft: 0,
    },
    references: {
      method: "conditioning_slots",
      override: null,
      cards: [{ label: "pose ref", file: "ref-1.png", id: "r1" }],
    },
    guidance: {
      engaged: true,
      mode: "canny",
      mechanism: "CONTROLNET_CONDITIONING",
      model_sha256: SHA64.toUpperCase(),
      mapping_revision: "r3",
      controller: { checkpoint: "ctrl.safetensors", folder: "controlnet", checkpoint_sha256: "" },
      nodes: { loader: "L", apply: "A", preprocessor: "P" },
      conditioning: { strength: 0.7, start: 0, end: 0.8 },
    },
    sketch: {
      tool: "brush",
      brushSize: 12,
      opacity: 0.9,
      hardness: 0.5,
      color: "#000000",
      bgColor: "#ffffff",
      width: 1024,
      height: 1024,
    },
    post: {
      recipe: { format: "png", quality: 95, embedMetadata: true },
    },
    output: {
      output_format: "png",
      quality: 90,
      auto_save_local: true,
      save_folder: "output/modal",
      save_metadata_sidecar: true,
      preview_default: "on",
      preview_codec: "webp",
      preview_quality: 80,
    },
  };
}

describe("allowlist serialization", () => {
  it("always emits all nine sections (the backend requires every section)", () => {
    const state = capturePresetState({ core: { positive_prompt: "hi" } });
    assert.equal(state.schema_version, 1);
    for (const section of PRESET_SECTIONS) {
      assert.ok(state[section] && typeof state[section] === "object", "missing section " + section);
    }
    // Neutral core still carries its required fields.
    assert.equal(state.core.skipTextGenerate, false);
    assert.deepEqual(state.core.controls, {});
    // Absent owners degrade to neutral, never to missing.
    assert.deepEqual(state.references.cards, []);
    assert.equal(state.references.override, null);
    assert.equal(state.guidance.engaged, false);
  });

  it("projects layout to the flat native shape", () => {
    const state = capturePresetState(richOwnerSnapshots());
    assert.equal(state.layout.high_level_description, "hero shot");
    assert.equal(state.layout.background, "coast");
    assert.equal(state.layout.style_mode, "photo");
    // Native lists serialize to palette strings (backend shape).
    assert.equal(state.layout.color_palette, "#112233");
    assert.deepEqual(state.layout.boxes, [
      {
        id: "b1",
        type: "text",
        x: 0.1,
        y: 0.1,
        w: 0.5,
        h: 0.2,
        desc: "title",
        text: "HELLO",
        color_palette: "#ff0000",
        nobbox: false,
        locked: false,
      },
    ]);
    assert.deepEqual(state.layout.dims, undefined);
    assert.ok(!("descriptor" in state.layout));
    assert.ok(!("modes" in state.layout));
  });

  it("generates box ids when missing (the backend requires non-empty ids)", () => {
    const state = capturePresetState({ layout: { boxes: [{ type: "obj", x: 0, y: 0, w: 1, h: 1 }] } });
    assert.ok(typeof state.layout.boxes[0].id === "string" && state.layout.boxes[0].id);
  });

  it("projects references to labels only, dropping empty labels", () => {
    const state = capturePresetState(richOwnerSnapshots());
    assert.deepEqual(state.references, {
      method: "conditioning_slots",
      override: null,
      cards: [{ label: "pose ref" }],
    });
    const withEmpty = capturePresetState({
      references: { method: "", override: null, cards: [{ label: "" }, { label: "  " }, { label: "ok" }] },
    });
    assert.deepEqual(withEmpty.references.cards, [{ label: "ok" }]);
  });

  it("projects method/reference overrides as pairs-or-null (bare ids degrade to null)", () => {
    const state = capturePresetState(richOwnerSnapshots());
    assert.deepEqual(state.methods.inpaintOverride, { workflow_id: "wf_1", workflow_version_id: "wv_1" });
    assert.equal(state.methods.expandOverride, null);
    const bare = capturePresetState({
      methods: { inpaintMethod: "crop_stitch", inpaintOverride: "wf_9", expandMethod: null },
      references: { method: "", override: "wf_9", cards: [] },
    });
    assert.equal(bare.methods.inpaintOverride, null);
    assert.equal(bare.references.override, null);
  });

  it("projects guidance without any guide image, revision as string", () => {
    const state = capturePresetState(richOwnerSnapshots());
    assert.equal(state.guidance.engaged, true);
    assert.equal(state.guidance.model_sha256, SHA64);
    assert.equal(state.guidance.mapping_revision, "r3");
    assert.deepEqual(state.guidance.controller, {
      checkpoint: "ctrl.safetensors",
      folder: "controlnet",
      checkpoint_sha256: "",
    });
    assert.deepEqual(state.guidance.conditioning, { strength: 0.7, start: 0, end: 0.8 });
    assert.ok(!("guideImage" in state.guidance));
    assert.ok(!("guide_image" in state.guidance));
  });

  it("drops malformed model digests (the backend requires 64-hex-or-empty)", () => {
    const state = capturePresetState({ guidance: { engaged: true, model_sha256: "ABCDEF" } });
    assert.equal(state.guidance.model_sha256, "");
  });

  it("keeps only the frozen post recipe scalars", () => {
    const state = capturePresetState({
      post: {
        recipe: {
          format: "png",
          quality: 95,
          embedMetadata: true,
          exposure: 5,
          curves: { master: [[0, 0]] },
          spots: [{ x: 0.1 }],
          lutId: "filmic",
        },
      },
    });
    assert.deepEqual(state.post, { recipe: { format: "png", quality: 95, embedMetadata: true } });
  });

  it("projects output to the flat shape (no nested save/preview objects)", () => {
    const state = capturePresetState(richOwnerSnapshots());
    assert.equal(state.output.output_format, "png");
    assert.equal(state.output.quality, 90);
    assert.equal(state.output.auto_save_local, true);
    assert.equal(state.output.save_folder, "output/modal");
    assert.equal(state.output.preview_default, "on");
    assert.ok(!("save" in state.output));
    assert.ok(!("preview" in state.output && typeof state.output.preview === "object"));
    assert.ok(!("format" in state.output));
  });
});

describe("visible prompt capture (stale-mapping safe)", () => {
  it("captures the structured composition (Subject + Style) as the prompt", () => {
    const state = capturePresetState({
      core: {
        positive_prompt: "",
        prompt: "",
        structuredParts: {
          subject: "PHASE12 POSITIVE PROMPT",
          style: "PHASE12 STYLE",
          details: "",
          composition: "",
        },
        promptMode: "structured",
        controls: { seed: 12345 },
      },
    });
    assert.equal(state.core.positive_prompt, "PHASE12 POSITIVE PROMPT, PHASE12 STYLE");
    // Role-specific survival: the scalar seed captures alongside the prompt.
    assert.equal(state.core.controls.seed, 12345);
  });

  it("structured mode owns the value even when empty (clear saves empty)", () => {
    const state = capturePresetState({
      core: {
        positive_prompt: "stale store value",
        structuredParts: { subject: "", style: "", details: "", composition: "" },
        promptMode: "structured",
        controls: {},
      },
    });
    assert.equal(state.core.positive_prompt, "");
  });

  it("captures text prompts under either alias", () => {
    assert.equal(
      capturePresetState({ core: { positive_prompt: "typed hello", controls: {} } }).core.positive_prompt,
      "typed hello"
    );
    assert.equal(
      capturePresetState({ core: { prompt: "bare alias value", controls: {} } }).core.positive_prompt,
      "bare alias value"
    );
  });

  it("text mode ignores superseded structured parts", () => {
    const state = capturePresetState({
      core: {
        prompt: "text wins",
        structuredParts: { subject: "stale breakdown", style: "", details: "", composition: "" },
        promptMode: "text",
        controls: {},
      },
    });
    assert.equal(state.core.positive_prompt, "text wins");
  });

  it("resolvePresetPrompt prefers the first non-empty alias", () => {
    assert.equal(resolvePresetPrompt({ positive_prompt: "a", prompt: "b" }), "a");
    assert.equal(resolvePresetPrompt({ positive_prompt: "", prompt: "b" }), "b");
    assert.equal(resolvePresetPrompt({ positive_prompt: "", prompt: "" }), "");
    assert.equal(resolvePresetPrompt({}), "");
  });

  it("an empty saved prompt plans present-but-empty (replace, never inherit)", () => {
    const state = capturePresetState({ core: { positive_prompt: "", controls: {} } });
    const plan = planPresetHydration(state, {});
    assert.equal(plan.sections.core.present, true);
    assert.equal(plan.sections.core.value.positive_prompt, "");
  });
});

describe("dirty-state image exclusion", () => {
  it("drops image-bearing control keys and values", () => {
    const state = capturePresetState({
      core: {
        positive_prompt: "a lighthouse",
        controls: {
          steps: 28,
          source_image: "upload-1.png",
          mask: "mask-1.png",
          guideImage: "data:image/png;base64,AAAA",
          prompt: "data:image/png;base64,BBBB",
          innocent: "clean",
        },
      },
    });
    assert.deepEqual(state.core.controls, { steps: 28, innocent: "clean" });
  });

  it("drops blob/https/base64 values anywhere", () => {
    const bad = {
      core: {
        controls: {
          a: "blob:http://x/1",
          b: "https://cdn.example/img.png",
        },
      },
      styles: { basePrompt: "data:image/png;base64,AAAA" },
      layout: { high_level_description: "ok", background: "blob:https://x" },
    };
    const state = capturePresetState(bad);
    assert.deepEqual(state.core.controls, {});
    assert.equal(state.styles.basePrompt, "");
    assert.equal(state.layout.background, "");
  });

  it("never captures owner image leftovers (savedMask, files, urls)", () => {
    const state = capturePresetState({
      methods: { inpaintMethod: "crop_stitch", savedMask: "m.png", savedMaskSource: "s.png" },
      references: { method: "", cards: [{ label: "a", file: "f.png" }] },
      sketch: { tool: "brush", baseImageUrl: "http://x/i.png", pixels: "AAAA" },
      output: { output_format: "png", imageUrl: "http://x/o.png" },
    });
    assert.ok(!("savedMask" in state.methods));
    assert.ok(!("savedMaskSource" in state.methods));
    assert.deepEqual(state.references.cards, [{ label: "a" }]);
    assert.ok(!("baseImageUrl" in state.sketch));
    assert.ok(!("imageUrl" in state.output));
  });

  it("isImageKey flags image/history/compare keys", () => {
    for (const key of [
      "source_image",
      "mask",
      "savedMask",
      "file",
      "imageUrl",
      "guideImage",
      "historyPreviewId",
      "run_id",
      "compareSlot",
      "bbox",
      "thumbnailUrl",
    ]) {
      assert.equal(isImageKey(key), true, key);
    }
    assert.equal(isImageKey("steps"), false);
    assert.equal(isImageKey("positive_prompt"), false);
    assert.equal(isImageKey("label"), false);
    assert.equal(isImageKey("crop"), false);
    assert.equal(isImageKey("preview"), false);
  });

  it("value rules: capture drops broadly, backend rule matches the server", () => {
    assert.equal(isImageLikeValue("data:image/png;base64,AAAA"), true);
    assert.equal(isImageLikeValue("blob:https://x"), true);
    assert.equal(isImageLikeValue("https://x/y.png"), true);
    assert.equal(isImageLikeValue("a lighthouse"), false);
    assert.equal(isBackendImageValue("data:image/png;base64,AAAA"), true);
    assert.equal(isBackendImageValue("blob:https://x"), true);
    assert.equal(isBackendImageValue("https://x/y.png"), true);
    assert.equal(isBackendImageValue("a lighthouse"), false);
  });
});

describe("hydration image-clearing", () => {
  it("double-projects so poisoned post-validation fields cannot survive", () => {
    const state = capturePresetState(richOwnerSnapshots());
    // Poison after capture (simulates a bypassed validator / tampered store).
    state.core.controls.source_image = "evil.png";
    state.references.cards = [{ label: "x", file: "evil.png" }];
    state.guidance.guideImage = "data:image/png;base64,AAAA";
    const plan = planPresetHydration(state, {});
    const serialized = JSON.stringify(plan.sections);
    assert.ok(!serialized.includes("evil.png"));
    assert.ok(!serialized.includes("data:image"));
    assert.ok(!serialized.includes("guideImage"));
    assert.ok(!serialized.includes("source_image"));
  });

  it("omitted sections hydrate to neutral, never inherit", () => {
    const state = capturePresetState({ core: { positive_prompt: "hi" } });
    delete state.layout;
    delete state.guidance;
    const plan = planPresetHydration(state, {});
    // Missing sections are blocking (the backend requires them)...
    assert.ok(plan.issues.some((i) => i.code === "missing_section" && i.blocking));
    // ...and plan to neutral, never to live values.
    assert.equal(plan.sections.layout.present, false);
    assert.deepEqual(plan.sections.layout.value.boxes, []);
    assert.equal(plan.sections.guidance.value.engaged, false);
    assert.deepEqual(plan.sections.references.value.cards, []);
  });
});

describe("schema and legacy compat", () => {
  it("rejects wrong schema versions as blocking", () => {
    const plan = planPresetHydration({ schema_version: 2, core: {} }, {});
    assert.ok(plan.issues.some((i) => i.code === "schema_mismatch" && i.blocking));
    // Fail closed: present sections plan to neutral.
    assert.deepEqual(plan.sections.core.value.controls, {});
  });

  it("rejects unknown sections as blocking", () => {
    const res = validatePresetState(Object.assign(capturePresetState({}), { upscale: {} }));
    assert.equal(res.ok, false);
    assert.ok(res.issues.some((i) => i.code === "unknown_section" && i.blocking));
  });

  it("rejects missing sections as blocking (mirrors the backend)", () => {
    const state = capturePresetState({});
    delete state.output;
    const res = validatePresetState(state);
    assert.equal(res.ok, false);
    assert.ok(res.issues.some((i) => i.code === "missing_section" && i.blocking));
  });

  it("rejects image-bearing state as blocking", () => {
    const state = capturePresetState({});
    state.core.controls = { a: 1 };
    state.core.mask = "m.png";
    const res = validatePresetState(state);
    assert.equal(res.ok, false);
    assert.ok(res.issues.some((i) => i.code === "image_key" && i.blocking));
  });

  it("rejects null control values (the backend requires scalars)", () => {
    const state = capturePresetState({});
    state.core.controls = { steps: null };
    const res = validatePresetState(state);
    assert.equal(res.ok, false);
    assert.ok(res.issues.some((i) => i.code === "control_scalar" && i.blocking));
  });

  it("treats absent studio_state (legacy records) as nothing-to-hydrate", () => {
    const res = validatePresetState(null);
    assert.equal(res.ok, true);
    assert.equal(res.legacy, true);
    const plan = planPresetHydration(null, {});
    assert.equal(plan.issues.length, 0);
    for (const section of PRESET_SECTIONS) {
      assert.equal(plan.sections[section].present, false);
    }
  });

  it("enforces the 64KiB cap", () => {
    assert.equal(PRESET_STATE_MAX_BYTES, 65536);
    const big = capturePresetState({});
    big.core.positive_prompt = "x".repeat(70000);
    const res = validatePresetState(big);
    assert.equal(res.ok, false);
    assert.ok(res.issues.some((i) => i.code === "too_large"));
  });
});

describe("no leakage with pre-existing session images", () => {
  it("capture ignores session image state even when owners hold it", () => {
    const owners = richOwnerSnapshots();
    owners.sessionImages = {
      sources: ["a.png"],
      masks: ["m.png"],
      guides: ["g.png"],
      sketchBuffer: "AAAA",
      compare: ["c.png"],
      outputs: ["o.png"],
    };
    const state = capturePresetState(owners);
    const serialized = JSON.stringify(state);
    assert.ok(!serialized.includes("sessionImages"));
    assert.ok(!serialized.includes("sketchBuffer"));
    const res = validatePresetState(state);
    assert.equal(res.ok, true);
  });
});

describe("method / reference / guidance restoration", () => {
  it("restores bound methods cleanly", () => {
    const plan = planPresetHydration(capturePresetState(richOwnerSnapshots()), {
      boundReferenceMethod: "conditioning_slots",
      referenceSlotCount: 4,
      guidanceMapping: { record: { model_sha256: SHA64 } },
      styleSetIds: ["curated"],
      styleIds: ["cinematic"],
    });
    assert.equal(plan.issues.filter((i) => i.blocking).length, 0);
    assert.equal(plan.sections.methods.value.inpaintMethod, "crop_stitch");
    assert.deepEqual(plan.sections.methods.value.inpaintOverride, {
      workflow_id: "wf_1",
      workflow_version_id: "wv_1",
    });
    assert.equal(plan.sections.references.value.method, "conditioning_slots");
    assert.equal(plan.sections.guidance.value.engaged, true);
  });

  it("fails closed on stale reference methods with bounded warnings (never silent switch)", () => {
    const plan = planPresetHydration(capturePresetState(richOwnerSnapshots()), {
      boundReferenceMethod: "dedicated",
      guidanceMapping: { record: {} },
      styleSetIds: ["curated"],
      styleIds: ["cinematic"],
    });
    const codes = plan.issues.map((i) => i.code);
    assert.ok(codes.includes("stale_reference_method"));
    // Rest preserved: methods + guidance survive.
    assert.equal(plan.sections.methods.value.inpaintMethod, "crop_stitch");
    assert.equal(plan.sections.guidance.value.engaged, true);
    assert.equal(plan.sections.references.value.method, "");
  });

  it("blocks guidance on missing mapping (requested mode preserved, run stays blocked)", () => {
    const plan = planPresetHydration(capturePresetState(richOwnerSnapshots()), {
      guidanceMapping: null,
    });
    const issue = plan.issues.find((i) => i.code === "guidance_mapping_missing");
    assert.ok(issue && issue.blocking);
    // Never silently reset to Off: the requested mode stays restored so the
    // normal Phase-9 check shows its blocked/manual state with the gate on.
    assert.equal(plan.sections.guidance.value.engaged, true);
    assert.equal(plan.sections.guidance.value.mode, "canny");
  });

  it("blocks guidance on stale mapping (requested mode preserved, never auto-reconfirmed)", () => {
    const plan = planPresetHydration(capturePresetState(richOwnerSnapshots()), {
      guidanceMapping: { record: {}, stale: true, staleDetail: "checkpoint changed" },
    });
    const issue = plan.issues.find((i) => i.code === "guidance_mapping_stale");
    assert.ok(issue && issue.blocking);
    assert.equal(plan.sections.guidance.value.engaged, true);
    assert.equal(plan.sections.guidance.value.mode, "canny");
  });

  it("restores labeled empty cards on an unbound version (bounded warning, no silent drop)", () => {
    const owners = richOwnerSnapshots();
    owners.references = {
      method: "conditioning_slots",
      override: null,
      cards: [{ label: "Character" }, { label: "Lighting" }],
    };
    const plan = planPresetHydration(capturePresetState(owners), {
      boundReferenceMethod: "",
      guidanceMapping: { record: {} },
      styleSetIds: ["curated"],
      styleIds: ["cinematic"],
    });
    const issue = plan.issues.find((i) => i.code === "reference_unbound");
    assert.ok(issue && !issue.blocking);
    // Labels/order/method restore with images empty (cards carry only
    // {label} by contract; fresh runtime ids + empty files happen at apply).
    assert.equal(plan.sections.references.value.method, "conditioning_slots");
    assert.deepEqual(plan.sections.references.value.cards, [{ label: "Character" }, { label: "Lighting" }]);
  });

  it("still fails closed on a stale reference method (labels unset, rest preserved)", () => {
    const owners = richOwnerSnapshots();
    owners.references = {
      method: "conditioning_slots",
      override: null,
      cards: [{ label: "Character" }],
    };
    const plan = planPresetHydration(capturePresetState(owners), {
      boundReferenceMethod: "dedicated",
      guidanceMapping: { record: {} },
    });
    assert.ok(plan.issues.some((i) => i.code === "stale_reference_method"));
    assert.equal(plan.sections.references.value.method, "");
    assert.deepEqual(plan.sections.references.value.cards, []);
  });

  it("warns bounded on missing style id and preserves the rest", () => {
    const plan = planPresetHydration(capturePresetState(richOwnerSnapshots()), {
      styleSetIds: ["curated"],
      styleIds: ["other-style"],
    });
    const issue = plan.issues.find((i) => i.code === "stale_style");
    assert.ok(issue && !issue.blocking);
    assert.equal(plan.sections.styles.value.selectedId, "");
    assert.equal(plan.sections.core.value.positive_prompt, "a lighthouse");
  });
});

describe("save payload and helpers", () => {
  it("requires a name and enforces backend metadata caps", () => {
    assert.equal(buildPresetSavePayload({ name: "  ", studio_state: capturePresetState({}) }).ok, false);
    assert.equal(
      buildPresetSavePayload({ name: "x".repeat(201), studio_state: capturePresetState({}) }).ok,
      false
    );
    assert.equal(
      buildPresetSavePayload({ name: "n", description: "x".repeat(2001), studio_state: capturePresetState({}) }).ok,
      false
    );
  });

  it("builds a bounded save payload with trimmed deduped tags", () => {
    const res = buildPresetSavePayload({
      name: "  My preset  ",
      description: "d",
      tags: ["a", "b", "a", "  ", 42],
      studio_state: capturePresetState(richOwnerSnapshots()),
    });
    assert.equal(res.ok, true);
    assert.equal(res.payload.name, "My preset");
    assert.deepEqual(res.payload.tags, ["a", "b"]);
  });

  it("keys working drafts by exact version + preset id", () => {
    assert.equal(presetDraftKey("v1", "p1"), "v1::p1");
  });

  it("composes style prompts once (base restored, fragment appended)", () => {
    assert.equal(composePresetStylePrompt("a lighthouse", "cinematic light"), "a lighthouse, cinematic light");
    assert.equal(composePresetStylePrompt("", "frag"), "frag");
    assert.equal(composePresetStylePrompt("base", ""), "base");
  });

  it("exposes neutral defaults per section", () => {
    assert.equal(neutralPresetSection("guidance").engaged, false);
    assert.equal(neutralPresetSection("guidance").mapping_revision, "");
    assert.deepEqual(neutralPresetSection("references").cards, []);
    assert.equal(neutralPresetSection("references").override, null);
    assert.equal(neutralPresetSection("methods").inpaintOverride, null);
    assert.equal(neutralPresetSection("methods").padRight, 256);
    assert.deepEqual(neutralPresetSection("output"), {});
    assert.equal(PRESET_SCHEMA_VERSION, 1);
  });
});
