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

from pathlib import Path

import pytest

import studio_upscale_deps as deps
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
    VOSR2_METHOD,
    VOSR2Unavailable,
    upscale_vosr2,
    validate_vosr2_scale,
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
