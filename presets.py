"""Prompt and image preset persistence with content-addressed image blobs.

Layout (all relative to the custom node root):
    .presets/prompts/<preset_id>.json
    .presets/images/<preset_id>.json
    .preset_blobs/<sha256>.<ext>

Atomicity: every JSON file write uses tmp + os.replace.

Conventions:
- IDs are slugified from the preset name, plus a short uuid suffix for
  uniqueness: re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:48] + "-" + uuid4().hex[:8].
- Experiments reference image content hashes, not preset-relative paths.
  Deleting a preset never deletes blobs; shared blobs are reference-safe.
- A separate cleanup_orphan_blobs() function exists for explicit orphan
  cleanup. The matrix compiler never calls it implicitly.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile as _tempfile
import uuid
from pathlib import Path
from typing import Any


PROMPT_PRESET_SCHEMA_VERSION = 1
IMAGE_PRESET_SCHEMA_VERSION = 1

PROMPTS_DIRNAME = "prompts"
IMAGES_DIRNAME = "images"
BLOBS_DIRNAME = "preset_blobs"


# ── Errors ───────────────────────────────────────────────────────────────

class PresetError(RuntimeError):
    pass


class PresetNotFoundError(PresetError):
    pass


class PresetDuplicateError(PresetError):
    pass


# ── Path helpers ─────────────────────────────────────────────────────────

def _prompts_dir(root: str) -> Path:
    p = Path(root) / ".presets" / PROMPTS_DIRNAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def _images_dir(root: str) -> Path:
    p = Path(root) / ".presets" / IMAGES_DIRNAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def _blobs_dir(root: str) -> Path:
    p = Path(root) / BLOBS_DIRNAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def _make_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")[:48]
    if not slug:
        slug = "preset"
    return f"{slug}-{uuid.uuid4().hex[:8]}"


def _atomic_write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, sort_keys=True, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ── Prompt presets ───────────────────────────────────────────────────────

def create_prompt_preset(root: str, name: str, shared_negative: str, items: list) -> dict:
    pid = _make_id(name)
    preset = {
        "schema_version": PROMPT_PRESET_SCHEMA_VERSION,
        "id": pid,
        "name": name,
        "shared_negative": shared_negative or "",
        "items": [dict(it) for it in items],
    }
    _atomic_write_json(_prompts_dir(root) / f"{pid}.json", preset)
    return preset


def list_prompt_presets(root: str) -> list:
    out = []
    for path in sorted(_prompts_dir(root).glob("*.json")):
        preset = _read_json(path)
        if preset is not None:
            out.append(preset)
    return out


def get_prompt_preset(root: str, preset_id: str) -> dict:
    path = _prompts_dir(root) / f"{preset_id}.json"
    preset = _read_json(path)
    if preset is None:
        raise PresetNotFoundError(f"prompt preset {preset_id!r} not found")
    return preset


def rename_prompt_preset(root: str, preset_id: str, new_name: str) -> dict:
    preset = get_prompt_preset(root, preset_id)
    preset["name"] = new_name
    _atomic_write_json(_prompts_dir(root) / f"{preset_id}.json", preset)
    return preset


def duplicate_prompt_preset(root: str, preset_id: str, new_name: str) -> dict:
    src = get_prompt_preset(root, preset_id)
    new_id = _make_id(new_name)
    new_items = [dict(it) for it in src["items"]]
    preset = {
        "schema_version": PROMPT_PRESET_SCHEMA_VERSION,
        "id": new_id,
        "name": new_name,
        "shared_negative": src.get("shared_negative", ""),
        "items": new_items,
    }
    _atomic_write_json(_prompts_dir(root) / f"{new_id}.json", preset)
    return preset


def delete_prompt_preset(root: str, preset_id: str) -> None:
    path = _prompts_dir(root) / f"{preset_id}.json"
    if not path.exists():
        raise PresetNotFoundError(f"prompt preset {preset_id!r} not found")
    path.unlink()


def reorder_prompt_items(root: str, preset_id: str, new_order: list) -> dict:
    """Reorder items in a prompt preset. ``new_order`` is the list of item ids
    in the new order. Any ids not in the list are appended at the end in
    their previous order."""
    preset = get_prompt_preset(root, preset_id)
    by_id = {it["id"]: dict(it) for it in preset["items"]}
    seen = set()
    new_items: list = []
    for iid in new_order:
        if iid in by_id and iid not in seen:
            new_items.append(by_id[iid])
            seen.add(iid)
    for iid, it in by_id.items():
        if iid not in seen:
            new_items.append(it)
    preset["items"] = new_items
    _atomic_write_json(_prompts_dir(root) / f"{preset_id}.json", preset)
    return preset


def detect_prompt_duplicates(root: str, preset_id: str) -> list:
    """Return a list of duplicate groups.

    A group is a list of item ids whose enabled items have identical
    canonical content (text + negative + shared_negative). Returns [] when
    no duplicates are found. Disabled items are excluded.
    """
    preset = get_prompt_preset(root, preset_id)
    shared = preset.get("shared_negative", "")
    enabled = [it for it in preset["items"] if it.get("enabled", True)]
    buckets: dict = {}
    for it in enabled:
        canonical = json.dumps({
            "text": it.get("text", ""),
            "negative": it.get("negative") if it.get("negative") is not None else None,
            "shared": shared,
        }, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        buckets.setdefault(canonical, []).append(it["id"])
    groups = [ids for ids in buckets.values() if len(ids) > 1]
    return groups


def import_prompts_from_text(text: str, shared_negative: str = "") -> list:
    """Parse plain text into prompt items, one per non-empty line.

    Each item gets an auto-generated id, a label equal to the first 20
    characters of the text, and enabled=True. Negative is None.
    """
    items = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        iid = f"imp-{uuid.uuid4().hex[:8]}"
        items.append({
            "id": iid,
            "label": line[:20],
            "text": line,
            "negative": None,
            "enabled": True,
        })
    return items


# ── Image presets ────────────────────────────────────────────────────────

def add_image_to_preset(root: str, preset_id: str, *, label: str,
                        original_filename: str, mime_type: str, width: int,
                        height: int, content_hash: str, file_ext: str,
                        data: bytes) -> dict:
    """Add an image item to an existing preset, writing the blob to disk.

    The blob path is ``.preset_blobs/<content_hash>.<ext>``. If a blob with
    the same content_hash already exists, the file is reused (this is the
    content-addressed store). Returns the updated preset.
    """
    preset = get_image_preset(root, preset_id)
    blob_path = _blobs_dir(root) / f"{content_hash}{file_ext if file_ext.startswith('.') else '.' + file_ext}"
    if not blob_path.exists():
        with open(blob_path, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
    item = {
        "id": f"img-{uuid.uuid4().hex[:8]}",
        "label": label,
        "original_filename": original_filename,
        "content_hash": content_hash,
        "mime_type": mime_type,
        "width": int(width),
        "height": int(height),
        "enabled": True,
    }
    preset.setdefault("items", []).append(item)
    _atomic_write_json(_images_dir(root) / f"{preset_id}.json", preset)
    return preset


def hash_image_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ── Image preset CRUD ────────────────────────────────────────────────────

def create_image_preset(root: str, name: str, items: list | None = None) -> dict:
    pid = _make_id(name)
    preset = {
        "schema_version": IMAGE_PRESET_SCHEMA_VERSION,
        "id": pid,
        "name": name,
        "items": [dict(it) for it in (items or [])],
    }
    _atomic_write_json(_images_dir(root) / f"{pid}.json", preset)
    return preset


def list_image_presets(root: str) -> list:
    out = []
    for path in sorted(_images_dir(root).glob("*.json")):
        preset = _read_json(path)
        if preset is not None:
            out.append(preset)
    return out


def get_image_preset(root: str, preset_id: str) -> dict:
    path = _images_dir(root) / f"{preset_id}.json"
    preset = _read_json(path)
    if preset is None:
        raise PresetNotFoundError(f"image preset {preset_id!r} not found")
    return preset


def rename_image_preset(root: str, preset_id: str, new_name: str) -> dict:
    preset = get_image_preset(root, preset_id)
    preset["name"] = new_name
    _atomic_write_json(_images_dir(root) / f"{preset_id}.json", preset)
    return preset


def delete_image_preset(root: str, preset_id: str) -> None:
    """Delete an image preset. Blobs are NOT deleted; they remain on disk
    for reference-safe behavior. Call cleanup_orphan_blobs() explicitly to
    remove orphan blobs."""
    path = _images_dir(root) / f"{preset_id}.json"
    if not path.exists():
        raise PresetNotFoundError(f"image preset {preset_id!r} not found")
    path.unlink()


def remove_image_item(root: str, preset_id: str, item_id: str) -> dict:
    """Remove a single image item from a preset. The blob is not deleted."""
    preset = get_image_preset(root, preset_id)
    preset["items"] = [it for it in preset.get("items", []) if it.get("id") != item_id]
    _atomic_write_json(_images_dir(root) / f"{preset_id}.json", preset)
    return preset


def reorder_image_items(root: str, preset_id: str, new_order: list) -> dict:
    preset = get_image_preset(root, preset_id)
    by_id = {it["id"]: dict(it) for it in preset["items"]}
    seen = set()
    new_items: list = []
    for iid in new_order:
        if iid in by_id and iid not in seen:
            new_items.append(by_id[iid])
            seen.add(iid)
    for iid, it in by_id.items():
        if iid not in seen:
            new_items.append(it)
    preset["items"] = new_items
    _atomic_write_json(_images_dir(root) / f"{preset_id}.json", preset)
    return preset


def detect_image_duplicates_in_preset(root: str, preset_id: str) -> list:
    """Return duplicate groups within one preset (same content_hash)."""
    preset = get_image_preset(root, preset_id)
    enabled = [it for it in preset["items"] if it.get("enabled", True)]
    buckets: dict = {}
    for it in enabled:
        buckets.setdefault(it.get("content_hash", ""), []).append(it["id"])
    return [ids for ids in buckets.values() if len(ids) > 1 and "" not in ids]


def blob_path_for(root: str, content_hash: str, file_ext: str) -> Path:
    ext = file_ext if file_ext.startswith(".") else "." + file_ext
    return _blobs_dir(root) / f"{content_hash}{ext}"


def cleanup_orphan_blobs(root: str) -> int:
    """Delete any blob in .preset_blobs/ that is not referenced by any
    existing image preset. Returns the number of blobs deleted. This is
    destructive and is NOT called automatically by the runner."""
    referenced: set = set()
    for preset in list_image_presets(root):
        for it in preset.get("items", []):
            referenced.add((it.get("content_hash", ""), it.get("id", "")))
    # We need to know the file ext to find the blob on disk; reconstruct
    # from the preset items list.
    referenced_paths: set = set()
    for preset in list_image_presets(root):
        for it in preset.get("items", []):
            ch = it.get("content_hash", "")
            if not ch:
                continue
            # Walk blob dir to find the file matching this hash (any ext)
            for p in _blobs_dir(root).glob(f"{ch}.*"):
                referenced_paths.add(p.resolve())
    deleted = 0
    for p in _blobs_dir(root).iterdir():
        if p.is_file() and p.resolve() not in referenced_paths:
            p.unlink()
            deleted += 1
    return deleted
