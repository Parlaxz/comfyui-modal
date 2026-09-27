"""Self-consistency tests for the Phase-G8 portability fixture corpus.

Validates the corpus against ``studio_workflow_manifest`` and
``portability_contract`` ONLY (no G6/G7 imports). Runs with plain
``python tests/test_portability_fixtures.py`` and is pytest-discoverable.
No network, no GPU, no writes.
"""

import copy
import json
import re
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR))
sys.path.insert(0, str(TESTS_DIR.parent))

import portability_contract as c  # noqa: E402
import portability_fixtures as fx  # noqa: E402
import studio_workflow_manifest as m  # noqa: E402

PLACEHOLDER = "TEST_SECRET_DO_NOT_USE"
CREDENTIAL_FILES = {
    "manifests/credential_like_value.manifest.json",
    "scenarios/credential_like_value.json",
}
PATH_ALLOWLIST = {
    "manifests/absolute_path.manifest.json",
    "scenarios/absolute_path.json",
    "README.md",
}
SANCTIONED_PATHS = {
    "C:\\example\\models\\foo.safetensors",
    "/opt/example/input/foo.png",
    "/opt/example/notes/related-fixtures.md",
}
INVALID_MANIFEST_FILES = {"unknown_root_section.manifest.invalid.json"}

DRIVE_PATH_RE = re.compile(r"\b[A-Za-z]:[\\/]")
POSIX_PATH_RE = re.compile(
    r"(?<![\w:])/(?:opt|home|root|usr|var|tmp|mnt|etc|Users)/[^\s\"']*"
)
SHA256_RE = re.compile(r"[0-9a-f]{64}")
COMMIT40_RE = re.compile(r"[0-9a-f]{40}")

SECRET_PATTERNS = (
    ("modal_token_id", re.compile(r"\bak-[A-Za-z0-9]{10,}")),
    ("modal_secret", re.compile(r"\bas-[A-Za-z0-9]{10,}")),
    ("hf_token", re.compile(r"\bhf_[A-Za-z0-9]{20,}")),
    ("github_pat_classic", re.compile(r"\bghp_[A-Za-z0-9]{30,}")),
    ("github_pat_finegrained", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("openai_style_key", re.compile(r"\bsk-[A-Za-z0-9]{20,}")),
    ("civitai_token", re.compile(r"civitai[-_ ]?token['\"]?[:=][ ]*[A-Za-z0-9]{16,}", re.I)),
)

RISK_VALUE_KEYS = {"risk_level", "expected_target_risk"}
EXTRA_RISK_KEYS = {
    "expected_workflow_portability_risk",
    "expected_environment_reproducibility",
}


# ── helpers ───────────────────────────────────────────────────────────────


def _walk(obj, parent_key=""):
    yield obj, parent_key
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk(v, k)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk(item, parent_key)


def _risk_values(root):
    """Collect (key, value) pairs that claim to be a risk level."""
    found = []
    for node, parent_key in _walk(root):
        if isinstance(node, dict):
            for k, v in node.items():
                if not isinstance(v, str):
                    continue
                if k in RISK_VALUE_KEYS or k in EXTRA_RISK_KEYS or k in c.TARGET_IDS:
                    found.append((k, v))
                elif k.endswith("_risk_level"):
                    found.append((k, v))
        if parent_key == "branch_alternatives" and isinstance(node, dict):
            for k, v in node.items():
                if isinstance(v, str):
                    found.append((k, v))
    return found


def _all_fixture_json():
    for rel in fx.iter_fixture_files(".json"):
        yield rel, fx.load_portability_fixture(rel)


def _valid_manifest_texts():
    for name in sorted(fx.fixture_manifest_names()):
        if name in INVALID_MANIFEST_FILES:
            continue
        yield name, (fx.MANIFEST_DIR / name).read_text(encoding="utf-8")


# ── 1. scenario inventory ─────────────────────────────────────────────────


def test_scenario_ids_unique_and_match_disk():
    ids = fx.scenario_ids()
    assert len(ids) == len(set(ids)), "scenario ids must be unique"
    on_disk = sorted(p.stem for p in fx.SCENARIO_DIR.glob("*.json"))
    assert sorted(ids) == on_disk
    loaded = fx.load_all_scenarios()
    assert sorted(loaded) == sorted(ids)
    for sid, data in loaded.items():
        assert data["scenario_id"] == sid
        assert data["kind"] in ("workflow", "environment", "capability")
        assert data["title"] and data["description"]
        assert isinstance(data["audit_basis"], list) and data["audit_basis"]


# ── 2. every JSON fixture parses ──────────────────────────────────────────


def test_every_json_fixture_parses():
    count = 0
    for rel, data in _all_fixture_json():
        assert isinstance(data, (dict, list)), rel
        count += 1
    assert count >= 45


# ── 3. valid manifests pass parse/validation ─────────────────────────────


def test_valid_manifests_parse_and_validate():
    names = [n for n, _ in _valid_manifest_texts()]
    assert len(names) >= 17
    for name, text in _valid_manifest_texts():
        parsed = m.parse_manifest(text)
        m.validate_manifest(parsed)
        assert parsed["manifest_version"] == 1


def test_unknown_section_fields_permitted_lenient_evolution():
    text = (fx.MANIFEST_DIR / "unknown_section_fields.manifest.json").read_text(encoding="utf-8")
    parsed = m.parse_manifest(text)
    assert parsed["workflow"]["future_extension_field"]["note"].startswith("unknown")
    assert parsed["metadata"]["future_metadata_key"] == ["a", "b"]


def test_unknown_root_section_rejected():
    text = (fx.MANIFEST_DIR / "unknown_root_section.manifest.invalid.json").read_text(
        encoding="utf-8")
    try:
        m.parse_manifest(text)
    except m.ManifestValidationError as exc:
        assert any("unknown root section" in msg for msg in exc.issues)
    else:
        raise AssertionError("unknown root section must be rejected")


# ── 4. not-ready fixture is valid JSON but readiness-fails ───────────────


def test_not_ready_fixture_valid_but_readiness_fails():
    man = fx.fixture_manifest("manifest_not_ready")
    m.validate_manifest(man)
    readiness = m.check_readiness(man)
    assert readiness["ready"] is False
    assert len(readiness["missing"]) == 1
    assert "fixture_nohash_model.safetensors" in readiness["missing"][0]
    desc = fx.load_scenario("manifest_not_ready")
    assert desc["manifest_readiness_expected"] == {"ready": False, "missing_count": 1}


def test_descriptor_readiness_expectations_match_reality():
    for sid in fx.WORKFLOW_SCENARIO_IDS:
        desc = fx.load_scenario(sid)
        man = fx.fixture_manifest(sid)
        actual = m.check_readiness(man)
        expected = desc["manifest_readiness_expected"]
        assert expected["ready"] == actual["ready"], sid
        assert expected["missing_count"] == len(actual["missing"]), sid


# ── 5. malformed fixture separately malformed ────────────────────────────


def test_malformed_fixture_is_invalid_json_distinct_from_structural():
    raw = fx.load_raw_text("malformed_manifest.txt")
    try:
        json.loads(raw)
    except json.JSONDecodeError:
        pass
    else:
        raise AssertionError("malformed_manifest.txt must not be valid JSON")
    try:
        m.parse_manifest(raw)
    except m.ManifestValidationError as exc:
        assert any(msg.startswith("invalid JSON") for msg in exc.issues)
    else:
        raise AssertionError("parse_manifest must reject invalid JSON")


# ── 6. target ids use exact G5 vocabulary ────────────────────────────────


def test_target_ids_exact_vocabulary_and_no_banned_aliases():
    matrix = fx.fixture_expected("target_matrix")
    for characteristic, row in matrix["characteristics"].items():
        assert set(row) == set(c.TARGET_IDS), characteristic
    for rel, data in _all_fixture_json():
        for node, _parent in _walk(data):
            if isinstance(node, dict):
                for key in node:
                    assert key not in c.BANNED_TARGET_ALIASES, (rel, key)
                for tid in c.TARGET_IDS:
                    if tid in node:
                        assert c.normalize_target_id(tid) == tid


# ── 7. risk values use exact lowercase vocabulary ────────────────────────


def test_risk_values_lowercase_vocabulary():
    checked = 0
    for rel, data in _all_fixture_json():
        for key, value in _risk_values(data):
            assert value in c.RISK_LEVELS, (rel, key, value)
            assert value == value.lower()
            checked += 1
    assert checked >= 40


# ── 8. environment HIGH distinct from workflow risk expectation ──────────


def test_environment_high_independent_of_workflow_risk():
    ev = fx.fixture_evidence("environment_repro_high")
    assert ev["source"] == c.ENVIRONMENT_SOURCE_CURRENT_STUDIO
    assert ev["expected_environment_risk_level"] == "high"
    assert ev["does_not_dictate"]["workflow_portability_risk"] == "independent_dimension"
    assert ev["does_not_dictate"]["policy"] == c.POLICY_ENVIRONMENT_ISOLATION
    assert "never_forces" in c.POLICY_ENVIRONMENT_ISOLATION
    core_desc = fx.load_scenario("core_clean")
    assert core_desc["expected"]["risk_level_hint_nonnormative"] == "low"
    assert ev["expected_environment_risk_level"] != \
        core_desc["expected"]["risk_level_hint_nonnormative"]


def test_environment_evidence_covers_all_frozen_env_codes():
    ev = fx.fixture_evidence("environment_repro_high")
    assert set(ev["expected_environment_issue_codes"]) == set(c.ENVIRONMENT_ISSUE_CODES)
    facts = ev["facts"]
    assert facts["comfyui_core_remote"]["pinned"] is True
    assert facts["torch_stack"]["pinned"] is False
    assert facts["base_image"]["digest_pinned"] is False
    assert facts["custom_node_provenance"]["provenance_complete"] is False
    assert facts["plugin_worktree"]["dirty"] is True
    assert facts["comfyui_core_local"]["local_patch_divergence"] is True
    assert facts["model_hash_coverage"]["populated_fraction"] == 0.0


# ── 9. current_corpus_shape MEDIUM + HIGH reconciliation ─────────────────


def test_current_corpus_shape_medium_with_environment_high():
    exp = fx.fixture_expected("current_corpus_shape")
    assert exp["workflow_portability_risk"] == "medium"
    assert exp["environment_reproducibility"] == "high"
    assert exp["coexistence"]["policy"] == c.POLICY_ENVIRONMENT_ISOLATION
    desc = fx.load_scenario("current_corpus_shape")
    assert desc["expected"]["signals"] == exp["expected_signals"]
    assert set(desc["expected"]["issue_codes"]) == set(exp["expected_issue_codes"])
    ev = fx.fixture_evidence("current_corpus_shape")
    assert ev["expected_workflow_portability_risk"] == "medium"
    assert ev["expected_environment_reproducibility"] == "high"


# ── 10/11. invalidation stamps ───────────────────────────────────────────


def test_all_invalidation_stamps_have_exact_fields():
    stamps = fx.load_invalidation_stamps()
    assert len(stamps) == 9
    for name, stamp in stamps.items():
        assert set(stamp) == set(c.INVALIDATION_FIELDS), name
        assert c.invalidation_stamp_issues(stamp) == [], name


def test_null_stamp_explicit_and_conservatively_stale():
    semantics = fx.load_invalidation_semantics()
    stamps = fx.load_invalidation_stamps()
    null_info = semantics["null_variant"]
    stamp = stamps[null_info["stamp"]]
    nulled = null_info["nulled_fields"]
    assert any(stamp[f] is None for f in nulled)
    reference = stamps["stamp_a"]
    mismatches = c.invalidation_mismatches(reference, stamp)
    assert set(nulled) <= set(mismatches)
    assert not c.invalidation_stamps_match(reference, stamp)
    assert not c.invalidation_stamps_match(stamp, stamp), \
        "null on either side forces conservative recompute"


def test_invalidation_semantics_reusable_vs_stale():
    semantics = fx.load_invalidation_semantics()
    stamps = fx.load_invalidation_stamps()
    for left, right in semantics["reusable_pairs"]:
        assert c.invalidation_stamps_match(stamps[left], stamps[right])
        assert c.invalidation_mismatches(stamps[left], stamps[right]) == []
    for name, expected_fields in semantics["stale_variants"].items():
        mismatches = c.invalidation_mismatches(stamps["stamp_a"], stamps[name])
        assert mismatches == expected_fields, name
        assert not c.invalidation_stamps_match(stamps["stamp_a"], stamps[name])


# ── 12. no real/local filesystem paths outside sanctioned fixtures ───────


def test_no_local_filesystem_paths_outside_synthetic_path_scenario():
    offenders = []
    for path in sorted(fx.FIXTURE_ROOT.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(fx.FIXTURE_ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        hits = DRIVE_PATH_RE.findall(text) + POSIX_PATH_RE.findall(text)
        if hits and rel not in PATH_ALLOWLIST:
            offenders.append((rel, hits[:3]))
    assert offenders == []
    man = fx.fixture_manifest("absolute_path")
    strings = {node for node, _ in _walk(man) if isinstance(node, str)}
    assert {
        "C:\\example\\models\\foo.safetensors",
        "/opt/example/input/foo.png",
    } <= strings
    assert any("/opt/example/notes/related-fixtures.md" in s for s in strings), \
        "inert note-text path must appear as data"
    desc = fx.load_scenario("absolute_path")
    cls = desc["classification"]
    assert set(cls["functional_paths"]) <= SANCTIONED_PATHS
    assert set(cls["inert_note_paths"]) <= SANCTIONED_PATHS
    assert cls["functional_paths"] and cls["inert_note_paths"]


# ── 13/14. secrets ───────────────────────────────────────────────────────


def test_corpus_is_secret_free():
    for path in sorted(fx.FIXTURE_ROOT.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(fx.FIXTURE_ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        for label, pattern in SECRET_PATTERNS:
            hit = pattern.search(text)
            assert hit is None, (rel, label, hit.group(0) if hit else "")


def test_placeholder_only_in_credential_fixture():
    for path in sorted(fx.FIXTURE_ROOT.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(fx.FIXTURE_ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        if PLACEHOLDER in text:
            assert rel in CREDENTIAL_FILES, "placeholder leaked into %s" % rel
    for rel in CREDENTIAL_FILES:
        assert PLACEHOLDER in fx.load_portability_fixture(rel).__str__() or \
            PLACEHOLDER in (fx.FIXTURE_ROOT / rel).read_text(encoding="utf-8")


def test_credential_fixture_only_contains_synthetic_placeholder():
    man = fx.fixture_manifest("credential_like_value")
    cred_keys = {"api_key", "token", "authorization", "password"}
    seen = 0
    for node, parent_key in _walk(man):
        if isinstance(node, dict) and "widget" in node:
            if node.get("name") in cred_keys:
                assert node["widget"]["value"] == PLACEHOLDER, node.get("name")
                seen += 1
    assert seen == 4
    desc = fx.load_scenario("credential_like_value")
    cls = desc["classification"]
    assert cls["credential_placeholder"] == PLACEHOLDER
    assert set(cls["credential_shaped_keys"]) == cred_keys
    assert cls["real_secrets_present"] is False


# ── 15/16. functional vs inert distinction metadata ─────────────────────


def test_note_path_and_url_fixtures_distinguish_functional_from_inert():
    abs_cls = fx.load_scenario("absolute_path")["classification"]
    assert set(abs_cls["functional_paths"]).isdisjoint(abs_cls["inert_note_paths"])
    ep_cls = fx.load_scenario("external_endpoint")["classification"]
    assert set(ep_cls["functional_endpoints"]).isdisjoint(ep_cls["inert_note_urls"])
    assert ep_cls["functional_endpoints"] == ["https://example.invalid/api/fixture-endpoint"]
    assert ep_cls["inert_note_urls"] == ["https://example.invalid/docs/fixture-readme"]
    ep_man = fx.fixture_manifest("external_endpoint")
    blob = json.dumps(ep_man)
    assert "https://example.invalid/api/fixture-endpoint" in blob
    assert "https://example.invalid/docs/fixture-readme" in blob


# ── 17. subgraph fixture carries definitions.subgraphs ───────────────────


def test_subgraph_fixture_contains_definitions_subgraphs():
    man = fx.fixture_manifest("subgraph_frontend")
    subs = man["workflow"]["graph"]["definitions"]["subgraphs"]
    assert isinstance(subs, list) and subs
    corpus = fx.fixture_manifest("current_corpus_shape")
    assert corpus["workflow"]["graph"]["definitions"]["subgraphs"]
    desc = fx.load_scenario("subgraph_frontend")
    assert desc["expected"]["signals"]["uses_subgraphs"] is True
    notes = " ".join(desc["expected"]["semantic_notes"])
    assert "target-sensitive" in notes
    assert c.POLICY_SUBGRAPHS == "target_sensitive_not_global_blocker"


# ── 18. input asset fixture reference truth ──────────────────────────────


def test_input_asset_fixture_reference_metadata_only():
    man = fx.fixture_manifest("input_asset_required")
    assets = man["assets"]
    assert len(assets) == 1
    asset = assets[0]
    assert asset["filename"] == "fixture_input.png"
    assert "/" not in asset["filename"] and "\\" not in asset["filename"]
    assert SHA256_RE.fullmatch(asset["sha256"])
    assert isinstance(asset["size"], int) and asset["size"] > 0
    assert asset["mime_type"] == "image/png"
    blob = json.dumps(man).lower()
    assert "base64" not in blob
    desc = fx.load_scenario("input_asset_required")
    assert desc["expected"]["signals"]["requires_input_asset"] is True
    assert desc["classification"]["asset_travels_separately"] is True
    assert desc["classification"]["contains_asset_bytes"] is False


# ── 19/20. provenance fixtures ───────────────────────────────────────────


def test_exact_provenance_fixture_has_revision():
    man = fx.fixture_manifest("custom_exact")
    entry = man["custom_nodes"][0]
    assert COMMIT40_RE.fullmatch(entry["revision"])
    assert entry["repo_url"].startswith("https://example.invalid/")
    assert "FixtureExactNode" in entry["classes"]
    desc = fx.load_scenario("custom_exact")
    assert desc["expected"]["provenance_quality"] == "exact"


def test_unresolved_provenance_fixture_lacks_authoritative_source():
    man = fx.fixture_manifest("unresolved_node")
    graph_classes = {n["type"] for n in man["workflow"]["graph"]["nodes"]}
    covered = set()
    for entry in man["custom_nodes"]:
        covered.update(entry.get("classes", []))
    assert "FixtureGhostNode" in graph_classes
    assert "FixtureGhostNode" not in covered
    desc = fx.load_scenario("unresolved_node")
    assert desc["expected"]["provenance_quality"] == "unresolved"
    assert desc["expected"]["signals"]["has_unresolved_node_type"] is True
    assert desc["expected"]["signals"]["unresolved_node_count"] == 1


def test_declared_and_inferred_provenance_levels_represented():
    declared = fx.load_scenario("custom_unpinned")
    assert declared["expected"]["provenance_quality"] == "declared"
    corpus_man = fx.fixture_manifest("current_corpus_shape")
    qualities = {e.get("provenance_quality") for e in corpus_man["custom_nodes"]}
    assert {"exact", "declared", "inferred"} <= qualities
    fallback = [e for e in corpus_man["custom_nodes"]
                if e["provenance_quality"] == "inferred"]
    assert fallback and fallback[0]["repo_url"].endswith("/comfyui-host-fallback")


# ── 21/22. model hash fixtures ───────────────────────────────────────────


def test_model_hash_fixtures_use_valid_fake_hex():
    for name, _text in _valid_manifest_texts():
        man = fx.fixture_manifest(name.replace(".manifest.json", ""))
        for rec in man.get("models", []):
            if "sha256" in rec and rec["sha256"] is not None:
                assert SHA256_RE.fullmatch(rec["sha256"]), (name, rec["filename"])
    core = fx.fixture_manifest("core_clean")
    assert SHA256_RE.fullmatch(core["models"][0]["sha256"])


def test_model_missing_hash_fixture_intentionally_null():
    man = fx.fixture_manifest("model_hash_missing")
    assert len(man["models"]) == 1
    assert man["models"][0].get("sha256") is None
    missing = m.check_readiness(man)["missing"]
    assert missing == ["models: fixture_unhashed_model.safetensors (missing hash)"]
    desc = fx.load_scenario("model_hash_missing")
    assert desc["expected"]["signals"]["model_hash_pinned"] is False


# ── 23. canonical serialization stable + golden ──────────────────────────


def test_canonical_serialization_stable_and_golden_hashes_match():
    golden = fx.golden_manifest_hashes()
    for name, text in _valid_manifest_texts():
        direct = json.loads(text)
        parsed = m.parse_manifest(text)
        first = m.canonical_json(parsed)
        reparsed = m.parse_manifest(first)
        assert m.canonical_json(reparsed) == first, name
        assert first == c.canonical_json(direct), name
        assert golden[name] == m.manifest_hash(parsed), name
        pretty = json.dumps(direct, indent=2, sort_keys=True,
                            ensure_ascii=False) + "\n"
        assert text == pretty, "fixture %s not stored deterministically" % name
    for sid in fx.WORKFLOW_SCENARIO_IDS:
        desc = fx.load_scenario(sid)
        fname = desc["manifest_file"].split("/")[-1]
        assert desc["manifest_sha256_canonical"] == golden[fname], sid


# ── 24. identity hash stable under allowed metadata variance ─────────────


def test_manifest_identity_hash_stable_under_metadata_variance():
    man = fx.fixture_manifest("core_clean")
    assert man["metadata"]["exported_at"]
    variant = copy.deepcopy(man)
    variant["metadata"]["exported_at"] = "2030-01-01T00:00:00+00:00"
    variant["metadata"]["captured_at"] = "2030-01-02T00:00:00+00:00"
    assert m.manifest_hash(variant, include_metadata=False) == \
        m.manifest_hash(man, include_metadata=False)
    assert m.manifest_hash(variant) != m.manifest_hash(man)


# ── descriptor well-formedness (contract vocabularies) ───────────────────


def test_descriptors_use_frozen_signal_issue_and_provenance_vocabularies():
    for sid in fx.WORKFLOW_SCENARIO_IDS:
        desc = fx.load_scenario(sid)
        exp = desc["expected"]
        normalized = c.normalize_signals(exp["signals"])
        assert normalized == exp["signals"], sid
        for code in exp["issue_codes"]:
            assert code in c.FOUNDATIONAL_ISSUE_CODES, (sid, code)
        if "provenance_quality" in exp:
            assert exp["provenance_quality"] in c.PROVENANCE_QUALITY_VALUES
        if "risk_level_hint_nonnormative" in exp:
            assert exp["risk_level_hint_nonnormative"] in c.RISK_LEVELS


# ── target matrix consistency ────────────────────────────────────────────


def test_target_matrix_matches_g3_characteristic_evidence():
    matrix = fx.fixture_expected("target_matrix")
    assert set(matrix["characteristics"]) == {
        "core_clean", "popular_custom", "native_build_dependency",
        "absolute_path", "private_model",
    }
    for characteristic, row in matrix["characteristics"].items():
        ev = fx.fixture_evidence("target_characteristic_%s" % characteristic)
        assert ev["expected_target_risk"] == row, characteristic
        assert ev["capability_evidence"].keys() == row.keys(), characteristic
    assert matrix["characteristics"]["core_clean"] == {
        "local": "low", "modal": "low", "runpod": "low",
        "runcomfy": "low", "comfy_cloud": "low", "baseten": "medium",
    }
    assert matrix["characteristics"]["native_build_dependency"]["runcomfy"] == "unknown"
    assert matrix["characteristics"]["absolute_path"]["local"] == "low"
    assert matrix["characteristics"]["absolute_path"]["comfy_cloud"] == "high"
    assert matrix["characteristics"]["private_model"]["comfy_cloud"] == "high"


def test_unknown_capability_rule_matches_evidence():
    matrix = fx.fixture_expected("target_matrix")
    rule = matrix["unknown_capability_rule"]
    ev = fx.fixture_evidence("unknown_target_capability")
    assert rule["target_id"] == ev["target_id"] == "runcomfy"
    assert ev["capability_value"] == "unknown"
    assert ev["expected"]["issue_code"] == "target_capability_unknown"
    assert ev["expected"]["risk_level"] == "unknown"
    assert rule["expected_issue_code"] in c.FOUNDATIONAL_ISSUE_CODES


def test_branch_alternatives_documented_for_dependent_cells():
    matrix = fx.fixture_expected("target_matrix")
    alts = matrix["branch_alternatives"]
    assert alts["popular_custom"] == {"comfy_cloud_off_curated_list": "high"}
    assert alts["private_model"] == {"comfy_cloud_catalog_hit": "low"}
    pop_ev = fx.fixture_evidence("target_characteristic_popular_custom")
    priv_ev = fx.fixture_evidence("target_characteristic_private_model")
    assert pop_ev["branch_alternatives"] == alts["popular_custom"]
    assert priv_ev["branch_alternatives"] == alts["private_model"]


# ── loader behavior ──────────────────────────────────────────────────────


def test_loader_rejects_path_escape_and_missing_files():
    try:
        fx.load_portability_fixture("../../portability_contract.py")
    except ValueError:
        pass
    else:
        raise AssertionError("path escape must be rejected")
    try:
        fx.load_scenario("does_not_exist")
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("missing fixture must raise")


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
        except Exception as exc:  # noqa: BLE001 - harness visibility
            failed += 1
            print("ERROR %s: %r" % (name, exc))
    print("%d/%d passed" % (len(fns) - failed, len(fns)))
    sys.exit(1 if failed else 0)
