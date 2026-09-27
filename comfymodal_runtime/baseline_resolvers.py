"""Lightweight runtime baseline/configuration resolvers."""

import os


PRELOAD_MODE = os.getenv("COMFYMODAL_PRELOAD_MODE", "off").strip().lower()
SAGE_RUNTIME_MODE = os.getenv("COMFYMODAL_SAGE_RUNTIME_MODE", "auto").strip().lower()
SAGE_RUNTIME_PROBE_ON_RESTORE = (
    os.getenv("COMFYMODAL_SAGE_RUNTIME_PROBE_ON_RESTORE", "1").strip().lower()
    in ("1", "true", "yes", "on")
)

PRELOAD_MODE_PATH = "/root/comfymodal_runtime_state/.preload_mode"
RUNTIME_CONFIG_DIR = "/root/comfymodal_runtime_state"
RUNTIME_RETURN_MODE_PATH = os.path.join(RUNTIME_CONFIG_DIR, "return_mode.txt")
RUNTIME_STATE_SNAPSHOT_PATH = os.path.join(
    RUNTIME_CONFIG_DIR, ".runtime_state_snapshot.json"
)


_PRODUCTION_BASELINE_OVERRIDES = {
    "COMFYMODAL_SAGE_RUNTIME_MODE": "baked_cuda",
    "COMFYMODAL_SAGE_RUNTIME_PROBE_ON_RESTORE": "0",
    "COMFYMODAL_PRELOAD_MODE": "clip_only",
    "COMFYMODAL_DIRECT_WARMUP_LOAD_UNET": "0",
    "COMFYMODAL_DIRECT_WARMUP_LOAD_CLIP": "1",
    "COMFYMODAL_DIRECT_WARMUP_CLIP_ENCODE": "1",
    "COMFYMODAL_EXACT_CLIP_PREFILL": "1",
    "COMFYMODAL_DIRECT_WARMUP_REQUIRE_CPU_CACHE_HIT": "1",
}


def production_baseline_value(name: str) -> str | None:
    """Return the immutable production value for an environment name."""
    env_name = str(name).strip().upper()
    if not env_name.startswith("COMFYMODAL_"):
        env_name = f"COMFYMODAL_{env_name}"
    return _PRODUCTION_BASELINE_OVERRIDES.get(env_name)


def _resolve_production_baseline_flag(name: str) -> str | None:
    return production_baseline_value(name)


def _read_runtime_file(path: str, *, file_exists=None, read_file=None) -> str | None:
    file_exists = os.path.isfile if file_exists is None else file_exists
    read_file = open if read_file is None else read_file
    try:
        if not file_exists(path):
            return None
        source = read_file(path)
        if hasattr(source, "read"):
            stream = source
            try:
                source = stream.read()
            finally:
                close = getattr(stream, "close", None)
                if close is not None:
                    close()
        return str(source).strip().lower()
    except Exception:
        return None


def _resolve_runtime_flag(
    name: str,
    default: str,
    is_golden: bool = False,
    *,
    runtime_config_dir: str | None = None,
    file_exists=None,
    read_file=None,
) -> bool:
    if not is_golden:
        baseline = production_baseline_value(name)
        if baseline is not None:
            return baseline == "1"
    runtime_config_dir = RUNTIME_CONFIG_DIR if runtime_config_dir is None else runtime_config_dir
    value = _read_runtime_file(
        os.path.join(runtime_config_dir, f"{name}.txt"),
        file_exists=file_exists,
        read_file=read_file,
    )
    if value in ("0", "1"):
        return value == "1"
    return os.environ.get(f"COMFYMODAL_{name}", default) == "1"


def _resolve_runtime_string(
    name: str,
    default: str,
    allowed: set[str] | tuple[str, ...] | None = None,
    *,
    runtime_config_dir: str | None = None,
    file_exists=None,
    read_file=None,
) -> str:
    runtime_config_dir = RUNTIME_CONFIG_DIR if runtime_config_dir is None else runtime_config_dir
    value = _read_runtime_file(
        os.path.join(runtime_config_dir, f"{name}.txt"),
        file_exists=file_exists,
        read_file=read_file,
    )
    if value and (allowed is None or value in allowed):
        return value
    env = os.environ.get(f"COMFYMODAL_{name}", default).strip().lower()
    return default if allowed is not None and env not in allowed else env


def _resolve_sage_runtime_env_override(
    is_golden: bool = False,
    *,
    runtime_config_dir: str | None = None,
    file_exists=None,
    read_file=None,
) -> str:
    if is_golden:
        # Golden's deploy-baked environment is authoritative.  In particular,
        # do not let a snapshot-era runtime file reintroduce ``auto`` and its
        # blocked-import fallback.
        configured = os.environ.get(
            "COMFYMODAL_SAGE_RUNTIME_MODE", SAGE_RUNTIME_MODE
        ).strip().lower()
        return configured if configured in {"auto", "baked_cuda", "triton_fallback"} else "auto"
    baseline = production_baseline_value("SAGE_RUNTIME_MODE")
    if not is_golden and baseline is not None:
        return baseline
    runtime_config_dir = RUNTIME_CONFIG_DIR if runtime_config_dir is None else runtime_config_dir
    value = _read_runtime_file(
        os.path.join(runtime_config_dir, "sage_runtime_mode.txt"),
        file_exists=file_exists,
        read_file=read_file,
    )
    if value in ("auto", "baked_cuda", "triton_fallback"):
        return value
    return SAGE_RUNTIME_MODE


def _resolve_sage_probe_on_restore(
    is_golden: bool = False,
    *,
    runtime_config_dir: str | None = None,
    file_exists=None,
    read_file=None,
) -> bool:
    baseline = production_baseline_value("SAGE_RUNTIME_PROBE_ON_RESTORE")
    if not is_golden and baseline is not None:
        return baseline == "1"
    runtime_config_dir = RUNTIME_CONFIG_DIR if runtime_config_dir is None else runtime_config_dir
    value = _read_runtime_file(
        os.path.join(runtime_config_dir, "sage_runtime_probe.txt"),
        file_exists=file_exists,
        read_file=read_file,
    )
    if value in ("0", "1"):
        return value == "1"
    return SAGE_RUNTIME_PROBE_ON_RESTORE


def _resolve_preload_mode(
    is_golden: bool = False,
    *,
    runtime_config_dir: str | None = None,
    preload_mode_path: str | None = None,
    file_exists=None,
    read_file=None,
) -> str:
    baseline = production_baseline_value("PRELOAD_MODE")
    if not is_golden and baseline is not None:
        return baseline
    if preload_mode_path is None:
        preload_mode_path = PRELOAD_MODE_PATH if runtime_config_dir is None else os.path.join(
            runtime_config_dir, ".preload_mode"
        )
    value = _read_runtime_file(preload_mode_path, file_exists=file_exists, read_file=read_file)
    return value or PRELOAD_MODE


__all__ = [
    "PRELOAD_MODE", "PRELOAD_MODE_PATH", "RUNTIME_CONFIG_DIR",
    "RUNTIME_RETURN_MODE_PATH", "RUNTIME_STATE_SNAPSHOT_PATH",
    "SAGE_RUNTIME_MODE", "SAGE_RUNTIME_PROBE_ON_RESTORE",
    "production_baseline_value", "_resolve_production_baseline_flag",
    "_resolve_preload_mode", "_resolve_runtime_flag", "_resolve_runtime_string",
    "_resolve_sage_probe_on_restore", "_resolve_sage_runtime_env_override",
]
