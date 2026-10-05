"""v2ctl must bake one deploy_id that the serving runtime reports back.

The chain under test:

    deploy construction -> expected deploy_id in the class environment
                       -> runtime freezes it at import
                       -> the Golden request reports it
                       -> validation compares expected vs same-request

The stale-snapshot case is reproduced by freezing a different id than the one
the caller expects, which is exactly what a container restored from an older
deployment does.
"""

from __future__ import annotations

import contextlib
import importlib
import os

import pytest

from comfymodal_runtime import deploy_identity as di

pytestmark = pytest.mark.fast_unit


@contextlib.contextmanager
def served_by(deploy_id_value):
    """Run as if the executing deployment carried `deploy_id_value`."""
    previous = os.environ.get(di.DEPLOY_ID_ENV)
    if deploy_id_value is None:
        os.environ.pop(di.DEPLOY_ID_ENV, None)
    else:
        os.environ[di.DEPLOY_ID_ENV] = deploy_id_value
    try:
        importlib.reload(di)
        yield di
    finally:
        if previous is None:
            os.environ.pop(di.DEPLOY_ID_ENV, None)
        else:
            os.environ[di.DEPLOY_ID_ENV] = previous
        importlib.reload(di)


def _deploy_id(revision):
    return di.compute_deploy_id(
        source_revision=revision,
        resolved_config={"COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND": "sage"},
        target={"app": "app-x", "class_name": "ComfyAPI_H100", "method": "run"},
        resources={"gpu": "H100", "cpu": 16, "memory_mb": 32768},
    )


def test_golden_envelope_reports_the_same_deploy_id_the_caller_expects():
    from comfymodal_runtime import golden_envelope as env
    import io
    from contextlib import redirect_stdout

    expected = _deploy_id("rev-a")
    with served_by(expected) as module:
        env.ENVELOPE.clear()
        env.record("req-1", {"method_entry_mono_ns": 1000})
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            env.emit_envelope("req-1")
        line = buffer.getvalue()
        # Compare inside the block: afterwards the module has been restored.
        ok, _ = module.verify(expected)

    assert "deploy_id=%s" % expected in line
    assert ok is True


def test_envelope_reports_the_old_id_when_a_stale_snapshot_serves_the_request():
    from comfymodal_runtime import golden_envelope as env
    import io
    from contextlib import redirect_stdout

    stale = _deploy_id("rev-a")
    expected = _deploy_id("rev-b")

    with served_by(stale) as module:
        env.ENVELOPE.clear()
        env.record("req-2", {"method_entry_mono_ns": 1000})
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            env.emit_envelope("req-2")
        line = buffer.getvalue()
        ok, reason = module.verify(expected)

    # The stale container honestly reports the deployment it actually is...
    assert "deploy_id=%s" % stale in line
    assert expected not in line
    # ...and that is what makes the request INVALID rather than merely suspect.
    assert ok is False
    assert "mismatch" in reason


def test_cli_bakes_the_deploy_id_into_the_deploy_environment():
    """The deploy path must publish the id the runtime will report."""
    import inspect

    from tools.v2_control import cli

    source = inspect.getsource(cli._canonical_metadata_env)
    # The attribute, not its value: the env var name comes from deploy_identity.
    assert "DEPLOY_ID_ENV" in source
    assert "compute_deploy_id" in source


def test_deploy_id_env_is_declared_in_the_registry_as_runtime_exposed():
    """It reaches the container through the single config authority."""
    from comfymodal_runtime import config_schema

    assert config_schema.is_runtime_exposed(di.DEPLOY_ID_ENV)


def test_verify_rejects_when_the_runtime_has_no_deploy_id():
    """An unidentifiable deployment is never treated as a correct one."""
    with served_by(None) as module:
        ok, reason = module.verify(_deploy_id("rev-a"))
    assert ok is False
    assert "no deploy_id" in reason