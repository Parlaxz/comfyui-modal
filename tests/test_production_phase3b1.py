"""Tests for Phase 3b1: direct-memory output sink and production request state.

Covers:
  - Module-level _PROD_DIRECT_SINK_REGISTRY and _PROD_DIRECT_SINK_REQUEST globals
  - ComfyModalProductionOutput node class definition and registration
  - Active production request state management in _execute_in_process
  - allow_direct_output_rewrite=True at all in-process compilation sites
  - Registry-first output collection in _collect_in_process_outputs
  - direct_output_sink_enabled / allow_direct_output_rewrite in production_report
"""

import unittest
import importlib.util
import sys
import types
import uuid
from pathlib import Path
from unittest.mock import MagicMock

from production_workflow import (
    _reset_cache,
    _cache_size,
    compile_production_workflow,
    normalize_production_options,
    COMPILER_SCHEMA_VERSION,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
COMFYAPP_PATH = REPO_ROOT / "comfyapp.py"
PRODWFLOW_PATH = REPO_ROOT / "production_workflow.py"


def _make_gpu_catalog_stub():
    stub = types.ModuleType("gpu_catalog")
    stub.GPU_CATALOG = []
    stub.get_supported_gpus = lambda: []
    stub.is_gpu_hidden = lambda v: False
    stub.get_default_gpu = lambda: "rtx-pro-6000"
    return stub


def _make_timing_trace_stub():
    stub = types.ModuleType("timing_trace")
    stub.Trace = type("Trace", (), {"__init__": lambda self, **kw: None, "mark": lambda self, *a, **kw: None, "fields": lambda self: {}, "update": lambda self, *a, **kw: None, "summary": lambda self: {}, "log_line": lambda self: ""})
    stub.coerce_t0_from_browser = lambda p: None
    return stub


def _make_modal_stub():
    stub = types.ModuleType("modal")
    stub.Image = MagicMock()
    stub.Image.debian_slim.return_value.apt_install.return_value.pip_install.return_value.run_commands.return_value = MagicMock()
    stub.App = MagicMock()
    stub.App.return_value.function = lambda **kw: (lambda f: f)
    stub.App.return_value.cls = lambda **kw: (lambda c: c)
    stub.Volume = MagicMock()
    stub.Volume.from_name.return_value = MagicMock()
    stub.Secret = MagicMock()
    stub.Secret.from_name.return_value = MagicMock()
    stub.web_server = lambda *a, **kw: (lambda f: f)
    stub.enter = lambda **kw: (lambda f: f)
    stub.exit = lambda: (lambda f: f)
    stub.method = lambda **kw: (lambda f: f)
    stub.concurrent = lambda **kw: (lambda c: c)
    return stub


def _load_comfyapp_module():
    original_modal = sys.modules.pop("modal", None)
    original_gpu_catalog = sys.modules.pop("gpu_catalog", None)
    original_timing_trace = sys.modules.pop("timing_trace", None)
    sys.modules["modal"] = _make_modal_stub()
    sys.modules["gpu_catalog"] = _make_gpu_catalog_stub()
    sys.modules["timing_trace"] = _make_timing_trace_stub()
    module_name = f"comfyapp_test_{uuid.uuid4().hex}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, str(COMFYAPP_PATH))
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if original_modal is not None:
            sys.modules["modal"] = original_modal
        else:
            sys.modules.pop("modal", None)
        if original_gpu_catalog is not None:
            sys.modules["gpu_catalog"] = original_gpu_catalog
        else:
            sys.modules.pop("gpu_catalog", None)
        if original_timing_trace is not None:
            sys.modules["timing_trace"] = original_timing_trace
        else:
            sys.modules.pop("timing_trace", None)
        sys.modules.pop(module_name, None)


def _minimal_production(output_ids=None, bypass_ids=None, **overrides):
    prod = {
        "schema_version": COMPILER_SCHEMA_VERSION,
        "output_node_ids": output_ids or ["9"],
        "bypass_node_ids": bypass_ids or [],
        "disable_sampler_previews": True,
        "quiet_execution_logs": True,
        "progress_min_interval_ms": 500,
        "strict_output_collection": True,
        "direct_output_sink": True,
        "metadata_mode": "none",
    }
    prod.update(overrides)
    return prod


# =========================================================================
# AST-based tests for comfyapp.py
# =========================================================================

class Phase3b1ComfyappAstTests(unittest.TestCase):
    """Source-level AST tests verifying Phase 3b1 production changes in
    comfyapp.py without importing the module (which requires ComfyUI runtime)."""

    def setUp(self):
        self.src = COMFYAPP_PATH.read_text(encoding="utf-8")

    # ── Module-level globals ──────────────────────────────────────────

    def test_PROD_DIRECT_SINK_REGISTRY_exists(self):
        self.assertIn("_PROD_DIRECT_SINK_REGISTRY", self.src)

    def test_PROD_DIRECT_SINK_REQUEST_exists(self):
        self.assertIn("_PROD_DIRECT_SINK_REQUEST", self.src)

    def test_PROD_DIRECT_SINK_REGISTRY_typed_dict(self):
        """Registry should be typed as dict[str, dict[str, list[dict]]]."""
        self.assertIn(
            "_PROD_DIRECT_SINK_REGISTRY: dict[str, dict[str, list[dict]]]",
            self.src,
        )

    # ── ComfyModalProductionOutput node class ─────────────────────────

    def test_ComfyModalProductionOutput_class_defined(self):
        self.assertIn("class ComfyModalProductionOutput", self.src)

    def test_ComfyModalProductionOutput_category(self):
        self.assertIn('CATEGORY = "_for_internal_use/ComfyModal"', self.src)

    def test_ComfyModalProductionOutput_encode_method(self):
        self.assertIn("def encode(self,", self.src)

    def test_ComfyModalProductionOutput_encode_stores_in_registry(self):
        """encode() must write into _PROD_DIRECT_SINK_REGISTRY."""
        self.assertIn("registry = _PROD_DIRECT_SINK_REGISTRY", self.src)
        self.assertIn("registry[prompt_id]", self.src)

    def test_ComfyModalProductionOutput_encode_returns_safe_empty_tuple(self):
        """encode() should return () — a safe empty tuple, not a dict payload
        that could be misinterpreted by ComfyUI's execution history."""
        self.assertIn("return ()", self.src)
        # The encode() method should NOT return a dict with ui metadata
        # that might be misinterpreted as image data in execution history
        encode_idx = self.src.find("def encode(self,")
        return_idx = self.src.find("return ()", encode_idx)
        # Ensure the return () is inside encode(), not other methods
        next_def = self.src.find("\n    def ", encode_idx + 20)
        self.assertGreater(return_idx, 0, "return () not found")
        self.assertLess(return_idx, next_def if next_def > 0 else len(self.src),
                        "return () not inside encode()")

    # ── Registration in _start_in_process_backend ─────────────────────

    def test_node_registered_after_init_extra_nodes(self):
        self.assertIn(
            "nodes.NODE_CLASS_MAPPINGS",
            self.src,
        )
        self.assertIn("ComfyModalProductionOutput", self.src)

    # ── Active production request state ───────────────────────────────

    def test_active_production_request_set_before_executor(self):
        """_active_production_request must be set before executor.execute()."""
        # Find the _active_production_request assignment before executor
        req_assign = "_active_production_request"
        exec_call = "self._executor.execute("
        idx_req = self.src.find(req_assign)
        idx_exec = self.src.find(exec_call, 9500)  # search from _execute_in_process
        self.assertGreater(
            idx_req, 0,
            "_active_production_request must be assigned somewhere"
        )
        self.assertGreater(
            idx_exec, 0,
            "executor.execute() call must exist"
        )
        # The _active_production_request assignment should appear before
        # the executor.execute call (but without import-time ordering we
        # just check both exist)
        self.assertLess(
            idx_req, idx_exec,
            "_active_production_request must be set before executor.execute()"
        )

    def test_active_production_request_contains_required_keys(self):
        """Verify the _active_production_request dict contains all required keys.
        
        We look for the dict literal that starts with "enabled" and contains
        prompt_id, output_format, quality, etc. before the executor.execute call."""
        keywords = ['"prompt_id"', '"output_format"', '"quality"',
                     '"webp_lossless_compression"', '"metadata_mode"']
        # Find the _active_production_request dict assignment in the
        # _execute_in_process method (the one that sets these keys)
        dict_start = self.src.find('self._active_production_request = {')
        self.assertGreater(dict_start, 0, "self._active_production_request dict not found")
        for kw in keywords:
            with self.subTest(key=kw):
                self.assertIn(
                    kw,
                    self.src[dict_start:dict_start + 1000],
                    f"Key {kw} not found inside _active_production_request dict"
                )

    def test_active_production_request_contains_authorized_node_ids(self):
        """The _active_production_request dict must include
        authorized_node_ids from the production options."""
        dict_start = self.src.find('self._active_production_request = {')
        self.assertIn(
            '"authorized_node_ids"',
            self.src[dict_start:dict_start + 1000],
        )

    # ── Authorisation checks in encode() ───────────────────────────

    def test_encode_checks_prompt_id_match(self):
        """encode() must verify the executing prompt_id matches the
        authorised request's prompt_id."""
        self.assertIn("req.get(\"prompt_id\")", self.src)
        self.assertIn("str(req_prompt_id) != str(prompt_id)", self.src)

    def test_encode_checks_authorized_node_ids(self):
        """encode() must verify the current node_id is in
        authorized_node_ids to prevent manual invocation."""
        self.assertIn("authorized_ids", self.src)
        self.assertIn("str(node_id) not in [str(a) for a in authorized_ids]", self.src)

    def test_encode_returns_empty_on_prompt_id_mismatch(self):
        """encode() must return () when prompt_id does not match."""
        self.assertIn("prompt_id mismatch", self.src)

    def test_encode_returns_empty_on_unauthorized_node(self):
        """encode() must return () when node is not authorized."""
        self.assertIn("not in [str(a) for a in authorized_ids]", self.src)

    # ── Registry cleanup timing ────────────────────────────────────

    def test_registry_cleanup_happens_on_early_return(self):
        """When collect_outputs=False, registry must still be cleaned up.
        
        There are two "if not collect_outputs:" blocks in _execute_in_process:
        one early (warmup validation skip) and one after executor execute
        (post-execution warmup return).  The cleanup should be in the second."""
        first_idx = self.src.find("if not collect_outputs:")
        second_idx = self.src.find("if not collect_outputs:", first_idx + 1)
        region = self.src[second_idx:second_idx + 700]
        self.assertIn(
            "_PROD_DIRECT_SINK_REGISTRY.pop(prompt_id, None)",
            region,
            "Registry cleanup must happen in the post-execution early return"
        )

    def test_production_output_registry_assigned(self):
        """_production_output_registry should be assigned to _PROD_DIRECT_SINK_REGISTRY."""
        self.assertIn(
            "self._production_output_registry = _PROD_DIRECT_SINK_REGISTRY",
            self.src,
        )

    def test_PROD_DIRECT_SINK_REQUEST_assigned(self):
        """Module-level _PROD_DIRECT_SINK_REQUEST should be set to the same dict."""
        self.assertIn(
            "_PROD_DIRECT_SINK_REQUEST = self._active_production_request",
            self.src,
        )

    def test_cleanup_in_finally_block(self):
        """State cleanup must happen: _PROD_DIRECT_SINK_REQUEST = None."""
        self.assertIn("_PROD_DIRECT_SINK_REQUEST = None", self.src)

    def test_registry_cleanup_after_collection_not_in_finally(self):
        """Registry pop must NOT happen in the executor finally block
        (it would clear data before _collect_in_process_outputs reads it).
        Instead, registry cleanup happens after collection completes."""
        # Verify registry is NOT popped in the finally block — search for
        # the pop near the cleanup section (which should NOT have it)
        finally_idx = self.src.find("finally:")
        after_finally = self.src[finally_idx:finally_idx + 150]
        self.assertNotIn(
            "_PROD_DIRECT_SINK_REGISTRY.pop",
            after_finally,
            "Registry pop MUST NOT be in the executor finally block"
        )
        # Registry pop should still exist in the file, but after collection
        self.assertIn("_PROD_DIRECT_SINK_REGISTRY.pop(prompt_id, None)", self.src)
        # It should appear AFTER _collect_in_process_outputs
        collect_idx = self.src.find("_collect_in_process_outputs(")
        pop_idx = self.src.find("_PROD_DIRECT_SINK_REGISTRY.pop(prompt_id, None)")
        self.assertGreater(
            pop_idx, collect_idx,
            "Registry pop must happen AFTER output collection"
        )

    def test_cleanup_del_instance_attrs(self):
        """Instance attrs _active_production_request and _production_output_registry
        must be deleted in cleanup."""
        self.assertIn("del self._active_production_request", self.src)
        self.assertIn("del self._production_output_registry", self.src)

    # ── allow_direct_output_rewrite=True in all three callsites ──────

    def test_execute_in_process_allow_direct_output_rewrite_true(self):
        """_execute_in_process must use allow_direct_output_rewrite=True."""
        self.assertIn(
            "build_production_topology_hash(",
            self.src,
        )
        self.assertIn(
            "allow_direct_output_rewrite=True",
            self.src,
        )

    def test_run_prompt_allow_direct_output_rewrite_true(self):
        """run_prompt compile_production_workflow must gate rewrite to in-process backend."""
        # Find the compile_production_workflow call in run_prompt region
        idx_rp = self.src.find("def run_prompt(")
        idx_sub = self.src.find("def run_prompt_stream(")
        region = self.src[idx_rp:idx_sub] if idx_sub > 0 else self.src[idx_rp:]
        self.assertIn('_allow_direct_output_rewrite = self._select_backend() == "in_process"', region)
        self.assertIn("allow_direct_output_rewrite=_allow_direct_output_rewrite", region)

    def test_run_prompt_stream_allow_direct_output_rewrite_true(self):
        """run_prompt_stream compile_production_workflow must gate rewrite to in-process backend."""
        idx = self.src.find("def run_prompt_stream(")
        region = self.src[idx:]
        self.assertIn('_allow_direct_output_rewrite = self._select_backend() == "in_process"', region)
        self.assertIn("allow_direct_output_rewrite=_allow_direct_output_rewrite", region)

    def test_compile_log_direct_output_rewrite_1(self):
        """Compile log message should include the direct-output-rewrite flag."""
        self.assertIn("direct_output_rewrite={1 if _allow_direct_output_rewrite else 0}", self.src)

    # ── Registry-first collection in _collect_in_process_outputs ──────

    def test_collect_checks_registry_first(self):
        """_collect_in_process_outputs must check _PROD_DIRECT_SINK_REGISTRY."""
        self.assertIn(
            "_PROD_DIRECT_SINK_REGISTRY.get(prompt_id)",
            self.src,
        )

    def test_collect_skips_history_when_registry_used(self):
        """history_result read should be guarded by 'if not _registry_used'."""
        self.assertIn("if not _registry_used:", self.src)

    def test_skips_queue_when_registry_used(self):
        """prompt_queue.history should be guarded by 'if not _registry_used'."""
        self.assertIn("if not _registry_used and not seen_filenames:", self.src)

    def test_registry_telemetry_printed(self):
        """Registry telemetry prints should exist."""
        self.assertIn("[timing.output.registry]", self.src)

    def test_registry_telemetry_in_output_collect(self):
        """output_collect should print registry_used, registry_node_count,
        registry_entry_count."""
        self.assertIn("registry_used={_registry_used}", self.src)
        self.assertIn("registry_node_count={_registry_node_count}", self.src)
        self.assertIn("registry_entry_count={_registry_entry_count}", self.src)

    def test_oc_timing_has_registry_fields(self):
        """_oc_timing dict should include registry-entry telemetry."""
        self.assertIn('"registry_entry_count"', self.src)
        self.assertIn('"registry_node_count"', self.src)

    def test_registry_entry_base64_encoded(self):
        """Registry entries should be base64-encoded using base64.b64encode."""
        self.assertIn("base64.b64encode(_raw_bytes)", self.src)


# =========================================================================
# Functional tests for production_workflow.py
# =========================================================================

class Phase3b1ProductionReportTests(unittest.TestCase):
    """Verify production_report includes Phase 3b1 telemetry fields."""

    def setUp(self):
        _reset_cache()

    def test_report_contains_direct_output_sink_enabled(self):
        wf = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 1, "model": ("2", 0)}},
            "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "m.safetensors"}},
            "3": {"class_type": "VAEDecode", "inputs": {"samples": ("1", 0)}},
            "4": {"class_type": "SaveImage", "inputs": {"images": ("3", 0)}},
        }
        prod = _minimal_production(output_ids=["4"])
        _, report = compile_production_workflow(wf, prod, allow_direct_output_rewrite=True)
        self.assertIn("direct_output_sink_enabled", report)
        self.assertTrue(report["direct_output_sink_enabled"])

    def test_report_contains_allow_direct_output_rewrite(self):
        wf = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 1, "model": ("2", 0)}},
            "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "m.safetensors"}},
            "3": {"class_type": "VAEDecode", "inputs": {"samples": ("1", 0)}},
            "4": {"class_type": "SaveImage", "inputs": {"images": ("3", 0)}},
        }
        prod = _minimal_production(output_ids=["4"])
        _, report = compile_production_workflow(wf, prod, allow_direct_output_rewrite=True)
        self.assertIn("allow_direct_output_rewrite", report)
        self.assertTrue(report["allow_direct_output_rewrite"])

    def test_report_fields_when_rewrite_false(self):
        wf = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 1, "model": ("2", 0)}},
            "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "m.safetensors"}},
            "3": {"class_type": "VAEDecode", "inputs": {"samples": ("1", 0)}},
            "4": {"class_type": "SaveImage", "inputs": {"images": ("3", 0)}},
        }
        prod = _minimal_production(output_ids=["4"])
        _, report = compile_production_workflow(wf, prod, allow_direct_output_rewrite=False)
        self.assertFalse(report["allow_direct_output_rewrite"])
        self.assertTrue(report["direct_output_sink_enabled"])

    def test_report_fields_when_direct_output_sink_disabled(self):
        wf = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 1, "model": ("2", 0)}},
            "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "m.safetensors"}},
            "3": {"class_type": "VAEDecode", "inputs": {"samples": ("1", 0)}},
            "4": {"class_type": "SaveImage", "inputs": {"images": ("3", 0)}},
        }
        prod = _minimal_production(output_ids=["4"], direct_output_sink=False)
        _, report = compile_production_workflow(wf, prod, allow_direct_output_rewrite=True)
        self.assertFalse(report["direct_output_sink_enabled"])
        self.assertTrue(report["allow_direct_output_rewrite"])

    def test_cache_hit_also_populates_telemetry_fields(self):
        """Both cache-hit and cache-miss paths must include both fields."""
        _reset_cache()
        wf = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 1, "model": ("2", 0)}},
            "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "m.safetensors"}},
            "3": {"class_type": "VAEDecode", "inputs": {"samples": ("1", 0)}},
            "4": {"class_type": "SaveImage", "inputs": {"images": ("3", 0)}},
        }
        prod = _minimal_production(output_ids=["4"])

        # First call — cache miss
        _, report1 = compile_production_workflow(wf, prod, allow_direct_output_rewrite=True)
        self.assertIn("direct_output_sink_enabled", report1)
        self.assertIn("allow_direct_output_rewrite", report1)
        self.assertFalse(report1["cache_hit"])

        # Second call with same args — cache hit
        _, report2 = compile_production_workflow(wf, prod, allow_direct_output_rewrite=True)
        self.assertIn("direct_output_sink_enabled", report2)
        self.assertIn("allow_direct_output_rewrite", report2)
        self.assertTrue(report2["cache_hit"])

    def test_direct_output_sink_disabled_report_false(self):
        """When direct_output_sink=False in production options,
        direct_output_sink_enabled should be False in report."""
        wf = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 1, "model": ("2", 0)}},
            "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "m.safetensors"}},
            "3": {"class_type": "VAEDecode", "inputs": {"samples": ("1", 0)}},
            "4": {"class_type": "SaveImage", "inputs": {"images": ("3", 0)}},
        }
        prod = _minimal_production(output_ids=["4"], direct_output_sink=False)
        _, report = compile_production_workflow(wf, prod, allow_direct_output_rewrite=True)
        self.assertFalse(report["direct_output_sink_enabled"])


class Phase3b1DirectOutputRewriteBehaviorTests(unittest.TestCase):
    """Verify that allow_direct_output_rewrite=True actually rewrites outputs."""

    def setUp(self):
        _reset_cache()

    def test_rewrite_happens_with_true(self):
        wf = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 1, "model": ("2", 0)}},
            "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "m.safetensors"}},
            "3": {"class_type": "VAEDecode", "inputs": {"samples": ("1", 0)}},
            "4": {"class_type": "SaveImage", "inputs": {"images": ("3", 0)}},
        }
        prod = _minimal_production(output_ids=["4"])
        compiled, _ = compile_production_workflow(wf, prod, allow_direct_output_rewrite=True)
        self.assertEqual(compiled["4"]["class_type"], "ComfyModalProductionOutput")

    def test_rewrite_skipped_with_false(self):
        wf = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 1, "model": ("2", 0)}},
            "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "m.safetensors"}},
            "3": {"class_type": "VAEDecode", "inputs": {"samples": ("1", 0)}},
            "4": {"class_type": "SaveImage", "inputs": {"images": ("3", 0)}},
        }
        prod = _minimal_production(output_ids=["4"])
        compiled, _ = compile_production_workflow(wf, prod, allow_direct_output_rewrite=False)
        self.assertEqual(compiled["4"]["class_type"], "SaveImage")


class Phase3b1AuthorizationBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.module = _load_comfyapp_module()

    def test_authorization_rejects_prompt_id_mismatch(self):
        helper = self.module._is_authorized_production_direct_sink_request
        req = {
            "enabled": True,
            "prompt_id": "prompt-a",
            "authorized_node_ids": ["41"],
        }
        self.assertFalse(helper(req, "prompt-b", "41"))

    def test_authorization_rejects_unauthorized_node_id(self):
        helper = self.module._is_authorized_production_direct_sink_request
        req = {
            "enabled": True,
            "prompt_id": "prompt-a",
            "authorized_node_ids": ["41"],
        }
        self.assertFalse(helper(req, "prompt-a", "99"))

    def test_authorization_accepts_matching_prompt_and_node(self):
        helper = self.module._is_authorized_production_direct_sink_request
        req = {
            "enabled": True,
            "prompt_id": "prompt-a",
            "authorized_node_ids": ["41"],
        }
        self.assertTrue(helper(req, "prompt-a", "41"))


# =========================================================================
# AST tests for production_workflow.py report structure
# =========================================================================

class Phase3b1ProductionWorkflowAstTests(unittest.TestCase):
    """Verify production_workflow.py source contains Phase 3b1 fields."""

    def setUp(self):
        self.src = PRODWFLOW_PATH.read_text(encoding="utf-8")

    def test_report_has_direct_output_sink_enabled(self):
        self.assertIn('"direct_output_sink_enabled"', self.src)

    def test_report_has_allow_direct_output_rewrite(self):
        self.assertIn('"allow_direct_output_rewrite"', self.src)

    def test_both_fields_in_cache_hit_and_miss_paths(self):
        """The telemetry fields should appear at least twice (cache-hit and cache-miss)."""
        count_sink = self.src.count('"direct_output_sink_enabled"')
        self.assertGreaterEqual(count_sink, 2)
        count_rewrite = self.src.count('"allow_direct_output_rewrite"')
        self.assertGreaterEqual(count_rewrite, 2)
