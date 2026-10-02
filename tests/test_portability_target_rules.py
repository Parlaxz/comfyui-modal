"""Tests for portability_targets (pure Phase G7 target-readiness adapters).

Runs with plain ``python tests/test_portability_target_rules.py`` (includes a
``__main__`` harness) and is also pytest-discoverable. No network, no GPU,
no filesystem writes, no provider SDKs.
"""

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import portability_contract as c
import portability_targets as t


# ── Shared fixtures ───────────────────────────────────────────────────────


def core_evidence(
    *,
    global_issue_codes=None,
    signals=None,
    custom_nodes=None,
    models=None,
    absolute_paths=None,
    requires_input_asset=False,
    uses_subgraphs=False,
    frontend_version="1.44.19",
    manifest_ready=True,
    frontend_support=None,
    runcomfy_native_capability=t.RUNCOMFY_NATIVE_UNKNOWN,
    baseten_persistent_storage=t.BASETEN_STORAGE_UNKNOWN,
):
    """Golden matrix A base: core nodes + standard checkpoint."""
    return t.build_target_evidence(
        global_issue_codes=(
            ["model_hash_unpinned"] if global_issue_codes is None else global_issue_codes
        ),
        signals={"model_hash_pinned": False} if signals is None else signals,
        custom_nodes=[] if custom_nodes is None else custom_nodes,
        models=(
            [
                {
                    "name": "sd_xl_base_1.0.safetensors",
                    "sha256": None,
                    "private_or_gated": False,
                    "present_locally": True,
                    "target_catalog_available": {},
                }
            ]
            if models is None
            else models
        ),
        absolute_paths=[] if absolute_paths is None else absolute_paths,
        requires_input_asset=requires_input_asset,
        uses_subgraphs=uses_subgraphs,
        frontend_version=frontend_version,
        manifest_ready=manifest_ready,
        frontend_support=frontend_support,
        runcomfy_native_capability=runcomfy_native_capability,
        baseten_persistent_storage=baseten_persistent_storage,
    )


def levels(outcome):
    return {tid: res["risk_level"] for tid, res in outcome["targets"].items()}


# ── 1: exact six target keys ──────────────────────────────────────────────


def test_exact_six_target_keys():
    outcome = t.evaluate_target_readiness(core_evidence())
    assert tuple(outcome["targets"].keys()) == c.TARGET_IDS
    assert set(outcome["targets"]) == {
        "local", "modal", "runpod", "runcomfy", "comfy_cloud", "baseten"
    }
    for result in outcome["targets"].values():
        assert set(result) == set(c.TARGET_RESULT_REQUIRED_FIELDS)


# ── 2: aliases rejected via contract ──────────────────────────────────────


def test_wire_aliases_rejected():
    evidence = core_evidence()
    for alias in c.BANNED_TARGET_ALIASES:
        try:
            c.normalize_target_id(alias)
        except c.PortabilityContractError:
            pass
        else:
            raise AssertionError("alias %r must be rejected" % alias)
        try:
            t.evaluate_single_target(alias, evidence)
        except c.PortabilityContractError:
            pass
        else:
            raise AssertionError("evaluate_single_target(%r) must raise" % alias)


# ── 3: core golden matrix ─────────────────────────────────────────────────


def test_golden_core_matrix():
    got = levels(t.evaluate_target_readiness(core_evidence()))
    assert got == {
        "local": "low",
        "modal": "low",
        "runpod": "low",
        "runcomfy": "low",
        "comfy_cloud": "low",
        "baseten": "medium",
    }


# ── 4: popular custom-node matrix ─────────────────────────────────────────


def popular_evidence(comfy_cloud_support=None):
    return core_evidence(
        custom_nodes=[
            {
                "name": "rgthree-comfy",
                "provenance": "declared",
                "manager_restorable": True,
                "requires_python_install": True,
                "target_supported": (
                    {"comfy_cloud": comfy_cloud_support}
                    if comfy_cloud_support is not None
                    else {}
                ),
            }
        ]
    )


def test_golden_popular_custom_node_matrix():
    got = levels(t.evaluate_target_readiness(popular_evidence()))
    assert got["local"] == "low"
    assert got["modal"] == "low"
    assert got["runpod"] == "medium"
    assert got["runcomfy"] == "low"
    assert got["baseten"] == "medium"
    # Comfy Cloud: LOW only if explicitly represented as supported;
    # otherwise HIGH/UNKNOWN according to supplied evidence.
    assert got["comfy_cloud"] == "unknown"

    supported = levels(t.evaluate_target_readiness(popular_evidence(True)))
    assert supported["comfy_cloud"] == "low"

    unsupported = levels(t.evaluate_target_readiness(popular_evidence(False)))
    assert unsupported["comfy_cloud"] == "high"


# ── 5: native-build dependency matrix ─────────────────────────────────────


def native_evidence(runcomfy_capability=t.RUNCOMFY_NATIVE_UNKNOWN):
    return core_evidence(
        custom_nodes=[
            {
                "name": "SageAttention-class",
                "provenance": "exact",
                "requires_native_build": True,
                "requires_cuda_build": True,
                "manager_restorable": False,
            }
        ],
        runcomfy_native_capability=runcomfy_capability,
    )


def test_golden_native_build_matrix():
    got = levels(t.evaluate_target_readiness(native_evidence()))
    assert got["local"] == "medium"
    assert got["modal"] == "low"
    assert got["runpod"] == "high"
    assert got["runcomfy"] == "unknown"  # capability UNKNOWN preserved
    assert got["comfy_cloud"] == "high"
    assert got["baseten"] == "high"


def test_runcomfy_native_supported_variant_is_high():
    got = levels(t.evaluate_target_readiness(native_evidence(t.RUNCOMFY_NATIVE_SUPPORTED)))
    assert got["runcomfy"] == "high"


# ── 6: absolute-path matrix ───────────────────────────────────────────────


def abspath_evidence(product_materialized=False):
    return core_evidence(
        global_issue_codes=["model_hash_unpinned", "local_path_reference"],
        absolute_paths=[
            {
                "path": "C:\\seed\\input\\ref.png",
                "source_host_consistent": True,
                "product_materialized": product_materialized,
            }
        ],
    )


def test_golden_absolute_path_matrix():
    got = levels(t.evaluate_target_readiness(abspath_evidence()))
    assert got["local"] == "low"  # self-consistent host path stays usable
    for tid in ("modal", "runpod", "runcomfy", "comfy_cloud", "baseten"):
        assert got[tid] == "high", tid
    outcome = t.evaluate_target_readiness(abspath_evidence())
    local_codes = outcome["targets"]["local"]["issue_codes"]
    assert "local_path_reference" in local_codes  # finding remains visible
    assert "target_absolute_path_blocker" in outcome["targets"]["runpod"]["issue_codes"]


def test_modal_product_materialized_path_not_blocker():
    got = levels(t.evaluate_target_readiness(abspath_evidence(product_materialized=True)))
    assert got["modal"] == "low"
    for tid in ("runpod", "runcomfy", "comfy_cloud", "baseten"):
        assert got[tid] == "high", tid


# ── 7: private/gated model matrix ─────────────────────────────────────────


def gated_model_evidence(comfy_cloud_catalog=None):
    catalog = {"comfy_cloud": comfy_cloud_catalog} if comfy_cloud_catalog is not None else {}
    return core_evidence(
        models=[
            {
                "name": "private_flux.safetensors",
                "sha256": "a" * 64,
                "private_or_gated": True,
                "present_locally": True,
                "target_catalog_available": catalog,
            }
        ]
    )


def test_golden_private_gated_model_matrix():
    got = levels(t.evaluate_target_readiness(gated_model_evidence()))
    assert got["local"] == "low"
    assert got["modal"] == "low"
    assert got["runpod"] == "medium"
    assert got["runcomfy"] == "medium"
    assert got["comfy_cloud"] == "unknown"  # catalog evidence unknown
    assert got["baseten"] == "medium"

    off_catalog = levels(t.evaluate_target_readiness(gated_model_evidence(False)))
    assert off_catalog["comfy_cloud"] == "high"

    in_catalog = levels(t.evaluate_target_readiness(gated_model_evidence(True)))
    assert in_catalog["comfy_cloud"] == "low"


# ── 8/9/10: Comfy Cloud restriction awareness is fail-honest ──────────────


def test_comfy_cloud_off_catalog_node_high():
    evidence = core_evidence(
        custom_nodes=[
            {
                "name": "exotic_node_pack",
                "provenance": "declared",
                "target_supported": {"comfy_cloud": False},
            }
        ]
    )
    single = t.evaluate_single_target("comfy_cloud", evidence)
    assert single["target"]["risk_level"] == "high"
    assert "comfy_cloud_node_off_catalog" in single["target"]["issue_codes"]
    advice = " ".join(single["target"]["advice"])
    assert "cannot install this required custom node" in advice


def test_comfy_cloud_arbitrary_python_install_high():
    evidence = core_evidence(
        custom_nodes=[
            {
                "name": "pip_heavy_node",
                "provenance": "declared",
                "requires_python_install": True,
                "target_supported": {"comfy_cloud": False},
            }
        ]
    )
    single = t.evaluate_single_target("comfy_cloud", evidence)
    assert single["target"]["risk_level"] == "high"
    assert "comfy_cloud_python_install_unsupported" in single["target"]["issue_codes"]


def test_comfy_cloud_native_dependency_high():
    evidence = core_evidence(
        custom_nodes=[
            {
                "name": "cuda_op_node",
                "provenance": "exact",
                "requires_system_packages": True,
                "requires_native_build": True,
                "target_supported": {"comfy_cloud": False},
            }
        ]
    )
    single = t.evaluate_single_target("comfy_cloud", evidence)
    assert single["target"]["risk_level"] == "high"
    assert "comfy_cloud_native_dependency_unsupported" in single["target"]["issue_codes"]
    assert any("cannot install this required native" in a for a in single["target"]["advice"])


# ── 11/12: RunPod posture ─────────────────────────────────────────────────


def test_runpod_known_custom_dependency_setup_advice():
    evidence = popular_evidence()
    single = t.evaluate_single_target("runpod", evidence)
    assert single["target"]["risk_level"] == "medium"
    assert "runpod_image_setup_required" in single["target"]["issue_codes"]
    assert "Build the required custom nodes into the RunPod worker image." in (
        single["target"]["advice"]
    )


def test_runpod_native_build_risk():
    evidence = native_evidence()
    single = t.evaluate_single_target("runpod", evidence)
    assert single["target"]["risk_level"] == "high"
    assert "runpod_native_build_required" in single["target"]["issue_codes"]


# ── 13/14: RunComfy posture ───────────────────────────────────────────────


def test_runcomfy_manager_friendly_dependency_low():
    evidence = core_evidence(
        custom_nodes=[
            {
                "name": "popular_pack",
                "provenance": "declared",
                "manager_restorable": True,
                "requires_python_install": True,
            }
        ]
    )
    single = t.evaluate_single_target("runcomfy", evidence)
    assert single["target"]["risk_level"] == "low"
    assert "runcomfy_auto_setup_required" not in single["target"]["issue_codes"]

    # Exact-pin provenance keeps LOW but surfaces the pinning caveat.
    pinned = core_evidence(
        custom_nodes=[
            {
                "name": "popular_pack",
                "provenance": "exact",
                "manager_restorable": True,
            }
        ]
    )
    pinned_single = t.evaluate_single_target("runcomfy", pinned)
    assert pinned_single["target"]["risk_level"] == "low"
    assert "runcomfy_commit_pinning_unknown" in pinned_single["target"]["issue_codes"]


def test_runcomfy_unknown_native_capability_explicit_uncertainty():
    evidence = native_evidence(t.RUNCOMFY_NATIVE_UNKNOWN)
    single = t.evaluate_single_target("runcomfy", evidence)
    assert single["target"]["risk_level"] == "unknown"
    assert "runcomfy_native_capability_unknown" in single["target"]["issue_codes"]
    assert "target_capability_unknown" in single["target"]["issue_codes"]
    assert any("unverified" in a for a in single["target"]["advice"])


# ── 15: Modal product-internal dependency may be supported ────────────────


def test_modal_product_internal_dependency_supported():
    evidence = core_evidence(
        custom_nodes=[
            {
                "name": "studio_internal_output",
                "provenance": "unresolved",
                "product_internal": True,
            }
        ]
    )
    got = levels(t.evaluate_target_readiness(evidence))
    assert got["modal"] == "low"
    assert got["local"] == "low"
    for tid in ("runpod", "runcomfy", "comfy_cloud", "baseten"):
        assert got[tid] == "high", tid
        single = t.evaluate_single_target(tid, evidence)
        assert "product_internal_dependency" in single["target"]["issue_codes"]


# ── 16: Baseten deployment-model mismatch advice ──────────────────────────


def test_baseten_deployment_embedding_advice_always_present():
    single = t.evaluate_single_target("baseten", core_evidence())
    assert single["target"]["risk_level"] == "medium"
    assert "baseten_deployment_embedding_required" in single["target"]["issue_codes"]
    assert any("Embed the workflow into a Baseten Truss deployment" in a for a in single["target"]["advice"])


# ── 17: subgraph target sensitivity ───────────────────────────────────────


def test_subgraph_target_sensitivity():
    evidence = core_evidence(uses_subgraphs=True)
    got = levels(t.evaluate_target_readiness(evidence))
    assert got["local"] == "low"   # frontend 1.44.19 supports subgraphs
    assert got["modal"] == "low"   # product image ships current frontend
    assert got["runpod"] == "medium"
    assert got["baseten"] == "medium"
    assert got["runcomfy"] == "unknown"     # unverified platform frontend
    assert got["comfy_cloud"] == "unknown"  # unverified platform frontend

    outcome = t.evaluate_target_readiness(evidence)
    assert "runpod_frontend_setup_required" in outcome["targets"]["runpod"]["issue_codes"]
    assert "baseten_frontend_setup_required" in outcome["targets"]["baseten"]["issue_codes"]
    assert "runcomfy_subgraph_support_unknown" in outcome["targets"]["runcomfy"]["issue_codes"]

    # Explicit confirmation clears the uncertainty.
    confirmed = core_evidence(
        uses_subgraphs=True,
        frontend_support={
            "runpod": True,
            "baseten": True,
            "runcomfy": True,
            "comfy_cloud": True,
        },
    )
    confirmed_levels = levels(t.evaluate_target_readiness(confirmed))
    assert confirmed_levels["runpod"] == "low"
    assert confirmed_levels["runcomfy"] == "low"
    assert confirmed_levels["comfy_cloud"] == "low"


# ── 18: target_capability_unknown emission ────────────────────────────────


def test_target_capability_unknown_code_emitted():
    outcome = t.evaluate_target_readiness(native_evidence())
    codes = outcome["targets"]["runcomfy"]["issue_codes"]
    assert "target_capability_unknown" in codes
    minted = {issue["code"] for issue in outcome["issues"]}
    assert "target_capability_unknown" in minted  # once in the shared pool


# ── 19: missing model SHA is not automatic target failure ─────────────────


def test_missing_model_sha_not_automatic_high():
    evidence = core_evidence()  # sha256 None, non-gated
    got = levels(t.evaluate_target_readiness(evidence))
    assert all(level != "high" for level in got.values())
    outcome = t.evaluate_target_readiness(evidence)
    assert "model_hash_unpinned" in outcome["targets"]["local"]["issue_codes"]


# ── 20: unresolved dependency source ──────────────────────────────────────


def test_unresolved_source_applicable_targets_high():
    evidence = core_evidence(
        custom_nodes=[
            {"name": "mystery_pack", "provenance": "unresolved"},
        ]
    )
    got = levels(t.evaluate_target_readiness(evidence))
    assert got["runpod"] == "high"
    assert got["runcomfy"] == "high"
    assert got["comfy_cloud"] == "high"
    assert got["baseten"] == "high"
    assert got["local"] == "medium"   # explainable locally, not a blocker
    assert got["modal"] == "medium"   # deploy bake lacks a pin


# ── 21/22: determinism ────────────────────────────────────────────────────


def test_deterministic_issue_code_order_and_bytes():
    evidence = core_evidence(
        global_issue_codes=["model_hash_unpinned", "local_path_reference"],
        custom_nodes=[
            {"name": "pack_b", "provenance": "unresolved"},
            {"name": "pack_a", "provenance": "declared", "requires_python_install": True},
        ],
        models=[{"name": "m2.safetensors"}, {"name": "m1.safetensors"}],
        absolute_paths=[{"path": "C:\\x\\a.png"}],
        uses_subgraphs=True,
        requires_input_asset=True,
    )
    first = t.evaluate_target_readiness(evidence)
    second = t.evaluate_target_readiness(evidence)
    assert c.canonical_json(first) == c.canonical_json(second)
    for result in first["targets"].values():
        assert result["issue_codes"] == sorted(result["issue_codes"])
        assert len(result["issue_codes"]) == len(set(result["issue_codes"]))
        assert result["advice"] == [a for a in result["advice"] if a]
        assert len(result["advice"]) == len(set(result["advice"]))
    assert [i["code"] for i in first["issues"]] == sorted(
        i["code"] for i in first["issues"]
    ) or True  # pool order follows sort_issues (severity desc, code)
    assert first["issues"] == c.sort_issues(first["issues"])


def test_issue_aggregation_single_object_per_code():
    evidence = core_evidence(
        custom_nodes=[
            {"name": "zeta", "provenance": "unresolved"},
            {"name": "alpha", "provenance": "unresolved"},
            {"name": "mid", "provenance": "unresolved"},
        ]
    )
    outcome = t.evaluate_target_readiness(evidence)
    source_issues = [i for i in outcome["issues"] if i["code"] == "dependency_source_unresolved"]
    assert len(source_issues) == 1
    issue = source_issues[0]
    assert issue["evidence"]["count"] == 3
    assert issue["evidence"]["names"] == ["alpha", "mid", "zeta"]
    assert "alpha, mid, zeta" in issue["message"]


def test_message_name_cap_bounded():
    names = [{"name": "n%02d" % i, "provenance": "unresolved"} for i in range(9)]
    evidence = core_evidence(custom_nodes=names)
    outcome = t.evaluate_target_readiness(evidence)
    issue = next(i for i in outcome["issues"] if i["code"] == "dependency_source_unresolved")
    assert issue["evidence"]["count"] == 9
    assert len(issue["evidence"]["names"]) == 8
    assert "; and 4 more" in issue["message"]
    assert len(c.canonical_json(issue)) < c.EVIDENCE_MAX_CANONICAL_BYTES


# ── 23: purity — stdlib-only imports, no network/provider surface ─────────


def test_no_provider_sdk_or_network_surface():
    source_path = Path(__file__).resolve().parents[1] / "portability_targets.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= {"__future__", "re", "portability_contract"}
    # Token scan targets network/exec surfaces only; target IDS such as
    # "modal"/"runpod" legitimately appear as data vocabulary.
    banned = (
        "requests", "urllib", "httpx", "http.client", "socket", "aiohttp",
        "subprocess", "boto3", "eval(", "exec(", "__import__",
        "urlopen", "getenv", "os.environ",
    )
    text = source_path.read_text(encoding="utf-8")
    lowered = text.lower()
    for token in banned:
        assert token not in lowered, token


# ── 24: rule_version exact ────────────────────────────────────────────────


def test_rule_version_exact():
    assert t.PORTABILITY_RULE_VERSION == "portability-rules-v1"
    assert t.PORTABILITY_RULE_VERSION == c.PORTABILITY_RULE_VERSION
    outcome = t.evaluate_target_readiness(core_evidence())
    assert outcome["rule_version"] == "portability-rules-v1"


# ── Contract composition & validation ─────────────────────────────────────


def test_outcome_composes_into_contract_valid_report():
    evidence = abspath_evidence()  # references global local_path_reference
    outcome = t.evaluate_target_readiness(evidence)
    graph_hash = "b" * 64
    # Composer duty: the global pool must contain every referenced code —
    # target-only mints PLUS canonical objects for supplied global codes.
    global_pool = {
        "local_path_reference": c.build_issue(
            code="local_path_reference",
            severity="medium",
            message="Workflow JSON references host-bound absolute paths.",
            subject="paths",
        ),
        "model_hash_unpinned": c.build_issue(
            code="model_hash_unpinned",
            severity="medium",
            message="Model refs have no sha256.",
            subject="models",
        ),
    }
    for issue in outcome["issues"]:
        global_pool[issue["code"]] = issue
    global_issues = c.sort_issues(list(global_pool.values()))
    counts = {key: 0 for key in c.COUNT_KEYS}
    for issue in global_issues:
        counts[issue["severity"]] += 1
    report = {
        "version_id": "wv_test",
        "graph_hash": graph_hash,
        "risk_level": "medium",
        "rule_version": c.PORTABILITY_RULE_VERSION,
        "issue_count": len(global_issues),
        "counts": counts,
        "issues": global_issues,
        "signals": {},
        "targets": outcome["targets"],
        "environment": {
            "risk_level": "low",
            "issues": [],
            "source": c.ENVIRONMENT_SOURCE_CURRENT_STUDIO,
        },
        "stale": False,
        "invalidation": c.build_invalidation_stamp(),
        "analyzed_at": "2026-08-23T00:00:00+00:00",
    }
    c.validate_report(report)  # must raise nothing


def test_manifest_not_ready_blocks_every_target():
    evidence = core_evidence(manifest_ready=False)
    got = levels(t.evaluate_target_readiness(evidence))
    assert all(level == "high" for level in got.values())
    outcome = t.evaluate_target_readiness(evidence)
    for tid in c.TARGET_IDS:
        assert "manifest_not_ready" in outcome["targets"][tid]["issue_codes"]


def test_evidence_builder_rejects_bad_payloads():
    try:
        t.build_target_evidence(custom_nodes=[{"name": "x", "provenance": "guessed"}])
    except t.TargetEvidenceError:
        pass
    else:
        raise AssertionError("bad provenance must be rejected")
    try:
        t.build_target_evidence(
            custom_nodes=[
                {
                    "name": "x",
                    "provenance": "exact",
                    "target_supported": {"comfy-cloud": True},
                }
            ]
        )
    except t.TargetEvidenceError:
        pass
    else:
        raise AssertionError("alias target keys must be rejected")
    try:
        t.build_target_evidence(models=[{"name": "m", "sha256": "nothex"}])
    except t.TargetEvidenceError:
        pass
    else:
        raise AssertionError("bad sha256 must be rejected")
    try:
        t.evaluate_target_readiness({"custom_nodes": []})
    except t.TargetEvidenceError:
        pass
    else:
        raise AssertionError("partial evidence payload must be rejected")


def test_input_asset_advice_without_risk_inflation():
    evidence = core_evidence(requires_input_asset=True)
    got = levels(t.evaluate_target_readiness(evidence))
    assert got == {
        "local": "low",
        "modal": "low",
        "runpod": "low",
        "runcomfy": "low",
        "comfy_cloud": "low",
        "baseten": "medium",
    }
    outcome = t.evaluate_target_readiness(evidence)
    assert any("payload or S3" in a for a in outcome["targets"]["runpod"]["advice"])


def test_baseten_storage_unknown_surfaces_uncertainty_code_only():
    evidence = core_evidence(baseten_persistent_storage=t.BASETEN_STORAGE_UNKNOWN)
    single = t.evaluate_single_target("baseten", evidence)
    assert single["target"]["risk_level"] == "medium"  # low-severity note only
    assert "baseten_storage_capability_unknown" in single["target"]["issue_codes"]
    assert "target_capability_unknown" in single["target"]["issue_codes"]


def test_signals_has_absolute_path_fallback_conserved():
    evidence = core_evidence(signals={"has_absolute_path": True})
    got = levels(t.evaluate_target_readiness(evidence))
    assert got["local"] == "low"
    for tid in ("runpod", "comfy_cloud"):
        assert got[tid] == "high", tid


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
