#!/usr/bin/env python
"""Part B charts: primary 4 ms preadv histogram (log-count) + tail zoom + survival curve."""
from __future__ import annotations

import csv
from pathlib import Path

D = Path(__file__).resolve().parents[1] / "qd4_distribution"

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except Exception as exc:  # noqa: BLE001
    print(f"matplotlib unavailable: {type(exc).__name__}: {exc}")
    raise SystemExit(0)

with (D / "qd4_64m_histogram_primary_4ms.csv").open(encoding="utf-8") as fh:
    hist = list(csv.DictReader(fh))
with (D / "qd4_64m_survival_primary_4ms.csv").open(encoding="utf-8") as fh:
    surv = list(csv.DictReader(fh))

labels, counts = [], []
for b in hist:
    lo, hi = b["bin_lo_ms"], b["bin_hi_ms"]
    labels.append(f">={lo}" if hi == "inf" else f"{lo}-{hi}")
    counts.append(int(b["count"]))

# 1) log-count histogram (healthy body + tail on one axis)
fig, ax = plt.subplots(figsize=(14, 6))
ax.bar(range(len(counts)), [max(c, 0.5) for c in counts], color="#3366cc")
ax.set_yscale("log")
ax.set_xticks(range(len(labels)))
ax.set_xticklabels(labels, rotation=90, fontsize=8)
ax.set_ylabel("read count (log scale)")
ax.set_xlabel("preadv_ms bin")
ax.set_title("QD4 / 64 MiB / H100 / 4 ms pacing — primary corpus (38 runs, 4560 reads), log-count")
ax.grid(axis="y", alpha=0.3)
fig.tight_layout()
fig.savefig(D / "qd4_64m_hist_primary_4ms_logcount.png", dpi=130)
plt.close(fig)

# 2) tail zoom >=100 ms, linear
idx = [i for i, b in enumerate(hist) if float(b["bin_lo_ms"]) >= 100]
fig, ax = plt.subplots(figsize=(10, 5))
ax.bar(range(len(idx)), [counts[i] for i in idx], color="#cc3333")
ax.set_xticks(range(len(idx)))
ax.set_xticklabels([labels[i] for i in idx], rotation=45, fontsize=9)
ax.set_ylabel("read count")
ax.set_xlabel("preadv_ms bin (tail only, >= 100 ms)")
ax.set_title("Primary 4 ms corpus — tail zoom (>=100 ms)")
ax.grid(axis="y", alpha=0.3)
fig.tight_layout()
fig.savefig(D / "qd4_64m_hist_primary_4ms_tail.png", dpi=130)
plt.close(fig)

# 3) survival: P(>=250/500/1000 | outstanding at X) and fraction outstanding
xs = [int(r["X_ms"]) for r in surv]
fig, ax = plt.subplots(figsize=(10, 6))
for key, colour, lab in (("P_ge250_given_outstanding", "#888800", "P(final>=250 | outstanding)"),
                         ("P_ge500_given_outstanding", "#cc6600", "P(final>=500 | outstanding)"),
                         ("P_ge1000_given_outstanding", "#cc0000", "P(final>=1000 | outstanding)")):
    ys = [float(r[key]) if r[key] not in ("", "None") else 0.0 for r in surv]
    ax.plot(xs, ys, marker="o", color=colour, label=lab)
ax.set_xlabel("X: read still outstanding at X ms")
ax.set_ylabel("conditional probability (%)")
ax.set_title("QD4/64 MiB/4 ms — if it is still running, how likely is it bad?")
ax.grid(alpha=0.3)
ax.legend()
fig.tight_layout()
fig.savefig(D / "qd4_64m_survival_primary_4ms.png", dpi=130)
plt.close(fig)

print("wrote 3 PNGs to", D)
