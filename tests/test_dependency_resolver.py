"""Tests for the workflow dependency resolver (dependency_resolver.py).

The resolver reads the persisted stores only.  Because the real ComfyUI
``nodes`` module is unavailable in the test environment, a fake ``nodes``
module is registered in ``sys.modules`` so core classes (e.g.
``CheckpointLoaderSimple``) resolve to ComfyUI core while
``SomeCustomClass`` resolves to a custom-node directory on disk.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path

import pytest

from tests import _test_env  # noqa: F401  (hide real ComfyUI from sys.path)

from custom_node_registry import CustomNodeRegistryStore
from dependency_resolver import DependencyResolver
from model_library import ModelLibraryService
import remote_inventory
from studio_domain import (
    WorkflowDomainService,
    WorkflowPresetValidationError,
    derive_mapping_candidates,
)

pytestmark = pytest.mark.fast_unit


def make_capture(prompt_nodes: dict) -> dict:
    return {
        "graph_json": {"id": "g1", "nodes": []},
        "api_prompt_json": {"workflow": {}, "output": prompt_nodes},
    }


def loader_prompt() -> dict:
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "krea_model.safetensors"}},
        "2": {"class_type": "SaveImage", "inputs": {"images": ["1", 0]}},
    }


def custom_prompt() -> dict:
    """Loader + a custom node class + output node."""
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "krea_model.safetensors"}},
        "2": {"class_type": "SomeCustomClass", "inputs": {}},
        "3": {"class_type": "SaveImage", "inputs": {}},
    }


class _FakeNodes:
    """In-process fake ``nodes`` module with file-resolvable classes."""

    def __init__(self, comfyui_root: Path) -> None:
        self._prior_nodes = sys.modules.get("nodes")
        core_mod = types.ModuleType("_dep_core_nodes_mod")
        core_mod.__file__ = str(comfyui_root / "nodes.py")
        kj_mod = types.ModuleType("_dep_kj_nodes_mod")
        kj_mod.__file__ = str(comfyui_root / "custom_nodes" / "ComfyUI-KJNodes" / "nodes.py")
        sys.modules[core_mod.__name__] = core_mod
        sys.modules[kj_mod.__name__] = kj_mod
        self._mods = (core_mod.__name__, kj_mod.__name__)

        def _cls(mod, name):
            cls = type(name, (), {})
            cls.__module__ = mod.__name__
            return cls

        self.nodes_mod = types.ModuleType("nodes")
        setattr(
            self.nodes_mod,
            "NODE_CLASS_MAPPINGS",
            {
                "CheckpointLoaderSimple": _cls(core_mod, "CheckpointLoaderSimple"),
                "SaveImage": _cls(core_mod, "SaveImage"),
                "CLIPTextEncode": _cls(core_mod, "CLIPTextEncode"),
                "KSampler": _cls(core_mod, "KSampler"),
                "EmptyLatentImage": _cls(core_mod, "EmptyLatentImage"),
                "SomeCustomClass": _cls(kj_mod, "SomeCustomClass"),
            },
        )
        sys.modules["nodes"] = self.nodes_mod

    def cleanup(self) -> None:
        for name in self._mods:
            sys.modules.pop(name, None)
        if sys.modules.get("nodes") is self.nodes_mod:
            if self._prior_nodes is not None:
                sys.modules["nodes"] = self._prior_nodes
            else:
                sys.modules.pop("nodes", None)


class DependencyResolverTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.comfyui_root = self.base / "comfyui"
        node_dir = self.base / "node"
        kj_dir = self.comfyui_root / "custom_nodes" / "ComfyUI-KJNodes"
        kj_dir.mkdir(parents=True, exist_ok=True)
        (kj_dir / "__init__.py").write_text("", encoding="utf-8")

        self.resolver = DependencyResolver(str(node_dir), str(self.comfyui_root))
        self.service = WorkflowDomainService(
            str(node_dir), dependency_provider=self.resolver.reasons_for
        )
        self.models = ModelLibraryService(str(node_dir), str(self.comfyui_root))
        self.registry = CustomNodeRegistryStore(str(node_dir))
        self._fake_nodes = _FakeNodes(self.comfyui_root)

    def tearDown(self) -> None:
        self._fake_nodes.cleanup()
        self._tmp.cleanup()

    # ── helpers ──────────────────────────────────────────────────────────

    def _create_workflow(self, name: str = "Test WF", compatible_models=None) -> dict:
        return self.service.create_workflow(name, compatible_models=compatible_models)

    def _create_version(self, workflow_id: str, prompt: dict | None = None) -> dict:
        return self.service.create_version_from_capture(
            workflow_id, make_capture(prompt if prompt is not None else loader_prompt())
        )

    def _set_mapping(self, version_id: str) -> None:
        entries, output_node_id = derive_mapping_candidates(
            make_capture(loader_prompt())
        )
        self.service.set_mapping(
            version_id,
            entries={role: e.to_dict() for role, e in entries.items()},
            output_node_id=output_node_id,
        )

    def _seed_model(self, content: bytes = b"contentA") -> None:
        path = self.comfyui_root / "models" / "checkpoints" / "krea_model.safetensors"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        self.models.rescan()

    def _seed_registry(self, installed_commit: str = "abc1234") -> None:
        self.registry.replace_records(
            [
                {
                    "name": "ComfyUI-KJNodes",
                    "install_path": str(
                        self.comfyui_root / "custom_nodes" / "ComfyUI-KJNodes"
                    ),
                    "repo_url": "",
                    "installed_commit": installed_commit,
                    "classes": ["SomeCustomClass"],
                }
            ]
        )

    def _inject_requirements(self, version_id: str, requirements: dict) -> dict:
        """Mutate the stored version's dependency_metadata (test-only)."""
        store = self.service.store
        raw = dict(store.get_version(version_id) or {})
        dep = dict(raw.get("dependency_metadata") or {})
        dep["custom_node_requirements"] = requirements
        raw["dependency_metadata"] = dep

        def _mutate(rows: list) -> None:
            for i, record in enumerate(rows):
                if record.get("workflow_version_id") == version_id:
                    rows[i] = raw
                    return

        store.versions.update(_mutate)
        return raw

    # ── 10. installed dependency → ready version ─────────────────────────

    def test_dependency_installed(self):
        self._seed_model()
        workflow = self._create_workflow()
        version = self._create_version(workflow["workflow_id"])
        version_id = version["workflow_version_id"]
        self._set_mapping(version_id)

        result = self.resolver.resolve_version(
            self.service.store.get_version(version_id) or {}
        )
        model_entries = result["models"]
        self.assertTrue(model_entries)
        self.assertEqual(model_entries[0]["filename"], "krea_model.safetensors")
        self.assertEqual(model_entries[0]["state"], "installed")
        self.assertTrue(model_entries[0]["installed"])
        self.assertTrue(result["summary"]["ready"])

        state = self.service.derive_version_state(version_id)
        self.assertEqual(state.status, "ready")
        self.assertEqual(state.reasons, [])
        self.assertTrue(state.runnable)

    # ── 11. missing dependency blocks runnable ───────────────────────────

    def test_dependency_missing(self):
        workflow = self._create_workflow()
        version = self._create_version(workflow["workflow_id"])
        version_id = version["workflow_version_id"]
        state = self.service.derive_version_state(version_id)
        self.assertEqual(state.status, "incomplete")
        self.assertFalse(state.runnable)
        self.assertTrue(
            any(
                "missing model 'krea_model.safetensors' (checkpoints)" in reason
                for reason in state.reasons
            )
        )

    # ── 12. wrong custom-node revision ───────────────────────────────────

    def test_wrong_custom_node_revision(self):
        self._seed_registry(installed_commit="abc1234")
        workflow = self._create_workflow()
        version = self._create_version(workflow["workflow_id"], custom_prompt())
        version_id = version["workflow_version_id"]
        raw = self._inject_requirements(
            version_id, {"SomeCustomClass": {"revision": "def5678"}}
        )

        result = self.resolver.resolve_version(raw)
        nodes = result["custom_nodes"]
        kj = [n for n in nodes if n["name"] == "ComfyUI-KJNodes"]
        self.assertTrue(kj)
        self.assertEqual(kj[0]["state"], "wrong_revision")
        self.assertEqual(kj[0]["installed_commit"], "abc1234")
        self.assertEqual(kj[0]["required_revision"], "def5678")
        reasons = self.resolver.reasons_for(raw)
        self.assertTrue(
            any("differs from required revision def5678" in reason for reason in reasons)
        )

    # ── 13. unknown (non-string) dependency ──────────────────────────────

    def test_unknown_dependency(self):
        version = {
            "workflow_version_id": "wv_unknown",
            "executable_prompt": {},
            "dependency_metadata": {"model_stack": {"checkpoint": [123]}, "node_classes": []},
        }
        refs = self.resolver.resolve_model_refs(version)
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["state"], "unknown")
        reasons = self.resolver.reasons_for(version)
        self.assertTrue(any("could not be identified" in reason for reason in reasons))

    # ── 14. custom node installed and missing ────────────────────────────

    def test_custom_node_installed_and_missing(self):
        self._seed_registry()
        version = {
            "workflow_version_id": "wv_cn",
            "executable_prompt": {},
            "dependency_metadata": {
                "model_stack": {},
                "node_classes": ["SomeCustomClass", "TotallyUnknownClass"],
            },
        }
        nodes = self.resolver.resolve_custom_nodes(version)
        by_name = {n["name"]: n for n in nodes}
        self.assertEqual(by_name["ComfyUI-KJNodes"]["state"], "installed")
        missing = [n for n in nodes if n["state"] == "missing"]
        self.assertTrue(missing)
        reasons = self.resolver.reasons_for(version)
        self.assertTrue(
            any(
                "required custom node 'TotallyUnknownClass' not installed" in reason
                for reason in reasons
            )
        )

    # ── 15. missing dep blocks runnable; seeding unblocks ────────────────

    def test_missing_dependency_blocks_runnable_and_resolution_unblocks(self):
        workflow = self._create_workflow()
        version = self._create_version(workflow["workflow_id"])
        version_id = version["workflow_version_id"]
        self._set_mapping(version_id)

        state = self.service.derive_version_state(version_id)
        self.assertEqual(state.status, "incomplete")
        self.assertFalse(state.runnable)
        self.assertTrue(any("missing model" in reason for reason in state.reasons))

        self._seed_model()
        state = self.service.derive_version_state(version_id)
        self.assertEqual(state.status, "ready")
        self.assertTrue(state.runnable)

        preset = self.service.create_preset(
            version_id,
            "Preset A",
            values={"model": "krea_model.safetensors"},
            model_choices={"model": "krea_model.safetensors"},
        )
        self.assertEqual(preset["state"]["status"], "ready")

    # ── 16. old version compatibility stays frozen ───────────────────────

    def test_old_version_compatibility_frozen(self):
        workflow = self._create_workflow(name="Compat", compatible_models=["A"])
        version = self._create_version(workflow["workflow_id"])
        version_id = version["workflow_version_id"]
        self._set_mapping(version_id)

        self.service.update_workflow(
            workflow["workflow_id"], {"compatible_models": ["B"]}
        )
        stored = self.service.store.get_version(version_id)
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(list(stored.get("compatible_models") or []), ["A"])

        with self.assertRaises(WorkflowPresetValidationError):
            self.service.create_preset(version_id, "Bad", model_choices={"model": "B"})
        preset = self.service.create_preset(version_id, "Good", model_choices={"model": "A"})
        self.assertTrue(preset["preset_id"].startswith("wpres_"))

    # ── 17. incompatible model cannot become a valid preset choice ───────

    def test_incompatible_model_cannot_become_valid_preset_choice(self):
        workflow = self._create_workflow(name="Compat2", compatible_models=["A"])
        version = self._create_version(workflow["workflow_id"])
        version_id = version["workflow_version_id"]
        self._set_mapping(version_id)

        with self.assertRaises(WorkflowPresetValidationError):
            self.service.create_preset(version_id, "Bad", model_choices={"model": "C"})
        preset = self.service.create_preset(
            version_id, "Good", model_choices={"model": "A"}
        )
        with self.assertRaises(WorkflowPresetValidationError):
            self.service.update_preset(
                preset["preset_id"], {"model_choices": {"model": "C"}}
            )

    # ── 18. no scan on state derivation; resolution reads records only ───

    def test_no_scan_on_state_derivation(self):
        self._seed_model()
        workflow = self._create_workflow()
        version = self._create_version(workflow["workflow_id"])
        version_id = version["workflow_version_id"]
        self._set_mapping(version_id)

        state = self.service.derive_version_state(version_id)
        self.assertEqual(state.status, "ready")

        before = list(self.models.store.list_records())
        for _ in range(3):
            self.service.derive_version_state(version_id)
        after = list(self.models.store.list_records())
        self.assertEqual(before, after)

        # Removing comfyui_root must not break resolution (records only).
        shutil.rmtree(str(self.comfyui_root))
        version_dict = self.service.store.get_version(version_id)
        self.assertIsNotNone(version_dict)
        assert version_dict is not None
        refs = self.resolver.resolve_model_refs(version_dict)
        self.assertTrue(refs)
        state = self.service.derive_version_state(version_id)
        self.assertIsNotNone(state)
        self.assertEqual(self.models.store.list_records(), before)

    # ── 19. corrupt model store degrades to "unknown", never raises ───────

    def test_resolve_version_survives_corrupt_model_store(self):
        workflow = self._create_workflow()
        version = self._create_version(workflow["workflow_id"])
        version_id = version["workflow_version_id"]
        version_dict = self.service.store.get_version(version_id) or {}
        store_path = self.base / "node" / ".studio_model_library.json"

        # Corrupt the model library store on disk (garbage bytes).
        store_path.write_bytes(b"\x00\x01garbage")

        result = self.resolver.resolve_version(version_dict)
        entries = result["models"]
        self.assertTrue(entries)
        self.assertEqual(entries[0]["state"], "unknown")
        self.assertEqual(entries[0]["reason"], "library store unreadable")
        self.assertFalse(result["summary"]["ready"])
        reasons = self.resolver.reasons_for(version_dict)
        self.assertTrue(reasons)

        # Restore a valid (empty) store: the same ref is now known-missing.
        # A known-missing model must never be converted to installed.
        store_path.write_text("[]", encoding="utf-8")
        result2 = self.resolver.resolve_version(version_dict)
        self.assertEqual(result2["models"][0]["state"], "missing")
        self.assertFalse(result2["summary"]["ready"])

    # ── 20. corrupt custom-node registry degrades to "missing" ────────────

    def test_resolve_version_survives_corrupt_custom_node_store(self):
        registry_path = self.base / "node" / ".studio_custom_nodes.json"
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_path.write_bytes(b"\x00\x01garbage")

        version = {
            "workflow_version_id": "wv_cn_corrupt",
            "executable_prompt": {},
            "dependency_metadata": {
                "model_stack": {},
                "node_classes": ["SomeCustomClass"],
            },
        }
        result = self.resolver.resolve_version(version)
        nodes = result["custom_nodes"]
        self.assertTrue(nodes)
        self.assertEqual(nodes[0]["state"], "missing")
        self.assertFalse(result["summary"]["ready"])


    # ── 21. custom-node rows group by pack, core merges ────────────────

    def test_custom_node_rows_group_by_pack(self):
        self._seed_registry()
        version = {
            "workflow_version_id": "wv_group",
            "executable_prompt": {},
            "dependency_metadata": {
                "model_stack": {},
                "node_classes": [
                    "CheckpointLoaderSimple",
                    "SaveImage",
                    "SomeCustomClass",
                    "SomeCustomClass",  # duplicate class collapses
                ],
            },
        }
        nodes = self.resolver.resolve_custom_nodes(version)
        core = [n for n in nodes if n["name"] == "ComfyUI core"]
        self.assertEqual(len(core), 1)
        self.assertEqual(
            sorted(core[0]["classes"]), ["CheckpointLoaderSimple", "SaveImage"]
        )
        kj = [n for n in nodes if n["name"] == "ComfyUI-KJNodes"]
        self.assertEqual(len(kj), 1)
        self.assertEqual(kj[0]["classes"], ["SomeCustomClass"])
        self.assertEqual(kj[0]["state"], "installed")

    # ── 21a-2. one physical install path is one row (donutnodes shape) ───

    def test_custom_node_duplicate_records_same_install_path_merge(self):
        """Distinct registry records that share an install path are one pack.

        The live donutnodes case: separate registry rows for the same physical
        directory carry different names/repos and metadata-derived cnr/aux ids.
        Grouping must key on the path, merge the classes, and retain the useful
        nonempty identity without inventing any.
        """
        install_path = str(self.comfyui_root / "custom_nodes" / "donutnodes")
        self.registry.replace_records(
            [
                {
                    "name": "donutnodes",
                    "install_path": install_path,
                    "repo_url": "https://github.com/DonutsDelivery/ComfyUI-DonutNodes",
                    "installed_commit": "abc1234",
                    "classes": ["DonutAlpha", "DonutBeta"],
                },
                {
                    "name": "DonutReferenceStudio",
                    "install_path": install_path,
                    "repo_url": "",
                    "installed_commit": "abc1234",
                    "classes": ["DonutGamma"],
                },
                {
                    "name": "donutnodes",
                    "install_path": install_path,
                    "repo_url": "",
                    "installed_commit": "abc1234",
                    "classes": ["DonutDelta"],
                },
            ]
        )
        version = {
            "workflow_version_id": "wv_donut_dupes",
            "executable_prompt": {},
            "dependency_metadata": {
                "model_stack": {},
                "node_classes": [
                    "DonutAlpha",
                    "DonutBeta",
                    "DonutGamma",
                    "DonutDelta",
                ],
                "custom_node_requirements": {
                    "DonutAlpha": {"cnr_id": "donutnodes"},
                    "DonutBeta": {"aux_id": "DonutsDelivery/ComfyUI-DonutNodes"},
                },
            },
        }
        nodes = self.resolver.resolve_custom_nodes(version)
        rows = [n for n in nodes if n.get("install_path")]
        self.assertEqual(len(rows), 1, "one physical install path is one pack")
        row = rows[0]
        self.assertEqual(row["name"], "donutnodes")
        self.assertEqual(row["state"], "installed")
        self.assertEqual(row["install_path"], install_path)
        self.assertEqual(row["cnr_id"], "donutnodes")
        self.assertEqual(row["aux_id"], "DonutsDelivery/ComfyUI-DonutNodes")
        self.assertEqual(
            row["repository_url"],
            "https://github.com/DonutsDelivery/ComfyUI-DonutNodes",
        )
        self.assertEqual(
            row["classes"],
            ["DonutAlpha", "DonutBeta", "DonutDelta", "DonutGamma"],
        )

    def test_custom_node_separate_install_paths_stay_separate(self):
        """A shared cnr_id never merges two genuinely different install paths."""
        path_a = str(self.comfyui_root / "custom_nodes" / "pack-a")
        path_b = str(self.comfyui_root / "custom_nodes" / "pack-b")
        self.registry.replace_records(
            [
                {
                    "name": "pack-a",
                    "install_path": path_a,
                    "repo_url": "",
                    "installed_commit": "abc1234",
                    "classes": ["PackAClass"],
                },
                {
                    "name": "pack-b",
                    "install_path": path_b,
                    "repo_url": "",
                    "installed_commit": "abc1234",
                    "classes": ["PackBClass"],
                },
            ]
        )
        version = {
            "workflow_version_id": "wv_separate_paths",
            "executable_prompt": {},
            "dependency_metadata": {
                "model_stack": {},
                "node_classes": ["PackAClass", "PackBClass"],
                "custom_node_requirements": {
                    "PackAClass": {"cnr_id": "shared-pack"},
                    "PackBClass": {"cnr_id": "shared-pack"},
                },
            },
        }
        nodes = self.resolver.resolve_custom_nodes(version)
        rows = sorted(
            (n for n in nodes if n.get("install_path")),
            key=lambda n: n["install_path"],
        )
        self.assertEqual(len(rows), 2, "different install paths are different packs")
        self.assertEqual({r["install_path"] for r in rows}, {path_a, path_b})
        self.assertEqual(
            {tuple(r["classes"]) for r in rows},
            {("PackAClass",), ("PackBClass",)},
        )
        self.assertTrue(all(r["cnr_id"] == "shared-pack" for r in rows))

    def test_custom_node_pack_state_degrades_conservatively(self):
        """A pack's merged state is its worst member: missing beats
        wrong_revision beats installed, and a path-less class joins the
        installed pack it identifies by cnr_id."""
        install_path = str(self.comfyui_root / "custom_nodes" / "mixed-pack")
        self.registry.replace_records(
            [
                {
                    "name": "MixedPack",
                    "install_path": install_path,
                    "repo_url": "",
                    "installed_commit": "abc1234",
                    "classes": ["MixedInstalled"],
                }
            ]
        )
        version = {
            "workflow_version_id": "wv_mixed_state",
            "executable_prompt": {},
            "dependency_metadata": {
                "model_stack": {},
                "node_classes": ["MixedInstalled", "MixedMissing"],
                "custom_node_requirements": {
                    "MixedInstalled": {"cnr_id": "mixed-pack", "revision": "def5678"},
                    "MixedMissing": {"cnr_id": "mixed-pack"},
                },
            },
        }
        nodes = self.resolver.resolve_custom_nodes(version)
        self.assertEqual(len(nodes), 1, "identity links the path-less class to the pack")
        row = nodes[0]
        self.assertEqual(row["state"], "missing", "missing is the most degraded state")
        self.assertEqual(row["install_path"], install_path)
        self.assertEqual(row["cnr_id"], "mixed-pack")
        self.assertEqual(row["classes"], ["MixedInstalled", "MixedMissing"])

    def test_custom_node_pack_state_wrong_revision_beats_installed(self):
        """A matching class never masks another class's revision mismatch."""
        install_path = str(self.comfyui_root / "custom_nodes" / "rev-pack")
        self.registry.replace_records(
            [
                {
                    "name": "RevPack",
                    "install_path": install_path,
                    "repo_url": "",
                    "installed_commit": "abc1234",
                    "classes": ["RevPackA"],
                },
                {
                    "name": "RevPack",
                    "install_path": install_path,
                    "repo_url": "",
                    "installed_commit": "abc1234",
                    "classes": ["RevPackB"],
                },
            ]
        )
        version = {
            "workflow_version_id": "wv_rev_merge",
            "executable_prompt": {},
            "dependency_metadata": {
                "model_stack": {},
                "node_classes": ["RevPackA", "RevPackB"],
                "custom_node_requirements": {
                    "RevPackA": {},
                    "RevPackB": {"revision": "def5678"},
                },
            },
        }
        nodes = self.resolver.resolve_custom_nodes(version)
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]["state"], "wrong_revision")
        self.assertEqual(nodes[0]["required_revision"], "def5678")
        self.assertEqual(nodes[0]["classes"], ["RevPackA", "RevPackB"])

    # ── 21b. captured CNR pack id propagates and groups by pack ──────────

    def test_custom_node_cnr_id_propagates_and_groups(self):
        version = {
            "workflow_version_id": "wv_cnr",
            "executable_prompt": {},
            "dependency_metadata": {
                "model_stack": {},
                "node_classes": [
                    "DonutLoaderA",
                    "DonutLoaderB",
                    "TotallyUnknownClass",
                ],
                "custom_node_requirements": {
                    "DonutLoaderA": {"cnr_id": "donutnodes"},
                    "DonutLoaderB": {"cnr_id": "donutnodes"},
                },
            },
        }
        nodes = self.resolver.resolve_custom_nodes(version)
        donut = [n for n in nodes if n.get("cnr_id") == "donutnodes"]
        self.assertEqual(len(donut), 1, "classes sharing a CNR id group into one row")
        self.assertEqual(donut[0]["state"], "missing")
        self.assertEqual(donut[0]["repository_url"], "")
        self.assertEqual(sorted(donut[0]["classes"]), ["DonutLoaderA", "DonutLoaderB"])
        self.assertEqual(donut[0]["name"], "donutnodes")
        unknown = [n for n in nodes if n["name"] == "TotallyUnknownClass"]
        self.assertEqual(len(unknown), 1)
        self.assertEqual(unknown[0]["cnr_id"], "")

    # ── 21c. stored graph supplies CNR id when requirements lack it ──────

    def test_custom_node_cnr_id_falls_back_to_stored_graph(self):
        """Older versions lack custom_node_requirements; their persisted UI
        graph cnr_id recovers the pack so classes sharing it group into one
        missing row (the six-Donut-classes live case)."""
        node_classes = [
            "DonutLoaderA",
            "DonutLoaderB",
            "TotallyUnknownClass",
        ]
        graphs = {
            "graph_json": {
                "nodes": [
                    {"id": 1, "type": "DonutLoaderA", "properties": {"cnr_id": "donutnodes"}},
                    {"id": 2, "type": "DonutLoaderB", "properties": {"cnr_id": "donutnodes"}},
                    {"id": 3, "type": "KSampler", "properties": {"cnr_id": "comfy-core"}},
                    {
                        "id": 4,
                        "type": "TotallyUnknownClass",
                        "properties": {},
                        "inputs": [{"name": "model", "link": None}],
                        "outputs": [{"name": "MODEL"}],
                    },
                ],
            },
            "static_graph": {
                "nodes": [
                    {"id": 1, "type": "DonutLoaderA", "properties": {"cnr_id": "donutnodes"}},
                    {"id": 2, "type": "DonutLoaderB", "properties": {"cnr_id": "donutnodes"}},
                ],
            },
        }
        for graph_key, graph in graphs.items():
            with self.subTest(graph_key=graph_key):
                version = {
                    "workflow_version_id": "wv_cnr_graph",
                    "executable_prompt": {},
                    graph_key: graph,
                    "dependency_metadata": {
                        "model_stack": {},
                        "node_classes": list(node_classes),
                    },
                }
                nodes = self.resolver.resolve_custom_nodes(version)
                donut = [n for n in nodes if n.get("cnr_id") == "donutnodes"]
                self.assertEqual(
                    len(donut), 1, "stored-graph cnr_id groups classes into one row"
                )
                self.assertEqual(donut[0]["state"], "missing")
                self.assertEqual(donut[0]["repository_url"], "")
                self.assertEqual(
                    sorted(donut[0]["classes"]), ["DonutLoaderA", "DonutLoaderB"]
                )
                unknown = [n for n in nodes if n["name"] == "TotallyUnknownClass"]
                self.assertEqual(len(unknown), 1)
                self.assertEqual(unknown[0]["cnr_id"], "")

    # ── 21c-2. nested stored-graph nodes resolve and group ───────────────

    @staticmethod
    def _nested_graph() -> dict:
        """Real nodes nested under definitions.subgraphs + extra.groupNodes."""
        return {
            "nodes": [],
            "definitions": {
                "subgraphs": [
                    {
                        "id": "sg",
                        "nodes": [
                            {
                                "id": 1,
                                "type": "NestedAlphaClass",
                                "properties": {"cnr_id": "nested-pack"},
                                "inputs": [{"name": "m", "link": None}],
                                "outputs": [{"name": "MODEL"}],
                            },
                            {
                                "id": 2,
                                "type": "NestedBetaClass",
                                "properties": {"cnr_id": "nested-pack"},
                                "inputs": [{"name": "m", "link": None}],
                                "outputs": [{"name": "MODEL"}],
                            },
                        ],
                    }
                ]
            },
            "extra": {
                "groupNodes": {
                    "g": {
                        "nodes": [
                            {
                                "id": 3,
                                "type": "NestedGammaClass",
                                "properties": {"aux_id": "owner/nested-gamma"},
                                "inputs": [{"name": "x", "link": None}],
                                "outputs": [{"name": "Y"}],
                            }
                        ]
                    }
                }
            },
        }

    @pytest.mark.fast_unit
    def test_stored_graph_nested_nodes_resolve_and_group(self):
        version = {
            "workflow_version_id": "wv_nested",
            "executable_prompt": {},
            "static_graph": self._nested_graph(),
            "dependency_metadata": {"model_stack": {}, "node_classes": []},
        }
        nodes = self.resolver.resolve_custom_nodes(version)
        pack = [n for n in nodes if n.get("cnr_id") == "nested-pack"]
        self.assertEqual(len(pack), 1, "nested classes sharing cnr_id group into one row")
        self.assertEqual(pack[0]["state"], "missing")
        self.assertEqual(
            sorted(pack[0]["classes"]), ["NestedAlphaClass", "NestedBetaClass"]
        )
        gamma = [n for n in nodes if n.get("aux_id") == "owner/nested-gamma"]
        self.assertEqual(len(gamma), 1, "nested aux-identified class surfaces")
        self.assertEqual(gamma[0]["classes"], ["NestedGammaClass"])

    @pytest.mark.fast_unit
    def test_stored_graph_nested_virtual_panel_excluded(self):
        nested_graph = {
            "nodes": [],
            "definitions": {
                "subgraphs": [
                    {
                        "id": "sg",
                        "nodes": [
                            {
                                "id": 1,
                                "type": "NestedPanel",
                                "properties": {},
                                "inputs": [],
                                "outputs": [],
                            }
                        ],
                    }
                ]
            },
        }
        version = {
            "workflow_version_id": "wv_nested_virtual",
            "executable_prompt": {},
            "static_graph": nested_graph,
            "dependency_metadata": {"model_stack": {}, "node_classes": []},
        }
        result = self.resolver.resolve_version(version)
        names = [n["name"] for n in result["custom_nodes"]]
        self.assertNotIn("NestedPanel", names)
        self.assertIn("NestedPanel", [u["name"] for u in result["unresolvable"]])
        self.assertEqual(result["summary"]["attention"], 0)

    @pytest.mark.fast_unit
    def test_stored_graph_nested_only_nodes_union_into_version(self):
        """A graph whose only real nodes live inside a subgraph still resolves."""
        nested_graph = {
            "nodes": [],
            "definitions": {
                "subgraphs": [
                    {
                        "id": "sg",
                        "nodes": [
                            {
                                "id": 1,
                                "type": "NestedOnlyClass",
                                "properties": {"cnr_id": "nested-only-pack"},
                                "inputs": [{"name": "x", "link": None}],
                                "outputs": [{"name": "Y"}],
                            }
                        ],
                    }
                ]
            },
        }
        version = {
            "workflow_version_id": "wv_nested_only",
            "executable_prompt": {},
            "graph_json": nested_graph,
            "dependency_metadata": {"model_stack": {}, "node_classes": []},
        }
        nodes = self.resolver.resolve_custom_nodes(version)
        row = [n for n in nodes if n.get("cnr_id") == "nested-only-pack"]
        self.assertEqual(len(row), 1)
        self.assertEqual(row[0]["classes"], ["NestedOnlyClass"])

    # ── 21d. captured aux_id propagates and groups by pack ───────────────

    def test_custom_node_aux_id_propagates_and_groups(self):
        version = {
            "workflow_version_id": "wv_aux",
            "executable_prompt": {},
            "dependency_metadata": {
                "model_stack": {},
                "node_classes": ["KJNodesA", "KJNodesB", "TotallyUnknownClass"],
                "custom_node_requirements": {
                    "KJNodesA": {"aux_id": "kijai/ComfyUI-KJNodes"},
                    "KJNodesB": {"aux_id": "kijai/ComfyUI-KJNodes"},
                },
            },
        }
        nodes = self.resolver.resolve_custom_nodes(version)
        aux = [n for n in nodes if n.get("aux_id") == "kijai/ComfyUI-KJNodes"]
        self.assertEqual(len(aux), 1, "classes sharing an aux_id group into one row")
        self.assertEqual(aux[0]["state"], "missing")
        self.assertEqual(aux[0]["repository_url"], "")
        self.assertEqual(sorted(aux[0]["classes"]), ["KJNodesA", "KJNodesB"])
        self.assertEqual(aux[0]["name"], "kijai/ComfyUI-KJNodes")
        unknown = [n for n in nodes if n["name"] == "TotallyUnknownClass"]
        self.assertEqual(len(unknown), 1)
        self.assertEqual(unknown[0]["aux_id"], "")

    # ── 21e. stored graph supplies aux_id when requirements lack it ──────

    def test_custom_node_aux_id_falls_back_to_stored_graph(self):
        version = {
            "workflow_version_id": "wv_aux_graph",
            "executable_prompt": {},
            "graph_json": {
                "nodes": [
                    {"id": 1, "type": "KJNodesA", "properties": {"aux_id": "kijai/ComfyUI-KJNodes"}},
                    {"id": 2, "type": "KJNodesB", "properties": {"aux_id": "kijai/ComfyUI-KJNodes"}},
                ],
            },
            "dependency_metadata": {
                "model_stack": {},
                "node_classes": ["KJNodesA", "KJNodesB"],
            },
        }
        nodes = self.resolver.resolve_custom_nodes(version)
        aux = [n for n in nodes if n.get("aux_id") == "kijai/ComfyUI-KJNodes"]
        self.assertEqual(len(aux), 1, "stored-graph aux_id groups classes into one row")
        self.assertEqual(sorted(aux[0]["classes"]), ["KJNodesA", "KJNodesB"])

    # ── 22. graph artifacts separate from missing, excluded from counts ──

    def test_graph_artifacts_unresolvable_not_missing(self):
        self._seed_registry()
        bad_uuid = "0324d3cd-a5a2-4bf0-9e02-a9f2aae29e77"
        bad_title = "Label (rgthree)"
        version = {
            "workflow_version_id": "wv_art",
            "executable_prompt": {},
            "dependency_metadata": {
                "model_stack": {},
                "node_classes": [
                    bad_uuid,
                    bad_title,
                    "SomeCustomClass",
                    "TotallyUnknownClass",
                ],
            },
        }
        result = self.resolver.resolve_version(version)
        names = [n["name"] for n in result["custom_nodes"]]
        self.assertNotIn(bad_uuid, names)
        self.assertNotIn(bad_title, names)
        unres = [u["name"] for u in result["unresolvable"]]
        self.assertEqual(sorted(unres), sorted([bad_uuid, bad_title]))
        missing = [n for n in result["custom_nodes"] if n["state"] == "missing"]
        self.assertEqual([n["name"] for n in missing], ["TotallyUnknownClass"])
        self.assertEqual(result["summary"]["attention"], 1)
        self.assertFalse(result["summary"]["ready"])
        reasons = self.resolver.reasons_for(version)
        self.assertFalse(
            any(bad_uuid in r or bad_title in r for r in reasons)
        )
        self.assertTrue(any("TotallyUnknownClass" in r for r in reasons))

    # ── 23. frontend-only virtual nodes are skipped, never "missing" ─────

    def test_virtual_reroute_note_workflow_nodes_skipped(self):
        version = {
            "workflow_version_id": "wv_virtual",
            "executable_prompt": {},
            "dependency_metadata": {
                "model_stack": {},
                "node_classes": ["Reroute", "Note", "WorkflowNode", "TotallyUnknownClass"],
            },
        }
        result = self.resolver.resolve_version(version)
        names = [n["name"] for n in result["custom_nodes"]]
        for virtual in ("Reroute", "Note", "WorkflowNode"):
            self.assertNotIn(virtual, names, virtual + " must not become a dependency")
        self.assertEqual([n["name"] for n in result["custom_nodes"]], ["TotallyUnknownClass"])
        self.assertEqual(result["summary"]["attention"], 1)

    # ── 24. stored UI-graph virtual panels: unresolvable, not missing ─────

    def test_graph_virtual_panels_unresolvable_not_missing(self):
        """The live Donut shape: real executable nodes keep their inputs/
        outputs; workflow-only panels have empty inputs/outputs and no pack
        identity. Only the real nodes may become missing packs."""
        version = {
            "workflow_version_id": "wv_virtual_panels",
            "executable_prompt": {
                "1": {"class_type": "DonutEditStudio", "inputs": {"image": ["9", 0]}},
                "2": {"class_type": "DonutReferenceStudio", "inputs": {"image": ["9", 0]}},
                "3": {"class_type": "DonutImageSave", "inputs": {"images": ["1", 0]}},
            },
            "graph_json": {
                "nodes": [
                    {"id": 1, "type": "DonutEditStudio", "inputs": [{"name": "image", "link": None}], "outputs": [{"name": "IMAGE"}]},
                    {"id": 2, "type": "DonutReferenceStudio", "inputs": [{"name": "image", "link": None}], "outputs": [{"name": "IMAGE"}]},
                    {"id": 3, "type": "DonutImageSave", "inputs": [{"name": "images", "link": None}], "outputs": []},
                    {"id": 4, "type": "DonutWorkflowPanel", "inputs": [], "outputs": []},
                    {"id": 5, "type": "DonutLatestPreview", "inputs": [], "outputs": []},
                    {"id": 6, "type": "DonutModelDownloads", "inputs": [], "outputs": []},
                ]
            },
            "dependency_metadata": {
                "model_stack": {},
                "node_classes": [
                    "DonutEditStudio", "DonutReferenceStudio", "DonutImageSave",
                    "DonutWorkflowPanel", "DonutLatestPreview", "DonutModelDownloads",
                ],
            },
        }
        result = self.resolver.resolve_version(version)
        missing = sorted(
            n["name"] for n in result["custom_nodes"] if n["state"] == "missing"
        )
        self.assertEqual(
            missing, ["DonutEditStudio", "DonutImageSave", "DonutReferenceStudio"]
        )
        virtual = {u["name"] for u in result["unresolvable"]}
        self.assertEqual(
            virtual,
            {"DonutWorkflowPanel", "DonutLatestPreview", "DonutModelDownloads"},
        )
        self.assertEqual(result["summary"]["attention"], 3)
        reasons = self.resolver.reasons_for(version)
        for name in ("DonutWorkflowPanel", "DonutLatestPreview", "DonutModelDownloads"):
            self.assertFalse(any(name in r for r in reasons), name + " inflated reasons")

    def test_graph_empty_input_node_in_executable_stays_missing(self):
        """Safety: a class that consumes an executable input stays a real
        dependency even when its graph node carries empty inputs/outputs."""
        version = {
            "workflow_version_id": "wv_empty_real",
            "executable_prompt": {
                "1": {"class_type": "DonutWidgetOnly", "inputs": {"model": ["2", 0]}}
            },
            "graph_json": {
                "nodes": [
                    {"id": 1, "type": "DonutWidgetOnly", "inputs": [], "outputs": []},
                ]
            },
            "dependency_metadata": {
                "model_stack": {},
                "node_classes": ["DonutWidgetOnly"],
            },
        }
        nodes = self.resolver.resolve_custom_nodes(version)
        self.assertEqual([n["state"] for n in nodes], ["missing"])
        self.assertEqual([n["name"] for n in nodes], ["DonutWidgetOnly"])
        self.assertEqual(self.resolver.unresolvable_classes(version), [])

    def test_graph_empty_input_node_with_identity_stays_missing(self):
        """Safety: an empty-input/outputs node carrying cnr_id/aux_id is a real
        pack dependency, never a virtual panel."""
        version = {
            "workflow_version_id": "wv_empty_identity",
            "executable_prompt": {},
            "graph_json": {
                "nodes": [
                    {
                        "id": 1,
                        "type": "DonutPanel",
                        "inputs": [],
                        "outputs": [],
                        "properties": {"cnr_id": "donutnodes"},
                    },
                ]
            },
            "dependency_metadata": {"model_stack": {}, "node_classes": ["DonutPanel"]},
        }
        nodes = self.resolver.resolve_custom_nodes(version)
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]["state"], "missing")
        self.assertEqual(nodes[0]["cnr_id"], "donutnodes")
        self.assertEqual(self.resolver.unresolvable_classes(version), [])

    def test_graph_real_shape_node_absent_from_executable_stays_missing(self):
        """Safety: a node with real inputs/outputs but absent from the
        executable prompt is still a dependency, not a virtual panel."""
        version = {
            "workflow_version_id": "wv_graph_real",
            "executable_prompt": {},
            "graph_json": {
                "nodes": [
                    {
                        "id": 1,
                        "type": "DonutHiddenLoader",
                        "inputs": [{"name": "model", "link": None}],
                        "outputs": [{"name": "MODEL"}],
                    },
                ]
            },
            "dependency_metadata": {
                "model_stack": {},
                "node_classes": ["DonutHiddenLoader"],
            },
        }
        nodes = self.resolver.resolve_custom_nodes(version)
        self.assertEqual([n["state"] for n in nodes], ["missing"])
        self.assertEqual(self.resolver.unresolvable_classes(version), [])

    # ── 24b. stored graph node types union into declared classes ─────────

    def test_custom_node_classes_union_from_stored_graph(self):
        """Old versions predate the capture-time graph union; their persisted
        UI graph node types must still surface as dependencies with identity."""
        self._seed_registry()
        version = {
            "workflow_version_id": "wv_graph_union",
            "executable_prompt": {"1": {"class_type": "SomeCustomClass", "inputs": {}}},
            "graph_json": {
                "nodes": [
                    {
                        "id": 1,
                        "type": "SomeCustomClass",
                        "inputs": [{"name": "x", "link": None}],
                        "outputs": [{"name": "Y"}],
                    },
                    {
                        "id": 2,
                        "type": "Krea2IdentityEdit",
                        "properties": {"cnr_id": "krea2_identity_edit"},
                        "inputs": [{"name": "image", "link": None}],
                        "outputs": [{"name": "IMAGE"}],
                    },
                    {
                        "id": 3,
                        "type": "BlehNode",
                        "properties": {"aux_id": "bleh/ComfyUI-bleh"},
                        "inputs": [{"name": "model", "link": None}],
                        "outputs": [{"name": "MODEL"}],
                    },
                ],
            },
            "dependency_metadata": {
                "model_stack": {},
                "node_classes": ["SomeCustomClass"],
            },
        }
        result = self.resolver.resolve_version(version)
        installed = [n for n in result["custom_nodes"] if n["state"] == "installed"]
        self.assertEqual(len(installed), 1)
        missing = [n for n in result["custom_nodes"] if n["state"] == "missing"]
        by_cnr = {n.get("cnr_id"): n for n in missing}
        by_aux = {n.get("aux_id"): n for n in missing}
        self.assertEqual(by_cnr["krea2_identity_edit"]["state"], "missing")
        self.assertEqual(by_aux["bleh/ComfyUI-bleh"]["state"], "missing")
        self.assertEqual(result["summary"]["attention"], 2)

    def test_stored_graph_virtual_classes_excluded_from_union(self):
        """The union must not turn a graph-only virtual panel into a fake
        missing pack; it stays in unresolvable and out of attention."""
        version = {
            "workflow_version_id": "wv_graph_union_virtual",
            "executable_prompt": {"1": {"class_type": "DonutImageSave", "inputs": {}}},
            "graph_json": {
                "nodes": [
                    {
                        "id": 1,
                        "type": "DonutImageSave",
                        "inputs": [{"name": "images", "link": None}],
                        "outputs": [],
                    },
                    {"id": 2, "type": "DonutWorkflowPanel", "inputs": [], "outputs": []},
                ],
            },
            "dependency_metadata": {
                "model_stack": {},
                "node_classes": ["DonutImageSave"],
            },
        }
        result = self.resolver.resolve_version(version)
        missing = [n["name"] for n in result["custom_nodes"] if n["state"] == "missing"]
        self.assertEqual(missing, ["DonutImageSave"])
        virtual = [u["name"] for u in result["unresolvable"]]
        self.assertEqual(virtual, ["DonutWorkflowPanel"])
        self.assertEqual(result["summary"]["attention"], 1)

    def test_synthetic_manager_mapped_missing_packs_group(self):
        """Several Manager-mapped missing packs (CNR / aux / shared-aux) each
        render one actionable row per pack identity."""
        version = {
            "workflow_version_id": "wv_six_packs",
            "executable_prompt": {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {}}},
            "graph_json": {
                "nodes": [
                    {
                        "id": 1,
                        "type": "CheckpointLoaderSimple",
                        "inputs": [],
                        "outputs": [{"name": "MODEL"}],
                    },
                    {
                        "id": 2,
                        "type": "Krea2IdentityEdit",
                        "properties": {"cnr_id": "krea2_identity_edit"},
                        "inputs": [{"name": "image", "link": None}],
                        "outputs": [{"name": "IMAGE"}],
                    },
                    {
                        "id": 3,
                        "type": "DerfuuNode",
                        "properties": {
                            "aux_id": "Derfuu/ComfyUI_Derfuu_ComfyUI_Modded_Nodes"
                        },
                        "inputs": [{"name": "image", "link": None}],
                        "outputs": [{"name": "IMAGE"}],
                    },
                    {
                        "id": 4,
                        "type": "ImpactSubpackNode",
                        "properties": {"cnr_id": "impact_subpack"},
                        "inputs": [{"name": "image", "link": None}],
                        "outputs": [{"name": "IMAGE"}],
                    },
                    {
                        "id": 5,
                        "type": "BlehNodeA",
                        "properties": {"aux_id": "bleh/ComfyUI-bleh"},
                        "inputs": [{"name": "x", "link": None}],
                        "outputs": [{"name": "Y"}],
                    },
                    {
                        "id": 6,
                        "type": "BlehNodeB",
                        "properties": {"aux_id": "bleh/ComfyUI-bleh"},
                        "inputs": [{"name": "x", "link": None}],
                        "outputs": [{"name": "Y"}],
                    },
                ],
            },
            "dependency_metadata": {
                "model_stack": {},
                "node_classes": ["CheckpointLoaderSimple"],
            },
        }
        result = self.resolver.resolve_version(version)
        missing = [n for n in result["custom_nodes"] if n["state"] == "missing"]
        self.assertEqual(len(missing), 4, "one row per pack identity")
        bleh = [n for n in missing if n.get("aux_id") == "bleh/ComfyUI-bleh"]
        self.assertEqual(len(bleh), 1)
        self.assertEqual(sorted(bleh[0]["classes"]), ["BlehNodeA", "BlehNodeB"])
        cnrs = {n.get("cnr_id") for n in missing}
        self.assertIn("krea2_identity_edit", cnrs)
        self.assertIn("impact_subpack", cnrs)
        auxes = {n.get("aux_id") for n in missing}
        self.assertIn("Derfuu/ComfyUI_Derfuu_ComfyUI_Modded_Nodes", auxes)
        self.assertEqual(result["summary"]["attention"], 4)

    # ── 25. stored graph widget metadata recovers model refs ─────────────

    def test_model_refs_recover_graph_widget_models(self):
        version = {
            "workflow_version_id": "wv_graph_model",
            "executable_prompt": {},
            "graph_json": {
                "nodes": [
                    {
                        "id": 4,
                        "type": "CheckpointLoaderSimple",
                        "inputs": [],
                        "outputs": [{"name": "MODEL"}],
                        "widgets_values_named": {"ckpt_name": "graph_model.safetensors"},
                    },
                ]
            },
            "dependency_metadata": {"model_stack": {}, "node_classes": []},
        }
        refs = self.resolver.resolve_model_refs(version)
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["role"], "checkpoint")
        self.assertEqual(refs[0]["filename"], "graph_model.safetensors")
        self.assertEqual(refs[0]["state"], "missing")

    # ── 26. role/folder aliases resolve to an installed record ───────────

    def test_model_ref_alias_role_matches_diffusion_models_record(self):
        path = (
            self.comfyui_root
            / "models"
            / "diffusion_models"
            / "alias_model.safetensors"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"alias-content")
        self.models.rescan()

        version = {
            "workflow_version_id": "wv_alias",
            "executable_prompt": {},
            "dependency_metadata": {
                "model_stack": {"unet": ["alias_model.safetensors"]},
                "node_classes": [],
            },
        }
        refs = self.resolver.resolve_model_refs(version)
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["state"], "installed")
        self.assertEqual(refs[0]["folder"], "diffusion_models")
        self.assertTrue(refs[0]["installed"])

    def test_model_ref_path_qualified_matches_record_basename(self):
        path = self.comfyui_root / "models" / "unet" / "nested_model.safetensors"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"nested-content")
        self.models.rescan()

        version = {
            "workflow_version_id": "wv_qref",
            "executable_prompt": {},
            "dependency_metadata": {
                "model_stack": {"unet": ["unet/nested_model.safetensors"]},
                "node_classes": [],
            },
        }
        refs = self.resolver.resolve_model_refs(version)
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["state"], "installed")

    # ── 27. executable no-op panels are excluded like graph virtuals ─────

    def test_virtual_panels_with_empty_executable_inputs_excluded(self):
        version = {
            "workflow_version_id": "wv_live_virtual",
            "executable_prompt": {
                "1": {"class_type": "DonutWorkflowPanel", "inputs": {}},
                "2": {"class_type": "DonutLatestPreview", "inputs": {}},
                "3": {"class_type": "DonutModelDownloads", "inputs": {}},
                "4": {"class_type": "DonutEditStudio", "inputs": {"model": ["5", 0]}},
            },
            "graph_json": {
                "nodes": [
                    {"id": 1, "type": "DonutWorkflowPanel", "inputs": [], "outputs": []},
                    {"id": 2, "type": "DonutLatestPreview", "inputs": [], "outputs": []},
                    {"id": 3, "type": "DonutModelDownloads", "inputs": [], "outputs": []},
                    {
                        "id": 4,
                        "type": "DonutEditStudio",
                        "inputs": [{"name": "model", "link": None}],
                        "outputs": [{"name": "MODEL"}],
                    },
                ]
            },
            "dependency_metadata": {
                "model_stack": {},
                "node_classes": [
                    "DonutWorkflowPanel",
                    "DonutLatestPreview",
                    "DonutModelDownloads",
                    "DonutEditStudio",
                ],
            },
        }
        result = self.resolver.resolve_version(version)
        names = [n["name"] for n in result["custom_nodes"]]
        unres = {u["name"] for u in result["unresolvable"]}
        for panel in ("DonutWorkflowPanel", "DonutLatestPreview", "DonutModelDownloads"):
            self.assertNotIn(panel, names, panel + " must not become a dependency")
            self.assertNotIn(panel, unres, panel + " must not be reported as a dep")
        self.assertIn("DonutEditStudio", names)

    # ── remote inventory reconciliation ──────────────────────────────────
    #
    # The resolver answers "what does the Modal app have" by joining the
    # workflow's requirements against one `get_volume_status` payload. Models
    # join on basename+folder; custom-node packs join on the directory name the
    # volume preserves from the local pack. Remote evidence can promote a row
    # to installed but never newly demote one: the custom-node volume is a
    # full-replace mirror of local custom_nodes/, so absence proves little.

    def _remote(self, models=None, custom_nodes=None):
        payload = {}
        if models is not None:
            payload["models"] = models
        if custom_nodes is not None:
            payload["custom_nodes"] = custom_nodes
        return payload

    def _remote_model(self, filename, folder="checkpoints", size=1024):
        return {"name": filename, "folder": folder, "size": size}

    def _version_with_model(self, filename="krea_model.safetensors"):
        workflow = self._create_workflow()
        prompt = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": filename}},
            "2": {"class_type": "SaveImage", "inputs": {}},
        }
        version = self._create_version(workflow["workflow_id"], prompt)
        return self.service.store.get_version(version["workflow_version_id"]) or {}

    def test_remote_model_present_upgrades_locally_missing(self):
        # The regression this whole change exists for: the model is on the
        # Modal volume and absent from the PC, so the local disk check says
        # "missing" and the report wrongly blocks the workflow.
        version = self._version_with_model()

        local_only = self.resolver.resolve_version(version)
        self.assertEqual(local_only["models"][0]["state"], "missing")
        self.assertFalse(local_only["summary"]["ready"])

        remote = self.resolver.resolve_version(
            version, remote=self._remote(models=[self._remote_model("krea_model.safetensors")])
        )
        row = remote["models"][0]
        self.assertEqual(row["state"], "installed")
        self.assertTrue(row["installed"])
        self.assertTrue(row["remote_available"])
        self.assertEqual(row["remote_model"]["size"], 1024)
        self.assertTrue(remote["summary"]["ready"])
        self.assertEqual(remote["summary"]["attention"], 0)

    def test_remote_model_absent_leaves_row_missing(self):
        version = self._version_with_model("absent_everywhere.safetensors")

        remote = self.resolver.resolve_version(
            version, remote=self._remote(models=[self._remote_model("something_else.safetensors")])
        )
        row = remote["models"][0]
        self.assertEqual(row["state"], "missing")
        self.assertNotIn("remote_model", row)
        self.assertFalse(remote["summary"]["ready"])

    def test_remote_model_zero_size_does_not_install(self):
        # A zero-byte volume entry is a placeholder, exactly like a zero-byte
        # local file is; it must not read as installed.
        version = self._version_with_model()

        remote = self.resolver.resolve_version(
            version,
            remote=self._remote(models=[self._remote_model("krea_model.safetensors", size=0)]),
        )
        row = remote["models"][0]
        self.assertEqual(row["state"], "missing")
        self.assertFalse(row["remote_available"])
        self.assertEqual(row["remote_model"]["size"], 0)
        self.assertFalse(remote["summary"]["ready"])

    def test_remote_model_matches_through_role_folder_alias(self):
        # A ref stored folder-qualified resolves against the alias folder the
        # volume actually uses, so unet/diffusion_models are one identity.
        version = self._version_with_model("weights/krea_model.safetensors")

        remote = self.resolver.resolve_version(
            version,
            remote=self._remote(
                models=[self._remote_model("krea_model.safetensors", folder="diffusion_models")]
            ),
        )
        self.assertEqual(remote["models"][0]["state"], "installed")
        self.assertEqual(
            remote["models"][0]["remote_model"]["folder"], "diffusion_models"
        )

    def test_remote_pack_installs_classes_with_no_local_record(self):
        # The pack is on the volume and was never installed locally, so there is
        # no local registry record at all. Matching the captured pack identity
        # against the volume directory name is what makes "pack present implies
        # its classes are present" work.
        workflow = self._create_workflow()
        version = self._create_version(workflow["workflow_id"], custom_prompt())
        version_id = version["workflow_version_id"]
        raw = self._inject_requirements(
            version_id, {"SomeCustomClass": {"cnr_id": "comfyui-kjnodes"}}
        )

        self.assertEqual(
            [n["state"] for n in self.resolver.resolve_version(raw)["custom_nodes"]
             if n["name"] != "ComfyUI core"],
            ["missing"],
        )

        remote = self.resolver.resolve_version(
            raw,
            remote=self._remote(
                models=[self._remote_model("krea_model.safetensors")],
                custom_nodes=["ComfyUI-KJNodes"],
            ),
        )
        kj = [n for n in remote["custom_nodes"] if n["name"] == "comfyui-kjnodes"]
        self.assertTrue(kj)
        self.assertEqual(kj[0]["state"], "installed")
        self.assertTrue(remote["summary"]["ready"])

    def test_remote_pack_absent_never_demotes_an_installed_pack(self):
        # Absence from the volume is weak evidence (the volume mirrors local
        # custom_nodes/ wholesale), so it must not invent a missing row.
        self._seed_registry()
        workflow = self._create_workflow()
        version = self._create_version(workflow["workflow_id"], custom_prompt())
        raw = self.service.store.get_version(version["workflow_version_id"]) or {}

        remote = self.resolver.resolve_version(
            raw, remote=self._remote(custom_nodes=["SomeOtherPack"])
        )
        kj = [n for n in remote["custom_nodes"] if n["name"] == "ComfyUI-KJNodes"]
        self.assertTrue(kj)
        self.assertEqual(kj[0]["state"], "installed")

    def test_remote_clears_wrong_version_when_the_model_is_on_the_volume(self):
        # The volume listing carries no hash, so remote truth cannot verify a
        # revision; a present model is reported installed and the stale
        # required_hash is dropped rather than left contradicting the state.
        self._seed_model()
        workflow = self._create_workflow()
        version = self._create_version(workflow["workflow_id"])
        version_id = version["workflow_version_id"]
        store = self.service.store
        raw = dict(store.get_version(version_id) or {})
        dep = dict(raw.get("dependency_metadata") or {})
        dep["required_models"] = {"krea_model.safetensors": "deadbeef"}
        raw["dependency_metadata"] = dep

        def _mutate(rows: list) -> None:
            for i, record in enumerate(rows):
                if record.get("workflow_version_id") == version_id:
                    rows[i] = raw
                    return

        store.versions.update(_mutate)

        self.assertEqual(
            self.resolver.resolve_version(raw)["models"][0]["state"], "wrong_version"
        )

        remote = self.resolver.resolve_version(
            raw, remote=self._remote(models=[self._remote_model("krea_model.safetensors")])
        )
        row = remote["models"][0]
        self.assertEqual(row["state"], "installed")
        self.assertIsNone(row["required_hash"])

    def test_remote_none_is_byte_for_byte_unchanged(self):
        # remote=None must reproduce the local-only report exactly, so every
        # remote-unavailable path (Modal down, fetch failure) is unchanged.
        self._seed_model()
        version = self._version_with_model()

        without = self.resolver.resolve_version(version)
        explicit_none = self.resolver.resolve_version(version, remote=None)
        self.assertEqual(without, explicit_none)
        self.assertNotIn("remote_model", without["models"][0])
        self.assertNotIn("remote_available", without["models"][0])

    def test_malformed_remote_payload_degrades_to_local_truth(self):
        self._seed_model()
        version = self._version_with_model()

        for junk in [{}, {"models": "not-a-list"}, {"models": [None, 7]}, "garbage", 42]:
            remote = self.resolver.resolve_version(version, remote=junk)
            self.assertEqual(remote["models"][0]["state"], "installed", junk)
            self.assertNotIn("remote_model", remote["models"][0], junk)

    # ── nonessential (no live reference) dependencies ────────────────────

    def _version_with_bypassed_lora(self) -> dict:
        # Models reachable only from a bypassed node are off the critical path.
        # The stack is pre-seeded with them, as pre-fix captures recorded, and
        # the graph keeps them with mode=4 so the resolver must classify them.
        version = {
            "workflow_version_id": "wv_lora",
            "executable_prompt": {
                "1": {
                    "class_type": "CheckpointLoaderSimple",
                    "inputs": {"ckpt_name": "base.safetensors"},
                },
            },
            "graph_json": {
                "id": "g",
                "nodes": [
                    {
                        "id": 1,
                        "type": "CheckpointLoaderSimple",
                        "mode": 0,
                        "widgets_values": ["base.safetensors"],
                    },
                    {
                        "id": 2,
                        "type": "SeedVR2LoadVAEModel",
                        "mode": 4,
                        "widgets_values": ["ema_vae_fp16.safetensors"],
                    },
                    {
                        "id": 3,
                        "type": "LoraLoader",
                        "mode": 2,
                        "widgets_values": ["muted.safetensors"],
                    },
                ],
            },
            "dependency_metadata": {
                "model_stack": {
                    "checkpoint": ["base.safetensors"],
                    "model": [
                        "ema_vae_fp16.safetensors",
                        "muted.safetensors",
                    ],
                },
                "node_classes": [],
            },
        }
        return version

    def test_bypassed_or_muted_node_models_are_nonessential(self):
        result = self.resolver.resolve_version(self._version_with_bypassed_lora())
        rows = {m["filename"]: m for m in result["models"]}

        self.assertTrue(rows["ema_vae_fp16.safetensors"]["nonessential"])
        self.assertTrue(rows["muted.safetensors"]["nonessential"])
        # The node ComfyUI will actually run keeps its model essential.
        self.assertNotIn("nonessential", rows["base.safetensors"])

    def test_nonessential_missing_does_not_block_readiness(self):
        version = self._version_with_bypassed_lora()
        result = self.resolver.resolve_version(version)

        # All three are absent everywhere, but only the live node's model is
        # counted: the two disabled ones are reported and never block.
        missing = [m for m in result["models"] if m["state"] == "missing"]
        self.assertEqual(len(missing), 3)
        essential = [m for m in missing if not m.get("nonessential")]
        self.assertEqual([m["filename"] for m in essential], ["base.safetensors"])
        self.assertEqual(result["summary"]["missing"], 1)
        self.assertEqual(result["summary"]["attention"], 1)
        self.assertFalse(result["summary"]["ready"])

        # Drop the live reference and the version is ready: the two disabled
        # models were never what stood in the way.
        version["dependency_metadata"]["model_stack"]["checkpoint"] = []
        version["executable_prompt"] = {}
        ready = self.resolver.resolve_version(version)
        self.assertEqual(ready["summary"]["missing"], 0)
        self.assertEqual(ready["summary"]["attention"], 0)
        self.assertTrue(ready["summary"]["ready"])

    def test_nonessential_models_emit_no_blocking_reason(self):
        version = self._version_with_bypassed_lora()

        reasons = self.resolver.reasons_for(version, remote={})

        # Only the active node's model blocks; the disabled pair is silent.
        self.assertTrue(reasons)
        self.assertTrue(all("base.safetensors" in r for r in reasons))
        self.assertFalse(any("ema_vae" in r or "muted.safetensors" in r for r in reasons))

    def test_active_model_named_only_by_a_note_stays_a_dependency(self):
        # A MarkdownNote that merely mentions a filename is prose, not a model
        # reference: it must not create a dependency of its own.
        version = {
            "workflow_version_id": "wv_note",
            "executable_prompt": {},
            "graph_json": {
                "id": "g",
                "nodes": [
                    {
                        "id": 1,
                        "type": "MarkdownNote",
                        "mode": 0,
                        "widgets_values": [
                            "use the controlnet "
                            "Z-Image-Turbo-Fun-Controlnet-Union-2.1-2602-8steps.safetensors"
                        ],
                    }
                ],
            },
            "dependency_metadata": {"model_stack": {}, "node_classes": []},
        }
        result = self.resolver.resolve_version(version)
        names = [m["filename"] for m in result["models"]]
        self.assertNotIn(
            "Z-Image-Turbo-Fun-Controlnet-Union-2.1-2602-8steps.safetensors", names
        )

    # ── user-declared overrides ──────────────────────────────────────────

    def test_user_override_marks_a_live_model_nonessential(self):
        # Detection cannot see this one: a live node names it. Only an explicit
        # override makes it advisory, and it must win over detection.
        version = self._version_with_bypassed_lora()
        version["workflow_id"] = "wf_override"
        live = "base.safetensors"
        result = self.resolver.resolve_version(version, remote={})
        row = [m for m in result["models"] if m["filename"] == live][0]
        self.assertNotIn("nonessential", row)
        self.assertFalse(result["summary"]["ready"])

        self.resolver.overrides.set_keys("wf_override", {f"checkpoint|{live}"})
        try:
            marked = self.resolver.resolve_version(version, remote={})
            row = [m for m in marked["models"] if m["filename"] == live][0]
            self.assertTrue(row["nonessential"])
            self.assertEqual(row["nonessential_source"], "user")
            self.assertTrue(marked["summary"]["ready"])
            # A deliberate override must also stop blocking the run gate.
            self.assertEqual(self.resolver.reasons_for(version, remote={}), [])
        finally:
            self.resolver.overrides.set_keys("wf_override", set())

    def test_override_is_scoped_to_its_workflow(self):
        version = self._version_with_bypassed_lora()
        version["workflow_id"] = "wf_a"
        self.resolver.overrides.set_keys("wf_b", {"checkpoint|base.safetensors"})
        try:
            result = self.resolver.resolve_version(version, remote={})
            self.assertFalse(result["summary"]["ready"])
        finally:
            self.resolver.overrides.set_keys("wf_b", set())

    def test_clearing_the_last_override_removes_the_record(self):
        self.resolver.overrides.set_keys("wf_c", {"checkpoint|base.safetensors"})
        self.assertEqual(self.resolver.overrides.keys_for("wf_c"), {"checkpoint|base.safetensors"})
        self.resolver.overrides.set_keys("wf_c", set())
        self.assertEqual(self.resolver.overrides.keys_for("wf_c"), set())

    def test_unreadable_override_store_degrades_to_no_overrides(self):
        store = self.resolver.overrides
        store.store.write_atomic([{"workflow_id": "wf_x", "nonessential": ["a|b"]}])
        store.store.path.write_bytes(b"{ not json")
        # Must not raise into resolution, and must not invent overrides.
        self.assertEqual(store.keys_for("wf_x"), set())
        version = self._version_with_bypassed_lora()
        version["workflow_id"] = "wf_x"
        self.assertIn("summary", self.resolver.resolve_version(version, remote={}))

    def test_user_override_applies_to_a_model_that_has_a_library_record(self):
        # Regression: the flag used to be stamped on only the "no library record
        # at all" branch, so overriding a model the library already knew about —
        # the common case — silently did nothing.
        self._seed_model()  # krea_model.safetensors is a known library record
        workflow = self._create_workflow()
        version = self._create_version(workflow["workflow_id"])
        version_id = version["workflow_version_id"]
        self._set_mapping(version_id)
        raw = self.service.store.get_version(version_id) or {}
        raw["workflow_id"] = "wf_recorded"
        live = "krea_model.safetensors"
        key = f"checkpoint|{live}"

        before = self.resolver.resolve_version(raw, remote={})
        row = [m for m in before["models"] if m["filename"] == live][0]
        self.assertEqual(row["state"], "installed")
        self.assertNotIn("nonessential", row)

        self.resolver.overrides.set_keys("wf_recorded", {key})
        try:
            after = self.resolver.resolve_version(raw, remote={})
            row = [m for m in after["models"] if m["filename"] == live][0]
            self.assertTrue(row["nonessential"], "override must survive a library record")
            self.assertEqual(row["nonessential_source"], "user")
        finally:
            self.resolver.overrides.set_keys("wf_recorded", set())

    def test_override_reaches_every_resolution_branch(self):
        # Each branch of resolve_model_refs (unknown / unreadable / installed /
        # known-but-absent / unknown-record) must carry the flag.
        self._seed_model()
        version = self._version_with_model("branch_probe.safetensors")
        version["workflow_id"] = "wf_branches"
        self.resolver.overrides.set_keys("wf_branches", {"checkpoint|branch_probe.safetensors"})
        try:
            row = [
                m for m in self.resolver.resolve_version(version, remote={})["models"]
                if m["filename"] == "branch_probe.safetensors"
            ][0]
            self.assertTrue(row["nonessential"])
            self.assertEqual(row["nonessential_source"], "user")
        finally:
            self.resolver.overrides.set_keys("wf_branches", set())

    def test_unresolvable_classes_are_untouched_by_remote(self):
        # A graph artifact can never be a pack, so a remote inventory must not
        # promote it into an installed dependency or clear it from the skip list.
        version = {
            "workflow_version_id": "wv_artifact",
            "executable_prompt": {},
            "graph_json": {
                "id": "g",
                "nodes": [
                    {"id": 1, "type": "DonutLatestPreview", "inputs": [], "outputs": []},
                ],
            },
            "dependency_metadata": {"model_stack": {}, "node_classes": ["DonutLatestPreview"]},
        }
        remote = self.resolver.resolve_version(
            version, remote=self._remote(custom_nodes=["DonutLatestPreview"])
        )
        self.assertEqual(remote["custom_nodes"], [])
        self.assertEqual([u["name"] for u in remote["unresolvable"]], ["DonutLatestPreview"])

    # ── version state and the report must agree ──────────────────────────

    def test_reasons_read_the_shared_inventory_snapshot(self):
        # The version card derives its state through reasons_for, not through
        # resolve_version. If it re-derived local-only truth the card would
        # say "Incomplete" directly above a report that says "Ready".
        workflow = self._create_workflow()
        version = self._create_version(workflow["workflow_id"])
        version_id = version["workflow_version_id"]
        self._set_mapping(version_id)
        raw = self.service.store.get_version(version_id) or {}

        self.assertTrue(
            any("missing model 'krea_model.safetensors'" in r for r in self.resolver.reasons_for(raw))
        )
        self.assertFalse(self.service.derive_version_state(version_id).runnable)

        payload = self._remote(models=[self._remote_model("krea_model.safetensors")])
        try:
            remote_inventory._fetch = _static_fetch(payload)
            asyncio.run(remote_inventory.get_inventory())

            # No explicit `remote=` anywhere: the shared snapshot is the input.
            self.assertEqual(self.resolver.reasons_for(raw), [])
            state = self.service.derive_version_state(version_id)
            self.assertTrue(state.runnable)
            self.assertEqual(state.status, "ready")

            # And the two surfaces now report the same thing.
            report = self.resolver.resolve_version(raw)
            self.assertEqual(report["summary"]["ready"], state.status == "ready")
        finally:
            remote_inventory._fetch = remote_inventory._default_fetch
            remote_inventory.invalidate()

    def test_reasons_can_be_forced_local_only(self):
        # remote={} opts out of the shared snapshot, so an explicit local-only
        # answer stays available for callers that want PC truth.
        workflow = self._create_workflow()
        version = self._create_version(workflow["workflow_id"])
        version_id = version["workflow_version_id"]
        self._set_mapping(version_id)
        raw = self.service.store.get_version(version_id) or {}

        payload = self._remote(models=[self._remote_model("krea_model.safetensors")])
        try:
            remote_inventory._fetch = _static_fetch(payload)
            asyncio.run(remote_inventory.get_inventory())
            self.assertEqual(self.resolver.reasons_for(raw), [])
            self.assertTrue(
                any(
                    "missing model 'krea_model.safetensors'" in r
                    for r in self.resolver.reasons_for(raw, remote={})
                )
            )
        finally:
            remote_inventory._fetch = remote_inventory._default_fetch
            remote_inventory.invalidate()


def _static_fetch(payload):
    async def _fetch():
        return payload

    return _fetch


if __name__ == "__main__":
    unittest.main()
