@echo off
rem E27 Follow-Up A deploy wrapper: redeploys the canonical restore-only
rem shadow app with E19 profile + E27 telemetry + warmup env.
chcp 65001 >nul
setlocal enabledelayedexpansion

set "COMFYMODAL_V2_APP_NAME=stable-modal-comfy-v2-restore-only-shadow"
set "COMFYMODAL_V2_RESTORE_ONLY_APP_NAME=stable-modal-comfy-v2-restore-only-shadow"
set "COMFYMODAL_V2_ENABLE_MEMORY_SNAPSHOT=1"
set "COMFYMODAL_V2_E27_FORENSICS=1"
set "COMFYMODAL_V2_GANTT_TELEMETRY=1"
set "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=1"
set "COMFYMODAL_V2_VAE_SNAPSHOT=1"
set "COMFYMODAL_V2_CPU_REQUEST=16"
set "COMFYMODAL_V2_MEMORY_MB=49152"
set "COMFYMODAL_V2_GPU=rtx-pro-6000"
set "COMFYMODAL_V2_ENV_PROFILE=inherit"
set "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET=1"
set "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT=1"
set "COMFYMODAL_V2_EVICT_RETAIN_ROLE=clip_vae"
set "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS=0"
set "COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION=1"
set "COMFYMODAL_V2_ATOMIC_PROFILE=E19_FINAL_COLD_LOADER"
set "V2_E19_FINAL_COLD_LOADER=1"
set "COMFYMODAL_WARMUP_PROFILE=split"
set "COMFYMODAL_WARMUP_UNET=z_image_turbo_bf16.safetensors"
set "COMFYMODAL_WARMUP_CLIP1=qwen_3_4b.safetensors"
set "COMFYMODAL_WARMUP_CLIP2="
set "COMFYMODAL_WARMUP_VAE=ae.safetensors"
set "COMFYMODAL_WARMUP_CLIP_TYPE=lumina2"
set "COMFYMODAL_WARMUP_TEXT=warmup"

call deploy_and_run_v2_single.bat E19_FINAL
exit /b %errorlevel%
