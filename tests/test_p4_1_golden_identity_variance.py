"""Focused P4.1 contracts for Golden identity and variance reporting."""

from __future__ import annotations

from tools import golden_observability as go


def test_hash_domains_are_explicit_and_use_one_canonical_json_encoding():
    raw = b'{ "b": 2, "a": 1 }'
    matrix = go.build_workflow_identity_matrix(
        workflow_file_bytes=raw,
        parsed_workflow={"a": 1, "b": 2},
        source_workflow="source-digest",
        compiled_workflow="compiled-digest",
        request_prompt={"prompt": "one"},
        normalized_golden_request={"prompt": "two"},
        actual_executed_workflow="actual-digest",
        expected_contract_workflow="expected-digest",
    )
    assert matrix["workflow_file_bytes_sha256"] != matrix["parsed_workflow_json_sha256"]
    assert matrix["request_prompt_sha256"] != matrix["normalized_golden_request_sha256"]
    assert matrix["source_workflow_sha256"] != matrix["compiled_workflow_sha256"]
    assert set(go.WORKFLOW_IDENTITY_FIELDS) <= set(matrix)
    assert go.canonical_json_sha256({"b": 2, "a": 1}) == matrix["parsed_workflow_json_sha256"]


def test_workflow_contract_rejects_bypass_and_mismatched_identity():
    bad = {
        "enabled": True,
        "bypassed": True,
        "actual_executed_workflow_sha256": "actual",
        "expected_contract_workflow_sha256": "expected",
    }
    result = go.validate_workflow_contract(bad)
    assert not result["valid"]
    assert any("bypassed" in reason for reason in result["reasons"])
    assert any("differ" in reason for reason in result["reasons"])


def test_stats_keep_raw_observations_and_all_variance_fields():
    stats = go.compute_stats([1, 2, 3, 4, 5])
    assert stats["raw_observations"] == [1.0, 2.0, 3.0, 4.0, 5.0]
    assert stats["min"] == 1.0 and stats["max"] == 5.0
    assert stats["median"] == 3.0 and stats["mean"] == 3.0 and stats["p90"] == 5.0
    assert stats["stdev"] > 0 and stats["cv"] > 0 and stats["range"] == 4.0
    assert "nearest_rank" in stats["method"]
    assert "no trimming" in stats["method"]


def test_comparison_is_conservative_about_tails_and_one_run_claims():
    def report(values, n=5):
        return {"valid": True, "stats": {
            "golden_unet_load": {
                "n": n, "min": min(values), "max": max(values),
                "median": values[len(values) // 2], "mean": sum(values) / len(values),
                "p90": sorted(values)[-1], "cv": 0.1, "range": max(values) - min(values),
            }
        }}

    improved = go.compare_baseline_candidate(report([10, 10, 12, 12, 12]),
                                              report([8, 8, 9, 10, 12]))
    assert improved["verdict"] == "IMPROVED"
    regressed_tail = go.compare_baseline_candidate(report([10, 10, 12, 12, 12]),
                                                    report([8, 8, 9, 10, 20]))
    assert regressed_tail["verdict"] == "REGRESSION"
    assert go.compare_baseline_candidate(report([10], n=1), report([8], n=1))["verdict"] == "UNVERIFIED"
