"""Tests for the snapshot-build manifest tooling and the lean-snapshot gate.

Covers:
- ``snapshot_build_manifest`` capture: gated off by default, bounded/JSON-safe
  when enabled, correct stage storage, and complete key surface.
- Lean snapshot gate in ``modal_app`` / ``model_preload``: stubs are active
  only when ``COMFYMODAL_V2_LEAN_SNAPSHOT=1`` and are behavior-identical
  (gates off) in production default.
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from types import SimpleNamespace

from comfymodal_runtime import snapshot_build_manifest as sbm


class SnapshotBuildManifestTest(unittest.TestCase):
    def test_disabled_by_default(self) -> None:
        env = dict(os.environ)
        env.pop("COMFYMODAL_V2_SNAPSHOT_MANIFEST", None)
        with _env(env):
            self.assertFalse(sbm.manifest_enabled())

    def test_enabled_with_truthy(self) -> None:
        for token in ("1", "true", "TRUE", "yes", "on"):
            with _env({"COMFYMODAL_V2_SNAPSHOT_MANIFEST": token}):
                self.assertTrue(sbm.manifest_enabled(), token)

    def test_capture_full_surface_and_json_safe(self) -> None:
        manifest = sbm.capture_snapshot_manifest("before_capture", model_ctx=None)
        for key in (
            "stage", "capture_wall_unix_ns", "capture_mono_ns",
            "status", "smaps_rollup", "mappings", "modules", "threads",
            "children", "fds", "torch_threads", "retained_models",
            "executors", "gc", "identity",
        ):
            self.assertIn(key, manifest, key)
        self.assertEqual(manifest["stage"], "before_capture")
        # JSON-safe round trip (bounded sampling must not blow up).
        dumped = sbm.dump_manifest_json(manifest)
        self.assertIsInstance(dumped, str)
        loaded = json.loads(dumped)
        self.assertEqual(loaded["stage"], "before_capture")
        # On non-Linux hosts /proc is absent; the manifest degrades quietly.
        if loaded["mappings"].get("available"):
            self.assertIn("total_mappings", loaded["mappings"])

    def test_retained_models_capture(self) -> None:
        class FakeModel:
            def parameters(self):
                return iter([])

        class FakeKey:
            unet_identity = "unet-x"
            clip_identity = "clip-y"
            vae_identity = "vae-z"

        ctx = SimpleNamespace(model_key=FakeKey(), unet=FakeModel(), clip=None, vae=None)
        out = sbm._capture_retained_models(ctx)
        self.assertTrue(out["present"])
        self.assertEqual(out["unet_identity"], "unet-x")
        self.assertIn("unet", out)
        self.assertNotIn("clip", out)

    def test_retained_models_absent(self) -> None:
        out = sbm._capture_retained_models(None)
        self.assertFalse(out["present"])

    def test_stage_storage(self) -> None:
        with _env({"COMFYMODAL_V2_SNAPSHOT_MANIFEST": "1"}):
            sbm.capture_snapshot_manifest("entry_probe", model_ctx=None)
        self.assertIn("entry_probe", sbm.latest_manifests())

    def test_mappings_bounded(self) -> None:
        out = sbm._capture_mappings()
        self.assertLessEqual(len(out.get("top_paths_by_count", [])), sbm._MAX_MAPPING_PATHS)

    def test_executors_scan(self) -> None:
        out = sbm._capture_executors()
        self.assertIsInstance(out["count"], int)
        self.assertLessEqual(len(out["executors"]), sbm._MAX_EXECUTORS)

    def test_never_raises_on_host(self) -> None:
        # /proc reads return None on Windows; everything must degrade quietly.
        manifest = sbm.capture_snapshot_manifest("host_probe", model_ctx=None)
        self.assertIsInstance(manifest, dict)


class LeanSnapshotGateTest(unittest.TestCase):
    def _probe(self, lean: str) -> dict[str, object]:
        """Import model_preload in a fresh interpreter under the gate value.

        The module caches its gate at import time, so cross-test reloads in
        the same interpreter cannot observe both arms; a subprocess gives an
        isolated module state for each arm.
        """
        import subprocess

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        code = (
            "import os,sys;"
            "os.environ['COMFYMODAL_V2_LEAN_SNAPSHOT']=sys.argv[1];"
            "sys.path.insert(0,sys.argv[2]);"
            "import json;"
            "from comfymodal_runtime import model_preload as mp;"
            "print(json.dumps({"
            "'lean': bool(mp._LEAN_SNAPSHOT),"
            "'page_path_probe_enabled': bool(mp.page_path_probe_enabled()),"
            "'synth_h2d_probe_enabled': bool(mp.synth_h2d_probe_enabled()),"
            "'rehome_after_restore_enabled': bool(mp.rehome_after_restore_enabled()),"
            "'unet_storage_sizes': list(mp.unet_storage_sizes(object())),"
            "'backing_evidence': mp.capture_unet_backing_evidence('x')"
            "}))"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code, lean, root],
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
        return json.loads(proc.stdout.strip().splitlines()[-1])

    def test_lean_gate_imports_stubs(self) -> None:
        out = self._probe("1")
        self.assertTrue(out["lean"])
        self.assertFalse(out["page_path_probe_enabled"])
        self.assertFalse(out["synth_h2d_probe_enabled"])
        self.assertFalse(out["rehome_after_restore_enabled"])
        self.assertEqual(out["unet_storage_sizes"], [])
        self.assertEqual(out["backing_evidence"], {})

    def test_lean_gate_default_off(self) -> None:
        out = self._probe("0")
        self.assertFalse(out["lean"])
        # Real gate functions are importable and return the default-off state.
        self.assertFalse(out["page_path_probe_enabled"])
        self.assertFalse(out["synth_h2d_probe_enabled"])


class _env:
    def __init__(self, updates: dict[str, str]) -> None:
        self.updates = updates
        self.saved: dict[str, str | None] = {}

    def __enter__(self) -> None:
        for key, value in self.updates.items():
            self.saved[key] = os.environ.get(key)
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def __exit__(self, *exc: object) -> None:
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    unittest.main()
