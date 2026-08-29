"""Focused source-root and duplicate-publication contract tests."""

from __future__ import annotations

import os
import io
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import comfyapp
from comfymodal_runtime import modal_app
from comfymodal_runtime.deployment_spec import build_deployment_identity
from comfymodal_runtime import publication_policy
from tools.publish_custom_nodes_volume import (
    _build_custom_nodes_archive,
    _resolve_custom_nodes_root as resolve_volume_root,
)


class SourceIdentityPublicationTests(unittest.TestCase):
    def test_default_root_is_parent_custom_nodes_for_all_publishers(self):
        repo_root = Path(__file__).resolve().parents[1]
        expected = repo_root.parent.resolve()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("COMFYMODAL_LOCAL_CUSTOM_NODES", None)
            self.assertEqual(Path(comfyapp._resolve_local_custom_nodes_root()), expected)
            self.assertEqual(modal_app._local_custom_nodes_root(), expected)
            self.assertEqual(Path(resolve_volume_root()), expected)
            self.assertEqual(
                Path(publication_policy.resolve_custom_nodes_root(repo_root)),
                expected,
            )

    def test_explicit_override_is_shared_and_not_replaced_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "staged-custom-nodes"
            root.mkdir()
            for name in ("node-a", "node-b", "node-c"):
                (root / name).mkdir()
                (root / name / "__init__.py").write_text("", encoding="utf-8")
            with patch.dict(os.environ, {"COMFYMODAL_LOCAL_CUSTOM_NODES": str(root)}):
                self.assertEqual(
                    publication_policy.resolve_custom_nodes_root(Path(tmp) / "plugin"),
                    str(root.resolve()),
                )

    def test_ambiguous_default_candidates_fail_clearly(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            candidates = []
            for index in (1, 2):
                candidate = base / f"custom-nodes-{index}"
                candidate.mkdir()
                for name in ("node-a", "node-b", "node-c"):
                    (candidate / name).mkdir()
                    (candidate / name / "__init__.py").write_text("", encoding="utf-8")
                candidates.append(candidate)
            with self.assertRaisesRegex(RuntimeError, "ambiguous custom-nodes source root"):
                publication_policy.resolve_custom_nodes_root(
                    base / "plugin",
                    fallback_roots=(candidates[0], candidates[1]),
                )

    def test_duplicate_worktrees_are_absent_from_archive_and_source_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "comfyui-modal").mkdir()
            (root / "comfyui-modal" / "source.py").write_text("canonical", encoding="utf-8")
            duplicate_names = (
                "comfyui-modal-p4-r1-reconcile",
                "comfyui-modal-r41.disabled",
                "comfyui-modal-r42",
                "golden-p3-comfyui-modal",
                "golden-p4-8-deploy",
            )
            for name in duplicate_names:
                duplicate = root / name
                (duplicate / "comfymodal_runtime").mkdir(parents=True)
                (duplicate / "comfyapp.py").write_text("duplicate", encoding="utf-8")
                (duplicate / "comfymodal_runtime" / "modal_app.py").write_text(
                    "duplicate", encoding="utf-8"
                )

            allowed = publication_policy.iter_syncable_custom_node_dirs(root)
            self.assertEqual(allowed, ["comfyui-modal"])
            archive = _build_custom_nodes_archive(str(root))
            with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
                members = {member.name.split("/", 1)[0] for member in tar.getmembers()}
            self.assertEqual(members, {"comfyui-modal"})

            runtime_root = root / "runtime"
            runtime_root.mkdir()
            identity = build_deployment_identity(runtime_root, custom_node_paths=[root])
            identity_paths = {path.replace("\\", "/") for path in identity.file_hashes}
            self.assertIn("custom_node_root_0/comfyui-modal/source.py", identity_paths)
            for name in duplicate_names:
                self.assertFalse(
                    any(path.startswith(f"custom_node_root_0/{name}/") for path in identity_paths)
                )
            before = identity.combined_hash
            (root / duplicate_names[0] / "new_source.py").write_text(
                "changed duplicate", encoding="utf-8"
            )
            self.assertEqual(
                before,
                build_deployment_identity(runtime_root, custom_node_paths=[root]).combined_hash,
            )


if __name__ == "__main__":
    unittest.main()
