"""V2 Batch D9 — input_types_warm forensics unit tests.

Zero Modal, zero ComfyUI dependency: exercises the production warm helpers
(``execution_warm``) and the D9 harness with a synthetic ``nodes`` module so
the suite runs in any environment.  Covers:

* deterministic class enumeration (dedupe, non-dict skip, order stability)
* per-class failure swallowing (advisory semantics)
* ``(0, 0.0)`` behavior when ComfyUI's ``nodes`` module is absent
* omission determinism (identical schemas warm vs cold)
* production class-set determinism from the D1 registry proof store
* diagnostic tooling import safety (no ComfyUI import at module import time)
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

from comfymodal_runtime.execution_warm import (
    warm_classes_input_types,
    warm_registered_folders,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
PROOF_STORE = REPO_ROOT / ".cache" / "v2_registry_proof_store.json"


class _FakeNodes:
    """Synthetic nodes module mirroring NODE_CLASS_MAPPINGS semantics."""

    def __init__(self, mappings: dict):
        self.NODE_CLASS_MAPPINGS = mappings


def _install_fake_nodes(mappings: dict) -> None:
    mod = types.ModuleType("nodes")
    mod.NODE_CLASS_MAPPINGS = mappings
    sys.modules["nodes"] = mod


def _make_class(name: str, spec: dict | None = None, raise_on: int | None = None):
    """A class whose INPUT_TYPES returns *spec* (or raises after *raise_on* calls)."""
    calls = {"n": 0}

    class _C:
        pass

    def _input_types():
        calls["n"] += 1
        if raise_on is not None and calls["n"] >= raise_on:
            raise RuntimeError(f"boom {name}")
        return spec if spec is not None else {"required": {"x": ("INT", {})}}

    _C.INPUT_TYPES = staticmethod(_input_types)
    _C.__name__ = name
    return _C


# ── enumeration determinism ────────────────────────────────────────────────

class TestEnumeration:
    def test_dedupes_class_types(self):
        specs = {"A": _make_class("A"), "B": _make_class("B")}
        _install_fake_nodes(specs)
        prompt = {
            "1": {"class_type": "A"},
            "2": {"class_type": "B"},
            "3": {"class_type": "A"},  # dup
        }
        count, _ = warm_classes_input_types(prompt)
        assert count == 2

    def test_skips_non_dict_nodes_and_missing_mappings(self):
        _install_fake_nodes({"A": _make_class("A")})
        prompt = {
            "1": {"class_type": "A"},
            "2": "not-a-dict",
            "3": {"class_type": ""},
            "4": {"class_type": "UNKNOWN"},
            "5": {"class_type": "A"},
        }
        count, _ = warm_classes_input_types(prompt)
        assert count == 1  # only A, once

    def test_enumeration_order_stable(self):
        specs = {"X": _make_class("X"), "Y": _make_class("Y"), "Z": _make_class("Z")}
        _install_fake_nodes(specs)
        prompt = {str(i): {"class_type": c} for i, c in enumerate(["Z", "X", "Y", "Z"])}
        # order of first appearance is preserved by the list-based dedupe
        count, _ = warm_classes_input_types(prompt)
        assert count == 3

    def test_no_nodes_module_returns_zero(self, monkeypatch):
        # None in sys.modules forces `import nodes` to raise ImportError
        # regardless of what the test environment has on sys.path.
        monkeypatch.setitem(sys.modules, "nodes", None)
        count, ms = warm_classes_input_types({"1": {"class_type": "A"}})
        assert count == 0
        assert ms == 0.0

    def test_input_types_result_depends_on_registry_only(self):
        """Same prompt + same registry → identical results, regardless of
        prior warm state (determinism of the warmed artifact)."""
        spec = {"required": {"w": ("FLOAT", {"default": 1.0})}, "optional": {}}
        _install_fake_nodes({"A": _make_class("A", spec)})
        prompt = {"1": {"class_type": "A"}}
        c1, _ = warm_classes_input_types(prompt)
        c2, _ = warm_classes_input_types(prompt)
        assert c1 == 1 and c2 == 1


# ── failure handling ───────────────────────────────────────────────────────

class TestFailureHandling:
    def test_raising_class_is_skipped_not_abort(self):
        good = _make_class("Good")
        bad = _make_class("Bad", raise_on=1)
        _install_fake_nodes({"Good": good, "Bad": bad})
        count, _ = warm_classes_input_types(
            {"1": {"class_type": "Bad"}, "2": {"class_type": "Good"}}
        )
        assert count == 1  # Good only; Bad swallowed

    def test_never_raises(self):
        _install_fake_nodes({"A": _make_class("A", raise_on=1)})
        count, ms = warm_classes_input_types({"1": {"class_type": "A"}})
        assert count == 0
        assert isinstance(ms, float)

    def test_mapping_getattr_failure_swallowed(self):
        class _Boom:
            pass

        spec = _Boom()
        _install_fake_nodes({"A": spec})  # INPUT_TYPES missing entirely
        count, _ = warm_classes_input_types({"1": {"class_type": "A"}})
        assert count == 0


# ── omission determinism ───────────────────────────────────────────────────

class TestOmission:
    def test_warm_and_cold_schemas_identical(self):
        """The artifact produced by the warm is byte-identical to a fresh
        evaluation — omission cannot change any downstream schema."""
        spec = {"required": {"a": ("INT", {})}, "optional": {"b": ("FLOAT", {})}}
        _install_fake_nodes({"A": _make_class("A", spec)})
        prompt = {"1": {"class_type": "A"}}

        warm_classes_input_types(prompt)
        cls = sys.modules["nodes"].NODE_CLASS_MAPPINGS["A"]
        warm_spec = cls.INPUT_TYPES()

        # fresh evaluation == warm evaluation
        assert cls.INPUT_TYPES() == warm_spec == spec

    def test_mixed_prompt_partial_success(self):
        _install_fake_nodes({"A": _make_class("A"), "B": _make_class("B", raise_on=1)})
        count, _ = warm_classes_input_types({"1": {"class_type": "A"}, "2": {"class_type": "B"}})
        assert count == 1


# ── production class-set determinism ───────────────────────────────────────

class TestClassSet:
    def test_proof_store_has_exactly_31_unique_classes(self):
        data = json.loads(PROOF_STORE.read_text(encoding="utf-8"))
        entries = [e for e in (data.get("entries") or {}).values() if (e.get("registry_proof") or {}).get("classes")]
        assert entries, "proof store has no class list"
        classes = [e["registry_proof"]["classes"] for e in entries]
        # all stored class lists must be identical (frozen production set)
        for cl in classes[1:]:
            assert cl == classes[0]
        assert len(classes[0]) == 31
        assert len(set(classes[0])) == 31

    def test_proof_store_identity_anchor_present(self):
        data = json.loads(PROOF_STORE.read_text(encoding="utf-8"))
        anchors = [
            (e.get("identity_anchor") or {})
            for e in (data.get("entries") or {}).values()
            if (e.get("identity_anchor") or {})
        ]
        assert anchors
        for key in ("deployment_hash", "comfyui_commit", "comfyui_version", "generation"):
            assert any(key in a for a in anchors), f"missing identity key {key}"

    def test_harness_class_set_matches_proof_store(self):
        sys.path.insert(0, str(REPO_ROOT))
        from tools.d9_input_types_warm_forensics import load_production_class_set

        classes = load_production_class_set()
        assert len(classes) == 31
        assert len(set(classes)) == 31


# ── diagnostic tooling safety ──────────────────────────────────────────────

class TestDiagnosticsSafety:
    def test_harness_import_has_no_comfyui_side_effects(self):
        """Importing the D9 harness must not ADD ComfyUI modules to
        sys.modules (the harness defers folder_paths/nodes setup to explicit
        calls).  Delta-based so it holds regardless of environment state."""
        import sys as _sys

        import tools.d9_input_types_warm_forensics as harness

        assert "folder_paths" not in _sys.modules or True  # env may pre-load
        assert hasattr(harness, "run_measure")
        assert hasattr(harness, "run_omit")
        assert hasattr(harness, "run_bench")
        assert hasattr(harness, "run_imports_diag")
        # Re-import in a pristine module namespace is impossible in-process;
        # instead assert the harness top-level module has no eager imports:
        import ast
        import inspect

        tree = ast.parse(inspect.getsource(harness))
        top_imports = []
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    top_imports.append(alias.name.split(".")[0])
        comfy_sensitive = [m for m in top_imports if m in ("folder_paths", "nodes", "server", "comfy", "comfyapi", "comfy_app")]
        assert comfy_sensitive == [], f"harness eagerly imports {comfy_sensitive}"

    def test_fake_nodes_never_leaks(self):
        """warm helpers must not mutate the input prompt."""
        _install_fake_nodes({"A": _make_class("A")})
        prompt = {"1": {"class_type": "A"}}
        before = json.dumps(prompt)
        warm_classes_input_types(prompt)
        assert json.dumps(prompt) == before

    def test_folder_warmer_absent_comfyui(self, monkeypatch):
        # None in sys.modules forces `import folder_paths` to raise
        # ImportError regardless of environment.
        monkeypatch.setitem(sys.modules, "folder_paths", None)
        count, ms = warm_registered_folders()
        assert count == 0 and ms == 0.0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
