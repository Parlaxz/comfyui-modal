#!/usr/bin/env python
"""Coordinate the remaining Phase-2 source-only observations.

This is intentionally only a coordinator.  It does not deploy an app or
implement another runner: each child imports and calls the existing
``run_exp04_source_ceiling._run_campaign`` once, with its shard's two block
sizes.  The four children overlap, while the existing runner remains serial
inside each child.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import importlib.util
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, NamedTuple, Sequence


_ROOT = Path(__file__).resolve().parents[1]
_RUNNER_PATH = Path(__file__).with_name("run_exp04_source_ceiling.py")
_DEFAULT_STATE = _ROOT / "unetClipExperimentsSeptember" / "source_h2d_decoupling_campaign_state.json"
_DEFAULT_OUTPUT = _ROOT / "unetClipExperimentsSeptember" / "06_source_only_runs"
_ROLES = ("clip", "unet")
_BLOCKS = (32, 64, 128, 256)
_QDS = (1, 2, 4, 8)
_MODELS = {"clip": "qwen_3_4b.safetensors", "unet": "z_image_turbo_bf16.safetensors"}
_INTERRUPTION_REASON = "interrupted_by_exp06_parallel_coordinator"

# These are the deployed identities already recorded by the Phase-2 campaign.
# They are defaults only; production code never derives an app name here.
DEFAULT_APPS = (
    "sept-unetclip-04-source-ceiling-batch1",
    "sept-unetclip-04-source-ceiling-batch2",
    "sept-unetclip-04-source-ceiling-batch3",
    "sept-unetclip-04-source-ceiling-oracle",
)


class Shard(NamedTuple):
    key: str
    role: str
    blocks: tuple[int, int]
    default_app: str


SHARDS = (
    Shard("clip_32_64", "clip", (32, 64), DEFAULT_APPS[0]),
    Shard("clip_128_256", "clip", (128, 256), DEFAULT_APPS[1]),
    Shard("unet_32_64", "unet", (32, 64), DEFAULT_APPS[2]),
    Shard("unet_128_256", "unet", (128, 256), DEFAULT_APPS[3]),
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _runner_module() -> Any:
    """Load the existing runner without importing it at coordinator startup."""
    spec = importlib.util.spec_from_file_location("exp06_existing_runner", _RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load existing runner: {_RUNNER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _atomic_write_json(path: Path, value: Any) -> None:
    """Write a complete, fsynced document before replacing the destination."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        # POSIX permits fsyncing the directory entry.  Windows/OneDrive does
        # not, so the file fsync above is the strongest portable guarantee.
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except (OSError, AttributeError):
            pass
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def campaign_cells() -> list[dict[str, Any]]:
    """Return the stable 32-cell configuration list in campaign order."""
    cells: list[dict[str, Any]] = []
    index = 0
    for block in _BLOCKS:
        for qd in _QDS:
            for role in _ROLES:
                index += 1
                cells.append(
                    {
                        "campaign_index": index,
                        "cell_id": f"{role}_b{block}_qd{qd}",
                        "role": role,
                        "model": _MODELS[role],
                        "qd": qd,
                        "block_mib": block,
                        "block_bytes": block * 1024 * 1024,
                        "status": "PENDING",
                        "attempts": [],
                    }
                )
    return cells


def partition_cells(cells: Iterable[Mapping[str, Any]] | None = None) -> dict[str, list[dict[str, Any]]]:
    """Partition the 32 cells into four disjoint, deterministic eight-cell shards."""
    source = [dict(item) for item in (cells if cells is not None else campaign_cells())]
    result: dict[str, list[dict[str, Any]]] = {shard.key: [] for shard in SHARDS}
    for cell in source:
        matches = [
            shard
            for shard in SHARDS
            if cell.get("role") == shard.role and int(cell.get("block_mib", -1)) in shard.blocks
        ]
        if len(matches) != 1:
            raise ValueError(f"cell does not belong to exactly one Phase-2 shard: {cell.get('cell_id')}")
        result[matches[0].key].append(cell)
    for key in result:
        result[key].sort(key=lambda item: int(item.get("campaign_index", 0)))
        if len(result[key]) != 8:
            raise ValueError(f"{key} contains {len(result[key])} cells; expected 8")
    flattened = [cell["cell_id"] for cells_for_shard in result.values() for cell in cells_for_shard]
    if len(flattened) != len(set(flattened)) or len(flattened) != 32:
        raise ValueError("Phase-2 shard partition is not a disjoint 32-cell cover")
    return result


def _cell_key(cell: Mapping[str, Any]) -> tuple[str, int, int]:
    return str(cell.get("role", "")).lower(), int(cell.get("block_mib", -1)), int(cell.get("qd", -1))


def _attempt_signature(attempt: Mapping[str, Any]) -> str:
    return json.dumps(dict(attempt), sort_keys=True, separators=(",", ":"), default=str)


def reconcile_running_attempts(
    ledger: dict[str, Any], reason: str = _INTERRUPTION_REASON
) -> int:
    """Recover valid artifacts, otherwise close stale RUNNING records."""
    changed = 0
    validator: Any | None = None
    for cell in ledger.get("cells", []):
        for attempt in cell.get("attempts", []):
            if attempt.get("status") != "RUNNING":
                continue
            # The child writes the artifact before it changes the ledger record
            # to COMPLETE.  If the coordinator dies in that small window, the
            # artifact is recoverable evidence rather than an interrupted run.
            artifact = attempt.get("artifact")
            attempt_id = attempt.get("attempt_id")
            if artifact and attempt_id:
                if validator is None:
                    validator = _runner_module()
                try:
                    recovered = _artifact_is_eligible(validator, str(artifact), str(attempt_id))
                except Exception:
                    recovered = False
                if recovered:
                    attempt.update({"status": "COMPLETE", "error": None})
                    attempt.pop("interruption_reason", None)
                    attempt.setdefault("finished_at", _now())
                    changed += 1
                    continue
            attempt.update(
                {
                    "status": "FAILED",
                    "error": reason,
                    "interruption_reason": reason,
                    "finished_at": _now(),
                }
            )
            changed += 1
    return changed


def _merge_ledger_attempts(canonical: dict[str, Any], incoming: Mapping[str, Any]) -> int:
    """Union attempts while coalescing lifecycle updates for one artifact."""
    by_id = {cell.get("cell_id"): cell for cell in canonical.get("cells", [])}
    added = 0
    for incoming_cell in incoming.get("cells", []):
        cell_id = incoming_cell.get("cell_id")
        if cell_id not in by_id:
            new_cell = copy.deepcopy(dict(incoming_cell))
            new_cell.setdefault("attempts", [])
            canonical.setdefault("cells", []).append(new_cell)
            by_id[cell_id] = new_cell
        target = by_id[cell_id]
        attempts = target.setdefault("attempts", [])
        by_identity: dict[tuple[str, ...], dict[str, Any]] = {}
        unique_attempts: list[dict[str, Any]] = []
        for existing in attempts:
            identity = _attempt_identity(existing)
            prior = by_identity.get(identity)
            if prior is None:
                unique_attempts.append(existing)
                by_identity[identity] = existing
            elif _attempt_status_rank(existing) >= _attempt_status_rank(prior):
                prior.clear()
                prior.update(existing)
        attempts[:] = unique_attempts
        for attempt in incoming_cell.get("attempts", []):
            identity = _attempt_identity(attempt)
            existing = by_identity.get(identity)
            if existing is not None:
                # A shard's terminal write is newer than the canonical
                # pre-shard RUNNING write.  Do not retain both as evidence for
                # the same artifact, and never let a stale RUNNING copy
                # downgrade a terminal record.
                if _attempt_status_rank(attempt) >= _attempt_status_rank(existing):
                    existing.clear()
                    existing.update(copy.deepcopy(dict(attempt)))
                continue
            attempts.append(copy.deepcopy(dict(attempt)))
            by_identity[identity] = attempts[-1]
            added += 1
    return added


def _attempt_identity(attempt: Mapping[str, Any]) -> tuple[str, ...]:
    """Identify one attempt across ledger lifecycle updates and merges."""
    attempt_id = attempt.get("attempt_id")
    artifact = attempt.get("artifact")
    if attempt_id is not None and artifact is not None:
        return ("attempt", str(attempt_id), str(artifact))
    if attempt_id is not None:
        return ("attempt_id", str(attempt_id))
    if artifact is not None:
        return ("artifact", str(artifact))
    return ("record", _attempt_signature(attempt))


def _attempt_status_rank(attempt: Mapping[str, Any]) -> int:
    return {"RUNNING": 0, "FAILED": 1, "INVALID": 1, "COMPLETE": 2}.get(
        str(attempt.get("status")), -1
    )


def merge_ledger_attempts(
    canonical_document: dict[str, Any], shard_documents: Iterable[Mapping[str, Any]]
) -> dict[str, Any]:
    """Merge shard ledgers into a copy of the canonical document."""
    result = copy.deepcopy(canonical_document)
    ledger = result.setdefault("ledger", {})
    reconcile_running_attempts(ledger, _INTERRUPTION_REASON)
    for document in shard_documents:
        incoming = document.get("ledger") if isinstance(document, Mapping) else None
        if isinstance(incoming, Mapping):
            incoming_copy = copy.deepcopy(dict(incoming))
            reconcile_running_attempts(incoming_copy, _INTERRUPTION_REASON)
            _merge_ledger_attempts(ledger, incoming_copy)
    return result


def _refresh_statuses(ledger: dict[str, Any], rounds: int) -> None:
    target = set(range(1, rounds + 1))
    for cell in ledger.get("cells", []):
        attempts = cell.get("attempts", [])
        completed = {attempt.get("round") for attempt in attempts if attempt.get("status") == "COMPLETE"}
        if target.issubset(completed):
            cell["status"] = "COMPLETE"
        elif attempts and attempts[-1].get("status") == "FAILED":
            cell["status"] = "FAILED"
        elif attempts and attempts[-1].get("status") == "INVALID":
            cell["status"] = "INVALID"
        else:
            cell["status"] = "PENDING"
    ledger["status"] = "COMPLETE" if ledger.get("cells") and all(c.get("status") == "COMPLETE" for c in ledger["cells"]) else "PARTIAL"


def _load_document(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"ledger": {"cells": campaign_cells()}}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"campaign state must be a JSON object: {path}")
    return value


def _source_ledger_paths(canonical_state: Path, document: Mapping[str, Any] | None = None) -> list[Path]:
    """Return historical shard ledgers without requiring any new artifacts."""
    parent = canonical_state.parent
    paths = [
        parent / "source_h2d_decoupling_batch1_clip.json",
        parent / "source_h2d_decoupling_batch2_unet_small.json",
        parent / "source_h2d_decoupling_batch3_unet_large.json",
    ]
    # Include ledgers from an earlier coordinator invocation as well.  This is
    # useful after a locally interrupted run and is harmless when absent.
    paths.extend(canonical_state.with_name(f"{canonical_state.stem}.{shard.key}.json") for shard in SHARDS)
    if isinstance(document, Mapping):
        for info in (document.get("parallel_shards") or {}).values():
            if not isinstance(info, Mapping):
                continue
            raw_path = info.get("state") or info.get("ledger")
            if not raw_path:
                continue
            candidate = Path(str(raw_path))
            if not candidate.is_absolute():
                repo_candidate = _ROOT / candidate
                candidate = repo_candidate if repo_candidate.exists() else canonical_state.parent / candidate
            if candidate not in paths and candidate != canonical_state:
                paths.append(candidate)
    return paths


def _shard_state_path(canonical_state: Path, shard: Shard) -> Path:
    return canonical_state.with_name(f"{canonical_state.stem}.{shard.key}.json")


def _shard_output_path(canonical_output: Path, shard: Shard) -> Path:
    return canonical_output.with_name(f"{canonical_output.name}_{shard.key}")


def _prepare_documents(canonical_state: Path, canonical_output: Path, rounds: int) -> tuple[dict[str, Any], dict[str, Path], dict[str, Path]]:
    canonical = _load_document(canonical_state)
    ledger = canonical.setdefault("ledger", {})
    if not isinstance(ledger.get("cells"), list) or not ledger["cells"]:
        ledger["cells"] = campaign_cells()
    # Close interrupted work in both the canonical ledger and old shard
    # ledgers before taking their union.  Their source artifacts are untouched.
    reconcile_running_attempts(ledger, "interrupted_before_exp06_parallel_sharding")
    historical_documents = []
    for path in _source_ledger_paths(canonical_state, canonical):
        if path.exists():
            document = _load_document(path)
            reconcile_running_attempts(document.setdefault("ledger", {}), "interrupted_before_exp06_parallel_sharding")
            historical_documents.append(document)
    canonical = merge_ledger_attempts(canonical, historical_documents)
    ledger = canonical["ledger"]
    _refresh_statuses(ledger, rounds)
    shard_cells = partition_cells(ledger["cells"])
    state_paths: dict[str, Path] = {}
    output_paths: dict[str, Path] = {}
    canonical["parallel_shards"] = {}
    for shard in SHARDS:
        state_path = _shard_state_path(canonical_state, shard)
        output_path = _shard_output_path(canonical_output, shard)
        state_paths[shard.key] = state_path
        output_paths[shard.key] = output_path
        canonical["parallel_shards"][shard.key] = {
            "app": shard.default_app,
            "role": shard.role,
            "block_mib": list(shard.blocks),
            "ledger": state_path.as_posix(),
            "out_dir": output_path.as_posix(),
        }
    for shard in SHARDS:
        state_path = state_paths[shard.key]
        shard_ledger = copy.deepcopy(ledger)
        shard_ledger["cells"] = shard_cells[shard.key]
        shard_ledger["app"] = shard.default_app
        shard_ledger["target_rounds"] = rounds
        shard_document = copy.deepcopy(canonical)
        shard_document["ledger"] = shard_ledger
        _atomic_write_json(state_path, shard_document)
    canonical.setdefault("coordinator", {})["source_only"] = True
    canonical["coordinator"]["deployment_performed"] = False
    canonical["coordinator"]["runner"] = "tools/run_exp04_source_ceiling.py"
    return canonical, state_paths, output_paths


_END_RE = re.compile(r"end=(?P<attempt>\S+) status=(?P<status>\S+).*?\bartifact=(?P<artifact>.+)$")


class ProgressCounter:
    """Count unique eligible completions and signal each twentieth one."""

    def __init__(self) -> None:
        self.seen: set[str] = set()
        self.newly_completed = 0

    def record(self, token: str, eligible: bool) -> bool:
        if not eligible or token in self.seen:
            return False
        self.seen.add(token)
        self.newly_completed += 1
        return self.newly_completed % 20 == 0


def combined_progress_line(counter: ProgressCounter, shard_counts: Mapping[str, int]) -> str:
    return "[exp06] progress newly_completed={0} shards={1}".format(
        counter.newly_completed,
        " ".join(f"{key}={shard_counts.get(key, 0)}" for key in (shard.key for shard in SHARDS)),
    )


def _artifact_is_eligible(module: Any, artifact: str, attempt_id: str) -> bool:
    path = Path(artifact)
    if not path.is_absolute():
        path = (_ROOT / path).resolve()
    match = re.match(r"(?P<role>clip|unet)_b(?P<block>\d+)_qd(?P<qd>\d+)_R\d+(?:_A\d+)?$", attempt_id)
    if not match or not path.exists():
        return False
    role = match.group("role")
    block = int(match.group("block"))
    qd = int(match.group("qd"))
    return bool(module.validate_completed_artifact(path, role, _MODELS[role], qd, block * 1024 * 1024, attempt_id)[0])


async def _monitor_child(
    key: str,
    process: asyncio.subprocess.Process,
    counter: ProgressCounter,
    shard_counts: dict[str, int],
) -> int:
    module = _runner_module()
    assert process.stdout is not None
    async for raw_line in process.stdout:
        line = raw_line.decode(errors="replace") if isinstance(raw_line, bytes) else raw_line
        print(f"[{key}] {line}", end="", flush=True)
        match = _END_RE.search(line.rstrip("\r\n"))
        if not match or match.group("status") != "ok":
            continue
        attempt_id = match.group("attempt")
        eligible = _artifact_is_eligible(module, match.group("artifact").strip(), attempt_id)
        before = counter.newly_completed
        boundary = counter.record(f"{key}:{attempt_id}", eligible)
        newly_counted = counter.newly_completed != before
        if newly_counted:
            shard_counts[key] = shard_counts.get(key, 0) + 1
        if boundary:
            print(combined_progress_line(counter, shard_counts), flush=True)
    return await process.wait()


async def _launch_children(
    apps: Sequence[str], state_paths: Mapping[str, Path], output_paths: Mapping[str, Path], rounds: int
) -> list[int]:
    counter = ProgressCounter()
    shard_counts: dict[str, int] = {shard.key: 0 for shard in SHARDS}
    processes: dict[str, asyncio.subprocess.Process] = {}
    try:
        for shard, app in zip(SHARDS, apps):
            output_paths[shard.key].mkdir(parents=True, exist_ok=True)
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--_child",
                "--app",
                app,
                "--state",
                str(state_paths[shard.key]),
                "--out-dir",
                str(output_paths[shard.key]),
                "--role",
                shard.role,
                "--blocks",
                ",".join(str(value) for value in shard.blocks),
                "--rounds",
                str(rounds),
            ]
            processes[shard.key] = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(_ROOT),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        results = await asyncio.gather(
            *(_monitor_child(key, process, counter, shard_counts) for key, process in processes.items())
        )
    except BaseException:
        for process in processes.values():
            if process.returncode is None:
                process.terminate()
        await asyncio.gather(*(process.wait() for process in processes.values()), return_exceptions=True)
        raise
    print(
        f"[exp06] final child totals newly_completed={counter.newly_completed} "
        + " ".join(f"{key}={shard_counts.get(key, 0)}" for key in shard_counts),
        flush=True,
    )
    return results


def _merge_finished_shards(
    canonical: dict[str, Any], canonical_state: Path, state_paths: Mapping[str, Path], rounds: int
) -> dict[str, Any]:
    documents = []
    for path in state_paths.values():
        if not path.exists():
            continue
        document = _load_document(path)
        reconcile_running_attempts(document.setdefault("ledger", {}), _INTERRUPTION_REASON)
        documents.append(document)
    reconcile_running_attempts(canonical.setdefault("ledger", {}), _INTERRUPTION_REASON)
    merged = merge_ledger_attempts(canonical, documents)
    ledger = merged.setdefault("ledger", {})
    # New runner attempts receive a local shard index.  Restore the canonical
    # campaign index during reconciliation without changing runner behavior.
    index_by_key = {_cell_key(cell): int(cell["campaign_index"]) for cell in campaign_cells()}
    for cell in ledger.get("cells", []):
        key = _cell_key(cell)
        if key in index_by_key:
            cell["campaign_index"] = index_by_key[key]
            for attempt in cell.get("attempts", []):
                round_number = attempt.get("round")
                cell_index = int(index_by_key[key])
                attempt["campaign_index"] = (
                    (int(round_number) - 1) * 32 + cell_index
                    if isinstance(round_number, int)
                    else cell_index
                )
    _refresh_statuses(ledger, rounds)
    merged["ledger"] = ledger
    merged["updated_at"] = _now()
    _atomic_write_json(canonical_state, merged)
    return merged


async def _run_coordinator(
    apps: Sequence[str], canonical_state: Path, canonical_output: Path, rounds: int
) -> int:
    if len(apps) != 4:
        raise ValueError("exactly four app names are required")
    canonical, state_paths, output_paths = _prepare_documents(canonical_state, canonical_output, rounds)
    # Record the exact caller-selected identities in both the campaign
    # document and each child ledger; no identity is inferred or deployed.
    for shard, app in zip(SHARDS, apps):
        canonical["parallel_shards"][shard.key]["app"] = app
        shard_document = _load_document(state_paths[shard.key])
        shard_document["ledger"]["app"] = app
        shard_document["parallel_shards"][shard.key]["app"] = app
        _atomic_write_json(state_paths[shard.key], shard_document)
    _atomic_write_json(canonical_state, canonical)
    try:
        results = await _launch_children(apps, state_paths, output_paths, rounds)
    except BaseException:
        # A parent interruption can leave a child between its RUNNING write
        # and its artifact write.  Close that record durably before re-raising.
        interrupted_documents = []
        for path in state_paths.values():
            if not path.exists():
                continue
            document = _load_document(path)
            reconcile_running_attempts(document.setdefault("ledger", {}), _INTERRUPTION_REASON)
            _refresh_statuses(document["ledger"], rounds)
            _atomic_write_json(path, document)
            interrupted_documents.append(document)
        if interrupted_documents:
            merged = merge_ledger_attempts(canonical, interrupted_documents)
            _refresh_statuses(merged["ledger"], rounds)
            _atomic_write_json(canonical_state, merged)
        raise
    merged = _merge_finished_shards(canonical, canonical_state, state_paths, rounds)
    ledger = merged.get("ledger", {})
    attempt_count = sum(len(cell.get("attempts", [])) for cell in ledger.get("cells", []))
    complete_cells = sum(cell.get("status") == "COMPLETE" for cell in ledger.get("cells", []))
    eligible_attempts = sum(
        attempt.get("status") == "COMPLETE"
        for cell in ledger.get("cells", [])
        for attempt in cell.get("attempts", [])
    )
    print(
        f"[exp06] final totals child_exit_codes={results} cells_complete={complete_cells}/32 "
        f"eligible_attempts={eligible_attempts} attempts_retained={attempt_count} "
        f"canonical_state={canonical_state}",
        flush=True,
    )
    return 0 if all(code == 0 for code in results) else 2


async def _run_child(args: argparse.Namespace) -> int:
    module = _runner_module()
    if not args.blocks:
        raise ValueError("child requires block sizes")
    blocks = tuple(int(value) for value in args.blocks.split(",") if value)
    if len(blocks) != 2 or any(value not in _BLOCKS for value in blocks):
        raise ValueError("child requires exactly two valid block sizes")
    app_names = tuple(args.app_names or ())
    if len(app_names) != 1 or not args.role or not args.out_dir:
        raise ValueError("invalid child invocation")
    results = await module._run_campaign(
        app_names[0],
        Path(args.out_dir),
        1,
        args.rounds,
        roles=(args.role,),
        qd_values=_QDS,
        block_mib_values=blocks,
        state_path=Path(args.state),
    )
    return 0 if all(item.get("status") == "ok" for item in results) else 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", action="append", dest="app_names", help="one app per shard; repeat four times")
    parser.add_argument("--apps", nargs=4, metavar=("CLIP_SMALL", "CLIP_LARGE", "UNET_SMALL", "UNET_LARGE"))
    parser.add_argument("--state", "--canonical-state", dest="state", default=str(_DEFAULT_STATE))
    parser.add_argument("--out-root", "--canonical-output-root", dest="out_root", default=str(_DEFAULT_OUTPUT))
    parser.add_argument("--out-dir", dest="out_dir", help=argparse.SUPPRESS)
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument("--_child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--role", choices=_ROLES, help=argparse.SUPPRESS)
    parser.add_argument("--blocks", help=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args._child:
            return asyncio.run(_run_child(args))
        if args.rounds < 1:
            parser.error("--rounds must be positive")
        apps = args.apps or tuple(args.app_names or ())
        if not apps:
            apps = tuple(shard.default_app for shard in SHARDS)
        if len(apps) != 4:
            parser.error("provide exactly four app names via --apps or repeated --app")
        return asyncio.run(_run_coordinator(apps, Path(args.state), Path(args.out_root), args.rounds))
    except Exception as exc:
        print(f"[exp06] failed={type(exc).__name__}:{exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
