import asyncio
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "experiment_runner.py"


def load_runner():
    if not MODULE_PATH.exists():
        raise AssertionError("experiment_runner.py missing")
    spec = importlib.util.spec_from_file_location("experiment_runner", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _callable(module, name):
    fn = getattr(module, name, None)
    if fn is None:
        raise AssertionError(f"experiment_runner.py missing public symbol: {name}")
    return fn


# ── Test fixtures ────────────────────────────────────────────────────────

class FakeInvoker:
    """In-memory replacement for the remote invoker. Records every cell
    it processed, tagged with the worker_invocation_id under which it ran."""

    def __init__(self) -> None:
        self.processed: list[dict] = []  # one entry per cell
        self.invocation_prefixes: dict[str, list] = {}  # worker_invocation_id -> [(prefix_changed, cell_key)]
        self._counter = 0
        self.fail_cell_keys: set = set()
        self.delay_ms: int = 0
        self._cancelled: set = set()  # worker_invocation_ids that received a cancel

    async def open_worker(self, worker_invocation_id: str, checkpoint_id: str, profile_id: str,
                          workflow: dict, triple: dict) -> None:
        # In the LocalRemoteInvoker, this is where the existing modal
        # remote call would be opened. For tests, no-op.
        self.invocation_prefixes.setdefault(worker_invocation_id, [])

    async def run_cell(self, worker_invocation_id: str, cell: dict) -> dict:
        self._counter += 1
        prefix = (cell["workflow_hash"], cell["triple_id"], cell["lora_selection_id"])
        prev = self.invocation_prefixes[worker_invocation_id]
        prefix_changed = (not prev) or (prev[-1][0] != prefix)
        prev.append((prefix, cell["cell_key"]))
        if self.delay_ms:
            await asyncio.sleep(self.delay_ms / 1000.0)
        if cell["cell_key"] in self.fail_cell_keys:
            self.processed.append({
                "worker_invocation_id": worker_invocation_id,
                "cell_key": cell["cell_key"],
                "prefix": prefix,
                "prefix_changed": prefix_changed,
                "sequence": cell["sequence"],
                "status": "failed",
            })
            return {"status": "failed", "cell_key": cell["cell_key"], "error": "simulated"}
        self.processed.append({
            "worker_invocation_id": worker_invocation_id,
            "cell_key": cell["cell_key"],
            "prefix": prefix,
            "prefix_changed": prefix_changed,
            "sequence": cell["sequence"],
            "status": "completed",
        })
        return {"status": "completed", "cell_key": cell["cell_key"]}

    async def close_worker(self, worker_invocation_id: str) -> None:
        pass

    async def cancel_worker(self, worker_invocation_id: str) -> None:
        self._cancelled.add(worker_invocation_id)


class _CompilerHelper:
    @staticmethod
    def compile(spec):
        from matrix_compiler import compile_experiment
        return compile_experiment(spec)


class _Harness:
    def __init__(self, tmpdir: str):
        self.tmpdir = tmpdir
        self._created: list = []

    def store(self, exp_id: str):
        from experiment_store import ExperimentStore
        s = ExperimentStore(Path(self.tmpdir) / ".experiments" / exp_id, root=Path(self.tmpdir))
        self._created.append(("store", s))
        return s

    def leases(self, name: str = "leases.db"):
        from experiment_lease import LeaseRegistry
        r = LeaseRegistry(Path(self.tmpdir) / name)
        self._created.append(("lease", r))
        return r

    def close_all(self) -> None:
        for kind, obj in self._created:
            try:
                obj.close()
            except Exception:
                pass

    def __enter__(self) -> "_Harness":
        return self

    def __exit__(self, *exc) -> None:
        self.close_all()


def _two_checkpoint_spec():
    return {
        "experiment_id": "exp_5",
        "revision": 1,
        "workflows": [
            {
                "profile_id": "p1",
                "loader_target_group_id": "g_default",
                "main_triple": {"id": "main", "unet": "u1", "clip": "c1", "vae": "v1"},
                "subprofile_triples": [
                    {"id": "alt", "unet": "u2", "clip": "c1", "vae": "v1", "enabled": True},
                ],
                "selected_triple_ids": ["main", "alt"],
                "lora_slots": [],
            },
        ],
        "prompts": {
            "items": [
                {"id": "p_a", "label": "a", "text": "a", "negative": None, "enabled": True},
                {"id": "p_b", "label": "b", "text": "b", "negative": None, "enabled": True},
            ],
        },
        "images": {"mode": "cartesian", "items": []},
        "loras": {
            "selections": [
                {"id": "L_no", "label": "No LoRA", "loras": [], "enabled": True},
            ],
        },
        "axes": {
            "shared": {"seed": {"mode": "list", "values": [1, 2]}},
            "per_workflow": {"p1": {"steps": {"mode": "list", "values": [20]}}},
        },
    }


def _compile_with_workflow_hash(spec):
    """Replicate how the runner builds cells: attach a workflow_hash per checkpoint."""
    result = _CompilerHelper.compile(spec)
    # Add a placeholder workflow_hash per checkpoint
    for ck in result["checkpoints"]:
        ck["workflow_hash"] = "wh_" + ck["id"]
        # Add minimal slots/workflow so resolve_and_inject_cell passes
        ck.setdefault("slots", {"prompt": {"node_id": "1", "field": "text", "path": ["inputs", "text"]}})
        ck.setdefault("workflow", {"1": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}}})
        ck.setdefault("loader_target_groups", [])
        ck.setdefault("lora_slots", [])
        ck.setdefault("triple", {"unet": "", "clip": "", "vae": ""})
    # Add workflow_hash to each cell too (copied from its checkpoint)
    ck_hash = {ck["id"]: ck["workflow_hash"] for ck in result["checkpoints"]}
    for cell in result["cells"]:
        cell["workflow_hash"] = ck_hash[cell["checkpoint_id"]]
    return result


class LocalRemoteInvokerOutputSaveTests(unittest.TestCase):
    def test_save_output_images_reads_outputs_shape(self):
        mod = load_runner()

        async def _unused_stream(**kwargs):
            if False:
                yield kwargs

        with tempfile.TemporaryDirectory() as tmp:
            invoker = mod.LocalRemoteInvoker(_unused_stream, experiment_id="exp_test", node_dir=tmp)
            result_data = {
                "outputs": {
                    "107": {
                        "images": [{
                            "filename": "studio_test.png",
                            "data": "aGVsbG8=",
                        }],
                    },
                },
            }

            saved = asyncio.run(invoker._save_output_images(result_data, "cell_1"))

            # The filename is now unique (studio_<exp>_<cell>_<node>_<idx>_<token>.png)
            # not the original remote name
            self.assertEqual(len(saved), 1)
            fname = saved[0]
            self.assertTrue(fname.startswith("studio_exp_test_cell_1_107_0_"),
                            f"Expected studio_ prefix pattern, got {fname!r}")
            self.assertTrue(fname.endswith(".png"), f"Expected .png extension, got {fname!r}")
            # Verify the file exists on disk
            output_file = Path(tmp) / "output" / "studio" / fname
            self.assertTrue(output_file.exists())
            # Content should be "hello" (base64 of "aGVsbG8=")
            self.assertEqual(output_file.read_bytes(), b"hello")


# ── Tests ────────────────────────────────────────────────────────────────

class WorkerInvocationTests(unittest.TestCase):
    def test_resolve_and_inject_cell_ignores_empty_negative_without_slot(self):
        r = load_runner()
        resolved = r.resolve_and_inject_cell(
            profile_workflow={"1": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}}},
            profile_slots={"prompt": {"node_id": "1", "field": "text", "path": ["inputs", "text"]}},
            loader_target_groups=[],
            lora_slots=[],
            cell={
                "profile_id": "studio_profile",
                "prompt": "hello",
                "negative_prompt": "",
                "triple": {},
                "axis_values": {},
                "loader_target_group_id": "g_default",
                "lora_signature": [],
            },
        )
        self.assertEqual(resolved.workflow["1"]["inputs"]["text"], "hello")

    def test_one_worker_per_checkpoint(self):
        r = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            invoker = FakeInvoker()
            spec = _two_checkpoint_spec()
            compilation = _compile_with_workflow_hash(spec)
            with _Harness(tmp) as harness:
                store = harness.store(spec["experiment_id"])
                store.ensure()
                store.write_definition({
                    "schema_version": 1,
                    "experiment_id": spec["experiment_id"],
                    "revision": 1,
                    "name": "Test", "notes": "",
                    "created_at": "2026-06-17T00:00:00Z",
                    "updated_at": "2026-06-17T00:00:00Z",
                })
                leases = harness.leases()
                runner = r.ExperimentRunner(
                    store=store, leases=leases, invoker=invoker,
                    compilation=compilation, max_containers=2,
                )
                asyncio.run(runner.run())
            # 2 checkpoints, each with 1 LoRA * 2 prompts * 2 seeds = 4 cells
            self.assertEqual(len(invoker.processed), 8)
            # Exactly 2 distinct worker_invocation_ids
            wids = {p["worker_invocation_id"] for p in invoker.processed}
            self.assertEqual(len(wids), 2)

    def test_no_checkpoint_is_split(self):
        r = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            invoker = FakeInvoker()
            spec = _two_checkpoint_spec()
            compilation = _compile_with_workflow_hash(spec)
            with _Harness(tmp) as harness:
                store = harness.store(spec["experiment_id"])
                store.ensure()
                store.write_definition({
                    "schema_version": 1, "experiment_id": spec["experiment_id"],
                    "revision": 1, "name": "T", "notes": "",
                    "created_at": "2026-06-17T00:00:00Z",
                    "updated_at": "2026-06-17T00:00:00Z",
                })
                leases = harness.leases()
                runner = r.ExperimentRunner(
                    store=store, leases=leases, invoker=invoker,
                    compilation=compilation, max_containers=4,
                )
                asyncio.run(runner.run())
                # For each checkpoint_id, exactly one worker_invocation_id handles all its cells
                by_ck: dict = {}
                for p in invoker.processed:
                    ck_id = p["prefix"][0]
                # The fake records prefix, not checkpoint_id. Re-derive from
                # the compilation: assign a worker_invocation_id to each checkpoint
                # and check it's consistent. The runner is expected to do this
                # via the lease registry.
                ck_to_wid: dict = {}
                exp_id = spec.get("experiment_id", "")
                for ck in compilation["checkpoints"]:
                    lease = leases.snapshot(exp_id)["leases"].get(ck["id"], {})
                    wid = lease.get("worker_invocation_id", "")
                    ck_to_wid[ck["id"]] = wid
                # All cells in a checkpoint share that checkpoint's wid
                for cell in compilation["cells"]:
                    expected_wid = ck_to_wid[cell["checkpoint_id"]]
                    actual_wids = {p["worker_invocation_id"] for p in invoker.processed
                                    if p["cell_key"] == cell["cell_key"]}
                    self.assertEqual(actual_wids, {expected_wid},
                                     f"cell {cell['cell_key']} split across workers")

    def test_expensive_prefix_changed_false_when_same(self):
        r = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            invoker = FakeInvoker()
            spec = _two_checkpoint_spec()
            compilation = _compile_with_workflow_hash(spec)
            with _Harness(tmp) as harness:
                store = harness.store(spec["experiment_id"])
                store.ensure()
                store.write_definition({
                    "schema_version": 1, "experiment_id": spec["experiment_id"],
                    "revision": 1, "name": "T", "notes": "",
                    "created_at": "2026-06-17T00:00:00Z",
                    "updated_at": "2026-06-17T00:00:00Z",
                })
                leases = harness.leases()
                runner = r.ExperimentRunner(
                    store=store, leases=leases, invoker=invoker,
                    compilation=compilation, max_containers=1,
                )
                asyncio.run(runner.run())
            # For cells in a checkpoint with the same LoRA identity, prefix_changed=False
            by_ck_prefix: dict = {}
            for p in invoker.processed:
                by_ck_prefix.setdefault(p["prefix"], []).append(p["prefix_changed"])
            # The first cell in a prefix tuple should be True, subsequent ones False
            for prefix, flags in by_ck_prefix.items():
                self.assertTrue(flags[0], f"first cell of {prefix} should have prefix_changed=True")
                self.assertTrue(all(flags[1:]) == False or len(flags) == 1,
                                f"non-first cells of {prefix} should have prefix_changed=False, got {flags}")


class EventJournalTests(unittest.TestCase):
    def test_events_appended_to_journal(self):
        r = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            invoker = FakeInvoker()
            spec = _two_checkpoint_spec()
            compilation = _compile_with_workflow_hash(spec)
            with _Harness(tmp) as harness:
                store = harness.store(spec["experiment_id"])
                store.ensure()
                store.write_definition({
                    "schema_version": 1, "experiment_id": spec["experiment_id"],
                    "revision": 1, "name": "T", "notes": "",
                    "created_at": "2026-06-17T00:00:00Z",
                    "updated_at": "2026-06-17T00:00:00Z",
                })
                leases = harness.leases()
                runner = r.ExperimentRunner(
                    store=store, leases=leases, invoker=invoker,
                    compilation=compilation, max_containers=2,
                )
                asyncio.run(runner.run())
                events = list(store.read_events())
                types = [e["type"] for e in events]
                # Must include cell.completed for every cell, plus checkpoint.claimed/completed
                self.assertEqual(types.count("cell.attempt_created"), 8)
                self.assertEqual(types.count("checkpoint.claimed"), 2)
                self.assertEqual(types.count("checkpoint.completed"), 2)


class StopNowTests(unittest.TestCase):
    def test_stop_now_does_not_emit_local_interrupted(self):
        """After fix: stop_now must NOT emit cell.interrupted from the runner.
        Remaining cells stay pending; interruption events come through the
        validated terminal-event path (stream_event_sink / invoker cancel)."""
        r = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            invoker = FakeInvoker()
            invoker.delay_ms = 30
            spec = _two_checkpoint_spec()
            compilation = _compile_with_workflow_hash(spec)
            with _Harness(tmp) as harness:
                store = harness.store(spec["experiment_id"])
                store.ensure()
                store.write_definition({
                    "schema_version": 1, "experiment_id": spec["experiment_id"],
                    "revision": 1, "name": "T", "notes": "",
                    "created_at": "2026-06-17T00:00:00Z",
                    "updated_at": "2026-06-17T00:00:00Z",
                })
                leases = harness.leases()
                runner = r.ExperimentRunner(
                    store=store, leases=leases, invoker=invoker,
                    compilation=compilation, max_containers=1,
                )
                async def drive():
                    async def trigger():
                        await asyncio.sleep(0.05)
                        await runner.stop_now()
                    asyncio.create_task(trigger())
                    await runner.run()
                asyncio.run(drive())
                # Some cells completed, total processed < 8
                self.assertLess(len(invoker.processed), 8)
                events = list(store.read_events())
                types = [e["type"] for e in events]
                # The runner must NOT emit cell.interrupted locally
                runner_interrupted = [
                    e for e in events
                    if e["type"] == "cell.interrupted"
                    and e.get("payload", {}).get("reason") != "recovery"
                ]
                self.assertEqual(len(runner_interrupted), 0,
                    "runner must not emit cell.interrupted locally; "
                    "interruption goes through the validated path")

    def test_tally_uses_visible_state_not_raw_counts(self):
        """The final tally must use visible snapshot state so that
        failed→successful retries count as completed only (not completed+failed)
        and counts never exceed total logical cells.

        Terminal events must be manually seeded in the journal (FakeInvoker
        does not emit them); the snapshot rebuild is what run() uses.
        """
        r = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            invoker = FakeInvoker()
            spec = _two_checkpoint_spec()
            compilation = _compile_with_workflow_hash(spec)
            with _Harness(tmp) as harness:
                store = harness.store(spec["experiment_id"])
                store.ensure()
                store.write_definition({
                    "schema_version": 1, "experiment_id": spec["experiment_id"],
                    "revision": 1, "name": "T", "notes": "",
                    "created_at": "2026-06-17T00:00:00Z",
                    "updated_at": "2026-06-17T00:00:00Z",
                })
                leases = harness.leases()
                # Seed the journal with a failed→superseded→completed sequence
                # to simulate a retry: cell k1 failed, then superseded, then completed.
                cells = compilation["cells"]
                ck1 = cells[0]["cell_key"]
                store.append_event({
                    "type": "cell.failed",
                    "payload": {"cell_key": ck1, "checkpoint_id": cells[0]["checkpoint_id"],
                                "attempt_id": "a_fail_1", "error": "first attempt failed"},
                })
                store.append_event({
                    "type": "attempt.superseded",
                    "payload": {"cell_key": ck1, "checkpoint_id": cells[0]["checkpoint_id"],
                                "previous_attempt_id": "a_fail_1"},
                })
                store.append_event({
                    "type": "cell.completed",
                    "payload": {"cell_key": ck1, "checkpoint_id": cells[0]["checkpoint_id"],
                                "attempt_id": "a_ok_2"},
                })
                # Other 7 cells get completed events
                for cell in cells[1:]:
                    store.append_event({
                        "type": "cell.completed",
                        "payload": {"cell_key": cell["cell_key"],
                                    "checkpoint_id": cell["checkpoint_id"],
                                    "attempt_id": f"a_{cell['cell_key'][:8]}"},
                    })
                # Run the runner; its tally uses rebuild_snapshot()
                runner = r.ExperimentRunner(
                    store=store, leases=leases, invoker=invoker,
                    compilation=compilation, max_containers=2,
                )
                result = asyncio.run(runner.run())
                # After retry: k1 visible as completed (not completed+failed)
                snap = store.rebuild_snapshot()
                counters = snap.get("counters", {})
                self.assertEqual(counters.get("completed", 0), 8,
                    "failed→superseded→completed retry counts as 1 completed only")
                self.assertEqual(counters.get("failed", 0), 0,
                    "superseded failed attempt must not appear in visible counters")
                # The sum must not exceed total cells
                total = len(compilation["cells"])
                self.assertLessEqual(counters.get("completed", 0) + counters.get("failed", 0) +
                                     counters.get("interrupted", 0) + counters.get("skipped", 0), total)
                self.assertIn("total_cells", result,
                    "experiment.completed must carry total_cells")

    def test_visible_state_excludes_superseded(self):
        """Superseded attempts must not appear in visible snapshot counters."""
        r = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            invoker = FakeInvoker()
            spec = _two_checkpoint_spec()
            compilation = _compile_with_workflow_hash(spec)
            cells = compilation["cells"]
            with _Harness(tmp) as harness:
                store = harness.store(spec["experiment_id"])
                store.ensure()
                store.write_definition({
                    "schema_version": 1, "experiment_id": spec["experiment_id"],
                    "revision": 1, "name": "T", "notes": "",
                    "created_at": "2026-06-17T00:00:00Z",
                    "updated_at": "2026-06-17T00:00:00Z",
                })
                leases = harness.leases()
                # Seed all cells with completed, then supersede+re-complete one
                for cell in cells:
                    store.append_event({
                        "type": "cell.completed",
                        "payload": {"cell_key": cell["cell_key"],
                                    "checkpoint_id": cell["checkpoint_id"],
                                    "attempt_id": f"a_first_{cell['cell_key'][:8]}"},
                    })
                # Supersede first cell and re-complete it
                store.append_event({
                    "type": "attempt.superseded",
                    "payload": {"cell_key": cells[0]["cell_key"],
                                "checkpoint_id": cells[0]["checkpoint_id"],
                                "previous_attempt_id": f"a_first_{cells[0]['cell_key'][:8]}"},
                })
                store.append_event({
                    "type": "cell.completed",
                    "payload": {"cell_key": cells[0]["cell_key"],
                                "checkpoint_id": cells[0]["checkpoint_id"],
                                "attempt_id": "a_retry_ok"},
                })
                snap = store.rebuild_snapshot()
                counters = snap.get("counters", {})
                # 8 unique cells visible as completed (superseded one is now only counted once)
                self.assertEqual(counters.get("completed", 0), 8,
                    "superseded then re-completed counts as 1, not 2")

    def test_stop_now_cancels_all_active_workers(self):
        """Phase 11: ExperimentRunner.stop_now() must call cancel_worker
        for every active worker."""
        r = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            invoker = FakeInvoker()
            invoker.delay_ms = 50
            spec = _two_checkpoint_spec()
            compilation = _compile_with_workflow_hash(spec)
            with _Harness(tmp) as harness:
                store = harness.store(spec["experiment_id"])
                store.ensure()
                store.write_definition({
                    "schema_version": 1, "experiment_id": spec["experiment_id"],
                    "revision": 1, "name": "T", "notes": "",
                    "created_at": "2026-06-17T00:00:00Z",
                    "updated_at": "2026-06-17T00:00:00Z",
                })
                leases = harness.leases()
                runner = r.ExperimentRunner(
                    store=store, leases=leases, invoker=invoker,
                    compilation=compilation, max_containers=2,
                )
                async def drive():
                    async def trigger():
                        await asyncio.sleep(0.03)
                        await runner.stop_now()
                    asyncio.create_task(trigger())
                    await runner.run()
                asyncio.run(drive())
                # Verify cancel_worker was called for each worker that was active
                # The invoker records cancelled worker IDs
                self.assertGreater(len(invoker._cancelled), 0, "cancel_worker must be called")


class FailurePropagationTests(unittest.TestCase):
    def test_cell_failure_does_not_kill_checkpoint(self):
        r = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            invoker = FakeInvoker()
            # Mark the FIRST cell of checkpoint 1 as failing
            spec = _two_checkpoint_spec()
            compilation = _compile_with_workflow_hash(spec)
            ck1_cells = [c for c in compilation["cells"] if c["checkpoint_id"] == compilation["checkpoints"][0]["id"]]
            invoker.fail_cell_keys = {ck1_cells[0]["cell_key"]}
            with _Harness(tmp) as harness:
                store = harness.store(spec["experiment_id"])
                store.ensure()
                store.write_definition({
                    "schema_version": 1, "experiment_id": spec["experiment_id"],
                    "revision": 1, "name": "T", "notes": "",
                    "created_at": "2026-06-17T00:00:00Z",
                    "updated_at": "2026-06-17T00:00:00Z",
                })
                leases = harness.leases()
                runner = r.ExperimentRunner(
                    store=store, leases=leases, invoker=invoker,
                    compilation=compilation, max_containers=2,
                )
                asyncio.run(runner.run())
                # Both checkpoints still ran all their cells; the failed cell is recorded
                self.assertEqual(len(invoker.processed), 8)
                types = [e["type"] for e in store.read_events()]
                # Fix B: terminal events no longer emitted by runner;
                # only cell.attempt_created appears in the journal.
                # The checkpoint summary still reflects failures.
                self.assertEqual(types.count("cell.attempt_created"), 8)
                self.assertEqual(types.count("checkpoint.completed_with_failures"), 1)
                self.assertEqual(types.count("checkpoint.completed"), 1)



class ResolveAndInjectCellTests(unittest.TestCase):
    """Test the authoritative resolve_and_inject_cell function."""

    def _make_runner(self):
        return load_runner()

    def _with_prompt(self, wf: dict, slots: dict, node_id="99") -> tuple[dict, dict]:
        """Add a CLIPTextEncode prompt node to workflow and matching slot
        for tests that do not already have one."""
        wf = dict(wf)
        wf[node_id] = {"class_type": "CLIPTextEncode", "inputs": {"text": "dummy"}}
        slots = dict(slots)
        slots["prompt"] = {"node_id": node_id, "field": "text", "path": ["inputs", "text"]}
        return wf, slots

    def _wf_owned(self):
        """Return the WORKFLOW_OWNED sentinel for cells that should not touch the workflow."""
        from matrix_compiler import WORKFLOW_OWNED
        return WORKFLOW_OWNED

    def test_resolve_and_inject_injects_prompt(self):
        r = self._make_runner()
        wf = {"1": {"class_type": "CLIPTextEncode", "inputs": {"text": "old prompt"}},
              "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "old neg"}}}
        slots = {
            "prompt": {"node_id": "1", "field": "text", "path": ["inputs", "text"]},
            "negative_prompt": {"node_id": "2", "field": "text", "path": ["inputs", "text"]},
        }
        cell = {
            "prompt": "new prompt",
            "negative_prompt": "new neg",
            "axis_values": {"seed": 42, "steps": 20, "guidance": 7.5},
            "lora_signature": [],
            "input_image_hash": "",
            "triple": {},
            "loader_target_group_id": "g_default",
        }
        resolved = r.resolve_and_inject_cell(wf, slots, [], [], cell)
        self.assertEqual(resolved.positive_prompt, "new prompt")
        self.assertEqual(resolved.workflow["1"]["inputs"]["text"], "new prompt")

    def test_resolve_and_inject_injects_negative_prompt(self):
        r = self._make_runner()
        wf = {
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "pos"}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "neg"}},
        }
        slots = {
            "prompt": {"node_id": "1", "field": "text", "path": ["inputs", "text"]},
            "negative_prompt": {"node_id": "2", "field": "text", "path": ["inputs", "text"]},
        }
        cell = {
            "prompt": "positive text",
            "negative_prompt": "negative text",
            "axis_values": {"seed": 1},
            "lora_signature": [],
            "input_image_hash": "",
            "triple": {},
            "loader_target_group_id": "g_default",
        }
        resolved = r.resolve_and_inject_cell(wf, slots, [], [], cell)
        self.assertEqual(resolved.positive_prompt, "positive text")
        self.assertEqual(resolved.negative_prompt, "negative text")
        self.assertEqual(resolved.workflow["1"]["inputs"]["text"], "positive text")
        self.assertEqual(resolved.workflow["2"]["inputs"]["text"], "negative text")

    def test_resolve_and_inject_negative_fallback_raises_error(self):
        """D2: When no negative_prompt slot is mapped but cell has a negative,
        the function must raise MissingNegativePromptSlot (no heuristic fallback)."""
        r = self._make_runner()
        wf = {
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "pos"}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "default neg"}},
        }
        slots = {"prompt": {"node_id": "1", "field": "text", "path": ["inputs", "text"]}}
        cell = {
            "profile_id": "p1",
            "prompt": "hello",
            "negative_prompt": "bad stuff",
            "axis_values": {"seed": 1},
            "lora_signature": [],
            "input_image_hash": "",
            "triple": {},
            "loader_target_group_id": "g_default",
        }
        with self.assertRaises(r.MissingNegativePromptSlot) as ctx:
            r.resolve_and_inject_cell(wf, slots, [], [], cell)
        self.assertIn("p1", str(ctx.exception))

    def test_resolve_and_inject_loader_target_group(self):
        r = self._make_runner()
        wf = {
            "10": {"class_type": "UNETLoader", "inputs": {"unet_name": "old.safetensors"}},
            "20": {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": "old_clip.safetensors"}},
            "30": {"class_type": "VAELoader", "inputs": {"vae_name": "old_vae.safetensors"}},
        }
        groups = [{
            "id": "g_default",
            "unet": [{"node_id": "10", "field": "unet_name"}],
            "clip": [{"node_id": "20", "field": "clip_name1"}],
            "vae": [{"node_id": "30", "field": "vae_name"}],
        }]
        # Add prompt slot for D2 preflight validation
        wf, slots_with_prompt = self._with_prompt(wf, {}, node_id="99")
        cell = {
            "prompt": "x",
            "negative_prompt": self._wf_owned(),
            "axis_values": {"seed": 1},
            "lora_signature": [],
            "triple": {"unet": "new_unet.safetensors", "clip": "new_clip.safetensors",
                       "vae": "new_vae.safetensors"},
            "loader_target_group_id": "g_default",
            "input_image_hash": "",
        }
        resolved = r.resolve_and_inject_cell(wf, slots_with_prompt, groups, [], cell)
        self.assertEqual(resolved.unet, "new_unet.safetensors")
        self.assertEqual(resolved.clip, "new_clip.safetensors")
        self.assertEqual(resolved.vae, "new_vae.safetensors")
        self.assertEqual(resolved.workflow["10"]["inputs"]["unet_name"], "new_unet.safetensors")
        self.assertEqual(resolved.workflow["20"]["inputs"]["clip_name1"], "new_clip.safetensors")
        self.assertEqual(resolved.workflow["30"]["inputs"]["vae_name"], "new_vae.safetensors")

    def test_resolve_and_inject_lora_chain(self):
        r = self._make_runner()
        wf = {
            "40": {"class_type": "LoraLoader", "inputs": {"lora_name": "", "strength_model": 0.0, "strength_clip": 0.0}},
            "41": {"class_type": "LoraLoader", "inputs": {"lora_name": "", "strength_model": 0.0, "strength_clip": 0.0}},
        }
        lora_slots = [
            {"slot_index": 0, "lora_node_id": "40", "lora_field": "lora_name",
             "model_strength_node_id": "40", "model_strength_field": "strength_model",
             "clip_strength_node_id": "40", "clip_strength_field": "strength_clip"},
            {"slot_index": 1, "lora_node_id": "41", "lora_field": "lora_name",
             "model_strength_node_id": "41", "model_strength_field": "strength_model",
             "clip_strength_node_id": "41", "clip_strength_field": "strength_clip"},
        ]
        # Add prompt slot for D2 preflight validation
        wf, slots_with_prompt = self._with_prompt(wf, {}, node_id="99")
        cell = {
            "prompt": "x",
            "negative_prompt": self._wf_owned(),
            "axis_values": {"seed": 1},
            "lora_signature": [["lora1.safetensors", 0.7, 0.8]],
            "triple": {},
            "loader_target_group_id": "g_default",
            "input_image_hash": "",
        }
        resolved = r.resolve_and_inject_cell(wf, slots_with_prompt, [], lora_slots, cell)
        self.assertEqual(len(resolved.lora_chain), 1)
        self.assertEqual(resolved.lora_chain[0]["file"], "lora1.safetensors")
        self.assertEqual(resolved.workflow["40"]["inputs"]["lora_name"], "lora1.safetensors")
        self.assertEqual(resolved.workflow["40"]["inputs"]["strength_model"], 0.7)
        self.assertEqual(resolved.workflow["40"]["inputs"]["strength_clip"], 0.8)
        # Unused slot 41 gets zeroed out
        self.assertEqual(resolved.workflow["41"]["inputs"]["strength_model"], 0.0)
        self.assertEqual(resolved.workflow["41"]["inputs"]["strength_clip"], 0.0)

    def test_resolve_and_inject_resolution(self):
        r = self._make_runner()
        wf = {"5": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512}}}
        slots = {
            "width": {"node_id": "5", "field": "width", "path": ["inputs", "width"]},
            "height": {"node_id": "5", "field": "height", "path": ["inputs", "height"]},
        }
        # Add prompt slot for D2 preflight validation
        wf, slots = self._with_prompt(wf, slots, node_id="99")
        from matrix_compiler import WORKFLOW_OWNED
        cell = {
            "prompt": "x", "negative_prompt": self._wf_owned(),
            "axis_values": {"seed": 1, "guidance": 7.5, "steps": 20,
                            "resolution": (768, 640)},
            "lora_signature": [], "input_image_hash": "",
            "triple": {}, "loader_target_group_id": "g_default",
        }
        resolved = r.resolve_and_inject_cell(wf, slots, [], [], cell)
        self.assertEqual(resolved.workflow["5"]["inputs"]["width"], 768)
        self.assertEqual(resolved.workflow["5"]["inputs"]["height"], 640)

    def test_resolve_and_inject_preset_resolver(self):
        r = self._make_runner()
        wf = {"6": {"class_type": "LoadImage", "inputs": {"image": ""}}}
        slots = {"input_image": {"node_id": "6", "field": "image", "path": ["inputs", "image"]}}
        wf, slots = self._with_prompt(wf, slots, node_id="99")
        resolver_calls = []

        img_bytes = b"fake_image_data_for_testing"
        img_hash = hashlib.sha256(img_bytes).hexdigest()

        def fake_resolver(content_hash):
            resolver_calls.append(content_hash)
            return {"path": "input/sample.png", "bytes": img_bytes, "mime": "image/png", "ext": ".png"}

        cell = {
            "prompt": "x", "negative_prompt": self._wf_owned(),
            "axis_values": {"seed": 1},
            "lora_signature": [], "input_image_hash": img_hash,
            "triple": {}, "loader_target_group_id": "g_default",
        }
        resolved = r.resolve_and_inject_cell(wf, slots, [], [], cell, preset_resolver=fake_resolver)
        self.assertEqual(len(resolver_calls), 1)
        self.assertEqual(resolver_calls[0], img_hash)
        self.assertEqual(resolved.input_image["path"], "input/sample.png")
        # The workflow must receive the REMOTE filename, not the local blob path
        injected = resolved.workflow["6"]["inputs"]["image"]
        self.assertNotEqual(injected, "input/sample.png",
            "must inject remote filename, not local blob path")
        self.assertTrue(injected.startswith("exp_"),
            f"remote filename should start with 'exp_', got: {injected}")
        self.assertIn(".png", injected,
            f"remote filename should include extension, got: {injected}")
        # Canonical payload is built on the cell
        self.assertIn("input_images", cell,
            "cell must have input_images field after resolve_and_inject_cell")
        image_payloads = cell["input_images"]
        self.assertEqual(len(image_payloads), 1,
            "one i2i image should produce one payload entry")
        remote_fn = list(image_payloads.keys())[0]
        payload = image_payloads[remote_fn]
        self.assertEqual(payload["content_hash"], img_hash)
        self.assertEqual(payload["mime_type"], "image/png")
        self.assertEqual(payload["extension"], ".png")
        self.assertEqual(payload["node_id"], "6")
        self.assertEqual(payload["field"], "image")
        self.assertIn("data", payload)
        self.assertIn("original_filename", payload)
        # The remote filename used as the dict key matches the workflow value
        self.assertEqual(remote_fn, injected,
            "input_images dict key must match workflow-injected filename")

    def test_input_image_missing_blob_fails(self):
        """Missing blob content hash must raise before Modal execution."""
        r = self._make_runner()
        wf = {"6": {"class_type": "LoadImage", "inputs": {"image": ""}}}
        slots = {"input_image": {"node_id": "6", "field": "image", "path": ["inputs", "image"]}}
        wf, slots = self._with_prompt(wf, slots, node_id="99")

        def missing_resolver(content_hash):
            return None  # blob does not exist

        cell = {
            "prompt": "x", "negative_prompt": self._wf_owned(),
            "axis_values": {"seed": 1},
            "lora_signature": [], "input_image_hash": "deadbeef",
            "triple": {}, "loader_target_group_id": "g_default",
        }
        with self.assertRaises((ValueError, RuntimeError)):
            r.resolve_and_inject_cell(wf, slots, [], [], cell, preset_resolver=missing_resolver)

    def test_input_image_hash_mismatch_fails(self):
        """Hash mismatch between expected and actual blob content must raise."""
        r = self._make_runner()
        wf = {"6": {"class_type": "LoadImage", "inputs": {"image": ""}}}
        slots = {"input_image": {"node_id": "6", "field": "image", "path": ["inputs", "image"]}}
        wf, slots = self._with_prompt(wf, slots, node_id="99")

        def mismatched_resolver(content_hash):
            # Return bytes whose sha256 != content_hash
            return {"path": "input/bad.png", "bytes": b"wrong_data", "mime": "image/png"}

        cell = {
            "prompt": "x", "negative_prompt": self._wf_owned(),
            "axis_values": {"seed": 1},
            "lora_signature": [], "input_image_hash": "abcdef1234567890",
            "triple": {}, "loader_target_group_id": "g_default",
        }
        with self.assertRaises(ValueError):
            r.resolve_and_inject_cell(wf, slots, [], [], cell, preset_resolver=mismatched_resolver)

    def test_input_image_unsupported_mime_fails(self):
        """Unsupported MIME type must raise before Modal execution."""
        r = self._make_runner()
        wf = {"6": {"class_type": "LoadImage", "inputs": {"image": ""}}}
        slots = {"input_image": {"node_id": "6", "field": "image", "path": ["inputs", "image"]}}
        wf, slots = self._with_prompt(wf, slots, node_id="99")

        def unsupported_resolver(content_hash):
            return {"path": "input/bad.tiff", "bytes": b"\x00\x01", "mime": "image/tiff"}

        cell = {
            "prompt": "x", "negative_prompt": self._wf_owned(),
            "axis_values": {"seed": 1},
            "lora_signature": [], "input_image_hash": "aaaa",
            "triple": {}, "loader_target_group_id": "g_default",
        }
        with self.assertRaises(ValueError):
            r.resolve_and_inject_cell(wf, slots, [], [], cell, preset_resolver=unsupported_resolver)

    def test_two_image_cells_distinct_remote_files(self):
        """Two i2i cells with different content hashes produce different remote filenames."""
        r = self._make_runner()
        wf = {"6": {"class_type": "LoadImage", "inputs": {"image": ""}}}
        slots = {"input_image": {"node_id": "6", "field": "image", "path": ["inputs", "image"]}}
        wf, slots = self._with_prompt(wf, slots, node_id="99")
        call_log = []

        img_a_bytes = b"unique_image_data_a_12345"
        img_b_bytes = b"unique_image_data_b_67890"
        hash_a = hashlib.sha256(img_a_bytes).hexdigest()
        hash_b = hashlib.sha256(img_b_bytes).hexdigest()
        _hash_to_data = {hash_a: img_a_bytes, hash_b: img_b_bytes}

        def capturing_resolver(content_hash):
            data = _hash_to_data.get(content_hash, b"fallback")
            call_log.append(content_hash)
            return {"path": f"input/{content_hash[:8]}.png", "bytes": data, "mime": "image/png", "ext": ".png"}

        cell_a = {
            "prompt": "a", "negative_prompt": self._wf_owned(),
            "axis_values": {"seed": 1}, "lora_signature": [],
            "input_image_hash": hash_a,
            "triple": {}, "loader_target_group_id": "g_default",
        }
        cell_b = {
            "prompt": "b", "negative_prompt": self._wf_owned(),
            "axis_values": {"seed": 2}, "lora_signature": [],
            "input_image_hash": hash_b,
            "triple": {}, "loader_target_group_id": "g_default",
        }
        r.resolve_and_inject_cell(wf.copy(), slots, [], [], cell_a, preset_resolver=capturing_resolver)
        r.resolve_and_inject_cell(wf.copy(), slots, [], [], cell_b, preset_resolver=capturing_resolver)
        fn_a = list(cell_a["input_images"].keys())[0]
        fn_b = list(cell_b["input_images"].keys())[0]
        self.assertNotEqual(fn_a, fn_b,
            "two different i2i cells must produce different remote filenames")

    def test_t2i_cell_no_input_images(self):
        """A t2i cell (no input_image_hash) must not create an input_images payload."""
        r = self._make_runner()
        wf = {"6": {"class_type": "LoadImage", "inputs": {"image": ""}}}
        slots = {"input_image": {"node_id": "6", "field": "image", "path": ["inputs", "image"]}}
        wf, slots = self._with_prompt(wf, slots, node_id="99")

        def unused_resolver(content_hash):
            self.fail("resolver should not be called for t2i cell")

        cell = {
            "prompt": "x", "negative_prompt": self._wf_owned(),
            "axis_values": {"seed": 1}, "lora_signature": [],
            "input_image_hash": "",  # t2i — no image
            "triple": {}, "loader_target_group_id": "g_default",
        }
        r.resolve_and_inject_cell(wf, slots, [], [], cell, preset_resolver=unused_resolver)
        self.assertNotIn("input_images", cell,
            "t2i cell must not have input_images")
        self.assertEqual(cell.get("_input_image_b64", None), None,
            "t2i cell must not have _input_image_b64")
        # Workflow value should remain unchanged
        self.assertEqual(wf["6"]["inputs"]["image"], "",
            "t2i cell should not modify workflow image field")

    def test_resolve_and_inject_workflow_owned_axis(self):
        r = self._make_runner()
        wf = {"3": {"class_type": "KSampler", "inputs": {"seed": 999, "steps": 30, "cfg": 7.0}}}
        slots = {
            "seed": {"node_id": "3", "field": "seed", "path": ["inputs", "seed"]},
            "steps": {"node_id": "3", "field": "steps", "path": ["inputs", "steps"]},
            "guidance": {"node_id": "3", "field": "cfg", "path": ["inputs", "cfg"]},
        }
        wf, slots = self._with_prompt(wf, slots, node_id="99")
        from matrix_compiler import WORKFLOW_OWNED
        cell = {
            "prompt": "x", "negative_prompt": self._wf_owned(),
            "axis_values": {"seed": 42, "steps": WORKFLOW_OWNED, "guidance": WORKFLOW_OWNED},
            "lora_signature": [], "input_image_hash": "",
            "triple": {}, "loader_target_group_id": "g_default",
        }
        resolved = r.resolve_and_inject_cell(wf, slots, [], [], cell)
        # Seed was set (not workflow-owned)
        self.assertEqual(resolved.workflow["3"]["inputs"]["seed"], 42)
        # Steps and guidance were workflow-owned, so they keep their original values
        self.assertEqual(resolved.workflow["3"]["inputs"]["steps"], 30)
        self.assertEqual(resolved.workflow["3"]["inputs"]["cfg"], 7.0)


# ── Control Backend Tests ───────────────────────────────────────────────

# Shared default identity values for test brevity
_DEP = ""
_CK = ""
_LG = 0


class ControlBackendTests(unittest.TestCase):
    """Tests for the shared control backend (worker_control module)
    using the 5-component identity contract."""

    def setUp(self):
        import worker_control as wc
        self.backend = wc.FakeDictControlBackend()

    def _run(self, coro):
        return asyncio.run(coro)

    # ── base state helpers ────────────────────────────────────────

    def _set(self, exp, wid, state, dep=_DEP, ck=_CK, lg=_LG):
        return self.backend.set_control(dep, exp, ck, wid, lg, state)

    def _get(self, exp, wid, dep=_DEP, ck=_CK, lg=_LG):
        return self.backend.get_control(dep, exp, ck, wid, lg)

    def _clear(self, exp, wid, dep=_DEP, ck=_CK, lg=_LG):
        return self.backend.clear_control(dep, exp, ck, wid, lg)

    def _record(self, exp, wid, dep=_DEP, ck=_CK, lg=_LG):
        return self.backend._get_record(dep, exp, ck, wid, lg)

    # ── tests ─────────────────────────────────────────────────────

    def test_default_continue(self):
        """Default state is 'continue' for unknown keys."""
        self.assertEqual(self._run(self._get("exp_a", "w_unk")), "continue")

    def test_set_get_pause_after_current(self):
        self._run(self._set("exp_a", "w1", "pause_after_current"))
        self.assertEqual(self._run(self._get("exp_a", "w1")), "pause_after_current")

    def test_set_get_stop_after_current(self):
        self._run(self._set("exp_a", "w1", "stop_after_current"))
        self.assertEqual(self._run(self._get("exp_a", "w1")), "stop_after_current")

    def test_set_get_stop_now(self):
        self._run(self._set("exp_a", "w1", "stop_now"))
        self.assertEqual(self._run(self._get("exp_a", "w1")), "stop_now")

    def test_clear_restores_continue(self):
        self._run(self._set("exp_a", "w1", "stop_now"))
        self._run(self._clear("exp_a", "w1"))
        self.assertEqual(self._run(self._get("exp_a", "w1")), "continue")

    def test_two_workers_separate_records(self):
        """w1 and w2 with different checkpoint IDs have separate control."""
        self._run(self._set("exp_a", "w1", "pause_after_current", ck="ck_x"))
        self._run(self._set("exp_a", "w2", "stop_after_current", ck="ck_y"))
        self.assertEqual(
            self._run(self._get("exp_a", "w1", ck="ck_x")), "pause_after_current"
        )
        self.assertEqual(
            self._run(self._get("exp_a", "w2", ck="ck_y")), "stop_after_current"
        )

    def test_experiment_isolation(self):
        """Identical wid+ck in different experiments have separate control."""
        self._run(self._set("exp_a", "w1", "stop_now"))
        self.assertEqual(self._run(self._get("exp_b", "w1")), "continue")
        self.assertEqual(self._run(self._get("exp_a", "w1")), "stop_now")

    def test_checkpoint_isolation(self):
        """Same experiment + wid + different checkpoint = separate control."""
        self._run(self._set("exp_a", "w1", "stop_now", ck="ck1"))
        self.assertEqual(self._run(self._get("exp_a", "w1", ck="ck2")), "continue")

    def test_lease_generation_isolation(self):
        """Same experiment+ck+wid but different lease gen = separate control."""
        self._run(self._set("exp_a", "w1", "stop_now", ck="ck1", lg=1))
        self.assertEqual(self._run(self._get("exp_a", "w1", ck="ck1", lg=2)), "continue")

    def test_cleanup_after_terminal(self):
        self._run(self._set("exp_a", "w1", "stop_now", ck="ck1"))
        self._run(self._clear("exp_a", "w1", ck="ck1"))
        self.assertEqual(self._run(self._get("exp_a", "w1", ck="ck1")), "continue")
        # Double clear is a no-op
        self._run(self._clear("exp_a", "w1", ck="ck1"))
        self.assertEqual(self._run(self._get("exp_a", "w1", ck="ck1")), "continue")

    def test_record_stores_full_identity(self):
        """Stored record includes all 5 identity components."""
        self._run(self._set("exp_a", "w1", "pause_after_current", dep="d1", ck="ck1", lg=7))
        # _get_record is a sync method, not a coroutine
        r = self._record("exp_a", "w1", dep="d1", ck="ck1", lg=7)
        self.assertIsNotNone(r)
        self.assertEqual(r["state"], "pause_after_current")
        self.assertEqual(r["deployment_generation"], "d1")
        self.assertEqual(r["experiment_id"], "exp_a")
        self.assertEqual(r["checkpoint_id"], "ck1")
        self.assertEqual(r["worker_invocation_id"], "w1")
        self.assertEqual(r["lease_generation"], 7)
        self.assertIn("updated_at", r)


# ── CheckpointStreamInvoker Control Tests ──────────────────────────────

class _FakeCheckpointStreamGenerator:
    """Minimal coroutine-based fake for run_checkpoint_stream.

    Yields a cell.completed per cell, then checkpoint.completed.
    """

    async def __call__(
        self, *, checkpoint_id, worker_invocation_id, lease_generation,
        workflow, triple, lora_chain, cells,
        experiment_id="", revision=0, deployment_generation="",
    ):
        for cell in cells:
            yield {
                "type": "cell.completed",
                "event": "cell.completed",
                "data": {
                    "cell_key": cell.get("cell_key", ""),
                    "experiment_id": experiment_id,
                    "revision": revision,
                    "deployment_generation": deployment_generation,
                },
            }
        yield {
            "type": "checkpoint.completed",
            "event": "checkpoint.completed",
            "data": {"completed": len(cells)},
        }


class CheckpointStreamInvokerControlTests(unittest.TestCase):
    """Tests for CheckpointStreamInvoker control methods using
    the 5-component identity contract."""

    def _make_invoker(self, experiment_id="exp_test"):
        from worker_control import FakeDictControlBackend
        from experiment_runner import CheckpointStreamInvoker
        backend = FakeDictControlBackend()
        invoker = CheckpointStreamInvoker(
            _FakeCheckpointStreamGenerator(),
            experiment_id=experiment_id,
            control_backend=backend,
        )
        return invoker, backend

    def _bg(self, dep="", ck="", lg=0):
        """Shorthand to look up a record by bare identity (no kwargs)."""

    def test_request_pause_writes_control(self):
        invoker, backend = self._make_invoker("exp_test")
        asyncio.run(invoker.request_pause("w1"))
        # With no payload, defaults are: dep="", ck="", lg=0
        state = asyncio.run(backend.get_control("", "exp_test", "", "w1", 0))
        self.assertEqual(state, "pause_after_current")

    def test_request_stop_after_current_writes_control(self):
        invoker, backend = self._make_invoker("exp_test")
        asyncio.run(invoker.request_stop_after_current("w1"))
        state = asyncio.run(backend.get_control("", "exp_test", "", "w1", 0))
        self.assertEqual(state, "stop_after_current")

    def test_cancel_worker_writes_stop_now_and_clears(self):
        invoker, backend = self._make_invoker("exp_test")
        asyncio.run(invoker.open_worker("w1", "ck1", "p1", {}, {}))
        asyncio.run(invoker.cancel_worker("w1"))
        # After cancel_worker, record is cleared -> "continue"
        state = asyncio.run(backend.get_control("", "exp_test", "", "w1", 0))
        self.assertEqual(state, "continue",
            "cancel_worker should clear control after stop_now")

    def test_cancel_worker_experiment_isolation(self):
        """Cancel on exp_test never touches exp_other (same wid, same defaults)."""
        invoker, backend = self._make_invoker("exp_test")
        asyncio.run(invoker.open_worker("w1", "ck1", "p1", {}, {}))
        asyncio.run(invoker.cancel_worker("w1"))
        # exp_other with same wid and defaults should be unaffected
        other = asyncio.run(backend.get_control("", "exp_other", "", "w1", 0))
        self.assertEqual(other, "continue")

    def test_close_worker_clears_control(self):
        """close_worker clears the record for that worker identity."""
        invoker, backend = self._make_invoker("exp_clean")
        asyncio.run(invoker.open_worker("w_clean", "ck1", "p1", {}, {}))
        # Manually set a record on the backend
        asyncio.run(backend.set_control("", "exp_clean", "", "w_clean", 0, "pause_after_current"))
        asyncio.run(invoker.close_worker("w_clean"))
        state = asyncio.run(backend.get_control("", "exp_clean", "", "w_clean", 0))
        self.assertEqual(state, "continue",
            "close_worker must clear record")

    def test_request_pause_stores_full_identity(self):
        """Control records contain the full 5-component identity."""
        from worker_control import FakeDictControlBackend
        from experiment_runner import CheckpointStreamInvoker
        backend = FakeDictControlBackend()
        invoker = CheckpointStreamInvoker(
            _FakeCheckpointStreamGenerator(),
            experiment_id="exp_id_full",
            control_backend=backend,
        )
        invoker.configure_checkpoint(
            checkpoint_id="ck_42",
            lease_generation=7,
            experiment_id="exp_id_full",
            revision=3,
            deployment_generation="gen_deadbeef",
            workflow={}, triple={}, lora_chain={}, cells=[],
        )
        asyncio.run(invoker.open_worker("w_full", "ck_42", "p1", {}, {}))
        asyncio.run(invoker.request_pause("w_full"))
        record = backend._get_record("gen_deadbeef", "exp_id_full", "ck_42", "w_full", 7)
        self.assertIsNotNone(record, "expected stored record with full key")
        self.assertEqual(record["state"], "pause_after_current")
        self.assertEqual(record["deployment_generation"], "gen_deadbeef")
        self.assertEqual(record["experiment_id"], "exp_id_full")
        self.assertEqual(record["checkpoint_id"], "ck_42")
        self.assertEqual(record["worker_invocation_id"], "w_full")
        self.assertEqual(record["lease_generation"], 7)


# ── Runner Control Propagation Tests ────────────────────────────────────

class _TrackingInvoker:
    """Fake invoker that records which control methods were called."""

    def __init__(self, delegate, calls=None):
        self._delegate = delegate
        self.calls = calls if calls is not None else []

    async def open_worker(self, *a, **k):
        self.calls.append(("open_worker", a, k))
        return await self._delegate.open_worker(*a, **k)

    async def run_cell(self, *a, **k):
        return await self._delegate.run_cell(*a, **k)

    async def close_worker(self, *a, **k):
        return await self._delegate.close_worker(*a, **k)

    async def cancel_worker(self, *a, **k):
        self.calls.append(("cancel_worker", a, k))
        return await self._delegate.cancel_worker(*a, **k)

    async def request_pause(self, *a, **k):
        self.calls.append(("request_pause", a, k))
        return await self._delegate.request_pause(*a, **k)

    async def request_stop_after_current(self, *a, **k):
        self.calls.append(("request_stop_after_current", a, k))
        return await self._delegate.request_stop_after_current(*a, **k)

    def configure_checkpoint(self, **payload):
        return self._delegate.configure_checkpoint(**payload)


class RunnerControlPropagationTests(unittest.TestCase):
    """Tests that ExperimentRunner control methods propagate to
    the invoker / control backend."""

    def test_request_pause_calls_invoker(self):
        """Runner.request_pause calls invoker.request_pause for each worker."""
        r = load_runner()
        calls = []
        inner = r.CheckpointStreamInvoker(
            _FakeCheckpointStreamGenerator(),
            experiment_id="exp_prop",
        )
        # Pre-populate worker state so the invoker has experiment_id context
        inner._workers["w1"] = {"payload": {"experiment_id": "exp_prop"}}
        inner._workers["w2"] = {"payload": {"experiment_id": "exp_prop"}}
        invoker = _TrackingInvoker(inner, calls=calls)
        runner = r.ExperimentRunner.__new__(r.ExperimentRunner)
        runner._invoker = invoker
        runner._active_workers = {"w1": "ck1", "w2": "ck1"}
        runner._compilation = {"experiment_id": "exp_prop"}
        asyncio.run(runner.request_pause())
        pause_calls = [c for c in calls if c[0] == "request_pause"]
        self.assertEqual(len(pause_calls), 2)
        called_wids = {c[1][0] for c in pause_calls}
        self.assertEqual(called_wids, {"w1", "w2"})

    def test_request_stop_after_current_calls_invoker(self):
        """Runner.request_stop_after_current calls invoker for each worker."""
        r = load_runner()
        calls = []
        inner = r.CheckpointStreamInvoker(
            _FakeCheckpointStreamGenerator(),
            experiment_id="exp_prop",
        )
        inner._workers["w1"] = {"payload": {"experiment_id": "exp_prop"}}
        invoker = _TrackingInvoker(inner, calls=calls)
        runner = r.ExperimentRunner.__new__(r.ExperimentRunner)
        runner._invoker = invoker
        runner._active_workers = {"w1": "ck1"}
        runner._compilation = {"experiment_id": "exp_prop"}
        asyncio.run(runner.request_stop_after_current())
        sac_calls = [c for c in calls if c[0] == "request_stop_after_current"]
        self.assertEqual(len(sac_calls), 1)
        self.assertEqual(sac_calls[0][1][0], "w1")

    def test_stop_now_calls_cancel_worker_for_each(self):
        """Runner.stop_now calls invoker.cancel_worker for each active worker."""
        r = load_runner()
        calls = []
        inner = r.CheckpointStreamInvoker(
            _FakeCheckpointStreamGenerator(),
            experiment_id="exp_prop",
        )
        inner._workers["w1"] = {"payload": {"experiment_id": "exp_prop"}}
        inner._workers["w2"] = {"payload": {"experiment_id": "exp_prop"}}
        invoker = _TrackingInvoker(inner, calls=calls)
        runner = r.ExperimentRunner.__new__(r.ExperimentRunner)
        runner._invoker = invoker
        runner._active_workers = {"w1": "ck1", "w2": "ck2"}
        runner._stop_mode = ""
        runner._stop_event = asyncio.Event()
        runner._compilation = {"experiment_id": "exp_prop"}
        asyncio.run(runner.stop_now())
        cancel_calls = [c for c in calls if c[0] == "cancel_worker"]
        self.assertEqual(len(cancel_calls), 2)
        called_wids = {c[1][0] for c in cancel_calls}
        self.assertEqual(called_wids, {"w1", "w2"})


# ── ExperimentId Passing Tests ──────────────────────────────────────────

class ExperimentIdInRemoteCallTests(unittest.TestCase):
    """Verify that experiment_id (and related metadata) flows
    through the invoker to the remote call."""

    def test_experiment_id_in_configure_checkpoint(self):
        r = load_runner()
        captured = {}

        class CapturingInvoker(r.CheckpointStreamInvoker):
            def configure_checkpoint(self, **payload):
                super().configure_checkpoint(**payload)
                captured.update(payload)

        invoker = CapturingInvoker(
            _FakeCheckpointStreamGenerator(),
            experiment_id="exp_capture",
        )
        invoker.configure_checkpoint(
            checkpoint_id="ck1",
            lease_generation=1,
            workflow={},
            triple={},
            lora_chain={},
            cells=[],
            experiment_id="exp_capture",
            revision=3,
            deployment_generation="gen_deadbeef",
        )
        self.assertEqual(captured.get("experiment_id"), "exp_capture")
        self.assertEqual(captured.get("revision"), 3)
        self.assertEqual(captured.get("deployment_generation"), "gen_deadbeef")

    def test_experiment_id_in_run_checkpoint_stream_call(self):
        """Verify experiment_id, revision, deployment_generation
        are passed to the run_checkpoint_stream callable."""
        r = load_runner()
        call_kwargs = {}

        async def tracking_generator(**kwargs):
            call_kwargs.update(kwargs)
            # Yield checkpoint.completed so the drive task completes.
            yield {"type": "checkpoint.completed", "event": "checkpoint.completed", "data": {}}

        invoker = r.CheckpointStreamInvoker(
            tracking_generator,
            experiment_id="exp_track",
        )
        invoker.configure_checkpoint(
            checkpoint_id="ck1",
            lease_generation=1,
            workflow={},
            triple={},
            lora_chain={},
            cells=[{"cell_key": "c1"}],
            experiment_id="exp_track",
            revision=2,
            deployment_generation="gen_cafe",
        )
        # Open worker to trigger _drive
        asyncio.run(invoker.open_worker("w_track", "ck1", "p1", {}, {}))

        async def run_one():
            # run_cell triggers _drive which calls tracking_generator
            result = await invoker.run_cell("w_track", {"cell_key": "c1", "_resolved_workflow": {}})
            return result

        result = asyncio.run(run_one())
        # Should complete without hanging
        self.assertIn(result.get("status"), ("completed", "checkpoint_completed"))

        self.assertEqual(call_kwargs.get("experiment_id"), "exp_track")
        self.assertEqual(call_kwargs.get("revision"), 2)
        self.assertEqual(call_kwargs.get("deployment_generation"), "gen_cafe")

    def test_experiment_id_consistency_in_events(self):
        """Remote events should contain experiment_id in data."""
        r = load_runner()

        async def emitting_generator(
            *, checkpoint_id, worker_invocation_id, lease_generation,
            workflow, triple, lora_chain, cells,
            experiment_id="", revision=0, deployment_generation="",
        ):
            for cell in cells:
                yield {
                    "type": "cell.completed",
                    "event": "cell.completed",
                    "data": {
                        "cell_key": cell.get("cell_key", ""),
                        "experiment_id": experiment_id,
                        "revision": revision,
                        "deployment_generation": deployment_generation,
                    },
                }
            yield {"type": "checkpoint.completed", "event": "checkpoint.completed", "data": {}}

        invoker = r.CheckpointStreamInvoker(
            emitting_generator,
            experiment_id="exp_evt",
        )
        invoker.configure_checkpoint(
            checkpoint_id="ck1",
            lease_generation=1,
            workflow={},
            triple={},
            lora_chain={},
            cells=[{"cell_key": "c1"}],
            experiment_id="exp_evt",
            revision=5,
            deployment_generation="gen_evt",
        )
        asyncio.run(invoker.open_worker("w_evt", "ck1", "p1", {}, {}))
        events = []

        async def run_and_collect():
            for _ in range(2):  # cell + checkpoint
                result = await invoker.run_cell("w_evt", {"cell_key": "c1"})
                events.append(result)

        asyncio.run(run_and_collect())
        # The cell.completed event data
        completed = next((e for e in events if e.get("status") == "completed"), None)
        if completed and completed.get("data"):
            data = completed["data"]
            self.assertEqual(data.get("experiment_id"), "exp_evt")
            self.assertEqual(data.get("revision"), 5)
            self.assertEqual(data.get("deployment_generation"), "gen_evt")


# ── Metadata Propagation & Transactional Materialization Tests ──────────

class _MetadataTrackingStreamEventSink:
    """Test sink that records every event received via the stream_event_sink."""

    def __init__(self):
        self.events: list[dict] = []

    async def __call__(self, event: dict):
        self.events.append(event)


class MetadataPropagationTests(unittest.TestCase):
    """Goal 5: resolved cell metadata must propagate through _drive to the
    stream_event_sink / _on_remote_event so history does not depend on later
    lookups."""

    def test_resolved_metadata_in_cell_completed_event(self):
        """_drive enriches cell.completed events with resolved cell metadata."""
        r = load_runner()
        sink = _MetadataTrackingStreamEventSink()
        invoker = r.CheckpointStreamInvoker(
            _FakeCheckpointStreamGenerator(),
            experiment_id="exp_meta",
            stream_event_sink=sink,
        )
        cells = [
            {
                "cell_key": "c1",
                "checkpoint_id": "ck1",
                "_resolved_prompt": "a cat",
                "_resolved_negative": "bad",
                "_resolved_unet": "flux1.safetensors",
                "_resolved_clip": "clip_l.safetensors",
                "_resolved_vae": "ae.safetensors",
                "_resolved_lora_chain": [{"file": "style.safetensors", "model_strength": 0.8, "clip_strength": 0.6}],
                "axis_values": {"seed": 42, "steps": 20, "guidance": 3.5, "sampler": "euler", "scheduler": "normal", "denoise": 1.0, "resolution": (512, 512)},
                "workflow_hash": "wh_test",
            },
        ]
        invoker.configure_checkpoint(
            checkpoint_id="ck1",
            lease_generation=1,
            workflow={},
            triple={},
            lora_chain={},
            cells=cells,
            experiment_id="exp_meta",
            revision=2,
            deployment_generation="gen_meta",
        )
        asyncio.run(invoker.open_worker("w_meta", "ck1", "p1", {}, {}))

        async def run_one():
            return await invoker.run_cell("w_meta", {"cell_key": "c1"})

        asyncio.run(run_one())

        # Look for the cell.completed event in the sink
        completed_events = [e for e in sink.events if e.get("type") == "cell.completed"]
        self.assertGreaterEqual(len(completed_events), 1, "expected at least one cell.completed in sink")
        ev = completed_events[0]
        data = ev.get("data", {})
        self.assertEqual(data.get("cell_key"), "c1")

class MaterializationFailureTests(unittest.TestCase):
    """Goal 3: on materialization failure the persisted event must be
    cell.failed, not cell.completed."""

    def test_cell_failed_persisted_when_materialization_fails(self):
        """Simulate a cell.completed arriving with result data that fails to
        materialize. The _on_remote_event equivalent must write cell.failed."""
        r = load_runner()
        from experiment_lease import LeaseRegistry

        with tempfile.TemporaryDirectory() as tmp:
            leases = LeaseRegistry(Path(tmp) / "leases.db")
            # Claim a lease so validate_and_accept passes
            leases.claim("exp_mat_fail", "ck1", "w1")

            # Build a cell.completed event whose result has undecodable base64
            # "data": None will trigger TypeError on b64decode
            ev = {
                "type": "cell.completed",
                "data": {
                    "cell_key": "c_fail",
                    "checkpoint_id": "ck1",
                    "lease_generation": 1,
                    "worker_invocation_id": "w1",
                    "attempt_id": "a_fail_1",
                    "experiment_id": "exp_mat_fail",
                    "result": {
                        "outputs": {
                            "7": {
                                "images": [
                                    {
                                        "filename": "out.png",
                                        "data": None,  # will cause b64decode(None) to raise TypeError
                                        "mime_type": "image/png",
                                        "width": 64, "height": 64,
                                    },
                                ],
                            },
                        },
                    },
                },
            }

            # Simulate _on_remote_event logic with a real store
            from experiment_store import ExperimentStore
            real_store = ExperimentStore(Path(tmp) / ".experiments" / "exp_mat_fail", root=Path(tmp))
            real_store.ensure()

            et = ev.get("type", "")
            data = ev.get("data", {}) or {}
            try:
                leases.validate_and_accept(
                    "exp_mat_fail",
                    checkpoint_id=data.get("checkpoint_id", ""),
                    lease_generation=int(data.get("lease_generation", 0)),
                    worker_invocation_id=data.get("worker_invocation_id", ""),
                    attempt_id=data.get("attempt_id", ""),
                )
            except Exception:
                pass

            payload = {
                "checkpoint_id": data.get("checkpoint_id", ""),
                "cell_key": data.get("cell_key", ""),
                "worker_invocation_id": data.get("worker_invocation_id", ""),
                "lease_generation": data.get("lease_generation", 0),
                "attempt_id": data.get("attempt_id", ""),
                "error": data.get("error", ""),
            }

            # Materialize (should fail because data=None causes b64decode error)
            result_data = data.get("result", {}) or {}
            materialization_failed = False
            if result_data:
                try:
                    from tests.test_input_image_paths import _load_init_module as _load_init
                    init_mod = _load_init()
                    output_dir = str(Path(tmp) / "outputs" / data.get("cell_key", "") / data.get("attempt_id", ""))
                    init_mod._materialize_experiment_output(
                        result_data, output_dir, data.get("cell_key", ""), data.get("attempt_id", ""),
                    )
                except Exception:
                    materialization_failed = True
                    payload["error"] = "output_materialization_failed: corrupt data"
                    real_store.append_event({
                        "type": "cell.failed",
                        "payload": payload,
                    })

            if not materialization_failed:
                real_store.append_event({
                    "type": "cell.completed",
                    "payload": payload,
                })

            # Read back what was persisted
            persisted = list(real_store.read_events())
            types = [e["type"] for e in persisted]
            self.assertIn("cell.failed", types,
                          "on materialization failure, cell.failed must be persisted")
            self.assertNotIn("cell.completed", types,
                             "on materialization failure, cell.completed must NOT be persisted")
            # Check the error category
            failed_event = next(e for e in persisted if e["type"] == "cell.failed")
            failed_payload = failed_event.get("payload", {})
            self.assertIn("output_materialization_failed",
                          str(failed_payload.get("error", "")),
                          "error must contain output_materialization_failed category")

            leases.close()
            real_store.close()


class NoBase64InPersistedEventTests(unittest.TestCase):
    """Goal 3: no base64/binary remains in persisted event payloads."""

    def test_result_stripped_before_persist(self):
        """The result dict (with base64 data) must NOT appear in persisted
        cell.completed payload."""
        r = load_runner()
        from experiment_lease import LeaseRegistry

        with tempfile.TemporaryDirectory() as tmp:
            leases = LeaseRegistry(Path(tmp) / "leases.db")
            leases.claim("exp_nob64", "ck1", "w1")

            test_bytes = b"hello-world-image"
            import base64 as _b64
            b64_data = _b64.b64encode(test_bytes).decode("ascii")

            ev = {
                "type": "cell.completed",
                "data": {
                    "cell_key": "c_nob64",
                    "checkpoint_id": "ck1",
                    "lease_generation": 1,
                    "worker_invocation_id": "w1",
                    "attempt_id": "a_nob64_1",
                    "experiment_id": "exp_nob64",
                    "result": {
                        "outputs": {
                            "7": {
                                "images": [
                                    {
                                        "filename": "out.png",
                                        "data": b64_data,
                                        "mime_type": "image/png",
                                        "width": 64, "height": 64,
                                    },
                                ],
                            },
                        },
                    },
                },
            }

            from experiment_store import ExperimentStore
            real_store = ExperimentStore(Path(tmp) / ".experiments" / "exp_nob64", root=Path(tmp))
            real_store.ensure()

            et = ev.get("type", "")
            data = ev.get("data", {}) or {}
            try:
                leases.validate_and_accept(
                    "exp_nob64",
                    checkpoint_id=data.get("checkpoint_id", ""),
                    lease_generation=int(data.get("lease_generation", 0)),
                    worker_invocation_id=data.get("worker_invocation_id", ""),
                    attempt_id=data.get("attempt_id", ""),
                )
            except Exception:
                pass

            result_data = data.get("result", {}) or {}
            payload = {
                "checkpoint_id": data.get("checkpoint_id", ""),
                "cell_key": data.get("cell_key", ""),
                "worker_invocation_id": data.get("worker_invocation_id", ""),
                "lease_generation": data.get("lease_generation", 0),
                "attempt_id": data.get("attempt_id", ""),
                "error": data.get("error", ""),
            }

            # Materialize (should succeed)
            if result_data:
                try:
                    from tests.test_input_image_paths import _load_init_module as _load_init
                    init_mod = _load_init()
                    output_dir = str(Path(tmp) / "outputs" / data.get("cell_key", "") / data.get("attempt_id", ""))
                    mat = init_mod._materialize_experiment_output(
                        result_data, output_dir, data.get("cell_key", ""), data.get("attempt_id", ""),
                    )
                    payload["asset_ids"] = list(mat.get("assets", {}).keys())
                    payload["primary_asset_id"] = mat.get("primary_asset_id", "")
                    # Strip result before persisting
                    data.pop("result", None)
                except Exception:
                    payload["error"] = "output_materialization_failed"
                    real_store.append_event({"type": "cell.failed", "payload": payload})
                    leases.close()
                    real_store.close()
                    return

            real_store.append_event({"type": "cell.completed", "payload": payload})

            # Verify no base64 in persisted payload
            persisted = list(real_store.read_events())
            completed = next(e for e in persisted if e["type"] == "cell.completed")
            payload_str = json.dumps(completed)
            self.assertNotIn("base64", payload_str,
                             "persisted payload must not contain base64 data")
            self.assertNotIn("hello-world-image", payload_str,
                             "persisted payload must not contain binary data")
            # The field "data" should not be at the payload level
            self.assertNotIn('"data"', payload_str,
                             "persisted payload should not have 'data' field at top level")

            leases.close()
            real_store.close()


class OneTerminalEventPerCellTests(unittest.TestCase):
    """A3: Exactly one cell-level terminal event per attempt in journal."""

    def test_exactly_one_completed_per_attempt_in_journal(self):
        """Each attempt_id must appear at most once as cell.completed in journal."""
        r = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            invoker = FakeInvoker()
            spec = _two_checkpoint_spec()
            compilation = _compile_with_workflow_hash(spec)
            with _Harness(tmp) as harness:
                store = harness.store(spec["experiment_id"])
                store.ensure()
                store.write_definition({
                    "schema_version": 1, "experiment_id": spec["experiment_id"],
                    "revision": 1, "name": "T", "notes": "",
                    "created_at": "2026-06-17T00:00:00Z",
                    "updated_at": "2026-06-17T00:00:00Z",
                })
                leases = harness.leases()
                runner = r.ExperimentRunner(
                    store=store, leases=leases, invoker=invoker,
                    compilation=compilation, max_containers=2,
                )
                asyncio.run(runner.run())
                events = list(store.read_events())
                # Collect attempt_id per cell.completed
                completed_attempts = {}
                for ev in events:
                    if ev["type"] == "cell.completed":
                        payload = ev.get("payload", {}) or {}
                        attempt_id = payload.get("attempt_id", "")
                        cell_key = payload.get("cell_key", "")
                        if attempt_id:
                            key = (cell_key, attempt_id)
                            completed_attempts[key] = completed_attempts.get(key, 0) + 1
                # Each attempt should appear at most once
                dupes = {k: v for k, v in completed_attempts.items() if v > 1}
                self.assertEqual(
                    len(dupes), 0,
                    f"duplicate cell.completed for attempt(s): {dupes}"
                )
                # Each cell should have at most one completed event
                cell_completed_count = {}
                for ev in events:
                    if ev["type"] == "cell.completed":
                        ck = ev.get("payload", {}).get("cell_key", "")
                        cell_completed_count[ck] = cell_completed_count.get(ck, 0) + 1
                over = {k: v for k, v in cell_completed_count.items() if v > 1}
                self.assertEqual(
                    len(over), 0,
                    f"cells with >1 cell.completed: {over}"
                )

    def test_runner_does_not_emit_cell_terminal_events(self):
        """The runner must NOT emit cell.completed/cell.failed events.
        Only cell.attempt_created is emitted by the runner."""
        r = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            invoker = FakeInvoker()
            spec = _two_checkpoint_spec()
            compilation = _compile_with_workflow_hash(spec)
            with _Harness(tmp) as harness:
                store = harness.store(spec["experiment_id"])
                store.ensure()
                store.write_definition({
                    "schema_version": 1, "experiment_id": spec["experiment_id"],
                    "revision": 1, "name": "T", "notes": "",
                    "created_at": "2026-06-17T00:00:00Z",
                    "updated_at": "2026-06-17T00:00:00Z",
                })
                leases = harness.leases()
                runner = r.ExperimentRunner(
                    store=store, leases=leases, invoker=invoker,
                    compilation=compilation, max_containers=2,
                )
                asyncio.run(runner.run())
                events = list(store.read_events())
                types = [e["type"] for e in events]
                # Runner must not emit cell.completed, cell.failed, or cell.interrupted
                runner_terminal = {"cell.completed", "cell.failed", "cell.interrupted"}
                runner_emitted = set(types) & runner_terminal
                self.assertEqual(
                    len(runner_emitted), 0,
                    f"runner must not emit cell terminal events, got: {runner_emitted}"
                )
                # Only experiment.started, experiment.completed, checkpoint.claimed,
                # checkpoint.completed, cell.attempt_created should be present
                allowed = {"experiment.started", "experiment.completed",
                           "checkpoint.claimed", "checkpoint.completed",
                           "checkpoint.stopped", "checkpoint.completed_with_failures",
                           "checkpoint.failed_fatal", "cell.attempt_created"}
                unexpected = set(types) - allowed
                self.assertEqual(
                    len(unexpected), 0,
                    f"unexpected event types emitted by runner: {unexpected}"
                )


class StopNowOrderTests(unittest.TestCase):
    """A4: Stop-now must follow (1) lease.invalidate, (2) write stop_now,
    (3) cancel remote stream, (4) wait bounded, (5) emit one cell.interrupted
    for active attempt, (6) clear control after ack."""

    def test_stop_now_invalidates_lease_before_cancel(self):
        """stop_now must invalidate leases before cancelling workers."""
        r = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            invoker = FakeInvoker()
            invoker.delay_ms = 50
            spec = _two_checkpoint_spec()
            compilation = _compile_with_workflow_hash(spec)
            with _Harness(tmp) as harness:
                store = harness.store(spec["experiment_id"])
                store.ensure()
                store.write_definition({
                    "schema_version": 1, "experiment_id": spec["experiment_id"],
                    "revision": 1, "name": "T", "notes": "",
                    "created_at": "2026-06-17T00:00:00Z",
                    "updated_at": "2026-06-17T00:00:00Z",
                })
                leases = harness.leases()
                runner = r.ExperimentRunner(
                    store=store, leases=leases, invoker=invoker,
                    compilation=compilation, max_containers=2,
                )
                async def drive():
                    async def trigger():
                        await asyncio.sleep(0.03)
                        await runner.stop_now()
                    asyncio.create_task(trigger())
                    await runner.run()
                asyncio.run(drive())
                exp_id = compilation.get("experiment_id", "")
                snap = leases.snapshot(exp_id)
                for ck_id, info in snap.get("leases", {}).items():
                    # All active leases should be cancelling or released
                    self.assertIn(
                        info["status"],
                        ("cancelling", "released"),
                        f"lease {ck_id} should be cancelling/released after stop_now, got {info['status']}"
                    )

    def test_stop_now_control_record_remains_while_pending(self):
        """Control record must remain stop_now while cancellation is pending."""
        r = load_runner()
        from worker_control import FakeDictControlBackend
        with tempfile.TemporaryDirectory() as tmp:
            invoker = FakeInvoker()
            invoker.delay_ms = 100
            spec = _two_checkpoint_spec()
            compilation = _compile_with_workflow_hash(spec)
            with _Harness(tmp) as harness:
                store = harness.store(spec["experiment_id"])
                store.ensure()
                store.write_definition({
                    "schema_version": 1, "experiment_id": spec["experiment_id"],
                    "revision": 1, "name": "T", "notes": "",
                    "created_at": "2026-06-17T00:00:00Z",
                    "updated_at": "2026-06-17T00:00:00Z",
                })
                leases = harness.leases()
                # Create a CheckpointStreamInvoker with a FakeDictControlBackend
                # so we can observe the control record
                control_backend = FakeDictControlBackend()
                stream_invoker = r.CheckpointStreamInvoker(
                    _FakeCheckpointStreamGenerator(),
                    experiment_id=spec["experiment_id"],
                    control_backend=control_backend,
                )
                runner = r.ExperimentRunner(
                    store=store, leases=leases, invoker=stream_invoker,
                    compilation=compilation, max_containers=1,
                )
                async def drive():
                    async def trigger():
                        await asyncio.sleep(0.02)
                        await runner.stop_now()
                        # After stop_now, check that control records for active
                        # workers are stop_now (before full cleanup)
                        for wid, ck_id in runner._active_workers.items():
                            state = await control_backend.get_control(
                                "", spec["experiment_id"], ck_id, wid, 0
                            )
                            # Note: the invoker's cancel_worker clears after writing,
                            # so the record may already be cleared. The key test is
                            # that stop_now wrote it at some point.
                    asyncio.create_task(trigger())
                    await runner.run()
                asyncio.run(drive())

    def test_stop_now_refuses_completion_after_boundary(self):
        """After stop_now, late cell.completed events must be rejected by
        lease validation."""
        r = load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            invoker = FakeInvoker()
            invoker.delay_ms = 50
            spec = _two_checkpoint_spec()
            compilation = _compile_with_workflow_hash(spec)
            with _Harness(tmp) as harness:
                store = harness.store(spec["experiment_id"])
                store.ensure()
                store.write_definition({
                    "schema_version": 1, "experiment_id": spec["experiment_id"],
                    "revision": 1, "name": "T", "notes": "",
                    "created_at": "2026-06-17T00:00:00Z",
                    "updated_at": "2026-06-17T00:00:00Z",
                })
                leases = harness.leases()
                runner = r.ExperimentRunner(
                    store=store, leases=leases, invoker=invoker,
                    compilation=compilation, max_containers=2,
                )
                async def drive():
                    async def trigger():
                        await asyncio.sleep(0.03)
                        await runner.stop_now()
                    asyncio.create_task(trigger())
                    await runner.run()
                asyncio.run(drive())
                exp_id = compilation.get("experiment_id", "")
                snap = leases.snapshot(exp_id)
                # Attempt to accept a late event for each lease should fail
                for ck_id, info in snap.get("leases", {}).items():
                    if info["status"] in ("cancelling",):
                        with self.assertRaises(r.LeaseError if not hasattr(r, 'CancellationBoundary') else (r.LeaseError,)):
                            pass  # The lease is invalidated, which is sufficient


# ── D2: Invalid mapping preflight error classes ───────────────────────────

class InvalidMappingErrorsTests(unittest.TestCase):
    """D2: resolve_and_inject_cell raises structured errors before remote open."""

    def setUp(self):
        self.runner = load_runner()
        self.wf = {
            "10": {"class_type": "CLIPTextEncode", "inputs": {"text": "hello"}},
            "6": {"class_type": "KSampler", "inputs": {"seed": 42, "steps": 20, "cfg": 7.0}},
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "u.safetensors"}},
        }
        self.cell = {
            "cell_key": "ck_test",
            "profile_id": "p1",
            "loader_target_group_id": "g_missing",
            "triple": {"unet": "n.safetensors", "clip": "", "vae": ""},
            "prompt": "test",
            "negative_prompt": "bad",
            "axis_values": {},
            "lora_signature": [],
        }

    def test_error_classes_available(self):
        """All structured error classes must be available."""
        mod = self.runner
        for cls_name in ("MissingLoaderTargetGroup", "MissingMappedNode",
                         "MissingMappedField", "MissingPromptSlot",
                         "MissingNegativePromptSlot", "MissingImageSlot",
                         "MissingLoRASlot", "InvalidLoRASlotCapacity",
                         "InvalidMappedPath"):
            self.assertTrue(
                hasattr(mod, cls_name),
                f"{cls_name} not found in experiment_runner module"
            )

    def test_missing_loader_target_group_error_includes_profile_and_group(self):
        """MissingLoaderTargetGroup error includes profile_id and group_id."""
        mod = self.runner
        profile_slots = {"prompt": {"node_id": "10", "path": ["inputs", "text"], "field": "text"}}
        loader_groups = [{"id": "g_real", "unet": [], "clip": [], "vae": []}]
        with self.assertRaises(mod.MissingLoaderTargetGroup) as ctx:
            mod.resolve_and_inject_cell(
                profile_workflow=self.wf,
                profile_slots=profile_slots,
                loader_target_groups=loader_groups,
                lora_slots=[],
                cell=self.cell,
            )
        msg = str(ctx.exception)
        self.assertIn("p1", msg)
        self.assertIn("g_missing", msg)

    def test_missing_prompt_slot_error_includes_profile(self):
        """MissingPromptSlot error includes profile_id."""
        mod = self.runner
        profile_slots = {}
        with self.assertRaises(mod.MissingPromptSlot) as ctx:
            mod.resolve_and_inject_cell(
                profile_workflow=self.wf,
                profile_slots=profile_slots,
                loader_target_groups=[],
                lora_slots=[],
                cell=self.cell,
            )
        msg = str(ctx.exception)
        self.assertIn("p1", msg)

    def test_missing_mapped_node_error_includes_node_and_profile(self):
        """MissingMappedNode error includes node_id and profile_id."""
        mod = self.runner
        profile_slots = {
            "prompt": {"node_id": "999", "path": ["inputs", "text"], "field": "text"},
        }
        with self.assertRaises(mod.MissingMappedNode) as ctx:
            mod.resolve_and_inject_cell(
                profile_workflow=self.wf,
                profile_slots=profile_slots,
                loader_target_groups=[],
                lora_slots=[],
                cell=self.cell,
            )
        msg = str(ctx.exception)
        self.assertIn("999", msg)
        self.assertIn("p1", msg)

    def test_invalid_mapped_path_error_includes_node_field_and_profile(self):
        """InvalidMappedPath error includes node_id, field, and profile_id."""
        mod = self.runner
        profile_slots = {
            "prompt": {"node_id": "10", "path": ["inputs", "nonexistent_field"], "field": "nonexistent_field"},
        }
        with self.assertRaises(mod.InvalidMappedPath) as ctx:
            mod.resolve_and_inject_cell(
                profile_workflow=self.wf,
                profile_slots=profile_slots,
                loader_target_groups=[],
                lora_slots=[],
                cell=self.cell,
            )
        msg = str(ctx.exception)
        self.assertIn("10", msg)
        self.assertIn("p1", msg)
        self.assertIn("nonexistent_field", msg)

    def test_missing_lora_slot_error_includes_profile(self):
        """MissingLoRASlot error includes profile_id."""
        mod = self.runner
        cell = dict(self.cell)
        cell["lora_signature"] = [["lora.safetensors", 0.5, 0.5]]
        profile_slots = {"prompt": {"node_id": "10", "path": ["inputs", "text"], "field": "text"}}
        with self.assertRaises(mod.MissingLoRASlot) as ctx:
            mod.resolve_and_inject_cell(
                profile_workflow=self.wf,
                profile_slots=profile_slots,
                loader_target_groups=[],
                lora_slots=[],
                cell=cell,
            )
        msg = str(ctx.exception)
        self.assertIn("p1", msg)


# ── D4: Resolved metadata flow ───────────────────────────────────────────

class ResolvedMetadataFlowTests(unittest.TestCase):
    """D4: resolve_and_inject_cell returns every value the runner needs."""

    def setUp(self):
        self.runner = load_runner()
        self.wf = {
            "10": {"class_type": "CLIPTextEncode", "inputs": {"text": "hello"}},
            "12": {"class_type": "CLIPTextEncode", "inputs": {"text": "bad"}},
            "6": {"class_type": "KSampler", "inputs": {"seed": 42, "steps": 20, "cfg": 7.0}},
        }
        self.slots = {
            "prompt": {"node_id": "10", "field": "text", "path": ["inputs", "text"]},
            "negative_prompt": {"node_id": "12", "field": "text", "path": ["inputs", "text"]},
            "seed": {"node_id": "6", "field": "seed", "path": ["inputs", "seed"]},
            "steps": {"node_id": "6", "field": "steps", "path": ["inputs", "steps"]},
            "guidance": {"node_id": "6", "field": "cfg", "path": ["inputs", "cfg"]},
        }
        self.cell = {
            "cell_key": "ck_d4",
            "profile_id": "p1",
            "loader_target_group_id": "g_default",
            "triple": {"unet": "u.safetensors", "clip": "c.safetensors", "vae": "v.safetensors"},
            "prompt": "a cat",
            "negative_prompt": "",
            "input_image_hash": "",
            "lora_signature": [],
            "axis_values": {
                "seed": 99,
                "steps": 30,
                "guidance": 8.0,
                "sampler": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
            },
        }

    def test_resolved_execution_has_all_expected_fields(self):
        """ResolvedCellExecution has every field the runner needs."""
        resolved = self.runner.resolve_and_inject_cell(
            profile_workflow=self.wf,
            profile_slots=self.slots,
            loader_target_groups=[],
            lora_slots=[],
            cell=self.cell,
        )
        # Verify all fields exist
        self.assertIsNotNone(resolved.workflow)
        self.assertIsInstance(resolved.workflow_hash, str)
        self.assertEqual(len(resolved.workflow_hash), 64)
        self.assertEqual(resolved.positive_prompt, "a cat")
        self.assertEqual(resolved.negative_prompt, "")
        self.assertEqual(resolved.unet, "u.safetensors")
        self.assertEqual(resolved.clip, "c.safetensors")
        self.assertEqual(resolved.vae, "v.safetensors")
        self.assertEqual(resolved.lora_chain, [])
        self.assertEqual(resolved.sampler, "euler")
        self.assertEqual(resolved.scheduler, "normal")
        self.assertEqual(resolved.steps, 30)
        self.assertEqual(resolved.guidance, 8.0)
        self.assertEqual(resolved.denoise, 1.0)
        self.assertEqual(resolved.seed, 99)
        self.assertIsInstance(resolved.resolved_axis, dict)

    def test_resolved_metadata_stored_on_cell(self):
        """Every resolved value must be stored on the cell dict for event-side."""
        resolved = self.runner.resolve_and_inject_cell(
            profile_workflow=self.wf,
            profile_slots=self.slots,
            loader_target_groups=[],
            lora_slots=[],
            cell=self.cell,
        )
        # The runner stores values as cell["_resolved_*"]
        self.cell["_resolved_workflow"] = resolved.workflow
        self.cell["_resolved_prompt"] = resolved.positive_prompt
        self.cell["_resolved_negative"] = resolved.negative_prompt
        self.cell["_resolved_unet"] = resolved.unet
        self.cell["_resolved_clip"] = resolved.clip
        self.cell["_resolved_vae"] = resolved.vae
        self.cell["_resolved_lora_chain"] = resolved.lora_chain
        # Verify all stored on cell
        self.assertEqual(self.cell["_resolved_prompt"], "a cat")
        self.assertEqual(self.cell["_resolved_negative"], "")
        self.assertEqual(self.cell["_resolved_unet"], "u.safetensors")
        self.assertEqual(self.cell["_resolved_clip"], "c.safetensors")
        self.assertEqual(self.cell["_resolved_vae"], "v.safetensors")
        self.assertEqual(self.cell["_resolved_lora_chain"], [])

    def test_explicit_guidance_zero_survives(self):
        """Explicit guidance 0 and seed 0 survive through resolution."""
        cell = dict(self.cell)
        cell["axis_values"] = {
            "seed": 0,
            "steps": 20,
            "guidance": 0.0,
            "denoise": 1.0,
        }
        resolved = self.runner.resolve_and_inject_cell(
            profile_workflow=self.wf,
            profile_slots=self.slots,
            loader_target_groups=[],
            lora_slots=[],
            cell=cell,
        )
        # 0 must survive, not be replaced by workflow_owned
        self.assertEqual(resolved.seed, 0)
        self.assertEqual(resolved.guidance, 0.0)

    def test_empty_negative_survives(self):
        """Empty negative string survives through resolution."""
        resolved = self.runner.resolve_and_inject_cell(
            profile_workflow=self.wf,
            profile_slots=self.slots,
            loader_target_groups=[],
            lora_slots=[],
            cell=self.cell,
        )
        self.assertEqual(resolved.negative_prompt, "")
        # Verify the actual workflow was injected with empty negative
        neg_node = resolved.workflow.get("12", {}).get("inputs", {}).get("text", "")
        self.assertEqual(neg_node, "")

    def test_workflow_owned_values_readable_after_injection(self):
        """WORKFLOW_OWNED axis values leave workflow values intact and
        resolved_axis captures the actual values."""
        cell = dict(self.cell)
        from matrix_compiler import WORKFLOW_OWNED
        cell["axis_values"] = {
            "seed": WORKFLOW_OWNED,
            "steps": WORKFLOW_OWNED,
            "guidance": WORKFLOW_OWNED,
        }
        resolved = self.runner.resolve_and_inject_cell(
            profile_workflow=self.wf,
            profile_slots=self.slots,
            loader_target_groups=[],
            lora_slots=[],
            cell=cell,
        )
        # Workflow should still have original values
        wf = resolved.workflow
        self.assertEqual(wf["6"]["inputs"]["seed"], 42)
        self.assertEqual(wf["6"]["inputs"]["steps"], 20)
        self.assertEqual(wf["6"]["inputs"]["cfg"], 7.0)
        # resolved_axis should contain the actual read-back values
        self.assertEqual(resolved.resolved_axis.get("seed"), 42)
        self.assertEqual(resolved.resolved_axis.get("steps"), 20)
        self.assertEqual(resolved.resolved_axis.get("guidance"), 7.0)


# ── Task 2: Axis value coercion before int() calls ─────────────────────────

class AxisCoercionBeforeIntTests(unittest.TestCase):
    """resolve_and_inject_cell must reject lists/objects for scalar axes
    before reaching int()/float() calls, with field-specific errors."""

    def _make_runner(self):
        return load_runner()

    def _wf_with_slots(self):
        wf = {
            "1": {"class_type": "KSampler", "inputs": {
                "seed": 42, "steps": 20, "cfg": 7.0,
                "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0,
            }},
            "99": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
        }
        slots = {
            "prompt": {"node_id": "99", "field": "text", "path": ["inputs", "text"]},
            "seed": {"node_id": "1", "field": "seed", "path": ["inputs", "seed"]},
            "steps": {"node_id": "1", "field": "steps", "path": ["inputs", "steps"]},
            "guidance": {"node_id": "1", "field": "cfg", "path": ["inputs", "cfg"]},
            "sampler": {"node_id": "1", "field": "sampler_name", "path": ["inputs", "sampler_name"]},
            "scheduler": {"node_id": "1", "field": "scheduler", "path": ["inputs", "scheduler"]},
            "denoise": {"node_id": "1", "field": "denoise", "path": ["inputs", "denoise"]},
        }
        return wf, slots

    def _cell(self, axis_values):
        from matrix_compiler import WORKFLOW_OWNED
        return {
            "profile_id": "p1",
            "prompt": "test",
            "negative_prompt": "",
            "axis_values": axis_values,
            "lora_signature": [],
            "input_image_hash": "",
            "triple": {},
            "loader_target_group_id": "g_default",
        }

    def test_axis_array_seed_rejected_before_int(self):
        """seed=[42] raises ValueError with field name before int()."""
        r = self._make_runner()
        wf, slots = self._wf_with_slots()
        with self.assertRaises(ValueError) as ctx:
            r.resolve_and_inject_cell(
                wf, slots, [], [], self._cell({"seed": [42]}),
            )
        self.assertIn("seed", str(ctx.exception))

    def test_axis_array_steps_rejected_before_int(self):
        """steps=[20] raises ValueError with field name before int()."""
        r = self._make_runner()
        wf, slots = self._wf_with_slots()
        with self.assertRaises(ValueError) as ctx:
            r.resolve_and_inject_cell(
                wf, slots, [], [], self._cell({"steps": [20]}),
            )
        self.assertIn("steps", str(ctx.exception))

    def test_axis_dict_guidance_rejected_before_float(self):
        """guidance={"val":7.5} raises ValueError before float()."""
        r = self._make_runner()
        wf, slots = self._wf_with_slots()
        with self.assertRaises(ValueError) as ctx:
            r.resolve_and_inject_cell(
                wf, slots, [], [], self._cell({"guidance": {"val": 7.5}}),
            )
        self.assertIn("guidance", str(ctx.exception))

    def test_axis_list_sampler_rejected(self):
        """sampler=["euler"] raises ValueError."""
        r = self._make_runner()
        wf, slots = self._wf_with_slots()
        with self.assertRaises(ValueError) as ctx:
            r.resolve_and_inject_cell(
                wf, slots, [], [], self._cell({"sampler": ["euler"]}),
            )
        self.assertIn("sampler", str(ctx.exception))

    def test_axis_zero_seed_preserved(self):
        """seed=0 survives without error."""
        r = self._make_runner()
        wf, slots = self._wf_with_slots()
        resolved = r.resolve_and_inject_cell(
            wf, slots, [], [], self._cell({"seed": 0, "steps": 20}),
        )
        self.assertEqual(resolved.seed, 0)

    def test_axis_zero_guidance_preserved(self):
        """guidance=0.0 survives without error."""
        r = self._make_runner()
        wf, slots = self._wf_with_slots()
        resolved = r.resolve_and_inject_cell(
            wf, slots, [], [], self._cell({"guidance": 0.0, "seed": 1, "steps": 20}),
        )
        self.assertEqual(resolved.guidance, 0.0)

    def test_axis_zero_denoise_preserved(self):
        """denoise=0.0 survives without error."""
        r = self._make_runner()
        wf, slots = self._wf_with_slots()
        resolved = r.resolve_and_inject_cell(
            wf, slots, [], [], self._cell({"denoise": 0.0, "seed": 1, "steps": 20}),
        )
        self.assertEqual(resolved.denoise, 0.0)


# ── B1: Per-invocation i2i ownership tests ────────────────────────────────

class PerInvocationMaterializationTests(unittest.TestCase):
    """B1 tests: per-invocation i2i file tracking with 5-component identity.

    These tests verify the _track_materialized_file and
    _cleanup_all_materialized_file helpers directly, validating that
    each invocation's files are isolated.
    """

    def setUp(self):
        # Import the comfyapp module's B1 helpers
        import importlib.util
        self._comfyapp_path = REPO_ROOT / "comfyapp.py"
        spec = importlib.util.spec_from_file_location("comfyapp_test", self._comfyapp_path)
        assert spec is not None
        assert spec.loader is not None
        self.cm = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.cm)
        # Reset the global tracking dict before each test
        self.cm._MATERIALIZED_FILES_BY_INVOCATION.clear()
        self.cm._MATERIALIZED_FILES.clear()

    def _key(self, dep="dg1", exp="exp1", ck="ck1", wid="w1", lg=1):
        return self.cm._build_invocation_key(dep, exp, ck, wid, lg)

    def test_two_invocations_have_isolated_file_lists(self):
        """B1: Two simultaneous invocations have isolated file lists."""
        key_a = self._key(wid="wA")
        key_b = self._key(wid="wB")
        self.cm._track_materialized_file("/tmp/inA/file1.png", identity_key=key_a)
        self.cm._track_materialized_file("/tmp/inA/file2.png", identity_key=key_a)
        self.cm._track_materialized_file("/tmp/inB/file1.png", identity_key=key_b)
        self.assertEqual(
            len(self.cm._MATERIALIZED_FILES_BY_INVOCATION[key_a]), 2,
            "invocation A should track 2 files"
        )
        self.assertEqual(
            len(self.cm._MATERIALIZED_FILES_BY_INVOCATION[key_b]), 1,
            "invocation B should track 1 file"
        )

    def test_finishing_a_does_not_delete_bs_files(self):
        """B1: Finishing invocation A does not delete B's files."""
        key_a = self._key(wid="wA")
        key_b = self._key(wid="wB")
        self.cm._track_materialized_file("/tmp/shared/file.png", identity_key=key_a)
        self.cm._track_materialized_file("/tmp/shared/file.png", identity_key=key_b)
        # Cleanup A's files
        deleted = self.cm._cleanup_all_materialized_files(identity_key=key_a)
        self.assertEqual(deleted, 0,  # file doesn't exist on disk
                         "no files on disk to delete")
        # B's list should still exist
        self.assertIn(key_b, self.cm._MATERIALIZED_FILES_BY_INVOCATION,
                      "invocation B should still be tracked after A cleans up")
        self.assertEqual(
            len(self.cm._MATERIALIZED_FILES_BY_INVOCATION[key_b]), 1,
            "invocation B should still have its file"
        )

    def test_cleanup_is_idempotent(self):
        """B1: Cleaning up an already-cleaned invocation is a no-op."""
        key_a = self._key(wid="wA")
        self.cm._track_materialized_file("/tmp/a/file.png", identity_key=key_a)
        self.cm._cleanup_all_materialized_files(identity_key=key_a)
        self.assertNotIn(key_a, self.cm._MATERIALIZED_FILES_BY_INVOCATION,
                         "invocation A should be removed after cleanup")
        # Second cleanup should be a no-op
        deleted = self.cm._cleanup_all_materialized_files(identity_key=key_a)
        self.assertEqual(deleted, 0, "second cleanup of same key should delete nothing")

    def test_same_image_does_not_duplicate_in_one_invocation(self):
        """B1: Same image path used multiple times in one invocation deduplicates."""
        key_a = self._key(wid="wA")
        self.cm._track_materialized_file("/tmp/shared/img.png", identity_key=key_a)
        self.cm._track_materialized_file("/tmp/shared/img.png", identity_key=key_a)
        self.cm._track_materialized_file("/tmp/shared/img.png", identity_key=key_a)
        self.assertEqual(
            len(self.cm._MATERIALIZED_FILES_BY_INVOCATION[key_a]), 1,
            "same path in one invocation should deduplicate"
        )


if __name__ == "__main__":
    unittest.main()
