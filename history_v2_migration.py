"""Non-destructive legacy migration seam for History V2.

Migrates legacy run-history ``meta.json`` files into the History V2 store
without ever writing to or deleting the legacy files.  Supports both legacy
meta schemas:

- ``RunHistoryService`` style (``experiment_service.py``): top-level
  ``run_id/kind/prompt_id/workflow_hash/status/started_at/updated_at/
  output_path`` plus ``extra`` and ``annotations`` dicts.
- Legacy ``run_history.py`` ``schema_version=2`` style: top-level
  ``run_id/kind/experiment_id/cell_key/.../model_stack/prompt/negative_prompt/
  seed/steps/guidance/sampler/scheduler/denoise/width/height/output_path/
  status/timings``.

Idempotent: a legacy run id already present in ``legacy_mapping`` is skipped.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from history_v2_models import RUN_STATUS_VALUES, TERMINAL_RUN_STATUSES, utc_now_iso
from history_v2_repository import HistoryV2Repository


@dataclass
class MigrationReport:
    """Summary of a ``migrate_run_history_dir`` scan."""

    total: int = 0
    imported: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


def _as_path_list(value: Any) -> list[str]:
    """Normalize a string-or-list-of-strings into a unique path list."""
    if isinstance(value, str):
        raw = [value]
    elif isinstance(value, (list, tuple)):
        raw = [v for v in value if isinstance(v, str) and v]
    else:
        raw = []
    seen: set[str] = set()
    out: list[str] = []
    for p in raw:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


class LegacyMigrationSeam:
    """Migrates legacy run-history meta files into the History V2 store."""

    def __init__(self, repo: HistoryV2Repository) -> None:
        self._repo = repo

    # ── Single-file migration ───────────────────────────────────────────

    def migrate_legacy_run_meta(
        self, meta_path: Path, *, source: str = "legacy"
    ) -> Optional[Any]:
        """Migrate one legacy ``meta.json``.

        Returns the created ``Generation`` (or ``None`` when the run id is
        already mapped / absent).  Raises ``ValueError`` for unreadable or
        malformed meta.  Never writes to or deletes the legacy file.
        """
        meta_path = Path(meta_path)
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            raise ValueError(f"unreadable meta.json: {exc}") from exc
        if not isinstance(meta, dict):
            raise ValueError("meta.json must contain a JSON object")

        legacy_run_id = meta.get("run_id")
        if not legacy_run_id:
            return None
        if self._repo._legacy_mapping_exists(legacy_run_id):
            return None  # idempotent skip

        extra = meta.get("extra")
        if not isinstance(extra, dict):
            extra = {}
        annotations = meta.get("annotations")
        if not isinstance(annotations, dict):
            annotations = {}

        # ── Generation fields ──────────────────────────────────────────
        prompt_text = self._extract_prompt(meta, extra)
        negative_prompt_text = self._extract_negative_prompt(meta, extra)
        model_stack = self._extract_model_stack(meta, extra)
        preset_id = extra.get("studio_preset_id") or extra.get("preset_id")
        preset_name = extra.get("studio_preset_label") or extra.get("preset_label")
        workflow_hash = meta.get("workflow_hash") or extra.get("workflow_hash") or None

        experiment_id = meta.get("experiment_id") or extra.get("experiment_id")
        if experiment_id and self._repo.get_experiment(experiment_id) is None:
            experiment_id = None  # don't violate the FK with a legacy-only id

        generation = self._repo.create_generation(
            workflow_id=workflow_hash,
            workflow_version_id=extra.get("workflow_version_id"),
            preset_id=preset_id,
            preset_name=preset_name,
            experiment_id=experiment_id,
            prompt_text=prompt_text,
            negative_prompt_text=negative_prompt_text,
            model_stack=model_stack,
            favorite=bool(annotations.get("favorite")),
            note=annotations.get("note") or "",
            created_at=meta.get("started_at"),
        )

        # ── One attempt (mode='original') ──────────────────────────────
        attempt = self._repo.add_attempt(
            generation.generation_id,
            mode="original",
            started_at=meta.get("started_at"),
        )
        raw_status = meta.get("status")
        terminal_status: Optional[str] = None
        if isinstance(raw_status, str) and raw_status in RUN_STATUS_VALUES:
            if raw_status in {s.value for s in TERMINAL_RUN_STATUSES}:
                terminal_status = raw_status
            # status present but non-terminal (queued/running): leave queued.
        else:
            terminal_status = "completed"  # missing/invalid -> completed
        timing = meta.get("timings") or meta.get("timing_summary")
        if terminal_status is not None:
            self._repo.update_attempt_terminal(
                attempt.run_id,
                status=terminal_status,
                finished_at=meta.get("updated_at") or meta.get("completed_at"),
                timing=timing if isinstance(timing, dict) else None,
            )

        # ── Assets (copy=False, pointing at the legacy paths) ──────────
        candidates: list[str] = []
        candidates.extend(_as_path_list(meta.get("output_path")))
        candidates.extend(_as_path_list(extra.get("output_path")))
        candidates.extend(_as_path_list(extra.get("output_paths")))
        for entry in extra.get("assets") or []:
            if isinstance(entry, dict):
                for key in ("path", "asset_path", "managed_path"):
                    value = entry.get(key)
                    if isinstance(value, str) and value:
                        candidates.append(value)
                        break
        for candidate in candidates:
            if Path(candidate).is_file():
                self._repo.attach_asset(
                    generation.generation_id,
                    run_id=attempt.run_id,
                    asset_type="original",
                    source_path=candidate,
                    copy=False,
                    filename=Path(candidate).name,
                )

        # ── Request snapshot (executable workflow JSON if available) ───
        workflow_json = extra.get("workflow_json")
        if isinstance(workflow_json, dict) and workflow_json:
            generation_params: dict[str, Any] = {}
            for key in ("seed", "steps", "guidance", "sampler", "scheduler",
                        "denoise", "width", "height"):
                value = meta.get(key)
                if value is None:
                    value = extra.get(key)
                if value is None:
                    value = self._extract_control(extra, key)
                if value is not None:
                    generation_params[key] = value
            if prompt_text:
                generation_params["prompt"] = prompt_text
            if negative_prompt_text:
                generation_params["negative_prompt"] = negative_prompt_text
            self._repo.create_request_snapshot(
                workflow_json=workflow_json,
                generation_params=generation_params,
                workflow_hash=workflow_hash,
                workflow_version_id=extra.get("workflow_version_id"),
                generation_id=generation.generation_id,
            )

        # ── Record the mapping last (marks the run as migrated) ────────
        self._repo._record_legacy_mapping(legacy_run_id, generation.generation_id, source)
        return generation

    # ── Directory scan ──────────────────────────────────────────────────

    def migrate_run_history_dir(
        self, run_history_root: Path, *, dry_run: bool = False
    ) -> MigrationReport:
        """Scan ``<root>/*/meta.json`` (one level deep) and migrate each.

        ``dry_run`` counts without any repo writes.
        """
        report = MigrationReport()
        root = Path(run_history_root)
        if not root.is_dir():
            return report
        for entry in sorted(root.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            meta_path = entry / "meta.json"
            if not meta_path.is_file():
                continue
            report.total += 1
            if dry_run:
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        parsed = json.load(f)
                    if isinstance(parsed, dict):
                        report.imported += 1
                    else:
                        report.failed += 1
                        report.errors.append(f"{meta_path}: not a JSON object")
                except (json.JSONDecodeError, OSError) as exc:
                    report.failed += 1
                    report.errors.append(f"{meta_path}: {exc}")
                continue
            try:
                generation = self.migrate_legacy_run_meta(meta_path)
                if generation is None:
                    report.skipped += 1
                else:
                    report.imported += 1
            except Exception as exc:
                report.failed += 1
                report.errors.append(f"{meta_path}: {type(exc).__name__}: {exc}")
        return report

    def dry_run_report(self, run_history_root: Path) -> MigrationReport:
        """Count what a migration would do, without writing anything."""
        return self.migrate_run_history_dir(run_history_root, dry_run=True)

    # ── Field extraction helpers ────────────────────────────────────────

    @staticmethod
    def _extract_prompt(meta: dict, extra: dict) -> str:
        for value in (
            meta.get("prompt"),
            (extra.get("resolved_controls") or {}).get("prompt")
            if isinstance(extra.get("resolved_controls"), dict) else None,
            (extra.get("requested_controls") or {}).get("prompt")
            if isinstance(extra.get("requested_controls"), dict) else None,
            extra.get("prompt"),
            extra.get("studio_prompt"),
        ):
            if isinstance(value, str) and value:
                return value
        return ""

    @staticmethod
    def _extract_negative_prompt(meta: dict, extra: dict) -> str:
        for value in (
            meta.get("negative_prompt"),
            (extra.get("resolved_controls") or {}).get("negative_prompt")
            if isinstance(extra.get("resolved_controls"), dict) else None,
            (extra.get("requested_controls") or {}).get("negative_prompt")
            if isinstance(extra.get("requested_controls"), dict) else None,
            extra.get("negative_prompt"),
            extra.get("studio_negative_prompt"),
        ):
            if isinstance(value, str) and value:
                return value
        return ""

    @staticmethod
    def _extract_control(extra: dict, key: str) -> Any:
        """Pull a scalar generation control from extra's controls dicts."""
        for controls_key in ("resolved_controls", "requested_controls"):
            controls = extra.get(controls_key)
            if isinstance(controls, dict) and controls.get(key) is not None:
                return controls[key]
        return None

    @staticmethod
    def _extract_model_stack(meta: dict, extra: dict) -> list[dict[str, Any]]:
        stack = meta.get("model_stack")
        if stack is None:
            stack = extra.get("model_stack")
        if isinstance(stack, dict):
            return [stack]
        if isinstance(stack, list):
            return [s for s in stack if isinstance(s, dict)]
        return []
