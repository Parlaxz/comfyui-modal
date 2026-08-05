@echo off
setlocal enabledelayedexpansion

chcp 65001 >nul

REM -- Pin environment variables ------------------------------------
set "COMFYMODAL_V2_APP_NAME=stable-modal-comfy-v2-shadow"
set "COMFYMODAL_V2_CLASS_NAME=ModalRuntimeEntrypointV2"
set "COMFYMODAL_V2_GPU=rtx-pro-6000"
if not defined COMFYMODAL_V2_ENV_PROFILE set "COMFYMODAL_V2_ENV_PROFILE=production"
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
if not defined COMFYMODAL_V2_CPU_MODEL_SNAPSHOT set "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=1"
if not defined COMFYMODAL_V2_VAE_SNAPSHOT set "COMFYMODAL_V2_VAE_SNAPSHOT=1"
if not defined COMFYMODAL_V2_CLIP_CONDITIONING_CACHE set "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE=1"
if not defined COMFYMODAL_V2_UNET_ACTIVATION_MODE set "COMFYMODAL_V2_UNET_ACTIVATION_MODE=late"
if not defined COMFYMODAL_V2_VAE_ACTIVATION_MODE set "COMFYMODAL_V2_VAE_ACTIVATION_MODE=sampling_end"
if not defined COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE set "COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE=1"
if not defined V2_BENCHMARK_RUNS set "V2_BENCHMARK_RUNS=1"
if not defined V2_BENCHMARK_GAP_SECONDS set "V2_BENCHMARK_GAP_SECONDS=0"
if not defined COMFYMODAL_V2_THREAD_POLICY set "COMFYMODAL_V2_THREAD_POLICY=TBASE"
if not defined COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER set "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER=O0"
if not defined COMFYMODAL_V2_MEMORY_MB set "COMFYMODAL_V2_MEMORY_MB=49152"
if not defined COMFYMODAL_V2_BASELINE_CPU_REQUEST set "COMFYMODAL_V2_BASELINE_CPU_REQUEST=16"
if not defined COMFYMODAL_V2_BASELINE_MEMORY_REQUEST set "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST=49152"

set "REPO_ROOT=%~dp0"
cd /d "%REPO_ROOT%" || exit /b 1

REM -- Workspace loading -------------------------------------------
echo === Loading active workspace ===
set "WS_FILE=%TEMP%\_ws_%RANDOM%.txt"
python -c "import json,sys;d=json.load(open('.modal_workspaces.json'));aid=d.get('active_workspace_id');ws=next((w for w in d.get('workspaces',[])if w.get('id')==aid),None);tid=ws and ws.get('token_id')or'';ts=ws and ws.get('token_secret')or'';label=ws and ws.get('label','')or'';open(sys.argv[1],'w').write('MODAL_TOKEN_ID='+tid+'\nMODAL_TOKEN_SECRET='+ts+'\nMODAL_WORKSPACE_LABEL='+label)" "%WS_FILE%"
if errorlevel 1 (
    echo === ERROR: Python workspace extraction failed ===
    if defined WS_FILE if exist "%WS_FILE%" del /q "%WS_FILE%"
    exit /b 1
)
for /f "usebackq tokens=1,* delims==" %%a in ("%WS_FILE%") do set "%%a=%%b"
if defined WS_FILE if exist "%WS_FILE%" del /q "%WS_FILE%"
if not defined MODAL_TOKEN_ID (
    echo === ERROR: Could not load active workspace credentials ===
    exit /b 1
)
echo === Active workspace: !MODAL_WORKSPACE_LABEL! ===

REM -- Warmup profile ----------------------------------------------
echo === Extracting warmup profile from benchmark workflow ===
set "WARMUP_FILE=%TEMP%\_v2warm_%RANDOM%.txt"
python tools\extract_warmup_profile.py > "%WARMUP_FILE%"
if errorlevel 1 (
    type "%WARMUP_FILE%"
    echo === ERROR: Warmup profile derivation failed ===
    if defined WARMUP_FILE if exist "%WARMUP_FILE%" del /q "%WARMUP_FILE%"
    exit /b 1
)
for /f "usebackq delims=" %%a in ("%WARMUP_FILE%") do set "%%a"
if defined WARMUP_FILE if exist "%WARMUP_FILE%" del /q "%WARMUP_FILE%"
echo === Warmup profile loaded ===

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
echo env_profile=!COMFYMODAL_V2_ENV_PROFILE!
echo thread_policy=!COMFYMODAL_V2_THREAD_POLICY!
echo snapshot_model_order=!COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER!
echo baseline_cpu_request=!COMFYMODAL_V2_BASELINE_CPU_REQUEST!
echo baseline_memory_request=!COMFYMODAL_V2_BASELINE_MEMORY_REQUEST!
echo cpu_model_snapshot=!COMFYMODAL_V2_CPU_MODEL_SNAPSHOT!
echo vae_snapshot=!COMFYMODAL_V2_VAE_SNAPSHOT!
echo clip_conditioning_cache=!COMFYMODAL_V2_CLIP_CONDITIONING_CACHE!
echo unet_activation_mode=!COMFYMODAL_V2_UNET_ACTIVATION_MODE!
echo vae_activation_mode=!COMFYMODAL_V2_VAE_ACTIVATION_MODE!
echo persistent_local_handle=!COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE!
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

REM -- Modal CLI detection -----------------------------------------
where modal >nul 2>nul
if not errorlevel 1 (
    set "MODAL_CLI=modal"
) else (
    set "MODAL_CLI=python -m modal"
)

REM -- Check existing V1 deployment via modal app list --json -------
echo === Checking for existing V1 deployment: comfyui ===
set "V1_CHECK_FILE=%TEMP%\_v1chk_%RANDOM%.txt"
python -c "import json,subprocess,sys;out=subprocess.check_output(sys.argv[1].split()+['app','list','--json'],timeout=30);open(sys.argv[2],'w').write('1'if any(a.get('Description')=='comfyui'and a.get('State','').lower()=='deployed'for a in json.loads(out))else'0')" "!MODAL_CLI!" "%V1_CHECK_FILE%" 2>nul
if errorlevel 1 (
    echo === ERROR: Could not determine whether V1 is deployed ===
    if defined V1_CHECK_FILE if exist "!V1_CHECK_FILE!" del /q "!V1_CHECK_FILE!"
    exit /b 1
)
if not exist "%V1_CHECK_FILE%" (
    echo === ERROR: V1 deployment check produced no result ===
    exit /b 1
)
if exist "%V1_CHECK_FILE%" (
    set /p "V1_EXISTS=" < "%V1_CHECK_FILE%"
    if defined V1_CHECK_FILE if exist "%V1_CHECK_FILE%" del /q "%V1_CHECK_FILE%"
) else (
    echo === ERROR: V1 deployment check result disappeared ===
    exit /b 1
)
if not defined V1_EXISTS (
    echo === ERROR: V1 deployment check result was empty ===
    exit /b 1
)

REM -- Conditional deploy -------------------------------------------
if "!V1_EXISTS!"=="1" (

    REM ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    REM V1 already deployed: deploy V2 only
    REM ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    echo === V1 comfyui already deployed. Deploying V2 only ===

    set "V2_LOG=%TEMP%\_v2dpl_%RANDOM%.txt"
    !MODAL_CLI! deploy -m comfymodal_runtime.modal_app > "!V2_LOG!" 2>&1
    set "V2_EXIT=!errorlevel!"

    echo.
    echo === V2 deploy log ===
    type "!V2_LOG!"
    echo.

    if !V2_EXIT! neq 0 (
        echo === ERROR: V2 deploy failed with exit code !V2_EXIT! ===
        if defined V2_LOG if exist "!V2_LOG!" del /q "!V2_LOG!"
        exit /b !V2_EXIT!
    )

    REM Validate V2 identifiers
    findstr /C:"stable-modal-comfy-v2-shadow" "!V2_LOG!" >nul 2>nul
    if errorlevel 1 (
        echo === ERROR: V2 deploy output missing shadow app identifier ===
        if defined V2_LOG if exist "!V2_LOG!" del /q "!V2_LOG!"
        exit /b 1
    )
    findstr /C:"ModalRuntimeEntrypointV2" "!V2_LOG!" >nul 2>nul
    if errorlevel 1 (
        echo === ERROR: V2 deploy output missing V2 class identifier ===
        if defined V2_LOG if exist "!V2_LOG!" del /q "!V2_LOG!"
        exit /b 1
    )

    if defined V2_LOG if exist "!V2_LOG!" del /q "!V2_LOG!"
    echo === V2 deploy verified OK ===

) else (

    REM ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    REM No V1 deployed: deploy V1 and V2 concurrently
    REM ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    echo === No existing V1 found. Deploying V1 and V2 concurrently ===

    set "V1_CMD_FILE=%TEMP%\_v1cmd_%RANDOM%.bat"
    set "V2_CMD_FILE=%TEMP%\_v2cmd_%RANDOM%.bat"
    set "V1_LOG=%TEMP%\_v1dpl_%RANDOM%.txt"
    set "V2_LOG=%TEMP%\_v2dpl_%RANDOM%.txt"
    set "DEPLOY_RESULT=%TEMP%\_dplres_%RANDOM%.txt"

    if not defined COMFYMODAL_DEPLOY_TIMEOUT_SECONDS set "COMFYMODAL_DEPLOY_TIMEOUT_SECONDS=3600"

    > "!V1_CMD_FILE!" echo @echo off
    >>"!V1_CMD_FILE!" echo !MODAL_CLI! deploy comfyapp.py
    >>"!V1_CMD_FILE!" echo exit /b %%errorlevel%%
    > "!V2_CMD_FILE!" echo @echo off
    >>"!V2_CMD_FILE!" echo !MODAL_CLI! deploy -m comfymodal_runtime.modal_app
    >>"!V2_CMD_FILE!" echo exit /b %%errorlevel%%

    echo === Deploying V1 and V2 concurrently. Timeout=!COMFYMODAL_DEPLOY_TIMEOUT_SECONDS!s ===
    python tools\run_deploys_concurrent.py ^
        "!V1_CMD_FILE!" "!V2_CMD_FILE!" ^
        "!V1_LOG!" "!V2_LOG!" ^
        "!COMFYMODAL_DEPLOY_TIMEOUT_SECONDS!" ^
        > "!DEPLOY_RESULT!"
    set "PARALLEL_EXIT=!errorlevel!"

    REM Clean command files immediately
    if defined V1_CMD_FILE if exist "!V1_CMD_FILE!" del /q "!V1_CMD_FILE!"
    if defined V2_CMD_FILE if exist "!V2_CMD_FILE!" del /q "!V2_CMD_FILE!"

    REM Parse result
    set "V1_DEPLOY_EXIT="
    set "V2_DEPLOY_EXIT="
    set "TIMED_OUT="
    for /f "usebackq tokens=1,* delims==" %%a in ("!DEPLOY_RESULT!") do (
        if "%%a"=="V1_EXIT" set "V1_DEPLOY_EXIT=%%b"
        if "%%a"=="V2_EXIT" set "V2_DEPLOY_EXIT=%%b"
        if "%%a"=="TIMED_OUT" set "TIMED_OUT=%%b"
    )
    if defined DEPLOY_RESULT if exist "!DEPLOY_RESULT!" del /q "!DEPLOY_RESULT!"

    REM Surface logs
    echo.
    echo === V1 deploy log ===
    type "!V1_LOG!" 2>nul
    echo.
    echo === V2 deploy log ===
    type "!V2_LOG!" 2>nul
    echo.

    REM Validate: timeout
    if /i "!TIMED_OUT!"=="true" (
        echo === ERROR: Concurrent deploy timed out after !COMFYMODAL_DEPLOY_TIMEOUT_SECONDS!s ===
        if defined V1_LOG if exist "!V1_LOG!" del /q "!V1_LOG!"
        if defined V2_LOG if exist "!V2_LOG!" del /q "!V2_LOG!"
        exit /b 1
    )

    REM Validate V1 exit code for this deploy
    if not defined V1_DEPLOY_EXIT set "V1_DEPLOY_EXIT=-1"
    if !V1_DEPLOY_EXIT! neq 0 (
        echo === ERROR: V1 deploy failed with exit code !V1_DEPLOY_EXIT! ===
        if defined V1_LOG if exist "!V1_LOG!" del /q "!V1_LOG!"
        if defined V2_LOG if exist "!V2_LOG!" del /q "!V2_LOG!"
        exit /b !V1_DEPLOY_EXIT!
    )

    REM Validate V1 output contains comfyui app identifier
    findstr /C:"comfyui" "!V1_LOG!" >nul 2>nul
    if errorlevel 1 (
        echo === ERROR: V1 deploy output missing 'comfyui' app identifier ===
        if defined V1_LOG if exist "!V1_LOG!" del /q "!V1_LOG!"
        if defined V2_LOG if exist "!V2_LOG!" del /q "!V2_LOG!"
        exit /b 1
    )

    REM Validate V2 exit code
    if not defined V2_DEPLOY_EXIT set "V2_DEPLOY_EXIT=-1"
    if !V2_DEPLOY_EXIT! neq 0 (
        echo === ERROR: V2 deploy failed with exit code !V2_DEPLOY_EXIT! ===
        if defined V1_LOG if exist "!V1_LOG!" del /q "!V1_LOG!"
        if defined V2_LOG if exist "!V2_LOG!" del /q "!V2_LOG!"
        exit /b !V2_DEPLOY_EXIT!
    )

    REM Validate V2 identifiers
    findstr /C:"stable-modal-comfy-v2-shadow" "!V2_LOG!" >nul 2>nul
    if errorlevel 1 (
        echo === ERROR: V2 deploy output missing shadow app identifier ===
        if defined V1_LOG if exist "!V1_LOG!" del /q "!V1_LOG!"
        if defined V2_LOG if exist "!V2_LOG!" del /q "!V2_LOG!"
        exit /b 1
    )
    findstr /C:"ModalRuntimeEntrypointV2" "!V2_LOG!" >nul 2>nul
    if errorlevel 1 (
        echo === ERROR: V2 deploy output missing V2 class identifier ===
        if defined V1_LOG if exist "!V1_LOG!" del /q "!V1_LOG!"
        if defined V2_LOG if exist "!V2_LOG!" del /q "!V2_LOG!"
        exit /b 1
    )

    REM Clean deploy logs
    if defined V1_LOG if exist "!V1_LOG!" del /q "!V1_LOG!"
    if defined V2_LOG if exist "!V2_LOG!" del /q "!V2_LOG!"

    echo === V1 and V2 deploys both verified OK ===
)

if /i "!COMFYMODAL_DEPLOY_ONLY!"=="1" (
    echo === Deploy-only requested; acceptance benchmark skipped ===
    exit /b 0
)

REM -- Benchmark invocation ------------------------------------------
REM Default: V2_BENCHMARK_RUNS=1 -> exactly one run.  The acceptance
REM sequence (A fresh / B reused / C fresh, ~3+ requests) runs ONLY via
REM the explicit opt-in env V2_BENCHMARK_MODE=acceptance so the single-run
REM contract of this script is never silently exceeded.
for /f %%a in ('powershell -NoProfile -Command "[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()"') do set "COMFYMODAL_COMMAND_START_UNIX_MS=%%a"
if /i "!V2_BENCHMARK_MODE!"=="acceptance" (
    echo === Running V2 acceptance benchmark - explicit opt-in ===
    python tools\benchmark_v2_direct.py --acceptance
    if errorlevel 1 (
        echo === ERROR: Acceptance benchmark failed ===
        exit /b 1
    )
    echo === V2 acceptance benchmark completed ===
) else (
    echo === Running V2 benchmark - single run by default ===
    python tools\benchmark_v2_direct.py
    if errorlevel 1 (
        echo === ERROR: Benchmark failed ===
        exit /b 1
    )
    echo === V2 benchmark completed ===
)
exit /b 0
