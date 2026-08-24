"""Golden ownership protocol tests: one read per role; join/adopt semantics."""

from __future__ import annotations

import threading

import pytest

from comfymodal_runtime.golden.contracts import GoldenError, JoinDecision, ModelRole
from comfymodal_runtime.golden.model_owner import GoldenModelOwner, GoldenOwnerRegistry


def _owner(role=ModelRole.CLIP, ident="abc123"):
    return GoldenModelOwner(role, ident)


def test_registry_rejects_duplicate_live_owner():
    reg = GoldenOwnerRegistry()
    o1 = _owner()
    o1.publish_device_ready({"buf": 1})
    reg.register(o1)
    with pytest.raises(GoldenError, match="duplicate live owner"):
        reg.register(_owner())


def test_registry_allows_reregister_after_release_or_failure():
    reg = GoldenOwnerRegistry()
    o1 = _owner()
    h = o1.take("bind")
    o1.release()
    reg.register(o1)
    reg.clear_role(ModelRole.CLIP)
    o2 = _owner(ident="def456")
    o2.publish_failure(RuntimeError("boom"))
    reg.register(o2)


def test_join_already_ready_without_wait():
    owner = _owner()
    owner.publish_device_ready("payload")
    assert owner.join(2.0) == JoinDecision.ALREADY_READY


def test_join_joined_inflight_producer():
    owner = _owner()
    timer = threading.Timer(0.05, owner.publish_device_ready, args=("late",))
    timer.start()
    try:
        assert owner.join(2.0) == JoinDecision.JOINED
    finally:
        timer.join()


def test_join_failed_producer_visible_to_consumer():
    owner = _owner()
    owner.publish_failure(RuntimeError("producer crashed"))
    assert owner.join(1.0) == JoinDecision.FAILED


def test_join_timeout_when_never_published():
    owner = _owner()
    assert owner.join(0.05) == JoinDecision.TIMEOUT


def test_take_release_lifecycle_and_strong_lifetime():
    owner = _owner()
    payload = {"destination": object()}
    owner.publish_device_ready(payload)
    h1 = owner.take("source_side")
    h2 = owner.take("demand_side")
    assert owner.payload is payload
    assert len(owner.take_ledger) == 2
    owner.release()
    assert owner.state.value != "released"
    owner.release()
    assert owner.state.value == "released"
    with pytest.raises(GoldenError):
        owner.release()


def test_take_forbidden_after_failure():
    owner = _owner()
    owner.publish_failure(RuntimeError("x"))
    with pytest.raises(GoldenError):
        owner.take("demand")


def test_illegal_transitions_raise():
    owner = _owner()
    with pytest.raises(GoldenError):
        owner.mark_bind_ready()
    owner.publish_device_ready()
    with pytest.raises(GoldenError):
        owner.publish_device_ready()


def test_join_or_adopt_semantics():
    reg = GoldenOwnerRegistry()
    decision, owner = reg.join_or_adopt(ModelRole.VAE, 0.1)
    assert decision == JoinDecision.ADOPTED
    assert owner is None
    producer = GoldenModelOwner(ModelRole.VAE, "vae-ident")
    reg.register(producer)
    timer = threading.Timer(0.03, producer.publish_device_ready, args=("v",))
    timer.start()
    try:
        decision, owner = reg.join_or_adopt(ModelRole.VAE, 2.0)
        assert decision == JoinDecision.JOINED
        assert owner is producer
    finally:
        timer.join()
