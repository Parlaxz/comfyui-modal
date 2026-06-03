# Headless Benchmark Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an invisible workflow snapshot helper plus a simple Python benchmark script that redeploys, runs the current workflow twice, and saves timestamped benchmark artifacts.

**Architecture:** `web/modal-node.js` silently posts the exact executable prompt payload to a tiny snapshot route in `__init__.py`. The latest workflow is kept in memory and on disk. `benchmark_modal.py` closes old local ComfyUI processes, runs the existing redeploy batch, waits for local health, submits two headless benchmark runs, polls for completion, and writes traces/responses/summaries to a timestamped folder.

**Tech Stack:** ComfyUI extension JavaScript, aiohttp routes in `__init__.py`, Python stdlib (`json`, `subprocess`, `urllib`, `pathlib`, `datetime`, `time`).

---

### Task 1: Add failing structural tests for snapshot routes and script wiring

**Files:**
- Modify: `tests/test_modal_runtime_routes.py`
- Create: `tests/test_benchmark_harness.py`

- [ ] **Step 1: Write the failing tests**

Add tests that assert:

```python
self.assertIn("/comfymodal/benchmark/workflow", routes)
self.assertIn("latest_benchmark_workflow.json", source)
self.assertIn("benchmark_modal.py", source_or_path)
self.assertIn("ComfyUI\\main.py", benchmark_source)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_modal_runtime_routes.py tests/test_benchmark_harness.py -q`

Expected: FAIL because the snapshot routes and script do not exist yet.

- [ ] **Step 3: Implement the minimal code to make them pass**

Add the route names, snapshot file path, and benchmark script file with the expected wiring.

- [ ] **Step 4: Run the same tests again**

Run: `python -m pytest tests/test_modal_runtime_routes.py tests/test_benchmark_harness.py -q`

Expected: PASS

### Task 2: Add workflow snapshot capture and persistence

**Files:**
- Modify: `web/modal-node.js`
- Modify: `__init__.py`
- Test: `tests/test_benchmark_harness.py`

- [ ] **Step 1: Write/extend failing tests for capture flow**

Assert the frontend still intercepts `/prompt`, posts the payload to `/comfymodal/benchmark/workflow`, and the backend persists `latest_benchmark_workflow.json`.

- [ ] **Step 2: Run tests to verify they fail for the new assertions**

Run: `python -m pytest tests/test_benchmark_harness.py -q`

Expected: FAIL until the new hook/persistence code exists.

- [ ] **Step 3: Implement minimal snapshot helpers**

Key shape:

```python
_LATEST_BENCHMARK_WORKFLOW_PATH = os.path.join(_NODE_DIR, "latest_benchmark_workflow.json")
_latest_benchmark_workflow: dict = {}
```

and routes:

```python
@_server.routes.post("/comfymodal/benchmark/workflow")
@_server.routes.get("/comfymodal/benchmark/workflow")
```

Frontend should clone the parsed `/prompt` body and post it without altering the outgoing prompt behavior.

- [ ] **Step 4: Run tests again**

Run: `python -m pytest tests/test_benchmark_harness.py tests/test_modal_runtime_routes.py -q`

Expected: PASS

### Task 3: Add the benchmark script and completion artifact flow

**Files:**
- Create: `benchmark_modal.py`
- Modify: `__init__.py`
- Test: `tests/test_benchmark_harness.py`

- [ ] **Step 1: Write/extend failing tests for benchmark script behavior**

Assert the script:

```python
self.assertIn("redeploy_modal_and_run_comfyui.bat", source)
self.assertIn("/comfymodal/benchmark/workflow", source)
self.assertIn("/comfymodal/prompt", source)
self.assertIn("/history/", source)
self.assertIn("benchmark_runs", source)
```

and the local server stores trace data with history metadata.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_benchmark_harness.py tests/test_modal_timing_trace.py -q`

Expected: FAIL because the script and history-trace wiring do not exist yet.

- [ ] **Step 3: Implement minimal benchmark flow**

The script should:

```python
# 1. load latest workflow snapshot
# 2. kill only matching ComfyUI main.py python processes
# 3. run the redeploy batch
# 4. wait for local health on 127.0.0.1:8188
# 5. POST workflow to /comfymodal/prompt
# 6. poll /history/{prompt_id}
# 7. save run1 artifacts
# 8. sleep 10s
# 9. repeat for run2
# 10. write summary.json, summary.md, benchmark.log
```

Update `__init__.py` so prompt completion stores trace metadata in history-accessible state for the script to read.

- [ ] **Step 4: Run targeted tests**

Run: `python -m pytest tests/test_benchmark_harness.py tests/test_modal_runtime_routes.py tests/test_modal_timing_trace.py -q`

Expected: PASS

### Task 4: Final verification

**Files:**
- Modify: `web/modal-node.js`
- Modify: `__init__.py`
- Create: `benchmark_modal.py`
- Modify/Create tests from prior tasks

- [ ] **Step 1: Run the focused benchmark-harness test set**

Run: `python -m pytest tests/test_benchmark_harness.py tests/test_modal_runtime_routes.py tests/test_modal_timing_trace.py -q`

Expected: PASS

- [ ] **Step 2: Run the broader test suite**

Run: `python -m pytest tests -q`

Expected: existing unrelated packaging failure may remain, but no new failures from this feature.
