"""Focused tests for V2 critical-path deletion fast paths.

All tests use mocks — no Modal/network calls, no real ComfyUI imports.
Covers:
- Custom-node restore identity skip (Target 2)
- Sage restore identity skip (Target 3)
- Snapshot-memory certificate (Target 4)
- Descriptor-only output base64 guard (Target 5)
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from comfymodal_runtime.runtime_bootstrap import (
    BootstrapConfig,
    BootstrapState,
    RuntimeBootstrap,
)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _make_state(*, prescan_cn_gen: str = "gen-1", sage_mode: str = "", sage_captured: bool = False) -> BootstrapState:
    state = BootstrapState()
    state.prescan_custom_node_generation = prescan_cn_gen
    state.prescan_runtime_generation = "rs-gen-1"
    state.sage_mode = sage_mode
    state.sage_identity_captured = sage_captured
    return state


CUSTOM_NODE_GENERATION_SCHEMA_VERSION = 1


def _write_prescan_record(path: str, generation: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump({
            "schema_version": CUSTOM_NODE_GENERATION_SCHEMA_VERSION,
            "generation": generation,
            "content_hash": "rs-hash",
            "reason": "test",
        }, f)


def _make_restore_bootstrap(
    *,
    prescan_cn_gen: str = "gen-1",
    record_gen: str = "gen-1",
    sage_mode: str = "baked_cuda",
    sage_captured: bool = False,
) -> tuple[RuntimeBootstrap, MagicMock, MagicMock]:
    """Create a RuntimeBootstrap with:
    - A prescan generation identity on the state
    - A prescan record file on disk
    - Mock sync_custom_nodes and apply_sage_policy callables
    """
    tmpdir = tempfile.mkdtemp()
    record_path = os.path.join(tmpdir, "prescan_record.json")
    _write_prescan_record(record_path, record_gen)

    config = BootstrapConfig(
        comfyui_root=tmpdir,
        models_path=os.path.join(tmpdir, "models"),
        prescan_record_path=record_path,
    )
    sync_mock = MagicMock()
    sage_mock = MagicMock(return_value=True)

    bootstrap = RuntimeBootstrap(
        config,
        reload_models=MagicMock(),
        reload_runtime_state=MagicMock(),
        sync_custom_nodes=sync_mock,
        start_backend=lambda: "in_process",
        restore_gpu_state=MagicMock(),
        initialize_cuda=lambda: {"device": "cuda:0", "cuda_available": "1"},
        apply_sage_policy=sage_mock,
        observe_generations=lambda: {"runtime_state": "rs-gen-1", "custom_nodes": record_gen},
    )
    # Set up the state with prescan identity and optional sage identity
    bootstrap.state.prescan_custom_node_generation = prescan_cn_gen
    bootstrap.state.prescan_runtime_generation = "rs-gen-1"
    bootstrap.state.prescan_record_path = record_path
    if sage_mode:
        bootstrap.state.sage_mode = sage_mode
    if sage_captured:
        bootstrap.state.sage_identity_captured = True

    return bootstrap, sync_mock, sage_mock


# ═══════════════════════════════════════════════════════════════════════════
# Target 2: Custom-node restore fast path
# ═══════════════════════════════════════════════════════════════════════════


class TestCustomNodeRestoreFastPath:
    """Verify identity-based skip of sync_custom_nodes during restore()."""

    def test_exact_identity_skips_sync(self) -> None:
        """When prescan identity matches persisted record, sync_custom_nodes is
        NOT called."""
        bootstrap, sync_mock, _ = _make_restore_bootstrap(
            prescan_cn_gen="gen-1",
            record_gen="gen-1",
        )
        with patch.object(bootstrap, "observe_generations", return_value={"runtime_state": "rs-gen-1", "custom_nodes": "gen-1"}):
            bootstrap.restore()
        assert sync_mock.call_count == 0, (
            f"sync_custom_nodes should not be called on identity match, "
            f"called {sync_mock.call_count} times"
        )

    def test_missing_record_calls_full_sync(self) -> None:
        """When no prescan record exists, sync_custom_nodes IS called
        because has_prescan_identity() returns False."""
        tmpdir = tempfile.mkdtemp()
        record_path = os.path.join(tmpdir, "nonexistent.json")
        config = BootstrapConfig(
            comfyui_root=tmpdir,
            models_path=os.path.join(tmpdir, "models"),
            prescan_record_path=record_path,
        )
        sync_mock = MagicMock()
        bootstrap = RuntimeBootstrap(
            config,
            reload_models=MagicMock(),
            reload_runtime_state=MagicMock(),
            sync_custom_nodes=sync_mock,
            start_backend=lambda: "in_process",
            restore_gpu_state=MagicMock(),
            initialize_cuda=lambda: {"device": "cuda:0"},
            apply_sage_policy=MagicMock(),
            observe_generations=lambda: {"runtime_state": "rs-gen-1", "custom_nodes": "gen-any"},
        )
        # Prescan values are not set on state and record doesn't exist —
        # has_prescan_identity() returns False, so sync_custom_nodes runs.
        bootstrap.restore()
        assert sync_mock.call_count >= 1, (
            "sync_custom_nodes should be called when record is missing"
        )

    def test_empty_prescan_identity_calls_full_sync(self) -> None:
        """When prescan identity fields are empty after record restore,
        sync_custom_nodes IS called because has_prescan_identity() returns False.

        This happens when the prescan record file has empty generation values."""
        tmpdir = tempfile.mkdtemp()
        record_path = os.path.join(tmpdir, "empty_record.json")
        os.makedirs(os.path.dirname(record_path), exist_ok=True)
        with open(record_path, "w") as f:
            json.dump({"schema_version": CUSTOM_NODE_GENERATION_SCHEMA_VERSION, "generation": "", "content_hash": "", "reason": ""}, f)
        config = BootstrapConfig(
            comfyui_root=tmpdir,
            models_path=os.path.join(tmpdir, "models"),
            prescan_record_path=record_path,
        )
        sync_mock = MagicMock()
        bootstrap = RuntimeBootstrap(
            config,
            reload_models=MagicMock(),
            reload_runtime_state=MagicMock(),
            sync_custom_nodes=sync_mock,
            start_backend=lambda: "in_process",
            restore_gpu_state=MagicMock(),
            initialize_cuda=lambda: {"device": "cuda:0"},
            apply_sage_policy=MagicMock(),
            observe_generations=lambda: {"runtime_state": "rs-gen-1", "custom_nodes": "gen-1"},
        )
        bootstrap.state.prescan_custom_node_generation = ""
        bootstrap.state.prescan_runtime_generation = ""
        bootstrap.restore()
        assert sync_mock.call_count >= 1, (
            "sync_custom_nodes should be called when prescan identity is empty"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Target 3: Sage exact-match fast path
# ═══════════════════════════════════════════════════════════════════════════


class TestSageRestoreFastPath:
    """Verify identity-based skip of Sage discovery/patch during restore()."""

    def test_sage_not_captured_calls_policy(self) -> None:
        """When sage_identity_captured is False, apply_sage_policy
        IS called during restore."""
        bootstrap, _, sage_mock = _make_restore_bootstrap(
            prescan_cn_gen="gen-1",
            record_gen="gen-1",
            sage_mode="baked_cuda",
            sage_captured=False,
        )
        with patch.object(bootstrap, "observe_generations", return_value={"runtime_state": "rs-gen-1", "custom_nodes": "gen-1"}):
            bootstrap.restore()
        assert sage_mock.call_count == 1, (
            f"apply_sage_policy should be called when not captured, "
            f"called {sage_mock.call_count} times"
        )

    def test_first_restore_captures_identity(self) -> None:
        """On first restore (sage_identity_captured=False), apply_sage_policy
        IS called and sage_identity_captured is set to True."""
        bootstrap, _, sage_mock = _make_restore_bootstrap(
            prescan_cn_gen="gen-1",
            record_gen="gen-1",
            sage_mode="",  # Not set yet (first restore)
            sage_captured=False,
        )
        with patch.object(bootstrap, "observe_generations", return_value={"runtime_state": "rs-gen-1", "custom_nodes": "gen-1"}):
            bootstrap.restore()
        assert sage_mock.call_count >= 1, (
            "apply_sage_policy should be called on first restore"
        )
        assert bootstrap.state.sage_identity_captured, (
            "sage_identity_captured should be True after first restore"
        )
        assert bootstrap.state.sage_mode == "baked_cuda", (
            "sage_mode should be populated after first restore"
        )

    def test_env_change_runs_discovery(self) -> None:
        """When the prescan record is missing (has_prescan_identity False),
        apply_sage_policy IS called even if identity was captured previously."""
        tmpdir = tempfile.mkdtemp()
        record_path = os.path.join(tmpdir, "nonexistent.json")
        config = BootstrapConfig(
            comfyui_root=tmpdir,
            models_path=os.path.join(tmpdir, "models"),
            prescan_record_path=record_path,
        )
        sage_mock = MagicMock(return_value=True)
        bootstrap = RuntimeBootstrap(
            config,
            reload_models=MagicMock(),
            reload_runtime_state=MagicMock(),
            sync_custom_nodes=MagicMock(),
            start_backend=lambda: "in_process",
            restore_gpu_state=MagicMock(),
            initialize_cuda=lambda: {"device": "cuda:0"},
            apply_sage_policy=sage_mock,
            observe_generations=lambda: {"runtime_state": "rs-gen-1", "custom_nodes": "gen-1"},
        )
        # Simulate sage was captured in a previous restore
        bootstrap.state.sage_mode = "baked_cuda"
        bootstrap.state.sage_identity_captured = True
        # No record exists → has_prescan_identity() is False → Sage fast path skips
        bootstrap.restore()
        assert sage_mock.call_count >= 1, (
            "apply_sage_policy should be called when env is unknown (no record)"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Target 4: Snapshot-memory certificate helper
# ═══════════════════════════════════════════════════════════════════════════


class TestSnapshotCertificateBuild:
    """Verify the snapshot certificate built during restore has valid identity components."""

    def test_snapshot_cert_built_during_restore(self) -> None:
        """After restore(), the snapshot certificate on BootstrapState is populated."""
        bootstrap, _, _ = _make_restore_bootstrap(
            prescan_cn_gen="gen-1",
            record_gen="gen-1",
            sage_mode="",
            sage_captured=False,
        )
        with patch.object(bootstrap, "observe_generations", return_value={"runtime_state": "rs-gen-1", "custom_nodes": "gen-1"}):
            bootstrap.restore()
        assert bootstrap.state.snapshot_cert_valid, (
            "snapshot_certificate should be valid after restore"
        )
        sc = bootstrap.state.snapshot_certificate
        assert isinstance(sc, dict), "snapshot_certificate should be a dict"


# ═══════════════════════════════════════════════════════════════════════════
# Target 5: Descriptor-only output path
# ═══════════════════════════════════════════════════════════════════════════


class TestConvertOutputItemsBase64:
    """Verify the include_base64 parameter in convert_output_items()."""

    def _make_item(self, *, raw_bytes: bytes = b"test-image-data-1234") -> Any:
        from comfymodal_runtime.output_delivery import OutputItem, ConversionMeta
        return OutputItem(
            node_id="107",
            output_key="images",
            filename="output.png",
            path="/tmp/output.png",
            raw_bytes=raw_bytes,
            mime_type="image/png",
            file_ext=".png",
            width=512,
            height=512,
            output_index=0,
            format="png",
            conversion_meta=ConversionMeta(
                format="png",
                mime_type="image/png",
                file_ext=".png",
                raw_bytes=len(raw_bytes),
                hash_of_raw="abc123",
            ),
        )

    def test_descriptor_mode_skips_base64(self) -> None:
        """When include_base64=False, base64 encoding is NOT called."""
        from comfymodal_runtime.result_delivery import convert_output_items
        item = self._make_item()
        # Patch base64 to verify it's not called
        with patch("comfymodal_runtime.result_delivery.base64.b64encode") as b64_mock:
            result = convert_output_items(
                [item],
                output_format="original",
                include_base64=False,
            )
        assert b64_mock.call_count == 0, (
            f"base64.b64encode should not be called in descriptor mode, "
            f"called {b64_mock.call_count} times"
        )
        assert len(result.items) == 1
        assert result.items[0].base64_data == "", (
            "base64_data should be empty string in descriptor mode"
        )

    def test_legacy_mode_still_encodes_base64(self) -> None:
        """When include_base64=True (default), base64 encoding IS called."""
        from comfymodal_runtime.result_delivery import convert_output_items
        item = self._make_item()
        with patch("comfymodal_runtime.result_delivery.base64.b64encode") as b64_mock:
            b64_mock.return_value = b"dGVzdC1pbWFnZS1kYXRhLTEyMzQ="
            result = convert_output_items(
                [item],
                output_format="original",
                include_base64=True,
            )
        assert b64_mock.call_count >= 1, (
            "base64.b64encode should be called in legacy mode"
        )
        assert result.items[0].base64_data == "dGVzdC1pbWFnZS1kYXRhLTEyMzQ=", (
            "base64_data should be the encoded value in legacy mode"
        )

    def test_descriptor_mode_default(self) -> None:
        """Descriptor mode is the safe default; legacy mode is explicit."""
        from inspect import signature
        from comfymodal_runtime.result_delivery import convert_output_items
        sig = signature(convert_output_items)
        assert "include_base64" in sig.parameters
        param = sig.parameters["include_base64"]
        assert param.default is False, (
            "include_base64 should default to False"
        )

    def test_byte_count_preserved_in_descriptor_mode(self) -> None:
        """Byte count should be the real converted bytes, not 8 or 0."""
        from comfymodal_runtime.result_delivery import convert_output_items
        raw = b"real-image-bytes-12345"
        item = self._make_item(raw_bytes=raw)
        result = convert_output_items(
            [item],
            output_format="original",
            include_base64=False,
        )
        assert len(result.items) == 1
        meta = result.items[0].conversion_meta
        assert meta is not None
        assert meta.raw_bytes > 0, "raw_bytes should be > 0"
        assert meta.raw_bytes == len(raw), (
            f"byte count mismatch: expected {len(raw)}, got {meta.raw_bytes}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Integration: custom-node identity + Sage identity compose correctly
# ═══════════════════════════════════════════════════════════════════════════


class TestRestoreFastPathIntegration:
    """Verify multiple fast paths work together in a single restore()."""

    def test_custom_node_skip_on_exact_match(self) -> None:
        """When prescan identity matches, sync_custom_nodes is skipped."""
        bootstrap, sync_mock, sage_mock = _make_restore_bootstrap(
            prescan_cn_gen="gen-1",
            record_gen="gen-1",
            sage_mode="baked_cuda",
            sage_captured=False,
        )
        with patch.object(bootstrap, "observe_generations", return_value={"runtime_state": "rs-gen-1", "custom_nodes": "gen-1"}):
            bootstrap.restore()
        assert sync_mock.call_count == 0, "sync should be skipped on identity match"
        # Sage runs because snapshot_sage_identity is empty (no real module)
        assert sage_mock.call_count >= 1, "sage runs since no real Sage module for verify"

    def test_first_call_runs_both(self) -> None:
        """On first restore, sync is skipped (prescan match) and Sage runs."""
        bootstrap, sync_mock, sage_mock = _make_restore_bootstrap(
            prescan_cn_gen="gen-1",
            record_gen="gen-1",
            sage_mode="",      # Not set yet
            sage_captured=False,
        )
        with patch.object(bootstrap, "observe_generations", return_value={"runtime_state": "rs-gen-1", "custom_nodes": "gen-1"}):
            bootstrap.restore()
        # Sage runs because snapshot_sage_identity is empty
        assert sage_mock.call_count >= 1, "sage should run on first restore"
        # CN sync is skipped because has_prescan_identity() is True (record restored)
        assert sync_mock.call_count == 0, (
            "sync is skipped because has_prescan_identity() succeeds"
        )
        # After first restore, sage identity is captured by apply_sage_policy
        assert bootstrap.state.sage_identity_captured

    def test_sage_runs_while_cn_skips(self) -> None:
        """Sage always runs when verify fails; CN sync skips when record exists.

        The sage_identity_captured flag alone is not sufficient to skip Sage
        (the fallback was removed per spec). The snapshot_sage_identity
        must verify against the real module for the skip to work."""
        tmpdir = tempfile.mkdtemp()
        record_path = os.path.join(tmpdir, "prescan_test.json")
        _write_prescan_record(record_path, "gen-1")
        config = BootstrapConfig(
            comfyui_root=tmpdir,
            models_path=os.path.join(tmpdir, "models"),
            prescan_record_path=record_path,
        )
        sync_mock = MagicMock()
        sage_mock = MagicMock(return_value={"mode": "baked_cuda", "reason": "patched"})
        bootstrap = RuntimeBootstrap(
            config,
            reload_models=MagicMock(),
            reload_runtime_state=MagicMock(),
            sync_custom_nodes=sync_mock,
            start_backend=lambda: "in_process",
            restore_gpu_state=MagicMock(),
            initialize_cuda=lambda: {"device": "cuda:0"},
            apply_sage_policy=sage_mock,
            observe_generations=lambda: {"runtime_state": "rs-gen-1", "custom_nodes": "gen-1"},
        )
        bootstrap.restore()
        # CN sync skipped because prescan record exists
        assert sync_mock.call_count == 0, "sync should be skipped (prescan record exists)"
        # Sage runs because snapshot_sage_identity is empty (verify fails)
        assert sage_mock.call_count >= 1, "sage should run (no snapshot_sage_identity)"
        assert sage_mock.call_count >= 1, "sage should run (no prescan identity to verify env)"
