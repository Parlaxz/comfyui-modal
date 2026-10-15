import { describe, expect, it } from "vitest";
import { buildWizardDraft, normalizeWorkflowType, parseWizardDraft } from "./workflows";

describe("workflow contracts", () => {
  it("normalizes feature types without provider branches", () => {
    expect(normalizeWorkflowType("txt2img")).toBe("t2i");
    expect(normalizeWorkflowType("inpaint")).toBe("inpaint");
  });

  it("bounds and rejects wizard drafts by schema/identity", () => {
    const draft = buildWizardDraft({ workflowId: "wf", versionId: "v1", step: "details" });
    expect(parseWizardDraft(JSON.stringify(draft), "wf", "v1")?.step).toBe("details");
    expect(parseWizardDraft(JSON.stringify(draft), "other", "v1")).toBeNull();
    expect(parseWizardDraft("{bad", "wf", "v1")).toBeNull();
    expect(parseWizardDraft("x".repeat(12001), "wf", "v1")).toBeNull();
  });
});
