// Modal Studio — Phase 9 Guidance frontend unit tests.
//
// Executable behavioral tests for the pure DOM-free logic module
// (web/studio-guidance.js): state machine transitions, poison-proof
// payload building, synthetic unseen-SHA manual flow, engaged-but-blocked
// snapshot shape, structural anchor discovery, installed-artifact listings,
// generic provenance projection, and the no-family hardcoding gate.
//
// No browser, no DOM, plain Node. All graphs, node types, checkpoints,
// and model digests are synthetic.
//
// Run: node --test tests/studio_guidance_unit.mjs

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  GUIDANCE_MODES,
  GUIDANCE_MECHANISMS,
  GUIDANCE_CONTROLLER_FOLDER,
  normalizeGuidanceMode,
  isSupportedGuidanceMode,
  shortHash,
  formatModelIdentity,
  listControllerCheckpoints,
  listPreprocessorCandidates,
  listLoaderCandidates,
  listApplyCandidates,
  discoverGuidanceAnchors,
  validateConditioning,
  buildMappingRecord,
  resolveGuidanceState,
  buildSnapshotGuidance,
  summarizeGuidanceProvenance,
} from "../web/studio-guidance.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const WEB_DIR = join(HERE, "..", "web");

const SHA_A = "aa".repeat(32);
const SHA_FUTURE = "ff".repeat(32);

const OBJECT_INFO = {
  SynthControlLoader: { input: { required: { control_net_name: ["STRING", {}] } } },
  SynthControlApply: {
    input: {
      required: {
        conditioning: ["CONDITIONING", {}],
        control_net: ["CONTROL_NET", {}],
        image: ["IMAGE", {}],
        strength: ["FLOAT", { default: 1.0 }],
      },
    },
  },
  SynthEdgePreprocessor: { input: { required: { image: ["IMAGE", {}] } } },
  SynthClipEncode: { input: { required: { text: ["STRING", {}] } } },
  SynthSampler: { input: { required: {} } },
};

function makeApiPrompt() {
  return {
    1: { class_type: "SynthModelLoader", inputs: { ckpt_name: "base.safetensors" } },
    2: {
      class_type: "SynthSampler",
      inputs: { model: ["1", 0], positive: ["3", 0], negative: ["4", 0] },
    },
    3: { class_type: "SynthClipEncode", inputs: { text: "a cat" } },
    4: { class_type: "SynthClipEncode", inputs: { text: "blurry" } },
    6: { class_type: "SynthLoadImage", inputs: {} },
  };
}

function confirmedMapping(sha) {
  return {
    record: {
      model_sha256: sha,
      mode: "canny",
      mechanism: "CONTROLNET_CONDITIONING",
      controller: { checkpoint: "guide-controller.safetensors", folder: "controlnet" },
      nodes: {
        loader: "SynthControlLoader",
        apply: "SynthControlApply",
        preprocessor: "SynthEdgePreprocessor",
      },
      conditioning: { strength: 0.7, start: 0.0, end: 0.8 },
      confirmed: true,
      audit: { mapping_revision: 1 },
    },
    stale: false,
  };
}

describe("guidance vocabulary", () => {
  it("supports exactly canny/depth/pose with one implemented mechanism", () => {
    assert.deepEqual([...GUIDANCE_MODES], ["canny", "depth", "pose"]);
    assert.deepEqual([...GUIDANCE_MECHANISMS], ["CONTROLNET_CONDITIONING"]);
    assert.equal(GUIDANCE_CONTROLLER_FOLDER, "controlnet");
    assert.equal(normalizeGuidanceMode("  Canny "), "canny");
    assert.equal(isSupportedGuidanceMode("depth"), true);
    assert.equal(isSupportedGuidanceMode("lineart"), false);
  });

  it("shows exact short-hash identity with filename as display-only context", () => {
    const id = formatModelIdentity({ sha: SHA_A, filename: "base.safetensors", folder: "diffusion_models" });
    assert.equal(id.shortHash, SHA_A.slice(0, 12));
    assert.equal(id.filename, "base.safetensors");
    assert.ok(id.label.includes(id.shortHash));
    assert.ok(id.label.includes("base.safetensors"));
  });
});

describe("guidance state machine", () => {
  it("is off and untouched when not engaged", () => {
    const st = resolveGuidanceState({ engaged: false, mode: "canny" });
    assert.equal(st.state, "off");
    assert.equal(st.ready, false);
    assert.equal(st.runGateReason, null);
    assert.equal(st.snapshot, null);
  });

  it("resolves with accepted copy while identity is unknown", () => {
    const st = resolveGuidanceState({ engaged: true, mode: "canny", identity: { status: "resolving" } });
    assert.equal(st.state, "resolving");
    assert.equal(st.headline, "Checking compatibility…");
    assert.equal(st.ready, false);
    assert.ok(st.runGateReason);
    assert.deepEqual(st.snapshot, { engaged: true, ready: false, reason: "identity_resolving" });
  });

  it("reports unknown_model with accepted copy when identity is unresolvable", () => {
    const st = resolveGuidanceState({
      engaged: true,
      mode: "canny",
      identity: { status: "unresolvable", filename: "ghost.safetensors" },
    });
    assert.equal(st.state, "unknown_model");
    assert.equal(st.headline, "Guidance unavailable for this model");
    assert.ok(st.detail.includes("will not guess from"));
    assert.ok(st.detail.includes("ghost.safetensors"));
    assert.deepEqual(st.actions.map((a) => a.id), ["choose_mapping", "cancel"]);
    assert.deepEqual(st.snapshot, { engaged: true, ready: false, reason: "identity_unresolvable" });
  });

  it("reports unknown_model when no mapping exists for the exact identity", () => {
    const st = resolveGuidanceState({
      engaged: true,
      mode: "depth",
      identity: { status: "resolved", sha: SHA_A, filename: "base.safetensors" },
      mapping: null,
    });
    assert.equal(st.state, "unknown_model");
    assert.equal(st.ready, false);
    assert.deepEqual(st.snapshot, { engaged: true, ready: false, reason: "no_confirmed_mapping" });
  });

  it("requires confirmation for unconfirmed mappings", () => {
    const st = resolveGuidanceState({
      engaged: true,
      mode: "canny",
      identity: { status: "resolved", sha: SHA_A, filename: "base.safetensors" },
      mapping: confirmedMapping(SHA_A),
      mappingUnconfirmed: true,
    });
    assert.equal(st.state, "known_unconfirmed");
    assert.equal(st.headline, "Guidance mapping needs confirmation");
    assert.deepEqual(st.actions.map((a) => a.id), ["confirm_mapping", "change"]);
    assert.equal(st.ready, false);
    assert.ok(st.runGateReason);
  });

  it("forces re-review on stale mappings, never silent replace", () => {
    const stale = confirmedMapping(SHA_A);
    stale.stale = true;
    stale.staleDetail = "controller checkpoint changed";
    const st = resolveGuidanceState({
      engaged: true,
      mode: "canny",
      identity: { status: "resolved", sha: SHA_A, filename: "base.safetensors" },
      mapping: stale,
    });
    assert.equal(st.state, "stale");
    assert.equal(st.headline, "Previously confirmed mapping needs review");
    assert.ok(st.detail.includes("will not replace"));
    assert.deepEqual(st.actions.map((a) => a.id), ["review_reconfirm", "keep_existing", "cancel"]);
    assert.equal(st.ready, false);
    assert.deepEqual(st.snapshot, { engaged: true, ready: false, reason: "stale_mapping" });
  });

  it("names the exact missing artifact in blocked_dependency", () => {
    const st = resolveGuidanceState({
      engaged: true,
      mode: "canny",
      identity: { status: "resolved", sha: SHA_A, filename: "base.safetensors" },
      mapping: confirmedMapping(SHA_A),
      missingDependencies: [{ kind: "checkpoint", name: "guide-controller.safetensors" }],
    });
    assert.equal(st.state, "blocked_dependency");
    assert.ok(st.headline.includes("guide-controller.safetensors"));
    assert.ok(st.runGateReason.includes("guide-controller.safetensors"));
    assert.deepEqual(st.snapshot, { engaged: true, ready: false, reason: "missing_dependency" });
  });

  it("refuses unsupported modes honestly", () => {
    const st = resolveGuidanceState({
      engaged: true,
      mode: "lineart",
      identity: { status: "resolved", sha: SHA_A, filename: "base.safetensors" },
    });
    assert.equal(st.state, "unsupported_mode");
    assert.ok(st.detail.includes("canny, depth, pose"));
    assert.deepEqual(st.snapshot, { engaged: true, ready: false, reason: "unsupported_mode" });
  });

  it("blocks incompatible workflows with the concrete refusal cause", () => {
    const st = resolveGuidanceState({
      engaged: true,
      mode: "canny",
      identity: { status: "resolved", sha: SHA_A, filename: "base.safetensors" },
      mapping: confirmedMapping(SHA_A),
      anchors: { ok: false, reason: "custom_sampler", detail: "no standard contract", candidates: [] },
    });
    assert.equal(st.state, "incompatible_workflow");
    assert.ok(st.runGateReason.includes("custom_sampler"));
    assert.deepEqual(st.snapshot, { engaged: true, ready: false, reason: "custom_sampler" });
  });

  it("offers a bounded anchor pick for multiple samplers", () => {
    const candidates = [
      { node_id: "2", class_type: "SynthSampler" },
      { node_id: "7", class_type: "SynthSampler" },
    ];
    const st = resolveGuidanceState({
      engaged: true,
      mode: "canny",
      identity: { status: "resolved", sha: SHA_A, filename: "base.safetensors" },
      mapping: confirmedMapping(SHA_A),
      anchors: { ok: false, reason: "multiple_samplers", detail: "two samplers", candidates },
    });
    assert.equal(st.state, "incompatible_workflow");
    assert.deepEqual(st.actions.map((a) => a.id), ["confirm_anchor", "cancel"]);
    assert.deepEqual(st.candidates, candidates);
    assert.equal(st.ready, false);
  });

  it("reaches ready only with confirmed mapping, anchors, and guide image", () => {
    const pending = resolveGuidanceState({
      engaged: true,
      mode: "canny",
      identity: { status: "resolved", sha: SHA_A, filename: "base.safetensors" },
      mapping: confirmedMapping(SHA_A),
      anchors: { ok: true, anchors: { sampler_id: "2" } },
      guideImage: "",
    });
    assert.equal(pending.state, "known_confirmed");
    assert.equal(pending.ready, false);
    assert.ok(pending.runGateReason);

    const st = resolveGuidanceState({
      engaged: true,
      mode: "canny",
      identity: { status: "resolved", sha: SHA_A, filename: "base.safetensors" },
      mapping: confirmedMapping(SHA_A),
      anchors: { ok: true, anchors: { sampler_id: "2" } },
      guideImage: "guide.png",
    });
    assert.equal(st.state, "ready");
    assert.equal(st.ready, true);
    assert.equal(st.runGateReason, null);
    assert.deepEqual(st.snapshot, { engaged: true, ready: true });
    assert.deepEqual(st.actions.map((a) => a.id), ["change", "reconfirm"]);
  });
});

describe("snapshot guidance key", () => {
  it("is null for plain runs and exact for engaged runs", () => {
    assert.equal(buildSnapshotGuidance(null), null);
    assert.equal(buildSnapshotGuidance({ engaged: false }), null);
    assert.deepEqual(buildSnapshotGuidance({ engaged: true, ready: true }), {
      engaged: true,
      ready: true,
    });
  });

  it("carries the engaged-but-blocked shape the backend gate consumes", () => {
    const key = buildSnapshotGuidance({ engaged: true, ready: false, reason: "no_confirmed_mapping" });
    assert.deepEqual(key, { engaged: true, ready: false, reason: "no_confirmed_mapping" });
    assert.deepEqual(Object.keys(key).sort(), ["engaged", "ready", "reason"]);
  });

  it("derives engaged-but-blocked from a full panel state", () => {
    const st = resolveGuidanceState({
      engaged: true,
      mode: "canny",
      identity: { status: "resolved", sha: SHA_A, filename: "base.safetensors" },
      mapping: null,
    });
    assert.deepEqual(buildSnapshotGuidance({ engaged: true, ready: st.ready, reason: st.snapshot.reason }), {
      engaged: true,
      ready: false,
      reason: "no_confirmed_mapping",
    });
  });
});

describe("manual mapping payload", () => {
  function manualInput() {
    return {
      model_sha256: SHA_FUTURE,
      mode: "depth",
      mechanism: "CONTROLNET_CONDITIONING",
      checkpoint: "future-controller.safetensors",
      loaderClass: "SynthControlLoader",
      applyClass: "SynthControlApply",
      preprocessorClass: "SynthEdgePreprocessor",
      strength: 0.6,
      start: 0.1,
      end: 0.9,
    };
  }

  it("builds a confirmable record for a synthetic unseen SHA", () => {
    const built = buildMappingRecord(manualInput());
    assert.equal(built.ok, true);
    assert.equal(built.record.model_sha256, SHA_FUTURE);
    assert.equal(built.record.mode, "depth");
    assert.equal(built.record.mechanism, "CONTROLNET_CONDITIONING");
    assert.equal(built.record.controller.checkpoint, "future-controller.safetensors");
    assert.equal(built.record.nodes.preprocessor, "SynthEdgePreprocessor");
    assert.deepEqual(built.record.conditioning, { strength: 0.6, start: 0.1, end: 0.9 });
    assert.equal(built.record.confirmed, true);
  });

  it("poisoned suggest/evidence/family fields do not alter the payload", () => {
    const clean = buildMappingRecord(manualInput());
    const poisoned = buildMappingRecord({
      ...manualInput(),
      suggest: { family: "POISON", display_filename: "poison.safetensors" },
      evidence: { workflow_url: "https://poison.invalid" },
      family: "poison-family",
      provider: "poison-provider",
      license: "POISON-LICENSE",
      source_url: "https://poison.invalid/x",
      workflow_id: "poison-workflow",
      display_filename: "poison.safetensors",
    });
    assert.equal(poisoned.ok, true);
    assert.deepEqual(poisoned.record, clean.record);
    const serialized = JSON.stringify(poisoned.record).toLowerCase();
    for (const token of ["poison", "suggest", "license", "source_url", "workflow_id", "provider", "family"]) {
      assert.ok(!serialized.includes(token), "payload leaks " + token);
    }
  });

  it("refuses unimplemented mechanisms and unsupported modes", () => {
    assert.equal(buildMappingRecord({ ...manualInput(), mechanism: "FUTURE_MECHANISM" }).ok, false);
    assert.equal(buildMappingRecord({ ...manualInput(), mode: "lineart" }).ok, false);
    assert.equal(buildMappingRecord({ ...manualInput(), checkpoint: "" }).ok, false);
  });
});

describe("structural anchor discovery", () => {
  it("discovers the single sampler anchor set", () => {
    const found = discoverGuidanceAnchors(makeApiPrompt());
    assert.equal(found.ok, true);
    assert.equal(found.anchors.sampler_id, "2");
    assert.deepEqual(found.anchors.positive, { node_id: "3", output: 0 });
    assert.deepEqual(found.anchors.negative, { node_id: "4", output: 0 });
    assert.equal(found.anchors.binding_id, "anchor:2");
  });

  it("asks with bounded candidates for multiple samplers", () => {
    const graph = makeApiPrompt();
    graph["7"] = JSON.parse(JSON.stringify(graph["2"]));
    const found = discoverGuidanceAnchors(graph);
    assert.equal(found.ok, false);
    assert.equal(found.reason, "multiple_samplers");
    assert.equal(found.candidates.length, 2);
  });

  it("refuses already-controlled graphs naming the node", () => {
    const graph = makeApiPrompt();
    graph["9"] = { class_type: "SynthControlNetApply", inputs: {} };
    const found = discoverGuidanceAnchors(graph);
    assert.equal(found.ok, false);
    assert.equal(found.reason, "already_controlled");
    assert.ok(found.detail.includes("9"));
  });

  it("refuses custom samplers and empty graphs", () => {
    const custom = {
      1: { class_type: "SynthCustomSampler", inputs: { model: ["9", 0], conditioning: ["8", 0] } },
      8: { class_type: "SynthClipEncode", inputs: {} },
      9: { class_type: "SynthModelLoader", inputs: {} },
    };
    assert.equal(discoverGuidanceAnchors(custom).reason, "custom_sampler");
    assert.equal(discoverGuidanceAnchors({}).reason, "no_sampler");
  });
});

describe("installed-artifact listings", () => {
  it("lists controlnet-folder checkpoints generically", () => {
    const records = [
      { folder: "controlnet", filename: "guide-a.safetensors", hash: "H1" },
      { folder: "diffusion_models", filename: "base.safetensors", hash: "H2" },
      { folder: "controlnet", filename: "guide-b.safetensors", hash: "" },
      null,
      "not-a-record",
    ];
    const listed = listControllerCheckpoints(records);
    assert.deepEqual(listed.map((r) => r.checkpoint), ["guide-a.safetensors", "guide-b.safetensors"]);
    assert.equal(listed[0].checkpoint_sha256, "H1");
  });

  it("lists preprocessor classes by IMAGE-slot shape only", () => {
    const listed = listPreprocessorCandidates(OBJECT_INFO);
    assert.ok(listed.includes("SynthEdgePreprocessor"));
    assert.ok(listed.includes("SynthControlApply"));
    assert.ok(!listed.includes("SynthClipEncode"));
    assert.ok(!listed.includes("SynthSampler"));
    assert.equal(listPreprocessorCandidates(null).length, 0);
  });

  it("lists loader and apply classes by structural slot contracts", () => {
    const loaders = listLoaderCandidates(OBJECT_INFO);
    assert.ok(loaders.includes("SynthControlLoader"));
    assert.ok(!loaders.includes("SynthSampler"));
    const applies = listApplyCandidates(OBJECT_INFO);
    assert.deepEqual(applies, ["SynthControlApply"]);
    assert.equal(listLoaderCandidates(null).length, 0);
    assert.equal(listApplyCandidates(null).length, 0);
  });
});

describe("guidance provenance projection", () => {
  it("renders generic fields and skips absent ones", () => {
    const rows = summarizeGuidanceProvenance({
      mode: "canny",
      model_sha256: SHA_A,
      mechanism: "CONTROLNET_CONDITIONING",
      controller_checkpoint: "guide-controller.safetensors",
      controller_checkpoint_sha256: "cc".repeat(32),
      preprocessor: "SynthEdgePreprocessor",
      mapping_revision: 2,
      anchor_binding_id: "anchor:2",
      sampler_id: "2",
      strength: 0.7,
      start: 0.0,
      end: 0.8,
    });
    const labels = rows.map((r) => r[0]);
    for (const want of ["Mode", "Model identity", "Mechanism", "Controller checkpoint", "Preprocessor", "Mapping revision", "Strength", "Start", "End"]) {
      assert.ok(labels.includes(want), "missing row " + want);
    }
    const model = rows.find((r) => r[0] === "Model identity");
    assert.equal(model[1], "sha256:" + SHA_A.slice(0, 12));
  });

  it("renders refusal causes and future strings as-is with no branches", () => {
    const rows = summarizeGuidanceProvenance({
      mode: "depth",
      model_sha256: SHA_FUTURE,
      mechanism: "SOME_FUTURE_MECHANISM",
      refusal_reason: "stale_anchor_binding",
      refusal_detail: "anchor gone after edit",
    });
    const byLabel = Object.fromEntries(rows);
    assert.equal(byLabel["Mechanism"], "SOME_FUTURE_MECHANISM");
    assert.equal(byLabel["Refusal reason"], "stale_anchor_binding");
    assert.equal(byLabel["Refusal detail"], "anchor gone after edit");
    assert.equal(summarizeGuidanceProvenance(null), null);
    assert.equal(summarizeGuidanceProvenance({}), null);
  });
});

describe("no model-family branches in production code", () => {
  const BANNED = ["qwen", "flux", "krea", "instantx", "shakker", "xlabs", "diffsynth", "bfl", "black.forest"];

  it("guidance-owned modules stay family-free; guidance lines in shared files too", () => {
    // Files owned by the guidance lane are scanned whole. Shared files
    // touched by this lane (playground, backend-api, history detail) are
    // scanned on guidance-path lines only: a pre-existing unrelated URL
    // elsewhere in those files must not fail this gate, but no guidance
    // line may branch on a model family or provider.
    const wholeFiles = [
      join(WEB_DIR, "studio-guidance.js"),
      join(HERE, "..", "studio_guidance.py"),
      join(HERE, "..", "studio_guidance_routes.py"),
    ];
    for (const path of wholeFiles) {
      const source = readFileSync(path, "utf-8").toLowerCase();
      for (const token of BANNED) {
        assert.ok(!source.includes(token), `${path} contains banned token ${token}`);
      }
    }
    const sharedFiles = [
      join(WEB_DIR, "studio-backend-api.js"),
      join(WEB_DIR, "studio-playground.js"),
      join(WEB_DIR, "studio-history-v2-detail.js"),
    ];
    for (const path of sharedFiles) {
      const lines = readFileSync(path, "utf-8").split("\n");
      lines.forEach((line, index) => {
        if (line.toLowerCase().includes("guidance")) {
          const lowered = line.toLowerCase();
          for (const token of BANNED) {
            assert.ok(!lowered.includes(token), `${path}:${index + 1} guidance line contains banned token ${token}`);
          }
        }
      });
    }
  });
});
