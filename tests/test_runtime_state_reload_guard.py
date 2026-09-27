"""Batch B rev 2 — runtime-state Volume reload guard tests (content-based).

Proves that RuntimeBootstrap.restore() skips the reload_runtime_state
callback only when BOTH the generation AND the local construction-state
content manifest match: expected-present files exist with matching sha256 and
expected-absent files remain absent.  Every other state reloads (fail
closed).  The guard performs only local filesystem reads — no network/RPC
I/O — and never falsely signals a remote reload (the 900 s cert-reload dedup
stamp lives in the modal_app reload closure, which is only ever invoked on the
reload path).
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from comfymodal_runtime.runtime_bootstrap import BootstrapConfig, RuntimeBootstrap
from comfymodal_runtime.runtime_generation import (
    RUNTIME_STATE_GENERATION_FILENAME,
    RUNTIME_STATE_GENERATION_SCHEMA_VERSION,
    build_runtime_state_manifest,
    write_runtime_state_generation_marker,
)


def _write_bytes(path: str, content: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(content)


def _write_prescan(root_dir: str, content: bytes = b'{"schema_version":"1","custom_node_generation":"cn123"}') -> None:
    _write_bytes(os.path.join(root_dir, "prescan_custom_nodes.json"), content)


def _write_gpu(root_dir: str, content: bytes = b'{"gpu_name":"RTX","total_vram_mib":97887}') -> None:
    _write_bytes(os.path.join(root_dir, "gpu_capacity_frozen.json"), content)


def _make_bootstrap(
    root_dir: str,
    *,
    snapshot_generation: str = "",
    snapshot_manifest: dict[str, Any] | None = None,
    with_reload_callback: bool = True,
    reader: Any = None,
    writer: Any = None,
    verifier: Any = None,
    manifest_files: tuple[str, ...] | None = None,
) -> tuple[RuntimeBootstrap, list[Any]]:
    """Build a RuntimeBootstrap whose runtime-state marker lives in root_dir.

    ``reader``/``writer``/``verifier`` default to the real local-filesystem
    module functions.  Returns (bootstrap, calls) where calls records reload
    callback invocations.
    """
    calls: list[Any] = []
    reload_fn = (lambda: calls.append("reload")) if with_reload_callback else None
    marker_path = os.path.join(root_dir, RUNTIME_STATE_GENERATION_FILENAME)
    config = BootstrapConfig(
        comfyui_root="/root/comfy/ComfyUI",
        models_path="/root/models",
        custom_nodes_path="/root/custom_nodes_vol",
        prescan_record_path=os.path.join(root_dir, "prescan_custom_nodes.json"),
        runtime_state_generation_path=marker_path,
        runtime_state_manifest_files=manifest_files if manifest_files is not None else (),
    )
    bootstrap = RuntimeBootstrap(
        config,
        reload_runtime_state=reload_fn,
        read_runtime_state_generation_marker=reader,
        write_runtime_state_generation_marker=writer,
        verify_runtime_state_manifest=verifier,
    )
    bootstrap.state.snapshot_runtime_state_generation = snapshot_generation
    if snapshot_manifest is not None:
        bootstrap.state.snapshot_runtime_state_manifest = dict(snapshot_manifest)
    return bootstrap, calls


def _run_restore(bootstrap: RuntimeBootstrap) -> str:
    buf = io.StringIO()
    with redirect_stdout(buf):
        bootstrap.restore()
    return buf.getvalue()


def _decision_line(output: str) -> str:
    for line in output.splitlines():
        if "[v2.runtime_state_volume_restore]" in line:
            return line.strip()
    return ""


class RuntimeStateReloadGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root_dir = self._tmp.name

    # ── Content-based skip/reload table ────────────────────────────────

    def test_generation_and_manifest_match_skips_reload(self) -> None:
        _write_prescan(self.root_dir)
        _write_gpu(self.root_dir)
        manifest = build_runtime_state_manifest(self.root_dir)
        gen = "a" * 32
        write_runtime_state_generation_marker(
            self.root_dir, generation=gen, files_manifest=manifest
        )
        bootstrap, calls = _make_bootstrap(
            self.root_dir, snapshot_generation=gen, snapshot_manifest=manifest
        )
        out = _run_restore(bootstrap)
        self.assertNotIn("reload", calls)
        line = _decision_line(out)
        self.assertIn("decision=skipped_generation_match", line)
        self.assertIn("reason=exact_match", line)
        self.assertIn("callback_called=0", line)
        self.assertIn("runtime_state_reload_invoked=0", line)
        self.assertEqual(
            bootstrap.state.restore_stage_classifications["reload_runtime_state"],
            "skipped",
        )
        self.assertEqual(
            bootstrap.state.restore_generation_guard_decisions["reload_runtime_state"]["reason"],
            "exact_match",
        )

    def test_match_but_expected_file_missing_reloads(self) -> None:
        _write_prescan(self.root_dir)
        _write_gpu(self.root_dir)
        manifest = build_runtime_state_manifest(self.root_dir)
        gen = "a" * 32
        write_runtime_state_generation_marker(
            self.root_dir, generation=gen, files_manifest=manifest
        )
        # The restored mount lost gpu_capacity_frozen.json.
        os.remove(os.path.join(self.root_dir, "gpu_capacity_frozen.json"))
        bootstrap, calls = _make_bootstrap(
            self.root_dir, snapshot_generation=gen, snapshot_manifest=manifest
        )
        out = _run_restore(bootstrap)
        self.assertIn("reload", calls)
        self.assertIn("reason=manifest_file_missing", _decision_line(out))

    def test_match_but_expected_file_content_changed_reloads(self) -> None:
        _write_prescan(self.root_dir)
        _write_gpu(self.root_dir)
        manifest = build_runtime_state_manifest(self.root_dir)
        gen = "a" * 32
        write_runtime_state_generation_marker(
            self.root_dir, generation=gen, files_manifest=manifest
        )
        # The restored mount has stale/different content.
        _write_gpu(self.root_dir, b'{"gpu_name":"DIFFERENT","total_vram_mib":1}')
        bootstrap, calls = _make_bootstrap(
            self.root_dir, snapshot_generation=gen, snapshot_manifest=manifest
        )
        out = _run_restore(bootstrap)
        self.assertIn("reload", calls)
        self.assertIn("reason=manifest_hash_mismatch", _decision_line(out))

    def test_match_but_marker_manifest_mismatch_reloads(self) -> None:
        # Baseline manifest differs from what the marker claims.
        _write_prescan(self.root_dir)
        _write_gpu(self.root_dir)
        baseline_manifest = build_runtime_state_manifest(self.root_dir)
        gen = "a" * 32
        other_manifest = {"prescan_custom_nodes.json": {"present": True, "sha256": "0" * 64}}
        write_runtime_state_generation_marker(
            self.root_dir, generation=gen, files_manifest=other_manifest
        )
        bootstrap, calls = _make_bootstrap(
            self.root_dir, snapshot_generation=gen, snapshot_manifest=baseline_manifest
        )
        out = _run_restore(bootstrap)
        self.assertIn("reload", calls)
        self.assertIn("reason=manifest_mismatch", _decision_line(out))

    def test_expected_absent_file_present_reloads(self) -> None:
        # Construction recorded gpu file as absent (arm off) but the restored
        # mount has one -> unexpected -> reload.
        _write_prescan(self.root_dir)
        manifest = build_runtime_state_manifest(self.root_dir)  # gpu present=false
        gen = "a" * 32
        write_runtime_state_generation_marker(
            self.root_dir, generation=gen, files_manifest=manifest
        )
        _write_gpu(self.root_dir)  # appears on restore
        bootstrap, calls = _make_bootstrap(
            self.root_dir, snapshot_generation=gen, snapshot_manifest=manifest
        )
        out = _run_restore(bootstrap)
        self.assertIn("reload", calls)
        self.assertIn("reason=manifest_file_unexpected", _decision_line(out))

    def test_stale_generation_identical_files_reloads(self) -> None:
        _write_prescan(self.root_dir)
        _write_gpu(self.root_dir)
        manifest = build_runtime_state_manifest(self.root_dir)
        baseline_gen = "a" * 32
        stale_gen = "b" * 32  # old marker survives on the mount
        write_runtime_state_generation_marker(
            self.root_dir, generation=stale_gen, files_manifest=manifest
        )
        bootstrap, calls = _make_bootstrap(
            self.root_dir, snapshot_generation=baseline_gen, snapshot_manifest=manifest
        )
        out = _run_restore(bootstrap)
        self.assertIn("reload", calls)
        line = _decision_line(out)
        self.assertIn("decision=reloaded_generation_mismatch", line)
        self.assertIn("reason=generation_mismatch", line)

    def test_corrupt_content_manifest_reloads(self) -> None:
        _write_prescan(self.root_dir)
        manifest = build_runtime_state_manifest(self.root_dir)
        gen = "a" * 32
        # Marker JSON is valid but files is not a dict.
        marker_path = os.path.join(self.root_dir, RUNTIME_STATE_GENERATION_FILENAME)
        with open(marker_path, "w", encoding="utf-8") as fh:
            json.dump(
                {"schema_version": RUNTIME_STATE_GENERATION_SCHEMA_VERSION, "generation": gen, "files": "garbage"},
                fh,
            )
        bootstrap, calls = _make_bootstrap(
            self.root_dir, snapshot_generation=gen, snapshot_manifest=manifest
        )
        out = _run_restore(bootstrap)
        self.assertIn("reload", calls)
        self.assertIn("reason=manifest_invalid", _decision_line(out))

    def test_file_read_exception_reloads(self) -> None:
        _write_prescan(self.root_dir)
        manifest = build_runtime_state_manifest(self.root_dir)
        gen = "a" * 32
        write_runtime_state_generation_marker(
            self.root_dir, generation=gen, files_manifest=manifest
        )

        def _boom_verifier(root: str, expected: dict[str, Any]) -> tuple[bool, str]:
            raise RuntimeError("boom")

        bootstrap, calls = _make_bootstrap(
            self.root_dir,
            snapshot_generation=gen,
            snapshot_manifest=manifest,
            verifier=_boom_verifier,
        )
        out = _run_restore(bootstrap)
        self.assertIn("reload", calls)
        line = _decision_line(out)
        self.assertIn("decision=reloaded_generation_error", line)
        self.assertIn("reason=manifest_read_error:RuntimeError", line)

    def test_old_v1_marker_reloads_fail_closed(self) -> None:
        # Legacy schema-v1 marker (generation only, no content manifest).
        gen = "a" * 32
        marker_path = os.path.join(self.root_dir, RUNTIME_STATE_GENERATION_FILENAME)
        with open(marker_path, "w", encoding="utf-8") as fh:
            json.dump({"schema_version": 1, "generation": gen}, fh)
        manifest = {"prescan_custom_nodes.json": {"present": True, "sha256": "0" * 64}}
        bootstrap, calls = _make_bootstrap(
            self.root_dir, snapshot_generation=gen, snapshot_manifest=manifest
        )
        out = _run_restore(bootstrap)
        self.assertIn("reload", calls)
        self.assertIn("reason=record_invalid", _decision_line(out))

    def test_marker_without_files_manifest_reloads(self) -> None:
        # Schema v2 but missing the files payload entirely.
        gen = "a" * 32
        marker_path = os.path.join(self.root_dir, RUNTIME_STATE_GENERATION_FILENAME)
        with open(marker_path, "w", encoding="utf-8") as fh:
            json.dump(
                {"schema_version": RUNTIME_STATE_GENERATION_SCHEMA_VERSION, "generation": gen},
                fh,
            )
        manifest = {"prescan_custom_nodes.json": {"present": True, "sha256": "0" * 64}}
        bootstrap, calls = _make_bootstrap(
            self.root_dir, snapshot_generation=gen, snapshot_manifest=manifest
        )
        out = _run_restore(bootstrap)
        self.assertIn("reload", calls)
        self.assertIn("reason=manifest_invalid", _decision_line(out))

    # ── Missing / corrupt / unknown marker ─────────────────────────────

    def test_generation_mismatch_reloads(self) -> None:
        _write_prescan(self.root_dir)
        manifest = build_runtime_state_manifest(self.root_dir)
        write_runtime_state_generation_marker(
            self.root_dir, generation="b" * 32, files_manifest=manifest
        )
        bootstrap, calls = _make_bootstrap(
            self.root_dir, snapshot_generation="a" * 32, snapshot_manifest=manifest
        )
        out = _run_restore(bootstrap)
        self.assertIn("reload", calls)
        self.assertEqual(calls.count("reload"), 1)
        line = _decision_line(out)
        self.assertIn("decision=reloaded_generation_mismatch", line)
        self.assertIn("reason=generation_mismatch", line)
        self.assertIn("runtime_state_reload_invoked=1", line)
        self.assertEqual(
            bootstrap.state.restore_stage_classifications["reload_runtime_state"],
            "reloaded",
        )
        self.assertEqual(
            bootstrap.state.restore_generation_guard_decisions["reload_runtime_state"]["decision"],
            "reloaded_generation_mismatch",
        )

    def test_missing_marker_reloads(self) -> None:
        manifest = {"prescan_custom_nodes.json": {"present": True, "sha256": "0" * 64}}
        bootstrap, calls = _make_bootstrap(
            self.root_dir, snapshot_generation="a" * 32, snapshot_manifest=manifest
        )
        out = _run_restore(bootstrap)
        self.assertIn("reload", calls)
        line = _decision_line(out)
        self.assertIn("decision=reloaded_generation_unknown", line)
        self.assertIn("reason=record_unavailable", line)

    def test_corrupt_marker_reloads(self) -> None:
        marker_path = os.path.join(self.root_dir, RUNTIME_STATE_GENERATION_FILENAME)
        _write_bytes(marker_path, b"{not-json!!")
        manifest = {"prescan_custom_nodes.json": {"present": True, "sha256": "0" * 64}}
        bootstrap, calls = _make_bootstrap(
            self.root_dir, snapshot_generation="a" * 32, snapshot_manifest=manifest
        )
        out = _run_restore(bootstrap)
        self.assertIn("reload", calls)
        self.assertIn("reason=record_unavailable", _decision_line(out))

    def test_invalid_schema_marker_reloads(self) -> None:
        marker_path = os.path.join(self.root_dir, RUNTIME_STATE_GENERATION_FILENAME)
        _write_bytes(
            marker_path,
            json.dumps({"schema_version": 99, "generation": "a" * 32}).encode(),
        )
        manifest = {"prescan_custom_nodes.json": {"present": True, "sha256": "0" * 64}}
        bootstrap, calls = _make_bootstrap(
            self.root_dir, snapshot_generation="a" * 32, snapshot_manifest=manifest
        )
        out = _run_restore(bootstrap)
        self.assertIn("reload", calls)
        self.assertIn("reason=record_invalid", _decision_line(out))

    def test_empty_generation_field_reloads(self) -> None:
        def _empty_gen_reader(root_dir: str) -> Any:
            return {"schema_version": RUNTIME_STATE_GENERATION_SCHEMA_VERSION, "generation": "", "files": {}}

        manifest = {"prescan_custom_nodes.json": {"present": True, "sha256": "0" * 64}}
        bootstrap, calls = _make_bootstrap(
            self.root_dir,
            snapshot_generation="a" * 32,
            snapshot_manifest=manifest,
            reader=_empty_gen_reader,
        )
        out = _run_restore(bootstrap)
        self.assertIn("reload", calls)
        self.assertIn("reason=record_invalid", _decision_line(out))

    def test_reader_exception_reloads(self) -> None:
        def _boom(root_dir: str) -> Any:
            raise RuntimeError("boom")

        manifest = {"prescan_custom_nodes.json": {"present": True, "sha256": "0" * 64}}
        bootstrap, calls = _make_bootstrap(
            self.root_dir,
            snapshot_generation="a" * 32,
            snapshot_manifest=manifest,
            reader=_boom,
        )
        out = _run_restore(bootstrap)
        self.assertIn("reload", calls)
        line = _decision_line(out)
        self.assertIn("decision=reloaded_generation_error", line)
        self.assertIn("reason=record_read_error", line)

    def test_no_snapshot_baseline_reloads(self) -> None:
        _write_prescan(self.root_dir)
        bootstrap, calls = _make_bootstrap(self.root_dir, snapshot_generation="")
        _write_gpu(self.root_dir)
        out = _run_restore(bootstrap)
        self.assertIn("reload", calls)
        line = _decision_line(out)
        self.assertIn("decision=reloaded_generation_unknown", line)
        self.assertIn("reason=no_snapshot_baseline", line)

    def test_manifest_baseline_missing_reloads(self) -> None:
        # Generation baseline captured but no content manifest (e.g. a v1-era
        # snapshot) -> fail closed.
        _write_prescan(self.root_dir)
        gen = "a" * 32
        write_runtime_state_generation_marker(
            self.root_dir, generation=gen, files_manifest={}
        )
        bootstrap, calls = _make_bootstrap(
            self.root_dir, snapshot_generation=gen, snapshot_manifest={}
        )
        out = _run_restore(bootstrap)
        self.assertIn("reload", calls)
        self.assertIn("reason=manifest_no_baseline", _decision_line(out))

    def test_mount_missing_reloads(self) -> None:
        # Exact generation + manifest match but the volume root is not
        # mounted: reload.  (Real local reader cannot produce this — file
        # exists implies dir — so inject a reader returning the match from a
        # dead path.)
        manifest = {"prescan_custom_nodes.json": {"present": True, "sha256": "0" * 64}}

        def _phantom_reader(root_dir: str) -> Any:
            return {
                "schema_version": RUNTIME_STATE_GENERATION_SCHEMA_VERSION,
                "generation": "a" * 32,
                "files": manifest,
            }

        missing_root = os.path.join(self._tmp.name, "no_such_mount")
        config = BootstrapConfig(
            comfyui_root="/root/comfy/ComfyUI",
            models_path="/root/models",
            custom_nodes_path="/root/custom_nodes_vol",
            prescan_record_path=os.path.join(missing_root, "prescan_custom_nodes.json"),
            runtime_state_generation_path=os.path.join(
                missing_root, RUNTIME_STATE_GENERATION_FILENAME
            ),
            runtime_state_manifest_files=("prescan_custom_nodes.json",),
        )
        calls: list[Any] = []
        bootstrap = RuntimeBootstrap(
            config,
            reload_runtime_state=lambda: calls.append("reload"),
            read_runtime_state_generation_marker=_phantom_reader,
        )
        bootstrap.state.snapshot_runtime_state_generation = "a" * 32
        bootstrap.state.snapshot_runtime_state_manifest = dict(manifest)
        out = _run_restore(bootstrap)
        self.assertIn("reload", calls)
        line = _decision_line(out)
        self.assertIn("reason=mount_missing", line)
        self.assertIn("decision=reloaded_generation_unknown", line)

    # ── Non-snapshot / legacy path ─────────────────────────────────────

    def test_legacy_path_no_callback_unchanged(self) -> None:
        bootstrap, calls = _make_bootstrap(
            self.root_dir, snapshot_generation="", with_reload_callback=False
        )
        out = _run_restore(bootstrap)
        self.assertEqual(calls, [])
        line = _decision_line(out)
        self.assertIn("decision=legacy_path", line)
        self.assertIn("reason=unconditional", line)
        self.assertIn("callback_called=0", line)

    def test_no_callback_marker_present_still_noop(self) -> None:
        _write_prescan(self.root_dir)
        manifest = build_runtime_state_manifest(self.root_dir)
        gen = "a" * 32
        write_runtime_state_generation_marker(
            self.root_dir, generation=gen, files_manifest=manifest
        )
        bootstrap, calls = _make_bootstrap(
            self.root_dir,
            snapshot_generation=gen,
            snapshot_manifest=manifest,
            with_reload_callback=False,
        )
        out = _run_restore(bootstrap)
        self.assertEqual(calls, [])
        self.assertIn("decision=legacy_path", _decision_line(out))

    # ── No-RPC proof ───────────────────────────────────────────────────

    def test_guard_performs_no_remote_io(self) -> None:
        _write_prescan(self.root_dir)
        _write_gpu(self.root_dir)
        manifest = build_runtime_state_manifest(self.root_dir)
        gen = "a" * 32
        write_runtime_state_generation_marker(
            self.root_dir, generation=gen, files_manifest=manifest
        )
        reads: list[str] = []
        verifies: list[str] = []

        def _local_reader(root_dir: str) -> Any:
            reads.append(root_dir)
            return read_runtime_state_generation_marker(root_dir)

        def _local_verifier(root_dir: str, expected: dict[str, Any]) -> tuple[bool, str]:
            verifies.append(root_dir)
            return verify_runtime_state_manifest(root_dir, expected)

        bootstrap, calls = _make_bootstrap(
            self.root_dir,
            snapshot_generation=gen,
            snapshot_manifest=manifest,
            reader=_local_reader,
            verifier=_local_verifier,
        )
        out = _run_restore(bootstrap)
        self.assertEqual(calls, [])
        self.assertEqual(reads, [self.root_dir])
        self.assertEqual(verifies, [self.root_dir])
        self.assertIn("decision=skipped_generation_match", _decision_line(out))

    # ── 900 s cert-reload dedup semantics ──────────────────────────────

    def test_skip_never_invokes_reload_callback(self) -> None:
        # The modal_app reload closure is the ONLY thing that stamps
        # _RUNTIME_STATE_VOLUME_RELOADED_MONO.  A skip must not invoke it,
        # so the 900 s dedup marker never claims a remote reload that did
        # not happen.
        _write_prescan(self.root_dir)
        manifest = build_runtime_state_manifest(self.root_dir)
        gen = "a" * 32
        write_runtime_state_generation_marker(
            self.root_dir, generation=gen, files_manifest=manifest
        )
        bootstrap, calls = _make_bootstrap(
            self.root_dir, snapshot_generation=gen, snapshot_manifest=manifest
        )
        _run_restore(bootstrap)
        self.assertEqual(calls, [])

    def test_reload_path_invokes_callback_exactly_once(self) -> None:
        # On a real reload the callback runs once (and would stamp the
        # 900 s marker exactly once in production).
        _write_prescan(self.root_dir)
        manifest = build_runtime_state_manifest(self.root_dir)
        write_runtime_state_generation_marker(
            self.root_dir, generation="b" * 32, files_manifest=manifest
        )
        bootstrap, calls = _make_bootstrap(
            self.root_dir, snapshot_generation="a" * 32, snapshot_manifest=manifest
        )
        _run_restore(bootstrap)
        self.assertEqual(calls.count("reload"), 1)

    # ── Construction-time baseline capture ─────────────────────────────

    def test_finalize_captures_baseline_and_manifest(self) -> None:
        _write_prescan(self.root_dir)
        bootstrap, calls = _make_bootstrap(
            self.root_dir,
            manifest_files=("prescan_custom_nodes.json", "gpu_capacity_frozen.json"),
        )
        gen = bootstrap.finalize_runtime_state_generation()
        self.assertTrue(gen)
        self.assertEqual(bootstrap.state.snapshot_runtime_state_generation, gen)
        self.assertTrue(bootstrap.state.runtime_state_generation_marker_written)
        manifest = bootstrap.state.snapshot_runtime_state_manifest
        self.assertIn("prescan_custom_nodes.json", manifest)
        self.assertTrue(manifest["prescan_custom_nodes.json"]["present"])
        self.assertTrue(manifest["prescan_custom_nodes.json"]["sha256"])
        # gpu absent at construction (arm off) -> recorded present=false.
        self.assertIn("gpu_capacity_frozen.json", manifest)
        self.assertFalse(manifest["gpu_capacity_frozen.json"]["present"])
        marker_path = os.path.join(self.root_dir, RUNTIME_STATE_GENERATION_FILENAME)
        with open(marker_path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        self.assertEqual(payload["generation"], gen)
        self.assertEqual(payload["schema_version"], RUNTIME_STATE_GENERATION_SCHEMA_VERSION)
        self.assertEqual(payload["files"], manifest)
        self.assertEqual(calls, [])  # construction marker write is not a reload

    def test_finalize_required_file_missing_fail_closed(self) -> None:
        # No prescan file in the construction root -> required-file read
        # failure -> no usable baseline.
        bootstrap, calls = _make_bootstrap(
            self.root_dir,
            manifest_files=("prescan_custom_nodes.json", "gpu_capacity_frozen.json"),
        )
        gen = bootstrap.finalize_runtime_state_generation()
        self.assertEqual(gen, "")
        self.assertEqual(bootstrap.state.snapshot_runtime_state_generation, "")
        self.assertEqual(bootstrap.state.snapshot_runtime_state_manifest, {})
        self.assertFalse(bootstrap.state.runtime_state_generation_marker_written)
        self.assertEqual(calls, [])

    def test_finalize_writer_exception_fail_closed(self) -> None:
        _write_prescan(self.root_dir)

        def _boom_writer(root_dir: str, **kwargs: Any) -> str:
            raise RuntimeError("boom")

        bootstrap, calls = _make_bootstrap(
            self.root_dir,
            writer=_boom_writer,
            manifest_files=("prescan_custom_nodes.json", "gpu_capacity_frozen.json"),
        )
        gen = bootstrap.finalize_runtime_state_generation()
        self.assertEqual(gen, "")
        self.assertEqual(bootstrap.state.snapshot_runtime_state_generation, "")
        self.assertEqual(bootstrap.state.snapshot_runtime_state_manifest, {})
        self.assertFalse(bootstrap.state.runtime_state_generation_marker_written)
        self.assertEqual(calls, [])

    def test_finalize_path_unavailable_fail_closed(self) -> None:
        config = BootstrapConfig(comfyui_root="/root/comfy/ComfyUI")
        bootstrap = RuntimeBootstrap(config)
        gen = bootstrap.finalize_runtime_state_generation()
        self.assertEqual(gen, "")
        self.assertEqual(bootstrap.state.snapshot_runtime_state_generation, "")
        self.assertEqual(bootstrap.state.snapshot_runtime_state_manifest, {})

    def test_finalize_then_restore_skip_roundtrip(self) -> None:
        # Full realistic cycle: construction finalize -> restore exact match.
        _write_prescan(self.root_dir)
        bootstrap, calls = _make_bootstrap(
            self.root_dir,
            manifest_files=("prescan_custom_nodes.json", "gpu_capacity_frozen.json"),
        )
        bootstrap.finalize_runtime_state_generation()
        gen = bootstrap.state.snapshot_runtime_state_generation
        out = _run_restore(bootstrap)
        self.assertEqual(calls, [])
        self.assertIn("decision=skipped_generation_match", _decision_line(out))
        self.assertTrue(gen)

    # ── Diagnostic reason accuracy ─────────────────────────────────────

    def test_diagnostic_reason_accurate(self) -> None:
        _write_prescan(self.root_dir)
        manifest = build_runtime_state_manifest(self.root_dir)
        write_runtime_state_generation_marker(
            self.root_dir, generation="c" * 32, files_manifest=manifest
        )
        bootstrap, calls = _make_bootstrap(
            self.root_dir, snapshot_generation="a" * 32, snapshot_manifest=manifest
        )
        out = _run_restore(bootstrap)
        line = _decision_line(out)
        self.assertIn("decision=reloaded_generation_mismatch", line)
        self.assertIn("reason=generation_mismatch", line)
        self.assertIn("callback_called=1", line)
        self.assertIn("runtime_state_reload_invoked=1", line)
        self.assertIn("check_ms=", line)
        self.assertEqual(calls.count("reload"), 1)

    # ── Cost ───────────────────────────────────────────────────────────

    def test_check_cost_reported_honestly(self) -> None:
        _write_prescan(self.root_dir)
        _write_gpu(self.root_dir)
        manifest = build_runtime_state_manifest(self.root_dir)
        gen = "a" * 32
        write_runtime_state_generation_marker(
            self.root_dir, generation=gen, files_manifest=manifest
        )
        bootstrap, calls = _make_bootstrap(
            self.root_dir, snapshot_generation=gen, snapshot_manifest=manifest
        )
        out = _run_restore(bootstrap)
        line = _decision_line(out)
        self.assertIn("check_ms=", line)
        check_ms = float(line.split("check_ms=")[-1].split(" ")[0])
        # Tiny local files: the whole local check must stay far below the
        # ~82 ms remote reload being replaced (generous CI-safe bound).
        self.assertLess(check_ms, 100.0)
        self.assertEqual(calls, [])

    def test_local_check_microbenchmark(self) -> None:
        """Microbenchmark of the full local decision (finalize + decide)."""
        import time as _time

        _write_prescan(self.root_dir)
        _write_gpu(self.root_dir)
        bootstrap, calls = _make_bootstrap(
            self.root_dir,
            manifest_files=("prescan_custom_nodes.json", "gpu_capacity_frozen.json"),
        )
        bootstrap.finalize_runtime_state_generation()
        n = 50
        decision: dict[str, Any] = {}
        t0 = _time.perf_counter()
        for _ in range(n):
            decision = bootstrap._decide_runtime_state_reload()
        total_ms = (_time.perf_counter() - t0) * 1000.0
        per_check_ms = total_ms / n
        self.assertEqual(decision["decision"], "skipped_generation_match")
        print(
            f"\n[bench] runtime_state_reload_check "
            f"median_ms_per_check~{per_check_ms:.4f} "
            f"total_{n}_checks_ms~{total_ms:.3f} "
            f"remote_reload_ms~82",
            flush=True,
        )
        # Looser bound than the CI-safe assertion above: locally sub-millisecond.
        self.assertLess(per_check_ms, 50.0)
        self.assertEqual(calls, [])


def read_runtime_state_generation_marker(root_dir: str) -> Any:
    from comfymodal_runtime.runtime_generation import (
        read_runtime_state_generation_marker as _impl,
    )

    return _impl(root_dir)


def verify_runtime_state_manifest(root_dir: str, expected: dict[str, Any]) -> tuple[bool, str]:
    from comfymodal_runtime.runtime_generation import (
        verify_runtime_state_manifest as _impl,
    )

    return _impl(root_dir, expected)


if __name__ == "__main__":
    unittest.main()
