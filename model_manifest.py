import json
import os
import re as _re
import time
from pathlib import Path

from local_placeholders import ALLOWED_MODEL_FOLDERS, get_local_model_file_info, normalize_model_filename, normalize_model_folder
from workflow_metadata import extract_workflow_model_refs


WORKFLOW_ROLE_FOLDERS = {
    "checkpoint": {"checkpoints"},
    "unet": {"unet", "diffusion_models"},
    "clip": {"clip", "text_encoders"},
    "vae": {"vae"},
    "lora": {"loras"},
    "controlnet": {"controlnet"},
}


def _default_manifest() -> dict:
    return {"manifest_version": 1, "entries": []}


def load_master_manifest(path: str | Path) -> dict:
    target = Path(path)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError, OSError):
        return _default_manifest()
    if not isinstance(payload, dict) or not isinstance(payload.get("entries"), list):
        return _default_manifest()
    return payload


def save_master_manifest(path: str | Path, payload: dict) -> dict:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(target)
    return payload


def infer_source_kind(url: str) -> str:
    lower = (url or "").lower()
    if "huggingface.co" in lower:
        return "huggingface"
    if "civitai.com" in lower:
        return "civitai"
    if lower.startswith("http://") or lower.startswith("https://"):
        return "direct"
    return "unknown"


def normalize_manifest_entry(entry: dict, now: float | None = None) -> dict:
    now_value = time.time() if now is None else now
    folder = normalize_model_folder(entry.get("folder", ""))
    filename = normalize_model_filename(entry.get("filename", ""))
    url = (entry.get("url") or "").strip()
    source_kind = (entry.get("source_kind") or infer_source_kind(url)).strip() or "unknown"
    return {
        "folder": folder,
        "filename": filename,
        "url": url,
        "source_kind": source_kind,
        "requires_hf_token": bool(entry.get("requires_hf_token", False)),
        "requires_civitai_token": bool(entry.get("requires_civitai_token", False)),
        "sha256": entry.get("sha256") or None,
        "notes": entry.get("notes") or "",
        "added_at": entry.get("added_at") or now_value,
        "updated_at": now_value,
        "remove_on_swap": bool(entry.get("remove_on_swap", False)),
    }


def upsert_manifest_entry(path: str | Path, entry: dict) -> dict:
    payload = load_master_manifest(path)
    normalized = normalize_manifest_entry(entry)
    replaced = False
    entries = []
    for existing in payload["entries"]:
        if (existing.get("folder"), existing.get("filename")) == (normalized["folder"], normalized["filename"]):
            entries.append({**existing, **normalized, "added_at": existing.get("added_at") or normalized["added_at"]})
            replaced = True
        else:
            entries.append(existing)
    if not replaced:
        entries.append(normalized)
    payload["entries"] = sorted(entries, key=lambda item: (item["folder"], item["filename"]))
    return save_master_manifest(path, payload)


def scan_manifest_issues(payload: dict) -> list[dict]:
    issues = []
    seen = {}
    for entry in payload.get("entries", []):
        key = (entry.get("folder"), entry.get("filename"))
        seen.setdefault(key, []).append(entry)
        if not entry.get("url") and not entry.get("remove_on_swap"):
            issues.append({"kind": "missing_url", **entry})
        if not entry.get("source_kind"):
            issues.append({"kind": "missing_source_kind", **entry})
        if entry.get("folder") not in ALLOWED_MODEL_FOLDERS:
            issues.append({"kind": "invalid_folder", **entry})
    for key, entries in seen.items():
        if len(entries) > 1:
            issues.append({"kind": "duplicate_key", "folder": key[0], "filename": key[1], "count": len(entries)})
    return issues


def scan_local_models_issues(comfyui_root: str, payload: dict) -> list[dict]:
    """Scan the local models directory for placeholder files not tracked in the manifest.

    Returns issues for each placeholder missing from the manifest, plus any
    manifest-level issues from scan_manifest_issues.
    """
    models_root = os.path.join(os.path.abspath(comfyui_root), "models")
    manifest_keys = {(entry.get("folder"), entry.get("filename")) for entry in payload.get("entries", [])}
    issues = scan_manifest_issues(payload)
    if not os.path.isdir(models_root):
        return issues
    for folder in os.listdir(models_root):
        if folder not in ALLOWED_MODEL_FOLDERS:
            continue
        folder_path = os.path.join(models_root, folder)
        if not os.path.isdir(folder_path):
            continue
        for fname in os.listdir(folder_path):
            fpath = os.path.join(folder_path, fname)
            if not os.path.isfile(fpath):
                continue
            size = os.path.getsize(fpath)
            if size != 0:
                continue
            # Skip ComfyUI's built-in "put_xxx_here" / "put_xxx_models_here" hint files
            stem, _ = os.path.splitext(fname)
            if _re.match(r"^put_.+_here$", stem, _re.IGNORECASE) or _re.match(r"^put_.+_models_here$", stem, _re.IGNORECASE):
                continue
            if (folder, fname) not in manifest_keys:
                issues.append({
                    "kind": "missing_from_manifest",
                    "folder": folder,
                    "filename": fname,
                    "url": "",
                    "source_kind": "unknown",
                })
    return issues


def build_workspace_swap_plan(payload: dict, remote_models: list[dict]) -> dict:
    remote_keys = {(item.get("folder"), item.get("name")) for item in remote_models}
    already_present = []
    to_install = []
    unresolved = []
    to_remove = []
    for entry in payload.get("entries", []):
        key = (entry.get("folder"), entry.get("filename"))
        if entry.get("remove_on_swap"):
            to_remove.append({"folder": key[0], "filename": key[1]})
        elif key in remote_keys:
            already_present.append({"folder": key[0], "filename": key[1]})
        elif not entry.get("url"):
            unresolved.append({"folder": key[0], "filename": key[1], "kind": "missing_url"})
        else:
            to_install.append({
                "url": entry["url"],
                "filename": entry["filename"],
                "save_path": entry["folder"],
                "requires_hf_token": bool(entry.get("requires_hf_token")),
                "requires_civitai_token": bool(entry.get("requires_civitai_token")),
            })
    return {"already_present": already_present, "to_install": to_install, "unresolved": unresolved, "to_remove": to_remove}


def export_workflow_manifest(master_manifest: dict, prompt: dict, workflow_name: str = "") -> dict:
    by_filename = {}
    for entry in master_manifest.get("entries", []):
        by_filename.setdefault(entry.get("filename"), []).append(entry)
    models = []
    unresolved = []
    for ref in extract_workflow_model_refs(prompt):
        allowed = WORKFLOW_ROLE_FOLDERS.get(ref["role"], set())
        matches = [item for item in by_filename.get(ref["filename"], []) if item.get("folder") in allowed]
        if len(matches) != 1 or not matches[0].get("url"):
            unresolved.append(ref)
            continue
        match = matches[0]
        models.append({
            "folder": match["folder"],
            "filename": match["filename"],
            "url": match["url"],
            "source_kind": (match.get("source_kind") or "unknown"),
            "requires_hf_token": bool(match.get("requires_hf_token")),
            "requires_civitai_token": bool(match.get("requires_civitai_token")),
            "notes": match.get("notes") or "",
        })
    return {
        "manifest_version": 1,
        "exported_at": time.time(),
        "workflow_name": workflow_name,
        "models": models,
        "unresolved": unresolved,
    }


def apply_manifest_repairs(payload: dict, updates: list[dict]) -> dict:
    indexed = {(item.get("folder"), item.get("filename")): dict(item) for item in payload.get("entries", [])}
    for update in updates:
        key = (update.get("folder"), update.get("filename"))
        if key not in indexed:
            if update.get("url") or update.get("remove"):
                indexed[key] = normalize_manifest_entry({**update, "remove_on_swap": bool(update.get("remove"))}, now=time.time())
            continue
        current = indexed[key]
        if update.get("remove"):
            indexed[key] = normalize_manifest_entry({**current, **update, "remove_on_swap": True}, now=time.time())
            continue
        if update.get("skip"):
            current.setdefault("notes", "")
            current["notes"] = (current["notes"] + "\nrepair skipped").strip()
            current["updated_at"] = time.time()
            continue
        merged = {**current, **update}
        indexed[key] = normalize_manifest_entry(merged, now=time.time())
    return {"manifest_version": payload.get("manifest_version", 1), "entries": list(indexed.values())}


def merge_workflow_manifest(local_payload: dict, imported_payload: dict, resolutions: dict[str, str] | None = None) -> dict:
    local_entries = list(local_payload.get("entries", []))
    by_key = {(item.get("folder"), item.get("filename")): item for item in local_entries}
    resolutions_map = resolutions or {}
    added = []
    filled = []
    conflicts = []
    for imported in imported_payload.get("models", []):
        key = (imported.get("folder"), imported.get("filename"))
        existing = by_key.get(key)
        if existing is None:
            local_entries.append(normalize_manifest_entry(imported))
            by_key[key] = local_entries[-1]
            added.append({"folder": key[0], "filename": key[1]})
            continue
        if not existing.get("url") and imported.get("url"):
            existing.update(normalize_manifest_entry({**existing, **imported, "added_at": existing.get("added_at")}))
            filled.append({"folder": key[0], "filename": key[1]})
            continue
        if existing.get("url") and imported.get("url") and existing.get("url") != imported.get("url"):
            resolution = resolutions_map.get(f"{key[0]}/{key[1]}")
            if resolution == "use_imported":
                existing.update(normalize_manifest_entry({**existing, **imported, "added_at": existing.get("added_at")}))
                continue
            if resolution in ("keep_local", "skip"):
                continue
            conflicts.append({
                "folder": key[0],
                "filename": key[1],
                "local_url": existing.get("url"),
                "imported_url": imported.get("url"),
            })
    return {"entries": local_entries, "added": added, "filled": filled, "conflicts": conflicts}
