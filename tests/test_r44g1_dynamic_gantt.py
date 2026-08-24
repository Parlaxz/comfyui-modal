"""R44G1 offline tests: V2 DYNAMIC CRITICAL PATH GANTT (comfymodal_runtime/dynamic_gantt.py).

No Modal, no CUDA, no network, no deploy.  Pure presentation-layer checks over
synthetic in-memory DynamicPayload fixtures shaped like real R44E artifacts,
plus one skip-if-absent integration test against the real R44E run directory.

Covers: sparse traces (no fabrication), rich ground-truth decomposition,
background/critical overlap math, outer-vs-inner CLIP naming, broad/exact H2D
coexistence, closure residual math (incl. nested-exclusion and CANNOT SUM),
telemetry completeness matrix, fallback-run header, dynamic windows,
label truncation, empty-payload grace, deterministic rendering, ASCII-only
bars (█ + eighth blocks, never '='), and the real-artifact reconciliation.
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from comfymodal_runtime import dynamic_gantt as dg  # noqa: E402

REAL_RUN_DIR = (
    r"C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI"
    r"\comfymodal-data\benchmarks\runs\v2_2026-08-24_02-49-32"
)

_BAR_CHARS = set("\u2588\u258f\u258e\u258d\u258c\u258b\u258a\u2589 ")


# ── synthetic fixture helpers ─────────────────────────────────────────────


def _evt(name, mono_ns, **meta):
    """Normalized trace event (same shape load_run_artifacts produces)."""
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
        "loader_selection": {}, "cpu_owner_records": [], "profile_name": "r44g1-test",
        "runtime_status": {},
    }


def _payload(raw, request_id="v2-benchmark-0-synthetic"):
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


# Rich R44E-like timeline (monotonic ns), carrying the R44E ground truth.
T4S = 220_000_000_000
T4E = T4S + 4_825_536_000              # CLIP node 4825.536 ms
CFLS = 220_050_000_000
CFLE = 224_800_000_000
OUTER_END = 225_400_000_000           # outer encode 4689.879 ms
INNER_END = 225_350_000_000           # inner forward 2330.498 ms
ARMED = 220_710_130_000               # UNET source prep armed
PREP_MS = 4827.587
JOIN_END = ARMED + 4_827_587_000
T4BS = 225_550_000_000
T4BE = T4BS + 819_495_000             # UNET node 819.495 ms
XFER_S = 225_650_000_000
UNET_SETUP_MS = 3.859
UNET_COPY_MS = 624.677
UNET_INSTANT_MS = 0.354
UNET_ADOPT_MS = 111.888
XFER_E = XFER_S + int(round((UNET_SETUP_MS + UNET_COPY_MS + UNET_INSTANT_MS + UNET_ADOPT_MS) * 1e6))
H2D_S = 225_649_000_000               # broad H2D 741.786 ms
T6S = 226_600_000_000
T6E = T6S + 3_727_396_000             # sampling 3727.396 ms


def _rich_raw(loader_selection=None):
    raw = _empty_raw()
    raw["events"] = [
        _evt("clip_fast_load_start", CFLS, descriptor_wall_ms=27.547),
        _evt("clip_fast_load_end", CFLE, wall_ms=4825.536,
             descriptor_wall_ms=27.547, fastsafe_setup_wall_ms=11.272,
             fastsafe_copy_wall_ms=1934.712, fastsafe_get_keys_wall_ms=0.200,
             fastsafe_get_tensor_loop_wall_ms=0.135, bind_ms=2670.544,
             sampled_tensor_count=169),
        _evt("clip_forward_end", OUTER_END, wall_ms=4689.879, allocated_delta_bytes=12345),
        _evt("clip_forward_end", INNER_END, duration_ms=2330.498,
             cuda_no_sync=True, thread_cpu_ms=11.5),
        _evt("unet_source_prep_armed", ARMED, armed_at_mono_ns=ARMED),
        _evt("unet_source_prep_joined", JOIN_END, join_end_mono_ns=JOIN_END),
        _evt("unet_gpu_transfer_start", XFER_S),
        _evt("unet_fastsafe_pipeline", 225_700_000_000, gate_wait_ms=1.089,
             fastsafe_setup_wall_ms=UNET_SETUP_MS, fastsafe_copy_wall_ms=UNET_COPY_MS,
             fastsafe_instantiate_wall_ms=UNET_INSTANT_MS, adopt_ms=UNET_ADOPT_MS,
             header_detect_wall_ms=5.526, skeleton_wall_ms=80.832,
             bind_wall_ms=13.669, identity_validation_wall_ms=11.839,
             storage_identity_total=512, storage_identity_matched=512,
             unet_prep_overlap_ms=4689.870, unet_prep_overlap_pct_of_prep=97.15),
        _evt("unet_gpu_transfer_end", XFER_E),
    ]
    raw["gt_spans"] = [
        _gt("UNET H2D", H2D_S, H2D_S + 741_786_000),
        _gt("VAE decode", 230_400_000_000, 230_400_000_000 + 494_346_000),
        _gt("output encode", 230_950_000_000, 231_070_000_000, lane="OUTPUT"),
    ]
    raw["waterfall_stages"] = dict([
        _wf("sampler_node_to_sampling", 226_450_000_000, 120.5),
        _wf("post_sampling_transition", 230_340_000_000, 45.2),
        _wf("output_persistence", 231_100_000_000, 80.0),
    ])
    raw["sample_stages"] = {
        "t4_modal_method_entry": 218_600_000_000,
        "t4_clip_load_start": T4S, "t4_clip_load_end": T4E,
        "t5_text_encode_end": 225_400_000_000,
        "t4b_unet_load_start": T4BS, "t4b_unet_load_end": T4BE,
        "t6_sampler_start": T6S, "t6_sampler_end": T6E,
    }
    raw["serial_ledger"] = {"start_mono_ns": 218_500_000_000, "end_mono_ns": 240_000_000_000}
    raw["cpu_owner_records"] = [{"operation": "load_models_gpu", "role": "CLIP",
                                 "wall_ms": 2283.612}]
    raw["loader_selection"] = loader_selection or {}
    return raw


def _bar_segments(text):
    """Yield the bar region (between the two │ glyphs) of every bar row."""
    for line in text.splitlines():
        parts = line.split("\u2502")
        if len(parts) >= 3:
            yield parts[1]


def _parse_bg_line(summary_text):
    m = re.search(r"activity_wall\u2248([\d,.]+) ms \u00b7 "
                  r"critical_path_contribution\u2248([\d,.]+) ms", summary_text)
    self_val = (float(m.group(1).replace(",", "")), float(m.group(2).replace(",", ""))) \
        if m else None
    return self_val


def _parse_residual(block):
    m = re.search(r"residual\s+([\d,.]+) ms \(([\d.]+)% of parent\)", block)
    if not m:
        return None
    return float(m.group(1).replace(",", "")), float(m.group(2))


# ── tests ─────────────────────────────────────────────────────────────────


class SparseTraceTest(unittest.TestCase):
    def test_sparse_native_trace_renders_only_present_rows(self):
        """Only a few native stages exist -> renders without crash, no
        fabricated FastSafe/CLIP rows."""
        raw = _empty_raw()
        k, v = _wf("remote_method_setup", 1_000_000_000, 110.0)
        raw["waterfall_stages"][k] = v
        k, v = _wf("prompt_executor_cache_setup", 1_200_000_000, 50.0)
        raw["waterfall_stages"][k] = v
        raw["sample_stages"] = {"t4_modal_method_entry": 900_000_000}
        raw["serial_ledger"] = {"start_mono_ns": 500_000_000, "end_mono_ns": 5_000_000_000}
        p = _payload(raw)
        text = dg.render_full_report(p)
        keys = {r.key for r in p.rows}
        self.assertIn("restore", keys)
        self.assertIn("request.setup.remote_method", keys)
        self.assertIn("request.setup.cache_setup", keys)
        self.assertNotIn("clip.copy", keys)
        self.assertNotIn("clip.inner", keys)
        self.assertNotIn("unet.copy", keys)
        self.assertNotIn("FastSafe", text)
        self.assertNotIn("CLIPLoader", text)
        # the completeness matrix legitimately names "CLIP inner forward" as a
        # MISSING metric; assert no rendered ROW carries that label
        self.assertFalse(any(r.label == "CLIP inner forward" for r in p.rows))
        self.assertIn("remote method setup", text)


class RichFixtureTest(unittest.TestCase):
    def setUp(self):
        self.payload = _payload(_rich_raw())
        self.by_key = {r.key: r for r in self.payload.rows}

    def test_rich_trace_rows_and_ground_truth_durations(self):
        expected = {
            "clip.node": ("CLIPLoader (t4 node)", 4825.536),
            "clip.descriptor": ("descriptor/header (exact)", 27.547),
            "clip.copy": ("FastSafe copy (exact)", 1934.712),
            "clip.construct": ("Comfy construction (exact)", 2670.544),
            "clip.lmg": ("CLIP load_models_gpu (exact)", 2283.612),
            "clip.encode_outer": ("CLIP outer encode", 4689.879),
            "clip.inner": ("CLIP inner forward", 2330.498),
            "unet.node": ("UNETLoader (t4b node)", 819.495),
            "unet.gate": ("gate wait (exact)", 1.089),
            "unet.copy": ("FastSafe copy (exact)", UNET_COPY_MS),
            "unet.adopt": ("adoption (exact)", UNET_ADOPT_MS),
            "unet.h2d_broad": ("UNET H2D (broad window)", 741.786),
            # R44H2: canonical label is now "progress sampling" (the window
            # is first→last progress callback, NOT the whole sampling call).
            "sampling": ("progress sampling", 3727.396),
            "post.sampling": ("post-sampling transition", 45.2),
            "vae.decode": ("VAE decode", 494.346),
        }
        for key, (label, ms) in expected.items():
            self.assertIn(key, self.by_key, f"missing row {key}")
            self.assertEqual(self.by_key[key].label, label, key)
            self.assertAlmostEqual(self.by_key[key].duration_ms, ms, delta=0.1, msg=key)
        for key in ("unet.entry_join", "unet.setup", "sampler.transition",
                    "output.encode", "output.persist"):
            self.assertIn(key, self.by_key, f"missing row {key}")
        # R44H2: without a TRUE sampling_start the legacy interval must be
        # labeled as a PROXY (first-progress end boundary), never a bare
        # "sampler startup".
        self.assertIn("PROXY", self.by_key["sampler.transition"].label)
        self.assertNotIn("sampling\u2192", self.by_key["sampler.transition"].label)

    def test_outer_vs_inner_forward_naming_no_bare_label(self):
        labels = {r.label for r in self.payload.rows}
        self.assertIn("CLIP outer encode", labels)
        self.assertIn("CLIP inner forward", labels)
        self.assertNotIn("CLIP forward", labels)
        self.assertEqual(dg.detect_label_conflicts(self.payload, self.payload.rows), [])
        self.assertIn("LABEL CONFLICTS: none", dg.render_full_report(self.payload))

    def test_broad_h2d_and_exact_copy_coexist(self):
        broad = self.by_key["unet.h2d_broad"]
        exact = self.by_key["unet.copy"]
        self.assertEqual(broad.label, "UNET H2D (broad window)")
        self.assertIn("(broad", broad.label)
        self.assertAlmostEqual(broad.duration_ms, 741.786, delta=0.001)
        self.assertEqual(exact.parent_key, "unet.node")
        self.assertAlmostEqual(exact.duration_ms, UNET_COPY_MS, delta=0.001)
        # the CLIP-side exact copy is a distinct row under a different parent
        self.assertIn("clip.copy", self.by_key)

    def test_closure_residual_math(self):
        blocks = dg.closure_reports(self.payload, self.payload.rows)
        clip_block = next(b for b in blocks if "CLIP NODE CLOSURE" in b)
        parsed = _parse_residual(clip_block)
        self.assertIsNotNone(parsed, "residual line missing from CLIP NODE CLOSURE")
        residual, pct = parsed
        self.assertAlmostEqual(residual, 181.126, delta=0.1)
        self.assertLess(pct, 5.0)
        self.assertIn("\u2713 closes", clip_block)
        unet_block = next(b for b in blocks if "UNET NODE CLOSURE" in b)
        parsed2 = _parse_residual(unet_block)
        self.assertIsNotNone(parsed2, "residual line missing from UNET NODE CLOSURE")
        residual2, pct2 = parsed2
        # implementation derives entry/prep join as remainder => residual ~0;
        # spec threshold is <250 ms and <5% either way
        self.assertLess(residual2, 250.0)
        self.assertLess(pct2, 5.0)
        self.assertIn("\u2713 closes", unet_block)
        # nested adoption grandchildren are reported but excluded from sums
        self.assertIn("excluded from sum", unet_block)
        self.assertIn("dropped nested component(s)", unet_block)

    def test_completeness_matrix_present_and_missing_with_proxies(self):
        matrix = dg.completeness_matrix(self.payload)
        for label in ("CLIP descriptor", "CLIP exact copy", "CLIP construction",
                      "CLIP load_models_gpu", "CLIP inner forward",
                      "UNET exact copy", "CLIP storage identity", "UNET source prep"):
            self.assertRegex(matrix, rf"{re.escape(label)}\s+PRESENT")
        self.assertIn("sampler-start decomposition        MISSING "
                      "(expected: fine-grained sampler-node\u2192sampling sub-events; "
                      "closest proxy: waterfall.sampler_node_to_sampling)", matrix)
        self.assertIn("post-sampling decomposition        MISSING "
                      "(expected: fine-grained post-sampling sub-events; "
                      "closest proxy: waterfall.post_sampling_transition)", matrix)
        # a payload lacking clip_fast_load_end still names the closest proxy
        raw = _empty_raw()
        raw["sample_stages"] = {"t4_clip_load_start": T4S, "t4_clip_load_end": T4E}
        m2 = dg.completeness_matrix(_payload(raw))
        self.assertIn("CLIP descriptor                    MISSING "
                          "(expected: trace.events:clip_fast_load_end.descriptor_wall_ms; "
                          "closest proxy: "
                          "trace.events:clip_fast_load_start.descriptor_wall_ms)", m2)

    def test_dynamic_windows_derive_from_events(self):
        wins = dg.compute_windows(self.payload, self.payload.rows)
        self.assertEqual(wins["CLIP DETAIL"][0], T4S)
        self.assertLessEqual(wins["UNET DETAIL"][0], ARMED)
        self.assertEqual(wins["SAMPLER TRANSITION"], (T4BE, T6S))
        self.assertEqual(wins["POST-SAMPLING / VAE"][0], T6E)
        again = dg.compute_windows(self.payload, self.payload.rows)
        self.assertEqual(wins, again)
        self.assertEqual(wins.get("AUTO-DENSE"), again.get("AUTO-DENSE"))

    def test_absent_boundary_events_skip_windows_gracefully(self):
        raw = _empty_raw()
        raw["events"] = [_evt("clip_forward_end", OUTER_END, wall_ms=100.0,
                              allocated_delta_bytes=1)]
        p = _payload(raw)
        wins = dg.compute_windows(p, p.rows)
        for absent in ("CLIP DETAIL", "UNET DETAIL", "SAMPLER TRANSITION",
                       "POST-SAMPLING / VAE"):
            self.assertNotIn(absent, wins)
        dg.render_full_report(p)  # must not raise

    def test_deterministic_rendering(self):
        a = dg.render_full_report(self.payload)
        b = dg.render_full_report(self.payload)
        c = dg.render_full_report(self.payload,
                                  windows=dg.compute_windows(self.payload, self.payload.rows))
        self.assertEqual(a, b)
        self.assertEqual(a, c)

    def test_ascii_bars_never_use_equals(self):
        text = dg.render_full_report(self.payload)
        segments = list(_bar_segments(text))
        self.assertTrue(segments, "expected at least one bar row")
        for seg in segments:
            self.assertTrue(set(seg) <= _BAR_CHARS, repr(seg))
            self.assertNotIn("=", seg)
        self.assertTrue(any("\u2588" in seg for seg in segments))

    def test_fallback_run_header(self):
        p = _payload(_rich_raw(loader_selection={
            "clip": {"fallback_attempted": True, "reason": "qd snapshot unavailable"}}))
        text = dg.render_full_report(p)
        self.assertIn("FALLBACK RUN", text)
        self.assertIn("clip", text)


class OverlapMathTest(unittest.TestCase):
    def test_prep_overlap_with_clip_compute(self):
        """Background UNET prep overlapping critical CLIP outer encode on one
        shared axis: contribution = wall - overlap, never exceeding spans."""
        raw = _empty_raw()
        o_end = 225_335_085_105
        armed3 = 220_645_216_105
        join3 = armed3 + 4_827_587_000
        raw["events"] = [
            _evt("clip_forward_end", o_end, wall_ms=4689.879, allocated_delta_bytes=1),
            _evt("unet_source_prep_armed", armed3, armed_at_mono_ns=armed3),
            _evt("unet_source_prep_joined", join3, join_end_mono_ns=join3),
        ]
        p = _payload(raw)
        prep = _row(p.rows, "unet.prep")
        outer = _row(p.rows, "clip.encode_outer")
        self.assertAlmostEqual(prep.duration_ms, 4827.587, delta=0.001)
        self.assertAlmostEqual(outer.duration_ms, 4689.879, delta=0.001)
        summary = dg.critical_path_summary(p, p.rows)
        parsed = _parse_bg_line(summary)
        self.assertIsNotNone(parsed, "background contribution line missing")
        activity, contrib = parsed
        self.assertAlmostEqual(activity, 4827.587, delta=0.05)
        self.assertGreater(contrib, 100.0)
        self.assertLess(contrib, 200.0)
        overlap = activity - contrib
        # display values are rounded to 0.1 ms — allow that slack here…
        self.assertLessEqual(overlap, min(prep.duration_ms, outer.duration_ms) + 0.05)
        # …and prove the exact ns math never exceeds the smaller span
        overlap_ns = (min(prep.end_mono_ns, outer.end_mono_ns)
                      - max(prep.start_mono_ns, outer.start_mono_ns))
        self.assertLessEqual(overlap_ns, min(prep.end_mono_ns - prep.start_mono_ns,
                                             outer.end_mono_ns - outer.start_mono_ns))
        self.assertAlmostEqual(overlap_ns / 1e6, 4689.869, delta=0.001)
        # rendered bars overlap on a shared axis
        w0 = min(prep.start_mono_ns, outer.start_mono_ns)
        w1 = max(prep.end_mono_ns, outer.end_mono_ns)
        win = dg.render_window(p.rows, (w0, w1), "OVERLAP TEST")

        def span(label):
            line = next(l for l in win.splitlines() if l.startswith(label[:20]))
            seg = line.split("\u2502")[1]
            idx = [i for i, ch in enumerate(seg) if ch != " "]
            return idx[0], idx[-1]

        a0, a1 = span("UNET source prep")
        b0, b1 = span("CLIP outer encode")
        self.assertTrue(max(a0, b0) <= min(a1, b1), "bars do not visually overlap")


class CannotSumTest(unittest.TestCase):
    def test_components_exceeding_parent_claim_cannot_sum(self):
        raw = _empty_raw()
        raw["sample_stages"] = {"t4_clip_load_start": 100_000_000_000,
                                "t4_clip_load_end": 100_100_000_000}  # 100 ms parent
        raw["events"] = [_evt("clip_fast_load_end", 100_050_000_000, bind_ms=500.0)]
        p = _payload(raw)
        blocks = dg.closure_reports(p, p.rows)
        block = next(b for b in blocks if "CLIP NODE CLOSURE" in b)
        self.assertIn("CANNOT SUM", block)
        self.assertNotIn("closes", block)


class LabelTruncationTest(unittest.TestCase):
    def test_truncate_label_deterministic(self):
        long = "U" * 60
        cut = dg.truncate_label(long)
        self.assertEqual(cut, "U" * 37 + "\u2026")
        self.assertEqual(len(cut), 38)
        self.assertEqual(cut, dg.truncate_label(long))
        self.assertEqual(dg.truncate_label("short"), "short")
        self.assertEqual(dg.truncate_label("abcdef", 4), "abc\u2026")

    def test_long_labels_keep_bar_layout_within_width(self):
        rows = [
            dg.GanttRow(key="a", label="L" * 60, parent_key=None, kind="exact",
                        role="critical", lane="CPU", start_mono_ns=0,
                        end_mono_ns=500_000_000, duration_ms=500.0, source_refs=[]),
            dg.GanttRow(key="b", label="M" * 60, parent_key="a", kind="exact",
                        role="critical", lane="CPU", start_mono_ns=100_000_000,
                        end_mono_ns=400_000_000, duration_ms=300.0, source_refs=[]),
        ]
        text = dg.render_window(rows, (0, 1_000_000_000), "TRUNC")
        bar_width = 110 - dg._LABEL_COL - 4
        for line in text.splitlines():
            parts = line.split("\u2502")
            if len(parts) >= 3:
                self.assertLessEqual(len(parts[0]), dg._LABEL_COL + 1)
                self.assertEqual(len(parts[1]), bar_width)


class EmptyPayloadTest(unittest.TestCase):
    def test_no_data_renders_gracefully_all_missing(self):
        p = _payload(_empty_raw(), request_id="empty-run")
        text = dg.render_full_report(p)  # must not raise (incl. ZeroDivision)
        self.assertIn(dg.GANTT_TITLE, text)
        self.assertEqual(text.splitlines()[0], dg.GANTT_TITLE)
        matrix = dg.completeness_matrix(p)
        # R44H2 extended the matrix with 10 sampler/post-sampling entries
        # (17 original + 10 = 27).
        self.assertEqual(matrix.count("MISSING"), 27)
        self.assertIn("closest proxy:", matrix)
        self.assertIn("loader fallback: none", text)


class RealArtifactIntegrationTest(unittest.TestCase):
    @unittest.skipUnless(os.path.isdir(REAL_RUN_DIR),
                         "real R44E artifact directory not present")
    def test_real_r44e_artifact_reconciliation(self):
        p = dg.load_run_artifacts(REAL_RUN_DIR)
        self.assertEqual(p.request_id, "v2-benchmark-0-d5df02fd8dba")
        by_key = {r.key: r for r in p.rows}
        expected = {
            "clip.node": 4825.536, "clip.copy": 1934.712, "clip.construct": 2670.544,
            "clip.descriptor": 27.547, "clip.lmg": 2283.612, "clip.inner": 2330.498,
            "clip.encode_outer": 4689.879, "unet.node": 819.495,
            "unet.h2d_broad": 741.786, "unet.copy": 624.677, "unet.adopt": 111.888,
            "sampling": 3727.396, "vae.decode": 494.346,
        }
        for key, ms in expected.items():
            self.assertIn(key, by_key, f"missing row {key} in real artifact")
            self.assertAlmostEqual(by_key[key].duration_ms, ms, delta=0.5, msg=key)
        self.assertEqual(dg.detect_label_conflicts(p, p.rows), [])
        text = dg.render_full_report(p)
        self.assertIn("\u2588", text)
        for seg in _bar_segments(text):
            self.assertTrue(set(seg) <= _BAR_CHARS, repr(seg))
            self.assertNotIn("=", seg)
        matrix = dg.completeness_matrix(p)
        for label in ("CLIP descriptor", "CLIP exact copy", "CLIP construction",
                      "CLIP load_models_gpu", "CLIP inner forward",
                      "UNET exact copy", "CLIP storage identity", "UNET source prep"):
            self.assertRegex(matrix, rf"{re.escape(label)}\s+PRESENT")
        self.assertIn("sampler-start decomposition        MISSING", matrix)
        self.assertIn("post-sampling decomposition        MISSING", matrix)


if __name__ == "__main__":
    unittest.main()
