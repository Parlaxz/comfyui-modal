#!/usr/bin/env python
"""Deterministic paired schedule for the THREADS-vs-PROCESSES discriminator.

Optional provider pinning (`--pinned`): every round is assigned ONE
(cloud, region) pair and BOTH arms of that round use it, so each pair is
region-matched by construction.  Cloud is restricted to aws/gcp, which
excludes Modal's own regions (odin, denver) and oci (us-chicago-1,
us-ashburn-1).

Region slugs are drawn only from slugs this project has already observed
scheduling the H100 probe successfully:
  aws -> us-east, eu-north, ap-northeast      gcp -> us-central

10 paired rounds, positional balance exactly 5/5, shuffled with a saved seed
and persisted before any remote run is launched.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_SEED = 20260924
_ARM_THREADS = "threads"
_ARM_PROCESSES = "processes"
_AWS_REGIONS = ["us-east", "eu-north", "ap-northeast"]
_GCP_REGIONS = ["us-central"]


def build(seed: int, rounds: int, pinned: bool, provider_only: bool = False) -> dict:
    half = rounds // 2

    rng = random.Random(seed)
    placements: list[tuple[str, str]] = []
    if provider_only:
        # Provider pinning ONLY.  No region is chosen or constrained: Modal
        # picks the region within the provider.  This removes Modal's own
        # regions (odin, denver) and oci/azure without touching region.
        clouds = ["aws"] * half + ["gcp"] * half
        rng.shuffle(clouds)
        placements = [(c, "") for c in clouds]
    elif pinned:
        aws_slots = [_AWS_REGIONS[i % len(_AWS_REGIONS)] for i in range(half)]
        gcp_slots = [_GCP_REGIONS[i % len(_GCP_REGIONS)] for i in range(half)]
        rng.shuffle(aws_slots)
        rng.shuffle(gcp_slots)
        placements = [("aws", r) for r in aws_slots] + [("gcp", r) for r in gcp_slots]
        rng.shuffle(placements)
    else:
        placements = [("", "") for _ in range(rounds)]

    orders = [[_ARM_THREADS, _ARM_PROCESSES] for _ in range(rounds - half)]
    orders += [[_ARM_PROCESSES, _ARM_THREADS] for _ in range(half)]
    rng.shuffle(orders)

    scheduled: list[dict] = []
    ordinal = 0
    for index, order in enumerate(orders):
        ordinal += 1
        first_ordinal = ordinal
        ordinal += 1
        second_ordinal = ordinal
        cloud, region = placements[index]
        scheduled.append({
            "round": index + 1,
            "cloud": cloud,
            "region": region,
            "first": order[0],
            "second": order[1],
            "order": list(order),
            "run_ordinals": {order[0]: first_ordinal, order[1]: second_ordinal},
        })

    region_counts: dict[str, int] = {}
    for entry in scheduled:
        key = f"{entry['cloud']}:{entry['region']}" if entry["cloud"] else "unpinned"
        region_counts[key] = region_counts.get(key, 0) + 1

    return {
        "seed": seed,
        "rounds": rounds,
        "pinned": bool(pinned or provider_only),
        "provider_only": bool(provider_only),
        "arms": [_ARM_THREADS, _ARM_PROCESSES],
        "read_mib": 64,
        "qd": 4,
        "min_launch_gap_ms": 4.0,
        "workers": 4,
        "threads_first": sum(1 for s in scheduled if s["first"] == _ARM_THREADS),
        "processes_first": sum(1 for s in scheduled if s["first"] == _ARM_PROCESSES),
        "region_counts": region_counts,
        "schedule": scheduled,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=_DEFAULT_SEED)
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument("--unpinned", action="store_true")
    parser.add_argument("--provider-only", action="store_true")
    parser.add_argument("--out", default="worker_model_runs/schedule.json")
    args = parser.parse_args()

    payload = build(args.seed, args.rounds, pinned=not args.unpinned,
                    provider_only=args.provider_only)
    out = _ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    print(f"seed={payload['seed']} rounds={payload['rounds']} pinned={payload['pinned']} "
          f"provider_only={payload['provider_only']} "
          f"threads_first={payload['threads_first']} processes_first={payload['processes_first']}")
    print(f"region_counts={payload['region_counts']}")
    for entry in payload["schedule"]:
        where = f"{entry['cloud']}:{entry['region']}" if entry["cloud"] else "unpinned"
        print(f"  round {entry['round']:>2}  {where:<22} first={entry['first']:<9} "
              f"second={entry['second']:<9} ordinals={entry['run_ordinals']}")
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
