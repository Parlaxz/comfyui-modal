@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

set "REPO_ROOT=%~dp0"
cd /d "%REPO_ROOT%" || exit /b 1

:: Verified production configuration for the shadow benchmark app
set "COMFYMODAL_V2_APP_NAME=stable-modal-comfy-v2-shadow"
set "COMFYMODAL_V2_CLASS_NAME=ModalRuntimeEntrypointV2"
set "COMFYMODAL_V2_GPU=rtx-pro-6000"
set "COMFYMODAL_V2_DEEP_MODEL_DIAG=1"
set "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=1"
set "COMFYMODAL_V2_MEMORY_MB=49152"
set "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST=49152"
set "COMFYMODAL_V2_SINGLE_USE_CONTAINERS=1"
set "COMFYMODAL_V2_VAE_SNAPSHOT=1"
set "COMFYMODAL_EXACT_CLIP_CONDITIONING_CACHE=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

:: Load active workspace credentials from .modal_workspaces.json
set "IDX=0"
for /f "usebackq delims=" %%a in (`python -c "import json,sys;d=json.load(open('.modal_workspaces.json'));aid=d.get('active_workspace_id');ws=next((w for w in d.get('workspaces',[])if w.get('id')==aid),None);tid=ws and ws.get('token_id')or'';ts=ws and ws.get('token_secret')or'';label=ws and ws.get('label','')or'';sys.exit(1)if not(aid and ws and tid and ts)else None;print(tid);print(ts);print(label)"`) do (
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

:: Warmup profile from the benchmark workflow
echo === Extracting warmup profile ===
python tools\extract_warmup_profile.py > "%TEMP%\_v2_warmup_profile.txt"
if errorlevel 1 (
    type "%TEMP%\_v2_warmup_profile.txt"
    del "%TEMP%\_v2_warmup_profile.txt" 2>nul
    exit /b 1
)
for /f "usebackq delims=" %%a in ("%TEMP%\_v2_warmup_profile.txt") do set "%%a"
del "%TEMP%\_v2_warmup_profile.txt" 2>nul

echo === Deploying V2 shadow app ===
where modal >nul 2>nul
if not errorlevel 1 (
    set "MODAL_CLI=modal"
) else (
    set "MODAL_CLI=python -m modal"
)

%MODAL_CLI% deploy -m comfymodal_runtime.modal_app > "%TEMP%\_v2_deploy.txt" 2>&1
set "DEPLOY_EXIT=%errorlevel%"
type "%TEMP%\_v2_deploy.txt"
if %DEPLOY_EXIT% neq 0 (
    del "%TEMP%\_v2_deploy.txt" 2>nul
    exit /b %DEPLOY_EXIT%
)
findstr /C:"stable-modal-comfy-v2-shadow" "%TEMP%\_v2_deploy.txt" >nul
if errorlevel 1 (
    del "%TEMP%\_v2_deploy.txt" 2>nul
    echo === ERROR: deploy output missing app name ===
    exit /b 1
)
del "%TEMP%\_v2_deploy.txt" 2>nul
echo === Deploy verified OK ===
exit /b 0
