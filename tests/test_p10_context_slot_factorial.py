"""P10 2x2 factorial: hoisted CUDA primary-context preinit x arena slot depth.

Two independent axes, deliberately tested together because host-registration work
depends on arena size:

  context preinit  COMFYMODAL_GOLDEN_C0_REGISTRATION_CONTEXT_PREINIT
  slot count       COMFYMODAL_GOLDEN_C0_SOURCE_SLOT_COUNT

These tests protect the contracts the arms depend on, not the timings:

CONTEXT
  * preinit OFF starts no worker and touches no CUDA before registration
  * preinit ON only runs post-restore (snap=False)
  * snap=True is refused outright and never runs the driver call
  * a worker failure propagates out of join, i.e. before any arena use
  * join is bounded (a stuck worker raises rather than blocking forever)
  * no Triton / model / H2D work is triggered by the primitive

SLOTS
  * 16 => exactly 1073741824 bytes, 12 => exactly 805306368 bytes
  * SLOT_BYTES stays 64 MiB at both axis values
  * slot_count / arena_bytes stay mutually consistent everywhere they are read
  * an unsupported slot count fails closed instead of inheriting the default

IDENTITY
  * the deploy-baked arm name reaches the resolver
  * declared arm vs observed slot count / preinit flag fail closed on mismatch
"""

from __future__ import annotations

import importlib
import inspect
import os
from typing import Any

import pytest


SLOT_BYTES = 64 * 1024 * 1024


def _source_of(target: Any) -> str:
    return inspect.getsource(target)


@pytest.fixture
def arm_env():
    """Reload runtime modules against a deploy-baked environment.

    The resolved constants (SLOT_COUNT, C0_SLOT_COUNT, the preinit flag, the
    preinit singleton) are computed at import time, so a test that wants a
    different arm must re-execute the module with that environment in force.
    The environment is kept in place for the whole test and restored on
    teardown: reading a constant after restoring the environment would just
    re-read the default.
    """
    forced: list[tuple[str, str, str | None]] = []

    def _load(module_path: str, env: dict[str, str]) -> Any:
        for name, value in env.items():
            if (module_path, name) not in {(path, key) for path, key, _ in forced}:
                forced.append((module_path, name, os.environ.get(name)))
            os.environ[name] = value
        module = importlib.import_module(module_path)
        importlib.reload(module)
        return module

    yield _load

    # Teardown: undo every environment change, then reload each touched module
    # so nothing keeps constants resolved from a temporary arm.
    for _path, name, original in reversed(forced):
        if original is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = original
    for module_path in dict.fromkeys(path for path, _key, _value in forced):
        importlib.reload(importlib.import_module(module_path))


def _load_gst(arm_env, slot_count: str | None = None):
    env = {}
    if slot_count is not None:
        env["COMFYMODAL_GOLDEN_C0_SOURCE_SLOT_COUNT"] = slot_count
    return arm_env("comfymodal_runtime.golden_source_threads", env)


def _load_c0(arm_env, **env: str):
    return arm_env("comfymodal_runtime.golden_io_process_v2", env)


# ── SLOTS ────────────────────────────────────────────────────────────────────


@pytest.mark.fast_unit
@pytest.mark.parametrize(
    ("value", "expected_count", "expected_bytes"),
    [("16", 16, 1_073_741_824), ("12", 12, 805_306_368)],
)
def test_slot_count_resolves_to_exact_arena_bytes(
    arm_env, value: str, expected_count: int, expected_bytes: int
) -> None:
    module = _load_gst(arm_env, value)
    assert module.SLOT_COUNT == expected_count
    assert module.ARENA_BYTES == expected_bytes
    assert module.ARENA_BYTES == expected_count * module.SLOT_BYTES
    geometry = module.geometry()
    assert geometry["slot_count"] == expected_count
    assert geometry["arena_bytes"] == expected_bytes
    assert geometry["slot_bytes"] == SLOT_BYTES


@pytest.mark.fast_unit
@pytest.mark.parametrize("value", ["12", "16"])
def test_slot_bytes_is_never_an_axis(arm_env, value: str) -> None:
    """SLOT_BYTES is the block/pacing/H2D unit, so it must not move with depth."""
    module = _load_gst(arm_env, value)
    assert module.SLOT_BYTES == SLOT_BYTES
    assert module.READER_COUNT == 4
    assert module.THREAD_COUNT == 4
    assert module.PACER_GAP_NS == 4_000_000


@pytest.mark.fast_unit
@pytest.mark.parametrize("value", ["8", "14", "0", "-4", "twelve", ""])
def test_unsupported_slot_count_fails_closed(value) -> None:
    from comfymodal_runtime import golden_source_threads as gst

    with pytest.raises(gst.SourceProtocolError) as excinfo:
        gst.resolve_slot_count(value)
    assert "unsupported_source_slot_count" in str(excinfo.value)


@pytest.mark.fast_unit
def test_resolve_slot_count_none_reads_the_environment() -> None:
    """None means "resolve from the environment", which is the default arm."""
    from comfymodal_runtime import golden_source_threads as gst

    assert gst.resolve_slot_count(None) == gst.DEFAULT_SLOT_COUNT


@pytest.mark.fast_unit
def test_default_slot_count_is_the_accepted_production_default() -> None:
    from comfymodal_runtime import golden_source_threads as gst

    assert gst.DEFAULT_SLOT_COUNT == 16
    assert gst.SUPPORTED_SLOT_COUNTS == (12, 16)


@pytest.mark.fast_unit
@pytest.mark.parametrize(
    ("value", "expected_slots", "expected_mask"),
    [("16", 16, 0xFFFF), ("12", 12, 0xFFF)],
)
def test_derived_slot_layout_follows_the_slot_count(
    arm_env, value: str, expected_slots: int, expected_mask: int
) -> None:
    """Slot table, free mask and control layout are all SLOT_COUNT-derived.

    A 12-slot arena that kept the 16-slot free mask would let the child address
    a slot the parent never allocated, so these must track the count exactly.
    """
    module = _load_gst(arm_env, value)
    assert module.SLOT_TABLE_BYTES == expected_slots * module.SLOT.size
    assert module.FREE_MASK == expected_mask
    assert module.COUNTER_OFFSET == module.SLOT_OFFSET + module.SLOT_TABLE_BYTES
    assert module.OP_OFFSET > module.ERROR_OFFSET


# ── CONTEXT: flag resolution ─────────────────────────────────────────────────


@pytest.mark.fast_unit
@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1", True), ("true", True), ("on", True), ("0", False), ("", False)],
)
def test_context_preinit_flag_is_truthy_only(arm_env, raw, expected: bool) -> None:
    c0 = _load_c0(arm_env, COMFYMODAL_GOLDEN_C0_REGISTRATION_CONTEXT_PREINIT=raw)
    assert c0.c0_registration_context_preinit_enabled() is expected


# ── CONTEXT: worker lifecycle ────────────────────────────────────────────────


@pytest.mark.fast_unit
def test_preinit_off_never_starts_a_worker_and_never_calls_the_driver(
    arm_env, monkeypatch
) -> None:
    """OFF must be the exact production control: no early CUDA at all."""
    c0 = _load_c0(arm_env, COMFYMODAL_GOLDEN_C0_REGISTRATION_CONTEXT_PREINIT="0")
    calls: list[int] = []
    monkeypatch.setattr(
        c0, "_preinit_primary_context", lambda device: calls.append(device) or {"ok": True}
    )
    assert c0.start_c0_context_preinit(snap=False) == {"context_preinit": "disabled"}
    assert calls == []
    state = c0.c0_context_preinit_telemetry()
    assert state["context_preinit_mode"] == "not_started"
    assert state["context_preinit_joined"] is False


@pytest.mark.fast_unit
def test_preinit_on_runs_the_driver_primitive_on_a_worker_thread(arm_env, monkeypatch) -> None:
    c0 = _load_c0(arm_env, COMFYMODAL_GOLDEN_C0_REGISTRATION_CONTEXT_PREINIT="1")
    main_ident = threading_ident()
    seen: dict[str, object] = {}

    def _fake(device_index: int) -> dict:
        seen["device_index"] = device_index
        seen["thread"] = threading_ident()
        return {"mode": "driver_primary_context_retain_set_current"}

    monkeypatch.setattr(c0, "_preinit_primary_context", _fake)
    started = c0.start_c0_context_preinit(snap=False)
    assert started["context_preinit_mode"] == "started"

    result = c0.join_c0_context_preinit()
    assert result["context_preinit_status"] == "ok"
    assert result["context_preinit_mode"] == "hoisted_worker"
    assert result["context_preinit"] == {"mode": "driver_primary_context_retain_set_current"}
    # The whole point of the treatment: the driver call does NOT run on the
    # thread that will later need the context, so restore can overlap it.
    assert seen["thread"] != main_ident
    assert seen["device_index"] == 0
    assert result["context_preinit_wall_ms"] >= 0.0
    assert result["context_preinit_thread_cpu_ms"] >= 0.0
    assert result["context_preinit_join_wait_ms"] >= 0.0
    assert result["context_preinit_start"] > 0
    assert result["context_preinit_end"] >= result["context_preinit_start"]


def threading_ident() -> int:
    import threading

    return threading.get_native_id()


@pytest.mark.fast_unit
def test_snap_true_is_refused_and_never_calls_the_driver(arm_env, monkeypatch) -> None:
    """A snapshot capture must never create CUDA state."""
    c0 = _load_c0(arm_env, COMFYMODAL_GOLDEN_C0_REGISTRATION_CONTEXT_PREINIT="1")
    calls: list[int] = []
    monkeypatch.setattr(c0, "_preinit_primary_context", lambda device: calls.append(device) or {})
    started = c0.start_c0_context_preinit(snap=True)
    assert started == {"context_preinit": "refused", "reason": "snapshot_capture"}
    assert calls == []
    assert c0.c0_context_preinit_telemetry()["context_preinit_mode"] == "not_started"


@pytest.mark.fast_unit
def test_worker_failure_propagates_from_join_before_any_arena_use(
    arm_env, monkeypatch
) -> None:
    """Fail closed: a broken context must surface at join, not later as CUDA."""
    import threading

    c0 = _load_c0(arm_env, COMFYMODAL_GOLDEN_C0_REGISTRATION_CONTEXT_PREINIT="1")

    def _boom(device_index: int) -> dict:
        raise RuntimeError("cuDevicePrimaryCtxRetain_failed:999")

    monkeypatch.setattr(c0, "_preinit_primary_context", _boom)
    c0.start_c0_context_preinit(snap=False)
    with pytest.raises(RuntimeError) as excinfo:
        c0.join_c0_context_preinit()
    assert "c0_context_preinit_failed" in str(excinfo.value)
    assert "cuDevicePrimaryCtxRetain_failed" in str(excinfo.value)
    assert not threading.current_thread().is_alive() is False  # sanity: still on main thread


@pytest.mark.fast_unit
def test_join_is_bounded_when_the_worker_never_finishes(arm_env, monkeypatch) -> None:
    """A bounded join must raise rather than block a restore indefinitely."""
    import threading

    c0 = _load_c0(arm_env, COMFYMODAL_GOLDEN_C0_REGISTRATION_CONTEXT_PREINIT="1")
    release = threading.Event()

    def _hang(device_index: int) -> dict:
        release.wait(30.0)
        return {}

    monkeypatch.setattr(c0, "_preinit_primary_context", _hang)
    c0.start_c0_context_preinit(snap=False)
    try:
        with pytest.raises(RuntimeError) as excinfo:
            c0.join_c0_context_preinit(timeout_s=0.05)
        assert "c0_context_preinit_join_timeout" in str(excinfo.value)
    finally:
        release.set()


@pytest.mark.fast_unit
def test_start_is_idempotent_and_does_not_relaunch(arm_env) -> None:
    c0 = _load_c0(arm_env, COMFYMODAL_GOLDEN_C0_REGISTRATION_CONTEXT_PREINIT="1")
    first = c0.start_c0_context_preinit(snap=False)
    thread_first = c0._C0_CONTEXT_PREINIT._thread
    second = c0.start_c0_context_preinit(snap=False)
    assert c0._C0_CONTEXT_PREINIT._thread is thread_first
    assert first["context_preinit_start"] == second["context_preinit_start"]


@pytest.mark.fast_unit
def test_join_without_a_worker_falls_back_inline_and_says_so(arm_env, monkeypatch) -> None:
    """A container that never ran the restore hoist must still do the work."""
    c0 = _load_c0(arm_env, COMFYMODAL_GOLDEN_C0_REGISTRATION_CONTEXT_PREINIT="1")
    main_ident = threading_ident()
    seen: dict[str, object] = {}

    def _fake(device_index: int) -> dict:
        seen["thread"] = threading_ident()
        return {"ok": True}

    monkeypatch.setattr(c0, "_preinit_primary_context", _fake)
    result = c0.join_c0_context_preinit()
    assert result["context_preinit_mode"] == "inline_fallback"
    assert result["context_preinit_join_wait_ms"] == 0.0
    assert seen["thread"] == main_ident


@pytest.mark.fast_unit
def test_preinit_primitive_does_no_model_triton_or_h2d_work() -> None:
    """Guard the treatment scope: retain + set-current, nothing else."""
    from comfymodal_runtime import golden_io_process_v2 as c0

    source = _source_of(c0._preinit_primary_context)
    for forbidden in (
        "torch",
        "triton",
        "empty(",
        "zeros(",
        "randn",
        "Tensor",
        "memcpy",
        "cudaMemcpy",
        "compile",
    ):
        assert forbidden not in source, forbidden
    # Exactly the four driver calls needed to create and retain the primary
    # context and make it current on the calling thread.
    for required in (
        "cuInit",
        "cuDeviceGet",
        "cuDevicePrimaryCtxRetain",
        "cuCtxSetCurrent",
    ):
        assert required in source


@pytest.mark.fast_unit
def test_preinit_evidence_carries_both_the_claim_and_the_observation(arm_env) -> None:
    """evidence() must expose declared preinit, declared geometry and the arm, so
    a run artifact proves which arm produced it."""
    c0 = _load_c0(
        arm_env,
        COMFYMODAL_GOLDEN_C0_REGISTRATION_CONTEXT_PREINIT="1",
        COMFYMODAL_GOLDEN_C0_SOURCE_SLOT_COUNT="16",
        COMFYMODAL_GOLDEN_IO_PROCESS_V2_SOURCE_GEOMETRY="qd4_64",
    )
    identity = c0.verify_experiment_arm(
        "p10-16-preinit", slot_count=16, slot_bytes=SLOT_BYTES, context_preinit=True
    )
    assert identity["observed_slot_count"] == 16
    assert identity["observed_slot_bytes"] == SLOT_BYTES
    assert identity["observed_arena_bytes"] == 1_073_741_824
    assert identity["observed_context_preinit"] is True
    assert identity["arm_verified"] is True

    source = _source_of(c0.SharedArenaRing.evidence)
    for key in (
        '"declared_slot_count"',
        '"declared_slot_bytes"',
        '"declared_arena_bytes"',
        '"slot_geometry_exact"',
        '"context_preinit_enabled"',
        '"context_preinit_state"',
        '"experiment_arm"',
        '"arena_establish_wall_ms"',
    ):
        assert key in source, key


# ── IDENTITY ─────────────────────────────────────────────────────────────────


@pytest.mark.fast_unit
def test_arm_name_reaches_the_resolver_from_the_deploy_environment(arm_env) -> None:
    c0 = _load_c0(arm_env, COMFYMODAL_GOLDEN_C0_EXPERIMENT_ARM="p10-12-preinit")
    assert c0.resolve_experiment_arm() == "p10-12-preinit"


@pytest.mark.fast_unit
def test_absent_arm_means_the_arm_axis_is_unused(arm_env) -> None:
    c0 = _load_c0(arm_env)
    assert c0.resolve_experiment_arm() is None
    identity = c0.verify_experiment_arm(None, slot_count=16, slot_bytes=SLOT_BYTES, context_preinit=False)
    assert identity["arm_status"] == "unassigned"
    assert identity["arm_verified"] is False


@pytest.mark.fast_unit
@pytest.mark.parametrize("bad", ["p10-16-sometimes", "p10-17-preinit", "p10-16", "16-preinit"])
def test_unknown_arm_name_fails_closed(arm_env, bad: str) -> None:
    c0 = _load_c0(arm_env, COMFYMODAL_GOLDEN_C0_EXPERIMENT_ARM=bad)
    with pytest.raises(ValueError) as excinfo:
        c0.resolve_experiment_arm()
    assert "COMFYMODAL_GOLDEN_C0_EXPERIMENT_ARM_invalid" in str(excinfo.value)


@pytest.mark.fast_unit
@pytest.mark.parametrize(
    ("arm", "slots", "preinit"),
    [
        ("p10-16-nopreinit", 16, False),
        ("p10-16-preinit", 16, True),
        ("p10-12-nopreinit", 12, False),
        ("p10-12-preinit", 12, True),
    ],
)
def test_matching_arm_verifies(arm_env, arm: str, slots: int, preinit: bool) -> None:
    c0 = _load_c0(arm_env)
    identity = c0.verify_experiment_arm(arm, slot_count=slots, slot_bytes=SLOT_BYTES, context_preinit=preinit)
    assert identity["arm_status"] == "verified"
    assert identity["arm_verified"] is True
    assert identity["observed_slot_count"] == slots


@pytest.mark.fast_unit
def test_slot_mismatch_fails_closed(arm_env) -> None:
    c0 = _load_c0(arm_env)
    with pytest.raises(RuntimeError) as excinfo:
        c0.verify_experiment_arm("p10-12-preinit", slot_count=16, slot_bytes=SLOT_BYTES, context_preinit=True)
    assert "c0_experiment_arm_slot_mismatch" in str(excinfo.value)


@pytest.mark.fast_unit
def test_preinit_mismatch_fails_closed(arm_env) -> None:
    c0 = _load_c0(arm_env)
    with pytest.raises(RuntimeError) as excinfo:
        c0.verify_experiment_arm("p10-16-preinit", slot_count=16, slot_bytes=SLOT_BYTES, context_preinit=False)
    assert "c0_experiment_arm_preinit_mismatch" in str(excinfo.value)


@pytest.mark.fast_unit
@pytest.mark.parametrize(("slots", "expected_bytes"), [(16, 1_073_741_824), (12, 805_306_368)])
def test_c0_geometry_mirrors_the_arena_owner(
    arm_env, slots: int, expected_bytes: int
) -> None:
    """The C0 module must describe the same mapping the source owner attaches."""
    _load_gst(arm_env, str(slots))
    c0 = _load_c0(
        arm_env,
        COMFYMODAL_GOLDEN_C0_SOURCE_SLOT_COUNT=str(slots),
        COMFYMODAL_GOLDEN_IO_PROCESS_V2_SOURCE_GEOMETRY="qd4_64",
    )
    geometry = c0.resolve_c0_geometry("qd4_64")
    assert geometry["slot_count"] == slots
    assert geometry["slot_bytes"] == SLOT_BYTES
    assert geometry["arena_bytes"] == expected_bytes
    assert geometry["arena_bytes"] == geometry["slot_count"] * geometry["slot_bytes"]
    # Slot owners stay evidence-only but must still cover every slot.
    assert len(geometry["slot_owners"]) == geometry["slot_count"]
    assert set(geometry["slot_owners"]) == {0, 1, 2, 3}
    assert c0.C0_ARENA_BYTES == expected_bytes
    assert c0.C0_SLOT_COUNT == slots
    assert c0.C0_INFLIGHT_LIMIT == slots


@pytest.mark.fast_unit
def test_qd4_64_slot_owners_reproduces_the_accepted_16_slot_assignment() -> None:
    from comfymodal_runtime import golden_io_process_v2 as c0

    assert c0._qd4_64_slot_owners(16, 4) == (
        0, 0, 1, 1, 2, 2, 3, 3, 0, 0, 1, 1, 2, 2, 3, 3,
    )
    assert c0._qd4_64_slot_owners(12, 4) == (0, 0, 1, 1, 2, 2, 3, 3, 0, 0, 1, 1)


# ── restore / join wiring ────────────────────────────────────────────────────


@pytest.mark.fast_unit
def test_minimal_restore_starts_preinit_with_snap_false_and_joins_in_initialize_cuda() -> None:
    """The hoist must live at the snap=False restore boundary and join in
    initialize_cuda(), not inside the registration call."""
    from comfymodal_runtime import golden_model_transport as gmt
    from comfymodal_runtime import modal_app

    restore_source = _source_of(modal_app.ModalRuntimeEntrypointV2._golden_minimal_restore)
    assert "start_c0_context_preinit(snap=False)" in restore_source
    assert "start_c0_context_preinit(snap=True)" not in restore_source
    # The state repair the hoist overlaps must come after the start, and the
    # CUDA-needing call must come after both.
    assert restore_source.index("start_c0_context_preinit(snap=False)") < restore_source.index(
        "self._golden_minimal_reset_container_state()"
    )
    assert restore_source.index(
        "self._golden_minimal_reset_container_state()"
    ) < restore_source.index("get_golden_model_transport().initialize_cuda()")

    init_source = _source_of(gmt.GoldenModelTransport.initialize_cuda)
    assert "join_c0_context_preinit()" in init_source
    # Join after the CPU-only prepare, before the first torch CUDA call.
    assert init_source.index("prepare_cpu()") < init_source.index("join_c0_context_preinit()")
    assert init_source.index("join_c0_context_preinit()") < init_source.index(
        "torch.cuda.is_available()"
    )


@pytest.mark.fast_unit
def test_registration_joins_the_worker_instead_of_running_it_inline() -> None:
    """ensure() must join, never call the driver primitive on its own thread."""
    from comfymodal_runtime import golden_io_process_v2 as c0

    source = _source_of(c0.SharedArenaRing.ensure)
    assert "join_c0_context_preinit()" in source
    assert "_preinit_primary_context(" not in source


@pytest.mark.fast_unit
def test_restore_hook_is_not_reachable_from_a_snapshot_capture_boundary() -> None:
    """snap=True is bound to startup, snap=False to restore.  The treatment must
    only be reachable from the snap=False method, and never ask for snap=True."""
    from comfymodal_runtime import modal_app

    module_source = _source_of(modal_app)
    assert "(snap=_resolve_enable_memory_snapshot())(cls.startup)" in module_source
    assert "_modal.enter(snap=False)(cls.restore)" in module_source
    # No caller ever asks for the snap=True branch of the treatment.
    assert "start_c0_context_preinit(snap=True)" not in module_source
    # The single start site is inside the minimal restore, which is the method
    # restore() delegates to under COMFYMODAL_GOLDEN_MINIMAL_RESTORE=1.
    assert module_source.count("start_c0_context_preinit(snap=False)") == 1
    assert (
        "start_c0_context_preinit(snap=False)"
        in _source_of(modal_app.ModalRuntimeEntrypointV2._golden_minimal_restore)
    )