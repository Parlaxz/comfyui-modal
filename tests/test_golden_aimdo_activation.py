"""Offline tests for comfymodal_runtime/golden_aimdo_activation.py.

Self-contained: upstream ``comfy.*`` and ``comfy_aimdo`` are replaced by fake
modules injected into ``sys.modules`` (the import system consults sys.modules
first, so no filesystem/GPU/aimdo-DLL access ever happens). The module under
test is loaded fresh per test via importlib so its process-wide idempotency
cache never leaks between tests.

Covers:
- gate unset/falsy -> nothing touched, activated=False, reason="gate_not_set"
- gate set + successful fake init -> alias rebound, aimdo_enabled True,
  exact telemetry schema/values, idempotent second call
- failure paths (init_devices failure, missing comfy_aimdo, identity
  verification failures) raise RuntimeError with exact
  ``golden_aimdo_activation_failed:<reason>`` markers; residual state per
  path is asserted and documented.
"""

from __future__ import annotations

import importlib.util
import itertools
import os
import sys
import types
import builtins
from pathlib import Path

import pytest

MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "comfymodal_runtime" / "golden_aimdo_activation.py"
)

GATE_ENV = "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM"
PROFILE_ENV = "COMFYMODAL_V2_ENV_PROFILE"

SHADOW_KEYS = [
    "comfy",
    "comfy.model_management",
    "comfy.model_patcher",
    "comfy.memory_management",
    "comfy_aimdo",
    "comfy_aimdo.control",
]

EXPECTED_TELEMETRY_KEYS = {
    "activated",
    "already_activated",
    "gate_env",
    "pid",
    "profile",
    "aimdo_import_version_or_none",
    "init_devices_ok",
    "device_indices",
    "patcher_class_module",
    "patcher_class_name",
    "is_dynamic_alias",
    "aimdo_enabled",
    "activated_monotonic_ns",
    "reason",
}

_module_counter = itertools.count()


# ── Fake stack construction ─────────────────────────────────────────────────


class _FakeDevice:
    def __init__(self, index: int):
        self.index = index


class _BrokenAliasModule(types.ModuleType):
    """model_patcher stand-in whose CoreModelPatcher rebind never sticks."""

    def __setattr__(self, name, value):
        if name == "CoreModelPatcher":
            super().__setattr__(name, object())  # store an unrelated object
        else:
            super().__setattr__(name, value)


class _BrokenFlagModule(types.ModuleType):
    """memory_management stand-in that coerces aimdo_enabled away from True."""

    def __setattr__(self, name, value):
        if name == "aimdo_enabled":
            super().__setattr__(name, bool(value) and "not-True-identity")
        else:
            super().__setattr__(name, value)


def _make_fake_stack(
    *,
    init_devices_result=True,
    n_devices=2,
    aimdo_version="9.9.9-fake",
    omit_aimdo=False,
    broken_alias=False,
    broken_flag=False,
):
    calls = []

    comfy_pkg = types.ModuleType("comfy")
    comfy_pkg.__path__ = []  # mark as package

    mm = types.ModuleType("comfy.model_management")
    mm.get_all_torch_devices = lambda *a, **k: [_FakeDevice(i) for i in range(n_devices)]

    mp = types.ModuleType("comfy.model_patcher")

    class ModelPatcher:
        pass

    class ModelPatcherDynamic(ModelPatcher):
        pass

    mp.ModelPatcher = ModelPatcher
    mp.ModelPatcherDynamic = ModelPatcherDynamic
    mp.CoreModelPatcher = ModelPatcher
    if broken_alias:
        mp = _BrokenAliasModule("comfy.model_patcher")
        mp.ModelPatcher = ModelPatcher
        mp.ModelPatcherDynamic = ModelPatcherDynamic
        mp.CoreModelPatcher = ModelPatcher

    mem = types.ModuleType("comfy.memory_management")
    mem.aimdo_enabled = False
    if broken_flag:
        mem = _BrokenFlagModule("comfy.memory_management")
        mem.aimdo_enabled = False

    comfy_pkg.model_management = mm
    comfy_pkg.model_patcher = mp
    comfy_pkg.memory_management = mem

    modules = {
        "comfy": comfy_pkg,
        "comfy.model_management": mm,
        "comfy.model_patcher": mp,
        "comfy.memory_management": mem,
    }

    if not omit_aimdo:
        aimdo_pkg = types.ModuleType("comfy_aimdo")
        aimdo_pkg.__path__ = []
        if aimdo_version is not None:
            aimdo_pkg.__version__ = aimdo_version

        control = types.ModuleType("comfy_aimdo.control")

        def _init(implementation=None):
            calls.append(("init", implementation))
            return True

        def _init_devices(device_ids):
            ids = [int(d) for d in device_ids]
            calls.append(("init_devices", ids))
            if isinstance(init_devices_result, Exception):
                raise init_devices_result
            return init_devices_result

        control.init = _init
        control.init_devices = _init_devices
        aimdo_pkg.control = control
        modules["comfy_aimdo"] = aimdo_pkg
        modules["comfy_aimdo.control"] = control

    return modules, calls


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture()
def fake_stack(monkeypatch):
    """Install a fresh fake comfy/comfy_aimdo stack into sys.modules."""

    def _install(**kwargs):
        modules, calls = _make_fake_stack(**kwargs)
        for key in SHADOW_KEYS:
            monkeypatch.delitem(sys.modules, key, raising=False)
        for key, mod in modules.items():
            monkeypatch.setitem(sys.modules, key, mod)
        return types.SimpleNamespace(
            calls=calls,
            model_patcher=modules["comfy.model_patcher"],
            memory_management=modules["comfy.memory_management"],
        )

    return _install


@pytest.fixture()
def fresh_module():
    """Load a pristine instance of the module under test (own idempotency state)."""
    for name in [n for n in sys.modules if n.startswith("golden_aimdo_activation_ut")]:
        del sys.modules[name]
    name = f"golden_aimdo_activation_ut_{next(_module_counter)}"
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(name, None)


# ── 1. Gate paths ───────────────────────────────────────────────────────────


def test_gate_unset_leaves_everything_untouched(monkeypatch, fake_stack, fresh_module):
    monkeypatch.delenv(GATE_ENV, raising=False)
    stack = fake_stack()

    result = fresh_module.activate_golden_dynamic_vram()

    assert result["activated"] is False
    assert result["reason"] == "gate_not_set"
    assert set(result) == EXPECTED_TELEMETRY_KEYS
    # Nothing touched: no aimdo calls, alias still legacy, flag still False.
    assert stack.calls == []
    assert stack.model_patcher.CoreModelPatcher is stack.model_patcher.ModelPatcher
    assert stack.memory_management.aimdo_enabled is False


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "", "   ", "enabled"])
def test_gate_falsy_values_do_not_activate(monkeypatch, fake_stack, fresh_module, value):
    monkeypatch.setenv(GATE_ENV, value)
    stack = fake_stack()

    result = fresh_module.activate_golden_dynamic_vram()

    assert result["activated"] is False
    assert result["reason"] == "gate_not_set"
    assert result["gate_env"] == {"name": GATE_ENV, "value": value}
    assert stack.calls == []
    assert stack.model_patcher.CoreModelPatcher is stack.model_patcher.ModelPatcher


def test_early_init_precedes_all_comfy_model_imports(monkeypatch, fake_stack, fresh_module):
    """The early AIMDO hook must initialize control before model modules load."""
    monkeypatch.setenv(GATE_ENV, "1")
    stack = fake_stack()
    timeline = []

    control = sys.modules["comfy_aimdo.control"]
    original_init = control.init

    def _tracked_init(*args, **kwargs):
        timeline.append("init")
        return original_init(*args, **kwargs)

    monkeypatch.setattr(control, "init", _tracked_init)
    original_import = builtins.__import__
    model_modules = {
        "comfy.memory_management",
        "comfy.model_management",
        "comfy.model_patcher",
    }

    def _tracked_import(name, *args, **kwargs):
        if name in model_modules:
            timeline.append(f"import:{name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _tracked_import)

    assert fresh_module.ensure_golden_aimdo_early_init() is True
    assert timeline == ["init"]
    result = fresh_module.activate_golden_dynamic_vram()
    assert result["activated"] is True
    assert timeline[0] == "init"
    assert all(
        timeline.index("init") < timeline.index(f"import:{name}")
        for name in model_modules
    )
    assert stack.calls == [("init", None), ("init_devices", [0, 1])]


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "Yes", "ON"])
def test_gate_truthy_values_activate(monkeypatch, fake_stack, fresh_module, value):
    monkeypatch.setenv(GATE_ENV, value)
    stack = fake_stack()

    result = fresh_module.activate_golden_dynamic_vram()

    assert result["activated"] is True
    assert result["reason"] is None
    assert stack.calls == [("init", None), ("init_devices", [0, 1])]


# ── 2. Success path ─────────────────────────────────────────────────────────


def test_success_rebinds_alias_and_reports_full_telemetry(monkeypatch, fake_stack, fresh_module):
    monkeypatch.setenv(GATE_ENV, "1")
    monkeypatch.setenv(PROFILE_ENV, "golden-p1")
    stack = fake_stack(n_devices=3)

    before_ns = fresh_module.time.monotonic_ns()
    result = fresh_module.activate_golden_dynamic_vram()
    after_ns = fresh_module.time.monotonic_ns()

    # Observable side effects exactly match upstream main.py L233-234.
    assert stack.model_patcher.CoreModelPatcher is stack.model_patcher.ModelPatcherDynamic
    assert stack.memory_management.aimdo_enabled is True
    # Upstream order: init() then init_devices() over device indices.
    assert stack.calls == [("init", None), ("init_devices", [0, 1, 2])]

    # Exact telemetry schema and values.
    assert set(result) == EXPECTED_TELEMETRY_KEYS
    assert result["activated"] is True
    assert result["already_activated"] is False
    assert result["gate_env"] == {"name": GATE_ENV, "value": "1"}
    assert result["pid"] == os.getpid()
    assert result["profile"] == "golden-p1"
    assert result["aimdo_import_version_or_none"] == "9.9.9-fake"
    assert result["init_devices_ok"] is True
    assert result["device_indices"] == [0, 1, 2]
    dynamic_cls = stack.model_patcher.ModelPatcherDynamic
    assert result["patcher_class_module"] == dynamic_cls.__module__
    assert result["patcher_class_name"] == "ModelPatcherDynamic"
    assert result["is_dynamic_alias"] is True
    assert result["aimdo_enabled"] is True
    assert isinstance(result["activated_monotonic_ns"], int)
    assert before_ns <= result["activated_monotonic_ns"] <= after_ns
    assert result["reason"] is None

    # JSON-safe: must survive json.dumps round-trip.
    import json

    assert json.loads(json.dumps(result)) == result


def test_second_call_is_idempotent(monkeypatch, fake_stack, fresh_module):
    monkeypatch.setenv(GATE_ENV, "1")
    stack = fake_stack()

    first = fresh_module.activate_golden_dynamic_vram()
    second = fresh_module.activate_golden_dynamic_vram()

    assert first["activated"] is True
    assert second["activated"] is True
    assert second["already_activated"] is True
    assert first["already_activated"] is False
    # Everything except the already_activated marker is identical.
    rest = {k for k in EXPECTED_TELEMETRY_KEYS if k != "already_activated"}
    assert {k: second[k] for k in rest} == {k: first[k] for k in rest}
    # No additional native calls on the repeat invocation.
    assert stack.calls == [("init", None), ("init_devices", [0, 1])]


def test_custom_gate_env_name(monkeypatch, fake_stack, fresh_module):
    custom = "MY_CUSTOM_GATE"
    monkeypatch.delenv(GATE_ENV, raising=False)
    monkeypatch.setenv(custom, "on")
    fake_stack()

    result = fresh_module.activate_golden_dynamic_vram(enabled_env=custom)

    assert result["activated"] is True
    assert result["gate_env"] == {"name": custom, "value": "on"}


def test_missing_profile_env_yields_none(monkeypatch, fake_stack, fresh_module):
    monkeypatch.setenv(GATE_ENV, "1")
    monkeypatch.delenv(PROFILE_ENV, raising=False)
    fake_stack()

    result = fresh_module.activate_golden_dynamic_vram()

    assert result["profile"] is None


def test_missing_aimdo_version_yields_none(monkeypatch, fake_stack, fresh_module):
    monkeypatch.setenv(GATE_ENV, "1")
    fake_stack(aimdo_version=None)

    result = fresh_module.activate_golden_dynamic_vram()

    assert result["activated"] is True
    assert result["aimdo_import_version_or_none"] is None


# ── 3. Failure paths (fail closed) ──────────────────────────────────────────


def test_init_devices_false_raises_and_leaves_no_half_bind(monkeypatch, fake_stack, fresh_module):
    monkeypatch.setenv(GATE_ENV, "1")
    stack = fake_stack(init_devices_result=False)

    with pytest.raises(RuntimeError, match=r"golden_aimdo_activation_failed:init_devices_failed"):
        fresh_module.activate_golden_dynamic_vram()

    # Residual state: only the recorded aimdo calls (DLL load is unavoidable);
    # the failure happens BEFORE any rebinding, so alias/flag are untouched.
    assert stack.calls == [("init", None), ("init_devices", [0, 1])]
    assert stack.model_patcher.CoreModelPatcher is stack.model_patcher.ModelPatcher
    assert stack.memory_management.aimdo_enabled is False


def test_init_devices_exception_raises_with_marker(monkeypatch, fake_stack, fresh_module):
    monkeypatch.setenv(GATE_ENV, "1")
    stack = fake_stack(init_devices_result=RuntimeError("native boom"))

    with pytest.raises(RuntimeError, match=r"golden_aimdo_activation_failed:init_devices_failed"):
        fresh_module.activate_golden_dynamic_vram()

    assert stack.model_patcher.CoreModelPatcher is stack.model_patcher.ModelPatcher
    assert stack.memory_management.aimdo_enabled is False


class _BlockComfyAimdoFinder:
    """Meta-path finder that makes 'comfy_aimdo' unimportable.

    Deleting sys.modules entries alone cannot hide a real site-packages
    install: path-based finders simply re-import it from disk. Raising
    ModuleNotFoundError from find_spec blocks every import mechanism.
    """

    def find_spec(self, fullname, path=None, target=None):
        if fullname == "comfy_aimdo" or fullname.startswith("comfy_aimdo."):
            raise ModuleNotFoundError(
                f"No module named {fullname!r} (blocked by test)", name=fullname
            )
        return None


def test_missing_comfy_aimdo_raises_import_failed(monkeypatch, fake_stack, fresh_module):
    monkeypatch.setenv(GATE_ENV, "1")
    # Install only the comfy half; make comfy_aimdo unimportable even when the
    # real package exists in site-packages (sys.modules deletion is not enough).
    modules, _calls = _make_fake_stack(omit_aimdo=True)
    for key in SHADOW_KEYS:
        monkeypatch.delitem(sys.modules, key, raising=False)
    for key, mod in modules.items():
        monkeypatch.setitem(sys.modules, key, mod)
    monkeypatch.setattr(sys, "meta_path", [_BlockComfyAimdoFinder()] + sys.meta_path)

    with pytest.raises(RuntimeError, match=r"golden_aimdo_activation_failed:import_failed") as excinfo:
        fresh_module.activate_golden_dynamic_vram()

    telemetry = excinfo.value.golden_activation_telemetry
    assert telemetry["activated"] is False
    assert telemetry["device_indices"] == []
    assert telemetry["init_devices_ok"] is False


def test_broken_alias_identity_raises_and_documents_residual(monkeypatch, fake_stack, fresh_module):
    """Alias rebind silently fails to stick -> fail closed.

    Documented residual: ``memory_management.aimdo_enabled`` was already set to
    True before the alias verification ran (upstream order sets both, then
    verifies). It is intentionally NOT restored (fail-closed contract).
    """
    monkeypatch.setenv(GATE_ENV, "1")
    stack = fake_stack(broken_alias=True)

    with pytest.raises(
        RuntimeError, match=r"golden_aimdo_activation_failed:alias_rebind_verification_failed"
    ):
        fresh_module.activate_golden_dynamic_vram()

    assert stack.model_patcher.CoreModelPatcher is not stack.model_patcher.ModelPatcherDynamic
    assert stack.memory_management.aimdo_enabled is not False  # documented residual


def test_broken_flag_identity_raises_and_documents_residual(monkeypatch, fake_stack, fresh_module):
    """aimdo_enabled loses strict-True identity -> fail closed.

    Documented residual: ``CoreModelPatcher`` was already rebound to
    ModelPatcherDynamic before the flag verification ran. Intentionally NOT
    restored (fail-closed contract).
    """
    monkeypatch.setenv(GATE_ENV, "1")
    stack = fake_stack(broken_flag=True)

    with pytest.raises(
        RuntimeError, match=r"golden_aimdo_activation_failed:aimdo_flag_verification_failed"
    ):
        fresh_module.activate_golden_dynamic_vram()

    assert stack.model_patcher.CoreModelPatcher is stack.model_patcher.ModelPatcherDynamic
    assert stack.memory_management.aimdo_enabled is not True  # documented residual


def test_failure_does_not_poison_later_successful_call(monkeypatch, fake_stack, fresh_module):
    """A failed attempt is not cached; a later call may still succeed."""
    monkeypatch.setenv(GATE_ENV, "1")
    fake_stack(init_devices_result=False)

    with pytest.raises(RuntimeError, match=r"init_devices_failed"):
        fresh_module.activate_golden_dynamic_vram()

    fake_stack(init_devices_result=True)
    result = fresh_module.activate_golden_dynamic_vram()
    assert result["activated"] is True
    assert result["already_activated"] is False
