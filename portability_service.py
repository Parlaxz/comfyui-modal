"""Portability backend service (Phase G9).

Composition layer between the production authorities and the frozen Phase-G
engines:

* ``studio_domain.services.WorkflowDomainService`` / ``store`` (identity,
  immutability, atomic multi-collection import transactions)
* ``studio_workflow_manifest`` (the SOLE manifest v1 authority — built,
  parsed, validated, hashed; never duplicated here)
* ``dependency_resolver.DependencyResolver`` + Model Library + Custom Node
  Registry (read-only dependency evidence)
* ``portability_risk`` (G6 engine) and ``portability_targets`` (G7 rules)

Owns: manifest Export (read-only, exact-JSON), Import dry-run preview,
atomic committed Import, and the WorkflowVersion portability report with
G10 derived-cache integration (Phase G11).  Performs NO provider calls, NO
installs, NO filesystem scans beyond guarded single-path existence checks.
Analysis logic lives here — HTTP handlers stay thin.

Cache integration (G11, derived-only invariant preserved): an injected
``PortabilityReportCache`` is a disposable mirror of live analysis.  The
explicit detail flow (``cached_portability_report``) builds the CURRENT
8-field G5 invalidation stamp from authoritative evidence, serves validated
hits with zero recomputation, and recomputes live through the unchanged G9
pipeline on miss/stale/invalid — always refreshing the cache afterwards.
Every cache error FAILS OPEN (live report is still produced; the endpoint
never 500s merely because the derived sidecar is unavailable).  List-card
summaries (``workflow_portability_summaries``) NEVER analyze: they only read
already-persisted versions and ask the cache for tri-state summaries.  The
cache never gates execution, never authorizes Import, and never becomes
source of truth.

Exact-JSON discipline: exported graphs are the PERSISTED Version bytes
(``graph_json`` / ``api_prompt_json`` verbatim); the manifest's hashable
``workflow.graph`` is the executable prompt so manifest integrity verifies
the domain identity rule (canonical hash of the executable prompt).  No
normalization, ID regeneration, node stripping, path rewriting, or default
insertion is ever applied to embedded graph/API objects.

Credential policy (fail-closed export): credential-shaped executable input
keys produce a deterministic ``credential_like_value_detected`` refusal —
the manifest download is refused with zero mutation and no secret values in
any message.  Import treats the same finding as a reported risk (per the
frozen G5 contract), never silently scrubbed.
"""

from __future__ import annotations

import copy
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import portability_contract as pc
import portability_risk as risk
import portability_targets as targets
import studio_workflow_manifest as manifest_codec
from portability_cache import (
    STATE_HIT,
    STATE_INVALID,
    STATE_MISS,
    STATE_STALE,
)
from portability_evidence import (
    EXPORTER_ID,
    adapt_manifest_custom_nodes,
    adapt_manifest_models,
    build_custom_node_manifest_records,
    build_model_manifest_records,
    build_target_evidence_payload,
    collect_environment_facts,
    core_classes_from_rows,
    derive_node_provenance,
    detect_manifest_credential_shapes,
    extract_asset_references,
    extract_aux_id_provenance,
)
from studio_domain.graph import extract_dependency_metadata, extract_executable_prompt
from studio_domain.models import (
    Mapping,
    Workflow,
    WorkflowPreset,
    WorkflowVersion,
    make_mapping_id,
    make_preset_id,
    make_version_id,
    make_workflow_id,
)
from studio_domain.services import WorkflowDomainService
from studio_workflow_manifest import (
    ManifestValidationError,
    build_manifest,
    check_readiness,
    manifest_hash,
    parse_manifest,
)

_MAX_JSON_DEPTH = pc.MAX_JSON_DEPTH
_MAX_JSON_ELEMENTS = pc.MAX_JSON_ELEMENTS

_log = logging.getLogger(__name__)


# ── Errors ────────────────────────────────────────────────────────────────


class PortabilityError(RuntimeError):
    """Base error for the portability backend."""


class ExportRefusedError(PortabilityError):
    """Deterministic security/integrity refusal of a manifest download."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class ImportBlockedError(PortabilityError):
    """Malformed/unsupported/integrity-failing manifest; zero writes made."""

    def __init__(self, message: str, issues: Optional[list[str]] = None) -> None:
        self.issues = list(issues or [])
        self.message = message
        super().__init__(message)


# ── bounded payload parsing ───────────────────────────────────────────────


def _reject_json_constant(name: str) -> None:
    raise ValueError("non-finite JSON constant: %s" % name)


def _check_depth_and_elements(data: Any) -> None:
    """Enforce MAX_JSON_DEPTH / MAX_JSON_ELEMENTS on a parsed payload."""
    elements = 0

    def _walk(value: Any, depth: int) -> None:
        nonlocal elements
        if depth > _MAX_JSON_DEPTH:
            raise ImportBlockedError(
                "payload exceeds maximum JSON depth (%d)" % _MAX_JSON_DEPTH
            )
        elements += 1
        if elements > _MAX_JSON_ELEMENTS:
            raise ImportBlockedError(
                "payload exceeds maximum JSON element count (%d)"
                % _MAX_JSON_ELEMENTS
            )
        if isinstance(value, dict):
            for key, item in value.items():
                elements += 1
                _walk(item, depth + 1)
        elif isinstance(value, list):
            for item in value:
                _walk(item, depth + 1)

    _walk(data, 1)


def load_manifest_payload(source: Any) -> dict:
    """Parse an untrusted manifest payload with security limits enforced.

    Accepts dict, str, or bytes.  Raises ``ImportBlockedError`` (zero
    writes by construction) for undecodable text, invalid JSON, NaN/
    Infinity constants, or depth/element violations.
    """
    if isinstance(source, dict):
        data = source
    elif isinstance(source, (str, bytes, bytearray)):
        if isinstance(source, (bytes, bytearray)):
            try:
                text = bytes(source).decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ImportBlockedError("payload is not valid UTF-8: %s" % exc) from None
        else:
            text = source
        try:
            data = json.loads(text, parse_constant=_reject_json_constant)
        except ValueError as exc:
            raise ImportBlockedError("invalid JSON: %s" % exc) from None
    else:
        raise ImportBlockedError("manifest payload must be JSON text or an object")
    if not isinstance(data, dict):
        raise ImportBlockedError("manifest root must be a JSON object")
    _check_depth_and_elements(data)
    return data


# ── small deterministic helpers ───────────────────────────────────────────


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _comfyui_version() -> Optional[str]:
    """Cheapest existing authoritative ComfyUI/core version identity.

    Mirrors the established runtime authority chain (modal_app): the pinned
    ``comfyui_version`` module first, then the ``comfy`` package version.
    Guarded imports only — never ``git rev-parse``, never remote inspection.
    """
    for module_name, attrs in (
        ("comfyui_version", ("version", "VERSION", "__version__")),
        ("comfy", ("__version__",)),
    ):
        try:
            module = __import__(module_name)
        except Exception:
            continue
        for attr in attrs:
            value = getattr(module, attr, None)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _dependency_summary(model_rows, custom_node_rows) -> dict:
    m_installed = sum(1 for r in model_rows if r.get("state") == "installed")
    m_missing = sum(1 for r in model_rows if r.get("state") == "missing")
    m_wrong = sum(1 for r in model_rows if r.get("state") == "wrong_version")
    m_unknown = sum(1 for r in model_rows if r.get("state") == "unknown")
    n_installed = sum(1 for r in custom_node_rows if r.get("state") == "installed")
    n_missing = sum(1 for r in custom_node_rows if r.get("state") == "missing")
    n_wrong = sum(1 for r in custom_node_rows if r.get("state") == "wrong_revision")
    attention = m_missing + m_wrong + m_unknown + n_missing + n_wrong
    return {
        "models": model_rows,
        "custom_nodes": custom_node_rows,
        "summary": {
            "installed": m_installed + n_installed,
            "missing": m_missing + n_missing,
            "wrong_version": m_wrong + n_wrong,
            "unknown": m_unknown,
            "attention": attention,
            "ready": attention == 0,
        },
    }


# ── invalidation-stamp generation authorities (Phase G11) ─────────────────
#
# The G10 cache treats generations as OPAQUE caller-supplied comparables and
# deliberately never inspects the Model Library / Custom Node Registry.  This
# composition layer owns that derivation: a deterministic SHA-256 token over
# NORMALIZED, portability-relevant fields of the already-persisted records.
# No model bytes are read, no directories are scanned, no git is invoked, no
# file mtimes are hashed.  Any authority failure yields None — which the
# frozen G5 comparator conservatively treats as stale (never a false hit).


def _int_or_none(value) -> Optional[int]:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _model_record_installed(record: dict) -> bool:
    """Presence/status truth that affects resolver analysis (guarded)."""
    try:
        from model_library import record_is_installed

        return bool(record_is_installed(record))
    except Exception:
        return False


def model_library_generation_token(source: Any) -> Optional[str]:
    """Stable generation token over portability-relevant Model Library truth.

    Hashes only normalized fields that change analysis outcomes: identity,
    filename, folder/role, hash, size, source references, provider revision,
    placeholder flag, and the derived install/presence status.  ``local_path``
    is intentionally excluded (absolute local path is not portability truth);
    timestamps are excluded (they do not affect analysis).
    """
    if source is None:
        return None
    try:
        records = [r for r in (source.list_records() or []) if isinstance(r, dict)]
    except Exception as exc:
        _log.debug("model library generation unavailable: %s", exc)
        return None
    normalized = []
    for record in sorted(records, key=lambda r: str(r.get("model_id") or "")):
        normalized.append(
            {
                "model_id": str(record.get("model_id") or ""),
                "folder": str(record.get("folder") or ""),
                "filename": str(record.get("filename") or ""),
                "hash": str(record.get("hash") or ""),
                "size": _int_or_none(record.get("size")),
                "source_urls": sorted(
                    str(u) for u in (record.get("source_urls") or []) if isinstance(u, str)
                ),
                "provider": str(record.get("provider") or ""),
                "revision": str(record.get("revision") or ""),
                "is_placeholder": bool(record.get("is_placeholder")),
                "installed": _model_record_installed(record),
            }
        )
    return pc.sha256_of_canonical(
        {"kind": "model_library_generation_v1", "records": normalized}
    )


def custom_node_registry_generation_token(source: Any) -> Optional[str]:
    """Stable generation token over portability-relevant registry evidence.

    Hashes package identity, declared classes, repo URL, installed commit,
    and provenance/confidence fields present on persisted registry rows.
    Never walks custom-node trees, never calls git, never uses mtimes.
    """
    if source is None:
        return None
    try:
        records = [r for r in (source.list_records() or []) if isinstance(r, dict)]
    except Exception as exc:
        _log.debug("custom node registry generation unavailable: %s", exc)
        return None
    normalized = []
    for record in sorted(records, key=lambda r: str(r.get("name") or "")):
        normalized.append(
            {
                "name": str(record.get("name") or ""),
                "repo_url": str(record.get("repo_url") or ""),
                "installed_commit": str(record.get("installed_commit") or ""),
                "declared_version": str(record.get("declared_version") or ""),
                "provenance": str(record.get("provenance") or ""),
                "classes": sorted(
                    str(c) for c in (record.get("classes") or []) if str(c)
                ),
            }
        )
    return pc.sha256_of_canonical(
        {"kind": "custom_node_registry_generation_v1", "records": normalized}
    )


# ── service ───────────────────────────────────────────────────────────────


class PortabilityService:
    """Production portability backend (export / import / cached report)."""

    def __init__(
        self,
        workflow_service: WorkflowDomainService,
        resolver: Any = None,
        model_library: Any = None,
        custom_node_registry: Any = None,
        *,
        cache: Any = None,
        model_library_generation_source: Any = None,
        custom_node_registry_generation_source: Any = None,
        analyzer: Optional[Callable[[str], dict]] = None,
    ) -> None:
        """``cache`` — optional ``PortabilityReportCache`` (G10, derived-only).

        ``model_library_generation_source`` /
        ``custom_node_registry_generation_source`` — store-like authorities
        (``list_records()``) used ONLY to derive invalidation-stamp
        generation tokens.  They are deliberately separate from the
        ``model_library`` / ``custom_node_registry`` import-adaptation
        params so wiring the cache never changes Import/Export semantics.

        ``analyzer`` — optional injection seam ``(version_id) -> report``
        replacing the internal live pipeline for the recompute step
        (deterministic test spy; production passes nothing).
        """
        self.service = workflow_service
        self.store = workflow_service.store
        self.resolver = resolver
        self._model_library = model_library
        self._custom_node_registry = custom_node_registry
        self.cache = cache
        self._model_generation_source = model_library_generation_source
        self._registry_generation_source = custom_node_registry_generation_source
        self._analyzer = analyzer

    # ── authority reads ───────────────────────────────────────────────

    def _resolve_dependency_rows(self, version: dict) -> tuple[list, list]:
        """Read-only resolver evidence for a persisted Version."""
        if self.resolver is None:
            return [], []
        try:
            summary = self.resolver.resolve_version(version)
        except Exception:
            return [], []
        models = [r for r in (summary.get("models") or []) if isinstance(r, dict)]
        nodes = [r for r in (summary.get("custom_nodes") or []) if isinstance(r, dict)]
        return models, nodes

    def _version_bundle(self, version_id: str) -> dict:
        version = self.store.get_version(version_id)
        if version is None:
            from studio_domain.models import WorkflowVersionNotFoundError

            raise WorkflowVersionNotFoundError(
                f"workflow version {version_id!r} not found"
            )
        workflow = self.store.get_workflow(str(version.get("workflow_id") or "")) or {}
        mapping = self.store.get_mapping_for_version(version_id)
        model_rows, custom_node_rows = self._resolve_dependency_rows(version)
        return {
            "version": version,
            "workflow": workflow,
            "mapping": mapping,
            "model_rows": model_rows,
            "custom_node_rows": custom_node_rows,
        }

    # ── shared analysis composition ───────────────────────────────────

    def _compose_analysis(
        self,
        *,
        version_like: dict,
        graph_json: Any,
        model_rows: list,
        custom_node_rows: list,
        manifest_readiness: Any = None,
        referenced_assets: tuple = (),
        manifest_version: int = 1,
        current_stamp: Optional[dict] = None,
    ) -> dict:
        """Run G6 + G7 over prepared evidence and assemble the frozen report."""
        aux_ids = extract_aux_id_provenance(graph_json)
        node_provenance = derive_node_provenance(custom_node_rows, aux_ids)
        core_classes = core_classes_from_rows(custom_node_rows)
        evidence = risk.evidence_from_version_record(
            version_like,
            model_rows=model_rows,
            custom_node_rows=custom_node_rows,
            core_classes=core_classes,
            manifest_readiness=manifest_readiness,
            referenced_assets=referenced_assets,
            node_provenance=node_provenance,
        )
        workflow_result = risk.analyze_workflow_version(evidence)
        full_signals = risk.compute_signals(evidence)
        target_payload = build_target_evidence_payload(
            workflow_issue_codes=[i["code"] for i in workflow_result["issues"]],
            signals=dict(workflow_result.get("signals") or {}),
            model_rows=model_rows,
            custom_node_rows=custom_node_rows,
            node_provenance=node_provenance,
            path_values=list(full_signals.get("__path_values__") or ()),
            graph_json=graph_json,
            requires_input_asset=bool(full_signals.get(pc.SIGNAL_REQUIRES_INPUT_ASSET)),
            uses_subgraphs=bool(full_signals.get(pc.SIGNAL_USES_SUBGRAPHS)),
            manifest_ready=True
            if not isinstance(manifest_readiness, dict)
            else bool(manifest_readiness.get("ready")),
        )
        outcome = targets.evaluate_target_readiness(target_payload)

        # Composer duty (G7 §2): the report's global pool = workflow issues ∪
        # target-only mints; targets reference codes. The workflow-domain
        # object is the single rendering authority — a target mint whose
        # code already exists in the workflow pool is dropped (reference by
        # code instead). Summary RISK stays derived from the WORKFLOW issues
        # only — target findings never move the workflow level.
        existing_codes = {i["code"] for i in workflow_result["issues"]}
        extra_target_issues = [
            i for i in outcome["issues"] if i["code"] not in existing_codes
        ]
        merged_issues = pc.sort_issues(
            list(workflow_result["issues"]) + extra_target_issues
        )
        merged_counts = {sev: 0 for sev in pc.COUNT_KEYS}
        for issue in merged_issues:
            merged_counts[issue["severity"]] += 1
        merged_result = dict(workflow_result)
        merged_result["issues"] = merged_issues
        merged_result["counts"] = merged_counts
        merged_result["issue_count"] = len(merged_issues)

        environment = risk.build_environment_result(
            collect_environment_facts(model_rows, custom_node_rows)
        )
        if current_stamp is not None:
            # Caller-supplied CURRENT stamp (full 8-field G5 identity built
            # from authoritative evidence); used verbatim so a freshly
            # computed report is cacheable against exactly that evidence.
            stamp = dict(current_stamp)
        else:
            dependency_metadata = version_like.get("dependency_metadata")
            stamp = pc.build_invalidation_stamp(
                workflow_version_id=str(version_like.get("version_id") or "") or None,
                graph_hash=str(version_like.get("graph_hash") or "") or None,
                dependency_metadata_hash=(
                    pc.sha256_of_canonical(dependency_metadata)
                    if isinstance(dependency_metadata, dict)
                    else None
                ),
                rule_version=pc.PORTABILITY_RULE_VERSION,
                manifest_version=manifest_version,
                comfyui_version=_comfyui_version(),
            )
        report = risk.assemble_report(
            merged_result,
            target_results=outcome["targets"],
            environment_result=environment,
            invalidation=stamp,
            analyzed_at=_utc_now_iso(),
            stale=False,
        )
        return {
            "report": report,
            "target_only_issues": outcome["issues"],
            "signals_full": full_signals,
            "node_provenance": node_provenance,
        }

    # ── Export (read-only) ────────────────────────────────────────────

    def export_manifest(self, version_id: str, include_presets: bool = False) -> dict:
        """Build the manifest-v1 export artifact for one WorkflowVersion.

        READ-ONLY: touches no domain collection.  Returns
        ``{"manifest", "filename", "warnings"}``; raises
        ``ExportRefusedError`` on credential-shaped content (fail-closed)
        and on any integrity failure.  Never recaptures the live graph.
        """
        bundle = self._version_bundle(version_id)
        version = bundle["version"]
        workflow = bundle["workflow"]
        if bundle["mapping"] is None:
            raise ExportRefusedError(
                "export_integrity_failure",
                "version has no immutable mapping; attach a mapping before "
                "export (the manifest v1 requires exactly-one Mapping)",
            )
        executable = extract_executable_prompt(version.get("api_prompt_json") or {})
        graph_hash = str(version.get("graph_hash") or "")
        if not isinstance(executable, dict) or not executable:
            raise ExportRefusedError(
                "export_integrity_failure",
                "version has no executable prompt to export",
            )
        try:
            recomputed = manifest_codec.graph_hash(executable)
        except ValueError:
            raise ExportRefusedError(
                "export_integrity_failure",
                "executable prompt contains non-finite values",
            ) from None
        if recomputed != graph_hash:
            raise ExportRefusedError(
                "graph_hash_mismatch",
                "persisted graph hash does not match the executable prompt",
            )

        model_rows = bundle["model_rows"]
        custom_node_rows = bundle["custom_node_rows"]
        graph_json = version.get("graph_json")
        aux_ids = extract_aux_id_provenance(graph_json)
        node_provenance = derive_node_provenance(custom_node_rows, aux_ids)
        evidence = risk.evidence_from_version_record(
            {
                "version_id": version_id,
                "graph_hash": graph_hash,
                "executable_prompt": executable,
                "api_prompt_json": version.get("api_prompt_json") or {},
                "graph_json": graph_json if isinstance(graph_json, dict) else {},
                "dependency_metadata": version.get("dependency_metadata") or {},
            },
            model_rows=model_rows,
            custom_node_rows=custom_node_rows,
            core_classes=core_classes_from_rows(custom_node_rows),
            node_provenance=node_provenance,
        )
        signals = risk.compute_signals(evidence)

        credential_keys = signals.get("__credential_keys__") or []
        if credential_keys:
            raise ExportRefusedError(
                pc.ISSUE_CREDENTIAL_LIKE_VALUE_DETECTED,
                "export refused: credential-like value detected in the "
                "workflow graph (%d field(s))" % len(credential_keys),
            )

        warnings: list[dict[str, str]] = []
        for gap in signals.get("__gap_refs__") or ():
            warnings.append(
                {
                    "code": pc.ISSUE_MODEL_EXTRACTION_GAP,
                    "message": (
                        "model-like loader input %s.%s (%s) is not covered by "
                        "known extraction mappings; omitted from manifest models"
                        % (gap.get("class_type"), gap.get("input"), gap.get("filename"))
                    ),
                }
            )
        custom_records, custom_findings = build_custom_node_manifest_records(
            custom_node_rows, aux_ids
        )
        for finding in custom_findings:
            warnings.append(
                {
                    "code": finding["code"],
                    "message": finding["message"],
                }
            )
        warnings.sort(key=lambda w: (w["code"], w["message"]))

        model_records = build_model_manifest_records(model_rows)
        asset_records = extract_asset_references(executable)

        display: dict[str, Any] = {}
        name = str(workflow.get("name") or "")
        description = str(workflow.get("description") or "")
        if name:
            display["name"] = name
        if description:
            display["description"] = description
        manifest_workflow: dict[str, Any] = {
            "workflow_id": str(workflow.get("workflow_id") or ""),
            "version_id": version_id,
            "graph_hash": graph_hash,
            "graph": copy.deepcopy(executable),
        }
        if display:
            manifest_workflow["display"] = display
        source: dict[str, str] = {}
        if workflow.get("source_author"):
            source["author"] = str(workflow["source_author"])
        if workflow.get("source_url"):
            source["url"] = str(workflow["source_url"])
        if source:
            manifest_workflow["source"] = source

        manifest_version_section = {
            "workflow_version_id": version_id,
            "workflow_id": str(workflow.get("workflow_id") or ""),
            "version_number": int(version.get("version_number") or 1),
            "immutable": True,
            "graph_hash": graph_hash,
            "created_at": str(version.get("created_at") or ""),
            "graph_json": copy.deepcopy(graph_json) if isinstance(graph_json, dict) else {},
            "api_prompt_json": copy.deepcopy(version.get("api_prompt_json") or {}),
        }

        manifest_mapping = {"mapping_id": "", "workflow_version_id": version_id, "entries": {}}
        if bundle["mapping"] is not None:
            raw_mapping = bundle["mapping"]
            entries: dict[str, Any] = {}
            for entry in raw_mapping.get("entries") or []:
                if isinstance(entry, dict) and entry.get("semantic_role"):
                    entries[str(entry["semantic_role"])] = copy.deepcopy(entry)
            manifest_mapping = {
                "mapping_id": str(raw_mapping.get("mapping_id") or ""),
                "workflow_version_id": version_id,
                "output_node_id": str(raw_mapping.get("output_node_id") or ""),
                "entries": entries,
            }

        preset_records = []
        if include_presets:
            default_preset_id = str(workflow.get("default_preset_id") or "")
            for preset in self.store.list_presets():
                if preset.get("workflow_version_id") != version_id:
                    continue
                record = copy.deepcopy(preset)
                record["is_default"] = (
                    default_preset_id != ""
                    and preset.get("preset_id") == default_preset_id
                )
                preset_records.append(record)
        preset_records.sort(key=lambda p: str(p.get("preset_id") or ""))

        metadata: dict[str, Any] = {
            "exported_at": _utc_now_iso(),
            "exporter": EXPORTER_ID,
        }
        if warnings:
            metadata["export_warnings"] = warnings

        manifest = build_manifest(
            workflow=manifest_workflow,
            version=manifest_version_section,
            mapping=manifest_mapping,
            presets=preset_records,
            models=model_records,
            custom_nodes=custom_records,
            assets=asset_records,
            metadata=metadata,
        )
        # Fail-closed credential policy over the ACTUAL artifact: any
        # credential-shaped exportable value refuses the download. Zero
        # mutation has occurred (export is read-only by construction).
        artifact_credentials = detect_manifest_credential_shapes(manifest)
        if artifact_credentials:
            raise ExportRefusedError(
                pc.ISSUE_CREDENTIAL_LIKE_VALUE_DETECTED,
                "export refused: credential-like value detected in the "
                "workflow graph (%d field(s))" % len(artifact_credentials),
            )
        filename = pc.suggest_export_filename(
            name or "workflow",
            int(version.get("version_number") or 1),
            graph_hash,
        )
        return {
            "manifest": manifest,
            "filename": filename,
            "warnings": warnings,
        }

    # ── Import (dry-run preview + atomic commit) ──────────────────────

    def _parse_validated_manifest(self, source: Any) -> dict:
        data = load_manifest_payload(source)
        try:
            return parse_manifest(data)
        except ManifestValidationError as exc:
            raise ImportBlockedError(
                "invalid manifest", [str(i) for i in exc.issues]
            ) from None

    def _manifest_analysis(self, manifest: dict) -> dict:
        """Adapt a valid manifest into evidence and run G6 + G7 (pure)."""
        workflow_section = manifest.get("workflow") or {}
        version_section = manifest.get("version") or {}
        executable = workflow_section.get("graph")
        if not isinstance(executable, dict):
            executable = {}
        api_prompt = version_section.get("api_prompt_json")
        if not isinstance(api_prompt, dict) or not api_prompt:
            api_prompt = executable
        graph_json = version_section.get("graph_json")
        if not isinstance(graph_json, dict):
            graph_json = {}

        model_stack: dict[str, list[str]] = {}
        node_classes: set[str] = set()
        for rec in manifest.get("models") or []:
            if not isinstance(rec, dict):
                continue
            role = rec.get("role")
            filename = rec.get("filename")
            if isinstance(role, str) and role and isinstance(filename, str) and filename:
                model_stack.setdefault(role, []).append(filename)
        for rec in manifest.get("custom_nodes") or []:
            if not isinstance(rec, dict):
                continue
            for cls in rec.get("classes") or []:
                if isinstance(cls, str) and cls:
                    node_classes.add(cls)
        synthetic_version = {
            "version_id": str(version_section.get("workflow_version_id") or ""),
            "graph_hash": str(workflow_section.get("graph_hash") or ""),
            "executable_prompt": executable,
            "api_prompt_json": api_prompt,
            "graph_json": graph_json,
            "dependency_metadata": {
                "model_stack": model_stack,
                "node_classes": sorted(node_classes),
            },
        }
        model_rows = adapt_manifest_models(
            manifest.get("models") or [], self._model_library
        )
        custom_rows = adapt_manifest_custom_nodes(
            manifest.get("custom_nodes") or [], self._custom_node_registry
        )
        readiness = check_readiness(manifest)
        analysis = self._compose_analysis(
            version_like=synthetic_version,
            graph_json=graph_json,
            model_rows=model_rows,
            custom_node_rows=custom_rows,
            manifest_readiness=readiness,
            referenced_assets=tuple(
                extract_asset_references(executable)
            ),
            manifest_version=int(manifest.get("manifest_version") or 1),
        )
        analysis["model_rows"] = model_rows
        analysis["custom_node_rows"] = custom_rows
        analysis["readiness"] = readiness
        analysis["synthetic_version"] = synthetic_version
        analysis["manifest_hash"] = manifest_hash(manifest)
        return analysis

    @staticmethod
    def _display_name_of(manifest: dict) -> str:
        workflow_section = manifest.get("workflow") or {}
        display = workflow_section.get("display")
        if isinstance(display, dict):
            name = display.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
        return "imported"

    def _existing_name_matches(self, base_name: str) -> list[dict[str, str]]:
        needle = base_name.casefold()
        matches = []
        for wf in self.store.list_workflows():
            name = str(wf.get("name") or "")
            folded = name.casefold()
            if folded == needle or (needle and needle in folded) or (folded and folded in needle):
                matches.append(
                    {
                        "workflow_id": str(wf.get("workflow_id") or ""),
                        "name": name,
                    }
                )
        matches.sort(key=lambda m: (m["name"], m["workflow_id"]))
        return matches

    def preview_import(self, source: Any) -> dict:
        """Dry-run import: full analysis, ZERO writes."""
        manifest = self._parse_validated_manifest(source)
        analysis = self._manifest_analysis(manifest)
        base_name = self._display_name_of(manifest)
        proposed_name = base_name + pc.IMPORT_SUGGESTED_NAME_SUFFIX
        import_presets = bool(manifest.get("presets"))
        # Deterministic security finding (never a blocker per the frozen G5
        # contract; values are never echoed).
        credential_shapes = detect_manifest_credential_shapes(manifest)
        issues: list[str] = []
        if credential_shapes:
            issues.append(
                "%s: %d credential-shaped field(s) detected in the manifest "
                "graphs (%s); values are not shown and were not altered"
                % (
                    pc.ISSUE_CREDENTIAL_LIKE_VALUE_DETECTED,
                    len(credential_shapes),
                    ", ".join(sorted({s["key"] for s in credential_shapes})),
                )
            )
        return {
            "status": pc.IMPORT_PREVIEW_STATUS,
            "valid": True,
            "manifest_version": int(manifest.get("manifest_version") or 1),
            "issues": issues,
            "readiness": analysis["readiness"],
            "portability": analysis["report"],
            "existing_name_matches": self._existing_name_matches(base_name),
            "proposed_name": proposed_name[:200],
            "will_create": {
                "workflow": True,
                "version": True,
                "mapping": True,
                "preset_count": len(manifest.get("presets") or []) if import_presets else 0,
            },
            "dependency_summary": _dependency_summary(
                analysis["model_rows"], analysis["custom_node_rows"]
            ),
            "manifest_hash": analysis["manifest_hash"],
            "security_findings": [
                {"code": pc.ISSUE_CREDENTIAL_LIKE_VALUE_DETECTED, "count": len(credential_shapes)}
            ]
            if credential_shapes
            else [],
        }

    def _build_import_records(
        self,
        manifest: dict,
        *,
        import_presets: bool,
        apply_default_preset: bool,
    ) -> dict:
        """Mint ALL local records for a committed import (no writes here)."""
        workflow_section = manifest.get("workflow") or {}
        version_section = manifest.get("version") or {}
        mapping_section = manifest.get("mapping") or {}

        api_prompt = version_section.get("api_prompt_json")
        if not isinstance(api_prompt, dict) or not api_prompt:
            api_prompt = workflow_section.get("graph")
        if not isinstance(api_prompt, dict):
            api_prompt = {}
        graph_json = version_section.get("graph_json")
        if not isinstance(graph_json, dict):
            graph_json = {}
        executable = extract_executable_prompt(api_prompt)
        declared_hash = str(workflow_section.get("graph_hash") or "")
        try:
            recomputed = manifest_codec.graph_hash(executable)
        except ValueError:
            raise ImportBlockedError(
                "manifest graph contains non-finite values"
            ) from None
        if recomputed != declared_hash:
            raise ImportBlockedError(
                "graph hash mismatch against the executable prompt",
                issues=[
                    "graph hash mismatch: manifest declares %s but the captured "
                    "graph hashes to %s" % (declared_hash, recomputed)
                ],
            )

        now = _utc_now_iso()
        new_workflow_id = make_workflow_id()
        new_version_id = make_version_id()
        new_mapping_id = make_mapping_id()

        display = workflow_section.get("display") or {}
        base_name = (
            display.get("name")
            if isinstance(display, dict) and isinstance(display.get("name"), str)
            else ""
        ) or "imported"
        proposed_name = (base_name + pc.IMPORT_SUGGESTED_NAME_SUFFIX)[:200]
        description = (
            display.get("description")
            if isinstance(display, dict) and isinstance(display.get("description"), str)
            else ""
        )
        # Declared origin attribution (user-facing authority fields designed
        # for exactly this); machine provenance stays structured under
        # dependency_metadata.import_provenance.
        source_section = workflow_section.get("source")
        source_author = ""
        source_url = ""
        if isinstance(source_section, dict):
            if isinstance(source_section.get("author"), str):
                source_author = source_section["author"][:500]
            if isinstance(source_section.get("url"), str):
                source_url = source_section["url"][:2000]

        dependency_metadata = extract_dependency_metadata(
            {"api_prompt_json": api_prompt, "graph_json": graph_json}
        )
        dependency_metadata["import_provenance"] = {
            "original_workflow_id": str(workflow_section.get("workflow_id") or ""),
            "original_version_id": str(version_section.get("workflow_version_id") or ""),
            "original_version_number": version_section.get("version_number"),
            "original_graph_hash": declared_hash,
            "manifest_hash": manifest_hash(manifest),
            "manifest_version": int(manifest.get("manifest_version") or 1),
            "exporter": (manifest.get("metadata") or {}).get("exporter"),
            "imported_at": now,
        }

        workflow = Workflow(
            workflow_id=new_workflow_id,
            name=proposed_name,
            description=(description or "")[:2000],
            folder="",
            tags=[],
            favorite=False,
            source_url=source_url,
            source_author=source_author,
            compatible_models=[],
            default_preset_id="",
            latest_version_id=new_version_id,
            created_at=now,
            updated_at=now,
        )

        version = WorkflowVersion(
            workflow_version_id=new_version_id,
            workflow_id=new_workflow_id,
            version_number=1,
            graph_json=copy.deepcopy(graph_json),
            api_prompt_json=copy.deepcopy(api_prompt),
            executable_prompt=dict(executable),
            graph_hash=recomputed,
            created_at=now,
            dependency_metadata=dependency_metadata,
            compatible_models=[],
        )

        entries_list = []
        for role, entry in (mapping_section.get("entries") or {}).items():
            if not isinstance(entry, dict):
                continue
            item = dict(entry)
            item.setdefault("semantic_role", str(role))
            item["semantic_role"] = str(role)
            entries_list.append(item)
        mapping = Mapping.from_dict(
            {
                "mapping_id": new_mapping_id,
                "workflow_version_id": new_version_id,
                "created_at": now,
                "updated_at": now,
                "output_node_id": str(mapping_section.get("output_node_id") or ""),
                "entries": entries_list,
            }
        )

        presets: list[WorkflowPreset] = []
        preset_id_map: dict[str, str] = {}
        default_source_id = ""
        defaults = [
            p
            for p in (manifest.get("presets") or [])
            if isinstance(p, dict) and p.get("is_default") is True
        ]
        if len(defaults) == 1:
            default_source_id = str(defaults[0].get("preset_id") or "")
        if import_presets:
            for source_preset in manifest.get("presets") or []:
                if not isinstance(source_preset, dict):
                    continue
                new_preset_id = make_preset_id()
                source_id = str(source_preset.get("preset_id") or "")
                if source_id:
                    preset_id_map[source_id] = new_preset_id
                record = dict(source_preset)
                record["preset_id"] = new_preset_id
                record["workflow_version_id"] = new_version_id
                record["workflow_id"] = new_workflow_id
                presets.append(WorkflowPreset.from_dict(record))

        applied_default_preset_id = ""
        default_application_note = ""
        if apply_default_preset:
            if not import_presets:
                default_application_note = (
                    "apply_default_preset requested without import_presets; "
                    "no default applied"
                )
            elif not default_source_id:
                default_application_note = (
                    "no single manifest default preset; no default applied"
                )
            else:
                local_default = preset_id_map.get(default_source_id)
                if local_default:
                    workflow.default_preset_id = local_default
                    applied_default_preset_id = local_default
                    default_application_note = ""

        return {
            "workflow": workflow,
            "version": version,
            "mapping": mapping,
            "presets": presets,
            "applied_default_preset_id": applied_default_preset_id,
            "default_application_note": default_application_note,
            "preset_id_map": preset_id_map,
            "proposed_name": proposed_name,
        }

    def commit_import(
        self,
        source: Any,
        *,
        import_presets: bool = False,
        apply_default_preset: bool = False,
    ) -> dict:
        """Committed import: validate fully, then create ALL records in ONE
        atomic domain transaction.  Any failure leaves zero partial state."""
        manifest = self._parse_validated_manifest(source)
        analysis = self._manifest_analysis(manifest)
        records = self._build_import_records(
            manifest,
            import_presets=import_presets,
            apply_default_preset=apply_default_preset,
        )
        created = self.store.commit_import_transaction(
            records["workflow"],
            records["version"],
            records["mapping"],
            records["presets"],
        )
        provenance = created["version"]["dependency_metadata"].get(
            "import_provenance"
        )
        return {
            "status": "ok",
            "workflow_id": created["workflow"]["workflow_id"],
            "workflow_version_id": created["version"]["workflow_version_id"],
            "mapping_id": created["mapping"]["mapping_id"],
            "preset_ids": [p["preset_id"] for p in created["presets"]],
            "applied_default_preset_id": records["applied_default_preset_id"] or None,
            "default_application_note": records["default_application_note"],
            "workflow_name": created["workflow"]["name"],
            "provenance": provenance,
            "dependency_summary": _dependency_summary(
                analysis["model_rows"], analysis["custom_node_rows"]
            ),
            "portability_risk_level": analysis["report"]["risk_level"],
            "manifest_hash": analysis["manifest_hash"],
        }

    # ── Live portability report ───────────────────────────────────────

    def portability_report(
        self, version_id: str, *, current_stamp: Optional[dict] = None
    ) -> dict:
        """Compute the CURRENT G5 report for a persisted WorkflowVersion.

        LIVE ONLY: no cache lookup, no cache write (the cached flow wraps
        this method).  ``current_stamp`` optionally supplies the full
        8-field invalidation stamp so the assembled report is cacheable
        against exactly the caller's evidence.
        """
        bundle = self._version_bundle(version_id)
        version = bundle["version"]
        executable = extract_executable_prompt(version.get("api_prompt_json") or {})
        graph_json = version.get("graph_json")
        analysis = self._compose_analysis(
            version_like={
                "version_id": version_id,
                "graph_hash": str(version.get("graph_hash") or ""),
                "executable_prompt": executable if isinstance(executable, dict) else {},
                "api_prompt_json": version.get("api_prompt_json") or {},
                "graph_json": graph_json if isinstance(graph_json, dict) else {},
                "dependency_metadata": version.get("dependency_metadata") or {},
            },
            graph_json=graph_json if isinstance(graph_json, dict) else {},
            model_rows=bundle["model_rows"],
            custom_node_rows=bundle["custom_node_rows"],
            manifest_readiness=None,
            referenced_assets=tuple(
                extract_asset_references(executable if isinstance(executable, dict) else {})
            ),
            current_stamp=current_stamp,
        )
        return analysis["report"]

    # ── Cached report flow (Phase G11) ────────────────────────────────

    def current_invalidation_stamp(self, version: dict) -> dict:
        """Build the CURRENT 8-field G5 stamp from authoritative evidence.

        * ``workflow_version_id`` / ``graph_hash`` — the persisted immutable
          Version record (never browser input).
        * ``dependency_metadata_hash`` — canonical SHA-256 of the persisted
          ``dependency_metadata`` (sorted keys, no NaN); None when absent.
        * generations — opaque tokens derived from the injected authorities
          (None when no authority is wired → conservative stale).
        * ``rule_version`` / ``manifest_version`` — the landed constants.
        * ``comfyui_version`` — cheapest existing guarded runtime identity.
        """
        dependency_metadata = (version or {}).get("dependency_metadata")
        return pc.build_invalidation_stamp(
            workflow_version_id=str((version or {}).get("workflow_version_id") or "") or None,
            graph_hash=str((version or {}).get("graph_hash") or "") or None,
            dependency_metadata_hash=(
                pc.sha256_of_canonical(dependency_metadata)
                if isinstance(dependency_metadata, dict)
                else None
            ),
            model_library_generation=model_library_generation_token(
                self._model_generation_source
            ),
            custom_node_registry_generation=custom_node_registry_generation_token(
                self._registry_generation_source
            ),
            rule_version=pc.PORTABILITY_RULE_VERSION,
            manifest_version=manifest_codec.MANIFEST_SCHEMA_VERSION,
            comfyui_version=_comfyui_version(),
        )

    def _recompute_report(self, version_id: str, stamp: dict) -> dict:
        """Recompute live through the unchanged G9 pipeline (or DI analyzer)
        and stamp the result with the CURRENT authoritative evidence."""
        if self._analyzer is not None:
            report = dict(self._analyzer(version_id))
        else:
            report = self.portability_report(version_id, current_stamp=stamp)
        report["invalidation"] = copy.deepcopy(stamp)
        return report

    def cached_portability_report(self, version_id: str) -> dict:
        """Explicit detail-endpoint flow: hit serves the cache; everything
        else recomputes live and refreshes the derived entry.

        Cache failures FAIL OPEN: a broken sidecar can never turn a valid
        Workflow into an error while live analysis succeeds.  Stale reports
        are never served as current from this flow.  A hit performs NO
        resolver/G6/G7 work: only the persisted Version record and the
        cheap stamp authorities are read.
        """
        version = self.store.get_version(version_id)
        if version is None:
            from studio_domain.models import WorkflowVersionNotFoundError

            raise WorkflowVersionNotFoundError(
                f"workflow version {version_id!r} not found"
            )
        stamp = self.current_invalidation_stamp(version)
        state = STATE_MISS
        mismatched: tuple = ()
        diagnostics: tuple = ()
        lookup = None
        if self.cache is not None:
            try:
                lookup = self.cache.get(version_id, stamp)
                state = lookup.state
                mismatched = tuple(lookup.mismatched_fields)
                diagnostics = tuple(self.cache.last_diagnostics)
            except Exception as exc:  # noqa: BLE001 — fail open
                diagnostics = ("cache get failed open: %s" % exc,)
                _log.warning("Portability cache get failed open: %s", exc)
        if lookup is not None and lookup.hit:
            return {
                "report": lookup.report,
                "cache": {
                    "state": STATE_HIT,
                    "recomputed": False,
                    "mismatched_fields": [],
                    "diagnostics": list(diagnostics),
                },
            }
        report = self._recompute_report(version_id, stamp)
        put_diagnostics: tuple = ()
        if self.cache is not None:
            try:
                put_result = self.cache.put(report)
                if not put_result.ok:
                    put_diagnostics = tuple(put_result.reasons)
                    _log.warning(
                        "Portability cache put rejected for %r: %s",
                        version_id,
                        "; ".join(put_result.reasons),
                    )
            except Exception as exc:  # noqa: BLE001 — fail open
                put_diagnostics = ("cache put failed open: %s" % exc,)
                _log.warning("Portability cache put failed open: %s", exc)
        return {
            "report": report,
            "cache": {
                "state": state,
                "recomputed": True,
                "mismatched_fields": list(mismatched),
                "diagnostics": list(diagnostics) + list(put_diagnostics),
            },
        }

    # ── List-card summaries (NEVER analyzes) ──────────────────────────

    def workflow_portability_summaries(
        self, workflows: list
    ) -> dict[str, Optional[dict]]:
        """Cheap ``portability_summary`` per workflow id from the derived
        cache ONLY — never runs G6/G7, never invokes the resolver, never
        writes.  Shape (frozen): ``{version_id, risk_level, issue_count,
        stale, analyzed_at}`` or None when no usable cached row exists.

        ``stale`` tri-state: False = verified current against the cheaply
        constructed stamp; True = checked and outdated; None = freshness
        unknowable on this path (never asserted current).
        """
        wf_ids = [str(w.get("workflow_id") or "") for w in workflows or []]
        empty: dict[str, Optional[dict]] = {wf_id: None for wf_id in wf_ids}
        if self.cache is None:
            return empty
        try:
            latest_ids: list[str] = []
            by_workflow: dict[str, str] = {}
            for workflow in workflows or []:
                wf_id = str(workflow.get("workflow_id") or "")
                version_id = str(workflow.get("latest_version_id") or "")
                if not wf_id or not version_id:
                    continue
                latest_ids.append(version_id)
                by_workflow[wf_id] = version_id
            if not latest_ids:
                return empty
            unique_ids = sorted(set(latest_ids))
            stamps: dict = {}
            unstamped: list[str] = []
            for version_id in unique_ids:
                version = self.store.get_version(version_id)
                if version:
                    stamps[version_id] = self.current_invalidation_stamp(version)
                else:
                    unstamped.append(version_id)
            entries = self.cache.summaries(unique_ids, current_stamps=stamps)
            if unstamped:
                # Dangling latest pointers: freshness unknowable (stale=None),
                # never silently asserted current.
                entries = entries + self.cache.summaries(unstamped, current_stamps=None)
            by_version = {e["version_id"]: e for e in entries}
            out: dict[str, Optional[dict]] = {}
            for wf_id in wf_ids:
                version_id = by_workflow.get(wf_id)
                entry = by_version.get(version_id) if version_id else None
                out[wf_id] = (
                    {
                        "version_id": entry["version_id"],
                        "risk_level": entry["risk_level"],
                        "issue_count": entry["issue_count"],
                        "stale": entry["stale"],
                        "analyzed_at": entry["analyzed_at"],
                    }
                    if entry is not None
                    else None
                )
            return out
        except Exception as exc:  # noqa: BLE001 — list must never crash
            _log.warning("Portability summary enrichment failed open: %s", exc)
            return empty


__all__ = [
    "PortabilityService",
    "PortabilityError",
    "ExportRefusedError",
    "ImportBlockedError",
    "load_manifest_payload",
    "model_library_generation_token",
    "custom_node_registry_generation_token",
]
