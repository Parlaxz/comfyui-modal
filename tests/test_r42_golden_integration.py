"""R42 Golden runtime bridge integration tests (CPU-only, hermetic).

Covers the current bridge contract:
- M-01 CLIP transport (byte-exact read_bytes contract)
- M-02 UNET payload adoption: materialize -> validate -> storage-bind
- M-03 VAE demand join + payload consumption
- generation determinism (content-derived, no UUID)
- module-level production helpers used by modal_app
"""

from __future__ import annotations

import json
import struct
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import torch  # noqa: E402

from comfymodal_runtime import golden_runtime_bridge as grb  # noqa: E402
from comfymodal_runtime.golden.contracts import (  # noqa: E402
    ForbiddenOverlapError,
    GoldenEvent,
    JoinDecision,
    LifecyclePhase,
    ModelRole,
    OwnershipState,
    ResourceDomain,
)
from comfymodal_runtime.golden.resource_scheduler import (  # noqa: E402
    ACT_CLIP_FORWARD,
    ACT_CLIP_GPU_CRITICAL,
    ACT_CLIP_QD_H2D,
    ACT_CLIP_QD_SOURCE,
    ACT_SAMPLING,
    ACT_VAE_QD,
    GoldenResourceScheduler,
)  # noqa: E402


def write_safetensors(path: Path, tensors_spec, fill_mod: int = 251):
    elem_sizes = {"F32": 4, "F16": 2, "BF16": 2, "I64": 8, "U8": 1}
    header = {}
    offset = 0
    payloads = []
    for name, dtype, shape in tensors_spec:
        nbytes = elem_sizes[dtype]
        for dim in shape:
            nbytes *= dim
        header[name] = {"dtype": dtype, "shape": list(shape), "data_offsets": [offset, offset + nbytes]}
        payloads.append(bytes((i % fill_mod) for i in range(nbytes)))
        offset += nbytes
    header_bytes = json.dumps(header).encode("utf-8")
    with open(path, "wb") as fh:
        fh.write(struct.pack("<Q", len(header_bytes)))
        fh.write(header_bytes)
        for payload in payloads:
            fh.write(payload)
    return path


def expected_state_dict(path: Path) -> dict:
    import safetensors.torch as sft

    with open(path, "rb") as fh:
        raw = fh.read()
    return sft.load(raw)


class _TinyDiffusion(torch.nn.Module):
    """Fake diffusion model whose state_dict names match a tiny safetensors."""

    def __init__(self, spec):
        super().__init__()
        for name, dtype, shape in spec:
            parts = name.split(".")
            parent = self
            for part in parts[:-1]:
                if not hasattr(parent, part):
                    parent.add_module(part, torch.nn.Module())
                parent = getattr(parent, part)
            tensor = torch.empty(shape, dtype=getattr(torch, {"F32": "float32", "F16": "float16"}[dtype]))
            parent.register_parameter(parts[-1], torch.nn.Parameter(tensor))


class TestLedgerBridgeSink(unittest.TestCase):
    def test_records_events_and_never_raises(self):
        sink = grb.LedgerBridgeSink()
        sink.emit("golden_test_event", value=1, nested={"a": object()})
        self.assertIn("golden_test_event", sink.names())


class TestMaterializeStateDict(unittest.TestCase):
    def test_round_trip_matches_safetensors_load(self):
        with tempfile.TemporaryDirectory() as td:
            path = write_safetensors(
                Path(td) / "m.safetensors",
                [("w0", "F32", (64, 64)), ("w1", "F32", (32, 128)), ("b0", "F32", (256,))],
            )
            ctx = grb.GoldenRunContext()
            manifest = ctx.build_manifest(str(path), ModelRole.CLIP)
            from comfymodal_runtime.golden.contracts import DestinationKind, DestinationPlan

            ordered_entries = sorted(manifest.layout.tensor_map, key=lambda t: t.abs_start)
            destination = DestinationPlan(
                kind=DestinationKind.PARAMETER_COPY_TARGET,
                buffers=[torch.empty(e.abs_end - e.abs_start, dtype=torch.uint8) for e in ordered_entries],
                buffer_bytes=[e.abs_end - e.abs_start for e in ordered_entries],
            )
            expected = expected_state_dict(path)
            with open(path, "rb") as fh:
                raw = fh.read()
            for entry, buf in zip(ordered_entries, destination.buffers):
                buf.copy_(torch.frombuffer(bytearray(raw[entry.abs_start : entry.abs_end]), dtype=torch.uint8))
            state_dict = grb.materialize_state_dict(destination, manifest.layout)
            self.assertEqual(set(state_dict), set(expected))
            for name in expected:
                self.assertTrue(torch.equal(state_dict[name], expected[name]), name)


class TestClipTransport(unittest.TestCase):
    def test_clip_golden_load_byte_exact(self):
        with tempfile.TemporaryDirectory() as td:
            path = write_safetensors(
                Path(td) / "clip.safetensors",
                [("tok.w", "F32", (32, 64)), ("tok.b", "F32", (64,))],
            )
            ctx = grb.GoldenRunContext()
            grb.set_current(ctx)
            try:
                ctx.on_restore_ready()
                ctx.note_role_source("clip", str(path))
                state_dict, metadata, diag = ctx.clip_golden_load(str(path))
                expected = expected_state_dict(path)
                self.assertEqual(set(state_dict), set(expected))
                for name in expected:
                    self.assertTrue(torch.equal(state_dict[name], expected[name]), name)
                self.assertEqual(diag["read_strategy"], "golden_qd4")
            finally:
                grb.clear_current()


class TestM02UnetAdoption(unittest.TestCase):
    def test_prepare_commit_payload_validate_bind(self):
        unet_spec = [("blk0.w", "F32", (16, 512)), ("blk1.w", "F32", (512, 256))]
        with tempfile.TemporaryDirectory() as td:
            clip_path = write_safetensors(Path(td) / "clip.safetensors", [("tok.w", "F32", (32, 64))])
            unet_path = write_safetensors(Path(td) / "unet.safetensors", unet_spec)
            ctx = grb.GoldenRunContext(join_timeout_s=30.0)
            grb.set_current(ctx)
            try:
                ctx.on_restore_ready()
                ctx.note_role_source("clip", str(clip_path))
                ctx.clip_golden_load(str(clip_path))
                ctx.note_role_source("unet", str(unet_path))
                ctx.on_clip_forward_start()
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline and ModelRole.UNET not in ctx.pipeline.prepared_sources:
                    time.sleep(0.01)
                # prepare done; release the forward-end barrier so commit runs
                ctx.on_clip_forward_end()
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline and not ctx._unet_committed.is_set():
                    time.sleep(0.01)
                self.assertTrue(ctx._unet_committed.is_set())
                decision, owner = ctx.adopt_unet(timeout_s=30.0)
                self.assertIn(str(getattr(decision, "value", decision)), ("already_ready", "joined"))
                sd = ctx.unet_payload(timeout_s=30.0)
                self.assertIsNotNone(sd)
                expected = expected_state_dict(unet_path)
                for name in expected:
                    self.assertTrue(torch.equal(sd[name].cpu(), expected[name]), name)

                # validate + bind into a fake diffusion module
                module = _TinyDiffusion(unet_spec)
                ok, vinfo = grb.GoldenRunContext.validate_adoption(sd, module)
                self.assertTrue(ok, vinfo["detail"])
                self.assertEqual(vinfo["detail"]["assigned_count"], len(expected))
                bind_info = grb.GoldenRunContext.bind_state_into_module(
                    vinfo["assigned_map"], module, None
                )
                self.assertEqual(bind_info["assigned_tensors"], len(expected))
                self.assertEqual(bind_info["device_move_ms"], 0.0)
                params = dict(module.named_parameters())
                for name in expected:
                    # storage-bind must be a zero-copy reference assignment:
                    # param.data wraps the SAME storage as the Golden tensor
                    # (.data returns a fresh wrapper per access, so identity
                    # is proven via data_ptr, not Python object identity).
                    self.assertEqual(params[name].data.data_ptr(), sd[name].data_ptr(), name)
                    self.assertTrue(torch.equal(params[name].data.cpu(), expected[name]), name)
            finally:
                grb.clear_current()

    def test_validate_adoption_rejects_mismatch(self):
        spec_a = [("w0", "F32", (16, 16))]
        spec_b = [("w0", "F32", (32, 16))]  # different shape
        with tempfile.TemporaryDirectory() as td:
            path_b = write_safetensors(Path(td) / "b.safetensors", spec_b)
            ctx = grb.GoldenRunContext()
            golden_sd = {name: torch.empty(shape) for name, _, shape in spec_a}
            module_b = _TinyDiffusion(spec_b)
            ok, vinfo = grb.GoldenRunContext.validate_adoption(golden_sd, module_b)
            self.assertFalse(ok)


class TestM03VaeJoin(unittest.TestCase):
    def test_vae_arm_join_payload(self):
        with tempfile.TemporaryDirectory() as td:
            vae_path = write_safetensors(Path(td) / "vae.safetensors", [("dec.w", "F32", (8, 8))])
            clip_path = write_safetensors(Path(td) / "clip.safetensors", [("tok.w", "F32", (32, 64))])
            unet_path = write_safetensors(
                Path(td) / "unet.safetensors",
                [("blk0.w", "F32", (16, 512)), ("blk1.w", "F32", (512, 256))],
            )
            ctx = grb.GoldenRunContext(join_timeout_s=30.0)
            grb.set_current(ctx)
            try:
                ctx.on_restore_ready()
                ctx.note_role_source("clip", str(clip_path))
                ctx.clip_golden_load(str(clip_path))
                # advance through UNET prepare/commit so SAMPLING is reachable
                ctx.note_role_source("unet", str(unet_path))
                ctx.on_clip_forward_start()
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline and ModelRole.UNET not in ctx.pipeline.prepared_sources:
                    time.sleep(0.01)
                ctx.on_clip_forward_end()
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline and not ctx._unet_committed.is_set():
                    time.sleep(0.01)
                self.assertTrue(ctx._unet_committed.is_set())
                ctx.note_role_source("vae", str(vae_path))
                ctx.on_first_sampler_step()
                # producer must register its owner BEFORE the load I/O
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline and ctx.pipeline.registry.get(ModelRole.VAE) is None:
                    time.sleep(0.01)
                owner = ctx.pipeline.registry.get(ModelRole.VAE)
                self.assertIsNotNone(owner, "VAE producer never registered an owner")
                decision, _owner = ctx.join_vae(30.0)
                self.assertIn(str(getattr(decision, "value", decision)), ("already_ready", "joined"))
                sd = ctx.vae_payload(timeout_s=30.0)
                self.assertIsNotNone(sd)
                expected = expected_state_dict(vae_path)
                for name in expected:
                    self.assertTrue(torch.equal(sd[name], expected[name]), name)
            finally:
                grb.clear_current()

    def test_join_vae_without_producer_degrades(self):
        ctx = grb.GoldenRunContext()
        decision, _owner = ctx.join_vae(0.05)
        dec = str(getattr(decision, "value", decision))
        self.assertNotIn(dec, ("already_ready", "joined"))


class TestOwnerLifecycleJoinability(unittest.TestCase):
    def test_unet_owner_joinable_during_prepare(self):
        unet_spec = [("blk0.w", "F32", (16, 512)), ("blk1.w", "F32", (512, 256))]
        with tempfile.TemporaryDirectory() as td:
            clip_path = write_safetensors(Path(td) / "clip.safetensors", [("tok.w", "F32", (32, 64))])
            unet_path = write_safetensors(Path(td) / "unet.safetensors", unet_spec)
            ctx = grb.GoldenRunContext(join_timeout_s=30.0)
            grb.set_current(ctx)
            try:
                ctx.on_restore_ready()
                ctx.note_role_source("clip", str(clip_path))
                ctx.clip_golden_load(str(clip_path))
                ctx.note_role_source("unet", str(unet_path))
                ctx.on_clip_forward_start()
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline and ctx.pipeline.registry.get(ModelRole.UNET) is None:
                    time.sleep(0.01)
                self.assertIsNotNone(ctx.pipeline.registry.get(ModelRole.UNET))
                outcome = {}

                def _joiner():
                    decision, _owner = ctx.pipeline.registry.join_or_adopt(ModelRole.UNET, 15.0)
                    outcome["decision"] = str(getattr(decision, "value", decision))

                t = threading.Thread(target=_joiner, daemon=True)
                t.start()
                time.sleep(0.1)  # let the joiner block on the owner signal
                ctx.on_clip_forward_end()
                t.join(timeout=20)
                self.assertEqual(outcome.get("decision"), "joined")
            finally:
                grb.clear_current()

    def test_run_role_load_publishes_failure_on_owner(self):
        class _FailingLoader:
            def load(self, *args, **kwargs):
                raise RuntimeError("boom")

        with tempfile.TemporaryDirectory() as td:
            clip_path = write_safetensors(Path(td) / "clip.safetensors", [("tok.w", "F32", (32, 64))])
            ctx = grb.GoldenRunContext(join_timeout_s=5.0)
            ctx.on_restore_ready()
            ctx.note_role_source("clip", str(clip_path))
            binding = ctx._role_binding("clip")
            self.assertIsNotNone(binding)
            with self.assertRaises(RuntimeError):
                ctx.pipeline.run_role_load(ModelRole.CLIP, _FailingLoader(), binding)
            owner = ctx.pipeline.registry.get(ModelRole.CLIP)
            self.assertIsNotNone(owner)
            self.assertIs(owner.state, OwnershipState.FAILED)
            decision, joined = ctx.pipeline.registry.join_or_adopt(ModelRole.CLIP, 1.0)
            self.assertIs(decision, JoinDecision.FAILED)
            self.assertIs(joined, owner)

    def test_scheduler_unarmed_vae_gate(self):
        s = GoldenResourceScheduler()
        s.begin_minimal_restore()
        s.transition(GoldenEvent.RESTORE_READY)
        # before the SAMPLING phase: unarmed VAE QD stays forbidden
        with self.assertRaises(ForbiddenOverlapError):
            s.acquire(ACT_VAE_QD, (ResourceDomain.STORAGE_HEAVY, ResourceDomain.H2D_HEAVY))
        s.acquire(ACT_CLIP_QD_SOURCE, (ResourceDomain.STORAGE_HEAVY,))
        s.acquire(ACT_CLIP_QD_H2D, (ResourceDomain.H2D_HEAVY,))
        s.transition(GoldenEvent.CLIP_DEVICE_READY)
        fwd = s.acquire(ACT_CLIP_FORWARD, (ResourceDomain.GPU_COMPUTE,))
        crit = s.acquire(ACT_CLIP_GPU_CRITICAL, (ResourceDomain.GPU_MUTATION,))
        s.transition(GoldenEvent.CLIP_STORAGE_RELEASED)
        s.release(fwd)
        s.release(crit)
        s.transition(GoldenEvent.CLIP_GPU_CRITICAL_DONE)
        s.transition(GoldenEvent.UNET_DEVICE_READY)
        self.assertEqual(s.phase, LifecyclePhase.SAMPLING)
        # SAMPLING phase entered but sampling not started: unarmed VAE QD allowed
        grant = s.acquire(ACT_VAE_QD, (ResourceDomain.STORAGE_HEAVY, ResourceDomain.H2D_HEAVY))
        s.release(grant)
        # once sampling starts (grant active), unarmed acquisition is forbidden again
        samp = s.acquire(ACT_SAMPLING, (ResourceDomain.GPU_COMPUTE,))
        s.transition(GoldenEvent.SAMPLING_STARTED)
        with self.assertRaises(ForbiddenOverlapError):
            s.acquire(ACT_VAE_QD, (ResourceDomain.STORAGE_HEAVY, ResourceDomain.H2D_HEAVY))
        # armed path still works
        s.transition(GoldenEvent.FIRST_SAMPLER_STEP_PROVEN)
        armed = s.acquire(ACT_VAE_QD, (ResourceDomain.STORAGE_HEAVY, ResourceDomain.H2D_HEAVY))
        s.release(armed)


class _CountingLoader:
    """Proxy counting producer `load` calls (one call == one physical read pass)."""

    def __init__(self, inner):
        self._inner = inner
        self.load_calls = 0

    def load(self, *args, **kwargs):
        self.load_calls += 1
        return self._inner.load(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._inner, name)


class TestVaeDemandLoad(unittest.TestCase):
    def test_vae_demand_load_inline_and_join(self):
        with tempfile.TemporaryDirectory() as td:
            clip_path = write_safetensors(Path(td) / "clip.safetensors", [("tok.w", "F32", (32, 64))])
            unet_path = write_safetensors(
                Path(td) / "unet.safetensors",
                [("blk0.w", "F32", (16, 512)), ("blk1.w", "F32", (512, 256))],
            )
            vae_path = write_safetensors(Path(td) / "vae.safetensors", [("dec.w", "F32", (8, 8))])
            ctx = grb.GoldenRunContext(join_timeout_s=30.0)
            grb.set_current(ctx)
            try:
                # walk to the SAMPLING phase (unarmed pre-sampling-start window)
                ctx.on_restore_ready()
                ctx.note_role_source("clip", str(clip_path))
                ctx.clip_golden_load(str(clip_path))
                ctx.note_role_source("unet", str(unet_path))
                ctx.on_clip_forward_start()
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline and ModelRole.UNET not in ctx.pipeline.prepared_sources:
                    time.sleep(0.01)
                ctx.on_clip_forward_end()
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline and not ctx._unet_committed.is_set():
                    time.sleep(0.01)
                self.assertTrue(ctx._unet_committed.is_set())
                counting = _CountingLoader(ctx.get_loader())
                ctx._loader = counting

                out = ctx.vae_demand_load(str(vae_path))
                self.assertIsNotNone(out)
                sd, meta = out
                expected = expected_state_dict(vae_path)
                for name in expected:
                    self.assertTrue(torch.equal(sd[name], expected[name]), name)
                self.assertEqual(counting.load_calls, 1)
                self.assertIsNotNone(ctx.pipeline.registry.get(ModelRole.VAE))
                self.assertTrue(ctx._vae_committed.is_set())

                # second demand JOINS the live owner: no second physical read
                out2 = ctx.vae_demand_load(str(vae_path))
                self.assertIsNotNone(out2)
                self.assertEqual(counting.load_calls, 1)

                # retry path: force exactly one ForbiddenOverlapError denial
                ctx.pipeline.registry.clear_role(ModelRole.VAE)
                orig_acquire = ctx.scheduler.acquire
                state = {"deny": 1}

                def flaky_acquire(label, domains):
                    if state["deny"] > 0 and label == "vae_qd":
                        state["deny"] -= 1
                        raise ForbiddenOverlapError("forced for test")
                    return orig_acquire(label, domains)

                ctx.scheduler.acquire = flaky_acquire
                try:
                    out3 = ctx.vae_demand_load(str(vae_path))
                finally:
                    ctx.scheduler.acquire = orig_acquire
                self.assertIsNotNone(out3)
                sd3, _meta3 = out3
                for name in expected:
                    self.assertTrue(torch.equal(sd3[name], expected[name]), name)
                self.assertEqual(counting.load_calls, 2)
            finally:
                grb.clear_current()


class TestGenerationDeterminism(unittest.TestCase):
    def test_content_derived_generation_is_deterministic(self):
        from comfymodal_runtime import runtime_generation as rg

        manifest = {
            "a.json": {"present": True, "sha256": "aa" * 32},
            "b.bin": {"present": True, "sha256": "bb" * 32},
        }
        g1 = rg._content_derived_generation(manifest)
        g2 = rg._content_derived_generation(dict(reversed(list(manifest.items()))))
        self.assertEqual(g1, g2)
        self.assertNotEqual(g1, rg._content_derived_generation({"x": {"present": False}}))

    def test_marker_writer_uses_content_generation_when_absent(self):
        from comfymodal_runtime import runtime_generation as rg

        with tempfile.TemporaryDirectory() as td:
            manifest = {"f": {"present": True, "sha256": "cc" * 32}}
            gen1 = rg.write_runtime_state_generation_marker(td, files_manifest=manifest)
            gen2 = rg.write_runtime_state_generation_marker(td, files_manifest=manifest)
            self.assertEqual(gen1, gen2)
            self.assertEqual(gen1, rg._content_derived_generation(manifest))


class TestModuleLevelProductionHelpers(unittest.TestCase):
    def test_map_degradation_to_reasons(self):
        self.assertEqual(
            grb.map_degradation_to_reasons(["golden_qd_fallback:clip"]),
            ["loader_fallback_clip"],
        )

    def test_build_config_truth_block(self):
        from comfymodal_runtime import config_authority as ca

        rc = ca.resolve({"COMFYMODAL_GOLDEN_PIPELINE": "1"})
        block = grb.build_config_truth_block(rc)
        names = {row["name"] for row in block["controls"]}
        self.assertIn("COMFYMODAL_GOLDEN_PIPELINE", names)

    def test_golden_enabled_reads_authority(self):
        from comfymodal_runtime import config_authority as ca

        self.assertTrue(grb.golden_enabled(ca.resolve({"COMFYMODAL_GOLDEN_PIPELINE": "1"})))
        self.assertFalse(grb.golden_enabled(ca.resolve({})))


class TestSourcePinsWiring(unittest.TestCase):
    def _read(self, rel: str) -> str:
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_comfyapp_routes_clip_through_bridge(self):
        src = self._read("comfyapp.py")
        self.assertIn("golden_runtime_bridge", src)
        self.assertIn("clip_golden_load", src)

    def test_modal_app_seeds_and_assembles_golden(self):
        src = self._read("comfymodal_runtime/modal_app.py")
        self.assertIn("_r42_golden_ctx", src)
        self.assertIn("build_config_truth_block", src)

    def test_forward_boundaries_hooked(self):
        src = self._read("comfymodal_runtime/clip_forward_forensics.py")
        self.assertIn("on_clip_forward_start", src)
        self.assertIn("on_clip_forward_end", src)

    def test_sampler_step_hooked(self):
        src = self._read("comfymodal_runtime/model_preload.py")
        self.assertIn("on_first_sampler_step", src)

    def test_m02_adoption_wired_into_load_models_gpu_wrapper(self):
        src = self._read("comfymodal_runtime/model_preload.py")
        self.assertIn("_r42_golden_unet_adoption", src)
        self.assertIn("unet_payload", src)

    def test_m03_adoption_wired_into_vae_demand(self):
        src = self._read("comfymodal_runtime/model_preload.py")
        self.assertIn("ensure_vae_load_started", src)
        self.assertIn("vae_payload", src)


class TestSchedulerUnarmedVaeWindow(unittest.TestCase):
    """R42 Phase 2: unarmed VAE QD window covers post-CLIP-critical phases."""

    def _walk_to_unet_commit(self, s):
        s.begin_minimal_restore()
        s.transition(GoldenEvent.RESTORE_READY)
        s.acquire(ACT_CLIP_QD_SOURCE, (ResourceDomain.STORAGE_HEAVY,))
        s.acquire(ACT_CLIP_QD_H2D, (ResourceDomain.H2D_HEAVY,))
        s.transition(GoldenEvent.CLIP_DEVICE_READY)
        fwd = s.acquire(ACT_CLIP_FORWARD, (ResourceDomain.GPU_COMPUTE,))
        crit = s.acquire(ACT_CLIP_GPU_CRITICAL, (ResourceDomain.GPU_MUTATION,))
        s.transition(GoldenEvent.CLIP_STORAGE_RELEASED)
        s.release(fwd)
        s.release(crit)
        s.transition(GoldenEvent.CLIP_GPU_CRITICAL_DONE)
        self.assertEqual(s.phase, LifecyclePhase.UNET_COMMIT)

    def test_unarmed_vae_allowed_in_unet_commit_window(self):
        s = GoldenResourceScheduler()
        self._walk_to_unet_commit(s)
        grant = s.acquire(ACT_VAE_QD, (ResourceDomain.STORAGE_HEAVY, ResourceDomain.H2D_HEAVY))
        s.release(grant)
        s.transition(GoldenEvent.UNET_DEVICE_READY)
        self.assertEqual(s.phase, LifecyclePhase.SAMPLING)

    def test_unarmed_vae_still_denied_in_clip_phases(self):
        s = GoldenResourceScheduler()
        s.begin_minimal_restore()
        s.transition(GoldenEvent.RESTORE_READY)
        with self.assertRaises(ForbiddenOverlapError):
            s.acquire(ACT_VAE_QD, (ResourceDomain.STORAGE_HEAVY, ResourceDomain.H2D_HEAVY))


class TestStageCReloadDecisionRecording(unittest.TestCase):
    """R42 Stage C: reload-invoked decisions are recorded for status merge."""

    def test_record_and_read_roundtrip_bounded(self):
        from comfymodal_runtime import runtime_bootstrap as rb

        before = len(rb.last_restore_reload_decisions())
        rb._record_restore_reload_decision(
            "runtime_state",
            decision="reloaded_generation_mismatch",
            reason="generation_mismatch",
            callback_called=True,
            check_ms=1.5,
        )
        rb._record_restore_reload_decision(
            "models",
            decision="skipped_generation_match",
            reason="exact_match",
            callback_called=False,
            check_ms=0.2,
        )
        decisions = rb.last_restore_reload_decisions()
        self.assertEqual(len(decisions), before + 2)
        tail = decisions[-2:]
        self.assertEqual(tail[0]["stage"], "runtime_state")
        self.assertTrue(tail[0]["callback_called"])
        self.assertEqual(tail[1]["decision"], "skipped_generation_match")
        self.assertFalse(tail[1]["callback_called"])
        # merge contract: callback_called=True maps to the canonical reason
        expected = {
            "runtime_state": "runtime_state_generation_reload",
            "models": "models_volume_generation_reload",
        }
        reasons = [
            expected[d["stage"]]
            for d in rb.last_restore_reload_decisions()
            if d.get("callback_called") and d.get("stage") in expected
        ]
        self.assertIn("runtime_state_generation_reload", reasons)
        self.assertNotIn("models_volume_generation_reload", reasons)

    def test_recorder_never_raises_on_bad_input(self):
        from comfymodal_runtime import runtime_bootstrap as rb

        rb._record_restore_reload_decision(
            "x", decision="d", reason="r", callback_called=False, check_ms=0.0
        )
        self.assertIsInstance(rb.last_restore_reload_decisions(), list)


class TestGoldenUnetVerifier(unittest.TestCase):
    """_r42_golden_unet_adoption must verify without skipping native load."""

    def test_returns_false_and_records_payload_absent_without_owner(self):
        from comfymodal_runtime import model_preload as mp

        with tempfile.TemporaryDirectory() as td:
            clip_path = write_safetensors(Path(td) / "clip.safetensors", [("tok.w", "F32", (32, 64))])
            ctx = grb.GoldenRunContext(join_timeout_s=30.0)
            grb.set_current(ctx)
            try:
                ctx.on_restore_ready()
                ctx.note_role_source("clip", str(clip_path))
                ctx.clip_golden_load(str(clip_path))

                class _DM:
                    pass

                class _Inner:
                    diffusion_model = _DM()

                class _Patcher:
                    model = _Inner()

                result = mp._r42_golden_unet_adoption([_Patcher()])
                self.assertFalse(result)
                self.assertEqual(
                    ctx.telemetry.get("model_io_uniqueness", {}).get("unet", {}).get("verify"),
                    "payload_absent",
                )
            finally:
                grb.clear_current()


class TestTorchFileVaeBranch(unittest.TestCase):
    """load_torch_file golden branch serves the VAE payload; others pass through."""

    def test_vae_path_served_from_golden_owner(self):
        from comfymodal_runtime.golden.contracts import ModelRole as MR

        with tempfile.TemporaryDirectory() as td:
            clip_path = write_safetensors(Path(td) / "clip.safetensors", [("tok.w", "F32", (32, 64))])
            unet_path = write_safetensors(
                Path(td) / "unet.safetensors",
                [("blk0.w", "F32", (16, 512)), ("blk1.w", "F32", (512, 256))],
            )
            vae_path = write_safetensors(Path(td) / "vae.safetensors", [("dec.w", "F32", (8, 8))])
            ctx = grb.GoldenRunContext(join_timeout_s=30.0)
            grb.set_current(ctx)
            try:
                ctx.on_restore_ready()
                ctx.note_role_source("clip", str(clip_path))
                ctx.clip_golden_load(str(clip_path))
                ctx.note_role_source("unet", str(unet_path))
                ctx.on_clip_forward_start()
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline and MR.UNET not in ctx.pipeline.prepared_sources:
                    time.sleep(0.01)
                ctx.on_clip_forward_end()
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline and not ctx._unet_committed.is_set():
                    time.sleep(0.01)
                counting = _CountingLoader(ctx.get_loader())
                ctx._loader = counting

                out = ctx.vae_demand_load(str(vae_path))
                self.assertIsNotNone(out)
                self.assertEqual(counting.load_calls, 1)

                # fake folder_paths so the branch resolves the vae role
                class _FakeFP:
                    @staticmethod
                    def get_full_path(folder, name):
                        if folder == "vae" and name == Path(str(vae_path)).name:
                            return str(vae_path)
                        return None

                saved = {k: v for k, v in sys.modules.items() if k == "folder_paths"}
                sys.modules["folder_paths"] = _FakeFP
                try:
                    from comfymodal_runtime import model_preload as mp

                    calls = {"n": 0}

                    def _original(ckpt, *a, **k):
                        calls["n"] += 1
                        return {"native": True}

                    wrapped = mp._make_torch_file_wrapper(_original)
                    got = wrapped(str(vae_path), return_metadata=True)
                    self.assertEqual(calls["n"], 0)
                    self.assertIsInstance(got, tuple)
                    sd, meta = got
                    expected = expected_state_dict(vae_path)
                    for name in expected:
                        self.assertTrue(torch.equal(sd[name], expected[name]), name)
                    # non-vae path passes through to original
                    got2 = wrapped(str(unet_path))
                    self.assertEqual(calls["n"], 1)
                    self.assertEqual(got2, {"native": True})
                finally:
                    if saved:
                        sys.modules["folder_paths"] = saved["folder_paths"]
                    else:
                        sys.modules.pop("folder_paths", None)
            finally:
                grb.clear_current()


if __name__ == "__main__":
    unittest.main()
