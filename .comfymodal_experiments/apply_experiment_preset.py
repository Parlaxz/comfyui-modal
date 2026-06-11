"""Apply an experiment preset to Modal runtime flags.

Usage:
    python apply_experiment_preset.py <preset_name>
    python apply_experiment_preset.py --list
"""

import json
import os
import sys
import time
from pathlib import Path

# ── Paths ───────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
PRESETS_PATH = BASE_DIR / "comfymodal_experiment_presets.json"
STATE_PATH = BASE_DIR / "comfymodal_experiment_state.json"

# Allowed runtime flag names (no COMFYMODAL_ prefix; set_runtime_flag handles
# the flag name as-is, _resolve_runtime_flag prepends COMFYMODAL_ for env var).
_ALLOWED_FLAGS = frozenset({
    "EXPERIMENTAL_RESTORE_BACKGROUND_CODE",
    "RESTORE_BACKGROUND_UNET",
    "RESTORE_DIRECT_CLIP_POLICY",
    "DISABLE_RESTORE_WARMUP_FOR_Z_IMAGE",
    "FUSE_READ_GOVERNOR",
})

# Flags whose values must be "0" or "1".
_BOOL_FLAGS = frozenset({
    "EXPERIMENTAL_RESTORE_BACKGROUND_CODE",
    "RESTORE_BACKGROUND_UNET",
    "DISABLE_RESTORE_WARMUP_FOR_Z_IMAGE",
    "FUSE_READ_GOVERNOR",
})

# Flags with specific string values.
_STRING_FLAG_ALLOWED_VALUES = {
    "RESTORE_DIRECT_CLIP_POLICY": frozenset({"auto", "off", "load_only", "load_and_encode"}),
}


def _log(msg: str) -> None:
    print(f"[comfymodal-preset] {msg}")


def _load_presets() -> dict:
    if not PRESETS_PATH.is_file():
        _log(f"ERROR: presets file not found: {PRESETS_PATH}")
        sys.exit(1)
    try:
        data = json.loads(PRESETS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _log(f"ERROR: invalid presets JSON: {exc}")
        sys.exit(1)
    if not isinstance(data, dict) or "presets" not in data:
        _log("ERROR: presets file missing 'presets' key")
        sys.exit(1)
    return data


def _load_state() -> dict:
    if STATE_PATH.is_file():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"schema_version": 1, "current_preset": None, "last_applied_at": None, "last_apply_result": None}


def _save_state(state: dict) -> None:
    STATE_PATH.write_text(
        json.dumps(state, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def list_presets() -> None:
    data = _load_presets()
    presets = data.get("presets", {})
    default = data.get("default_preset", "")
    _log(f"Available presets (default: {default}):")
    for name in sorted(presets):
        desc = presets[name].get("description", "")
        flags = presets[name].get("runtime_flags", {})
        flag_str = " ".join(f"{k}={v}" for k, v in flags.items())
        _log(f"  {name}")
        if desc:
            _log(f"    description: {desc}")
        if flag_str:
            _log(f"    flags: {flag_str}")


def apply_preset(preset_name: str) -> None:
    data = _load_presets()
    presets = data.get("presets", {})

    if preset_name not in presets:
        _log(f"ERROR: unknown preset: {preset_name!r}")
        _log(f"  Use --list to see available presets.")
        sys.exit(1)

    preset = presets[preset_name]
    flags = preset.get("runtime_flags", {})
    invalid_flags = [k for k in flags if k not in _ALLOWED_FLAGS]
    if invalid_flags:
        _log(f"ERROR: invalid runtime flag(s) in preset {preset_name!r}: {invalid_flags}")
        sys.exit(1)

    # Validate each flag's value
    invalid_values = []
    for key, value in flags.items():
        if key in _BOOL_FLAGS:
            if value not in ("0", "1"):
                invalid_values.append(f"{key}={value!r} (must be '0' or '1')")
        elif key in _STRING_FLAG_ALLOWED_VALUES:
            allowed = _STRING_FLAG_ALLOWED_VALUES[key]
            if value not in allowed:
                invalid_values.append(f"{key}={value!r} (must be one of {sorted(allowed)})")
        else:
            invalid_values.append(f"{key} (unknown flag type for validation)")
    if invalid_values:
        _log(f"ERROR: invalid value(s) in preset {preset_name!r}:")
        for iv in invalid_values:
            _log(f"  {iv}")
        sys.exit(1)

    # Apply each flag via modal.Function.from_name
    _log(f"preset={preset_name}")
    try:
        import modal
    except ImportError:
        _log("ERROR: modal package not installed")
        sys.exit(1)

    for name, value in sorted(flags.items()):
        try:
            fn = modal.Function.from_name("comfyui", "set_runtime_flag")
            result = fn.remote(name, value)
            _log(f"{name}={value} -> {result}")
        except Exception as exc:
            _log(f"ERROR: failed to set {name}={value}: {exc}")
            sys.exit(1)

    # Update state
    state = _load_state()
    state["current_preset"] = preset_name
    state["last_applied_at"] = time.time()
    state["last_apply_result"] = "ok"
    _save_state(state)
    _log(f"state updated: {STATE_PATH.name}")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    if sys.argv[1] == "--list":
        list_presets()
        return

    preset_name = sys.argv[1]
    apply_preset(preset_name)


if __name__ == "__main__":
    main()
