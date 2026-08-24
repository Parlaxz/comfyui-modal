"""R44H2 tests: live dynamic-Gantt integration + sampler/post-sampling telemetry.

No Modal, no CUDA requirement, no network, no deploy.  Covers:

A. true ``sampling_start`` persistence -> detailed canonical rows
B. fallback semantics: absent true event -> PROXY labeling (never a bare
   "sampling start" claim)
C. stage split node entry < sampling_start < first_eval < first_progress
   < last_progress < sampler_return renders correctly
D. first-progress is NEVER presented as the sampling start
E. a ~650 ms synthetic tail is attributed to the RES4LYF sampler post-loop,
   not to a VAE transition
F. GC/deepcopy/.cpu() sub-timing aggregation without double counting
G. broad ``post_sampling_transition`` parent + exact ``sampler_tail`` child
   coexist without double counting
H. (run separately) R44G1 dynamic-Gantt suite stays green
I. sparse/old/native traces still render without errors
J. deterministic rendering + low local overhead (render + tick recording)
"""

import os
import sys
import time
import unittest

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
# Defensive: a previously-collected test module may have pinned
# ``comfymodal_runtime`` to a SIBLING checkout; this worktree's package must
# win for these assertions.
for _name in [k for k in list(sys.modules)
              if k == "comfymodal_runtime" or k.startswith("comfymodal_runtime.")]:
    _mod = sys.modules.get(_name)
    _path0 = getattr(getattr(_mod, "__path__", None), "__getitem__", lambda *_: "")(0)
    if _path0 and not os.path.normcase(_path0).startswith(os.path.normcase(_HERE)):
        del sys.modules[_name]

from comfymodal_runtime import dynamic_gantt as dg  # noqa: E402
from comfymodal_runtime import sampler_telemetry as st  # noqa: E402


# ── fixture helpers (G1-compatible shapes) ────────────────────────────────


def _evt(name, mono_ns, **meta):
    return {"name": name, "mono_ns": int(mono_ns), "wall_unix_ns": 0, "meta": meta}


def _gt(name, start, end, lane="GPU"):
    return {"name": name, "lane": lane, "start_mono_ns": int(start),
            "end_mono_ns": int(end), "duration_ms": (int(end) - int(start)) / 1e6}


def _wf(key, start, dur_ms):
    return (key, {"key": key, "label": key, "start_mono_ns": int(start),
                  "end_mono_ns": int(start + round(dur_ms * 1e6)),
                  "duration_ms": float(dur_ms), "clock_scope": "monotonic"})


def _empty_raw():
    return {
        "run_file": "run_0.json", "events": [], "gt_spans": [], "led_spans": [],
        "ledger": {}, "serial_ledger": {}, "waterfall_stages": {}, "sample_stages": {},
        "phase_durations_ms": {}, "timing": {}, "restore_timing": {},
        "loader_selection": {}, "cpu_owner_records": [], "profile_name": "r44h2-test",
        "runtime_status": {},
    }


def _payload(raw, request_id="v2-benchmark-0-r44h2"):
    p = dg.DynamicPayload(
        request_id=request_id, rows=[], raw=raw,
        anchors={"wall_minus_mono_ns": 0, "anchor_samples": 0,
                 "origin_mono_ns": (raw.get("serial_ledger") or {}).get("start_mono_ns") or 0},
        warnings=[],
    )
    p.rows = dg.build_rows(p)
    return p


def _row(rows, key):
    return next(r for r in rows if r.key == key)


# ── rich fixture WITH the new R44H2 sampler events ────────────────────────

T4BS = 225_550_000_000
T4BE = T4BS + 819_495_000
NODE_ENTRY = 226_400_000_000
SS = 226_520_000_000            # node -> true sampling_start = 120 ms
FE = 227_600_000_000            # sampling_start -> first eval = 1080 ms
T6S = 227_700_000_000           # first eval -> first progress = 100 ms
T6E = T6S + 3_727_396_000       # progress window
TAIL_MS = 649.777
TAIL_END = T6E + int(round(TAIL_MS * 1e6))
VAE_DS = TAIL_END + 300_000     # ~0.3 ms executor dispatch
VAE_DE = VAE_DS + 494_346_000


def _rich_h2_raw():
    raw = _empty_raw()
    raw["events"] = [
        _evt("pre_sampler_stages", NODE_ENTRY + 1_000,
             first_sampler_node_monotonic_ns=NODE_ENTRY,
             sampling_start_monotonic_ns=SS,
             sampling_start_source="authoritative_wrapper"),
        _evt("sampling_start", SS, node_id="1242", node_class="ClownsharKSampler_Beta",
             steps=8),
        _evt("unet_first_cuda_op", FE, elapsed_ms=1080.0),
        _evt("sampler_step_ticks", T6E, count=8,
             steps=[{"i": i, "mono_ns": T6S + i * 466_000_000, "progress": None}
                    for i in range(8)]),
        _evt("sampler_tail", TAIL_END,
             start_mono_ns=T6E, end_mono_ns=TAIL_END, wall_ms=TAIL_MS,
             gc_collect_ms=210.5, gc_collect_count=1,
             state_info_deepcopy_ms=95.2, state_info_deepcopy_count=1,
             cpu_transfer_wall_ms=180.0, cpu_transfer_bytes=12_345_678,
             cpu_transfer_count=2),
        _evt("vae_decode_start", VAE_DS),
    ]
    raw["gt_spans"] = [_gt("VAE decode", VAE_DS, VAE_DE)]
    raw["waterfall_stages"] = dict([
        _wf("post_sampling_transition", T6E, TAIL_MS + 0.3),
    ])
    raw["sample_stages"] = {
        "t6_sampler_start": T6S, "t6_sampler_end": T6E,
        "t7_vae_decode_start": VAE_DS, "t7_vae_decode_end": VAE_DE,
    }
    raw["serial_ledger"] = {"start_mono_ns": 218_500_000_000, "end_mono_ns": 240_000_000_000}
    raw["cpu_owner_records"] = [
        {"operation": "load_models_gpu", "role": "other", "caller": "vae_decode",
         "wall_ms": 61.369, "start_mono_ns": VAE_DS + 1_000_000,
         "end_mono_ns": VAE_DS + 62_369_000},
    ]
    return raw


class TrueSamplingStartPersistenceTest(unittest.TestCase):
    """A. The authoritative event survives into the rendered artifact view."""

    def setUp(self):
        self.p = _payload(_rich_h2_raw())
        self.by = {r.key: r for r in self.p.rows}

    def test_detailed_rows_present_with_true_boundaries(self):
        for key in ("sampler.node", "sampler.prep", "sampler.first_eval_startup",
                    "sampler.first_step_latency", "sampling", "sampler.tail"):
            self.assertIn(key, self.by, f"missing {key}")
        self.assertAlmostEqual(self.by["sampler.prep"].duration_ms, 120.0, delta=0.01)
        self.assertAlmostEqual(self.by["sampler.first_eval_startup"].duration_ms, 1080.0, delta=0.01)
        self.assertAlmostEqual(self.by["sampler.first_step_latency"].duration_ms, 100.0, delta=0.01)
        # no PROXY interval when the true event exists
        self.assertNotIn("sampler.transition", self.by)

    def test_completeness_marks_true_wrapper_start_present(self):
        matrix = dg.completeness_matrix(self.p)
        self.assertRegex(matrix, r"sampling wrapper start \(true\)\s+PRESENT")
        self.assertRegex(matrix, r"sampler prep phase\s+PRESENT")
        self.assertRegex(matrix, r"first eval start\s+PRESENT")
        self.assertRegex(matrix, r"per-step ticks\s+PRESENT")
        self.assertRegex(matrix, r"sampler tail\s+PRESENT")
        self.assertRegex(matrix, r"tail GC split\s+PRESENT")
        self.assertRegex(matrix, r"tail deepcopy split\s+PRESENT")
        self.assertRegex(matrix, r"tail CPU transfer split\s+PRESENT")
        self.assertRegex(matrix, r"VAE load_models_gpu mono timestamps\s+PRESENT")

    def test_stage_summary_names_true_boundary(self):
        text = dg.stage_summary(self.p, self.p.rows)
        self.assertIn("node entry \u2192 true sampling_start", text)
        self.assertNotIn("[LEGACY", text)


class FallbackProxySemanticsTest(unittest.TestCase):
    """B + D. Absent true event -> explicit PROXY, never 'sampling start'."""

    def setUp(self):
        raw = _empty_raw()
        raw["waterfall_stages"] = dict([
            _wf("sampler_node_to_sampling", 226_450_000_000, 1461.501),
            _wf("sampling", 227_900_000_000, 3727.396),
        ])
        raw["sample_stages"] = {"t6_sampler_start": 227_900_000_000,
                                "t6_sampler_end": 231_627_396_000}
        self.p = _payload(raw)

    def test_proxy_label_not_bare_startup(self):
        row = _row(self.p.rows, "sampler.transition")
        self.assertIn("PROXY", row.label)
        self.assertIn("first progress", row.label)
        self.assertNotIn("sampler startup", row.label.lower())
        self.assertTrue(row.meta.get("proxy"))

    def test_completeness_missing_with_exact_proxy_name(self):
        import re
        matrix = dg.completeness_matrix(self.p)
        self.assertRegex(matrix, r"sampling wrapper start \(true\)\s+MISSING "
                         r"\(expected: trace\.events:sampling_start; closest proxy: "
                         r"pre_sampler_stages\.sampling_start_monotonic_ns\[proxy_first_progress\]\)")

    def test_resolver_priority(self):
        # 1) durable event wins
        class _Ev:
            name = "sampling_start"
            monotonic_ns = 111
        mono, src = st.resolve_sampling_start([_Ev()], None)
        self.assertEqual((mono, src), (111, "authoritative_wrapper"))
        # 2) request-scoped wrapper store (still TRUE source)
        st.reset_request("resolver-test")
        st.note_sampling_start(222, 0, request_id="resolver-test")
        mono2, src2 = st.resolve_sampling_start(None, None)
        self.assertEqual((mono2, src2), (222, "wrapper_runtime_store"))
        # 3) milestone fallback is explicitly a PROXY (store cleared first)
        st.reset_request("")
        mono3, src3 = st.resolve_sampling_start(None, {"sampler_first_stage_ns": 333})
        self.assertEqual((mono3, src3), (333, "proxy_first_progress"))
        st.reset_request("")


class StageSplitOrderingTest(unittest.TestCase):
    """C. node entry < sampling_start < first_eval < first_progress."""

    def test_chain_order_and_containment(self):
        p = _payload(_rich_h2_raw())
        by = {r.key: r for r in p.rows}
        chain = ["sampler.prep", "sampler.first_eval_startup",
                 "sampler.first_step_latency", "sampling", "sampler.tail"]
        bounds = [(by[k].start_mono_ns, by[k].end_mono_ns) for k in chain]
        for (_, e1), (s2, _) in zip(bounds, bounds[1:]):
            self.assertLessEqual(abs(e1 - s2), 1_000_000, f"{chain} not contiguous at {e1}")
        self.assertLess(by["sampler.prep"].start_mono_ns, by["sampling"].end_mono_ns)
        wins = dg.compute_windows(p, p.rows)
        self.assertIn("SAMPLER DETAIL", wins)
        self.assertEqual(wins["SAMPLER DETAIL"][0], NODE_ENTRY)
        win_text = dg.render_window(p.rows, wins["SAMPLER DETAIL"], "SAMPLER DETAIL")
        order = [win_text.index(lab) for lab in
                 ("sampler orchestration/prep", "first-eval startup",
                  "first-step latency", "progress sampling")]
        self.assertEqual(order, sorted(order))


class TailAttributionTest(unittest.TestCase):
    """E. ~650 ms tail -> RES4LYF sampler post-loop, NOT a VAE transition."""

    def test_tail_row_and_dispatch(self):
        p = _payload(_rich_h2_raw())
        by = {r.key: r for r in p.rows}
        tail = by["sampler.tail"]
        self.assertEqual(tail.parent_key, "post.sampling")
        self.assertAlmostEqual(tail.duration_ms, TAIL_MS, delta=0.01)
        self.assertIn("RES4LYF", tail.label)
        self.assertNotIn("VAE", tail.label)
        disp = by["post.executor_dispatch"]
        self.assertAlmostEqual(disp.duration_ms, 0.3, delta=0.01)
        # broad parent coexists (G) and fully contains the exact child
        broad = by["post.sampling"]
        self.assertEqual(broad.kind, "broad")
        self.assertLessEqual(broad.start_mono_ns, tail.start_mono_ns)
        self.assertGreaterEqual(broad.end_mono_ns, tail.end_mono_ns)


class SubTimingAggregationTest(unittest.TestCase):
    """F. GC/deepcopy/.cpu() timers aggregate without double counting."""

    def setUp(self):
        st.reset_request("subtiming-test")

    def tearDown(self):
        st._TELEMETRY._remove_subtiming_patches()
        st.reset_request("")

    def test_patches_count_each_call_once(self):
        import copy
        st._TELEMETRY._install_subtiming_patches()
        copy.deepcopy({"a": [1, 2, 3]})
        gc_before = st.subtiming_totals()["gc_collect_count"]
        import gc as _gc
        _gc.collect()
        totals = st.subtiming_totals()
        self.assertEqual(totals["gc_collect_count"], gc_before + 1)
        self.assertEqual(totals["state_info_deepcopy_count"], 1)
        self.assertGreater(totals["state_info_deepcopy_ms"], 0.0)
        try:
            import torch  # noqa: F401
        except Exception:
            return  # torch-free environment: .cpu() coverage is best-effort
        x = __import__("torch").zeros(4)
        x.cpu()
        totals2 = st.subtiming_totals()
        self.assertEqual(totals2["cpu_transfer_count"], 1)
        self.assertEqual(totals2["cpu_transfer_bytes"], 16)  # 4 float32

    def test_finish_tail_idempotent_no_double_count(self):
        st.note_progress_tick(step=0, source="test")
        time.sleep(0.001)
        perf_now = time.perf_counter_ns()
        mono_now = time.monotonic_ns()
        t1 = st.finish_sampler_tail(perf_now + 1_000_000, mono_now + 1_000_000)
        t2 = st.finish_sampler_tail(perf_now + 9_000_000, mono_now + 9_000_000)
        self.assertIsNotNone(t1)
        self.assertIs(t1, t2)  # first close wins; no double counting


class DurableEventEmissionTest(unittest.TestCase):
    def test_emit_durable_events_once(self):
        class _FakeTrace:
            def __init__(self):
                self.emitted = []

            def emit(self, name, phase=None, metadata=None):
                self.emitted.append((name, metadata))
                return type("E", (), {"monotonic_ns": 0, "wall_unix_ns": 0})()

        st.reset_request("emit-test")
        st.note_sampler_node_entry("1242", "ClownsharKSampler_Beta")
        st.note_sampling_start(time.monotonic_ns() + 1, 0, node_id="1242", steps=8,
                               sigmas_len=9, latent_dtype="torch.float64",
                               latent_device="cuda:0", default_dtype="torch.float64")
        st.note_first_eval(time.monotonic_ns() + 2)
        st.note_progress_tick(step=0, source="wrapper_callback")
        st.finish_sampler_tail(time.perf_counter_ns() + 1_000_000,
                               time.monotonic_ns() + 1_000_000)
        ft = _FakeTrace()
        n = st.emit_durable_events(ft)
        names = [x[0] for x in ft.emitted]
        # R44I2: 4 legacy + deferred authoritative sampling_start (FakeTrace
        # exposes no .events, so the dedup guard emits) + mandatory status.
        self.assertEqual(n, 6)
        for want in ("sampler_prep_phase", "sampler_first_eval_start",
                     "sampler_step_ticks", "sampler_tail",
                     "sampling_start", "sampler_telemetry_status"):
            self.assertIn(want, names)
        prep_meta = dict(ft.emitted)[ "sampler_prep_phase"]
        self.assertEqual(prep_meta["sigmas_len"], 9)
        self.assertEqual(prep_meta["latent_device"], "cuda:0")
        self.assertEqual(st.emit_durable_events(ft), 0)  # idempotent per request
        st.reset_request("")


class SparseTraceGraceTest(unittest.TestCase):
    """I. old/native runs still render without errors."""

    def test_minimal_native_trace(self):
        raw = _empty_raw()
        k, v = _wf("remote_method_setup", 1_000_000_000, 110.0)
        raw["waterfall_stages"][k] = v
        raw["sample_stages"] = {"t6_sampler_start": 5_000_000_000,
                                "t6_sampler_end": 8_700_000_000}
        p = _payload(raw)
        text = dg.render_full_report(p)  # must not raise
        self.assertIn(dg.GANTT_TITLE, text)
        self.assertIn("progress sampling", text)

    def test_empty_payload(self):
        p = _payload(_empty_raw())
        text = dg.render_full_report(p)
        self.assertIn(dg.GANTT_TITLE, text)
        self.assertIn("STAGE SUMMARY", text)


class DeterminismAndOverheadTest(unittest.TestCase):
    """J. deterministic rendering + low local overhead."""

    def test_render_deterministic(self):
        p = _payload(_rich_h2_raw())
        a = dg.render_full_report(p)
        b = dg.render_full_report(p)
        self.assertEqual(a, b)

    def test_render_overhead_bounded(self):
        p = _payload(_rich_h2_raw())
        t0 = time.perf_counter()
        dg.render_full_report(p)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        self.assertLess(dt_ms, 500.0, f"full report render took {dt_ms:.1f} ms")

    def test_tick_recording_overhead_negligible(self):
        st.reset_request("perf-ticks")
        t0 = time.perf_counter()
        for i in range(2000):
            st.note_progress_tick(step=i % 8, source="perf")
        dt_ms = (time.perf_counter() - t0) * 1000.0
        self.assertLess(dt_ms, 500.0, f"2000 ticks took {dt_ms:.1f} ms")
        st.reset_request("")


if __name__ == "__main__":
    unittest.main()
