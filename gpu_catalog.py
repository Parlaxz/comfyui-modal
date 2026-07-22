import os

DEFAULT_GPU = "rtx-pro-6000"
# V2 canonical primary GPU name (Modal-cased), used when COMFYMODAL_V2_GPU
# is absent or explicitly empty.  Preserves legacy DEFAULT_GPU for backward
# compat in non-V2 code paths.
V2_DEFAULT_GPU: str = "RTX-PRO-6000"

# ── Canonical GPU name mapping (lowercase-normalized → Modal canonical) ──
# All keys and values must match Modal's accepted GPU strings exactly.
GPU_CANONICAL_MAP: dict[str, str] = {
    "rtx-pro-6000": "RTX-PRO-6000",
    "rtx pro 6000": "RTX-PRO-6000",
    "a100-80gb": "A100-80GB",
    "a100 80gb": "A100-80GB",
    "a100_80gb": "A100-80GB",
    "a100-40gb": "A100-40GB",
    "a100 40gb": "A100-40GB",
    "a100_40gb": "A100-40GB",
    "a100": "A100",
    "t4": "T4",
    "l4": "L4",
    "a10g": "A10",
    "a10": "A10",
    "l40s": "L40S",
    "l40": "L40S",
    "h100": "H100",
    "h200": "H200",
    "b200": "B200",
}

# ── Default ordered GPU request ─────────────────────────────────────────
# Primary from COMFYMODAL_V2_GPU, fallbacks from COMFYMODAL_V2_GPU_FALLBACKS.
# Deduped preserving order.  Empty/absent fallbacks = no fallback.
DEFAULT_GPU_FALLBACKS: tuple[str, ...] = ()


def _normalize_gpu_name(raw: str) -> str:
    """Normalize a GPU name to lower-case with hyphens, then look up canonical."""
    cleaned = raw.strip().lower().replace("_", "-").replace(" ", "-")
    return GPU_CANONICAL_MAP.get(cleaned, cleaned)


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    """Remove duplicates while preserving first-seen order."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def parse_gpu_request() -> tuple[str, ...]:
    """Parse the ordered GPU request from environment variables.

    Returns an immutable deduplicated tuple of Modal-canonical GPU names.
    Never appends GPUs beyond those explicitly configured or defaulted.

    Semantics
    ---------
    * ``COMFYMODAL_V2_GPU`` absent → ``V2_DEFAULT_GPU`` as primary.
    * ``COMFYMODAL_V2_GPU`` explicitly empty or whitespace-only
      → ``V2_DEFAULT_GPU`` as primary (not legacy ``DEFAULT_GPU``).
    * ``COMFYMODAL_V2_GPU_FALLBACKS`` absent → no fallbacks (empty tuple).
    * ``COMFYMODAL_V2_GPU_FALLBACKS`` explicitly empty or whitespace-only
      → disable all fallbacks (empty tuple).
    """
    primary_raw = os.environ.get("COMFYMODAL_V2_GPU", V2_DEFAULT_GPU).strip()
    primary = _normalize_gpu_name(primary_raw) if primary_raw else V2_DEFAULT_GPU

    fallbacks_raw = os.environ.get("COMFYMODAL_V2_GPU_FALLBACKS")
    if fallbacks_raw is None:
        # Absent → use defaults
        fallback_list = list(DEFAULT_GPU_FALLBACKS)
    elif fallbacks_raw.strip():
        # Non-empty explicit value → parse comma-separated list
        fallback_list = [
            _normalize_gpu_name(fb.strip())
            for fb in fallbacks_raw.split(",")
            if fb.strip()
        ]
    else:
        # Explicitly empty or whitespace-only → disable all fallbacks
        fallback_list = []

    # Build ordered list: primary first, then fallbacks, dedupe preserving order
    ordered = [primary] + fallback_list
    return tuple(_dedupe_preserve_order(ordered))

GPU_CATALOG = [
    {"value": "rtx-pro-6000", "label": "RTX PRO 6000", "modal_gpu": "rtx-pro-6000", "class_name": "ComfyAPI_RTX_PRO_6000", "profile": "high_mem"},
    {"value": "t4", "label": "T4", "modal_gpu": "t4", "class_name": "ComfyAPI_T4", "profile": "budget"},
    {"value": "l4", "label": "L4", "modal_gpu": "l4", "class_name": "ComfyAPI_L4", "profile": "standard"},
    {"value": "a10g", "label": "A10G", "modal_gpu": "a10g", "class_name": "ComfyAPI", "profile": "standard"},
    {"value": "l40s", "label": "L40S", "modal_gpu": "l40s", "class_name": "ComfyAPI_L40S", "profile": "high_mem"},
    {"value": "a100", "label": "A100 (default 40GB)", "modal_gpu": "a100", "class_name": "ComfyAPI_A100", "profile": "high_mem"},
    {"value": "a100-40gb", "label": "A100-40GB", "modal_gpu": "a100-40gb", "class_name": "ComfyAPI_A100_40GB", "profile": "high_mem"},
    {"value": "a100-80gb", "label": "A100-80GB", "modal_gpu": "a100-80gb", "class_name": "ComfyAPI_A100_80GB", "profile": "high_mem"},
    {"value": "h100", "label": "H100", "modal_gpu": "h100", "class_name": "ComfyAPI_H100", "profile": "high_mem"},
    {"value": "h200", "label": "H200", "modal_gpu": "h200", "class_name": "ComfyAPI_H200", "profile": "high_mem"},
    {"value": "b200", "label": "B200", "modal_gpu": "b200", "class_name": "ComfyAPI_B200", "profile": "high_mem"},
]

GPU_VALUES = [entry["value"] for entry in GPU_CATALOG]
GPU_BY_VALUE = {entry["value"]: entry for entry in GPU_CATALOG}

# ── Hidden GPU support ──────────────────────────────────────────────────
# Controlled by the COMFYMODAL_HIDE_GPUS environment variable, which lists
# comma-separated GPU *values* (e.g. "t4,l4,l40s").  Hidden GPUs are
# excluded from registration, from the config endpoint, and from validation.
# Uses lazy initialisation so tests can set the env var before calling.
_HIDDEN_GPU_VALUES: frozenset | None = None


def _get_hidden_gpus() -> frozenset:
    global _HIDDEN_GPU_VALUES
    if _HIDDEN_GPU_VALUES is None:
        _HIDDEN_GPU_VALUES = frozenset(
            v.strip().lower()
            for v in os.environ.get("COMFYMODAL_HIDE_GPUS", "").split(",")
            if v.strip()
        )
    return _HIDDEN_GPU_VALUES


def _clear_hidden_cache():
    """Forget cached hidden set (used by tests)."""
    global _HIDDEN_GPU_VALUES
    _HIDDEN_GPU_VALUES = None


def normalize_gpu_value(gpu: str) -> str:
    return str(gpu or "").strip().lower()


def is_gpu_hidden(gpu_value: str) -> bool:
    """Return True if the given GPU value is in the hidden set."""
    return normalize_gpu_value(gpu_value) in _get_hidden_gpus()


def get_default_gpu() -> str:
    hidden = _get_hidden_gpus()
    if DEFAULT_GPU not in hidden:
        return DEFAULT_GPU
    for entry in GPU_CATALOG:
        if entry["value"] not in hidden:
            return entry["value"]
    return ""


def get_supported_gpus() -> list[str]:
    """Return GPU values that are NOT hidden."""
    hidden = _get_hidden_gpus()
    return [e["value"] for e in GPU_CATALOG if e["value"] not in hidden]


def get_available_gpu_options() -> list[dict[str, str]]:
    """Return value/label options for GPUs that are NOT hidden."""
    hidden = _get_hidden_gpus()
    return [{"value": e["value"], "label": e["label"]} for e in GPU_CATALOG if e["value"] not in hidden]


def is_supported_gpu(gpu: str) -> bool:
    """Return True if the GPU value is in the catalog and NOT hidden."""
    n = normalize_gpu_value(gpu)
    return n in GPU_BY_VALUE and n not in _get_hidden_gpus()
