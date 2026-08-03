"""Long-lived owner subprocess for persistent Modal handle IPC.

Serves authenticated JSON-lines requests over loopback TCP (127.0.0.1 only).
Owns Modal clients and class instances across requests (cached in-process,
never pickled or serialized) and forwards ``run_plan_stream`` generator
events and ``publish_restore_plan`` results as JSON frames.

Run as ``python -m comfymodal_runtime.local_handle_owner`` from the
repository root.  Modal is imported only at handle-resolution time so this
module stays importable in workers that lack the Modal SDK.  Token values
are never printed and are redacted from forwarded error text.
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import os
import re
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Mapping

# ── Protocol frame keys ─────────────────────────────────────────────────────

FRAME_DECISION = "decision"
FRAME_READY = "ready"
FRAME_EVENT = "event"
FRAME_EOF = "eof"
FRAME_RESULT = "result"
FRAME_ERROR = "error"
FRAME_PONG = "pong"

DECISION_MISS_RESOLVED_CACHED = "miss_resolved_cached"
DECISION_PERSISTENT_HIT = "persistent_hit"
DECISION_STALE_RETRY = "stale_retry"

# ── Stale/deleted handle detection (conservative) ──────────────────────────
# Recognized from Modal class names (NotFound, NOT_FOUND, ...) and from
# deployment/handle vocabulary in the error text.  Scoped to Modal-ish
# phrases so ordinary remote errors are not misclassified.

_STALE_CLASS_RE = re.compile(r"(NotFound|NOT_FOUND|Stale|Deleted|Gone)", re.IGNORECASE)
_STALE_TEXT_RE = re.compile(
    r"(?:deployment|handle|function|class|app|object)[^.\n]{0,60}not\s*found|"
    r"no such (?:deployment|handle|function|class|app|object)|"
    r"(?:deployment|handle|function|class|app|object)[^.\n]{0,40}(?:deleted|missing|no longer exists)|"
    r"(?:was|has been) deleted|"
    r"no longer exists|"
    r"not_found",
    re.IGNORECASE,
)


def is_stale_handle_error(exc_or_text: Any) -> bool:
    """Conservatively detect a stale/deleted Modal handle error.

    Accepts an exception, a message string, or an error dict carrying a
    ``message`` key.  Matches Modal class names and deployment/handle
    vocabulary in the text.
    """
    if isinstance(exc_or_text, dict):
        exc_or_text = exc_or_text.get("message", "") or str(exc_or_text)
    if isinstance(exc_or_text, BaseException):
        class_name = type(exc_or_text).__name__
        text = str(exc_or_text)
    else:
        class_name = ""
        text = str(exc_or_text or "")
    if class_name and _STALE_CLASS_RE.search(class_name):
        return True
    return bool(text and _STALE_TEXT_RE.search(text))


# ── Frame/state helpers ─────────────────────────────────────────────────────


def _request_secrets(request: Mapping[str, Any], workspace: Mapping[str, Any]) -> tuple[str, ...]:
    secrets = [
        str(workspace.get("token_secret", "") or ""),
        str(workspace.get("token_id", "") or ""),
        str(request.get("auth", "") or ""),
    ]
    return tuple(s for s in secrets if s)


def _redact(message: Any, secrets: tuple[str, ...]) -> str:
    text = str(message)
    for secret in secrets:
        if secret and secret in text:
            text = text.replace(secret, "***")
    return text


def _error_frame(error_type: str, exc: BaseException, *, secrets: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "frame": FRAME_ERROR,
        "error": {"type": error_type, "message": _redact(str(exc), secrets)},
    }


async def _write_frame(writer: asyncio.StreamWriter, frame: dict[str, Any]) -> None:
    writer.write(json.dumps(frame, default=str, ensure_ascii=False).encode("utf-8") + b"\n")
    await writer.drain()


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".owner-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
        os.replace(tmp, str(path))
    finally:
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except OSError:
            pass


async def _aclose_stream(stream: Any) -> None:
    close = getattr(stream, "aclose", None)
    if close is None:
        return
    try:
        await close()
    except Exception:
        pass


# ── Owner ───────────────────────────────────────────────────────────────────


class LocalHandleOwner:
    """Caches Modal clients and class instances across requests.

    Modal clients are cached by ``(workspace identity, token_id,
    environment)``; class instances by the complete key (workspace identity,
    app name, class name, deployment identity, environment, cloud, gpu,
    token_id).  Handles live only in this process — they are never
    serialized.
    """

    def __init__(self) -> None:
        self._client_cache: dict[tuple[str, ...], Any] = {}
        self._handle_cache: dict[tuple[str, ...], Any] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _client_cache_key(key: Mapping[str, Any], workspace: Mapping[str, Any]) -> tuple[str, ...]:
        return (
            str(key.get("workspace_identity", "")),
            str((workspace or {}).get("token_id", "")),
            str(key.get("environment", "")),
        )

    @staticmethod
    def _handle_cache_key(key: Mapping[str, Any]) -> tuple[str, ...]:
        return (
            str(key.get("workspace_identity", "")),
            str(key.get("app_name", "")),
            str(key.get("class_name", "")),
            str(key.get("deployment_identity", "")),
            str(key.get("environment", "")),
            str(key.get("cloud", "")),
            str(key.get("gpu", "")),
            str(key.get("token_id", "")),
        )

    def _invalidate_handle(self, key: Mapping[str, Any]) -> None:
        with self._lock:
            self._handle_cache.pop(self._handle_cache_key(key), None)

    def _resolve_modal_sync(self, key: Mapping[str, Any], workspace: Mapping[str, Any]) -> tuple[Any, bool]:
        """Return ``(handle, was_cached)``.  Runs off the event loop."""
        client_key = self._client_cache_key(key, workspace)
        handle_key = self._handle_cache_key(key)
        with self._lock:
            cached = self._handle_cache.get(handle_key)
            if cached is not None:
                return cached, True
            client = self._client_cache.get(client_key)
        if client is None:
            client = self._new_client(workspace)
            with self._lock:
                self._client_cache.setdefault(client_key, client)
        handle = self._new_handle(client, key)
        with self._lock:
            self._handle_cache[handle_key] = handle
        return handle, False

    @staticmethod
    def _new_client(workspace: Mapping[str, Any]) -> Any:
        import modal  # only the owner needs Modal, at resolution time

        token_id = str(workspace.get("token_id", "") or "")
        token_secret = str(workspace.get("token_secret", "") or "")
        if not token_id or not token_secret:
            raise ValueError("owner requires workspace token_id and token_secret")
        return modal.Client.from_credentials(token_id, token_secret)

    @staticmethod
    def _new_handle(client: Any, key: Mapping[str, Any]) -> Any:
        import modal

        cls_handle = modal.Cls.from_name(
            str(key.get("app_name", "")),
            str(key.get("class_name", "")),
            client=client,
            environment_name=str(key.get("environment", "") or "") or None,
        )
        return cls_handle()

    async def _resolve_modal(self, key: Mapping[str, Any], workspace: Mapping[str, Any]) -> tuple[Any, bool]:
        return await asyncio.to_thread(self._resolve_modal_sync, key, workspace)

    async def _invalidate_and_reresolve(
        self,
        key: Mapping[str, Any],
        workspace: Mapping[str, Any],
        writer: asyncio.StreamWriter,
        secrets: tuple[str, ...],
    ) -> Any | None:
        """Invalidate the stale handle, resolve exactly once, emit the
        ``stale_retry`` decision.  Returns the new handle or ``None`` when
        re-resolution failed (an error frame was already written)."""
        self._invalidate_handle(key)
        try:
            handle, _ = await self._resolve_modal(key, workspace)
        except Exception as exc:
            await _write_frame(writer, _error_frame("resolve_failed", exc, secrets=secrets))
            return None
        await _write_frame(writer, {"frame": FRAME_DECISION, "decision": DECISION_STALE_RETRY})
        return handle

    async def handle_ping(self, writer: asyncio.StreamWriter) -> None:
        await _write_frame(writer, {"frame": FRAME_PONG})

    async def handle_run_plan_stream(self, request: Mapping[str, Any], writer: asyncio.StreamWriter) -> None:
        key = request.get("key") or {}
        workspace = request.get("workspace") or {}
        payload = request.get("payload") or {}
        request_id = str(request.get("request_id", "") or "")
        secrets = _request_secrets(request, workspace)
        try:
            handle, cached = await self._resolve_modal(key, workspace)
        except Exception as exc:
            await _write_frame(writer, _error_frame("resolve_failed", exc, secrets=secrets))
            return
        await _write_frame(writer, {
            "frame": FRAME_DECISION,
            "decision": DECISION_PERSISTENT_HIT if cached else DECISION_MISS_RESOLVED_CACHED,
        })
        events_sent = 0
        retried = False
        while True:
            stream = None
            try:
                stream = await self._open_plan_stream(handle, payload, request_id)
                await _write_frame(writer, {
                    "frame": FRAME_READY,
                    "input_id": str(getattr(stream, "input_id", "") or ""),
                    "input_created_at": getattr(stream, "input_created_at", None),
                })
                async for event in stream:
                    await _write_frame(writer, {"frame": FRAME_EVENT, "event": event})
                    events_sent += 1
                await _write_frame(writer, {"frame": FRAME_EOF})
                return
            except Exception as exc:
                if is_stale_handle_error(exc) and events_sent == 0 and not retried:
                    handle = await self._invalidate_and_reresolve(key, workspace, writer, secrets)
                    if handle is None:
                        return
                    retried = True
                    continue
                await _write_frame(writer, _error_frame("stream_failed", exc, secrets=secrets))
                return
            finally:
                await _aclose_stream(stream)

    async def handle_publish_restore_plan(self, request: Mapping[str, Any], writer: asyncio.StreamWriter) -> None:
        key = request.get("key") or {}
        workspace = request.get("workspace") or {}
        payload = request.get("payload") or {}
        snapshot_seed = request.get("snapshot_seed")
        secrets = _request_secrets(request, workspace)
        try:
            handle, cached = await self._resolve_modal(key, workspace)
        except Exception as exc:
            await _write_frame(writer, _error_frame("resolve_failed", exc, secrets=secrets))
            return
        await _write_frame(writer, {
            "frame": FRAME_DECISION,
            "decision": DECISION_PERSISTENT_HIT if cached else DECISION_MISS_RESOLVED_CACHED,
        })
        retried = False
        while True:
            try:
                result = await self._publish_restore(handle, payload, snapshot_seed)
                await _write_frame(writer, {"frame": FRAME_RESULT, "result": result})
                return
            except Exception as exc:
                if is_stale_handle_error(exc) and not retried:
                    handle = await self._invalidate_and_reresolve(key, workspace, writer, secrets)
                    if handle is None:
                        return
                    retried = True
                    continue
                await _write_frame(writer, _error_frame("publish_failed", exc, secrets=secrets))
                return

    @staticmethod
    async def _open_plan_stream(handle: Any, payload: Any, request_id: str) -> Any:
        stream = handle.run_plan_stream.remote_gen.aio(payload, request_id=request_id)
        if inspect.isawaitable(stream):
            stream = await stream
        return stream

    @staticmethod
    async def _publish_restore(handle: Any, payload: Any, snapshot_seed: Any) -> Any:
        publish_fn = handle.publish_restore_plan
        remote = getattr(publish_fn, "remote", None)
        if remote is not None and callable(getattr(remote, "aio", None)):
            result = remote.aio(payload, snapshot_seed=snapshot_seed)
        elif inspect.iscoroutinefunction(publish_fn):
            result = publish_fn(payload, snapshot_seed=snapshot_seed)
        else:
            result = await asyncio.to_thread(publish_fn, payload, snapshot_seed=snapshot_seed)
        if inspect.isawaitable(result):
            result = await result
        return result


# ── Server ──────────────────────────────────────────────────────────────────


async def _handle_connection(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    auth_token: str,
    owner: LocalHandleOwner,
) -> None:
    try:
        while True:
            line = await reader.readline()
            if not line:
                return
            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                return
            if not isinstance(request, dict):
                return
            if request.get("auth") != auth_token:
                await _write_frame(writer, _error_frame("auth_failed", RuntimeError("invalid auth token")))
                return
            op = request.get("op")
            if op == "ping":
                await owner.handle_ping(writer)
            elif op == "run_plan_stream":
                await owner.handle_run_plan_stream(request, writer)
            elif op == "publish_restore_plan":
                await owner.handle_publish_restore_plan(request, writer)
            else:
                await _write_frame(
                    writer, _error_frame("unknown_op", RuntimeError(f"unknown operation: {op}"))
                )
    except (asyncio.CancelledError, ConnectionError, OSError):
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def _serve(auth_token: str, state_path: str) -> None:
    owner = LocalHandleOwner()
    server = await asyncio.start_server(
        lambda reader, writer: _handle_connection(reader, writer, auth_token, owner),
        host="127.0.0.1",
        port=0,
    )
    port = server.sockets[0].getsockname()[1]
    if state_path:
        _atomic_write_json(Path(state_path), {
            "schema_version": 1,
            "status": "ready",
            "pid": os.getpid(),
            "port": port,
            "auth_token": auth_token,
            "started_at": time.time(),
        })
    print(f"[v2.local_handle] owner ready pid={os.getpid()} port={port}", flush=True)
    # No stdin EOF watchdog: the owner must not depend on a parent pipe, so it
    # stays alive after the parent benchmark process exits.  It runs until
    # explicitly terminated by a client or replaced by stale recovery.
    async with server:
        await server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="comfymodal_runtime.local_handle_owner")
    parser.add_argument("--auth", default=os.environ.get("COMFYMODAL_LOCAL_HANDLE_AUTH_TOKEN", ""))
    parser.add_argument("--state", default=os.environ.get("COMFYMODAL_LOCAL_HANDLE_STATE_FILE", ""))
    args = parser.parse_args(argv)
    if not args.auth:
        print("[v2.local_handle] owner requires an auth token", file=sys.stderr, flush=True)
        return 2
    try:
        asyncio.run(_serve(args.auth, args.state))
    except KeyboardInterrupt:
        return 0
    return 0


__all__ = [
    "DECISION_MISS_RESOLVED_CACHED",
    "DECISION_PERSISTENT_HIT",
    "DECISION_STALE_RETRY",
    "FRAME_DECISION",
    "FRAME_EOF",
    "FRAME_ERROR",
    "FRAME_EVENT",
    "FRAME_READY",
    "FRAME_RESULT",
    "LocalHandleOwner",
    "is_stale_handle_error",
    "main",
]

if __name__ == "__main__":
    raise SystemExit(main())
