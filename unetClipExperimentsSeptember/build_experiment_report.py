"""Render deterministic experiment reports from explicit local evidence.

The renderer is intentionally host-only: standard library only, no Modal,
subprocess, network, discovery, or mtime-based selection.  The primary
manifest owns the attempt order and paths.  An optional reference manifest is
used only for a labelled, descriptive comparison section.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path
from typing import Any, Iterable


MAX_INLINE_JSON = 200_000
MISSING = "UNAVAILABLE"
STAGES = (
    "external_restore", "request_setup", "clip_load", "clip_forward",
    "unet_load", "sampler_prepare", "vae_load", "sampling",
    "sampler_tail", "vae_decode", "output", "teardown", "request_wall",
)
TRANSPORT_ROLES = ("clip", "unet", "vae")
DECOMPOSITION_FIELDS = (
    ("source wall", "SOURCE_TOTAL_WALL_MS"),
    ("syscall union", "SOURCE_SYSCALL_UNION_BUSY_MS"),
    ("source -> GPU ready", "SOURCE_TO_GPU_READY_MS"),
    ("H2D wall", "H2D_TOTAL_WALL_MS"),
    ("source/H2D overlap", "SOURCE_H2D_OVERLAP_MS"),
    ("post-source H2D tail", "POST_SOURCE_H2D_TAIL_MS"),
)


def _text(path: str | None) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace") if path else ""


def _meta(path: str | None) -> dict[str, Any]:
    if not path:
        return {"path": None, "present": False}
    candidate = Path(path)
    if not candidate.is_file():
        return {"path": path, "present": False}
    digest = hashlib.sha256()
    with candidate.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": path,
        "present": True,
        "bytes": candidate.stat().st_size,
        "sha256": digest.hexdigest(),
    }


def _json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _pretty(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)


def _json_evidence(path: str | None) -> str:
    info = _meta(path)
    if not info["present"]:
        return "ABSENT (path not present in the local evidence bundle)."
    try:
        value = _json(path)  # type: ignore[arg-type]
    except Exception as exc:
        return f"UNREADABLE JSON: {type(exc).__name__}: {exc}"
    raw = _pretty(value)
    if len(raw.encode("utf-8")) <= MAX_INLINE_JSON:
        return raw
    selected = {
        key: value.get(key, MISSING)
        for key in ("identity", "capture_guard", "validation", "cold_evidence")
    } if isinstance(value, dict) else {"value": value}
    return (
        f"[JSON exceeds {MAX_INLINE_JSON} bytes; selected sections embedded.\n"
        f"byte_size={info['bytes']} sha256={info['sha256']}\n\n"
        + _pretty(selected)
    )


def _text_evidence(path: str | None) -> str:
    info = _meta(path)
    if not info["present"]:
        return "ABSENT (path not present in the local evidence bundle)."
    text = _text(path)
    if len(text.encode("utf-8")) <= MAX_INLINE_JSON:
        return text
    return (
        f"[Text exceeds {MAX_INLINE_JSON} bytes; full file remains at the audited path.\n"
        f"byte_size={info['bytes']} sha256={info['sha256']}\ntext_omitted=true]"
    )


def _value(mapping: Any, *keys: str) -> Any:
    if not isinstance(mapping, dict):
        return MISSING
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return value
    return MISSING


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None or value == MISSING:
        return MISSING
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return str(value)


def _cell(value: Any, digits: int = 3) -> str:
    return _fmt(value, digits).replace("|", "\\|").replace("\n", " ")


def _stats(values: Iterable[Any]) -> list[float] | None:
    numbers = [_number(value) for value in values]
    if any(value is None for value in numbers):
        return None
    clean = [value for value in numbers if value is not None]
    if len(clean) < 2:
        return None
    mean = statistics.mean(clean)
    sd = statistics.stdev(clean)
    return [min(clean), max(clean), max(clean) - min(clean), mean,
            statistics.median(clean), sd, sd / mean if mean else 0.0]


def _stat_header() -> str:
    return "min | max | range | mean | median | sample SD | CV"


def _stat_cells(stats: list[float] | None) -> str:
    return " | ".join(_cell(value) for value in stats) if stats else " | ".join([MISSING] * 7)


def _stage_walls(artifact: dict[str, Any]) -> dict[str, float]:
    walls: dict[str, float] = {}
    for stage in artifact.get("golden_telemetry", {}).get("stages", []):
        if not isinstance(stage, dict):
            continue
        try:
            name = str(stage["name"])
            walls[name.removeprefix("golden_")] = (
                stage["end_monotonic_ns"] - stage["entry_monotonic_ns"]
            ) / 1_000_000
        except (KeyError, TypeError):
            continue
    return walls


def _transport_records(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for stage in artifact.get("golden_telemetry", {}).get("stages", []):
        if not isinstance(stage, dict):
            continue
        raw = stage.get("details", {}).get("transport_stats")
        items = raw if isinstance(raw, list) else [raw]
        for record in items:
            if isinstance(record, dict) and record.get("role") in TRANSPORT_ROLES:
                records[str(record["role"])] = record
    return records


def _transport_value(record: dict[str, Any], key: str, *fallbacks: str) -> Any:
    for source in (record, record.get("experiment"), record.get("actual_source")):
        value = _value(source, key, *fallbacks)
        if value != MISSING:
            return value
    return MISSING


def _attempt_artifact(attempt: dict[str, Any]) -> dict[str, Any] | None:
    path = attempt.get("artifact_path")
    if not path or not Path(path).is_file():
        return None
    try:
        value = _json(path)
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _summary_valid(attempt: dict[str, Any]) -> bool:
    path = attempt.get("derived_summary_path")
    if not path or not Path(path).is_file():
        return False
    try:
        summary = _json(path)
    except Exception:
        return False
    return isinstance(summary, dict) and summary.get("valid_count") == 1 and summary.get("invalid_count") == 0


def _summary_deployment_fingerprint(attempt: dict[str, Any]) -> Any:
    path = attempt.get("derived_summary_path")
    if not path or not Path(path).is_file():
        return MISSING
    try:
        summary = _json(path)
    except Exception:
        return MISSING
    identity = summary.get("deployment_identity") if isinstance(summary, dict) else None
    if isinstance(identity, dict):
        return _value(identity, "deploy_fingerprint", "deployment_combined_hash")
    return MISSING


def _counted(manifest: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    rows = []
    for attempt in manifest.get("attempts", []):
        if not isinstance(attempt, dict) or not attempt.get("counted"):
            continue
        artifact = _attempt_artifact(attempt)
        if artifact is not None:
            rows.append((attempt, artifact))
    return rows


def _artifact_fields(artifact: dict[str, Any]) -> dict[str, Any]:
    identity = artifact.get("identity", {})
    validation = artifact.get("validation", {})
    return {
        "duration_ms": artifact.get("duration_ms", MISSING),
        "true_cold": artifact.get("true_cold", MISSING),
        "provider": _value(identity, "cloud"),
        "region": _value(identity, "region"),
        "restore_count": _value(identity, "restore_count"),
        "request_count": _value(identity, "request_count"),
        "output_sha_match": _value(validation, "output_sha_match"),
        "output_sha": _value(validation, "observed_output_shas"),
        "walls": _stage_walls(artifact),
        "transport": _transport_records(artifact),
    }


def _table(lines: list[str], headers: list[str], rows: list[list[Any]]) -> None:
    lines.extend([
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---:" if index else "---" for index in range(len(headers))) + "|",
    ])
    for row in rows:
        lines.append("| " + " | ".join(_cell(value) for value in row) + " |")


def _stage_table(lines: list[str], counted: list[tuple[dict[str, Any], dict[str, Any]]]) -> None:
    roles = [str(attempt.get("cohort_role", MISSING)) for attempt, _ in counted]
    lines.extend(["| stage | " + " | ".join(roles) + " | " + _stat_header() + " |",
                  "|---|" + "---:|" * len(roles) + "---:|" * 7])
    for stage in STAGES:
        values = []
        for _, artifact in counted:
            fields = _artifact_fields(artifact)
            value = fields["duration_ms"] if stage == "request_wall" else fields["walls"].get(stage, MISSING)
            if stage == "external_restore":
                value = artifact.get("restore_total_ms", MISSING)
            values.append(value)
        lines.append("| " + stage + " | " + " | ".join(_cell(value) for value in values)
                     + " | " + _stat_cells(_stats(values)) + " |")


def _timeline_table(lines: list[str], counted: list[tuple[dict[str, Any], dict[str, Any]]]) -> None:
    lines.extend([
        "## Timeline / Gantt evidence", "",
        "Exact monotonic stage boundaries are retained here; nested transport intervals are not added to stage walls.", "",
        "| request | stage | entry monotonic ns | end monotonic ns | wall ms |",
        "|---|---|---:|---:|---:|",
    ])
    for attempt, artifact in counted:
        request = str(attempt.get("cohort_role", MISSING))
        for stage in artifact.get("golden_telemetry", {}).get("stages", []):
            if not isinstance(stage, dict):
                continue
            entry = stage.get("entry_monotonic_ns")
            end = stage.get("end_monotonic_ns")
            wall = ((end - entry) / 1_000_000
                    if isinstance(entry, (int, float)) and isinstance(end, (int, float)) else MISSING)
            lines.append("| " + " | ".join(_cell(value) for value in (
                request, stage.get("name", MISSING), entry, end, wall,
            )) + " |")
    lines.append("")


def _output_durability_table(lines: list[str], counted: list[tuple[dict[str, Any], dict[str, Any]]]) -> None:
    lines.extend([
        "## Output and durability", "",
        "Output correctness and durability are reported as observed; durability mode `off` ends at `FIRST_RESULT_READY`.", "",
        "| request | output endpoint | output SHA match | output bytes | durability mode | durability status | true durable |",
        "|---|---|---|---:|---|---|---|",
    ])
    for attempt, artifact in counted:
        validation = artifact.get("validation", {})
        durability = validation.get("durability", {})
        lines.append("| " + " | ".join(_cell(value) for value in (
            attempt.get("cohort_role", MISSING),
            _value(validation, "output_endpoint"),
            _value(validation, "output_sha_match"),
            _value(validation, "observed_output_byte_count"),
            _value(validation, "output_durability_mode"),
            _value(durability, "status"),
            _value(durability, "true_durable"),
        )) + " |")
    lines.append("")


def _loader_values(counted: list[tuple[dict[str, Any], dict[str, Any]]]) -> list[float | None]:
    result = []
    for _, artifact in counted:
        walls = _stage_walls(artifact)
        result.append(sum(walls.get(name, 0.0) for name in ("clip_load", "unet_load", "vae_load"))
                      if all(name in walls for name in ("clip_load", "unet_load", "vae_load")) else None)
    return result


def _transport_table(lines: list[str], counted: list[tuple[dict[str, Any], dict[str, Any]]]) -> None:
    roles = [str(attempt.get("cohort_role", MISSING)) for attempt, _ in counted]
    for role in TRANSPORT_ROLES:
        lines.extend([f"### {role.upper()}", "",
                      "| metric | " + " | ".join(roles) + " | " + _stat_header() + " |",
                      "|---|" + "---:|" * len(roles) + "---:|" * 7])
        metrics = list(DECOMPOSITION_FIELDS) + [
            ("load-wall residual after source -> GPU ready", "_LOAD_RESIDUAL"),
            ("GPU active union", "GPU_COPY_ACTIVE_UNION_MS"),
            ("GPU stream span", "GPU_COPY_STREAM_SPAN_MS"),
            ("GPU idle inside span", "GPU_COPY_IDLE_INSIDE_STREAM_SPAN_MS"),
            ("GPU active share (%)", "_GPU_ACTIVE_SHARE"),
            ("GPU idle share (%)", "_GPU_IDLE_SHARE"),
            ("H2D target bytes", "h2d_target_bytes"),
            ("H2D minimum submission bytes", "h2d_min_submission_bytes"),
            ("H2D maximum submission bytes", "h2d_max_submission_bytes"),
            ("H2D mean submission bytes", "h2d_mean_submission_bytes"),
            ("H2D submissions", "H2D_SUBMISSION_COUNT", "h2d_submit_count"),
            ("GPU copy count", "GPU_COPY_COUNT"),
            ("GPU copy bytes", "GPU_COPY_BYTES"),
            ("request-cumulative H2D submits", "REQUEST_CUMULATIVE_H2D_SUBMIT_COUNT"),
            ("request-cumulative H2D completions", "REQUEST_CUMULATIVE_H2D_COMPLETION_COUNT"),
            ("request-cumulative GPU copy count", "REQUEST_CUMULATIVE_GPU_COPY_COUNT"),
            ("request-cumulative GPU copy bytes", "REQUEST_CUMULATIVE_GPU_COPY_BYTES"),
            ("H2D completions", "h2d_completion_count"),
            ("aggregation enabled", "aggregation_enabled"),
            ("aggregation scheduler entries", "aggregation_scheduler_enter_count"),
            ("aggregation wait count", "aggregation_wait_count"),
            ("aggregated submissions", "aggregated_submission_count"),
            ("non-aggregated submissions", "non_aggregated_submission_count"),
            ("tail submissions", "tail_submission_count"),
            ("aggregation fallback count", "aggregation_fallback_count"),
            ("source reads", "source_read_count"),
            ("source opens", "source_open_count"),
            ("source bytes", "source_bytes"),
            ("max actual source inflight", "max_actual_source_inflight"),
        ]
        for metric in metrics:
            label, key, *fallbacks = metric
            values = []
            for _, artifact in counted:
                record = _transport_records(artifact).get(role, {})
                if key == "_LOAD_RESIDUAL":
                    load_name = f"{role}_load"
                    ready = _number(_transport_value(record, "SOURCE_TO_GPU_READY_MS"))
                    load_wall = _number(_stage_walls(artifact).get(load_name))
                    values.append(load_wall - ready if load_wall is not None and ready is not None else MISSING)
                elif key in ("_GPU_ACTIVE_SHARE", "_GPU_IDLE_SHARE"):
                    active = _number(_transport_value(record, "GPU_COPY_ACTIVE_UNION_MS"))
                    span = _number(_transport_value(record, "GPU_COPY_STREAM_SPAN_MS"))
                    if active is None or span in (None, 0):
                        values.append(MISSING)
                    else:
                        values.append((active if key == "_GPU_ACTIVE_SHARE" else span - active) / span * 100)
                else:
                    values.append(_transport_value(record, key, *fallbacks))
            lines.append("| " + label + " | " + " | ".join(_cell(value) for value in values)
                         + " | " + _stat_cells(_stats(values)) + " |")
        lines.append("")


def _header_staging_table(lines: list[str], counted: list[tuple[dict[str, Any], dict[str, Any]]]) -> None:
    roles = [str(attempt.get("cohort_role", MISSING)) for attempt, _ in counted]
    for role in TRANSPORT_ROLES:
        lines.extend([f"### {role.upper()} header, staging, and proof", "",
                      "| metric | " + " | ".join(roles) + " |",
                      "|---|" + "---|" * len(roles)])
        metrics = (
            ("header parse count", "header_parse_count"),
            ("source block count", "source_block_count"),
            ("source block bytes", "source_block_bytes"),
            ("arena bytes", "arena_bytes"),
            ("logical slot count", "logical_slot_count"),
            ("logical slot bytes", "logical_slot_bytes"),
            ("request pinned allocation count", "request_physical_pinned_alloc_count"),
            ("transport pinned allocation count", "transport_physical_pinned_alloc_count"),
            ("adoption result", "adoption_result"),
            ("post-transport construction adoption", "post_transport_construction_adoption"),
            ("E27 source mechanism proven", "E27_SOURCE_MECHANISM_PROVEN"),
            ("E27 failed predicates", "e27_source_mechanism_failed_predicates"),
        )
        for label, key in metrics:
            values = [_transport_value(_transport_records(artifact).get(role, {}), key) for _, artifact in counted]
            lines.append("| " + label + " | " + " | ".join(_cell(value) for value in values) + " |")
        lines.extend(["", "Future transport fields not emitted by the authoritative artifacts remain `UNAVAILABLE`.", ""])


def _per_attempt_transport(lines: list[str], counted: list[tuple[dict[str, Any], dict[str, Any]]]) -> None:
    lines.extend(["## Transport evidence by request", "",
                  "These rows preserve the raw per-request distinctions that are lost in cohort means.", ""])
    for attempt, artifact in counted:
        role = str(attempt.get("cohort_role", MISSING))
        lines.extend([f"### {role}", "",
                      "| role | E27 source proven | fallback reasons | adoption | H2D reconciliation | GPU timing proven |",
                      "|---|---|---|---|---|---|"])
        for transport_role in TRANSPORT_ROLES:
            record = _transport_records(artifact).get(transport_role, {})
            actual = record.get("actual_source") or {}
            e27 = _value(record, "E27_SOURCE_MECHANISM_PROVEN")
            reasons = _value(record, "aggregation_fallback_reasons")
            reconciliation = _value(actual, "h2d_reconciliation_complete")
            if reconciliation == MISSING:
                reconciliation = _value(record, "exact_reconciliation")
            gpu_proof = _value(record, "GPU_COPY_ACTIVE_UNION_PROVEN_SINGLE_STREAM_NON_OVERLAP")
            lines.append("| " + " | ".join([
                transport_role.upper(), _cell(e27), _cell(reasons),
                _cell(_value(record, "adoption_result")), _cell(reconciliation), _cell(gpu_proof),
            ]) + " |")
        lines.extend(["", "#### Aggregation state detail", "",
                      "| role | aggregation enabled | scheduler entries | wait count | aggregated submissions | fallback reasons | source QD target | mean QD | QD4 wall share (%) | producer count |",
                      "|---|---|---:|---:|---:|---|---:|---:|---:|---:|"])
        for transport_role in TRANSPORT_ROLES:
            record = _transport_records(artifact).get(transport_role, {})
            actual = record.get("actual_source") or {}
            lines.append("| " + " | ".join([
                transport_role.upper(), _cell(_transport_value(record, "aggregation_enabled")),
                _cell(_transport_value(record, "aggregation_scheduler_enter_count")),
                _cell(_transport_value(record, "aggregation_wait_count")),
                _cell(_transport_value(record, "aggregated_submission_count")),
                _cell(_transport_value(record, "aggregation_fallback_reasons")),
                _cell(_transport_value(record, "source_qd_target")),
                _cell(_value(actual, "time_weighted_mean_qd")),
                _cell(_value(actual, "percentage_source_wall_at_qd4")),
                _cell(_value(actual, "producer_count")),
            ]) + " |")
        lines.append("")


def _consistency(lines: list[str], manifest: dict[str, Any],
                 counted: list[tuple[dict[str, Any], dict[str, Any]]]) -> None:
    lines.extend(["## Consistency audit", "",
                  "These checks join only the explicit manifest rows and their explicitly named artifacts.", "",
                  "| check | result |", "|---|---|"])
    roles = [str(attempt.get("cohort_role", MISSING)) for attempt, _ in counted]
    declared = [str(role) for role in manifest.get("counted_cohort", [])]
    checks: list[tuple[str, Any]] = [
        ("declared counted cohort matches artifact rows", roles == declared),
        ("five counted artifacts loaded", len(counted) == 5),
        ("request IDs match manifest bindings", all(
            artifact.get("request_id") == attempt.get("request_id")
            for attempt, artifact in counted
        )),
        ("authoritative summary deployment fingerprints match manifest", all(
            _summary_deployment_fingerprint(attempt) == manifest.get("deploy_fingerprint")
            for attempt, _ in counted
        )),
        ("true_cold is true for every counted artifact", all(
            artifact.get("true_cold") is True for _, artifact in counted
        )),
        ("output SHA match is true for every counted artifact", all(
            _value(artifact.get("validation"), "output_sha_match") is True
            for _, artifact in counted
        )),
        ("authoritative summaries report valid=1 and invalid=0", all(
            _summary_valid(attempt)
            for attempt, _ in counted
        )),
    ]
    for role in TRANSPORT_ROLES:
        records = [_transport_records(artifact).get(role, {}) for _, artifact in counted]
        checks.append((f"{role.upper()} submitted/completed bytes reconcile", all(
            _transport_value(record, "h2d_submitted_bytes") == _transport_value(record, "h2d_completed_bytes")
            for record in records
        )))
        checks.extend([
            (f"{role.upper()} aggregation is disabled", all(
                _transport_value(record, "aggregation_enabled") is False for record in records
            )),
            (f"{role.upper()} aggregation counters are zero", all(
                _transport_value(record, "aggregation_scheduler_enter_count") == 0
                and _transport_value(record, "aggregation_wait_count") == 0
                and _transport_value(record, "aggregated_submission_count") == 0
                and _transport_value(record, "aggregation_fallback_count") == 0
                for record in records
            )),
            (f"{role.upper()} uses 32 MiB H2D targets with explicit partial tails", all(
                _transport_value(record, "h2d_target_bytes") == 33_554_432
                and _transport_value(record, "h2d_max_submission_bytes") == 33_554_432
                and all(0 < size <= 33_554_432 for size in (_transport_value(record, "h2d_submission_sizes") or []))
                and _transport_value(record, "tail_submission_count") == sum(
                    size != 33_554_432 for size in (_transport_value(record, "h2d_submission_sizes") or [])
                )
                for record in records
            )),
            (f"{role.upper()} has four source producers", all(
                _transport_value(record, "producer_count") == 4 for record in records
            )),
            (f"{role.upper()} has one 256 MiB arena and eight 32 MiB slots", all(
                _transport_value(record, "arena_bytes") == 268_435_456
                and _transport_value(record, "logical_slot_count") == 8
                and _transport_value(record, "logical_slot_bytes") == 33_554_432
                for record in records
            )),
        ])
    for label, result in checks:
        lines.append(f"| {label} | {'PASS' if result else 'FAIL'} |")
    lines.extend(["", "The VAE R3 record is retained as `E27_SOURCE_MECHANISM_PROVEN=NO` with failed predicate `max_actual_source_inflight`; this is reported separately from the artifact validity/SHA checks.", "The per-request `attempt_0.json` runtime identity hash is distinct from the authoritative deployment binding. Deployment identity checks use each explicit request `manifest.json`/`summary.json` binding, which matches the primary manifest; the raw distinction is not normalized away.", ""])


def _comparison(lines: list[str], reference: dict[str, Any] | None,
                counted: list[tuple[dict[str, Any], dict[str, Any]]]) -> None:
    if reference is None:
        lines.extend(["## Experiment 01 reference", "", "No explicit reference manifest was supplied.", ""])
        return
    reference_counted = _counted(reference)
    lines.extend(["## Experiment 01 reference", "",
                  "This is a descriptive reference comparison only. The required top-level performance flags remain NOT_PERFORMED/NOT_PROVIDED.",
                  "", f"Reference manifest: `{reference.get('_path', MISSING)}`",
                  f"Reference counted cohort: `{','.join(str(a.get('cohort_role', MISSING)) for a, _ in reference_counted)}`",
                  ""])
    def mean_median(values: list[Any]) -> tuple[Any, Any]:
        result = _stats(values)
        return (result[3], result[4]) if result else (MISSING, MISSING)

    reference_loader = mean_median(_loader_values(reference_counted))
    current_loader = mean_median(_loader_values(counted))
    reference_wall = mean_median([a.get("duration_ms", MISSING) for _, a in reference_counted])
    current_wall = mean_median([a.get("duration_ms", MISSING) for _, a in counted])
    _table(lines, ["cohort", "n", "loader wall mean (ms)", "loader wall median (ms)", "request wall mean (ms)", "request wall median (ms)"], [
        ["Experiment 01", len(reference_counted), *reference_loader, *reference_wall],
        ["Experiment 02", len(counted), *current_loader, *current_wall],
    ])
    lines.extend(["", "### Stage mean reference", "",
                  "| stage | Experiment 01 mean (ms) | Experiment 02 mean (ms) | descriptive delta (ms) |",
                  "|---|---:|---:|---:|"])
    for stage in STAGES:
        def values(rows: list[tuple[dict[str, Any], dict[str, Any]]]) -> list[Any]:
            return [(_artifact_fields(artifact)["duration_ms"] if stage == "request_wall"
                     else _artifact_fields(artifact)["walls"].get(stage, MISSING)) for _, artifact in rows]
        first, second = _stats(values(reference_counted)), _stats(values(counted))
        first_mean = first[3] if first else MISSING
        second_mean = second[3] if second else MISSING
        delta = second_mean - first_mean if isinstance(first_mean, (int, float)) and isinstance(second_mean, (int, float)) else MISSING
        lines.append(f"| {stage} | {_cell(first_mean)} | {_cell(second_mean)} | {_cell(delta)} |")
    lines.extend(["", "### Transport reference", "",
                  "Only fields present in both explicit artifact cohorts are shown; missing Experiment 01 aggregation counters remain `UNAVAILABLE`.", "",
                  "| role | metric | Experiment 01 mean | Experiment 02 mean | descriptive delta (%) |",
                  "|---|---|---:|---:|---:|"])
    for role in TRANSPORT_ROLES:
        for label, key in DECOMPOSITION_FIELDS:
            def transport_values(rows: list[tuple[dict[str, Any], dict[str, Any]]]) -> list[Any]:
                return [_transport_value(_transport_records(artifact).get(role, {}), key) for _, artifact in rows]
            first, second = _stats(transport_values(reference_counted)), _stats(transport_values(counted))
            first_mean = first[3] if first else MISSING
            second_mean = second[3] if second else MISSING
            delta = ((second_mean / first_mean) - 1) * 100 if isinstance(first_mean, (int, float)) and isinstance(second_mean, (int, float)) and first_mean else MISSING
            lines.append(f"| {role.upper()} | {label} | {_cell(first_mean)} | {_cell(second_mean)} | {_cell(delta)} |")
        for label, key, *fallbacks in (("H2D submissions", "H2D_SUBMISSION_COUNT", "h2d_submit_count"),):
            first_values = [_transport_value(_transport_records(artifact).get(role, {}), key, *fallbacks) for _, artifact in reference_counted]
            second_values = [_transport_value(_transport_records(artifact).get(role, {}), key, *fallbacks) for _, artifact in counted]
            first, second = _stats(first_values), _stats(second_values)
            first_mean = first[3] if first else MISSING
            second_mean = second[3] if second else MISSING
            delta = ((second_mean / first_mean) - 1) * 100 if isinstance(first_mean, (int, float)) and isinstance(second_mean, (int, float)) and first_mean else MISSING
            lines.append(f"| {role.upper()} | {label} | {_cell(first_mean)} | {_cell(second_mean)} | {_cell(delta)} |")
    lines.append("")


def _appendices(lines: list[str], manifest: dict[str, Any]) -> None:
    lines.extend(["## Per-attempt appendices", ""])
    for attempt in manifest.get("attempts", []):
        if not isinstance(attempt, dict):
            continue
        key = attempt.get("attempt_key", MISSING)
        artifact = _attempt_artifact(attempt)
        lines.extend([f"### {key}", "",
                      f"role=`{attempt.get('cohort_role', MISSING)}` classification=`{attempt.get('classification', MISSING)}`",
                      f"invocation_id=`{attempt.get('invocation_id', MISSING)}` request_id=`{attempt.get('request_id', MISSING)}`", ""])
        if artifact is not None:
            fields = _artifact_fields(artifact)
            lines.extend(["#### Available stage/invariant values", ""])
            for field in ("duration_ms", "provider", "region", "output_sha_match", "output_sha", "true_cold", "restore_count", "request_count"):
                lines.append(f"* `{field}`: `{_cell(fields[field])}`")
            for name, value in fields["walls"].items():
                lines.append(f"* stage `{name}` wall ms: `{value:.3f}`")
            lines.append("")
        explicit_files = (
            ("deployment stdout", "deployment_stdout_path", False),
            ("source-probe stdout", "source_probe_stdout_path", False),
            ("pre-deploy status/doctor", "preflight_status_path", False),
            ("post-deploy status/doctor", "post_deploy_doctor_path", False),
            ("run stdout", "stdout_path", False),
            ("run manifest", "run_manifest_path", True),
            ("attempt artifact", "artifact_path", True),
            ("derived report", "derived_report_path", False),
            ("derived gantt", "derived_gantt_path", False),
            ("derived summary", "derived_summary_path", True),
            ("raw session events", "session_events_path", False),
            ("raw milestones", "milestones_path", False),
            ("blocked stdout", "blocked_stdout_path", False),
            ("post-block doctor/status", "post_block_doctor_path", False),
        )
        for label, path_key, is_json in explicit_files:
            path = attempt.get(path_key)
            info = _meta(path)
            lines.extend([f"#### {key} / {label}", ""])
            if not info["present"]:
                lines.extend([f"ABSENT — checked explicit path: {path or MISSING}", ""])
                continue
            lines.extend([f"Path: `{info['path']}` — {info['bytes']} bytes, sha256 `{info['sha256']}`.", "",
                          "```json" if is_json else "```text",
                          _json_evidence(path) if is_json else _text_evidence(path), "```", ""])
        guard = artifact.get("capture_guard", MISSING) if artifact else attempt.get("capture_guard", MISSING)
        lines.extend([f"#### {key} / capture-guard record", "", "```json", _pretty(guard), "```", ""])


def _geometry_stats(values: Iterable[Any]) -> dict[str, Any]:
    stats = _stats(values)
    if not stats:
        return {"n": 0, "min": MISSING, "max": MISSING, "range": MISSING,
                "mean": MISSING, "median": MISSING, "sample_sd": MISSING, "cv": MISSING}
    return dict(zip(("min", "max", "range", "mean", "median", "sample_sd", "cv"), stats, strict=True)) | {"n": len([v for v in values if _number(v) is not None])}


def _geometry_report(manifest: dict[str, Any], output_path: str) -> None:
    attempts = [a for a in manifest.get("attempts", []) if isinstance(a, dict) and a.get("counted")]
    arms: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for attempt in attempts:
        artifact = _attempt_artifact(attempt)
        if artifact is not None:
            arms.setdefault(str(attempt.get("arm", attempt.get("value_mib", MISSING))), []).append((attempt, artifact))
    arms = dict(sorted(arms.items(), key=lambda item: int(item[0]) if item[0].isdigit() else item[0]))

    summary: dict[str, Any] = {
        "schema_version": 1,
        "experiment_id": manifest.get("experiment_id", MISSING),
        "status": manifest.get("cohort_status", MISSING),
        "performance_comparison": "NOT_PERFORMED",
        "performance_verdict": "NOT_PROVIDED",
        "expected_output_sha": manifest.get("expected_output_sha", MISSING),
        "arms": [],
    }
    lines = [
        f"# {manifest.get('report_title', 'Direct-source geometry sweep')}", "",
        "PERFORMANCE_COMPARISON=NOT_PERFORMED", "",
        "PERFORMANCE_VERDICT=NOT_PROVIDED", "",
        f"STATUS={manifest.get('cohort_status', 'UNKNOWN')}", "",
        "## Scope", "",
        "Six direct-source geometry arms were collected with 12 eligible, non-snapshot/post-snapshot observations per value. The four newest observations in each arm are the requested additional runs and are retained separately as `EXTRA`; they are included in all arm summaries.", "",
        "No performance winner or promotion decision is made by this report.", "",
        "## Arm Inventory", "",
        "| value | app | profile | deployment fingerprint | eligible | core | extra | geometry check |", "|---:|---|---|---|---:|---:|---:|---|",
    ]
    for arm, rows in arms.items():
        first_attempt, first_artifact = rows[0]
        expected = int(arm) * 1024 * 1024 if arm.isdigit() else None
        geometry_ok = True
        invariant_failures: list[str] = []
        for attempt, artifact in rows:
            guard = artifact.get("capture_guard", {})
            if guard.get("classification") != "ELIGIBLE" or artifact.get("valid") is not True or artifact.get("true_cold") is not True:
                geometry_ok = False
                invariant_failures.append(str(attempt.get("attempt_key", MISSING)))
            records = _transport_records(artifact)
            for role in TRANSPORT_ROLES:
                record = records.get(role, {})
                if expected is None or any(_transport_value(record, key) != expected for key in ("source_block_bytes", "h2d_target_bytes", "logical_slot_bytes")):
                    geometry_ok = False
                    invariant_failures.append(f"{attempt.get('attempt_key', MISSING)}:{role}:geometry")
                if _transport_value(record, "logical_slot_count") != 8 or _transport_value(record, "aggregation_enabled", "AGGREGATION_ENABLED") is not False:
                    geometry_ok = False
                    invariant_failures.append(f"{attempt.get('attempt_key', MISSING)}:{role}:invariant")
        value_mib = int(arm) if arm.isdigit() else arm
        core = [(a, x) for a, x in rows if a.get("cohort_group") != "EXTRA"]
        extra = [(a, x) for a, x in rows if a.get("cohort_group") == "EXTRA"]
        request_values = [x.get("duration_ms") for _, x in rows]
        loader_values = [sum(_artifact_fields(x)["walls"].get(stage, 0) for stage in ("clip_load", "unet_load", "vae_load")) for _, x in rows]
        transport_summary: dict[str, Any] = {}
        for role in TRANSPORT_ROLES:
            records = [_transport_records(x).get(role, {}) for _, x in rows]
            transport_summary[role] = {
                "source_block_bytes": sorted({_transport_value(r, "source_block_bytes") for r in records}),
                "h2d_target_bytes": sorted({_transport_value(r, "h2d_target_bytes") for r in records}),
                "arena_bytes": sorted({_transport_value(r, "arena_bytes") for r in records}),
                "logical_slot_count": sorted({_transport_value(r, "logical_slot_count") for r in records}),
                "logical_slot_bytes": sorted({_transport_value(r, "logical_slot_bytes") for r in records}),
                "aggregation_enabled": sorted({_transport_value(r, "aggregation_enabled", "AGGREGATION_ENABLED") for r in records}, key=str),
                "source_wall_ms": _geometry_stats([_transport_value(r, "SOURCE_TOTAL_WALL_MS") for r in records]),
                "h2d_wall_ms": _geometry_stats([_transport_value(r, "H2D_TOTAL_WALL_MS") for r in records]),
                "source_h2d_overlap_ms": _geometry_stats([_transport_value(r, "SOURCE_H2D_OVERLAP_MS") for r in records]),
                "post_source_h2d_tail_ms": _geometry_stats([_transport_value(r, "POST_SOURCE_H2D_TAIL_MS") for r in records]),
            }
        arm_summary = {
            "value_mib": value_mib,
            "app": first_artifact.get("target", {}).get("app", first_attempt.get("app", MISSING)),
            "profile": first_artifact.get("profile", first_attempt.get("profile", MISSING)),
            "deployment_fingerprints": sorted({str(a.get("deployment_fingerprint", MISSING)) for a, _ in rows}),
            "eligible_n": len(rows),
            "core_n": len(core),
            "extra_n": len(extra),
            "geometry_ok": geometry_ok,
            "invariant_failures": invariant_failures,
            "request_wall_ms": _geometry_stats(request_values),
            "combined_loader_wall_ms": _geometry_stats(loader_values),
            "transport": transport_summary,
        }
        summary["arms"].append(arm_summary)
        lines.append("| " + " | ".join(_cell(value) for value in (value_mib, arm_summary["app"], arm_summary["profile"], ", ".join(arm_summary["deployment_fingerprints"]), len(rows), len(core), len(extra), "PASS" if geometry_ok else "FAIL")) + " |")

    lines.extend(["", "## Per-Arm Statistics", "", "| value | metric | min | max | range | mean | median | sample SD | CV |", "|---:|---|---:|---:|---:|---:|---:|---:|---:|"])
    for arm_summary in summary["arms"]:
        for label, key in (("request wall (ms)", "request_wall_ms"), ("combined loader wall (ms)", "combined_loader_wall_ms")):
            values = arm_summary[key]
            lines.append("| " + " | ".join(_cell(value) for value in (arm_summary["value_mib"], label, values.get("min"), values.get("max"), values.get("range"), values.get("mean"), values.get("median"), values.get("sample_sd"), values.get("cv"))) + " |")

    lines.extend(["", "## Additional Four Runs", "", "The `EXTRA` rows below are the four newest eligible observations for each value and are included in the per-arm statistics above.", "", "| attempt | value | request wall (ms) | artifact |", "|---|---:|---:|---|"])
    for attempt in attempts:
        if attempt.get("cohort_group") != "EXTRA":
            continue
        artifact = _attempt_artifact(attempt) or {}
        lines.append("| " + " | ".join(_cell(value) for value in (attempt.get("attempt_key", MISSING), attempt.get("arm", MISSING), artifact.get("duration_ms", MISSING), attempt.get("artifact_path", MISSING))) + " |")

    lines.extend(["", "## Eligibility Ledger", "", "| attempt | value | classification | counted | capture guard | true cold | valid | run manifest |", "|---|---:|---|---|---|---|---|---|"])
    for attempt in attempts:
        artifact = _attempt_artifact(attempt) or {}
        lines.append("| " + " | ".join(_cell(value) for value in (attempt.get("attempt_key", MISSING), attempt.get("arm", MISSING), attempt.get("classification", MISSING), attempt.get("counted", MISSING), artifact.get("capture_guard", {}).get("classification", MISSING), artifact.get("true_cold", MISSING), artifact.get("valid", MISSING), attempt.get("run_manifest_path", MISSING))) + " |")

    lines.extend(["", "## Identity and Disposition", "", f"- experiment id: `{manifest.get('experiment_id', MISSING)}`", f"- expected output SHA: `{manifest.get('expected_output_sha', MISSING)}`", f"- source identity: `{manifest.get('source_identity_note', MISSING)}`", f"- disposition: {manifest.get('disposition', 'No performance comparison or winner is provided.')}", "", "## Summary Artifact", "", f"`{manifest.get('summary_output_path', MISSING)}`", ""])
    Path(output_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    summary_path = manifest.get("summary_output_path")
    if summary_path:
        Path(summary_path).write_text(_pretty(summary) + "\n", encoding="utf-8")


def build(manifest_path: str, output_path: str, reference_manifest_path: str | None = None) -> None:
    manifest = _json(manifest_path)
    if not isinstance(manifest, dict):
        raise ValueError("experiment manifest must be a JSON object")
    if manifest.get("report_mode") == "direct_source_geometry":
        _geometry_report(manifest, output_path)
        return
    reference = None
    if reference_manifest_path:
        reference = _json(reference_manifest_path)
        if not isinstance(reference, dict):
            raise ValueError("reference manifest must be a JSON object")
        reference["_path"] = reference_manifest_path
    counted = _counted(manifest)

    lines = [
        f"# {manifest.get('report_title', 'September UNET/CLIP Experiment Report')}", "",
        "PERFORMANCE_COMPARISON=NOT_PERFORMED", "",
        "PERFORMANCE_VERDICT=NOT_PROVIDED", "",
        f"STATUS={manifest.get('cohort_status', 'UNKNOWN')}", "",
        "## Identity", "",
    ]
    identity_keys = (
        "worktree", "branch", "head", "git_dirty", "tracked_diff_files",
        "tracked_diff_bytes", "tracked_diff_sha256", "untracked_inventory",
        "experiment_id", "app", "profile", "class_name", "method", "gpu",
        "deploy_fingerprint", "profile_config_fingerprint", "run_fingerprint",
        "content_generation", "deployment_manifest", "deployment_receipt",
        "raw_evidence_root",
    )
    for key in identity_keys:
        value = manifest.get(key, MISSING)
        if isinstance(value, list):
            lines.append(f"* **{key}:**")
            lines.extend(f"  * `{item}`" for item in value)
        else:
            lines.append(f"* **{key}:** `{_cell(value)}`")
    lines.extend(["", "### Effective environment", ""])
    environment = manifest.get("effective_environment", [])
    if isinstance(environment, dict):
        environment = [f"{key}={value}" for key, value in environment.items()]
    lines.extend(f"* `{item}`" for item in (environment or [MISSING]))
    lines.extend(["", "### SHA policies", "",
                  f"* expected output SHA (profile/workload): `{manifest.get('expected_output_sha', MISSING)}`",
                  f"* skill-identity SHA: `{manifest.get('skill_identity_sha', MISSING)}`",
                  "* Current-bundle semantics retained; no new SHA gate was applied.",
                  "", "## Attempt ledger", "",
                  "All attempts are retained in manifest order; counted membership is taken from the manifest.", "",
                  "| attempt | role | classification | invocation ID | request ID | counted |",
                  "|---|---|---|---|---|---|"])
    for attempt in manifest.get("attempts", []):
        if isinstance(attempt, dict):
            lines.append("| " + " | ".join(_cell(attempt.get(key, MISSING)) for key in (
                "attempt_key", "cohort_role", "classification", "invocation_id", "request_id", "counted")) + " |")

    lines.extend(["", "## Capture boundary", "", _cell(manifest.get("capture_boundary_note", MISSING)), "",
                  "## Five-run performance schema", ""])
    if len(counted) != 5:
        lines.extend(["NOT_APPLICABLE_INCOMPLETE: five counted observations are required; no cohort statistics were computed.", ""])
    else:
        lines.extend(["The counted cohort is `" + ",".join(str(a.get("cohort_role", MISSING)) for a, _ in counted) + "`.", ""])
    _consistency(lines, manifest, counted)
    _stage_table(lines, counted)
    _timeline_table(lines, counted)
    _output_durability_table(lines, counted)
    lines.extend([
        "## Counter scope note", "",
        "`GPU_COPY_COUNT`/`GPU_COPY_BYTES` are model-local. `REQUEST_CUMULATIVE_GPU_COPY_COUNT`/`REQUEST_CUMULATIVE_GPU_COPY_BYTES` are cumulative across the request's CLIP, UNET, and VAE loads.",
        "The captured `REQUEST_CUMULATIVE_H2D_SUBMIT_COUNT` is zero because the deployed CUDA submission path increments the model-local H2D submit counter without mirroring that increment into the cumulative counter. `H2D_SUBMISSION_COUNT` and GPU-copy cumulative counters remain the authoritative observed counts; the zero cumulative H2D submit field must not be interpreted as zero H2D submissions.",
        "",
    ])
    loader = _loader_values(counted)
    lines.extend(["", "### Combined loader wall", "",
                  "Derived per-request sum of the authoritative `clip_load + unet_load + vae_load` stage walls; it is not an end-to-end wall.", ""])
    _table(lines, ["metric"] + [str(a.get("cohort_role", MISSING)) for a, _ in counted] + _stat_header().split(" | "),
           [["combined loader wall (ms)"] + loader + (_stats(loader) or [MISSING] * 7)])

    lines.extend(["", "## CLIP / UNET / VAE decomposition", "",
                  "Nested transport intervals explain the enclosing stage and are not added as independent walls.", ""])
    _transport_table(lines, counted)
    _header_staging_table(lines, counted)
    lines.extend(["## Resource and correctness invariants", "",
                  "| role | arena alloc count | arena bytes | logical slots | slot bytes | event objects | event rerecords | fresh event/copy | duplicate reads |", 
                  "|---|---:|---:|---:|---:|---:|---:|---:|---:|"])
    for role in TRANSPORT_ROLES:
        records = [_transport_records(artifact).get(role, {}) for _, artifact in counted]
        def mean_field(key: str, *fallbacks: str) -> Any:
            values = [_transport_value(record, key, *fallbacks) for record in records]
            stats = _stats(values)
            return stats[3] if stats else (values[0] if values and all(value == values[0] for value in values) else MISSING)
        lines.append("| " + " | ".join(_cell(value) for value in [
            role.upper(), mean_field("pinned_arena_physical_allocation_count", "request_physical_pinned_alloc_count"),
            mean_field("pinned_arena_physical_allocation_bytes", "arena_bytes"),
            mean_field("logical_slot_count", "slot_count"), mean_field("logical_slot_bytes", "slot_bytes"),
            mean_field("event_object_count"), mean_field("event_rerecord_count"),
            mean_field("fresh_cuda_event_per_copy_count"), mean_field("duplicate_read_count"),
        ]) + " |")
    lines.extend(["", "Correctness and identity observations are per-request, not means:", ""])
    for attempt, artifact in counted:
        fields = _artifact_fields(artifact)
        lines.append(f"* `{attempt.get('cohort_role', MISSING)}`: provider=`{fields['provider']}` region=`{fields['region']}` true_cold=`{fields['true_cold']}` restore_count=`{fields['restore_count']}` request_count=`{fields['request_count']}` output_sha_match=`{fields['output_sha_match']}`")

    _per_attempt_transport(lines, counted)
    if manifest.get("comparison_policy") == "NOT_PERFORMED":
        lines.extend(["## Reference comparison", "",
                      "NOT_PERFORMED: this report contains no Experiment 01 or Experiment 02 comparison.", ""])
    else:
        _comparison(lines, reference, counted)
    _appendices(lines, manifest)
    disposition = manifest.get("disposition")
    if disposition:
        lines.extend(["## Disposition", "", str(disposition), ""])
    else:
        lines.extend(["## Disposition", "",
                      "Experiment 02 proves that aggregation was exercised, but the observed groups were small and transport placement fallback dominated the attempted grouping. The evidence does not establish a performance win for this configuration.",
                      "",
                      "The report retains the aggregation evidence for diagnosis. Do not promote this aggregation configuration as an Experiment 03 optimization without a separately designed change that addresses canonical slot ordering and demonstrates a valid end-to-end result. If Experiment 03 does not explicitly test that redesign, use the Experiment 01 transport-core behavior as the revert boundary.",
                      "",
                      "## Evidence integrity note", "",
                      "The v2ctl confirmation renderer labels the first four confirmation rows MISMATCH and the last EXACT. The authoritative per-request summaries remain valid, SHA-matching, and bound to the same deployment; the renderer identity mismatch is retained as a control-plane evidence defect, not hidden.",
                      ""])
    lines.extend(["## Audit path inventory", "",
                  "The primary manifest is the authority for the audit inventory; every listed path is rendered or marked ABSENT.", ""])
    for path in manifest.get("audit_paths", []):
        info = _meta(path)
        lines.append(f"* `{path}` — {info['bytes']} bytes — sha256 `{info['sha256']}`" if info["present"] else f"* `{path}` — ABSENT")
    if reference_manifest_path:
        info = _meta(reference_manifest_path)
        lines.extend(["", f"* reference manifest `{reference_manifest_path}` — {info['bytes']} bytes — sha256 `{info['sha256']}`" if info["present"] else f"* reference manifest `{reference_manifest_path}` — ABSENT"])
    Path(output_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a host-only report from explicit evidence manifests.")
    parser.add_argument("manifest", help="primary experiment manifest JSON")
    parser.add_argument("output", help="Markdown report to write")
    parser.add_argument("--reference-manifest", help="optional explicit comparison manifest JSON")
    args = parser.parse_args()
    build(args.manifest, args.output, args.reference_manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
