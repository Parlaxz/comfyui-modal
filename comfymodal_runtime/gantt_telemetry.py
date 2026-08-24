"""Precise ASCII Gantt telemetry for V2 critical-path forensics (Batch E27).

Target E: render every important remote span on ONE common monotonic axis
(``time.monotonic_ns()``) as solid ``█`` bars with exact numerical
start/end/duration.  This module is measurement/telemetry ONLY:

* everything is gated behind ``COMFYMODAL_V2_GANTT_TELEMETRY`` (default off)
  and additionally requires an active request trace (``_ACTIVE_REQUEST_TRACE``
  or ``_ACTIVE_LANE_TRACE`` from ``model_preload``) so it never runs outside a
  real request context;
* spans are collected in memory and rendered as ONE coherent multiline log
  record at request completion — no per-event prints on the critical path;
* the renderer never raises and never alters the generation path.

Clock discipline: all spans share the remote process monotonic clock.  Events
that cannot share that clock (platform scheduling) are NEVER drawn on the
remote axis; they may appear only in a separate PLATFORM header.

Span collection uses the existing paired ``<name>`` / ``<name>_end`` events on
the request ``RuntimeTrace`` (both carry ``monotonic_ns``) plus
``gantt_span`` records from ``register_gantt_span`` (for lanes whose work is
not represented by a request-trace event pair).  ``RuntimeTrace.emit`` already
enforces strictly increasing monotonic timestamps within a process, so spans
derived from trace events are ordered by construction.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Iterable, Mapping

from .env import env_flag

_GANTT_FLAG = "COMFYMODAL_V2_GANTT_TELEMETRY"

_ENABLED: bool = env_flag(_GANTT_FLAG, default=False)
"""Frozen at import time, matching the runtime convention."""

# ── Lane taxonomy (used by span records that carry an explicit lane) ──────
LANES: tuple[str, ...] = ("RESTORE", "MAIN", "STORAGE", "CPU", "GPU",
                          "MODEL-MGMT", "OUTPUT")

# Default lane assignment for span names (overridable per span).
_NAME_LANE_DEFAULTS: dict[str, str] = {
    # restore / method lifecycle
    "restore_entry": "RESTORE",
    "snap_false_entry": "RESTORE",
    "restore_reconcile": "RESTORE",
    "post_restore": "RESTORE",
    "cuda_init": "GPU",
    "cuda_readiness_start": "GPU",
    "cuda_readiness_complete": "GPU",
    "method_setup": "MAIN",
    "plan_deserialize": "MAIN",
    "graph_setup": "MAIN",
    "graph_start": "MAIN",
    "request_accept": "MAIN",
    # CLIP
    "clip_hydration": "STORAGE",
    "clip_source_read": "STORAGE",
    "clip_construct": "CPU",
    "clip_bind": "GPU",
    "clip_forward": "GPU",
    "clip_ready": "GPU",
    "clip_demand": "GPU",
    "clip_loader_setup": "STORAGE",
    "clip_cuda_copy": "GPU",
    "clip_speculative_future_created": "STORAGE",
    # UNET
    "unet_prefetch": "STORAGE",
    "unet_source_read": "STORAGE",
    "unet_construct": "CPU",
    "unet_h2d": "GPU",
    "unet_ready": "GPU",
    # sampling
    "sampler_setup": "GPU",
    "sampling": "GPU",
    # VAE / model management
    "vae_transition": "MODEL-MGMT",
    "vae_model_management": "MODEL-MGMT",
    "vae_model_activation": "MODEL-MGMT",
    "vae_h2d": "GPU",
    "vae_decode_prep": "GPU",
    "empty_cache": "MODEL-MGMT",
    "vae_decode": "GPU",
    # output
    "output_encode": "OUTPUT",
    "png_encode": "OUTPUT",
    "output_write": "OUTPUT",
    "result_emit": "OUTPUT",
}

# Point events (no duration) are rendered separately, never fabricated as spans.
_POINT_EVENT_SUFFIXES: tuple[str, ...] = ("_start", "_end", "_ready", "_done")


def gantt_enabled() -> bool:
    return _ENABLED


def lane_for(name: str) -> str:
    return _NAME_LANE_DEFAULTS.get(name, "MAIN")


# ── In-memory span registry (thread-safe, bounded) ────────────────────────
# A small bounded registry of explicit (start_ns, end_ns) spans contributed
# outside the request trace event stream.  This is the escape hatch for
# worker lanes (e.g. fastsafe worker A/B) that already publish forensic
# intervals via ``trace.register_forensic_interval`` — the renderer reads
# those too, so most callers need nothing here.

_LOCK = threading.Lock()
_EXTRA_SPANS: list[dict[str, Any]] = []
_MAX_EXTRA_SPANS = 512


def register_gantt_span(
    name: str,
    *,
    start_mono_ns: int,
    end_mono_ns: int,
    lane: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> None:
    """Register one explicit span on the remote monotonic axis.

    No-op when the gate is off.  Bounded: silently drops beyond
    ``_MAX_EXTRA_SPANS`` (never raises, never perturbs the critical path).
    """
    if not _ENABLED:
        return
    try:
        start_mono_ns = int(start_mono_ns)
        end_mono_ns = int(end_mono_ns)
        if end_mono_ns < start_mono_ns:
            end_mono_ns = start_mono_ns
        with _LOCK:
            if len(_EXTRA_SPANS) >= _MAX_EXTRA_SPANS:
                return
            _EXTRA_SPANS.append({
                "name": str(name),
                "start_mono_ns": start_mono_ns,
                "end_mono_ns": end_mono_ns,
                "lane": lane or lane_for(str(name)),
                "metadata": dict(metadata or {}),
            })
    except Exception:
        pass


# ── Span extraction from the request trace ────────────────────────────────

_TRACE_EVENT_SPANS = {
    # (start_event, end_event, display_name, lane)
    "restore_entry": ("restore_entry", "restore_entry_end", "restore", "RESTORE"),
    "snap_false_entry": ("snap_false_entry", "snap_false_entry_end",
                         "snap=False setup", "RESTORE"),
    "restore_reconcile": ("restore_reconcile", "restore_reconcile_end",
                          "restore reconcile", "RESTORE"),
    "post_restore": ("post_restore", "post_restore_end",
                     "post-restore", "RESTORE"),
    "cuda_init": ("cuda_init_start", "cuda_init_end", "CUDA init", "GPU"),
    "method_setup": ("method_setup_start", "method_setup_end",
                     "method/setup", "MAIN"),
    "plan_deserialize": ("plan_deserialize_start", "plan_deserialize_end",
                         "plan deserialize", "MAIN"),
    "graph_setup": ("graph_setup_start", "graph_setup_end",
                    "graph setup", "MAIN"),
    "clip_hydration": ("clip_fh_hydration_start", "clip_fh_hydration_end",
                       "CLIP hydration", "STORAGE"),
    "clip_hydration_gpu": ("clip_hydration_gpu_start",
                           "clip_hydration_gpu_end",
                           "CLIP GPU hydration", "GPU"),
    "clip_source_read": ("clip_source_read_start", "clip_source_read_end",
                         "CLIP source read", "STORAGE"),
    "clip_loader_setup": ("clip_loader_setup_start", "clip_loader_setup_end",
                          "CLIP loader setup", "STORAGE"),
    "clip_cuda_copy": ("clip_cuda_copy_start", "clip_cuda_copy_end",
                       "CLIP CUDA copy", "GPU"),
    "clip_construct": ("clip_construct_start", "clip_construct_end",
                       "CLIP construct", "CPU"),
    "clip_bind": ("clip_bind_wait_start", "clip_bind_wait_end",
                  "CLIP bind", "GPU"),
    "clip_forward": ("clip_forward_start", "clip_forward_end",
                     "CLIP forward", "GPU"),
    "unet_prefetch": ("unet_prefetch_start", "unet_prefetch_end",
                      "UNET prefetch", "STORAGE"),
    "unet_source_read": ("unet_source_read_start", "unet_source_read_end",
                         "UNET source read", "STORAGE"),
    "unet_construct": ("unet_construct_start", "unet_construct_end",
                       "UNET construct", "CPU"),
    "unet_h2d": ("unet_gpu_transfer_start", "unet_gpu_transfer_end",
                 "UNET H2D", "GPU"),
    "sampler_setup": ("sampler_setup_start", "sampler_setup_end",
                      "sampler setup", "GPU"),
    "sampling": ("sampling_start", "sampling_end", "sampling", "GPU"),
    "vae_transition": ("vae_transition_start", "vae_transition_end",
                       "VAE transition", "MODEL-MGMT"),
    "vae_model_management": ("vae_model_management_start",
                             "vae_model_management_end",
                             "VAE model-mgmt", "MODEL-MGMT"),
    "vae_model_activation": ("vae_model_activation_start",
                             "vae_model_activation_end",
                             "VAE model activation", "MODEL-MGMT"),
    "vae_h2d": ("vae_h2d_start", "vae_h2d_end", "VAE H2D", "GPU"),
    "vae_decode_prep": ("vae_decode_prep_start", "vae_decode_prep_end",
                        "VAE decode prep", "GPU"),
    "empty_cache": ("model_management_soft_empty_cache_start",
                    "model_management_soft_empty_cache_end",
                    "empty_cache", "MODEL-MGMT"),
    "vae_decode": ("vae_decode_start", "vae_decode_end", "VAE decode", "GPU"),
    "output_encode": ("output_encode_start", "output_encode_end",
                      "output encode", "OUTPUT"),
    "png_encode": ("png_encode_start", "png_encode_end", "PNG", "OUTPUT"),
    "output_write": ("output_write_start", "output_write_end",
                     "output write", "OUTPUT"),
    "result_emit": ("remote_result_emit_start", "remote_result_emit_end",
                    "result emit", "OUTPUT"),
}


# R44H2: printed adjacent to legacy Gantt output whenever the legacy
# "CLIP forward" span is present.  The span name is a persisted schema
# value (kept for backwards compatibility); its SEMANTICS are the OUTER
# encode wrapper, not the inner transformer forward.
_LEGACY_CLIP_FORWARD_WARNING = (
    'WARNING: LEGACY "CLIP forward" = outer encode wrapper '
    "(NOT the inner transformer forward);"
)
_LEGACY_CLIP_FORWARD_WARNING_2 = (
    "use DYNAMIC GANTT for inner transformer forward."
)


def _restore_spans_from_metadata(trace: Any) -> list[dict[str, Any]]:
    """Restore/method boundary spans reconstructed from trace metadata.

    The restore() method records ``restore_method_start_mono_ns`` /
    ``restore_method_end_mono_ns`` and the request path records
    ``modal_method_entry_mono_ns`` in trace metadata.  These share the same
    process monotonic clock, so they can be drawn on the remote axis.
    """
    out: list[dict[str, Any]] = []
    try:
        metadata = getattr(trace, "_metadata", None) or {}
        if not isinstance(metadata, Mapping):
            return out
        resume = metadata.get("remote_python_resume_mono_ns")
        restore_start = metadata.get("restore_method_start_mono_ns")
        restore_end = metadata.get("restore_method_end_mono_ns")
        method_entry = metadata.get("modal_method_entry_mono_ns")
        if isinstance(resume, int):
            out.append({
                "name": "remote python resume",
                "lane": "RESTORE",
                "start_mono_ns": int(resume),
                "end_mono_ns": int(resume),
                "duration_ms": 0.0,
                "point": True,
            })
        if isinstance(restore_start, int) and isinstance(restore_end, int):
            out.append({
                "name": "restore method",
                "lane": "RESTORE",
                "start_mono_ns": int(restore_start),
                "end_mono_ns": int(restore_end),
                "duration_ms": round(
                    (int(restore_end) - int(restore_start)) / 1_000_000, 3),
            })
        if isinstance(method_entry, int):
            out.append({
                "name": "method entry",
                "lane": "MAIN",
                "start_mono_ns": int(method_entry),
                "end_mono_ns": int(method_entry),
                "duration_ms": 0.0,
                "point": True,
            })
    except Exception:
        pass
    return out


def _collect_spans(trace: Any) -> list[dict[str, Any]]:
    """Collect spans from the trace event stream + the extra registry.

    A span is kept only when BOTH the start and end events exist (never
    fabricate a span from a point event).  Returns JSON-safe dicts ordered by
    start_mono_ns.  Never raises.
    """
    spans: dict[str, dict[str, Any]] = {}
    try:
        events = getattr(trace, "events", None)
        if events is not None:
            event_list = list(events)
            # Index every event's monotonic stamp by name (first occurrence).
            stamps: dict[str, int] = {}
            for event in event_list:
                name = getattr(event, "name", "")
                mono = getattr(event, "monotonic_ns", 0) or 0
                if not isinstance(name, str) or not name:
                    continue
                stamps.setdefault(name, int(mono))
            for key, (start_name, end_name, display, lane) in _TRACE_EVENT_SPANS.items():
                if start_name in stamps and end_name in stamps:
                    s, e = stamps[start_name], stamps[end_name]
                    if e >= s:
                        spans[key] = {
                            "name": display,
                            "lane": lane,
                            "start_mono_ns": s,
                            "end_mono_ns": e,
                            "duration_ms": round((e - s) / 1_000_000, 3),
                        }
    except Exception:
        spans = {}
    # Restore/method boundaries from trace metadata.
    for record in _restore_spans_from_metadata(trace):
        key = f"meta:{record['name']}"
        spans[key] = record
    # Extra registry spans (explicit, outside the trace stream).
    try:
        with _LOCK:
            extra = list(_EXTRA_SPANS)
        for record in extra:
            s, e = int(record["start_mono_ns"]), int(record["end_mono_ns"])
            key = f"extra:{record['name']}:{s}"
            spans[key] = {
                "name": str(record["name"]),
                "lane": str(record.get("lane") or lane_for(str(record["name"]))),
                "start_mono_ns": s,
                "end_mono_ns": e,
                "duration_ms": round((e - s) / 1_000_000, 3),
                "metadata": dict(record.get("metadata") or {}),
            }
    except Exception:
        pass
    ordered = sorted(spans.values(), key=lambda r: r["start_mono_ns"])
    return ordered


# ── Rendering ─────────────────────────────────────────────────────────────

_BLOCK = "\u2588"  # █ solid block
_TINY = "\u258f"  # ▏ tiny (sub-char) span / point
# Fixed physical width budgets (Target E hard requirement: no horizontal
# scroll in a normal log viewer; the bar region is ~55-75 chars).
_NAME_COL = 20
_BAR_COL = 64
_LABEL_COL = 10
_TOTAL_LINE_MAX = _NAME_COL + 1 + _BAR_COL + 1 + _LABEL_COL  # 96 chars


def _pick_scale_ms(spans: list[dict[str, Any]], max_chars: int = 120) -> float:
    """Pick ms/char so the longest span fits in *max_chars* columns."""
    longest = max(
        (float(s.get("duration_ms", 0.0)) for s in spans),
        default=0.0,
    )
    if longest <= 0:
        return 100.0
    return max(1.0, longest / max_chars)


def _fmt_dur(ms: float) -> str:
    """Compact duration formatting: <1 s -> ms, >=1 s -> s with 2-3 digits."""
    ms = max(0.0, float(ms))
    if ms < 1000.0:
        return f"{ms:.0f}ms" if ms >= 100 else f"{ms:.1f}ms"
    return f"{ms / 1000.0:.2f}s"


def _fmt_sec(offset_ms: float) -> str:
    sign = "-" if offset_ms < 0 else "+"
    return f"{sign}{abs(offset_ms) / 1000.0:.3f}s"


def _render_window(
    spans: list[dict[str, Any]],
    *,
    origin_ns: int,
    window_start_ns: int,
    window_end_ns: int,
    title: str,
    lane_order: tuple[str, ...] = LANES,
) -> list[str]:
    """Render one fixed-width Gantt window.

    * ``window_start_ns``..``window_end_ns`` is the local time range (all
      spans clipped to it; true relative positioning preserved).
    * The graph and the exact-number table are SEPARATE (Target E §8.2): the
      graph rows carry only the ``█`` bar + lane + duration; the precise
      start/end/duration values live in a compact table below the graph.
    * Physical line width is bounded (``_TOTAL_LINE_MAX`` ≈ 96 chars) — never
      one column per ~40 ms across a 20+ s request.
    * Tiny/point spans render as ``▏`` so sub-char work stays visible.
    """
    if not spans:
        return [f"{title}: no spans collected"]
    w_start = int(window_start_ns)
    w_end = int(window_end_ns)
    w_ms = max(1.0, (w_end - w_start) / 1_000_000.0)
    ms_per_char = max(1e-6, w_ms / _BAR_COL)
    lines: list[str] = []
    lines.append(
        f"{title}  window=+{(w_start - origin_ns) / 1e9:.3f}s..+{(w_end - origin_ns) / 1e9:.3f}s"
        f"  scale={ms_per_char:.1f} ms/char"
    )
    # Local ruler: ticks every 1 s (or a finer step when the window is short).
    tick_ms = 1000.0
    if w_ms <= 6000.0:
        tick_ms = 500.0
    if w_ms <= 2500.0:
        tick_ms = 250.0
    if w_ms <= 1200.0:
        tick_ms = 100.0
    tick_chars = max(1.0, tick_ms / ms_per_char)
    header = [" " * (_NAME_COL + 1)]
    prev_tick = -1
    for col in range(_BAR_COL + 1):
        tick_offset_ms = col * ms_per_char
        tick_i = int(tick_offset_ms // tick_ms)
        if tick_i > prev_tick:
            sec = (w_start - origin_ns + int(tick_offset_ms * 1_000_000)) / 1e9
            header.append(f"{sec:+.1f}s".ljust(int(tick_chars))[: int(tick_chars)])
            prev_tick = tick_i
    lines.append("".join(header).rstrip())
    lines.append(" " * (_NAME_COL + 1) + "|" + "-" * _BAR_COL)
    for lane in lane_order:
        for s in sorted(
            (x for x in spans if x.get("lane") == lane),
            key=lambda r: r["start_mono_ns"],
        ):
            start = int(s["start_mono_ns"])
            end = int(s["end_mono_ns"])
            if end < w_start or start > w_end:
                continue
            c_start = max(0, int((start - w_start) / 1_000_000.0 / ms_per_char))
            c_end = min(
                _BAR_COL,
                max(c_start, int((end - w_start) / 1_000_000.0 / ms_per_char)),
            )
            dur_ms = float(s.get("duration_ms", 0.0))
            if c_end <= c_start:
                # Tiny/point span: a visible tick.
                bar = " " * c_start + _TINY
            else:
                bar = " " * c_start + _BLOCK * (c_end - c_start)
            name = str(s.get("name", "?"))[:_NAME_COL].ljust(_NAME_COL)
            lines.append(f"{name} {bar[: _BAR_COL].ljust(_BAR_COL)} {_fmt_dur(dur_ms)}")
    # Exact numerical table (separate from the visualization).
    lines.append(f"--- {title} exact numbers ---")
    lines.append(
        f"{'Stage':<{_NAME_COL}} {'Start':>10} {'End':>10} {'Duration':>10}"
    )
    for s in sorted(spans, key=lambda r: r["start_mono_ns"]):
        start = int(s["start_mono_ns"])
        end = int(s["end_mono_ns"])
        dur_ms = float(s.get("duration_ms", 0.0))
        name = str(s.get("name", "?"))[:_NAME_COL].ljust(_NAME_COL)
        lines.append(
            f"{name} {_fmt_sec((start - origin_ns) / 1e6):>10} "
            f"{_fmt_sec((end - origin_ns) / 1e6):>10} {_fmt_dur(dur_ms):>10}"
        )
    return lines


# ── E28 multi-window views (Target E §8.3) ────────────────────────────────

_WINDOW_SPECS: list[dict[str, Any]] = [
    {"key": "overview", "title": "FULL REQUEST OVERVIEW", "span_ms": None},
    {"key": "restore_clip", "title": "RESTORE + EARLY CLIP", "span_ms": 5000.0},
    {"key": "model_ready", "title": "MODEL READY / PRE-SAMPLING", "span_ms": 5000.0},
    {"key": "clip_unet", "title": "CLIP + UNET CRITICAL-PATH OVERLAP", "span_ms": 8000.0},
    {"key": "sampling_vae", "title": "SAMPLING + VAE + OUTPUT", "span_ms": 10000.0},
]

# Events whose absence means a window's anchor is unknown (fail-closed: no
# fabricated window).
_ANCHOR_EVENTS = {
    "restore_clip": ("clip_manifest_available", "clip_fh_speculative_read_start",
                     "clip_source_read_start", "restore_entry"),
    "model_ready": ("clip_forward_start", "clip_fh_hydration_start",
                    "unet_gpu_transfer_start", "graph_start"),
    "clip_unet": ("clip_forward_start", "unet_gpu_transfer_start",
                  "clip_source_read_start", "unet_source_read_start"),
    "sampling_vae": ("sampling_start", "vae_decode_start", "output_encode_start"),
}


def _span_events_index(trace: Any) -> dict[str, int]:
    """First-occurrence monotonic stamps by event name (request trace)."""
    out: dict[str, int] = {}
    try:
        events = getattr(trace, "events", None)
        if events is None:
            return out
        for event in list(events):
            name = getattr(event, "name", "")
            mono = getattr(event, "monotonic_ns", 0) or 0
            if isinstance(name, str) and name and mono:
                out.setdefault(name, int(mono))
    except Exception:
        pass
    return out


def _pick_auto_dense_window(spans: list[dict[str, Any]]) -> tuple[int, int]:
    """Deterministic auto-dense window: the 4 s interval (rounded to 100 ms)
    containing the most active spans weighted by overlap.  Simple, bounded,
    deterministic — never tuned by hand."""
    if not spans:
        return 0, 0
    starts = [int(s["start_mono_ns"]) for s in spans]
    ends = [int(s["end_mono_ns"]) for s in spans]
    lo = min(starts)
    hi = max(ends)
    if hi <= lo:
        return lo, lo + 4_000_000_000
    step = 100_000_000  # 100 ms
    best_start = lo
    best_score = -1.0
    window_ns = 4_000_000_000
    t = lo
    while t + window_ns <= hi + step:
        w_end = t + window_ns
        active = 0
        for s in spans:
            if int(s["end_mono_ns"]) >= t and int(s["start_mono_ns"]) <= w_end:
                active += 1
        score = float(active)
        if score > best_score:
            best_score = score
            best_start = t
        t += step
    return best_start, best_start + window_ns


def _collect_window_spans(
    spans: list[dict[str, Any]],
    events: dict[str, int],
    *,
    window_start_ns: int | None,
    window_end_ns: int | None,
) -> list[dict[str, Any]]:
    if window_start_ns is None or window_end_ns is None:
        return spans
    return [
        s for s in spans
        if int(s["end_mono_ns"]) >= window_start_ns
        and int(s["start_mono_ns"]) <= window_end_ns
    ]


def render_gantt_trace(
    trace: Any,
    *,
    title: str = "V2 REMOTE GANTT",
    origin_ns: int | None = None,
    max_chars: int = 120,
) -> list[str]:
    """Render the full-span Gantt for a request trace.  Never raises.

    *origin_ns* defaults to the remote ``python_resume`` boundary (from trace
    metadata) when available, else the earliest span start.  Callers that
    know the true remote ``python_resume`` monotonic origin can pass it
    explicitly.  E28: the FULL REQUEST OVERVIEW is one fixed-width window
    (the whole request scaled into the bar canvas); the other windows are
    generated by :func:`render_gantt_windows`.
    """
    try:
        spans = _collect_spans(trace)
        if origin_ns is None:
            origin_ns = _trace_origin_ns(trace)
        if origin_ns is None:
            origin_ns = 0
        lo = min([int(s["start_mono_ns"]) for s in spans] or [int(origin_ns)])
        hi = max([int(s["end_mono_ns"]) for s in spans] or [lo])
        lines = _render_window(
            spans,
            origin_ns=int(origin_ns),
            window_start_ns=lo,
            window_end_ns=max(hi, lo + 1),
            title=title,
        )
        # R44H2: legacy label semantics warning (adjacent to legacy output).
        if any(s.get("name") == "CLIP forward" for s in spans):
            lines.append(_LEGACY_CLIP_FORWARD_WARNING)
            lines.append(_LEGACY_CLIP_FORWARD_WARNING_2)
        return lines
    except Exception:
        return [f"{title}: render failed (telemetry-only)"]


def render_gantt_windows(
    trace: Any,
    *,
    origin_ns: int | None = None,
) -> list[str]:
    """E28: render ALL fixed-width windows from one trace.

    Views: FULL REQUEST OVERVIEW, RESTORE + EARLY CLIP, MODEL READY /
    PRE-SAMPLING, CLIP + UNET CRITICAL-PATH OVERLAP, SAMPLING + VAE +
    OUTPUT, and AUTO-DENSE (a 4 s window with the highest active-span
    density, discovered automatically).  Every window shares the same fixed
    physical width and the same remote monotonic axis.  Never raises."""
    try:
        spans = _collect_spans(trace)
        if origin_ns is None:
            origin_ns = _trace_origin_ns(trace)
        if origin_ns is None:
            origin_ns = 0
        origin = int(origin_ns)
        events = _span_events_index(trace)
        lo = min([int(s["start_mono_ns"]) for s in spans] or [origin])
        hi = max([int(s["end_mono_ns"]) for s in spans] or [lo])
        full_end = max(hi, lo + 1)
        out: list[str] = []
        for spec in _WINDOW_SPECS:
            key = spec["key"]
            span_ms = spec["span_ms"]
            if span_ms is None:
                w_start, w_end = lo, full_end
            else:
                anchor = None
                for ev in _ANCHOR_EVENTS.get(key, ()):
                    if ev in events:
                        anchor = events[ev]
                        break
                if anchor is None:
                    continue
                w_start = anchor
                w_end = anchor + int(span_ms * 1_000_000)
            window_spans = _collect_window_spans(
                spans, events, window_start_ns=w_start, window_end_ns=w_end
            )
            if not window_spans:
                continue
            out.extend(
                _render_window(
                    window_spans,
                    origin_ns=origin,
                    window_start_ns=w_start,
                    window_end_ns=w_end,
                    title=f"V2 GANTT {spec['title']}",
                )
            )
            out.append("")
        # R44H2: legacy label semantics warning (adjacent to legacy output).
        if any(s.get("name") == "CLIP forward" for s in spans):
            out.append(_LEGACY_CLIP_FORWARD_WARNING)
            out.append(_LEGACY_CLIP_FORWARD_WARNING_2)
            out.append("")
        # AUTO-DENSE window.
        if spans:
            a_start, a_end = _pick_auto_dense_window(spans)
            dense_spans = _collect_window_spans(
                spans, events, window_start_ns=a_start, window_end_ns=a_end
            )
            if dense_spans:
                out.extend(
                    _render_window(
                        dense_spans,
                        origin_ns=origin,
                        window_start_ns=a_start,
                        window_end_ns=a_end,
                        title="V2 GANTT AUTO-DENSE WINDOW",
                    )
                )
        return out
    except Exception:
        return ["V2 GANTT WINDOWS: render failed (telemetry-only)"]


def _trace_origin_ns(trace: Any) -> int | None:
    """Resolve the remote-axis origin: the earliest of the metadata resume
    boundary or the first collected span start.  None when unknown."""
    try:
        metadata = getattr(trace, "_metadata", None) or {}
        candidates: list[int] = []
        for key in (
            "remote_python_resume_mono_ns",
            "restore_method_start_mono_ns",
            "modal_method_entry_mono_ns",
        ):
            value = metadata.get(key)
            if isinstance(value, int):
                candidates.append(int(value))
        spans = _collect_spans(trace)
        candidates.extend(int(s["start_mono_ns"]) for s in spans)
        if not candidates:
            return None
        return min(candidates)
    except Exception:
        return None


def render_zoomed_gantt(
    trace: Any,
    *,
    window_ms: float,
    title: str = "V2 MODEL-READY ZOOM",
    origin_ns: int | None = None,
    max_chars: int = 100,
) -> list[str]:
    """Backward-compatible zoomed view (fixed-width window).  Keeps 40-200 ms
    work visible via the window's own local scale."""
    try:
        spans = _collect_spans(trace)
        if origin_ns is None:
            origin_ns = _trace_origin_ns(trace)
        if origin_ns is None:
            origin_ns = min([int(s["start_mono_ns"]) for s in spans] or [0])
        window_start = int(origin_ns)
        window_end = window_start + int(window_ms * 1_000_000)
        clipped = [
            s for s in spans
            if int(s["end_mono_ns"]) >= window_start
            and int(s["start_mono_ns"]) <= window_end
        ]
        if not clipped:
            return [f"{title}: no spans in window"]
        return _render_window(
            clipped,
            origin_ns=int(origin_ns),
            window_start_ns=window_start,
            window_end_ns=window_end,
            title=title,
        )
    except Exception:
        return [f"{title}: render failed (telemetry-only)"]


def emit_gantt_records(trace: Any, *, request_id: str = "") -> None:
    """Emit ALL fixed-width Gantt windows as one coherent multiline log block.

    Called at request completion.  No-op when the gate is off or no trace.
    Also measures the render/log overhead itself (``gantt_render_wall_ms`` /
    ``gantt_log_payload_bytes`` / window count / max physical line length) so
    logging cost is measured, not guessed.
    """
    if not _ENABLED:
        return
    try:
        rid = str(getattr(trace, "request_id", "") or request_id or "")
        _render_started = time.monotonic_ns()
        full = render_gantt_trace(trace, title=f"V2 REMOTE GANTT request={rid}")
        windows = render_gantt_windows(trace)
        _render_wall_ms = round(
            (time.monotonic_ns() - _render_started) / 1_000_000, 3
        )
        _payload_bytes = sum(len(line.encode("utf-8", "replace")) for line in full)
        _payload_bytes += sum(len(line.encode("utf-8", "replace")) for line in windows)
        _max_line = max(
            [len(line.encode("utf-8", "replace")) for line in full + windows]
            or [0]
        )
        print(
            f"[v2.gantt_overhead] request={rid} "
            f"gantt_render_wall_ms={_render_wall_ms} "
            f"gantt_log_payload_bytes={_payload_bytes} "
            f"full_lines={len(full)} window_lines={len(windows)} "
            f"window_count={windows.count('') + 1 if windows else 0} "
            f"physical_max_line={_max_line}",
            flush=True,
        )
        print("\n".join(full), flush=True)
        print("\n".join(windows), flush=True)
    except Exception:
        pass


def reset_gantt_spans() -> None:
    """Clear the extra-span registry (used between requests/tests)."""
    global _EXTRA_SPANS
    with _LOCK:
        _EXTRA_SPANS = []


def collect_gantt_report(trace: Any) -> dict[str, Any]:
    """JSON-safe machine-readable span report (same axis rules as the Gantt).

    Always available (not gated) so the report/waterfall can carry the spans;
    the *print* path is gated.  Returns ``{"spans": [...], "origin_ns": ...}``.
    """
    try:
        spans = _collect_spans(trace)
        origin_ns = min(
            [int(s["start_mono_ns"]) for s in spans] or [0],
        )
        return {
            "spans": spans,
            "origin_ns": int(origin_ns),
            "count": len(spans),
        }
    except Exception:
        return {"spans": [], "origin_ns": 0, "count": 0}


def collect_point_events(trace: Any) -> list[dict[str, Any]]:
    """Point events (no paired end) kept separate — never fabricated as spans."""
    out: list[dict[str, Any]] = []
    try:
        events = getattr(trace, "events", None)
        if events is None:
            return out
        for event in list(events):
            name = getattr(event, "name", "")
            mono = getattr(event, "monotonic_ns", 0) or 0
            if not isinstance(name, str) or not name:
                continue
            if name.endswith("_end") and name[:-4] in _TRACE_EVENT_SPANS:
                continue
            if name in _TRACE_EVENT_SPANS:
                continue
            out.append({
                "name": name,
                "monotonic_ns": int(mono),
            })
    except Exception:
        pass
    out.sort(key=lambda r: r["monotonic_ns"])
    return out
