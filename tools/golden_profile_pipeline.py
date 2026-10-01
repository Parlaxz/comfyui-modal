"""End-to-end profiling pipeline for a Golden full-trace run.

Consolidates what previously only existed as throwaway scripts under
``%TEMP%\\gep_run``. Given a trace id on the profile volume it downloads and
verifies the bundle, runs the exhaustive analysis, and renders the decision
documents.

The bundle SHA is **not** recorded in the v2ctl run manifest
(``provenance.artifact_sha256`` is always ``None``); it only exists in
``artifact.json`` next to the bundle on the volume. That is read here and the
download is refused on mismatch.

Subcommands:
    latest              list recent trace ids with their bundle sha
    fetch <trace_id>    download, verify and extract a bundle
    analyze <session>   parse, analyze and write the exhaustive artifacts
    render <session>    write the stage decision documents
    report <trace_id>   fetch + analyze + render
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import io
import json
import os
import sys
import tarfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

#: Keep in sync with ``PROFILE_VOLUME_NAME`` in comfymodal_runtime/modal_app.py.
#: Duplicated rather than imported because that module is ~24k lines and pulls
#: in Modal, which is not importable in every local context.
DEFAULT_PROFILE_VOLUME = "comfymodal-v2-profiles"

WORKSPACE_REGISTRY = REPO_ROOT / ".git" / "comfymodal" / "modal_workspaces.json"
MODAL_TARGET = REPO_ROOT / "config" / "v2" / "modal_target.toml"
RUNS_ROOT = REPO_ROOT / "artifacts" / "golden_exhaustive_runs"

CANONICAL_STAGE_ORDER = (
    "golden_restore",
    "golden_request_setup",
    "golden_clip_load",
    "golden_clip_forward",
    "golden_unet_load",
    "golden_sampler_prepare",
    "golden_vae_load",
    "golden_sampling",
    "golden_sampler_tail",
    "golden_vae_decode",
    "golden_output",
)

FINAL_REPORT_NAME = "golden_stage_report.md"


def log(message: str) -> None:
    print(f"[golden.profile] {message}", flush=True)


def error(message: str) -> None:
    print(f"[golden.profile] ERROR: {message}", file=sys.stderr, flush=True)


def fail(message: str) -> int:
    error(message)
    return 1


# ── configuration ────────────────────────────────────────────────────────────


def resolve_profile_volume(explicit: str | None) -> str:
    if explicit:
        return explicit
    return os.environ.get("COMFYMODAL_V2_PROFILE_VOLUME") or DEFAULT_PROFILE_VOLUME


def resolve_workspace_id(explicit: str | None) -> str | None:
    """Workspace id from the explicit flag, the env, or the config-owned target."""
    if explicit:
        return explicit
    env = os.environ.get("MODAL_WORKSPACE_ID")
    if env:
        return env
    try:
        import tomllib

        with MODAL_TARGET.open("rb") as handle:
            data = tomllib.load(handle)
    except Exception:
        return None
    node = data
    for key in ("modal", "target", "modal_destination", "destination"):
        if isinstance(node, dict) and key in node:
            node = node[key]
    if isinstance(node, dict):
        for key in ("workspace_id", "workspace"):
            value = node.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def credentials(workspace_id: str) -> tuple[str, str, str]:
    """Resolve Modal credentials for *workspace_id* without printing them."""
    with io.open(WORKSPACE_REGISTRY, encoding="utf-8") as handle:
        data = json.load(handle)
    for entry in data.get("workspaces") or []:
        if entry.get("id") == workspace_id:
            return (
                str(entry.get("token_id") or ""),
                str(entry.get("token_secret") or ""),
                str(entry.get("label") or ""),
            )
    raise SystemExit(
        f"no credentials registered for {workspace_id} in {WORKSPACE_REGISTRY}"
    )


def open_volume(workspace_id: str | None, volume_name: str):
    """Return a Modal volume handle, raising a readable error on failure."""
    if not workspace_id:
        raise SystemExit(
            "no workspace id: pass --workspace-id, set MODAL_WORKSPACE_ID, or add "
            f"workspace_id to {MODAL_TARGET}"
        )
    token_id, token_secret, label = credentials(workspace_id)
    if not token_id or not token_secret:
        raise SystemExit(f"incomplete credentials for {workspace_id}")
    os.environ["MODAL_TOKEN_ID"] = token_id
    os.environ["MODAL_TOKEN_SECRET"] = token_secret
    import modal

    log(f"workspace={workspace_id} ({label}) volume={volume_name}")
    return modal.Volume.from_name(volume_name)


# ── volume inspection ────────────────────────────────────────────────────────


def candidate_dates(days: int) -> list[str]:
    today = datetime.datetime.now(datetime.timezone.utc)
    return [
        (today - datetime.timedelta(days=offset)).strftime("%Y-%m-%d")
        for offset in range(max(1, days))
    ]


def list_traces(volume, days: int = 3) -> list[dict]:
    """Recent trace ids with their bundle sha, newest first."""
    found: list[dict] = []
    for date in candidate_dates(days):
        try:
            entries = list(volume.listdir(f"v2-full-trace/{date}", recursive=False))
        except Exception:
            continue
        for entry in entries:
            path = entry.path.rstrip("/")
            if not path.endswith(tuple("0123456789abcdef")) or len(
                path.rsplit("/", 1)[-1]
            ) != 32:
                continue
            trace_id = path.rsplit("/", 1)[-1]
            sha = None
            try:
                descriptor = json.loads(
                    b"".join(volume.read_file(path + "/artifact.json"))
                )
                sha = descriptor.get("sha256") or descriptor.get("bundle_sha256")
            except Exception:
                sha = None
            found.append({"trace_id": trace_id, "date": date, "sha256": sha})
    return found


def resolve_trace(volume, trace_id: str, days: int = 3) -> dict | None:
    for record in list_traces(volume, days=days):
        if record["trace_id"] == trace_id:
            return record
    return None


def latest_trace(volume, days: int = 3) -> dict | None:
    records = list_traces(volume, days=days)
    if not records:
        return None
    # listdir has no reliable mtime; the date bucket is the only ordering
    # signal, so fall back to the caller choosing explicitly when ambiguous.
    return records[-1]


# ── fetch ────────────────────────────────────────────────────────────────────


def fetch(volume, trace_id: str, record: dict, force: bool = False) -> Path | None:
    """Download, verify and extract a bundle. Returns the session directory.

    Returns ``None`` on any failure so callers can test ``is None``; returning an
    int status here would be truthy and read as success.
    """
    sha = record.get("sha256")
    if not sha:
        error(
            f"no sha256 in artifact.json for {trace_id}; cannot verify the download"
        )
        return None
    remote_dir = f"v2-full-trace/{record['date']}/{trace_id}"
    output = RUNS_ROOT / trace_id / trace_id
    session = output / "session"
    if session.is_dir() and not force:
        log(f"already extracted: {session}")
        return session

    output.mkdir(parents=True, exist_ok=True)
    bundle = output / "bundle.tar.gz"
    digest = hashlib.sha256()
    size = 0
    log(f"downloading {remote_dir}/bundle.tar.gz")
    with bundle.open("wb") as handle:
        for chunk in volume.read_file(remote_dir + "/bundle.tar.gz"):
            handle.write(chunk)
            digest.update(chunk)
            size += len(chunk)
    actual = digest.hexdigest()
    log(f"downloaded bytes={size} sha256={actual}")
    if actual.lower() != str(sha).lower():
        error(
            f"SHA-256 mismatch for {trace_id}: expected {sha}, got {actual}; "
            "refusing to extract"
        )
        return None

    session.mkdir(parents=True, exist_ok=True)
    with tarfile.open(bundle, "r:gz") as archive:
        members = archive.getmembers()
        for member in members:
            candidate = Path(member.name)
            if candidate.is_absolute() or ".." in candidate.parts:
                error(f"refusing unsafe archive member: {member.name}")
                return None
        archive.extractall(session)
    log(f"extracted {len(members)} members -> {session}")
    return session


# ── analyze ──────────────────────────────────────────────────────────────────


def analyze(session_dir: Path) -> int:
    start = time.perf_counter()

    def lap(message: str) -> None:
        log(f"[{time.perf_counter() - start:7.2f}s] {message}")

    from comfymodal_runtime import full_trace_report as ftr
    from comfymodal_runtime import golden_exhaustive_profile as gep

    session = Path(session_dir)
    events, _meta, entry_count, _cap, truncated = ftr._parse_trace_file(session)
    lap(
        f"parsed parent trace: events={len(events)} count={entry_count} "
        f"truncated={truncated}"
    )
    calls = ftr._build_calls(events)
    ftr._reconstruct_parents(calls)
    # _build_calls produces independent rows, so the 1.26M raw event dicts are
    # dead weight from here on. A raw event row is ~1 KB, so holding them for the
    # rest of the run cost roughly a gigabyte of resident memory for nothing.
    events = None
    del events
    lap(f"normalized calls: {len(calls)}")

    config = ftr._parse_trace_config(session)
    sessions = ftr._parse_session_events(session)
    semantic_ops = ftr._build_semantic_ops(calls, sessions, trace_config=config)
    resource_result = ftr._parse_cpu_samples(ftr._parse_resource_samples(session))
    torch_events = ftr._parse_torch_trace(session)
    stack_issues = len(ftr._detect_stack_inconsistencies(calls))
    lap("prepared semantic ops, resource samples, torch trace, stack check")

    print("    [gep.analyze] entering (this takes minutes; heartbeats follow)",
          flush=True)
    profile = gep.analyze(
        session,
        parent_calls=calls,
        trace_config=config,
        semantic_ops=semantic_ops,
        cpu_evidence=dict(resource_result or {}),
        stack_inconsistencies=stack_issues,
        torch_enabled=bool(torch_events),
        c_function_tracing=bool((config.get("config") or {}).get("ignore_c_function")),
        env={},
    )
    lap("analyzed")
    written = gep.write_artifacts(session, profile)
    lap(f"artifacts written: {sorted(written)}")

    print()
    print("=" * 78)
    print(
        "GOLDEN_EXHAUSTIVE_PROFILE_COMPLETE =",
        "YES" if profile.get("complete") else "NO",
    )
    for reason in profile.get("reasons") or []:
        print("   -", reason)
    root = profile.get("root") or {}
    print(
        f"ROOT={root.get('name')} ROOT_WALL_MS={root.get('wall_ms')} "
        f"calls={root.get('call_count')}"
    )
    print("ROOT_COMPLETE =", root.get("complete"))
    manifest = profile.get("process_manifest") or {}
    print(
        "PROCESS_COVERAGE =", manifest.get("process_coverage"),
        "| expected =", manifest.get("expected_processes"),
        "| traced =", manifest.get("traced_processes"),
        "| missing =", manifest.get("missing_processes"),
    )
    clock = profile.get("clock_alignment") or {}
    print("CLOCK_ALIGNMENT =", clock.get("status"), "|", clock.get("reason"))
    threads = profile.get("thread_coverage") or {}
    print(
        "THREAD_COVERAGE =", threads.get("status"),
        "| lanes =", threads.get("lanes_traced") or threads.get("lanes"),
    )
    print("INCOMPLETE_CALLS =", profile.get("incomplete_calls"))
    print()
    print("CANONICAL STAGES:")
    for stage in profile.get("stages") or []:
        bubbles = stage.get("bubbles") or []
        print(
            f"  {stage.get('stage'):<28} {stage.get('wall_ms')} ms  "
            f"bubbles={len(bubbles)}"
        )
    return 0


# ── render ───────────────────────────────────────────────────────────────────


def render(session_dir: Path, min_ms: float = 1.0) -> int:
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    import golden_stage_gantt
    import golden_stage_report
    import golden_stage_tree

    session = Path(session_dir)
    log(f"rendering decision documents from {session}")
    parsers = (
        ("golden_stage_report", golden_stage_report, "stage decision report"),
        ("golden_stage_gantt", golden_stage_gantt, "per-stage gantts"),
        ("golden_stage_tree", golden_stage_tree, "per-stage call trees"),
    )
    for name, module, label in parsers:
        argv = sys.argv
        sys.argv = [name, str(session), "--min-ms", str(min_ms)]
        try:
            rc = module.main()
        except SystemExit as exc:
            rc = exc.code
        finally:
            sys.argv = argv
        if rc not in (0, None):
            return fail(f"{label} generation failed with rc={rc}")

    final = session / "derived" / FINAL_REPORT_NAME
    if not final.is_file():
        return fail(f"expected final report missing: {final}")
    print()
    print("=" * 78)
    print("FINAL REPORT:")
    print(str(final))
    return 0


def find_session(trace_id: str) -> Path | None:
    root = RUNS_ROOT / trace_id
    if not root.is_dir():
        return None
    for candidate in root.rglob("session"):
        if candidate.is_dir():
            return candidate
    return None


# ── cli ──────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="golden_profile_pipeline",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--workspace-id", default=None,
                       help="Modal workspace id (default: env or config target)")
        p.add_argument("--volume", default=None,
                       help=f"profile volume (default: {DEFAULT_PROFILE_VOLUME})")

    p_latest = sub.add_parser(
        "latest", help="list recent trace ids and their bundle sha256")
    common(p_latest)
    p_latest.add_argument("--days", type=int, default=3)

    p_fetch = sub.add_parser(
        "fetch", help="download, verify and extract one bundle")
    p_fetch.add_argument("trace_id")
    p_fetch.add_argument("--days", type=int, default=3)
    p_fetch.add_argument("--force", action="store_true",
                         help="re-extract even if a session dir exists")
    common(p_fetch)

    p_analyze = sub.add_parser(
        "analyze", help="analyze an already extracted session directory")
    p_analyze.add_argument("session_dir", type=Path)

    p_render = sub.add_parser(
        "render", help="write the stage decision documents")
    p_render.add_argument("session_dir", type=Path)
    p_render.add_argument("--min-ms", type=float, default=1.0)

    p_report = sub.add_parser(
        "report", help="fetch, analyze and render in one step")
    p_report.add_argument("trace_id")
    p_report.add_argument("--days", type=int, default=3)
    p_report.add_argument("--force", action="store_true")
    p_report.add_argument("--min-ms", type=float, default=1.0)
    p_report.add_argument("--skip-analyze", action="store_true",
                          help="reuse existing artifacts, only render")
    common(p_report)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "analyze":
        return analyze(args.session_dir)
    if args.command == "render":
        return render(args.session_dir, args.min_ms)

    workspace_id = resolve_workspace_id(args.workspace_id)
    volume_name = resolve_profile_volume(args.volume)
    volume = open_volume(workspace_id, volume_name)

    if args.command == "latest":
        records = list_traces(volume, days=args.days)
        if not records:
            return fail(f"no traces found in the last {args.days} day(s)")
        log(f"{len(records)} trace(s):")
        for record in records:
            log(
                f"  {record['trace_id']}  {record['date']}  "
                f"sha256={str(record['sha256'])[:16]}"
            )
        return 0

    if args.command == "fetch":
        record = resolve_trace(volume, args.trace_id, days=args.days)
        if record is None:
            return fail(f"trace {args.trace_id} not found in the last {args.days} day(s)")
        session = fetch(volume, args.trace_id, record, force=args.force)
        return 0 if session else 1

    if args.command == "report":
        record = resolve_trace(volume, args.trace_id, days=args.days)
        if record is None:
            return fail(f"trace {args.trace_id} not found in the last {args.days} day(s)")
        session = fetch(volume, args.trace_id, record, force=args.force)
        if session is None:
            return 1
        if not args.skip_analyze:
            rc = analyze(session)
            if rc != 0:
                return rc
        return render(session, args.min_ms)

    return fail(f"unknown command {args.command}")


if __name__ == "__main__":
    sys.exit(main())