"""Deterministic loader for the Phase-G8 portability fixture corpus.

Pure path-relative readers over ``tests/fixtures/portability/``. No hidden
machine-state behavior, no environment lookups, no writes. Later G6/G7/G9
lanes consume fixtures through this module instead of re-deriving paths.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TESTS_DIR = Path(__file__).resolve().parent
FIXTURE_ROOT = TESTS_DIR / "fixtures" / "portability"

SCENARIO_DIR = FIXTURE_ROOT / "scenarios"
MANIFEST_DIR = FIXTURE_ROOT / "manifests"
EVIDENCE_DIR = FIXTURE_ROOT / "evidence"
EXPECTED_DIR = FIXTURE_ROOT / "expected"
INVALIDATION_DIR = FIXTURE_ROOT / "invalidation"
RAW_DIR = FIXTURE_ROOT / "raw"

# Frozen scenario ids (G8). Order is the canonical inventory order.
SCENARIO_IDS = (
    "core_clean",
    "custom_unpinned",
    "custom_exact",
    "unresolved_node",
    "model_hash_missing",
    "model_extraction_gap",
    "input_asset_required",
    "absolute_path",
    "external_endpoint",
    "subgraph_frontend",
    "private_model",
    "native_build_dependency",
    "manifest_not_ready",
    "credential_like_value",
    "popular_custom",
    "current_corpus_shape",
    "environment_repro_high",
    "unknown_target_capability",
)

WORKFLOW_SCENARIO_IDS = tuple(
    sid for sid in SCENARIO_IDS
    if sid not in ("environment_repro_high", "unknown_target_capability")
)

TARGET_CHARACTERISTIC_EVIDENCE_IDS = (
    "target_characteristic_core_clean",
    "target_characteristic_popular_custom",
    "target_characteristic_native_build_dependency",
    "target_characteristic_absolute_path",
    "target_characteristic_private_model",
)


def load_portability_fixture(relpath: str) -> Any:
    """Load any fixture file relative to the portability fixture root.

    JSON files (.json) are parsed; anything else is returned as text.
    """
    path = (FIXTURE_ROOT / relpath).resolve()
    if FIXTURE_ROOT.resolve() not in path.parents:
        raise ValueError("fixture relpath escapes fixture root: %r" % relpath)
    if not path.is_file():
        raise FileNotFoundError("fixture not found: %s" % path)
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    return path.read_text(encoding="utf-8")


def scenario_ids() -> tuple:
    """Frozen scenario id tuple."""
    return SCENARIO_IDS


def load_scenario(name: str) -> dict:
    """Load one scenario descriptor from scenarios/<name>.json."""
    return load_portability_fixture("scenarios/%s.json" % name)


def load_all_scenarios() -> dict:
    """All scenario descriptors keyed by scenario_id."""
    out = {}
    for name in SCENARIO_IDS:
        data = load_scenario(name)
        out[data["scenario_id"]] = data
    return out


def manifest_filename(name: str) -> str:
    return "%s.manifest.json" % name


def fixture_manifest(name: str) -> dict:
    """Parsed JSON dict of manifests/<name>.manifest.json (no validation here)."""
    return load_portability_fixture("manifests/" + manifest_filename(name))


def fixture_manifest_names() -> list:
    return sorted(p.name for p in MANIFEST_DIR.glob("*.json"))


def fixture_evidence(name: str) -> dict:
    """Parsed evidence file evidence/<name>.evidence.json."""
    return load_portability_fixture("evidence/%s.evidence.json" % name)


def fixture_expected(name: str) -> dict:
    """Parsed expectation file expected/<name>.expected.json."""
    return load_portability_fixture("expected/%s.expected.json" % name)


def golden_manifest_hashes() -> dict:
    """Manifest filename -> sha256 over canonical bytes (incl. metadata)."""
    return fixture_expected("manifest_golden_hashes")["hashes"]


def load_invalidation_stamps() -> dict:
    """All invalidation stamps keyed by stamp name."""
    return load_portability_fixture("invalidation/stamps.json")["stamps"]


def load_invalidation_semantics() -> dict:
    return load_portability_fixture("invalidation/semantics.expected.json")


def load_raw_text(name: str) -> str:
    """Raw text fixture raw/<name> (e.g. malformed_manifest.txt)."""
    return load_portability_fixture("raw/" + name)


def iter_fixture_files(suffix=".json"):
    """Yield repo-relative-ish paths (relative to FIXTURE_ROOT) for iteration."""
    for path in sorted(FIXTURE_ROOT.rglob("*" + suffix)):
        if path.is_file():
            yield path.relative_to(FIXTURE_ROOT).as_posix()
