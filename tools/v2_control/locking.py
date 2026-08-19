"""Deploy ownership lock for the v2ctl control plane (Batch E32).

Implements design section 16 ("Deploy Ownership Lock") of
V2_CANONICAL_DEPLOY_RUN_CONTROL_PLANE.md:

* deploy commands acquire the lock automatically;
* a conflicting deploy owner exits nonzero (LockHeldError);
* stale-lock detection requires *evidence* (dead pid on the same host, or a
  foreign host whose lock is older than 6h) -- we never steal silently;
* force-unlock is explicit and logged;
* release is visible (removed only when pid+owner match our own identity).

Python 3.11 stdlib only; no network calls.  The only subprocess use is
`tasklist` on win32 for pid liveness evidence.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .errors import LockHeldError, LockStaleError

LOG = logging.getLogger("v2ctl.locking")

_LOCK_SCHEMA_VERSION = 1
_STALE_AGE_SECONDS = 6 * 3600  # foreign-host lock older than 6h is stale


def _default_lock_path() -> Path:
    """<repo_root>/.v2ctl/deploy.lock -- repo root is two levels above tools/."""
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / ".v2ctl" / "deploy.lock"


class DeployLock:
    """A single-writer deploy lock stored as JSON at ``.v2ctl/deploy.lock``.

    The lock file records ``{schema_version, owner, pid, host, target,
    profile, timestamp, started_at}``.  ``now_fn`` is an injectable clock
    (``Callable[[], datetime]``) used by tests to make staleness
    deterministic; the default is ``datetime.now(timezone.utc)``.
    """

    def __init__(self, lock_path: Path | None = None, *, now_fn: Callable[[], datetime] | None = None) -> None:
        self._lock_path = Path(lock_path) if lock_path is not None else _default_lock_path()
        self._now_fn = now_fn
        # Identity captured at acquire(); release() only removes a lock whose
        # pid+owner match these.
        self._owner: str | None = None
        self._pid: int | None = None
        self._host: str | None = None

    # -- identity -----------------------------------------------------------

    @staticmethod
    def host_id() -> str:
        """Simple host identity: ``socket.gethostname()`` (kept deliberately
        simple per the contract -- no uuid suffix)."""
        return socket.gethostname()

    def lock_dir(self) -> Path:
        """Parent directory of the lock file (``.v2ctl``)."""
        return self._lock_path.parent

    # -- clock --------------------------------------------------------------

    def _now(self) -> datetime:
        if self._now_fn is not None:
            return self._now_fn()
        return datetime.now(timezone.utc)

    # -- status -------------------------------------------------------------

    def status(self) -> dict | None:
        """Parsed lock JSON, or None when missing/corrupt (corrupt logs a
        warning and is treated as 'no usable lock')."""
        try:
            raw = self._lock_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as exc:  # pragma: no cover - defensive
            LOG.warning("cannot read deploy lock %s: %s", self._lock_path, exc)
            return None
        try:
            data = json.loads(raw)
        except (ValueError, TypeError) as exc:
            LOG.warning("deploy lock %s is corrupt (unparseable JSON): %s", self._lock_path, exc)
            return None
        if not isinstance(data, dict):
            LOG.warning("deploy lock %s is corrupt (not a JSON object)", self._lock_path)
            return None
        return data

    # -- staleness (evidence-based; never steal silently) -------------------

    def is_stale(self, status: dict | None = None) -> bool:
        """Evidence-based staleness.

        A lock is stale only when:

        * it is on the *same host* and the recorded pid is not alive
          (posix: ``os.kill(pid, 0)``; win32: ``tasklist /FI "PID eq N"``), or
        * it is on a *different host* AND older than 6 hours.

        Anything ambiguous (missing fields, unparseable timestamp, a liveness
        probe that failed) is treated as *not stale* -- we never steal
        silently.
        """
        status = status if status is not None else self.status()
        if not status:
            return False
        pid = status.get("pid")
        host = status.get("host")
        timestamp = status.get("timestamp")
        if pid is None or host is None or timestamp is None:
            LOG.warning("deploy lock %s lacks pid/host/timestamp; treating as not stale", self._lock_path)
            return False
        if host == self.host_id():
            alive = self._pid_alive(pid)
            if not alive:
                LOG.info("deploy lock %s pid %s is dead on this host -> stale", self._lock_path, pid)
                return True
            return False
        age = self._lock_age(timestamp)
        if age is None:
            return False
        if age > _STALE_AGE_SECONDS:
            LOG.info(
                "deploy lock %s is on foreign host %s and %d seconds old (>6h) -> stale",
                self._lock_path, host, age,
            )
            return True
        return False

    def _lock_age(self, timestamp: str) -> float | None:
        try:
            ts = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            LOG.warning("deploy lock %s has unparseable timestamp %r", self._lock_path, timestamp)
            return None
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (self._now() - ts).total_seconds()

    def _pid_alive(self, pid: object) -> bool:
        """True when the pid is (probably) alive; probe failure -> True
        (treated as not-stale, per contract)."""
        try:
            pid = int(pid)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return True
        if os.name == "nt":
            return self._win_pid_alive(pid)
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    @staticmethod
    def _win_pid_alive(pid: int) -> bool:
        """tasklist /FI "PID eq <pid>" -- parse output; tolerate failure as
        not-stale (alive=True)."""
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            proc = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True,
                text=True,
                timeout=10,
                **kwargs,
            )
        except Exception:  # noqa: BLE001 - probe failure means "cannot prove dead"
            LOG.warning("tasklist pid-liveness probe failed for pid %s; treating as alive", pid)
            return True
        out = f"{proc.stdout or ''}\n{proc.stderr or ''}"
        # tasklist prints "INFO: No tasks are running which match the
        # specified criteria." when the pid does not exist; any row output
        # (header + process line, which contains the pid) means alive.
        if "No tasks" in out:
            return False
        return str(pid) in out

    # -- acquire ------------------------------------------------------------

    def acquire(self, *, owner: str, target: str, profile: str, force: bool = False) -> dict:
        """Atomically create the lock file (O_EXCL).  Returns the written
        payload dict.

        Raises:
            LockStaleError -- lock exists and is stale; the user must pass
                ``force=True`` explicitly (never auto-steal).
            LockHeldError -- lock exists, is fresh, and is owned by someone
                else (carries all recorded fields).
        """
        now = self._now()
        payload = {
            "schema_version": _LOCK_SCHEMA_VERSION,
            "owner": owner,
            "pid": os.getpid(),
            "host": self.host_id(),
            "target": target,
            "profile": profile,
            "timestamp": now.isoformat(),
            "started_at": now.isoformat(),
        }
        self.lock_dir().mkdir(parents=True, exist_ok=True)
        body = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        try:
            fd = os.open(self._lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            existing = self.status()
            if force:
                LOG.warning(
                    "force acquire: replacing existing deploy lock %s (previous owner=%s pid=%s host=%s)",
                    self._lock_path,
                    (existing or {}).get("owner"),
                    (existing or {}).get("pid"),
                    (existing or {}).get("host"),
                )
                self._lock_path.write_text(body, encoding="utf-8")
                self._remember(payload)
                return payload
            if existing is not None and self.is_stale(existing):
                raise LockStaleError(
                    "deploy lock exists and appears stale (pid dead on this host, or a "
                    "foreign-host lock older than 6h); pass --force to replace it explicitly "
                    "- v2ctl never steals locks silently"
                )
            raise LockHeldError(
                "deploy lock is held by another process; refusing to acquire",
                owner=existing.get("owner") if existing else None,
                pid=existing.get("pid") if existing else None,
                host=existing.get("host") if existing else None,
                target=existing.get("target") if existing else None,
                profile=existing.get("profile") if existing else None,
                timestamp=existing.get("timestamp") if existing else None,
            )
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(body)
        self._remember(payload)
        LOG.info("deploy lock acquired: %s (owner=%s pid=%s host=%s)", self._lock_path, owner, payload["pid"], payload["host"])
        return payload

    def _remember(self, payload: dict) -> None:
        self._owner = payload.get("owner")
        self._pid = payload.get("pid")
        self._host = payload.get("host")

    # -- release ------------------------------------------------------------

    def release(self) -> None:
        """Remove the lock only when pid+owner match our own acquire
        identity.  Missing lock file is a no-op; anything else raises
        LockHeldError."""
        status = self.status()
        if status is None:
            return None  # nothing held (or corrupt); nothing to release
        if self._owner is None or self._pid is None:
            raise LockHeldError(
                "deploy lock is held by another process and this instance never "
                "acquired it; refusing to release",
                owner=status.get("owner"),
                pid=status.get("pid"),
                host=status.get("host"),
                target=status.get("target"),
                profile=status.get("profile"),
                timestamp=status.get("timestamp"),
            )
        if status.get("pid") == self._pid and status.get("owner") == self._owner:
            self._lock_path.unlink(missing_ok=True)
            LOG.info("deploy lock released: %s (owner=%s pid=%s)", self._lock_path, self._owner, self._pid)
            self._owner = None
            self._pid = None
            self._host = None
            return None
        raise LockHeldError(
            "deploy lock is held by a different owner/pid; refusing to release",
            owner=status.get("owner"),
            pid=status.get("pid"),
            host=status.get("host"),
            target=status.get("target"),
            profile=status.get("profile"),
            timestamp=status.get("timestamp"),
        )

    def force_release(self, requested_by: str) -> None:
        """Explicit forced removal -- always logged."""
        status = self.status()
        LOG.warning(
            "force release of deploy lock %s requested by %s (previous owner=%s pid=%s host=%s)",
            self._lock_path,
            requested_by,
            (status or {}).get("owner"),
            (status or {}).get("pid"),
            (status or {}).get("host"),
        )
        self._lock_path.unlink(missing_ok=True)
        self._owner = None
        self._pid = None
        self._host = None
