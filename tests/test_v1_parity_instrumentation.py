"""Focused tests for Phase 7 V1 parity instrumentation.

Covers:
  1. V1 deployment identity capture function exists and returns expected keys.
  2. V1 profile publication markers present in run_prompt_stream.
  3. V1 GPU submission markers present in run_prompt_stream.
  4. V1 identity merged into first stream event.
  5. V1 output_collect / return_packaging markers present in comfyapp.py.
  6. V1 deployment identity in comfyapp.py remote entry.
  7. No sensitive fields (token, secret, password, prompt text) in identity.
  8. Instrumentation does not change existing payload shape (type/phase).
  9. No local diagnostic timeout wrapper around first-event iteration.
 10. No explicit generator-close in modal_client stream functions.
 11. Authoritative remote identity fields present in comfyapp.py first-stream-event.
"""

import ast
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODAL_CLIENT_PATH = REPO_ROOT / "modal_client.py"
COMFYAPP_PATH = REPO_ROOT / "comfyapp.py"


class TestV1IdentityCapture(unittest.TestCase):
    """V1 deployment identity: _capture_v1_deployment_identity exists and has correct shape."""

    def test_capture_identity_function_exists(self):
        source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        self.assertIn("def _capture_v1_deployment_identity", source)

    def test_capture_identity_returns_app_name(self):
        source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        self.assertIn('"app_name"', source)
        self.assertIn("APP_NAME", source)

    def test_capture_identity_returns_gpu(self):
        source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        self.assertIn('"gpu":', source)
        self.assertIn("selected_gpu", source)

    def test_capture_identity_returns_runtime_mode(self):
        source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        self.assertIn('"runtime_mode": "v1"', source)

    def test_capture_identity_returns_class_and_method(self):
        source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        self.assertIn('"class_name"', source)
        self.assertIn('"method_name"', source)

    def test_capture_identity_returns_cloud_and_region(self):
        source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        self.assertIn('"cloud":', source)
        self.assertIn('"region":', source)

    def test_capture_identity_no_sensitive_fields(self):
        """Verify no credentials/tokens leak into the identity dict."""
        source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        # Check that token_secret, token_id, password are NOT in identity keys
        tree = ast.parse(source)
        # Look for all dict keys in the _capture_v1_deployment_identity function
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for key in node.keys:
                    if isinstance(key, ast.Constant):
                        val = str(key.value)
                        self.assertNotIn("token", val.lower(),
                                         f"identity dict must not contain credential field: {val}")
                        self.assertNotIn("secret", val.lower(),
                                         f"identity dict must not contain credential field: {val}")
                        self.assertNotIn("password", val.lower(),
                                         f"identity dict must not contain credential field: {val}")
                        self.assertNotIn("credential", val.lower(),
                                         f"identity dict must not contain credential field: {val}")


class TestV1SnapshotIdentity(unittest.TestCase):
    """V1 snapshot identity: snapshot_enabled vs gpu_snapshot_enabled semantics."""

    def test_snapshot_enabled_is_true(self):
        """snapshot_enabled must be True (V1 always has enable_memory_snapshot=True)."""
        source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        func = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_capture_v1_deployment_identity":
                func = node
                break
        self.assertIsNotNone(func)
        found = False
        for node in ast.walk(func):
            if isinstance(node, ast.Dict):
                for key, val in zip(node.keys, node.values):
                    if isinstance(key, ast.Constant) and key.value == "snapshot_enabled":
                        self.assertIsInstance(val, ast.Constant,
                                              "snapshot_enabled value must be a literal constant")
                        self.assertTrue(val.value,
                                        "snapshot_enabled must be True (V1 always has enable_memory_snapshot=True)")
                        found = True
        self.assertTrue(found, "snapshot_enabled key not found in identity dict")

    def test_gpu_snapshot_enabled_uses_env_var(self):
        """gpu_snapshot_enabled must be controlled by COMFYMODAL_ENABLE_GPU_SNAPSHOT."""
        source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        func = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_capture_v1_deployment_identity":
                func = node
                break
        self.assertIsNotNone(func)
        found = False
        for node in ast.walk(func):
            if isinstance(node, ast.Dict):
                for key, val in zip(node.keys, node.values):
                    if isinstance(key, ast.Constant) and key.value == "gpu_snapshot_enabled":
                        source_segment = ast.get_source_segment(source, val)
                        self.assertIsNotNone(source_segment)
                        self.assertIn("COMFYMODAL_ENABLE_GPU_SNAPSHOT", source_segment,
                                      "gpu_snapshot_enabled must read COMFYMODAL_ENABLE_GPU_SNAPSHOT env var")
                        self.assertNotEqual(source_segment.strip(), "True",
                                            "gpu_snapshot_enabled must not be a hardcoded True")
                        found = True
        self.assertTrue(found, "gpu_snapshot_enabled key not found in identity dict")

    def test_snapshot_and_gpu_snapshot_are_distinct(self):
        """snapshot_enabled and gpu_snapshot_enabled must be different expressions."""
        source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        func = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_capture_v1_deployment_identity":
                func = node
                break
        self.assertIsNotNone(func)
        snapshot_expr = None
        gpu_snapshot_expr = None
        for node in ast.walk(func):
            if isinstance(node, ast.Dict):
                for key, val in zip(node.keys, node.values):
                    if isinstance(key, ast.Constant):
                        if key.value == "snapshot_enabled":
                            snapshot_expr = ast.get_source_segment(source, val)
                        elif key.value == "gpu_snapshot_enabled":
                            gpu_snapshot_expr = ast.get_source_segment(source, val)
        self.assertIsNotNone(snapshot_expr, "snapshot_enabled key not found")
        self.assertIsNotNone(gpu_snapshot_expr, "gpu_snapshot_enabled key not found")
        self.assertNotEqual(snapshot_expr, gpu_snapshot_expr,
                            "snapshot_enabled and gpu_snapshot_enabled must have different values")


class TestV1ProfilePublicationMarkers(unittest.TestCase):
    """V1 profile publication markers: profile_publish_start/end."""

    def test_profile_publish_start_marker(self):
        source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        self.assertIn('trace["profile_publish_start"]', source)

    def test_profile_publish_end_marker(self):
        source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        self.assertIn('trace["profile_publish_end"]', source)

    def test_profile_publish_diag_log(self):
        source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        self.assertIn("phase=profile_publish", source)


class TestV1GpuSubmissionMarkers(unittest.TestCase):
    """V1 GPU submission markers: gpu_submission_start/end."""

    def test_gpu_submission_start_marker(self):
        source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        self.assertIn('trace["gpu_submission_start"]', source)

    def test_gpu_submission_end_marker(self):
        source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        self.assertIn('trace["gpu_submission_end"]', source)

    def test_gpu_submit_to_first_event_ns_marker(self):
        source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        self.assertIn('trace["gpu_submit_to_first_event_ns"] =', source)
        self.assertIn('trace["gpu_submit_to_first_event_ms"] =', source)
        self.assertIn("_delta_s", source)


class TestV1IdentityFirstEvent(unittest.TestCase):
    """V1 identity merged into first stream event."""

    def test_first_event_identity_merge(self):
        source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        self.assertIn("v1_identity", source)
        self.assertIn("first_msg.setdefault", source)


class TestV1ComfyappIdentityMarkers(unittest.TestCase):
    """V1 deployment identity at remote entry in comfyapp.py."""

    def test_v1_diag_log_in_run_prompt_stream(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn("[v1.diag] phase=remote_entry", source)

    def test_v1_identity_in_result(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn('_r["v1_identity"]', source)

    def test_container_session_id_in_v1_identity(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn("container_session_id", source)


class TestV1OutputCollectMarkers(unittest.TestCase):
    """V1 output collection and return packaging markers in comfyapp.py."""

    def test_output_collect_start_marker(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn('trace.setdefault("output_collect_start"', source)

    def test_output_collect_end_marker(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn('trace.setdefault("output_collect_end"', source)

    def test_return_packaging_start_marker(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn('trace["return_packaging_start"]', source)

    def test_return_packaging_end_marker(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn('trace["return_packaging_end"]', source)

    def test_remote_return_start_marker(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn('trace["remote_return_start"]', source)

    def test_remote_return_end_marker(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn('trace["remote_return_end"]', source)


class TestV1PayloadShapeInvariant(unittest.TestCase):
    """Instrumentation must not change existing event type/phase semantics."""

    def test_run_prompt_stream_result_type_unchanged(self):
        """The 'result' event must still have type='result' and data key."""
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn('yield {"type": "result", "data": _result[0]}', source)

    def test_run_prompt_stream_error_type_unchanged(self):
        """The 'error' event must still have type='error'."""
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn('yield {"type": "error", "message": str(_error[0])}', source)

    def test_run_prompt_stream_status_type_unchanged(self):
        """Status events must still carry phase/message."""
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        for phase in ("restore", "custom_nodes", "gpu", "warmup", "execution"):
            self.assertIn(f'"phase": "{phase}"', source,
                          f"status phase '{phase}' must be preserved")

    def test_run_prompt_stream_accepts_same_signature(self):
        """run_prompt_stream signature must not change."""
        source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        func = None
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "run_prompt_stream":
                func = node
                break
        self.assertIsNotNone(func)
        arg_names = [arg.arg for arg in func.args.args]
        self.assertEqual(
            arg_names,
            ["workflow", "input_images", "trace", "production_report", "gpu", "modal_options", "workspace"],
            f"run_prompt_stream signature must not change, got: {arg_names}",
        )


class TestV1GetIdentityAccessor(unittest.TestCase):
    """V1 get_v1_deployment_identity accessor."""

    def test_get_identity_function_exists(self):
        source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        self.assertIn("def get_v1_deployment_identity", source)

    def test_get_identity_returns_dict(self):
        """Verify get_v1_deployment_identity returns _V1_DEPLOYMENT_METADATA copy."""
        source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        self.assertIn("return dict(_V1_DEPLOYMENT_METADATA)", source)


class TestV1ResultPayloadShape(unittest.TestCase):
    """Verify V1 result payload shape unchanged."""

    def test_comfyapp_execute_in_process_return_shape_preserved(self):
        """_execute_in_process must still return result dict with images/videos/outputs."""
        source = COMFYAPP_PATH.read_text(encoding="utf-8-sig")
        self.assertIn('result = self._collect_in_process_outputs', source)
        self.assertIn('images,', source)
        self.assertIn('videos,', source)


class TestV1TimeoutAbsence(unittest.TestCase):
    """No local diagnostic timeout wrapper around first-event iteration."""

    def test_no_stream_first_event_timeout_constant(self):
        """_STREAM_FIRST_EVENT_TIMEOUT must not exist in modal_client.py."""
        source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        self.assertNotIn("_STREAM_FIRST_EVENT_TIMEOUT", source)

    def test_no_stream_first_event_timeout_constant_in_transport(self):
        """_STREAM_FIRST_EVENT_TIMEOUT must not exist in modal_transport.py."""
        transport_path = REPO_ROOT / "comfymodal_runtime" / "modal_transport.py"
        source = transport_path.read_text(encoding="utf-8")
        self.assertNotIn("_STREAM_FIRST_EVENT_TIMEOUT", source)

    def test_no_asyncio_wait_for_on_first_event(self):
        """run_prompt_stream must NOT use asyncio.wait_for on gen.__anext__()."""
        source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        # asyncio.wait_for may appear for CONTROL_RPC_TIMEOUT, but NOT
        # wrapping gen.__anext__(). The text pattern below should be absent.
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "wait_for":
                    for arg in node.args:
                        if isinstance(arg, ast.Call):
                            inner = arg.func
                            if isinstance(inner, ast.Attribute) and inner.attr == "__anext__":
                                self.fail("asyncio.wait_for wrapping gen.__anext__() found in modal_client.py")

    @staticmethod
    def _has_exception_suppressed_aclose(stmts: list[ast.stmt]) -> bool:
        """Check if *stmts* contain a try/except Exception: pass wrapping gen.aclose().
        
        The try/except is nested inside ``if gen is not None:``, so we
        traverse ``If.body`` as well as top-level finalbody statements.
        """
        candidates: list[ast.stmt] = []
        for stmt in stmts:
            candidates.append(stmt)
            if isinstance(stmt, ast.If):
                candidates.extend(stmt.body)
        for stmt in candidates:
            if not isinstance(stmt, ast.Try):
                continue
            for handler in stmt.handlers:
                if not isinstance(handler, ast.ExceptHandler):
                    continue
                if not (isinstance(handler.type, ast.Name) and handler.type.id == "Exception"):
                    continue
                if not handler.body or not all(isinstance(s, ast.Pass) for s in handler.body):
                    continue
                for body_stmt in stmt.body:
                    if (isinstance(body_stmt, ast.Expr) and
                        isinstance(body_stmt.value, ast.Await) and
                        isinstance(body_stmt.value.value, ast.Call) and
                        isinstance(body_stmt.value.value.func, ast.Attribute) and
                        body_stmt.value.value.func.attr == "aclose"):
                        return True
        return False

    def test_cleanup_finally_in_run_prompt_stream(self):
        """run_prompt_stream must have finally block with try/except Exception: pass wrapping gen.aclose()."""
        source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        func = None
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "run_prompt_stream":
                func = node
                break
        self.assertIsNotNone(func)
        found_cleanup = False
        for node in ast.walk(func):
            if isinstance(node, ast.Try) and node.finalbody:
                if self._has_exception_suppressed_aclose(node.finalbody):
                    found_cleanup = True
        self.assertTrue(found_cleanup,
                        "run_prompt_stream must have finally block with "
                        "try/except Exception: pass wrapping gen.aclose()")

    def test_cleanup_finally_in_run_checkpoint_stream(self):
        """run_checkpoint_stream must have finally block with try/except Exception: pass wrapping gen.aclose()."""
        source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        func = None
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "run_checkpoint_stream":
                func = node
                break
        self.assertIsNotNone(func)
        found_cleanup = False
        for node in ast.walk(func):
            if isinstance(node, ast.Try) and node.finalbody:
                if self._has_exception_suppressed_aclose(node.finalbody):
                    found_cleanup = True
        self.assertTrue(found_cleanup,
                        "run_checkpoint_stream must have finally block with "
                        "try/except Exception: pass wrapping gen.aclose()")


class TestV1RemoteIdentityFields(unittest.TestCase):
    """Authoritative remote identity fields present in comfyapp.py first-stream-event."""

    def test_first_stream_event_has_v1_identity(self):
        """The 'execution' phase yield must contain v1_identity."""
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn('"v1_identity": _v1_remote_identity', source)

    def test_remote_identity_has_task_id(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn('"task_id"', source)

    def test_remote_identity_has_image_id(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn('"image_id"', source)

    def test_remote_identity_has_modal_input_id(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn('"modal_input_id"', source)

    def test_remote_identity_has_cloud_provider(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn('"cloud_provider"', source)

    def test_remote_identity_has_region(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn('"region"', source)

    def test_remote_identity_has_container_session_id(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn('"container_session_id"', source)

    def test_remote_identity_has_restore_session_id(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn('"restore_session_id"', source)

    def test_remote_identity_has_request_seq(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn('"request_seq"', source)

    def test_remote_identity_has_environment(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn('"environment"', source)

    def test_remote_identity_has_function_id(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn('"function_id"', source)

    def test_remote_identity_has_restore_count(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn('"restore_count"', source)

    def test_remote_identity_no_client_generated_uuid(self):
        """Client-side container_session_id must NOT use uuid.uuid4().hex[:16]."""
        source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        self.assertNotIn("uuid.uuid4", source)

    def test_remote_identity_no_client_modal_env_vars(self):
        """Client-side must NOT read MODAL_TASK_ID or MODAL_IMAGE_ID as authoritative."""
        client_source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        # The client _capture_v1_deployment_identity must NOT reference MODAL_TASK_ID
        self.assertNotIn("MODAL_TASK_ID", client_source)
        self.assertNotIn("MODAL_IMAGE_ID", client_source)
        self.assertNotIn("MODAL_INPUT_ID", client_source)
        self.assertNotIn("MODAL_CPU", client_source)
        self.assertNotIn("MODAL_MEMORY_MB", client_source)


class TestV1SemanticPreservation(unittest.TestCase):
    """Existing V1 execution order and payload types are preserved."""

    def test_run_prompt_stream_still_extracts_first_msg(self):
        """run_prompt_stream still captures the first event inside async iteration."""
        source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        self.assertIn("first_msg", source)
        self.assertIn("async for msg in gen", source)

    def test_run_prompt_stream_still_yields_first_msg(self):
        """The first message is still yielded through the existing async loop."""
        source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        self.assertIn("yield msg", source)

    def test_v1_result_collection_preserved(self):
        """V1 result body collection pattern preserved."""
        source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        self.assertIn("_v1_result = None", source)
        self.assertIn('if isinstance(msg, dict) and msg.get("type") == "result"', source)

    def test_first_msg_identity_merge_preserved(self):
        """first_msg.setdefault pattern for identity merge is preserved."""
        source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        self.assertIn("first_msg.setdefault", source)
        self.assertIn(".setdefault(_ik, _iv)", source)

    def test_v1_identity_in_trace_preserved(self):
        """trace['v1_identity'] still set."""
        source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        self.assertIn('trace["v1_identity"]', source)

    def test_first_remote_message_received_marker_preserved(self):
        """first_remote_message_received timing marker preserved."""
        source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        self.assertIn("first_remote_message_received", source)


if __name__ == "__main__":
    unittest.main()
