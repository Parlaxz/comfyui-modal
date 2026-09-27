"""Focused tests for runtime_state: atomic writes, serialized commits, fake volumes, mounted volume."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest

from comfymodal_runtime.runtime_state import (
    CommitCoordinator,
    CommitMetrics,
    FakeVolume,
    MountedStateVolume,
    StateVolume,
)


class TestFakeVolume(unittest.TestCase):
    """FakeVolume tracks metrics and stores bytes in memory."""

    def test_write_and_read(self):
        fv = FakeVolume()
        fv.write_bytes("state.json", b'{"a": 1}')
        self.assertEqual(fv.read_bytes("state.json"), b'{"a": 1}')

    def test_read_nonexistent_returns_empty(self):
        fv = FakeVolume()
        self.assertEqual(fv.read_bytes("missing"), b"")

    def test_exists(self):
        fv = FakeVolume()
        self.assertFalse(fv.exists("state.json"))
        fv.write_bytes("state.json", b"data")
        self.assertTrue(fv.exists("state.json"))

    def test_write_count(self):
        fv = FakeVolume()
        fv.write_bytes("a.json", b"1")
        fv.write_bytes("b.json", b"2")
        self.assertEqual(fv.write_count, 2)

    def test_read_count(self):
        fv = FakeVolume()
        fv.write_bytes("s.json", b"data")
        fv.read_bytes("s.json")
        fv.read_bytes("s.json")
        self.assertEqual(fv.read_count, 2)

    def test_write_bytes_total(self):
        fv = FakeVolume()
        fv.write_bytes("a.json", b"hello")
        fv.write_bytes("b.json", b"world")
        self.assertEqual(fv.write_bytes_total, 10)

    def test_file_count(self):
        fv = FakeVolume()
        fv.write_bytes("a.json", b"1")
        fv.write_bytes("b.json", b"2")
        self.assertEqual(fv.file_count, 2)

    def test_protocol_check(self):
        self.assertIsInstance(FakeVolume(), StateVolume)

    def test_remove_removes_file(self):
        fv = FakeVolume()
        fv.write_bytes("state.json", b"data")
        self.assertTrue(fv.exists("state.json"))
        fv.remove("state.json")
        self.assertFalse(fv.exists("state.json"))

    def test_remove_nonexistent_does_not_raise(self):
        fv = FakeVolume()
        fv.remove("nonexistent.json")  # should not raise

    def test_commit_increments_count(self):
        fv = FakeVolume()
        self.assertEqual(fv.commit_count, 0)
        fv.commit()
        self.assertEqual(fv.commit_count, 1)
        fv.commit()
        self.assertEqual(fv.commit_count, 2)


class TestMountedStateVolume(unittest.TestCase):
    """MountedStateVolume uses real filesystem with temp+rename for atomicity."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.volume = MountedStateVolume(root=self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_write_and_read(self):
        self.volume.write_bytes("state.json", b'{"a": 1}')
        self.assertEqual(self.volume.read_bytes("state.json"), b'{"a": 1}')

    def test_exists(self):
        self.assertFalse(self.volume.exists("state.json"))
        self.volume.write_bytes("state.json", b"data")
        self.assertTrue(self.volume.exists("state.json"))

    def test_atomic_write_no_orphan_temp(self):
        """After write_bytes, no .tmp file remains at the final path."""
        self.volume.write_bytes("state.json", b"hello")
        # Final file should exist
        self.assertTrue(self.volume.exists("state.json"))
        # No temp file with the .tmp. prefix should remain
        temp_glob = [
            f for f in os.listdir(self.tmpdir.name)
            if "state.json.tmp." in f
        ]
        self.assertEqual(len(temp_glob), 0,
                         "Temp file should be cleaned up after atomic rename")

    def test_remove_cleans_final_and_orphan_temp(self):
        """remove() should delete both final and any orphan temp file."""
        self.volume.write_bytes("state.json", b"data")
        # Manually create an orphan temp file using the volume's temp pattern
        temp_path = self.volume._temp_path("state.json")
        with open(temp_path, "wb") as f:
            f.write(b"orphan")
        self.assertTrue(os.path.exists(temp_path),
                        "Orphan temp should exist before remove")
        self.volume.remove("state.json")
        self.assertFalse(self.volume.exists("state.json"))
        self.assertFalse(os.path.exists(temp_path),
                         "Orphan temp should be cleaned up by remove")

    def test_protocol_check(self):
        self.assertIsInstance(self.volume, StateVolume)

    def test_write_count(self):
        self.volume.write_bytes("a.json", b"1")
        self.volume.write_bytes("b.json", b"2")
        self.assertEqual(self.volume.write_count, 2)

    def test_read_count(self):
        self.volume.write_bytes("s.json", b"data")
        self.volume.read_bytes("s.json")
        self.volume.read_bytes("s.json")
        self.assertEqual(self.volume.read_count, 2)

    def test_commit_increments_commit_count(self):
        self.volume.write_bytes("s.json", b"data")
        self.assertEqual(self.volume.commit_count, 0)
        self.volume.commit()
        self.assertEqual(self.volume.commit_count, 1)
        self.volume.commit()
        self.assertEqual(self.volume.commit_count, 2)

    def test_write_bytes_total(self):
        self.volume.write_bytes("a.json", b"hello")
        self.volume.write_bytes("b.json", b"world")
        self.assertEqual(self.volume.write_bytes_total, 10)


class TestCommitCoordinatorBasic(unittest.TestCase):
    """Basic write/commit/read cycle without concurrency."""

    def setUp(self):
        self.volume = FakeVolume()
        self.coord = CommitCoordinator(self.volume, state_path="state.json")

    def test_initial_state(self):
        self.assertEqual(self.coord.dirty_generation, -1)
        self.assertEqual(self.coord.committed_generation, -1)
        self.assertFalse(self.coord.in_flight)

    def test_write_state_sets_dirty_generation(self):
        self.coord.write_state(1, {"key": "value"})
        self.assertEqual(self.coord.dirty_generation, 1)
        self.assertEqual(self.coord.committed_generation, -1)

    def test_write_state_persists_to_volume(self):
        self.coord.write_state(1, {"key": "value"})
        self.assertTrue(self.volume.exists("state.json"))
        raw = self.volume.read_bytes("state.json")
        data = json.loads(raw.decode("utf-8"))
        self.assertEqual(data["key"], "value")
        self.assertEqual(data["_generation"], 1)

    def test_commit_succeeds(self):
        self.coord.write_state(1, {"key": "value"})
        result = self.coord.commit(1)
        self.assertTrue(result)
        self.assertEqual(self.coord.committed_generation, 1)

    def test_commit_wrong_generation_returns_false(self):
        self.coord.write_state(1, {"key": "value"})
        result = self.coord.commit(2)
        self.assertFalse(result)
        self.assertEqual(self.coord.committed_generation, -1)

    def test_read_state_returns_none_when_missing(self):
        self.assertIsNone(self.coord.read_state())

    def test_read_state_after_write(self):
        self.coord.write_state(1, {"key": "value"})
        state = self.coord.read_state()
        self.assertIsNotNone(state)
        if state:
            self.assertEqual(state["key"], "value")

    def test_metrics_after_write(self):
        self.coord.write_state(1, {"x": "y"})
        m = self.coord.metrics
        self.assertEqual(m.write_count, 1)
        self.assertGreater(m.total_write_bytes, 0)
        self.assertEqual(m.commit_count, 0)

    def test_metrics_after_commit(self):
        self.coord.write_state(1, {"x": "y"})
        self.coord.commit(1)
        m = self.coord.metrics
        self.assertEqual(m.write_count, 1)
        self.assertEqual(m.commit_count, 1)
        self.assertGreater(m.last_commit_ms, 0)

    def test_multiple_writes_and_commits(self):
        for gen in range(1, 4):
            self.coord.write_state(gen, {"gen": gen})
            self.coord.commit(gen)
        self.assertEqual(self.coord.committed_generation, 3)
        m = self.coord.metrics
        self.assertEqual(m.write_count, 3)
        self.assertEqual(m.commit_count, 3)

    def test_write_state_cleans_orphan_temp(self):
        """write_state cleans up orphan temp before writing."""
        # Simulate an orphan temp file
        temp = self.coord._temp_path()
        self.volume.write_bytes(temp, b"orphan")
        self.assertTrue(self.volume.exists(temp))
        # Now write state — should clean the temp
        self.coord.write_state(1, {"a": 1})
        self.assertFalse(
            self.volume.exists(temp),
            "Orphan temp should have been removed",
        )


class TestCommitCoordinatorAtomicity(unittest.TestCase):
    """Writes are atomic (data is never partially written)."""

    def test_full_data_is_written(self):
        volume = FakeVolume()
        coord = CommitCoordinator(volume)
        large = {"data": "x" * 10000, "nested": {"a": [1, 2, 3]}}
        coord.write_state(1, large)
        state = coord.read_state()
        self.assertIsNotNone(state)
        if state:
            self.assertEqual(state["data"], "x" * 10000)
            self.assertEqual(state["nested"]["a"], [1, 2, 3])

    def test_write_state_no_temp_file_created(self):
        """write_state now writes only through the volume; no intermediate temp."""
        volume = FakeVolume()
        coord = CommitCoordinator(volume, state_path="my_state.json")
        coord.write_state(1, {"a": 1})
        # Only the final path should exist
        self.assertTrue(volume.exists("my_state.json"))
        # No temp files should exist
        temp_files = [k for k in volume._files if ".tmp." in k]
        self.assertEqual(
            len(temp_files), 0,
            "No temp files should remain after write_state",
        )


class TestCommitInvokesVolumeCommit(unittest.TestCase):
    """CommitCoordinator.commit() calls volume.commit()."""

    def test_commit_calls_volume_commit(self):
        volume = FakeVolume()
        coord = CommitCoordinator(volume)
        coord.write_state(1, {"a": 1})
        self.assertEqual(volume.commit_count, 0)
        coord.commit(1)
        # The volume.commit() should have been called
        self.assertEqual(
            volume.commit_count, 1,
            "volume.commit() should be invoked during coordinator.commit()",
        )

    def test_commit_with_mounted_volume(self):
        """Full cycle with MountedStateVolume."""
        with tempfile.TemporaryDirectory() as tmp:
            volume = MountedStateVolume(root=tmp)
            coord = CommitCoordinator(volume, state_path="restore.json")
            coord.write_state(5, {"key": "value"})
            result = coord.commit(5)
            self.assertTrue(result)
            self.assertEqual(coord.committed_generation, 5)
            self.assertEqual(volume.commit_count, 1)
            # Verify data survives on real filesystem
            final_path = os.path.join(tmp, "restore.json")
            self.assertTrue(os.path.isfile(final_path))
            with open(final_path, "rb") as f:
                data = json.loads(f.read().decode("utf-8"))
                self.assertEqual(data["key"], "value")
                self.assertEqual(data["_generation"], 5)


class _SignaledVolume(FakeVolume):
    """FakeVolume that signals an event when ``read_bytes`` is entered,
    then inserts a delay so the commit is guaranteed in-flight."""

    SIGNAL_DELAY_S = 0.05

    def __init__(self) -> None:
        super().__init__()
        self.read_started = threading.Event()

    def read_bytes(self, path: str) -> bytes:
        self.read_started.set()
        time.sleep(self.SIGNAL_DELAY_S)
        return super().read_bytes(path)


class TestCommitCoordinatorConcurrency(unittest.TestCase):
    """Serialized commit behavior under concurrent access."""

    def test_concurrent_write_and_commit_triggers_follow_up(self):
        """When writes arrive during commit, exactly one follow-up runs."""
        volume = _SignaledVolume()
        coord = CommitCoordinator(volume)

        # Write gen 1
        coord.write_state(1, {"gen": 1})
        self.assertEqual(coord.dirty_generation, 1)

        # Start commit in background thread; wait for it to be in-flight
        t1 = threading.Thread(target=lambda: coord.commit(1))
        t1.start()
        volume.read_started.wait()  # commit holds in_flight=True

        # Write arrives during the commit
        coord.write_state(2, {"gen": 2})

        t1.join()

        # The post-commit follow-up should have committed gen 2
        self.assertEqual(
            coord.committed_generation, 2,
            "Follow-up commit should have committed gen 2",
        )
        m = coord.metrics
        self.assertEqual(m.follow_up_count, 1,
                          "Exactly one follow-up should occur")

    def test_concurrent_commit_serialization(self):
        """Two concurrent commits: only one runs, the other returns False."""
        volume = _SignaledVolume()
        coord = CommitCoordinator(volume)
        coord.write_state(1, {"gen": 1})

        results: list[bool] = []
        lock = threading.Lock()
        barrier = threading.Barrier(2, timeout=5)

        def do_commit():
            barrier.wait()
            result = coord.commit(1)
            with lock:
                results.append(result)

        t1 = threading.Thread(target=do_commit)
        t2 = threading.Thread(target=do_commit)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Exactly one commit should have succeeded, the other returned False
        self.assertEqual(len(results), 2)
        true_count = sum(1 for r in results if r)
        self.assertEqual(true_count, 1,
                          "Only one commit call should perform the commit")

    def test_follow_up_does_not_exceed_one(self):
        """Multiple writes during commit trigger exactly one follow-up."""
        volume = _SignaledVolume()
        coord = CommitCoordinator(volume)
        coord.write_state(1, {"gen": 1})

        # Start commit in background thread; wait for it to be in-flight
        t_commit = threading.Thread(target=lambda: coord.commit(1))
        t_commit.start()
        volume.read_started.wait()  # commit holds in_flight=True

        # Multiple writes arrive during the commit
        coord.write_state(2, {"gen": 2})
        coord.write_state(3, {"gen": 3})

        t_commit.join()

        # committed_generation should be 3 (latest dirty gen after follow-up)
        self.assertEqual(
            coord.committed_generation, 3,
            "Should have committed gen 3 via follow-up",
        )
        m = coord.metrics
        self.assertEqual(m.follow_up_count, 1,
                          "Exactly one follow-up should occur")


class TestCommitMetrics(unittest.TestCase):
    """CommitMetrics dataclass."""

    def test_defaults(self):
        m = CommitMetrics()
        self.assertEqual(m.write_count, 0)
        self.assertEqual(m.commit_count, 0)
        self.assertEqual(m.follow_up_count, 0)
        self.assertEqual(m.total_write_bytes, 0)
        self.assertEqual(m.last_commit_ms, 0.0)


if __name__ == "__main__":
    unittest.main()
