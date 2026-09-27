#!/usr/bin/env python
"""Inspect the source_fullfile_runs corpus schema."""
from __future__ import annotations
import json
from pathlib import Path

d = Path("source_fullfile_runs")
fs = sorted(d.glob("*.json"))
print("json files:", len(fs))
print("names sample:", [f.name for f in fs[:10]])

r = json.loads(fs[0].read_text(encoding="utf-8"))
print("\ntop-level keys:")
for k in r.keys():
    v = r[k]
    kind = type(v).__name__
    n = len(v) if hasattr(v, "__len__") else "-"
    print(f"  {k}: {kind} len={n}")

print("\n--- reads sample ---")
reads = r.get("reads") or r.get("physical_reads")
if isinstance(reads, list) and reads:
    print("n reads:", len(reads))
    print(json.dumps(reads[0], indent=2)[:900])
    print("\nread[1]:")
    print(json.dumps(reads[1], indent=2)[:600])

for k in ("config", "env", "identity"):
    if k in r:
        print(f"\n--- {k} ---")
        print(json.dumps(r[k], indent=2)[:700])
