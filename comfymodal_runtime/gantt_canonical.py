"""Canonical-ledger Gantt renderer (Batch E29 Gantt repair).

The Gantt is now a RENDERER of the canonical E29 ledger
(``comfymodal_runtime.critical_path_ledger``) — never an independent timing
interpretation.  It:

* consumes the per-request span/event store (strictly request-scoped, so a
  reused container can never append previous-request spans into the next
  request);
* renders semantic rows (RESTORE -> REQUEST SETUP -> CLIP -> UNET ->
  SAMPLING -> VAE -> OUTPUT) so CLIP source read / hydration / bind / forward
  stay adjacent vertically even though source read begins during restore;
* renders every real critical-path wall: any interval with no owning span
  shows as ``UNATTRIBUTED`` — never a blank hole;
* keeps point events in the exact table / detail view, never as cluttering
  full-overview bars.

Measurement-only: never alters the generation path.
"""

from __future__ import annotations

import time
from typing import Any, Iterable, Mapping

from .env import env_flag

_GANTT_FLAG = "COMFYMODAL_V2_GANTT_TELEMETRY"
_ENABLED: bool = env_flag(_GANTT_FLAG, default=False)


def _gantt_enabled() -> bool:
    """Evaluate the deploy-baked Gantt gate after Modal env injection."""
    return env_flag(_GANTT_FLAG, default=_ENABLED)

# ── Semantic row order (full overview) ────────────────────────────────────
_SEMANTIC_LANES: tuple[str, ...] = (
    "RESTORE",
    "REQUEST-SETUP",
    "CLIP",
    "UNET",
    "SAMPLING",
    "VAE",
    "OUTPUT",
)

# Ledger span names -> semantic lane (overrides the raw lane for grouping).
_NAME_LANE: dict[str, str] = {
    "restore": "RESTORE",
    "restore method": "RESTORE",
    "bootstrap_restore": "RESTORE",
    "restore:early": "RESTORE",
    "restore:eviction": "RESTORE",
    "restore:snapshot": "RESTORE",
    "restore:preamble": "RESTORE",
    "restore:bootstrap": "RESTORE",
    "restore:preload": "RESTORE",
    "restore:finalize": "RESTORE",
    "request:identity-capture": "REQUEST-SETUP",
    "request:plan-deserialize": "REQUEST-SETUP",
    "request:setup-schedule": "REQUEST-SETUP",
    "request:cc-prefetch-submit": "REQUEST-SETUP",
    "request:input-types-warm": "REQUEST-SETUP",
    "request:executor-run": "EXECUTOR",
    "executor:graph-execution": "EXECUTOR",
    "CLIP source read": "CLIP",
    "CLIP hydration": "CLIP",
    "CLIP GPU hydration": "CLIP",
    "CLIP bind": "CLIP",
    "CLIP forward": "CLIP",
    "UNET source read": "UNET",
    "UNET H2D": "UNET",
    "UNET final ready": "UNET",
    "sampler setup": "SAMPLING",
    "sampling": "SAMPLING",
    "post-sampling transition": "VAE",
    "vae:early-activation": "VAE",
    "model-mgmt:load_models_gpu": "VAE",
    "VAE model-mgmt": "VAE",
    "VAE decode": "VAE",
    "output encode": "OUTPUT",
    "durable result": "OUTPUT",
}

_BLOCK = "\u2588"
_TINY = "\u258f"
_NAME_COL = 20
_BAR_COL = 64
_TOTAL_LINE_MAX = _NAME_COL + 1 + _BAR_COL + 1 + 12  # <= 98 chars


def gantt_enabled() -> bool:
    return _ENABLED


def _semantic_lane(span: Mapping[str, Any]) -> str:
    name = str(span.get("name", "?"))
    return _NAME_LANE.get(name, str(span.get("lane") or "MAIN"))


def _fmt_dur(ms: float) -> str:
    ms = max(0.0, float(ms))
    if ms < 1000.0:
        return f"{ms:.0f}ms" if ms >= 100 else f"{ms:.1f}ms"
    return f"{ms / 1000.0:.2f}s"


def _fmt_sec(offset_ms: float) -> str:
    sign = "-" if offset_ms < 0 else "+"
    return f"{sign}{abs(offset_ms) / 1000.0:.3f}s"


def _collect_ledger_spans(ledger: Any) -> list[dict[str, Any]]:
    """Pull the current request's spans from the canonical ledger store.

    ``ledger`` may be the module itself (its ``get_spans``) or an object
    exposing ``get_spans()``.  Falls back to an empty list on any error.
    Includes the restore-session spans (same process, same monotonic axis)
    so the full RESTORE section renders.
    """
    try:
        getter = getattr(ledger, "get_spans", None)
        restore_getter = getattr(ledger, "get_restore_spans", None)
        spans: list[dict[str, Any]] = []
        if callable(restore_getter):
            restored = restore_getter()
            if isinstance(restored, list):
                spans.extend(restored)
        if callable(getter):
            current = getter()
            if isinstance(current, list):
                spans.extend(current)
        return spans
    except Exception:
        pass
    return []


def _collect_ledger_events(ledger: Any) -> list[dict[str, Any]]:
    try:
        getter = getattr(ledger, "get_events", None)
        restore_getter = getattr(ledger, "get_restore_events", None)
        events: list[dict[str, Any]] = []
        if callable(restore_getter):
            restored = restore_getter()
            if isinstance(restored, list):
                events.extend(restored)
        if callable(getter):
            current = getter()
            if isinstance(current, list):
                events.extend(current)
        return events
    except Exception:
        pass
    return []


def _golden_parallel_stage_mapping(
    golden_telemetry: Mapping[str, Any] | None,
) -> dict[str, Mapping[str, Any]]:
    """Project authoritative Golden stage intervals for the console renderer.

    The direct Golden path persists its stage recorder independently of the
    optional full trace and independently of the canonical ledger.  Keep this
    projection deliberately small: the recorder's monotonic entry/end marks
    are the only interval authority used by the fallback renderer.
    """
    if not isinstance(golden_telemetry, Mapping):
        return {}
    raw_stages = golden_telemetry.get("stages")
    if not isinstance(raw_stages, list):
        return {}
    stages: dict[str, Mapping[str, Any]] = {}
    for raw_stage in raw_stages:
        if not isinstance(raw_stage, Mapping):
            continue
        name = str(raw_stage.get("name") or "").strip()
        if name:
            stages[name] = raw_stage
    return stages


def _golden_parallel_transport_records(
    golden_telemetry: Mapping[str, Any] | None,
) -> list[Mapping[str, Any]]:
    """Collect transport annotations already persisted by Golden telemetry."""
    if not isinstance(golden_telemetry, Mapping):
        return []

    records: list[Mapping[str, Any]] = []

    def add(value: Any) -> None:
        if isinstance(value, Mapping):
            record = dict(value)
            # Transport implementations persist the same measurements either
            # flat or under a small timing/stats/details mapping.  Flatten only
            # the renderer's known fields; raw telemetry remains untouched.
            for nested_key in ("m2_timing", "timing", "stats", "details"):
                nested = record.get(nested_key)
                if isinstance(nested, Mapping):
                    for field in (
                        "source_wall_ms",
                        "source_read_wall_ms",
                        "total_load_ms",
                        "full_load_ms",
                        "gpu_ready_wall_ms",
                        "gpu_ready_tail_ms",
                    ):
                        if record.get(field) is None and nested.get(field) is not None:
                            record[field] = nested[field]
            if record.get("source_wall_ms") is None and record.get("source_read_wall_ms") is not None:
                record["source_wall_ms"] = record["source_read_wall_ms"]
            if record.get("total_load_ms") is None and record.get("full_load_ms") is not None:
                record["total_load_ms"] = record["full_load_ms"]
            records.append(record)
        elif isinstance(value, list):
            records.extend(item for item in value if isinstance(item, Mapping))

    for key in ("transports", "transport_records", "model_transport_records"):
        add(golden_telemetry.get(key))

    events = golden_telemetry.get("events")
    if isinstance(events, list):
        has_full_transport_events = any(
            isinstance(event, Mapping)
            and str(event.get("name", "")) == "golden_model_transport_load"
            for event in events
        )
        for event in events:
            if not isinstance(event, Mapping):
                continue
            event_name = str(event.get("name", ""))
            if event_name == "golden_m2_transport" and has_full_transport_events:
                continue
            if event_name not in {"golden_model_transport_load", "golden_m2_transport"}:
                continue
            fields = event.get("fields")
            add(fields if isinstance(fields, Mapping) else event)

    stages = golden_telemetry.get("stages")
    if isinstance(stages, list):
        for stage in stages:
            if not isinstance(stage, Mapping):
                continue
            details = stage.get("details")
            if not isinstance(details, Mapping):
                continue
            for key in (
                "transports",
                "transport_records",
                "model_transport_records",
                "transport_stats",
            ):
                add(details.get(key))
            for key in ("transport", "transport_telemetry"):
                value = details.get(key)
                if isinstance(value, Mapping):
                    add(value)
                    add(value.get("records"))

    # A transport can be present in both an event and a stage detail.  Preserve
    # recorder order while avoiding duplicate annotations in the compact view.
    unique: list[Mapping[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for record in records:
        identity = (
            record.get("path"),
            record.get("source_wall_ms"),
            record.get("total_load_ms", record.get("full_load_ms")),
            record.get("gpu_ready_wall_ms"),
            record.get("gpu_ready_tail_ms"),
        )
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(record)
    return unique


def _golden_parallel_arch(golden_telemetry: Mapping[str, Any] | None) -> str:
    if not isinstance(golden_telemetry, Mapping):
        return ""
    for key in ("architecture", "execution_architecture", "execution_arm"):
        value = golden_telemetry.get(key)
        if value:
            return str(value)
    identity = golden_telemetry.get("run_identity")
    if isinstance(identity, Mapping):
        for key in ("architecture", "execution_architecture", "execution_arm"):
            value = identity.get(key)
            if value:
                return str(value)
    return ""


def _golden_parallel_external_restore(
    golden_telemetry: Mapping[str, Any] | None,
) -> tuple[Any, Any]:
    if not isinstance(golden_telemetry, Mapping):
        return None, None
    external = golden_telemetry.get("external_restore")
    if not isinstance(external, Mapping):
        return None, None
    restore = external.get("restore_total_ms")
    snapshot = next(
        (
            external.get(key)
            for key in ("platform_snapshot_ms", "snapshot_ms", "snapshot_restore_ms")
            if external.get(key) is not None
        ),
        None,
    )
    return restore, snapshot


def _serial_gap_segments(
    spans: list[dict[str, Any]],
    *,
    start_mono_ns: int,
    end_mono_ns: int,
) -> list[dict[str, Any]]:
    """UNATTRIBUTED segments on the serial axis between/around spans."""
    segments: list[dict[str, Any]] = []
    ordered = sorted(
        spans, key=lambda s: (int(s["start_mono_ns"]), int(s["end_mono_ns"]))
    )
    cursor = int(start_mono_ns)
    for s in ordered:
        s_start = int(s["start_mono_ns"])
        s_end = int(s["end_mono_ns"])
        if s_end <= cursor:
            continue
        if s_start > cursor:
            segments.append({
                "name": "UNATTRIBUTED",
                "start_mono_ns": cursor,
                "end_mono_ns": s_start,
                "duration_ms": (s_start - cursor) / 1_000_000,
            })
        cursor = max(cursor, s_end)
    if cursor < int(end_mono_ns):
        segments.append({
            "name": "UNATTRIBUTED",
            "start_mono_ns": cursor,
            "end_mono_ns": int(end_mono_ns),
            "duration_ms": (int(end_mono_ns) - cursor) / 1_000_000,
        })
    return segments


def render_canonical_gantt(
    ledger: Any,
    *,
    origin_ns: int | None = None,
    title: str = "E29 CANONICAL GANTT",
    max_chars: int = 120,
) -> list[str]:
    """Render the full-overview Gantt strictly from the canonical ledger.

    * ``origin_ns`` defaults to the earliest span start (or the first event).
    * Bars are drawn on the semantic lane rows; every real gap on the serial
      axis renders as an explicit UNATTRIBUTED bar (never blank).
    * Point events (zero duration) never appear as overview bars.
    """
    try:
        spans = _collect_ledger_spans(ledger)
        events = _collect_ledger_events(ledger)
        if not spans and not events:
            return [f"{title}: no canonical ledger data"]
        all_stamps = [int(s["start_mono_ns"]) for s in spans] + [
            int(s["end_mono_ns"]) for s in spans
        ] + [int(e["mono_ns"]) for e in events]
        lo = min(all_stamps)
        hi = max(all_stamps)
        if origin_ns is None:
            origin_ns = lo
        origin = int(origin_ns)
        w_start, w_end = lo, max(hi, lo + 1)
        w_ms = max(1.0, (w_end - w_start) / 1_000_000.0)
        ms_per_char = max(1e-6, w_ms / _BAR_COL)
        lines: list[str] = []
        lines.append(
            f"{title}  window=+{(w_start - origin) / 1e9:.3f}s.."
            f"+{(w_end - origin) / 1e9:.3f}s  scale={ms_per_char:.1f} ms/char"
        )
        # Local ruler.
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
                sec = (w_start - origin + int(tick_offset_ms * 1_000_000)) / 1e9
                header.append(f"{sec:+.1f}s".ljust(int(tick_chars))[: int(tick_chars)])
                prev_tick = tick_i
        lines.append("".join(header).rstrip())
        lines.append(" " * (_NAME_COL + 1) + "|" + "-" * _BAR_COL)

        def _render_bar(record: Mapping[str, Any], label: str) -> None:
            start = int(record["start_mono_ns"])
            end = int(record["end_mono_ns"])
            if end < w_start or start > w_end:
                return
            c_start = max(0, int((start - w_start) / 1_000_000.0 / ms_per_char))
            c_end = min(
                _BAR_COL,
                max(c_start, int((end - w_start) / 1_000_000.0 / ms_per_char)),
            )
            dur_ms = float(record.get("duration_ms", 0.0))
            if c_end <= c_start:
                bar = " " * c_start + _TINY
            else:
                bar = " " * c_start + _BLOCK * (c_end - c_start)
            lines.append(
                f"{label[: _NAME_COL].ljust(_NAME_COL)} "
                f"{bar[: _BAR_COL].ljust(_BAR_COL)} {_fmt_dur(dur_ms)}"
            )

        for lane in _SEMANTIC_LANES:
            lane_spans = [s for s in spans if _semantic_lane(s) == lane]
            for s in sorted(lane_spans, key=lambda r: int(r["start_mono_ns"])):
                _render_bar(s, str(s.get("name", "?")))
        # Explicit UNATTRIBUTED gap bars (never blank critical-path holes).
        for gap in _serial_gap_segments(spans, start_mono_ns=w_start, end_mono_ns=w_end):
            if gap["duration_ms"] <= 0:
                continue
            _render_bar(gap, "UNATTRIBUTED")
        # Exact numerical table (separate from the visualization).
        lines.append(f"--- {title} exact numbers ---")
        lines.append(f"{'Stage':<{_NAME_COL}} {'Start':>10} {'End':>10} {'Duration':>10}")
        for s in sorted(spans, key=lambda r: int(r["start_mono_ns"])):
            name = str(s.get("name", "?"))[:_NAME_COL].ljust(_NAME_COL)
            lines.append(
                f"{name} {_fmt_sec((int(s['start_mono_ns']) - origin) / 1e6):>10} "
                f"{_fmt_sec((int(s['end_mono_ns']) - origin) / 1e6):>10} "
                f"{_fmt_dur(float(s.get('duration_ms', 0.0))):>10}"
            )
        # Point-event detail (never full-overview bars).
        if events:
            lines.append("--- point events ---")
            for e in sorted(events, key=lambda r: int(r["mono_ns"])):
                lines.append(
                    f"{str(e.get('name', '?'))[:_NAME_COL].ljust(_NAME_COL)} "
                    f"{_fmt_sec((int(e['mono_ns']) - origin) / 1e6):>10}"
                )
        return lines
    except Exception:
        return [f"{title}: render failed (telemetry-only)"]


def emit_canonical_gantt(
    ledger: Any,
    *,
    request_id: str = "",
    force: bool = False,
    golden_telemetry: Mapping[str, Any] | None = None,
) -> None:
    """Print each canonical Gantt line as its own flushed, locatable record.

    The canonical ledger is independent of the optional E27 trace.  Direct
    Golden may additionally provide its authoritative persisted stage list;
    that list is used only when the canonical ledger has no rows.  ``force``
    is reserved for a request-owned path such as direct Golden; the default
    remains gated for non-Golden callers.
    Emission errors intentionally propagate to the caller.
    """
    if not force and not _gantt_enabled():
        return
    rid = str(request_id or "")
    spans = _collect_ledger_spans(ledger)
    events = _collect_ledger_events(ledger)
    if not spans and not events:
        stages = _golden_parallel_stage_mapping(golden_telemetry)
        if stages:
            from .golden_human_report import render_parallel_console_gantt

            restore_ms, snapshot_ms = _golden_parallel_external_restore(
                golden_telemetry
            )
            rendered = render_parallel_console_gantt(
                stages,
                transports=_golden_parallel_transport_records(golden_telemetry),
                arch=_golden_parallel_arch(golden_telemetry),
                external_restore_ms=restore_ms,
                external_snapshot_ms=snapshot_ms,
            )
            for line in rendered.splitlines():
                # The established renderer owns its [GOLDEN GANTT] header.
                # Normalize that header into the same request-addressable,
                # flushed record shape as canonical output without producing a
                # nested/duplicate prefix.
                if line.startswith("[GOLDEN GANTT]"):
                    line = line[len("[GOLDEN GANTT]"):].lstrip()
                print(f"[GOLDEN GANTT] request={rid} {line}", flush=True)
            return
        print(
            f"[GOLDEN GANTT] request={rid} unavailable: no canonical ledger rows",
            flush=True,
        )
        return

    lines = render_canonical_gantt(ledger, title=f"E29 CANONICAL GANTT request={rid}")
    for line in lines:
        print(f"[GOLDEN GANTT] {line}", flush=True)
