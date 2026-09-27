"""Derived portability report cache with frozen G5 invalidation (Phase G10).

Persistent sidecar cache for validated Workflow portability reports, keyed by
``workflow_version_id`` (WorkflowVersions are immutable, so one current report
per version is sufficient).

DERIVED-ONLY INVARIANT (hard): this cache is a disposable mirror of live
analysis. It NEVER becomes Workflow source of truth, NEVER alters
VersionState/WorkflowVersion, NEVER gates execution or Import, NEVER replaces
live DependencyResolver truth, and NEVER mutates a persisted report's analysis
fields. There is deliberately NO ``runnable``/``authorize``/``can_execute``/
``can_import``-style API here; recomputation decisions belong to later route
integration (G9 seam), not to storage.

Sidecar: ``.studio_portability_reports.json`` next to the other Studio stores.
The file is a JSON ARRAY holding exactly ONE envelope object::

    [
      {
        "cache_format_version": 1,
        "reports": {
          "<workflow_version_id>": {
            "report": { ...contract-valid portability report... },
            "stamp":  { ...exact 8-field G5 invalidation stamp... }
          }
        }
      }
    ]

The array-rooted shape adapts around the existing ``StudioJsonStore``
(list-rooted reader) WITHOUT modifying it, reusing its RLock thread safety,
tmp+``os.replace`` atomic writes, fsync, BOM tolerance, and missing-file
convention.

Invalidation uses ``portability_contract.invalidation_mismatches`` verbatim
(frozen G5 semantics): reuse requires EVERY stamp field concrete (non-null)
on BOTH sides and equal. Any concrete difference stales. Any null on either
side — including null compared with null — stales conservatively. There is
NO TTL: ``analyzed_at`` is never consulted; staleness is evidence/version
based only.

Corruption FAILS OPEN: malformed JSON, wrong root type, unknown cache format,
or a malformed row yields ``invalid``/``miss`` states plus diagnostics —
never an exception to the caller, never a corrupted report presented as a
hit. Because the file is derived, writes may regenerate it from scratch
rather than propagate unrelated pre-existing corruption.

Cross-process guarantee (truthful): single-process thread safety comes from
the store's RLock. Across processes there are NO transactional semantics —
the last COMPLETE atomic writer wins (readers never observe partial JSON
because of tmp+replace). That is acceptable precisely because the cache is
derived and fully regenerable.

Generation values (``model_library_generation``,
``custom_node_registry_generation``), ``dependency_metadata_hash``, and
``comfyui_version`` are OPAQUE comparable values SUPPLIED BY THE CALLER.
This module never inspects Model Library, custom-node registry, or
WorkflowVersion stores to manufacture them.
"""

from __future__ import annotations

import copy
import dataclasses
from pathlib import Path
from typing import Any

import portability_contract as contract
import studio_store

# Internal sidecar layout version. Deliberately DISTINCT from
# manifest_version and rule_version (separate concepts, never collapsed).
CACHE_FORMAT_VERSION = 1

DEFAULT_SIDECAR_FILENAME = ".studio_portability_reports.json"

STATE_HIT = "hit"
STATE_MISS = "miss"
STATE_STALE = "stale"
STATE_INVALID = "invalid"
LOOKUP_STATES = (STATE_HIT, STATE_MISS, STATE_STALE, STATE_INVALID)

FRESHNESS_VERIFIED = "verified"    # checked against a caller-supplied stamp
FRESHNESS_UNCHECKED = "unchecked"  # no current stamp supplied: freshness unknown


@dataclasses.dataclass(frozen=True)
class CacheLookup:
    """Explicit result of ``get`` — callers never infer state from None."""

    state: str                      # one of LOOKUP_STATES
    report: Any                     # validated cached report VIEW, else None
    mismatched_fields: tuple        # stale reason: stamp field names
    reason: str                     # human/log-readable diagnostic

    @property
    def hit(self) -> bool:
        return self.state == STATE_HIT

    @property
    def stale(self) -> bool:
        return self.state == STATE_STALE


@dataclasses.dataclass(frozen=True)
class CachePutResult:
    """Explicit result of ``put`` — rejected puts carry ALL reasons."""

    ok: bool
    version_id: Any
    reasons: tuple


def _row_problems(version_id, row) -> list:
    """Every reason a cached row is unusable; [] means internally consistent."""
    problems = []
    if not isinstance(row, dict):
        return ["cached row is not an object"]
    report = row.get("report")
    if not isinstance(report, dict):
        return ["cached report is not an object"]
    stamp = row.get("stamp")
    if not isinstance(stamp, dict):
        return ["cached stamp is not an object"]
    for issue in contract.report_validation_issues(report):
        problems.append("cached report invalid: %s" % issue)
    for issue in contract.invalidation_stamp_issues(stamp):
        problems.append("cached stamp invalid: %s" % issue)
    if report.get("version_id") != version_id:
        problems.append(
            "cached report version_id %r disagrees with row key %r"
            % (report.get("version_id"), version_id)
        )
    if stamp.get("workflow_version_id") != version_id:
        problems.append(
            "cached stamp workflow_version_id %r disagrees with row key %r"
            % (stamp.get("workflow_version_id"), version_id)
        )
    if report.get("graph_hash") != stamp.get("graph_hash"):
        problems.append("cached graph_hash disagrees between report and stamp")
    return problems


class PortabilityReportCache:
    """Thread-safe derived cache of validated portability reports."""

    def __init__(self, path_or_store) -> None:
        if isinstance(path_or_store, studio_store.StudioJsonStore):
            self._store = path_or_store
        elif isinstance(path_or_store, (str, Path)):
            self._store = studio_store.StudioJsonStore(path_or_store)
        else:
            raise TypeError(
                "path_or_store must be a path or StudioJsonStore, got %r"
                % type(path_or_store).__name__
            )
        self.last_diagnostics: tuple = ()

    @property
    def path(self) -> Path:
        return self._store.path

    # ── read path (fail-open, never repairs) ──────────────────────────────

    def _read_document(self):
        """Return ``(reports_map_or_None, diagnostics)``.

        ``None`` map ⇒ structurally unusable sidecar (caller sees invalid).
        ``{}`` ⇒ usable but empty/missing (caller sees miss).
        """
        try:
            rows = self._store.read()
        except studio_store.StudioStoreError as exc:
            return None, ("sidecar unreadable: %s" % exc,)
        if not isinstance(rows, list):
            return None, ("sidecar root is not a JSON array",)
        if not rows:
            return {}, ()  # missing or empty sidecar: legitimate miss
        if len(rows) > 1:
            return None, (
                "expected exactly one cache envelope, found %d" % len(rows),
            )
        envelope = rows[0]
        if not isinstance(envelope, dict):
            return None, ("cache envelope is not an object",)
        fmt = envelope.get("cache_format_version")
        if isinstance(fmt, bool) or fmt != CACHE_FORMAT_VERSION:
            return None, (
                "incompatible cache_format_version: %r (expected %r)"
                % (fmt, CACHE_FORMAT_VERSION),
            )
        reports = envelope.get("reports")
        if not isinstance(reports, dict):
            return None, ("cache envelope has no valid reports map",)
        return reports, ()

    # ── write path (atomic; regenerates derived content when needed) ──────

    @staticmethod
    def _fresh_envelope() -> dict:
        return {"cache_format_version": CACHE_FORMAT_VERSION, "reports": {}}

    def _writable_envelope(self, rows, diagnostics) -> dict:
        if (
            isinstance(rows, list)
            and len(rows) == 1
            and isinstance(rows[0], dict)
            and rows[0].get("cache_format_version") == CACHE_FORMAT_VERSION
            and isinstance(rows[0].get("reports"), dict)
        ):
            return rows[0]
        if rows:
            diagnostics.append(
                "discarding unrecognized sidecar content during write "
                "(derived cache; regeneration acceptable)"
            )
        return self._fresh_envelope()

    def _mutate_document(self, mutator) -> tuple:
        """Read-modify-write the envelope under the store lock, atomically."""
        diagnostics: list = []

        def apply(rows):
            envelope = self._writable_envelope(rows, diagnostics)
            mutator(envelope)
            rows[:] = [envelope]

        try:
            self._store.update(apply)
        except studio_store.StudioStoreError as exc:
            diagnostics.append(
                "sidecar unusable during write; regenerating derived cache (%s)"
                % exc
            )
            envelope = self._fresh_envelope()
            mutator(envelope)
            self._store.write_atomic([envelope])
        return tuple(diagnostics)

    # ── public API ────────────────────────────────────────────────────────

    def get(self, version_id, current_stamp) -> CacheLookup:
        """Look up one cached report against the caller's current stamp.

        States: ``hit`` (validated report, every stamp field concrete and
        equal), ``stale`` (usable report returned as a COPY marked
        ``stale=true`` plus mismatched field names), ``miss`` (unknown
        version / no file / empty sidecar), ``invalid`` (corrupt or
        incompatible content — never returns the poisoned payload).
        """
        if not isinstance(version_id, str) or not version_id:
            return CacheLookup(STATE_MISS, None, (), "no cache entry for unknown version id")
        reports, diagnostics = self._read_document()
        self.last_diagnostics = diagnostics
        if reports is None:
            return CacheLookup(STATE_INVALID, None, (), "; ".join(diagnostics))
        row = reports.get(version_id)
        if row is None:
            return CacheLookup(
                STATE_MISS, None, (), "no cached report for %r" % version_id
            )
        problems = _row_problems(version_id, row)
        if problems:
            return CacheLookup(STATE_INVALID, None, (), "; ".join(problems))
        cached_stamp = row["stamp"]
        mismatches = tuple(
            contract.invalidation_mismatches(current_stamp, cached_stamp)
        )
        view = copy.deepcopy(row["report"])
        if mismatches:
            view["stale"] = True
            return CacheLookup(
                STATE_STALE,
                view,
                mismatches,
                "stale invalidation fields: %s" % ", ".join(mismatches),
            )
        view["stale"] = False
        return CacheLookup(STATE_HIT, view, (), "cached report reusable")

    def put(self, report) -> CachePutResult:
        """Validate and atomically store one report under its version id.

        Rejects (without writing anything): non-dicts, contract-invalid
        reports, missing/incomplete invalidation stamps, and disagreement
        between version_id/graph_hash across report and stamp. Null stamp
        FIELD VALUES are accepted (they simply can never produce a hit).
        """
        if not isinstance(report, dict):
            return CachePutResult(False, None, ("report must be a dict",))
        version_id = report.get("version_id")
        if not isinstance(version_id, str) or not version_id:
            return CachePutResult(
                False, version_id, ("report.version_id must be a non-empty string",)
            )
        issues = contract.report_validation_issues(report)
        if issues:
            return CachePutResult(
                False,
                version_id,
                tuple("invalid report: %s" % issue for issue in issues),
            )
        stamp = report.get("invalidation")
        if not isinstance(stamp, dict):
            return CachePutResult(
                False,
                version_id,
                (
                    "report.invalidation must be a complete 8-field stamp dict "
                    "to be cacheable",
                ),
            )
        stamp_issues = contract.invalidation_stamp_issues(stamp)
        if stamp_issues:
            return CachePutResult(
                False,
                version_id,
                tuple("invalid stamp: %s" % issue for issue in stamp_issues),
            )
        if stamp.get("workflow_version_id") != version_id:
            return CachePutResult(
                False,
                version_id,
                ("stamp.workflow_version_id must equal report.version_id",),
            )
        if stamp.get("graph_hash") != report.get("graph_hash"):
            return CachePutResult(
                False,
                version_id,
                ("stamp.graph_hash must equal report.graph_hash",),
            )

        stored_row = {
            "report": copy.deepcopy(report),
            "stamp": copy.deepcopy(stamp),
        }

        def mutate(envelope):
            envelope["reports"][version_id] = stored_row

        self.last_diagnostics = self._mutate_document(mutate)
        return CachePutResult(True, version_id, ())

    def remove(self, version_id) -> bool:
        """Drop one version's row; True if it existed. Others are untouched."""
        removed = {"found": False}

        def mutate(envelope):
            reports = envelope.get("reports")
            if isinstance(reports, dict) and version_id in reports:
                del reports[version_id]
                removed["found"] = True

        self.last_diagnostics = self._mutate_document(mutate)
        return removed["found"]

    def clear(self) -> None:
        """Reset the sidecar to an empty v1 envelope (tests/maintenance)."""
        self._store.write_atomic([self._fresh_envelope()])
        self.last_diagnostics = ()

    def inspect(self, version_id) -> dict:
        """Diagnostics for one row without needing a current stamp.

        Never raises on corrupt content; describes what is wrong instead.
        """
        info = {
            "version_id": version_id,
            "present": False,
            "usable": False,
            "problems": [],
            "load_diagnostics": [],
            "stamp": None,
            "risk_level": None,
            "issue_count": None,
            "analyzed_at": None,
        }
        reports, diagnostics = self._read_document()
        info["load_diagnostics"] = list(diagnostics)
        if not reports:
            return info
        row = reports.get(version_id)
        if row is None:
            return info
        info["present"] = True
        problems = _row_problems(version_id, row)
        info["problems"] = problems
        if problems:
            return info
        report = row["report"]
        info["usable"] = True
        info["stamp"] = copy.deepcopy(row["stamp"])
        info["risk_level"] = report.get("risk_level")
        info["issue_count"] = report.get("issue_count")
        info["analyzed_at"] = report.get("analyzed_at")
        return info

    def summaries(self, version_ids, current_stamps=None) -> list:
        """Lightweight list-card metadata for caller-supplied version ids.

        One entry per requested id that has a USABLE cached row (misses and
        unusable rows are omitted, never fabricated). Each entry carries
        ``stale`` plus an explicit ``freshness`` marker so a UI can never
        silently render possibly-stale data as current:

        - ``freshness="verified"``, ``stale=False`` — caller supplied a
          current stamp and every field matched (true hit).
        - ``freshness="verified"``, ``stale=True`` — checked and outdated;
          ``mismatched_fields`` says why.
        - ``freshness="unchecked"``, ``stale=None`` — no current stamp was
          supplied; freshness is UNKNOWN, never asserted current.
        """
        stamps = current_stamps if isinstance(current_stamps, dict) else {}
        reports, diagnostics = self._read_document()
        self.last_diagnostics = diagnostics
        out = []
        if not reports:
            return out
        for version_id in version_ids:
            row = reports.get(version_id)
            if row is None:
                continue
            if _row_problems(version_id, row):
                continue
            report = row["report"]
            entry = {
                "version_id": version_id,
                "risk_level": report.get("risk_level"),
                "issue_count": report.get("issue_count"),
                "analyzed_at": report.get("analyzed_at"),
                "stale": None,
                "freshness": FRESHNESS_UNCHECKED,
                "mismatched_fields": (),
            }
            if version_id in stamps:
                mismatches = tuple(
                    contract.invalidation_mismatches(
                        stamps[version_id], row["stamp"]
                    )
                )
                entry["mismatched_fields"] = mismatches
                entry["stale"] = bool(mismatches)
                entry["freshness"] = FRESHNESS_VERIFIED
            out.append(entry)
        return out


__all__ = [
    "CACHE_FORMAT_VERSION",
    "DEFAULT_SIDECAR_FILENAME",
    "LOOKUP_STATES",
    "STATE_HIT",
    "STATE_MISS",
    "STATE_STALE",
    "STATE_INVALID",
    "FRESHNESS_VERIFIED",
    "FRESHNESS_UNCHECKED",
    "CacheLookup",
    "CachePutResult",
    "PortabilityReportCache",
]
