import json, sys

mf = sys.argv[1]
j = json.load(open(mf, encoding="utf-8"))
a = json.load(open(j["artifacts"]["run_artifact"], encoding="utf-8"))
s = json.load(open(j["artifacts"]["summary_artifact"], encoding="utf-8"))
att = (s.get("attempts") or [{}])[0]
tel = a.get("golden_telemetry") or {}
ev = tel.get("events") or []
print("valid:", a.get("valid"), "dnf:", a.get("dnf"), "events:", len(ev))
print("sha:", att.get("observed_output_shas"))
print("failures:", a.get("failures"))

final = None
for e in ev:
    if e.get("name") == "m1cb_copy_probe":
        f = e.get("fields") or {}
        if f.get("phase") == "final":
            final = f
if final is None:
    print("!! no final probe event")
    sys.exit(0)
print("phases_completed:", final.get("phases_completed"))
print("phase_errors:", final.get("phase_errors"))

print("\n=== Q2  CONCURRENCY CEILING (file-backed, pre-warmed source) ===")
for c in final.get("m1c_concurrency") or []:
    k = c.get("nthreads")
    print(f"  {k} reader(s): per-reader={[round(x,2) for x in (c.get('per_reader_gbps') or [])]}"
          f"  median={c.get('per_reader_median_gbps') and round(c['per_reader_median_gbps'],2)}"
          f"  AGGREGATE={c.get('aggregate_gbps') and round(c['aggregate_gbps'],2)} GB/s"
          f"  efficiency={c.get('scaling_efficiency') and round(c['scaling_efficiency'],3)}"
          f"  span={c.get('span_wall_ns') and round(c['span_wall_ns']/1e6,1)}ms")

print("\n=== Q3  REGISTERED ARENA A/B/C (resident file source) ===")
abc = final.get("m1c_arena_abc_gbps") or {}
for k, v in abc.items():
    print(f"  {k:<22} {v and round(v,2)} GB/s")
p = final.get("registered_arena_penalty_pct")
print(f"  REGISTERED_ARENA_PENALTY = {p and round(p,1)}%")
print("  arena_note:", final.get("arena_note"))
print("  source:", json.dumps(final.get("m1c_source") or {})[:200])