"""Golden scheduler tests: deterministic transitions + overlap matrix."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from comfymodal_runtime.golden.contracts import (
    ForbiddenOverlapError,
    GoldenError,
    GoldenEvent,
    LifecyclePhase,
    ResourceDomain,
)
from comfymodal_runtime.golden.resource_scheduler import (
    ACT_CHEAP_REQUEST_SETUP,
    ACT_CLIP_FORWARD,
    ACT_CLIP_GPU_CRITICAL,
    ACT_CLIP_QD_H2D,
    ACT_CLIP_QD_SOURCE,
    ACT_SAMPLING,
    ACT_UNET_BULK_SOURCE,
    ACT_UNET_GPU_COMMIT,
    ACT_UNET_H2D,
    ACT_UNET_METADATA_PREP,
    ACT_VAE_GPU_MUTATION,
    ACT_VAE_QD,
    GoldenResourceScheduler,
    OverlapMatrix,
)

SCHEDULER_SRC = Path(__file__).resolve().parents[2] / "comfymodal_runtime" / "golden" / "resource_scheduler.py"


def _fresh() -> GoldenResourceScheduler:
    return GoldenResourceScheduler()


def _walk_legal(s: GoldenResourceScheduler):
    s.begin_minimal_restore()
    assert s.transition(GoldenEvent.RESTORE_READY) == LifecyclePhase.CLIP_QD_LOAD
    g_src = s.acquire(ACT_CLIP_QD_SOURCE, (ResourceDomain.STORAGE_HEAVY,))
    g_h2d = s.acquire(ACT_CLIP_QD_H2D, (ResourceDomain.H2D_HEAVY,))
    assert s.transition(GoldenEvent.CLIP_DEVICE_READY) == LifecyclePhase.CLIP_FORWARD_UNET_PREPARE
    assert not s.active_labels(), "clip qd grants must be force-released"
    g_fwd = s.acquire(ACT_CLIP_FORWARD, (ResourceDomain.GPU_COMPUTE,))
    g_crit = s.acquire(ACT_CLIP_GPU_CRITICAL, (ResourceDomain.GPU_MUTATION,))
    s.transition(GoldenEvent.CLIP_FORWARD_STARTED)
    s.transition(GoldenEvent.CLIP_STORAGE_RELEASED)
    g_prep = s.acquire(ACT_UNET_METADATA_PREP, (ResourceDomain.CPU_HEAVY,))
    s.release(g_prep)
    s.release(g_fwd)
    s.release(g_crit)
    assert s.transition(GoldenEvent.CLIP_GPU_CRITICAL_DONE) == LifecyclePhase.UNET_COMMIT
    g_commit = s.acquire(ACT_UNET_GPU_COMMIT, (ResourceDomain.GPU_MUTATION,))
    s.release(g_commit)
    assert s.transition(GoldenEvent.UNET_DEVICE_READY) == LifecyclePhase.SAMPLING
    g_samp = s.acquire(ACT_SAMPLING, (ResourceDomain.GPU_COMPUTE,))
    s.transition(GoldenEvent.SAMPLING_STARTED)
    s.transition(GoldenEvent.FIRST_SAMPLER_STEP_PROVEN)
    g_vae = s.acquire(ACT_VAE_QD, (ResourceDomain.STORAGE_HEAVY, ResourceDomain.H2D_HEAVY))
    s.release(g_vae)
    s.transition(GoldenEvent.VAE_DEVICE_READY)
    assert s.transition(GoldenEvent.VAE_DECODE_DEMAND) == LifecyclePhase.OUTPUT_DELIVERY
    s.release(g_samp)
    assert s.transition(GoldenEvent.FIRST_DURABLE_RESULT) == LifecyclePhase.COMPLETE


def test_full_legal_transition_walk():
    _walk_legal(_fresh())


def test_deterministic_identical_histories():
    a, b = _fresh(), _fresh()
    _walk_legal(a)
    _walk_legal(b)
    assert a.phase_history == b.phase_history


def test_illegal_transitions_fail_loudly():
    s = _fresh()
    with pytest.raises(GoldenError):
        s.transition(GoldenEvent.UNET_DEVICE_READY)
    s.begin_minimal_restore()
    s.transition(GoldenEvent.RESTORE_READY)
    with pytest.raises(GoldenError):
        s.transition(GoldenEvent.RESTORE_READY)


def test_matrix_explicit_denials():
    m = OverlapMatrix()
    for active, request in [
        ({ACT_CLIP_QD_H2D}, ACT_UNET_H2D),
        ({ACT_CLIP_QD_SOURCE}, ACT_UNET_BULK_SOURCE),
        ({ACT_CLIP_GPU_CRITICAL}, ACT_UNET_GPU_COMMIT),
        ({ACT_CLIP_GPU_CRITICAL}, ACT_SAMPLING),
        ({ACT_VAE_GPU_MUTATION}, ACT_SAMPLING),
        ({ACT_UNET_GPU_COMMIT}, ACT_SAMPLING),
        ({ACT_CLIP_FORWARD}, ACT_CLIP_QD_SOURCE),
    ]:
        decision = m.check(set(active), request)
        assert not decision.allowed, f"{active}+{request} must deny"
        with pytest.raises(ForbiddenOverlapError):
            m.require(set(active), request)


def test_matrix_allows_and_conditionals():
    m = OverlapMatrix()
    assert m.check({ACT_CLIP_QD_SOURCE}, ACT_CHEAP_REQUEST_SETUP).allowed
    assert m.check({ACT_CLIP_FORWARD}, ACT_UNET_METADATA_PREP).allowed
    assert m.check({ACT_CLIP_FORWARD}, ACT_UNET_BULK_SOURCE).allowed
    unarmed = OverlapMatrix(vae_qd_armed_provider=lambda: False)
    assert not unarmed.check({ACT_SAMPLING}, ACT_VAE_QD).allowed
    armed = OverlapMatrix(vae_qd_armed_provider=lambda: True)
    assert armed.check({ACT_SAMPLING}, ACT_VAE_QD).allowed


def test_unlisted_heavy_pair_defaults_deny():
    m = OverlapMatrix()
    assert not m.check({ACT_UNET_METADATA_PREP}, ACT_VAE_GPU_MUTATION).allowed


def test_acquire_gating_rules():
    s = _fresh()
    with pytest.raises(ForbiddenOverlapError):
        s.acquire(ACT_CLIP_QD_SOURCE, (ResourceDomain.STORAGE_HEAVY,))
    s.begin_minimal_restore()
    s.transition(GoldenEvent.RESTORE_READY)
    with pytest.raises(ForbiddenOverlapError):
        s.acquire(ACT_UNET_BULK_SOURCE, (ResourceDomain.STORAGE_HEAVY,))
    with pytest.raises(ForbiddenOverlapError):
        s.acquire(ACT_UNET_GPU_COMMIT, (ResourceDomain.GPU_MUTATION,))
    with pytest.raises(ForbiddenOverlapError):
        s.acquire(ACT_VAE_QD, (ResourceDomain.STORAGE_HEAVY,))
    g = s.acquire(ACT_CLIP_QD_SOURCE, (ResourceDomain.STORAGE_HEAVY,))
    s.transition(GoldenEvent.CLIP_DEVICE_READY)
    assert ACT_CLIP_QD_SOURCE in s.forced_releases
    s.acquire(ACT_UNET_BULK_SOURCE, (ResourceDomain.STORAGE_HEAVY,))


def test_exclusive_domain_enforced():
    s = _fresh()
    s.begin_minimal_restore()
    s.transition(GoldenEvent.RESTORE_READY)
    s.acquire(ACT_CLIP_QD_H2D, (ResourceDomain.H2D_HEAVY,))
    with pytest.raises(ForbiddenOverlapError):
        s.acquire(ACT_UNET_H2D, (ResourceDomain.H2D_HEAVY,))


def test_no_sleeps_in_scheduler_source():
    tree = ast.parse(SCHEDULER_SRC.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "sleep":
                pytest.fail(f"time.sleep-like call found at line {node.lineno}")


def test_release_unknown_grant_raises():
    s = _fresh()
    from comfymodal_runtime.golden.resource_scheduler import Grant

    with pytest.raises(GoldenError):
        s.release(Grant(label=ACT_SAMPLING, domains=(), grant_id=999))
