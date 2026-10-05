"""The generated runtime environment must match the pre-refactor behaviour.

This is the differential contract for unifying the configuration authority.

Before the refactor, ``modal_app._runtime_env`` was a handwritten list of ~180
``os.environ.get(...)`` entries and ``config/v2/flag_registry.toml`` was
documentation that had drifted from it: 26 shared flags carried different
defaults, 74 emitted keys were unregistered, and 54 registered flags were never
emitted.

The migration made the registry the single authority by recording what
deployments actually emit, so generating the environment from it must reproduce
the old output exactly. ``runtime_env_contract.json`` is the pre-refactor
contract, captured from the handwritten implementation before it was deleted.

These tests exercise ``config_schema`` rather than importing ``modal_app``:
the projection is the whole contract, and ``config_schema`` depends only on
tomllib. ``_runtime_env`` is a thin wrapper over exactly that projection plus
three explicit entries, which is checked here by reading its source instead of
importing a 24k-line module that pulls in torch.
"""

from __future__ import annotations

import ast
import io
import json
import os
from pathlib import Path

import pytest

from comfymodal_runtime import config_schema

pytestmark = pytest.mark.fast_unit

CONTRACT = Path(__file__).with_name("runtime_env_contract.json")
MODAL_APP = Path(__file__).resolve().parents[1] / "comfymodal_runtime" / "modal_app.py"

# Keys _runtime_env still sets explicitly, because their value is not a static
# flag default: derived from the target spec or a module constant, or computed
# from another flag or from resolved resources. Everything else comes from the
# registry projection.
EXPLICIT_LITERAL_KEYS = {
    "COMFYMODAL_V2_APP_NAME",
    "COMFYMODAL_CUSTOM_NODE_DELIVERY",
    "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST",
}
EXPLICIT_ASSIGNED_KEYS = {
    "COMFYMODAL_RESTORE_CLIP_READ_PROBE_SOURCE",
    "COMFYMODAL_V2_CPU_REQUEST",
    "COMFYMODAL_V2_MEMORY_MB",
    "COMFYMODAL_V2_MEMORY_REQUEST",
    "COMFYMODAL_V2_RUNTIME_SHAPE_FINGERPRINT",
    "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER",
    "COMFYMODAL_V2_STATE_VOLUME_ROOT",
    "COMFYMODAL_V2_THREAD_POLICY",
}
EXPLICIT_KEYS = EXPLICIT_LITERAL_KEYS | EXPLICIT_ASSIGNED_KEYS

SCENARIOS = {
    "defaults": {},
    "experimental_arm": {
        "COMFYMODAL_GOLDEN_IO_PROCESS_V2": "1",
        "COMFYMODAL_GOLDEN_IO_PROCESS_V2_SOURCE_GEOMETRY": "qd4_32",
        "COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND": "sage",
        "COMFYMODAL_GOLDEN_C0_HOST_REGISTER": "1",
        "COMFYMODAL_GOLDEN_CLIP_SKELETON_OVERLAP": "1",
    },
    "resource_shape": {
        "COMFYMODAL_V2_GPU": "H100",
        "COMFYMODAL_V2_CPU_REQUEST": "16",
        "COMFYMODAL_V2_MEMORY_MB": "32768",
        "COMFYMODAL_V2_BASELINE_CPU_REQUEST": "12",
        "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST": "8192",
    },
    "explicit_override": {
        "COMFYMODAL_V2_CLIP_FASTSAFE_THREADS": "4",
        "COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES": "16777216",
        "COMFYMODAL_ENABLE_GPU_SNAPSHOT": "1",
    },
    "host_only_set": {
        "COMFYMODAL_GOLDEN_EXHAUSTIVE_PROFILE": "1",
        "COMFYMODAL_V2CTL_PROFILE": "some-profile",
    },
    "explicit_empty": {
        "COMFYMODAL_V2_MEMORY_MB": "",
        "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "",
    },
}


@pytest.fixture(scope="module")
def contract():
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


@pytest.fixture
def clean_flag_env(monkeypatch):
    """Remove every flag-shaped variable, including any set by a parent.

    monkeypatch only reverts what a test changed, so ambient values must be
    removed explicitly before the scenario under test is applied.
    """
    for name in list(os.environ):
        if name.startswith("COMFYMODAL") or name.startswith("V2_"):
            monkeypatch.delenv(name, raising=False)
    return monkeypatch


def _schema_env(overrides):
    """The generated projection for a synthetic host environment.

    Builds a plain dict instead of mutating os.environ: the projection only
    reads the mapping it is handed, and mutating the real environment would
    leak into later tests because monkeypatch cannot undo an out-of-band change.
    """
    base = {
        name: value
        for name, value in os.environ.items()
        if not (name.startswith("COMFYMODAL") or name.startswith("V2_"))
    }
    base.update(overrides)
    return config_schema.project_runtime_env(base)


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_generated_env_matches_pre_refactor_contract(scenario, contract):
    """OLD handwritten _runtime_env == NEW generated projection."""
    old = contract["scenarios"][scenario]
    # The contract also contains keys the runtime sets explicitly outside the
    # schema; compare the schema's share against the old contract exactly.
    added = _added_after_contract()
    comparable = {
        k: v for k, v in old.items() if k not in _explicit_keys(contract)
    }
    new = {
        k: v for k, v in _schema_env(SCENARIOS[scenario]).items() if k not in added
    }

    assert sorted(set(new) - set(comparable)) == [], "projection added keys"
    assert sorted(set(comparable) - set(new)) == [], "projection dropped keys"
    differing = {k: (comparable[k], new[k]) for k in comparable if comparable[k] != new[k]}
    assert differing == {}, "projection changed values: %r" % differing


def _added_after_contract():
    """Keys added to the schema after the pre-refactor contract was captured.

    COMFYMODAL_V2_DEPLOY_ID arrived with the single deploy_id. It is a deliberate
    addition rather than drift, so the differential excludes exactly that key
    instead of being weakened.
    """
    added = {"COMFYMODAL_V2_DEPLOY_ID"}
    return added & set(config_schema.runtime_env_fields())


def _explicit_keys(contract):
    """Keys the runtime sets outside the schema projection.

    Derived from the frozen contract rather than hardcoded: whatever the
    pre-refactor implementation emitted that the registry does not declare is
    exactly the set that must remain explicit in _runtime_env.
    """
    return set(contract["scenarios"]["defaults"]) - set(
        config_schema.runtime_env_fields()
    )


def test_projection_covers_every_contract_key_except_the_explicit_ones(contract):
    projected = set(config_schema.runtime_env_fields()) - _added_after_contract()
    old = set(contract["scenarios"]["defaults"])
    assert projected == old - _explicit_keys(contract)
    assert _explicit_keys(contract), "expected some explicitly-set keys"


def test_no_key_is_both_schema_projected_and_handwritten():
    """The invariant that makes this a single authority.

    Any key the registry projects must not also appear as a per-flag
    ``os.environ.get(NAME, default)`` entry in _runtime_env. If one did, the two
    authorities could disagree again -- which is the defect being removed.
    """
    source = MODAL_APP.read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "_runtime_env"
    )
    literal = None
    for node in ast.walk(fn):
        if isinstance(node, ast.AnnAssign) and isinstance(node.value, ast.Dict):
            if getattr(node.target, "id", None) == "env":
                literal = node.value
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            if any(getattr(t, "id", None) == "env" for t in node.targets):
                literal = node.value
    assert literal is not None, "could not find the env dict literal"

    handwritten_passthrough = set()
    for key, value in zip(literal.keys, literal.values):
        if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
            continue
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Attribute)
            and value.func.attr == "get"
        ):
            handwritten_passthrough.add(key.value)

    projected = set(config_schema.runtime_env_fields())
    duplicated = sorted(handwritten_passthrough & projected)
    assert duplicated == [], (
        "these keys are both schema-projected and handwritten in _runtime_env: %r"
        % duplicated
    )
    # The projection must actually be consumed.
    assert "config_schema.project_runtime_env" in source
    # And the one remaining passthrough computes its default from another flag.
    assert handwritten_passthrough <= {
        "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST"
    }


def test_registry_only_flag_reaches_the_container_without_touching_runtime_env(
    clean_flag_env,
):
    """The invariant: define once in the registry, get it in the deployed env."""
    clean_flag_env.setenv("COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND", "sdpa")

    env = config_schema.project_runtime_env(os.environ)
    assert env["COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND"] == "sdpa"
    assert config_schema.is_runtime_exposed("COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND")

    # The deploy path does not name the flag at all.
    source = MODAL_APP.read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "_runtime_env"
    )
    assert "COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND" not in ast.get_source_segment(
        source, fn
    )


def test_host_only_flag_is_never_projected(clean_flag_env):
    """runtime_exposed = false must not be sent even when set on the host."""
    clean_flag_env.setenv("COMFYMODAL_GOLDEN_EXHAUSTIVE_PROFILE", "1")

    assert not config_schema.is_runtime_exposed("COMFYMODAL_GOLDEN_EXHAUSTIVE_PROFILE")
    assert "COMFYMODAL_GOLDEN_EXHAUSTIVE_PROFILE" not in (
        config_schema.project_runtime_env(os.environ)
    )


def test_registry_default_is_injected_when_host_is_silent(clean_flag_env):
    env = config_schema.project_runtime_env(os.environ)
    # Previously-unregistered keys now arrive with their historical defaults.
    assert env["COMFYMODAL_GOLDEN_IO_PROCESS_V2_SOURCE_GEOMETRY"] == "qd4_32"
    assert env["COMFYMODAL_GOLDEN_C0_HOST_REGISTER"] == "0"


def test_empty_string_value_is_preserved_not_replaced(clean_flag_env):
    """An explicit empty means "unset, container decides" and must survive."""
    clean_flag_env.setenv("COMFYMODAL_V2_VARIANCE_DIAGNOSTICS", "")
    env = config_schema.project_runtime_env(os.environ)
    assert env["COMFYMODAL_V2_VARIANCE_DIAGNOSTICS"] == ""


def test_registry_declares_runtime_exposed_for_every_projected_key():
    flags = config_schema.load_registry()
    declared = {f["name"] for f in flags if f.get("runtime_exposed") is True}
    assert declared == set(config_schema.runtime_env_fields())