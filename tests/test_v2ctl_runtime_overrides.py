"""Tests for tools/v2_control/runtime_overrides.py (design section 10).

Covers contract section 21 runtime-override coverage: local listing from a
tmp dir, forbid raising with names listed, warn not raising, clear
single/all-with-confirm, traversal guard, and proof that the remote lister
is never invoked unless include_remote=True.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.v2_control.errors import RuntimeOverrideViolation
from tools.v2_control.runtime_overrides import (
    DEFAULT_RUNTIME_OVERRIDE_POLICY,
    RuntimeOverride,
    RuntimeOverrideInventory,
)


def make_override_dir(tmp_path: Path) -> Path:
    d = tmp_path / ".runtime_state"
    d.mkdir(parents=True)
    return d


def write_override(directory: Path, name: str, value: str) -> None:
    (directory / f"{name}.txt").write_text(value, encoding="utf-8")


class TestListLocal:
    def test_empty_dir_lists_nothing(self, tmp_path):
        inventory = RuntimeOverrideInventory(local_dir=make_override_dir(tmp_path))
        assert inventory.list_local() == []

    def test_missing_dir_lists_nothing(self, tmp_path):
        inventory = RuntimeOverrideInventory(local_dir=tmp_path / "does-not-exist")
        assert inventory.list_local() == []

    def test_lists_stem_value_source(self, tmp_path):
        directory = make_override_dir(tmp_path)
        write_override(directory, "COMFYMODAL_V2_BENCHMARK", "1")
        write_override(directory, "COMFYMODAL_V2_GAP_SECONDS", "0")
        inventory = RuntimeOverrideInventory(local_dir=directory)
        overrides = inventory.list_local()
        assert [o.name for o in overrides] == ["COMFYMODAL_V2_BENCHMARK", "COMFYMODAL_V2_GAP_SECONDS"]
        assert overrides[0].value == "1"
        assert overrides[0].source == "local_staging"

    def test_values_are_stripped(self, tmp_path):
        directory = make_override_dir(tmp_path)
        write_override(directory, "X", "  hello  \n")
        inventory = RuntimeOverrideInventory(local_dir=directory)
        assert inventory.list_local()[0].value == "hello"


class TestListRemote:
    def test_remote_empty_when_no_lister(self, tmp_path):
        inventory = RuntimeOverrideInventory(local_dir=make_override_dir(tmp_path))
        assert inventory.list_remote() == []

    def test_remote_lister_never_called_unless_include_remote(self, tmp_path):
        def boom():
            raise AssertionError("remote lister must not be called")

        inventory = RuntimeOverrideInventory(
            local_dir=make_override_dir(tmp_path), remote_lister=boom
        )
        # these must NOT touch the remote lister at all
        inventory.list_local()
        inventory.enforce_policy("forbid")  # nothing local -> no raise, no lister call
        inventory.describe()
        # explicit include_remote DOES call it
        with pytest.raises(AssertionError):
            inventory.enforce_policy("forbid", include_remote=True)

    def test_list_remote_uses_lister_when_called_explicitly(self, tmp_path):
        inventory = RuntimeOverrideInventory(
            local_dir=make_override_dir(tmp_path),
            remote_lister=lambda: [RuntimeOverride(name="REMOTE_FLAG", value="9", source="remote_volume")],
        )
        remote = inventory.list_remote()
        assert len(remote) == 1
        assert remote[0].name == "REMOTE_FLAG"
        assert remote[0].source == "remote_volume"


class TestEnforcePolicy:
    def test_forbid_with_override_raises_listing_names(self, tmp_path):
        directory = make_override_dir(tmp_path)
        write_override(directory, "COMFYMODAL_V2_BENCHMARK", "1")
        write_override(directory, "COMFYMODAL_V2_GAP", "0")
        inventory = RuntimeOverrideInventory(local_dir=directory)
        with pytest.raises(RuntimeOverrideViolation) as excinfo:
            inventory.enforce_policy("forbid")
        message = str(excinfo.value)
        assert "COMFYMODAL_V2_BENCHMARK" in message
        assert "COMFYMODAL_V2_GAP" in message
        # never auto-deletes
        assert inventory.list_local() != []

    def test_forbid_with_no_overrides_passes(self, tmp_path):
        inventory = RuntimeOverrideInventory(local_dir=make_override_dir(tmp_path))
        assert inventory.enforce_policy("forbid") == []

    def test_warn_does_not_raise(self, tmp_path):
        directory = make_override_dir(tmp_path)
        write_override(directory, "COMFYMODAL_V2_BENCHMARK", "1")
        inventory = RuntimeOverrideInventory(local_dir=directory)
        present = inventory.enforce_policy("warn")
        assert [o.name for o in present] == ["COMFYMODAL_V2_BENCHMARK"]

    def test_default_policy_constant(self):
        assert DEFAULT_RUNTIME_OVERRIDE_POLICY == "forbid"


class TestClear:
    def test_clear_local_single(self, tmp_path):
        directory = make_override_dir(tmp_path)
        write_override(directory, "COMFYMODAL_V2_BENCHMARK", "1")
        inventory = RuntimeOverrideInventory(local_dir=directory)
        assert inventory.clear_local("COMFYMODAL_V2_BENCHMARK") is True
        assert inventory.list_local() == []
        assert inventory.clear_local("COMFYMODAL_V2_BENCHMARK") is False

    def test_clear_local_traversal_guard(self, tmp_path):
        inventory = RuntimeOverrideInventory(local_dir=make_override_dir(tmp_path))
        for bad in ("../evil", "a/b", "a\\b", "/abs", ".."):
            with pytest.raises(ValueError):
                inventory.clear_local(bad)

    def test_clear_local_all_requires_confirm(self, tmp_path):
        directory = make_override_dir(tmp_path)
        write_override(directory, "A", "1")
        inventory = RuntimeOverrideInventory(local_dir=directory)
        with pytest.raises(RuntimeOverrideViolation):
            inventory.clear_local_all(confirm=False)
        assert inventory.list_local() != []

    def test_clear_local_all_with_confirm_returns_removed(self, tmp_path):
        directory = make_override_dir(tmp_path)
        write_override(directory, "B", "1")
        write_override(directory, "A", "2")
        inventory = RuntimeOverrideInventory(local_dir=directory)
        removed = inventory.clear_local_all(confirm=True)
        assert removed == ["A", "B"]
        assert inventory.list_local() == []


class TestDescribe:
    def test_describe_shape(self, tmp_path):
        directory = make_override_dir(tmp_path)
        write_override(directory, "COMFYMODAL_V2_BENCHMARK", "1")
        inventory = RuntimeOverrideInventory(local_dir=directory, remote_lister=None)
        info = inventory.describe()
        assert info["policy"] == "forbid"
        assert info["remote_available"] is False
        assert info["remote"] == []
        assert [o["name"] for o in info["local"]] == ["COMFYMODAL_V2_BENCHMARK"]
