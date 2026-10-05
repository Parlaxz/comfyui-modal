"""One deploy_id: the authoritative answer to "which deployment served this?".

Why this exists
---------------
v2ctl used several independent identities (deploy fingerprint, run fingerprint,
deployment identity, canonical boundary identity, source manifest hash, image
identity, Modal version, generation tokens) and needed ambiguity-resolution
logic to reconcile them. None of them answered the only question that matters
when a result comes back:

    did the deployment I intended actually serve this request?

The answer is a single deterministic id over the deployment-relevant inputs:

    shipped source revision
  + resolved deploy-time configuration
  + target class/method
  + resource shape (only where changing it changes the deployed function)

Request-only settings, logs, reports, timestamps and local paths are excluded,
because they do not change what was deployed.

How it survives memory snapshots
--------------------------------
Modal bakes the class environment at deploy time, so the id is present in the
process environment before the snapshot is captured. It is read once at import
and frozen here. A container restored from an older snapshot keeps reporting the
older id, so a stale deployment is caught by a plain comparison rather than by
guessing from version counters or re-hashing the mounted tree.

This is deliberately the whole mechanism. There is no generation ladder, no
boundary algebra and no request-time filesystem hashing.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Mapping

#: Environment variable carrying the deploy id into the deployed runtime.
DEPLOY_ID_ENV = "COMFYMODAL_V2_DEPLOY_ID"

#: Deployment-relevant resource attributes. Changing one of these changes the
#: deployed function, so it belongs in the identity. Anything not listed here is
#: treated as non-deployment-relevant and excluded.
RESOURCE_FIELDS = (
    "gpu",
    "cpu",
    "memory_mb",
    "baseline_cpu_request",
    "baseline_memory_request",
    "gpu_requested_order",
    "timeout_s",
)

#: Read once, at import. This is the value the executing interpreter was
#: deployed with; it cannot drift underneath a restored snapshot.
IMPORTED_DEPLOY_ID = os.environ.get(DEPLOY_ID_ENV, "").strip()


def _canonical(value: Any) -> Any:
    """Normalise a value so equal deployments produce equal ids."""
    if isinstance(value, Mapping):
        return {str(k): _canonical(value[k]) for k in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return repr(value)
    return str(value)


def compute_deploy_id(
    *,
    source_revision: str,
    resolved_config: Mapping[str, Any] | None = None,
    target: Mapping[str, Any] | None = None,
    resources: Mapping[str, Any] | None = None,
) -> str:
    """Deterministic identity of one deployment.

    Excludes request-only settings and any local/diagnostic noise so the same
    deployment always yields the same id, and two genuinely different
    deployments never collide.
    """
    payload = {
        "source_revision": str(source_revision or ""),
        "config": _canonical(resolved_config or {}),
        "target": _canonical(target or {}),
        "resources": _canonical(
            {
                key: resources[key]
                for key in RESOURCE_FIELDS
                if resources and key in resources
            }
        ),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def deploy_id() -> str:
    """The deploy id this interpreter was deployed with, frozen at import."""
    return IMPORTED_DEPLOY_ID


def verify(expected: str) -> tuple[bool, str]:
    """Compare the expected deploy id with this interpreter's own.

    Returns ``(ok, reason)``. A missing id on either side fails closed: an
    unidentifiable deployment is not evidence of a correct one.
    """
    if not expected:
        return False, "no expected deploy_id was supplied"
    actual = deploy_id()
    if not actual:
        return False, (
            "the runtime reported no deploy_id (%s unset at import); cannot prove "
            "which deployment served this request" % DEPLOY_ID_ENV
        )
    if actual != expected:
        return False, (
            "deploy_id mismatch: expected %s but the executing deployment is %s "
            "(stale snapshot or wrong deployment)" % (expected, actual)
        )
    return True, "deploy_id matches the deployment that was requested"