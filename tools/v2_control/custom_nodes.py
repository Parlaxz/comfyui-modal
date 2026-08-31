"""S2 custom-node publication identity, receipt, and skip control.

This module is deliberately host-side and standard-library-only.  The
publication policy remains owned by ``comfymodal_runtime.publication_policy``;
this module only turns that policy's semantic file set into one archive,
manifest, and identity.  Modal is imported only by the small volume adapter.
"""

from __future__ import annotations

import asyncio
import gzip
import hashlib
import inspect
import io
import json
import os
import stat
import tarfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from comfymodal_runtime.publication_policy import (
    CUSTOM_NODES_PUBLISHER_APP_NAME,
    CUSTOM_NODES_VOLUME_NAME,
    canonical_publication_bytes,
    publication_manifest_digest,
    is_excluded_path,
    iter_publication_files,
    iter_syncable_custom_node_dirs,
    resolve_custom_nodes_root,
)


IDENTITY_SCHEMA_VERSION = 2
RECEIPT_SCHEMA_VERSION = 2
PACKAGING_POLICY_VERSION = 1
PUBLICATION_PROTOCOL_VERSION = 2
GENERATION_RECORD_SCHEMA_VERSION = 2
PUBLISHER_MARKER = "comfyui-modal-golden"
RECEIPT_PATH = ".comfymodal_control/custom_nodes_publication_receipt.json"
GENERATION_RECORD_PATH = ".comfymodal_control/custom_nodes_generation.json"


class ReceiptError(ValueError):
    """A receipt cannot be trusted for an exact skip."""


@dataclass(frozen=True)
class SemanticFile:
    path: str
    size: int
    sha256: str
    data: bytes


@dataclass(frozen=True)
class CustomNodeSourceIdentity:
    content_generation: str
    identity_schema: int
    packaging_policy_version: int
    file_count: int
    total_bytes: int
    manifest_digest: str
    files: tuple[tuple[str, int, str], ...] = ()
    source_generation: str = ""

    @property
    def generation(self) -> str:
        """Compatibility view; publication code uses content_generation."""
        return self.content_generation

    @property
    def manifest(self) -> tuple[dict[str, Any], ...]:
        """The exact canonical manifest projection used for its digest."""
        return tuple(
            {"path": path, "size": size, "sha256": digest}
            for path, size, digest in self.files
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "content_generation": self.content_generation,
            "identity_schema": self.identity_schema,
            "packaging_policy_version": self.packaging_policy_version,
            "file_count": self.file_count,
            "total_bytes": self.total_bytes,
            "manifest_digest": self.manifest_digest,
            "source_generation": self.source_generation,
        }


@dataclass(frozen=True)
class PublicationReceipt:
    schema_version: int
    content_generation: str
    identity_schema: int
    packaging_policy_version: int
    publication_protocol_version: int
    state: str
    volume_name: str
    file_count: int
    total_bytes: int
    manifest_digest: str
    publisher: str
    ownership_marker: str
    integrity_digest: str
    created_at: str = ""

    @property
    def generation(self) -> str:
        """Compatibility view; receipt identity is content_generation."""
        return self.content_generation

    @property
    def bytes(self) -> int:
        return self.total_bytes

    def payload(self) -> dict[str, Any]:
        """Canonical receipt payload covered by ``integrity_digest``."""
        return {
            "schema_version": self.schema_version,
            "content_generation": self.content_generation,
            "identity_schema": self.identity_schema,
            "packaging_policy_version": self.packaging_policy_version,
            "publication_protocol_version": self.publication_protocol_version,
            "state": self.state,
            "volume_name": self.volume_name,
            "file_count": self.file_count,
            "bytes": self.total_bytes,
            "total_bytes": self.total_bytes,
            "manifest_digest": self.manifest_digest,
            "publisher": self.publisher,
            "ownership_marker": self.ownership_marker,
            "created_at": self.created_at,
        }

    def to_dict(self) -> dict[str, Any]:
        result = self.payload()
        result["integrity_digest"] = self.integrity_digest
        return result

    def to_bytes(self) -> bytes:
        return _canonical_json(self.to_dict())

    @classmethod
    def create(cls, identity: CustomNodeSourceIdentity, volume_name: str) -> "PublicationReceipt":
        receipt = cls(
            schema_version=RECEIPT_SCHEMA_VERSION,
            content_generation=identity.content_generation,
            identity_schema=identity.identity_schema,
            packaging_policy_version=identity.packaging_policy_version,
            publication_protocol_version=PUBLICATION_PROTOCOL_VERSION,
            state="verified",
            volume_name=str(volume_name),
            file_count=identity.file_count,
            total_bytes=identity.total_bytes,
            manifest_digest=identity.manifest_digest,
            publisher=PUBLISHER_MARKER,
            ownership_marker=PUBLISHER_MARKER,
            integrity_digest="",
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        return cls(**{**receipt.__dict__, "integrity_digest": _receipt_integrity(receipt)})

    @classmethod
    def from_bytes(cls, data: bytes) -> "PublicationReceipt":
        try:
            raw = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
            raise ReceiptError("malformed_receipt") from exc
        if not isinstance(raw, dict):
            raise ReceiptError("malformed_receipt")
        required = {
            "schema_version", "content_generation", "identity_schema",
            "packaging_policy_version", "publication_protocol_version", "state",
            "volume_name", "file_count", "bytes", "total_bytes", "manifest_digest",
            "publisher", "ownership_marker", "integrity_digest", "created_at",
        }
        if not required.issubset(raw):
            raise ReceiptError("malformed_receipt")
        try:
            receipt = cls(
                schema_version=raw["schema_version"],
                content_generation=raw["content_generation"],
                identity_schema=raw["identity_schema"],
                packaging_policy_version=raw["packaging_policy_version"],
                publication_protocol_version=raw["publication_protocol_version"],
                state=raw["state"], volume_name=raw["volume_name"],
                file_count=raw["file_count"], total_bytes=raw["total_bytes"],
                manifest_digest=raw["manifest_digest"], publisher=raw["publisher"],
                ownership_marker=raw["ownership_marker"],
                integrity_digest=raw["integrity_digest"], created_at=raw["created_at"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ReceiptError("malformed_receipt") from exc
        if type(receipt.schema_version) is not int or receipt.schema_version != RECEIPT_SCHEMA_VERSION:
            raise ReceiptError("schema_mismatch")
        if any(type(value) is not int for value in (
            receipt.identity_schema, receipt.packaging_policy_version,
            receipt.publication_protocol_version,
        )):
            raise ReceiptError("malformed_receipt")
        if receipt.publication_protocol_version != PUBLICATION_PROTOCOL_VERSION:
            raise ReceiptError("protocol_mismatch")
        if receipt.packaging_policy_version != PACKAGING_POLICY_VERSION:
            raise ReceiptError("policy_mismatch")
        if receipt.identity_schema != IDENTITY_SCHEMA_VERSION:
            raise ReceiptError("schema_mismatch")
        if receipt.state != "verified":
            raise ReceiptError("publication_incomplete")
        if "generation" in raw and raw["generation"] != receipt.content_generation:
            raise ReceiptError("schema_mismatch")
        if not all(isinstance(getattr(receipt, name), str) and getattr(receipt, name)
                   for name in ("content_generation", "volume_name", "manifest_digest", "publisher",
                                "ownership_marker", "integrity_digest")):
            raise ReceiptError("malformed_receipt")
        if type(receipt.file_count) is not int or type(receipt.total_bytes) is not int:
            raise ReceiptError("malformed_receipt")
        if raw.get("bytes") != receipt.total_bytes:
            raise ReceiptError("malformed_receipt")
        if _receipt_integrity(receipt) != receipt.integrity_digest:
            raise ReceiptError("integrity_mismatch")
        return receipt


@dataclass(frozen=True)
class PublicationDecision:
    action: str
    reason: str
    identity: CustomNodeSourceIdentity
    receipt: PublicationReceipt | None = None
    result: Any = None
    schema_version: int = RECEIPT_SCHEMA_VERSION
    publication_protocol_version: int = PUBLICATION_PROTOCOL_VERSION

    @property
    def skip(self) -> bool:
        return self.action == "skip"


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _receipt_integrity(receipt: PublicationReceipt) -> str:
    return hashlib.sha256(_canonical_json(receipt.payload())).hexdigest()


def _is_control_metadata(relative_path: str) -> bool:
    # Both names are already policy exclusions in the current policy.  The
    # explicit path guard keeps this S2 receipt safe if a future policy adds a
    # broader control directory without changing the source contract.
    normalized = relative_path.replace("\\", "/")
    return normalized in {RECEIPT_PATH, "custom_nodes_generation.json"} or normalized.startswith(
        ".comfymodal_control/"
    )


def collect_semantic_files(root: str | Path) -> tuple[SemanticFile, ...]:
    """Collect the canonical publication set exactly once, deterministically."""
    raw_root = Path(root).expanduser()
    try:
        raw_root_stat = raw_root.lstat()
    except OSError as exc:
        raise OSError(f"custom-node source root is unreadable: {raw_root}") from exc
    if stat.S_ISLNK(raw_root_stat.st_mode):
        raise ValueError(f"symlink is not a publishable source root: {raw_root}")
    root_path = raw_root.resolve(strict=False)
    try:
        root_stat = root_path.lstat()
    except OSError as exc:
        raise OSError(f"custom-node source root is unreadable: {root_path}") from exc
    if not stat.S_ISDIR(root_stat.st_mode) or stat.S_ISLNK(root_stat.st_mode):
        raise ValueError(f"custom-node source root is not a directory: {root_path}")

    # Validate root-level links/special entries before policy can filter them
    # out as non-node content.  Regular files at this level are allowed (and
    # simply are not syncable top-level nodes).
    for entry in os.scandir(root_path):
        try:
            entry_stat = entry.stat(follow_symlinks=False)
        except OSError as exc:
            raise OSError(f"custom-node tree entry is unreadable: {entry.path}") from exc
        if stat.S_ISLNK(entry_stat.st_mode):
            raise ValueError(f"symlink is not publishable: {entry.path}")
        if not stat.S_ISDIR(entry_stat.st_mode) and not stat.S_ISREG(entry_stat.st_mode):
            raise ValueError(f"special file is not publishable: {entry.path}")

    files: list[SemanticFile] = []
    for path in iter_publication_files(root_path):
        relative = path.relative_to(root_path).as_posix()
        data = canonical_publication_bytes(relative, path.read_bytes())
        files.append(SemanticFile(relative, len(data), hashlib.sha256(data).hexdigest(), data))
    return tuple(sorted(files, key=lambda item: item.path))


def _manifest(files: Iterable[SemanticFile]) -> tuple[list[dict[str, Any]], str, int]:
    entries = [{"path": item.path, "size": item.size, "sha256": item.sha256} for item in files]
    return entries, publication_manifest_digest(entries), sum(item.size for item in files)


def build_source_identity(
    root: str | Path,
    *,
    semantic_files: tuple[SemanticFile, ...] | None = None,
    identity_provider: Callable[..., Any] | None = None,
) -> CustomNodeSourceIdentity:
    files = semantic_files if semantic_files is not None else collect_semantic_files(root)
    entries, manifest_digest, total_bytes = _manifest(files)
    # Adapter-shaped integration point for S1's canonical provider.  The
    # provider is passed the already-collected semantic set when it accepts a
    # second argument, so callers need not walk the tree twice.
    provided = None
    if identity_provider is not None:
        try:
            parameters = tuple(inspect.signature(identity_provider).parameters.values())
            variadic = any(
                parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD)
                for parameter in parameters
            )
            positional_count = sum(
                parameter.kind in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD)
                for parameter in parameters
            )
        except (TypeError, ValueError):
            variadic, positional_count = True, 3
        if variadic or positional_count >= 3:
            provided = identity_provider(root, files, entries)
        elif positional_count >= 2:
            provided = identity_provider(root, files)
        else:
            provided = identity_provider(root)
    source_generation = str(
        provided.get("generation") if isinstance(provided, Mapping) else provided or ""
    ).strip()
    # Publication generation is the manifest digest, not the narrower S1 code
    # hash supplied by the optional adapter.  Keep that adapter value separate
    # for diagnostics/consumers that still need a source-only identity.
    content_generation = manifest_digest
    return CustomNodeSourceIdentity(
        content_generation=content_generation,
        identity_schema=IDENTITY_SCHEMA_VERSION,
        packaging_policy_version=PACKAGING_POLICY_VERSION,
        file_count=len(entries), total_bytes=total_bytes,
        manifest_digest=manifest_digest,
        files=tuple((item.path, item.size, item.sha256) for item in files),
        source_generation=source_generation,
    )


def build_archive(files: tuple[SemanticFile, ...]) -> bytes:
    """Build a reproducible archive from the exact identity file set."""
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode="wb", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as archive:
            for item in files:
                info = tarfile.TarInfo(item.path)
                info.size = item.size
                info.mtime = 0
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                info.mode = 0o644
                archive.addfile(info, io.BytesIO(item.data))
    return output.getvalue()


def prepare_publication(root: str | Path, *, identity_provider: Callable[..., Any] | None = None):
    files = collect_semantic_files(root)
    identity = build_source_identity(root, semantic_files=files, identity_provider=identity_provider)
    return identity, build_archive(files), files


def _read_volume_file(volume: Any, path: str) -> bytes:
    chunks = volume.read_file(path)
    if inspect.isawaitable(chunks) or hasattr(chunks, "__aiter__"):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(_read_volume_file_async_result(chunks))
        raise RuntimeError("async Volume.read_file requires the async publication path")
    return b"".join(chunks)


async def _read_volume_file_async_result(chunks: Any) -> bytes:
    if inspect.isawaitable(chunks):
        chunks = await chunks
    if hasattr(chunks, "__aiter__"):
        result = bytearray()
        async for chunk in chunks:
            result.extend(chunk)
        return bytes(result)
    return b"".join(chunks)


async def _read_volume_file_async(volume: Any, path: str) -> bytes:
    # Modal 1.4.x exposes both a blocking interface and an ``.aio`` interface
    # on live methods.  Calling the former from this coroutine emits
    # AsyncUsageWarning and can leave the readback untrusted.  Local fakes may
    # only expose the plain method, so retain that narrow compatibility path.
    method = volume.read_file
    aio_method = getattr(method, "aio", None)
    chunks = aio_method(path) if callable(aio_method) else method(path)
    return await _read_volume_file_async_result(chunks)


def get_volume(
    volume_name: str,
    volume_factory: Callable[[str], Any] | None = None,
    *,
    workspace: Mapping[str, object] | None = None,
) -> Any:
    """Return a named Volume, using explicit workspace credentials when given.

    ``volume_factory`` remains the first-class injection point for local tests
    and callers that already own a Volume.  The Modal import stays lazy so
    identity and dry-run paths do not require the SDK.
    """
    if volume_factory is not None:
        return volume_factory(volume_name)
    import modal  # lazy: dry-run and local identity tests must not import Modal
    if workspace is None:
        return modal.Volume.from_name(volume_name)
    client = modal.Client.from_credentials(
        str(workspace["token_id"]), str(workspace["token_secret"])
    )
    return modal.Volume.from_name(volume_name, client=client)


def read_receipt(volume: Any, *, volume_name: str, path: str = RECEIPT_PATH) -> PublicationReceipt:
    try:
        data = _read_volume_file(volume, path)
    except FileNotFoundError as exc:
        raise ReceiptError("missing_receipt") from exc
    # Empty data is a malformed receipt, not proof that the receipt is absent.
    receipt = PublicationReceipt.from_bytes(data)
    if receipt.volume_name != volume_name:
        raise ReceiptError("volume_mismatch")
    return receipt


async def read_receipt_async(
    volume: Any, *, volume_name: str, path: str = RECEIPT_PATH
) -> PublicationReceipt:
    try:
        data = await _read_volume_file_async(volume, path)
    except FileNotFoundError as exc:
        raise ReceiptError("missing_receipt") from exc
    # Empty data is a malformed receipt, not proof that the receipt is absent.
    receipt = PublicationReceipt.from_bytes(data)
    if receipt.volume_name != volume_name:
        raise ReceiptError("volume_mismatch")
    return receipt


def evaluate_receipt(
    raw_receipt: PublicationReceipt | bytes | None,
    desired: CustomNodeSourceIdentity,
    *,
    volume_name: str,
    repair_requested: bool = False,
) -> PublicationDecision:
    def fail(reason: str, receipt: PublicationReceipt | None = None) -> PublicationDecision:
        return PublicationDecision("publish", reason, desired, receipt)
    if repair_requested:
        return fail("repair_requested")
    if raw_receipt is None:
        return fail("missing_receipt")
    try:
        receipt = raw_receipt if isinstance(raw_receipt, PublicationReceipt) else PublicationReceipt.from_bytes(raw_receipt)
        if receipt.volume_name != volume_name:
            return fail("volume_mismatch", receipt)
        if receipt.schema_version != RECEIPT_SCHEMA_VERSION or receipt.identity_schema != IDENTITY_SCHEMA_VERSION:
            return fail("schema_mismatch", receipt)
        if receipt.packaging_policy_version != PACKAGING_POLICY_VERSION:
            return fail("policy_mismatch", receipt)
        if receipt.publication_protocol_version != PUBLICATION_PROTOCOL_VERSION:
            return fail("protocol_mismatch", receipt)
        if receipt.state != "verified":
            return fail("publication_incomplete", receipt)
        if receipt.publisher != PUBLISHER_MARKER or receipt.ownership_marker != PUBLISHER_MARKER:
            return fail("ownership_unproven", receipt)
        if _receipt_integrity(receipt) != receipt.integrity_digest:
            return fail("integrity_mismatch", receipt)
        if (receipt.content_generation != desired.content_generation or receipt.file_count != desired.file_count
                or receipt.total_bytes != desired.total_bytes
                or receipt.manifest_digest != desired.manifest_digest):
            return fail("generation_mismatch", receipt)
        return PublicationDecision("skip", "exact_match", desired, receipt)
    except ReceiptError as exc:
        return fail(str(exc))
    except Exception:
        return fail("malformed_receipt")


def _content_generation_from_record(data: bytes) -> str | None:
    try:
        raw = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(raw, dict):
        return None
    if raw.get("schema_version") != GENERATION_RECORD_SCHEMA_VERSION:
        return None
    value = raw.get("content_generation")
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        return None
    # A compatibility echo is harmless only when it cannot disagree with the
    # canonical field.  Schema-1 generation-only records are rejected above.
    if "generation" in raw and raw.get("generation") != value:
        return None
    return value.strip()


def _content_generation_readback(volume: Any) -> str | None:
    try:
        return _content_generation_from_record(
            _read_volume_file(volume, GENERATION_RECORD_PATH)
        )
    except Exception:
        return None


async def _content_generation_readback_async(volume: Any) -> str | None:
    try:
        return _content_generation_from_record(
            await _read_volume_file_async(volume, GENERATION_RECORD_PATH)
        )
    except Exception:
        return None


def _is_host_modal_volume(volume: Any) -> bool:
    """Identify a real host-side Modal Volume without importing Modal eagerly."""
    volume_type = type(volume)
    return (
        volume_type.__module__ == "modal.volume"
        and volume_type.__name__ == "Volume"
        and os.environ.get("MODAL_IS_REMOTE") != "1"
    )


async def _refresh_volume_async(volume: Any) -> Any:
    """Optionally refresh an injected/container-side Volume handle.

    ``Volume.reload`` is a container-only operation.  On the host control
    plane, direct ``Volume.read_file`` calls already read committed state and
    ``reload().aio()`` raises because there is no running Modal function.
    Small local fakes and container-compatible handles may still provide a
    reload/reopen operation, so retain that compatibility path when the
    handle is not a real host-side Modal Volume.
    """
    if _is_host_modal_volume(volume):
        return volume
    method = getattr(volume, "reload", None)
    if not callable(method):
        method = getattr(volume, "reopen", None)
    if not callable(method):
        return volume
    aio_method = getattr(method, "aio", None)
    if callable(aio_method):
        refreshed = aio_method()
    else:
        # Modal's plain reload/reopen wrappers are synchronous.  Never invoke
        # them on the event-loop thread, even when a local/injected Volume
        # exposes only that compatibility interface.
        refreshed = await asyncio.to_thread(method)
    if inspect.isawaitable(refreshed):
        refreshed = await refreshed
    return refreshed if refreshed is not None else volume


def write_receipt(volume: Any, receipt: PublicationReceipt, *, path: str = RECEIPT_PATH) -> None:
    with volume.batch_upload(force=True) as batch:
        batch.put_file(io.BytesIO(receipt.to_bytes()), path)


async def write_receipt_async(
    volume: Any, receipt: PublicationReceipt, *, path: str = RECEIPT_PATH
) -> None:
    """Write a receipt using Modal 1.4.3's async batch-upload contract.

    The synchronous branch is only a compatibility adapter for small local
    fakes and older injected Volume doubles.  Real Modal Volumes take the
    async-context-manager branch.
    """
    method = volume.batch_upload
    aio_method = getattr(method, "aio", None)
    batch: Any = aio_method(force=True) if callable(aio_method) else method(force=True)
    if inspect.isawaitable(batch):
        batch = await batch
    if hasattr(batch, "__aenter__"):
        async with batch as upload:
            result = upload.put_file(io.BytesIO(receipt.to_bytes()), path)
            if inspect.isawaitable(result):
                await result
        return
    # Keep the test/dry-run compatibility surface narrow and explicit.
    write_receipt(volume, receipt, path=path)


async def publish_or_skip(
    root: str | Path,
    *,
    volume_name: str,
    publisher: Callable[[bytes], Any],
    volume: Any | None = None,
    volume_factory: Callable[[str], Any] | None = None,
    workspace: Mapping[str, object] | None = None,
    identity_provider: Callable[..., Any] | None = None,
    repair_requested: bool = False,
) -> PublicationDecision:
    # Inspect the tiny receipt before constructing the archive.  Exact skips
    # therefore perform no tar/gzip work and do not invoke the publisher.
    files = collect_semantic_files(root)
    identity = build_source_identity(
        root, semantic_files=files, identity_provider=identity_provider
    )
    if volume is None:
        # Volume.from_name and Client.from_credentials are synchronous in
        # Modal 1.4.3.  Construct the handle off the event-loop thread; the
        # handle's subsequent reads/uploads use the native ``.aio`` methods.
        factory = volume_factory
        if factory is None:
            volume = await asyncio.to_thread(get_volume, volume_name, workspace=workspace)
        else:
            volume = await asyncio.to_thread(factory, volume_name)
            if inspect.isawaitable(volume):
                volume = await volume
    volume_refresh_ok = True
    try:
        volume = await _refresh_volume_async(volume)
        existing = await read_receipt_async(volume, volume_name=volume_name)
        decision = evaluate_receipt(existing, identity, volume_name=volume_name,
                                    repair_requested=repair_requested)
    except ReceiptError as exc:
        decision = PublicationDecision("publish", str(exc), identity)
    except Exception:
        # A refresh/read failure must never become an exact skip.
        volume_refresh_ok = False
        decision = PublicationDecision("publish", "volume_readback_failed", identity)
    if decision.skip:
        return decision

    # A content publication can succeed while its receipt write is lost (or a
    # previous receipt can become stale).  The content-generation record is
    # written by
    # the remote publisher before its content commit and is therefore the
    # authoritative, tiny proof that the Volume already contains this exact
    # source content generation.  Recovering only the receipt avoids rebuilding and
    # re-uploading content.  Any read/parse ambiguity returns None and remains
    # on the normal fail-closed publication path.
    content_generation_matches = (
        volume_refresh_ok
        and not repair_requested
        and await _content_generation_readback_async(volume) == identity.content_generation
    )
    if content_generation_matches:
        recovered = PublicationReceipt.create(identity, volume_name)
        try:
            await write_receipt_async(volume, recovered)
            trusted = evaluate_receipt(
                await read_receipt_async(volume, volume_name=volume_name), identity,
                volume_name=volume_name,
            )
        except Exception:
            return PublicationDecision(
                "publish", "receipt_recovery_failed", identity,
            )
        if trusted is not None and trusted.skip:
            return PublicationDecision(
                "recovered", "receipt_only_generation_match", identity,
                trusted.receipt,
            )
        return PublicationDecision("publish", "receipt_recovery_failed", identity)

    archive = build_archive(files)
    result = publisher(archive)
    if inspect.isawaitable(result):
        result = await result
    if not isinstance(result, Mapping) or str(result.get("status", "")).lower() not in {"ok", "success", "verified"}:
        return PublicationDecision("publish", "publication_incomplete", identity, result=result)
    result_value = result.get("content_generation") if isinstance(result, Mapping) else None
    result_content_generation = (
        result_value
        if isinstance(result_value, str)
        and result_value
        and result_value == result_value.strip()
        and ("generation" not in result or result.get("generation") == result_value)
        else ""
    )
    # Read the committed record directly.  Host-side Modal Volume.read_file is
    # the authoritative readback; reloading here is container-only and can
    # raise before the generation proof is available.
    readback_content_generation = await _content_generation_readback_async(volume)
    # Both the explicit publisher result and persisted record are required.
    if (
        result_content_generation != identity.content_generation
        or readback_content_generation != identity.content_generation
    ):
        return PublicationDecision("publish", "publication_incomplete", identity, result=result)
    receipt = PublicationReceipt.create(identity, volume_name)
    try:
        await write_receipt_async(volume, receipt)
        trusted = evaluate_receipt(
            await read_receipt_async(volume, volume_name=volume_name), identity,
            volume_name=volume_name,
        )
    except Exception:
        return PublicationDecision("publish", "publication_incomplete", identity, result=result)
    if not trusted.skip:
        return PublicationDecision("publish", "publication_incomplete", identity, trusted.receipt, result)
    return PublicationDecision("published", "published_verified", identity, trusted.receipt, result)


def run_publish_or_skip(*args: Any, **kwargs: Any) -> PublicationDecision:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(publish_or_skip(*args, **kwargs))
    raise RuntimeError("publish_or_skip is async; await it from a running event loop")


__all__ = [
    "CustomNodeSourceIdentity", "PublicationReceipt", "PublicationDecision",
    "SemanticFile", "ReceiptError", "IDENTITY_SCHEMA_VERSION",
    "RECEIPT_SCHEMA_VERSION", "PACKAGING_POLICY_VERSION",
    "PUBLICATION_PROTOCOL_VERSION", "GENERATION_RECORD_SCHEMA_VERSION",
    "RECEIPT_PATH", "GENERATION_RECORD_PATH",
    "CUSTOM_NODES_VOLUME_NAME", "CUSTOM_NODES_PUBLISHER_APP_NAME",
    "collect_semantic_files", "build_source_identity", "build_archive",
    "prepare_publication", "evaluate_receipt", "read_receipt", "read_receipt_async",
    "write_receipt", "write_receipt_async",
    "publish_or_skip", "run_publish_or_skip", "get_volume", "resolve_custom_nodes_root",
]
