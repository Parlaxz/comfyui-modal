"""Pure per-target readiness rule adapters (Phase G7).

Answers exactly one question: given PREPARED WorkflowVersion portability
evidence, what is this workflow's readiness for ONE specific execution
target? Exactly six targets are supported, keyed by the frozen G5 target
vocabulary::

    local · modal · runpod · runcomfy · comfy_cloud · baseten

This module OWNS ONLY per-target portability/readiness policy. It performs
NO I/O, NO network access, NO provider SDK calls, NO filesystem access, NO
credential handling, NO environment mutation, and NO route registration.
It imports only ``portability_contract`` (stdlib-only) plus the standard
library and must stay that way.

Deliberately NOT answered here (other lanes own these):
  - source-environment reproducibility (G2/environment section),
  - global Workflow portability risk summary (risk-engine lane),
  - provider availability right now / pricing / GPU scheduling,
  - live deployment success.

G3 audited provider facts (``PHASE_G3_TARGET_ENVIRONMENT_PORTABILITY_MATRIX_
2026-08-23.md``) are the evidence baseline. Facts G3 marked UNKNOWN stay
UNKNOWN: when readiness depends on an unknown capability this adapter emits
``target_capability_unknown`` and uses the UNKNOWN risk level rather than
assuming support or failure.

Rule version is exactly the frozen G5 value
(``portability_contract.PORTABILITY_RULE_VERSION == "portability-rules-v1"``).
No separate target-rule version exists.

Authoritative lane document:
``PHASE_G7_TARGET_READINESS_RULES_2026-08-23.md``.
"""

from __future__ import annotations

import re

import portability_contract as pc

# Single frozen rule version (re-exported; no separate target-rule version).
PORTABILITY_RULE_VERSION = pc.PORTABILITY_RULE_VERSION

# ── Errors ────────────────────────────────────────────────────────────────


class TargetEvidenceError(ValueError):
    """Raised when a prepared-evidence payload fails validation."""


# ── Evidence vocabulary ───────────────────────────────────────────────────

INSTALL_INSTALLED = "installed"
INSTALL_MISSING = "missing"
INSTALL_UNKNOWN = "unknown"
INSTALL_STATUSES = (INSTALL_INSTALLED, INSTALL_MISSING, INSTALL_UNKNOWN)

# Prepared capability flags a dependency record may carry. These mirror the
# G5/G6 native-dependency evidence fields; target rules only INTERPRET them.
FLAG_PYTHON_INSTALL = "requires_python_install"
FLAG_SYSTEM_PACKAGES = "requires_system_packages"
FLAG_NATIVE_BUILD = "requires_native_build"
FLAG_CUDA_BUILD = "requires_cuda_build"

DEPENDENCY_FLAGS = (
    FLAG_PYTHON_INSTALL,
    FLAG_SYSTEM_PACKAGES,
    FLAG_NATIVE_BUILD,
    FLAG_CUDA_BUILD,
)

RUNCOMFY_NATIVE_SUPPORTED = "supported"
RUNCOMFY_NATIVE_UNSUPPORTED = "unsupported"
RUNCOMFY_NATIVE_UNKNOWN = "unknown"
RUNCOMFY_NATIVE_CAPABILITIES = (
    RUNCOMFY_NATIVE_SUPPORTED,
    RUNCOMFY_NATIVE_UNSUPPORTED,
    RUNCOMFY_NATIVE_UNKNOWN,
)

BASETEN_STORAGE_AVAILABLE = "available"
BASETEN_STORAGE_UNKNOWN = "unknown"
BASETEN_STORAGE_STATES = (BASETEN_STORAGE_AVAILABLE, BASETEN_STORAGE_UNKNOWN)

# Tri-state catalog/allowlist evidence supplied per required node or model.
# True = explicitly represented as supported/available on that target,
# False = explicitly unavailable, None/absent = unknown (never guessed).
SUPPORT_TRUE = True
SUPPORT_FALSE = False
SUPPORT_UNKNOWN = None

# Frontend release line that introduced subgraph definitions (G1/G4 audits;
# current source pin is 1.44.19). Used ONLY to interpret an explicitly
# supplied frontend_version string for local/modal impact.
SUBGRAPH_MIN_FRONTEND = (1, 44, 0)
_FRONTEND_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)")

_EVIDENCE_KEYS = (
    "global_issue_codes",
    "signals",
    "custom_nodes",
    "models",
    "absolute_paths",
    "requires_input_asset",
    "uses_subgraphs",
    "frontend_version",
    "manifest_ready",
    "frontend_support",
    "runcomfy_native_capability",
    "baseten_persistent_storage",
)

# ── Target-only issue codes minted by this module ─────────────────────────
# All codes are snake_case and unique across the global issue pool. Where a
# foundational code already covers a fact (e.g. ``local_path_reference``)
# targets REFERENCE the global object by code instead of minting a copy.

ISSUE_LOCAL_NATIVE_BUILD_BURDEN = "local_native_build_burden"
ISSUE_LOCAL_DEPENDENCY_MISSING = "local_dependency_missing"
ISSUE_LOCAL_PROVENANCE_UNRESOLVED = "local_dependency_provenance_unresolved"
ISSUE_LOCAL_PATH_INVALID_ON_SOURCE_HOST = "local_path_invalid_on_source_host"
ISSUE_LOCAL_MODEL_MISSING = "local_model_missing"

ISSUE_MODAL_REVISION_UNRESOLVED = "modal_dependency_revision_unresolved"
ISSUE_MODAL_MODEL_UNAVAILABLE = "modal_model_unavailable"

ISSUE_PRODUCT_INTERNAL_DEPENDENCY = "product_internal_dependency"
ISSUE_TARGET_ABSOLUTE_PATH_BLOCKER = "target_absolute_path_blocker"
ISSUE_DEPENDENCY_SOURCE_UNRESOLVED = "dependency_source_unresolved"

ISSUE_RUNPOD_IMAGE_SETUP_REQUIRED = "runpod_image_setup_required"
ISSUE_RUNPOD_NATIVE_BUILD_REQUIRED = "runpod_native_build_required"
ISSUE_RUNPOD_PRIVATE_MODEL_TOKEN_SETUP = "runpod_private_model_token_setup"
ISSUE_RUNPOD_MODEL_UNAVAILABLE = "runpod_model_unavailable"
ISSUE_RUNPOD_FRONTEND_SETUP_REQUIRED = "runpod_frontend_setup_required"

ISSUE_RUNCOMFY_AUTO_SETUP_REQUIRED = "runcomfy_auto_setup_required"
ISSUE_RUNCOMFY_NATIVE_BUILD_REQUIRED = "runcomfy_native_build_required"
ISSUE_RUNCOMFY_NATIVE_BLOCKED = "runcomfy_native_dependency_blocked"
ISSUE_RUNCOMFY_NATIVE_CAPABILITY_UNKNOWN = "runcomfy_native_capability_unknown"
ISSUE_RUNCOMFY_COMMIT_PINNING_UNKNOWN = "runcomfy_commit_pinning_unknown"
ISSUE_RUNCOMFY_SUBGRAPH_SUPPORT_UNKNOWN = "runcomfy_subgraph_support_unknown"
ISSUE_RUNCOMFY_TOKEN_ATTACH_REQUIRED = "runcomfy_token_attach_required"
ISSUE_RUNCOMFY_MODEL_UNAVAILABLE = "runcomfy_model_unavailable"

ISSUE_COMFY_CLOUD_NODE_OFF_CATALOG = "comfy_cloud_node_off_catalog"
ISSUE_COMFY_CLOUD_NODE_SUPPORT_UNKNOWN = "comfy_cloud_node_support_unknown"
ISSUE_COMFY_CLOUD_PYTHON_INSTALL_UNSUPPORTED = "comfy_cloud_python_install_unsupported"
ISSUE_COMFY_CLOUD_NATIVE_UNSUPPORTED = "comfy_cloud_native_dependency_unsupported"
ISSUE_COMFY_CLOUD_MODEL_OFF_CATALOG = "comfy_cloud_model_off_catalog"
ISSUE_COMFY_CLOUD_MODEL_CATALOG_UNKNOWN = "comfy_cloud_model_catalog_unknown"
ISSUE_COMFY_CLOUD_SUBGRAPH_SUPPORT_UNKNOWN = "comfy_cloud_subgraph_support_unknown"

ISSUE_BASETEN_DEPLOYMENT_EMBEDDING = "baseten_deployment_embedding_required"
ISSUE_BASETEN_NODE_BAKE_REQUIRED = "baseten_custom_node_bake_required"
ISSUE_BASETEN_CUDA_BUILD_REQUIRED = "baseten_cuda_build_required"
ISSUE_BASETEN_NATIVE_PACKAGES_REQUIRED = "baseten_native_packages_required"
ISSUE_BASETEN_PRIVATE_MODEL_SECRET_SETUP = "baseten_private_model_secret_setup"
ISSUE_BASETEN_MODEL_UNAVAILABLE = "baseten_model_unavailable"
ISSUE_BASETEN_STORAGE_CAPABILITY_UNKNOWN = "baseten_storage_capability_unknown"
ISSUE_BASETEN_FRONTEND_SETUP_REQUIRED = "baseten_frontend_setup_required"

TARGET_ONLY_ISSUE_CODES = (
    ISSUE_LOCAL_NATIVE_BUILD_BURDEN,
    ISSUE_LOCAL_DEPENDENCY_MISSING,
    ISSUE_LOCAL_PROVENANCE_UNRESOLVED,
    ISSUE_LOCAL_PATH_INVALID_ON_SOURCE_HOST,
    ISSUE_LOCAL_MODEL_MISSING,
    ISSUE_MODAL_REVISION_UNRESOLVED,
    ISSUE_MODAL_MODEL_UNAVAILABLE,
    ISSUE_PRODUCT_INTERNAL_DEPENDENCY,
    ISSUE_TARGET_ABSOLUTE_PATH_BLOCKER,
    ISSUE_DEPENDENCY_SOURCE_UNRESOLVED,
    ISSUE_RUNPOD_IMAGE_SETUP_REQUIRED,
    ISSUE_RUNPOD_NATIVE_BUILD_REQUIRED,
    ISSUE_RUNPOD_PRIVATE_MODEL_TOKEN_SETUP,
    ISSUE_RUNPOD_MODEL_UNAVAILABLE,
    ISSUE_RUNPOD_FRONTEND_SETUP_REQUIRED,
    ISSUE_RUNCOMFY_AUTO_SETUP_REQUIRED,
    ISSUE_RUNCOMFY_NATIVE_BUILD_REQUIRED,
    ISSUE_RUNCOMFY_NATIVE_BLOCKED,
    ISSUE_RUNCOMFY_NATIVE_CAPABILITY_UNKNOWN,
    ISSUE_RUNCOMFY_COMMIT_PINNING_UNKNOWN,
    ISSUE_RUNCOMFY_SUBGRAPH_SUPPORT_UNKNOWN,
    ISSUE_RUNCOMFY_TOKEN_ATTACH_REQUIRED,
    ISSUE_RUNCOMFY_MODEL_UNAVAILABLE,
    ISSUE_COMFY_CLOUD_NODE_OFF_CATALOG,
    ISSUE_COMFY_CLOUD_NODE_SUPPORT_UNKNOWN,
    ISSUE_COMFY_CLOUD_PYTHON_INSTALL_UNSUPPORTED,
    ISSUE_COMFY_CLOUD_NATIVE_UNSUPPORTED,
    ISSUE_COMFY_CLOUD_MODEL_OFF_CATALOG,
    ISSUE_COMFY_CLOUD_MODEL_CATALOG_UNKNOWN,
    ISSUE_COMFY_CLOUD_SUBGRAPH_SUPPORT_UNKNOWN,
    ISSUE_BASETEN_DEPLOYMENT_EMBEDDING,
    ISSUE_BASETEN_NODE_BAKE_REQUIRED,
    ISSUE_BASETEN_CUDA_BUILD_REQUIRED,
    ISSUE_BASETEN_NATIVE_PACKAGES_REQUIRED,
    ISSUE_BASETEN_PRIVATE_MODEL_SECRET_SETUP,
    ISSUE_BASETEN_MODEL_UNAVAILABLE,
    ISSUE_BASETEN_STORAGE_CAPABILITY_UNKNOWN,
    ISSUE_BASETEN_FRONTEND_SETUP_REQUIRED,
)

# Global (foundational) codes targets may reference when the caller confirms
# they already exist in the global issue pool. ``target_capability_unknown``
# and ``manifest_not_ready`` are minted once by G7 when absent so target
# results always remain explainable standalone.
REFERENCABLE_GLOBAL_CODES = (
    pc.ISSUE_LOCAL_PATH_REFERENCE,
    pc.ISSUE_MODEL_HASH_UNPINNED,
    pc.ISSUE_SUBGRAPH_FRONTEND_REQUIREMENT,
    pc.ISSUE_MANIFEST_NOT_READY,
    pc.ISSUE_DEPENDENCY_MISSING,
    pc.ISSUE_CUSTOM_NODE_UNPINNED,
    pc.ISSUE_UNRESOLVED_NODE_TYPE,
    pc.ISSUE_TARGET_CAPABILITY_UNKNOWN,
)

# ── Evidence normalization ────────────────────────────────────────────────

_CODE_RE = re.compile(r"[a-z0-9]+(_[a-z0-9]+)*")


def _require_bool(record, field, problems, default=False):
    value = record.get(field, default)
    if not isinstance(value, bool):
        problems.append("%s must be a bool" % field)
        return default
    return value


def _require_tri_state_map(record, field, problems):
    """Per-target tri-state map {target_id: True|False|None}."""
    raw = record.get(field) or {}
    if not isinstance(raw, dict):
        problems.append("%s must be a dict keyed by target id" % field)
        return {}
    out = {}
    for key, value in raw.items():
        try:
            tid = pc.normalize_target_id(key)
        except pc.PortabilityContractError:
            problems.append("%s has invalid target id: %r" % (field, key))
            continue
        if value is not None and not isinstance(value, bool):
            problems.append("%s[%s] must be true, false, or null" % (field, tid))
            continue
        out[tid] = value
    return out


def _normalize_custom_node(record, problems):
    if not isinstance(record, dict):
        problems.append("custom node entries must be dicts")
        return None
    name = record.get("name")
    if not isinstance(name, str) or not name.strip():
        problems.append("custom node name must be a non-empty string")
        return None
    provenance = record.get("provenance")
    if provenance not in pc.PROVENANCE_QUALITY_VALUES:
        problems.append(
            "custom node %r provenance must be one of %s"
            % (name, ", ".join(pc.PROVENANCE_QUALITY_VALUES))
        )
        return None
    install_status = record.get("install_status", INSTALL_INSTALLED)
    if install_status not in INSTALL_STATUSES:
        problems.append(
            "custom node %r install_status must be one of %s"
            % (name, ", ".join(INSTALL_STATUSES))
        )
        return None
    normalized = {
        "name": name.strip(),
        "provenance": provenance,
        "manager_restorable": _require_bool(record, "manager_restorable", problems),
        "product_internal": _require_bool(record, "product_internal", problems),
        "install_status": install_status,
    }
    for flag in DEPENDENCY_FLAGS:
        normalized[flag] = _require_bool(record, flag, problems)
    normalized["target_supported"] = _require_tri_state_map(
        record, "target_supported", problems
    )
    return normalized


def _normalize_model(record, problems):
    if not isinstance(record, dict):
        problems.append("model entries must be dicts")
        return None
    name = record.get("name")
    if not isinstance(name, str) or not name.strip():
        problems.append("model name must be a non-empty string")
        return None
    sha256 = record.get("sha256")
    if sha256 is not None and not pc.is_sha256_hex(sha256):
        problems.append("model %r sha256 must be null or 64-char lowercase hex" % name)
        return None
    present_locally = record.get("present_locally")
    if present_locally is not None and not isinstance(present_locally, bool):
        problems.append("model %r present_locally must be bool or null" % name)
        return None
    return {
        "name": name.strip(),
        "sha256": sha256,
        "private_or_gated": _require_bool(record, "private_or_gated", problems),
        "present_locally": present_locally,
        "target_catalog_available": _require_tri_state_map(
            record, "target_catalog_available", problems
        ),
    }


def build_target_evidence(
    *,
    global_issue_codes=None,
    signals=None,
    custom_nodes=None,
    models=None,
    absolute_paths=None,
    requires_input_asset=False,
    uses_subgraphs=False,
    frontend_version=None,
    manifest_ready=True,
    frontend_support=None,
    runcomfy_native_capability=RUNCOMFY_NATIVE_UNKNOWN,
    baseten_persistent_storage=BASETEN_STORAGE_UNKNOWN,
) -> dict:
    """Validate and normalize prepared portability evidence (pure).

    This is the explicit pure input object consumed by the six adapters.
    Nothing here touches machine state; callers supply facts discovered by
    earlier lanes (manifest analysis, dependency resolution, model library,
    provider-evidence updaters).
    """
    problems: list = []

    codes = []
    for code in list(global_issue_codes or []):
        if not isinstance(code, str) or _CODE_RE.fullmatch(code) is None:
            problems.append(
                "global_issue_codes entries must be snake_case strings: %r" % (code,)
            )
        else:
            codes.append(code)

    normalized_signals = {}
    if signals is not None:
        try:
            normalized_signals = pc.normalize_signals(signals)
        except pc.PortabilityContractError as exc:
            problems.extend(exc.issues)

    nodes = []
    for record in list(custom_nodes or []):
        node = _normalize_custom_node(record, problems)
        if node is not None:
            nodes.append(node)
    nodes.sort(key=lambda item: item["name"])

    model_records = []
    for record in list(models or []):
        model = _normalize_model(record, problems)
        if model is not None:
            model_records.append(model)
    model_records.sort(key=lambda item: item["name"])

    paths = []
    for record in list(absolute_paths or []):
        if not isinstance(record, dict):
            problems.append("absolute_paths entries must be dicts")
            continue
        path_value = record.get("path")
        if not isinstance(path_value, str) or not path_value.strip():
            problems.append("absolute_paths.path must be a non-empty string")
            continue
        paths.append(
            {
                "path": path_value,
                "source_host_consistent": _require_bool(
                    record, "source_host_consistent", problems, default=True
                ),
                "product_materialized": _require_bool(
                    record, "product_materialized", problems
                ),
            }
        )
    paths.sort(key=lambda item: item["path"])

    if not isinstance(requires_input_asset, bool):
        problems.append("requires_input_asset must be a bool")
    if not isinstance(uses_subgraphs, bool):
        problems.append("uses_subgraphs must be a bool")
    if frontend_version is not None and not isinstance(frontend_version, str):
        problems.append("frontend_version must be a string or null")
    if not isinstance(manifest_ready, bool):
        problems.append("manifest_ready must be a bool")

    support_confirmed = {}
    for key, value in (frontend_support or {}).items():
        try:
            tid = pc.normalize_target_id(key)
        except pc.PortabilityContractError:
            problems.append("frontend_support has invalid target id: %r" % (key,))
            continue
        if not isinstance(value, bool):
            problems.append("frontend_support[%s] must be a bool" % tid)
            continue
        support_confirmed[tid] = value

    if runcomfy_native_capability not in RUNCOMFY_NATIVE_CAPABILITIES:
        problems.append(
            "runcomfy_native_capability must be one of %s"
            % ", ".join(RUNCOMFY_NATIVE_CAPABILITIES)
        )
    if baseten_persistent_storage not in BASETEN_STORAGE_STATES:
        problems.append(
            "baseten_persistent_storage must be one of %s"
            % ", ".join(BASETEN_STORAGE_STATES)
        )

    if problems:
        raise TargetEvidenceError("; ".join(sorted(set(problems))))

    return {
        "global_issue_codes": sorted(set(codes)),
        "signals": normalized_signals,
        "custom_nodes": nodes,
        "models": model_records,
        "absolute_paths": paths,
        "requires_input_asset": requires_input_asset,
        "uses_subgraphs": uses_subgraphs,
        "frontend_version": frontend_version,
        "manifest_ready": manifest_ready,
        "frontend_support": support_confirmed,
        "runcomfy_native_capability": runcomfy_native_capability,
        "baseten_persistent_storage": baseten_persistent_storage,
    }


# ── Internal rule machinery ───────────────────────────────────────────────

_SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3}

_MESSAGE_NAME_CAP = 5
_EVIDENCE_NAME_CAP = 8


class _Accumulator:
    """Collects one target's issues/advice with deterministic dedupe.

    Issues are aggregated PER CODE: repeated triggers merge their subject
    names into one bounded issue object so logically identical findings are
    never duplicated. Rendering happens once, at finalize time.
    """

    def __init__(self, target_id, global_codes):
        self.target_id = target_id
        self.global_codes = frozenset(global_codes)
        self.issue_codes = []            # ordered, deduped
        self._issue_code_seen = set()
        self.advice = []                 # ordered, deduped
        self._advice_seen = set()
        self.max_severity = None         # highest severity among minted issues
        self.unknown_capability = False
        self._drafts = {}                # code -> draft dict

    # -- issue codes -------------------------------------------------------

    def reference(self, code):
        """Reference a global issue by code (no new object minted)."""
        if code in self.global_codes:
            self._add_code(code)

    def capability_unknown(self):
        """Record a decision-critical UNKNOWN capability."""
        self.unknown_capability = True
        if pc.ISSUE_TARGET_CAPABILITY_UNKNOWN in self.global_codes:
            self._add_code(pc.ISSUE_TARGET_CAPABILITY_UNKNOWN)
        else:
            self.mint(
                pc.ISSUE_TARGET_CAPABILITY_UNKNOWN,
                "medium",
                pc.SUBJECT_TARGET,
                "A provider capability this readiness decision depends on is unverified.",
                fix_hint="Verify the provider capability before relying on this target.",
            )

    def mint(self, code, severity, subject, message_template, fix_hint="", names=None):
        """Mint/merge one target-only issue (aggregated per code)."""
        draft = self._drafts.get(code)
        if draft is None:
            draft = {
                "severity": severity,
                "subject": subject,
                "message_template": message_template,
                "fix_hint": fix_hint,
                "names": [],
            }
            self._drafts[code] = draft
            rank = _SEVERITY_RANK[severity]
            if self.max_severity is None or rank > _SEVERITY_RANK[self.max_severity]:
                self.max_severity = severity
        if names:
            for name in names:
                if name not in draft["names"]:
                    draft["names"].append(name)
        self._add_code(code)

    def finalize_issues(self):
        """Render aggregated drafts into canonical issue objects."""
        rendered = []
        for code in sorted(self._drafts):
            draft = self._drafts[code]
            evidence = None
            template_vars = {"target": self.target_id}
            if draft["names"]:
                unique_names = sorted(draft["names"])
                evidence = {
                    "count": len(unique_names),
                    "names": unique_names[:_EVIDENCE_NAME_CAP],
                }
                shown = unique_names[:_MESSAGE_NAME_CAP]
                rendered_names = ", ".join(shown)
                if len(unique_names) > _MESSAGE_NAME_CAP:
                    rendered_names += "; and %d more" % (len(unique_names) - _MESSAGE_NAME_CAP)
                template_vars["names"] = rendered_names
                template_vars["count"] = len(unique_names)
            rendered.append(
                pc.build_issue(
                    code=code,
                    severity=draft["severity"],
                    message=draft["message_template"].format(**template_vars),
                    subject=draft["subject"],
                    fix_hint=draft["fix_hint"],
                    evidence=evidence,
                )
            )
        return rendered

    # -- advice --------------------------------------------------------------

    def advise(self, *lines):
        for line in lines:
            if line and line not in self._advice_seen:
                self._advice_seen.add(line)
                self.advice.append(line)

    # -- result ----------------------------------------------------------------

    def _add_code(self, code):
        if code not in self._issue_code_seen:
            self._issue_code_seen.add(code)
            self.issue_codes.append(code)

    def result(self):
        """Risk precedence: known HIGH > UNKNOWN > MEDIUM > LOW.

        A known HIGH blocker always wins so the actionable finding is never
        masked; uncertainty stays visible through ``target_capability_unknown``
        in issue_codes. An UNKNOWN with no known blocker reports UNKNOWN
        (fail-honest: neither support nor failure is assumed).
        """
        if self.max_severity == "high":
            level = pc.PortabilityRiskLevel.HIGH
        elif self.unknown_capability:
            level = pc.PortabilityRiskLevel.UNKNOWN
        elif self.max_severity == "medium":
            level = pc.PortabilityRiskLevel.MEDIUM
        else:
            level = pc.PortabilityRiskLevel.LOW
        return pc.make_target_result(
            risk_level=level,
            issue_codes=sorted(self.issue_codes),
            advice=list(self.advice),
        )


def _is_native_like(node):
    return any(
        node[flag] for flag in (FLAG_SYSTEM_PACKAGES, FLAG_NATIVE_BUILD, FLAG_CUDA_BUILD)
    )


def _is_cuda_like(node):
    return bool(node[FLAG_CUDA_BUILD])


def _frontend_supports_subgraphs(version_string):
    """True/False/None from an explicit version string; None = unverifiable."""
    if not isinstance(version_string, str):
        return None
    match = _FRONTEND_VERSION_RE.match(version_string.strip())
    if match is None:
        return None
    parsed = tuple(int(part) for part in match.groups())
    return parsed >= SUBGRAPH_MIN_FRONTEND


def _catalog(model, tid):
    return model["target_catalog_available"].get(tid)


def _supported(node, tid):
    return node["target_supported"].get(tid)


# ── Shared findings (manifest / absolute paths / subgraphs) ───────────────


def _apply_shared_findings(acc, evidence, tid):
    if not evidence["manifest_ready"]:
        acc.reference(pc.ISSUE_MANIFEST_NOT_READY)
        acc.mint(
            pc.ISSUE_MANIFEST_NOT_READY,
            "high",
            pc.SUBJECT_MANIFEST,
            "Manifest structural readiness failed; every target inherits the blocker.",
            fix_hint="Fix manifest validation findings before targeting any environment.",
        )

    paths = list(evidence["absolute_paths"])
    if not paths and evidence["signals"].get(pc.SIGNAL_HAS_ABSOLUTE_PATH):
        # Signal asserts host-bound references without prepared records;
        # treat as one opaque source-host-consistent reference.
        paths = [
            {
                "path": "<unrecorded>",
                "source_host_consistent": True,
                "product_materialized": False,
            }
        ]
    if paths:
        acc.reference(pc.ISSUE_LOCAL_PATH_REFERENCE)
        broken = [p["path"] for p in paths if not p["source_host_consistent"]]
        if broken:
            acc.mint(
                ISSUE_LOCAL_PATH_INVALID_ON_SOURCE_HOST,
                "high",
                pc.SUBJECT_PATHS,
                "Referenced absolute paths do not exist on the source host: {names}.",
                fix_hint="Repair or remove stale absolute paths before export.",
                names=broken,
            )
        if tid != pc.TARGET_LOCAL:
            blocking = [
                p["path"]
                for p in paths
                if not (tid == pc.TARGET_MODAL and p["product_materialized"])
            ]
            if blocking:
                acc.mint(
                    ISSUE_TARGET_ABSOLUTE_PATH_BLOCKER,
                    "high",
                    pc.SUBJECT_PATHS,
                    "Workflow JSON requires host-bound absolute paths that remote "
                    "targets do not share ({count} reference(s)).",
                    fix_hint=(
                        "Replace absolute paths with portable filenames transported as inputs."
                    ),
                    names=blocking,
                )

    if evidence["uses_subgraphs"]:
        acc.reference(pc.ISSUE_SUBGRAPH_FRONTEND_REQUIREMENT)
        confirmed = evidence["frontend_support"].get(tid)
        if confirmed is None:
            if tid in (pc.TARGET_LOCAL, pc.TARGET_MODAL):
                confirmed = _frontend_supports_subgraphs(evidence["frontend_version"])
                if confirmed is None:
                    # Source environment ships a current pinned frontend (1.44.19).
                    confirmed = True
            else:
                # Remote targets: frontend support is unverified by prepared
                # evidence (user-baked image or platform-managed frontend).
                confirmed = False
        if confirmed is False:
            if tid in (pc.TARGET_RUNPOD, pc.TARGET_BASETEN):
                code = (
                    ISSUE_RUNPOD_FRONTEND_SETUP_REQUIRED
                    if tid == pc.TARGET_RUNPOD
                    else ISSUE_BASETEN_FRONTEND_SETUP_REQUIRED
                )
                acc.mint(
                    code,
                    "medium",
                    pc.SUBJECT_FRONTEND,
                    "The {target} image must ship a ComfyUI frontend that supports subgraphs.",
                    fix_hint="Bake a subgraph-capable ComfyUI frontend into the image.",
                )
            elif tid in (pc.TARGET_RUNCOMFY, pc.TARGET_COMFY_CLOUD):
                code = (
                    ISSUE_RUNCOMFY_SUBGRAPH_SUPPORT_UNKNOWN
                    if tid == pc.TARGET_RUNCOMFY
                    else ISSUE_COMFY_CLOUD_SUBGRAPH_SUPPORT_UNKNOWN
                )
                acc.mint(
                    code,
                    "medium",
                    pc.SUBJECT_FRONTEND,
                    "{target} frontend/subgraph support for this graph is unverified.",
                    fix_hint="Verify subgraph execution before relying on it.",
                )
                acc.capability_unknown()
            else:
                acc.reference(pc.ISSUE_SUBGRAPH_FRONTEND_REQUIREMENT)
                acc.mint(
                    pc.ISSUE_SUBGRAPH_FRONTEND_REQUIREMENT,
                    "medium",
                    pc.SUBJECT_FRONTEND,
                    "The source frontend does not satisfy the graph's subgraph requirement.",
                    fix_hint="Upgrade the ComfyUI frontend to a subgraph-capable release.",
                )


# ── Custom-node dependency rules ──────────────────────────────────────────


def _apply_custom_node(acc, evidence, tid, node):
    name = node["name"]

    # Explainability only: reference global findings when the caller
    # confirmed they exist; never mint duplicates, never move risk.
    if node["provenance"] in (pc.PROVENANCE_DECLARED, pc.PROVENANCE_INFERRED):
        acc.reference(pc.ISSUE_CUSTOM_NODE_UNPINNED)

    if node["product_internal"]:
        if tid in (pc.TARGET_LOCAL, pc.TARGET_MODAL):
            return  # product/plugin image supplies these classes
        acc.mint(
            ISSUE_PRODUCT_INTERNAL_DEPENDENCY,
            "high",
            pc.SUBJECT_CUSTOM_NODES,
            "Required classes belong to the Studio product plugin and are not "
            "publicly installable outside the product environment: {names}.",
            fix_hint=(
                "Run on Local or Modal, or replace product-internal classes "
                "with public equivalents."
            ),
            names=[name],
        )
        return

    if node["provenance"] == pc.PROVENANCE_UNRESOLVED:
        if tid == pc.TARGET_LOCAL:
            acc.mint(
                ISSUE_LOCAL_PROVENANCE_UNRESOLVED,
                "medium",
                pc.SUBJECT_CUSTOM_NODES,
                "Local provenance could not be established for: {names}.",
                fix_hint="Identify the source repository and revision locally.",
                names=[name],
            )
        elif tid == pc.TARGET_MODAL:
            acc.mint(
                ISSUE_MODAL_REVISION_UNRESOLVED,
                "medium",
                pc.SUBJECT_CUSTOM_NODES,
                "Modal deploy bake cannot pin a revision for: {names}.",
                fix_hint="Resolve repo URL and commit before redeploying the Modal app.",
                names=[name],
            )
        else:
            acc.mint(
                ISSUE_DEPENDENCY_SOURCE_UNRESOLVED,
                "high",
                pc.SUBJECT_CUSTOM_NODES,
                "Remote provisioning cannot reproduce an unpinned dependency "
                "source: {names}.",
                fix_hint=(
                    "Provide a pinned source (repo URL + commit) before "
                    "provisioning this dependency."
                ),
                names=[name],
            )
        return

    if tid == pc.TARGET_LOCAL:
        if node["install_status"] == INSTALL_MISSING:
            acc.mint(
                ISSUE_LOCAL_DEPENDENCY_MISSING,
                "high",
                pc.SUBJECT_CUSTOM_NODES,
                "Required custom nodes are not installed locally: {names}.",
                fix_hint="Install the missing custom nodes locally.",
                names=[name],
            )
        if _is_native_like(node):
            acc.mint(
                ISSUE_LOCAL_NATIVE_BUILD_BURDEN,
                "medium",
                pc.SUBJECT_ENVIRONMENT,
                "Local execution requires building native components for: {names}.",
                fix_hint="Install local build tools or use prebuilt wheels.",
                names=[name],
            )
        return

    if tid == pc.TARGET_MODAL:
        # Broad dependency control: image layers solve python/native installs.
        return

    if tid == pc.TARGET_RUNPOD:
        if _is_native_like(node):
            acc.mint(
                ISSUE_RUNPOD_NATIVE_BUILD_REQUIRED,
                "high",
                pc.SUBJECT_CUSTOM_NODES,
                "RunPod image build must compile/install native components for: {names}.",
                fix_hint="Add native packages and build steps to the worker Dockerfile.",
                names=[name],
            )
        else:
            acc.mint(
                ISSUE_RUNPOD_IMAGE_SETUP_REQUIRED,
                "medium",
                pc.SUBJECT_CUSTOM_NODES,
                "RunPod requires these custom nodes to be baked into the worker image: {names}.",
                fix_hint="Build the required custom nodes into the RunPod worker image.",
                names=[name],
            )
        return

    if tid == pc.TARGET_RUNCOMFY:
        if _is_native_like(node):
            capability = evidence["runcomfy_native_capability"]
            if capability == RUNCOMFY_NATIVE_SUPPORTED:
                acc.mint(
                    ISSUE_RUNCOMFY_NATIVE_BUILD_REQUIRED,
                    "high",
                    pc.SUBJECT_CUSTOM_NODES,
                    "RunComfy session must provision native components for: {names}.",
                    fix_hint="Provision native packages through RunComfy session setup.",
                    names=[name],
                )
            elif capability == RUNCOMFY_NATIVE_UNSUPPORTED:
                acc.mint(
                    ISSUE_RUNCOMFY_NATIVE_BLOCKED,
                    "high",
                    pc.SUBJECT_CUSTOM_NODES,
                    "Supplied evidence marks RunComfy unable to provision native "
                    "components for: {names}.",
                    fix_hint=(
                        "Choose a target with custom-environment support for "
                        "this dependency."
                    ),
                    names=[name],
                )
            else:
                acc.mint(
                    ISSUE_RUNCOMFY_NATIVE_CAPABILITY_UNKNOWN,
                    "medium",
                    pc.SUBJECT_CUSTOM_NODES,
                    "RunComfy native package support for this dependency is "
                    "unverified: {names}.",
                    fix_hint=(
                        "Verify RunComfy native/system package support before "
                        "committing to it."
                    ),
                    names=[name],
                )
                acc.capability_unknown()
        elif not (
            node["manager_restorable"]
            and node["provenance"] in (pc.PROVENANCE_EXACT, pc.PROVENANCE_DECLARED)
        ):
            acc.mint(
                ISSUE_RUNCOMFY_AUTO_SETUP_REQUIRED,
                "medium",
                pc.SUBJECT_CUSTOM_NODES,
                "RunComfy auto-setup must install: {names}.",
                fix_hint="Let RunComfy auto-setup install the missing nodes, then snapshot.",
                names=[name],
            )
        if node["provenance"] == pc.PROVENANCE_EXACT:
            acc.mint(
                ISSUE_RUNCOMFY_COMMIT_PINNING_UNKNOWN,
                "low",
                pc.SUBJECT_CUSTOM_NODES,
                "RunComfy explicit commit-level pinning is unverified; exact "
                "revisions may not be restorable: {names}.",
                fix_hint="Snapshot after auto-setup; verify the restored revision.",
                names=[name],
            )
        return

    if tid == pc.TARGET_COMFY_CLOUD:
        support = _supported(node, tid)
        if support is False:
            acc.mint(
                ISSUE_COMFY_CLOUD_NODE_OFF_CATALOG,
                "high",
                pc.SUBJECT_CUSTOM_NODES,
                "Comfy Cloud cannot execute nodes outside its supported catalog: {names}.",
                fix_hint=(
                    "Comfy Cloud cannot install this required custom node; "
                    "replace it or choose a target with custom environments."
                ),
                names=[name],
            )
        elif support is None:
            acc.mint(
                ISSUE_COMFY_CLOUD_NODE_SUPPORT_UNKNOWN,
                "medium",
                pc.SUBJECT_CUSTOM_NODES,
                "Comfy Cloud catalog support for these required nodes is not "
                "established by supplied evidence: {names}.",
                fix_hint=(
                    "Confirm the node appears in Comfy Cloud's supported list "
                    "before exporting there."
                ),
                names=[name],
            )
            acc.capability_unknown()
        # Arbitrary pip is impossible on Comfy Cloud; this is a HARD blocker
        # only when the node is known off-catalog. With unknown catalog
        # membership the uncertainty codes above carry the decision instead
        # (never assume failure).
        if node[FLAG_PYTHON_INSTALL] and support is False:
            acc.mint(
                ISSUE_COMFY_CLOUD_PYTHON_INSTALL_UNSUPPORTED,
                "high",
                pc.SUBJECT_CUSTOM_NODES,
                "Comfy Cloud cannot install arbitrary Python packages required by: {names}.",
                fix_hint=(
                    "Comfy Cloud cannot install arbitrary Python packages for "
                    "this workflow."
                ),
                names=[name],
            )
        if _is_native_like(node):
            acc.mint(
                ISSUE_COMFY_CLOUD_NATIVE_UNSUPPORTED,
                "high",
                pc.SUBJECT_CUSTOM_NODES,
                "Comfy Cloud cannot install this required native custom-node "
                "dependency: {names}.",
                fix_hint=(
                    "Comfy Cloud cannot satisfy native/system installs; choose "
                    "a custom-environment target."
                ),
                names=[name],
            )
        return

    if tid == pc.TARGET_BASETEN:
        acc.mint(
            ISSUE_BASETEN_NODE_BAKE_REQUIRED,
            "medium",
            pc.SUBJECT_CUSTOM_NODES,
            "Baseten build_commands must clone/install: {names}.",
            fix_hint="Clone and install required custom nodes in Truss build_commands.",
            names=[name],
        )
        if _is_cuda_like(node):
            acc.mint(
                ISSUE_BASETEN_CUDA_BUILD_REQUIRED,
                "high",
                pc.SUBJECT_ENVIRONMENT,
                "Baseten image build must compile CUDA components for: {names}.",
                fix_hint="Provide CUDA build support in the Truss image for native components.",
                names=[name],
            )
        elif _is_native_like(node):
            acc.mint(
                ISSUE_BASETEN_NATIVE_PACKAGES_REQUIRED,
                "medium",
                pc.SUBJECT_ENVIRONMENT,
                "Baseten system_packages/build_commands must provide native "
                "components for: {names}.",
                fix_hint="Declare system packages in the Truss config for native components.",
                names=[name],
            )
        return


# ── Model rules ───────────────────────────────────────────────────────────


def _apply_models(acc, evidence, tid):
    models = evidence["models"]
    if not models:
        return
    private = [m["name"] for m in models if m["private_or_gated"]]

    # Missing SHA is a reproducibility/setup warning, never an automatic
    # target failure: reference the global finding when supplied.
    if any(m["sha256"] is None for m in models):
        acc.reference(pc.ISSUE_MODEL_HASH_UNPINNED)

    if tid == pc.TARGET_LOCAL:
        missing_local = [m["name"] for m in models if m["present_locally"] is False]
        if missing_local:
            acc.mint(
                ISSUE_LOCAL_MODEL_MISSING,
                "high",
                pc.SUBJECT_MODELS,
                "Required models are missing from the local library: {names}.",
                fix_hint="Place the required models into their ComfyUI model buckets.",
                names=missing_local,
            )
        return

    if tid == pc.TARGET_MODAL:
        unavailable = [m["name"] for m in models if _catalog(m, tid) is False]
        if unavailable:
            acc.mint(
                ISSUE_MODAL_MODEL_UNAVAILABLE,
                "high",
                pc.SUBJECT_MODELS,
                "Supplied evidence marks these models unavailable on Modal volumes: {names}.",
                fix_hint="Mount or upload the required models to Modal volumes.",
                names=unavailable,
            )
        return

    if tid == pc.TARGET_RUNPOD:
        if private:
            acc.mint(
                ISSUE_RUNPOD_PRIVATE_MODEL_TOKEN_SETUP,
                "medium",
                pc.SUBJECT_MODELS,
                "Private/gated models need token plumbing in the RunPod endpoint "
                "environment: {names}.",
                fix_hint="Configure endpoint tokens/secrets for private/gated model downloads.",
                names=private,
            )
        unavailable = [m["name"] for m in models if _catalog(m, tid) is False]
        if unavailable:
            acc.mint(
                ISSUE_RUNPOD_MODEL_UNAVAILABLE,
                "high",
                pc.SUBJECT_MODELS,
                "Supplied evidence marks these models unavailable to the RunPod "
                "endpoint: {names}.",
                fix_hint="Bake or mount the required models for the endpoint.",
                names=unavailable,
            )
        return

    if tid == pc.TARGET_RUNCOMFY:
        if private:
            acc.mint(
                ISSUE_RUNCOMFY_TOKEN_ATTACH_REQUIRED,
                "medium",
                pc.SUBJECT_MODELS,
                "Attach provider tokens in RunComfy for private/gated models: {names}.",
                fix_hint="Attach Civitai/HuggingFace tokens to the RunComfy session.",
                names=private,
            )
        unavailable = [m["name"] for m in models if _catalog(m, tid) is False]
        if unavailable:
            acc.mint(
                ISSUE_RUNCOMFY_MODEL_UNAVAILABLE,
                "high",
                pc.SUBJECT_MODELS,
                "Supplied evidence marks these models unavailable to RunComfy "
                "auto-setup: {names}.",
                fix_hint="Upload or link the required models in the RunComfy session.",
                names=unavailable,
            )
        return

    if tid == pc.TARGET_COMFY_CLOUD:
        off_catalog = [m["name"] for m in models if _catalog(m, tid) is False]
        if off_catalog:
            acc.mint(
                ISSUE_COMFY_CLOUD_MODEL_OFF_CATALOG,
                "high",
                pc.SUBJECT_MODELS,
                "Comfy Cloud cannot serve models outside its managed catalog: {names}.",
                fix_hint="Remap to catalog equivalents or choose a target with model freedom.",
                names=off_catalog,
            )
        gated_unknown = [
            m["name"]
            for m in models
            if m["private_or_gated"] and _catalog(m, tid) is None
        ]
        if gated_unknown:
            acc.mint(
                ISSUE_COMFY_CLOUD_MODEL_CATALOG_UNKNOWN,
                "medium",
                pc.SUBJECT_MODELS,
                "Comfy Cloud catalog availability for these models is not "
                "established by supplied evidence: {names}.",
                fix_hint="Confirm the models exist in Comfy Cloud's managed catalog.",
                names=gated_unknown,
            )
            acc.capability_unknown()
        return

    if tid == pc.TARGET_BASETEN:
        if private:
            acc.mint(
                ISSUE_BASETEN_PRIVATE_MODEL_SECRET_SETUP,
                "medium",
                pc.SUBJECT_MODELS,
                "Baseten build must fetch private/gated models via secrets: {names}.",
                fix_hint="Fetch private/gated models at build time using Truss secrets.",
                names=private,
            )
        unavailable = [m["name"] for m in models if _catalog(m, tid) is False]
        if unavailable:
            acc.mint(
                ISSUE_BASETEN_MODEL_UNAVAILABLE,
                "high",
                pc.SUBJECT_MODELS,
                "Supplied evidence marks these models unavailable to the Baseten "
                "build: {names}.",
                fix_hint="Fetch or bake the required models into the Truss image.",
                names=unavailable,
            )
        if evidence["baseten_persistent_storage"] == BASETEN_STORAGE_UNKNOWN:
            acc.mint(
                ISSUE_BASETEN_STORAGE_CAPABILITY_UNKNOWN,
                "low",
                pc.SUBJECT_TARGET,
                "Baseten persistent storage options for ComfyUI-style model trees "
                "were unverified in the G3 audit.",
                fix_hint="Verify Baseten storage options before baking large model trees.",
            )
            # Surface the shared uncertainty code without flipping the risk
            # level: models bake into the image either way (embedding already
            # holds MEDIUM). Severity matches capability_unknown() so the
            # shared pool keeps ONE canonical object for this code.
            acc.mint(
                pc.ISSUE_TARGET_CAPABILITY_UNKNOWN,
                "medium",
                pc.SUBJECT_TARGET,
                "A provider capability this readiness decision depends on is unverified.",
                fix_hint="Verify the provider capability before relying on this target.",
            )
        return


# ── Base posture & advice ─────────────────────────────────────────────────

_ADVICE_INPUT_ASSETS = {
    pc.TARGET_RUNPOD: "Provide input assets via the job payload or S3.",
    pc.TARGET_RUNCOMFY: "Upload required input assets through the RunComfy session.",
    pc.TARGET_COMFY_CLOUD: "Upload required input assets through the Comfy Cloud assets API.",
    pc.TARGET_BASETEN: "Wire input assets through deployment values or the predict payload.",
}


def _apply_base_posture(acc, evidence, tid):
    if tid == pc.TARGET_BASETEN:
        acc.mint(
            ISSUE_BASETEN_DEPLOYMENT_EMBEDDING,
            "medium",
            pc.SUBJECT_TARGET,
            "Baseten embeds the workflow into a deployment; free arbitrary "
            "graph-per-request dispatch is not the default model.",
            fix_hint=(
                "Embed the workflow into a Baseten Truss deployment rather than "
                "expecting graph-per-request dispatch."
            ),
        )
    if evidence["requires_input_asset"]:
        line = _ADVICE_INPUT_ASSETS.get(tid)
        if line:
            acc.advise(line)


def _target_advice(acc, evidence, tid):
    """Deterministic, short, provider-specific-only-where-audited advice."""
    codes = set(acc.issue_codes)
    if tid == pc.TARGET_LOCAL:
        if ISSUE_LOCAL_DEPENDENCY_MISSING in codes:
            acc.advise("Resolve missing local dependencies before running.")
        if ISSUE_LOCAL_NATIVE_BUILD_BURDEN in codes:
            acc.advise("Native-build components require local toolchain availability.")
        if pc.ISSUE_LOCAL_PATH_REFERENCE in codes:
            acc.advise(
                "Absolute paths may keep working on this source host; replace them "
                "with portable filenames for cross-target use."
            )
    elif tid == pc.TARGET_MODAL:
        if ISSUE_MODAL_REVISION_UNRESOLVED in codes:
            acc.advise("Resolve repo URL and commit before redeploying the Modal app.")
        if ISSUE_TARGET_ABSOLUTE_PATH_BLOCKER in codes:
            acc.advise("Materialize absolute-path inputs through the product input transport.")
        if ISSUE_MODAL_MODEL_UNAVAILABLE in codes:
            acc.advise("Mount or upload the required models to Modal volumes.")
    elif tid == pc.TARGET_RUNPOD:
        if ISSUE_RUNPOD_IMAGE_SETUP_REQUIRED in codes:
            acc.advise("Build the required custom nodes into the RunPod worker image.")
        if ISSUE_RUNPOD_NATIVE_BUILD_REQUIRED in codes:
            acc.advise("Add native packages and build steps to the worker Dockerfile.")
        if ISSUE_DEPENDENCY_SOURCE_UNRESOLVED in codes:
            acc.advise("Provide a pinned source (repo URL + commit) for every baked dependency.")
        if ISSUE_RUNPOD_PRIVATE_MODEL_TOKEN_SETUP in codes:
            acc.advise("Configure endpoint tokens for private/gated models.")
        if ISSUE_RUNPOD_FRONTEND_SETUP_REQUIRED in codes:
            acc.advise("Ship a subgraph-capable ComfyUI frontend in the worker image.")
        if ISSUE_TARGET_ABSOLUTE_PATH_BLOCKER in codes:
            acc.advise("Map model/input paths onto the worker volume profile (/runpod-volume).")
    elif tid == pc.TARGET_RUNCOMFY:
        if ISSUE_RUNCOMFY_AUTO_SETUP_REQUIRED in codes:
            acc.advise("Let RunComfy auto-setup install the missing nodes/models.")
        if ISSUE_RUNCOMFY_COMMIT_PINNING_UNKNOWN in codes:
            acc.advise("Exact commit-level pinning on RunComfy is unverified; snapshot after setup.")
        if ISSUE_RUNCOMFY_NATIVE_CAPABILITY_UNKNOWN in codes:
            acc.advise("RunComfy native package support for this dependency is unverified.")
        if ISSUE_RUNCOMFY_TOKEN_ATTACH_REQUIRED in codes:
            acc.advise("Attach provider tokens for private/gated models.")
        if ISSUE_RUNCOMFY_SUBGRAPH_SUPPORT_UNKNOWN in codes:
            acc.advise("Verify subgraph execution in a RunComfy session first.")
        if ISSUE_TARGET_ABSOLUTE_PATH_BLOCKER in codes:
            acc.advise("Re-link absolute paths onto the managed /ComfyUI tree.")
    elif tid == pc.TARGET_COMFY_CLOUD:
        if ISSUE_COMFY_CLOUD_NODE_OFF_CATALOG in codes:
            acc.advise("Comfy Cloud cannot install this required custom node.")
        if ISSUE_COMFY_CLOUD_PYTHON_INSTALL_UNSUPPORTED in codes:
            acc.advise("Comfy Cloud cannot install arbitrary Python packages for this workflow.")
        if ISSUE_COMFY_CLOUD_NATIVE_UNSUPPORTED in codes:
            acc.advise("Comfy Cloud cannot install this required native custom-node dependency.")
        if ISSUE_COMFY_CLOUD_MODEL_OFF_CATALOG in codes:
            acc.advise("Remap off-catalog models to Comfy Cloud catalog equivalents or switch targets.")
        if (
            ISSUE_COMFY_CLOUD_NODE_SUPPORT_UNKNOWN in codes
            or ISSUE_COMFY_CLOUD_MODEL_CATALOG_UNKNOWN in codes
            or ISSUE_COMFY_CLOUD_SUBGRAPH_SUPPORT_UNKNOWN in codes
        ):
            acc.advise("Confirm Comfy Cloud catalog/frontend support before exporting there.")
        if ISSUE_TARGET_ABSOLUTE_PATH_BLOCKER in codes:
            acc.advise(
                "Comfy Cloud content-addressed storage has no filesystem semantics for these paths."
            )
    elif tid == pc.TARGET_BASETEN:
        if ISSUE_BASETEN_DEPLOYMENT_EMBEDDING in codes:
            acc.advise(
                "Embed the workflow into a Baseten Truss deployment rather than "
                "expecting graph-per-request dispatch."
            )
        if ISSUE_BASETEN_NODE_BAKE_REQUIRED in codes:
            acc.advise("Clone and install required custom nodes in build_commands.")
        if ISSUE_BASETEN_CUDA_BUILD_REQUIRED in codes:
            acc.advise("Provide CUDA build support in the Truss image for native components.")
        if ISSUE_BASETEN_PRIVATE_MODEL_SECRET_SETUP in codes:
            acc.advise("Fetch private/gated models at build time using secrets.")
        if ISSUE_BASETEN_STORAGE_CAPABILITY_UNKNOWN in codes:
            acc.advise("Verify Baseten persistent-storage options for large model trees.")
        if ISSUE_TARGET_ABSOLUTE_PATH_BLOCKER in codes:
            acc.advise("Rewrite absolute paths onto image-defined paths during the build.")


# ── Public evaluation API ─────────────────────────────────────────────────


def evaluate_target_readiness(evidence) -> dict:
    """Run all six target adapters over prepared evidence (pure).

    Returns::

        {
          "rule_version": "portability-rules-v1",
          "targets": {<six frozen target ids>: make_target_result(...)},
          "issues": [ ...deterministically sorted target-only issues... ],
        }

    ``issues`` contains each target-only issue ONCE (single rendering
    authority, G5 §7.2); targets reference codes. Referenced global codes
    appear in ``targets.*.issue_codes`` only when listed in the evidence's
    ``global_issue_codes`` — the composer merges both lists into the report's
    global pool. Target results never decide the Workflow summary risk: one
    target may be HIGH while the global Workflow risk is MEDIUM.
    """
    if not isinstance(evidence, dict) or any(key not in evidence for key in _EVIDENCE_KEYS):
        raise TargetEvidenceError("evidence must be a build_target_evidence() payload")

    outcomes = {}
    merged_minted = {}

    for tid in pc.TARGET_IDS:
        acc = _Accumulator(tid, evidence["global_issue_codes"])
        _apply_base_posture(acc, evidence, tid)
        _apply_shared_findings(acc, evidence, tid)
        for node in evidence["custom_nodes"]:
            _apply_custom_node(acc, evidence, tid, node)
        _apply_models(acc, evidence, tid)
        _target_advice(acc, evidence, tid)
        outcomes[tid] = acc.result()
        for issue in acc.finalize_issues():
            existing = merged_minted.get(issue["code"])
            if existing is None:
                merged_minted[issue["code"]] = issue
            elif pc.canonical_json(existing) != pc.canonical_json(issue):
                raise TargetEvidenceError(
                    "conflicting minted issue objects for code %s" % issue["code"]
                )

    return {
        "rule_version": PORTABILITY_RULE_VERSION,
        "targets": outcomes,
        "issues": pc.sort_issues(list(merged_minted.values())),
    }


def evaluate_single_target(target_id, evidence):
    """Evaluate readiness for exactly one frozen target id (pure).

    Returns ``{"target": <target result>, "issues": [minted issues...]}``.
    Aliases (``comfy-cloud``, ``comfycloud``, ``run_comfy``) are rejected via
    the contract's ``normalize_target_id``.
    """
    tid = pc.normalize_target_id(target_id)
    outcome = evaluate_target_readiness(evidence)
    result = outcome["targets"][tid]
    referenced = set(result["issue_codes"])
    return {
        "target": result,
        "issues": [i for i in outcome["issues"] if i["code"] in referenced],
    }


__all__ = [
    "PORTABILITY_RULE_VERSION",
    "TargetEvidenceError",
    "INSTALL_STATUSES",
    "DEPENDENCY_FLAGS",
    "RUNCOMFY_NATIVE_CAPABILITIES",
    "BASETEN_STORAGE_STATES",
    "TARGET_ONLY_ISSUE_CODES",
    "REFERENCABLE_GLOBAL_CODES",
    "build_target_evidence",
    "evaluate_target_readiness",
    "evaluate_single_target",
]
