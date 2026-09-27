# Cold-Start Wall-Clock Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the benchmark harness bridge-faithful and accurate, then implement the remaining runtime cleanup changes and produce a final before/after cost-savings matrix for each proposed fix.

**Architecture:** First fix the benchmark harness so it mirrors the Modal bridge timing model and only accepts true cold runs. Then capture a baseline with the improved harness, land the one-pass custom-node sync and duplicate-reload cleanup, and finally rerun benchmarks plus generate a machine-readable and human-readable comparison matrix.

**Tech Stack:** Python 3.11, Modal, ComfyUI custom node runtime, unittest, JSON benchmark artifacts

---

## File Structure

- `_run_benchmark.py`
  - bridge-faithful benchmark harness
  - cold-run classification, output validation, summary, cost matrix generation
- `tests/test_run_benchmark.py`
  - unit tests for benchmark helpers and summary/matrix logic
- `custom_node_sync.py`
  - local pure helper for sync + optional one-pass state capture
- `tests/test_custom_node_sync.py`
  - unit tests for sync/state helper behavior
- `comfyapp.py`
  - Modal runtime lifecycle, inline sync helper, restore/run_prompt reload ownership
- `tests/test_comfyapp_volume_lifecycle.py`
  - AST/source guard rails for reload ownership rules
- `benchmark_logs/`
  - per-run artifacts plus final comparison/matrix summaries

### Task 1: Make `_run_benchmark.py` Bridge-Faithful and Testable

**Files:**
- Modify: `_run_benchmark.py`
- Test: `tests/test_run_benchmark.py`

- [ ] **Step 1: Add failing tests for bridge-style cold classification and output validation**

Add tests like these to `tests/test_run_benchmark.py`:

```python
class TestBridgeFaithfulValidation(unittest.TestCase):
    def test_classify_cold_run_rejects_missing_restore_markers(self):
        import importlib
        spec = importlib.util.spec_from_file_location("_run_benchmark", BENCHMARK_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        result = mod.classify_cold_run({}, {"stages": {"t3_modal_entry": 1.0}})

        self.assertEqual(result["validation_status"], "invalid_warm_reuse")
        self.assertFalse(result["is_valid_cold"])

    def test_classify_cold_run_accepts_restore_and_trace_markers(self):
        import importlib
        spec = importlib.util.spec_from_file_location("_run_benchmark", BENCHMARK_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        restore = {
            "restore_total_ms": 5000.0,
            "restore_start_unix_s": 10.0,
            "restore_end_unix_s": 15.0,
        }
        trace = {"stages": {"t3_modal_entry": 15.5}}

        result = mod.classify_cold_run(restore, trace)

        self.assertEqual(result["validation_status"], "valid_cold")
        self.assertTrue(result["is_valid_cold"])

    def test_validate_output_payload_rejects_blank_filename(self):
        import importlib
        spec = importlib.util.spec_from_file_location("_run_benchmark", BENCHMARK_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        result = mod.validate_output_payload({"images": [{"filename": "", "data": "abc"}], "videos": []})

        self.assertFalse(result["ok"])
        self.assertEqual(result["invalid_entries"], 1)
```

- [ ] **Step 2: Run the targeted tests to verify they fail first**

Run:

```powershell
pytest tests/test_run_benchmark.py::TestBridgeFaithfulValidation -v
```

Expected: FAIL because the helper names/behavior do not exist yet.

- [ ] **Step 3: Add bridge-faithful helper functions to `_run_benchmark.py`**

Add helpers shaped like:

```python
def build_bridge_trace(prompt_id: str = "") -> dict:
    now = time.time()
    return {
        "prompt_id": prompt_id,
        "t0_client_press": now,
        "t1_local_recv": now,
        "t2_local_dispatch": now,
    }


def classify_cold_run(restore: dict, trace: dict) -> dict:
    stages = trace.get("stages", {}) if isinstance(trace, dict) else {}
    has_restore_total = bool(restore.get("restore_total_ms"))
    has_restore_start = bool(restore.get("restore_start_unix_s"))
    has_restore_end = bool(restore.get("restore_end_unix_s"))
    has_t3 = bool(stages.get("t3_modal_entry"))
    is_valid_cold = bool(has_restore_total and has_restore_start and has_restore_end and has_t3)
    return {
        "is_valid_cold": is_valid_cold,
        "validation_status": "valid_cold" if is_valid_cold else "invalid_warm_reuse",
        "cold_classification": "cold" if is_valid_cold else "warm_or_unclear",
        "lifecycle_markers": {
            "has_restore_total_ms": has_restore_total,
            "has_restore_start": has_restore_start,
            "has_restore_end": has_restore_end,
            "has_t3_modal_entry": has_t3,
        },
    }


def validate_output_payload(result: dict, expected_count: int | None = None) -> dict:
    outputs = list(result.get("images", [])) + list(result.get("videos", []))
    invalid = [entry for entry in outputs if not entry.get("filename") or not entry.get("data")]
    output_bytes = sum(len(entry.get("data", "")) for entry in outputs)
    count_ok = expected_count is None or len(outputs) == expected_count
    return {
        "ok": count_ok and not invalid,
        "output_count": len(outputs),
        "output_bytes": output_bytes,
        "invalid_entries": len(invalid),
        "expected_count": expected_count,
    }
```

- [ ] **Step 4: Add failing tests for comparison summary, matrix rows, and mixed-clock labelling**

Add tests like:

```python
class TestBenchmarkSummaries(unittest.TestCase):
    def test_summarize_set_counts_only_valid_cold_runs(self):
        import importlib
        spec = importlib.util.spec_from_file_location("_run_benchmark", BENCHMARK_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        summary = mod.summarize_benchmark_set([
            {"validation_status": "valid_cold", "waterfall": {"benchmark_wall_ms": 1000.0}},
            {"validation_status": "invalid_warm_reuse", "waterfall": {"benchmark_wall_ms": 50.0}},
            {"validation_status": "valid_cold", "waterfall": {"benchmark_wall_ms": 900.0}},
        ])

        self.assertEqual(summary["valid_cold_runs"], 2)
        self.assertEqual(summary["median_wall_ms"], 1000.0)

    def test_build_matrix_row_contains_cost_fields(self):
        import importlib
        spec = importlib.util.spec_from_file_location("_run_benchmark", BENCHMARK_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        row = mod.build_matrix_row(
            "reload_cleanup",
            {"benchmark_set_id": "base", "median_wall_ms": 20000.0, "median_restore_ms": 12000.0, "median_prompt_ms": 7000.0, "spread_ms": 1000.0, "valid_cold_runs": 3},
            {"benchmark_set_id": "after", "median_wall_ms": 18000.0, "median_restore_ms": 10000.0, "median_prompt_ms": 7000.0, "spread_ms": 900.0, "valid_cold_runs": 3},
            gpu_hourly_cost=2.5,
        )

        self.assertIn("estimated_cost_per_cold_start_before", row)
        self.assertIn("estimated_savings_per_1000_cold_starts", row)

    def test_derived_mixed_clock_fields_are_marked_non_authoritative(self):
        import importlib
        spec = importlib.util.spec_from_file_location("_run_benchmark", BENCHMARK_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        derived = mod.label_derived_clock_fields({"platform_restore_ms": 123.0})

        self.assertEqual(derived["platform_restore_ms"]["authority"], "derived_mixed_clock")
```

- [ ] **Step 5: Run the new summary/matrix tests and verify RED**

Run:

```powershell
pytest tests/test_run_benchmark.py::TestBenchmarkSummaries -v
```

Expected: FAIL because these helpers/fields do not exist yet.

- [ ] **Step 6: Implement summary, matrix, and mixed-clock helper functions**

Add helpers shaped like:

```python
def summarize_benchmark_set(results: list[dict]) -> dict:
    valid = [r for r in results if r.get("validation_status") == "valid_cold" and not r.get("error")]
    walls = sorted(r.get("waterfall", {}).get("benchmark_wall_ms", 0.0) for r in valid if r.get("waterfall", {}).get("benchmark_wall_ms", 0.0) > 0)
    restores = sorted(r.get("restore_timing", {}).get("restore_total_ms", 0.0) for r in valid if r.get("restore_timing", {}).get("restore_total_ms", 0.0) > 0)
    prompts = sorted(r.get("trace", {}).get("deltas_ms", {}).get("t3b_to_t8", 0.0) for r in valid if r.get("trace", {}).get("deltas_ms", {}).get("t3b_to_t8", 0.0) > 0)
    if not walls:
        return {"valid_cold_runs": 0, "median_wall_ms": 0.0, "spread_ms": 0.0}
    mid = len(walls) // 2
    return {
        "benchmark_set_id": valid[0].get("benchmark_set_id") if valid else None,
        "valid_cold_runs": len(valid),
        "median_wall_ms": walls[mid],
        "median_restore_ms": restores[mid] if restores else 0.0,
        "median_prompt_ms": prompts[mid] if prompts else 0.0,
        "best_wall_ms": min(walls),
        "worst_wall_ms": max(walls),
        "spread_ms": max(walls) - min(walls),
    }


def label_derived_clock_fields(fields: dict) -> dict:
    return {key: {"value": value, "authority": "derived_mixed_clock"} for key, value in fields.items()}


def build_matrix_row(label: str, before: dict, after: dict, gpu_hourly_cost: float) -> dict:
    before_cost = (before.get("median_wall_ms", 0.0) / 1000.0 / 3600.0) * gpu_hourly_cost
    after_cost = (after.get("median_wall_ms", 0.0) / 1000.0 / 3600.0) * gpu_hourly_cost
    savings = before_cost - after_cost
    return {
        "label": label,
        "baseline_benchmark_set_id": before.get("benchmark_set_id"),
        "comparison_benchmark_set_id": after.get("benchmark_set_id"),
        "baseline_median_wall_ms": before.get("median_wall_ms", 0.0),
        "comparison_median_wall_ms": after.get("median_wall_ms", 0.0),
        "baseline_median_restore_ms": before.get("median_restore_ms", 0.0),
        "comparison_median_restore_ms": after.get("median_restore_ms", 0.0),
        "baseline_median_prompt_ms": before.get("median_prompt_ms", 0.0),
        "comparison_median_prompt_ms": after.get("median_prompt_ms", 0.0),
        "estimated_cost_per_cold_start_before": before_cost,
        "estimated_cost_per_cold_start_after": after_cost,
        "estimated_savings_per_cold_start": savings,
        "estimated_savings_per_100_cold_starts": savings * 100,
        "estimated_savings_per_1000_cold_starts": savings * 1000,
    }
```

- [ ] **Step 7: Refactor the benchmark call path to mirror the bridge path**

Update the benchmark loop so each attempt:

```python
        trace_seed = build_bridge_trace(prompt_id=label)
        request_submit_ts = time.time()
        result = None
        for msg in api.run_prompt_stream.remote_gen(workflow, input_images=input_images if input_images else None, trace=trace_seed):
            if not isinstance(msg, dict):
                continue
            if msg.get("type") == "result":
                result = msg.get("data")
                break
            if msg.get("type") == "error":
                raise RuntimeError(msg.get("message") or "run_prompt_stream error")
        output_complete_ts = time.time()
        if result is None:
            raise RuntimeError("run_prompt_stream ended without result")
```

Also ensure artifacts include:

```python
        cold_info = classify_cold_run(restore, trace)
        output_info = validate_output_payload(result, expected_output_count)
        derived_clock_fields = label_derived_clock_fields({
            "platform_restore_ms": platform_restore_ms,
            "modal_return_to_client_ms": modal_return_to_client_ms,
        })
```

- [ ] **Step 8: Run the benchmark helper test file and verify GREEN**

Run:

```powershell
pytest tests/test_run_benchmark.py -v
```

Expected: PASS for the new bridge-faithful helper and matrix tests.

### Task 2: Capture a Baseline with the Improved Harness Before Runtime Cleanup

**Files:**
- Modify: none
- Read: `_run_benchmark.py`, `latest_benchmark_workflow.json`
- Output: `benchmark_logs/*.json`

- [ ] **Step 1: Verify the benchmark workflow snapshot exists**

Run:

```powershell
python -c "from pathlib import Path; p=Path('latest_benchmark_workflow.json'); print(p.exists(), p.resolve())"
```

Expected: `True` and the absolute path to `latest_benchmark_workflow.json`.

- [ ] **Step 2: Run focused benchmark tests before baseline capture**

Run:

```powershell
pytest tests/test_run_benchmark.py -v
```

Expected: PASS.

- [ ] **Step 3: Deploy the current runtime code**

Run:

```powershell
python -m modal deploy comfyapp.py
```

Expected: successful deploy.

- [ ] **Step 4: Capture the baseline benchmark set with the improved harness**

Run:

```powershell
python _run_benchmark.py
```

Expected: artifacts are preserved for both valid and invalid attempts, and the run completes only after collecting 3 `valid_cold` runs.

- [ ] **Step 5: Record the baseline set identifier and summary artifact names**

Expected artifacts should include a set identifier plus per-run JSON files and a summary/matrix JSON file for the baseline set.

### Task 3: Make Custom-Node Sync Return State in One Pass

**Files:**
- Modify: `custom_node_sync.py`, `comfyapp.py`
- Test: `tests/test_custom_node_sync.py`

- [ ] **Step 1: Add a failing unit test for one-pass state capture**

Add this test to `tests/test_custom_node_sync.py` below `test_volume_state_changes_when_node_added`:

```python
    def test_sync_returns_state_when_requested(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            volume = root / "volume"
            comfy = root / "comfy"
            (volume / "NodeA").mkdir(parents=True)
            (volume / "NodeA" / "requirements.txt").write_text("pkg==1.0\n", encoding="utf-8")
            comfy.mkdir(parents=True)

            with mock.patch.object(module.os, "symlink"):
                result = module.sync_custom_nodes_into_comfy(str(volume), str(comfy), include_state=True)

            self.assertIn("state", result)
            self.assertEqual(result["state"], module.custom_node_volume_state(str(volume)))
```

- [ ] **Step 2: Run the targeted test to confirm RED**

Run:

```powershell
pytest tests/test_custom_node_sync.py::CustomNodeSyncTests::test_sync_returns_state_when_requested -v
```

Expected: FAIL with `TypeError` because `include_state` is not supported yet.

- [ ] **Step 3: Implement optional one-pass state capture in `custom_node_sync.py`**

Update the helper to:

```python
def sync_custom_nodes_into_comfy(volume_root: str, comfy_custom_nodes_root: str, include_state: bool = False) -> dict:
    volume_dirs = []
    state = []
    for name in _safe_listdir(volume_root):
        path = os.path.join(volume_root, name)
        if not os.path.isdir(path) or name in _EXCLUDED_DIRS:
            continue
        volume_dirs.append(name)
        if include_state:
            stat = os.stat(path)
            req_file = os.path.join(path, "requirements.txt")
            req_mtime_ns = os.stat(req_file).st_mtime_ns if os.path.isfile(req_file) else None
            state.append((name, stat.st_mtime_ns, req_mtime_ns))
```

and return `result["state"] = tuple(state)` when requested.

- [ ] **Step 4: Mirror the same helper shape in `comfyapp.py` and consume the returned state**

Update `_sync_custom_nodes_from_volume()` to:

```python
    def _sync_custom_nodes_from_volume(self):
        custom_nodes_vol.reload()
        comfy_custom_nodes = "/root/comfy/ComfyUI/custom_nodes"
        summary = sync_custom_nodes_into_comfy(CUSTOM_NODES_PATH, comfy_custom_nodes, include_state=True)
        state = summary.pop("state", custom_node_volume_state(CUSTOM_NODES_PATH))
        return summary, state
```

- [ ] **Step 5: Run the sync test file and verify GREEN**

Run:

```powershell
pytest tests/test_custom_node_sync.py -v
```

Expected: PASS.

### Task 4: Remove Redundant Outer `custom_nodes_vol.reload()` Calls

**Files:**
- Modify: `comfyapp.py`
- Test: `tests/test_comfyapp_volume_lifecycle.py`

- [ ] **Step 1: Replace the stale restore guard with reload-ownership tests**

Update `tests/test_comfyapp_volume_lifecycle.py` to add/keep assertions shaped like:

```python
def _count_direct_calls(method_body, obj_name: str, attr_name: str) -> int:
    return sum(
        1
        for node in ast.walk(method_body)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == obj_name
        and node.func.attr == attr_name
    )


class ComfyAppVolumeLifecycleTests(unittest.TestCase):
    def test_sync_helper_reloads_custom_node_volume_once(self):
        helper = _get_method("_sync_custom_nodes_from_volume")
        self.assertEqual(_count_direct_calls(helper, "custom_nodes_vol", "reload"), 1)

    def test_restore_and_run_prompt_do_not_directly_reload_custom_node_volume(self):
        restore = _get_method("restore")
        run_prompt = _get_method("run_prompt")
        self.assertEqual(_count_direct_calls(restore, "custom_nodes_vol", "reload"), 0)
        self.assertEqual(_count_direct_calls(run_prompt, "custom_nodes_vol", "reload"), 0)
```

- [ ] **Step 2: Run the targeted lifecycle test to confirm RED**

Run:

```powershell
pytest tests/test_comfyapp_volume_lifecycle.py::ComfyAppVolumeLifecycleTests::test_restore_and_run_prompt_do_not_directly_reload_custom_node_volume -v
```

Expected: FAIL because `restore()` and `run_prompt()` still call `custom_nodes_vol.reload()` directly.

- [ ] **Step 3: Remove the direct outer reloads from `restore()` and `run_prompt()`**

Apply these changes in `comfyapp.py`:

```python
        _s2 = time.time()
        _cn_summary, self._custom_nodes_state = self._sync_custom_nodes_from_volume()
```

and:

```python
        _cn_sync_start = time.time()
        _cn_summary, self._custom_nodes_state = self._sync_custom_nodes_from_volume()
```

Keep the single reload inside `_sync_custom_nodes_from_volume()`.

- [ ] **Step 4: Decide `resync_runtime()` reload ownership explicitly**

If `resync_runtime()` delegates through `_sync_custom_nodes_from_volume()`, do not add a second direct `custom_nodes_vol.reload()` there. If it does not, keep its behavior explicit and tested.

- [ ] **Step 5: Run the lifecycle test file and verify GREEN**

Run:

```powershell
pytest tests/test_comfyapp_volume_lifecycle.py -v
```

Expected: PASS.

### Task 5: Run Focused Verification, Re-Deploy, and Produce Final Matrix

**Files:**
- Modify: none unless a failing test forces code changes
- Test: `tests/test_custom_node_sync.py`, `tests/test_comfyapp_volume_lifecycle.py`, `tests/test_run_benchmark.py`, `tests/test_restore_timing_data_flow.py`
- Output: `benchmark_logs/*.json`, `benchmark_logs/*matrix*.json`

- [ ] **Step 1: Run the focused Python test suite**

Run:

```powershell
pytest tests/test_custom_node_sync.py tests/test_comfyapp_volume_lifecycle.py tests/test_run_benchmark.py tests/test_restore_timing_data_flow.py -v
```

Expected: PASS.

- [ ] **Step 2: Deploy the updated runtime code**

Run:

```powershell
python -m modal deploy comfyapp.py
```

Expected: successful deploy.

- [ ] **Step 3: Capture the post-cleanup benchmark set**

Run:

```powershell
python _run_benchmark.py
```

Expected: a second valid benchmark set with 3 `valid_cold` runs plus preserved invalid attempts.

- [ ] **Step 4: Generate the final before/after matrix**

The summary/matrix output must include at least one row for each proposed fix/config, including:

```text
- fix/config label
- baseline benchmark set ID
- comparison benchmark set ID
- baseline median wall clock
- comparison median wall clock
- wall-clock delta (ms and %)
- baseline/comparison restore_total_ms
- baseline/comparison prompt-side metric
- best/median/worst spread for both sets
- valid cold run counts
- benchmark validity judgment
- GPU hourly cost input
- cost per cold start before/after
- savings per cold start
- savings per 100 cold starts
- savings per 1000 cold starts
```

- [ ] **Step 5: Judge keep/reject using only authoritative metrics**

Use these as acceptance-driving metrics:

```text
- benchmark wall clock
- restore_total_ms
- remote_total
- t3b_to_t8
- inference deltas
- t8b_breakdown
```

Treat these as derived/non-authoritative only:

```text
- platform_restore_ms
- modal_return_to_client_ms
- any host-minus-container absolute timestamp field
```

- [ ] **Step 6: Update `working_optimizations.md` only if the result is a confirmed accepted win**

If accepted, append a new entry with exact measured values. If not accepted, skip the file update and preserve the rejection/blocking reason in the summary artifact.
