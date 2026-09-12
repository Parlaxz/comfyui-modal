"""Tests for the workflow dependency resolver (dependency_resolver.py).

The resolver reads the persisted stores only.  Because the real ComfyUI
``nodes`` module is unavailable in the test environment, a fake ``nodes``
module is registered in ``sys.modules`` so core classes (e.g.
``CheckpointLoaderSimple``) resolve to ComfyUI core while
``SomeCustomClass`` resolves to a custom-node directory on disk.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path

from tests import _test_env  # noqa: F401  (hide real ComfyUI from sys.path)

from custom_node_registry import CustomNodeRegistryStore
from dependency_resolver import DependencyResolver
from model_library import ModelLibraryService
from studio_domain import (
    WorkflowDomainService,
    WorkflowPresetValidationError,
    derive_mapping_candidates,
)


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


if __name__ == "__main__":
    unittest.main()
