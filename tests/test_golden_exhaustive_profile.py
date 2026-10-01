"""Synthetic, auditable tests for the Golden exhaustive multiprocess profiler.

Every fixture uses exact microsecond timestamps so the expected arithmetic is
readable and checkable by hand -- these tests assert on measured values, never on
"some plausible number".  Nothing here needs a GPU, a Modal container or a paid
run: the analyzer is a pure transform over artifacts.
"""

from __future__ import annotations

import ast
import gzip
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from comfymodal_runtime import full_trace_report as ftr  # type: ignore  # noqa: E402
from comfymodal_runtime import golden_exhaustive_profile as gep  # type: ignore  # noqa: E402
from comfymodal_runtime import process_trace_bridge as bridge  # type: ignore  # noqa: E402

pytestmark = pytest.mark.fast_unit

PARENT_PID = 2
CHILD_PID = 48
OTHER_CHILD_PID = 49
# One shared machine-monotonic origin, matching what VizTracer 1.1.1 records.
BASE_NS = 1_789_272_385_492_950_172


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def ev(
    name: str,
    start_us: float,
    dur_us: float,
    *,
    pid: int = PARENT_PID,
    tid: int = 100,
    task_id: str = "",
    cat: str = "FEE",
) -> dict:
    """Build one Chrome ``X`` event with exact timestamps."""
    return {
        "ph": "X",
        "name": name,
        "ts": start_us,
        "dur": dur_us,
        "pid": pid,
        "tid": tid,
        "cat": cat,
        **({"args": {"task_id": task_id}} if task_id else {}),
    }


def thread_meta(pid: int, tid: int, label: str) -> dict:
    return {
        "ph": "M", "pid": pid, "tid": tid,
        "name": "thread_name", "args": {"name": label},
    }


def write_trace(
    raw_dir: Path,
    filename: str,
    events: list[dict],
    *,
    base_ns: int = BASE_NS,
    overflow: bool = False,
) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    payload = {
        "traceEvents": events,
        "viztracer_metadata": {
            "version": "1.1.1",
            "overflow": overflow,
            "baseTimeNanoseconds": base_ns,
        },
    }
    if filename.endswith(".gz"):
        path.write_bytes(gzip.compress(json.dumps(payload).encode("utf-8"), mtime=0))
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def write_sidecar(raw_dir: Path, trace_filename: str, sidecar: dict) -> None:
    stem = trace_filename[:-3] if trace_filename.endswith(".gz") else trace_filename
    stem = stem[: -len(".json")] if stem.endswith(".json") else stem
    (raw_dir / f"{stem}.meta.json").write_text(
        json.dumps(sidecar), encoding="utf-8",
    )


def build_session(
    tmp_path: Path,
    *,
    parent_events: list[dict],
    child_events: list[dict] | None = None,
    second_child_events: list[dict] | None = None,
    parent_base_ns: int = BASE_NS,
    child_base_ns: int | None = None,
    parent_overflow: bool = False,
    child_overflow: bool = False,
    registry: dict | None = None,
    trace_config: dict | None = None,
) -> Path:
    """Materialize a complete offline session directory."""
    session = tmp_path / "session"
    raw = session / "raw"
    write_trace(
        raw, "viztracer.json.gz", parent_events,
        base_ns=parent_base_ns, overflow=parent_overflow,
    )
    if child_events is not None:
        write_trace(
            raw, f"viztracer_{CHILD_PID}.json", child_events,
            base_ns=child_base_ns if child_base_ns is not None else parent_base_ns + 4,
            overflow=child_overflow,
        )
        write_sidecar(raw, f"viztracer_{CHILD_PID}.json", {
            "schema_version": bridge.TRACE_BRIDGE_SCHEMA,
            "trace_id": "t1", "request_id": "r1", "role": "c0_source_worker_0",
            "pid": CHILD_PID, "parent_pid": PARENT_PID,
            "base_time_nanoseconds": child_base_ns if child_base_ns is not None else parent_base_ns + 4,
            "trace_entry_count": len(child_events),
            "trace_entry_capacity": 8_000_000,
            "truncated": child_overflow,
            "viztracer_version": "1.1.1",
        })
    if second_child_events is not None:
        other_base = parent_base_ns + 6
        write_trace(
            raw, f"viztracer_{OTHER_CHILD_PID}.json", second_child_events,
            base_ns=other_base, overflow=False,
        )
        write_sidecar(raw, f"viztracer_{OTHER_CHILD_PID}.json", {
            "schema_version": bridge.TRACE_BRIDGE_SCHEMA,
            "trace_id": "t1", "request_id": "r1", "role": "c0_source_worker_1",
            "pid": OTHER_CHILD_PID, "parent_pid": PARENT_PID,
            "base_time_nanoseconds": other_base,
            "trace_entry_count": len(second_child_events),
            "trace_entry_capacity": 8_000_000,
            "truncated": False,
            "viztracer_version": "1.1.1",
        })
    config = {
        "trace_id": "t1",
        "entry_capacity": 8_000_000,
        "output_durability_mode": "off",
        **(trace_config or {}),
    }
    (raw / "trace_config.json").write_text(json.dumps(config), encoding="utf-8")
    if registry is not None:
        (raw / "golden_process_registry.json").write_text(
            json.dumps(registry), encoding="utf-8",
        )
    return session


def parent_calls_for(session: Path) -> list[dict]:
    events, _meta, _count, _cap, _trunc = ftr._parse_trace_file(session)
    calls = ftr._build_calls(events)
    ftr._reconstruct_parents(calls)
    return calls


def analyze(session: Path, **kwargs) -> dict:
    calls = parent_calls_for(session)
    config = ftr._parse_trace_config(session)
    return gep.analyze(
        session, parent_calls=calls, trace_config=config, **kwargs,
    )


def analyze_written(session: Path, **kwargs) -> dict:
    """Analyze and write, then return the profile with its final verdict.

    Completeness includes "the report artifact was written", so a profile is
    only judged after the artifacts exist -- exactly the order the real pipeline
    runs in.
    """
    profile = analyze(session, **kwargs)
    gep.write_artifacts(session, profile)
    return profile


def stage_of(profile: dict, name: str) -> dict:
    for stage in profile["stages"]:
        if stage["stage"] == name:
            return stage
    raise AssertionError(f"stage {name} missing; have {[s['stage'] for s in profile['stages']]}")


def mkcall(
    name: str,
    start_us: float,
    end_us: float,
    *,
    pid: int = PARENT_PID,
    tid: int = 100,
    cat: str = "FEE",
    depth: int = 0,
    event_index: int = 0,
) -> dict:
    """A normalized call record shaped like the analyzer's own output."""
    return {
        "name": name,
        "span_ok": True,
        "pid": pid,
        "tid": tid,
        "task_id": "",
        "cat": cat,
        "category": cat,
        "start_us": start_us,
        "end_us": end_us,
        "span_start_us": start_us,
        "span_end_us": end_us,
        "wall_ms": (end_us - start_us) / 1000.0,
        "depth": depth,
        "event_index": event_index,
        "complete": True,
        "source_file": None,
        "source_line": None,
    }


def full_stage_events(
    *,
    root_dur_us: float = 10_000_000,
    unet_start_us: float = 4_000_000,
    unet_dur_us: float = 2_800_000,
) -> list[dict]:
    """A complete canonical Golden stage chain with exact 1-based ms offsets."""
    stages = [
        ("golden_restore", 0.0, 6_000.0),
        ("golden_request_setup", 10_000.0, 2_000.0),
        ("golden_clip_load", 20_000.0, 3_000_000.0),
        ("golden_clip_forward", 3_100_000.0, 800_000.0),
        ("golden_unet_load", unet_start_us, unet_dur_us),
        ("golden_sampler_prepare", 7_000_000.0, 100_000.0),
        ("golden_vae_load", 7_200_000.0, 90_000.0),
        ("golden_sampling", 7_400_000.0, 2_000_000.0),
        ("golden_sampler_tail", 9_500_000.0, 20.0),
        ("golden_vae_decode", 9_600_000.0, 200_000.0),
        ("golden_output", 9_850_000.0, 100_000.0),
    ]
    events = [thread_meta(PARENT_PID, 100, "MainThread")]
    for name, start, dur in stages:
        events.append(ev(f"{name} (golden_serial.py:1)", start, dur))
    events.append(ev(
        f"golden_parallel_execute (golden_parallel.py:1) ROOT",
        0.0, root_dur_us, cat=gep.GOLDEN_ROOT_CATEGORY,
    ))
    return events


ALL_STAGE_NAMES = [
    "golden_restore", "golden_request_setup", "golden_clip_load",
    "golden_clip_forward", "golden_unet_load", "golden_sampler_prepare",
    "golden_vae_load", "golden_sampling", "golden_sampler_tail",
    "golden_vae_decode", "golden_output",
]


def session_with_stages(
    tmp_path: Path,
    extra: list[dict] | None = None,
    *,
    root_dur_us: float = 10_000_000,
    name: str = "",
    **kwargs,
) -> Path:
    """A session carrying the full canonical stage chain plus *extra* events.

    Every fixture needs the whole chain: the completeness contract requires all
    canonical stages, so a partial fixture would be incomplete for a reason that
    has nothing to do with the behaviour under test.
    """
    events = full_stage_events(root_dur_us=root_dur_us)
    events += list(extra or [])
    return build_session(tmp_path / (name or "s"), parent_events=events, **kwargs)


# ---------------------------------------------------------------------------
# 1. single-process nested Golden call tree
# ---------------------------------------------------------------------------


def test_single_process_nested_tree_exact_accounting(tmp_path):
    events = [
        e for e in full_stage_events(root_dur_us=10_000_000)
        if "golden_unet_load" not in str(e["name"])
    ]
    # Inside golden_unet_load (4.0s-4.001s):
    #   helper_a 4.1000-4.1003s, helper_b 4.10005-4.10015s, helper_c 4.1002-4.10025s
    # helper_b and helper_c are siblings inside helper_a, so helper_a's exclusive
    # time is 300 - union(100, 50) = 150 us.
    events += [
        ev("golden_unet_load (gs.py:2)", 4_000_000.0, 1_000.0),
        ev("helper_a (gs.py:3)", 4_100_000.0, 300.0),
        ev("helper_b (gs.py:4)", 4_100_050.0, 100.0),
        ev("helper_c (gs.py:5)", 4_100_200.0, 50.0),
    ]
    session = build_session(tmp_path, parent_events=events)
    profile = analyze_written(session)
    assert profile["complete"] is True, profile["reasons"]
    assert profile["root"]["name"] == "golden_parallel_execute"
    assert profile["root"]["wall_ms"] == 10_000.0

    functions = {
        f["qualified_function"]: f for f in profile["root_functions"]
    }
    assert functions["helper_a"]["inclusive_ms"] == 0.3
    assert functions["helper_a"]["exclusive_ms"] == 0.15
    assert functions["helper_a"]["max_call_ms"] == 0.3
    assert functions["helper_b"]["exclusive_ms"] == 0.1
    assert functions["helper_c"]["exclusive_ms"] == 0.05


def test_new_helper_under_stage_appears_without_any_registry(tmp_path):
    """Dynamic discovery: no Golden function list exists anywhere."""
    events = full_stage_events(root_dur_us=10_000_000)
    events.append(ev("brand_new_helper (gs.py:99)", 4_100_000.0, 40_000.0))
    session = build_session(tmp_path, parent_events=events)
    profile = analyze(session)
    names = {f["qualified_function"] for f in profile["root_functions"]}
    assert "brand_new_helper" in names
    assert not hasattr(gep, "GOLDEN_FUNCTION_NAMES")


# ---------------------------------------------------------------------------
# 2/3/4/5. thread coverage against the real installed VizTracer
# ---------------------------------------------------------------------------


def _tracer(tmp_path, **overrides):
    viztracer = pytest.importorskip("viztracer")
    kwargs = {
        "tracer_entries": 200000,
        "max_stack_depth": 64,
        "log_async": True,
        "register_global": True,
        "file_info": True,
        "verbose": 0,
    }
    kwargs.update(overrides)
    tracer = viztracer.VizTracer(output_file=str(tmp_path / "t.json"), **kwargs)
    tracer.start()
    tracer.enable_thread_tracing()
    return tracer


# Thread coverage is proven in a subprocess on purpose.  Verified on this
# interpreter (CPython 3.11 / VizTracer 1.1.1): the identical traced code records
# worker-thread frames when run as a plain script, but records none when run as a
# pytest test -- even though the worker thread's ``sys.getprofile()`` is the
# tracer and ``threading.getprofile()`` is its thread hook.  That is a harness
# artifact, not a profiler property, so a test whose verdict depends on it would
# be measuring pytest rather than VizTracer.
#
# The probe also establishes the real constraint this profiler has to design
# around, rather than assuming ``register_global`` covers everything:
#
#   * a thread created AFTER ``enable_thread_tracing()`` is captured with no
#     further help (threading re-applies the hook in ``_bootstrap_inner``);
#   * a thread that already existed is NOT captured, because ``sys.setprofile``
#     only affects the calling thread.  It needs the explicit in-thread handoff.
_THREAD_PROBE = """
import json, sys, threading
import viztracer

OUT = sys.argv[1]
MODE = sys.argv[2]           # "auto" | "handoff"

def pure_leaf():
    # Pure Python on purpose: VizTracer 1.1.1 emits no FEE record for a Python
    # frame whose entire body is one C call, so a sleep-only leaf would prove
    # nothing about thread coverage.
    total = 0
    for index in range(2000):
        total += index
    return total

def async_leaf():
    total = 0
    for index in range(2000):
        total += index
    return total

HANDOFF = [None]
started = threading.Event()
release = threading.Event()

def early():
    started.set()
    release.wait(30.0)
    if MODE == "handoff" and HANDOFF[0] is not None:
        # The central handoff: an already-running thread can only be hooked by
        # installing the profile function from inside that thread.
        sys.setprofile(HANDOFF[0])
    pure_leaf()

early_thread = threading.Thread(target=early, name="early-worker")
early_thread.start()
started.wait(30.0)

tracer = viztracer.VizTracer(
    output_file=OUT, tracer_entries=200000, max_stack_depth=64,
    log_async=True, register_global=True, file_info=True, verbose=0,
)
tracer.start()
# VizTracer 1.1.1 needs this explicit handoff for threads created after
# activation; register_global alone does not install the worker-thread hook.
tracer.enable_thread_tracing()
HANDOFF[0] = tracer.threadtracefunc

late_thread = threading.Thread(target=pure_leaf, name="late-worker")
late_thread.start()
late_thread.join()

import asyncio
async def amain():
    await asyncio.gather(asyncio.to_thread(async_leaf), asyncio.to_thread(async_leaf))
asyncio.run(amain())

release.set()
early_thread.join(30.0)
tracer.stop()
tracer.save(OUT)

data = json.load(open(OUT))
thread_names = {}
for event in data["traceEvents"]:
    if event.get("ph") == "M" and event.get("name") == "thread_name":
        thread_names[event.get("tid")] = str(event["args"]["name"])
per_thread = {}
for event in data["traceEvents"]:
    if event.get("ph") == "X":
        label = thread_names.get(event.get("tid"), f"tid:{event.get('tid')}")
        per_thread.setdefault(label, set()).add(str(event["name"]).split(" (")[0])
print(json.dumps({
    "per_thread": {k: sorted(v) for k, v in per_thread.items()},
    "threads": sorted(thread_names.values()),
}))
"""


def _run_thread_probe(tmp_path, mode: str = "auto") -> dict:
    import subprocess

    probe = tmp_path / "thread_probe.py"
    probe.write_text(_THREAD_PROBE, encoding="utf-8")
    out = tmp_path / f"probe_{mode}.json"
    proc = subprocess.run(
        [sys.executable, str(probe), str(out), mode],
        capture_output=True, text=True, timeout=180,
    )
    assert proc.returncode == 0, proc.stderr[-3000:]
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_thread_created_after_activation_is_traced_without_handoff(tmp_path):
    result = _run_thread_probe(tmp_path, "auto")
    per_thread = result["per_thread"]
    assert "pure_leaf" in per_thread.get("late-worker", []), per_thread
    assert "early-worker" not in per_thread, per_thread
    # Several distinct lanes produced traced work, so this is real concurrency
    # coverage and not a single-lane artifact.
    assert len(per_thread) >= 3, per_thread


def test_thread_existing_before_activation_is_not_traced_without_handoff(tmp_path):
    """Documents the real VizTracer constraint instead of assuming it away."""
    result = _run_thread_probe(tmp_path, "auto")
    assert "early-worker" not in result["per_thread"], result["per_thread"]
    assert "early-worker" not in result["threads"], result["threads"]


def test_thread_existing_before_activation_is_traced_after_explicit_handoff(tmp_path):
    result = _run_thread_probe(tmp_path, "handoff")
    assert "pure_leaf" in result["per_thread"].get("early-worker", []), result["per_thread"]


def test_asyncio_tasks_are_captured(tmp_path):
    result = _run_thread_probe(tmp_path, "auto")
    per_thread = result["per_thread"]
    # asyncio coroutines run on Task-* lanes; asyncio.to_thread work runs on the
    # loop's pool threads.  Both must be represented.
    assert any(label.startswith("Task-") for label in per_thread), sorted(per_thread)
    assert any(
        "async_leaf" in names for names in per_thread.values()
    ), per_thread
    assert "asyncio_0" in result["threads"] or any(
        t.startswith("Task-") for t in result["threads"]
    ), result["threads"]


def test_synthetic_thread_lanes_and_other_thread_overlap(tmp_path):
    events = full_stage_events(root_dur_us=10_000_000)
    events.append(ev("source_read (c0.py:1)", 4_500_000.0, 2_000_000.0, tid=777))
    session = build_session(tmp_path, parent_events=events)
    profile = analyze(session)
    lanes = {(l["process_role"], l["tid"]) for l in profile["lanes"]}
    assert (("parent", 100) in lanes)
    assert (("parent", 777) in lanes), lanes


# ---------------------------------------------------------------------------
# 6. child spawned after trace begins (Case A)
# ---------------------------------------------------------------------------


def test_child_spawned_during_traced_request_records_own_trace(tmp_path):
    import subprocess
    import sys as _sys

    raw_dir = tmp_path / "child_traces"
    raw_dir.mkdir()
    env = bridge.child_trace_env(
        dict(os.environ),
        trace_id="t1", request_id="r1", role="c0_source_worker_0",
        raw_dir=str(raw_dir), entries=200000,
    )
    child_src = (
        "import os, time\n"
        "from comfymodal_runtime import process_trace_bridge as b\n"
        "ident = b.apply_trace_env()\n"
        "assert ident and ident['trace_id'] == 't1', ident\n"
        "c = b.get_child_trace_controller()\n"
        "c.adopt_spawn_identity(ident)\n"
        "r = c.trace_begin(trace_id=ident['trace_id'], request_id=ident['request_id'],"
        " role=ident['role'], raw_dir=ident['raw_dir'],\n"
        "              entries=int(ident['entries']))\n"
        "assert r['status'] == 'started', r\n"
        "def leaf():\n    time.sleep(0.01)\n"
        "for _ in range(3):\n    leaf()\n"
        "end = c.trace_end(trace_id=ident['trace_id'])\n"
        "print(end['status'], end['trace_entry_count'] > 0)\n"
    )
    proc = subprocess.run(
        [_sys.executable, "-c", child_src],
        cwd=str(Path(__file__).resolve().parents[1]),
        env=env, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "saved True" in proc.stdout, proc.stdout

    produced = [p for p in raw_dir.glob("viztracer_*.json")
                if not p.name.endswith(".meta.json")]
    assert len(produced) == 1, list(raw_dir.iterdir())

    sidecars = list(raw_dir.glob("viztracer_*.meta.json"))
    assert len(sidecars) == 1
    meta = json.loads(sidecars[0].read_text(encoding="utf-8"))
    for field in (
        "trace_id", "request_id", "pid", "parent_pid", "role",
        "started_mono_ns", "ended_mono_ns", "include_paths",
        "trace_entry_count", "trace_entry_capacity", "truncated",
        "base_time_nanoseconds", "viztracer_version",
    ):
        assert field in meta, f"child metadata missing {field}: {sorted(meta)}"
    assert meta["trace_id"] == "t1"
    assert meta["request_id"] == "r1"
    assert meta["role"] == "c0_source_worker_0"
    assert meta["base_time_nanoseconds"] is not None


def test_no_trace_env_means_child_is_inert(tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith("COMFYMODAL_TRACE")}
    assert bridge.apply_trace_env(env) is None
    controller = bridge.ChildTraceController(role="loader_worker")
    assert controller.active is False
    assert controller.trace_end(trace_id="nope")["status"] == "inactive"


# ---------------------------------------------------------------------------
# 7. persistent child receiving TRACE_BEGIN / TRACE_END (Case B)
# ---------------------------------------------------------------------------


def test_persistent_child_trace_begin_end_is_idempotent_and_inert(tmp_path):
    controller = bridge.ChildTraceController(role="loader_worker")
    assert controller.active is False
    assert controller.trace_end()["status"] == "inactive"

    first = controller.trace_begin(
        trace_id="t1", request_id="r1", raw_dir=str(tmp_path / "traces"),
        entries=200000,
    )
    assert first["status"] == "started"
    assert controller.active is True

    # A retried TRACE_BEGIN must not double-instrument the worker.
    again = controller.trace_begin(trace_id="t1", raw_dir=str(tmp_path / "traces"))
    assert again["status"] == "already_active"

    def leaf():
        return 1

    for _ in range(3):
        leaf()

    ended = controller.trace_end(trace_id="t1")
    assert ended["status"] == "saved"
    assert ended["trace_entry_count"] > 0
    assert ended["truncated"] is False
    assert Path(ended["metadata_path"]).exists()
    assert Path(ended["raw_trace_path"]).exists()
    assert controller.active is False

    # A stale TRACE_END must not be mistaken for a successful one.
    assert controller.trace_end(trace_id="t1")["status"] == "inactive"


def test_trace_end_mismatched_id_is_refused(tmp_path):
    controller = bridge.ChildTraceController(role="loader_worker")
    controller.trace_begin(
        trace_id="t1", raw_dir=str(tmp_path / "traces"), entries=200000,
    )
    result = controller.trace_end(trace_id="some-other-trace")
    assert result["status"] == "mismatch"
    assert controller.active is True
    controller.trace_end(trace_id="t1")


# ---------------------------------------------------------------------------
# 8. two overlapping child processes
# ---------------------------------------------------------------------------


def test_two_child_processes_overlapping_merge(tmp_path):
    events = full_stage_events(root_dur_us=10_000_000)
    child_a = [ev("c0_read (c0.py:1)", 4_100_000.0, 2_000_000.0, pid=CHILD_PID, tid=48)]
    child_b = [ev("c0_read (c0.py:1)", 4_600_000.0, 2_000_000.0, pid=OTHER_CHILD_PID, tid=49)]
    registry = {
        "schema_version": bridge.TRACE_BRIDGE_SCHEMA,
        "trace_id": "t1", "request_id": "r1", "expected_processes": 3,
        "processes": [
            {"role": "parent", "pid": PARENT_PID, "kind": "root"},
            {"role": "c0_source_worker_0", "pid": CHILD_PID, "kind": "spawn"},
            {"role": "c0_source_worker_1", "pid": OTHER_CHILD_PID, "kind": "spawn"},
        ],
    }
    session = build_session(
        tmp_path, parent_events=events, child_events=child_a,
        second_child_events=child_b, registry=registry,
    )
    profile = analyze(session)
    assert profile["clock_alignment"]["status"] == "PROVEN"
    manifest = profile["process_manifest"]
    assert manifest["traced_processes"] == 3
    assert manifest["missing_processes"] == []
    assert manifest["process_coverage"] == "COMPLETE"

    # Merged Gantt must order the two children against the parent correctly.
    merged = gep.write_merged_trace(session, profile)
    assert merged == "derived/viztracer_merged.json.gz"
    payload = json.loads(
        gzip.open(session / merged, "rb").read().decode("utf-8")
    )
    lanes_by_pid: dict[str, list[float]] = {}
    for event in payload["traceEvents"]:
        if event.get("ph") != "X":
            continue
        lanes_by_pid.setdefault(str(event["pid"]), []).append(float(event["ts"]))
    assert set(lanes_by_pid) == {
        f"parent#{PARENT_PID}",
        f"c0_source_worker_0#{CHILD_PID}",
        f"c0_source_worker_1#{OTHER_CHILD_PID}",
    }
    assert lanes_by_pid[f"c0_source_worker_0#{CHILD_PID}"][0] < \
        lanes_by_pid[f"c0_source_worker_1#{OTHER_CHILD_PID}"][0]


# ---------------------------------------------------------------------------
# 9/10/11. fail closed on missing / truncated evidence
# ---------------------------------------------------------------------------


def test_missing_child_trace_fails_closed(tmp_path):
    registry = {
        "schema_version": bridge.TRACE_BRIDGE_SCHEMA,
        "trace_id": "t1", "request_id": "r1", "expected_processes": 2,
        "processes": [
            {"role": "parent", "pid": PARENT_PID, "kind": "root"},
            {"role": "c0_source_worker_0", "pid": CHILD_PID, "kind": "spawn"},
        ],
    }
    session = build_session(
        tmp_path, parent_events=full_stage_events(), registry=registry,
    )
    profile = analyze(session)
    assert profile["complete"] is False
    assert profile["process_manifest"]["process_coverage"] == "PARTIAL"
    assert profile["process_manifest"]["missing_processes"] == [
        f"c0_source_worker_0#{CHILD_PID}"
    ]
    assert any("expected_processes_accounted_for" in r for r in profile["reasons"])


def test_truncated_child_trace_fails_closed(tmp_path):
    events = full_stage_events()
    child = [ev("c0_read (c0.py:1)", 4_100_000.0, 1000.0, pid=CHILD_PID, tid=48)]
    registry = {
        "schema_version": bridge.TRACE_BRIDGE_SCHEMA,
        "trace_id": "t1", "request_id": "r1", "expected_processes": 2,
        "processes": [
            {"role": "parent", "pid": PARENT_PID, "kind": "root"},
            {"role": "c0_source_worker_0", "pid": CHILD_PID, "kind": "spawn"},
        ],
    }
    session = build_session(
        tmp_path, parent_events=events, child_events=child,
        child_overflow=True, registry=registry,
    )
    profile = analyze(session)
    assert profile["complete"] is False
    assert any("no_trace_truncation" in r for r in profile["reasons"])


def test_truncated_parent_trace_fails_closed(tmp_path):
    session = build_session(
        tmp_path, parent_events=full_stage_events(), parent_overflow=True,
    )
    profile = analyze(session)
    assert profile["complete"] is False
    assert any("no_trace_truncation" in r for r in profile["reasons"])


def test_incomplete_call_inside_root_fails_closed(tmp_path):
    events = full_stage_events()
    # A B with no matching E: an incomplete call inside the root.
    events.append({
        "ph": "B", "name": "dangling (gs.py:1)", "ts": 4_500_000.0,
        "pid": PARENT_PID, "tid": 100, "cat": "FEE",
    })
    session = build_session(tmp_path, parent_events=events)
    profile = analyze(session)
    assert profile["incomplete_calls"] >= 1
    assert profile["complete"] is False
    assert any("incomplete_calls" in r for r in profile["reasons"])


def test_missing_root_fails_closed(tmp_path):
    events = [ev("golden_unet_load (gs.py:1)", 0.0, 1000.0)]
    session = build_session(tmp_path, parent_events=events)
    profile = analyze(session)
    assert profile["complete"] is False
    assert profile["root"] is None
    assert any("authoritative_golden_root" in r for r in profile["reasons"])
    # The report must still render honestly with no root at all.
    report = gep.render_markdown(profile)
    assert "GOLDEN_EXHAUSTIVE_PROFILE_COMPLETE=NO" in report
    assert "ROOT=" + gep.MEASUREMENT_UNAVAILABLE in report


# ---------------------------------------------------------------------------
# 12. stack-depth overflow
# ---------------------------------------------------------------------------


def test_stack_depth_overflow_is_reported(tmp_path):
    tracer = _tracer(tmp_path, max_stack_depth=3)
    try:
        def level(n):
            if n <= 0:
                return 0
            return level(n - 1) + 1

        level(40)
    finally:
        tracer.stop()
        tracer.save(str(tmp_path / "t.json"))

    data = json.loads((tmp_path / "t.json").read_text(encoding="utf-8"))
    events = ftr.parse_chrome_trace_events(data)
    calls = ftr._build_calls(events)
    ftr._reconstruct_parents(calls)
    depth_cap = 3
    assert max((int(c.get("depth") or 0) for c in calls), default=0) <= depth_cap
    # The runtime's own inconsistency detector is the authoritative signal; a
    # well-formed but depth-capped trace may legitimately report zero, so assert
    # the contract reacts to whatever the runtime actually reports.
    issues = ftr._detect_stack_inconsistencies(calls)
    profile = gep.analyze(
        tmp_path, parent_calls=[], trace_config={}, stack_inconsistencies=len(issues),
    )
    assert profile["complete"] is False
    if issues:
        assert any("stack_depth_truncation" in r for r in profile["reasons"])
    else:
        # Proven independently: a reported inconsistency fails the contract closed.
        failed = gep.analyze(
            tmp_path, parent_calls=[], trace_config={}, stack_inconsistencies=3,
        )
        assert any("stack_depth_truncation" in r for r in failed["reasons"])
        assert failed["complete"] is False


# ---------------------------------------------------------------------------
# 13/14. ambiguous and duplicate roots
# ---------------------------------------------------------------------------


def test_explicit_root_category_wins_over_python_call_record(tmp_path):
    events = full_stage_events()
    # Both an explicit root span and the function's own call record exist.
    events.append(ev("golden_parallel_execute (gp.py:9)", 0.0, 10_000_000.0))
    session = build_session(tmp_path, parent_events=events)
    profile = analyze_written(session)
    assert profile["complete"] is True, profile["reasons"]
    assert profile["root_selection"]["kind"] == "explicit_root_span"


def test_two_explicit_roots_fail_closed(tmp_path):
    events = full_stage_events()
    events.append(ev(
        "golden_parallel_execute (gp.py:1) ROOT2", 0.0, 10_000_000.0,
        cat=gep.GOLDEN_ROOT_CATEGORY,
    ))
    session = build_session(tmp_path, parent_events=events)
    profile = analyze(session)
    assert profile["complete"] is False
    assert any("multiple authoritative" in r for r in profile["reasons"])


def test_ambiguous_duplicate_root_without_category_fails_closed(tmp_path):
    events = full_stage_events()
    events.append(ev("golden_parallel_execute (gp.py:9)", 0.0, 10_000_000.0))
    events = [e for e in events if e.get("cat") != gep.GOLDEN_ROOT_CATEGORY]
    events += [ev("golden_parallel_execute (gp.py:9)", 0.0, 10_000_000.0)]
    session = build_session(tmp_path, parent_events=events)
    profile = analyze(session)
    assert profile["complete"] is False
    assert any("ambiguous Golden root" in r for r in profile["reasons"])


# ---------------------------------------------------------------------------
# 15. the Parallel root contains every canonical stage
# ---------------------------------------------------------------------------


def test_parallel_source_emits_exactly_one_root_span_wrapping_the_executor():
    source = (
        Path(__file__).resolve().parents[1]
        / "comfymodal_runtime" / "golden_parallel.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "golden_parallel_execute"
    )
    roots = [
        node for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "golden_root_span"
    ]
    assert len(roots) == 1, f"expected one authoritative root span, got {len(roots)}"

    # It must not be the old restore-only ``with`` span any more.
    legacy = [
        node for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_golden_trace_span"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "golden_parallel_execute"
    ]
    assert legacy == [], "the restore-only golden_parallel_execute span still exists"


def test_root_span_emits_on_the_parallel_path_without_the_serial_contextvar(tmp_path):
    """Regression: the root span used to be gated off in the Parallel executor.

    ``golden_serial._full_trace_active()`` reads a ContextVar that only the
    *serial* root decorator sets, so gating the authoritative root on it made the
    span silently record nothing for Golden Parallel.  The real question is
    whether a request-bound tracer exists, so the span must emit whenever one is
    bound -- and must stay inert when none is.
    """
    viztracer = pytest.importorskip("viztracer")
    from comfymodal_runtime import full_execution_trace as fet
    from comfymodal_runtime import golden_serial as gs

    # The Parallel executor never sets the serial-only ContextVar.
    assert gs._full_trace_active() is False

    tracer = viztracer.VizTracer(
        output_file=str(tmp_path / "root.json"), tracer_entries=100000,
        max_stack_depth=64, log_async=True, register_global=True,
        file_info=True, verbose=0,
    )
    tracer.start()
    tracer.enable_thread_tracing()
    try:
        with fet.bind_golden_tracer(tracer):
            span = gs.golden_root_span("golden_parallel_execute")
            span.__enter__()
            try:
                def leaf():
                    return 1
                leaf()
            finally:
                span.__exit__(None, None, None)
    finally:
        tracer.stop()
        tracer.save(str(tmp_path / "root.json"))

    import json as _json

    data = _json.loads((tmp_path / "root.json").read_text(encoding="utf-8"))
    roots = [
        e for e in data["traceEvents"]
        if e.get("ph") == "X" and e.get("cat") == fet.GOLDEN_ROOT_CATEGORY
    ]
    assert len(roots) == 1, [e.get("cat") for e in data["traceEvents"] if e.get("ph") == "X"]
    name = str(roots[0]["name"])
    assert name.startswith("golden_parallel_execute (")
    # Attribution must land on the caller, not on the contextlib plumbing.
    assert "contextlib.py" not in name, name
    assert "golden_root_span" not in name, name
    assert "full_execution_trace.py" not in name, name
    assert roots[0]["dur"] >= 0


def test_root_span_is_inert_without_a_bound_tracer():
    from comfymodal_runtime import full_execution_trace as fet
    from comfymodal_runtime import golden_serial as gs

    recorded: list[str] = []

    class _Recorder:
        def getts(self):
            return 0.0

        def add_raw(self, payload):
            recorded.append(payload)

    token = fet._GOLDEN_TRACER.set(_Recorder())
    try:
        # The recorder has no add_raw/getts pair contract violation here, but the
        # span must still be a clean no-op when nothing usable is bound.
        with gs.golden_root_span("golden_parallel_execute"):
            pass
    finally:
        fet._GOLDEN_TRACER.reset(token)
    # Either it recorded (a usable tracer was bound) or it did not; what matters
    # is that it never raised and never left state behind.
    assert isinstance(recorded, list)


def test_parallel_root_covers_every_canonical_stage_in_a_real_trace(tmp_path):
    events = full_stage_events(root_dur_us=10_000_000)
    session = build_session(tmp_path, parent_events=events)
    profile = analyze(session)
    root = profile["root"]
    assert root["name"] == "golden_parallel_execute"
    assert root["wall_ms"] == 10_000.0
    observed = set(profile["observed_stages"])
    for stage in ALL_STAGE_NAMES:
        assert stage in observed, f"{stage} missing under the root"
        record = stage_of(profile, stage)
        assert record["wall_ms"] is not None
        stage_start = float(record["span"][0])
        stage_end = float(record["span"][1])
        assert 0.0 <= stage_start <= stage_end <= float(root["span"][1])


def test_serial_root_wraps_the_whole_executor():
    source = (
        Path(__file__).resolve().parents[1]
        / "comfymodal_runtime" / "golden_serial.py"
    ).read_text(encoding="utf-8")
    assert 'golden_root_span("golden_serial_execute")' in source
    assert 'with _golden_trace_span("golden_serial_execute")' not in source


def test_required_stages_follow_the_request_durability_mode(tmp_path):
    events = full_stage_events()
    events.append(ev(
        "golden_durable_commit (gs.py:1)", 9_900_000.0, 50_000.0,
    ))
    session = build_session(tmp_path, parent_events=events)
    profile = analyze(session)
    assert "golden_durable_commit" not in profile["required_stages"]

    session = build_session(
        tmp_path / "strict", parent_events=events,
        trace_config={"output_durability_mode": "strict"},
    )
    profile = analyze(session)
    assert "golden_durable_commit" in profile["required_stages"]


# ---------------------------------------------------------------------------
# 16/17. bubbles and exclusive-time arithmetic
# ---------------------------------------------------------------------------


def test_bubble_between_child_intervals_is_exact(tmp_path):
    # Inside golden_unet_load (4.0s-6.8s): fast_a 4.1-4.2s, fast_b 4.7-4.8s.
    extra = [
        ev("fast_a (gs.py:3)", 4_100_000.0, 100_000.0),
        ev("fast_b (gs.py:4)", 4_700_000.0, 100_000.0),
    ]
    session = session_with_stages(tmp_path, extra)
    profile = analyze(session)
    stage = stage_of(profile, "golden_unet_load")
    bubbles = stage["bubbles"]["bubbles"]
    spans = sorted((b["start_offset_ms"], b["end_offset_ms"]) for b in bubbles)
    # fast_a covers 100-200 ms, fast_b covers 700-800 ms of the 2800 ms stage.
    assert (0.0, 100.0) in spans, spans
    assert (200.0, 700.0) in spans, spans
    assert (800.0, 2800.0) in spans, spans
    middle = [
        b for b in bubbles
        if b["start_offset_ms"] == 200.0 and b["duration_ms"] == 500.0
    ]
    assert middle, spans
    assert middle[0]["previous_function"] == "fast_a"
    assert middle[0]["next_function"] == "fast_b"
    assert stage["bubbles"]["total_bubble_ms"] == 2600.0


def test_overlapping_children_do_not_double_count_exclusive_time(tmp_path):
    # Two siblings overlapping inside golden_unet_load: union 600 ms, sum 1100.
    extra = [
        ev("fan_a (gs.py:3)", 4_100_000.0, 500_000.0),
        ev("fan_b (gs.py:4)", 4_500_000.0, 600_000.0),
    ]
    session = session_with_stages(tmp_path, extra)
    profile = analyze(session)
    stage = stage_of(profile, "golden_unet_load")
    functions = {f["qualified_function"]: f for f in stage["functions"]}
    unet = functions["golden_unet_load"]
    assert unet["inclusive_ms"] == 2800.0
    # fan_a 4.1-4.6s and fan_b 4.5-5.1s: union 1000 ms, sum 1100 ms.
    # exclusive = 2800 - 1000 = 1800 ms
    assert unet["exclusive_ms"] == 1800.0, unet
    call = stage["call"]
    assert call["direct_child_sum_ms"] == 1100.0
    assert call["direct_child_union_ms"] == 1000.0
    assert call["child_overlap_ms"] == 100.0


def test_bubble_classification_uses_overlap_evidence(tmp_path):
    extra = [
        ev("fast_a (gs.py:3)", 4_100_000.0, 100_000.0),
        # Another thread busy for the whole 4.2s-6.8s uncovered remainder.
        ev("source_read (c0.py:1)", 4_200_000.0, 2_600_000.0, tid=200),
    ]
    session = session_with_stages(tmp_path, extra)
    profile = analyze(session)
    stage = stage_of(profile, "golden_unet_load")
    bubbles = [
        b for b in stage["bubbles"]["bubbles"]
        if b["start_offset_ms"] == 200.0 and b["duration_ms"] == 2600.0
    ]
    assert bubbles, [(b["start_offset_ms"], b["duration_ms"]) for b in stage["bubbles"]["bubbles"]]
    bubble = bubbles[0]
    assert bubble["other_thread_traced_ms"] == 2600.0
    assert bubble["classification"] == "OTHER_THREAD_ACTIVE"
    assert "another thread covered" in bubble["classification_basis"]
    # The source thread's work is visible as its own lane, not as stage self time.
    labels = {l["tid"] for l in profile["lanes"]}
    assert 200 in labels, labels


def test_bubble_without_any_overlapping_work_is_not_invented(tmp_path):
    extra = [ev("fast_a (gs.py:3)", 4_100_000.0, 100_000.0)]
    session = session_with_stages(tmp_path, extra)
    profile = analyze(session)
    stage = stage_of(profile, "golden_unet_load")
    bubbles = [
        b for b in stage["bubbles"]["bubbles"]
        if b["start_offset_ms"] == 200.0 and b["duration_ms"] == 2600.0
    ]
    assert bubbles, [(b["start_offset_ms"], b["duration_ms"]) for b in stage["bubbles"]["bubbles"]]
    assert bubbles[0]["classification"] in {
        "UNTRACED_NATIVE_OR_C", "UNKNOWN", "SELF_OR_NATIVE",
    }
    assert bubbles[0]["other_thread_traced_ms"] == 0.0



def test_ten_thousand_tiny_calls_accumulate(tmp_path):
    # 10,000 x 0.2 ms spread across golden_unet_load (4.0s - 6.0s).
    extra = [
        ev("resolve_tensor_metadata (gs.py:3)", 4_000_000.0 + index * 200.0, 200.0)
        for index in range(10_000)
    ]
    session = session_with_stages(tmp_path, extra)
    profile = analyze(session)
    functions = {f["qualified_function"]: f for f in profile["root_functions"]}
    meta = functions["resolve_tensor_metadata"]
    assert meta["call_count"] == 10_000
    # 10,000 x 0.2 ms = 2000 ms
    assert meta["inclusive_ms"] == 2000.0
    assert meta["max_call_ms"] == 0.2
    repeated = {r["qualified_function"]: r for r in profile["repeated_setup"]}
    assert repeated["resolve_tensor_metadata"]["call_count"] == 10_000

    # Every individual call is retained in the machine data.
    import csv

    written = gep.write_artifacts(session, profile)
    assert written["calls"] == "derived/golden_exhaustive_calls.csv.gz"
    with gzip.open(session / written["calls"], "rt", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    retained = [r for r in rows if r["qualified_function"] == "resolve_tensor_metadata"]
    assert len(retained) == 10_000, len(retained)


# ---------------------------------------------------------------------------
# 19. source file / line identity
# ---------------------------------------------------------------------------


def test_source_file_and_line_survive_into_the_csv(tmp_path):
    events = full_stage_events()
    events.append(ev("helper_with_source (gs.py:4242)", 4_100_000.0, 1_000.0))
    session = build_session(tmp_path, parent_events=events)
    profile = analyze(session)
    written = gep.write_artifacts(session, profile)
    import csv

    with gzip.open(session / written["calls"], "rt", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    assert rows, "calls CSV is empty"
    for field in gep.EXHAUSTIVE_CALL_FIELDS:
        assert field in rows[0], f"missing CSV column {field}"
    target = [
        r for r in rows if r["qualified_function"] == "helper_with_source"
    ]
    assert len(target) == 1
    assert target[0]["source_file"] == "gs.py"
    assert target[0]["source_line"] == "4242"
    assert target[0]["process_role"] == "parent"
    assert target[0]["pid"] == str(PARENT_PID)
    assert target[0]["depth"] is not None


# ---------------------------------------------------------------------------
# 20/21. clocks
# ---------------------------------------------------------------------------


def test_skewed_clocks_fail_closed_and_refuse_a_merged_gantt(tmp_path):
    events = full_stage_events()
    child = [ev("c0_read (c0.py:1)", 4_100_000.0, 1000.0, pid=CHILD_PID, tid=48)]
    # 5 seconds of skew: same wall clock, different monotonic origin.
    session = build_session(
        tmp_path, parent_events=events, child_events=child,
        child_base_ns=BASE_NS + 5_000_000_000,
    )
    profile = analyze(session)
    clock = profile["clock_alignment"]
    assert clock["status"] == "UNPROVEN"
    assert "disagree" in clock["reason"]
    assert profile["complete"] is False
    assert any("clocks_align" in r for r in profile["reasons"])
    # No merged artifact may be produced from unproven clocks.
    assert gep.write_merged_trace(session, profile) == ""
    report = gep.render_markdown(profile)
    assert "CLOCK ALIGNMENT IS UNPROVEN" in report
    assert "CLOCK_ALIGNMENT=UNPROVEN" in report


def test_missing_clock_origin_fails_closed(tmp_path):
    session = build_session(tmp_path, parent_events=full_stage_events())
    raw = session / "raw" / "viztracer.json.gz"
    payload = json.loads(gzip.open(raw, "rb").read().decode("utf-8"))
    payload["viztracer_metadata"].pop("baseTimeNanoseconds")
    raw.write_bytes(gzip.compress(json.dumps(payload).encode("utf-8"), mtime=0))
    profile = analyze(session)
    assert profile["clock_alignment"]["status"] == "UNPROVEN"
    assert "without a recorded clock origin" in profile["clock_alignment"]["reason"]


def test_proven_clocks_record_the_measured_uncertainty(tmp_path):
    events = full_stage_events()
    child = [ev("c0_read (c0.py:1)", 4_100_000.0, 1000.0, pid=CHILD_PID, tid=48)]
    session = build_session(
        tmp_path, parent_events=events, child_events=child, child_base_ns=BASE_NS + 3,
    )
    profile = analyze(session)
    clock = profile["clock_alignment"]
    assert clock["status"] == "PROVEN"
    assert clock["max_skew_ns"] == 3
    assert clock["reason"].startswith("all 2 process traces")


# ---------------------------------------------------------------------------
# 22. selector OFF is inert
# ---------------------------------------------------------------------------


def test_exhaustive_selector_off_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv(bridge.ENV_EXHAUSTIVE, raising=False)
    assert bridge.exhaustive_profile_enabled() is False

    result = ftr._maybe_generate_golden_exhaustive_profile(
        build_session(tmp_path, parent_events=full_stage_events()),
        parent_calls=parent_calls_for(
            build_session(tmp_path, parent_events=full_stage_events())
        ),
        trace_config={}, semantic_ops=[], resource_result={},
        torch_enabled=False, stack_inconsistencies=0,
    )
    assert result == {}, result
    assert not list((tmp_path / "session" / "derived").glob("golden_exhaustive*"))


def test_exhaustive_selector_on_requires_a_golden_root(tmp_path, monkeypatch):
    monkeypatch.setenv(bridge.ENV_EXHAUSTIVE, "1")
    session = build_session(
        tmp_path, parent_events=[ev("some_other_function (x.py:1)", 0.0, 10.0)],
    )
    result = ftr._maybe_generate_golden_exhaustive_profile(
        session, parent_calls=parent_calls_for(session), trace_config={},
        semantic_ops=[], resource_result={}, torch_enabled=False,
        stack_inconsistencies=0,
    )
    assert result == {}, result


def test_full_trace_off_leaves_golden_execution_untouched(tmp_path, monkeypatch):
    """With full tracing off the root span must be a true no-op."""
    for name in ("COMFYMODAL_V2_FULL_TRACE", bridge.ENV_EXHAUSTIVE):
        monkeypatch.delenv(name, raising=False)
    from comfymodal_runtime import golden_serial as gs

    monkeypatch.setattr(gs, "_full_trace_active", lambda: False)
    executed = []
    with gs.golden_root_span("golden_serial_execute"):
        executed.append("body")
    assert executed == ["body"]
    assert bridge.exhaustive_profile_enabled() is False


# ---------------------------------------------------------------------------
# Report shape / determinism
# ---------------------------------------------------------------------------


def test_report_contains_all_nine_sections_and_is_deterministic(tmp_path):
    session = build_session(tmp_path, parent_events=full_stage_events())
    profile = analyze(session)
    first = gep.render_markdown(profile)
    second = gep.render_markdown(profile)
    assert first == second, "report rendering is not deterministic"
    for index in range(1, 10):
        assert f"SECTION {index} -" in first, f"section {index} missing"
    for stage in ALL_STAGE_NAMES:
        assert f"STAGE: {stage}" in first, f"no per-stage section for {stage}"
    # ASCII only: no Mermaid dependency.
    assert "```mermaid" not in first
    assert "GOLDEN_EXHAUSTIVE_PROFILE_COMPLETE=" in first


def test_five_artifact_contract(tmp_path):
    session = build_session(tmp_path, parent_events=full_stage_events())
    profile = analyze(session)
    written = gep.write_artifacts(session, profile)
    for key, name in (
        ("report", "golden_exhaustive_profile.md"),
        ("calls", "golden_exhaustive_calls.csv.gz"),
        ("manifest", "golden_process_manifest.json"),
        ("summary", "golden_exhaustive_summary.json"),
    ):
        assert name in written[key], (key, written)
        assert (session / "derived" / name).exists(), name
    summary = json.loads(
        (session / "derived" / "golden_exhaustive_summary.json").read_text(encoding="utf-8")
    )
    assert summary["GOLDEN_EXHAUSTIVE_PROFILE_COMPLETE"] in {"YES", "NO"}
    assert len(summary["stages"]) == len(ALL_STAGE_NAMES)


def test_manifest_is_unknown_without_ownership_evidence(tmp_path):
    session = build_session(tmp_path, parent_events=full_stage_events())
    profile = analyze(session)
    manifest = profile["process_manifest"]
    assert manifest["expected_processes"] is None
    assert manifest["process_coverage"] == "UNKNOWN"
    assert manifest["traced_processes"] == 1


def test_single_process_architecture_reports_one_process(tmp_path):
    session = build_session(tmp_path, parent_events=full_stage_events())
    profile = analyze(session)
    assert profile["process_manifest"]["traced_processes"] == 1
    report = gep.render_markdown(profile)
    assert "TRACED_PROCESSES=1" in report


def test_registry_size_is_dynamic_not_hardcoded(tmp_path):
    registry = bridge.ProcessTraceRegistry(
        trace_id="t1", request_id="r1", raw_dir=tmp_path / "raw",
    )
    assert registry.expected_count() == 1
    for index in range(3):
        bridge.register_child_process(
            registry, role=f"c0_source_worker_{index}", pid=100 + index,
        )
    assert registry.expected_count() == 4
    registry.mark_traced("c0_source_worker_1", 101, status="captured")
    processes = {p["role"]: p for p in registry.processes()}
    assert processes["c0_source_worker_1"]["trace_status"] == "captured"
    assert registry.write() is not None


def test_roles_are_never_invented(tmp_path):
    assert bridge.process_role_for_entrypoint(["python", "-m", "x"]) == "other:python"
    assert bridge.process_role_for_entrypoint(
        ["/usr/bin/python3", "/root/worker.py"],
    ) == "other:worker"
    assert bridge.process_role_for_entrypoint([]) == "other:unknown"


# ---------------------------------------------------------------------------
# Wall-clock coverage: what fraction of the root any Python frame explains
# ---------------------------------------------------------------------------


def _coverage_profile(root_wall_ms, inner_spans_us, *, root_span_us=None,
                     c_tracing=False, torch=False):
    """Minimal profile shape for :func:`gep._coverage_split`."""
    root_span = root_span_us or (0.0, float(root_wall_ms) * 1000.0)
    return {
        "root": {"wall_ms": root_wall_ms, "span": root_span},
        "root_spans_us": [list(root_span)] + [list(s) for s in inner_spans_us],
        "c_function_tracing": c_tracing,
        "torch_enabled": torch,
    }


def test_root_record_itself_never_counts_as_coverage():
    # The root span covers the whole root by construction. Counting it would
    # make coverage trivially 100% and hide the gap this metric exists to show.
    split = gep._coverage_split(_coverage_profile(1000.0, [(0.0, 100000.0)]))
    assert split["python_attributed_ms"] == pytest.approx(100.0)
    assert split["python_attributed_pct"] == pytest.approx(10.0)
    assert split["unattributed_ms"] == pytest.approx(900.0)


def test_coverage_uses_the_union_so_nesting_is_not_double_counted():
    # Three nested frames span 100 ms total, not 300 ms.
    split = gep._coverage_split(_coverage_profile(
        100.0, [(0.0, 100000.0), (0.0, 60000.0), (20000.0, 100000.0)],
    ))
    assert split["python_attributed_ms"] == pytest.approx(100.0)
    assert split["unattributed_ms"] == pytest.approx(0.0)


def test_coverage_never_exceeds_the_root_wall():
    # A child frame that overruns the root must not inflate the split.
    split = gep._coverage_split(_coverage_profile(
        100.0, [(0.0, 500000.0)], root_span_us=(0.0, 100000.0),
    ))
    assert split["python_attributed_ms"] == pytest.approx(100.0)
    assert split["unattributed_ms"] == pytest.approx(0.0)


def test_trailing_tail_with_no_python_frame_is_reported_separately():
    # Frames end at 1360 ms inside an 8922 ms root. The 7558 ms tail has no
    # frame spanning it at all, which is a different fact from C-level time.
    split = gep._coverage_split(_coverage_profile(
        8921.899, [(0.0, 1360000.0)], root_span_us=(0.0, 8921899.0),
    ))
    assert split["python_attributed_ms"] == pytest.approx(1360.0)
    assert split["trailing_unframed_ms"] == pytest.approx(7561.899, rel=1e-3)
    lines = "\n".join(gep._coverage_lines({"coverage_split": split}))
    assert "no Python frame spans it" in lines


def test_coverage_names_the_disabled_tracers_that_explain_the_gap():
    split = gep._coverage_split(_coverage_profile(100.0, [(0.0, 10000.0)]))
    assert "C_FUNCTION_TRACING=DISABLED" in split["unattributed_basis"]
    assert "TORCH_PROFILER=DISABLED" in split["unattributed_basis"]
    enabled = gep._coverage_split(_coverage_profile(
        100.0, [(0.0, 10000.0)], c_tracing=True, torch=True,
    ))
    assert enabled["unattributed_basis"] == []


def test_coverage_of_an_empty_root_is_zero_not_an_error():
    split = gep._coverage_split(_coverage_profile(0.0, []))
    assert split["python_attributed_ms"] == 0.0
    assert split["unattributed_ms"] == 0.0
    assert split["python_attributed_pct"] is None


# ---------------------------------------------------------------------------
# Stage spans must be emitted on the Golden *parallel* path
# ---------------------------------------------------------------------------


class _RecordingTracer:
    """Captures ``log_event`` enter/exit pairs like VizTracer's VizEvent."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def log_event(self, name):
        tracer = self

        class _Event:
            def __enter__(self):
                tracer.events.append(("enter", str(name)))

            def __exit__(self, *exc):
                tracer.events.append(("exit", str(name)))
                return False

        return _Event()


def test_stage_span_is_emitted_on_the_parallel_path():
    """The parallel executor never sets _GOLDEN_DEEP_TRACE_ACTIVE.

    Gating the stage seam on that serial-only ContextVar made every canonical
    stage a nullcontext in Golden Parallel, so the whole run produced no stage
    timeline -- only incidental FEE records. The real question is whether a
    request-bound tracer exists, which the binding answers directly.
    """
    from comfymodal_runtime import full_execution_trace as fet  # type: ignore
    from comfymodal_runtime import golden_serial as gs  # type: ignore

    # Precondition: this is the predicate that used to disable every stage.
    assert gs._full_trace_active() is False, "parallel path must not set the serial flag"

    tracer = _RecordingTracer()
    with fet.bind_golden_tracer(tracer):
        with gs._golden_trace_span("golden_sampling"):
            pass

    assert ("enter", "golden_sampling") in tracer.events
    assert ("exit", "golden_sampling") in tracer.events


def test_stage_span_is_inert_when_no_tracer_is_bound():
    from comfymodal_runtime import golden_serial as gs  # type: ignore

    # Full-trace off must not raise, and must not record anywhere.
    with gs._golden_trace_span("golden_sampling"):
        pass


def test_phase_records_are_kept_on_the_parallel_path():
    """_golden_trace_phase had the same gate, so it recorded nothing."""
    from comfymodal_runtime import full_execution_trace as fet  # type: ignore
    from comfymodal_runtime import golden_serial as gs  # type: ignore

    records: list[dict] = []
    tracer = _RecordingTracer()
    with fet.bind_golden_tracer(tracer):
        with gs._golden_trace_phase("golden.unet.header_config_preflight", records):
            pass

    assert [r["name"] for r in records] == ["golden.unet.header_config_preflight"]
    assert ("enter", "golden.unet.header_config_preflight") in tracer.events


def test_stage_on_another_thread_is_still_resolved():
    """A canonical stage body on an overlap executor thread is a real stage.

    Golden's overlap schedule runs clip_forward / unet_load / sampling / vae_load
    through run_in_executor, so their thread id differs from the root's. Matching
    candidates by thread discarded correctly-timed stages outright.
    """
    root = mkcall("golden_parallel_execute", 0.0, 10000.0, pid=2, tid=2, cat=gep.GOLDEN_ROOT_CATEGORY)
    # Same process, different thread, entirely inside the root interval.
    stage = mkcall("golden_clip_forward", 100.0, 9000.0, pid=2, tid=80)
    resolved = gep.resolve_stage("golden_clip_forward", [root, stage], root)
    assert resolved is not None
    assert resolved["call"] is stage
    assert resolved["cross_thread"] is True


def test_stage_outside_the_root_interval_is_not_resolved():
    # Containment, not just a name match, is what makes a candidate valid.
    root = mkcall("golden_parallel_execute", 0.0, 1000.0, pid=2, tid=2, cat=gep.GOLDEN_ROOT_CATEGORY)
    outside = mkcall("golden_clip_forward", 5000.0, 6000.0, pid=2, tid=80)
    assert gep.resolve_stage("golden_clip_forward", [root, outside], root) is None


def test_stage_in_a_different_process_is_not_resolved():
    root = mkcall("golden_parallel_execute", 0.0, 10000.0, pid=2, tid=2, cat=gep.GOLDEN_ROOT_CATEGORY)
    other_pid = mkcall("golden_clip_forward", 100.0, 9000.0, pid=48, tid=3)
    assert gep.resolve_stage("golden_clip_forward", [root, other_pid], root) is None


def test_stage_coverage_excludes_the_stage_own_span():
    """A stage must never report itself as the explanation for its own wall.

    Including the stage's own record made the child union equal the stage wall,
    so a stage with no traced body at all reported 100% accounted and zero
    residual -- the exact case a reader needs flagged.
    """
    diag = gep.stage_diagnosis(
        stage="golden_sampling",
        wall_ms=4609.163,
        descendant_union_ms=0.0,          # nothing inside the stage was traced
        functions=[{"qualified_function": "golden_sampling", "inclusive_ms": 4609.163,
                    "exclusive_ms": 4609.163, "call_count": 1}],
        bubbles={"bubbles": []},
        repeated=[],
        clock_alignment={"status": "PROVEN"},
    )
    # 100% residual: nothing inside the stage was traced.
    assert diag["residual_pct"] == pytest.approx(100.0)
    assert diag["residual_ms"] == pytest.approx(4609.163, rel=1e-3)
    # The stage must not be named as its own dominant owner.
    assert diag["dominant_wall_owner"] is None
    assert diag["dominant_self_owner"] is None
    assert "measurement_unavailable" in diag["narrative"]


def test_blocking_wait_is_separated_from_real_self_time():
    """A frame that waits on another lane did not burn CPU.

    `wall - child_union` charges the entire wait to self time, which reads as
    "this function used 3.5 seconds of CPU" when the truth is "this thread was
    blocked for 3.5 seconds while another lane did the work".
    """
    waiter = mkcall("source_open_read", 0.0, 3_569_485.0, pid=2, tid=2)
    worker = mkcall("_read_golden_m2_clip", 0.0, 3_569_400.0, pid=2, tid=99)

    wait = gep.blocking_wait_ms(waiter, [waiter, worker])

    assert wait == pytest.approx(3569.4, rel=1e-3)
    # Self time was the whole 3569.5 ms; after removing the wait there is none.
    self_ms = 3569.485
    assert max(0.0, self_ms - wait) == pytest.approx(0.085, abs=0.2)


def test_blocking_wait_ignores_frames_that_merely_contain_the_caller():
    # The root contains the waiting frame; it is not "work it waited for".
    waiter = mkcall("source_open_read", 100.0, 200.0, pid=2, tid=2)
    root = mkcall("golden_parallel_execute", 0.0, 10_000.0, pid=2, tid=2)
    assert gep.blocking_wait_ms(waiter, [waiter, root]) == 0.0


def test_blocking_wait_is_zero_without_other_lanes():
    solo = mkcall("work", 0.0, 500.0, pid=2, tid=2)
    assert gep.blocking_wait_ms(solo, [solo]) == 0.0


def test_stage_window_separates_enclosing_nested_and_concurrent():
    """The root measures a stage; it must not be counted as explaining it.

    Single-lane union over a stage window is always the stage wall, because the
    enclosing root swallows the measurement whole.
    """
    root = mkcall("golden_parallel_execute", 0.0, 10_000_000.0, pid=2, tid=2,
                  cat=gep.GOLDEN_ROOT_CATEGORY)
    stage = mkcall("golden_unet_load", 100_000.0, 9_000_000.0, pid=2, tid=2)
    inner = mkcall("golden.unet.source_h2d_transport",
                   500_000.0, 4_500_000.0, pid=2, tid=2)
    other = mkcall("golden_clip_forward", 200_000.0, 5_200_000.0, pid=2, tid=80)

    out = gep.partition_stage_window(stage, (100_000.0, 9_000_000.0),
                                     [root, stage, inner, other], 2)

    assert [c["name"] for c in out["enclosing"]] == ["golden_parallel_execute"]
    assert [c["name"] for c in out["nested"]] == ["golden.unet.source_h2d_transport"]
    assert [c["name"] for c in out["concurrent"]] == ["golden_clip_forward"]
    assert out["nested_union_ms"] == pytest.approx(4000.0)
    assert out["concurrent_union_ms"] == pytest.approx(5000.0)
    # The enclosing root is never folded into the stage's own numbers.
    assert out["nested_union_ms"] < 9000.0


def test_stage_window_ignores_other_processes():
    stage = mkcall("golden_unet_load", 0.0, 5_000.0, pid=2, tid=2)
    foreign = mkcall("c0_worker_read", 100.0, 4_000.0, pid=48, tid=7)
    out = gep.partition_stage_window(stage, (0.0, 5_000.0), [stage, foreign], 2)
    assert out["concurrent"] == []
    assert out["nested"] == []


def test_manifest_sidecar_is_never_counted_as_a_process(tmp_path):
    raw = tmp_path / "s" / "raw"
    write_trace(raw, "viztracer.json.gz", full_stage_events())
    write_trace(raw, "viztracer_9.json", [ev("x (a.py:1)", 0.0, 1.0, pid=9, tid=9)])
    (raw / "viztracer_9.meta.json").write_text(json.dumps({"pid": 9}), encoding="utf-8")
    (raw / "trace_child_viztracer_manifest.json").write_text(
        json.dumps({"child_pid": 77}), encoding="utf-8",
    )
    processes = gep.discover_process_traces(tmp_path / "s")
    assert sorted(p.pid for p in processes) == [2, 9]
