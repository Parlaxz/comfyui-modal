#!/usr/bin/env python
"""Generate (once) the corrected-hedge 20-run schedule.

5 blocks x [H75, H75, H150, H250]; each block's four positions shuffled with a
fixed saved seed.  Persisted and never regenerated.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
OUT = _ROOT / "hedge_runs2" / "schedule2.json"
SEED = 20260923
BLOCKS = 5
BASE = ["H75", "H75", "H150", "H250"]


def main() -> int:
    rng = random.Random(SEED)
    orders = []
    for _ in range(BLOCKS):
        block = list(BASE)
        rng.shuffle(block)
        orders.append(block)

    rows = []
    ordinal = 0
    for b, block in enumerate(orders, start=1):
        for pos, arm in enumerate(block, start=1):
            ordinal += 1
            rows.append({"ordinal": ordinal, "block": b, "position": pos, "arm": arm})

    counts: dict[str, int] = {}
    for x in rows:
        counts[x["arm"]] = counts.get(x["arm"], 0) + 1

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(
        {"seed": SEED, "blocks": BLOCKS, "base_per_block": BASE,
         "runs": rows, "note": "generated once; never regenerated"},
        indent=2), encoding="utf-8")

    print(f"seed={SEED} wrote {OUT} runs={len(rows)} counts={counts}")
    for b, block in enumerate(orders, start=1):
        print(f"  block {b}: {block}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
