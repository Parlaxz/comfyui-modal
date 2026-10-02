#!/usr/bin/env python
"""Fisher exact tests for the launch-spacing confirmation."""
from __future__ import annotations
from math import comb


def fisher_two_sided(a: int, b: int, c: int, d: int) -> float:
    """2x2 [[a,b],[c,d]] two-sided Fisher exact p."""
    n = a + b + c + d
    r1, r2 = a + b, c + d
    c1 = a + c

    def prob(x: int) -> float:
        return comb(c1, x) * comb(n - c1, r1 - x) / comb(n, r1)

    lo = max(0, r1 - (n - c1))
    hi = min(r1, c1)
    obs = prob(a)
    total = 0.0
    for x in range(lo, hi + 1):
        p = prob(x)
        if p <= obs + 1e-12:
            total += p
    return total


def row(label: str, a: int, b: int, c: int, d: int) -> None:
    p = fisher_two_sided(a, b, c, d)
    print(f"  {label:<44} a={a:>4} rest={b:>5} c={c:>4} rest={d:>5}  "
          f"p_two_sided={p:.4f}")


print("READ-LEVEL, >=500 ms (out of 1800 reads per arm, 120 reads x 15 runs)")
row("gap 0 vs gap 4", 6, 1794, 0, 1800)
row("gap 2 vs gap 4", 6, 1794, 0, 1800)
row("gap 0+2 pooled vs gap 4", 12, 3588, 0, 1800)
row("gap 0 vs gap 2 (should be ns)", 6, 1794, 6, 1794)

print("\nREAD-LEVEL, >=1000 ms")
row("gap 0 vs gap 4", 4, 1796, 0, 1800)
row("gap 2 vs gap 4", 4, 1796, 0, 1800)
row("gap 0+2 pooled vs gap 4", 8, 3592, 0, 1800)

print("\nGEN-0 ONLY, >=500 ms (out of 60 gen-0 reads per arm)")
row("gap 0 vs gap 4", 4, 56, 0, 60)
row("gap 2 vs gap 4", 6, 54, 0, 60)
row("gap 0+2 pooled vs gap 4", 10, 110, 0, 60)

print("\nRUN-LEVEL, runs having any >=1000 ms read (15 runs per arm)")
row("gap 0 vs gap 4", 1, 14, 0, 15)
row("gap 2 vs gap 4", 2, 13, 0, 15)
row("gap 0+2 pooled vs gap 4", 3, 27, 0, 15)

print("\nRUN-LEVEL, runs having any >=500 ms read")
row("gap 0 vs gap 4", 1, 14, 0, 15)
row("gap 2 vs gap 4", 3, 12, 0, 15)
row("gap 0+2 pooled vs gap 4", 4, 26, 0, 15)
