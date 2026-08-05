"""Narrow strict validator for the V0/V1 VAE-policy experiment.

This module is a dependency-free library (stdlib only).  It consumes
"records" shaped like the benchmark artifacts produced by
``tools/benchmark_v2_direct._run_one``::

    {
      "run_index": 0,
      "request_id": "...",
      "vae_policy": {
          "requested_policy": "v0",          # from env at artifact build time
          "requested_prefetch_mode": "off",
          "applied_policy": "v0",            # from cpu_snapshot_vae_policy_ready
      },
      "provenance": {"workflow_hash": "...", "source_sha": "..."},
      "timing": {"vae_decode_ms": 123.4, ...},
      "waterfall": {
          "identity": {
              "restore_count": 1,
              "request_count": 1,
              "fresh": true,                # bool, or unambiguous str/bool form
              "restored_instance_id": "...",
          }
      },
      "result": {
          "trace": {
              "events": [
                  {"name": "cpu_snapshot_vae_policy_ready",
                   "metadata": {"policy": "v0", "prefetch_mode": "off"}},
                  {"name": "vae_early_activation_terminal",
                   "metadata": {"status": "ready", "transfer_count": 1}},
                  {"name": "sampling_end", "monotonic_ns": ...},
                  {"name": "vae_decode_end", "monotonic_ns": ...},
              ]
          }
      }
    }

Semantics
---------

The validator is deliberately narrow and fail-closed:

* A record must carry a requested policy and an applied policy, and they
  must match.  Requested prefetch must be ``off`` and the applied trace
  policy (the ``cpu_snapshot_vae_policy_ready`` event) must show prefetch
  off.
* The applied policy must be recovered from the ``cpu_snapshot_vae_policy_ready``
  trace event; a missing event is invalid (never invented).
* Timing must include ``vae_decode_ms`` and the waterfall identity must
  show ``restore_count == 1``, ``request_count == 1``, and ``fresh`` is
  unambiguously true.
* Trace evidence must prove successful CPU snapshot reuse/binding with
  exactly one VAE transfer (``vae_early_activation_terminal`` with
  ``status == "ready"`` and ``transfer_count == 1``).  Any fallback /
  failure / invalid terminal event makes the record invalid.
* An expected workflow hash (when supplied) must match the record's
  provenance identity; mismatched or missing identity is rejected.

By default ``strict=True``: missing decisive evidence is reported as
``status="invalid"`` and never downgraded to ``status="na"``.  A
``strict=False`` mode is kept for backward-compatible callers that want
``status="na"`` for *missing* (but not contradictory) evidence.

The matrix helper ``validate_matrix`` requires exactly two baseline V0
records and exactly two candidate V1 records, validates each record
strictly, and reports per-run plus median values for VAE decode time and
sampling-end-to-decode completion.  It never auto-selects a winner and
preserves any existing image-quality evidence present on the records.
"""

from __future__ import annotations

from typing import Any, Iterable, Iterator

__all__ = [
    "POLICY_READY_EVENT",
    "VAE_EA_TERMINAL_EVENT",
    "VAE_EA_FALLBACK_EVENT",
    "VAE_EA_FAILED_EVENT",
    "VAE_EA_INVALID_EVENT",
    "VALID_POLICIES",
    "validate_record",
    "validate_matrix",
    "requested_policy",
    "applied_policy",
    "extract_applied_vae_policy",
    "vae_decode_ms",
    "sampling_end_to_decode_end_ms",
    "waterfall_identity",
    "vae_transfer_count",
]

# ── Domain constants ─────────────────────────────────────────────────────

POLICY_READY_EVENT = "cpu_snapshot_vae_policy_ready"
VAE_EA_TERMINAL_EVENT = "vae_early_activation_terminal"
VAE_EA_FALLBACK_EVENT = "vae_early_activation_fallback"
VAE_EA_FAILED_EVENT = "vae_early_activation_failed"
VAE_EA_INVALID_EVENT = "vae_early_activation_invalid"

VALID_POLICIES = frozenset({"v0", "v1"})
PREFETCH_OFF = "off"

# Sampling-end event names (primary + historical alias).
_SAMPLING_END_NAMES = ("sampling_end", "sampler_end")
# VAE decode-end event names (primary + historical alias).
_VAE_DECODE_END_NAMES = ("vae_decode_end", "vae_decode_done")
# Applied prefetch keys checked on the policy-ready event metadata.
_PREFETCH_KEYS = ("prefetch_mode", "prefetch", "vae_prefetch_mode")

# Strings that unambiguously mean true / false when deserialised.
_TRUE_STRINGS = frozenset({"1", "true", "yes", "on"})
_FALSE_STRINGS = frozenset({"0", "false", "no", "off", ""})
_OFF_STRINGS = frozenset({"off", "false", "0", "none", "no", "disabled", ""})


# ── Low-level coercion helpers ───────────────────────────────────────────


def _coerce_bool(value: Any) -> bool | None:
    """Coerce *value* to bool, or ``None`` when it does not unambiguously
    mean true or false.  Accepts native bools, ints, and common serialised
    string/bool forms.  Unknown strings (e.g. ``"unknown"``) return ``None``.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in _TRUE_STRINGS:
            return True
        if lowered in _FALSE_STRINGS:
            return False
    return None


def _to_int(value: Any) -> int | None:
    """Coerce *value* to an int without silently dropping ambiguity."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return None


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return None


# ── Trace access ─────────────────────────────────────────────────────────


def _iter_events(record: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Yield trace event dicts from a record, de-duplicated by identity.

    Events are read from the top-level ``trace.events`` (flat unit-test
    records) and/or the nested ``result.trace.events`` (production
    artifact wrapper).
    """
    seen: set[int] = set()

    def _add(trace: Any) -> Iterator[dict[str, Any]]:
        if isinstance(trace, dict):
            events = trace.get("events")
            if isinstance(events, list):
                for event in events:
                    if isinstance(event, dict) and id(event) not in seen:
                        seen.add(id(event))
                        yield event

    if isinstance(record, dict):
        yield from _add(record.get("trace"))
        result = record.get("result")
        if isinstance(result, dict):
            yield from _add(result.get("trace"))


def _first_event(record: dict[str, Any], name: str) -> dict[str, Any] | None:
    for event in _iter_events(record):
        if event.get("name") == name:
            return event
    return None


def _first_event_any(
    record: dict[str, Any], names: Iterable[str]
) -> dict[str, Any] | None:
    names_set = set(names)
    for event in _iter_events(record):
        if event.get("name") in names_set:
            return event
    return None


def _event_meta(
    event: dict[str, Any] | None, key: str | None = None, default: Any = None
) -> Any:
    if event is None:
        return default
    meta = event.get("metadata")
    if not isinstance(meta, dict):
        return default
    return meta if key is None else meta.get(key, default)


def _event_mono_ns(record: dict[str, Any], name: str) -> int | None:
    event = _first_event(record, name)
    if event is None:
        return None
    val = event.get("monotonic_ns")
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return int(val)
    return None


# ── Backward-compatible basic helpers (return plain values, None when absent) ──


def requested_policy(record: dict[str, Any]) -> str | None:
    """Return the requested VAE policy, or ``None`` when absent/empty."""
    if not isinstance(record, dict):
        return None
    vp = record.get("vae_policy")
    if not isinstance(vp, dict):
        return None
    val = vp.get("requested_policy")
    if isinstance(val, str) and val.strip():
        return val.strip()
    return None


def requested_prefetch_mode(record: dict[str, Any]) -> str | None:
    if not isinstance(record, dict):
        return None
    vp = record.get("vae_policy")
    if not isinstance(vp, dict):
        return None
    val = vp.get("requested_prefetch_mode")
    if isinstance(val, str) and val.strip():
        return val.strip()
    return None


def extract_applied_vae_policy(record: dict[str, Any]) -> str | None:
    """Recover the applied VAE policy from the policy-ready trace event.

    Fail-closed: returns ``None`` when the event is missing or its
    ``policy`` field is empty.  Never invents a policy.
    """
    if not isinstance(record, dict):
        return None
    event = _first_event(record, POLICY_READY_EVENT)
    applied = _event_meta(event, "policy")
    if isinstance(applied, str) and applied.strip():
        return applied.strip()
    return None


def applied_policy(record: dict[str, Any]) -> str | None:
    """Alias for :func:`extract_applied_vae_policy` (plain, non-strict)."""
    return extract_applied_vae_policy(record)


def vae_decode_ms(record: dict[str, Any]) -> float | None:
    if not isinstance(record, dict):
        return None
    timing = record.get("timing")
    if not isinstance(timing, dict):
        return None
    return _to_float(timing.get("vae_decode_ms"))


def sampling_end_to_decode_end_ms(record: dict[str, Any]) -> float | None:
    """Return sampling_end -> vae_decode_end duration in ms, or None."""
    if not isinstance(record, dict):
        return None
    s = _event_mono_ns(record, _SAMPLING_END_NAMES[0])
    if s is None:
        s = _event_mono_ns(record, _SAMPLING_END_NAMES[1])
    e = _event_mono_ns(record, _VAE_DECODE_END_NAMES[0])
    if e is None:
        e = _event_mono_ns(record, _VAE_DECODE_END_NAMES[1])
    if s is None or e is None:
        return None
    delta = e - s
    if delta < 0:
        return None
    return round(delta / 1_000_000.0, 3)


def waterfall_identity(record: dict[str, Any]) -> dict[str, Any]:
    """Return the waterfall identity dict (falls back to top-level identity)."""
    if not isinstance(record, dict):
        return {}
    wf = record.get("waterfall")
    if isinstance(wf, dict):
        ident = wf.get("identity")
        if isinstance(ident, dict):
            return ident
    ident = record.get("identity")
    return ident if isinstance(ident, dict) else {}


def vae_transfer_count(record: dict[str, Any]) -> int | None:
    """Return the VAE transfer count from the terminal event, or None."""
    terminal = _first_event(record, VAE_EA_TERMINAL_EVENT)
    val = _event_meta(terminal, "transfer_count")
    if isinstance(val, bool):
        return 1 if val else 0
    return _to_int(val)


def _vae_terminal_status(record: dict[str, Any]) -> str | None:
    terminal = _first_event(record, VAE_EA_TERMINAL_EVENT)
    val = _event_meta(terminal, "status")
    if isinstance(val, str) and val.strip():
        return val.strip()
    return None


def _extract_applied_prefetch_mode(record: dict[str, Any]) -> str | None:
    """Return the applied prefetch value from the policy-ready event.

    Returns ``None`` when the event is missing or carries no prefetch key.
    """
    event = _first_event(record, POLICY_READY_EVENT)
    if event is None:
        return None
    meta = event.get("metadata")
    if not isinstance(meta, dict):
        return None
    for key in _PREFETCH_KEYS:
        if key in meta:
            return str(meta[key]).strip()
    return None


def _prefetch_is_off(value: str | None) -> bool | None:
    """True if *value* unambiguously means off; False if on; None if unknown."""
    if value is None:
        return None
    lowered = value.strip().lower()
    if lowered in _OFF_STRINGS:
        return True
    if lowered in _TRUE_STRINGS:
        return False
    return None


def _workflow_hash(record: dict[str, Any]) -> str | None:
    if not isinstance(record, dict):
        return None
    prov = record.get("provenance")
    if not isinstance(prov, dict):
        return None
    val = prov.get("workflow_hash")
    if isinstance(val, str) and val.strip():
        return val.strip()
    return None


def _run_index(record: dict[str, Any]) -> int | None:
    if not isinstance(record, dict):
        return None
    return _to_int(record.get("run_index"))


def _preserve_quality_evidence(record: dict[str, Any]) -> dict[str, Any]:
    """Pass through any image/quality evidence present on the record so it
    is never dropped by the matrix report (image-quality gates preserved)."""
    out: dict[str, Any] = {}
    if not isinstance(record, dict):
        return out
    for key, val in record.items():
        if isinstance(key, str) and (
            "image" in key.lower() or "quality" in key.lower()
        ):
            out[key] = val
    return out


# ── Strict record validation ─────────────────────────────────────────────


def validate_record(
    record: dict[str, Any],
    *,
    expected_workflow_hash: str | None = None,
    strict: bool = True,
) -> dict[str, Any]:
    """Validate a single V0/V1 record.

    Returns a dict::

        {
          "status": "valid" | "invalid" | "na",
          "run_index": int | None,
          "policy": str | None,
          "errors": [str, ...],
          "missing": [str, ...],     # decisive evidence that is absent
          "mismatch": [str, ...],    # evidence present but contradictory
          "metrics": {
              "policy": str | None,
              "vae_decode_ms": float | None,
              "sampling_end_to_decode_end_ms": float | None,
          },
        }

    In ``strict`` mode (default) any missing decisive evidence yields
    ``status="invalid"``.  In non-strict (backward-compatible) mode,
    missing-only evidence yields ``status="na"`` while contradictory
    evidence still yields ``status="invalid"``.
    """
    missing: list[str] = []
    mismatch: list[str] = []

    # 1. requested + applied policy present and matching
    req_policy = requested_policy(record)
    appl_policy = extract_applied_vae_policy(record)
    if req_policy is None:
        missing.append("missing requested policy")
    if appl_policy is None:
        missing.append("missing applied policy (cpu_snapshot_vae_policy_ready event absent/empty)")
    elif req_policy is not None and appl_policy != req_policy:
        mismatch.append(
            f"applied policy {appl_policy!r} != requested {req_policy!r}"
        )

    # 2. requested prefetch off + applied trace prefetch off
    req_prefetch = requested_prefetch_mode(record)
    if req_prefetch is None:
        missing.append("missing requested prefetch mode")
    elif req_prefetch.lower() != PREFETCH_OFF:
        mismatch.append(
            f"requested prefetch mode must be {PREFETCH_OFF!r}, got {req_prefetch!r}"
        )
    appl_prefetch = _extract_applied_prefetch_mode(record)
    if appl_prefetch is None:
        missing.append("applied trace policy shows no prefetch evidence (decisive)")
    elif _prefetch_is_off(appl_prefetch) is not True:
        mismatch.append(f"applied trace prefetch must be off, got {appl_prefetch!r}")

    # 3. require timing vae_decode_ms
    decode_ms = vae_decode_ms(record)
    if decode_ms is None:
        missing.append("missing vae_decode_ms timing")

    # 4. waterfall identity: restore_count==1, request_count==1, fresh true
    ident = waterfall_identity(record)
    restore_count = _to_int(ident.get("restore_count"))
    request_count = _to_int(ident.get("request_count"))
    fresh = _coerce_bool(ident.get("fresh"))
    if restore_count is None:
        missing.append("missing waterfall restore_count")
    elif restore_count != 1:
        mismatch.append(f"waterfall restore_count must be 1, got {restore_count}")
    if request_count is None:
        missing.append("missing waterfall request_count")
    elif request_count != 1:
        mismatch.append(f"waterfall request_count must be 1, got {request_count}")
    if fresh is None:
        missing.append("waterfall fresh is not unambiguously true")
    elif fresh is not True:
        mismatch.append(f"waterfall fresh must be true, got {ident.get('fresh')!r}")

    # 5. trace evidence of CPU snapshot reuse/binding + exactly one VAE transfer
    for bad_name in (VAE_EA_FALLBACK_EVENT, VAE_EA_FAILED_EVENT, VAE_EA_INVALID_EVENT):
        if _first_event(record, bad_name) is not None:
            mismatch.append(f"{bad_name} event present (fallback/mismatch invalid)")
    terminal_status = _vae_terminal_status(record)
    transfer_count = vae_transfer_count(record)
    if terminal_status is None:
        missing.append("missing vae_early_activation_terminal evidence (decisive)")
    elif terminal_status != "ready":
        mismatch.append(
            f"vae early activation status must be 'ready', got {terminal_status!r}"
        )
    if transfer_count is None:
        missing.append("missing vae transfer_count evidence")
    elif transfer_count != 1:
        mismatch.append(f"vae transfer_count must be 1, got {transfer_count}")

    # 6. expected workflow hash (only when supplied)
    if expected_workflow_hash is not None:
        actual_hash = _workflow_hash(record)
        if actual_hash is None:
            missing.append("missing workflow identity (provenance.workflow_hash)")
        elif actual_hash != expected_workflow_hash:
            mismatch.append(
                f"workflow hash mismatch: got {actual_hash!r}, expected {expected_workflow_hash!r}"
            )

    errors = missing + mismatch
    if not errors:
        status = "valid"
    elif strict:
        status = "invalid"
    elif mismatch:
        status = "invalid"
    else:
        status = "na"

    policy = req_policy
    return {
        "status": status,
        "run_index": _run_index(record),
        "policy": policy,
        "errors": errors,
        "missing": missing,
        "mismatch": mismatch,
        "metrics": {
            "policy": policy,
            "vae_decode_ms": decode_ms,
            "sampling_end_to_decode_end_ms": sampling_end_to_decode_end_ms(record),
        },
    }


# ── Matrix-level strict validation ───────────────────────────────────────


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return round((ordered[mid - 1] + ordered[mid]) / 2.0, 3)


def validate_matrix(
    records: list[dict[str, Any]],
    *,
    expected_workflow_hash: str | None = None,
    strict: bool = True,
) -> dict[str, Any]:
    """Validate a full V0/V1 matrix.

    Requires exactly two baseline V0 records and exactly two candidate V1
    records.  Each record is validated strictly.  Reports per-run and
    median values for ``vae_decode_ms`` and
    ``sampling_end_to_decode_end_ms`` per policy.  Never auto-selects a
    winner and preserves image-quality evidence.

    Returns a dict::

        {
          "status": "valid" | "invalid" | "na",
          "errors": [str, ...],
          "results": [validate_record result, ...],
          "summary": {
              "v0": {"count": 2, "per_run": [...], "median_vae_decode_ms": ...,
                     "median_sampling_end_to_decode_end_ms": ...},
              "v1": {...},
          },
          "winner": None,
          "counts": {"v0": int, "v1": int},
        }
    """
    if not isinstance(records, list):
        raise TypeError("records must be a list of record dicts")

    results = [
        validate_record(
            rec, expected_workflow_hash=expected_workflow_hash, strict=strict
        )
        for rec in records
    ]

    # Pair each validation result with its original record so per-run
    # image/quality evidence can be preserved without loss.
    paired = list(zip(records, results))
    v0 = [pair for pair in paired if pair[1]["policy"] == "v0"]
    v1 = [pair for pair in paired if pair[1]["policy"] == "v1"]

    errors: list[str] = []
    if len(v0) != 2:
        errors.append(f"baseline V0 requires exactly 2 records, got {len(v0)}")
    if len(v1) != 2:
        errors.append(f"candidate V1 requires exactly 2 records, got {len(v1)}")
    for res in results:
        if res["status"] != "valid":
            run = res["run_index"]
            errors.append(
                f"record {run}: {res['status']}: " + "; ".join(res["errors"])
            )

    def _group_summary(group: list[tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
        vae = [
            res["metrics"]["vae_decode_ms"]
            for _, res in group
            if res["metrics"]["vae_decode_ms"] is not None
        ]
        s2d = [
            res["metrics"]["sampling_end_to_decode_end_ms"]
            for _, res in group
            if res["metrics"]["sampling_end_to_decode_end_ms"] is not None
        ]
        per_run = [
            {
                "run_index": res["run_index"],
                "vae_decode_ms": res["metrics"]["vae_decode_ms"],
                "sampling_end_to_decode_end_ms": res["metrics"][
                    "sampling_end_to_decode_end_ms"
                ],
                "quality_evidence": _preserve_quality_evidence(rec),
            }
            for rec, res in group
        ]
        return {
            "count": len(group),
            "per_run": per_run,
            "median_vae_decode_ms": _median(vae),
            "median_sampling_end_to_decode_end_ms": _median(s2d),
        }

    if not errors:
        status = "valid"
    elif strict:
        status = "invalid"
    elif any(res["status"] == "invalid" for _, res in paired) or len(v0) != 2 or len(v1) != 2:
        status = "invalid"
    else:
        status = "na"

    return {
        "status": status,
        "errors": errors,
        "results": results,
        "summary": {"v0": _group_summary(v0), "v1": _group_summary(v1)},
        "winner": None,  # never auto-select
        "counts": {"v0": len(v0), "v1": len(v1)},
    }


# ── Minimal dependency-free CLI (no Modal) ───────────────────────────────


def _main(argv: list[str]) -> int:
    import json
    import sys

    if len(argv) < 2:
        print(
            "usage: python tools/compare_vae_policy_runs.py RECORD.json [RECORD.json ...] "
            "[--workflow-hash HASH]",
            file=sys.stderr,
        )
        return 2

    expected_hash: str | None = None
    paths: list[str] = []
    for arg in argv[1:]:
        if arg == "--workflow-hash":
            continue
        if expected_hash is None and arg.startswith("sha256:"):
            expected_hash = arg[len("sha256:"):]
            continue
        paths.append(arg)

    records = []
    for path in paths:
        with open(path, "r", encoding="utf-8") as fh:
            records.append(json.load(fh))

    result = validate_matrix(records, expected_workflow_hash=expected_hash)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result["status"] == "valid" else 1


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv))
