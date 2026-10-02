"""Focused source-root and duplicate-publication contract tests."""

from __future__ import annotations

import os
import io
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import comfyapp
from comfymodal_runtime import modal_app
from comfymodal_runtime.deployment_spec import build_deployment_identity
from comfymodal_runtime import publication_policy
from tools.publish_custom_nodes_volume import (
    _build_custom_nodes_archive,
    _resolve_custom_nodes_root as resolve_volume_root,
)


class SourceIdentityPublicationTests(unittest.TestCase):
    @staticmethod
    def _archive_with_node() -> bytes:
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode="w:gz") as tar:
            payload = b"NODE = True\n"
            member = tarfile.TarInfo("node-a/__init__.py")
            member.size = len(payload)
            tar.addfile(member, io.BytesIO(payload))
        return archive.getvalue()

    def test_sync_fails_closed_before_record_write_or_commit_on_generation_failure(self):
        secret = "custom-node generation failed token=modal-token-secret"
        credential = "modal-token-secret"
        with tempfile.TemporaryDirectory() as tmp:
            record_writer = patch.object(comfyapp, "_write_custom_nodes_generation_record_no_commit")
            volume = Mock()
            with patch.object(comfyapp, "CUSTOM_NODES_PATH", tmp), \
                 patch.object(comfyapp, "custom_nodes_vol", volume), \
                 patch.object(
                     comfyapp,
                     "custom_node_source_generation",
                     side_effect=RuntimeError(secret),
                 ), record_writer as mock_writer:
                result = comfyapp.sync_custom_nodes_to_volume.local(
                    self._archive_with_node()
                )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["comfyapp_version"], comfyapp.COMFYAPP_VERSION)
        self.assertIn("generation_computation_failed", result["error"])
        self.assertIn("custom_node_source_generation raised RuntimeError:", result["error"])
        self.assertIn("custom-node generation failed", result["generation_failure_reason"])
        self.assertIn(result["generation_failure_reason"], result["error"])
        self.assertNotIn(secret, result["error"])
        self.assertNotIn(credential, result["error"])
        self.assertNotIn(credential, result["generation_failure_reason"])
        self.assertLessEqual(len(result["generation_failure_reason"]), 320)
        mock_writer.assert_not_called()
        volume.commit.assert_not_called()

    def test_sync_fails_closed_before_record_write_or_commit_on_empty_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            volume = Mock()
            with patch.object(comfyapp, "CUSTOM_NODES_PATH", tmp), \
                 patch.object(comfyapp, "custom_nodes_vol", volume), \
                 patch.object(comfyapp, "custom_node_source_generation", return_value=""), \
                 patch.object(
                     comfyapp,
                     "_write_custom_nodes_generation_record_no_commit",
                 ) as mock_writer:
                result = comfyapp.sync_custom_nodes_to_volume.local(
                    self._archive_with_node()
                )

        self.assertEqual(result["status"], "error")
        self.assertIn("generation_computation_failed", result["error"])
        self.assertIn("returned empty content_generation", result["error"])
        mock_writer.assert_not_called()
        volume.commit.assert_not_called()

    def test_sync_success_returns_explicit_content_generation_with_one_commit(self):
        generation = "canonical-content-generation"
        with tempfile.TemporaryDirectory() as tmp:
            volume = Mock()
            with patch.object(comfyapp, "CUSTOM_NODES_PATH", tmp), \
                 patch.object(comfyapp, "custom_nodes_vol", volume), \
                 patch.object(
                     comfyapp,
                     "custom_node_source_generation",
                     return_value=generation,
                 ), patch.object(
                     comfyapp,
                     "_write_custom_nodes_generation_record_no_commit",
                     return_value={
                         "schema_version": 2,
                         "content_generation": generation,
                     },
                 ) as mock_writer:
                result = comfyapp.sync_custom_nodes_to_volume.local(
                    self._archive_with_node()
                )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["content_generation"], generation)
        mock_writer.assert_called_once_with(
            reason="post_sync_custom_nodes_to_volume",
            content_generation=generation,
        )
        volume.commit.assert_called_once_with()

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

    def test_experiment_evidence_dirs_are_not_published(self):
        """Host-side evidence must never reach the image or the identity.

        ``golden_history`` and ``unetClipExperimentsSeptember`` were ~68.7% of
        the published custom-node payload (1.66 GB / 1,569 files) while
        contributing no runtime code.  Every deploy paid to walk, hash, and
        per-file-RPC them.  They stay tracked in git; this pins only that they
        are pruned from publication, from the image ignore patterns, and from
        the publication generation.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "custom_nodes"
            node = root / "comfyui-modal"
            node.mkdir(parents=True)
            (node / "source.py").write_text("canonical", encoding="utf-8")

            for name in publication_policy.EVIDENCE_ONLY_DIR_NAMES:
                evidence = node / name
                evidence.mkdir()
                # A .py file so only the directory exclusion can prune it.
                (evidence / "evidence.py").write_text("evidence", encoding="utf-8")
                nested = evidence / "nested"
                nested.mkdir()
                (nested / "deep.py").write_text("deep", encoding="utf-8")

            published = {
                path.relative_to(root).as_posix()
                for path in publication_policy.iter_publication_files(root)
            }
            self.assertIn("comfyui-modal/source.py", published)
            for name in publication_policy.EVIDENCE_ONLY_DIR_NAMES:
                self.assertFalse(
                    [p for p in published if f"/{name}/" in p or p.endswith(f"/{name}")],
                    msg=f"{name} must not be published",
                )

            # The same policy drives the image ignore patterns Modal prunes on.
            ignore_patterns = publication_policy.image_ignore_patterns()
            for name in publication_policy.EVIDENCE_ONLY_DIR_NAMES:
                self.assertTrue(
                    any(name in str(pattern) for pattern in ignore_patterns),
                    msg=f"{name} must appear in the image ignore patterns",
                )

            # Changing evidence content must not move the publication
            # generation: the generation is what makes a redeploy look dirty.
            before = publication_policy.compute_publication_generation(root)
            for name in publication_policy.EVIDENCE_ONLY_DIR_NAMES:
                (node / name / "evidence.py").write_text("mutated", encoding="utf-8")
            self.assertEqual(
                before,
                publication_policy.compute_publication_generation(root),
            )


if __name__ == "__main__":
    unittest.main()
