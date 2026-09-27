#!/usr/bin/env python3
"""C12 — safetensors layout analysis + byte-balanced shard planning (no model conversion).

Reads a safetensors *header* from one of:
  --input <local .safetensors>   (reads only the header region, never the payload)
  --input <local header.json>    (JSON dump from comfymodal_runtime's
                                 _c6_parse_safetensors_header / safe_open .keys())
  --input <https://...>          (HTTP Range fetch of the header only)

Then:
  1. Reports physical layout statistics: tensor order, sizes, size classes,
     gaps/alignment, contiguity validation (safetensors data section is
     byte-packed in header order; this tool verifies it for the given file).
  2. Generates shard plans for N = --shards (default "2,4,8"): greedy packing
     in header order at whole-tensor boundaries, target = total_bytes / N.
     Each shard is a CONTIGUOUS byte range of the original file, so a future
     splitter can copy payload bytes verbatim (byte-identical tensors).
  3. Prints balance stats and (with --save-plans) writes a JSON plan file
     mapping tensor key -> shard -> byte offset within shard.

Stdlib only. Never downloads tensor payloads.
"""

import argparse
import json
import math
import struct
import sys
import urllib.request

HEADER_LEN_PREFIX = 8  # bytes: little-endian u64 header length


def fetch_range(url, start, end):
    """Fetch bytes [start, end) of url via HTTP Range. Returns bytes."""
    req = urllib.request.Request(url, headers={
        "Range": "bytes=%d-%d" % (start, end),
        "User-Agent": "c12-plan-safetensors-shards/1.0",
        "Accept": "*/*",
    })
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def fetch_header_from_url(url):
    """Range-fetch the safetensors header JSON without touching the payload.
    Returns (header_dict, true_header_len) — the length from the 8-byte prefix,
    which is authoritative (json re-encoding is not byte-exact)."""
    head = fetch_range(url, 0, HEADER_LEN_PREFIX - 1)
    header_len = struct.unpack("<Q", head)[0]
    if header_len > 128 * 1024 * 1024:
        raise ValueError("header too large (%d bytes) — not a safetensors file?" % header_len)
    raw = fetch_range(url, HEADER_LEN_PREFIX, HEADER_LEN_PREFIX + header_len - 1)
    return json.loads(raw.decode("utf-8")), header_len


def read_header_from_file(path):
    """Read only the header of a local .safetensors file.
    Returns (header_dict, true_header_len)."""
    with open(path, "rb") as f:
        raw_len = f.read(HEADER_LEN_PREFIX)
        if len(raw_len) < HEADER_LEN_PREFIX:
            raise ValueError("file too small to be safetensors: %s" % path)
        header_len = struct.unpack("<Q", raw_len)[0]
        raw = f.read(header_len)
    return json.loads(raw.decode("utf-8")), header_len


def load_header_json(path):
    with open(path, "r", encoding="utf-8") as f:
        header = json.load(f)
    return header, len(json.dumps(header).encode("utf-8"))


def parse_tensors(header):
    """Return ordered list of dicts (key, dtype, shape, start, end, nbytes) and header metadata.

    NOTE: per the safetensors spec, ``data_offsets`` are relative to the start of
    the data section (which begins at 8 + len(header JSON)), not to file offset 0.
    The comfymodal runtime wave builder uses the same convention
    (``_md_data_start_offset = 8 + header_len``, ``_wave_abs = data_start + rel``).
    """
    meta = header.get("__metadata__", {})
    tensors = []
    for key, info in header.items():
        if key == "__metadata__":
            continue
        start, end = info["data_offsets"]
        tensors.append({
            "key": key,
            "dtype": info["dtype"],
            "shape": info["shape"],
            "start": start,   # relative to data section start
            "end": end,
            "nbytes": end - start,
        })
    return tensors, meta


def validate_contiguity(tensors):
    """safetensors data section must be byte-packed, in header order, zero gaps.

    Offsets are data-section-relative: first tensor must start at 0 and every
    subsequent tensor must start exactly where the previous one ended.
    """
    issues = []
    if not tensors:
        return 0, issues
    prev_end = 0
    for t in tensors:
        if t["start"] != prev_end:
            issues.append("gap/overlap at %s: expected start %d, got %d (delta %+d)"
                          % (t["key"], prev_end, t["start"], t["start"] - prev_end))
        prev_end = t["end"]
    return prev_end, issues


def size_class(nbytes):
    if nbytes < 1024:
        return "tiny (<1 KiB)"
    if nbytes < 1024 * 1024:
        return "small (1 KiB-1 MiB)"
    if nbytes < 64 * 1024 * 1024:
        return "medium (1-64 MiB)"
    return "huge (>=64 MiB)"


def layout_stats(tensors, total_bytes, data_start):
    stats = {
        "count": len(tensors),
        "total_bytes": total_bytes,
        "classes": {"tiny (<1 KiB)": 0, "small (1 KiB-1 MiB)": 0,
                    "medium (1-64 MiB)": 0, "huge (>=64 MiB)": 0},
        "class_bytes": {"tiny (<1 KiB)": 0, "small (1 KiB-1 MiB)": 0,
                        "medium (1-64 MiB)": 0, "huge (>=64 MiB)": 0},
        "largest": None,
        "smallest": None,
        "page_unaligned": 0,   # tensors whose absolute data start is not 4096-aligned
        "byte_fraction_in_huge": 0.0,
    }
    for t in tensors:
        cls = size_class(t["nbytes"])
        stats["classes"][cls] += 1
        stats["class_bytes"][cls] += t["nbytes"]
        if (data_start + t["start"]) % 4096 != 0:
            stats["page_unaligned"] += 1
        if stats["largest"] is None or t["nbytes"] > stats["largest"]["nbytes"]:
            stats["largest"] = t
        if stats["smallest"] is None or t["nbytes"] < stats["smallest"]["nbytes"]:
            stats["smallest"] = t
    stats["byte_fraction_in_huge"] = stats["class_bytes"]["huge (>=64 MiB)"] / total_bytes if total_bytes else 0.0
    return stats


def plan_shards(tensors, n, total_bytes):
    """Partition tensors (in header order, whole tensors only) into n shards whose
    cumulative byte size is as close as possible to total_bytes / n.

    Each shard is a CONTIGUOUS byte range of the original data section, so a
    future splitter can copy payload bytes verbatim (byte-identical tensors).
    Cut points are chosen at the cumulative boundary nearest each target
    boundary (k * total / n), guaranteeing >= 1 tensor per shard and a
    monotonically increasing partition.
    """
    cum = []
    acc = 0
    for t in tensors:
        acc += t["nbytes"]
        cum.append(acc)
    cuts = []  # last tensor index of each shard; cuts[-1] = len(tensors)-1 implied
    for k in range(1, n):
        target_k = k * total_bytes / n
        lo = (cuts[-1] + 1) if cuts else 0          # this shard must keep >= 1 tensor
        hi = len(tensors) - (n - k)                 # remaining shards must keep >= 1 each
        best_i, best_d = None, None
        for i in range(lo, hi):
            d = abs(cum[i] - target_k)
            if best_d is None or d < best_d:
                best_i, best_d = i, d
        cuts.append(best_i)
    shards = []
    prev = 0
    for k in range(n):
        end = (cuts[k] + 1) if k < len(cuts) else len(tensors)
        part = tensors[prev:end]
        shards.append({
            "index": k,
            "tensors": part,
            "bytes": sum(t["nbytes"] for t in part),
            "start": part[0]["start"],
            "end": part[-1]["end"],
        })
        prev = end
    return shards


def balance_report(shards):
    sizes = [s["bytes"] for s in shards]
    total = sum(sizes)
    mx, mn = max(sizes), min(sizes)
    return {
        "n_shards": len(shards),
        "sizes": sizes,
        "total": total,
        "target": total / len(shards) if shards else 0,
        "max": mx,
        "min": mn,
        "balance_ratio_max_min": (mx / mn) if mn else float("inf"),
        "max_dev_pct": (mx / (total / len(shards)) - 1.0) * 100 if shards else 0.0,
    }


def build_plan_output(shards, total_bytes, base_name):
    out = {"metadata": {"total_bytes": total_bytes, "base_name": base_name,
                        "packing": "header-order contiguous, whole tensors"}}
    weight_map = {}
    for s in shards:
        fname = "%s-%05d-of-%05d.safetensors" % (base_name, s["index"] + 1, len(shards))
        for t in s["tensors"]:
            weight_map[t["key"]] = {"file": fname, "shard_offset": t["start"] - s["start"],
                                    "nbytes": t["nbytes"], "dtype": t["dtype"],
                                    "shape": t["shape"]}
    out["weight_map"] = weight_map
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True,
                    help="local .safetensors path, local header .json, or https URL (range-fetched)")
    ap.add_argument("--shards", default="2,4,8", help="comma-separated shard counts to plan")
    ap.add_argument("--base-name", default="model", help="shard filename prefix (e.g. 'model')")
    ap.add_argument("--save-plans", help="optional JSON output path for the generated plans")
    args = ap.parse_args()

    src = args.input
    if src.startswith("http://") or src.startswith("https://"):
        header, header_len = fetch_header_from_url(src)
        src_desc = "URL (range-fetch)"
    elif src.endswith(".json"):
        header, header_len = load_header_json(src)
        src_desc = "header JSON"
    else:
        header, header_len = read_header_from_file(src)
        src_desc = "local file (header region only)"

    tensors, meta = parse_tensors(header)
    data_start = HEADER_LEN_PREFIX + header_len   # absolute file offset of data section
    data_end_rel, issues = validate_contiguity(tensors)
    total_bytes = data_end_rel
    stats = layout_stats(tensors, total_bytes, data_start)

    print("=== C12 safetensors layout analysis ===")
    print("source            : %s (%s)" % (src, src_desc))
    print("header metadata   : %s" % (json.dumps(meta) if meta else "(none)"))
    print("header length     : %d bytes (8-byte prefix + JSON)" % (HEADER_LEN_PREFIX + header_len))
    print("tensor count      : %d" % stats["count"])
    print("payload bytes     : %d (%.2f GiB)" % (total_bytes, total_bytes / 2**30))
    print("file size         : %d (header+payload)" % (data_start + total_bytes))
    print("data section      : [%d, %d) absolute file offsets" % (data_start, data_start + data_end_rel))
    print("contiguity        : %s" % ("PACKED, zero gaps" if not issues else "ISSUES: %d" % len(issues)))
    for issue in issues[:10]:
        print("  ! %s" % issue)
    print()
    print("=== size classes ===")
    for cls in ["tiny (<1 KiB)", "small (1 KiB-1 MiB)", "medium (1-64 MiB)", "huge (>=64 MiB)"]:
        print("  %-18s %5d tensors  %12d B (%.1f%%)" % (
            cls, stats["classes"][cls], stats["class_bytes"][cls],
            100.0 * stats["class_bytes"][cls] / total_bytes))
    print()
    print("largest  : %s  %d B  abs@%d" % (stats["largest"]["key"], stats["largest"]["nbytes"],
                                           data_start + stats["largest"]["start"]))
    print("smallest : %s  %d B  abs@%d" % (stats["smallest"]["key"], stats["smallest"]["nbytes"],
                                           data_start + stats["smallest"]["start"]))
    print("page-unaligned tensor starts : %d / %d" % (stats["page_unaligned"], stats["count"]))
    print("bytes in huge (>=64 MiB)     : %.1f%%" % (100.0 * stats["byte_fraction_in_huge"]))
    print()
    print("=== first 25 tensors (physical = header order; ComfyUI reads in this order) ===")
    for t in tensors[:25]:
        print("  %-58s %8d B  abs@%d" % (t["key"], t["nbytes"], data_start + t["start"]))
    print()

    plans = {}
    for n_str in args.shards.split(","):
        n = int(n_str.strip())
        if n < 1:
            continue
        shards = plan_shards(tensors, n, total_bytes)
        bal = balance_report(shards)
        plans[n] = build_plan_output(shards, total_bytes, args.base_name)
        print("=== shard plan: %d shard(s) — header-order contiguous greedy packing ===" % n)
        print("  target/shard   : %.2f GiB" % (bal["target"] / 2**30))
        for i, s in enumerate(shards):
            print("  shard %02d : %5d tensors  %10.2f MiB  data-range [%d, %d)  (%.1f%% of payload)"
                  % (i + 1, len(s["tensors"]), s["bytes"] / 2**20, s["start"], s["end"],
                     100.0 * s["bytes"] / total_bytes))
        print("  balance max/min : %.3f  |  max deviation from target : %+.1f%%"
              % (bal["balance_ratio_max_min"], bal["max_dev_pct"]))
        print("  weight_map      : %d entries -> %s-00001-of-%05d.safetensors ... %s-%05d-of-%05d.safetensors"
              % (len(plans[n]["weight_map"]), args.base_name, n, args.base_name, n, n))
        print()

    if args.save_plans:
        with open(args.save_plans, "w", encoding="utf-8") as f:
            json.dump(plans, f, indent=2)
        print("plans written to %s" % args.save_plans)


if __name__ == "__main__":
    sys.exit(main())
