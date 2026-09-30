"""Production 7 acceptance: per-run gate + required metrics + optimization proofs."""
import json, glob, os, sys, statistics, re

RUNS = sys.argv[1]
SHA = "3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577"
MIB = 1024 * 1024


def stats(d):
    out = []
    ts = d.get("transport_stats")
    for t in (ts if isinstance(ts, list) else [ts] if isinstance(ts, dict) else []):
        if isinstance(t, dict):
            out.append(t)
    return out


def cov_bytes(d):
    return sum(int((t.get("coverage") or {}).get("source_bytes") or 0) for t in stats(d))


def extract(mf):
    j = json.load(open(mf, encoding="utf-8"))
    art = j["artifacts"]
    a = json.load(open(art["run_artifact"], encoding="utf-8"))
    s = json.load(open(art["summary_artifact"], encoding="utf-8"))
    att = (s.get("attempts") or [{}])[0]
    tel = a.get("golden_telemetry") or {}
    st = {x.get("name"): x for x in (tel.get("stages") or [])}
    ev = tel.get("events") or []
    names = [str(x.get("name") or "") for x in ev]
    ee = j.get("effective_environment") or {}
    res = att.get("result") or att.get("terminal_result") or {}

    def wall(name):
        x = st.get(name) or {}
        e, z = x.get("entry_monotonic_ns"), x.get("end_monotonic_ns")
        return ((z - e) / 1e6) if (e and z) else None

    r = {"run": os.path.basename(mf), "valid": a.get("valid"), "dnf": a.get("dnf"),
         "sha": att.get("observed_output_shas"), "failures": a.get("failures") or [],
         "events": len(ev), "region": (j.get("experiment_identity") or {}).get("region", "")}
    m = re.search(r'"region[_a-z]*"\s*:\s*"([a-z\-]+)"', json.dumps(a))
    r["region"] = m.group(1) if m else ""
    for role, sn in (("clip", "golden_clip_load"), ("unet", "golden_unet_load")):
        d = (st.get(sn) or {}).get("details") or {}
        w = wall(sn)
        b = cov_bytes(d)
        r[f"{role}_load_ms"] = w
        r[f"{role}_src_gbps"] = (b / 1e9) / (w / 1000.0) if (b and w) else None
        r[f"{role}_src_mib"] = b / MIB
    r["clip_fwd_ms"] = tel.get("clip_forward_total_ms")
    r["sampler_ms"] = tel.get("sampler_total_wall_ms")
    r["vae_ms"] = tel.get("vae_decode_ms") or (st.get("golden_vae_decode") or {}).get("entry_monotonic_ns")
    for nm, key in (("golden_vae_decode", "vae_decode"), ("golden_sampler_tail", "sampler_tail"),
                    ("golden_output", "output")):
        x = st.get(nm) or {}
        e, z = x.get("entry_monotonic_ns"), x.get("end_monotonic_ns")
        if e and z:
            r[f"stage_{key}_ms"] = (z - e) / 1e6
    r["golden_wall_ms"] = (st.get("golden_generation") or {}).get("entry_monotonic_ns") and wall("golden_generation")
    r["backend_elapsed_s"] = (j.get("backend") or {}).get("elapsed_seconds")
    r["restore_count"] = att.get("restore_count", tel.get("restore_count"))
    r["request_count"] = att.get("request_count")
    r["fallback_source"] = tel.get("fallback_source")
    r["fallback_reason"] = tel.get("fallback_reason")
    r["gpu"] = (s.get("target") or {}).get("gpu")
    r["resources"] = ((j.get("deploy_inputs") or {}).get("resources") or {})
    if not r["resources"]:
        # run manifests carry deploy_inputs without resources; the authoritative
        # copy lives in the deploy manifest named by the run's receipt.
        rp = j.get("receipt_manifest_path") or ""
        if rp and os.path.exists(rp):
            try:
                dm = json.load(open(rp, encoding="utf-8"))
                r["resources"] = ((dm.get("deploy_inputs") or {}).get("resources") or {})
            except Exception:
                pass
    # geometry / lifecycle / teardown evidence
    r["mmap"] = ee.get("COMFYMODAL_GOLDEN_C0_MMAP_LIFECYCLE")
    r["worker"] = ee.get("COMFYMODAL_GOLDEN_C0_SOURCE_WORKER_KIND")
    r["geom"] = ee.get("COMFYMODAL_GOLDEN_C0_TRANSPORT_GEOMETRY")
    r["teardown_flag"] = ee.get("COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN")
    r["min_containers"] = r["resources"].get("min_containers")
    blob = json.dumps(a)
    r["stale_ready_error"] = "stale_ready_generation" in blob
    r["protocol_error"] = any(k in blob for k in
                              ("SourceProtocolError", "source_thread_failed", "stale_ready_plan_generation",
                               "stale_release_plan_generation"))
    r["gate_fail"] = bool(re.search(r"model_gate|gate_timeout|ModelGate", blob))
    r["arena_bytes"] = None
    for e in ev:
        if e.get("name") == "golden_model_transport_load":
            r["arena_bytes"] = (e.get("fields") or {}).get("c0_arena_bytes")
    # --- optimization 1: minimal teardown ---
    r["teardown_events"] = [n for n in names if "TEARDOWN" in n or "UNLOAD" in n
                            or "unload_all_models" in n]
    r["unload_evidence"] = [k for k in ("unload_all_models", "unload_models",
                                        "free_memory", "empty_cache") if k in blob]
    r["teardown_ms"] = None
    x = st.get("golden_teardown") or {}
    e, z = x.get("entry_monotonic_ns"), x.get("end_monotonic_ns")
    if e and z:
        r["teardown_ms"] = (z - e) / 1e6
    # --- optimization 2: duplicate PNG removed ---
    r["result_keys"] = sorted(res.keys()) if isinstance(res, dict) else []
    r["image_data_keys"] = [k for k in r["result_keys"] if "image" in k.lower()]
    r["image_data_present"] = "image_data" in r["result_keys"]
    r["image_count"] = blob.count('"image_data"')
    r["sha_in_result"] = (res.get("output_sha256") or res.get("sha256")
                          if isinstance(res, dict) else None)
    return r


rows = []
for mf in sorted(glob.glob(os.path.join(RUNS, "run_*.json"))):
    try:
        rows.append(extract(mf))
    except Exception as exc:
        print("extract failed", os.path.basename(mf), exc)

def g(r, k):
    return r.get(k)

print("=" * 100)
print("PRODUCTION 7 ACCEPTANCE GATE")
print("=" * 100)
hdr = ("run", "valid", "sha_ok", "fb", "gpu", "cpu", "minc", "mmap", "worker", "geom",
       "teardown", "stale", "proto", "gate", "clip_gbps", "unet_gbps")
print("{:<15}{:<6}{:<7}{:<4}{:<7}{:<5}{:<6}{:<7}{:<8}{:<9}{:<9}{:<7}{:<7}{:<6}{:>10}{:>10}".format(*hdr))
accepted = []
for r in rows:
    sha_ok = r["sha"] == [SHA]
    fb = "none" if not r["fallback_source"] and not r["fallback_reason"] else "SET"
    checks = dict(
        valid=r["valid"] is True, sha=sha_ok,
        fb=(not r["fallback_source"] and not r["fallback_reason"]),
        gpu=str(r["gpu"]).lower() == "h100!", cpu=str(r["resources"].get("cpu")) == "12",
        minc=r["min_containers"] == 0,
        mmap=r["mmap"] == "whole", worker=r["worker"] == "thread",
        geom=r["geom"] == "qd4_64", teardown=r["teardown_flag"] == "1",
        stale=not r["stale_ready_error"], proto=not r["protocol_error"],
        gate=not r["gate_fail"], fails=not r["failures"])
    ok = all(checks.values())
    if ok:
        accepted.append(r)
    cg = f"{r['clip_src_gbps']:.2f}" if r.get("clip_src_gbps") else "-"
    ug = f"{r['unet_src_gbps']:.2f}" if r.get("unet_src_gbps") else "-"
    print("{:<15}{:<6}{:<7}{:<4}{:<7}{:<5}{:<6}{:<7}{:<8}{:<9}{:<9}{:<7}{:<7}{:<6}{:>10}{:>10}".format(
        r["run"][4:19], str(r["valid"]), str(sha_ok), fb,
        str(r["gpu"]), str(r["resources"].get("cpu")), str(r["min_containers"]),
        str(r["mmap"]), str(r["worker"]), str(r["geom"]), str(r["teardown_flag"]),
        str(r["stale_ready_error"]), str(r["protocol_error"]), str(r["gate_fail"]), cg, ug))
    if not ok:
        bad = [k for k, v in checks.items() if not v]
        print(f"      REJECTED: {bad} failures={r['failures'][:2]}")

print(f"\nACCEPTED: {len(accepted)}/{len(rows)}")
if not accepted:
    sys.exit(0)

def dist(vals, label):
    v = sorted(x for x in vals if isinstance(x, float))
    if not v:
        print(f"  {label}: none"); return
    p90 = v[int(0.9 * (len(v) - 1))]
    print(f"  {label:<22} n={len(v)} min={v[0]:.2f} p50={statistics.median(v):.2f} "
          f"p90={p90:.2f} max={v[-1]:.2f} mean={statistics.mean(v):.2f} "
          f"CV={statistics.pstdev(v)/statistics.mean(v)*100:.1f}%")

print("\n--- SOURCE THROUGHPUT ---")
dist([r["clip_src_gbps"] for r in accepted], "CLIP source GB/s")
dist([r["unet_src_gbps"] for r in accepted], "UNET source GB/s")
print("\n--- STAGE WALLS (ms) ---")
for k in ("clip_load_ms", "unet_load_ms", "clip_fwd_ms", "stage_vae_decode_ms",
          "stage_sampler_tail_ms", "stage_output_ms", "teardown_ms"):
    dist([r.get(k) for r in accepted], k)
dist([r.get("backend_elapsed_s") for r in accepted], "backend elapsed s")

print(f"\n  runs CLIP >= 6.5 GB/s : {sum(1 for r in accepted if (r.get('clip_src_gbps') or 0) >= 6.5)}/{len(accepted)}")
print(f"  runs UNET >= 6.5 GB/s : {sum(1 for r in accepted if (r.get('unet_src_gbps') or 0) >= 6.5)}/{len(accepted)}")
print(f"  regions: {sorted(set(r['region'] for r in accepted))}")
print(f"  arena bytes: {sorted(set(r.get('arena_bytes') for r in accepted))}")
print(f"  restore_count: {sorted(set(str(r.get('restore_count')) for r in accepted))}")
print(f"  request_count: {sorted(set(str(r.get('request_count')) for r in accepted))}")

print("\n--- OPTIMIZATION 1: MINIMAL TEARDOWN (ec76b64c) ---")
for r in accepted[:3]:
    print(f"  {r['run'][4:19]}: flag={r['teardown_flag']} min_containers={r['min_containers']} "
          f"teardown_stage_ms={r.get('teardown_ms')} events={r['teardown_events']} "
          f"unload_evidence={r['unload_evidence']}")
print(f"  runs with unload/model-eviction evidence: "
      f"{sum(1 for r in accepted if r['unload_evidence'])}/{len(accepted)}")

print("\n--- OPTIMIZATION 2: DUPLICATE PNG REMOVED (5ac6f704) ---")
for r in accepted[:3]:
    print(f"  {r['run'][4:19]}: image*keys={r['image_data_keys']} "
          f"image_data_present={r['image_data_present']} occurrences={r['image_count']}")
print(f"  runs carrying image_data: {sum(1 for r in accepted if r['image_data_present'])}/{len(accepted)}")
print(f"  runs with >1 image_data occurrence: {sum(1 for r in accepted if r['image_count'] > 1)}/{len(accepted)}")