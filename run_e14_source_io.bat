@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

set "REPO_ROOT=%~dp0"
cd /d "%REPO_ROOT%" || exit /b 1

:: Source-only safetensors source-I/O benchmark (e14) wrapper.
:: Local, standard-library-only harness. No Modal, no network, no deploy.
if not defined E14_BLOCK_MIB set "E14_BLOCK_MIB=256"
if not defined E14_RANGE_MIB set "E14_RANGE_MIB=32"
if not defined E14_CACHE_LABEL set "E14_CACHE_LABEL=cold_unknown"

set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

:: Require at least one user-supplied path (file or directory).
if "%~1"=="" (
    echo ERROR: at least one safetensors path is required.
    echo Usage: run_e14_source_io.bat PATH [PATH ...] [--arm ARM] [--json-out FILE] ...
    exit /b 1
)

echo === Source-only source-I/O benchmark (e14): no Modal, no deploy ===
echo block_mib=!E14_BLOCK_MIB! range_mib=!E14_RANGE_MIB! cache_label=!E14_CACHE_LABEL!

python tools\benchmark_source_io_e14.py --block-mib !E14_BLOCK_MIB! --range-mib !E14_RANGE_MIB! --cache-label !E14_CACHE_LABEL! %*
set "EXIT=!errorlevel!"
echo === E14_SOURCE_IO_EXIT=!EXIT! ===
exit /b !EXIT!
