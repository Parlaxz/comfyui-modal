"""Small, dependency-free helpers for constructing Golden requests."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import tomllib
from typing import Any


GOLDEN_P1_MODE = "golden_p1_serial"
GOLDEN_PARALLEL_MODE = "golden_p1_parallel"
GOLDEN_ATTENTION_BACKENDS = ("pytorch", "sage", "comfy_kitchen")


def _contains_true_selector(value: Any, selector: str) -> bool:
    """Find a truthy selector in request-owned metadata without mutating it."""
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).strip().lower() == selector and child is True:
                return True
            if _contains_true_selector(child, selector):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_true_selector(child, selector) for child in value)
    return False


def _profile_deploy_environment(name: str) -> str | None:
    """Read one deploy-owned flag for a local run harness.

    v2ctl deliberately does not copy deploy-only flags from the ambient shell
    into the benchmark subprocess.  The request still needs an identity echo
    for restore-owned architecture validation, so read only the selected
    profile's declarative environment when the caller did not provide a value.
    """
    profile = str(os.environ.get("COMFYMODAL_V2CTL_PROFILE") or "").strip()
    if profile and not any(token in profile for token in ("/", "\\", "..")):
        filename = profile if profile.endswith(".toml") else f"{profile}.toml"
        path = Path(__file__).resolve().parents[2] / "config" / "v2" / "profiles" / filename
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
            value = (data.get("environment") or {}).get(name)
            if value is not None:
                return str(value)
        except (OSError, ValueError, TypeError):
            pass

    # The Windows run wrapper may not preserve the profile name, but v2ctl
    # still carries the config-owned app/deployment identity.  Resolve the
    # exact receipt rather than selecting a newest file by mtime.
    app = str(os.environ.get("COMFYMODAL_V2_APP_NAME") or "").strip()
    fingerprint = str(os.environ.get("COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT") or "").strip()
    if not app and not fingerprint:
        return None
    deployment_dir = Path(__file__).resolve().parents[2] / ".v2ctl" / "deployments"
    matches: list[str] = []
    for receipt_path in sorted(deployment_dir.glob("receipt_*.json")):
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            target = receipt.get("target") or receipt.get("deployment_identity") or {}
            target_app = str(target.get("app") or target.get("app_name") or "")
            if app and target_app != app:
                continue
            if fingerprint and str(receipt.get("deploy_fingerprint") or "") != fingerprint:
                continue
            value = (receipt.get("effective_environment") or {}).get(name)
            if value is None:
                receipt_profile = str(receipt.get("profile") or "").strip()
                if receipt_profile and not any(token in receipt_profile for token in ("/", "\\", "..")):
                    filename = receipt_profile if receipt_profile.endswith(".toml") else f"{receipt_profile}.toml"
                    profile_path = Path(__file__).resolve().parents[2] / "config" / "v2" / "profiles" / filename
                    try:
                        profile_data = tomllib.loads(profile_path.read_text(encoding="utf-8"))
                        value = (profile_data.get("environment") or {}).get(name)
                    except (OSError, ValueError, TypeError):
                        value = None
            if value is not None:
                matches.append(str(value))
        except (OSError, ValueError, TypeError):
            continue
    return matches[0] if len(set(matches)) == 1 else None


def _golden_p1_request_payload(
    source: dict[str, Any],
    *,
    request_id: str,
    index: int,
    attention_backend: str | None = None,
    golden_mode: str = "serial",
    invocation_id: str | None = None,
    cpu_qd2_prefetch: bool = False,
    deep_trace: bool = False,
    c0_mmap_lifecycle: str | None = None,
    c0_source_threads: bool | None = None,
    source_policy: str | None = None,
    source_launch_gap_ns: int | str | None = None,
    microscope_mode: str | None = None,
    qd_mode: str | None = None,
) -> dict[str, Any]:
    if not isinstance(cpu_qd2_prefetch, bool):
        raise ValueError("golden_cpu_qd2_prefetch_must_be_bool")
    if not isinstance(deep_trace, bool):
        raise ValueError("golden_deep_trace_must_be_bool")
    if c0_source_threads is None:
        c0_source_threads = str(
            os.environ.get("COMFYMODAL_GOLDEN_C0_SOURCE_THREADS")
            or _profile_deploy_environment("COMFYMODAL_GOLDEN_C0_SOURCE_THREADS")
            or "0"
        ).strip().lower() in {"1", "true", "yes", "on"}
    if not isinstance(c0_source_threads, bool):
        raise ValueError("golden_c0_source_threads_must_be_bool")
    lifecycle = str(
        c0_mmap_lifecycle
        if c0_mmap_lifecycle is not None
        else (
            os.environ.get("COMFYMODAL_GOLDEN_C0_MMAP_LIFECYCLE")
            or _profile_deploy_environment("COMFYMODAL_GOLDEN_C0_MMAP_LIFECYCLE")
            or ("whole" if c0_source_threads else "fresh")
        )
    ).strip().lower()
    if lifecycle not in {"fresh", "whole", "epoch"}:
        raise ValueError("golden_c0_mmap_lifecycle_invalid")
    if cpu_qd2_prefetch and _contains_true_selector(source, "instant_tensor"):
        raise ValueError("golden_cpu_qd2_prefetch_instant_tensor_conflict")
    mode = str(golden_mode).strip().lower()
    if mode not in {"serial", "parallel"}:
        raise ValueError("golden_mode_invalid")
    payload = {
        "request_id": request_id,
        "prompt": copy.deepcopy(source["prompt"]),
        "extra_data": copy.deepcopy(source["extra_data"]),
        "modal_options": copy.deepcopy(source["modal_options"]),
        "request_origin_info": {
            "benchmark_mode": GOLDEN_P1_MODE if mode == "serial" else GOLDEN_PARALLEL_MODE,
            "golden_mode": mode,
            "golden_p1_run_index": index,
            "golden_p1_request_id": request_id,
            "serial": mode == "serial",
        },
    }
    normalized = (
        "sage"
        if attention_backend is None
        else str(attention_backend).strip().lower()
    )
    if normalized not in GOLDEN_ATTENTION_BACKENDS:
        raise ValueError(
            "golden attention backend must be one of: "
            + ", ".join(GOLDEN_ATTENTION_BACKENDS)
        )
    payload["attention_backend"] = normalized
    payload["c0_mmap_lifecycle"] = lifecycle
    payload["request_origin_info"]["c0_mmap_lifecycle"] = lifecycle
    # Experimental controls are deliberately absent from the ordinary payload.
    # In particular, do not turn the historical implicit 4 ms floor into an
    # explicit selector on every benchmark request.
    control_values: dict[str, Any] = {}
    explicit_controls = (
        source_policy is not None
        or source_launch_gap_ns is not None
        or microscope_mode is not None
        or qd_mode is not None
    )
    if not explicit_controls and str(
        os.environ.get("COMFYMODAL_GOLDEN_SOURCE_EXPERIMENT", "")
    ).strip().lower() in {"1", "true", "yes", "on"}:
        for key, env_name in (
            ("source_policy", "COMFYMODAL_GOLDEN_SOURCE_POLICY"),
            ("source_launch_gap_ns", "COMFYMODAL_GOLDEN_SOURCE_LAUNCH_GAP_NS"),
            ("microscope_mode", "COMFYMODAL_GOLDEN_MICROSCOPE"),
            ("qd_mode", "COMFYMODAL_GOLDEN_QD_MODE"),
        ):
            if env_name in os.environ:
                control_values[key] = os.environ[env_name]
        explicit_controls = bool(control_values)
    else:
        control_values = {
            key: value for key, value in {
                "source_policy": source_policy,
                "source_launch_gap_ns": source_launch_gap_ns,
                "microscope_mode": microscope_mode,
                "qd_mode": qd_mode,
            }.items() if value is not None
        }
    if explicit_controls:
        from comfymodal_runtime.golden_experiment_controls import parse_controls
        controls = parse_controls(control_values, explicit=True)
        payload.update({
            "source_policy": controls.source_policy,
            "source_launch_gap_ns": controls.launch_gap_ns,
            "microscope_mode": controls.microscope_mode,
            "qd_mode": controls.qd_mode,
        })
        payload["request_origin_info"]["golden_source_experiment"] = dict(
            controls.effective_description
        )
        payload["request_origin_info"].update({
            "source_policy": controls.source_policy,
            "source_launch_gap_ns": controls.launch_gap_ns,
            "microscope_mode": controls.microscope_mode,
            "qd_mode": controls.qd_mode,
        })
    # Keep the control payload byte-compatible: the optional request selector
    # is emitted only for the explicit QD2 arm.
    if cpu_qd2_prefetch:
        payload["cpu_qd2_prefetch"] = True
        payload["request_origin_info"]["golden_arm"] = "cpu_qd2_prefetch"
    if deep_trace:
        payload["deep_trace"] = True
        payload["request_origin_info"]["golden_deep_trace"] = True
    if c0_source_threads:
        payload["c0_source_threads"] = True
        payload["request_origin_info"]["c0_source_threads"] = True
    if invocation_id:
        payload["request_origin_info"]["v2ctl_invocation_id"] = str(invocation_id)
    return payload
