@echo off
setlocal enabledelayedexpansion

chcp 65001 >nul

REM -- UTF-8 for the Modal client (E29 root-cause fix) ------------------
REM The Modal CLI prints emoji/unicode (e.g. the hammer build icon U+1F528)
REM and crashes with a 'charmap' codec error on Windows cp1252 consoles,
REM which can surface as a deploy that exits 0 while the app version never
REM advances.  Force UTF-8 for every child Python process (modal client)
REM regardless of how this BAT is spawned, so a deploy either really
REM deploys or fails loudly.
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

set "V2_PREFLIGHT_ONLY=0"
if /i "%~2"=="--preflight-only" set "V2_PREFLIGHT_ONLY=1"
set "V2_RUN_ONLY=0"
if /i "%~2"=="--run-only" set "V2_RUN_ONLY=1"
if /i "%~1"=="E22_PREFETCH_OFF" set "V2_BENCHMARK_MODE=e22_single"
if /i "%~1"=="E22_PREFETCH_ON" set "V2_BENCHMARK_MODE=e22_single"
if /i "%~1"=="E22_PREFETCH_OFF" set "V2_E22_CONDITIONING_NONCE=%RANDOM%-%RANDOM%-%RANDOM%"
if /i "%~1"=="E22_PREFETCH_ON" set "V2_E22_CONDITIONING_NONCE=%RANDOM%-%RANDOM%-%RANDOM%"
if /i "%~1"=="E25_VALIDATION" set "V2_BENCHMARK_MODE=e25_single"
if /i "%~1"=="E25_VALIDATION" set "V2_E25_CONDITIONING_NONCE=%RANDOM%-%RANDOM%-%RANDOM%"
set "V2_E22_REQUESTED_RUN_COUNT=1"
if /i "%~3"=="--run-count" set "V2_E22_REQUESTED_RUN_COUNT=%~4"
if /i "%~1"=="E22_PREFETCH_OFF" set "V2_BENCHMARK_RUNS=!V2_E22_REQUESTED_RUN_COUNT!"
if /i "%~1"=="E22_PREFETCH_ON" set "V2_BENCHMARK_RUNS=!V2_E22_REQUESTED_RUN_COUNT!"
if /i "%~1"=="E25_VALIDATION" set "V2_BENCHMARK_RUNS=1"
if /i "%~1"=="E26_VALIDATION" set "V2_BENCHMARK_MODE=e26_single"
if /i "%~1"=="E26_VALIDATION" set "V2_E26_CONDITIONING_NONCE=%RANDOM%-%RANDOM%-%RANDOM%"
if /i "%~1"=="E26_VALIDATION" set "V2_BENCHMARK_RUNS=1"
if /i "%~1"=="E37_VALIDATION" set "V2_BENCHMARK_MODE=e37_single"
if /i "%~1"=="E37_VALIDATION" set "V2_E37_CONDITIONING_NONCE=%RANDOM%-%RANDOM%-%RANDOM%"
if /i "%~1"=="E37_VALIDATION" set "V2_BENCHMARK_RUNS=1"
set "V2_E37_CLEAN_LANE_ACTIVE=0"
if /i "%~1"=="E37_CLEAN_LANE_VALIDATION" set "V2_E37_CLEAN_LANE_ACTIVE=1"
if /i "!COMFYMODAL_V2_E37_CLEAN_LANE!"=="1" set "V2_E37_CLEAN_LANE_ACTIVE=1"
if /i "!COMFYMODAL_V2_CLEAN_LANE!"=="1" set "V2_E37_CLEAN_LANE_ACTIVE=1"
if "!V2_E37_CLEAN_LANE_ACTIVE!"=="1" set "V2_E19_FINAL_COLD_LOADER=0"
if "!V2_E37_CLEAN_LANE_ACTIVE!"=="1" set "V2_E28_VALIDATION=0"
if "!V2_E37_CLEAN_LANE_ACTIVE!"=="1" set "V2_E31_VALIDATION=0"
if /i "%~1"=="E37_CLEAN_LANE_VALIDATION" set "V2_E37_VALIDATION=1"
if /i "%~1"=="E37_CLEAN_LANE_VALIDATION" set "V2_E37_CONDITIONING_NONCE=%RANDOM%-%RANDOM%-%RANDOM%"
if /i "%~1"=="E37_CLEAN_LANE_VALIDATION" set "V2_BENCHMARK_MODE=e37_single"
if /i "%~1"=="E37_CLEAN_LANE_VALIDATION" set "V2_BENCHMARK_RUNS=1"
if /i "%~1"=="E37_VALIDATION" if "!V2_E37_CLEAN_LANE_ACTIVE!"=="0" set "V2_E19_FINAL_COLD_LOADER=1"
if /i "%~1"=="E28_VALIDATION" set "V2_BENCHMARK_MODE=e28_single"
if /i "%~1"=="E28_VALIDATION" set "V2_E28_CONDITIONING_NONCE=%RANDOM%-%RANDOM%-%RANDOM%"
if /i "%~1"=="E28_VALIDATION" set "V2_BENCHMARK_RUNS=1"
if /i "%~1"=="E28_VALIDATION" set "V2_E19_FINAL_COLD_LOADER=1"
if /i "%~1"=="E31_VALIDATION" set "V2_BENCHMARK_MODE=e31_single"
if /i "%~1"=="E31_VALIDATION" set "V2_E31_CONDITIONING_NONCE=%RANDOM%-%RANDOM%-%RANDOM%"
if /i "%~1"=="E31_VALIDATION" set "V2_BENCHMARK_RUNS=1"
if /i "%~1"=="E31_VALIDATION" set "V2_E19_FINAL_COLD_LOADER=1"

REM -- golden_p1 serial-Golden profile selector (atomic opt-in) -------------
REM Same %~1 mechanism as the validation selectors above.  golden_p1 is the
REM isolated R0 deploy path (snapshot construction, no probes) and only
REM establishes the profile's deploy-baked dynamic-VRAM flag.  The flag is
REM set ONLY when not already defined so a v2ctl-resolved child environment
REM (profile golden_p1) is never overwritten after resolution.
set "V2_GOLDEN_P1_ACTIVE=0"
set "V2_GOLDEN_P1_PARALLEL_ACTIVE=0"
if /i "%~1"=="golden_p1" set "V2_GOLDEN_P1_ACTIVE=1"
if /i "%~1"=="golden_p1_parallel" set "V2_GOLDEN_P1_ACTIVE=1"
if /i "!COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM!"=="1" set "V2_GOLDEN_P1_ACTIVE=1"
if /i "!COMFYMODAL_V2CTL_PROFILE!"=="golden_p1_parallel" set "V2_GOLDEN_P1_PARALLEL_ACTIVE=1"
if /i "!COMFYMODAL_V2CTL_PROFILE!"=="golden_p1_parallel" set "V2_GOLDEN_P1_ACTIVE=1"
if /i "!V2_BENCHMARK_MODE!"=="golden_p1_parallel" set "V2_GOLDEN_P1_ACTIVE=1"
if /i "!V2_BENCHMARK_MODE!"=="golden_p1_parallel" set "V2_GOLDEN_P1_PARALLEL_ACTIVE=1"
if "!V2_GOLDEN_P1_ACTIVE!"=="1" (
    if "!V2_GOLDEN_P1_PARALLEL_ACTIVE!"=="1" (
        if defined COMFYMODAL_V2CTL_PROFILE if /i not "!COMFYMODAL_V2CTL_PROFILE!"=="golden_p1_parallel" (
            echo === ERROR: parallel Golden selector requires COMFYMODAL_V2CTL_PROFILE=golden_p1_parallel ===
            exit /b 1
        )
        if defined V2_BENCHMARK_MODE if /i not "!V2_BENCHMARK_MODE!"=="golden_p1_parallel" (
            echo === ERROR: golden_p1_parallel requires V2_BENCHMARK_MODE=golden_p1_parallel ===
            exit /b 1
        )
        set "V2_BENCHMARK_MODE=golden_p1_parallel"
    ) else (
        if defined V2_BENCHMARK_MODE if /i not "!V2_BENCHMARK_MODE!"=="golden_p1_serial" (
            echo === ERROR: golden_p1 requires V2_BENCHMARK_MODE=golden_p1_serial ===
            exit /b 1
        )
        set "V2_BENCHMARK_MODE=golden_p1_serial"
    )
    if not defined COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM set "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM=1"
    echo [v2.golden_p1] selector=ACTIVE golden_enable_dynamic_vram=!COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM!
    REM Golden R0 is isolated. Reject missing/protected identity before any
    REM fallback defaults, workspace loading, or Modal/backend work.
    if not defined COMFYMODAL_V2_APP_NAME (
        echo === ERROR: golden_p1 requires an experimental COMFYMODAL_V2_APP_NAME ===
        exit /b 1
    )
    if /i "!COMFYMODAL_V2_APP_NAME!"=="stable-modal-comfy-v2-golden-p1" (
        echo === ERROR: golden_p1 refuses protected production app stable-modal-comfy-v2-golden-p1 ===
        exit /b 1
    )
)


REM -- E22 arm arguments: establish selectors inside cmd.exe ---------------
if /i "%~1"=="E22_PREFETCH_OFF" (
    set "V2_E19_FINAL_COLD_LOADER=1"
    set "V2_E22_PREFETCH_OFF=1"
    set "V2_E22_PREFETCH_ON=0"
)
if /i "%~1"=="E22_PREFETCH_ON" (
    set "V2_E19_FINAL_COLD_LOADER=1"
    set "V2_E22_PREFETCH_OFF=0"
    set "V2_E22_PREFETCH_ON=1"
)
REM -- E25 validation argument: establish the selector inside cmd.exe -------
if /i "%~1"=="E25_VALIDATION" (
    set "V2_E19_FINAL_COLD_LOADER=1"
    set "V2_E25_VALIDATION=1"
)

REM -- Pin environment variables ------------------------------------
if not defined COMFYMODAL_V2_APP_NAME set "COMFYMODAL_V2_APP_NAME=stable-modal-comfy-v2-restore-only-shadow"
set "COMFYMODAL_V2_CLASS_NAME=ModalRuntimeEntrypointV2"
if not defined COMFYMODAL_V2_GPU set "COMFYMODAL_V2_GPU=rtx-pro-6000"
if not defined COMFYMODAL_V2_RESTORE_ONLY_APP_NAME set "COMFYMODAL_V2_RESTORE_ONLY_APP_NAME=stable-modal-comfy-v2-restore-only-shadow"
REM -- Variance-cold mode (explicit opt-in) -------------------------
REM Uses a unique shadow app name ONLY for variance mode.  Normal and
REM production modes keep the default identity above.
set "V2_IS_VARIANCE=0"
if /i "!V2_BENCHMARK_MODE!"=="variance_cold" set "V2_IS_VARIANCE=1"
if /i "!V2_BENCHMARK_MODE!"=="variance_matrix" set "V2_IS_VARIANCE=1"
if /i "!V2_BENCHMARK_MODE!"=="host_ab" set "V2_IS_VARIANCE=1"
REM v2ctl owns the target identity.  Keep the legacy default only when no
REM target was supplied; never validate every profile against the production
REM restore-only app name.
if not defined V2_DEPLOY_IDENT set "V2_DEPLOY_IDENT=!COMFYMODAL_V2_APP_NAME!"
set "COMFYMODAL_V2_ATOMIC_PROFILE="
set "V2_PROFILE_PRETOUCH=0"
REM -- Production default mode: snapshot_restore_only --------------------
REM The accepted production configuration deploys the restore-only shadow
REM app (UNET excluded from the CPU snapshot, eviction clip_vae, inherit
REM profile, snapshot-construction marker) and exits after construction
REM WITHOUT issuing reuse probes.  Batches are then run with
REM run_v2_single.bat (defaults: 10 runs, 35 s cooldown).  Any explicit
REM V2_BENCHMARK_MODE overrides this default.
if not defined V2_BENCHMARK_MODE set "V2_BENCHMARK_MODE=snapshot_restore_only"
if /i "!V2_IS_VARIANCE!"=="1" (
    set "COMFYMODAL_V2_APP_NAME=stable-modal-comfy-v2-variance-shadow"
    set "V2_DEPLOY_IDENT=stable-modal-comfy-v2-variance-shadow"
    if defined V2_VARIANCE_PRETOUCH set "V2_PROFILE_PRETOUCH=!V2_VARIANCE_PRETOUCH!"
    if not defined V2_VARIANCE_COLD_GAP_SECONDS set "V2_VARIANCE_COLD_GAP_SECONDS=25"
    REM Enable the runtime variance-diagnostics gate and the UNET pretouch gate
    REM for the deployed container.  These are diagnostic-only and default OFF in
    REM every other mode (production defaults are untouched).
    set "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS=1"
    set "COMFYMODAL_V2_UNET_PRETOUCH=!V2_PROFILE_PRETOUCH!"
)
REM -- UNET-absent snapshot restore-only mode (explicit opt-in) -----
REM Uses a unique shadow app name deployed with
REM COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET=1 (experiment identity/reporting
REM gate only) so startup STILL constructs the full CLIP/UNET/VAE CPU
REM snapshot with normal UNET dtype validation, then the strict clip_vae
REM eviction retain role evicts the UNET (proving it dead via weakrefs)
REM while fresh CLIP and VAE are reloaded back into the retained
REM CpuSnapshotModels container before Modal captures the memory snapshot.
REM Provider and region stay UNPINNED (COMFYMODAL_V2_CLOUD /
REM COMFYMODAL_V2_REGION are never set here).  This deploy invocation is
REM the LABELED/EXCLUDED snapshot construction: it exits after deploy and
REM must NOT issue reuse probes.  The exactly-6 valid reuse probes are
REM issued ONLY by run_v2_single.bat with V2_BENCHMARK_MODE=
REM snapshot_restore_only.
set "V2_IS_RESTORE_ONLY=0"
if /i "!V2_BENCHMARK_MODE!"=="snapshot_restore_only" set "V2_IS_RESTORE_ONLY=1"
if /i "!V2_IS_RESTORE_ONLY!"=="1" (
    set "COMFYMODAL_V2_APP_NAME=!COMFYMODAL_V2_RESTORE_ONLY_APP_NAME!"
    set "V2_DEPLOY_IDENT=!COMFYMODAL_V2_RESTORE_ONLY_APP_NAME!"
    set "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET=1"
    REM Evict the UNET payload before snapshot capture, retaining only
    REM fresh CLIP+VAE in the kept container (restore idle 0).
    set "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT=1"
    set "COMFYMODAL_V2_EVICT_RETAIN_ROLE=clip_vae"
    set "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS=0"
    REM Non-production env profile: the production snapshot invariant
    REM requires a UNET object at restore time, which this mode excludes.
    REM Forced (not "if not defined") so a user's global production profile
    REM can never re-enable the production branch and wipe the eviction vars.
    set "COMFYMODAL_V2_ENV_PROFILE=inherit"
    REM Snapshot construction lifecycle marker: this deploy invocation is
    REM the labeled/excluded snapshot construction.  The marker keeps the
    REM active-next-profile publication available on the construction path;
    REM normal restored generations (run_v2_single.bat) never set it and
    REM skip the remote checker/setter entirely.
    set "COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION=1"
)
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
REM -- D6 fast-path validation profile (atomic opt-in; production/default behavior unchanged when absent) --
if not defined V2_D6_FASTPATH_VALIDATION set "V2_D6_FASTPATH_VALIDATION=0"
set "V2_D6_FASTPATH_VALIDATION_ACTIVE=0"
if /i "!V2_D6_FASTPATH_VALIDATION!"=="1" set "V2_D6_FASTPATH_VALIDATION_ACTIVE=1"
if /i "!V2_D6_FASTPATH_VALIDATION!"=="true" set "V2_D6_FASTPATH_VALIDATION_ACTIVE=1"
if /i "!V2_D6_FASTPATH_VALIDATION!"=="yes" set "V2_D6_FASTPATH_VALIDATION_ACTIVE=1"
if /i "!V2_D6_FASTPATH_VALIDATION!"=="on" set "V2_D6_FASTPATH_VALIDATION_ACTIVE=1"
if "!V2_D6_FASTPATH_VALIDATION_ACTIVE!"=="1" (
    REM Validation-only profile: FORCE the 8 D6 fast-path values (plain set,
    REM NOT "if not defined", so caller values cannot leak in).  Must match
    REM tools\benchmark_v2_direct.py --verify-d6-profile.
    set "COMFYMODAL_V2_UNET_FASTSAFETENSORS=1"
    set "COMFYMODAL_V2_CLIP_FAST_HYDRATION=1"
    set "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS=1"
    set "COMFYMODAL_V2_CLIP_COLD_FORENSICS=1"
    set "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST=1"
    set "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA=1"
    set "COMFYMODAL_V2_INPUT_TYPES_WARM=1"
    set "COMFYMODAL_V2_UNET_FORENSICS=0"
    set "COMFYMODAL_V2_CRITICAL_GPU_COORDINATION=1"
)
REM -- D10 integration-validation profile (atomic opt-in) -----------------
REM Measurement-integrity variant of the D6 fast-path profile for the
REM Phase-D integration batch: identical except
REM COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA=0.  The D6 run's SYNC_CUDA=1
REM installs a global torch.cuda.synchronize wrapper and a CUDA-event realize
REM around every ModelPatcher.load/partially_load — INTRUSIVE on the request
REM critical path.  D10 keeps structural diagnostics (state checkpoints,
REM hydration events, cast counters/histograms) with production sync
REM semantics only.  Must match tools\benchmark_v2_direct.py D10 map.
if not defined V2_D10_INTEGRATION_VALIDATION set "V2_D10_INTEGRATION_VALIDATION=0"
set "V2_D10_INTEGRATION_VALIDATION_ACTIVE=0"
if /i "!V2_D10_INTEGRATION_VALIDATION!"=="1" set "V2_D10_INTEGRATION_VALIDATION_ACTIVE=1"
if /i "!V2_D10_INTEGRATION_VALIDATION!"=="true" set "V2_D10_INTEGRATION_VALIDATION_ACTIVE=1"
if /i "!V2_D10_INTEGRATION_VALIDATION!"=="yes" set "V2_D10_INTEGRATION_VALIDATION_ACTIVE=1"
if /i "!V2_D10_INTEGRATION_VALIDATION!"=="on" set "V2_D10_INTEGRATION_VALIDATION_ACTIVE=1"
if "!V2_D10_INTEGRATION_VALIDATION_ACTIVE!"=="1" (
    set "COMFYMODAL_V2_UNET_FASTSAFETENSORS=1"
    set "COMFYMODAL_V2_CLIP_FAST_HYDRATION=1"
    set "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS=1"
    set "COMFYMODAL_V2_CLIP_COLD_FORENSICS=1"
    set "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST=1"
    set "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA=0"
    set "COMFYMODAL_V2_INPUT_TYPES_WARM=1"
    set "COMFYMODAL_V2_UNET_FORENSICS=0"
)
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
REM -- E22 arm selectors: activate E19 + override CHECKPOINT_PREWARM ----------
set "V2_E22_ARM_LABEL="
if not defined V2_E22_PREFETCH_OFF set "V2_E22_PREFETCH_OFF=0"
if not defined V2_E22_PREFETCH_ON set "V2_E22_PREFETCH_ON=0"
if /i "!V2_E22_PREFETCH_OFF!"=="1" if /i "!V2_E22_PREFETCH_ON!"=="1" echo === ERROR: E22 arm selectors are mutually exclusive ===
if /i "!V2_E22_PREFETCH_OFF!"=="1" if /i "!V2_E22_PREFETCH_ON!"=="1" exit /b 1
if /i "!V2_E22_PREFETCH_OFF!"=="1" if "!V2_E19_FINAL_COLD_LOADER_ACTIVE!"=="0" echo === ERROR: V2_E22_PREFETCH_OFF requires E19 profile (V2_E19_FINAL_COLD_LOADER=1) ===
if /i "!V2_E22_PREFETCH_OFF!"=="1" if "!V2_E19_FINAL_COLD_LOADER_ACTIVE!"=="0" exit /b 1
if /i "!V2_E22_PREFETCH_OFF!"=="1" set "COMFYMODAL_V2_CHECKPOINT_PREWARM=0"
if /i "!V2_E22_PREFETCH_OFF!"=="1" set "V2_E22_ARM_LABEL=E22_PREFETCH_OFF"
if /i "!V2_E22_PREFETCH_OFF!"=="1" echo [v2.e22_arm] ARM=E22_PREFETCH_OFF CHECKPOINT_PREWARM=0
if /i "!V2_E22_PREFETCH_ON!"=="1" if "!V2_E19_FINAL_COLD_LOADER_ACTIVE!"=="0" echo === ERROR: V2_E22_PREFETCH_ON requires E19 profile (V2_E19_FINAL_COLD_LOADER=1) ===
if /i "!V2_E22_PREFETCH_ON!"=="1" if "!V2_E19_FINAL_COLD_LOADER_ACTIVE!"=="0" exit /b 1
if /i "!V2_E22_PREFETCH_ON!"=="1" set "COMFYMODAL_V2_CHECKPOINT_PREWARM=1"
if /i "!V2_E22_PREFETCH_ON!"=="1" set "V2_E22_ARM_LABEL=E22_PREFETCH_ON"
if /i "!V2_E22_PREFETCH_ON!"=="1" echo [v2.e22_arm] ARM=E22_PREFETCH_ON CHECKPOINT_PREWARM=1
REM -- E25 whole-critical-path validation selector (atomic opt-in) -----------
REM Historical E25 selector: inherits the E19 final cold-loader base and sets
REM the E25 validation flags.  E26 corrects the VAE defaults: the ineffective
REM sampling_end/250 early activation is NO LONGER the production default —
REM the selector now uses the canonical late/safe VAE mode (the experiment
REM remains available behind the explicit flags).  Run count is hard-gated
REM to 1.
if not defined V2_E25_VALIDATION set "V2_E25_VALIDATION=0"
set "V2_E25_VALIDATION_ACTIVE=0"
if /i "!V2_E25_VALIDATION!"=="1" set "V2_E25_VALIDATION_ACTIVE=1"
if /i "!V2_E25_VALIDATION!"=="true" set "V2_E25_VALIDATION_ACTIVE=1"
if /i "!V2_E25_VALIDATION!"=="yes" set "V2_E25_VALIDATION_ACTIVE=1"
if /i "!V2_E25_VALIDATION!"=="on" set "V2_E25_VALIDATION_ACTIVE=1"
if "!V2_E25_VALIDATION_ACTIVE!"=="1" (
    if "!V2_E19_FINAL_COLD_LOADER_ACTIVE!"=="0" goto :e25_fail_no_e19
    if defined V2_E22_ARM_LABEL goto :e25_fail_e22
    set "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION=1"
    set "COMFYMODAL_V2_GPU_FAST_RETURN=1"
    set "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS=1"
    set "COMFYMODAL_V2_VAE_ACTIVATION_MODE=late"
    set "COMFYMODAL_V2_VAE_EARLY_START_MS=0"
    echo [v2.e25_validation] selector=ACTIVE speculative_clip=1 gpu_fast_return=1 opt_diag=1 vae_mode=late vae_early=0
)
goto :e25_validation_continue
:e25_fail_no_e19
echo === ERROR: E25 validation requires E19 profile (V2_E19_FINAL_COLD_LOADER=1) ===
exit /b 1
:e25_fail_e22
echo === ERROR: E25 validation cannot combine with an E22 arm ===
exit /b 1
:e25_validation_continue
REM -- E26 concrete cold-wins validation selector (atomic opt-in) ----------
REM Inherits the E19 final cold-loader base EXACTLY and changes ONLY the E26
REM validation flags: E26 speculative CLIP (frozen-manifest absolute paths),
REM production GPU fast return, checkpoint prewarm (coordinated CLIP-first /
REM UNET-second schedule), late/safe VAE (early activation OFF), optimization
REM diagnostics.  Run count is hard-gated to 1 per run (see
REM V2_E26_CONDITIONING_NONCE + run-count guard and the CLI-side E26 guard);
REM a validation cycle is exactly two --run-count 1 requests on one deploy.
if not defined V2_E26_VALIDATION set "V2_E26_VALIDATION=0"
set "V2_E26_VALIDATION_ACTIVE=0"
if /i "!V2_E26_VALIDATION!"=="1" set "V2_E26_VALIDATION_ACTIVE=1"
if /i "!V2_E26_VALIDATION!"=="true" set "V2_E26_VALIDATION_ACTIVE=1"
if /i "!V2_E26_VALIDATION!"=="yes" set "V2_E26_VALIDATION_ACTIVE=1"
if /i "!V2_E26_VALIDATION!"=="on" set "V2_E26_VALIDATION_ACTIVE=1"
if "!V2_E26_VALIDATION_ACTIVE!"=="1" (
    if "!V2_E19_FINAL_COLD_LOADER_ACTIVE!"=="0" goto :e26_fail_no_e19
    if defined V2_E22_ARM_LABEL goto :e26_fail_e22
    set "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION=1"
    set "COMFYMODAL_V2_GPU_FAST_RETURN=1"
    set "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS=1"
    set "COMFYMODAL_V2_VAE_ACTIVATION_MODE=late"
    set "COMFYMODAL_V2_VAE_EARLY_START_MS=0"
    set "COMFYMODAL_V2_CHECKPOINT_PREWARM=1"
    echo [v2.e26_validation] selector=ACTIVE speculative_clip=1 gpu_fast_return=1 opt_diag=1 vae_mode=late vae_early=0 checkpoint_prewarm=1
)
goto :e26_validation_continue
:e26_fail_no_e19
echo === ERROR: E26 validation requires E19 profile (V2_E19_FINAL_COLD_LOADER=1) ===
exit /b 1
:e26_fail_e22
echo === ERROR: E26 validation cannot combine with an E22 arm ===
exit /b 1
:e26_validation_continue
REM -- E37 late CLIP validation selector (atomic opt-in) ----------------------
REM E37 shares the E19 full-generation base, but must never inherit E28's
REM restore-earliest or diagnostic forcing.  Required QD/FASTSAFE, late-policy,
REM minimal-restore, and strict-proof values remain profile-owned; this block
REM only projects the selector and hard-gates one full run.
if not defined V2_E37_VALIDATION set "V2_E37_VALIDATION=0"
if /i "%~1"=="E37_VALIDATION" set "V2_E37_VALIDATION=1"
if /i "!COMFYMODAL_V2_E37_STRICT_PROOF!"=="1" set "V2_E37_VALIDATION=1"
set "V2_E37_VALIDATION_ACTIVE=0"
if /i "!V2_E37_VALIDATION!"=="1" set "V2_E37_VALIDATION_ACTIVE=1"
if /i "!V2_E37_VALIDATION!"=="true" set "V2_E37_VALIDATION_ACTIVE=1"
if /i "!V2_E37_VALIDATION!"=="yes" set "V2_E37_VALIDATION_ACTIVE=1"
if /i "!V2_E37_VALIDATION!"=="on" set "V2_E37_VALIDATION_ACTIVE=1"
if "!V2_E37_VALIDATION_ACTIVE!"=="1" (
    if "!V2_E37_CLEAN_LANE_ACTIVE!"=="1" goto :e37_clean_validation
    if "!V2_E19_FINAL_COLD_LOADER_ACTIVE!"=="0" goto :e37_fail_no_e19
    if defined V2_E22_ARM_LABEL goto :e37_fail_e22
    set "V2_E28_VALIDATION=0"
    set "V2_E31_VALIDATION=0"
    set "V2_BENCHMARK_MODE=e37_single"
    set "V2_BENCHMARK_RUNS=1"
    if not defined V2_E37_CONDITIONING_NONCE set "V2_E37_CONDITIONING_NONCE=%RANDOM%-%RANDOM%-%RANDOM%"
    echo [v2.e37_validation] selector=ACTIVE full_run=1 e19=1 nonce=present
)
goto :e37_validation_continue
:e37_clean_validation
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
set "V2_E37_VALIDATION=1"
set "V2_E28_VALIDATION=0"
set "V2_E31_VALIDATION=0"
set "V2_BENCHMARK_MODE=e37_single"
set "V2_BENCHMARK_RUNS=1"
if not defined V2_E37_CONDITIONING_NONCE set "V2_E37_CONDITIONING_NONCE=%RANDOM%-%RANDOM%-%RANDOM%"
echo [v2.e37_clean_lane_validation] selector=ACTIVE full_run=1 e19=0 qd=4 block_mib=32 nonce=present
goto :e37_validation_continue
:e37_fail_no_e19
echo === ERROR: E37 validation requires E19 profile (V2_E19_FINAL_COLD_LOADER=1) ===
exit /b 1
:e37_fail_e22
echo === ERROR: E37 validation cannot combine with an E22 arm ===
exit /b 1
:e37_validation_continue
REM -- E31 QD4 cast-once validation selector (atomic opt-in) ------------------
REM This is NOT ordinary E28: the E31 profile inherits E29/E28 settings, so
REM the explicit selector disables E28 validation and forces the complete
REM E31-owned QD4/cast-once tuple before the local verifier runs.
if not defined V2_E31_VALIDATION set "V2_E31_VALIDATION=0"
if /i "%~1"=="E31_VALIDATION" set "V2_E31_VALIDATION=1"
set "V2_E31_VALIDATION_ACTIVE=0"
if /i "!V2_E31_VALIDATION!"=="1" set "V2_E31_VALIDATION_ACTIVE=1"
if /i "!V2_E31_VALIDATION!"=="true" set "V2_E31_VALIDATION_ACTIVE=1"
if /i "!V2_E31_VALIDATION!"=="yes" set "V2_E31_VALIDATION_ACTIVE=1"
if /i "!V2_E31_VALIDATION!"=="on" set "V2_E31_VALIDATION_ACTIVE=1"
if "!V2_E31_VALIDATION_ACTIVE!"=="1" (
    if "!V2_E19_FINAL_COLD_LOADER_ACTIVE!"=="0" goto :e31_fail_no_e19
    if defined V2_E22_ARM_LABEL goto :e31_fail_e22
    set "V2_E28_VALIDATION=0"
    set "COMFYMODAL_V2_CLIP_QD_READER=1"
    set "COMFYMODAL_V2_CLIP_QD_QD=4"
    set "COMFYMODAL_V2_CLIP_QD_BLOCK_MIB=32"
    set "COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY=restore_earliest"
    set "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE=1"
    set "COMFYMODAL_V2_E31_FORENSICS=1"
    set "COMFYMODAL_V2_E31_FORWARD_PROFILE=0"
    echo [v2.e31_validation] selector=ACTIVE qd_reader=1 qd=4 block_mib=32 launch_policy=restore_earliest cast_once=1 forensics=1 forward_profile=0
)
goto :e31_validation_continue
:e31_fail_no_e19
echo === ERROR: E31 validation requires E19 profile (V2_E19_FINAL_COLD_LOADER=1) ===
exit /b 1
:e31_fail_e22
echo === ERROR: E31 validation cannot combine with an E22 arm ===
exit /b 1
:e31_validation_continue
REM -- E28 critical-path implementation validation selector (atomic opt-in) --
REM Inherits the E19 base EXACTLY and adds the E28 production optimizations:
REM earliest restore-time CLIP lane (speculative CLIP was already on), the
REM tuned direct-GPU loader configs (CLIP T8/B64MiB, UNET T8/B256MiB — the
REM E27 Follow-Up A first-touch screening winners, now the code defaults),
REM and the multi-window readable Gantt (opt-in telemetry).  The FP32
REM cast-once experiment stays OFF by default (opt-in per request via the
REM e28_fp32_cast_once experiment arm).  Run count is hard-gated to 1 per
REM run; a validation cycle is exactly two --run-count 1 requests.
if not defined V2_E28_VALIDATION set "V2_E28_VALIDATION=0"
if /i "%~1"=="E28_VALIDATION" set "V2_E28_VALIDATION=1"
set "V2_E28_VALIDATION_ACTIVE=0"
if /i "!V2_E28_VALIDATION!"=="1" set "V2_E28_VALIDATION_ACTIVE=1"
if /i "!V2_E28_VALIDATION!"=="true" set "V2_E28_VALIDATION_ACTIVE=1"
if /i "!V2_E28_VALIDATION!"=="yes" set "V2_E28_VALIDATION_ACTIVE=1"
if /i "!V2_E28_VALIDATION!"=="on" set "V2_E28_VALIDATION_ACTIVE=1"
if "!V2_E28_VALIDATION_ACTIVE!"=="1" (
    if "!V2_E19_FINAL_COLD_LOADER_ACTIVE!"=="0" goto :e28_fail_no_e19
    if defined V2_E22_ARM_LABEL goto :e28_fail_e22
    set "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION=1"
    set "COMFYMODAL_V2_GPU_FAST_RETURN=1"
    set "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS=1"
    set "COMFYMODAL_V2_VAE_ACTIVATION_MODE=late"
    set "COMFYMODAL_V2_VAE_EARLY_START_MS=0"
    set "COMFYMODAL_V2_CHECKPOINT_PREWARM=1"
    set "COMFYMODAL_V2_GANTT_TELEMETRY=1"
    set "COMFYMODAL_V2_E27_FORENSICS=1"
    echo [v2.e28_validation] selector=ACTIVE speculative_clip=1 gpu_fast_return=1 opt_diag=1 vae_mode=late checkpoint_prewarm=1 gantt=1 e27_forensics=1
)
goto :e28_validation_continue
:e28_fail_no_e19
echo === ERROR: E28 validation requires E19 profile (V2_E19_FINAL_COLD_LOADER=1) ===
exit /b 1
:e28_fail_e22
echo === ERROR: E28 validation cannot combine with an E22 arm ===
exit /b 1
:e28_validation_continue
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
if /i "!COMFYMODAL_V2_ENV_PROFILE!"=="production" if not defined COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST set "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST=1"
if not defined COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST set "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST=0"

set "REPO_ROOT=%~dp0"
cd /d "%REPO_ROOT%" || exit /b 1

REM -- Atomic deploy profile verify gate (abort BEFORE any deploy) ----------
REM The E22 arm verifier is local-only and validates the complete E19 base
REM profile plus the arm-specific deployment-scoped prewarm value.  The E25
REM verifier validates the E19 base + the five E25 validation flags.
if /i "!V2_E37_VALIDATION_ACTIVE!"=="1" (
    if "!V2_E37_CLEAN_LANE_ACTIVE!"=="1" (
        python tools\benchmark_v2_direct.py --verify-e37-clean-lane-profile --run-count 1
    ) else (
        python tools\benchmark_v2_direct.py --verify-e37-profile --run-count 1
    )
) else if /i "!V2_E31_VALIDATION_ACTIVE!"=="1" (
    python tools\benchmark_v2_direct.py --verify-e31-profile --run-count 1
) else if /i "!V2_E28_VALIDATION_ACTIVE!"=="1" (
    python tools\benchmark_v2_direct.py --verify-e28-profile --run-count 1
) else if /i "!V2_E26_VALIDATION_ACTIVE!"=="1" (
    python tools\benchmark_v2_direct.py --verify-e26-profile --run-count 1
) else if /i "!V2_E25_VALIDATION_ACTIVE!"=="1" (
    python tools\benchmark_v2_direct.py --verify-e25-profile --run-count 1
) else if /i "!V2_E22_PREFETCH_OFF!"=="1" (
    python tools\benchmark_v2_direct.py --verify-e22-arm-profile --run-count !V2_E22_REQUESTED_RUN_COUNT!
) else if /i "!V2_E22_PREFETCH_ON!"=="1" (
    python tools\benchmark_v2_direct.py --verify-e22-arm-profile --run-count !V2_E22_REQUESTED_RUN_COUNT!
) else (
    python tools\benchmark_v2_direct.py --verify-d6-profile
)
if errorlevel 1 (
    echo === ERROR: deploy profile validation FAILED - aborting before deploy. Spend zero. ===
    exit /b 1
)
set "V2_CUSTOM_NODE_REUSE_PROVEN=0"
if defined V2_E22_ARM_LABEL (
    python -c "import json,sys,comfyapp; s=json.load(open('.deployed_state.json',encoding='utf-8')); local=comfyapp.custom_node_source_generation(comfyapp._LOCAL_CUSTOM_NODES); deployed=str(s.get('custom_nodes_generation') or ''); print('[v2.volume_publish_preflight] local_generation='+local); print('[v2.volume_publish_preflight] deployed_generation='+deployed); print('[v2.volume_publish_preflight] reuse_proven='+('1' if local and local==deployed else '0')); sys.exit(0 if local and local==deployed else 1)"
    if errorlevel 1 (
        echo === ERROR: exact custom-node Volume reuse proof FAILED - refusing E22 deployment ===
        exit /b 1
    )
    set "V2_CUSTOM_NODE_REUSE_PROVEN=1"
)
if defined V2_E22_ARM_LABEL if not "!V2_E22_REQUESTED_RUN_COUNT!"=="1" echo === ERROR: E22 requires BENCHMARK_RUN_COUNT=1; refusing deployment/request ===
if defined V2_E22_ARM_LABEL if not "!V2_E22_REQUESTED_RUN_COUNT!"=="1" exit /b 1
if "!V2_E25_VALIDATION_ACTIVE!"=="1" if not "!V2_BENCHMARK_RUNS!"=="1" echo === ERROR: E25 validation requires BENCHMARK_RUN_COUNT=1; refusing deployment/request ===
if "!V2_E25_VALIDATION_ACTIVE!"=="1" if not "!V2_BENCHMARK_RUNS!"=="1" exit /b 1
if "!V2_E26_VALIDATION_ACTIVE!"=="1" if not "!V2_BENCHMARK_RUNS!"=="1" echo === ERROR: E26 validation requires BENCHMARK_RUN_COUNT=1; refusing deployment/request ===
if "!V2_E26_VALIDATION_ACTIVE!"=="1" if not "!V2_BENCHMARK_RUNS!"=="1" exit /b 1
if "!V2_E28_VALIDATION_ACTIVE!"=="1" if not "!V2_BENCHMARK_RUNS!"=="1" echo === ERROR: E28 validation requires BENCHMARK_RUN_COUNT=1; refusing deployment/request ===
if "!V2_E28_VALIDATION_ACTIVE!"=="1" if not "!V2_BENCHMARK_RUNS!"=="1" exit /b 1
if "!V2_E31_VALIDATION_ACTIVE!"=="1" if not "!V2_BENCHMARK_RUNS!"=="1" echo === ERROR: E31 validation requires BENCHMARK_RUN_COUNT=1; refusing deployment/request ===
if "!V2_E31_VALIDATION_ACTIVE!"=="1" if not "!V2_BENCHMARK_RUNS!"=="1" exit /b 1
if "!V2_E37_VALIDATION_ACTIVE!"=="1" if not "!V2_BENCHMARK_RUNS!"=="1" echo === ERROR: E37 validation requires BENCHMARK_RUN_COUNT=1; refusing deployment/request ===
if "!V2_E37_VALIDATION_ACTIVE!"=="1" if not "!V2_BENCHMARK_RUNS!"=="1" exit /b 1
if "!V2_PREFLIGHT_ONLY!"=="1" (
    if defined V2_E22_ARM_LABEL echo [v2.preflight] BENCHMARK_RUN_COUNT=!V2_E22_REQUESTED_RUN_COUNT!
    if defined V2_E22_ARM_LABEL echo [v2.preflight] EXPECTED_PAID_REQUEST_COUNT=1
    if defined V2_E22_ARM_LABEL echo [v2.preflight] BENCHMARK_COMMAND=python tools\benchmark_v2_direct.py --run-count !V2_E22_REQUESTED_RUN_COUNT! --conditioning-cache-nonce !V2_E22_CONDITIONING_NONCE!
    if "!V2_E25_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] BENCHMARK_RUN_COUNT=1
    if "!V2_E25_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] EXPECTED_PAID_REQUEST_COUNT=1
    if "!V2_E25_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] BENCHMARK_COMMAND=python tools\benchmark_v2_direct.py --run-count 1 --conditioning-cache-nonce !V2_E25_CONDITIONING_NONCE!
    if "!V2_E26_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] BENCHMARK_RUN_COUNT=1
    if "!V2_E26_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] EXPECTED_PAID_REQUEST_COUNT=1
    if "!V2_E26_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] BENCHMARK_COMMAND=python tools\benchmark_v2_direct.py --run-count 1 --conditioning-cache-nonce !V2_E26_CONDITIONING_NONCE!
    if "!V2_E28_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] BENCHMARK_RUN_COUNT=1
    if "!V2_E28_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] EXPECTED_PAID_REQUEST_COUNT=1
    if "!V2_E28_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] BENCHMARK_COMMAND=python tools\benchmark_v2_direct.py --run-count 1 --conditioning-cache-nonce !V2_E28_CONDITIONING_NONCE!
    if "!V2_E31_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] BENCHMARK_RUN_COUNT=1
    if "!V2_E31_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] EXPECTED_PAID_REQUEST_COUNT=1
    if "!V2_E31_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] BENCHMARK_COMMAND=python tools\benchmark_v2_direct.py --run-count 1 --conditioning-cache-nonce !V2_E31_CONDITIONING_NONCE!
    if "!V2_E37_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] BENCHMARK_RUN_COUNT=1
    if "!V2_E37_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] EXPECTED_PAID_REQUEST_COUNT=1
    if "!V2_E37_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] BENCHMARK_COMMAND=python tools\benchmark_v2_direct.py --run-count 1 --conditioning-cache-nonce !V2_E37_CONDITIONING_NONCE!
    echo [v2.preflight] selector=!V2_E22_ARM_LABEL!
    if "!V2_E25_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] selector=E25_VALIDATION
    if "!V2_E26_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] selector=E26_VALIDATION
    if "!V2_E28_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] selector=E28_VALIDATION
    if "!V2_E31_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] selector=E31_VALIDATION
    if "!V2_E37_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] selector=E37_VALIDATION
    echo [v2.preflight] ATOMIC_PROFILE=!COMFYMODAL_V2_ATOMIC_PROFILE!
    echo [v2.preflight] CHECKPOINT_PREWARM=!COMFYMODAL_V2_CHECKPOINT_PREWARM!
    echo [v2.preflight] FAST_COLD_ORCHESTRATION=!COMFYMODAL_V2_FAST_COLD_ORCHESTRATION!
    echo [v2.preflight] CLIP_FAST_HYDRATION=!COMFYMODAL_V2_CLIP_FAST_HYDRATION!
    echo [v2.preflight] CLIP_SNAPSHOT_EXCLUDE_WEIGHTS=!COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS!
    echo [v2.preflight] SNAPSHOT_EXCLUDE_UNET=!COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET!
    echo [v2.preflight] UNET_FASTSAFETENSORS=!COMFYMODAL_V2_UNET_FASTSAFETENSORS!
    echo [v2.preflight] CRITICAL_GPU_COORDINATION=!COMFYMODAL_V2_CRITICAL_GPU_COORDINATION!
    echo [v2.preflight] SCOPED_CUDA_READINESS=!COMFYMODAL_V2_SCOPED_CUDA_READINESS!
    echo [v2.preflight] STAGED_SAFETENSORS=!COMFYMODAL_V2_STAGED_SAFETENSORS!
    echo [v2.preflight] STAGED_SOURCE_ORDER=!COMFYMODAL_V2_STAGED_SOURCE_ORDER!
    echo [v2.preflight] C9QD_EXTRAS=!COMFYMODAL_V2_C9QD_EXTRAS!
    if "!V2_E25_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] SPECULATIVE_CLIP_HYDRATION=!COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION!
    if "!V2_E25_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] GPU_FAST_RETURN=!COMFYMODAL_V2_GPU_FAST_RETURN!
    if "!V2_E25_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] OPTIMIZATION_DIAGNOSTICS=!COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS!
    if "!V2_E25_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] VAE_ACTIVATION_MODE=!COMFYMODAL_V2_VAE_ACTIVATION_MODE!
    if "!V2_E25_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] VAE_EARLY_START_MS=!COMFYMODAL_V2_VAE_EARLY_START_MS!
    if "!V2_E26_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] SPECULATIVE_CLIP_HYDRATION=!COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION!
    if "!V2_E26_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] GPU_FAST_RETURN=!COMFYMODAL_V2_GPU_FAST_RETURN!
    if "!V2_E26_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] OPTIMIZATION_DIAGNOSTICS=!COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS!
    if "!V2_E26_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] VAE_ACTIVATION_MODE=!COMFYMODAL_V2_VAE_ACTIVATION_MODE!
    if "!V2_E26_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] VAE_EARLY_START_MS=!COMFYMODAL_V2_VAE_EARLY_START_MS!
    if "!V2_E26_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] CHECKPOINT_PREWARM=!COMFYMODAL_V2_CHECKPOINT_PREWARM!
    if "!V2_E31_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] CLIP_QD_READER=!COMFYMODAL_V2_CLIP_QD_READER!
    if "!V2_E31_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] CLIP_QD_QD=!COMFYMODAL_V2_CLIP_QD_QD!
    if "!V2_E31_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] CLIP_QD_BLOCK_MIB=!COMFYMODAL_V2_CLIP_QD_BLOCK_MIB!
    if "!V2_E31_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] CLIP_QD_LAUNCH_POLICY=!COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY!
    if "!V2_E31_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] CLIP_FP32_CAST_ONCE=!COMFYMODAL_V2_CLIP_FP32_CAST_ONCE!
    if "!V2_E31_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] E31_FORENSICS=!COMFYMODAL_V2_E31_FORENSICS!
    if "!V2_E31_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] E31_FORWARD_PROFILE=!COMFYMODAL_V2_E31_FORWARD_PROFILE!
    if "!V2_E37_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] CLIP_QD_READER=!COMFYMODAL_V2_CLIP_QD_READER!
    if "!V2_E37_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] CLIP_QD_QD=!COMFYMODAL_V2_CLIP_QD_QD!
    if "!V2_E37_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] CLIP_QD_BLOCK_MIB=!COMFYMODAL_V2_CLIP_QD_BLOCK_MIB!
    if "!V2_E37_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] CLIP_QD_LAUNCH_POLICY=!COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY!
    if "!V2_E37_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] MINIMAL_RESTORE=!COMFYMODAL_MINIMAL_RESTORE!
    if "!V2_E37_VALIDATION_ACTIVE!"=="1" echo [v2.preflight] E37_STRICT_PROOF=!COMFYMODAL_V2_E37_STRICT_PROOF!
    echo PROFILE ACCEPTED
    echo MODAL_DEPLOY_SKIPPED=1
    exit /b 0
)
if "!V2_E10_BUCKET_FIRST_VALIDATION_ACTIVE!"=="1" (
    python tools\benchmark_v2_direct.py --verify-e10-profile
    if errorlevel 1 (
        echo === ERROR: E10 bucket-first profile validation FAILED - aborting before deploy. Spend zero. ===
        exit /b 1
    )
)

REM -- Workspace loading -------------------------------------------
echo === Loading active workspace ===
set "WS_FILE=%TEMP%\_ws_%RANDOM%.txt"
python -c "import json,sys;d=json.load(open('.modal_workspaces.json'));aid=d.get('active_workspace_id');ws=next((w for w in d.get('workspaces',[])if w.get('id')==aid),None);tid=ws and ws.get('token_id')or'';ts=ws and ws.get('token_secret')or'';label=ws and ws.get('label','')or'';open(sys.argv[1],'w').write('MODAL_TOKEN_ID='+tid+'\nMODAL_TOKEN_SECRET='+ts+'\nMODAL_WORKSPACE_LABEL='+label)" "%WS_FILE%"
if errorlevel 1 (
    echo === ERROR: Python workspace extraction failed ===
    if defined WS_FILE if exist "%WS_FILE%" del /q "%WS_FILE%"
    exit /b 1
)
for /f "usebackq tokens=1,* delims==" %%a in ("%WS_FILE%") do set "%%a=%%b"
if defined WS_FILE if exist "%WS_FILE%" del /q "%WS_FILE%"
if not defined MODAL_TOKEN_ID (
    echo === ERROR: Could not load active workspace credentials ===
    exit /b 1
)
echo === Active workspace: !MODAL_WORKSPACE_LABEL! ===

REM -- Workspace guard (E29 root-cause fix) ----------------------------
REM The modal CLI default profile may point at a DIFFERENT workspace than
REM the active one (e.g. profile "default" -> testing3 while the active
REM workspace is testing6).  Deploying/checking against the wrong workspace
REM silently no-ops or reads the wrong app version.  HARD REFUSE: the
REM workspace label must equal the active workspace's label from
REM .modal_workspaces.json — any mismatch means the credentials did not
REM take effect and the deploy must NOT proceed.
if not defined MODAL_WORKSPACE_LABEL (
    echo === ERROR: active workspace label missing; refusing to deploy ===
    exit /b 1
)

REM -- Warmup profile ----------------------------------------------
echo === Extracting warmup profile from benchmark workflow ===
set "WARMUP_FILE=%TEMP%\_v2warm_%RANDOM%.txt"
python tools\extract_warmup_profile.py > "%WARMUP_FILE%"
if errorlevel 1 (
    type "%WARMUP_FILE%"
    echo === ERROR: Warmup profile derivation failed ===
    if defined WARMUP_FILE if exist "%WARMUP_FILE%" del /q "%WARMUP_FILE%"
    exit /b 1
)
for /f "usebackq delims=" %%a in ("%WARMUP_FILE%") do set "%%a"
if defined WARMUP_FILE if exist "%WARMUP_FILE%" del /q "%WARMUP_FILE%"
echo === Warmup profile loaded ===

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
echo variance_mode=!V2_IS_VARIANCE!
echo volume_read_run_count=!V2_VOLUME_READ_RUN_COUNT!
echo restore_only_mode=!V2_IS_RESTORE_ONLY!
echo restore_only_app=!COMFYMODAL_V2_RESTORE_ONLY_APP_NAME!
echo restore_only_run_count=!V2_RESTORE_ONLY_RUN_COUNT!
echo restore_only_max_attempts=!V2_RESTORE_ONLY_MAX_ATTEMPTS!
echo snapshot_exclude_unet=!COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET!
echo snapshot_construction=!COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION!
echo d6_fastpath_validation=!V2_D6_FASTPATH_VALIDATION!
echo d10_integration_validation=!V2_D10_INTEGRATION_VALIDATION_ACTIVE!
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

REM -- Modal CLI detection -----------------------------------------
where modal >nul 2>nul
if not errorlevel 1 (
    set "MODAL_CLI=modal"
) else (
    set "MODAL_CLI=python -m modal"
)

REM -- Check existing V1 deployment via modal app list --json -------
echo === Checking for existing V1 deployment: comfyui ===
set "V1_CHECK_FILE=%TEMP%\_v1chk_%RANDOM%.txt"
python -c "import json,subprocess,sys;out=subprocess.check_output(sys.argv[1].split()+['app','list','--json'],timeout=30);open(sys.argv[2],'w').write('1'if any(a.get('Description')=='comfyui'and a.get('State','').lower()=='deployed'for a in json.loads(out))else'0')" "!MODAL_CLI!" "%V1_CHECK_FILE%" 2>nul
if errorlevel 1 (
    echo === ERROR: Could not determine whether V1 is deployed ===
    if defined V1_CHECK_FILE if exist "!V1_CHECK_FILE!" del /q "!V1_CHECK_FILE!"
    exit /b 1
)
if not exist "%V1_CHECK_FILE%" (
    echo === ERROR: V1 deployment check produced no result ===
    exit /b 1
)
if exist "%V1_CHECK_FILE%" (
    set /p "V1_EXISTS=" < "%V1_CHECK_FILE%"
    if defined V1_CHECK_FILE if exist "%V1_CHECK_FILE%" del /q "%V1_CHECK_FILE%"
) else (
    echo === ERROR: V1 deployment check result disappeared ===
    exit /b 1
)
if not defined V1_EXISTS (
    echo === ERROR: V1 deployment check result was empty ===
    exit /b 1
)

REM -- Conditional deploy -------------------------------------------
if "!V2_RUN_ONLY!"=="1" (
    echo === Run-only requested; reusing the already-deployed V2 identity ===
    python tools\benchmark_v2_direct.py --prime-registry-proof --run-count !V2_E22_REQUESTED_RUN_COUNT!
    if errorlevel 1 (
        echo === ERROR: registry-proof priming failed in run-only mode ===
        exit /b 1
    )
    goto :v2_benchmark
)
if "!V1_EXISTS!"=="1" (

    REM ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    REM V1 already deployed: deploy V2 only
    REM ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    echo === V1 comfyui already deployed. Deploying V2 only ===

    REM -- Publish local custom nodes to the Volume so baked == persisted at snapshot construction --
    echo === Publishing custom nodes to Volume for V2 generation parity ===
    if "!V2_CUSTOM_NODE_REUSE_PROVEN!"=="1" (
        echo === Reusing custom-node Volume; exact generation already proven ===
    ) else (
        python tools\publish_custom_nodes_volume.py
        if errorlevel 1 (
            echo === ERROR: custom-node Volume publication failed ===
            exit /b 1
        )
    )

    set "V2_LOG=%TEMP%\_v2dpl_%RANDOM%.txt"
    !MODAL_CLI! deploy -m comfymodal_runtime.modal_app --name "!COMFYMODAL_V2_APP_NAME!" > "!V2_LOG!" 2>&1
    set "V2_EXIT=!errorlevel!"

    echo.
    echo === V2 deploy log ===
    type "!V2_LOG!"
    echo.

    if !V2_EXIT! neq 0 (
        echo === ERROR: V2 deploy failed with exit code !V2_EXIT! ===
        if defined V2_LOG if exist "!V2_LOG!" del /q "!V2_LOG!"
        exit /b !V2_EXIT!
    )

    REM ── Deploy-failure detection (E29 root-cause fix) ────────────────────
    REM The Modal client can exit 0 even when the deploy actually failed
    REM (e.g. a Windows charmap codec crash while printing build output, or a
    REM Modal-side error box).  NEVER treat such a deploy as successful: scan
    REM the captured log for the Modal error-box marker, a Python traceback,
    REM or the charmap codec crash signature, and fail hard when present.
    findstr /C:"+- Error" /C:"Traceback (most recent call last)" /C:"charmap" /C:"codec can't encode" "!V2_LOG!" >nul 2>nul
    if not errorlevel 1 (
        echo === ERROR: V2 deploy output contains a Modal/Python error marker despite exit 0 ===
        echo === The deployed app was NOT updated. Refusing to continue. ===
        if defined V2_LOG if exist "!V2_LOG!" del /q "!V2_LOG!"
        exit /b 1
    )

    REM Validate V2 identifiers
    python -c "import sys; s=''.join(open(sys.argv[1],encoding='utf-8',errors='replace').read().split()); sys.exit(0 if ''.join(sys.argv[2].split()) in s else 1)" "!V2_LOG!" "!V2_DEPLOY_IDENT!"
    if errorlevel 1 (
        echo === ERROR: V2 deploy output missing target app identifier !V2_DEPLOY_IDENT! ===
        if defined V2_LOG if exist "!V2_LOG!" del /q "!V2_LOG!"
        exit /b 1
    )
    findstr /C:"ModalRuntimeEntrypointV2" "!V2_LOG!" >nul 2>nul
    if errorlevel 1 (
        echo === ERROR: V2 deploy output missing V2 class identifier ===
        if defined V2_LOG if exist "!V2_LOG!" del /q "!V2_LOG!"
        exit /b 1
    )

    if defined V2_LOG if exist "!V2_LOG!" del /q "!V2_LOG!"
    echo === V2 deploy verified OK ===
    REM -- Record the ACTUAL baked deployment identity (container readback) so plan builds carry the exact deployed hash --
    echo === Recording baked deployment identity ===
    python tools\record_deployment_identity.py
    if errorlevel 1 (
        echo === ERROR: deployment identity record failed ===
        exit /b 1
    )

    REM -- Prime the local registry-proof/validation store (D1 zero-gap): registry work happens at deploy time, before any user benchmark trigger --
    python tools\benchmark_v2_direct.py --prime-registry-proof
    if errorlevel 1 (
        echo === ERROR: registry-proof priming failed ===
        exit /b 1
    )

) else (

    REM ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    REM No V1 deployed: deploy V1 and V2 concurrently
    REM ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    echo === No existing V1 found. Deploying V1 and V2 concurrently ===

    set "V1_CMD_FILE=%TEMP%\_v1cmd_%RANDOM%.bat"
    set "V2_CMD_FILE=%TEMP%\_v2cmd_%RANDOM%.bat"
    set "V1_LOG=%TEMP%\_v1dpl_%RANDOM%.txt"
    set "V2_LOG=%TEMP%\_v2dpl_%RANDOM%.txt"
    set "DEPLOY_RESULT=%TEMP%\_dplres_%RANDOM%.txt"

    if not defined COMFYMODAL_DEPLOY_TIMEOUT_SECONDS set "COMFYMODAL_DEPLOY_TIMEOUT_SECONDS=3600"

    > "!V1_CMD_FILE!" echo @echo off
    >>"!V1_CMD_FILE!" echo !MODAL_CLI! deploy comfyapp.py
    >>"!V1_CMD_FILE!" echo exit /b %%errorlevel%%
    > "!V2_CMD_FILE!" echo @echo off
    >>"!V2_CMD_FILE!" echo !MODAL_CLI! deploy -m comfymodal_runtime.modal_app --name "!COMFYMODAL_V2_APP_NAME!"
    >>"!V2_CMD_FILE!" echo exit /b %%errorlevel%%

    echo === Deploying V1 and V2 concurrently. Timeout=!COMFYMODAL_DEPLOY_TIMEOUT_SECONDS!s ===
    python tools\run_deploys_concurrent.py ^
        "!V1_CMD_FILE!" "!V2_CMD_FILE!" ^
        "!V1_LOG!" "!V2_LOG!" ^
        "!COMFYMODAL_DEPLOY_TIMEOUT_SECONDS!" ^
        > "!DEPLOY_RESULT!"
    set "PARALLEL_EXIT=!errorlevel!"

    REM Clean command files immediately
    if defined V1_CMD_FILE if exist "!V1_CMD_FILE!" del /q "!V1_CMD_FILE!"
    if defined V2_CMD_FILE if exist "!V2_CMD_FILE!" del /q "!V2_CMD_FILE!"

    REM Parse result
    set "V1_DEPLOY_EXIT="
    set "V2_DEPLOY_EXIT="
    set "TIMED_OUT="
    for /f "usebackq tokens=1,* delims==" %%a in ("!DEPLOY_RESULT!") do (
        if "%%a"=="V1_EXIT" set "V1_DEPLOY_EXIT=%%b"
        if "%%a"=="V2_EXIT" set "V2_DEPLOY_EXIT=%%b"
        if "%%a"=="TIMED_OUT" set "TIMED_OUT=%%b"
    )
    if defined DEPLOY_RESULT if exist "!DEPLOY_RESULT!" del /q "!DEPLOY_RESULT!"

    REM Surface logs
    echo.
    echo === V1 deploy log ===
    type "!V1_LOG!" 2>nul
    echo.
    echo === V2 deploy log ===
    type "!V2_LOG!" 2>nul
    echo.

    REM Validate: timeout
    if /i "!TIMED_OUT!"=="true" (
        echo === ERROR: Concurrent deploy timed out after !COMFYMODAL_DEPLOY_TIMEOUT_SECONDS!s ===
        if defined V1_LOG if exist "!V1_LOG!" del /q "!V1_LOG!"
        if defined V2_LOG if exist "!V2_LOG!" del /q "!V2_LOG!"
        exit /b 1
    )

    REM Validate V1 exit code for this deploy
    if not defined V1_DEPLOY_EXIT set "V1_DEPLOY_EXIT=-1"
    if !V1_DEPLOY_EXIT! neq 0 (
        echo === ERROR: V1 deploy failed with exit code !V1_DEPLOY_EXIT! ===
        if defined V1_LOG if exist "!V1_LOG!" del /q "!V1_LOG!"
        if defined V2_LOG if exist "!V2_LOG!" del /q "!V2_LOG!"
        exit /b !V1_DEPLOY_EXIT!
    )

    REM Validate V1 output contains comfyui app identifier
    findstr /C:"comfyui" "!V1_LOG!" >nul 2>nul
    if errorlevel 1 (
        echo === ERROR: V1 deploy output missing 'comfyui' app identifier ===
        if defined V1_LOG if exist "!V1_LOG!" del /q "!V1_LOG!"
        if defined V2_LOG if exist "!V2_LOG!" del /q "!V2_LOG!"
        exit /b 1
    )

    REM Validate V2 exit code
    if not defined V2_DEPLOY_EXIT set "V2_DEPLOY_EXIT=-1"
    if !V2_DEPLOY_EXIT! neq 0 (
        echo === ERROR: V2 deploy failed with exit code !V2_DEPLOY_EXIT! ===
        if defined V1_LOG if exist "!V1_LOG!" del /q "!V1_LOG!"
        if defined V2_LOG if exist "!V2_LOG!" del /q "!V2_LOG!"
        exit /b !V2_DEPLOY_EXIT!
    )
    REM ── Deploy-failure detection (E29 root-cause fix; mirrors the first
    REM deploy check): a Modal client that exits 0 with an error marker in
    REM the log must never be treated as a successful deploy. ──
    findstr /C:"+- Error" /C:"Traceback (most recent call last)" /C:"charmap" /C:"codec can't encode" "!V2_LOG!" >nul 2>nul
    if not errorlevel 1 (
        echo === ERROR: V2 deploy output contains a Modal/Python error marker despite exit 0 ===
        echo === The deployed app was NOT updated. Refusing to continue. ===
        if defined V1_LOG if exist "!V1_LOG!" del /q "!V1_LOG!"
        if defined V2_LOG if exist "!V2_LOG!" del /q "!V2_LOG!"
        exit /b 1
    )

    REM Validate V2 identifiers
    python -c "import sys; s=''.join(open(sys.argv[1],encoding='utf-8',errors='replace').read().split()); sys.exit(0 if ''.join(sys.argv[2].split()) in s else 1)" "!V2_LOG!" "!V2_DEPLOY_IDENT!"
    if errorlevel 1 (
        echo === ERROR: V2 deploy output missing target app identifier !V2_DEPLOY_IDENT! ===
        if defined V1_LOG if exist "!V1_LOG!" del /q "!V1_LOG!"
        if defined V2_LOG if exist "!V2_LOG!" del /q "!V2_LOG!"
        exit /b 1
    )
    findstr /C:"ModalRuntimeEntrypointV2" "!V2_LOG!" >nul 2>nul
    if errorlevel 1 (
        echo === ERROR: V2 deploy output missing V2 class identifier ===
        if defined V1_LOG if exist "!V1_LOG!" del /q "!V1_LOG!"
        if defined V2_LOG if exist "!V2_LOG!" del /q "!V2_LOG!"
        exit /b 1
    )

    REM Clean deploy logs
    if defined V1_LOG if exist "!V1_LOG!" del /q "!V1_LOG!"
    if defined V2_LOG if exist "!V2_LOG!" del /q "!V2_LOG!"

    echo === V1 and V2 deploys both verified OK ===

    REM -- Publish local custom nodes to the Volume so baked == persisted at snapshot construction --
    REM V1 is now deployed and verified, so the V1 remote sync function is reachable.
    echo === Publishing custom nodes to Volume for V2 generation parity ===
    if "!V2_CUSTOM_NODE_REUSE_PROVEN!"=="1" (
        echo === Reusing custom-node Volume; exact generation already proven ===
    ) else (
        python tools\publish_custom_nodes_volume.py
        if errorlevel 1 (
            echo === ERROR: custom-node Volume publication failed ===
            exit /b 1
        )
    )

    REM -- Re-deploy V2 so snapshot construction sees the freshly published Volume --
    REM V2 was deployed above while the Volume generation record was still stale.
    set "V2_RELOG=%TEMP%\_v2rdpl_%RANDOM%.txt"
    !MODAL_CLI! deploy -m comfymodal_runtime.modal_app --name "!COMFYMODAL_V2_APP_NAME!" > "!V2_RELOG!" 2>&1
    set "V2_REEXIT=!errorlevel!"
    echo.
    echo === V2 re-deploy log after Volume publish ===
    type "!V2_RELOG!"
    echo.
    if !V2_REEXIT! neq 0 (
        echo === ERROR: V2 re-deploy after Volume publish failed with exit code !V2_REEXIT! ===
        if defined V2_RELOG if exist "!V2_RELOG!" del /q "!V2_RELOG!"
        exit /b !V2_REEXIT!
    )
    REM ── Deploy-failure detection (E29 root-cause fix; mirrors the first
    REM deploy check): a Modal client that exits 0 with an error marker in
    REM the log must never be treated as a successful re-deploy. ──
    findstr /C:"+- Error" /C:"Traceback (most recent call last)" /C:"charmap" /C:"codec can't encode" "!V2_RELOG!" >nul 2>nul
    if not errorlevel 1 (
        echo === ERROR: V2 re-deploy output contains a Modal/Python error marker despite exit 0 ===
        echo === The deployed app was NOT updated. Refusing to continue. ===
        if defined V2_RELOG if exist "!V2_RELOG!" del /q "!V2_RELOG!"
        exit /b 1
    )
    if defined V2_RELOG if exist "!V2_RELOG!" del /q "!V2_RELOG!"
    echo === V2 re-deploy after Volume publish verified OK ===
    REM -- Record the ACTUAL baked deployment identity (container readback) so plan builds carry the exact deployed hash --
    echo === Recording baked deployment identity ===
    python tools\record_deployment_identity.py
    if errorlevel 1 (
        echo === ERROR: deployment identity record failed ===
        exit /b 1
    )

    REM -- Prime the local registry-proof/validation store (D1 zero-gap): registry work happens at deploy time, before any user benchmark trigger --
    python tools\benchmark_v2_direct.py --prime-registry-proof
    if errorlevel 1 (
        echo === ERROR: registry-proof priming failed ===
        exit /b 1
    )
)

if /i "!COMFYMODAL_DEPLOY_ONLY!"=="1" (
    echo === Deploy-only requested; acceptance benchmark skipped ===
    exit /b 0
)

:v2_benchmark
REM -- Benchmark invocation ------------------------------------------
REM Production default: V2_BENCHMARK_MODE=snapshot_restore_only ->
REM deploy the restore-only shadow app (accepted production config) and
REM EXIT after construction (this script never issues probes).  Run
REM batches with run_v2_single.bat (defaults V2_BENCHMARK_RUNS=10,
REM V2_BENCHMARK_GAP_SECONDS=35 -> 10 cold runs, 35 s cooldown).  The
REM acceptance sequence (A fresh / B reused / C fresh, ~3+ requests)
REM runs ONLY via the explicit opt-in env V2_BENCHMARK_MODE=acceptance.
REM The variance-cold sequence (one request at a time, 25s gap, strict
REM cold-identity proof) runs ONLY via the explicit opt-in
REM V2_BENCHMARK_MODE=variance_cold.  The four-condition round-robin
REM matrix runs ONLY via the explicit opt-in V2_BENCHMARK_MODE=variance_matrix.
REM The mounted-Volume raw sequential-read benchmark (pure volume read
REM speed, no model workload) runs ONLY via the explicit opt-in
REM V2_BENCHMARK_MODE=volume_read.
REM The UNET-absent snapshot restore-only mode is a snapshot CONSTRUCTION
REM invocation: it deploys with COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET=1
REM (identity/reporting gate), builds the full CLIP/UNET/VAE snapshot, then
REM evicts the UNET via the clip_vae retain role (fresh CLIP+VAE kept in the
REM retained container, unet proven dead) and exits WITHOUT issuing reuse
REM probes (this invocation is labeled/excluded from the probe count).  The
REM exactly-6 valid reuse probes are issued ONLY via run_v2_single.bat with
REM V2_BENCHMARK_MODE=snapshot_restore_only.
for /f %%a in ('powershell -NoProfile -Command "[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()"') do set "COMFYMODAL_COMMAND_START_UNIX_MS=%%a"
if /i "!V2_BENCHMARK_MODE!"=="variance_matrix" (
    echo === Running V2 variance-cold MATRIX - explicit opt-in ===
    python tools\benchmark_v2_direct.py --variance-matrix
    if errorlevel 1 (
        echo === ERROR: Variance-cold matrix benchmark failed ===
        exit /b 1
    )
    echo === V2 variance-cold matrix benchmark completed ===
) else if /i "!V2_BENCHMARK_MODE!"=="variance_cold" (
    echo === Running V2 variance-cold benchmark - explicit opt-in ===
    if not defined V2_VARIANCE_RUN_COUNT set "V2_VARIANCE_RUN_COUNT=!V2_BENCHMARK_RUNS!"
    python tools\benchmark_v2_direct.py --variance-cold --variance-pretouch !V2_PROFILE_PRETOUCH!
    if errorlevel 1 (
        echo === ERROR: Variance-cold benchmark failed ===
        exit /b 1
    )
    echo === V2 variance-cold benchmark completed ===
) else if /i "!V2_BENCHMARK_MODE!"=="acceptance" (
    echo === Running V2 acceptance benchmark - explicit opt-in ===
    python tools\benchmark_v2_direct.py --acceptance
    if errorlevel 1 (
        echo === ERROR: Acceptance benchmark failed ===
        exit /b 1
    )
    echo === V2 acceptance benchmark completed ===
) else if /i "!V2_BENCHMARK_MODE!"=="host_ab" (
    echo === Running V2 host-characteristics cold study - explicit opt-in ===
    python tools\benchmark_v2_direct.py --host-ab --teardown minimal
    if errorlevel 1 (
        echo === ERROR: Host-AB benchmark failed ===
        exit /b 1
    )
    echo === V2 host-characteristics cold study completed ===
) else if /i "!V2_BENCHMARK_MODE!"=="volume_read" (
    echo === Running V2 mounted-Volume raw sequential-read benchmark - explicit opt-in ===
    python tools\benchmark_v2_direct.py --volume-read
    if errorlevel 1 (
        echo === ERROR: Volume-read benchmark failed ===
        exit /b 1
    )
    echo === V2 mounted-Volume raw sequential-read benchmark completed ===
) else if /i "!V2_BENCHMARK_MODE!"=="e25_single" (
    echo === Running V2 E25 whole-critical-path validation - single cold run ===
    if defined V2_E25_CONDITIONING_NONCE (
        python tools\benchmark_v2_direct.py --run-count 1 --conditioning-cache-nonce !V2_E25_CONDITIONING_NONCE!
    ) else (
        python tools\benchmark_v2_direct.py --run-count 1
    )
    if errorlevel 1 (
        echo === ERROR: E25 validation benchmark failed ===
        exit /b 1
    )
    echo === V2 E25 validation benchmark completed ===
) else if /i "!V2_BENCHMARK_MODE!"=="e26_single" (
    echo === Running V2 E26 concrete-cold-wins validation - single cold run ===
    if defined V2_E26_CONDITIONING_NONCE (
        python tools\benchmark_v2_direct.py --run-count 1 --conditioning-cache-nonce !V2_E26_CONDITIONING_NONCE!
    ) else (
        python tools\benchmark_v2_direct.py --run-count 1
    )
    if errorlevel 1 (
        echo === ERROR: E26 validation benchmark failed ===
        exit /b 1
    )
    echo === V2 E26 validation benchmark completed ===
) else if /i "!V2_BENCHMARK_MODE!"=="e37_single" (
    echo === Running V2 E37 late CLIP validation - single cold generation ===
    if defined V2_E37_CONDITIONING_NONCE (
        python tools\benchmark_v2_direct.py --run-count 1 --conditioning-cache-nonce !V2_E37_CONDITIONING_NONCE!
    ) else (
        echo === ERROR: E37 validation requires a conditioning nonce ===
        exit /b 1
    )
    if errorlevel 1 (
        echo === ERROR: E37 validation benchmark failed ===
        exit /b 1
    )
    echo === V2 E37 validation benchmark completed ===
) else if /i "!V2_BENCHMARK_MODE!"=="e31_single" (
    echo === Running V2 E31 QD4 cast-once validation - single cold run ===
    if defined V2_E31_CONDITIONING_NONCE (
        python tools\benchmark_v2_direct.py --run-count 1 --conditioning-cache-nonce !V2_E31_CONDITIONING_NONCE!
    ) else (
        echo === ERROR: E31 validation requires a conditioning nonce ===
        exit /b 1
    )
    if errorlevel 1 (
        echo === ERROR: E31 validation benchmark failed ===
        exit /b 1
    )
    echo === V2 E31 validation benchmark completed ===
) else if /i "!V2_BENCHMARK_MODE!"=="e28_single" (
    echo === Running V2 E28 critical-path validation - single cold run ===
    if defined V2_E28_CONDITIONING_NONCE (
        python tools\benchmark_v2_direct.py --run-count 1 --conditioning-cache-nonce !V2_E28_CONDITIONING_NONCE!
    ) else (
        python tools\benchmark_v2_direct.py --run-count 1
    )
    if errorlevel 1 (
        echo === ERROR: E28 validation benchmark failed ===
        exit /b 1
    )
    echo === V2 E28 validation benchmark completed ===
) else if /i "!V2_BENCHMARK_MODE!"=="snapshot_restore_only" (
    echo ======================================================================
    echo === V2 UNET-absent snapshot CONSTRUCTION invocation - labeled/excluded ===
    echo === App deployed with COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET=1          ===
    echo === Identity gate; UNET evicted via clip_vae retain before capture   ===
    echo === This invocation issues NO reuse probes.                         ===
    echo === Issue the exactly-6 valid reuse probes with:                    ===
    echo ===   run_v2_single.bat with V2_BENCHMARK_MODE=snapshot_restore_only ===
    echo ======================================================================
    exit /b 0
) else (
    echo === Running V2 benchmark - single run by default ===
    if defined V2_E22_CONDITIONING_NONCE (
        python tools\benchmark_v2_direct.py --run-count !V2_E22_REQUESTED_RUN_COUNT! --conditioning-cache-nonce !V2_E22_CONDITIONING_NONCE!
    ) else (
        python tools\benchmark_v2_direct.py
    )
    if errorlevel 1 (
        echo === ERROR: Benchmark failed ===
        exit /b 1
    )
    echo === V2 benchmark completed ===
)
exit /b 0
