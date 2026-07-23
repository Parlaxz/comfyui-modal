@echo off
setlocal enabledelayedexpansion

:: Console code page
chcp 65001 >nul

:: Pin environment variables
set "COMFYMODAL_V2_APP_NAME=stable-modal-comfy-v2-shadow"
set "COMFYMODAL_V2_CLASS_NAME=ModalRuntimeEntrypointV2"
set "COMFYMODAL_V2_GPU=rtx-pro-6000"
set "COMFYMODAL_V2_DEEP_MODEL_DIAG=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
set "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=1"
if not defined COMFYMODAL_V2_MEMORY_MB set "COMFYMODAL_V2_MEMORY_MB=49152"

:: Repo root = script directory, safe from any CWD
set "REPO_ROOT=%~dp0"
cd /d "%REPO_ROOT%" || exit /b 1

:: Load active workspace credentials from .modal_workspaces.json
echo === Loading active workspace ===
set "IDX=0"
for /f "usebackq delims=" %%a in (`python -c "import json,sys;d=json.load(open('.modal_workspaces.json'));aid=d.get('active_workspace_id');ws=next((w for w in d.get('workspaces',[])if w.get('id')==aid),None);tid=ws and ws.get('token_id')or'';ts=ws and ws.get('token_secret')or'';label=ws and ws.get('label','')or'';sys.exit(1)if not(aid and ws and tid and ts)else None;print(tid);print(ts);print(label)"`) do (
    if !IDX! equ 0 set "MODAL_TOKEN_ID=%%a"
    if !IDX! equ 1 set "MODAL_TOKEN_SECRET=%%a"
    if !IDX! equ 2 set "MODAL_WORKSPACE_LABEL=%%a"
    set /a IDX+=1
)
if !IDX! lss 3 (
    echo === ERROR: Could not load active workspace credentials from .modal_workspaces.json ===
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

echo === Deploying V2 shadow app ===

:: Prefer modal CLI, fall back to python -m modal
where modal >nul 2>nul
if not errorlevel 1 (
    set "MODAL_CLI=modal"
) else (
    set "MODAL_CLI=python -m modal"
)

:: Deploy V2 module, capture output
%MODAL_CLI% deploy -m comfymodal_runtime.modal_app > "%TEMP%\_v2_deploy.txt" 2>&1
set "DEPLOY_EXIT=%errorlevel%"
type "%TEMP%\_v2_deploy.txt"

:: Fail on deploy error
if %DEPLOY_EXIT% neq 0 (
    echo === ERROR: Deploy failed with exit code %DEPLOY_EXIT% ===
    del "%TEMP%\_v2_deploy.txt" 2>nul
    exit /b %DEPLOY_EXIT%
)

:: Fail unless output contains both expected identifiers
findstr /C:"stable-modal-comfy-v2-shadow" "%TEMP%\_v2_deploy.txt" >nul
if errorlevel 1 (
    echo === ERROR: Deploy output missing 'stable-modal-comfy-v2-shadow' ===
    del "%TEMP%\_v2_deploy.txt" 2>nul
    exit /b 1
)
findstr /C:"ModalRuntimeEntrypointV2" "%TEMP%\_v2_deploy.txt" >nul
if errorlevel 1 (
    echo === ERROR: Deploy output missing 'ModalRuntimeEntrypointV2' ===
    del "%TEMP%\_v2_deploy.txt" 2>nul
    exit /b 1
)

del "%TEMP%\_v2_deploy.txt" 2>nul
echo === Deploy verified OK ===

:: Run exactly one V2 direct cold benchmark trial
echo === Running V2 direct benchmark (1 cold trial) ===
set "V2_BENCHMARK_RUNS=1"
set "V2_BENCHMARK_GAP_SECONDS=0"
python tools\benchmark_v2_direct.py
set "BENCHMARK_EXIT=%errorlevel%"
if %BENCHMARK_EXIT% neq 0 (
    echo === ERROR: Benchmark failed with exit code %BENCHMARK_EXIT% ===
    exit /b %BENCHMARK_EXIT%
)

echo === All V2 benchmarks completed successfully ===
exit /b 0
