"""V2 DYNAMIC CRITICAL PATH GANTT — dynamic event-driven renderer + telemetry reconciliation.

Scope
-----
This module is a PURE presentation/reconciliation layer over already-collected
telemetry artifacts (``run_0.json`` / ``run_*_sample.json`` written by the v2
benchmark harness).  It never measures anything itself and never touches the
generation path.  Given a run directory it:

* discovers which measurements actually exist in the artifacts and renders ONLY
  those (never fabricates a row for absent telemetry);
* maps raw events/spans onto a canonical REGISTRY with honest labels and a
  parent/child hierarchy (children indented under parents);
* places every row on ONE shared absolute monotonic timeline.  Epoch-second
  stage keys (t4..t8) are converted into the monotonic domain through the
  constant ``A = wall_unix_ns - mono_ns`` derived from trace events that carry
  both clocks;
* keeps broad windows and exact sub-spans COEXISTING (e.g. "UNET H2D (broad
  window)" next to the exact FastSafe copy/adoption children) — never one
  substituted for the other;
* applies the LEGACY ALIAS RULE for spans/events literally named
  ``"CLIP forward"``: such a span maps to "CLIP inner forward" only when its
  duration matches the inner-forward evidence (within 5%), or — when it is the
  only CLIP-forward-ish evidence and its magnitude matches the outer wrapper —
  to "CLIP outer encode".  When BOTH outer and inner evidence exist the labels
  are exactly "CLIP outer encode" / "CLIP inner forward", never bare
  "CLIP forward";
* renders WINDOWS (full application, pre-sampler, CLIP detail, UNET detail,
  sampler transition, post-sampling/VAE, AUTO-DENSE), skipping gracefully any
  window whose boundary events are absent;
* emits CLOSURE reports (parent = node/container, components = exact
  sub-spans; residual math only when components fit and do not overlap);
* emits a TELEMETRY COMPLETENESS matrix (PRESENT/MISSING + closest proxy),
  LABEL CONFLICT detection, and a CRITICAL PATH SUMMARY whose totals are
  computed over the UNION coverage of critical rows (overlapping rows are
  never summed).

AUTO-DENSE window algorithm (deterministic)
-------------------------------------------
Candidate regions are evaluated with a sliding 4-second span over the sorted
row start times: for every row start ``s`` the candidate cluster is the set of
rows intersecting ``[s, s + 4s]``.  Clusters with fewer than 3 rows are
ignored.  Among the remaining candidates the winner maximizes, in order:
(1) row count, (2) total busy ms inside the span, (3) earliest start.  The
winning cluster is expanded to fully contain every intersecting row, then
clamped to at most ``min(full_span, 8s)``.

Honesty note on anchoring
-------------------------
Some exact durations (e.g. ``fastsafe_copy_wall_ms``) carry no timestamps.
Such rows are placed at a deterministic estimated anchor (parent start, or
sequentially after preceding siblings inside their known container) and their
``meta["anchoring"]`` records the estimate ("parent-start" /
"sequential-estimate").  Durations shown are always the measured values;
only the horizontal placement of timestamp-less components is estimated.

All functions are pure except :func:`load_run_artifacts` (filesystem read).
Rendered text is deterministic: sorted iteration, no wall-clock, no randomness.
"""

from __future__ import annotations

import json
import os
import statistics
from dataclasses import dataclass, field

GANTT_TITLE = "V2 DYNAMIC CRITICAL PATH GANTT"

_MS = 1_000_000          # ns per ms
_S = 1_000_000_000       # ns per second
_BLOCK = "\u2588"         # █
_EIGHTHS = ("\u258f", "\u258e", "\u258d", "\u258c", "\u258b", "\u258a", "\u2589")  # ▏▎▍▌▋▊▉
_LABEL_COL = 38

# Tolerances (spec)
_FIT_TOL_MS = 25.0       # component-inside-parent clock-skew tolerance
_OVERLAP_TOL_MS = 1.0    # pairwise component overlap tolerance
_CLOSE_RES_PCT = 5.0     # closure pass threshold: residual pct
_CLOSE_RES_MS = 250.0    # closure pass threshold: residual ms


# ── Data model ────────────────────────────────────────────────────────────


@dataclass
class GanttRow:
    key: str                      # stable registry key or synthesized "event:<name>"
    label: str                    # canonical display label
    parent_key: str | None
    kind: str                     # "exact" | "broad" | "point" | "derived" | "container"
    role: str                     # "critical" | "background"
    lane: str                     # "GPU" | "CPU" | "IO" | "APP" | ...
    start_mono_ns: int
    end_mono_ns: int              # == start for point rows
    duration_ms: float
    source_refs: list[str]
    meta: dict = field(default_factory=dict)


@dataclass
class DynamicPayload:
    request_id: str
    rows: list[GanttRow]
    raw: dict                     # normalized source dicts for closure/completeness logic
    anchors: dict                 # clock anchor info, origin, etc.
    warnings: list[str]


# ── Small pure helpers ────────────────────────────────────────────────────


def truncate_label(label: str, limit: int = _LABEL_COL) -> str:
    """Deterministically truncate a display label to ``limit`` chars (test-friendly)."""
    label = str(label)
    if len(label) <= limit:
        return label
    if limit <= 1:
        return label[:limit]
    return label[: limit - 1] + "\u2026"  # ellipsis


def _fmt_ms(ms: float) -> str:
    ms = max(0.0, float(ms))
    if ms >= 10_000.0:
        return f"{ms:,.0f}"
    if ms >= 100.0:
        return f"{ms:.1f}"
    return f"{ms:.3f}".rstrip("0").rstrip(".") if ms < 10.0 else f"{ms:.1f}"


def _rel_diff(a: float, b: float) -> float:
    b = abs(float(b))
    return abs(float(a) - b) / b if b else float("inf")


def _overlap_ns(a0: int, a1: int, b0: int, b1: int) -> int:
    return max(0, min(a1, b1) - max(a0, b0))


# ── Loading ───────────────────────────────────────────────────────────────


def _find_run_file(run_dir: str) -> str | None:
    for cand in ("run_0.json", "run_000.json"):
        p = os.path.join(run_dir, cand)
        if os.path.isfile(p):
            return p
    for name in sorted(os.listdir(run_dir)):
        if name.startswith("run_") and name.endswith(".json") and "sample" not in name:
            return os.path.join(run_dir, name)
    return None


def _find_sample_file(run_dir: str) -> str | None:
    if not os.path.isdir(run_dir):
        return None
    for name in sorted(os.listdir(run_dir)):
        if name.startswith("run_") and name.endswith(".json") and "sample" in name:
            return os.path.join(run_dir, name)
    return None


def _derive_anchor_ns(trace_events: list) -> tuple[int, int]:
    """Return (A, n_samples) where A = wall_unix_ns - mono_ns (constant per run)."""
    samples = []
    for e in trace_events or []:
        mono = e.get("monotonic_ns") or 0
        wall = e.get("wall_unix_ns") or 0
        if mono > 0 and wall > 0:
            samples.append(wall - mono)
    if not samples:
        return 0, 0
    return int(round(statistics.median(samples))), len(samples)


def _to_mono(wall_ns: int, anchor: int) -> int:
    return int(wall_ns) - int(anchor) if wall_ns else 0


def load_run_artifacts(run_dir: str, run_file: str | None = None) -> DynamicPayload:
    """Load a benchmark run directory into a normalized DynamicPayload.

    ``run_file`` optionally selects a specific artifact (e.g. ``run_2.json``
    in multi-run campaign directories); defaults to auto-discovery.
    """
    warnings: list[str] = []
    run_path = os.path.join(run_dir, run_file) if run_file else _find_run_file(run_dir)
    if not run_path or not os.path.isfile(run_path):
        raise FileNotFoundError(f"no run_*.json artifact found in {run_dir!r}")
    with open(run_path, "r", encoding="utf-8") as fh:
        d = json.load(fh)

    r = d.get("result") or {}
    trace = r.get("trace") or {}
    events_raw = trace.get("events") or []

    anchor, n_anchor = _derive_anchor_ns(events_raw)
    if not anchor:
        warnings.append("no wall+monotonic event pair found; epoch->mono conversion disabled")

    # ── normalize trace events ────────────────────────────────────────────
    events: list[dict] = []
    for e in events_raw:
        meta = e.get("metadata") or {}
        # R44I2: deferred-emitted boundary events carry their TRUE timestamp
        # in metadata.mono_ns (top-level monotonic_ns is the late emit stamp).
        mono = int(e.get("monotonic_ns") or 0)
        if str(meta.get("emission") or "") == "deferred_boundary":
            mono = int(meta.get("mono_ns") or 0) or mono
        mono = mono or _to_mono(e.get("wall_unix_ns") or 0, anchor)
        ev = {
            "name": str(e.get("name", "?")),
            "mono_ns": mono,
            "wall_unix_ns": int(e.get("wall_unix_ns") or 0),
            "meta": meta,
        }
        dur = meta.get("duration_ms")
        if dur is None:
            dur = meta.get("wall_ms")
        if isinstance(dur, (int, float)) and dur > 0:
            ev["dur_ms"] = float(dur)
            ev["start_mono_ns"] = mono - int(round(dur * _MS))
            ev["end_mono_ns"] = mono
        events.append(ev)

    # ── spans from gantt_telemetry and canonical_ledger ───────────────────
    gt = r.get("gantt_telemetry") or {}
    gt_spans = [
        {
            "name": str(s.get("name", "?")),
            "lane": str(s.get("lane", "MAIN")),
            "start_mono_ns": int(s.get("start_mono_ns") or 0),
            "end_mono_ns": int(s.get("end_mono_ns") or s.get("start_mono_ns") or 0),
            "duration_ms": float(s.get("duration_ms") or 0.0),
        }
        for s in (gt.get("spans") or [])
    ]

    ledger = r.get("canonical_ledger") or d.get("canonical_ledger") or {}
    led_spans = [
        {
            "name": str(s.get("name", "?")),
            "lane": str(s.get("lane", "MAIN")),
            "start_mono_ns": int(s.get("start_mono_ns") or 0),
            "end_mono_ns": int(s.get("end_mono_ns") or 0),
            "duration_ms": float(s.get("duration_ms") or 0.0),
        }
        for s in (ledger.get("spans") or [])
    ]

    # ── waterfall stages (normalize to mono ns) ───────────────────────────
    wf_stages: dict[str, dict] = {}
    for st in ((d.get("waterfall") or {}).get("stages") or []):
        key = st.get("key")
        if not key:
            continue
        scope = str(st.get("clock_scope") or "wall")
        start = int(st.get("start_ns") or 0)
        end = int(st.get("end_ns") or 0)
        dur = float(st.get("duration_ms") or 0.0)
        if not scope.startswith("monotonic"):
            start = _to_mono(start, anchor)
            end = _to_mono(end, anchor)
        if end <= 0 and dur > 0:
            end = start + int(round(dur * _MS))
        wf_stages[key] = {
            "key": key,
            "label": str(st.get("label") or key),
            "start_mono_ns": start,
            "end_mono_ns": end,
            "duration_ms": dur,
            "clock_scope": scope,
        }

    # ── per-run sample stages (epoch seconds -> mono ns) ──────────────────
    sample_stages: dict[str, int] = {}
    sample_path = _find_sample_file(run_dir)
    if sample_path is not None:
        try:
            with open(sample_path, "r", encoding="utf-8") as fh:
                samp = json.load(fh)
            for k, v in ((samp.get("full_trace") or {}).get("stages") or {}).items():
                if isinstance(v, (int, float)) and v > 0:
                    sample_stages[k] = int(round(v * 1_000_000_000)) - anchor
        except (OSError, ValueError) as exc:
            warnings.append(f"could not load sample artifact: {exc}")

    psr = r.get("pre_sampler_structured_report") or {}
    raw = {
        "run_file": os.path.basename(run_path),
        "events": events,
        "gt_spans": gt_spans,
        "led_spans": led_spans,
        "ledger": ledger,
        "serial_ledger": ledger.get("serial_ledger") or {},
        "waterfall_stages": wf_stages,
        "sample_stages": sample_stages,
        "phase_durations_ms": r.get("phase_durations_ms") or {},
        "timing": d.get("timing") or {},
        "restore_timing": r.get("_restore_timing") or {},
        "loader_selection": d.get("loader_selection") or {},
        "cpu_owner_records": psr.get("cpu_owner_records") or [],
        "profile_name": d.get("profile_name") or "",
        "runtime_status": d.get("runtime_status") or {},
    }

    payload = DynamicPayload(
        request_id=str(d.get("request_id") or r.get("request_id") or "?"),
        rows=[],
        raw=raw,
        anchors={
            "wall_minus_mono_ns": anchor,
            "anchor_samples": n_anchor,
            "origin_mono_ns": (ledger.get("start_mono_ns") or 0),
        },
        warnings=warnings,
    )
    payload.rows = build_rows(payload)
    return payload


# ── Evidence accessors ────────────────────────────────────────────────────


def _ev(raw: dict, name: str, pred=None) -> dict | None:
    """Last event with ``name`` (optionally filtered) — deterministic."""
    found = None
    for e in raw["events"]:
        if e["name"] == name and (pred is None or pred(e)):
            found = e
    return found


def _gt_span(raw: dict, name: str) -> dict | None:
    for s in raw["gt_spans"]:
        if s["name"] == name:
            return s
    return None


def _led_span(raw: dict, name: str) -> dict | None:
    for s in raw["led_spans"]:
        if s["name"] == name:
            return s
    return None


def _samp(raw: dict, key: str) -> int | None:
    v = raw["sample_stages"].get(key)
    return int(v) if v else None


def _classify_clip_forward(dur_ms: float, inner_ms: float | None, outer_ms: float | None) -> str | None:
    """LEGACY ALIAS RULE for spans/events literally named "CLIP forward"."""
    if inner_ms is not None and _rel_diff(dur_ms, inner_ms) <= 0.05:
        return "inner"
    if outer_ms is not None and _rel_diff(dur_ms, outer_ms) <= 0.05:
        return "outer"
    if inner_ms is None and outer_ms is not None and _rel_diff(dur_ms, outer_ms) <= 0.10:
        return "outer"
    if outer_ms is None and inner_ms is not None and _rel_diff(dur_ms, inner_ms) <= 0.10:
        return "inner"
    return None


# ── Registry / row construction ───────────────────────────────────────────

_CONSUMED_EVENT_ALIASES = {
    "clip_fast_load_start", "clip_fast_load_end",
    "clip_forward_start", "clip_forward_end", "clip_raw_encode_start", "clip_raw_encode_end",
    "unet_source_prep_armed", "unet_source_prep_joined", "unet_fastsafe_pipeline",
    "unet_gpu_transfer_start", "unet_gpu_transfer_end",
    "unet_gpu_gate_wait_start", "unet_gpu_gate_wait_end",
    "remote_method_entry", "remote_result_emit",
    # R44H2 sampler boundary events (rendered as canonical rows, never as
    # unregistered duplicates)
    "sampling_start", "sampler_prep_phase", "sampler_first_eval_start",
    "sampler_step_ticks", "sampler_tail", "unet_first_cuda_op",
}


def _row(key, label, parent, kind, role, lane, start, end, refs, **meta) -> GanttRow:
    start = int(start)
    end = int(end)
    dur = (end - start) / _MS
    return GanttRow(
        key=key, label=label, parent_key=parent, kind=kind, role=role, lane=lane,
        start_mono_ns=start, end_mono_ns=end, duration_ms=dur,
        source_refs=list(refs), meta=dict(meta),
    )


def _seq_places(start_ns: int, durs_ms: list[float]) -> list[tuple[int, int]]:
    """Sequentially lay out durations from ``start_ns`` (deterministic estimate)."""
    places = []
    cur = int(start_ns)
    for d in durs_ms:
        end = cur + int(round(float(d) * _MS))
        places.append((cur, end))
        cur = end
    return places


def build_rows(payload: DynamicPayload) -> list[GanttRow]:
    """Build the canonical registry rows from a payload (pure, idempotent).

    Can also be called on a fresh ``DynamicPayload`` whose ``raw`` was filled
    by :func:`load_run_artifacts`; calling twice yields identical rows.
    """
    raw = payload.raw
    anchor = int(payload.anchors.get("wall_minus_mono_ns") or 0)
    rows: list[GanttRow] = []
    consumed_gt: set[int] = set()
    consumed_led: set[int] = set()

    # ---- evidence --------------------------------------------------------
    cfls = _ev(raw, "clip_fast_load_start")
    cfle = _ev(raw, "clip_fast_load_end")
    cfls_m = (cfls or {}).get("meta", {})
    cfle_m = (cfle or {}).get("meta", {})

    fwd_events = [e for e in raw["events"] if e["name"] == "clip_forward_end"]
    outer_ev = next((e for e in fwd_events if "wall_ms" in e["meta"] and "allocated_delta_bytes" in e["meta"]), None)
    inner_ev = next((e for e in fwd_events if "duration_ms" in e["meta"] and ("cuda_no_sync" in e["meta"] or "thread_cpu_ms" in e["meta"])), None)
    outer_ms = float(outer_ev["meta"]["wall_ms"]) if outer_ev else None
    inner_ms = float(inner_ev["meta"]["duration_ms"]) if inner_ev else None

    cre_s = _ev(raw, "clip_raw_encode_start")
    cre_e = _ev(raw, "clip_raw_encode_end")

    armed = _ev(raw, "unet_source_prep_armed")
    joined = _ev(raw, "unet_source_prep_joined")
    pipe = _ev(raw, "unet_fastsafe_pipeline")
    pipe_m = (pipe or {}).get("meta", {})
    xfer_s = _ev(raw, "unet_gpu_transfer_start")
    xfer_e = _ev(raw, "unet_gpu_transfer_end")

    lmg_rec = next((rc for rc in raw["cpu_owner_records"]
                    if rc.get("operation") == "load_models_gpu" and rc.get("role") == "CLIP"), None)

    samp = raw["sample_stages"]
    wf = raw["waterfall_stages"]
    gt_clip_fwd = _gt_span(raw, "CLIP forward")
    gt_h2d = _gt_span(raw, "UNET H2D")
    gt_vae = _gt_span(raw, "VAE decode")
    gt_oenc = _gt_span(raw, "output encode")
    led_restore = _led_span(raw, "restore method")
    led_bootstrap = _led_span(raw, "restore:bootstrap")
    led_method_entry = next((s for s in raw["gt_spans"] if s["name"] == "method entry"), None)

    # ---- restore ---------------------------------------------------------
    restore_start = restore_end = None
    if led_restore and led_restore["end_mono_ns"] > led_restore["start_mono_ns"]:
        restore_start, restore_end = led_restore["start_mono_ns"], led_restore["end_mono_ns"]
        consumed_gt.add(id(led_restore))
    elif _samp(raw, "t4_modal_method_entry"):
        pass
    if restore_start is None and raw["serial_ledger"].get("start_mono_ns"):
        restore_start = int(raw["serial_ledger"]["start_mono_ns"])
    if restore_start is not None:
        rows.append(_row("restore", "Restore (application)", None, "container", "critical", "APP",
                         restore_start, restore_end or restore_start,
                         [f"gantt_telemetry.spans:restore method"], decomposes=bool(led_bootstrap)))

    if led_bootstrap and led_bootstrap["duration_ms"] > 0:
        consumed_led.add(id(led_bootstrap))
        rows.append(_row("restore.bootstrap", "restore bootstrap", "restore", "exact", "critical", "APP",
                         led_bootstrap["start_mono_ns"], led_bootstrap["end_mono_ns"],
                         ["canonical_ledger.spans:restore:bootstrap"]))
    elif raw["phase_durations_ms"].get("v2_bootstrap_restore") and restore_end:
        dur = float(raw["phase_durations_ms"]["v2_bootstrap_restore"])
        rows.append(_row("restore.bootstrap", "restore bootstrap", "restore", "exact", "critical", "APP",
                         restore_end - int(round(dur * _MS)), restore_end,
                         ["result.phase_durations_ms:v2_bootstrap_restore"], anchoring="parent-end"))

    # ---- request/setup ---------------------------------------------------
    setup_children: list[GanttRow] = []
    rms = wf.get("remote_method_setup")
    if rms and rms["end_mono_ns"] > rms["start_mono_ns"]:
        setup_children.append(_row("request.setup.remote_method", "remote method setup", "request.setup",
                                   "exact", "critical", "APP", rms["start_mono_ns"], rms["end_mono_ns"],
                                   ["waterfall.stages:remote_method_setup"]))
    pcs = wf.get("prompt_executor_cache_setup")
    if pcs and pcs["duration_ms"] > 0:
        setup_children.append(_row("request.setup.cache_setup", "prompt executor cache setup", "request.setup",
                                   "exact", "critical", "APP", pcs["start_mono_ns"], pcs["end_mono_ns"],
                                   ["waterfall.stages:prompt_executor_cache_setup"]))
    method_entry_ns = None
    if led_method_entry:
        method_entry_ns = led_method_entry["start_mono_ns"]
        consumed_gt.add(id(led_method_entry))
    elif _samp(raw, "t4_modal_method_entry"):
        method_entry_ns = _samp(raw, "t4_modal_method_entry")
    if restore_end and method_entry_ns and method_entry_ns > restore_end:
        setup_children.append(_row("request.setup.restore_gap", "restore\u2192method entry gap", "request.setup",
                                   "derived", "critical", "APP", restore_end, method_entry_ns,
                                   ["gantt_telemetry.spans:restore method", "gantt_telemetry.spans:method entry"]))
    if setup_children:
        s0 = min(c.start_mono_ns for c in setup_children)
        s1 = max(c.end_mono_ns for c in setup_children)
        rows.append(_row("request.setup", "request/setup", None, "container", "critical", "APP", s0, s1,
                         ["waterfall.stages", "canonical_ledger"]))
        rows.extend(setup_children)

    # ---- VAE loader ------------------------------------------------------
    t4cs, t4ce = _samp(raw, "t4c_vae_load_start"), _samp(raw, "t4c_vae_load_end")
    if t4cs and t4ce and t4ce > t4cs:
        rows.append(_row("vae.loader", "VAE loader (t4c)", None, "container", "critical", "IO",
                         t4cs, t4ce, ["run_sample.full_trace.stages:t4c_vae_load_*"]))

    # ---- CLIPLoader node -------------------------------------------------
    t4s, t4e = _samp(raw, "t4_clip_load_start"), _samp(raw, "t4_clip_load_end")
    if t4s and t4e and t4e > t4s:
        clip_node = _row(
            "clip.node", "CLIPLoader (t4 node)", None, "container", "critical", "IO",
            t4s, t4e, ["run_sample.full_trace.stages:t4_clip_load_*"],
            adoption_mode=cfle_m.get("adoption_mode") or cfls_m.get("adoption_mode"),
            checkpoint_dtype=cfle_m.get("checkpoint_dtype") or cfls_m.get("checkpoint_dtype"),
            runtime_dtype=(cfle_m.get("expected_runtime_dtype")
                           or cfls_m.get("expected_runtime_dtype")),
            duplicate_weight_bytes_before_forward=cfle_m.get(
                "duplicate_weight_bytes_before_forward"
            ),
            model_sized_movement_detected=cfle_m.get("model_sized_movement_detected"),
        )
        rows.append(clip_node)
        comps = [
            ("clip.descriptor", "descriptor/header (exact)",
             float(cfle_m.get("descriptor_wall_ms") or cfls_m.get("descriptor_wall_ms") or 0.0),
             ["trace.events:clip_fast_load_end.descriptor_wall_ms"]),
            ("clip.fastsafe_setup", "FastSafe setup (exact)",
             float(cfle_m.get("fastsafe_setup_wall_ms") or 0.0),
             ["trace.events:clip_fast_load_end.fastsafe_setup_wall_ms"]),
            ("clip.copy", "FastSafe copy (exact)",
             float(cfle_m.get("fastsafe_copy_wall_ms") or 0.0),
             ["trace.events:clip_fast_load_end.fastsafe_copy_wall_ms"]),
            ("clip.construct", (
                "final-device skeleton construction (exact)"
                if cfle_m.get("construction_ex_loadsd_wall_ms")
                else "Comfy construction (exact)"
            ),
             float(cfle_m.get("construction_ex_loadsd_wall_ms")
                   or (cfle_m.get("bind_ms") or 0.0)),
             ["trace.events:clip_fast_load_end.construction_ex_loadsd_wall_ms",
              "trace.events:clip_fast_load_end.bind_ms[fallback]"]),
            ("clip.load_sd", "native load_sd cast-once BF16→FP16 (exact)",
             float(cfle_m.get("load_sd_wall_ms") or 0.0),
             ["trace.events:clip_fast_load_end.load_sd_wall_ms"]),
            ("clip.validation", "structural/bounded validation (exact)",
             float(cfle_m.get("validation_wall_ms") or 0.0),
             ["trace.events:clip_fast_load_end.validation_wall_ms"]),
            ("clip.residency", "residency registration (exact)",
             float(cfle_m.get("residency_register_wall_ms") or 0.0),
             ["trace.events:clip_fast_load_end.residency_register_wall_ms"]),
            ("clip.source_release", "source-owner retirement (exact)",
             float(cfle_m.get("owner_release_wall_ms") or 0.0),
             ["trace.events:clip_fast_load_end.owner_release_wall_ms"]),
        ]
        places = _seq_places(t4s, [c[2] for c in comps])
        for (key, label, dur, refs), (ps, pe) in zip(comps, places):
            if dur > 0:
                rows.append(_row(key, label, "clip.node", "exact", "critical", "IO", ps, pe, refs,
                                 anchoring="sequential-estimate"))

    # ---- CLIP encode (outer wrapper + inner forward) ---------------------
    outer_row = None
    if outer_ev and outer_ms:
        o_end = int(outer_ev["mono_ns"])
        o_start = o_end - int(round(outer_ms * _MS))
        outer_row = _row("clip.encode_outer", "CLIP outer encode", None, "exact", "critical", "CPU",
                         o_start, o_end,
                         ["trace.events:clip_forward_end[outer].wall_ms"])
    elif cre_s and cre_e and cre_e["mono_ns"] > cre_s["mono_ns"]:
        outer_row = _row("clip.encode_outer", "CLIP outer encode", None, "exact", "critical", "CPU",
                         cre_s["mono_ns"], cre_e["mono_ns"],
                         ["trace.events:clip_raw_encode_start", "trace.events:clip_raw_encode_end"])
    if outer_row is not None and gt_clip_fwd:
        cls = _classify_clip_forward(gt_clip_fwd["duration_ms"], inner_ms, outer_ms)
        if cls == "outer":
            outer_row.source_refs.append("gantt_telemetry.spans:CLIP forward")
            consumed_gt.add(id(gt_clip_fwd))
    if outer_row is not None:
        rows.append(outer_row)
        o_children: list[GanttRow] = []
        if lmg_rec:
            dur = float(lmg_rec.get("wall_ms") or 0.0)
            if dur > 0:
                o_children.append(_row("clip.lmg", "CLIP load_models_gpu (exact)", "clip.encode_outer",
                                       "exact", "critical", "CPU", outer_row.start_mono_ns,
                                       outer_row.start_mono_ns + int(round(dur * _MS)),
                                       ["pre_sampler_structured_report.cpu_owner_records[role=CLIP,op=load_models_gpu].wall_ms"],
                                       anchoring="parent-start"))
        inner_bounds = None
        if inner_ev:
            i_end = int(inner_ev["mono_ns"])
            inner_bounds = (i_end - int(round(inner_ms * _MS)), i_end)
            refs = ["trace.events:clip_forward_end[inner].duration_ms"]
        elif pipe_m.get("clip_forward_start_mono_ns") and pipe_m.get("clip_forward_end_mono_ns"):
            inner_bounds = (int(pipe_m["clip_forward_start_mono_ns"]), int(pipe_m["clip_forward_end_mono_ns"]))
            refs = ["trace.events:unet_fastsafe_pipeline.clip_forward_*_mono_ns"]
        if inner_bounds and inner_bounds[1] > inner_bounds[0]:
            if gt_clip_fwd and id(gt_clip_fwd) not in consumed_gt:
                cls = _classify_clip_forward(gt_clip_fwd["duration_ms"], inner_ms, outer_ms)
                if cls == "inner":
                    refs.append("canonical_ledger.spans:CLIP forward")
                    for ls in raw["led_spans"]:
                        if ls["name"] == "CLIP forward":
                            consumed_led.add(id(ls))
            o_children.append(_row("clip.inner", "CLIP inner forward", "clip.encode_outer",
                                   "exact", "critical", "GPU", inner_bounds[0], inner_bounds[1], refs))
        rows.extend(o_children)

    # ---- R44F structural events -------------------------------------------
    # CLIP FastSafe eligibility decision (e.g. native_adoption_ineligible /
    # dtype_parity_mismatch) is a first-class structural fact: render it as a
    # point row so adoption skips are never silently invisible.
    skip_ev = _ev(raw, "clip_fastsafe_skip")
    if skip_ev:
        _skip_meta = skip_ev.get("meta") or {}
        rows.append(_row("clip.fastsafe_skip", "CLIP FastSafe skip (eligibility)", None,
                         "point", "background", "IO",
                         int(skip_ev.get("mono_ns") or 0), int(skip_ev.get("mono_ns") or 0),
                         ["trace.events:clip_fastsafe_skip"],
                         reason=str(_skip_meta.get("reason") or ""),
                         detail=str(_skip_meta.get("detail") or "")))

    # ---- UNET source prep (background) ------------------------------------
    armed_ns = (armed or {}).get("meta", {}).get("armed_at_mono_ns")
    join_end = (joined or {}).get("meta", {}).get("join_end_mono_ns")
    if armed_ns and join_end and int(join_end) > int(armed_ns):
        rows.append(_row("unet.prep", "UNET source prep", None, "broad", "background", "IO",
                         int(armed_ns), int(join_end),
                         ["trace.events:unet_source_prep_armed.armed_at_mono_ns",
                          "trace.events:unet_source_prep_joined.join_end_mono_ns"]))

    # ---- UNETLoader node --------------------------------------------------
    t4bs, t4be = _samp(raw, "t4b_unet_load_start"), _samp(raw, "t4b_unet_load_end")
    if t4bs and t4be and t4be > t4bs:
        rows.append(_row("unet.node", "UNETLoader (t4b node)", None, "container", "critical", "IO",
                         t4bs, t4be, ["run_sample.full_trace.stages:t4b_unet_load_*"]))
        xfer_start = int(xfer_s["mono_ns"]) if xfer_s else None
        xfer_end = int(xfer_e["mono_ns"]) if xfer_e else None
        gate_ms = float(pipe_m.get("gate_wait_ms") or 0.0)
        if xfer_start and xfer_start > t4bs:
            seg_end = xfer_start - int(round(gate_ms * _MS)) if gate_ms else xfer_start
            if seg_end > t4bs:
                rows.append(_row("unet.entry_join", "entry/prep join (derived)", "unet.node",
                                 "derived", "critical", "IO", t4bs, seg_end,
                                 ["run_sample.full_trace.stages:t4b_unet_load_start",
                                  "trace.events:unet_gpu_transfer_start"],
                                 note="node start\u2192transfer start segment minus gate"))
        if gate_ms > 0 and xfer_start:
            rows.append(_row("unet.gate", "gate wait (exact)", "unet.node", "exact", "critical", "IO",
                             xfer_start - int(round(gate_ms * _MS)), xfer_start,
                             ["trace.events:unet_fastsafe_pipeline.gate_wait_ms"],
                             anchoring="transfer-start"))
        if xfer_start and xfer_end and xfer_end > xfer_start:
            comps = [
                ("unet.setup", "FastSafe setup (exact)",
                 float(pipe_m.get("fastsafe_setup_wall_ms") or 0.0),
                 ["trace.events:unet_fastsafe_pipeline.fastsafe_setup_wall_ms"]),
                ("unet.copy", "FastSafe copy (exact)",
                 float(pipe_m.get("fastsafe_copy_wall_ms") or 0.0),
                 ["trace.events:unet_fastsafe_pipeline.fastsafe_copy_wall_ms"]),
                ("unet.instantiate", "instantiate (exact)",
                 float(pipe_m.get("fastsafe_instantiate_wall_ms") or 0.0),
                 ["trace.events:unet_fastsafe_pipeline.fastsafe_instantiate_wall_ms"]),
                ("unet.adopt", "adoption (exact)",
                 float(pipe_m.get("adopt_ms") or 0.0),
                 ["trace.events:unet_fastsafe_pipeline.adopt_ms"]),
            ]
            places = _seq_places(xfer_start, [c[2] for c in comps])
            adopt_place = None
            for (key, label, dur, refs), (ps, pe) in zip(comps, places):
                if dur <= 0:
                    continue
                rows.append(_row(key, label, "unet.node", "exact", "critical", "IO", ps, pe, refs,
                                 anchoring="sequential-estimate"))
                if key == "unet.adopt":
                    adopt_place = (ps, pe)
            # grandchildren nested INSIDE adoption — reported but dropped from sums
            if adopt_place:
                nested = [
                    ("unet.header", "header detect", float(pipe_m.get("header_detect_wall_ms") or 0.0)),
                    ("unet.skeleton", "skeleton", float(pipe_m.get("skeleton_wall_ms") or 0.0)),
                    ("unet.bind", "bind", float(pipe_m.get("bind_wall_ms") or 0.0)),
                    ("unet.identity", "identity validation", float(pipe_m.get("identity_validation_wall_ms") or 0.0)),
                ]
                nplaces = _seq_places(adopt_place[0], [n[2] for n in nested])
                for (key, label, dur), (ps, pe) in zip(nested, nplaces):
                    if dur > 0:
                        rows.append(_row(key, label, "unet.adopt", "exact", "critical", "IO", ps, pe,
                                         [f"trace.events:unet_fastsafe_pipeline.{key.split('.')[-1]}_wall_ms"],
                                         nested_in="adoption", anchoring="sequential-estimate"))
        if xfer_s:
            consumed_event_xfer = True  # transfer events feed entry/gate/children context

    # ---- UNET H2D broad window (coexists with exact children) -------------
    if gt_h2d and gt_h2d["end_mono_ns"] > gt_h2d["start_mono_ns"]:
        consumed_gt.add(id(gt_h2d))
        rows.append(_row("unet.h2d_broad", "UNET H2D (broad window)", None, "broad", "critical", "GPU",
                         gt_h2d["start_mono_ns"], gt_h2d["end_mono_ns"],
                         ["gantt_telemetry.spans:UNET H2D"]))

    # ---- sampler / post-sampling / vae / output ---------------------------
    # R44H2: TRUE sampling-start semantics.  The authoritative wrapper
    # ``sampling_start`` event (or its backfilled pre_sampler_stages stamp,
    # never a progress proxy) splits the old misleading "sampler startup"
    # into orchestration/prep, first-eval startup, and first-step latency;
    # a durable ``sampler_tail`` attributes the post-loop region to the
    # RES4LYF sampler instead of a broad "post-sampling transition".
    psr_m = (_ev(raw, "pre_sampler_stages") or {}).get("meta", {})
    node_entry_ns = int(psr_m.get("first_sampler_node_monotonic_ns") or 0)
    true_ss_ns = 0
    ss_ev = _ev(raw, "sampling_start")
    if ss_ev:
        true_ss_ns = int(ss_ev.get("mono_ns") or 0)
    if not true_ss_ns and psr_m.get("sampling_start_monotonic_ns") \
            and str(psr_m.get("sampling_start_source") or "") != "proxy_first_progress":
        true_ss_ns = int(psr_m["sampling_start_monotonic_ns"])
    fe_ev = _ev(raw, "sampler_first_eval_start") or _ev(raw, "unet_first_cuda_op")
    first_eval_ns = int((fe_ev or {}).get("mono_ns") or 0)
    tail_ev = _ev(raw, "sampler_tail")
    tail_m = (tail_ev or {}).get("meta", {})

    st = wf.get("sampler_node_to_sampling")
    t6s, t6e = _samp(raw, "t6_sampler_start"), _samp(raw, "t6_sampler_end")

    if true_ss_ns:
        sampler_children: list[GanttRow] = []
        prep_start = node_entry_ns or (
            int(st["start_mono_ns"]) if st and st.get("start_mono_ns") else 0
        )
        if prep_start and true_ss_ns > prep_start:
            sampler_children.append(_row(
                "sampler.prep", "sampler orchestration/prep", "sampler.node",
                "exact", "critical", "APP", prep_start, true_ss_ns,
                ["trace.events:sampling_start"]
                + (["pre_sampler_stages.first_sampler_node_monotonic_ns"] if node_entry_ns else []),
            ))
        if first_eval_ns and t6s and true_ss_ns < first_eval_ns < t6s:
            sampler_children.append(_row(
                "sampler.first_eval_startup", "first-eval startup", "sampler.node",
                "exact", "critical", "GPU", true_ss_ns, first_eval_ns,
                ["trace.events:sampler_first_eval_start|unet_first_cuda_op"]))
            sampler_children.append(_row(
                "sampler.first_step_latency", "first-step latency", "sampler.node",
                "exact", "critical", "GPU", first_eval_ns, t6s,
                ["trace.events:sampler_first_eval_start|unet_first_cuda_op",
                 "run_sample.full_trace.stages:t6_sampler_start"]))
        elif t6s and true_ss_ns < t6s:
            sampler_children.append(_row(
                "sampler.first_eval_startup", "first-eval startup + first step (unsplit)",
                "sampler.node", "exact", "critical", "GPU", true_ss_ns, t6s,
                ["trace.events:sampling_start",
                 "run_sample.full_trace.stages:t6_sampler_start"]))
        if sampler_children:
            s_end = max(
                [c.end_mono_ns for c in sampler_children]
                + ([int(tail_m.get("end_mono_ns"))] if tail_m.get("end_mono_ns") else [])
                + ([t6e] if t6e else [])
            )
            rows.append(_row("sampler.node", "Sampler node", None, "container", "critical",
                             "APP", min(c.start_mono_ns for c in sampler_children), s_end,
                             ["trace.events:sampling_start", "pre_sampler_stages"]))
            rows.extend(sampler_children)
    elif st and st["duration_ms"] > 0:
        # Legacy/proxy interval: end boundary is the FIRST PROGRESS callback,
        # so it contains prep AND the first step(s).  Never labeled as a bare
        # "sampler startup".
        rows.append(_row("sampler.transition", 
                         "sampler node\u2192first progress (PROXY \u2014 incl. prep + first step)",
                         None, "exact", "critical", "APP",
                         st["start_mono_ns"], st["end_mono_ns"],
                         ["waterfall.stages:sampler_node_to_sampling[proxy]"],
                         proxy=True))
    wsamp = wf.get("sampling")
    if t6s and t6e and t6e > t6s:
        rows.append(_row("sampling", "progress sampling", None, "exact", "critical", "GPU", t6s, t6e,
                         ["run_sample.full_trace.stages:t6_sampler_*"]))
    elif wsamp and wsamp["duration_ms"] > 0:
        rows.append(_row("sampling", "progress sampling", None, "exact", "critical", "GPU",
                         wsamp["start_mono_ns"], wsamp["end_mono_ns"],
                         ["waterfall.stages:sampling"]))
    pst = wf.get("post_sampling_transition")
    if pst and pst["duration_ms"] > 0:
        rows.append(_row("post.sampling", "post-sampling transition", None, "broad", "critical", "APP",
                         pst["start_mono_ns"], pst["end_mono_ns"],
                         ["waterfall.stages:post_sampling_transition[broad parent/proxy]"]))
    if tail_m.get("start_mono_ns") and tail_m.get("end_mono_ns"):
        rows.append(_row("sampler.tail", "RES4LYF sampler post-loop tail", "post.sampling",
                         "exact", "critical", "CPU",
                         int(tail_m["start_mono_ns"]), int(tail_m["end_mono_ns"]),
                         ["trace.events:sampler_tail.wall_ms"],
                         gc_collect_ms=tail_m.get("gc_collect_ms"),
                         state_info_deepcopy_ms=tail_m.get("state_info_deepcopy_ms"),
                         cpu_transfer_wall_ms=tail_m.get("cpu_transfer_wall_ms"),
                         cpu_transfer_bytes=tail_m.get("cpu_transfer_bytes")))
        vae_ds = _ev(raw, "vae_decode_start")
        if vae_ds:
            gap_ms = (int(vae_ds["mono_ns"]) - int(tail_m["end_mono_ns"])) / _MS
            if 0.0 < gap_ms < 5000.0:
                rows.append(_row("post.executor_dispatch", "executor dispatch \u2192 VAEDecode",
                                 "post.sampling", "derived", "critical", "APP",
                                 int(tail_m["end_mono_ns"]), int(vae_ds["mono_ns"]),
                                 ["trace.events:sampler_tail.end",
                                  "trace.events:vae_decode_start"]))
    elif tail_m.get("wall_ms") and t6e:
        # wall-only tail (no mono stamps): anchor sequentially after sampling
        rows.append(_row("sampler.tail", "RES4LYF sampler post-loop tail", "post.sampling",
                         "exact", "critical", "CPU", t6e,
                         t6e + int(round(float(tail_m["wall_ms"]) * _MS)),
                         ["trace.events:sampler_tail.wall_ms"], anchoring="sequential-estimate"))
    t7s, t7e = _samp(raw, "t7_vae_decode_start"), _samp(raw, "t7_vae_decode_end")
    if gt_vae and gt_vae["end_mono_ns"] > gt_vae["start_mono_ns"]:
        consumed_gt.add(id(gt_vae))
        rows.append(_row("vae.decode", "VAE decode", None, "exact", "critical", "GPU",
                         gt_vae["start_mono_ns"], gt_vae["end_mono_ns"],
                         ["gantt_telemetry.spans:VAE decode"]))
    elif t7s and t7e and t7e > t7s:
        rows.append(_row("vae.decode", "VAE decode", None, "exact", "critical", "GPU", t7s, t7e,
                         ["run_sample.full_trace.stages:t7_vae_decode_*"]))
    if gt_oenc and gt_oenc["end_mono_ns"] > gt_oenc["start_mono_ns"]:
        consumed_gt.add(id(gt_oenc))
        rows.append(_row("output.encode", "output encode", None, "exact", "critical", "OUTPUT",
                         gt_oenc["start_mono_ns"], gt_oenc["end_mono_ns"],
                         ["gantt_telemetry.spans:output encode"]))
    op = wf.get("output_persistence")
    if op and op["duration_ms"] > 0:
        rows.append(_row("output.persist", "result persistence", None, "exact", "critical", "OUTPUT",
                         op["start_mono_ns"], op["end_mono_ns"],
                         ["waterfall.stages:output_persistence"]))

    # ---- unregistered activity (discovered dynamically) -------------------
    registered_labels = {r.label for r in rows}
    unreg: list[GanttRow] = []
    for s in raw["gt_spans"]:
        if id(s) in consumed_gt or s["name"] in ("restore_first_line", "restore_reconcile_start"):
            continue
        if s["end_mono_ns"] > s["start_mono_ns"]:
            unreg.append(_row(f"unreg:gt:{s['name']}", f"(unregistered) {s['name']}", None,
                              "broad", "background", s["lane"], s["start_mono_ns"], s["end_mono_ns"],
                              [f"gantt_telemetry.spans:{s['name']}"]))
    for s in raw["led_spans"]:
        if id(s) in consumed_led or s["duration_ms"] <= 0:
            continue
        unreg.append(_row(f"unreg:led:{s['name']}", f"(unregistered) {s['name']}", None,
                          "exact", "background", s["lane"], s["start_mono_ns"], s["end_mono_ns"],
                          [f"canonical_ledger.spans:{s['name']}"]))
    for e in raw["events"]:
        if e["name"] in _CONSUMED_EVENT_ALIASES:
            continue
        dur = e.get("dur_ms")
        if isinstance(dur, (int, float)) and dur > 0 and e.get("start_mono_ns") is not None:
            unreg.append(_row(f"event:{e['name']}", f"(unregistered) {e['name']}", None,
                              "exact", "background", "CPU", e["start_mono_ns"], e["end_mono_ns"],
                              [f"trace.events:{e['name']}"]))
    rows.extend(sorted(unreg, key=lambda r: (r.start_mono_ns, r.key)))

    rows.sort(key=lambda r: (r.start_mono_ns, r.key))
    return rows


# ── Windows ───────────────────────────────────────────────────────────────


def compute_windows(payload: DynamicPayload, rows: list[GanttRow]) -> dict[str, tuple[int, int]]:
    """Derive render windows from present boundary events (absent -> skipped)."""
    raw = payload.raw
    samp = raw["sample_stages"]
    wf = raw["waterfall_stages"]
    wins: dict[str, tuple[int, int]] = {}

    sl = raw["serial_ledger"] or {}
    full_s = None
    rs = next((r for r in rows if r.key == "restore"), None)
    if rs:
        full_s = rs.start_mono_ns
    elif sl.get("start_mono_ns"):
        full_s = int(sl["start_mono_ns"])
    full_e = int(sl["end_mono_ns"]) if sl.get("end_mono_ns") else None
    emit_ev = _ev(raw, "remote_result_emit")
    if full_e is None and emit_ev:
        full_e = int(emit_ev["mono_ns"])
    if full_s and full_e and full_e > full_s:
        wins["FULL APPLICATION"] = (full_s, full_e)

    def _samp_or(*keys: str) -> int | None:
        for k in keys:
            v = samp.get(k)
            if v:
                return int(v)
        return None

    method_entry = _samp_or("t4_modal_method_entry")
    me_row = next((r for r in rows if r.key == "request.setup"), None)
    if method_entry is None and me_row:
        method_entry = me_row.start_mono_ns
    t6s = _samp_or("t6_sampler_start")
    if method_entry and t6s and t6s > method_entry:
        wins["MODEL PREPARATION / PRE-SAMPLER"] = (method_entry, t6s)

    t4s = _samp_or("t4_clip_load_start")
    if t4s:
        ends = [v for v in (
            samp.get("t5_text_encode_end"),
            (_ev(raw, "clip_raw_encode_end") or {}).get("mono_ns") or None,
        ) if v]
        if ends:
            wins["CLIP DETAIL"] = (t4s, max(int(e) for e in ends))

    armed = _ev(raw, "unet_source_prep_armed")
    armed_ns = ((armed or {}).get("meta") or {}).get("armed_at_mono_ns")
    t4bs, t4be = _samp_or("t4b_unet_load_start"), _samp_or("t4b_unet_load_end")
    pipe = _ev(raw, "unet_fastsafe_pipeline")
    if (armed_ns or t4bs) and (t4be or pipe):
        lo = min(int(x) for x in (armed_ns, t4bs) if x)
        hi_candidates = [int(x) for x in (t4be, int(pipe["mono_ns"]) if pipe else None) if x]
        if hi_candidates:
            wins["UNET DETAIL"] = (lo, max(hi_candidates))

    if t4be and t6s and t6s >= t4be:
        wins["SAMPLER TRANSITION"] = (int(t4be), int(t6s))

    t6e = _samp_or("t6_sampler_end")
    persist_end = None
    op = wf.get("output_persistence")
    if op and op.get("end_mono_ns"):
        persist_end = int(op["end_mono_ns"])
    if persist_end is None:
        persist_end = _samp_or("t8bb_persist_end")
    if t6e and persist_end and persist_end > t6e:
        wins["POST-SAMPLING / VAE"] = (int(t6e), persist_end)

    t4be = _samp_or("t4b_unet_load_end")
    psr_m2 = (_ev(raw, "pre_sampler_stages") or {}).get("meta", {})
    node_entry_ns = int(psr_m2.get("first_sampler_node_monotonic_ns") or 0)
    tail_end_ns = int(((_ev(raw, "sampler_tail") or {}).get("meta") or {}).get("end_mono_ns") or 0)
    samp_detail_end = max([v for v in (t6e, tail_end_ns) if v], default=None)
    if node_entry_ns and samp_detail_end and samp_detail_end > node_entry_ns:
        wins["SAMPLER DETAIL"] = (node_entry_ns, int(samp_detail_end))

    dense = _auto_dense_window(rows, (full_e - full_s) if (full_s and full_e) else None)
    if dense:
        wins["AUTO-DENSE"] = dense
    return wins


def _auto_dense_window(rows: list[GanttRow], full_span_ns: int | None) -> tuple[int, int] | None:
    """Deterministic AUTO-DENSE selection (see module docstring)."""
    ivs = [(r.start_mono_ns, r.end_mono_ns) for r in rows if r.end_mono_ns > r.start_mono_ns]
    if len(ivs) < 3:
        return None
    span = 4 * _S
    best = None  # (score_tuple, lo, hi)
    for s0, _ in sorted(ivs):
        lim = s0 + span
        cluster = [(a, b) for (a, b) in ivs if a <= lim and b >= s0]
        if len(cluster) < 3:
            continue
        busy = sum(min(b, lim) - max(a, s0) for (a, b) in cluster)
        score = (len(cluster), busy, -s0)
        if best is None or score > best[0]:
            best = (score, s0, lim)
    if best is None:
        return None
    _, s0, lim = best
    members = [(a, b) for (a, b) in ivs if a <= lim and b >= s0]
    lo = min(a for a, _ in members)
    hi = max(b for _, b in members)
    clamp = min(full_span_ns, 8 * _S) if full_span_ns else 8 * _S
    if hi - lo > clamp:
        hi = lo + clamp
    return (lo, hi)


# ── Rendering ─────────────────────────────────────────────────────────────


def _bar(start: int, end: int, w0: int, w1: int, width: int) -> str:
    """Render a bar of ``width`` cells covering [w0,w1); only █/eighth-blocks."""
    step = (w1 - w0) / float(width)
    if step <= 0:
        return _BLOCK * width
    out = []
    for i in range(width):
        c0 = w0 + i * step
        c1 = c0 + step
        ov = min(end, c1) - max(start, c0)
        if ov <= 0:
            out.append(" ")
            continue
        frac = ov / step
        if frac >= 0.999:
            out.append(_BLOCK)
        else:
            idx = min(6, max(0, int(round(frac * 8)) - 1))
            out.append(_EIGHTHS[idx])
    return "".join(out)


def _pick_tick(step_ms: float) -> float:
    for tick in (1000.0, 500.0, 250.0, 100.0):
        if tick >= step_ms * 4:
            return tick
    return max(100.0, round(step_ms * 4))


def _ruler(w0: int, w1: int, width: int) -> list[str]:
    step_ms = (w1 - w0) / float(width) / _MS
    tick = _pick_tick(step_ms)
    tick_ns = tick * _MS
    marks = []
    for i in range(width):
        t = w0 + i * (w1 - w0) / width
        marks.append("\u253c" if abs(t / tick_ns - round(t / tick_ns)) < 1e-9 else "\u00b7")
    labels = []
    next_t = None
    for i in range(width):
        t = w0 + i * (w1 - w0) / width
        k = int(round(t / tick_ns))
        if abs(t / tick_ns - k) < 1e-9 and (next_t is None or k >= next_t):
            sec = (t - w0) / _S / 1000.0
            lab = f"{sec:.1f}s"
            labels.append((i, lab))
            next_t = k + max(1, int(len(lab) * 1000.0 / tick) + 1)
    label_line = [" "] * width
    for i, lab in labels:
        for j, ch in enumerate(lab):
            if i + j < width:
                label_line[i + j] = ch
    return ["".join(marks).rstrip(), "".join(label_line).rstrip()]


def _row_line(row: GanttRow, depth: int, w0: int, w1: int, width: int) -> str:
    label = truncate_label(("  " * depth) + row.label, _LABEL_COL)
    if row.kind == "point" or row.end_mono_ns <= row.start_mono_ns:
        pos = int((row.start_mono_ns - w0) / ((w1 - w0) / width))
        bar = [" "] * width
        if 0 <= pos < width:
            bar[pos] = _BLOCK
        bar = "".join(bar)
        off = (row.start_mono_ns - w0) / _MS
        right = f"@+{off / 1000.0:.3f}s"
    else:
        bar = _bar(row.start_mono_ns, row.end_mono_ns, w0, w1, width)
        off = (row.start_mono_ns - w0) / _MS
        right = f"{_fmt_ms(row.duration_ms)} ms @+{off / 1000.0:.3f}s"
    if row.role == "background":
        right += " \u00b7 [background]"
    return f"{label:<{_LABEL_COL}} \u2502{bar}\u2502 {right}"


def render_window(rows: list[GanttRow], window_bounds: tuple[int, int], title: str,
                  width_chars: int = 110, origin_mono_ns: int | None = None) -> str:
    """Render one window: header, scale, ruler, hierarchical bar rows, legend."""
    w0, w1 = int(window_bounds[0]), int(window_bounds[1])
    bar_width = max(20, int(width_chars) - _LABEL_COL - 4)
    sel = [r for r in rows if r.start_mono_ns < w1 and r.end_mono_ns > w0]
    sel.sort(key=lambda r: (r.start_mono_ns, r.key))

    by_parent: dict[str | None, list[GanttRow]] = {}
    for r in sel:
        by_parent.setdefault(r.parent_key, []).append(r)
    # keep parents present even if their own bounds fall outside via children
    keys_present = {r.key for r in sel}
    for r in list(sel):
        pk = r.parent_key
        while pk and pk not in keys_present:
            parent = next((x for x in rows if x.key == pk), None)
            if parent is None:
                break
            sel.append(parent)
            keys_present.add(pk)
            by_parent.setdefault(parent.parent_key, []).append(parent)
            pk = parent.parent_key
        # re-sort
    sel.sort(key=lambda r: (r.start_mono_ns, r.key))
    by_parent = {}
    for r in sel:
        by_parent.setdefault(r.parent_key, []).append(r)

    origin_label = "mono:0"
    if origin_mono_ns:
        match = next((r for r in rows if r.start_mono_ns == int(origin_mono_ns)), None)
        origin_label = match.key if match else f"mono:{int(origin_mono_ns)}"
    step_ms = (w1 - w0) / bar_width / _MS

    lines = [f"\u2500\u2500 {title} " + "\u2500" * max(4, width_chars - len(title) - 4)]
    lines.append(f"scale: 1 char = {step_ms:.1f} ms | axis {(w1 - w0) / _S:.1f} s | origin = {origin_label}")
    lines.extend(_ruler(w0, w1, bar_width))

    emitted: set[str] = set()

    def emit(parent_key: str | None, depth: int) -> None:
        for r in by_parent.get(parent_key, []):
            if r.key in emitted:
                continue
            emitted.add(r.key)
            lines.append(_row_line(r, depth, w0, w1, bar_width))
            emit(r.key, depth + 1)

    emit(None, 0)
    lines.append("legend: \u2588 busy bar (\u258f\u258e\u258d\u258c\u258b\u258a\u2589 sub-char precision); [background] marks "
                 "off-critical-path activity; see CRITICAL PATH SUMMARY")
    return "\n".join(lines)


# ── Closures (GOAL 6) ─────────────────────────────────────────────────────


def _closure_block(title: str, parent_label: str, parent_ms: float,
                   components: list[tuple[str, float]], nested_dropped: list[str],
                   notes: list[str] | None = None) -> str:
    lines = [f"\u2550\u2550 {title} \u2550\u2550"]
    lines.append(f"parent: {parent_label}  {_fmt_ms(parent_ms)} ms")
    comp_sum = 0.0
    for name, ms in components:
        lines.append(f"  component {name:<42} {_fmt_ms(ms)} ms")
        comp_sum += ms
    for note in (notes or []):
        lines.append(f"  note: {note}")
    if nested_dropped:
        lines.append("  note: dropped nested component(s) " + ", ".join(nested_dropped)
                     + " (contained in another listed component)")
    residual = parent_ms - comp_sum
    pct = (residual / parent_ms * 100.0) if parent_ms else 0.0
    lines.append(f"  sum(components)                               {_fmt_ms(comp_sum)} ms")
    lines.append(f"  residual                                      {_fmt_ms(residual)} ms ({pct:.2f}% of parent)")
    if residual < 0:
        lines.append("  CANNOT SUM (components exceed parent bounds)")
    else:
        ok = pct < _CLOSE_RES_PCT and residual < _CLOSE_RES_MS
        lines.append(("  \u2713 closes (residual <5% and <250 ms)" if ok
                      else "  \u2717 does not close (residual \u22655% or \u2265250 ms)"))
    return "\n".join(lines)


def closure_reports(payload: DynamicPayload, rows: list[GanttRow]) -> list[str]:
    """CLIP NODE / CLIP ENCODE / UNET NODE closure blocks (only when evidence exists)."""
    raw = payload.raw
    cfle_m = (_ev(raw, "clip_fast_load_end") or {}).get("meta", {})
    pipe_m = (_ev(raw, "unet_fastsafe_pipeline") or {}).get("meta", {})
    samp = raw["sample_stages"]
    reports: list[str] = []

    # CLIP NODE CLOSURE
    t4s, t4e = samp.get("t4_clip_load_start"), samp.get("t4_clip_load_end")
    parent_ms = ((t4e - t4s) / _MS) if (t4s and t4e and t4e > t4s) else cfle_m.get("wall_ms")
    comps = [
        ("descriptor/header (exact)", float(cfle_m.get("descriptor_wall_ms") or 0.0)),
        ("FastSafe setup (exact)", float(cfle_m.get("fastsafe_setup_wall_ms") or 0.0)),
        ("FastSafe copy (exact)", float(cfle_m.get("fastsafe_copy_wall_ms") or 0.0)),
        ("tensor views (exact)", float(cfle_m.get("fastsafe_get_keys_wall_ms") or 0.0)
         + float(cfle_m.get("fastsafe_get_tensor_loop_wall_ms") or 0.0)),
        ("Comfy construction (exact)", float(cfle_m.get("bind_ms") or 0.0)),
    ]
    if parent_ms and any(ms > 0 for _, ms in comps):
        reports.append(_closure_block("CLIP NODE CLOSURE", "CLIPLoader (t4 node)", float(parent_ms),
                                      [(n, m) for n, m in comps if m > 0], []))

    # CLIP ENCODE CLOSURE
    fwd = [e for e in raw["events"] if e["name"] == "clip_forward_end"]
    outer = next((e for e in fwd if "wall_ms" in e["meta"] and "allocated_delta_bytes" in e["meta"]), None)
    inner = next((e for e in fwd if "duration_ms" in e["meta"]
                  and ("cuda_no_sync" in e["meta"] or "thread_cpu_ms" in e["meta"])), None)
    lmg = next((rc for rc in raw["cpu_owner_records"]
                if rc.get("operation") == "load_models_gpu" and rc.get("role") == "CLIP"), None)
    if outer and inner:
        comps2 = []
        if lmg:
            comps2.append(("CLIP load_models_gpu (exact)", float(lmg.get("wall_ms") or 0.0)))
        comps2.append(("CLIP inner forward", float(inner["meta"]["duration_ms"])))
        reports.append(_closure_block("CLIP ENCODE CLOSURE", "CLIP outer encode",
                                      float(outer["meta"]["wall_ms"]),
                                      [(n, m) for n, m in comps2 if m > 0], []))

    # UNET NODE CLOSURE
    t4bs, t4be = samp.get("t4b_unet_load_start"), samp.get("t4b_unet_load_end")
    if t4bs and t4be and t4be > t4bs:
        parent2 = (t4be - t4bs) / _MS
        gate = float(pipe_m.get("gate_wait_ms") or 0.0)
        xfer_s = _ev(raw, "unet_gpu_transfer_start")
        xfer_e = _ev(raw, "unet_gpu_transfer_end")
        comps3: list[tuple[str, float]] = []
        nested: list[str] = []
        notes3: list[str] = []
        if xfer_s and xfer_e:
            xfer_ms = (int(xfer_e["mono_ns"]) - int(xfer_s["mono_ns"])) / _MS
            pre = parent2 - gate - xfer_ms
            if pre > 0:
                comps3.append(("entry/prep join (derived)", pre))
            if gate > 0:
                comps3.append(("gate wait (exact)", gate))
            comps3.append(("UNET H2D device transfer (exact window)", xfer_ms))
            inner_sum = (float(pipe_m.get("fastsafe_setup_wall_ms") or 0.0)
                         + float(pipe_m.get("fastsafe_copy_wall_ms") or 0.0)
                         + float(pipe_m.get("fastsafe_instantiate_wall_ms") or 0.0)
                         + float(pipe_m.get("adopt_ms") or 0.0))
            if inner_sum > 0:
                notes3.append(f"transfer decomposes into setup+copy+instantiate+adoption "
                              f"= {_fmt_ms(inner_sum)} ms (nested in transfer; excluded from sum)")
                for nm in ("header_detect", "skeleton", "bind", "identity_validation"):
                    if float(pipe_m.get(f"{nm}_wall_ms") or 0.0) > 0:
                        nested.append(nm.replace("_", " ") + " (in adoption)")
        if comps3:
            reports.append(_closure_block("UNET NODE CLOSURE", "UNETLoader (t4b node)", parent2,
                                          comps3, nested, notes3))
    return reports


# ── Completeness matrix (GOAL 7) ──────────────────────────────────────────


def completeness_matrix(payload: DynamicPayload) -> str:
    raw = payload.raw
    cfle_m = (_ev(raw, "clip_fast_load_end") or {}).get("meta", {})
    pipe_m = (_ev(raw, "unet_fastsafe_pipeline") or {}).get("meta", {})
    psr_m = (_ev(raw, "pre_sampler_stages") or {}).get("meta", {})
    samp = raw["sample_stages"]

    def has(cond: bool) -> bool:
        return bool(cond)

    fwd = [e for e in raw["events"] if e["name"] == "clip_forward_end"]
    has_outer = any("wall_ms" in e["meta"] and "allocated_delta_bytes" in e["meta"] for e in fwd)
    has_inner = any("duration_ms" in e["meta"] and ("cuda_no_sync" in e["meta"] or "thread_cpu_ms" in e["meta"])
                    for e in fwd)
    lmg = any(rc.get("operation") == "load_models_gpu" and rc.get("role") == "CLIP"
              for rc in raw["cpu_owner_records"])
    led_names = {s["name"] for s in raw["led_spans"]}

    items: list[tuple[str, bool, str, str]] = [
        ("CLIP descriptor", has(cfle_m.get("descriptor_wall_ms")),
         "trace.events:clip_fast_load_end.descriptor_wall_ms",
         "trace.events:clip_fast_load_start.descriptor_wall_ms"),
        ("CLIP exact copy", has(cfle_m.get("fastsafe_copy_wall_ms")),
         "trace.events:clip_fast_load_end.fastsafe_copy_wall_ms", "none"),
        ("CLIP construction", has(cfle_m.get("bind_ms")),
         "trace.events:clip_fast_load_end.bind_ms", "none"),
        ("CLIP storage identity", has(cfle_m.get("sampled_tensor_count")),
         "trace.events:clip_fast_load_end.sampled_tensor_count", "none"),
        ("CLIP load_models_gpu", has(lmg),
         "pre_sampler_structured_report.cpu_owner_records[op=load_models_gpu,role=CLIP]", "none"),
        ("CLIP inner forward", has(has_inner), "trace.events:clip_forward_end[inner].duration_ms",
         "gantt_telemetry.spans:CLIP forward"),
        ("CLIP outer encode", has(has_outer), "trace.events:clip_forward_end[outer].wall_ms",
         "trace.events:clip_raw_encode_end.duration_ms"),
        ("UNET source prep", has(_ev(raw, "unet_source_prep_armed") and _ev(raw, "unet_source_prep_joined")),
         "trace.events:unet_source_prep_armed/joined", "none"),
        ("UNET exact copy", has(pipe_m.get("fastsafe_copy_wall_ms")),
         "trace.events:unet_fastsafe_pipeline.fastsafe_copy_wall_ms", "none"),
        ("UNET broad H2D", has(_gt_span(raw, "UNET H2D") or _ev(raw, "unet_gpu_transfer_end")),
         "gantt_telemetry.spans:UNET H2D", "trace.events:unet_gpu_transfer_start/end"),
        ("UNET storage identity", has(pipe_m.get("storage_identity_total")),
         "trace.events:unet_fastsafe_pipeline.storage_identity_matched/total", "none"),
        ("sampler-start decomposition",
         has(_ev(raw, "sampler_prep_phase") or _ev(raw, "sampling_start")
             or (psr_m.get("sampling_start_monotonic_ns")
                 and str(psr_m.get("sampling_start_source") or "") != "proxy_first_progress")),
         "fine-grained sampler-node\u2192sampling sub-events", "waterfall.sampler_node_to_sampling"),
        ("post-sampling decomposition", has(_ev(raw, "sampler_tail")),
         "fine-grained post-sampling sub-events", "waterfall.post_sampling_transition"),
        ("VAE decode", has(_gt_span(raw, "VAE decode") or samp.get("t7_vae_decode_end")),
         "gantt_telemetry.spans:VAE decode", "run_sample.full_trace.stages:t7_vae_decode_*"),
        ("output encode", has(_gt_span(raw, "output encode") or _ev(raw, "output_encode_end")),
         "gantt_telemetry.spans:output encode", "result.phase_durations_ms:output_encode"),
        ("restore decomposition", has(any(n.startswith("restore:") for n in led_names)),
         "canonical_ledger.spans:restore:*", "result._restore_timing.snapshot_restore_ms"),
        ("request/setup decomposition", has(any(n.startswith("request:") for n in led_names)),
         "canonical_ledger.spans:request:*", "waterfall.stages:remote_method_setup"),
        # ── R44H2 sampler/post-sampling completeness ─────────────────────
        ("sampling wrapper start (true)",
         has(_ev(raw, "sampling_start")
             or (psr_m.get("sampling_start_monotonic_ns")
                 and str(psr_m.get("sampling_start_source") or "") != "proxy_first_progress")),
         "trace.events:sampling_start",
         "pre_sampler_stages.sampling_start_monotonic_ns[proxy_first_progress]"),
        ("sampler prep phase",
         has(_ev(raw, "sampler_prep_phase")
             or (psr_m.get("first_sampler_node_monotonic_ns")
                 and psr_m.get("sampling_start_monotonic_ns"))),
         "trace.events:sampler_prep_phase",
         "waterfall.sampler_node_to_sampling[node\u2192first-progress proxy]"),
        ("first eval start",
         has(_ev(raw, "sampler_first_eval_start") or _ev(raw, "unet_first_cuda_op")),
         "trace.events:sampler_first_eval_start|unet_first_cuda_op", "none"),
        ("first progress", has(samp.get("t6_sampler_start")),
         "run_sample.full_trace.stages:t6_sampler_start",
         "waterfall.sampling stage start"),
        ("per-step ticks", has(_ev(raw, "sampler_step_ticks")),
         "trace.events:sampler_step_ticks.steps[]",
         "t6 progress window / steps count"),
        ("sampler tail", has(_ev(raw, "sampler_tail")),
         "trace.events:sampler_tail.wall_ms",
         "derived: sampler node wall \u2212 startup \u2212 progress window"),
        ("tail GC split",
         has((_ev(raw, "sampler_tail") or {}).get("meta", {}).get("gc_collect_ms") is not None),
         "trace.events:sampler_tail.gc_collect_ms", "none"),
        ("tail deepcopy split",
         has((_ev(raw, "sampler_tail") or {}).get("meta", {}).get("state_info_deepcopy_ms")
             is not None),
         "trace.events:sampler_tail.state_info_deepcopy_ms", "none"),
        ("tail CPU transfer split",
         has((_ev(raw, "sampler_tail") or {}).get("meta", {}).get("cpu_transfer_wall_ms")
             is not None),
         "trace.events:sampler_tail.cpu_transfer_wall_ms/.cpu_transfer_bytes", "none"),
        ("VAE load_models_gpu mono timestamps",
         has(any(rc.get("operation") == "load_models_gpu"
                 and rc.get("start_mono_ns") and rc.get("end_mono_ns")
                 for rc in raw["cpu_owner_records"])),
         "pre_sampler_structured_report.cpu_owner_records[].start_mono_ns/end_mono_ns"
         "[caller=vae_decode]",
         "cpu_owner_records[].wall_ms only"),
    ]

    lines = ["\u2550\u2550 TELEMETRY COMPLETENESS \u2550\u2550"]
    for label, present, expected, proxy in items:
        if present:
            lines.append(f"{label:<34} PRESENT")
        else:
            lines.append(f"{label:<34} MISSING (expected: {expected}; closest proxy: {proxy})")
    return "\n".join(lines)


# ── Label conflicts (GOAL 8) ──────────────────────────────────────────────


def detect_label_conflicts(payload: DynamicPayload, rows: list[GanttRow]) -> list[str]:
    """Return human-readable label conflicts ([] when clean)."""
    conflicts: list[str] = []
    raw = payload.raw
    fwd = [e for e in raw["events"] if e["name"] == "clip_forward_end"]
    has_outer = any("wall_ms" in e["meta"] and "allocated_delta_bytes" in e["meta"] for e in fwd)
    has_inner = any("duration_ms" in e["meta"] and ("cuda_no_sync" in e["meta"] or "thread_cpu_ms" in e["meta"])
                    for e in fwd)
    if has_outer and has_inner and any(r.label == "CLIP forward" for r in rows):
        conflicts.append('bare "CLIP forward" label emitted while both outer and inner evidence exist '
                         '(must be "CLIP outer encode" / "CLIP inner forward")')
    if _gt_span(raw, "UNET H2D") and not any(r.label == "UNET H2D (broad window)" for r in rows) \
            and any(r.label == "FastSafe copy (exact)" and r.parent_key == "unet.node" for r in rows):
        conflicts.append('broad/exact substitution: exact UNET copy rendered without the broad '
                         '"UNET H2D (broad window)" row')
    # same label is legitimate across different parents (e.g. FastSafe copy under
    # CLIPLoader AND UNETLoader); only flag true duplicates within one parent scope
    by_label: dict[tuple[str | None, str], set[tuple[int, int]]] = {}
    for r in rows:
        by_label.setdefault((r.parent_key, r.label), set()).add((r.start_mono_ns, r.end_mono_ns))
    for (parent, label), spans in sorted(by_label.items(), key=lambda kv: (kv[0][0] or "", kv[0][1])):
        if len(spans) > 1:
            conflicts.append(f'duplicate label "{label}"'
                             + (f' under "{parent}"' if parent else "")
                             + f' used for {len(spans)} different spans')
    return conflicts


# ── Critical path vs background (GOAL 5) ──────────────────────────────────


def critical_path_summary(payload: DynamicPayload, rows: list[GanttRow]) -> str:
    raw = payload.raw
    crit = sorted((r for r in rows if r.role == "critical" and r.end_mono_ns > r.start_mono_ns),
                  key=lambda r: (r.start_mono_ns, r.key))
    bg = sorted((r for r in rows if r.role == "background"),
                key=lambda r: (r.start_mono_ns, r.key))

    # union coverage of critical rows (never summing overlapping rows)
    merged: list[list[int]] = []
    for r in crit:
        s, e = r.start_mono_ns, r.end_mono_ns
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    union_ms = sum((e - s) for s, e in merged) / _MS

    def bg_overlap_ms(r: GanttRow) -> float:
        return sum(_overlap_ns(r.start_mono_ns, r.end_mono_ns, s, e) for s, e in merged) / _MS

    lines = ["\u2550\u2550 CRITICAL PATH SUMMARY \u2550\u2550"]
    lines.append(f"union-based critical path total: {_fmt_ms(union_ms)} ms "
                 f"(over {len(crit)} critical rows; overlapping rows NOT summed)")
    pipe_m = (_ev(raw, "unet_fastsafe_pipeline") or {}).get("meta", {})
    ov_ms = pipe_m.get("unet_prep_overlap_ms")
    if isinstance(ov_ms, (int, float)) and ov_ms > 0:
        pct = pipe_m.get("unet_prep_overlap_pct_of_prep")
        lines.append(f"UNET source-prep overlap: {ov_ms:.3f} ms ({pct}% of prep) "
                     "\u2014 background read hidden under CLIP encode")
    lines.append("critical rows (time order):")
    for r in crit:
        lines.append(f"  {truncate_label(r.label, 52):<54} {_fmt_ms(r.duration_ms)} ms")
    lines.append("background:")
    if not bg:
        lines.append("  (none)")
    for r in bg:
        ov = bg_overlap_ms(r)
        contrib = max(0.0, r.duration_ms - ov)
        lines.append(f"  {truncate_label(r.label, 44):<46} "
                     f"activity_wall\u2248{_fmt_ms(r.duration_ms)} ms \u00b7 "
                     f"critical_path_contribution\u2248{_fmt_ms(contrib)} ms")
    lines.append("legend: critical = on the measured critical path; background = wall time largely "
                 "overlapping critical coverage; contribution = wall \u2212 overlap with the critical union")
    return "\n".join(lines)


# ── Stage summary (R44H2 §12) ─────────────────────────────────────────────


def stage_summary(payload: DynamicPayload, rows: list[GanttRow]) -> str:
    """Canonical per-model stage summary with UNAMBIGUOUS semantics.

    No future agent should need to reverse-engineer t6 semantics from
    source to understand what "sampler startup" means: every line names
    its exact boundary pair, and proxy intervals are labeled as proxies.
    """
    by_key = {r.key: r for r in rows}
    lines = ["\u2550\u2550 STAGE SUMMARY (canonical boundary semantics) \u2550\u2550"]

    def emit(section: str, entries: list[tuple[str, str]]) -> None:
        present = [(lab, by_key[k]) for lab, k in entries if k in by_key]
        if not present:
            return
        lines.append(section)
        for lab, r in present:
            suffix = ""
            if r.meta.get("proxy"):
                suffix = "  [PROXY \u2014 end boundary is FIRST PROGRESS, not sampling start]"
            lines.append(f"  {truncate_label(lab, 46):<48} {_fmt_ms(r.duration_ms)} ms{suffix}")

    emit("CLIP", [
        ("loader (CLIPLoader node)", "clip.node"),
        ("model/device prepare (load_models_gpu)", "clip.lmg"),
        ("inner transformer forward", "clip.inner"),
        ("outer encode wrapper", "clip.encode_outer"),
    ])
    unet_entries = [
        ("source prep activity (background read)", "unet.prep"),
        ("exact transfer (FastSafe copy)", "unet.copy"),
        ("adoption", "unet.adopt"),
        ("broad H2D window", "unet.h2d_broad"),
    ]
    unet_prep_note = None
    prep = by_key.get("unet.prep")
    outer = by_key.get("clip.encode_outer")
    if prep is not None and outer is not None:
        ov = _overlap_ns(prep.start_mono_ns, prep.end_mono_ns,
                         outer.start_mono_ns, outer.end_mono_ns) / _MS
        uncovered = max(0.0, prep.duration_ms - ov)
        unet_prep_note = (f"  UNET prep uncovered contribution          "
                          f"{_fmt_ms(uncovered)} ms "
                          f"(wall {_fmt_ms(prep.duration_ms)} \u2212 overlap {_fmt_ms(ov)})")
    emit("UNET", unet_entries)
    if unet_prep_note:
        lines.append(unet_prep_note)
    emit("SAMPLER", [
        ("node entry \u2192 true sampling_start (orchestration/prep)", "sampler.prep"),
        ("true sampling_start \u2192 first eval (first-eval startup)", "sampler.first_eval_startup"),
        ("first eval \u2192 first progress (first-step latency)", "sampler.first_step_latency"),
        ("progress window (first\u2192last progress)", "sampling"),
        ("post-loop tail (last progress \u2192 node return)", "sampler.tail"),
        ("node \u2192 first progress [legacy interval]", "sampler.transition"),
    ])
    vae_lmg_ms = None
    for rc in payload.raw.get("cpu_owner_records") or []:
        if rc.get("operation") == "load_models_gpu" and (
            rc.get("caller") == "vae_decode"
            or (isinstance(rc.get("roles"), list) and "vae" in [str(x).lower() for x in rc["roles"]])
        ):
            vae_lmg_ms = float(rc.get("wall_ms") or 0.0)
            break
    vae_lines: list[tuple[str, str]] = [("decode", "vae.decode")]
    if "vae.loader" in by_key:
        vae_lines.insert(0, ("loader (VAELoader node)", "vae.loader"))
    emit("VAE", vae_lines)
    if vae_lmg_ms:
        lines.append(f"  load_models_gpu (caller=vae_decode)         {_fmt_ms(vae_lmg_ms)} ms")
    return "\n".join(lines)


# ── Full report ───────────────────────────────────────────────────────────


def render_full_report(payload: DynamicPayload, windows: dict[str, tuple[int, int]] | None = None) -> str:
    rows = payload.rows or build_rows(payload)
    if windows is None:
        windows = compute_windows(payload, rows)
    ls = raw_ls = payload.raw.get("loader_selection") or {}
    fallbacks = sorted(k for k, v in raw_ls.items()
                       if isinstance(v, dict) and v.get("fallback_attempted"))
    out: list[str] = []
    out.append(GANTT_TITLE)
    out.append("\u2501" * min(110, max(len(GANTT_TITLE), 60)))
    out.append(f"request: {payload.request_id}   profile: {payload.raw.get('profile_name') or '?'}   "
               f"artifact: {payload.raw.get('run_file')}")
    if fallbacks:
        out.append("FALLBACK RUN \u2014 loader fallback attempted for: " + ", ".join(fallbacks))
    else:
        out.append("loader fallback: none")
    # ── R44H2 structural header facts (R44F/R44E reconciliation) ─────────
    raw = payload.raw
    _rs = raw.get("runtime_status") or {}
    if str(_rs.get("status") or "").upper() not in ("", "NOMINAL", "OK"):
        out.append("RUNTIME STATUS: " + str(_rs.get("status"))
                   + " reasons=" + ",".join(str(x) for x in (_rs.get("reasons") or [])))
    for _role, _ls_info in sorted((raw.get("loader_selection") or {}).items()):
        if isinstance(_ls_info, dict) and not str(_ls_info.get("observed") or "").strip():
            out.append(f"loader observed status: {_role}=UNOBSERVED "
                       f"(requested={_ls_info.get('requested')} effective={_ls_info.get('effective')})")
    _skip_ev = _ev(raw, "clip_fastsafe_skip")
    if _skip_ev:
        _sm = _skip_ev.get("meta") or {}
        out.append(f"CLIP FastSafe eligibility: SKIPPED reason={_sm.get('reason')}"
                   f"{' detail=' + str(_sm.get('detail')) if _sm.get('detail') else ''}")
        out.append('note: with the FastSafe arm skipped, CLIP ran the native path; '
                   '"CLIP outer encode"/"CLIP load_models_gpu" rows describe the FALLBACK, '
                   "not zero-copy adoption.")
    for w in payload.warnings:
        out.append(f"warning: {w}")
    out.append("")
    for name, bounds in windows.items():
        origin = bounds[0] if name in ("FULL APPLICATION",) else None
        out.append(render_window(rows, bounds, name, origin_mono_ns=origin))
        out.append("")
    closures = closure_reports(payload, rows)
    if closures:
        out.extend(closures)
        out.append("")
    conflicts = detect_label_conflicts(payload, rows)
    out.append("LABEL CONFLICTS: " + ("none" if not conflicts else ""))
    for c in conflicts:
        out.append(f"  \u0021 {c}")
    out.append("")
    out.append(completeness_matrix(payload))
    out.append("")
    out.append(critical_path_summary(payload, rows))
    out.append("")
    out.append(stage_summary(payload, rows))
    return "\n".join(out)


def render_run_dir(run_dir: str) -> str:
    """One-shot: load_run_artifacts + render_full_report."""
    payload = load_run_artifacts(run_dir)
    return render_full_report(payload)


def render_artifact_file(run_dir: str, run_file: str) -> str:
    """One-shot render of a SPECIFIC run artifact (multi-run campaigns)."""
    payload = load_run_artifacts(run_dir, run_file=run_file)
    return render_full_report(payload)
