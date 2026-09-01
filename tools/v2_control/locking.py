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
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

from .errors import LockHeldError, LockStaleError

LOG = logging.getLogger("v2ctl.locking")

_LOCK_SCHEMA_VERSION = 1
_STALE_AGE_SECONDS = 6 * 3600  # foreign-host lock older than 6h is stale


@dataclass(frozen=True)
class LockRecoveryRecord:
    """Auditable facts for one successful automatic stale-lock recovery."""

    owner: str
    pid: int
    host: str
    target: str
    acquisition_timestamp: str
    proof_pid_dead: bool
    action: str

    def as_dict(self) -> dict[str, object]:
        """Return the non-secret recovery facts in a serialization-friendly form."""
        return {
            "owner": self.owner,
            "pid": self.pid,
            "host": self.host,
            "target": self.target,
            "acquisition_timestamp": self.acquisition_timestamp,
            "proof_pid_dead": self.proof_pid_dead,
            "action": self.action,
        }


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
        self._last_recovery: LockRecoveryRecord | None = None

    @property
    def last_recovery(self) -> LockRecoveryRecord | None:
        """The most recent successful automatic recovery, if any."""
        return self._last_recovery

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
        except ProcessLookupError:
            return False
        except OSError:
            # EPERM and other probe failures do not prove that the process is
            # dead.  Keep the lock in place when liveness is uncertain.
            return True
        except Exception:  # noqa: BLE001 - probe failure means "cannot prove dead"
            LOG.warning("pid-liveness probe failed for pid %s; treating as alive", pid)
            return True

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
        if proc.returncode != 0:
            return True
        if "No tasks" in out:
            return False
        # An unexpected successful response is not proof of death.  Only the
        # explicit tasklist no-match response is evidence we can use to
        # recover a lock automatically.
        return True

    # -- acquire interlock ---------------------------------------------------

    @contextmanager
    def _acquire_interlock(self) -> Iterator[None]:
        """Serialize every lock-file mutation made by a DeployLock client.

        The primary lock is replaced during automatic recovery, so an
        ``O_EXCL`` create followed by a re-read is not sufficient by itself:
        another DeployLock could otherwise change the lock after validation
        and before ``os.replace``.  A persistent sidecar is used as the
        stable lock object because replacing the primary file would replace
        any lock held on that file too.  The platform's advisory/exclusive
        file-lock primitive is deliberately not optional; failure to acquire
        it fails closed instead of falling back to an unsafe replacement.
        """
        self.lock_dir().mkdir(parents=True, exist_ok=True)
        interlock_path = self.lock_dir() / f".{self._lock_path.name}.interlock"
        with interlock_path.open("a+b") as handle:
            try:
                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                self._lock_interlock_file(handle)
            except OSError as exc:
                raise LockHeldError(
                    "unable to acquire deploy-lock interlock; refusing unsafe lock mutation"
                ) from exc
            try:
                yield
            finally:
                self._unlock_interlock_file(handle)

    @staticmethod
    def _lock_interlock_file(handle) -> None:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            return
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)

    @staticmethod
    def _unlock_interlock_file(handle) -> None:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            return
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    # -- acquire ------------------------------------------------------------

    def acquire(
        self,
        *,
        owner: str,
        target: str,
        profile: str,
        force: bool = False,
        auto_recover: bool = False,
    ) -> dict:
        """Acquire the deploy lock while holding the cross-process interlock."""
        self.lock_dir().mkdir(parents=True, exist_ok=True)
        with self._acquire_interlock():
            return self._acquire_locked(
                owner=owner,
                target=target,
                profile=profile,
                force=force,
                auto_recover=auto_recover,
            )

    def _acquire_locked(
        self,
        *,
        owner: str,
        target: str,
        profile: str,
        force: bool = False,
        auto_recover: bool = False,
    ) -> dict:
        """Atomically create the lock file (O_EXCL).  Returns the written
        payload dict.

        Raises:
            LockStaleError -- lock exists and is stale; the user must pass
                ``force=True`` explicitly, unless ``auto_recover=True`` proves
                this owner's same-host pid is definitely dead.
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
                self._last_recovery = None
                return payload
            if auto_recover:
                recovery = self._recover_if_proven(existing, owner=owner, body=body)
                if recovery is not None:
                    self._remember(payload)
                    self._last_recovery = recovery
                    LOG.warning(
                        "automatic deploy lock recovery: owner=%s pid=%s host=%s target=%s "
                        "acquisition_timestamp=%s proof_pid_dead=%s action=%s",
                        recovery.owner,
                        recovery.pid,
                        recovery.host,
                        recovery.target,
                        recovery.acquisition_timestamp,
                        recovery.proof_pid_dead,
                        recovery.action,
                    )
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
        self._last_recovery = None
        LOG.info("deploy lock acquired: %s (owner=%s pid=%s host=%s)", self._lock_path, owner, payload["pid"], payload["host"])
        return payload

    def _recover_if_proven(self, existing: dict | None, *, owner: str, body: str) -> LockRecoveryRecord | None:
        """Replace an existing lock only after all recovery facts are proven."""
        validated = self._validate_recovery_status(existing)
        if validated is None:
            return None
        if not isinstance(existing, dict):
            return None
        pid, acquisition_timestamp = validated
        if existing["owner"] != owner or existing["host"] != self.host_id():
            return None
        try:
            if self._pid_alive(pid):
                return None
        except Exception:  # noqa: BLE001 - an exception is not proof of death
            LOG.warning("deploy lock pid-liveness probe failed; refusing automatic recovery")
            return None

        # Re-read immediately before replacement.  The replacement itself is
        # atomic, so readers see either the old complete lock or the new one;
        # a change observed before this point is never overwritten.
        if self.status() != existing:
            LOG.warning("deploy lock changed during automatic recovery; refusing replacement")
            return None
        if not self._atomic_replace(body, expected=existing):
            return None
        return LockRecoveryRecord(
            owner=existing["owner"],
            pid=pid,
            host=existing["host"],
            target=existing["target"],
            acquisition_timestamp=acquisition_timestamp,
            proof_pid_dead=True,
            action="replace_stale_lock",
        )

    def _validate_recovery_status(self, status: dict | None) -> tuple[int, str] | None:
        """Return trusted recovery fields, or None for any ambiguity."""
        if (
            not isinstance(status, dict)
            or type(status.get("schema_version")) is not int
            or status.get("schema_version") != _LOCK_SCHEMA_VERSION
        ):
            return None
        for field in ("owner", "host", "target", "timestamp"):
            value = status.get(field)
            if not isinstance(value, str) or not value.strip():
                return None
        pid = status.get("pid")
        if isinstance(pid, bool):
            return None
        if isinstance(pid, int):
            parsed_pid = pid
        elif isinstance(pid, str) and pid.strip().isdigit():
            parsed_pid = int(pid.strip())
        else:
            return None
        if parsed_pid <= 0:
            return None
        timestamp = status["timestamp"]
        try:
            parsed_timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
        if parsed_timestamp.tzinfo is None or parsed_timestamp.utcoffset() is None:
            return None
        return parsed_pid, timestamp

    def _atomic_replace(self, body: str, *, expected: dict) -> bool:
        """Conditionally publish a complete replacement.

        The interlock protects this check from other DeployLock clients.  The
        second check also makes a replacement injected by an external writer
        fail closed rather than overwriting a changed lock or resurrecting a
        deleted one.
        """
        if self.status() != expected:
            LOG.warning("deploy lock changed before automatic replacement; refusing replacement")
            return False
        temp_path: str | None = None
        try:
            fd, temp_path = tempfile.mkstemp(
                prefix=f".{self._lock_path.name}.",
                suffix=".tmp",
                dir=self.lock_dir(),
            )
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self._lock_path)
            temp_path = None
            return True
        except OSError as exc:
            LOG.warning("automatic deploy lock recovery replacement failed: %s", exc)
            return False
        finally:
            if temp_path is not None:
                try:
                    os.unlink(temp_path)
                except FileNotFoundError:
                    pass

    def _remember(self, payload: dict) -> None:
        self._owner = payload.get("owner")
        self._pid = payload.get("pid")
        self._host = payload.get("host")

    # -- release ------------------------------------------------------------

    def release(self) -> None:
        """Release the lock while holding the cross-process interlock."""
        if not self._lock_path.exists():
            return None
        with self._acquire_interlock():
            return self._release_locked()

    def _release_locked(self) -> None:
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
        with self._acquire_interlock():
            self._force_release_locked(requested_by)

    def _force_release_locked(self, requested_by: str) -> None:
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
