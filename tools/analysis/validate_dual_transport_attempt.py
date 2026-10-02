"""Fail-closed validator for one dual-transport Golden run artifact."""
from __future__ import annotations
import json
import sys
from pathlib import Path

def main() -> int:
    if len(sys.argv) != 3:
        print("usage: validate_dual_transport_attempt.py RUN_MANIFEST.json sham|split")
        return 2
    manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    expected_mode = sys.argv[2]
    artifact_path = manifest.get("artifacts", {}).get("run_artifact")
    if not artifact_path:
        print(json.dumps({"valid": False, "reasons": ["run_artifact_missing"]}))
        return 1
    attempt = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    events = attempt.get("golden_telemetry", {}).get("events", [])
    identity = next((e.get("fields", {}) for e in events if e.get("name") == "dual_transport_identity"), None)
    reasons = []
    if not attempt.get("valid"):
        reasons.append("attempt_valid_false")
    if not attempt.get("true_cold"):
        reasons.append("true_cold_false")
    if attempt.get("identity", {}).get("restore_count") != 1:
        reasons.append("restore_count_not_one")
    if attempt.get("identity", {}).get("request_count") != 1:
        reasons.append("request_count_not_one")
    validation = attempt.get("validation", {})
    if not validation.get("output_sha_match"):
        reasons.append("output_sha_mismatch")
    if any(e.get("name") == "OUTPUT_SHA_MISMATCH_WARNING" for e in events):
        reasons.append("output_sha_warning")
    if not identity:
        reasons.append("dual_transport_identity_missing")
    else:
        if identity.get("mode") != expected_mode:
            reasons.append("observed_mode_mismatch")
        if not identity.get("static_e27") or identity.get("c0_active"):
            reasons.append("transport_eligibility_mismatch")
        for key in ("arena_data_ptrs_distinct", "stream_identities_distinct", "event_identities_distinct", "pool_identities_distinct"):
            if identity.get(key) is not True:
                reasons.append(key + "_false")
        if identity.get("arena_overlap") is not False:
            reasons.append("arena_overlap")
        if identity.get("both_live_through_unet") is not True:
            reasons.append("not_live_through_unet")
        if expected_mode == "split":
            for key in ("other_resource_source_fills_before_unet", "other_resource_h2d_ops_before_unet", "other_resource_slot_leases_before_unet"):
                if identity.get(key) != 0:
                    reasons.append(key + "_not_zero")
            if identity.get("other_resource_before_unet_verified") is not True:
                reasons.append("other_resource_before_unet_unverified")
        expected_unet = identity.get("clip_resource") if expected_mode == "sham" else identity.get("other_resource")
        if identity.get("vae_resource") != identity.get("clip_resource"):
            reasons.append("vae_route_mismatch")
        if expected_unet != identity.get("clip_resource") and expected_mode == "sham":
            reasons.append("sham_unet_route_mismatch")
        if expected_mode == "split" and expected_unet == identity.get("clip_resource"):
            reasons.append("split_unet_route_mismatch")
    result = {"valid": not reasons, "reasons": reasons, "request_id": attempt.get("request_id"), "run_artifact": str(artifact_path), "identity": identity, "validation": validation}
    print(json.dumps(result, separators=(",", ":")))
    return 0 if not reasons else 1

if __name__ == "__main__":
    raise SystemExit(main())
