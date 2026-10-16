// Manager pack resolution — focused unit tests.
// Proves CNR/aux/class/pattern identity order and the single-target
// install plan (CNR queue, explicit-repo git fallback, or none).
import { describe, expect, it } from "vitest";
import {
  buildManagerPackIndex,
  resolveManagerPack,
  resolveNodeInstall,
} from "./manager";

const packs = {
  donutnodes: { title: "ComfyUI-DonutNodes", version: "1.2.3", install_type: "cnr", repository: "https://github.com/DonutsDelivery/ComfyUI-DonutNodes" },
};
const mappings = { donutnodes: [["DonutLoaderClass"], {}] };

describe("resolveManagerPack", () => {
  it("resolves CNR identity first", () => {
    const index = buildManagerPackIndex(packs, mappings);
    expect(resolveManagerPack({ cnr_id: "donutnodes" }, index)?.name).toBe("ComfyUI-DonutNodes");
  });

  it("resolves aux repository slugs", () => {
    const index = buildManagerPackIndex(packs, {});
    expect(
      resolveManagerPack({ aux_id: "DonutsDelivery/ComfyUI-DonutNodes" }, index)?.name,
    ).toBe("ComfyUI-DonutNodes");
  });

  it("resolves exact classes", () => {
    const index = buildManagerPackIndex(packs, mappings);
    expect(resolveManagerPack({ classes: ["DonutLoaderClass"] }, index)?.name).toBe(
      "ComfyUI-DonutNodes",
    );
  });

  it("returns null without guessing when nothing matches", () => {
    const index = buildManagerPackIndex(packs, mappings);
    expect(resolveManagerPack({ name: "Unknown", classes: ["Nope"] }, index)).toBeNull();
  });
});

describe("resolveNodeInstall", () => {
  it("prefers the CNR queue for identified packs", () => {
    const index = buildManagerPackIndex(packs, mappings);
    const plan = resolveNodeInstall({ name: "ComfyUI-DonutNodes", cnr_id: "donutnodes" }, index);
    expect(plan.kind).toBe("cnr");
  });

  it("falls back to explicit repository URLs only", () => {
    const index = buildManagerPackIndex({}, {});
    const plan = resolveNodeInstall(
      { name: "X", repository_url: "https://github.com/ex/X" },
      index,
    );
    expect(plan).toEqual({ kind: "git", pack: null, url: "https://github.com/ex/X", name: "X" });
  });

  it("reports none rather than guessing", () => {
    const index = buildManagerPackIndex({}, {});
    expect(resolveNodeInstall({ name: "X" }, index).kind).toBe("none");
  });
});
