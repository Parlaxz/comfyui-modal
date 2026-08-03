"""Persistent local owner IPC client for comfyui-modal workers.

Starts a loopback-only JSON-lines owner subprocess
(``sys.executable -m comfymodal_runtime.local_handle_owner``) from the
repository root, recovers stale state files, and proxies
``run_plan_stream`` / ``publish_restore_plan`` with a
``remote_gen.aio(...)``-compatible async iterator.  Never imports Modal and
never pickles Modal clients, Cls handles, or class instances — only the
owner process resolves Modal handles at request time.  Token values are
never printed; decision lines are emitted verbatim as
``[v2.local_handle] decision=<decision>``.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Mapping

# ── Exceptions ──────────────────────────────────────────────────────────────


class PersistentHandleError(RuntimeError):
    """Raised when the owner reports an operation failure."""

    def __init__(self, message: str, *, frame: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.frame = dict(frame) if frame else {}


class PersistentHandleUnavailable(PersistentHandleError):
    """Raised when the owner process cannot be started or reached."""


# ── Stale/deleted handle detection (conservative) ──────────────────────────
# Mirrors the owner's matcher so error frames and local exceptions can be
# classified without importing the owner module or Modal.

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
    ``message`` key.  Matches Modal class names (``NotFound``, ``NOT_FOUND``,
    ...) and deployment/handle vocabulary in the text.
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


# ── Key-to-dict utility ─────────────────────────────────────────────────────


def build_handle_key(
    *,
    workspace_identity: str,
    app_name: str,
    class_name: str,
    deployment_identity: str = "",
    environment: str = "",
    cloud: str = "",
    gpu: str = "",
    token_id: str = "",
) -> dict[str, str]:
    """Build the serializable key dict that addresses owner-cached handles.

    The owner caches class instances by the complete key: workspace identity,
    app name, class name, deployment identity, environment, cloud, GPU and
    token identity.  ``token_id`` is the public token *identity* only — the
    token secret is never part of a key or log.
    """
    return {
        "workspace_identity": str(workspace_identity or ""),
        "app_name": str(app_name or ""),
        "class_name": str(class_name or ""),
        "deployment_identity": str(deployment_identity or ""),
        "environment": str(environment or ""),
        "cloud": str(cloud or ""),
        "gpu": str(gpu or ""),
        "token_id": str(token_id or ""),
    }


def handle_key_to_dict(
    *,
    workspace_identity: str,
    app_name: str,
    class_name: str,
    deployment_identity: str = "",
    environment: str = "",
    cloud: str = "",
    gpu: str = "",
    token_id: str = "",
) -> dict[str, str]:
    """Alias of ``build_handle_key``: the full handle cache key as a dict."""
    return build_handle_key(
        workspace_identity=workspace_identity,
        app_name=app_name,
        class_name=class_name,
        deployment_identity=deployment_identity,
        environment=environment,
        cloud=cloud,
        gpu=gpu,
        token_id=token_id,
    )


# ── State-file helpers ──────────────────────────────────────────────────────


def default_owner_state_path() -> Path:
    """Return the owner state-file path under the local data root.

    Honors ``COMFYMODAL_LOCAL_HANDLE_STATE_FILE`` when set, otherwise
    resolves to ``<data-root>/local-handle/owner.json``.  The parent is
    created lazily by the writer.
    """
    override = os.environ.get("COMFYMODAL_LOCAL_HANDLE_STATE_FILE", "").strip()
    if override:
        return Path(override)
    from local_artifacts import get_local_data_root

    return get_local_data_root() / "local-handle" / "owner.json"


def _default_repo_root() -> Path:
    override = os.environ.get("COMFYMODAL_LOCAL_HANDLE_REPO_ROOT", "").strip()
    if override:
        return Path(override).resolve()
    from local_artifacts import get_plugin_root

    return get_plugin_root()


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


def _read_state(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def _is_pid_alive(pid: int) -> bool:
    if not pid:
        return False
    if os.name == "nt":
        try:
            import ctypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid)
            )
            if not handle:
                return False
            try:
                exit_code = ctypes.c_ulong()
                if ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return exit_code.value == 259  # STILL_ACTIVE
                return False
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


async def _write_json(writer: asyncio.StreamWriter, payload: Mapping[str, Any]) -> None:
    writer.write(json.dumps(payload, default=str, ensure_ascii=False).encode("utf-8") + b"\n")
    await writer.drain()


def _request_secrets(workspace: Mapping[str, Any]) -> tuple[str, ...]:
    """Secret strings to scrub from client-side error text (defense-in-depth;
    the owner already redacts before forwarding)."""
    secrets = [
        str(workspace.get("token_secret", "") or ""),
        str(workspace.get("token_id", "") or ""),
    ]
    return tuple(s for s in secrets if s)


def _redact(message: Any, secrets: tuple[str, ...]) -> str:
    text = str(message)
    for secret in secrets:
        if secret and secret in text:
            text = text.replace(secret, "***")
    return text


# ── Streaming proxy ─────────────────────────────────────────────────────────


class PersistentHandleProxy:
    """``remote_gen.aio(...)``-compatible streaming proxy.

    ``input_id`` / ``input_created_at`` reflect the owner's reported remote
    input identity (when supplied).  Supports ``async for`` and deterministic
    ``await proxy.aclose()``; the socket and the pump task are closed both on
    natural EOF/error and on explicit close.
    """

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        *,
        key: Mapping[str, Any] | None = None,
        secrets: tuple[str, ...] = (),
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._key = dict(key or {})
        self._secrets = tuple(secrets)
        self.input_id = ""
        self.input_created_at: Any = None
        self.decisions: list[str] = []
        self._queue: asyncio.Queue[Any] = asyncio.Queue()
        self._task: asyncio.Task[Any] | None = None
        self._first_frame = asyncio.Event()
        self._done = False

    @property
    def key(self) -> dict[str, Any]:
        return dict(self._key)

    @property
    def last_decision(self) -> str:
        return self.decisions[-1] if self.decisions else ""

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._pump())

    def __aiter__(self) -> "PersistentHandleProxy":
        return self

    async def __anext__(self) -> Any:
        if self._done:
            raise StopAsyncIteration
        item = await self._queue.get()
        if isinstance(item, dict):
            if item.get("__eof__"):
                self._done = True
                raise StopAsyncIteration
            if "__error__" in item:
                self._done = True
                error = item["__error__"] or {}
                raise PersistentHandleError(
                    _redact(
                        f"{error.get('type', 'error')}: {error.get('message', '')}",
                        self._secrets,
                    ),
                    frame=error,
                )
        return item

    def __await__(self) -> Any:
        async def _await_first() -> "PersistentHandleProxy":
            await self._first_frame.wait()
            return self

        return _await_first().__await__()

    async def aclose(self) -> None:
        self._done = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._close_writer()
        try:
            await self._writer.wait_closed()
        except Exception:
            pass

    def _close_writer(self) -> None:
        try:
            self._writer.close()
        except Exception:
            pass

    async def _pump(self) -> None:
        try:
            while not self._done:
                line = await self._reader.readline()
                if not line:
                    await self._queue.put({"__eof__": True})
                    return
                frame = json.loads(line)
                self._handle_frame(frame)
                if frame.get("frame") in ("eof", "error"):
                    return
        except asyncio.CancelledError:
            raise
        except (OSError, ConnectionError, json.JSONDecodeError, asyncio.IncompleteReadError) as exc:
            await self._queue.put({"__error__": {"type": "proxy_read_failed", "message": str(exc)}})
        except Exception as exc:
            await self._queue.put({"__error__": {"type": "proxy_internal", "message": str(exc)}})
        finally:
            self._first_frame.set()
            self._close_writer()

    def _handle_frame(self, frame: Mapping[str, Any]) -> None:
        ftype = frame.get("frame")
        if ftype == "decision":
            decision = str(frame.get("decision", "") or "")
            self.decisions.append(decision)
            print(f"[v2.local_handle] decision={decision}", flush=True)
        elif ftype == "ready":
            if frame.get("input_id"):
                self.input_id = str(frame["input_id"])
            if "input_created_at" in frame and frame["input_created_at"] is not None:
                self.input_created_at = frame["input_created_at"]
        elif ftype == "event":
            self._queue.put_nowait(frame.get("event"))
        elif ftype == "eof":
            self._queue.put_nowait({"__eof__": True})
        elif ftype == "error":
            self._queue.put_nowait({"__error__": frame.get("error") or {}})
        self._first_frame.set()


# ── Client ──────────────────────────────────────────────────────────────────


class PersistentHandleClient:
    """Manages one loopback owner subprocess and proxies operations.

    The owner is started lazily on first use and reused across calls.  Stale
    state (dead owner pid/port) is recovered by starting a fresh owner.
    """

    def __init__(
        self,
        *,
        repo_root: str | os.PathLike | None = None,
        state_path: str | os.PathLike | None = None,
        auth_token: str = "",
        start_timeout: float = 30.0,
        connect_timeout: float = 10.0,
    ) -> None:
        self._repo_root = Path(repo_root) if repo_root else _default_repo_root()
        self._state_path = Path(state_path) if state_path else default_owner_state_path()
        self._auth_token = auth_token or secrets.token_urlsafe(32)
        self._start_timeout = start_timeout
        self._connect_timeout = connect_timeout
        self._owner_process: subprocess.Popen[Any] | None = None
        self._owner_port: int | None = None
        self._owner_ready = False
        self._owner_ready_announced = False
        self._start_lock = asyncio.Lock()

    # -- lifecycle ----------------------------------------------------------

    async def _ensure_owner(self) -> None:
        if self._owner_ready:
            return
        async with self._start_lock:
            if self._owner_ready:
                return
            state = _read_state(self._state_path)
            if state is not None:
                port = state.get("port")
                token = str(state.get("auth_token", "") or "")
                if port and await self._try_connect_ok(int(port), token):
                    self._auth_token = token
                    self._owner_port = int(port)
                    self._owner_ready = True
                    self._announce_owner_ready(state.get("pid"))
                    return
            await self._start_owner()

    def _announce_owner_ready(self, pid: Any) -> None:
        """Print the one-time, non-secret readiness line for first-run logs."""
        if self._owner_ready_announced:
            return
        self._owner_ready_announced = True
        print(f"[v2.local_handle] owner_ready pid={pid}", flush=True)

    async def _start_owner(self) -> None:
        token = self._auth_token
        self._owner_ready_announced = False
        _atomic_write_json(self._state_path, {
            "schema_version": 1,
            "status": "starting",
            "auth_token": token,
            "pid": None,
            "port": None,
            "started_at": time.time(),
        })
        env = dict(os.environ)
        env["COMFYMODAL_LOCAL_HANDLE_AUTH_TOKEN"] = token
        env["COMFYMODAL_LOCAL_HANDLE_STATE_FILE"] = str(self._state_path)
        env["COMFYMODAL_LOCAL_HANDLE_REPO_ROOT"] = str(self._repo_root)
        self._terminate_owner()
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            # stdin=DEVNULL (not PIPE): the owner must not depend on a parent
            # pipe for its lifetime, so it survives the parent benchmark
            # process exiting and can serve a later run_v2_single.bat.
            self._owner_process = subprocess.Popen(
                [sys.executable, "-m", "comfymodal_runtime.local_handle_owner"],
                cwd=str(self._repo_root),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise PersistentHandleUnavailable(f"failed to start local handle owner: {exc}") from exc
        deadline = time.monotonic() + self._start_timeout
        while time.monotonic() < deadline:
            state = _read_state(self._state_path)
            if state is not None and state.get("status") == "ready" and state.get("port"):
                port = int(state["port"])
                state_token = str(state.get("auth_token", "") or "")
                if await self._try_connect_ok(port, state_token):
                    if state_token != token:
                        # Another client won the state race — adopt its owner.
                        self._terminate_owner()
                        self._auth_token = state_token
                    self._owner_port = port
                    self._owner_ready = True
                    self._announce_owner_ready(state.get("pid"))
                    return
            await asyncio.sleep(0.1)
        self._terminate_owner()
        raise PersistentHandleUnavailable(
            f"local handle owner did not become ready within {self._start_timeout}s"
        )

    async def _try_connect_ok(self, port: int, token: str) -> bool:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", port),
                timeout=self._connect_timeout,
            )
        except (OSError, asyncio.TimeoutError):
            return False
        try:
            await _write_json(writer, {"op": "ping", "auth": token})
            line = await asyncio.wait_for(reader.readline(), timeout=self._connect_timeout)
            if not line:
                return False
            frame = json.loads(line)
            return frame.get("frame") == "pong"
        except (OSError, asyncio.TimeoutError, json.JSONDecodeError):
            return False
        finally:
            try:
                writer.close()
            except Exception:
                pass

    def _terminate_owner(self) -> None:
        proc = self._owner_process
        self._owner_process = None
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def shutdown(self) -> None:
        """Terminate the owned owner subprocess (best-effort)."""
        self._terminate_owner()
        self._owner_ready = False
        self._owner_ready_announced = False
        self._owner_port = None

    # -- operations ---------------------------------------------------------

    @staticmethod
    def _ensure_token_id_in_key(
        key: Mapping[str, Any], workspace: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Return the key with the workspace token identity included.

        Includes only the public token *identity* (``token_id``) so the
        owner's handle cache is scoped per token; the token secret is never
        placed in a key.
        """
        normalized = dict(key or {})
        token_id = str((workspace or {}).get("token_id", "") or "")
        if token_id and not normalized.get("token_id"):
            normalized["token_id"] = token_id
        return normalized

    async def run_plan_stream(
        self,
        key: Mapping[str, Any],
        workspace: Mapping[str, Any],
        payload: Mapping[str, Any],
        *,
        request_id: str = "",
        gpu: Any = None,
    ) -> PersistentHandleProxy:
        """Open a streaming run against the owned handle.

        Returns a ``PersistentHandleProxy`` exposing ``input_id`` /
        ``input_created_at`` (when supplied by the owner) and supporting
        ``async for``.  Close deterministically with ``await proxy.aclose()``.
        """
        await self._ensure_owner()
        key = self._ensure_token_id_in_key(key, workspace)
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", self._owner_port),
                timeout=self._connect_timeout,
            )
        except (OSError, asyncio.TimeoutError) as exc:
            raise PersistentHandleUnavailable(
                f"cannot connect to local handle owner: {exc}"
            ) from exc
        proxy = PersistentHandleProxy(
            reader, writer, key=dict(key), secrets=_request_secrets(workspace)
        )
        try:
            await _write_json(writer, {
                "op": "run_plan_stream",
                "auth": self._auth_token,
                "key": dict(key),
                "workspace": dict(workspace),
                "payload": dict(payload),
                "request_id": str(request_id or ""),
                "gpu": gpu,
            })
            proxy.start()
        except Exception:
            await proxy.aclose()
            raise
        return proxy

    async def publish_restore_plan(
        self,
        key: Mapping[str, Any],
        workspace: Mapping[str, Any],
        payload: Mapping[str, Any],
        *,
        snapshot_seed: Mapping[str, Any] | None = None,
        gpu: Any = None,
        request_id: str = "",
    ) -> Any:
        """One-shot ``publish_restore_plan`` against the owned handle.

        Awaitable; returns the authoritative publication result.  The owner
        retries publish once on a stale/deleted handle error.
        """
        await self._ensure_owner()
        key = self._ensure_token_id_in_key(key, workspace)
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", self._owner_port),
                timeout=self._connect_timeout,
            )
        except (OSError, asyncio.TimeoutError) as exc:
            raise PersistentHandleUnavailable(
                f"cannot connect to local handle owner: {exc}"
            ) from exc
        try:
            await _write_json(writer, {
                "op": "publish_restore_plan",
                "auth": self._auth_token,
                "key": dict(key),
                "workspace": dict(workspace),
                "payload": dict(payload),
                "snapshot_seed": dict(snapshot_seed) if snapshot_seed else None,
                "gpu": gpu,
                "request_id": str(request_id or ""),
            })
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=self._connect_timeout)
                if not line:
                    raise PersistentHandleUnavailable(
                        "owner closed the connection before a result"
                    )
                frame = json.loads(line)
                ftype = frame.get("frame")
                if ftype == "decision":
                    print(f"[v2.local_handle] decision={frame.get('decision', '')}", flush=True)
                elif ftype == "result":
                    return frame.get("result")
                elif ftype == "error":
                    error = frame.get("error") or {}
                    raise PersistentHandleError(
                        _redact(
                            f"publish_restore_plan failed: "
                            f"{error.get('type', 'unknown')}: {error.get('message', '')}",
                            _request_secrets(workspace),
                        ),
                        frame=error,
                    )
        except asyncio.TimeoutError as exc:
            raise PersistentHandleError(f"publish_restore_plan timed out: {exc}") from exc
        except (json.JSONDecodeError, ConnectionError, OSError) as exc:
            raise PersistentHandleError(f"publish_restore_plan read failed: {exc}") from exc
        finally:
            try:
                writer.close()
            except Exception:
                pass


# ── Default singleton ───────────────────────────────────────────────────────

_default_client: PersistentHandleClient | None = None
_default_client_lock = threading.Lock()


def get_default_handle_client() -> PersistentHandleClient:
    """Return a module-level singleton ``PersistentHandleClient``.

    Lazily initialised on first call; concurrent callers share the same
    client (and therefore the same owner subprocess).
    """
    global _default_client
    if _default_client is not None:
        return _default_client
    with _default_client_lock:
        if _default_client is None:
            _default_client = PersistentHandleClient()
    return _default_client


__all__ = [
    "PersistentHandleClient",
    "PersistentHandleError",
    "PersistentHandleProxy",
    "PersistentHandleUnavailable",
    "build_handle_key",
    "default_owner_state_path",
    "get_default_handle_client",
    "handle_key_to_dict",
    "is_stale_handle_error",
]
