"""Experiment 1 (``unet_transfer``, B arm): bounded pinned-staging chunked
host→device transfer for a torch module.

Replaces the driver's pageable-staging H2D path with ONE reused pinned bounce
buffer of at most ``chunk_mb`` MiB, copying each CPU parameter/buffer in
byte-aligned chunks: pageable→pinned (host copy), then pinned→device (async,
non-blocking) on a single lazily-created dedicated staging stream.

Default OFF: the caller (``model_preload._fast_disk_replay_to``) only invokes
this module when the ``unet_transfer`` experiment resolves to the
``pinned_staging`` arm; otherwise the original ``module.to(...)`` path runs
byte-for-byte.  No dtype conversion is performed here — the caller guarantees
no ``dtype``/``memory_format`` conversion is requested, so raw-byte copies are
always value-exact.

On ANY abort the module is left EXACTLY as it was: the only mutation is the
final ``t.data = gpu`` rebind loop, and if an exception interrupts that loop
the already-bound tensors are restored to their original (CPU) storage.
"""

from __future__ import annotations

from typing import Any

# Single source of truth for the copy-API label reported in the metrics dict
# (mirrored by ``model_preload``'s OptTransferProbe metadata on the B path).
COPY_API_LABEL = "pinned_staging_chunked_copy_"

# Lazily-created dedicated staging stream.  Created on first use (only when
# CUDA is available); the stream's priority is reported in the metrics.
_STAGING_STREAM: Any = None


def _staging_stream() -> Any:
    """Return the process-singleton dedicated staging stream (lazy-init)."""
    global _STAGING_STREAM
    if _STAGING_STREAM is None:
        import torch as _torch_st
        _STAGING_STREAM = _torch_st.cuda.Stream()
    return _STAGING_STREAM


def transfer_module_via_pinned_staging(
    module: Any,
    *,
    target_device: Any,
    chunk_mb: int = 512,
    trace: Any = None,
    phase: str = "restore",
) -> dict[str, Any]:
    """Transfer *module*'s CPU parameters/buffers to *target_device* using a
    bounded pinned-staging chunked copy.

    Parameters
    ----------
    module:
        Any ``torch.nn.Module``-like object exposing ``parameters()`` and
        ``buffers()``.  CPU tensors are copied value/byte-exactly to
        *target_device*; tensors already on a CUDA device are skipped.
    target_device:
        Destination CUDA device.
    chunk_mb:
        Bounded pinned staging size in MiB (one reused buffer).
    trace / phase:
        Reserved for interface symmetry with the caller; the caller is
        responsible for emitting its own trace events.

    Returns a metrics dict (all keys always present):

    - ``copy_api``              = ``"pinned_staging_chunked_copy_"``
    - ``non_blocking``          = True
    - ``stream``                = str of the staging stream (or "")
    - ``stream_priority``       = int stream priority
    - ``source_pinned_fraction``= 0.0 (pageable source by design)
    - ``staging_alloc_bytes``   = pinned buffer size in bytes
    - ``peak_staging_bytes``    = same (one reused buffer)
    - ``chunk_mb``              = the requested chunk size in MiB
    - ``chunk_count``           = total byte-chunks copied
    - ``copied_params``         = parameters moved
    - ``copied_buffers``        = buffers moved
    - ``total_bytes``           = total bytes copied
    - ``h2d_cpu_wall_ms``       = monotonic wall time around the transfer
    - ``cuda_event_ms``         = CUDA-event elapsed time (or None)
    - ``gbps``                  = throughput in GiB/s (or None)
    - ``fallback``              = None | "cuda_unavailable" |
      "non_contiguous_tensor" | "exception:<ExcType>"
    - ``error``                 = truncated error text ("" when none)
    """
    import time as _time
    import torch as _torch

    _pin_bytes = max(1, int(chunk_mb or 1)) * 1024 * 1024
    _wall_start_ns = _time.monotonic_ns()
    _metrics: dict[str, Any] = {
        "copy_api": COPY_API_LABEL,
        "non_blocking": True,
        "stream": "",
        "stream_priority": 0,
        "source_pinned_fraction": 0.0,
        "staging_alloc_bytes": _pin_bytes,
        "peak_staging_bytes": _pin_bytes,
        "chunk_mb": int(chunk_mb or 1),
        "chunk_count": 0,
        "copied_params": 0,
        "copied_buffers": 0,
        "total_bytes": 0,
        "h2d_cpu_wall_ms": 0.0,
        "cuda_event_ms": None,
        "gbps": None,
        "fallback": None,
        "error": "",
    }

    def _finish(metrics: dict[str, Any]) -> dict[str, Any]:
        metrics["h2d_cpu_wall_ms"] = round(
            (_time.monotonic_ns() - _wall_start_ns) / 1_000_000, 3
        )
        return metrics

    try:
        if not _torch.cuda.is_available():
            _metrics["fallback"] = "cuda_unavailable"
            return _finish(_metrics)
        _stream = _staging_stream()
        _metrics["stream"] = str(_stream)
        _metrics["stream_priority"] = int(getattr(_stream, "priority", 0) or 0)

        # ── Eligibility pass (before ANY copy so an abort leaves no partial
        # transfer): parameters first, then buffers.  A module that cannot
        # enumerate its tensors aborts with an exception fallback. ──
        _pairs: list[tuple[str, Any]] = []
        _pairs.extend(("param", _t) for _t in (module.parameters() or ()))
        _pairs.extend(("buffer", _t) for _t in (module.buffers() or ()))
        _eligible: list[tuple[str, Any]] = []
        for _kind, _t in _pairs:
            if getattr(_t, "device", _torch.device("cpu")).type == "cuda":
                continue
            _is_contig = getattr(_t, "is_contiguous", None)
            if not bool(_is_contig() if callable(_is_contig) else True):
                _metrics["fallback"] = "non_contiguous_tensor"
                return _finish(_metrics)
            _eligible.append((_kind, _t))

        _pin = _torch.empty(_pin_bytes, dtype=_torch.uint8, pin_memory=True)
        _ev_start = _torch.cuda.Event(enable_timing=True)
        _ev_end = _torch.cuda.Event(enable_timing=True)
        _pending: list[tuple[Any, Any]] = []  # (tensor, gpu_tensor)
        _bound: list[tuple[Any, Any]] = []    # (tensor, original_view) for restore
        try:
            with _torch.cuda.stream(_stream):
                _ev_start.record(_stream)
                for _kind, _t in _eligible:
                    _flat = _t.detach().reshape(-1)
                    _esz = int(_t.element_size())
                    _nbytes = int(_flat.numel()) * _esz
                    _gpu = _torch.empty(_flat.shape, dtype=_t.dtype, device=target_device)
                    _src_view = _flat.view(_torch.uint8)
                    _dst_view = _gpu.view(_torch.uint8)
                    for _off in range(0, _nbytes, _pin_bytes):
                        _n = min(_pin_bytes, _nbytes - _off)
                        # pageable → pinned (host copy, synchronous)
                        _pin[:_n].copy_(_src_view[_off:_off + _n])
                        # pinned → device (async on the staging stream)
                        _dst_view[_off:_off + _n].copy_(_pin[:_n], non_blocking=True)
                        _metrics["chunk_count"] += 1
                        # Single-buffer safety barrier: the ONE pinned buffer
                        # is reused for the NEXT chunk's pageable→pinned host
                        # copy (also across tensor boundaries), so the host
                        # must wait for the just-enqueued async pinned→device
                        # copy to consume it first — otherwise the DMA and the
                        # next memcpy race on the same host memory.
                        _stream.synchronize()
                    _metrics["total_bytes"] += _nbytes
                    if _kind == "param":
                        _metrics["copied_params"] += 1
                    else:
                        _metrics["copied_buffers"] += 1
                    _pending.append((_t, _gpu))
                _ev_end.record(_stream)
            # Order the default stream after the staging stream, then the
            # single synchronize that also realizes the CUDA-event timing.
            _torch.cuda.current_stream().wait_stream(_stream)
            _torch.cuda.synchronize()
            _device_ms = round(float(_ev_start.elapsed_time(_ev_end)), 3)
            _metrics["cuda_event_ms"] = _device_ms
            if _device_ms > 0:
                _metrics["gbps"] = round(
                    (_metrics["total_bytes"] / (1024.0 ** 3)) / (_device_ms / 1000.0), 3
                )
        except Exception as _exc:
            # Mid-transfer exception: nothing has been bound yet (the bind
            # loop below is the ONLY module mutation) — module unchanged.
            _metrics["fallback"] = "exception:" + type(_exc).__name__
            _metrics["error"] = str(_exc)[:200]
            print(f"[unet_pinned_staging] error={_metrics['error']}", flush=True)
            return _finish(_metrics)
        # ── Final bind — the ONLY module mutation.  Restore-on-abort. ──
        try:
            for _t, _gpu in _pending:
                _original = _t.detach()
                _t.data = _gpu.reshape(_t.shape)
                _bound.append((_t, _original))
        except Exception as _exc:
            for _t, _original in _bound:
                try:
                    _t.data = _original
                except Exception:
                    pass
            _metrics["fallback"] = "exception:" + type(_exc).__name__
            _metrics["error"] = str(_exc)[:200]
            print(f"[unet_pinned_staging] error={_metrics['error']}", flush=True)
            return _finish(_metrics)
        return _finish(_metrics)
    except Exception as _exc:
        _metrics["fallback"] = "exception:" + type(_exc).__name__
        _metrics["error"] = str(_exc)[:200]
        print(f"[unet_pinned_staging] error={_metrics['error']}", flush=True)
        return _finish(_metrics)
