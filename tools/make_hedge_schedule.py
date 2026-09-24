#!/usr/bin/env python
"""Generate (once) the balanced randomized 100-run hedge schedule.

25 rounds x 4 arms.  Rounds 1-24 use each of the 24 permutations of the four
arms exactly once, with the order of those permutations shuffled by a fixed
seed.  Round 25 gets one additional seed-derived permutation.

The schedule is persisted and never regenerated.
"""
from __future__ import annotations

import itertools
import json
import random
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
OUT = _ROOT / "hedge_runs" / "schedule.json"
SEED = 20260922

ARMS = ["C", "H75", "H125", "H200"]
ROUNDS = 25


def main() -> int:
    rng = random.Random(SEED)
    perms = list(itertools.permutations(ARMS))
    assert len(perms) == 24, len(perms)
    rng.shuffle(perms)
    final = list(ARMS)
    rng.shuffle(final)
    rounds = perms + [tuple(final)]

    rows = []
    ordinal = 0
    for r, perm in enumerate(rounds, start=1):
        assert sorted(perm) == sorted(ARMS)
        for pos, arm in enumerate(perm, start=1):
            ordinal += 1
            rows.append({"ordinal": ordinal, "round": r, "position": pos, "arm": arm})

    counts = {a: sum(1 for x in rows if x["arm"] == a) for a in ARMS}
    pos_counts = {a: {p: 0 for p in range(1, 5)} for a in ARMS}
    for x in rows:
        pos_counts[x["arm"]][x["position"]] += 1

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(
        {"seed": SEED, "arms": ARMS, "rounds": ROUNDS, "runs": rows,
         "note": "generated once; never regenerated"},
        indent=2), encoding="utf-8")

    print(f"seed={SEED}  wrote {OUT}  runs={len(rows)}")
    print(f"arm totals: {counts}")
    print("arm x position counts:")
    for a in ARMS:
        print(f"  {a:<5} {pos_counts[a]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
