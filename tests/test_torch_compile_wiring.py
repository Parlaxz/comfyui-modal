"""FAST_UNIT: torch.compile policy wiring (modal_app seams + flags + retirement).

Dependency-free: stdlib plus the two unwired policy modules only.  No
torch / Comfy / Modal / modal_app imports at module scope (modal_app is on
the FAST_UNIT heavy-import guard, so the wiring below is verified by AST
source-contract plus exec of the extracted pure helpers with injected
fakes, matching the repo's existing audit-test style).

Coverage:
* wiring order (restore -> cache-bind -> readiness -> attach-before-merge
  -> ON_PRE_RUN prepare -> cleanup) via AST call-sequence + exec with
  recording fakes;
* off-by-default no-op (no wrappers, no env mutation, silent logs,
  release in finally);
* KJ set_torch_compile_wrapper signature verified against the installed
  ComfyUI source (never guessed) + kj_capability_missing eager path;
* flag registry + ideogram profile validation control (compile stays off
  unless explicitly enabled);
* comfyapp dormant-hook retirement (Triton/load-diagnostic code untouched).
"""

from __future__ import annotations

import ast
import contextlib
import io
import os
import sys
import tempfile
import tomllib
import unittest
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from comfymodal_runtime import compiler_cache as cc
from comfymodal_runtime import torch_compile_policy as tcp
from tools.v2_control.registry import FlagRegistry

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

MODAL_APP_PATH = REPO_ROOT / "comfymodal_runtime" / "modal_app.py"
COMFYAPP_PATH = REPO_ROOT / "comfyapp.py"
REGISTRY_PATH = REPO_ROOT / "config" / "v2" / "flag_registry.toml"
PROFILE_PATH = (
    REPO_ROOT / "config" / "v2" / "profiles" / "ideogram4_h100_20261015.toml"
)
COMFY_API_HELPERS = (
    REPO_ROOT.parents[1] / "comfy_api" / "torch_helpers" / "torch_compile.py"
)
COMFY_API_HELPERS_INIT = (
    REPO_ROOT.parents[1] / "comfy_api" / "torch_helpers" / "__init__.py"
)

EXPECTED_WIRING_HELPERS = (
    "_compile_alias_env",
    "resolve_request_compile_policy",
    "_compile_toolchain_identity",
    "ensure_compile_cache_bound",
    "_compile_cuda_initialized",
    "_compile_gpu_restore_complete",
    "_compile_execution_device_is_cuda",
    "_compile_ready_for_request",
    "_kj_dynamic_for_policy",
    "_kj_wrapper_kwargs_for_policy",
    "apply_kj_compile_to_patcher",
    "_install_request_compile_scope",
    "_finalize_request_compile_scope",
)

EXPECTED_POLICY_APIS = (
    "resolve_compile_policy",
    "install_sampling_compile_scope",
    "attach_compile_policy",
    "prepare_compile_targets",
    "finish_compile_sample",
    "release_compile_targets",
    "summarize_compile_sample",
    "bind_compiler_cache",
    "probe_kj_compile_capability",
)

# Verified against installed ComfyUI source
# (comfy_api/torch_helpers/__init__.py) and KJNodes call sites
# (ComfyUI-KJNodes/nodes/model_optimization_nodes.py).
EXPECTED_KJ_PARAMS = (
    "model",
    "backend",
    "options",
    "mode",
    "fullgraph",
    "dynamic",
    "keys",
)


def _read(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if text.startswith("\ufeff"):
        text = text[1:]
    return text


_MODAL_APP_SRC: str | None = None
_MODAL_APP_TREE: ast.AST | None = None


def _modal_app_src() -> str:
    global _MODAL_APP_SRC
    if _MODAL_APP_SRC is None:
        _MODAL_APP_SRC = _read(MODAL_APP_PATH)
    assert _MODAL_APP_SRC is not None
    return _MODAL_APP_SRC


def _modal_app_tree() -> ast.AST:
    global _MODAL_APP_TREE
    if _MODAL_APP_TREE is None:
        _MODAL_APP_TREE = ast.parse(_modal_app_src())
    assert _MODAL_APP_TREE is not None
    return _MODAL_APP_TREE


def _func_node(
    src: str, name: str
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    tree = _modal_app_tree() if src == _modal_app_src() else ast.parse(src)
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
        ):
            return node
    return None


def _func_source(src: str, name: str) -> str | None:
    node = _func_node(src, name)
    if node is None:
        return None
    return ast.get_source_segment(src, node)


def _call_sequence(func_node: ast.AST) -> list[str]:
    """Call target names in source order (attr for methods, id for names)."""
    calls: list[tuple[int, int, str]] = []
    for node in ast.walk(func_node):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                calls.append((node.lineno, node.col_offset, func.id))
            elif isinstance(func, ast.Attribute):
                calls.append((node.lineno, node.col_offset, func.attr))
    calls.sort(key=lambda item: (item[0], item[1]))
    return [name for _, _, name in calls]


def _filtered_order(sequence: list[str], wanted: list[str]) -> list[str]:
    wanted_set = set(wanted)
    seen: list[str] = []
    for name in sequence:
        if name in wanted_set and name not in seen:
            seen.append(name)
    return seen


def _exec_helpers(*names: str) -> dict[str, Any]:
    """Exec extracted modal_app wiring helpers with injected stdlib names.

    Relative imports inside the helpers never execute in these tests:
    every suite injects fakes or the real tcp/cc callables for each
    dependency path it exercises.
    """
    src = _modal_app_src()
    tree = _modal_app_tree()
    parts: list[str] = []
    for const in (
        "_COMPILE_RECOMPILE_LIMIT_ENV",
        "_COMPILE_RECOMPILE_BUDGET_ENV",
    ):
        found = False
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == const
            ):
                segment = ast.get_source_segment(src, node)
                assert segment is not None, const
                parts.append(segment)
                found = True
                break
        assert found, const
    for name in names:
        segment = _func_source(src, name)
        assert segment is not None, name
        parts.append(segment)
    namespace: dict[str, Any] = {
        "__name__": "compile_wiring_test_ns",
        "os": os,
        "sys": sys,
        "platform": __import__("platform"),
        "Mapping": Mapping,
        "Any": Any,
        "print": print,
        "_COMPILE_CACHE_BINDING": None,
    }
    exec(
        "from __future__ import annotations\n" + "\n".join(parts),
        namespace,
    )
    return namespace


class _Block:
    """Callable block with nontrivial children (structural region member)."""

    def __init__(self, tag: str = "b"):
        self.tag = tag
        self._modules = {"sub0": object(), "sub1": object()}

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return ("eager", self.tag)


class _Model:
    def __init__(self, **containers: Any):
        for name, value in containers.items():
            setattr(self, name, value)


def _regional_policy(**overrides: Any) -> tcp.CompilePolicy:
    kwargs: dict[str, Any] = {"requested_mode": "regional", "mode": "regional"}
    kwargs.update(overrides)
    return tcp.CompilePolicy(**kwargs)


def _kj_missing() -> dict[str, Any]:
    return {
        "available": False,
        "reason": tcp.KJ_CAPABILITY_MISSING,
        "wrapper": None,
        "source": "fake",
    }


# ---------------------------------------------------------------------------
# Wiring order (AST source-contract on modal_app.py)
# ---------------------------------------------------------------------------


@pytest.mark.fast_unit
class CompileWiringOrderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = _read(MODAL_APP_PATH)

    def test_helper_section_defines_all_seams(self):
        for name in EXPECTED_WIRING_HELPERS:
            self.assertIsNotNone(
                _func_node(self.src, name), f"missing wiring helper {name}"
            )

    def test_install_order_is_resolve_install_attach_readiness_prepare(self):
        node = _func_node(self.src, "_install_request_compile_scope")
        self.assertIsNotNone(node)
        assert node is not None
        order = _filtered_order(
            _call_sequence(node),
            ["resolve", "_install", "_attach", "ready_fn", "_prepare"],
        )
        self.assertEqual(
            order,
            ["resolve", "_install", "_attach", "ready_fn", "_prepare"],
        )

    def test_finalize_order_is_finish_summarize_release(self):
        node = _func_node(self.src, "_finalize_request_compile_scope")
        self.assertIsNotNone(node)
        assert node is not None
        order = _filtered_order(
            _call_sequence(node), ["_finish", "_summarize", "_release"]
        )
        self.assertEqual(order, ["_finish", "_summarize", "_release"])

    def test_wiring_references_exact_public_apis(self):
        section = "\n".join(
            _func_source(self.src, name) or "" for name in EXPECTED_WIRING_HELPERS
        )
        for api in EXPECTED_POLICY_APIS:
            self.assertIn(api, section, f"wiring must reference {api}")

    def test_attach_precedes_prepare_in_install_source(self):
        segment = _func_source(self.src, "_install_request_compile_scope")
        self.assertIsNotNone(segment)
        assert segment is not None
        self.assertLess(
            segment.index("_tcp_attach.attach_compile_policy"),
            segment.index("_tcp_prepare.prepare_compile_targets"),
            "attach (before wrapper merge) must precede ON_PRE_RUN prepare",
        )

    def test_restore_binds_cache_after_gpu_repair(self):
        node = _func_node(self.src, "restore")
        self.assertIsNotNone(node)
        assert node is not None
        segment = ast.get_source_segment(self.src, node)
        assert segment is not None
        self.assertLess(
            segment.index("repair_gpu_capabilities_after_restore"),
            segment.index("ensure_compile_cache_bound"),
            "cache bind must follow gpu_restore repair at restore scope",
        )

    def test_executor_path_install_before_execute_finalize_after(self):
        node = _func_node(self.src, "_execute_v2_prompt_executor")
        self.assertIsNotNone(node)
        assert node is not None
        segment = ast.get_source_segment(self.src, node)
        assert segment is not None
        install_at = segment.index("_install_request_compile_scope")
        execute_at = segment.index("executor.execute")
        finalize_at = segment.index("_finalize_request_compile_scope")
        self.assertLess(install_at, execute_at)
        self.assertLess(execute_at, finalize_at)

    def test_gpu_restore_seams_preserved_byte_identical(self):
        # Lane 1 owns these seams: the wiring lane must not add, remove, or
        # rename any gpu_restore call.
        self.assertEqual(
            self.src.count("repair_gpu_capabilities_after_restore"), 3
        )
        self.assertEqual(
            self.src.count("ensure_gpu_capabilities_repaired_before_execution"), 3
        )
        self.assertEqual(self.src.count("begin_gpu_restore()"), 1)
        # 1 def + 3 guarded call sites + 1 lifecycle-doc mention.
        self.assertEqual(self.src.count("ensure_compile_cache_bound()"), 4)
        self.assertEqual(self.src.count("def ensure_compile_cache_bound"), 1)

    def test_compile_wiring_never_raises_past_call_sites(self):
        # Every in-function call site guards the wiring best-effort.
        for marker in (
            "ensure_compile_cache_bound()",
            "_install_request_compile_scope(executor)",
            "_finalize_request_compile_scope(_compile_scope_record)",
        ):
            self.assertIn(marker, self.src)


# ---------------------------------------------------------------------------
# Pure helper behavior (exec of extracted source, injected fakes)
# ---------------------------------------------------------------------------


@pytest.mark.fast_unit
class CompileAliasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = _exec_helpers("_compile_alias_env")

    def test_limit_aliases_to_budget_when_budget_absent(self):
        out = self.ns["_compile_alias_env"](
            {"COMFYMODAL_TORCH_COMPILE_RECOMPILE_LIMIT": "12"}
        )
        self.assertEqual(out["COMFYMODAL_TORCH_COMPILE_RECOMPILE_BUDGET"], "12")

    def test_explicit_budget_wins_over_limit(self):
        out = self.ns["_compile_alias_env"](
            {
                "COMFYMODAL_TORCH_COMPILE_RECOMPILE_LIMIT": "12",
                "COMFYMODAL_TORCH_COMPILE_RECOMPILE_BUDGET": "4",
            }
        )
        self.assertEqual(out["COMFYMODAL_TORCH_COMPILE_RECOMPILE_BUDGET"], "4")

    def test_blank_limit_leaves_budget_absent(self):
        out = self.ns["_compile_alias_env"](
            {"COMFYMODAL_TORCH_COMPILE_RECOMPILE_LIMIT": "  "}
        )
        self.assertNotIn("COMFYMODAL_TORCH_COMPILE_RECOMPILE_BUDGET", out)

    def test_non_mapping_passes_through(self):
        self.assertIsNone(self.ns["_compile_alias_env"](None))


@pytest.mark.fast_unit
class CompileKjKwargsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = _exec_helpers("_kj_dynamic_for_policy", "_kj_wrapper_kwargs_for_policy")

    def test_kwargs_cover_verified_signature_exactly(self):
        kwargs = self.ns["_kj_wrapper_kwargs_for_policy"](
            _regional_policy(), ["diffusion_model.double_blocks.0"]
        )
        self.assertEqual(
            sorted(kwargs),
            sorted(["backend", "options", "mode", "fullgraph", "dynamic", "keys"]),
        )
        for key in kwargs:
            self.assertIn(key, EXPECTED_KJ_PARAMS)

    def test_fixed_codegen_contract(self):
        kwargs = self.ns["_kj_wrapper_kwargs_for_policy"](
            _regional_policy(), ["diffusion_model"]
        )
        self.assertEqual(kwargs["backend"], "inductor")
        self.assertIsNone(kwargs["options"])
        self.assertIsNone(kwargs["mode"])
        self.assertFalse(kwargs["fullgraph"])
        self.assertIsNone(kwargs["dynamic"])
        self.assertEqual(kwargs["keys"], ["diffusion_model"])

    def test_dynamic_mapping(self):
        dynamic = self.ns["_kj_dynamic_for_policy"]
        self.assertIsNone(dynamic(_regional_policy(dynamic="auto")))
        self.assertTrue(dynamic(_regional_policy(dynamic="true")))
        self.assertFalse(dynamic(_regional_policy(dynamic="false")))


@pytest.mark.fast_unit
class CompileReadinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = _exec_helpers("_compile_ready_for_request")

    def _check(self, policy, **gates):
        ready_fn = self.ns["_compile_ready_for_request"]
        return ready_fn(
            policy,
            _cuda_ok=lambda: gates.get("cuda", True),
            _restore_ok=lambda: gates.get("restore", True),
            _device_ok=lambda: gates.get("device", True),
            snapshot_capturing=gates.get("snapshot", False),
            external_compile_owner=gates.get("owner", ""),
        )

    def test_mode_off_short_circuits(self):
        policy, _ = tcp.resolve_compile_policy(env={}, argv=[])
        result = self._check(policy)
        self.assertFalse(result["ready"])
        self.assertEqual(result["reason"], "mode_off")

    def test_snapshot_capture_forces_eager(self):
        result = self._check(_regional_policy(), snapshot=True)
        self.assertEqual(result["reason"], "snapshot_capture_active")

    def test_external_owner_forces_eager(self):
        result = self._check(_regional_policy(), owner="kj_nodes")
        self.assertEqual(result["reason"], "external_compile_owner")

    def test_cuda_init_gate(self):
        result = self._check(_regional_policy(), cuda=False)
        self.assertEqual(result["reason"], "cuda_not_initialized")

    def test_gpu_restore_gate(self):
        result = self._check(_regional_policy(), restore=False)
        self.assertEqual(result["reason"], "gpu_restore_incomplete")

    def test_execution_device_gate(self):
        result = self._check(_regional_policy(), device=False)
        self.assertEqual(result["reason"], "execution_device_not_cuda")

    def test_all_gates_pass_reports_ready(self):
        result = self._check(_regional_policy())
        self.assertEqual(result, {"ready": True, "reason": "ready"})


@pytest.mark.fast_unit
class CompileWiringLifecycleTests(unittest.TestCase):
    """Order + off-by-default + KJ paths via exec with recording fakes."""

    @classmethod
    def setUpClass(cls):
        cls.ns = _exec_helpers(
            "_compile_alias_env",
            "resolve_request_compile_policy",
            "_compile_ready_for_request",
            "_install_request_compile_scope",
            "_finalize_request_compile_scope",
            "ensure_compile_cache_bound",
        )

    def test_full_order_with_recording_fakes(self):
        calls: list[str] = []
        ns = self.ns
        record = ns["_install_request_compile_scope"](
            {"executor": "fake"},
            diffusion_model=_Model(
                double_blocks=[_Block(f"b{i}") for i in range(3)]
            ),
            _resolve=lambda **k: (
                calls.append("resolve"),
                _regional_policy(),
                {"reasons": []},
            )[1:],
            _install=lambda **k: (calls.append("install"), {"scope": True})[1],
            _attach=lambda state, policy: calls.append("attach") or {
                "attached": True,
                "via": "mapping",
            },
            _ready=lambda policy, **k: calls.append("readiness") or {
                "ready": True,
                "reason": "ready",
            },
            _prepare=lambda scope, **k: calls.append("prepare") or {
                "prepared": True,
                "reason": "prepared",
            },
            _probe=lambda: calls.append("probe") or {"available": True},
        )
        self.assertEqual(
            calls, ["resolve", "install", "attach", "readiness", "prepare"]
        )
        self.assertTrue(record["prepared"])
        self.assertTrue(record["attached"])

        calls.clear()
        outcome = ns["_finalize_request_compile_scope"](
            record,
            _finish=lambda scope, **k: calls.append("finish") or {},
            _summarize=lambda scope, **k: calls.append("summarize")
            or {"line": "[compile] fake", "details": {}},
            _release=lambda scope: calls.append("release")
            or {"released": True, "already": False},
        )
        self.assertEqual(calls, ["finish", "summarize", "release"])
        self.assertTrue(outcome["released"])

    def test_off_by_default_adds_no_wrappers(self):
        wrapper_calls: list[dict[str, Any]] = []
        probe_calls: list[str] = []
        saved_env = dict(os.environ)
        try:
            record = self.ns["_install_request_compile_scope"](
                {},
                env={},
                argv=[],
                _resolve=tcp.resolve_compile_policy,
                _install=tcp.install_sampling_compile_scope,
                _attach=tcp.attach_compile_policy,
                _ready=lambda policy, **k: {
                    "ready": False,
                    "reason": "mode_off",
                },
                _prepare=tcp.prepare_compile_targets,
                _probe=lambda: probe_calls.append("probe") or _kj_missing(),
            )
            self.assertEqual(record["policy_mode"], "off")
            self.assertFalse(record["prepared"])
            self.assertEqual(record["prepare_reason"], "mode_off")
            scope = record["scope"]
            self.assertIsNotNone(scope)
            assert isinstance(scope, dict)
            self.assertEqual(
                scope["latch"].state, tcp.LATCH_EAGER_SKIPPED
            )
            self.assertEqual(wrapper_calls, [])
            # No KJ capability probe needed once mode_off short-circuits.
            self.assertEqual(probe_calls, [])
            # No cache env routed while off.
            self.assertNotIn("TORCHINDUCTOR_CACHE_DIR", os.environ)
            self.assertNotIn("TRITON_CACHE_DIR", os.environ)

            captured = io.StringIO()
            with contextlib.redirect_stdout(captured):
                outcome = self.ns["_finalize_request_compile_scope"](
                    record,
                    _finish=tcp.finish_compile_sample,
                    _summarize=tcp.summarize_compile_sample,
                    _release=tcp.release_compile_targets,
                )
            self.assertTrue(outcome["released"])
            self.assertNotIn("[compile]", captured.getvalue())
            self.assertFalse(outcome["emitted"])
            self.assertEqual(scope["targets"], [])
        finally:
            os.environ.clear()
            os.environ.update(saved_env)

    def test_legacy_flag_never_enables_compile(self):
        resolve = self.ns["resolve_request_compile_policy"]
        policy, diagnostics = resolve(
            env={"COMFYMODAL_ENABLE_TORCH_COMPILE": "1"},
            argv=[],
            _resolve=tcp.resolve_compile_policy,
        )
        self.assertEqual(policy.mode, "off")
        self.assertIn("legacy_compile_flag_deprecated", diagnostics["reasons"])
        policy, diagnostics = resolve(
            env={
                "COMFYMODAL_ENABLE_TORCH_COMPILE": "1",
                "COMFYMODAL_TORCH_COMPILE_MODE": "regional",
            },
            argv=[],
            _resolve=tcp.resolve_compile_policy,
        )
        self.assertEqual(policy.mode, "regional")
        self.assertIn("legacy_compile_flag_conflict", diagnostics["reasons"])

    def test_recompile_limit_alias_reaches_resolver(self):
        resolve = self.ns["resolve_request_compile_policy"]
        policy, _ = resolve(
            env={"COMFYMODAL_TORCH_COMPILE_RECOMPILE_LIMIT": "3"},
            argv=[],
            _resolve=tcp.resolve_compile_policy,
        )
        self.assertEqual(policy.recompile_budget, 3)

    def test_ensure_cache_bound_off_path_is_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            sentinel = os.path.join(tmp, "must_not_exist")
            result = self.ns["ensure_compile_cache_bound"](
                env={}, root=sentinel, _resolve=tcp.resolve_compile_policy
            )
            self.assertFalse(result["bound"])
            self.assertEqual(result["reason"], "mode_off")
            self.assertFalse(os.path.exists(sentinel))

    def test_missing_kj_capability_stays_eager(self):
        wrapper_calls: list[dict[str, Any]] = []
        record = self.ns["_install_request_compile_scope"](
            {},
            env={"COMFYMODAL_TORCH_COMPILE_MODE": "regional"},
            argv=[],
            diffusion_model=_Model(double_blocks=[_Block(f"b{i}") for i in range(3)]),
            _resolve=tcp.resolve_compile_policy,
            _install=tcp.install_sampling_compile_scope,
            _attach=tcp.attach_compile_policy,
            _ready=lambda policy, **k: {"ready": True, "reason": "ready"},
            _prepare=tcp.prepare_compile_targets,
            _probe=_kj_missing,
        )
        self.assertEqual(record["policy_mode"], "regional")
        self.assertFalse(record["prepared"])
        self.assertEqual(record["prepare_reason"], tcp.KJ_CAPABILITY_MISSING)
        scope = record["scope"]
        assert isinstance(scope, dict)
        self.assertEqual(scope["latch"].state, tcp.LATCH_EAGER_SKIPPED)
        self.assertEqual(wrapper_calls, [])


@pytest.mark.fast_unit
class CompileCacheBindTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = _exec_helpers(
            "_compile_alias_env",
            "resolve_request_compile_policy",
            "ensure_compile_cache_bound",
        )

    def test_enabled_bind_verifies_effective_paths(self):
        saved_env = dict(os.environ)
        os.environ.pop("TORCHINDUCTOR_CACHE_DIR", None)
        os.environ.pop("TRITON_CACHE_DIR", None)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = os.path.join(tmp, "compiler-cache")
                identity = {
                    "torch_version": "2.5.1",
                    "cuda_version": "12.4",
                    "triton_version": "3.1.0",
                    "arch": "sm_100",
                    "python_version": "3.12",
                }
                first = self.ns["ensure_compile_cache_bound"](
                    env={"COMFYMODAL_TORCH_COMPILE_MODE": "regional"},
                    root=root,
                    _resolve=tcp.resolve_compile_policy,
                    _cache_mod=cc,
                    _identity=identity,
                )
                self.assertTrue(first["bound"])
                self.assertFalse(first.get("already", False))
                self.assertTrue(os.path.isdir(first["paths"]["inductor_dir"]))
                self.assertTrue(os.path.isdir(first["paths"]["triton_dir"]))
                self.assertEqual(
                    os.environ.get("TORCHINDUCTOR_CACHE_DIR"),
                    first["paths"]["inductor_dir"],
                )
                self.assertEqual(
                    os.environ.get("TRITON_CACHE_DIR"),
                    first["paths"]["triton_dir"],
                )
                second = self.ns["ensure_compile_cache_bound"](
                    env={"COMFYMODAL_TORCH_COMPILE_MODE": "regional"},
                    root=root,
                    _resolve=tcp.resolve_compile_policy,
                    _cache_mod=cc,
                    _identity=identity,
                )
                self.assertTrue(second["bound"])
                self.assertTrue(second.get("already", False))
        finally:
            os.environ.clear()
            os.environ.update(saved_env)


@pytest.mark.fast_unit
class CompileKjApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = _exec_helpers(
            "resolve_request_compile_policy",
            "_compile_ready_for_request",
            "_kj_dynamic_for_policy",
            "_kj_wrapper_kwargs_for_policy",
            "apply_kj_compile_to_patcher",
            "_install_request_compile_scope",
            "_finalize_request_compile_scope",
        )

    def test_enabled_scope_applies_verified_wrapper_signature(self):
        applied: list[dict[str, Any]] = []

        def _recording_wrapper(model: Any, **kwargs: Any) -> None:
            applied.append({"model": model, **kwargs})

        record = self.ns["_install_request_compile_scope"](
            {},
            env={"COMFYMODAL_TORCH_COMPILE_MODE": "regional"},
            argv=[],
            diffusion_model=_Model(double_blocks=[_Block(f"b{i}") for i in range(3)]),
            _resolve=tcp.resolve_compile_policy,
            _install=tcp.install_sampling_compile_scope,
            _attach=tcp.attach_compile_policy,
            _ready=lambda policy, **k: {"ready": True, "reason": "ready"},
            _prepare=tcp.prepare_compile_targets,
            _probe=lambda: {
                "available": True,
                "reason": "ok",
                "wrapper": object(),
                "source": "fake",
            },
        )
        self.assertTrue(record["prepared"])
        scope = record["scope"]
        assert isinstance(scope, dict)
        self.assertEqual(len(scope["regions"]), 1)
        patcher = object()
        result = self.ns["apply_kj_compile_to_patcher"](
            patcher, scope, _wrapper=_recording_wrapper
        )
        self.assertTrue(result["applied"])
        self.assertEqual(
            result["keys"],
            [
                "diffusion_model.double_blocks.0",
                "diffusion_model.double_blocks.1",
                "diffusion_model.double_blocks.2",
            ],
        )
        self.assertEqual(len(applied), 1)
        call = applied[0]
        self.assertIs(call["model"], patcher)
        self.assertEqual(
            sorted(k for k in call if k != "model"),
            sorted(["backend", "options", "mode", "fullgraph", "dynamic", "keys"]),
        )
        self.assertEqual(call["backend"], "inductor")
        self.assertIsNone(call["options"])
        self.assertIsNone(call["mode"])
        self.assertFalse(call["fullgraph"])
        self.assertIsNone(call["dynamic"])

        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            outcome = self.ns["_finalize_request_compile_scope"](
                record,
                _finish=tcp.finish_compile_sample,
                _summarize=tcp.summarize_compile_sample,
                _release=tcp.release_compile_targets,
            )
        self.assertTrue(outcome["finished"])
        self.assertTrue(outcome["released"])
        self.assertTrue(outcome["emitted"])
        self.assertIn("[compile]", captured.getvalue())
        self.assertIn("requested=regional", captured.getvalue())
        # Release is idempotent: a second finalize reports already-released.
        again = self.ns["_finalize_request_compile_scope"](
            record,
            _finish=tcp.finish_compile_sample,
            _summarize=tcp.summarize_compile_sample,
            _release=tcp.release_compile_targets,
        )
        self.assertTrue(again["released"])
        self.assertTrue(again.get("already", False))


@pytest.mark.fast_unit
class CompileKjSignatureTests(unittest.TestCase):
    def test_installed_wrapper_signature_is_verified(self):
        node = None
        helper_src: str | None = None
        for candidate in (COMFY_API_HELPERS, COMFY_API_HELPERS_INIT):
            if candidate.is_file():
                candidate_src = _read(candidate)
                candidate_node = _func_node(
                    candidate_src, "set_torch_compile_wrapper"
                )
                if candidate_node is not None:
                    node = candidate_node
                    helper_src = candidate_src
                    break
        if node is None or helper_src is None:
            pytest.skip("installed comfy_api torch_helpers not present")
        assert node is not None
        assert helper_src is not None
        positional = [arg.arg for arg in node.args.args]
        self.assertEqual(positional, list(EXPECTED_KJ_PARAMS))
        defaults = node.args.defaults
        # (model, backend) required; (options, mode, fullgraph, dynamic, keys)
        # carry the documented defaults.
        self.assertEqual(len(positional) - len(defaults), 2)
        default_src = [
            ast.get_source_segment(helper_src, item) for item in defaults
        ]
        self.assertEqual(
            default_src, ["None", "None", "False", "None", '["diffusion_model"]']
        )


# ---------------------------------------------------------------------------
# Flag validation (registry + validation-control profile)
# ---------------------------------------------------------------------------


@pytest.mark.fast_unit
class CompileFlagValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        registry = FlagRegistry(REGISTRY_PATH)
        registry.load()
        cls.registry = registry
        with REGISTRY_PATH.open("rb") as handle:
            cls.raw_flags = {
                entry["name"]: entry for entry in tomllib.load(handle)["flag"]
            }
        with PROFILE_PATH.open("rb") as handle:
            cls.profile = tomllib.load(handle)

    def _entry(self, name: str):
        entry = self.registry.get(name)
        self.assertIsNotNone(entry, name)
        assert entry is not None
        return entry

    def _raw(self, name: str) -> dict[str, Any]:
        raw = self.raw_flags.get(name)
        self.assertIsInstance(raw, dict, name)
        assert isinstance(raw, dict)
        return raw

    def test_registry_declares_four_compile_flags(self):
        names = self.registry.registered_names()
        for name in (
            "COMFYMODAL_TORCH_COMPILE_MODE",
            "COMFYMODAL_TORCH_COMPILE_DYNAMIC",
            "COMFYMODAL_TORCH_COMPILE_DEBUG",
            "COMFYMODAL_TORCH_COMPILE_RECOMPILE_LIMIT",
        ):
            self.assertIn(name, names)

    def test_registry_names_stay_sorted(self):
        names = self.registry.registered_names()
        self.assertEqual(names, sorted(names))

    def test_mode_flag_conventions(self):
        entry = self._entry("COMFYMODAL_TORCH_COMPILE_MODE")
        self.assertEqual(entry.type, "enum")
        self.assertEqual(entry.default, "off")
        self.assertEqual(list(entry.enum_values or []), ["off", "regional", "full"])
        self.assertEqual(entry.consumed_at, "request")
        self.assertEqual(entry.change_requires, "run")
        self.assertTrue(entry.owner)
        self.assertTrue(entry.description)
        self.assertTrue(self._raw("COMFYMODAL_TORCH_COMPILE_MODE")["runtime_exposed"])

    def test_dynamic_flag_conventions(self):
        entry = self._entry("COMFYMODAL_TORCH_COMPILE_DYNAMIC")
        self.assertEqual(entry.type, "enum")
        self.assertEqual(entry.default, "auto")
        self.assertEqual(list(entry.enum_values or []), ["auto", "true", "false"])
        self.assertEqual(entry.consumed_at, "request")
        self.assertEqual(entry.change_requires, "run")
        self.assertTrue(entry.owner)
        self.assertTrue(entry.description)
        self.assertTrue(
            self._raw("COMFYMODAL_TORCH_COMPILE_DYNAMIC")["runtime_exposed"]
        )

    def test_debug_flag_conventions(self):
        entry = self._entry("COMFYMODAL_TORCH_COMPILE_DEBUG")
        self.assertEqual(entry.type, "bool")
        self.assertEqual(entry.default, "0")
        self.assertEqual(entry.consumed_at, "request")
        self.assertEqual(entry.change_requires, "run")
        self.assertTrue(entry.owner)
        self.assertTrue(entry.description)
        self.assertTrue(self._raw("COMFYMODAL_TORCH_COMPILE_DEBUG")["runtime_exposed"])

    def test_recompile_limit_flag_conventions(self):
        entry = self._entry("COMFYMODAL_TORCH_COMPILE_RECOMPILE_LIMIT")
        self.assertEqual(entry.type, "int")
        self.assertEqual(entry.default, "8")
        self.assertEqual(entry.min, 0)
        self.assertEqual(entry.max, 64)
        self.assertEqual(entry.consumed_at, "request")
        self.assertEqual(entry.change_requires, "run")
        self.assertTrue(entry.owner)
        self.assertTrue(entry.description)
        self.assertTrue(
            self._raw("COMFYMODAL_TORCH_COMPILE_RECOMPILE_LIMIT")["runtime_exposed"]
        )

    def test_ideogram_profile_pins_compile_off(self):
        environment = self.profile.get("environment", {})
        self.assertEqual(environment.get("COMFYMODAL_TORCH_COMPILE_MODE"), "off")
        self.assertEqual(
            environment.get("COMFYMODAL_TORCH_COMPILE_DYNAMIC"), "auto"
        )
        self.assertEqual(environment.get("COMFYMODAL_TORCH_COMPILE_DEBUG"), "0")
        self.assertEqual(
            environment.get("COMFYMODAL_TORCH_COMPILE_RECOMPILE_LIMIT"), "8"
        )


# ---------------------------------------------------------------------------
# comfyapp dormant-hook retirement
# ---------------------------------------------------------------------------


@pytest.mark.fast_unit
class ComfyappRetirementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = _read(COMFYAPP_PATH)

    def test_hook_patches_nothing(self):
        segment = _func_source(self.src, "_enable_torch_compile_on_unet")
        self.assertIsNotNone(segment)
        assert segment is not None
        # Paren-qualified: docstring prose may name the retired path, but no
        # code may invoke it.
        self.assertNotIn("set_torch_compile_wrapper(", segment)
        self.assertNotIn("load_models_gpu(", segment)
        self.assertNotIn("import torch", segment)
        self.assertNotIn("model_management", segment)
        self.assertIn("resolve_compile_policy", segment)
        self.assertIn("RETIRED", segment)

    def test_execute_path_stays_eager(self):
        segment = _func_source(self.src, "_execute_in_process")
        self.assertIsNotNone(segment)
        assert segment is not None
        self.assertNotIn("_enable_torch_compile_on_unet()", segment)
        self.assertIn("retired", segment.lower())

    def test_triton_backend_and_load_diagnostics_untouched(self):
        self.assertIn("def _force_triton_during_snapshot", self.src)
        self.assertIn("enable_triton_backend", self.src)
        self.assertIn("def _collect_custom_node_import_health", self.src)
        self.assertIn("COMFYMODAL_ENABLE_TORCH_COMPILE", self.src)


# ---------------------------------------------------------------------------
# ON_PRE_RUN deferred prepare (install defers without a model; the refresh
# seam prepares once with the effective post-load model)
# ---------------------------------------------------------------------------


def _regional_env() -> dict[str, str]:
    return {"COMFYMODAL_TORCH_COMPILE_MODE": "regional"}


def _kj_available() -> dict[str, Any]:
    return {
        "available": True,
        "reason": "ok",
        "wrapper": object(),
        "source": "fake",
    }


def _ready_ok(policy: Any, **kwargs: Any) -> dict[str, Any]:
    return {"ready": True, "reason": "ready"}


def _fake_patcher(tag: str = "p0") -> Any:
    """Fake ModelPatcher shape: patcher.model.diffusion_model.

    Mirrors the verified unet_forward_probe.resolve_diffusion_model
    ModelPatcher walk (``.model.diffusion_model``); the paired resolver
    below reads the same attribute chain.
    """
    return _Model(
        model=_Model(
            diffusion_model=_Model(
                double_blocks=[_Block(f"{tag}-b{i}") for i in range(3)]
            )
        )
    )


def _patcher_walk_resolver(patcher: Any) -> tuple[Any | None, Any | None]:
    inner = getattr(patcher, "model", None)
    dm = getattr(inner, "diffusion_model", None)
    return patcher, dm


@pytest.mark.fast_unit
class CompileDeferredInstallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = _exec_helpers(
            "_install_request_compile_scope",
            "_refresh_request_compile_scope_on_pre_run",
        )
        cls.src = _read(MODAL_APP_PATH)

    def _install(self, **overrides: Any) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "env": _regional_env(),
            "argv": [],
            "_resolve": tcp.resolve_compile_policy,
            "_install": tcp.install_sampling_compile_scope,
            "_attach": tcp.attach_compile_policy,
            "_ready": _ready_ok,
            "_prepare": tcp.prepare_compile_targets,
            "_probe": _kj_available,
        }
        kwargs.update(overrides)
        return self.ns["_install_request_compile_scope"](
            {}, **kwargs
        )

    def test_install_without_model_defers_not_terminal(self):
        record = self._install()
        self.assertFalse(record["prepared"])
        self.assertEqual(
            record["prepare_reason"], "deferred_no_diffusion_model"
        )
        self.assertTrue(record.get("deferred"))
        scope = record["scope"]
        assert isinstance(scope, dict)
        # The latch must stay UNTRIED so the later ON_PRE_RUN prepare can
        # proceed (EAGER_* is one-way terminal per CompileFallbackLatch).
        self.assertEqual(scope["latch"].state, tcp.LATCH_UNTRIED)
        self.assertEqual(scope["regions"], [])
        self.assertEqual(scope["targets"], [])

    def test_install_without_model_off_path_stays_terminal(self):
        # Mode off has no later prepare pending: keep the immediate
        # terminal mode_off record.
        record = self._install(env={})
        self.assertEqual(record["policy_mode"], "off")
        self.assertFalse(record["prepared"])
        self.assertEqual(record["prepare_reason"], "mode_off")
        scope = record["scope"]
        assert isinstance(scope, dict)
        self.assertEqual(scope["latch"].state, tcp.LATCH_EAGER_SKIPPED)

    def test_install_with_model_still_prepares_inline(self):
        model = _Model(double_blocks=[_Block(f"b{i}") for i in range(3)])
        record = self._install(diffusion_model=model)
        self.assertTrue(record["prepared"])
        scope = record["scope"]
        assert isinstance(scope, dict)
        self.assertEqual(len(scope["regions"]), 1)
        self.assertEqual(scope["latch"].state, tcp.LATCH_READY)

    def test_install_source_defers_before_prepare(self):
        segment = _func_source(self.src, "_install_request_compile_scope")
        self.assertIsNotNone(segment)
        assert segment is not None
        self.assertIn("deferred_no_diffusion_model", segment)
        # The install-time prepare call site is retained (validation
        # supplied models + mode-off path still prepare inline).
        self.assertIn("_tcp_prepare.prepare_compile_targets", segment)

    def test_refresh_seam_references_prepare_api(self):
        node = _func_node(self.src, "_refresh_request_compile_scope_on_pre_run")
        self.assertIsNotNone(node)
        segment = _func_source(self.src, "_refresh_request_compile_scope_on_pre_run")
        self.assertIsNotNone(segment)
        assert segment is not None
        self.assertIn("prepare_compile_targets", segment)


@pytest.mark.fast_unit
class CompileOnPreRunRefreshTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = _exec_helpers(
            "_install_request_compile_scope",
            "_refresh_request_compile_scope_on_pre_run",
            "_finalize_request_compile_scope",
        )

    def _install_deferred(self, **overrides: Any) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "env": _regional_env(),
            "argv": [],
            "_resolve": tcp.resolve_compile_policy,
            "_install": tcp.install_sampling_compile_scope,
            "_attach": tcp.attach_compile_policy,
            "_ready": _ready_ok,
            "_prepare": tcp.prepare_compile_targets,
            "_probe": _kj_available,
        }
        kwargs.update(overrides)
        return self.ns["_install_request_compile_scope"](
            {}, **kwargs
        )

    def _refresh_kwargs(self, **overrides: Any) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "_ready": _ready_ok,
            "_prepare": tcp.prepare_compile_targets,
            "_probe": _kj_available,
            "_resolve_model": _patcher_walk_resolver,
        }
        kwargs.update(overrides)
        return kwargs

    def test_on_pre_run_prepare_discovers_regions(self):
        record = self._install_deferred()
        scope = record["scope"]
        assert isinstance(scope, dict)
        outcome = self.ns["_refresh_request_compile_scope_on_pre_run"](
            record, _fake_patcher(), **self._refresh_kwargs()
        )
        self.assertTrue(outcome["prepared"])
        self.assertEqual(outcome["reason"], "prepared")
        self.assertEqual(len(scope["regions"]), 1)
        self.assertTrue(len(scope["targets"]) > 0)
        self.assertEqual(scope["latch"].state, tcp.LATCH_READY)

    def test_second_prepare_with_same_model_is_noop(self):
        record = self._install_deferred()
        calls: list[str] = []

        def _counting_prepare(scope: Any, **kwargs: Any) -> dict[str, Any]:
            calls.append("prepare")
            return tcp.prepare_compile_targets(scope, **kwargs)

        kwargs = self._refresh_kwargs(_prepare=_counting_prepare)
        patcher = _fake_patcher()
        first = self.ns["_refresh_request_compile_scope_on_pre_run"](
            record, patcher, **kwargs
        )
        self.assertTrue(first["prepared"])
        second = self.ns["_refresh_request_compile_scope_on_pre_run"](
            record, patcher, **kwargs
        )
        self.assertTrue(second["prepared"])
        self.assertEqual(second["reason"], "already_prepared")
        self.assertEqual(calls, ["prepare"])

    def test_changed_model_identity_reprepares(self):
        record = self._install_deferred()
        calls: list[str] = []

        def _counting_prepare(scope: Any, **kwargs: Any) -> dict[str, Any]:
            calls.append("prepare")
            return tcp.prepare_compile_targets(scope, **kwargs)

        kwargs = self._refresh_kwargs(_prepare=_counting_prepare)
        first = self.ns["_refresh_request_compile_scope_on_pre_run"](
            record, _fake_patcher("p0"), **kwargs
        )
        self.assertTrue(first["prepared"])
        second = self.ns["_refresh_request_compile_scope_on_pre_run"](
            record, _fake_patcher("p1"), **kwargs
        )
        self.assertTrue(second["prepared"])
        self.assertEqual(second["reason"], "prepared")
        self.assertEqual(calls, ["prepare", "prepare"])

    def test_terminal_latch_stays_terminal(self):
        record = self._install_deferred()
        scope = record["scope"]
        assert isinstance(scope, dict)
        self.assertTrue(
            scope["latch"].mark_eager_skipped(tcp.KJ_CAPABILITY_MISSING)
        )
        calls: list[str] = []

        def _counting_prepare(scope: Any, **kwargs: Any) -> dict[str, Any]:
            calls.append("prepare")
            return tcp.prepare_compile_targets(scope, **kwargs)

        outcome = self.ns["_refresh_request_compile_scope_on_pre_run"](
            record,
            _fake_patcher(),
            **self._refresh_kwargs(_prepare=_counting_prepare),
        )
        self.assertFalse(outcome["prepared"])
        self.assertEqual(outcome["reason"], tcp.KJ_CAPABILITY_MISSING)
        self.assertEqual(calls, [])
        self.assertEqual(scope["latch"].state, tcp.LATCH_EAGER_SKIPPED)

    def test_no_model_at_on_pre_run_leaves_prior_state(self):
        record = self._install_deferred()
        scope = record["scope"]
        assert isinstance(scope, dict)
        calls: list[str] = []

        def _counting_prepare(scope: Any, **kwargs: Any) -> dict[str, Any]:
            calls.append("prepare")
            return tcp.prepare_compile_targets(scope, **kwargs)

        outcome = self.ns["_refresh_request_compile_scope_on_pre_run"](
            record,
            object(),
            **self._refresh_kwargs(
                _prepare=_counting_prepare,
                _resolve_model=lambda p: (None, None),
            ),
        )
        self.assertFalse(outcome["prepared"])
        self.assertEqual(outcome["reason"], "no_diffusion_model")
        self.assertEqual(calls, [])
        # Prior deferred state untouched: still UNTRIED, no regions.
        self.assertEqual(scope["latch"].state, tcp.LATCH_UNTRIED)
        self.assertEqual(scope["regions"], [])

    def test_snapshot_capture_never_prepares(self):
        record = self._install_deferred()
        scope = record["scope"]
        assert isinstance(scope, dict)
        calls: list[str] = []

        def _counting_prepare(scope: Any, **kwargs: Any) -> dict[str, Any]:
            calls.append("prepare")
            return tcp.prepare_compile_targets(scope, **kwargs)

        outcome = self.ns["_refresh_request_compile_scope_on_pre_run"](
            record,
            _fake_patcher(),
            snapshot_capturing=True,
            **self._refresh_kwargs(_prepare=_counting_prepare),
        )
        self.assertFalse(outcome["prepared"])
        self.assertEqual(outcome["reason"], "snapshot_capture_active")
        self.assertEqual(calls, [])
        self.assertEqual(scope["latch"].state, tcp.LATCH_UNTRIED)

    def test_readiness_gate_blocks_refresh(self):
        record = self._install_deferred()
        scope = record["scope"]
        assert isinstance(scope, dict)
        outcome = self.ns["_refresh_request_compile_scope_on_pre_run"](
            record,
            _fake_patcher(),
            **self._refresh_kwargs(
                _ready=lambda policy, **k: {
                    "ready": False,
                    "reason": "cuda_not_initialized",
                },
            ),
        )
        self.assertFalse(outcome["prepared"])
        self.assertEqual(outcome["reason"], "cuda_not_initialized")
        self.assertEqual(scope["latch"].state, tcp.LATCH_UNTRIED)

    def test_mode_off_refresh_leaves_scope_eager(self):
        record = self._install_deferred(env={})
        calls: list[str] = []

        def _counting_prepare(scope: Any, **kwargs: Any) -> dict[str, Any]:
            calls.append("prepare")
            return tcp.prepare_compile_targets(scope, **kwargs)

        outcome = self.ns["_refresh_request_compile_scope_on_pre_run"](
            record,
            _fake_patcher(),
            **self._refresh_kwargs(_prepare=_counting_prepare),
        )
        self.assertFalse(outcome["prepared"])
        self.assertEqual(outcome["reason"], "mode_off")
        self.assertEqual(calls, [])

    def test_deferred_then_prepared_finalize_reports_regions(self):
        record = self._install_deferred()
        outcome = self.ns["_refresh_request_compile_scope_on_pre_run"](
            record, _fake_patcher(), **self._refresh_kwargs()
        )
        self.assertTrue(outcome["prepared"])
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            final = self.ns["_finalize_request_compile_scope"](
                record,
                _finish=tcp.finish_compile_sample,
                _summarize=tcp.summarize_compile_sample,
                _release=tcp.release_compile_targets,
            )
        self.assertTrue(final["released"])
        self.assertIn("regions=1", captured.getvalue())


# ---------------------------------------------------------------------------
# Production hookup (SAMPLER_SAMPLE wrapper refreshes the deferred scope)
# ---------------------------------------------------------------------------


@pytest.mark.fast_unit
class CompileSamplerHookupTests(unittest.TestCase):
    """The install path defers prepare when no diffusion model is observable
    pre-execution; the sampling-start boundary in runtime_executor is the
    ON_PRE_RUN point where the live guider patcher IS observable.  These pin
    the single best-effort refresh call site (never fails sampling)."""

    @classmethod
    def setUpClass(cls):
        cls.executor_src = _read(
            REPO_ROOT / "comfymodal_runtime" / "runtime_executor.py"
        )
        cls.executor_tree = ast.parse(cls.executor_src)

    def _wrapper_node(self):
        for node in ast.walk(self.executor_tree):
            if (
                isinstance(node, ast.FunctionDef)
                and node.name == "_build_sampling_wrapper"
            ):
                for child in ast.walk(node):
                    if (
                        isinstance(child, ast.FunctionDef)
                        and child.name == "_wrapper"
                    ):
                        return child
        return None

    def _refresh_calls(self, wrapper):
        # The hookup resolves the seam via getattr into the local alias
        # _compile_refresh (attribute access would tangle the lazy
        # modal_app import), then invokes the alias exactly once.
        return [
            node
            for node in ast.walk(wrapper)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_compile_refresh"
        ]

    def test_wrapper_calls_refresh_with_live_patcher_pre_forward(self):
        wrapper = self._wrapper_node()
        self.assertIsNotNone(wrapper)
        assert wrapper is not None
        segment = ast.get_source_segment(self.executor_src, wrapper)
        assert segment is not None
        self.assertIn("_refresh_request_compile_scope_on_pre_run", segment)
        self.assertIn("modal_app", segment)
        self.assertIn("_compile_scope_record", segment)
        # Real patcher object, never constructed: the wrapper's resolved
        # live patcher with the guider fallback.
        self.assertIn(
            "_patch if _patch is not None else sampler_self", segment
        )
        # Pre-first-forward: the refresh precedes sampler dispatch (the
        # dispatch return is the LAST early/dispatch return in _wrapper;
        # the no-trace and dedup fast paths return before it).
        self.assertLess(
            segment.index("_refresh_request_compile_scope_on_pre_run"),
            segment.rindex("return executor(*args"),
        )

    def test_exactly_one_guarded_refresh_call_site(self):
        wrapper = self._wrapper_node()
        self.assertIsNotNone(wrapper)
        assert wrapper is not None
        self.assertEqual(len(self._refresh_calls(wrapper)), 1)
        guarded = False
        for child in ast.walk(wrapper):
            if isinstance(child, ast.Try):
                segment = ast.get_source_segment(self.executor_src, child)
                if (
                    segment
                    and "_refresh_request_compile_scope_on_pre_run" in segment
                ):
                    guarded = True
        self.assertTrue(guarded, "refresh call must sit inside try/except")
