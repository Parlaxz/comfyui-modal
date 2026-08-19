"""Phase 1 of the Step-3 acceptance retry: the V2 direct benchmark harness must
build its plans the SAME way the production v2 dispatch does.

Covered here:
  - AST: both ``build_execution_plan(...)`` call sites in
    ``tools/benchmark_v2_direct.py`` pass ``collect_validation_proof=True`` and
    a ``comfyui_root`` keyword (mirroring the production call site in
    ``__init__.py``), so the plan carries the validation payload and a registry
    fingerprint whose surface matches the container's (builtin classes
    included) - making the fast path reachable.
  - Behavior: with ``execution``/``nodes`` stubbed, a plan built through the
    same kwargs carries the validation payload (schema_version, validated flag,
    sorted outputs_to_execute, validated_workflow_hash == workflow_hash) and a
    deployment identity exposing the expected keys.
  - Behavior: ``comfyui_root`` feeds the registry-fingerprint roots filter;
    in-root stub classes are included while out-of-root stub classes are
    excluded (proving the filter selects the container-surface classes).
  - AST: the harness mirrors the ComfyUI server startup registry - exactly one
    ``_ensure_full_node_registry`` definition exists and both plan-building
    functions await it BEFORE ``build_execution_plan(...)`` (so comfy_extras /
    custom-node classes are registered before validation and fingerprinting).
  - AST: the registry helper pins the real ComfyUI ``utils`` package into
    sys.modules by explicit file path (``spec_from_file_location("utils",
    ...)`` + ``sys.modules["utils"] = ...``) BEFORE ``import nodes`` and
    ``nodes.init_extra_nodes(...)``, so ``import utils`` can never resolve to
    ``comfy\\utils.py`` (nodes.py puts ``<root>\\comfy`` on sys.path[0]) or a
    CacheDiT-style plain ``utils.py`` for later node imports.
  - AST: the registry helper mirrors main.py:470 by constructing a
    ``PromptServer(...)`` (assigning ``PromptServer.instance``) BEFORE
    ``nodes.init_extra_nodes(...)``, so import-time ``PromptServer.instance``
    decorators in Impact Pack / RES4LYF / comfyui-manager can register.
  - AST: after ``nodes.init_extra_nodes(...)`` the helper mirrors comfyapp's
    manual registration (comfyapp.py:18186-18188) of the production output
    classes (``ComfyModalProductionOutput``, ``ComfyModalProductionImageComparerOutput``)
    into ``nodes.NODE_CLASS_MAPPINGS`` via AST extraction (never ``import
    comfyapp`` — its module body makes Modal ``Volume.from_name`` network
    calls).

All tests are local (no Modal, no paid anything).  ``execution`` and ``nodes``
are stubbed via ``sys.modules`` so the parent-ComfyUI modules are never
imported (same pattern as tests/test_plan_validation_proof.py).
"""

import ast
import importlib.util
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

from comfymodal_runtime.contracts import (
    VALIDATION_PROOF_SCHEMA_VERSION,
    compute_registry_fingerprint,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
HARNESS_PATH = REPO_ROOT / "tools" / "benchmark_v2_direct.py"

# A small valid 2-node workflow shape (same shape as the plan-proof tests).
WORKFLOW_A = {
    "1": {"class_type": "X", "inputs": {}},
    "2": {"class_type": "Y", "inputs": {"a": ["1", 0]}},
}


class _DummyNode:
    """Simple stand-in for a NODE_CLASS_MAPPINGS entry."""


_REMOVE = object()
"""Sentinel for ``_stub_modules``: remove the key instead of stubbing it."""


def _load_canonical():
    """Load canonical_execution module without parent-ComfyUI imports."""
    spec = importlib.util.spec_from_file_location(
        "canonical_execution", REPO_ROOT / "canonical_execution.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["canonical_execution"] = mod
    spec.loader.exec_module(mod)
    return mod


def _make_fake_execution(outputs, valid=True, error=None, node_errors=None):
    """Fake ``execution`` module whose validate_prompt is controllable.

    Mirrors the production contract: returns
    ``(valid, error, outputs, node_errors)``.
    """
    mod = types.ModuleType("execution")

    async def validate_prompt(prompt_id, prompt, partial_execution_list=None):
        return (valid, error, outputs, node_errors or {})

    mod.validate_prompt = validate_prompt
    return mod


def _make_fake_nodes(mappings=None):
    """Fake ``nodes`` module carrying a NODE_CLASS_MAPPINGS registry."""
    mod = types.ModuleType("nodes")
    if mappings is None:
        mappings = {"X": _DummyNode, "Y": _DummyNode}
    mod.NODE_CLASS_MAPPINGS = mappings
    return mod


class _stub_modules:
    """Context manager installing module stubs into sys.modules.

    A value of ``_REMOVE`` pops the key (restoring it afterwards).
    """

    def __init__(self, stubs):
        self._stubs = stubs
        self._saved = {}

    def __enter__(self):
        for name, value in self._stubs.items():
            self._saved[name] = sys.modules.get(name)
            if value is _REMOVE:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value
        return self

    def __exit__(self, exc_type, exc, tb):
        for name, value in self._saved.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value
        return False


class TestBenchmarkV2ProofCollection(unittest.TestCase):
    def setUp(self):
        import tempfile as _tf
        import shutil as _sh
        self._td = _tf.mkdtemp()
        self.addCleanup(lambda: _sh.rmtree(self._td, ignore_errors=True))
        self._saved_store = os.environ.get("COMFYMODAL_V2_REGISTRY_PROOF_STORE")
        # Isolate the D1 registry-proof store: build_execution_plan persists
        # when .deployed_state.json exists (deploy-frozen identity), so point
        # the store at a fresh temp path to avoid writing synthetic test
        # payloads into the real repo store.
        os.environ["COMFYMODAL_V2_REGISTRY_PROOF_STORE"] = os.path.join(
            self._td, "v2_registry_proof_store.json"
        )
        self.addCleanup(self._restore_store_env)
        self.mod = _load_canonical()

    def _restore_store_env(self):
        if self._saved_store is None:
            os.environ.pop("COMFYMODAL_V2_REGISTRY_PROOF_STORE", None)
        else:
            os.environ["COMFYMODAL_V2_REGISTRY_PROOF_STORE"] = self._saved_store

    # ── AST: harness call sites request the proof payload ────────────────

    def test_harness_call_sites_request_proof_collection(self):
        """All build_execution_plan call sites in the benchmark harness pass
        collect_validation_proof (literal True or the module flag that
        defaults to True) AND a comfyui_root keyword (mirroring the
        production v2 dispatch).  Three call sites: _run_one, the acceptance
        request, and the D1 --prime-registry-proof prime mode (the latter
        also requests the proof payload so the persisted store entry covers
        it)."""
        source = HARNESS_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "build_execution_plan"
        ]
        self.assertEqual(len(calls), 3)
        uses_flag = False
        for call in calls:
            kwargs = {kw.arg: kw.value for kw in call.keywords}
            self.assertIn("collect_validation_proof", kwargs)
            proof_value = kwargs["collect_validation_proof"]
            if isinstance(proof_value, ast.Constant):
                self.assertIs(proof_value.value, True)
            else:
                # Module flag form: collect_validation_proof=_PLAN_VALIDATION_PROOF
                self.assertIsInstance(proof_value, ast.Name)
                self.assertEqual(proof_value.id, "_PLAN_VALIDATION_PROOF")
                uses_flag = True
            self.assertIn("comfyui_root", kwargs)
        if uses_flag:
            # The flag defaults to True: _PLAN_VALIDATION_PROOF = env_flag(
            # "COMFYMODAL_V2_PLAN_VALIDATION_PROOF", default=True).
            assigns = [
                node for node in ast.walk(tree)
                if isinstance(node, ast.Assign)
                and node.targets
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "_PLAN_VALIDATION_PROOF"
            ]
            self.assertEqual(len(assigns), 1)
            call = assigns[0].value
            self.assertIsInstance(call, ast.Call)
            defaults = {kw.arg: kw.value for kw in call.keywords}
            self.assertIn("default", defaults)
            self.assertIsInstance(defaults["default"], ast.Constant)
            self.assertIs(defaults["default"].value, True)

    # ── Behavior: plan carries the validation payload ────────────────────

    def test_harness_plan_carries_validation_payload(self):
        """A plan built with the harness kwargs carries the validation proof:
        schema_version, validated flag, sorted outputs, hash binding."""
        with tempfile.TemporaryDirectory() as tmp_root:
            with _stub_modules({
                "execution": _make_fake_execution(["9", "5"]),
                "nodes": _make_fake_nodes(),
            }):
                plan = self.mod.build_execution_plan(
                    dict(WORKFLOW_A), prompt_id="p1",
                    request_metadata={"benchmark_run_index": 0, "benchmark_app": "test"},
                    trace=None, validate=False,
                    collect_validation_proof=True,
                    comfyui_root=tmp_root,
                )
        validation = dict(plan.validation)
        self.assertEqual(validation.get("schema_version"), VALIDATION_PROOF_SCHEMA_VERSION)
        self.assertEqual(validation.get("schema_version"), 1)
        self.assertIs(validation.get("validated"), True)
        # ExecutionPlan freezes list values into tuples; compare sorted ids.
        self.assertEqual(list(validation.get("outputs_to_execute") or []), ["5", "9"])
        self.assertEqual(
            validation.get("validated_workflow_hash"), plan.workflow_hash,
        )
        dep = dict(plan.deployment_identity)
        for key in (
            "deployment_combined_hash",
            "custom_nodes_generation",
            "registry_fingerprint",
            "dependency_manifest_identity",
            "complete",
        ):
            self.assertIn(key, dep)

    # ── Behavior: comfyui_root feeds the registry-fingerprint filter ─────

    def test_harness_plan_comfyui_root_passed(self):
        """Passing comfyui_root still yields a non-empty registry fingerprint
        (the roots filter includes the builtin-surface stub classes)."""
        with tempfile.TemporaryDirectory() as tmp_root:
            with _stub_modules({
                "execution": _make_fake_execution(["5"]),
                "nodes": _make_fake_nodes(),
            }):
                plan = self.mod.build_execution_plan(
                    dict(WORKFLOW_A), prompt_id="p2",
                    request_metadata={"benchmark_run_index": 0, "benchmark_app": "test"},
                    trace=None, validate=False,
                    collect_validation_proof=True,
                    comfyui_root=tmp_root,
                )
        dep = dict(plan.deployment_identity)
        self.assertTrue(dep.get("registry_fingerprint"))

    def test_registry_fingerprint_is_root_filtered(self):
        """In-root stub classes are included while out-of-root stub classes are
        excluded when roots are supplied - proving comfyui_root drives the
        container-surface filter (builtin classes included on the host)."""
        with tempfile.TemporaryDirectory() as tmp_root:
            in_mod = types.ModuleType("nodes_in_root")
            in_mod.__file__ = os.path.join(tmp_root, "nodes_in_root.py")

            out_mod = types.ModuleType("nodes_outside")
            out_mod.__file__ = os.path.join(
                os.path.dirname(tmp_root), "outside_of_root", "nodes_outside.py",
            )

            class InRootNode:
                pass
            InRootNode.__module__ = "nodes_in_root"

            class OutRootNode:
                pass
            OutRootNode.__module__ = "nodes_outside"

            mappings = {"InRoot": InRootNode, "OutRoot": OutRootNode}
            with _stub_modules({
                "nodes_in_root": in_mod,
                "nodes_outside": out_mod,
            }):
                full = compute_registry_fingerprint(mappings)
                filtered = compute_registry_fingerprint(mappings, roots=[tmp_root])
        self.assertTrue(full)
        self.assertTrue(filtered)
        self.assertNotEqual(full, filtered)

    def test_harness_awaits_full_node_registry_before_plan_build(self):
        """The harness mirrors the ComfyUI server startup registry: exactly one
        definition of ``_ensure_full_node_registry`` exists, and both
        plan-building functions (``_run_one``, ``_run_acceptance_request``)
        await it BEFORE their ``build_execution_plan(...)`` call."""
        source = HARNESS_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)

        def _defs_named(name):
            return [
                node for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == name
            ]

        # Exactly one definition of the registry helper.
        helper_defs = _defs_named("_ensure_full_node_registry")
        self.assertEqual(len(helper_defs), 1)

        def _first_call_line(fn_node, func_name):
            return min(
                node.lineno
                for node in ast.walk(fn_node)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == func_name
            )

        for fn_name in ("_run_one", "_run_acceptance_request"):
            # Defensively pick the definition that actually builds a plan.
            plan_builders = [
                node for node in _defs_named(fn_name)
                if any(
                    isinstance(c, ast.Call)
                    and isinstance(c.func, ast.Name)
                    and c.func.id == "build_execution_plan"
                    for c in ast.walk(node)
                )
            ]
            self.assertEqual(len(plan_builders), 1)
            fn = plan_builders[0]
            registry_call_line = _first_call_line(fn, "_ensure_full_node_registry")
            plan_build_line = _first_call_line(fn, "build_execution_plan")
            self.assertLess(
                registry_call_line, plan_build_line,
                f"{fn_name}: _ensure_full_node_registry() must be awaited "
                "before build_execution_plan(",
            )

    def test_harness_prelocks_utils_before_init_extra_nodes(self):
        """The registry helper pins the real ComfyUI ``utils`` package into
        sys.modules by explicit file path (``spec_from_file_location("utils",
        ...)`` + ``sys.modules["utils"] = ...``) BEFORE ``import nodes``
        (which itself inserts ``<root>\\comfy`` at sys.path[0], ComfyUI
        nodes.py:23) and BEFORE ``nodes.init_extra_nodes`` — so a plain
        ``import utils`` can never resolve to ``comfy\\utils.py`` or a
        CacheDiT-style ``utils.py`` module (breaks ``utils.install_util``
        consumers such as comfyui-impact-pack and RES4LYF)."""
        source = HARNESS_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        helper = next(
            node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "_ensure_full_node_registry"
        )
        try_blocks = [node for node in ast.walk(helper) if isinstance(node, ast.Try)]
        # Outer try is first in BFS order; inner tries (e.g. the production-
        # output registration block) are nested inside it.
        self.assertGreaterEqual(len(try_blocks), 1)
        try_block = try_blocks[0]

        # Pinned pre-lock: spec_from_file_location("utils", <root>\utils\__init__.py)
        pin_spec_calls = [
            node for node in ast.walk(try_block)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "spec_from_file_location"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == "utils"
        ]
        self.assertEqual(len(pin_spec_calls), 1)

        # Pinned pre-lock: sys.modules["utils"] = <pinned module>
        sys_modules_utils_assigns = [
            node for node in ast.walk(try_block)
            if isinstance(node, ast.Assign)
            and node.targets
            and isinstance(node.targets[0], ast.Subscript)
            and isinstance(node.targets[0].value, ast.Attribute)
            and isinstance(node.targets[0].value.value, ast.Name)
            and node.targets[0].value.value.id == "sys"
            and node.targets[0].value.attr == "modules"
            and isinstance(node.targets[0].slice, ast.Constant)
            and node.targets[0].slice.value == "utils"
        ]
        self.assertEqual(len(sys_modules_utils_assigns), 1)

        import_lines = {}
        for node in ast.walk(try_block):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    import_lines[alias.name] = node.lineno
        self.assertIn("utils.install_util", import_lines)

        nodes_imports = [
            node for node in ast.walk(try_block)
            if isinstance(node, ast.Import)
            and any(alias.name == "nodes" for alias in node.names)
        ]
        self.assertEqual(len(nodes_imports), 1)

        init_calls = [
            node for node in ast.walk(try_block)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "nodes"
            and node.func.attr == "init_extra_nodes"
        ]
        self.assertEqual(len(init_calls), 1)

        for _label, _line in (
            ("spec_from_file_location(\"utils\", ...) pre-lock", pin_spec_calls[0].lineno),
            ("sys.modules[\"utils\"] pin", sys_modules_utils_assigns[0].lineno),
            ("import utils.install_util", import_lines["utils.install_util"]),
        ):
            self.assertLess(
                _line, nodes_imports[0].lineno,
                f"{_label} must appear before import nodes",
            )
            self.assertLess(
                _line, init_calls[0].lineno,
                f"{_label} must appear before nodes.init_extra_nodes(",
            )

    def test_harness_constructs_prompt_server_mirror(self):
        """The registry helper mirrors main.py:470 — it constructs a
        PromptServer (which assigns ``PromptServer.instance`` in its
        __init__, server.py:205) BEFORE ``nodes.init_extra_nodes`` runs, so
        packs that decorate ``@PromptServer.instance.routes`` at import time
        (Impact Pack, RES4LYF, comfyui-manager, ...) can register."""
        source = HARNESS_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        helper = next(
            node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "_ensure_full_node_registry"
        )

        imports = {
            alias.name
            for node in ast.walk(helper)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        self.assertIn("server", imports)

        prompt_server_calls = [
            node for node in ast.walk(helper)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "server"
            and node.func.attr == "PromptServer"
        ]
        self.assertEqual(len(prompt_server_calls), 1)

        init_calls = [
            node for node in ast.walk(helper)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "nodes"
            and node.func.attr == "init_extra_nodes"
        ]
        self.assertEqual(len(init_calls), 1)
        self.assertLess(
            prompt_server_calls[0].lineno, init_calls[0].lineno,
            "PromptServer(...) must be constructed before nodes.init_extra_nodes(",
        )

    def test_harness_registers_production_output_classes(self):
        """After init_extra_nodes, the helper mirrors comfyapp.py:18186-18188
        by registering the comfyui-modal production output classes
        (ComfyModalProductionOutput, ComfyModalProductionImageComparerOutput)
        into nodes.NODE_CLASS_MAPPINGS — so the benchmark workflow's
        production-compiled graph validates host-side and the registry
        fingerprint matches the container's.  The registration must NOT
        ``import comfyapp`` (its module body makes Modal Volume.from_name
        network calls); it must use the AST-extraction path instead."""
        source = HARNESS_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        helper = next(
            node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "_ensure_full_node_registry"
        )
        try_blocks = [node for node in ast.walk(helper) if isinstance(node, ast.Try)]
        # Outer try is first in BFS order; the production-output registration
        # block adds a nested inner try.
        self.assertGreaterEqual(len(try_blocks), 1)
        try_block = try_blocks[0]

        init_calls = [
            node for node in ast.walk(try_block)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "nodes"
            and node.func.attr == "init_extra_nodes"
        ]
        self.assertEqual(len(init_calls), 1)
        _init_line = init_calls[0].lineno

        # Both production class names appear in the registration block.
        class_name_consts = {
            node.value
            for node in ast.walk(try_block)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value in (
                "ComfyModalProductionOutput",
                "ComfyModalProductionImageComparerOutput",
            )
        }
        self.assertIn("ComfyModalProductionOutput", class_name_consts)
        self.assertIn("ComfyModalProductionImageComparerOutput", class_name_consts)

        # Registration assigns into nodes.NODE_CLASS_MAPPINGS AFTER
        # init_extra_nodes.
        mapping_assigns = [
            node for node in ast.walk(try_block)
            if isinstance(node, ast.Assign)
            and node.targets
            and isinstance(node.targets[0], ast.Subscript)
            and isinstance(node.targets[0].value, ast.Attribute)
            and isinstance(node.targets[0].value.value, ast.Name)
            and node.targets[0].value.value.id == "nodes"
            and node.targets[0].value.attr == "NODE_CLASS_MAPPINGS"
        ]
        self.assertGreaterEqual(len(mapping_assigns), 1)
        for _node in mapping_assigns:
            self.assertGreater(
                _node.lineno, _init_line,
                "production classes must be registered after nodes.init_extra_nodes(",
            )

        # AST-extraction mechanism is used (parse of comfyapp source) and the
        # unsafe ``import comfyapp`` is NOT used in the helper.
        parse_calls = [
            node for node in ast.walk(try_block)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "parse"
        ]
        self.assertGreaterEqual(len(parse_calls), 1)
        comfyapp_imports = [
            node for node in ast.walk(helper)
            if isinstance(node, ast.Import)
            and any(alias.name == "comfyapp" for alias in node.names)
        ]
        self.assertEqual(len(comfyapp_imports), 0)

    def test_run_one_prints_waterfall_unconditionally(self):
        """The per-run waterfall table must be printed after EVERY completed
        benchmark request, even when ``_defer_waterfall=True`` (the single-run
        path).  The ``render_waterfall(...)`` print in ``_run_one`` must be a
        statement-level call — NOT wrapped in an ``if not _defer_waterfall:``
        gate (nor any other ``if``/``try``) — and both the host-reconciled
        header and the reconcile-unavailable fallback header must exist."""
        source = HARNESS_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        run_one = next(
            node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "_run_one"
            and any(
                isinstance(c, ast.Call)
                and isinstance(c.func, ast.Name)
                and c.func.id == "build_execution_plan"
                for c in ast.walk(node)
            )
        )

        # Call-site compatibility: _defer_waterfall stays in the signature but
        # must no longer suppress the per-run print.
        arg_names = [a.arg for a in run_one.args.args + run_one.args.kwonlyargs]
        self.assertIn("_defer_waterfall", arg_names)

        render_calls = [
            node for node in ast.walk(run_one)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "render_waterfall"
        ]
        self.assertEqual(
            len(render_calls), 1,
            "expected exactly one per-run render_waterfall(...) print in _run_one",
        )

        # The render call must sit directly in the function body — no `if`
        # (the former `if not _defer_waterfall:` gate) and no `try` above it.
        target = render_calls[0]
        enclosing_ifs = []
        enclosing_trys = []

        def _collect_ancestors(node, chain):
            if node is target:
                enclosing_ifs.extend(n for n in chain if isinstance(n, ast.If))
                enclosing_trys.extend(n for n in chain if isinstance(n, ast.Try))
                return True
            return any(
                _collect_ancestors(child, chain + [node])
                for child in ast.iter_child_nodes(node)
            )

        _collect_ancestors(run_one, [])
        self.assertEqual(
            enclosing_ifs, [],
            "per-run render_waterfall(...) print must not be gated behind an "
            "if (e.g. `if not _defer_waterfall:`)",
        )
        self.assertEqual(
            enclosing_trys, [],
            "per-run render_waterfall(...) print must not be swallowed by a try",
        )

        # Both headers are present: the reconciled header and the fallback
        # warning printed when host reconciliation is unavailable.
        self.assertIn("WATERFALL (host-reconciled)", source)
        self.assertIn(
            "WATERFALL (host reconcile unavailable - remote/partial report below)",
            source,
        )


if __name__ == "__main__":
    unittest.main()
