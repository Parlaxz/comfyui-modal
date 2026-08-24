"""R44I2 tests: authoritative DIRECT sampler boundary telemetry.

Local, CPU-only, no Modal/network/deploy.  Covers R44I2 spec §13 items A–I:

A. exact ModelPatcher/model_options cloning used by the RES4LYF/guider path
B. demonstrate the old H2 wrapper attachment gets LOST (reproduces the
   remote R44H3 failure deterministically)
C. direct sampling_start seam survives regardless of patcher clone
D. first-eval hook executes on the first denoiser call
E. only ONE first-eval recording per request
F. per-step ticks unchanged
G. tail telemetry schema unchanged
H. no explicit CUDA sync introduced anywhere in the module
I. feature disabled = native behavior untouched

Root cause being locked in (source-proven): comfy's ``CFGGuider.sample``
clones ``model_options`` at entry (samplers.py:1304) BEFORE the sampler-
internal ``load_models_gpu`` runs (sampler_helpers.py:201), and the
SAMPLER_SAMPLE wrapper lookup reads ONLY the clone chain (samplers.py:
1220-1227).  H2's late install into ``model_patcher.model_options`` could
therefore never execute for the live invocation.
"""

import importlib
import os
import sys
import time
import unittest

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
# Defensive: pin this worktree's package (mirrors test_r44h2 pattern).
for _name in [k for k in list(sys.modules)
              if k == "comfymodal_runtime" or k.startswith("comfymodal_runtime.")]:
    _mod = sys.modules.get(_name)
    _path0 = getattr(getattr(_mod, "__path__", None), "__getitem__", lambda *_: "")(0)
    if _path0 and not os.path.normcase(_path0).startswith(os.path.normcase(_HERE)):
        del sys.modules[_name]

from comfymodal_runtime import sampler_telemetry as st  # noqa: E402


def _cleanup():
    """Reset request state, then restore class/global patches.

    Order matters: ``reset_request`` auto-installs the direct boundaries
    (production trigger), so the REMOVE must come last or every cleanup
    would leave wrappers installed and break class-identity assertions.
    """
    try:
        st.reset_request("")
    except Exception:
        pass
    try:
        st.remove_direct_boundaries()
    except Exception:
        pass
    try:
        st._TELEMETRY._remove_subtiming_patches()
    except Exception:
        pass


# ── A + B: reproduce the H2 wrapper loss with real clone semantics ────────


class H2WrapperLossReproductionTest(unittest.TestCase):
    """The lmg-seam install lands AFTER the guider's model_options clone."""

    def setUp(self):
        try:
            self._pe = importlib.import_module("comfy.patcher_extension")
        except Exception as exc:  # pragma: no cover - stdlib-only module
            self.skipTest(f"comfy.patcher_extension unavailable: {exc}")

    def _clone(self, options):
        """Use comfy's own clone helper when importable (torch present)."""
        try:
            cmp_mod = importlib.import_module("comfy.model_patcher")
            return cmp_mod.create_model_options_clone(options)
        except Exception:
            return self._pe.copy_nested_dicts(options)

    def test_late_install_never_reaches_sampler_sample_lookup(self):
        pe = self._pe
        key = "comfymodal_v2_sampling_timing"
        marker = lambda executor, *a, **k: executor(*a, **k)  # noqa: E731

        # Fresh patcher model_options for this request — no wrapper yet.
        patcher_model_options = {}

        # (1) CFGGuider.sample ENTRY clones model_options BEFORE anything
        #     installs (samplers.py:1303-1304).
        guider_options = self._clone(patcher_model_options)

        # (2) The H2 lmg seam fires INSIDE outer_sample -> prepare_sampling
        #     and installs into the ORIGINAL patcher dict — successfully.
        pe.add_wrapper_with_key(
            pe.WrappersMP.SAMPLER_SAMPLE, key, marker,
            patcher_model_options, is_model_options=True)
        self.assertTrue(pe.get_wrappers_with_key(
            pe.WrappersMP.SAMPLER_SAMPLE, key,
            patcher_model_options, is_model_options=True))

        # (3) inner_sample clones the GUIDER's options (samplers.py:1220)
        #     and reads SAMPLER_SAMPLE wrappers from that clone (:1227).
        extra_model_options = self._clone(guider_options)
        found = pe.get_wrappers_with_key(
            pe.WrappersMP.SAMPLER_SAMPLE, key,
            extra_model_options, is_model_options=True)

        # Install succeeded on the original, but the live invocation's
        # lookup sees an EMPTY chain -> the wrapper can never execute.
        self.assertEqual(found, [])
        self.assertTrue(pe.get_wrappers_with_key(
            pe.WrappersMP.SAMPLER_SAMPLE, key,
            patcher_model_options, is_model_options=True))


# ── C: direct sampling_start seam is clone-independent ────────────────────


class DirectSamplingStartSeamTest(unittest.TestCase):

    def setUp(self):
        _cleanup()
        st.reset_request("r44i2-ss")

    def tearDown(self):
        _cleanup()

    @staticmethod
    def _make_guider(orig_sample):
        class _FakeGuider:
            def sample(self, noise, latent_image, sampler, sigmas,
                       denoise_mask=None, callback=None, disable_pbar=False,
                       seed=None):
                return ("sampled", noise, latent_image, sigmas)

        _FakeGuider.sample = st.build_direct_sampling_start_wrapper(orig_sample)
        return _FakeGuider()

    def test_seam_records_and_passes_through(self):
        calls = []

        def orig_sample(self, noise, latent_image, sampler, sigmas,
                        denoise_mask=None, callback=None, disable_pbar=False,
                        seed=None):
            calls.append((noise, latent_image, tuple(sigmas)))
            return "sampled"

        g = self._make_guider(orig_sample)
        result = g.sample("noise", "latent", "sampler", [0.1] * 5)
        self.assertEqual(result, "sampled")
        self.assertEqual(len(calls), 1)

        snap = st.snapshot()
        self.assertGreater(snap["sampling_start_mono_ns"], 0)
        self.assertTrue(snap["ss_hook_invoked"])
        self.assertEqual(snap["steps"], 4)
        mono, src = st.resolve_sampling_start(None, None)
        self.assertEqual(src, "authoritative_direct_sampler_boundary")
        self.assertGreater(mono, 0)

    def test_idempotent_first_boundary_wins(self):
        g = self._make_guider(lambda self, *a, **k: "ok")
        g.sample("n", "l", "s", [1, 2, 3])
        first = st.snapshot()["sampling_start_mono_ns"]
        time.sleep(0.001)
        g.sample("n", "l", "s", [1, 2, 3])
        second = st.snapshot()["sampling_start_mono_ns"]
        self.assertEqual(first, second)

    def test_inactive_request_records_nothing(self):
        st.reset_request("")  # request_id empty -> gate closed
        g = self._make_guider(lambda self, *a, **k: "ok")
        g.sample("n", "l", "s", [1, 2])
        snap = st.snapshot()
        self.assertEqual(snap["sampling_start_mono_ns"], 0)
        self.assertFalse(snap["ss_hook_invoked"])

    def test_seam_survives_full_clone_dance(self):
        """C: recording happens even around the exact H2 clone sequence."""
        try:
            pe = importlib.import_module("comfy.patcher_extension")
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"comfy.patcher_extension unavailable: {exc}")
        g = self._make_guider(lambda self, *a, **k: "ok")
        mo = {}
        clone1 = pe.copy_nested_dicts(mo)  # sample-entry clone
        pe.add_wrapper_with_key(pe.WrappersMP.SAMPLER_SAMPLE, "k",
                                lambda e, *a, **kw: e(*a, **kw), mo,
                                is_model_options=True)  # late lmg install
        clone2 = pe.copy_nested_dicts(clone1)  # inner_sample clone
        g.sample("n", "l", "s", [1, 2, 3])
        self.assertGreater(st.snapshot()["sampling_start_mono_ns"], 0)
        self.assertIsNot(clone2, mo)


# ── D + E: first-eval boundary ────────────────────────────────────────────


class DirectFirstEvalSeamTest(unittest.TestCase):

    def setUp(self):
        _cleanup()
        st.reset_request("r44i2-fe")

    def tearDown(self):
        _cleanup()

    @staticmethod
    def _make_model(orig_apply):
        class _FakeModel:
            def apply_model(self, x, t, **kwargs):
                return ("eval", x, t)

        _FakeModel.apply_model = st.build_direct_first_eval_wrapper(orig_apply)
        return _FakeModel()

    def test_first_eval_recorded_once_and_passthrough(self):
        results = []
        m = self._make_model(lambda self, x, t, **kw: ("eval", x, t))
        results.append(m.apply_model("x1", "t1"))
        first = st.snapshot()["first_eval_mono_ns"]
        results.append(m.apply_model("x2", "t2"))
        second = st.snapshot()["first_eval_mono_ns"]

        self.assertEqual([r[0] for r in results], ["eval", "eval"])
        self.assertEqual(results[0][1], "x1")
        self.assertEqual(results[1][1], "x2")
        self.assertGreater(first, 0)
        self.assertEqual(first, second)  # E: exactly one recording
        self.assertTrue(st.snapshot()["fe_hook_invoked"])
        self.assertLessEqual(first, time.monotonic_ns())

    def test_inactive_request_records_nothing(self):
        st.reset_request("")
        m = self._make_model(lambda self, x, t, **kw: ("eval", x, t))
        m.apply_model("x", "t")
        snap = st.snapshot()
        self.assertEqual(snap["first_eval_mono_ns"], 0)
        self.assertFalse(snap["fe_hook_invoked"])


# ── real class-level install/remove integration ───────────────────────────


class RealClassInstallRemoveTest(unittest.TestCase):

    def setUp(self):
        try:
            self._cs = importlib.import_module("comfy.samplers")
            self._cmb = importlib.import_module("comfy.model_base")
        except Exception as exc:
            self.skipTest(f"comfy runtime classes unavailable: {exc}")
        self._orig_sample = self._cs.CFGGuider.sample
        self._orig_apply = self._cmb.BaseModel.apply_model
        _cleanup()

    def tearDown(self):
        try:
            st.remove_direct_boundaries()
        finally:
            self._cs.CFGGuider.sample = self._orig_sample
            self._cmb.BaseModel.apply_model = self._orig_apply
        _cleanup()

    def test_install_wraps_remove_restores_exactly(self):
        stub_sample = lambda self, *a, **k: "stub-sample"  # noqa: E731
        stub_apply = lambda self, *a, **k: "stub-apply"  # noqa: E731
        self._cs.CFGGuider.sample = stub_sample
        self._cmb.BaseModel.apply_model = stub_apply
        # Clear install state left by setUp's auto-install trigger so the
        # install below wraps the STUBS (deterministic identity assertions).
        st.remove_direct_boundaries()

        status = st.install_direct_boundaries()
        self.assertEqual(status, {"sampling_start": True, "first_eval": True})
        self.assertIsNot(self._cs.CFGGuider.sample, stub_sample)
        self.assertIsNot(self._cmb.BaseModel.apply_model, stub_apply)
        self.assertTrue(st.snapshot()["ss_hook_installed"])
        self.assertTrue(st.snapshot()["fe_hook_installed"])

        # Idempotent install never double-wraps.
        status2 = st.install_direct_boundaries()
        self.assertEqual(status2, {"sampling_start": True, "first_eval": True})

        # Drive a dummy instance through the patched class methods with an
        # active request: recording happens, orig (the stub) still returns.
        st.reset_request("r44i2-real")

        class _DummyG(self._cs.CFGGuider):
            def __init__(self):  # skip real CFGGuider init
                pass

        class _DummyM(self._cmb.BaseModel):
            def __init__(self):  # skip real BaseModel init
                pass

        self.assertEqual(_DummyG().sample("n", "lat", "smp", [1, 2, 3]),
                         "stub-sample")
        self.assertEqual(_DummyM().apply_model("x", "t"), "stub-apply")
        snap = st.snapshot()
        self.assertGreater(snap["sampling_start_mono_ns"], 0)
        self.assertGreater(snap["first_eval_mono_ns"], 0)
        mono, src = st.resolve_sampling_start(None, None)
        self.assertEqual(src, "authoritative_direct_sampler_boundary")

        st.remove_direct_boundaries()
        self.assertIs(self._cs.CFGGuider.sample, stub_sample)
        self.assertIs(self._cmb.BaseModel.apply_model, stub_apply)
        st.remove_direct_boundaries()  # idempotent


# ── §11: hook_installed / hook_invoked / persisted distinction ────────────


class _RecordingTrace:
    """FakeTrace that ALSO exposes .events so dedup guards see emissions."""

    def __init__(self):
        self.events = []
        self.emitted = []

    def emit(self, name, phase=None, metadata=None):
        meta = dict(metadata or {})
        self.events.append({"name": name, "metadata": meta})
        self.emitted.append((name, meta))
        return type("E", (), {"monotonic_ns": 0, "wall_unix_ns": 0})()


class StatusEventTest(unittest.TestCase):

    def tearDown(self):
        _cleanup()

    def test_success_scenario_reports_all_true(self):
        try:
            st.install_direct_boundaries()
        except Exception:
            pass  # comfy missing: installed flags then stay False; still valid
        st.reset_request("r44i2-status-ok")
        st._TELEMETRY.node_entry_mono_ns = time.monotonic_ns() - 10_000_000
        st._TELEMETRY.node_id = "1242"
        st._TELEMETRY.node_class = "ClownsharKSampler_Beta"

        class _G:
            def sample(self, noise, latent_image, sampler, sigmas, **kw):
                return "ok"

        _G.sample = st.build_direct_sampling_start_wrapper(_G.__dict__["sample"])
        _G().sample("n", "lat", "smp", [1] * 9)

        class _M:
            def apply_model(self, x, t, **kw):
                return "eval"

        _M.apply_model = st.build_direct_first_eval_wrapper(_M.__dict__["apply_model"])
        _M().apply_model("x", "t")

        st.note_progress_tick(step=0, source="wrapper_callback")
        st.finish_sampler_tail(time.perf_counter_ns() + 1_000_000,
                               time.monotonic_ns() + 1_000_000)

        ft = _RecordingTrace()
        n = st.emit_durable_events(ft)
        names = [x[0] for x in ft.emitted]
        self.assertEqual(names[-1], "sampler_telemetry_status")
        status = ft.emitted[-1][1]
        self.assertTrue(status["sampling_start_hook_installed"])
        self.assertTrue(status["sampling_start_hook_invoked"])
        self.assertTrue(status["sampling_start_persisted"])
        self.assertTrue(status["first_eval_hook_invoked"])
        self.assertTrue(status["first_eval_persisted"])
        self.assertIn("first_eval_hook_installed", status)
        self.assertEqual(status["tick_count"], 1)
        self.assertTrue(status["tail_present"])
        # deferred authoritative sampling_start carries the TRUE stamp
        self.assertIn("sampling_start", names)
        ds = dict(ft.emitted)["sampling_start"]
        self.assertEqual(ds["emission"], st.DEFERRED_EMISSION_FLAG)
        self.assertGreater(int(ds["mono_ns"]), 0)
        self.assertEqual(ds["source"], st.DIRECT_SAMPLING_START_SOURCE)
        self.assertGreaterEqual(n, 6)

    def test_opaque_gate_scenario_reports_missing(self):
        """Exactly the signal that would have exposed the H2 remote failure."""
        st.reset_request("r44i2-status-none")  # hooks may be installed; nothing invoked
        ft = _RecordingTrace()
        n = st.emit_durable_events(ft)
        names = [x[0] for x in ft.emitted]
        self.assertEqual(names.count("sampler_telemetry_status"), 1)
        status = dict(ft.emitted)["sampler_telemetry_status"]
        self.assertFalse(status["sampling_start_persisted"])
        self.assertFalse(status["sampling_start_hook_invoked"])
        self.assertFalse(status["first_eval_persisted"])
        self.assertFalse(status["first_eval_hook_invoked"])
        self.assertEqual(n, 1)  # nothing else had evidence

    def test_deferred_sampling_start_skipped_when_trace_has_one(self):
        st.reset_request("r44i2-dedup")
        st.note_sampling_start(123456, 0, node_id="n", steps=2)
        ft = _RecordingTrace()
        ft.events.append({"name": "sampling_start",
                          "metadata": {"mono_ns": 999}})
        st.emit_durable_events(ft)
        names = [x[0] for x in ft.emitted]
        self.assertNotIn("sampling_start", names)  # deterministic dedup
        self.assertIn("sampler_telemetry_status", names)


# ── H: no GPU synchronization introduced ──────────────────────────────────


class NoGpuSyncTest(unittest.TestCase):

    def test_module_source_has_no_cuda_sync_or_cache_clears(self):
        """AST scan: no synchronize/empty_cache/set_device CALLS anywhere.

        A raw substring scan would false-positive on the module docstring,
        which mentions these operations as things it deliberately avoids.
        """
        import ast

        path = os.path.join(_HERE, "comfymodal_runtime", "sampler_telemetry.py")
        with open(path, "r", encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=path)
        forbidden = {"synchronize", "empty_cache", "set_device"}
        hits = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr in forbidden:
                    hits.append(f"line {node.lineno}: .{func.attr}()")
                elif isinstance(func, ast.Name) and func.id in forbidden:
                    hits.append(f"line {node.lineno}: {func.id}()")
        self.assertEqual(hits, [])


class DeferredTimestampRoundTripTest(unittest.TestCase):
    """Consumer normalization: a real artifact file's deferred events must
    resolve to their TRUE metadata stamps (not the late emit-time stamp)."""

    def test_load_run_artifacts_honors_deferred_boundary_flag(self):
        try:
            from comfymodal_runtime import dynamic_gantt as dg
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"dynamic_gantt unavailable: {exc}")
        import json
        import tempfile

        true_ss = 226_520_000_000
        true_fe = 227_600_000_000
        late_emit = 300_000_000_000  # what emit-time stamping would produce
        doc = {
            "request_id": "r44i2-roundtrip",
            "result": {"trace": {"events": [
                {"name": "sampling_start", "monotonic_ns": late_emit,
                 "wall_unix_ns": 0,
                 "metadata": {"mono_ns": true_ss,
                              "source": st.DIRECT_SAMPLING_START_SOURCE,
                              "emission": st.DEFERRED_EMISSION_FLAG}},
                {"name": "sampler_first_eval_start", "monotonic_ns": late_emit + 1,
                 "wall_unix_ns": 0,
                 "metadata": {"mono_ns": true_fe, "step_index": 0,
                              "emission": st.DEFERRED_EMISSION_FLAG}},
            ]}},
            "waterfall": {"stages": []},
        }
        tmpdir = tempfile.mkdtemp(prefix="r44i2_roundtrip_")
        with open(os.path.join(tmpdir, "run_0.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(doc, fh)
        payload = dg.load_run_artifacts(tmpdir)
        by_name = {e["name"]: e for e in payload.raw["events"]}
        self.assertEqual(by_name["sampling_start"]["mono_ns"], true_ss)
        self.assertEqual(
            by_name["sampler_first_eval_start"]["mono_ns"], true_fe)


# ── F + G: existing tick/tail telemetry unchanged ─────────────────────────


class ExistingTelemetryUnchangedTest(unittest.TestCase):

    def setUp(self):
        _cleanup()
        st.reset_request("r44i2-fg")

    def tearDown(self):
        _cleanup()

    def test_ticks_and_tail_schema_unchanged_with_seams_installed(self):
        st.install_direct_boundaries()
        st.note_progress_tick(step=0, source="wrapper_callback")
        snap = st.snapshot()
        self.assertEqual(snap["tick_count"], 1)
        self.assertEqual(snap["ticks"][0]["step"], 0)
        self.assertEqual(snap["ticks"][0]["source"], "wrapper_callback")

        tail = st.finish_sampler_tail(time.perf_counter_ns() + 1_000_000,
                                      time.monotonic_ns() + 1_000_000)
        for key in ("start_mono_ns", "end_mono_ns", "wall_ms",
                    "gc_collect_ms", "gc_collect_count",
                    "state_info_deepcopy_ms", "state_info_deepcopy_count",
                    "cpu_transfer_wall_ms", "cpu_transfer_bytes",
                    "cpu_transfer_count", "subtiming_other_ms"):
            self.assertIn(key, tail)

    def test_resolver_labels_all_source_classes(self):
        # store capture with legacy wrapper source
        st.note_sampling_start(111, 0, request_id="r44i2-resolver")
        mono, src = st.resolve_sampling_start(None, None)
        self.assertEqual((mono, src), (111, "wrapper_runtime_store"))
        # direct source relabels to the authoritative direct boundary
        st.reset_request("r44i2-resolver2")
        st.note_sampling_start(222, 0, request_id="r44i2-resolver2",
                               source=st.DIRECT_SAMPLING_START_SOURCE)
        mono2, src2 = st.resolve_sampling_start(None, None)
        self.assertEqual((mono2, src2),
                         (222, "authoritative_direct_sampler_boundary"))
        # durable trace event beats the store
        class _Ev:
            name = "sampling_start"
            monotonic_ns = 333
        mono3, src3 = st.resolve_sampling_start([_Ev()], None)
        self.assertEqual((mono3, src3), (333, "authoritative_wrapper"))
        # milestone proxy stays last and explicitly labeled
        st.reset_request("")
        mono4, src4 = st.resolve_sampling_start(
            None, {"sampler_first_stage_ns": 444})
        self.assertEqual((mono4, src4), (444, "proxy_first_progress"))


# ── I: feature disabled = native behavior untouched ───────────────────────


class FeatureDisabledNativeBehaviorTest(unittest.TestCase):

    def setUp(self):
        try:
            self._cs = importlib.import_module("comfy.samplers")
            self._cmb = importlib.import_module("comfy.model_base")
        except Exception as exc:
            self.skipTest(f"comfy runtime classes unavailable: {exc}")
        _cleanup()
        # Capture AFTER cleanup: _cleanup ends with remove_direct_boundaries,
        # so these are guaranteed to be the TRUE originals.
        self._orig_sample = self._cs.CFGGuider.sample
        self._orig_apply = self._cmb.BaseModel.apply_model
        self._prev_enabled = st._ENABLED

    def tearDown(self):
        st._ENABLED = True if not hasattr(self, "_prev_enabled") else self._prev_enabled
        self._cs.CFGGuider.sample = self._orig_sample
        self._cmb.BaseModel.apply_model = self._orig_apply
        _cleanup()

    def test_disabled_flag_leaves_classes_and_recording_untouched(self):
        st.remove_direct_boundaries()
        st._ENABLED = False
        try:
            status = st.install_direct_boundaries()
            self.assertEqual(status, {"sampling_start": False, "first_eval": False})
            self.assertIs(self._cs.CFGGuider.sample, self._orig_sample)
            self.assertIs(self._cmb.BaseModel.apply_model, self._orig_apply)

            st.reset_request("r44i2-disabled")
            st.note_sampling_start(123, 456)
            st.note_first_eval(789)
            st.note_progress_tick(step=0, source="t")
            snap = st.snapshot()
            self.assertEqual(snap["sampling_start_mono_ns"], 0)
            self.assertEqual(snap["first_eval_mono_ns"], 0)
            self.assertEqual(snap["tick_count"], 0)
            self.assertEqual(st.emit_durable_events(_RecordingTrace()), 0)

            # Even a manually-built wrapper must not record while disabled.
            wrapped = st.build_direct_sampling_start_wrapper(
                lambda self, *a, **k: "ok")
            holder = type("H", (), {"sample": wrapped})
            holder().sample("n", "l", "s", [1, 2])
            self.assertEqual(st.snapshot()["sampling_start_mono_ns"], 0)
        finally:
            st._ENABLED = self._prev_enabled


if __name__ == "__main__":
    unittest.main()
