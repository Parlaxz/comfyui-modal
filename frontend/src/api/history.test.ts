import { describe, expect, it } from "vitest";
import { normalizeHistoryRecord } from "./history";

describe("History V2 normalization", () => {
  it("normalizes one Generation and its projected media outputs", () => {
    const item = normalizeHistoryRecord({
      generation_id: "gen_1",
      status: "completed",
      workflow_name: "Portrait",
      created_at: "2026-10-15T12:00:00Z",
      outputs: [{ asset_id: "asset_1", width: 512, height: 512, filename: "image.png" }],
    });
    expect(item.id).toBe("gen_1");
    expect(item.kind).toBe("generation");
    expect(item.featuredOutput?.originalUrl).toContain("asset_1");
    expect(item.workflow).toBe("Portrait");
  });

  it("distinguishes experiments without creating a second entity authority", () => {
    expect(normalizeHistoryRecord({ experiment_id: "exp_1", kind: "experiment" }).kind).toBe("experiment");
  });
});
