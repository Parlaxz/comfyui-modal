"""Stable, diagnosable error responses for the Studio run endpoint."""

from __future__ import annotations

from studio_run_adapter import _STABLE_INTERNAL_ERROR, _execution_error_response


def test_execution_error_response_is_stable_and_structured():
    payload = _execution_error_response(
        RuntimeError("backend token must not become user-facing copy"),
        operation="studio_run_route",
        run_id="run-123",
    )

    assert payload["status"] == "error"
    assert payload["message"] == _STABLE_INTERNAL_ERROR
    assert payload["error_code"] == "STUDIO_EXECUTION_ERROR"
    assert payload["error"]["operation"] == "studio_run_route"
    assert payload["error"]["run_id"] == "run-123"
    assert "RuntimeError" in payload["error"]["detail"]
    assert "backend token" in payload["error"]["detail"]


def test_stable_message_contains_no_request_specific_details():
    assert "backend token" not in _STABLE_INTERNAL_ERROR
    assert "traceback" not in _STABLE_INTERNAL_ERROR.lower()
    assert "\n" not in _STABLE_INTERNAL_ERROR
