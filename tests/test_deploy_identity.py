"""One deploy_id must identify the deployment that actually served a request.

These are the correctness cases that matter, and each maps to a real historical
failure:

  * deterministic   -- the same deployment always yields the same id
  * deploy A / B    -- two deployments are distinguishable
  * stale snapshot  -- an interpreter restored from an older deployment reports
                       the OLD id, so a request expecting B is rejected
  * wrong deployment-- a request expecting A served by B is rejected
  * missing         -- an unidentifiable deployment is never accepted

The stale-snapshot case needs no filesystem manipulation: the id is frozen at
import from the environment Modal bakes into the class, so reloading the module
with a different environment value reproduces exactly what a restored snapshot
does.
"""

from __future__ import annotations

import contextlib
import importlib
import os

import pytest

from comfymodal_runtime import deploy_identity as di

pytestmark = pytest.mark.fast_unit

CONFIG = {"COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND": "sage"}
TARGET = {"app": "app-x", "class": "ComfyAPI_H100", "method": "run"}
RESOURCES = {"gpu": "H100", "cpu": 16, "memory_mb": 32768}


def _id(**overrides):
    kwargs = {
        "source_revision": "abc123",
        "resolved_config": CONFIG,
        "target": TARGET,
        "resources": RESOURCES,
    }
    kwargs.update(overrides)
    return di.compute_deploy_id(**kwargs)


def test_deploy_id_is_deterministic():
    assert _id() == _id()


def test_deploy_id_is_a_full_sha256():
    value = _id()
    assert len(value) == 64
    assert all(c in "0123456789abcdef" for c in value)


def test_two_deployments_are_distinguishable():
    assert _id() != _id(source_revision="def456")
    assert _id() != _id(resolved_config={"COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND": "sdpa"})
    assert _id() != _id(target=dict(TARGET, method="other"))
    assert _id() != _id(resources=dict(RESOURCES, cpu=8))


def test_request_only_and_diagnostic_inputs_do_not_change_the_id():
    """Only deployment-relevant inputs may affect identity."""
    baseline = _id()
    # Extra keys that are not deployment-relevant are ignored.
    assert baseline == di.compute_deploy_id(
        source_revision="abc123",
        resolved_config=CONFIG,
        target=TARGET,
        resources={**RESOURCES, "some_diagnostic": "x"},
    )
    # Absent resources are treated as empty rather than failing.
    assert di.compute_deploy_id(
        source_revision="abc123",
        resolved_config=CONFIG,
        target=TARGET,
        resources={},
    ) == di.compute_deploy_id(
        source_revision="abc123",
        resolved_config=CONFIG,
        target=TARGET,
        resources=None,
    )


def test_key_order_does_not_change_the_id():
    a = di.compute_deploy_id(
        source_revision="r",
        resolved_config={"B": "2", "A": "1"},
        target={"app": "x", "class": "C"},
    )
    b = di.compute_deploy_id(
        source_revision="r",
        resolved_config={"A": "1", "B": "2"},
        target={"class": "C", "app": "x"},
    )
    assert a == b


@contextlib.contextmanager
def deployed_as(value):
    """Reload deploy_identity as if the process had been deployed with `value`.

    Yields inside the reloaded state. The previous environment is restored on
    exit, so the assertions must run inside the with block -- reading the id
    afterwards would observe the restored value, not the frozen one.
    """
    previous = os.environ.get(di.DEPLOY_ID_ENV)
    if value is None:
        os.environ.pop(di.DEPLOY_ID_ENV, None)
    else:
        os.environ[di.DEPLOY_ID_ENV] = value
    try:
        importlib.reload(di)
        yield di
    finally:
        if previous is None:
            os.environ.pop(di.DEPLOY_ID_ENV, None)
        else:
            os.environ[di.DEPLOY_ID_ENV] = previous
        importlib.reload(di)


def test_request_reports_the_deployment_that_served_it():
    deploy_a = _id(source_revision="aaa")
    deploy_b = _id(source_revision="bbb")

    with deployed_as(deploy_a) as module:
        assert module.deploy_id() == deploy_a
        ok, _ = module.verify(deploy_a)
        assert ok is True


def test_stale_snapshot_reports_its_own_old_id_and_is_rejected():
    """The case that motivated this: a restored snapshot serving a newer deploy."""
    deploy_a = _id(source_revision="aaa")
    deploy_b = _id(source_revision="bbb")

    with deployed_as(deploy_a) as stale:
        # The snapshot still believes it is A...
        assert stale.deploy_id() == deploy_a
        # ...but the caller expects B.
        ok, reason = stale.verify(deploy_b)
        assert ok is False
        assert "mismatch" in reason
        assert deploy_a in reason and deploy_b in reason


def test_wrong_deployment_is_rejected():
    deploy_a = _id(source_revision="aaa")
    deploy_b = _id(source_revision="bbb")

    with deployed_as(deploy_b) as serving_b:
        assert serving_b.deploy_id() == deploy_b
        ok, reason = serving_b.verify(deploy_a)
        assert ok is False
        assert "mismatch" in reason


def test_missing_id_on_either_side_fails_closed():
    with deployed_as(None) as without:
        assert without.deploy_id() == ""
        ok, reason = without.verify(_id())
        assert ok is False
        assert "no deploy_id" in reason

    with deployed_as(_id()) as present:
        ok, reason = present.verify("")
        assert ok is False
        assert "no expected deploy_id" in reason


def test_verify_is_cheap_enough_for_the_request_path():
    """Identity must not do filesystem work per request."""
    import inspect

    source = inspect.getsource(di.verify) + inspect.getsource(di.deploy_id)
    for forbidden in ("open(", "hashlib", "sha256", "os.stat", "read_bytes"):
        assert forbidden not in source, (
            "request-path identity must not use %s" % forbidden
        )