"""R44F: native zero-copy CLIP adoption over the request FastSafe lane.

Coverage (all local, CPU-only, no Modal/network/CUDA required):

* Flag gating            — ``request_fastpath.clip_native_adopt_enabled``
* Construction decisions — ``request_clip_fastsafe._native_adoption_gates``
                           (device/dtype-parity/uniformity/transform/quant)
* Assign-style bind      — synthetic same-storage data_ptr/value/dtype/shape
                           proof through the scoped ``CLIP.load_sd`` seam
* Full mapping accounting— explicit transformed / non-parameter buckets,
                           byte coverage, missing-parameter fail-closed
* Owner lifetime         — retained on success, closed on fail-closed
* Owner release point    — per-adopted-patcher ``ON_DETACH`` callback
                           (Group 9): partial detach keeps owners open,
                           full detach releases exactly once, hook-install
                           gaps fail closed before publication
* Residency bookkeeping  — already-target-resident ``load_models_gpu``
                           compatibility WITHOUT a model-sized allocation or
                           copy (mocked allocator counters stay flat)
* Sticky fallback truth  — missing/mismatched keys fail closed, terminal
                           ledger + loader_selection fallback recorded
* Flag-off neutrality    — the proven R44B/R44E copy-mode producer path is
                           the default when the flag is unset

The producer world is exercised through injected fake modules (same pattern
as tests/test_r44b_request_fastsafe.py) with REAL torch tensors so the
data_ptr/shape/dtype semantics are genuine; the CUDA allocator counters are
stubbed to constants so "no model-sized allocation" is directly observable.
"""
from __future__ import annotations

import sys
import types

import pytest

torch = pytest.importorskip("torch")

from comfymodal_runtime import request_clip_fastsafe as rcfs
from comfymodal_runtime import request_fastpath as rfp

# Inner-module state-dict names (exactly how Comfy TE leaves receive them).
TENSOR_KEYS = ("weight", "bias", "logit_scale")
SHAPES = {"weight": (4, 3), "bias": (3,), "logit_scale": ()}
BLOB_KEY = "spiece_model"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeTrace:
    def emit(self, name, phase=None, metadata=None, **extra):
        md = dict(metadata or {})
        md.update(extra)
        self.events.append((str(name), md))

    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def names(self) -> list[str]:
        return [name for name, _ in self.events]

    def payloads(self, name: str) -> list[dict]:
        return [md for evt, md in self.events if evt == name]


class FakeLoader:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeFB:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeDescriptor:
    """Header-only stand-in for ModelFileDescriptor."""

    def __init__(self, *, keys=TENSOR_KEYS, dtypes=None, shapes=None,
                 size_bytes=2048, fresh=True, metadata=None):
        self.role = "clip"
        self.keys = tuple(keys)
        self.shapes = dict(shapes or {k: SHAPES.get(k, (2,)) for k in self.keys})
        self.dtypes = dict(dtypes or {k: "F32" for k in self.keys})
        self.metadata = dict(metadata or {})
        self.size_bytes = int(size_bytes)
        self.target_device = "cuda:0"
        self._fresh = bool(fresh)

    def fresh(self) -> bool:
        return self._fresh


def _fake_torch(monkeypatch):
    """Real torch semantics + stubbed CUDA allocator counters.

    The constant counters make "no model-sized allocation/copy" directly
    assertable: any real copy of model-sized payloads cannot move these
    numbers, while the producer's own delta math stays consistent."""
    mod = types.ModuleType("torch")
    for name in dir(torch):
        if name.startswith("__"):
            continue
        try:
            mod.__dict__[name] = getattr(torch, name)
        except Exception:
            pass
    mod.cuda = types.SimpleNamespace(
        current_device=lambda: 0,
        is_available=lambda: True,
        memory_allocated=lambda: 4096,
        memory_reserved=lambda: 8192,
        max_memory_allocated=lambda: 8192,
        max_memory_reserved=lambda: 16384,
        reset_peak_memory_stats=lambda: None,
        empty_cache=lambda: None,
        synchronize=lambda: None,
    )
    monkeypatch.setitem(sys.modules, "torch", mod)
    return mod


@pytest.fixture
def fastsafe_env(monkeypatch):
    monkeypatch.setenv(rfp.FLAG_MASTER, "1")
    monkeypatch.setenv(rfp.FLAG_CLIP, "1")
    monkeypatch.delenv(rfp.FLAG_CLIP_NATIVE_ADOPT, raising=False)


@pytest.fixture
def adopt_env(fastsafe_env, monkeypatch):
    monkeypatch.setenv(rfp.FLAG_CLIP_NATIVE_ADOPT, "1")


@pytest.fixture(autouse=True)
def _restore_pkg_submodule_attrs():
    """Restore ``comfymodal_runtime.<sub>`` package attributes after each test.

    Relative imports (``from . import clip_fast_hydration``) cache the bound
    module as an attribute ON THE PARENT PACKAGE, which outlives
    ``monkeypatch.setitem(sys.modules, ...)`` restoration.  Without this
    fixture, a fake bound during one of THIS file's tests would shadow the
    fresh fakes other test files install afterwards (observed as cross-file
    pollution in tests/test_r44b_request_fastsafe.py)."""
    import comfymodal_runtime as pkg

    attrs = (
        "clip_fast_hydration",
        "clip_fast_hydration_wiring",
        "loader_selection",
        "model_preload",
        "checkpoint_prewarm",
    )
    saved = {name: getattr(pkg, name, None) for name in attrs}
    yield
    for name, value in saved.items():
        if value is None:
            try:
                delattr(pkg, name)
            except Exception:
                pass
        else:
            try:
                setattr(pkg, name, value)
            except Exception:
                pass


class World:
    """Mutable handles the fake-module installers share with the tests."""

    def __init__(self) -> None:
        self.fs_calls: list[str] = []
        self.ltf_calls: list[str] = []
        self.owners_created: list[tuple[FakeLoader, FakeFB]] = []
        self.owner_calls: list[tuple[Any, Any]] = []
        self.hydrated: list[Any] = []
        self.record_mode: list[tuple] = []
        self.observed: list[tuple] = []
        self.served_sds: list[dict] = []
        self.mm_load_calls: list[tuple] = []
        self.current_loaded: list[Any] = []
        #: devices seen BY THE FAKE CONSTRUCTION from
        #: text_encoder_initial_device (meta inside the window, cpu when
        #: the flag is off / after restore).
        self.construction_initial_devices: list[Any] = []
        self.tensors_by_path: dict[str, dict] = {}
        #: when set, the served sd is missing one weight key (fail-closed
        #: harness); the fake constructor still builds the FULL skeleton.
        self.drop_key: str | None = None
        self.resolved = ""
        #: when True, the fake patcher's ``add_callback`` raises — simulating
        #: a patcher whose callback/ownership lifecycle is unsupported (the
        #: hook-install fail-closed harness).
        self.break_owner_release_hook = False
        # Originals captured BEFORE any seam runs (restoration assertions).
        self.orig_ltf: Any = None
        self.orig_load_sd: Any = None
        self.orig_initial_device: Any = None
        #: expected runtime TE dtype name (drives the fake
        #: model_management.text_encoder_dtype); R44H1 lets tests select it.
        self.expected_dtype: str = "torch.float32"
        self.descriptor: FakeDescriptor = FakeDescriptor()


def _install_world(monkeypatch, tmp_path, *, world: World | None = None) -> World:
    world = world or World()
    # -- folder_paths --------------------------------------------------------
    fp_mod = types.ModuleType("folder_paths")
    ckpt = tmp_path / "clip.safetensors"
    ckpt.write_bytes(b"x")
    world.resolved = str(ckpt)
    fp_mod.get_full_path = lambda kind, name: world.resolved
    monkeypatch.setitem(sys.modules, "folder_paths", fp_mod)

    # -- torch (real semantics, stubbed CUDA counters) -----------------------
    _fake_torch(monkeypatch)

    # -- comfy package with utils / sd / model_management --------------------
    comfy_mod = types.ModuleType("comfy")
    utils_mod = types.ModuleType("comfy.utils")

    def load_torch_file(ckpt_path, *args, **kwargs):
        world.ltf_calls.append(str(ckpt_path))
        return {"__native_read__": str(ckpt_path)}

    utils_mod.load_torch_file = load_torch_file
    world.orig_ltf = load_torch_file

    sd_mod = types.ModuleType("comfy.sd")

    class _NativeLoadSD:
        """Stands in for comfy.sd.CLIP.load_sd (the seam target)."""

        def __call__(self, clip_self, sd, full_model=False):
            can_assign = clip_self.patcher.is_dynamic()
            for m in clip_self.cond_stage_model.modules():
                m.can_assign_sd = can_assign
            return clip_self.cond_stage_model.load_sd(sd)

    class CLIP:
        load_sd = _NativeLoadSD()

    sd_mod.CLIP = CLIP
    world.orig_load_sd = CLIP.load_sd

    mm_mod = types.ModuleType("comfy.model_management")

    def text_encoder_device():
        return torch.device("cuda:0")

    def text_encoder_dtype(device=None):
        # R44H1: resolve from world.expected_dtype ("torch.float16" etc.).
        name = str(world.expected_dtype).split(".", 1)[-1]
        return getattr(torch, name, torch.float32)

    def text_encoder_initial_device(load_device, offload_device, model_size=0):
        return torch.device("cpu")

    def load_models_gpu(models, memory_required=0, force_patch_weights=False,
                        force_full_load=False, **kw):
        world.mm_load_calls.append((tuple(models), force_full_load))
        for m in models:
            world.current_loaded.append(types.SimpleNamespace(model=m))

    mm_mod.text_encoder_device = text_encoder_device
    mm_mod.text_encoder_dtype = text_encoder_dtype
    mm_mod.text_encoder_initial_device = text_encoder_initial_device
    mm_mod.load_models_gpu = load_models_gpu
    mm_mod.current_loaded_models = world.current_loaded
    world.orig_initial_device = text_encoder_initial_device

    comfy_mod.utils = utils_mod
    comfy_mod.sd = sd_mod
    comfy_mod.model_management = mm_mod
    monkeypatch.setitem(sys.modules, "comfy", comfy_mod)
    monkeypatch.setitem(sys.modules, "comfy.utils", utils_mod)
    monkeypatch.setitem(sys.modules, "comfy.sd", sd_mod)
    monkeypatch.setitem(sys.modules, "comfy.model_management", mm_mod)

    # -- comfy.patcher_extension (CallbacksMP contract mirror) ----------------
    pe_mod = types.ModuleType("comfy.patcher_extension")

    class CallbacksMP:
        ON_DETACH = "on_detach_after"

    pe_mod.CallbacksMP = CallbacksMP
    comfy_mod.patcher_extension = pe_mod
    monkeypatch.setitem(sys.modules, "comfy.patcher_extension", pe_mod)

    # -- comfymodal_runtime hydration seams ----------------------------------
    cfh_mod = types.ModuleType("comfymodal_runtime.clip_fast_hydration")
    cfh_mod.MODE_FASTSAFE = "fastsafetensors_direct_gpu"
    cfh_mod.OWNER_ATTR = "_r44f_test_owners"
    cfh_mod._TOKENIZER_BLOB_KEYS = (BLOB_KEY,)

    def owner_attach(clip, loader, fb):
        world.owner_calls.append((loader, fb))
        owners = getattr(clip.patcher, cfh_mod.OWNER_ATTR, None)
        if owners is None:
            owners = []
            setattr(clip.patcher, cfh_mod.OWNER_ATTR, owners)
        owners.append((loader, fb))

    cfh_mod.owner_attach = owner_attach

    def release_owner(clip):
        """Mirror of the real helper over the fake OWNER_ATTR list: closes
        every owner component exactly once and removes the attribute."""
        patcher = getattr(clip, "patcher", None)
        if patcher is None:
            return False
        owners = getattr(patcher, cfh_mod.OWNER_ATTR, None)
        if not owners:
            return False
        for owner in owners:
            for component in owner:
                close = getattr(component, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception:
                        pass
        delattr(patcher, cfh_mod.OWNER_ATTR)
        return True

    cfh_mod.release_owner = release_owner
    cfh_mod.mark_clip_hydrated = lambda clip: world.hydrated.append(clip)
    monkeypatch.setitem(sys.modules, "comfymodal_runtime.clip_fast_hydration", cfh_mod)

    wiring_mod = types.ModuleType("comfymodal_runtime.clip_fast_hydration_wiring")

    def _fastsafe_load(path, metrics=None):
        world.fs_calls.append(str(path))
        tensors = {
            key: torch.zeros(SHAPES.get(key, (2,)), dtype=torch.float32)
            for key in TENSOR_KEYS
        }
        # The physical read returns the WHOLE file: tokenizer blob included.
        tensors[BLOB_KEY] = torch.zeros(8, dtype=torch.uint8)
        if world.drop_key:
            tensors.pop(world.drop_key, None)
        world.tensors_by_path[str(path)] = tensors
        if metrics is not None:
            metrics["fastsafe_setup_wall_ms"] = 0.1
            metrics["fastsafe_copy_wall_ms"] = 1.0
            metrics["fastsafe_get_keys_wall_ms"] = 0.0
            metrics["fastsafe_get_tensor_loop_wall_ms"] = 0.2
        loader, fb = FakeLoader(), FakeFB()
        world.owners_created.append((loader, fb))
        return (tensors, loader, fb)

    wiring_mod._fastsafe_load = _fastsafe_load
    wiring_mod._record_mode = lambda clip, mode, md: world.record_mode.append(
        (mode, dict(md))
    )
    monkeypatch.setitem(
        sys.modules, "comfymodal_runtime.clip_fast_hydration_wiring", wiring_mod
    )

    ls_mod = types.ModuleType("comfymodal_runtime.loader_selection")
    ls_mod.record_observed = lambda role, arm, **kw: world.observed.append(
        (role, arm, dict(kw))
    )
    ls_mod.normalize_observed = lambda role, arm: (
        "native_comfy" if arm == "native" else arm
    )
    monkeypatch.setitem(sys.modules, "comfymodal_runtime.loader_selection", ls_mod)

    # -- nodes with a NATIVE-construction fake CLIPLoader ---------------------
    nodes_mod = types.ModuleType("nodes")

    def build_fake_clip():
        """Mimic comfy.sd.load_clip over the GUARDED load_torch_file: serve
        the resident tensors, resolve the initial device (the meta seam),
        build a META skeleton, route the weight load through
        comfy.sd.CLIP.load_sd (the assign seam under test)."""
        import comfy.model_management as comfy_mm
        import comfy.sd
        import comfy.utils

        out = comfy.utils.load_torch_file(world.resolved, safe_load=True, return_metadata=True)
        payload = out[0] if isinstance(out, tuple) else out
        world.served_sds.append(payload)
        if not all(k in payload for k in TENSOR_KEYS):
            # Unguarded native reader (fallback path): simulate a genuine
            # disk read producing FRESH tensors at DIFFERENT storage.
            payload = {
                k: torch.zeros(SHAPES.get(k, (2,)), dtype=torch.float32)
                for k in TENSOR_KEYS
            }
        # CLIP.__init__ parity: the skeleton is built on whatever the
        # (seamed) initial-device resolver yields.
        initial_device = comfy_mm.text_encoder_initial_device(
            torch.device("cuda:0"), torch.device("cpu"), 1024
        )
        world.construction_initial_devices.append(initial_device)

        class Transformer(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.weight = torch.nn.Parameter(
                    torch.empty(SHAPES["weight"], dtype=torch.float32, device=initial_device)
                )
                self.bias = torch.nn.Parameter(
                    torch.empty(SHAPES["bias"], dtype=torch.float32, device=initial_device)
                )

            def load_sd(self, sd):
                return self.load_state_dict(
                    sd, strict=False, assign=getattr(self, "can_assign_sd", False)
                )

        class TinyTE(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.transformer = Transformer()
                self.logit_scale = torch.nn.Parameter(
                    torch.empty((), dtype=torch.float32, device=initial_device)
                )

            def load_sd(self, sd):
                r1 = self.transformer.load_sd(
                    {k: v for k, v in sd.items() if k != "logit_scale"}
                )
                self.load_state_dict(
                    {"logit_scale": sd["logit_scale"]},
                    strict=False,
                    assign=getattr(self, "can_assign_sd", False),
                )
                return r1

        class FakePatcher:
            """ModelPatcher mirror for the callback/detach contract: the
            callbacks dict shape, add_callback/get_all_callbacks semantics,
            and detach(unpatch_all) invoking ON_DETACH callbacks with
            (patcher, unpatch_all) — exactly like comfy/model_patcher.py."""

            def __init__(self, model):
                self.model = model
                self.load_device = torch.device("cuda:0")
                self.offload_device = torch.device("cpu")
                self.callbacks: dict[str, list] = {}
                self._broken_hook = bool(world.break_owner_release_hook)

            def is_dynamic(self):
                return False

            def add_callback(self, call_type, callback):
                if self._broken_hook:
                    raise RuntimeError("hook_install_unsupported")
                self.callbacks.setdefault(call_type, []).append(callback)

            def get_all_callbacks(self, call_type):
                return list(self.callbacks.get(call_type, []))

            def detach(self, unpatch_all=True):
                for callback in self.get_all_callbacks("on_detach_after"):
                    callback(self, unpatch_all)

        class FakeClip:
            pass

        clip = FakeClip()
        clip.cond_stage_model = TinyTE()
        clip.patcher = FakePatcher(clip.cond_stage_model)
        clip.tokenizer = types.SimpleNamespace(name="fake-tokenizer")
        comfy.sd.CLIP.load_sd(clip, payload)
        return (clip,)

    class CLIPLoader:
        def load_clip(self, clip_name, type="stable_diffusion", device="default"):
            return build_fake_clip()

    class DualCLIPLoader:
        def load_clip(self, clip_name1, clip_name2, type="sdxl", device="default"):
            return build_fake_clip()

    class CLIPTextEncode:
        def encode(self, text):
            return ([f"cond:{text}"], ["pooled"])

    nodes_mod.NODE_CLASS_MAPPINGS = {
        "CLIPLoader": CLIPLoader,
        "DualCLIPLoader": DualCLIPLoader,
        "CLIPTextEncode": CLIPTextEncode,
    }
    monkeypatch.setitem(sys.modules, "nodes", nodes_mod)

    # -- descriptor stub ------------------------------------------------------
    world.descriptor = FakeDescriptor(keys=TENSOR_KEYS + (BLOB_KEY,))
    monkeypatch.setattr(rfp, "build_descriptor", lambda *a, **k: world.descriptor)
    return world


def _nodes():
    import nodes as nodes_module

    return nodes_module.NODE_CLASS_MAPPINGS


def _comfy_mods():
    """Resolve the (fake) comfy modules CURRENTLY registered in sys.modules.

    Real ComfyUI is importable in this environment, so tests must never bind
    ``comfy.*`` at function top (that can capture the real package before the
    fakes are installed)."""
    return (
        sys.modules["comfy.utils"],
        sys.modules["comfy.sd"],
        sys.modules["comfy.model_management"],
    )


# ---------------------------------------------------------------------------
# Group 1: flag gating
# ---------------------------------------------------------------------------


def test_native_adopt_default_off(monkeypatch):
    for flag in (rfp.FLAG_MASTER, rfp.FLAG_CLIP, rfp.FLAG_CLIP_NATIVE_ADOPT):
        monkeypatch.delenv(flag, raising=False)
    assert rfp.clip_native_adopt_enabled() is False


def test_native_adopt_requires_clip_lane_and_flag(monkeypatch):
    monkeypatch.setenv(rfp.FLAG_MASTER, "1")
    monkeypatch.setenv(rfp.FLAG_CLIP, "1")
    monkeypatch.delenv(rfp.FLAG_CLIP_NATIVE_ADOPT, raising=False)
    assert rfp.clip_native_adopt_enabled() is False  # flag missing -> off
    monkeypatch.setenv(rfp.FLAG_CLIP_NATIVE_ADOPT, "1")
    assert rfp.clip_native_adopt_enabled() is True
    monkeypatch.setenv(rfp.FLAG_CLIP, "0")
    assert rfp.clip_native_adopt_enabled() is False  # clip lane off wins


# ---------------------------------------------------------------------------
# Group 2: native-parity construction decisions (pre-transport gates)
# ---------------------------------------------------------------------------


def _gates(descriptors, *, kwargs=None, args=()):
    return rcfs._native_adoption_gates(("clip_name",), args, kwargs or {}, descriptors)


def test_gates_pass_on_clean_uniform_checkpoint(adopt_env, monkeypatch, tmp_path):
    world = _install_world(monkeypatch, tmp_path)
    ok, reason, details = _gates([world.descriptor])
    assert ok is True
    assert reason == "ok"
    assert details["expected_te_dtype"] == "torch.float32"


def test_gates_reject_cpu_device_request(adopt_env, monkeypatch, tmp_path):
    world = _install_world(monkeypatch, tmp_path)
    ok, reason, _ = _gates([world.descriptor], kwargs={"device": "cpu"})
    assert ok is False and reason == "cpu_device_requested"


def test_gates_classify_bf16_fp16_as_cast_once(adopt_env, monkeypatch, tmp_path):
    world = _install_world(monkeypatch, tmp_path)
    world.expected_dtype = "torch.float16"
    desc = FakeDescriptor(dtypes={k: "BF16" for k in TENSOR_KEYS})
    ok, reason, details = _gates([desc])
    assert ok is True
    assert reason == "ok"
    assert details["adoption_mode"] == "cast_once_fp16"
    assert details["checkpoint_dtype"] == "BF16"


def test_gates_reject_unsupported_dtype_pair(adopt_env, monkeypatch, tmp_path):
    world = _install_world(monkeypatch, tmp_path)
    desc = FakeDescriptor(dtypes={k: "F64" for k in TENSOR_KEYS})
    ok, reason, _ = _gates([desc])
    assert ok is False and reason.startswith("unsupported_dtype_pair")


def test_gates_reject_non_uniform_dtype(adopt_env, monkeypatch, tmp_path):
    world = _install_world(monkeypatch, tmp_path)
    desc = FakeDescriptor(
        dtypes={TENSOR_KEYS[0]: "F32", TENSOR_KEYS[1]: "F16", TENSOR_KEYS[2]: "F32"}
    )
    ok, reason, _ = _gates([desc])
    assert ok is False and reason.startswith("non_uniform_dtype")


def test_gates_reject_native_preprocess_transform_keys(adopt_env, monkeypatch, tmp_path):
    _install_world(monkeypatch, tmp_path)
    for bad in (
        "text_projection",
        "lm_head.weight",
        "transformer.resblocks.0.ln_1.weight",
    ):
        desc = FakeDescriptor(keys=(bad,), dtypes={bad: "F32"}, shapes={bad: (2,)})
        ok, reason, _ = _gates([desc])
        assert ok is False, bad
        assert reason.startswith("native_preprocess_transform"), bad


def test_gates_reject_quantized_checkpoint(adopt_env, monkeypatch, tmp_path):
    _install_world(monkeypatch, tmp_path)
    desc = FakeDescriptor(metadata={"_quantization_metadata": "{}"})
    ok, reason, _ = _gates([desc])
    assert ok is False and reason.startswith("quantized_checkpoint")


# ---------------------------------------------------------------------------
# Group 3: end-to-end native zero-copy adoption (mocked transport/seams)
# ---------------------------------------------------------------------------


def test_native_producer_zero_copy_bind_and_single_physical_read(
    adopt_env, monkeypatch, tmp_path
):
    world = _install_world(monkeypatch, tmp_path)
    assert rcfs.install_request_clip_fastsafe() is True
    try:
        trace = FakeTrace()
        ctx = rfp.begin(request_id="r44f-ok", trace=trace)
        try:
            result = _nodes()["CLIPLoader"]().load_clip(clip_name="clip.safetensors")

            # Single physical read; the native reader NEVER ran.
            assert world.fs_calls == [world.resolved]
            assert world.ltf_calls == []

            clip = result[0]
            csm = clip.cond_stage_model
            served = world.tensors_by_path[world.resolved]
            # Assign-style bind: every parameter SHARES storage with the
            # served FastSafe tensor (data_ptr identity), same shape/dtype.
            assert csm.transformer.weight.data_ptr() == served["weight"].data_ptr()
            assert csm.transformer.bias.data_ptr() == served["bias"].data_ptr()
            assert csm.logit_scale.data_ptr() == served["logit_scale"].data_ptr()
            assert csm.transformer.weight.shape == served["weight"].shape
            assert csm.transformer.weight.dtype == served["weight"].dtype
            # Values travel with the storage (no reinitialization).
            served["weight"].fill_(7.0)
            assert bool((csm.transformer.weight == 7.0).all())
            # No meta skeleton residue anywhere.
            assert not any(p.is_meta for p in csm.parameters())
            # Published patcher reports NON-dynamic like a normal ModelPatcher
            # (the instance-level is_dynamic shadow was removed).
            assert "is_dynamic" not in clip.patcher.__dict__
            assert clip.patcher.is_dynamic() is False

            # Owners retained (NOT closed) for lifetime.
            assert len(world.owner_calls) == 1
            loader, fb = world.owners_created[0]
            assert loader.closed is False and fb.closed is False
            assert getattr(clip.patcher, "_r44f_test_owners") == [(loader, fb)]

            # Residency bookkeeping: load_models_gpu([patcher]) ran with
            # force_full_load and the patcher IS registered — without any
            # model-sized allocation/copy (stubbed counters stayed flat).
            assert len(world.mm_load_calls) == 1
            models_arg, force_full = world.mm_load_calls[0]
            assert models_arg == (clip.patcher,) and force_full is True
            assert any(lm.model is clip.patcher for lm in world.current_loaded)

            # Truth: canonical arm observed, result published, state ready.
            assert world.observed == [("clip", "fastsafetensors_direct_gpu", {})]
            assert ctx.result("clip") is clip
            assert ctx.clip_state == "ready"

            # Telemetry: adoption mode + full mapping accounting.
            start = trace.payloads("clip_fast_load_start")[0]
            assert start["adoption_mode"] == "same_storage_assign"
            end = trace.payloads("clip_fast_load_end")[0]
            assert end["ok"] is True
            assert end["adoption_mode"] == "same_storage_assign"
            assert end["bind_mode"] == "same_storage"
            assert end["checkpoint_tensor_count"] == len(TENSOR_KEYS) + 1  # + blob
            assert end["same_storage_count"] == len(TENSOR_KEYS)
            assert end["exception_count"] == 1  # tokenizer blob only
            assert end["transformed_count"] == 0
            assert end["missing_parameter_count"] == 0
            assert end["comparable_live_parameter_mapping_count"] == len(TENSOR_KEYS)
            assert end["comparable_live_storage_mapping_count"] == len(TENSOR_KEYS)
            assert end["extra_model_tensor_count"] == 0
            assert end["byte_coverage_pct"] == 100.0
            assert end["owner_retained"] is True
            assert end["residency_registered"] is True
            assert end["duplicate_residency_detected"] is False
            assert end["model_sized_copy_detected"] is False

            # Seams fully restored: default native behavior intact.
            comfy_utils, comfy_sd, comfy_mm = _comfy_mods()
            assert comfy_utils.load_torch_file is world.orig_ltf
            assert comfy_sd.CLIP.load_sd is world.orig_load_sd
            probe = comfy_mm.text_encoder_initial_device(
                torch.device("cuda:0"), torch.device("cpu")
            )
            assert probe == torch.device("cpu")
            # meta INSIDE the construction window (seam 2 engaged).
            assert world.construction_initial_devices == [torch.device("meta")]
        finally:
            rfp.teardown(ctx)
    finally:
        rcfs.uninstall_for_tests()


def test_native_producer_dual_loader_same_path(adopt_env, monkeypatch, tmp_path):
    world = _install_world(monkeypatch, tmp_path)
    assert rcfs.install_request_clip_fastsafe() is True
    try:
        ctx = rfp.begin(request_id="r44f-dual")
        try:
            result = _nodes()["DualCLIPLoader"]().load_clip(
                clip_name1="a.safetensors", clip_name2="b.safetensors"
            )
            clip = result[0]
            assert not any(p.is_meta for p in clip.cond_stage_model.parameters())
            # One FastSafe transport per FILE (two names => two reads/owners).
            assert len(world.fs_calls) == 2
            assert len(world.owner_calls) == 2
            assert world.observed == [("clip", "fastsafetensors_direct_gpu", {})]
        finally:
            rfp.teardown(ctx)
    finally:
        rcfs.uninstall_for_tests()


# ---------------------------------------------------------------------------
# Group 4: fail-closed — missing key, sticky truth, owner closure
# ---------------------------------------------------------------------------


def test_missing_key_fails_closed_with_sticky_truth(adopt_env, monkeypatch, tmp_path):
    world = _install_world(monkeypatch, tmp_path)
    world.drop_key = "bias"  # skeleton keeps a META leftover for it
    assert rcfs.install_request_clip_fastsafe() is True
    try:
        ctx = rfp.begin(request_id="r44f-missing")
        try:
            result = _nodes()["CLIPLoader"]().load_clip(clip_name="clip.safetensors")

            # Transport DID happen, then validation failed closed.
            assert len(world.fs_calls) == 1
            loader, fb = world.owners_created[0]
            assert loader.closed is True and fb.closed is True
            # Canonical native fallback observation + sticky terminal ledger.
            assert len(world.observed) == 1
            role, arm, kw = world.observed[0]
            assert (role, arm) == ("clip", "native_comfy")
            assert kw.get("fallback_attempted") is True
            assert any(
                "clip_fastsafe_failed:RuntimeError" in reason
                for reason in ctx.terminal_reasons()
            )
            # Nothing published; the request survived through the original.
            assert ctx.result("clip") is None
            assert isinstance(result, tuple) and len(result) == 1
            # The fallback ran OUTSIDE the guard: the native reader served it.
            assert len(world.ltf_calls) == 1
            # Seams restored even on the failure path.
            _, _, comfy_mm = _comfy_mods()
            assert comfy_mm.text_encoder_initial_device is world.orig_initial_device
        finally:
            rfp.teardown(ctx)
    finally:
        rcfs.uninstall_for_tests()


def test_ineligible_gate_releases_claim_without_transport(
    adopt_env, monkeypatch, tmp_path
):
    world = _install_world(monkeypatch, tmp_path)
    world.descriptor = FakeDescriptor(
        keys=("text_projection",),
        dtypes={"text_projection": "F32"},
        shapes={"text_projection": (2,)},
    )
    assert rcfs.install_request_clip_fastsafe() is True
    try:
        ctx = rfp.begin(request_id="r44f-ineligible")
        try:
            result = _nodes()["CLIPLoader"]().load_clip(clip_name="clip.safetensors")
            # No transport, no adoption; sticky ineligible terminal reason.
            assert world.fs_calls == []
            assert world.owner_calls == []
            assert any(
                "clip_fastsafe_ineligible:native_preprocess_transform" in reason
                for reason in ctx.terminal_reasons()
            )
            assert ctx.summary()["claims"]["clip"] is False
            assert ctx.result("clip") is None
            assert result[0] is not None  # original produced natively
        finally:
            rfp.teardown(ctx)
    finally:
        rcfs.uninstall_for_tests()


# ---------------------------------------------------------------------------
# Group 5: full mapping accounting buckets (unit)
# ---------------------------------------------------------------------------


def test_full_mapping_accounting_buckets():
    served = {
        "w": torch.zeros(4, 3, dtype=torch.float32),
        "transformed": torch.zeros(2, 2, dtype=torch.float32),
        BLOB_KEY: torch.zeros(8, dtype=torch.uint8),
        "unused": torch.zeros(3, dtype=torch.float32),
    }

    class Desc:
        keys = tuple(served.keys())
        shapes = {"w": (4, 3), "transformed": (5, 5), BLOB_KEY: (8,), "unused": (3,)}
        dtypes = {k: "F32" for k in keys}
        metadata = {}

    class CSM(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.w = torch.nn.Parameter(served["w"])  # same storage

    csm = CSM()
    # A buffer sharing served storage (non-parameter destination).
    csm.register_buffer("pos", served["unused"])

    accounting = rcfs._validate_native_bind(
        types.SimpleNamespace(cond_stage_model=csm, patcher=object(), tokenizer=object()),
        [served],
        [Desc()],
    )
    assert accounting["checkpoint_tensor_count"] == 4
    # w: direct parameter mapping; unused: direct BUFFER mapping.
    assert accounting["direct_mapping_count"] == 2
    assert accounting["same_storage_count"] == 2
    assert accounting["non_same_count"] == 2
    # transformed: header says (5,5), served tensor is (2,2).
    assert accounting["transformed_count"] == 1
    assert accounting["transformed_keys_sample"] == ["transformed"]
    # spiece_model blob lands in the explicit non-parameter bucket.
    assert accounting["exception_count"] == 1
    assert accounting["exception_keys_sample"] == [BLOB_KEY]
    assert accounting["parameter_count"] == 1
    assert accounting["buffer_count"] == 1
    assert accounting["matched_buffer_count"] == 1
    # R44F full-mapping telemetry: w is the only comparable live PARAMETER
    # mapping; the buffer adds one more comparable live STORAGE mapping;
    # every live tensor is represented by a comparable checkpoint entry.
    assert accounting["comparable_live_parameter_mapping_count"] == 1
    assert accounting["comparable_live_storage_mapping_count"] == 2
    assert accounting["extra_model_tensor_count"] == 0
    total = sum(t.numel() * t.element_size() for t in served.values())
    covered = served["w"].numel() * 4 + served["unused"].numel() * 4
    assert accounting["source_bytes_total"] == total
    assert accounting["byte_coverage_bytes"] == covered
    # Coverage is measured against parameter-ELIGIBLE bytes (the tokenizer
    # blob is excluded from the denominator).
    eligible = total - served[BLOB_KEY].numel() * served[BLOB_KEY].element_size()
    assert accounting["eligible_bytes_total"] == eligible
    assert accounting["byte_coverage_pct"] == round(100.0 * covered / eligible, 3)


def test_full_mapping_accounting_extra_model_tensors():
    """R44F full-mapping telemetry: a live buffer whose storage has NO
    comparable checkpoint entry lands in extra_model_tensor_count while the
    comparable parameter/storage mapping counts stay honest (parameters
    only vs parameters+buffers)."""
    served = {"w": torch.zeros(4, 3, dtype=torch.float32)}

    class Desc:
        keys = ("w",)
        shapes = {"w": (4, 3)}
        dtypes = {"w": "F32"}
        metadata = {}

    class CSM(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.w = torch.nn.Parameter(served["w"])  # same storage
            # Live scratch buffer backed by storage absent from the
            # checkpoint: never a fail-closed condition (buffers are not
            # required to map), but it must be counted as extra.
            self.register_buffer("scratch", torch.zeros(5, dtype=torch.float32))

    accounting = rcfs._validate_native_bind(
        types.SimpleNamespace(cond_stage_model=CSM(), patcher=object(), tokenizer=object()),
        [served],
        [Desc()],
    )
    assert accounting["comparable_live_parameter_mapping_count"] == 1
    assert accounting["comparable_live_storage_mapping_count"] == 1
    assert accounting["extra_model_tensor_count"] == 1
    # Existing fields preserved alongside the new telemetry.
    assert accounting["direct_mapping_count"] == 1
    assert accounting["same_storage_count"] == 1
    assert accounting["matched_buffer_count"] == 0
    assert accounting["missing_parameter_count"] == 0


def test_validate_native_bind_fails_on_copy_semantics():
    """A bind that COPIED values into freshly-initialized parameters (no
    shared storage) must fail closed — the exact property R44F buys."""
    served = {"w": torch.zeros(4, 3, dtype=torch.float32)}

    class Desc:
        keys = ("w",)
        shapes = {"w": (4, 3)}
        dtypes = {"w": "F32"}
        metadata = {}

    class CSM(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.w = torch.nn.Parameter(torch.zeros(4, 3, dtype=torch.float32))

    with pytest.raises(RuntimeError, match="missing_param_storage"):
        rcfs._validate_native_bind(
            types.SimpleNamespace(cond_stage_model=CSM(), patcher=object(), tokenizer=object()),
            [{"w": served["w"].clone()}],  # clone => different storage
            [Desc()],
        )


def test_validate_native_bind_fails_on_meta_residual():
    class Desc:
        keys = ()
        shapes = {}
        dtypes = {}
        metadata = {}

    class CSM(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.w = torch.nn.Parameter(torch.empty(2, device="meta"))

    with pytest.raises(RuntimeError, match="meta_residual"):
        rcfs._validate_native_bind(
            types.SimpleNamespace(
                cond_stage_model=CSM(), patcher=object(), tokenizer=object()
            ),
            [{}],
            [Desc()],
        )


# ---------------------------------------------------------------------------
# Group 6: forward-boundary residency instrumentation
# ---------------------------------------------------------------------------


def test_encode_wrapper_reports_residency_and_no_migration(
    adopt_env, monkeypatch, tmp_path
):
    world = _install_world(monkeypatch, tmp_path)
    assert rcfs.install_request_clip_fastsafe() is True
    try:
        trace = FakeTrace()
        ctx = rfp.begin(request_id="r44f-encode", trace=trace)
        try:
            mappings = _nodes()
            clip = mappings["CLIPLoader"]().load_clip(clip_name="clip.safetensors")[0]
            out = mappings["CLIPTextEncode"]().encode("hello")
            assert out == (["cond:hello"], ["pooled"])
            end = trace.payloads("clip_forward_end")[0]
            assert end["ok"] is True
            # The produced patcher is already registered (early residency
            # registration), so the post-forward scan sees it.
            assert end["clip_resident_registered"] is True
            # Stubbed allocator counters are flat: no model-sized migration.
            assert end["model_sized_migration_detected"] is False
            assert end["clip_parameter_bytes"] > 0
            assert any(lm.model is clip.patcher for lm in world.current_loaded)
        finally:
            rfp.teardown(ctx)
    finally:
        rcfs.uninstall_for_tests()


# ---------------------------------------------------------------------------
# Group 7: flag OFF preserves the proven R44B/R44E producer exactly
# ---------------------------------------------------------------------------


def test_flag_off_keeps_legacy_copy_mode_producer(fastsafe_env, monkeypatch, tmp_path):
    world = _install_world(monkeypatch, tmp_path)
    assert rcfs.install_request_clip_fastsafe() is True
    try:
        trace = FakeTrace()
        ctx = rfp.begin(request_id="r44f-off", trace=trace)
        try:
            result = _nodes()["CLIPLoader"]().load_clip(clip_name="clip.safetensors")
            # Legacy lane: single physical read, served dict passthrough.
            assert world.fs_calls == [world.resolved]
            assert world.ltf_calls == []
            served = world.served_sds[0]
            assert set(served.keys()) == set(TENSOR_KEYS) | {BLOB_KEY}
            # R44F adoption machinery never engaged: legacy lane labeled
            # copy_cuda_legacy, honest copy-mode verdict, no early residency
            # registration.
            start = trace.payloads("clip_fast_load_start")[0]
            end = trace.payloads("clip_fast_load_end")[0]
            assert start["adoption_mode"] == "copy_cuda_legacy"
            assert end["adoption_mode"] == "copy_cuda_legacy"
            assert end["bind_mode"] == "copy_cuda"
            assert world.mm_load_calls == []
            # Seams untouched: the initial-device resolver is the original and
            # yielded the plain CPU device during legacy construction.
            _, _, comfy_mm = _comfy_mods()
            assert comfy_mm.text_encoder_initial_device is world.orig_initial_device
            assert world.construction_initial_devices == [torch.device("cpu")]
            assert result[0] is not None
        finally:
            rfp.teardown(ctx)
    finally:
        rcfs.uninstall_for_tests()


# ---------------------------------------------------------------------------
# Group 8: config authority + Modal class-env boundary (R44D pattern)
# ---------------------------------------------------------------------------


def test_config_authority_registers_native_adopt_flag_default_off():
    from comfymodal_runtime import config_authority as ca

    spec = ca.GOLDEN_CONTROL_FLAGS["COMFYMODAL_V2_REQUEST_CLIP_FASTSAFE_NATIVE_ADOPT"]
    assert spec["type"] == "bool"
    assert spec["default"] is False
    assert spec["env_var"] == "COMFYMODAL_V2_REQUEST_CLIP_FASTSAFE_NATIVE_ADOPT"


def test_runtime_env_passthrough_default_off_and_verbatim_when_set(monkeypatch):
    from comfymodal_runtime.modal_app import _runtime_env

    key = "COMFYMODAL_V2_REQUEST_CLIP_FASTSAFE_NATIVE_ADOPT"
    with monkeypatch.context() as m:
        m.delenv(key, raising=False)
        env = _runtime_env()
    assert env.get(key) == "0"  # absent host env -> container default stays off

    with monkeypatch.context() as m:
        m.setenv(key, "1")
        env = _runtime_env()
    assert env.get(key) == "1"  # crosses the Modal class-env boundary verbatim


def test_profile_r44_request_fastsafe_pins_native_adopt_on():
    """The ONLY profile that defaults the flag on is r44-request-fastsafe."""
    try:
        from pathlib import Path

        from tools.v2_control import profiles as profiles_mod
    except Exception:  # pragma: no cover - tooling layout guard
        pytest.skip("tools.v2_control unavailable")
    profiles = profiles_mod.Profiles(
        Path(__file__).resolve().parents[1] / "config" / "v2" / "profiles"
    )
    resolved = profiles.resolve("r44-request-fastsafe")
    value = resolved.environment.get("COMFYMODAL_V2_REQUEST_CLIP_FASTSAFE_NATIVE_ADOPT")
    assert str(value) == "1"


# ---------------------------------------------------------------------------
# Group 9: R44F follow-up — per-patcher ON_DETACH owner-release point
# ---------------------------------------------------------------------------


def _adopt_once(monkeypatch, tmp_path, *, request_id: str):
    """Run one successful native adoption; returns (world, trace, ctx, clip).

    Callers own the teardown: ``rfp.teardown(ctx)`` +
    ``rcfs.uninstall_for_tests()``."""
    world = _install_world(monkeypatch, tmp_path)
    assert rcfs.install_request_clip_fastsafe() is True
    trace = FakeTrace()
    ctx = rfp.begin(request_id=request_id, trace=trace)
    clip = _nodes()["CLIPLoader"]().load_clip(clip_name="clip.safetensors")[0]
    return world, trace, ctx, clip


def test_owner_release_hook_installed_with_telemetry(adopt_env, monkeypatch, tmp_path):
    world, trace, ctx, clip = _adopt_once(
        monkeypatch, tmp_path, request_id="r44f-hook-ok"
    )
    try:
        end = trace.payloads("clip_fast_load_end")[0]
        assert end["ok"] is True
        assert end["owner_release_hook_installed"] is True
        assert end["owner_release_point"] == "on_detach_after"
        # Provenance mirrors the release point on the published object.
        provenance = getattr(clip, "_comfymodal_r44b_request_fastsafe")
        assert provenance["owner_release_hook_installed"] is True
        assert provenance["owner_release_point"] == "on_detach_after"

        patcher = clip.patcher
        # Idempotency latch + exactly ONE ON_DETACH callback registered.
        assert getattr(patcher, rcfs._OWNER_RELEASE_HOOK_ATTR) is True
        callbacks = patcher.callbacks.get("on_detach_after", [])
        assert len(callbacks) == 1 and callable(callbacks[0])
        # Owners retained until detach: nothing closed at adoption time.
        loader, fb = world.owners_created[0]
        assert loader.closed is False and fb.closed is False
    finally:
        rfp.teardown(ctx)
        rcfs.uninstall_for_tests()


def test_partial_detach_leaves_owners_open(adopt_env, monkeypatch, tmp_path):
    world, _trace, ctx, clip = _adopt_once(
        monkeypatch, tmp_path, request_id="r44f-detach-false"
    )
    try:
        loader, fb = world.owners_created[0]
        # unpatch_all=False (partial detach / offload): callback must return
        # WITHOUT releasing — buffers still back live parameters.
        clip.patcher.detach(unpatch_all=False)
        assert loader.closed is False and fb.closed is False
        owners = getattr(clip.patcher, "_r44f_test_owners", None)
        assert isinstance(owners, list) and len(owners) == 1
    finally:
        rfp.teardown(ctx)
        rcfs.uninstall_for_tests()


def test_full_detach_releases_exactly_once_and_cleans_owner(
    adopt_env, monkeypatch, tmp_path
):
    world, _trace, ctx, clip = _adopt_once(
        monkeypatch, tmp_path, request_id="r44f-detach-true"
    )
    try:
        loader, fb = world.owners_created[0]
        close_calls: list[int] = []
        original_close = loader.close

        def counting_close():
            close_calls.append(1)
            original_close()

        loader.close = counting_close  # type: ignore[method-assign]

        clip.patcher.detach(unpatch_all=True)
        # Exactly one release; both owner components closed.
        assert len(close_calls) == 1
        assert loader.closed is True and fb.closed is True
        # Owner attribute removed from the patcher (clean lifecycle).
        assert getattr(clip.patcher, "_r44f_test_owners", None) is None
    finally:
        rfp.teardown(ctx)
        rcfs.uninstall_for_tests()


def test_repeated_detach_is_idempotent(adopt_env, monkeypatch, tmp_path):
    world, _trace, ctx, clip = _adopt_once(
        monkeypatch, tmp_path, request_id="r44f-detach-repeat"
    )
    try:
        loader, fb = world.owners_created[0]
        close_calls: list[int] = []
        original_close = fb.close

        def counting_close():
            close_calls.append(1)
            original_close()

        fb.close = counting_close  # type: ignore[method-assign]

        clip.patcher.detach(unpatch_all=True)
        clip.patcher.detach(unpatch_all=True)  # second full detach: no-op
        clip.patcher.detach(unpatch_all=False)  # partial after full: no-op
        assert len(close_calls) == 1
        assert loader.closed is True and fb.closed is True
        assert getattr(clip.patcher, "_r44f_test_owners", None) is None
    finally:
        rfp.teardown(ctx)
        rcfs.uninstall_for_tests()


def test_hook_install_failure_fails_closed_without_publication(
    adopt_env, monkeypatch, tmp_path
):
    world = _install_world(monkeypatch, tmp_path)
    world.break_owner_release_hook = True
    assert rcfs.install_request_clip_fastsafe() is True
    try:
        ctx = rfp.begin(request_id="r44f-hook-broken")
        try:
            result = _nodes()["CLIPLoader"]().load_clip(clip_name="clip.safetensors")
            # Transport DID happen, then the hook gap failed the adoption.
            assert len(world.fs_calls) == 1
            loader, fb = world.owners_created[0]
            assert loader.closed is True and fb.closed is True
            # Nothing published; canonical native fallback observed.
            assert ctx.result("clip") is None
            assert isinstance(result, tuple) and result[0] is not None
            assert any(
                "clip_fastsafe_failed:RuntimeError" in reason
                for reason in ctx.terminal_reasons()
            )
            role, arm, kw = world.observed[0]
            assert (role, arm) == ("clip", "native_comfy")
            assert kw.get("fallback_attempted") is True
        finally:
            rfp.teardown(ctx)
    finally:
        rcfs.uninstall_for_tests()
