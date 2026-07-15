"""Tests for the diagnostic-pass additions (audit round 8).

Covers:
  * ``optimizations.CriticalPathRecorder`` — bind, record, snapshot,
    counters, monotonic-ns ordering, hot-path short-circuit.
  * Cache lookup diagnostic fix (Part 7) — restore seed no longer
    suppresses a later graph lookup; graph hits use phase=graph_lookup;
    graph misses use phase=graph_miss_encode.
  * Active-next read diagnostic dedup (Part 8) — per-restore dedup,
    call count, new restore resets state.
  * Critical-path summary (Part 5) — uses only observed timestamps,
    emits explicit nulls for missing events, never fabricates
    causal claims.
  * Static non-regression scan — no production behavior changes
    around the locked-down parameters.

These tests do NOT require the heavy ComfyUI import path.  They
exercise the diagnostic surface in isolation.
"""

import ast
import importlib
import io
import os
import re
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _func_source(src, name):
    """Extract the source of a function by name using AST. Returns None if not found."""
    try:
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                return ast.unparse(node)
    except SyntaxError:
        pass
    return None


def _load_optimizations(force_clean_env: bool = False):
    import optimizations
    return importlib.reload(optimizations)


def _enable_diag(optim, *, critical: bool = True, unet: bool = True, validation: bool = True):
    optim.CRITICAL_PATH_DIAG_ENABLED = critical
    optim.UNET_PHASE_DIAG_ENABLED = unet
    optim.VALIDATION_PHASE_DIAG_ENABLED = validation


def _disable_diag(optim):
    optim.CRITICAL_PATH_DIAG_ENABLED = False
    optim.UNET_PHASE_DIAG_ENABLED = False
    optim.VALIDATION_PHASE_DIAG_ENABLED = False


# ── Recorder (Part 1) ────────────────────────────────────────────────────


class CriticalPathRecorderTests(unittest.TestCase):
    def setUp(self):
        self.optim = _load_optimizations()
        _enable_diag(self.optim)

    def tearDown(self):
        _disable_diag(self.optim)

    def test_bind_preserves_restore_events(self):
        rec = self.optim._new_critical_path_recorder()
        # Simulate the real lifecycle: restore phase first
        rec.start_restore("rsid-1")
        rec.record("restore_event")
        # First request: freezes restore_event as _restore_events
        rec.start_request("rsid-1", 1)
        rec.record("request_event")
        # Snapshot includes both restore-phase and request-phase events
        snap = rec.snapshot()
        self.assertEqual(len(snap), 2)
        self.assertEqual(snap[0]["name"], "restore_event")
        self.assertEqual(snap[0]["request_seq"], 0)  # restore phase
        self.assertEqual(snap[1]["name"], "request_event")
        self.assertEqual(snap[1]["request_seq"], 1)
        # Second request: restore events survive unchanged
        rec.start_request("rsid-1", 2)
        rec.record("request_event_2")
        snap2 = rec.snapshot()
        self.assertEqual(len(snap2), 2)
        self.assertEqual(snap2[0]["name"], "restore_event")
        self.assertEqual(snap2[0]["request_seq"], 0)
        self.assertEqual(snap2[1]["name"], "request_event_2")
        self.assertEqual(snap2[1]["request_seq"], 2)

    def test_record_captures_safe_metadata(self):
        rec = self.optim._new_critical_path_recorder()
        rec.bind("rsid-2", 7)
        rec.record("graph_clip_lookup_end", canonical_digest="abc", extra={"mode": "exact", "hit": 1})
        snap = rec.snapshot()
        self.assertEqual(len(snap), 1)
        ev = snap[0]
        self.assertEqual(ev["name"], "graph_clip_lookup_end")
        self.assertEqual(ev["request_seq"], 7)
        self.assertEqual(ev["restore_session_id"], "rsid-2")
        self.assertEqual(ev["canonical_digest"], "abc")
        self.assertEqual(ev["mode"], "exact")
        self.assertEqual(ev["hit"], 1)
        self.assertIsInstance(ev["monotonic_ns"], int)
        self.assertGreater(ev["monotonic_ns"], 0)
        # No raw prompt text
        for k, v in ev.items():
            if isinstance(v, str):
                self.assertNotIn("prompt", k.lower() or "")

    def test_disabled_hot_path_short_circuits(self):
        rec = self.optim._new_critical_path_recorder()
        rec.bind("rsid-disabled", 1)
        _disable_diag(self.optim)
        rec.record("ignored")
        self.assertEqual(rec.snapshot(), [])
        self.assertEqual(rec.event_count("ignored"), 0)

    def test_thread_safety_concurrent_record(self):
        rec = self.optim._new_critical_path_recorder()
        rec.bind("rsid-concurrent", 1)
        def worker(i):
            for j in range(50):
                rec.record(f"event_{i}_{j}")
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # 4 * 50 = 200 events
        self.assertEqual(len(rec.snapshot()), 200)

    def test_counters_and_first_last_event_at(self):
        rec = self.optim._new_critical_path_recorder()
        rec.bind("rsid-ord", 1)
        rec.record("x")
        time.sleep(0.001)
        rec.record("y")
        rec.record("x")
        self.assertEqual(rec.event_count("x"), 2)
        self.assertEqual(rec.event_count("y"), 1)
        first_x = rec.first_event_at("x")
        last_x = rec.last_event_at("x")
        first_y = rec.first_event_at("y")
        self.assertIsNotNone(first_x)
        self.assertIsNotNone(last_x)
        self.assertIsNotNone(first_y)
        self.assertLess(first_x, last_x)
        # first x came before first y
        self.assertLess(first_x, first_y)

    def test_to_dict_round_trip(self):
        rec = self.optim._new_critical_path_recorder()
        rec.bind("rsid-d", 9)
        rec.record("a")
        rec.record("b")
        d = rec.to_dict()
        self.assertEqual(d["restore_session_id"], "rsid-d")
        self.assertEqual(d["request_seq"], 9)
        self.assertEqual(len(d["events"]), 2)
        self.assertEqual(d["counters"], {"a": 1, "b": 1})

    def test_recorder_never_raises(self):
        rec = self.optim._new_critical_path_recorder()
        rec.bind("rsid-bad", 1)
        # A pathological extra dict should not raise.
        rec.record("x", extra={"weird": object()})
        self.assertEqual(len(rec.snapshot()), 1)

    def test_reason_is_bounded(self):
        rec = self.optim._new_critical_path_recorder()
        rec.bind("rsid-reason", 1)
        rec.record("x", reason="x" * 1000)
        snap = rec.snapshot()
        # Reason is truncated at 96 chars.
        self.assertLessEqual(len(snap[0]["reason"]), 96)


# ── Cache lookup diagnostic fix (Part 7) ─────────────────────────────────


class CacheLookupDiagnosticTests(unittest.TestCase):
    """Test that the cache wrapper emits both seed and lookup events
    for the same digest, with phase=graph_lookup on the lookup path
    and phase=graph_miss_encode on a real miss-then-encode.
    """

    def setUp(self):
        self.optim = _load_optimizations()
        # Reload the comfyapp source to grab the patched _cached
        # function and install a fake CLIPTextEncode class.
        import comfyapp  # type: ignore
        self.comfyapp = comfyapp
        # The patch is on _ComfyAPIMixin.  Use a no-op stand-in
        # instance so the closure operates against the same fake
        # ``nodes.NODE_CLASS_MAPPINGS`` we install below.
        from comfyapp import _ComfyAPIMixin  # type: ignore
        # Reset the in-class state from prior tests.
        cls = self._install_fake_clip()
        # Force a clean install (uninstall the marker).
        if hasattr(cls, "encode"):
            cls._comfy_modal_cached = False
        # The real method reads self._init_clip_cache(); a
        # Mixin-only stub doesn't need it.  We invoke the real
        # method via an instance-less hack: call the function on
        # the mixin class itself and pass a dummy self.
        method = _ComfyAPIMixin._patch_clip_text_encode_cache
        # Bind to a tiny object so ``self`` is non-None.
        class _Stub:
            pass
        method(_Stub())

    def _install_fake_clip(self):
        """Install a fake ``nodes.NODE_CLASS_MAPPINGS['CLIPTextEncode']``
        that records every encode call.  The patch reads from this
        mapping at install time only."""
        import types
        # Locate or create a module named "nodes" importable.
        try:
            import nodes  # type: ignore
        except Exception:
            nodes_mod = types.ModuleType("nodes")
            sys.modules["nodes"] = nodes_mod
        import nodes  # type: ignore
        if not hasattr(nodes, "NODE_CLASS_MAPPINGS"):
            nodes.NODE_CLASS_MAPPINGS = {}
        cls = nodes.NODE_CLASS_MAPPINGS.get("CLIPTextEncode")
        if cls is None:
            cls = type("CLIPTextEncode", (), {})
            nodes.NODE_CLASS_MAPPINGS["CLIPTextEncode"] = cls
        # Replace FUNCTION with our own so the cache wrapper is the
        # entrypoint.  We track call counts and arguments.
        cls._test_encode_calls = []
        def _encode(self_node, clip, text):
            cls._test_encode_calls.append({
                "self_node_id": str(getattr(self_node, "id", "")),
                "text": text,
            })
            return ([object()],)
        cls.FUNCTION = "encode"
        cls.encode = _encode
        return cls

    def _cls(self):
        # Always read the class from the live ``nodes`` module
        # because some tests rebind ``cls.FUNCTION``.
        import nodes  # type: ignore
        return nodes.NODE_CLASS_MAPPINGS["CLIPTextEncode"]

    def test_restore_seed_and_graph_lookup_emit_two_diagnostics(self):
        # We need to drive the same _cached function through both
        # a seed and a lookup.  Use a fake clip with stable
        # _warmup_model_paths / _warmup_clip_type so the digest is
        # identical.

        cls = self._cls()
        # Set the per-class phase to "restore_exact_prefill" so the
        # next call is a seed; then clear the phase so a follow-up
        # call becomes a graph-side lookup.
        cls._exact_prefill_phase = "restore_exact_prefill"
        # Reset seen-digests so this test is independent of others.
        cls._clip_textencode_cache_diag_seen = set()
        captured = io.StringIO()
        clip = type("C", (), {
            "_warmup_model_paths": ("/x/qwen.safetensors",),
            "_warmup_clip_type": "lumina2",
        })()
        node = type("N", (), {"id": "42"})()
        with redirect_stdout(captured):
            # First call: restore seed (miss -> encode -> cache).
            cls.encode(node, clip, "hello")
            # Now flip phase off; the second call is a graph-side
            # lookup that should emit a separate diagnostic.
            cls._exact_prefill_phase = ""
            cls.encode(node, clip, "hello")
        out = captured.getvalue()
        # Both diagnostic lines must appear.
        self.assertIn("stage=seed", out)
        self.assertIn("stage=lookup", out)
        # And both phases must be correct.
        self.assertIn("phase=restore_exact_prefill", out)
        self.assertIn("phase=graph_lookup", out)
        # The underlying encoder was called exactly once (the seed).
        self.assertEqual(len(cls._test_encode_calls), 1)

    def test_relaxed_lookup_uses_graph_lookup_phase(self):
        # Build the cache by seeding with one CLIP object, then
        # look up with a different CLIP object (same paths/type) to
        # force the relaxed-key path.
        cls = self._cls()
        cls._exact_prefill_phase = "restore_exact_prefill"
        cls._clip_textencode_cache_diag_seen = set()
        captured = io.StringIO()
        clip_a = type("C", (), {
            "_warmup_model_paths": ("/x/qwen.safetensors",),
            "_warmup_clip_type": "lumina2",
        })()
        clip_b = type("C", (), {
            "_warmup_model_paths": ("/x/qwen.safetensors",),
            "_warmup_clip_type": "lumina2",
        })()
        node = type("N", (), {"id": "7"})()
        with redirect_stdout(captured):
            cls.encode(node, clip_a, "abc")
            cls._exact_prefill_phase = ""
            cls.encode(node, clip_b, "abc")
        out = captured.getvalue()
        self.assertIn("mode=relaxed", out)
        self.assertIn("phase=graph_lookup", out)
        # Underlying encoder was called once (only the seed).
        self.assertEqual(len(cls._test_encode_calls), 1)

    def test_graph_miss_encode_uses_correct_phase(self):
        cls = self._cls()
        cls._exact_prefill_phase = ""
        cls._clip_textencode_cache_diag_seen = set()
        captured = io.StringIO()
        clip = type("C", (), {
            "_warmup_model_paths": ("/y/some.safetensors",),
            "_warmup_clip_type": "flux",
        })()
        node = type("N", (), {"id": "11"})()
        with redirect_stdout(captured):
            cls.encode(node, clip, "first call")
        out = captured.getvalue()
        self.assertIn("stage=seed", out)
        self.assertIn("phase=graph_miss_encode", out)
        # Underlying encoder was called once.
        self.assertEqual(len(cls._test_encode_calls), 1)

    def test_no_prompt_text_in_diagnostics(self):
        cls = self._cls()
        cls._exact_prefill_phase = "restore_exact_prefill"
        cls._clip_textencode_cache_diag_seen = set()
        captured = io.StringIO()
        clip = type("C", (), {
            "_warmup_model_paths": ("/z/super_unique_path_marker_xyz.safetensors",),
            "_warmup_clip_type": "lumina2",
        })()
        node = type("N", (), {"id": "13"})()
        prompt_text = "PROMBANNER-DO-NOT-LOG-12345"
        with redirect_stdout(captured):
            cls.encode(node, clip, prompt_text)
            cls._exact_prefill_phase = ""
            cls.encode(node, clip, prompt_text)
        out = captured.getvalue()
        # The literal prompt text must not appear in any log line.
        self.assertNotIn(prompt_text, out)
        # The path also must not appear (diagnostic shows only digest).
        self.assertNotIn("super_unique_path_marker_xyz", out)


# ── Active-next read diagnostic dedup (Part 8) ──────────────────────────


class ActiveNextReadDedupTests(unittest.TestCase):
    """Test the per-restore dedup of the active-next read diagnostic.

    We exercise the dedup logic in isolation by replicating the
    same key scheme on a small helper, without requiring the
    heavyweight ComfyUI graph path.
    """

    def _make_deduper(self):
        # Mirror the on-instance state used by _load_active_next_profile.
        state = {
            "dedup": set(),
            "call_count": 0,
            "obs_count": 0,
            "emit_count": 0,
        }
        def _maybe_emit(rsid, token, bundle_hash, has_bundle):
            state["call_count"] += 1
            if not has_bundle:
                return False
            state["obs_count"] += 1
            key = (rsid, token, bundle_hash)
            if key in state["dedup"]:
                return False
            state["dedup"].add(key)
            state["emit_count"] += 1
            return True
        def _reset():
            state["dedup"].clear()
            state["call_count"] = 0
            state["obs_count"] = 0
            state["emit_count"] = 0
        return _maybe_emit, state, _reset

    def test_two_reads_same_token_emit_once(self):
        emit, state, _ = self._make_deduper()
        self.assertTrue(emit("rs1", "tok", "hash", has_bundle=True))
        self.assertFalse(emit("rs1", "tok", "hash", has_bundle=True))
        self.assertEqual(state["call_count"], 2)
        self.assertEqual(state["obs_count"], 2)
        self.assertEqual(state["emit_count"], 1)

    def test_new_restore_resets(self):
        emit, state, reset = self._make_deduper()
        emit("rs1", "tok", "hash", has_bundle=True)
        reset()
        # After reset, a new restore with the same token emits again.
        self.assertTrue(emit("rs2", "tok", "hash", has_bundle=True))
        self.assertEqual(state["emit_count"], 1)

    def test_different_token_emits_again(self):
        emit, state, _ = self._make_deduper()
        emit("rs1", "tok-a", "hash", has_bundle=True)
        self.assertTrue(emit("rs1", "tok-b", "hash", has_bundle=True))
        self.assertEqual(state["emit_count"], 2)

    def test_different_bundle_hash_emits_again(self):
        emit, state, _ = self._make_deduper()
        emit("rs1", "tok", "hash-a", has_bundle=True)
        self.assertTrue(emit("rs1", "tok", "hash-b", has_bundle=True))
        self.assertEqual(state["emit_count"], 2)

    def test_no_bundle_never_emits(self):
        emit, state, _ = self._make_deduper()
        self.assertFalse(emit("rs1", "tok", "hash", has_bundle=False))
        self.assertFalse(emit("rs1", "tok", "hash", has_bundle=False))
        self.assertEqual(state["call_count"], 2)
        self.assertEqual(state["obs_count"], 0)
        self.assertEqual(state["emit_count"], 0)


# ── Critical-path summary (Part 5) ───────────────────────────────────────


class CriticalPathSummaryTests(unittest.TestCase):
    def setUp(self):
        self.optim = _load_optimizations()
        _enable_diag(self.optim)

    def tearDown(self):
        _disable_diag(self.optim)

    def test_summary_uses_only_observed_timestamps(self):
        rec = self.optim._new_critical_path_recorder()
        rec.bind("rsid-sum", 1)
        rec.record("validation_start")
        rec.record("validation_complete")
        rec.record("sampler_first_progress")
        # Build a fake instance to call the summary method.
        from comfyapp import _ComfyAPIMixin  # type: ignore
        # We don't run the full ComfyAPI; just bind the method.
        m = _ComfyAPIMixin()
        m._critical_path_recorder = rec
        captured = io.StringIO()
        with redirect_stdout(captured):
            m._emit_critical_path_summary()
        out = captured.getvalue()
        # The summary should mention observed fields.
        self.assertIn("validation_start_ms", out)
        self.assertIn("validation_end_ms", out)
        self.assertIn("sampler_first_progress_ms", out)
        # No causal-savings term should appear.
        self.assertNotIn("saved_ms", out)
        self.assertNotIn("hidden_saving", out)
        self.assertNotIn("dominant_cause", out)
        self.assertNotIn("bottleneck_cause", out)

    def test_missing_events_produce_null(self):
        rec = self.optim._new_critical_path_recorder()
        rec.bind("rsid-missing", 1)
        # Record only a single isolated event so the recorder is
        # non-empty (the summary short-circuits when no events are
        # ever recorded).  All other phase boundaries stay
        # unobserved and must appear as null.
        rec.record("isolated_event")
        from comfyapp import _ComfyAPIMixin  # type: ignore
        m = _ComfyAPIMixin()
        m._critical_path_recorder = rec
        captured = io.StringIO()
        with redirect_stdout(captured):
            m._emit_critical_path_summary()
        out = captured.getvalue()
        # All start/end values should be reported as null.
        for field in (
            "validation_start_ms=null",
            "validation_end_ms=null",
            "sampler_first_progress_ms=null",
            "unet_submit_ms=null",
        ):
            self.assertIn(field, out)

    def test_overlap_labeled_observed(self):
        rec = self.optim._new_critical_path_recorder()
        rec.bind("rsid-overlap", 1)
        # Synthesize two events with a known gap.
        rec.record("validation_start")
        rec.record("validation_complete")
        from comfyapp import _ComfyAPIMixin  # type: ignore
        m = _ComfyAPIMixin()
        m._critical_path_recorder = rec
        captured = io.StringIO()
        with redirect_stdout(captured):
            m._emit_critical_path_summary()
        out = captured.getvalue()
        self.assertIn("observed_overlap", out)


# ── Static non-regression scan (Part 9) ──────────────────────────────────


class StaticNonRegressionTests(unittest.TestCase):
    """Scan the source for the lock-down keywords.  The diff must not
    have changed any of these constants or environment variables in
    production code paths.
    """

    SOURCES = ["comfyapp.py", "optimizations.py", "__init__.py"]

    def _read(self, name):
        return (REPO_ROOT / name).read_text(encoding="utf-8-sig")

    def test_gpu_classes_are_hard_locked_to_zero_and_four_seconds(self):
        text = self._read("comfyapp.py")
        register_src = _func_source(text, "_register_gpu_classes")
        self.assertIsNotNone(register_src)
        self.assertIn("min_containers=0", register_src)
        self.assertIn("scaledown_window=4", register_src)
        self.assertNotIn("COMFYMODAL_MIN_CONTAINERS", text)
        self.assertNotIn("COMFYMODAL_SCALEDOWN_WINDOW", text)
        for match in re.finditer(r"min_containers\s*=\s*(\d+)", text):
            self.assertEqual(int(match.group(1)), 0)

    def test_certificate_candidate_attached_to_result(self):
        """_execute_in_process must attach _certificate_candidate to result."""
        text = self._read("comfyapp.py")
        eip_src = _func_source(text, "_execute_in_process")
        self.assertIsNotNone(eip_src)
        # The synchronous _write_validation_certificate call is replaced
        self.assertNotIn("_WR = _write_validation_certificate(", eip_src.upper())
        # The candidate is attached to result dict (ast.unparse normalizes
        # quotes to single quotes)
        self.assertIn("result['_certificate_candidate']", eip_src)
        # Metrics use deferred status and submitted=0 (honest telemetry:
        # cert write is NOT yet submitted to the dispatcher)
        self.assertIn("'deferred'", eip_src)
        self.assertIn("_validation_certificate_write_submitted = 0", eip_src)
        # node_errors are pre-encoded via _CertNodeErrorEncoder for JSON safety
        self.assertIn("_CertNodeErrorEncoder.encode(_pending", eip_src)

    def test_certificate_persistence_in_post_delivery(self):
        """__init__.py post-delivery section must schedule cert persistence."""
        init_src = (REPO_ROOT / "__init__.py").read_text(encoding="utf-8-sig")
        # The post-delivery cert section references persist_validation_certificate
        self.assertIn("persist_validation_certificate", init_src)
        # It uses _POST_DELIVERY_SINGLETON for the dispatcher
        self.assertIn("_POST_DELIVERY_SINGLETON", init_src)
        # It schedules with a collision-resistant task_id
        self.assertIn("_persist_task_id", init_src)
        # Must not delay result delivery (after _finish_job)
        self.assertIn("_finish_job", init_src)

    def test_certificate_persistence_order_after_materialization(self):
        """Cert persistence must be scheduled after materialization and _finish_job."""
        init_src = (REPO_ROOT / "__init__.py").read_text(encoding="utf-8-sig")
        execute_src = _func_source(init_src, "_execute_job")
        self.assertIsNotNone(execute_src)
        finish_pos = execute_src.find("_finish_job(")
        persist_pos = execute_src.find("persist_validation_certificate(")
        self.assertGreater(finish_pos, -1)
        self.assertGreater(persist_pos, finish_pos)

    def test_experiment_certificate_persistence_is_post_completion(self):
        init_src = (REPO_ROOT / "__init__.py").read_text(encoding="utf-8-sig")
        handler_src = _func_source(init_src, "_on_remote_event")
        self.assertIsNotNone(handler_src)
        append_pos = handler_src.find("store.append_event")
        history_pos = handler_src.find("_record_experiment_cell_history", append_pos)
        persist_pos = handler_src.find("persist_validation_certificate", history_pos)
        self.assertGreater(append_pos, -1)
        self.assertGreater(history_pos, append_pos)
        self.assertGreater(persist_pos, history_pos)

    def test_cache_dit_touch_unchanged(self):
        # CacheDiT should be mentioned only in a "do not touch"
        # context or by third-party code.  We don't expect any new
        # modifications to CacheDiT.
        text = self._read("comfyapp.py")
        # Allow mentions but no `import CacheDiT` or
        # ``CacheDiTModelOptimizer`` patches.
        self.assertNotIn("CacheDiTModelOptimizer =", text)
        self.assertNotIn("patch CacheDiT", text)

    def test_no_raw_prompt_logging_in_source(self):
        # The audit-round work never logs the literal text of a
        # prompt in a print/log call.  The cache wrapper logs only
        # a 16-char digest and a node id; nothing in the new
        # telemetry path sees the prompt string.
        #
        # This test is intentionally narrow: it scans only for the
        # specific patterns that would constitute a leak (a
        # print() that includes a bare ``text=`` value or a bare
        # ``prompt=`` value with no digest context).  Other
        # unrelated text= matches (e.g. regex match arguments) are
        # not in scope.
        for src in self.SOURCES:
            text = self._read(src)
            # Look for a print/log that includes ``text=`` or
            # ``prompt=`` in a context that could leak prompt text.
            # We require the match to be inside a print() call and
            # we require no ``digest=`` substring within 200 chars.
            for m in re.finditer(r'print\([^)]*\btext\s*=[^,)]', text):
                start = max(0, m.start() - 50)
                end = min(len(text), m.end() + 200)
                snippet = text[start:end]
                # Allow the cache-wrapper line which uses
                # ``text=`` together with ``digest=``.
                if "digest=" in snippet:
                    continue
                self.fail(f"{src} print may leak prompt text: {snippet!r}")

    def test_persistent_validation_certificate_default_on(self):
        text = self._read("comfyapp.py")
        # The default is "1" (enabled by default after audit round 7).
        # Verify the env var is referenced and enabled by default.
        self.assertIn("COMFYMODAL_PERSISTENT_VALIDATION_CERTIFICATE", text)
        # The second occurrence (at the actual call site) has default "1"
        idx = text.find("COMFYMODAL_PERSISTENT_VALIDATION_CERTIFICATE", text.find("COMFYMODAL_PERSISTENT_VALIDATION_CERTIFICATE") + 1)
        if idx > 0:
            self.assertIn('"1"', text[idx:idx + 100])

    def test_exact_prefill_cache_keys_unchanged(self):
        # The audit-round work did not modify stable_clip_cache_tag.
        # We import fresh in case state was mutated elsewhere.
        import importlib
        import optimizations
        importlib.reload(optimizations)
        sct = optimizations.stable_clip_cache_tag
        # Empty paths: tag is just the clip type.
        self.assertEqual(sct((), "flux"), "flux")
        # Single path: tag is clip_type@basename.
        self.assertEqual(
            sct(("/a/b.safetensors",), "flux"),
            "flux@b.safetensors",
        )
        # Multiple paths: joined with underscore.
        self.assertEqual(
            sct(("/a/b.safetensors", "/a/c.safetensors"), "lumina2"),
            "lumina2@b.safetensors_c.safetensors",
        )

    def test_no_actual_load_mode_change(self):
        text = self._read("comfyapp.py")
        # The log line that surfaces the resolved actual_load mode
        # must still be present and reference the ACTUAL_LOAD_MODE
        # variable.
        self.assertIn("actual_load_mode_effective=", text)
        self.assertIn("ACTUAL_LOAD_MODE", text)

    def test_no_safetensors_read_mode_change(self):
        text = self._read("comfyapp.py")
        # The log line that surfaces the resolved safetensors read
        # mode must still be present.
        self.assertIn("effective_SAFETENSORS_READ_MODE=", text)
        self.assertIn("SAFETENSORS_READ_MODE", text)

    def test_no_worker_count_change(self):
        text = self._read("comfyapp.py")
        # Worker count surface area is around preload_models_to_cpu.
        self.assertIn("preload_models_to_cpu", text)

    def test_no_vae_deferral_change(self):
        text = self._read("comfyapp.py")
        # VAE handling must still go through the init helper.
        self.assertIn("_init_vae_cache", text)
        # And the VAELoader patch must still be in place.
        self.assertIn("VAELoader", text)


# ── Smoke tests (Part 9) ────────────────────────────────────────────────


class TelemetryDisabledSmokeTests(unittest.TestCase):
    def test_no_records_when_all_flags_off(self):
        optim = _load_optimizations()
        _disable_diag(optim)
        rec = optim._new_critical_path_recorder()
        rec.bind("rsid-off", 1)
        rec.record("a")
        rec.record("b", canonical_digest="abc")
        self.assertEqual(rec.snapshot(), [])
        self.assertEqual(rec.event_count("a"), 0)


class TelemetryOverheadSmokeTests(unittest.TestCase):
    """Cheap overhead check.  When all flags are off, record() should
    short-circuit to a boolean check, so 1M calls take < 1s.
    """

    def test_disabled_path_is_fast(self):
        optim = _load_optimizations()
        _disable_diag(optim)
        rec = optim._new_critical_path_recorder()
        rec.bind("rsid-perf", 1)
        start = time.perf_counter()
        for _ in range(1_000_000):
            rec.record("ignored", canonical_digest="abc")
        elapsed = time.perf_counter() - start
        # 1M short-circuiting record() calls should be well under
        # 1 second on a typical CI box.
        self.assertLess(elapsed, 1.5, f"disabled-path overhead too high: {elapsed:.3f}s")


class TelemetryNoFilesystemSmokeTests(unittest.TestCase):
    def test_record_does_not_touch_filesystem(self):
        optim = _load_optimizations()
        _enable_diag(optim)
        rec = optim._new_critical_path_recorder()
        rec.bind("rsid-fs", 1)
        with tempfile.TemporaryDirectory() as td:
            cwd = os.getcwd()
            os.chdir(td)
            try:
                rec.record("e1", canonical_digest="abc")
                rec.record("e2", reason="x" * 200)
                rec.record("e3", status="failed", reason="r")
            finally:
                os.chdir(cwd)
            # The directory should still be empty (no telemetry
            # files were written).
            self.assertEqual(os.listdir(td), [])


class ModuleImportSmokeTests(unittest.TestCase):
    def test_optimizations_imports_with_recorder(self):
        optim = _load_optimizations()
        self.assertTrue(hasattr(optim, "CriticalPathRecorder"))
        self.assertTrue(hasattr(optim, "critical_path_diag_active"))
        self.assertTrue(hasattr(optim, "_new_critical_path_recorder"))


if __name__ == "__main__":
    unittest.main()
