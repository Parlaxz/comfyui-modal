#!/usr/bin/env python
"""Deterministic 3-arm schedule for the process-architecture QD sweep.

10 rounds, each containing QD5, QD6 and QD7 exactly once, with the per-round
order randomized from a saved seed.  Positional exposure is balanced so each
arm appears 3-4 times in each of the three positions.

No provider or region is pinned.  The whole schedule is persisted before any
remote run is launched.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_SEED = 20260928
_ARMS: list[tuple[str, int]] = [("qd5", 5), ("qd6", 6), ("qd7", 7)]


def _position_counts(orders: list[list[str]]) -> dict[str, list[int]]:
    counts = {arm: [0, 0, 0] for arm, _ in _ARMS}
    for order in orders:
        for position, arm in enumerate(order):
            counts[arm][position] += 1
    return counts


def _balanced(seed: int, rounds: int) -> list[list[str]]:
    """Random per-round orders whose positional counts are all 3-4."""
    names = [arm for arm, _ in _ARMS]
    rng = random.Random(seed)
    for _ in range(20000):
        orders = [rng.sample(names, len(names)) for _ in range(rounds)]
        counts = _position_counts(orders)
        if all(3 <= c <= 4 for per_arm in counts.values() for c in per_arm):
            return orders
    # Deterministic fallback: cyclic rotation is exactly balanced (4/3/3).
    return [names[i % len(names):] + names[: i % len(names)] for i in range(rounds)]


def build(seed: int, rounds: int) -> dict:
    orders = _balanced(seed, rounds)
    scheduled: list[dict] = []
    ordinal = 0
    for index, order in enumerate(orders):
        ordinals: dict[str, int] = {}
        for arm in order:
            ordinal += 1
            ordinals[arm] = ordinal
        scheduled.append({
            "round": index + 1,
            "order": list(order),
            "first": order[0],
            "second": order[1],
            "third": order[2],
            "run_ordinals": ordinals,
        })

    return {
        "seed": seed,
        "rounds": rounds,
        "pinned": False,
        "worker_model": "processes",
        "arms": [arm for arm, _ in _ARMS],
        "qd_by_arm": {arm: qd for arm, qd in _ARMS},
        "read_mib": 64,
        "min_launch_gap_ms": 4.0,
        "position_counts": _position_counts(orders),
        "schedule": scheduled,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=_DEFAULT_SEED)
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument("--out", default="qd_sweep_runs/schedule.json")
    args = parser.parse_args()

    payload = build(args.seed, args.rounds)
    out = _ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    print(f"seed={payload['seed']} rounds={payload['rounds']} "
          f"qd_by_arm={payload['qd_by_arm']} slots={args.rounds * len(_ARMS)}")
    print(f"position_counts (first, second, third): {payload['position_counts']}")
    for entry in payload["schedule"]:
        print(f"  round {entry['round']:>2}  order={' -> '.join(entry['order'])}  "
              f"ordinals={entry['run_ordinals']}")
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
