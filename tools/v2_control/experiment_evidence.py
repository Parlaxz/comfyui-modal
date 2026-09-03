"""Identity-bound evidence finalization for Golden/RX experiments.

This module is intentionally a small, stdlib-only boundary.  It does not run
anything and it never chooses an artifact by age.  Callers provide the result
identity; cohort discovery is bound to the result/record artifact owners, so a
finalization cannot walk unrelated historical cohorts.  Explicit control-plane
paths and the local .v2ctl/config inputs remain part of the evidence bundle.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


GOLDEN_COHORT_ROOT = Path("artifacts") / "phase_p1_serial_golden_v1"
_SECRET_RE = re.compile(
    r"(?ix)"
    r"(?P<prefix>"
    r"[\"']?[A-Za-z0-9_.-]*(?:token|secret|password|api[_-]?key|credential)"
    r"[A-Za-z0-9_.-]*[\"']?\s*[=:]\s*)"
    r"(?P<value>(?:"
    r"(?P<double>\"(?:\\.|[^\"\\])*\")|"
    r"(?P<single>'(?:\\.|[^'\\])*')|"
    r"(?P<bare>[^\s,;\"'}]+)"
    r"))"
)
_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_.-]+")
_OMIT_EVENTS_BYTES = 256 * 1024
# Shared upper bound for JSON path projection and textual embedding.  Evidence
# above 128 KiB is copied and SHA-256 inventoried, but not parsed or embedded.
_MAX_PATH_PROJECTION_BYTES = 128 * 1024
_GOLDEN_P1_BACKENDS = frozenset({"pytorch", "sage", "comfy_kitchen"})


def _golden_p1_observed_value(
    sources: tuple[Any, ...], keys: frozenset[str], allowed: frozenset[str]
) -> str:
    """Project one runtime value, returning ``mixed`` on contradiction.

    Control-plane selectors are intentionally not included in *keys*.  They
    are request inputs, not proof that the selected runtime was actually used.
    """
    values: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                normalized = str(key).strip().lower()
                if normalized in keys and item not in (None, ""):
                    candidate = str(item).strip().lower()
                    if candidate in allowed and candidate not in values:
                        values.append(candidate)
                visit(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item)

    for source in sources:
        visit(source)
    if not values:
        return "missing"
    return values[0] if len(values) == 1 else "mixed"


def _golden_p1_runtime_provenance(
    golden_telemetry: Mapping[str, Any] | None,
    terminal_identity: Mapping[str, Any] | None,
    *,
    sage_effective_input: str,
    sage_resolution_source: str,
) -> dict[str, str]:
    """Extract backend identity from returned runtime evidence only.

    Request selectors are never accepted as resolved evidence, so an
    error/DNF without telemetry remains ``missing``.
    """
    telemetry = golden_telemetry if isinstance(golden_telemetry, Mapping) else {}
    identity = terminal_identity if isinstance(terminal_identity, Mapping) else {}
    sources = (telemetry, identity)

    attention = _golden_p1_observed_value(
        sources,
        frozenset({
            "attention_backend_resolved",
            "resolved_attention_backend",
            "attention_backend_observed",
        }),
        _GOLDEN_P1_BACKENDS,
    )
    selected_callables: list[str] = []

    def collect_selection(value: Any, in_selection: bool = False) -> None:
        if isinstance(value, Mapping):
            selection = in_selection or str(value.get("name", "")).strip().lower() == "attention_backend_selection"
            if selection:
                selected = str(value.get("selected_callable", "")).strip().lower()
                if selected:
                    selected_callables.append(selected)
            for item in value.values():
                collect_selection(item, selection)
        elif isinstance(value, (list, tuple)):
            for item in value:
                collect_selection(item, in_selection)

    for source in sources:
        collect_selection(source)
    mapped: list[str] = []
    for selected in selected_callables:
        if "sageattention.sageattn" in selected or selected.endswith(".sageattn"):
            backend = "sage"
        elif "attention_pytorch" in selected:
            backend = "pytorch"
        elif "comfy_kitchen" in selected or "kitchen" in selected:
            backend = "comfy_kitchen"
        else:
            continue
        if backend not in mapped:
            mapped.append(backend)
    attention_values = set(mapped)
    if attention == "mixed":
        attention_values.clear()
        attention_values.add("mixed")
    elif attention != "missing":
        attention_values.add(attention)
    attention = (
        next(iter(attention_values)) if len(attention_values) == 1
        else ("mixed" if attention_values else "missing")
    )

    effective_values: list[str] = []
    source_values: list[str] = []

    def collect_sage_inputs(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                normalized = str(key).strip().lower()
                if normalized in {
                    "sage_runtime_mode_effective_input",
                    "sage_effective_input",
                    "effective_sage_runtime_mode",
                }:
                    candidate = str(item).strip().lower()
                    if candidate in {"auto", "baked_cuda", "triton_fallback"} and candidate not in effective_values:
                        effective_values.append(candidate)
                if normalized in {
                    "sage_runtime_mode_resolution_source",
                    "sage_resolution_source",
                    "sage_runtime_reason",
                    "sage_reason",
                    "resolution_source",
                } and item not in (None, ""):
                    candidate = str(item).strip().lower()
                    if candidate and candidate not in source_values:
                        source_values.append(candidate)
                collect_sage_inputs(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                collect_sage_inputs(item)

    for source in sources:
        collect_sage_inputs(source)
    effective = effective_values[0] if len(effective_values) == 1 else (
        "mixed" if effective_values else sage_effective_input
    )
    resolution_source = source_values[0] if len(source_values) == 1 else (
        "mixed" if source_values else sage_resolution_source
    )
    return {
        "attention_backend_resolved": attention,
        "sage_runtime_mode_effective_input": effective or "missing",
        "sage_runtime_mode_resolution_source": resolution_source or "missing",
        "sage_runtime_mode_resolved": resolved_sage_runtime_mode(*sources) or "missing",
    }


def _golden_p1_consensus(records: list[dict[str, Any]], field: str, default: str) -> str:
    """Return one record-level provenance value, or ``mixed`` fail-closed."""
    values = {
        str(record.get(field, "") or "").strip().lower() or default
        for record in records
    }
    if not values:
        return default
    return next(iter(values)) if len(values) == 1 else "mixed"


@dataclass(frozen=True)
class EvidenceResult:
    experiment_id: str
    bundle_dir: Path
    markdown_path: Path
    status: str
    verdict: str


def _value(source: Any, *names: str, default: Any = "") -> Any:
    if isinstance(source, Mapping):
        for name in names:
            if source.get(name) not in (None, ""):
                return source[name]
    else:
        for name in names:
            candidate = getattr(source, name, None)
            if candidate not in (None, ""):
                return candidate
    return default


def resolved_attention_backend(config: Any) -> str:
    """Return the backend resolved before dispatch, defaulting to PyTorch."""
    flag = None
    lookup = getattr(config, "flag", None)
    if callable(lookup):
        flag = lookup("COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND")
    if flag is None:
        for candidate in getattr(config, "flags", ()) or ():
            if getattr(candidate, "name", "") == "COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND":
                flag = candidate
                break
    value = str(_value(flag, "value", default="pytorch") or "pytorch").strip().lower()
    if value not in {"pytorch", "sage", "comfy_kitchen"}:
        raise ValueError(f"invalid Golden attention backend: {value or '(empty)'}")
    return value


SAGE_RUNTIME_MODE_FLAG = "COMFYMODAL_SAGE_RUNTIME_MODE"
_SAGE_RUNTIME_MODES = {"auto", "baked_cuda", "triton_fallback"}


def configured_sage_runtime_mode(config: Any) -> str:
    """Return the Sage mode selected by the resolved v2 config flag."""
    flag = None
    lookup = getattr(config, "flag", None)
    if callable(lookup):
        flag = lookup(SAGE_RUNTIME_MODE_FLAG)
    if flag is None:
        for candidate in getattr(config, "flags", ()) or ():
            if getattr(candidate, "name", "") == SAGE_RUNTIME_MODE_FLAG:
                flag = candidate
                break
    value = str(_value(flag, "value", default="auto") or "auto").strip().lower()
    if value not in _SAGE_RUNTIME_MODES:
        raise ValueError(f"invalid Sage runtime mode: {value or '(empty)'}")
    return value


def resolved_sage_runtime_mode(*sources: Any) -> str:
    """Read the actual Sage mode from existing runtime evidence.

    ``sage_mode`` and ``resolved_sage_runtime_mode`` are observed results;
    ``sage_env_mode``, ``configured_sage_runtime_mode``, ``sage_runtime_mode``
    when carrying ``auto``, and ``COMFYMODAL_SAGE_RUNTIME_MODE`` are configured
    policy and must not be treated as observed execution. ``auto`` is never an
    executed backend — it is treated as missing/unknown.
    This helper only projects existing evidence and does not choose a policy.
    """
    _RESOLVED_OBSERVED_MODES = {"baked_cuda", "triton_fallback"}
    values: list[str] = []
    saw_auto = False

    def visit(value: Any) -> None:
        nonlocal saw_auto
        if isinstance(value, Mapping):
            for key, item in value.items():
                if str(key).lower() in {
                    "resolved_sage_runtime_mode", "sage_mode", "sage_runtime_mode_resolved",
                } and item not in (None, ""):
                    text = str(item).strip().lower()
                    if text == "auto":
                        saw_auto = True
                    elif text in _RESOLVED_OBSERVED_MODES and text not in values:
                        values.append(text)
                visit(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item)

    for source in sources:
        visit(source)
    if saw_auto and values:
        return "mixed"
    if not values:
        return ""
    return values[0] if len(values) == 1 else "mixed"


def _sage_effective_input(*sources: Any) -> str:
    """Project the effective Sage input observed before resolution."""
    values: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                lk = str(key).lower()
                if lk in {
                    "sage_runtime_mode_effective_input",
                    "sage_effective_input",
                    "effective_sage_runtime_mode",
                    "effective_input",
                } and item not in (None, ""):
                    text = str(item).strip().lower()
                    if text in {"auto", "baked_cuda", "triton_fallback"} and text not in values:
                        values.append(text)
                visit(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item)

    for source in sources:
        visit(source)
    if not values:
        return ""
    return values[0] if len(values) == 1 else "mixed"


def _sage_resolution_source(*sources: Any) -> str:
    """Project the factual category explaining where final Sage mode came from."""
    values: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                lk = str(key).lower()
                if lk in {
                    "sage_runtime_mode_resolution_source",
                    "sage_resolution_source",
                    "resolution_source",
                    "sage_reason",
                    "sage_runtime_reason",
                } and item not in (None, ""):
                    text = str(item).strip().lower()
                    if text and text not in values:
                        values.append(text)
                visit(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item)

    for source in sources:
        visit(source)
    if not values:
        return ""
    return values[0] if len(values) == 1 else "mixed"


def attention_backend_configured_value(config: Any) -> str:
    """Return the configured attention backend from control-plane identity."""
    return resolved_attention_backend(config)


def attention_backend_resolved_value(*sources: Any) -> str:
    """Return the observed attention backend from runtime evidence, or 'missing'."""
    values: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                lk = str(key).lower()
                if lk in {
                    "attention_backend_resolved",
                    "resolved_attention_backend",
                    "attention_backend_observed",
                } and item not in (None, ""):
                    text = str(item).strip().lower()
                    if text in {"pytorch", "sage", "comfy_kitchen"} and text not in values:
                        values.append(text)
                # Also accept legacy attention_backend if it carries resolved semantics
                # (but configured is separate; we treat legacy as resolved only when
                # new fields are absent — handled in _compact_cohort fallback)
                visit(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item)

    for source in sources:
        visit(source)
    if not values:
        return "missing"
    return values[0] if len(values) == 1 else "mixed"


def sage_runtime_identity(config: Any, *sources: Any) -> dict[str, str]:
    """Project configured, effective, source and observed Sage modes into identity."""
    return {
        "sage_runtime_mode_configured": configured_sage_runtime_mode(config),
        "sage_runtime_mode_effective_input": _sage_effective_input(*sources) or configured_sage_runtime_mode(config),
        "sage_runtime_mode_resolution_source": _sage_resolution_source(*sources),
        "sage_runtime_mode_resolved": resolved_sage_runtime_mode(*sources),
        # Back-compat spellings
        "configured_sage_runtime_mode": configured_sage_runtime_mode(config),
        "resolved_sage_runtime_mode": resolved_sage_runtime_mode(*sources),
        # Attention backend provenance (control-plane vs runtime)
        "attention_backend_configured": attention_backend_configured_value(config),
        "attention_backend_resolved": attention_backend_resolved_value(*sources),
    }


def is_experiment_profile(config: Any) -> bool:
    """Identify Golden/RX control-plane experiments without a second runner."""
    profile = str(getattr(config, "profile_name", "") or "").strip().lower()
    return profile == "golden_p1" or profile.startswith(("rx", "ra"))


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "to_dict") and callable(value.to_dict):
        try:
            return _jsonable(value.to_dict())
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        return _jsonable(vars(value))
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _artifact_paths(value: Any) -> list[Path]:
    paths: list[Path] = []
    if value is None:
        return paths
    for name in (
        "output_dir", "run_artifact", "summary_artifact", "campaign_manifest",
        "console_capture", "run_artifacts",
    ):
        item = getattr(value, name, None)
        items = item if isinstance(item, (list, tuple)) else [item]
        for candidate in items:
            if candidate:
                path = Path(candidate)
                if path not in paths and path.is_file():
                    paths.append(path)
    return paths


def _extract_paths(value: Any) -> Iterable[Path]:
    """Extract explicit path-shaped evidence references from JSON objects."""
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key).lower()
            if isinstance(item, str) and (
                key_text.endswith("path") or key_text.endswith("file")
                or key_text.endswith("artifact") or key_text.endswith("log")
            ):
                yield Path(item)
            yield from _extract_paths(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _extract_paths(item)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _nested_values(value: Any, names: set[str]) -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).lower() in names and item not in (None, ""):
                text = str(item).strip().lower()
                if text and text not in found:
                    found.append(text)
            found.extend(_nested_values(item, names))
    elif isinstance(value, list):
        for item in value:
            found.extend(_nested_values(item, names))
    return list(dict.fromkeys(found))


def _direct_values(sources: Iterable[Any], names: set[str]) -> list[str]:
    """Read policy values from the record envelopes, not nested telemetry."""
    normalized = {name.lower() for name in names}
    found: list[str] = []
    for source in sources:
        if not isinstance(source, Mapping):
            continue
        for key, item in source.items():
            if str(key).lower() in normalized and item not in (None, ""):
                text = str(item).strip().lower()
                if text and text not in found:
                    found.append(text)
    return found


def _fallback_values(value: Any, *, in_predicates: bool = False) -> list[str]:
    """Collect fallback outcomes while ignoring diagnostic predicates."""
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key).lower()
            if not in_predicates and key_text in {"fallback", "fallback_attempted"}:
                text = str(item).strip().lower()
                if text and text not in found:
                    found.append(text)
            found.extend(_fallback_values(item, in_predicates=in_predicates or key_text == "predicates"))
    elif isinstance(value, list):
        for item in value:
            found.extend(_fallback_values(item, in_predicates=in_predicates))
    return list(dict.fromkeys(found))


def _output_sha_values(value: Any) -> list[str]:
    values: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).lower() in {"observed_output_sha", "observed_output_shas", "output_sha"}:
                candidates = item if isinstance(item, list) else [item]
                for candidate in candidates:
                    if candidate not in (None, ""):
                        text = str(candidate).strip()
                        if text and text not in values:
                            values.append(text)
            values.extend(v for v in _output_sha_values(item) if v not in values)
    elif isinstance(value, list):
        for item in value:
            values.extend(v for v in _output_sha_values(item) if v not in values)
    return values


def _compact_cohort(path: Path, identity: Mapping[str, Any]) -> dict[str, Any]:
    manifest_path = path / "manifest.json"
    summary_path = path / "summary.json"
    manifest_value = _read_json(manifest_path) if manifest_path.is_file() else None
    summary_value = _read_json(summary_path) if summary_path.is_file() else None
    manifest = manifest_value or {}
    summary = summary_value or {}
    attempts = sorted(
        p for p in path.glob("attempt_*.json")
        if (
            p.is_file()
            and not p.name.endswith("_events.json")
            and not p.name.endswith(".json.v2ctl-provenance.json")
        )
    )
    loaded_attempts = [_read_json(p) for p in attempts]
    attempt_data = [item or {} for item in loaded_attempts]
    all_data = [manifest, summary, *attempt_data]
    target = manifest.get("target", {}) if isinstance(manifest, dict) else {}
    resources = manifest.get("resources", {}) if isinstance(manifest, dict) else {}
    deployment_identity = manifest.get("deployment_identity", {}) if isinstance(manifest, dict) else {}
    target = target if isinstance(target, Mapping) else {}
    resources = resources if isinstance(resources, Mapping) else {}
    deployment_identity = deployment_identity if isinstance(deployment_identity, Mapping) else {}
    if not resources and isinstance(deployment_identity.get("resources"), Mapping):
        resources = deployment_identity["resources"]
    # RX9P-H: attention backend is frozen with separate configured/resolved provenance.
    configured_backend_values = _nested_values(
        all_data, {"attention_backend_configured", "ATTENTION_BACKEND_CONFIGURED"}
    )
    resolved_backend_values = _nested_values(
        all_data, {"attention_backend_resolved", "ATTENTION_BACKEND_RESOLVED", "resolved_attention_backend"}
    )
    # Legacy fallback: when new fields absent, treat legacy attention_backend as both.
    if not configured_backend_values and not resolved_backend_values:
        legacy = _nested_values(all_data, {"attention_backend"})
        configured_backend_values = legacy
        resolved_backend_values = legacy
    configured_backend_value = (
        configured_backend_values[0] if len(configured_backend_values) == 1 else ("mixed" if configured_backend_values else "")
    )
    resolved_backend_value = (
        resolved_backend_values[0] if len(resolved_backend_values) == 1 else ("mixed" if resolved_backend_values else "missing")
    )
    # Sage 4-field model: configured, effective_input, resolution_source, resolved
    configured_sage_names = {
        "configured_sage_runtime_mode",
        "sage_runtime_mode_configured",
        "sage_env_mode",
        SAGE_RUNTIME_MODE_FLAG.lower(),
    }
    configured_sage_values = _direct_values(all_data, configured_sage_names)
    if not configured_sage_values:
        configured_sage_values = _nested_values(all_data, configured_sage_names)
    configured_sage_value = (
        configured_sage_values[0]
        if len(configured_sage_values) == 1
        else ("mixed" if configured_sage_values else "")
    )
    effective_sage_values = _nested_values(
        all_data, {"sage_runtime_mode_effective_input", "sage_effective_input", "effective_input"}
    )
    effective_sage_value = (
        effective_sage_values[0] if len(effective_sage_values) == 1 else ("mixed" if effective_sage_values else "")
    )
    if not effective_sage_value:
        effective_sage_value = configured_sage_value
    sage_resolution_values = _nested_values(
        all_data, {"sage_runtime_mode_resolution_source", "sage_resolution_source", "resolution_source", "sage_reason", "sage_runtime_reason"}
    )
    sage_resolution_value = (
        sage_resolution_values[0] if len(sage_resolution_values) == 1 else ("mixed" if sage_resolution_values else "")
    )
    resolved_sage_value = resolved_sage_runtime_mode(*all_data)
    exact = True
    mismatches: list[str] = []
    missing: list[str] = []

    # A readable JSON object is not sufficient evidence by itself.  Keep
    # malformed/partial cohorts visible as INCOMPLETE rather than allowing the
    # default ``exact=True`` below to turn an empty artifact set into EXACT.
    for artifact_path, loaded in (
        (manifest_path, manifest_value),
        (summary_path, summary_value),
    ):
        if not artifact_path.is_file() or loaded is None:
            missing.append(str(artifact_path))
    for artifact_path, loaded in zip(attempts, loaded_attempts):
        if loaded is None:
            missing.append(str(artifact_path))

    def require_text(value: Any, label: str, artifact_path: Path) -> str:
        text = str(value or "").strip()
        if not text:
            missing.append(f"{artifact_path}: {label}")
        return text

    expected_invocation = require_text(
        identity.get("v2ctl_invocation_id"), "expected v2ctl_invocation_id", manifest_path
    )
    manifest_invocation = _value(manifest, "v2ctl_invocation_id", default="")
    nested_manifest = manifest.get("v2ctl")
    if not manifest_invocation and isinstance(nested_manifest, Mapping):
        manifest_invocation = _value(
            nested_manifest, "v2ctl_invocation_id", "invocation_id", default=""
        )
    manifest_invocation = require_text(
        manifest_invocation, "v2ctl_invocation_id", manifest_path
    )
    if expected_invocation and manifest_invocation and manifest_invocation != expected_invocation:
        exact = False
        mismatches.append(
            f"v2ctl_invocation_id: expected {expected_invocation}, observed {manifest_invocation}"
        )

    first_attempt = attempt_data[0] if attempt_data else {}
    expected_profile = str(identity.get("profile", "") or "").strip()
    observed_profile = require_text(manifest.get("profile"), "profile", manifest_path)
    if expected_profile and observed_profile and observed_profile != expected_profile:
        exact = False
        mismatches.append(f"profile: expected {expected_profile}, observed {observed_profile}")
    for key in ("v2ctl_invocation_id", "profile_config_fingerprint", "run_fingerprint"):
        expected = str(identity.get(key, "") or "")
        if key in {"v2ctl_invocation_id", "run_fingerprint"}:
            continue
        nested_manifest = manifest.get("v2ctl") if isinstance(manifest, dict) else None
        observed = _value(manifest, key, default="")
        if not observed and isinstance(nested_manifest, Mapping):
            observed = _value(nested_manifest, key, default="")
        if expected and not str(observed or "").strip():
            missing.append(f"{manifest_path}: {key}")
        elif expected and str(observed) != expected:
            exact = False
            mismatches.append(f"{key}: expected {expected}, observed {observed}")
    # RX9P-H: attention backend frozen with separate provenance — fail closed.
    # Configured must be pytorch (Golden control), resolved must be observed pytorch (not missing, not mixed, not copied).
    expected_attention_configured = str(identity.get("attention_backend_configured") or identity.get("attention_backend") or "").strip().lower()
    expected_attention_resolved = str(identity.get("attention_backend_resolved") or identity.get("attention_backend") or "").strip().lower()
    # If identity provides no explicit attention expectation but profile is golden, default to pytorch.
    if not expected_attention_configured and str(identity.get("profile", "") or "").strip().lower() == "golden_p1":
        expected_attention_configured = "pytorch"
    if not expected_attention_resolved and str(identity.get("profile", "") or "").strip().lower() == "golden_p1":
        expected_attention_resolved = "pytorch"
    if expected_attention_configured:
        if not configured_backend_value:
            missing.append(f"{manifest_path}: attention_backend_configured")
        elif configured_backend_value == "mixed":
            exact = False
            mismatches.append(f"attention_backend_configured: mixed observed {configured_backend_values}")
        elif configured_backend_value != expected_attention_configured:
            exact = False
            mismatches.append(f"attention_backend_configured: expected {expected_attention_configured}, observed {configured_backend_value}")
    if expected_attention_resolved:
        if resolved_backend_value == "missing" or not resolved_backend_value:
            missing.append(f"{manifest_path}: attention_backend_resolved")
            exact = False
            mismatches.append("attention_backend_resolved: missing (runtime evidence absent)")
        elif resolved_backend_value == "mixed":
            exact = False
            mismatches.append(f"attention_backend_resolved: mixed observed {resolved_backend_values}")
        elif resolved_backend_value != expected_attention_resolved:
            exact = False
            mismatches.append(f"attention_backend_resolved: expected {expected_attention_resolved}, observed {resolved_backend_value}")
    # Configured and resolved must agree for golden_p1 (both pytorch), and resolved must not be mere copy.
    if configured_backend_value and resolved_backend_value and configured_backend_value != resolved_backend_value:
        exact = False
        mismatches.append(f"attention_backend: configured {configured_backend_value} != resolved {resolved_backend_value}")
    # Sage 4-field identity — fail closed on override masquerading as auto resolution.
    for key, observed in (
        ("sage_runtime_mode_configured", configured_sage_value),
        ("sage_runtime_mode_effective_input", effective_sage_value),
        ("sage_runtime_mode_resolution_source", sage_resolution_value),
        ("sage_runtime_mode_resolved", resolved_sage_value),
        # Back-compat aliases
        ("configured_sage_runtime_mode", configured_sage_value),
        ("resolved_sage_runtime_mode", resolved_sage_value),
    ):
        # Only validate keys present in identity; new 4-field keys are validated when expected.
        expected = str(identity.get(key, "") or "").strip().lower()
        if not expected:
            continue
        if not observed or observed == "missing":
            missing.append(f"{manifest_path}: {key}")
        elif observed != expected:
            exact = False
            mismatches.append(f"{key}: expected {expected}, observed {observed}")
    # Effective-input override detection: configured=auto but effective!=auto due to override must fail unless override is frozen config.
    if configured_sage_value == "auto" and effective_sage_value and effective_sage_value != "auto":
        # An override is not a legitimate auto_resolution; surface it.
        if sage_resolution_value in ("environment_override", "runtime_override", "fallback", "explicit_profile"):
            # Unless the frozen identity explicitly allows this override (it does not for golden_p1), fail.
            allowed_override = str(identity.get("sage_runtime_mode_effective_input", "") or "").strip().lower()
            if effective_sage_value != allowed_override:
                exact = False
                mismatches.append(
                    f"sage_effective_input_override: configured=auto effective={effective_sage_value} source={sage_resolution_value}"
                )
    if resolved_sage_value == "auto":
        exact = False
        mismatches.append("sage_runtime_mode_resolved is auto (never executing)")
    if configured_sage_value and resolved_sage_value and configured_sage_value == "auto" and effective_sage_value == "auto" and sage_resolution_value not in ("auto_resolution", "auto", "explicit_profile", "probe", ""):
        # Resolution source must truthfully indicate auto-selection mechanism, not override.
        if sage_resolution_value in ("environment_override", "runtime_override"):
            exact = False
            mismatches.append(f"sage_resolution_source_unexpected_override: {sage_resolution_value}")
    if not attempts:
        missing.append(str(path / "attempt_*.json"))
    receipt_ref = _value(manifest, "deployment_receipt_path", default="")
    if receipt_ref:
        receipt_path = Path(str(receipt_ref))
        if not receipt_path.is_absolute():
            receipt_path = path / receipt_path
        if not receipt_path.is_file():
            missing.append(f"deployment receipt: {receipt_ref}")
    summary_invocation = require_text(
        summary.get("v2ctl_invocation_id"), "v2ctl_invocation_id", summary_path
    )
    attempt_invocation = require_text(
        first_attempt.get("v2ctl_invocation_id"),
        "v2ctl_invocation_id",
        attempts[0] if attempts else path / "attempt_*.json",
    )
    for label, observed in (("summary", summary_invocation), ("attempt", attempt_invocation)):
        if expected_invocation and observed and observed != expected_invocation:
            exact = False
            mismatches.append(
                f"{label} v2ctl_invocation_id: expected {expected_invocation}, observed {observed}"
            )
    request_id = require_text(
        first_attempt.get("request_id"),
        "request_id",
        attempts[0] if attempts else path / "attempt_*.json",
    )
    summary_request_id = str(summary.get("request_id") or "").strip()
    manifest_attempts = manifest.get("attempts")
    if not isinstance(manifest_attempts, list) or len(manifest_attempts) != 1:
        missing.append(f"{manifest_path}: attempts")
    else:
        declared_request_id = require_text(
            manifest_attempts[0].get("request_id") if isinstance(manifest_attempts[0], Mapping) else "",
            "attempts[0].request_id",
            manifest_path,
        )
        if declared_request_id and request_id and declared_request_id != request_id:
            exact = False
            mismatches.append(
                f"request_id: expected manifest {declared_request_id}, observed attempt {request_id}"
            )
    expected_request_id = str(identity.get("request_id", "") or "").strip()
    for label, observed in (("summary", summary_request_id), ("attempt", request_id)):
        if expected_request_id and observed and observed != expected_request_id:
            exact = False
            mismatches.append(
                f"{label} request_id: expected {expected_request_id}, observed {observed}"
            )
    for key in ("valid", "dnf"):
        if not isinstance(first_attempt.get(key), bool):
            missing.append(f"{attempts[0] if attempts else path / 'attempt_*.json'}: {key}")
    for artifact_path, item in zip(attempts[1:], attempt_data[1:]):
        observed = require_text(item.get("v2ctl_invocation_id"), "v2ctl_invocation_id", artifact_path)
        if expected_invocation and observed and observed != expected_invocation:
            exact = False
            mismatches.append(
                f"attempt v2ctl_invocation_id: expected {expected_invocation}, observed {observed}"
            )
        require_text(item.get("request_id"), "request_id", artifact_path)
        for key in ("valid", "dnf"):
            if not isinstance(item.get(key), bool):
                missing.append(f"{artifact_path}: {key}")
    first_identity = first_attempt.get("identity", {}) if isinstance(first_attempt, Mapping) else {}
    first_identity = first_identity if isinstance(first_identity, Mapping) else {}
    output_modes = _nested_values(all_data, {
        "output_durability_mode", "output_durability", "durability_mode",
    })
    fallback_values = _fallback_values(all_data)
    fallback = any(value in {"1", "true", "yes", "on", "ok"} for value in fallback_values)
    failed_attempts = [
        item for item in attempt_data
        if item.get("dnf") is True or item.get("valid") is False
        or item.get("error") or item.get("failures")
    ]
    if failed_attempts and not missing:
        exact = False
        mismatches.append("failed attempt present")
    return {
        "cohort": path.name,
        "arm": _value(manifest, "arm", "variant", default=""),
        "app": _value(target, "app_name", "app", default=""),
        "gpu": _value(target, "gpu", default="") or _value(resources, "gpu", default=""),
        "cpu": _value(resources, "cpu", "cpu_request", default=""),
        "ram": _value(resources, "memory_mb", "ram_mb", default=""),
        "min_containers": _value(resources, "min_containers", default=""),
        "scaledown_window": _value(resources, "scaledown_window", default=""),
        "deployment_fingerprint": _value(
            manifest, "deploy_fingerprint", "deployment_fingerprint",
            default=_value(deployment_identity, "deploy_fingerprint", "deployment_combined_hash", default=identity.get("deploy_fingerprint", "")),
        ),
        "run_fingerprint": _value(manifest, "run_fingerprint", default=identity.get("run_fingerprint", "")),
        "profile_fingerprint": _value(manifest, "profile_config_fingerprint", default=""),
        "attention_backend": configured_backend_value,
        "attention_backend_configured": configured_backend_value,
        "attention_backend_resolved": resolved_backend_value,
        "configured_sage_runtime_mode": configured_sage_value,
        "resolved_sage_runtime_mode": resolved_sage_value,
        "sage_runtime_mode_configured": configured_sage_value,
        "sage_runtime_mode_effective_input": effective_sage_value,
        "sage_runtime_mode_resolution_source": sage_resolution_value,
        "sage_runtime_mode_resolved": resolved_sage_value,
        "expected_output_sha": _value(manifest, "expected_output_sha", default=""),
        "observed_output_sha": _output_sha_values(all_data)[:1],
        "exact": "EXACT" if exact and not missing else ("INCOMPLETE" if missing else "MISMATCH"),
        "mismatch": mismatches,
        "missing": missing,
        "dnf": sum(1 for item in attempt_data if item.get("dnf") is True),
        "fallback": fallback,
        "seriality": _value(manifest, "strict_serial", default=""),
        "output_durability": output_modes[0] if len(output_modes) == 1 else ("mixed" if output_modes else ""),
        "true_cold": _value(first_attempt, "true_cold", default=""),
        "request_count": _value(first_identity, "request_count", default=""),
        "restore_count": _value(first_identity, "restore_count", default=""),
        "start": _value(manifest, "started_utc", "start_ts", default=""),
        "end": _value(manifest, "completed_utc", "end_ts", default=""),
        "duration": _value(summary, "duration_ms", default=""),
        "failure": [item.get("error") or item.get("failures") for item in failed_attempts],
        "source_artifacts": [str(p) for p in sorted(path.iterdir()) if p.is_file()],
    }


def _redact(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        prefix = match.group("prefix")
        if match.group("double"):
            return f'{prefix}"<redacted>"'
        if match.group("single"):
            return f"{prefix}'<redacted>'"
        return f"{prefix}<redacted>"

    return _SECRET_RE.sub(replace, text)


def _markdown_json(value: Any) -> str:
    return json.dumps(_jsonable(value), indent=2, sort_keys=True, ensure_ascii=False)


def _identity_from_inputs(identity: Mapping[str, Any]) -> dict[str, Any]:
    return {str(k): _jsonable(v) for k, v in sorted(identity.items(), key=lambda item: str(item[0]))}


def _default_experiment_id(identity: Mapping[str, Any]) -> str:
    stable = _markdown_json(_identity_from_inputs(identity)).encode("utf-8")
    digest = hashlib.sha256(stable).hexdigest()[:16]
    profile = _SAFE_ID_RE.sub("-", str(identity.get("profile", "experiment"))).strip("-") or "experiment"
    return f"{profile}_{digest}"


def _owner_cohort_dir(owner: Any, root: Path) -> Path | None:
    """Return the invocation-owned cohort directory, if one is identifiable."""
    if owner is None:
        return None

    def normalize(value: Any) -> Path:
        candidate = Path(value)
        return candidate if candidate.is_absolute() else root / candidate

    output_dir = getattr(owner, "output_dir", None)
    run_artifact = getattr(owner, "run_artifact", None)
    if output_dir:
        candidate = normalize(output_dir)
        if candidate.is_file():
            return candidate.parent
        if candidate.is_dir() or not run_artifact:
            return candidate
    if run_artifact:
        return normalize(run_artifact).parent
    return None


def finalize_experiment_evidence(
    repo_root: Path,
    *,
    identity: Mapping[str, Any],
    verdict: str,
    result: Any | None = None,
    records: Iterable[Any] = (),
    gate_manifest: Path | None = None,
    confirmation_manifest: Path | None = None,
    extra_paths: Iterable[Path | str] = (),
    experiment_id: str | None = None,
) -> EvidenceResult:
    """Write the ignored raw bundle and the Git-visible evidence index.

    Cohort collection is invocation-bound: only cohorts owned by ``result`` or
    ``records`` are compacted and copied.  Historical cohorts are not
    selectors and are never enumerated here.

    The Markdown file is always written before this function returns.  If
    collection fails, a FAILED/INCONCLUSIVE document is written instead and
    the exception is re-raised so callers cannot report a normal verdict.
    """
    root = Path(repo_root)
    records = list(records)
    frozen = _identity_from_inputs(identity)
    exp_id = _SAFE_ID_RE.sub("-", experiment_id or _default_experiment_id(frozen)).strip("-")
    if not exp_id:
        exp_id = _default_experiment_id(frozen)
    date = datetime.now(timezone.utc).date().isoformat()
    bundle_dir = root / "artifacts" / f"{exp_id}_evidence_{date}"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = root / f"EXPERIMENT_EVIDENCE_{exp_id}_{date}.md"
    try:
        paths: list[Path] = []
        declared_missing: list[str] = []
        paths.extend(_artifact_paths(getattr(result, "artifacts", None)))
        for record in records:
            paths.extend(_artifact_paths(getattr(record, "artifacts", None)))
        owners = [getattr(result, "artifacts", None)]
        owners.extend(getattr(record, "artifacts", None) for record in records)
        for owner in owners:
            if owner is None:
                continue
            for name in ("run_artifact", "summary_artifact", "campaign_manifest"):
                candidate = getattr(owner, name, None)
                if candidate and not Path(candidate).is_file():
                    declared_missing.append(str(Path(candidate)))
            output_dir = getattr(owner, "output_dir", None)
            run_path = getattr(owner, "run_artifact", None)
            cohort_dir = Path(output_dir) if output_dir else (
                Path(run_path).parent if run_path else None
            )
            if cohort_dir is not None and cohort_dir.is_dir() and (
                str(frozen.get("profile", "")).lower() == "golden_p1"
                or cohort_dir.name.startswith("cohort_")
            ):
                for required_name in ("manifest.json", "summary.json"):
                    required_path = cohort_dir / required_name
                    if not required_path.is_file():
                        declared_missing.append(str(required_path))
        for explicit in (gate_manifest, confirmation_manifest, *extra_paths):
            if explicit:
                paths.append(Path(explicit))
        # Persisted v2ctl state is the authoritative local control-plane
        # evidence.  Include it wholesale; it is already ignored and callers
        # must be able to audit every gate/receipt/confirmation path.
        state_root = root / ".v2ctl"
        if state_root.is_dir():
            paths.extend(p for p in state_root.rglob("*") if p.is_file())
        profile_name = str(frozen.get("profile", "") or "")
        for config_path in (
            root / "config" / "v2" / "flag_registry.toml",
            root / "config" / "v2" / "profiles" / f"{profile_name}.toml",
        ):
            if config_path.is_file():
                paths.append(config_path)
        # Operators commonly save preflight/doctor/deploy/smoke/source-probe
        # captures at the worktree root.  These are evidence inputs, not
        # selectors: names are used only to preserve them, never to choose a
        # cohort.
        log_markers = (
            "doctor", "deploy", "smoke", "preflight", "probe", "receipt",
            "publisher", "identity", "cohort", "gate", "confirm",
        )
        for candidate in root.iterdir() if root.is_dir() else ():
            if not candidate.is_file():
                continue
            name = candidate.name.casefold()
            if any(marker in name for marker in log_markers) and candidate.suffix.casefold() in {
                ".log", ".txt", ".json", ".md",
            }:
                paths.append(candidate)
        # Cohort collection is invocation-bound.  Do not enumerate the
        # canonical artifact root: it contains historical cohorts that are not
        # evidence for this result and may contain very large event streams.
        # Result/record owners are the authoritative current-cohort selectors;
        # every file in each explicitly owned cohort is retained, including
        # invalid attempts, so missing/integrity classifications remain true.
        cohorts = []
        seen_cohorts: set[str] = set()
        for owner in owners:
            cohort = _owner_cohort_dir(owner, root)
            if cohort is None or not cohort.is_dir():
                continue
            cohort_key = os.path.abspath(cohort).casefold()
            if cohort_key in seen_cohorts:
                continue
            seen_cohorts.add(cohort_key)
            cohorts.append(_compact_cohort(cohort, frozen))
            paths.extend(p for p in cohort.rglob("*") if p.is_file())
        # Explicit path references embedded in known manifests/receipts/log
        # projections are retained too.
        for path in list(paths):
            # Event streams are retained in the raw bundle and inventory below,
            # but are not path-reference projections.  Re-reading a large
            # repeated stream here can block finalization after the request has
            # already returned.
            if path.name.casefold().endswith("_events.json"):
                continue
            if not path.is_file():
                continue
            # Large evidence files stay in the raw bundle, but path projection
            # is best-effort and must not parse them on the finalization path.
            try:
                if path.stat().st_size > _MAX_PATH_PROJECTION_BYTES:
                    continue
            except OSError:
                continue
            data = _read_json(path)
            if data:
                paths.extend(_extract_paths(data))
        unique: list[Path] = []
        seen: set[str] = set()
        for path in paths:
            candidate = path if path.is_absolute() else root / path
            candidate = Path(os.path.abspath(candidate))
            key = str(candidate).casefold()
            if candidate.is_file() and key not in seen:
                seen.add(key)
                unique.append(candidate)

        raw_dir = bundle_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        inventory: list[dict[str, Any]] = []
        evidence_text: list[tuple[Path, str, str]] = []
        for index, source in enumerate(sorted(unique, key=lambda p: str(p).casefold())):
            size = source.stat().st_size
            digest = _sha256(source)
            copied = raw_dir / f"{index:04d}_{source.name}"
            shutil.copyfile(source, copied)
            item = {
                "source_path": str(source),
                "bundle_path": str(copied),
                "bytes": size,
                "sha256": digest,
            }
            is_repeated_attempt_events = (
                source.name.startswith("attempt_")
                and source.name.endswith("_events.json")
            )
            if is_repeated_attempt_events and size > _OMIT_EVENTS_BYTES:
                item["text_omitted"] = True
                item["cohort"] = source.parent.name
                item["omission_reason"] = "large repeated attempt event stream; raw copy and integrity metadata retained"
            elif size > _MAX_PATH_PROJECTION_BYTES:
                item["text_omitted"] = True
                item["omission_reason"] = "oversized evidence source; raw copy and integrity metadata retained"
            else:
                try:
                    evidence_text.append((source, _redact(source.read_text(encoding="utf-8", errors="replace")), digest))
                except (OSError, UnicodeError):
                    item["text_omitted"] = True
                    item["omission_reason"] = "binary or undecodable source"
            inventory.append(item)

        index_data = {
            "schema_version": 1,
            "status": "OK",
            "verdict": str(verdict),
            "experiment_id": exp_id,
            "identity": frozen,
            "raw_bundle_path": str(bundle_dir),
            "cohorts": cohorts,
            "inventory": inventory,
            "missing_artifacts": list(dict.fromkeys(
                declared_missing + [item for cohort in cohorts for item in cohort.get("missing", [])]
            )),
            "EXPERIMENT_EVIDENCE_STATUS": "OK",
            "EXPERIMENT_VERDICT": str(verdict),
        }
        index_path = bundle_dir / "evidence_index.json"
        index_path.write_text(_markdown_json(index_data) + "\n", encoding="utf-8")

        lines = [
            f"# Experiment evidence: `{exp_id}`",
            "",
            f"- **Status:** `OK`",
            f"- **Verdict:** `{verdict}`",
            f"- **EXPERIMENT_EVIDENCE_STATUS:** `OK`",
            f"- **EXPERIMENT_VERDICT:** `{verdict}`",
            f"- **Generated:** `{datetime.now(timezone.utc).isoformat()}`",
            f"- **Raw bundle:** `{bundle_dir}`",
            "",
            "## Frozen identity",
            "",
            "```json",
            _markdown_json(frozen),
            "```",
            "",
            "Identity chain: `v2ctl invocation ID -> request ID -> exact cohort directory -> manifest.json -> attempt artifact(s) -> summary.json`.",
            "",
            "## Cohort index",
            "",
            "| cohort | arm | app | gpu | cpu | RAM MB | min containers | scaledown | deploy fp | run fp | profile fp | attention | attn_cfg | attn_res | sage_cfg | sage_eff | sage_src | sage_res | durability | true cold | requests | restores | expected SHA | observed SHA | classification | DNF | fallback | serial | start | end | duration | failure | source |",
            "|---|---|---|---|---:|---:|---:|---:|---|---|---|---|---|---|---|---|---|---|---|---:|---:|---|---|---|---:|---|---|---|---|---|---|---|",
        ]
        for cohort in cohorts:
            lines.append(
                "| {cohort} | {arm} | {app} | {gpu} | {cpu} | {ram} | {min_containers} | {scaledown_window} | {deployment_fingerprint} | {run_fingerprint} | {profile_fingerprint} | {attention_backend} | {attention_backend_configured} | {attention_backend_resolved} | {sage_runtime_mode_configured} | {sage_runtime_mode_effective_input} | {sage_runtime_mode_resolution_source} | {sage_runtime_mode_resolved} | {output_durability} | {true_cold} | {request_count} | {restore_count} | {expected_output_sha} | {observed_output_sha} | {exact} | {dnf} | {fallback} | {seriality} | {start} | {end} | {duration} | {failure} | {source_artifacts} |".format(
                    **{key: str(cohort.get(key, "")).replace("|", "\\|") for key in (
                        "cohort", "arm", "app", "gpu", "cpu", "ram", "min_containers",
                        "scaledown_window", "deployment_fingerprint", "run_fingerprint",
                        "profile_fingerprint", "attention_backend", "attention_backend_configured", "attention_backend_resolved",
                        "sage_runtime_mode_configured", "sage_runtime_mode_effective_input", "sage_runtime_mode_resolution_source", "sage_runtime_mode_resolved",
                        "output_durability", "true_cold",
                        "request_count", "restore_count", "expected_output_sha", "observed_output_sha",
                        "exact", "dnf", "fallback", "seriality", "start", "end", "duration", "failure",
                        "source_artifacts",
                    )}
                )
            )
        if not cohorts:
            lines.append("| (none) | | | | | | | | | INCOMPLETE | | | | |")
        lines += ["", "## Missing-artifact declarations", ""]
        missing = index_data["missing_artifacts"]
        if missing:
            lines.extend(f"- MISSING: `{item}`" for item in missing)
        else:
            lines.append("- NONE")
        lines += ["", "## Byte/SHA256 inventory", "", "```json", _markdown_json(inventory), "```", ""]
        lines += ["## Textual evidence (source path is authoritative)", ""]
        for source, text, digest in evidence_text:
            lines += [f"### `{source}`", "", f"SHA256: `{digest}`", "", "```text", text, "```", ""]
        for item in inventory:
            if item.get("text_omitted"):
                lines += [
                    f"### `{item['source_path']}`",
                    "",
                    f"Text omitted: {item['omission_reason']}; cohort={item.get('cohort', '')}; bytes={item['bytes']}; SHA256={item['sha256']}; raw={item['bundle_path']}",
                    "",
                ]
        markdown_path.write_text("\n".join(lines), encoding="utf-8")
        return EvidenceResult(exp_id, bundle_dir, markdown_path, "OK", str(verdict))
    except Exception as exc:
        failure = (
            f"# Experiment evidence: `{exp_id}`\n\n"
            "- **Status:** `FAILED`\n"
            "- **Verdict:** `INCONCLUSIVE`\n"
            "- **EXPERIMENT_EVIDENCE_STATUS:** `FAILED`\n"
            "- **EXPERIMENT_VERDICT:** `INCONCLUSIVE`\n"
            f"- **Raw bundle:** `{bundle_dir}`\n"
            f"- **Failure:** `{type(exc).__name__}: {exc}`\n\n"
            "Evidence generation failed; no normal ACCEPT/REJECT claim is valid.\n"
        )
        try:
            markdown_path.write_text(failure, encoding="utf-8")
        except OSError:
            pass
        raise


# Descriptive compatibility spellings for focused offline tools.
generate_experiment_evidence = finalize_experiment_evidence
write_experiment_evidence = finalize_experiment_evidence
