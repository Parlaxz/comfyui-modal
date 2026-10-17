// Ported Manager-model matching + wizard role catalog: pure-logic parity pins.
import { describe, expect, it } from "vitest";
import {
  buildManagerModelIndex,
  matchManagerModel,
  normalizeManagerSavePath,
} from "./manager";
import {
  optionalWizardRoles,
  requiredWizardRoles,
  wizardRoleDef,
  wizardRoleSuggestions,
} from "./workflows";

describe("buildManagerModelIndex / matchManagerModel", () => {
  const index = buildManagerModelIndex([
    { filename: "unet.safetensors", url: "https://example.com/u", save_path: "diffusion_models", type: "diffusion_model" },
    { filename: "sub/dir/lora.safetensors", url: "https://example.com/l", save_path: "default", type: "lora" },
  ]);

  it("matches exact filenames", () => {
    const hit = matchManagerModel({ filename: "unet.safetensors", role: "unet" }, index);
    expect(hit?.url).toBe("https://example.com/u");
  });

  it("matches path-like filenames by basename", () => {
    const hit = matchManagerModel({ filename: "sub/dir/lora.safetensors", role: "lora" }, index);
    expect(hit?.url).toBe("https://example.com/l");
  });

  it("rejects same-basename files of another type", () => {
    const hit = matchManagerModel({ filename: "other/path/unet.safetensors", role: "vae" }, index);
    expect(hit).toBeNull();
  });

  it("returns null without a catalog or filename", () => {
    expect(matchManagerModel({ filename: "x" }, null)).toBeNull();
    expect(matchManagerModel({}, index)).toBeNull();
  });

  it("normalizes default save paths through the type map, never emitting default", () => {
    expect(normalizeManagerSavePath("default", "lora")).toBe("loras");
    expect(normalizeManagerSavePath("custom/dir", "lora")).toBe("custom/dir");
    expect(normalizeManagerSavePath("", "unknown-type")).toBe("");
  });
});

describe("wizard role catalog", () => {
  it("requires the legacy t2i role set", () => {
    expect(requiredWizardRoles("t2i")).toEqual(["prompt", "seed", "model_unet", "vae", "clip"]);
  });

  it("requires source_image and mask for inpaint", () => {
    const required = requiredWizardRoles("inpaint");
    expect(required).toContain("source_image");
    expect(required).toContain("mask");
  });

  it("keeps sampler-family controls optional everywhere", () => {
    for (const type of ["t2i", "i2i", "inpaint", "sketch", "outpaint"]) {
      expect(optionalWizardRoles(type)).toEqual(
        expect.arrayContaining(["step_count", "cfg_scale", "sampler", "width", "height"]),
      );
    }
  });

  it("labels every required role and hints the common ones", () => {
    expect(wizardRoleDef("prompt").label).toBe("Prompt");
    expect(wizardRoleDef("model_unet").hint).toContain("UNETLoader");
    expect(wizardRoleSuggestions("seed")).toEqual([{ nodeType: "KSampler", widget: "seed" }]);
    expect(wizardRoleSuggestions("mask")).toEqual([]);
  });
});
