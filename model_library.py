"""Studio Model Library: local model registry with derived install state.

The library is a JSON store of ``ModelRecord`` entries (one per discovered
identity — same filename + different hash => distinct records).  Records
are created by a filesystem scan (``ModelDiscovery.scan_and_reconcile``)
and are never deleted: a model removed from disk still appears as a record
with derived ``installed=False`` so metadata survives.

``installed`` is always DERIVED at read time from the record's ``local_path``
and ``fingerprint`` (size + mtime) — it is never persisted as stored truth.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from studio_store import StudioJsonStore

MODEL_TYPES = [
    "checkpoint",
    "unet",
    "clip",
    "vae",
    "lora",
    "controlnet",
    "upscaler",
    "other",
]

FOLDER_MODEL_TYPES: dict[str, str] = {
    "checkpoints": "checkpoint",
    "unet": "unet",
    "diffusion_models": "unet",
    "clip": "clip",
    "text_encoders": "clip",
    "vae": "vae",
    "loras": "lora",
    "controlnet": "controlnet",
    "upscale_models": "upscaler",
}

# Buckets discovered when the ComfyUI ``folder_paths`` module is unavailable.
KNOWN_DISCOVERY_BUCKETS: tuple[str, ...] = (
    "checkpoints",
    "unet",
    "diffusion_models",
    "clip",
    "text_encoders",
    "vae",
    "loras",
    "controlnet",
    "upscale_models",
    "embeddings",
    "style_models",
    "gligen",
)

# ComfyUI ``folder_paths`` registry keys that are not model buckets: code and
# dataset roots must never be walked as if every file were a model.
_NON_MODEL_REGISTRY_KEYS: frozenset[str] = frozenset(
    {"custom_nodes", "datasets", "configs"}
)

_ALLOWED_FOLDERS_FALLBACK: tuple[str, ...] = (
    "checkpoints",
    "unet",
    "diffusion_models",
    "clip",
    "text_encoders",
    "vae",
    "loras",
    "controlnet",
    "upscale_models",
    "embeddings",
    "style_models",
    "gligen",
)

_SHA256_CHUNK = 1024 * 1024


class ModelLibraryError(RuntimeError):
    """Base error for the model library service."""


class ModelNotFoundError(ModelLibraryError):
    """Raised when a model_id is not present in the store."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_model_id() -> str:
    return f"ml_{uuid.uuid4().hex[:16]}"


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while True:
                chunk = f.read(_SHA256_CHUNK)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


def _allowed_model_folders() -> tuple[str, ...]:
    try:
        from local_placeholders import ALLOWED_MODEL_FOLDERS

        return tuple(ALLOWED_MODEL_FOLDERS)
    except Exception:
        return _ALLOWED_FOLDERS_FALLBACK


def record_is_installed(record: dict[str, Any]) -> bool:
    """Derive ``installed`` from the record's stored metadata + disk state.

    A record is installed when its file exists on disk AND the file itself is
    non-empty.  Zero-byte sentinels (``put_*_here``) and stale placeholders
    therefore stay ``installed=False`` even when a legacy record stored a
    positive size.  When a fingerprint (size + mtime_ns) was recorded it must
    still match the file; a mismatch means the file was replaced by a
    different model, so the old record is reported missing.
    """
    try:
        local_path = record.get("local_path", "")
        if not local_path or not os.path.isfile(local_path):
            return False
        st = os.stat(local_path)
        if st.st_size <= 0:
            # Zero-byte file: placeholder, never an installed model.
            return False
        stored_size = record.get("size", 0)
        if isinstance(stored_size, int) and stored_size > 0 and stored_size != st.st_size:
            # Disk content no longer matches the recorded size.
            return False
        fingerprint = record.get("fingerprint")
        if fingerprint and isinstance(fingerprint, dict):
            if fingerprint.get("size") != st.st_size:
                return False
            if fingerprint.get("mtime_ns") != st.st_mtime_ns:
                return False
        return True
    except Exception:
        return False


# ── Record ────────────────────────────────────────────────────────────────


@dataclass
class ModelRecord:
    """One discovered model identity in the library."""

    model_id: str
    folder: str
    filename: str
    display_name: str
    model_type: str
    local_path: str
    hash: str
    size: int
    source_urls: list[str] = field(default_factory=list)
    provider: str = ""
    revision: str = ""
    is_placeholder: bool = False
    fingerprint: Optional[dict] = None
    discovered_at: str = ""
    updated_at: str = ""
    notes: str = ""
    tags: list[str] = field(default_factory=list)

    @property
    def installed(self) -> bool:
        return record_is_installed(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "folder": self.folder,
            "filename": self.filename,
            "display_name": self.display_name,
            "model_type": self.model_type,
            "local_path": self.local_path,
            "hash": self.hash,
            "size": self.size,
            "source_urls": list(self.source_urls),
            "provider": self.provider,
            "revision": self.revision,
            "is_placeholder": self.is_placeholder,
            "fingerprint": dict(self.fingerprint) if self.fingerprint else None,
            "discovered_at": self.discovered_at,
            "updated_at": self.updated_at,
            "notes": self.notes,
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelRecord":
        filename = str(data.get("filename", ""))
        display_name = str(data.get("display_name", "") or "")
        if not display_name:
            display_name = Path(filename).stem
        fingerprint = data.get("fingerprint")
        return cls(
            model_id=str(data.get("model_id", "")),
            folder=str(data.get("folder", "")),
            filename=filename,
            display_name=display_name,
            model_type=str(data.get("model_type", "other")),
            local_path=str(data.get("local_path", "")),
            hash=str(data.get("hash", "")),
            size=int(data.get("size", 0) or 0),
            source_urls=[u for u in (data.get("source_urls") or []) if isinstance(u, str)],
            provider=str(data.get("provider", "")),
            revision=str(data.get("revision", "")),
            is_placeholder=bool(data.get("is_placeholder", False)),
            fingerprint=dict(fingerprint) if isinstance(fingerprint, dict) else None,
            discovered_at=str(data.get("discovered_at", "")),
            updated_at=str(data.get("updated_at", "")),
            notes=str(data.get("notes", "")),
            tags=[t for t in (data.get("tags") or []) if isinstance(t, str)],
        )


# ── Store ─────────────────────────────────────────────────────────────────


class ModelLibraryStore:
    """Persistent JSON store of model records (thread-safe, atomic)."""

    FILENAME = ".studio_model_library.json"

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.store = StudioJsonStore(self.root / self.FILENAME)

    def list_records(self) -> list[dict[str, Any]]:
        return self.store.read()

    def read_all(self) -> list[dict[str, Any]]:
        return self.store.read()

    def get_record(self, model_id: str) -> Optional[dict[str, Any]]:
        for record in self.store.read():
            if record.get("model_id") == model_id:
                return record
        return None

    def records_by_filename(self, filename: str) -> list[dict[str, Any]]:
        return [r for r in self.store.read() if r.get("filename") == filename]

    def upsert(self, record: ModelRecord | dict[str, Any]) -> dict[str, Any]:
        data = record.to_dict() if isinstance(record, ModelRecord) else dict(record)

        def _mutate(rows: list[dict]) -> None:
            for i, existing in enumerate(rows):
                if existing.get("model_id") == data["model_id"]:
                    rows[i] = data
                    return
            rows.append(data)

        self.store.update(_mutate)
        return data

    def replace_records(self, records: list[dict[str, Any]]) -> None:
        data = [r.to_dict() if isinstance(r, ModelRecord) else dict(r) for r in records]

        def _mutate(rows: list[dict]) -> None:
            rows[:] = data

        self.store.update(_mutate)


# ── Discovery ─────────────────────────────────────────────────────────────


class ModelDiscovery:
    """Filesystem scan reconciling disk state with the model library store."""

    KNOWN_BUCKETS = KNOWN_DISCOVERY_BUCKETS
    FOLDER_MODEL_TYPES = FOLDER_MODEL_TYPES

    def folder_paths_map(self, comfyui_root: str | Path) -> dict[str, list[str]]:
        """Map model bucket -> list of base dirs to scan.

        Uses the live ComfyUI ``folder_paths`` registry when importable so
        every canonical model folder it registers is scanned (``unet`` aliases
        its legacy directory through ``diffusion_models``, newer buckets like
        ``diffusers``/``model_patches`` are picked up automatically).  On top
        of that, every known bucket that exists on disk is merged in, so a
        real ``models/<bucket>`` directory is still discovered when ComfyUI's
        registry omits it.  A physical directory is assigned to exactly one
        bucket (first wins) to keep one file from producing duplicate records.
        Never raises.
        """
        models_root = Path(comfyui_root) / "models"
        buckets: dict[str, list[str]] = {}

        try:
            import folder_paths  # type: ignore[import-not-found]

            names = getattr(folder_paths, "folder_names_and_paths", None)
            if isinstance(names, dict):
                for raw_bucket, raw in names.items():
                    bucket = str(raw_bucket)
                    if not bucket or bucket in _NON_MODEL_REGISTRY_KEYS:
                        continue
                    paths = None
                    if isinstance(raw, tuple) and raw:
                        paths = raw[0]
                    elif isinstance(raw, list):
                        paths = raw
                    if not paths:
                        continue
                    bucket_paths = buckets.setdefault(bucket, [])
                    for path in paths:
                        value = str(path)
                        if value and value not in bucket_paths:
                            bucket_paths.append(value)
        except Exception:
            pass

        # Merge on-disk canonical buckets the registry did not expose (legacy
        # ComfyUI versions, or a bucket whose directory exists but is not
        # registered).  Registry paths keep priority so aliases stay grouped.
        for bucket in self.KNOWN_BUCKETS:
            try:
                candidate = models_root / bucket
                if not candidate.is_dir():
                    continue
            except Exception:
                continue
            bucket_paths = buckets.setdefault(bucket, [])
            value = str(candidate)
            if value not in bucket_paths:
                bucket_paths.append(value)

        # One physical directory belongs to one bucket only: scanning the same
        # tree under two buckets would create duplicate records for one file.
        seen_dirs: set[str] = set()
        result: dict[str, list[str]] = {}
        for bucket, dirs in buckets.items():
            unique: list[str] = []
            for directory in dirs:
                try:
                    key = os.path.normcase(os.path.normpath(directory))
                except Exception:
                    continue
                if key in seen_dirs:
                    continue
                seen_dirs.add(key)
                unique.append(directory)
            if unique:
                result[bucket] = unique
        return result

    @staticmethod
    def _model_type_for_folder(folder: str) -> str:
        return FOLDER_MODEL_TYPES.get(folder, "other")

    def _make_record(
        self,
        folder: str,
        filename: str,
        local_path: str,
        size: int,
        digest: str,
        is_placeholder: bool,
        fingerprint: dict,
        now: str,
    ) -> ModelRecord:
        return ModelRecord(
            model_id=make_model_id(),
            folder=folder,
            filename=filename,
            display_name=Path(filename).stem,
            model_type=self._model_type_for_folder(folder),
            local_path=local_path,
            hash=digest,
            size=size,
            is_placeholder=is_placeholder,
            fingerprint=fingerprint,
            discovered_at=now,
            updated_at=now,
        )

    def scan_and_reconcile(
        self,
        store: ModelLibraryStore,
        comfyui_root: str | Path,
        force_rehash: bool = False,
    ) -> dict[str, Any]:
        """Scan the model folders and reconcile them with the store.

        Returns a summary dict with keys ``added``, ``updated``, ``removed``,
        ``unchanged``, ``hashed``, ``placeholders``, ``total``.

        Identity rule: an existing record with the same ``(folder, filename)``
        AND same hash AND same fingerprint is unchanged (no rehash).  A file
        whose content changed produces a NEW record with a new ``model_id``;
        the old record remains in the store with derived ``installed=False``.
        Every filesystem operation is guarded; this never raises.
        """
        summary: dict[str, Any] = {
            "added": 0,
            "updated": 0,
            "removed": 0,
            "unchanged": 0,
            "hashed": 0,
            "placeholders": 0,
            "total": 0,
        }
        folders_map = self.folder_paths_map(comfyui_root)
        existing = store.list_records()
        now = _now_iso()
        new_records: list[dict[str, Any]] = []
        matched_ids: set[str] = set()

        for bucket, base_dirs in folders_map.items():
            for base in base_dirs:
                if not os.path.isdir(base):
                    continue
                try:
                    walker = os.walk(base)
                except Exception:
                    continue
                for root_dir, dirs, files in walker:
                    dirs[:] = [d for d in dirs if not d.startswith(".")]
                    for fname in sorted(files):
                        if fname.startswith("."):
                            continue
                        full = os.path.join(root_dir, fname)
                        try:
                            rel = os.path.relpath(full, base)
                            if rel.startswith(".."):
                                continue
                            st = os.stat(full)
                        except Exception:
                            continue
                        filename = rel.replace(os.sep, "/")
                        if not filename:
                            continue
                        size = st.st_size
                        fingerprint = {"size": size, "mtime_ns": st.st_mtime_ns}
                        is_placeholder = size == 0
                        same_key = [
                            r
                            for r in existing
                            if r.get("folder") == bucket and r.get("filename") == filename
                        ]

                        # Fast path: unchanged fingerprint → no rehash.
                        if not force_rehash:
                            fp_match = next(
                                (r for r in same_key if r.get("fingerprint") == fingerprint),
                                None,
                            )
                            if fp_match is not None and (fp_match.get("hash") or is_placeholder):
                                matched_ids.add(fp_match["model_id"])
                                new_records.append(fp_match)
                                summary["unchanged"] += 1
                                continue

                        if is_placeholder:
                            digest = ""
                            summary["placeholders"] += 1
                        else:
                            digest = _sha256_file(full)
                            if digest:
                                summary["hashed"] += 1

                        same_hash = next(
                            (r for r in same_key if digest and r.get("hash") == digest),
                            None,
                        )
                        if same_hash is not None:
                            rec = dict(same_hash)
                            matched_ids.add(rec["model_id"])
                            rec.update(
                                {
                                    "size": size,
                                    "is_placeholder": is_placeholder,
                                    "fingerprint": fingerprint,
                                    "local_path": full,
                                    "updated_at": now,
                                }
                            )
                            new_records.append(rec)
                            summary["updated"] += 1
                        else:
                            record = self._make_record(
                                bucket,
                                filename,
                                full,
                                size,
                                digest,
                                is_placeholder,
                                fingerprint,
                                now,
                            )
                            matched_ids.add(record.model_id)
                            new_records.append(record.to_dict())
                            summary["added"] += 1

        # Records whose file no longer exists stay in the store (derived
        # installed=False); they are counted as removed in the summary.
        for rec in existing:
            if rec.get("model_id") in matched_ids:
                continue
            try:
                exists = bool(rec.get("local_path")) and os.path.isfile(
                    str(rec.get("local_path", ""))
                )
            except Exception:
                exists = False
            if not exists:
                summary["removed"] += 1
            new_records.append(rec)

        store.replace_records(new_records)
        summary["total"] = len(new_records)
        return summary


# ── Service ───────────────────────────────────────────────────────────────


class ModelLibraryService:
    """Facade over the model library store + discovery + validation rules."""

    ALLOWED_METADATA_KEYS = {
        "display_name",
        "notes",
        "tags",
        "source_urls",
        "provider",
        "revision",
    }

    def __init__(self, root: str | Path, comfyui_root: str | Path) -> None:
        self.store = ModelLibraryStore(root)
        self.comfyui_root = str(comfyui_root)
        self.discovery = ModelDiscovery()

    def list_models(
        self, search: str = "", model_type: str = "", state: str = ""
    ) -> list[dict[str, Any]]:
        """List records filtered by search / type / derived install state."""
        query = (search or "").strip().lower()
        results: list[dict[str, Any]] = []
        for record in self.store.list_records():
            if query:
                haystack = " ".join(
                    [
                        str(record.get("display_name", "")),
                        str(record.get("filename", "")),
                        str(record.get("folder", "")),
                        " ".join(str(t) for t in (record.get("tags") or [])),
                    ]
                ).lower()
                if query not in haystack:
                    continue
            if model_type and record.get("model_type") != model_type:
                continue
            installed = record_is_installed(record)
            if state == "installed" and not installed:
                continue
            if state == "missing" and installed:
                continue
            item = dict(record)
            item["installed"] = installed
            results.append(item)
        results.sort(key=lambda item: str(item.get("display_name", "")).lower())
        return results

    def get_model(self, model_id: str) -> dict[str, Any]:
        record = self.store.get_record(model_id)
        if record is None:
            raise ModelNotFoundError(f"model {model_id!r} not found")
        item = dict(record)
        item["installed"] = record_is_installed(record)
        return item

    def update_metadata(self, model_id: str, body: dict[str, Any]) -> dict[str, Any]:
        record = self.store.get_record(model_id)
        if record is None:
            raise ModelNotFoundError(f"model {model_id!r} not found")
        for key in body:
            if key not in self.ALLOWED_METADATA_KEYS:
                raise ModelLibraryError(
                    f"field {key!r} is not editable on a model record"
                )
        updated = dict(record)
        if "display_name" in body:
            value = body["display_name"]
            if not isinstance(value, str) or not value.strip():
                raise ModelLibraryError("display_name must be a non-empty string")
            updated["display_name"] = value.strip()
        if "notes" in body:
            if not isinstance(body["notes"], str):
                raise ModelLibraryError("notes must be a string")
            updated["notes"] = body["notes"]
        if "tags" in body:
            if not isinstance(body["tags"], list) or not all(
                isinstance(t, str) for t in body["tags"]
            ):
                raise ModelLibraryError("tags must be a list of strings")
            updated["tags"] = list(body["tags"])
        if "source_urls" in body:
            if not isinstance(body["source_urls"], list) or not all(
                isinstance(u, str) for u in body["source_urls"]
            ):
                raise ModelLibraryError("source_urls must be a list of strings")
            updated["source_urls"] = list(body["source_urls"])
        if "provider" in body:
            if not isinstance(body["provider"], str):
                raise ModelLibraryError("provider must be a string")
            updated["provider"] = body["provider"]
        if "revision" in body:
            if not isinstance(body["revision"], str):
                raise ModelLibraryError("revision must be a string")
            updated["revision"] = body["revision"]
        updated["updated_at"] = _now_iso()
        self.store.upsert(updated)
        item = dict(updated)
        item["installed"] = record_is_installed(updated)
        return item

    def rescan(self, force_rehash: bool = False) -> dict[str, Any]:
        return self.discovery.scan_and_reconcile(
            self.store, self.comfyui_root, force_rehash=force_rehash
        )

    def install_request(
        self, folder: str, filename: str, url: str
    ) -> dict[str, Any]:
        """Validate an install request; does NOT download anything."""
        if folder not in _allowed_model_folders():
            raise ModelLibraryError(f"unsupported model folder: {folder}")
        if not isinstance(filename, str) or not filename.strip():
            raise ModelLibraryError("filename required")
        fname = filename.strip()
        if fname in {".", ".."} or "/" in fname or "\\" in fname:
            raise ModelLibraryError(f"unsafe filename: {filename}")
        if os.path.isabs(fname):
            raise ModelLibraryError(f"unsafe filename: {filename}")
        if len(fname) >= 2 and fname[1] == ":":
            raise ModelLibraryError(f"unsafe filename: {filename}")
        if not isinstance(url, str) or not url:
            raise ModelLibraryError("url required")
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ModelLibraryError(f"unsupported url: {url}")
        from model_manifest import infer_source_kind

        return {
            "folder": folder,
            "filename": fname,
            "url": url,
            "source_kind": infer_source_kind(url),
            "requires_hf_token": "huggingface.co" in url,
            "requires_civitai_token": ("civitai" in url or "civitai.red" in url),
            "approved": True,
        }
