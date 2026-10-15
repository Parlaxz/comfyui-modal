import { describe, expect, it } from "vitest";
import { configSchema } from "./settings";

describe("settings API boundary", () => {
  it("normalizes the real /config envelope while preserving unknown server fields", () => {
    const config = configSchema.parse({
      gpu: "rtx-pro-6000",
      available_gpus: [{ value: "rtx-pro-6000", label: "RTX PRO 6000" }],
      data_saver_default: "on",
      skip_plan_validation: true,
      future_server_field: "preserved",
    });
    expect(config.gpu).toBe("rtx-pro-6000");
    expect(config.data_saver_default).toBe("on");
    expect(config.future_server_field).toBe("preserved");
    expect(config.output_format).toBe("original");
  });

  it("rejects malformed durable/trust-boundary values", () => {
    expect(() => configSchema.parse({ available_gpus: [{ value: 1, label: "bad" }] })).toThrow();
    expect(() => configSchema.parse({ data_saver_default: "maybe" })).toThrow();
  });
});
