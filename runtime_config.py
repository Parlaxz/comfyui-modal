"""Minimal runtime configuration constants and snapshot-key builder."""

import hashlib
import json
import os

# ---------------------------------------------------------------------------
# Environment-derived constants
# ---------------------------------------------------------------------------

DEFAULT_EXECUTION_BACKEND: str = os.environ.get(
    "COMFYMODAL_EXECUTION_BACKEND", "in_process"
)
# Supported values:
#   "in_process"  — (default) run ComfyUI in the same Python process.  Requires
#                   Modal memory snapshotting (enable_memory_snapshot=True) for
#                   fast restores (~2-4 s cold start).
#   "subprocess"  — launch ComfyUI as a child process via `comfy launch`.
#                   Set COMFYMODAL_EXECUTION_BACKEND=subprocess to opt out.
ENABLE_WARMUP: bool = (
    os.environ.get("COMFYMODAL_ENABLE_WARMUP", "false").lower() == "true"
)
WARMUP_PROFILE: str = os.environ.get("COMFYMODAL_WARMUP_PROFILE", "off")
RUNTIME_VERSION: str = os.environ.get("COMFYMODAL_RUNTIME_VERSION", "2")
SNAPSHOT_SCHEMA_VERSION: str = os.environ.get(
    "COMFYMODAL_SNAPSHOT_SCHEMA_VERSION", "1"
)
WARMUP_PROFILE_VERSION: str = os.environ.get(
    "COMFYMODAL_WARMUP_PROFILE_VERSION", "1"
)

# ---------------------------------------------------------------------------
# Snapshot key helpers
# ---------------------------------------------------------------------------


def build_runtime_snapshot_key(
    *,
    runtime_version: str,
    comfy_version: str,
    worker_version: str,
    manifest_hash: str,
    warmup_version: str,
    warmup_profile: str,
    gpu_type: str,
) -> str:
    """Build a deterministic snapshot key from the given runtime parameters.

    All parameters are keyword-only to prevent accidental mis-ordering.
    The returned hex digest is a SHA-256 of the sorted parameter pairs,
    ensuring the same inputs always produce the same key.
    """
    payload = json.dumps(
        dict(
            runtime_version=runtime_version,
            comfy_version=comfy_version,
            worker_version=worker_version,
            manifest_hash=manifest_hash,
            warmup_version=warmup_version,
            warmup_profile=warmup_profile,
            gpu_type=gpu_type,
        ),
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
