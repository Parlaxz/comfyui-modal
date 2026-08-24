"""R44A — runtime-state generation semantic-identity determinism tests.

Two independent constructions whose correctness-relevant files differ ONLY in
volatile/diagnostic fields (gpu marketing name, capture timestamps, prescan
updated_at) and serialization (key order, whitespace) must derive the SAME
generation token and manifest.  Any change to a load-bearing value (VRAM
capacity, custom-node generation) must change the generation.  Every real
divergence still fails closed.
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
    _content_derived_generation,
    _identity_sha256_file,
    _semantic_identity_bytes,
    build_runtime_state_manifest,
    read_runtime_state_generation_marker,
    verify_runtime_state_manifest,
    write_runtime_state_generation_marker,
)

PRESCAN_A: dict[str, Any] = {
    "schema_version": "1",
    "custom_node_generation": "cnG",
    "generation_source": "observe_generations",
    "deployment_combined_hash": "depH",
    "updated_at": 1000.5,
}
GPU_A: dict[str, Any] = {
    "gpu_name": "NVIDIA RTX PRO 6000 Blackwell Server Edition",
    "total_vram_mib": 97887,
    "source": "nvidia-smi",
    "captured_at": 1000.5,
}
GPU_B: dict[str, Any] = {
    "captured_at": 9999.25,
    "total_vram_mib": 97887,
    "source": "nvidia-smi",
    "gpu_name": "NVIDIA RTX PRO 6000 Blackwell MAX-Q SE",
}


def _prescan_b_bytes() -> bytes:
    reordered = {
        "deployment_combined_hash": "depH",
        "generation_source": "observe_generations",
        "custom_node_generation": "cnG",
        "schema_version": "1",
        "updated_at": 9999.25,
    }
    return json.dumps(reordered, indent=2).encode("utf-8")


def _prescan_a_bytes() -> bytes:
    return json.dumps(PRESCAN_A, separators=(", ", ": ")).encode("utf-8")


def _gpu_a_bytes() -> bytes:
    return json.dumps(GPU_A).encode("utf-8")


def _gpu_b_bytes() -> bytes:
    return json.dumps(GPU_B).encode("utf-8")


def _write_bytes(path: str, content: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(content)


def _read_bytes(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


def _populate(root_dir: str, *, prescan: bytes, gpu: bytes) -> None:
    _write_bytes(os.path.join(root_dir, "prescan_custom_nodes.json"), prescan)
    _write_bytes(os.path.join(root_dir, "gpu_capacity_frozen.json"), gpu)


def _make_production_bootstrap(root_dir: str) -> RuntimeBootstrap:
    config = BootstrapConfig(
        comfyui_root="/root/comfy/ComfyUI",
        models_path="/root/models",
        custom_nodes_path="/root/custom_nodes_vol",
        prescan_record_path=os.path.join(root_dir, "prescan_custom_nodes.json"),
        runtime_state_generation_path=os.path.join(
            root_dir, RUNTIME_STATE_GENERATION_FILENAME
        ),
    )
    return RuntimeBootstrap(config)


def _finalize_production(root_dir: str) -> tuple[RuntimeBootstrap, str]:
    bootstrap = _make_production_bootstrap(root_dir)
    buf = io.StringIO()
    with redirect_stdout(buf):
        gen = bootstrap.finalize_runtime_state_generation()
    return bootstrap, gen


class R44AGenerationDeterminismTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = self._tmp.name

    def _fresh_root(self, name: str) -> str:
        root = os.path.join(self.base, name)
        os.makedirs(root, exist_ok=True)
        return root

    # ── 1. Independent constructions ───────────────────────────────────

    def test_independent_constructions_same_generation(self) -> None:
        root_a = self._fresh_root("rootA")
        root_b = self._fresh_root("rootB")
        _populate(root_a, prescan=_prescan_a_bytes(), gpu=_gpu_a_bytes())
        _populate(root_b, prescan=_prescan_b_bytes(), gpu=_gpu_b_bytes())
        boot_a, gen_a = _finalize_production(root_a)
        boot_b, gen_b = _finalize_production(root_b)
        self.assertTrue(gen_a)
        self.assertTrue(gen_b)
        self.assertEqual(gen_a, gen_b)
        manifest_a = boot_a.state.snapshot_runtime_state_manifest
        manifest_b = boot_b.state.snapshot_runtime_state_manifest
        self.assertEqual(manifest_a, manifest_b)
        gpu_raw_b = _read_bytes(os.path.join(root_b, "gpu_capacity_frozen.json"))
        self.assertIn(b"MAX-Q SE", gpu_raw_b)
        self.assertIn(b"9999.25", gpu_raw_b)
        prescan_raw_b = _read_bytes(
            os.path.join(root_b, "prescan_custom_nodes.json")
        )
        self.assertIn(b"9999.25", prescan_raw_b)
        gpu_raw_a = _read_bytes(os.path.join(root_a, "gpu_capacity_frozen.json"))
        self.assertIn(b"Server Edition", gpu_raw_a)
        self.assertIn(b"1000.5", gpu_raw_a)

    # ── 2/3. Load-bearing changes must change the generation ──────────

    def test_semantic_capacity_change_changes_generation(self) -> None:
        root_a = self._fresh_root("rootA")
        root_c = self._fresh_root("rootC")
        _populate(root_a, prescan=_prescan_a_bytes(), gpu=_gpu_a_bytes())
        gpu_c = dict(GPU_A)
        gpu_c["total_vram_mib"] = 81510
        _populate(root_c, prescan=_prescan_a_bytes(), gpu=json.dumps(gpu_c).encode())
        _, gen_a = _finalize_production(root_a)
        _, gen_c = _finalize_production(root_c)
        self.assertTrue(gen_a)
        self.assertTrue(gen_c)
        self.assertNotEqual(gen_a, gen_c)

    def test_prescan_source_change_changes_generation(self) -> None:
        root_a = self._fresh_root("rootA")
        root_d = self._fresh_root("rootD")
        _populate(root_a, prescan=_prescan_a_bytes(), gpu=_gpu_a_bytes())
        prescan_d = dict(PRESCAN_A)
        prescan_d["custom_node_generation"] = "cnG2"
        _populate(root_d, prescan=json.dumps(prescan_d).encode(), gpu=_gpu_a_bytes())
        _, gen_a = _finalize_production(root_a)
        _, gen_d = _finalize_production(root_d)
        self.assertTrue(gen_a)
        self.assertTrue(gen_d)
        self.assertNotEqual(gen_a, gen_d)

    # ── 4. Volatile-only drift is an exact match ───────────────────────

    def test_volatile_only_drift_is_exact_match(self) -> None:
        root_a = self._fresh_root("rootA")
        root_b = self._fresh_root("rootB")
        _populate(root_a, prescan=_prescan_a_bytes(), gpu=_gpu_a_bytes())
        _populate(root_b, prescan=_prescan_b_bytes(), gpu=_gpu_b_bytes())
        manifest_a = build_runtime_state_manifest(root_a)
        _populate(root_a, prescan=_prescan_b_bytes(), gpu=_gpu_b_bytes())
        ok, reason = verify_runtime_state_manifest(root_a, manifest_a)
        self.assertEqual((ok, reason), (True, "exact_match"))

    # ── 5. Real mismatches fail closed ─────────────────────────────────

    def test_real_mismatch_still_fail_closed(self) -> None:
        root_a = self._fresh_root("rootA")
        _populate(root_a, prescan=_prescan_a_bytes(), gpu=_gpu_a_bytes())
        manifest_a = build_runtime_state_manifest(root_a)
        prescan_path = os.path.join(root_a, "prescan_custom_nodes.json")
        gpu_path = os.path.join(root_a, "gpu_capacity_frozen.json")

        gpu_changed = dict(GPU_A)
        gpu_changed["total_vram_mib"] = 81510
        _write_bytes(gpu_path, json.dumps(gpu_changed).encode())
        self.assertEqual(
            verify_runtime_state_manifest(root_a, manifest_a),
            (False, "manifest_hash_mismatch"),
        )

        os.remove(prescan_path)
        self.assertEqual(
            verify_runtime_state_manifest(root_a, manifest_a),
            (False, "manifest_file_missing"),
        )

        os.remove(gpu_path)
        self.assertEqual(
            verify_runtime_state_manifest(root_a, manifest_a),
            (False, "manifest_file_missing"),
        )

        expected_absent_gpu = dict(manifest_a)
        expected_absent_gpu["gpu_capacity_frozen.json"] = {"present": False}
        _write_bytes(prescan_path, _prescan_a_bytes())
        _write_bytes(gpu_path, _gpu_a_bytes())
        self.assertEqual(
            verify_runtime_state_manifest(root_a, expected_absent_gpu),
            (False, "manifest_file_unexpected"),
        )

        _write_bytes(prescan_path, b"not-json{{{")
        self.assertEqual(
            verify_runtime_state_manifest(root_a, manifest_a),
            (False, "manifest_hash_mismatch"),
        )

    # ── 6. Key order / whitespace only ─────────────────────────────────

    def test_key_order_and_whitespace_only_no_identity_change(self) -> None:
        root_a = self._fresh_root("rootA")
        root_e = self._fresh_root("rootE")
        compact = json.dumps(GPU_A, sort_keys=True, separators=(",", ":")).encode()
        pretty = json.dumps(
            dict(reversed(list(GPU_A.items()))), indent=4
        ).encode()
        self.assertNotEqual(compact, pretty)
        identity_compact = _semantic_identity_bytes(
            "gpu_capacity_frozen.json", compact
        )
        identity_pretty = _semantic_identity_bytes(
            "gpu_capacity_frozen.json", pretty
        )
        self.assertEqual(identity_compact, identity_pretty)
        _populate(root_a, prescan=_prescan_a_bytes(), gpu=compact)
        _populate(root_e, prescan=_prescan_a_bytes(), gpu=pretty)
        manifest_a = build_runtime_state_manifest(root_a)
        manifest_e = build_runtime_state_manifest(root_e)
        self.assertEqual(
            manifest_a["gpu_capacity_frozen.json"]["sha256"],
            manifest_e["gpu_capacity_frozen.json"]["sha256"],
        )
        self.assertEqual(
            _content_derived_generation(manifest_a),
            _content_derived_generation(manifest_e),
        )

    # ── 7. Unparseable file falls back to raw bytes ────────────────────

    def test_unparseable_file_falls_back_to_raw_bytes(self) -> None:
        scratch = self._fresh_root("scratch")
        path_x = os.path.join(scratch, "x.bin")
        path_y = os.path.join(scratch, "y.bin")
        raw_x = b"\x00not-json{{{"
        raw_y = b"\x00not-json}}}"
        _write_bytes(path_x, raw_x)
        sha_x1 = _identity_sha256_file("prescan_custom_nodes.json", path_x)
        sha_x2 = _identity_sha256_file("prescan_custom_nodes.json", path_x)
        self.assertEqual(sha_x1, sha_x2)
        _write_bytes(path_y, raw_y)
        sha_y = _identity_sha256_file("prescan_custom_nodes.json", path_y)
        self.assertNotEqual(sha_x1, sha_y)

    # ── 8. Marker payload shape ────────────────────────────────────────

    def test_marker_payload_shape(self) -> None:
        root_a = self._fresh_root("rootA")
        _populate(root_a, prescan=_prescan_a_bytes(), gpu=_gpu_a_bytes())
        bootstrap, gen = _finalize_production(root_a)
        payload = read_runtime_state_generation_marker(root_a)
        self.assertIsInstance(payload, dict)
        assert payload is not None
        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(payload["generation"], gen)
        self.assertEqual(
            payload["files"], bootstrap.state.snapshot_runtime_state_manifest
        )
        with open(
            os.path.join(root_a, RUNTIME_STATE_GENERATION_FILENAME),
            "r",
            encoding="utf-8",
        ) as fh:
            raw_marker = json.load(fh)
        self.assertIn("updated_at_unix", raw_marker)

    # ── 9. Reload decision across independent constructions ────────────

    def test_decide_reload_skips_across_constructions(self) -> None:
        root_a = self._fresh_root("rootA")
        root_b = self._fresh_root("rootB")
        _populate(root_a, prescan=_prescan_a_bytes(), gpu=_gpu_a_bytes())
        _populate(root_b, prescan=_prescan_b_bytes(), gpu=_gpu_b_bytes())
        bootstrap_a, gen_a = _finalize_production(root_a)
        _, gen_b = _finalize_production(root_b)
        self.assertTrue(gen_a)
        self.assertEqual(gen_a, gen_b)

        marker_b = _read_bytes(os.path.join(root_b, RUNTIME_STATE_GENERATION_FILENAME))
        _write_bytes(
            os.path.join(root_a, "prescan_custom_nodes.json"), _prescan_b_bytes()
        )
        _write_bytes(os.path.join(root_a, "gpu_capacity_frozen.json"), _gpu_b_bytes())
        _write_bytes(os.path.join(root_a, RUNTIME_STATE_GENERATION_FILENAME), marker_b)

        buf = io.StringIO()
        with redirect_stdout(buf):
            decision = bootstrap_a._decide_runtime_state_reload()
        self.assertEqual(decision["decision"], "skipped_generation_match")
        self.assertEqual(decision["reason"], "exact_match")

        gpu_changed = dict(GPU_B)
        gpu_changed["total_vram_mib"] = 81510
        _write_bytes(
            os.path.join(root_a, "gpu_capacity_frozen.json"),
            json.dumps(gpu_changed).encode(),
        )
        fresh_manifest = build_runtime_state_manifest(root_a)
        buf = io.StringIO()
        with redirect_stdout(buf):
            write_runtime_state_generation_marker(
                root_a, files_manifest=fresh_manifest
            )
        buf = io.StringIO()
        with redirect_stdout(buf):
            decision = bootstrap_a._decide_runtime_state_reload()
        self.assertEqual(decision["decision"], "reloaded_generation_mismatch")


if __name__ == "__main__":
    unittest.main()
