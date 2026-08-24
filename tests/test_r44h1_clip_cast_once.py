"""R44H1: CAST-ONCE CLIP adoption (BF16 checkpoint -> FP16 expectation).

Coverage (all local, CPU-only, no Modal/network/CUDA required):

* Provenance          — ``request_clip_fastsafe._expected_te_dtype_str``
* Gate classification — BF16+FP16 classifies ``cast_once_fp16`` (NOT
                        rejected like the old ``dtype_parity_mismatch``);
                        unsupported pairs fail closed at the gate
* Cast-once producer  — end-to-end through the scoped seams: skeleton built
                        on the (simulated) load device, Comfy's own
                        ``load_state_dict(assign=False)`` performs EXACTLY
                        ONE BF16->FP16 conversion into FINAL live storage,
                        values proven bit-exact, staging retired EARLY
                        (non-destructive ``retire_source_owners``, never
                        close/purge on the hot path), residency stays
                        bookkeeping-only
* Accounting buckets  — blob / transformed / comparable classification via
                        ``_validate_cast_once_bind`` (direct unit call)
* Fail-closed         — missing key and value mismatch fall back to the
                        native lane with sticky truth and closed owners
* Owner lifetime      — after early retirement nothing is left to close;
                        the ``ON_DETACH`` hook no-ops (no double release)
* Flag-off neutrality — the legacy producer is labeled ``copy_cuda_legacy``

The harness mirrors tests/test_r44f_clip_zero_copy.py (fake modules + REAL
torch tensors) with three R44H1-specific differences: the fake TE module is
FLAT so staged checkpoint keys equal final state_dict keys (the cast-once
validator is name-keyed), the skeleton dtype/device are configurable, and
the CUDA load device is simulated as ``cpu`` so no real GPU is needed.
"""
from __future__ import annotations

import sys
import types
from typing import Any

import pytest

torch = pytest.importorskip("torch")

from comfymodal_runtime import request_clip_fastsafe as rcfs
from comfymodal_runtime import request_fastpath as rfp

# Inner-module state-dict names (the fake TE is FLAT: staged key ==
# state_dict key, which is what the name-keyed cast-once validator needs).
TENSOR_KEYS = ("weight", "bias", "logit_scale")
SHAPES = {"weight": (4, 3), "bias": (3,), "logit_scale": ()}
BLOB_KEY = "spiece_model"

#: Distinct values exactly representable in bf16 AND fp16 (bit-exact proof).
STAGED_VALUES = {"weight": 1.5, "bias": 0.25, "logit_scale": 0.125}

_ST_TO_SAFETENSORS = {
    torch.float64: "F64",
    torch.float32: "F32",
    torch.float16: "F16",
    torch.bfloat16: "BF16",
}


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
    """Mirrors the real loader ownership surface: destructive ``close``
    (discard path) plus the NON-destructive ``release_storage`` API that
    ``retire_source_owners`` prefers on the hot path."""

    def __init__(self) -> None:
        self.closed = False
        self.release_calls = 0
        self.purge_requests: list[bool] = []

    def close(self) -> None:
        self.closed = True

    def release_storage(self, *, purge_allocator: bool = False) -> None:
        self.purge_requests.append(bool(purge_allocator))
        self.release_calls += 1


class FakeFB:
    def __init__(self) -> None:
        self.closed = False
        self.release_calls = 0
        self.purge_requests: list[bool] = []

    def close(self) -> None:
        self.closed = True

    def release_storage(self, *, purge_allocator: bool = False) -> None:
        self.purge_requests.append(bool(purge_allocator))
        self.release_calls += 1


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
    """Real torch semantics + stubbed CUDA allocator counters."""
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
    """Restore ``comfymodal_runtime.<sub>`` package attributes after each test."""
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
        #: text_encoder_initial_device (the seamed skeleton device inside
        #: the window, ``initial_device_return`` when unseamed).
        self.construction_initial_devices: list[Any] = []
        self.tensors_by_path: dict[str, dict] = {}
        #: when set, the served sd is missing one weight key (fail-closed
        #: harness); the fake constructor still builds the FULL skeleton.
        self.drop_key: str | None = None
        self.resolved = ""
        #: when True, the fake patcher's ``add_callback`` raises.
        self.break_owner_release_hook = False
        # --- R44H1 knobs -----------------------------------------------------
        #: expected runtime TE dtype name (drives the fake
        #: model_management.text_encoder_dtype).
        self.expected_dtype: str = "torch.float32"
        #: dtype used for the tiny Transformer/TinyTE skeleton parameters.
        self.skeleton_dtype: torch.dtype = torch.float32
        #: what the (unseamed) fake text_encoder_initial_device returns.
        self.initial_device_return: Any = torch.device("cpu")
        #: dtype of the STAGED FastSafe tensors (the physical read).
        self.staged_dtype: torch.dtype = torch.float32
        #: when True the fake constructor fills params with WRONG values
        #: after load (value_mismatch fail-closed harness).
        self.corrupt_values: bool = False
        #: when set to a key name, the fake constructor binds THAT key by
        #: assigning the STAGED tensor object directly (aliasing harness).
        self.alias_key: str | None = None
        #: when True, the fake loader_selection.record_observed raises
        #: (publication-order harness).
        self.fail_record_observed: bool = False
        #: when True, the fake retire_source_owners fails closed WITHOUT
        #: releasing/closing anything (R44H3 retirement-failure harness).
        self.fail_source_retirement: bool = False
        #: when True, the fake constructor registers its patcher the way
        #: pinned comfy sd.py:280-281 does (load_models_gpu force_full_load).
        self.register_patcher_on_build: bool = False
        #: every CLIP object the fake constructor built (failed or not).
        self.built_clips: list[Any] = []
        # Originals captured BEFORE any seam runs (restoration assertions).
        self.orig_ltf: Any = None
        self.orig_load_sd: Any = None
        self.orig_initial_device: Any = None
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
        name = str(world.expected_dtype).split(".", 1)[-1]
        return getattr(torch, name, torch.float32)

    def text_encoder_initial_device(load_device, offload_device, model_size=0):
        return world.initial_device_return

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
    cfh_mod.OWNER_ATTR = "_r44h1_test_owners"
    cfh_mod._TOKENIZER_BLOB_KEYS = (BLOB_KEY,)

    def owner_attach(clip, loader, fb):
        world.owner_calls.append((loader, fb))
        owners = getattr(clip.patcher, cfh_mod.OWNER_ATTR, None)
        if owners is None:
            owners = []
            setattr(clip.patcher, cfh_mod.OWNER_ATTR, owners)
        # Mirror the real _FastsafeOwner wrapper shape (.loader/.fb attrs) so
        # retire_source_owners' component-id filter can match attachments.
        owners.append(types.SimpleNamespace(loader=loader, fb=fb))

    cfh_mod.owner_attach = owner_attach

    def release_owner(clip):
        """Destructive discard-path mirror (close + attribute removal)."""
        patcher = getattr(clip, "patcher", None)
        if patcher is None:
            return False
        owners = getattr(patcher, cfh_mod.OWNER_ATTR, None)
        if not owners:
            return False
        for owner in owners:
            components = (
                (getattr(owner, "loader", None), getattr(owner, "fb", None))
                if hasattr(owner, "loader") or hasattr(owner, "fb")
                else tuple(owner)
            )
            for component in components:
                if component is None:
                    continue
                close = getattr(component, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception:
                        pass
        delattr(patcher, cfh_mod.OWNER_ATTR)
        return True

    cfh_mod.release_owner = release_owner

    def retire_source_owners(owners, *, bf16_bytes=0, fp32_bytes=0, clip=None):
        """Mirror of the REAL helper (clip_fast_hydration.py): prefer the
        non-destructive ``release_storage(purge_allocator=False)`` API, fail
        closed on partial retirement, clear the caller's list and the
        patcher OWNER_ATTR on full success, NEVER close/purge here."""
        before = len(owners)
        if world.fail_source_retirement:
            # R44H3 harness: fail closed WITHOUT touching the owners — they
            # stay attached and nothing is released or closed (the real
            # helper's documented failure contract).
            return {
                "ok": False,
                "owner_count_before": int(before),
                "owner_count_after": int(before),
                "owner_bytes_before": int(max(0, bf16_bytes)),
                "owners_retired": 0,
                "owners_failed": int(before),
                "per_owner": [],
                "error": "release_storage_injected_failure",
            }
        retired = 0
        seen: set[int] = set()
        source_component_ids = {
            id(item)
            for owner in owners
            for item in (
                tuple(owner) if isinstance(owner, (tuple, list)) else (owner,)
            )
            if item is not None
        }
        statuses: list[dict[str, Any]] = []
        for index, owner in enumerate(list(owners)):
            components = (
                tuple(owner) if isinstance(owner, (tuple, list)) else (owner,)
            )
            component_status: list[dict[str, Any]] = []
            for item in components:
                if item is None or id(item) in seen:
                    continue
                seen.add(id(item))
                method = getattr(item, "release_storage", None)
                method_name = "release_storage"
                if not callable(method):
                    for name in ("free_storage", "release_buffer", "release"):
                        candidate = getattr(item, name, None)
                        if callable(candidate):
                            method, method_name = candidate, name
                            break
                status: dict[str, Any] = {
                    "method": method_name if callable(method) else None,
                    "released": False,
                    "error": "" if callable(method) else "no_release_api",
                }
                if callable(method):
                    try:
                        method(purge_allocator=False)
                        status["released"] = True
                    except TypeError:
                        status["error"] = "release_api_requires_explicit_no_purge"
                    except Exception as exc:
                        status["error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
                component_status.append(status)
            owner_retired = bool(component_status) and all(
                bool(item.get("released")) for item in component_status
            )
            if owner_retired:
                retired += 1
            statuses.append(
                {
                    "owner_index": index,
                    "status": "retired" if owner_retired else "not_retired",
                    "released": owner_retired,
                }
            )
        all_retired = before > 0 and retired == before
        if all_retired:
            owners.clear()
            if clip is not None:
                patcher = getattr(clip, "patcher", None)
                attached = (
                    getattr(patcher, cfh_mod.OWNER_ATTR, None)
                    if patcher is not None
                    else None
                )
                if isinstance(attached, list):
                    attached[:] = [
                        item
                        for item in attached
                        if id(item) not in source_component_ids
                        and id(getattr(item, "loader", None))
                        not in source_component_ids
                        and id(getattr(item, "fb", None)) not in source_component_ids
                    ]
                    try:
                        if not attached:
                            delattr(patcher, cfh_mod.OWNER_ATTR)
                    except Exception:
                        pass
        return {
            "ok": all_retired,
            "owner_count_before": int(before),
            "owner_count_after": int(before - retired),
            "owner_bytes_before": int(max(0, bf16_bytes)),
            "owners_retired": int(retired),
            "owners_failed": int(before - retired),
            "per_owner": statuses,
        }

    cfh_mod.retire_source_owners = retire_source_owners
    cfh_mod.mark_clip_hydrated = lambda clip: world.hydrated.append(clip)
    monkeypatch.setitem(sys.modules, "comfymodal_runtime.clip_fast_hydration", cfh_mod)

    wiring_mod = types.ModuleType("comfymodal_runtime.clip_fast_hydration_wiring")

    def _fastsafe_load(path, metrics=None):
        world.fs_calls.append(str(path))
        tensors = {
            key: torch.full(
                SHAPES.get(key, (2,)),
                STAGED_VALUES.get(key, 0.0),
                dtype=world.staged_dtype,
            )
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

    def _record_observed(role, arm, **kw):
        if world.fail_record_observed:
            raise RuntimeError("record_observed_injected_failure")
        world.observed.append((role, arm, dict(kw)))

    ls_mod.record_observed = _record_observed
    ls_mod.normalize_observed = lambda role, arm: (
        "native_comfy" if arm == "native" else arm
    )
    monkeypatch.setitem(sys.modules, "comfymodal_runtime.loader_selection", ls_mod)

    # -- nodes with a NATIVE-construction fake CLIPLoader ---------------------
    nodes_mod = types.ModuleType("nodes")

    def build_fake_clip():
        """Mimic comfy.sd.load_clip over the GUARDED load_torch_file: serve
        the resident tensors, resolve the initial device (the skeleton seam),
        build the skeleton there, route the weight load through
        comfy.sd.CLIP.load_sd (assign shadow OR plain copy under test)."""
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

        class TinyTE(torch.nn.Module):
            """FLAT text encoder: staged checkpoint keys == state_dict keys."""

            def __init__(self):
                super().__init__()
                self.weight = torch.nn.Parameter(
                    torch.empty(
                        SHAPES["weight"],
                        dtype=world.skeleton_dtype,
                        device=initial_device,
                    )
                )
                self.bias = torch.nn.Parameter(
                    torch.empty(
                        SHAPES["bias"],
                        dtype=world.skeleton_dtype,
                        device=initial_device,
                    )
                )
                self.logit_scale = torch.nn.Parameter(
                    torch.empty(
                        (), dtype=world.skeleton_dtype, device=initial_device
                    )
                )

            def load_sd(self, sd):
                return self.load_state_dict(
                    sd, strict=False, assign=getattr(self, "can_assign_sd", False)
                )

        class FakePatcher:
            """ModelPatcher mirror for the callback/detach contract."""

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
        world.built_clips.append(clip)
        comfy.sd.CLIP.load_sd(clip, payload)
        if world.register_patcher_on_build:
            # Pinned comfy sd.py:280-281 parity: CLIP.__init__ itself
            # registers the patcher when skeleton device == load_device.
            comfy_mm.load_models_gpu([clip.patcher], force_full_load=True)
        if world.alias_key:
            # Aliasing harness: bind ONE key by assigning the STAGED tensor
            # object directly (shared storage) instead of copying.
            staged_t = payload.get(world.alias_key)
            if isinstance(staged_t, torch.Tensor):
                setattr(
                    clip.cond_stage_model,
                    world.alias_key,
                    torch.nn.Parameter(staged_t),
                )
        if world.corrupt_values:
            with torch.no_grad():
                clip.cond_stage_model.weight.fill_(999.0)
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

    # -- descriptor stub (dtypes derived from the STAGED dtype) ---------------
    st_name = _ST_TO_SAFETENSORS.get(world.staged_dtype, "F32")
    world.descriptor = FakeDescriptor(
        keys=TENSOR_KEYS + (BLOB_KEY,),
        dtypes={**{k: st_name for k in TENSOR_KEYS}, BLOB_KEY: "U8"},
        shapes={**SHAPES, BLOB_KEY: (8,)},
    )
    monkeypatch.setattr(rfp, "build_descriptor", lambda *a, **k: world.descriptor)

    # -- R44H1 test-lane device simulation ------------------------------------
    # The cast-once skeleton is built on the LOAD device; simulate it as CPU
    # so the whole lane runs without a real GPU (the validator accepts any
    # device when target_device_str == "cpu").
    monkeypatch.setattr(rcfs, "_current_cuda_device_str", lambda: "cpu")
    return world


def _nodes():
    import nodes as nodes_module

    return nodes_module.NODE_CLASS_MAPPINGS


def _comfy_mods():
    """Resolve the (fake) comfy modules CURRENTLY registered in sys.modules."""
    return (
        sys.modules["comfy.utils"],
        sys.modules["comfy.sd"],
        sys.modules["comfy.model_management"],
    )


def _cast_world() -> World:
    """World configured for the cast-once lane: BF16 staging, FP16
    expectation, FP16 skeleton on the (simulated) load device.

    ``initial_device_return`` is ``meta``: the UNSEAMED device resolver
    answer.  A passing run therefore PROVES the device seam engaged — the
    skeleton must have been built on the seamed load device (cpu) instead."""
    world = World()
    world.expected_dtype = "torch.float16"
    world.staged_dtype = torch.bfloat16
    world.skeleton_dtype = torch.float16
    world.initial_device_return = torch.device("meta")
    return world


def _cast_world_bf16() -> World:
    """Cast-once lane for the symmetric F16 -> BF16 pair: FP16 staging,
    BF16 expectation, BF16 skeleton on the (simulated) load device."""
    world = World()
    world.expected_dtype = "torch.bfloat16"
    world.staged_dtype = torch.float16
    world.skeleton_dtype = torch.bfloat16
    world.initial_device_return = torch.device("meta")
    return world


# ---------------------------------------------------------------------------
# C1: expected TE dtype provenance
# ---------------------------------------------------------------------------


def test_expected_te_dtype_provenance(adopt_env, monkeypatch, tmp_path):
    world = _install_world(monkeypatch, tmp_path)
    world.expected_dtype = "torch.float16"
    assert rcfs._expected_te_dtype_str() == "torch.float16"


# ---------------------------------------------------------------------------
# C2: gate classification (independent mirror of the r44f pair)
# ---------------------------------------------------------------------------


def test_gate_bf16_classifies_cast_once_not_rejected(adopt_env, monkeypatch, tmp_path):
    world = _install_world(monkeypatch, tmp_path)
    world.expected_dtype = "torch.float16"
    desc = FakeDescriptor(dtypes={k: "BF16" for k in TENSOR_KEYS})
    ok, reason, details = rcfs._native_adoption_gates(
        ("clip_name",), (), {}, [desc]
    )
    assert ok is True
    assert reason == "ok"
    assert details["adoption_mode"] == "cast_once_fp16"
    assert details["checkpoint_dtype"] == "BF16"


# ---------------------------------------------------------------------------
# C3: cast-once producer end-to-end
# ---------------------------------------------------------------------------


def test_cast_once_producer_end_to_end(adopt_env, monkeypatch, tmp_path):
    world = _install_world(monkeypatch, tmp_path, world=_cast_world())
    assert rcfs.install_request_clip_fastsafe() is True
    try:
        trace = FakeTrace()
        ctx = rfp.begin(request_id="r44h1-e2e", trace=trace)
        try:
            result = _nodes()["CLIPLoader"]().load_clip(clip_name="clip.safetensors")
            clip = result[0]
            csm = clip.cond_stage_model
            served = world.tensors_by_path[world.resolved]

            # Single physical read; the native reader NEVER ran.
            assert world.fs_calls == [world.resolved]
            assert world.ltf_calls == []

            # EXACTLY ONE conversion: live params are FP16, values bitwise
            # equal to the staged BF16 cast to FP16.
            assert csm.weight.dtype == torch.float16
            assert csm.bias.dtype == torch.float16
            assert csm.logit_scale.dtype == torch.float16
            assert bool(torch.equal(csm.weight, served["weight"].to(torch.float16)))
            assert bool(torch.equal(csm.bias, served["bias"].to(torch.float16)))
            assert bool(
                torch.equal(csm.logit_scale, served["logit_scale"].to(torch.float16))
            )
            # NOT pointer-same-storage (honest nomenclature).
            assert csm.weight.data_ptr() != served["weight"].data_ptr()

            # Provenance + telemetry: cast-once labeling everywhere.
            start = trace.payloads("clip_fast_load_start")[0]
            assert start["adoption_mode"] == "cast_once_fp16"
            assert start["checkpoint_dtype"] == "BF16"
            assert start["expected_runtime_dtype"] == "torch.float16"
            end = trace.payloads("clip_fast_load_end")[0]
            assert end["ok"] is True
            assert end["bind_mode"] == "cast_once_fp16"
            assert end["adoption_mode"] == "cast_once_fp16"
            assert end["cast_once_count"] == len(TENSOR_KEYS)
            assert end["same_storage_count"] == 0
            assert end["legacy_copy_count"] == 0
            assert end["final_live_weight_bytes"] > 0
            assert end["duplicate_weight_bytes_before_forward"] == 0
            assert end["owner_retained"] is False
            assert end["owner_release_point"] == "after_cast_validation"
            assert end["owner_release_method"] == "retire_source_owners"
            assert end["owners_retired"] == 1
            assert end["owners_failed"] == 0
            provenance = getattr(clip, "_comfymodal_r44b_request_fastsafe")
            assert provenance["bind_mode"] == "cast_once_fp16"
            assert provenance["adoption_mode"] == "cast_once_fp16"

            # EARLY STAGING RELEASE: retired non-destructively BEFORE forward
            # (release_storage, purge_allocator=False; close NEVER ran).
            loader, fb = world.owners_created[0]
            assert loader.release_calls == 1 and fb.release_calls == 1
            assert loader.purge_requests == [False] and fb.purge_requests == [False]
            assert loader.closed is False and fb.closed is False
            assert getattr(clip.patcher, "_r44h1_test_owners", None) is None

            # Truth: canonical arm observed WITHOUT fallback; result published.
            assert world.observed == [("clip", "fastsafetensors_direct_gpu", {})]
            assert ctx.result("clip") is clip

            # T5 DEVICE SEAM PROOF: the fake construction saw the SEAMED
            # skeleton device (the simulated load device, cpu), NOT the
            # unseamed resolver answer (meta) — the seam engaged.
            assert world.construction_initial_devices[-1] == torch.device("cpu")
            assert world.initial_device_return == torch.device("meta")

            # Residency stayed bookkeeping-only (stubbed counters flat).
            residency = trace.payloads("clip_fastsafe_residency_register")[0]
            assert residency["registered"] is True
            assert residency["force_full_load"] is True
            assert residency["model_sized_movement_detected"] is False

            # Seams fully restored.
            comfy_utils, comfy_sd, comfy_mm = _comfy_mods()
            assert comfy_utils.load_torch_file is world.orig_ltf
            assert comfy_sd.CLIP.load_sd is world.orig_load_sd
            probe = comfy_mm.text_encoder_initial_device(
                torch.device("cuda:0"), torch.device("cpu")
            )
            assert probe == world.initial_device_return
        finally:
            rfp.teardown(ctx)
    finally:
        rcfs.uninstall_for_tests()


# ---------------------------------------------------------------------------
# C4: full accounting buckets (direct validator call)
# ---------------------------------------------------------------------------


def test_full_state_accounting_buckets():
    served = {
        "weight": torch.full((4, 3), 1.5, dtype=torch.bfloat16),
        "bias": torch.full((3,), 0.25, dtype=torch.bfloat16),
        "logit_scale": torch.full((), 0.125, dtype=torch.bfloat16),
        "transformed": torch.zeros(2, 2, dtype=torch.bfloat16),
        BLOB_KEY: torch.zeros(8, dtype=torch.uint8),
    }

    class Desc:
        keys = tuple(served.keys())
        shapes = {
            "weight": (4, 3),
            "bias": (3,),
            "logit_scale": (),
            "transformed": (5, 5),  # header MISMATCHES the staged (2, 2)
            BLOB_KEY: (8,),
        }
        dtypes = {
            "weight": "BF16",
            "bias": "BF16",
            "logit_scale": "BF16",
            "transformed": "BF16",
            BLOB_KEY: "U8",
        }
        metadata = {}

    class Tiny(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.weight = torch.nn.Parameter(
                torch.full((4, 3), 1.5, dtype=torch.float16)
            )
            self.bias = torch.nn.Parameter(torch.full((3,), 0.25, dtype=torch.float16))
            self.logit_scale = torch.nn.Parameter(
                torch.full((), 0.125, dtype=torch.float16)
            )
            # ctor-initialized buffer with NO staged source (rope inv_freq
            # pattern): tolerated, counted — never fatal.
            self.register_buffer("inv_freq", torch.zeros(4, dtype=torch.float16))

    clip = types.SimpleNamespace(
        cond_stage_model=Tiny(), patcher=object(), tokenizer=object()
    )
    accounting = rcfs._validate_cast_once_bind(
        clip, [served], [Desc()], "torch.float16", "cpu"
    )
    assert accounting["checkpoint_tensor_count"] == 5
    # transformed: reported, not fatal (native load handled it).
    assert accounting["transformed_count"] == 1
    assert accounting["transformed_keys_sample"] == ["transformed"]
    # blob: explicit exception bucket.
    assert accounting["exception_count"] == 1
    assert accounting["exception_keys_sample"] == [BLOB_KEY]
    # the three normal keys cast-once bound.
    assert accounting["cast_once_count"] == 3
    assert accounting["same_storage_count"] == 0
    assert accounting["legacy_copy_count"] == 0
    assert accounting["comparable_live_parameter_mapping_count"] == 3
    assert accounting["buffer_extra_count"] == 1
    assert accounting["extra_model_tensor_count"] == 1
    assert accounting["live_parameter_dtype"] == "torch.float16"
    assert accounting["final_live_weight_bytes"] > 0
    total = sum(t.numel() * t.element_size() for t in served.values())
    assert accounting["source_bytes_total"] == total


# ---------------------------------------------------------------------------
# C5/C6: fail-closed — missing key / value mismatch
# ---------------------------------------------------------------------------


def test_missing_key_fail_closed(adopt_env, monkeypatch, tmp_path):
    world = _install_world(monkeypatch, tmp_path, world=_cast_world())
    world.drop_key = "bias"  # skeleton keeps a random-init leftover for it
    assert rcfs.install_request_clip_fastsafe() is True
    try:
        ctx = rfp.begin(request_id="r44h1-missing")
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
            # Nothing published; the request survived through the original
            # (unguarded native read outside the seams).
            assert ctx.result("clip") is None
            assert isinstance(result, tuple) and len(result) == 1
            assert len(world.ltf_calls) == 1
            # Seams restored even on the failure path.
            _, _, comfy_mm = _comfy_mods()
            assert comfy_mm.text_encoder_initial_device is world.orig_initial_device
        finally:
            rfp.teardown(ctx)
    finally:
        rcfs.uninstall_for_tests()


def test_value_mismatch_fail_closed(adopt_env, monkeypatch, tmp_path):
    world = _install_world(monkeypatch, tmp_path, world=_cast_world())
    world.corrupt_values = True  # wrong values AFTER the single cast
    assert rcfs.install_request_clip_fastsafe() is True
    try:
        ctx = rfp.begin(request_id="r44h1-corrupt")
        try:
            result = _nodes()["CLIPLoader"]().load_clip(clip_name="clip.safetensors")

            assert len(world.fs_calls) == 1
            loader, fb = world.owners_created[0]
            assert loader.closed is True and fb.closed is True
            assert len(world.observed) == 1
            role, arm, kw = world.observed[0]
            assert (role, arm) == ("clip", "native_comfy")
            assert kw.get("fallback_attempted") is True
            assert any(
                "clip_fastsafe_failed:RuntimeError" in reason
                for reason in ctx.terminal_reasons()
            )
            assert ctx.result("clip") is None
            assert isinstance(result, tuple) and len(result) == 1
        finally:
            rfp.teardown(ctx)
    finally:
        rcfs.uninstall_for_tests()


# ---------------------------------------------------------------------------
# C7: owner lifetime after early retirement
# ---------------------------------------------------------------------------


def test_owner_lifetime_early_release(adopt_env, monkeypatch, tmp_path):
    world = _install_world(monkeypatch, tmp_path, world=_cast_world())
    assert rcfs.install_request_clip_fastsafe() is True
    try:
        ctx = rfp.begin(request_id="r44h1-owner")
        try:
            clip = _nodes()["CLIPLoader"]().load_clip(clip_name="clip.safetensors")[0]
            patcher = clip.patcher
            # Early retirement already removed the owner attribute.
            assert getattr(patcher, "_r44h1_test_owners", None) is None
            loader, fb = world.owners_created[0]

            close_calls: list[int] = []
            original_close = loader.close

            def counting_close():
                close_calls.append(1)
                original_close()

            loader.close = counting_close  # type: ignore[method-assign]

            # Full detach invokes the ON_DETACH safety net: it must NOT raise
            # and must NOT double-release anything.
            patcher.detach(unpatch_all=True)
            assert len(close_calls) == 0
            assert loader.closed is False and fb.closed is False
            assert loader.release_calls == 1 and fb.release_calls == 1
        finally:
            rfp.teardown(ctx)
    finally:
        rcfs.uninstall_for_tests()


# ---------------------------------------------------------------------------
# C8: unsupported dtype pair fails closed AT THE GATE
# ---------------------------------------------------------------------------


def test_unsupported_pair_fail_closed_at_gate(adopt_env, monkeypatch, tmp_path):
    world = _install_world(monkeypatch, tmp_path, world=_cast_world())
    world.staged_dtype = torch.float64  # F64 staged vs FP16 expectation
    st_name = _ST_TO_SAFETENSORS[torch.float64]
    world.descriptor = FakeDescriptor(
        keys=TENSOR_KEYS + (BLOB_KEY,),
        dtypes={**{k: st_name for k in TENSOR_KEYS}, BLOB_KEY: "U8"},
        shapes={**SHAPES, BLOB_KEY: (8,)},
    )
    assert rcfs.install_request_clip_fastsafe() is True
    try:
        trace = FakeTrace()
        ctx = rfp.begin(request_id="r44h1-f64", trace=trace)
        try:
            result = _nodes()["CLIPLoader"]().load_clip(clip_name="clip.safetensors")
            skip = trace.payloads("clip_fastsafe_skip")[0]
            assert skip["reason"] == "native_adoption_ineligible"
            assert skip["detail"].startswith("unsupported_dtype_pair")
            # Claim released, no transport, original produced natively.
            assert ctx.summary()["claims"]["clip"] is False
            assert world.fs_calls == []
            assert result[0] is not None
        finally:
            rfp.teardown(ctx)
    finally:
        rcfs.uninstall_for_tests()


# ---------------------------------------------------------------------------
# C9: flag OFF keeps the legacy producer, labeled copy_cuda_legacy
# ---------------------------------------------------------------------------


def test_flag_off_copy_cuda_legacy_neutrality(fastsafe_env, monkeypatch, tmp_path):
    world = _install_world(monkeypatch, tmp_path)
    assert rcfs.install_request_clip_fastsafe() is True
    try:
        trace = FakeTrace()
        ctx = rfp.begin(request_id="r44h1-off", trace=trace)
        try:
            result = _nodes()["CLIPLoader"]().load_clip(clip_name="clip.safetensors")
            start = trace.payloads("clip_fast_load_start")[0]
            end = trace.payloads("clip_fast_load_end")[0]
            assert start["adoption_mode"] == "copy_cuda_legacy"
            assert end["adoption_mode"] == "copy_cuda_legacy"
            assert end["bind_mode"] in {"copy_cuda", "same_storage"}
            # Otherwise identical to the proven legacy expectations.
            assert world.fs_calls == [world.resolved]
            assert world.ltf_calls == []
            assert world.mm_load_calls == []
            assert world.observed == [("clip", "fastsafetensors_direct_gpu", {})]
            assert result[0] is not None
        finally:
            rfp.teardown(ctx)
    finally:
        rcfs.uninstall_for_tests()


# ---------------------------------------------------------------------------
# C10: residency registration is bookkeeping-only
# ---------------------------------------------------------------------------


def test_residency_bookkeeping_no_movement(adopt_env, monkeypatch, tmp_path):
    world = _install_world(monkeypatch, tmp_path, world=_cast_world())
    assert rcfs.install_request_clip_fastsafe() is True
    try:
        trace = FakeTrace()
        ctx = rfp.begin(request_id="r44h1-residency", trace=trace)
        try:
            _nodes()["CLIPLoader"]().load_clip(clip_name="clip.safetensors")
            # load_models_gpu ran with force_full_load=True ...
            assert len(world.mm_load_calls) == 1
            models_arg, force_full = world.mm_load_calls[0]
            assert force_full is True
            assert len(models_arg) == 1
            # ... and the stubbed allocator counters stayed FLAT, so the
            # movement detector must report False against the event payload.
            residency = trace.payloads("clip_fastsafe_residency_register")[0]
            assert residency["force_full_load"] is True
            assert residency["allocated_before_bytes"] == 4096
            assert residency["allocated_after_bytes"] == 4096
            assert residency["model_sized_movement_detected"] is False
        finally:
            rfp.teardown(ctx)
    finally:
        rcfs.uninstall_for_tests()


# ---------------------------------------------------------------------------
# C11 (T1): gated cast_once_bf16 pair — gate + end-to-end, dtype-honest bind
# ---------------------------------------------------------------------------


def test_gate_f16_bf16_classifies_cast_once_bf16(adopt_env, monkeypatch, tmp_path):
    world = _install_world(monkeypatch, tmp_path)
    world.expected_dtype = "torch.bfloat16"
    desc = FakeDescriptor(dtypes={k: "F16" for k in TENSOR_KEYS})
    ok, reason, details = rcfs._native_adoption_gates(
        ("clip_name",), (), {}, [desc]
    )
    assert ok is True
    assert reason == "ok"
    assert details["adoption_mode"] == "cast_once_bf16"
    assert details["checkpoint_dtype"] == "F16"


def test_cast_once_bf16_end_to_end(adopt_env, monkeypatch, tmp_path):
    world = _install_world(monkeypatch, tmp_path, world=_cast_world_bf16())
    assert rcfs.install_request_clip_fastsafe() is True
    try:
        trace = FakeTrace()
        ctx = rfp.begin(request_id="r44h1-bf16", trace=trace)
        try:
            result = _nodes()["CLIPLoader"]().load_clip(clip_name="clip.safetensors")
            clip = result[0]
            csm = clip.cond_stage_model
            served = world.tensors_by_path[world.resolved]

            # Single physical read; the native reader NEVER ran.
            assert world.fs_calls == [world.resolved]
            assert world.ltf_calls == []

            # EXACTLY ONE conversion: live params are BF16, values bitwise
            # equal to the staged F16 cast to BF16.
            assert csm.weight.dtype == torch.bfloat16
            assert csm.bias.dtype == torch.bfloat16
            assert csm.logit_scale.dtype == torch.bfloat16
            assert bool(torch.equal(csm.weight, served["weight"].to(torch.bfloat16)))
            assert bool(torch.equal(csm.bias, served["bias"].to(torch.bfloat16)))
            assert bool(
                torch.equal(csm.logit_scale, served["logit_scale"].to(torch.bfloat16))
            )
            # NOT pointer-same-storage.
            assert csm.weight.data_ptr() != served["weight"].data_ptr()

            # Provenance + telemetry: dtype-honest cast-once labeling.
            start = trace.payloads("clip_fast_load_start")[0]
            assert start["adoption_mode"] == "cast_once_bf16"
            assert start["checkpoint_dtype"] == "F16"
            assert start["expected_runtime_dtype"] == "torch.bfloat16"
            end = trace.payloads("clip_fast_load_end")[0]
            assert end["ok"] is True
            # FIX 1: bind_mode carries the ACTUAL mode name, not a generic
            # cast_once_fp16 label.
            assert end["bind_mode"] == "cast_once_bf16"
            assert end["adoption_mode"] == "cast_once_bf16"
            provenance = getattr(clip, "_comfymodal_r44b_request_fastsafe")
            assert provenance["bind_mode"] == "cast_once_bf16"
            assert provenance["adoption_mode"] == "cast_once_bf16"

            # EARLY STAGING RELEASE happened (retire mirror ran; nothing closed).
            loader, fb = world.owners_created[0]
            assert loader.release_calls == 1 and fb.release_calls == 1
            assert loader.purge_requests == [False] and fb.purge_requests == [False]
            assert loader.closed is False and fb.closed is False
            assert getattr(clip.patcher, "_r44h1_test_owners", None) is None

            # Truth: canonical arm observed WITHOUT fallback; result published.
            assert world.observed == [("clip", "fastsafetensors_direct_gpu", {})]
            assert ctx.result("clip") is clip

            # Device seam engaged (construction saw the seamed load device).
            assert world.construction_initial_devices[-1] == torch.device("cpu")
        finally:
            rfp.teardown(ctx)
    finally:
        rcfs.uninstall_for_tests()


# ---------------------------------------------------------------------------
# C12 (T2): aliased live param fails closed with aliasing_unexpected
# ---------------------------------------------------------------------------


def test_aliasing_fail_closed(adopt_env, monkeypatch, tmp_path):
    world = _install_world(monkeypatch, tmp_path, world=_cast_world())
    world.alias_key = "weight"  # fake ctor binds weight to the STAGED tensor
    assert rcfs.install_request_clip_fastsafe() is True
    try:
        trace = FakeTrace()
        ctx = rfp.begin(request_id="r44h1-alias", trace=trace)
        try:
            result = _nodes()["CLIPLoader"]().load_clip(clip_name="clip.safetensors")

            # Fail-closed to the native lane with the aliasing reason.
            assert len(world.observed) == 1
            role, arm, kw = world.observed[0]
            assert (role, arm) == ("clip", "native_comfy")
            assert kw.get("fallback_attempted") is True
            assert "aliasing_unexpected" in str(kw.get("fallback_reason"))
            fallback_evt = trace.payloads("clip_fastsafe_fallback")[0]
            assert "aliasing_unexpected" in str(fallback_evt.get("reason"))
            assert any(
                "clip_fastsafe_failed:RuntimeError" in reason
                for reason in ctx.terminal_reasons()
            )
            # Owners closed, nothing published, request survived natively.
            loader, fb = world.owners_created[0]
            assert loader.closed is True and fb.closed is True
            assert ctx.result("clip") is None
            assert isinstance(result, tuple) and len(result) == 1
        finally:
            rfp.teardown(ctx)
    finally:
        rcfs.uninstall_for_tests()


# ---------------------------------------------------------------------------
# C13 (T3): record_observed failure => NOTHING published or marked loaded
# ---------------------------------------------------------------------------


def test_publication_order_record_observed_failure(adopt_env, monkeypatch, tmp_path):
    world = _install_world(monkeypatch, tmp_path, world=_cast_world())
    world.fail_record_observed = True
    assert rcfs.install_request_clip_fastsafe() is True
    try:
        ctx = rfp.begin(request_id="r44h1-puborder")
        try:
            publish_calls: list[Any] = []
            mark_calls: list[Any] = []
            orig_publish = ctx.publish_result
            orig_mark = ctx.mark_clip_loaded

            def spy_publish(role, payload):
                publish_calls.append((role, payload))
                orig_publish(role, payload)

            def spy_mark():
                mark_calls.append(1)
                orig_mark()

            ctx.publish_result = spy_publish  # type: ignore[method-assign]
            ctx.mark_clip_loaded = spy_mark  # type: ignore[method-assign]

            result = _nodes()["CLIPLoader"]().load_clip(clip_name="clip.safetensors")

            # Producer fell back natively...
            assert isinstance(result, tuple) and len(result) == 1
            assert len(world.ltf_calls) == 1
            # ... NOTHING was published and clip was never marked loaded ...
            assert publish_calls == []
            assert mark_calls == []
            assert ctx.result("clip") is None
            # ... and the failure was recorded terminally.
            assert any(
                "clip_fastsafe_failed:RuntimeError" in reason
                for reason in ctx.terminal_reasons()
            )
            # The success observation never landed (record_observed raised;
            # even the fallback re-record is suppressed by the same fault).
            assert world.observed == []
        finally:
            rfp.teardown(ctx)
    finally:
        rcfs.uninstall_for_tests()


# ---------------------------------------------------------------------------
# C13b (R44H3): source-retirement failure => NOTHING published, owners closed
# ---------------------------------------------------------------------------


def test_source_retirement_failure_does_not_publish(adopt_env, monkeypatch, tmp_path):
    world = _install_world(monkeypatch, tmp_path, world=_cast_world())
    world.fail_source_retirement = True
    assert rcfs.install_request_clip_fastsafe() is True
    try:
        trace = FakeTrace()
        ctx = rfp.begin(request_id="r44h3-retirefail", trace=trace)
        try:
            publish_calls: list[Any] = []
            mark_calls: list[Any] = []
            orig_publish = ctx.publish_result
            orig_mark = ctx.mark_clip_loaded

            def spy_publish(role, payload):
                publish_calls.append((role, payload))
                orig_publish(role, payload)

            def spy_mark():
                mark_calls.append(1)
                orig_mark()

            ctx.publish_result = spy_publish  # type: ignore[method-assign]
            ctx.mark_clip_loaded = spy_mark  # type: ignore[method-assign]

            result = _nodes()["CLIPLoader"]().load_clip(clip_name="clip.safetensors")

            # NOTHING was published or marked loaded ...
            assert publish_calls == []
            assert mark_calls == []
            assert ctx.result("clip") is None
            # ... and the request survived through the native lane.
            assert isinstance(result, tuple) and len(result) == 1
            assert len(world.ltf_calls) == 1

            # Honest telemetry: the precise failure reason landed in the
            # fallback event and terminal reasons; NO success end event.
            fb_evt = trace.payloads("clip_fastsafe_fallback")[0]
            assert "cast_once_source_retirement_failed" in str(fb_evt.get("reason"))
            assert "release_storage_injected_failure" in str(fb_evt.get("reason"))
            assert trace.payloads("clip_fast_load_end") == []
            assert any(
                "cast_once_source_retirement_failed" in reason
                for reason in ctx.terminal_reasons()
            )

            # Truth: ONLY the canonical native fallback observation landed.
            assert len(world.observed) == 1
            role, arm, kw = world.observed[0]
            assert (role, arm) == ("clip", "native_comfy")
            assert kw.get("fallback_attempted") is True

            # Owners were PRESERVED through the retirement failure (never
            # release_storage'd) and then CLOSED by the fail-closed handler.
            loader, fb = world.owners_created[0]
            assert loader.release_calls == 0 and fb.release_calls == 0
            assert loader.closed is True and fb.closed is True
        finally:
            rfp.teardown(ctx)
    finally:
        rcfs.uninstall_for_tests()


# ---------------------------------------------------------------------------
# C14 (T4): failed construction's registered patcher gets discarded
# ---------------------------------------------------------------------------


def test_failed_patcher_discarded(adopt_env, monkeypatch, tmp_path):
    world = _install_world(monkeypatch, tmp_path, world=_cast_world())
    world.register_patcher_on_build = True  # pinned sd.py:280-281 parity
    world.corrupt_values = True  # force a POST-construction failure
    assert rcfs.install_request_clip_fastsafe() is True
    try:
        trace = FakeTrace()
        ctx = rfp.begin(request_id="r44h1-discard", trace=trace)
        try:
            result = _nodes()["CLIPLoader"]().load_clip(clip_name="clip.safetensors")

            failed_patcher = world.built_clips[0].patcher

            # The failed patcher no longer sits in current_loaded_models.
            import comfy.model_management as comfy_mm

            assert all(
                getattr(lm, "model", None) is not failed_patcher
                for lm in comfy_mm.current_loaded_models
            )
            evt = trace.payloads("clip_fastsafe_failed_patchers_discarded")
            assert len(evt) >= 1
            assert int(evt[0].get("count", 0)) >= 1

            # Fallback still succeeded natively; nothing published.
            assert isinstance(result, tuple) and len(result) == 1
            assert ctx.result("clip") is None
            assert any(
                "clip_fastsafe_failed:RuntimeError" in reason
                for reason in ctx.terminal_reasons()
            )
        finally:
            rfp.teardown(ctx)
    finally:
        rcfs.uninstall_for_tests()
