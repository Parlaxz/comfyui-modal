"""Route tests for the Studio Model Library + dependency HTTP API.

Handlers are driven synchronously through the same ``_StubServer`` /
``_MockRequest`` pattern used by ``test_workflow_routes.py`` (helpers are
copied here; ``test_workflow_routes.py`` is not modified).
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

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests import _test_env  # noqa: E402,F401  (hide real ComfyUI from sys.path)

from dependency_resolver import DependencyResolver  # noqa: E402
from model_library import MODEL_TYPES  # noqa: E402


# ── Minimal _server stub (self-contained copy of the house pattern) ──────


class _StubServer:
    def __init__(self) -> None:
        self.routes: Any = _StubRouteTable()


class _StubRouteTable:
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

    def patch(self, path: str) -> Any:
        def deco(fn):
            self._handlers.append(("PATCH", path, fn))
            return fn

        return deco

    def delete(self, path: str) -> Any:
        def deco(fn):
            self._handlers.append(("DELETE", path, fn))
            return fn

        return deco


class _MockRequest:
    def __init__(
        self, *, json_body: dict | None = None, query: dict | None = None, match_info: dict | None = None
    ):
        self._json = json_body
        self._query = query or {}
        self._match_info = match_info or {}

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
    for m, p, fn in module._server.routes._handlers:
        if m == method and p == path:
            return fn
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


def loader_capture() -> dict:
    return {
        "graph_json": {"id": "g1", "nodes": []},
        "api_prompt_json": {
            "workflow": {},
            "output": {
                "1": {
                    "class_type": "CheckpointLoaderSimple",
                    "inputs": {"ckpt_name": "krea_model.safetensors"},
                },
                "2": {"class_type": "SaveImage", "inputs": {"images": ["1", 0]}},
            },
        },
    }


class ModelLibraryRoutesTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.node_dir = self.base / "node"
        self.comfyui_root = self.base / "comfyui"

        self.routes_mod = _load_repo_module(
            "model_library_routes_under_test", "model_library_routes.py"
        )
        self.wf_routes_mod = _load_repo_module(
            "studio_workflow_routes_under_routes_test", "studio_workflow_routes.py"
        )

        stub = _StubServer()
        self.resolver = DependencyResolver(str(self.node_dir), str(self.comfyui_root))
        self.wf_routes_mod.register_workflow_routes(
            stub, node_dir=str(self.node_dir), resolver=self.resolver
        )
        self.routes_mod.register_model_library_routes(
            stub,
            node_dir=str(self.node_dir),
            comfyui_root=str(self.comfyui_root),
            resolver=self.resolver,
        )
        self.mod = type("RoutesModule", (), {"_server": stub})

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # ── helpers ──────────────────────────────────────────────────────────

    def _call(self, method: str, path: str, **req_kwargs):
        handler = _handler_for(self.mod, method, path)
        self.assertIsNotNone(handler, f"no route registered for {method} {path}")
        assert handler is not None
        return _run(handler(_MockRequest(**req_kwargs)))

    def _body(self, resp) -> dict:
        return json.loads(resp.body)

    def _write_model(self, folder: str, filename: str, content: bytes = b"contentA") -> Path:
        path = self.comfyui_root / "models" / folder / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def _import_workflow(self, **fields) -> tuple[dict, dict]:
        capture = loader_capture()
        body = {
            "name": "Routes WF",
            "graph_json": capture["graph_json"],
            "api_prompt_json": capture["api_prompt_json"],
            **fields,
        }
        resp = self._call("POST", "/comfymodal/studio/workflows/import", json_body=body)
        self.assertEqual(resp.status, 200, msg=resp.body)
        payload = self._body(resp)
        return payload["workflow"], payload["version"]

    def _write_library_store(self, records: list[dict], bom: bool = False) -> Path:
        payload = json.dumps(records, indent=2).encode("utf-8")
        if bom:
            payload = b"\xef\xbb\xbf" + payload
        path = self.node_dir / ".studio_model_library.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path

    # ── 19. models list + types routes ───────────────────────────────────

    def test_models_list_and_types_routes(self):
        resp = self._call("GET", "/comfymodal/studio/models")
        self.assertEqual(resp.status, 200)
        body = self._body(resp)
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["models"], [])
        self.assertEqual(body["total"], 0)
        self.assertEqual(body["scan_hint"], "not_scanned")

        resp = self._call("GET", "/comfymodal/studio/models/types")
        self.assertEqual(resp.status, 200)
        self.assertEqual(self._body(resp)["types"], MODEL_TYPES)

    # ── 20. rescan route returns a summary ───────────────────────────────

    def test_rescan_route_returns_summary(self):
        self._write_model("checkpoints", "krea_model.safetensors")
        resp = self._call("POST", "/comfymodal/studio/models/rescan", json_body={})
        self.assertEqual(resp.status, 200, msg=resp.body)
        summary = self._body(resp)["summary"]
        self.assertEqual(summary["added"], 1)
        self.assertEqual(summary["total"], 1)

        resp = self._call("GET", "/comfymodal/studio/models")
        body = self._body(resp)
        self.assertEqual(body["scan_hint"], "ok")
        self.assertEqual(len(body["models"]), 1)
        self.assertTrue(body["models"][0]["installed"])
        self.assertTrue(body["models"][0]["model_id"].startswith("ml_"))

        # force_rehash flag is accepted and re-hashes unchanged files.
        resp = self._call(
            "POST", "/comfymodal/studio/models/rescan", json_body={"force_rehash": True}
        )
        self.assertEqual(resp.status, 200, msg=resp.body)
        summary = self._body(resp)["summary"]
        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["hashed"], 1)
        self.assertEqual(summary["unchanged"] + summary["updated"], 1)

    # ── 21. patch model metadata route ───────────────────────────────────

    def test_patch_model_metadata_route(self):
        self._write_model("checkpoints", "krea_model.safetensors")
        self._call("POST", "/comfymodal/studio/models/rescan", json_body={})
        resp = self._call("GET", "/comfymodal/studio/models")
        model = self._body(resp)["models"][0]
        model_id = model["model_id"]

        resp = self._call(
            "PATCH",
            "/comfymodal/studio/models/{model_id}",
            match_info={"model_id": model_id},
            json_body={"notes": "hello", "tags": ["t1"], "display_name": "Krea"},
        )
        self.assertEqual(resp.status, 200, msg=resp.body)
        updated = self._body(resp)["model"]
        self.assertEqual(updated["notes"], "hello")
        self.assertEqual(updated["tags"], ["t1"])
        self.assertEqual(updated["display_name"], "Krea")
        self.assertTrue(updated["installed"])

        # Bad key → 400.
        resp = self._call(
            "PATCH",
            "/comfymodal/studio/models/{model_id}",
            match_info={"model_id": model_id},
            json_body={"hash": "tampered"},
        )
        self.assertEqual(resp.status, 400)
        self.assertEqual(self._body(resp)["status"], "error")

        # Unknown id → 404.
        resp = self._call(
            "PATCH",
            "/comfymodal/studio/models/{model_id}",
            match_info={"model_id": "ml_ghost"},
            json_body={"notes": "x"},
        )
        self.assertEqual(resp.status, 404)

    # ── 22. install-request route ────────────────────────────────────────

    def test_install_request_route_approved_and_validation(self):
        resp = self._call(
            "POST",
            "/comfymodal/studio/models/install-request",
            json_body={
                "folder": "checkpoints",
                "filename": "krea_model.safetensors",
                "url": "https://huggingface.co/org/repo/resolve/main/model.safetensors",
            },
        )
        self.assertEqual(resp.status, 200, msg=resp.body)
        body = self._body(resp)
        self.assertEqual(body["status"], "ok")
        self.assertTrue(body["request"]["approved"])
        self.assertEqual(body["request"]["source_kind"], "huggingface")
        self.assertIn("note", body)
        self.assertIn("install endpoint", body["note"])

        resp = self._call(
            "POST",
            "/comfymodal/studio/models/install-request",
            json_body={"folder": "nope", "filename": "a.safetensors", "url": "https://x.com/a"},
        )
        self.assertEqual(resp.status, 400)
        self.assertEqual(self._body(resp)["status"], "error")

    # ── 23. custom-nodes list + refresh routes ───────────────────────────

    def test_custom_nodes_list_and_refresh_routes(self):
        resp = self._call("GET", "/comfymodal/studio/custom-nodes")
        self.assertEqual(resp.status, 200, msg=resp.body)
        body = self._body(resp)
        self.assertEqual(body["status"], "ok")
        self.assertIn("custom_nodes", body)
        self.assertIn("core_classes", body)

        resp = self._call("POST", "/comfymodal/studio/custom-nodes/refresh")
        self.assertEqual(resp.status, 200, msg=resp.body)
        self.assertIn("custom_nodes", self._body(resp))

        resp = self._call(
            "POST",
            "/comfymodal/studio/custom-nodes/install-request",
            json_body={"name": "ComfyUI-KJNodes", "repo_url": "https://github.com/x/y", "revision": "abc"},
        )
        self.assertEqual(resp.status, 200, msg=resp.body)
        request = self._body(resp)["request"]
        self.assertTrue(request["approved"])
        self.assertEqual(request["name"], "ComfyUI-KJNodes")

    # ── 24. dependencies route shape ─────────────────────────────────────

    def test_dependencies_route_shape(self):
        _workflow, version = self._import_workflow()
        version_id = version["workflow_version_id"]

        resp = self._call(
            "GET",
            "/comfymodal/studio/workflows/versions/{version_id}/dependencies",
            match_info={"version_id": version_id},
        )
        self.assertEqual(resp.status, 200, msg=resp.body)
        body = self._body(resp)
        self.assertEqual(body["version_id"], version_id)
        self.assertIn("models", body)
        self.assertIn("custom_nodes", body)
        self.assertIn("summary", body)
        summary = body["summary"]
        self.assertGreater(summary["attention"], 0)
        self.assertFalse(summary["ready"])
        self.assertTrue(
            any(
                m["filename"] == "krea_model.safetensors" and m["state"] == "missing"
                for m in body["models"]
            )
        )

        # Unknown version → 404.
        resp = self._call(
            "GET",
            "/comfymodal/studio/workflows/versions/{version_id}/dependencies",
            match_info={"version_id": "wv_ghost"},
        )
        self.assertEqual(resp.status, 404)

    # ── 25. compatibility patch rejects frozen-incompatible models ───────

    def test_compatibility_patch_rejects_incompatible_frozen_model(self):
        _workflow, version = self._import_workflow(
            compatible_models=["krea_model.safetensors"]
        )
        version_id = version["workflow_version_id"]

        # Reject marking a frozen compatible model incompatible.
        resp = self._call(
            "PATCH",
            "/comfymodal/studio/workflows/versions/{version_id}/compatibility",
            match_info={"version_id": version_id},
            json_body={
                "model_name": "krea_model.safetensors",
                "status": "incompatible",
                "note": "nope",
            },
        )
        self.assertEqual(resp.status, 400)
        message = self._body(resp)["message"]
        self.assertIn(
            "cannot mark incompatible a model in the frozen compatible list", message
        )

        # Invalid status → 400.
        resp = self._call(
            "PATCH",
            "/comfymodal/studio/workflows/versions/{version_id}/compatibility",
            match_info={"version_id": version_id},
            json_body={"model_name": "x.safetensors", "status": "banana"},
        )
        self.assertEqual(resp.status, 400)

        # Annotations accepted for other models.
        resp = self._call(
            "PATCH",
            "/comfymodal/studio/workflows/versions/{version_id}/compatibility",
            match_info={"version_id": version_id},
            json_body={
                "model_name": "other.safetensors",
                "status": "untested",
                "note": "needs test",
            },
        )
        self.assertEqual(resp.status, 200, msg=resp.body)
        annotations = self._body(resp)["annotations"]
        self.assertEqual(annotations["other.safetensors"]["status"], "untested")

        # GET derived sections.
        resp = self._call(
            "GET",
            "/comfymodal/studio/workflows/versions/{version_id}/compatibility",
            match_info={"version_id": version_id},
        )
        self.assertEqual(resp.status, 200)
        body = self._body(resp)
        self.assertEqual(
            [c["model"] for c in body["compatible"]], ["krea_model.safetensors"]
        )
        self.assertEqual([u["model"] for u in body["untested"]], ["other.safetensors"])
        self.assertEqual(body["incompatible"], [])

    # ── 26. import response contains dependency_summary ──────────────────

    def test_import_response_contains_dependency_summary(self):
        resp = self._call(
            "POST",
            "/comfymodal/studio/workflows/import",
            json_body={
                "name": "Dep WF",
                "graph_json": loader_capture()["graph_json"],
                "api_prompt_json": loader_capture()["api_prompt_json"],
            },
        )
        self.assertEqual(resp.status, 200, msg=resp.body)
        body = self._body(resp)
        self.assertIn("dependency_summary", body)
        summary = body["dependency_summary"]
        self.assertIn("models", summary)
        self.assertGreater(len(summary["models"]), 0)
        self.assertIn("custom_nodes", summary)
        self.assertIn("summary", summary)

    # ── 27. models list reads tolerate a UTF-8 BOM store ──────────────────

    def test_models_list_200_with_bom_store(self):
        self._write_library_store(
            [
                {
                    "model_id": "ml_bom_1",
                    "folder": "checkpoints",
                    "filename": "krea_model.safetensors",
                    "display_name": "krea_model",
                    "model_type": "checkpoint",
                    "local_path": "",
                    "hash": "abc",
                    "size": 0,
                }
            ],
            bom=True,
        )
        resp = self._call("GET", "/comfymodal/studio/models")
        self.assertEqual(resp.status, 200)
        body = self._body(resp)
        self.assertEqual(body["status"], "ok")
        self.assertEqual(len(body["models"]), 1)
        self.assertEqual(body["models"][0]["model_id"], "ml_bom_1")
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["scan_hint"], "ok")

    # NOTE: test 4 (missing store → 200, models:[], scan_hint:"not_scanned")
    # is already covered exactly by test_models_list_and_types_routes (line
    # ~209): it asserts status 200, models [], total 0, scan_hint
    # "not_scanned". Skipped as a duplicate.

    # ── 28. corrupt store degrades to scan_hint "unavailable", no rewrite ─

    def test_models_list_200_corrupt_store_no_rescan(self):
        store_path = self.node_dir / ".studio_model_library.json"
        store_path.parent.mkdir(parents=True, exist_ok=True)
        store_path.write_bytes(b"\x00\x01garbage")

        resp = self._call("GET", "/comfymodal/studio/models")
        self.assertEqual(resp.status, 200)
        body = self._body(resp)
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["models"], [])
        self.assertEqual(body["total"], 0)
        self.assertEqual(body["scan_hint"], "unavailable")

        # The read must not rewrite/scan the store: the garbage stays intact.
        self.assertEqual(store_path.read_bytes(), b"\x00\x01garbage")

    # ── 29. dependencies route tolerates a BOM-prefixed store ─────────────

    def test_dependencies_200_with_bom_store(self):
        _workflow, version = self._import_workflow()
        version_id = version["workflow_version_id"]
        self._write_library_store([], bom=True)

        resp = self._call(
            "GET",
            "/comfymodal/studio/workflows/versions/{version_id}/dependencies",
            match_info={"version_id": version_id},
        )
        self.assertEqual(resp.status, 200, msg=resp.body)
        body = self._body(resp)
        self.assertEqual(body["status"], "ok")
        self.assertIn("models", body)
        self.assertIn("custom_nodes", body)
        self.assertIn("summary", body)
        # The referenced model is absent from the (BOM, empty) store, so the
        # version can never report "everything installed".
        self.assertFalse(body["summary"]["ready"])
        self.assertTrue(
            any(
                m["filename"] == "krea_model.safetensors" and m["state"] == "missing"
                for m in body["models"]
            )
        )

        # Unknown version still → 404.
        resp = self._call(
            "GET",
            "/comfymodal/studio/workflows/versions/{version_id}/dependencies",
            match_info={"version_id": "wv_ghost"},
        )
        self.assertEqual(resp.status, 404)

    # ── 30. dependencies fall back to the owning Workflow static graph ────

    @staticmethod
    def _parent_graph_only_static_graph() -> dict:
        """Workflow static graph holding UI-only classes absent from the
        version's executable prompt (the live Manager-missing shape)."""
        return {
            "nodes": [
                {
                    "id": 1,
                    "type": "BlehSetSamplerPreset",
                    "properties": {"cnr_id": "bleh", "ver": "1.2.3"},
                    "inputs": [{"name": "value", "link": None}],
                    "outputs": [{"name": "PRESET"}],
                },
                {
                    "id": 2,
                    "type": "KreaSeedVarianceEnhancer",
                    "properties": {"aux_id": "Krea/krea-seed", "ver": "0.4.0"},
                    "inputs": [{"name": "model", "link": None}],
                    "outputs": [{"name": "MODEL"}],
                },
                {
                    # Workflow-only virtual panel: empty inputs/outputs and no
                    # pack identity, so it must never become a missing row.
                    "id": 3,
                    "type": "WorkflowOnlyPanel",
                    "properties": {},
                    "inputs": [],
                    "outputs": [],
                },
            ]
        }

    def _stored_version(self, version_id: str) -> dict:
        path = self.node_dir / ".studio_workflow_versions.json"
        records = json.loads(path.read_text(encoding="utf-8"))
        return next(
            r for r in records if r.get("workflow_version_id") == version_id
        )

    @pytest.mark.fast_unit
    def test_dependencies_merge_parent_workflow_static_graph(self):
        """When the version has no full UI graph, the owning Workflow's
        static_graph supplies the graph-only classes (CNR/aux identity kept,
        virtual panels excluded) without mutating the version store."""
        parent = self._parent_graph_only_static_graph()
        _workflow, version = self._import_workflow(static_graph=parent)
        version_id = version["workflow_version_id"]

        resp = self._call(
            "GET",
            "/comfymodal/studio/workflows/versions/{version_id}/dependencies",
            match_info={"version_id": version_id},
        )
        self.assertEqual(resp.status, 200, msg=resp.body)
        rows = self._body(resp)["custom_nodes"]

        bleh = [n for n in rows if n.get("cnr_id") == "bleh"]
        self.assertEqual(len(bleh), 1, "graph-only CNR pack groups into one row")
        self.assertEqual(bleh[0]["state"], "missing")
        self.assertIn("BlehSetSamplerPreset", bleh[0]["classes"])

        krea = [n for n in rows if n.get("aux_id") == "Krea/krea-seed"]
        self.assertEqual(len(krea), 1, "graph-only aux pack groups into one row")
        self.assertEqual(krea[0]["state"], "missing")
        self.assertIn("KreaSeedVarianceEnhancer", krea[0]["classes"])

        classes = [c for n in rows for c in n["classes"]]
        self.assertNotIn(
            "WorkflowOnlyPanel", classes, "virtual panel must never be a dependency"
        )

        # The persisted version is untouched: the parent graph is merged into a
        # copy used only for resolution.
        self.assertNotIn("static_graph", self._stored_version(version_id))

    @pytest.mark.fast_unit
    def test_dependencies_merge_parent_graph_with_nonempty_version_graph(self):
        """A version with its own top-level graph still merges the owning
        Workflow's static_graph: the version graph stays authoritative for
        duplicate classes while parent-only nested classes and model widgets
        remain resolvable. The stored version is never mutated."""
        version_graph = {
            "id": "v",
            "nodes": [
                {
                    "id": 1,
                    "type": "UNETLoader",
                    "properties": {"cnr_id": "versionpack"},
                    "inputs": [{"name": "unet_name", "link": None}],
                    "outputs": [{"name": "MODEL"}],
                    "widgets_values_named": {"unet_name": "version_model.safetensors"},
                },
                {
                    "id": 2,
                    "type": "DupNode",
                    "properties": {"cnr_id": "versionpack"},
                    "inputs": [{"name": "x", "link": None}],
                    "outputs": [{"name": "Y"}],
                },
            ],
        }
        parent = {
            "nodes": [
                {
                    # The version graph already carries this class: version
                    # identity must win for the duplicate.
                    "id": 2,
                    "type": "DupNode",
                    "properties": {"cnr_id": "parentpack"},
                    "inputs": [{"name": "x", "link": None}],
                    "outputs": [{"name": "Y"}],
                },
            ],
            "definitions": {
                "subgraphs": [
                    {
                        "id": "sg",
                        "nodes": [
                            {
                                "id": 10,
                                "type": "UNETLoader",
                                "properties": {"cnr_id": "parentpack"},
                                "inputs": [{"name": "unet_name", "link": None}],
                                "outputs": [{"name": "MODEL"}],
                                "widgets_values_named": {
                                    "unet_name": "parent_nested_model.safetensors"
                                },
                            },
                            {
                                "id": 11,
                                "type": "ParentNestedNode",
                                "properties": {"cnr_id": "parentpack"},
                                "inputs": [{"name": "x", "link": None}],
                                "outputs": [{"name": "Y"}],
                            },
                        ],
                    }
                ]
            },
        }
        _workflow, version = self._import_workflow(
            graph_json=version_graph, static_graph=parent
        )
        version_id = version["workflow_version_id"]

        resp = self._call(
            "GET",
            "/comfymodal/studio/workflows/versions/{version_id}/dependencies",
            match_info={"version_id": version_id},
        )
        self.assertEqual(resp.status, 200, msg=resp.body)
        body = self._body(resp)

        filenames = {m["filename"] for m in body["models"]}
        self.assertIn("version_model.safetensors", filenames)
        self.assertIn(
            "parent_nested_model.safetensors",
            filenames,
            "parent-only nested model widget must be resolved",
        )

        rows = body["custom_nodes"]
        classes = [c for n in rows for c in n["classes"]]
        self.assertIn("DupNode", classes)
        self.assertIn("ParentNestedNode", classes)
        dup = [n for n in rows if "DupNode" in n["classes"]]
        self.assertEqual(len(dup), 1, "duplicate class resolves to one row")
        self.assertEqual(
            dup[0]["cnr_id"], "versionpack", "version class identity wins"
        )

        # The persisted version is untouched: the parent graph is merged into a
        # copy used only for resolution.
        self.assertNotIn("static_graph", self._stored_version(version_id))

    # ── 30b. parent fallback reaches nested graph nodes ──────────────────

    @staticmethod
    def _nested_parent_static_graph() -> dict:
        """Parent static graph whose real nodes live only inside nested
        subgraph/group containers (the live Manager-missing shape)."""
        return {
            "nodes": [],
            "definitions": {
                "subgraphs": [
                    {
                        "id": "sg",
                        "nodes": [
                            {
                                "id": 1,
                                "type": "NestedAlphaNode",
                                "properties": {"cnr_id": "nested-pack", "ver": "1.2.3"},
                                "inputs": [{"name": "x", "link": None}],
                                "outputs": [{"name": "Y"}],
                            },
                            {
                                "id": 2,
                                "type": "NestedBetaNode",
                                "properties": {"aux_id": "owner/nested-beta"},
                                "inputs": [{"name": "m", "link": None}],
                                "outputs": [{"name": "MODEL"}],
                            },
                            {
                                # Nested virtual panel: must never be a row.
                                "id": 3,
                                "type": "NestedPanel",
                                "properties": {},
                                "inputs": [],
                                "outputs": [],
                            },
                        ],
                    }
                ]
            },
            "extra": {
                "groupNodes": {
                    "g": {
                        "nodes": [
                            {
                                "id": 4,
                                "type": "NestedGammaNode",
                                "properties": {"cnr_id": "nested-pack"},
                                "inputs": [{"name": "x", "link": None}],
                                "outputs": [{"name": "Y"}],
                            }
                        ]
                    }
                }
            },
        }

    @pytest.mark.fast_unit
    def test_dependencies_merge_nested_parent_static_graph(self):
        """The parent Workflow's static_graph fallback reaches nodes nested in
        subgraph/group containers; identities group and virtual panels stay out
        without mutating the version store."""
        parent = self._nested_parent_static_graph()
        _workflow, version = self._import_workflow(static_graph=parent)
        version_id = version["workflow_version_id"]

        resp = self._call(
            "GET",
            "/comfymodal/studio/workflows/versions/{version_id}/dependencies",
            match_info={"version_id": version_id},
        )
        self.assertEqual(resp.status, 200, msg=resp.body)
        rows = self._body(resp)["custom_nodes"]
        classes = [c for n in rows for c in n["classes"]]
        self.assertIn("NestedAlphaNode", classes)
        self.assertIn("NestedBetaNode", classes)
        self.assertIn("NestedGammaNode", classes)

        pack = [n for n in rows if n.get("cnr_id") == "nested-pack"]
        self.assertEqual(len(pack), 1, "nested classes sharing cnr_id group into one row")
        self.assertEqual(pack[0]["state"], "missing")
        self.assertEqual(
            sorted(pack[0]["classes"]), ["NestedAlphaNode", "NestedGammaNode"]
        )
        beta = [n for n in rows if n.get("aux_id") == "owner/nested-beta"]
        self.assertEqual(len(beta), 1)
        self.assertIn("NestedBetaNode", beta[0]["classes"])
        self.assertNotIn("NestedPanel", classes)
        self.assertNotIn("static_graph", self._stored_version(version_id))


if __name__ == "__main__":
    unittest.main()
