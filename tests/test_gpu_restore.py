"""FAST_UNIT: post-snapshot GPU capability repair coordinator (Part A4).

Repair-behavior tests moved here from ``tests/test_v2_ideogram_cuda_profile.py``
(which keeps profiling coverage only).  Dependency-free fakes throughout:
a mutable CUDA switch, a fake kitchen registry with keyed registration /
unavailable / disables / priority / stale compute-capability, and a fake
``comfy.model_management`` carrying the attention device limit.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.fast_unit

from comfymodal_runtime import gpu_restore as gr

STALE_LIMIT = 2**31
FIXED_LIMIT = 2**15


@pytest.fixture(autouse=True)
def _hermetic_gpu_restore():
    gr.begin_gpu_restore()
    yield
    gr.begin_gpu_restore()


class _CudaFake:
    """Mutable CUDA switch: visibility and device name flip per test."""

    def __init__(self, *, visible=True, name="NVIDIA H100"):
        self._visible = visible
        self._name = name

    def is_available(self):
        return self._visible

    def set_visible(self, visible):
        self._visible = bool(visible)

    def current_device(self):
        return 0

    def get_device_name(self, _index=0):
        return self._name

    def get_device_capability(self, _index=0):
        return (9, 0)


class _Registry:
    """Fake kitchen registry: keyed registration, unavailable, policy."""

    def __init__(
        self,
        *,
        disabled=(),
        priority=("cuda", "triton", "eager"),
        stale_cc=True,
        registerable=("cuda", "triton"),
    ):
        self._disabled = set(disabled)
        self._priority = list(priority)
        self._unavailable = {
            "cuda": "CUDA not available on this system",
            "triton": "Neither CUDA nor XPU available on this system",
        }
        self.capabilities = {"cuda": [], "triton": [], "eager": ["int8_linear"]}
        self.register_calls: list[str] = []
        self._registerable = set(registerable)
        if stale_cc:
            self.__dict__["_compute_capability"] = (8, 0)

    def register(self, name, capabilities):
        self.register_calls.append(name)
        self.capabilities[name] = list(capabilities)
        if name in self._registerable:
            self._unavailable.pop(name, None)

    def list_backends(self):
        out = {}
        for name in ("cuda", "triton", "eager"):
            out[name] = {
                "available": name not in self._unavailable and name not in self._disabled,
                "disabled": name in self._disabled,
                "unavailable_reason": self._unavailable.get(name),
                "capabilities": list(self.capabilities.get(name, [])),
            }
        return out

    def get_capable_backend(self, func, kwargs=None):
        for name in self._priority:
            if name not in self._disabled and name not in self._unavailable:
                if func in self.capabilities.get(name, []):
                    return name
        return None


def _install_torch(monkeypatch, cuda):
    torch_mod = types.ModuleType("torch")
    torch_mod.cuda = cuda
    monkeypatch.setitem(sys.modules, "torch", torch_mod)
    return torch_mod


def _install_kitchen(monkeypatch, registry, *, cuda, triton_failure=False):
    ck = types.ModuleType("comfy_kitchen")
    ck.registry = registry
    backends = types.ModuleType("comfy_kitchen.backends")
    cuda_mod = types.ModuleType("comfy_kitchen.backends.cuda")
    triton_mod = types.ModuleType("comfy_kitchen.backends.triton")
    calls = {"cuda": 0, "triton": 0}
    fail = {"triton": triton_failure}

    def _cuda_register():
        calls["cuda"] += 1
        if not cuda.is_available():
            registry._unavailable["cuda"] = "CUDA not available on this system"
            return
        registry.register("cuda", ["int8_linear"])

    def _triton_register():
        calls["triton"] += 1
        if fail["triton"]:
            raise RuntimeError("fake triton registration failure")
        registry.register("triton", ["int8_linear"])

    cuda_mod._register = _cuda_register
    triton_mod._register = _triton_register
    monkeypatch.setitem(sys.modules, "comfy_kitchen", ck)
    monkeypatch.setitem(sys.modules, "comfy_kitchen.backends", backends)
    monkeypatch.setitem(sys.modules, "comfy_kitchen.backends.cuda", cuda_mod)
    monkeypatch.setitem(sys.modules, "comfy_kitchen.backends.triton", triton_mod)
    return calls, fail


def _install_mm(monkeypatch, *, cpu_state="GPU", limit=STALE_LIMIT):
    mm = types.ModuleType("comfy.model_management")
    mm.CPUState = SimpleNamespace(CPU="CPU", GPU="GPU")
    mm.cpu_state = cpu_state
    mm.SDP_BATCH_LIMIT = limit
    mm.attention_backend = "flash"
    mm.vram_state = "HIGH"
    monkeypatch.setitem(sys.modules, "comfy.model_management", mm)
    return mm


def _install_full(
    monkeypatch,
    *,
    visible=True,
    device_name="NVIDIA H100",
    disabled=(),
    triton_failure=False,
    cpu_state="GPU",
    limit=STALE_LIMIT,
    stale_cc=True,
    with_mm=True,
):
    cuda = _CudaFake(visible=visible, name=device_name)
    _install_torch(monkeypatch, cuda)
    registry = _Registry(disabled=disabled, stale_cc=stale_cc)
    calls, fail = _install_kitchen(
        monkeypatch, registry, cuda=cuda, triton_failure=triton_failure
    )
    mm = _install_mm(monkeypatch, cpu_state=cpu_state, limit=limit) if with_mm else None
    _install_cli_args(monkeypatch)
    am = _install_attn_mod(monkeypatch)
    _install_ck_probe(monkeypatch, value=True)
    return SimpleNamespace(
        cuda=cuda, registry=registry, calls=calls, fail=fail, mm=mm, am=am
    )


# ── Lifecycle ─────────────────────────────────────────────────────────────


def test_full_lifecycle_complete(monkeypatch):
    env = _install_full(monkeypatch)
    assert gr.begin_gpu_restore() == {
        "reset": True,
        "pending": [
            "attention_backend_selection",
            "attention_consumer_aliases",
            "comfy_attention_device_limits",
            "kitchen_gpu_backends",
            "model_management_derived_state",
        ],
    }
    report = gr.repair_gpu_capabilities_after_restore()
    assert report["outcome"] == "complete"
    assert report["pending"] == []
    assert sorted(report["completed"]) == [
        "attention_backend_selection",
        "attention_consumer_aliases",
        "comfy_attention_device_limits",
        "kitchen_gpu_backends",
        "model_management_derived_state",
    ]
    kitchen = report["providers"]["kitchen_gpu_backends"]
    assert kitchen["outcome"] == "complete"
    assert kitchen["cuda"] == "rerun"
    assert kitchen["triton"] == "rerun"
    attention = report["providers"]["comfy_attention_device_limits"]
    assert attention["outcome"] == "complete"
    assert (attention["limit_before"], attention["limit_after"]) == (
        STALE_LIMIT,
        FIXED_LIMIT,
    )
    assert env.mm.SDP_BATCH_LIMIT == FIXED_LIMIT
    ensured = gr.ensure_gpu_capabilities_repaired_before_execution()
    assert ensured["outcome"] == "complete"
    assert ensured["reason"] == "already_done"


def test_repair_idempotent_no_rerun(monkeypatch):
    env = _install_full(monkeypatch)
    gr.begin_gpu_restore()
    first = gr.repair_gpu_capabilities_after_restore()
    assert first["outcome"] == "complete"
    assert env.calls == {"cuda": 1, "triton": 1}
    second = gr.repair_gpu_capabilities_after_restore()
    assert second["outcome"] == "complete"
    assert second["reason"] == "already_done"
    assert second["providers"] == {}
    assert env.calls == {"cuda": 1, "triton": 1}
    assert env.registry.register_calls == ["cuda", "triton"]


def test_deferred_recovery_after_cuda_invisible(monkeypatch):
    env = _install_full(monkeypatch, visible=False)
    gr.begin_gpu_restore()
    first = gr.repair_gpu_capabilities_after_restore()
    assert first["outcome"] == "deferred"
    assert env.calls == {"cuda": 0, "triton": 0}
    # Real CUDA appears (CUDA-init callback / execution boundary): retry once.
    env.cuda.set_visible(True)
    second = gr.ensure_gpu_capabilities_repaired_before_execution()
    assert second["outcome"] == "complete"


def test_cpu_no_gpu_safety_no_mutation_no_guard(monkeypatch):
    env = _install_full(monkeypatch, visible=False)
    gr.begin_gpu_restore()
    report = gr.repair_gpu_capabilities_after_restore()
    assert report["outcome"] == "deferred"
    assert env.registry.register_calls == []
    assert env.registry.__dict__.get("_compute_capability") == (8, 0)
    assert env.mm.SDP_BATCH_LIMIT == STALE_LIMIT
    # CUDA-invisible must NOT consume the once-guard.
    assert gr._provider_done == {
        "kitchen_gpu_backends": False,
        "model_management_derived_state": False,
        "attention_backend_selection": False,
        "attention_consumer_aliases": False,
        "comfy_attention_device_limits": False,
    }


@pytest.mark.parametrize(
    "disabled", [("cuda",), ("triton",), ("cuda", "triton")]
)
def test_disabled_stays_disabled_never_enabled(monkeypatch, disabled):
    env = _install_full(monkeypatch, disabled=disabled)
    gr.begin_gpu_restore()
    report = gr.repair_gpu_capabilities_after_restore()
    # Intentionally-disabled backends count as terminal policy-preserved
    # completion (the fixed infinite-retry bug), not as pending work.
    assert report["outcome"] == "complete"
    kitchen = report["providers"]["kitchen_gpu_backends"]
    for name in disabled:
        assert kitchen[name] == "skipped:disabled"
        assert env.calls[name] == 0
    assert set(env.registry._disabled) == set(disabled)


def test_priority_preserved(monkeypatch):
    env = _install_full(monkeypatch, disabled=("triton",))
    before_priority = list(env.registry._priority)
    before_disabled = set(env.registry._disabled)
    gr.begin_gpu_restore()
    assert gr.repair_gpu_capabilities_after_restore()["outcome"] == "complete"
    assert env.registry._priority == before_priority
    assert set(env.registry._disabled) == before_disabled


def test_stale_cc_cleared_and_dispatch_recovers(monkeypatch):
    env = _install_full(monkeypatch)
    assert env.registry.__dict__["_compute_capability"] == (8, 0)
    gr.begin_gpu_restore()
    assert gr.repair_gpu_capabilities_after_restore()["outcome"] == "complete"
    assert "_compute_capability" not in env.registry.__dict__
    assert env.registry.get_capable_backend("int8_linear", {}) == "cuda"


def test_partial_failure_stays_pending_then_recovers(monkeypatch):
    env = _install_full(monkeypatch, triton_failure=True)
    gr.begin_gpu_restore()
    failed = gr.repair_gpu_capabilities_after_restore()
    kitchen = failed["providers"]["kitchen_gpu_backends"]
    assert kitchen["cuda"] == "rerun"
    assert str(kitchen["triton"]).startswith("failed:")
    assert failed["outcome"] == "deferred"
    assert gr._provider_done["kitchen_gpu_backends"] is False
    env.fail["triton"] = False
    recovered = gr.ensure_gpu_capabilities_repaired_before_execution()
    assert recovered["outcome"] == "complete"


def test_genuine_unavailability_stays_pending_retry_allowed(monkeypatch):
    env = _install_full(monkeypatch)
    # Native rerun succeeds but the extension stays genuinely unavailable.
    env.registry._registerable = {"triton"}
    gr.begin_gpu_restore()
    first = gr.repair_gpu_capabilities_after_restore()
    kitchen = first["providers"]["kitchen_gpu_backends"]
    assert kitchen["cuda"] == "rerun"
    assert kitchen["repaired"] is False
    assert kitchen["reason"] == "backend_unavailable"
    assert first["outcome"] == "deferred"
    register_count = len(env.registry.register_calls)
    second = gr.repair_gpu_capabilities_after_restore()
    assert second["outcome"] == "deferred"
    assert second.get("reason") != "already_done"
    assert len(env.registry.register_calls) > register_count


def test_quant_ops_overlap_untouched(monkeypatch):
    qops = types.ModuleType("comfy.quant_ops")
    qops.SENTINEL = {"touched": False}
    monkeypatch.setitem(sys.modules, "comfy.quant_ops", qops)
    env = _install_full(monkeypatch)
    gr.begin_gpu_restore()
    assert gr.repair_gpu_capabilities_after_restore()["outcome"] == "complete"
    assert qops.SENTINEL == {"touched": False}
    assert env.registry.get_capable_backend("int8_linear", {}) == "cuda"
    # The coordinator never needs quant_ops at all.
    monkeypatch.delitem(sys.modules, "comfy.quant_ops")
    gr.begin_gpu_restore()
    assert gr.repair_gpu_capabilities_after_restore()["outcome"] == "complete"


# ── Attention device limit ────────────────────────────────────────────────


def test_attention_limit_repaired_on_nvidia(monkeypatch):
    env = _install_full(monkeypatch, limit=STALE_LIMIT)
    gr.begin_gpu_restore()
    report = gr.repair_gpu_capabilities_after_restore()
    attention = report["providers"]["comfy_attention_device_limits"]
    assert attention["outcome"] == "complete"
    assert (attention["limit_before"], attention["limit_after"]) == (
        STALE_LIMIT,
        FIXED_LIMIT,
    )
    assert env.mm.SDP_BATCH_LIMIT == FIXED_LIMIT


@pytest.mark.parametrize("existing", [FIXED_LIMIT, 4096, 2**20])
def test_attention_preserves_existing_values_and_overrides(monkeypatch, existing):
    env = _install_full(monkeypatch, limit=existing)
    gr.begin_gpu_restore()
    report = gr.repair_gpu_capabilities_after_restore()
    attention = report["providers"]["comfy_attention_device_limits"]
    assert attention["outcome"] == "complete"
    assert attention["limit_after"] == existing
    assert env.mm.SDP_BATCH_LIMIT == existing


def test_attention_inert_while_cpu_state_then_completes_after_reattach(
    monkeypatch,
):
    env = _install_full(monkeypatch, cpu_state="CPU", limit=STALE_LIMIT)
    gr.begin_gpu_restore()
    first = gr.repair_gpu_capabilities_after_restore()
    attention = first["providers"]["comfy_attention_device_limits"]
    assert attention["outcome"] == "deferred"
    assert attention["reason"] == "cpu_state"
    assert env.mm.SDP_BATCH_LIMIT == STALE_LIMIT
    assert gr._provider_done["comfy_attention_device_limits"] is False
    # Minimal logical reattach flips CPU-state to GPU; the next pass completes.
    env.mm.cpu_state = env.mm.CPUState.GPU
    second = gr.repair_gpu_capabilities_after_restore()
    assert (
        second["providers"]["comfy_attention_device_limits"]["outcome"]
        == "complete"
    )
    assert env.mm.SDP_BATCH_LIMIT == FIXED_LIMIT


def test_attention_non_nvidia_not_applicable(monkeypatch):
    env = _install_full(monkeypatch, device_name="AMD MI300")
    gr.begin_gpu_restore()
    report = gr.repair_gpu_capabilities_after_restore()
    attention = report["providers"]["comfy_attention_device_limits"]
    assert attention["outcome"] == "not-applicable"
    assert env.mm.SDP_BATCH_LIMIT == STALE_LIMIT
    assert gr._provider_done["comfy_attention_device_limits"] is True
    assert report["outcome"] == "complete"


def test_excluded_state_untouched(monkeypatch):
    env = _install_full(monkeypatch)
    monkeypatch.delitem(sys.modules, "comfy.quant_ops", raising=False)
    before = (env.mm.cpu_state, env.mm.attention_backend, env.mm.vram_state)
    gr.begin_gpu_restore()
    assert gr.repair_gpu_capabilities_after_restore()["outcome"] == "complete"
    # Deliberately OUT: model_management full refresh, attention backend
    # rebinding / availability flags, quant_ops replay.
    assert (env.mm.cpu_state, env.mm.attention_backend, env.mm.vram_state) == before
    assert not hasattr(env.mm, "refreshed")
    assert "comfy.quant_ops" not in sys.modules
    assert env.registry._priority == ["cuda", "triton", "eager"]
    assert set(env.registry._disabled) == set()


def test_legacy_entrypoint_delegates_to_canonical(monkeypatch):
    from comfymodal_runtime import ideogram_cuda_profile as ideo

    _install_full(monkeypatch)
    gr.begin_gpu_restore()
    result = ideo.repair_kitchen_gpu_backends_after_restore()
    assert result["provider"] == "kitchen_gpu_backends"
    assert result["outcome"] == "complete"
    assert result["cuda"] == "rerun"


# ── Wiring (bounded source checks; behavior lives above) ──────────────────


def _modal_source() -> str:
    root = Path(__file__).resolve().parents[1]
    return (root / "comfymodal_runtime" / "modal_app.py").read_text(encoding="utf-8")


def _method_segment(source: str, marker: str) -> str:
    start = source.index(marker)
    tail = source[start + len(marker):]
    ends = []
    for stop in ("\n    async def ", "\n    def "):
        idx = tail.find(stop)
        if idx != -1:
            ends.append(idx)
    end = min(ends) if ends else len(tail)
    return source[start:start + len(marker) + end]


def test_restore_repairs_before_minimal_fast_return():
    source = _modal_source()
    restore = source[source.index("    def restore(self) -> dict[str, Any]:"):]
    begin = restore.index("begin_gpu_restore()")
    repair = restore.index("repair_gpu_capabilities_after_restore()")
    minimal_gate = restore.index("if _golden_minimal_restore_enabled()")
    minimal_return = restore.index("return self._golden_minimal_restore(")
    assert begin < repair < minimal_gate < minimal_return
    # Neutral coordinator owns every restore seam now; the profiling module
    # carries no restore-time repair call.
    assert "repair_kitchen_gpu_backends_after_restore" not in source
    assert "ideogram_cuda_profile" not in source
    assert "emit_kitchen_backend_proof" not in restore[:minimal_return]
    assert "install_int8_selection_counter" not in restore[:minimal_return]


def test_cuda_init_retry_precedes_sage_policy():
    source = _modal_source()
    init = source.index("def initialize_cuda()")
    retry = source.index("repair_gpu_capabilities_after_restore()", init)
    sage = source.index("def select_sage_runtime_mode()")
    apply_policy = source.index("def apply_sage_policy()")
    assert init < retry < sage < apply_policy
    segment = source[init:sage]
    assert "gpu_restore" in segment
    assert "ideogram_cuda_profile" not in segment


def test_execution_boundaries_observe_completion_before_early_return():
    source = _modal_source()
    ensure = "ensure_gpu_capabilities_repaired_before_execution()"
    early_cancel = "execution cancelled before PromptExecutor start"
    for marker in (
        "    async def _run_in_process(",
        "    async def _execute_v2_prompt_executor(",
    ):
        segment = _method_segment(source, marker)
        assert ensure in segment, marker
        assert segment.index(ensure) < segment.index(early_cancel), marker
    # Golden owns its request lifecycle: repair precedes the GPU-readiness gate.
    readiness_call = source.index("            ensure_gpu_ready()\n")
    window = source[max(0, readiness_call - 2000):readiness_call]
    assert ensure in window


def test_minimal_logical_reattach_completes_repair():
    source = _modal_source()
    segment = _method_segment(source, "    def _golden_minimal_restore(")
    attach = segment.index("self._golden_minimal_restore_logical_gpu_state()")
    repair = segment.index("repair_gpu_capabilities_after_restore()")
    assert attach < repair


def test_new_restore_resets_inherited_completion(monkeypatch):
    env = _install_full(monkeypatch)
    gr.begin_gpu_restore()
    assert gr.repair_gpu_capabilities_after_restore()["outcome"] == "complete"
    assert (
        gr.ensure_gpu_capabilities_repaired_before_execution()["reason"]
        == "already_done"
    )
    calls_after_first = dict(env.calls)
    # A new restore lifecycle must not inherit the previous completion.
    gr.begin_gpu_restore()
    report = gr.repair_gpu_capabilities_after_restore()
    assert report["outcome"] == "complete"
    assert env.calls["cuda"] > calls_after_first["cuda"]
    assert env.calls["triton"] > calls_after_first["triton"]

# -- model_management derived-state provider --------------------------

def _install_cli_args(monkeypatch, **flags):
    cli = types.ModuleType("comfy.cli_args")
    defaults = dict(
        use_pytorch_cross_attention=False,
        use_split_cross_attention=False,
        use_quad_cross_attention=False,
        use_sage_attention=False,
        use_flash_attention=False,
        use_ck_attention=False,
        async_offload=None,
        disable_async_offload=False,
        fast=[],
    )
    defaults.update(flags)
    cli.args = SimpleNamespace(**defaults)
    monkeypatch.setitem(sys.modules, "comfy.cli_args", cli)
    return cli.args


def _install_mm_full(monkeypatch, *, cpu_state="GPU", ratio=0.4,
                     pytorch_attn=False, streams=0, tvn=(2, 14),
                     nvidia=True, amd=False):
    mm = types.ModuleType("comfy.model_management")
    mm.CPUState = SimpleNamespace(CPU="CPU", GPU="GPU")
    mm.cpu_state = cpu_state
    mm.MIN_WEIGHT_MEMORY_RATIO = ratio
    mm.ENABLE_PYTORCH_ATTENTION = pytorch_attn
    mm.NUM_STREAMS = streams
    mm.torch_version_numeric = tvn
    mm.XFORMERS_IS_AVAILABLE = False
    mm.PRIORITIZE_FP16 = False
    mm.is_nvidia = lambda: bool(nvidia) and mm.cpu_state == "GPU"
    mm.is_amd = lambda: bool(amd)
    mm.is_intel_xpu = lambda: False
    mm.is_ascend_npu = lambda: False
    mm.is_mlu = lambda: False
    mm.is_ixuca = lambda: False
    mm.xformers_enabled = lambda: False
    monkeypatch.setitem(sys.modules, "comfy.model_management", mm)
    return mm


def _install_attn_mod(monkeypatch, *, kitchen_flag=False, selected="attention_sub_quad"):
    am = types.ModuleType("comfy.ldm.modules.attention")
    def _fn(name):
        def _f(*a, **k):
            raise AssertionError("fake attention fn called")
        _f.__name__ = name
        return _f
    for _name in ("attention_sage", "attention_flash", "attention_xformers",
                  "attention_pytorch", "attention_sub_quad", "attention_split",
                  "attention_comfy_kitchen_int8", "attention3_sage"):
        setattr(am, _name, _fn(_name))
    am.optimized_attention = getattr(am, selected)
    am.optimized_attention_masked = getattr(am, selected)
    am.COMFY_KITCHEN_INT8_ATTENTION_IS_AVAILABLE = kitchen_flag
    am.SAGE_ATTENTION_IS_AVAILABLE = False
    am.SAGE_ATTENTION3_IS_AVAILABLE = False
    am.FLASH_ATTENTION_IS_AVAILABLE = False
    am.REGISTERED_ATTENTION_FUNCTIONS = {}
    def _register(name, fn):
        if name not in am.REGISTERED_ATTENTION_FUNCTIONS:
            am.REGISTERED_ATTENTION_FUNCTIONS[name] = fn
    am.register_attention_function = _register
    monkeypatch.setitem(sys.modules, "comfy.ldm.modules.attention", am)
    return am


def _install_ck_probe(monkeypatch, value=True, raises=False):
    ck = sys.modules.get("comfy_kitchen")
    if ck is None:
        ck = types.ModuleType("comfy_kitchen")
        monkeypatch.setitem(sys.modules, "comfy_kitchen", ck)
    def _probe():
        if raises:
            raise RuntimeError("fake probe failure")
        return value
    ck.int8_attention_is_available = _probe
    return ck


def _install_mm_full_stack(monkeypatch, *, visible=True, cpu_state="GPU",
                           ratio=0.4, pytorch_attn=False, streams=0,
                           kitchen_flag=False, selected="attention_sub_quad",
                           probe=True, **cli_flags):
    cuda = _CudaFake(visible=visible)
    _install_torch(monkeypatch, cuda)
    mm = _install_mm_full(monkeypatch, cpu_state=cpu_state, ratio=ratio,
                          pytorch_attn=pytorch_attn, streams=streams)
    _install_cli_args(monkeypatch, **cli_flags)
    am = _install_attn_mod(monkeypatch, kitchen_flag=kitchen_flag,
                           selected=selected)
    _install_ck_probe(monkeypatch, value=probe)
    return SimpleNamespace(cuda=cuda, mm=mm, am=am)


def test_mm_derived_repaired_on_nvidia(monkeypatch):
    _install_mm_full_stack(monkeypatch)
    out = gr.repair_gpu_capabilities_after_restore()
    assert out["providers"]["model_management_derived_state"]["outcome"] == "complete"
    mm = sys.modules["comfy.model_management"]
    assert mm.MIN_WEIGHT_MEMORY_RATIO == 0.0
    assert mm.ENABLE_PYTORCH_ATTENTION is True
    assert mm.NUM_STREAMS == 2


def test_mm_explicit_flags_preserved(monkeypatch):
    _install_mm_full_stack(monkeypatch, use_split_cross_attention=True,
                           async_offload=4)
    out = gr.repair_gpu_capabilities_after_restore()
    assert out["providers"]["model_management_derived_state"]["outcome"] == "complete"
    mm = sys.modules["comfy.model_management"]
    assert mm.ENABLE_PYTORCH_ATTENTION is False
    assert mm.NUM_STREAMS == 4


def test_mm_inert_while_cpu_state_then_repairs(monkeypatch):
    env = _install_mm_full_stack(monkeypatch, cpu_state="CPU")
    first = gr.repair_gpu_capabilities_after_restore()
    assert first["providers"]["model_management_derived_state"]["outcome"] == "deferred"
    assert env.mm.MIN_WEIGHT_MEMORY_RATIO == 0.4
    env.mm.cpu_state = "GPU"
    second = gr.repair_gpu_capabilities_after_restore()
    assert second["providers"]["model_management_derived_state"]["outcome"] == "complete"
    assert env.mm.MIN_WEIGHT_MEMORY_RATIO == 0.0


def test_mm_cuda_invisible_no_mutation(monkeypatch):
    env = _install_mm_full_stack(monkeypatch, visible=False)
    out = gr.repair_gpu_capabilities_after_restore()
    assert out["providers"]["model_management_derived_state"]["outcome"] == "deferred"
    assert env.mm.ENABLE_PYTORCH_ATTENTION is False


def test_attention_selection_pytorch_on_nvidia(monkeypatch):
    _install_mm_full_stack(monkeypatch)
    out = gr.repair_gpu_capabilities_after_restore()
    prov = out["providers"]["attention_backend_selection"]
    assert prov["outcome"] == "complete"
    assert prov["after"] == "pytorch"
    assert prov["kitchen_available"] is True
    assert "comfy_kitchen_int8" in prov["registered_added"]
    am = sys.modules["comfy.ldm.modules.attention"]
    assert am.optimized_attention.__name__ == "attention_pytorch"
    assert am.optimized_attention_masked.__name__ == "attention_pytorch"


def test_attention_explicit_sage_flag_not_forced(monkeypatch):
    _install_mm_full_stack(monkeypatch, use_sage_attention=True)
    out = gr.repair_gpu_capabilities_after_restore()
    prov = out["providers"]["attention_backend_selection"]
    assert prov["outcome"] == "complete"
    assert prov["after"] == "sage"


def test_attention_kitchen_requested_unavailable_errors(monkeypatch):
    _install_mm_full_stack(monkeypatch, use_ck_attention=True, probe=False)
    out = gr.repair_gpu_capabilities_after_restore()
    prov = out["providers"]["attention_backend_selection"]
    assert prov["outcome"] == "error"
    assert prov["reason"] == "kitchen_requested_unavailable"
    am = sys.modules["comfy.ldm.modules.attention"]
    assert am.optimized_attention.__name__ == "attention_sub_quad"


def test_attention_from_import_limitation_documented(monkeypatch):
    env = _install_mm_full_stack(monkeypatch)
    am = env.am
    stale_ref = am.optimized_attention_masked
    out = gr.repair_gpu_capabilities_after_restore()
    assert out["providers"]["attention_backend_selection"]["outcome"] == "complete"
    assert stale_ref.__name__ == "attention_sub_quad"
    assert am.optimized_attention_masked.__name__ == "attention_pytorch"


def test_attention_provider_order_after_mm(monkeypatch):
    _install_mm_full_stack(monkeypatch)
    names = [fn.__name__ for fn in gr._PROVIDERS]
    assert names.index("_repair_model_management_derived_state") < names.index(
        "_repair_attention_backend_selection")

# -- attention consumer aliases --------------------------

def _install_attn_selectable(monkeypatch, *, kitchen_flag=False,
                             selected="attention_sub_quad"):
    am = _install_attn_mod(monkeypatch, kitchen_flag=kitchen_flag,
                           selected=selected)
    return am


def _install_consumer(monkeypatch, dotted, attr, value):
    parts = dotted.split(".")
    top = sys.modules.get(parts[0])
    if top is None:
        top = types.ModuleType(parts[0])
        monkeypatch.setitem(sys.modules, parts[0], top)
    mod = types.ModuleType(dotted)
    setattr(mod, attr, value)
    monkeypatch.setitem(sys.modules, dotted, mod)
    parent = sys.modules.get(".".join(parts[:-1]))
    if parent is not None:
        try:
            setattr(parent, parts[-1], mod)
        except Exception:
            pass
    return mod


def _install_alias_world(monkeypatch, *, probe=True, stale_fn="attention_sub_quad"):
    cuda = _CudaFake(visible=True)
    _install_torch(monkeypatch, cuda)
    mm = _install_mm_full(monkeypatch)
    mm.ENABLE_PYTORCH_ATTENTION = True
    _install_cli_args(monkeypatch)
    am = _install_attn_mod(monkeypatch)
    _install_ck_probe(monkeypatch, value=probe)
    stale = getattr(am, stale_fn)
    _install_consumer(monkeypatch, "comfy.ldm.ideogram4.model",
                      "optimized_attention_masked", stale)
    _install_consumer(monkeypatch, "comfy.ldm.flux.math",
                      "optimized_attention", stale)
    return SimpleNamespace(cuda=cuda, mm=mm, am=am, stale=stale)


def test_aliases_rebind_stale_holders(monkeypatch):
    env = _install_alias_world(monkeypatch)
    report = gr.repair_gpu_capabilities_after_restore()
    sel = report["providers"]["attention_backend_selection"]
    assert sel["outcome"] == "complete"
    assert sel["after"] == "pytorch"
    out = report["providers"]["attention_consumer_aliases"]
    assert out["outcome"] == "complete"
    assert out["rebound"] >= 2
    ide = sys.modules["comfy.ldm.ideogram4.model"]
    flx = sys.modules["comfy.ldm.flux.math"]
    assert ide.optimized_attention_masked.__name__ == "attention_pytorch"
    assert flx.optimized_attention.__name__ == "attention_pytorch"


def test_aliases_preserve_custom_override(monkeypatch):
    env = _install_alias_world(monkeypatch)
    custom_called = []
    def _custom(*a, **k):
        custom_called.append(True)
    _custom.__name__ = "custom_attn"
    _install_consumer(monkeypatch, "comfy.ldm.wan.model",
                      "optimized_attention", _custom)
    report = gr.repair_gpu_capabilities_after_restore()
    out = report["providers"]["attention_consumer_aliases"]
    assert out["outcome"] == "complete"
    assert out["preserved_custom"] >= 1
    assert sys.modules["comfy.ldm.wan.model"].optimized_attention is _custom


def test_aliases_missing_modules_skipped(monkeypatch):
    _install_alias_world(monkeypatch)
    report = gr.repair_gpu_capabilities_after_restore()
    out = report["providers"]["attention_consumer_aliases"]
    assert out["outcome"] == "complete"
    assert out["missing"] > 0
    assert out["checked"] == len(gr._ATTENTION_CONSUMER_ALIASES)


def test_aliases_defer_without_selection(monkeypatch):
    _install_alias_world(monkeypatch)
    gr.begin_gpu_restore()
    out = gr._repair_attention_consumer_aliases()
    assert out["outcome"] == "deferred"
    assert out["reason"] == "selection_pending"


def test_aliases_kitchen_flag_rebound(monkeypatch):
    _install_alias_world(monkeypatch, probe=True)
    mm_vae = types.ModuleType("comfy.ldm.minimax.vae")
    mm_vae.COMFY_KITCHEN_INT8_ATTENTION_IS_AVAILABLE = False
    monkeypatch.setitem(sys.modules, "comfy.ldm.minimax.vae", mm_vae)
    report = gr.repair_gpu_capabilities_after_restore()
    out = report["providers"]["attention_consumer_aliases"]
    assert out["outcome"] == "complete"
    assert mm_vae.COMFY_KITCHEN_INT8_ATTENTION_IS_AVAILABLE is True
    assert out["rebound"] >= 1


def test_aliases_already_correct_noop(monkeypatch):
    env = _install_alias_world(monkeypatch)
    report = gr.repair_gpu_capabilities_after_restore()
    first = report["providers"]["attention_consumer_aliases"]
    assert first["outcome"] == "complete"
    gr._provider_done[gr._ALIASES_KEY] = False
    second = gr.repair_gpu_capabilities_after_restore()
    out = second["providers"]["attention_consumer_aliases"]
    assert out["outcome"] == "complete"
    assert out["rebound"] == 0
    assert out["unchanged"] >= 2


def test_alias_table_contract():
    kinds = {"masked", "unmasked", "kitchen_flag"}
    seen = set()
    for path, attr, kind in gr._ATTENTION_CONSUMER_ALIASES:
        assert kind in kinds
        assert path.startswith("comfy.")
        assert (path, attr) not in seen
        seen.add((path, attr))
        if kind == "kitchen_flag":
            assert attr == "COMFY_KITCHEN_INT8_ATTENTION_IS_AVAILABLE"
        elif kind == "masked":
            assert attr == "optimized_attention_masked"
        else:
            assert attr == "optimized_attention"
    assert len(gr._ATTENTION_CONSUMER_ALIASES) >= 40
