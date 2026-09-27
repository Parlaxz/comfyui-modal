@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
set "REPO_ROOT=%~dp0"
cd /d "%REPO_ROOT%" || exit /b 1

if not defined COMFYMODAL_E16_APP_NAME set "COMFYMODAL_E16_APP_NAME=comfyui-modal-e16-source-io"
if not defined COMFYMODAL_V2_GPU set "COMFYMODAL_V2_GPU=rtx-pro-6000"
set "COMFYMODAL_E16_SOURCE_BENCHMARK=1"
set "COMFYMODAL_V2_STAGED_SOURCE_ORDER=1"
set "COMFYMODAL_V2_CLOUD="
set "COMFYMODAL_V2_REGION="
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

set "RUN_ID=%~1"
if not defined RUN_ID set "RUN_ID=RUN1"
set "ORDER=CLIP_CURRENT_FIRST"
if /i "!RUN_ID!"=="RUN2" set "ORDER=CLIP_SOURCE_FIRST"
set "OUTPUT=%~2"
if not defined OUTPUT set "OUTPUT=V2_BATCH_E16_!RUN_ID!.json"

set "IDX=0"
for /f "usebackq delims=" %%a in (`python -c "import json,sys;d=json.load(open('.modal_workspaces.json'));aid=d.get('active_workspace_id');ws=next((w for w in d.get('workspaces',[]) if w.get('id')==aid),None);sys.exit(1) if not ws else None;print(ws.get('token_id',''));print(ws.get('token_secret',''))"`) do (
    if !IDX! equ 0 set "MODAL_TOKEN_ID=%%a"
    if !IDX! equ 1 set "MODAL_TOKEN_SECRET=%%a"
    set /a IDX+=1
)
if !IDX! lss 2 exit /b 1

where modal >nul 2>nul
if not errorlevel 1 (set "MODAL_CLI=modal") else (set "MODAL_CLI=python -m modal")
echo === Running E16 !RUN_ID!: order=!ORDER! ===
echo output=!OUTPUT!
!MODAL_CLI! run -m e16_source_io_modal --run-id "!RUN_ID!" --strategy-order "!ORDER!" --output "!OUTPUT!"
set "EXIT=!errorlevel!"
echo === E16_REQUEST_EXIT=!EXIT! ===
exit /b !EXIT!
