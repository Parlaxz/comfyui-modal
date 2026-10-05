"""Phase G9 deterministic exact-round-trip integration proof (G1 §11).

Version
  → manifest Export (read-only)
  → Import dry run (zero writes)
  → committed Import (atomic)
  → new local Workflow Version #1
  → Export again

Asserts canonical ``graph_json`` / ``api_prompt_json`` / executable-prompt /
graph-hash equality, and Mapping semantic equality under reminted ids,
and manifest identity stability excluding allowed provenance/time metadata.
No live ComfyUI required.
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_TESTS_DIR = str(Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    # Sibling-module imports (test_portability_backend) must work both when
    # run directly and when loaded as ``tests.test_portability_roundtrip``.
    sys.path.insert(0, _TESTS_DIR)

import portability_contract as pc
import studio_workflow_manifest as manifest_codec
from portability_service import PortabilityService
from studio_domain.services import WorkflowDomainService

from test_portability_backend import (
    MAPPING_BODY,
    CoreOnlyResolver,
    PINNED_HASH,
    sample_graph_json,
    sample_prompt,
)


def canonical(value) -> str:
    return pc.canonical_json(value)


class ExactRoundTripTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = str(Path(self._tmp.name))
        self.service = WorkflowDomainService(self.root)
        self.portability = PortabilityService(
            self.service, resolver=CoreOnlyResolver()
        )

    def tearDown(self):
        self._tmp.cleanup()

    def _snapshot(self):
        snap = {}
        for name in (
            ".studio_workflows.json",
            ".studio_workflow_versions.json",
            ".studio_workflow_mappings.json",
        ):
            path = Path(self.root) / name
            snap[name] = path.read_bytes() if path.exists() else None
        return snap

    def _build_source(self):
        wf = self.service.create_workflow(
            "Round Trip Source",
            description="source description",
            source_author="author",
            source_url="https://example.invalid/source",
            compatible_models=["krea_model.safetensors"],
        )
        capture = {
            "graph_json": sample_graph_json(),
            "api_prompt_json": {"workflow": {}, "output": sample_prompt(seed=99)},
        }
        version = self.service.create_version_from_capture(wf["workflow_id"], capture)
        self.service.set_mapping(
            version["workflow_version_id"],
            entries=MAPPING_BODY["entries"],
            output_node_id=MAPPING_BODY["output_node_id"],
        )
        return wf, version, []

    def _export(self, version_id):
        result = self.portability.export_manifest(version_id)
        return result["manifest"], result["filename"]

    def _remap_ids(self, manifest, id_map):
        """Rewrite reminted local ids back to the source ids so identity is
        comparable excluding ALLOWED provenance differences (ids, timestamps,
        and the deterministic ``" (imported)"`` name suffix)."""
        out = copy.deepcopy(manifest)
        out["workflow"]["workflow_id"] = id_map["wf"]
        out["workflow"]["version_id"] = id_map["wv"]
        if isinstance(out["workflow"].get("display"), dict):
            out["workflow"]["display"]["name"] = id_map["name"]
        out["version"]["workflow_id"] = id_map["wf"]
        out["version"]["workflow_version_id"] = id_map["wv"]
        out["version"]["created_at"] = id_map["created_at"]
        out["mapping"]["mapping_id"] = id_map["wm"]
        out["mapping"]["workflow_version_id"] = id_map["wv"]
        return out


    def test_full_round_trip_is_exact(self):
        wf, version, _ = self._build_source()
        vid = version["workflow_version_id"]

        # ── Export #1 (read-only) ──────────────────────────────────────
        before = self._snapshot()
        m1, filename1 = self._export(vid)
        self.assertEqual(self._snapshot(), before)
        self.assertEqual(m1["manifest_version"], 1)

        # ── Dry run (zero writes) ──────────────────────────────────────
        before = self._snapshot()
        preview = self.portability.preview_import(copy.deepcopy(m1))
        self.assertEqual(preview["status"], "preview")
        self.assertTrue(preview["valid"])
        self.assertEqual(self._snapshot(), before)

        # ── Committed import ───────────────────────────────────────────
        commit = self.portability.commit_import(copy.deepcopy(m1))
        self.assertEqual(commit["status"], "ok")

        imported_wf_id = commit["workflow_id"]
        imported_versions = self.service.store.list_versions_for_workflow(imported_wf_id)
        self.assertEqual(len(imported_versions), 1)
        imported_version = imported_versions[0]
        self.assertEqual(imported_version["version_number"], 1)
        imported_vid = imported_version["workflow_version_id"]

        # Foreign ids never become local authority.
        local_ids = {
            imported_wf_id,
            imported_vid,
            commit["mapping_id"],
        }
        foreign_ids = {
            wf["workflow_id"], vid,
        }
        self.assertEqual(local_ids & foreign_ids, set())

        # ── Export #2 ──────────────────────────────────────────────────
        m2, filename2 = self._export(imported_vid)

        # Exact-JSON fidelity of the persisted capture pair.
        self.assertEqual(
            canonical(m1["version"]["graph_json"]),
            canonical(m2["version"]["graph_json"]),
        )
        self.assertEqual(
            canonical(m1["version"]["api_prompt_json"]),
            canonical(m2["version"]["api_prompt_json"]),
        )
        self.assertEqual(
            canonical(m1["workflow"]["graph"]),
            canonical(m2["workflow"]["graph"]),
        )
        self.assertEqual(m1["workflow"]["graph_hash"], m2["workflow"]["graph_hash"])
        self.assertEqual(
            m1["workflow"]["graph_hash"], imported_version["graph_hash"]
        )

        # Mapping semantically equal under reminted ids.
        map1 = dict(m1["mapping"])
        map2 = dict(m2["mapping"])
        self.assertEqual(map1["output_node_id"], map2["output_node_id"])
        self.assertEqual(
            canonical(map1["entries"]), canonical(map2["entries"])
        )


        # Manifest identity stable excluding allowed provenance/time deltas.
        base_map = {
            "wf": m1["workflow"]["workflow_id"],
            "wv": m1["workflow"]["version_id"],
            "wm": m1["mapping"]["mapping_id"],
            "created_at": m1["version"].get("created_at"),
            "name": m1["workflow"]["display"]["name"],
        }
        n1 = self._remap_ids(m1, base_map)
        n2 = self._remap_ids(m2, base_map)
        self.assertEqual(
            manifest_codec.manifest_hash(n1, include_metadata=False),
            manifest_codec.manifest_hash(n2, include_metadata=False),
        )
        # Full canonical equality excluding the free-form metadata root
        # (exported_at is time metadata, excluded from identity by contract).
        n1.pop("metadata")
        n2.pop("metadata")
        self.assertEqual(canonical(n1), canonical(n2))

        # Deterministic filenames remain well-formed on both exports.
        for manifest, filename in ((m1, filename1), (m2, filename2)):
            expected = pc.suggest_export_filename(
                manifest["workflow"]["display"]["name"],
                manifest["version"]["version_number"],
                manifest["workflow"]["graph_hash"],
            )
            self.assertTrue(filename.endswith(".workflow.json"))
            self.assertIn(expected.split("-v")[0], filename)

    def test_double_import_creates_two_independent_workflows(self):
        wf, version, _ = self._build_source()
        m1, _ = self._export(version["workflow_version_id"])
        first = self.portability.commit_import(copy.deepcopy(m1))
        second = self.portability.commit_import(copy.deepcopy(m1))
        self.assertNotEqual(first["workflow_id"], second["workflow_id"])
        self.assertNotEqual(first["workflow_version_id"], second["workflow_version_id"])
        self.assertNotEqual(first["mapping_id"], second["mapping_id"])
        workflows = json.loads((Path(self.root) / ".studio_workflows.json").read_text())
        self.assertEqual(len(workflows), 3)
        for payload in (first, second):
            owned_mapping = self.service.store.get_mapping_for_version(
                payload["workflow_version_id"]
            )
            self.assertIsNotNone(owned_mapping)
            self.assertEqual(owned_mapping["mapping_id"], payload["mapping_id"])

    def test_unknown_section_fields_preview_survives(self):
        fixture = (
            Path(__file__).parent / "fixtures" / "portability" / "manifests"
            / "unknown_section_fields.manifest.json"
        )
        raw = json.loads(fixture.read_text(encoding="utf-8"))
        preview = self.portability.preview_import(raw)
        self.assertTrue(preview["valid"])
        self.assertEqual(preview["issues"], [])

    def test_unknown_root_section_rejected(self):
        fixture = (
            Path(__file__).parent / "fixtures" / "portability" / "manifests"
            / "unknown_root_section.manifest.invalid.json"
        )
        raw = fixture.read_text(encoding="utf-8")
        before = self._snapshot()
        with self.assertRaises(Exception) as ctx:
            self.portability.preview_import(raw)
        message = " ".join(
            [str(ctx.exception)] + list(getattr(ctx.exception, "issues", []))
        )
        self.assertIn("unknown root section", message)
        self.assertEqual(self._snapshot(), before)


if __name__ == "__main__":
    unittest.main()
