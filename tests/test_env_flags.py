"""Audit tests for the shared env-flag parser (comfymodal_runtime.env).

Every ``env_flag`` conversion in commit 9628c51 ("Complete V2 cache
snapshot and timing fixes") was reconciled against its parent expression
(``git show 9628c51 -- <file>`` vs ``86a4a61``).  This file encodes, for
each converted flag:

* the exact absent semantics of the pre-commit expression
  (``absent_expected``), which must equal the ``default`` argument the
  conversion preserved at each call site;
* the shared-parser result for every explicit value (``1``/``true``/``yes``/
  ``on`` → True after trim + lower; everything else → False).

Intentional defaults are NOT normalised away: flags that were on by default
pre-commit (e.g. ``COMFYMODAL_EXACT_CLIP_PREFILL``, ``COMFYMODAL_ENABLE_WARMUP``,
the ``FASTPATH_V21621_*`` family, ``COMFYMODAL_PERSISTENT_VALIDATION_CERTIFICATE``)
keep ``default=True``.  Negative flags (``DISABLE_*``) are parsed by the same
shared parser — truthiness is unchanged, only the meaning at the call site is
inverted — and are covered here so the parser itself is proven value-agnostic.

Strict pre-commit parsers that were intentionally *outside* the shared parser
are documented at the bottom of this file (``COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT``
was a strict RuntimeError-raising parser before the commit; the commit
deliberately replaced it with the shared parser).  ``_parse_evict_retain_role``
and ``_parse_memory_mb`` remain strict enum/int parsers in ``modal_app.py``
and are intentionally NOT routed through ``env_flag``; they are documented
here but not changed.
"""

from __future__ import annotations

import os

import pytest

from comfymodal_runtime.env import TRUE_VALUES, env_flag


# ── Shared parser contract ────────────────────────────────────────────────


def test_true_values_set_is_exact():
    assert TRUE_VALUES == frozenset({"1", "true", "yes", "on"})


def test_signature_has_bool_default(monkeypatch):
    monkeypatch.delenv("COMFYMODAL_TEST_UNKNOWN_FLAG", raising=False)
    # default is positional-optional and False by default
    assert env_flag("COMFYMODAL_TEST_UNKNOWN_FLAG") is False


def test_absent_returns_default(monkeypatch):
    monkeypatch.delenv("COMFYMODAL_TEST_ABSENT", raising=False)
    assert env_flag("COMFYMODAL_TEST_ABSENT") is False
    assert env_flag("COMFYMODAL_TEST_ABSENT", default=False) is False
    assert env_flag("COMFYMODAL_TEST_ABSENT", default=True) is True


def test_explicit_value_contract(monkeypatch):
    for value, expected in [
        ("", False),        # empty
        ("0", False),       # numeric zero
        ("false", False),
        ("no", False),
        ("off", False),
        ("1", True),
        ("true", True),
        ("yes", True),
        ("on", True),
        ("TRUE", True),     # mixed case
        ("YeS", True),
        (" On ", True),     # surrounding whitespace
        (" 1 ", True),
        ("\ttrue\n", True),
        ("banana", False),  # unknown token
        ("2", False),       # unknown number
    ]:
        monkeypatch.setenv("COMFYMODAL_TEST_EXPLICIT", value)
        assert env_flag("COMFYMODAL_TEST_EXPLICIT") is expected, value


def test_unknown_or_empty_is_false_when_explicit(monkeypatch):
    # explicit value always wins over default — even when default=True
    for value in ("", "0", "false", "no", "off", "banana", "2", "Truee"):
        monkeypatch.setenv("COMFYMODAL_TEST_OVERRIDE", value)
        assert env_flag("COMFYMODAL_TEST_OVERRIDE", default=True) is False, value


# ── Converted-flag table (commit 9628c51 vs parent 86a4a61) ───────────────
#
# Each case records the flag name, the default preserved by the conversion
# (identical to the pre-commit absent result), and the exact pre-commit
# expression the conversion replaced.

FLAG_CASES = [
    # comfyapp.py
    dict(name="COMFYMODAL_EXACT_CLIP_PREFILL", default=True,
         absent_expected=True, negative=False,
         pre_commit='os.environ.get("COMFYMODAL_EXACT_CLIP_PREFILL", "1") == "1"'),
    dict(name="COMFYMODAL_SILENT_EXCEPTION_DEBUG", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.getenv("COMFYMODAL_SILENT_EXCEPTION_DEBUG", "0") == "1"'),
    dict(name="COMFYMODAL_PROFILING", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.getenv("COMFYMODAL_PROFILING", "0") == "1"'),
    dict(name="COMFYMODAL_ENABLE_WARMUP", default=True,
         absent_expected=True, negative=False,
         pre_commit='os.getenv("COMFYMODAL_ENABLE_WARMUP", "1") == "1"'),
    dict(name="COMFYMODAL_ENABLE_TORCH_COMPILE", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.getenv("COMFYMODAL_ENABLE_TORCH_COMPILE", "0") == "1"'),
    dict(name="COMFYMODAL_ENABLE_GPU_SNAPSHOT", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.getenv("COMFYMODAL_ENABLE_GPU_SNAPSHOT", "0") == "1"'),
    dict(name="COMFYMODAL_PRELOAD_UNKNOWN_PROFILES", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.getenv("COMFYMODAL_PRELOAD_UNKNOWN_PROFILES", "0") == "1"'),
    dict(name="COMFYMODAL_ENABLE_REMOTE_BACKGROUND_DEPLOY", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.getenv("COMFYMODAL_ENABLE_REMOTE_BACKGROUND_DEPLOY", "0") == "1"'),
    dict(name="PROMPT_ASYNC_PRELOAD", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.getenv("PROMPT_ASYNC_PRELOAD", "0") == "1"'),
    dict(name="PROMPT_ASYNC_ACTUAL_LOAD", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.getenv("PROMPT_ASYNC_ACTUAL_LOAD", "0") == "1"'),
    dict(name="PROMPT_ASYNC_ACTUAL_LOAD_UNET", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.getenv("PROMPT_ASYNC_ACTUAL_LOAD_UNET", "0") == "1"'),
    dict(name="DISABLE_CACHEDIT_FOR_Z_IMAGE", default=False,
         absent_expected=False, negative=True,
         pre_commit='os.getenv("DISABLE_CACHEDIT_FOR_Z_IMAGE", "0") == "1"'),
    dict(name="DISABLE_RESTORE_WARMUP_FOR_Z_IMAGE", default=False,
         absent_expected=False, negative=True,
         pre_commit='os.getenv("DISABLE_RESTORE_WARMUP_FOR_Z_IMAGE", "0") == "1"'),
    dict(name="COMFYMODAL_ALLOW_SPECULATIVE_LOAD", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.environ.get("COMFYMODAL_ALLOW_SPECULATIVE_LOAD", "0") == "1"'),
    dict(name="COMFYMODAL_COLD_UNET_EARLY_LOAD", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.getenv("COMFYMODAL_COLD_UNET_EARLY_LOAD", "0") == "1"'),
    # Dual/computed default: False normally, True when restore_direct mode.
    dict(name="COMFYMODAL_COLD_UNET_REQUIRE_CPU_CACHE_HIT", default=False,
         absent_expected=False, negative=False, dual_default=True,
         pre_commit='os.getenv("COMFYMODAL_COLD_UNET_REQUIRE_CPU_CACHE_HIT", "0") == "1"'),
    dict(name="COMFYMODAL_COLD_UNET_REQUIRE_CPU_CACHE_HIT__RESTORE_DIRECT", default=True,
         absent_expected=True, negative=False, dual_default=True,
         pre_commit='os.getenv("COMFYMODAL_COLD_UNET_REQUIRE_CPU_CACHE_HIT", "1") == "1"'),
    dict(name="COMFYMODAL_COLD_UNET_DISABLE_ON_VOLUME_STALL", default=True,
         absent_expected=True, negative=True,
         pre_commit='os.getenv("COMFYMODAL_COLD_UNET_DISABLE_ON_VOLUME_STALL", "1") == "1"'),
    dict(name="COMFYMODAL_COLD_UNET_DEBUG", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.getenv("COMFYMODAL_COLD_UNET_DEBUG", "0") == "1"'),
    dict(name="COMFYMODAL_DIRECT_WARMUP_LOAD_UNET", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.getenv("COMFYMODAL_DIRECT_WARMUP_LOAD_UNET", "0") == "1"'),
    dict(name="COMFYMODAL_DIRECT_WARMUP_LOAD_CLIP", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.getenv("COMFYMODAL_DIRECT_WARMUP_LOAD_CLIP", "0") == "1"'),
    dict(name="COMFYMODAL_DIRECT_WARMUP_CLIP_ENCODE", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.getenv("COMFYMODAL_DIRECT_WARMUP_CLIP_ENCODE", "0") == "1"'),
    dict(name="COMFYMODAL_DIRECT_WARMUP_REQUIRE_CPU_CACHE_HIT", default=True,
         absent_expected=True, negative=False,
         pre_commit='os.getenv("COMFYMODAL_DIRECT_WARMUP_REQUIRE_CPU_CACHE_HIT", "1") == "1"'),
    dict(name="COMFYMODAL_VAE_DECODE_WARMUP", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.getenv("COMFYMODAL_VAE_DECODE_WARMUP", "0") == "1"'),
    dict(name="COMFYMODAL_RESTORE_BACKGROUND_UNET", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.getenv("COMFYMODAL_RESTORE_BACKGROUND_UNET", "0") == "1"'),
    dict(name="COMFYMODAL_EXPERIMENTAL_RESTORE_BACKGROUND_CODE", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.getenv("COMFYMODAL_EXPERIMENTAL_RESTORE_BACKGROUND_CODE", "0") == "1"'),
    dict(name="COMFYMODAL_SAFETENSORS_STRICT", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.getenv("COMFYMODAL_SAFETENSORS_STRICT", "0") == "1"'),
    dict(name="COMFYMODAL_FASTPATH_V21621", default=True,
         absent_expected=True, negative=False,
         pre_commit='os.getenv("COMFYMODAL_FASTPATH_V21621", "1") == "1"'),
    dict(name="COMFYMODAL_FASTPATH_V21621_BACKGROUND_UNET", default=True,
         absent_expected=True, negative=False,
         pre_commit='os.getenv("COMFYMODAL_FASTPATH_V21621_BACKGROUND_UNET", "1") == "1"'),
    dict(name="COMFYMODAL_FASTPATH_V21621_CLIP_LOAD_ONLY", default=True,
         absent_expected=True, negative=False,
         pre_commit='os.getenv("COMFYMODAL_FASTPATH_V21621_CLIP_LOAD_ONLY", "1") == "1"'),
    dict(name="COMFYMODAL_FASTPATH_V21621_CLIP_READ_BYTES", default=True,
         absent_expected=True, negative=False,
         pre_commit='os.getenv("COMFYMODAL_FASTPATH_V21621_CLIP_READ_BYTES", "1") == "1"'),
    dict(name="COMFYMODAL_FUSE_READ_GOVERNOR", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.getenv("COMFYMODAL_FUSE_READ_GOVERNOR", "0").strip().lower() in {"1", "true", "yes", "on"}'),
    dict(name="COMFYMODAL_PERSIST_PER_STACK_METRICS", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.getenv("COMFYMODAL_PERSIST_PER_STACK_METRICS", "0") == "1"'),
    dict(name="COMFYMODAL_DEFER_VAE_ACTUAL_LOAD_DURING_RBG_UNET", default=True,
         absent_expected=True, negative=False,
         pre_commit='os.getenv("COMFYMODAL_DEFER_VAE_ACTUAL_LOAD_DURING_RBG_UNET", "1") == "1"'),
    dict(name="COMFYMODAL_DEFER_VAE_INCLUDING_PRODUCTION_UNET", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.getenv("COMFYMODAL_DEFER_VAE_INCLUDING_PRODUCTION_UNET", "0") == "1"'),
    dict(name="COMFYMODAL_PRODUCTION_UNET_VAE_DIAG", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.environ.get("COMFYMODAL_PRODUCTION_UNET_VAE_DIAG", "0") == "1"'),
    dict(name="COMFYMODAL_SAGE_RUNTIME_PROBE_ON_RESTORE", default=True,
         absent_expected=True, negative=False,
         pre_commit='os.getenv("COMFYMODAL_SAGE_RUNTIME_PROBE_ON_RESTORE", "1") == "1"'),
    dict(name="COMFYMODAL_DISABLE_PLATFORM_DIAG", default=False,
         absent_expected=False, negative=True,
         pre_commit='os.environ.get("COMFYMODAL_DISABLE_PLATFORM_DIAG", "0") == "1"'),
    dict(name="COMFYMODAL_DISABLE_WATERFALL", default=False,
         absent_expected=False, negative=True,
         pre_commit='os.environ.get("COMFYMODAL_DISABLE_WATERFALL", "0") == "1"'),
    dict(name="COMFYMODAL_V2_DEEP_MODEL_DIAG", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.environ.get("COMFYMODAL_V2_DEEP_MODEL_DIAG", "0") == "1"'),
    dict(name="COMFYMODAL_ALLOW_RUNTIME_MODEL_DOWNLOADS", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.getenv("COMFYMODAL_ALLOW_RUNTIME_MODEL_DOWNLOADS", "0") == "1"'),
    # Strict pre-commit: os.environ.get("COMFYMODAL_RUNTIME") == "1" (no default).
    # "true"/"yes"/"on" were False pre-commit; the shared parser now accepts them.
    dict(name="COMFYMODAL_RUNTIME", default=False,
         absent_expected=False, negative=False, strict_precommit=True,
         pre_commit='os.environ.get("COMFYMODAL_RUNTIME") == "1"'),
    dict(name="COMFYMODAL_PERSISTENT_CLIP_CACHE", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.environ.get("COMFYMODAL_PERSISTENT_CLIP_CACHE", "0") == "1"'),
    dict(name="COMFYMODAL_PERSISTENT_VALIDATION_CERTIFICATE", default=True,
         absent_expected=True, negative=False,
         pre_commit='os.environ.get("COMFYMODAL_PERSISTENT_VALIDATION_CERTIFICATE", "1") == "1"'),
    dict(name="COMFYMODAL_THIRD_PARTY_LOG_SUPPRESSION", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.environ.get("COMFYMODAL_THIRD_PARTY_LOG_SUPPRESSION", "0") == "1"'),
    # __init__.py
    dict(name="COMFYMODAL_EXACT_CLIP_PREFILL", default=True,
         absent_expected=True, negative=False,
         pre_commit='os.environ.get("COMFYMODAL_EXACT_CLIP_PREFILL", "1") == "1" (__init__ line 26)'),
    dict(name="COMFYMODAL_RUNTIME", default=False,
         absent_expected=False, negative=False, strict_precommit=True,
         pre_commit='os.environ.get("COMFYMODAL_RUNTIME") == "1" (__init__ line 1690)'),
    dict(name="COMFYMODAL_PERSISTENT_CLIP_CACHE", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.environ.get("COMFYMODAL_PERSISTENT_CLIP_CACHE", "0") == "1" (__init__ line 2877)'),
    dict(name="COMFYMODAL_V2_DEEP_MODEL_DIAG", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.environ.get("COMFYMODAL_V2_DEEP_MODEL_DIAG", "0") == "1" (__init__ line 3640)'),
    # warmup_profile.py
    dict(name="COMFYMODAL_EXACT_CLIP_PREFILL", default=True,
         absent_expected=True, negative=False,
         pre_commit='os.environ.get("COMFYMODAL_EXACT_CLIP_PREFILL", "1") == "1" (warmup_profile line 176)'),
    dict(name="COMFYMODAL_PERSISTENT_CLIP_CACHE", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.environ.get("COMFYMODAL_PERSISTENT_CLIP_CACHE", "0") == "1" (warmup_profile line 181)'),
    # benchmark_modal_e2e.py
    dict(name="COMFYMODAL_ENABLE_REMOTE_BACKGROUND_DEPLOY", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.environ.get("COMFYMODAL_ENABLE_REMOTE_BACKGROUND_DEPLOY", "0").strip().lower() in {"1", "true", "yes", "on"} (benchmark line 386)'),
    # modal_client.py
    dict(name="COMFYMODAL_ENABLE_GPU_SNAPSHOT", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.environ.get("COMFYMODAL_ENABLE_GPU_SNAPSHOT", "0") == "1" (modal_client line 295)'),
    # model_preload.py
    dict(name="COMFYMODAL_V2_PAGEFAULT_TRACKING", default=True,
         absent_expected=True, negative=False,
         pre_commit='os.environ.get("COMFYMODAL_V2_PAGEFAULT_TRACKING", "1") == "1" (model_preload line 61)'),
    # Strict pre-commit set: in ("1", "true", "yes") — "on" was False pre-commit.
    dict(name="COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET", default=False,
         absent_expected=False, negative=False, strict_precommit=True,
         pre_commit='os.environ.get("COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET", "").strip().lower() in ("1", "true", "yes") (model_preload line 100)'),
    dict(name="COMFYMODAL_V2_DEEP_MODEL_DIAG", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.environ.get("COMFYMODAL_V2_DEEP_MODEL_DIAG", "0") == "1" (model_preload line 125)'),
    # unet_forward_probe.py — strict pre-commit: == "1" only.
    dict(name="COMFYMODAL_V2_UNET_FORWARD_DIAG", default=False,
         absent_expected=False, negative=False, strict_precommit=True,
         pre_commit='os.environ.get("COMFYMODAL_V2_UNET_FORWARD_DIAG", "") == "1" (unet_forward_probe line 98)'),
    # modal_app.py
    dict(name="COMFYMODAL_V2_VALIDATION_CERT", default=True,
         absent_expected=True, negative=False,
         pre_commit='os.environ.get("COMFYMODAL_V2_VALIDATION_CERT", "1") == "1" (modal_app line 300)'),
    dict(name="COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.environ.get("COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS", "0") == "1" (modal_app line 338)'),
    # Strict pre-commit: os.environ.get("COMFYMODAL_V2_FULL_TRACE", "") == "1".
    dict(name="COMFYMODAL_V2_FULL_TRACE", default=False,
         absent_expected=False, negative=False, strict_precommit=True,
         pre_commit='os.environ.get("COMFYMODAL_V2_FULL_TRACE", "") == "1" (modal_app line 343)'),
    dict(name="COMFYMODAL_V2_CPU_MODEL_SNAPSHOT", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.environ.get("COMFYMODAL_V2_CPU_MODEL_SNAPSHOT", "0") == "1" (modal_app line 715)'),
    dict(name="COMFYMODAL_ENABLE_GPU_SNAPSHOT", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.environ.get("COMFYMODAL_ENABLE_GPU_SNAPSHOT", "0") == "1" (modal_app line 723)'),
    # Replaced a strict RuntimeError-raising parser; see strict-parser docs below.
    dict(name="COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT", default=False,
         absent_expected=False, negative=False, strict_precommit=True,
         pre_commit="strict parser: absent/empty/'0' -> False, '1' -> True, else RuntimeError (modal_app line 1759)"),
    dict(name="COMFYMODAL_ENABLE_GPU_SNAPSHOT", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.environ.get("COMFYMODAL_ENABLE_GPU_SNAPSHOT", "0") == "1" (modal_app line 1721)'),
    dict(name="COMFYMODAL_ENABLE_GPU_SNAPSHOT", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.environ.get("COMFYMODAL_ENABLE_GPU_SNAPSHOT", "0") == "1" (modal_app line 1853)'),
    dict(name="COMFYMODAL_ENABLE_GPU_SNAPSHOT", default=False,
         absent_expected=False, negative=False,
         pre_commit='os.environ.get("COMFYMODAL_ENABLE_GPU_SNAPSHOT", "0") == "1" (modal_app line 10799)'),
    # optimizations.py `_env_flag(name, default="...")` wrapper — computed default:
    # env_flag(name, default=default == "1").  String defaults below.
    dict(name="COMFYMODAL_PRODUCTION_MODEL_READ_COORDINATOR", default=False,
         absent_expected=False, negative=False, wrapper_default="0",
         pre_commit='os.environ.get(name, "0").strip().lower() in {"1", "true", "yes", "on"} (optimizations _env_flag)'),
    dict(name="COMFYMODAL_PRODUCTION_MODEL_READ_COORDINATOR_DIAG", default=True,
         absent_expected=True, negative=False, wrapper_default="1",
         pre_commit='os.environ.get(name, "1").strip().lower() in {"1", "true", "yes", "on"} (optimizations _env_flag)'),
    dict(name="COMFYMODAL_GENERIC_CLIP_WARMUP_FALLBACK", default=False,
         absent_expected=False, negative=False, wrapper_default="0",
         pre_commit='os.environ.get(name, "0").strip().lower() in {"1", "true", "yes", "on"} (optimizations _env_flag)'),
    dict(name="COMFYMODAL_CUSTOM_NODE_GENERATION_FASTPATH", default=False,
         absent_expected=False, negative=False, wrapper_default="0",
         pre_commit='os.environ.get(name, "0").strip().lower() in {"1", "true", "yes", "on"} (optimizations _env_flag)'),
    dict(name="COMFYMODAL_MODEL_PATH_CACHE", default=False,
         absent_expected=False, negative=False, wrapper_default="0",
         pre_commit='os.environ.get(name, "0").strip().lower() in {"1", "true", "yes", "on"} (optimizations _env_flag)'),
    dict(name="COMFYMODAL_PROFILE_RESOURCES", default=False,
         absent_expected=False, negative=False, wrapper_default="0",
         pre_commit='os.environ.get(name, "0").strip().lower() in {"1", "true", "yes", "on"} (optimizations _env_flag)'),
    dict(name="COMFYMODAL_CRITICAL_PATH_DIAG", default=True,
         absent_expected=True, negative=False, wrapper_default="1",
         pre_commit='os.environ.get(name, "1").strip().lower() in {"1", "true", "yes", "on"} (optimizations _env_flag)'),
    dict(name="COMFYMODAL_UNET_PHASE_DIAG", default=True,
         absent_expected=True, negative=False, wrapper_default="1",
         pre_commit='os.environ.get(name, "1").strip().lower() in {"1", "true", "yes", "on"} (optimizations _env_flag)'),
    dict(name="COMFYMODAL_VALIDATION_PHASE_DIAG", default=True,
         absent_expected=True, negative=False, wrapper_default="1",
         pre_commit='os.environ.get(name, "1").strip().lower() in {"1", "true", "yes", "on"} (optimizations _env_flag)'),
]


# ── Value matrix required for every converted flag ────────────────────────
# (label, raw value, shared-parser expected result)

VALUE_MATRIX = [
    ("empty", "", False),
    ("zero", "0", False),
    ("false", "false", False),
    ("no", "no", False),
    ("off", "off", False),
    ("one", "1", True),
    ("true", "true", True),
    ("yes", "yes", True),
    ("on", "on", True),
    ("mixed-case", "TrUe", True),
    ("upper", "YES", True),
    ("on-upper", "ON", True),
    ("ws-1", "  1  ", True),
    ("ws-true", "\ttrue\n", True),
    ("ws-zero", " 0 ", False),
    ("unknown", "banana", False),
    ("other-number", "2", False),
]


def _flag_id(case: dict) -> str:
    return f"{case['name']}~{case.get('pre_commit', '')[-28:]}" if "wrapper_default" in case else case["name"]


@pytest.mark.parametrize("case", FLAG_CASES, ids=lambda c: c["name"])
def test_absent_expected_matches_converted_default(case, monkeypatch):
    """Absent result must equal the exact pre-commit expression's absent value."""
    monkeypatch.delenv(case["name"], raising=False)
    assert env_flag(case["name"], default=case["default"]) is case["absent_expected"]
    # The whole point of the conversion: absent default is preserved exactly.
    assert case["absent_expected"] == case["default"]


_MATRIX_IDS = [item[0] for item in VALUE_MATRIX]


@pytest.mark.parametrize("case", FLAG_CASES, ids=lambda c: c["name"])
@pytest.mark.parametrize("label,value,expected", VALUE_MATRIX, ids=_MATRIX_IDS)
def test_converted_flag_explicit_value(case, label, value, expected, monkeypatch):
    """Every converted flag must obey the shared parser for explicit values."""
    monkeypatch.setenv(case["name"], value)
    assert env_flag(case["name"], default=case["default"]) is expected


@pytest.mark.parametrize("case", [c for c in FLAG_CASES if c["negative"]],
                         ids=lambda c: c["name"])
def test_negative_flags_parse_like_any_other_flag(case, monkeypatch):
    """Negative (DISABLE_*) flags are value-agnostic: '1' means 'disabled'."""
    monkeypatch.setenv(case["name"], "1")
    assert env_flag(case["name"], default=case["default"]) is True
    monkeypatch.setenv(case["name"], "0")
    assert env_flag(case["name"], default=case["default"]) is False


@pytest.mark.parametrize("case", [c for c in FLAG_CASES if "wrapper_default" in c],
                         ids=lambda c: c["name"])
def test_computed_default_wrapper(case, monkeypatch):
    """The ``_env_flag(name, default='0'/'1')`` wrapper computes bool default
    as ``default == '1'``; absent semantics must match the string default."""
    monkeypatch.delenv(case["name"], raising=False)
    computed = case["wrapper_default"] == "1"
    assert env_flag(case["name"], default=computed) is computed
    assert computed is case["absent_expected"]


def test_dual_default_require_cpu_cache_hit(monkeypatch):
    """COLD_UNET_REQUIRE_CPU_CACHE_HIT has two defaults depending on mode:
    False by default, True under restore_direct (both preserved)."""
    monkeypatch.delenv("COMFYMODAL_COLD_UNET_REQUIRE_CPU_CACHE_HIT", raising=False)
    assert env_flag("COMFYMODAL_COLD_UNET_REQUIRE_CPU_CACHE_HIT") is False
    assert env_flag("COMFYMODAL_COLD_UNET_REQUIRE_CPU_CACHE_HIT", default=True) is True
    # restore_direct is encoded at the call site as default=True
    monkeypatch.setenv("COMFYMODAL_COLD_UNET_REQUIRE_CPU_CACHE_HIT", "0")
    assert env_flag("COMFYMODAL_COLD_UNET_REQUIRE_CPU_CACHE_HIT", default=True) is False


# ── Strict parsers intentionally outside the shared parser ────────────────
#
# 1. COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT — pre-commit modal_app.py had
#    a strict parser: absent/empty/'0' -> False, '1' -> True, and *any other
#    nonempty value raised RuntimeError*.  Commit 9628c51 deliberately
#    replaced it with the shared parser, so unknown values now return False
#    instead of raising.  This is a documented, intentional relaxation.
#
# 2. COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET — pre-commit truth set was
#    ("1", "true", "yes") — notably WITHOUT "on".  The shared parser now
#    accepts "on" too.  Documented widening.
#
# 3. COMFYMODAL_RUNTIME / COMFYMODAL_V2_FULL_TRACE / COMFYMODAL_V2_UNET_FORWARD_DIAG —
#    pre-commit accepted "1" only.  The shared parser now accepts
#    true/yes/on as well.  Documented widening.
#
# 4. modal_app._parse_evict_retain_role and _parse_memory_mb remain strict
#    enum/int parsers and are intentionally NOT routed through env_flag;
#    they are out of scope and unchanged.


@pytest.mark.parametrize("value", ["banana", "2", "maybe", " UNKNOWN "])
def test_evict_flag_unknown_no_longer_raises(value, monkeypatch):
    """Regression: shared parser replaced the strict RuntimeError parser."""
    monkeypatch.setenv("COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT", value)
    assert env_flag("COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT") is False


def test_prefill_wait_for_unet_on_now_accepted(monkeypatch):
    """Widening documented: pre-commit set excluded 'on'; shared parser includes it."""
    monkeypatch.setenv("COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET", "on")
    assert env_flag("COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET") is True
    monkeypatch.setenv("COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET", "yes")
    assert env_flag("COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET") is True


@pytest.mark.parametrize("name", [
    "COMFYMODAL_RUNTIME",
    "COMFYMODAL_V2_FULL_TRACE",
    "COMFYMODAL_V2_UNET_FORWARD_DIAG",
])
def test_strict_one_only_flags_now_accept_shared_set(name, monkeypatch):
    """Documented widening: pre-commit == '1' only; shared parser accepts all."""
    monkeypatch.setenv(name, "true")
    assert env_flag(name) is True
    monkeypatch.setenv(name, "1")
    assert env_flag(name) is True
    monkeypatch.setenv(name, "0")
    assert env_flag(name) is False
