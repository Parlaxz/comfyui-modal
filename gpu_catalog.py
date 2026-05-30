DEFAULT_GPU = "a10g"

GPU_CATALOG = [
    {"value": "t4", "label": "T4", "modal_gpu": "t4", "class_name": "ComfyAPI_T4", "profile": "budget"},
    {"value": "l4", "label": "L4", "modal_gpu": "l4", "class_name": "ComfyAPI_L4", "profile": "standard"},
    {"value": "a10g", "label": "A10G", "modal_gpu": "a10g", "class_name": "ComfyAPI", "profile": "standard"},
    {"value": "l40s", "label": "L40S", "modal_gpu": "l40s", "class_name": "ComfyAPI_L40S", "profile": "high_mem"},
    {"value": "rtx-pro-6000", "label": "RTX PRO 6000", "modal_gpu": "rtx-pro-6000", "class_name": "ComfyAPI_RTX_PRO_6000", "profile": "high_mem"},
    {"value": "a100", "label": "A100 (default 40GB)", "modal_gpu": "a100", "class_name": "ComfyAPI_A100", "profile": "high_mem"},
    {"value": "a100-40gb", "label": "A100-40GB", "modal_gpu": "a100-40gb", "class_name": "ComfyAPI_A100_40GB", "profile": "high_mem"},
    {"value": "a100-80gb", "label": "A100-80GB", "modal_gpu": "a100-80gb", "class_name": "ComfyAPI_A100_80GB", "profile": "high_mem"},
    {"value": "h100", "label": "H100", "modal_gpu": "h100", "class_name": "ComfyAPI_H100", "profile": "high_mem"},
    {"value": "h200", "label": "H200", "modal_gpu": "h200", "class_name": "ComfyAPI_H200", "profile": "high_mem"},
    {"value": "b200", "label": "B200", "modal_gpu": "b200", "class_name": "ComfyAPI_B200", "profile": "high_mem"},
]

GPU_VALUES = [entry["value"] for entry in GPU_CATALOG]
GPU_BY_VALUE = {entry["value"]: entry for entry in GPU_CATALOG}


def normalize_gpu_value(gpu: str) -> str:
    return str(gpu or "").strip().lower()


def get_default_gpu() -> str:
    return DEFAULT_GPU


def get_supported_gpus() -> list[str]:
    return list(GPU_VALUES)


def get_available_gpu_options() -> list[dict[str, str]]:
    return [{"value": entry["value"], "label": entry["label"]} for entry in GPU_CATALOG]


def is_supported_gpu(gpu: str) -> bool:
    return normalize_gpu_value(gpu) in GPU_BY_VALUE
