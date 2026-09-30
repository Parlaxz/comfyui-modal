"""Contract for the restore-boundary container facts capture.

Model-load bandwidth on the C0 parallel lane spans roughly 1.5-7 GB/s between
otherwise identical runs.  The only known mechanism that would force a cold
model re-read is a failed memory-snapshot restore, but neither the execution
region nor the snapshot outcome reaches the produced artifacts, so they are
captured at the restore boundary.

The property that matters most: this is observation-only instrumentation and
must never be able to fail a production request.  These tests pin that.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SERIAL = ROOT / "comfymodal_runtime" / "golden_serial.py"


def _load_helper(os_module=None):
    """Import the helper directly; golden_serial imports ComfyUI-only modules.

    ``os_module`` lets a test inject a stand-in environment without touching the
    real ``os.environ``, which pytest itself depends on.
    """
    source = SERIAL.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_container_restore_facts":
            module = ast.Module(body=[node], type_ignores=[])
            namespace = {"os": os_module if os_module is not None else __import__("os")}
            exec(compile(module, str(SERIAL), "exec"), namespace)
            return namespace["_container_restore_facts"]
    raise AssertionError("_container_restore_facts not found in golden_serial")


class _FakeEnviron(dict):
    def get(self, key, default=None):
        return dict.get(self, key, default)


def _fake_os(env=None):
    """Module-like stand-in exposing only what the helper touches."""
    return SimpleNamespace(environ=_FakeEnviron(env or {}))


def test_helper_is_defined_and_never_raises_on_missing_env():
    helper = _load_helper(_fake_os({}))
    facts = helper()
    assert isinstance(facts, dict)
    # The snapshot flag must always resolve to a bool, never None: it is the
    # field that decides whether a restore failure means a cold start.
    assert isinstance(facts["memory_snapshot_enabled"], bool)


def test_snapshot_flag_defaults_to_true_and_honours_false_tokens():
    for token in (None, "0", "false", "no", "off"):
        env = {} if token is None else {"COMFYMODAL_V2_ENABLE_MEMORY_SNAPSHOT": token}
        helper = _load_helper(_fake_os(env))
        expected = token is None or token.lower() not in {"0", "false", "no", "off"}
        assert helper()["memory_snapshot_enabled"] is expected


def test_probe_failures_degrade_to_none_instead_of_raising():
    """A raising os.environ must not propagate: telemetry cannot fail a run."""

    class ExplodingEnviron:
        def get(self, *_args, **_kwargs):
            raise RuntimeError("probe failure")

    class ExplodingOs:
        environ = ExplodingEnviron()

    helper = _load_helper(ExplodingOs)
    facts = helper()
    assert facts["memory_snapshot_enabled"] is None


def test_restore_baseline_carries_container_facts():
    """The capture must actually reach the persisted restore baseline.

    The caller discards the returned baseline, so the facts must also be
    recorded on the stage itself or they never reach the artifacts.
    """
    source = SERIAL.read_text(encoding="utf-8", errors="replace")
    assert '"container_facts": _container_restore_facts(),' in source
    assert 'container_facts=baseline["container_facts"],' in source


def test_probe_uses_stable_names_and_captures_region_when_present():
    helper = _load_helper(_fake_os({"MODAL_REGION": "eu-south"}))
    facts = helper()
    assert facts["modal_region"] == "eu-south"


@pytest.mark.parametrize("name", ["MODAL_CONTAINER_ID", "MODAL_TASK_ID"])
def test_absent_probes_are_omitted_rather_than_recorded_as_none(name):
    helper = _load_helper(_fake_os({}))
    facts = helper()
    assert name.lower() not in facts
