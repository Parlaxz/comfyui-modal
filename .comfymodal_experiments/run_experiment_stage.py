"""Run a single experiment stage: apply preset, then launch the deploy batch.

Usage:
    python run_experiment_stage.py <preset_name>
    python run_experiment_stage.py --list
    python run_experiment_stage.py --current
    python run_experiment_stage.py --diagnose-context
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

# ── Paths ───────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
PRESETS_PATH = BASE_DIR / "comfymodal_experiment_presets.json"
STATE_PATH = BASE_DIR / "comfymodal_experiment_state.json"
DEPLOY_BATCH = Path(
    r"C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install"
    r"\redeploy_modal_and_run_comfyui.bat"
)


def _log(msg: str) -> None:
    print(f"[run-experiment] {msg}")


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
    return {}


def list_presets() -> None:
    data = _load_presets()
    default = data.get("default_preset", "")
    _log(f"Available presets (default: {default}):")
    for name in sorted(data.get("presets", {})):
        desc = data["presets"][name].get("description", "")
        _log(f"  {name}")
        if desc:
            _log(f"    {desc}")


def show_current() -> None:
    state = _load_state()
    preset = state.get("current_preset", "none")
    applied = state.get("last_applied_at", None)
    if applied:
        applied_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(applied))
    else:
        applied_str = "never"
    _log(f"current_preset={preset}")
    _log(f"last_applied_at={applied_str}")

    if preset and preset != "none":
        data = _load_presets()
        preset_data = data.get("presets", {}).get(preset, {})
        expected = preset_data.get("expected_logs", [])
        if expected:
            _log(f"expected_logs for {preset}:")
            for line in expected:
                _log(f"  {line}")


def run_stage(preset_name: str) -> None:
    data = _load_presets()
    presets = data.get("presets", {})

    if preset_name not in presets:
        _log(f"ERROR: unknown preset: {preset_name!r}")
        _log(f"  Use --list to see available presets.")
        sys.exit(1)

    preset = presets[preset_name]
    expected = preset.get("expected_logs", [])

    # Step 1: Apply the preset
    _log(f"Applying preset: {preset_name}")
    apply_script = Path(__file__).parent / "apply_experiment_preset.py"
    if not apply_script.is_file():
        _log(f"ERROR: apply script not found: {apply_script}")
        sys.exit(1)

    result = subprocess.run(
        [sys.executable, str(apply_script), preset_name],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        _log(f"ERROR: apply_experiment_preset.py failed:")
        print(result.stderr)
        sys.exit(1)

    for line in result.stdout.strip().splitlines():
        print(f"  {line}")
    if result.stderr.strip():
        _log("stderr:")
        for line in result.stderr.strip().splitlines():
            print(f"  {line}")

    _log(f"Preset {preset_name} applied successfully.")

    # Step 2: Launch the deploy batch
    _log(f"Launching deploy batch: {DEPLOY_BATCH}")
    if not DEPLOY_BATCH.is_file():
        _log(f"ERROR: batch file not found: {DEPLOY_BATCH}")
        sys.exit(1)

    try:
        subprocess.Popen(
            ["cmd.exe", "/c", "start", "", str(DEPLOY_BATCH)],
            shell=False,
        )
        _log("Batch launched in a separate window.")
        _log("Wait for the window to open and ComfyUI to load.")
    except Exception as exc:
        _log(f"WARNING: could not launch batch in new window: {exc}")
        _log("Please launch manually:")
        _log(f"  {DEPLOY_BATCH}")

    # Step 3: Print ready message
    _print_ready(preset_name, expected)


def _print_ready(preset_name: str, expected_logs: list[str]) -> None:
    print()
    print("=" * 70)
    _log(f"READY: preset={preset_name}")
    print()
    print("  1 warm/cache/profile run, then 3 measured runs.")
    print("  Paste the logs/results when done.")
    print()
    if expected_logs:
        _log("Expected log signatures to verify:")
        for line in expected_logs:
            print(f"    {line}")
    print("=" * 70)


def diagnose_context() -> None:
    """Print diagnostic info about harness file placement and ignore coverage.

    Does not apply flags, does not deploy, does not run generations.
    """
    _log("=== Harness Context Diagnostics ===")
    _log(f"preset_dir={BASE_DIR}")
    _log(f"state_file_path={STATE_PATH}")
    _log(f"state_under_experiments_dir={STATE_PATH.parent.resolve() == BASE_DIR.resolve()}")
    _log(f"state_file_exists={STATE_PATH.is_file()}")
    _log(f"presets_file_exists={PRESETS_PATH.is_file()}")

    comfyui_modal_root = BASE_DIR.parent
    legacy_files = {
        "comfymodal_experiment_presets.json": comfyui_modal_root / "comfymodal_experiment_presets.json",
        "comfymodal_experiment_state.json": comfyui_modal_root / "comfymodal_experiment_state.json",
        "apply_experiment_preset.py": comfyui_modal_root / "apply_experiment_preset.py",
        "run_experiment_stage.py": comfyui_modal_root / "run_experiment_stage.py",
    }
    legacy_present = [name for name, p in legacy_files.items() if p.is_file()]
    if legacy_present:
        _log("WARNING: legacy harness files still present beside comfyapp.py:")
        for name in legacy_present:
            _log(f"  {name}")
    else:
        _log("legacy_direct_files_present=none (clean)")

    deploy_exists = DEPLOY_BATCH.is_file()
    _log(f"deploy_batch_exists={deploy_exists}")
    if deploy_exists:
        deploy_mtime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(DEPLOY_BATCH.stat().st_mtime))
        _log(f"deploy_batch_modified_by_tool=expected_no (mtime={deploy_mtime})")

    _log("ignore pattern coverage:")
    _log("  _COMFYUI_MODAL_IMAGE_IGNORE_PATTERNS should include .comfymodal_experiments/ and all harness filenames")
    _log("  _COMBINED_CUSTOM_NODE_IGNORE_PATTERNS should include comfyui-modal/.comfymodal_experiments/ and all prefixed harness filenames")
    _log("  per-node ignore (comfyui-modal extends _COMFYUI_MODAL_IMAGE_IGNORE_PATTERNS)")

    state = _load_state()
    current = state.get("current_preset", "none") if state else "none"
    _log(f"current_preset={current}")
    _log("=== Diagnostics complete ===")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    if sys.argv[1] == "--list":
        list_presets()
        return

    if sys.argv[1] == "--current":
        show_current()
        return

    if sys.argv[1] == "--diagnose-context":
        diagnose_context()
        return

    preset_name = sys.argv[1]
    run_stage(preset_name)


if __name__ == "__main__":
    main()
