#!/usr/bin/env python3
"""Safe controlled-matrix planner and manifest generator for VAE policy runs.

This tool ONLY plans.  The default invocation emits a plan/manifest and never
spawns subprocesses, never calls Modal, and never deploys.  An explicit
`--execute` flag exists but still refuses to run unless `--allow-modal` is also
provided; the execution path is intentionally inert in this module.

Planned matrix arms:
    v0  - baseline; binds explicitly to policy v0, prefetch off
    v1  - binds explicitly to policy v1
    v2  - binds explicitly to policy v2
    v3  - winner-bound variant (requires --winner-policy and --winner-prefetch)
    v4  - winner-bound variant (requires --winner-policy and --winner-prefetch)

Winner policy must be given in the form:
    tuple:<weight>:<compute>:<memory_format>
where weight, compute, and memory_format are concrete runtime-accepted values:
    weight        float32 | bfloat16 | float16
    compute       float32 | bfloat16_native | bfloat16_autocast |
                  float16_native | float16_autocast
    memory_format contiguous | channels_last
e.g. tuple:float32:float32:contiguous or tuple:bfloat16:bfloat16_native:channels_last.
Malformed or unsupported tokens are rejected rather than silently falling back
to v0.  Winner prefetch must be one of the real prefetch modes:
    off | madvise_willneed | madvise_populate_read | bounded_native_touch

Per-arm runs emit the real runtime env assignments:
    COMFYMODAL_V2_VAE_POLICY         - policy string bound to the arm
    COMFYMODAL_V2_VAE_PREFETCH_MODE  - prefetch mode bound to the arm

Fixed run protocol defaults (exact; overridable only via known knobs):
    fixture_path     - c5_latest_benchmark_workflow.json
    output_node      - 107
    seed             - 1111894690380134
    gpu              - rtx-pro-6000
    min_containers   - 0
    scaledown_window - 4
    cold_runs        - 2 (expected two cold runs)
    gap_seconds      - 20

Usage:
    python tools/c5_vae_policy_runner.py --arms v0 v1 v2
    python tools/c5_vae_policy_runner.py --arms v3 v4 \\
        --winner-policy tuple:float32:float32:contiguous --winner-prefetch off
"""

import argparse
import json
from typing import Any, Dict, List, Optional, Tuple

FIXTURE_PATH = "c5_latest_benchmark_workflow.json"
OUTPUT_NODE_ID = "107"
SEED = 1111894690380134
GPU = "rtx-pro-6000"
MIN_CONTAINERS = 0
SCALEDOWN_WINDOW = 4
COLD_RUNS = 2
GAP_SECONDS = 20

ENV_POLICY = "COMFYMODAL_V2_VAE_POLICY"
ENV_PREFETCH = "COMFYMODAL_V2_VAE_PREFETCH_MODE"

PREFETCH_MODES = (
    "off",
    "madvise_willneed",
    "madvise_populate_read",
    "bounded_native_touch",
)
DEFAULT_PREFETCH = "off"

ALLOWED_ARMS = ("v0", "v1", "v2", "v3", "v4")

WINNER_POLICY_PREFIX = "tuple"
# Concrete runtime-accepted policy component sets.
WINNER_WEIGHTS = ("float32", "bfloat16", "float16")
WINNER_COMPUTES = (
    "float32",
    "bfloat16_native",
    "bfloat16_autocast",
    "float16_native",
    "float16_autocast",
)
WINNER_MEMORY_FORMATS = ("contiguous", "channels_last")

# Knobs that may be overridden; anything else is rejected.
KNOWN_KNOBS = frozenset(
    {
        "fixture_path",
        "output_node",
        "seed",
        "gpu",
        "min_containers",
        "scaledown_window",
        "cold_runs",
        "gap_seconds",
    }
)


def _arm_policy(arm: str) -> Optional[str]:
    """Explicit binding for v0/v1/v2; v3/v4 come from the winner tuple."""
    if arm in ("v0", "v1", "v2"):
        return arm
    return None


def _arm_prefetch(arm: str, winner_prefetch: Optional[str]) -> str:
    if arm in ("v0", "v1", "v2"):
        return DEFAULT_PREFETCH
    return winner_prefetch if winner_prefetch is not None else DEFAULT_PREFETCH


def parse_winner_policy(value: str) -> Dict[str, str]:
    """Parse a winner policy tuple into its concrete components.

    Accepts only the runtime-accepted concrete sets for weight, compute, and
    memory_format.  Raises ValueError for malformed or unsupported tokens so a
    bad tuple can never silently fall back to v0.
    """
    if not isinstance(value, str):
        raise ValueError("winner policy must be a string")
    parts = value.strip().split(":")
    if len(parts) != 4 or parts[0] != WINNER_POLICY_PREFIX:
        raise ValueError(
            "winner policy must be of form tuple:<weight>:<compute>:<memory_format>"
        )
    weight, compute, memfmt = parts[1], parts[2], parts[3]
    if weight not in WINNER_WEIGHTS:
        raise ValueError(f"unsupported weight: {weight!r}")
    if compute not in WINNER_COMPUTES:
        raise ValueError(f"unsupported compute: {compute!r}")
    if memfmt not in WINNER_MEMORY_FORMATS:
        raise ValueError(f"unsupported memory_format: {memfmt!r}")
    return {"weight": weight, "compute": compute, "memory_format": memfmt}


def validate_winner_policy(value: str) -> str:
    """Validate a winner policy tuple and return it canonicalized."""
    parse_winner_policy(value)
    return value.strip()


def validate_winner_prefetch(value: str) -> str:
    if value not in PREFETCH_MODES:
        raise ValueError(f"unsupported prefetch mode: {value}")
    return value


def validate_knobs(knobs: Dict[str, Any]) -> None:
    """Raise ValueError on any unknown knob."""
    unknown = sorted(set(knobs) - KNOWN_KNOBS)
    if unknown:
        raise ValueError(f"unknown knobs: {', '.join(unknown)}")


def resolve_defaults(knobs: Dict[str, Any]) -> Dict[str, Any]:
    """Merge user knobs over the fixed protocol defaults."""
    validate_knobs(knobs)
    merged = {
        "fixture_path": FIXTURE_PATH,
        "output_node": OUTPUT_NODE_ID,
        "seed": SEED,
        "gpu": GPU,
        "min_containers": MIN_CONTAINERS,
        "scaledown_window": SCALEDOWN_WINDOW,
        "cold_runs": COLD_RUNS,
        "gap_seconds": GAP_SECONDS,
    }
    merged.update(knobs)
    return merged


def build_env(arm: str, policy: str, prefetch: str) -> Dict[str, str]:
    """Per-arm real runtime environment assignments for a single run."""
    return {ENV_POLICY: policy, ENV_PREFETCH: prefetch}


def build_arms(
    arms: List[str],
    knobs: Optional[Dict[str, Any]] = None,
    winner: Optional[Tuple[str, str]] = None,
) -> List[Dict[str, Any]]:
    """Build the controlled-matrix plan.

    winner is (winner_policy_tuple, winner_prefetch).  Raises ValueError for
    unknown arms, missing/invalid winner on v3/v4, and unknown knobs.
    """
    knobs = knobs or {}
    cfg = resolve_defaults(knobs)
    bad = [a for a in arms if a not in ALLOWED_ARMS]
    if bad:
        raise ValueError(f"unknown arms: {', '.join(bad)}")

    winner_policy = None
    winner_prefetch = None
    if winner is not None:
        if len(winner) != 2:
            raise ValueError("winner must be (winner_policy_tuple, winner_prefetch)")
        winner_policy = validate_winner_policy(winner[0])
        winner_prefetch = validate_winner_prefetch(winner[1])

    if any(a in ("v3", "v4") for a in arms):
        if winner_policy is None or winner_prefetch is None:
            raise ValueError(
                "v3/v4 require --winner-policy (tuple:<weight>:<compute>:<memory_format>) "
                "and --winner-prefetch"
            )

    planned: List[Dict[str, Any]] = []
    for arm in arms:
        policy = _arm_policy(arm)
        if arm in ("v3", "v4"):
            policy = winner_policy
        prefetch = _arm_prefetch(arm, winner_prefetch)
        env = build_env(arm, policy, prefetch)
        planned.append(
            {
                "arm": arm,
                "policy": policy,
                "prefetch": prefetch,
                "applied_policy": policy,
                "winner_bound": arm in ("v3", "v4"),
                "env": env,
                "expected_cold_runs": cfg["cold_runs"],
                "gap_seconds": cfg["gap_seconds"],
                "fixture_path": cfg["fixture_path"],
                "output_node": str(cfg["output_node"]),
                "seed": str(cfg["seed"]),
                "gpu": cfg["gpu"],
                "min_containers": cfg["min_containers"],
                "scaledown_window": cfg["scaledown_window"],
            }
        )
    return planned


def build_manifest(
    arms: List[str],
    knobs: Optional[Dict[str, Any]] = None,
    winner: Optional[Tuple[str, str]] = None,
) -> Dict[str, Any]:
    """Return a JSON-serializable run manifest for the planned matrix."""
    knobs = knobs or {}
    cfg = resolve_defaults(knobs)
    planned = build_arms(arms, knobs=knobs, winner=winner)
    return {
        "schema": "comfymodal.v2_vae_policy_run.manifest.v1",
        "protocol": {
            "fixture_path": cfg["fixture_path"],
            "output_node": str(cfg["output_node"]),
            "seed": str(cfg["seed"]),
            "gpu": cfg["gpu"],
            "min_containers": cfg["min_containers"],
            "scaledown_window": cfg["scaledown_window"],
            "cold_runs": cfg["cold_runs"],
            "gap_seconds": cfg["gap_seconds"],
            "env_policy": ENV_POLICY,
            "env_prefetch": ENV_PREFETCH,
            "prefetch_modes": list(PREFETCH_MODES),
        },
        "winner": list(winner) if winner is not None else None,
        "arms": planned,
        "mode": "plan",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plan a controlled VAE policy run matrix (no execution)."
    )
    parser.add_argument(
        "--arms", nargs="+", required=True, choices=list(ALLOWED_ARMS),
        help="matrix arms to plan (v0 v1 v2 v3 v4)",
    )
    parser.add_argument(
        "--winner-policy", default=None,
        help="winner policy tuple tuple:<weight>:<compute>:<memory_format> "
             "(weight: float32|bfloat16|float16; compute: float32|bfloat16_native|"
             "bfloat16_autocast|float16_native|float16_autocast; memory_format: "
             "contiguous|channels_last) for v3/v4",
    )
    parser.add_argument(
        "--winner-prefetch", default=None,
        help="winner prefetch mode for v3/v4",
    )
    parser.add_argument(
        "--execute", action="store_true",
        help="request execution; still refused without --allow-modal",
    )
    parser.add_argument(
        "--allow-modal", action="store_true",
        help="permission gate required before any execution is permitted",
    )
    parser.add_argument("--out", default=None, help="write manifest JSON to path")
    args = parser.parse_args()

    winner = None
    if args.winner_policy is not None or args.winner_prefetch is not None:
        if args.winner_policy is None or args.winner_prefetch is None:
            parser.error("--winner-policy and --winner-prefetch must be provided together")
        winner = (args.winner_policy, args.winner_prefetch)

    if args.execute:
        if not args.allow_modal:
            parser.error("refusing to execute: --execute requires --allow-modal")
        # Intentional: execution is not implemented in this module.
        print("EXECUTION NOT IMPLEMENTED: plan-only module; nothing executed.")

    manifest = build_manifest(args.arms, winner=winner)
    text = json.dumps(manifest, indent=2, sort_keys=True)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
