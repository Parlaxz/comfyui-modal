"""Tests for tools/v2_control/locking.py (design section 16).

Covers contract section 21 lock coverage: acquire/status/release, conflicting
owner, held-by-other release, force acquire, evidence-based stale detection
(via injected clock), and stale acquire without force.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from tools.v2_control.errors import LockHeldError, LockStaleError
from tools.v2_control.locking import DeployLock


def make_now() -> datetime:
    return datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def lock_path(tmp_path):
    return tmp_path / ".v2ctl" / "deploy.lock"


@pytest.fixture
def now():
    return make_now()


def make_lock(lock_path, now=None):
    return DeployLock(lock_path, now_fn=(lambda: now) if now is not None else None)


def write_lock(lock_path, owner="other", pid=424242, host=None, timestamp=None, target="t", profile="p"):
    if host is None:
        host = DeployLock.host_id()
    if timestamp is None:
        timestamp = datetime(2026, 1, 1, 11, 0, 0, tzinfo=timezone.utc).isoformat()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "owner": owner,
                "pid": pid,
                "host": host,
                "target": target,
                "profile": profile,
                "timestamp": timestamp,
                "started_at": timestamp,
            }
        ),
        encoding="utf-8",
    )


class TestAcquireStatusRelease:
    def test_acquire_writes_json_and_status_roundtrips(self, lock_path, now):
        lock = make_lock(lock_path, now)
        payload = lock.acquire(owner="e29", target="stable-modal-comfy-v2-restore-only-shadow", profile="production")
        assert payload["schema_version"] == 1
        assert payload["owner"] == "e29"
        assert payload["pid"] == os.getpid()
        assert payload["host"] == DeployLock.host_id()
        assert payload["target"] == "stable-modal-comfy-v2-restore-only-shadow"
        assert payload["profile"] == "production"
        assert payload["timestamp"] == now.isoformat()

        status = lock.status()
        assert status is not None
        assert status["owner"] == "e29"
        assert status["pid"] == os.getpid()
        assert status["host"] == DeployLock.host_id()

    def test_status_none_when_missing(self, lock_path):
        assert make_lock(lock_path).status() is None

    def test_status_none_when_corrupt(self, lock_path):
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text("{not json", encoding="utf-8")
        assert make_lock(lock_path).status() is None

    def test_release_removes_lock(self, lock_path, now):
        lock = make_lock(lock_path, now)
        lock.acquire(owner="e29", target="t", profile="p")
        lock.release()
        assert lock.status() is None

    def test_release_missing_lock_is_noop(self, lock_path):
        make_lock(lock_path).release()  # must not raise

    def test_conflicting_owner_acquire_raises_lock_held(self, lock_path, now):
        lock = make_lock(lock_path, now)
        lock.acquire(owner="e29", target="t", profile="p")
        other = make_lock(lock_path, now + timedelta(seconds=1))
        with pytest.raises(LockHeldError) as excinfo:
            other.acquire(owner="e30", target="t", profile="p")
        assert excinfo.value.owner == "e29"
        assert excinfo.value.pid == os.getpid()
        assert excinfo.value.host == DeployLock.host_id()
        assert excinfo.value.target == "t"
        assert excinfo.value.profile == "p"
        assert excinfo.value.timestamp == now.isoformat()

    def test_held_by_other_release_raises(self, lock_path, now):
        lock = make_lock(lock_path, now)
        lock.acquire(owner="e29", target="t", profile="p")
        other = make_lock(lock_path, now + timedelta(seconds=1))
        with pytest.raises(LockHeldError):
            other.release()
        # lock still in place
        assert lock.status() is not None

    def test_force_acquire_replaces_and_logs(self, lock_path, now, caplog):
        lock = make_lock(lock_path, now)
        lock.acquire(owner="e29", target="t", profile="p")
        force_lock = make_lock(lock_path, now + timedelta(seconds=1))
        with caplog.at_level("WARNING", logger="v2ctl.locking"):
            payload = force_lock.acquire(owner="e30", target="t2", profile="p2", force=True)
        assert payload["owner"] == "e30"
        assert lock.status()["owner"] == "e30"
        assert "force" in caplog.text.lower()

    def test_force_release_removes_and_logs(self, lock_path, now, caplog):
        lock = make_lock(lock_path, now)
        lock.acquire(owner="e29", target="t", profile="p")
        with caplog.at_level("WARNING", logger="v2ctl.locking"):
            lock.force_release("test-user")
        assert lock.status() is None
        assert "force release" in caplog.text.lower()


class TestStaleDetection:
    def test_dead_pid_same_host_is_stale(self, lock_path, now):
        write_lock(lock_path, pid=99999999, timestamp=now.isoformat())
        lock = make_lock(lock_path, now)
        assert lock.is_stale() is True

    def test_fresh_lock_same_host_not_stale(self, lock_path, now):
        write_lock(lock_path, pid=os.getpid(), timestamp=now.isoformat())
        lock = make_lock(lock_path, now)
        assert lock.is_stale() is False

    def test_foreign_host_old_lock_is_stale(self, lock_path, now):
        old = (now - timedelta(hours=7)).isoformat()
        write_lock(lock_path, pid=12345, host="some-other-machine", timestamp=old)
        lock = make_lock(lock_path, now)
        assert lock.is_stale() is True

    def test_foreign_host_fresh_lock_not_stale(self, lock_path, now):
        fresh = (now - timedelta(minutes=5)).isoformat()
        write_lock(lock_path, pid=12345, host="some-other-machine", timestamp=fresh)
        lock = make_lock(lock_path, now)
        assert lock.is_stale() is False

    def test_stale_acquire_without_force_raises_lock_stale(self, lock_path, now):
        write_lock(lock_path, pid=99999999, timestamp=now.isoformat())
        lock = make_lock(lock_path, now)
        with pytest.raises(LockStaleError):
            lock.acquire(owner="e29", target="t", profile="p")

    def test_stale_acquire_with_force_succeeds(self, lock_path, now, caplog):
        write_lock(lock_path, pid=99999999, timestamp=now.isoformat())
        lock = make_lock(lock_path, now)
        with caplog.at_level("WARNING", logger="v2ctl.locking"):
            payload = lock.acquire(owner="e29", target="t", profile="p", force=True)
        assert payload["owner"] == "e29"
        assert lock.status()["owner"] == "e29"
        assert "force" in caplog.text.lower()

    def test_missing_status_not_stale(self, lock_path, now):
        assert make_lock(lock_path, now).is_stale() is False

    def test_corrupt_lock_not_stale(self, lock_path, now):
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text("garbage", encoding="utf-8")
        assert make_lock(lock_path, now).is_stale() is False


class TestIdentity:
    def test_host_id_nonempty(self):
        assert DeployLock.host_id()

    def test_lock_dir_is_parent(self, lock_path):
        lock = make_lock(lock_path)
        assert lock.lock_dir() == lock_path.parent
