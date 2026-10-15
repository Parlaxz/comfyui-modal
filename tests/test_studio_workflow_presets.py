"""Phase 12 tests: version-scoped WorkflowPreset domain.

Covers: CRUD, version binding, whole-state update (no merge), duplicate,
delete, copy-forward success + fail-closed stale binding, image-key
rejection, 64 KiB cap, 0/false/"" preservation, validation metadata,
export/import round-trip with new ids and untouched graph hash, workflow
cascade delete, route registration + thin-handler round trip, and the
manifest v1 preset record contract (obsolete fields rejected).

All tests are lightweight (tmp dirs, canned graphs, no resolver/network).
"""

from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.fast_unit

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from studio_domain import (
    PresetNotFoundError,
    WorkflowDomainService,
    WorkflowDomainValidationError,
    WorkflowVersionNotFoundError,
    compute_mapping_fingerprint,
    derive_mapping_candidates,
    normalize_studio_state,
)
from studio_domain.preset_state import STUDIO_STATE_SCHEMA_VERSION


# ── fixtures ───────────────────────────────────────────────────────────────


def make_capture(prompt_nodes: dict, graph_json=None) -> dict:
    return {
        "graph_json": graph_json or {"id": "g1", "nodes": []},
        "api_prompt_json": {"workflow": {}, "output": prompt_nodes},
    }


def txt2img_prompt(seed: int = 0, steps: int = 20) -> dict:
    return {
        "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "hello world", "clip": ["4", 0]}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "negative", "clip": ["4", 0]}},
        "3": {"class_type": "KSampler", "inputs": {
            "model": ["4", 0], "seed": seed, "steps": steps, "cfg": 7.0,
            "sampler_name": "euler", "scheduler": "normal",
            "positive": ["1", 0], "negative": ["2", 0], "latent_image": ["5", 0],
            "denoise": 1.0}},
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "krea_model.safetensors"}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
        "6": {"class_type": "SaveImage", "inputs": {"images": ["3", 0]}},
    }


def make_state(**overrides: Any) -> dict:
    state = {
        "schema_version": 1,
        "core": {
            "positive_prompt": "a cat",
            "negative_prompt": "blurry",
            "controls": {"seed": 7, "steps": 20},
            "activeMode": "t2i",
            "activeSubtool": "",
            "skipTextGenerate": False,
        },
        "styles": {"setId": "set-a", "selectedId": "sel-1",
                   "basePrompt": "a cat"},
        "layout": {
            "high_level_description": "portrait",
            "background": "studio",
            "style_mode": "photo",
            "aesthetics": "",
            "lighting": "soft",
            "photo": "portrait",
            "medium": "digital",
            "art_style": "",
            "color_palette": "warm",
            "width": 512,
            "height": 768,
            "bgBrightness": 0.5,
            "boxes": [{"id": "b1", "type": "subject", "x": 0, "y": 0,
                       "w": 100, "h": 100, "desc": "", "text": "",
                       "color_palette": "", "nobbox": False, "locked": False}],
        },
        "methods": {
            "inpaintMethod": None,
            "inpaintOverride": None,
            "expandMethod": "outpaint",
            "expandOverride": {"workflow_id": "wf_aaa",
                               "workflow_version_id": "wv_bbb"},
            "padTop": 0,
            "padRight": 64,
            "padBottom": 0,
            "padLeft": 64,
        },
        "references": {"method": "", "override": None,
                       "cards": [{"label": "ref-1"}]},
        "guidance": {
            "engaged": True,
            "mode": "balanced",
            "mechanism": "adapter",
            "model_sha256": "a" * 64,
            "mapping_revision": "r1",
            "controller": {"checkpoint": "ctrl.safetensors",
                           "folder": "controlnet",
                           "checkpoint_sha256": ""},
            "nodes": {"loader": "11", "apply": "12", "preprocessor": "10"},
            "conditioning": {"strength": 0.8, "start": 0.0, "end": 1.0},
        },
        "sketch": {"tool": "brush", "brushSize": 8, "opacity": 1.0,
                   "hardness": 0.5, "color": "#000000", "bgColor": "#ffffff",
                   "width": 512, "height": 512},
        "post": {"recipe": {"curves": "linear", "mixer": 0, "grading": "",
                            "crop": None, "format": "png", "quality": 95,
                            "embedMetadata": True}},
        "output": {"output_format": "png", "quality": 95,
                   "webp_lossless_compression": False,
                   "auto_save_local": True, "save_folder": "outputs/studio",
                   "save_metadata_sidecar": False,
                   "preview_method": "thumbnail"},
    }
    for section, patch in overrides.items():
        if patch is None:
            state.pop(section, None)
        elif isinstance(patch, dict):
            state[section].update(patch)
        else:
            state[section] = patch
    return state


# ── service-level tests ────────────────────────────────────────────────────


class PresetServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.service = WorkflowDomainService(str(Path(self._tmp.name)))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # helpers
    def _mapped_version(self, prompt: dict | None = None,
                        entries: dict | None = None) -> dict:
        wf = self.service.create_workflow("Preset Wf")
        version = self.service.create_version_from_capture(
            wf["workflow_id"], make_capture(prompt or txt2img_prompt()))
        if entries is None:
            derived, output_id = derive_mapping_candidates(
                make_capture(prompt or txt2img_prompt()))
            entries = {r: e.to_dict() for r, e in derived.items()}
            output_id_value = output_id
        else:
            output_id_value = "6"
        self.service.set_mapping(version["workflow_version_id"],
                                 entries=entries,
                                 output_node_id=output_id_value)
        return version

    def _seed_entry(self) -> dict:
        return {"seed": {
            "semantic_role": "seed", "node_id": "3", "input_name": "seed",
            "output_name": "", "kind": "widget", "data_type": "INT",
            "enum_options": [], "minimum": 0, "maximum": 100, "step": 1,
            "required": False, "multiline": False, "control_kind": "integer",
            "display_name": "Seed"}}

    def test_01_create_get_list_version_binding(self):
        v1 = self._mapped_version()
        v2 = self._mapped_version()
        p1 = self.service.create_preset(v1["workflow_version_id"],
                                        name="  First  ",
                                        description="d",
                                        tags=["a", "b"],
                                        studio_state=make_state())
        self.assertTrue(p1["preset_id"].startswith("wp_"))
        self.assertEqual(len(p1["preset_id"]), 19)
        self.assertEqual(p1["name"], "First")  # trimmed
        self.assertEqual(p1["workflow_version_id"], v1["workflow_version_id"])
        self.assertNotIn("workflow_id", p1)  # no workflow_id field
        self.assertNotIn("is_default", p1)  # no default-preset field
        self.assertTrue(p1["mapping_fingerprint"])
        # get + list binding
        self.assertEqual(self.service.get_preset(p1["preset_id"])["preset_id"],
                         p1["preset_id"])
        self.assertEqual(
            [p["preset_id"] for p in
             self.service.list_presets(v1["workflow_version_id"])],
            [p1["preset_id"]])
        self.assertEqual(
            self.service.list_presets(v2["workflow_version_id"]), [])

    def test_02_create_rejects_unknown_version_and_missing_mapping(self):
        with self.assertRaises(WorkflowVersionNotFoundError):
            self.service.create_preset("wv_missing", name="x",
                                       studio_state=make_state())
        wf = self.service.create_workflow("Unmapped")
        version = self.service.create_version_from_capture(
            wf["workflow_id"], make_capture(txt2img_prompt()))
        with self.assertRaises(WorkflowDomainValidationError) as ctx:
            self.service.create_preset(version["workflow_version_id"],
                                       name="x",
                                       studio_state=make_state())
        self.assertIn("no mapping", str(ctx.exception))
        self.assertEqual(
            self.service.store.list_presets_for_version(
                version["workflow_version_id"]), [])

    def test_03_create_rejects_bad_metadata(self):
        version = self._mapped_version()
        with self.assertRaises(WorkflowDomainValidationError):
            self.service.create_preset(version["workflow_version_id"],
                                       name="   ",
                                       studio_state=make_state())
        with self.assertRaises(WorkflowDomainValidationError):
            self.service.create_preset(
                version["workflow_version_id"], name="x",
                tags=["ok"] * 21, studio_state=make_state())
        with self.assertRaises(WorkflowDomainValidationError):
            self.service.create_preset(
                version["workflow_version_id"], name="x",
                tags=["t" * 81], studio_state=make_state())
        self.assertEqual(
            self.service.list_presets(version["workflow_version_id"]), [])

    def test_04_whole_state_update_replaces_without_merge(self):
        version = self._mapped_version()
        preset = self.service.create_preset(
            version["workflow_version_id"], name="Up",
            studio_state=make_state())
        new_state = make_state()
        new_state["core"]["positive_prompt"] = "a dog"
        new_state["styles"]["setId"] = "set-b"
        del new_state["layout"]["boxes"]  # absent stays absent (no merge)
        updated = self.service.update_preset(
            preset["preset_id"],
            {"name": "Up2", "studio_state": new_state})
        self.assertEqual(updated["studio_state"], normalize_studio_state(new_state))
        self.assertNotIn("boxes", updated["studio_state"]["layout"])
        self.assertEqual(updated["name"], "Up2")
        self.assertEqual(updated["created_at"], preset["created_at"])
        # version binding + fingerprint are immutable here
        with self.assertRaises(WorkflowDomainValidationError):
            self.service.update_preset(
                preset["preset_id"], {"workflow_version_id": "wv_other"})
        with self.assertRaises(WorkflowDomainValidationError):
            self.service.update_preset(
                preset["preset_id"], {"mapping_fingerprint": "x" * 64})
        # failed update writes nothing
        bad = make_state()
        bad["core"] = {"positive_prompt": "x"}  # incomplete section
        with self.assertRaises(WorkflowDomainValidationError):
            self.service.update_preset(preset["preset_id"], {"studio_state": bad})
        self.assertEqual(
            self.service.get_preset(preset["preset_id"])["studio_state"],
            updated["studio_state"])

    def test_05_delete_and_unknown_ids(self):
        version = self._mapped_version()
        preset = self.service.create_preset(
            version["workflow_version_id"], name="Del",
            studio_state=make_state())
        self.service.delete_preset(preset["preset_id"])
        with self.assertRaises(PresetNotFoundError):
            self.service.get_preset(preset["preset_id"])
        with self.assertRaises(PresetNotFoundError):
            self.service.delete_preset(preset["preset_id"])
        with self.assertRaises(PresetNotFoundError):
            self.service.update_preset(preset["preset_id"], {"name": "z"})
        with self.assertRaises(PresetNotFoundError):
            self.service.duplicate_preset(preset["preset_id"])
        with self.assertRaises(PresetNotFoundError):
            self.service.copy_preset_to_version(
                preset["preset_id"], version["workflow_version_id"])
        self.assertEqual(
            self.service.list_presets(version["workflow_version_id"]), [])

    def test_06_duplicate_same_version_new_id(self):
        version = self._mapped_version()
        preset = self.service.create_preset(
            version["workflow_version_id"], name="Orig",
            studio_state=make_state())
        dup = self.service.duplicate_preset(preset["preset_id"])
        self.assertNotEqual(dup["preset_id"], preset["preset_id"])
        self.assertEqual(dup["workflow_version_id"],
                         preset["workflow_version_id"])
        self.assertEqual(dup["studio_state"], preset["studio_state"])
        self.assertEqual(dup["mapping_fingerprint"],
                         preset["mapping_fingerprint"])
        self.assertEqual(len(self.service.list_presets(
            version["workflow_version_id"])), 2)
        renamed = self.service.duplicate_preset(preset["preset_id"],
                                                name="Renamed")
        self.assertEqual(renamed["name"], "Renamed")

    def test_07_copy_forward_success_and_stale_fail_closed(self):
        version = self._mapped_version()
        preset = self.service.create_preset(
            version["workflow_version_id"], name="Fwd",
            studio_state=make_state())
        # Same-graph mapping revision: copy succeeds, fingerprint carried.
        derived, _ = derive_mapping_candidates(
            make_capture(txt2img_prompt()))
        revision = self.service.create_mapping_revision(
            version["workflow_version_id"],
            entries={r: e.to_dict() for r, e in derived.items()},
            output_node_id="6")
        fwd = self.service.copy_preset_to_version(
            preset["preset_id"], revision["workflow_version_id"])
        self.assertNotEqual(fwd["preset_id"], preset["preset_id"])
        self.assertEqual(fwd["workflow_version_id"],
                         revision["workflow_version_id"])
        self.assertEqual(fwd["studio_state"], preset["studio_state"])
        self.assertEqual(fwd["mapping_fingerprint"],
                         compute_mapping_fingerprint(
                             self.service.store.get_mapping_for_version(
                                 revision["workflow_version_id"])))
        # Narrow target mapping (seed only): steps control is stale.
        wf = self.service.create_workflow("Narrow")
        narrow = self.service.create_version_from_capture(
            wf["workflow_id"], make_capture(txt2img_prompt()))
        self.service.set_mapping(narrow["workflow_version_id"],
                                 entries=self._seed_entry(),
                                 output_node_id="6")
        with self.assertRaises(WorkflowDomainValidationError) as ctx:
            self.service.copy_preset_to_version(
                preset["preset_id"], narrow["workflow_version_id"])
        self.assertIn("stale binding", str(ctx.exception))
        self.assertEqual(
            self.service.list_presets(narrow["workflow_version_id"]), [])
        with self.assertRaises(WorkflowVersionNotFoundError):
            self.service.copy_preset_to_version(preset["preset_id"], "wv_nope")

    def test_08_image_keys_rejected(self):
        bad_controls = make_state()
        bad_controls["core"]["controls"] = {"reference_files": "x"}
        with self.assertRaises(WorkflowDomainValidationError) as ctx:
            normalize_studio_state(bad_controls)
        self.assertIn("image-bearing", str(ctx.exception))

        bad_value = make_state()
        bad_value["core"]["positive_prompt"] = "data:image/png;base64,AAAA"
        with self.assertRaises(WorkflowDomainValidationError):
            normalize_studio_state(bad_value)

        bad_url = make_state()
        bad_url["output"]["image_url"] = "https://example.invalid/a.png"
        with self.assertRaises(WorkflowDomainValidationError) as ctx2:
            normalize_studio_state(bad_url)
        self.assertIn("image-bearing", str(ctx2.exception))

        bad_asset_role = make_state()
        bad_asset_role["core"]["controls"] = {"mask": 1}
        with self.assertRaises(WorkflowDomainValidationError):
            normalize_studio_state(bad_asset_role)

        bad_schema = make_state()
        bad_schema["schema_version"] = 2
        with self.assertRaises(WorkflowDomainValidationError):
            normalize_studio_state(bad_schema)

        bad_section = make_state()
        bad_section["bogus"] = {}
        with self.assertRaises(WorkflowDomainValidationError):
            normalize_studio_state(bad_section)

        bad_field = make_state()
        bad_field["core"]["extra"] = 1
        with self.assertRaises(WorkflowDomainValidationError):
            normalize_studio_state(bad_field)

    def test_09_caps_and_scalar_preservation(self):
        self.assertEqual(STUDIO_STATE_SCHEMA_VERSION, 1)
        big = make_state()
        big["core"]["positive_prompt"] = "x" * (64 * 1024 + 1)
        with self.assertRaises(WorkflowDomainValidationError) as ctx:
            normalize_studio_state(big)
        self.assertIn("65536", str(ctx.exception))

        long_str = make_state()
        long_str["core"]["negative_prompt"] = "y" * (8 * 1024 + 1)
        with self.assertRaises(WorkflowDomainValidationError):
            normalize_studio_state(long_str)

        many = make_state()
        many["references"]["cards"] = [{"label": f"c{i}"} for i in range(65)]
        with self.assertRaises(WorkflowDomainValidationError):
            normalize_studio_state(many)

        # 0 / False / "" survive normalization untouched.
        kept = make_state()
        kept["core"]["controls"] = {"seed": 0, "steps": 0}
        kept["core"]["positive_prompt"] = ""
        kept["core"]["skipTextGenerate"] = False
        kept["methods"]["padTop"] = 0
        out = normalize_studio_state(kept)
        self.assertEqual(out["core"]["controls"], {"seed": 0, "steps": 0})
        self.assertEqual(out["core"]["positive_prompt"], "")
        self.assertIs(out["core"]["skipTextGenerate"], False)
        self.assertEqual(out["methods"]["padTop"], 0)

    def test_10_cascade_on_workflow_delete(self):
        version = self._mapped_version()
        self.service.create_preset(version["workflow_version_id"], name="C",
                                   studio_state=make_state())
        wf_id = self.service.store.get_version(
            version["workflow_version_id"])["workflow_id"]
        self.service.delete_workflow(wf_id)
        self.assertEqual(self.service.store.list_presets(), [])

    def test_11_export_import_round_trip(self):
        from portability_service import PortabilityService
        version = self._mapped_version()
        graph_hash_before = self.service.store.get_version(
            version["workflow_version_id"])["graph_hash"]
        preset = self.service.create_preset(
            version["workflow_version_id"], name="Ship",
            tags=["t"], studio_state=make_state())
        portability = PortabilityService(self.service)
        exported = portability.export_manifest(version["workflow_version_id"])
        manifest = exported["manifest"]
        self.assertEqual(len(manifest["presets"]), 1)
        self.assertEqual(manifest["presets"][0]["preset_id"],
                         preset["preset_id"])
        committed = portability.commit_import(manifest)
        self.assertEqual(committed["preset_count"], 1)
        new_id = committed["preset_ids"][0]
        self.assertNotEqual(new_id, preset["preset_id"])
        self.assertTrue(new_id.startswith("wp_"))
        stored = self.service.get_preset(new_id)
        self.assertEqual(stored["workflow_version_id"],
                         committed["workflow_version_id"])
        self.assertEqual(stored["studio_state"], preset["studio_state"])
        self.assertEqual(stored["name"], "Ship")
        # Graph JSON/hash untouched by preset handling.
        new_version = self.service.store.get_version(
            committed["workflow_version_id"])
        old_version = self.service.store.get_version(
            version["workflow_version_id"])
        self.assertEqual(new_version["graph_hash"], graph_hash_before)
        self.assertEqual(new_version["graph_json"], old_version["graph_json"])
        self.assertEqual(new_version["api_prompt_json"],
                         old_version["api_prompt_json"])

    def test_12_import_rejects_bad_preset_with_zero_writes(self):
        from portability_service import PortabilityService
        version = self._mapped_version()
        portability = PortabilityService(self.service)
        exported = portability.export_manifest(version["workflow_version_id"])
        manifest = copy.deepcopy(exported["manifest"])
        manifest["presets"] = [{
            "preset_id": "wp_" + "0" * 16,
            "workflow_version_id": manifest["version"]["workflow_version_id"],
            "name": "Bad",
            "studio_state": {"schema_version": 1},  # sections missing
        }]
        before = self.service.store.snapshot_all()
        with self.assertRaises(Exception):
            portability.commit_import(manifest)
        self.assertEqual(self.service.store.snapshot_all(), before)


# ── manifest contract tests ────────────────────────────────────────────────


class PresetManifestContractTests(unittest.TestCase):
    def _record(self, **overrides: Any) -> dict:
        rec = {
            "preset_id": "wp_0011223344556677",
            "workflow_version_id": "wv_fedcba9876543210",
            "name": "Default Quality",
            "description": "Quality preset",
            "tags": ["quality"],
            "studio_state": make_state(),
            "mapping_fingerprint": "f" * 64,
            "created_at": "2026-08-14T00:00:00+00:00",
            "updated_at": "2026-08-14T00:00:00+00:00",
        }
        rec.update(overrides)
        return rec

    def _manifest(self, presets: list) -> dict:
        import studio_workflow_manifest as m
        graph = {"nodes": [{"id": 1}], "links": []}
        return {
            "manifest_version": 1,
            "workflow": {
                "workflow_id": "wf_0123456789abcdef",
                "version_id": "wv_fedcba9876543210",
                "graph": graph,
                "graph_hash": m.graph_hash(graph),
            },
            "version": {
                "workflow_version_id": "wv_fedcba9876543210",
                "workflow_id": "wf_0123456789abcdef",
                "version_number": 1,
            },
            "mapping": {
                "mapping_id": "wm_1122334455667788",
                "workflow_version_id": "wv_fedcba9876543210",
                "entries": {},
            },
            "presets": presets,
        }

    def test_20_v1_record_validates(self):
        import studio_workflow_manifest as m
        m.validate_manifest(self._manifest([self._record()]))
        minimal = self._record()
        for key in ("description", "tags", "mapping_fingerprint",
                    "created_at", "updated_at"):
            minimal.pop(key)
        m.validate_manifest(self._manifest([minimal]))

    def test_21_obsolete_fields_rejected(self):
        import studio_workflow_manifest as m
        for obsolete in ("is_default", "favorite", "values",
                         "exposed_controls", "dropped_controls",
                         "model_choices", "lora_values",
                         "recommended_values", "workflow_id"):
            rec = self._record()
            rec[obsolete] = True if obsolete in ("is_default", "favorite") else (
                {} if obsolete in ("values", "model_choices", "lora_values",
                                   "recommended_values") else (
                    [] if obsolete in ("exposed_controls",
                                       "dropped_controls") else "wf_x"))
            with self.assertRaises(m.ManifestValidationError,
                                   msg=obsolete):
                m.validate_manifest(self._manifest([rec]))

    def test_22_id_shape_duplicates_and_version_linkage(self):
        import studio_workflow_manifest as m
        rec = self._record()
        rec["preset_id"] = "wpres_0011223344556677"  # old shape
        with self.assertRaises(m.ManifestValidationError):
            m.validate_manifest(self._manifest([rec]))
        dup = self._record()
        with self.assertRaises(m.ManifestValidationError):
            m.validate_manifest(self._manifest([self._record(), dup]))
        stray = self._record()
        stray["preset_id"] = "wp_9900000000000001"
        stray["workflow_version_id"] = "wv_0000000000000000"
        with self.assertRaises(m.ManifestValidationError):
            m.validate_manifest(self._manifest([stray]))


# ── route tests (stub server, thin handlers) ─────────────────────────────


class _StubRouteTable:
    def __init__(self) -> None:
        self._handlers: list[tuple[str, str, Any]] = []

    def get(self, path: str):
        return self._deco("GET", path)

    def post(self, path: str):
        return self._deco("POST", path)

    def patch(self, path: str):
        return self._deco("PATCH", path)

    def delete(self, path: str):
        return self._deco("DELETE", path)

    def _deco(self, method: str, path: str):
        def deco(fn):
            self._handlers.append((method, path, fn))
            return fn
        return deco


class _StubServer:
    def __init__(self) -> None:
        self.routes = _StubRouteTable()


class _MockRequest:
    def __init__(self, *, json_body: dict | None = None,
                 match_info: dict | None = None):
        self._json = json_body
        self._match_info = match_info or {}

    async def json(self) -> dict:
        if self._json is None:
            raise ValueError("no body")
        return self._json

    @property
    def query(self):
        return {}

    @property
    def match_info(self):
        return self._match_info


def _run(coro):
    return asyncio.run(coro)


def _load_routes_module():
    name = "studio_workflow_routes_preset_test"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, REPO_ROOT / "studio_workflow_routes.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class PresetRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.routes_mod = _load_routes_module()

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = str(Path(self._tmp.name))
        self.service = WorkflowDomainService(self.root)
        stub = _StubServer()
        self.routes_mod.register_workflow_routes(stub, node_dir=self.root)
        self.handlers = {(m, p): fn for m, p, fn in stub.routes._handlers}

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _call(self, method: str, path: str, **kwargs):
        handler = self.handlers.get((method, path))
        self.assertIsNotNone(handler, f"no route for {method} {path}")
        assert handler is not None
        return _run(handler(_MockRequest(**kwargs)))

    def _body(self, resp) -> dict:
        return json.loads(resp.body)

    def _mapped_version_id(self) -> str:
        wf = self.service.create_workflow("Route Wf")
        version = self.service.create_version_from_capture(
            wf["workflow_id"], make_capture(txt2img_prompt()))
        derived, output_id = derive_mapping_candidates(
            make_capture(txt2img_prompt()))
        self.service.set_mapping(
            version["workflow_version_id"],
            entries={r: e.to_dict() for r, e in derived.items()},
            output_node_id=output_id)
        return version["workflow_version_id"]

    def test_30_all_preset_routes_registered(self):
        base = "/comfymodal/studio/workflows"
        expected = [
            ("GET", f"{base}/versions/{{version_id}}/presets"),
            ("POST", f"{base}/versions/{{version_id}}/presets"),
            ("GET", f"{base}/presets/{{preset_id}}"),
            ("PATCH", f"{base}/presets/{{preset_id}}"),
            ("DELETE", f"{base}/presets/{{preset_id}}"),
            ("POST", f"{base}/presets/{{preset_id}}/duplicate"),
            ("POST", f"{base}/presets/{{preset_id}}/copy-to-version"),
        ]
        for method, path in expected:
            self.assertIn((method, path), self.handlers,
                          f"missing route {method} {path}")
        # Stale preset routes must not exist.
        for method, path in self.handlers:
            self.assertNotIn("default-preset", path)
            self.assertNotIn("copy-bulk", path)

    def test_31_route_crud_round_trip(self):
        base = "/comfymodal/studio/workflows"
        version_id = self._mapped_version_id()
        payload = {"name": "Route Preset", "tags": ["r"],
                   "studio_state": make_state()}
        resp = self._call(
            "POST", f"{base}/versions/{{version_id}}/presets",
            json_body=payload, match_info={"version_id": version_id})
        self.assertEqual(resp.status, 200, resp.body)
        preset_id = self._body(resp)["preset"]["preset_id"]

        resp = self._call("GET", f"{base}/versions/{{version_id}}/presets",
                          match_info={"version_id": version_id})
        self.assertEqual(resp.status, 200)
        self.assertEqual(
            [p["preset_id"] for p in self._body(resp)["presets"]], [preset_id])

        resp = self._call("GET", f"{base}/presets/{{preset_id}}",
                          match_info={"preset_id": preset_id})
        self.assertEqual(resp.status, 200)
        self.assertEqual(self._body(resp)["preset"]["name"], "Route Preset")

        updated_state = make_state()
        updated_state["styles"]["setId"] = "set-route"
        resp = self._call("PATCH", f"{base}/presets/{{preset_id}}",
                          json_body={"studio_state": updated_state},
                          match_info={"preset_id": preset_id})
        self.assertEqual(resp.status, 200, resp.body)
        self.assertEqual(self._body(resp)["preset"]["studio_state"]["styles"]["setId"],
                         "set-route")

        resp = self._call("POST", f"{base}/presets/{{preset_id}}/duplicate",
                          json_body={}, match_info={"preset_id": preset_id})
        self.assertEqual(resp.status, 200, resp.body)
        dup_id = self._body(resp)["preset"]["preset_id"]
        self.assertNotEqual(dup_id, preset_id)

        resp = self._call("DELETE", f"{base}/presets/{{preset_id}}",
                          match_info={"preset_id": preset_id})
        self.assertEqual(resp.status, 200)
        resp = self._call("GET", f"{base}/presets/{{preset_id}}",
                          match_info={"preset_id": preset_id})
        self.assertEqual(resp.status, 404)
        self.assertIn("message", self._body(resp))

    def test_32_route_errors_mapped(self):
        base = "/comfymodal/studio/workflows"
        resp = self._call("GET", f"{base}/presets/{{preset_id}}",
                          match_info={"preset_id": "wp_ffffffffffffffff"})
        self.assertEqual(resp.status, 404)
        resp = self._call(
            "POST", f"{base}/versions/{{version_id}}/presets",
            json_body={"name": "x", "studio_state": {"schema_version": 1}},
            match_info={"version_id": "wv_ffffffffffffffff"})
        self.assertEqual(resp.status, 404)  # unknown version, nothing written
        version_id = self._mapped_version_id()
        resp = self._call(
            "POST", f"{base}/versions/{{version_id}}/presets",
            json_body={"name": "", "studio_state": make_state()},
            match_info={"version_id": version_id})
        self.assertEqual(resp.status, 400)
        resp = self._call(
            "POST", f"{base}/presets/{{preset_id}}/copy-to-version",
            json_body={}, match_info={"preset_id": "wp_ffffffffffffffff"})
        self.assertEqual(resp.status, 404)


if __name__ == "__main__":
    unittest.main()
