"""Focused tests for the V2 A/B experiment framework.

Covers the unified experiment registry (``comfymodal_runtime.v2_experiments``)
and the per-experiment implementations that consume it:

1. default arms / selectors with no env set
2. the env -> arm selection matrix for every experiment
3. explicit invalid-arm diagnostics (ERROR lines + safe fallback)
4. the chunk-mb clamp bounds
5. the ``experiment_selection`` trace metadata contract
6. PNG compress-level equivalence (lossless at any level) + diag level
7. UNET pinned-staging chunked H2D transfer correctness (CUDA)
8. non-contiguous UNET fallback (module left untouched)
9. async LRU conditioning-cache coalescing / boundedness / failure independence
10. frozen-total-VRAM restore semantics

Every test cleans ``os.environ`` after itself via ``monkeypatch``.  No Modal
runs; nothing here launches a Modal app.
"""

from __future__ import annotations

import json
import os
import tempfile
import time

import pytest
import torch

from comfymodal_runtime.v2_experiments import (
    EXPERIMENT_SPECS,
    conditioning_async_lru_enabled,
    emit_experiment_selection,
    png_compress_level,
    resolve_all_experiments,
    resolve_experiment,
    restore_total_vram_frozen_enabled,
    unet_pinned_staging_enabled,
    unet_staging_chunk_mb,
    vae_early_start_ms,
    vae_expected_sampling_ms,
)

# Every experiment env key, so tests can guarantee a clean default state.
_V2_ENV_KEYS = (
    "COMFYMODAL_V2_UNET_PINNED_STAGING",
    "COMFYMODAL_V2_UNET_STAGING_CHUNK_MB",
    "COMFYMODAL_V2_VAE_EARLY_START_MS",
    "COMFYMODAL_V2_VAE_EXPECTED_SAMPLING_MS",
    "COMFYMODAL_V2_PNG_COMPRESS_LEVEL",
    "COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU",
    "COMFYMODAL_V2_RESTORE_TOTAL_VRAM_FROZEN",
)


def _clear_v2_env(monkeypatch) -> None:
    for key in _V2_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


# ── 1. Defaults ─────────────────────────────────────────────────────────────
def test_all_experiments_default_off(monkeypatch):
    """No env set: all five experiments resolve to their baseline arm, the
    effective settings carry the documented defaults, and the selectors are
    4 request-selectable + 1 deployment-selectable."""
    _clear_v2_env(monkeypatch)

    expected = {
        "unet_transfer": ("baseline", {"pinned_staging": False, "chunk_mb": 512}),
        "vae_overlap": ("baseline", {"early_start_ms": 0, "expected_sampling_ms": 4900}),
        "png_encode": ("level1", {"compress_level": 1}),
        "conditioning_hit": ("sync_lru", {"async_lru": False}),
        "restore_memory": ("baseline", {"total_vram_frozen": False}),
    }
    selections = resolve_all_experiments()
    assert set(selections) == set(EXPERIMENT_SPECS)
    for name, (arm, settings) in expected.items():
        sel = selections[name]
        assert sel.name == name
        assert sel.arm == arm, f"{name}: {sel.arm} != {arm}"
        assert dict(sel.effective_settings) == settings
        assert sel.implementation_version == "1"
        assert sel.source == "default"

    assert selections["unet_transfer"].selector == "request"
    assert selections["vae_overlap"].selector == "request"
    assert selections["png_encode"].selector == "request"
    assert selections["conditioning_hit"].selector == "request"
    assert selections["restore_memory"].selector == "deployment"
    assert sum(1 for s in selections.values() if s.selector == "request") == 4
    assert sum(1 for s in selections.values() if s.selector == "deployment") == 1

    # Accessors agree with the resolved selections.
    assert unet_pinned_staging_enabled() is False
    assert unet_staging_chunk_mb() == 512
    assert vae_early_start_ms() == 0
    assert vae_expected_sampling_ms() == 4900
    assert png_compress_level() == 1
    assert conditioning_async_lru_enabled() is False
    assert restore_total_vram_frozen_enabled() is False


# ── 2. Arm selection matrix ────────────────────────────────────────────────
def test_arm_selection_matrix(monkeypatch):
    """Each env key flips its experiment to the documented arm."""
    _clear_v2_env(monkeypatch)

    monkeypatch.setenv("COMFYMODAL_V2_UNET_PINNED_STAGING", "1")
    sel = resolve_experiment("unet_transfer")
    assert sel.arm == "pinned_staging"
    assert sel.effective_settings["pinned_staging"] is True

    monkeypatch.setenv("COMFYMODAL_V2_UNET_PINNED_STAGING", "0")
    assert resolve_experiment("unet_transfer").arm == "baseline"

    for value, expected_arm in (
        (250, "early_250"), (500, "early_500"), (750, "early_750"), (1000, "early_1000"),
    ):
        monkeypatch.setenv("COMFYMODAL_V2_VAE_EARLY_START_MS", str(value))
        sel = resolve_experiment("vae_overlap")
        assert sel.arm == expected_arm, f"early {value} -> {sel.arm}"
        assert sel.effective_settings["early_start_ms"] == value

    monkeypatch.setenv("COMFYMODAL_V2_VAE_EARLY_START_MS", "0")
    sel = resolve_experiment("vae_overlap")
    assert sel.arm == "baseline"
    assert sel.effective_settings["early_start_ms"] == 0

    monkeypatch.setenv("COMFYMODAL_V2_PNG_COMPRESS_LEVEL", "1")
    assert resolve_experiment("png_encode").arm == "level1"
    monkeypatch.setenv("COMFYMODAL_V2_PNG_COMPRESS_LEVEL", "6")
    assert resolve_experiment("png_encode").arm == "level6"

    monkeypatch.setenv("COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU", "1")
    sel = resolve_experiment("conditioning_hit")
    assert sel.arm == "async_lru"
    assert sel.effective_settings["async_lru"] is True

    monkeypatch.setenv("COMFYMODAL_V2_RESTORE_TOTAL_VRAM_FROZEN", "1")
    sel = resolve_experiment("restore_memory")
    assert sel.arm == "optimized"
    assert sel.effective_settings["total_vram_frozen"] is True


# ── 3. Invalid arms fail explicitly ────────────────────────────────────────
def test_invalid_arm_fails_explicitly(monkeypatch, capsys):
    """Invalid env values fall back to the default arm and print a
    ``[v2.experiment] ERROR invalid_arm`` line carrying the raw value."""
    _clear_v2_env(monkeypatch)

    monkeypatch.setenv("COMFYMODAL_V2_PNG_COMPRESS_LEVEL", "3")
    sel = resolve_experiment("png_encode")
    out = capsys.readouterr().out
    assert sel.arm == "level1"
    assert sel.effective_settings["compress_level"] == 1
    assert "[v2.experiment] ERROR invalid_arm" in out
    assert "env_key=COMFYMODAL_V2_PNG_COMPRESS_LEVEL" in out
    assert "value='3'" in out

    monkeypatch.setenv("COMFYMODAL_V2_VAE_EARLY_START_MS", "123")
    sel = resolve_experiment("vae_overlap")
    out = capsys.readouterr().out
    assert sel.arm == "baseline"
    assert sel.effective_settings["early_start_ms"] == 0
    assert "[v2.experiment] ERROR invalid_arm" in out
    assert "value='123'" in out

    monkeypatch.setenv("COMFYMODAL_V2_VAE_EARLY_START_MS", "abc")
    sel = resolve_experiment("vae_overlap")
    out = capsys.readouterr().out
    assert sel.arm == "baseline"
    assert sel.effective_settings["early_start_ms"] == 0
    assert "[v2.experiment] ERROR invalid_arm" in out
    assert "value='abc'" in out

    # Source is still "env" (the key WAS present, even though it was invalid).
    assert sel.source == "env"


# ── 4. Chunk-mb clamp ──────────────────────────────────────────────────────
def test_chunk_mb_clamp(monkeypatch):
    """COMFYMODAL_V2_UNET_STAGING_CHUNK_MB clamps to 16..8192, default 512."""
    _clear_v2_env(monkeypatch)
    assert unet_staging_chunk_mb() == 512

    monkeypatch.setenv("COMFYMODAL_V2_UNET_STAGING_CHUNK_MB", "99999")
    assert unet_staging_chunk_mb() == 8192

    monkeypatch.setenv("COMFYMODAL_V2_UNET_STAGING_CHUNK_MB", "4")
    assert unet_staging_chunk_mb() == 16

    monkeypatch.delenv("COMFYMODAL_V2_UNET_STAGING_CHUNK_MB")
    assert unet_staging_chunk_mb() == 512


# ── 5. experiment_selection metadata event ─────────────────────────────────
class _FakeTrace:
    """Minimal recorder matching the RuntimeTrace.emit contract."""

    def __init__(self, request_id: str = "req-123") -> None:
        self.request_id = request_id
        self.events = []

    def emit(self, name: str, *, phase: str = "execution", metadata=None):
        self.events.append({"name": name, "phase": phase, "metadata": dict(metadata or {})})
        return self.events[-1]


def test_experiment_selection_metadata_event(monkeypatch):
    """emit_experiment_selection emits an ``experiment_selection`` trace event
    with the full metadata contract and the resolved arm."""
    _clear_v2_env(monkeypatch)
    monkeypatch.setenv("COMFYMODAL_V2_PNG_COMPRESS_LEVEL", "1")

    trace = _FakeTrace()
    selection = resolve_experiment("png_encode")
    assert selection.arm == "level1"

    emit_experiment_selection(trace, selection)
    assert trace.events
    event = trace.events[-1]
    assert event["name"] == "experiment_selection"
    assert event["phase"] == "execution"
    meta = event["metadata"]
    for key in (
        "experiment_name", "arm", "effective_settings",
        "implementation_version", "selector", "source",
    ):
        assert key in meta, f"missing metadata key {key!r}"
    assert meta["experiment_name"] == "png_encode"
    assert meta["arm"] == "level1"
    assert meta["implementation_version"] == "1"
    assert meta["selector"] == "request"
    assert meta["source"] == "env"
    assert meta["effective_settings"]["compress_level"] == 1


# ── 6. PNG compress-level equivalence ──────────────────────────────────────
def _gradient_image():
    """Deterministic 64x48 RGB gradient as a [1, H, W, C] uint8 tensor."""
    h, w = 48, 64
    x = torch.linspace(0, 255, w).repeat(h, 1)
    y = torch.linspace(0, 255, h).repeat(w, 1).t()
    r = x.round().to(torch.uint8)
    g = y.round().to(torch.uint8)
    b = ((x + y) % 256).round().to(torch.uint8)
    arr = torch.stack([r, g, b], dim=-1)  # [H, W, C]
    return arr.unsqueeze(0).contiguous()  # [1, H, W, C]


def _decode_png(raw: bytes):
    from io import BytesIO
    from PIL import Image

    return Image.open(BytesIO(raw))


def test_png_level_equivalence(monkeypatch):
    """PNG is lossless at every compress level: level 6 and level 1 encodings
    of the same image decode to byte-identical pixels, and the diagnostics
    record the actual level used."""
    import io

    tensor = _gradient_image()
    expected_size = (tensor.shape[2], tensor.shape[1])  # PIL reports (W, H)

    try:
        import comfyapp
    except Exception as exc:  # pragma: no cover - comfyapp is importable here
        # Fallback: prove PIL-level equivalence with the same arguments.
        from PIL import Image

        arr = tensor[0].numpy()
        pil = Image.fromarray(arr, mode="RGB")

        def _encode(level: int) -> bytes:
            buf = io.BytesIO()
            pil.save(buf, format="PNG", compress_level=level)
            return buf.getvalue()

        raw6, raw1 = _encode(6), _encode(1)
        assert raw6.startswith(b"\x89PNG")
        assert raw1.startswith(b"\x89PNG")
        img6, img1 = _decode_png(raw6), _decode_png(raw1)
        assert img6.size == img1.size == expected_size
        assert img6.mode == img1.mode == "RGB"
        assert img6.tobytes() == img1.tobytes()
        pytest.skip(f"comfyapp import unavailable ({exc!r}); PIL-direct equivalence only")
        return

    monkeypatch.setattr(comfyapp, "_opt_diag_enabled", lambda: True)
    monkeypatch.delenv("COMFYMODAL_V2_PNG_COMPRESS_LEVEL", raising=False)

    # Level 6 (non-default; explicit override).
    monkeypatch.setenv("COMFYMODAL_V2_PNG_COMPRESS_LEVEL", "6")
    comfyapp._PNG_EXPERIMENT_LOGGED = False
    comfyapp._OPT_ENCODE_DIAG.clear()
    entries6, ext6, mime6, w6, h6 = comfyapp.encode_image_tensor_batch(tensor, "original")
    diag6 = dict(comfyapp._OPT_ENCODE_DIAG[-1])
    raw6 = entries6[0][0]
    size6 = len(raw6)

    # Level 1 (default).
    monkeypatch.setenv("COMFYMODAL_V2_PNG_COMPRESS_LEVEL", "1")
    comfyapp._PNG_EXPERIMENT_LOGGED = False
    comfyapp._OPT_ENCODE_DIAG.clear()
    entries1, ext1, mime1, w1, h1 = comfyapp.encode_image_tensor_batch(tensor, "original")
    diag1 = dict(comfyapp._OPT_ENCODE_DIAG[-1])
    raw1 = entries1[0][0]
    size1 = len(raw1)

    assert len(entries6) == len(entries1) == 1
    assert (ext6, ext1) == (".png", ".png")
    assert (mime6, mime1) == ("image/png", "image/png")
    assert (w6, h6) == (tensor.shape[2], tensor.shape[1])
    assert raw6.startswith(b"\x89PNG")
    assert raw1.startswith(b"\x89PNG")

    img6 = _decode_png(raw6)
    img1 = _decode_png(raw1)
    assert img6.size == img1.size == expected_size
    assert img6.mode == img1.mode == "RGB"
    assert img6.tobytes() == img1.tobytes()

    # Diagnostics report the actual compress level per call.
    assert diag6["compress_level"] == 6
    assert diag1["compress_level"] == 1
    # Record the sizes so a run-to-run comparison is available in the log.
    print(f"[png_equivalence] level6_bytes={size6} level1_bytes={size1}")


# ── 7. UNET pinned-staging transfer correctness (CUDA) ─────────────────────
@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA is required")
def test_unet_staging_transfer_correctness():
    """A mixed-size module transfers byte-exactly to CUDA through the bounded
    pinned staging buffer; the metrics report the copy shape."""
    from comfymodal_runtime.unet_pinned_staging import transfer_module_via_pinned_staging

    module = torch.nn.Module()
    module.big = torch.nn.Parameter(torch.randn(1024, 512))      # 2 MiB float32
    module.small = torch.nn.Parameter(torch.randn(64, 64))       # 16 KiB
    module.register_buffer("buf", torch.zeros(256))              # 1 KiB
    expected_params = 2
    expected_buffers = 1
    originals = {name: param.detach().cpu().clone() for name, param in module.named_parameters()}
    original_buf = module.buf.detach().cpu().clone()

    metrics = transfer_module_via_pinned_staging(
        module, target_device=torch.device("cuda"), chunk_mb=1
    )

    assert metrics["fallback"] is None, metrics
    assert metrics["error"] == ""
    assert metrics["staging_alloc_bytes"] == 1024 * 1024
    assert metrics["peak_staging_bytes"] == 1024 * 1024
    assert metrics["chunk_mb"] == 1
    assert metrics["chunk_count"] >= 2
    assert metrics["copied_params"] == expected_params
    assert metrics["copied_buffers"] == expected_buffers
    assert metrics["total_bytes"] == 1024 * 512 * 4 + 64 * 64 * 4 + 256 * 4
    assert metrics["source_pinned_fraction"] == 0.0
    for key in ("copy_api", "non_blocking", "stream", "stream_priority",
                "gbps", "cuda_event_ms", "h2d_cpu_wall_ms"):
        assert key in metrics, f"missing metric {key!r}"
    assert metrics["copy_api"].startswith("pinned_staging_chunked_copy_")
    assert metrics["non_blocking"] is True

    # The module is fully bound to CUDA with dtype preserved.
    assert module.big.device.type == "cuda"
    assert module.small.device.type == "cuda"
    assert module.buf.device.type == "cuda"
    assert module.big.dtype == torch.float32
    assert module.small.dtype == torch.float32
    assert module.buf.dtype == torch.float32
    # Values are byte-identical to the original CPU tensors.
    assert torch.equal(module.big.detach().cpu(), originals["big"])
    assert torch.equal(module.small.detach().cpu(), originals["small"])
    assert torch.equal(module.buf.detach().cpu(), original_buf)


# ── 8. UNET non-contiguous fallback ────────────────────────────────────────
@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA is required")
def test_unet_staging_non_contiguous_fallback():
    """A non-contiguous parameter aborts to ``non_contiguous_tensor`` before
    ANY copy, leaving the module untouched on CPU."""
    from comfymodal_runtime.unet_pinned_staging import transfer_module_via_pinned_staging

    module = torch.nn.Module()
    module.t = torch.nn.Parameter(torch.randn(16, 8).t())  # shape (8,16), non-contiguous
    original = module.t.detach().cpu().clone()

    metrics = transfer_module_via_pinned_staging(
        module, target_device=torch.device("cuda"), chunk_mb=1
    )

    assert metrics["fallback"] == "non_contiguous_tensor"
    assert metrics["copied_params"] == 0
    assert metrics["copied_buffers"] == 0
    assert metrics["total_bytes"] == 0
    # Module unchanged: still CPU, same values, same dtype.
    assert module.t.device.type == "cpu"
    assert module.t.dtype == torch.float32
    assert torch.equal(module.t.detach().cpu(), original)


# ── 9. Async LRU conditioning-cache semantics ──────────────────────────────
def _base_ctx(text: str = "a cat", *, workflow_hash: str = "wf1", **overrides) -> dict:
    ctx = {
        "request_id": "v2-ab-req",
        "clip_identity": "clip.safetensors",
        "clip_type": "flux",
        "loader_class": "CLIPLoader",
        "filenames": ["clip.safetensors"],
        "weight_dtype": "bf16",
        "compute_dtype": "bfloat16",
        "torch_version": torch.__version__,
        "torch_num_threads": 4,
        "model_generation": "gen1",
        "workflow_hash": workflow_hash,
        "deployment_hash": "dep1",
        "custom_node_generation": "cn1",
        "production_options_hash": "po1",
        "tokenizer_identity": "tok1",
    }
    ctx.update(overrides)
    return ctx


def _entry(text: str = "a cat", role: str = "positive") -> dict:
    return {"text": text, "role": role, "node_class": "CLIPTextEncode", "prompt_input": "text"}


def _value(rows: int = 64, dim: int = 64):
    return [[torch.randn(rows, dim), {"pooled": torch.randn(1, dim)}]]


def _wait_until(predicate, timeout: float = 10.0, interval: float = 0.01) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class _FakeLruWorker:
    """Stand-in for the LRU background thread: keeps the async path 'alive'
    so queued touches stay queued (no sync fallback) and flush drains them."""

    def is_alive(self) -> bool:
        return True

    def join(self, timeout=None) -> None:
        return None


def _make_cache(root: str, monkeypatch, **env):
    """Construct an ExactConditioningCache with the async LRU arm on and the
    requested env (MAX_LRU_QUEUE etc.) applied before construction."""
    from comfymodal_runtime.clip_conditioning_cache import ExactConditioningCache

    monkeypatch.setenv("COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU", "1")
    monkeypatch.setenv("COMFYMODAL_EXACT_CLIP_CONDITIONING_CACHE_ROOT", root)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return ExactConditioningCache(root_dir=root, max_entries=64, max_bytes=1 << 30, mounted=False)


def test_cache_lru_async_bounded_and_coalesced(monkeypatch):
    """Async LRU touches dedup, coalesce into ONE manifest rewrite drained by
    flush, bump recency on disk, report async mode, drop beyond the queue
    bound without raising, and swallow manifest-write failures."""
    from comfymodal_runtime.clip_conditioning_cache import ExactConditioningCache

    _clear_v2_env(monkeypatch)
    monkeypatch.delenv("COMFYMODAL_EXACT_CLIP_CONDITIONING_CACHE_MAX_LRU_QUEUE", raising=False)

    # ── (a) Dedup + one coalesced batch + flush drain ─────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        cache = _make_cache(tmp, monkeypatch)
        # Fake worker: no background thread racing the assertions; the async
        # enqueue/flush machinery is exercised deterministically.
        monkeypatch.setattr(cache, "_ensure_lru_worker", lambda: None)
        monkeypatch.setattr(cache, "_lru_worker", _FakeLruWorker())

        # Seed a manifest so the touched digests exist and can be bumped.
        cache._write_manifest_atomic({
            "schema_version": 1,
            "format_version": 1,
            "next_seq": 0,
            "entries": [
                {"key_hash": "aaa", "byte_length": 10, "last_access_seq": 0, "created_at": 1.0},
                {"key_hash": "bbb", "byte_length": 10, "last_access_seq": 0, "created_at": 1.0},
            ],
        })

        with cache._lock:
            cache._enqueue_lru_touch({"aaa", "bbb"})
            cache._enqueue_lru_touch({"aaa"})  # overlap -> dedup
            diag_before = cache.latest_lookup_diagnostics()
            assert diag_before["lru_async_enqueued"] == 2, diag_before
            cache.flush(timeout=5)

        diag = cache.latest_lookup_diagnostics()
        assert diag["lru_async_enqueued"] == 2, diag
        assert diag["lru_async_batches"] == 1, diag      # coalesced into one rewrite
        assert diag["lru_async_batch_size"] == 2, diag
        assert diag["lru_async_flush_count"] == 1, diag
        manifest = cache._read_manifest()
        entries = {e["key_hash"]: e for e in manifest["entries"]}
        assert entries["aaa"]["last_access_seq"] == 1
        assert entries["bbb"]["last_access_seq"] == 2
        assert manifest["next_seq"] == 2

    # ── (b) Bounded queue: > max -> dropped, no exception ─────────────────
    with tempfile.TemporaryDirectory() as tmp:
        cache = _make_cache(tmp, monkeypatch, COMFYMODAL_EXACT_CLIP_CONDITIONING_CACHE_MAX_LRU_QUEUE="16")
        monkeypatch.setattr(cache, "_ensure_lru_worker", lambda: None)
        monkeypatch.setattr(cache, "_lru_worker", _FakeLruWorker())
        with cache._lock:
            cache._enqueue_lru_touch({f"d{i}" for i in range(24)})  # 24 > max 16
            cache.flush(timeout=5)
        diag = cache.latest_lookup_diagnostics()
        assert diag["lru_async_enqueued"] == 16, diag
        assert diag["lru_async_dropped"] == 8, diag
        assert diag["lru_async_failed"] == 0, diag

    # ── (c) Failure independence: manifest rewrite raises once ────────────
    with tempfile.TemporaryDirectory() as tmp:
        cache = _make_cache(tmp, monkeypatch)
        monkeypatch.setattr(cache, "_ensure_lru_worker", lambda: None)
        monkeypatch.setattr(cache, "_lru_worker", _FakeLruWorker())

        def _boom(*args, **kwargs):
            raise RuntimeError("simulated manifest write failure")

        with cache._lock:
            cache._enqueue_lru_touch({"aaa"})
            monkeypatch.setattr(cache, "_write_manifest_atomic", _boom)
            cache.flush(timeout=5)  # must not raise
        diag = cache.latest_lookup_diagnostics()
        assert diag["lru_async_failed"] >= 1, diag

    # ── (d) Real store -> hit cycle reports async lru_touch_mode ──────────
    with tempfile.TemporaryDirectory() as tmp:
        cache = _make_cache(tmp, monkeypatch)
        ctx, entry, value = _base_ctx("lru-mode"), _entry("lru-mode"), _value(64, 64)
        assert cache.store_entry(ctx, entry, value) is True
        assert _wait_until(lambda: cache._worker_diag.get("persisted", 0) >= 1), "entry never persisted"
        hits, misses, hc, mc = cache.lookup_many(ctx, [entry])
        assert (hc, mc) == (1, 0), (hc, mc)
        diag = cache.latest_lookup_diagnostics()
        assert diag.get("lru_touch_mode") == "async", diag
        assert diag.get("lru_async_enqueued", 0) >= 1, diag
        cache.flush(timeout=5)


# ── 10. Restore frozen-VRAM semantics ──────────────────────────────────────
def test_restore_frozen_vram_semantics(monkeypatch, tmp_path, capsys):
    """apply_frozen_total_vram_or_none returns the frozen value only when the
    arm is on AND the frozen capacity file is valid; every failure is None."""
    import comfymodal_runtime.restore_memory_arm as rma

    _clear_v2_env(monkeypatch)
    monkeypatch.setenv("COMFYMODAL_V2_STATE_VOLUME_ROOT", str(tmp_path))
    monkeypatch.setenv("COMFYMODAL_V2_RESTORE_STATE_FILE", "restore_state.json")
    monkeypatch.delenv("COMFYMODAL_V2_RESTORE_TOTAL_VRAM_FROZEN", raising=False)

    frozen_path = rma.frozen_capacity_path()
    assert frozen_path == os.path.join(str(tmp_path), "gpu_capacity_frozen.json")

    # Arm off -> None, no file access.
    assert rma.apply_frozen_total_vram_or_none() is None

    # Arm on, no file -> None + one fallback log line.
    monkeypatch.setenv("COMFYMODAL_V2_RESTORE_TOTAL_VRAM_FROZEN", "1")
    rma._APPLY_FALLBACK_LOGGED = False
    assert rma.apply_frozen_total_vram_or_none() is None
    out = capsys.readouterr().out
    assert "fallback=no_frozen_capacity" in out

    # Valid frozen capacity -> float MiB.
    with open(frozen_path, "w", encoding="utf-8") as f:
        json.dump({"total_vram_mib": 98304}, f)
    rma._APPLY_FALLBACK_LOGGED = False
    assert rma.apply_frozen_total_vram_or_none() == 98304.0

    # Corrupt JSON -> None.
    with open(frozen_path, "w", encoding="utf-8") as f:
        f.write("{not json")
    rma._APPLY_FALLBACK_LOGGED = False
    assert rma.apply_frozen_total_vram_or_none() is None

    # Wrong value type / non-positive -> None.
    with open(frozen_path, "w", encoding="utf-8") as f:
        json.dump({"total_vram_mib": "abc"}, f)
    rma._APPLY_FALLBACK_LOGGED = False
    assert rma.apply_frozen_total_vram_or_none() is None

    rma._APPLY_FALLBACK_LOGGED = False
