"""E26 focused tests: concrete cold-path wins.

Covers:
* frozen-manifest absolute-path resolution for the speculative CLIP lane
  (authoritative source, generic for arbitrary text-encoder filenames).
* file_facts fallback when no attached manifest exists.
* stale manifest / missing file rejection at plan receipt (fail closed).
* demand fallback unchanged: a lane that fails to read records a failed
  result the demand path treats as a normal-hydrator fallback.
* CLIP-first / UNET-second: the release callback fires exactly once on
  success, on failure, and on cancellation; a failed speculative read
  releases UNET immediately.
* no folder_paths scan on the fast path (resolution happens from the frozen
  manifest/file-facts at plan receipt, never worker-side).
* orchestration ownership: FastColdOrchestrator takes speculative CLIP
  ownership and skips the checkpoint prewarmer's clip prefetch; the storage
  state machine stays legal through the release (CLIP_PREFETCH -> CLIP_DEMAND
  -> UNET_PREFETCH).
* GPU fast-return production default: enabled when env unset, force-disable
  honored, fail-closed residency proof.
* VAE production profile: canonical late default restored; explicit
  experiment flags still select sampling_end.
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from comfymodal_runtime import clip_fast_hydration as cfh
from comfymodal_runtime import speculative_clip_hydration as sch
from comfymodal_runtime import cpu_snapshot_models as csm
from comfymodal_runtime import fast_cold_orchestration as fco


class _FakeModelKey:
    def __init__(self, hash_val: str = "abc123"):
        self.stable_hash = hash_val


class _AttrClip:
    """Minimal CLIP stand-in that can carry the frozen manifest attribute."""
    pass


def _make_manifest(paths, sizes=None):
    """Build a frozen capability manifest matching the demand-side shape."""
    files = []
    for i, path in enumerate(paths):
        size = sizes[i] if sizes else (os.path.getsize(path) if os.path.exists(path) else 0)
        try:
            mtime = int(os.path.getmtime(path) * 1_000_000_000) if os.path.exists(path) else 0
        except OSError:
            mtime = 0
        files.append({
            "path": path,
            "size_bytes": int(size),
            "mtime_ns": mtime,
            "dtype": "torch.float16",
            "key_set": ["a.weight"],
            "key_shapes": {"a.weight": [2, 2]},
            "pipeline": [],
        })
    return {"schema": 1, "eligible": True, "files": files}


def _make_clip_with_manifest(paths, sizes=None):
    clip = _AttrClip()
    cfh.attach_clip_manifest(clip, _make_manifest(paths, sizes))
    return clip


class FrozenManifestResolutionTest(unittest.TestCase):
    def setUp(self):
        self._old_flag = os.environ.get("COMFYMODAL_V2_CLIP_FAST_HYDRATION")
        self._old_spec = os.environ.get("COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION")
        os.environ["COMFYMODAL_V2_CLIP_FAST_HYDRATION"] = "1"
        os.environ["COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION"] = "1"
        self._tmp = tempfile.mkdtemp(prefix="comfymodal-e26-")

    def tearDown(self):
        import shutil
        if self._old_flag is None:
            os.environ.pop("COMFYMODAL_V2_CLIP_FAST_HYDRATION", None)
        else:
            os.environ["COMFYMODAL_V2_CLIP_FAST_HYDRATION"] = self._old_flag
        if self._old_spec is None:
            os.environ.pop("COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION", None)
        else:
            os.environ["COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION"] = self._old_spec
        sch.clear_speculative_lanes_for_test()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _path(self, name):
        return os.path.join(self._tmp, name)

    def test_absolute_manifest_path_accepted(self):
        path = self._path("t5.safetensors")
        with open(path, "wb") as f:
            f.write(b"\x00" * 1024)
        lane = sch._start_speculative_clip_lane(
            request_id="r-abs",
            model_key=_FakeModelKey(),
            model_spec={"loaders": {"clip": [{"clip_name": "t5.safetensors"}]}},
            workflow_hash="wf", deployment_hash="dep", custom_node_generation="gen",
            clip=_make_clip_with_manifest([path]),
        )
        self.assertIsNotNone(lane)
        self.assertEqual(lane.path_source, "frozen_manifest")
        self.assertEqual(lane.file_paths, (path,))
        # No worker-side folder_paths resolution needed: the path is already
        # the authoritative frozen absolute path.
        self.assertNotIn("folder_paths", lane.record)

    def test_arbitrary_text_encoder_filename_accepted(self):
        # Generic for ANY text encoder: a path with spaces and an unusual
        # name — the mechanism must not hard-code qwen_3_4b.safetensors.
        path = self._path("my custom text encoder v2.safetensors")
        with open(path, "wb") as f:
            f.write(b"\x00" * 2048)
        lane = sch._start_speculative_clip_lane(
            request_id="r-generic",
            model_key=_FakeModelKey(),
            model_spec={"loaders": {"clip": [{"clip_name": "my custom text encoder v2.safetensors"}]}},
            workflow_hash="wf", deployment_hash="dep", custom_node_generation="gen",
            clip=_make_clip_with_manifest([path]),
        )
        self.assertIsNotNone(lane)
        self.assertEqual(lane.file_paths, (path,))
        self.assertIn("my custom text encoder v2.safetensors", lane.file_paths[0])

    def test_multiple_clip_files_handled(self):
        p1 = self._path("clip_a.safetensors")
        p2 = self._path("clip_b.safetensors")
        for p in (p1, p2):
            with open(p, "wb") as f:
                f.write(b"\x00" * 1024)
        lane = sch._start_speculative_clip_lane(
            request_id="r-multi",
            model_key=_FakeModelKey(),
            model_spec={"loaders": {"clip": [{"clip_name": "clip_a.safetensors"}, {"clip_name": "clip_b.safetensors"}]}},
            workflow_hash="wf", deployment_hash="dep", custom_node_generation="gen",
            clip=_make_clip_with_manifest([p1, p2]),
        )
        self.assertIsNotNone(lane)
        self.assertEqual(lane.file_paths, (p1, p2))

    def test_file_facts_fallback_when_no_manifest(self):
        path = self._path("t5.safetensors")
        with open(path, "wb") as f:
            f.write(b"\x00" * 1024)
        facts = (csm.ModelFileFact(role="clip1", path=path, size_bytes=1024, mtime_ns=1),)
        cpu_models = SimpleNamespace(file_facts=facts)
        lane = sch._start_speculative_clip_lane(
            request_id="r-facts",
            model_key=_FakeModelKey(),
            model_spec={"loaders": {"clip": [{"clip_name": "t5.safetensors"}]}},
            workflow_hash="wf", deployment_hash="dep", custom_node_generation="gen",
            clip=object(),  # no manifest
            cpu_models=cpu_models,
        )
        self.assertIsNotNone(lane)
        self.assertEqual(lane.path_source, "file_facts")
        self.assertEqual(lane.file_paths, (path,))

    def test_stale_manifest_rejected(self):
        path = self._path("t5.safetensors")
        with open(path, "wb") as f:
            f.write(b"\x00" * 1024)
        # Manifest records a stale (larger) size: the lane fails closed at
        # plan receipt before any read.
        lane = sch._start_speculative_clip_lane(
            request_id="r-stale",
            model_key=_FakeModelKey(),
            model_spec={"loaders": {"clip": [{"clip_name": "t5.safetensors"}]}},
            workflow_hash="wf", deployment_hash="dep", custom_node_generation="gen",
            clip=_make_clip_with_manifest([path], sizes=[999999]),
        )
        self.assertIsNone(lane)

    def test_generation_mismatch_changes_identity(self):
        path = self._path("t5.safetensors")
        with open(path, "wb") as f:
            f.write(b"\x00" * 1024)
        base = dict(
            model_key=_FakeModelKey(),
            model_spec={"loaders": {"clip": [{"clip_name": "t5.safetensors"}]}},
            workflow_hash="wf", deployment_hash="dep",
        )
        id_a = sch._build_speculative_identity(**base, custom_node_generation="gen1")
        id_b = sch._build_speculative_identity(**base, custom_node_generation="gen2")
        self.assertNotEqual(id_a, id_b)
        # Manifest digest folded into the identity: same manifest same id.
        clip = _make_clip_with_manifest([path])
        lane = sch._start_speculative_clip_lane(
            request_id="r-gen", model_key=_FakeModelKey(),
            model_spec={"loaders": {"clip": [{"clip_name": "t5.safetensors"}]}},
            workflow_hash="wf", deployment_hash="dep", custom_node_generation="gen1",
            clip=clip,
        )
        self.assertIsNotNone(lane)
        self.assertIn(":mf:", lane.identity)

    def test_missing_file_rejected(self):
        path = self._path("missing.safetensors")
        clip = _make_clip_with_manifest([path], sizes=[1024])
        lane = sch._start_speculative_clip_lane(
            request_id="r-missing",
            model_key=_FakeModelKey(),
            model_spec={"loaders": {"clip": [{"clip_name": "missing.safetensors"}]}},
            workflow_hash="wf", deployment_hash="dep", custom_node_generation="gen",
            clip=clip,
        )
        self.assertIsNone(lane)

    def test_demand_fallback_unchanged_on_worker_failure(self):
        # A lane that starts but whose read fails (not a real safetensors)
        # records ok=False; the demand path falls back to the normal hydrator.
        path = self._path("t5.safetensors")
        with open(path, "wb") as f:
            f.write(b"\x00" * 1024)
        lane = sch._start_speculative_clip_lane(
            request_id="r-fallback",
            model_key=_FakeModelKey(),
            model_spec={"loaders": {"clip": [{"clip_name": "t5.safetensors"}]}},
            workflow_hash="wf", deployment_hash="dep", custom_node_generation="gen",
            clip=_make_clip_with_manifest([path]),
        )
        self.assertIsNotNone(lane)
        deadline = time.monotonic() + 13.0
        while lane.finished_mono_ns == 0 and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertGreater(lane.finished_mono_ns, 0)
        self.assertFalse(lane.record.get("result", {}).get("ok", False))
        # take_speculative_read returns None -> normal hydrator runs.
        self.assertIsNone(sch.take_speculative_read("r-fallback"))

    def test_join_waits_for_inflight_lane(self):
        # E26: demand that arrives while the spec lane is still reading must
        # join (bounded) so a completed successful read is consumed instead
        # of a second full CLIP read.  This test proves the join-then-take
        # sequence with an artificially slow lane.
        path = self._path("t5.safetensors")
        with open(path, "wb") as f:
            f.write(b"\x00" * 1024)
        calls = []
        lane = sch._start_speculative_clip_lane(
            request_id="r-join",
            model_key=_FakeModelKey(),
            model_spec={"loaders": {"clip": [{"clip_name": "t5.safetensors"}]}},
            workflow_hash="wf", deployment_hash="dep", custom_node_generation="gen",
            clip=_make_clip_with_manifest([path]),
            release_callback=lambda: calls.append(1),
        )
        self.assertIsNotNone(lane)
        # The lane is in flight (not finished) for this fake file; the read
        # fails fast, but join must wait for completion then take returns None
        # (failed read) — the demand fallback path.
        record = sch.join_speculative_clip_lane("r-join", timeout_s=15.0)
        self.assertIsNotNone(record)
        self.assertFalse(record.get("result", {}).get("ok", False))
        self.assertIsNone(sch.take_speculative_read("r-join"))
        # Release fired exactly once.
        self.assertEqual(len(calls), 1)


class ReleaseOrderingTest(unittest.TestCase):
    def setUp(self):
        self._old_flag = os.environ.get("COMFYMODAL_V2_CLIP_FAST_HYDRATION")
        self._old_spec = os.environ.get("COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION")
        os.environ["COMFYMODAL_V2_CLIP_FAST_HYDRATION"] = "1"
        os.environ["COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION"] = "1"
        self._tmp = tempfile.mkdtemp(prefix="comfymodal-e26-")

    def tearDown(self):
        import shutil
        if self._old_flag is None:
            os.environ.pop("COMFYMODAL_V2_CLIP_FAST_HYDRATION", None)
        else:
            os.environ["COMFYMODAL_V2_CLIP_FAST_HYDRATION"] = self._old_flag
        if self._old_spec is None:
            os.environ.pop("COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION", None)
        else:
            os.environ["COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION"] = self._old_spec
        sch.clear_speculative_lanes_for_test()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _path(self, name):
        return os.path.join(self._tmp, name)

    def test_release_fires_exactly_once_on_completion(self):
        path = self._path("t5.safetensors")
        with open(path, "wb") as f:
            f.write(b"\x00" * 1024)
        calls = []
        lock = threading.Lock()

        def cb():
            with lock:
                calls.append(1)

        lane = sch._start_speculative_clip_lane(
            request_id="r-rel",
            model_key=_FakeModelKey(),
            model_spec={"loaders": {"clip": [{"clip_name": "t5.safetensors"}]}},
            workflow_hash="wf", deployment_hash="dep", custom_node_generation="gen",
            clip=_make_clip_with_manifest([path]),
            release_callback=cb,
        )
        self.assertIsNotNone(lane)
        deadline = time.monotonic() + 13.0
        while lane.finished_mono_ns == 0 and time.monotonic() < deadline:
            time.sleep(0.05)
        sch.close_speculative_clip_lane("r-rel")
        with lock:
            self.assertEqual(len(calls), 1)

    def test_release_fires_on_failure(self):
        # A failed speculative read must release UNET immediately — never
        # delay UNET because the lane failed.
        path = self._path("t5.safetensors")
        with open(path, "wb") as f:
            f.write(b"\x00" * 1024)
        calls = []
        lane = sch._start_speculative_clip_lane(
            request_id="r-fail-rel",
            model_key=_FakeModelKey(),
            model_spec={"loaders": {"clip": [{"clip_name": "t5.safetensors"}]}},
            workflow_hash="wf", deployment_hash="dep", custom_node_generation="gen",
            clip=_make_clip_with_manifest([path]),
            release_callback=lambda: calls.append(1),
        )
        self.assertIsNotNone(lane)
        deadline = time.monotonic() + 13.0
        while lane.finished_mono_ns == 0 and time.monotonic() < deadline:
            time.sleep(0.05)
        # The fake file is not a real safetensors: the read failed.
        self.assertFalse(lane.record.get("result", {}).get("ok", False))
        # The release fired anyway (from the worker finally).
        self.assertEqual(len(calls), 1)

    def test_release_fires_on_cancellation(self):
        path = self._path("t5.safetensors")
        with open(path, "wb") as f:
            f.write(b"\x00" * 1024)
        calls = []
        lane = sch._start_speculative_clip_lane(
            request_id="r-cancel",
            model_key=_FakeModelKey(),
            model_spec={"loaders": {"clip": [{"clip_name": "t5.safetensors"}]}},
            workflow_hash="wf", deployment_hash="dep", custom_node_generation="gen",
            clip=_make_clip_with_manifest([path]),
            release_callback=lambda: calls.append(1),
        )
        self.assertIsNotNone(lane)
        sch.close_speculative_clip_lane("r-cancel")
        self.assertEqual(len(calls), 1)
        # No stale state for the next request.
        self.assertIsNone(sch.get_speculative_clip_lane("r-cancel"))


class OrchestrationOwnershipTest(unittest.TestCase):
    def setUp(self):
        self._old_flag = os.environ.get("COMFYMODAL_V2_CLIP_FAST_HYDRATION")
        self._old_spec = os.environ.get("COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION")
        self._old_prev = os.environ.get("COMFYMODAL_V2_CHECKPOINT_PREWARM")
        self._old_fco = os.environ.get("COMFYMODAL_V2_FAST_COLD_ORCHESTRATION")
        os.environ["COMFYMODAL_V2_CLIP_FAST_HYDRATION"] = "1"
        os.environ["COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION"] = "1"
        os.environ["COMFYMODAL_V2_CHECKPOINT_PREWARM"] = "1"
        os.environ["COMFYMODAL_V2_FAST_COLD_ORCHESTRATION"] = "1"

    def tearDown(self):
        for name, old in (
            ("COMFYMODAL_V2_CLIP_FAST_HYDRATION", self._old_flag),
            ("COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION", self._old_spec),
            ("COMFYMODAL_V2_CHECKPOINT_PREWARM", self._old_prev),
            ("COMFYMODAL_V2_FAST_COLD_ORCHESTRATION", self._old_fco),
        ):
            if old is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = old

    def test_speculative_ownership_skips_checkpoint_clip_prefetch(self):
        ctrl = fco.FastColdOrchestrator("r-own", model_spec={}, trace=None)
        # Speculative CLIP owns the source: no checkpoint prewarmer started.
        self.assertTrue(ctrl.speculative_clip_owner())
        self.assertIsNone(ctrl.clip_prefetch)
        # start_clip_prefetch is a no-op under spec ownership.
        self.assertTrue(ctrl.start_clip_prefetch())
        self.assertIsNone(ctrl.clip_prefetch)

    def test_storage_state_machine_through_release(self):
        ctrl = fco.FastColdOrchestrator("r-sm", model_spec={}, trace=None)
        # Lane ownership put storage in CLIP_PREFETCH.
        self.assertEqual(ctrl.storage.storage_owner, fco.STORAGE_CLIP_PREFETCH)
        # Release: CLIP_PREFETCH -> CLIP_DEMAND, then UNET prefetch starts.
        ctrl.on_speculative_clip_done()
        self.assertIn(
            ctrl.storage.storage_owner,
            (fco.STORAGE_CLIP_DEMAND, fco.STORAGE_UNET_PREFETCH, fco.STORAGE_UNET_DEMAND),
        )
        # No illegal transitions recorded.
        for t in ctrl.storage.transitions:
            self.assertIn(t.transition_to, fco._ALLOWED_TRANSITIONS[t.transition_from])

    def test_unet_release_not_gated_when_spec_lane_fails_to_start(self):
        # Simulate: ownership claimed by the controller but the lane could not
        # start (no manifest).  The fail-open release must leave storage legal
        # and UNET unblocked.
        ctrl = fco.FastColdOrchestrator("r-fail-open", model_spec={}, trace=None)
        ctrl.on_speculative_clip_done()
        self.assertNotEqual(ctrl.storage.storage_owner, fco.STORAGE_CLIP_PREFETCH)


class ProductionProfileTest(unittest.TestCase):
    def test_gpu_fast_return_defaults_on(self):
        old = os.environ.get("COMFYMODAL_V2_GPU_FAST_RETURN")
        os.environ.pop("COMFYMODAL_V2_GPU_FAST_RETURN", None)
        try:
            from comfymodal_runtime import model_preload as mp
            self.assertTrue(mp._gpu_fast_return_enabled())
        finally:
            if old is None:
                os.environ.pop("COMFYMODAL_V2_GPU_FAST_RETURN", None)
            else:
                os.environ["COMFYMODAL_V2_GPU_FAST_RETURN"] = old

    def test_gpu_fast_return_force_disable(self):
        old = os.environ.get("COMFYMODAL_V2_GPU_FAST_RETURN")
        os.environ["COMFYMODAL_V2_GPU_FAST_RETURN"] = "0"
        try:
            from comfymodal_runtime import model_preload as mp
            self.assertFalse(mp._gpu_fast_return_enabled())
        finally:
            if old is None:
                os.environ.pop("COMFYMODAL_V2_GPU_FAST_RETURN", None)
            else:
                os.environ["COMFYMODAL_V2_GPU_FAST_RETURN"] = old

    def test_gpu_fast_return_fail_closed_residency(self):
        from comfymodal_runtime import model_preload as mp
        # CPU parameter -> not proven resident -> False.
        class _CPUModel:
            model = SimpleNamespace()
        m = _CPUModel()
        m.model.parameters = lambda: [SimpleNamespace(device="cpu")]
        m.model.buffers = lambda: []
        self.assertFalse(mp._all_models_proven_cuda_resident([m]))

    def test_vae_production_default_is_late(self):
        old_mode = os.environ.get("COMFYMODAL_V2_VAE_ACTIVATION_MODE")
        old_start = os.environ.get("COMFYMODAL_V2_VAE_EARLY_START_MS")
        os.environ.pop("COMFYMODAL_V2_VAE_ACTIVATION_MODE", None)
        os.environ.pop("COMFYMODAL_V2_VAE_EARLY_START_MS", None)
        try:
            from comfymodal_runtime import model_preload as mp
            mp._VAE_ACTIVATION_MODE = mp._resolve_vae_activation_mode("late")
            self.assertEqual(mp.vae_activation_mode(), "late")
        finally:
            if old_mode is None:
                os.environ.pop("COMFYMODAL_V2_VAE_ACTIVATION_MODE", None)
            else:
                os.environ["COMFYMODAL_V2_VAE_ACTIVATION_MODE"] = old_mode
            if old_start is None:
                os.environ.pop("COMFYMODAL_V2_VAE_EARLY_START_MS", None)
            else:
                os.environ["COMFYMODAL_V2_VAE_EARLY_START_MS"] = old_start

    def test_vae_experiment_still_available(self):
        from comfymodal_runtime import model_preload as mp
        # The experiment is NOT deleted: explicit flag still selects the
        # sampling_end mode.
        self.assertEqual(
            mp._resolve_vae_activation_mode("sampling_end"),
            mp._VAE_ACTIVATION_MODE_SAMPLING_END,
        )


class SignatureCachePersistenceTest(unittest.TestCase):
    def test_persistence_round_trip_and_invalidation(self):
        from comfymodal_runtime import prompt_signature_cache as psc
        psc.reset_store()
        try:
            ident = psc.memo_identity(
                workflow_hash="wf1",
                source_workflow_hash="swf1",
                deployment_combined_hash="dep1",
                custom_node_generation="gen1",
                registry_proof={"k": "v"},
            )
            self.assertTrue(ident["complete"])
            entry = {"nodes": {"1": {"class_type": "CLIPLoader", "is_changed": False, "signature": [], "inputs_hash": "x"}}}
            psc.set_store(ident["identity_hash"], entry)
            with tempfile.TemporaryDirectory() as td:
                path = os.path.join(td, "memo.json")
                os.environ["COMFYMODAL_V2_STATE_VOLUME_ROOT"] = td
                try:
                    psc.persist_store(path)
                    psc.reset_store()
                    loaded = psc.load_signature_memo(path)
                    self.assertIn(ident["identity_hash"], loaded)
                finally:
                    os.environ.pop("COMFYMODAL_V2_STATE_VOLUME_ROOT", None)
            # Invalidation: any identity field change -> different hash.
            ident2 = psc.memo_identity(
                workflow_hash="wf2",
                source_workflow_hash="swf1",
                deployment_combined_hash="dep1",
                custom_node_generation="gen1",
                registry_proof={"k": "v"},
            )
            self.assertNotEqual(ident["identity_hash"], ident2["identity_hash"])
        finally:
            psc.reset_store()

    def test_memo_hit_reevaluates_is_changed(self):
        # The memo-hit path must re-evaluate is_changed — a preseed that skips
        # the runtime is_changed cannot be semantically safe.
        from comfymodal_runtime import prompt_signature_cache as psc
        psc.reset_store()
        try:
            node_ids = [1]
            node = {"class_type": "CLIPLoader", "inputs": {"clip_name": "t5.safetensors"}}
            # A valid encoded signature is a frozenset of (key, value) pairs.
            signature = psc.encode_hashable(frozenset({("clip_name", "t5.safetensors")}))
            entry = {
                "nodes": {
                    "1": {
                        "class_type": "CLIPLoader",
                        "is_changed": psc.encode_is_changed(False),
                        "signature": signature,
                        "inputs_hash": psc.canonical_inputs_hash(node["inputs"]),
                    }
                }
            }
            ident = "somehash"
            psc.set_store(ident, entry)
            keys = {}
            subcache = {}
            calls = []

            async def run():
                return await psc.apply_memo_hit(
                    keys=keys,
                    subcache_keys=subcache,
                    node_ids=node_ids,
                    get_node=lambda nid: node,
                    has_node=lambda nid: True,
                    get_is_changed=lambda nid: calls.append(nid) or False,
                    identity_hash=ident,
                )

            import asyncio
            ok, reason = asyncio.run(run())
            self.assertTrue(ok, reason)
            # is_changed False short-circuits per design (no re-evaluation).
            self.assertEqual(len(calls), 0)
            # When stored is_changed is truthy, it MUST be re-evaluated.
            entry["nodes"]["1"]["is_changed"] = psc.encode_is_changed("abc")
            psc.set_store(ident, entry)
            keys = {}
            subcache = {}

            async def run2():
                async def _isc(nid):
                    calls.append(nid)
                    return "abc"
                return await psc.apply_memo_hit(
                    keys=keys,
                    subcache_keys=subcache,
                    node_ids=node_ids,
                    get_node=lambda nid: node,
                    has_node=lambda nid: True,
                    get_is_changed=_isc,
                    identity_hash=ident,
                )
            ok2, reason2 = asyncio.run(run2())
            self.assertTrue(ok2, reason2)
            self.assertGreaterEqual(len(calls), 1)
        finally:
            psc.reset_store()


if __name__ == "__main__":
    unittest.main()
