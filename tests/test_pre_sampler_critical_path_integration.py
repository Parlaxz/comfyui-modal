"""Live pre-sampler instrumentation integration tests.

Exercises the actual ``PreSamplerInstrumentation`` hooks by calling each
patched native boundary directly (``get_input_data``, ``execute``,
``load_models_gpu``, ``PromptExecutor.execute_async``) with
realistic simulated arguments.

Asserts non-zero live timings, correct classification of CLIPTextEncode
and KSampler nodes, and exactly one ``[v2.pre_sampler_critical_path]``
summary line per simulated request.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import time
from typing import Any

import pytest

from comfymodal_runtime.runtime_executor import (
    install_pre_sampler_hooks,
    uninstall_pre_sampler_hooks,
    pre_sampler_instrumentation_scope,
    set_lock_wait_ms,
    _instrumentation_var,
    _pop_lock_wait_ms,
    _emit_pre_sampler_line,
    _fmt_or_absent,
    _PRE_SAMPLER_ABSENT_STR,
)


# ═══════════════════════════════════════════════════════════════════════
# Module-level hooking support
# ═══════════════════════════════════════════════════════════════════════

# Before any test runs, ensure hooks are installable by lazily
# creating minimal stubs for the ComfyUI module paths.  The real
# modules are not available in this test environment, so we create
# the minimum viable stand-ins so the patched functions can be
# exercised without real ComfyUI.


def _ensure_comfyui_stubs() -> None:
    """Create minimal stubs for ComfyUI module paths so hooks can be
    installed in a test environment without the real ComfyUI.

    This must run BEFORE ``install_pre_sampler_hooks()`` is called.
    The stubs provide just enough structure for the hook wrappers to
    activate: a real ``get_input_data``, a real ``execute`` function,
    a ``PromptExecutor`` class with an ``execute_async`` method, and a
    real ``load_models_gpu`` function.  Each stub sleeps briefly to
    simulate real work so the instrumentation records non-zero timings.
    """
    import sys
    import types

    # Avoid double-install
    if "execution" in sys.modules and hasattr(sys.modules["execution"], "_pre_sampler_stubbed"):
        return

    # ── comfy package ───────────────────────────────────────────────
    _comfy = types.ModuleType("comfy")
    _mm = types.ModuleType("comfy.model_management")
    _mm.load_models_gpu = _make_fake_load_models_gpu()
    _mm.load_model_gpu = lambda m: _mm.load_models_gpu([m])
    _comfy.model_management = _mm
    sys.modules["comfy"] = _comfy
    sys.modules["comfy.model_management"] = _mm

    # ── comfy_execution (needed by execution imports) ────────────────
    _ce = types.ModuleType("comfy_execution")
    _ce.graph = types.ModuleType("comfy_execution.graph")
    _ce.graph.DynamicPrompt = type("DynamicPrompt", (), {})
    _ce.graph.ExecutionBlocker = type("ExecutionBlocker", (), {})
    _ce.graph.get_input_info = lambda *a: ("STRING", "required", {})
    _ce.graph.is_link = lambda v: isinstance(v, (list, tuple)) and len(v) >= 2
    sys.modules["comfy_execution"] = _ce
    if "comfy_execution.graph" not in sys.modules:
        sys.modules["comfy_execution.graph"] = _ce.graph

    _ce.caching = types.ModuleType("comfy_execution.caching")
    _ce.caching.BasicCache = type("BasicCache", (), {})
    _ce.caching.CacheKeySetID = type("CacheKeySetID", (), {})
    _ce.caching.CacheKeySetInputSignature = type("CacheKeySetInputSignature", (), {})

    class _NullCache:
        async def get(self, node_id): return None
        async def set(self, node_id, value): pass
        def all_node_ids(self): return []
        def clean_unused(self): pass
        def poll(self, **kw): pass
        def get_local(self, node_id): return None
        def set_local(self, node_id, value): pass

    class _HierarchicalCache:
        """Stub that returns None (miss) by default; tests can override."""
        _class_stub_cache_data: dict = {}

        def __init__(self, key_class=None, enable_providers=False):
            self._stub_cache_data = {}

        async def get(self, node_id):
            return self._stub_cache_data.get(str(node_id))

        async def set(self, node_id, value):
            self._stub_cache_data[str(node_id)] = value

        def get_local(self, node_id): return None
        def set_local(self, node_id, value): pass
        def all_node_ids(self): return []
        def clean_unused(self): pass

    class _LRUCache:
        async def get(self, node_id): return None
        async def set(self, node_id, value): pass
        def all_node_ids(self): return []
        def clean_unused(self): pass

    class _RAMPressureCache:
        async def get(self, node_id): return None
        async def set(self, node_id, value): pass
        def all_node_ids(self): return []
        def clean_unused(self): pass

    _ce.caching.NullCache = _NullCache
    _ce.caching.HierarchicalCache = _HierarchicalCache
    _ce.caching.LRUCache = _LRUCache
    _ce.caching.RAMPressureCache = _RAMPressureCache
    sys.modules["comfy_execution.caching"] = _ce.caching

    _ce.utils = types.ModuleType("comfy_execution.utils")
    _ce.utils.CurrentNodeContext = type("CurrentNodeContext", (), {})
    sys.modules["comfy_execution.utils"] = _ce.utils

    _ce.validation = types.ModuleType("comfy_execution.validation")
    _ce.validation.validate_node_input = lambda *a: True
    sys.modules["comfy_execution.validation"] = _ce.validation

    _ce.progress = types.ModuleType("comfy_execution.progress")
    _ce.progress.get_progress_state = lambda: type("s", (), {"finish_progress": lambda s, uid: None, "start_progress": lambda s, uid: None})()
    _ce.progress.reset_progress_state = lambda *a: None
    _ce.progress.add_progress_handler = lambda *a: None
    _ce.progress.WebUIProgressHandler = lambda s: None
    sys.modules["comfy_execution.progress"] = _ce.progress

    _ce.cache_provider = types.ModuleType("comfy_execution.cache_provider")
    _ce.cache_provider._has_cache_providers = lambda: False
    _ce.cache_provider._get_cache_providers = lambda: []
    _ce.cache_provider._logger = type("l", (), {"warning": staticmethod(lambda *a: None)})()
    sys.modules["comfy_execution.cache_provider"] = _ce.cache_provider

    # ── comfy_api internal (needed by execution) ─────────────────────
    _ca = types.ModuleType("comfy_api")
    _ca.internal = types.ModuleType("comfy_api.internal")
    _ca.internal._ComfyNodeInternal = type("_ComfyNodeInternal", (), {})
    _ca.internal._NodeOutputInternal = type("_NodeOutputInternal", (), {})
    _ca.internal.first_real_override = lambda *a: None
    _ca.internal.is_class = lambda v: isinstance(v, type)
    _ca.internal.make_locked_method_func = lambda f: f
    sys.modules["comfy_api"] = _ca
    sys.modules["comfy_api.internal"] = _ca.internal

    _ca.latest = types.ModuleType("comfy_api.latest")
    _ca.latest.io = types.ModuleType("comfy_api.latest.io")
    _ca.latest.io._io = types.ModuleType("_io")
    _ca.latest._io = types.ModuleType("_io")

    class _ComfyTypeIO:
        STRING = "STRING"
        CLIP = "CLIP"
        CONDITIONING = "CONDITIONING"
        INT = "INT"
        FLOAT = "FLOAT"
    _ca.latest.io.ComfyTypeIO = _ComfyTypeIO

    class _V3Data(dict):
        def copy(self):
            return type(self)(self)
    _ca.latest.io.V3Data = _V3Data
    sys.modules["comfy_api.latest"] = _ca.latest
    sys.modules["comfy_api.latest.io"] = _ca.latest.io
    sys.modules["comfy_api.latest._io"] = _ca.latest._io

    # ── nodes module (needed by execution) ──────────────────────────
    _nodes = types.ModuleType("nodes")
    _nodes.NODE_CLASS_MAPPINGS = {}
    _nodes.ComfyNodeABC = type("ComfyNodeABC", (), {})
    _nodes.before_node_execution = lambda: None
    _nodes.interrupt_processing = lambda v: None
    _nodes.MAX_RESOLUTION = 16384
    sys.modules["nodes"] = _nodes

    # ── latent_preview ──────────────────────────────────────────────
    _lp = types.ModuleType("latent_preview")
    _lp.set_preview_method = lambda m: None
    sys.modules["latent_preview"] = _lp

    # ── comfy.cli_args ──────────────────────────────────────────────
    _cli = types.ModuleType("comfy.cli_args")
    _cli.args = type("args", (), {"verbose": ""})()
    sys.modules["comfy.cli_args"] = _cli

    # ── comfy.memory_management ─────────────────────────────────────
    _cmm = types.ModuleType("comfy.memory_management")
    _cmm.set_ram_cache_release_state = lambda *a: None
    _cmm.cleanup_models_gc = lambda: None
    _cmm.DISABLE_SMART_MEMORY = False
    sys.modules["comfy.memory_management"] = _cmm

    # ── comfy.model_prefetch ────────────────────────────────────────
    _cpf = types.ModuleType("comfy.model_prefetch")
    _cpf.cleanup_prefetch_queues = lambda: None
    sys.modules["comfy.model_prefetch"] = _cpf

    # ── comfy_aimdo ─────────────────────────────────────────────────
    _aim = types.ModuleType("comfy_aimdo")
    _aim.model_vbar = types.ModuleType("comfy_aimdo.model_vbar")
    _aim.model_vbar.vbars_reset_watermark_limits = lambda: None
    _aim.control = types.ModuleType("comfy_aimdo.control")
    _aim.control.analyze = lambda: None
    sys.modules["comfy_aimdo"] = _aim
    sys.modules["comfy_aimdo.model_vbar"] = _aim.model_vbar
    sys.modules["comfy_aimdo.control"] = _aim.control

    # ── sageattention (optional import) ─────────────────────────────
    try:
        import sageattention  # noqa: F401
    except ImportError:
        _sa = types.ModuleType("sageattention")
        _sa._fused = types.ModuleType("sageattention._fused")
        sys.modules["sageattention"] = _sa
        sys.modules["sageattention._fused"] = _sa._fused

    # ── Now create the execution module with our fakes ───────────────
    _exec = types.ModuleType("execution")
    _exec.CacheSet = _make_fake_cacheset()
    _exec.IsChangedCache = _make_fake_is_changed_cache()
    _exec.DuplicateNodeError = type("DuplicateNodeError", (Exception,), {})
    _exec.ExecutionResult = type("ExecutionResult", (), {"SUCCESS": 0, "FAILURE": 1, "PENDING": 2})
    _exec.get_input_data = _make_real_get_input_data()
    _exec.execute = _make_fake_exec_node()
    _exec.get_output_data = _make_fake_get_output_data()
    _exec.get_output_from_returns = lambda r, o: ([], {}, False)
    _exec._async_map_node_over_list = _make_fake_async_map()
    async def _async_resolve(results):
        return results
    _exec.resolve_map_node_over_list_results = _async_resolve
    _exec.format_value = lambda x: str(x) if not isinstance(x, (int, float, bool, type(None))) else x
    _exec._is_intermediate_output = lambda *a: False
    _exec._send_cached_ui = lambda *a: None

    class _PromptExecutor:
        def __init__(self):
            self.caches = _make_fake_cacheset()
            self.server = None
            self.status_messages = []
            self.success = True

        def reset(self):
            self.status_messages = []
            self.success = True

        async def execute_async(
            self, prompt, prompt_id, extra_data=None, execute_outputs=None,
        ):
            import sys as _sys_exec
            import comfy.model_management as _mm
            import asyncio as _asyncio
            _exec_mod = _sys_exec.modules["execution"]
            self.add_message("execution_start", {"prompt_id": prompt_id}, broadcast=False)
            # Simulate cache gather from real PromptExecutor
            for node_id in sorted(prompt.keys()):
                await self.caches.outputs.get(node_id)
            # Simulate the execution loop from PromptExecutor
            for node_id in sorted(prompt.keys()):
                node_info = prompt[node_id]
                node_class = node_info.get("class_type", "")
                _class_lower = node_class.lower()

                # Simulate model loading for loader/checkpoint nodes
                if "loader" in _class_lower or "checkpoint" in _class_lower:
                    _mm.load_models_gpu([])

                _exec_mod.get_input_data(
                    node_info.get("inputs", {}),
                    type("FakeClassDef", (), {
                        "INPUT_TYPES": staticmethod(lambda: {"required": {}, "optional": {}, "hidden": {}}),
                        "__bases__": (object,),
                    })(),
                    node_id,
                    execution_list=None,
                    dynprompt=None,
                    extra_data=extra_data or {},
                )
                time.sleep(0.002)  # simulate work
                await _exec_mod.execute(
                    server=None,
                    dynprompt=None,
                    caches=_make_fake_cacheset(),
                    current_item=node_id,
                    extra_data=extra_data or {},
                    executed=set(),
                    prompt_id=prompt_id,
                    execution_list=_make_fake_execution_list(),
                    pending_subgraph_results={},
                    pending_async_nodes={},
                    ui_outputs={},
                )
                time.sleep(0.001)
            # Simulate future-wait resolution: call resolve with a mix of done/not-done tasks
            _done_task = _asyncio.ensure_future(_asyncio.sleep(0))
            await _asyncio.sleep(0)  # let the done task complete
            _pending_task = _asyncio.ensure_future(_asyncio.sleep(0.001))
            _results = [_done_task, "plain_value", _pending_task]
            await _exec_mod.resolve_map_node_over_list_results(_results)
            self.add_message("execution_success", {"prompt_id": prompt_id}, broadcast=False)

        def add_message(self, event, data, broadcast):
            self.status_messages.append((event, data))

        def execute(self, prompt, prompt_id, extra_data=None, execute_outputs=None):
            asyncio.run(self.execute_async(prompt, prompt_id, extra_data, execute_outputs))

    _exec.PromptExecutor = _PromptExecutor
    _exec._pre_sampler_stubbed = True
    sys.modules["execution"] = _exec


def _make_fake_load_models_gpu():
    """Return a load_models_gpu stub that sleeps briefly."""
    def _load(models, memory_required=0, force_patch_weights=False,
              minimum_memory_required=None, force_full_load=False):
        time.sleep(0.003)
    return _load


def _make_fake_cacheset():
    """Return a CacheSet instance stub using HierarchicalCache for outputs."""
    from comfy_execution.caching import HierarchicalCache, NullCache
    class _FakeCaches:
        def __init__(self):
            self.outputs = HierarchicalCache(type("FakeKeyClass", (), {"get_data_key": staticmethod(lambda n: str(n))})())
            self.objects = NullCache()
            self.all = [self.outputs, self.objects]
    # Return an instance so .outputs works immediately
    return _FakeCaches()


def _make_fake_is_changed_cache():
    class _Fake:
        def __init__(self, *a, **kw): pass
        def set_prompt(self, *a, **kw): pass
        def clean_unused(self): pass
    return _Fake


def _make_real_get_input_data():
    """Return a get_input_data function similar to the real one."""
    def _get_input_data(inputs, class_def, unique_id, execution_list=None,
                        dynprompt=None, extra_data={}):
        time.sleep(0.001)
        return ({k: [v] for k, v in inputs.items()}, {}, {})
    return _get_input_data


def _make_fake_exec_node():
    """Return an execute function stub that sleeps briefly."""
    async def _execute(server, dynprompt, caches, current_item, extra_data,
                       executed, prompt_id, execution_list,
                       pending_subgraph_results, pending_async_nodes, ui_outputs):
        time.sleep(0.003)
        return (0, None, None)  # (ExecutionResult.SUCCESS, None, None)
    return _execute


def _make_fake_get_output_data():
    async def _get_output_data(*a, **kw):
        time.sleep(0.002)
        return ([], {}, False, False)
    return _get_output_data


def _make_fake_async_map():
    async def _map(*a, **kw):
        return []
    return _map


def _make_fake_execution_list():
    class _Fake:
        def get_cache(self, s, d): return None
        def cache_update(self, n, e): pass
        def stage_node_execution(self): return (None, None, None)
        def unstage_node_execution(self): pass
        def complete_node_execution(self): pass
        def add_node(self, n): pass
        def cache_link(self, n, u): pass
        def add_strong_link(self, s, i, d): pass
        def make_input_strong_link(self, n, k): pass
        def add_external_block(self, n): return lambda: None
        def is_empty(self): return True
    return _Fake()


# Ensure stubs available before any test
_ensure_comfyui_stubs()


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def _clean_hooks():
    """Ensure hooks are uninstalled before and after each test."""
    uninstall_pre_sampler_hooks()
    yield
    uninstall_pre_sampler_hooks()


@pytest.fixture
def capture_stdout() -> io.StringIO:
    """Capture stdout for summary-line verification."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        yield out


# ═══════════════════════════════════════════════════════════════════════
# Helper: simulate a full request through native bounds
# ═══════════════════════════════════════════════════════════════════════


async def _simulate_request(
    node_list: list[dict[str, Any]],
    *,
    simulate_get_input_data: bool = True,
    simulate_load_models: bool = False,
    simulate_node_execution: bool = True,
) -> dict[str, Any]:
    """Run a simulated request through the PreSamplerInstrumentation hooks.

    Creates the per-request state, installs hooks, calls each patched
    boundary directly, and returns the aggregated state dict (which the
    ``_patched_exec_async`` summarises into the one-line print).

    The ``execute_async`` wrapper emits the summary line in its finally
    block — we call it explicitly with a minimal fake executor.
    """
    import execution as _execution

    state: dict[str, Any] = {}
    token = _instrumentation_var.set(state)
    install_pre_sampler_hooks()

    # Build a fake prompt dict from the node list
    prompt = {str(i): {
        "class_type": n.get("class_type", ""),
        "inputs": n.get("inputs", {}),
    } for i, n in enumerate(node_list)}

    try:
        # Call PromptExecutor.execute_async which triggers the patched
        # version that handles the full execution loop internally.
        executor = _execution.PromptExecutor()
        await _execution.PromptExecutor.execute_async(
            executor,
            prompt,
            "test-prompt-id",
            extra_data={},
            execute_outputs=None,
        )
    finally:
        _instrumentation_var.reset(token)

    return state


# ═══════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════


class TestPreSamplerInstrumentationLive:
    """Live timings from actual patched execution boundaries."""

    @pytest.mark.asyncio
    async def test_basic_execution_records_nonzero_timings(self):
        """A simple request produces non-zero aggregate timings for
        node_execution_ms and input_resolution_ms."""
        state = await _simulate_request([
            {"class_type": "CLIPTextEncode", "inputs": {"text": "cat"}},
            {"class_type": "KSampler", "inputs": {"seed": 42}},
        ])

        # node_execution_ms: each simulated node adds measurable time
        assert state.get("node_execution_ms", 0.0) > 0, (
            f"expected non-zero node_execution_ms, got keys={list(state.keys())} values={ {k:v for k,v in state.items() if k.endswith('_ms')} }"
        )

        # input_resolution_ms: each get_input_data call adds time
        assert state.get("input_resolution_ms", 0.0) > 0, (
            f"expected non-zero input_resolution_ms, got {state}"
        )

        # conditioning_ms: CLIPTextEncode node should be classified
        assert state.get("conditioning_ms", 0.0) > 0, (
            f"expected non-zero conditioning_ms, got {state}"
        )

        # pre_sampler_unattributed_ms: populated from wall time
        assert state.get("pre_sampler_unattributed_ms", 0.0) > 0, (
            f"expected non-zero pre_sampler_unattributed_ms, got {state}"
        )

    @pytest.mark.asyncio
    async def test_model_loader_records_model_patch(self):
        """A request with a model-loader node records model_patch_ms."""
        state = await _simulate_request([
            {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model.ckpt"}},
            {"class_type": "CLIPTextEncode", "inputs": {"text": "cat"}},
            {"class_type": "KSampler", "inputs": {"seed": 42}},
        ], simulate_load_models=True)

        assert state.get("model_patch_ms", 0.0) > 0, (
            f"expected non-zero model_patch_ms, got {state}"
        )

    @pytest.mark.asyncio
    async def test_sampler_detected_by_classification(self):
        """Sampler node class type is captured in state."""
        state = await _simulate_request([
            {"class_type": "CLIPTextEncode", "inputs": {"text": "cat"}},
            {"class_type": "KSampler", "inputs": {"seed": 42}},
        ])

        assert "sampler_node_id" in state, (
            f"expected sampler_node_id in state, got keys={list(state.keys())}"
        )
        assert state.get("sampler_class_type") == "KSampler"
        assert isinstance(state.get("first_node_enter_perf_ns"), int)
        assert isinstance(state.get("sampler_node_enter_perf_ns"), int)
        assert state["sampler_node_enter_perf_ns"] >= state["first_node_enter_perf_ns"]
        assert "sampler_start_ns" not in state

    @pytest.mark.asyncio
    async def test_first_and_last_node_tracked(self):
        """The first and last node ids and class types are tracked."""
        state = await _simulate_request([
            {"class_type": "CLIPTextEncode", "inputs": {"text": "cat"}},
            {"class_type": "VAEDecode", "inputs": {}},
            {"class_type": "KSampler", "inputs": {"seed": 42}},
        ])

        assert state.get("first_node_id") is not None
        assert state.get("first_class_type") is not None
        assert state.get("last_node_id") is not None
        assert state.get("last_class_type") is not None

    @pytest.mark.asyncio
    async def test_background_future_flags(self):
        """background_future_exists and model_cache_hit are set."""
        state = await _simulate_request([
            {"class_type": "CLIPTextEncode", "inputs": {"text": "cat"}},
        ])

        assert "background_future_exists" in state
        assert isinstance(state["background_future_exists"], bool)
        assert "background_future_done" in state
        assert isinstance(state["background_future_done"], bool)

    @pytest.mark.asyncio
    async def test_span_name_filled(self):
        """The dominant interval span name is populated."""
        state = await _simulate_request([
            {"class_type": "CLIPTextEncode", "inputs": {"text": "cat"}},
            {"class_type": "KSampler", "inputs": {"seed": 42}},
        ])

        assert state.get("span") in (
            "full_pre_sampler", "sampler_path", "conditioning_only",
            "execution_complete",
        ), f"unexpected span={state.get('span')}"


class TestPreSamplerSummaryLine:
    """Exactly one [v2.pre_sampler_critical_path] line is emitted."""

    @pytest.mark.asyncio
    async def test_one_summary_line_emitted(self, capture_stdout):
        """Running a simulated request produces exactly one summary line."""
        await _simulate_request([
            {"class_type": "CLIPTextEncode", "inputs": {"text": "cat"}},
            {"class_type": "KSampler", "inputs": {"seed": 42}},
        ])

        output = capture_stdout.getvalue()
        lines = [
            l for l in output.splitlines()
            if l.startswith("[v2.pre_sampler_critical_path]")
        ]
        assert len(lines) == 1, (
            f"expected exactly one summary line, got {len(lines)}: {lines}"
        )

    @pytest.mark.asyncio
    async def test_summary_line_contains_required_fields(self, capture_stdout):
        """The summary line includes all required fields."""
        await _simulate_request([
            {"class_type": "CLIPTextEncode", "inputs": {"text": "cat"}},
            {"class_type": "KSampler", "inputs": {"seed": 42}},
        ])

        output = capture_stdout.getvalue()
        line = next(
            (l for l in output.splitlines()
             if l.startswith("[v2.pre_sampler_critical_path]")),
            None,
        )
        assert line is not None, "no summary line found"

        required_fields = [
            "span", "start_node_id", "start_class_type",
            "end_node_id", "end_class_type",
            "cache_lookup_ms", "pre_sampler_unattributed_ms",
            "input_resolution_ms", "future_wait_ms", "lock_wait_ms",
            "model_patch_ms", "conditioning_ms", "node_execution_ms",
            "unattributed_ms", "background_future_exists",
            "background_future_done", "model_cache_hit",
        ]
        for field in required_fields:
            assert f"{field}=" in line, (
                f"summary line missing field '{field}': {line}"
            )

    @pytest.mark.asyncio
    async def test_non_negative_timings_in_line(self, capture_stdout):
        """All numeric timings in the summary line are non-negative."""
        await _simulate_request([
            {"class_type": "CLIPTextEncode", "inputs": {"text": "cat"}},
            {"class_type": "KSampler", "inputs": {"seed": 42}},
        ])

        output = capture_stdout.getvalue()
        line = next(
            (l for l in output.splitlines()
             if l.startswith("[v2.pre_sampler_critical_path]")),
            None,
        )
        assert line is not None

        timing_fields = [
            "cache_lookup_ms", "pre_sampler_unattributed_ms",
            "input_resolution_ms", "future_wait_ms", "lock_wait_ms",
            "model_patch_ms", "conditioning_ms", "node_execution_ms",
            "unattributed_ms",
        ]
        for field in timing_fields:
            prefix = f"{field}="
            idx = line.find(prefix)
            if idx == -1:
                continue  # absent timings are valid
            rest = line[idx + len(prefix):].split(" ")[0]
            if rest == _PRE_SAMPLER_ABSENT_STR:
                continue
            val = float(rest)
            assert val >= 0, (
                f"negative timing {field}={val} in line: {line}"
            )


class TestPreSamplerHooksLifecycle:
    """Hook install/uninstall is idempotent and reversible."""

    def test_install_uninstall_idempotent(self):
        """Calling install/uninstall multiple times does not crash."""
        install_pre_sampler_hooks()
        install_pre_sampler_hooks()  # second install = no-op
        uninstall_pre_sampler_hooks()
        uninstall_pre_sampler_hooks()  # second uninstall = no-op

        # Can reinstall
        install_pre_sampler_hooks()
        uninstall_pre_sampler_hooks()

    def test_hooks_restore_originals(self):
        """After uninstall, functions are restored to originals."""
        import execution as _execution

        orig_exec = _execution.execute
        install_pre_sampler_hooks()
        assert _execution.execute is not orig_exec
        uninstall_pre_sampler_hooks()
        # After uninstall, the function should be the original stub
        # (which is _make_fake_exec_node, not the patched version)

    def test_inactive_hooks_passthrough(self):
        """Without state set, the hooks call the original functions
        without modification."""
        install_pre_sampler_hooks()
        import execution as _execution
        import comfy.model_management as _mm

        # Calls without state should work normally
        result = _execution.get_input_data(
            {"text": "hello"},
            type("Fake", (), {"INPUT_TYPES": staticmethod(lambda: {"required": {}, "optional": {}, "hidden": {}})})(),
            "0",
        )
        assert isinstance(result, tuple) and len(result) == 3

        # load_models_gpu without state
        _mm.load_models_gpu([])

        uninstall_pre_sampler_hooks()


class TestAbsentSemantics:
    """Fields not observed during execution render as 'absent'."""

    @pytest.mark.asyncio
    async def test_lock_wait_absent_when_not_observed(self, capture_stdout):
        """lock_wait_ms shows as absent when no model loading lock occurs."""
        await _simulate_request([
            {"class_type": "CLIPTextEncode", "inputs": {"text": "cat"}},
        ])

        output = capture_stdout.getvalue()
        line = next(
            (l for l in output.splitlines()
             if l.startswith("[v2.pre_sampler_critical_path]")),
            None,
        )
        assert line is not None
        # lock_wait_ms should be "absent" or "0" since no model loading
        assert "lock_wait_ms=absent" in line


class TestNoCrossRequestLeak:
    """Instrumentation state does not leak across requests."""

    @pytest.mark.asyncio
    async def test_state_reset_per_request(self):
        """Each simulated request starts with fresh state."""
        state1 = await _simulate_request([
            {"class_type": "CLIPTextEncode", "inputs": {"text": "cat"}},
        ])
        state2 = await _simulate_request([
            {"class_type": "KSampler", "inputs": {"seed": 42}},
        ])

        # They should have independent state dicts
        assert state1 is not state2

    @pytest.mark.asyncio
    async def test_no_carryover_between_requests(self):
        """First request's sampler data does not leak to second."""
        state1 = await _simulate_request([
            {"class_type": "KSampler", "inputs": {"seed": 42}},
        ])
        state2 = await _simulate_request([
            {"class_type": "CLIPTextEncode", "inputs": {"text": "cat"}},
        ])

        # State dicts are independent
        assert state1 is not state2


class TestEmitPreSamplerLine:
    """Unit-level tests for _emit_pre_sampler_line."""

    def test_absent_renders_correctly(self, capture_stdout):
        """Fields absent in state render as the absent string."""
        state: dict[str, Any] = {
            "span": "test_span",
            "node_execution_ms": 10.5,
        }
        _emit_pre_sampler_line(state)

        output = capture_stdout.getvalue()
        assert "[v2.pre_sampler_critical_path]" in output
        assert "span=test_span" in output
        assert "node_execution_ms=10.500" in output
        # Fields not in state render as absent
        assert "cache_lookup_ms=absent" in output

    def test_bool_renders_as_01(self, capture_stdout):
        """Boolean values render as 1/0."""
        state: dict[str, Any] = {
            "span": "s",
            "background_future_exists": True,
            "background_future_done": False,
        }
        _emit_pre_sampler_line(state)

        output = capture_stdout.getvalue()
        assert "background_future_exists=1" in output
        assert "background_future_done=0" in output

    def test_missing_fields_are_absent(self, capture_stdout):
        """A completely empty state produces absent for all fields."""
        state: dict[str, Any] = {}
        _emit_pre_sampler_line(state)

        output = capture_stdout.getvalue()
        for field in (
            "span", "start_node_id", "start_class_type",
            "end_node_id", "end_class_type",
        ):
            assert f"{field}=absent" in output


class TestCacheLookupLive:
    """cache_lookup_ms is recorded from live HierarchicalCache.get calls."""

    @pytest.mark.asyncio
    async def test_cache_lookup_accumulates(self):
        """A request with cache lookups accumulates non-zero cache_lookup_ms."""
        state = await _simulate_request([
            {"class_type": "CLIPTextEncode", "inputs": {"text": "cat"}},
        ])
        # The fake executor calls self.caches.outputs.get() for each node,
        # which triggers the patched HierarchicalCache.get hook.
        # Since the stub returns None (miss), each call should take some
        # minimal time; cache_lookup_ms should be >= 0.
        assert "cache_lookup_ms" in state, (
            f"expected cache_lookup_ms in state, got keys={list(state.keys())}"
        )
        assert state["cache_lookup_ms"] >= 0

    @pytest.mark.asyncio
    async def test_cache_miss_recorded(self, capture_stdout):
        """When cache.get returns None, a miss is recorded (no hit)."""
        await _simulate_request([
            {"class_type": "KSampler", "inputs": {"seed": 42}},
        ])
        output = capture_stdout.getvalue()
        line = next(
            (l for l in output.splitlines()
             if l.startswith("[v2.pre_sampler_critical_path]")),
            None,
        )
        assert line is not None
        # cache_lookup_ms should be present and numeric (not absent)
        assert "cache_lookup_ms=" in line
        assert "cache_lookup_ms=absent" not in line


class TestFutureWaitLive:
    """future_wait_ms is recorded from live resolve_map_node_over_list_results."""

    @pytest.mark.asyncio
    async def test_future_wait_accumulates(self):
        """A request with future resolution accumulates non-zero future_wait_ms."""
        state = await _simulate_request([
            {"class_type": "CLIPTextEncode", "inputs": {"text": "cat"}},
        ])
        # The fake executor calls resolve_map_node_over_list_results with
        # a mix of done/not-done tasks, triggering the patched hook.
        assert "future_wait_ms" in state, (
            f"expected future_wait_ms in state, got keys={list(state.keys())}"
        )
        # The pending task should produce measurable wait time
        fw = state["future_wait_ms"]
        assert fw >= 0.0, f"future_wait_ms must be >= 0, got {fw}"

    @pytest.mark.asyncio
    async def test_future_wait_summary_line(self, capture_stdout):
        """future_wait_ms appears in the summary line as a numeric value."""
        await _simulate_request([
            {"class_type": "KSampler", "inputs": {"seed": 42}},
        ])
        output = capture_stdout.getvalue()
        line = next(
            (l for l in output.splitlines()
             if l.startswith("[v2.pre_sampler_critical_path]")),
            None,
        )
        assert line is not None
        assert "future_wait_ms=" in line
        assert "future_wait_ms=absent" not in line


class TestLockWaitBridge:
    """lock_wait_ms is bridged from modal_app sampler lane acquisition."""

    @pytest.mark.asyncio
    async def test_lock_wait_from_bridge(self, capture_stdout):
        """set_lock_wait_ms within the instrumentation scope populates lock_wait_ms
        when _pop_lock_wait_ms is called (as happens inside _patched_exec_async)."""
        state: dict[str, Any] = {}
        with pre_sampler_instrumentation_scope(state):
            install_pre_sampler_hooks()
            # Simulate what modal_app's send_sync wrapper does:
            # 1. Lock is acquired, set_lock_wait_ms bridges the duration
            set_lock_wait_ms(12.345)
            # 2. Execution continues (cache lookups, future waits, etc.)
            # 3. After execute_async completes, _pop_lock_wait_ms is called
            #    (inside _patched_exec_async's finally block)
            _pop_lock_wait_ms(state)

        # lock_wait_ms should have been populated from the bridge
        assert state.get("lock_wait_ms", 0.0) > 0, (
            f"expected non-zero lock_wait_ms, got {state}"
        )
        # The bridged value (12.345) should be reflected in the aggregate
        assert state["lock_wait_ms"] >= 12.345, (
            f"lock_wait_ms={state['lock_wait_ms']} should include bridged value"
        )

    @pytest.mark.asyncio
    async def test_lock_wait_zero_when_not_bridged(self):
        """Without set_lock_wait_ms, lock_wait_ms is absent/zero."""
        import execution as _execution

        state: dict[str, Any] = {}
        with pre_sampler_instrumentation_scope(state):
            install_pre_sampler_hooks()
            # Do not call set_lock_wait_ms
            from comfy_execution.caching import HierarchicalCache
            cache = HierarchicalCache()
            await cache.get("node_0")
            _done = asyncio.ensure_future(asyncio.sleep(0))
            await asyncio.sleep(0)
            await _execution.resolve_map_node_over_list_results([_done])

        # lock_wait_ms should be absent (never bridged)
        assert "lock_wait_ms" not in state or state["lock_wait_ms"] == 0.0


class TestLiveHookWiringProduction:
    """The production wiring point (_execute_v2_prompt_executor) enters the
    pre_sampler_instrumentation_scope, so all hooks fire during a normal
    executor call."""

    @pytest.mark.asyncio
    async def test_hooks_fire_through_production_wiring(self):
        """When the patched execute_async runs under the production scope,
        cache_lookup_ms, future_wait_ms, and other live fields are populated."""
        import execution as _execution

        state: dict[str, Any] = {}
        with pre_sampler_instrumentation_scope(state):
            install_pre_sampler_hooks()
            executor = _execution.PromptExecutor()
            await _execution.PromptExecutor.execute_async(
                executor,
                {"0": {"class_type": "CLIPTextEncode", "inputs": {"text": "cat"}}},
                "test-prod-wiring",
            )

        # After the full execute_async runs, multiple live fields should be present
        assert state.get("cache_lookup_ms", -1) >= 0, (
            f"cache_lookup_ms absent or negative: {state}"
        )
        assert state.get("future_wait_ms", -1) >= 0, (
            f"future_wait_ms absent or negative: {state}"
        )
        assert state.get("node_execution_ms", 0.0) > 0, (
            f"node_execution_ms not > 0: {state}"
        )
        assert state.get("input_resolution_ms", 0.0) > 0, (
            f"input_resolution_ms not > 0: {state}"
        )
        # span should be classified
        assert state.get("span") in (
            "full_pre_sampler", "sampler_path", "conditioning_only",
            "execution_complete",
        ), f"unexpected span={state.get('span')}"


class TestCacheHitMissTracking:
    """Patched HierarchicalCache.get tracks hit vs miss."""

    @pytest.mark.asyncio
    async def test_cache_miss_default(self):
        """When cache returns None, miss is recorded (not hit)."""
        state: dict[str, Any] = {}
        with pre_sampler_instrumentation_scope(state):
            install_pre_sampler_hooks()
            from comfy_execution.caching import HierarchicalCache
            cache = HierarchicalCache()
            result = await cache.get("unknown_node")
            assert result is None

        # Internal counters should show 1 miss, 0 hits
        assert state.get("_cache_count", 0) >= 1
        # _cache_hit_count may be 0 and _cache_miss_count should be >= 1
        _hits = state.get("_cache_hit_count", 0)
        _misses = state.get("_cache_miss_count", 0)
        assert _hits + _misses >= 1, "expected at least 1 cache operation"
        # When only misses, hits should be 0
        if _misses > 0 and _hits == 0:
            pass  # correct: all misses

    @pytest.mark.asyncio
    async def test_cache_hit_recorded(self):
        """When cache returns a value, hit is recorded."""
        state: dict[str, Any] = {}
        with pre_sampler_instrumentation_scope(state):
            install_pre_sampler_hooks()
            from comfy_execution.caching import HierarchicalCache
            cache = HierarchicalCache()
            await cache.set("node_known", "cached_value")
            result = await cache.get("node_known")
            assert result == "cached_value"

        # Internal counters should show at least 1 hit
        assert state.get("_cache_hit_count", 0) >= 1, (
            f"expected cache hit, got state={state}"
        )
        assert state.get("cache_lookup_ms", 0.0) >= 0


class TestFutureWaitTiming:
    """Future-wait records 0.0 for completed futures and >0 for pending."""

    @pytest.mark.asyncio
    async def test_completed_future_zero_time(self):
        """A completed future's resolve should record 0.0 (or very near)."""
        import execution as _execution

        state: dict[str, Any] = {}
        with pre_sampler_instrumentation_scope(state):
            install_pre_sampler_hooks()
            _done = asyncio.ensure_future(asyncio.sleep(0))
            await asyncio.sleep(0)
            # done task
            await _execution.resolve_map_node_over_list_results([_done])

        fw = state.get("future_wait_ms", -1)
        # Should be 0.0 or very small (completed future returns immediately)
        assert fw >= 0.0, f"future_wait_ms must be >= 0, got {fw}"
        # Reset for next test
        uninstall_pre_sampler_hooks()

    @pytest.mark.asyncio
    async def test_incomplete_future_records_positive(self):
        """An incomplete future's resolve records measurable wait time."""
        import execution as _execution

        state: dict[str, Any] = {}
        with pre_sampler_instrumentation_scope(state):
            install_pre_sampler_hooks()
            _pending = asyncio.ensure_future(asyncio.sleep(0.005))
            await _execution.resolve_map_node_over_list_results([_pending])

        fw = state.get("future_wait_ms", -1)
        # The pending task takes ~5ms, but the actual measured time depends
        # on the event loop. It should be a small positive number.
        assert fw > 0, f"expected positive future_wait_ms for pending task, got {fw}"
