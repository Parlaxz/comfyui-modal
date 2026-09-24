#!/usr/bin/env python
"""Collect the deployed source-race oracle matrix, strictly serially."""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import os
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, Sequence

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_DEFAULT_WIDTHS = (1, 2, 4, 8, 16)
_CELL_STATES = ("PENDING", "RUNNING", "COMPLETE", "INVALID", "FAILED")
_LATIN_PERMUTATIONS = (
    (0, 1, 2, 3, 4),
    (4, 3, 2, 1, 0),
    (1, 3, 0, 4, 2),
    (2, 0, 4, 1, 3),
    (3, 4, 1, 2, 0),
)
_EVIDENCE_FIELDS = ("identity", "provider", "region", "observed_gpu", "requested_gpu")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path: Path, value: Any) -> None:
    """Write and fsync a complete JSON document before replacing its path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.replace(temporary, path)
        except PermissionError:
            # OneDrive can briefly deny replacement of an indexed file.
            with path.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump(value, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _parse_widths(raw: str) -> tuple[int, ...]:
    widths = tuple(int(part.strip()) for part in str(raw).split(",") if part.strip())
    if not widths or len(set(widths)) != len(widths) or any(width < 1 for width in widths):
        raise ValueError("--widths must contain distinct positive integers")
    return widths


def _width_order(round_number: int, widths: Sequence[int]) -> tuple[int, ...]:
    widths = tuple(int(width) for width in widths)
    if not widths:
        raise ValueError("widths must not be empty")
    if len(widths) == 5:
        permutation = _LATIN_PERMUTATIONS[(int(round_number) - 1) % 5]
        return tuple(widths[index] for index in permutation)
    shift = (int(round_number) - 1) % len(widths)
    return widths[shift:] + widths[:shift]


def campaign_schedule(
    profile: str,
    rounds: int,
    widths: Sequence[int],
    role: str,
) -> list[dict[str, Any]]:
    """Return a pure, deterministic, round-major Latin-square schedule."""
    profile = str(profile).strip()
    role = str(role).strip()
    if not profile:
        raise ValueError("profile must not be empty")
    if not role:
        raise ValueError("role must not be empty")
    if int(rounds) < 1:
        raise ValueError("rounds must be positive")
    widths = tuple(int(width) for width in widths)
    if not widths or len(set(widths)) != len(widths) or any(width < 1 for width in widths):
        raise ValueError("widths must contain distinct positive integers")
    schedule: list[dict[str, Any]] = []
    index = 0
    for round_number in range(1, int(rounds) + 1):
        for width_index, race_width in enumerate(_width_order(round_number, widths)):
            index += 1
            schedule.append(
                {
                    "campaign_index": index,
                    "profile": profile,
                    "round": round_number,
                    "width_index": width_index,
                    "race_width": race_width,
                    "role": role,
                    "cell_key": ledger_key(profile, round_number, race_width),
                }
            )
    return schedule


def ledger_key(profile: str, round: int, width: int) -> str:
    """Stable serialized form of the ledger key ``(profile, round, width)``."""
    return f"{profile}|round={int(round)}|width={int(width)}"


def _new_ledger(profile: str, config: dict[str, Any], schedule: Sequence[dict[str, Any]]) -> dict[str, Any]:
    cells = {
        item["cell_key"]: {
            "key": [profile, item["round"], item["race_width"]],
            "profile": profile,
            "round": item["round"],
            "width": item["race_width"],
            "width_index": item["width_index"],
            "status": "PENDING",
            "attempts": [],
        }
        for item in schedule
    }
    return {
        "version": 1,
        "campaign": "source_race",
        "profile": profile,
        "config": dict(config),
        "status": "PENDING",
        "cells": cells,
        "updated_at": _now(),
    }


def _load_ledger(
    state_path: Path,
    profile: str,
    config: dict[str, Any],
    schedule: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    loaded: dict[str, Any] = {}
    if state_path.exists():
        value = json.loads(state_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise RuntimeError(f"campaign state must be a JSON object: {state_path}")
        loaded = value
    ledger = _new_ledger(profile, config, schedule)
    old_cells = loaded.get("cells", {})
    if isinstance(old_cells, list):
        old_cells = {str(cell.get("cell_id")): cell for cell in old_cells if isinstance(cell, dict)}
    if isinstance(old_cells, dict):
        for key, cell in ledger["cells"].items():
            old = old_cells.get(key)
            if isinstance(old, dict):
                cell["attempts"] = list(old.get("attempts") or [])
                cell["status"] = old.get("status", "PENDING")
    return ledger


def _save_ledger(state_path: Path, ledger: dict[str, Any]) -> None:
    ledger["updated_at"] = _now()
    _atomic_write_json(state_path, ledger)


def transition_cell(cell: dict[str, Any], state: str, **fields: Any) -> dict[str, Any]:
    """Apply one explicit ledger state transition and return the cell."""
    if state not in _CELL_STATES:
        raise ValueError(f"unknown ledger state: {state}")
    cell["status"] = state
    cell.update(fields)
    return cell


def _artifact_path(out_dir: Path, attempt_id: str, reserved: Iterable[str] = ()) -> Path:
    reserved = set(reserved)
    candidate = out_dir / f"{attempt_id}.json"
    if not candidate.exists() and candidate.stem not in reserved:
        return candidate
    suffix = 2
    while True:
        candidate = out_dir / f"{attempt_id}_A{suffix}.json"
        if not candidate.exists() and candidate.stem not in reserved:
            return candidate
        suffix += 1


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _container_id(result: dict[str, Any]) -> str:
    value = result.get("container_session_id", "")
    identity = result.get("identity")
    if not value and isinstance(identity, dict):
        value = identity.get("container_session_id", "")
    return str(value or "")


def _coldness_evidence(result: dict[str, Any], previous_container_id: str | None) -> dict[str, Any]:
    current = _container_id(result)
    differs = None if previous_container_id is None else current != previous_container_id
    valid = bool(current) and (differs is None or differs)
    if not current:
        assertion = "INVALID: returned container identity is missing; coldness is unproven"
    elif differs is False:
        assertion = (
            "INVALID: returned container identity is identical to the immediately "
            f"preceding run ({current})"
        )
    elif differs is None:
        assertion = "first run; no preceding container identity exists"
    else:
        assertion = "returned container identity differs from the immediately preceding run"
    if not valid:
        print(f"[source-race][INVALID COLDNESS] {assertion}", file=sys.stderr, flush=True)
    return {
        "fresh_container_required": True,
        "single_use_containers": True,
        "observed_container_identity": current,
        "immediately_preceding_container_identity": previous_container_id,
        "differs_from_immediately_preceding": differs,
        "assertion": assertion,
        "valid": valid,
    }


def serialize_run(
    item: dict[str, Any],
    *,
    model_name: str,
    logical_qd: int,
    read_bytes: int,
    max_blocks: int,
    fd_mode: str,
    hash_mode: str,
    attempt_id: str,
    binding: dict[str, Any],
    engine_result: dict[str, Any],
    previous_container_id: str | None,
) -> dict[str, Any]:
    """Serialize one raw engine response without adding classifications."""
    coldness = _coldness_evidence(engine_result, previous_container_id)
    engine_evidence = {name: engine_result.get(name, "") for name in _EVIDENCE_FIELDS}
    return {
        "attempt_id": attempt_id,
        "profile": item["profile"],
        "round": item["round"],
        "width_index": item["width_index"],
        "race_width": item["race_width"],
        "logical_qd": logical_qd,
        "read_bytes": read_bytes,
        "max_blocks": max_blocks,
        "fd_mode": fd_mode,
        "hash_mode": hash_mode,
        "role": item["role"],
        "model_name": model_name,
        "campaign_index": item["campaign_index"],
        **binding,
        "evidence": engine_evidence,
        "engine_evidence": engine_evidence,
        "engine_result": engine_result,
        "coldness_evidence": coldness,
        "campaign_status": (
            "FAILED"
            if engine_result.get("status") != "ok"
            else "COMPLETE" if coldness["valid"] else "INVALID"
        ),
        "finished_at": _now(),
    }


def _destination() -> tuple[str, str]:
    """Return (workspace_id, environment) from the config-owned v2ctl destination.

    v2ctl resolves its deploy destination from ``config/v2/modal_target.toml``.
    The driver must use that same authority: otherwise it can authenticate
    against a different workspace than the one the profile was deployed to and
    fail to find the deployed app.
    """
    import tomllib

    path = _ROOT / "config" / "v2" / "modal_target.toml"
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    modal = data.get("modal") or {}
    workspace_id = str(modal.get("workspace_id") or "").strip()
    environment = str(modal.get("environment") or "").strip()
    if not workspace_id:
        raise RuntimeError(f"no [modal].workspace_id in {path}")
    return workspace_id, environment


def _registry_candidates() -> tuple[Path, ...]:
    """Credential registries, v2ctl's first (that is the one its preflight reads)."""
    return (
        _ROOT / ".git" / "comfymodal" / "modal_workspaces.json",
        _ROOT / ".modal_workspaces.json",
    )


def _active_workspace(workspace_id: str | None = None) -> dict[str, Any]:
    """Resolve credentials for the config-owned destination workspace."""
    destination_id, destination_environment = _destination()
    wanted = str(workspace_id or destination_id).strip()
    errors: list[str] = []
    for registry in _registry_candidates():
        if not registry.is_file():
            continue
        try:
            data = json.loads(registry.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - try the next registry
            errors.append(f"{registry.name}: {exc}")
            continue
        workspace = next(
            (item for item in data.get("workspaces", []) if str(item.get("id") or "") == wanted),
            None,
        )
        if workspace is None:
            continue
        if not workspace.get("token_id") or not workspace.get("token_secret"):
            raise RuntimeError(f"workspace {wanted} has no credentials in {registry}")
        # The config-owned destination environment wins over any registry value.
        environment = destination_environment or str(workspace.get("environment") or "")
        return {**workspace, "environment": environment}
    tried = ", ".join(str(path) for path in _registry_candidates())
    detail = f" (errors: {'; '.join(errors)})" if errors else ""
    raise RuntimeError(
        f"destination workspace {wanted} not found in any registry; tried {tried}{detail}"
    )



def _resolve_profile(profile_name: str) -> Any:
    from tools.v2_control.config import ConfigResolver
    from tools.v2_control.profiles import Profiles
    from tools.v2_control.registry import FlagRegistry

    registry = FlagRegistry(_ROOT / "config" / "v2" / "flag_registry.toml")
    profiles = Profiles(_ROOT / "config" / "v2" / "profiles")
    config = ConfigResolver(_ROOT, profiles, registry).resolve(profile_name=profile_name)
    missing = [
        name for name, value in (
            ("target.app", config.target.app),
            ("target.class_name", config.target.class_name),
            ("target.method", config.target.method),
        ) if not str(value).strip()
    ]
    if missing:
        raise RuntimeError(f"profile {profile_name!r} lacks required fields: {', '.join(missing)}")
    return config


def _receipt_for_profile(config: Any) -> tuple[Path, Any]:
    from tools.v2_control import deployment_receipt

    target = {"app": config.target.app, "class": config.target.class_name, "method": config.target.method}
    selected = deployment_receipt.latest_deployment_receipt(
        _ROOT, profile=config.profile_name, target=target
    )
    if selected is None:
        raise RuntimeError(
            f"no deployment receipt found for profile {config.profile_name!r}; "
            f"run `v2ctl deploy --profile {config.profile_name}` and "
            f"`v2ctl source-probe --profile {config.profile_name}` first"
        )
    return selected


def _binding(config: Any, receipt_path: Path, receipt: Any) -> dict[str, Any]:
    deployed_source = dict(receipt.deployed_source or {})
    return {
        "deployment_version": receipt.deployment_version,
        "deploy_fingerprint": receipt.deploy_fingerprint,
        "profile_config_fingerprint": receipt.profile_config_fingerprint,
        "receipt_path": str(receipt_path),
        "deployed_source": {
            "git_head": str(deployed_source.get("git_head") or ""),
            "dirty_hashes": dict(deployed_source.get("dirty_hashes") or {}),
        },
        "git_head": str(deployed_source.get("git_head") or ""),
        "dirty_hashes": dict(deployed_source.get("dirty_hashes") or {}),
        "target": {
            "app": config.target.app,
            "class_name": config.target.class_name,
            "method": config.target.method,
        },
        "resources": {"gpu": config.resources.gpu},
        "workload": {
            "fresh_required": config.workload.fresh_required,
            "conditioning_cache": config.workload.conditioning_cache,
            "expected_output_sha": config.workload.expected_output_sha,
            "run_count": config.workload.run_count,
            "gap_seconds": config.workload.gap_seconds,
            "nonce": config.workload.nonce,
        },
    }


@contextmanager
def _destination_environment(workspace: dict[str, Any], config: Any):
    original = dict(os.environ)
    try:
        for name in list(os.environ):
            if name.startswith("MODAL_") or name in {
                "COMFYMODAL_ENVIRONMENT", "COMFYMODAL_V2_ENVIRONMENT",
                "COMFYMODAL_MODAL_PROFILE", "COMFYMODAL_V2_APP_NAME",
                "COMFYMODAL_V2_CLASS_NAME", "COMFYMODAL_V2_GPU",
            }:
                os.environ.pop(name, None)
        os.environ["MODAL_TOKEN_ID"] = str(workspace.get("token_id") or "")
        os.environ["MODAL_TOKEN_SECRET"] = str(workspace.get("token_secret") or "")
        environment = str(workspace.get("environment") or "")
        if environment:
            os.environ["MODAL_ENVIRONMENT"] = environment
            os.environ["COMFYMODAL_ENVIRONMENT"] = environment
            os.environ["COMFYMODAL_V2_ENVIRONMENT"] = environment
        os.environ["COMFYMODAL_V2_APP_NAME"] = config.target.app
        os.environ["COMFYMODAL_V2_CLASS_NAME"] = config.target.class_name
        os.environ["COMFYMODAL_V2_GPU"] = config.resources.gpu
        yield
    finally:
        os.environ.clear()
        os.environ.update(original)


def _make_invoker(config: Any, receipt: Any, workspace: dict[str, Any]) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    """Build a serial invoker from the source-probe handle lookup mechanism."""
    from comfymodal_runtime.modal_transport import ModalTransport

    if "id" not in workspace and workspace.get("workspace_id"):
        workspace = {**workspace, "id": workspace["workspace_id"]}
    transport = ModalTransport()
    # Copied from tools/v2_control/source_probe.py:337-349.  The profile's
    # GPU is passed to the same private v2 handle lookup, then its remote
    # method is called through remote.aio when available.
    handle = transport._v2_handle(
        workspace=workspace,
        gpu=config.resources.gpu,
        deployment_identity=receipt.deploy_fingerprint,
    )
    method = getattr(handle, config.target.method, None)
    if method is None:
        raise RuntimeError(f"deployed class has no {config.target.method} method")

    async def invoke(kwargs: dict[str, Any]) -> dict[str, Any]:
        remote = getattr(method, "remote", None)
        if remote is not None and callable(getattr(remote, "aio", None)):
            value = remote.aio(**kwargs)
        else:
            value = method(**kwargs)
        if inspect.isawaitable(value):
            value = await value
        if not isinstance(value, dict):
            raise RuntimeError(f"remote returned {type(value).__name__}")
        return value

    return invoke


async def _run_campaign(
    config: Any,
    receipt_path: Path,
    receipt: Any,
    out_dir: Path,
    args: argparse.Namespace,
    invoke: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    schedule = campaign_schedule(config.profile_name, args.rounds, args.widths, args.role)
    campaign_config = {
        "profile": config.profile_name,
        "rounds": args.rounds,
        "widths": list(args.widths),
        "role": args.role,
        "model_name": args.model_name,
        "logical_qd": args.logical_qd,
        "read_bytes": args.read_bytes,
        "max_blocks": args.max_blocks,
        "fd_mode": args.fd_mode,
        "hash_mode": args.hash_mode,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    state_path = Path(args.state) if args.state else out_dir / "source_race_campaign_state.json"
    ledger = _load_ledger(state_path, config.profile_name, campaign_config, schedule)
    _save_ledger(state_path, ledger)
    binding = _binding(config, receipt_path, receipt)
    results: list[dict[str, Any]] = []
    previous_container_id: str | None = None

    workspace: dict[str, Any] | None = None
    environment = None
    if invoke is None:
        workspace = _active_workspace()
        environment = _destination_environment(workspace, config)
        environment.__enter__()
        try:
            invoke = await asyncio.to_thread(_make_invoker, config, receipt, workspace)
        except Exception:
            environment.__exit__(*sys.exc_info())
            raise

    try:
        for item in schedule:
            cell = ledger["cells"][item["cell_key"]]
            attempts = cell.setdefault("attempts", [])
            latest = attempts[-1] if attempts else None
            if latest and latest.get("status") == "RUNNING":
                transition_cell(cell, "FAILED", error="interrupted_without_artifact", finished_at=_now())
            if latest and latest.get("status") == "COMPLETE" and latest.get("artifact"):
                saved = _read_json(Path(latest["artifact"]))
                if saved and saved.get("campaign_status") == "COMPLETE":
                    results.append(saved)
                    previous_container_id = saved.get("coldness_evidence", {}).get("observed_container_identity")
                    continue

            expected = f"{config.profile_name}_R{item['round']}_W{item['race_width']}"
            artifact_path = _artifact_path(out_dir, expected, (attempt.get("attempt_id") for attempt in attempts))
            attempt_id = artifact_path.stem
            attempt = {
                "attempt_id": attempt_id,
                "round": item["round"],
                "width": item["race_width"],
                "artifact": str(artifact_path),
                "status": "RUNNING",
                "campaign_index": item["campaign_index"],
                "started_at": _now(),
            }
            attempts.append(attempt)
            transition_cell(cell, "RUNNING")
            _save_ledger(state_path, ledger)
            kwargs = {
                "role": args.role,
                "model_name": args.model_name,
                "race_width": item["race_width"],
                "logical_qd": args.logical_qd,
                "read_bytes": args.read_bytes,
                "max_blocks": args.max_blocks,
                "fd_mode": args.fd_mode,
                "hash_mode": args.hash_mode,
                "attempt_id": attempt_id,
            }
            print(f"[source-race] start={attempt_id}", flush=True)
            try:
                invoked = invoke(kwargs)
                engine_result = await invoked if inspect.isawaitable(invoked) else invoked
                if not isinstance(engine_result, dict):
                    raise RuntimeError(f"invocation returned {type(engine_result).__name__}")
                artifact = serialize_run(
                    item,
                    model_name=args.model_name,
                    logical_qd=args.logical_qd,
                    read_bytes=args.read_bytes,
                    max_blocks=args.max_blocks,
                    fd_mode=args.fd_mode,
                    hash_mode=args.hash_mode,
                    attempt_id=attempt_id,
                    binding=binding,
                    engine_result=engine_result,
                    previous_container_id=previous_container_id,
                )
                _atomic_write_json(artifact_path, artifact)
                state = artifact["campaign_status"]
                transition_cell(cell, state, finished_at=artifact["finished_at"], artifact=str(artifact_path))
                attempt.update({"status": state, "finished_at": artifact["finished_at"], "error": None})
                results.append(artifact)
                previous_container_id = artifact["coldness_evidence"]["observed_container_identity"]
                _save_ledger(state_path, ledger)
                print(f"[source-race] end={attempt_id} status={state} artifact={artifact_path}", flush=True)
            except Exception as exc:
                error = f"{type(exc).__name__}:{exc}"
                failed = {
                    "attempt_id": attempt_id,
                    "profile": config.profile_name,
                    "round": item["round"],
                    "width_index": item["width_index"],
                    "race_width": item["race_width"],
                    "logical_qd": args.logical_qd,
                    "read_bytes": args.read_bytes,
                    "max_blocks": args.max_blocks,
                    "fd_mode": args.fd_mode,
                    "hash_mode": args.hash_mode,
                    "role": args.role,
                    "model_name": args.model_name,
                    "campaign_index": item["campaign_index"],
                    **binding,
                    "evidence": {name: "" for name in _EVIDENCE_FIELDS},
                    "engine_evidence": {name: "" for name in _EVIDENCE_FIELDS},
                    "engine_result": {"status": "error", "error": error},
                    "coldness_evidence": {
                        "fresh_container_required": True,
                        "single_use_containers": True,
                        "observed_container_identity": "",
                        "immediately_preceding_container_identity": previous_container_id,
                        "differs_from_immediately_preceding": None,
                        "assertion": "INVALID: invocation raised before a returned container identity",
                        "valid": False,
                    },
                    "campaign_status": "FAILED",
                    "error": error,
                    "finished_at": _now(),
                }
                _atomic_write_json(artifact_path, failed)
                transition_cell(cell, "FAILED", finished_at=failed["finished_at"], artifact=str(artifact_path), error=error)
                attempt.update({"status": "FAILED", "finished_at": failed["finished_at"], "error": error})
                results.append(failed)
                _save_ledger(state_path, ledger)
                print(f"[source-race] FAILED={attempt_id} {error}", file=sys.stderr, flush=True)
        ledger["status"] = "COMPLETE" if all(cell["status"] == "COMPLETE" for cell in ledger["cells"].values()) else "RUNNING"
        _save_ledger(state_path, ledger)
        return results
    finally:
        if environment is not None:
            environment.__exit__(None, None, None)


def _print_schedule(schedule: Sequence[dict[str, Any]]) -> None:
    print("planned source-race schedule (serial, round-major):")
    for item in schedule:
        print(
            f"{item['profile']} round={item['round']} width_index={item['width_index']} "
            f"race_width={item['race_width']} role={item['role']}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--widths", default=",".join(map(str, _DEFAULT_WIDTHS)))
    parser.add_argument("--logical-qd", type=int, default=2)
    parser.add_argument("--read-bytes", type=int, default=134217728)
    parser.add_argument("--fd-mode", default="independent")
    parser.add_argument("--hash-mode", default="winners_in_order")
    parser.add_argument("--max-blocks", type=int, default=0)
    parser.add_argument("--role", default="clip")
    parser.add_argument("--model-name", default="qwen_3_4b.safetensors")
    parser.add_argument("--out", default=str(_ROOT / "unetClipExperimentsSeptember" / "source_race_runs"))
    parser.add_argument("--state", default=None, help="resumable ledger JSON; defaults inside --out")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        args.widths = _parse_widths(args.widths)
        if args.rounds < 1 or args.logical_qd < 1 or args.read_bytes < 1 or args.max_blocks < 0:
            raise ValueError("rounds, logical_qd, and read_bytes must be positive; max_blocks cannot be negative")
        config = _resolve_profile(args.profile)
        schedule = campaign_schedule(config.profile_name, args.rounds, args.widths, args.role)
        if args.dry_run:
            _print_schedule(schedule)
            return 0
        receipt_path, receipt = _receipt_for_profile(config)
        results = asyncio.run(_run_campaign(config, receipt_path, receipt, Path(args.out), args))
        print(f"[source-race] complete observations={len(results)}", flush=True)
        return 0 if all(item.get("campaign_status") == "COMPLETE" for item in results) else 2
    except Exception as exc:
        print(f"[source-race] failed={type(exc).__name__}:{exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
