import { describe, expect, it } from "vitest";
import { normalizeDeployStatus, summarizeWorkspaces, isDeployUsable } from "./infrastructure";

describe("infrastructure API projections", () => {
  it("projects workspace server truth without duplicating credentials", () => {
    const summary = summarizeWorkspaces({
      status: "ok",
      active_workspace_id: "ws-b",
      workspaces: [
        { id: "ws-a", label: "A", token_secret: "must-not-project" },
        { id: "ws-b", label: "B", last_deploy_status: "ready" },
      ],
    });
    expect(summary.activeId).toBe("ws-b");
    expect(summary.rows[1]).toMatchObject({ id: "ws-b", isActive: true, lastDeployStatus: "ready" });
    expect(summary.rows[0]).not.toHaveProperty("token_secret");
  });

  it("normalizes deploy states and preserves usability semantics", () => {
    expect(normalizeDeployStatus({ state: "deployed_unwarmed", has_log: true })).toMatchObject({
      state: "deployed_unwarmed", hasLog: true, available: true,
    });
    expect(isDeployUsable("ready")).toBe(true);
    expect(isDeployUsable("deployed_unwarmed")).toBe(true);
    expect(isDeployUsable("failed")).toBe(false);
  });
});
