from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = (ROOT / "deploy_and_run_v2_single.bat").read_text(encoding="utf-8")
RUN = (ROOT / "run_v2_single.bat").read_text(encoding="utf-8")
FULL_TRACE = (ROOT / "deploy_v2_full_trace_only.bat").read_text(encoding="utf-8")
MODAL_APP = (ROOT / "comfymodal_runtime" / "modal_app.py").read_text(encoding="utf-8")
MODAL_TRANSPORT = (ROOT / "comfymodal_runtime" / "modal_transport.py").read_text(encoding="utf-8")
BENCHMARK = (ROOT / "tools" / "benchmark_v2_direct.py").read_text(encoding="utf-8")


def test_profiles_are_explicit_and_supported_in_both_batches():
    for source in (DEPLOY, RUN):
        assert 'if not defined COMFYMODAL_V2_ENV_PROFILE set "COMFYMODAL_V2_ENV_PROFILE=production"' in source
        assert '=="production"' in source
        assert '=="diagnostic"' in source
        assert "COMFYMODAL_V2_FULL_TRACE=0" in source
        assert "COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS=0" in source
        assert "COMFYMODAL_V2_DEEP_MODEL_DIAG=0" in source
        assert "COMFYMODAL_V2_PAGEFAULT_TRACKING=0" in source
        assert "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT=0" in source
        assert "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS=0" in source
        assert "COMFYMODAL_V2_EVICT_RETAIN_ROLE=" in source
        assert "COMFYMODAL_V2_PREFILL_LANES=critical" in source
        assert "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET=0" in source
        assert "COMFYMODAL_V2_RESTORE_TORCH_THREADS=" in source


def test_default_snapshot_and_caller_benchmark_values_are_preserved():
    for source in (DEPLOY, RUN):
        assert 'if not defined V2_BENCHMARK_RUNS set "V2_BENCHMARK_RUNS=1"' in source
        assert 'if not defined V2_BENCHMARK_GAP_SECONDS set "V2_BENCHMARK_GAP_SECONDS=0"' in source
        for key, value in (
            ("COMFYMODAL_V2_CPU_MODEL_SNAPSHOT", "1"),
            ("COMFYMODAL_V2_VAE_SNAPSHOT", "1"),
            ("COMFYMODAL_V2_CLIP_CONDITIONING_CACHE", "1"),
            ("COMFYMODAL_V2_UNET_ACTIVATION_MODE", "late"),
            ("COMFYMODAL_V2_VAE_ACTIVATION_MODE", "sampling_end"),
            ("COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE", "1"),
        ):
            assert f'if not defined {key} set "{key}={value}"' in source


def test_production_memory_and_release_defaults_are_explicit():
    for source in (DEPLOY, RUN):
        assert 'if not defined COMFYMODAL_V2_MEMORY_MB set "COMFYMODAL_V2_MEMORY_MB=49152"' in source
        assert 'if not defined COMFYMODAL_V2_BASELINE_MEMORY_REQUEST set "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST=49152"' in source
        assert 'if not defined COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST set "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST=1"' in source
        assert 'echo release_gpu_after_request=!COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST!' in source
    assert 'if not defined COMFYMODAL_V2_MEMORY_MB set "COMFYMODAL_V2_MEMORY_MB=49152"' in FULL_TRACE
    assert 'if not defined COMFYMODAL_V2_BASELINE_MEMORY_REQUEST set "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST=49152"' in FULL_TRACE
    assert 'if not defined COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST set "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST=0"' in FULL_TRACE


def test_acceptance_is_opt_in_env_only_in_both_batches():
    """V2_BENCHMARK_RUNS=1 must perform exactly one run by default; the
    acceptance A/B/C sequence runs ONLY via the explicit opt-in env
    V2_BENCHMARK_MODE=acceptance in both single-run launchers."""
    for source in (DEPLOY, RUN):
        assert 'if /i "!V2_BENCHMARK_MODE!"=="acceptance" (' in source
        # Default branch must run the plain benchmark (honours V2_BENCHMARK_RUNS).
        assert "python tools\\benchmark_v2_direct.py" in source
        # The opt-in branch runs --acceptance; the default branch runs the
        # plain benchmark (which honours V2_BENCHMARK_RUNS=1).
        _optin = source.index('if /i "!V2_BENCHMARK_MODE!"=="acceptance" (')
        _accept_line = source.index("--acceptance")
        _plain = source.index("python tools\\benchmark_v2_direct.py", _accept_line)
        assert _optin < _accept_line < _plain
        assert ") else (" in source[_optin:_plain]
    # Single-run contract: both launchers default V2_BENCHMARK_RUNS to 1 when
    # the caller did not set it (caller override preserved).
    for source in (DEPLOY, RUN):
        assert 'if not defined V2_BENCHMARK_RUNS set "V2_BENCHMARK_RUNS=1"' in source


def test_deploy_only_is_after_deploy_verification_and_before_acceptance():
    guard = 'if /i "!COMFYMODAL_DEPLOY_ONLY!"=="1"'
    assert guard in DEPLOY
    assert DEPLOY.index(guard) > DEPLOY.index("=== V2 deploy verified OK ===")
    # The opt-in acceptance branch still carries the canonical marker.
    assert DEPLOY.index(guard) < DEPLOY.index("=== Running V2 acceptance benchmark - explicit opt-in ===")
    assert "=== V2 acceptance benchmark completed ===" in DEPLOY
    assert "Deploy-only requested; acceptance benchmark skipped" in DEPLOY


def test_identity_workspace_warmup_and_concurrent_deploy_paths_remain():
    for source in (DEPLOY, RUN):
        assert "stable-modal-comfy-v2-shadow" in source
        assert "ModalRuntimeEntrypointV2" in source
        assert "rtx-pro-6000" in source
    assert ".modal_workspaces.json" in DEPLOY
    assert "extract_warmup_profile.py" in DEPLOY
    assert "run_deploys_concurrent.py" in DEPLOY


def test_profile_summary_is_sanitized():
    for source in (DEPLOY, RUN):
        marker = source.index("[v2.env_profile]")
        summary = source[marker:]
        assert "MODAL_TOKEN_ID" not in summary
        assert "MODAL_TOKEN_SECRET" not in summary
        for field in (
            "env_profile",
            "cpu_model_snapshot",
            "vae_snapshot",
            "clip_conditioning_cache",
            "unet_activation_mode",
            "vae_activation_mode",
            "persistent_local_handle",
            "release_gpu_after_request",
        ):
            assert f"echo {field}=" in summary


def test_profile_summary_has_no_leaked_batch_else_syntax():
    for source in (DEPLOY, RUN):
        assert 'else set "V2_PROFILE_' not in source
        assert 'eviction_role=none"' not in source
        assert 'restore_torch_threads=none"' not in source
        assert 'if defined COMFYMODAL_V2_EVICT_RETAIN_ROLE (' in source
        assert 'if defined COMFYMODAL_V2_RESTORE_TORCH_THREADS (' in source


def test_profile_flags_are_forwarded_to_remote_runtime_allowlist():
    for key in (
        "COMFYMODAL_V2_ENV_PROFILE",
        "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT",
        "COMFYMODAL_V2_VAE_SNAPSHOT",
        "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE",
        "COMFYMODAL_V2_UNET_ACTIVATION_MODE",
        "COMFYMODAL_V2_VAE_ACTIVATION_MODE",
        "COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS",
        "COMFYMODAL_V2_DEEP_MODEL_DIAG",
        "COMFYMODAL_V2_PAGEFAULT_TRACKING",
        "COMFYMODAL_V2_PREFILL_LANES",
        "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET",
        "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST",
    ):
        assert f'"{key}"' in MODAL_APP


def test_request_profile_forwarding_and_owner_scope_remain_unchanged():
    assert '_local_env_profile = os.environ.get(' in MODAL_TRANSPORT
    assert '_origin_from_meta["env_profile"] = _local_env_profile' in MODAL_TRANSPORT
    assert 'plan_dict["__request_origin_info__"] = _origin_from_meta' in MODAL_TRANSPORT
    assert "env_profile" not in (ROOT / "comfymodal_runtime" / "local_handle_owner.py").read_text(encoding="utf-8")


def test_production_profile_guard_uses_remote_metadata():
    assert "def _validate_remote_profile" in BENCHMARK
    assert 'requested_profile != "production"' in BENCHMARK
    assert 'request_origin.get("env_profile", "")' in BENCHMARK
    assert "V2 production profile mismatch:" in BENCHMARK
    assert "remote_effective=" in BENCHMARK
    assert "The benchmark would bypass the CPU snapshot fast path." in BENCHMARK


def test_benchmark_waterfall_is_emitted_by_remote_modal_runtime():
    assert "from .v2_waterfall import build_waterfall, render_waterfall" in MODAL_APP
    assert 'trigger_source", "")).lower() in {"benchmark", "acceptance_benchmark"}' in MODAL_APP
    assert "attach_waterfall(data, report=_waterfall, run_label=_run_label)" in MODAL_APP
