# Headless Benchmark Harness Design

Date: 2026-06-02

## Goal

Replace the manual Modal benchmark loop with a simple headless Python script that:

- closes the previous local ComfyUI instance
- redeploys `comfyapp.py`
- relaunches local ComfyUI
- runs the currently loaded workflow twice
- waits `10s` after the first response before starting the second run
- saves both raw responses, traces, and summaries to a timestamped folder

The benchmark target is the **second run total** from the same deploy cycle.

## Non-Goals

This design does **not** include:

- a full autonomous optimizer
- any visible UI changes
- background graph polling on every edit
- workflow mutation or automatic prompt rewriting
- database/storage infrastructure
- any replacement for the existing local ComfyUI UX

## Constraints

- Keep the solution simple: one Python script plus tiny capture/storage helpers.
- No visible UI elements or workflow changes for the user.
- Negligible runtime overhead during normal ComfyUI usage.
- The benchmark workflow must come from the **currently loaded ComfyUI workflow**.
- The workflow capture must survive restart/redeploy.
- The script must not kill unrelated Python processes.

## Recommended Shape

Three small pieces:

1. **Silent workflow snapshot hook** in `web/modal-node.js`
2. **Tiny workflow snapshot routes** in `__init__.py`
3. **One standalone benchmark script** in the repo root

The script owns process cleanup, redeploy, health checks, benchmark execution, and artifact capture.

## Architecture

### 1. Silent Workflow Snapshot Hook

The frontend should capture the workflow on the **existing prompt submission path**, not by watching every graph edit.

Behavior:

- When the user runs a normal ComfyUI generation, intercept the outgoing prompt submission path already used by the node.
- Capture the **exact executable prompt payload** that ComfyUI is about to submit.
- POST that payload to a tiny backend snapshot route.

Why this trigger:

- avoids capturing half-edited workflows
- avoids noisy polling or debounce logic on graph changes
- guarantees the saved workflow is runnable
- keeps overhead close to zero because it only runs when the user already generates

Requirements:

- no buttons
- no banners
- no added visible controls
- no normal-console noise unless explicit debug mode is enabled later

### 2. Snapshot Storage Backend

Add a tiny route pair in `__init__.py`:

- `POST` route to save the latest workflow snapshot
- `GET` route to fetch the latest workflow snapshot

The snapshot should be stored in two places:

- in memory for quick retrieval while ComfyUI is alive
- on disk as a small JSON file so the snapshot survives restart/redeploy

The stored data should be the **executable prompt payload**, not just UI graph metadata.

Suggested persisted file:

- `latest_benchmark_workflow.json`

Suggested contents:

- prompt payload
- capture timestamp
- prompt hash
- optional lightweight metadata such as model stack summary if already available cheaply

### 3. Headless Benchmark Script

Add a standalone Python script, e.g.:

- `benchmark_modal.py`

This script should:

1. create a timestamped output directory
2. load the latest saved workflow snapshot
3. close existing local ComfyUI processes safely
4. run the existing redeploy batch file
5. wait for local ComfyUI health
6. submit run #1 headlessly
7. wait for completion
8. sleep `10s`
9. submit run #2
10. wait for completion
11. save raw responses, traces, summaries, and script logs

## Detailed Control Flow

### Output Directory

Each invocation creates a new folder, for example:

- `benchmark_runs/2026-06-02_14-37-11/`

This folder is append-only and never reused.

### Workflow Snapshot Load

At startup, the script loads the latest snapshot from disk or over the local helper route.

Failure rule:

- if no workflow snapshot exists, fail immediately with a clear message

The exact snapshot used for the run must be copied into the output folder as an artifact.

### Local ComfyUI Shutdown

Because `redeploy_modal_and_run_comfyui.bat` does not reliably close the old local instance, the Python script must handle shutdown itself.

Rules:

- identify only Python processes whose command line contains `ComfyUI\main.py`
- terminate gracefully first
- wait briefly
- force-kill only remaining matching processes
- do not kill unrelated Python processes

### Redeploy and Relaunch

After local shutdown:

- call `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI\redeploy_modal_and_run_comfyui.bat`
- wait for it to finish successfully
- then poll local ComfyUI health until ready

Health target:

- local ComfyUI HTTP endpoint on `127.0.0.1:8188`

Use a generous timeout because deploy/startup may take minutes.

### Run #1

The script submits the captured workflow through the local ComfyUI API.

It then:

- waits until the prompt completes
- saves the raw response
- extracts and saves trace/timing data

### Run #2

After run #1 completes:

- sleep `10s`
- submit the exact same workflow again
- wait until completion
- save the raw response
- extract and save trace/timing data

### Summary Generation

After both runs, write:

- `summary.json`
- `summary.md`
- `benchmark.log`

The summary should highlight:

- run 1 total
- run 2 total
- run 2 timing breakdown
- any obvious delta between run 1 and run 2

## Failure Behavior

Keep failure handling simple and explicit.

Possible terminal states:

- `deploy_failed`
- `health_timeout`
- `run1_failed`
- `run2_failed`
- `ok`

Rules:

- On deploy failure, stop immediately and save a failure summary.
- On health timeout, stop immediately and save a failure summary.
- On run 1 failure, stop immediately and save all available logs.
- On run 2 failure, keep run 1 artifacts and save a failure summary.
- Never delete prior benchmark folders.

## Files and Responsibilities

### `web/modal-node.js`

Responsibilities:

- intercept normal prompt submission path
- send the outgoing executable prompt payload to the backend snapshot route

Must not:

- add visible UI
- poll on every edit
- alter the workflow payload

### `__init__.py`

Responsibilities:

- accept and persist the latest workflow snapshot
- serve the latest workflow snapshot to local tools/scripts

Must not:

- take over benchmark execution
- add large background services

### `benchmark_modal.py`

Responsibilities:

- process cleanup
- redeploy invocation
- ComfyUI health polling
- two-run benchmark execution
- artifact capture
- summary generation

Must not:

- modify the captured workflow
- mutate repo files beyond benchmark output folders

## Artifact Format

Each run folder should contain at least:

- `workflow_snapshot.json`
- `run1_response.json`
- `run2_response.json`
- `run1_trace.json`
- `run2_trace.json`
- `summary.json`
- `summary.md`
- `benchmark.log`

Optional extra artifacts if cheap and useful:

- `run1_trace_line.txt`
- `run2_trace_line.txt`
- `environment.json`

## Testing Strategy

Add lightweight structural tests only.

Suggested tests:

1. snapshot route existence/behavior in `__init__.py`
2. snapshot persistence path is referenced
3. benchmark script references the expected batch file and output folder structure

Avoid deep tests for OS-specific process-kill details beyond basic safeguards.

## Performance and UX Guardrails

The helper must remain invisible and cheap.

Guardrails:

- no graph-edit polling
- no visible controls
- capture only on normal prompt submission
- no heavy serialization loops beyond the prompt already being sent
- no repeated disk writes except when the user actually runs a prompt

## Success Criteria

The design is successful when:

- the user can run one Python script to reproduce the manual two-run benchmark loop
- the script always benchmarks the currently loaded workflow that was last actually run in ComfyUI
- all benchmark outputs are saved to timestamped folders
- normal ComfyUI behavior, visuals, and responsiveness remain unchanged

## Out of Scope for This Design

These are intentionally deferred:

- approval-gated multi-iteration optimizer loop
- automatic code editing based on benchmark results
- git commit automation
- browser automation
- benchmark dashboard or UI viewer

Those can be layered on top later, but this design stops at reliable capture + headless two-run benchmarking.
