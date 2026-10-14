"""Phase 11 Upscale backend-contract tests (FAST_UNIT, no heavy imports).

Locks the runtime contract owned by ``studio_upscale_run.py`` /
``studio_upscale_vosr2.py`` / ``studio_upscale_seedvr2.py`` (this phase adds
tests + dependency declarations only and must not invent a conflicting
schema — every behavioral assertion below calls the real functions):

* method literal vosr2|seedvr2 — explicit only, ``"auto"`` rejected;
* input is the current image filename (``source_image`` basename);
* request params carry method + source_image + scale (+ seed/tiles);
* dependency gate fails closed with explicit ``VOSR2_UNAVAILABLE*`` /
  ``SEEDVR2_UNAVAILABLE*`` errors (``*_unavailable`` precedent);
* output materialization exposes ``output_paths`` / ``primary_asset_id``
  plus ``meta {upscale_method, scale, source_asset, timings}``;
* the stored workflow JSON is never mutated;
* Generate/Edit paths are unaffected;
* web/ panel prefs + Run wiring match the backend literals (read-only).

Pure stdlib at collection: the upscale modules import torch/Modal/ComfyUI
lazily inside functions only.  No network, no GPU, no browser.  Each test
runs in milliseconds.
"""

from __future__ import annotations

import ast
import contextlib
import json
import sys
import types
from pathlib import Path

import numpy as np
import pytest

import studio_upscale_deps as deps
import studio_upscale_vosr2 as vosr2_mod
from studio_upscale_run import (
    UPSCALE_METHODS,
    UPSCALE_MODAL_APP_ENV,
    UPSCALE_MODAL_TIMEOUT_S,
    UPSCALE_REMOTE_FUNCTION,
    UpscaleRequestError,
    UpscaleRunError,
    _run_local,
    parse_upscale_request,
)
from studio_upscale_seedvr2 import (
    ERROR_CODE as SEEDVR2_ERROR_CODE,
)
from studio_upscale_seedvr2 import (
    SEEDVR2_METHOD,
    SeedVR2Unavailable,
    seedvr2_target_size,
)
from studio_upscale_vosr2 import ERROR_CODE as VOSR2_ERROR_CODE
from studio_upscale_vosr2 import (
    DEFAULT_SEED as VOSR2_DEFAULT_SEED,
)
from studio_upscale_vosr2 import (
    DEFAULT_TILE_OVERLAP,
    DEFAULT_TILE_SIZE,
    DEFAULT_VAE_TILE_SIZE,
    REQUEST_TIMING_KEYS,
    RESTORE_TIMING_KEYS,
    SNAPSHOT_MODE_CPU_WEIGHTS,
    SNAPSHOT_MODE_LEAN,
    STARTUP_TIMING_KEYS,
    VOSR2_FULL_IMAGE_MAX_PX,
    VOSR2_METHOD,
    VOSR2_SNAPSHOT_MODE_ENV,
    VOSR2Unavailable,
    _reset_vosr2_state,
    get_last_vosr2_timing,
    resolve_vosr2_tiling,
    upscale_vosr2,
    validate_vosr2_scale,
    vosr2_is_restored,
    vosr2_is_static_ready,
    vosr2_restore,
    vosr2_static_init,
)

pytestmark = pytest.mark.fast_unit

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def _code(exc: Exception) -> str:
    return getattr(exc, "error_code", "")


# ── method selection: explicit literals, no auto ────────────────────────────


def test_method_literals_are_exactly_vosr2_seedvr2():
    assert UPSCALE_METHODS == ("vosr2", "seedvr2")
    assert VOSR2_METHOD == "vosr2" and SEEDVR2_METHOD == "seedvr2"
    assert "auto" not in UPSCALE_METHODS


def test_parse_accepts_both_methods_with_sane_defaults():
    vosr = parse_upscale_request({"method": "vosr2", "source_image": "a.png"})
    assert vosr["method"] == "vosr2"
    assert vosr["source_image"] == "a.png"
    assert vosr["scale"] == 4
    assert vosr["seed"] == VOSR2_DEFAULT_SEED
    assert vosr["tile_size"] == DEFAULT_TILE_SIZE
    assert vosr["tile_overlap"] == DEFAULT_TILE_OVERLAP
    assert vosr["vae_tile_size"] == DEFAULT_VAE_TILE_SIZE
    seed = parse_upscale_request(
        {"method": "seedvr2", "source_image": "b.png", "scale": 2}
    )
    assert seed["method"] == "seedvr2" and seed["scale"] == 2
    assert "tile_size" not in seed  # seedvr2 takes target res, not tiles


def test_parse_rejects_auto_and_unknown_methods():
    for bad in ("auto", "Auto", "AUTO", " auto", "esrgan", "vosr", ""):
        with pytest.raises(UpscaleRequestError) as caught:
            parse_upscale_request({"method": bad, "source_image": "a.png"})
        assert _code(caught.value) in (
            "UPSCALE_UNKNOWN_METHOD",
            "UPSCALE_METHOD_REQUIRED",
        )
        assert "400" not in _code(caught.value)
    with pytest.raises(UpscaleRequestError) as caught:
        parse_upscale_request({"source_image": "a.png"})
    assert _code(caught.value) == "UPSCALE_METHOD_REQUIRED"
    with pytest.raises(UpscaleRequestError) as caught:
        parse_upscale_request(["not", "a", "dict"])
    assert _code(caught.value) == "UPSCALE_BAD_REQUEST"


def test_parse_rejects_missing_and_unsafe_sources():
    with pytest.raises(UpscaleRequestError) as caught:
        parse_upscale_request({"method": "vosr2"})
    assert _code(caught.value) == "UPSCALE_SOURCE_REQUIRED"
    for bad in ("out/a.png", "C:\\o\\a.png", "../escape.png", ".."):
        with pytest.raises(UpscaleRequestError) as caught:
            parse_upscale_request({"method": "vosr2", "source_image": bad})
        assert _code(caught.value) == "UPSCALE_BAD_SOURCE"


def test_parse_rejects_bad_scales_and_options():
    for bad in (0, -1, "huge", None):
        with pytest.raises(UpscaleRequestError) as caught:
            parse_upscale_request(
                {"method": "vosr2", "source_image": "a.png", "scale": bad}
            )
        assert _code(caught.value) == "UPSCALE_BAD_SCALE"
    with pytest.raises(UpscaleRequestError) as caught:
        parse_upscale_request(
            {"method": "vosr2", "source_image": "a.png", "tile_size": 3}
        )
    assert _code(caught.value) == "UPSCALE_BAD_OPTION"
    with pytest.raises(UpscaleRequestError) as caught:
        parse_upscale_request(
            {"method": "seedvr2", "source_image": "a.png", "seed": -2}
        )
    assert _code(caught.value) == "UPSCALE_BAD_OPTION"


def test_request_errors_are_400_class():
    try:
        parse_upscale_request({"method": "auto", "source_image": "a.png"})
    except UpscaleRequestError as exc:
        assert exc.http_status == 400
        assert isinstance(exc, ValueError)
    else:  # pragma: no cover
        raise AssertionError("expected UpscaleRequestError")


# ── dependency gate: explicit fail-closed errors ────────────────────────────


def test_dep_error_codes_match_unavailable_precedent():
    assert VOSR2_ERROR_CODE == "VOSR2_UNAVAILABLE"
    assert SEEDVR2_ERROR_CODE == "SEEDVR2_UNAVAILABLE"
    assert "UNAVAILABLE" in VOSR2_ERROR_CODE and "UNAVAILABLE" in SEEDVR2_ERROR_CODE


def test_vosr2_scale_validation_fails_closed():
    assert validate_vosr2_scale(4) == 4.0
    assert validate_vosr2_scale("2") == 2.0
    for bad in (0, -1, "huge", None):
        with pytest.raises(VOSR2Unavailable) as caught:
            validate_vosr2_scale(bad)
        assert "VOSR2_UNAVAILABLE" in str(caught.value)


def test_seedvr2_target_size_snaps_to_16_and_fails_closed():
    assert seedvr2_target_size(100, 100, 2) == (192, 192)
    assert seedvr2_target_size(64, 64, 1)[0] % 16 == 0
    for bad in (0, -1, "huge", None):
        with pytest.raises(SeedVR2Unavailable) as caught:
            seedvr2_target_size(64, 64, bad)
        assert "SEEDVR2_UNAVAILABLE" in str(caught.value)


def test_adapters_reject_non_pil_input_before_touching_gpu():
    with pytest.raises(VOSR2Unavailable) as caught:
        upscale_vosr2("not-an-image", scale=2)
    assert "VOSR2_UNAVAILABLE" in str(caught.value)
    from studio_upscale_seedvr2 import upscale_seedvr2

    with pytest.raises(SeedVR2Unavailable) as caught:
        upscale_seedvr2("not-an-image", scale=2)
    assert "SEEDVR2_UNAVAILABLE" in str(caught.value)


def test_local_dispatch_fails_closed_without_cuda_or_weights():
    from PIL import Image

    rgb = Image.new("RGB", (32, 32), (10, 20, 30))
    with pytest.raises(UpscaleRunError) as caught:
        _run_local(
            "vosr2",
            rgb,
            {
                "scale": 2,
                "tile_size": 512,
                "tile_overlap": 64,
                "vae_tile_size": 256,
                "seed": 0,
            },
        )
    assert caught.value.http_status == 503
    assert "VOSR2_UNAVAILABLE" in caught.value.error_code
    with pytest.raises(UpscaleRunError) as caught:
        _run_local("seedvr2", rgb, {"scale": 2, "seed": 666})
    assert caught.value.http_status == 503
    assert "SEEDVR2_UNAVAILABLE" in caught.value.error_code


def test_manifest_gate_uses_real_codes_and_stays_fast_safe():
    for method in ("vosr2", "seedvr2"):
        result = deps.check_upscale_dependencies(method)
        assert result["ok"] is False
        assert result["missing"] == [method]
        assert len(result["errors"]) == 1
        assert deps.UPSCALE_DEP_ERROR_CODES[method] in result["errors"][0]
    ok = deps.check_upscale_dependencies("vosr2", available_backends={"vosr2"})
    assert ok["ok"] is True and ok["errors"] == []
    bad = deps.check_upscale_dependencies("auto")
    assert bad["ok"] is False and "UPSCALE_UNKNOWN_METHOD" in bad["errors"][0]
    text = (ROOT / "studio_upscale_deps.py").read_text(encoding="utf-8")
    for banned in ("import torch", "import modal", "import comfy", "from torch",
                   "from modal", "from comfy", "import folder_paths",
                   "import nodes"):
        assert banned not in text, f"heavy import leaked: {banned}"
    assert isinstance(deps.MODAL_PIP_PINS, tuple)
    assert "comfyapp.py" in deps.MODAL_FOUNDATION_REF


def test_remote_dispatch_table_is_config_owned_and_constant():
    assert UPSCALE_REMOTE_FUNCTION == "studio_upscale"
    assert UPSCALE_MODAL_APP_ENV == "COMFYMODAL_UPSCALE_APP_NAME"
    assert UPSCALE_MODAL_TIMEOUT_S == 1800.0
    assert deps.UPSCALE_REMOTE_FUNCTION == "studio_upscale"
    # Single entrypoint: no per-method deployed names remain.
    text = (ROOT / "studio_upscale_run.py").read_text(encoding="utf-8")
    assert "UPSCALE_REMOTE_FUNCTIONS" not in text
    assert '"studio_upscale_vosr2"' not in text
    assert '"studio_upscale_seedvr2"' not in text
    assert '"studio_upscale"' in text


def test_single_remote_payload_carries_method_explicitly():
    text = (ROOT / "studio_upscale_run.py").read_text(encoding="utf-8")
    assert '"method": method' in text
    assert '"image_b64"' in text
    # The single Modal call looks up exactly one deployed name.
    assert "UPSCALE_REMOTE_FUNCTION" in text
    assert "modal.Function.from_name(app_name, remote_name" in text
    # Error codes name the single function path, not per-method names.
    assert "UPSCALE_MODAL_UNAVAILABLE" in text
    assert "UPSCALE_MODAL_FAILED" in text
    assert "UPSCALE_MODAL_BAD_RESULT" in text
    assert "via {remote_name} failed" in text


def test_modal_dispatch_revalidates_unknown_method_fast():
    import asyncio

    from studio_upscale_run import _run_on_modal

    async def _call():
        await _run_on_modal("auto", object(), {"scale": 4, "seed": 0}, {})

    with pytest.raises(UpscaleRequestError) as caught:
        asyncio.run(_call())
    assert _code(caught.value) == "UPSCALE_UNKNOWN_METHOD"


def test_manifest_lock_declares_real_dep_surface():
    text = (ROOT / "upscale_dependency_lock.txt").read_text(encoding="utf-8")
    for marker in ("vosr2", "seedvr2", "studio_upscale",
                   "COMFYMODAL_VOSR2_WEIGHTS",
                   "COMFYMODAL_SEEDVR2_WEIGHTS", "COMFYMODAL_UPSCALE_APP_NAME"):
        assert marker in text, f"lock missing {marker}"
    assert '"studio_upscale_vosr2"' not in text
    assert '"studio_upscale_seedvr2"' not in text
    assert "single remote entry" in text
    assert "auto" in text.lower()  # documents the no-auto rule


# ── output materialization + provenance shape (structural, FAST-safe) ───────


def test_result_shape_locks_paths_primary_asset_and_meta():
    # handle_upscale_async needs ComfyUI dirs + GPU; lock its promised shape
    # at source level so FAST never pays for heavy execution.
    text = (ROOT / "studio_upscale_run.py").read_text(encoding="utf-8")
    for marker in ('"output_paths"', '"output_path"', '"primary_asset_id"',
                   '"runId"', '"meta"', '"upscale_method"', '"scale"',
                   '"source_asset"', '"timings"', '"load_ms"',
                   '"inference_ms"', '"save_ms"', '"total_ms"',
                   '"backend"', '"modal_used"', '"status": "ok"',
                   'studio-upscale-'):
        assert marker in text, f"result shape missing {marker}"


def test_no_workflow_mutation_in_dispatch_source():
    text = (ROOT / "studio_upscale_run.py").read_text(encoding="utf-8")
    mentions = [
        line.strip()
        for line in text.splitlines()
        if "workflow" in line.lower()
    ]
    # Exactly the two docstring promises; no workflow parameter, no writes.
    assert len(mentions) == 2, mentions
    assert "Never mutates the stored workflow" in text
    lines = text.splitlines()
    start = next(
        i for i, line in enumerate(lines) if "async def handle_upscale_async" in line
    )
    signature = "\n".join(lines[start : start + 6])
    assert "workflow" not in signature


def test_generate_edit_python_paths_carry_no_upscale_vocabulary():
    for name in ("studio_workflow_run.py", "studio_golden_run.py"):
        text = (ROOT / name).read_text(encoding="utf-8")
        for marker in ("vosr2", "seedvr2", "studio_upscale", "UPSCALE_",
                       "upscale_method"):
            assert marker not in text, f"{name} unexpectedly mentions {marker}"


# ── web/ panel + Run wiring (read-only structural guards) ───────────────────


def test_web_panel_literals_match_backend():
    state = (WEB / "studio-playground-state.js").read_text(encoding="utf-8")
    assert 'Object.freeze(["vosr2", "seedvr2"])' in state
    assert 'vosr2: "VOSR2"' in state and 'seedvr2: "SeedVR2"' in state
    assert '"comfymodal.studio.upscale.v1"' in state
    # Default prefs mirror the backend contract: vosr2, scale 4,
    # explicit seed 0, VOSR2 tile edge 512.
    assert '{ method: "vosr2", scale: 4, seed: 0, tileSize: 512 }' in state


def test_web_panel_has_no_auto_and_upscale_runs_unblocked():
    state = (WEB / "studio-playground-state.js").read_text(encoding="utf-8")
    assert "only those two persist" in state
    assert "Upscale runs from the Run Upscale button in the panel below." in state
    assert "Upscale arrives in a later phase" not in state  # shipped, not placeholder
    assert '["references", "guidance"]' in state  # upscale left placeholders
    assert "Post Processing runs locally" in state  # other Post still local


def test_web_backend_api_posts_upscale_with_error_plumbing():
    api = (WEB / "studio-backend-api.js").read_text(encoding="utf-8")
    assert "export async function runStudioUpscale" in api
    assert '"/studio/upscale"' in api
    assert "source_image" in api
    assert "STUDIO_UPSCALE_ERROR" in api
    assert "error_code" in api


def test_history_provenance_contract_is_additive_and_method_truthful():
    # History carries upscale provenance additively: the repository
    # normalizes {method, scale, seed, ...} from backend-projected keys and
    # the detail view renders one Upscale section only when present.
    repo = (WEB / "history-v2-repository.js").read_text(encoding="utf-8")
    assert "upscale: _firstObject(out.upscale, out.upscale_info, out.upscaleInfo)" in repo
    for marker in ("raw.upscale", "raw.upscale_info", "raw.upscaleInfo"):
        assert marker in repo, f"repository record level missing {marker}"
    detail = (WEB / "studio-history-v2-detail.js").read_text(encoding="utf-8")
    assert "function _buildUpscaleSection(record)" in detail
    assert '"history-v2-upscale"' in detail
    assert 'method === "seedvr2" ? "SeedVR2"' in detail
    assert 'method === "vosr2" ? "VOSR2"' in detail
    # Additive: no section when neither record nor featured output carries it.
    assert "Returns null when neither" in detail


def test_queue_fake_spec_still_lists_upscale_tool_mode():
    text = (
        ROOT / "tests" / "browser" / "fake" / "studio-fake-queue-manager.spec.mjs"
    ).read_text(encoding="utf-8")
    assert "upscale" in text


# ── History-registry hook (additive, exception-isolated) ───────────────────


def _upscale_history_hook_block() -> str:
    text = (ROOT / "__init__.py").read_text(encoding="utf-8")
    start = text.index("# History provenance (additive, exception-isolated)")
    end = text.index("return web.json_response(result, status=200)", start)
    return text[start:end]


def test_upscale_history_hook_is_additive_and_never_fails():
    # The /comfymodal/studio/upscale route records provenance through the
    # shared registry AFTER handle_upscale_async succeeds.  The hook must
    # stay additive (copy meta, nest under one "upscale" key) and must never
    # fail the upscale (broad except warns only; the 200 return follows).
    block = _upscale_history_hook_block()
    assert "REGISTRY as _upscale_registry" in block
    assert ".history().record_run(" in block
    assert 'kind="studio_upscale"' in block
    assert 'status="completed"' in block
    assert '_upscale_meta = dict(result.get("meta") or {})' in block
    assert '_upscale_meta["upscale"] = {' in block
    assert "except Exception:" in block
    assert 'Studio upscale history record failed' in block
    assert "\nraise" not in block and " raise " not in block
    # history_generation_id stamped only when the registry returns one.
    assert 'result["history_generation_id"]' in block
    assert 'if isinstance(_hist, dict) and _hist.get("history_generation_id")' in block
    # timings passed through only when dict (record_run treats None as absent).
    assert "isinstance(_upscale_timings, dict) else None" in block


def test_upscale_history_hook_kwargs_match_record_run_signature():
    # The hook swallows ALL exceptions, so a signature drift in
    # RunHistoryService.record_run would silently drop provenance.  Pin the
    # kwargs the hook passes against the real signature via AST (stdlib
    # only — no heavy experiment_service import at collection).
    import ast

    src = (ROOT / "experiment_service.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    sig = None
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "record_run"
        ):
            names = [a.arg for a in node.args.kwonlyargs]
            if "kind" in names and "prompt_id" in names:
                sig = node
                break
    assert sig is not None, "RunHistoryService.record_run not found"
    params = {a.arg for a in sig.args.kwonlyargs}
    for kw in ("kind", "prompt_id", "status", "meta", "timings", "output_path"):
        assert kw in params, f"record_run missing kwarg {kw}"
    kw_defaults = {
        a.arg: d for a, d in zip(sig.args.kwonlyargs, sig.args.kw_defaults)
    }
    for kw in ("status", "meta", "timings", "output_path"):
        assert kw_defaults.get(kw) is not None, f"{kw} must have a default"


# ── TRUE-COLD VOSR2: in-process adapter contract ────────────────────────────
#
# These tests exercise the real ``studio_upscale_vosr2`` static/restore/
# per-image split against stub upstream modules (recorded fakes injected
# via ``sys.modules``).  No real torch import (real torch takes seconds and
# owns CUDA), no network, no subprocess, no GPU.  Each test runs in
# milliseconds.


_FAKE_VOSR2_ARGS = {
    "ae_type": "qwen",
    "ae_path": "preset/ckpts/Qwen-Image-vae-2d",
    "enc_type": "dinov2l",
    "layer_dinov2b_list": [21, 22, 23],
    "dim": 64,
    "depth": 2,
    "num_heads": 4,
    "mlp_ratio": 4.0,
    "enc_dim": 32,
    "encdim_ratio": 2.0,
    "resolution": 256,
    "patch_size": 2,
    "time_dist": ["lognorm", -0.4, 1.0],
    "cfg_ratio": 0.1,
    "cfg_scale": 2.0,
    "interp_type": "lin",
    "t_start": 0.0,
    "t_end": 1.0,
    "dinov2_size": 256,
    "infer_steps": 1,
    "align_method": "wavelet",
}


class _FakeTensor:
    """Numpy-backed tensor double: supports exactly the ops the adapter's
    own IO helpers use (model math stays inside the stub upstream fns)."""

    def __init__(self, arr, calls):
        self._arr = np.asarray(arr, dtype=np.float32)
        self._calls = calls

    @property
    def shape(self):
        return self._arr.shape

    def __len__(self):
        return len(self._arr)

    def __getitem__(self, idx):
        return _FakeTensor(self._arr[idx], self._calls)

    def unsqueeze(self, dim):
        return _FakeTensor(np.expand_dims(self._arr, dim), self._calls)

    def permute(self, *dims):
        return _FakeTensor(np.transpose(self._arr, dims), self._calls)

    def to(self, device):
        self._calls.append(("tensor.to", str(device)))
        return self

    def cpu(self):
        return self

    def detach(self):
        return self

    def numpy(self):
        return self._arr

    def _binop(self, other, op):
        rhs = other._arr if isinstance(other, _FakeTensor) else other
        return _FakeTensor(op(self._arr, rhs), self._calls)

    def __mul__(self, other):
        return self._binop(other, np.multiply)

    __rmul__ = __mul__

    def __add__(self, other):
        return self._binop(other, np.add)

    def __sub__(self, other):
        return self._binop(other, np.subtract)

    def __truediv__(self, other):
        return self._binop(other, np.true_divide)


class _FakeModel:
    def __init__(self, calls, name, **kwargs):
        self._calls = calls
        self._name = name
        self.kwargs = dict(kwargs)

    def to(self, device):
        self._calls.append((f"{self._name}.to", str(device)))
        return self

    def eval(self):
        self._calls.append((f"{self._name}.eval",))
        return self

    def parameters(self):
        return []

    def load_state_dict(self, state, strict=False):
        self._calls.append((f"{self._name}.load_state_dict", len(state)))
        return self


def _build_vosr2_stubs(calls):
    """Build the stub torch + upstream module doubles.  Every boundary the
    contract cares about (cuda touches, weight reads, H2D, kernel choice)
    appends to ``calls``."""

    class _FakeCuda:
        def is_available(self):
            calls.append(("cuda.is_available",))
            return True

        def init(self):
            calls.append(("cuda.init",))

        def manual_seed_all(self, seed):
            calls.append(("cuda.manual_seed_all", seed))

        def synchronize(self):
            calls.append(("cuda.synchronize",))

        def empty_cache(self):
            calls.append(("cuda.empty_cache",))

    torch_stub = types.ModuleType("torch")
    torch_stub.cuda = _FakeCuda()

    def _device(name):
        calls.append(("torch.device", str(name)))
        return str(name)

    torch_stub.device = _device

    def _manual_seed(seed):
        calls.append(("torch.manual_seed", seed))

    torch_stub.manual_seed = _manual_seed

    def _torch_load(path, map_location=None):
        calls.append(("torch.load", str(path)))
        return {}

    torch_stub.load = _torch_load

    def _from_numpy(arr):
        return _FakeTensor(arr, calls)

    torch_stub.from_numpy = _from_numpy
    torch_stub.hub = types.SimpleNamespace(
        set_dir=lambda d: calls.append(("hub.set_dir", str(d))),
    )
    torch_stub.no_grad = lambda: contextlib.nullcontext()

    class _FakeDiT(_FakeModel):
        def __init__(self, **kwargs):
            super().__init__(calls, "dit", **kwargs)
            calls.append(("dit.construct", sorted(kwargs)))

        def forward_flexible(self, *args, **kwargs):
            calls.append(("dit.forward_flexible",))
            return _FakeTensor(np.zeros((1, 16, 4, 4)), calls)

    class _FakeEncoder(_FakeModel):
        def __init__(self):
            super().__init__(calls, "venc")
            calls.append(("venc.construct",))

    class _FakeVAE(_FakeModel):
        def __init__(self):
            super().__init__(calls, "vae")

        @classmethod
        def from_pretrained(cls, path):
            calls.append(("vae.from_pretrained", str(path)))
            return cls()

    class _FakeVOSR:
        def __init__(self, **kwargs):
            self._calls = calls
            calls.append(("vosr.construct", sorted(kwargs)))

        def eval(self):
            return self

        def sample_onestep(
            self, model, lq, venc_fea=None, n_steps=1, schedule="linear"
        ):
            calls.append(("vosr.sample_onestep", n_steps))
            return _FakeTensor(np.zeros((1, 16, 4, 4)), calls)

    def _load_dinov2(config, device):
        calls.append(("load_dinov2", str(device)))
        return _FakeEncoder()

    def _get_venc_features(venc, lq, args):
        calls.append(("get_venc_features",))
        return [_FakeTensor(np.zeros((1, 5, 3)), calls)]

    def _encode_dispatch(vae, x, args, device):
        calls.append(("encode_dispatch", str(device)))
        h, w = x.shape[2] // 8, x.shape[3] // 8
        return (
            _FakeTensor(np.zeros((1, 16, h, w)), calls),
            _FakeTensor(np.zeros((1, 16, 1, 1)), calls),
            _FakeTensor(np.ones((1, 16, 1, 1)), calls),
        )

    def _decode_dispatch(vae, latent, args, mean, std, light_decoder=None):
        calls.append(("decode_dispatch",))
        h, w = latent.shape[2] * 8, latent.shape[3] * 8
        return _FakeTensor(np.zeros((1, 3, h, w)), calls)

    def _tiled_latent_inference(
        model, vae, venc, lq, args, device, light_decoder=None
    ):
        calls.append(("tiled_latent_inference", str(device)))
        h, w = lq.shape[2], lq.shape[3]
        return _FakeTensor(np.zeros((1, 3, h, w)), calls)

    def _wavelet(img, ref):
        calls.append(("wavelet_color_fix",))
        return img

    def _adain(img, ref):
        calls.append(("adain_color_fix",))
        return img

    upstream = types.ModuleType("inference_vosr_onestep")
    upstream.load_dinov2 = _load_dinov2
    upstream.get_venc_features = _get_venc_features
    upstream.tiled_latent_inference = _tiled_latent_inference
    upstream.wavelet_color_fix = _wavelet
    upstream.adain_color_fix = _adain

    tiled_vae = types.ModuleType("tiled_vae")
    tiled_vae.encode_dispatch = _encode_dispatch
    tiled_vae.decode_dispatch = _decode_dispatch

    models_pkg = types.ModuleType("models")
    models_pkg.__path__ = []
    dit_mod = types.ModuleType("models.lightningdit")
    dit_mod.LightningDiT = _FakeDiT
    decoder_mod = types.ModuleType("models.light_decoder")
    decoder_mod.LightDecoder = _FakeModel
    qwen_mod = types.ModuleType("models.qwenimage_vae2d")
    qwen_mod.AutoencoderKLQwenImage2D = _FakeVAE
    vosr_mod = types.ModuleType("vosr")
    vosr_mod.VOSR = _FakeVOSR

    safetensors_pkg = types.ModuleType("safetensors")
    safetensors_pkg.__path__ = []
    safetensors_torch = types.ModuleType("safetensors.torch")

    def _load_file(path):
        calls.append(("safetensors.load_file", str(path)))
        return {"w": _FakeTensor(np.zeros((2, 2)), calls)}

    safetensors_torch.load_file = _load_file

    return {
        "torch": torch_stub,
        "models": models_pkg,
        "models.lightningdit": dit_mod,
        "models.light_decoder": decoder_mod,
        "models.qwenimage_vae2d": qwen_mod,
        "vosr": vosr_mod,
        "tiled_vae": tiled_vae,
        "inference_vosr_onestep": upstream,
        "safetensors": safetensors_pkg,
        "safetensors.torch": safetensors_torch,
    }


def _write_fake_vosr2_bundle(tmp_path, *, with_dinov2=True, with_weights=True):
    """Create a fake checkout + weights bundle (files only — the stub
    modules above stand in for torch/upstream)."""
    repo = tmp_path / "repo"
    weights = tmp_path / "weights"
    (weights / "checkpoints").mkdir(parents=True)
    (weights / "args.json").write_text(json.dumps(_FAKE_VOSR2_ARGS))
    if with_weights:
        (weights / "checkpoints" / "ema_model.safetensors").write_bytes(b"fake")
    vae_dir = repo / "preset" / "ckpts" / "Qwen-Image-vae-2d"
    vae_dir.mkdir(parents=True)
    (vae_dir / "config.json").write_text("{}")
    if with_dinov2:
        cache = (
            repo / "preset" / "ckpts" / "torch_cache"
            / "facebookresearch_dinov2_main"
        )
        cache.mkdir(parents=True)
        (cache / "README").write_text("fake")
    (repo / "inference_vosr_onestep.py").write_text("# stub marker\n")
    return repo, weights


@pytest.fixture
def vosr2_stub(monkeypatch, tmp_path):
    """Stub torch + upstream VOSR modules with a pre-warmed fake bundle."""
    calls: list = []
    repo, weights = _write_fake_vosr2_bundle(tmp_path)
    for name, mod in _build_vosr2_stubs(calls).items():
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.setenv("COMFYMODAL_VOSR2_WEIGHTS", str(weights))
    monkeypatch.setenv("COMFYMODAL_VOSR2_REPO", str(repo))
    for knob in (
        "COMFYMODAL_VOSR2_DINOV2",
        "COMFYMODAL_VOSR2_DINOV2_PATH",
        "COMFYMODAL_VOSR2_TORCH_HUB",
        "COMFYMODAL_VOSR2_SNAPSHOT_MODE",
    ):
        monkeypatch.delenv(knob, raising=False)
    monkeypatch.setenv("TORCH_HUB_DIR", str(tmp_path / "empty_hub"))
    _reset_vosr2_state()
    yield {"calls": calls, "repo": repo, "weights": weights}
    _reset_vosr2_state()


def _cuda_touches(calls) -> list:
    return [
        call
        for call in calls
        if call[0].startswith("cuda.")
        or (call[0].endswith(".to") and call[-1] != "cpu")
        or (call[0] == "tensor.to" and call[-1] != "cpu")
    ]


def test_vosr2_adapter_has_no_subprocess_network_or_cli_surface():
    # The TRUE-COLD adapter is in-process: no subprocess, no sockets, no
    # CLI argv — and the upstream call happens through real upstream
    # symbols, not reimplemented math.  (Bans are code patterns, not prose:
    # the docstring legitimately names what was removed.)
    text = (ROOT / "studio_upscale_vosr2.py").read_text(encoding="utf-8")
    for banned in (
        "import subprocess",
        "from subprocess",
        "subprocess.run",
        "subprocess.Popen",
        "import socket",
        "from socket",
        "socket.create_connection",
        "_run_cli",
        "Popen(",
        "check_output",
        "sys.executable",
        "torch.hub.load(",
        "--tile_size",
    ):
        assert banned not in text, f"request-time surface leaked: {banned}"
    for required in (
        "tiled_latent_inference",
        "encode_dispatch",
        "decode_dispatch",
        "sample_onestep",
        "get_venc_features",
        "vosr2_static_init",
        "vosr2_restore",
    ):
        assert required in text, f"upstream call missing: {required}"


def test_vosr2_request_path_has_no_imports_and_static_has_no_cuda():
    # Zero request-time imports/config/path-scanning: the per-image body
    # uses cached static state only.  Snapshot-capturable static init:
    # zero torch.cuda touches (asserted structurally, not by luck).
    tree = ast.parse(
        (ROOT / "studio_upscale_vosr2.py").read_text(encoding="utf-8")
    )
    fns = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    request_body = fns["upscale_vosr2"]
    assert not any(
        isinstance(node, (ast.Import, ast.ImportFrom))
        for node in ast.walk(request_body)
    ), "request path must not import"
    static_body = fns["vosr2_static_init"]
    assert not any(
        isinstance(node, ast.Attribute) and node.attr == "cuda"
        for node in ast.walk(static_body)
    ), "static init must not touch torch.cuda"
    assert not any(
        isinstance(node, ast.Name) and node.id == "cuda"
        for node in ast.walk(static_body)
    ), "static init must not name cuda"


def test_vosr2_static_split_and_timing_boundaries(vosr2_stub):
    # STATIC (CPU-only, no CUDA, no weight bytes in lean mode) vs RESTORE
    # (CUDA init once, H2D, lean re-reads) vs PER-IMAGE (decode -> DINO ->
    # VAE -> DiT -> VAE -> align), with disjoint timing boundaries.
    calls = vosr2_stub["calls"]
    assert not vosr2_is_static_ready() and not vosr2_is_restored()

    ready = vosr2_static_init()
    assert ready["status"] == "ready"
    assert ready["snapshot_mode"] == SNAPSHOT_MODE_LEAN
    assert vosr2_is_static_ready() and not vosr2_is_restored()
    assert _cuda_touches(calls) == []
    # Lean static defers every weight/DINO load to restore (shells + paths
    # only); the hub cache pointer is CPU config and is set now.
    assert ("hub.set_dir", str(vosr2_stub["repo"] / "preset" / "ckpts" / "torch_cache")) in calls
    assert ("load_dinov2", "cpu") not in calls
    # Lean static reads no weight bytes — only records paths.
    assert [
        call
        for call in calls
        if call[0]
        in ("safetensors.load_file", "torch.load", "vae.from_pretrained")
    ] == []
    startup_timing = ready["startup_timing"]
    assert all(key in startup_timing for key in STARTUP_TIMING_KEYS)
    assert not any(key in startup_timing for key in REQUEST_TIMING_KEYS)

    restored = vosr2_restore()
    assert restored["status"] == "ready"
    assert vosr2_is_restored()
    assert ("cuda.init",) in calls
    assert ("dit.to", "cuda") in calls
    assert ("vae.to", "cuda") in calls
    assert ("venc.to", "cuda") in calls
    # Lean restore loads DINOv2 on CPU first, then H2Ds everything.
    assert ("load_dinov2", "cpu") in calls
    # Lean restore re-reads weights from disk, then materializes.
    assert any(
        call[0] == "safetensors.load_file" for call in calls
    )
    assert any(call[0] == "vae.from_pretrained" for call in calls)
    restore_timing = restored["restore_timing"]
    assert all(key in restore_timing for key in RESTORE_TIMING_KEYS)
    assert set(RESTORE_TIMING_KEYS).isdisjoint(REQUEST_TIMING_KEYS)
    assert set(STARTUP_TIMING_KEYS).isdisjoint(REQUEST_TIMING_KEYS)

    from PIL import Image

    out = upscale_vosr2(Image.new("RGB", (16, 16), (10, 20, 30)), scale=2)
    assert out.size == (32, 32)
    timing = get_last_vosr2_timing()
    assert all(key in timing for key in REQUEST_TIMING_KEYS)
    assert all(key in timing for key in RESTORE_TIMING_KEYS)
    assert timing["tiling"] == "full"
    assert timing["tile_size_effective"] == 0
    assert timing["vae_tile_size_effective"] is None
    # Small image: full-image kernels, never the tiled DiT kernel.
    assert ("vosr.sample_onestep", 1) in calls
    assert any(call[0] == "encode_dispatch" for call in calls)
    assert not any(call[0] == "tiled_latent_inference" for call in calls)

    # Restore is idempotent: no second source read, no second H2D.
    reads_before = len(
        [
            call
            for call in calls
            if call[0]
            in ("safetensors.load_file", "torch.load", "vae.from_pretrained")
        ]
    )
    h2d_before = len([call for call in calls if call[0].endswith(".to")])
    second = vosr2_restore()
    assert second["cached"] is True
    assert (
        len(
            [
                call
                for call in calls
                if call[0]
                in (
                    "safetensors.load_file",
                    "torch.load",
                    "vae.from_pretrained",
                )
            ]
        )
        == reads_before
    )
    assert len([call for call in calls if call[0].endswith(".to")]) == h2d_before


def test_vosr2_snapshot_modes_lean_vs_cpu_weights(vosr2_stub, monkeypatch):
    # The operator knob switches weight residency; nothing else changes.
    calls = vosr2_stub["calls"]
    monkeypatch.setenv(VOSR2_SNAPSHOT_MODE_ENV, SNAPSHOT_MODE_CPU_WEIGHTS)
    vosr2_static_init()
    static_reads = [
        call
        for call in calls
        if call[0]
        in ("safetensors.load_file", "torch.load", "vae.from_pretrained")
    ]
    assert static_reads, "cpu_weights must read weights at static init"
    assert _cuda_touches(calls) == []
    vosr2_restore()
    assert (
        len(
            [
                call
                for call in calls
                if call[0]
                in (
                    "safetensors.load_file",
                    "torch.load",
                    "vae.from_pretrained",
                )
            ]
        )
        == len(static_reads)
    ), "cpu_weights restore must not re-read weights"

    _reset_vosr2_state()
    calls.clear()
    monkeypatch.setenv(VOSR2_SNAPSHOT_MODE_ENV, SNAPSHOT_MODE_LEAN)
    vosr2_static_init()
    assert [
        call
        for call in calls
        if call[0]
        in ("safetensors.load_file", "torch.load", "vae.from_pretrained")
    ] == []
    vosr2_restore()
    assert [
        call
        for call in calls
        if call[0]
        in ("safetensors.load_file", "torch.load", "vae.from_pretrained")
    ], "lean restore must re-read weights"

    _reset_vosr2_state()
    monkeypatch.setenv(VOSR2_SNAPSHOT_MODE_ENV, "bogus-mode")
    with pytest.raises(VOSR2Unavailable) as caught:
        vosr2_static_init()
    assert "VOSR2_UNAVAILABLE" in str(caught.value)


def test_vosr2_tiling_rule_full_for_small_tiled_for_large(
    vosr2_stub, monkeypatch
):
    # 400x400-class outputs take the normal full-image path; only genuinely
    # large outputs honor the caller's tiling knobs.
    assert VOSR2_FULL_IMAGE_MAX_PX == 2048
    small = resolve_vosr2_tiling(400, 400, 4, 512, 64, 256)
    assert small["tiling"] == "full"
    assert small["tile_size"] == 0 and small["vae_tile_size"] is None
    at_threshold = resolve_vosr2_tiling(512, 512, 4, 512, 64, 256)
    assert at_threshold["tiling"] == "full"  # 2048 == threshold
    large = resolve_vosr2_tiling(1600, 1600, 4, 512, 64, 256)
    assert large["tiling"] == "tiled"
    assert large["tile_size"] == 512 and large["tile_overlap"] == 64
    assert large["vae_tile_size"] == 256

    # The tiled execution path drives the upstream tiled kernel (stub) and
    # reports itself as tiled — never lumped with the full-image timings.
    calls = vosr2_stub["calls"]
    monkeypatch.setattr(vosr2_mod, "VOSR2_FULL_IMAGE_MAX_PX", 16)
    from PIL import Image

    out = upscale_vosr2(Image.new("RGB", (16, 16), (10, 20, 30)), scale=2)
    assert out.size == (32, 32)
    assert any(call[0] == "tiled_latent_inference" for call in calls)
    assert not any(call[0] == "encode_dispatch" for call in calls)
    assert get_last_vosr2_timing()["tiling"] == "tiled"


def test_vosr2_fails_closed_offline_without_prewarm(monkeypatch, tmp_path):
    # No staged cache, no knob content, no hub content -> explicit
    # VOSR2_UNAVAILABLE (and, by construction, no network attempt: the
    # module has no socket surface at all).
    calls: list = []
    repo, weights = _write_fake_vosr2_bundle(tmp_path, with_dinov2=False)
    for name, mod in _build_vosr2_stubs(calls).items():
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.setenv("COMFYMODAL_VOSR2_WEIGHTS", str(weights))
    monkeypatch.setenv("COMFYMODAL_VOSR2_REPO", str(repo))
    for knob in (
        "COMFYMODAL_VOSR2_DINOV2",
        "COMFYMODAL_VOSR2_DINOV2_PATH",
        "COMFYMODAL_VOSR2_TORCH_HUB",
        "COMFYMODAL_VOSR2_SNAPSHOT_MODE",
    ):
        monkeypatch.delenv(knob, raising=False)
    monkeypatch.setenv("TORCH_HUB_DIR", str(tmp_path / "empty_hub"))
    _reset_vosr2_state()
    try:
        with pytest.raises(VOSR2Unavailable) as caught:
            vosr2_static_init()
        assert "VOSR2_UNAVAILABLE" in str(caught.value)
        assert "dinov2" in str(caught.value).lower()
    finally:
        _reset_vosr2_state()


def test_vosr2_lifecycle_arg_validation_and_missing_weights(
    monkeypatch, tmp_path
):
    # snap= flags are contracts, not hints; missing bundles fail closed
    # before any heavy work.
    _reset_vosr2_state()
    try:
        with pytest.raises(VOSR2Unavailable):
            vosr2_restore()  # before static init
        with pytest.raises(VOSR2Unavailable):
            vosr2_static_init(snap=False)
        with pytest.raises(VOSR2Unavailable):
            vosr2_restore(snap=True)
        empty = tmp_path / "empty_weights"
        empty.mkdir()
        monkeypatch.setenv("COMFYMODAL_VOSR2_WEIGHTS", str(empty))
        monkeypatch.delenv("COMFYMODAL_VOSR2_SNAPSHOT_MODE", raising=False)
        with pytest.raises(VOSR2Unavailable) as caught:
            vosr2_static_init()
        assert "VOSR2_UNAVAILABLE" in str(caught.value)
        assert "args.json" in str(caught.value)
    finally:
        _reset_vosr2_state()


def test_modal_true_cold_lifecycle_wiring():
    # Snapshot lifecycle mirrors Golden: enabling param on the serving
    # function, startup(snap=True) -> static init, restore(snap=False) ->
    # CUDA/H2D, additive vosr2_timing in the ok response.  Dispatch and the
    # remote payload schema are untouched.
    text = (ROOT / "studio_upscale_modal.py").read_text(encoding="utf-8")
    assert "enable_memory_snapshot=True" in text
    assert "def startup(snap: bool = True)" in text
    assert "def restore(snap: bool = False)" in text
    assert "vosr2_static_init" in text and "vosr2_restore" in text
    assert '"vosr2_timing"' in text and '"png_encode_ms"' in text
    assert "NO Modal GPU" in text or "NOT GPU" in text
    # Remote contract stable: same entrypoint, same ok keys.
    assert "def studio_upscale(payload: dict)" in text
    assert '"status": "ok"' in text and '"image_b64"' in text
    run_text = (ROOT / "studio_upscale_run.py").read_text(encoding="utf-8")
    assert "vosr2_timing" not in run_text
    seed_text = (ROOT / "studio_upscale_seedvr2.py").read_text(encoding="utf-8")
    assert "vosr2" not in seed_text.lower()  # SeedVR2 shares nothing
