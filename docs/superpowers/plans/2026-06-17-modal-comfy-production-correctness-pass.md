# Modal-Comfy Production Correctness Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the remaining end-to-end runtime defects so experiments run correctly from ComfyUI UI through Modal execution, recovery, output materialization, and results display.

**Architecture:** Keep the existing experiment compiler/store/lease/runner foundations. Replace the local-only control path with a Modal-visible control plane, push resolved metadata through the checkpoint stream, make terminal-event persistence and asset registration authoritative, and wire the UI to exact journal and asset records.

**Tech Stack:** Python, aiohttp, SQLite, Modal, vanilla JS, unittest, Pillow

---

### Task 1: Remote control plane and checkpoint identity

**Files:**
- Modify: `experiment_runner.py`
- Modify: `modal_client.py`
- Modify: `comfyapp.py`
- Modify: `experiment_scheduler.py`
- Modify: `tests/test_experiment_runner.py`
- Modify: `tests/test_experiment_scheduler.py`

- [ ] Replace local temp-file control with a Modal-visible control backend keyed by deployment generation, experiment_id, checkpoint_id, worker_invocation_id, and lease_generation.
- [ ] Pass experiment_id, deployment generation, and revision through `run_checkpoint_stream` end-to-end.
- [ ] Add/update failing tests first for pause, stop-after-current, stop-now, per-worker separation, cross-experiment isolation, and control cleanup.
- [ ] Verify remote-side checks happen before checkpoint prep, before each cell, after each cell, before checkpoint completion, and on cancellation.

### Task 2: i2i payload contract and remote materialization

**Files:**
- Modify: `experiment_runner.py`
- Modify: `modal_client.py`
- Modify: `comfyapp.py`
- Modify: `tests/test_experiment_runner.py`
- Modify: `tests/test_integration_acceptance.py`

- [ ] Normalize to one canonical input-image field name shared by local and remote code.
- [ ] Build canonical payload with hash, filename, MIME, extension, encoded bytes, mapped node id, and mapped field.
- [ ] Inject remote filenames into workflows instead of local blob paths.
- [ ] Add/update failing tests first for missing blob, hash mismatch, MIME rejection, two i2i cells producing distinct remote files, and t2i cells skipping materialization.

### Task 3: Lease invalidation, recovery, persistence, and durable events

**Files:**
- Modify: `experiment_lease.py`
- Modify: `experiment_service.py`
- Modify: `experiment_scheduler.py`
- Modify: `experiment_runner.py`
- Modify: `__init__.py`
- Modify: `tests/test_experiment_lease.py`
- Modify: `tests/test_recovery_round_trip.py`
- Modify: `tests/test_experiment_scheduler.py`
- Modify: `tests/test_integration_acceptance.py`

- [ ] Make stop-now invalidate the lease atomically before cancellation.
- [ ] Make recovery release or supersede dead leases, bump generations, append validated interruptions once, and restore resumable scheduler status.
- [ ] Make scheduler persistence authoritative for start/pause/stop/resume/skip/unskip/rerun/run-missing/completion paths.
- [ ] Remove any remaining duplicate durable event path; EventBridge must be the only durable broadcaster.
- [ ] Add/update failing tests first for cancellation boundary acceptance/rejection, dead-lease reclaim, repeated recovery idempotence, persistence invariants, and EventBridge retry behavior.

### Task 4: Materialization, assets, primary output, and history metadata

**Files:**
- Modify: `__init__.py`
- Modify: `experiment_lease.py`
- Modify: `experiment_runner.py`
- Modify: `run_history.py`
- Modify: `comparison.py`
- Modify: `tests/test_run_history.py`
- Modify: `tests/test_modal_output_materialization.py`
- Modify: `tests/test_experiment_runner.py`

- [ ] Use globally unique asset IDs while preserving content hash as metadata.
- [ ] Make thumbnails first-class assets and keep materialization transactional with terminal success.
- [ ] Reuse deterministic primary-output selection rules from the ordinary result path.
- [ ] Propagate complete resolved cell metadata into remote terminal events and run history.
- [ ] Add/update failing tests first for identical bytes across attempts, thumbnail registration, decode/write failures becoming `cell.failed`, no base64 in journal payloads, and exact workflow hash/history metadata round-trip.

### Task 5: Compiler validation, profile association, warmup, and UI wiring

**Files:**
- Modify: `matrix_compiler.py`
- Modify: `comparison.py`
- Modify: `deploy_warmup.py`
- Modify: `__init__.py`
- Modify: `web/testing-setup.js`
- Modify: `web/testing-results.js`
- Modify: `web/testing-ab-slider.js`
- Modify: `web/testing-settings.js`
- Modify: `tests/test_matrix_compiler.py`
- Modify: `tests/test_comparison_extended_mappings.py`
- Modify: `tests/test_testing_setup_js.py`
- Modify: `tests/test_testing_results_js.py`
- Modify: `tests/test_deploy_warmup.py`

- [ ] Raise structured failures for invalid mappings and invalid LoRA strength lists before Modal execution.
- [ ] Preserve shared-negative / explicit-empty-negative semantics everywhere.
- [ ] Verify and enforce explicit profile workflow association instead of implicit fallback.
- [ ] Keep deployment state unwarmed until automatic warmup completes successfully.
- [ ] Finish UI wiring for multi-LoRA editors, per-worker progress cards, exact asset URLs, durable refresh, and fullscreen A/B.
- [ ] Add/update failing tests first for these behaviors.

### Task 6: Integrated local verification and real Modal verification

**Files:**
- Modify: `tests/test_integration_acceptance.py`
- Modify: `tests/test_testing_ui_wired.py`
- Modify: any targeted regression test modules needed by the above tasks

- [ ] Run the focused experiment suite locally after each task group and again at the end.
- [ ] Add end-to-end local tests that prove the corrected contracts rather than helper-only behavior.
- [ ] Deploy and run real Modal verification for one-checkpoint residency, two-checkpoint concurrency, pause, stop-after-current, stop-now, i2i, recovery, warmup, and results assets.
- [ ] Capture concrete evidence: deployment generation, experiment_id, checkpoint_id, worker_invocation_id, Modal call id, container session id, attempt_id, lease generation, control acknowledgements, and asset ids.
