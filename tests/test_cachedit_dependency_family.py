"""Focused tests for the CacheDiT dependency-family repair.

Covers:
- Lock file content and identity
- Constraints application to every custom-node pip install (build + runtime)
- Family reapply (--force-reinstall --no-deps) at image build
- Build import gate function (``_cachedit_import_gate``)
- Boolean flash-attn-2-available assertion semantics
- Fatal only on explicit CacheDiT invocation (``_guard_cachedit_node_class``)
- Startup snap preimports without request state (``preimport_cachedit_family``)
- Manager offline configuration preserves existing semantics
- BF16 CPU snapshot identity/reuse preserved (existing test coverage verified)
"""

import importlib.util
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

REPO_ROOT = Path(__file__).resolve().parents[1]
COMFYAPP_PATH = REPO_ROOT / "comfyapp.py"
MODAL_APP_PATH = REPO_ROOT / "comfymodal_runtime" / "modal_app.py"
LOCK_FILE_PATH = REPO_ROOT / "cachedit_dependency_lock.txt"


# ── Helpers ──────────────────────────────────────────────────────────

def _unique_module_name() -> str:
    import uuid
    return f"comfyapp_test_{uuid.uuid4().hex}"


def _module_snapshot() -> set[str]:
    """Return frozenset of current sys.modules keys for later restore."""
    return set(sys.modules)


def _module_restore(before: set[str], keep: set[str] | None = None) -> None:
    """Remove from sys.modules any key added since *before* snapshot,
    except those in *keep*."""
    keep = keep or set()
    for key in list(sys.modules):
        if key not in before and key not in keep:
            sys.modules.pop(key, None)


def _stub_module(name, attrs=None):
    mod = types.ModuleType(name)
    mod.__package__ = name.rpartition(".")[0]
    if attrs:
        for k, v in attrs.items():
            setattr(mod, k, v)
    return mod


def load_comfyapp():
    """Import comfyapp.py under a unique name with stubs for external
    dependencies.  All injected modules and any side-effect imports are
    purged from sys.modules before return (except the returned module)."""
    mod_before = _module_snapshot()

    def _replace(name, stub):
        sys.modules.pop(name, None)
        sys.modules[name] = stub

    _replace("modal", _stub_module("modal", {
        "Image": MagicMock(),
        "App": MagicMock(),
        "Volume": MagicMock(),
        "Secret": MagicMock(),
        "Dict": MagicMock(),
        "enter": lambda **kw: (lambda f: f),
        "exit": lambda: (lambda f: f),
        "method": lambda **kw: (lambda f: f),
        "concurrent": lambda **kw: (lambda c: c),
        "web_server": lambda *a, **kw: (lambda f: f),
        "asgi_app": lambda *a, **kw: (lambda f: f),
        "current_input_id": lambda: None,
        "from_name": lambda n, **kw: MagicMock(),
        "Cls": MagicMock(),
        "function": lambda **kw: (lambda f: f),
        "is_local": lambda: True,
    }))
    stub_img = MagicMock()
    for attr in ("apt_install", "pip_install", "run_commands", "env",
                 "add_local_dir", "add_local_file", "add_local_python_source",
                 "from_registry", "entrypoint"):
        getattr(stub_img, attr).return_value = stub_img
    sys.modules["modal"].Image.from_registry.return_value = stub_img
    sys.modules["modal"].Image.debian_slim.return_value = stub_img

    _replace("gpu_catalog", _stub_module("gpu_catalog", {
        "GPU_CATALOG": [],
        "get_supported_gpus": lambda: [],
        "is_gpu_hidden": lambda v: False,
        "get_default_gpu": lambda: "rtx-pro-6000",
        "SUPPORTED_GPUS": [],
        "GPU_BY_VALUE": {},
        "parse_gpu_request": lambda: ("H100",),
        "gpu_supports_bf16": lambda g: "H100" in g or "B200" in g,
    }))
    _replace("timing_trace", _stub_module("timing_trace", {
        "Trace": MagicMock(),
        "coerce_t0_from_browser": lambda p: None,
    }))
    _replace("wall_clock_trace_v3", _stub_module("wall_clock_trace_v3", {
        "make_actual_load_record": lambda **kw: {},
        "merge_wall_clock_trace": lambda **kw: {},
        "make_summary_log_line": lambda **kw: "",
        "make_wall_clock_summary": lambda **kw: {},
        "get_profile_level": lambda: 0,
        "profile_enabled": lambda: False,
        "TRACE_VERSION": 1,
    }))
    _replace("profiler_trace_v4", _stub_module("profiler_trace_v4", {
        "mark_event": lambda **kw: None,
        "make_event": lambda **kw: {},
        "summarize_trace": lambda **kw: {},
        "T3_MODAL_ENTRY": "t3_modal_entry",
        "T8C_RETURN_PACKAGING_START": "t8c_return_packaging_start",
        "T8D_RETURN_PACKAGING_END": "t8d_return_packaging_end",
        "T8E_REMOTE_RETURN_START": "t8e_remote_return_start",
        "T8F_REMOTE_RETURN_END": "t8f_remote_return_end",
        "PHASE_RETURN": "phase_return",
        "PHASE_EXECUTION": "phase_execution",
        "derive_spans": lambda **kw: [],
    }))
    _replace("failure_summary", _stub_module("failure_summary", {
        "FailureSummary": type("FailureSummary", (), {"__init__": lambda self, **kw: None}),
    }))
    _replace("production_workflow", _stub_module("production_workflow", {
        "normalize_production_options": lambda **kw: kw,
        "compile_production_workflow": lambda **kw: (kw, {}),
        "build_production_topology_hash": lambda **kw: "",
    }))
    _replace("comfymodal_runtime.dependency_manifest", _stub_module("comfymodal_runtime.dependency_manifest", {
        "build_identity": lambda **kw: "test-identity",
        "build_manifest_dict": lambda **kw: {},
        "persist_manifest": lambda **kw: False,
        "load_manifest": lambda **kw: None,
        "check_identity": lambda **kw: {"identity_match": False},
        "emit_validation_diagnostic": lambda **kw: None,
        "commit_volume_sync": lambda v: False,
        "commit_volume_async": lambda v: False,
        "DEPENDENCY_MANIFEST_SCHEMA_VERSION": 1,
    }))
    _replace("comfymodal_runtime.contracts", _stub_module("comfymodal_runtime.contracts", {
        "stable_hash": lambda s: "stable-hash",
        "DeploymentIdentity": MagicMock(),
        "ExecutionPlan": MagicMock(),
        "ModelRestoreKey": MagicMock(),
        "RestorePlan": MagicMock(),
        "_thaw": lambda x: x,
    }))

    module_name = _unique_module_name()
    spec = importlib.util.spec_from_file_location(module_name, str(COMFYAPP_PATH))
    assert spec is not None, f"Could not create spec for {COMFYAPP_PATH}"
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    module._INSIDE_MODAL_CONTAINER = True

    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        _module_restore(mod_before)
        raise exc

    # Purge all new modules except the test module itself
    _module_restore(mod_before, keep={module_name})
    return module


def load_modal_app():
    """Import modal_app module via the comfymodal_runtime package with
    stubs for external dependencies.  All injected modules and
    side-effect imports are purged from sys.modules before return."""
    mod_before = _module_snapshot()

    # modal needs specific attributes for modal_app module-level code
    sys.modules.pop("modal", None)
    sys.modules["modal"] = _stub_module("modal", {
        "enter": lambda **kw: (lambda f: f),
        "exit": lambda: (lambda f: f),
        "method": lambda **kw: (lambda f: f),
        "concurrent": lambda **kw: (lambda c: c),
        "web_server": lambda *a, **kw: (lambda f: f),
        "asgi_app": lambda *a, **kw: (lambda f: f),
        "App": MagicMock(),
        "Volume": MagicMock(),
        "Secret": MagicMock(),
        "Dict": MagicMock(),
        "Image": MagicMock(),
        "current_input_id": lambda: None,
        "from_name": lambda n, **kw: MagicMock(),
        "Cls": MagicMock(),
        "function": lambda **kw: (lambda f: f),
        "is_local": lambda: True,
    })

    # gpu_catalog needs real symbols
    sys.modules.pop("gpu_catalog", None)
    sys.modules["gpu_catalog"] = _stub_module("gpu_catalog", {
        "parse_gpu_request": lambda: ("H100",),
        "normalize_gpu_value": lambda v, **kw: v,
        "GPU_CATALOG": [],
        "GPU_BY_VALUE": {},
        "get_supported_gpus": lambda: [],
        "is_gpu_hidden": lambda v: False,
        "get_default_gpu": lambda: "rtx-pro-6000",
        "gpu_supports_bf16": lambda g: True,
    })

    # Stub top-level modules that modal_app imports at module level
    for sname in ("timing_trace", "wall_clock_trace_v3",
                  "profiler_trace_v4", "failure_summary",
                  "production_workflow"):
        sys.modules.pop(sname, None)
        sys.modules[sname] = _stub_module(sname)

    # Set up comfymodal_runtime package and its submodule stubs
    for submod in (
        "comfymodal_runtime",
        "comfymodal_runtime.contracts",
        "comfymodal_runtime.deployment_spec",
        "comfymodal_runtime.restore_plan",
        "comfymodal_runtime.runtime_bootstrap",
        "comfymodal_runtime.runtime_executor",
        "comfymodal_runtime.runtime_state",
        "comfymodal_runtime.model_preload",
        "comfymodal_runtime.cpu_snapshot_models",
        "comfymodal_runtime.unet_forward_probe",
        "comfymodal_runtime.output_delivery",
        "comfymodal_runtime.result_delivery",
        "comfymodal_runtime.trace",
    ):
        sys.modules.pop(submod, None)
        pkg = _stub_module(submod)
        pkg.__path__ = []
        if submod == "comfymodal_runtime":
            pkg.__path__ = [str(REPO_ROOT / "comfymodal_runtime")]
        sys.modules[submod] = pkg

    # Populate required symbols in stub submodules
    sys.modules["comfymodal_runtime.contracts"].__dict__.update({
        "DeploymentIdentity": MagicMock(),
        "ExecutionPlan": MagicMock(),
        "ModelRestoreKey": MagicMock(),
        "RestorePlan": MagicMock(),
        "_thaw": lambda x: x,
        "stable_hash": lambda s: "stable-hash",
    })
    sys.modules["comfymodal_runtime.deployment_spec"].__dict__.update({
        "build_deployment_identity": lambda **kw: MagicMock(),
    })
    sys.modules["comfymodal_runtime.restore_plan"].__dict__.update({
        "RestorePlanPublisher": MagicMock(),
        "build_restore_model_spec": lambda **kw: None,
        "derive_model_key": lambda **kw: None,
        "derive_prefill_key": lambda **kw: None,
    })
    sys.modules["comfymodal_runtime.runtime_bootstrap"].__dict__.update({
        "BootstrapConfig": MagicMock(),
        "RuntimeBootstrap": MagicMock(),
    })
    sys.modules["comfymodal_runtime.runtime_executor"].__dict__.update({
        "ExecutionContext": MagicMock(),
        "RuntimeExecutor": MagicMock(),
        "pre_sampler_instrumentation_scope": MagicMock(),
        "set_lock_wait_ms": lambda ms: None,
    })
    sys.modules["comfymodal_runtime.runtime_state"].__dict__.update({
        "CommitCoordinator": MagicMock(),
        "ModalMountedStateVolume": MagicMock(),
    })
    sys.modules["comfymodal_runtime.model_preload"].__dict__.update({
        "V2LoaderBridge": MagicMock(),
        "RestorePreparation": MagicMock(),
        "_collect_restore_events_for_summary": lambda **kw: [],
        "get_restore_return_marker": lambda: None,
        "gpu_not_observed_summary": lambda: {},
        "request_execution_trace_scope": MagicMock(),
        "resolve_unet_effective_dtype": lambda **kw: (None, "default"),
        "set_model_load_identity": lambda **kw: None,
        "set_restore_return_marker": lambda **kw: None,
        "_capture_host_info": lambda **kw: {},
        "_DIAGNOSTIC_FLAG": False,
    })
    sys.modules["comfymodal_runtime.cpu_snapshot_models"].__dict__.update({
        "CpuSnapshotModels": MagicMock(),
        "collect_unet_runtime_state": lambda **kw: {},
        "identity_from_profile": lambda **kw: None,
        "inspect_and_validate_snapshot_params": lambda **kw: {},
        "load_cpu_snapshot_models": lambda **kw: None,
        "validate_cpu_snapshot_models": lambda **kw: None,
        "validate_snapshot_unet_bf16_native": lambda **kw: None,
        "retarget_cpu_snapshot_models": lambda **kw: None,
        "_COMPUTE_POLICY_BF16_NATIVE": "bf16_native",
    })
    sys.modules["comfymodal_runtime.unet_forward_probe"].__dict__.update({
        "register_unet_forward_probe": lambda **kw: None,
    })
    sys.modules["comfymodal_runtime.output_delivery"].__dict__.update({
        "Attempt": MagicMock(),
        "_measure_json_bytes": lambda x: 0,
        "attempt_to_descriptor_result": lambda **kw: {"images": [], "videos": [], "outputs": {}, "asset_descriptors": [], "use_descriptors": True},
        "build_default_chain": lambda **kw: [],
        "run_strategy_chain": lambda **kw: {},
    })
    sys.modules["comfymodal_runtime.result_delivery"].__dict__.update({
        "ConversionFailedError": type("ConversionFailedError", (Exception,), {}),
        "convert_output_items": lambda **kw: [],
    })
    sys.modules["comfymodal_runtime.trace"].__dict__.update({
        "RuntimeTrace": MagicMock(),
        "_emit_breakdown_line": lambda **kw: None,
        "merge_runtime_traces": lambda **kw: {},
    })

    # Minimal comfyapp stub for modal_app import
    sys.modules.pop("comfyapp", None)
    sys.modules["comfyapp"] = _stub_module("comfyapp", {
        "_image_base": MagicMock(),
        "image": MagicMock(),
    })

    # Import the real modal_app via the package
    import importlib as _il
    try:
        module = _il.import_module("comfymodal_runtime.modal_app")
    except Exception as exc:
        _module_restore(mod_before)
        raise exc

    # Purge all new modules except modal_app
    _module_restore(mod_before, keep={"comfymodal_runtime.modal_app"})
    return module


# ── Module-level helpers ─────────────────────────────────────────────

def _setup_model_preload():
    """Set up sys.modules stubs so model_preload can be imported.
    Returns (importlib_util, cleanup_fn) where cleanup_fn restores
    sys.modules to its pre-call state."""
    mod_before = _module_snapshot()
    import importlib.util as _iu
    sys.modules["comfymodal_runtime"] = types.ModuleType("comfymodal_runtime")
    sys.modules["comfymodal_runtime"].__path__ = [str(REPO_ROOT / "comfymodal_runtime")]
    for _sub in ("contracts", "trace"):
        sys.modules[f"comfymodal_runtime.{_sub}"] = types.ModuleType(f"comfymodal_runtime.{_sub}")
    sys.modules["comfymodal_runtime.contracts"].ModelRestoreKey = MagicMock()
    sys.modules["comfymodal_runtime.contracts"].PrefillKey = MagicMock()
    sys.modules["comfymodal_runtime.contracts"].stable_hash = lambda s: "hash"
    # cpu_snapshot_models needs specific symbols
    sys.modules["comfymodal_runtime.cpu_snapshot_models"] = types.ModuleType(
        "comfymodal_runtime.cpu_snapshot_models")
    _csm = sys.modules["comfymodal_runtime.cpu_snapshot_models"]
    _csm.collect_unet_runtime_state = lambda **kw: {}
    _csm.identity_from_profile = lambda **kw: None
    _csm.inspect_and_validate_snapshot_params = lambda **kw: {}
    _csm.load_cpu_snapshot_models = lambda **kw: None
    _csm.validate_cpu_snapshot_models = lambda **kw: None
    _csm.validate_snapshot_unet_bf16_native = lambda **kw: None
    _csm.retarget_cpu_snapshot_models = lambda **kw: None
    _csm._COMPUTE_POLICY_BF16_NATIVE = "bf16_native"
    _csm.CpuSnapshotModels = MagicMock()
    _csm.cpu_snapshot_unet_compute_policy = MagicMock()
    sys.modules["comfymodal_runtime.trace"].RuntimeTrace = MagicMock()

    def _cleanup():
        _module_restore(mod_before)
    return _iu, _cleanup


# ── Tests ────────────────────────────────────────────────────────────

class TestLockFileIdentity(unittest.TestCase):
    """Dependency lock file content and path identity."""

    def test_lock_file_exists(self):
        self.assertTrue(LOCK_FILE_PATH.is_file(),
                        f"Lock file not found at {LOCK_FILE_PATH}")

    def test_lock_file_has_exact_pins(self):
        content = LOCK_FILE_PATH.read_text(encoding="utf-8")
        expected_pins = [
            "cache-dit==1.2.3",
            "transformers==4.55.2",
            "diffusers==0.36.0",
            "huggingface-hub==0.34.4",
            "accelerate==1.10.1",
            "safetensors==0.5.3",
            "tokenizers==0.21.4",
        ]
        for pin in expected_pins:
            with self.subTest(pin=pin):
                self.assertIn(pin, content,
                              f"Expected pin {pin!r} not in lock file")

    def test_lock_file_has_no_extra_deps(self):
        content = LOCK_FILE_PATH.read_text(encoding="utf-8")
        lines = [l.strip() for l in content.splitlines() if l.strip() and not l.strip().startswith("#")]
        # Exactly 7 pinned lines
        self.assertEqual(len(lines), 7,
                         f"Expected exactly 7 pinned lines, got {len(lines)}: {lines}")

    def test_lock_file_participates_in_image_build(self):
        """Verify comfyapp.py references the lock file path."""
        src = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn("cachedit_dependency_lock.txt", src,
                      "Lock file name must be referenced in comfyapp.py for image-build participation")


class TestConstraintsApplication(unittest.TestCase):
    """Constraints file applied to every custom-node pip install."""

    def test_build_loop_uses_c_flag(self):
        src = COMFYAPP_PATH.read_text(encoding="utf-8")
        # The image-build shell command must use -c with the lock
        self.assertIn("-c \"$_lock\"", src,
                      "Build loop must apply constraints via -c to pip install")
        self.assertIn("CACHEDIT_LOCK_DST", src,
                      "Build image must reference lock destination path")

    def test_runtime_install_uses_c_flag(self):
        src = COMFYAPP_PATH.read_text(encoding="utf-8")
        # The runtime _install_custom_node_requirements must use -c
        self.assertIn("_pip_cmd.extend([\"-c\", _CACHEDIT_LOCK_DST])", src,
                      "Runtime pip install must apply constraints via -c")

    def test_family_reinstall_at_build(self):
        src = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn("--force-reinstall --no-deps -r \"$_lock\"", src,
                      "Build must reinstall locked family with --force-reinstall --no-deps")

    def test_family_reinstall_precedes_import_gate(self):
        src = COMFYAPP_PATH.read_text(encoding="utf-8")
        # The family reinstall must appear before the import gate in the shell script
        reinstall_pos = src.find("FAMILY_REINSTALL_START")
        gate_pos = src.find("CACHEDIT_LOCK_GATE")
        self.assertGreater(gate_pos, reinstall_pos,
                           "Import gate must follow family reinstall in build script")
        self.assertNotEqual(reinstall_pos, -1, "Family reinstall marker not found")
        self.assertNotEqual(gate_pos, -1, "Import gate marker not found")


class TestBuildGate(unittest.TestCase):
    """Image-build import gate logic."""

    def test_import_gate_function_exists(self):
        module = load_comfyapp()
        self.assertTrue(hasattr(module, "_cachedit_import_gate"),
                        "comfyapp must export _cachedit_import_gate")
        self.assertTrue(callable(module._cachedit_import_gate))

    def test_import_gate_ok_when_all_packages_available(self):
        module = load_comfyapp()
        _call_log = []

        class FakeImportlibMeta:
            @staticmethod
            def version(pkg):
                versions = {
                    "cache-dit": "1.2.3",
                    "transformers": "4.55.2",
                    "diffusers": "0.36.0",
                    "huggingface-hub": "0.34.4",
                    "accelerate": "1.10.1",
                    "safetensors": "0.5.3",
                    "tokenizers": "0.21.4",
                }
                return versions.get(pkg, "0.0.0")

        class FakeImportlib:
            metadata = FakeImportlibMeta()

            @staticmethod
            def import_module(name):
                mod = types.ModuleType(name)
                mod.__file__ = f"/fake/path/{name}.py"
                return mod

        _captured_fa_type = []

        def _fake_fa_available():
            _captured_fa_type.append(True)
            return True

        result = module._cachedit_import_gate(
            _importlib=FakeImportlib(),
            _print=lambda *a, **kw: _call_log.append(("print", a, kw)),
        )
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["errors"]), 0)
        self.assertIn("transformers", result["versions"])
        self.assertEqual(result["versions"]["cache-dit"], "1.2.3")
        # flash_attn will be checked by the function

    def test_import_gate_fails_on_missing_package(self):
        module = load_comfyapp()

        class FailImportlib:
            metadata = type("Meta", (), {"version": staticmethod(lambda pkg: (_ for _ in ()).throw(Exception("pkg not found")))})()
            @staticmethod
            def import_module(name):
                raise ImportError(f"No module named {name}")

        result = module._cachedit_import_gate(_importlib=FailImportlib())
        self.assertFalse(result["ok"])
        self.assertGreater(len(result["errors"]), 0)

    def test_import_gate_build_step_referenced(self):
        """Verify the build shell script references the import gate function or inline gate."""
        src = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn("CACHEDIT_LOCK_GATE", src,
                      "Build shell script must contain the import gate invocation")

    def test_build_gate_overrides_torchinductor_cache_dir(self):
        """Build gate must export TORCHINDUCTOR_CACHE_DIR to a /tmp path
        to avoid creating content under the future volume mount point."""
        src = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "export TORCHINDUCTOR_CACHE_DIR=/tmp/build_gate_inductor_cache",
            src,
            "Build gate must override TORCHINDUCTOR_CACHE_DIR to /tmp path",
        )

    def test_build_gate_overrides_triton_cache_dir(self):
        """Build gate must export TRITON_CACHE_DIR to a /tmp path
        to avoid creating content under the future volume mount point."""
        src = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "export TRITON_CACHE_DIR=/tmp/build_gate_triton_cache",
            src,
            "Build gate must override TRITON_CACHE_DIR to /tmp path",
        )

    def test_build_gate_env_overrides_precede_gate(self):
        """The env override exports must appear before the PYEOF gate
        invocation in the build script so they are active during imports."""
        src = COMFYAPP_PATH.read_text(encoding="utf-8")
        inductor_pos = src.find("export TORCHINDUCTOR_CACHE_DIR=/tmp/build_gate_inductor_cache")
        triton_pos = src.find("export TRITON_CACHE_DIR=/tmp/build_gate_triton_cache")
        gate_pos = src.find('python3 << "PYEOF"')
        self.assertNotEqual(inductor_pos, -1, "TORCHINDUCTOR_CACHE_DIR override not found")
        self.assertNotEqual(triton_pos, -1, "TRITON_CACHE_DIR override not found")
        self.assertNotEqual(gate_pos, -1, "PYEOF gate not found")
        self.assertLess(inductor_pos, gate_pos,
                        "TORCHINDUCTOR_CACHE_DIR override must precede the PYEOF gate")
        self.assertLess(triton_pos, gate_pos,
                        "TRITON_CACHE_DIR override must precede the PYEOF gate")

    def test_build_gate_python_cleanup_uses_shutil_rmtree(self):
        """Build gate must use shutil.rmtree inside the Python heredoc to
        clean up /root/comfymodal_runtime_state, avoiding unsupported
        Dockerfile shell 'rm' command after PYEOF."""
        src = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn(
            'shutil.rmtree("/root/comfymodal_runtime_state", ignore_errors=True)',
            src,
            "Build gate must clean up /root/comfymodal_runtime_state "
            "via shutil.rmtree inside the Python heredoc",
        )

    def test_build_gate_cleanup_before_pyeof(self):
        """The shutil.rmtree cleanup must appear before the PYEOF terminator,
        inside the heredoc Python script, so it runs in the same supported
        RUN process as the import gate."""
        src = COMFYAPP_PATH.read_text(encoding="utf-8")
        rmtree_pos = src.find('shutil.rmtree("/root/comfymodal_runtime_state"')
        pyeof_pos = src.rfind("PYEOF")
        self.assertNotEqual(rmtree_pos, -1, "shutil.rmtree cleanup not found")
        self.assertNotEqual(pyeof_pos, -1, "PYEOF terminator not found")
        self.assertLess(rmtree_pos, pyeof_pos,
                        "shutil.rmtree must appear before the PYEOF terminator")

    def test_build_gate_no_shell_rm_after_pyeof(self):
        """No shell 'rm -rf' command may appear after the PYEOF terminator,
        since the Modal Dockerfile build does not support post-heredoc
        shell commands as separate RUN layers."""
        src = COMFYAPP_PATH.read_text(encoding="utf-8")
        rm_pos = src.find("rm -rf /root/comfymodal_runtime_state")
        pyeof_pos = src.rfind("PYEOF")
        if rm_pos != -1:
            self.assertLess(
                rm_pos, pyeof_pos,
                "shell rm -rf must NOT appear after PYEOF; "
                "cleanup must be inside the Python heredoc",
            )


class TestFlashAttnBoolSemantics(unittest.TestCase):
    """Boolean flash-attn-2-available assertion semantics."""

    def test_gate_requires_bool_from_flash_attn(self):
        """_cachedit_import_gate must assert isinstance(result, bool)."""
        module = load_comfyapp()

        class FakeImportlib:
            metadata = type("Meta", (), {
                "version": staticmethod(lambda pkg: "1.0.0"),
            })()
            @staticmethod
            def import_module(name):
                mod = types.ModuleType(name)
                mod.__file__ = f"/fake/{name}.py"
                return mod

        class FakeTransformersUtils:
            @staticmethod
            def is_flash_attn_2_available():
                return "not-a-bool"

        import sys as _sys
        _sys.modules["transformers.utils"] = FakeTransformersUtils  # type: ignore

        try:
            result = module._cachedit_import_gate(_importlib=FakeImportlib())
            self.assertFalse(result["flash_attn_type_ok"])
            self.assertFalse(result["ok"])
        finally:
            _sys.modules.pop("transformers.utils", None)

    def test_gate_accepts_true_from_flash_attn(self):
        module = load_comfyapp()

        class FakeImportlib2:
            metadata = type("Meta", (), {
                "version": staticmethod(lambda pkg: "1.0.0"),
            })()
            @staticmethod
            def import_module(name):
                mod = types.ModuleType(name)
                mod.__file__ = f"/fake/{name}.py"
                return mod

        class FakeTransformersUtils2:
            @staticmethod
            def is_flash_attn_2_available():
                return True

        import sys as _sys
        _sys.modules["transformers.utils"] = FakeTransformersUtils2  # type: ignore
        try:
            result = module._cachedit_import_gate(_importlib=FakeImportlib2())
            self.assertTrue(result["flash_attn_type_ok"])
            self.assertTrue(result["flash_attn_available"] is True or result["flash_attn_available"] is False)
        finally:
            _sys.modules.pop("transformers.utils", None)


class TestCacheDiTGuard(unittest.TestCase):
    """Fatal only on explicit CacheDiT invocation, non-CacheDiT unaffected."""

    def test_guard_function_exists(self):
        module = load_comfyapp()
        self.assertTrue(hasattr(module, "_guard_cachedit_node_class"))
        self.assertTrue(callable(module._guard_cachedit_node_class))

    def test_guard_wraps_function(self):
        module = load_comfyapp()
        class FakeCD:
            FUNCTION = "apply_model_optimization"
            def apply_model_optimization(self, model):
                return (model,)

        with patch.object(module, "DISABLE_CACHEDIT_FOR_Z_IMAGE", False):
            result = module._guard_cachedit_node_class(FakeCD)
        self.assertTrue(result)
        self.assertTrue(getattr(FakeCD.apply_model_optimization, "_comfy_modal_guarded", False))

    def test_guard_skipped_when_disabled(self):
        module = load_comfyapp()
        class FakeCD:
            FUNCTION = "apply_model_optimization"
            def apply_model_optimization(self, model):
                return (model,)

        with patch.object(module, "DISABLE_CACHEDIT_FOR_Z_IMAGE", True):
            result = module._guard_cachedit_node_class(FakeCD)
        self.assertFalse(result)

    def test_guard_passes_through_success(self):
        module = load_comfyapp()
        class FakeCD:
            FUNCTION = "apply_model_optimization"
            def apply_model_optimization(self, model):
                return (model,)

        with patch.object(module, "DISABLE_CACHEDIT_FOR_Z_IMAGE", False):
            module._guard_cachedit_node_class(FakeCD)
        instance = FakeCD()
        result = instance.apply_model_optimization("test-model")
        self.assertEqual(result, ("test-model",))

    def test_guard_fails_fatal_on_exception(self):
        module = load_comfyapp()
        class FakeCD:
            FUNCTION = "apply_model_optimization"
            def apply_model_optimization(self, model):
                raise ValueError("simulated init failure")

        with patch.object(module, "DISABLE_CACHEDIT_FOR_Z_IMAGE", False):
            module._guard_cachedit_node_class(FakeCD)
        instance = FakeCD()
        with self.assertRaises(RuntimeError) as ctx:
            instance.apply_model_optimization("test-model")
        self.assertIn("CacheDiT model optimizer FAILED", str(ctx.exception))
        self.assertIn("Locked package versions", str(ctx.exception))

    def test_guard_does_not_affect_non_cachedit(self):
        """Non-CacheDiT nodes, when wrapped, still work correctly (no failure)."""
        module = load_comfyapp()
        class OtherNode:
            FUNCTION = "do_stuff"
            def do_stuff(self, x):
                return x * 2

        with patch.object(module, "DISABLE_CACHEDIT_FOR_Z_IMAGE", False):
            result = module._guard_cachedit_node_class(OtherNode)
        # The guard wraps any node with FUNCTION; the wrapper passes through
        self.assertTrue(result)
        self.assertTrue(getattr(OtherNode.do_stuff, "_comfy_modal_guarded", False))
        # Method still works correctly
        instance = OtherNode()
        self.assertEqual(instance.do_stuff(5), 10)


class TestStartupPreimport(unittest.TestCase):
    """Startup snap preimports (transformers, diffusers, cache_dit) without request state."""

    def test_preimport_function_exists(self):
        module = load_modal_app()
        self.assertTrue(hasattr(module, "preimport_cachedit_family"))
        self.assertTrue(callable(module.preimport_cachedit_family))

    def test_preimport_ok_with_fake_packages(self):
        module = load_modal_app()
        _call_log = []

        class FakeImportlibMeta:
            @staticmethod
            def version(pkg):
                versions = {
                    "transformers": "4.55.2",
                    "diffusers": "0.36.0",
                    "cache-dit": "1.2.3",
                }
                return versions.get(pkg, "0.0.0")

        class FakeImportlib:
            metadata = FakeImportlibMeta()
            @staticmethod
            def import_module(name):
                mod = types.ModuleType(name)
                mod.__file__ = f"/fake/path/{name}.py"
                if name == "cache_dit":
                    mod.__version__ = "1.2.3"
                    mod.__title__ = "cache-dit"
                return mod

        result = module.preimport_cachedit_family(
            _importlib=FakeImportlib(),
            _print=lambda *a, **kw: _call_log.append(a),
        )
        if not result["ok"]:
            print(f"DEBUG preimport errors: {result['errors']}", file=sys.stderr)
            print(f"DEBUG preimport versions: {result['versions']}", file=sys.stderr)
        self.assertTrue(result["ok"], f"preimport failed: {result['errors']}")
        self.assertEqual(len(result["errors"]), 0)
        self.assertEqual(result["versions"].get("cache_dit"), "1.2.3")
        self.assertEqual(result["versions"].get("transformers"), "4.55.2")
        self.assertEqual(result["versions"].get("diffusers"), "0.36.0")

    def test_preimport_fails_on_missing_package(self):
        module = load_modal_app()

        class FailImportlib:
            metadata = type("Meta", (), {
                "version": staticmethod(lambda pkg: (_ for _ in ()).throw(Exception("not found")))
            })()
            @staticmethod
            def import_module(name):
                raise ImportError(f"No module {name}")

        result = module.preimport_cachedit_family(_importlib=FailImportlib())
        self.assertFalse(result["ok"])
        self.assertGreater(len(result["errors"]), 0)

    def test_preimport_no_request_state(self):
        """Verify preimport function does not create prompt/timestep/CUDA/session state."""
        module = load_modal_app()
        src = MODAL_APP_PATH.read_text(encoding="utf-8")
        # The function body (excluding docstring) must not contain keywords
        # that imply request/latent/CUDA state creation.
        sensitive = ["torch.cuda", "session_state", "latent", "prompt"]
        for term in sensitive:
            with self.subTest(term=term):
                start = src.find("def preimport_cachedit_family")
                if start >= 0:
                    end = src.find("\ndef ", start + 5)
                    fn_body = src[start:end] if end > start else src[start:]
                    # Skip the docstring (between """ markers)
                    doc_start = fn_body.find('"""')
                    doc_end = fn_body.find('"""', doc_start + 3) if doc_start >= 0 else -1
                    if doc_start >= 0 and doc_end > doc_start:
                        code_body = fn_body[:doc_start] + fn_body[doc_end + 3:]
                    else:
                        code_body = fn_body
                    self.assertNotIn(term, code_body,
                                     f"preimport function code should not contain {term}")


class TestManagerOffline(unittest.TestCase):
    """Manager offline/no-runtime-mutation production behavior."""

    def test_manager_offline_in_bootstrap_config(self):
        # BootstrapConfig defaults: manager_offline=True
        import comfymodal_runtime.runtime_bootstrap as rb
        config = rb.BootstrapConfig()
        self.assertTrue(config.manager_offline)

    @staticmethod
    def _load_runtime_bootstrap():
        """Load and return the real runtime_bootstrap module, cleaning up
        sys.modules afterwards.  Returns (rb_module, cleanup_fn)."""
        mod_before = _module_snapshot()
        import importlib.util as _iu
        sys.modules["comfymodal_runtime"] = types.ModuleType("comfymodal_runtime")
        sys.modules["comfymodal_runtime"].__path__ = [str(REPO_ROOT / "comfymodal_runtime")]
        sys.modules["comfymodal_runtime.trace"] = types.ModuleType("comfymodal_runtime.trace")
        sys.modules["comfymodal_runtime.trace"].RuntimeTrace = MagicMock()
        _rb_path = REPO_ROOT / "comfymodal_runtime" / "runtime_bootstrap.py"
        _rb_spec = _iu.spec_from_file_location("comfymodal_runtime.runtime_bootstrap", str(_rb_path))
        assert _rb_spec is not None and _rb_spec.loader is not None
        _rb_mod = _iu.module_from_spec(_rb_spec)
        sys.modules["comfymodal_runtime.runtime_bootstrap"] = _rb_mod
        _rb_spec.loader.exec_module(_rb_mod)

        def _cleanup():
            _module_restore(mod_before)
        return _rb_mod, _cleanup

    def test_manager_offline_writes_config_ini(self):
        """configure_manager_offline must set network_mode=offline."""
        _rb_mod, _cleanup = self._load_runtime_bootstrap()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                _rb_mod.configure_manager_offline(str(root))
                config_path = root / "user" / "__manager" / "config.ini"
                self.assertTrue(config_path.is_file(), f"config.ini not at {config_path}")
                content = config_path.read_text(encoding="utf-8")
                self.assertIn("network_mode", content)
                self.assertIn("offline", content)
        finally:
            _cleanup()

    def test_manager_offline_sets_env_vars(self):
        _rb_mod, _cleanup = self._load_runtime_bootstrap()
        try:
            env = {}
            _rb_mod.configure_manager_offline("/fake/root", environ=env)
            self.assertEqual(env.get("COMFYUI_MANAGER_MODE"), "offline")
            self.assertEqual(env.get("COMFYUI_MANAGER_NETWORK_MODE"), "offline")
        finally:
            _cleanup()


class TestBF16IdentityCoverage(unittest.TestCase):
    """BF16 CPU snapshot identity/reuse coverage (structural verification)."""

    def test_bf16_native_compute_policy_preserved(self):
        """The BF16-native compute policy symbols must still be referenced
        (defined in cpu_snapshot_models, used by modal_app)."""
        csm_path = REPO_ROOT / "comfymodal_runtime" / "cpu_snapshot_models.py"
        src = csm_path.read_text(encoding="utf-8")
        self.assertIn("_COMPUTE_POLICY_BF16_NATIVE", src,
                      "BF16 native policy constant must be in cpu_snapshot_models")
        # Verify validate_snapshot_unet_bf16_native is still used in modal_app
        ma_src = MODAL_APP_PATH.read_text(encoding="utf-8")
        self.assertIn("validate_snapshot_unet_bf16_native", ma_src)

    def test_manual_cast_dtype_none_preserved(self):
        """The cpu_snapshot_unet_compute_policy lives in model_preload (not cpu_snapshot_models)."""
        mp_src = (REPO_ROOT / "comfymodal_runtime" / "model_preload.py").read_text(encoding="utf-8")
        self.assertIn("cpu_snapshot_unet_compute_policy", mp_src,
                      "cpu_snapshot_unet_compute_policy must be defined in model_preload")


class TestLockFilePathInBuild(unittest.TestCase):
    """The lock file path participates in image rebuild via add_local_file."""

    def test_add_local_file_references_lock(self):
        src = COMFYAPP_PATH.read_text(encoding="utf-8")
        # add_local_file with the lock file
        self.assertIn("add_local_file", src)
        self.assertIn("_CACHEDIT_LOCK_SRC", src)
        self.assertIn("_CACHEDIT_LOCK_DST", src)

    def test_lock_path_constants_defined(self):
        module = load_comfyapp()
        self.assertTrue(hasattr(module, "_CACHEDIT_LOCK_SRC"))
        self.assertTrue(hasattr(module, "_CACHEDIT_LOCK_DST"))
        self.assertTrue(hasattr(module, "_CACHEDIT_LOCK_FILENAME"))
        self.assertEqual(module._CACHEDIT_LOCK_FILENAME, "cachedit_dependency_lock.txt")


class TestNoRuntimeMutation(unittest.TestCase):
    """No request/startup-time mutation of ComfyUI-Manager config."""

    def test_fail_fast_default(self):
        """REQUIREMENTS_REPAIR_MODE must remain fail_fast."""
        module = load_comfyapp()
        self.assertEqual(module.REQUIREMENTS_REPAIR_MODE, "fail_fast")

    def test_manager_config_not_overridden_at_runtime(self):
        """configure_manager_offline uses setdefault, preserving caller values."""
        _rb_mod, _cleanup = TestManagerOffline._load_runtime_bootstrap()
        try:
            env = {"COMFYUI_MANAGER_MODE": "respect_existing"}
            _rb_mod.configure_manager_offline("/fake/root", environ=env)
            self.assertEqual(env.get("COMFYUI_MANAGER_MODE"), "respect_existing")
            self.assertEqual(env.get("COMFYUI_MANAGER_NETWORK_MODE"), "offline")
        finally:
            _cleanup()


# ── Existing test re-runs for BF16 identity/reuse ────────────────────

class TestExistingBF16SnapshotSurvival(unittest.TestCase):
    """Existing CPU snapshot BF16 identity/reuse coverage preserved (source-level)."""

    def test_validate_snapshot_unet_bf16_native_reference_preserved(self):
        """The bf16 validation function must still be defined in cpu_snapshot_models."""
        csm_src = (REPO_ROOT / "comfymodal_runtime" / "cpu_snapshot_models.py").read_text(encoding="utf-8")
        self.assertIn("def validate_snapshot_unet_bf16_native", csm_src,
                      "validate_snapshot_unet_bf16_native must be defined")

    def test_cpu_snapshot_compute_policy_context_manager_preserved(self):
        """The compute policy context manager must still be defined in model_preload."""
        mp_src = (REPO_ROOT / "comfymodal_runtime" / "model_preload.py").read_text(encoding="utf-8")
        self.assertIn("def cpu_snapshot_unet_compute_policy", mp_src,
                      "cpu_snapshot_unet_compute_policy must be defined in model_preload")
        self.assertIn("@contextmanager\ndef cpu_snapshot_unet_compute_policy", mp_src,
                      "cpu_snapshot_unet_compute_policy must be a context manager")


# ── Module-level sys.modules isolation ──────────────────────────────
# Snapshot sys.modules before any test runs; restore after all tests
# so that the next test file in the same pytest process is not polluted.
_modules_before: set[str] = set()


class TestHeredocPythonCompiles(unittest.TestCase):
    """Extract the PYEOF heredoc from the Modal run_commands source,
    render the exact Python script, and verify it compiles+executes
    without SyntaxError (especially f-string backslash regression)."""

    @staticmethod
    def _extract_heredoc_python(filepath: str) -> str:
        # fmt: off
        """Parse comfyapp.py line by line, extract every single-quoted
        Python string literal between the ``<< "PYEOF"`` line and the
        ``'PYEOF...'`` terminator line, decode escape sequences with
        ``ast.literal_eval``, and return the concatenated rendered script."""
        # fmt: on
        import ast

        with open(filepath, encoding="utf-8") as _fh:
            all_lines = _fh.readlines()

        # Find start and end line indices
        start_idx: int | None = None
        end_idx: int | None = None
        for _li, _line in enumerate(all_lines):
            if _line.startswith("#"):
                continue  # skip comment lines to avoid false positives
            if '<< "PYEOF"' in _line and start_idx is None:
                start_idx = _li
            elif start_idx is not None and "'PYEOF" in _line:
                end_idx = _li
                break

        if start_idx is None:
            raise ValueError("Heredoc start '<< \"PYEOF\"' not found")
        if end_idx is None:
            raise ValueError("Heredoc end 'PYEOF' not found")

        body_lines = all_lines[start_idx + 1 : end_idx]

        parts: list[str] = []
        for _line in body_lines:
            stripped = _line.strip()
            if not stripped.startswith("'"):
                continue
            # Grab the string content from the first ' to the closing '
            # (handles the common case: '....\n'  or '...')
            if stripped.endswith("'"):
                pass  # single-line string literal
            else:
                # Handle strings that span multiple source lines via
                # implicit concatenation — each fragment is a valid
                # standalone string literal.
                pass  # take what we have; literal_eval will validate
            if not stripped:
                continue
            try:
                val = ast.literal_eval(stripped)
            except (ValueError, SyntaxError) as _exc:
                # Truncate long chunk for readable error message
                _show = stripped[:80] + "..." if len(stripped) > 80 else stripped
                raise ValueError(f"Failed to decode {_show!r}: {_exc}") from _exc
            parts.append(val)

        return "".join(parts)

    def test_heredoc_extracted_and_rendered(self):
        """The extracted heredoc contains the gate logic with no SyntaxError."""
        script = self._extract_heredoc_python(str(COMFYAPP_PATH))
        self.assertIn("CACHEDIT_LOCK_GATE", script)
        self.assertIn("is_flash_attn_2_available", script)

    def test_heredoc_compiles(self):
        """Rendered heredoc Python must compile to bytecode without error
        (catches f-string backslash, invalid escapes, etc.)."""
        script = self._extract_heredoc_python(str(COMFYAPP_PATH))
        try:
            compile(script, "<cachedit_heredoc>", "exec")
        except SyntaxError as exc:
            self.fail(f"Heredoc script has SyntaxError:\n{exc}\n--- script ---\n{script}")

    def test_heredoc_no_fstring_backslash(self):
        """No rendered line containing an f-string has a backslash inside its
        expression part.  (Backslashes in f-string {} were the original bug.)"""
        script = self._extract_heredoc_python(str(COMFYAPP_PATH))
        for lineno, line in enumerate(script.splitlines(), 1):
            # Look for lines containing f"...{...\...}..."
            if not any(m in line for m in ('f"', "f'")):
                continue
            # Check if a backslash appears between the first { and its matching }
            depth = 0
            in_fstring = False
            in_braces = False
            braces_buf = ""
            for ch in line:
                if ch in ('f', 'F') and not in_fstring:
                    # Check for f" or f'
                    idx = line.find('"') if ch == 'f' else -1
                    pass
            # Simpler heuristic: any line with f" that contains \\ inside {} is suspect
            # But we can just check the rendered f-string expression doesn't have \
            import re
            # Find f-string expression bodies {...}
            for m in re.finditer(r'\{([^}]+)\}', line):
                expr = m.group(1)
                if "\\" in expr:
                    self.fail(
                        f"Line {lineno} f-string expression contains backslash: "
                        f"{expr!r}\n  full line: {line!r}"
                    )

    def test_heredoc_executes_without_imports(self):
        """The gate logic (assignments, loops, data flow) must be
        syntactically executable.  We exec with stubs for the outer
        imports to catch NameErrors in simple data-flow lines."""
        script = self._extract_heredoc_python(str(COMFYAPP_PATH))
        # Build a restricted globals dict with stubs for needed names
        globs: dict = {
            "importlib": __import__("importlib"),
            "transformers": type(sys)("transformers"),
            "diffusers": type(sys)("diffusers"),
            "cache_dit": type(sys)("cache_dit"),
            "__builtins__": __builtins__,
        }
        # The script will fail on `import transformers, diffusers, cache_dit`
        # because those aren't real. We catch that and still verify the
        # gate-specific lines (f-strings, getattr, etc.) are valid by
        # compiling then exec'ing in a minimal namespace.
        try:
            exec(script, globs)
        except (ImportError, ModuleNotFoundError):
            pass  # expected in test environment
        except Exception as exc:
            # Any exception other than ImportError is a signal of a deeper issue
            self.fail(f"Heredoc exec raised unexpected {type(exc).__name__}: {exc}")

    def test_heredoc_fstring_expressions_valid(self):
        """Every f-string expression in the rendered heredoc must be a valid
        standalone Python expression (no SyntaxError when parsed alone)."""
        import ast as _ast
        script = self._extract_heredoc_python(str(COMFYAPP_PATH))
        for lineno, line in enumerate(script.splitlines(), 1):
            if not any(m in line for m in ('f"', "f'")):
                continue
            # Extract expression parts from f-strings
            depth = 0
            expr_start = -1
            for col, ch in enumerate(line):
                if ch == "{":
                    if depth == 0:
                        expr_start = col + 1
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0 and expr_start >= 0:
                        expr = line[expr_start:col]
                        try:
                            compile(expr, f"<fstring_expr_line{lineno}>", "eval")
                        except SyntaxError as exc:
                            self.fail(
                                f"Line {lineno}: f-string expression {expr!r} "
                                f"is not valid Python:\n  {exc}"
                            )
                        expr_start = -1


class TestBuildGateVersionMismatch(unittest.TestCase):
    """Gate must fail closed on version mismatch."""

    def test_import_gate_fails_on_single_version_mismatch(self):
        module = load_comfyapp()

        class MismatchMeta:
            @staticmethod
            def version(pkg):
                versions = {
                    "cache-dit": "9.9.9",  # deliberately wrong
                    "transformers": "4.55.2",
                    "diffusers": "0.36.0",
                    "huggingface-hub": "0.34.4",
                    "accelerate": "1.10.1",
                    "safetensors": "0.5.3",
                    "tokenizers": "0.21.4",
                }
                return versions.get(pkg, "0.0.0")

        class MismatchImportlib:
            metadata = MismatchMeta()
            @staticmethod
            def import_module(name):
                mod = types.ModuleType(name)
                mod.__file__ = f"/fake/path/{name}.py"
                return mod

        result = module._cachedit_import_gate(_importlib=MismatchImportlib())
        self.assertFalse(result["ok"])
        self.assertGreater(len(result["errors"]), 0)
        version_errors = [e for e in result["errors"] if "version mismatch" in e]
        self.assertGreater(len(version_errors), 0,
                           msg=f"Expected version-mismatch error, got: {result['errors']}")
        self.assertIn("cache-dit", version_errors[0])

    def test_import_gate_passes_on_exact_family(self):
        module = load_comfyapp()
        _call_log = []

        class ExactMeta:
            @staticmethod
            def version(pkg):
                versions = {
                    "cache-dit": "1.2.3",
                    "transformers": "4.55.2",
                    "diffusers": "0.36.0",
                    "huggingface-hub": "0.34.4",
                    "accelerate": "1.10.1",
                    "safetensors": "0.5.3",
                    "tokenizers": "0.21.4",
                }
                return versions.get(pkg, "0.0.0")

        class ExactImportlib:
            metadata = ExactMeta()
            @staticmethod
            def import_module(name):
                mod = types.ModuleType(name)
                mod.__file__ = f"/fake/path/{name}.py"
                return mod

        result = module._cachedit_import_gate(
            _importlib=ExactImportlib(),
            _print=lambda *a, **kw: _call_log.append(("print", a, kw)),
        )
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["errors"]), 0)
        self.assertEqual(result["versions"]["cache-dit"], "1.2.3")
        self.assertEqual(result["versions"]["transformers"], "4.55.2")
        self.assertEqual(result["versions"]["diffusers"], "0.36.0")
        self.assertEqual(result["versions"]["huggingface-hub"], "0.34.4")
        self.assertEqual(result["versions"]["accelerate"], "1.10.1")
        self.assertEqual(result["versions"]["safetensors"], "0.5.3")
        self.assertEqual(result["versions"]["tokenizers"], "0.21.4")





def setUpModule():
    global _modules_before
    _modules_before = set(sys.modules)


def tearDownModule():
    _module_restore(_modules_before)


if __name__ == "__main__":
    unittest.main()
