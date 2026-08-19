@echo off
rem E27 Follow-Up A: single cold generation against the restore-only app.
chcp 65001 >nul
setlocal enabledelayedexpansion

set "COMFYMODAL_V2_APP_NAME=stable-modal-comfy-v2-restore-only-shadow"
set "COMFYMODAL_V2_GPU=rtx-pro-6000"
set "COMFYMODAL_V2_CPU_REQUEST=16"
set "COMFYMODAL_V2_MEMORY_MB=49152"
set "COMFYMODAL_V2_ALLOW_MULTI_AXIS=1"
set "V2_E19_FINAL_COLD_LOADER=1"
set "V2_BENCHMARK_RUNS=1"
set "V2_BENCHMARK_GAP_SECONDS=5"
set "V2_E26_CONDITIONING_NONCE=e27-fa-%RANDOM%-%RANDOM%"

call run_v2_single.bat
exit /b %errorlevel%
