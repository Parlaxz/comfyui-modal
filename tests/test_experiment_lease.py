import importlib.util
import sys
import tempfile
import threading
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "experiment_lease.py"


def load_module():
    if not MODULE_PATH.exists():
        raise AssertionError("experiment_lease.py missing")
    spec = importlib.util.spec_from_file_location("experiment_lease", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class LeaseClaimTests(unittest.TestCase):
    def test_first_claim_assigns_generation_1(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.LeaseRegistry(Path(tmp) / "leases.db") as reg:
                lease = reg.claim("exp_a", "ck_1", "worker_1")
                self.assertEqual(lease["experiment_id"], "exp_a")
                self.assertEqual(lease["checkpoint_id"], "ck_1")
                self.assertEqual(lease["worker_invocation_id"], "worker_1")
                self.assertEqual(lease["lease_generation"], 1)
                self.assertEqual(lease["status"], "claimed")

    def test_second_claim_when_active_raises(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.LeaseRegistry(Path(tmp) / "leases.db") as reg:
                reg.claim("exp_a", "ck_1", "worker_1")
                with self.assertRaises(module.LeaseActiveError):
                    reg.claim("exp_a", "ck_1", "worker_2")

    def test_release_then_reclaim_increments_generation(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.LeaseRegistry(Path(tmp) / "leases.db") as reg:
                reg.claim("exp_a", "ck_1", "worker_1")
                reg.release("exp_a", "ck_1", "worker_1")
                lease = reg.claim("exp_a", "ck_1", "worker_2")
                self.assertEqual(lease["lease_generation"], 2)
                self.assertEqual(lease["worker_invocation_id"], "worker_2")

    def test_release_by_wrong_worker_raises(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.LeaseRegistry(Path(tmp) / "leases.db") as reg:
                reg.claim("exp_a", "ck_1", "worker_1")
                with self.assertRaises(module.LeaseOwnershipError):
                    reg.release("exp_a", "ck_1", "worker_2")

    def test_different_experiments_same_checkpoint_id(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.LeaseRegistry(Path(tmp) / "leases.db") as reg:
                a = reg.claim("exp_a", "ck_001", "w1")
                b = reg.claim("exp_b", "ck_001", "w2")  # should succeed
                self.assertEqual(a["lease_generation"], 1)
                self.assertEqual(b["lease_generation"], 1)

    def test_same_experiment_duplicate_claim_raises(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.LeaseRegistry(Path(tmp) / "leases.db") as reg:
                reg.claim("exp_a", "ck_001", "w1")
                with self.assertRaises(module.LeaseActiveError):
                    reg.claim("exp_a", "ck_001", "w2")


class StaleEventRejectionTests(unittest.TestCase):
    def test_old_generation_event_is_rejected(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.LeaseRegistry(Path(tmp) / "leases.db") as reg:
                reg.claim("exp_a", "ck_1", "worker_1")  # gen 1
                reg.release("exp_a", "ck_1", "worker_1")
                reg.claim("exp_a", "ck_1", "worker_2")  # gen 2
                with self.assertRaises(module.StaleEventError):
                    reg.accept_event("exp_a", "ck_1", lease_generation=1, attempt_id="a1")

    def test_current_generation_event_accepted(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.LeaseRegistry(Path(tmp) / "leases.db") as reg:
                reg.claim("exp_a", "ck_1", "worker_1")
                reg.accept_event("exp_a", "ck_1", lease_generation=1, attempt_id="a1")  # no raise

    def test_unknown_checkpoint_raises(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.LeaseRegistry(Path(tmp) / "leases.db") as reg:
                with self.assertRaises(module.UnknownCheckpointError):
                    reg.accept_event("exp_a", "ck_missing", lease_generation=1, attempt_id="a1")


class ConcurrencyTests(unittest.TestCase):
    def test_concurrent_claim_only_one_wins(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.LeaseRegistry(Path(tmp) / "leases.db") as reg:
                winners: list[str] = []
                losers: list[Exception] = []
                lock = threading.Lock()
                def attempt(worker: str):
                    try:
                        lease = reg.claim("exp_a", "ck_1", worker)
                        with lock:
                            winners.append(lease["worker_invocation_id"])
                    except module.LeaseActiveError as exc:
                        with lock:
                            losers.append(exc)
                    finally:
                        reg.close_thread()
                threads = [threading.Thread(target=attempt, args=(f"w{i}",)) for i in range(10)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join()
                self.assertEqual(len(winners), 1)
                self.assertEqual(len(losers), 9)


def _mp_worker(path_str: str, worker: str, result_path: str) -> None:
    """Top-level worker for cross-process lease test (must be picklable)."""
    import json as _json
    import importlib.util
    spec = importlib.util.spec_from_file_location("experiment_lease", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    try:
        with module.LeaseRegistry(Path(path_str)) as reg:
            lease = reg.claim("exp_a", "ck_x", worker)
        with open(result_path, "w", encoding="utf-8") as f:
            _json.dump({"worker": worker, "lease": lease}, f)
    except module.LeaseActiveError as exc:
        with open(result_path, "w", encoding="utf-8") as f:
            _json.dump({"worker": worker, "error": str(exc)}, f)


class CrossProcessTests(unittest.TestCase):
    """Two processes cannot both claim the same checkpoint."""

    def test_cross_process_claim_serialised(self):
        import multiprocessing as mp
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "leases.db"
            # Do NOT touch the DB in the parent — child processes will
            # create it on first connect. Pre-creating in the parent
            # sets WAL mode which holds a lock that prevents children
            # from initialising.
            ctx = mp.get_context("spawn")
            results_dir = Path(tmp) / "results"
            results_dir.mkdir()
            procs = [
                ctx.Process(target=_mp_worker, args=(str(db), f"w{i}", str(results_dir / f"r{i}.json")))
                for i in range(2)
            ]
            for p in procs:
                p.start()
            for p in procs:
                p.join()
            self.assertTrue(all(p.exitcode == 0 for p in procs), f"procs failed: {[p.exitcode for p in procs]}")
            winners = 0
            losers = 0
            for i in range(2):
                import json
                with open(results_dir / f"r{i}.json", "r", encoding="utf-8") as f:
                    d = json.load(f)
                if "lease" in d:
                    winners += 1
                else:
                    losers += 1
            self.assertEqual(winners, 1)
            self.assertEqual(losers, 1)


class ValidateAndAcceptTests(unittest.TestCase):
    """Phase 8: strict lease validation before terminal event persistence."""

    def test_validate_and_accept_rejects_old_generation(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.LeaseRegistry(Path(tmp) / "leases.db") as reg:
                reg.claim("exp_a", "ck_1", "worker_1")  # gen 1
                reg.release("exp_a", "ck_1", "worker_1")
                reg.claim("exp_a", "ck_1", "worker_2")  # gen 2
                with self.assertRaises(module.StaleEventError):
                    reg.validate_and_accept("exp_a", "ck_1", lease_generation=1,
                                            worker_invocation_id="worker_2",
                                            attempt_id="a1")

    def test_validate_and_accept_rejects_wrong_worker(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.LeaseRegistry(Path(tmp) / "leases.db") as reg:
                reg.claim("exp_a", "ck_1", "worker_1")
                with self.assertRaises(module.LeaseOwnershipError):
                    reg.validate_and_accept("exp_a", "ck_1", lease_generation=1,
                                            worker_invocation_id="worker_2",
                                            attempt_id="a1")

    def test_validate_and_accept_rejects_not_claimed(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.LeaseRegistry(Path(tmp) / "leases.db") as reg:
                reg.claim("exp_a", "ck_1", "worker_1")
                reg.release("exp_a", "ck_1", "worker_1")
                with self.assertRaises(module.LeaseError):
                    reg.validate_and_accept("exp_a", "ck_1", lease_generation=1,
                                            worker_invocation_id="worker_1",
                                            attempt_id="a1")

    def test_validate_and_accept_rejects_duplicate_attempt(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.LeaseRegistry(Path(tmp) / "leases.db") as reg:
                reg.claim("exp_a", "ck_1", "worker_1")
                reg.validate_and_accept("exp_a", "ck_1", lease_generation=1,
                                        worker_invocation_id="worker_1",
                                        attempt_id="a1")
                with self.assertRaises(module.LeaseError):
                    reg.validate_and_accept("exp_a", "ck_1", lease_generation=1,
                                            worker_invocation_id="worker_1",
                                            attempt_id="a1")

    def test_validate_and_accept_unknown_checkpoint(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.LeaseRegistry(Path(tmp) / "leases.db") as reg:
                with self.assertRaises(module.UnknownCheckpointError):
                    reg.validate_and_accept("exp_a", "ck_missing", lease_generation=1,
                                            worker_invocation_id="worker_1",
                                            attempt_id="a1")

    def test_validate_and_accept_success(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.LeaseRegistry(Path(tmp) / "leases.db") as reg:
                reg.claim("exp_a", "ck_1", "worker_1")
                # Must not raise
                reg.validate_and_accept("exp_a", "ck_1", lease_generation=1,
                                        worker_invocation_id="worker_1",
                                        attempt_id="a1")
                # Verify the attempt was recorded
                snap = reg.snapshot("exp_a")
                self.assertIn("a1", snap["leases"]["ck_1"]["accepted_attempts"])


class LeaseInvalidateTests(unittest.TestCase):
    """Lease invalidation (cancellation boundary) — Task 3."""

    def test_invalidate_claimed_lease(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.LeaseRegistry(Path(tmp) / "leases.db") as reg:
                reg.claim("exp_a", "ck_1", "worker_1")  # gen 1
                result = reg.invalidate("exp_a", "ck_1")
                self.assertEqual(result["status"], "cancelling")
                self.assertEqual(result["lease_generation"], 2)

    def test_invalidate_no_lease_raises(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.LeaseRegistry(Path(tmp) / "leases.db") as reg:
                with self.assertRaises(module.UnknownCheckpointError):
                    reg.invalidate("exp_a", "ck_missing")

    def test_invalidate_released_lease_raises(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.LeaseRegistry(Path(tmp) / "leases.db") as reg:
                reg.claim("exp_a", "ck_1", "worker_1")
                reg.release("exp_a", "ck_1", "worker_1")
                with self.assertRaises(module.LeaseError):
                    reg.invalidate("exp_a", "ck_1")

    def test_invalidate_already_cancelling_is_idempotent(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.LeaseRegistry(Path(tmp) / "leases.db") as reg:
                reg.claim("exp_a", "ck_1", "worker_1")  # gen 1
                reg.invalidate("exp_a", "ck_1")          # gen 2, cancelling
                result = reg.invalidate("exp_a", "ck_1")  # idempotent
                self.assertEqual(result["status"], "cancelling")
                self.assertEqual(result["lease_generation"], 2)  # no second bump

    def test_completion_before_invalidation_succeeds(self):
        """Completion before cancellation boundary is accepted."""
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.LeaseRegistry(Path(tmp) / "leases.db") as reg:
                reg.claim("exp_a", "ck_1", "worker_1")  # gen 1
                # Validate before invalidation → succeeds
                reg.validate_and_accept("exp_a", "ck_1", lease_generation=1,
                                        worker_invocation_id="worker_1",
                                        attempt_id="a1")
                snap = reg.snapshot("exp_a")
                self.assertIn("a1", snap["leases"]["ck_1"]["accepted_attempts"])

    def test_completion_after_invalidation_old_gen_fails(self):
        """Completion after cancellation boundary with old generation is rejected."""
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.LeaseRegistry(Path(tmp) / "leases.db") as reg:
                reg.claim("exp_a", "ck_1", "worker_1")  # gen 1
                reg.invalidate("exp_a", "ck_1")          # gen 2, cancelling
                # Old generation event → rejected (status check fires before
                # gen check, so accept either StaleEventError or LeaseError)
                with self.assertRaises((module.StaleEventError, module.LeaseError)):
                    reg.validate_and_accept("exp_a", "ck_1", lease_generation=1,
                                            worker_invocation_id="worker_1",
                                            attempt_id="a1")

    def test_completion_after_invalidation_new_gen_fails(self):
        """Completion after cancellation boundary with new gen is rejected
        because status is 'cancelling', not 'claimed'."""
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.LeaseRegistry(Path(tmp) / "leases.db") as reg:
                reg.claim("exp_a", "ck_1", "worker_1")  # gen 1
                reg.invalidate("exp_a", "ck_1")          # gen 2, cancelling
                # New generation event → CancellationBoundary (status is not claimed)
                with self.assertRaises((module.LeaseError, module.CancellationBoundary)) as ctx:
                    reg.validate_and_accept("exp_a", "ck_1", lease_generation=2,
                                            worker_invocation_id="worker_1",
                                            attempt_id="a1")
                # May be CancellationBoundary or generic LeaseError depending on check order

    def test_claim_after_invalidate_works(self):
        """After invalidation, a new worker can claim the checkpoint."""
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.LeaseRegistry(Path(tmp) / "leases.db") as reg:
                reg.claim("exp_a", "ck_1", "worker_1")  # gen 1
                reg.invalidate("exp_a", "ck_1")          # gen 2, cancelling
                # Claim from a new worker — should succeed (cancelling is reclaimable)
                lease = reg.claim("exp_a", "ck_1", "worker_2")  # gen 3
                self.assertEqual(lease["lease_generation"], 3)
                self.assertEqual(lease["status"], "claimed")
                self.assertEqual(lease["worker_invocation_id"], "worker_2")

    def test_release_after_invalidate_by_owner_succeeds(self):
        """The original owner can release a cancelling lease."""
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.LeaseRegistry(Path(tmp) / "leases.db") as reg:
                reg.claim("exp_a", "ck_1", "worker_1")  # gen 1
                reg.invalidate("exp_a", "ck_1")          # gen 2, cancelling
                # Owner can still release
                reg.release("exp_a", "ck_1", "worker_1")  # no raise
                snap = reg.snapshot("exp_a")
                self.assertEqual(snap["leases"]["ck_1"]["status"], "released")

    def test_release_cancelling_wrong_owner_raises(self):
        """Non-owner cannot release a cancelling lease."""
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.LeaseRegistry(Path(tmp) / "leases.db") as reg:
                reg.claim("exp_a", "ck_1", "worker_1")
                reg.invalidate("exp_a", "ck_1")
                with self.assertRaises(module.LeaseOwnershipError):
                    reg.release("exp_a", "ck_1", "worker_999")


class AssetRegistryTests(unittest.TestCase):
    """Phase 10: exact asset registry via LeaseRegistry."""

    def test_register_and_resolve_asset(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.LeaseRegistry(Path(tmp) / "leases.db") as reg:
                reg.register_asset(
                    asset_id="ast_001",
                    experiment_id="exp_1",
                    cell_key="cell_1",
                    attempt_id="a1",
                    variant="original",
                    path="/tmp/test.png",
                    mime_type="image/png",
                    byte_size=1024,
                    content_hash="abc123",
                )
                record = reg.resolve_asset("ast_001")
                self.assertIsNotNone(record)
                self.assertEqual(record["asset_id"], "ast_001")
                self.assertEqual(record["experiment_id"], "exp_1")
                self.assertEqual(record["cell_key"], "cell_1")
                self.assertEqual(record["variant"], "original")
                self.assertEqual(record["mime_type"], "image/png")

    def test_resolve_nonexistent_asset(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.LeaseRegistry(Path(tmp) / "leases.db") as reg:
                record = reg.resolve_asset("nonexistent")
                self.assertIsNone(record)

    def test_list_assets_for_experiment(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.LeaseRegistry(Path(tmp) / "leases.db") as reg:
                reg.register_asset("a1", "exp_1", "c1", "a1", "original", "/tmp/a1.png", "image/png")
                reg.register_asset("a2", "exp_1", "c2", "a2", "original", "/tmp/a2.png", "image/png")
                reg.register_asset("b1", "exp_2", "c1", "a1", "original", "/tmp/b1.png", "image/png")
                assets = reg.list_assets_for_experiment("exp_1")
                self.assertEqual(len(assets), 2)
                asset_ids = {a["asset_id"] for a in assets}
                self.assertIn("a1", asset_ids)
                self.assertIn("a2", asset_ids)
                self.assertNotIn("b1", asset_ids)

    def test_list_assets_for_cell(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.LeaseRegistry(Path(tmp) / "leases.db") as reg:
                reg.register_asset("a1", "exp_1", "cell_A", "a1", "original", "/tmp/a1.png", "image/png")
                reg.register_asset("a2", "exp_1", "cell_B", "a1", "original", "/tmp/a2.png", "image/png")
                reg.register_asset("a3", "exp_2", "cell_A", "a2", "original", "/tmp/a3.png", "image/png")
                assets = reg.list_assets_for_cell("cell_A")
                self.assertEqual(len(assets), 2)
                assets_filtered = reg.list_assets_for_cell("cell_A", experiment_id="exp_1")
                self.assertEqual(len(assets_filtered), 1)

    def test_register_asset_ignores_duplicate(self):
        """B3: INSERT OR IGNORE means the first write for an asset_id wins."""
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.LeaseRegistry(Path(tmp) / "leases.db") as reg:
                reg.register_asset("a1", "exp_1", "c1", "a1", "original", "/tmp/old.png", "image/png")
                reg.register_asset("a1", "exp_1", "c1", "a1", "original", "/tmp/new.png", "image/jpeg")
                record = reg.resolve_asset("a1")
                self.assertEqual(record["path"], "/tmp/old.png",
                    "INSERT OR IGNORE: first write should win")
                self.assertEqual(record["mime_type"], "image/png",
                    "INSERT OR IGNORE: first write should win")


class CancellationBoundaryTests(unittest.TestCase):
    """A2: CancellationBoundary error and stricter invalidate mode."""

    def test_cancellation_boundary_error_defined(self):
        """CancellationBoundary error class exists."""
        module = load_module()
        self.assertTrue(
            hasattr(module, "CancellationBoundary"),
            "CancellationBoundary error class must be defined",
        )

    def test_cancellation_boundary_is_lease_error(self):
        """CancellationBoundary is a subclass of LeaseError."""
        module = load_module()
        self.assertTrue(issubclass(module.CancellationBoundary, module.LeaseError))

    def test_invalidate_clears_accepted_attempts(self):
        """invalidate with clear_attempts=True wipes accepted_attempts."""
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.LeaseRegistry(Path(tmp) / "leases.db") as reg:
                reg.claim("exp_a", "ck_1", "worker_1")  # gen 1
                reg.validate_and_accept("exp_a", "ck_1", lease_generation=1,
                                        worker_invocation_id="worker_1",
                                        attempt_id="a1")
                snap = reg.snapshot("exp_a")
                self.assertIn("a1", snap["leases"]["ck_1"]["accepted_attempts"])
                # Invalidate with clear_attempts
                reg.invalidate("exp_a", "ck_1", clear_attempts=True)
                snap2 = reg.snapshot("exp_a")
                self.assertEqual(
                    snap2["leases"]["ck_1"]["accepted_attempts"], [],
                    "accepted_attempts must be cleared after invalidate with clear_attempts=True"
                )

    def test_validate_after_invalidate_raises_cancellation_boundary(self):
        """validate_and_accept after invalidate raises CancellationBoundary,
        not a generic error."""
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.LeaseRegistry(Path(tmp) / "leases.db") as reg:
                reg.claim("exp_a", "ck_1", "worker_1")  # gen 1
                reg.invalidate("exp_a", "ck_1")          # gen 2, cancelling
                with self.assertRaises(module.CancellationBoundary):
                    reg.validate_and_accept("exp_a", "ck_1", lease_generation=1,
                                            worker_invocation_id="worker_1",
                                            attempt_id="a1")

    def test_validate_after_invalidate_new_gen_raises_cancellation_boundary(self):
        """Even with bumped generation, validate_and_accept after invalidate
        raises CancellationBoundary because status is not 'claimed'."""
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.LeaseRegistry(Path(tmp) / "leases.db") as reg:
                reg.claim("exp_a", "ck_1", "worker_1")  # gen 1
                reg.invalidate("exp_a", "ck_1")          # gen 2, cancelling
                with self.assertRaises(module.CancellationBoundary):
                    reg.validate_and_accept("exp_a", "ck_1", lease_generation=2,
                                            worker_invocation_id="worker_1",
                                            attempt_id="a1")

    def test_invalidate_clears_attempts_on_new_claim(self):
        """After invalidate+clear_attempts, a new claim starts with fresh
        accepted_attempts."""
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with module.LeaseRegistry(Path(tmp) / "leases.db") as reg:
                reg.claim("exp_a", "ck_1", "worker_1")
                reg.validate_and_accept("exp_a", "ck_1", lease_generation=1,
                                        worker_invocation_id="worker_1",
                                        attempt_id="a1")
                reg.invalidate("exp_a", "ck_1", clear_attempts=True)
                reg.claim("exp_a", "ck_1", "worker_2")
                snap = reg.snapshot("exp_a")
                self.assertEqual(
                    snap["leases"]["ck_1"]["accepted_attempts"], [],
                    "new claim after invalidate+clear must start with empty accepted_attempts"
                )


if __name__ == "__main__":
    unittest.main()
