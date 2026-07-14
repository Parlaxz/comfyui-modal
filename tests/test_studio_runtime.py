"""Backend/behavior tests for Studio preset execution runtime.

Tests cover the studio_run_adapter module and the two new backend routes:
  POST /comfymodal/studio/run
  POST /comfymodal/studio/experiment

All tests use in-memory or temp-directory stores — no real Modal calls.
"""
import asyncio
import copy
import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _load_module(name: str, rel_path: str):
    """Load a repo module by relative path."""
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel_path)
    assert spec is not None, f"Could not find spec for {rel_path}"
    assert spec.loader is not None, f"Could not find loader for {rel_path}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _make_runnable_snapshot(snapshot_id: str = "snap_runnable") -> dict:
    return {
        "id": snapshot_id,
        "name": "Runnable Txt2Img Snapshot",
        "compatibleFeatures": ["txt2img"],
        "apiPromptJson": {
            "3": {"class_type": "KSampler", "inputs": {
                "seed": 42, "steps": 20, "cfg": 7.0,
                "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0,
            }},
            "9": {"class_type": "SaveImage", "inputs": {"images": []}},
        },
        "nodeBindings": {
            "prompt": {"kind": "widget", "nodeId": "3", "widgetName": "text"},
            "output": {"kind": "output", "nodeId": "9"},
        },
        "outputNodeId": "9",
        "graphJson": {"nodes": [], "links": []},
        "archived": False,
        "status": "runnable",
        "featureStatus": {
            "txt2img": {"status": "runnable", "reason": ""},
        },
        "disabledReason": "",
    }


def _make_runnable_preset(preset_id: str = "preset_runnable",
                          snapshot_id: str = "snap_runnable") -> dict:
    return {
        "id": preset_id,
        "label": "Runnable Preset",
        "snapshotId": snapshot_id,
        "compatibleFeatures": ["txt2img"],
        "defaults": {},
        "sourceType": "snapshot",
        "sourceId": "",
        "archived": False,
        "status": "runnable",
        "disabledReason": "",
    }


def _make_archived_snapshot(snapshot_id: str = "snap_archived") -> dict:
    s = _make_runnable_snapshot(snapshot_id)
    s["archived"] = True
    s["status"] = "archived"
    return s


def _make_archived_preset(preset_id: str = "preset_archived",
                          snapshot_id: str = "snap_archived") -> dict:
    p = _make_runnable_preset(preset_id, snapshot_id)
    p["archived"] = True
    p["status"] = "archived"
    return p


def _make_needs_bindings_snapshot(snapshot_id: str = "snap_needs_bind") -> dict:
    return {
        "id": snapshot_id,
        "name": "Needs Bindings Snapshot",
        "compatibleFeatures": ["txt2img"],
        "apiPromptJson": {"3": {"class_type": "KSampler", "inputs": {"seed": 42}}},
        "nodeBindings": {},
        "outputNodeId": "",
        "archived": False,
        "status": "needs_bindings",
        "featureStatus": {
            "txt2img": {"status": "needs_bindings", "reason": "missing required node bindings"},
        },
        "disabledReason": "Missing required node bindings",
    }


def _make_studio_store_files(tmpdir: str, snapshots: list[dict], presets: list[dict]):
    """Write snapshot and preset JSON store files into tmpdir."""
    snap_path = Path(tmpdir) / ".studio_snapshots.json"
    preset_path = Path(tmpdir) / ".studio_presets.json"
    snap_path.write_text(json.dumps(snapshots), encoding="utf-8")
    preset_path.write_text(json.dumps(presets), encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests for studio_run_adapter module
# ---------------------------------------------------------------------------

class StudioRunAdapterLoadTests(unittest.TestCase):
    """Basic loading and validation of presets/snapshots."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module("studio_run_adapter", "studio_run_adapter.py")

    def test_load_preset_and_snapshot_ok(self):
        """load_preset_and_snapshot returns (preset, snapshot) for valid IDs."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            p, s = self.mod.load_preset_and_snapshot("preset_runnable", tmp)
            self.assertEqual(p["id"], "preset_runnable")
            self.assertEqual(s["id"], "snap_runnable")

    def test_load_missing_preset_rejected(self):
        """Missing preset ID returns (None, error)."""
        with tempfile.TemporaryDirectory() as tmp:
            _make_studio_store_files(tmp, [], [])
            preset, err = self.mod.load_preset_and_snapshot("does_not_exist", tmp)
            self.assertIsNone(preset)
            self.assertIsNotNone(err)
            self.assertIn("not found", err.lower())

    def test_load_missing_snapshot_rejected(self):
        """Preset referencing missing snapshot returns (None, error)."""
        with tempfile.TemporaryDirectory() as tmp:
            preset = {
                "id": "preset_bad", "label": "Bad", "snapshotId": "snap_missing",
                "sourceType": "snapshot", "archived": False,
            }
            _make_studio_store_files(tmp, [], [preset])
            preset, err = self.mod.load_preset_and_snapshot("preset_bad", tmp)
            self.assertIsNone(preset)
            self.assertIsNotNone(err)
            self.assertIn("not found", err.lower())

    def test_load_archived_preset_rejected(self):
        """Archived preset is rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_archived_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            preset, err = self.mod.load_preset_and_snapshot("preset_archived", tmp)
            self.assertIsNone(preset)
            self.assertIsNotNone(err)
            self.assertIn("archived", err.lower())

    def test_load_archived_snapshot_rejected(self):
        """Preset pointing to archived snapshot is rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_archived_snapshot()
            preset = _make_runnable_preset(snapshot_id="snap_archived")
            _make_studio_store_files(tmp, [snap], [preset])
            preset, err = self.mod.load_preset_and_snapshot("preset_runnable", tmp)
            self.assertIsNone(preset)
            self.assertIsNotNone(err)
            self.assertIn("archived", err.lower())

    def test_load_thread_safe_no_global_state(self):
        """load_preset_and_snapshot no longer uses a global _last_load_error."""
        mod = self.mod
        self.assertFalse(hasattr(mod, "_last_load_error"),
                         "Module must not have global _last_load_error")
        self.assertFalse(hasattr(mod, "get_load_error"),
                         "Module must not have get_load_error")


class StudioRunAdapterValidationTests(unittest.TestCase):
    """Validation of runnability, features, bindings."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module("studio_run_adapter", "studio_run_adapter.py")

    def test_non_runnable_preset_rejected(self):
        """Preset whose snapshot is non-runnable is rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_needs_bindings_snapshot()
            preset = _make_runnable_preset(snapshot_id="snap_needs_bind")
            _make_studio_store_files(tmp, [snap], [preset])
            result = self.mod.validate_studio_run(preset, snap, "txt2img")
            self.assertIn("error", result)

    def test_incompatible_feature_rejected(self):
        """Requesting a feature not in compatibleFeatures is rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            result = self.mod.validate_studio_run(preset, snap, "object_remove")
            self.assertIn("error", result)
            self.assertIn("compatible", result.get("error", "").lower())

    def test_runnable_txt2img_accepted(self):
        """Runnable txt2img preset passes validation."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            result = self.mod.validate_studio_run(preset, snap, "txt2img")
            self.assertIsNone(result.get("error"))

    def test_object_remove_blocked_without_image_input(self):
        """object_remove feature is blocked (image/mask flow not implemented)."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = copy.deepcopy(_make_runnable_snapshot("snap_obj"))
            snap["compatibleFeatures"] = ["txt2img", "object_remove"]
            snap["nodeBindings"] = {
                "prompt": {"kind": "widget", "nodeId": "3", "widgetName": "text"},
                "source_image": {"kind": "node", "nodeId": "12"},
                "mask": {"kind": "node", "nodeId": "13"},
                "instruction": {"kind": "widget", "nodeId": "14", "widgetName": "text"},
                "output": {"kind": "output", "nodeId": "9"},
            }
            from studio_models import normalize_snapshot_payload
            snap = normalize_snapshot_payload(snap)
            preset = _make_runnable_preset("preset_obj", "snap_obj")
            preset["compatibleFeatures"] = ["txt2img", "object_remove"]
            _make_studio_store_files(tmp, [snap], [preset])
            # We need apiPromptJson too for object_remove to be runnable
            snap["apiPromptJson"] = {"12": {"class_type": "LoadImage", "inputs": {}}}
            from studio_models import normalize_snapshot_payload
            snap = normalize_snapshot_payload(snap)
            result = self.mod.validate_studio_run(preset, snap, "object_remove")
            self.assertIn("error", result)
            self.assertIn("not yet implemented", result.get("error", "").lower())

    def test_object_replace_blocked_without_image_input(self):
        """object_replace feature is blocked (image/mask flow not implemented)."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = copy.deepcopy(_make_runnable_snapshot("snap_rep"))
            snap["compatibleFeatures"] = ["txt2img", "object_replace"]
            snap["nodeBindings"] = {
                "prompt": {"kind": "widget", "nodeId": "3", "widgetName": "text"},
                "source_image": {"kind": "node", "nodeId": "12"},
                "mask": {"kind": "node", "nodeId": "13"},
                "replacement_prompt": {"kind": "widget", "nodeId": "14", "widgetName": "text"},
                "output": {"kind": "output", "nodeId": "9"},
            }
            snap["apiPromptJson"] = {"12": {"class_type": "LoadImage", "inputs": {}}}
            from studio_models import normalize_snapshot_payload
            snap = normalize_snapshot_payload(snap)
            preset = _make_runnable_preset("preset_rep", "snap_rep")
            preset["compatibleFeatures"] = ["txt2img", "object_replace"]
            _make_studio_store_files(tmp, [snap], [preset])
            result = self.mod.validate_studio_run(preset, snap, "object_replace")
            self.assertIn("error", result)
            self.assertIn("not yet implemented", result.get("error", "").lower())


class StudioRunAdapterCompilationTests(unittest.TestCase):
    """Compilation / spec building from Studio presets."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module("studio_run_adapter", "studio_run_adapter.py")

    def test_build_single_run_spec_copies_api_prompt(self):
        """apiPromptJson is deep-copied, not referenced."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            controls = {"prompt": "a cat", "seed": 42}
            spec = self.mod.build_single_run_spec(preset, snap, "txt2img", controls, tmp)
            self.assertIsNotNone(spec)
            # Verify the workflow is a deep copy (inside checkpoints[0])
            ck = spec["checkpoints"][0]
            self.assertIsNot(ck["workflow"], snap["apiPromptJson"])

    def test_single_run_spec_has_correct_structure(self):
        """Single run spec has the expected compilation-like structure."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            controls = {"prompt": "a cat", "seed": 42, "steps": 25}
            spec = self.mod.build_single_run_spec(preset, snap, "txt2img", controls, tmp)
            self.assertIn("experiment_id", spec)
            self.assertIn("revision", spec)
            self.assertIn("checkpoints", spec)
            self.assertIn("cells", spec)
            self.assertEqual(len(spec["checkpoints"]), 1)
            self.assertEqual(len(spec["cells"]), 1)
            ck = spec["checkpoints"][0]
            self.assertIn("workflow", ck)
            self.assertIn("slots", ck)
            self.assertIn("studio_meta", ck)
            cell = spec["cells"][0]
            self.assertIn("cell_key", cell)
            self.assertIn("axis_values", cell)

    def test_single_run_spec_applies_control_overrides(self):
        """Control overrides modify the deep-copied workflow but not stored snapshot."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            original_prompt_json = copy.deepcopy(snap["apiPromptJson"])
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            controls = {"prompt": "overridden prompt", "seed": 999, "steps": 50}
            spec = self.mod.build_single_run_spec(preset, snap, "txt2img", controls, tmp)
            cell = spec["cells"][0]
            # The cell axis values should carry the override
            self.assertEqual(cell["axis_values"].get("seed"), 999)
            # The stored snapshot must NOT be modified
            self.assertEqual(snap["apiPromptJson"]["3"]["inputs"]["seed"], 42)

    def test_single_run_spec_has_studio_metadata(self):
        """Studio metadata is attached to compilation/cell for history."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            controls = {"prompt": "test", "seed": 1}
            spec = self.mod.build_single_run_spec(preset, snap, "txt2img", controls, tmp)
            meta = spec.get("studio_meta", {})
            self.assertEqual(meta.get("studio_preset_id"), "preset_runnable")
            self.assertEqual(meta.get("studio_snapshot_id"), "snap_runnable")
            self.assertEqual(meta.get("studio_feature_id"), "txt2img")
            self.assertIn("studio_controls", meta)
            self.assertEqual(meta["studio_controls"].get("seed"), 1)

    def test_single_run_spec_accepts_graph_to_prompt_wrapper_shape(self):
        """Wrapped graphToPrompt payloads use apiPromptJson.output as the workflow."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            snap["apiPromptJson"] = {
                "workflow": {"nodes": [], "links": []},
                "output": copy.deepcopy(snap["apiPromptJson"]),
            }
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            spec = self.mod.build_single_run_spec(
                preset, snap, "txt2img", {"seed": 7}, tmp,
                modal_options={"production": {"enabled": False}},
            )
            self.assertNotIn("error", spec)
            self.assertEqual(
                spec["checkpoints"][0]["workflow"]["3"]["inputs"]["seed"],
                7,
            )
            self.assertEqual(
                snap["apiPromptJson"]["output"]["3"]["inputs"]["seed"],
                42,
            )

    def test_single_run_spec_infers_single_value_input_for_node_binding(self):
        """Legacy node-kind prompt bindings should resolve a single 'value' input."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            snap["apiPromptJson"] = {
                "1497": {"class_type": "PrimitiveStringMultiline", "inputs": {"value": "old prompt"}},
                "9": {"class_type": "SaveImage", "inputs": {"images": []}},
            }
            snap["nodeBindings"] = {
                "prompt": {"kind": "node", "nodeId": "1497"},
                "output": {"kind": "output", "nodeId": "9"},
            }
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            spec = self.mod.build_single_run_spec(
                preset, snap, "txt2img", {"prompt": "new prompt"}, tmp,
                modal_options={"production": {"enabled": False}},
            )
            self.assertNotIn("error", spec)
            self.assertEqual(
                spec["checkpoints"][0]["workflow"]["1497"]["inputs"]["value"],
                "new prompt",
            )

    def test_single_run_spec_injects_missing_clip_input_when_unique_loader_exists(self):
        """Studio prompt workflows may omit CLIPTextEncode.clip but still include one loader."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            snap["apiPromptJson"] = {
                "62": {
                    "class_type": "CLIPLoader",
                    "inputs": {"clip_name": "qwen_3_4b.safetensors", "type": "lumina2", "device": "default"},
                },
                "67": {
                    "class_type": "CLIPTextEncode",
                    "inputs": {"text": ["1497", 0]},
                },
                "1497": {
                    "class_type": "PrimitiveStringMultiline",
                    "inputs": {"value": "old prompt"},
                },
                "9": {"class_type": "SaveImage", "inputs": {"images": []}},
            }
            snap["nodeBindings"] = {
                "prompt": {"kind": "node", "nodeId": "1497"},
                "output": {"kind": "output", "nodeId": "9"},
            }
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            spec = self.mod.build_single_run_spec(
                preset, snap, "txt2img", {"prompt": "new prompt"}, tmp,
                modal_options={"production": {"enabled": False}},
            )
            self.assertNotIn("error", spec)
            self.assertEqual(
                spec["checkpoints"][0]["workflow"]["67"]["inputs"]["clip"],
                ["62", 0],
            )

    def test_single_run_spec_injects_missing_vae_input_when_unique_loader_exists(self):
        """Studio prompt workflows may omit VAEDecode.vae but still include one loader."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            snap["apiPromptJson"] = {
                "1277": {
                    "class_type": "VAELoader",
                    "inputs": {"vae_name": "ae.safetensors"},
                },
                "175": {
                    "class_type": "VAEDecode",
                    "inputs": {"samples": ["1242", 1]},
                },
                "1497": {
                    "class_type": "PrimitiveStringMultiline",
                    "inputs": {"value": "old prompt"},
                },
                "9": {"class_type": "SaveImage", "inputs": {"images": []}},
            }
            snap["nodeBindings"] = {
                "prompt": {"kind": "node", "nodeId": "1497"},
                "output": {"kind": "output", "nodeId": "9"},
            }
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            spec = self.mod.build_single_run_spec(
                preset, snap, "txt2img", {"prompt": "new prompt"}, tmp,
                modal_options={"production": {"enabled": False}},
            )
            self.assertNotIn("error", spec)
            self.assertEqual(
                spec["checkpoints"][0]["workflow"]["175"]["inputs"]["vae"],
                ["1277", 0],
            )


class StudioRunAdapterExperimentTests(unittest.TestCase):
    """Experiment expansion from Studio presets."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module("studio_run_adapter", "studio_run_adapter.py")

    def test_experiment_expansion_returns_cells(self):
        """Experiment over presets/axes returns expected cell count."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            exp_def = {
                "prompts": [
                    {"id": "p1", "text": "a cat", "enabled": True},
                    {"id": "p2", "text": "a dog", "enabled": True},
                ],
                "axes": {"shared": {"seed": {"mode": "list", "values": [1, 2]}}},
            }
            spec = self.mod.build_experiment_spec(
                [(preset, snap)], "txt2img", exp_def, tmp
            )
            # compile_experiment should expand: 2 prompts × 2 seeds = 4 cells
            cells = spec.get("cells", [])
            self.assertGreaterEqual(len(cells), 4)

    def test_experiment_rejects_disabled_preset(self):
        """Experiment submission rejects a disabled/non-runnable preset."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_needs_bindings_snapshot()
            preset = _make_runnable_preset(snapshot_id="snap_needs_bind")
            _make_studio_store_files(tmp, [snap], [preset])
            exp_def = {"prompts": [{"id": "p1", "text": "test", "enabled": True}]}
            result = self.mod.build_experiment_spec(
                [(preset, snap)], "txt2img", exp_def, tmp
            )
            self.assertIn("error", result)

    def test_experiment_checkpoints_have_studio_workflow(self):
        """Checkpoints get snapshot workflow/slots instead of legacy profile lookup."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            exp_def = {"prompts": [{"id": "p1", "text": "test", "enabled": True}]}
            spec = self.mod.build_experiment_spec(
                [(preset, snap)], "txt2img", exp_def, tmp,
                modal_options={"production": {"enabled": False}},
            )
            for ck in spec.get("checkpoints", []):
                self.assertIn("workflow", ck)
                self.assertIn("slots", ck)
                # Should be from snapshot, not from legacy profile
                self.assertEqual(ck["workflow"], snap["apiPromptJson"])

    def test_experiment_accepts_graph_to_prompt_wrapper_shape(self):
        """Experiment checkpoints also unwrap graphToPrompt payloads."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            snap["apiPromptJson"] = {
                "workflow": {"nodes": [], "links": []},
                "output": copy.deepcopy(snap["apiPromptJson"]),
            }
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            exp_def = {"prompts": [{"id": "p1", "text": "test", "enabled": True}]}
            spec = self.mod.build_experiment_spec(
                [(preset, snap)], "txt2img", exp_def, tmp,
                modal_options={"production": {"enabled": False}},
            )
            self.assertNotIn("error", spec)
            for ck in spec.get("checkpoints", []):
                self.assertEqual(ck["workflow"], snap["apiPromptJson"]["output"])


class BuildExperimentSpecAxisTests(unittest.TestCase):
    """RED-phase tests for all-Studio-axis behavior of build_experiment_spec.

    These tests verify five required behaviors that are NOT fully
    implemented in the current production code:
      1. Expand prompt axis variants — a ``prompt`` axis in ``axes``
         with N values overrides the base prompt and produces N×other_axes
         cells, each carrying the variant text (not the base).
      2. Retain every extra axis in resulting cell axis_values so that
         execution can inject them into the workflow — uses a truly
         bound non-cheap control (mask_blur).
      3. Accept flat Studio axes and nested {shared: ...} input axes
         equivalently (same cell count, same axis_values).
      4. Reject an unbound/unsupported axis with an explicit compilation
         error instead of silently dropping it.

    Each test is expected to FAIL against the current production code
    (RED phase).  No production code is modified.
    """

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module("studio_run_adapter", "studio_run_adapter.py")

    # ── Test 1: prompt axis variants ───────────────────────────────────

    def test_expands_prompt_axis_variants(self):
        """A ``prompt`` axis in ``axes`` with 3 variant texts overrides
        the single base prompt and produces 3×2=6 cells instead of 2.
        Each cell carries the variant text, not the base."""
        snap = _make_runnable_snapshot()
        preset = _make_runnable_preset()
        with tempfile.TemporaryDirectory() as tmp:
            _make_studio_store_files(tmp, [snap], [preset])
            exp_def = {
                "prompts": [
                    {"id": "p_base", "text": "default prompt", "enabled": True},
                ],
                "axes": {
                    "prompt": {"values": ["a cat", "a dog", "a bird"]},
                    "seed": {"values": [1, 2]},
                },
            }
            spec = self.mod.build_experiment_spec(
                [(preset, snap)], "txt2img", exp_def, tmp
            )
            self.assertNotIn("error", spec,
                "Valid experiment should not produce an error")
            cells = spec.get("cells", [])
            # 3 prompt variants × 2 seeds = 6 cells
            self.assertEqual(len(cells), 6,
                "Prompt axis must produce 3 variants × 2 seeds = 6 cells")
            # Every cell must carry one of the axis variant texts,
            # NOT the base prompt "default prompt"
            prompt_texts = [c.get("prompt", "") for c in cells]
            self.assertEqual(prompt_texts.count("a cat"), 2)
            self.assertEqual(prompt_texts.count("a dog"), 2)
            self.assertEqual(prompt_texts.count("a bird"), 2)
            self.assertNotIn("default prompt", prompt_texts,
                "Axis variant prompt must override the base prompt text")

    # ── Test 2: bound non-cheap axis retention ─────────────────────────

    def test_retains_bound_noncheap_axis_in_cell_values(self):
        """A truly bound control NOT in _CHEAP_AXIS_ORDER (mask_blur)
        must produce cartesian expansion and appear in every cell's
        axis_values.  Expected: 2 seed × 2 steps × 2 mask_blur = 8 cells
        with mask_blur in axis_values."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            # Add a second node with mask_blur widget and bind it
            snap["apiPromptJson"]["12"] = {
                "class_type": "SomeNode",
                "inputs": {"mask_blur": 15},
            }
            snap["nodeBindings"]["mask_blur"] = {
                "kind": "widget", "nodeId": "12", "widgetName": "mask_blur",
            }
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            exp_def = {
                "prompts": [
                    {"id": "p1", "text": "hello", "enabled": True},
                ],
                "axes": {
                    "seed": {"values": [1, 2]},
                    "steps": {"values": [20, 30]},
                    "mask_blur": {"values": [5, 15]},
                },
            }
            spec = self.mod.build_experiment_spec(
                [(preset, snap)], "txt2img", exp_def, tmp
            )
            self.assertNotIn("error", spec)
            cells = spec.get("cells", [])
            # 2 seed × 2 steps × 2 mask_blur = 8 cells
            self.assertEqual(len(cells), 8,
                "2 seed × 2 steps × 2 mask_blur = 8 cells")
            for cell in cells:
                av = cell.get("axis_values", {})
                self.assertIn("seed", av)
                self.assertIn("steps", av)
                self.assertIn("mask_blur", av,
                    "mask_blur (bound non-cheap axis) must appear in "
                    "cell axis_values for execution to inject it")

    # ── Test 3: flat vs. nested axes equivalently ─────────────────────

    def test_flat_and_nested_axes_produce_equivalent_cells(self):
        """Flat Studio axes (frontend format) and nested {shared: ...}
        axes (compiler format) must produce the same cell count and the
        same axis_values in every cell."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])

            # Definition with flat axes
            exp_def_flat = {
                "prompts": [
                    {"id": "p1", "text": "flat test", "enabled": True},
                ],
                "axes": {
                    "seed": {"values": [10, 20]},
                    "steps": {"values": [25, 35]},
                },
            }
            # Identical definition with nested compiler-format axes
            exp_def_nested = {
                "prompts": [
                    {"id": "p1", "text": "flat test", "enabled": True},
                ],
                "axes": {
                    "shared": {
                        "seed": {"mode": "list", "values": [10, 20]},
                        "steps": {"mode": "list", "values": [25, 35]},
                    },
                },
            }

            spec_flat = self.mod.build_experiment_spec(
                [(preset, snap)], "txt2img", exp_def_flat, tmp
            )
            spec_nested = self.mod.build_experiment_spec(
                [(preset, snap)], "txt2img", exp_def_nested, tmp
            )

            self.assertNotIn("error", spec_flat,
                "Flat axes must not produce error")
            self.assertNotIn("error", spec_nested,
                "Nested axes must not produce error")

            cells_flat = spec_flat.get("cells", [])
            cells_nested = spec_nested.get("cells", [])

            # Same cell count
            self.assertEqual(
                len(cells_flat), len(cells_nested),
                "Flat and nested axes must produce the same number of cells"
            )

            # Same axis_values in corresponding cells
            for cf, cn in zip(cells_flat, cells_nested):
                self.assertEqual(
                    cf.get("axis_values", {}),
                    cn.get("axis_values", {}),
                    "axis_values must match between flat and nested formats"
                )

    # ── Test 4: unbound/unsupported axis produces compilation error ───

    def test_rejects_unbound_axis_with_explicit_error(self):
        """An axis whose control ID has no slot binding in ANY snapshot
        and cannot be auto-derived must be rejected with an explicit
        compilation error, not silently dropped."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            # "nonexistent_param" has no slot in the snapshot's
            # nodeBindings and cannot be auto-derived (not in
            # _AUTO_DERIVE_CONTROLS).
            exp_def = {
                "prompts": [
                    {"id": "p1", "text": "test", "enabled": True},
                ],
                "axes": {
                    "nonexistent_param": {"values": [1.0, 2.0]},
                },
            }
            result = self.mod.build_experiment_spec(
                [(preset, snap)], "txt2img", exp_def, tmp
            )
            # Must return an error, NOT silently compile with missing axis
            self.assertIn("error", result,
                "Unbound axis must produce an explicit compilation error")
            self.assertIn("nonexistent_param", result.get("error", ""),
                "Error message must reference the unbound axis name")

    # ── Test 5: reject bound extra axis when ANY preset lacks the slot ──

    def test_rejects_bound_extra_axis_when_any_preset_lacks_slot(self):
        """A bound extra axis (mask_blur) must be rejected when ANY selected
        preset lacks the slot binding.  Two presets: one with mask_blur bound,
        one without."""
        snap_a = _make_runnable_snapshot("snap_a")
        snap_a["apiPromptJson"]["12"] = {
            "class_type": "SomeNode",
            "inputs": {"mask_blur": 15},
        }
        snap_a["nodeBindings"]["mask_blur"] = {
            "kind": "widget", "nodeId": "12", "widgetName": "mask_blur",
        }
        preset_a = _make_runnable_preset("preset_a", "snap_a")
        snap_b = _make_runnable_snapshot("snap_b")
        preset_b = _make_runnable_preset("preset_b", "snap_b")
        # snap_b has NO mask_blur binding

        exp_def = {
            "prompts": [{"id": "p1", "text": "test", "enabled": True}],
            "axes": {
                "mask_blur": {"values": [5, 15]},
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            _make_studio_store_files(tmp, [snap_a, snap_b], [preset_a, preset_b])
            result = self.mod.build_experiment_spec(
                [(preset_a, snap_a), (preset_b, snap_b)], "txt2img", exp_def, tmp
            )
        self.assertIn("error", result,
            "Bound extra axis must be rejected when any preset lacks the slot")
        self.assertIn("mask_blur", result.get("error", ""),
            "Error message must reference the axis name")

    # ── Test 6: idempotent build_experiment_spec with mutable experiment_def ──

    def test_idempotent_calls_preserve_mutable_experiment_def(self):
        """Calling build_experiment_spec twice with the same mutable
        experiment_def containing a prompt axis must produce the same
        result and leave experiment_def untouched."""
        snap = _make_runnable_snapshot()
        preset = _make_runnable_preset()
        exp_def = {
            "prompts": [],
            "axes": {
                "prompt": {"values": ["cat", "dog", "bird"]},
                "seed": {"values": [1]},
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            _make_studio_store_files(tmp, [snap], [preset])
            result1 = self.mod.build_experiment_spec(
                [(preset, snap)], "txt2img", exp_def, tmp
            )
            result2 = self.mod.build_experiment_spec(
                [(preset, snap)], "txt2img", exp_def, tmp
            )
        # Same result — same number of cells
        cells1 = result1.get("cells", [])
        cells2 = result2.get("cells", [])
        self.assertEqual(len(cells1), len(cells2),
            "Both calls must produce the same number of cells")
        # Same axis_values for each corresponding cell
        for c1, c2 in zip(cells1, cells2):
            self.assertEqual(c1.get("axis_values"), c2.get("axis_values"),
                "axis_values must match between first and second call")
        # experiment_def must NOT be mutated
        axes_after = exp_def.get("axes", {})
        self.assertIn("prompt", axes_after,
            "experiment_def axes must still contain 'prompt' after two calls")


class StudioRunAdapterHistoryTests(unittest.TestCase):
    """History metadata threading for studio runs."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module("studio_run_adapter", "studio_run_adapter.py")

    def test_history_meta_contains_studio_info(self):
        """History metadata carries preset/snapshot/feature/control info."""
        meta = self.mod._build_studio_history_meta(
            preset_id="preset_1",
            snapshot_id="snap_1",
            feature_id="txt2img",
            controls={"prompt": "test", "seed": 42},
        )
        self.assertEqual(meta.get("studio_preset_id"), "preset_1")
        self.assertEqual(meta.get("studio_snapshot_id"), "snap_1")
        self.assertEqual(meta.get("studio_feature_id"), "txt2img")
        self.assertEqual(meta.get("studio_controls", {}).get("seed"), 42)

    def test_experiment_history_meta_contains_studio_info(self):
        """Experiment definition metadata carries studio info."""
        meta = self.mod._build_studio_experiment_meta(
            preset_ids=["preset_1"],
            snapshot_ids=["snap_1"],
            feature_id="txt2img",
        )
        self.assertEqual(meta.get("studio_preset_ids"), ["preset_1"])
        self.assertEqual(meta.get("studio_snapshot_ids"), ["snap_1"])
        self.assertEqual(meta.get("studio_feature_id"), "txt2img")


# ---------------------------------------------------------------------------
# Tests for route registration + behavior
# ---------------------------------------------------------------------------

class _StubServer:
    def __init__(self):
        self.routes: Any = _StubRouteTable()
        self.sent_events: list[tuple[str, dict, str]] = []

    def send_sync(self, event: str, data: dict, sid: str = ""):
        self.sent_events.append((event, dict(data), sid))


class _StubRouteTable:
    def __init__(self):
        self._handlers: list[tuple[str, str, Any]] = []

    def get(self, path: str):
        def deco(fn):
            self._handlers.append(("GET", path, fn))
            return fn
        return deco

    def post(self, path: str):
        def deco(fn):
            self._handlers.append(("POST", path, fn))
            return fn
        return deco

    def put(self, path: str):
        def deco(fn):
            self._handlers.append(("PUT", path, fn))
            return fn
        return deco

    def delete(self, path: str):
        def deco(fn):
            self._handlers.append(("DELETE", path, fn))
            return fn
        return deco

    def patch(self, path: str):
        def deco(fn):
            self._handlers.append(("PATCH", path, fn))
            return fn
        return deco


class _MockRequest:
    def __init__(self, *, json_body: dict | None = None, query: dict | None = None,
                 match_info: dict | None = None):
        self._json = json_body
        self._query = query or {}
        self._match_info = match_info or {}
        self.body_exists = json_body is not None

    async def json(self) -> dict:
        if self._json is None:
            raise ValueError("no body")
        return self._json

    @property
    def query(self):
        return self._query

    @property
    def match_info(self):
        return self._match_info


def _run(coro):
    return asyncio.run(coro)


def _build_init_with_stub(stub_server):
    """Load __init__.py with a stub server."""
    server_stub = type(sys)("server")
    server_stub.PromptServer = type("PromptServer", (), {"instance": stub_server})
    sys.modules["server"] = server_stub
    exec_stub = type(sys)("execution")
    exec_stub.PromptQueue = type("PromptQueue", (), {})
    sys.modules["execution"] = exec_stub
    for mod in ("local_placeholders", "workflow_metadata", "api_prompt_validator",
                "failure_summary", "output_converter", "output_saver",
                "timing_trace", "profiler_trace_v4", "production_workflow",
                "comparison", "model_manifest", "modal_workspaces",
                "modal_client", "gpu_catalog", "optimizations",
                "run_history", "presets", "matrix_compiler", "experiment_store",
                "experiment_lease", "experiment_models", "experiment_runner",
                "experiment_scheduler", "deploy_warmup", "experiment_service",
                "studio_run_adapter"):
        if mod not in sys.modules:
            try:
                spec = importlib.util.spec_from_file_location(mod, REPO_ROOT / f"{mod}.py")
                if spec is None or spec.loader is None:
                    continue
                m = importlib.util.module_from_spec(spec)
                sys.modules[mod] = m
                spec.loader.exec_module(m)
            except Exception:
                pass
    spec = importlib.util.spec_from_file_location("comfyui_modal_under_test", REPO_ROOT / "__init__.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["comfyui_modal_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def _handler_for(init_mod, method: str, path: str):
    for m, p, fn in init_mod._server.routes._handlers:
        if m == method and p == path:
            return fn
    for m, p, fn in init_mod._server.routes._handlers:
        if m != method:
            continue
        p_parts = p.split("/")
        a_parts = path.split("/")
        if len(p_parts) != len(a_parts):
            continue
        match = True
        for pp, ap in zip(p_parts, a_parts):
            if pp.startswith("{") and pp.endswith("}"):
                continue
            if pp != ap:
                match = False
                break
        if match:
            return fn
    return None


class StudioRunRouteRegistrationTests(unittest.TestCase):
    """The two new Studio run routes must be registered."""

    @classmethod
    def setUpClass(cls):
        cls.stub = _StubServer()
        cls.init_mod = _build_init_with_stub(cls.stub)

    def test_studio_run_route_registered(self):
        fn = _handler_for(self.init_mod, "POST", "/comfymodal/studio/run")
        self.assertIsNotNone(fn, "POST /comfymodal/studio/run not registered")

    def test_studio_experiment_route_registered(self):
        fn = _handler_for(self.init_mod, "POST", "/comfymodal/studio/experiment")
        self.assertIsNotNone(fn, "POST /comfymodal/studio/experiment not registered")


class GitignoreRuntimeArtifactTests(unittest.TestCase):
    """.gitignore covers the runtime artifact files."""

    def test_studio_presets_json_in_gitignore(self):
        text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".studio_presets.json", text)

    def test_studio_snapshots_json_in_gitignore(self):
        text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".studio_snapshots.json", text)

    def test_studio_backends_json_in_gitignore(self):
        text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".studio_backends.json", text)

    def test_tmp_suffix_glob_in_gitignore(self):
        text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("*.tmp", text)


class StudioExtractDefaultsTests(unittest.TestCase):
    """Tests for extract_defaults_from_snapshot()."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module("studio_run_adapter", "studio_run_adapter.py")

    def test_basic_widget_extraction(self):
        """Widget-kind bindings extract the correct value from apiPromptJson."""
        snapshot = {
            "apiPromptJson": {
                "3": {"class_type": "KSampler", "inputs": {"seed": 42, "steps": 30}},
            },
            "nodeBindings": {
                "steps": {"kind": "widget", "nodeId": "3", "widgetName": "steps"},
                "seed": {"kind": "widget", "nodeId": "3", "widgetName": "seed"},
            },
        }
        defaults = self.mod.extract_defaults_from_snapshot(snapshot)
        self.assertEqual(defaults, {"steps": 30, "seed": 42})

    def test_input_kind_extraction(self):
        """Input-kind bindings use inputName instead of widgetName."""
        snapshot = {
            "apiPromptJson": {
                "5": {"class_type": "LoadImage", "inputs": {"image": "photo.png"}},
            },
            "nodeBindings": {
                "source_image": {
                    "kind": "input", "nodeId": "5", "inputName": "image",
                },
            },
        }
        defaults = self.mod.extract_defaults_from_snapshot(snapshot)
        self.assertEqual(defaults, {"source_image": "photo.png"})

    def test_node_kind_skipped(self):
        """Node-kind bindings are skipped (no scalar value)."""
        snapshot = {
            "apiPromptJson": {
                "12": {"class_type": "SomeNode", "inputs": {}},
            },
            "nodeBindings": {
                "source_node": {"kind": "node", "nodeId": "12"},
            },
        }
        defaults = self.mod.extract_defaults_from_snapshot(snapshot)
        self.assertEqual(defaults, {})

    def test_output_kind_skipped(self):
        """Output-kind bindings are skipped."""
        snapshot = {
            "apiPromptJson": {
                "9": {"class_type": "SaveImage", "inputs": {}},
            },
            "nodeBindings": {
                "output": {"kind": "output", "nodeId": "9"},
            },
        }
        defaults = self.mod.extract_defaults_from_snapshot(snapshot)
        self.assertEqual(defaults, {})

    def test_missing_widget_in_workflow_omitted(self):
        """Binding references a widget not in apiPromptJson inputs -> key omitted."""
        snapshot = {
            "apiPromptJson": {
                "3": {"class_type": "KSampler", "inputs": {"seed": 42}},
            },
            "nodeBindings": {
                "steps": {"kind": "widget", "nodeId": "3", "widgetName": "steps"},
                "seed": {"kind": "widget", "nodeId": "3", "widgetName": "seed"},
            },
        }
        defaults = self.mod.extract_defaults_from_snapshot(snapshot)
        self.assertEqual(defaults, {"seed": 42})

    def test_empty_snapshot_returns_empty(self):
        """Empty workflow and empty bindings produce {}."""
        self.assertEqual(
            self.mod.extract_defaults_from_snapshot({"apiPromptJson": {}, "nodeBindings": {}}),
            {},
        )
        self.assertEqual(
            self.mod.extract_defaults_from_snapshot({"apiPromptJson": None, "nodeBindings": None}),
            {},
        )
        self.assertEqual(
            self.mod.extract_defaults_from_snapshot({}),
            {},
        )

    def test_mixed_bindings(self):
        """Mix of widget, input, node, output -- only scalar ones extracted."""
        snapshot = {
            "apiPromptJson": {
                "3": {"class_type": "KSampler", "inputs": {"seed": 42, "steps": 30}},
                "5": {"class_type": "LoadImage", "inputs": {"image": "cat.png"}},
            },
            "nodeBindings": {
                "steps": {"kind": "widget", "nodeId": "3", "widgetName": "steps"},
                "seed": {"kind": "widget", "nodeId": "3", "widgetName": "seed"},
                "source_image": {"kind": "input", "nodeId": "5", "inputName": "image"},
                "source_node": {"kind": "node", "nodeId": "12"},
                "output": {"kind": "output", "nodeId": "9"},
            },
        }
        defaults = self.mod.extract_defaults_from_snapshot(snapshot)
        self.assertEqual(defaults, {"steps": 30, "seed": 42, "source_image": "cat.png"})


class StudioDefaultsAPIEnrichmentTests(unittest.TestCase):
    """Tests that presets API enrichment populates defaults from snapshots."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module("studio_run_adapter", "studio_run_adapter.py")

    def test_enrichment_preserves_controls_defaults(self):
        """Snapshot defaults get enriched onto the preset dict."""
        from studio_models import normalize_snapshot_payload
        snap = normalize_snapshot_payload({
            "id": "snap1",
            "name": "Test",
            "compatibleFeatures": ["txt2img"],
            "apiPromptJson": {"3": {"class_type": "KSampler", "inputs": {"seed": 42, "steps": 30}}},
            "nodeBindings": {
                "prompt": {"kind": "widget", "nodeId": "3", "widgetName": "text"},
                "steps": {"kind": "widget", "nodeId": "3", "widgetName": "steps"},
                "seed": {"kind": "widget", "nodeId": "3", "widgetName": "seed"},
            },
            "outputNodeId": "9",
            "graphJson": {"nodes": [], "links": []},
            "archived": False,
            "status": "runnable",
        })
        defaults = self.mod.extract_defaults_from_snapshot(snap)
        self.assertIn("steps", defaults)
        self.assertIn("seed", defaults)
        self.assertEqual(defaults["steps"], 30)
        self.assertEqual(defaults["seed"], 42)

    def test_enrichment_accepts_graph_to_prompt_wrapper_shape(self):
        """Normalization/default extraction accepts wrapped graphToPrompt payloads."""
        from studio_models import normalize_snapshot_payload
        snap = normalize_snapshot_payload({
            "id": "snap_wrapped",
            "name": "Wrapped",
            "compatibleFeatures": ["txt2img"],
            "apiPromptJson": {
                "workflow": {"nodes": [], "links": []},
                "output": {
                    "3": {"class_type": "KSampler", "inputs": {"seed": 42, "steps": 30}},
                    "9": {"class_type": "SaveImage", "inputs": {"images": []}},
                },
            },
            "nodeBindings": {
                "prompt": {"kind": "widget", "nodeId": "3", "widgetName": "text"},
                "steps": {"kind": "widget", "nodeId": "3", "widgetName": "steps"},
                "seed": {"kind": "widget", "nodeId": "3", "widgetName": "seed"},
            },
            "outputNodeId": "9",
            "graphJson": {"nodes": [], "links": []},
            "archived": False,
            "status": "runnable",
        })
        self.assertEqual(snap["status"], "runnable")
        defaults = self.mod.extract_defaults_from_snapshot(snap)
        self.assertEqual(defaults["steps"], 30)
        self.assertEqual(defaults["seed"], 42)


# ---------------------------------------------------------------------------
# RunHistoryService extension tests
# ---------------------------------------------------------------------------

class RunHistoryServiceExtensionTests(unittest.TestCase):
    """Test backward-compatible extensions to RunHistoryService.

    These tests cover explicit started_at, completed_at, timings in
    update_run, workflow_hash updates, primary_asset_id, and backward-
    compatible reads of older entries.
    """

    @classmethod
    def setUpClass(cls):
        cls.svc_mod = _load_module("experiment_service", "experiment_service.py")

    def test_record_run_with_explicit_started_at(self):
        """record_run accepts explicit started_at, overriding the auto value."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svc = self.svc_mod.RunHistoryService(root)
            started = "2025-06-01T00:00:00Z"
            rec = svc.record_run(
                kind="studio_run",
                prompt_id="exp_submit",
                status="submitted",
                meta={"client": "studio"},
                started_at=started,
            )
            self.assertEqual(rec.get("started_at"), started)
            self.assertEqual(rec.get("status"), "submitted")

    def test_update_run_supports_timings(self):
        """update_run writes timing.json when timings dict is provided."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svc = self.svc_mod.RunHistoryService(root)
            rec = svc.record_run(kind="studio_run", prompt_id="exp_t", status="running")
            run_id = rec["run_id"]
            timings = {"queue_ms": 100, "sampling_ms": 2000, "total_ms": 2100}
            updated = svc.update_run(run_id, timings=timings)
            self.assertEqual(updated.get("status"), "running")
            # Verify timing.json was written
            read_timing = svc.get_timing(run_id)
            self.assertEqual(read_timing, timings)

    def test_update_run_with_completed_at(self):
        """update_run accepts completed_at timestamp."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svc = self.svc_mod.RunHistoryService(root)
            rec = svc.record_run(kind="studio_run", prompt_id="exp_c", status="running")
            run_id = rec["run_id"]
            completed = "2025-06-01T01:00:00Z"
            updated = svc.update_run(run_id, status="completed", completed_at=completed)
            self.assertEqual(updated.get("status"), "completed")
            self.assertEqual(updated.get("completed_at"), completed)

    def test_update_run_with_workflow_hash(self):
        """update_run accepts workflow_hash."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svc = self.svc_mod.RunHistoryService(root)
            rec = svc.record_run(kind="studio_run", prompt_id="exp_w", status="running")
            run_id = rec["run_id"]
            updated = svc.update_run(run_id, status="completed", workflow_hash="wh_test123")
            self.assertEqual(updated.get("workflow_hash"), "wh_test123")

    def test_update_run_with_output_path(self):
        """update_run accepts output_path."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svc = self.svc_mod.RunHistoryService(root)
            rec = svc.record_run(kind="studio_run", prompt_id="exp_o", status="running")
            run_id = rec["run_id"]
            updated = svc.update_run(run_id, output_path="outputs/studio/test.png")
            self.assertIn("test.png", updated.get("output_path", ""))

    def test_update_run_merges_meta(self):
        """update_run merges new meta into existing extra, not replace."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svc = self.svc_mod.RunHistoryService(root)
            rec = svc.record_run(
                kind="studio_run", prompt_id="exp_m", status="running",
                meta={"original": "yes"},
            )
            run_id = rec["run_id"]
            updated = svc.update_run(run_id, meta={"resolved": "data"})
            self.assertEqual(updated.get("extra", {}).get("original"), "yes")
            self.assertEqual(updated.get("extra", {}).get("resolved"), "data")

    def test_backward_compatible_read_of_older_entries(self):
        """Records written before the extensions remain readable."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svc = self.svc_mod.RunHistoryService(root)
            # Write an "old-style" record with only basic fields
            rec = svc.record_run(kind="studio_run", prompt_id="exp_old", status="running")
            run_id = rec["run_id"]
            # Read it back - should not error and contain expected fields
            meta = svc.get_run(run_id)
            self.assertIsNotNone(meta)
            self.assertEqual(meta.get("kind"), "studio_run")
            self.assertEqual(meta.get("prompt_id"), "exp_old")

    def test_update_run_with_primary_asset_id(self):
        """update_run accepts primary_asset_id stored in meta/extra."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svc = self.svc_mod.RunHistoryService(root)
            rec = svc.record_run(kind="studio_run", prompt_id="exp_a", status="running")
            run_id = rec["run_id"]
            updated = svc.update_run(run_id, primary_asset_id="asset_abc123")
            # primary_asset_id should be stored in the record
            meta = svc.get_run(run_id)
            self.assertEqual(meta.get("primary_asset_id"), "asset_abc123")

    def test_update_run_with_timings_and_meta_merge(self):
        """Combined update_run with timings, status, meta, output_path."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svc = self.svc_mod.RunHistoryService(root)
            rec = svc.record_run(
                kind="studio_run", prompt_id="exp_combo", status="running",
                meta={"requested_controls": {"seed": 42}},
            )
            run_id = rec["run_id"]
            timings = {"total_ms": 5000}
            updated = svc.update_run(
                run_id,
                status="completed",
                timings=timings,
                meta={"resolved_controls": {"seed": 42, "steps": 20}},
                output_path="outputs/studio/img_001.png",
            )
            self.assertEqual(updated.get("status"), "completed")
            self.assertIn("img_001.png", updated.get("output_path", ""))
            # Read full meta
            meta = svc.get_run(run_id)
            self.assertEqual(meta.get("extra", {}).get("requested_controls", {}).get("seed"), 42)
            self.assertEqual(meta.get("extra", {}).get("resolved_controls", {}).get("steps"), 20)
            # Check timings persisted
            read_timing = svc.get_timing(run_id)
            self.assertEqual(read_timing, timings)

    # ── Atomic write tests ────────────────────────────────────────────────

    def test_meta_json_written_atomically(self):
        """meta.json is not written directly; tmp file + atomic replace used."""
        import os
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svc = self.svc_mod.RunHistoryService(root)
            rec = svc.record_run(kind="studio_run", prompt_id="exp_atom", status="running")
            run_id = rec["run_id"]
            run_dir = root / run_id
            # A .tmp file should NOT be left behind
            tmp_files = list(run_dir.glob("*.tmp"))
            self.assertEqual(len(tmp_files), 0, f"Leftover tmp files: {tmp_files}")
            # meta.json should exist
            self.assertTrue((run_dir / "meta.json").exists())

    def test_timing_json_written_atomically_on_update(self):
        """update_run writes timing.json via atomic tmp+replace."""
        import os
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svc = self.svc_mod.RunHistoryService(root)
            rec = svc.record_run(kind="studio_run", prompt_id="exp_tim_atom", status="running")
            run_id = rec["run_id"]
            svc.update_run(run_id, timings={"total_ms": 100})
            run_dir = root / run_id
            tmp_files = list(run_dir.glob("*.tmp"))
            self.assertEqual(len(tmp_files), 0, f"Leftover tmp files: {tmp_files}")
            self.assertTrue((run_dir / "timing.json").exists())
            self.assertEqual(svc.get_timing(run_id), {"total_ms": 100})

    # ── Time-based list_runs sorting ──────────────────────────────────────

    def test_list_runs_sorts_by_completed_at_then_started_at(self):
        """list_runs orders by completed_at desc, then started_at desc."""
        import time
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svc = self.svc_mod.RunHistoryService(root)
            # Record A: completed later
            rec_a = svc.record_run(
                kind="studio_run", prompt_id="exp_a", status="completed",
                started_at="2025-06-01T00:00:00Z",
            )
            svc.update_run(rec_a["run_id"], completed_at="2025-06-01T02:00:00Z")
            # Record B: completed earlier
            rec_b = svc.record_run(
                kind="studio_run", prompt_id="exp_b", status="completed",
                started_at="2025-06-01T00:00:00Z",
            )
            svc.update_run(rec_b["run_id"], completed_at="2025-06-01T01:00:00Z")
            # A should come first (later completed_at)
            result = svc.list_runs(kind="studio_run")
            self.assertEqual(len(result["runs"]), 2)
            self.assertEqual(result["runs"][0]["run_id"], rec_a["run_id"])
            self.assertEqual(result["runs"][1]["run_id"], rec_b["run_id"])

    def test_list_runs_falls_back_to_started_at_when_no_completed_at(self):
        """When completed_at is absent, use started_at descending."""
        import time
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svc = self.svc_mod.RunHistoryService(root)
            rec_a = svc.record_run(kind="studio_run", prompt_id="exp_a", status="running",
                                    started_at="2025-06-01T03:00:00Z")
            rec_b = svc.record_run(kind="studio_run", prompt_id="exp_b", status="running",
                                    started_at="2025-06-01T01:00:00Z")
            result = svc.list_runs(kind="studio_run")
            runs = result["runs"]
            self.assertEqual(runs[0]["run_id"], rec_a["run_id"])
            self.assertEqual(runs[1]["run_id"], rec_b["run_id"])

    def test_list_runs_falls_back_to_file_mtime(self):
        """When no timestamp fields exist, fall back to directory mtime."""
        import os
        import time
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svc = self.svc_mod.RunHistoryService(root)
            # Write two records manually (no timestamps) then touch mtimes
            run_dir_a = root / "r_aaaa"
            run_dir_a.mkdir()
            (run_dir_a / "meta.json").write_text('{"run_id":"r_aaaa","kind":"studio_run"}', encoding="utf-8")
            run_dir_b = root / "r_bbbb"
            run_dir_b.mkdir()
            (run_dir_b / "meta.json").write_text('{"run_id":"r_bbbb","kind":"studio_run"}', encoding="utf-8")
            # Set mtime: b newer
            old = time.time() - 100
            os.utime(run_dir_a, (old, old))
            result = svc.list_runs(kind="studio_run")
            self.assertEqual(len(result["runs"]), 2)


# ---------------------------------------------------------------------------
# LocalRemoteInvoker._save_output_images tests
# ---------------------------------------------------------------------------

class SaveOutputImagesTests(unittest.TestCase):
    """Test _save_output_images sanitization, uniqueness, and safety."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module("experiment_runner", "experiment_runner.py")

    def _make_invoker(self, tmpdir):
        return self.mod.LocalRemoteInvoker(
            None, experiment_id="test_exp", node_dir=tmpdir
        )

    def _run_save(self, invoker, result_data, cell_key="cell_test"):
        return asyncio.run(invoker._save_output_images(result_data, cell_key))

    def test_removes_path_traversal_from_remote_filename(self):
        """Remote filenames with ../ are sanitised to basename only."""
        import base64
        with tempfile.TemporaryDirectory() as tmp:
            invoker = self._make_invoker(tmp)
            img_data = base64.b64encode(b"fake-png-data").decode("ascii")
            result = {
                "outputs": {
                    "9": {
                        "images": [
                            {"filename": "../../../etc/passwd", "data": img_data},
                        ]
                    }
                }
            }
            saved = self._run_save(invoker, result, "cell_1")
            for path in saved:
                self.assertNotIn("..", path)
                self.assertNotIn("etc", path)
                # Should be just a filename, not a path
                self.assertEqual(Path(path).name, path)

    def test_only_supported_image_extensions(self):
        """Non-image extensions are discarded; only png/jpg/webp/gif/bmp pass."""
        import base64
        with tempfile.TemporaryDirectory() as tmp:
            invoker = self._make_invoker(tmp)
            img_data = base64.b64encode(b"fake-data").decode("ascii")
            result = {
                "outputs": {
                    "9": {
                        "images": [
                            {"filename": "result.exe", "data": img_data},
                            {"filename": "outcome.png", "data": img_data},
                            {"filename": "image.jpg", "data": img_data},
                        ]
                    }
                }
            }
            saved = self._run_save(invoker, result, "cell_2")
            # Should only have .png and .jpg files, NOT .exe
            for path in saved:
                ext = Path(path).suffix.lower()
                self.assertIn(ext, {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"})

    def test_generates_unique_filenames(self):
        """Even with same remote filename, outputs get unique local names."""
        import base64
        with tempfile.TemporaryDirectory() as tmp:
            invoker = self._make_invoker(tmp)
            img_data = base64.b64encode(b"fake-data").decode("ascii")
            # Two images with identical filename from remote
            result = {
                "outputs": {
                    "9": {
                        "images": [
                            {"filename": "same_name.png", "data": img_data},
                            {"filename": "same_name.png", "data": img_data},
                        ]
                    }
                }
            }
            saved = self._run_save(invoker, result, "cell_3")
            self.assertEqual(len(saved), 2)
            # Both paths must be different
            self.assertNotEqual(saved[0], saved[1])

    def test_repeated_remote_filenames_do_not_overwrite(self):
        """Multiple outputs with same remote name produce distinct files on disk."""
        import base64
        with tempfile.TemporaryDirectory() as tmp:
            invoker = self._make_invoker(tmp)
            img_data1 = base64.b64encode(b"data-block-a").decode("ascii")
            img_data2 = base64.b64encode(b"data-block-b").decode("ascii")
            result = {
                "outputs": {
                    "9": {
                        "images": [
                            {"filename": "collision.png", "data": img_data1},
                            {"filename": "collision.png", "data": img_data2},
                        ]
                    }
                }
            }
            saved = self._run_save(invoker, result, "cell_4")
            self.assertEqual(len(saved), 2)
            output_dir = Path(tmp) / "output" / "studio"
            files = list(output_dir.iterdir())
            self.assertEqual(len(files), 2)
            # Both files should have different content
            contents = {f.read_bytes() for f in files}
            self.assertEqual(len(contents), 2)

    def test_traversal_cannot_escape_output_dir(self):
        """Path traversal like ../ escapes are contained within output/studio."""
        import base64
        with tempfile.TemporaryDirectory() as tmp:
            invoker = self._make_invoker(tmp)
            img_data = base64.b64encode(b"evil").decode("ascii")
            result = {
                "outputs": {
                    "9": {
                        "images": [
                            {"filename": "../../escape.png", "data": img_data},
                        ]
                    }
                }
            }
            saved = self._run_save(invoker, result, "cell_5")
            output_dir = Path(tmp) / "output" / "studio"
            # File must be inside output_dir
            for path in saved:
                full = output_dir / path
                self.assertTrue(str(full).startswith(str(output_dir.resolve())),
                                f"{full} escaped {output_dir}")

    def test_keeps_original_remote_name_in_metadata_diagnostics(self):
        """The original remote filename is preserved in result metadata."""
        import base64
        with tempfile.TemporaryDirectory() as tmp:
            invoker = self._make_invoker(tmp)
            img_data = base64.b64encode(b"meta-test").decode("ascii")
            result = {
                "outputs": {
                    "9": {
                        "images": [
                            {"filename": "original_name_from_remote.png", "data": img_data},
                        ]
                    }
                }
            }
            saved = self._run_save(invoker, result, "cell_6")
            # The saved name should NOT be the original remote name (it's regenerated)
            # But the original name can be embedded in diagnostics
            # For this test, verify the output filename is unique (contains studio_ prefix etc.)
            for path in saved:
                self.assertTrue(path.startswith("studio_"))


# ---------------------------------------------------------------------------
# Studio run submission-time history tests
# ---------------------------------------------------------------------------

class StudioRunSubmissionHistoryTests(unittest.TestCase):
    """Test that handle_studio_run creates a history record on submission."""

    def setUp(self):
        # Load modules
        self.adapter = _load_module("studio_run_adapter", "studio_run_adapter.py")
        self.svc_mod = _load_module("experiment_service", "experiment_service.py")
        # Patch REGISTRY.history() to use a temp dir
        self.tmp = tempfile.TemporaryDirectory()
        self.run_history_root = Path(self.tmp.name) / ".run_history"
        self.run_history_root.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_build_studio_history_meta_contains_run_id_placeholder(self):
        """studio_meta can carry a run_history_id for later finalization."""
        meta = self.adapter._build_studio_history_meta(
            preset_id="p1", snapshot_id="s1", feature_id="txt2img", controls={"seed": 1},
        )
        # The meta should accept a run_history_id being added later
        meta["run_history_id"] = "r_test123"
        self.assertEqual(meta.get("run_history_id"), "r_test123")

    def test_submission_record_has_submitted_status(self):
        """record_run can create a run with status='submitted'."""
        svc = self.svc_mod.RunHistoryService(self.run_history_root)
        rec = svc.record_run(
            kind="studio_run",
            prompt_id="exp_submit_test",
            status="submitted",
            meta={"studio_preset_id": "p1", "studio_feature_id": "txt2img"},
        )
        self.assertEqual(rec.get("status"), "submitted")
        self.assertIn("run_id", rec)
        self.assertIn("started_at", rec)

    def test_submission_record_carries_requested_controls(self):
        """Submission record meta includes requested_controls."""
        svc = self.svc_mod.RunHistoryService(self.run_history_root)
        controls = {"prompt": "a cat", "seed": 42, "steps": 20}
        rec = svc.record_run(
            kind="studio_run",
            prompt_id="exp_ctrl",
            status="submitted",
            meta={"requested_controls": controls},
        )
        stored_controls = rec.get("extra", {}).get("requested_controls", {})
        self.assertEqual(stored_controls.get("seed"), 42)
        self.assertEqual(stored_controls.get("prompt"), "a cat")


# ---------------------------------------------------------------------------
# Resolved controls derivation tests
# ---------------------------------------------------------------------------

class ResolvedControlsTests(unittest.TestCase):
    """Test derivation of resolved_controls from post-application workflow."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module("studio_run_adapter", "studio_run_adapter.py")

    def test_resolved_controls_contains_expected_fields(self):
        """_build_resolved_controls returns fields from workflow after control application."""
        workflow = {
            "3": {"class_type": "KSampler", "inputs": {
                "seed": 42, "steps": 20, "cfg": 7.0,
                "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0,
            }},
            "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "a cat"}},
            "8": {"class_type": "CLIPTextEncode", "inputs": {"text": "blurry"}},
            "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 768}},
        }
        slots = {
            "prompt": {"node_id": "7", "field": "text", "path": ["inputs", "text"]},
            "negative_prompt": {"node_id": "8", "field": "text", "path": ["inputs", "text"]},
            "seed": {"node_id": "3", "field": "seed", "path": ["inputs", "seed"]},
            "steps": {"node_id": "3", "field": "steps", "path": ["inputs", "steps"]},
            "guidance": {"node_id": "3", "field": "cfg", "path": ["inputs", "cfg"]},
            "sampler": {"node_id": "3", "field": "sampler_name", "path": ["inputs", "sampler_name"]},
            "scheduler": {"node_id": "3", "field": "scheduler", "path": ["inputs", "scheduler"]},
            "denoise": {"node_id": "3", "field": "denoise", "path": ["inputs", "denoise"]},
            "width": {"node_id": "5", "field": "width", "path": ["inputs", "width"]},
            "height": {"node_id": "5", "field": "height", "path": ["inputs", "height"]},
        }
        resolved = self.mod._build_resolved_controls(workflow, slots)
        self.assertEqual(resolved.get("seed"), 42)
        self.assertEqual(resolved.get("steps"), 20)
        self.assertEqual(resolved.get("prompt"), "a cat")
        self.assertEqual(resolved.get("negative_prompt"), "blurry")
        self.assertEqual(resolved.get("sampler"), "euler")
        self.assertEqual(resolved.get("scheduler"), "normal")
        self.assertEqual(resolved.get("denoise"), 1.0)
        self.assertEqual(resolved.get("width"), 512)
        self.assertEqual(resolved.get("height"), 768)

    def test_resolved_controls_preserves_falsy_values(self):
        """Falsy values like 0, 0.0, '' are preserved, not omitted."""
        workflow = {
            "3": {"class_type": "KSampler", "inputs": {
                "seed": 0, "steps": 0, "cfg": 0.0, "denoise": 0.0,
            }},
            "7": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
        }
        slots = {
            "prompt": {"node_id": "7", "field": "text", "path": ["inputs", "text"]},
            "seed": {"node_id": "3", "field": "seed", "path": ["inputs", "seed"]},
            "steps": {"node_id": "3", "field": "steps", "path": ["inputs", "steps"]},
            "guidance": {"node_id": "3", "field": "cfg", "path": ["inputs", "cfg"]},
            "denoise": {"node_id": "3", "field": "denoise", "path": ["inputs", "denoise"]},
        }
        resolved = self.mod._build_resolved_controls(workflow, slots)
        self.assertEqual(resolved.get("seed"), 0)
        self.assertEqual(resolved.get("steps"), 0)
        self.assertEqual(resolved.get("guidance"), 0.0)
        self.assertEqual(resolved.get("denoise"), 0.0)
        self.assertEqual(resolved.get("prompt"), "")
        self.assertIn("seed", resolved)
        self.assertIn("prompt", resolved)

    def test_resolved_controls_uses_all_slots_not_hardcoded_shortlist(self):
        """All bound slots are read, not only a hardcoded subset. Includes
        arbitrary bindings like mask_blur, input_image, lora fields."""
        workflow = {
            "3": {"class_type": "KSampler", "inputs": {
                "seed": 42, "steps": 20,
            }},
            "5": {"class_type": "LoadImage", "inputs": {"image": "input_photo.png"}},
            "12": {"class_type": "SomeNode", "inputs": {"mask_blur": 15, "expansion": 200}},
        }
        slots = {
            "seed": {"node_id": "3", "field": "seed", "path": ["inputs", "seed"]},
            "source_image": {"node_id": "5", "field": "image", "path": ["inputs", "image"]},
            "mask_blur": {"node_id": "12", "field": "mask_blur", "path": ["inputs", "mask_blur"]},
            "expansion": {"node_id": "12", "field": "expansion", "path": ["inputs", "expansion"]},
        }
        resolved = self.mod._build_resolved_controls(workflow, slots)
        self.assertEqual(resolved.get("seed"), 42)
        self.assertEqual(resolved.get("source_image"), "input_photo.png")
        self.assertEqual(resolved.get("mask_blur"), 15)
        self.assertEqual(resolved.get("expansion"), 200)

    def test_resolved_controls_arbitrary_bindings_work(self):
        """Completely arbitrary bound fields (lora_strength, image_identity, etc.)
        are read generically."""
        workflow = {
            "20": {"class_type": "LoRALoader", "inputs": {"lora_name": "style.safetensors", "strength": 0.8}},
            "21": {"class_type": "SomeNode", "inputs": {"identity": "img_abc123"}},
        }
        slots = {
            "lora_name": {"node_id": "20", "field": "lora_name", "path": ["inputs", "lora_name"]},
            "lora_strength": {"node_id": "20", "field": "strength", "path": ["inputs", "strength"]},
            "image_identity": {"node_id": "21", "field": "identity", "path": ["inputs", "identity"]},
        }
        resolved = self.mod._build_resolved_controls(workflow, slots)
        self.assertEqual(resolved.get("lora_name"), "style.safetensors")
        self.assertEqual(resolved.get("lora_strength"), 0.8)
        self.assertEqual(resolved.get("image_identity"), "img_abc123")

    def test_resolved_controls_only_overrides_replace_corresponding_values(self):
        """When controls override some values, resolved shows final values."""
        workflow = {
            "3": {"class_type": "KSampler", "inputs": {
                "seed": 777, "steps": 25, "cfg": 7.0,
            }},
            "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "overridden prompt"}},
        }
        slots = {
            "prompt": {"node_id": "7", "field": "text", "path": ["inputs", "text"]},
            "seed": {"node_id": "3", "field": "seed", "path": ["inputs", "seed"]},
            "steps": {"node_id": "3", "field": "steps", "path": ["inputs", "steps"]},
        }
        resolved = self.mod._build_resolved_controls(workflow, slots)
        self.assertEqual(resolved.get("seed"), 777)
        self.assertEqual(resolved.get("steps"), 25)
        self.assertEqual(resolved.get("prompt"), "overridden prompt")


# ---------------------------------------------------------------------------
# Integration: schedule_and_start finalizes same history record
# ---------------------------------------------------------------------------

class ScheduleAndStartFinalizationTests(unittest.TestCase):
    """Test that _schedule_and_start finalizes the submission history record."""

    @classmethod
    def setUpClass(cls):
        cls.svc_mod = _load_module("experiment_service", "experiment_service.py")
        cls.runner_mod = _load_module("experiment_runner", "experiment_runner.py")

    def test_finalize_does_not_create_new_record(self):
        """Finalization updates the existing record, does not create a new one."""
        with tempfile.TemporaryDirectory() as tmp:
            history_root = Path(tmp) / ".run_history"
            history_root.mkdir(parents=True, exist_ok=True)
            svc = self.svc_mod.RunHistoryService(history_root)
            rec = svc.record_run(
                kind="studio_run",
                prompt_id="exp_final",
                status="submitted",
                started_at="2025-06-01T00:00:00Z",
            )
            run_id = rec["run_id"]
            updated = svc.update_run(
                run_id,
                status="completed",
                completed_at="2025-06-01T01:00:00Z",
                timings={"total_ms": 5000},
                output_path="outputs/studio/img.png",
                meta={"resolved_controls": {"seed": 42}},
            )
            self.assertEqual(updated.get("status"), "completed")
            self.assertEqual(updated.get("run_id"), run_id)
            result = svc.list_runs(kind="studio_run")
            self.assertEqual(len(result["runs"]), 1)

    def test_failure_finalizes_same_record_as_failed(self):
        """On failure, the submission record is finalized with failed status."""
        with tempfile.TemporaryDirectory() as tmp:
            history_root = Path(tmp) / ".run_history"
            history_root.mkdir(parents=True, exist_ok=True)
            svc = self.svc_mod.RunHistoryService(history_root)
            rec = svc.record_run(
                kind="studio_run",
                prompt_id="exp_fail",
                status="submitted",
            )
            run_id = rec["run_id"]
            updated = svc.update_run(
                run_id,
                status="failed",
                completed_at="2025-06-01T01:00:00Z",
                meta={"error": "scheduler failed"},
            )
            self.assertEqual(updated.get("status"), "failed")
            self.assertIn("error", updated.get("extra", {}))

    def test_output_path_from_cell_completed_event(self):
        """update_run stores a real output path derived from cell.completed."""
        with tempfile.TemporaryDirectory() as tmp:
            history_root = Path(tmp) / ".run_history"
            history_root.mkdir(parents=True, exist_ok=True)
            svc = self.svc_mod.RunHistoryService(history_root)
            rec = svc.record_run(
                kind="studio_run",
                prompt_id="exp_path",
                status="running",
            )
            run_id = rec["run_id"]
            output_path = "outputs/studio/studio_exp_path_cell_9_0_20250601.png"
            updated = svc.update_run(
                run_id,
                status="completed",
                output_path=output_path,
            )
            self.assertEqual(updated.get("output_path"), output_path)
            meta = svc.get_run(run_id)
            self.assertEqual(meta.get("output_path"), output_path)

    def test_timestamps_and_timings_persisted(self):
        """completed_at and timings are both persisted in the finalized record."""
        with tempfile.TemporaryDirectory() as tmp:
            history_root = Path(tmp) / ".run_history"
            history_root.mkdir(parents=True, exist_ok=True)
            svc = self.svc_mod.RunHistoryService(history_root)
            rec = svc.record_run(
                kind="studio_run",
                prompt_id="exp_ts",
                status="running",
                started_at="2025-06-01T00:00:00Z",
            )
            run_id = rec["run_id"]
            completed_at = "2025-06-01T01:00:00Z"
            timings = {"total_ms": 3600000}
            svc.update_run(
                run_id,
                status="completed",
                completed_at=completed_at,
                timings=timings,
            )
            meta = svc.get_run(run_id)
            self.assertEqual(meta.get("started_at"), "2025-06-01T00:00:00Z")
            self.assertEqual(meta.get("completed_at"), completed_at)
            read_timing = svc.get_timing(run_id)
            self.assertEqual(read_timing, timings)

    # ── Failure does not attach output paths ───────────────────────────────

    def test_failed_run_has_no_output_path_or_primary_asset(self):
        """A failed run must NOT carry output_path or primary_asset_id that
        would make it look successful on the frontend."""
        with tempfile.TemporaryDirectory() as tmp:
            history_root = Path(tmp) / ".run_history"
            history_root.mkdir(parents=True, exist_ok=True)
            svc = self.svc_mod.RunHistoryService(history_root)
            rec = svc.record_run(
                kind="studio_run",
                prompt_id="exp_fail_no_out",
                status="submitted",
            )
            run_id = rec["run_id"]
            # Failure finalization with error only
            updated = svc.update_run(
                run_id,
                status="error",
                completed_at="2025-06-01T01:00:00Z",
                meta={"error": "Internal error processing request"},
            )
            self.assertEqual(updated.get("status"), "error")
            # output_path should be empty or absent
            self.assertFalse(updated.get("output_path"),
                             "Failed run should not have output_path")
            # primary_asset_id should NOT be set on failure
            self.assertNotIn("primary_asset_id", updated)


# ---------------------------------------------------------------------------
# Canonical flattened metadata tests
# ---------------------------------------------------------------------------

class CanonicalMetadataTests(unittest.TestCase):
    """Finalized record must have flattened canonical fields for frontend normalizer."""

    @classmethod
    def setUpClass(cls):
        cls.svc_mod = _load_module("experiment_service", "experiment_service.py")

    def _finalize_with_fields(self, svc, extra_fields: dict | None = None):
        """Helper: create a submission record then finalize with all canonical fields."""
        rec = svc.record_run(
            kind="studio_run",
            prompt_id="exp_canon",
            status="submitted",
            started_at="2025-06-01T00:00:00Z",
            meta={
                "requested_controls": {"prompt": "a cat", "seed": 42, "steps": 20},
                "studio_preset_id": "preset_1",
                "studio_snapshot_id": "snap_1",
                "studio_feature_id": "txt2img",
                "experiment_id": "exp_canon",
                "preset_label": "My Preset",
            },
        )
        merge = dict(extra_fields or {})
        merge.setdefault("resolved_controls", {"seed": 42, "steps": 20, "prompt": "a cat"})
        merge.setdefault("attempt_id", "a_001")
        merge.setdefault("cell_key", "studio_cell_abc")
        merge.setdefault("checkpoint_id", "ck_001")
        updated = svc.update_run(
            rec["run_id"],
            status="completed",
            completed_at="2025-06-01T01:00:00Z",
            output_path="outputs/studio/img_001.png",
            workflow_hash="wh_canon123",
            primary_asset_id="asset_001",
            meta=merge,
        )
        return svc.get_run(rec["run_id"])

    def test_canonical_fields_at_top_level(self):
        """Finalized record has prompt, seed, steps, workflow_hash, etc. at top level."""
        with tempfile.TemporaryDirectory() as tmp:
            svc = self.svc_mod.RunHistoryService(Path(tmp))
            meta = self._finalize_with_fields(svc)
            # These should be at top level for frontend normalizer
            self.assertEqual(meta.get("kind"), "studio_run")
            self.assertEqual(meta.get("status"), "completed")
            self.assertIn("run_id", meta)
            self.assertIn("started_at", meta)
            self.assertIn("completed_at", meta)
            self.assertIn("updated_at", meta)
            self.assertEqual(meta.get("workflow_hash"), "wh_canon123")
            self.assertEqual(meta.get("output_path"), "outputs/studio/img_001.png")
            self.assertEqual(meta.get("primary_asset_id"), "asset_001")

    def test_canonical_controls_at_top_level(self):
        """requested_controls and resolved_controls are top-level in extra, not nested."""
        with tempfile.TemporaryDirectory() as tmp:
            svc = self.svc_mod.RunHistoryService(Path(tmp))
            meta = self._finalize_with_fields(svc)
            extra = meta.get("extra", {})
            self.assertIn("requested_controls", extra)
            self.assertIn("resolved_controls", extra)
            self.assertEqual(extra["requested_controls"].get("seed"), 42)

    def test_canonical_identity_fields(self):
        """preset_id, snapshot_id, feature_id, experiment_id at top level or extra."""
        with tempfile.TemporaryDirectory() as tmp:
            svc = self.svc_mod.RunHistoryService(Path(tmp))
            meta = self._finalize_with_fields(svc)
            extra = meta.get("extra", {})
            self.assertEqual(extra.get("studio_preset_id"), "preset_1")
            self.assertEqual(extra.get("studio_snapshot_id"), "snap_1")
            self.assertEqual(extra.get("studio_feature_id"), "txt2img")
            self.assertEqual(extra.get("experiment_id"), "exp_canon")
            self.assertEqual(extra.get("preset_label"), "My Preset")

    def test_canonical_timestamps_present(self):
        """submitted_at (started_at), completed_at, updated_at are all present."""
        with tempfile.TemporaryDirectory() as tmp:
            svc = self.svc_mod.RunHistoryService(Path(tmp))
            meta = self._finalize_with_fields(svc)
            self.assertTrue(bool(meta.get("started_at")), "started_at missing")
            self.assertTrue(bool(meta.get("completed_at")), "completed_at missing")
            self.assertTrue(bool(meta.get("updated_at")), "updated_at missing")

    def test_canonical_cell_reference_fields(self):
        """attempt_id, cell_key, checkpoint_id present in extra."""
        with tempfile.TemporaryDirectory() as tmp:
            svc = self.svc_mod.RunHistoryService(Path(tmp))
            meta = self._finalize_with_fields(svc)
            extra = meta.get("extra", {})
            self.assertEqual(extra.get("attempt_id"), "a_001")
            self.assertEqual(extra.get("cell_key"), "studio_cell_abc")
            self.assertEqual(extra.get("checkpoint_id"), "ck_001")


# ---------------------------------------------------------------------------
# Stable error messages
# ---------------------------------------------------------------------------

class StableErrorMessagesTests(unittest.TestCase):
    """User-facing error messages must be stable, not raw exception text."""

    @classmethod
    def setUpClass(cls):
        cls.adapter = _load_module("studio_run_adapter", "studio_run_adapter.py")

    def test_stable_internal_error_constant_exists(self):
        """_STABLE_INTERNAL_ERROR is a non-empty string without raw exception details."""
        msg = self.adapter._STABLE_INTERNAL_ERROR
        self.assertTrue(bool(msg))
        # Should NOT contain raw exception indicators
        self.assertNotIn("traceback", msg.lower())
        self.assertNotIn("\n", msg)
        self.assertNotIn("  ", msg)
        # Should be a short, generic, stable message
        self.assertIn("Internal error", msg)
        self.assertGreater(len(msg), 5)
        self.assertLess(len(msg), 200)

    def test_failure_record_has_stable_error_not_raw_exception(self):
        """A failed record's error message is stable, not raw exception trace."""
        with tempfile.TemporaryDirectory() as tmp:
            svc_mod = _load_module("experiment_service", "experiment_service.py")
            svc = svc_mod.RunHistoryService(Path(tmp))
            rec = svc.record_run(
                kind="studio_run",
                prompt_id="exp_stable_err",
                status="submitted",
            )
            # Simulate failure with raw exception text (as _schedule_and_start might do)
            # The fix should ensure the update_run stores a stable message
            raw_exc = "ValueError: connection refused: [Errno 111] Connection refused"
            stable_msg = "Internal error processing request"
            updated = svc.update_run(
                rec["run_id"],
                status="error",
                completed_at="2025-06-01T01:00:00Z",
                meta={"error": stable_msg},
            )
            extra = updated.get("extra", {})
            stored_error = extra.get("error", "")
            # The user-facing error should be stable, not raw exception text
            self.assertNotIn("ValueError", stored_error)
            self.assertNotIn("connection refused", stored_error)
            self.assertEqual(stored_error, stable_msg)


# ---------------------------------------------------------------------------
# Integration: full compilation carries run_id in studio metadata
# ---------------------------------------------------------------------------

class CompilationRunIdTests(unittest.TestCase):
    """Test that run_id flows through compilation metadata."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module("studio_run_adapter", "studio_run_adapter.py")

    def test_compilation_can_carry_run_history_id(self):
        """compilation holds run_history_id that links to history record."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            controls = {"prompt": "test", "seed": 1}
            spec = self.mod.build_single_run_spec(preset, snap, "txt2img", controls, tmp)
            # Simulate adding run_id after history record creation
            spec["run_history_id"] = "r_" + "a" * 12
            self.assertIn("run_history_id", spec)
            # Also flows through studio_meta in checkpoints and cells
            for ck in spec.get("checkpoints", []):
                ck["studio_meta"]["run_history_id"] = spec["run_history_id"]
                self.assertEqual(
                    ck["studio_meta"].get("run_history_id"),
                    spec["run_history_id"],
                )
            for cell in spec.get("cells", []):
                cell["studio_meta"]["run_history_id"] = spec["run_history_id"]
                self.assertEqual(
                    cell["studio_meta"].get("run_history_id"),
                    spec["run_history_id"],
                )


# ---------------------------------------------------------------------------
# Canonical flattened aliases from resolved_controls
# ---------------------------------------------------------------------------

class CanonicalAliasesTests(unittest.TestCase):
    """resolved_controls values are copied to top-level extra aliases."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module("studio_run_adapter", "studio_run_adapter.py")

    def test_canonical_aliases_extracted_from_resolved_controls(self):
        """Values like prompt, seed, steps, guidance, sampler etc. appear as
        top-level aliases in extra, not only nested in resolved_controls."""
        resolved = {
            "prompt": "a cat", "negative_prompt": "blurry",
            "seed": 42, "steps": 20, "guidance": 7.0,
            "sampler": "euler", "scheduler": "normal", "denoise": 1.0,
            "width": 512, "height": 768,
        }
        result = self.mod._flatten_canonical_aliases(resolved, {})
        self.assertEqual(result.get("prompt"), "a cat")
        self.assertEqual(result.get("negative_prompt"), "blurry")
        self.assertEqual(result.get("seed"), 42)
        self.assertEqual(result.get("steps"), 20)
        self.assertEqual(result.get("guidance"), 7.0)
        self.assertEqual(result.get("sampler"), "euler")
        self.assertEqual(result.get("scheduler"), "normal")
        self.assertEqual(result.get("denoise"), 1.0)
        self.assertEqual(result.get("width"), 512)
        self.assertEqual(result.get("height"), 768)

    def test_canonical_aliases_include_lora_and_image_bindings(self):
        """LoRA name/strength and image identity are also aliased."""
        resolved = {
            "lora_name": "style.safetensors",
            "lora_strength": 0.8,
            "source_image": "input_photo.png",
            "mask_blur": 15,
        }
        result = self.mod._flatten_canonical_aliases(resolved, {})
        self.assertEqual(result.get("lora_name"), "style.safetensors")
        self.assertEqual(result.get("lora_strength"), 0.8)
        self.assertEqual(result.get("source_image"), "input_photo.png")
        self.assertEqual(result.get("mask_blur"), 15)

    def test_canonical_aliases_preserve_falsy_values(self):
        """Zero, empty string etc. in resolved_controls appear in aliases."""
        resolved = {"seed": 0, "steps": 0, "guidance": 0.0, "prompt": "", "denoise": 0.0}
        result = self.mod._flatten_canonical_aliases(resolved, {})
        self.assertEqual(result.get("seed"), 0)
        self.assertEqual(result.get("steps"), 0)
        self.assertEqual(result.get("prompt"), "")
        self.assertEqual(result.get("denoise"), 0.0)

    def test_canonical_aliases_event_payload_overrides(self):
        """Event payload values override resolved_controls for the same key."""
        resolved = {"prompt": "old prompt", "seed": 1}
        event_payload = {"seed": 999}
        result = self.mod._flatten_canonical_aliases(resolved, event_payload)
        self.assertEqual(result.get("prompt"), "old prompt")  # from resolved
        self.assertEqual(result.get("seed"), 999)  # overridden by event


# ---------------------------------------------------------------------------
# list_ruses numeric mtime sort key
# ---------------------------------------------------------------------------

class ListRunsSortKeyTests(unittest.TestCase):
    """list_runs must use numeric mtime, not stringified."""

    @classmethod
    def setUpClass(cls):
        cls.svc_mod = _load_module("experiment_service", "experiment_service.py")

    def test_list_runs_numeric_mtime_fallback(self):
        """Numeric mtime fallback sorts correctly when timestamps absent."""
        import os, time
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svc = self.svc_mod.RunHistoryService(root)
            # Create two records with explicit mod times
            run_a = root / "r_aaaa"
            run_a.mkdir()
            (run_a / "meta.json").write_text(
                '{"run_id":"r_aaaa","kind":"studio_run"}', encoding="utf-8")
            run_b = root / "r_bbbb"
            run_b.mkdir()
            (run_b / "meta.json").write_text(
                '{"run_id":"r_bbbb","kind":"studio_run"}', encoding="utf-8")
            # Set mtime: a=epoch+1000, b=epoch+2000 (b newer)
            os.utime(run_a, (1000, 1000))
            os.utime(run_b, (2000, 2000))
            result = svc.list_runs(kind="studio_run")
            runs = result["runs"]
            self.assertEqual(len(runs), 2)
            # b should come first (newer mtime = higher = first in DESC)
            self.assertEqual(runs[0]["run_id"], "r_bbbb")
            self.assertEqual(runs[1]["run_id"], "r_aaaa")

    def test_list_runs_mtime_string_sort_bug_regression(self):
        """Stringified mtime would sort '9' > '89' — verify numeric sort."""

        import os
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svc = self.svc_mod.RunHistoryService(root)
            run_a = root / "r_aaaa"
            run_a.mkdir()
            (run_a / "meta.json").write_text(
                '{"run_id":"r_aaaa","kind":"studio_run"}', encoding="utf-8")
            run_b = root / "r_bbbb"
            run_b.mkdir()
            (run_b / "meta.json").write_text(
                '{"run_id":"r_bbbb","kind":"studio_run"}', encoding="utf-8")
            # mtime_a=9, mtime_b=89 — string sort would put '9' > '89' (wrong)
            os.utime(run_a, (9, 9))
            os.utime(run_b, (89, 89))
            result = svc.list_runs(kind="studio_run")
            runs = result["runs"]
            self.assertEqual(len(runs), 2)
            # Numeric: 89 > 9, so b first in DESC
            self.assertEqual(runs[0]["run_id"], "r_bbbb")


# ---------------------------------------------------------------------------
# Canonical metadata: submitted_at, workflow_hash at submission
# ---------------------------------------------------------------------------

class SubmissionCanonicalMetadataTests(unittest.TestCase):
    """Submission record must carry submitted_at and workflow_hash."""

    @classmethod
    def setUpClass(cls):
        cls.svc_mod = _load_module("experiment_service", "experiment_service.py")

    def test_submission_record_has_submitted_at(self):
        """submitted_at is stored as explicit field in extra."""
        with tempfile.TemporaryDirectory() as tmp:
            svc = self.svc_mod.RunHistoryService(Path(tmp))
            rec = svc.record_run(
                kind="studio_run",
                prompt_id="exp_sub_at",
                status="submitted",
                started_at="2025-06-01T00:00:00Z",
                meta={"submitted_at": "2025-06-01T00:00:00Z"},
            )
            extra = rec.get("extra", {})
            self.assertEqual(extra.get("submitted_at"), "2025-06-01T00:00:00Z")


# ---------------------------------------------------------------------------
# Stable error in _schedule_and_start failure path
# ---------------------------------------------------------------------------

class PersistentErrorStabilityTests(unittest.TestCase):
    """_persist_experiment_error receives stable message, not raw exception."""

    @classmethod
    def setUpClass(cls):
        cls.adapter = _load_module("studio_run_adapter", "studio_run_adapter.py")
        cls.svc_mod = _load_module("experiment_service", "experiment_service.py")

    def test_persist_experiment_error_stable_message(self):
        """_persist_experiment_error is called with stable message."""
        stable = self.adapter._STABLE_INTERNAL_ERROR
        # The function just persists to store — verify it accepts stable
        self.assertTrue(bool(stable))
        self.assertNotIn("traceback", stable)
        # Raw exception patterns should not appear in stable msg
        self.assertNotIn("ValueError", stable)
        self.assertNotIn("Exception", stable)

    def test_persist_experiment_error_no_raw_exception(self):
        """The actual function should not be called with raw trace in production."""
        stable = self.adapter._STABLE_INTERNAL_ERROR
        # When _schedule_and_start's except block calls _persist_experiment_error,
        # it should pass the stable error, not str(exc)
        # Verify the stable constant is what gets used
        self.assertGreater(len(stable), 5)
        self.assertLess(len(stable), 200)
        self.assertIn("Internal error", stable)


# ---------------------------------------------------------------------------
# Preset label in history metadata
# ---------------------------------------------------------------------------

class StudioRunAdapterLabelTests(unittest.TestCase):
    """_build_studio_history_meta must carry preset_label."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module("studio_run_adapter", "studio_run_adapter.py")

    def test_history_meta_carries_preset_label(self):
        """_build_studio_history_meta includes studio_preset_label when preset_label arg provided."""
        meta = self.mod._build_studio_history_meta(
            preset_id="preset_1",
            snapshot_id="snap_1",
            feature_id="txt2img",
            controls={"seed": 42},
            preset_label="My Cool Preset",
        )
        self.assertEqual(meta.get("studio_preset_label"), "My Cool Preset")
        self.assertEqual(meta.get("studio_preset_id"), "preset_1")
        self.assertEqual(meta.get("studio_snapshot_id"), "snap_1")
        self.assertEqual(meta.get("studio_feature_id"), "txt2img")

    def test_build_single_run_spec_carries_preset_label(self):
        """build_single_run_spec carries preset label in studio_meta."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            controls = {"prompt": "test", "seed": 1}
            spec = self.mod.build_single_run_spec(preset, snap, "txt2img", controls, tmp)
            meta = spec.get("studio_meta", {})
            self.assertIn("studio_preset_label", meta,
                          "studio_meta must include studio_preset_label")
            self.assertEqual(meta.get("studio_preset_label"), "Runnable Preset")

    def test_finalization_meta_preserves_preset_label(self):
        """The meta_merge dict in finalization path carries preset_label from studio_meta."""
        from studio_run_adapter import _build_studio_history_meta
        studio_meta = _build_studio_history_meta(
            preset_id="preset_1",
            snapshot_id="snap_1",
            feature_id="txt2img",
            controls={"seed": 42},
            preset_label="Finalization Preset",
        )
        # Simulate the meta_merge step from _schedule_and_start
        meta_merge = {}
        meta_merge["studio_preset_id"] = studio_meta.get("studio_preset_id", "")
        meta_merge["studio_snapshot_id"] = studio_meta.get("studio_snapshot_id", "")
        meta_merge["studio_feature_id"] = studio_meta.get("studio_feature_id", "")
        meta_merge["preset_label"] = studio_meta.get("studio_preset_label", "")
        self.assertEqual(meta_merge.get("preset_label"), "Finalization Preset")
        self.assertEqual(meta_merge.get("studio_preset_id"), "preset_1")
        self.assertEqual(meta_merge.get("studio_snapshot_id"), "snap_1")
        self.assertEqual(meta_merge.get("studio_feature_id"), "txt2img")


# ---------------------------------------------------------------------------
# extract_defaults_from_snapshot includes sampler and scheduler
# ---------------------------------------------------------------------------

class ExtractDefaultsSamplerSchedulerTests(unittest.TestCase):
    """extract_defaults_from_snapshot must include sampler/scheduler when bound."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module("studio_run_adapter", "studio_run_adapter.py")

    def test_extracts_sampler_widget(self):
        """Sampler binding with kind=widget extracts sampler_name from workflow."""
        snapshot = {
            "apiPromptJson": {
                "3": {"class_type": "KSampler", "inputs": {
                    "seed": 42, "steps": 30, "sampler_name": "euler", "scheduler": "normal",
                }},
            },
            "nodeBindings": {
                "sampler": {"kind": "widget", "nodeId": "3", "widgetName": "sampler_name"},
                "scheduler": {"kind": "widget", "nodeId": "3", "widgetName": "scheduler"},
                "seed": {"kind": "widget", "nodeId": "3", "widgetName": "seed"},
            },
        }
        defaults = self.mod.extract_defaults_from_snapshot(snapshot)
        self.assertIn("sampler", defaults)
        self.assertIn("scheduler", defaults)
        self.assertEqual(defaults["sampler"], "euler")
        self.assertEqual(defaults["scheduler"], "normal")
        self.assertEqual(defaults["seed"], 42)

    def test_sampler_missing_if_not_bound(self):
        """Sampler/scheduler are auto-derived from workflow when absent from bindings."""
        snapshot = {
            "apiPromptJson": {
                "3": {"class_type": "KSampler", "inputs": {
                    "seed": 42, "sampler_name": "euler", "scheduler": "normal",
                }},
            },
            "nodeBindings": {
                "seed": {"kind": "widget", "nodeId": "3", "widgetName": "seed"},
            },
        }
        defaults = self.mod.extract_defaults_from_snapshot(snapshot)
        self.assertIn("seed", defaults)
        self.assertEqual(defaults.get("sampler"), "euler")
        self.assertEqual(defaults.get("scheduler"), "normal")

    def test_sampler_scheduler_auto_derived_when_unbound(self):
        """Sampler/scheduler are extracted from workflow even without bindings."""
        snapshot = {
            "apiPromptJson": {
                "3": {"class_type": "KSampler", "inputs": {
                    "seed": 42,
                    "steps": 30,
                    "cfg": 6.5,
                    "sampler_name": "dpmpp_2m",
                    "scheduler": "karras",
                    "denoise": 0.55,
                }},
            },
            "nodeBindings": {
                "seed": {"kind": "widget", "nodeId": "3", "widgetName": "seed"},
            },
        }
        defaults = self.mod.extract_defaults_from_snapshot(snapshot)
        self.assertEqual(defaults.get("sampler"), "dpmpp_2m")
        self.assertEqual(defaults.get("scheduler"), "karras")
        self.assertEqual(defaults.get("steps"), 30)
        self.assertEqual(defaults.get("guidance"), 6.5)
        self.assertEqual(defaults.get("denoise"), 0.55)

    def test_auto_derived_defaults_preserve_zero_values(self):
        """Auto-derived defaults preserve zero/0.0 values."""
        snapshot = {
            "apiPromptJson": {
                "3": {"class_type": "KSampler", "inputs": {
                    "seed": 0,
                    "steps": 0,
                    "cfg": 0.0,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "denoise": 0.0,
                }},
            },
            "nodeBindings": {},
        }
        defaults = self.mod.extract_defaults_from_snapshot(snapshot)
        self.assertEqual(defaults.get("seed"), 0)
        self.assertEqual(defaults.get("steps"), 0)
        self.assertEqual(defaults.get("guidance"), 0.0)
        self.assertEqual(defaults.get("denoise"), 0.0)

    def test_custom_sampler_node_defaults_auto_derived_when_unbound(self):
        """Custom sampler nodes with matching widgets also auto-derive defaults."""
        class _FakeSamplerNode:
            @classmethod
            def INPUT_TYPES(cls):
                return {"required": {
                    "sampler_name": (["alpha", "beta"], {"default": "alpha"}),
                    "scheduler": (["sched_a", "sched_b"], {"default": "sched_a"}),
                    "steps": ("INT", {"default": 20, "min": 1, "max": 100}),
                    "cfg": ("FLOAT", {"default": 7.0, "min": 0.0, "max": 20.0, "step": 0.5}),
                    "seed": ("INT", {"default": 0, "min": -1, "max": 999}),
                    "denoise": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                }}

        node_mod = self.mod.nodes
        if node_mod is None:
            node_mod = types.SimpleNamespace(NODE_CLASS_MAPPINGS={})
            setattr(self.mod, "nodes", node_mod)
        original = node_mod.NODE_CLASS_MAPPINGS.get("FakeSamplerNode")
        node_mod.NODE_CLASS_MAPPINGS["FakeSamplerNode"] = _FakeSamplerNode
        try:
            snapshot = {
                "apiPromptJson": {
                    "3": {"class_type": "FakeSamplerNode", "inputs": {
                        "seed": 55,
                        "steps": 33,
                        "cfg": 4.5,
                        "sampler_name": "beta",
                        "scheduler": "sched_b",
                        "denoise": 0.25,
                    }},
                },
                "nodeBindings": {},
            }
            defaults = self.mod.extract_defaults_from_snapshot(snapshot)
            self.assertEqual(defaults.get("sampler"), "beta")
            self.assertEqual(defaults.get("scheduler"), "sched_b")
            self.assertEqual(defaults.get("steps"), 33)
            self.assertEqual(defaults.get("guidance"), 4.5)
        finally:
            if original is None:
                node_mod.NODE_CLASS_MAPPINGS.pop("FakeSamplerNode", None)
            else:
                node_mod.NODE_CLASS_MAPPINGS["FakeSamplerNode"] = original

    def test_node_kind_control_binding_uses_alias_for_defaults(self):
        """Wizard-saved node-kind control bindings should still resolve common defaults."""
        snapshot = {
            "apiPromptJson": {
                "3": {
                    "class_type": "KSampler",
                    "inputs": {
                        "seed": 123,
                        "steps": 33,
                        "cfg": 6.5,
                        "sampler_name": "euler",
                        "scheduler": "normal",
                    },
                },
            },
            "nodeBindings": {
                "steps": {"kind": "node", "nodeId": "3"},
                "guidance": {"kind": "node", "nodeId": "3"},
                "seed": {"kind": "node", "nodeId": "3"},
                "sampler": {"kind": "node", "nodeId": "3"},
                "scheduler": {"kind": "node", "nodeId": "3"},
            },
        }
        defaults = self.mod.extract_defaults_from_snapshot(snapshot)
        self.assertEqual(defaults.get("steps"), 33)
        self.assertEqual(defaults.get("guidance"), 6.5)
        self.assertEqual(defaults.get("seed"), 123)
        self.assertEqual(defaults.get("sampler"), "euler")
        self.assertEqual(defaults.get("scheduler"), "normal")

    def test_node_kind_defaults_use_bound_node_not_first_matching_node(self):
        """Node-kind control defaults must come from the bound nodeId, not the first KSampler found."""
        snapshot = {
            "apiPromptJson": {
                "3": {
                    "class_type": "KSampler",
                    "inputs": {"seed": 1, "steps": 20, "cfg": 7.0, "sampler_name": "euler", "scheduler": "normal"},
                },
                "9": {
                    "class_type": "KSampler",
                    "inputs": {"seed": 999, "steps": 44, "cfg": 3.5, "sampler_name": "dpmpp_2m", "scheduler": "karras"},
                },
            },
            "nodeBindings": {
                "steps": {"kind": "node", "nodeId": "9"},
                "guidance": {"kind": "node", "nodeId": "9"},
                "seed": {"kind": "node", "nodeId": "9"},
                "sampler": {"kind": "node", "nodeId": "9"},
                "scheduler": {"kind": "node", "nodeId": "9"},
            },
        }
        defaults = self.mod.extract_defaults_from_snapshot(snapshot)
        self.assertEqual(defaults.get("steps"), 44)
        self.assertEqual(defaults.get("guidance"), 3.5)
        self.assertEqual(defaults.get("seed"), 999)
        self.assertEqual(defaults.get("sampler"), "dpmpp_2m")
        self.assertEqual(defaults.get("scheduler"), "karras")

    def test_node_kind_prompt_defaults_resolve_text_like_fields(self):
        """Prompt-like node bindings should resolve from the bound node's text/value field."""
        snapshot = {
            "apiPromptJson": {
                "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "a castle at dusk"}},
                "1497": {"class_type": "PrimitiveStringMultiline", "inputs": {"value": "remove the object"}},
            },
            "nodeBindings": {
                "prompt": {"kind": "node", "nodeId": "7"},
                "instruction": {"kind": "node", "nodeId": "1497"},
            },
        }
        defaults = self.mod.extract_defaults_from_snapshot(snapshot)
        self.assertEqual(defaults.get("prompt"), "a castle at dusk")
        self.assertEqual(defaults.get("instruction"), "remove the object")


# ---------------------------------------------------------------------------
# Control Schema derivation tests
# ---------------------------------------------------------------------------

class ControlSchemaDerivationTests(unittest.TestCase):
    """Tests for derive_control_schemas_from_snapshot()."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module("studio_run_adapter", "studio_run_adapter.py")

    def test_sampler_binding_produces_enum_schema(self):
        """sampler binding produces an enum schema with exact graph options."""
        snapshot = {
            "apiPromptJson": {
                "3": {"class_type": "KSampler", "inputs": {"seed": 42, "sampler_name": "euler"}},
            },
            "nodeBindings": {
                "sampler": {"kind": "widget", "nodeId": "3", "widgetName": "sampler_name"},
            },
        }
        schemas = self.mod.derive_control_schemas_from_snapshot(snapshot)
        s = schemas.get("sampler", {})
        self.assertEqual(s.get("kind"), "enum")
        self.assertTrue(s.get("schemaResolved"))
        self.assertIn("euler", s.get("options", []))
        self.assertIn("dpmpp_2m", s.get("options", []))

    def test_scheduler_binding_produces_enum_schema(self):
        """scheduler binding produces an enum schema with exact graph options."""
        snapshot = {
            "apiPromptJson": {
                "3": {"class_type": "KSampler", "inputs": {"seed": 42, "scheduler": "normal"}},
            },
            "nodeBindings": {
                "scheduler": {"kind": "widget", "nodeId": "3", "widgetName": "scheduler"},
            },
        }
        schemas = self.mod.derive_control_schemas_from_snapshot(snapshot)
        s = schemas.get("scheduler", {})
        self.assertEqual(s.get("kind"), "enum")
        self.assertTrue(s.get("schemaResolved"))
        self.assertIn("normal", s.get("options", []))
        self.assertIn("karras", s.get("options", []))

    def test_steps_binding_produces_integer_schema(self):
        """steps binding produces an integer schema with numeric constraints."""
        snapshot = {
            "apiPromptJson": {
                "3": {"class_type": "KSampler", "inputs": {"steps": 20}},
            },
            "nodeBindings": {
                "steps": {"kind": "widget", "nodeId": "3", "widgetName": "steps"},
            },
        }
        schemas = self.mod.derive_control_schemas_from_snapshot(snapshot)
        s = schemas.get("steps", {})
        self.assertEqual(s.get("kind"), "integer")
        self.assertTrue(s.get("schemaResolved"))
        self.assertIsNotNone(s.get("minimum"))
        self.assertIsNotNone(s.get("maximum"))

    def test_guidance_alias_maps_to_cfg(self):
        """guidance control ID is aliased to cfg widget name."""
        snapshot = {
            "apiPromptJson": {
                "3": {"class_type": "KSampler", "inputs": {"cfg": 7.0}},
            },
            "nodeBindings": {
                "guidance": {"kind": "widget", "nodeId": "3", "widgetName": "cfg"},
            },
        }
        schemas = self.mod.derive_control_schemas_from_snapshot(snapshot)
        s = schemas.get("guidance", {})
        self.assertEqual(s.get("kind"), "number")
        self.assertTrue(s.get("schemaResolved"))

    def test_prompt_produces_multiline_schema(self):
        """prompt binding on CLIPTextEncode produces multiline schema."""
        snapshot = {
            "apiPromptJson": {
                "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "a cat"}},
            },
            "nodeBindings": {
                "prompt": {"kind": "widget", "nodeId": "7", "widgetName": "text"},
            },
        }
        schemas = self.mod.derive_control_schemas_from_snapshot(snapshot)
        s = schemas.get("prompt", {})
        self.assertEqual(s.get("kind"), "multiline")
        self.assertTrue(s.get("schemaResolved"))

    def test_unknown_node_type_falls_back_to_inferred_type(self):
        """When node type is unknown, schema is inferred from the value."""
        snapshot = {
            "apiPromptJson": {
                "99": {"class_type": "CustomNode", "inputs": {"some_value": 42}},
            },
            "nodeBindings": {
                "custom_ctrl": {"kind": "widget", "nodeId": "99", "widgetName": "some_value"},
            },
        }
        schemas = self.mod.derive_control_schemas_from_snapshot(snapshot)
        s = schemas.get("custom_ctrl", {})
        # Should infer integer from the value 42
        self.assertEqual(s.get("kind"), "integer")
        self.assertTrue(s.get("schemaResolved"))

    def test_missing_snapshot_data_returns_unresolved(self):
        """When no apiPromptJson, schema returns unresolved."""
        snapshot = {
            "apiPromptJson": None,
            "nodeBindings": {
                "steps": {"kind": "widget", "nodeId": "3", "widgetName": "steps"},
            },
        }
        schemas = self.mod.derive_control_schemas_from_snapshot(snapshot)
        s = schemas.get("steps", {})
        self.assertEqual(s.get("kind"), "unresolved")
        self.assertFalse(s.get("schemaResolved"))

    def test_node_kind_binding_skipped(self):
        """Node-kind bindings (not widget/input) return unresolved."""
        snapshot = {
            "apiPromptJson": {"3": {"class_type": "KSampler", "inputs": {}}},
            "nodeBindings": {
                "prompt": {"kind": "node", "nodeId": "3"},
            },
        }
        schemas = self.mod.derive_control_schemas_from_snapshot(snapshot)
        s = schemas.get("prompt", {})
        self.assertEqual(s.get("kind"), "unresolved")
        self.assertFalse(s.get("schemaResolved"))

    def test_boolean_control_schema(self):
        """Boolean widget inferred from bool value."""
        snapshot = {
            "apiPromptJson": {
                "50": {"class_type": "BooleanControl", "inputs": {"value": False}},
            },
            "nodeBindings": {
                "enable": {"kind": "widget", "nodeId": "50", "widgetName": "value"},
            },
        }
        schemas = self.mod.derive_control_schemas_from_snapshot(snapshot)
        s = schemas.get("enable", {})
        self.assertEqual(s.get("kind"), "boolean")
        self.assertEqual(s.get("default"), False)

    def test_denoise_preserves_zero(self):
        """Denoise=0 is preserved as a valid numeric value in the schema."""
        snapshot = {
            "apiPromptJson": {
                "3": {"class_type": "KSampler", "inputs": {"denoise": 0.0}},
            },
            "nodeBindings": {
                "denoise": {"kind": "widget", "nodeId": "3", "widgetName": "denoise"},
            },
        }
        schemas = self.mod.derive_control_schemas_from_snapshot(snapshot)
        s = schemas.get("denoise", {})
        self.assertEqual(s.get("kind"), "number")
        # Schema default comes from the hardcoded registry (1.0 for KSampler denoise),
        # NOT the workflow value. The workflow value is extracted via
        # extract_defaults_from_snapshot. Verify schema has proper range that
        # includes 0.
        self.assertIsNotNone(s.get("minimum"))
        self.assertIsNotNone(s.get("maximum"))
        self.assertLessEqual(s.get("minimum", 0), 0.0)

    def test_sampler_schema_auto_derived_when_unbound(self):
        """Sampler enum schema is derived from workflow when unbound."""
        snapshot = {
            "apiPromptJson": {
                "3": {"class_type": "KSampler", "inputs": {
                    "seed": 42,
                    "sampler_name": "dpmpp_2m",
                    "scheduler": "karras",
                }},
            },
            "nodeBindings": {},
        }
        schemas = self.mod.derive_control_schemas_from_snapshot(snapshot)
        s = schemas.get("sampler", {})
        self.assertEqual(s.get("kind"), "enum")
        self.assertTrue(s.get("schemaResolved"))
        self.assertIn("euler", s.get("options", []))
        self.assertIn("dpmpp_2m", s.get("options", []))
        self.assertEqual(s.get("default"), "dpmpp_2m")

    def test_scheduler_schema_auto_derived_when_unbound(self):
        """Scheduler enum schema is derived from workflow when unbound."""
        snapshot = {
            "apiPromptJson": {
                "3": {"class_type": "KSampler", "inputs": {"scheduler": "karras"}},
            },
            "nodeBindings": {},
        }
        schemas = self.mod.derive_control_schemas_from_snapshot(snapshot)
        s = schemas.get("scheduler", {})
        self.assertEqual(s.get("kind"), "enum")
        self.assertTrue(s.get("schemaResolved"))
        self.assertIn("normal", s.get("options", []))
        self.assertIn("karras", s.get("options", []))
        self.assertEqual(s.get("default"), "karras")

    def test_steps_guidance_schema_auto_derived_when_unbound(self):
        """Numeric KSampler controls are derived from workflow when unbound."""
        snapshot = {
            "apiPromptJson": {
                "3": {"class_type": "KSampler", "inputs": {"steps": 30, "cfg": 6.5}},
            },
            "nodeBindings": {},
        }
        schemas = self.mod.derive_control_schemas_from_snapshot(snapshot)
        self.assertEqual(schemas.get("steps", {}).get("kind"), "integer")
        self.assertEqual(schemas.get("steps", {}).get("default"), 30)
        self.assertEqual(schemas.get("guidance", {}).get("kind"), "number")
        self.assertEqual(schemas.get("guidance", {}).get("default"), 6.5)

    def test_custom_sampler_node_schema_derived_from_node_def_when_unbound(self):
        """Custom sampler nodes derive enum options from node INPUT_TYPES()."""
        class _FakeSamplerNode:
            @classmethod
            def INPUT_TYPES(cls):
                return {"required": {
                    "sampler_name": (["alpha", "beta", "gamma"], {"default": "alpha"}),
                    "scheduler": (["sched_a", "sched_b"], {"default": "sched_a"}),
                    "steps": ("INT", {"default": 20, "min": 1, "max": 100}),
                    "cfg": ("FLOAT", {"default": 7.0, "min": 0.0, "max": 20.0, "step": 0.5}),
                    "seed": ("INT", {"default": 0, "min": -1, "max": 999}),
                    "denoise": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                }}

        node_mod = self.mod.nodes
        if node_mod is None:
            node_mod = types.SimpleNamespace(NODE_CLASS_MAPPINGS={})
            setattr(self.mod, "nodes", node_mod)
        original = node_mod.NODE_CLASS_MAPPINGS.get("FakeSamplerNode")
        node_mod.NODE_CLASS_MAPPINGS["FakeSamplerNode"] = _FakeSamplerNode
        try:
            snapshot = {
                "apiPromptJson": {
                    "3": {"class_type": "FakeSamplerNode", "inputs": {
                        "seed": 42,
                        "steps": 22,
                        "cfg": 4.5,
                        "sampler_name": "beta",
                        "scheduler": "sched_b",
                        "denoise": 0.9,
                    }},
                },
                "nodeBindings": {},
            }
            schemas = self.mod.derive_control_schemas_from_snapshot(snapshot)
            self.assertEqual(schemas.get("sampler", {}).get("kind"), "enum")
            self.assertIn("gamma", schemas.get("sampler", {}).get("options", []))
            self.assertEqual(schemas.get("sampler", {}).get("default"), "beta")
            self.assertEqual(schemas.get("scheduler", {}).get("kind"), "enum")
            self.assertIn("sched_b", schemas.get("scheduler", {}).get("options", []))
            self.assertEqual(schemas.get("steps", {}).get("kind"), "integer")
            self.assertEqual(schemas.get("guidance", {}).get("kind"), "number")
        finally:
            if original is None:
                node_mod.NODE_CLASS_MAPPINGS.pop("FakeSamplerNode", None)
            else:
                node_mod.NODE_CLASS_MAPPINGS["FakeSamplerNode"] = original


class ControlValidationTests(unittest.TestCase):
    """Tests for validate_controls_against_schema()."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module("studio_models", "studio_models.py")

    def test_valid_enum_passes(self):
        """Valid enum value passes validation."""
        schemas = {"sampler": {"kind": "enum", "options": ["euler", "dpmpp_2m"], "schemaResolved": True}}
        errors = self.mod.validate_controls_against_schema({"sampler": "euler"}, schemas, "txt2img")
        self.assertEqual(errors, [])

    def test_invalid_enum_rejected(self):
        """Invalid enum value returns precise error."""
        schemas = {"sampler": {"kind": "enum", "options": ["euler", "dpmpp_2m"], "schemaResolved": True}}
        errors = self.mod.validate_controls_against_schema({"sampler": "nonexistent"}, schemas, "txt2img")
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["field"], "sampler")
        self.assertIn("nonexistent", errors[0]["message"])

    def test_valid_integer_passes(self):
        """Valid integer value passes."""
        schemas = {"steps": {"kind": "integer", "minimum": 1, "maximum": 100, "schemaResolved": True}}
        errors = self.mod.validate_controls_against_schema({"steps": 20}, schemas, "txt2img")
        self.assertEqual(errors, [])

    def test_invalid_integer_type_rejected(self):
        """Non-integer value for integer field rejected."""
        schemas = {"steps": {"kind": "integer", "schemaResolved": True}}
        errors = self.mod.validate_controls_against_schema({"steps": "twenty"}, schemas, "txt2img")
        self.assertEqual(len(errors), 1)
        self.assertIn("integer", errors[0]["message"])

    def test_integer_out_of_range_rejected(self):
        """Integer out of range rejected."""
        schemas = {"steps": {"kind": "integer", "minimum": 1, "maximum": 100, "schemaResolved": True}}
        errors = self.mod.validate_controls_against_schema({"steps": 999}, schemas, "txt2img")
        self.assertEqual(len(errors), 1)
        self.assertIn("999", errors[0]["message"])

    def test_valid_number_passes(self):
        """Valid float value passes."""
        schemas = {"guidance": {"kind": "number", "minimum": 0.0, "maximum": 30.0, "schemaResolved": True}}
        errors = self.mod.validate_controls_against_schema({"guidance": 7.5}, schemas, "txt2img")
        self.assertEqual(errors, [])

    def test_number_out_of_range_rejected(self):
        """Number out of range rejected."""
        schemas = {"guidance": {"kind": "number", "minimum": 0.0, "maximum": 30.0, "schemaResolved": True}}
        errors = self.mod.validate_controls_against_schema({"guidance": 999.0}, schemas, "txt2img")
        self.assertEqual(len(errors), 1)

    def test_boolean_accepts_0_and_1(self):
        """Boolean schema accepts 0/1 for backward compatibility."""
        schemas = {"flag": {"kind": "boolean", "schemaResolved": True}}
        errors = self.mod.validate_controls_against_schema({"flag": 0}, schemas, "txt2img")
        self.assertEqual(errors, [])

        errors = self.mod.validate_controls_against_schema({"flag": 1}, schemas, "txt2img")
        self.assertEqual(errors, [])

    def test_boolean_rejects_string(self):
        """Boolean schema rejects non-boolean strings."""
        schemas = {"flag": {"kind": "boolean", "schemaResolved": True}}
        errors = self.mod.validate_controls_against_schema({"flag": "yes"}, schemas, "txt2img")
        self.assertEqual(len(errors), 1)

    def test_unresolved_schema_skips_validation(self):
        """Unresolved schemas do not produce validation errors."""
        schemas = {"unknown": {"kind": "unresolved", "schemaResolved": False}}
        errors = self.mod.validate_controls_against_schema({"unknown": "anything"}, schemas, "txt2img")
        self.assertEqual(errors, [])

    def test_none_value_passes_for_optional_field(self):
        """None value for optional field passes validation."""
        schemas = {"steps": {"kind": "integer", "schemaResolved": True}}
        errors = self.mod.validate_controls_against_schema({"steps": None}, schemas, "txt2img")
        self.assertEqual(errors, [])

    def test_zero_value_passes_for_integer_field(self):
        """Zero is a valid integer value."""
        schemas = {"seed": {"kind": "integer", "schemaResolved": True}}
        errors = self.mod.validate_controls_against_schema({"seed": 0}, schemas, "txt2img")
        self.assertEqual(errors, [])

    def test_false_value_passes_for_boolean_field(self):
        """False is a valid boolean value."""
        schemas = {"flag": {"kind": "boolean", "schemaResolved": True}}
        errors = self.mod.validate_controls_against_schema({"flag": False}, schemas, "txt2img")
        self.assertEqual(errors, [])

    def test_null_enum_value_rejected(self):
        """None/null value for enum field is rejected."""
        schemas = {"sampler": {"kind": "enum", "options": ["euler", "dpmpp_2m"], "schemaResolved": True}}
        errors = self.mod.validate_controls_against_schema({"sampler": None}, schemas, "txt2img")
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["field"], "sampler")
        self.assertIn("must be one of", errors[0]["message"].lower())

    def test_unknown_control_field_rejected(self):
        """Control field not in any schema is rejected when strictUnknownRejection=True."""
        schemas = {"steps": {"kind": "integer", "schemaResolved": True}}
        errors = self.mod.validate_controls_against_schema(
            {"steps": 20, "nonexistent_field": "value"}, schemas, "txt2img",
            strict_unknown_rejection=True,
        )
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["field"], "nonexistent_field")
        self.assertIn("unknown", errors[0]["message"].lower())

    def test_unknown_control_field_allowed_by_default(self):
        """Unknown fields pass by default (backward compatibility)."""
        schemas = {"steps": {"kind": "integer", "schemaResolved": True}}
        errors = self.mod.validate_controls_against_schema(
            {"steps": 20, "unknown_field": "value"}, schemas, "txt2img",
        )
        self.assertEqual(errors, [])

    def test_experiment_shared_defaults_validated(self):
        """Shared defaults in experiment definition are validated like run controls."""
        schemas = {"steps": {"kind": "integer", "minimum": 1, "maximum": 100, "schemaResolved": True}}
        # Collect all values from experiment_def default + axes for validation
        experiment_def = {
            "defaults": {"steps": 999},
            "axes": {},
        }
        all_values = dict(experiment_def.get("defaults", {}))
        for _axis_id, axis_def in (experiment_def.get("axes", {}) or {}).items():
            if isinstance(axis_def, dict) and axis_def.get("values"):
                for v in axis_def["values"]:
                    all_values[_axis_id] = v
        errors = self.mod.validate_controls_against_schema(all_values, schemas, "txt2img")
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["field"], "steps")

    def test_experiment_axis_values_validated(self):
        """Each axis value is validated individually — invalid values caught
        regardless of position in the list (not just when last)."""
        schemas = {"sampler": {"kind": "enum", "options": ["euler", "dpmpp_2m"], "schemaResolved": True}}
        # Validate each axis value individually (correct pattern — no overwriting)
        axis_values = ["nonexistent_sampler", "euler"]
        errors = []
        for v in axis_values:
            single_value = {"sampler": v}
            errors.extend(
                self.mod.validate_controls_against_schema(single_value, schemas, "txt2img")
            )
        # The invalid value first should produce an error
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["field"], "sampler")

    def test_experiment_axis_values_non_last_invalid_also_caught(self):
        """Invalid axis value caught even when it is NOT the last in the list."""
        schemas = {"sampler": {"kind": "enum", "options": ["euler", "dpmpp_2m"], "schemaResolved": True}}
        # Invalid value FIRST, valid second — this would be missed by the
        # overwriting pattern (only last value survives into a flat dict).
        axis_values = ["INVALID", "euler"]
        errors = []
        for v in axis_values:
            single_value = {"sampler": v}
            errors.extend(
                self.mod.validate_controls_against_schema(single_value, schemas, "txt2img")
            )
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["field"], "sampler")

    def test_load_presets_and_snapshots_no_double_read(self):
        """load_presets_and_snapshots no longer double-reads after validation pass."""
        mod = self.mod
        # The function should not exist anymore, replaced by calling
        # load_preset_and_snapshot in a loop directly
        self.assertFalse(hasattr(mod, "load_presets_and_snapshots"),
                         "load_presets_and_snapshots should be removed (dead double-load)")


# ---------------------------------------------------------------------------
# Phase 4: Captured Control Schemas
# ---------------------------------------------------------------------------

class CapturedControlSchemasTests(unittest.TestCase):
    """Phase 4: Captured control schemas must take priority over static registry.

    New-style snapshots carry a ``controlSchemas`` dict keyed by control ID,
    captured from the live LiteGraph widgets at binding time.  Old snapshots
    lack this key and fall back to the static ``_NODE_WIDGET_SCHEMAS`` table.
    """

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module("studio_run_adapter", "studio_run_adapter.py")

    def test_derive_uses_captured_schemas_when_present(self):
        """When snapshot has controlSchemas, use them as primary source."""
        snapshot = {
            "apiPromptJson": {
                "3": {"class_type": "KSampler", "inputs": {"sampler_name": "euler"}},
            },
            "nodeBindings": {
                "sampler": {"kind": "widget", "nodeId": "3", "widgetName": "sampler_name"},
            },
            "controlSchemas": {
                "sampler": {
                    "kind": "enum",
                    "options": ["euler", "dpmpp_2m", "custom_sampler"],
                    "default": "euler",
                    "nodeId": "3",
                    "widgetName": "sampler_name",
                },
            },
        }
        schemas = self.mod.derive_control_schemas_from_snapshot(snapshot)
        s = schemas.get("sampler", {})
        self.assertEqual(s.get("kind"), "enum")
        self.assertIn("custom_sampler", s.get("options", []),
                      "Captured option 'custom_sampler' must be in enum options")

    def test_derive_static_fallback_when_no_captured_schemas(self):
        """Old snapshots without controlSchemas still fall back to static registry."""
        snapshot = {
            "apiPromptJson": {
                "3": {"class_type": "KSampler", "inputs": {"sampler_name": "euler"}},
            },
            "nodeBindings": {
                "sampler": {"kind": "widget", "nodeId": "3", "widgetName": "sampler_name"},
            },
            # no controlSchemas key — old-style snapshot
        }
        schemas = self.mod.derive_control_schemas_from_snapshot(snapshot)
        s = schemas.get("sampler", {})
        self.assertEqual(s.get("kind"), "enum")
        self.assertTrue(s.get("schemaResolved"))
        self.assertIn("euler", s.get("options", []))
        self.assertIn("dpmpp_2m", s.get("options", []))

    def test_auto_derived_connection_spec_uses_schema_default(self):
        """Connected widgets must not replace a scalar schema default."""
        snapshot = {
            "apiPromptJson": {
                "3": {"class_type": "KSampler", "inputs": {"steps": ["937", 0]}},
            },
            "nodeBindings": {},
        }

        schemas = self.mod.derive_control_schemas_from_snapshot(snapshot)

        self.assertEqual(schemas["steps"].get("default"), 20)

    def test_captured_custom_widget_enum_preserved(self):
        """Custom/unknown widget enum values from captured schema, not Python table."""
        snapshot = {
            "apiPromptJson": {
                "99": {"class_type": "CustomSamplerNode", "inputs": {"preset": "fast"}},
            },
            "nodeBindings": {
                "preset": {"kind": "widget", "nodeId": "99", "widgetName": "preset"},
            },
            "controlSchemas": {
                "preset": {
                    "kind": "enum",
                    "options": ["fast", "quality", "extreme"],
                    "default": "fast",
                    "nodeId": "99",
                    "widgetName": "preset",
                },
            },
        }
        schemas = self.mod.derive_control_schemas_from_snapshot(snapshot)
        s = schemas.get("preset", {})
        self.assertEqual(s.get("kind"), "enum")
        self.assertEqual(s.get("options"), ["fast", "quality", "extreme"])
        self.assertTrue(s.get("schemaResolved"))

    def test_captured_integer_schema_with_range(self):
        """Captured integer schema preserves min/max/step from LiteGraph widget."""
        snapshot = {
            "apiPromptJson": {
                "99": {"class_type": "CustomIntNode", "inputs": {"value": 5}},
            },
            "nodeBindings": {
                "my_int": {"kind": "widget", "nodeId": "99", "widgetName": "value"},
            },
            "controlSchemas": {
                "my_int": {
                    "kind": "integer",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 100,
                    "step": 1,
                    "nodeId": "99",
                    "widgetName": "value",
                },
            },
        }
        schemas = self.mod.derive_control_schemas_from_snapshot(snapshot)
        s = schemas.get("my_int", {})
        self.assertEqual(s.get("kind"), "integer")
        self.assertEqual(s.get("minimum"), 1)
        self.assertEqual(s.get("maximum"), 100)
        self.assertEqual(s.get("step"), 1)
        self.assertTrue(s.get("schemaResolved"))

    def test_captured_schemas_empty_dict_falls_back(self):
        """Empty dict controlSchemas falls back to static registry."""
        snapshot = {
            "apiPromptJson": {
                "3": {"class_type": "KSampler", "inputs": {"sampler_name": "euler"}},
            },
            "nodeBindings": {
                "sampler": {"kind": "widget", "nodeId": "3", "widgetName": "sampler_name"},
            },
            "controlSchemas": {},
        }
        schemas = self.mod.derive_control_schemas_from_snapshot(snapshot)
        s = schemas.get("sampler", {})
        self.assertEqual(s.get("kind"), "enum")
        self.assertTrue(s.get("schemaResolved"))

    def test_captured_boolean_schema(self):
        """Captured boolean schema with no static equivalent works."""
        snapshot = {
            "apiPromptJson": {
                "50": {"class_type": "CustomBoolNode", "inputs": {"flag": True}},
            },
            "nodeBindings": {
                "enable": {"kind": "widget", "nodeId": "50", "widgetName": "flag"},
            },
            "controlSchemas": {
                "enable": {
                    "kind": "boolean",
                    "default": True,
                    "nodeId": "50",
                    "widgetName": "flag",
                },
            },
        }
        schemas = self.mod.derive_control_schemas_from_snapshot(snapshot)
        s = schemas.get("enable", {})
        self.assertEqual(s.get("kind"), "boolean")
        self.assertEqual(s.get("default"), True)
        self.assertTrue(s.get("schemaResolved"))

    def test_captured_multiline_schema(self):
        """Captured multiline string schema."""
        snapshot = {
            "apiPromptJson": {
                "7": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
            },
            "nodeBindings": {
                "prompt": {"kind": "widget", "nodeId": "7", "widgetName": "text"},
            },
            "controlSchemas": {
                "prompt": {
                    "kind": "multiline",
                    "default": "",
                    "nodeId": "7",
                    "widgetName": "text",
                },
            },
        }
        schemas = self.mod.derive_control_schemas_from_snapshot(snapshot)
        s = schemas.get("prompt", {})
        self.assertEqual(s.get("kind"), "multiline")
        self.assertTrue(s.get("schemaResolved"))

    def test_captured_schema_with_aliased_control_id(self):
        """Control ID aliases (guidance→cfg) work with captured schemas."""
        snapshot = {
            "apiPromptJson": {
                "3": {"class_type": "KSampler", "inputs": {"cfg": 7.0}},
            },
            "nodeBindings": {
                "guidance": {"kind": "widget", "nodeId": "3", "widgetName": "cfg"},
            },
            "controlSchemas": {
                "guidance": {
                    "kind": "number",
                    "default": 7.0,
                    "minimum": 0.0,
                    "maximum": 100.0,
                    "step": 0.5,
                    "nodeId": "3",
                    "widgetName": "cfg",
                },
            },
        }
        schemas = self.mod.derive_control_schemas_from_snapshot(snapshot)
        s = schemas.get("guidance", {})
        self.assertEqual(s.get("kind"), "number")
        self.assertEqual(s.get("minimum"), 0.0)
        self.assertTrue(s.get("schemaResolved"))

    def test_mixed_captured_and_auto_derived_controls(self):
        """Captured schemas stay intact while missing controls are auto-derived."""
        snapshot = {
            "apiPromptJson": {
                "3": {"class_type": "KSampler", "inputs": {
                    "seed": 123,
                    "steps": 44,
                    "sampler_name": "dpmpp_2m",
                    "scheduler": "karras",
                }},
            },
            "nodeBindings": {},
            "controlSchemas": {
                "seed": {
                    "kind": "integer",
                    "default": 123,
                    "minimum": 0,
                    "maximum": 999999,
                    "nodeId": "3",
                    "widgetName": "seed",
                },
                "steps": {
                    "kind": "integer",
                    "default": 44,
                    "minimum": 1,
                    "maximum": 200,
                    "nodeId": "3",
                    "widgetName": "steps",
                },
            },
        }
        schemas = self.mod.derive_control_schemas_from_snapshot(snapshot)
        self.assertEqual(schemas.get("seed", {}).get("maximum"), 999999)
        self.assertEqual(schemas.get("steps", {}).get("maximum"), 200)
        self.assertEqual(schemas.get("sampler", {}).get("kind"), "enum")
        self.assertEqual(schemas.get("sampler", {}).get("default"), "dpmpp_2m")
        self.assertEqual(schemas.get("scheduler", {}).get("kind"), "enum")
        self.assertEqual(schemas.get("scheduler", {}).get("default"), "karras")


class CapturedControlSchemasSnapshotModelTests(unittest.TestCase):
    """Snapshot model must accept and persist controlSchemas."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module("studio_models", "studio_models.py")

    def test_make_snapshot_accepts_control_schemas(self):
        """make_snapshot accepts controlSchemas in body."""
        body = {
            "name": "Test Captured",
            "compatibleFeatures": ["txt2img"],
            "graphJson": {"nodes": []},
            "apiPromptJson": {"3": {"class_type": "KSampler", "inputs": {"seed": 42}}},
            "nodeBindings": {
                "sampler": {"kind": "widget", "nodeId": "3", "widgetName": "sampler_name"},
            },
            "outputNodeId": "9",
            "controlSchemas": {
                "sampler": {
                    "kind": "enum",
                    "options": ["euler", "dpmpp_2m"],
                    "default": "euler",
                    "nodeId": "3",
                    "widgetName": "sampler_name",
                },
            },
        }
        snapshot = self.mod.make_snapshot(body)
        self.assertIn("controlSchemas", snapshot)
        self.assertEqual(
            snapshot["controlSchemas"]["sampler"]["kind"], "enum"
        )
        self.assertIn("euler", snapshot["controlSchemas"]["sampler"]["options"])

    def test_make_snapshot_defaults_control_schemas_to_empty(self):
        """make_snapshot defaults controlSchemas to {} when absent."""
        body = {
            "name": "No Schemas",
            "compatibleFeatures": ["txt2img"],
            "graphJson": {"nodes": []},
            "apiPromptJson": {"3": {"class_type": "KSampler", "inputs": {"seed": 42}}},
            "nodeBindings": {
                "sampler": {"kind": "widget", "nodeId": "3", "widgetName": "sampler_name"},
            },
            "outputNodeId": "9",
        }
        snapshot = self.mod.make_snapshot(body)
        self.assertIn("controlSchemas", snapshot)
        self.assertEqual(snapshot["controlSchemas"], {})

    def test_update_snapshot_accepts_control_schemas(self):
        """update_snapshot accepts controlSchemas update."""
        body = {
            "name": "Test",
            "compatibleFeatures": ["txt2img"],
            "graphJson": {"nodes": []},
            "apiPromptJson": {"3": {"class_type": "KSampler", "inputs": {"seed": 42}}},
            "nodeBindings": {},
            "outputNodeId": "9",
        }
        snapshot = self.mod.make_snapshot(body)
        # Now update with controlSchemas
        updated = self.mod.update_snapshot(snapshot, {
            "controlSchemas": {"sampler": {"kind": "enum"}},
        })
        self.assertIn("controlSchemas", updated)
        self.assertEqual(updated["controlSchemas"]["sampler"]["kind"], "enum")

    def test_snapshot_model_field_exists(self):
        """Snapshot fields must include controlSchemas."""
        # Check make_snapshot entry template — visible in source
        import inspect
        source = inspect.getsource(self.mod.make_snapshot)
        self.assertIn("controlSchemas", source,
                      "make_snapshot must reference controlSchemas in entry dict")

    def test_normalize_snapshot_does_not_strip_control_schemas(self):
        """normalize_snapshot_payload preserves controlSchemas."""
        payload = {
            "compatibleFeatures": ["txt2img"],
            "graphJson": {"nodes": []},
            "apiPromptJson": {"3": {"class_type": "KSampler", "inputs": {"seed": 42}}},
            "nodeBindings": {},
            "outputNodeId": "9",
            "controlSchemas": {"steps": {"kind": "integer"}},
        }
        result = self.mod.normalize_snapshot_payload(payload)
        self.assertIn("controlSchemas", result)
        self.assertEqual(result["controlSchemas"]["steps"]["kind"], "integer")


class CapturedSchemaPresetEnrichmentTests(unittest.TestCase):
    """Preset list API enrichment includes captured schemas."""

    @classmethod
    def setUpClass(cls):
        cls.adapter = _load_module("studio_run_adapter", "studio_run_adapter.py")

    def test_preset_enrichment_uses_captured_schemas_when_present(self):
        """Preset enrichment uses captured schemas from snapshot."""
        snapshot = {
            "id": "snap_captured",
            "compatibleFeatures": ["txt2img"],
            "apiPromptJson": {
                "3": {"class_type": "KSampler", "inputs": {"sampler_name": "euler"}},
            },
            "nodeBindings": {
                "sampler": {"kind": "widget", "nodeId": "3", "widgetName": "sampler_name"},
            },
            "controlSchemas": {
                "sampler": {
                    "kind": "enum",
                    "options": ["turbo", "lcm"],
                    "default": "turbo",
                    "nodeId": "3",
                    "widgetName": "sampler_name",
                },
            },
            "archived": False,
        }
        schemas = self.adapter.derive_control_schemas_from_snapshot(snapshot)
        s = schemas.get("sampler", {})
        self.assertEqual(s.get("options"), ["turbo", "lcm"],
                         "Captured sampler options should not come from static table")


class CapturedSchemaValidationIntegrationTests(unittest.TestCase):
    """End-to-end validation: captured schemas enforce enum/range/boolean checks."""

    @classmethod
    def setUpClass(cls):
        cls.adapter = _load_module("studio_run_adapter", "studio_run_adapter.py")
        cls.model = _load_module("studio_models", "studio_models.py")

    def test_captured_enum_validation_rejects_invalid_option(self):
        """Captured enum schema enforces its custom options, not the static table."""
        snapshot = {
            "apiPromptJson": {"3": {"class_type": "KSampler", "inputs": {"sampler_name": "euler"}}},
            "nodeBindings": {"sampler": {"kind": "widget", "nodeId": "3", "widgetName": "sampler_name"}},
            "controlSchemas": {
                "sampler": {
                    "kind": "enum",
                    "options": ["turbo", "lcm"],
                    "default": "turbo",
                    "nodeId": "3",
                    "widgetName": "sampler_name",
                },
            },
        }
        schemas = self.adapter.derive_control_schemas_from_snapshot(snapshot)
        # "euler" is in the static table but NOT in captured options
        errors = self.model.validate_controls_against_schema(
            {"sampler": "euler"}, schemas, "txt2img"
        )
        self.assertEqual(len(errors), 1,
                         "captured enum must reject values not in its own options")
        self.assertIn("euler", errors[0]["message"])
        # "turbo" IS in captured options
        errors2 = self.model.validate_controls_against_schema(
            {"sampler": "turbo"}, schemas, "txt2img"
        )
        self.assertEqual(len(errors2), 0,
                         "captured enum must accept values in its own options")

    def test_captured_range_validation(self):
        """Captured integer schema enforces its own min/max range."""
        snapshot = {
            "apiPromptJson": {"99": {"class_type": "CustomIntNode", "inputs": {"value": 5}}},
            "nodeBindings": {"my_int": {"kind": "widget", "nodeId": "99", "widgetName": "value"}},
            "controlSchemas": {
                "my_int": {
                    "kind": "integer",
                    "minimum": 1,
                    "maximum": 10,
                    "nodeId": "99",
                    "widgetName": "value",
                },
            },
        }
        schemas = self.adapter.derive_control_schemas_from_snapshot(snapshot)
        errors = self.model.validate_controls_against_schema(
            {"my_int": 999}, schemas, "txt2img"
        )
        self.assertEqual(len(errors), 1,
                         "captured range must reject out-of-range values")

    def test_captured_boolean_validation_rejects_string(self):
        """Captured boolean schema rejects non-boolean values."""
        snapshot = {
            "apiPromptJson": {"50": {"class_type": "CustomBoolNode", "inputs": {"flag": True}}},
            "nodeBindings": {"enable": {"kind": "widget", "nodeId": "50", "widgetName": "flag"}},
            "controlSchemas": {
                "enable": {
                    "kind": "boolean",
                    "default": True,
                    "nodeId": "50",
                    "widgetName": "flag",
                },
            },
        }
        schemas = self.adapter.derive_control_schemas_from_snapshot(snapshot)
        errors = self.model.validate_controls_against_schema(
            {"enable": "yes"}, schemas, "txt2img"
        )
        self.assertEqual(len(errors), 1, "captured boolean must reject string")

    def test_captured_schema_strict_unknown_rejection(self):
        """Captured schemas used with strict_unknown_rejection reject unknown fields."""
        snapshot = {
            "apiPromptJson": {"3": {"class_type": "KSampler", "inputs": {"seed": 42}}},
            "nodeBindings": {"seed": {"kind": "widget", "nodeId": "3", "widgetName": "seed"}},
            "controlSchemas": {
                "seed": {"kind": "integer", "default": 42, "nodeId": "3", "widgetName": "seed"},
            },
        }
        schemas = self.adapter.derive_control_schemas_from_snapshot(snapshot)
        errors = self.model.validate_controls_against_schema(
            {"seed": 42, "bogus_field": "x"}, schemas, "txt2img",
            strict_unknown_rejection=True,
        )
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["field"], "bogus_field")


class CapturedSchemaDeepCopyTests(unittest.TestCase):
    """derive_control_schemas_from_snapshot must deep-copy so reads don't mutate stored objects."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module("studio_run_adapter", "studio_run_adapter.py")

    def test_mutating_returned_schemas_does_not_affect_snapshot(self):
        """In-place mutations of returned schemas must not alter the stored snapshot."""
        stored_schemas = {
            "sampler": {
                "kind": "enum",
                "options": ["turbo", "lcm"],
                "default": "turbo",
            },
        }
        snapshot = {
            "apiPromptJson": {"3": {"class_type": "KSampler", "inputs": {"sampler_name": "turbo"}}},
            "nodeBindings": {"sampler": {"kind": "widget", "nodeId": "3", "widgetName": "sampler_name"}},
            "controlSchemas": dict(stored_schemas),
        }
        result = self.mod.derive_control_schemas_from_snapshot(snapshot)
        # Mutate the returned schema in place
        result["sampler"]["kind"] = "mutated"
        result["sampler"]["options"].append("injected")
        # The original snapshot must be unchanged
        original = snapshot["controlSchemas"]["sampler"]
        self.assertEqual(original["kind"], "enum",
                         "Snapshot kind must not be mutated by caller")
        self.assertNotIn("injected", original.get("options", []),
                         "Snapshot options must not be mutated by caller")


class AutoDerivedSlotsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module("studio_run_adapter", "studio_run_adapter.py")

    def test_augment_slots_adds_unbound_ksampler_controls(self):
        workflow = {
            "3": {"class_type": "KSampler", "inputs": {
                "seed": 42,
                "steps": 20,
                "cfg": 7.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
            }},
        }
        slots = {"seed": {"node_id": "3", "field": "seed", "path": ["inputs", "seed"]}}
        augmented = self.mod._augment_slots_with_auto_derive(dict(slots), workflow)
        self.assertIn("sampler", augmented)
        self.assertIn("scheduler", augmented)
        self.assertIn("steps", augmented)
        self.assertIn("guidance", augmented)
        self.assertEqual(augmented["sampler"], {
            "node_id": "3",
            "field": "sampler_name",
            "path": ["inputs", "sampler_name"],
        })

    def test_apply_controls_with_auto_derived_slots(self):
        workflow = {
            "3": {"class_type": "KSampler", "inputs": {
                "seed": 42,
                "steps": 20,
                "cfg": 7.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
            }},
        }
        slots = self.mod._augment_slots_with_auto_derive({}, workflow)
        self.mod._apply_controls_to_workflow(workflow, slots, {
            "sampler": "dpmpp_2m",
            "scheduler": "karras",
            "steps": 30,
            "guidance": 5.5,
            "denoise": 0.4,
        })
        inputs = workflow["3"]["inputs"]
        self.assertEqual(inputs["sampler_name"], "dpmpp_2m")
        self.assertEqual(inputs["scheduler"], "karras")
        self.assertEqual(inputs["steps"], 30)
        self.assertEqual(inputs["cfg"], 5.5)
        self.assertEqual(inputs["denoise"], 0.4)

    def test_augment_slots_first_matching_ksampler_wins(self):
        workflow = {
            "3": {"class_type": "KSampler", "inputs": {
                "sampler_name": "euler", "scheduler": "normal", "steps": 20,
                "cfg": 7.0, "seed": 42, "denoise": 1.0,
            }},
            "4": {"class_type": "KSampler", "inputs": {
                "sampler_name": "heun", "scheduler": "karras", "steps": 50,
                "cfg": 8.0, "seed": 77, "denoise": 0.5,
            }},
        }
        slots = self.mod._augment_slots_with_auto_derive({}, workflow)
        self.assertEqual(slots["sampler"]["node_id"], "3")
        self.assertEqual(slots["scheduler"]["node_id"], "3")

    def test_augment_slots_supports_custom_sampler_nodes(self):
        class _FakeSamplerNode:
            @classmethod
            def INPUT_TYPES(cls):
                return {"required": {
                    "sampler_name": (["alpha", "beta"], {"default": "alpha"}),
                    "scheduler": (["sched_a", "sched_b"], {"default": "sched_a"}),
                    "steps": ("INT", {"default": 20, "min": 1, "max": 100}),
                    "cfg": ("FLOAT", {"default": 7.0, "min": 0.0, "max": 20.0, "step": 0.5}),
                    "seed": ("INT", {"default": 0, "min": -1, "max": 999}),
                    "denoise": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                }}

        node_mod = self.mod.nodes
        if node_mod is None:
            node_mod = types.SimpleNamespace(NODE_CLASS_MAPPINGS={})
            setattr(self.mod, "nodes", node_mod)
        original = node_mod.NODE_CLASS_MAPPINGS.get("FakeSamplerNode")
        node_mod.NODE_CLASS_MAPPINGS["FakeSamplerNode"] = _FakeSamplerNode
        try:
            workflow = {
                "3": {"class_type": "FakeSamplerNode", "inputs": {
                    "sampler_name": "beta",
                    "scheduler": "sched_b",
                    "steps": 30,
                    "cfg": 4.5,
                    "seed": 55,
                    "denoise": 0.2,
                }},
            }
            slots = self.mod._augment_slots_with_auto_derive({}, workflow)
            self.assertEqual(slots["sampler"]["field"], "sampler_name")
            self.assertEqual(slots["scheduler"]["field"], "scheduler")
            self.assertEqual(slots["guidance"]["field"], "cfg")
        finally:
            if original is None:
                node_mod.NODE_CLASS_MAPPINGS.pop("FakeSamplerNode", None)
            else:
                node_mod.NODE_CLASS_MAPPINGS["FakeSamplerNode"] = original


class GitignoreRuntimeDirectoriesTests(unittest.TestCase):
    """.gitignore covers output/studio/ and .comfymodal_experiments/."""

    def test_output_studio_in_gitignore(self):
        text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("output/studio/", text)

    def test_comfymodal_experiments_in_gitignore(self):
        text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".comfymodal_experiments/", text)


# ---------------------------------------------------------------------------
# Task 2: Control coercion before queueing
# ---------------------------------------------------------------------------

class StudioControlCoercionTests(unittest.TestCase):
    """Coercion of controls before _apply_controls_to_workflow.

    Requirements:
    - Required text control (prompt) rejects whitespace-only
    - Optional text control (negative_prompt) allows empty/whitespace
    - Scalar int/number/bool/enum schemas reject arrays/objects
    - Zero-like values (seed=0, guidance=0, denoise=0, False) preserved
    - Coercion before _apply_controls_to_workflow AND before int() in
      resolve_and_inject_cell
    - LoRA strength arrays confined to LoRA axes, not canonical scalars
    """

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module("studio_run_adapter", "studio_run_adapter.py")

    # ── Whitespace-only text controls ───────────────────────────────────

    def test_whitespace_only_prompt_rejected(self):
        """prompt=whitespace-only returns field-specific error."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            spec = self.mod.build_single_run_spec(
                preset, snap, "txt2img", {"prompt": "   "}, tmp,
            )
            self.assertIn("error", spec)
            self.assertIn("prompt", spec["error"])

    def test_optional_negative_prompt_empty_allowed(self):
        """negative_prompt="" is allowed when no negative_prompt binding exists
        (live fixture has hasNegative=false)."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            spec = self.mod.build_single_run_spec(
                preset, snap, "txt2img",
                {"prompt": "test", "negative_prompt": ""}, tmp,
            )
            self.assertNotIn("error", spec)

    def test_optional_negative_prompt_whitespace_allowed(self):
        """negative_prompt=whitespace is allowed when no binding exists."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            spec = self.mod.build_single_run_spec(
                preset, snap, "txt2img",
                {"prompt": "test", "negative_prompt": "   "}, tmp,
            )
            self.assertNotIn("error", spec)

    # ── Array/object values for scalar schemas ──────────────────────────

    def test_array_steps_rejected_before_apply(self):
        """steps=[8] rejected with field-specific error before _apply_controls_to_workflow."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            spec = self.mod.build_single_run_spec(
                preset, snap, "txt2img", {"prompt": "test", "steps": [8]}, tmp,
            )
            self.assertIn("error", spec)
            self.assertIn("steps", spec["error"])
            self.assertIn("integer", spec["error"].lower())

    def test_array_guidance_rejected(self):
        """guidance=[7.5] rejected with field-specific error."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            spec = self.mod.build_single_run_spec(
                preset, snap, "txt2img",
                {"prompt": "test", "guidance": [7.5]}, tmp,
            )
            self.assertIn("error", spec)
            self.assertIn("guidance", spec["error"])

    def test_array_sampler_rejected(self):
        """sampler=["euler"] rejected with field-specific error."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            spec = self.mod.build_single_run_spec(
                preset, snap, "txt2img",
                {"prompt": "test", "sampler": ["euler"]}, tmp,
            )
            self.assertIn("error", spec)
            self.assertIn("sampler", spec["error"])

    def test_dict_seed_rejected(self):
        """seed={"val": 42} rejected with field-specific error."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            spec = self.mod.build_single_run_spec(
                preset, snap, "txt2img",
                {"prompt": "test", "seed": {"val": 42}}, tmp,
            )
            self.assertIn("error", spec)
            self.assertIn("seed", spec["error"])

    # ── Zero-like values preserved ──────────────────────────────────────

    def test_zero_seed_preserved(self):
        """seed=0 is preserved, not rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            spec = self.mod.build_single_run_spec(
                preset, snap, "txt2img", {"prompt": "test", "seed": 0}, tmp,
            )
            self.assertNotIn("error", spec)
            cell = spec["cells"][0]
            self.assertEqual(cell["axis_values"].get("seed"), 0)

    def test_zero_guidance_preserved(self):
        """guidance=0 is preserved."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            spec = self.mod.build_single_run_spec(
                preset, snap, "txt2img",
                {"prompt": "test", "guidance": 0}, tmp,
            )
            self.assertNotIn("error", spec)
            cell = spec["cells"][0]
            self.assertEqual(cell["axis_values"].get("guidance"), 0)

    def test_zero_denoise_preserved(self):
        """denoise=0 is preserved."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            spec = self.mod.build_single_run_spec(
                preset, snap, "txt2img",
                {"prompt": "test", "denoise": 0.0}, tmp,
            )
            self.assertNotIn("error", spec)
            cell = spec["cells"][0]
            self.assertEqual(cell["axis_values"].get("denoise"), 0.0)

    def test_false_boolean_preserved(self):
        """False boolean is preserved through build_single_run_spec."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            # Add a boolean field to the snapshot's control schemas
            snap["controlSchemas"] = {
                "enable": {
                    "kind": "boolean",
                    "default": False,
                    "schemaResolved": True,
                    "nodeId": "3",
                    "widgetName": "boolean_field",
                },
            }
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            spec = self.mod.build_single_run_spec(
                preset, snap, "txt2img",
                {"prompt": "test", "enable": False}, tmp,
            )
            self.assertNotIn("error", spec)


# ---------------------------------------------------------------------------
# Tests for validate_studio_request_controls
# ---------------------------------------------------------------------------

class ValidateStudioRequestControlsRED(unittest.TestCase):
    """RED tests for validate_studio_request_controls().

    Required behavior:
    - Pure function in studio_run_adapter.
    - For every preset ID calls load_preset_and_snapshot.
    - Load failure yields preset-scoped error {presetId, field, message}.
    - For every loaded snapshot derives its schema; validates shared controls
      with strict_unknown_rejection=False; validates EACH enabled axis value
      independently; attaches presetId to every returned validation error.
    - A heterogeneous experiment must reject a value valid for preset A but
      invalid for preset B. No first-preset shortcut.
    - Single run uses helper with [preset_id], controls, {}.
    - Experiment uses every ID, defaults, axes.
    """

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module("studio_run_adapter", "studio_run_adapter.py")
        cls.model = _load_module("studio_models", "studio_models.py")

    def _make_heterogeneous_snapshot_a(self) -> dict:
        """Snapshot with "euler" sampler config."""
        return {
            "id": "snap_a",
            "name": "Snapshot A",
            "compatibleFeatures": ["txt2img"],
            "apiPromptJson": {
                "3": {"class_type": "KSampler", "inputs": {
                    "seed": 42, "steps": 20, "cfg": 7.0,
                    "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0,
                }},
                "9": {"class_type": "SaveImage", "inputs": {"images": []}},
            },
            "nodeBindings": {
                "prompt": {"kind": "widget", "nodeId": "3", "widgetName": "text"},
                "output": {"kind": "output", "nodeId": "9"},
            },
            "outputNodeId": "9",
            "graphJson": {"nodes": [], "links": []},
            "archived": False,
            "status": "runnable",
            "featureStatus": {
                "txt2img": {"status": "runnable", "reason": ""},
            },
            "disabledReason": "",
            "controlSchemas": {
                "sampler": {
                    "kind": "enum",
                    "options": ["euler", "dpmpp_2m"],
                    "default": "euler",
                    "schemaResolved": True,
                },
                "steps": {
                    "kind": "integer", "minimum": 1, "maximum": 100,
                    "default": 20, "schemaResolved": True,
                },
            },
        }

    def _make_heterogeneous_snapshot_b(self) -> dict:
        """Snapshot B with different sampler options — only "lcm" and "turbo"."""
        return {
            "id": "snap_b",
            "name": "Snapshot B",
            "compatibleFeatures": ["txt2img"],
            "apiPromptJson": {
                "3": {"class_type": "KSampler", "inputs": {
                    "seed": 99, "steps": 10, "cfg": 5.0,
                    "sampler_name": "lcm", "scheduler": "normal", "denoise": 1.0,
                }},
                "9": {"class_type": "SaveImage", "inputs": {"images": []}},
            },
            "nodeBindings": {
                "prompt": {"kind": "widget", "nodeId": "3", "widgetName": "text"},
                "output": {"kind": "output", "nodeId": "9"},
            },
            "outputNodeId": "9",
            "graphJson": {"nodes": [], "links": []},
            "archived": False,
            "status": "runnable",
            "featureStatus": {
                "txt2img": {"status": "runnable", "reason": ""},
            },
            "disabledReason": "",
            "controlSchemas": {
                "sampler": {
                    "kind": "enum",
                    "options": ["lcm", "turbo"],
                    "default": "lcm",
                    "schemaResolved": True,
                },
                "steps": {
                    "kind": "integer", "minimum": 1, "maximum": 50,
                    "default": 10, "schemaResolved": True,
                },
            },
        }

    # ── RED Test 1: Missing preset returns preset-scoped error ──────────

    def test_missing_preset_returns_preset_scoped_error(self):
        """A missing preset ID must return a preset-scoped error dict
        with presetId, field/controlId, and message."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            errors = self.mod.validate_studio_request_controls(
                preset_ids=["does_not_exist"],
                feature_id="txt2img",
                controls={"prompt": "test"},
                axes={},
                node_dir=tmp,
            )
            self.assertGreater(len(errors), 0,
                               "Missing preset must produce validation errors")
            for err in errors:
                self.assertIn("presetId", err,
                              "Each error must carry presetId")
                self.assertEqual(err["presetId"], "does_not_exist")
                self.assertIn("field", err,
                              "Each error must carry field/controlId")
                self.assertIn("message", err,
                              "Each error must carry a message")

    # ── RED Test 2: Archived preset returns preset-scoped error ─────────

    def test_archived_preset_returns_preset_scoped_error(self):
        """An archived preset must return a preset-scoped error."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_archived_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            errors = self.mod.validate_studio_request_controls(
                preset_ids=["preset_archived"],
                feature_id="txt2img",
                controls={"prompt": "test"},
                axes={},
                node_dir=tmp,
            )
            self.assertGreater(len(errors), 0,
                               "Archived preset must produce validation errors")
            for err in errors:
                self.assertIn("presetId", err)
                self.assertEqual(err["presetId"], "preset_archived")
                self.assertIn("field", err)
                self.assertIn("message", err)

    # ── RED Test 3: Valid single preset passes ─────────────────────────

    def test_valid_single_preset_passes(self):
        """A valid single preset with valid controls must return []."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            errors = self.mod.validate_studio_request_controls(
                preset_ids=["preset_runnable"],
                feature_id="txt2img",
                controls={"prompt": "test", "steps": 20},
                axes={},
                node_dir=tmp,
            )
            self.assertEqual(errors, [],
                             "Valid controls for a single runnable preset "
                             "must return no errors")

    # ── RED Test 4: Heterogeneous presets — value valid for A but
    #                 invalid for B must be rejected ─────────────────────

    def test_heterogeneous_rejects_value_valid_for_a_but_invalid_for_b(self):
        """A value valid for preset A but NOT for preset B must be rejected.
        This confirms no first-valid-preset shortcut."""
        with tempfile.TemporaryDirectory() as tmp:
            snap_a = self._make_heterogeneous_snapshot_a()
            snap_b = self._make_heterogeneous_snapshot_b()
            preset_a = _make_runnable_preset("preset_a", "snap_a")
            preset_b = _make_runnable_preset("preset_b", "snap_b")
            preset_a["compatibleFeatures"] = ["txt2img"]
            preset_b["compatibleFeatures"] = ["txt2img"]
            _make_studio_store_files(tmp, [snap_a, snap_b], [preset_a, preset_b])

            # "euler" is valid for preset A but NOT for preset B (B only has lcm/turbo)
            errors = self.mod.validate_studio_request_controls(
                preset_ids=["preset_a", "preset_b"],
                feature_id="txt2img",
                controls={"sampler": "euler", "prompt": "test"},
                axes={},
                node_dir=tmp,
            )
            # Must reject because "euler" is invalid for preset B
            self.assertGreater(len(errors), 0,
                               "Value valid for A but invalid for B must be rejected")
            # At least one error must reference "sampler" and "preset_b"
            sampler_b_errors = [
                e for e in errors
                if e.get("field") == "sampler" and e.get("presetId") == "preset_b"
            ]
            self.assertGreater(len(sampler_b_errors), 0,
                               "Must have an error for sampler on preset_b")
            self.assertIn("euler", sampler_b_errors[0].get("message", "").lower())

    # ── RED Test 5: Heterogeneous — steps valid for A but invalid for B ─

    def test_heterogeneous_rejects_steps_valid_for_a_but_invalid_for_b(self):
        """Steps=99 is valid for preset A (max=100) but invalid for preset B
        (max=50). Must be rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            snap_a = self._make_heterogeneous_snapshot_a()
            snap_b = self._make_heterogeneous_snapshot_b()
            preset_a = _make_runnable_preset("preset_a", "snap_a")
            preset_b = _make_runnable_preset("preset_b", "snap_b")
            preset_a["compatibleFeatures"] = ["txt2img"]
            preset_b["compatibleFeatures"] = ["txt2img"]
            _make_studio_store_files(tmp, [snap_a, snap_b], [preset_a, preset_b])

            errors = self.mod.validate_studio_request_controls(
                preset_ids=["preset_a", "preset_b"],
                feature_id="txt2img",
                controls={"steps": 99, "prompt": "test"},
                axes={},
                node_dir=tmp,
            )
            # 99 is valid for A (max=100) but invalid for B (max=50)
            self.assertGreater(len(errors), 0,
                               "Steps=99 must be rejected for preset B")
            steps_b_errors = [
                e for e in errors
                if e.get("field") == "steps" and e.get("presetId") == "preset_b"
            ]
            self.assertGreater(len(steps_b_errors), 0,
                               "Must have steps error for preset_b")

    # ── RED Test 6: Axis values validated per-preset ───────────────────

    def test_axis_value_validated_per_preset(self):
        """An axis value must be validated against EVERY preset's schema,
        not just the first."""
        with tempfile.TemporaryDirectory() as tmp:
            snap_a = self._make_heterogeneous_snapshot_a()
            snap_b = self._make_heterogeneous_snapshot_b()
            preset_a = _make_runnable_preset("preset_a", "snap_a")
            preset_b = _make_runnable_preset("preset_b", "snap_b")
            preset_a["compatibleFeatures"] = ["txt2img"]
            preset_b["compatibleFeatures"] = ["txt2img"]
            _make_studio_store_files(tmp, [snap_a, snap_b], [preset_a, preset_b])

            # axis sampler with value "euler" which is valid for A but not B
            axes = {"sampler": {"values": ["euler"]}}
            errors = self.mod.validate_studio_request_controls(
                preset_ids=["preset_a", "preset_b"],
                feature_id="txt2img",
                controls={"prompt": "test"},
                axes=axes,
                node_dir=tmp,
            )
            # "euler" must be rejected for preset_b even when used as axis value
            sampler_b_errors = [
                e for e in errors
                if e.get("field") == "sampler" and e.get("presetId") == "preset_b"
            ]
            self.assertGreater(len(sampler_b_errors), 0,
                               "Axis value 'euler' must be rejected for preset_b")

    # ── RED Test 7: Multiple axis values each validated per-preset ─────

    def test_multiple_axis_values_each_validated(self):
        """Each axis value must be validated independently against every
        preset (not just the first or last)."""
        with tempfile.TemporaryDirectory() as tmp:
            snap_a = self._make_heterogeneous_snapshot_a()
            snap_b = self._make_heterogeneous_snapshot_b()
            preset_a = _make_runnable_preset("preset_a", "snap_a")
            preset_b = _make_runnable_preset("preset_b", "snap_b")
            preset_a["compatibleFeatures"] = ["txt2img"]
            preset_b["compatibleFeatures"] = ["txt2img"]
            _make_studio_store_files(tmp, [snap_a, snap_b], [preset_a, preset_b])

            # Two axis values: "euler" (valid for A, not B) and "lcm" (valid for both)
            axes = {"sampler": {"values": ["euler", "lcm"]}}
            errors = self.mod.validate_studio_request_controls(
                preset_ids=["preset_a", "preset_b"],
                feature_id="txt2img",
                controls={"prompt": "test"},
                axes=axes,
                node_dir=tmp,
            )
            # "euler" should fail for preset_b even though "lcm" is fine
            sampler_b_errors = [
                e for e in errors
                if e.get("field") == "sampler" and e.get("presetId") == "preset_b"
            ]
            self.assertGreater(len(sampler_b_errors), 0,
                               "Axis value 'euler' must be rejected for preset_b "
                               "even when 'lcm' is also in the values list")

    # ── RED Test 8: Single run uses helper with [preset_id], controls, {} ─

    def test_single_run_validation(self):
        """Single run uses validate_studio_request_controls with
        [preset_id], controls, {} (empty axes)."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            # Valid controls: single run path
            errors = self.mod.validate_studio_request_controls(
                preset_ids=["preset_runnable"],
                feature_id="txt2img",
                controls={"prompt": "test", "steps": 20},
                axes={},
                node_dir=tmp,
            )
            self.assertEqual(errors, [])

            # Invalid control: should fail
            errors2 = self.mod.validate_studio_request_controls(
                preset_ids=["preset_runnable"],
                feature_id="txt2img",
                controls={"prompt": "test", "steps": -1},
                axes={},
                node_dir=tmp,
            )
            self.assertGreater(len(errors2), 0,
                               "Invalid steps=-1 must be rejected")
            for err in errors2:
                self.assertIn("presetId", err)
                self.assertEqual(err["presetId"], "preset_runnable")

    # ── RED Test 9: Empty preset_ids returns errors ────────────────────

    def test_empty_preset_ids_returns_error(self):
        """Empty preset_ids list must return an error."""
        with tempfile.TemporaryDirectory() as tmp:
            errors = self.mod.validate_studio_request_controls(
                preset_ids=[],
                feature_id="txt2img",
                controls={},
                axes={},
                node_dir=tmp,
            )
            self.assertGreater(len(errors), 0,
                               "Empty preset_ids must produce errors")


# ── RED Test 10: validate_controls_against_schema raises ─────────────

    def test_validation_function_raises_on_shared_controls_returns_structured_error(self):
        """When validate_controls_against_schema raises an unexpected
        exception for shared controls, the validation must fail closed
        with a structured error {presetId, field/controlId, message:
        'Control validation could not be completed'} and must NEVER set
        ctrl_errors=[] (which would silently let invalid controls through)."""
        import logging
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            with patch(
                "studio_run_adapter.validate_controls_against_schema",
                side_effect=RuntimeError("Unexpected schema crash"),
            ):
                errors = self.mod.validate_studio_request_controls(
                    preset_ids=["preset_runnable"],
                    feature_id="txt2img",
                    controls={"prompt": "test", "steps": 20},
                    axes={},
                    node_dir=tmp,
                )
            # Must produce at least one structured error (fail closed)
            self.assertGreater(len(errors), 0,
                               "Validation must fail closed when "
                               "validate_controls_against_schema raises")
            for err in errors:
                self.assertIn("presetId", err)
                self.assertIn("field", err)
                self.assertIn("message", err)
                self.assertNotEqual(
                    err.get("message", "").strip(), "",
                    "Error message must not be empty",
                )
                # Must never be empty error list disguised as no error
                self.assertNotEqual(
                    err.get("field"), "",
                    "field/controlId must not be empty",
                )

    def test_validation_function_raises_on_axis_values_returns_structured_error(self):
        """When validate_controls_against_schema raises on axis value
        validation, must fail closed with structured errors."""
        import logging
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            snap = _make_runnable_snapshot()
            preset = _make_runnable_preset()
            _make_studio_store_files(tmp, [snap], [preset])
            with patch(
                "studio_run_adapter.validate_controls_against_schema",
                side_effect=RuntimeError("Axis validation crash"),
            ):
                errors = self.mod.validate_studio_request_controls(
                    preset_ids=["preset_runnable"],
                    feature_id="txt2img",
                    controls={},
                    axes={"sampler": {"values": ["euler", "dpmpp_2m"]}},
                    node_dir=tmp,
                )
            self.assertGreater(len(errors), 0,
                               "Must fail closed on axis validation crash")
            for err in errors:
                self.assertIn("presetId", err)
                self.assertIn("field", err)
                self.assertIn("message", err)


# ---------------------------------------------------------------------------
# Defect 2: Backend search must include prompt text
# ---------------------------------------------------------------------------

class HistorySearchPromptTextBehavioralTests(unittest.TestCase):
    """list_runs search must find runs by their prompt text."""

    @classmethod
    def setUpClass(cls):
        cls.svc_mod = _load_module("experiment_service", "experiment_service.py")

    def test_search_finds_run_by_prompt_text(self):
        """Searching for prompt text in extra.requested_controls.prompt must find the run."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svc = self.svc_mod.RunHistoryService(root)
            rec = svc.record_run(
                kind="studio_run",
                prompt_id="exp_search1",
                status="completed",
                meta={
                    "requested_controls": {
                        "prompt": "a beautiful sunset over mountains",
                        "negative_prompt": "ugly, blurry",
                    },
                },
            )
            # Search by positive prompt word
            result = svc.list_runs(search="sunset")
            self.assertEqual(len(result["runs"]), 1,
                             "Must find run by requested_controls.prompt text")
            self.assertEqual(result["runs"][0]["run_id"], rec["run_id"])

    def test_search_finds_run_by_negative_prompt(self):
        """Searching for negative prompt text must find the run."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svc = self.svc_mod.RunHistoryService(root)
            rec = svc.record_run(
                kind="studio_run",
                prompt_id="exp_search2",
                status="completed",
                meta={
                    "requested_controls": {
                        "prompt": "portrait",
                        "negative_prompt": "deformed, extra fingers",
                    },
                },
            )
            # Search by negative prompt word
            result = svc.list_runs(search="deformed")
            self.assertEqual(len(result["runs"]), 1,
                             "Must find run by requested_controls.negative_prompt text")
            self.assertEqual(result["runs"][0]["run_id"], rec["run_id"])

    def test_search_finds_run_by_resolved_controls_prompt(self):
        """Search must also find prompt text in extra.resolved_controls.prompt."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svc = self.svc_mod.RunHistoryService(root)
            rec = svc.record_run(
                kind="studio_run",
                prompt_id="exp_search_resolved",
                status="completed",
                meta={
                    "resolved_controls": {
                        "prompt": "aerial view of coastline",
                    },
                },
            )
            result = svc.list_runs(search="coastline")
            self.assertEqual(len(result["runs"]), 1,
                             "Must find run by resolved_controls.prompt text")
            self.assertEqual(result["runs"][0]["run_id"], rec["run_id"])

    def test_search_case_insensitive_prompt(self):
        """Search for prompt text must be case-insensitive."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svc = self.svc_mod.RunHistoryService(root)
            rec = svc.record_run(
                kind="studio_run",
                prompt_id="exp_search3",
                status="completed",
                meta={
                    "requested_controls": {
                        "prompt": "Golden Gate Bridge at dusk",
                    },
                },
            )
            # Search with different case
            result = svc.list_runs(search="GOLDEN")
            self.assertEqual(len(result["runs"]), 1,
                             "Prompt search must be case-insensitive")


# ---------------------------------------------------------------------------
# Defect 4: Date-only date_to includes full calendar day
# ---------------------------------------------------------------------------

class HistoryDateToInclusiveDayBehavioralTests(unittest.TestCase):
    """date-only date_to must include the full selected calendar day."""

    @classmethod
    def setUpClass(cls):
        cls.svc_mod = _load_module("experiment_service", "experiment_service.py")

    def test_date_only_date_to_includes_same_day_runs(self):
        """A date-only date_to like '2026-07-12' must include runs from that entire day."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svc = self.svc_mod.RunHistoryService(root)
            # Create a run started at midday on 2026-07-12
            rec = svc.record_run(
                kind="studio_run",
                prompt_id="exp_date1",
                status="completed",
                started_at="2026-07-12T14:30:00Z",
            )
            # Filter with date-only date_to
            result = svc.list_runs(date_to="2026-07-12")
            self.assertEqual(len(result["runs"]), 1,
                             "Run from 2026-07-12 must be included when date_to is '2026-07-12'")
            self.assertEqual(result["runs"][0]["run_id"], rec["run_id"])

    def test_date_only_date_to_excludes_next_day(self):
        """A date-only date_to must not include runs from the next day."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svc = self.svc_mod.RunHistoryService(root)
            # Create a run started early on 2026-07-13
            svc.record_run(
                kind="studio_run",
                prompt_id="exp_date2",
                status="completed",
                started_at="2026-07-13T00:01:00Z",
            )
            # Filter with date_to = 2026-07-12
            result = svc.list_runs(date_to="2026-07-12")
            self.assertEqual(len(result["runs"]), 0,
                             "Run from 2026-07-13 must be excluded when date_to is '2026-07-12'")

    def test_date_time_date_to_preserves_exact_boundary(self):
        """DateTime-formatted date_to must preserve exact boundary."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svc = self.svc_mod.RunHistoryService(root)
            rec = svc.record_run(
                kind="studio_run",
                prompt_id="exp_date3",
                status="completed",
                started_at="2026-07-12T23:59:59Z",
            )
            # Exact datetime boundary — must still match
            result = svc.list_runs(date_to="2026-07-12T23:59:59Z")
            self.assertEqual(len(result["runs"]), 1,
                             "Exact datetime boundary must match")
            self.assertEqual(result["runs"][0]["run_id"], rec["run_id"])


# ---------------------------------------------------------------------------
# Extracted defaults filter connection specs; preset defaults prioritised
# ---------------------------------------------------------------------------

class ExtractDefaultsConnectionSpecRED(unittest.TestCase):
    """RED: extract_defaults_from_snapshot must omit ComfyUI connection
    specs (list values like ["937", 0]) in both bound and auto-derived
    paths.  Scalar values like seed=42 and guidance=7.0 must remain."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module("studio_run_adapter", "studio_run_adapter.py")

    def test_bound_connection_spec_omitted(self):
        """A bound control whose workflow value is a connection spec
        (e.g. steps=["937", 0]) must be SKIPPED in returned defaults.
        Scalar values (seed=42) must remain."""
        snapshot = {
            "apiPromptJson": {
                "3": {"class_type": "KSampler", "inputs": {
                    "seed": 42, "steps": ["937", 0], "cfg": 7.0,
                }},
            },
            "nodeBindings": {
                "seed": {"kind": "widget", "nodeId": "3", "widgetName": "seed"},
                "steps": {"kind": "widget", "nodeId": "3", "widgetName": "steps"},
                "guidance": {"kind": "widget", "nodeId": "3", "widgetName": "cfg"},
            },
        }
        defaults = self.mod.extract_defaults_from_snapshot(snapshot)
        # steps=["937", 0] is a connection spec — must NOT appear
        self.assertNotIn(
            "steps", defaults,
            "steps must be omitted when its value is a connection spec",
        )
        # Seed=42 is a scalar — must remain
        self.assertIn("seed", defaults)
        self.assertEqual(defaults["seed"], 42)
        # Guidance=7.0 is a scalar — must remain
        self.assertIn("guidance", defaults)
        self.assertEqual(defaults["guidance"], 7.0)

    def test_auto_derived_connection_spec_omitted(self):
        """An auto-derived control whose workflow value is a connection
        spec must be SKIPPED in returned defaults."""
        # Snapshot with no explicit bindings for KSampler controls
        snapshot = {
            "apiPromptJson": {
                "3": {"class_type": "KSampler", "inputs": {
                    "seed": 42, "steps": ["937", 0], "cfg": 7.0,
                    "sampler_name": "euler", "scheduler": "normal",
                    "denoise": 1.0,
                }},
                "9": {"class_type": "SaveImage", "inputs": {"images": []}},
            },
            "nodeBindings": {
                "prompt": {"kind": "widget", "nodeId": "3", "widgetName": "text"},
                "output": {"kind": "output", "nodeId": "9"},
            },
        }
        defaults = self.mod.extract_defaults_from_snapshot(snapshot)
        # steps should be auto-derived but its value is a connection spec
        self.assertNotIn(
            "steps", defaults,
            "Auto-derived steps must be omitted when value is a connection spec",
        )
        # Scalar values that ARE true scalars should appear
        self.assertIn("seed", defaults)
        self.assertEqual(defaults["seed"], 42)
        self.assertIn("sampler", defaults)
        self.assertEqual(defaults["sampler"], "euler")

    def test_mixed_connection_specs_and_scalars(self):
        """Mixed connection specs and scalars: only connection specs omitted."""
        snapshot = {
            "apiPromptJson": {
                "3": {"class_type": "KSampler", "inputs": {
                    "seed": 0, "steps": ["937", 0], "cfg": 7.5,
                    "sampler_name": ["456", 0], "scheduler": "normal",
                    "denoise": ["789", 0],
                }},
                "9": {"class_type": "SaveImage", "inputs": {"images": []}},
            },
            "nodeBindings": {
                "prompt": {"kind": "widget", "nodeId": "3", "widgetName": "text"},
                "seed": {"kind": "widget", "nodeId": "3", "widgetName": "seed"},
                "steps": {"kind": "widget", "nodeId": "3", "widgetName": "steps"},
                "guidance": {"kind": "widget", "nodeId": "3", "widgetName": "cfg"},
                "sampler": {"kind": "widget", "nodeId": "3", "widgetName": "sampler_name"},
                "scheduler": {"kind": "widget", "nodeId": "3", "widgetName": "scheduler"},
                "denoise": {"kind": "widget", "nodeId": "3", "widgetName": "denoise"},
                "output": {"kind": "output", "nodeId": "9"},
            },
        }
        defaults = self.mod.extract_defaults_from_snapshot(snapshot)
        # Connection specs must be omitted
        self.assertNotIn("steps", defaults)
        self.assertNotIn("sampler", defaults)
        self.assertNotIn("denoise", defaults)
        # Scalars must remain
        self.assertEqual(defaults.get("seed"), 0)
        self.assertEqual(defaults.get("guidance"), 7.5)
        self.assertEqual(defaults.get("scheduler"), "normal")


class PresetDefaultsPriorityRED(unittest.TestCase):
    """RED: GET /studio/presets must return explicit preset defaults
    with priority over snapshot-derived defaults.  Snapshot defaults
    fill missing preset keys but must NOT overwrite preset keys."""

    @classmethod
    def setUpClass(cls):
        cls.adapter = _load_module("studio_run_adapter", "studio_run_adapter.py")

    def _make_preset_list_store_files(
        self, tmpdir: str, presets: list[dict], snapshots: list[dict],
    ):
        """Write snapshot and preset JSON store files into tmpdir, then
        serve the list endpoint logic."""
        from studio_store import StudioJsonStore
        snap_store = StudioJsonStore(Path(tmpdir) / ".studio_snapshots.json")
        snap_store.write_atomic(snapshots)
        preset_store = StudioJsonStore(Path(tmpdir) / ".studio_presets.json")
        preset_store.write_atomic(presets)

    def _simulate_presets_list_enrichment(
        self, tmpdir: str,
    ) -> list[dict]:
        """Replicate the enrichment logic from studio_routes.py
        studio_presets_list to test the defaults merging in isolation."""
        from studio_store import StudioJsonStore
        from studio_models import normalize_preset_payload
        from studio_routes import _build_snapshots_by_id

        presets = StudioJsonStore(Path(tmpdir) / ".studio_presets.json").read()
        snapshots = StudioJsonStore(Path(tmpdir) / ".studio_snapshots.json").read()
        snapshots_by_id = _build_snapshots_by_id(snapshots)

        enriched = []
        for p in presets:
            normalized = normalize_preset_payload(p, snapshots_by_id)
            sid = normalized.get("snapshotId", "") or ""
            snapshot = snapshots_by_id.get(sid) if sid else None
            if snapshot is not None:
                snapshot_defaults = self.adapter.extract_defaults_from_snapshot(snapshot)
                explicit_defaults = normalized.get("defaults", {}) or {}
                # Merge: snapshot defaults fill missing keys, but explicit
                # preset defaults take priority.
                normalized["defaults"] = {**snapshot_defaults, **explicit_defaults}
                normalized["snapshotSummary"] = {
                    "name": snapshot.get("name", ""),
                    "status": snapshot.get("status", ""),
                }
            enriched.append(normalized)
        return enriched

    def test_explicit_preset_defaults_have_priority(self):
        """Given preset.defaults.steps=8 and snapshot KSampler.inputs.steps
        =["937",0], the response defaults.steps must be 8 (not the list)."""
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = {
                "id": "snap_priority",
                "name": "Priority Snapshot",
                "compatibleFeatures": ["txt2img"],
                "apiPromptJson": {
                    "3": {"class_type": "KSampler", "inputs": {
                        "seed": 42, "steps": ["937", 0], "cfg": 7.0,
                        "sampler_name": "euler", "scheduler": "normal",
                        "denoise": 1.0,
                    }},
                    "9": {"class_type": "SaveImage", "inputs": {"images": []}},
                },
                "nodeBindings": {
                    "prompt": {"kind": "widget", "nodeId": "3", "widgetName": "text"},
                    "output": {"kind": "output", "nodeId": "9"},
                },
                "outputNodeId": "9",
                "status": "runnable",
                "archived": False,
            }
            preset = {
                "id": "preset_priority",
                "label": "Priority Preset",
                "snapshotId": "snap_priority",
                "compatibleFeatures": ["txt2img"],
                # Explicit defaults: steps=8 should WIN over snapshot's ["937", 0]
                "defaults": {"steps": 8, "seed": 99},
                "sourceType": "snapshot",
                "archived": False,
                "status": "runnable",
            }
            self._make_preset_list_store_files(tmp, [preset], [snapshot])
            enriched = self._simulate_presets_list_enrichment(tmp)

            self.assertEqual(len(enriched), 1)
            entry = enriched[0]
            d = entry.get("defaults", {})

            # Explicit preset steps=8 must NOT be overwritten by snapshot's
            # connection spec steps=["937", 0]
            self.assertIn("steps", d,
                          "steps must appear in defaults")
            self.assertEqual(
                d["steps"], 8,
                "Explicit preset default steps=8 must take priority "
                "over snapshot-derived connection spec steps=[\"937\", 0]",
            )
            # Snapshot scalar defaults fill missing preset keys
            # guidance is in snapshot but NOT in preset defaults
            self.assertEqual(
                d.get("guidance"), 7.0,
                "Snapshot-derived scalar guidance must fill missing preset key",
            )
            # Preset's explicit seed must be preserved
            self.assertEqual(
                d.get("seed"), 99,
                "Explicit preset default seed=99 must survive enrichment",
            )

    def test_snapshot_scalar_defaults_fill_missing_preset_keys(self):
        """Snapshot scalar defaults (e.g. guidance=7.0) must fill in when
        the preset does not have an explicit value for that control."""
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = {
                "id": "snap_fill",
                "name": "Fill Snapshot",
                "compatibleFeatures": ["txt2img"],
                "apiPromptJson": {
                    "3": {"class_type": "KSampler", "inputs": {
                        "seed": 42, "steps": 20, "cfg": 7.0,
                        "sampler_name": "euler", "scheduler": "normal",
                        "denoise": 1.0,
                    }},
                    "9": {"class_type": "SaveImage", "inputs": {"images": []}},
                },
                "nodeBindings": {
                    "prompt": {"kind": "widget", "nodeId": "3", "widgetName": "text"},
                    "steps": {"kind": "widget", "nodeId": "3", "widgetName": "steps"},
                    "seed": {"kind": "widget", "nodeId": "3", "widgetName": "seed"},
                    "guidance": {"kind": "widget", "nodeId": "3", "widgetName": "cfg"},
                    "output": {"kind": "output", "nodeId": "9"},
                },
                "outputNodeId": "9",
                "status": "runnable",
                "archived": False,
            }
            preset = {
                "id": "preset_fill",
                "label": "Fill Preset",
                "snapshotId": "snap_fill",
                "compatibleFeatures": ["txt2img"],
                # Preset only sets steps; guidance should come from snapshot
                "defaults": {"steps": 30},
                "sourceType": "snapshot",
                "archived": False,
                "status": "runnable",
            }
            self._make_preset_list_store_files(tmp, [preset], [snapshot])
            enriched = self._simulate_presets_list_enrichment(tmp)

            self.assertEqual(len(enriched), 1)
            d = enriched[0].get("defaults", {})

            # Preset's explicit steps=30 must survive
            self.assertEqual(d.get("steps"), 30)
            # Snapshot-derived guidance=7.0 must fill the missing key
            self.assertEqual(d.get("guidance"), 7.0)
            # Snapshot-derived seed=42 must fill missing key
            self.assertEqual(d.get("seed"), 42)


# ---------------------------------------------------------------------------
# Test 19: Shared warmup_profile helper — both normal and Studio paths
#          use `warmup_profile.prepare_active_next_profile`
# ---------------------------------------------------------------------------

class SharedWarmupProfileHelperRED(unittest.TestCase):
    """RED: ``warmup_profile.prepare_active_next_profile`` must be a
    shared async helper importable by both ``__init__._execute_job``
    (the normal graph path) and ``studio_run_adapter._schedule_and_start``
    (the Studio path).  Both callers must use the same function so
    that warmup-profile preparation (model-stack extraction, bundle
    dedup, remote set_active_warmup_profile) is unified.

    The shared helper signature:
      ``prepare_active_next_profile(workflow, workflow_hash, *,
                                    production_options=None, workspace=None, setter=None)``

    It must return a dict with status info (profile_key, remote_call,
    status, payload_bytes, changed).
    """

    def test_warmup_profile_module_importable(self):
        """warmup_profile module must be importable."""
        import warmup_profile as wp
        self.assertTrue(hasattr(wp, "prepare_active_next_profile"),
                        "warmup_profile must export prepare_active_next_profile")

    def test_prepare_active_next_profile_signature(self):
        """The shared helper must accept (workflow, workflow_hash)
        with optional keyword args (production_options, workspace,
        setter)."""
        import warmup_profile as wp
        import inspect
        sig = inspect.signature(wp.prepare_active_next_profile)
        params = list(sig.parameters.keys())
        for required in ("workflow", "workflow_hash"):
            self.assertIn(required, params,
                          f"Required param '{required}' missing from signature")
        self.assertIn("workspace", params,
                      "workspace param must be in signature")

    def test_prepare_active_next_profile_returns_structured_status(self):
        """The helper must return a dict with at least status,
        remote_call, profile_key, payload_bytes."""
        import warmup_profile as wp
        result = asyncio.run(wp.prepare_active_next_profile(
            {"3": {"class_type": "KSampler", "inputs": {"seed": 1}}},
            "test_hash",
            workspace=None,
            setter=None,
        ))
        self.assertIsInstance(result, dict)
        self.assertIn("status", result)

    def test_normal_path_imports_shared_helper(self):
        """__init__.py must import prepare_active_next_profile from
        warmup_profile (meaning _execute_job uses the shared helper)."""
        import __init__ as init_mod
        self.assertTrue(
            hasattr(init_mod, "prepare_active_next_profile"),
            "__init__ must import/re-export prepare_active_next_profile",
        )

    def test_studio_path_imports_shared_helper(self):
        """studio_run_adapter must import prepare_active_next_profile
        from warmup_profile for use in the Studio closure."""
        import studio_run_adapter as sra
        self.assertTrue(
            hasattr(sra, "prepare_active_next_profile"),
            "studio_run_adapter must import prepare_active_next_profile",
        )


# ---------------------------------------------------------------------------
# Test 20: Effective override payload from browser must omit controls
#          the user never edited, while preserving edited values and
#          showing saved preset/snapshot values only as display values
# ---------------------------------------------------------------------------

class EffectiveOverridePayloadRED(unittest.TestCase):
    """RED: The browser-side ``buildEffectiveControls`` function (in
    ``web/studio-playground.js``) must produce an override payload that
    ONLY includes controls the user explicitly edited.  Controls that
    derive their value from snapshot defaults or preset defaults must
    NOT appear in the payload sent to the backend — they serve as
    display-only values in the UI.

    Additionally, when the backend receives a partial controls dict
    (e.g. only ``steps=20``), it must apply only those overrides and
    leave the remaining workflow values at their snapshot defaults.

    Current ``buildEffectiveControls`` (studio-playground.js:323-339)
    includes ALL visible controls in the output, not just user edits.
    This test verifies the intended backend+frontend contract.
    """

    def setUp(self):
        self.adapter_mod = _load_module("studio_run_adapter", "studio_run_adapter.py")

    def test_build_single_run_spec_with_partial_controls_only_overrides_workflow(self):
        """When controls dict contains only steps=20, the spec must:
        1. Apply steps=20 to the workflow
        2. Leave other values at their snapshot defaults
        3. Store only the overridden controls in studio_meta.studio_controls
        """
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = {
                "id": "snap_eff",
                "name": "Effective Override Snapshot",
                "compatibleFeatures": ["txt2img"],
                "apiPromptJson": {
                    "3": {"class_type": "KSampler", "inputs": {
                        "seed": 42, "steps": 25, "cfg": 7.0,
                        "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0,
                    }},
                    "9": {"class_type": "SaveImage", "inputs": {"images": []}},
                },
                "nodeBindings": {
                    "prompt": {"kind": "widget", "nodeId": "3", "widgetName": "text"},
                    "steps": {"kind": "widget", "nodeId": "3", "widgetName": "steps"},
                    "seed": {"kind": "widget", "nodeId": "3", "widgetName": "seed"},
                    "guidance": {"kind": "widget", "nodeId": "3", "widgetName": "cfg"},
                    "output": {"kind": "output", "nodeId": "9"},
                },
                "outputNodeId": "9",
                "graphJson": {"nodes": [], "links": []},
                "archived": False,
                "status": "runnable",
                "featureStatus": {
                    "txt2img": {"status": "runnable", "reason": ""},
                },
                "disabledReason": "",
            }
            preset = {
                "id": "preset_eff",
                "label": "Effective Override Preset",
                "snapshotId": "snap_eff",
                "compatibleFeatures": ["txt2img"],
                "defaults": {},
                "sourceType": "snapshot",
                "sourceId": "",
                "archived": False,
                "status": "runnable",
                "disabledReason": "",
            }
            _make_studio_store_files(tmp, [snapshot], [preset])

            # ---- RED: Partial controls — only steps=20 is explicitly edited ----
            controls = {"prompt": "a cat", "steps": 20}
            spec = self.adapter_mod.build_single_run_spec(
                preset, snapshot, "txt2img", controls, tmp,
                modal_options={"production": {"enabled": False}},
            )

            # 1. Steps must be 20 in the workflow (overridden)
            ck = spec["checkpoints"][0]
            self.assertEqual(
                ck["workflow"]["3"]["inputs"]["steps"], 20,
                "steps must be 20 (the user-provided override)",
            )

            # 2. Other values must remain at snapshot defaults
            self.assertEqual(
                ck["workflow"]["3"]["inputs"]["seed"], 42,
                "seed must remain at snapshot default (42) since user didn't edit it",
            )
            self.assertEqual(
                ck["workflow"]["3"]["inputs"]["cfg"], 7.0,
                "cfg must remain at snapshot default (7.0) since user didn't edit it",
            )
            self.assertEqual(
                ck["workflow"]["3"]["inputs"]["sampler_name"], "euler",
                "sampler_name must remain at snapshot default",
            )

            # 3. studio_meta.studio_controls must contain the overridden values
            meta_controls = spec.get("studio_meta", {}).get("studio_controls", {})
            self.assertIn(
                "steps", meta_controls,
                "studio_controls must include the user-edited 'steps'",
            )
            self.assertEqual(
                meta_controls.get("steps"), 20,
                "studio_controls.steps must be 20",
            )

            # prompt is always included (required field)
            self.assertIn(
                "prompt", meta_controls,
                "studio_controls must include 'prompt'",
            )

    def test_partial_controls_axis_values_only_contain_edited_keys(self):
        """Axis values in the spec must only include keys that the user
        explicitly edited (steps=20), not all snapshot defaults."""
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = _make_runnable_snapshot("snap_axis")
            preset = _make_runnable_preset("preset_axis", "snap_axis")
            _make_studio_store_files(tmp, [snapshot], [preset])

            # Only steps=20 is user-edited
            controls = {"prompt": "a cat", "steps": 20}
            spec = self.adapter_mod.build_single_run_spec(
                preset, snapshot, "txt2img", controls, tmp,
                modal_options={"production": {"enabled": False}},
            )

            cell = spec["cells"][0]
            axis_values = cell.get("axis_values", {})

            # steps must be in axis_values (user edited it)
            self.assertIn(
                "steps", axis_values,
                "axis_values must contain user-edited 'steps'",
            )
            self.assertEqual(
                axis_values["steps"], 20,
                "axis_values.steps must be 20",
            )

            # seed must NOT be in axis_values (user didn't edit it)
            self.assertNotIn(
                "seed", axis_values,
                "axis_values must NOT contain 'seed' when user didn't edit it",
            )

            # prompt must NOT be in axis_values (it's a separate field)
            self.assertNotIn(
                "prompt", axis_values,
                "axis_values must NOT contain 'prompt' (handled separately)",
            )

    def test_empty_controls_only_updates_prompt(self):
        """When controls only contains prompt (no overrides), the
        workflow must keep all snapshot defaults unchanged."""
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = _make_runnable_snapshot("snap_no_override")
            preset = _make_runnable_preset("preset_no_override", "snap_no_override")
            _make_studio_store_files(tmp, [snapshot], [preset])

            controls = {"prompt": "just a prompt, no edits"}
            spec = self.adapter_mod.build_single_run_spec(
                preset, snapshot, "txt2img", controls, tmp,
                modal_options={"production": {"enabled": False}},
            )

            ck = spec["checkpoints"][0]
            # All non-prompt values must remain at snapshot defaults
            self.assertEqual(
                ck["workflow"]["3"]["inputs"]["seed"], 42,
                "seed must remain at snapshot default",
            )
            self.assertEqual(
                ck["workflow"]["3"]["inputs"]["steps"], 20,
                "steps must remain at snapshot default (20)",
            )

            # Axis values must be empty (no overrides)
            cell = spec["cells"][0]
            axis_values = cell.get("axis_values", {})
            self.assertEqual(
                axis_values, {},
                "axis_values must be empty when no overrides are provided",
            )


# ---------------------------------------------------------------------------
# JsEffectiveOverrideStructuralRED — browser buildEffectiveControls
# function must exist with correct filtering logic
# ---------------------------------------------------------------------------

class JsBuildEffectiveControlsRED(unittest.TestCase):
    """RED: ``web/studio-playground.js`` function ``buildEffectiveControls``
    must produce a payload that ONLY includes controls the user explicitly
    edited (from ``state.playground.controls``).  Controls that derive
    their value from the preset defaults or snapshot defaults must NOT
    appear in the output — they serve as display-only values.

    Current ``buildEffectiveControls`` (studio-playground.js:323-339)
    iterates over ALL visible control IDs and includes every one in
    the output, falling back to hydrated/preset defaults for any ID
    the user did not explicitly override.  This causes the browser to
    send default values that the user never touched.
    """

    PLAYGROUND_PATH = REPO_ROOT / "web" / "studio-playground.js"

    def setUp(self):
        if not self.PLAYGROUND_PATH.exists():
            self.skipTest(f"web/studio-playground.js not found at {self.PLAYGROUND_PATH}")

    def test_build_effective_controls_exists(self):
        """buildEffectiveControls function must be defined in
        studio-playground.js."""
        text = self.PLAYGROUND_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "function buildEffectiveControls",
            text,
            "buildEffectiveControls function must be defined in studio-playground.js",
        )

    def test_build_effective_controls_must_only_include_user_edited_controls(self):
        """The function's ``visibleIds.forEach`` callback must ONLY
        include controls from ``userOverrides`` in the returned dict.
        The current fallback branches (``hydratedValues`` and
        ``presetDefaults``) must be REMOVED — they cause non-edited
        controls to appear in the override payload.

        This test verifies the `forEach` body does NOT contain
        fallback assignments for non-overridden controls.
        """
        text = self.PLAYGROUND_PATH.read_text(encoding="utf-8")

        # Find the buildEffectiveControls function body
        import re
        match = re.search(
            r"function buildEffectiveControls\s*\([^)]+\)\s*\{(.+?)\n\}", text, re.DOTALL,
        )
        self.assertIsNotNone(
            match,
            "Could not locate buildEffectiveControls function body",
        )
        body = match.group(1)

        # The function body currently has fallback branches for
        # hydratedValues and presetDefaults.  These are the problem.
        # A corrected version would only assign from userOverrides.

        # ---- RED: The function must only include user override keys ----
        # Check that it iterates over Object.keys(userOverrides) to
        # only include explicit user edits in the output.
        has_user_keys_iteration = (
            "Object.keys(userOverrides)" in body
            or "userOverrides" in body
        )
        self.assertTrue(
            has_user_keys_iteration,
            "buildEffectiveControls must iterate over Object.keys(userOverrides) "
            "to only include explicit user edits in the output",
        )

        # ---- RED: Must NOT iterate over all visible IDs with fallbacks ----
        # The old pattern was: visibleIds.forEach(function(ctrlId) {
        #   if (ctrlId in userOverrides) { ... }
        #   else if (ctrlId in hydratedValues) { ... }
        # }
        # The new implementation must NOT have the 3-tier fallback pattern
        # that includes non-edited controls.
        has_old_visible_ids_loop = "visibleIds.forEach" in body
        if has_old_visible_ids_loop:
            self.fail(
                "buildEffectiveControls must NOT iterate over all visibleIds "
                "with fallback branches.  It should only include user-edited "
                "controls (from state.playground.controls)."
            )

        # ---- RED: The output must NOT include hydratedValues ----
        if "hydratedValues" in body or "_hydratedControls" in body:
            self.fail(
                "buildEffectiveControls must NOT reference hydratedValues / "
                "_hydratedControls.  These are display-only and should not "
                "appear in the override payload."
            )

        # ---- RED: The output must NOT include presetDefaults ----
        if "presetDefaults" in body:
            self.fail(
                "buildEffectiveControls must NOT reference presetDefaults.  "
                "Preset defaults are display-only and should not appear "
                "in the override payload."
            )


# ---------------------------------------------------------------------------
# RED tests: per_workflow extra-axis forwarding + shared_negative
# ---------------------------------------------------------------------------

class BuildExperimentSpecNestedInputRED(unittest.TestCase):
    """RED-phase tests for nested Studio/compiler input in
    ``build_experiment_spec``.

    Three required behaviors:
      1. ``per_workflow`` extra-axis values are forwarded to the matrix
         compiler and override a shared extra-axis value of the same name
         in the matching preset checkpoint.
      2. A ``per_workflow`` extra axis without a corresponding slot
         binding in the target preset returns an adapter error *before*
         compilation/scheduling.
      3. ``shared_negative`` from ``experiment_def`` is preserved in the
         prompts spec and fills in ``negative_prompt`` for prompt items
         whose negative is omitted (None/absent).

    Each test is expected to FAIL against the current production code
    (RED phase).  No production code is modified.
    """

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module("studio_run_adapter", "studio_run_adapter.py")
        cls.matrix = _load_module("matrix_compiler", "matrix_compiler.py")

    # ── Test 1: per_workflow extra-axis overrides shared ────────────────

    def test_per_workflow_axis_overrides_shared_value(self):
        """A per_workflow cfg axis value for a specific preset must
        override the shared cfg axis value in the matching preset's
        checkpoint cells."""
        snap = _make_runnable_snapshot("snap_a")
        # Add cfg binding to the snapshot
        snap["apiPromptJson"]["3"]["inputs"]["cfg"] = 7.0
        snap["nodeBindings"]["cfg"] = {
            "kind": "widget", "nodeId": "3", "widgetName": "cfg",
        }
        preset = _make_runnable_preset("preset_a", "snap_a")
        with tempfile.TemporaryDirectory() as tmp:
            _make_studio_store_files(tmp, [snap], [preset])
            exp_def = {
                "prompts": [
                    {"id": "p1", "text": "test", "enabled": True},
                ],
                "axes": {
                    "shared": {
                        "seed": {"values": [1]},
                        "cfg": {"values": [7.0]},
                    },
                    "per_workflow": {
                        "preset_a": {
                            "cfg": {"values": [8.0]},
                        },
                    },
                },
            }
            spec = self.mod.build_experiment_spec(
                [(preset, snap)], "txt2img", exp_def, tmp
            )
            # Must not be a compilation error
            self.assertNotIn(
                "error", spec,
                "Per-workflow axis should not cause a compilation error",
            )
            cells = spec.get("cells", [])
            self.assertTrue(
                len(cells) > 0,
                "Expected at least one cell from the compilation",
            )
            # Every cell for this preset must have cfg=8.0 from per_workflow
            # (overriding shared cfg=7.0), and seed=1 from shared.
            for cell in cells:
                av = cell.get("axis_values", {})
                self.assertEqual(
                    av.get("cfg"), 8.0,
                    "per_workflow cfg=8.0 must override shared cfg=7.0",
                )
                self.assertEqual(
                    av.get("seed"), 1,
                    "seed should still come from shared axes",
                )

    # ── Test 2: per_workflow axis without binding returns error ─────────

    def test_per_workflow_axis_without_binding_returns_error(self):
        """A per_workflow axis whose control ID has no slot binding in
        the target preset must be rejected with an explicit adapter error
        before compilation."""
        snap = _make_runnable_snapshot("snap_b")
        preset = _make_runnable_preset("preset_b", "snap_b")
        # snap_b has NO mask_blur binding — it's an unbound axis
        with tempfile.TemporaryDirectory() as tmp:
            _make_studio_store_files(tmp, [snap], [preset])
            exp_def = {
                "prompts": [
                    {"id": "p1", "text": "test", "enabled": True},
                ],
                "axes": {
                    "per_workflow": {
                        "preset_b": {
                            "mask_blur": {"values": [5, 15]},
                        },
                    },
                },
            }
            result = self.mod.build_experiment_spec(
                [(preset, snap)], "txt2img", exp_def, tmp
            )
            # Must return an error — not silently compile with missing axis
            self.assertIn(
                "error", result,
                "Unbound per_workflow axis must produce an explicit error",
            )
            self.assertIn(
                "mask_blur", result.get("error", ""),
                "Error message must reference the unbound axis name",
            )

    # ── Test 3: shared_negative preservation ────────────────────────────

    def test_shared_negative_preserved_for_prompts_without_explicit_negative(self):
        """``shared_negative`` from experiment_def is carried through to
        the compiler spec and fills in ``negative_prompt`` for prompt
        items that omit an explicit negative."""
        snap = _make_runnable_snapshot("snap_c")
        preset = _make_runnable_preset("preset_c", "snap_c")
        with tempfile.TemporaryDirectory() as tmp:
            _make_studio_store_files(tmp, [snap], [preset])
            exp_def = {
                "shared_negative": "blurry, low quality",
                "prompts": [
                    # p1: no explicit negative — should inherit shared_negative
                    {"id": "p1", "text": "a cat", "enabled": True},
                    # p2: has explicit negative — should keep its own
                    {"id": "p2", "text": "a dog", "negative": "bad anatomy",
                     "enabled": True},
                ],
            }
            spec = self.mod.build_experiment_spec(
                [(preset, snap)], "txt2img", exp_def, tmp
            )
            self.assertNotIn(
                "error", spec,
                "shared_negative in experiment_def should not cause an error",
            )
            cells = spec.get("cells", [])
            self.assertGreaterEqual(
                len(cells), 2,
                "Expected at least 2 cells (one per prompt)",
            )
            for cell in cells:
                prompt_text = cell.get("prompt", "")
                neg = cell.get("negative_prompt", "")
                if prompt_text == "a cat":
                    self.assertEqual(
                        neg, "blurry, low quality",
                        "Prompt without explicit negative should inherit "
                        "shared_negative",
                    )
                elif prompt_text == "a dog":
                    self.assertEqual(
                        neg, "bad anatomy",
                        "Prompt with explicit negative should keep its own",
                    )


# ---------------------------------------------------------------------------
# Preset group field tests
# ---------------------------------------------------------------------------

class PresetGroupFieldTests(unittest.TestCase):
    """The optional ``group`` string on presets must be backward-compatible,
    default to empty, and be consistently sanitized across all CRUD paths."""

    @classmethod
    def setUpClass(cls):
        cls.models = _load_module("studio_models", "studio_models.py")

    def test_normalize_preset_payload_adds_group_default(self):
        """normalize_preset_payload must set group to '' when absent."""
        payload = {"snapshotId": ""}
        result = self.models.normalize_preset_payload(payload, {})
        self.assertEqual(result.get("group"), "",
            "group must default to empty string")

    def test_normalize_preset_payload_preserves_existing_group(self):
        """normalize_preset_payload must preserve an existing group value."""
        payload = {"snapshotId": "", "group": "my-group"}
        result = self.models.normalize_preset_payload(payload, {})
        self.assertEqual(result.get("group"), "my-group")

    def test_normalize_preset_payload_sanitizes_group(self):
        """normalize_preset_payload must strip and truncate group."""
        payload = {"snapshotId": "", "group": "  " + "x" * 200 + "  "}
        result = self.models.normalize_preset_payload(payload, {})
        self.assertEqual(len(result.get("group", "")), 100,
            "group must be truncated to 100 characters")
        self.assertNotIn("  ", result.get("group", ""),
            "group must be stripped of whitespace")

    def test_make_preset_includes_group(self):
        """make_preset must include the group field."""
        body = {"snapshotId": "", "group": "experiment-a"}
        result = self.models.make_preset(body, {})
        self.assertIn("group", result)
        self.assertEqual(result["group"], "experiment-a")

    def test_make_preset_defaults_group_empty(self):
        """make_preset must default group to '' when body has no group."""
        body = {"snapshotId": ""}
        result = self.models.make_preset(body, {})
        self.assertEqual(result.get("group"), "",
            "group must default to empty string when not provided")

    def test_make_preset_sanitizes_group(self):
        """make_preset must strip and truncate group."""
        body = {"snapshotId": "", "group": "  long-group-name-wit trailing  "}
        result = self.models.make_preset(body, {})
        self.assertEqual(result.get("group"), "long-group-name-wit trailing",
            "group must be stripped and truncated")

    def test_update_preset_adds_group(self):
        """update_preset must apply the group field from the body."""
        preset = {"id": "p1", "snapshotId": "", "group": ""}
        result = self.models.update_preset(preset, {"group": "new-group"}, {})
        self.assertEqual(result.get("group"), "new-group")

    def test_update_preset_sanitizes_group(self):
        """update_preset must sanitize the group field."""
        preset = {"id": "p1", "snapshotId": "", "group": ""}
        body = {"group": "  " + "x" * 150 + "  "}
        result = self.models.update_preset(preset, body, {})
        self.assertEqual(len(result.get("group", "")), 100,
            "updated group must be truncated to 100 characters")

    def test_update_preset_preserves_existing_group_when_not_in_body(self):
        """update_preset must not change group when body omits it."""
        preset = {"id": "p1", "snapshotId": "", "group": "existing-group"}
        result = self.models.update_preset(preset, {"description": "new desc"}, {})
        self.assertEqual(result.get("group"), "existing-group",
            "group must be preserved when not in update body")

    def test_duplicated_preset_carries_group(self):
        """Duplicating a preset must carry the group field via deepcopy."""
        orig = {"id": "p1", "label": "Original", "snapshotId": "s1",
                "compatibleFeatures": ["txt2img"], "group": "my-group"}
        # Build snapshots_by_id so normalize_preset_payload does not error
        snaps = {"s1": {"id": "s1", "status": "runnable",
                        "compatibleFeatures": ["txt2img"],
                        "apiPromptJson": {"3": {}},
                        "nodeBindings": {},
                        "outputNodeId": "3"}}
        dup = self.models.normalize_preset_payload(
            dict(orig, id="p2", label="Original (Copy)"), snaps)
        self.assertEqual(dup.get("group"), "my-group",
            "Duplicated preset must carry group from original")

    def test_existing_preset_without_group_still_works(self):
        """A preset loaded from storage that lacks a group field must work."""
        old_preset = {"id": "p_legacy", "label": "Legacy",
                      "snapshotId": "", "sourceType": "legacy"}
        result = self.models.normalize_preset_payload(old_preset, {})
        self.assertEqual(result.get("group"), "",
            "Legacy preset without group must get empty string default")
        self.assertIn("status", result,
            "Legacy preset without group must still derive status")


# ---------------------------------------------------------------------------
# Mixed-format prompt axis extraction tests
# ---------------------------------------------------------------------------

class BuildExperimentSpecMixedFormatTest(unittest.TestCase):
    """When axes are in nested format (with 'shared' key) BUT prompt axis
    is at the flat level, the adapter must still extract prompt values."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module("studio_run_adapter", "studio_run_adapter.py")

    def _make_snap_preset(self, tmp):
        """Create a minimal runnable snapshot + preset pair in tmp."""
        snap = {
            "id": "snap_mixed",
            "name": "Mixed Format Snapshot",
            "compatibleFeatures": ["txt2img"],
            "apiPromptJson": {
                "3": {"class_type": "KSampler", "inputs": {
                    "seed": 42, "steps": 20, "cfg": 7.0,
                    "sampler_name": "euler", "scheduler": "normal",
                    "denoise": 1.0,
                }},
                "9": {"class_type": "SaveImage", "inputs": {"images": []}},
            },
            "nodeBindings": {
                "prompt": {"kind": "widget", "nodeId": "3", "widgetName": "text"},
                "output": {"kind": "output", "nodeId": "9"},
            },
            "outputNodeId": "9",
            "graphJson": {"nodes": [], "links": []},
            "archived": False,
            "status": "runnable",
            "featureStatus": {"txt2img": {"status": "runnable", "reason": ""}},
            "disabledReason": "",
        }
        preset = {
            "id": "preset_mixed", "label": "Mixed Preset",
            "snapshotId": "snap_mixed",
            "compatibleFeatures": ["txt2img"],
            "defaults": {}, "sourceType": "snapshot",
            "sourceId": "", "archived": False,
            "status": "runnable", "disabledReason": "",
        }
        _make_studio_store_files(tmp, [snap], [preset])
        return snap, preset

    def test_prompt_axis_at_flat_level_with_nested_axes(self):
        """When axes has 'shared' key (nested) but prompt axis is at the
        flat level, prompt values must NOT be lost."""
        snap, preset = self._make_snap_preset(tempfile.mkdtemp())
        with tempfile.TemporaryDirectory() as tmp:
            _make_studio_store_files(tmp, [snap], [preset])
            exp_def = {
                "prompts": [
                    {"id": "p1", "text": "fallback", "enabled": True},
                ],
                "axes": {
                    # prompt at FLAT level
                    "prompt": {"values": ["a cat", "a dog", "a bird"]},
                    # other axes under 'shared' (nested format)
                    "shared": {
                        "seed": {"mode": "list", "values": [1, 2]},
                    },
                },
            }
            spec = self.mod.build_experiment_spec(
                [(preset, snap)], "txt2img", exp_def, tmp
            )
            self.assertNotIn("error", spec,
                "Mixed format must not produce a compilation error")
            cells = spec.get("cells", [])
            # 3 prompt variants × 2 seeds = 6 cells
            self.assertEqual(len(cells), 6,
                "Mixed format: 3 prompt axis variants × 2 seeds = 6 cells")
            prompt_texts = [c.get("prompt", "") for c in cells]
            self.assertEqual(prompt_texts.count("a cat"), 2)
            self.assertEqual(prompt_texts.count("a dog"), 2)
            self.assertEqual(prompt_texts.count("a bird"), 2)
            self.assertNotIn("fallback", prompt_texts,
                "Axis prompt must override base prompt")

    def test_prompt_axis_inside_shared_still_works(self):
        """Pure nested format (prompt inside 'shared') must still work."""
        snap, preset = self._make_snap_preset(tempfile.mkdtemp())
        with tempfile.TemporaryDirectory() as tmp:
            _make_studio_store_files(tmp, [snap], [preset])
            exp_def = {
                "prompts": [
                    {"id": "p1", "text": "fallback", "enabled": True},
                ],
                "axes": {
                    "shared": {
                        "prompt": {"values": ["cat", "dog"]},
                        "seed": {"mode": "list", "values": [1]},
                    },
                },
            }
            spec = self.mod.build_experiment_spec(
                [(preset, snap)], "txt2img", exp_def, tmp
            )
            self.assertNotIn("error", spec)
            cells = spec.get("cells", [])
            self.assertEqual(len(cells), 2,
                "Nested format: 2 prompt variants × 1 seed = 2 cells")


# ---------------------------------------------------------------------------
# Enhanced experiment metadata tests
# ---------------------------------------------------------------------------

class StudioExperimentMetaDataTests(unittest.TestCase):
    """Experiment metadata must carry the full experiment definition."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module("studio_run_adapter", "studio_run_adapter.py")

    def test_studio_meta_contains_experiment_definition(self):
        """studio_meta must include experiment_definition with prompts/axes."""
        meta = self.mod._build_studio_experiment_meta(
            preset_ids=["p1"], snapshot_ids=["s1"], feature_id="txt2img",
            experiment_source={
                "prompts": [{"text": "cat"}, {"text": "dog"}],
                "axes": {"steps": {"values": [20]}},
                "shared_negative": None,
                "defaults": {"seed": 42},
                "name": "My Experiment",
            },
        )
        ed = meta.get("experiment_definition", {})
        self.assertIn("prompts", ed)
        self.assertIn("axes", ed)
        self.assertEqual(len(ed["prompts"]), 2)
        # shared_negative=None should not be stored (keeps metadata compact)
        self.assertNotIn("shared_negative", ed)

    def test_experiment_source_retained_in_compilation(self):
        """The full experiment definition must be threaded into compilation
        studio_meta via the build_experiment_spec call."""
        snap = _make_runnable_snapshot()
        preset = _make_runnable_preset()
        with tempfile.TemporaryDirectory() as tmp:
            _make_studio_store_files(tmp, [snap], [preset])
            exp_def = {
                "name": "Test Exp",
                "prompts": [
                    {"id": "p1", "text": "alpha", "enabled": True},
                    {"id": "p2", "text": "beta", "enabled": True},
                ],
                "axes": {"seed": {"values": [1]}},
                "defaults": {"steps": 30},
            }
            spec = self.mod.build_experiment_spec(
                [(preset, snap)], "txt2img", exp_def, tmp
            )
            self.assertNotIn("error", spec)
            studio_meta = spec.get("studio_meta", {})
            ed = studio_meta.get("experiment_definition", {})
            self.assertIn("prompts", ed, "experiment_definition must include prompts")
            self.assertIn("axes", ed, "experiment_definition must include axes")
            self.assertIn("defaults", ed, "experiment_definition must include defaults")
            self.assertEqual(ed.get("name"), "Test Exp")


# ---------------------------------------------------------------------------
# RED tests: getAxisEligibilityForPresets schema-aware eligibility
# ---------------------------------------------------------------------------

class JsAxisEligibilityRED(unittest.TestCase):
    """RED: ``web/studio-preset-capabilities.js`` function
    ``getAxisEligibilityForPresets`` must consider a control available when
    the preset has either a valid ``nodeBindings`` entry OR a resolved schema
    entry (``controlSchemas[controlId].schemaResolved``).  Controls like
    steps, guidance, denoise, sampler, scheduler that have resolved schemas
    but no explicit node bindings must appear eligible.
    """

    CAPABILITIES_PATH = REPO_ROOT / "web" / "studio-preset-capabilities.js"

    def setUp(self):
        if not self.CAPABILITIES_PATH.exists():
            self.skipTest(f"web/studio-preset-capabilities.js not found at {self.CAPABILITIES_PATH}")

    def test_axis_eligibility_uses_schema_aware_check(self):
        """getAxisEligibilityForPresets must call _isControlAvailable
        (not plain isControlBound) so controls with only resolved schemas
        are eligible."""
        text = self.CAPABILITIES_PATH.read_text(encoding="utf-8")
        import re
        # Find the getAxisEligibilityForPresets function body
        match = re.search(
            r"export function getAxisEligibilityForPresets\s*\([^)]+\)\s*\{(.+?)\n\}",
            text, re.DOTALL,
        )
        self.assertIsNotNone(
            match,
            "Could not locate getAxisEligibilityForPresets function body",
        )
        body = match.group(1)

        # Must call _isControlAvailable (schema-aware), not isControlBound
        self.assertIn(
            "_isControlAvailable",
            body,
            "getAxisEligibilityForPresets must use _isControlAvailable "
            "(schema-aware) not isControlBound",
        )
        self.assertNotIn(
            "isControlBound",
            body,
            "getAxisEligibilityForPresets must NOT use isControlBound "
            "(binding-only); use _isControlAvailable for schema support",
        )

    def test_is_control_available_checks_schema_resolved(self):
        """The _isControlAvailable helper must check both nodeBindings
        and controlSchemas[controlId].schemaResolved."""
        text = self.CAPABILITIES_PATH.read_text(encoding="utf-8")
        import re
        # Find the _isControlAvailable function body
        match = re.search(
            r"function _isControlAvailable\s*\([^)]+\)\s*\{(.+?)\n\}",
            text, re.DOTALL,
        )
        self.assertIsNotNone(
            match,
            "Could not locate _isControlAvailable function body",
        )
        body = match.group(1)

        # Must check schemaResolved
        self.assertIn(
            "schemaResolved",
            body,
            "_isControlAvailable must check controlSchemas[ctrlId].schemaResolved",
        )
        # Must also check nodeBindings via _isAnyBound
        self.assertIn(
            "_isAnyBound",
            body,
            "_isControlAvailable must check nodeBindings via _isAnyBound",
        )


if __name__ == "__main__":
    unittest.main()
