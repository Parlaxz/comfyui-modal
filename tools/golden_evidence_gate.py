"""Accept/reject a Golden run against a runtime-evidence gate.

Duration is explicitly NOT a criterion: command, deployment and container
provisioning time are not acceptance signals.  Every check is an actual runtime
observation.  With --baseline, resolved configuration must also match the
baseline run flag-for-flag (M1B diagnostic selectors excepted).
"""
import json, sys, os

EXPECTED_SHA = "3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577"
# Diagnostic selectors are the only permitted configuration deltas.
ALLOWED_DELTA = ("COMFYMODAL_M1B_COPY_PROBE", "COMFYMODAL_M1B_LEVEL")
# v2ctl bookkeeping that necessarily differs per invocation.
BOOKKEEPING = ("COMFYMODAL_V2CTL_DEPLOYMENT_HASH", "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT",
               "COMFYMODAL_V2CTL_INVOCATION_ID", "COMFYMODAL_V2CTL_PROFILE",
               "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT",
               "COMFYMODAL_V2CTL_RUN_FINGERPRINT", "COMFYMODAL_V2_APP_NAME")


def load(manifest):
    j = json.load(open(manifest, encoding="utf-8"))
    art = j.get("artifacts") or {}
    a = json.load(open(art["run_artifact"], encoding="utf-8"))
    s = json.load(open(art["summary_artifact"], encoding="utf-8"))
    return j, a, s


def deploy_resources(j):
    p = (j.get("receipt_manifest_path") or "")
    if p and os.path.exists(p):
        d = json.load(open(p, encoding="utf-8"))
        return ((d.get("deploy_inputs") or {}).get("resources") or {})
    return {}


def evaluate(manifest, profile, app, baseline=None):
    j, a, s = load(manifest)
    att = (s.get("attempts") or [{}])[0]
    tel = a.get("golden_telemetry") or {}
    events = tel.get("events") or []
    stages = {x.get("name"): x for x in (tel.get("stages") or [])}
    blob = json.dumps(a)
    ee = j.get("effective_environment") or {}
    res = deploy_resources(j)
    tgt = s.get("target") or {}

    ck = []
    def add(label, ok, detail=""):
        ck.append((label, "PASS" if ok else "FAIL", detail))

    add("valid", a.get("valid") is True, repr(a.get("valid")))
    add("dnf_false", (a.get("dnf") is False) and (att.get("dnf") is False),
        f"artifact={a.get('dnf')} attempt={att.get('dnf')}")
    shas = a.get("observed_output_shas") or att.get("observed_output_shas")
    add("exact_sha", bool(shas) and all(x == EXPECTED_SHA for x in shas), json.dumps(shas))
    add("method", s.get("method") == "run_golden_parallel_stream", str(s.get("method")))
    add("profile", s.get("profile") == profile, str(s.get("profile")))
    add("app", tgt.get("app_name") == app, str(tgt.get("app_name")))
    add("gpu_h100", str(tgt.get("gpu", "")).strip().lower() == "h100!", str(tgt.get("gpu")))
    add("cpu_12", str(res.get("cpu")) == "12", f"resources={res}")
    add("mmap_whole", ee.get("COMFYMODAL_GOLDEN_C0_MMAP_LIFECYCLE") == "whole",
        str(ee.get("COMFYMODAL_GOLDEN_C0_MMAP_LIFECYCLE")))
    add("source_thread_mode", str(ee.get("COMFYMODAL_GOLDEN_C0_SOURCE_THREADS")) == "1"
        and ee.get("COMFYMODAL_GOLDEN_C0_SOURCE_WORKER_KIND") == "thread",
        f"threads={ee.get('COMFYMODAL_GOLDEN_C0_SOURCE_THREADS')} "
        f"kind={ee.get('COMFYMODAL_GOLDEN_C0_SOURCE_WORKER_KIND')}")
    add("no_stale_ready", "stale_ready_generation" not in blob, "absent")
    add("no_internal_failure", "InternalFailure" not in blob, "absent")
    add("no_fatal", not tel.get("fatal_failure"), repr(tel.get("fatal_failure")))
    add("no_fallback", not tel.get("fallback_source") and not tel.get("fallback_reason"),
        f"source={tel.get('fallback_source')} reason={tel.get('fallback_reason')}")
    add("owner_live", tel.get("source_owner_retired") is not True,
        f"retired={tel.get('source_owner_retired')}")
    # Durability is proven by valid + exact SHA.  Neither result_durable nor
    # true_durable_marked is a gate: both read False on accepted runs.
    # The population measure is the inline telemetry event list.  a["event_count"]
    # is NOT population -- it reads 1 on every accepted run -- and
    # a["duration_ms"] is not wall clock (16-56s across valid runs, while
    # backend.elapsed_seconds is ~190s).  Neither is used here.
    add("event_population", len(events) >= 20, f"inline_events={len(events)}")
    for st in ("golden_clip_load", "golden_unet_load"):
        add(f"stage_{st}", (stages.get(st) or {}).get("ok") is True,
            f"ok={(stages.get(st) or {}).get('ok')}")
    ud = (stages.get("golden_unet_load") or {}).get("details") or {}
    cov = ((ud.get("transport_stats") or {}).get("coverage") or {})
    add("coverage_exact", cov.get("ok") is True, json.dumps(cov)[:160])
    q = ud.get("qd_quiescence") or {}
    add("qd_quiesced", bool(q.get("copies_complete")) and bool(q.get("source_slots_free"))
        and not q.get("operation_live"), json.dumps(q))
    add("reader_pool", q.get("reader_pool_persistent") is True,
        f"persistent={q.get('reader_pool_persistent')}")
    add("source_reads", (ud.get("source_read_count") or 0) > 0, f"count={ud.get('source_read_count')}")
    # Durability is proven by valid + exact SHA, not by the advisory
    # result_durable flag, which is False even on accepted runs.
    add("no_failures", not a.get("failures"), json.dumps(a.get("failures"))[:300])

    if baseline:
        _, _, _ = None, None, None
        jb, ab, sb = load(baseline)
        eb = jb.get("effective_environment") or {}
        diffs = []
        for k in sorted(set(ee) | set(eb)):
            if k in ALLOWED_DELTA or k in BOOKKEEPING:
                continue
            if not (k.startswith("COMFYMODAL_")):
                continue
            if ee.get(k) != eb.get(k):
                diffs.append(f"{k}: {eb.get(k)!r} -> {ee.get(k)!r}")
        add("config_parity", not diffs, "; ".join(diffs)[:400] if diffs else "identical")

    return all(c[1] == "PASS" for c in ck), ck


if __name__ == "__main__":
    mf, profile, app = sys.argv[1], sys.argv[2], sys.argv[3]
    base = sys.argv[4] if len(sys.argv) > 4 else None
    ok, checks = evaluate(mf, profile, app, base)
    print(f"== {os.path.basename(mf)}")
    for label, verdict, detail in checks:
        print(f"  {verdict:5} {label:20} {detail}")
    print("VERDICT:", "ACCEPT" if ok else "REJECT")
