"""Audit tests for the P9 VAE residency redundancy question.

Two jobs, both deliberately cheap:

1. Pin the audit probe's contract (default-OFF, read-only, never raises) so a
   future refactor cannot quietly turn diagnostics into behaviour.
2. Pin the structural facts the VAE-residency classification rests on.  If
   someone later moves a ``load_models_gpu`` call into ``golden_vae_load``, or
   stops seeding the runner with the preloaded VAE object, the "the decode-time
   load is first-time DynamicVRAM activation" conclusion becomes false and these
   tests fail instead of the conclusion going stale.

The P9 numbers these tests protect against re-deriving live in
``reports/golden_profiler_p9opt/``; they are checked here only as a
double-counting guard on the timing nesting, which is the one arithmetic error
the audit was explicitly asked to avoid.
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path

import pytest

from comfymodal_runtime import vae_residency_audit as audit


pytestmark = pytest.mark.fast_unit

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_SERIAL = REPO_ROOT / "comfymodal_runtime" / "golden_serial.py"
P9OPT = REPO_ROOT / "reports" / "golden_profiler_p9opt"


# ── gate contract ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("raw", ["1", "true", "TRUE", "Yes", "on", " On "])
def test_gate_truthy_values_enable(raw):
    assert audit.enabled({audit.GATE_ENV: raw}) is True


@pytest.mark.parametrize("raw", ["", "0", "false", "no", "off", "maybe", "2"])
def test_gate_non_truthy_values_stay_off(raw):
    assert audit.enabled({audit.GATE_ENV: raw}) is False


def test_gate_defaults_off_when_absent():
    assert audit.enabled({}) is False


def test_gate_defaults_off_in_a_clean_process(monkeypatch):
    monkeypatch.delenv(audit.GATE_ENV, raising=False)
    assert audit.enabled() is False


# ── read-only contract ───────────────────────────────────────────────────────


class _Recorder:
    def __init__(self):
        self.events = []

    def event(self, name, **fields):
        self.events.append((name, fields))


class _Tensor:
    def __init__(self, device, numel=4, itemsize=2):
        self.device = device
        self._numel = numel
        self._itemsize = itemsize

    def numel(self):
        return self._numel

    def element_size(self):
        return self._itemsize


class _Module:
    def __init__(self, params, modules=()):
        self._params = list(params)
        self._modules = list(modules)

    def parameters(self):
        return iter(self._params)

    def modules(self):
        return iter([self] + self._modules)


class _Model:
    def __init__(self, module, pins, vbars):
        self.dynamic_pins = pins
        self.dynamic_vbars = vbars
        self.model_loaded_weight_memory = 0
        self.device = "cpu"
        self._module = module

    def parameters(self):
        return self._module.parameters()

    def modules(self):
        return self._module.modules()


class _Patcher:
    """Minimal duck-type of the ModelPatcherDynamic read surface.

    Any attribute the probe writes to raises, so a probe that stopped being
    read-only fails loudly instead of silently mutating request state.
    """

    def __init__(self, model):
        object.__setattr__(self, "model", model)
        object.__setattr__(self, "load_device", "cuda:0")
        object.__setattr__(self, "offload_device", "cpu")
        object.__setattr__(self, "backup", {})
        object.__setattr__(self, "backup_buffers", {})

    def __setattr__(self, name, value):
        raise AssertionError(f"probe mutated patcher attribute {name!r}")

    def is_dynamic(self):
        return True

    def model_size(self):
        return 1024

    def loaded_size(self):
        return 512


class _Vae:
    def __init__(self, patcher, module):
        self.patcher = patcher
        self.first_stage_model = module


def _preloaded_vae():
    """A patcher in the exact state golden_vae_load leaves it in."""
    pins = {
        "cuda:0": {
            "weights": (None, [], [-1], [0], [0], {}),
            "patches": (None, [], [-1], [0], [0], {}),
            "weights-loaded": (None, [], [-1], [0], [0], {}),
            "patches-loaded": (None, [], [-1], [0], [0], {}),
            "hostbufs_initialized": False,
            "failed": False,
            "active": False,
            "current_prompt": False,
        }
    }
    module = _Module([_Tensor("cuda:0"), _Tensor("cpu")])
    model = _Model(module, pins, {})
    return _Vae(_Patcher(model), module)


def test_probe_reports_preload_state_without_mutating():
    vae = _preloaded_vae()
    pin_state_before = dict(vae.patcher.model.dynamic_pins["cuda:0"])

    snapshot = audit.probe("before_golden_vae_decode", vae)

    pin_state_after = vae.patcher.model.dynamic_pins["cuda:0"]
    assert dict(pin_state_after) == pin_state_before
    assert vae.patcher.backup == {}
    assert snapshot["patcher_class"] == "_Patcher"
    assert snapshot["is_dynamic"] is True
    assert snapshot["load_device"] == "cuda:0"
    assert snapshot["model_size_bytes"] == 1024
    assert snapshot["loaded_size_bytes"] == 512


def test_probe_exposes_the_dynamicvram_activation_flags():
    snapshot = audit.probe("before_golden_vae_decode", _preloaded_vae())
    pin = snapshot["dynamic_pins"]["devices"]["cuda:0"]
    # These two flags are the whole basis of the classification: they are False
    # before decode precisely because no DynamicVRAM load has happened yet.
    assert pin["hostbufs_initialized"] is False
    assert pin["active"] is False
    # No vbar block and no weight-function wiring exist before the first load().
    assert snapshot["module_markers"]["modules_with_vbar_block"] == 0
    assert snapshot["module_markers"]["modules_with_weight_function_attr"] == 0
    assert snapshot["aimdo"]["vbar_present"] is False


def test_probe_counts_parameter_bytes_per_device():
    snapshot = audit.probe("before_golden_vae_decode", _preloaded_vae())
    params = snapshot["first_stage_params"]
    assert params["target_device"] == "cuda:0"
    assert params["param_count"] == 2
    assert params["param_bytes_total"] == 16
    assert params["param_bytes_on_target_device"] == 8
    assert params["param_bytes_on_cpu"] == 8


def test_probe_survives_a_vae_without_a_patcher():
    snapshot = audit.probe("after_golden_vae_decode", object())
    assert snapshot["patcher_present"] is False
    assert snapshot["vae_object_id"]


def test_probe_never_raises_on_a_broken_patcher():
    class Exploding:
        @property
        def model(self):
            raise RuntimeError("nope")

        def is_dynamic(self):
            raise RuntimeError("nope")

    vae = _Vae.__new__(_Vae)
    vae.patcher = Exploding()
    vae.first_stage_model = None
    snapshot = audit.probe("x", vae)
    assert snapshot["patcher_present"] is True
    assert snapshot["is_dynamic"] is None


def test_record_is_a_noop_when_the_gate_is_off(monkeypatch):
    monkeypatch.delenv(audit.GATE_ENV, raising=False)
    recorder = _Recorder()
    assert audit.record(recorder, "before_golden_vae_decode", _preloaded_vae()) is None
    assert recorder.events == []


def test_record_emits_one_event_when_the_gate_is_on(monkeypatch):
    monkeypatch.setenv(audit.GATE_ENV, "1")
    recorder = _Recorder()
    snapshot = audit.record(
        recorder, "before_golden_vae_decode", _preloaded_vae()
    )
    assert snapshot is not None
    assert len(recorder.events) == 1
    name, fields = recorder.events[0]
    assert name == audit.EVENT_NAME
    assert fields["label"] == "before_golden_vae_decode"
    assert fields["schema_version"] == 1


def test_record_swallows_a_broken_recorder(monkeypatch):
    monkeypatch.setenv(audit.GATE_ENV, "1")

    class Broken:
        def event(self, *_args, **_kwargs):
            raise RuntimeError("telemetry down")

    assert audit.record(Broken(), "x", _preloaded_vae()) is not None


def test_module_imports_without_torch_or_comfyui():
    """The probe must be import-safe on a developer machine.

    ``torch``, ``comfy.*`` and ``comfy_aimdo`` are all absent here; importing
    the module anyway is what keeps the tests above meaningful.
    """
    assert "torch" not in globals()
    assert audit.probe("label", None)["patcher_present"] is False


# ── structural facts the classification depends on ───────────────────────────


def _function_node(path: Path, name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            return node  # type: ignore[return-value]
    raise AssertionError(f"{name} not found in {path}")


def _called_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if isinstance(func, ast.Attribute):
            names.add(func.attr)
        elif isinstance(func, ast.Name):
            names.add(func.id)
    return names


def test_golden_vae_load_never_loads_the_vae_through_model_management():
    """`golden_vae_load` must not call the GPU load path on the VAE patcher.

    This is the load-bearing fact for "the decode-time load is the first
    DynamicVRAM activation".  If a future change adds `load_models_gpu` or
    `partially_load` here, the decode-time cost stops being first-time setup
    and the classification in reports/P9_VAE_RESIDENCY_AUDIT.md is stale.
    """
    body = _function_node(GOLDEN_SERIAL, "golden_vae_load")
    called = _called_names(body)
    assert "load_models_gpu" not in called
    assert "partially_load" not in called
    assert "load_model_gpu" not in called
    assert "partially_unload" not in called


def test_golden_vae_load_rejects_a_non_dynamic_core_patcher():
    """Preload is fail-closed on a dynamic patcher before construction."""
    body = _function_node(GOLDEN_SERIAL, "golden_vae_load")
    assert "require_dynamic_core_model_patcher" in _called_names(body)


def test_golden_vae_load_proves_storage_adoption_before_returning():
    body = _function_node(GOLDEN_SERIAL, "golden_vae_load")
    assert "validate_qd_adoption" in _called_names(body)


def test_golden_vae_decode_seeds_the_preloaded_vae_object():
    """Decode must consume `session.vae` itself, not re-resolve a VAE."""
    body = _function_node(GOLDEN_SERIAL, "golden_vae_decode")
    seed_calls = [
        child
        for child in ast.walk(body)
        if isinstance(child, ast.Call)
        and isinstance(child.func, ast.Attribute)
        and child.func.attr == "seed"
    ]
    assert len(seed_calls) == 1
    # `runner.seed(node_map.vae_loader_id, [[session.vae]])` -- the preloaded
    # object itself, not a re-resolved or re-loaded VAE.
    seeded = seed_calls[0].args[1]
    assert isinstance(seeded, ast.List)
    assert isinstance(seeded.elts[0], ast.List)
    assert seeded.elts[0].elts[0].attr == "vae"


def test_golden_vae_decode_does_not_bypass_the_canonical_load_path():
    """No VAE load short-circuit may reappear in the decode stage."""
    body = _function_node(GOLDEN_SERIAL, "golden_vae_decode")
    called = _called_names(body)
    for forbidden in (
        "load_models_gpu",
        "partially_load",
        "unload_model_clones",
        "free_memory",
    ):
        assert forbidden not in called


def test_probe_module_is_referenced_only_from_the_three_audit_sites():
    """Keep the instrumentation surface explicit and minimal."""
    source = GOLDEN_SERIAL.read_text(encoding="utf-8")
    assert source.count("from .vae_residency_audit import record") == 2
    assert source.count('_vae_residency_record(rec, "') == 3


# ── timing nesting: the double-counting guard ────────────────────────────────


def _p9opt_trees() -> dict[str, str]:
    """Map trace-id suffix -> per-stage call-tree markdown."""
    return {
        path.stem.replace("golden_stage_trees_", ""): path.read_text(encoding="utf-8")
        for path in P9OPT.glob("golden_stage_trees_*.md")
    }


def _stage_section(text: str, stage: str) -> str:
    marker = f"## `{stage}`"
    start = text.index(marker)
    rest = text[start + len(marker):]
    nxt = rest.find("\n## `")
    return rest if nxt < 0 else rest[:nxt]


def _tree_frames(section: str) -> list[tuple[str, int, float]]:
    """Parse a profiler call tree into (function, indent, inclusive_wall_ms).

    The artifact format is two lines per frame::

        - `ModelPatcherDynamic.partially_load`
          wall **65.542 ms**  self **0.079 ms**  `model_patcher.py:2141`
    """
    frames: list[tuple[str, int, float]] = []
    lines = section.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("- `") or not stripped.endswith("`"):
            continue
        function = stripped[3:-1].strip()
        if not function:
            continue
        indent = len(line) - len(line.lstrip())
        wall = 0.0
        for follow in lines[index + 1:index + 2]:
            match = re.search(r"wall \*\*([0-9.]+)\s*ms\*\*", follow)
            if match:
                wall = float(match.group(1))
        frames.append((function, indent, wall))
    return frames


def _frame(section: str, function: str) -> tuple[int, float]:
    for name, indent, wall in _tree_frames(section):
        if name == function:
            return indent, wall
    raise AssertionError(f"{function} not found in stage section")


@pytest.mark.parametrize("suffix", ["25172b0c", "ad2f1cf4", "ddb6c39a"])
def test_partially_load_is_nested_inside_load_models_gpu(suffix):
    """`partially_load` must be a CHILD of `load_models_gpu`, never a sibling.

    This is the arithmetic the audit was told not to get wrong: adding
    `load_models_gpu` and `partially_load` would double count the nested call.
    """
    section = _stage_section(_p9opt_trees()[suffix], "golden_vae_decode")
    lmg_indent, _ = _frame(section, "load_models_gpu")
    pl_indent, _ = _frame(section, "ModelPatcherDynamic.partially_load")
    model_load_indent, _ = _frame(section, "LoadedModel.model_load")
    assert model_load_indent > lmg_indent
    assert pl_indent > model_load_indent, "partially_load is not nested under load_models_gpu"


@pytest.mark.parametrize(
    "suffix,expected_lmg",
    [("25172b0c", 73.028), ("ad2f1cf4", 78.091), ("ddb6c39a", 110.675)],
)
def test_removable_wall_is_bounded_by_the_outer_inclusive_time(suffix, expected_lmg):
    """MAX_NON_OVERLAPPING_REMOVABLE is the OUTER inclusive, never the sum.

    Guards the specific error of 73.0 + 65.5 / 110.7 + 100.1.
    """
    section = _stage_section(_p9opt_trees()[suffix], "golden_vae_decode")
    _, lmg = _frame(section, "load_models_gpu")
    _, pl = _frame(section, "ModelPatcherDynamic.partially_load")
    assert lmg == pytest.approx(expected_lmg, abs=0.01)
    assert pl < lmg
    # The naive sum would be ~90% larger than what can actually be removed.
    assert (lmg + pl) / lmg > 1.8


def test_p9opt_artifacts_are_present_for_every_referenced_run():
    """The report cites three traces; all three must still be on disk."""
    trees = _p9opt_trees()
    for suffix in ("25172b0c", "ad2f1cf4", "ddb6c39a"):
        assert suffix in trees
        assert os.path.exists(
            P9OPT / f"golden_stage_trees_{suffix}.md"
        )