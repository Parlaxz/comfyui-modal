@echo off
setlocal enabledelayedexpansion
for /f %%a in ('powershell -NoProfile -Command "[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()"') do set "COMMAND_START_MS=%%a"

chcp 65001 >nul
if not defined COMFYMODAL_V2_APP_NAME set "COMFYMODAL_V2_APP_NAME=stable-modal-comfy-v2-shadow"
set "COMFYMODAL_V2_CLASS_NAME=ModalRuntimeEntrypointV2"
if not defined COMFYMODAL_V2_GPU set "COMFYMODAL_V2_GPU=rtx-pro-6000"
if not defined COMFYMODAL_V2_RESTORE_ONLY_APP_NAME set "COMFYMODAL_V2_RESTORE_ONLY_APP_NAME=stable-modal-comfy-v2-restore-only-shadow"
set "COMFYMODAL_V2_CLOUD="
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
if not defined COMFYMODAL_V2_NATIVE_FAST_DISK_UNET set "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET=0"
if not defined COMFYMODAL_V2_PUBLISH_RESTORE_PLAN set "COMFYMODAL_V2_PUBLISH_RESTORE_PLAN=0"
if not defined COMFYMODAL_V2_VAE_SNAPSHOT set "COMFYMODAL_V2_VAE_SNAPSHOT=1"
if not defined COMFYMODAL_V2_CLIP_CONDITIONING_CACHE set "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE=1"
if not defined COMFYMODAL_V2_UNET_ACTIVATION_MODE set "COMFYMODAL_V2_UNET_ACTIVATION_MODE=late"
if not defined COMFYMODAL_V2_VAE_ACTIVATION_MODE set "COMFYMODAL_V2_VAE_ACTIVATION_MODE=sampling_end"
if not defined COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE set "COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE=1"
if not defined V2_BENCHMARK_RUNS set "V2_BENCHMARK_RUNS=1"
if not defined V2_BENCHMARK_GAP_SECONDS set "V2_BENCHMARK_GAP_SECONDS=0"
if not defined V2_VOLUME_READ_RUN_COUNT set "V2_VOLUME_READ_RUN_COUNT=3"
if not defined V2_VOLUME_READ_GAP_SECONDS set "V2_VOLUME_READ_GAP_SECONDS=25"
if not defined V2_RESTORE_ONLY_RUN_COUNT set "V2_RESTORE_ONLY_RUN_COUNT=6"
if not defined V2_RESTORE_ONLY_MAX_ATTEMPTS set "V2_RESTORE_ONLY_MAX_ATTEMPTS=40"
if not defined V2_RESTORE_ONLY_GAP_SECONDS set "V2_RESTORE_ONLY_GAP_SECONDS=30"
if not defined COMFYMODAL_V2_THREAD_POLICY set "COMFYMODAL_V2_THREAD_POLICY=TBASE"
if not defined COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER set "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER=O0"
if not defined COMFYMODAL_V2_MEMORY_MB set "COMFYMODAL_V2_MEMORY_MB=32768"
if not defined COMFYMODAL_V2_CPU_REQUEST set "COMFYMODAL_V2_CPU_REQUEST=12"
if not defined COMFYMODAL_V2_VAE_POLICY set "COMFYMODAL_V2_VAE_POLICY=v1"
if not defined COMFYMODAL_V2_BASELINE_CPU_REQUEST set "COMFYMODAL_V2_BASELINE_CPU_REQUEST=12"
if not defined COMFYMODAL_V2_BASELINE_MEMORY_REQUEST set "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST=32768"
if /i "!COMFYMODAL_V2_ENV_PROFILE!"=="production" if not defined COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST set "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST=1"
if not defined COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST set "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST=0"

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
set "V2_PROFILE_PRETOUCH=0"
if defined V2_VARIANCE_PRETOUCH set "V2_PROFILE_PRETOUCH=!V2_VARIANCE_PRETOUCH!"
echo [v2.env_profile]
echo env_profile=!COMFYMODAL_V2_ENV_PROFILE!
echo thread_policy=!COMFYMODAL_V2_THREAD_POLICY!
echo snapshot_model_order=!COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER!
echo baseline_cpu_request=!COMFYMODAL_V2_BASELINE_CPU_REQUEST!
echo baseline_memory_request=!COMFYMODAL_V2_BASELINE_MEMORY_REQUEST!
echo memory_request_mb=!COMFYMODAL_V2_MEMORY_MB!
echo vae_policy=!COMFYMODAL_V2_VAE_POLICY!
echo release_gpu_after_request=!COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST!
echo cpu_model_snapshot=!COMFYMODAL_V2_CPU_MODEL_SNAPSHOT!
echo native_fast_disk_unet=!COMFYMODAL_V2_NATIVE_FAST_DISK_UNET!
echo publish_restore_plan=!COMFYMODAL_V2_PUBLISH_RESTORE_PLAN!
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
echo variance_pretouch=!V2_PROFILE_PRETOUCH!
echo volume_read_run_count=!V2_VOLUME_READ_RUN_COUNT!
echo restore_only_app=!COMFYMODAL_V2_RESTORE_ONLY_APP_NAME!
echo restore_only_run_count=!V2_RESTORE_ONLY_RUN_COUNT!
echo snapshot_exclude_unet=!COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET!

set "COMFYMODAL_COMMAND_START_UNIX_MS=!COMMAND_START_MS!"
REM -- Benchmark invocation ------------------------------------------
REM Default: V2_BENCHMARK_RUNS=1 -> exactly one run.  The acceptance
REM sequence (A/B/C, ~3+ requests) runs ONLY via the explicit opt-in env
REM V2_BENCHMARK_MODE=acceptance.  The variance-cold sequence (one request
REM at a time, 25s gap, strict cold-identity proof) runs ONLY via the
REM explicit opt-in V2_BENCHMARK_MODE=variance_cold.  The four-condition
REM round-robin matrix runs ONLY via the explicit opt-in
REM V2_BENCHMARK_MODE=variance_matrix.  The mounted-Volume raw
REM sequential-read benchmark (pure volume read speed, no model workload)
REM runs ONLY via the explicit opt-in V2_BENCHMARK_MODE=volume_read.
REM The UNET-absent snapshot restore-only mode issues EXACTLY 6 valid
REM reused-snapshot restore-only probes (V2_RESTORE_ONLY_RUN_COUNT) against
REM the deployment built by deploy_and_run_v2_single.bat (that deploy
REM invocation is the labeled/excluded snapshot construction, which builds
REM the full CLIP/UNET/VAE snapshot and then evicts the UNET with the
REM clip_vae retain role ??? keeping fresh CLIP+VAE in the retained container ???
REM before capture).  COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET=1 is the identity/
REM reporting gate only.  Provider/region unpinned; the harness hard-stops
REM at 6 valid, invalid probes never count, no beautification probes.  Runs
REM ONLY via the explicit opt-in V2_BENCHMARK_MODE=snapshot_restore_only.
if /i "!V2_BENCHMARK_MODE!"=="variance_matrix" (
    echo === Running V2 variance-cold MATRIX - explicit opt-in ===
    set "COMFYMODAL_V2_APP_NAME=stable-modal-comfy-v2-variance-shadow"
    set "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS=1"
    set "COMFYMODAL_V2_UNET_PRETOUCH=!V2_PROFILE_PRETOUCH!"
    if not defined V2_VARIANCE_COLD_GAP_SECONDS set "V2_VARIANCE_COLD_GAP_SECONDS=25"
    python tools\benchmark_v2_direct.py --variance-matrix
) else if /i "!V2_BENCHMARK_MODE!"=="variance_cold" (
    echo === Running V2 variance-cold benchmark - explicit opt-in ===
    set "COMFYMODAL_V2_APP_NAME=stable-modal-comfy-v2-variance-shadow"
    set "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS=1"
    set "COMFYMODAL_V2_UNET_PRETOUCH=!V2_PROFILE_PRETOUCH!"
    if not defined V2_VARIANCE_COLD_GAP_SECONDS set "V2_VARIANCE_COLD_GAP_SECONDS=25"
    if not defined V2_VARIANCE_RUN_COUNT set "V2_VARIANCE_RUN_COUNT=!V2_BENCHMARK_RUNS!"
    python tools\benchmark_v2_direct.py --variance-cold --variance-pretouch !V2_PROFILE_PRETOUCH!
) else if /i "!V2_BENCHMARK_MODE!"=="acceptance" (
    echo === Running V2 acceptance benchmark - explicit opt-in ===
    python tools\benchmark_v2_direct.py --acceptance
) else if /i "!V2_BENCHMARK_MODE!"=="host_ab" (
    echo === Running V2 host-characteristics cold study - explicit opt-in ===
    set "COMFYMODAL_V2_APP_NAME=stable-modal-comfy-v2-variance-shadow"
    set "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS=1"
    if not defined V2_VARIANCE_COLD_GAP_SECONDS set "V2_VARIANCE_COLD_GAP_SECONDS=25"
    python tools\benchmark_v2_direct.py --host-ab --teardown minimal
) else if /i "!V2_BENCHMARK_MODE!"=="volume_read" (
    echo === Running V2 mounted-Volume raw sequential-read benchmark - explicit opt-in ===
    python tools\benchmark_v2_direct.py --volume-read
) else if /i "!V2_BENCHMARK_MODE!"=="snapshot_restore_only" (
    echo === Running V2 UNET-absent snapshot restore-only probes - explicit opt-in ===
    set "COMFYMODAL_V2_APP_NAME=!COMFYMODAL_V2_RESTORE_ONLY_APP_NAME!"
    set "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET=1"
    REM Identity/eviction contract mirrors the deploy invocation:
    REM evict UNET before snapshot capture, retain CLIP+VAE in the kept
    REM container, restore idle 0, inherit profile; never production.
    set "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT=1"
    set "COMFYMODAL_V2_EVICT_RETAIN_ROLE=clip_vae"
    set "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS=0"
    REM Forced instead of "if not defined" so a user's global production profile
    REM can never re-enable the production branch and wipe the eviction vars.
    set "COMFYMODAL_V2_ENV_PROFILE=inherit"
    python tools\benchmark_v2_direct.py --snapshot-restore-only
) else (
    echo === Running one V2 benchmark trial against the existing deployment ===
    echo === Deploy first with deploy_and_run_v2_single.bat after source or env changes ===
    python tools\benchmark_v2_direct.py %*
)
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
