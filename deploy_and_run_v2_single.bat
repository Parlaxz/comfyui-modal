@echo off
setlocal enabledelayedexpansion

chcp 65001 >nul
set "COMFYMODAL_V2_APP_NAME=stable-modal-comfy-v2-shadow"
set "COMFYMODAL_V2_CLASS_NAME=ModalRuntimeEntrypointV2"
set "COMFYMODAL_V2_GPU=rtx-pro-6000"
set "COMFYMODAL_V2_DEEP_MODEL_DIAG=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
set "V2_BENCHMARK_RUNS=1"
set "V2_BENCHMARK_GAP_SECONDS=0"
set "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=1"
if not defined COMFYMODAL_V2_MEMORY_MB set "COMFYMODAL_V2_MEMORY_MB=49152"

set "REPO_ROOT=%~dp0"
cd /d "%REPO_ROOT%" || exit /b 1

echo === Loading active workspace ===
set "IDX=0"
for /f "usebackq delims=" %%a in (`python -c "import json,sys;d=json.load(open('.modal_workspaces.json'));aid=d.get('active_workspace_id');ws=next((w for w in d.get('workspaces',[]) if w.get('id')==aid),None);tid=ws and ws.get('token_id') or '';ts=ws and ws.get('token_secret') or '';label=ws and ws.get('label','') or '';sys.exit(1) if not(aid and ws and tid and ts) else None;print(tid);print(ts);print(label)"`) do (
    if !IDX! equ 0 set "MODAL_TOKEN_ID=%%a"
    if !IDX! equ 1 set "MODAL_TOKEN_SECRET=%%a"
    if !IDX! equ 2 set "MODAL_WORKSPACE_LABEL=%%a"
    set /a IDX+=1
)
if !IDX! lss 3 (
    echo === ERROR: Could not load active workspace credentials ===
    exit /b 1
)
echo === Active workspace: !MODAL_WORKSPACE_LABEL! ===

echo === Extracting warmup profile from benchmark workflow ===
python tools\extract_warmup_profile.py > "%TEMP%\_v2_warmup_profile.txt"
if errorlevel 1 (
    type "%TEMP%\_v2_warmup_profile.txt"
    echo === ERROR: Warmup profile derivation failed ===
    del "%TEMP%\_v2_warmup_profile.txt" 2>nul
    exit /b 1
)
for /f "usebackq delims=" %%a in ("%TEMP%\_v2_warmup_profile.txt") do set "%%a"
del "%TEMP%\_v2_warmup_profile.txt" 2>nul
echo === Warmup profile loaded ===

where modal >nul 2>nul
if not errorlevel 1 (
    set "MODAL_CLI=modal"
) else (
    set "MODAL_CLI=python -m modal"
)

REM ── Concurrent deployment via Python helper ────────────────────────────
set "V1_CMD_FILE=%TEMP%\_v1_deploy_cmd_%RANDOM%.bat"
set "V2_CMD_FILE=%TEMP%\_v2_deploy_cmd_%RANDOM%.bat"
set "V1_DEPLOY_LOG=%TEMP%\_v1_deploy.txt"
set "V2_DEPLOY_LOG=%TEMP%\_v2_deploy.txt"
set "DEPLOY_RESULT_LOG=%TEMP%\_deploy_result_%RANDOM%.txt"

REM Write tiny command files so the Python helper receives pre-resolved args.
REM Escape percent signs so each worker evaluates its own exit code at runtime.
> "%V1_CMD_FILE%" echo @echo off
>>"%V1_CMD_FILE%" echo %MODAL_CLI% deploy comfyapp.py
>>"%V1_CMD_FILE%" echo exit /b %%errorlevel%%
> "%V2_CMD_FILE%" echo @echo off
>>"%V2_CMD_FILE%" echo %MODAL_CLI% deploy -m comfymodal_runtime.modal_app
>>"%V2_CMD_FILE%" echo exit /b %%errorlevel%%

if not defined COMFYMODAL_DEPLOY_TIMEOUT_SECONDS set "COMFYMODAL_DEPLOY_TIMEOUT_SECONDS=3600"

echo === Deploying V1 (comfyui) and V2 (shadow) concurrently (timeout=%COMFYMODAL_DEPLOY_TIMEOUT_SECONDS%s) ===
python tools\run_deploys_concurrent.py ^
    "%V1_CMD_FILE%" "%V2_CMD_FILE%" ^
    "%V1_DEPLOY_LOG%" "%V2_DEPLOY_LOG%" ^
    "%COMFYMODAL_DEPLOY_TIMEOUT_SECONDS%" ^
    > "%DEPLOY_RESULT_LOG%"
set "PARALLEL_EXIT=%errorlevel%"

REM Remove command-file artifacts immediately (no longer needed)
del "%V1_CMD_FILE%" 2>nul
del "%V2_CMD_FILE%" 2>nul

REM Parse the key=value lines produced by the Python helper
set "V1_DEPLOY_EXIT="
set "V2_DEPLOY_EXIT="
set "TIMED_OUT="
for /f "usebackq tokens=1,* delims==" %%a in ("%DEPLOY_RESULT_LOG%") do (
    if "%%a"=="V1_EXIT" set "V1_DEPLOY_EXIT=%%b"
    if "%%a"=="V2_EXIT" set "V2_DEPLOY_EXIT=%%b"
    if "%%a"=="TIMED_OUT" set "TIMED_OUT=%%b"
)
del "%DEPLOY_RESULT_LOG%" 2>nul

REM Surface both deployment logs
echo.
echo === V1 deploy log ===
type "%V1_DEPLOY_LOG%" 2>nul
echo.
echo === V2 deploy log ===
type "%V2_DEPLOY_LOG%" 2>nul
echo.

REM Validate: timeout
if /i "!TIMED_OUT!"=="true" (
    echo === ERROR: Concurrent deploy timed out after %COMFYMODAL_DEPLOY_TIMEOUT_SECONDS%s ===
    del "%V1_DEPLOY_LOG%" 2>nul
    del "%V2_DEPLOY_LOG%" 2>nul
    exit /b 1
)

REM Validate: V1 exit code
if not defined V1_DEPLOY_EXIT set "V1_DEPLOY_EXIT=-1"
if !V1_DEPLOY_EXIT! neq 0 (
    echo === ERROR: V1 deploy failed with exit code !V1_DEPLOY_EXIT! ===
    del "%V1_DEPLOY_LOG%" 2>nul
    del "%V2_DEPLOY_LOG%" 2>nul
    exit /b !V1_DEPLOY_EXIT!
)

REM Validate: V2 exit code
if not defined V2_DEPLOY_EXIT set "V2_DEPLOY_EXIT=-1"
if !V2_DEPLOY_EXIT! neq 0 (
    echo === ERROR: V2 deploy failed with exit code !V2_DEPLOY_EXIT! ===
    del "%V1_DEPLOY_LOG%" 2>nul
    del "%V2_DEPLOY_LOG%" 2>nul
    exit /b !V2_DEPLOY_EXIT!
)

REM Validate: V1 output contains app identifier
findstr /C:"comfyui" "%V1_DEPLOY_LOG%" >nul 2>nul
if errorlevel 1 (
    echo === ERROR: V1 deploy output missing 'comfyui' app identifier ===
    del "%V1_DEPLOY_LOG%" 2>nul
    del "%V2_DEPLOY_LOG%" 2>nul
    exit /b 1
)

REM Validate: V2 output contains app and class identifiers
findstr /C:"stable-modal-comfy-v2-shadow" "%V2_DEPLOY_LOG%" >nul 2>nul
if errorlevel 1 (
    echo === ERROR: V2 deploy output missing shadow app identifier ===
    del "%V1_DEPLOY_LOG%" 2>nul
    del "%V2_DEPLOY_LOG%" 2>nul
    exit /b 1
)
findstr /C:"ModalRuntimeEntrypointV2" "%V2_DEPLOY_LOG%" >nul 2>nul
if errorlevel 1 (
    echo === ERROR: V2 deploy output missing V2 class identifier ===
    del "%V1_DEPLOY_LOG%" 2>nul
    del "%V2_DEPLOY_LOG%" 2>nul
    exit /b 1
)

REM Clean deploy logs
del "%V1_DEPLOY_LOG%" 2>nul
del "%V2_DEPLOY_LOG%" 2>nul

echo === V1 and V2 deploys both verified OK ===

echo === Running one V2 benchmark trial ===
python tools\benchmark_v2_direct.py
if errorlevel 1 (
    echo === ERROR: Benchmark failed ===
    exit /b 1
)
echo === Single V2 deploy and run completed ===
exit /b 0
