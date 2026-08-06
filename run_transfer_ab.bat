@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

set "REPO_ROOT=%~dp0"
cd /d "%REPO_ROOT%" || exit /b 1

:: Load active workspace credentials
set "IDX=0"
for /f "usebackq delims=" %%a in (`python -c "import json,sys;d=json.load(open('.modal_workspaces.json'));aid=d.get('active_workspace_id');ws=next((w for w in d.get('workspaces',[])if w.get('id')==aid),None);tid=ws and ws.get('token_id')or'';ts=ws and ws.get('token_secret')or'';sys.exit(1)if not(aid and ws and tid and ts)else None;print(tid);print(ts)"`) do (
    if !IDX! equ 0 set "MODAL_TOKEN_ID=%%a"
    if !IDX! equ 1 set "MODAL_TOKEN_SECRET=%%a"
    set /a IDX+=1
)
if !IDX! lss 2 (
    echo ERROR: could not load workspace credentials
    exit /b 1
)
set "COMFYMODAL_V2_APP_NAME=stable-modal-comfy-v2-shadow"
set "COMFYMODAL_V2_CLASS_NAME=ModalRuntimeEntrypointV2"
set "COMFYMODAL_V2_GPU=rtx-pro-6000"
set "COMFYMODAL_V2_VARIANCE_APP_NAME=stable-modal-comfy-v2-shadow"
set "COMFYMODAL_V2_ENV_PROFILE=production"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

:: Interleaved A/B: 10 valid cold per condition, cap 15 attempts per condition,
:: 25s cold gaps, minimal teardown (production config), both arms diagnostics ON.
set "V2_TRANSFER_AB_TARGET_COLD=10"
set "V2_TRANSFER_AB_MAX_ATTEMPTS_PER_CONDITION=15"
set "V2_VARIANCE_COLD_GAP_SECONDS=25"

python tools\benchmark_v2_direct.py --transfer-ab --teardown minimal
set "EXIT=%errorlevel%"
echo === TRANSFER_AB_EXIT=%EXIT% ===
exit /b %EXIT%
