"""Phase G9 backend tests: manifest Export, Import preview/commit, live
portability report, atomicity, concurrency, security.

Exercises ``portability_service.PortabilityService`` directly AND through the
registered ``studio_workflow_routes`` handlers (house _StubServer pattern).
No provider/network/GPU/live-generation anywhere.
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import portability_contract as pc
import studio_workflow_manifest as manifest_codec
from portability_service import (
    ExportRefusedError,
    ImportBlockedError,
    PortabilityService,
)
from studio_domain.services import WorkflowDomainService
from studio_workflow_routes import register_workflow_routes

STORE_FILENAMES = (
    ".studio_workflows.json",
    ".studio_workflow_versions.json",
    ".studio_workflow_mappings.json",
    ".studio_workflow_presets.json",
)

PINNED_HASH = "ab" * 32
LEAK_CANARY_LOCAL_PATH = r"C:\\canary\\models\\krea_model.safetensors"
LEAK_CANARY_INSTALL_PATH = r"C:\\canary\\custom_nodes\\leaky"


# ── HTTP harness (house pattern) ──────────────────────────────────────────


class _StubRouteTable:
    def __init__(self) -> None:
        self._handlers: list[tuple[str, str, object]] = []

    def get(self, path):
        return self._deco("GET", path)

    def post(self, path):
        return self._deco("POST", path)

    def put(self, path):
        return self._deco("PUT", path)

    def delete(self, path):
        return self._deco("DELETE", path)

    def patch(self, path):
        return self._deco("PATCH", path)

    def _deco(self, method, path):
        def deco(fn):
            self._handlers.append((method, path, fn))
            return fn

        return deco


class _StubServer:
    def __init__(self) -> None:
        self.routes = _StubRouteTable()


class _MockRequest:
    def __init__(self, *, body_bytes=None, query=None, match_info=None):
        self._body = body_bytes
        self.query = query or {}
        self.match_info = match_info or {}
        self.content_length = len(body_bytes) if body_bytes is not None else None

    async def read(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body

    async def json(self):
        return json.loads(bytes(self._body or b"{}"))


def _run(coro):
    return asyncio.run(coro)


def _handler_for(stub, method, path):
    for m, p, fn in stub.routes._handlers:
        if m == method and p == path:
            return fn
    for m, p, fn in stub.routes._handlers:
        if m != method:
            continue
        pp = p.split("/")
        aa = path.split("/")
        if len(pp) == len(aa) and all(
            x.startswith("{") or x == y for x, y in zip(pp, aa)
        ):
            return fn
    return None


# ── domain fixtures ───────────────────────────────────────────────────────


def sample_prompt(seed=7):
    return {
        "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "hello world", "clip": ["4", 0]}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "negative", "clip": ["4", 0]}},
        "3": {"class_type": "KSampler", "inputs": {
            "model": ["4", 0], "seed": seed, "steps": 20, "cfg": 7.0,
            "sampler_name": "euler", "scheduler": "normal",
            "positive": ["1", 0], "negative": ["2", 0], "latent_image": ["5", 0],
            "denoise": 1.0}},
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "krea_model.safetensors"}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
        "6": {"class_type": "SaveImage", "inputs": {"images": ["3", 0]}},
    }


def sample_graph_json():
    return {
        "id": "g-sample",
        "revision": 0,
        "last_node_id": 6,
        "last_link_id": 5,
        "nodes": [
            {"id": 4, "type": "CheckpointLoaderSimple", "pos": [0, 0], "properties": {}},
            {"id": 6, "type": "SaveImage", "pos": [100, 0], "properties": {}},
        ],
        "links": [],
        "groups": [],
        "config": {},
        "extra": {},
        "version": 0.4,
    }


def credential_prompt():
    prompt = sample_prompt()
    prompt["9"] = {"class_type": "FixtureAuthNode", "inputs": {"api_key": "placeholder-not-a-secret"}}
    return prompt


def corpus_prompt():
    return {
        "10": {"class_type": "UNETLoader", "inputs": {"unet_name": "fixture_z_unet.safetensors"}},
        "11": {"class_type": "CLIPLoader", "inputs": {"clip_name": "fixture_qwen_clip.safetensors", "type": "flux"}},
        "12": {"class_type": "VAELoader", "inputs": {"vae_name": "fixture_ae_vae.safetensors"}},
        "13": {"class_type": "FixturePatchLoader", "inputs": {"name": "fixture_patch_model.safetensors"}},
        "14": {"class_type": "FixtureKJLikeNode", "inputs": {"image": "fixture_in.png"}},
        "15": {"class_type": "FixtureRGLikeNode", "inputs": {"mode": "clean"}},
        "16": {"class_type": "FixtureFallbackAttributionNode", "inputs": {"value": 1}},
        "17": {"class_type": "SaveImage", "inputs": {"images": ["14", 0]}},
    }


def corpus_graph_json():
    return {
        "id": "g-corpus",
        "nodes": [
            {"id": 13, "type": "FixturePatchLoader", "properties": {"aux_id": "fixture-author/comfyui-fixture-patchloader"}},
            {"id": 17, "type": "SaveImage", "properties": {}},
        ],
        "links": [],
        "groups": [],
        "config": {},
        "extra": {},
        "definitions": {"subgraphs": [{"id": "sg:1", "name": "fixture-subgraph"}]},
        "version": 0.4,
    }


MAPPING_BODY = {
    "entries": {
        "positive_prompt": {
            "semantic_role": "positive_prompt", "node_id": "1", "input_name": "text",
            "output_name": "", "kind": "node_input", "data_type": "STRING",
            "enum_options": [], "minimum": None, "maximum": None, "step": None,
            "required": True, "multiline": True, "control_kind": "multiline",
            "display_name": "Positive Prompt",
        },
        "seed": {
            "semantic_role": "seed", "node_id": "3", "input_name": "seed",
            "output_name": "", "kind": "widget", "data_type": "INT",
            "enum_options": [], "minimum": 0, "maximum": 4294967295, "step": 1,
            "required": False, "multiline": False, "control_kind": "integer",
            "display_name": "Seed",
        },
    },
    "output_node_id": "6",
}


class CoreOnlyResolver:
    """All classes are ComfyUI core; one pinned installed model row."""

    def __init__(self, model_hash=PINNED_HASH):
        self.model_hash = model_hash

    def resolve_version(self, version):
        dm = version.get("dependency_metadata") or {}
        classes = sorted(dm.get("node_classes") or [])
        rows = [{
            "name": "ComfyUI core", "state": "installed", "install_path": "",
            "installed_commit": "", "required_revision": "",
            "repository_url": "", "classes": classes,
        }]
        models = []
        seen = set()
        for role, files in (dm.get("model_stack") or {}).items():
            for fn in files:
                if fn in seen:
                    continue
                seen.add(fn)
                models.append({
                    "key": "%s|%s" % (role, fn), "role": role, "filename": fn,
                    "state": "installed", "model_id": "ml_pinned", "folder": "checkpoints",
                    "hash": self.model_hash, "size": 4321,
                    "local_path": LEAK_CANARY_LOCAL_PATH,
                    "source_urls": ["https://example.invalid/model"],
                    "installed": True,
                })
        return {"models": models, "custom_nodes": rows}

    def reasons_for(self, version):
        return []


class CorpusResolver:
    """Prepared G8 current_corpus_shape evidence (deterministic)."""

    def resolve_version(self, version):
        custom = [
            {"name": "comfyui-fixture-kjlike", "state": "installed", "install_path": "",
             "installed_commit": "9999000011112222333344445555666677778888",
             "required_revision": "",
             "repository_url": "https://example.invalid/git/comfyui-fixture-kjlike",
             "classes": ["FixtureKJLikeNode"], "provenance": "exact"},
            {"name": "comfyui-fixture-rglike", "state": "installed", "install_path": "",
             "installed_commit": "",
             "required_revision": "v1.0.2605082257-declared",
             "repository_url": "https://example.invalid/git/comfyui-fixture-rglike",
             "classes": ["FixtureRGLikeNode"], "provenance": "declared"},
            {"name": "comfyui-fixture-fallback", "state": "installed", "install_path": "",
             "installed_commit": "aaaabbbbccccddddeeeeffff0000111122223333",
             "required_revision": "",
             "repository_url": "https://github.com/Comfy-Org/ComfyUI",
             "classes": ["FixtureFallbackAttributionNode"], "provenance": "inferred"},
            {"name": "comfyui-fixture-patchloader", "state": "installed", "install_path": "",
             "installed_commit": "11223344556677889900aabbccddeeff00112233",
             "required_revision": "",
             "repository_url": "https://example.invalid/git/comfyui-fixture-patchloader",
             "classes": ["FixturePatchLoader"], "provenance": "exact"},
            {"name": "ComfyUI core", "state": "installed", "install_path": "",
             "installed_commit": "", "required_revision": "",
             "repository_url": "",
             "classes": ["SaveImage", "UNETLoader", "CLIPLoader", "VAELoader"]},
        ]
        models = [
            {"key": "unet|fixture_z_unet.safetensors", "role": "unet",
             "filename": "fixture_z_unet.safetensors", "state": "installed",
             "model_id": "ml_1", "folder": "diffusion_models", "hash": "",
             "size": 100, "local_path": LEAK_CANARY_LOCAL_PATH,
             "source_urls": [], "installed": True},
            {"key": "clip|fixture_qwen_clip.safetensors", "role": "clip",
             "filename": "fixture_qwen_clip.safetensors", "state": "installed",
             "model_id": "ml_2", "folder": "text_encoders", "hash": "",
             "size": 100, "local_path": LEAK_CANARY_LOCAL_PATH,
             "source_urls": [], "installed": True},
            {"key": "vae|fixture_ae_vae.safetensors", "role": "vae",
             "filename": "fixture_ae_vae.safetensors", "state": "installed",
             "model_id": "ml_3", "folder": "vae", "hash": "",
             "size": 100, "local_path": LEAK_CANARY_LOCAL_PATH,
             "source_urls": [], "installed": True},
        ]
        return {"models": models, "custom_nodes": custom}

    def reasons_for(self, version):
        return []


# ── shared base ───────────────────────────────────────────────────────────


class PortabilityBackendTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = str(Path(self._tmp.name))
        self.service = WorkflowDomainService(self.root)
        self.portability = PortabilityService(
            self.service, resolver=CoreOnlyResolver()
        )
        self.stub = _StubServer()
        register_workflow_routes(
            self.stub, node_dir=self.root, resolver=CoreOnlyResolver()
        )

    def tearDown(self):
        self._tmp.cleanup()

    # -- helpers -----------------------------------------------------------

    def call(self, method, path, *, body_bytes=None, query=None, match_info=None):
        handler = _handler_for(self.stub, method, path)
        assert handler is not None, "missing route %s %s" % (method, path)
        req = _MockRequest(body_bytes=body_bytes, query=query, match_info=match_info)
        return _run(handler(req))

    @staticmethod
    def body(resp):
        payload = getattr(resp, "body", None)
        return json.loads(bytes(payload) if payload is not None else b"{}")

    def create_workflow(self, name="Sample Workflow"):
        resp = self.call(
            "POST", "/comfymodal/studio/workflows",
            body_bytes=json.dumps({"name": name}).encode(),
        )
        assert resp.status == 200, resp.body
        return self.body(resp)["workflow"]

    def capture_version(self, wf_id, prompt=None, graph_json=None):
        capture = {
            "graph_json": graph_json if graph_json is not None else sample_graph_json(),
            "api_prompt_json": {"workflow": {}, "output": prompt or sample_prompt()},
        }
        resp = self.call(
            "POST", "/comfymodal/studio/workflows/{workflow_id}/versions",
            body_bytes=json.dumps(capture).encode(),
            match_info={"workflow_id": wf_id},
        )
        assert resp.status == 200, resp.body
        return self.body(resp)["version"]

    def set_mapping(self, version_id):
        resp = self.call(
            "POST", "/comfymodal/studio/workflows/versions/{version_id}/mapping",
            body_bytes=json.dumps(MAPPING_BODY).encode(),
            match_info={"version_id": version_id},
        )
        assert resp.status == 200, resp.body
        return self.body(resp)["mapping"]

    def create_preset(self, version_id, name="Base Preset", **extra):
        body = {"name": name, "values": {"positive_prompt": "hi", "seed": 5}, **extra}
        resp = self.call(
            "POST", "/comfymodal/studio/workflows/versions/{version_id}/presets",
            body_bytes=json.dumps(body).encode(),
            match_info={"version_id": version_id},
        )
        assert resp.status == 200, resp.body
        return self.body(resp)["preset"]

    def setup_mapped_version(self, name="Sample Workflow"):
        wf = self.create_workflow(name)
        version = self.capture_version(wf["workflow_id"])
        mapping = self.set_mapping(version["workflow_version_id"])
        return wf, version, mapping

    def snapshot_stores(self):
        snap = {}
        for name in STORE_FILENAMES:
            path = Path(self.root) / name
            snap[name] = path.read_bytes() if path.exists() else None
        return snap

    def export_bytes(self, version_id, include_presets=None):
        query = {}
        if include_presets is not None:
            query["include_presets"] = "1" if include_presets else "0"
        resp = self.call(
            "GET",
            "/comfymodal/studio/workflows/versions/{version_id}/export",
            query=query,
            match_info={"version_id": version_id},
        )
        return resp


class ExportTests(PortabilityBackendTestBase):
    def test_01_include_presets_default_false(self):
        _, version, _ = self.setup_mapped_version()
        self.create_preset(version["workflow_version_id"])
        resp = self.export_bytes(version["workflow_version_id"])
        self.assertEqual(resp.status, 200)
        manifest = json.loads(resp.body)
        self.assertEqual(manifest["presets"], [])
        self.assertEqual(manifest["manifest_version"], 1)

    def test_02_include_presets_true(self):
        _, version, _ = self.setup_mapped_version()
        preset = self.create_preset(version["workflow_version_id"])
        resp = self.export_bytes(version["workflow_version_id"], include_presets=True)
        self.assertEqual(resp.status, 200)
        manifest = json.loads(resp.body)
        self.assertEqual(len(manifest["presets"]), 1)
        self.assertEqual(manifest["presets"][0]["preset_id"], preset["preset_id"])
        self.assertIn("is_default", manifest["presets"][0])

    def test_03_exact_filename_and_content_headers(self):
        wf, version, _ = self.setup_mapped_version(name="My Fancy: Workflow/Name?")
        resp = self.export_bytes(version["workflow_version_id"])
        self.assertEqual(resp.status, 200)
        expected = pc.suggest_export_filename(
            "My Fancy: Workflow/Name?",
            int(version["version_number"]),
            version["graph_hash"],
        )
        self.assertEqual(expected, "My_Fancy_Workflow_Name-v1-%s.workflow.json" % version["graph_hash"][:8])
        disposition = resp.headers.get("Content-Disposition", "")
        self.assertIn('filename="%s"' % expected, disposition)
        self.assertEqual(resp.content_type, "application/json")
        canonical = manifest_codec.canonical_bytes(json.loads(resp.body))
        self.assertEqual(resp.body, canonical)

    def test_04_version_not_found(self):
        resp = self.export_bytes("wv_missing")
        self.assertEqual(resp.status, 404)

    def test_05_export_is_read_only(self):
        _, version, _ = self.setup_mapped_version()
        self.create_preset(version["workflow_version_id"])
        before = self.snapshot_stores()
        self.export_bytes(version["workflow_version_id"], include_presets=True)
        self.assertEqual(self.snapshot_stores(), before)

    def test_06_credential_like_export_refusal(self):
        wf = self.create_workflow(name="Cred Workflow")
        version = self.capture_version(wf["workflow_id"], prompt=credential_prompt())
        self.set_mapping(version["workflow_version_id"])
        before = self.snapshot_stores()
        resp = self.export_bytes(version["workflow_version_id"])
        self.assertEqual(resp.status, 409)
        body = self.body(resp)
        self.assertEqual(body["code"], pc.ISSUE_CREDENTIAL_LIKE_VALUE_DETECTED)
        self.assertNotIn("placeholder-not-a-secret", resp.body.decode())
        self.assertEqual(self.snapshot_stores(), before)

    def test_07_no_local_install_path_leakage(self):
        _, version, _ = self.setup_mapped_version()
        resp = self.export_bytes(version["workflow_version_id"])
        manifest = json.loads(resp.body)
        text = json.dumps(manifest)
        self.assertNotIn("local_path", text)
        self.assertNotIn("install_path", text)
        self.assertNotIn(r"C:\\canary", text)

    def test_07b_unmapped_version_fails_closed(self):
        wf = self.create_workflow(name="No Mapping")
        version = self.capture_version(wf["workflow_id"])
        resp = self.export_bytes(version["workflow_version_id"])
        self.assertEqual(resp.status, 409)
        self.assertIn("mapping", self.body(resp)["message"])

    def test_07c_extraction_gap_warning_not_silently_dropped(self):
        wf = self.create_workflow(name="Gap Workflow")
        version = self.capture_version(
            wf["workflow_id"],
            prompt={
                "13": {"class_type": "ModelPatchLoader", "inputs": {"name": "patch.safetensors"}},
                "17": {"class_type": "SaveImage", "inputs": {"images": ["13", 0]}},
            },
            graph_json={"nodes": [], "links": [], "extra": {}},
        )
        self.set_mapping(version["workflow_version_id"])
        resp = self.export_bytes(version["workflow_version_id"])
        self.assertEqual(resp.status, 200)
        manifest = json.loads(resp.body)
        filenames = [m["filename"] for m in manifest["models"]]
        self.assertNotIn("patch.safetensors", filenames)
        codes = [w["code"] for w in manifest["metadata"]["export_warnings"]]
        self.assertIn(pc.ISSUE_MODEL_EXTRACTION_GAP, codes)


class ImportPreviewTests(PortabilityBackendTestBase):
    def _export_manifest_bytes(self):
        _, version, _ = self.setup_mapped_version(name="Round Trip Source")
        self.create_preset(version["workflow_version_id"])
        resp = self.export_bytes(version["workflow_version_id"], include_presets=True)
        return resp.body, version

    def test_08_valid_preview_shape(self):
        raw, _ = self._export_manifest_bytes()
        before = self.snapshot_stores()
        resp = self.call(
            "POST", "/comfymodal/studio/workflows/import-manifest",
            body_bytes=raw, query={},
        )
        self.assertEqual(resp.status, 200)
        payload = self.body(resp)
        self.assertEqual(payload["status"], "preview")
        self.assertTrue(payload["valid"])
        self.assertEqual(payload["manifest_version"], 1)
        self.assertEqual(payload["issues"], [])
        self.assertIn("ready", payload["readiness"])
        self.assertIsNotNone(payload["portability"])
        pc.validate_report(payload["portability"])
        self.assertEqual(payload["will_create"]["preset_count"], 1)
        self.assertTrue(payload["proposed_name"].endswith(" (imported)"))
        self.assertEqual(self.snapshot_stores(), before)

    def test_09_malformed_json_blocked_400(self):
        malformed = Path(__file__).parent / "fixtures" / "portability" / "raw" / "malformed_manifest.txt"
        before = self.snapshot_stores()
        resp = self.call(
            "POST", "/comfymodal/studio/workflows/import-manifest",
            body_bytes=malformed.read_bytes(), query={},
        )
        self.assertEqual(resp.status, 400)
        self.assertEqual(self.snapshot_stores(), before)

    def test_10_unknown_future_manifest_version_blocked(self):
        _, version, _ = self.setup_mapped_version()
        resp = self.export_bytes(version["workflow_version_id"])
        manifest = json.loads(resp.body)
        manifest["manifest_version"] = 2
        before = self.snapshot_stores()
        result = self.call(
            "POST", "/comfymodal/studio/workflows/import-manifest",
            body_bytes=json.dumps(manifest).encode(), query={},
        )
        self.assertEqual(result.status, 400)
        self.assertIn("unsupported manifest version", result.body.decode())
        self.assertEqual(self.snapshot_stores(), before)

    def test_11_not_ready_manifest_reports_readiness(self):
        fixture = (
            Path(__file__).parent / "fixtures" / "portability" / "manifests"
            / "model_hash_missing.manifest.json"
        )
        resp = self.call(
            "POST", "/comfymodal/studio/workflows/import-manifest",
            body_bytes=fixture.read_bytes(), query={},
        )
        self.assertEqual(resp.status, 200)
        payload = self.body(resp)
        self.assertTrue(payload["valid"])
        self.assertFalse(payload["readiness"]["ready"])

    def test_12_missing_dependencies_allowed_in_preview(self):
        _, version, _ = self.setup_mapped_version()
        resp = self.export_bytes(version["workflow_version_id"])
        manifest = json.loads(resp.body)
        for rec in manifest["models"]:
            rec.pop("sha256", None)
        result = self.call(
            "POST", "/comfymodal/studio/workflows/import-manifest",
            body_bytes=json.dumps(manifest).encode(), query={},
        )
        self.assertEqual(result.status, 200)
        payload = self.body(result)
        self.assertFalse(payload["readiness"]["ready"])
        self.assertIsNotNone(payload["portability"])
        summary = payload["dependency_summary"]["summary"]
        self.assertGreater(summary["attention"], 0)

    def test_13_credential_finding_reported_not_blocking(self):
        fixture = (
            Path(__file__).parent / "fixtures" / "portability" / "manifests"
            / "credential_like_value.manifest.json"
        )
        resp = self.call(
            "POST", "/comfymodal/studio/workflows/import-manifest",
            body_bytes=fixture.read_bytes(), query={},
        )
        self.assertEqual(resp.status, 200)
        payload = self.body(resp)
        joined = json.dumps(payload)
        self.assertIn(pc.ISSUE_CREDENTIAL_LIKE_VALUE_DETECTED, joined)
        self.assertNotIn("TEST_SECRET_DO_NOT_USE", joined)
        findings = payload.get("security_findings") or []
        self.assertEqual(findings[0]["code"], pc.ISSUE_CREDENTIAL_LIKE_VALUE_DETECTED)

    def test_14_duplicate_name_suggestion(self):
        self.create_workflow(name="Dup Target")
        _, version, _ = self.setup_mapped_version(name="Dup Target")
        resp = self.export_bytes(version["workflow_version_id"])
        result = self.call(
            "POST", "/comfymodal/studio/workflows/import-manifest",
            body_bytes=resp.body, query={},
        )
        payload = self.body(result)
        self.assertEqual(payload["proposed_name"], "Dup Target (imported)")
        self.assertTrue(
            any(m["name"] == "Dup Target" for m in payload["existing_name_matches"])
        )

    def test_15_preview_writes_nothing_nan_rejected_depth_guard(self):
        _, version, _ = self.setup_mapped_version()
        before = self.snapshot_stores()
        resp = self.export_bytes(version["workflow_version_id"])
        self.assertEqual(self.snapshot_stores(), before)
        nan_body = b'{"manifest_version": 1, "workflow": NaN}'
        result = self.call(
            "POST", "/comfymodal/studio/workflows/import-manifest",
            body_bytes=nan_body, query={},
        )
        self.assertEqual(result.status, 400)
        deep: dict = {"manifest_version": 1}
        cursor: dict = deep
        for _ in range(pc.MAX_JSON_DEPTH + 2):
            child: dict = {}
            cursor["child"] = child
            cursor = child
        result = self.call(
            "POST", "/comfymodal/studio/workflows/import-manifest",
            body_bytes=json.dumps(deep).encode(), query={},
        )
        self.assertEqual(result.status, 400)
        self.assertIn("depth", result.body.decode())
        self.assertEqual(self.snapshot_stores(), before)

    def test_15b_oversized_payload_413(self):
        huge = b'{"pad": "' + b"a" * (pc.MAX_IMPORT_BODY_BYTES + 1) + b'"}'
        resp = self.call(
            "POST", "/comfymodal/studio/workflows/import-manifest",
            body_bytes=huge, query={},
        )
        self.assertEqual(resp.status, 413)

    def test_15c_invalid_dry_run_value_400(self):
        resp = self.call(
            "POST", "/comfymodal/studio/workflows/import-manifest",
            body_bytes=b"{}", query={"dry_run": "yes"},
        )
        self.assertEqual(resp.status, 400)


class ImportCommitTests(PortabilityBackendTestBase):
    def _exported(self, name="Round Trip Source", presets=1):
        wf, version, _ = self.setup_mapped_version(name=name)
        for i in range(presets):
            self.create_preset(
                version["workflow_version_id"],
                name="Preset %d" % i,
                favorite=i == 0,
            )
        resp = self.export_bytes(version["workflow_version_id"], include_presets=True)
        return resp.body, wf, version

    def test_16_default_commit_imports_zero_presets(self):
        raw, _, _ = self._exported(presets=1)
        resp = self.call(
            "POST", "/comfymodal/studio/workflows/import-manifest",
            body_bytes=raw, query={"dry_run": "0"},
        )
        self.assertEqual(resp.status, 200)
        payload = self.body(resp)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["preset_ids"], [])
        presets = json.loads(
            (Path(self.root) / ".studio_workflow_presets.json").read_text()
        )
        imported = [
            p for p in presets
            if p["workflow_version_id"] == payload["workflow_version_id"]
        ]
        self.assertEqual(imported, [])

    def test_17_presets_imported_when_explicit(self):
        raw, _, _ = self._exported(presets=2)
        manifest = json.loads(raw)
        manifest["import_presets"] = True
        resp = self.call(
            "POST", "/comfymodal/studio/workflows/import-manifest",
            body_bytes=json.dumps(manifest).encode(), query={"dry_run": "0"},
        )
        self.assertEqual(resp.status, 200)
        payload = self.body(resp)
        self.assertEqual(len(payload["preset_ids"]), 2)
        presets = json.loads(
            (Path(self.root) / ".studio_workflow_presets.json").read_text()
        )
        imported = [
            p for p in presets
            if p["workflow_version_id"] == payload["workflow_version_id"]
        ]
        self.assertEqual(len(imported), 2)
        for preset in imported:
            self.assertTrue(str(preset["preset_id"]).startswith("wpres_"))

    def test_18_default_preset_not_applied_unless_explicit(self):
        raw, source_wf, _ = self._exported(presets=1)
        manifest = json.loads(raw)
        self.service.set_default_preset(
            source_wf["workflow_id"], manifest["presets"][0]["preset_id"]
        )
        source_version_id = _reexport_version_id(self, source_wf)
        refreshed = self.export_bytes(source_version_id, include_presets=True)
        manifest = json.loads(refreshed.body)
        self.assertIs(manifest["presets"][0]["is_default"], True)
        manifest["import_presets"] = True
        resp = self.call(
            "POST", "/comfymodal/studio/workflows/import-manifest",
            body_bytes=json.dumps(manifest).encode(), query={"dry_run": "0"},
        )
        payload = self.body(resp)
        self.assertEqual(resp.status, 200, resp.body)
        self.assertIsNone(payload["applied_default_preset_id"])
        wf_record = json.loads(
            (Path(self.root) / ".studio_workflows.json").read_text()
        )[-1]
        self.assertEqual(wf_record["default_preset_id"], "")

    def test_19_default_applied_when_explicit(self):
        raw, source_wf, _ = self._exported(presets=1)
        manifest = json.loads(raw)
        self.service.set_default_preset(
            source_wf["workflow_id"], manifest["presets"][0]["preset_id"]
        )
        refreshed = self.export_bytes(
            _reexport_version_id(self, source_wf), include_presets=True
        )
        manifest = json.loads(refreshed.body)
        manifest["import_presets"] = True
        manifest["apply_default_preset"] = True
        resp = self.call(
            "POST", "/comfymodal/studio/workflows/import-manifest",
            body_bytes=json.dumps(manifest).encode(), query={"dry_run": "0"},
        )
        payload = self.body(resp)
        self.assertEqual(resp.status, 200, resp.body)
        self.assertIsNotNone(payload["applied_default_preset_id"])
        wf_record = json.loads(
            (Path(self.root) / ".studio_workflows.json").read_text()
        )[-1]
        self.assertEqual(wf_record["default_preset_id"], payload["applied_default_preset_id"])

    def test_20_reminted_ids_never_reuse_foreign(self):
        raw, _, _ = self._exported(presets=1)
        manifest = json.loads(raw)
        foreign_ids = {
            manifest["workflow"]["workflow_id"],
            manifest["version"]["workflow_version_id"],
            manifest["mapping"]["mapping_id"],
            manifest["presets"][0]["preset_id"],
        }
        manifest["import_presets"] = True
        resp = self.call(
            "POST", "/comfymodal/studio/workflows/import-manifest",
            body_bytes=json.dumps(manifest).encode(), query={"dry_run": "0"},
        )
        payload = self.body(resp)
        local_ids = {
            payload["workflow_id"],
            payload["workflow_version_id"],
            payload["mapping_id"],
            *payload["preset_ids"],
        }
        self.assertEqual(local_ids & foreign_ids, set())
        for local_id in local_ids:
            self.assertTrue(
                local_id.startswith(("wf_", "wv_", "wm_", "wpres_")),
                "unexpected id shape: %s" % local_id,
            )
        version = json.loads(
            (Path(self.root) / ".studio_workflow_versions.json").read_text()
        )[-1]
        self.assertEqual(version["version_number"], 1)

    def test_21_provenance_structured_not_contaminating(self):
        raw, _, _ = self._exported()
        resp = self.call(
            "POST", "/comfymodal/studio/workflows/import-manifest",
            body_bytes=raw, query={"dry_run": "0"},
        )
        payload = self.body(resp)
        version = json.loads(
            (Path(self.root) / ".studio_workflow_versions.json").read_text()
        )[-1]
        prov = version["dependency_metadata"]["import_provenance"]
        self.assertEqual(prov["original_graph_hash"], payload["provenance"]["original_graph_hash"])
        self.assertIn("original_workflow_id", prov)
        wf_record = json.loads(
            (Path(self.root) / ".studio_workflows.json").read_text()
        )[-1]
        self.assertEqual(wf_record["description"], "")
        self.assertEqual(wf_record["source_url"], "")

    def test_22_hash_mismatch_blocks_commit_with_zero_writes(self):
        raw, _, _ = self._exported()
        manifest = json.loads(raw)
        manifest["workflow"]["graph"] = {"tampered": True}
        before = self.snapshot_stores()
        resp = self.call(
            "POST", "/comfymodal/studio/workflows/import-manifest",
            body_bytes=json.dumps(manifest).encode(), query={"dry_run": "0"},
        )
        self.assertEqual(resp.status, 400)
        self.assertEqual(self.snapshot_stores(), before)


def _reexport_version_id(testcase, source_wf):
    versions = testcase.service.store.list_versions_for_workflow(source_wf["workflow_id"])
    return versions[0]["workflow_version_id"]


class AtomicityTests(PortabilityBackendTestBase):
    """Injected-failure rollback: all four collections byte-equal pre-state."""

    def _prepared_manifest(self, preset_count=2, apply_default=False):
        wf = self.create_workflow(name="Atomic Source")
        version = self.capture_version(wf["workflow_id"])
        self.set_mapping(version["workflow_version_id"])
        for i in range(preset_count):
            self.create_preset(version["workflow_version_id"], name="P%d" % i)
        resp = self.export_bytes(version["workflow_version_id"], include_presets=True)
        manifest = json.loads(resp.body)
        manifest["import_presets"] = True
        if apply_default:
            self.service.set_default_preset(wf["workflow_id"], manifest["presets"][0]["preset_id"])
            refreshed = json.loads(
                self.export_bytes(version["workflow_version_id"], include_presets=True).body
            )
            refreshed["import_presets"] = True
            refreshed["apply_default_preset"] = True
            manifest = refreshed
        return manifest

    def _commit(self, manifest):
        import_presets = bool(manifest.pop("import_presets", False))
        apply_default = bool(manifest.pop("apply_default_preset", False))
        return self.portability.commit_import(
            manifest, import_presets=import_presets, apply_default_preset=apply_default
        )

    def _assert_untouched(self, before):
        self.assertEqual(self.snapshot_stores(), before)

    def test_22a_fail_before_workflow_creation(self):
        manifest = self._prepared_manifest()
        before = self.snapshot_stores()
        original = self.portability._build_import_records

        def boom(*a, **k):
            raise RuntimeError("injected")

        self.portability._build_import_records = boom
        try:
            with self.assertRaises(RuntimeError):
                self._commit(manifest)
        finally:
            self.portability._build_import_records = original
        self._assert_untouched(before)

    def test_22b_fail_after_staging_before_transaction(self):
        manifest = self._prepared_manifest()
        before = self.snapshot_stores()
        store = self.portability.store
        original = store.commit_import_transaction

        def boom(*a, **k):
            raise RuntimeError("injected")

        store.commit_import_transaction = boom
        try:
            with self.assertRaises(RuntimeError):
                self._commit(manifest)
        finally:
            store.commit_import_transaction = original
        self._assert_untouched(before)

    def _inject_store_failure(self, attribute, fail_on_call, manifest):
        before = self.snapshot_stores()
        store = self.portability.store
        target = getattr(store, attribute)
        counter = {"n": 0}
        original = target.update

        def patched_update(mutator):
            counter["n"] += 1
            if counter["n"] == fail_on_call:
                raise RuntimeError("injected")
            return original(mutator)

        getattr(store, attribute).update = patched_update
        try:
            with self.assertRaises(RuntimeError):
                self._commit(manifest)
        finally:
            getattr(store, attribute).update = original
        self._assert_untouched(before)

    def test_22c_fail_at_version_step(self):
        self._inject_store_failure("versions", 1, self._prepared_manifest())

    def test_22d_fail_at_mapping_step(self):
        self._inject_store_failure("mappings", 1, self._prepared_manifest())

    def test_22e_fail_at_first_preset(self):
        self._inject_store_failure("presets", 1, self._prepared_manifest())

    def test_22f_fail_at_later_preset(self):
        self._inject_store_failure("presets", 2, self._prepared_manifest())

    def test_22g_fail_after_default_preset_staged(self):
        manifest = self._prepared_manifest(apply_default=True)
        before = self.snapshot_stores()
        store = self.portability.store
        staged = {}
        original_build = self.portability._build_import_records
        original_update = store.workflows.update

        def wrapped_build(*a, **k):
            records = original_build(*a, **k)
            staged["default_preset_id"] = records["workflow"].default_preset_id
            return records

        def boom(mutator):
            raise RuntimeError("injected-default")

        self.portability._build_import_records = wrapped_build
        store.workflows.update = boom
        try:
            with self.assertRaises(RuntimeError):
                self._commit(manifest)
        finally:
            self.portability._build_import_records = original_build
            store.workflows.update = original_update
        self.assertTrue(staged.get("default_preset_id"))
        self._assert_untouched(before)

    def test_22h_fail_at_final_persistence(self):
        self._inject_store_failure("workflows", 1, self._prepared_manifest())

    def test_22i_successful_commit_shape(self):
        manifest = self._prepared_manifest(apply_default=True)
        result = self._commit(manifest)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["applied_default_preset_id"])
        workflows = json.loads((Path(self.root) / ".studio_workflows.json").read_text())
        imported = [w for w in workflows if w["workflow_id"] == result["workflow_id"]]
        self.assertEqual(len(imported), 1)
        self.assertEqual(imported[0]["default_preset_id"], result["applied_default_preset_id"])


class ConcurrencyTests(PortabilityBackendTestBase):
    def test_23_concurrent_committed_imports_same_manifest(self):
        wf = self.create_workflow(name="Concurrent Source")
        version = self.capture_version(wf["workflow_id"])
        self.set_mapping(version["workflow_version_id"])
        self.create_preset(version["workflow_version_id"], name="P1")
        resp = self.export_bytes(version["workflow_version_id"], include_presets=True)
        raw = resp.body
        manifest = json.loads(raw)
        manifest["import_presets"] = True

        handler = _handler_for(
            self.stub, "POST", "/comfymodal/studio/workflows/import-manifest"
        )
        assert handler is not None
        results = []

        def worker():
            request = _MockRequest(
                body_bytes=json.dumps(manifest).encode(), query={"dry_run": "0"}
            )
            results.append(_run(handler(request)))

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), 2)
        for resp in results:
            self.assertEqual(resp.status, 200, resp.body)
        payloads = [json.loads(r.body) for r in results]
        ids = {(p["workflow_id"], p["workflow_version_id"]) for p in payloads}
        self.assertEqual(len(ids), 2)

        workflows = json.loads((Path(self.root) / ".studio_workflows.json").read_text())
        versions = json.loads((Path(self.root) / ".studio_workflow_versions.json").read_text())
        mappings = json.loads((Path(self.root) / ".studio_workflow_mappings.json").read_text())
        presets = json.loads((Path(self.root) / ".studio_workflow_presets.json").read_text())
        self.assertEqual(len(workflows), 3)  # source + 2 imports
        self.assertEqual(len(versions), 3)
        self.assertEqual(len(mappings), 3)
        self.assertEqual(len(presets), 3)

        version_ids = {v["workflow_version_id"] for v in versions}
        for mapping in mappings:
            self.assertIn(mapping["workflow_version_id"], version_ids)
        mapping_by_version = {m["workflow_version_id"]: m for m in mappings}
        for payload in payloads:
            mapping = mapping_by_version[payload["workflow_version_id"]]
            self.assertEqual(mapping["mapping_id"], payload["mapping_id"])
        for payload in payloads:
            owned = [
                p for p in presets
                if p["workflow_version_id"] == payload["workflow_version_id"]
            ]
            self.assertEqual(len(owned), 1)


class PortabilityReportTests(PortabilityBackendTestBase):
    def _report_via_route(self, version_id, resolver=None):
        stub = _StubServer()
        register_workflow_routes(stub, node_dir=self.root, resolver=resolver or CoreOnlyResolver())
        handler = _handler_for(
            stub, "GET", "/comfymodal/studio/workflows/versions/{version_id}/portability"
        )
        assert handler is not None
        return _run(handler(_MockRequest(match_info={"version_id": version_id})))

    def test_24_clean_core_workflow_is_low(self):
        _, version, _ = self.setup_mapped_version(name="Clean")
        resp = self._report_via_route(version["workflow_version_id"])
        self.assertEqual(resp.status, 200)
        report = self.body(resp)["portability"]
        pc.validate_report(report)
        self.assertEqual(report["risk_level"], "low")
        self.assertEqual(report["version_id"], version["workflow_version_id"])

    def test_25_current_corpus_medium_with_environment_high_isolated(self):
        wf = self.create_workflow(name="Corpus Shape")
        capture = {
            "graph_json": corpus_graph_json(),
            "api_prompt_json": {"workflow": {}, "output": corpus_prompt()},
        }
        version = self.service.create_version_from_capture(wf["workflow_id"], capture)
        stub_resolver = CorpusResolver()
        resp = self._report_via_route(version["workflow_version_id"], resolver=stub_resolver)
        self.assertEqual(resp.status, 200)
        report = self.body(resp)["portability"]
        pc.validate_report(report)
        expected = json.loads(
            (Path(__file__).parent / "fixtures" / "portability" / "expected"
             / "current_corpus_shape.expected.json").read_text()
        )
        self.assertEqual(report["risk_level"], expected["workflow_portability_risk"])
        workflow_codes = {i["code"] for i in report["issues"]}
        # Environment issues live in their own section, never in the pool.
        env_codes = {i["code"] for i in report["environment"]["issues"]}
        self.assertNotIn("custom_node_source_unpinned", workflow_codes)
        self.assertIn("custom_node_source_unpinned", env_codes)
        self.assertEqual(report["environment"]["risk_level"], expected["environment_reproducibility"])
        self.assertEqual(
            report["environment"]["source"],
            pc.ENVIRONMENT_SOURCE_CURRENT_STUDIO,
        )
        core_codes = {
            i["code"] for i in report["issues"]
            if i["subject"] != pc.SUBJECT_TARGET
        }
        for code in expected["expected_issue_codes"]:
            self.assertIn(code, core_codes)

    def test_26_all_six_target_ids_present(self):
        _, version, _ = self.setup_mapped_version()
        resp = self._report_via_route(version["workflow_version_id"])
        report = self.body(resp)["portability"]
        self.assertEqual(tuple(sorted(report["targets"])), tuple(sorted(pc.TARGET_IDS)))
        for tid, result in report["targets"].items():
            self.assertIn("risk_level", result)
            self.assertIn("issue_codes", result)
            self.assertIn("advice", result)

    def test_27_comfy_cloud_off_catalog_dependency_is_high(self):
        evidence = __import__("portability_targets").build_target_evidence(
            global_issue_codes=[],
            signals={},
            custom_nodes=[{
                "name": "SomeCustomNode",
                "provenance": "declared",
                "manager_restorable": True,
                "product_internal": False,
                "install_status": "installed",
                "requires_python_install": False,
                "requires_system_packages": False,
                "requires_native_build": False,
                "requires_cuda_build": False,
                "target_supported": {"comfy_cloud": False},
            }],
            models=[],
            absolute_paths=[],
        )
        outcome = __import__("portability_targets").evaluate_target_readiness(evidence)
        comfy = outcome["targets"]["comfy_cloud"]
        self.assertEqual(comfy["risk_level"], "high")
        self.assertIn("comfy_cloud_node_off_catalog", comfy["issue_codes"])

    def test_28_runcomfy_unknown_capability_survives_unknown(self):
        targets_mod = __import__("portability_targets")
        evidence = targets_mod.build_target_evidence(
            global_issue_codes=[],
            signals={},
            custom_nodes=[{
                "name": "NativeNode",
                "provenance": "exact",
                "manager_restorable": True,
                "product_internal": False,
                "install_status": "installed",
                "requires_python_install": False,
                "requires_system_packages": True,
                "requires_native_build": True,
                "requires_cuda_build": False,
                "target_supported": {},
            }],
            models=[],
            absolute_paths=[],
            runcomfy_native_capability="unknown",
        )
        outcome = targets_mod.evaluate_target_readiness(evidence)
        runcomfy = outcome["targets"]["runcomfy"]
        self.assertEqual(runcomfy["risk_level"], "unknown")
        self.assertIn(pc.ISSUE_TARGET_CAPABILITY_UNKNOWN, runcomfy["issue_codes"])

    def test_29_no_compatibility_naming_collision(self):
        registered = [(m, p) for m, p, _ in self.stub.routes._handlers]
        paths = {p for _, p in registered}
        self.assertIn("/comfymodal/studio/workflows/versions/{version_id}/export", paths)
        self.assertIn("/comfymodal/studio/workflows/import-manifest", paths)
        self.assertIn("/comfymodal/studio/workflows/versions/{version_id}/portability", paths)
        for path in paths:
            self.assertNotIn("compatibility", path)

    def test_30_report_endpoint_unknown_version_404(self):
        resp = self._report_via_route("wv_nope")
        self.assertEqual(resp.status, 404)

    def test_31_aux_id_rescues_unresolved_provenance(self):
        from portability_evidence import derive_node_provenance, extract_aux_id_provenance

        graph = {"nodes": [{"type": "MysteryNode", "properties": {"aux_id": "author/some-repo"}}]}
        aux = extract_aux_id_provenance(graph)
        provenance = derive_node_provenance([], aux)
        self.assertEqual(provenance["MysteryNode"]["quality"], "declared")
        self.assertEqual(provenance["MysteryNode"]["repo"], "https://github.com/author/some-repo")

    def test_32_host_fallback_repo_replaced_by_aux_id_in_export(self):
        class FallbackResolver:
            def resolve_version(self, version):
                dm = version.get("dependency_metadata") or {}
                classes = sorted(dm.get("node_classes") or [])
                package = [c for c in classes if c != "SaveImage"]
                rows = []
                if package:
                    rows.append({
                        "name": "fallback-attributed", "state": "installed",
                        "install_path": "", "installed_commit": "a1b2c3d4e5",
                        "required_revision": "",
                        "repository_url": "https://github.com/Comfy-Org/ComfyUI",
                        "classes": package,
                    })
                core = [c for c in classes if c == "SaveImage"]
                if core:
                    rows.append({
                        "name": "ComfyUI core", "state": "installed",
                        "install_path": "", "installed_commit": "",
                        "required_revision": "", "repository_url": "",
                        "classes": core,
                    })
                return {"models": [], "custom_nodes": rows}

            def reasons_for(self, version):
                return []

        wf = self.create_workflow(name="Fallback Export")
        prompt = {
            "20": {"class_type": "FixtureFallbackAttributionNode", "inputs": {"value": 1}},
            "21": {"class_type": "SaveImage", "inputs": {"images": ["20", 0]}},
        }
        graph = {"nodes": [{"id": 20, "type": "FixtureFallbackAttributionNode",
                            "properties": {"aux_id": "real-author/real-nodes"}}],
                 "links": [], "extra": {}}
        version = self.service.create_version_from_capture(
            wf["workflow_id"],
            {"graph_json": graph, "api_prompt_json": {"workflow": {}, "output": prompt}},
        )
        self.set_mapping(version["workflow_version_id"])
        fallback_service = PortabilityService(self.service, resolver=FallbackResolver())
        result = fallback_service.export_manifest(version["workflow_version_id"])
        records = result["manifest"]["custom_nodes"]
        repos = [r["repo_url"] for r in records]
        self.assertIn("https://github.com/real-author/real-nodes", repos)
        self.assertNotIn("https://github.com/Comfy-Org/ComfyUI", repos)


if __name__ == "__main__":
    unittest.main()
