// runController — deterministic execution-safety contracts.
//
// Ports the accepted legacy semantics (web/studio-playground-run.js +
// studio-run-model.js) into cheap deterministic event sequences. No
// sleeps, no browser, no backend: ordering is proven by explicit calls.
import { describe, expect, it } from "vitest";
import { createRunController } from "./runController";

describe("runController identity", () => {
  it("allocates a fresh run identity per beginRun", () => {
    const controller = createRunController();
    const first = controller.beginRun();
    const second = controller.beginRun();
    expect(first).toBeTruthy();
    expect(second).toBeTruthy();
    expect(second).not.toBe(first);
    expect(controller.getRunId()).toBe(second);
  });

  it("resets terminal state on a new run (no cross-run leakage)", () => {
    const controller = createRunController();
    controller.beginRun();
    controller.attach();
    controller.handleWsEvent({ type: "execution_start", prompt_id: "p-1" });
    controller.handleWsEvent({ type: "execution_success", prompt_id: "p-1" });
    expect(controller.isTerminal()).toBe(true);
    controller.beginRun();
    expect(controller.isTerminal()).toBe(false);
    expect(controller.getStatus()).toBe("created");
  });
});

describe("runController terminal lock (cancel/terminal races)", () => {
  it("cancel then late success cannot resurrect the run", () => {
    const controller = createRunController();
    const runId = controller.beginRun();
    controller.cancel();
    expect(controller.getStatus()).toBe("canceled");
    const applied = controller.applyDirectResult({ status: "ok", direct_run: true }, runId);
    expect(applied).toBe("ignored");
    expect(controller.getStatus()).toBe("canceled");
    expect(controller.isTerminal()).toBe(true);
  });

  it("success then late progress cannot regress the run", () => {
    const controller = createRunController();
    const runId = controller.beginRun();
    controller.attach();
    controller.applyDirectResult({ status: "ok" }, runId);
    expect(controller.getStatus()).toBe("completed");
    expect(controller.handleWsEvent({ type: "progress" })).toBe(false);
    expect(controller.applySnapshot("running", { callerRunId: runId })).toBe(false);
    expect(controller.getStatus()).toBe("completed");
  });

  it("failure then late success cannot resurrect the run", () => {
    const controller = createRunController();
    const runId = controller.beginRun();
    controller.applyLocalError("boom");
    expect(controller.getStatus()).toBe("failed");
    expect(controller.applyDirectResult({ status: "ok" }, runId)).toBe("ignored");
    expect(controller.getStatus()).toBe("failed");
  });

  it("duplicate success settles once (first terminal wins)", () => {
    const controller = createRunController();
    const runId = controller.beginRun();
    expect(controller.applyDirectResult({ status: "ok" }, runId)).toBe("completed");
    expect(controller.applyDirectResult({ status: "ok" }, runId)).toBe("ignored");
    expect(controller.getStatus()).toBe("completed");
  });

  it("duplicate failure settles once", () => {
    const controller = createRunController();
    controller.beginRun();
    expect(controller.applyLocalError("first")).toBe(true);
    expect(controller.applyLocalError("second")).toBe(false);
    expect(controller.getFailureMessage()).toBe("first");
  });

  it("cancel after success cannot regress to canceled", () => {
    const controller = createRunController();
    const runId = controller.beginRun();
    controller.applyDirectResult({ status: "ok" }, runId);
    expect(controller.cancel()).toBe(false);
    expect(controller.getStatus()).toBe("completed");
  });
});

describe("runController stale/foreign rejection", () => {
  it("rejects foreign prompt terminal events", () => {
    const controller = createRunController();
    controller.beginRun();
    controller.attach();
    controller.handleWsEvent({ type: "execution_start", prompt_id: "p-ours" });
    expect(
      controller.handleWsEvent({ type: "execution_success", prompt_id: "p-foreign" }),
    ).toBe(false);
    expect(controller.isTerminal()).toBe(false);
    expect(
      controller.handleWsEvent({ type: "execution_success", prompt_id: "p-ours" }),
    ).toBe(true);
    expect(controller.getStatus()).toBe("completed");
  });

  it("rejects progress before execution-start (stale pre-lock stream)", () => {
    const controller = createRunController();
    controller.beginRun();
    controller.attach();
    expect(controller.handleWsEvent({ type: "progress" })).toBe(false);
    expect(controller.handleWsEvent({ type: "executing" })).toBe(false);
    expect(controller.getStatus()).toBe("created");
  });

  it("rejects terminal ws events arriving before execution-start", () => {
    const controller = createRunController();
    controller.beginRun();
    controller.attach();
    expect(
      controller.handleWsEvent({ type: "execution_success", prompt_id: "p-stale" }),
    ).toBe(false);
    expect(controller.isTerminal()).toBe(false);
  });

  it("ignores a second execution_start while the stream is locked", () => {
    const controller = createRunController();
    controller.beginRun();
    controller.attach();
    expect(controller.handleWsEvent({ type: "execution_start", prompt_id: "p-1" })).toBe(true);
    expect(controller.handleWsEvent({ type: "execution_start", prompt_id: "p-2" })).toBe(false);
    // The lock stays on the first execution: p-2's terminal is foreign.
    expect(controller.handleWsEvent({ type: "execution_success", prompt_id: "p-2" })).toBe(false);
    expect(controller.isTerminal()).toBe(false);
  });

  it("drops experiment events for single runs (no experiment identity)", () => {
    const controller = createRunController();
    controller.beginRun();
    controller.attach();
    controller.handleWsEvent({ type: "execution_start", prompt_id: "p-1" });
    expect(
      controller.handleWsEvent({ type: "experiment.worker.progress", experiment_id: "exp-9" }),
    ).toBe(false);
    expect(controller.isTerminal()).toBe(false);
  });

  it("routes experiment events only to the matching experiment", () => {
    const controller = createRunController();
    controller.beginRun();
    controller.attach();
    controller.setBackendIds({ experimentId: "exp-ours" });
    expect(
      controller.handleWsEvent({ type: "experiment.worker.progress", experiment_id: "exp-other" }),
    ).toBe(false);
    expect(controller.isTerminal()).toBe(false);
  });

  it("late prior-run direct results cannot hijack the new run", () => {
    const controller = createRunController();
    const oldRun = controller.beginRun();
    const newRun = controller.beginRun();
    expect(controller.applyDirectResult({ status: "ok" }, oldRun)).toBe("ignored");
    expect(controller.isTerminal()).toBe(false);
    expect(controller.applyDirectResult({ status: "ok" }, newRun)).toBe("completed");
    expect(controller.getStatus()).toBe("completed");
  });

  it("late prior-run snapshots cannot hijack the new run", () => {
    const controller = createRunController();
    const oldRun = controller.beginRun();
    controller.beginRun();
    expect(controller.applySnapshot("completed", { callerRunId: oldRun })).toBe(false);
    expect(controller.isTerminal()).toBe(false);
  });

  it("detached controllers reject events (navigation/dispose safety)", () => {
    const controller = createRunController();
    controller.beginRun();
    controller.attach();
    controller.detach();
    expect(controller.handleWsEvent({ type: "execution_start", prompt_id: "p-1" })).toBe(false);
    expect(controller.isTerminal()).toBe(false);
  });
});

describe("runController snapshot dedupe + result authority", () => {
  it("duplicate snapshot polls are no-ops", () => {
    const controller = createRunController();
    const runId = controller.beginRun();
    expect(controller.applySnapshot("running", { callerRunId: runId })).toBe(true);
    expect(controller.applySnapshot("running", { callerRunId: runId })).toBe(false);
    expect(controller.getStatus()).toBe("running");
  });

  it("duplicate terminal journal entries settle once", () => {
    const controller = createRunController();
    const runId = controller.beginRun();
    expect(
      controller.applySnapshot("completed", { callerRunId: runId, journalSignature: "j-1" }),
    ).toBe(true);
    expect(
      controller.applySnapshot("completed", { callerRunId: runId, journalSignature: "j-1" }),
    ).toBe(false);
  });

  it("direct POST result is terminal authority (failure preserves identity)", () => {
    const controller = createRunController();
    const runId = controller.beginRun();
    controller.applySubmissionAck();
    expect(controller.getStatus()).toBe("submitting");
    expect(controller.applyDirectResult({ status: "error", message: "GPU busy" }, runId)).toBe("failed");
    expect(controller.getStatus()).toBe("failed");
    expect(controller.getRunId()).toBe(runId);
    expect(controller.getFailureMessage()).toBe("GPU busy");
  });

  it("Golden progress is presentation-only and never completes a run", () => {
    const controller = createRunController();
    controller.beginRun();
    controller.noteGoldenProgress("stage 9/9");
    expect(controller.isTerminal()).toBe(false);
    expect(controller.getSnapshot().goldenNote).toBe("stage 9/9");
  });

  it("scheduler acceptance stays non-terminal (completion arrives later)", () => {
    const controller = createRunController();
    const runId = controller.beginRun();
    expect(controller.applyDirectResult({ status: "accepted", run_id: "backend-1" }, runId)).toBe(
      "accepted",
    );
    expect(controller.isTerminal()).toBe(false);
    expect(controller.getStatus()).toBe("running");
  });

  it("failure preserves the run identity for diagnostics", () => {
    const controller = createRunController();
    const runId = controller.beginRun();
    controller.applyLocalError("validation blew up");
    expect(controller.getRunId()).toBe(runId);
    expect(controller.isTerminal()).toBe(true);
  });
});
