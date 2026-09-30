"""Is the run-to-run variance new, and does placement explain it?"""
import json, glob, os, statistics, collections, re, sys

MIB = 1024 * 1024

def cov_bytes(d):
    tot = 0
    ts = d.get("transport_stats")
    for t in (ts if isinstance(ts, list) else [ts] if isinstance(ts, dict) else []):
        if isinstance(t, dict):
            tot += int((t.get("coverage") or {}).get("source_bytes") or 0)
    return tot

def scan(d, label):
    out = []
    for mf in sorted(glob.glob(os.path.join(d, "run_*.json"))):
        try:
            j = json.load(open(mf, encoding="utf-8"))
            a = json.load(open(j["artifacts"]["run_artifact"], encoding="utf-8"))
        except Exception:
            continue
        if a.get("valid") is not True:
            continue
        tel = a.get("golden_telemetry") or {}
        stages = {x.get("name"): x for x in (tel.get("stages") or [])}
        rec = {"run": os.path.basename(mf)}
        for role, st in (("clip", "golden_clip_load"), ("unet", "golden_unet_load")):
            sd = stages.get(st) or {}
            dd = sd.get("details") or {}
            e_, x_ = sd.get("entry_monotonic_ns"), sd.get("end_monotonic_ns")
            w = ((x_ - e_) / 1e6) if (e_ and x_) else None
            b = cov_bytes(dd)
            rec[role] = (b / 1e9) / (w / 1000.0) if (b and w) else None
        blob = json.dumps(a)
        m = re.search(r'"region[_a-z]*"\s*:\s*"([a-z\-]+)"', blob)
        rec["region"] = m.group(1) if m else ""
        m2 = re.search(r'"cloud[_a-z]*"\s*:\s*"([A-Za-z_]+)"', blob)
        rec["cloud"] = m2.group(1) if m2 else ""
        out.append(rec)
    return out

TREES = {
    "CONTROL production-006 (pre-M1B, untouched)":
        r"C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\production-006\.v2ctl\runs",
    "M1B/M1C instrumented (diagnostic apps)":
        r"C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\m1c-port\.v2ctl\runs",
}
for label, d in TREES.items():
    rows = [r for r in scan(d, label) if r.get("clip") or r.get("unet")]
    if not rows:
        print(f"{label}: none"); continue
    print("=" * 78)
    print(f"{label}   valid runs={len(rows)}")
    for role in ("clip", "unet"):
        v = [r[role] for r in rows if r.get(role)]
        if not v:
            continue
        v_sorted = sorted(v)
        print(f"  {role:<5} n={len(v)} min={min(v):.2f} p50={statistics.median(v):.2f} "
              f"max={max(v):.2f}  spread={max(v)/min(v):.2f}x  "
              f"cv={(statistics.pstdev(v)/statistics.mean(v))*100:.1f}%")
    regs = collections.Counter(r["region"] for r in rows if r["region"])
    print(f"  regions: {dict(regs)}")
    print("  per-run:")
    for r in rows:
        c = f"{r['clip']:.2f}" if r.get("clip") else "  - "
        u = f"{r['unet']:.2f}" if r.get("unet") else "  - "
        print(f"    {r['run'][:34]:<34} clip={c:>6} unet={u:>6} region={r['region'] or '-'}")