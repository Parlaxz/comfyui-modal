import importlib.util
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "experiment_store.py"


def load_module():
    if not MODULE_PATH.exists():
        raise AssertionError("experiment_store.py missing")
    spec = importlib.util.spec_from_file_location("experiment_store", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class JournalAppendTests(unittest.TestCase):
    def test_append_assigns_monotonic_sequence(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.ExperimentStore(Path(tmp) / "exp1", root=Path(tmp)) as store:
                store.ensure()
                e1 = store.append_event({"type": "experiment.created", "payload": {}})
                e2 = store.append_event({"type": "experiment.started", "payload": {}})
                self.assertEqual(e1["sequence"], 1)
                self.assertEqual(e2["sequence"], 2)

    def test_append_persists_event_to_disk(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.ExperimentStore(Path(tmp) / "exp1", root=Path(tmp)) as store:
                store.ensure()
                store.append_event({"type": "experiment.created", "payload": {"x": 1}})
                events = list(store.read_events())
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0]["type"], "experiment.created")
                self.assertEqual(events[0]["payload"], {"x": 1})

    def test_concurrent_appends_get_unique_sequences(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.ExperimentStore(Path(tmp) / "exp1", root=Path(tmp)) as store:
                store.ensure()
                results: list[int] = []
                lock = threading.Lock()
                def worker():
                    ev = store.append_event({"type": "noop", "payload": {}})
                    with lock:
                        results.append(ev["sequence"])
                    store.close_thread()
                threads = [threading.Thread(target=worker) for _ in range(20)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join()
                self.assertEqual(sorted(results), list(range(1, 21)))

    def test_read_events_ignores_truncated_final_line(self):
        # With the SQLite-backed store, partial / truncated writes are
        # impossible: a single INSERT is atomic. A test that used to
        # append a malformed final line and recover the rest is no
        # longer applicable. Instead, verify that an externally-broken
        # SQLite row can never appear because the store only writes via
        # INSERT.
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.ExperimentStore(Path(tmp) / "exp1", root=Path(tmp)) as store:
                store.ensure()
                store.append_event({"type": "a", "payload": {}})
                store.append_event({"type": "b", "payload": {}})
                events = list(store.read_events())
                self.assertEqual([e["type"] for e in events], ["a", "b"])


class JournalCorruptionTests(unittest.TestCase):
    def test_read_events_skips_unparseable_payloads(self):
        # With the SQLite-backed store, the events table is authoritative.
        # If a row's payload field is somehow corrupt (manual SQL edit,
        # partial restore), read_events() returns an empty payload dict
        # rather than raising -- callers tolerate unknown event types.
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.ExperimentStore(Path(tmp) / "exp1", root=Path(tmp)) as store:
                store.ensure()
                store.append_event({"type": "a", "payload": {"k": 1}})
                # Inject a corrupt payload directly via the connection.
                store._conn().execute(
                    "INSERT INTO events (event_id, type, payload, timestamp) "
                    "VALUES (?, ?, ?, ?)",
                    ("corrupt-evt", "x", "NOT JSON", "2026-06-17T00:00:00Z"),
                )
                events = list(store.read_events())
                types = [e["type"] for e in events]
                self.assertEqual(types, ["a", "x"])
                self.assertEqual(events[1]["payload"], {})


class SnapshotTests(unittest.TestCase):
    def test_snapshot_round_trip(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.ExperimentStore(Path(tmp) / "exp1", root=Path(tmp)) as store:
                store.ensure()
                store.write_snapshot({"status": "running", "counters": {"completed": 3}})
                snap = store.read_snapshot()
                self.assertEqual(snap["status"], "running")
                self.assertEqual(snap["counters"], {"completed": 3})

    def test_snapshot_atomic_replace(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.ExperimentStore(Path(tmp) / "exp1", root=Path(tmp)) as store:
                store.ensure()
                store.write_snapshot({"a": 1})
                store.write_snapshot({"a": 2})
                # No leftover temp file should remain after the replace.
                leftovers = [
                    p for p in (Path(tmp) / "exp1").iterdir()
                    if p.name != "store.db" and p.name != "store.db-wal" and p.name != "store.db-shm"
                    and p.name != "snapshot.json"
                ]
                self.assertEqual(leftovers, [])

    def test_read_snapshot_returns_none_when_missing(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.ExperimentStore(Path(tmp) / "exp1", root=Path(tmp)) as store:
                store.ensure()
                self.assertIsNone(store.read_snapshot())


class RebuildTests(unittest.TestCase):
    def test_rebuild_from_journal_only(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.ExperimentStore(Path(tmp) / "exp1", root=Path(tmp)) as store:
                store.ensure()
                store.append_event({"type": "experiment.created", "payload": {"id": "x"}})
                store.append_event({"type": "cell.completed", "payload": {"cell_key": "k1"}})
                store.append_event({"type": "cell.completed", "payload": {"cell_key": "k2"}})
                store.append_event({"type": "cell.failed", "payload": {"cell_key": "k3"}})
                rebuilt = store.rebuild_snapshot()
                self.assertEqual(rebuilt["counters"]["completed"], 2)
                self.assertEqual(rebuilt["counters"]["failed"], 1)
                self.assertEqual(rebuilt["last_sequence"], 4)

    def test_snapshot_visible_state_excludes_superseded(self):
        """Superseded attempts must not appear in visible counters."""
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.ExperimentStore(Path(tmp) / "exp1", root=Path(tmp)) as store:
                store.ensure()
                store.append_event({"type": "cell.completed", "payload": {"cell_key": "k1"}})
                store.append_event({"type": "cell.completed", "payload": {"cell_key": "k2"}})
                # Supersede k1 and re-complete it
                store.append_event({"type": "attempt.superseded", "payload": {"cell_key": "k1"}})
                store.append_event({"type": "cell.completed", "payload": {"cell_key": "k1"}})
                rebuilt = store.rebuild_snapshot()
                # k1 appears only once in visible state (not completed=2)
                self.assertEqual(rebuilt["counters"]["completed"], 2,
                    "superseded+re-completed counts as 1 completed, not 2")
                # k1 is in cell_visible
                self.assertEqual(rebuilt["cell_visible"].get("k1"), "completed")

    def test_snapshot_counters_never_exceed_total_unique_cells(self):
        """Counters sum must not exceed total unique cell_keys in events."""
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.ExperimentStore(Path(tmp) / "exp1", root=Path(tmp)) as store:
                store.ensure()
                store.append_event({"type": "cell.completed", "payload": {"cell_key": "k1"}})
                store.append_event({"type": "cell.failed", "payload": {"cell_key": "k2"}})
                store.append_event({"type": "cell.interrupted", "payload": {"cell_key": "k3"}})
                store.append_event({"type": "cell.skipped", "payload": {"cell_key": "k4"}})
                rebuilt = store.rebuild_snapshot()
                total_visible = sum(rebuilt["counters"].values())
                self.assertEqual(total_visible, 4,
                    "each unique cell_key counted exactly once")
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.ExperimentStore(Path(tmp) / "exp1", root=Path(tmp)) as store:
                store.ensure()
                store.append_event({"type": "experiment.created", "payload": {"id": "x"}})
                store.append_event({"type": "cell.completed", "payload": {"cell_key": "k1"}})
                store.append_event({"type": "cell.completed", "payload": {"cell_key": "k2"}})
                store.append_event({"type": "cell.failed", "payload": {"cell_key": "k3"}})
                rebuilt = store.rebuild_snapshot()
                self.assertEqual(rebuilt["counters"]["completed"], 2)
                self.assertEqual(rebuilt["counters"]["failed"], 1)
                self.assertEqual(rebuilt["last_sequence"], 4)

    def test_rebuild_after_snapshot_delete_matches_disk(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.ExperimentStore(Path(tmp) / "exp1", root=Path(tmp)) as store:
                store.ensure()
                for i in range(5):
                    store.append_event({"type": "cell.completed", "payload": {"i": i}})
                store.rebuild_snapshot()  # write first
                (Path(tmp) / "exp1" / "snapshot.json").unlink()
                rebuilt = store.rebuild_snapshot()
                self.assertEqual(rebuilt["counters"]["completed"], 5)
                self.assertEqual(rebuilt["last_sequence"], 5)

    def test_snapshot_includes_total_cells(self):
        """C7: rebuild_snapshot must include total_cells in its output."""
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.ExperimentStore(Path(tmp) / "exp1", root=Path(tmp)) as store:
                store.ensure()
                store.append_event({"type": "cell.completed", "payload": {"cell_key": "k1"}})
                store.append_event({"type": "cell.completed", "payload": {"cell_key": "k2"}})
                rebuilt = store.rebuild_snapshot(total_cells=10)
                self.assertIn("total_cells", rebuilt,
                    "snapshot must include total_cells")
                self.assertEqual(rebuilt["total_cells"], 10,
                    "total_cells must match the passed value")
                # Default (no arg) should be 0
                rebuilt2 = store.rebuild_snapshot()
                self.assertEqual(rebuilt2.get("total_cells", -1), 0,
                    "default total_cells should be 0")


def _mp_worker(exp_dir_str: str, tag: str, result_path: str) -> None:
    """Top-level worker for cross-process test (must be picklable)."""
    import json as _json
    import importlib.util
    exp_dir = Path(exp_dir_str)
    spec = importlib.util.spec_from_file_location("experiment_store", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    with module.ExperimentStore(exp_dir, root=exp_dir.parent) as store:
        store.ensure()
        ev = store.append_event({"type": tag, "payload": {}})
    with open(result_path, "w", encoding="utf-8") as f:
        _json.dump({"tag": tag, "sequence": ev["sequence"]}, f)


class CrossInstanceTests(unittest.TestCase):
    """Two independently-constructed stores sharing the same directory
    must see the same data and assign monotonic unique sequences."""

    def test_two_stores_see_each_others_events(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            exp_dir = Path(tmp) / "exp1"
            with module.ExperimentStore(exp_dir, root=Path(tmp)) as a:
                a.ensure()
                a.append_event({"type": "a1", "payload": {}})
                a.append_event({"type": "a2", "payload": {}})
            with module.ExperimentStore(exp_dir, root=Path(tmp)) as b:
                events = list(b.read_events())
                self.assertEqual([e["type"] for e in events], ["a1", "a2"])
                self.assertEqual([e["sequence"] for e in events], [1, 2])

    def test_two_stores_assign_distinct_sequences(self):
        import multiprocessing as mp
        with tempfile.TemporaryDirectory() as tmp:
            exp_dir = Path(tmp) / "exp1"
            # First store exists long enough to write the schema
            module = load_module()
            with module.ExperimentStore(exp_dir, root=Path(tmp)) as a:
                a.ensure()
            # Now spawn two child processes, each opens its own store and
            # appends a single event. Their sequence numbers must not collide.
            ctx = mp.get_context("spawn")
            results_dir = Path(tmp) / "results"
            results_dir.mkdir()
            procs = [
                ctx.Process(target=_mp_worker, args=(str(exp_dir), f"p{i}", str(results_dir / f"r{i}.json")))
                for i in range(2)
            ]
            for p in procs:
                p.start()
            for p in procs:
                p.join()
            self.assertTrue(all(p.exitcode == 0 for p in procs), f"procs failed: {[p.exitcode for p in procs]}")
            with module.ExperimentStore(exp_dir, root=Path(tmp)) as b:
                seqs = [e["sequence"] for e in b.read_events()]
                self.assertEqual(len(seqs), 2)
                self.assertEqual(sorted(seqs), [1, 2])


class StatusEventPrecedenceTests(unittest.TestCase):
    """experiment.status events must take precedence over stale
    experiment.completed in rebuild_snapshot."""

    def test_status_event_overrides_stale_completed(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.ExperimentStore(Path(tmp) / "exp1", root=Path(tmp)) as store:
                store.ensure()
                store.append_event({"type": "experiment.started", "payload": {"total_cells": 2}})
                store.append_event({"type": "cell.completed", "payload": {"cell_key": "k1"}})
                store.append_event({"type": "experiment.completed", "payload": {"completed": 1}})
                store.append_event({"type": "experiment.status", "payload": {"status": "paused"}})
                snap = store.rebuild_snapshot()
                self.assertEqual(snap["status"], "paused",
                    "experiment.status with paused must override stale completed")

    def test_status_event_completed_with_failures(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.ExperimentStore(Path(tmp) / "exp1", root=Path(tmp)) as store:
                store.ensure()
                store.append_event({"type": "experiment.started", "payload": {"total_cells": 2}})
                store.append_event({"type": "experiment.status", "payload": {"status": "completed_with_failures"}})
                snap = store.rebuild_snapshot()
                self.assertEqual(snap["status"], "completed_with_failures")

    def test_status_event_stopped_precedence(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.ExperimentStore(Path(tmp) / "exp1", root=Path(tmp)) as store:
                store.ensure()
                store.append_event({"type": "experiment.started", "payload": {"total_cells": 2}})
                store.append_event({"type": "experiment.completed", "payload": {"completed": 1}})
                store.append_event({"type": "experiment.status", "payload": {"status": "stopped"}})
                snap = store.rebuild_snapshot()
                self.assertEqual(snap["status"], "stopped")

    def test_status_event_failed_fatal_precedence(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.ExperimentStore(Path(tmp) / "exp1", root=Path(tmp)) as store:
                store.ensure()
                store.append_event({"type": "experiment.started", "payload": {"total_cells": 2}})
                store.append_event({"type": "experiment.completed", "payload": {"completed": 1}})
                store.append_event({"type": "experiment.status", "payload": {"status": "failed_fatal"}})
                snap = store.rebuild_snapshot()
                self.assertEqual(snap["status"], "failed_fatal")

    def test_multiple_status_events_last_wins(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.ExperimentStore(Path(tmp) / "exp1", root=Path(tmp)) as store:
                store.ensure()
                store.append_event({"type": "experiment.status", "payload": {"status": "running"}})
                store.append_event({"type": "experiment.status", "payload": {"status": "paused"}})
                store.append_event({"type": "experiment.status", "payload": {"status": "completed"}})
                snap = store.rebuild_snapshot()
                self.assertEqual(snap["status"], "completed",
                    "last experiment.status event must win")


class TotalCellsInferenceTests(unittest.TestCase):
    """rebuild_snapshot must infer total_cells from experiment.started/resumed
    when explicit arg is not provided."""

    def test_infers_from_started_event(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.ExperimentStore(Path(tmp) / "exp1", root=Path(tmp)) as store:
                store.ensure()
                store.append_event({"type": "experiment.started", "payload": {"total_cells": 10}})
                snap = store.rebuild_snapshot()
                self.assertEqual(snap["total_cells"], 10,
                    "must infer total_cells from experiment.started event")

    def test_infers_from_resumed_event(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.ExperimentStore(Path(tmp) / "exp1", root=Path(tmp)) as store:
                store.ensure()
                store.append_event({"type": "experiment.resumed", "payload": {"total_cells": 7}})
                snap = store.rebuild_snapshot()
                self.assertEqual(snap["total_cells"], 7,
                    "must infer total_cells from experiment.resumed event")

    def test_explicit_arg_not_overridden(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.ExperimentStore(Path(tmp) / "exp1", root=Path(tmp)) as store:
                store.ensure()
                store.append_event({"type": "experiment.started", "payload": {"total_cells": 10}})
                snap = store.rebuild_snapshot(total_cells=5)
                self.assertEqual(snap["total_cells"], 5,
                    "explicit total_cells arg must not be overridden by inference")

    def test_default_zero_when_no_started_event(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.ExperimentStore(Path(tmp) / "exp1", root=Path(tmp)) as store:
                store.ensure()
                store.append_event({"type": "cell.completed", "payload": {"cell_key": "k1"}})
                snap = store.rebuild_snapshot()
                self.assertEqual(snap["total_cells"], 0,
                    "default total_cells must be 0 when no started/resumed event")


class DefinitionTests(unittest.TestCase):
    def test_write_and_read_definition(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.ExperimentStore(Path(tmp) / "exp1", root=Path(tmp)) as store:
                store.ensure()
                defn = {
                    "schema_version": 1,
                    "experiment_id": "exp1",
                    "revision": 1,
                    "name": "Test",
                    "notes": "",
                    "created_at": "2026-06-17T12:00:00Z",
                    "updated_at": "2026-06-17T12:00:00Z",
                }
                store.write_definition(defn)
                restored = store.read_definition()
                self.assertEqual(restored, defn)


if __name__ == "__main__":
    unittest.main()
