"""Unit contracts for the VAE DynamicVRAM activation relocation.

The audit (``reports/P9_VAE_RESIDENCY_AUDIT.md``) classified the decode-time VAE
work as ``REQUIRED`` and the remedy as *relocation*, so these tests deliberately
do not assert that anything is skipped.  They assert that:

* the activation is still performed, through the canonical entry point;
* it is refused whenever the captured identity no longer holds, leaving the
  canonical decode-time call to run unchanged;
* it leaves ``current_loaded_models`` byte-identical to how it found it, which
  is what keeps the decode-time call from double-registering the patcher.

ComfyUI is not importable here, so ``comfy.model_management`` is replaced with a
faithful stand-in: it models the two upstream behaviours the design depends on,
namely the unconditional ``current_loaded_models.insert(0, loaded_model)`` at the
end of ``load_models_gpu`` and ``LoadedModel.model_unload`` nulling its
finalizer (which is why a duplicate entry raises at teardown).
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import pytest

from comfymodal_runtime import vae_dynamicvram_overlap as overlap


class _FakeFinalizer:
    def __init__(self) -> None:
        self.detached = False

    def detach(self) -> None:
        if self.detached:
            return
        self.detached = True


class _FakeLoadedModel:
    """Stands in for ``model_management.LoadedModel``."""

    def __init__(self, patcher: Any) -> None:
        self.model = patcher
        self.device = getattr(patcher, "load_device", None)
        self.model_finalizer = _FakeFinalizer()
        self.unload_calls = 0

    def model_memory_required(self, device: Any) -> int:
        return 0

    def model_load(self, lowvram_model_memory: int = 0, **_: Any) -> None:
        # ``load_models_gpu`` reaches ``model_load`` on every call, including the
        # second one for an already-registered patcher.
        self.model_finalizer = _FakeFinalizer()
        self.model.loaded_size_calls += 1

    def model_unload(self, memory_to_free: int | None = None, **_: Any) -> bool:
        self.unload_calls += 1
        finalizer, self.model_finalizer = self.model_finalizer, None
        if finalizer is None:
            # Upstream would raise ``AttributeError`` on ``None.detach()``.  The
            # duplicate-registration hazard this guards against is exactly this.
            raise AttributeError("'NoneType' object has no attribute 'detach'")
        finalizer.detach()
        return True


class _FakeModelManagement:
    """Faithful stand-in for the parts of upstream ``model_management`` used here."""

    def __init__(self) -> None:
        self.current_loaded_models: list[Any] = []
        self.calls: list[tuple[list[Any], bool]] = []
        self.raise_on_load: Exception | None = None
        self.activate_effect = None

    def load_models_gpu(self, models: list[Any], force_full_load: bool = False, **_: Any) -> None:
        self.calls.append((list(models), force_full_load))
        if self.raise_on_load is not None:
            raise self.raise_on_load
        for patcher in models:
            # Upstream appends unconditionally at the end of this function.
            self.current_loaded_models.insert(0, _FakeLoadedModel(patcher))
            if self.activate_effect is not None:
                self.activate_effect(patcher)

    def free_memory(self, *_: Any, **__: Any) -> None:
        """Mirrors upstream teardown: unload every registry entry."""
        for entry in list(self.current_loaded_models):
            entry.model_unload(1e30)


class _FakeParam:
    def __init__(self, device: str) -> None:
        self.device = device


class _FakeFirstStage:
    def __init__(self, device: str = "cuda:0") -> None:
        self._device = device

    def parameters(self) -> list[_FakeParam]:
        return [_FakeParam(self._device)]


class _FakePatcher:
    def __init__(self, *, device: str = "cuda:0", dynamic: bool = True) -> None:
        self.load_device = device
        self._dynamic = dynamic
        self.loaded = 0
        self.loaded_size_calls = 0

    def is_dynamic(self) -> bool:
        return self._dynamic

    def loaded_size(self) -> int:
        self.loaded_size_calls += 1
        return self.loaded


class _FakeVae:
    def __init__(self, patcher: _FakePatcher, *, device: str = "cuda:0") -> None:
        self.patcher = patcher
        self.disable_offload = False
        self.first_stage_model = _FakeFirstStage(device)


class _FakeSession:
    def __init__(self, vae: Any) -> None:
        self.vae = vae


@pytest.fixture
def mm(monkeypatch: pytest.MonkeyPatch) -> _FakeModelManagement:
    fake = _FakeModelManagement()
    module = types.ModuleType("comfy.model_management")
    module.current_loaded_models = fake.current_loaded_models  # type: ignore[attr-defined]
    module.load_models_gpu = fake.load_models_gpu  # type: ignore[attr-defined]
    module.free_memory = fake.free_memory  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "comfy", types.ModuleType("comfy"))
    monkeypatch.setitem(sys.modules, "comfy.model_management", module)
    return fake


def _activated_vae(**patcher_kwargs: Any) -> _FakeVae:
    """A VAE whose canonical activation actually takes effect."""
    vae = _FakeVae(_FakePatcher(**patcher_kwargs))
    vae.patcher.loaded = 335 * 1024 * 1024
    return vae


def test_early_activation_runs_the_canonical_call_and_reports_activated(mm) -> None:
    vae = _activated_vae()
    session = _FakeSession(vae)
    identity = overlap.capture_identity(session)

    record = overlap.early_activate(session, identity)

    assert record["status"] == overlap.STATUS_ACTIVATED
    assert record["reason"] == "ok"
    assert record["registered"] is True
    assert record["resident"] is True
    assert record["on_load_device"] is True
    # The activation happened under sampling, so record a real interval.
    # ``<=`` rather than ``<``: the stand-in is instantaneous and the monotonic
    # clock can return one tick for both edges.  The overlap question itself is
    # answered by ``annotate_sampling_overlap`` against real stage bounds.
    assert record["activation_start_ns"] is not None
    assert record["activation_start_ns"] <= record["activation_end_ns"]
    assert record["activation_ms"] >= 0.0
    # Exactly the canonical call, with the VAE's own force_full_load.
    assert mm.calls == [([vae.patcher], False)]


def test_early_activation_never_repeats_and_leaves_the_registry_untouched(mm) -> None:
    """The decode-time call must still register the patcher exactly once.

    ``load_models_gpu`` inserts unconditionally, so an entry left behind here
    would be inserted a second time by ``VAE.decode`` and then unloaded twice at
    teardown -- ``model_unload`` nulls its finalizer, so the second call raises.
    """
    vae = _activated_vae()
    session = _FakeSession(vae)
    identity = overlap.capture_identity(session)

    record = overlap.early_activate(session, identity)

    assert record["status"] == overlap.STATUS_ACTIVATED
    assert mm.current_loaded_models == [], "early activation must not register the VAE"

    # Now replay the canonical decode-time activation.
    mm.load_models_gpu([vae.patcher], force_full_load=False)
    assert len(mm.current_loaded_models) == 1

    # Teardown must not raise, which it would not if the entry were duplicated.
    mm.free_memory(1e30)


@pytest.mark.parametrize(
    "mutate, expected_status, expected_reason",
    [
        (None, overlap.STATUS_ACTIVATED, "ok"),
        ("replace_vae", overlap.STATUS_GUARD_FAILED, "precondition:vae_identity_changed"),
    ],
)
def test_guard_rejects_a_substituted_vae(mm, mutate, expected_status, expected_reason) -> None:
    vae = _activated_vae()
    session = _FakeSession(vae)
    identity = overlap.capture_identity(session)
    original_patcher = vae.patcher
    if mutate == "replace_vae":
        session.vae = _FakeVae(_FakePatcher())

    record = overlap.early_activate(session, identity)

    assert record["status"] == expected_status
    assert record["reason"] == expected_reason
    if expected_status == overlap.STATUS_ACTIVATED:
        assert mm.calls == [([original_patcher], False)]
    else:
        assert mm.calls == [], "a refused guard must not activate anything"


def test_guard_rejects_a_replaced_patcher(mm) -> None:
    vae = _activated_vae()
    session = _FakeSession(vae)
    identity = overlap.capture_identity(session)
    # Same VAE object, but its patcher was swapped out after capture.
    vae.patcher = _FakePatcher()

    record = overlap.early_activate(session, identity)

    assert record["status"] == overlap.STATUS_GUARD_FAILED
    assert record["reason"] == "precondition:patcher_identity_changed"
    assert mm.calls == []


def test_guard_rejects_a_non_dynamic_patcher(mm) -> None:
    vae = _activated_vae(dynamic=False)
    session = _FakeSession(vae)

    record = overlap.early_activate(session, overlap.capture_identity(session))

    assert record["status"] == overlap.STATUS_GUARD_FAILED
    assert record["reason"] == "precondition:patcher_not_dynamic"
    assert mm.calls == []


def test_guard_rejects_a_retargeted_load_device(mm) -> None:
    vae = _activated_vae()
    session = _FakeSession(vae)
    identity = overlap.capture_identity(session)
    vae.patcher.load_device = "cuda:1"

    record = overlap.early_activate(session, identity)

    assert record["status"] == overlap.STATUS_GUARD_FAILED
    assert record["reason"] == "precondition:load_device_changed"
    assert mm.calls == []


def test_guard_rejects_a_missing_vae(mm) -> None:
    session = _FakeSession(None)

    record = overlap.early_activate(session, overlap.capture_identity(session))

    assert record["status"] == overlap.STATUS_GUARD_FAILED
    assert record["reason"] == "precondition:vae_or_patcher_missing"
    assert mm.calls == []


def test_missing_identity_snapshot_is_a_guard_failure_not_a_crash(mm) -> None:
    """No captured identity means nothing was proven, so refuse."""
    vae = _activated_vae()
    session = _FakeSession(vae)

    record = overlap.early_activate(session, {})

    assert record["status"] == overlap.STATUS_GUARD_FAILED
    assert mm.calls == []


def test_activation_exception_is_contained_and_registry_restored(mm) -> None:
    vae = _activated_vae()
    session = _FakeSession(vae)
    mm.raise_on_load = RuntimeError("out of memory")

    record = overlap.early_activate(session, overlap.capture_identity(session))

    assert record["status"] == overlap.STATUS_ERROR
    assert "RuntimeError" in record["reason"]
    assert mm.current_loaded_models == []
    assert record["registry_restored"] is True


def test_unproven_residency_is_a_postcondition_failure_not_a_success(mm) -> None:
    """Activation that does not actually make the VAE resident must not claim to."""
    vae = _FakeVae(_FakePatcher())  # loaded_size() stays 0
    session = _FakeSession(vae)

    record = overlap.early_activate(session, overlap.capture_identity(session))

    assert record["status"] == overlap.STATUS_POSTCONDITION_FAILED
    assert "resident" in record["reason"]
    assert mm.current_loaded_models == []


def test_parameters_off_the_load_device_fail_the_postcondition(mm) -> None:
    vae = _activated_vae()
    session = _FakeSession(vae)
    # Activation succeeds, but a first-stage parameter is not on the load device.
    vae.first_stage_model = _FakeFirstStage(device="cpu")

    record = overlap.early_activate(session, overlap.capture_identity(session))

    assert record["status"] == overlap.STATUS_POSTCONDITION_FAILED
    assert "on_load_device" in record["reason"]


def test_registry_survives_a_pre_existing_entry(mm) -> None:
    """Other models' entries must be preserved exactly, not just the count."""
    vae = _activated_vae()
    session = _FakeSession(vae)
    sentinel = object()
    mm.current_loaded_models.insert(0, _FakeLoadedModel(_FakePatcher()))
    mm.current_loaded_models.insert(0, sentinel)

    record = overlap.early_activate(session, overlap.capture_identity(session))

    assert record["status"] == overlap.STATUS_ACTIVATED
    assert mm.current_loaded_models[0] is sentinel
    assert len(mm.current_loaded_models) == 2
    assert record["registry_entries_before"] == 2
    assert record["registry_entries_after_restore"] == 2
    assert record["registry_restored"] is True


def test_force_full_load_follows_the_vae(mm) -> None:
    """A VAE that disabled offload keeps its exact semantics."""
    vae = _activated_vae()
    vae.disable_offload = True
    session = _FakeSession(vae)

    overlap.early_activate(session, overlap.capture_identity(session))

    assert mm.calls == [([vae.patcher], True)]


def test_capture_identity_records_the_live_patcher(mm) -> None:
    vae = _activated_vae()
    session = _FakeSession(vae)

    identity = overlap.capture_identity(session)

    assert identity["vae_present"] is True
    assert identity["patcher_present"] is True
    assert identity["vae_id"] == id(vae)
    assert identity["patcher_id"] == id(vae.patcher)
    assert identity["load_device"] == "cuda:0"
    assert identity["is_dynamic"] is True


def test_overlap_annotation_reports_activation_inside_sampling() -> None:
    record = {"activation_start_ns": 100, "activation_end_ns": 200}

    annotated = overlap.annotate_sampling_overlap(
        record, {"owner_start_ns": 50, "owner_end_ns": 400}
    )

    assert annotated["inside_sampling"] is True
    assert annotated["sampling_active_at_start"] is True
    assert annotated["hidden_by_sampling_ms"] == pytest.approx(0.0001)


def test_overlap_annotation_exposes_a_miss_that_was_not_hidden() -> None:
    """Moving the cost earlier without overlapping it must not read as a win."""
    record = {"activation_start_ns": 500, "activation_end_ns": 600}

    annotated = overlap.annotate_sampling_overlap(
        record, {"owner_start_ns": 50, "owner_end_ns": 400}
    )

    assert annotated["inside_sampling"] is False
    assert annotated["sampling_active_at_start"] is False
    assert annotated["hidden_by_sampling_ms"] == 0.0


def test_overlap_annotation_tolerates_missing_evidence() -> None:
    record = {"activation_start_ns": 100, "activation_end_ns": 200}

    assert overlap.annotate_sampling_overlap(record, {})["inside_sampling"] is None
    assert overlap.annotate_sampling_overlap(record, None)["inside_sampling"] is None


# ── Wiring contract ────────────────────────────────────────────────────────
# ComfyUI (and therefore golden_serial) cannot be imported in this environment,
# so the call sites are asserted against the source text.  This is the same
# technique the existing stage-pair foundation test uses.

_SOURCE = (
    Path(__file__).resolve().parents[1] / "comfymodal_runtime" / "golden_serial.py"
).read_text(encoding="utf-8")


def _region(start_marker: str, end_marker: str) -> str:
    """Slice ``_SOURCE`` between two markers, inclusive of start, exclusive of end."""
    start = _SOURCE.index(start_marker)
    end = _SOURCE.index(end_marker, start)
    assert end > start, f"{end_marker!r} must follow {start_marker!r}"
    return _SOURCE[start:end]


def test_relocation_is_wired_into_the_overlap_window_only() -> None:
    """The activation is relocated only where there is sampling to hide behind.

    On the ``serial`` schedule the two stages do not run concurrently, so
    relocating there would not hide anything -- it would only move ~80 ms
    earlier and delay sampling.  The serial branch must therefore stay exactly
    the historical ``vae_load`` then ``sampling`` pair.
    """
    window = _region(
        "async def golden_sampling_vae_window",
        "def _finalize_vae_dynamicvram_activation",
    )

    overlap_branch = window[window.index("if schedule == OVERLAP_SCHEDULE_OVERLAP") :]
    serial_branch = overlap_branch[overlap_branch.index("return") :]

    assert "_golden_vae_load_then_early_activate" in overlap_branch
    assert "_finalize_vae_dynamicvram_activation" in overlap_branch
    # Serial schedule: canonical ordering, no relocation.
    assert "early_activate" not in serial_branch
    assert serial_branch.index("await vae_load()") < serial_branch.index("await sampling()")


def test_relocation_runs_after_vae_load_not_before() -> None:
    """The whole point is to overlap, so it must come after the VAE exists."""
    wrapper = _region(
        "async def _golden_vae_load_then_early_activate",
        "async def golden_sampling_vae_window",
    )

    assert wrapper.index("result = await vae_load()") < wrapper.index("capture_identity")
    assert "early_activate(session, identity)" in wrapper


def test_relocation_never_raises_into_the_request() -> None:
    """A failure must cost wall, never correctness."""
    wrapper = _region(
        "async def _golden_vae_load_then_early_activate",
        "async def golden_sampling_vae_window",
    )

    assert "except Exception" in wrapper
    # The result of vae_load is returned regardless of the relocation outcome.
    assert wrapper.rstrip().endswith("return result")