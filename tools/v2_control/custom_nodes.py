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
from dataclasses import dataclass, field
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
CANDIDATE_READBACK_SAMPLE_SIZE = 128
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
    mode: int = 0o644
    source_data: bytes | None = None


@dataclass(frozen=True)
class PackagePublicationManifest:
    """The canonical publication evidence for one top-level package."""

    name: str
    file_count: int
    total_bytes: int
    content_digest: str
    path_list: tuple[str, ...]
    path_digest: str
    source_root: str = ""
    first_party: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "file_count": self.file_count,
            "bytes": self.total_bytes,
            "total_bytes": self.total_bytes,
            "content_digest": self.content_digest,
            "path_list": list(self.path_list),
            "path_digest": self.path_digest,
            "source_root": self.source_root,
            "first_party": self.first_party,
        }


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
    source_root: str = ""
    package_manifests: tuple[PackagePublicationManifest, ...] = ()

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
            "source_root": self.source_root,
            "packages": [item.to_dict() for item in self.package_manifests],
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
    source_root: str = ""
    package_manifests: tuple[dict[str, Any], ...] = ()
    destructive_override: bool = False
    destructive_delta: dict[str, Any] = field(default_factory=dict)

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
            "source_root": self.source_root,
            "packages": [dict(item) for item in self.package_manifests],
            "destructive_override": self.destructive_override,
            "destructive_delta": dict(self.destructive_delta),
        }

    def to_dict(self) -> dict[str, Any]:
        result = self.payload()
        result["integrity_digest"] = self.integrity_digest
        return result

    def to_bytes(self) -> bytes:
        return _canonical_json(self.to_dict())

    @classmethod
    def create(
        cls,
        identity: CustomNodeSourceIdentity,
        volume_name: str,
        *,
        destructive_override: bool = False,
        destructive_delta: Mapping[str, Any] | None = None,
    ) -> "PublicationReceipt":
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
            source_root=identity.source_root,
            package_manifests=tuple(item.to_dict() for item in identity.package_manifests),
            destructive_override=bool(destructive_override),
            destructive_delta=dict(destructive_delta or {}),
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
                source_root=str(raw.get("source_root") or ""),
                package_manifests=tuple(raw.get("packages") or ()),
                destructive_override=bool(raw.get("destructive_override", False)),
                destructive_delta=dict(raw.get("destructive_delta") or {}),
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
    destructive_delta: dict[str, Any] = field(default_factory=dict)
    destructive_override: bool = False

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
        source_data = path.read_bytes()
        data = canonical_publication_bytes(relative, source_data)
        mode = stat.S_IMODE(path.stat(follow_symlinks=False).st_mode)
        files.append(SemanticFile(
            relative,
            len(data),
            hashlib.sha256(data).hexdigest(),
            data,
            mode=mode,
            source_data=source_data,
        ))
    return tuple(sorted(files, key=lambda item: item.path))


def _manifest(files: Iterable[SemanticFile]) -> tuple[list[dict[str, Any]], str, int]:
    entries = [{"path": item.path, "size": item.size, "sha256": item.sha256} for item in files]
    return entries, publication_manifest_digest(entries), sum(item.size for item in files)


def _path_digest(paths: Iterable[str]) -> str:
    return hashlib.sha256(_canonical_json(sorted(str(path) for path in paths))).hexdigest()


def _is_first_party_package(root: Path, name: str) -> bool:
    """Identify comfyui-modal from source identity, not worktree dirtiness."""
    if name.casefold() != "comfyui-modal":
        return False
    package = root / name
    return (
        (package / ".git").exists()
        or (package / "comfyapp.py").is_file()
        and (package / "comfymodal_runtime" / "modal_app.py").is_file()
    )


def _package_manifests(
    root: str | Path,
    files: tuple[SemanticFile, ...],
) -> tuple[PackagePublicationManifest, ...]:
    root_path = Path(root).resolve()
    grouped: dict[str, list[SemanticFile]] = {}
    for item in files:
        package, _, _relative = item.path.partition("/")
        grouped.setdefault(package, []).append(item)
    result: list[PackagePublicationManifest] = []
    for name in sorted(grouped):
        package_files = sorted(grouped[name], key=lambda item: item.path)
        entries = [
            {
                "path": item.path,
                "size": item.size,
                "sha256": item.sha256,
            }
            for item in package_files
        ]
        paths = tuple(item.path for item in package_files)
        content_digest = publication_manifest_digest(entries)
        result.append(PackagePublicationManifest(
            name=name,
            file_count=len(package_files),
            total_bytes=sum(item.size for item in package_files),
            content_digest=content_digest,
            path_list=paths,
            path_digest=_path_digest(paths),
            source_root=str(root_path),
            first_party=_is_first_party_package(root_path, name),
        ))
    return tuple(result)


def _manifest_map(value: Any) -> dict[str, dict[str, Any]]:
    if isinstance(value, PublicationReceipt):
        raw = value.package_manifests
    elif isinstance(value, CustomNodeSourceIdentity):
        raw = value.package_manifests
    elif isinstance(value, Mapping):
        raw = value.get("packages", value.get("package_manifests", ()))
    else:
        raw = ()
    result: dict[str, dict[str, Any]] = {}
    for item in raw or ():
        data = item.to_dict() if isinstance(item, PackagePublicationManifest) else dict(item)
        name = str(data.get("name") or "")
        if name:
            result[name] = data
    return result


def publication_safety_delta(
    previous: PublicationReceipt | Mapping[str, Any] | None,
    desired: CustomNodeSourceIdentity,
) -> dict[str, Any]:
    """Return external-package file-loss evidence before any remote mutation."""
    previous_packages = _manifest_map(previous)
    desired_packages = _manifest_map(desired)
    blocked: list[dict[str, Any]] = []
    if not previous_packages and isinstance(previous, PublicationReceipt) and previous.file_count:
        blocked.append({
            "package": "<unavailable>",
            "reason": "previous_package_manifest_missing",
            "prev_files": previous.file_count,
            "cand_files": desired.file_count,
            "prev_bytes": previous.total_bytes,
            "cand_bytes": desired.total_bytes,
            "missing_paths": [],
            "missing_count": previous.file_count,
            "prev_digest": previous.manifest_digest,
            "cand_digest": desired.manifest_digest,
        })
    for name, previous_item in sorted(previous_packages.items()):
        prev_files = int(previous_item.get("file_count", 0) or 0)
        if prev_files <= 0 or name.casefold() == "comfyui-modal" or previous_item.get("first_party"):
            continue
        candidate = desired_packages.get(name)
        prev_paths = set(str(path) for path in previous_item.get("path_list", ()) or ())
        cand_paths = set(str(path) for path in (candidate or {}).get("path_list", ()) or ())
        missing = sorted(prev_paths - cand_paths)
        cand_files = int((candidate or {}).get("file_count", 0) or 0)
        if candidate is None or cand_files == 0 or missing:
            blocked.append({
                "package": name,
                "prev_files": prev_files,
                "cand_files": cand_files,
                "prev_bytes": int(previous_item.get("total_bytes", previous_item.get("bytes", 0)) or 0),
                "cand_bytes": int((candidate or {}).get("total_bytes", (candidate or {}).get("bytes", 0)) or 0),
                "missing_paths": missing,
                "missing_count": len(missing) if missing else prev_files,
                "prev_digest": str(previous_item.get("content_digest", "")),
                "cand_digest": str((candidate or {}).get("content_digest", "")),
            })
    return {
        "blocked": bool(blocked),
        "packages": blocked,
        "previous_generation": (
            previous.content_generation if isinstance(previous, PublicationReceipt)
            else str((previous or {}).get("content_generation", ""))
        ),
        "candidate_generation": desired.content_generation,
    }


def check_publication_safety(
    previous: PublicationReceipt | Mapping[str, Any] | None,
    desired: CustomNodeSourceIdentity,
    *,
    allow_destructive: bool = False,
) -> dict[str, Any]:
    delta = publication_safety_delta(previous, desired)
    delta["override_allowed"] = bool(allow_destructive)
    delta["allowed"] = not delta["blocked"] or bool(allow_destructive)
    return delta


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
        source_root=str(Path(root).resolve()),
        package_manifests=_package_manifests(root, files),
    )


def build_archive(files: tuple[SemanticFile, ...]) -> bytes:
    """Build a reproducible archive from the exact identity file set."""
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode="wb", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as archive:
            for item in sorted(files, key=lambda item: item.path):
                normalized_path = item.path.replace("\\", "/")
                parts = normalized_path.split("/")
                if (
                    not normalized_path
                    or normalized_path.startswith("/")
                    or normalized_path.startswith("//")
                    or (len(normalized_path) >= 2 and normalized_path[1] == ":")
                    or normalized_path != item.path
                    or "\x00" in normalized_path
                    or any(part in ("", ".", "..") for part in parts)
                ):
                    raise ValueError(f"unsafe archive member path: {item.path!r}")
                info = tarfile.TarInfo(normalized_path)
                payload = item.source_data if item.source_data is not None else item.data
                info.size = len(payload)
                info.mtime = 0
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                info.mode = stat.S_IMODE(item.mode)
                archive.addfile(info, io.BytesIO(payload))
    return output.getvalue()


def archive_content_digest(files: tuple[SemanticFile, ...]) -> str:
    """Return a stable cache key for archive bytes without rebuilding them."""
    digest = hashlib.sha256()
    for item in sorted(files, key=lambda item: item.path):
        payload = item.source_data if item.source_data is not None else item.data
        digest.update(item.path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(stat.S_IMODE(item.mode)).encode("ascii"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(payload).digest())
        digest.update(b"\0")
    return digest.hexdigest()


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
    kwargs: dict[str, Any] = {"client": client}
    environment = str(workspace.get("environment") or "(default)").strip()
    if environment != "(default)":
        kwargs["environment_name"] = environment
    return modal.Volume.from_name(volume_name, **kwargs)


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


async def _remote_content_mismatch(
    volume: Any,
    previous: PublicationReceipt | None,
    desired: CustomNodeSourceIdentity,
) -> str | None:
    """Verify the file-level content represented by the publication manifests.

    The generation record authenticates the candidate generation, but it does
    not prove that a failed replacement removed files from the shared Volume.
    Read every old path that should have disappeared.  Candidate content is
    checked using a deterministic path-hash sample so publish cost is bounded;
    the sample proves those candidate files, not every candidate file.
    """
    previous_packages = _manifest_map(previous)
    desired_packages = _manifest_map(desired)
    if previous is not None and previous.file_count and not previous_packages:
        return "previous package manifest unavailable"
    for name, package in previous_packages.items():
        raw_paths = package.get("path_list")
        file_count = int(package.get("file_count", 0) or 0)
        if file_count and (
            not isinstance(raw_paths, (list, tuple)) or len(raw_paths) != file_count
        ):
            return f"previous package manifest unavailable: {name}"

    previous_paths = {
        str(path)
        for package in previous_packages.values()
        for path in package.get("path_list", ()) or ()
    }
    desired_paths = {
        str(path)
        for package in desired_packages.values()
        for path in package.get("path_list", ()) or ()
    }
    for path in sorted(previous_paths - desired_paths):
        try:
            await _read_volume_file_async(volume, path)
        except FileNotFoundError:
            continue
        except Exception as exc:  # noqa: BLE001 - remote readback is fail-closed
            return f"unable to verify removed remote path {path}: {type(exc).__name__}"
        return f"stale remote path remains: {path}"

    candidate_by_path = {
        path: (size, digest) for path, size, digest in desired.files
    }
    candidate_readback_paths = sorted(
        candidate_by_path,
        key=lambda path: (hashlib.sha256(path.encode("utf-8")).digest(), path),
    )[:CANDIDATE_READBACK_SAMPLE_SIZE]
    for path in sorted(candidate_readback_paths):
        expected_size, expected_digest = candidate_by_path[path]
        try:
            data = await _read_volume_file_async(volume, path)
        except FileNotFoundError:
            return f"candidate package path is missing remotely: {path}"
        except Exception as exc:  # noqa: BLE001 - remote readback is fail-closed
            return f"unable to read candidate remote path {path}: {type(exc).__name__}"
        actual_digest = hashlib.sha256(data).hexdigest()
        if len(data) != expected_size or actual_digest != expected_digest:
            return f"candidate remote content differs: {path}"
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
    allow_destructive: bool = False,
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
    verified_previous: PublicationReceipt | None = None
    try:
        volume = await _refresh_volume_async(volume)
        existing = await read_receipt_async(volume, volume_name=volume_name)
        verified_previous = existing
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

    # Destructive-publication guard: compare the candidate identity against
    # the last verified remote receipt BEFORE any remote deletion/replacement
    # (the remote publisher deletes the prior tree on commit).  A missing or
    # unreadable receipt is not authority for a block; only a verified remote
    # receipt is.  Fail-closed: on block, return without invoking the
    # publisher, writing a receipt/generation, or mutating the remote.
    safety = check_publication_safety(
        verified_previous, identity, allow_destructive=allow_destructive
    )
    if safety["blocked"] and not safety["allowed"]:
        print(
            "[custom_nodes.publish] decision=blocked "
            "reason=destructive_custom_node_publication_blocked "
            f"previous_generation={str(safety['previous_generation'])[:16] or '(none)'} "
            f"candidate_generation={str(safety['candidate_generation'])[:16] or '(none)'} "
            f"packages={len(safety['packages'])}"
        )
        for entry in safety["packages"]:
            print(
                "[custom_nodes.publish] blocked_package "
                f"package={entry['package']} "
                f"prev_files={entry['prev_files']} cand_files={entry['cand_files']} "
                f"prev_bytes={entry['prev_bytes']} cand_bytes={entry['cand_bytes']} "
                f"missing_count={entry['missing_count']} "
                f"prev_digest={str(entry['prev_digest'])[:16] or '(none)'} "
                f"cand_digest={str(entry['cand_digest'])[:16] or '(none)'}"
            )
            for missing in entry["missing_paths"][:20]:
                print(f"[custom_nodes.publish] missing_path package={entry['package']} path={missing}")
        print(
            "[custom_nodes.publish] refused without --allow-destructive-custom-node-publication; "
            "remote generation is unchanged"
        )
        return PublicationDecision(
            "blocked",
            "destructive_custom_node_publication_blocked",
            identity,
            verified_previous,
            destructive_delta=safety,
            destructive_override=False,
        )

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
    content_mismatch = await _remote_content_mismatch(
        volume, verified_previous, identity
    )
    if content_mismatch is not None:
        incomplete_result = dict(result) if isinstance(result, Mapping) else {}
        incomplete_result["remote_content_mismatch"] = content_mismatch
        return PublicationDecision(
            "publish", "publication_incomplete", identity, result=incomplete_result
        )
    receipt = PublicationReceipt.create(
        identity,
        volume_name,
        destructive_override=bool(safety["blocked"] and safety["allowed"]),
        destructive_delta=dict(safety) if safety["blocked"] else {},
    )
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
    "CANDIDATE_READBACK_SAMPLE_SIZE",
    "RECEIPT_PATH", "GENERATION_RECORD_PATH",
    "CUSTOM_NODES_VOLUME_NAME", "CUSTOM_NODES_PUBLISHER_APP_NAME",
    "collect_semantic_files", "build_source_identity", "build_archive",
    "archive_content_digest",
    "prepare_publication", "evaluate_receipt", "read_receipt", "read_receipt_async",
    "write_receipt", "write_receipt_async",
    "check_publication_safety", "publication_safety_delta",
    "publish_or_skip", "run_publish_or_skip", "get_volume", "resolve_custom_nodes_root",
]
