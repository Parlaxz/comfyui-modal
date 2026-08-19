@echo off
setlocal enabledelayedexpansion

:: Console code page
chcp 65001 >nul

:: Pin V2 full-trace environment variables
set "COMFYMODAL_V2_APP_NAME=stable-modal-comfy-v2-shadow"
set "COMFYMODAL_V2_CLASS_NAME=ModalRuntimeEntrypointV2"
set "COMFYMODAL_V2_GPU=rtx-pro-6000"
set "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=1"
set "COMFYMODAL_V2_FULL_TRACE=1"
set "COMFYMODAL_V2_FULL_TRACE_TORCH=0"
set "COMFYMODAL_V2_FULL_TRACE_ENTRIES=8000000"
set "COMFYMODAL_V2_FULL_TRACE_RESOURCE_INTERVAL_MS=50"
set "COMFYMODAL_V2_PROFILE_VOLUME=comfymodal-v2-profiles"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
:: Diagnostic deploy uses the verified 48 GiB production baseline.
if not defined COMFYMODAL_V2_MEMORY_MB set "COMFYMODAL_V2_MEMORY_MB=49152"
if not defined COMFYMODAL_V2_BASELINE_MEMORY_REQUEST set "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST=49152"
if not defined COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST set "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST=0"

:: Repo root = script directory, safe from any CWD
set "REPO_ROOT=%~dp0"
cd /d "%REPO_ROOT%" || exit /b 1

:: Load active workspace credentials from .modal_workspaces.json
:: Values are captured into env vars via python stdout — never echoed.
echo === Loading active workspace ===
set "IDX=0"
for /f "usebackq delims=" %%a in (`python -c "import json,sys;d=json.load(open('.modal_workspaces.json'));aid=d.get('active_workspace_id');ws=next((w for w in d.get('workspaces',[]) if w.get('id')==aid),None);tid=ws and ws.get('token_id') or '';ts=ws and ws.get('token_secret') or '';label=ws and ws.get('label','') or '';sys.exit(1) if not(aid and ws and tid and ts) else None;print(tid);print(ts);print(label)"`) do (
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

:: Derive warmup profile from benchmark workflow
echo === Extracting warmup profile ===
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

:: Resolve modal CLI
where modal >nul 2>nul
if not errorlevel 1 (
    set "MODAL_CLI=modal"
) else (
    set "MODAL_CLI=python -m modal"
)

echo === Deploying V2 full-trace app ===

:: Deploy V2 module, capture output to temporary log
%MODAL_CLI% deploy -m comfymodal_runtime.modal_app > "%TEMP%\_v2_deploy.txt" 2>&1
set "DEPLOY_EXIT=%errorlevel%"
type "%TEMP%\_v2_deploy.txt"

:: Fail on deploy error
if !DEPLOY_EXIT! neq 0 (
    echo === ERROR: Deploy failed with exit code !DEPLOY_EXIT! ===
    del "%TEMP%\_v2_deploy.txt" 2>nul
    exit /b !DEPLOY_EXIT!
)

:: Verify deploy output contains expected app identifier
findstr /C:"stable-modal-comfy-v2-shadow" "%TEMP%\_v2_deploy.txt" >nul
if errorlevel 1 (
    echo === ERROR: Deploy output missing 'stable-modal-comfy-v2-shadow' ===
    del "%TEMP%\_v2_deploy.txt" 2>nul
    exit /b 1
)

:: Verify deploy output contains expected class identifier
findstr /C:"ModalRuntimeEntrypointV2" "%TEMP%\_v2_deploy.txt" >nul
if errorlevel 1 (
    echo === ERROR: Deploy output missing 'ModalRuntimeEntrypointV2' ===
    del "%TEMP%\_v2_deploy.txt" 2>nul
    exit /b 1
)

:: Clean temp log
del "%TEMP%\_v2_deploy.txt" 2>nul

echo === Deploy verified OK ===
exit /b 0
