"""O6 EXTENSION task #7: mechanical AST-hash extension for comfymodal_runtime + BOM-fixed comfyapp.py.

READ-ONLY on the repo (git show/log/ls-tree + file reads). Writes ONLY to
C:\\Users\\parla\\AppData\\Local\\Temp\\opencode\\PhaseO\\O6\\ (new files; existing outputs untouched).

Outputs:
  O6_HISTORICAL_FUNCTION_HASHES_RUNTIME.csv
  O6_PARSE_FAILURES_RUNTIME.csv
  O6_WORKTREE_NOW_FUNCTION_HASHES.csv
  O6_FUNCTION_HASH_CHRONOLOGY_RUNTIME.md
"""

import ast
import csv
import hashlib
import os
import re
import subprocess
import sys
import textwrap
from datetime import datetime, timezone

REPO_W1 = r"C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal"
REPO_W2 = r"C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal-r42"
OUT_DIR = r"C:\Users\parla\AppData\Local\Temp\opencode\PhaseO\O6"

COMMITS = [
    "a2286dd", "ca1f114", "04142c7", "3200faf", "77544c9", "00c76a6",
    "59e88a8", "92b81e7", "c5a6ee1", "f669bc9", "b2ecfe7", "2df772a",
    "e5483d5", "eea1b3c", "6a84c16", "a6a755e", "0ba7000", "79cc994",
    "8e49d75", "36b895d", "0c59f46", "9f58629", "2187c5e", "4575c7e",
    "442f18d", "9a428fd", "6040c45",
]

WATCHLIST_RE = re.compile(
    r"restore|snapshot|quiesc|\bqd\b|qdr|fast_?safe|fastsafe|clip|unet|h2d|dispatch|"
    r"teardown|garbage|\bgc\b|pre_?copy|precop|hydrate|hydrat|bind|loader|load_|warmup|"
    r"encode|seed|publish|evict|cast|prep|waterfall|conditioning|commit_|_commit\b",
    re.IGNORECASE,
)

CHRONO_RE = re.compile(
    r"restore|snapshot|qd|fastsafe|teardown|garbage|pre_?copy|h2d|dispatch|hydrate|warmup",
    re.IGNORECASE,
)

HEADER = [
    "qualname", "file", "commit", "commit_date", "subject",
    "n_lines", "body_sha_raw_full", "body_sha_ast_full", "first_source_line",
]


def git(args, cwd=REPO_W1):
    res = subprocess.run(
        ["git"] + args, cwd=cwd, capture_output=True
    )
    if res.returncode != 0:
        raise RuntimeError(
            "git failed: %s\nstderr: %s" % (" ".join(args), res.stderr.decode("utf-8", "replace"))
        )
    return res.stdout


def git_text(args, cwd=REPO_W1):
    return git(args, cwd=cwd).decode("utf-8", "replace")


def decode_source(raw):
    # utf-8-sig semantics: strips leading UTF-8 BOM (U+FEFF) if present.
    return raw.decode("utf-8-sig")


def extract_functions(text):
    """Return list of (qualname, node, dedented_segment, n_lines, first_line_trim120)."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        raise
    lines = text.splitlines()
    out = []

    def handle(node, qual_prefix):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qual = (qual_prefix + node.name) if qual_prefix else node.name
            seg = "\n".join(lines[node.lineno - 1: node.end_lineno])
            seg_dedented = textwrap.dedent(seg)
            end = node.end_lineno if node.end_lineno is not None else node.lineno
            n_lines = end - node.lineno + 1
            first = (lines[node.lineno - 1].strip())[:120]
            out.append((qual, node, seg_dedented, n_lines, first))
        # do NOT recurse into nested defs here (module-level + one-class-deep only)

    for child in tree.body:
        handle(child, "")
        if isinstance(child, ast.ClassDef):
            for sub in child.body:
                handle(sub, child.name + ".")
    return out


def sha256_hex(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def matches_watchlist(qualname):
    return bool(WATCHLIST_RE.search(qualname))


def main():
    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR, exist_ok=True)

    hist_rows = []       # PART1 rows (dict)
    failures = []        # (commit, file, error)

    # ---- commit metadata cache ----
    meta = {}
    for sha in COMMITS:
        out = git_text(["show", "-s", "--date=iso", "--format=%ad%x1f%s", sha]).strip()
        ad, subj = out.split("\x1f", 1)
        meta[sha] = (ad.strip(), subj.strip())

    def sort_key(ad_str):
        try:
            return datetime.strptime(ad_str, "%Y-%m-%d %H:%M:%S %z")
        except ValueError:
            return datetime(1970, 1, 1, tzinfo=timezone.utc)

    # ---- PART 1a: historical sweep of comfymodal_runtime/*.py ----
    # Union file list across commits
    union_files = set()
    per_commit_files = {}
    for sha in COMMITS:
        listing = git_text(["ls-tree", "-r", "--name-only", sha]).splitlines()
        files = sorted(p for p in listing if p.startswith("comfymodal_runtime/") and p.endswith(".py"))
        per_commit_files[sha] = files
        union_files.update(files)

    print("union comfymodal_runtime files: %d" % len(union_files))

    for sha in COMMITS:
        ad, subj = meta[sha]
        for path in per_commit_files[sha]:
            raw = git(["show", "%s:%s" % (sha, path)])
            try:
                text = decode_source(raw)
                funcs = extract_functions(text)
            except (SyntaxError, ValueError, UnicodeDecodeError) as e:
                failures.append((sha, path, "%s: %s" % (type(e).__name__, e)))
                continue
            fname = path.split("/", 1)[1]
            for qual, node, seg, n_lines, first in funcs:
                if not matches_watchlist(qual):
                    continue
                hist_rows.append({
                    "qualname": qual,
                    "file": fname,
                    "commit": sha,
                    "commit_date": ad,
                    "subject": subj,
                    "n_lines": n_lines,
                    "body_sha_raw_full": sha256_hex(seg),
                    "body_sha_ast_full": sha256_hex(ast.dump(node)),
                    "first_source_line": first,
                    "_sort": (sort_key(ad), sha),
                    "_part": 1,
                })

    # ---- PART 1b: re-do previously-failing comfyapp.py commits (BOM-stripped) ----
    comfyapp_ok = 0
    comfyapp_fail = 0
    for sha in COMMITS:
        ad, subj = meta[sha]
        raw = git(["show", "%s:%s" % (sha, "comfyapp.py")])
        try:
            text = decode_source(raw)
            funcs = extract_functions(text)
        except (SyntaxError, ValueError, UnicodeDecodeError) as e:
            failures.append((sha, "comfyapp.py", "%s: %s" % (type(e).__name__, e)))
            comfyapp_fail += 1
            continue
        comfyapp_ok += 1
        for qual, node, seg, n_lines, first in funcs:
            if not matches_watchlist(qual):
                continue
            hist_rows.append({
                "qualname": qual,
                "file": "comfyapp.py",
                "commit": sha,
                "commit_date": ad,
                "subject": subj,
                "n_lines": n_lines,
                "body_sha_raw_full": sha256_hex(seg),
                "body_sha_ast_full": sha256_hex(ast.dump(node)),
                "first_source_line": first,
                "_sort": (sort_key(ad), sha),
                "_part": 1,
            })

    hist_rows.sort(key=lambda r: r["_sort"])

    hist_csv = os.path.join(OUT_DIR, "O6_HISTORICAL_FUNCTION_HASHES_RUNTIME.csv")
    with open(hist_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HEADER, lineterminator="\n")
        w.writeheader()
        for r in hist_rows:
            w.writerow({k: r[k] for k in HEADER})

    fail_csv = os.path.join(OUT_DIR, "O6_PARSE_FAILURES_RUNTIME.csv")
    with open(fail_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["commit", "file", "error"])
        for row in failures:
            w.writerow(row)

    print("PART1 rows: %d ; failures: %d ; comfyapp ok=%d fail=%d"
          % (len(hist_rows), len(failures), comfyapp_ok, comfyapp_fail))

    # ---- PART 2: WORKTREE-NOW ----
    now_rows = []

    def scan_worktree(root_dir, label, rel_names):
        for rel in rel_names:
            fp = os.path.join(root_dir, rel)
            if not os.path.isfile(fp):
                print("MISSING worktree file (%s): %s" % (label, fp))
                continue
            st = os.stat(fp)
            mtime_iso = datetime.fromtimestamp(st.st_mtime).isoformat()
            with open(fp, "rb") as fh:
                raw = fh.read()
            try:
                text = decode_source(raw)
                funcs = extract_functions(text)
            except (SyntaxError, ValueError, UnicodeDecodeError) as e:
                failures.append((label, rel, "%s: %s" % (type(e).__name__, e)))
                continue
            for qual, node, seg, n_lines, first in funcs:
                if not matches_watchlist(qual):
                    continue
                now_rows.append({
                    "qualname": qual,
                    "file": rel.replace("\\", "/"),
                    "commit": label,
                    "commit_date": mtime_iso,
                    "subject": "current disk state",
                    "n_lines": n_lines,
                    "body_sha_raw_full": sha256_hex(seg),
                    "body_sha_ast_full": sha256_hex(ast.dump(node)),
                    "first_source_line": first,
                    "_label": label,
                })

    w1_rt = os.path.join(REPO_W1, "comfymodal_runtime")
    w1_files = sorted(n for n in os.listdir(w1_rt) if n.endswith(".py"))
    scan_worktree(w1_rt, "WORKTREE_NOW_W1", w1_files)

    W2_EXTRAS = [
        "early_model_prep.py",
        "clip_forward_exec_state.py",
        "modal_app.py",
        "model_preload.py",
        "request_clip_fastsafe.py",
        "request_unet_fastsafe.py",
        "request_fastpath.py",
        "snapshot_capture_hygiene.py",
        "clip_conditioning_cache.py",
    ]
    scan_worktree(os.path.join(REPO_W2, "comfymodal_runtime"), "WORKTREE_NOW_W2", W2_EXTRAS)

    now_csv = os.path.join(OUT_DIR, "O6_WORKTREE_NOW_FUNCTION_HASHES.csv")
    with open(now_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HEADER, lineterminator="\n")
        w.writeheader()
        for r in now_rows:
            w.writerow({k: r[k] for k in HEADER})

    print("PART2 rows: %d (W1=%d W2=%d)" % (
        len(now_rows),
        sum(1 for r in now_rows if r["_label"] == "WORKTREE_NOW_W1"),
        sum(1 for r in now_rows if r["commit"] == "WORKTREE_NOW_W2"),
    ))

    # ---- PART 3: chronology markdown ----
    md_path = os.path.join(OUT_DIR, "O6_FUNCTION_HASH_CHRONOLOGY_RUNTIME.md")
    groups = {}
    for r in hist_rows:
        if CHRONO_RE.search(r["qualname"]):
            groups.setdefault(r["qualname"], []).append(r)
    for r in now_rows:
        if CHRONO_RE.search(r["qualname"]):
            groups.setdefault(r["qualname"], []).append(r)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# O6 FUNCTION HASH CHRONOLOGY (runtime extension)\n\n")
        f.write("PART1 = historical (comfymodal_runtime/* + BOM-fixed comfyapp.py); "
                "PART2 = WORKTREE_NOW_W1 / WORKTREE_NOW_W2 appended at end.\n\n")
        for qual in sorted(groups):
            rows = groups[qual]
            f.write("## %s\n\n" % qual)
            f.write("| date | commit | file | n_lines | body_sha_raw[0:16] | body_sha_ast[0:16] | subject |\n")
            f.write("|---|---|---|---|---|---|---|\n")
            for r in rows:
                f.write("| %s | %s | %s | %s | %s | %s | %s |\n" % (
                    r["commit_date"], r["commit"], r["file"], r["n_lines"],
                    r["body_sha_raw_full"][:16], r["body_sha_ast_full"][:16],
                    str(r["subject"]).replace("|", "\\|"),
                ))
            f.write("\n")

        f.write("## DISTINCT BODY VERSION COUNTS (runtime)\n\n")
        # distinct raw-hash counts over ALL watchlist quals (PART1+PART2)
        all_groups = {}
        for r in hist_rows:
            all_groups.setdefault(r["qualname"], {}).setdefault(r["body_sha_raw_full"], [])
        for r in now_rows:
            d = all_groups.setdefault(r["qualname"], {})
            key = r["body_sha_raw_full"]
            tags = d.setdefault(key, [])
            tag = "[NOW-W1]" if r["_label"] == "WORKTREE_NOW_W1" else "[NOW-W2]"
            if tag not in d[key]:
                d[key].append(tag)
        for qual in sorted(all_groups):
            cnt = len(all_groups[qual])
            extra = []
            for tags in all_groups[qual].values():
                extra.extend(tags)
            marks = " (%s)" % ",".join(extra) if extra else ""
            f.write("- %s: %d%s\n" % (qual, cnt, marks))

    print("chronology written: %s" % md_path)


if __name__ == "__main__":
    sys.exit(main())
