#!/usr/bin/env python3
"""Secondary raw-derived analysis over the canonical golden-sickness corpus.

This tool reads ONLY the already-completed canonical outputs under
``reports/golden_sickness_forensic_2026-09-17/`` (per_request.json,
per_request.csv, per_read.csv, onset.csv, exclusions.json, counts.json,
provider_region_summary.json, threshold_summary.json, field_availability.csv,
source_hashes.json).  It never reparses raw bundles, never hashes raw files,
and never mutates runtime/source/tests or the canonical outputs.  All outputs
are new files under the same report directory.

Deterministic and offline: every derived number is a pure function of the
canonical inputs.  Bootstrap/permutation use a fixed seed and small fixed
iteration counts.  Run with ``python tools/analysis/golden_sickness_derived.py``.
"""

from __future__ import annotations

import csv
import json
import math
import random
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Frozen configuration
# ---------------------------------------------------------------------------

REPORT_DIR = (
    Path(__file__).resolve().parents[2]
    / "reports"
    / "golden_sickness_forensic_2026-09-17"
)

# Read-latency thresholds requested for the derived rate tables (ms).
THRESHOLDS_MS = (100, 250, 500, 1000, 2000)
# Thresholds used for onset dynamics (canonical bands).
ONSET_THRESHOLDS_MS = (250, 500, 1000)
# Canonical hard-sickness definition (mirrors golden_sickness_forensic.py).
HARD_SICK_MAX_PREADV_MS = 1000.0
HARD_SICK_LOAD_MS = 5000.0
ROLES = ("clip", "unet")

# Deterministic statistics.
SEED = 20260917
BOOTSTRAP_ITERS = 2000
PERM_ITERS = 5000

# Regime proxy: requests whose dispatch gap exceeds this start a new cluster.
CLUSTER_GAP_MS = 600_000.0

R6 = 6


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def r6(value):
    """Round for deterministic output; pass through None/str."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, str)):
        return value
    try:
        f = float(value)
    except (TypeError, ValueError):
        return value
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, R6)


def num(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def i_or_none(value):
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def load_json(name):
    with open(REPORT_DIR / name, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def load_csv(name):
    with open(REPORT_DIR / name, "r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_json(name, payload):
    path = REPORT_DIR / name
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=False, ensure_ascii=False)
        handle.write("\n")
    return path


def write_csv(name, rows, columns):
    path = REPORT_DIR / name
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def quantile(sorted_values, frac):
    """Linear-interpolation quantile, identical to golden_sickness_forensic.py."""
    n = len(sorted_values)
    if n == 0:
        return None
    if n == 1:
        return sorted_values[0]
    pos = frac * (n - 1)
    low = int(math.floor(pos))
    high = min(low + 1, n - 1)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (pos - low)


def summarize(values):
    vals = sorted(v for v in (num(v) for v in values) if v is not None)
    if not vals:
        return {"n": 0, "min": None, "q1": None, "median": None, "q3": None,
                "p90": None, "p95": None, "p99": None, "max": None, "mean": None}
    return {
        "n": len(vals),
        "min": r6(vals[0]),
        "q1": r6(quantile(vals, 0.25)),
        "median": r6(quantile(vals, 0.5)),
        "q3": r6(quantile(vals, 0.75)),
        "p90": r6(quantile(vals, 0.90)),
        "p95": r6(quantile(vals, 0.95)),
        "p99": r6(quantile(vals, 0.99)),
        "max": r6(vals[-1]),
        "mean": r6(sum(vals) / len(vals)),
    }


def safe_div(numerator, denominator):
    if not denominator:
        return None
    return numerator / denominator


def rate(count, denominator):
    value = safe_div(count, denominator)
    return r6(value) if value is not None else None


def counter_dict(counter, keys=None):
    if keys is None:
        keys = sorted(counter, key=lambda k: str(k))
    return {str(k): counter.get(k, 0) for k in keys}


def population_block(all_rows, valid_rows, invalid_ids):
    """Explicit valid-only population metadata attached to every derived payload.

    Canonical ``per_request.json`` keeps all attempts for audit; every derived
    statistic is computed over ``computed_valid=true`` rows only.  This block makes
    both denominators explicit so no rate is silently reported against the raw
    attempt count.
    """
    all_arms = Counter(r["arm"] for r in all_rows)
    valid_arms = Counter(r["arm"] for r in valid_rows)
    return OrderedDict(
        [
            ("all_attempts_n", len(all_rows)),
            ("valid_n", len(valid_rows)),
            ("invalid_excluded_n", len(invalid_ids)),
            ("invalid_excluded_request_ids", list(invalid_ids)),
            ("all_attempts_sham", all_arms.get("sham", 0)),
            ("all_attempts_split", all_arms.get("split", 0)),
            ("valid_sham", valid_arms.get("sham", 0)),
            ("valid_split", valid_arms.get("split", 0)),
            (
                "inclusion_rule",
                "Every rate/count/threshold/onset/conditional/provider-region/"
                "allocation/time/concentration/severity/correlation/statistical test "
                "uses computed_valid=true rows only. Canonical per_request.json retains "
                "all attempts for audit; canonical per_read.csv retains all reads.",
            ),
        ]
    )


def _hyper_prob(a, b, c, d):
    n = a + b + c + d
    return math.comb(a + b, a) * math.comb(c + d, c) / math.comb(n, a + c)


def fisher_exact(a, b, c, d):
    """Two-sided Fisher exact p-value for [[a,b],[c,d]] (deterministic)."""
    if min(a, b, c, d) < 0:
        return None
    r1, r2, c1 = a + b, c + d, a + c
    n = r1 + r2
    if n == 0:
        return None
    obs = _hyper_prob(a, b, c, d)
    lo = max(0, c1 - r2)
    hi = min(r1, c1)
    p = 0.0
    for x in range(lo, hi + 1):
        pr = _hyper_prob(x, r1 - x, c1 - x, r2 - (c1 - x))
        if pr <= obs * (1 + 1e-12):
            p += pr
    return r6(min(1.0, p))


def _ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    sxy = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    return sxy / math.sqrt(sxx * syy)


def spearman(xs, ys):
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 3:
        return None
    rx = _ranks([p[0] for p in pairs])
    ry = _ranks([p[1] for p in pairs])
    return pearson(rx, ry)


def permutation_p(xs, ys, iters=PERM_ITERS, seed=SEED):
    """Two-sided permutation p for Spearman |rho| (deterministic seed).

    Ranks are computed once; each iteration permutes the y-rank vector, which is
    equivalent to shuffling y values but avoids re-ranking inside the loop.
    """
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 4:
        return None
    x = [p[0] for p in pairs]
    y = [p[1] for p in pairs]
    xr = _ranks(x)
    yr = _ranks(y)
    obs = pearson(xr, yr)
    if obs is None:
        return None
    rng = random.Random(seed)
    ge = 0
    abs_obs = abs(obs)
    work = list(yr)
    for _ in range(iters):
        rng.shuffle(work)
        rho = pearson(xr, work)
        if rho is not None and abs(rho) >= abs_obs:
            ge += 1
    return r6((ge + 1) / (iters + 1))


def bootstrap_diff_ci(flag_a, flag_b, iters=BOOTSTRAP_ITERS, seed=SEED):
    """Seed-fixed bootstrap CI for rate(b)-rate(a) on two 0/1 samples."""
    if not flag_a or not flag_b:
        return None
    rng = random.Random(seed)
    diffs = []
    na, nb = len(flag_a), len(flag_b)
    for _ in range(iters):
        ra = sum(flag_a[rng.randrange(na)] for _ in range(na)) / na
        rb = sum(flag_b[rng.randrange(nb)] for _ in range(nb)) / nb
        diffs.append(rb - ra)
    diffs.sort()
    obs = sum(flag_b) / nb - sum(flag_a) / na
    return {
        "observed_diff": r6(obs),
        "ci95_low": r6(quantile(diffs, 0.025)),
        "ci95_high": r6(quantile(diffs, 0.975)),
        "iters": iters,
        "seed": seed,
    }


def log2_ratio(numerator, denominator):
    if numerator is None or denominator is None or numerator <= 0 or denominator <= 0:
        return None
    return math.log2(numerator / denominator)


# ---------------------------------------------------------------------------
# Load canonical inputs
# ---------------------------------------------------------------------------


def load_corpus():
    records = load_json("per_request.json")
    per_read = load_csv("per_read.csv")
    onset = load_csv("onset.csv")
    exclusions = load_json("exclusions.json")
    counts = load_json("counts.json")
    return records, per_read, onset, exclusions, counts


def index_reads(per_read):
    indexed = defaultdict(lambda: defaultdict(list))
    for row in per_read:
        indexed[row["request_id"]][row["role"]].append(row)
    return indexed


# ---------------------------------------------------------------------------
# Per-request derived model
# ---------------------------------------------------------------------------


def role_read_stats(reads):
    """Threshold/onset/concentration stats for one (request, role) read list."""
    out = {
        "read_count": len(reads),
        "duration_null_count": 0,
        "max_preadv_ms": None,
        "quantiles": {"p50": None, "p90": None, "p95": None, "p99": None},
        "counts_ge": {},
        "rates_ge": {},
        "first_seq_ge": {},
        "last_seq_ge": {},
        "frac_ge": {},
        "toggles_ge": {},
    }
    if not reads:
        return out
    ordered = sorted(reads, key=lambda r: i_or_none(r["read_seq"]) or 0)
    durations = []
    for read in ordered:
        d = num(read["duration_ms"])
        if d is None:
            out["duration_null_count"] += 1
        else:
            durations.append(d)
    if not durations:
        return out
    durations_sorted = sorted(durations)
    out["max_preadv_ms"] = r6(durations_sorted[-1])
    out["quantiles"] = {
        "p50": r6(quantile(durations_sorted, 0.50)),
        "p90": r6(quantile(durations_sorted, 0.90)),
        "p95": r6(quantile(durations_sorted, 0.95)),
        "p99": r6(quantile(durations_sorted, 0.99)),
    }
    n = len(ordered)
    seqs = [i_or_none(r["read_seq"]) for r in ordered]
    for threshold in THRESHOLDS_MS:
        key = str(threshold)
        flags = []  # aligned with `ordered`
        for read in ordered:
            duration = num(read["duration_ms"])
            flags.append(duration is not None and duration >= float(threshold))
        crossings = [
            seq for seq, flag in zip(seqs, flags)
            if flag and seq is not None
        ]
        toggles = sum(1 for i in range(1, n) if flags[i] != flags[i - 1])
        out["counts_ge"][key] = len(crossings)
        out["rates_ge"][key] = rate(len(crossings), n)
        out["first_seq_ge"][key] = min(crossings) if crossings else None
        out["last_seq_ge"][key] = max(crossings) if crossings else None
        out["frac_ge"][key] = rate(len(crossings), n)
        out["toggles_ge"][key] = toggles
    return out


def concentration_stats(reads, role):
    """Worker/region/slot/offset concentration for one (request, role)."""
    out = {
        "role": role,
        "read_count": len(reads),
        "producer_count": 0,
        "region_count": 0,
        "slot_index_present": 0,
        "slot_index_missing": len(reads),
        "producer_hhi": None,
        "producer_top_share": None,
        "region_hhi": None,
        "producer_alternations": None,
        "source_offset_distinct": None,
        "source_offset_min": None,
        "source_offset_max": None,
        "destination_offset_distinct": None,
        "destination_offset_min": None,
        "destination_offset_max": None,
        "destination_span_bytes": None,
        "duplicate_source_offsets": None,
    }
    if not reads:
        return out
    ordered = sorted(reads, key=lambda r: i_or_none(r["read_seq"]) or 0)
    producers = [r.get("producer_id") for r in ordered]
    regions = [r.get("region_id") for r in ordered]
    producer_counts = Counter(p for p in producers if p not in (None, ""))
    region_counts = Counter(g for g in regions if g not in (None, ""))
    n = len(ordered)

    def hhi(counts):
        total = sum(counts.values())
        if not total:
            return None
        return sum((v / total) ** 2 for v in counts.values())

    out["producer_count"] = len(producer_counts)
    out["region_count"] = len(region_counts)
    out["producer_hhi"] = r6(hhi(producer_counts))
    out["region_hhi"] = r6(hhi(region_counts))
    if producer_counts:
        out["producer_top_share"] = r6(max(producer_counts.values()) / sum(producer_counts.values()))
    out["producer_alternations"] = sum(
        1 for i in range(1, n) if producers[i] != producers[i - 1]
    )
    out["slot_index_present"] = sum(
        1 for r in ordered if r.get("slot_index") not in (None, "")
    )
    out["slot_index_missing"] = n - out["slot_index_present"]

    src = [i_or_none(r.get("source_offset")) for r in ordered]
    src = [v for v in src if v is not None]
    dst = [i_or_none(r.get("destination_offset")) for r in ordered]
    dst = [v for v in dst if v is not None]
    if src:
        out["source_offset_distinct"] = len(set(src))
        out["source_offset_min"] = min(src)
        out["source_offset_max"] = max(src)
    if dst:
        out["destination_offset_distinct"] = len(set(dst))
        out["destination_offset_min"] = min(dst)
        out["destination_offset_max"] = max(dst)
        out["destination_span_bytes"] = max(dst) - min(dst)
    requested = [i_or_none(r.get("requested_bytes")) for r in ordered]
    returned = [i_or_none(r.get("returned_bytes")) for r in ordered]
    if requested and returned:
        out["duplicate_source_offsets"] = len(src) - len(set(src)) if src else None
    return out


def derive_request(record, reads_by_role):
    clip_reads = reads_by_role.get("clip", [])
    unet_reads = reads_by_role.get("unet", [])
    clip = role_read_stats(clip_reads)
    unet = role_read_stats(unet_reads)
    thresholds = record.get("thresholds") or {}
    identity = record.get("identity") or {}
    timestamps = record.get("timestamps") or {}
    transport = record.get("transport") or {}

    clip_resource = identity.get("clip_resource")
    unet_resource = identity.get("unet_resource")
    if clip_resource is not None and unet_resource is not None:
        relation = "same" if clip_resource == unet_resource else "switched"
    else:
        relation = None
    direction = None
    if clip_resource is not None and unet_resource is not None:
        direction = "%s->%s" % (clip_resource, unet_resource)

    clip_metrics = (transport.get("clip") or {}).get("metrics") or {}
    unet_metrics = (transport.get("unet") or {}).get("metrics") or {}

    derived = OrderedDict()
    derived["request_id"] = record.get("request_id")
    derived["bundle"] = record.get("bundle")
    derived["arm"] = record.get("arm")
    derived["provider"] = record.get("provider")
    derived["region"] = record.get("region")
    derived["provider_region"] = record.get("provider_region")
    derived["profile"] = record.get("profile")
    derived["clip_resource"] = clip_resource
    derived["unet_resource"] = unet_resource
    derived["other_resource"] = identity.get("other_resource")
    derived["vae_resource"] = identity.get("vae_resource")
    derived["resource_relation"] = relation
    derived["resource_direction"] = direction
    derived["computed_valid"] = (record.get("correctness") or {}).get("computed_valid")
    derived["hard_sick_clip"] = bool(thresholds.get("HARD_SICK_CLIP"))
    derived["hard_sick_unet"] = bool(thresholds.get("HARD_SICK_UNET"))
    derived["sickness_class"] = thresholds.get("sickness_class")
    derived["clip_trigger_class"] = thresholds.get("clip_trigger_class")
    derived["unet_trigger_class"] = thresholds.get("unet_trigger_class")
    derived["onset_pattern"] = thresholds.get("onset_pattern")
    derived["severity_score"] = r6(record.get("severity_score"))
    derived["severity_rank"] = record.get("severity_rank")
    derived["unet_load_ms"] = r6(unet_metrics.get("load_ms"))
    derived["clip_load_ms"] = r6(clip_metrics.get("load_ms"))
    derived["clip_max_preadv_ms"] = clip["max_preadv_ms"]
    derived["unet_max_preadv_ms"] = unet["max_preadv_ms"]
    derived["clip"] = clip
    derived["unet"] = unet
    derived["clip_concentration"] = concentration_stats(clip_reads, "clip")
    derived["unet_concentration"] = concentration_stats(unet_reads, "unet")
    derived["unet_created_vs_reused"] = unet_metrics.get("created_vs_reused")
    derived["clip_created_vs_reused"] = clip_metrics.get("created_vs_reused")
    derived["dispatch_unix_ms"] = i_or_none(timestamps.get("dispatch_unix_ms"))
    derived["duration_ms"] = r6(timestamps.get("duration_ms"))
    derived["manifest_gap_seconds"] = r6(timestamps.get("manifest_gap_seconds"))
    derived["restore_total_ms"] = r6((record.get("restore") or {}).get("restore_total_ms"))
    derived["sampler_total_wall_ms"] = r6(record.get("sampler_total_wall_ms"))
    derived["clip_forward_total_ms"] = r6(record.get("clip_forward_total_ms"))
    derived["stages"] = OrderedDict(
        (name, r6((stage or {}).get("wall_ms")))
        for name, stage in (record.get("stages") or {}).items()
    )
    derived["transport"] = OrderedDict(
        (
            role,
            OrderedDict(
                (
                    field,
                    r6((((transport.get(role) or {}).get("metrics")) or {}).get(field)),
                )
                for field in (
                    "SOURCE_TOTAL_WALL_MS",
                    "SOURCE_SYSCALL_UNION_BUSY_MS",
                    "H2D_TOTAL_WALL_MS",
                    "SOURCE_TO_GPU_READY_MS",
                    "SOURCE_H2D_OVERLAP_MS",
                    "POST_SOURCE_H2D_TAIL_MS",
                    "GPU_COPY_ACTIVE_UNION_MS",
                    "GPU_COPY_ACTIVE_SUM_MS",
                    "GPU_COPY_STREAM_SPAN_MS",
                    "GPU_COPY_IDLE_INSIDE_STREAM_SPAN_MS",
                    "GPU_COPY_TIMING_AVAILABLE",
                    "E27_SOURCE_MECHANISM_PROVEN",
                    "load_ms",
                    "source_read_count",
                    "source_open_count",
                    "source_bytes",
                    "source_block_count",
                    "h2d_submit_count",
                    "h2d_completion_count",
                    "aggregated_submission_count",
                    "non_aggregated_submission_count",
                    "tail_submission_count",
                    "aggregation_fallback_count",
                    "count_short_read",
                    "count_retry",
                    "count_error",
                )
            ),
        )
        for role in ROLES
    )
    return derived


# ---------------------------------------------------------------------------
# Group count tables
# ---------------------------------------------------------------------------


GROUP_FIELDS = OrderedDict(
    [
        ("overall", None),
        ("arm", "arm"),
        ("provider", "provider"),
        ("region", "region"),
        ("provider_region", "provider_region"),
        ("resource_relation", "resource_relation"),
        ("clip_resource", "clip_resource"),
        ("resource_direction", "resource_direction"),
    ]
)


def build_group_entry(derived_rows):
    n = len(derived_rows)
    entry = OrderedDict()
    entry["n_requests"] = n
    entry["computed_valid"] = sum(1 for r in derived_rows if r.get("computed_valid"))
    role_present = {
        role: sum(1 for r in derived_rows if (r.get(role) or {}).get("read_count"))
        for role in ROLES
    }
    entry["role_present"] = role_present
    hard_clip = sum(1 for r in derived_rows if r["hard_sick_clip"])
    hard_unet = sum(1 for r in derived_rows if r["hard_sick_unet"])
    entry["hard_sick_counts"] = {
        "clip": hard_clip,
        "unet": hard_unet,
        "both": sum(1 for r in derived_rows if r["hard_sick_clip"] and r["hard_sick_unet"]),
        "either": sum(1 for r in derived_rows if r["hard_sick_clip"] or r["hard_sick_unet"]),
        "neither": sum(
            1 for r in derived_rows if not r["hard_sick_clip"] and not r["hard_sick_unet"]
        ),
    }
    entry["hard_sick_rates"] = {
        "clip": rate(hard_clip, n),
        "unet": rate(hard_unet, n),
    }
    entry["sickness_class_counts"] = counter_dict(
        Counter(r["sickness_class"] for r in derived_rows)
    )
    entry["onset_pattern_counts"] = counter_dict(
        Counter(r["onset_pattern"] for r in derived_rows)
    )
    threshold_counts = OrderedDict()
    for threshold in THRESHOLDS_MS:
        key = str(threshold)
        block = OrderedDict()
        for role in ROLES:
            denom = role_present[role]
            hits = sum(
                1
                for r in derived_rows
                if (r.get(role) or {}).get("counts_ge", {}).get(key, 0) > 0
            )
            block[role] = {
                "denominator": denom,
                "requests_with_any_ge": hits,
                "rate": rate(hits, denom),
                "total_reads_ge": sum(
                    (r.get(role) or {}).get("counts_ge", {}).get(key, 0)
                    for r in derived_rows
                ),
            }
        threshold_counts[key] = block
    entry["threshold_counts"] = threshold_counts
    entry["quantiles"] = OrderedDict()
    for field in (
        "clip_max_preadv_ms",
        "unet_max_preadv_ms",
        "clip_load_ms",
        "unet_load_ms",
        "severity_score",
        "duration_ms",
        "restore_total_ms",
        "clip_forward_total_ms",
        "sampler_total_wall_ms",
    ):
        entry["quantiles"][field] = summarize(r.get(field) for r in derived_rows)
    entry["created_vs_reused"] = {
        "clip": counter_dict(
            Counter(r.get("clip_created_vs_reused") for r in derived_rows)
        ),
        "unet": counter_dict(
            Counter(r.get("unet_created_vs_reused") for r in derived_rows)
        ),
    }
    return entry


def build_group_counts(derived_rows, population):
    payload = OrderedDict()
    payload["generated_by"] = "tools/analysis/golden_sickness_derived.py"
    payload["source"] = "reports/golden_sickness_forensic_2026-09-17/per_request.json, per_read.csv"
    payload["thresholds_ms"] = list(THRESHOLDS_MS)
    payload["population"] = population
    payload["definitions"] = {
        "threshold_count": "requests whose role has >=1 read with duration_ms >= threshold",
        "denominator": "computed_valid=true requests in group where the role has >=1 observed read",
        "hard_sick": "canonical thresholds.HARD_SICK_* (max_preadv>=1000 OR load>=5000)",
        "computed_valid": "canonical correctness.computed_valid; invalid attempts excluded from all rates",
    }
    payload["groups"] = OrderedDict()
    for group_name, field in GROUP_FIELDS.items():
        if field is None:
            payload["groups"]["overall"] = build_group_entry(derived_rows)
            continue
        buckets = defaultdict(list)
        for row in derived_rows:
            buckets[row.get(field)].append(row)
        payload["groups"][group_name] = OrderedDict(
            (str(key), build_group_entry(rows))
            for key, rows in sorted(buckets.items(), key=lambda kv: str(kv[0]))
        )
    return payload


def build_counts_csv(group_payload):
    rows = []
    for group_name, group_value in group_payload["groups"].items():
        if group_name == "overall":
            iterable = [("overall", group_value)]
        else:
            iterable = group_value.items()
        for label, entry in iterable:
            row = {
                "group_family": group_name,
                "group": label,
                "n_requests": entry["n_requests"],
                "computed_valid": entry["computed_valid"],
                "clip_present": entry["role_present"]["clip"],
                "unet_present": entry["role_present"]["unet"],
                "hard_sick_clip": entry["hard_sick_counts"]["clip"],
                "hard_sick_unet": entry["hard_sick_counts"]["unet"],
                "hard_sick_both": entry["hard_sick_counts"]["both"],
                "clip_sick_rate": entry["hard_sick_rates"]["clip"],
                "unet_sick_rate": entry["hard_sick_rates"]["unet"],
            }
            for threshold in THRESHOLDS_MS:
                key = str(threshold)
                for role in ROLES:
                    block = entry["threshold_counts"][key][role]
                    row["%s_ge_%s_n" % (role, threshold)] = block["requests_with_any_ge"]
                    row["%s_ge_%s_rate" % (role, threshold)] = block["rate"]
            for field in (
                "clip_max_preadv_ms",
                "unet_max_preadv_ms",
                "clip_load_ms",
                "unet_load_ms",
                "severity_score",
            ):
                row[field + "_median"] = entry["quantiles"][field]["median"]
                row[field + "_p95"] = entry["quantiles"][field]["p95"]
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Conditional sickness / carryover / recovery
# ---------------------------------------------------------------------------


def conditional_block(rows, label):
    a = sum(1 for r in rows if r["hard_sick_clip"] and r["hard_sick_unet"])
    b = sum(1 for r in rows if r["hard_sick_clip"] and not r["hard_sick_unet"])
    c = sum(1 for r in rows if not r["hard_sick_clip"] and r["hard_sick_unet"])
    d = sum(1 for r in rows if not r["hard_sick_clip"] and not r["hard_sick_unet"])
    clip_sick = a + b
    unet_sick = a + c
    n = a + b + c + d
    p_given_sick = safe_div(a, clip_sick)
    p_given_healthy = safe_div(c, c + d)
    risk_difference = (
        p_given_sick - p_given_healthy
        if p_given_sick is not None and p_given_healthy is not None
        else None
    )
    return {
        "label": label,
        "n": n,
        "table": {"both": a, "clip_only": b, "unet_only": c, "neither": d},
        "clip_sick": clip_sick,
        "unet_sick": unet_sick,
        "p_unet_sick_given_clip_sick": rate(a, clip_sick),
        "p_unet_sick_given_clip_healthy": rate(c, c + d),
        "p_clip_sick_given_unet_sick": rate(a, unet_sick),
        "p_clip_sick_given_unet_healthy": rate(b, b + d),
        "risk_difference_unet_given_clip": r6(risk_difference),
        "fisher_p_joint_independence": fisher_exact(a, b, c, d),
    }


def recovery_class(role_stats, threshold=500):
    """Classify the >=threshold read sequence by its on/off structure.

    none                    no read crosses the threshold
    persistent_ends_sick    a single contiguous sick block that reaches the last read
    contiguous_then_clear   a single contiguous sick block that clears before the end
    single_episode          exactly one isolated crossing episode (off->on->off)
    alternating             4+ transitions across the threshold
    """
    key = str(threshold)
    count = role_stats["counts_ge"].get(key, 0)
    if not count:
        return "none"
    toggles = role_stats["toggles_ge"].get(key, 0)
    last_seq = role_stats["last_seq_ge"].get(key)
    read_count = role_stats["read_count"]
    if toggles == 0:
        if last_seq is not None and read_count and last_seq >= read_count - 1:
            return "persistent_ends_sick"
        return "contiguous_then_clear"
    if toggles == 2:
        return "single_episode"
    return "alternating"


def build_conditional(records, derived_rows, population):
    by_id = {r["request_id"]: r for r in derived_rows}
    payload = OrderedDict()
    payload["generated_by"] = "tools/analysis/golden_sickness_derived.py"
    payload["source"] = "per_request.json thresholds + per_read.csv (computed_valid rows only)"
    payload["population"] = population
    payload["resource_semantics"] = {
        "same_resource": "sham: identity.clip_resource == identity.unet_resource",
        "switched_resource": "split: clip_resource != unet_resource",
        "verified_counts": {},
    }
    verified = Counter(
        (r.get("arm"), (r.get("identity") or {}).get("other_resource_before_unet_verified"))
        for r in records
    )
    payload["resource_semantics"]["verified_counts"] = {
        str(k): v for k, v in sorted(verified.items(), key=lambda kv: str(kv[0]))
    }

    payload["overall"] = conditional_block(derived_rows, "overall")
    payload["by_arm"] = OrderedDict()
    for arm in sorted({r["arm"] for r in derived_rows}):
        payload["by_arm"][arm] = conditional_block(
            [r for r in derived_rows if r["arm"] == arm], arm
        )
    payload["by_resource_relation"] = OrderedDict()
    for relation in sorted({r["resource_relation"] for r in derived_rows}):
        payload["by_resource_relation"][relation] = conditional_block(
            [r for r in derived_rows if r["resource_relation"] == relation], relation
        )

    # Initial CLIP/UNET sickness and explicit carryover state.
    sham = [r for r in derived_rows if r["arm"] == "sham"]
    split = [r for r in derived_rows if r["arm"] == "split"]
    payload["initial_sickness_and_carryover"] = OrderedDict(
        [
            (
                "initial_clip_hard_sick",
                {
                    "same_resource_sham": sum(1 for r in sham if r["hard_sick_clip"]),
                    "switched_resource_split": sum(1 for r in split if r["hard_sick_clip"]),
                },
            ),
            (
                "initial_unet_hard_sick",
                {
                    "same_resource_sham": sum(1 for r in sham if r["hard_sick_unet"]),
                    "switched_resource_split": sum(1 for r in split if r["hard_sick_unet"]),
                },
            ),
            (
                "carryover_state",
                {
                    "unet_arena_reused_in_same_resource": sum(
                        1 for r in sham if r["unet_created_vs_reused"] == "REUSED"
                    ),
                    "unet_arena_created_in_switched_resource": sum(
                        1 for r in split if r["unet_created_vs_reused"] == "CREATED"
                    ),
                    "other_resource_verified_pristine_before_unet_split": sum(
                        1
                        for r in records
                        if r["arm"] == "split"
                        and (r.get("identity") or {}).get(
                            "other_resource_before_unet_verified"
                        )
                    ),
                    "other_resource_source_fills_before_unet_split_max": max(
                        [
                            (r.get("identity") or {}).get(
                                "other_resource_source_fills_before_unet"
                            )
                            or 0
                            for r in records
                            if r["arm"] == "split"
                        ]
                        or [None]
                    ),
                },
            ),
        ]
    )

    # Arm x joint-sickness independence (Fisher exact on 2x2 arm tables).
    payload["arm_vs_joint_sickness"] = {
        "clip_sick": {
            "sham": sum(1 for r in sham if r["hard_sick_clip"]),
            "split": sum(1 for r in split if r["hard_sick_clip"]),
            "fisher_p": fisher_exact(
                sum(1 for r in sham if r["hard_sick_clip"]),
                sum(1 for r in sham if not r["hard_sick_clip"]),
                sum(1 for r in split if r["hard_sick_clip"]),
                sum(1 for r in split if not r["hard_sick_clip"]),
            ),
        },
        "unet_sick": {
            "sham": sum(1 for r in sham if r["hard_sick_unet"]),
            "split": sum(1 for r in split if r["hard_sick_unet"]),
            "fisher_p": fisher_exact(
                sum(1 for r in sham if r["hard_sick_unet"]),
                sum(1 for r in sham if not r["hard_sick_unet"]),
                sum(1 for r in split if r["hard_sick_unet"]),
                sum(1 for r in split if not r["hard_sick_unet"]),
            ),
        },
    }

    # Severity / recovery classes.
    payload["recovery_classes"] = OrderedDict()
    payload["recovery_classes"]["per_role_500ms"] = OrderedDict()
    for arm in sorted({r["arm"] for r in derived_rows}):
        subset = [r for r in derived_rows if r["arm"] == arm]
        block = OrderedDict()
        for role in ROLES:
            cls = Counter(recovery_class(r[role], 500) for r in subset)
            block[role] = counter_dict(cls)
        payload["recovery_classes"]["per_role_500ms"][arm] = block
    payload["recovery_classes"]["request_level_500ms"] = counter_dict(
        Counter(
            "%s|%s"
            % (recovery_class(r["clip"], 500), recovery_class(r["unet"], 500))
            for r in derived_rows
        )
    )

    # Severity bands from fixed overall quantiles (deterministic cut points).
    severity_values = sorted(
        v for v in (r["severity_score"] for r in derived_rows) if v is not None
    )
    cut_median = quantile(severity_values, 0.5)
    cut_p75 = quantile(severity_values, 0.75)

    def severity_band(value):
        if value is None:
            return "unknown"
        if value <= cut_median:
            return "low_<=median"
        if value <= cut_p75:
            return "mid_median_to_p75"
        return "high_>p75"

    payload["severity_bands"] = {
        "cut_median": r6(cut_median),
        "cut_p75": r6(cut_p75),
        "overall_counts": counter_dict(
            Counter(severity_band(r["severity_score"]) for r in derived_rows)
        ),
        "by_arm": OrderedDict(
            (
                arm,
                counter_dict(
                    Counter(
                        severity_band(r["severity_score"])
                        for r in derived_rows
                        if r["arm"] == arm
                    )
                ),
            )
            for arm in sorted({r["arm"] for r in derived_rows})
        ),
        "by_sickness_class": OrderedDict(
            (
                cls,
                counter_dict(
                    Counter(
                        severity_band(r["severity_score"])
                        for r in derived_rows
                        if r["sickness_class"] == cls
                    )
                ),
            )
            for cls in sorted({r["sickness_class"] for r in derived_rows})
        ),
    }

    # Healthy CLIP -> sick UNET and the inverse.
    payload["discordant_transitions"] = {
        "healthy_clip_sick_unet": [
            {
                "request_id": r["request_id"],
                "arm": r["arm"],
                "provider_region": r["provider_region"],
                "clip_resource": r["clip_resource"],
                "unet_resource": r["unet_resource"],
                "unet_max_preadv_ms": r["unet_max_preadv_ms"],
                "severity_score": r["severity_score"],
            }
            for r in sorted(
                (x for x in derived_rows if not x["hard_sick_clip"] and x["hard_sick_unet"]),
                key=lambda x: -(x["unet_max_preadv_ms"] or 0),
            )
        ],
        "sick_clip_healthy_unet": [
            {
                "request_id": r["request_id"],
                "arm": r["arm"],
                "provider_region": r["provider_region"],
                "clip_max_preadv_ms": r["clip_max_preadv_ms"],
                "severity_score": r["severity_score"],
            }
            for r in sorted(
                (x for x in derived_rows if x["hard_sick_clip"] and not x["hard_sick_unet"]),
                key=lambda x: -(x["clip_max_preadv_ms"] or 0),
            )
        ],
    }

    # Strongest recovery / residual cases using read-level sequences at 500ms.
    recovery_cases = []
    residual_cases = []
    for r in derived_rows:
        for role in ROLES:
            stats = r[role]
            if not stats["counts_ge"].get("500"):
                continue
            cls = recovery_class(stats, 500)
            peak = stats["max_preadv_ms"]
            p95 = stats["quantiles"].get("p95")
            entry = {
                "request_id": r["request_id"],
                "role": role,
                "arm": r["arm"],
                "sickness_class": r["sickness_class"],
                "max_preadv_ms": peak,
                "p95_ms": p95,
                "read_count": stats["read_count"],
                "counts_ge_500": stats["counts_ge"].get("500"),
                "last_seq_ge_500": stats["last_seq_ge"].get("500"),
                "toggles_ge_500": stats["toggles_ge"].get("500"),
                "recovery_class": cls,
            }
            if cls in ("contiguous_then_clear", "single_episode"):
                recovery_cases.append(entry)
            elif cls == "persistent_ends_sick":
                residual_cases.append(entry)
    recovery_cases.sort(key=lambda e: -(e["max_preadv_ms"] or 0))
    residual_cases.sort(key=lambda e: -(e["max_preadv_ms"] or 0))
    payload["strongest_recovery_cases"] = recovery_cases[:10]
    payload["strongest_residual_cases"] = residual_cases[:10]
    return payload


# ---------------------------------------------------------------------------
# Onset dynamics
# ---------------------------------------------------------------------------


def build_onset(derived_rows, population):
    payload = OrderedDict()
    payload["generated_by"] = "tools/analysis/golden_sickness_derived.py"
    payload["source"] = "per_read.csv (read sequence) + per_request.json thresholds"
    payload["population"] = population
    payload["definitions"] = {
        "born_sick": "first read_seq with duration >= T is <= 1",
        "becomes_sick": "first read_seq with duration >= T is > 1",
        "persistent_ends_sick": "single contiguous >=T block reaching the final read",
        "contiguous_then_clear": "single contiguous >=T block clearing before the final read",
        "single_episode": "exactly one isolated off->on->off crossing episode",
        "alternating": "4+ transitions across the threshold in the read sequence",
        "alternation_toggles": "number of transitions in the boolean >=T read sequence",
    }
    payload["per_role_by_arm"] = OrderedDict()
    for arm in sorted({r["arm"] for r in derived_rows}):
        subset = [r for r in derived_rows if r["arm"] == arm]
        block = OrderedDict()
        for role in ROLES:
            role_block = OrderedDict()
            for threshold in ONSET_THRESHOLDS_MS:
                key = str(threshold)
                born = 0
                becomes = 0
                for r in subset:
                    first = r[role]["first_seq_ge"].get(key)
                    if first is None:
                        continue
                    if first <= 1:
                        born += 1
                    else:
                        becomes += 1
                cls = Counter(recovery_class(r[role], threshold) for r in subset)
                role_block[key] = {
                    "born_sick": born,
                    "becomes_sick": becomes,
                    "recovery_class_counts": counter_dict(cls),
                    "mean_toggles": r6(
                        sum(r[role]["toggles_ge"].get(key, 0) for r in subset)
                        / len(subset)
                    )
                    if subset
                    else None,
                }
            block[role] = role_block
        payload["per_role_by_arm"][arm] = block
    payload["canonical_onset_pattern_by_arm"] = OrderedDict()
    for arm in sorted({r["arm"] for r in derived_rows}):
        payload["canonical_onset_pattern_by_arm"][arm] = counter_dict(
            Counter(r["onset_pattern"] for r in derived_rows if r["arm"] == arm)
        )
    payload["canonical_onset_pattern_overall"] = counter_dict(
        Counter(r["onset_pattern"] for r in derived_rows)
    )
    # Per-request onset sequence for auditable drilldown.
    payload["per_request"] = [
        OrderedDict(
            [
                ("request_id", r["request_id"]),
                ("arm", r["arm"]),
                ("sickness_class", r["sickness_class"]),
                ("onset_pattern", r["onset_pattern"]),
                (
                    "clip",
                    OrderedDict(
                        [
                            ("first_seq_ge", r["clip"]["first_seq_ge"]),
                            ("last_seq_ge", r["clip"]["last_seq_ge"]),
                            ("counts_ge", r["clip"]["counts_ge"]),
                            ("toggles_ge", r["clip"]["toggles_ge"]),
                            ("recovery_class_500", recovery_class(r["clip"], 500)),
                        ]
                    ),
                ),
                (
                    "unet",
                    OrderedDict(
                        [
                            ("first_seq_ge", r["unet"]["first_seq_ge"]),
                            ("last_seq_ge", r["unet"]["last_seq_ge"]),
                            ("counts_ge", r["unet"]["counts_ge"]),
                            ("toggles_ge", r["unet"]["toggles_ge"]),
                            ("recovery_class_500", recovery_class(r["unet"], 500)),
                        ]
                    ),
                ),
            ]
        )
        for r in derived_rows
    ]
    return payload


def build_onset_csv(derived_rows):
    rows = []
    for r in derived_rows:
        for role in ROLES:
            stats = r[role]
            row = {
                "request_id": r["request_id"],
                "arm": r["arm"],
                "role": role,
                "read_count": stats["read_count"],
                "max_preadv_ms": stats["max_preadv_ms"],
                "recovery_class_250": recovery_class(stats, 250),
                "recovery_class_500": recovery_class(stats, 500),
                "recovery_class_1000": recovery_class(stats, 1000),
            }
            for threshold in ONSET_THRESHOLDS_MS:
                key = str(threshold)
                row["count_ge_%s" % threshold] = stats["counts_ge"].get(key)
                row["first_seq_ge_%s" % threshold] = stats["first_seq_ge"].get(key)
                row["last_seq_ge_%s" % threshold] = stats["last_seq_ge"].get(key)
                row["toggles_ge_%s" % threshold] = stats["toggles_ge"].get(key)
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# syscall / source / H2D decomposition
# ---------------------------------------------------------------------------


TRANSPORT_FIELDS = (
    "SOURCE_TOTAL_WALL_MS",
    "SOURCE_SYSCALL_UNION_BUSY_MS",
    "H2D_TOTAL_WALL_MS",
    "SOURCE_TO_GPU_READY_MS",
    "SOURCE_H2D_OVERLAP_MS",
    "POST_SOURCE_H2D_TAIL_MS",
    "GPU_COPY_ACTIVE_UNION_MS",
    "GPU_COPY_ACTIVE_SUM_MS",
    "GPU_COPY_STREAM_SPAN_MS",
    "GPU_COPY_IDLE_INSIDE_STREAM_SPAN_MS",
    "load_ms",
    "source_read_count",
    "source_open_count",
    "source_bytes",
    "source_block_count",
    "h2d_submit_count",
    "h2d_completion_count",
    "aggregated_submission_count",
    "non_aggregated_submission_count",
    "tail_submission_count",
    "aggregation_fallback_count",
    "count_short_read",
    "count_retry",
    "count_error",
)


def build_decomposition(derived_rows, population):
    payload = OrderedDict()
    payload["generated_by"] = "tools/analysis/golden_sickness_derived.py"
    payload["source"] = (
        "per_request.json transport.{clip,unet}.metrics; "
        "per_read.csv for observed read counts (computed_valid rows only)"
    )
    payload["population"] = population
    payload["definitions"] = {
        "source_minus_syscall_ms": "SOURCE_TOTAL_WALL_MS - SOURCE_SYSCALL_UNION_BUSY_MS "
        "(time source transport was wall-active but not inside the read syscall union)",
        "load_minus_source_ms": "load_ms - SOURCE_TOTAL_WALL_MS (stage wall outside source transport)",
        "h2d_minus_gpu_union_ms": "H2D_TOTAL_WALL_MS - GPU_COPY_ACTIVE_UNION_MS (H2D wall not covered by GPU copy union)",
        "source_minus_h2d_ms": "SOURCE_TOTAL_WALL_MS - H2D_TOTAL_WALL_MS",
        "overlap_frac_of_source": "SOURCE_H2D_OVERLAP_MS / SOURCE_TOTAL_WALL_MS",
        "unknowns_note": "overlap/tail semantics are taken from canonical field names only; "
        "no raw reparse was performed, so decomposition of unlabeled residual time is unknown.",
    }
    per_role = OrderedDict()
    for role in ROLES:
        rows = []
        for r in derived_rows:
            t = r["transport"][role]
            source = t.get("SOURCE_TOTAL_WALL_MS")
            syscall = t.get("SOURCE_SYSCALL_UNION_BUSY_MS")
            h2d = t.get("H2D_TOTAL_WALL_MS")
            load = t.get("load_ms")
            gpu_union = t.get("GPU_COPY_ACTIVE_UNION_MS")
            row = {
                "request_id": r["request_id"],
                "arm": r["arm"],
                "role": role,
                "provider_region": r["provider_region"],
                "sickness_class": r["sickness_class"],
                "load_ms": load,
                "source_total_wall_ms": source,
                "source_syscall_union_busy_ms": syscall,
                "h2d_total_wall_ms": h2d,
                "source_to_gpu_ready_ms": t.get("SOURCE_TO_GPU_READY_MS"),
                "source_h2d_overlap_ms": t.get("SOURCE_H2D_OVERLAP_MS"),
                "post_source_h2d_tail_ms": t.get("POST_SOURCE_H2D_TAIL_MS"),
                "gpu_copy_active_union_ms": gpu_union,
                "gpu_copy_stream_span_ms": t.get("GPU_COPY_STREAM_SPAN_MS"),
                "gpu_copy_idle_inside_span_ms": t.get("GPU_COPY_IDLE_INSIDE_STREAM_SPAN_MS"),
                "gpu_copy_timing_available": t.get("GPU_COPY_TIMING_AVAILABLE"),
                "read_count_observed": r[role]["read_count"],
                "source_read_count": t.get("source_read_count"),
                "h2d_submit_count": t.get("h2d_submit_count"),
                "h2d_completion_count": t.get("h2d_completion_count"),
                "short_read_count": t.get("count_short_read"),
                "retry_count": t.get("count_retry"),
                "error_count": t.get("count_error"),
            }
            row["syscall_frac_of_load"] = r6(safe_div(syscall, load))
            row["source_frac_of_load"] = r6(safe_div(source, load))
            row["h2d_frac_of_load"] = r6(safe_div(h2d, load))
            row["source_minus_syscall_ms"] = (
                r6(source - syscall) if source is not None and syscall is not None else None
            )
            row["load_minus_source_ms"] = (
                r6(load - source) if load is not None and source is not None else None
            )
            row["h2d_minus_gpu_union_ms"] = (
                r6(h2d - gpu_union) if h2d is not None and gpu_union is not None else None
            )
            row["source_minus_h2d_ms"] = (
                r6(source - h2d) if source is not None and h2d is not None else None
            )
            row["overlap_frac_of_source"] = r6(
                safe_div(t.get("SOURCE_H2D_OVERLAP_MS"), source)
            )
            rows.append(row)
        per_role[role] = rows

    # Aggregate by arm/role and by sickness class/role.
    def aggregates(rows, key_field, key_values):
        block = OrderedDict()
        for value in key_values:
            subset = [row for row in rows if row.get(key_field) == value]
            block[str(value)] = {
                "n": len(subset),
                "syscall_frac_of_load": summarize(
                    row["syscall_frac_of_load"] for row in subset
                ),
                "source_frac_of_load": summarize(
                    row["source_frac_of_load"] for row in subset
                ),
                "h2d_frac_of_load": summarize(row["h2d_frac_of_load"] for row in subset),
                "load_minus_source_ms": summarize(
                    row["load_minus_source_ms"] for row in subset
                ),
                "source_minus_syscall_ms": summarize(
                    row["source_minus_syscall_ms"] for row in subset
                ),
                "overlap_frac_of_source": summarize(
                    row["overlap_frac_of_source"] for row in subset
                ),
            }
        return block

    payload["aggregates"] = OrderedDict()
    for role in ROLES:
        rows = per_role[role]
        payload["aggregates"][role] = {
            "by_arm": aggregates(rows, "arm", sorted({r["arm"] for r in rows})),
            "by_sickness_class": aggregates(
                rows, "sickness_class", sorted({r["sickness_class"] for r in rows})
            ),
        }
    payload["explicit_unknowns"] = [
        "slot_index is empty for every canonical per_read row (per_read.csv), "
        "so slot-level attribution is unknown.",
        "per_read region_id equals producer_id for every row, so region and worker "
        "effects are not separable in the read-level data.",
        "The residual load_ms - SOURCE_TOTAL_WALL_MS is not decomposed by the canonical "
        "schema; it remains an explicit unknown rather than an assigned cause.",
        "Overlap/tail are canonical field scalars; no independent verification was "
        "performed in this offline lane.",
    ]
    return {"per_role": per_role, "summary": payload}


def build_decomposition_csv(per_role):
    columns = list(
        OrderedDict.fromkeys(
            key for rows in per_role.values() for row in rows for key in row.keys()
        )
    )
    rows = [row for role in ROLES for row in per_role[role]]
    return rows, columns


# ---------------------------------------------------------------------------
# Time ordering / gaps / regime proxies
# ---------------------------------------------------------------------------


def build_time_ordering(derived_rows, per_read, population):
    ordered = sorted(
        (r for r in derived_rows if r.get("dispatch_unix_ms") is not None),
        key=lambda r: r["dispatch_unix_ms"],
    )
    payload = OrderedDict()
    payload["generated_by"] = "tools/analysis/golden_sickness_derived.py"
    payload["source"] = "per_request.json timestamps + per_read.csv syscall times"
    payload["population"] = population
    payload["ordering_field"] = "timestamps.dispatch_unix_ms"
    payload["n_with_dispatch"] = len(ordered)
    gaps = []
    for prev, cur in zip(ordered, ordered[1:]):
        gaps.append(cur["dispatch_unix_ms"] - prev["dispatch_unix_ms"])
    payload["inter_request_gap_ms"] = summarize(gaps)
    payload["manifest_gap_seconds"] = summarize(
        r.get("manifest_gap_seconds") for r in derived_rows
    )
    payload["duration_ms"] = summarize(r.get("duration_ms") for r in derived_rows)
    payload["gap_before_present"] = sum(
        1 for r in derived_rows if r.get("gap_before") is not None
    )

    # Cluster requests into contiguous dispatch windows.
    clusters = []
    current = []
    for r in ordered:
        if current and (r["dispatch_unix_ms"] - current[-1]["dispatch_unix_ms"]) > CLUSTER_GAP_MS:
            clusters.append(current)
            current = []
        current.append(r)
    if current:
        clusters.append(current)
    payload["cluster_gap_threshold_ms"] = CLUSTER_GAP_MS
    payload["clusters"] = []
    for index, cluster in enumerate(clusters):
        sick = sum(1 for r in cluster if r["hard_sick_clip"] or r["hard_sick_unet"])
        both = sum(1 for r in cluster if r["hard_sick_clip"] and r["hard_sick_unet"])
        payload["clusters"].append(
            {
                "cluster": index,
                "n": len(cluster),
                "start_dispatch_unix_ms": cluster[0]["dispatch_unix_ms"],
                "end_dispatch_unix_ms": cluster[-1]["dispatch_unix_ms"],
                "span_ms": cluster[-1]["dispatch_unix_ms"] - cluster[0]["dispatch_unix_ms"],
                "arms": counter_dict(Counter(r["arm"] for r in cluster)),
                "providers": counter_dict(Counter(r["provider"] for r in cluster)),
                "sick_requests": sick,
                "sick_rate": rate(sick, len(cluster)),
                "both_sick": both,
            }
        )
    payload["n_clusters"] = len(clusters)

    # Lag-1 autocorrelation of the binary "any sickness" indicator in dispatch order.
    flags = [1 if (r["hard_sick_clip"] or r["hard_sick_unet"]) else 0 for r in ordered]
    if len(flags) > 3 and 0 < sum(flags) < len(flags):
        lag1 = pearson(flags[:-1], flags[1:])
    else:
        lag1 = None
    payload["sickness_indicator_lag1_pearson"] = r6(lag1)
    payload["sickness_indicator_autocorr_note"] = (
        "Pearson correlation of adjacent dispatch-ordered sickness indicators; "
        "descriptive only, no causal claim."
    )

    # Per-read within-request syscall ordering check (read_seq vs syscall clock).
    groups = defaultdict(list)
    for row in per_read:
        groups[(row["request_id"], row["role"])].append(row)
    ordering_issues = 0
    checked_pairs = 0
    comparable_groups = 0
    for rows in groups.values():
        timed = [
            (i_or_none(r["read_seq"]), num(r["syscall_enter_monotonic_ns"]))
            for r in rows
        ]
        timed = [(seq, ts) for seq, ts in timed if seq is not None and ts is not None]
        if len(timed) < 2:
            continue
        comparable_groups += 1
        timed.sort(key=lambda item: item[0])
        checked_pairs += len(timed) - 1
        ordering_issues += sum(
            1 for i in range(1, len(timed)) if timed[i][1] < timed[i - 1][1]
        )
    payload["syscall_order"] = {
        "requests_roles_with_timing": comparable_groups,
        "adjacent_pairs_checked": checked_pairs,
        "readseq_vs_syscall_enter_inversions": ordering_issues,
    }
    return payload


# ---------------------------------------------------------------------------
# Provider / region conditioning and confounding
# ---------------------------------------------------------------------------


def build_conditioning(derived_rows, population):
    payload = OrderedDict()
    payload["generated_by"] = "tools/analysis/golden_sickness_derived.py"
    payload["source"] = "per_request.json provider/region/arm + thresholds (computed_valid rows only)"
    payload["population"] = population
    payload["arm_by_provider"] = OrderedDict()
    for provider in sorted({r["provider"] for r in derived_rows}):
        subset = [r for r in derived_rows if r["provider"] == provider]
        payload["arm_by_provider"][provider] = {
            "n": len(subset),
            "arms": counter_dict(Counter(r["arm"] for r in subset)),
            "clip_sick": sum(1 for r in subset if r["hard_sick_clip"]),
            "unet_sick": sum(1 for r in subset if r["hard_sick_unet"]),
            "clip_sick_rate": rate(sum(1 for r in subset if r["hard_sick_clip"]), len(subset)),
            "unet_sick_rate": rate(sum(1 for r in subset if r["hard_sick_unet"]), len(subset)),
        }
    payload["arm_by_region"] = OrderedDict()
    for region in sorted({r["region"] for r in derived_rows}):
        subset = [r for r in derived_rows if r["region"] == region]
        payload["arm_by_region"][region] = {
            "n": len(subset),
            "arms": counter_dict(Counter(r["arm"] for r in subset)),
            "clip_sick_rate": rate(sum(1 for r in subset if r["hard_sick_clip"]), len(subset)),
            "unet_sick_rate": rate(sum(1 for r in subset if r["hard_sick_unet"]), len(subset)),
        }

    # Within-provider_region arm contrast (only cells with both arms present).
    payload["within_provider_region_arm_contrast"] = OrderedDict()
    regions = sorted({r["provider_region"] for r in derived_rows})
    for pr in regions:
        subset = [r for r in derived_rows if r["provider_region"] == pr]
        sham = [r for r in subset if r["arm"] == "sham"]
        split = [r for r in subset if r["arm"] == "split"]
        if not sham or not split:
            continue
        payload["within_provider_region_arm_contrast"][pr] = {
            "sham_n": len(sham),
            "split_n": len(split),
            "sham_both_sick": sum(1 for r in sham if r["hard_sick_clip"] and r["hard_sick_unet"]),
            "split_both_sick": sum(1 for r in split if r["hard_sick_clip"] and r["hard_sick_unet"]),
            "sham_clip_sick": sum(1 for r in sham if r["hard_sick_clip"]),
            "split_clip_sick": sum(1 for r in split if r["hard_sick_clip"]),
            "clip_sick_fisher_p": fisher_exact(
                sum(1 for r in sham if r["hard_sick_clip"]),
                sum(1 for r in sham if not r["hard_sick_clip"]),
                sum(1 for r in split if r["hard_sick_clip"]),
                sum(1 for r in split if not r["hard_sick_clip"]),
            ),
        }

    # Direct standardization of overall arm rates to the overall provider_region mix.
    overall_mix = Counter(r["provider_region"] for r in derived_rows)
    total = sum(overall_mix.values())
    std = OrderedDict()
    for arm in sorted({r["arm"] for r in derived_rows}):
        subset = [r for r in derived_rows if r["arm"] == arm]
        weighted = 0.0
        covered = 0
        for pr, count in overall_mix.items():
            cell = [r for r in subset if r["provider_region"] == pr]
            if not cell:
                continue
            weighted += (count / total) * (sum(1 for r in cell if r["hard_sick_clip"]) / len(cell))
            covered += count
        std[arm] = {
            "crude_clip_sick_rate": rate(
                sum(1 for r in subset if r["hard_sick_clip"]), len(subset)
            ),
            "provider_region_standardized_clip_sick_rate": r6(weighted),
            "standardization_coverage_weight": rate(covered, total),
        }
    payload["direct_standardized_rates"] = std
    payload["confounding_note"] = (
        "Arm is strongly imbalanced across provider_region in this corpus; crude arm "
        "comparisons are therefore conditioned on provider_region in the table above. "
        "Small per-cell counts limit inference."
    )
    return payload


# ---------------------------------------------------------------------------
# A/B resource and order
# ---------------------------------------------------------------------------


def build_resource_order(derived_rows, population):
    payload = OrderedDict()
    payload["generated_by"] = "tools/analysis/golden_sickness_derived.py"
    payload["source"] = "per_request.json identity.* + transport.*.created_vs_reused (computed_valid rows only)"
    payload["population"] = population
    payload["created_vs_reused_by_arm"] = OrderedDict()
    for arm in sorted({r["arm"] for r in derived_rows}):
        subset = [r for r in derived_rows if r["arm"] == arm]
        payload["created_vs_reused_by_arm"][arm] = {
            "clip": counter_dict(Counter(r["clip_created_vs_reused"] for r in subset)),
            "unet": counter_dict(Counter(r["unet_created_vs_reused"] for r in subset)),
        }
    payload["by_clip_resource"] = OrderedDict()
    for resource in sorted({r["clip_resource"] for r in derived_rows}):
        subset = [r for r in derived_rows if r["clip_resource"] == resource]
        payload["by_clip_resource"][resource] = {
            "n": len(subset),
            "arms": counter_dict(Counter(r["arm"] for r in subset)),
            "clip_sick": sum(1 for r in subset if r["hard_sick_clip"]),
            "unet_sick": sum(1 for r in subset if r["hard_sick_unet"]),
            "both_sick": sum(
                1 for r in subset if r["hard_sick_clip"] and r["hard_sick_unet"]
            ),
            "clip_sick_rate": rate(sum(1 for r in subset if r["hard_sick_clip"]), len(subset)),
            "unet_sick_rate": rate(sum(1 for r in subset if r["hard_sick_unet"]), len(subset)),
            "severity_median": summarize(r["severity_score"] for r in subset)["median"],
        }
    payload["by_direction"] = OrderedDict()
    for direction in sorted({r["resource_direction"] for r in derived_rows}):
        subset = [r for r in derived_rows if r["resource_direction"] == direction]
        payload["by_direction"][direction] = {
            "n": len(subset),
            "arm": counter_dict(Counter(r["arm"] for r in subset)),
            "clip_sick_rate": rate(sum(1 for r in subset if r["hard_sick_clip"]), len(subset)),
            "unet_sick_rate": rate(sum(1 for r in subset if r["hard_sick_unet"]), len(subset)),
            "both_sick": sum(1 for r in subset if r["hard_sick_clip"] and r["hard_sick_unet"]),
        }
    # Split-side A->B vs B->A independence test.
    ab = [r for r in derived_rows if r["resource_direction"] == "A->B"]
    ba = [r for r in derived_rows if r["resource_direction"] == "B->A"]
    payload["direction_contrast"] = {
        "A_to_B_n": len(ab),
        "B_to_A_n": len(ba),
        "unet_sick_fisher_p": fisher_exact(
            sum(1 for r in ab if r["hard_sick_unet"]),
            sum(1 for r in ab if not r["hard_sick_unet"]),
            sum(1 for r in ba if r["hard_sick_unet"]),
            sum(1 for r in ba if not r["hard_sick_unet"]),
        ),
    }
    payload["note"] = (
        "clip arena is CREATED in all %d computed_valid requests; unet arena is REUSED "
        "only in the %d valid same-resource (sham) requests and CREATED in all %d valid "
        "switched-resource (split) requests, matching the arm split exactly."
        % (
            population["valid_n"], population["valid_sham"], population["valid_split"],
        )
    )
    return payload


# ---------------------------------------------------------------------------
# Worker / slot / destination concentration
# ---------------------------------------------------------------------------


def build_concentration(derived_rows, population):
    payload = OrderedDict()
    payload["generated_by"] = "tools/analysis/golden_sickness_derived.py"
    payload["source"] = "per_read.csv producer_id/region_id/slot_index/source_offset/destination_offset (computed_valid rows only)"
    payload["population"] = population
    payload["missingness"] = {
        "slot_index": "empty string for every canonical per_read row (100% missing); "
        "derived valid-only statistics cover computed_valid requests only",
        "region_id": "identical to producer_id for every row; not separable",
        "physical_provenance": "constant 'golden_serial._read_at' for every row",
    }
    payload["by_arm_role"] = OrderedDict()
    for arm in sorted({r["arm"] for r in derived_rows}):
        subset = [r for r in derived_rows if r["arm"] == arm]
        block = OrderedDict()
        for role in ROLES:
            stats = [r[role + "_concentration"] for r in subset]
            block[role] = {
                "n_requests": len(stats),
                "total_reads": sum(s["read_count"] for s in stats),
                "producer_count": summarize(s["producer_count"] for s in stats),
                "producer_hhi": summarize(s["producer_hhi"] for s in stats),
                "producer_top_share": summarize(s["producer_top_share"] for s in stats),
                "producer_alternations": summarize(s["producer_alternations"] for s in stats),
                "source_offset_distinct": summarize(s["source_offset_distinct"] for s in stats),
                "destination_offset_distinct": summarize(
                    s["destination_offset_distinct"] for s in stats
                ),
                "slot_index_present_total": sum(s["slot_index_present"] for s in stats),
                "slot_index_missing_total": sum(s["slot_index_missing"] for s in stats),
            }
        payload["by_arm_role"][arm] = block
    payload["by_sickness_class_role"] = OrderedDict()
    for cls in sorted({r["sickness_class"] for r in derived_rows}):
        subset = [r for r in derived_rows if r["sickness_class"] == cls]
        block = OrderedDict()
        for role in ROLES:
            stats = [r[role + "_concentration"] for r in subset]
            block[role] = {
                "n_requests": len(stats),
                "producer_hhi_median": summarize(s["producer_hhi"] for s in stats)["median"],
                "producer_alternations_median": summarize(
                    s["producer_alternations"] for s in stats
                )["median"],
                "source_offset_distinct_median": summarize(
                    s["source_offset_distinct"] for s in stats
                )["median"],
                "destination_offset_distinct_median": summarize(
                    s["destination_offset_distinct"] for s in stats
                )["median"],
            }
        payload["by_sickness_class_role"][cls] = block
    # Correlation of concentration with severity.
    payload["severity_correlations"] = {}
    for role in ROLES:
        xs_hhi = [r[role + "_concentration"]["producer_hhi"] for r in derived_rows]
        ys = [r["severity_score"] for r in derived_rows]
        payload["severity_correlations"][role + "_producer_hhi"] = {
            "spearman": r6(spearman(xs_hhi, ys)),
            "perm_p": permutation_p(xs_hhi, ys),
            "n": sum(1 for x, y in zip(xs_hhi, ys) if x is not None and y is not None),
        }
        xs_alt = [r[role + "_concentration"]["producer_alternations"] for r in derived_rows]
        payload["severity_correlations"][role + "_producer_alternations"] = {
            "spearman": r6(spearman(xs_alt, ys)),
            "perm_p": permutation_p(xs_alt, ys),
            "n": sum(1 for x, y in zip(xs_alt, ys) if x is not None and y is not None),
        }
    return payload


# ---------------------------------------------------------------------------
# Stage asymmetry and severity correlations
# ---------------------------------------------------------------------------


def build_stage_severity(derived_rows, population):
    payload = OrderedDict()
    payload["generated_by"] = "tools/analysis/golden_sickness_derived.py"
    payload["source"] = "per_request.json stages + severity_score (computed_valid rows only)"
    payload["population"] = population
    stage_names = sorted(
        {name for r in derived_rows for name in (r.get("stages") or {})}
    )
    payload["stage_quantiles_by_arm"] = OrderedDict()
    for arm in sorted({r["arm"] for r in derived_rows}):
        subset = [r for r in derived_rows if r["arm"] == arm]
        payload["stage_quantiles_by_arm"][arm] = OrderedDict(
            (
                name,
                summarize((r.get("stages") or {}).get(name) for r in subset),
            )
            for name in stage_names
        )
    # Asymmetry ratios (clip vs unet load, forward vs load, sampler vs load).
    ratios = OrderedDict()
    for r in derived_rows:
        stages = r.get("stages") or {}
        clip_load = stages.get("golden_clip_load")
        unet_load = stages.get("golden_unet_load")
        clip_fwd = stages.get("golden_clip_forward")
        ratios[r["request_id"]] = {
            "request_id": r["request_id"],
            "arm": r["arm"],
            "sickness_class": r["sickness_class"],
            "log2_clip_load_over_unet_load": r6(log2_ratio(clip_load, unet_load)),
            "log2_clip_forward_over_clip_load": r6(log2_ratio(clip_fwd, clip_load)),
            "log2_sampling_over_clip_load": r6(
                log2_ratio(stages.get("golden_sampling"), clip_load)
            ),
        }
    payload["asymmetry_by_arm"] = OrderedDict()
    for arm in sorted({r["arm"] for r in derived_rows}):
        subset = [v for v in ratios.values() if v["arm"] == arm]
        payload["asymmetry_by_arm"][arm] = {
            key: summarize(v[key] for v in subset)
            for key in (
                "log2_clip_load_over_unet_load",
                "log2_clip_forward_over_clip_load",
                "log2_sampling_over_clip_load",
            )
        }
    # Correlations with severity.
    severity = [r["severity_score"] for r in derived_rows]
    corr_targets = {
        "clip_max_preadv_ms": [r["clip_max_preadv_ms"] for r in derived_rows],
        "unet_max_preadv_ms": [r["unet_max_preadv_ms"] for r in derived_rows],
        "clip_load_ms": [r["clip_load_ms"] for r in derived_rows],
        "unet_load_ms": [r["unet_load_ms"] for r in derived_rows],
        "duration_ms": [r["duration_ms"] for r in derived_rows],
        "restore_total_ms": [r["restore_total_ms"] for r in derived_rows],
        "clip_forward_total_ms": [r["clip_forward_total_ms"] for r in derived_rows],
        "sampler_total_wall_ms": [r["sampler_total_wall_ms"] for r in derived_rows],
    }
    for stage_name in (
        "golden_restore",
        "golden_clip_load",
        "golden_unet_load",
        "golden_sampling",
        "golden_vae_decode",
    ):
        corr_targets["stage_" + stage_name] = [
            (r.get("stages") or {}).get(stage_name) for r in derived_rows
        ]
    payload["severity_correlations"] = OrderedDict()
    for name, values in corr_targets.items():
        payload["severity_correlations"][name] = {
            "spearman": r6(spearman(values, severity)),
            "perm_p": permutation_p(values, severity),
            "n": sum(1 for v in values if v is not None),
        }
    # Cross-role correlation.
    payload["cross_role_correlations"] = {
        "clip_max_vs_unet_max": {
            "spearman": r6(
                spearman(
                    [r["clip_max_preadv_ms"] for r in derived_rows],
                    [r["unet_max_preadv_ms"] for r in derived_rows],
                )
            ),
            "perm_p": permutation_p(
                [r["clip_max_preadv_ms"] for r in derived_rows],
                [r["unet_max_preadv_ms"] for r in derived_rows],
            ),
        },
        "clip_load_vs_unet_load": {
            "spearman": r6(
                spearman(
                    [r["clip_load_ms"] for r in derived_rows],
                    [r["unet_load_ms"] for r in derived_rows],
                )
            ),
            "perm_p": permutation_p(
                [r["clip_load_ms"] for r in derived_rows],
                [r["unet_load_ms"] for r in derived_rows],
            ),
        },
    }
    return payload


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def build_tests(derived_rows, population):
    payload = OrderedDict()
    payload["generated_by"] = "tools/analysis/golden_sickness_derived.py"
    payload["population"] = population
    payload["method"] = {
        "fisher": "two-sided exact Fisher test, deterministic",
        "bootstrap": {
            "iters": BOOTSTRAP_ITERS,
            "seed": SEED,
            "interval": "percentile 2.5/97.5 of rate(second)-rate(first)",
        },
        "permutation": {"iters": PERM_ITERS, "seed": SEED},
    }
    sham = [r for r in derived_rows if r["arm"] == "sham"]
    split = [r for r in derived_rows if r["arm"] == "split"]
    payload["arm_clip_sickness"] = {
        "sham": {"sick": sum(1 for r in sham if r["hard_sick_clip"]), "n": len(sham)},
        "split": {"sick": sum(1 for r in split if r["hard_sick_clip"]), "n": len(split)},
        "fisher_p": fisher_exact(
            sum(1 for r in sham if r["hard_sick_clip"]),
            sum(1 for r in sham if not r["hard_sick_clip"]),
            sum(1 for r in split if r["hard_sick_clip"]),
            sum(1 for r in split if not r["hard_sick_clip"]),
        ),
        "bootstrap_rate_diff": bootstrap_diff_ci(
            [1 if r["hard_sick_clip"] else 0 for r in sham],
            [1 if r["hard_sick_clip"] else 0 for r in split],
        ),
    }
    payload["arm_unet_sickness"] = {
        "sham": {"sick": sum(1 for r in sham if r["hard_sick_unet"]), "n": len(sham)},
        "split": {"sick": sum(1 for r in split if r["hard_sick_unet"]), "n": len(split)},
        "fisher_p": fisher_exact(
            sum(1 for r in sham if r["hard_sick_unet"]),
            sum(1 for r in sham if not r["hard_sick_unet"]),
            sum(1 for r in split if r["hard_sick_unet"]),
            sum(1 for r in split if not r["hard_sick_unet"]),
        ),
        "bootstrap_rate_diff": bootstrap_diff_ci(
            [1 if r["hard_sick_unet"] else 0 for r in sham],
            [1 if r["hard_sick_unet"] else 0 for r in split],
        ),
    }
    payload["arm_both_sickness"] = {
        "sham": {
            "sick": sum(1 for r in sham if r["hard_sick_clip"] and r["hard_sick_unet"]),
            "n": len(sham),
        },
        "split": {
            "sick": sum(1 for r in split if r["hard_sick_clip"] and r["hard_sick_unet"]),
            "n": len(split),
        },
        "fisher_p": fisher_exact(
            sum(1 for r in sham if r["hard_sick_clip"] and r["hard_sick_unet"]),
            sum(1 for r in sham if not (r["hard_sick_clip"] and r["hard_sick_unet"])),
            sum(1 for r in split if r["hard_sick_clip"] and r["hard_sick_unet"]),
            sum(1 for r in split if not (r["hard_sick_clip"] and r["hard_sick_unet"])),
        ),
        "bootstrap_rate_diff": bootstrap_diff_ci(
            [1 if (r["hard_sick_clip"] and r["hard_sick_unet"]) else 0 for r in sham],
            [1 if (r["hard_sick_clip"] and r["hard_sick_unet"]) else 0 for r in split],
        ),
    }
    return payload


# ---------------------------------------------------------------------------
# Evidence matrix
# ---------------------------------------------------------------------------


def build_validation(all_rows, valid_rows, onset_rows, valid_onset_rows,
                     counts_data, per_read, valid_per_read, invalid_ids) -> dict:
    """Cross-check the valid-only derived model against the canonical files.

    ``all_rows`` / canonical ``per_read`` retain every attempt for audit;
    ``valid_rows`` / ``valid_per_read`` are the computed_valid=true population that
    every derived statistic uses.  The checks below assert the exact valid-only
    counts and that the per-read/onset reconciliation is valid-only, so no rate is
    silently reported against the 142-attempt population.
    """
    canonical_per_read_role_rows = Counter(row["role"] for row in per_read)
    valid_per_read_role_rows = Counter(row["role"] for row in valid_per_read)
    derived_role_reads = Counter()
    for r in valid_rows:
        for role in ROLES:
            derived_role_reads[role] += r[role]["read_count"]
    onset_map = {(row["request_id"], row["role"]): row for row in valid_onset_rows}
    mismatches = 0
    compared = 0
    for r in valid_rows:
        for role in ROLES:
            row = onset_map.get((r["request_id"], role))
            if row is None:
                mismatches += 1
                continue
            compared += 1
            if i_or_none(row["read_count"]) != r[role]["read_count"]:
                mismatches += 1
    expected_clip = (counts_data.get("sham") or {}).get("hard_sick_clip", 0) + (
        counts_data.get("split") or {}
    ).get("hard_sick_clip", 0)
    expected_unet = (counts_data.get("sham") or {}).get("hard_sick_unet", 0) + (
        counts_data.get("split") or {}
    ).get("hard_sick_unet", 0)
    expected_sham = (counts_data.get("sham") or {}).get("computed_valid")
    expected_split = (counts_data.get("split") or {}).get("computed_valid")
    all_sham = sum(1 for r in all_rows if r["arm"] == "sham")
    all_split = sum(1 for r in all_rows if r["arm"] == "split")
    valid_sham = sum(1 for r in valid_rows if r["arm"] == "sham")
    valid_split = sum(1 for r in valid_rows if r["arm"] == "split")
    hard_clip = sum(1 for r in valid_rows if r["hard_sick_clip"])
    hard_unet = sum(1 for r in valid_rows if r["hard_sick_unet"])
    class_counts = Counter(r["sickness_class"] for r in valid_rows)
    headline = OrderedDict()
    headline.update(
        [
            ("all_attempts_n", len(all_rows)),
            ("valid_n", len(valid_rows)),
            ("valid_sham", valid_sham),
            ("valid_split", valid_split),
            ("hard_sick_clip", hard_clip),
            ("hard_sick_unet", hard_unet),
            ("both_sick", sum(
                1 for r in valid_rows if r["hard_sick_clip"] and r["hard_sick_unet"]
            )),
            ("clip_sick_only", class_counts.get("CLIP_SICK_ONLY", 0)),
            ("unet_sick_only", class_counts.get("UNET_SICK_ONLY", 0)),
            ("neither", class_counts.get("NEITHER", 0)),
        ]
    )
    headline_checks = OrderedDict(
        [
            (
                "valid_n_matches_canonical",
                len(valid_rows) == (expected_sham or 0) + (expected_split or 0),
            ),
            ("valid_sham_matches_canonical", valid_sham == expected_sham),
            ("valid_split_matches_canonical", valid_split == expected_split),
            (
                "valid_n_equals_all_minus_invalid",
                len(valid_rows) == len(all_rows) - len(invalid_ids),
            ),
            ("hard_sick_clip_matches_canonical", hard_clip == expected_clip),
            ("hard_sick_unet_matches_canonical", hard_unet == expected_unet),
        ]
    )
    headline.update(headline_checks)
    headline.update([("all_checks_match", all(headline_checks.values()))])
    return OrderedDict(
        [
            ("all_attempts_records", len(all_rows)),
            ("valid_records", len(valid_rows)),
            ("invalid_records", len(invalid_ids)),
            ("invalid_request_ids", list(invalid_ids)),
            ("all_attempts_sham", all_sham),
            ("all_attempts_split", all_split),
            ("unique_request_ids", len({r["request_id"] for r in all_rows})),
            ("counts_total_records", counts_data.get("total_records")),
            ("total_records_match", len(all_rows) == counts_data.get("total_records")),
            ("counts_computed_valid", (expected_sham or 0) + (expected_split or 0)),
            ("valid_records_match_counts", len(valid_rows) == (expected_sham or 0) + (expected_split or 0)),
            ("hard_sick_clip_all_attempts", sum(1 for r in all_rows if r["hard_sick_clip"])),
            ("hard_sick_clip", hard_clip),
            ("hard_sick_clip_expected", expected_clip),
            ("hard_sick_clip_match", hard_clip == expected_clip),
            ("hard_sick_unet_all_attempts", sum(1 for r in all_rows if r["hard_sick_unet"])),
            ("hard_sick_unet", hard_unet),
            ("hard_sick_unet_expected", expected_unet),
            ("hard_sick_unet_match", hard_unet == expected_unet),
            ("headline_valid_counts", headline),
            ("onset_rows_canonical", len(onset_rows)),
            ("onset_rows_valid", len(valid_onset_rows)),
            ("onset_role_rows_compared", compared),
            ("onset_read_count_mismatches", mismatches),
            ("canonical_per_read_rows", len(per_read)),
            ("valid_per_read_rows", len(valid_per_read)),
            ("excluded_invalid_per_read_rows", len(per_read) - len(valid_per_read)),
            ("canonical_per_read_role_rows", dict(canonical_per_read_role_rows)),
            ("valid_per_read_role_rows", dict(valid_per_read_role_rows)),
            ("derived_role_reads", dict(derived_role_reads)),
            (
                "per_read_role_rows_match",
                all(valid_per_read_role_rows[role] == derived_role_reads[role] for role in ROLES),
            ),
        ]
    )


def build_evidence_matrix(derived_rows, counts, exclusions, population, all_attempts_n):
    fields = {row["field_path"]: row for row in load_csv("field_availability.csv")}
    matrix = OrderedDict()
    matrix["generated_by"] = "tools/analysis/golden_sickness_derived.py"
    matrix["instructions"] = (
        "Maps each derived result family to exact canonical source paths and the "
        "missingness observed in the canonical corpus. No raw bundle was reparsed. "
        "All derived families are computed over computed_valid=true rows only; the "
        "canonical per_request.json retains all attempts for audit."
    )
    matrix["population"] = population
    matrix["canonical_inputs"] = OrderedDict(
        [
            ("per_request.json", {"path": "reports/golden_sickness_forensic_2026-09-17/per_request.json", "records": all_attempts_n, "computed_valid_records": population["valid_n"]}),
            ("per_request.csv", {"path": "reports/golden_sickness_forensic_2026-09-17/per_request.csv"}),
            ("per_read.csv", {"path": "reports/golden_sickness_forensic_2026-09-17/per_read.csv", "rows": counts.get("per_read_rows")}),
            ("onset.csv", {"path": "reports/golden_sickness_forensic_2026-09-17/onset.csv", "rows": counts.get("onset_rows")}),
            ("exclusions.json", {"path": "reports/golden_sickness_forensic_2026-09-17/exclusions.json", "exclusions": counts.get("exclusions")}),
            ("counts.json", {"path": "reports/golden_sickness_forensic_2026-09-17/counts.json", "total_records": counts.get("total_records")}),
        ]
    )
    families = OrderedDict()
    families["threshold_counts_and_rates"] = {
        "sources": [
            "per_request.json: [].arm, [].provider, [].region, [].provider_region",
            "per_request.json: [].thresholds.HARD_SICK_CLIP/UNET",
            "per_read.csv: request_id, role, read_seq, duration_ms",
        ],
        "derived_file": "derived_counts.json / derived_counts.csv",
        "denominator": "computed_valid=true requests per group with >=1 observed read for the role "
        "(valid_n=%d, sham=%d, split=%d)" % (
            population["valid_n"], population["valid_sham"], population["valid_split"],
        ),
        "missingness": "duration_ms null count: %d (valid rows only)"
        % sum(r[role]["duration_null_count"] for r in derived_rows for role in ROLES),
    }
    families["sickness_conditional_and_recovery"] = {
        "sources": [
            "per_request.json: [].identity.clip_resource/unet_resource/other_resource",
            "per_request.json: [].thresholds.sickness_class",
            "per_read.csv: duration_ms sequences",
        ],
        "derived_file": "derived_conditional.json",
        "denominator": "valid_n=%d computed_valid requests (%d sham / %d split); "
        "role-level denominators per table cell; canonical %d attempts retained for audit"
        % (
            population["valid_n"], population["valid_sham"], population["valid_split"],
            population["all_attempts_n"],
        ),
        "missingness": "other_resource_before_unet_verified false for %d valid sham rows "
        "(sham has no distinct other resource by construction)"
        % population["valid_sham"],
    }
    families["onset_dynamics"] = {
        "sources": [
            "per_read.csv: role, read_seq, duration_ms",
            "per_request.json: [].thresholds.onset_pattern",
        ],
        "derived_file": "derived_onset.json / derived_onset.csv",
        "denominator": "computed_valid requests with >=1 read for the role",
        "missingness": "read_seq present for all rows; invalid request reads excluded "
        "from derived onset (retained in canonical per_read.csv)",
    }
    families["transport_decomposition"] = {
        "sources": [
            "per_request.json: [].transport.clip.metrics, [].transport.unet.metrics",
            "fields: SOURCE_TOTAL_WALL_MS, SOURCE_SYSCALL_UNION_BUSY_MS, "
            "H2D_TOTAL_WALL_MS, SOURCE_H2D_OVERLAP_MS, POST_SOURCE_H2D_TAIL_MS, "
            "GPU_COPY_ACTIVE_UNION_MS",
        ],
        "derived_file": "derived_transport_decomposition.json / .csv",
        "denominator": "%d computed_valid requests x 2 roles" % population["valid_n"],
        "missingness": "all listed fields present for the %d valid records "
        "(field_availability.csv covers all %d attempts); residual load time is an "
        "explicit unknown" % (population["valid_n"], population["all_attempts_n"]),
    }
    families["time_ordering_clusters"] = {
        "sources": [
            "per_request.json: [].timestamps.dispatch_unix_ms/",
            "duration_ms/manifest_gap_seconds",
        ],
        "derived_file": "derived_time_ordering.json",
        "denominator": "computed_valid requests with dispatch_unix_ms (%d)" % sum(
            1 for r in derived_rows if r.get("dispatch_unix_ms") is not None
        ),
        "missingness": "timestamps.gap_before null for all %d valid requests "
        "(canonical %d attempts)" % (population["valid_n"], population["all_attempts_n"]),
    }
    families["provider_region_conditioning"] = {
        "sources": [
            "per_request.json: [].provider, [].region, [].provider_region, [].arm",
        ],
        "derived_file": "derived_conditional.json + derived_evidence_matrix.json",
        "denominator": "valid-only group n",
        "missingness": "1 valid request has provider CLOUD_PROVIDER_UNSPECIFIED",
    }
    families["resource_order"] = {
        "sources": [
            "per_request.json: [].identity.*, [].transport.*.metrics.created_vs_reused",
        ],
        "derived_file": "derived_resource_order.json",
        "denominator": "%d computed_valid requests" % population["valid_n"],
        "missingness": "none for the listed fields",
    }
    families["concentration"] = {
        "sources": [
            "per_read.csv: producer_id, region_id, slot_index, source_offset, destination_offset",
        ],
        "derived_file": "derived_concentration.json",
        "denominator": "per computed_valid request x role",
        "missingness": "slot_index empty for all 88892 canonical per_read rows; "
        "region_id==producer_id for all rows; physical_provenance constant. "
        "Derived statistics exclude the invalid request's reads",
    }
    families["stage_asymmetry_severity"] = {
        "sources": [
            "per_request.json: [].stages.*.wall_ms, [].severity_score",
        ],
        "derived_file": "derived_stage_severity.json",
        "denominator": "%d computed_valid requests" % population["valid_n"],
        "missingness": "all 12 stages present for the %d valid records "
        "(canonical %d attempts)" % (population["valid_n"], population["all_attempts_n"]),
    }
    families["statistical_tests"] = {
        "sources": ["derived arm/role contingency tables"],
        "derived_file": "derived_tests.json",
        "denominator": "valid-only sham n=%d, split n=%d" % (
            population["valid_sham"], population["valid_split"],
        ),
        "method": "exact Fisher + seed-fixed bootstrap/permutation",
    }
    matrix["families"] = families
    matrix["exclusions"] = {
        "count": len(exclusions.get("exclusions") or []),
        "items": exclusions.get("exclusions") or [],
    }
    matrix["field_availability_spot_check"] = {
        key: fields[key]
        for key in (
            "transport.clip.reads[].slot_index",
            "transport.clip.reads[].producer_id",
            "transport.clip.reads[].region_id",
            "identity.other_resource_source_fills_before_unet",
        )
        if key in fields
    }
    return matrix


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def fmt(value, digits=4):
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return ("%%.%df" % digits) % value
    return str(value)


def build_markdown(derived_rows, group_payload, conditional, onset, decomposition, time_ordering, conditioning, resource_order, concentration, stage_severity, tests, counts, evidence, population):
    lines = []
    add = lines.append
    add("# Derived Golden-Sickness Analysis")
    add("")
    add("Offline, deterministic secondary analysis of the canonical corpus in")
    add("`reports/golden_sickness_forensic_2026-09-17/`. Generated by")
    add("`tools/analysis/golden_sickness_derived.py`. No raw bundle was reparsed and no")
    add("runtime/source/test file was modified.")
    add("")
    add("## Corpus")
    add("")
    add("- Attempts retained (canonical audit): **%d** (sham %d / split %d)" % (
        population["all_attempts_n"], population["all_attempts_sham"],
        population["all_attempts_split"],
    ))
    add("- Valid analysis population (`computed_valid=true`): **%d** (sham %d / split %d)" % (
        population["valid_n"], population["valid_sham"], population["valid_split"],
    ))
    add("- Excluded invalid attempts from all derived statistics: %d (%s)" % (
        population["invalid_excluded_n"],
        ", ".join(population["invalid_excluded_request_ids"]) or "none",
    ))
    add("- Canonical counts: total_records=%s, computed_valid sham=%s/split=%s, exclusions=%s" % (
        counts.get("total_records"),
        counts.get("sham", {}).get("computed_valid"),
        counts.get("split", {}).get("computed_valid"),
        counts.get("exclusions"),
    ))
    add("- per_read rows=%s canonical (all attempts); derived valid-only reads=%s; "
        "onset rows=%s canonical" % (
            counts.get("per_read_rows"), counts.get("valid_per_read_rows"),
            counts.get("onset_rows"),
        ))
    add("")
    add("## Threshold counts and rates (per_read-derived)")
    add("")
    add("Denominator is the number of `computed_valid=true` requests in the group with at")
    add("least one observed read for that role. Invalid attempts are retained in canonical")
    add("`per_request.json` for audit but excluded from every derived denominator.")
    add("`ge_T` = request has >=1 read with duration >= T ms.")
    add("")
    add("| group | n | clip_sick | unet_sick | clip_ge_100 | unet_ge_100 | clip_ge_2000 | unet_ge_2000 |")
    add("|---|---|---|---|---|---|---|---|")
    for label, entry in [
        ("overall", group_payload["groups"]["overall"]),
    ] + [
        ("arm:" + k, v) for k, v in group_payload["groups"]["arm"].items()
    ] + [
        ("pc:" + k, v) for k, v in group_payload["groups"]["provider_region"].items()
    ]:
        add("| %s | %d | %d | %d | %d | %d | %d | %d |" % (
            label,
            entry["n_requests"],
            entry["hard_sick_counts"]["clip"],
            entry["hard_sick_counts"]["unet"],
            entry["threshold_counts"]["100"]["clip"]["requests_with_any_ge"],
            entry["threshold_counts"]["100"]["unet"]["requests_with_any_ge"],
            entry["threshold_counts"]["2000"]["clip"]["requests_with_any_ge"],
            entry["threshold_counts"]["2000"]["unet"]["requests_with_any_ge"],
        ))
    add("")
    add("## Sickness conditional on arm (same vs switched resource)")
    add("")
    add("| arm | n | clip sick | unet sick | both | P(unet sick given clip sick) | P(unet sick given clip healthy) | Fisher p |")
    add("|---|---|---|---|---|---|---|---|")
    for arm, block in conditional["by_arm"].items():
        add("| %s | %d | %d | %d | %d | %s | %s | %s |" % (
            arm, block["n"], block["clip_sick"], block["unet_sick"],
            block["table"]["both"], fmt(block["p_unet_sick_given_clip_sick"]),
            fmt(block["p_unet_sick_given_clip_healthy"]),
            fmt(block["fisher_p_joint_independence"]),
        ))
    add("")
    carry = conditional["initial_sickness_and_carryover"]
    add("Carryover state: unet arena reused in %d/%d valid same-resource (sham) requests "
        "and created in %d/%d valid switched-resource (split) requests; the non-CLIP "
        "resource was verified pristine before UNET in %d/%d valid split requests with "
        "max source fills before UNET = %s." % (
            carry["carryover_state"]["unet_arena_reused_in_same_resource"],
            population["valid_sham"],
            carry["carryover_state"]["unet_arena_created_in_switched_resource"],
            population["valid_split"],
            carry["carryover_state"]["other_resource_verified_pristine_before_unet_split"],
            population["valid_split"],
            carry["carryover_state"]["other_resource_source_fills_before_unet_split_max"],
        ))
    add("")
    add("Severity bands (overall cut median=%s, p75=%s): %s" % (
        fmt(conditional["severity_bands"]["cut_median"]),
        fmt(conditional["severity_bands"]["cut_p75"]),
        ", ".join(
            "%s=%d" % (k, v)
            for k, v in sorted(conditional["severity_bands"]["overall_counts"].items())
        ),
    ))
    add("")
    add("Discordant transitions: healthy-CLIP->sick-UNET n=%d; sick-CLIP->healthy-UNET n=%d." % (
        len(conditional["discordant_transitions"]["healthy_clip_sick_unet"]),
        len(conditional["discordant_transitions"]["sick_clip_healthy_unet"]),
    ))
    add("")
    add("## Onset dynamics (born-sick vs becomes-sick)")
    add("")
    add("| arm | role | T=500 born | T=500 becomes | ends-sick | single-episode | alternating | contiguous-then-clear |")
    add("|---|---|---|---|---|---|---|---|")
    for arm, roles in onset["per_role_by_arm"].items():
        for role, thresholds in roles.items():
            block = thresholds["500"]
            counts_ = block["recovery_class_counts"]
            add("| %s | %s | %d | %d | %d | %d | %d | %d |" % (
                arm, role, block["born_sick"], block["becomes_sick"],
                counts_.get("persistent_ends_sick", 0),
                counts_.get("single_episode", 0),
                counts_.get("alternating", 0),
                counts_.get("contiguous_then_clear", 0),
            ))
    add("")
    recovery = conditional["strongest_recovery_cases"]
    residual = conditional["strongest_residual_cases"]
    add("Strongest recovery cases (peak >=500 ms, sequence returns below threshold): "
        + (", ".join(
            "%s/%s %s ms (%s)" % (
                e["request_id"], e["role"], fmt(e["max_preadv_ms"], 0), e["recovery_class"]
            )
            for e in recovery[:5]
        ) or "none") + ".")
    add("")
    add("Strongest residual cases (peak >=500 ms, sequence ends >=500 ms): "
        + (", ".join(
            "%s/%s %s ms" % (
                e["request_id"], e["role"], fmt(e["max_preadv_ms"], 0)
            )
            for e in residual[:5]
        ) or "none") + ".")
    add("")
    add("## syscall / source / H2D decomposition")
    add("")
    add("| role | arm | n | median source/load | median syscall/load | median h2d/load | median overlap/source |")
    add("|---|---|---|---|---|---|---|")
    for role, blocks in decomposition["summary"]["aggregates"].items():
        for arm, block in blocks["by_arm"].items():
            add("| %s | %s | %d | %s | %s | %s | %s |" % (
                role, arm, block["n"],
                fmt(block["source_frac_of_load"]["median"]),
                fmt(block["syscall_frac_of_load"]["median"]),
                fmt(block["h2d_frac_of_load"]["median"]),
                fmt(block["overlap_frac_of_source"]["median"]),
            ))
    add("")
    add("Explicit unknowns: slot_index is empty for every one of the 88892 canonical reads;")
    add("region_id equals producer_id for every canonical read; the residual")
    add("`load_ms - SOURCE_TOTAL_WALL_MS` is not decomposed by the canonical schema.")
    add("")
    add("## Time ordering and regime proxies")
    add("")
    add("- Dispatch-ordered requests: %d; clusters at >%s ms gap: %d" % (
        time_ordering["n_with_dispatch"],
        fmt(time_ordering["cluster_gap_threshold_ms"], 0),
        time_ordering["n_clusters"],
    ))
    add("- Inter-request gap (ms): median %s, p95 %s, max %s" % (
        fmt(time_ordering["inter_request_gap_ms"]["median"]),
        fmt(time_ordering["inter_request_gap_ms"]["p95"]),
        fmt(time_ordering["inter_request_gap_ms"]["max"]),
    ))
    add("- Sickness-indicator lag-1 Pearson: %s (descriptive)" % fmt(
        time_ordering["sickness_indicator_lag1_pearson"]
    ))
    add("- `timestamps.gap_before` present in %d/%d valid requests; `manifest_gap_seconds` "
        "is constant %s across all valid requests" % (
            time_ordering["gap_before_present"],
            population["valid_n"],
            fmt(time_ordering["manifest_gap_seconds"]["median"]),
        ))
    add("- read_seq vs syscall_enter clock inversions: %d of %d adjacent pairs "
        "across %d request-role groups" % (
            time_ordering["syscall_order"]["readseq_vs_syscall_enter_inversions"],
            time_ordering["syscall_order"]["adjacent_pairs_checked"],
            time_ordering["syscall_order"]["requests_roles_with_timing"],
        ))
    add("")
    add("## Provider/region conditioning")
    add("")
    add(conditioning["confounding_note"])
    add("")
    add("| arm | crude clip-sick | standardized clip-sick | coverage weight |")
    add("|---|---|---|---|")
    for arm, block in conditioning["direct_standardized_rates"].items():
        add("| %s | %s | %s | %s |" % (
            arm, fmt(block["crude_clip_sick_rate"]),
            fmt(block["provider_region_standardized_clip_sick_rate"]),
            fmt(block["standardization_coverage_weight"]),
        ))
    add("")
    add("## Resource A/B and order")
    add("")
    add("- " + resource_order["note"])
    add("")
    add("| clip resource | n | clip sick | unet sick | both |")
    add("|---|---|---|---|---|")
    for res, block in resource_order["by_clip_resource"].items():
        add("| %s | %d | %d | %d | %d |" % (
            res, block["n"], block["clip_sick"], block["unet_sick"], block["both_sick"],
        ))
    add("")
    add("Split direction: A->B n=%d, B->A n=%d; unet-sick Fisher p=%s." % (
        resource_order["direction_contrast"]["A_to_B_n"],
        resource_order["direction_contrast"]["B_to_A_n"],
        fmt(resource_order["direction_contrast"]["unet_sick_fisher_p"]),
    ))
    add("")
    add("## Concentration (worker / slot / destination)")
    add("")
    add("| arm | role | reads | producer_hhi median | top worker share median | destination offsets distinct median |")
    add("|---|---|---|---|---|---|")
    for arm, roles in concentration["by_arm_role"].items():
        for role, block in roles.items():
            add("| %s | %s | %d | %s | %s | %s |" % (
                arm, role, block["total_reads"],
                fmt(block["producer_hhi"]["median"]),
                fmt(block["producer_top_share"]["median"]),
                fmt(block["destination_offset_distinct"]["median"]),
            ))
    add("")
    add("- Slot index is empty for every one of the 88892 canonical reads; `region_id`")
    add("  equals `producer_id` for every canonical read (4 workers/regions, HHI ~0.25,")
    add("  ~even shares), so worker and region attribution are not separable. Destination")
    add("  offsets are near-fully distinct per request-role (median equals read count).")
    add("")
    add("## Stage asymmetry and severity correlations")
    add("")
    add("| metric | Spearman rho | permutation p | n |")
    add("|---|---|---|---|")
    for name, block in stage_severity["severity_correlations"].items():
        add("| %s | %s | %s | %d |" % (
            name, fmt(block["spearman"]), fmt(block["perm_p"]), block["n"],
        ))
    add("")
    add("## Statistical tests")
    add("")
    for name in ("arm_clip_sickness", "arm_unet_sickness", "arm_both_sickness"):
        block = tests[name]
        add("- %s: sham %d/%d vs split %d/%d, Fisher p=%s, bootstrap diff 95%% CI [%s, %s]" % (
            name,
            block["sham"]["sick"], block["sham"]["n"],
            block["split"]["sick"], block["split"]["n"],
            fmt(block["fisher_p"]),
            fmt(block["bootstrap_rate_diff"]["ci95_low"]),
            fmt(block["bootstrap_rate_diff"]["ci95_high"]),
        ))
    add("")
    add("## Evidence matrix")
    add("")
    add("`derived_evidence_matrix.json` maps every family below to its canonical source")
    add("paths and missingness. Families: " + ", ".join(evidence["families"].keys()) + ".")
    add("")
    add("## Interpretation guardrails")
    add("")
    add("- All statements above are raw-derived associations on the %d computed_valid" % population["valid_n"])
    add("  requests (from %d retained attempts); they are not causal claims." % population["all_attempts_n"])
    add("- Provider/region, arm, and resource relation are structurally imbalanced, so")
    add("  crude and standardized rates are both reported.")
    add("- Small counts in several cells make Fisher/bootstrap intervals wide.")
    add("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    records, per_read, onset, exclusions, counts_data = load_corpus()
    reads_index = index_reads(per_read)

    # Canonical audit population: every retained attempt, valid or not.
    all_derived = []
    for record in records:
        reads_by_role = reads_index.get(record.get("request_id"), {})
        all_derived.append(derive_request(record, reads_by_role))

    # Inferential population: computed_valid=true rows only.  Invalid attempts stay in
    # canonical per_request.json / per_read.csv for audit but never enter a statistic.
    invalid_ids = [
        r["request_id"] for r in all_derived if not r.get("computed_valid")
    ]
    invalid_set = set(invalid_ids)
    valid_derived = [r for r in all_derived if r["request_id"] not in invalid_set]
    valid_records = [r for r in records if r["request_id"] not in invalid_set]
    valid_per_read = [row for row in per_read if row["request_id"] not in invalid_set]
    valid_onset = [row for row in onset if row["request_id"] not in invalid_set]

    population = population_block(all_derived, valid_derived, invalid_ids)

    counts = dict(counts_data)
    counts["per_read_rows"] = len(per_read)
    counts["valid_per_read_rows"] = len(valid_per_read)
    counts["excluded_invalid_per_read_rows"] = len(per_read) - len(valid_per_read)
    counts["onset_rows"] = len(onset)
    counts["valid_onset_rows"] = len(valid_onset)

    group_payload = build_group_counts(valid_derived, population)
    conditional = build_conditional(valid_records, valid_derived, population)
    onset_payload = build_onset(valid_derived, population)
    decomposition = build_decomposition(valid_derived, population)
    time_ordering = build_time_ordering(valid_derived, valid_per_read, population)
    conditioning = build_conditioning(valid_derived, population)
    resource_order = build_resource_order(valid_derived, population)
    concentration = build_concentration(valid_derived, population)
    stage_severity = build_stage_severity(valid_derived, population)
    tests = build_tests(valid_derived, population)
    validation_checks = build_validation(
        all_derived, valid_derived, onset, valid_onset, counts_data, per_read,
        valid_per_read, invalid_ids,
    )
    evidence = build_evidence_matrix(
        valid_derived, counts, exclusions, population, len(all_derived)
    )
    evidence["validation"] = validation_checks

    outputs = []
    # derived_requests.json is the per-request audit model and intentionally keeps all
    # retained attempts; every other output is valid-only.
    outputs.append(write_json("derived_requests.json", all_derived))
    counts_csv_rows = build_counts_csv(group_payload)
    outputs.append(write_json("derived_counts.json", group_payload))
    outputs.append(write_csv("derived_counts.csv", counts_csv_rows, list(counts_csv_rows[0].keys())))
    outputs.append(write_json("derived_conditional.json", conditional))
    outputs.append(write_json("derived_onset.json", onset_payload))
    onset_csv_rows = build_onset_csv(valid_derived)
    outputs.append(write_csv("derived_onset.csv", onset_csv_rows, list(onset_csv_rows[0].keys())))
    decomp_rows, decomp_columns = build_decomposition_csv(decomposition["per_role"])
    outputs.append(write_json("derived_transport_decomposition.json", OrderedDict(
        [
            ("generated_by", decomposition["summary"]["generated_by"]),
            ("source", decomposition["summary"]["source"]),
            ("population", decomposition["summary"]["population"]),
            ("definitions", decomposition["summary"]["definitions"]),
            ("aggregates", decomposition["summary"]["aggregates"]),
            ("explicit_unknowns", decomposition["summary"]["explicit_unknowns"]),
            ("per_role", decomposition["per_role"]),
        ]
    )))
    outputs.append(write_csv("derived_transport_decomposition.csv", decomp_rows, decomp_columns))
    outputs.append(write_json("derived_time_ordering.json", time_ordering))
    outputs.append(write_json("derived_conditioning.json", conditioning))
    outputs.append(write_json("derived_resource_order.json", resource_order))
    outputs.append(write_json("derived_concentration.json", concentration))
    outputs.append(write_json("derived_stage_severity.json", stage_severity))
    outputs.append(write_json("derived_tests.json", tests))
    outputs.append(write_json("derived_evidence_matrix.json", evidence))

    markdown = build_markdown(
        valid_derived, group_payload, conditional, onset_payload, decomposition,
        time_ordering, conditioning, resource_order, concentration, stage_severity,
        tests, counts, evidence, population,
    )
    md_path = REPORT_DIR / "DERIVED_ANALYSIS.md"
    md_path.write_text(markdown, encoding="utf-8")
    outputs.append(md_path)

    validation: dict = OrderedDict(validation_checks)
    validation["per_read_rows"] = len(per_read)
    validation["valid_per_read_rows"] = len(valid_per_read)
    validation["derived_outputs"] = len(outputs)
    validation["all_attempts_n"] = len(all_derived)
    validation["valid_n"] = len(valid_derived)
    validation["clip_reads_total"] = sum(r["clip"]["read_count"] for r in valid_derived)
    validation["unet_reads_total"] = sum(r["unet"]["read_count"] for r in valid_derived)
    validation["sham"] = sum(1 for r in valid_derived if r["arm"] == "sham")
    validation["split"] = sum(1 for r in valid_derived if r["arm"] == "split")
    validation["both_sick"] = sum(
        1 for r in valid_derived if r["hard_sick_clip"] and r["hard_sick_unet"]
    )
    validation["clip_plus_unet_reads"] = sum(
        r[role]["read_count"] for r in valid_derived for role in ROLES
    )
    validation["slot_index_missing_clip_unet_reads"] = sum(
        r[role + "_concentration"]["slot_index_missing"] for r in valid_derived for role in ROLES
    )
    validation["threshold_ge_1000_clip_requests"] = sum(
        1 for r in valid_derived if r["clip"]["counts_ge"].get("1000", 0) > 0
    )
    validation["threshold_ge_1000_unet_requests"] = sum(
        1 for r in valid_derived if r["unet"]["counts_ge"].get("1000", 0) > 0
    )
    validation["output_dir"] = str(REPORT_DIR)
    print(json.dumps(validation, indent=2))
    return validation


if __name__ == "__main__":
    main()
