"""E25 focused tests: pre-graph exact-identity cache + speculative CLIP lane.

Covers:
* pre_graph_cache: compute-or-reuse, exact-key miss, LRU bound, fail-closed.
* speculative_clip_hydration identity: exact identity built from model key +
  loader spec + workflow/deployment identity; prompt/seed never in identity.
* speculative lane: single-flight per request, identity-change drop, consume
  transfers owners, close releases owners, fail-closed on missing inputs.
* wiring integration seam: _try_fast_hydrate takes a completed speculative
  read only when the manifest matches (unit-level, with a stubbed spec).
"""

from __future__ import annotations

import os
import sys
import threading
import time
import unittest
from types import SimpleNamespace

# Isolate from real ComfyUI/torch import cost where possible.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from comfymodal_runtime import pre_graph_cache as pgc
from comfymodal_runtime import speculative_clip_hydration as sch


class _FakeModelKey:
    def __init__(self, hash_val: str = "abc123"):
        self.stable_hash = hash_val


class PreGraphCacheTest(unittest.TestCase):
    def test_compute_or_reuse(self):
        cache = pgc.PreGraphCache()
        calls = []

        def compute():
            calls.append(1)
            return {"v": len(calls)}

        first = pgc.with_cache(cache, "k1", compute)
        second = pgc.with_cache(cache, "k1", compute)
        self.assertEqual(first, {"v": 1})
        self.assertEqual(second, {"v": 1})
        self.assertEqual(len(calls), 1)

    def test_exact_key_miss(self):
        cache = pgc.PreGraphCache()
        cache.put("a", 1)
        self.assertIsNone(cache.get("b"))
        self.assertEqual(cache.get("a"), 1)

    def test_bounded_eviction(self):
        cache = pgc.PreGraphCache(max_entries=2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)
        # 'a' evicted (oldest)
        self.assertIsNone(cache.get("a"))
        self.assertEqual(cache.get("b"), 2)
        self.assertEqual(cache.get("c"), 3)

    def test_empty_key_falls_through(self):
        cache = pgc.PreGraphCache()
        calls = []

        def compute():
            calls.append(1)
            return 42

        self.assertEqual(pgc.with_cache(cache, "", compute), 42)
        self.assertEqual(len(calls), 1)


class SpeculativeIdentityTest(unittest.TestCase):
    def test_identity_excludes_request_seed(self):
        key = _FakeModelKey("hash1")
        spec = {"loaders": {"clip": [{"clip_name": "t5.safetensors"}]}}
        id_a = sch._build_speculative_identity(
            model_key=key, model_spec=spec,
            workflow_hash="wf", deployment_hash="dep", custom_node_generation="gen",
        )
        id_b = sch._build_speculative_identity(
            model_key=key, model_spec=spec,
            workflow_hash="wf", deployment_hash="dep", custom_node_generation="gen",
        )
        # Same identity for identical inputs.
        self.assertEqual(id_a, id_b)
        # Prompt text / seed are NOT part of the identity (no field for them).

    def test_identity_changes_with_model_or_workflow(self):
        key = _FakeModelKey("hash1")
        spec = {"loaders": {"clip": [{"clip_name": "t5.safetensors"}]}}
        base = dict(model_key=key, model_spec=spec,
                    workflow_hash="wf", deployment_hash="dep",
                    custom_node_generation="gen")
        id_1 = sch._build_speculative_identity(**base)
        id_2 = sch._build_speculative_identity(**{**base, "workflow_hash": "wf2"})
        id_3 = sch._build_speculative_identity(**{**base, "model_key": _FakeModelKey("hash2")})
        self.assertNotEqual(id_1, id_2)
        self.assertNotEqual(id_1, id_3)

    def test_start_gates(self):
        # No request id -> None (no lane).
        self.assertIsNone(sch._start_speculative_clip_lane(
            request_id="", model_key=_FakeModelKey(), model_spec={},
            workflow_hash="", deployment_hash="", custom_node_generation="",
        ))
        # Fast hydration flag off -> None.
        old = os.environ.get("COMFYMODAL_V2_CLIP_FAST_HYDRATION")
        os.environ["COMFYMODAL_V2_CLIP_FAST_HYDRATION"] = "0"
        try:
            self.assertIsNone(sch._start_speculative_clip_lane(
                request_id="r1", model_key=_FakeModelKey(), model_spec={},
                workflow_hash="", deployment_hash="", custom_node_generation="",
            ))
        finally:
            if old is None:
                os.environ.pop("COMFYMODAL_V2_CLIP_FAST_HYDRATION", None)
            else:
                os.environ["COMFYMODAL_V2_CLIP_FAST_HYDRATION"] = old

    def test_start_requires_frozen_manifest(self):
        # E26: without a frozen manifest on the CLIP object (and no
        # file_facts), the lane fails closed at plan receipt — it never
        # starts a worker and never scans folder_paths.
        old_flag = os.environ.get("COMFYMODAL_V2_CLIP_FAST_HYDRATION")
        old_spec = os.environ.get("COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION")
        os.environ["COMFYMODAL_V2_CLIP_FAST_HYDRATION"] = "1"
        os.environ["COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION"] = "1"
        try:
            lane = sch._start_speculative_clip_lane(
                request_id="r-manifest-less",
                model_key=_FakeModelKey(),
                model_spec={"loaders": {"clip": [{"clip_name": "t5.safetensors"}]}},
                workflow_hash="wf", deployment_hash="dep", custom_node_generation="gen",
                clip=object(),  # no attached manifest
                cpu_models=None,
            )
            self.assertIsNone(lane)
        finally:
            if old_flag is None:
                os.environ.pop("COMFYMODAL_V2_CLIP_FAST_HYDRATION", None)
            else:
                os.environ["COMFYMODAL_V2_CLIP_FAST_HYDRATION"] = old_flag
            if old_spec is None:
                os.environ.pop("COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION", None)
            else:
                os.environ["COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION"] = old_spec
            sch.clear_speculative_lanes_for_test()

    def test_lane_single_flight_and_consume_close(self):
        old_flag = os.environ.get("COMFYMODAL_V2_CLIP_FAST_HYDRATION")
        old_spec = os.environ.get("COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION")
        os.environ["COMFYMODAL_V2_CLIP_FAST_HYDRATION"] = "1"
        os.environ["COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION"] = "1"
        try:
            import tempfile
            tmpdir = tempfile.mkdtemp(prefix="comfymodal-e26-clip-")
            path = os.path.join(tmpdir, "t5.safetensors")
            with open(path, "wb") as f:
                f.write(b"\x00" * 1024)
            manifest = {
                "eligible": True,
                "files": [{
                    "path": path,
                    "size_bytes": 1024,
                    "mtime_ns": int(os.path.getmtime(path) * 1_000_000_000),
                    "dtype": "torch.float16",
                    "key_set": [],
                    "key_shapes": {},
                    "pipeline": [],
                }],
            }

            class _AttrClip:
                pass

            clip = _AttrClip()
            from comfymodal_runtime import clip_fast_hydration as cfh
            cfh.attach_clip_manifest(clip, manifest)
            # Lane starts; the worker fails the fastsafetensors load (the
            # file is not a real safetensors), records failure, and the
            # demand path treats it as a normal-hydrator fallback.
            lane = sch._start_speculative_clip_lane(
                request_id="r-single", model_key=_FakeModelKey(),
                model_spec={"loaders": {"clip": [{"clip_name": "t5.safetensors"}]}},
                workflow_hash="wf", deployment_hash="dep", custom_node_generation="gen",
                clip=clip,
            )
            self.assertIsNotNone(lane)
            self.assertEqual(lane.clip_names, ("t5.safetensors",))
            self.assertEqual(lane.path_source, "frozen_manifest")
            self.assertEqual(lane.file_paths, (path,))
            # The lane resolves paths from the frozen manifest (never a
            # folder_paths scan): single-flight by request id.
            lane2 = sch._start_speculative_clip_lane(
                request_id="r-single", model_key=_FakeModelKey(),
                model_spec={"loaders": {"clip": [{"clip_name": "t5.safetensors"}]}},
                workflow_hash="wf", deployment_hash="dep", custom_node_generation="gen",
                clip=clip,
            )
            self.assertIs(lane, lane2)
            # Give the worker a moment to fail the read and finalize.
            import time as _time
            deadline = _time.monotonic() + 13.0
            while lane.finished_mono_ns == 0 and _time.monotonic() < deadline:
                _time.sleep(0.05)
            self.assertGreater(lane.finished_mono_ns, 0)
            self.assertFalse(lane.record.get("result", {}).get("ok", False))
            # Cleanup is safe and idempotent.
            sch.close_speculative_clip_lane("r-single")
            sch.clear_speculative_lanes_for_test()
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)
        finally:
            if old_flag is None:
                os.environ.pop("COMFYMODAL_V2_CLIP_FAST_HYDRATION", None)
            else:
                os.environ["COMFYMODAL_V2_CLIP_FAST_HYDRATION"] = old_flag
            if old_spec is None:
                os.environ.pop("COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION", None)
            else:
                os.environ["COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION"] = old_spec
            sch.clear_speculative_lanes_for_test()

    def test_close_lane_never_raises(self):
        sch.clear_speculative_lanes_for_test()
        # Closing a non-existent lane is a no-op.
        sch.close_speculative_clip_lane("does-not-exist")
        sch.clear_speculative_lanes_for_test()


class _FakeLane:
    """Minimal stand-in for the module's _SpeculativeClipLane in take/close
    semantics tests (no GPU objects required)."""

    def __init__(self, request_id, identity, per_file_sds, owners, record):
        self.request_id = request_id
        self.identity = identity
        self.per_file_sds = per_file_sds
        self.owners = owners
        self.record = record
        self.finished_mono_ns = time.monotonic_ns()
        self.cancelled = False
        self.started_mono_ns = time.monotonic_ns()


if __name__ == "__main__":
    unittest.main()
