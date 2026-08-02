@echo off
setlocal enabledelayedexpansion
for /f %%a in ('powershell -NoProfile -Command "[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()"') do set "COMMAND_START_MS=%%a"

chcp 65001 >nul
set "COMFYMODAL_V2_APP_NAME=stable-modal-comfy-v2-shadow"
set "COMFYMODAL_V2_CLASS_NAME=ModalRuntimeEntrypointV2"
set "COMFYMODAL_V2_GPU=rtx-pro-6000"
set "COMFYMODAL_V2_CLOUD="
if not defined COMFYMODAL_V2_ENV_PROFILE set "COMFYMODAL_V2_ENV_PROFILE=inherit"
if /i "!COMFYMODAL_V2_ENV_PROFILE!"=="production" (
    set "COMFYMODAL_V2_FULL_TRACE=0"
    set "COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS=0"
    set "COMFYMODAL_V2_DEEP_MODEL_DIAG=0"
    set "COMFYMODAL_V2_PAGEFAULT_TRACKING=0"
    set "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT=0"
    set "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS=0"
    set "COMFYMODAL_V2_EVICT_RETAIN_ROLE="
    set "COMFYMODAL_V2_PREFILL_LANES=critical"
    set "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET=0"
    set "COMFYMODAL_V2_RESTORE_TORCH_THREADS="
)
if /i "!COMFYMODAL_V2_ENV_PROFILE!"=="diagnostic" if not defined COMFYMODAL_V2_DEEP_MODEL_DIAG set "COMFYMODAL_V2_DEEP_MODEL_DIAG=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
if not defined V2_BENCHMARK_RUNS set "V2_BENCHMARK_RUNS=1"
if not defined V2_BENCHMARK_GAP_SECONDS set "V2_BENCHMARK_GAP_SECONDS=0"
if /i "!COMFYMODAL_V2_ENV_PROFILE!"=="production" (
    set "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=1"
) else if not defined COMFYMODAL_V2_CPU_MODEL_SNAPSHOT set "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=1"
if not defined COMFYMODAL_V2_MEMORY_MB set "COMFYMODAL_V2_MEMORY_MB=49152"

set "REPO_ROOT=%~dp0"
cd /d "%REPO_ROOT%" || exit /b 1

set "IDX=0"
for /f "usebackq delims=" %%a in (`python -c "import json,sys;d=json.load(open('.modal_workspaces.json'));aid=d.get('active_workspace_id');ws=next((w for w in d.get('workspaces',[]) if w.get('id')==aid),None);tid=ws and ws.get('token_id') or '';ts=ws and ws.get('token_secret') or '';sys.exit(1) if not(aid and ws and tid and ts) else None;print(tid);print(ts)"`) do (
    if !IDX! equ 0 set "MODAL_TOKEN_ID=%%a"
    if !IDX! equ 1 set "MODAL_TOKEN_SECRET=%%a"
    set /a IDX+=1
)
if !IDX! lss 2 (
    echo === ERROR: Could not load active workspace credentials ===
    exit /b 1
)

REM -- Sanitized environment profile summary ------------------------
set "V2_PROFILE_FULL_TRACE=0"
if defined COMFYMODAL_V2_FULL_TRACE set "V2_PROFILE_FULL_TRACE=!COMFYMODAL_V2_FULL_TRACE!"
set "V2_PROFILE_RESIDENCY=0"
if defined COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS set "V2_PROFILE_RESIDENCY=!COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS!"
set "V2_PROFILE_DEEP_DIAG=0"
if defined COMFYMODAL_V2_DEEP_MODEL_DIAG set "V2_PROFILE_DEEP_DIAG=!COMFYMODAL_V2_DEEP_MODEL_DIAG!"
set "V2_PROFILE_PAGEFAULT=0"
if defined COMFYMODAL_V2_PAGEFAULT_TRACKING set "V2_PROFILE_PAGEFAULT=!COMFYMODAL_V2_PAGEFAULT_TRACKING!"
set "V2_PROFILE_EVICTION=0"
if defined COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT set "V2_PROFILE_EVICTION=!COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT!"
set "V2_PROFILE_EVICT_IDLE=0"
if defined COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS set "V2_PROFILE_EVICT_IDLE=!COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS!"
set "V2_PROFILE_EVICT_ROLE=none"
if defined COMFYMODAL_V2_EVICT_RETAIN_ROLE (
    set "V2_PROFILE_EVICT_ROLE=!COMFYMODAL_V2_EVICT_RETAIN_ROLE!"
)
set "V2_PROFILE_PREFILL=critical"
if defined COMFYMODAL_V2_PREFILL_LANES set "V2_PROFILE_PREFILL=!COMFYMODAL_V2_PREFILL_LANES!"
set "V2_PROFILE_PREFILL_WAIT=0"
if defined COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET set "V2_PROFILE_PREFILL_WAIT=!COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET!"
set "V2_PROFILE_THREADS=none"
if defined COMFYMODAL_V2_RESTORE_TORCH_THREADS (
    set "V2_PROFILE_THREADS=!COMFYMODAL_V2_RESTORE_TORCH_THREADS!"
)
echo [v2.env_profile]
echo profile=!COMFYMODAL_V2_ENV_PROFILE!
echo cpu_model_snapshot=!COMFYMODAL_V2_CPU_MODEL_SNAPSHOT!
echo full_trace=!V2_PROFILE_FULL_TRACE!
echo residency_diagnostics=!V2_PROFILE_RESIDENCY!
echo deep_model_diag=!V2_PROFILE_DEEP_DIAG!
echo pagefault_tracking=!V2_PROFILE_PAGEFAULT!
echo eviction_enabled=!V2_PROFILE_EVICTION!
echo eviction_role=!V2_PROFILE_EVICT_ROLE!
echo eviction_idle_seconds=!V2_PROFILE_EVICT_IDLE!
echo prefill_lanes=!V2_PROFILE_PREFILL!
echo prefill_wait_for_unet=!V2_PROFILE_PREFILL_WAIT!
echo restore_torch_threads=!V2_PROFILE_THREADS!

set "COMFYMODAL_COMMAND_START_UNIX_MS=!COMMAND_START_MS!"
echo === Running one V2 benchmark trial against the existing deployment ===
echo === Deploy first with deploy_and_run_v2_single.bat after source or env changes ===
python tools\benchmark_v2_direct.py
set "BENCHMARK_EXIT_CODE=!errorlevel!"
for /f %%a in ('powershell -NoProfile -Command "[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()"') do set "COMMAND_END_MS=%%a"
for /f %%a in ('powershell -NoProfile -Command "(([long]!COMMAND_END_MS! - [long]!COMMAND_START_MS!) / 1000.0).ToString('0.000', [Globalization.CultureInfo]::InvariantCulture)"') do set "COMMAND_ELAPSED_SECONDS=%%a"
if !BENCHMARK_EXIT_CODE! geq 1 (
    echo === ERROR: Benchmark failed ===
    echo === Total command-to-response time: !COMMAND_ELAPSED_SECONDS!s ===
    exit /b 1
)
echo === Single V2 benchmark completed ===
echo === Total command-to-response time: !COMMAND_ELAPSED_SECONDS!s ===
exit /b 0
