@echo off
setlocal enabledelayedexpansion
for /f %%a in ('powershell -NoProfile -Command "[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()"') do set "COMMAND_START_MS=%%a"

chcp 65001 >nul
REM -- E25 whole-critical-path validation selector (atomic opt-in) -----------
REM Run-side mirror of the deploy selector: sets the five E25 validation flags
REM for the request environment.  The deployed container must have been built
REM with the same selector (deploy_and_run_v2_single.bat E25_VALIDATION).
if not defined V2_E25_VALIDATION set "V2_E25_VALIDATION=0"
set "V2_E25_VALIDATION_ACTIVE=0"
if /i "!V2_E25_VALIDATION!"=="1" set "V2_E25_VALIDATION_ACTIVE=1"
if /i "!V2_E25_VALIDATION!"=="true" set "V2_E25_VALIDATION_ACTIVE=1"
if /i "!V2_E25_VALIDATION!"=="yes" set "V2_E25_VALIDATION_ACTIVE=1"
if /i "!V2_E25_VALIDATION!"=="on" set "V2_E25_VALIDATION_ACTIVE=1"
if "!V2_E25_VALIDATION_ACTIVE!"=="1" (
    REM The E25 validation inherits the E19 base (deployed atomic profile is
    REM E19_FINAL_COLD_LOADER); the request-side preflight requires the same
    REM selector so the atomic-profile check passes.  E26: VAE is the
    REM canonical late/safe production mode (early activation is OFF).
    set "V2_E19_FINAL_COLD_LOADER=1"
    set "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION=1"
    set "COMFYMODAL_V2_GPU_FAST_RETURN=1"
    set "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS=1"
    set "COMFYMODAL_V2_VAE_ACTIVATION_MODE=late"
    set "COMFYMODAL_V2_VAE_EARLY_START_MS=0"
    if not defined V2_E25_CONDITIONING_NONCE set "V2_E25_CONDITIONING_NONCE=%RANDOM%-%RANDOM%-%RANDOM%"
    set "V2_BENCHMARK_RUNS=1"
    echo [v2.e25_validation] run_selector=ACTIVE speculative_clip=1 gpu_fast_return=1 opt_diag=1 vae_mode=late vae_early=0 runs=1
)
REM -- E26 concrete cold-wins validation selector (atomic opt-in) -----------
REM Run-side mirror of the deploy selector: sets the E26 validation flags for
REM the request environment.  The deployed container must have been built
REM with the same selector (deploy_and_run_v2_single.bat E26_VALIDATION).
REM Cycle = exactly two --run-count 1 requests on one deployment.
if not defined V2_E26_VALIDATION set "V2_E26_VALIDATION=0"
set "V2_E26_VALIDATION_ACTIVE=0"
if /i "!V2_E26_VALIDATION!"=="1" set "V2_E26_VALIDATION_ACTIVE=1"
if /i "!V2_E26_VALIDATION!"=="true" set "V2_E26_VALIDATION_ACTIVE=1"
if /i "!V2_E26_VALIDATION!"=="yes" set "V2_E26_VALIDATION_ACTIVE=1"
if /i "!V2_E26_VALIDATION!"=="on" set "V2_E26_VALIDATION_ACTIVE=1"
if "!V2_E26_VALIDATION_ACTIVE!"=="1" (
    REM Inherits the E19 base (deployed atomic profile is
    REM E19_FINAL_COLD_LOADER); the request-side preflight requires the same
    REM selector so the atomic-profile check passes.
    set "V2_E19_FINAL_COLD_LOADER=1"
    set "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION=1"
    set "COMFYMODAL_V2_GPU_FAST_RETURN=1"
    set "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS=1"
    set "COMFYMODAL_V2_VAE_ACTIVATION_MODE=late"
    set "COMFYMODAL_V2_VAE_EARLY_START_MS=0"
    set "COMFYMODAL_V2_CHECKPOINT_PREWARM=1"
    if not defined V2_E26_CONDITIONING_NONCE set "V2_E26_CONDITIONING_NONCE=%RANDOM%-%RANDOM%-%RANDOM%"
    set "V2_BENCHMARK_RUNS=1"
    echo [v2.e26_validation] run_selector=ACTIVE speculative_clip=1 gpu_fast_return=1 opt_diag=1 vae_mode=late vae_early=0 checkpoint_prewarm=1 runs=1
)
REM -- E28 critical-path validation selector (atomic opt-in) -----------------
REM Run-side mirror of the deploy selector: sets the E28 validation flags for
REM the request environment.  The deployed container must have been built
REM with the same selector (deploy_and_run_v2_single.bat E28_VALIDATION).
REM -- E37 late CLIP validation selector (atomic opt-in) ----------------------
REM E37 shares E19's full-generation base, but does not force E28 restore or
REM diagnostic settings.  QD/FASTSAFE, late policy, minimal restore, and
REM strict-proof values remain profile-provided and are verified locally.
if not defined V2_E37_VALIDATION set "V2_E37_VALIDATION=0"
if /i "%~1"=="E37_VALIDATION" set "V2_E37_VALIDATION=1"
if /i "!COMFYMODAL_V2_E37_STRICT_PROOF!"=="1" set "V2_E37_VALIDATION=1"
set "V2_E37_CLEAN_LANE_ACTIVE=0"
if /i "%~1"=="E37_CLEAN_LANE_VALIDATION" set "V2_E37_CLEAN_LANE_ACTIVE=1"
if /i "!COMFYMODAL_V2_E37_CLEAN_LANE!"=="1" set "V2_E37_CLEAN_LANE_ACTIVE=1"
if /i "!COMFYMODAL_V2_CLEAN_LANE!"=="1" set "V2_E37_CLEAN_LANE_ACTIVE=1"
if "!V2_E37_CLEAN_LANE_ACTIVE!"=="1" set "V2_E19_FINAL_COLD_LOADER=0"
if "!V2_E37_CLEAN_LANE_ACTIVE!"=="1" set "V2_E28_VALIDATION=0"
if "!V2_E37_CLEAN_LANE_ACTIVE!"=="1" set "V2_E31_VALIDATION=0"
if /i "%~1"=="E37_CLEAN_LANE_VALIDATION" set "V2_E37_VALIDATION=1"
set "V2_E37_VALIDATION_ACTIVE=0"
if /i "!V2_E37_VALIDATION!"=="1" set "V2_E37_VALIDATION_ACTIVE=1"
if /i "!V2_E37_VALIDATION!"=="true" set "V2_E37_VALIDATION_ACTIVE=1"
if /i "!V2_E37_VALIDATION!"=="yes" set "V2_E37_VALIDATION_ACTIVE=1"
if /i "!V2_E37_VALIDATION!"=="on" set "V2_E37_VALIDATION_ACTIVE=1"
if "!V2_E37_VALIDATION_ACTIVE!"=="1" (
    if "!V2_E37_CLEAN_LANE_ACTIVE!"=="0" set "V2_E19_FINAL_COLD_LOADER=1"
    set "V2_E28_VALIDATION=0"
    set "V2_E31_VALIDATION=0"
    set "V2_BENCHMARK_MODE=e37_single"
    set "V2_BENCHMARK_RUNS=1"
    if not defined V2_E37_CONDITIONING_NONCE set "V2_E37_CONDITIONING_NONCE=%RANDOM%-%RANDOM%-%RANDOM%"
    echo [v2.e37_validation] run_selector=ACTIVE full_run=1 e19=1 nonce=present
)
if "!V2_E37_CLEAN_LANE_ACTIVE!"=="1" (
    set "COMFYMODAL_V2_E37_CLEAN_LANE=1"
    set "COMFYMODAL_V2_CLEAN_LANE=1"
    set "COMFYMODAL_V2_ATOMIC_PROFILE=E37_CLEAN_LANE"
    set "COMFYMODAL_V2_ENV_PROFILE=inherit"
    set "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET=0"
    set "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT=0"
    set "COMFYMODAL_V2_EVICT_RETAIN_ROLE=none"
    set "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS=0"
    set "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION=0"
    set "COMFYMODAL_V2_CHECKPOINT_PREWARM=0"
    set "COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS=0"
    set "COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB=0"
    set "COMFYMODAL_V2_UNET_FASTSAFETENSORS=0"
    set "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS=0"
    set "COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH=0"
    set "COMFYMODAL_V2_INPUT_TYPES_WARM=0"
    set "COMFYMODAL_V2_PREFILL_LANES=none"
    set "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET=0"
    set "COMFYMODAL_V2_EXECUTION_PREFILL=0"
    set "COMFYMODAL_V2_GRAPH_PRELOAD=0"
    set "COMFYMODAL_V2_MODEL_PRELOAD=0"
    set "COMFYMODAL_V2_EXACT_CACHE_PERSIST=0"
    set "COMFYMODAL_V2_ALLOCATOR_PURGE=0"
    set "COMFYMODAL_V2_BACKGROUND_PERSISTENCE=0"
    set "COMFYMODAL_V2_BACKGROUND_DIAGNOSTICS=0"
    set "V2_E28_VALIDATION=0"
    set "V2_E31_VALIDATION=0"
    set "V2_BENCHMARK_MODE=e37_single"
    set "V2_BENCHMARK_RUNS=1"
    if not defined V2_E37_CONDITIONING_NONCE set "V2_E37_CONDITIONING_NONCE=%RANDOM%-%RANDOM%-%RANDOM%"
    echo [v2.e37_clean_lane_validation] run_selector=ACTIVE full_run=1 e19=0 nonce=present
)
if not defined V2_E28_VALIDATION set "V2_E28_VALIDATION=0"
if /i "%~1"=="E28_VALIDATION" set "V2_E28_VALIDATION=1"
set "V2_E28_VALIDATION_ACTIVE=0"
if /i "!V2_E28_VALIDATION!"=="1" set "V2_E28_VALIDATION_ACTIVE=1"
if /i "!V2_E28_VALIDATION!"=="true" set "V2_E28_VALIDATION_ACTIVE=1"
if /i "!V2_E28_VALIDATION!"=="yes" set "V2_E28_VALIDATION_ACTIVE=1"
if /i "!V2_E28_VALIDATION!"=="on" set "V2_E28_VALIDATION_ACTIVE=1"
if "!V2_E28_VALIDATION_ACTIVE!"=="1" (
    set "V2_E19_FINAL_COLD_LOADER=1"
    set "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION=1"
    set "COMFYMODAL_V2_GPU_FAST_RETURN=1"
    set "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS=1"
    set "COMFYMODAL_V2_VAE_ACTIVATION_MODE=late"
    set "COMFYMODAL_V2_VAE_EARLY_START_MS=0"
    set "COMFYMODAL_V2_CHECKPOINT_PREWARM=1"
    set "COMFYMODAL_V2_GANTT_TELEMETRY=1"
    set "COMFYMODAL_V2_E27_FORENSICS=1"
    if not defined V2_E28_CONDITIONING_NONCE set "V2_E28_CONDITIONING_NONCE=%RANDOM%-%RANDOM%-%RANDOM%"
    set "V2_BENCHMARK_RUNS=1"
    echo [v2.e28_validation] run_selector=ACTIVE speculative_clip=1 gpu_fast_return=1 opt_diag=1 vae_mode=late checkpoint_prewarm=1 gantt=1 e27_forensics=1 runs=1
)
REM -- golden_p1 serial-Golden selector (atomic opt-in) ----------------------
REM Run-side mirror of the deploy selector: routes the request to
REM tools\benchmark_v2_direct.py --golden-p1.  Activation uses the SAME two
REM mechanisms as the existing selectors: the first positional argument
REM ("golden_p1") or the resolved profile env var
REM COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM=1 (set by v2ctl when the
REM golden_p1 profile is selected).  The flag itself is only established
REM when not already defined so a v2ctl-resolved environment is never
REM overwritten after resolution.  Explicit V2_BENCHMARK_MODE branches below
REM keep precedence, preserving every existing mode.
set "V2_GOLDEN_P1_ACTIVE=0"
if /i "%~1"=="golden_p1" set "V2_GOLDEN_P1_ACTIVE=1"
if /i "!COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM!"=="1" set "V2_GOLDEN_P1_ACTIVE=1"
if /i "!COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM!"=="true" set "V2_GOLDEN_P1_ACTIVE=1"
if /i "!COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM!"=="yes" set "V2_GOLDEN_P1_ACTIVE=1"
if /i "!COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM!"=="on" set "V2_GOLDEN_P1_ACTIVE=1"
if /i "!COMFYMODAL_V2CTL_PROFILE!"=="golden_p1" set "V2_GOLDEN_P1_ACTIVE=1"
if "!V2_GOLDEN_P1_ACTIVE!"=="1" (
    if not defined COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM set "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM=1"
    echo [v2.golden_p1] run_selector=ACTIVE golden_enable_dynamic_vram=!COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM!
    REM Golden must never inherit the run-only restore fallback.  Abort before
    REM credentials are loaded or any benchmark/Modal work is attempted.
    if not defined COMFYMODAL_V2_APP_NAME (
        echo === ERROR: golden_p1 requires COMFYMODAL_V2_APP_NAME=stable-modal-comfy-v2-golden-p1 ===
        exit /b 1
    )
    if /i not "!COMFYMODAL_V2_APP_NAME!"=="stable-modal-comfy-v2-golden-p1" (
        echo === ERROR: golden_p1 app identity mismatch: !COMFYMODAL_V2_APP_NAME! ===
        echo === Expected stable-modal-comfy-v2-golden-p1; refusing before any Modal work. ===
        exit /b 1
    )
)
if not defined COMFYMODAL_V2_APP_NAME set "COMFYMODAL_V2_APP_NAME=stable-modal-comfy-v2-restore-only-shadow"
set "COMFYMODAL_V2_CLASS_NAME=ModalRuntimeEntrypointV2"
if "!V2_E37_CLEAN_LANE_ACTIVE!"=="0" set "COMFYMODAL_V2_ATOMIC_PROFILE="
if not defined COMFYMODAL_V2_GPU set "COMFYMODAL_V2_GPU=rtx-pro-6000"
if not defined COMFYMODAL_V2_RESTORE_ONLY_APP_NAME set "COMFYMODAL_V2_RESTORE_ONLY_APP_NAME=stable-modal-comfy-v2-restore-only-shadow"
set "COMFYMODAL_V2_CLOUD="
if not defined COMFYMODAL_V2_ENV_PROFILE set "COMFYMODAL_V2_ENV_PROFILE=inherit"
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
if not defined COMFYMODAL_V2_NATIVE_FAST_DISK_UNET set "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET=1"
if not defined COMFYMODAL_V2_PUBLISH_RESTORE_PLAN set "COMFYMODAL_V2_PUBLISH_RESTORE_PLAN=0"
if not defined COMFYMODAL_V2_VAE_SNAPSHOT set "COMFYMODAL_V2_VAE_SNAPSHOT=1"
if not defined COMFYMODAL_V2_CLIP_CONDITIONING_CACHE set "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE=1"
if not defined COMFYMODAL_V2_UNET_ACTIVATION_MODE set "COMFYMODAL_V2_UNET_ACTIVATION_MODE=late"
if not defined COMFYMODAL_V2_VAE_ACTIVATION_MODE set "COMFYMODAL_V2_VAE_ACTIVATION_MODE=late"
if not defined COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE set "COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE=1"
if not defined V2_BENCHMARK_RUNS set "V2_BENCHMARK_RUNS=10"
if not defined V2_BENCHMARK_GAP_SECONDS set "V2_BENCHMARK_GAP_SECONDS=35"
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
REM -- D-phase runtime flags (Phase-D integration gate; defaults preserve production behavior) --
if not defined COMFYMODAL_V2_UNET_FASTSAFETENSORS set "COMFYMODAL_V2_UNET_FASTSAFETENSORS=0"
if not defined COMFYMODAL_V2_CLIP_FAST_HYDRATION set "COMFYMODAL_V2_CLIP_FAST_HYDRATION=0"
if not defined COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS set "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS=0"
if not defined COMFYMODAL_V2_CLIP_COLD_FORENSICS set "COMFYMODAL_V2_CLIP_COLD_FORENSICS=0"
if not defined COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST set "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST=0"
if not defined COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA set "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA=0"
if not defined COMFYMODAL_V2_INPUT_TYPES_WARM set "COMFYMODAL_V2_INPUT_TYPES_WARM=1"
if not defined COMFYMODAL_V2_UNET_FORENSICS set "COMFYMODAL_V2_UNET_FORENSICS=0"
if not defined COMFYMODAL_V2_C9QD_EXTRAS set "COMFYMODAL_V2_C9QD_EXTRAS=0"
REM -- E10 complete bucket-first B profile (atomic opt-in) -----------------
if not defined V2_E10_BUCKET_FIRST_VALIDATION set "V2_E10_BUCKET_FIRST_VALIDATION=0"
set "V2_E10_BUCKET_FIRST_VALIDATION_ACTIVE=0"
if /i "!V2_E10_BUCKET_FIRST_VALIDATION!"=="1" set "V2_E10_BUCKET_FIRST_VALIDATION_ACTIVE=1"
if /i "!V2_E10_BUCKET_FIRST_VALIDATION!"=="true" set "V2_E10_BUCKET_FIRST_VALIDATION_ACTIVE=1"
if /i "!V2_E10_BUCKET_FIRST_VALIDATION!"=="yes" set "V2_E10_BUCKET_FIRST_VALIDATION_ACTIVE=1"
if /i "!V2_E10_BUCKET_FIRST_VALIDATION!"=="on" set "V2_E10_BUCKET_FIRST_VALIDATION_ACTIVE=1"
if "!V2_E10_BUCKET_FIRST_VALIDATION_ACTIVE!"=="1" (
    set "V2_D10_INTEGRATION_VALIDATION=1"
    set "V2_D10_INTEGRATION_VALIDATION_ACTIVE=1"
    set "COMFYMODAL_V2_STAGED_SAFETENSORS=1"
    set "COMFYMODAL_V2_STAGED_PRODUCERS=4"
    set "COMFYMODAL_V2_STAGED_POOL_MB=1024"
    set "COMFYMODAL_V2_STAGED_BUCKET_MB=256"
    set "COMFYMODAL_V2_STAGED_CPU_CAST=1"
    set "COMFYMODAL_V2_STAGED_ASYNC_H2D=1"
    set "COMFYMODAL_V2_STAGED_CONTIGUOUS_GPU_BUCKETS=1"
    set "COMFYMODAL_V2_UNET_FASTSAFETENSORS=1"
    set "COMFYMODAL_V2_CLIP_FAST_HYDRATION=1"
    set "COMFYMODAL_V2_CLIP_STAGED_HYDRATION=1"
    set "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS=1"
    set "COMFYMODAL_V2_CLIP_COLD_FORENSICS=1"
    set "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST=1"
    set "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA=0"
    set "COMFYMODAL_V2_INPUT_TYPES_WARM=1"
    set "COMFYMODAL_V2_UNET_FORENSICS=0"
    set "COMFYMODAL_V2_CRITICAL_GPU_COORDINATION=1"
    set "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET=0"
)
set "V2_D6_FASTPATH_VALIDATION_ACTIVE=0"
if /i "!V2_D6_FASTPATH_VALIDATION!"=="1" set "V2_D6_FASTPATH_VALIDATION_ACTIVE=1"
if /i "!V2_D6_FASTPATH_VALIDATION!"=="true" set "V2_D6_FASTPATH_VALIDATION_ACTIVE=1"
if /i "!V2_D6_FASTPATH_VALIDATION!"=="yes" set "V2_D6_FASTPATH_VALIDATION_ACTIVE=1"
if /i "!V2_D6_FASTPATH_VALIDATION!"=="on" set "V2_D6_FASTPATH_VALIDATION_ACTIVE=1"
set "V2_D10_INTEGRATION_VALIDATION_ACTIVE=0"
if /i "!V2_D10_INTEGRATION_VALIDATION!"=="1" set "V2_D10_INTEGRATION_VALIDATION_ACTIVE=1"
if /i "!V2_D10_INTEGRATION_VALIDATION!"=="true" set "V2_D10_INTEGRATION_VALIDATION_ACTIVE=1"
if /i "!V2_D10_INTEGRATION_VALIDATION!"=="yes" set "V2_D10_INTEGRATION_VALIDATION_ACTIVE=1"
if /i "!V2_D10_INTEGRATION_VALIDATION!"=="on" set "V2_D10_INTEGRATION_VALIDATION_ACTIVE=1"
REM -- E19 final cold-loader profile (atomic opt-in) ----------------------
if not defined V2_E19_FINAL_COLD_LOADER set "V2_E19_FINAL_COLD_LOADER=0"
set "V2_E19_FINAL_COLD_LOADER_ACTIVE=0"
if /i "!V2_E19_FINAL_COLD_LOADER!"=="1" set "V2_E19_FINAL_COLD_LOADER_ACTIVE=1"
if /i "!V2_E19_FINAL_COLD_LOADER!"=="true" set "V2_E19_FINAL_COLD_LOADER_ACTIVE=1"
if /i "!V2_E19_FINAL_COLD_LOADER!"=="yes" set "V2_E19_FINAL_COLD_LOADER_ACTIVE=1"
if /i "!V2_E19_FINAL_COLD_LOADER!"=="on" set "V2_E19_FINAL_COLD_LOADER_ACTIVE=1"
if "!V2_E19_FINAL_COLD_LOADER_ACTIVE!"=="1" (
    if "!V2_D6_FASTPATH_VALIDATION_ACTIVE!"=="1" (
        echo === ERROR: E19 cannot combine with D6 atomic profile ===
        exit /b 1
    )
    if "!V2_D10_INTEGRATION_VALIDATION_ACTIVE!"=="1" (
        echo === ERROR: E19 cannot combine with D10 atomic profile ===
        exit /b 1
    )
    if "!V2_E10_BUCKET_FIRST_VALIDATION_ACTIVE!"=="1" (
        echo === ERROR: E19 cannot combine with E10 atomic profile ===
        exit /b 1
    )
    set "COMFYMODAL_V2_ATOMIC_PROFILE=E19_FINAL_COLD_LOADER"
    set "COMFYMODAL_V2_ENV_PROFILE=inherit"
    set "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET=1"
    set "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT=1"
    set "COMFYMODAL_V2_EVICT_RETAIN_ROLE=clip_vae"
    set "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS=0"
    set "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION=1"
    set "COMFYMODAL_V2_CHECKPOINT_PREWARM=1"
    set "COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS=4"
    set "COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB=8"
    set "COMFYMODAL_V2_UNET_FASTSAFETENSORS=1"
    set "COMFYMODAL_V2_CLIP_FAST_HYDRATION=1"
    set "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS=1"
    set "COMFYMODAL_V2_CRITICAL_GPU_COORDINATION=1"
    set "COMFYMODAL_V2_SCOPED_CUDA_READINESS=1"
    set "COMFYMODAL_V2_STAGED_SAFETENSORS=0"
    set "COMFYMODAL_V2_C9QD_EXTRAS=0"
    set "COMFYMODAL_V2_STAGED_SOURCE_ORDER=0"
    set "COMFYMODAL_V2_CLIP_STAGED_HYDRATION=0"
    set "COMFYMODAL_V2_CLIP_COLD_FORENSICS=0"
    set "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST=0"
    set "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA=0"
    set "COMFYMODAL_V2_INPUT_TYPES_WARM=1"
    set "COMFYMODAL_V2_UNET_FORENSICS=0"
)
REM -- Fail-closed: verify E19 selector actually set required flags --
if "!COMFYMODAL_V2_ATOMIC_PROFILE!"=="E19_FINAL_COLD_LOADER" (
    if "!COMFYMODAL_V2_FAST_COLD_ORCHESTRATION!"=="0" (
        echo === ERROR: E19 profile selected but FAST_COLD_ORCHESTRATION=0 ===
        echo === This means the E19 flags were not properly set. Aborting. ===
        exit /b 1
    )
    if "!COMFYMODAL_V2_UNET_FASTSAFETENSORS!"=="0" (
        echo === ERROR: E19 profile selected but UNET_FASTSAFETENSORS=0 ===
        echo === This means the E19 flags were not properly set. Aborting. ===
        exit /b 1
    )
    if "!COMFYMODAL_V2_CLIP_FAST_HYDRATION!"=="0" (
        echo === ERROR: E19 profile selected but CLIP_FAST_HYDRATION=0 ===
        echo === This means the E19 flags were not properly set. Aborting. ===
        exit /b 1
    )
    echo [v2.profile_guard] E19 selector verified: all critical flags present
)

set "REPO_ROOT=%~dp0"
cd /d "%REPO_ROOT%" || exit /b 1

if "!V2_E19_FINAL_COLD_LOADER_ACTIVE!"=="1" (
    python tools\benchmark_v2_direct.py --verify-d6-profile
    if errorlevel 1 (
        echo === ERROR: E19 atomic profile validation FAILED - aborting before any Modal call. ===
        exit /b 1
    )
)

if "!V2_E37_VALIDATION_ACTIVE!"=="1" (
    if "!V2_E37_CLEAN_LANE_ACTIVE!"=="1" (
        python tools\benchmark_v2_direct.py --verify-e37-clean-lane-profile --run-count 1
    ) else (
        python tools\benchmark_v2_direct.py --verify-e37-profile --run-count 1
    )
    if errorlevel 1 (
        echo === ERROR: E37 profile validation FAILED - aborting before any Modal call. ===
        exit /b 1
    )
)

if "!V2_E10_BUCKET_FIRST_VALIDATION_ACTIVE!"=="1" (
    python tools\benchmark_v2_direct.py --verify-e10-profile
    if errorlevel 1 (
        echo === ERROR: E10 bucket-first profile validation FAILED - aborting before any Modal call. ===
        exit /b 1
    )
)

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

if "!V2_E10_BUCKET_FIRST_VALIDATION_ACTIVE!"=="1" (
    echo === Verifying deployed E10 bucket-first runtime profile ===
    python tools\benchmark_v2_direct.py --verify-e10-remote-profile
    if errorlevel 1 (
        echo === E10 remote profile validation FAILED - aborting before graph request. ===
        exit /b 1
    )
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
echo ATOMIC_PROFILE=!COMFYMODAL_V2_ATOMIC_PROFILE!
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
echo fast_cold_orchestration=!COMFYMODAL_V2_FAST_COLD_ORCHESTRATION!
echo checkpoint_prewarm=!COMFYMODAL_V2_CHECKPOINT_PREWARM!
echo prewarm_threads=!COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS!
echo prewarm_chunk_mb=!COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB!
echo unet_fastsafetensors=!COMFYMODAL_V2_UNET_FASTSAFETENSORS!
echo clip_fast_hydration=!COMFYMODAL_V2_CLIP_FAST_HYDRATION!
echo clip_snapshot_exclude_weights=!COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS!
echo critical_gpu_coordination=!COMFYMODAL_V2_CRITICAL_GPU_COORDINATION!
echo scoped_cuda_readiness=!COMFYMODAL_V2_SCOPED_CUDA_READINESS!
echo staged_safetensors=!COMFYMODAL_V2_STAGED_SAFETENSORS!
echo c9qd_extras=!COMFYMODAL_V2_C9QD_EXTRAS!
echo staged_source_order=!COMFYMODAL_V2_STAGED_SOURCE_ORDER!
echo clip_staged_hydration=!COMFYMODAL_V2_CLIP_STAGED_HYDRATION!
echo volume_read_run_count=!V2_VOLUME_READ_RUN_COUNT!
echo restore_only_app=!COMFYMODAL_V2_RESTORE_ONLY_APP_NAME!
echo restore_only_run_count=!V2_RESTORE_ONLY_RUN_COUNT!
echo snapshot_exclude_unet=!COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET!
echo e10_bucket_first_validation=!V2_E10_BUCKET_FIRST_VALIDATION_ACTIVE!
if "!V2_E10_BUCKET_FIRST_VALIDATION_ACTIVE!"=="1" (
    echo staged_safetensors=!COMFYMODAL_V2_STAGED_SAFETENSORS!
    echo staged_producers=!COMFYMODAL_V2_STAGED_PRODUCERS!
    echo staged_pool_mb=!COMFYMODAL_V2_STAGED_POOL_MB!
    echo staged_bucket_mb=!COMFYMODAL_V2_STAGED_BUCKET_MB!
    echo staged_cpu_cast=!COMFYMODAL_V2_STAGED_CPU_CAST!
    echo staged_async_h2d=!COMFYMODAL_V2_STAGED_ASYNC_H2D!
    echo staged_contiguous_gpu_buckets=!COMFYMODAL_V2_STAGED_CONTIGUOUS_GPU_BUCKETS!
    echo clip_fast_hydration=!COMFYMODAL_V2_CLIP_FAST_HYDRATION!
    echo clip_staged_hydration=!COMFYMODAL_V2_CLIP_STAGED_HYDRATION!
    echo critical_gpu_coordination=!COMFYMODAL_V2_CRITICAL_GPU_COORDINATION!
    echo prefill_wait_for_unet=!COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET!
)

set "COMFYMODAL_COMMAND_START_UNIX_MS=!COMMAND_START_MS!"
REM -- Benchmark invocation ------------------------------------------
REM Production default: V2_BENCHMARK_RUNS=10, V2_BENCHMARK_GAP_SECONDS=35
REM -> 10 cold runs with a 35 s cooldown against the restore-only shadow
REM app (the accepted production deployment; deploy first with
REM deploy_and_run_v2_single.bat, which deploys and exits without probes).
REM Override with V2_BENCHMARK_RUNS=1 for a single trial.  The acceptance
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
    python tools\benchmark_v2_direct.py --snapshot-restore-only %*
) else if "!V2_GOLDEN_P1_ACTIVE!"=="1" (
    echo === Running V2 golden_p1 serial-Golden generation - explicit opt-in ===
    set "V2_TOOL_ARGS="
    for %%a in (%*) do if /i not "%%~a"=="golden_p1" set "V2_TOOL_ARGS=!V2_TOOL_ARGS! %%a"
    python tools\benchmark_v2_direct.py --golden-p1!V2_TOOL_ARGS!
) else (
    echo === Running one V2 benchmark trial against the existing deployment ===
    echo === Deploy first with deploy_and_run_v2_single.bat after source or env changes ===
    echo === Fail-closed request preflight (local, no spend) ===
    if "!V2_E37_VALIDATION_ACTIVE!"=="1" (
        python tools\benchmark_v2_direct.py --verify-run-preflight --run-count 1 --conditioning-cache-nonce !V2_E37_CONDITIONING_NONCE!
    ) else if "!V2_E28_VALIDATION_ACTIVE!"=="1" (
        python tools\benchmark_v2_direct.py --verify-run-preflight --run-count 1 --conditioning-cache-nonce !V2_E28_CONDITIONING_NONCE!
    ) else if "!V2_E26_VALIDATION_ACTIVE!"=="1" (
        python tools\benchmark_v2_direct.py --verify-run-preflight --run-count 1 --conditioning-cache-nonce !V2_E26_CONDITIONING_NONCE!
    ) else if "!V2_E25_VALIDATION_ACTIVE!"=="1" (
        python tools\benchmark_v2_direct.py --verify-run-preflight --run-count 1 --conditioning-cache-nonce !V2_E25_CONDITIONING_NONCE!
    ) else (
        python tools\benchmark_v2_direct.py --verify-run-preflight %*
    )
    if errorlevel 1 (
        echo === RUN PREFLIGHT FAILED - aborting before any Modal submission ===
        exit /b 1
    )
    if "!V2_E37_VALIDATION_ACTIVE!"=="1" (
        set "V2_TOOL_ARGS="
        set "V2_FIRST_SKIP="
        for %%a in (%*) do if not defined V2_FIRST_SKIP (set "V2_FIRST_SKIP=1") else (set "V2_TOOL_ARGS=!V2_TOOL_ARGS! %%a")
        python tools\benchmark_v2_direct.py --run-count 1 --conditioning-cache-nonce !V2_E37_CONDITIONING_NONCE!!V2_TOOL_ARGS!
    ) else if "!V2_E28_VALIDATION_ACTIVE!"=="1" (
        set "V2_TOOL_ARGS="
        set "V2_FIRST_SKIP="
        for %%a in (%*) do if not defined V2_FIRST_SKIP (set "V2_FIRST_SKIP=1") else (set "V2_TOOL_ARGS=!V2_TOOL_ARGS! %%a")
        python tools\benchmark_v2_direct.py --run-count 1 --conditioning-cache-nonce !V2_E28_CONDITIONING_NONCE!!V2_TOOL_ARGS!
    ) else if "!V2_E26_VALIDATION_ACTIVE!"=="1" (
        python tools\benchmark_v2_direct.py --run-count 1 --conditioning-cache-nonce !V2_E26_CONDITIONING_NONCE!
    ) else if "!V2_E25_VALIDATION_ACTIVE!"=="1" (
        python tools\benchmark_v2_direct.py --run-count 1 --conditioning-cache-nonce !V2_E25_CONDITIONING_NONCE!
    ) else (
        python tools\benchmark_v2_direct.py %*
    )
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
