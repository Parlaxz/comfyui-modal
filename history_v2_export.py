"""History V2 configured-folder Export CORE service.

Reusable server-side core for exporting ONE selected managed History V2
asset into the user's configured output folder, recording durable truth in
``export_records``:

    selected managed Asset + resolved live Export options
      → fetch/read managed bytes (local path OR ``modal://``)
      → verify against the immutable asset SHA-256
      → convert when the resolved output format requires it
      → write the destination atomically
      → verify the destination exists
      → upsert ``ExportRecord(state="exported", destination_path=…)``

Deliberate boundaries (Phase F7):

- NO HTTP route and NO frontend wiring live here.  A later integration
  batch calls ``HistoryV2ExportService.export_asset(...)``.
- Settings authority stays OUTSIDE the service: callers pass already-
  resolved :class:`ExportOptions` built from the canonical Output settings
  (``save_folder``, ``output_format``, ``quality``,
  ``webp_lossless_compression``, ``save_metadata_sidecar``).  This module
  never reads ``.modal_settings.json``, localStorage, or window globals.
- Export state is keyed by ``asset_id`` ONLY (one ``export_records`` row per
  asset).  Preview / Original / Thumbnail variants of one logical output
  therefore have fully independent export state, and a rerender's NEW asset
  always starts ``not_exported``.  No Generation-level collapsed state and
  no variant substitution happens here — the caller explicitly selects the
  asset to export.
- NO legacy run-history dependency: no ``run_id`` requirement, no
  ``.run_history`` store, no ``extra.output_saved`` flags, and no
  ``/run-history/{id}/save`` involvement.

Dependency injection:

- *repository* — anything exposing ``get_asset``, ``get_export_record`` and
  ``upsert_export_record`` with the ``HistoryV2Repository`` signatures.
- *byte_resolver* — optional async-or-sync callable ``(Asset) -> bytes``
  used for ``modal://`` managed references (the established URI-aware
  serving seam, e.g. ``modal_client.read_output_asset`` wrapped by the
  future route).  Remote availability is NEVER classified with
  ``os.path.isfile(modal_uri)``.  Local managed paths are read directly by
  this service.  Without a resolver, a ``modal://`` export fails truthfully
  WITHOUT writing any record (no real attempt occurred).
- *converter* — optional replacement for
  ``output_converter.convert_image_bytes`` (tests inject failures).
- *clock* — optional ``() -> ISO timestamp``.

Failure atomicity ordering (never persist ``exported`` before the file is
durably written):

    resolve source → validate bytes (sha256) → convert → atomic write
    → verify destination exists → persist ExportRecord(exported)

If record persistence fails AFTER the file write, the written destination
copy (+ sidecar) is deleted (legacy ``save_run_history_output`` precedent)
so a retry cannot strand untracked duplicates; if cleanup itself fails the
orphan path is reported truthfully on the result.  The MANAGED asset is
never modified or deleted by any path in this module.

Duplicate / missing semantics:

- record ``exported`` + destination file still exists + the recorded
  destination matches the currently resolved folder/format semantics
  → ``already_exported`` reuse, no duplicate file.
- record ``exported`` + destination gone → classified (and persisted) as
  ``missing`` first, then the explicit export proceeds (re-export allowed;
  managed source untouched).
- recorded destination differs from the current resolution because
  settings/folder changed → treated as an explicit export request, never a
  false ``already_exported`` hit.
"""

from __future__ import annotations

import hashlib
import inspect
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, Union

from history_v2_models import Asset, ExportState, utc_now_iso
from output_saver import (
    _build_metadata_sidecar,
    _ensure_dir,
    _resolve_save_folder,
    _sanitize,
    _unique_filename,
)

# ComfyUI root (this file: <root>/custom_nodes/comfyui-modal/…), matching the
# history_v2_store data-root derivation convention.
_DEFAULT_COMFYUI_ROOT = str(Path(__file__).resolve().parents[2])

# Workflow-name component cap so pathological names cannot push the final
# path past Windows MAX_PATH once date/seed/index/ext are appended.
_MAX_NAME_COMPONENT = 80

# Source-extension mapping used on the byte-preserving fast path
# (output_format == "original"); mirrors output_converter._FORMAT_META and
# the legacy adapter's _EXT_TO_MIME tables.
_SOURCE_EXT_BY_FORMAT = {
    "png": ".png",
    "webp": ".webp",
    "jpg": ".jpg",
    "jpeg": ".jpg",
    "gif": ".gif",
    "bmp": ".bmp",
}
_MIME_BY_EXT = {
    ".png": "image/png",
    ".webp": "image/webp",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}

# Reason codes surfaced on ExportResult.reason.
REASON_ASSET_NOT_FOUND = "asset_not_found"
REASON_REMOTE_RESOLVER_UNAVAILABLE = "remote_resolver_unavailable"
REASON_SOURCE_UNREADABLE = "source_unreadable"
REASON_HASH_MISMATCH = "hash_mismatch"
REASON_CONVERSION_FAILED = "conversion_failed"
REASON_WRITE_FAILED = "write_failed"
REASON_RECORD_PERSIST_FAILED = "record_persist_failed"

STATUS_OK = "ok"
STATUS_ERROR = "error"


class _RemoteResolverUnavailable(RuntimeError):
    """No byte resolver is wired for ``modal://`` assets (config gap)."""


# ── Value objects ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ExportOptions:
    """Already-resolved live Output settings (authority stays external).

    Field-for-field the canonical Output settings domain confirmed by the
    Phase F4 audit.  No new settings are introduced here.
    """

    save_folder: str = ""
    output_format: str = "original"
    quality: int = 75
    webp_lossless_compression: str = "balanced"
    save_metadata_sidecar: bool = True


@dataclass(frozen=True)
class ExportNamingContext:
    """Caller-supplied identity used for deterministic filenames/sidecars.

    ``output_index`` is the REAL logical-output index (fixing the legacy
    hardcode-everything-as-index-0 weakness).  Metadata fields are optional
    enrichment only; the service never invents values.
    """

    output_index: int = 0
    workflow_name: str = ""
    workflow_hash: str = ""
    preset_id: Optional[str] = None
    preset_name: Optional[str] = None
    seed: str = ""
    comfyui_root: str = _DEFAULT_COMFYUI_ROOT

    def __post_init__(self) -> None:
        if isinstance(self.output_index, bool) or not isinstance(
            self.output_index, int
        ) or self.output_index < 0:
            raise ValueError("output_index must be a non-negative integer")


@dataclass(frozen=True)
class ExportResult:
    """Structured outcome of one ``export_asset`` call."""

    status: str
    asset_id: str
    reason: Optional[str] = None
    message: Optional[str] = None
    saved: bool = False
    already_exported: bool = False
    state: str = ExportState.NOT_EXPORTED.value
    destination_path: str = ""
    metadata_path: str = ""
    byte_count: int = 0
    file_ext: str = ""
    mime_type: str = ""
    output_format: str = "original"
    quality: Optional[int] = None
    webp_lossless_compression: Optional[str] = None
    exported_at: Optional[str] = None
    partial: bool = False
    orphan_path: str = ""

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK


@dataclass(frozen=True)
class ExportStateView:
    """Lazily-classified export state for one asset."""

    asset_id: str
    state: str
    record: Optional[Any] = None
    destination_exists: Optional[bool] = None


ByteResolver = Callable[[Asset], Union[bytes, Awaitable[bytes]]]
Converter = Callable[..., dict]


# ── Service ───────────────────────────────────────────────────────────────


class HistoryV2ExportService:
    """Core History V2 configured-folder export engine (route-agnostic)."""

    def __init__(
        self,
        repository: Any,
        *,
        byte_resolver: Optional[ByteResolver] = None,
        converter: Optional[Converter] = None,
        clock: Callable[[], str] = utc_now_iso,
    ) -> None:
        self._repository = repository
        self._byte_resolver = byte_resolver
        self._converter = converter
        self._clock = clock

    # ── Public API ────────────────────────────────────────────────────

    async def export_asset(
        self,
        asset_id: str,
        options: ExportOptions,
        naming: Optional[ExportNamingContext] = None,
    ) -> ExportResult:
        """Export ONE selected managed asset per the resolved options."""
        naming = naming or ExportNamingContext()
        asset = self._load_asset(asset_id)
        if asset is None:
            return ExportResult(
                status=STATUS_ERROR,
                asset_id=asset_id,
                reason=REASON_ASSET_NOT_FOUND,
                message="asset not found in History V2 store",
            )

        record = self._get_record(asset_id)

        # Idempotency gate: exact same asset + same resolved destination
        # semantics + record says exported + file still present → reuse.
        if (
            record is not None
            and record.state == ExportState.EXPORTED.value
            and self._destination_matches(record, options, naming, asset)
        ):
            return ExportResult(
                status=STATUS_OK,
                asset_id=asset_id,
                saved=True,
                already_exported=True,
                state=ExportState.EXPORTED.value,
                destination_path=str(record.destination_path or ""),
                exported_at=record.exported_at,
                output_format=options.output_format,
                message="already exported; existing copy reused",
            )

        # Record says exported but the file vanished → truthful missing
        # classification BEFORE recovery, then fall through to re-export.
        if (
            record is not None
            and record.state == ExportState.EXPORTED.value
            and record.destination_path
            and not os.path.isfile(record.destination_path)
        ):
            self._mark_state(
                asset_id, ExportState.MISSING, destination_path=None
            )

        # ── Resolve source bytes ──────────────────────────────────────
        try:
            source_bytes = await self._resolve_bytes(asset)
        except _RemoteResolverUnavailable as exc:
            # Configuration gap, not a real export attempt: no record write.
            return ExportResult(
                status=STATUS_ERROR,
                asset_id=asset_id,
                reason=REASON_REMOTE_RESOLVER_UNAVAILABLE,
                message=str(exc),
                output_format=options.output_format,
            )
        except Exception as exc:
            return self._fail(
                asset_id,
                REASON_SOURCE_UNREADABLE,
                f"managed source unreadable: {exc}",
                options,
            )
        if not source_bytes:
            return self._fail(
                asset_id,
                REASON_SOURCE_UNREADABLE,
                "managed source is empty",
                options,
            )

        # ── Verify immutable identity (single hashing model: sha256) ──
        if asset.sha256:
            digest = hashlib.sha256(source_bytes).hexdigest()
            if digest != str(asset.sha256).lower():
                return self._fail(
                    asset_id,
                    REASON_HASH_MISMATCH,
                    "managed bytes do not match the immutable asset sha256",
                    options,
                )

        # ── Convert when required (fast path: original = byte-preserving)
        src_ext = self._source_ext(asset)
        mime_type = _MIME_BY_EXT.get(src_ext, "image/png")
        file_ext = src_ext
        out_bytes = source_bytes
        effective_quality: Optional[int] = None
        effective_webp: Optional[str] = None

        if options.output_format != "original":
            conv = self._run_converter(options)
            if conv is None:
                return self._fail(
                    asset_id,
                    REASON_CONVERSION_FAILED,
                    "output converter unavailable",
                    options,
                )
            try:
                converted = conv(
                    source_bytes,
                    output_format=options.output_format,
                    quality=options.quality,
                    webp_lossless_compression=options.webp_lossless_compression,
                )
            except Exception as exc:
                return self._fail(
                    asset_id,
                    REASON_CONVERSION_FAILED,
                    f"conversion failed: {exc}",
                    options,
                )
            if not isinstance(converted, dict):
                return self._fail(
                    asset_id,
                    REASON_CONVERSION_FAILED,
                    "converter returned an invalid result",
                    options,
                )
            if converted.get("fallback") or converted.get("error"):
                return self._fail(
                    asset_id,
                    REASON_CONVERSION_FAILED,
                    str(converted.get("error") or "conversion fell back"),
                    options,
                )
            payload = converted.get("bytes")
            if not isinstance(payload, bytes) or not payload:
                return self._fail(
                    asset_id,
                    REASON_CONVERSION_FAILED,
                    "converter produced no bytes",
                    options,
                )
            out_bytes = payload
            file_ext = str(converted.get("file_ext") or file_ext)
            mime_type = str(converted.get("mime_type") or mime_type)
            effective_quality = converted.get("quality")
            effective_webp = converted.get("webp_lossless_compression")

        # ── Write destination atomically ──────────────────────────────
        images_dir, metadata_dir, dir_error = self._prepare_dirs(options, naming)
        if dir_error:
            return self._fail(
                asset_id, REASON_WRITE_FAILED, dir_error, options
            )
        assert images_dir is not None
        destination = self._unique_destination(
            images_dir, options, naming, asset, file_ext
        )
        try:
            self._atomic_write(destination, out_bytes)
        except Exception as exc:
            return self._fail(
                asset_id,
                REASON_WRITE_FAILED,
                f"destination write failed: {exc}",
                options,
            )
        if not destination.is_file():
            return self._fail(
                asset_id,
                REASON_WRITE_FAILED,
                "destination did not persist",
                options,
            )

        # ── Sidecar (best-effort, canonical structure) ────────────────
        metadata_path = ""
        if options.save_metadata_sidecar and metadata_dir is not None:
            metadata_path = self._write_sidecar(
                metadata_dir=metadata_dir,
                images_dir=images_dir,
                destination=destination,
                options=options,
                naming=naming,
                asset=asset,
                file_ext=file_ext,
                mime_type=mime_type,
                effective_quality=effective_quality,
                effective_webp=effective_webp,
                source_size=len(source_bytes),
                out_size=len(out_bytes),
            )

        # ── Persist durable truth LAST ────────────────────────────────
        exported_at = self._clock()
        try:
            record = self._repository.upsert_export_record(
                asset_id,
                state=ExportState.EXPORTED.value,
                destination_path=str(destination),
                exported_at=exported_at,
            )
        except Exception as exc:
            orphan = self._cleanup_written(str(destination), metadata_path)
            return ExportResult(
                status=STATUS_ERROR,
                asset_id=asset_id,
                reason=REASON_RECORD_PERSIST_FAILED,
                message=f"file written but export record persist failed: {exc}",
                partial=True,
                destination_path=str(destination),
                metadata_path=metadata_path,
                byte_count=len(out_bytes),
                file_ext=file_ext,
                mime_type=mime_type,
                output_format=options.output_format,
                orphan_path=orphan,
            )

        return ExportResult(
            status=STATUS_OK,
            asset_id=asset_id,
            saved=True,
            state=ExportState.EXPORTED.value,
            destination_path=str(destination),
            metadata_path=metadata_path,
            byte_count=len(out_bytes),
            file_ext=file_ext,
            mime_type=mime_type,
            output_format=options.output_format,
            quality=effective_quality,
            webp_lossless_compression=effective_webp,
            exported_at=record.exported_at if record else exported_at,
        )

    def get_export_state(
        self, asset_id: str, *, persist_missing: bool = True
    ) -> ExportStateView:
        """Lazily classify export state for one asset (no filesystem scan).

        A recorded ``exported`` whose destination file no longer exists is
        classified (and by default persisted) as ``missing``.  Assets with
        no record are ``not_exported`` — including rerender successors,
        which never inherit a predecessor's export state.
        """
        record = self._get_record(asset_id)
        if record is None:
            return ExportStateView(
                asset_id=asset_id, state=ExportState.NOT_EXPORTED.value
            )
        if (
            record.state == ExportState.EXPORTED.value
            and record.destination_path
        ):
            if os.path.isfile(record.destination_path):
                return ExportStateView(
                    asset_id=asset_id,
                    state=ExportState.EXPORTED.value,
                    record=record,
                    destination_exists=True,
                )
            if persist_missing:
                self._mark_state(
                    asset_id, ExportState.MISSING, destination_path=None
                )
                record = self._get_record(asset_id) or record
            return ExportStateView(
                asset_id=asset_id,
                state=ExportState.MISSING.value,
                record=record,
                destination_exists=False,
            )
        return ExportStateView(
            asset_id=asset_id, state=record.state, record=record
        )

    # ── Internals ─────────────────────────────────────────────────────

    def _load_asset(self, asset_id: str) -> Optional[Asset]:
        return self._repository.get_asset(asset_id)

    def _get_record(self, asset_id: str) -> Optional[Any]:
        try:
            return self._repository.get_export_record(asset_id)
        except Exception:
            return None

    def _mark_state(
        self,
        asset_id: str,
        state: ExportState,
        *,
        destination_path: Optional[str],
    ) -> None:
        try:
            self._repository.upsert_export_record(
                asset_id, state=state.value, destination_path=destination_path
            )
        except Exception:
            pass

    def _fail(
        self,
        asset_id: str,
        reason: str,
        message: str,
        options: ExportOptions,
    ) -> ExportResult:
        """Truthful failed-attempt bookkeeping + error result.

        A real export attempt occurred (bytes were fetched/read), so the
        record becomes ``failed``.  No destination file exists — no false
        ``exported`` lie is ever written.
        """
        self._mark_state(
            asset_id, ExportState.FAILED, destination_path=None
        )
        return ExportResult(
            status=STATUS_ERROR,
            asset_id=asset_id,
            reason=reason,
            message=message,
            state=ExportState.FAILED.value,
            output_format=options.output_format,
        )

    async def _resolve_bytes(self, asset: Asset) -> bytes:
        managed_path = str(asset.managed_path or "")
        if managed_path.startswith("modal://"):
            if self._byte_resolver is None:
                raise _RemoteResolverUnavailable(
                    "remote modal:// asset requires an injected byte resolver"
                )
            resolved = self._byte_resolver(asset)
            if inspect.isawaitable(resolved):
                resolved = await resolved
            if not isinstance(resolved, (bytes, bytearray)):
                raise TypeError("resolver returned non-bytes payload")
            return bytes(resolved)
        path = Path(managed_path)
        return path.read_bytes()

    def _run_converter(self, options: ExportOptions) -> Optional[Converter]:
        if self._converter is not None:
            return self._converter
        try:
            from output_converter import convert_image_bytes
        except ImportError:
            return None
        return convert_image_bytes

    def _source_ext(self, asset: Asset) -> str:
        fmt = str(asset.format or "").strip().lower()
        if fmt in _SOURCE_EXT_BY_FORMAT:
            return _SOURCE_EXT_BY_FORMAT[fmt]
        suffix = Path(str(asset.managed_path or "")).suffix.lower()
        if suffix in _MIME_BY_EXT:
            return suffix
        return ".png"

    def _resolved_images_dir(
        self, options: ExportOptions, naming: ExportNamingContext
    ) -> str:
        comfyui_root = naming.comfyui_root or _DEFAULT_COMFYUI_ROOT
        return os.path.join(
            _resolve_save_folder(options.save_folder, comfyui_root), "images"
        )

    def _prepare_dirs(
        self, options: ExportOptions, naming: ExportNamingContext
    ) -> tuple[Optional[str], Optional[str], Optional[str]]:
        resolved_root = _resolve_save_folder(
            options.save_folder, naming.comfyui_root or _DEFAULT_COMFYUI_ROOT
        )
        images_dir = os.path.join(resolved_root, "images")
        metadata_dir = os.path.join(resolved_root, "metadata")
        if not _ensure_dir(images_dir):
            return None, None, f"cannot create directory: {images_dir}"
        if options.save_metadata_sidecar:
            _ensure_dir(metadata_dir)
        return images_dir, metadata_dir, None

    def _base_filename_stem(
        self, naming: ExportNamingContext, asset: Asset
    ) -> str:
        """Deterministic stem derived from ASSET identity, not wall clock.

        Uses the asset's own ``created_at`` so the same asset always maps to
        the same base name (required for idempotent reuse), while different
        assets/rerenders naturally differ.  The REAL logical-output index is
        encoded (never a hardcoded 0).
        """
        name_source = (
            naming.workflow_name
            or (naming.workflow_hash[:12] if naming.workflow_hash else "")
            or asset.generation_id
        )
        name = _sanitize(name_source)[:_MAX_NAME_COMPONENT]
        seed = _sanitize(str(naming.seed or "0"))
        date_str = _asset_created_at_stamp(asset, self._clock)
        return f"{date_str}_{name}_seed-{seed}_{int(naming.output_index)}"

    def _unique_destination(
        self,
        images_dir: str,
        options: ExportOptions,
        naming: ExportNamingContext,
        asset: Asset,
        file_ext: str,
    ) -> Path:
        stem = self._base_filename_stem(naming, asset)
        ext = file_ext if file_ext.startswith(".") else f".{file_ext}"
        filename = f"{stem}{ext}"
        unique = _unique_filename(images_dir, filename)
        final = Path(unique)
        # Hard containment invariant: sanitization removed every separator,
        # so the destination must sit exactly in the resolved images dir.
        assert final.parent == Path(images_dir), (
            "sanitized destination escaped the resolved images directory"
        )
        return final

    def _destination_matches(
        self,
        record: Any,
        options: ExportOptions,
        naming: ExportNamingContext,
        asset: Asset,
    ) -> bool:
        """Same resolved destination semantics as the current request?

        Folder change or target-extension change ⇒ NOT a hit (explicit
        export proceeds).  Quality-only changes cannot be detected from the
        frozen record schema and reuse the existing copy (documented).
        """
        destination = str(record.destination_path or "")
        if not destination or not os.path.isfile(destination):
            return False
        try:
            expected_dir = os.path.normcase(
                os.path.abspath(self._resolved_images_dir(options, naming))
            )
            actual_dir = os.path.normcase(
                os.path.abspath(os.path.dirname(destination))
            )
            if actual_dir != expected_dir:
                return False
            if options.output_format != "original":
                expected_ext = {
                    "webp_lossless": ".webp",
                    "webp_lossy": ".webp",
                    "jpeg": ".jpg",
                }.get(options.output_format)
                if expected_ext and not destination.lower().endswith(expected_ext):
                    return False
        except OSError:
            return False
        return True

    def _atomic_write(self, destination: Path, payload: bytes) -> None:
        tmp = destination.with_suffix(destination.suffix + ".tmp")
        with open(tmp, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, destination)

    def _write_sidecar(
        self,
        *,
        metadata_dir: str,
        images_dir: str,
        destination: Path,
        options: ExportOptions,
        naming: ExportNamingContext,
        asset: Asset,
        file_ext: str,
        mime_type: str,
        effective_quality: Optional[int],
        effective_webp: Optional[str],
        source_size: int,
        out_size: int,
    ) -> str:
        """Best-effort canonical sidecar carrying full History identity."""
        try:
            history_identity = {
                "history_v2": True,
                "exported_via": "history_v2_export",
                "generation_id": asset.generation_id,
                "run_id": asset.run_id,
                "asset_id": asset.asset_id,
                "variant": asset.type,
                "logical_output_key": asset.logical_output_key,
                "output_index": int(naming.output_index),
                "preset_id": naming.preset_id,
                "preset_name": naming.preset_name,
                "workflow_hash": naming.workflow_hash,
                "seed": str(naming.seed or "0"),
                "source_managed_path": asset.managed_path,
            }
            meta = _build_metadata_sidecar(
                created_at=self._clock(),
                workflow_hash=naming.workflow_hash,
                workflow_name=naming.workflow_name,
                seed=str(naming.seed or "0"),
                width=int(asset.width or 0),
                height=int(asset.height or 0),
                output_format=options.output_format,
                mime_type=mime_type,
                file_ext=file_ext,
                quality=effective_quality,
                webp_lossless_compression=effective_webp,
                image_path=str(destination),
                image_size_bytes=out_size,
                original_png_size_bytes_before_conversion=source_size,
                conversion_time_ms=0,
                saved_local=True,
            )
            meta.update(history_identity)
            stem = destination.name[: -len(destination.suffix)] or destination.name
            meta_filename = f"{stem}.json"
            meta_path = _unique_filename(metadata_dir, meta_filename)
            import json

            with open(meta_path, "w", encoding="utf-8") as handle:
                json.dump(meta, handle, indent=2, default=str)
            return meta_path
        except Exception:
            return ""

    @staticmethod
    def _cleanup_written(*written: str) -> str:
        """Remove written copies after a record-persist failure.

        Returns the first path that could NOT be removed (orphan), or "".
        """
        orphan = ""
        for path in written:
            if not path:
                continue
            try:
                os.unlink(path)
            except OSError:
                orphan = orphan or path
        return orphan


def _asset_created_at_stamp(asset: Asset, clock: Callable[[], str]) -> str:
    """``YYYY-MM-DD_HHMMSS`` stamp from the asset's own creation time."""
    from datetime import datetime

    raw = str(asset.created_at or "").replace("Z", "+00:00")
    try:
        moment = datetime.fromisoformat(raw)
        return moment.strftime("%Y-%m-%d_%H%M%S")
    except ValueError:
        # Undated asset: fall back to the current clock (still sanitized).
        raw = clock().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(raw).strftime("%Y-%m-%d_%H%M%S")
        except ValueError:
            return "undated"
