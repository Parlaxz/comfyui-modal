"""Tests for tools/v2_control/registry.py (Batch E32, Agent A).

Stdlib only; uses the real config/v2/flag_registry.toml for integration-style
coverage and tmp_path for isolated registry files.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from tools.v2_control.registry import (
    FLAG_NAME_RE,
    AuditReport,
    FlagDef,
    FlagRegistry,
)
from tools.v2_control.errors import FlagError

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO_ROOT / "config" / "v2" / "flag_registry.toml"


@pytest.fixture(scope="module")
def real_registry() -> FlagRegistry:
    registry = FlagRegistry(REGISTRY_PATH)
    registry.load()
    return registry


# ── real TOML parse ────────────────────────────────────────────────────────


def test_real_toml_is_parseable_by_tomllib():
    with REGISTRY_PATH.open("rb") as handle:
        data = tomllib.load(handle)
    assert data["schema_version"] == 1
    assert isinstance(data["flag"], list)
    assert len(data["flag"]) >= 80


def test_real_registry_loads(real_registry):
    names = real_registry.registered_names()
    assert len(names) >= 80
    assert names == sorted(names)
    # A few anchors from each lifecycle group.
    assert "COMFYMODAL_V2_PNG_COMPRESS_LEVEL" in names
    assert "COMFYMODAL_V2_UNET_FASTSAFETENSORS" in names
    assert "V2_BENCHMARK_MODE" in names
    assert "V2_E28_CONDITIONING_NONCE" in names
    assert "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE" in names


def test_real_registry_flag_metadata(real_registry):
    cast_once = real_registry.get("COMFYMODAL_V2_CLIP_FP32_CAST_ONCE")
    assert cast_once is not None
    assert cast_once.type == "bool"
    assert cast_once.consumed_at == "module_import"
    assert cast_once.change_requires == "deploy"
    assert cast_once.default == "0"
    assert "allowlisted" in cast_once.description

    png = real_registry.get("COMFYMODAL_V2_PNG_COMPRESS_LEVEL")
    assert png.min == 1 and png.max == 6

    mode = real_registry.get("V2_BENCHMARK_MODE")
    assert mode.enum_values is not None
    assert "snapshot_restore_only" in mode.enum_values
    assert mode.default == "snapshot_restore_only"


def test_nonce_regex_metadata(real_registry):
    nonce = real_registry.get("V2_E28_CONDITIONING_NONCE")
    assert nonce is not None
    assert nonce.regex == "^[0-9A-Za-z-]+$"


# ── type validation (bool) ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value",
    ["1", "0", "true", "false", "yes", "no", "on", "off", "TRUE", "Off", "Yes"],
)
def test_bool_accepts_all_spellings(value):
    flag = FlagDef(
        name="TEST_BOOL", type="bool", default="0", consumed_at="request",
        change_requires="run", owner="test", description="d",
    )
    assert flag.validate_value(value) in ("1", "0")


def test_bool_normalizes():
    flag = FlagDef(
        name="TEST_BOOL", type="bool", default="0", consumed_at="request",
        change_requires="run", owner="test", description="d",
    )
    assert flag.validate_value("true") == "1"
    assert flag.validate_value("off") == "0"
    assert flag.validate_value("1") == "1"
    assert flag.validate_value("0") == "0"


@pytest.mark.parametrize("value", ["2", "maybe", "", "True-ish", "1.0"])
def test_bool_rejects_garbage(value):
    flag = FlagDef(
        name="TEST_BOOL", type="bool", default="0", consumed_at="request",
        change_requires="run", owner="test", description="d",
    )
    with pytest.raises(FlagError, match="boolean"):
        flag.validate_value(value)


# ── type validation (int / min / max) ──────────────────────────────────────


def test_int_accepts_and_normalizes():
    flag = FlagDef(
        name="TEST_INT", type="int", default="3", consumed_at="request",
        change_requires="run", owner="test", description="d", min=1, max=6,
    )
    assert flag.validate_value("3") == "3"
    assert flag.validate_value(" 004 ") == "4"


def test_int_min_max():
    flag = FlagDef(
        name="TEST_INT", type="int", default="3", consumed_at="request",
        change_requires="run", owner="test", description="d", min=1, max=6,
    )
    assert flag.validate_value("1") == "1"
    assert flag.validate_value("6") == "6"
    with pytest.raises(FlagError, match="below minimum"):
        flag.validate_value("0")
    with pytest.raises(FlagError, match="above maximum"):
        flag.validate_value("7")


@pytest.mark.parametrize("value", ["abc", "3.5", "", "0x10"])
def test_int_rejects_non_int(value):
    flag = FlagDef(
        name="TEST_INT", type="int", default="3", consumed_at="request",
        change_requires="run", owner="test", description="d",
    )
    with pytest.raises(FlagError, match="integer"):
        flag.validate_value(value)


def test_float_accepts_and_normalizes():
    flag = FlagDef(
        name="TEST_FLOAT", type="float", default="35.0", consumed_at="harness",
        change_requires="run", owner="test", description="d",
    )
    assert float(flag.validate_value("35")) == 35.0
    assert float(flag.validate_value("1e3")) == 1000.0


@pytest.mark.parametrize("value", ["abc", "", "nan", "inf"])
def test_float_rejects_garbage(value):
    flag = FlagDef(
        name="TEST_FLOAT", type="float", default="35.0", consumed_at="harness",
        change_requires="run", owner="test", description="d",
    )
    with pytest.raises(FlagError):
        flag.validate_value(value)


# ── type validation (enum) ─────────────────────────────────────────────────


def test_enum_accepts_member():
    flag = FlagDef(
        name="TEST_ENUM", type="enum", default="late", consumed_at="restore",
        change_requires="deploy", owner="test", description="d",
        enum_values=("late", "sampling_end"),
    )
    assert flag.validate_value("sampling_end") == "sampling_end"


def test_enum_rejects_unknown():
    flag = FlagDef(
        name="TEST_ENUM", type="enum", default="late", consumed_at="restore",
        change_requires="deploy", owner="test", description="d",
        enum_values=("late", "sampling_end"),
    )
    with pytest.raises(FlagError, match="enum"):
        flag.validate_value("early")


# ── type validation (string / regex / json / path) ─────────────────────────


def test_string_regex_matches():
    flag = FlagDef(
        name="TEST_NONCE", type="string", default="", consumed_at="harness",
        change_requires="run", owner="test", description="d",
        regex="^[0-9A-Za-z-]+$",
    )
    assert flag.validate_value("abc-123") == "abc-123"


@pytest.mark.parametrize("value", ["has space", "under_score!", "a.b"])
def test_string_regex_rejects(value):
    flag = FlagDef(
        name="TEST_NONCE", type="string", default="", consumed_at="harness",
        change_requires="run", owner="test", description="d",
        regex="^[0-9A-Za-z-]+$",
    )
    with pytest.raises(FlagError, match="does not match"):
        flag.validate_value(value)


def test_string_regex_empty_is_unset_sentinel():
    # Empty string is the "unset" sentinel and is never regex-checked, which
    # is why the registry's nonce defaults ("") can carry a `+` pattern.
    flag = FlagDef(
        name="TEST_NONCE", type="string", default="", consumed_at="harness",
        change_requires="run", owner="test", description="d",
        regex="^[0-9A-Za-z-]+$",
    )
    assert flag.validate_value("") == ""


def test_path_nonempty():
    flag = FlagDef(
        name="TEST_PATH", type="path", default="/tmp/x", consumed_at="restore",
        change_requires="deploy", owner="test", description="d",
    )
    assert flag.validate_value("some/dir") == "some/dir"
    with pytest.raises(FlagError, match="non-empty"):
        flag.validate_value("")


def test_json_valid_and_invalid():
    flag = FlagDef(
        name="TEST_JSON", type="json", default="{}", consumed_at="restore",
        change_requires="deploy", owner="test", description="d",
    )
    assert flag.validate_value('{"a": [1, 2]}') == '{"a": [1, 2]}'
    assert flag.validate_value("null") == "null"
    with pytest.raises(FlagError, match="JSON"):
        flag.validate_value("{not json")


# ── aliases ────────────────────────────────────────────────────────────────


def test_alias_resolves(tmp_path):
    path = tmp_path / "reg.toml"
    path.write_text(
        'schema_version = 1\n'
        '[[flag]]\n'
        'name = "COMFYMODAL_V2_ALIASED"\n'
        'type = "bool"\n'
        'default = "0"\n'
        'consumed_at = "request"\n'
        'change_requires = "run"\n'
        'owner = "test"\n'
        'description = "d"\n'
        'aliases = ["OLD_ALIAS_NAME", "LEGACY_NAME"]\n',
        encoding="utf-8",
    )
    registry = FlagRegistry(path)
    registry.load()
    assert registry.get("OLD_ALIAS_NAME").name == "COMFYMODAL_V2_ALIASED"
    assert registry.get("LEGACY_NAME").name == "COMFYMODAL_V2_ALIASED"
    assert registry.get("COMFYMODAL_V2_ALIASED").name == "COMFYMODAL_V2_ALIASED"


# ── deprecation metadata ───────────────────────────────────────────────────


def test_deprecation_metadata(tmp_path):
    path = tmp_path / "reg.toml"
    path.write_text(
        'schema_version = 1\n'
        '[[flag]]\n'
        'name = "COMFYMODAL_V2_OLD_DEP"\n'
        'type = "bool"\n'
        'default = "0"\n'
        'consumed_at = "restore"\n'
        'change_requires = "deploy"\n'
        'owner = "test"\n'
        'description = "deprecated demo"\n'
        'deprecated = true\n',
        encoding="utf-8",
    )
    registry = FlagRegistry(path)
    registry.load()
    flag = registry.get("COMFYMODAL_V2_OLD_DEP")
    assert flag.deprecated is True


# ── name syntax validation ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    ["COMFYMODAL_V2_OK", "V2_BENCHMARK_RUNS", "A1_B", "ABC"],
)
def test_validate_name_accepts(name):
    assert FlagRegistry.validate_name(name) == name
    assert FLAG_NAME_RE.fullmatch(name)


@pytest.mark.parametrize(
    "name",
    [
        "", "a", "lower", "1LEADING_DIGIT", "A B", "A-B", "A.B", "A" * 129,
        "A" * 200, "HAS\nNEWLINE", "A_" * 70,
    ],
)
def test_validate_name_rejects(name):
    with pytest.raises(FlagError):
        FlagRegistry.validate_name(name)
    assert not FLAG_NAME_RE.fullmatch(name)


def test_validate_name_min_length_two_chars():
    # The regex requires at least 2 chars: [A-Z] then {1,127} more.
    assert FlagRegistry.validate_name("AB") == "AB"
    with pytest.raises(FlagError):
        FlagRegistry.validate_name("A")


# ── bad registry files ─────────────────────────────────────────────────────


def test_bad_toml_raises_flag_error(tmp_path):
    path = tmp_path / "bad.toml"
    path.write_text("schema_version = [unclosed", encoding="utf-8")
    with pytest.raises(FlagError, match="TOML"):
        FlagRegistry(path).load()


def test_missing_registry_raises(tmp_path):
    with pytest.raises(FlagError, match="not found"):
        FlagRegistry(tmp_path / "nope.toml").load()


def test_wrong_schema_version_raises(tmp_path):
    path = tmp_path / "reg.toml"
    path.write_text('schema_version = 99\n[[flag]]\nname = "X"\n', encoding="utf-8")
    with pytest.raises(FlagError, match="schema_version"):
        FlagRegistry(path).load()


def test_invalid_registered_default_raises(tmp_path):
    path = tmp_path / "reg.toml"
    path.write_text(
        'schema_version = 1\n'
        '[[flag]]\n'
        'name = "BAD_DEFAULT"\n'
        'type = "int"\n'
        'default = "not-an-int"\n'
        'consumed_at = "request"\n'
        'change_requires = "run"\n'
        'owner = "test"\n'
        'description = "d"\n',
        encoding="utf-8",
    )
    with pytest.raises(FlagError, match="default"):
        FlagRegistry(path).load()


def test_duplicate_flag_rejected(tmp_path):
    path = tmp_path / "reg.toml"
    path.write_text(
        'schema_version = 1\n'
        '[[flag]]\nname = "DUP"\ntype = "bool"\ndefault = "0"\n'
        'consumed_at = "request"\nchange_requires = "run"\n'
        'owner = "t"\ndescription = "d"\n'
        '[[flag]]\nname = "DUP"\ntype = "bool"\ndefault = "0"\n'
        'consumed_at = "request"\nchange_requires = "run"\n'
        'owner = "t"\ndescription = "d"\n',
        encoding="utf-8",
    )
    with pytest.raises(FlagError, match="duplicate"):
        FlagRegistry(path).load()


# ── audit ──────────────────────────────────────────────────────────────────


def test_audit_real_registry(real_registry):
    report = real_registry.audit(
        consumed_names=[
            "COMFYMODAL_V2_PNG_COMPRESS_LEVEL",
            "SOME_UNKNOWN_RUNTIME_VAR",
        ],
        profile_set_names=["V2_TOTALLY_UNKNOWN_PROFILE_VAR"],
    )
    assert isinstance(report, AuditReport)
    assert "COMFYMODAL_V2_PNG_COMPRESS_LEVEL" in report.consumed_registered
    assert "SOME_UNKNOWN_RUNTIME_VAR" in report.consumed_unregistered
    assert "COMFYMODAL_V2_PNG_COMPRESS_LEVEL" not in report.registered_no_consumer
    assert "COMFYMODAL_V2_UNET_FASTSAFETENSORS" in report.registered_no_consumer
    assert "V2_TOTALLY_UNKNOWN_PROFILE_VAR" in report.profile_set_no_consumer


def test_audit_empty_inputs(real_registry):
    report = real_registry.audit(consumed_names=[], profile_set_names=[])
    assert report.consumed_registered == []
    assert report.consumed_unregistered == []
    assert len(report.registered_no_consumer) == len(real_registry.registered_names())


# ── load idempotence ───────────────────────────────────────────────────────


def test_load_idempotent(tmp_path):
    path = tmp_path / "reg.toml"
    path.write_text(
        'schema_version = 1\n'
        '[[flag]]\nname = "X1"\ntype = "bool"\ndefault = "0"\n'
        'consumed_at = "request"\nchange_requires = "run"\n'
        'owner = "t"\ndescription = "d"\n',
        encoding="utf-8",
    )
    registry = FlagRegistry(path)
    registry.load()
    registry.load()  # no-op
    assert len(registry.registered_names()) == 1


def test_unknown_name_returns_none(real_registry):
    assert real_registry.get("COMFYMODAL_V2_DEFINITELY_NOT_REGISTERED") is None
