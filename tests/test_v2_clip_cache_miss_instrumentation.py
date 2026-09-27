"""Focused tests for the CLIP cache-miss benchmark instrumentation:
lookup timing, miss decision evidence, and the UNET loader boundary."""

from __future__ import annotations

import time
import types
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import comfymodal_runtime.model_preload as mp
from comfymodal_runtime.contracts import ModelRestoreKey, PrefillKey, RestorePlan
from comfymodal_runtime.trace import RuntimeTrace


def _build_bridge(
    *,
    unet_loader: Any = None,
    clip_loader: Any = None,
    invoke_original: Any = None,
    max_workers: int = 2,
) -> mp.V2LoaderBridge:
    bridge = mp.V2LoaderBridge(max_workers=max_workers)
    bridge.install = lambda nodes=None, trace=None: True
    bridge._request_list = lambda bucket: [{"clip_name": "clip_l.safetensors"}]
    bridge._model_spec = {
        "loaders": {
            "unet": [{"unet_name": "unet.safetensors"}],
            "clip": [{"clip_name": "clip_l.safetensors"}],
        }
    }
    bridge.coordinator.clip_loader = clip_loader or (
        lambda key: SimpleNamespace(patcher=SimpleNamespace())
    )
    bridge.coordinator.unet_loader = unet_loader or (lambda key: "unet-done")
    bridge._invoke_original = invoke_original or (
        lambda class_name, kwargs: (f"conditioning:{kwargs['text']}",)
    )
    return bridge


def _make_plan(
    unet_identity: str = "unet.safetensors",
    clip_identity: str = "clip_l.safetensors",
    text: str = "a happy cat",
    role: str = "positive",
) -> RestorePlan:
    model_key = ModelRestoreKey(
        unet_identity=unet_identity,
        clip_identity=clip_identity,
        clip_type="stable_diffusion",
    )
    prefill_key = PrefillKey(
        model_key=model_key,
        prompt_bundle_hash="hash-cache-miss",
        encode_options={
            "eligible": True,
            "encodes": [
                {
                    "node_id": "6",
                    "text": text,
                    "role": role,
                }
            ],
        },
    )
    return RestorePlan(model_key=model_key, prefill_key=prefill_key)


def _wait_future(fut: Any, timeout: float = 5.0) -> Any:
    if fut is None:
        return None
    return fut.result(timeout=timeout)


def _event_meta(trace: RuntimeTrace, name: str) -> list[dict[str, Any]]:
    return [dict(e.metadata) for e in trace.events if e.name == name]


def _event_names(trace: RuntimeTrace) -> set[str]:
    return {e.name for e in trace.events}


class _FakeConditioningCache:
    """Minimal stand-in for ``ExactConditioningCache``."""

    def __init__(
        self,
        *,
        hit_count: int = 0,
        store_ok: bool = True,
        last_store_reason: str = "",
        store_delay_s: float = 0.0,
    ) -> None:
        self._hit_count = int(hit_count)
        self._store_ok = bool(store_ok)
        self._store_delay_s = float(store_delay_s)
        self.last_store_reason = last_store_reason
        self.lookup_calls = 0
        self.store_calls = 0

    def lookup_many(
        self,
        base_ctx: Any,
        entries: list[dict[str, Any]],
    ) -> tuple[dict[int, Any], list[dict[str, Any]], int, int]:
        self.lookup_calls += 1
        hits: dict[int, Any] = {}
        misses: list[dict[str, Any]] = []
        for index, entry in enumerate(entries):
            if index < self._hit_count:
                hits[index] = (f"cached:{entry.get('text', '')}",)
            else:
                misses.append(dict(entry))
        return hits, misses, len(hits), len(misses)

    def store_entry(self, base_ctx: Any, entry: dict[str, Any], value: Any) -> bool:
        self.store_calls += 1
        if self._store_delay_s > 0:
            time.sleep(self._store_delay_s)
        return self._store_ok

    def latest_lookup_diagnostics(self) -> dict[str, Any]:
        return {"lookup_calls": self.lookup_calls}

    def pop_store_diagnostics(self) -> dict[str, Any]:
        return {"store_calls": self.store_calls}


class TestCacheLookupInstrumentation:
    """``lookup_wall_ms`` on the lookup event and the pre-encode miss log."""

    def _run_miss_flow(self, fake_cache: _FakeConditioningCache):
        encode_calls: list[str] = []

        def tracking_encode(class_name: str, kwargs: dict[str, Any]) -> tuple[str, ...]:
            encode_calls.append(kwargs.get("text", ""))
            return (f"conditioning:{kwargs['text']}",)

        bridge = _build_bridge(invoke_original=tracking_encode, max_workers=2)
        trace = RuntimeTrace(request_id="cache-miss-req", process="remote")
        plan = _make_plan()
        decisions: list[dict[str, Any]] = []
        trace_snapshots: list[set[str]] = []

        def _recording_decisions(decision: str, **kv: Any) -> None:
            decisions.append({"decision": decision, **kv})
            if decision == "miss" and trace is not None:
                trace_snapshots.append({e.name for e in trace.events})

        with patch.object(
            mp, "get_exact_conditioning_cache", return_value=fake_cache
        ), patch.object(
            mp, "log_conditioning_cache_decision", side_effect=_recording_decisions
        ):
            bridge.prepare(plan, trace=trace)
            prep = bridge._preparation
            assert prep is not None
            assert bridge.schedule_execution_prefill(trace=trace) is True
            results = _wait_future(prep.prefill_future)
        bridge.coordinator.close()
        return {
            "bridge": bridge,
            "trace": trace,
            "results": results,
            "encode_calls": encode_calls,
            "decisions": decisions,
            "trace_snapshots": trace_snapshots,
            "prep": prep,
        }

    def test_lookup_event_carries_lookup_wall_ms_on_miss(self):
        fake_cache = _FakeConditioningCache(hit_count=0, store_ok=True)
        artifacts = self._run_miss_flow(fake_cache)
        trace = artifacts["trace"]

        assert fake_cache.lookup_calls == 1
        lookups = _event_meta(trace, "clip_conditioning_cache_lookup")
        assert len(lookups) == 1
        meta = lookups[0]
        assert meta["hit_count"] == 0
        assert meta["miss_count"] == 1
        assert meta["entry_count"] == 1
        assert isinstance(meta["lookup_wall_ms"], (int, float))
        assert meta["lookup_wall_ms"] >= 0

    def test_decision_miss_logged_before_encode_with_key_summary_and_timing(self):
        fake_cache = _FakeConditioningCache(hit_count=0, store_ok=True)
        artifacts = self._run_miss_flow(fake_cache)
        trace = artifacts["trace"]

        miss_logs = [d for d in artifacts["decisions"] if d["decision"] == "miss"]
        assert len(miss_logs) == 1
        log = miss_logs[0]
        assert log["key_hash"]
        assert log["identity_status"] in ("valid", "invalid")
        assert log["schema_version"] >= 0
        assert log["validation_scope"]
        assert log["hit_count"] == 0
        assert log["miss_count"] == 1
        assert log["entries"] == 1
        assert isinstance(log["lookup_wall_ms"], (int, float))
        assert log["lookup_wall_ms"] >= 0
        assert log["request_id"] == "cache-miss-req"

        assert artifacts["trace_snapshots"], "miss decision was never recorded"
        assert mp._EVENT_ENCODE_START not in artifacts["trace_snapshots"][0]
        assert artifacts["encode_calls"] == ["a happy cat"]
        assert mp._EVENT_ENCODE_START in _event_names(trace)
        names = [e.name for e in trace.events]
        assert names.index("clip_conditioning_cache_lookup") < names.index(
            mp._EVENT_ENCODE_START
        )

    def test_exact_hit_emits_lookup_timing_but_no_miss_log(self):
        fake_cache = _FakeConditioningCache(hit_count=1, store_ok=True)
        artifacts = self._run_miss_flow(fake_cache)
        trace = artifacts["trace"]

        assert fake_cache.lookup_calls == 1
        lookups = _event_meta(trace, "clip_conditioning_cache_lookup")
        assert len(lookups) == 1
        assert lookups[0]["hit_count"] == 1
        assert lookups[0]["miss_count"] == 0
        assert isinstance(lookups[0]["lookup_wall_ms"], (int, float))

        assert [d for d in artifacts["decisions"] if d["decision"] == "miss"] == []
        assert [d for d in artifacts["decisions"] if d["decision"] == "exact_hit"] != []
        assert artifacts["encode_calls"] == []


class TestEncodeEvidence:
    """``encode_loop_wall_ms`` + ``encode_calls`` on the miss decisions."""

    def _run_miss_flow(self, fake_cache: _FakeConditioningCache):
        encode_calls: list[str] = []

        def tracking_encode(class_name: str, kwargs: dict[str, Any]) -> tuple[str, ...]:
            encode_calls.append(kwargs.get("text", ""))
            return (f"conditioning:{kwargs['text']}",)

        bridge = _build_bridge(invoke_original=tracking_encode, max_workers=2)
        trace = RuntimeTrace(request_id="cache-miss-req", process="remote")
        plan = _make_plan()
        decisions: list[dict[str, Any]] = []

        def _recording_decisions(decision: str, **kv: Any) -> None:
            decisions.append({"decision": decision, **kv})

        with patch.object(
            mp, "get_exact_conditioning_cache", return_value=fake_cache
        ), patch.object(
            mp, "log_conditioning_cache_decision", side_effect=_recording_decisions
        ):
            bridge.prepare(plan, trace=trace)
            prep = bridge._preparation
            assert prep is not None
            assert bridge.schedule_execution_prefill(trace=trace) is True
            _wait_future(prep.prefill_future)
        bridge.coordinator.close()
        return {
            "trace": trace,
            "encode_calls": encode_calls,
            "decisions": decisions,
        }

    def test_miss_stored_carries_encode_loop_wall_ms_and_encode_calls(self):
        fake_cache = _FakeConditioningCache(hit_count=0, store_ok=True)
        artifacts = self._run_miss_flow(fake_cache)
        trace = artifacts["trace"]

        assert fake_cache.store_calls == 1
        stored = [e for e in trace.events if e.name == "clip_conditioning_cache_decision"
                  and e.metadata.get("decision") == "miss_stored"]
        assert len(stored) == 1
        meta = stored[0].metadata
        assert meta["encode_calls"] == 1
        assert isinstance(meta["encode_loop_wall_ms"], (int, float))
        assert meta["encode_loop_wall_ms"] >= 0
        assert meta["stored_count"] == 1
        assert meta["cache_store_calls"] == 1
        assert isinstance(meta["cache_store_wall_ms"], (int, float))
        assert meta["cache_store_wall_ms"] >= 0

        stored_logs = [d for d in artifacts["decisions"] if d["decision"] == "miss_stored"]
        assert len(stored_logs) == 1
        assert stored_logs[0]["encode_calls"] == 1
        assert isinstance(stored_logs[0]["encode_loop_wall_ms"], (int, float))
        assert stored_logs[0]["encode_loop_wall_ms"] >= 0
        assert stored_logs[0]["cache_store_calls"] == 1
        assert isinstance(stored_logs[0]["cache_store_wall_ms"], (int, float))
        assert stored_logs[0]["cache_store_wall_ms"] >= 0

        completed = [e for e in trace.events if e.name == mp._EVENT_COMPLETED]
        assert completed and completed[0].metadata.get("encoded_count") == 1

    def test_miss_not_stored_carries_encode_loop_wall_ms_and_encode_calls(self):
        fake_cache = _FakeConditioningCache(
            hit_count=0, store_ok=False, last_store_reason="test-no-store"
        )
        artifacts = self._run_miss_flow(fake_cache)
        trace = artifacts["trace"]

        assert fake_cache.store_calls == 1
        not_stored = [
            e for e in trace.events
            if e.name == "clip_conditioning_cache_decision"
            and e.metadata.get("decision") == "miss_not_stored"
        ]
        assert len(not_stored) == 1
        meta = not_stored[0].metadata
        assert meta["encode_calls"] == 1
        assert isinstance(meta["encode_loop_wall_ms"], (int, float))
        assert meta["encode_loop_wall_ms"] >= 0
        assert meta["entry_count"] == 1
        assert meta["reason"] == "test-no-store"
        assert meta["cache_store_calls"] == 1
        assert isinstance(meta["cache_store_wall_ms"], (int, float))
        assert meta["cache_store_wall_ms"] >= 0

        assert [d for d in artifacts["decisions"] if d["decision"] == "miss_stored"] == []
        assert artifacts["encode_calls"] == ["a happy cat"]

    def test_cache_store_wall_ms_aggregates_real_store_duration(self):
        fake_cache = _FakeConditioningCache(
            hit_count=0, store_ok=True, store_delay_s=0.05,
        )
        artifacts = self._run_miss_flow(fake_cache)
        trace = artifacts["trace"]

        assert fake_cache.store_calls == 1
        stored = [e for e in trace.events if e.name == "clip_conditioning_cache_decision"
                  and e.metadata.get("decision") == "miss_stored"]
        assert len(stored) == 1
        meta = stored[0].metadata
        assert meta["cache_store_calls"] == 1
        assert meta["cache_store_wall_ms"] >= 10.0


class _FakeDiffusionModel:
    """Weakref-able diffusion-model stand-in for the forward-probe registry."""

    def named_parameters(self, recurse: bool = True):
        return iter([])

    def named_buffers(self, recurse: bool = True):
        return iter([])

    def forward(self, x: Any) -> Any:
        return x

    def register_forward_pre_hook(self, hook: Any, with_kwargs: bool = False) -> Any:
        return None

    def register_forward_hook(self, hook: Any) -> Any:
        return None


class _FakeUnet:
    """Weakref-able fake UNET accepted by ``collect_unet_runtime_state``
    and ``register_unet_forward_probe``."""

    def __init__(self) -> None:
        self.model = SimpleNamespace(diffusion_model=_FakeDiffusionModel())
        self.load_device = "cpu"
        self.offload_device = "cpu"
        self.weight_dtype = "default"


def _fake_unet_for_load() -> _FakeUnet:
    return _FakeUnet()


class TestUnetLoaderBoundary:
    """``unet_loader_start/end`` around the production UNETLoader call."""

    def setup_method(self):
        self._token = mp._ACTIVE_REQUEST_TRACE.set(None)
        self._model_key = ModelRestoreKey(
            unet_identity="test.safetensors",
            clip_identity="",
            clip_type="sd",
        )
        self._bridge = mp.V2LoaderBridge()
        self._bridge._original_methods = {
            "UNETLoader.load_unet": lambda self, unet_name, weight_dtype: (object(),)
        }
        self._bridge._model_spec = {
            "loaders": {
                "unet": [{"unet_name": "test.safetensors", "weight_dtype": "default"}],
                "clip": [],
            },
        }
        self._bridge._model_key = self._model_key

    def teardown_method(self):
        mp._ACTIVE_REQUEST_TRACE.reset(self._token)

    def test_success_emits_wall_timestamped_loader_start_and_end(self):
        trace = RuntimeTrace(request_id="unet-loader-req", process="remote")
        self._bridge._trace = trace
        self._bridge._invoke_original = lambda class_name, kwargs: (
            _fake_unet_for_load(),
        )

        self._bridge._load_unet(self._model_key)

        starts = [e for e in trace.events if e.name == "unet_loader_start"]
        ends = [e for e in trace.events if e.name == "unet_loader_end"]
        assert len(starts) == 1, [e.name for e in trace.events]
        assert len(ends) == 1
        assert not [e for e in trace.events
                    if e.name in ("unet_prepare_start", "unet_prepare_end")]

        start_meta = dict(starts[0].metadata)
        end_meta = dict(ends[0].metadata)
        assert isinstance(starts[0].wall_unix_ns, int) and starts[0].wall_unix_ns > 0
        assert isinstance(ends[0].wall_unix_ns, int) and ends[0].wall_unix_ns > 0
        assert end_meta["status"] == "ok"
        assert start_meta["unet_identity"] == "test.safetensors"
        assert start_meta["requested_weight_dtype"] == "default"
        assert start_meta["request_id"] == "unet-loader-req"

        assert isinstance(end_meta["wall_ms"], (int, float))
        assert end_meta["wall_ms"] >= 0
        expected_ms = (ends[0].monotonic_ns - starts[0].monotonic_ns) / 1_000_000
        assert abs(end_meta["wall_ms"] - expected_ms) < 1.0

        names = [e.name for e in trace.events]
        assert names.index("unet_loader_start") < names.index("unet_loader_end")
        assert ends[0].monotonic_ns >= starts[0].monotonic_ns

    def test_failure_emits_error_end_and_does_not_claim_success(self):
        trace = RuntimeTrace(request_id="unet-loader-fail", process="remote")
        self._bridge._trace = trace

        def _boom(class_name: str, kwargs: dict[str, Any]) -> Any:
            raise RuntimeError("simulated UNET loader failure")

        self._bridge._invoke_original = _boom
        try:
            self._bridge._load_unet(self._model_key)
        except RuntimeError as exc:
            assert "simulated UNET loader failure" in str(exc)
        else:
            raise AssertionError("_load_unet must propagate the loader error")

        ends = [e for e in trace.events if e.name == "unet_loader_end"]
        assert len(ends) == 1
        assert ends[0].metadata.get("status") == "error"
        assert isinstance(ends[0].wall_unix_ns, int) and ends[0].wall_unix_ns > 0
        assert isinstance(ends[0].metadata.get("wall_ms"), (int, float))
        assert ends[0].metadata["wall_ms"] >= 0
        assert not [e for e in trace.events
                    if e.name == "unet_loader_end"
                    and e.metadata.get("status") == "ok"]


def _make_fake_clip_classes():
    class _FakeCondStageModel:
        def __init__(self):
            self.forward_calls = []

        def encode_token_weights(self, tokens):
            self.forward_calls.append(tokens)
            return ("pooled", tokens)

    class _FakeCLIP:
        def __init__(self):
            self.cond_stage_model = _FakeCondStageModel()
            self.tokenize_calls = []
            self.load_calls = []
            self.encode_calls = []
            self.scheduled_calls = []

        def tokenize(self, text):
            self.tokenize_calls.append(text)
            return {"tokens": text}

        def load_model(self):
            self.load_calls.append(True)
            return None

        def encode_from_tokens(self, tokens, return_pooled=False, return_dict=False):
            self.encode_calls.append(tokens)
            self.load_model()
            return self.cond_stage_model.encode_token_weights(tokens)

        def encode_from_tokens_scheduled(self, tokens, encode_func=None):
            self.scheduled_calls.append(tokens)
            return self.encode_from_tokens(tokens)

    return _FakeCLIP


def _fake_sd_module(clip_cls):
    fake_sd = types.ModuleType("comfy.sd")
    fake_sd.CLIP = clip_cls
    return fake_sd


def _run_with_request_trace(trace, fn):
    token = mp._ACTIVE_REQUEST_TRACE.set(trace)
    try:
        return fn()
    finally:
        mp._ACTIVE_REQUEST_TRACE.reset(token)


class TestClipSpanInstrumentation:
    """Request-scoped CLIP spans: tokenize/gpu_prepare/raw_encode/forward/
    scheduled_conditioning with start/end wall+monotonic timestamps."""

    def test_spans_nest_and_order_for_single_encode(self):
        _CLIP = _make_fake_clip_classes()
        statuses = mp._install_clip_span_wrappers(_fake_sd_module(_CLIP))
        assert set(statuses.values()) == {"installed"}
        clip = _CLIP()
        trace = RuntimeTrace(request_id="span-nest", process="remote")

        def _run():
            tokens = clip.tokenize("a cat")
            clip.encode_from_tokens(tokens)
            clip.encode_from_tokens_scheduled(tokens)

        _run_with_request_trace(trace, _run)

        def _mono(name):
            return [e.monotonic_ns for e in trace.events if e.name == name]

        assert len(_mono("clip_tokenize_start")) == 1
        assert len(_mono("clip_tokenize_end")) == 1
        assert len(_mono("clip_scheduled_conditioning_start")) == 1
        assert len(_mono("clip_scheduled_conditioning_end")) == 1
        assert len(_mono("clip_raw_encode_start")) == 2
        assert len(_mono("clip_raw_encode_end")) == 2
        assert len(_mono("clip_gpu_prepare_start")) == 2
        assert len(_mono("clip_gpu_prepare_end")) == 2
        assert len(_mono("clip_forward_start")) == 2
        assert len(_mono("clip_forward_end")) == 2

        def _idx(name, k=0):
            return [i for i, e in enumerate(trace.events) if e.name == name][k]

        assert _idx("clip_tokenize_start") < _idx("clip_tokenize_end") < _idx("clip_raw_encode_start")
        assert _idx("clip_raw_encode_start") < _idx("clip_gpu_prepare_start")
        assert _idx("clip_gpu_prepare_end") < _idx("clip_forward_start")
        assert _idx("clip_forward_end") < _idx("clip_raw_encode_end")
        assert _idx("clip_raw_encode_end") < _idx("clip_scheduled_conditioning_start")
        assert _idx("clip_scheduled_conditioning_start") < _idx("clip_raw_encode_start", 1)
        assert _idx("clip_raw_encode_end", 1) < _idx("clip_scheduled_conditioning_end")
        for name in ("clip_tokenize", "clip_gpu_prepare", "clip_raw_encode",
                     "clip_forward", "clip_scheduled_conditioning"):
            starts = [e for e in trace.events if e.name == f"{name}_start"]
            ends = [e for e in trace.events if e.name == f"{name}_end"]
            for s, e in zip(starts, ends):
                assert e.monotonic_ns >= s.monotonic_ns
                assert e.wall_unix_ns >= s.wall_unix_ns

        for ev in trace.events:
            if not ev.name.endswith("_end"):
                continue
            assert isinstance(ev.wall_unix_ns, int) and ev.wall_unix_ns > 0
            assert isinstance(ev.monotonic_ns, int)
            meta = ev.metadata
            assert meta["status"] == "ok"
            assert isinstance(meta["duration_ms"], (int, float))
            assert meta["duration_ms"] >= 0
            assert meta["thread_cpu_ms"] is None or isinstance(meta["thread_cpu_ms"], (int, float))
            assert isinstance(meta["process_cpu_ms"], (int, float))
            for key in ("thread_minor_faults", "thread_major_faults",
                        "process_minor_faults", "process_major_faults"):
                assert key in meta

    def test_forward_wrapper_installed_on_dynamic_class_before_first_call(self):
        _CLIP = _make_fake_clip_classes()
        clip = _CLIP()
        csm = clip.cond_stage_model
        trace = RuntimeTrace(request_id="span-fwd", process="remote")

        def _run():
            assert mp._ensure_clip_forward_wrapper(clip) == "installed"
            assert mp._ensure_clip_forward_wrapper(clip) == "already_installed"
            bound = csm.encode_token_weights
            assert bound.__name__ == "encode_token_weights"
            result = bound({"tok": 1})
            assert result == ("pooled", {"tok": 1})
            return result

        result = _run_with_request_trace(trace, _run)
        assert csm.forward_calls == [{"tok": 1}]
        assert result == ("pooled", {"tok": 1})
        fwd_starts = [e for e in trace.events if e.name == "clip_forward_start"]
        fwd_ends = [e for e in trace.events if e.name == "clip_forward_end"]
        assert len(fwd_starts) == 1
        assert len(fwd_ends) == 1
        assert fwd_ends[0].metadata["status"] == "ok"
        assert fwd_starts[0].metadata["clip_span"] == "clip_forward"

    def test_exception_preserved_and_span_paired_with_error_status(self):
        class _BoomCLIP:
            def __init__(self):
                self.cond_stage_model = SimpleNamespace()

            def encode_from_tokens(self, tokens, return_pooled=False, return_dict=False):
                raise RuntimeError("span-boom")

        fake_sd = _fake_sd_module(_BoomCLIP)
        assert mp._install_clip_span_wrappers(fake_sd)["clip_raw_encode"] == "installed"
        trace = RuntimeTrace(request_id="span-exc", process="remote")

        def _run():
            _BoomCLIP().encode_from_tokens({"tok": 1})

        try:
            _run_with_request_trace(trace, _run)
        except RuntimeError as exc:
            assert "span-boom" in str(exc)
        else:
            raise AssertionError("span wrapper must preserve the exception")

        starts = [e for e in trace.events if e.name == "clip_raw_encode_start"]
        ends = [e for e in trace.events if e.name == "clip_raw_encode_end"]
        assert len(starts) == 1
        assert len(ends) == 1
        assert ends[0].metadata["status"] == "error"

    def test_install_is_idempotent_no_double_wrap(self):
        _CLIP = _make_fake_clip_classes()
        fake_sd = _fake_sd_module(_CLIP)
        r1 = mp._install_clip_span_wrappers(fake_sd)
        r2 = mp._install_clip_span_wrappers(fake_sd)
        assert set(r1.values()) == {"installed"}
        assert set(r2.values()) == {"already_installed"}
        clip = _CLIP()
        trace = RuntimeTrace(request_id="span-idem", process="remote")

        def _run():
            clip.tokenize("x")
            clip.tokenize("y")

        _run_with_request_trace(trace, _run)
        assert clip.tokenize_calls == ["x", "y"]
        starts = [e for e in trace.events if e.name == "clip_tokenize_start"]
        assert len(starts) == 2

    def test_gpu_prepare_and_forward_metadata_shape_no_cuda_init(self):
        _CLIP = _make_fake_clip_classes()
        mp._install_clip_span_wrappers(_fake_sd_module(_CLIP))
        clip = _CLIP()
        trace = RuntimeTrace(request_id="span-cuda", process="remote")

        def _run():
            mp._ensure_clip_forward_wrapper(clip)
            clip.load_model()
            clip.cond_stage_model.encode_token_weights({"tok": 1})

        _run_with_request_trace(trace, _run)

        gpu_ends = [e for e in trace.events if e.name == "clip_gpu_prepare_end"]
        assert len(gpu_ends) == 1
        gmeta = gpu_ends[0].metadata
        assert gmeta["cuda_no_sync"] is True
        assert "cuda_initialized_before" in gmeta
        assert "cuda_initialized_after" in gmeta
        if not gmeta["cuda_initialized_before"]:
            assert "cuda_allocated_before_bytes" not in gmeta
        for key in ("duration_ms", "process_cpu_ms", "thread_cpu_ms",
                    "thread_minor_faults", "thread_major_faults",
                    "process_minor_faults", "process_major_faults"):
            assert key in gmeta

        fwd_ends = [e for e in trace.events if e.name == "clip_forward_end"]
        assert len(fwd_ends) == 1
        fmeta = fwd_ends[0].metadata
        assert fmeta["cuda_no_sync"] is True
        assert "cuda_initialized_before" in fmeta

    def test_span_wrappers_preserve_result_object(self):
        marker = object()

        class _MarkerCLIP:
            def __init__(self):
                self.cond_stage_model = SimpleNamespace()

            def tokenize(self, text):
                return {"tokens": text}

            def load_model(self):
                return None

            def encode_from_tokens(self, tokens, return_pooled=False, return_dict=False):
                return marker

            def encode_from_tokens_scheduled(self, tokens, encode_func=None):
                return marker

        mp._install_clip_span_wrappers(_fake_sd_module(_MarkerCLIP))
        clip = _MarkerCLIP()
        trace = RuntimeTrace(request_id="span-out", process="remote")

        def _run():
            assert clip.tokenize("t") == {"tokens": "t"}
            assert clip.encode_from_tokens({"tok": 1}) is marker
            assert clip.encode_from_tokens_scheduled({"tok": 1}) is marker
            assert clip.load_model() is None

        _run_with_request_trace(trace, _run)

    def test_spans_emit_from_prefill_worker_via_lane_trace(self):
        _CLIP = _make_fake_clip_classes()
        mp._install_clip_span_wrappers(_fake_sd_module(_CLIP))
        trace = RuntimeTrace(request_id="span-lane-worker", process="remote")
        lane_trace = mp.ModelLaneTrace(trace, "prefill", phase="execution")
        outputs: list[Any] = []

        def worker():
            clip = _CLIP()
            token = mp._ACTIVE_LANE_TRACE.set(lane_trace)
            try:
                tokens = clip.tokenize("a cat")
                outputs.append(clip.encode_from_tokens(tokens))
                outputs.append(clip.encode_from_tokens_scheduled(tokens))
            finally:
                mp._ACTIVE_LANE_TRACE.reset(token)
            return True

        with ThreadPoolExecutor(max_workers=1) as ex:
            assert ex.submit(worker).result(timeout=5) is True

        assert outputs == [("pooled", {"tokens": "a cat"}), ("pooled", {"tokens": "a cat"})]
        names = [e.name for e in trace.events]
        for pair in ("clip_tokenize", "clip_gpu_prepare", "clip_raw_encode",
                     "clip_forward", "clip_scheduled_conditioning"):
            assert f"{pair}_start" in names and f"{pair}_end" in names
        assert names.count("clip_raw_encode_start") == 2
        assert names.count("clip_forward_end") == 2
        assert len({e.trace_id for e in trace.events}) == 1

    def test_worker_exception_preserved_with_error_span(self):
        class _BoomCLIP:
            def __init__(self):
                self.cond_stage_model = SimpleNamespace()

            def encode_from_tokens(self, tokens, return_pooled=False, return_dict=False):
                raise RuntimeError("worker-span-boom")

        mp._install_clip_span_wrappers(_fake_sd_module(_BoomCLIP))
        trace = RuntimeTrace(request_id="span-lane-exc", process="remote")
        lane_trace = mp.ModelLaneTrace(trace, "prefill", phase="execution")

        def worker():
            token = mp._ACTIVE_LANE_TRACE.set(lane_trace)
            try:
                _BoomCLIP().encode_from_tokens({"tok": 1})
            finally:
                mp._ACTIVE_LANE_TRACE.reset(token)
            return True

        with ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(worker)
            exc = fut.exception(timeout=5)
        assert exc is not None and isinstance(exc, RuntimeError)
        assert "worker-span-boom" in str(exc)
        ends = [e for e in trace.events if e.name == "clip_raw_encode_end"]
        assert len(ends) == 1
        assert ends[0].metadata["status"] == "error"
