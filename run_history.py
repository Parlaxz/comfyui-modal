"""Run history persistence and redaction helpers.

Authoritative spec: parent plan sections 13 and 14.

Layout (relative to the custom node root):
    .run_history/<run_id>/meta.json
    .run_history/<run_id>/thumbnail.webp
    .run_history/<run_id>/log.txt
    .run_history/<run_id>/timing.json

Kinds of runs recorded:
    - ordinary: a single run that did not come from an experiment cell
    - experiment_cell: a cell from a run_experiment (linked to experiment_id,
      cell_key, attempt_id)
    - warmup: a deployment warmup run (kind="warmup")

Conventions:
- meta.json is the authoritative per-run record.
- Original output is NOT copied here unless the caller passed
  copy_original=True (the parent's "Copy the original only when the
  original location is temporary").
- Log redaction strips credentials and tokens before writing the log
  file (see _REDACT_PATTERNS).
- timing.json is a small structured dump; the meta.json may embed a
  compact form for the "Last-run drawer" UI.

Public API:
    record_run(root, *, run_id, kind, experiment_id=None, cell_key=None,
               checkpoint_id=None, workflow_name, model_stack, loras,
               prompt, negative_prompt, seed, steps, guidance, sampler,
               scheduler, denoise, width, height, output_path, log_lines,
               timings, status)
    list_runs(root, limit=50)
    get_run(root, run_id)
    redact_log(text) -> str
    format_timing(meta, fmt) -> str   # "text" or "json"
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


# ── Errors ───────────────────────────────────────────────────────────────

class HistoryError(RuntimeError):
    pass


# ── Redaction patterns ──────────────────────────────────────────────────

_REDACT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"ak-[A-Za-z0-9_\-]+"), "ak-REDACTED"),
    (re.compile(r"as-[A-Za-z0-9_\-]+"), "as-REDACTED"),
    (re.compile(r"hf_[A-Za-z0-9]{20,}"), "hf_REDACTED"),
    # Order matters: Bearer must come before the generic Authorization
    # header pattern, otherwise the Authorization pattern eats the
    # whole line first and the Bearer replacement never runs.
    (re.compile(r"Bearer\s+[A-Za-z0-9._\-]+"), "Bearer REDACTED"),
    (re.compile(r"Authorization:\s*[^\n]+", re.IGNORECASE),
     "Authorization: REDACTED"),
    (re.compile(r"civitai_[A-Za-z0-9]{20,}"), "civitai_REDACTED"),
]


def redact_log(text: str) -> str:
    """Redact known credential/token patterns in ``text``."""
    if not text:
        return text
    out = text
    for pattern, replacement in _REDACT_PATTERNS:
        out = pattern.sub(replacement, out)
    return out


# ── Persistence helpers ────────────────────────────────────────────────

def _run_dir(root: str, run_id: str) -> Path:
    return Path(root) / ".run_history" / run_id


def _meta_path(root: str, run_id: str) -> Path:
    return _run_dir(root, run_id) / "meta.json"


def _log_path(root: str, run_id: str) -> Path:
    return _run_dir(root, run_id) / "log.txt"


def _timing_path(root: str, run_id: str) -> Path:
    return _run_dir(root, run_id) / "timing.json"


def _atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, sort_keys=True, indent=2, default=str)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


# ── Public API ──────────────────────────────────────────────────────────

def record_run(root: str, *, run_id: str | None = None,
                kind: str = "ordinary",
                experiment_id: str | None = None,
                cell_key: str | None = None,
                checkpoint_id: str | None = None,
                attempt_id: str | None = None,
                workflow_name: str = "",
                workflow_hash: str = "",
                model_stack: dict | None = None,
                loras: list | None = None,
                prompt: str = "",
                negative_prompt: str = "",
                seed: int | None = None,
                steps: int | None = None,
                guidance: float | None = None,
                sampler: str = "",
                scheduler: str = "",
                denoise: float | None = None,
                width: int | None = None,
                height: int | None = None,
                output_path: str = "",
                log_lines: Iterable[str] | None = None,
                timings: dict | None = None,
                status: str = "completed",
                # B7: additional experiment metadata
                deployment_generation: str = "",
                experiment_revision: int = 0,
                output_policy: dict | None = None) -> str:
    """Record a run in .run_history. Returns the run id."""
    if kind not in ("ordinary", "experiment_cell", "warmup"):
        raise HistoryError(f"invalid kind: {kind!r}")
    rid = run_id or f"run_{uuid.uuid4().hex[:8]}"
    started_at = datetime.now(tz=timezone.utc).isoformat()
    meta = {
        "schema_version": 2,
        "run_id": rid,
        "kind": kind,
        "experiment_id": experiment_id or "",
        "cell_key": cell_key or "",
        "checkpoint_id": checkpoint_id or "",
        "attempt_id": attempt_id or "",
        "started_at": started_at,
        "workflow_name": workflow_name,
        "workflow_hash": workflow_hash,
        "model_stack": model_stack or {},
        "loras": loras or [],
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "seed": seed,
        "steps": steps,
        "guidance": guidance,
        "sampler": sampler,
        "scheduler": scheduler,
        "denoise": denoise,
        "width": width,
        "height": height,
        "output_path": output_path,
        "status": status,
        "timings": timings or {},
        # B7: additional experiment metadata
        "deployment_generation": deployment_generation or "",
        "experiment_revision": int(experiment_revision or 0),
        "output_policy": dict(output_policy or {}),
    }
    _atomic_write_json(_meta_path(root, rid), meta)
    if timings:
        _atomic_write_json(_timing_path(root, rid), timings)
    if log_lines is not None:
        redacted = "\n".join(redact_log(line) for line in log_lines)
        _atomic_write_text(_log_path(root, rid), redacted)
    return rid


def list_runs(root: str, limit: int = 50) -> list:
    """Return the most recent ``limit`` runs, newest first."""
    base = Path(root) / ".run_history"
    if not base.is_dir():
        return []
    out = []
    for entry in sorted(base.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not entry.is_dir():
            continue
        meta = _read_json(entry / "meta.json")
        if meta is not None:
            out.append(meta)
        if len(out) >= limit:
            break
    return out


def get_run(root: str, run_id: str) -> dict | None:
    return _read_json(_meta_path(root, run_id))


def get_log(root: str, run_id: str) -> str | None:
    p = _log_path(root, run_id)
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8", errors="replace")


def get_timing(root: str, run_id: str) -> dict | None:
    return _read_json(_timing_path(root, run_id))


def format_timing(meta: dict, fmt: str = "text") -> str:
    """Format the timing block for copy-as-text or copy-as-json."""
    timings = meta.get("timings", {}) or {}
    if fmt == "json":
        return json.dumps(timings, indent=2, default=str)
    lines = [f"Run: {meta.get('run_id', '')}", f"Workflow: {meta.get('workflow_name', '')}"]
    for k, v in timings.items():
        lines.append(f"  {k}: {v}")
    return "\n".join(lines)


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
