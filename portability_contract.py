"""Pure portability contract freeze (Phase G5).

Single machine-readable authority for the shared Phase-G portability
contracts: risk vocabularies, target ids, issue/report/invalidation payload
shapes, endpoint contracts, security limits, and deterministic helpers.

This module OWNS ONLY contracts. It performs NO I/O, NO network access,
NO registry scans, NO route registration, NO risk computation, and NO
provider calls. It imports only the Python standard library and must stay
that way (same purity discipline as ``studio_workflow_manifest.py``).

The canonical v1 portability ARTIFACT remains the existing single-JSON
Studio Workflow Manifest built/validated by ``studio_workflow_manifest.py``
(``WORKFLOW_MANIFEST_FORMAT.md``). This module never replaces that format;
it freezes everything AROUND it so later lanes (risk engine, target rules,
backend wiring, report cache, frontend) implement one product.

Authoritative reconciliation document:
``PHASE_G5_PORTABILITY_CONTRACT_FREEZE_2026-08-23.md``.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

# ── Rule / format versions ────────────────────────────────────────────────

# Shared by the future risk engine AND target-rule adapters. A rule behavior
# change requires an intentional bump of this value; it is NEVER derived from
# the app version.
PORTABILITY_RULE_VERSION = "portability-rules-v1"

# The sole export artifact authority (existing manifest v1; do not fork).
MANIFEST_AUTHORITY_MODULE = "studio_workflow_manifest"
MANIFEST_AUTHORITY_DOC = "WORKFLOW_MANIFEST_FORMAT.md"
SUPPORTED_MANIFEST_VERSIONS = (1,)

# ── Separately-named concepts (never collapse these) ──────────────────────

CONCEPT_MANIFEST_READINESS = "manifest_readiness"
CONCEPT_DEPENDENCY_AVAILABILITY = "dependency_availability"
CONCEPT_WORKFLOW_PORTABILITY_RISK = "workflow_portability_risk"
CONCEPT_TARGET_READINESS = "target_readiness"
CONCEPT_ENVIRONMENT_REPRODUCIBILITY = "environment_reproducibility"

PORTABILITY_CONCEPTS = (
    CONCEPT_MANIFEST_READINESS,
    CONCEPT_DEPENDENCY_AVAILABILITY,
    CONCEPT_WORKFLOW_PORTABILITY_RISK,
    CONCEPT_TARGET_READINESS,
    CONCEPT_ENVIRONMENT_REPRODUCIBILITY,
)

# ── Risk levels (workflow portability risk AND target readiness) ──────────


class PortabilityRiskLevel:
    """Wire values are lowercase strings (house style: resolver states)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


RISK_LEVELS = (
    PortabilityRiskLevel.LOW,
    PortabilityRiskLevel.MEDIUM,
    PortabilityRiskLevel.HIGH,
    PortabilityRiskLevel.UNKNOWN,
)

# Frozen severity philosophy (exact rules live in the risk engine lane):
RISK_LEVEL_SEMANTICS = {
    PortabilityRiskLevel.LOW: (
        "no blocking or unresolved findings; graph structurally portable; "
        "dependencies resolved with sufficient identity evidence; no "
        "required environment-bound inputs"
    ),
    PortabilityRiskLevel.MEDIUM: (
        "portable with explicit setup/attention: known but unpinned "
        "dependencies, model refs without byte hashes, separately "
        "transported assets, resolvable mismatches, soft structural concerns"
    ),
    PortabilityRiskLevel.HIGH: (
        "likely or non-negotiable execution blocker for portability: "
        "unresolved required node identity, host-bound path required by the "
        "graph, unavailable dependency/source, manifest readiness failure, "
        "or a target explicitly cannot satisfy a requirement"
    ),
    PortabilityRiskLevel.UNKNOWN: (
        "analyzer cannot make a defensible determination: evidence store "
        "unreadable, essential analysis unavailable, or target capability "
        "itself unknown and the decision depends on it"
    ),
}

# Issue severity has NO unknown value. UNKNOWN is a report-level verdict,
# represented by an issue/reason explaining why no verdict was possible.
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

SEVERITIES = (SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW)

_SEVERITY_RANK = {SEVERITY_HIGH: 3, SEVERITY_MEDIUM: 2, SEVERITY_LOW: 1}

# ── Target ids (sole vocabulary; banned aliases below) ────────────────────

TARGET_LOCAL = "local"
TARGET_MODAL = "modal"
TARGET_RUNPOD = "runpod"
TARGET_RUNCOMFY = "runcomfy"
TARGET_COMFY_CLOUD = "comfy_cloud"
TARGET_BASETEN = "baseten"

TARGET_IDS = (
    TARGET_LOCAL,
    TARGET_MODAL,
    TARGET_RUNPOD,
    TARGET_RUNCOMFY,
    TARGET_COMFY_CLOUD,
    TARGET_BASETEN,
)

# Never appear in wire payloads (audit shorthand only):
BANNED_TARGET_ALIASES = ("comfy-cloud", "comfycloud", "run_comfy")

# ── Stable subject vocabulary for issues ──────────────────────────────────

SUBJECT_GRAPH = "graph"
SUBJECT_CUSTOM_NODES = "custom_nodes"
SUBJECT_MODELS = "models"
SUBJECT_ASSETS = "assets"
SUBJECT_PATHS = "paths"
SUBJECT_ENDPOINTS = "endpoints"
SUBJECT_FRONTEND = "frontend"
SUBJECT_ENVIRONMENT = "environment"
SUBJECT_MANIFEST = "manifest"
SUBJECT_TARGET = "target"

SUBJECT_VOCABULARY = (
    SUBJECT_GRAPH,
    SUBJECT_CUSTOM_NODES,
    SUBJECT_MODELS,
    SUBJECT_ASSETS,
    SUBJECT_PATHS,
    SUBJECT_ENDPOINTS,
    SUBJECT_FRONTEND,
    SUBJECT_ENVIRONMENT,
    SUBJECT_MANIFEST,
    SUBJECT_TARGET,
)

# ── Static signal names (G1 S1–S12, de-numbered for the wire) ─────────────
# Names are frozen; COMPUTATION belongs to the later risk-engine lane.

SIGNAL_HAS_ABSOLUTE_PATH = "has_absolute_path"
SIGNAL_HAS_UNRESOLVED_NODE_TYPE = "has_unresolved_node_type"
SIGNAL_UNRESOLVED_NODE_COUNT = "unresolved_node_count"
SIGNAL_CUSTOM_NODE_COUNT = "custom_node_count"
SIGNAL_CUSTOM_REPO_COUNT = "custom_repo_count"
SIGNAL_CUSTOM_NODE_REVISION_PINNED = "custom_node_revision_pinned"
SIGNAL_MODEL_REF_BASENAME_ONLY = "model_ref_basename_only"
SIGNAL_MODEL_HASH_PINNED = "model_hash_pinned"
SIGNAL_MODEL_EXTRACTION_GAP = "model_extraction_gap"
SIGNAL_REQUIRES_INPUT_ASSET = "requires_input_asset"
SIGNAL_HAS_EXTERNAL_ENDPOINT = "has_external_endpoint"
SIGNAL_USES_SUBGRAPHS = "uses_subgraphs"
SIGNAL_EXACT_ROUNDTRIP_PROVEN = "exact_roundtrip_proven"
SIGNAL_ENV_BOUND_REGISTRY_LEAK = "env_bound_registry_leak"

_BOOLEAN_SIGNAL_NAMES = (
    SIGNAL_HAS_ABSOLUTE_PATH,
    SIGNAL_HAS_UNRESOLVED_NODE_TYPE,
    SIGNAL_CUSTOM_NODE_REVISION_PINNED,
    SIGNAL_MODEL_REF_BASENAME_ONLY,
    SIGNAL_MODEL_HASH_PINNED,
    SIGNAL_MODEL_EXTRACTION_GAP,
    SIGNAL_REQUIRES_INPUT_ASSET,
    SIGNAL_HAS_EXTERNAL_ENDPOINT,
    SIGNAL_USES_SUBGRAPHS,
    SIGNAL_EXACT_ROUNDTRIP_PROVEN,
    SIGNAL_ENV_BOUND_REGISTRY_LEAK,
)

_COUNT_SIGNAL_NAMES = (
    SIGNAL_UNRESOLVED_NODE_COUNT,
    SIGNAL_CUSTOM_NODE_COUNT,
    SIGNAL_CUSTOM_REPO_COUNT,
)

SIGNAL_NAMES = _BOOLEAN_SIGNAL_NAMES + _COUNT_SIGNAL_NAMES

_SIGNAL_TYPES = {name: "bool" for name in _BOOLEAN_SIGNAL_NAMES}
_SIGNAL_TYPES.update({name: "count" for name in _COUNT_SIGNAL_NAMES})

# ── Dependency provenance quality (evidence-based, not trust-based) ───────

PROVENANCE_EXACT = "exact"          # trusted repo identity + enforced revision/hash
PROVENANCE_DECLARED = "declared"    # declared by record/metadata, not verified
PROVENANCE_INFERRED = "inferred"    # derived heuristically (e.g. registry fallback)
PROVENANCE_UNRESOLVED = "unresolved"  # no usable provenance evidence

PROVENANCE_QUALITY_VALUES = (
    PROVENANCE_EXACT,
    PROVENANCE_DECLARED,
    PROVENANCE_INFERRED,
    PROVENANCE_UNRESOLVED,
)

# ── Foundational issue codes (stable; used by the next lanes) ─────────────

ISSUE_CREDENTIAL_LIKE_VALUE_DETECTED = "credential_like_value_detected"
ISSUE_LOCAL_PATH_REFERENCE = "local_path_reference"
ISSUE_UNRESOLVED_NODE_TYPE = "unresolved_node_type"
ISSUE_CUSTOM_NODE_UNPINNED = "custom_node_unpinned"
ISSUE_MODEL_HASH_UNPINNED = "model_hash_unpinned"
ISSUE_MODEL_EXTRACTION_GAP = "model_extraction_gap"
ISSUE_REQUIRED_INPUT_ASSET = "required_input_asset"
ISSUE_EXTERNAL_ENDPOINT_REFERENCE = "external_endpoint_reference"
ISSUE_SUBGRAPH_FRONTEND_REQUIREMENT = "subgraph_frontend_requirement"
ISSUE_MANIFEST_NOT_READY = "manifest_not_ready"
ISSUE_DEPENDENCY_MISSING = "dependency_missing"
ISSUE_DEPENDENCY_WRONG_REVISION = "dependency_wrong_revision"
ISSUE_TARGET_CAPABILITY_UNKNOWN = "target_capability_unknown"

FOUNDATIONAL_ISSUE_CODES = (
    ISSUE_CREDENTIAL_LIKE_VALUE_DETECTED,
    ISSUE_LOCAL_PATH_REFERENCE,
    ISSUE_UNRESOLVED_NODE_TYPE,
    ISSUE_CUSTOM_NODE_UNPINNED,
    ISSUE_MODEL_HASH_UNPINNED,
    ISSUE_MODEL_EXTRACTION_GAP,
    ISSUE_REQUIRED_INPUT_ASSET,
    ISSUE_EXTERNAL_ENDPOINT_REFERENCE,
    ISSUE_SUBGRAPH_FRONTEND_REQUIREMENT,
    ISSUE_MANIFEST_NOT_READY,
    ISSUE_DEPENDENCY_MISSING,
    ISSUE_DEPENDENCY_WRONG_REVISION,
    ISSUE_TARGET_CAPABILITY_UNKNOWN,
)

# Environment-reproducibility dimension codes (G2 findings vocabulary).
# These are reported in the environment section and MUST NOT force the
# WorkflowVersion's own portability risk level.
ENV_TORCH_STACK_UNPINNED = "torch_stack_unpinned"
ENV_CUSTOM_NODE_SOURCE_UNPINNED = "custom_node_source_unpinned"
ENV_PLUGIN_WORKTREE_DIRTY = "plugin_worktree_dirty"
ENV_LOCAL_CORE_PATCH_DIVERGENCE = "local_core_patch_divergence"
ENV_MODEL_HASH_UNPINNED = "model_hash_unpinned"
ENV_BASE_IMAGE_DIGEST_UNPINNED = "base_image_digest_unpinned"

ENVIRONMENT_ISSUE_CODES = (
    ENV_TORCH_STACK_UNPINNED,
    ENV_CUSTOM_NODE_SOURCE_UNPINNED,
    ENV_PLUGIN_WORKTREE_DIRTY,
    ENV_LOCAL_CORE_PATCH_DIVERGENCE,
    ENV_MODEL_HASH_UNPINNED,
    ENV_BASE_IMAGE_DIGEST_UNPINNED,
)

ENVIRONMENT_SOURCE_CURRENT_STUDIO = "current_studio_environment"

# ── Summary report contract ───────────────────────────────────────────────

REPORT_REQUIRED_FIELDS = (
    "version_id",
    "graph_hash",
    "risk_level",
    "rule_version",
    "issue_count",
    "counts",
    "issues",
    "signals",
    "targets",
    "environment",
    "stale",
    "invalidation",
    "analyzed_at",
)

# Target results reference global issues[] BY CODE; target-only issues are
# still full objects in the single global issues[] list (one rendering
# authority), referenced from the owning target's issue_codes.
TARGET_RESULT_REQUIRED_FIELDS = ("risk_level", "issue_codes", "advice")

COUNT_KEYS = SEVERITIES

# ── Invalidation stamp contract (cache is derived-only, never gates runs) ─

INVALIDATION_FIELDS = (
    "workflow_version_id",
    "graph_hash",
    "dependency_metadata_hash",
    "model_library_generation",
    "custom_node_registry_generation",
    "rule_version",
    "manifest_version",
    "comfyui_version",
)

# ── Checklist contract (pure derived model from a report) ─────────────────

CHECKLIST_FIELDS = (
    "summary_risk_level",
    "issue_counts",
    "issue_rows",
    "dependency_table",
    "target_matrix",
    "import_expectations",
    "provenance",
    "rule_version",
    "analyzed_at",
)

# ── Export endpoint contract ──────────────────────────────────────────────

EXPORT_ENDPOINT = "/comfymodal/studio/workflows/versions/{version_id}/export"
EXPORT_FILENAME_SUFFIX = ".workflow.json"
EXPORT_FILENAME_NAME_CAP = 60

# ── Import endpoint contract ──────────────────────────────────────────────

IMPORT_MANIFEST_ENDPOINT = "/comfymodal/studio/workflows/import-manifest"
IMPORT_QUERY_DRY_RUN = "dry_run"
IMPORT_DEFAULT_DRY_RUN = True  # preview writes NOTHING unless explicitly 0
IMPORT_PREVIEW_STATUS = "preview"
IMPORT_SUGGESTED_NAME_SUFFIX = " (imported)"

# ── Security limits (route layer enforces; frozen here) ───────────────────

MAX_IMPORT_BODY_BYTES = 10 * 1024 * 1024  # 10 MiB
MAX_JSON_DEPTH = 64
MAX_JSON_ELEMENTS = 200000
EVIDENCE_MAX_CANONICAL_BYTES = 2048

SECURITY_RULES = (
    "max request body 10 MiB (or stricter common app cap)",
    "JSON depth/element sanity limits enforced before parse",
    "NaN/Infinity rejected",
    "no archive extraction in v1",
    "manifest filenames are data, never joined to filesystem paths",
    "repo/model URLs are inert data, never auto-fetched",
    "zero install operations during import",
    "zero shell execution",
    "credential-shaped embedded values produce a deterministic finding",
    "exporter must not leak known secrets or local install paths",
)

# ── Reconciled policies (machine-readable descriptors) ────────────────────

# Subgraphs require a sufficiently new frontend; presence alone is NOT a
# universal HIGH. Local/Modal may stay low-impact when the environment
# guarantees an adequate frontend; targets that cannot support them raise
# severity in their own rules.
POLICY_SUBGRAPHS = "target_sensitive_not_global_blocker"

# Absolute paths are always a workflow-level finding; LOCAL may deem a
# self-consistent host path operationally usable while every other target
# becomes HIGH via severity override. The summary algorithm is explicitly
# source-environment-oriented and must document this rule.
POLICY_ABSOLUTE_PATHS = "global_finding_with_target_severity_override"

# G2 source-environment debt lives in the environment section only.
POLICY_ENVIRONMENT_ISOLATION = (
    "environment_reproducibility_never_forces_workflow_or_target_risk"
)

# ── Errors ────────────────────────────────────────────────────────────────


class PortabilityContractError(ValueError):
    """Raised when a contract payload fails validation; carries ALL issues."""

    def __init__(self, issues):
        self.issues = list(issues)
        super().__init__("; ".join(self.issues))


# ── Private helpers ───────────────────────────────────────────────────────

_SHA256_HEX_RE = re.compile(r"[0-9a-f]{64}")
_ISSUE_CODE_RE = re.compile(r"[a-z0-9]+(_[a-z0-9]+)*")

_CANONICAL_JSON_KWARGS = {
    "sort_keys": True,
    "separators": (",", ":"),
    "ensure_ascii": False,
    "allow_nan": False,
}


def _is_str(value) -> bool:
    return isinstance(value, str)


def _nonempty_str(value) -> bool:
    return isinstance(value, str) and bool(value)


def _is_bool(value) -> bool:
    return isinstance(value, bool)


def _is_count(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _reject_json_constant(name: str):
    raise ValueError("non-finite JSON constant: %s" % name)


# ── Canonical serialization (project convention) ──────────────────────────


def canonical_json(obj: Any) -> str:
    """Deterministic JSON string: sorted keys, compact separators, no NaN."""
    return json.dumps(obj, **_CANONICAL_JSON_KWARGS)


def canonical_bytes(obj: Any) -> bytes:
    return canonical_json(obj).encode("utf-8")


def sha256_of_canonical(obj: Any) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def is_sha256_hex(value) -> bool:
    return isinstance(value, str) and _SHA256_HEX_RE.fullmatch(value) is not None


# ── Normalizers ───────────────────────────────────────────────────────────


def normalize_risk_level(value) -> str:
    """Canonical lowercase risk level; case-insensitive on input."""
    if isinstance(value, str):
        candidate = value.strip().lower()
        if candidate in RISK_LEVELS:
            return candidate
    raise PortabilityContractError(
        ["invalid risk level: %r (valid: %s)" % (value, ", ".join(RISK_LEVELS))]
    )


def normalize_severity(value) -> str:
    if isinstance(value, str):
        candidate = value.strip().lower()
        if candidate in SEVERITIES:
            return candidate
    raise PortabilityContractError(
        ["invalid severity: %r (valid: %s)" % (value, ", ".join(SEVERITIES))]
    )


def normalize_target_id(value) -> str:
    if isinstance(value, str):
        candidate = value.strip()
        if candidate in TARGET_IDS:
            return candidate
    raise PortabilityContractError(
        ["invalid target id: %r (valid: %s)" % (value, ", ".join(TARGET_IDS))]
    )


def normalize_signals(signals) -> dict:
    """Validate a signals payload against the frozen vocabulary/types.

    Unknown signal names are rejected (adding signals requires a
    PORTABILITY_RULE_VERSION bump). Omitted signals simply mean "not
    computed". Returns a new dict; input is never mutated.
    """
    if not isinstance(signals, dict):
        raise PortabilityContractError(["signals must be a dict"])
    issues = []
    out = {}
    for name, value in signals.items():
        kind = _SIGNAL_TYPES.get(name)
        if kind is None:
            issues.append("unknown signal name: %r" % (name,))
            continue
        if kind == "bool":
            if not _is_bool(value):
                issues.append("signal %s must be a bool" % name)
                continue
        else:
            if not _is_count(value):
                issues.append("signal %s must be a non-negative int" % name)
                continue
        out[name] = value
    if issues:
        raise PortabilityContractError(issues)
    return out


# ── Issue contract ────────────────────────────────────────────────────────

ISSUE_FIELDS = ("code", "severity", "message", "subject", "fix_hint", "evidence")


def build_issue(
    *,
    code: str,
    severity: str,
    message: str,
    subject: str,
    fix_hint: str = "",
    evidence: dict | None = None,
) -> dict:
    """Build one canonical issue dict (validates; pure)."""
    return normalize_issue(
        {
            "code": code,
            "severity": severity,
            "message": message,
            "subject": subject,
            "fix_hint": fix_hint,
            "evidence": evidence,
        }
    )


def normalize_issue(issue) -> dict:
    """Normalize one issue to the canonical shape; raises with all problems.

    Canonical shape:
      {"code": str, "severity": high|medium|low, "message": str,
       "subject": <vocabulary>, "fix_hint": str ("" default),
       "evidence": optional bounded dict — omitted when empty}
    """
    issues = []
    if not isinstance(issue, dict):
        raise PortabilityContractError(["issue must be a dict"])

    code = issue.get("code")
    if not isinstance(code, str) or not code:
        issues.append("issue.code must be a non-empty snake_case string")
    elif _ISSUE_CODE_RE.fullmatch(code) is None:
        issues.append("issue.code must be a non-empty snake_case string")
    sev = issue.get("severity")
    try:
        sev = normalize_severity(sev)
    except PortabilityContractError as exc:
        issues.extend(exc.issues)
    msg = issue.get("message")
    if not _nonempty_str(msg):
        issues.append("issue.message must be a non-empty string")
    subject = issue.get("subject")
    if subject not in SUBJECT_VOCABULARY:
        issues.append(
            "issue.subject %r outside stable vocabulary %s"
            % (subject, ", ".join(SUBJECT_VOCABULARY))
        )
    fix_hint = issue.get("fix_hint")
    if fix_hint is None:
        fix_hint = ""
    elif not _is_str(fix_hint):
        issues.append("issue.fix_hint must be a string if present")

    evidence = issue.get("evidence")
    if evidence is None or evidence == {}:
        evidence = None
    else:
        if not isinstance(evidence, dict):
            issues.append("issue.evidence must be a dict if present")
        else:
            try:
                encoded = canonical_json(evidence)
            except ValueError:
                issues.append("issue.evidence must be finite JSON data")
            else:
                if len(encoded.encode("utf-8")) > EVIDENCE_MAX_CANONICAL_BYTES:
                    issues.append(
                        "issue.evidence exceeds %d canonical bytes"
                        % EVIDENCE_MAX_CANONICAL_BYTES
                    )

    if issues:
        raise PortabilityContractError(issues)

    out = {
        "code": code,
        "severity": sev,
        "message": msg,
        "subject": subject,
        "fix_hint": fix_hint,
    }
    if evidence is not None:
        out["evidence"] = evidence
    return out


def sort_issues(issues) -> list:
    """Deterministic issue order: severity desc, then code, then subject."""
    def key(issue):
        rank = _SEVERITY_RANK.get(issue.get("severity"), 0)
        return (-rank, str(issue.get("code", "")), str(issue.get("subject", "")))

    return sorted(issues, key=key)


# ── Report contract ───────────────────────────────────────────────────────


def make_target_result(
    *,
    risk_level: str,
    issue_codes=None,
    advice=None,
) -> dict:
    """Build one canonical per-target result (pure)."""
    codes = list(issue_codes or [])
    hints = list(advice or [])
    issues = []
    level = None
    try:
        level = normalize_risk_level(risk_level)
    except PortabilityContractError as exc:
        issues.extend(exc.issues)
    for code in codes:
        if not (_nonempty_str(code) and _ISSUE_CODE_RE.fullmatch(code)):
            issues.append("target issue code must be a non-empty snake_case string: %r" % (code,))
    for hint in hints:
        if not _nonempty_str(hint):
            issues.append("target advice entries must be non-empty strings")
    if issues:
        raise PortabilityContractError(issues)
    return {"risk_level": level, "issue_codes": codes, "advice": hints}


def report_validation_issues(report) -> list:
    """Collect every contract violation of a summary report; never raises."""
    issues = []
    if not isinstance(report, dict):
        return ["report must be a dict"]

    for field in REPORT_REQUIRED_FIELDS:
        if field not in report:
            issues.append("missing required report field: %s" % field)
    if not isinstance(report, dict):
        return issues

    vid = report.get("version_id")
    if not _nonempty_str(vid):
        issues.append("version_id must be a non-empty string")
    gh = report.get("graph_hash")
    if not is_sha256_hex(gh):
        issues.append("graph_hash must be a 64-character lowercase hex sha256")
    try:
        normalize_risk_level(report.get("risk_level"))
    except PortabilityContractError as exc:
        issues.extend(exc.issues)
    if report.get("rule_version") != PORTABILITY_RULE_VERSION:
        issues.append(
            "rule_version must be %r (got %r)" % (PORTABILITY_RULE_VERSION, report.get("rule_version"))
        )

    count = report.get("issue_count")
    if not _is_count(count):
        issues.append("issue_count must be a non-negative int")

    counts = report.get("counts")
    if not isinstance(counts, dict):
        issues.append("counts must be a dict keyed by severity")
    else:
        for key in COUNT_KEYS:
            if key not in counts:
                issues.append("counts missing severity key: %s" % key)
            elif not _is_count(counts[key]):
                issues.append("counts.%s must be a non-negative int" % key)
        extra = set(counts) - set(COUNT_KEYS)
        if extra:
            issues.append("counts has unknown keys: %s" % ", ".join(sorted(extra)))

    issues_list = report.get("issues")
    seen_codes: set = set()
    if not isinstance(issues_list, list):
        issues.append("issues must be a list")
    else:
        for idx, issue in enumerate(issues_list):
            try:
                normalized = normalize_issue(issue)
            except PortabilityContractError as exc:
                issues.append("issues[%d]: %s" % (idx, "; ".join(exc.issues)))
                continue
            if isinstance(issue, dict) and issue.get("code"):
                if issue["code"] in seen_codes:
                    issues.append("duplicate issue code: %s" % issue["code"])
                seen_codes.add(issue["code"])
        if isinstance(count, int) and not isinstance(count, bool):
            if count != len(issues_list):
                issues.append("issue_count must equal len(issues)")
            tally = {key: 0 for key in COUNT_KEYS}
            for issue in issues_list:
                sev = issue.get("severity") if isinstance(issue, dict) else None
                if sev in tally:
                    tally[sev] += 1
            if isinstance(counts, dict):
                for key in COUNT_KEYS:
                    if _is_count(counts.get(key)) and counts[key] != tally[key]:
                        issues.append(
                            "counts.%s must equal the number of %s-severity issues (%d)"
                            % (key, key, tally[key])
                        )

    signals = report.get("signals")
    if signals is not None:
        try:
            normalize_signals(signals)
        except PortabilityContractError as exc:
            issues.extend(exc.issues)

    targets = report.get("targets")
    if not isinstance(targets, dict):
        issues.append("targets must be a dict keyed by target id")
    else:
        missing = [t for t in TARGET_IDS if t not in targets]
        if missing:
            issues.append("targets missing keys: %s" % ", ".join(missing))
        extra = sorted(set(targets) - set(TARGET_IDS))
        if extra:
            issues.append("targets has unknown keys: %s" % ", ".join(extra))
        for tid in TARGET_IDS:
            result = targets.get(tid)
            if not isinstance(result, dict):
                continue
            for field in TARGET_RESULT_REQUIRED_FIELDS:
                if field not in result:
                    issues.append("targets.%s missing field: %s" % (tid, field))
            try:
                normalize_risk_level(result.get("risk_level"))
            except PortabilityContractError as exc:
                issues.append("targets.%s: %s" % (tid, "; ".join(exc.issues)))
            codes = result.get("issue_codes")
            if not isinstance(codes, list):
                issues.append("targets.%s.issue_codes must be a list" % tid)
            else:
                for code in codes:
                    if isinstance(issues_list, list) and seen_codes and code not in seen_codes:
                        issues.append(
                            "targets.%s references unknown issue code: %s" % (tid, code)
                        )
            advice = result.get("advice")
            if not isinstance(advice, list) or any(not _nonempty_str(a) for a in advice):
                issues.append("targets.%s.advice must be a list of non-empty strings" % tid)

    env = report.get("environment")
    if not isinstance(env, dict):
        issues.append("environment must be a dict (distinct reproducibility section)")
    else:
        try:
            normalize_risk_level(env.get("risk_level"))
        except PortabilityContractError as exc:
            issues.append("environment.risk_level: %s" % "; ".join(exc.issues))
        if not isinstance(env.get("issues"), list):
            issues.append("environment.issues must be a list")
        if env.get("source") != ENVIRONMENT_SOURCE_CURRENT_STUDIO:
            issues.append(
                "environment.source must be %r" % ENVIRONMENT_SOURCE_CURRENT_STUDIO
            )

    stale = report.get("stale")
    if not _is_bool(stale):
        issues.append("stale must be a bool")

    invalidation = report.get("invalidation")
    if invalidation is not None:
        issues.extend(invalidation_stamp_issues(invalidation))

    if not _nonempty_str(report.get("analyzed_at")):
        issues.append("analyzed_at must be a non-empty ISO timestamp string")

    return issues


def validate_report(report) -> None:
    """Raise PortabilityContractError carrying ALL report violations."""
    issues = report_validation_issues(report)
    if issues:
        raise PortabilityContractError(issues)


# ── Invalidation stamps ───────────────────────────────────────────────────


def build_invalidation_stamp(
    *,
    workflow_version_id=None,
    graph_hash=None,
    dependency_metadata_hash=None,
    model_library_generation=None,
    custom_node_registry_generation=None,
    rule_version=PORTABILITY_RULE_VERSION,
    manifest_version=None,
    comfyui_version=None,
) -> dict:
    """Build a full stamp; fields unavailable today stay None (never guessed)."""
    return {
        "workflow_version_id": workflow_version_id,
        "graph_hash": graph_hash,
        "dependency_metadata_hash": dependency_metadata_hash,
        "model_library_generation": model_library_generation,
        "custom_node_registry_generation": custom_node_registry_generation,
        "rule_version": rule_version,
        "manifest_version": manifest_version,
        "comfyui_version": comfyui_version,
    }


def invalidation_stamp_issues(stamp) -> list:
    issues = []
    if not isinstance(stamp, dict):
        return ["invalidation must be a dict"]
    for field in INVALIDATION_FIELDS:
        if field not in stamp:
            issues.append("invalidation missing field: %s" % field)
    extra = sorted(set(stamp) - set(INVALIDATION_FIELDS))
    if extra:
        issues.append("invalidation has unknown fields: %s" % ", ".join(extra))
    mv = stamp.get("manifest_version")
    if mv is not None and (isinstance(mv, bool) or not isinstance(mv, int)):
        issues.append("invalidation.manifest_version must be an int or null")
    return issues


def invalidation_mismatches(current, cached) -> list:
    """Field names that differ OR are unknowable (None on either side).

    Comparison semantics (frozen): a cached report may be reused only when
    EVERY field is concrete (non-null) on both sides and equal. Null is
    never treated as "unchanged forever"; an unknowable field forces a
    conservative recompute.
    """
    if not isinstance(current, dict) or not isinstance(cached, dict):
        return list(INVALIDATION_FIELDS)
    mismatched = []
    for field in INVALIDATION_FIELDS:
        cur = current.get(field)
        old = cached.get(field)
        if cur is None or old is None:
            mismatched.append(field)
        elif cur != old:
            mismatched.append(field)
    return mismatched


def invalidation_stamps_match(current, cached) -> bool:
    return not invalidation_mismatches(current, cached)


# ── Export filename helper ────────────────────────────────────────────────


def sanitize_filename_part(value, max_len: int = EXPORT_FILENAME_NAME_CAP) -> str:
    """Mirror web/history-v2-browser-download.js sanitizeFilenamePart()."""
    text = "" if value is None else str(value)
    sanitized = re.sub(r"[^a-zA-Z0-9._-]+", "_", text.strip())
    sanitized = sanitized.strip("_")
    return sanitized[:max_len]


def suggest_export_filename(name, version_number: int, graph_hash: str) -> str:
    """`<sanitized-name>-v<version_number>-<graph_hash[:8]>.workflow.json`."""
    issues = []
    if not isinstance(version_number, int) or isinstance(version_number, bool) or version_number < 1:
        issues.append("version_number must be an int >= 1")
    if not is_sha256_hex(graph_hash):
        issues.append("graph_hash must be a 64-character lowercase hex sha256")
    if issues:
        raise PortabilityContractError(issues)
    part = sanitize_filename_part(name) or "workflow"
    return "%s-v%d-%s%s" % (part, version_number, graph_hash[:8], EXPORT_FILENAME_SUFFIX)


__all__ = [
    "PORTABILITY_RULE_VERSION",
    "MANIFEST_AUTHORITY_MODULE",
    "MANIFEST_AUTHORITY_DOC",
    "SUPPORTED_MANIFEST_VERSIONS",
    "PortabilityRiskLevel",
    "RISK_LEVELS",
    "RISK_LEVEL_SEMANTICS",
    "SEVERITIES",
    "SEVERITY_HIGH",
    "SEVERITY_MEDIUM",
    "SEVERITY_LOW",
    "TARGET_IDS",
    "TARGET_LOCAL",
    "TARGET_MODAL",
    "TARGET_RUNPOD",
    "TARGET_RUNCOMFY",
    "TARGET_COMFY_CLOUD",
    "TARGET_BASETEN",
    "BANNED_TARGET_ALIASES",
    "SUBJECT_VOCABULARY",
    "SIGNAL_NAMES",
    "PROVENANCE_QUALITY_VALUES",
    "FOUNDATIONAL_ISSUE_CODES",
    "ENVIRONMENT_ISSUE_CODES",
    "ENVIRONMENT_SOURCE_CURRENT_STUDIO",
    "PORTABILITY_CONCEPTS",
    "CONCEPT_MANIFEST_READINESS",
    "CONCEPT_DEPENDENCY_AVAILABILITY",
    "CONCEPT_WORKFLOW_PORTABILITY_RISK",
    "CONCEPT_TARGET_READINESS",
    "CONCEPT_ENVIRONMENT_REPRODUCIBILITY",
    "REPORT_REQUIRED_FIELDS",
    "TARGET_RESULT_REQUIRED_FIELDS",
    "COUNT_KEYS",
    "INVALIDATION_FIELDS",
    "CHECKLIST_FIELDS",
    "EXPORT_ENDPOINT",
            "EXPORT_FILENAME_SUFFIX",
    "IMPORT_MANIFEST_ENDPOINT",
    "IMPORT_QUERY_DRY_RUN",
    "IMPORT_DEFAULT_DRY_RUN",
                    "IMPORT_PREVIEW_STATUS",
    "IMPORT_SUGGESTED_NAME_SUFFIX",
    "MAX_IMPORT_BODY_BYTES",
    "MAX_JSON_DEPTH",
    "MAX_JSON_ELEMENTS",
    "EVIDENCE_MAX_CANONICAL_BYTES",
    "SECURITY_RULES",
    "POLICY_SUBGRAPHS",
    "POLICY_ABSOLUTE_PATHS",
    "POLICY_ENVIRONMENT_ISOLATION",
    "ISSUE_FIELDS",
    "PortabilityContractError",
    "canonical_json",
    "canonical_bytes",
    "sha256_of_canonical",
    "is_sha256_hex",
    "normalize_risk_level",
    "normalize_severity",
    "normalize_target_id",
    "normalize_signals",
    "build_issue",
    "normalize_issue",
    "sort_issues",
    "make_target_result",
    "report_validation_issues",
    "validate_report",
    "build_invalidation_stamp",
    "invalidation_stamp_issues",
    "invalidation_mismatches",
    "invalidation_stamps_match",
    "sanitize_filename_part",
    "suggest_export_filename",
]
