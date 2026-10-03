"""Tests for portability_contract (pure Phase-G5 contract freeze module).

Runs with plain ``python tests/test_portability_contract.py`` (includes a
``__main__`` harness) and is also pytest-discoverable. No network, no GPU,
no filesystem writes.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import portability_contract as c


# ── Shared fixtures ───────────────────────────────────────────────────────


def make_issue(**overrides):
    base = {
        "code": "model_hash_unpinned",
        "severity": "medium",
        "message": "Model ref has no sha256.",
        "subject": "models",
        "fix_hint": "Pin a hash in the export dialog.",
    }
    base.update(overrides)
    return base


def make_report(**overrides):
    graph_hash = "a" * 64
    issues = [
        c.build_issue(
            code="custom_node_unpinned",
            severity="medium",
            message="2 unpinned custom nodes.",
            subject="custom_nodes",
        ),
        c.build_issue(
            code="required_input_asset",
            severity="low",
            message="Input asset must travel separately.",
            subject="assets",
        ),
    ]
    report = {
        "version_id": "wv_8821af78d5c8408d",
        "graph_hash": graph_hash,
        "risk_level": "medium",
        "rule_version": c.PORTABILITY_RULE_VERSION,
        "issue_count": len(issues),
        "counts": {"high": 0, "medium": 1, "low": 1},
        "issues": issues,
        "signals": {
            "has_absolute_path": False,
            "unresolved_node_count": 0,
            "uses_subgraphs": True,
        },
        "targets": {
            tid: c.make_target_result(risk_level="low") for tid in c.TARGET_IDS
        },
        "environment": {
            "risk_level": "high",
            "issues": [
                c.build_issue(
                    code="torch_stack_unpinned",
                    severity="high",
                    message="Torch trio floats.",
                    subject="environment",
                )
            ],
            "source": c.ENVIRONMENT_SOURCE_CURRENT_STUDIO,
        },
        "stale": False,
        "invalidation": c.build_invalidation_stamp(
            workflow_version_id="wv_8821af78d5c8408d",
            graph_hash=graph_hash,
            rule_version=c.PORTABILITY_RULE_VERSION,
            manifest_version=1,
        ),
        "analyzed_at": "2026-08-23T00:00:00+00:00",
    }
    report.update(overrides)
    return report


# ── 1/2/11: risk levels ───────────────────────────────────────────────────


def test_every_valid_risk_level_accepted():
    for level in ("low", "medium", "high", "unknown"):
        assert c.normalize_risk_level(level) == level
    assert c.normalize_risk_level("HIGH") == "high"
    assert c.normalize_risk_level(" Unknown ") == "unknown"


def test_invalid_risk_rejected():
    for bad in ("none", "critical", "", "LOWISH", 1, True, None):
        try:
            c.normalize_risk_level(bad)
        except c.PortabilityContractError:
            pass
        else:
            raise AssertionError("risk level %r should be rejected" % (bad,))


def test_unknown_supported_and_never_normalized_to_low():
    assert c.PortabilityRiskLevel.UNKNOWN == "unknown"
    assert c.normalize_risk_level(c.PortabilityRiskLevel.UNKNOWN) == "unknown"
    assert "unknown" not in c.SEVERITIES
    assert set(c.RISK_LEVEL_SEMANTICS) == set(c.RISK_LEVELS)


# ── 3/4: target ids ───────────────────────────────────────────────────────


def test_every_valid_target_id_accepted():
    assert c.TARGET_IDS == (
        "local", "modal", "runpod", "runcomfy", "comfy_cloud", "baseten",
    )
    for tid in c.TARGET_IDS:
        assert c.normalize_target_id(tid) == tid


def test_invalid_target_rejected():
    for bad in ("comfy-cloud", "comfycloud", "run_comfy", "Comfy Cloud", "", None, 1):
        try:
            c.normalize_target_id(bad)
        except c.PortabilityContractError:
            pass
        else:
            raise AssertionError("target id %r should be rejected" % (bad,))
    for alias in c.BANNED_TARGET_ALIASES:
        assert alias not in c.TARGET_IDS


# ── 5: severity ordering deterministic ────────────────────────────────────


def test_severity_ordering_deterministic():
    issues = [
        make_issue(code="zzz_low", severity="low"),
        make_issue(code="aaa_high", severity="high"),
        make_issue(code="mmm_med", severity="medium"),
        make_issue(code="bbb_high", severity="high", subject="graph"),
        make_issue(code="aaa_high_dup", severity="high"),
    ]
    ordered = [i["code"] for i in c.sort_issues(issues)]
    assert ordered == ["aaa_high", "aaa_high_dup", "bbb_high", "mmm_med", "zzz_low"]
    again = [i["code"] for i in c.sort_issues(list(reversed(issues)))]
    assert again == ordered
    ranks = {s: r for r, s in enumerate(reversed(c.SEVERITIES), start=1)}
    assert ranks == {"low": 1, "medium": 2, "high": 3}


def test_no_unknown_severity():
    try:
        c.normalize_severity("unknown")
    except c.PortabilityContractError:
        pass
    else:
        raise AssertionError("severity 'unknown' must not exist")


# ── 6: issue normalization deterministic ──────────────────────────────────


def test_issue_normalization_deterministic():
    raw = make_issue(fix_hint=None, evidence={"filename": "x.safetensors"})
    first = c.normalize_issue(raw)
    second = c.normalize_issue(dict(first))
    assert first == second
    assert set(first) == {"code", "severity", "message", "subject", "fix_hint", "evidence"}
    empty_evidence = c.normalize_issue(make_issue(evidence={}))
    assert "evidence" not in empty_evidence
    default_hint = c.normalize_issue(make_issue(fix_hint=None))
    assert default_hint["fix_hint"] == ""


def test_issue_normalization_rejects_bad_payloads():
    for bad in (
        make_issue(code="Bad-Code"),
        make_issue(severity="unknown"),
        make_issue(message=""),
        make_issue(subject="arbitrary_subject"),
        make_issue(evidence="not-a-dict"),
        make_issue(evidence={"k": float("nan")}),
        "not-a-dict",
    ):
        try:
            c.normalize_issue(bad)
        except c.PortabilityContractError:
            pass
        else:
            raise AssertionError("issue %r should be rejected" % (bad,))


def test_evidence_is_bounded():
    big = {"blob": "x" * (c.EVIDENCE_MAX_CANONICAL_BYTES + 1)}
    try:
        c.normalize_issue(make_issue(evidence=big))
    except c.PortabilityContractError as exc:
        assert any("evidence" in msg for msg in exc.issues)
    else:
        raise AssertionError("oversized evidence should be rejected")


# ── 7: stable subject vocabulary ──────────────────────────────────────────


def test_stable_subject_vocabulary():
    assert c.SUBJECT_VOCABULARY == (
        "graph", "custom_nodes", "models", "assets", "paths", "endpoints",
        "frontend", "environment", "manifest", "target",
    )
    for subject in c.SUBJECT_VOCABULARY:
        assert c.normalize_issue(make_issue(subject=subject))["subject"] == subject


# ── 8/9/10: report contract ───────────────────────────────────────────────


def test_required_report_fields():
    assert c.REPORT_REQUIRED_FIELDS == (
        "version_id", "graph_hash", "risk_level", "rule_version",
        "issue_count", "counts", "issues", "signals", "targets",
        "environment", "stale", "invalidation", "analyzed_at",
    )
    c.validate_report(make_report())
    for field in c.REPORT_REQUIRED_FIELDS:
        trimmed = make_report()
        del trimmed[field]
        msgs = c.report_validation_issues(trimmed)
        assert any(field in m for m in msgs), field


def test_all_six_target_keys_required_and_exact():
    report = make_report()
    c.validate_report(report)
    assert set(report["targets"]) == set(c.TARGET_IDS)
    trimmed = make_report()
    del trimmed["targets"]["baseten"]
    assert any("baseten" in m for m in c.report_validation_issues(trimmed))
    extra = make_report()
    extra["targets"]["comfy-cloud"] = c.make_target_result(risk_level="low")
    assert any("comfy-cloud" in m for m in c.report_validation_issues(extra))


def test_environment_section_distinct_from_summary():
    report = make_report()
    assert report["risk_level"] != report["environment"]["risk_level"]
    c.validate_report(report)
    concepts = set(c.PORTABILITY_CONCEPTS)
    assert len(concepts) == 5
    assert c.CONCEPT_WORKFLOW_PORTABILITY_RISK in concepts
    assert c.CONCEPT_ENVIRONMENT_REPRODUCIBILITY in concepts
    assert c.CONCEPT_TARGET_READINESS in concepts
    broken = make_report(environment={"risk_level": "high", "issues": []})
    assert any("source" in m for m in c.report_validation_issues(broken))


def test_report_counts_and_rule_version_pinned():
    report = make_report(counts={"high": 0, "medium": 9})
    msgs = c.report_validation_issues(report)
    assert any("low" in m for m in msgs)
    wrong_count = make_report(issue_count=99)
    assert any("issue_count" in m for m in c.report_validation_issues(wrong_count))
    wrong_rules = make_report(rule_version="portability-rules-v2")
    assert c.report_validation_issues(wrong_rules)


def test_target_results_reference_global_issue_codes():
    report = make_report()
    report["issues"].append(
        c.build_issue(
            code="dependency_missing",
            severity="high",
            message="Required node class unresolved.",
            subject="custom_nodes",
        )
    )
    report["issue_count"] = len(report["issues"])
    report["counts"] = {"high": 1, "medium": 1, "low": 1}
    report["targets"]["modal"] = c.make_target_result(
        risk_level="high",
        issue_codes=["dependency_missing"],
        advice=["Bake missing dependency into the image."],
    )
    c.validate_report(report)
    dangling = make_report(
        targets={tid: c.make_target_result(risk_level="low", issue_codes=["nope_missing"])
                 for tid in c.TARGET_IDS}
    )
    assert any("nope_missing" in m for m in c.report_validation_issues(dangling))


# ── 12: invalidation shape + semantics ────────────────────────────────────


def test_invalidation_shape():
    assert c.INVALIDATION_FIELDS == (
        "workflow_version_id", "graph_hash", "dependency_metadata_hash",
        "model_library_generation", "custom_node_registry_generation",
        "rule_version", "manifest_version", "comfyui_version",
    )
    stamp = c.build_invalidation_stamp()
    assert set(stamp) == set(c.INVALIDATION_FIELDS)
    assert stamp["rule_version"] == c.PORTABILITY_RULE_VERSION
    assert all(stamp[f] is None for f in c.INVALIDATION_FIELDS if f != "rule_version")
    assert c.invalidation_stamp_issues(stamp) == []
    partial = dict(stamp)
    del partial["graph_hash"]
    assert any("graph_hash" in m for m in c.invalidation_stamp_issues(partial))


def test_invalidation_null_never_means_unchanged_forever():
    current = c.build_invalidation_stamp(
        workflow_version_id="wv_a", graph_hash="a" * 64,
        dependency_metadata_hash="b" * 64,
        model_library_generation=3, custom_node_registry_generation=7,
        rule_version=c.PORTABILITY_RULE_VERSION, manifest_version=1,
        comfyui_version="0.24.0",
    )
    assert c.invalidation_stamps_match(current, dict(current))
    changed = dict(current)
    changed["model_library_generation"] = 4
    assert not c.invalidation_stamps_match(current, changed)
    assert "model_library_generation" in c.invalidation_mismatches(current, changed)
    unknown_side = dict(current)
    unknown_side["comfyui_version"] = None
    assert not c.invalidation_stamps_match(current, unknown_side)
    both_unknown = c.build_invalidation_stamp(
        workflow_version_id="wv_a", graph_hash="a" * 64,
        rule_version=c.PORTABILITY_RULE_VERSION, manifest_version=1,
    )
    assert not c.invalidation_stamps_match(current, both_unknown)
    assert not c.invalidation_stamps_match(both_unknown, both_unknown)


# ── 13: rule version exact ────────────────────────────────────────────────


def test_rule_version_exact():
    assert c.PORTABILITY_RULE_VERSION == "portability-rules-v1"


# ── 14/15/16/17: endpoint contracts ───────────────────────────────────────


def test_export_endpoint_constants():
    assert c.EXPORT_ENDPOINT == "/comfymodal/studio/workflows/versions/{version_id}/export"
    path = c.EXPORT_ENDPOINT.format(version_id="wv_abc")
    assert path.startswith("/comfymodal/studio/workflows/")
    assert path.endswith("/export")
    # Presets are gone, so the export contract carries no preset query flag.
    assert not hasattr(c, "EXPORT_QUERY_INCLUDE_PRESETS")
    assert not hasattr(c, "EXPORT_DEFAULT_INCLUDE_PRESETS")


def test_import_endpoint_constants():
    assert c.IMPORT_MANIFEST_ENDPOINT == "/comfymodal/studio/workflows/import-manifest"
    assert c.IMPORT_MANIFEST_ENDPOINT != "/comfymodal/studio/workflows/import"
    assert c.IMPORT_QUERY_DRY_RUN == "dry_run"


def test_import_dry_run_default_contract():
    assert c.IMPORT_DEFAULT_DRY_RUN is True
    assert isinstance(c.IMPORT_DEFAULT_DRY_RUN, bool)


def test_preset_policy_flags_are_gone():
    """Presets no longer exist, so the contract must not offer preset policy."""
    for name in (
        "EXPORT_QUERY_INCLUDE_PRESETS",
        "EXPORT_DEFAULT_INCLUDE_PRESETS",
        "IMPORT_FIELD_IMPORT_PRESETS",
        "IMPORT_FIELD_APPLY_DEFAULT_PRESET",
        "IMPORT_DEFAULT_IMPORT_PRESETS",
        "IMPORT_DEFAULT_APPLY_DEFAULT_PRESET",
    ):
        assert not hasattr(c, name), f"{name} must not be re-introduced"
    assert c.IMPORT_PREVIEW_STATUS == "preview"


# ── 18: stable foundational issue codes ───────────────────────────────────


def test_stable_foundational_issue_codes():
    expected = {
        "credential_like_value_detected", "local_path_reference",
        "unresolved_node_type", "custom_node_unpinned", "model_hash_unpinned",
        "model_extraction_gap", "required_input_asset",
        "external_endpoint_reference", "subgraph_frontend_requirement",
        "manifest_not_ready", "dependency_missing",
        "dependency_wrong_revision", "target_capability_unknown",
    }
    assert set(c.FOUNDATIONAL_ISSUE_CODES) == expected
    assert len(c.FOUNDATIONAL_ISSUE_CODES) == len(set(c.FOUNDATIONAL_ISSUE_CODES))
    assert set(c.ENVIRONMENT_ISSUE_CODES) == {
        "torch_stack_unpinned", "custom_node_source_unpinned",
        "plugin_worktree_dirty", "local_core_patch_divergence",
        "model_hash_unpinned", "base_image_digest_unpinned",
    }


# ── 19: deterministic canonical serialization ─────────────────────────────


def test_canonical_serialization_deterministic():
    a = {"b": 1, "a": {"z": [1, 2], "y": None}}
    b = {"a": {"y": None, "z": [1, 2]}, "b": 1}
    assert c.canonical_json(a) == c.canonical_json(b)
    assert c.sha256_of_canonical(a) == c.sha256_of_canonical(b)
    try:
        c.canonical_json({"x": float("inf")})
    except ValueError:
        pass
    else:
        raise AssertionError("NaN/Infinity must be rejected")
    assert c.is_sha256_hex("a" * 64)
    assert not c.is_sha256_hex("A" * 64)


# ── 20: separately named concepts ─────────────────────────────────────────


def test_concepts_remain_separately_named():
    names = [
        c.CONCEPT_MANIFEST_READINESS,
        c.CONCEPT_DEPENDENCY_AVAILABILITY,
        c.CONCEPT_WORKFLOW_PORTABILITY_RISK,
        c.CONCEPT_TARGET_READINESS,
        c.CONCEPT_ENVIRONMENT_REPRODUCIBILITY,
    ]
    assert len(set(names)) == 5
    assert c.MANIFEST_AUTHORITY_MODULE == "studio_workflow_manifest"
    assert c.SUPPORTED_MANIFEST_VERSIONS == (1,)


# ── Signals / provenance / policies / filename ────────────────────────────


def test_signal_vocabulary_and_types():
    names = set(c.SIGNAL_NAMES)
    required = {
        "has_absolute_path", "has_unresolved_node_type", "custom_node_count",
        "custom_repo_count", "custom_node_revision_pinned",
        "model_ref_basename_only", "model_hash_pinned", "model_extraction_gap",
        "requires_input_asset", "has_external_endpoint", "uses_subgraphs",
        "exact_roundtrip_proven", "env_bound_registry_leak",
        "unresolved_node_count",
    }
    assert required <= names
    normalized = c.normalize_signals({
        "has_absolute_path": False,
        "unresolved_node_count": 3,
        "custom_node_count": 22,
    })
    assert normalized["unresolved_node_count"] == 3
    for bad in (
        {"has_absolute_path": 1},
        {"custom_node_count": True},
        {"custom_node_count": -1},
        {"s13_new_thing": True},
        "not-a-dict",
    ):
        try:
            c.normalize_signals(bad)
        except c.PortabilityContractError:
            pass
        else:
            raise AssertionError("signals %r should be rejected" % (bad,))


def test_provenance_quality_vocabulary():
    assert c.PROVENANCE_QUALITY_VALUES == ("exact", "declared", "inferred", "unresolved")


def test_policy_descriptors_frozen():
    assert c.POLICY_SUBGRAPHS == "target_sensitive_not_global_blocker"
    assert c.POLICY_ABSOLUTE_PATHS == "global_finding_with_target_severity_override"
    assert "never_forces" in c.POLICY_ENVIRONMENT_ISOLATION


def test_security_limits_frozen():
    assert c.MAX_IMPORT_BODY_BYTES == 10 * 1024 * 1024
    assert c.MAX_JSON_DEPTH >= 16
    assert len(c.SECURITY_RULES) >= 10


def test_export_filename_helper():
    name = c.suggest_export_filename("Smoke Test Workflow", 2, "7911b4070925df26" + "0" * 48)
    assert name == "Smoke_Test_Workflow-v2-7911b407.workflow.json"
    assert c.suggest_export_filename("", 1, "a" * 64).startswith("workflow-v1-")
    for bad_args in ((None, 0, "a" * 64), ("x", True, "a" * 64), ("x", 1, "ZZ")):
        try:
            c.suggest_export_filename(*bad_args)
        except c.PortabilityContractError:
            pass
        else:
            raise AssertionError("filename args %r should be rejected" % (bad_args,))


def test_checklist_fields_frozen():
    assert c.CHECKLIST_FIELDS == (
        "summary_risk_level", "issue_counts", "issue_rows", "dependency_table",
        "target_matrix", "import_expectations", "provenance", "rule_version",
        "analyzed_at",
    )


if __name__ == "__main__":
    failed = 0
    fns = sorted(name for name in dir() if name.startswith("test_"))
    for name in fns:
        try:
            globals()[name]()
            print("ok  %s" % name)
        except AssertionError as exc:
            failed += 1
            print("FAIL %s: %s" % (name, exc))
    print("%d/%d passed" % (len(fns) - failed, len(fns)))
    sys.exit(1 if failed else 0)
