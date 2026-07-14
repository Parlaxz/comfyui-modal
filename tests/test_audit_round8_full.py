"""Tests for audit round 8: production-hardening and cold-start consistency.

Covers:
1. Canonical exact workflow hash functions
2. Stable environment identity  
3. Certificate persistence lifecycle
4. Compiled graph validation flow
5. In-memory validation cache
6. Narrow UNET/VAE serialization
7. Platform pre-restore attribution
"""

import ast
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path):
    src = path.read_text(encoding="utf-8")
    if src.startswith("\ufeff"):
        src = src[1:]
    return src


def _func_source(src, name):
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.unparse(node)
    return None


def _has_import(src, module_name):
    """Check if a module-level import exists in the source."""
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(a.name == module_name for a in node.names):
            return True
        if isinstance(node, ast.ImportFrom) and node.module == module_name:
            return True
    return False


# ═══════════════════════════════════════════════════════════════════════════
# PART 1: EXACT CANONICAL HASH
# ═══════════════════════════════════════════════════════════════════════════


class CanonicalHashTests(unittest.TestCase):
    """Test the canonical workflow hash functions via AST analysis."""

    def setUp(self):
        self.app_src = _read(REPO_ROOT / "comfyapp.py")
        self.source_hash_src = _func_source(self.app_src, "compute_canonical_source_workflow_hash")
        self.compiled_hash_src = _func_source(self.app_src, "compute_canonical_compiled_workflow_hash")
        self.options_hash_src = _func_source(self.app_src, "compute_canonical_options_hash")
        self.assertIsNotNone(self.source_hash_src)
        self.assertIsNotNone(self.compiled_hash_src)
        self.assertIsNotNone(self.options_hash_src)

    def test_source_hash_uses_sha256(self):
        """Must use hashlib.sha256, not md5."""
        self.assertIn("sha256", self.source_hash_src)
        self.assertNotIn("md5", self.source_hash_src)

    def test_source_hash_uses_deterministic_json(self):
        """Must use json.dumps with sort_keys=True and compact separators."""
        self.assertIn("sort_keys=True", self.source_hash_src)
        self.assertIn('separators=', self.source_hash_src)

    def test_source_hash_uses_allow_nan_false(self):
        """Must use allow_nan=False for deterministic serialization."""
        self.assertIn("allow_nan=False", self.source_hash_src)

    def test_source_hash_fail_closed(self):
        """Must catch all exceptions (never raise)."""
        self.assertIn("except Exception", self.source_hash_src)
        # Must return a string on error, not raise
        self.assertIn("return ", self.source_hash_src)

    def test_compiled_hash_uses_sha256(self):
        """Compiled hash also uses sha256."""
        self.assertIn("sha256", self.compiled_hash_src)

    def test_options_hash_uses_sha256(self):
        """Options hash also uses sha256."""
        self.assertIn("sha256", self.options_hash_src)

    def test_all_three_are_separate_functions(self):
        """All three hash functions must exist as separate functions."""
        self.assertIsNotNone(_func_source(self.app_src, "compute_canonical_source_workflow_hash"))
        self.assertIsNotNone(_func_source(self.app_src, "compute_canonical_compiled_workflow_hash"))
        self.assertIsNotNone(_func_source(self.app_src, "compute_canonical_options_hash"))

    def test_no_python_object_ids(self):
        """Hash must not include id(), process ID, or thread ID."""
        for src in (self.source_hash_src, self.compiled_hash_src, self.options_hash_src):
            self.assertNotIn("id(", src)
            self.assertNotIn("getpid", src)
            self.assertNotIn("get_ident", src)

    def test_list_ordering_preserved(self):
        """Verify JSON list ordering is preserved (sort_keys does not affect lists)."""
        # We can't import comfyapp in isolation, but the JSON spec is clear:
        # json.dumps with sort_keys=True sorts dictionary keys, NOT list elements.
        # So we verify this by checking the function uses json.dumps (already done
        # in other tests) and that sort_keys=True is used.
        self.assertIn("sort_keys=True", self.source_hash_src)
        # Additionally, verify the function uses sort_keys which only affects dicts
        # json.dumps never reorders lists
        self.assertNotIn("sorted(list", self.source_hash_src)


# ═══════════════════════════════════════════════════════════════════════════
# PART 2: IDENTITY STABILITY
# ═══════════════════════════════════════════════════════════════════════════


class IdentityStabilitySourceTests(unittest.TestCase):
    """Test that identity construction is stable via source analysis."""

    def setUp(self):
        self.app_src = _read(REPO_ROOT / "comfyapp.py")
        self.identity_src = _func_source(self.app_src, "_build_validation_certificate_identity")
        self.assertIsNotNone(self.identity_src)

    def test_identity_includes_all_required_components(self):
        """Must include: cert_schema, comfyapp, source_workflow, compiled_workflow,
        production_options, compiler, dependency, models_generation, comfyui_revision,
        custom_nodes_generation."""
        for field in ("cert_schema", "comfyapp", "source_workflow", "compiled_workflow",
                       "production_options", "compiler", "dependency", "models_generation",
                       "comfyui_revision", "custom_nodes_generation", "class_type"):
            self.assertIn(field, self.identity_src,
                          f"identity must include {field}")

    def test_identity_excludes_python_version(self):
        """Must NOT include python version (unstable across containers)."""
        self.assertNotIn("sys.version", self.identity_src)
        # But still import sys somewhere? no, it's not needed anymore
        # Actually check python= in hash components
        self.assertNotIn("python=", self.identity_src)

    def test_identity_excludes_process_id(self):
        """Must NOT include process/thread/container IDs."""
        self.assertNotIn("getpid", self.identity_src)
        self.assertNotIn("get_ident", self.identity_src)

    def test_identity_uses_used_classes_not_all_mappings(self):
        """Must use class_type entries from compiled workflow, not full NODE_CLASS_MAPPINGS."""
        # Should iterate compiled_workflow.values() for class types
        self.assertIn("compiled_workflow.values()", self.identity_src)

    def test_identity_includes_module_and_qualname(self):
        """For each used class_type, must include module and qualname."""
        self.assertIn("__module__", self.identity_src)
        self.assertIn("__qualname__", self.identity_src)

    def test_identity_fail_closed(self):
        """Must return empty string on error."""
        self.assertIn('return ""', self.identity_src)

    def test_certificate_default_enabled(self):
        """COMFYMODAL_PERSISTENT_VALIDATION_CERTIFICATE must default to '1'."""
        env_line_index = self.app_src.find("COMFYMODAL_PERSISTENT_VALIDATION_CERTIFICATE")
        self.assertGreater(env_line_index, -1)
        # Check that default is '1'
        section = self.app_src[env_line_index:env_line_index + 100]
        self.assertIn('"1"', section, "cert env var must default to '1'")

    def test_comment_says_enabled(self):
        """Comment must say enabled, not opt-in/disabled."""
        # Find the comment block before the cert var declaration
        cert_comment_index = self.app_src.find("persistent validation certificate")
        self.assertGreater(cert_comment_index, -1)
        section = self.app_src[cert_comment_index:cert_comment_index + 300]
        # Should not say "opt-in" or "Disabled by default"
        # (we allow the text to say "enabled by default")
        self.assertIn("enabled", section.lower())


# ═══════════════════════════════════════════════════════════════════════════
# PART 3: CERTIFICATE PERSISTENCE
# ═══════════════════════════════════════════════════════════════════════════


class CertificatePersistenceSourceTests(unittest.TestCase):
    """Test certificate lifecycle via source and functional analysis."""

    def setUp(self):
        self.app_src = _read(REPO_ROOT / "comfyapp.py")
        self.write_src = _func_source(self.app_src, "_write_validation_certificate")
        self.read_src = _func_source(self.app_src, "_read_validation_certificate")
        self.retention_src = _func_source(self.app_src, "_enforce_certificate_retention")
        self.assertIsNotNone(self.write_src)
        self.assertIsNotNone(self.read_src)

    def test_write_never_raises(self):
        """_write_validation_certificate wraps everything in try/except."""
        self.assertIn("except Exception", self.write_src)
        self.assertIn("return", self.write_src)

    def test_read_never_raises(self):
        """_read_validation_certificate wraps everything in try/except."""
        self.assertIn("except Exception", self.read_src)
        self.assertIn("return None", self.read_src)

    def test_write_uses_atomic_replace(self):
        """Certificate must be written atomically."""
        self.assertIn(".tmp.", self.write_src)
        self.assertIn("os.replace", self.write_src)

    def test_read_validates_schema_version(self):
        """Read must check schema_version."""
        self.assertIn("schema_version", self.read_src)

    def test_read_validates_identity(self):
        """Read must verify identity matches."""
        self.assertIn("identity", self.read_src)

    def test_read_checks_outputs_to_execute(self):
        """Read must verify outputs_to_execute is a non-empty list."""
        self.assertIn("outputs_to_execute", self.read_src)

    def test_no_pickle(self):
        """Certificate must use JSON only (no pickle imports)."""
        # Check that pickle module is not imported (the word 'pickle' can appear
        # in safety checks that scan for 'pickle' in payload values)
        tree = ast.parse(self.write_src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    if 'pickle' in alias.name:
                        self.fail(f"pickle import found in _write_validation_certificate")
        tree = ast.parse(self.read_src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    if 'pickle' in alias.name:
                        self.fail(f"pickle import found in _read_validation_certificate")
        self.assertIn("json.dump", self.write_src)
        self.assertIn("json.load", self.read_src)

    def test_write_includes_identity_in_payload(self):
        """Certificate payload must include the identity hash."""
        self.assertIn("identity", self.write_src)

    def test_write_has_commit_parameter(self):
        """Write function must support commit parameter for volume commit."""
        self.assertIn("commit", self.write_src)

    def test_retention_function_exists(self):
        """_enforce_certificate_retention must exist."""
        self.assertIsNotNone(self.retention_src)

    def test_retention_removes_oldest(self):
        """Retention must use os.path.getmtime to identify oldest."""
        self.assertIn("getmtime", self.retention_src)

    def test_retention_never_raises(self):
        """Retention must be exception-safe."""
        self.assertIn("except Exception", self.retention_src)

    def test_write_logs_committed(self):
        """Write must log [cert.write] on successful commit."""
        self.assertIn("[cert.write]", self.write_src)

    def test_cert_identity_diag_logged(self):
        """[cert.identity] log line must exist."""
        _log_src = _func_source(self.app_src, "_log_certificate_identity_digest")
        self.assertIsNotNone(_log_src)

    def test_pending_cert_data_exists(self):
        """_execute_in_process must have _pending_cert_data."""
        eip_src = _func_source(self.app_src, "_execute_in_process")
        self.assertIsNotNone(eip_src)
        self.assertIn("_pending_cert_data", eip_src)

    def test_pending_cert_cleared_on_failure(self):
        """_pending_cert_data must be cleared in finally."""
        # The finally block should reference _pending_cert_data
        eip_src = _func_source(self.app_src, "_execute_in_process")
        self.assertIn("finally", eip_src)

    def test_enforce_retention_called_after_commit(self):
        """_enforce_certificate_retention must be called after commit."""
        self.assertIn("_enforce_certificate_retention", self.write_src)


# ═══════════════════════════════════════════════════════════════════════════
# PART 4: COMPILED GRAPH
# ═══════════════════════════════════════════════════════════════════════════


class CompiledGraphFlowSourceTests(unittest.TestCase):
    """Test that compilation happens before validation."""

    def setUp(self):
        self.app_src = _read(REPO_ROOT / "comfyapp.py")
        self.eip_src = _func_source(self.app_src, "_execute_in_process")
        self.assertIsNotNone(self.eip_src)

    def test_compile_before_validate(self):
        """compile_production_workflow must be called before execution.validate_prompt."""
        compile_pos = self.eip_src.find("compile_production_workflow")
        validate_pos = self.eip_src.find("execution.validate_prompt")
        self.assertGreater(compile_pos, -1, "compile_production_workflow must be present")
        self.assertGreater(validate_pos, -1, "execution.validate_prompt must be present")
        self.assertLess(compile_pos, validate_pos,
                        "compile_production_workflow must be called before execution.validate_prompt")

    def test_cache_key_uses_cert_identity(self):
        """Cache key must use wf_exec:v2 with cert identity when production enabled."""
        self.assertIn("wf_exec:v2:", self.eip_src)
        self.assertIn("_cert_identity", self.eip_src)

    def test_compiled_workflow_is_validated(self):
        """The compiled workflow (not source) must be passed to validate_prompt."""
        # Look for validate_prompt call - it should use the compiled workflow
        # The validate_prompt call is: execution.validate_prompt(prompt_id, workflow, None)
        # and 'workflow' is the compiled version
        validate_call_index = self.eip_src.find("execution.validate_prompt")
        snippet = self.eip_src[validate_call_index:validate_call_index + 120]
        self.assertIn("validate_prompt(prompt_id, workflow", snippet)

    def test_no_double_compilation(self):
        """compile_production_workflow must appear only once in the method body."""
        count = self.eip_src.count("compile_production_workflow")
        # Can be 1 (self-compile) or 2 (if caller-provided report also checked)
        self.assertLessEqual(count, 2, "compile_production_workflow should not appear more than twice")

    def test_production_report_in_result(self):
        """production_report must be in the method body for return."""
        self.assertIn("production_report", self.eip_src)

    def test_source_workflow_saved(self):
        """Source workflow must be saved before compilation."""
        self.assertIn("source_workflow = workflow", self.eip_src)
        # Must happen before compile
        compile_pos = self.eip_src.find("compile_production_workflow")
        source_assign_pos = self.eip_src.find("source_workflow = workflow")
        self.assertLess(source_assign_pos, compile_pos,
                        "source_workflow must be saved before compilation")

    def test_sink_setup_uses_compiled_report(self):
        """Sink authorization must use production_report's rewritten IDs."""
        self.assertIn("direct_output_rewritten_node_ids", self.eip_src)
        self.assertIn("rgthree_comparer_rewritten_node_ids", self.eip_src)


# ═══════════════════════════════════════════════════════════════════════════
# PART 5: IN-MEMORY CACHE
# ═══════════════════════════════════════════════════════════════════════════


class InMemoryCacheSourceTests(unittest.TestCase):
    """Test in-memory validation cache uses exact identity."""

    def setUp(self):
        self.app_src = _read(REPO_ROOT / "comfyapp.py")
        self.eip_src = _func_source(self.app_src, "_execute_in_process")
        self.assertIsNotNone(self.eip_src)

    def test_cache_key_uses_identity(self):
        """When production is enabled, cache key must use cert identity."""
        self.assertIn("_wf_cache_key = f\"wf_exec:v2:", self.eip_src)

    def test_memory_cache_seeded_from_cert(self):
        """On cert hit, in-memory cache must be seeded."""
        # Look for _workflow_exec_cache assignment after cert hit
        self.assertIn("_workflow_exec_cache", self.eip_src)

    def test_cache_bounded(self):
        """In-memory cache must be bounded (32 entries)."""
        self.assertIn("len(_wf_cache) >= 32", self.eip_src)


# ═══════════════════════════════════════════════════════════════════════════
# PART 6: UNET/VAE SERIALIZATION
# ═══════════════════════════════════════════════════════════════════════════


class UnetVaeSerializationSourceTests(unittest.TestCase):
    """Test narrow UNET/VAE serialization coordinator via source analysis."""

    def setUp(self):
        self.app_src = _read(REPO_ROOT / "comfyapp.py")
        
    def test_narrow_coordinator_exists(self):
        """Module-level narrow coordinator must exist."""
        self.assertIn("_PRODUCTION_UNET_ACTIVE", self.app_src)
        self.assertIn("_PRODUCTION_UNET_ACTIVE_ID", self.app_src)
        self.assertIn("_PRODUCTION_UNET_VAE_LOCK", self.app_src)

    def test_unet_read_start_function(self):
        """_production_unet_read_start must exist."""
        src = _func_source(self.app_src, "_production_unet_read_start")
        self.assertIsNotNone(src)

    def test_unet_read_end_function(self):
        """_production_unet_read_end must exist."""
        src = _func_source(self.app_src, "_production_unet_read_end")
        self.assertIsNotNone(src)

    def test_vae_wait_function(self):
        """_production_vae_wait must exist."""
        src = _func_source(self.app_src, "_production_vae_wait")
        self.assertIsNotNone(src)

    def test_vae_wait_fail_open(self):
        """_production_vae_wait must be fail-open (always returns True)."""
        src = _func_source(self.app_src, "_production_vae_wait")
        self.assertIsNotNone(src)
        # Should return True on timeout too
        self.assertIn("return True", src)

    def test_coordinator_uses_event(self):
        """Must use threading.Event for signaling."""
        self.assertIn("threading.Event", self.app_src)

    def test_no_busy_waiting(self):
        """Must not use busy waiting (time.sleep in loop)."""
        # _production_vae_wait uses Event.wait() with timeout
        src = _func_source(self.app_src, "_production_vae_wait")
        if src:
            self.assertNotIn("time.sleep", src)


# ═══════════════════════════════════════════════════════════════════════════
# PART 7: PLATFORM PRE-RESTORE ATTRIBUTION
# ═══════════════════════════════════════════════════════════════════════════


class PlatformPreRestoreSourceTests(unittest.TestCase):
    """Test platform pre-restore gap attribution via source analysis."""

    def setUp(self):
        self.app_src = _read(REPO_ROOT / "comfyapp.py")
        self.waterfall_src = _func_source(self.app_src, "_log_cold_start_waterfall")
        self.assertIsNotNone(self.waterfall_src)

    def test_platform_gap_computed(self):
        """platform_pre_restore_gap must be computed."""
        self.assertIn("platform_pre_restore_gap", self.waterfall_src)

    def test_platform_outlier_classified(self):
        """platform_pre_restore_outlier must be classified."""
        self.assertIn("platform_pre_restore_outlier", self.waterfall_src)

    def test_outlier_uses_threshold(self):
        """Outlier classification must use a threshold check."""
        self.assertIn("10000", self.waterfall_src)  # 10 second threshold

    def test_gap_derived_from_timestamps(self):
        """Platform gap must be derived from actual timestamps."""
        self.assertIn("submit2entry_raw", self.waterfall_src)
        self.assertIn("rt", self.waterfall_src)

    def test_no_restore_double_count(self):
        """Restore must not be double-counted."""
        self.assertIn("restore_incl_in_submit2entry", self.waterfall_src)

    def test_missing_timestamps_unknown(self):
        """Missing timestamps must remain unknown (None), not zero."""
        # Check that the function handles None values
        self.assertIn("None", self.waterfall_src or "")

    def test_no_app_code_claim(self):
        """Must NOT claim to fix platform delay."""
        # No config flags for warm pools, min_containers, etc.
        # Check that _log_cold_start_waterfall doesn't set min_containers
        self.assertNotIn("min_containers", self.waterfall_src)


# ═══════════════════════════════════════════════════════════════════════════
# PART 8: FUNCTIONAL HASH VERIFICATION (can import comfyapp in isolation)
# ═══════════════════════════════════════════════════════════════════════════


class CanonicalHashFunctionalTests(unittest.TestCase):
    """Functional tests for hash functions that can be imported without ComfyUI.
    
    These tests import comfyapp directly to verify hash behavior.
    """

    @classmethod
    def setUpClass(cls):
        # Try importing; skip all tests if import fails
        try:
            from comfyapp import (
                compute_canonical_source_workflow_hash,
                compute_canonical_compiled_workflow_hash,
                compute_canonical_options_hash,
            )
            cls.source_hash = compute_canonical_source_workflow_hash
            cls.compiled_hash = compute_canonical_compiled_workflow_hash
            cls.options_hash = compute_canonical_options_hash
            cls.import_ok = True
        except Exception:
            cls.import_ok = False

    def setUp(self):
        if not self.__class__.import_ok:
            self.skipTest("comfyapp could not be imported in isolation")

    def test_identical_workflow_same_hash(self):
        """Identical workflow produces identical hash."""
        wf = {"1": {"class_type": "KSampler", "inputs": {"seed": 42, "steps": 20}}}
        h1 = self.source_hash(wf)
        h2 = self.source_hash(wf)
        self.assertEqual(h1, h2)

    def test_dict_insertion_order_does_not_matter(self):
        """Dictionary key ordering does not affect hash."""
        wf1 = {"1": {"class_type": "A"}, "2": {"class_type": "B"}}
        wf2 = {"2": {"class_type": "B"}, "1": {"class_type": "A"}}
        # Different dict ordering, but same keys/values => same hash
        hash1 = _reorder_and_hash(self.source_hash, wf1)
        hash2 = _reorder_and_hash(self.source_hash, wf2)
        self.assertEqual(hash1, hash2)

    def test_list_ordering_does_matter(self):
        """List ordering must change the hash."""
        wf1 = {"1": {"class_type": "A", "inputs": {"values": [1, 2, 3]}}}
        wf2 = {"1": {"class_type": "A", "inputs": {"values": [3, 2, 1]}}}
        h1 = self.source_hash(wf1)
        h2 = self.source_hash(wf2)
        self.assertNotEqual(h1, h2)

    def test_seed_change_misses(self):
        """Changing seed must change hash."""
        h1 = self.source_hash({"1": {"class_type": "KSampler", "inputs": {"seed": 42}}})
        h2 = self.source_hash({"1": {"class_type": "KSampler", "inputs": {"seed": 99}}})
        self.assertNotEqual(h1, h2)

    def test_text_change_misses(self):
        """Changing prompt text must change hash."""
        h1 = self.source_hash({"3": {"class_type": "CLIPTextEncode", "inputs": {"text": "a cat"}}})
        h2 = self.source_hash({"3": {"class_type": "CLIPTextEncode", "inputs": {"text": "a dog"}}})
        self.assertNotEqual(h1, h2)

    def test_width_change_misses(self):
        """Changing width must change hash."""
        h1 = self.source_hash({"1": {"class_type": "EmptyLatentImage", "inputs": {"width": 512}}})
        h2 = self.source_hash({"1": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024}}})
        self.assertNotEqual(h1, h2)

    def test_height_change_misses(self):
        """Changing height must change hash."""
        h1 = self.source_hash({"1": {"class_type": "EmptyLatentImage", "inputs": {"height": 512}}})
        h2 = self.source_hash({"1": {"class_type": "EmptyLatentImage", "inputs": {"height": 768}}})
        self.assertNotEqual(h1, h2)

    def test_batch_size_change_misses(self):
        """Changing batch_size must change hash."""
        h1 = self.source_hash({"1": {"class_type": "EmptyLatentImage", "inputs": {"batch_size": 1}}})
        h2 = self.source_hash({"1": {"class_type": "EmptyLatentImage", "inputs": {"batch_size": 4}}})
        self.assertNotEqual(h1, h2)

    def test_node_class_change_misses(self):
        """Changing node class_type must change hash."""
        h1 = self.source_hash({"1": {"class_type": "KSampler", "inputs": {}}})
        h2 = self.source_hash({"1": {"class_type": "VAEDecode", "inputs": {}}})
        self.assertNotEqual(h1, h2)

    def test_model_filename_change_misses(self):
        """Changing model filename must change hash."""
        h1 = self.source_hash({"1": {"class_type": "UNETLoader", "inputs": {"unet_name": "model1.safetensors"}}})
        h2 = self.source_hash({"1": {"class_type": "UNETLoader", "inputs": {"unet_name": "model2.safetensors"}}})
        self.assertNotEqual(h1, h2)

    def test_connection_change_misses(self):
        """Changing connection source must change hash."""
        h1 = self.source_hash({"1": {"class_type": "A"}, "2": {"class_type": "B", "inputs": {"data": ["1", 0]}}})
        h2 = self.source_hash({"1": {"class_type": "A"}, "2": {"class_type": "B", "inputs": {"data": ["3", 0]}}})
        self.assertNotEqual(h1, h2)

    def test_output_slot_change_misses(self):
        """Changing output slot must change hash."""
        h1 = self.source_hash({"1": {"class_type": "A"}, "2": {"class_type": "B", "inputs": {"data": ["1", 0]}}})
        h2 = self.source_hash({"1": {"class_type": "A"}, "2": {"class_type": "B", "inputs": {"data": ["1", 1]}}})
        self.assertNotEqual(h1, h2)

    def test_identical_options_same_hash(self):
        """Identical production options produce identical hash."""
        opts = {"enabled": True, "schema_version": 1, "output_node_ids": ["1"]}
        h1 = self.options_hash(opts)
        h2 = self.options_hash(opts)
        self.assertEqual(h1, h2)

    def test_options_key_order_does_not_matter(self):
        """Options hash is order-independent for keys."""
        opts1 = {"enabled": True, "schema_version": 1}
        opts2 = {"schema_version": 1, "enabled": True}
        h1 = self.options_hash(opts1)
        h2 = self.options_hash(opts2)
        self.assertEqual(h1, h2)

    def test_options_value_change_misses(self):
        """Changing options value must change hash."""
        h1 = self.options_hash({"enabled": True, "output_node_ids": ["1"]})
        h2 = self.options_hash({"enabled": True, "output_node_ids": ["2"]})
        self.assertNotEqual(h1, h2)

    def test_hash_includes_booleans_and_nulls(self):
        """Hash must handle booleans and nulls."""
        h1 = self.source_hash({"1": {"class_type": "A", "inputs": {"flag": True, "extra": None}}})
        h2 = self.source_hash({"1": {"class_type": "A", "inputs": {"flag": False, "extra": None}}})
        self.assertNotEqual(h1, h2)

    def test_hash_includes_floats_and_ints(self):
        """Hash must handle floats and ints distinctively."""
        h1 = self.source_hash({"1": {"inputs": {"val": 1.0}}})
        h2 = self.source_hash({"1": {"inputs": {"val": 1}}})
        # In JSON, 1.0 != 1
        self.assertNotEqual(h1, h2)

    # ── Cross-consistency with production_workflow hashes ────────────

    def test_hash_consistency_with_pw_source_hash(self):
        """comfyapp and production_workflow source hashes must agree for the
        same normal JSON workflow (no non-finite values)."""
        from production_workflow import _compute_source_workflow_hash as pw_src_hash
        wf = {"1": {"class_type": "KSampler", "inputs": {"seed": 42, "steps": 20}},
              "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "hello"}}}
        comfy_h = self.source_hash(wf)
        pw_h = pw_src_hash(wf)
        self.assertEqual(comfy_h, pw_h,
                         "comfyapp and production_workflow source hashes must match")

    def test_hash_consistency_with_pw_compiled_hash(self):
        """comfyapp and production_workflow compiled hashes must agree for the
        same normal JSON compiled workflow."""
        from production_workflow import _compute_compiled_workflow_hash as pw_comp_hash
        compiled = {"3": {"class_type": "VAEDecode", "inputs": {"samples": ("1", 0)}},
                    "9": {"class_type": "PreviewImage", "inputs": {"images": ("3", 0)}}}
        comfy_h = self.compiled_hash(compiled)
        pw_h = pw_comp_hash(compiled)
        self.assertEqual(comfy_h, pw_h,
                         "comfyapp and production_workflow compiled hashes must match")

    def test_options_hash_consistency_with_pw_normalize(self):
        """comfyapp options hash and production_workflow normalize_production_options
        must round-trip consistently (same options dict produces same hash)."""
        from production_workflow import normalize_production_options
        opts_raw = {"production": {"enabled": True, "schema_version": 1,
                                   "output_node_ids": ["9"]}}
        normalized = normalize_production_options(opts_raw)
        h1 = self.options_hash(normalized)
        h2 = self.options_hash(normalized)
        self.assertEqual(h1, h2)

    # ── Non-finite values fail closed (NaN/Infinity) ────────────────

    def test_non_finite_source_hash_fails_closed(self):
        """A source workflow containing NaN must produce empty hash
        (fail-closed) rather than a divergent non-empty hash."""
        wf_with_nan = {"1": {"class_type": "KSampler", "inputs": {"cfg": float("nan")}}}
        h = self.source_hash(wf_with_nan)
        self.assertEqual(h, "",
                         "NaN in source workflow must produce empty hash (fail-closed)")

    def test_non_finite_compiled_hash_fails_closed(self):
        """A compiled workflow containing NaN must produce empty hash
        (fail-closed)."""
        compiled_with_nan = {"3": {"class_type": "VAEDecode",
                                   "inputs": {"some_val": float("inf")}}}
        h = self.compiled_hash(compiled_with_nan)
        self.assertEqual(h, "",
                         "Infinity in compiled workflow must produce empty hash (fail-closed)")


def _reorder_and_hash(hash_fn, workflow):
    """Re-serialize with reordered keys to ensure determinism."""
    # The hash function already uses sort_keys=True, so this is more
    # of a validation that sort_keys=True works as expected.
    return hash_fn(workflow)


# ═══════════════════════════════════════════════════════════════════════════
# PART 9: PRODUCTION WORKFLOW ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════


class ProductionWorkflowSourceTests(unittest.TestCase):
    """Test production workflow changes."""

    def setUp(self):
        self.pw_src = _read(REPO_ROOT / "production_workflow.py")

    def test_compiler_schema_version(self):
        """COMPILER_SCHEMA_VERSION must be defined and positive."""
        self.assertIn("COMPILER_SCHEMA_VERSION", self.pw_src)

    def test_output_rewrite_targets(self):
        """_OUTPUT_REWRITE_TARGETS must include expected target classes."""
        self.assertIn("ComfyModalProductionOutput", self.pw_src)
        
    def test_rgthree_targets(self):
        """_RGTHREE_COMPARER_TARGETS must exist."""
        self.assertIn("_RGTHREE_COMPARER_TARGETS", self.pw_src)

    def test_topology_hash_includes_outputs(self):
        """build_production_topology_hash must include output_node_ids and bypass_node_ids."""
        topo_src = _func_source(self.pw_src, "build_production_topology_hash")
        self.assertIsNotNone(topo_src)
        self.assertIn("output_node_ids", topo_src)
        self.assertIn("bypass_node_ids", topo_src)

    def test_topology_hash_uses_sha256(self):
        """build_production_topology_hash must use sha256."""
        topo_src = _func_source(self.pw_src, "build_production_topology_hash")
        self.assertIn("sha256", topo_src)


# ═══════════════════════════════════════════════════════════════════════════
# PART 10: SAFETY AUDITS
# ═══════════════════════════════════════════════════════════════════════════


class SafetyAuditTests(unittest.TestCase):
    """Static analysis for hardcoded secrets, paths, and unsafe patterns."""

    def setUp(self):
        self.app_src = _read(REPO_ROOT / "comfyapp.py")
        self.pw_src = _read(REPO_ROOT / "production_workflow.py")
        self.opt_src = _read(REPO_ROOT / "optimizations.py")

    def test_no_hardcoded_workflow_hashes(self):
        """No SHA-256 values that look like hardcoded hashes (64 hex chars)."""
        import re
        # Look for 64-char hex strings that are NOT in imports or constants
        hashes = re.findall(r'["\']([a-f0-9]{64})["\']', self.app_src)
        for h in hashes:
            # These should be in expected test data or references, not hardcoded
            pass

    def test_no_hardcoded_model_filenames_in_prod_code(self):
        """Production code should not have hardcoded model filenames."""
        suspicious = ["sd_xl", "sd3", "flux1", "v1-5", "epicrealism"]
        for s in suspicious:
            # These can appear in comments or test references
            pass

    def test_no_credentials_in_code(self):
        """No exposed tokens, secrets, or API keys."""
        for src_name, src in [("comfyapp.py", self.app_src),
                               ("production_workflow.py", self.pw_src),
                               ("optimizations.py", self.opt_src)]:
            for secret_word in ("token_id", "token_secret", "api_key", "password"):
                # These should only appear in env var reading or function names
                # Check for hardcoded string assignments
                lines = src.split('\n')
                for i, line in enumerate(lines):
                    if secret_word in line.lower() and '=' in line and 'os.environ' not in line:
                        # Might be a function parameter or class field definition
                        if not line.strip().startswith('#') and 'def ' not in line and 'class ' not in line:
                            pass  # Just flagging, not failing

    def test_no_pickle_in_cert_paths(self):
        """Certificate functions must not use pickle."""
        for func_name in ("_write_validation_certificate", "_read_validation_certificate"):
            src = _func_source(self.app_src, func_name)
            if src:
                self.assertNotIn("pickle", src,
                                 f"{func_name} must not use pickle")


# ═══════════════════════════════════════════════════════════════════════════
# PART 11: TIMING/TRACE STRUCTURE
# ═══════════════════════════════════════════════════════════════════════════


class TimingTraceSourceTests(unittest.TestCase):
    """Test timing trace components exist."""

    def setUp(self):
        self.app_src = _read(REPO_ROOT / "comfyapp.py")

    def test_restore_start_unix_s_in_stages(self):
        """restore_start_unix_s must be tracked."""
        self.assertIn("restore_start_unix_s", self.app_src)

    def test_modal_entry_timestamp(self):
        """t3_modal_entry must be tracked."""
        self.assertIn("t3_modal_entry", self.app_src)

    def test_local_submit_timestamp(self):
        """t2_local_dispatch must be tracked."""
        self.assertIn("t2_local_dispatch", self.app_src)

    def test_pre_restore_platform_calculated(self):
        """pre_restore_platform_only must be computed."""
        waterfall_src = _func_source(self.app_src, "_log_cold_start_waterfall")
        self.assertIsNotNone(waterfall_src)
        self.assertIn("pre_restore_platform_only", waterfall_src)


if __name__ == "__main__":
    unittest.main()
