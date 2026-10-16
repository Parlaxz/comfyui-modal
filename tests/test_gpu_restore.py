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
    return SimpleNamespace(
        cuda=cuda, registry=registry, calls=calls, fail=fail, mm=mm
    )


# ── Lifecycle ─────────────────────────────────────────────────────────────


def test_full_lifecycle_complete(monkeypatch):
    env = _install_full(monkeypatch)
    assert gr.begin_gpu_restore() == {
        "reset": True,
        "pending": ["comfy_attention_device_limits", "kitchen_gpu_backends"],
    }
    report = gr.repair_gpu_capabilities_after_restore()
    assert report["outcome"] == "complete"
    assert report["pending"] == []
    assert sorted(report["completed"]) == [
        "comfy_attention_device_limits",
        "kitchen_gpu_backends",
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
