"""Ten proofs for the async exact-conditioning cache persistence contract.

Each test maps 1:1 to a user validation requirement:

  1. ``test_miss_available_before_commit``        — miss conditioning is usable
     before any persistence commit; ``store_entry`` is enqueue-only and the
     foreground never writes files.
  2. ``test_one_batch_commit``                     — N entries coalesce into
     exactly ONE commit (not one per entry).
  3. ``test_lookup_never_reloads``                 — the lookup path performs
     ZERO Volume reloads; only the worker's throttled reload-before-batch runs.
  4. ``test_hits_fully_validated``                 — corruption on disk turns a
     hit into a miss, never a wrong hit.
  5. ``test_stale_only_misses``                    — stale committed state can
     only produce extra misses.
  6. ``test_worker_diag_across_threads``           — worker counters are visible
     to the foreground via ``pop_store_diagnostics``/``latest_lookup_diagnostics``.
  7. ``test_failures_never_fail_generation``       — queue-full / commit-failure /
     reload-failure never raise and fail closed.
  8. ``test_teardown_flush_dirty``                 — flush fires the final commit
     on dirty-but-empty state and adds no extra commit after a clean drain.
  9. ``test_local_only_zero_rpcs``                 — local-only mode performs
     ZERO reload AND commit RPCs while still persisting locally.
 10. ``test_no_lock_across_commit``                — the RLock is never held when
     the commit hook runs (worker batch commit and flush final commit).

Every test that enqueues calls ``flush(timeout=...)`` so the non-daemon
persistence worker can never hang interpreter exit.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from typing import Any

import torch

from comfymodal_runtime.clip_conditioning_cache import (
    ExactConditioningCache,
    _atomic_write,
    _atomic_write_text,
    _merge_entry_context,
    _model_identity_block,
    build_exact_key_components,
    conditioning_cache_key_summary,
    exact_key_digest,
    serialize_conditioning,
)


def _base_ctx(text: str = "a cat", *, workflow_hash: str = "wf1", **overrides) -> dict[str, Any]:
    ctx = {
        "request_id": "async-persist-req",
        "clip_identity": "clip.safetensors",
        "clip_type": "flux",
        "loader_class": "CLIPLoader",
        "filenames": ["clip.safetensors"],
        "weight_dtype": "bf16",
        "compute_dtype": "bfloat16",
        "torch_version": torch.__version__,
        "torch_num_threads": 4,
        "model_generation": "gen1",
        "workflow_hash": workflow_hash,
        "deployment_hash": "dep1",
        "custom_node_generation": "cn1",
        "production_options_hash": "po1",
        "tokenizer_identity": "tok1",
    }
    ctx.update(overrides)
    return ctx


def _entry(text: str = "a cat", role: str = "positive") -> dict[str, Any]:
    return {"text": text, "role": role, "node_class": "CLIPTextEncode", "prompt_input": "text"}


def _value(rows: int = 128, dim: int = 128) -> Any:
    return [[torch.randn(rows, dim), {"pooled": torch.randn(1, dim)}]]


def _new_cache(
    tmp: str,
    *,
    mounted: bool = True,
    max_entries: int = 64,
    max_bytes: int = 512 * 1024 * 1024,
) -> ExactConditioningCache:
    return ExactConditioningCache(
        root_dir=tmp, max_entries=max_entries, max_bytes=max_bytes, mounted=mounted
    )


def _entry_paths(cache: ExactConditioningCache, ctx: dict[str, Any], entry: dict[str, Any]):
    kh = conditioning_cache_key_summary(ctx, [entry])["key_hash"]
    header_path, data_path = cache._entry_paths(kh)
    return kh, header_path, data_path, cache._manifest_path


def _wait_until(predicate, timeout: float = 10.0, interval: float = 0.01) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class TestAsyncPersistenceProofs:

    def test_miss_available_before_commit(self):
        """store_entry returns immediately (enqueue-only) while the worker's
        commit is blocked; no foreground file write; files appear only after
        the worker drains (and after flush)."""
        block = threading.Event()
        commits: list[int] = []

        def blocking_hook():
            commits.append(1)
            block.wait(timeout=15.0)

        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp, mounted=True)
            cache.set_commit_hook(blocking_hook)
            ctx, entry, value = _base_ctx("prompt-1"), _entry("prompt-1"), _value()
            kh, header_path, data_path, _ = _entry_paths(cache, ctx, entry)
            # Hold the RLock so the worker cannot drain between the store
            # call and the assertions — the enqueue must be complete before
            # the commit can even begin, and no foreground write may occur.
            with cache._lock:
                t0 = time.monotonic()
                ok = cache.store_entry(ctx, entry, value)
                enqueue_wall = time.monotonic() - t0
                assert ok is True
                assert enqueue_wall < 0.2, (
                    f"enqueue took {enqueue_wall:.3f}s while the commit is blocked"
                )
                assert not os.path.isfile(header_path), "foreground wrote a header file"
                assert not os.path.isfile(data_path), "foreground wrote a data blob"
            # Worker drains, writes files, then blocks inside the commit hook.
            assert _wait_until(lambda: bool(commits)), "worker never reached the commit hook"
            assert os.path.isfile(header_path) and os.path.isfile(data_path)
            assert len(commits) == 1
            block.set()
            f = cache.flush(timeout=15.0)
            assert f["flush_status"] == "ok"
            assert os.path.isfile(header_path) and os.path.isfile(data_path)

    def test_one_batch_commit(self):
        """N distinct entries coalesce into exactly ONE commit."""
        commits: list[int] = []

        def hook():
            commits.append(1)

        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp, mounted=True)
            cache.set_commit_hook(hook)
            # Enqueue all N while holding the RLock so the worker cannot
            # drain mid-way; one batch must be formed.
            with cache._lock:
                for i in range(5):
                    t = f"prompt-{i}"
                    assert cache.store_entry(_base_ctx(t), _entry(t), _value(64, 64)) is True
                assert len(commits) == 0, (
                    "worker cannot have committed while the RLock is held"
                )
            assert _wait_until(
                lambda: cache._worker_diag.get("persisted", 0) >= 5
            ), "batch was never persisted"
            assert len(commits) == 1, f"expected exactly 1 commit, got {len(commits)}"
            diag = cache.pop_store_diagnostics()
            assert diag.get("persisted") == 5, diag
            assert diag.get("batch_size") == 5, diag
            assert diag.get("batch_count") >= 1
            f = cache.flush(timeout=15.0)
            assert f["flush_status"] == "ok"
            assert len(commits) == 1, "flush must not add a second commit when not dirty"

    def test_lookup_never_reloads(self):
        """The lookup path performs ZERO Volume reloads; only the worker's
        throttled reload-before-batch runs (at most once per interval)."""
        reloads: list[int] = []

        def reload_hook():
            reloads.append(1)

        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp, mounted=True)
            cache.set_reload_hook(reload_hook)
            hits, misses, hc, mc = cache.lookup_many(_base_ctx("a"), [_entry("a")])
            assert (hc, mc) == (0, 1)
            assert len(reloads) == 0, f"lookup triggered reloads: {len(reloads)}"
            hits, misses, hc, mc = cache.lookup_many(_base_ctx("b"), [_entry("b")])
            assert (hc, mc) == (0, 1)
            assert len(reloads) == 0, f"lookup triggered reloads: {len(reloads)}"
            ldiag = cache.latest_lookup_diagnostics()
            assert abs(ldiag.get("volume_reload_ms", 1.0)) < 0.001, ldiag
            # Worker reload-before-batch: at most one (throttled) reload.
            assert cache.store_entry(_base_ctx("c"), _entry("c"), _value(64, 64)) is True
            assert _wait_until(lambda: cache._worker_diag.get("persisted", 0) >= 1)
            time.sleep(0.2)
            assert 0 <= len(reloads) <= 1, reloads
            cache.flush(timeout=15.0)

    def test_hits_fully_validated(self):
        """A stored entry hits with identical tensor values; corruption on
        disk turns the hit into a miss — never a wrong hit."""
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp, mounted=True)
            ctx, entry, value = _base_ctx("hit-me"), _entry("hit-me"), _value(128, 128)
            assert cache.store_entry(ctx, entry, value) is True
            cache.flush(timeout=15.0)
            hits, misses, hc, mc = cache.lookup_many(ctx, [entry])
            assert (hc, mc) == (1, 0), (hc, mc)
            got = hits[0]
            assert isinstance(got, list) and got
            cond, meta = got[0]
            assert isinstance(cond, torch.Tensor)
            assert torch.equal(cond, value[0][0]), "conditioning tensor mismatch"
            pooled = meta.get("pooled")
            assert pooled is not None and isinstance(pooled, torch.Tensor)
            assert torch.equal(pooled, value[0][1].get("pooled")), "pooled tensor mismatch"
            # Corrupt the on-disk data blob -> full validation must miss.
            _, header_path, data_path, _ = _entry_paths(cache, ctx, entry)
            with open(data_path, "wb") as f:
                f.write(b"\x00" * os.path.getsize(data_path))
            hits, misses, hc, mc = cache.lookup_many(ctx, [entry])
            assert (hc, mc) == (0, 1), "corrupted payload must never be served"

    def test_stale_only_misses(self):
        """A valid entry committed by another container (seeded directly on
        disk, bypassing the queue) can only cause extra misses — never a
        wrong hit — and the queue path still hits after flush."""
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp, mounted=True)
            # Seed a fully valid entry DIRECTLY on disk + manifest, simulating
            # another container's committed state for a DIFFERENT key.
            seed_ctx = _base_ctx("stale text", workflow_hash="wf-stale")
            # Build the seed digest from the SAME merged context a lookup
            # computes, so the seeded entry is a fully valid cross-container hit.
            seed_merged = _merge_entry_context(seed_ctx, _entry("stale text"))
            seed_components = build_exact_key_components(seed_merged)
            seed_digest = exact_key_digest(seed_components)
            header, data = serialize_conditioning(_value(64, 64))
            assert header is not None
            header["key_hash"] = seed_digest
            header["key_components"] = seed_components
            header["model_identity"] = _model_identity_block(seed_components)
            header["created_at"] = time.time()
            hp, dp = cache._entry_paths(seed_digest)
            _atomic_write(dp, data)
            _atomic_write_text(hp, json.dumps(header, sort_keys=True, separators=(",", ":")))
            cache._write_manifest_atomic({
                "schema_version": 1,
                "format_version": 1,
                "next_seq": 1,
                "entries": [{
                    "key_hash": seed_digest,
                    "byte_length": len(data),
                    "last_access_seq": 1,
                    "created_at": time.time(),
                }],
            })
            # A key differing in ONE component must miss: stale state only
            # produces extra misses, never a wrong hit.
            near_ctx = _base_ctx("stale text", workflow_hash="wf-other")
            hits, misses, hc, mc = cache.lookup_many(near_ctx, [_entry("stale text")])
            assert (hc, mc) == (0, 1), "stale entry must never satisfy a different key"
            # The seeded entry itself IS valid cross-container state -> hit.
            hits, misses, hc, mc = cache.lookup_many(seed_ctx, [_entry("stale text")])
            assert (hc, mc) == (1, 0)
            # Store the near key through the queue; after flush it hits.
            assert cache.store_entry(near_ctx, _entry("stale text"), _value(64, 64)) is True
            cache.flush(timeout=15.0)
            hits, misses, hc, mc = cache.lookup_many(near_ctx, [_entry("stale text")])
            assert (hc, mc) == (1, 0)

    def test_worker_diag_across_threads(self):
        """Worker counters (persisted/batch_count/batch_size/commit_ms) are
        visible to the foreground through ``pop_store_diagnostics``, and the
        lookup diag is readable through ``latest_lookup_diagnostics``."""
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp, mounted=True)
            ctx, entry, value = _base_ctx("diag"), _entry("diag"), _value(64, 64)
            assert cache.store_entry(ctx, entry, value) is True
            cache.flush(timeout=15.0)
            diag = cache.pop_store_diagnostics()
            for key in (
                "persisted", "batch_count", "batch_size", "commit_ms",
                "enqueued", "file_write_ms", "manifest_ms", "store_calls",
                "serialization_ms", "enqueue_ms", "total_ms",
            ):
                assert key in diag, f"missing diag key {key!r} in {sorted(diag)}"
            assert diag["persisted"] >= 1
            assert diag["batch_count"] >= 1
            hits, misses, hc, mc = cache.lookup_many(ctx, [entry])
            assert (hc, mc) == (1, 0)
            ldiag = cache.latest_lookup_diagnostics()
            assert ldiag.get("hit_count", 0) == 1
            assert "volume_reload_ms" in ldiag

    def test_failures_never_fail_generation(self):
        # (a) Queue full -> fail closed (False), never raise; queued entry still persists.
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp, mounted=True)
            cache._max_queue = 1
            with cache._lock:
                assert cache.store_entry(_base_ctx("f1"), _entry("f1"), _value(32, 32)) is True
                assert cache.store_entry(_base_ctx("f2"), _entry("f2"), _value(32, 32)) is False
            assert cache.last_store_reason == "queue_full"
            cache.flush(timeout=15.0)
            assert cache._worker_diag.get("persisted", 0) == 1
        # (b) Commit hook raises -> store_entry still True, flush never raises.
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp, mounted=True)

            def failing_hook():
                raise RuntimeError("simulated commit failure")

            cache.set_commit_hook(failing_hook)
            assert cache.store_entry(_base_ctx("g"), _entry("g"), _value(32, 32)) is True
            f = cache.flush(timeout=15.0)
            assert f["flush_status"] == "ok"
            diag = cache.pop_store_diagnostics()
            assert diag.get("commit_failed", 0) >= 1
        # (c) Reload hook raises -> lookups still return misses, never raise.
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp, mounted=True)

            def failing_reload():
                raise RuntimeError("simulated reload failure")

            cache.set_reload_hook(failing_reload)
            hits, misses, hc, mc = cache.lookup_many(_base_ctx("r"), [_entry("r")])
            assert (hc, mc) == (0, 1)

    def test_teardown_flush_dirty(self):
        # Dirty-but-empty queue: the worker wrote files + manifest and set
        # _dirty_since_commit, but its commit failed.  flush must fire the
        # final explicit commit (backstop) and report status ok.
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp, mounted=True)
            commit_calls: list[int] = []
            block = threading.Event()

            def flaky_hook():
                commit_calls.append(1)
                block.wait(timeout=15.0)
                raise RuntimeError("simulated commit failure")

            cache.set_commit_hook(flaky_hook)
            ctx, entry, value = _base_ctx("dirty"), _entry("dirty"), _value(32, 32)
            assert cache.store_entry(ctx, entry, value) is True
            _, header_path, data_path, _ = _entry_paths(cache, ctx, entry)
            assert _wait_until(lambda: bool(commit_calls)), "worker never reached the commit hook"
            assert os.path.isfile(header_path) and os.path.isfile(data_path)
            assert cache._dirty_since_commit is True
            block.set()  # worker's batch commit now fails -> dirty stays True
            time.sleep(0.3)  # let the worker fail and settle idle
            before = len(commit_calls)
            f = cache.flush(timeout=15.0)
            assert f["flush_status"] == "ok"
            assert len(commit_calls) > before, (
                "flush must fire the final commit when the mount is dirty"
            )
        # Queue-drain case: enqueue while holding the RLock (one batch), the
        # worker drains and commits exactly once; flush adds no extra commit.
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp, mounted=True)
            commit_calls: list[int] = []

            def hook():
                commit_calls.append(1)

            cache.set_commit_hook(hook)
            with cache._lock:
                for i in range(3):
                    t = f"drain-{i}"
                    assert cache.store_entry(_base_ctx(t), _entry(t), _value(32, 32)) is True
            assert _wait_until(lambda: cache._worker_diag.get("persisted", 0) >= 3)
            time.sleep(0.2)
            assert len(commit_calls) == 1, (
                f"exactly one batch commit expected, got {len(commit_calls)}"
            )
            before = len(commit_calls)
            f = cache.flush(timeout=15.0)
            assert f["flush_status"] == "ok"
            assert len(commit_calls) == before, "flush must not add a commit when not dirty"

    def test_local_only_zero_rpcs(self):
        """Local-only (unmounted) mode: ZERO reload and ZERO commit RPCs even
        with hooks registered; entries still persist to local disk and hit."""
        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp, mounted=False)
            reloads: list[int] = []
            commits: list[int] = []
            cache.set_reload_hook(lambda: reloads.append(1))
            cache.set_commit_hook(lambda: commits.append(1))
            ctx, entry, value = _base_ctx("local"), _entry("local"), _value(32, 32)
            assert cache.store_entry(ctx, entry, value) is True
            cache.lookup_many(ctx, [entry])
            cache.flush(timeout=15.0)
            assert len(reloads) == 0, f"local-only issued reloads: {len(reloads)}"
            assert len(commits) == 0, f"local-only issued commits: {len(commits)}"
            _, header_path, data_path, _ = _entry_paths(cache, ctx, entry)
            assert os.path.isfile(header_path) and os.path.isfile(data_path), (
                "local-only must persist files to local disk"
            )
            hits, misses, hc, mc = cache.lookup_many(ctx, [entry])
            assert (hc, mc) == (1, 0)

    def test_no_lock_across_commit(self):
        """The RLock is never held when the commit hook runs — verified for
        the worker batch commit, the worker final commit, and the flush final
        commit via the CPython ``_is_owned()`` probe."""
        probes: list[dict[str, Any]] = []

        def probing_hook():
            probes.append({
                "is_owned": cache._lock._is_owned(),
                "owner": getattr(cache._lock, "_owner", None),
            })
            raise RuntimeError("force dirty so the flush final commit also runs")

        with tempfile.TemporaryDirectory() as tmp:
            cache = _new_cache(tmp, mounted=True)
            cache.set_commit_hook(probing_hook)
            assert cache.store_entry(_base_ctx("lock"), _entry("lock"), _value(32, 32)) is True
            cache.flush(timeout=15.0)
        assert len(probes) >= 2, (
            f"expected worker batch commit + flush final commit probes, got {len(probes)}"
        )
        for probe in probes:
            assert probe["is_owned"] is False, f"RLock held across commit: {probe}"
