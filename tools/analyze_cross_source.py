#!/usr/bin/env python
"""Rigorous cross-source analysis: do diagnostic probes overlap ANY worker stall?

For every run: build worker stall episodes, then for every diagnostic probe report
whether it overlapped a stall, and what the concurrent worker stall magnitude was.
"""
from __future__ import annotations
import json
from pathlib import Path

D = Path(__file__).resolve().parents[1] / "cross_source_runs"
STALL_MS = 250.0


def rel(t, t0):
    return (t - t0) / 1e6


def episodes(reads):
    """Merge stall reads (preadv_ms >= STALL_MS) into time-overlapping episodes."""
    stalls = sorted((r for r in reads if r["preadv_ms"] >= STALL_MS),
                    key=lambda r: r["preadv_enter_ns"])
    eps = []
    for r in stalls:
        if eps and r["preadv_enter_ns"] <= eps[-1]["end"]:
            e = eps[-1]
            e["end"] = max(e["end"], r["preadv_exit_ns"])
            e["reads"].append(r)
        else:
            eps.append({"start": r["preadv_enter_ns"], "end": r["preadv_exit_ns"],
                        "reads": [r]})
    for e in eps:
        e["span_ms"] = (e["end"] - e["start"]) / 1e6
        e["worst_ms"] = max(r["preadv_ms"] for r in e["reads"])
        e["workers"] = sorted({r["worker"] for r in e["reads"]})
    return eps


summary = []
for path in sorted(D.glob("cs-r*.json")):
    run = json.loads(path.read_text(encoding="utf-8"))
    if run.get("status") != "ok" or not run.get("reads"):
        continue
    reads = run["reads"]
    t0 = min(r["preadv_enter_ns"] for r in reads)
    eps = episodes(reads)
    psets = run.get("probe_sets") or []
    patho = [s for s in psets if s.get("kind") == "pathological"]
    cleanref = [s for s in psets if s.get("kind") == "clean_reference"]

    print(f"\n{'='*100}\n{path.stem}  {run.get('provider')}/{run.get('region')}  "
          f"gbps={run['decimal_gbps']:.2f} max={run['max_ms']:.0f}ms "
          f"hb_max_gap={(run.get('heartbeat_max_gap_ms') or 0):.0f}ms  "
          f"stall_episodes={len(eps)}")
    for i, e in enumerate(eps):
        print(f"  stall#{i}: t={rel(e['start'],t0):.0f}..{rel(e['end'],t0):.0f}ms "
              f"span={e['span_ms']:.0f}ms worst={e['worst_ms']:.0f}ms workers={e['workers']}")
        for r in sorted(e["reads"], key=lambda x: x["preadv_enter_ns"]):
            print(f"      w{r['worker']} gen{r['gen']} enter={rel(r['preadv_enter_ns'],t0):.0f} "
                  f"exit={rel(r['preadv_exit_ns'],t0):.0f} ms={r['preadv_ms']:.0f} "
                  f"off={r['offset']}")

    for kind, sets in (("pathological", patho), ("clean_reference", cleanref)):
        for ps in sets:
            trig = ps["trigger_ns"]
            print(f"  --- {kind} probe set, trigger t={rel(trig,t0):.0f}ms")
            if ps.get("blocked"):
                print(f"      blocked at trigger: " + ", ".join(
                    f"w{w}(el={v['elapsed_ms']:.0f}ms,off={v['offset']})"
                    for w, v in sorted(ps["blocked"].items())))
                # did the triggering blocked requests clear before probes entered?
            for name, e in sorted((ps.get("results") or {}).items()):
                if e.get("status") not in ("ok", "short"):
                    print(f"      {name}: {e.get('status')}")
                    continue
                ov = [x for x in eps if e["enter_ns"] < x["end"] and e["exit_ns"] > x["start"]]
                if ov:
                    conc = max(x["worst_ms"] for x in ov)
                    wl = sorted({w for x in ov for w in x["workers"]})
                    tag = f"OVERLAPS stall#{eps.index(ov[0])} (worst={conc:.0f}ms,workers={wl})"
                else:
                    tag = "no-overlap"
                print(f"      {name}: enter={rel(e['enter_ns'],t0):.0f} "
                      f"exit={rel(e['exit_ns'],t0):.0f} lat={e['latency_ms']:.0f}ms "
                      f"enter-trig={rel(e['enter_ns'],trig):.0f}ms  {tag}")

    a = next((ps for ps in patho), None)
    if a:
        trig = a["trigger_ns"]
        blk = a.get("blocked") or {}
        ex = []
        for w, info in blk.items():
            rec = next((x for x in reads if str(x["worker"]) == w and x["offset"] == info["offset"]), None)
            if rec:
                ex.append(rel(rec["preadv_exit_ns"], trig))
        probes_in = [rel(e["enter_ns"], trig) for e in (a.get("results") or {}).values()
                     if e.get("status") in ("ok", "short")]
        if ex and probes_in:
            print(f"  TRIGGER->clear: blocked requests exited {min(ex):.0f}..{max(ex):.0f}ms after trigger; "
                  f"earliest probe entered {min(probes_in):.0f}ms after trigger => "
                  f"{'probes fired AFTER clear' if min(probes_in) > max(ex) else 'PROBES OVERLAPPED TRIGGER EPISODE'}")

    summary.append({
        "run": path.stem, "region": f"{run.get('provider')}/{run.get('region')}",
        "gbps": run["decimal_gbps"], "max_ms": run["max_ms"],
        "hb": run.get("heartbeat_max_gap_ms"), "n_eps": len(eps),
        "n_probe": len(patho),
    })

print(f"\n\n{'='*100}\nSUMMARY")
for s in summary:
    print(f"  {s['run']} {s['region']:42s} gbps={s['gbps']:.2f} max={s['max_ms']:7.0f}ms "
          f"hb_gap={(s['hb'] or 0):6.0f}ms stalls={s['n_eps']} probe_sets={s['n_probe']}")
