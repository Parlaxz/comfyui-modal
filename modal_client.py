import asyncio
import functools
import modal

from gpu_catalog import (
    DEFAULT_GPU,
    GPU_CATALOG,
    get_available_gpu_options,
    get_default_gpu,
    get_supported_gpus,
    is_gpu_hidden,
    normalize_gpu_value,
)

# Client-side backpressure: only one in-flight prompt execution at a time
_run_prompt_semaphore = asyncio.Semaphore(1)

# Build API handles only for GPUs that are NOT hidden
_apis = {
    entry["value"]: modal.Cls.from_name("comfyui", entry["class_name"])
    for entry in GPU_CATALOG
    if not is_gpu_hidden(entry["value"])
}
_download_fn = modal.Function.from_name("comfyui", "download_model_to_volume")
_download_stream_fn = modal.Function.from_name("comfyui", "download_model_stream")
_batch_download_fn = modal.Function.from_name("comfyui", "batch_download_models")
_sync_custom_nodes_fn = modal.Function.from_name("comfyui", "sync_custom_nodes_to_volume")
_get_volume_status_fn = modal.Function.from_name("comfyui", "get_volume_status")
_upload_model_fn = modal.Function.from_name("comfyui", "upload_model_to_volume")
_upload_model_chunk_fn = modal.Function.from_name("comfyui", "upload_model_chunk")
_set_active_warmup_profile_fn = modal.Function.from_name("comfyui", "set_active_warmup_profile")

_list_models_fn = modal.Function.from_name("comfyui", "list_models_cpu")
_delete_model_fn = modal.Function.from_name("comfyui", "delete_model_cpu")
_health_fn = modal.Function.from_name("comfyui", "health_cpu")
_runtime_state_fn = modal.Function.from_name("comfyui", "runtime_state_cpu")

_current_gpu = DEFAULT_GPU
_api_instances = {}
_handle_cache_hits = 0
_handle_cache_misses = 0


def get_handle_cache_stats() -> dict:
    return {"hits": _handle_cache_hits, "misses": _handle_cache_misses}


def set_gpu(gpu: str):
    global _current_gpu
    normalized = normalize_gpu_value(gpu)
    if normalized not in _apis:
        raise ValueError(f"Unsupported GPU: {normalized}")
    _current_gpu = normalized


def get_gpu() -> str:
    return _current_gpu


def get_available_gpus() -> list[dict[str, str]]:
    return get_available_gpu_options()


def _api():
    global _handle_cache_hits, _handle_cache_misses
    if _current_gpu not in _api_instances:
        _handle_cache_misses += 1
        _api_instances[_current_gpu] = _apis[_current_gpu]()
    else:
        _handle_cache_hits += 1
    return _api_instances[_current_gpu]


def _api_for_gpu(gpu: str | None = None):
    global _handle_cache_hits, _handle_cache_misses
    selected_gpu = _current_gpu if gpu is None else normalize_gpu_value(gpu)
    if selected_gpu not in _apis:
        raise ValueError(f"Unsupported GPU: {selected_gpu}")
    if selected_gpu not in _api_instances:
        _handle_cache_misses += 1
        _api_instances[selected_gpu] = _apis[selected_gpu]()
    else:
        _handle_cache_hits += 1
    return _api_instances[selected_gpu]


def clear_cache():
    """Clear cached API instance handles so subsequent requests use fresh handles."""
    global _handle_cache_hits, _handle_cache_misses
    _api_instances.clear()
    _handle_cache_hits = 0
    _handle_cache_misses = 0


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


@_modal_error_handler
async def run_prompt(
    workflow: dict,
    input_images: dict | None = None,
    trace: dict | None = None,
    gpu: str | None = None,
    modal_options: dict | None = None,
) -> dict:
    async with _run_prompt_semaphore:
        return await asyncio.to_thread(
            lambda: _api_for_gpu(gpu).run_prompt.remote(workflow, input_images or {}, trace or {}, modal_options or {}),
        )


# NOTE: no @_modal_error_handler here — that decorator does `await func()`
# which breaks async generator functions.  Error handling is inline.
async def run_prompt_stream(
    workflow: dict,
    input_images: dict | None = None,
    trace: dict | None = None,
    gpu: str | None = None,
    modal_options: dict | None = None,
):
    """Execute workflow on Modal and stream progress events back to the caller.

    Yields dicts with types:
      ``{"type": "status", "message": "..."}`` — startup/restore phase.
      ``{"type": "progress", "event": "...", "data": {...}}`` — ComfyUI events.
      ``{"type": "result", "data": {...}}`` — final result (last yield).
      ``{"type": "error", "message": "..."}`` — fatal error.
    """
    async with _run_prompt_semaphore:
        try:
            gen = _api_for_gpu(gpu).run_prompt_stream.remote_gen.aio(
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
async def get_object_info() -> dict:
    return await asyncio.to_thread(lambda: _api().object_info.remote())


@_modal_error_handler
async def health_check() -> dict:
    return await asyncio.to_thread(lambda: _health_fn.remote())


@_modal_error_handler
async def download_model(url: str, filename: str, save_path: str = "checkpoints", hf_token: str = "", civitai_token: str = "") -> dict:
    kwargs = dict(url=url, filename=filename, save_path=save_path, hf_token=hf_token)
    if civitai_token:
        kwargs["civitai_token"] = civitai_token
    return await asyncio.to_thread(lambda: _download_fn.remote(**kwargs))


async def download_model_stream(url: str, filename: str, save_path: str = "checkpoints", hf_token: str = "", civitai_token: str = ""):
    """Async generator yielding progress dicts from a Modal streaming download."""
    kwargs = dict(url=url, filename=filename, save_path=save_path, hf_token=hf_token)
    if civitai_token:
        kwargs["civitai_token"] = civitai_token
    loop = asyncio.get_running_loop()
    gen = await loop.run_in_executor(None, lambda: _download_stream_fn.remote_gen(**kwargs))
    while True:
        try:
            item = await loop.run_in_executor(None, next, gen)
            yield item
        except StopIteration:
            break


@_modal_error_handler
async def batch_download_models(items: list, hf_token: str = "", civitai_token: str = "") -> list:
    kwargs = dict(hf_token=hf_token)
    if civitai_token:
        kwargs["civitai_token"] = civitai_token
    return await asyncio.to_thread(lambda: _batch_download_fn.remote(items, **kwargs))


@_modal_error_handler
async def list_models() -> dict:
    return await asyncio.to_thread(lambda: _list_models_fn.remote())


@_modal_error_handler
async def delete_model(folder: str, filename: str) -> dict:
    return await asyncio.to_thread(
        lambda: _delete_model_fn.remote(folder=folder, filename=filename),
    )


@_modal_error_handler
async def sync_custom_nodes(archive_data: bytes) -> dict:
    return await asyncio.to_thread(
        lambda: _sync_custom_nodes_fn.remote(archive_data),
    )


@_modal_error_handler
async def refresh_custom_nodes(expected_nodes: list | None = None) -> dict:
    return await asyncio.to_thread(
        lambda: _api().refresh_custom_nodes.remote(expected_nodes or []),
    )


@_modal_error_handler
async def get_sync_status() -> dict:
    return await asyncio.to_thread(
        lambda: _get_volume_status_fn.remote(),
    )


@_modal_error_handler
async def upload_model_to_volume(file_data: bytes, folder: str, filename: str) -> dict:
    return await asyncio.to_thread(
        lambda: _upload_model_fn.remote(file_data, folder, filename),
    )


@_modal_error_handler
async def upload_model_chunk(chunk_data: bytes, folder: str, filename: str, offset: int, is_last: bool) -> dict:
    return await asyncio.to_thread(
        lambda: _upload_model_chunk_fn.remote(chunk_data, folder, filename, offset, is_last),
    )


@_modal_error_handler
async def resync_runtime(scope: str = "all") -> dict:
    return await asyncio.to_thread(lambda: _api().resync_runtime.remote(scope))


@_modal_error_handler
async def get_runtime_state() -> dict:
    """Check runtime state — CPU-only, no GPU needed."""
    return await asyncio.to_thread(lambda: _runtime_state_fn.remote())


@_modal_error_handler
async def set_active_warmup_profile(payload: dict) -> dict:
    return await asyncio.to_thread(lambda: _set_active_warmup_profile_fn.remote(payload))
