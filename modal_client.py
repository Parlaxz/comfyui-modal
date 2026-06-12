import asyncio
import functools
import os
from collections.abc import Callable

import modal

from gpu_catalog import (
    DEFAULT_GPU,
    GPU_CATALOG,
    GPU_BY_VALUE,
    get_available_gpu_options,
    get_default_gpu,
    get_supported_gpus,
    is_gpu_hidden,
    normalize_gpu_value,
)

APP_NAME = os.environ.get("COMFYMODAL_APP_NAME", "comfyui").strip() or "comfyui"

# Client-side backpressure: only one in-flight prompt execution at a time
_run_prompt_semaphore = asyncio.Semaphore(1)

# Per-workspace caches — populated lazily on first use per workspace.
# Key: workspace["id"] for clients, (workspace["id"], name) for function handles,
# (workspace["id"], gpu_value) for Cls instances.
_workspace_resolver: Callable[[], dict | None] | None = None
_workspace_clients: dict[str, object] = {}
_workspace_function_handles: dict[tuple[str, str], object] = {}
_workspace_cls_instances: dict[tuple[str, str], object] = {}
_current_gpu = DEFAULT_GPU
_handle_cache_hits = 0
_handle_cache_misses = 0


# ── Workspace helpers ────────────────────────────────────────────────────


def set_workspace_resolver(resolver: Callable[[], dict | None] | None):
    """Install a callable that returns the currently active workspace dict.

    The resolver is invoked every time one of the public API functions is
    called *without* an explicit ``workspace=`` kwarg.  It should return a
    dict with keys ``id``, ``token_id``, ``token_secret``, or ``None`` if
    no workspace is available.
    """
    global _workspace_resolver
    _workspace_resolver = resolver


def _resolve_workspace(workspace: dict | None) -> dict:
    """Return a valid workspace dict, either from the caller or the resolver."""
    candidate = workspace or (_workspace_resolver() if _workspace_resolver else None)
    if not candidate:
        raise RuntimeError("No active Modal workspace selected")
    if not candidate.get("token_id") or not candidate.get("token_secret"):
        raise RuntimeError("Active Modal workspace is missing credentials")
    return candidate


def _workspace_client(workspace: dict):
    """Return (and cache) a ``modal.Client`` for the given workspace."""
    key = workspace["id"]
    client = _workspace_clients.get(key)
    if client is None:
        client = modal.Client.from_credentials(workspace["token_id"], workspace["token_secret"])
        _workspace_clients[key] = client
    return client


def _workspace_function(name: str, workspace: dict):
    """Return (and cache) a ``modal.Function`` handle scoped to *workspace*."""
    global _handle_cache_hits, _handle_cache_misses
    key = (workspace["id"], name)
    handle = _workspace_function_handles.get(key)
    if handle is None:
        _handle_cache_misses += 1
        handle = modal.Function.from_name(APP_NAME, name, client=_workspace_client(workspace))
        _workspace_function_handles[key] = handle
    else:
        _handle_cache_hits += 1
    return handle


def _workspace_api(workspace: dict, gpu: str | None = None):
    """Return (and cache) a GPU-class Cls instance scoped to *workspace*.

    If *gpu* is ``None`` the module-level ``_current_gpu`` is used.
    """
    global _handle_cache_hits, _handle_cache_misses
    selected_gpu = _current_gpu if gpu is None else normalize_gpu_value(gpu)
    entry = GPU_BY_VALUE.get(selected_gpu)
    if entry is None:
        raise ValueError(f"Unsupported GPU: {selected_gpu}")
    key = (workspace["id"], selected_gpu)
    instance = _workspace_cls_instances.get(key)
    if instance is None:
        _handle_cache_misses += 1
        cls_handle = modal.Cls.from_name(APP_NAME, entry["class_name"], client=_workspace_client(workspace))
        instance = cls_handle()
        _workspace_cls_instances[key] = instance
    else:
        _handle_cache_hits += 1
    return instance


# ── Existing public helpers (unchanged except set_gpu validation) ─────────


def get_modal_app_name() -> str:
    return APP_NAME


def get_modal_class_name(gpu: str | None = None) -> str:
    selected_gpu = _current_gpu if gpu is None else normalize_gpu_value(gpu)
    entry = GPU_BY_VALUE.get(selected_gpu)
    if entry is None:
        raise ValueError(f"Unsupported GPU: {selected_gpu}")
    return entry["class_name"]


def get_modal_lookup_target(gpu: str | None = None, method_name: str = "run_prompt") -> str:
    return f"{APP_NAME}.{get_modal_class_name(gpu)}.{method_name}"


def get_handle_cache_stats() -> dict:
    return {"hits": _handle_cache_hits, "misses": _handle_cache_misses}


def set_gpu(gpu: str):
    global _current_gpu
    normalized = normalize_gpu_value(gpu)
    if normalized not in GPU_BY_VALUE:
        raise ValueError(f"Unsupported GPU: {normalized}")
    _current_gpu = normalized


def get_gpu() -> str:
    return _current_gpu


def get_available_gpus() -> list[dict[str, str]]:
    return get_available_gpu_options()


def clear_cache():
    """Clear all per-workspace caches so subsequent requests use fresh handles."""
    global _handle_cache_hits, _handle_cache_misses
    _workspace_clients.clear()
    _workspace_function_handles.clear()
    _workspace_cls_instances.clear()
    _handle_cache_hits = 0
    _handle_cache_misses = 0


# ── Error-handler decorator ──────────────────────────────────────────────


def _modal_error_handler(func):
    """Decorator that catches common exceptions and re-raises with user-friendly messages."""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except TimeoutError as e:
            raise TimeoutError(
                "Modal request timed out. The container may be cold-starting (1-3 min)."
            ) from e
        except (ConnectionError, OSError) as e:
            raise ConnectionError(
                "Modal connection failed. Check your internet connection and Modal token."
            ) from e
        except Exception as e:
            if getattr(type(e), "__module__", "").startswith("modal"):
                raise RuntimeError(
                    f"Modal error: {e}. Try redeploying with the Deploy button."
                ) from e
            raise
    return wrapper


# ── Public async API (all accept optional workspace kwarg) ───────────────


@_modal_error_handler
async def run_prompt(
    workflow: dict,
    input_images: dict | None = None,
    trace: dict | None = None,
    gpu: str | None = None,
    modal_options: dict | None = None,
    workspace: dict | None = None,
) -> dict:
    selected = _resolve_workspace(workspace)
    async with _run_prompt_semaphore:
        return await asyncio.to_thread(
            lambda: _workspace_api(selected, gpu).run_prompt.remote(
                workflow, input_images or {}, trace or {}, modal_options or {},
            ),
        )


# NOTE: no @_modal_error_handler here — that decorator does `await func()`
# which breaks async generator functions.  Error handling is inline.
async def run_prompt_stream(
    workflow: dict,
    input_images: dict | None = None,
    trace: dict | None = None,
    gpu: str | None = None,
    modal_options: dict | None = None,
    workspace: dict | None = None,
):
    """Execute workflow on Modal and stream progress events back to the caller.

    Yields dicts with types:
      ``{"type": "status", "message": "..."}`` — startup/restore phase.
      ``{"type": "progress", "event": "...", "data": {...}}`` — ComfyUI events.
      ``{"type": "result", "data": {...}}`` — final result (last yield).
      ``{"type": "error", "message": "..."}`` — fatal error.
    """
    selected = _resolve_workspace(workspace)
    async with _run_prompt_semaphore:
        try:
            gen = _workspace_api(selected, gpu).run_prompt_stream.remote_gen.aio(
                workflow, input_images or {}, trace or {}, modal_options or {},
            )
            async for msg in gen:
                yield msg
        except TimeoutError:
            raise TimeoutError(
                "Modal request timed out. The container may be cold-starting (1-3 min)."
            )
        except (ConnectionError, OSError) as e:
            raise ConnectionError(
                "Modal connection failed. Check your internet connection and Modal token."
            ) from e
        except Exception as e:
            if getattr(type(e), "__module__", "").startswith("modal"):
                raise RuntimeError(
                    f"Modal error: {e}. Try redeploying with the Deploy button."
                ) from e
            raise


@_modal_error_handler
async def get_object_info(workspace: dict | None = None) -> dict:
    selected = _resolve_workspace(workspace)
    return await asyncio.to_thread(lambda: _workspace_api(selected).object_info.remote())


@_modal_error_handler
async def health_check(workspace: dict | None = None) -> dict:
    selected = _resolve_workspace(workspace)
    return await asyncio.to_thread(lambda: _workspace_function("health_cpu", selected).remote())


@_modal_error_handler
async def download_model(
    url: str,
    filename: str,
    save_path: str = "checkpoints",
    hf_token: str = "",
    civitai_token: str = "",
    workspace: dict | None = None,
) -> dict:
    selected = _resolve_workspace(workspace)
    kwargs = dict(url=url, filename=filename, save_path=save_path, hf_token=hf_token)
    if civitai_token:
        kwargs["civitai_token"] = civitai_token
    return await asyncio.to_thread(
        lambda: _workspace_function("download_model_to_volume", selected).remote(**kwargs),
    )


async def download_model_stream(
    url: str,
    filename: str,
    save_path: str = "checkpoints",
    hf_token: str = "",
    civitai_token: str = "",
    workspace: dict | None = None,
):
    """Async generator yielding progress dicts from a Modal streaming download."""
    selected = _resolve_workspace(workspace)
    kwargs = dict(url=url, filename=filename, save_path=save_path, hf_token=hf_token)
    if civitai_token:
        kwargs["civitai_token"] = civitai_token
    loop = asyncio.get_running_loop()
    gen = await loop.run_in_executor(
        None,
        lambda: _workspace_function("download_model_stream", selected).remote_gen(**kwargs),
    )
    while True:
        try:
            item = await loop.run_in_executor(None, next, gen)
            yield item
        except StopIteration:
            break


@_modal_error_handler
async def batch_download_models(
    items: list,
    hf_token: str = "",
    civitai_token: str = "",
    workspace: dict | None = None,
) -> list:
    selected = _resolve_workspace(workspace)
    kwargs = dict(hf_token=hf_token)
    if civitai_token:
        kwargs["civitai_token"] = civitai_token
    return await asyncio.to_thread(
        lambda: _workspace_function("batch_download_models", selected).remote(items, **kwargs),
    )


@_modal_error_handler
async def list_models(workspace: dict | None = None) -> dict:
    selected = _resolve_workspace(workspace)
    return await asyncio.to_thread(lambda: _workspace_function("list_models_cpu", selected).remote())


@_modal_error_handler
async def delete_model(folder: str, filename: str, workspace: dict | None = None) -> dict:
    selected = _resolve_workspace(workspace)
    return await asyncio.to_thread(
        lambda: _workspace_function("delete_model_cpu", selected).remote(folder=folder, filename=filename),
    )


@_modal_error_handler
async def sync_custom_nodes(archive_data: bytes, workspace: dict | None = None) -> dict:
    selected = _resolve_workspace(workspace)
    return await asyncio.to_thread(
        lambda: _workspace_function("sync_custom_nodes_to_volume", selected).remote(archive_data),
    )


@_modal_error_handler
async def refresh_custom_nodes(
    expected_nodes: list | None = None,
    workspace: dict | None = None,
) -> dict:
    selected = _resolve_workspace(workspace)
    return await asyncio.to_thread(
        lambda: _workspace_api(selected).refresh_custom_nodes.remote(expected_nodes or []),
    )


@_modal_error_handler
async def get_sync_status(workspace: dict | None = None) -> dict:
    selected = _resolve_workspace(workspace)
    return await asyncio.to_thread(
        lambda: _workspace_function("get_volume_status", selected).remote(),
    )


@_modal_error_handler
async def upload_model_to_volume(
    file_data: bytes,
    folder: str,
    filename: str,
    workspace: dict | None = None,
) -> dict:
    selected = _resolve_workspace(workspace)
    return await asyncio.to_thread(
        lambda: _workspace_function("upload_model_to_volume", selected).remote(file_data, folder, filename),
    )


@_modal_error_handler
async def upload_model_chunk(
    chunk_data: bytes,
    folder: str,
    filename: str,
    offset: int,
    is_last: bool,
    workspace: dict | None = None,
) -> dict:
    selected = _resolve_workspace(workspace)
    return await asyncio.to_thread(
        lambda: _workspace_function("upload_model_chunk", selected).remote(
            chunk_data, folder, filename, offset, is_last,
        ),
    )


@_modal_error_handler
async def resync_runtime(scope: str = "all", workspace: dict | None = None) -> dict:
    selected = _resolve_workspace(workspace)
    return await asyncio.to_thread(lambda: _workspace_api(selected).resync_runtime.remote(scope))


@_modal_error_handler
async def get_runtime_state(workspace: dict | None = None) -> dict:
    """Check runtime state — CPU-only, no GPU needed."""
    selected = _resolve_workspace(workspace)
    return await asyncio.to_thread(lambda: _workspace_function("runtime_state_cpu", selected).remote())


@_modal_error_handler
async def set_active_warmup_profile(payload: dict, workspace: dict | None = None) -> dict:
    selected = _resolve_workspace(workspace)
    return await asyncio.to_thread(
        lambda: _workspace_function("set_active_warmup_profile", selected).remote(payload),
    )
