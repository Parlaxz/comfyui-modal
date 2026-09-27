"""Read-only Modal storage map and volume-generation identification helper.

Inspects the local comfyui-modal repo: reads the state JSON files
(.modal_settings.json / .deployed_state.json / .model_manifest.json /
.modal_workspaces.json) and regex-extracts the volume/path constants from the
V1 (comfyapp.py) and V2 (comfymodal_runtime/modal_app.py) runtimes (modules are
never imported), then prints a storage map, the model-weights manifest summary,
and local loader/modal metadata.

Guarantee: this script mutates NOTHING.  It never creates a volume
(create_if_missing is never passed as True), never commits / reloads / deletes
/ deploys, and never writes to disk.  The default mode performs NO network
access at all.  ``--probe`` (opt-in) makes READ-ONLY Modal API calls to detect
the generation of the model/custom-nodes/runtime-state volumes and must only be
run by the execution owner (C9) in an allowed window.

Usage:
  python tools/inspect_modal_model_storage.py                 # local only, no network
  python tools/inspect_modal_model_storage.py --json          # same, as JSON
  python tools/inspect_modal_model_storage.py --probe         # READ-ONLY Modal API calls
  python tools/inspect_modal_model_storage.py --probe --volumes comfyui-models,comfyui-custom-nodes
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
PARENT_COMFY_UTILS = REPO_ROOT.parent.parent / "comfy" / "utils.py"

MODAL_SETTINGS = REPO_ROOT / ".modal_settings.json"
DEPLOYED_STATE = REPO_ROOT / ".deployed_state.json"
MODEL_MANIFEST = REPO_ROOT / ".model_manifest.json"
MODAL_WORKSPACES = REPO_ROOT / ".modal_workspaces.json"
COMFYAPP = REPO_ROOT / "comfyapp.py"
MODAL_APP = REPO_ROOT / "comfymodal_runtime" / "modal_app.py"

# Spec-defined constant sets; only these are reported in the CONSTANTS section.
_V1_KNOWN = {
    "VOLUME_NAME",
    "MODELS_PATH",
    "CUSTOM_NODES_VOLUME_NAME",
    "RUNTIME_CONFIG_VOLUME_NAME",
    "PROMPT_CACHE_VOLUME_NAME",
    "RUNTIME_CONFIG_PATH",
}
_V2_KNOWN = {
    "MODELS_VOLUME_NAME",
    "MODELS_PATH",
    "CUSTOM_NODES_VOLUME_NAME",
    "RUNTIME_STATE_VOLUME_NAME",
    "RUNTIME_STATE_PATH",
    "PROFILE_VOLUME_NAME",
    "PROMPT_CACHE_VOLUME_NAME",
}
# Supplementary mount-path constants extracted with the same scanner; they feed
# the mount-path column of the STORAGE MAP only.
_SUPPLEMENTARY_PATHS = {"CUSTOM_NODES_PATH", "PROMPT_CACHE_VOLUME_PATH", "PROFILE_PATH"}

_LITERAL_RE = re.compile(r'^\s*([A-Z_]+)\s*=\s*"([^"]+)"')
_ENV_DEFAULT_RE = re.compile(
    r'^\s*([A-Z_]+)\s*=\s*os\.environ\.get\(\s*"[^"]+"\s*,\s*"([^"]+)"'
)
_MODELS_PATH_RE = re.compile(r"^\s*MODELS_PATH\s*=\s*[^#\n]+")
_GPU_SNAPSHOT_RE = re.compile(
    r'^\s*[A-Z_]+\s*=\s*env_flag\(\s*"COMFYMODAL_ENABLE_GPU_SNAPSHOT"'
    r"\s*(?:,\s*default\s*=\s*(\w+)\s*)?\)"
)

_ROLE_INFO = [
    (
        "models",
        "model weights (diffusion models / text encoders / VAE / clip / loras / controlnet / model patches)",
        {"v1_name": "VOLUME_NAME", "v2_name": "MODELS_VOLUME_NAME",
         "v1_path": "MODELS_PATH", "v2_path": "MODELS_PATH"},
    ),
    (
        "custom-nodes",
        "custom-node source and dependency cache",
        {"v1_name": "CUSTOM_NODES_VOLUME_NAME", "v2_name": "CUSTOM_NODES_VOLUME_NAME",
         "v1_path": "CUSTOM_NODES_PATH", "v2_path": "CUSTOM_NODES_PATH"},
    ),
    (
        "runtime-state",
        "runtime config / restore-state volume",
        {"v1_name": "RUNTIME_CONFIG_VOLUME_NAME", "v2_name": "RUNTIME_STATE_VOLUME_NAME",
         "v1_path": "RUNTIME_CONFIG_PATH", "v2_path": "RUNTIME_STATE_PATH"},
    ),
    (
        "profiles",
        "V2 warmup / production profile data",
        {"v1_name": None, "v2_name": "PROFILE_VOLUME_NAME",
         "v1_path": None, "v2_path": "PROFILE_PATH"},
    ),
    (
        "prompt-cache",
        "prompt-encoding (CLIP) cache",
        {"v1_name": "PROMPT_CACHE_VOLUME_NAME", "v2_name": "PROMPT_CACHE_VOLUME_NAME",
         "v1_path": "PROMPT_CACHE_VOLUME_PATH", "v2_path": "PROMPT_CACHE_VOLUME_PATH"},
    ),
]

READ_ONLY_CHECKS = (
    "The snippets below identify the deployed volume generation. They are printed\n"
    "for reference and are NOT executed by this script. Both make READ-ONLY Modal\n"
    "API calls and must only be run by the execution owner (C9) in an allowed window.\n"
    "\n"
    "```\n"
    "# 1) CLI listing (read-only; note: no version column, even with --json)\n"
    "modal volume list\n"
    "\n"
    "# 2) SDK version-pin probe (read-only)\n"
    'vol = modal.Volume.from_name("comfyui-models", create_if_missing=False, version=1)\n'
    "vol.hydrate()\n"
    '# An InvalidError whose message contains "exists but has version v2" proves v2;\n'
    "# success implies v1. Private fallback after hydration: vol._metadata.version\n"
    "```\n"
)


def _read_json(path: Path) -> tuple[object | None, str | None]:
    """Return (parsed JSON, None) or (None, error) when unreadable.  Never fetches."""
    if not path.is_file():
        return None, "file missing"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except Exception as exc:  # noqa: BLE001
        return None, f"unparseable JSON: {exc}"


def extract_constants() -> dict:
    """Regex-extract the known constants from comfyapp.py and modal_app.py.

    Returns per-file records keyed by relative path: {"present", "hits",
    "values", "gpu_snapshot"}.  ``hits`` is [(name, line_no, value)] in file
    order; ``values`` maps name -> (line_no, value).  Modules are never imported.
    """
    results: dict = {}
    for rel, path, known in (
        ("comfyapp.py", COMFYAPP, _V1_KNOWN),
        ("comfymodal_runtime/modal_app.py", MODAL_APP, _V2_KNOWN),
    ):
        if not path.is_file():
            results[rel] = {"present": False, "hits": [], "values": {}, "gpu_snapshot": []}
            continue
        hits: list[tuple[str, int, str]] = []
        values: dict[str, tuple[int, str]] = {}
        gpu_snapshot: list[dict] = []
        wanted = known | _SUPPLEMENTARY_PATHS
        for line_no, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            m = _LITERAL_RE.match(line)
            if m and m.group(1) in wanted:
                hits.append((m.group(1), line_no, m.group(2)))
                values.setdefault(m.group(1), (line_no, m.group(2)))
                continue
            m = _ENV_DEFAULT_RE.match(line)
            if m and m.group(1) in wanted:
                hits.append((m.group(1), line_no, m.group(2)))
                values.setdefault(m.group(1), (line_no, m.group(2)))
                continue
            if "MODELS_PATH" in known and "MODELS_PATH" not in values:
                m = _MODELS_PATH_RE.match(line)
                if m:
                    value = line.split("=", 1)[1].strip()
                    hits.append(("MODELS_PATH", line_no, value))
                    values["MODELS_PATH"] = (line_no, value)
            m = _GPU_SNAPSHOT_RE.match(line)
            if m:
                default = (m.group(1) == "True") if m.group(1) else False
                gpu_snapshot.append(
                    {"line": line_no, "default": default, "expr": line.strip()}
                )
        results[rel] = {
            "present": True,
            "hits": hits,
            "values": values,
            "gpu_snapshot": gpu_snapshot,
        }
    return results


def _combine(v1: str | None, v2: str | None) -> str:
    if v1 is None and v2 is None:
        return "(not extracted)"
    if v1 == v2:
        return str(v1)
    parts = [f"V1: {v1}" for v in (v1,) if v] + [f"V2: {v2}" for v in (v2,) if v]
    return " / ".join(parts)


def build_storage_map(constants: dict) -> list[dict]:
    """Build the volume-name / mount-path / referenced-by rows per role."""
    v1 = constants["comfyapp.py"]["values"]
    v2 = constants["comfymodal_runtime/modal_app.py"]["values"]
    rows = []
    for role, description, mapping in _ROLE_INFO:
        v1_name = v1.get(mapping["v1_name"], (None, None))[1] if mapping["v1_name"] else None
        v2_name = v2.get(mapping["v2_name"], (None, None))[1] if mapping["v2_name"] else None
        v1_path = v1.get(mapping["v1_path"], (None, None))[1] if mapping["v1_path"] else None
        v2_path = v2.get(mapping["v2_path"], (None, None))[1] if mapping["v2_path"] else None
        referenced = []
        if mapping["v1_name"] and (v1_name is not None or v1_path is not None):
            referenced.append("V1 comfyapp.py")
        if mapping["v2_name"] and (v2_name is not None or v2_path is not None):
            referenced.append("V2 modal_app.py")
        rows.append({
            "role": role,
            "description": description,
            "volume_name": _combine(v1_name, v2_name),
            "mount_path": _combine(v1_path, v2_path),
            "referenced_by": ", ".join(referenced) or "(none)",
        })
    return rows


def _manifest_summary(data: object | None, error: str | None) -> dict:
    if data is None:
        return {
            "present": False, "error": error, "total_entries": 0,
            "per_folder": {}, "size_field_present": False, "total_bytes": None,
        }
    entries = data.get("entries", []) if isinstance(data, dict) else []
    if not isinstance(entries, list):
        entries = []
    per_folder: dict[str, int] = {}
    size_keys = ("size", "bytes", "size_bytes", "file_size", "size_mb", "total_bytes")
    size_field_present = False
    total_bytes = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        folder = str(entry.get("folder") or "unknown")
        per_folder[folder] = per_folder.get(folder, 0) + 1
        for key in size_keys:
            value = entry.get(key)
            if isinstance(value, (int, float)):
                size_field_present = True
                total_bytes += int(value)
                break
    return {
        "present": True, "error": None, "total_entries": len(entries),
        "per_folder": per_folder, "size_field_present": size_field_present,
        "total_bytes": total_bytes if size_field_present else None,
    }


def _workspaces_summary(data: object | None, error: str | None) -> dict:
    if data is None:
        return {
            "present": False, "error": error, "active_workspace_id": None,
            "active_workspace_name": None, "token_fields": "redacted",
        }
    active_id = data.get("active_workspace_id") if isinstance(data, dict) else None
    name = None
    for ws in data.get("workspaces", []) if isinstance(data, dict) else []:
        if isinstance(ws, dict) and ws.get("id") == active_id:
            name = ws.get("label") or ws.get("name")
            break
    return {
        "present": True, "error": None, "active_workspace_id": active_id,
        "active_workspace_name": name, "token_fields": "redacted",
    }


def state_file_summaries() -> dict:
    settings, settings_err = _read_json(MODAL_SETTINGS)
    deployed, deployed_err = _read_json(DEPLOYED_STATE)
    manifest, manifest_err = _read_json(MODEL_MANIFEST)
    workspaces, workspaces_err = _read_json(MODAL_WORKSPACES)
    settings_dict = settings if isinstance(settings, dict) else {}
    deployed_dict = deployed if isinstance(deployed, dict) else {}
    return {
        "modal_settings": {
            "present": settings is not None,
            "error": settings_err,
            "execution_mode": settings_dict.get("execution_mode"),
            "save_folder": settings_dict.get("save_folder"),
        },
        "deployed_state": {
            "present": deployed is not None,
            "error": deployed_err,
            "app_name": deployed_dict.get("app_name"),
            "comfyui_version": deployed_dict.get("comfyui_version"),
        },
        "model_manifest": _manifest_summary(manifest, manifest_err),
        "modal_workspaces": _workspaces_summary(workspaces, workspaces_err),
    }


def _find_lines(text: str, needle: str) -> dict:
    lines = [i + 1 for i, line in enumerate(text.splitlines()) if needle in line]
    return {"found": bool(lines), "lines": lines[:20]}


def loader_read_path_data() -> dict:
    if not PARENT_COMFY_UTILS.is_file():
        return {"path": str(PARENT_COMFY_UTILS), "present": False,
                "safe_open": None, "mmap": None}
    text = PARENT_COMFY_UTILS.read_text(encoding="utf-8")
    return {
        "path": str(PARENT_COMFY_UTILS),
        "present": True,
        "safe_open": _find_lines(text, "safe_open"),
        "mmap": _find_lines(text, "mmap"),
    }


def local_modal_metadata_data() -> dict:
    home = Path.home()
    modal_dir = home / ".modal"
    toml = home / ".modal.toml"
    return {
        "modal_dir": {"path": str(modal_dir), "present": modal_dir.is_dir()},
        "modal_toml": {"path": str(toml), "present": toml.is_file()},
        "note": "token contents are never printed (redacted)",
    }


def inspect_local() -> dict:
    constants = extract_constants()
    return {
        "repo_root": str(REPO_ROOT),
        "state_files": state_file_summaries(),
        "constants": constants,
        "storage_map": build_storage_map(constants),
        "loader_read_path": loader_read_path_data(),
        "local_modal_metadata": local_modal_metadata_data(),
        "read_only_checks": READ_ONLY_CHECKS,
        "mutated_nothing": True,
    }


def _section(title: str) -> None:
    print("")
    print("=" * 72)
    print(title)
    print("=" * 72)


def _render_table(header: list[str], rows: list[list[str]]) -> None:
    widths = [len(h) for h in header]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    print("  " + "  ".join(h.ljust(widths[i]) for i, h in enumerate(header)))
    print("  " + "  ".join("-" * widths[i] for i in range(len(header))))
    for row in rows:
        print("  " + "  ".join(str(c).ljust(widths[i]) for i, c in enumerate(row)))


def render_sections(data: dict) -> None:
    print("comfyui-modal storage inspection (read-only; default mode: no network)")
    sf = data["state_files"]

    _section("LOCAL STATE FILES")
    ms = sf["modal_settings"]
    if ms["present"]:
        print(
            f"  .modal_settings.json     execution_mode={ms['execution_mode']!r}  "
            f"save_folder={ms['save_folder']!r}"
        )
    else:
        print(f"  .modal_settings.json     NOT READABLE ({ms['error']})")

    ds = sf["deployed_state"]
    if ds["present"]:
        print(
            f"  .deployed_state.json     app_name={ds['app_name']!r}  "
            f"comfyui_version={ds['comfyui_version']!r}"
        )
    else:
        print(f"  .deployed_state.json     NOT READABLE ({ds['error']})")

    mm = sf["model_manifest"]
    if mm["present"]:
        print(f"  .model_manifest.json     entries={mm['total_entries']}")
        for folder in sorted(mm["per_folder"]):
            print(f"      {folder:<22} {mm['per_folder'][folder]}")
        if mm["size_field_present"]:
            print(f"      total bytes (summed size field): {mm['total_bytes']}")
        else:
            print("      no size field in any entry -> total bytes not available (nothing fetched)")
    else:
        print(f"  .model_manifest.json     NOT READABLE ({mm['error']})")

    ws = sf["modal_workspaces"]
    if ws["present"]:
        print(f"  .modal_workspaces.json   active_workspace_id={ws['active_workspace_id']!r}")
        print(f"      active workspace name={ws['active_workspace_name']!r}")
        print("      token_id/token_secret: redacted (never printed)")
    else:
        print(f"  .modal_workspaces.json   NOT READABLE ({ws['error']})")

    _section("CONSTANTS (regex-extracted; modules NOT imported)")
    consts = data["constants"]
    print(
        "  Known V1/V2 constants below; supplementary mount-path constants "
        "(CUSTOM_NODES_PATH, PROFILE_PATH, PROMPT_CACHE_VOLUME_PATH) also "
        "extracted and feed the STORAGE MAP mount column."
    )
    for rel in ("comfyapp.py", "comfymodal_runtime/modal_app.py"):
        info = consts[rel]
        print(f"  {rel}")
        if not info["present"]:
            print("      (file not found)")
            continue
        for name, line_no, value in info["hits"]:
            print(f"      {name:<32} = {value!r:<45} [line {line_no}]")
    gpu = consts["comfyapp.py"].get("gpu_snapshot", [])
    if gpu:
        print("  COMFYMODAL_ENABLE_GPU_SNAPSHOT default")
        for hit in gpu:
            print(
                f"      default = {hit['default']!r}  [comfyapp.py line {hit['line']} "
                "- env_flag() without explicit default (signature default False)]"
            )

    _section("STORAGE MAP")
    rows = [
        [r["role"], r["volume_name"], r["mount_path"], r["referenced_by"]]
        for r in data["storage_map"]
    ]
    _render_table(["ROLE", "VOLUME NAME", "MOUNT PATH", "REFERENCED BY"], rows)
    print("  roles:")
    for r in data["storage_map"]:
        print(f"    {r['role']:<14} {r['description']}")

    _section("MODEL WEIGHTS SUMMARY")
    mm = sf["model_manifest"]
    if mm["present"]:
        for folder in sorted(mm["per_folder"]):
            print(f"  {folder:<22} {mm['per_folder'][folder]} entries")
        print(f"  total entries: {mm['total_entries']}")
    else:
        print(f"  (unavailable - {mm['error']})")

    _section("LOADER READ PATH")
    lr = data["loader_read_path"]
    if lr["present"]:
        print(f"  parent comfy/utils.py found: {lr['path']}")
        print(
            "  contains 'safe_open': "
            f"{'yes' if lr['safe_open']['found'] else 'no'}  "
            f"(lines: {lr['safe_open']['lines'] or '-'})"
        )
        print(
            "  contains 'mmap':        "
            f"{'yes' if lr['mmap']['found'] else 'no'}  "
            f"(lines: {lr['mmap']['lines'] or '-'})"
        )
    else:
        print(f"  parent repo path was not found: {lr['path']}")
        print("  (safe_open / mmap check skipped)")

    _section("LOCAL MODAL METADATA")
    lm = data["local_modal_metadata"]
    print(f"  {lm['modal_dir']['path']} (directory): {'present' if lm['modal_dir']['present'] else 'absent'}")
    print(f"  {lm['modal_toml']['path']}: {'present' if lm['modal_toml']['present'] else 'absent'}")
    print(f"  {lm['note']}")

    _section("READ-ONLY CHECKS (generation identification - NOT executed)")
    print(data["read_only_checks"].rstrip())

    print("")
    print("This script mutated nothing.")


def default_probe_volumes(constants: dict) -> list[str]:
    """Model / custom-nodes / runtime-state volume names found above, deduped."""
    v1 = constants["comfyapp.py"]["values"]
    v2 = constants["comfymodal_runtime/modal_app.py"]["values"]
    candidates = [
        v1.get("VOLUME_NAME", (None, None))[1],
        v2.get("MODELS_VOLUME_NAME", (None, None))[1],
        v1.get("CUSTOM_NODES_VOLUME_NAME", (None, None))[1],
        v2.get("CUSTOM_NODES_VOLUME_NAME", (None, None))[1],
        v1.get("RUNTIME_CONFIG_VOLUME_NAME", (None, None))[1],
        v2.get("RUNTIME_STATE_VOLUME_NAME", (None, None))[1],
    ]
    seen: set[str] = set()
    out: list[str] = []
    for name in candidates:
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def _map_version(version: object) -> str:
    raw = getattr(version, "value", version)
    if isinstance(raw, int):
        return f"v{raw}" if raw in (1, 2) else f"v{raw}"
    text = str(raw).strip().lower()
    if text in {"1", "v1"}:
        return "v1"
    if text in {"2", "v2"}:
        return "v2"
    return text or f"({type(raw).__name__})"


def run_probe(volume_names: list[str]) -> int:
    print("")
    print("WARNING: --probe makes READ-ONLY Modal API calls "
          "(Volume.from_name + hydrate, create_if_missing=False).")
    print("Nothing is created, written, or mutated. Run only by the execution")
    print("owner (C9) in an allowed window.")
    print("")
    try:
        import modal  # noqa: PLC0415, F401
    except Exception as exc:  # noqa: BLE001
        print(f"modal SDK not importable: {exc}")
        print(
            "install with: pip install modal   "
            "(credentials: ~/.modal.toml or MODAL_TOKEN_ID / MODAL_TOKEN_SECRET)"
        )
        return 1
    if not volume_names:
        print("no volume names to probe (none found locally and none passed)")
        return 0
    results: list[tuple[str, str]] = []
    for name in volume_names:
        try:
            vol = modal.Volume.from_name(name, create_if_missing=False, version=1)
            vol.hydrate()
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).lower()
            if "v2" in msg:
                result = "v2 (per version-pin probe)"
            else:
                result = f"unknown: {type(exc).__name__}"
            results.append((name, result))
            continue
        try:
            metadata: Any = getattr(vol, "_metadata", None)
            version = getattr(metadata, "version", None)
            results.append((name, _map_version(version)))
        except Exception:  # noqa: BLE001
            results.append((name, "v1 (probe passed, version attr unavailable)"))
    print(f"{'VOLUME':<48} GENERATION")
    print("-" * 70)
    for name, generation in results:
        print(f"{name:<48} {generation}")
    print("")
    print("Probe complete. No volumes were created or modified.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="inspect_modal_model_storage",
        description=(
            "Read-only Modal storage map + volume-generation identification. "
            "Default mode performs NO network access and mutates nothing."
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--probe",
        action="store_true",
        help="READ-ONLY Modal API calls to detect volume generation (C9, allowed window only)",
    )
    mode.add_argument(
        "--json",
        action="store_true",
        help="print the local-inspection summary as JSON instead of sections (default mode only)",
    )
    parser.add_argument(
        "--volumes",
        default="",
        help="comma-separated volume names for --probe "
        "(default: model/custom-nodes/runtime-state volume names found above)",
    )
    args = parser.parse_args(argv)

    if args.volumes and not args.probe:
        parser.error("--volumes requires --probe")

    if args.probe:
        constants = extract_constants()
        names = (
            [n.strip() for n in args.volumes.split(",") if n.strip()]
            if args.volumes.strip()
            else default_probe_volumes(constants)
        )
        print(f"probing volumes: {', '.join(names) or '(none found)'}")
        return run_probe(names)

    data = inspect_local()
    if args.json:
        print(json.dumps(data, indent=2, default=str))
    else:
        render_sections(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
