@echo off
rem =====================================================================
rem CLEAN BEST-CASE V2 DEPLOY — E19 final cold-loader profile, production
rem cache semantics, ALL E27/forensics instrumentation killed.
rem Deploys via the canonical deploy_and_run_v2_single.bat (E19_FINAL)
rem at the C8-verified 16 CPU / 49152 MiB shape.
rem =====================================================================
chcp 65001 >nul
setlocal enabledelayedexpansion

rem --- E19 final cold-loader profile ---
set "V2_E19_FINAL_COLD_LOADER=1"
set "COMFYMODAL_V2_ATOMIC_PROFILE=E19_FINAL_COLD_LOADER"
set "COMFYMODAL_V2_ENV_PROFILE=inherit"

rem --- Normal production cache semantics; DO NOT force a CLIP miss ---
set "V2_E26_CONDITIONING_NONCE="

rem --- Disable E27 / diagnostic instrumentation ---
set "COMFYMODAL_V2_E27_FORENSICS=0"
set "COMFYMODAL_V2_GANTT_TELEMETRY=0"
set "COMFYMODAL_V2_CLIP_COLD_FORENSICS=0"
set "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST=0"
set "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA=0"
set "COMFYMODAL_V2_UNET_FORENSICS=0"

rem --- Best-case resource shape (C8-verified) ---
set "COMFYMODAL_V2_CPU_REQUEST=16"
set "COMFYMODAL_V2_MEMORY_MB=49152"
set "COMFYMODAL_V2_BASELINE_CPU_REQUEST=12"
set "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST=32768"

call deploy_and_run_v2_single.bat E19_FINAL
exit /b %errorlevel%
