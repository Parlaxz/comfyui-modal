"""Backend-focused tests for the single-output run-history save action.

Covers the implementation behind ``POST /comfymodal/run-history/{run_id}/save``:

- adapter-level ``studio_run_adapter.save_run_history_output``:
    * idempotent retries (no duplicate files)
    * metadata/settings parity (folder/format/quality/WebP/sidecar)
    * selected output only (``output_index``)
    * failure state (missing run/output, empty file, state-persist failure)
- route-level validation (stub ``_server`` load of ``__init__.py``):
    * method/path registration
    * invalid bodies, invalid ``output_index``, unknown run
    * happy path persists ``extra.output_saved`` in the authoritative meta

Non-deploying: never invokes Modal, never generates images via a remote run
(only tiny local PNG fixtures via Pillow when available).
"""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _load_module(name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel_path)
    assert spec is not None, f"Could not find spec for {rel_path}"
    assert spec.loader is not None, f"Could not find loader for {rel_path}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _make_png_bytes(color=(180, 40, 40), size=(8, 8)) -> bytes:
    """Create tiny real PNG bytes (not fabricated image payloads)."""
    try:
        from PIL import Image
    except ImportError:
        # Minimal 1x1 transparent-ish PNG literal so tests still work
        # without Pillow for byte-identity checks.
        import base64
        return base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
            "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        )
    import io
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _write_png(path: Path, color=(180, 40, 40)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_make_png_bytes(color=color))
    return path


def _save_with_state(adapter, svc, run_id, output_index=0, **kwargs):
    """Mimic the route flow: read authoritative meta, save, persist state."""
    meta = svc.get_run(run_id)

    def _persist(state: dict) -> None:
        svc.update_run(run_id, meta=state)

    return adapter.save_run_history_output(
        meta,
        output_index=output_index,
        persist_state_fn=_persist,
        **kwargs,
    )


def _count_images(save_root: Path) -> int:
    images_dir = save_root / "images"
    if not images_dir.is_dir():
        return 0
    return len([p for p in images_dir.iterdir() if p.is_file()])


# ===========================================================================
# Adapter-level tests
# ===========================================================================

class RunHistorySaveAdapterTests(unittest.TestCase):
    """Idempotency, settings parity, selected output, failure state."""

    @classmethod
    def setUpClass(cls):
        cls.adapter = _load_module("studio_run_adapter", "studio_run_adapter.py")
        cls.svc_mod = _load_module("experiment_service", "experiment_service.py")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "run_history"
        self.root.mkdir(parents=True, exist_ok=True)
        self.save_root = Path(self.tmp.name) / "save"
        self.outputs_root = Path(self.tmp.name) / "outputs"
        self.outputs_root.mkdir(parents=True, exist_ok=True)
        self.svc = self.svc_mod.RunHistoryService(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def _record(self, output_path: str = "", extra: dict | None = None, kind="studio_run"):
        meta = dict(extra or {})
        if output_path:
            meta.setdefault("output_paths", [output_path])
        rec = self.svc.record_run(
            kind=kind,
            prompt_id="exp_save",
            status="completed",
            output_path=output_path,
            meta=meta,
            workflow_hash="wh_save_test",
        )
        return rec["run_id"]

    # ── Idempotent retries ────────────────────────────────────────────────

    def test_retry_after_success_returns_same_path_no_duplicate(self):
        src = _write_png(self.outputs_root / "out_a.png")
        run_id = self._record(str(src), extra={"resolved_controls": {"seed": 7}})

        first = _save_with_state(
            self.adapter, self.svc, run_id,
            output_format="original", save_folder=str(self.save_root),
        )
        self.assertEqual(first["status"], "ok")
        self.assertTrue(first["saved"])
        self.assertFalse(first["already_saved"])
        self.assertTrue(first["path"])
        self.assertEqual(_count_images(self.save_root), 1)

        second = _save_with_state(
            self.adapter, self.svc, run_id,
            output_format="original", save_folder=str(self.save_root),
        )
        self.assertEqual(second["status"], "ok")
        self.assertTrue(second["saved"])
        self.assertTrue(second["already_saved"])
        self.assertEqual(second["path"], first["path"])
        # No duplicate file was written.
        self.assertEqual(_count_images(self.save_root), 1)

    def test_meta_state_persisted_after_save(self):
        src = _write_png(self.outputs_root / "out_b.png")
        run_id = self._record(str(src))
        _save_with_state(
            self.adapter, self.svc, run_id,
            output_format="original", save_folder=str(self.save_root),
        )
        meta = self.svc.get_run(run_id)
        extra = meta.get("extra", {})
        self.assertIs(extra.get("output_saved"), True)
        self.assertEqual(extra.get("output_saved_index"), 0)
        self.assertTrue(extra.get("output_saved_path"))
        self.assertTrue(extra.get("output_saved_at"))
        # Frontend relies on raw.extra.output_saved === true.
        self.assertIs(extra.get("output_saved"), True)

    def test_idempotency_gate_short_circuits_without_persist_fn(self):
        """A record already marked saved returns the recorded path even when
        the caller supplies no persist callback (pure replay path)."""
        src = _write_png(self.outputs_root / "out_c.png")
        run_id = self._record(str(src), extra={
            "output_saved": True,
            "output_saved_index": 0,
            "output_saved_path": str(src),
        })
        result = self.adapter.save_run_history_output(
            self.svc.get_run(run_id),
            output_index=0,
            save_folder=str(self.save_root),
        )
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["already_saved"])
        self.assertEqual(result["path"], str(src))
        self.assertEqual(_count_images(self.save_root), 0)

    def test_deleted_recorded_file_allows_resave(self):
        """If the previously recorded file is gone, a retry may save again."""
        src = _write_png(self.outputs_root / "out_d.png")
        run_id = self._record(str(src), extra={
            "output_saved": True,
            "output_saved_index": 0,
            "output_saved_path": str(self.outputs_root / "gone.png"),
        })
        result = _save_with_state(
            self.adapter, self.svc, run_id,
            output_format="original", save_folder=str(self.save_root),
        )
        self.assertEqual(result["status"], "ok")
        self.assertFalse(result["already_saved"])
        self.assertTrue(result["path"])
        self.assertEqual(_count_images(self.save_root), 1)

    # ── Metadata / settings parity ────────────────────────────────────────

    def test_original_format_copies_bytes_and_records_original(self):
        src = _write_png(self.outputs_root / "orig.png")
        src_bytes = src.read_bytes()
        run_id = self._record(str(src))
        result = _save_with_state(
            self.adapter, self.svc, run_id,
            output_format="original", save_folder=str(self.save_root),
        )
        self.assertEqual(result["status"], "ok")
        saved = Path(result["path"])
        self.assertEqual(saved.suffix.lower(), ".png")
        self.assertEqual(saved.read_bytes(), src_bytes)
        meta = json.loads(Path(result["metadata_path"]).read_text(encoding="utf-8"))
        self.assertEqual(meta["output_format"], "original")
        self.assertIsNone(meta["quality"])
        self.assertIsNone(meta["webp_lossless_compression"])
        self.assertEqual(meta["mime_type"], "image/png")

    def test_webp_lossy_settings_parity(self):
        src = _write_png(self.outputs_root / "wl.png")
        run_id = self._record(str(src))
        result = _save_with_state(
            self.adapter, self.svc, run_id,
            output_format="webp_lossy", quality=40,
            webp_lossless_compression="balanced",
            save_folder=str(self.save_root),
        )
        self.assertEqual(result["status"], "ok")
        saved = Path(result["path"])
        self.assertEqual(saved.suffix.lower(), ".webp")
        head = saved.read_bytes()[:12]
        self.assertTrue(head[:4] == b"RIFF" and b"WEBP" in head, "saved bytes are not WebP")
        meta = json.loads(Path(result["metadata_path"]).read_text(encoding="utf-8"))
        self.assertEqual(meta["output_format"], "webp_lossy")
        self.assertEqual(meta["quality"], 40)
        self.assertIsNone(meta["webp_lossless_compression"])
        self.assertEqual(meta["mime_type"], "image/webp")

    def test_jpeg_settings_parity(self):
        src = _write_png(self.outputs_root / "jp.png")
        run_id = self._record(str(src))
        result = _save_with_state(
            self.adapter, self.svc, run_id,
            output_format="jpeg", quality=80,
            webp_lossless_compression="balanced",
            save_folder=str(self.save_root),
        )
        self.assertEqual(result["status"], "ok")
        saved = Path(result["path"])
        self.assertEqual(saved.suffix.lower(), ".jpg")
        self.assertEqual(saved.read_bytes()[:3], b"\xff\xd8\xff")
        meta = json.loads(Path(result["metadata_path"]).read_text(encoding="utf-8"))
        self.assertEqual(meta["output_format"], "jpeg")
        self.assertEqual(meta["quality"], 80)
        self.assertEqual(meta["mime_type"], "image/jpeg")

    def test_webp_lossless_settings_parity(self):
        src = _write_png(self.outputs_root / "wl_l.png")
        run_id = self._record(str(src))
        result = _save_with_state(
            self.adapter, self.svc, run_id,
            output_format="webp_lossless", quality=75,
            webp_lossless_compression="max",
            save_folder=str(self.save_root),
        )
        self.assertEqual(result["status"], "ok")
        saved = Path(result["path"])
        self.assertEqual(saved.suffix.lower(), ".webp")
        meta = json.loads(Path(result["metadata_path"]).read_text(encoding="utf-8"))
        self.assertEqual(meta["output_format"], "webp_lossless")
        self.assertIsNone(meta["quality"])
        self.assertEqual(meta["webp_lossless_compression"], "max")

    def test_sidecar_disabled_writes_no_metadata_file(self):
        src = _write_png(self.outputs_root / "noside.png")
        run_id = self._record(str(src))
        result = _save_with_state(
            self.adapter, self.svc, run_id,
            output_format="original", save_folder=str(self.save_root),
            save_metadata_sidecar=False,
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["metadata_path"], "")
        metadata_dir = self.save_root / "metadata"
        if metadata_dir.is_dir():
            self.assertEqual(len(list(metadata_dir.iterdir())), 0)

    def test_configured_save_folder_is_used(self):
        src = _write_png(self.outputs_root / "folder.png")
        run_id = self._record(str(src))
        result = _save_with_state(
            self.adapter, self.svc, run_id,
            output_format="original", save_folder=str(self.save_root),
        )
        self.assertEqual(result["status"], "ok")
        saved = Path(result["path"])
        self.assertTrue(str(self.save_root / "images") in str(saved.parent))
        # Sidecar lands in the same configured folder root.
        self.assertIn(str(self.save_root / "metadata"), result["metadata_path"])

    # ── Selected output only ──────────────────────────────────────────────

    def test_selected_output_index_saves_only_that_output(self):
        src_a = _write_png(self.outputs_root / "sel_a.png", color=(200, 20, 20))
        src_b = _write_png(self.outputs_root / "sel_b.png", color=(20, 200, 20))
        run_id = self._record("", extra={"output_paths": [str(src_a), str(src_b)]})

        result0 = _save_with_state(
            self.adapter, self.svc, run_id, output_index=0,
            output_format="original", save_folder=str(self.save_root),
        )
        self.assertEqual(result0["status"], "ok")
        saved0 = Path(result0["path"])
        self.assertEqual(saved0.read_bytes(), src_a.read_bytes())

        result1 = _save_with_state(
            self.adapter, self.svc, run_id, output_index=1,
            output_format="original", save_folder=str(self.save_root),
        )
        self.assertEqual(result1["status"], "ok")
        saved1 = Path(result1["path"])
        self.assertEqual(saved1.read_bytes(), src_b.read_bytes())

        meta = self.svc.get_run(run_id)
        self.assertEqual(meta["extra"]["output_saved_index"], 1)

    def test_out_of_range_output_index_errors(self):
        src = _write_png(self.outputs_root / "oor.png")
        run_id = self._record("", extra={"output_paths": [str(src)]})
        result = _save_with_state(
            self.adapter, self.svc, run_id, output_index=5,
            save_folder=str(self.save_root),
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["reason"], "output_unresolved")

    # ── Experiment-cell records (asset-registry resolution) ───────────────

    def test_experiment_cell_record_resolves_asset_via_resolver(self):
        """Experiment-cell records carry asset IDs, not paths; the injected
        resolver maps them to the materialised local file."""
        src = _write_png(self.outputs_root / "cell.png")
        run_id = self._record(
            "", extra={"primary_asset_id": "cell-1", "asset_ids": ["cell-1"]},
            kind="experiment_cell",
        )
        resolver = {"cell-1": {
            "asset_id": "cell-1", "variant": "original", "path": str(src),
        }}
        result = _save_with_state(
            self.adapter, self.svc, run_id, output_index=0,
            output_format="original", save_folder=str(self.save_root),
            asset_resolver_fn=lambda aid: resolver.get(aid),
        )
        self.assertEqual(result["status"], "ok")
        saved = Path(result["path"])
        self.assertEqual(saved.read_bytes(), src.read_bytes())
        self.assertEqual(result["source_path"], str(src))

    def test_experiment_cell_thumbnail_repoints_to_parent_original(self):
        """A thumbnail asset record is re-pointed at its parent original."""
        src = _write_png(self.outputs_root / "cell_orig.png")
        run_id = self._record(
            "", extra={"primary_asset_id": "cell-thumb-1",
                       "asset_ids": ["cell-thumb-1"]},
            kind="experiment_cell",
        )
        resolver = {
            "cell-thumb-1": {
                "asset_id": "cell-thumb-1", "variant": "thumbnail",
                "path": str(self.outputs_root / "thumb.webp"),
                "parent_asset_id": "cell-orig-1",
            },
            "cell-orig-1": {
                "asset_id": "cell-orig-1", "variant": "original",
                "path": str(src),
            },
        }
        result = _save_with_state(
            self.adapter, self.svc, run_id, output_index=0,
            output_format="original", save_folder=str(self.save_root),
            asset_resolver_fn=lambda aid: resolver.get(aid),
        )
        self.assertEqual(result["status"], "ok")
        saved = Path(result["path"])
        self.assertEqual(saved.read_bytes(), src.read_bytes())

    def test_experiment_cell_without_resolver_errors(self):
        run_id = self._record(
            "", extra={"primary_asset_id": "cell-2", "asset_ids": ["cell-2"]},
            kind="experiment_cell",
        )
        result = _save_with_state(
            self.adapter, self.svc, run_id, save_folder=str(self.save_root),
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["reason"], "output_unresolved")

    def test_experiment_cell_remote_only_asset_errors(self):
        run_id = self._record(
            "", extra={"primary_asset_id": "cell-3", "asset_ids": ["cell-3"]},
            kind="experiment_cell",
        )
        resolver = {"cell-3": {
            "asset_id": "cell-3", "variant": "original",
            "path": "modal://ws|gpu|/remote/out.png",
        }}
        result = _save_with_state(
            self.adapter, self.svc, run_id, output_index=0,
            save_folder=str(self.save_root),
            asset_resolver_fn=lambda aid: resolver.get(aid),
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["reason"], "output_unresolved")

    # ── Failure state ─────────────────────────────────────────────────────

    def test_run_without_output_errors(self):
        run_id = self._record("", extra={})
        result = _save_with_state(
            self.adapter, self.svc, run_id, save_folder=str(self.save_root),
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["reason"], "output_unresolved")

    def test_missing_output_file_errors(self):
        run_id = self._record(str(self.outputs_root / "missing.png"))
        result = _save_with_state(
            self.adapter, self.svc, run_id, save_folder=str(self.save_root),
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["reason"], "output_missing")

    def test_empty_output_file_errors(self):
        empty = self.outputs_root / "empty.png"
        empty.write_bytes(b"")
        run_id = self._record(str(empty))
        result = _save_with_state(
            self.adapter, self.svc, run_id, save_folder=str(self.save_root),
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["reason"], "output_empty")
        self.assertEqual(_count_images(self.save_root), 0)

    def test_non_image_output_type_errors(self):
        txt = self.outputs_root / "notes.txt"
        txt.write_text("not an image", encoding="utf-8")
        run_id = self._record(str(txt))
        result = _save_with_state(
            self.adapter, self.svc, run_id, save_folder=str(self.save_root),
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["reason"], "unsupported_output_type")
        self.assertEqual(_count_images(self.save_root), 0)

    def test_invalid_run_meta_errors(self):
        result = self.adapter.save_run_history_output(
            {"run_id": ""}, output_index=0, save_folder=str(self.save_root),
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["reason"], "invalid_run_meta")

    def test_state_persist_failure_surfaces_error_and_not_marked_saved(self):
        src = _write_png(self.outputs_root / "persist_fail.png")
        run_id = self._record(str(src))

        def _boom(state):
            raise RuntimeError("disk full")

        result = self.adapter.save_run_history_output(
            self.svc.get_run(run_id),
            output_index=0,
            output_format="original",
            save_folder=str(self.save_root),
            persist_state_fn=_boom,
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["reason"], "state_persist_failed")
        # The record must not be marked saved so a retry can recover.
        meta = self.svc.get_run(run_id)
        self.assertIsNot(meta.get("extra", {}).get("output_saved"), True)

    def test_saved_sidecar_carries_run_context(self):
        src = _write_png(self.outputs_root / "ctx.png")
        run_id = self._record(str(src), extra={
            "preset_label": "Cool Preset",
            "resolved_controls": {"seed": 42, "width": 512, "height": 640},
        })
        result = _save_with_state(
            self.adapter, self.svc, run_id,
            output_format="original", save_folder=str(self.save_root),
        )
        meta = json.loads(Path(result["metadata_path"]).read_text(encoding="utf-8"))
        self.assertEqual(meta["workflow_name"], "Cool Preset")
        self.assertEqual(meta["seed"], "42")
        self.assertEqual(meta["width"], 512)
        self.assertEqual(meta["height"], 640)
        self.assertEqual(meta["saved_via"], "run_history_save")


# ===========================================================================
# Route-level tests (stub _server load of __init__.py)
# ===========================================================================

class _StubRoutes:
    def __init__(self):
        self._handlers = []

    def get(self, path):
        def deco(fn):
            self._handlers.append(("GET", path, fn))
            return fn
        return deco

    def post(self, path):
        def deco(fn):
            self._handlers.append(("POST", path, fn))
            return fn
        return deco

    def put(self, path):
        def deco(fn):
            self._handlers.append(("PUT", path, fn))
            return fn
        return deco

    def delete(self, path):
        def deco(fn):
            self._handlers.append(("DELETE", path, fn))
            return fn
        return deco

    def patch(self, path):
        def deco(fn):
            self._handlers.append(("PATCH", path, fn))
            return fn
        return deco


class _StubServer:
    def __init__(self):
        self.routes = _StubRoutes()
        self.sent_events = []

    def send_sync(self, event, data, sid=""):
        self.sent_events.append((event, dict(data), sid))


class _MockRequest:
    def __init__(self, *, json_body=None, query=None, match_info=None):
        self._json = json_body
        self._query = query or {}
        self._match_info = match_info or {}
        self.body_exists = json_body is not None

    async def json(self):
        if self._json is None:
            raise ValueError("no body")
        return self._json

    @property
    def query(self):
        return self._query

    @property
    def match_info(self):
        return self._match_info


def _build_init_with_stub(stub_server, data_root: str):
    """Load __init__.py with a stubbed PromptServer and a temp data root."""
    server_stub = type(sys)("server")
    server_stub.PromptServer = type("PromptServer", (), {"instance": stub_server})
    sys.modules["server"] = server_stub
    exec_stub = type(sys)("execution")
    exec_stub.PromptQueue = type("PromptQueue", (), {})
    sys.modules["execution"] = exec_stub

    # Force the local data root to a temp dir BEFORE the module caches paths.
    from local_artifacts import _reset_caches_for_testing
    os.environ["COMFYMODAL_LOCAL_DATA_DIR"] = data_root
    _reset_caches_for_testing(data_root)

    for mod in ("local_placeholders", "workflow_metadata", "api_prompt_validator",
                "failure_summary", "output_converter", "output_saver",
                "timing_trace", "profiler_trace_v4", "production_workflow",
                "comparison", "model_manifest", "modal_workspaces",
                "modal_client", "gpu_catalog", "optimizations",
                "run_history", "presets", "matrix_compiler", "experiment_store",
                "experiment_lease", "experiment_models", "experiment_runner",
                "experiment_scheduler", "deploy_warmup", "experiment_service",
                "studio_store", "studio_models", "studio_routes",
                "studio_run_adapter"):
        if mod not in sys.modules:
            try:
                spec = importlib.util.spec_from_file_location(
                    mod, REPO_ROOT / f"{mod}.py"
                )
                if spec is None or spec.loader is None:
                    continue
                m = importlib.util.module_from_spec(spec)
                sys.modules[mod] = m
                spec.loader.exec_module(m)
            except Exception:
                pass
    spec = importlib.util.spec_from_file_location(
        "comfyui_modal_save_under_test", REPO_ROOT / "__init__.py"
    )
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["comfyui_modal_save_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def _handler_for(init_mod, method: str, path: str) -> Any:
    """Return the route handler for *method* + *path* (or None)."""
    handlers = init_mod._server.routes._handlers
    for m, p, fn in handlers:
        if m == method and p == path:
            return fn
    return None


def _run(coro):
    import asyncio
    return asyncio.run(coro)


class RunHistorySaveRouteTests(unittest.TestCase):
    """Route registration, validation, and happy-path save persistence."""

    @classmethod
    def setUpClass(cls):
        cls._data_tmp = tempfile.TemporaryDirectory()
        cls.stub = _StubServer()
        cls.init_mod = _build_init_with_stub(
            cls.stub, data_root=cls._data_tmp.name
        )
        # NOTE: do not cache the handler on the class — a class-attribute
        # function becomes a bound method via descriptor protocol, which
        # injects ``self`` and breaks direct calls.

    @classmethod
    def tearDownClass(cls):
        cls._data_tmp.cleanup()

    def _save_handler(self) -> Any:
        handler = _handler_for(
            self.init_mod, "POST", "/comfymodal/run-history/{run_id}/save"
        )
        assert handler is not None, "POST /save route not registered"
        return handler

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.save_root = Path(self.tmp.name) / "save"
        self.outputs_root = Path(self.tmp.name) / "outputs"
        self.outputs_root.mkdir(parents=True, exist_ok=True)
        # Hermetic save settings for every route test.
        self.settings_patcher = mock.patch.object(
            self.init_mod, "_load_modal_settings",
            return_value={
                "output_format": "original",
                "quality": 75,
                "webp_lossless_compression": "balanced",
                "save_folder": str(self.save_root),
                "save_metadata_sidecar": True,
            },
        )
        self.settings_patcher.start()

    def tearDown(self):
        self.settings_patcher.stop()
        self.tmp.cleanup()

    def _record_run(self, output_path: str, extra: dict | None = None) -> str:
        history = self.init_mod.REGISTRY.history()
        rec = history.record_run(
            kind="studio_run",
            prompt_id="exp_route_save",
            status="completed",
            output_path=output_path,
            meta=dict(extra or {}),
        )
        return rec["run_id"]

    def test_route_registered_as_post_only(self):
        handler = self._save_handler()
        self.assertIsNotNone(handler)
        get_handler = _handler_for(
            self.init_mod, "GET", "/comfymodal/run-history/{run_id}/save"
        )
        self.assertIsNone(get_handler, "save route must be POST-only")

    def test_invalid_json_body_returns_400(self):
        handler = self._save_handler()
        req = _MockRequest(json_body="not-a-dict", match_info={"run_id": "r_test1"})
        resp = _run(handler(req))
        self.assertEqual(resp.status, 400)
        self.assertIn("error", json.loads(resp.body)["status"])

    def test_invalid_output_index_returns_400(self):
        handler = self._save_handler()
        src = _write_png(self.outputs_root / "r_invalid.png")
        run_id = self._record_run(str(src), {"output_paths": [str(src)]})
        for bad in ("0", -1, 1.5, True, None):
            req = _MockRequest(
                json_body={"output_index": bad},
                match_info={"run_id": run_id},
            )
            resp = _run(handler(req))
            self.assertEqual(resp.status, 400, f"output_index={bad!r}")

    def test_unknown_run_returns_404(self):
        handler = self._save_handler()
        req = _MockRequest(
            json_body={"output_index": 0},
            match_info={"run_id": "r_does_not_exist_123"},
        )
        resp = _run(handler(req))
        self.assertEqual(resp.status, 404)

    def test_happy_path_saves_and_persists_meta_state(self):
        handler = self._save_handler()
        src = _write_png(self.outputs_root / "r_ok.png")
        run_id = self._record_run(str(src), {"output_paths": [str(src)]})

        req = _MockRequest(
            json_body={"output_index": 0},
            match_info={"run_id": run_id},
        )
        resp = _run(handler(req))
        self.assertEqual(resp.status, 200, msg=resp.body)
        body = json.loads(resp.body)
        self.assertEqual(body["status"], "ok")
        self.assertTrue(body["saved"])
        self.assertFalse(body["already_saved"])
        self.assertTrue(Path(body["path"]).is_file())

        # Saved state persisted into the authoritative source meta.
        meta = self.init_mod.REGISTRY.history().get_run(run_id)
        extra = meta.get("extra", {})
        self.assertIs(extra.get("output_saved"), True)
        self.assertEqual(extra.get("output_saved_path"), body["path"])

    def test_happy_path_is_idempotent_across_requests(self):
        handler = self._save_handler()
        src = _write_png(self.outputs_root / "r_idem.png")
        run_id = self._record_run(str(src), {"output_paths": [str(src)]})
        match_info = {"run_id": run_id}

        first = _run(handler(_MockRequest(
            json_body={"output_index": 0}, match_info=match_info,
        )))
        self.assertEqual(first.status, 200)
        first_body = json.loads(first.body)

        second = _run(handler(_MockRequest(
            json_body={"output_index": 0}, match_info=match_info,
        )))
        self.assertEqual(second.status, 200)
        second_body = json.loads(second.body)
        self.assertTrue(second_body["already_saved"])
        self.assertEqual(second_body["path"], first_body["path"])

        images_dir = self.save_root / "images"
        files = [p for p in images_dir.iterdir() if p.is_file()] if images_dir.is_dir() else []
        self.assertEqual(len(files), 1, "duplicate file written on retry")


if __name__ == "__main__":
    unittest.main()
