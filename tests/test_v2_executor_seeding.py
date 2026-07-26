"""Focused behavior tests for Phase-1 V2 acceptance-mode strictness.

Proves:
  (a) Missing seed evidence fails fresh request.
  (b) Correct seed evidence with required roles/decisions passes.
  (c) Conflicting/wrong decisions, missing roles, and missing timing
      fields produce appropriate failures.

  No source/AST presence tests.  Uses only _check_acceptance from
  tools.benchmark_v2_direct.
"""

from __future__ import annotations

import unittest
from typing import Any


# ── Minimal event factory ──────────────────────────────────────────────


def _ev(name: str, **kw: Any) -> dict[str, Any]:
    ev: dict[str, Any] = {"name": name, "monotonic_ns": 1000, "wall_unix_ns": 1000}
    if "metadata" in kw:
        ev["metadata"] = kw["metadata"]
    if "mono_ns" in kw:
        ev["monotonic_ns"] = kw["mono_ns"]
    if "wall_ns" in kw:
        ev["wall_unix_ns"] = kw["wall_ns"]
    return ev


def _mkresult(events: list[dict[str, Any]], **kw: Any) -> dict[str, Any]:
    r: dict[str, Any] = {
        "trace": {"events": list(events)},
        "images": [],
        "output_attempts": [],
        "identity": {"restored_instance_id": "inst_X", "restore_count": 1, "request_count": 1},
    }
    if "timing_overrides" in kw:
        r.update(kw["timing_overrides"])
    return r


_ACCEPTANCE: Any = None


def _check(run_label: str, result: dict[str, Any], timing: dict[str, Any],
           **kwargs: Any) -> list[str]:
    global _ACCEPTANCE
    if _ACCEPTANCE is None:
        from tools.benchmark_v2_direct import _check_acceptance as _ca
        _ACCEPTANCE = _ca
    return _ACCEPTANCE(
        run_label, result, timing, result.get("images", []), [],
        is_fresh=True,
        expected_restore_count=kwargs.get("expected_restore_count", 1),
        expected_request_count=kwargs.get("expected_request_count", 1),
    )


def _timing_with(**kw: Any) -> dict[str, Any]:
    t: dict[str, Any] = {
        "wall_ms": 3000.0,
        "restore_total_ms": 3500.0,
        "dispatch_to_modal_entry_ms": 1500.0,
        "method_entry_to_durable_result_ms": 8000.0,
        "trigger_to_durable_result_ms": 9500.0,
        "exec_start_to_cached_ms": 200.0,
        "sampler_node_to_sampler_start_ms": 400.0,
        "sampling_ms": 5000.0,
        "vae_decode_ms": 3000.0,
        "output_encode_ms": 1000.0,
        "output_commit_ms": 500.0,
        "unet_demand_to_first_forward_ms": 150.0,
        "demand_start_present": 1,
    }
    t.update(kw)
    return t


def _min_seed_diag() -> dict[str, dict[str, str]]:
    return {
        "10": {"role": "unet", "decision": "seeded"},
        "20": {"role": "clip", "decision": "seeded"},
        "30": {"role": "vae", "decision": "missing_snapshot_output"},
    }


def _base_events() -> list[dict[str, Any]]:
    return [
        _ev("remote_method_entry", metadata={"request_id": "r",
             "restored_instance_id": "X", "restore_count": 1, "request_count": 1}),
        _ev("output_persist_end", mono_ns=5000000),
    ]


def _required_events() -> list[dict[str, Any]]:
    return [
        _ev("executor_loader_cache_seed_end",
            metadata={"diagnostics": _min_seed_diag()}),
        _ev("prompt_executor_milestones",
            metadata={"execution_start_to_cached_ms": 200.0}),
        _ev("pre_sampler_stages",
            metadata={"sampler_node_to_sampler_start_ms": 400.0}),
        _ev("sampling_start", mono_ns=3000000),
        _ev("sampling_end", mono_ns=8000000, metadata={"steps": 8}),
        _ev("vae_decode_start", mono_ns=9000000),
        _ev("vae_decode_end", mono_ns=12000000),
    ]


# ═══════════════════════════════════════════════════════════════════════
# Strictness tests
# ═══════════════════════════════════════════════════════════════════════


class TestCheckAcceptanceFreshStrictness(unittest.TestCase):
    """Validate _check_acceptance enforces seed evidence + timing presence
    for fresh requests."""

    # ── Seed evidence ─────────────────────────────────────────────

    def test_missing_seed_event_fails(self):
        result = _mkresult(_base_events() + _required_events()[1:])  # no seed event
        failures = _check("EV", result, _timing_with())
        self.assertTrue(
            any("seed_loader_cache_signatures evidence missing" in f for f in failures),
            f"expected seed evidence failure, got: {failures}",
        )

    def test_seed_event_present_passes(self):
        result = _mkresult(_base_events() + _required_events())
        failures = _check("EV", result, _timing_with())
        seed_fails = [f for f in failures if "seed" in f.lower() or "unet" in f.lower()
                      or "clip" in f.lower() or "vae" in f.lower()]
        self.assertEqual(seed_fails, [], f"unexpected seed/role failures: {failures}")

    def test_wrong_unet_decision_fails(self):
        diag = _min_seed_diag()
        diag["10"]["decision"] = "identity_mismatch"
        events = _base_events() + [ev for ev in _required_events()]
        events[1] = _ev("executor_loader_cache_seed_end",
                        metadata={"diagnostics": diag})
        result = _mkresult(events)
        failures = _check("WR", result, _timing_with())
        self.assertTrue(
            any("unet" in f and "identity_mismatch" in f for f in failures),
            f"expected unet identity_mismatch failure, got: {failures}",
        )

    def test_missing_role_in_seed_fails(self):
        diag = {"10": {"role": "unet", "decision": "seeded"},
                "30": {"role": "vae", "decision": "missing_snapshot_output"}}
        events = _base_events() + [ev for ev in _required_events()]
        events[1] = _ev("executor_loader_cache_seed_end",
                        metadata={"diagnostics": diag})
        result = _mkresult(events)
        failures = _check("MR", result, _timing_with())
        self.assertTrue(
            any("no clip decision" in f for f in failures),
            f"expected missing clip role failure, got: {failures}",
        )

    def test_conflicting_role_decisions_fails(self):
        diag = {
            "10": {"role": "unet", "decision": "seeded"},
            "11": {"role": "unet", "decision": "identity_mismatch"},
            "20": {"role": "clip", "decision": "seeded"},
            "30": {"role": "vae", "decision": "missing_snapshot_output"},
        }
        events = _base_events() + [ev for ev in _required_events()]
        events[1] = _ev("executor_loader_cache_seed_end",
                        metadata={"diagnostics": diag})
        result = _mkresult(events)
        failures = _check("CR", result, _timing_with())
        self.assertTrue(
            any("conflicting unet" in f for f in failures),
            f"expected conflicting unet failure, got: {failures}",
        )

    # ── Timing presence ───────────────────────────────────────────

    def test_missing_exec_start_to_cached_fails(self):
        result = _mkresult(_base_events() + [ev for ev in _required_events()
                           if ev["name"] != "prompt_executor_milestones"])
        failures = _check("EC", result, _timing_with(exec_start_to_cached_ms=None))
        self.assertTrue(
            any("exec_start_to_cached_ms" in f and "missing/absent" in f for f in failures),
            f"expected exec_start_to_cached_ms failure, got: {failures}",
        )

    def test_missing_sampler_node_to_sampler_start_fails(self):
        result = _mkresult(_base_events() + [ev for ev in _required_events()
                           if ev["name"] != "pre_sampler_stages"])
        failures = _check("SN", result, _timing_with(sampler_node_to_sampler_start_ms=None))
        self.assertTrue(
            any("sampler_node_to_sampler_start_ms" in f and "missing/absent" in f for f in failures),
            f"expected sampler_node_to_sampler_start_ms failure, got: {failures}",
        )

    # ── Sampling events ───────────────────────────────────────────

    def test_missing_sampling_start_fails(self):
        events = [ev for ev in _base_events() + _required_events()
                  if ev["name"] != "sampling_start"]
        result = _mkresult(events)
        failures = _check("MS", result, _timing_with())
        self.assertTrue(
            any("sampling_start event missing" in f for f in failures),
            f"expected sampling_start missing failure, got: {failures}",
        )

    def test_missing_sampling_end_fails(self):
        events = [ev for ev in _base_events() + _required_events()
                  if ev["name"] != "sampling_end"]
        result = _mkresult(events)
        failures = _check("ME", result, _timing_with())
        self.assertTrue(
            any("sampling_end event missing" in f for f in failures),
            f"expected sampling_end missing failure, got: {failures}",
        )

    def test_wrong_step_count_fails(self):
        events = _base_events() + _required_events()
        # Replace sampling_end with wrong steps
        for i, ev in enumerate(events):
            if ev["name"] == "sampling_end":
                events[i] = _ev("sampling_end", mono_ns=8000000, metadata={"steps": 20})
                break
        result = _mkresult(events)
        failures = _check("SC", result, _timing_with())
        self.assertTrue(
            any("steps=20" in f and "expected 8" in f for f in failures),
            f"expected step count failure, got: {failures}",
        )

    def test_missing_step_count_fails(self):
        events = _base_events() + _required_events()
        for i, ev in enumerate(events):
            if ev["name"] == "sampling_end":
                events[i] = _ev("sampling_end", mono_ns=8000000)  # no steps metadata
                break
        result = _mkresult(events)
        failures = _check("SC", result, _timing_with())
        self.assertTrue(
            any("steps not found" in f for f in failures),
            f"expected missing steps failure, got: {failures}",
        )

    def test_sampling_end_before_vae_decode_passes(self):
        result = _mkresult(_base_events() + _required_events())
        failures = _check("OR", result, _timing_with())
        order_fails = [f for f in failures if ">=" in f and "vae_decode" in f]
        self.assertEqual(order_fails, [], f"unexpected ordering failures: {failures}")

    def test_sampling_end_after_vae_decode_fails(self):
        events = _base_events() + _required_events()
        for i, ev in enumerate(events):
            if ev["name"] == "sampling_end":
                events[i] = _ev("sampling_end", mono_ns=10000000, metadata={"steps": 8})
                break
        result = _mkresult(events)
        failures = _check("OR", result, _timing_with())
        self.assertTrue(
            any(">=" in f and "vae_decode" in f for f in failures),
            f"expected ordering failure, got: {failures}",
        )


# ═══════════════════════════════════════════════════════════════════════
# CacheEntry output nesting tests (V2 executor seeding)
# ═══════════════════════════════════════════════════════════════════════


class TestSeedLoaderCacheSignatureOutputNesting(unittest.IsolatedAsyncioTestCase):
    """seed_loader_cache_signatures must normalize outputs to match
    merge_result_data shape: one list per output slot.

    ComfyUI's get_input_data (execution.py:180-183) indexes
    cached.outputs[output_index] and uses the result as a list
    (max_len_input = max(len(x) ...)).  Flat output lists like
    [clip_obj] break because CLIP objects are not iterable.

    The fix wraps each slot value in a list:
      scalar → [[scalar]]
      tuple  → [[v1], [v2], ...]

    NOTE: tuple/list tests are skipped because CheckpointLoader is
    unconditionally blocked at step-2 of seed_loader_cache_signatures
    and no other allowed loader produces multi-slot outputs.
    """

    # ── execution.CacheEntry shim ───────────────────────────────────
    # ComfyUI's execution.py cannot be imported in test env (it pulls
    # comfy_aimdo).  We inject a minimal fake so the runtime's
    # "from execution import CacheEntry" succeeds.

    _execution_shim: Any = None

    @classmethod
    def setUpClass(cls) -> None:
        from collections import namedtuple
        import sys

        if "execution" not in sys.modules:
            shim = type(sys)("execution")
            shim.CacheEntry = namedtuple("CacheEntry", ["ui", "outputs"])
            sys.modules["execution"] = shim
            cls._execution_shim = shim

    @classmethod
    def tearDownClass(cls) -> None:
        import sys
        if cls._execution_shim is not None:
            sys.modules.pop("execution", None)
            cls._execution_shim = None

    # ── helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _make_fake_executor():
        """Minimal executor with a dict-backed outputs cache."""

        class _CacheKeySet:
            def get_data_key(self, node_id: str) -> str:
                return f"test_key_{node_id}"

        class _OutputsCache:
            def __init__(self):
                self.cache_key_set = _CacheKeySet()
                self.initialized = True
                self._store: dict[str, Any] = {}

            async def set_prompt(self, *args: Any, **kwargs: Any) -> dict[str, str]:
                return {"prompt": "ok"}

            async def set(self, node_id: str, entry: Any) -> None:
                self._store[node_id] = entry

            async def get(self, node_id: str) -> Any:
                return self._store.get(node_id)

            async def delete(self, node_id: str) -> None:
                self._store.pop(node_id, None)

        class _Caches:
            outputs = _OutputsCache()

        executor = type("FakeExecutor", (), {"caches": _Caches()})()
        return executor

    @staticmethod
    def _make_state() -> Any:
        from comfymodal_runtime.contracts import SnapshotExecutionSeed
        from comfymodal_runtime.runtime_bootstrap import BootstrapState

        state = BootstrapState()
        state.snapshot_execution_seed = SnapshotExecutionSeed()
        return state

    @staticmethod
    def _make_scalar_output():
        """A non-iterable object simulating a CLIP model output."""
        return type("FakeCLIP", (), {"__repr__": lambda s: "FakeCLIP()"})()

    # ── scalar output tests ─────────────────────────────────────────

    async def test_scalar_output_is_nested(self):
        """A scalar (CLIP-like) output produces CacheEntry.outputs == [[obj]]."""
        state = self._make_state()
        executor = self._make_fake_executor()

        fake_obj = self._make_scalar_output()

        diag = await state.seed_loader_cache_signatures(
            executor=executor,
            loader_node_ids=["10"],
            loader_node_class_types={"10": "CLIPLoader"},
            loader_outputs={"10": fake_obj},
            request_model_key={},
            snapshot_model_key={},
            request_model_spec={},
            snapshot_model_spec={},
        )

        dec = diag.get("10", {}).get("decision", "?")
        self.assertEqual(
            dec, "seeded",
            f"expected decision='seeded', got '{dec}'; full diag={diag}",
        )
        entry = executor.caches.outputs._store.get("10")
        self.assertIsNotNone(entry, "expected CacheEntry to be stored")
        self.assertIsInstance(entry.outputs, list)
        self.assertEqual(len(entry.outputs), 1,
                         "expected exactly one output slot")
        slot0 = entry.outputs[0]
        self.assertIsInstance(slot0, list,
                              f"outputs[0] must be a list, got {type(slot0)}")
        self.assertIs(slot0[0], fake_obj,
                      "nested value must be the original object")

    async def test_scalar_output_iterability(self):
        """Output slot values must be iterable (simulating get_input_data)."""
        state = self._make_state()
        executor = self._make_fake_executor()

        fake_obj = self._make_scalar_output()
        diag = await state.seed_loader_cache_signatures(
            executor=executor,
            loader_node_ids=["10"],
            loader_node_class_types={"10": "CLIPLoader"},
            loader_outputs={"10": fake_obj},
            request_model_key={},
            snapshot_model_key={},
            request_model_spec={},
            snapshot_model_spec={},
        )

        dec = diag.get("10", {}).get("decision", "?")
        self.assertEqual(
            dec, "seeded",
            f"expected decision='seeded', got '{dec}'; full diag={diag}",
        )
        entry = executor.caches.outputs._store["10"]
        # Simulate what get_input_data does:
        #   obj = cached.outputs[output_index]
        #   input_data_all[x] = obj   # used by _async_map_node_over_list
        slot_val = entry.outputs[0]
        # Must be iterable for max(len(x) for x in input_data_all.values())
        iter(slot_val)  # raises TypeError if not iterable


if __name__ == "__main__":
    unittest.main()
