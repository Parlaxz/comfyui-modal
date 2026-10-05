"""Behavior tests for the Studio Workflow HTTP routes.

``studio_workflow_routes.register_workflow_routes`` is exercised through the
same ``_StubServer`` / ``_StubRouteTable`` / ``_MockRequest`` / ``_run``
helpers used by ``test_routes_registered.py``: a stub route table records the
decorated handlers and each test looks one up and drives it synchronously
with a fake ``aiohttp`` request.

The workflow domain business rules (immutable versions, one immutable mapping
per version, mapping revisions) live in
``studio_domain.services.WorkflowDomainService`` and are NOT re-implemented
here — the handlers only translate HTTP <-> service calls.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from studio_domain import derive_mapping_candidates
from studio_domain.store import WorkflowDomainStore


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ── Minimal _server stub (self-contained copy of the house pattern) ──────


class _StubServer:
    def __init__(self) -> None:
        self.routes: Any = _StubRouteTable()


class _StubRouteTable:
    """Mimic ``PromptServer.instance.routes`` enough that the route
    decorators in studio_workflow_routes.py can record their handlers."""

    def __init__(self) -> None:
        self._handlers: list[tuple[str, str, Any]] = []

    def get(self, path: str) -> Any:
        def deco(fn):
            self._handlers.append(("GET", path, fn))
            return fn
        return deco

    def post(self, path: str) -> Any:
        def deco(fn):
            self._handlers.append(("POST", path, fn))
            return fn
        return deco

    def put(self, path: str) -> Any:
        def deco(fn):
            self._handlers.append(("PUT", path, fn))
            return fn
        return deco

    def delete(self, path: str) -> Any:
        def deco(fn):
            self._handlers.append(("DELETE", path, fn))
            return fn
        return deco

    def patch(self, path: str) -> Any:
        def deco(fn):
            self._handlers.append(("PATCH", path, fn))
            return fn
        return deco


class _MockRequest:
    """Minimal aiohttp.web.Request shim."""

    def __init__(self, *, json_body: dict | None = None, query: dict | None = None, match_info: dict | None = None):
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
    """Run an async coroutine to completion synchronously."""
    return asyncio.run(coro)


def _paths_match(pattern: str, actual: str) -> bool:
    p_parts = pattern.split("/")
    a_parts = actual.split("/")
    if len(p_parts) != len(a_parts):
        return False
    for pp, ap in zip(p_parts, a_parts):
        if pp.startswith("{") and pp.endswith("}"):
            continue
        if pp != ap:
            return False
    return True


def _handler_for(module, method: str, path: str):
    """Look up the route handler in the stub server's route table."""
    for m, p, fn in module._server.routes._handlers:
        if m == method and p == path:
            return fn
    # Try with simple path match (ignoring {param} segments)
    for m, p, fn in module._server.routes._handlers:
        if m != method:
            continue
        if _paths_match(p, path):
            return fn
    return None


def _load_repo_module(module_name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(module_name, REPO_ROOT / relative_path)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# ── fixtures (adapted from test_workflow_domain.py, standalone) ──────────


def make_capture(prompt_nodes: dict, graph_json=None) -> dict:
    return {
        "graph_json": graph_json or {"id": "g1", "nodes": []},
        "api_prompt_json": {"workflow": {}, "output": prompt_nodes},
    }


def txt2img_prompt(seed: int = 0, steps: int = 20, sampler: str = "euler") -> dict:
    return {
        "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "hello world", "clip": ["4", 0]}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "negative", "clip": ["4", 0]}},
        "3": {"class_type": "KSampler", "inputs": {
            "model": ["4", 0], "seed": seed, "steps": steps, "cfg": 7.0,
            "sampler_name": sampler, "scheduler": "normal",
            "positive": ["1", 0], "negative": ["2", 0], "latent_image": ["5", 0],
            "denoise": 1.0}},
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "krea_model.safetensors"}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
        "6": {"class_type": "SaveImage", "inputs": {"images": ["3", 0]}},
    }


def fake_node_def(class_type: str):
    if class_type == "KSampler":
        return (
            {
                "model": ("MODEL",),
                "positive": ("CONDITIONING",),
                "negative": ("CONDITIONING",),
                "latent_image": ("LATENT",),
                "seed": ("INT", {"min": 0, "max": 281474976710655, "step": 1, "default": 0}),
                "steps": ("INT", {"min": 1, "max": 150, "step": 1, "default": 20}),
                "cfg": ("FLOAT", {"min": 0.0, "max": 30.0, "step": 0.5, "default": 7.0}),
                "sampler_name": (["euler", "dpmpp_2m"],),
                "scheduler": (["normal", "karras"],),
                "denoise": ("FLOAT", {"min": 0.0, "max": 1.0, "step": 0.01, "default": 1.0}),
            },
            {},
        )
    if class_type == "CLIPTextEncode":
        return ({"text": ("STRING", {"multiline": True}), "clip": ("CLIP",)}, {})
    if class_type == "EmptyLatentImage":
        return (
            {
                "width": ("INT", {"min": 16, "max": 8192, "step": 8}),
                "height": ("INT", {"min": 16, "max": 8192, "step": 8}),
                "batch_size": ("INT", {"min": 1, "max": 64}),
            },
            {},
        )
    if class_type == "CheckpointLoaderSimple":
        return ({"ckpt_name": (["krea_model.safetensors", "flux-dev.safetensors"],)}, {})
    if class_type == "SaveImage":
        return ({"images": ("IMAGE",), "filename_prefix": ("STRING", {"default": "ComfyUI"})}, {})
    return None


# ── Tests ────────────────────────────────────────────────────────────────


class WorkflowRoutesTests(unittest.TestCase):
    """End-to-end behavior tests for the Studio Workflow route handlers."""

    @classmethod
    def setUpClass(cls):
        cls.routes_mod = _load_repo_module(
            "studio_workflow_routes_under_test", "studio_workflow_routes.py"
        )

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = str(Path(self._tmp.name))
        self.mod = self._register(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # ── helpers ──────────────────────────────────────────────────────────

    def _register(self, node_dir: str):
        stub = _StubServer()
        self.routes_mod.register_workflow_routes(stub, node_dir=node_dir)
        return type("WorkflowRoutesModule", (), {"_server": stub})

    def _call(self, method: str, path: str, **req_kwargs):
        handler = _handler_for(self.mod, method, path)
        self.assertIsNotNone(handler, f"no route registered for {method} {path}")
        assert handler is not None
        return _run(handler(_MockRequest(**req_kwargs)))

    def _body(self, resp) -> dict:
        return json.loads(resp.body)

    def _create_workflow(self, **fields) -> dict:
        body = {"name": "Test Workflow", **fields}
        resp = self._call("POST", "/comfymodal/studio/workflows", json_body=body)
        self.assertEqual(resp.status, 200, msg=f"create body={resp.body}")
        return self._body(resp)["workflow"]

    def _capture_version(self, workflow_id: str, prompt: dict | None = None) -> dict:
        capture = make_capture(prompt if prompt is not None else txt2img_prompt())
        resp = self._call(
            "POST", "/comfymodal/studio/workflows/{workflow_id}/versions",
            match_info={"workflow_id": workflow_id}, json_body=capture,
        )
        self.assertEqual(resp.status, 200, msg=f"capture body={resp.body}")
        return self._body(resp)["version"]

    def _mapping_payload(self, prompt: dict | None = None) -> dict:
        capture = make_capture(prompt if prompt is not None else txt2img_prompt())
        entries, output_node_id = derive_mapping_candidates(
            capture, node_def_provider=fake_node_def
        )
        return {
            "entries": {role: e.to_dict() for role, e in entries.items()},
            "output_node_id": output_node_id,
        }

    def _set_mapping(self, version_id: str, prompt: dict | None = None) -> dict:
        payload = self._mapping_payload(prompt)
        resp = self._call(
            "POST", "/comfymodal/studio/workflows/versions/{version_id}/mapping",
            match_info={"version_id": version_id}, json_body=payload,
        )
        self.assertEqual(resp.status, 200, msg=f"mapping body={resp.body}")
        return self._body(resp)["mapping"]

    def _setup_mapped(self, workflow_id: str, prompt: dict | None = None) -> dict:
        version = self._capture_version(workflow_id, prompt)
        self._set_mapping(version["workflow_version_id"], prompt)
        return version

    def _default_values(self, prompt: dict | None = None) -> dict:
        prompt = prompt or txt2img_prompt()
        return {
            "positive_prompt": "hello world",
            "negative_prompt": "negative",
            "seed": prompt["3"]["inputs"]["seed"],
            "steps": prompt["3"]["inputs"]["steps"],
            "cfg": prompt["3"]["inputs"]["cfg"],
            "sampler": prompt["3"]["inputs"]["sampler_name"],
            "scheduler": prompt["3"]["inputs"]["scheduler"],
            "denoise": prompt["3"]["inputs"]["denoise"],
            "width": prompt["5"]["inputs"]["width"],
            "height": prompt["5"]["inputs"]["height"],
            "model": prompt["4"]["inputs"]["ckpt_name"],
        }

    # ── 1. list empty / create / missing name ────────────────────────────

    def test_01_list_empty_create_and_missing_name(self):
        # Empty library.
        resp = self._call("GET", "/comfymodal/studio/workflows")
        self.assertEqual(resp.status, 200)
        body = self._body(resp)
        self.assertEqual(body.get("status"), "ok")
        self.assertEqual(body.get("workflows"), [])

        # Create with a name.
        resp = self._call("POST", "/comfymodal/studio/workflows",
                          json_body={"name": "Krea Portrait Workflow"})
        self.assertEqual(resp.status, 200, msg=resp.body)
        body = self._body(resp)
        self.assertEqual(body.get("status"), "ok")
        workflow = body.get("workflow", {})
        self.assertTrue(str(workflow.get("workflow_id", "")).startswith("wf_"))
        self.assertEqual(workflow.get("name"), "Krea Portrait Workflow")

        # Create without a name → 400.
        resp = self._call("POST", "/comfymodal/studio/workflows",
                          json_body={"description": "no name here"})
        self.assertEqual(resp.status, 400)
        body = self._body(resp)
        self.assertEqual(body.get("status"), "error")
        self.assertIn("name", body.get("message", "").lower())

    # ── 2. workflow detail / unknown id ──────────────────────────────────

    def test_02_detail_and_unknown(self):
        workflow = self._create_workflow(name="Detail Me")
        resp = self._call(
            "GET", "/comfymodal/studio/workflows/{workflow_id}",
            match_info={"workflow_id": workflow["workflow_id"]},
        )
        self.assertEqual(resp.status, 200)
        body = self._body(resp)
        self.assertEqual(body["workflow"]["workflow_id"], workflow["workflow_id"])

        resp = self._call(
            "GET", "/comfymodal/studio/workflows/{workflow_id}",
            match_info={"workflow_id": "wf_nope"},
        )
        self.assertEqual(resp.status, 404)
        body = self._body(resp)
        self.assertEqual(body.get("status"), "error")

    # ── 3. patch workflow metadata ───────────────────────────────────────

    def test_03_patch_workflow(self):
        workflow = self._create_workflow(name="Original")
        resp = self._call(
            "PATCH", "/comfymodal/studio/workflows/{workflow_id}",
            match_info={"workflow_id": workflow["workflow_id"]},
            json_body={
                "name": "Renamed",
                "description": "a new description",
                "folder": "Portraits/AI",
                "tags": ["portrait", "krea"],
                "favorite": True,
                "source_url": "https://example.com/wf",
                "source_author": "Krea",
                "compatible_models": ["krea_model.safetensors"],
            },
        )
        self.assertEqual(resp.status, 200, msg=resp.body)
        updated = self._body(resp)["workflow"]
        self.assertEqual(updated["name"], "Renamed")
        self.assertEqual(updated["folder"], "Portraits/AI")
        self.assertEqual(updated["tags"], ["portrait", "krea"])
        self.assertTrue(updated["favorite"])
        self.assertEqual(updated["source_url"], "https://example.com/wf")
        self.assertEqual(updated["source_author"], "Krea")
        self.assertEqual(updated["compatible_models"], ["krea_model.safetensors"])

        # Unknown field → 400.
        resp = self._call(
            "PATCH", "/comfymodal/studio/workflows/{workflow_id}",
            match_info={"workflow_id": workflow["workflow_id"]},
            json_body={"latest_version_id": "wv_x"},
        )
        self.assertEqual(resp.status, 400)
        body = self._body(resp)
        self.assertEqual(body.get("status"), "error")
        self.assertIn("not editable", body.get("message", ""))

        # Unknown id → 404.
        resp = self._call(
            "PATCH", "/comfymodal/studio/workflows/{workflow_id}",
            match_info={"workflow_id": "wf_ghost"},
            json_body={"name": "Ghost"},
        )
        self.assertEqual(resp.status, 404)

    # ── 4. import creates workflow + first version ───────────────────────

    def test_04_import_creates_workflow_and_first_version(self):
        capture = make_capture(txt2img_prompt())
        resp = self._call("POST", "/comfymodal/studio/workflows/import", json_body={
            "name": "Imported WF",
            "description": "from a capture",
            "graph_json": capture["graph_json"],
            "api_prompt_json": capture["api_prompt_json"],
        })
        self.assertEqual(resp.status, 200, msg=resp.body)
        body = self._body(resp)
        self.assertEqual(body.get("status"), "ok")
        workflow = body["workflow"]
        version = body["version"]
        self.assertTrue(str(workflow["workflow_id"]).startswith("wf_"))
        # The response returns the pre-update workflow snapshot (latest_version_id
        # is still "" on it); the stored workflow is wired to the new version.
        self.assertEqual(workflow["latest_version_id"], "")
        resp = self._call(
            "GET", "/comfymodal/studio/workflows/{workflow_id}",
            match_info={"workflow_id": workflow["workflow_id"]},
        )
        self.assertEqual(self._body(resp)["workflow"]["latest_version_id"],
                         version["workflow_version_id"])
        self.assertEqual(version["version_number"], 1)
        # graph_hash is non-empty.
        self.assertTrue(version.get("graph_hash"))
        # No mapping yet → incomplete + unrunnable.
        self.assertEqual(version["state"]["status"], "incomplete")
        self.assertFalse(version["state"]["runnable"])
        self.assertTrue(any("missing mapping" in r for r in version["state"]["reasons"]))
        # Capture body shape preserved.
        self.assertEqual(version["api_prompt_json"]["output"]["3"]["class_type"], "KSampler")

    # ── 5. folders / tags ────────────────────────────────────────────────

    def test_05_folders_and_tags(self):
        self._create_workflow(name="A", folder="a/b/c", tags=["t1"])
        self._create_workflow(name="B", folder="a/b", tags=["t2"])
        self._create_workflow(name="C", folder="a/b/c")
        self._create_workflow(name="D", folder="x")

        resp = self._call("GET", "/comfymodal/studio/workflows/folders")
        self.assertEqual(resp.status, 200)
        self.assertEqual(self._body(resp)["folders"], ["a", "a/b", "a/b/c", "x"])

        # Tags aggregate from workflow tags only; presets no longer exist.
        e = self._create_workflow(name="E", folder="y", tags=["t3"])
        self._setup_mapped(e["workflow_id"])

        resp = self._call("GET", "/comfymodal/studio/workflows/tags")
        self.assertEqual(resp.status, 200)
        self.assertEqual(self._body(resp)["tags"], ["t1", "t2", "t3"])

        resp = self._call(
            "POST", "/comfymodal/studio/workflows/folders",
            json_body={"path": " /empty/new/"},
        )
        self.assertEqual(resp.status, 200, msg=resp.body)
        self.assertEqual(
            self._body(resp)["folders"],
            ["a", "a/b", "a/b/c", "empty", "empty/new", "x", "y"],
        )
        resp = self._call(
            "POST", "/comfymodal/studio/workflows/folders",
            json_body={"path": " / "},
        )
        self.assertEqual(resp.status, 400)

    # ── 6. list filters ──────────────────────────────────────────────────

    def test_06_list_filters(self):
        self._create_workflow(name="Sunset Portrait", description="a krea style painting",
                              folder="portraits/krea", tags=["portrait", "krea"], favorite=True)
        self._create_workflow(name="Sunrise Landscape", description="nature at dawn",
                              folder="landscapes", tags=["nature"], favorite=False)
        self._create_workflow(name="Night City Portrait", description="neon krea lights",
                              folder="portraits/city", tags=["city", "portrait"], favorite=False)

        def _ids(query=None):
            resp = self._call("GET", "/comfymodal/studio/workflows", query=query or {})
            self.assertEqual(resp.status, 200)
            return [w["name"] for w in self._body(resp)["workflows"]]

        self.assertEqual(len(_ids()), 3)

        # search: name/description substring, case-insensitive.
        self.assertEqual(set(_ids({"search": "portrait"})), {"Sunset Portrait", "Night City Portrait"})
        self.assertEqual(set(_ids({"search": "KREA"})), {"Sunset Portrait", "Night City Portrait"})
        self.assertEqual(_ids({"search": "zzz-nowhere"}), [])

        # tag.
        self.assertEqual(_ids({"tag": "portrait"}), ["Sunset Portrait", "Night City Portrait"])
        self.assertEqual(_ids({"tag": "nature"}), ["Sunrise Landscape"])

        # folder: exact or prefix.
        self.assertEqual(set(_ids({"folder": "portraits"})), {"Sunset Portrait", "Night City Portrait"})
        self.assertEqual(_ids({"folder": "portraits/city"}), ["Night City Portrait"])
        self.assertEqual(_ids({"folder": "landscapes"}), ["Sunrise Landscape"])

        # favorite.
        self.assertEqual(_ids({"favorite": "1"}), ["Sunset Portrait"])

    def test_06b_list_omits_static_graph_but_detail_serves_it(self):
        """Library list rows must not carry the durable static graph: it is
        ~99% of a stored Workflow record and no list view reads it. The
        per-workflow detail endpoint remains the authority for it."""
        graph = {"nodes": [{"id": 1, "type": "KSampler"}], "links": []}
        created = self._create_workflow(name="Graphy", static_graph=graph)
        self.assertEqual(created.get("static_graph"), graph)

        resp = self._call("GET", "/comfymodal/studio/workflows")
        self.assertEqual(resp.status, 200)
        rows = self._body(resp)["workflows"]
        self.assertEqual([w["name"] for w in rows], ["Graphy"])
        self.assertNotIn("static_graph", rows[0])
        # List-specific enrichment is still present.
        self.assertIn("version_count", rows[0])

        detail = self._call(
            "GET", "/comfymodal/studio/workflows/{workflow_id}",
            match_info={"workflow_id": created["workflow_id"]},
        )
        self.assertEqual(detail.status, 200)
        self.assertEqual(
            self._body(detail)["workflow"]["static_graph"], graph
        )

    # ── 7. versions: capture / dedupe / list / state ─────────────────────

    def test_07_versions_capture_dedupe_list_state(self):
        workflow = self._create_workflow(name="Versions")

        # First capture → version 1.
        v1 = self._capture_version(workflow["workflow_id"])
        self.assertEqual(v1["version_number"], 1)

        # Identical capture → deduped, same version, still one record.
        again = self._capture_version(workflow["workflow_id"])
        self.assertEqual(again["workflow_version_id"], v1["workflow_version_id"])
        self.assertEqual(again["version_number"], 1)

        # Structural change → version 2.
        changed = txt2img_prompt()
        del changed["3"]["inputs"]["steps"]
        v2 = self._capture_version(workflow["workflow_id"], changed)
        self.assertEqual(v2["version_number"], 2)

        # Versions list sorted ascending.
        resp = self._call(
            "GET", "/comfymodal/studio/workflows/{workflow_id}/versions",
            match_info={"workflow_id": workflow["workflow_id"]},
        )
        self.assertEqual(resp.status, 200)
        versions = self._body(resp)["versions"]
        self.assertEqual([v["version_number"] for v in versions], [1, 2])
        self.assertEqual(versions[0]["workflow_version_id"], v1["workflow_version_id"])

        # Unknown version detail → 404.
        resp = self._call(
            "GET", "/comfymodal/studio/workflows/versions/{version_id}",
            match_info={"version_id": "wv_ghost"},
        )
        self.assertEqual(resp.status, 404)

        # State endpoint: no mapping yet → runnable False with reasons.
        resp = self._call(
            "GET", "/comfymodal/studio/workflows/versions/{version_id}/state",
            match_info={"version_id": v1["workflow_version_id"]},
        )
        self.assertEqual(resp.status, 200)
        state = self._body(resp)["state"]
        self.assertFalse(state["runnable"])
        self.assertTrue(any("missing mapping" in r for r in state["reasons"]))

    # ── 8. mapping candidates ────────────────────────────────────────────

    def test_08_mapping_candidates(self):
        workflow = self._create_workflow(name="Candidates")
        version = self._capture_version(workflow["workflow_id"])

        resp = self._call(
            "GET", "/comfymodal/studio/workflows/versions/{version_id}/mapping/candidates",
            match_info={"version_id": version["workflow_version_id"]},
        )
        self.assertEqual(resp.status, 200, msg=resp.body)
        body = self._body(resp)
        candidates = body["candidates"]
        # Semantic roles derived from the txt2img prompt inputs.
        for role in ("positive_prompt", "negative_prompt", "seed", "steps", "cfg",
                     "sampler", "scheduler", "denoise", "width", "height", "model"):
            self.assertIn(role, candidates, msg=f"missing candidate role {role!r}")
        # Entries carry graph location metadata.
        self.assertEqual(candidates["seed"]["node_id"], "3")
        self.assertEqual(candidates["seed"]["input_name"], "seed")
        self.assertEqual(candidates["sampler"]["node_id"], "3")
        self.assertEqual(body["output_node_id"], "6")

    # ── 9. mapping create + 409 on second create ─────────────────────────

    def test_09_mapping_create_and_conflict(self):
        workflow = self._create_workflow(name="Mapping")
        version = self._capture_version(workflow["workflow_id"])
        version_id = version["workflow_version_id"]

        resp = self._call(
            "POST", "/comfymodal/studio/workflows/versions/{version_id}/mapping",
            match_info={"version_id": version_id}, json_body=self._mapping_payload(),
        )
        self.assertEqual(resp.status, 200, msg=resp.body)
        body = self._body(resp)
        self.assertEqual(body.get("status"), "ok")
        mapping = body["mapping"]
        self.assertTrue(mapping["mapping_id"].startswith("wm_"))
        self.assertEqual(mapping["workflow_version_id"], version_id)
        self.assertGreater(len(mapping["entries"]), 0)

        # A second create on the same version is refused.
        resp = self._call(
            "POST", "/comfymodal/studio/workflows/versions/{version_id}/mapping",
            match_info={"version_id": version_id}, json_body=self._mapping_payload(),
        )
        self.assertEqual(resp.status, 409)
        body = self._body(resp)
        self.assertEqual(body.get("status"), "error")
        message = body.get("message", "")
        self.assertTrue("immutable" in message or "revision" in message,
                        msg=f"unexpected message: {message}")

    # ── 10. mapping revision ─────────────────────────────────────────────

    def test_10_mapping_revision(self):
        workflow = self._create_workflow(name="Revision")
        v1 = self._setup_mapped(workflow["workflow_id"])
        v1_id = v1["workflow_version_id"]

        # Revised entries without the "steps" control.
        revised = self._mapping_payload()
        del revised["entries"]["steps"]

        resp = self._call(
            "POST", "/comfymodal/studio/workflows/versions/{version_id}/mapping/revision",
            match_info={"version_id": v1_id}, json_body=revised,
        )
        self.assertEqual(resp.status, 200, msg=resp.body)
        body = self._body(resp)
        self.assertEqual(body.get("status"), "ok")
        v2 = body["version"]
        self.assertNotEqual(v2["workflow_version_id"], v1_id)
        self.assertEqual(v2["version_number"], 2)

        # Latest-version pointer moved to the revision.
        resp = self._call(
            "GET", "/comfymodal/studio/workflows/{workflow_id}",
            match_info={"workflow_id": workflow["workflow_id"]},
        )
        self.assertEqual(self._body(resp)["workflow"]["latest_version_id"],
                         v2["workflow_version_id"])

        # v1 keeps its original mapping (still has steps).
        resp = self._call(
            "GET", "/comfymodal/studio/workflows/versions/{version_id}/mapping",
            match_info={"version_id": v1_id},
        )
        self.assertEqual(resp.status, 200)
        m1 = self._body(resp)["mapping"]
        roles1 = {e["semantic_role"] for e in m1["entries"]}
        self.assertIn("steps", roles1)

        # v2 has the revised mapping (no steps).
        resp = self._call(
            "GET", "/comfymodal/studio/workflows/versions/{version_id}/mapping",
            match_info={"version_id": v2["workflow_version_id"]},
        )
        self.assertEqual(resp.status, 200)
        m2 = self._body(resp)["mapping"]
        roles2 = {e["semantic_role"] for e in m2["entries"]}
        self.assertNotIn("steps", roles2)
        self.assertIn("seed", roles2)

    # ── 11. no version mutation routes ──────────────────────────────────

    def test_19_no_version_mutation_routes(self):
        # Versions are immutable: no PATCH route for a version.
        self.assertIsNone(_handler_for(
            self.mod, "PATCH", "/comfymodal/studio/workflows/versions/{version_id}"))

    def test_20_delete_workflow_cascades_and_preserves_unrelated_records(self):
        workflow = self._create_workflow(name="Delete Me")
        version = self._setup_mapped(workflow["workflow_id"])
        changed_prompt = txt2img_prompt()
        changed_prompt["5"]["inputs"]["batch_size"] = 2
        second_version = self._setup_mapped(workflow["workflow_id"], changed_prompt)

        other = self._create_workflow(name="Keep Me")
        other_version = self._setup_mapped(other["workflow_id"])

        response = self._call(
            "DELETE", "/comfymodal/studio/workflows/{workflow_id}",
            match_info={"workflow_id": workflow["workflow_id"]},
        )
        self.assertEqual(response.status, 200, msg=response.body)
        self.assertEqual(self._body(response), {"status": "ok"})

        snapshot = WorkflowDomainStore(self.root).snapshot_all()
        self.assertNotIn(workflow["workflow_id"], {
            row["workflow_id"] for row in snapshot["workflows"]
        })
        self.assertNotIn(version["workflow_version_id"], {
            row["workflow_version_id"] for row in snapshot["versions"]
        })
        self.assertNotIn(second_version["workflow_version_id"], {
            row["workflow_version_id"] for row in snapshot["versions"]
        })
        self.assertFalse(any(
            row.get("workflow_version_id") in {
                version["workflow_version_id"],
                second_version["workflow_version_id"],
            }
for row in snapshot["mappings"]
        ))

        self.assertIn(other["workflow_id"], {
            row["workflow_id"] for row in snapshot["workflows"]
        })
        self.assertIn(other_version["workflow_version_id"], {
            row["workflow_version_id"] for row in snapshot["versions"]
        })
        self.assertTrue(any(
            row.get("workflow_version_id") == other_version["workflow_version_id"]
            for row in snapshot["mappings"]
        ), "unrelated mapping survives")

        response = self._call(
            "DELETE", "/comfymodal/studio/workflows/{workflow_id}",
            match_info={"workflow_id": "wf_missing"},
        )
        self.assertEqual(response.status, 404)
        self.assertEqual(self._body(response).get("status"), "error")


if __name__ == "__main__":
    unittest.main()
