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

echo === Running one V2 benchmark trial against the existing deployment ===
echo === Deploy first with deploy_and_run_v2_single.bat after source or env changes ===
python tools\benchmark_v2_direct.py
if errorlevel 1 (
    echo === ERROR: Benchmark failed ===
    exit /b 1
)
echo === Single V2 benchmark completed ===
exit /b 0
