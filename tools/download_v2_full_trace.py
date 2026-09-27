#!/usr/bin/env python3
"""
Secure local Modal Volume bundle downloader for V2 full-trace artifacts.

Downloads a ``bundle.tar.gz`` from a Modal Volume, verifies its SHA-256
incrementally while streaming, atomically stages it, safely extracts,
validates ``bundle_manifest.json`` entries against extracted files,
enforces required-file presence, and reports success as exactly six
``FULL_TRACE_*`` KEY=value lines (or exits non-zero on failure).

Usage::

    # All arguments explicit
    python tools/download_v2_full_trace.py \\
        --volume my-volume \\
        --remote-path /traces/v2_full_trace_abc.tar.gz \\
        --sha256 d7189fb68b61... \\
        --trace-id run-20260728-abc123 \\
        --output-dir ./downloads

    # Artifact descriptor (JSON with aliases supported)
    python tools/download_v2_full_trace.py \\
        --descriptor-path /path/to/descriptor.json

Exit code 0 on success, non-zero on any failure (error detail to stderr).
Credentials are never printed to stdout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import ntpath
import os
import secrets
import sys
import tarfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Tuple


# ── Constants ───────────────────────────────────────────────────────────────

# Repo root (this file lives in ``tools/``); lets the tool import the
# config-owned ``modal_workspaces`` module whether it is run as a script or
# imported as ``tools.download_v2_full_trace``.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Ambient selection variables that must never decide which Modal workspace a
# Volume is resolved against.  Mirrors tools/v2_control/source_probe.py.
_AMBIENT_MODAL_SELECTORS: Tuple[str, ...] = (
    "COMFYMODAL_ENVIRONMENT",
    "COMFYMODAL_V2_ENVIRONMENT",
    "COMFYMODAL_MODAL_PROFILE",
)

BUNDLE_FILENAME = "bundle.tar.gz"
MANIFEST_FILENAME = "bundle_manifest.json"
REQUIRED_MANIFEST_KEYS: Tuple[str, ...] = ("path", "size_bytes", "sha256", "category")

REQUIRED_EXTRACTED_FILES: Tuple[str, ...] = (
    "derived/report.md",
    "raw/viztracer.json.gz",
    "derived/manifest.json",
)

OPTIONAL_EXTRACTED_FILES: Tuple[str, ...] = (
    "raw/torch_trace.json.gz",
    # Golden profiler artifacts are optional so older bundles remain valid.
    "derived/golden_profile_report.md",
    "derived/golden_profile_gantt.txt",
    "derived/golden_profile_summary.json",
)

BLOCK_SIZE = 65536


# ── Artifact Descriptor ─────────────────────────────────────────────────────

class ArtifactDescriptor:
    """Immutable download specification loaded from CLI args or JSON file."""

    def __init__(
        self,
        volume: str,
        remote_path: str,
        sha256: str,
        trace_id: str,
        output_dir: str,
    ) -> None:
        self.volume = volume
        self.remote_path = remote_path
        self.sha256 = sha256.lower()
        self.trace_id = trace_id
        self.output_dir = output_dir

    @classmethod
    def from_cli_args(cls, args: argparse.Namespace) -> "ArtifactDescriptor":
        """Build from parsed CLI arguments."""
        return cls(
            volume=args.volume,
            remote_path=args.remote_path,
            sha256=args.sha256,
            trace_id=args.trace_id,
            output_dir=args.output_dir,
        )

    @classmethod
    def from_descriptor_file(cls, path: str) -> "ArtifactDescriptor":
        """Build from a JSON descriptor file on disk.

        Supports field aliases for cross-contract compatibility:

          ``volume`` / ``volume_name``
          ``remote_path`` / ``remote_bundle_path``
          ``sha256`` / ``bundle_sha256``
          ``output_dir`` (same, no alias)
          ``trace_id`` (same, no alias)
        """

        def _get(data: dict, *keys: str) -> Any:
            for k in keys:
                if k in data:
                    return data[k]
            raise KeyError(
                f"None of {keys} found in descriptor; "
                f"available keys: {list(data.keys())}"
            )

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(
            volume=_get(data, "volume", "volume_name"),
            remote_path=_get(data, "remote_path", "remote_bundle_path"),
            sha256=_get(data, "sha256", "bundle_sha256"),
            trace_id=_get(data, "trace_id"),
            output_dir=_get(data, "output_dir"),
        )

    def to_dict(self) -> Dict[str, str]:
        return {
            "volume": self.volume,
            "remote_path": self.remote_path,
            "sha256": self.sha256,
            "trace_id": self.trace_id,
            "output_dir": self.output_dir,
        }


# ── Download Abstraction ────────────────────────────────────────────────────

class DownloadClient:
    """Abstracts Modal Volume file operations for testability.

    The real implementation uses ``modal.Volume.read_file()``.  Tests may
    subclass or monkey-patch the method stubs.
    """

    def read_file_chunks(self, volume: Any, remote_path: str) -> Iterable[bytes]:
        """Yield chunks of *remote_path* from *volume*.

        *volume* is a live Modal Volume object (or a test double).
        """
        return volume.read_file(remote_path)


# ── SHA-256 + file helpers ──────────────────────────────────────────────────

def _compute_file_sha256(path: Path) -> str:
    """SHA-256 hex digest of a file on disk."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(BLOCK_SIZE)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _incremental_verify(
    src_chunks: Iterable[bytes],
    dst_path: Path,
    expected_sha256: str,
) -> None:
    """Stream bytes from *src_chunks* into *dst_path* while computing SHA-256.

    Closes and fsyncs *dst_path* before verifying the hash.  If the hash
    does not match, *dst_path* is removed and ``ValueError`` is raised.
    """
    h = hashlib.sha256()
    with open(dst_path, "wb") as f:
        for chunk in src_chunks:
            f.write(chunk)
            h.update(chunk)
        f.flush()
        os.fsync(f.fileno())

    actual = h.hexdigest()
    if actual != expected_sha256:
        dst_path.unlink(missing_ok=True)
        raise ValueError(
            f"SHA-256 mismatch for {dst_path.name}: "
            f"expected {expected_sha256}, got {actual}"
        )


# ── Secure tar extraction ───────────────────────────────────────────────────

class ExtractionError(Exception):
    """Raised when a tar member fails security validation."""


def _is_within(root: Path, candidate: Path) -> bool:
    """Return whether *candidate* resolves beneath *root*."""
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _safe_extract(tar_path: Path, extract_root: Path) -> None:
    """Extract *tar_path* into *extract_root* with rigorous security checks.

    Validates ALL members before extracting any (two-pass), then extracts
    with Python 3.12+ ``filter="data"`` for defence-in-depth.

    Rejects:
      - Absolute member paths
      - ``..`` traversal components
      - Members that escape *extract_root*
      - Device files (FIFO, character, block)
      - Symlinks pointing outside *extract_root*
      - Hardlinks pointing outside *extract_root*
    """
    with tarfile.open(tar_path, "r:gz") as tar:
        members = tar.getmembers()
        # First pass: validate every member
        for member in members:
            _validate_tar_member(member, extract_root)
        # Second pass: extract only after all pass validation
        for member in members:
            tar.extract(member, path=str(extract_root), filter="data")


def _validate_tar_member(member: tarfile.TarInfo, extract_root: Path) -> None:
    """Validate a single tar member against security rules."""
    name = member.name
    safe_name = name.lstrip("/") if name.startswith("/") else name
    # Normalise for traversal detection
    normalized = Path(safe_name).as_posix()

    # ── Reject absolute paths ────────────────────────────────────────
    if (
        name.startswith(("/", "\\"))
        or ntpath.isabs(name)
        or bool(ntpath.splitdrive(name)[0])
    ):
        raise ExtractionError(
            f"Absolute path in tar entry: {name!r}"
        )

    if "\\" in name:
        raise ExtractionError(
            f"Unsafe path separator in tar entry: {name!r}"
        )

    # ── Reject path traversal (..) ───────────────────────────────────
    parts = normalized.split("/")
    if ".." in parts:
        raise ExtractionError(
            f"Path traversal in tar entry: {name!r}"
        )

    # ── Reject root escape via resolved path ─────────────────────────
    resolved = (extract_root / safe_name).resolve()
    if not _is_within(extract_root, resolved):
        raise ExtractionError(
            f"Tar entry would escape extraction root: {name!r} -> {resolved}"
        )

    # ── Reject device / special files ────────────────────────────────
    if member.isfifo() or member.ischr() or member.isblk():
        raise ExtractionError(
            f"Device or special file in tar entry: {name!r} "
            f"(type={member.type})"
        )

    if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
        raise ExtractionError(
            f"Unsupported tar entry type in {name!r}: {member.type!r}"
        )

    # ── Reject unsafe symlinks ───────────────────────────────────────
    if member.issym():
        link_target = member.linkname
        if (
            not link_target
            or link_target.startswith(("/", "\\"))
            or ntpath.isabs(link_target)
            or bool(ntpath.splitdrive(link_target)[0])
        ):
            raise ExtractionError(
                f"Symlink in tar entry {name!r} has unsafe target: "
                f"{link_target!r}"
            )
        link_parent = (extract_root / safe_name).parent
        resolved_link = (link_parent / link_target).resolve()
        if not _is_within(extract_root, resolved_link):
            raise ExtractionError(
                f"Symlink in tar entry {name!r} points outside root: "
                f"{link_target!r} -> {resolved_link}"
            )

    # ── Reject unsafe hardlinks ──────────────────────────────────────
    if member.islnk():
        link_target = member.linkname
        if (
            not link_target
            or link_target.startswith(("/", "\\"))
            or ntpath.isabs(link_target)
            or bool(ntpath.splitdrive(link_target)[0])
        ):
            raise ExtractionError(
                f"Hardlink in tar entry {name!r} has unsafe target: "
                f"{link_target!r}"
            )
        resolved_link = (extract_root / link_target).resolve()
        if not _is_within(extract_root, resolved_link):
            raise ExtractionError(
                f"Hardlink in tar entry {name!r} points outside root: "
                f"{link_target!r} -> {resolved_link}"
            )


# ── Manifest validation ─────────────────────────────────────────────────────

def _load_manifest(extract_root: Path) -> Dict[str, Any]:
    """Load and validate ``bundle_manifest.json`` from *extract_root*.

    Validates structure, required keys per entry, and path safety
    (rejects absolute paths and ``..`` traversal).  Returns a dict with:

      ``entries`` — validated entry list
      ``strict_completeness`` — bool from manifest or ``False``
      ``raw_manifest`` — original parsed JSON (for cross-referencing)

    Raises ``ValueError`` for missing, malformed, or structurally
    invalid manifests.
    """
    manifest_path = extract_root / MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise ValueError(f"Missing {MANIFEST_FILENAME} at {manifest_path}")

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed {MANIFEST_FILENAME}: {exc}") from exc

    if not isinstance(manifest, dict):
        raise ValueError(
            f"Expected {MANIFEST_FILENAME} to be a JSON object, "
            f"got {type(manifest).__name__}"
        )

    # Find the entries list under a known key
    entries: List[Dict[str, Any]] = []
    if "entries" in manifest:
        entries = manifest["entries"]
    elif "files" in manifest:
        entries = manifest["files"]
    else:
        # Top-level dict-of-entries pattern
        for val in manifest.values():
            if isinstance(val, list):
                entries = val
                break
        if not entries:
            raise ValueError(
                f"Cannot locate file entries in {MANIFEST_FILENAME} "
                f"(expected 'entries' or 'files' key)"
            )

    if not isinstance(entries, list):
        raise ValueError(
            f"Expected entries in {MANIFEST_FILENAME} to be a list, "
            f"got {type(entries).__name__}"
        )

    validated: List[Dict[str, Any]] = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(
                f"Entry {i} in {MANIFEST_FILENAME} is not an object"
            )
        missing_keys = [k for k in REQUIRED_MANIFEST_KEYS if k not in entry]
        if missing_keys:
            raise ValueError(
                f"Entry {i} in {MANIFEST_FILENAME} missing required keys: "
                f"{missing_keys}.  Found keys: {list(entry.keys())}"
            )
        # ── Path safety for every entry ──────────────────────────────
        epath = entry.get("path", "")
        if epath.startswith("/"):
            raise ValueError(
                f"Entry {i} in {MANIFEST_FILENAME} has absolute path: {epath!r}"
            )
        if ".." in Path(epath).as_posix().split("/"):
            raise ValueError(
                f"Entry {i} in {MANIFEST_FILENAME} has path traversal: {epath!r}"
            )
        validated.append(entry)

    strict = manifest.get("strict_completeness", manifest.get("strict", False))
    return {
        "entries": validated,
        "strict_completeness": bool(strict),
        "raw_manifest": manifest,
    }


def _build_file_index(extract_root: Path) -> Dict[str, Path]:
    """Map relative paths to absolute Paths under *extract_root*.

    Keys always use POSIX forward slashes for cross-platform consistency
    with manifest entries (which always use ``/``).
    """
    index: Dict[str, Path] = {}
    for dirpath_str, _dirnames, filenames in os.walk(str(extract_root)):
        dirpath = Path(dirpath_str)
        for fn in filenames:
            full = dirpath / fn
            rel = full.relative_to(extract_root).as_posix()
            index[rel] = full
    return index


def _validate_manifest_entries(
    manifest: Dict[str, Any],
    extract_root: Path,
) -> Dict[str, Any]:
    """Cross-check every manifest entry against actual file on disk.

    When *manifest* declares ``strict_completeness`` (truthy), any file
    on disk not listed in the manifest is treated as an error.  Otherwise
    unexpected files are reported in metadata without causing failure.

    Returns a dict with keys:

      ``status`` — ``"ok"`` or ``"mismatch"``
      ``errors`` — list of mismatch descriptions
      ``unexpected_files`` — files on disk not in manifest (always reported)
    """
    entries: List[Dict[str, Any]] = manifest["entries"]
    strict: bool = bool(manifest.get("strict_completeness", False))
    errors: List[str] = []
    file_index = _build_file_index(extract_root)

    manifest_paths: set = set()

    for entry in entries:
        rel_path = entry["path"]
        manifest_paths.add(rel_path)
        expected_size = entry.get("size_bytes", entry.get("size", None))
        expected_sha = entry.get("sha256", None)

        actual_path = file_index.get(rel_path)
        if actual_path is None:
            errors.append(f"Manifest entry path not found on disk: {rel_path!r}")
            continue

        if expected_size is not None:
            actual_size = actual_path.stat().st_size
            if actual_size != expected_size:
                errors.append(
                    f"Size mismatch for {rel_path!r}: "
                    f"expected {expected_size}, got {actual_size}"
                )

        if expected_sha is not None:
            actual_sha = _compute_file_sha256(actual_path)
            if actual_sha != str(expected_sha).lower():
                errors.append(
                    f"SHA-256 mismatch for {rel_path!r}: "
                    f"expected {expected_sha}, got {actual_sha}"
                )

    # Detect unexpected files (on disk but not in manifest)
    unexpected = sorted(
        set(file_index.keys()) - manifest_paths - {MANIFEST_FILENAME}
    )
    if strict and unexpected:
        errors.append(
            f"Strict completeness enabled but {len(unexpected)} file(s) "
            f"not in manifest: {unexpected}"
        )

    return {
        "status": "mismatch" if errors else "ok",
        "errors": errors,
        "unexpected_files": unexpected,
    }


def _check_required_files(extract_root: Path) -> List[str]:
    """Verify all REQUIRED_EXTRACTED_FILES exist on disk.

    Returns a list of missing file paths (empty = all present).
    """
    missing: List[str] = []
    for rel_path in REQUIRED_EXTRACTED_FILES:
        if not (extract_root / rel_path).is_file():
            missing.append(rel_path)
    return missing


def _check_optional_files(extract_root: Path) -> Dict[str, bool]:
    """Check which OPTIONAL_EXTRACTED_FILES exist on disk.

    Returns dict mapping relative path -> bool (present / absent).
    """
    return {
        rel_path: (extract_root / rel_path).is_file()
        for rel_path in OPTIONAL_EXTRACTED_FILES
    }


# ── Main download + extract workflow ────────────────────────────────────────

def run_download(
    descriptor: ArtifactDescriptor,
    *,
    download_client: Optional[DownloadClient] = None,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Full download -> verify -> extract -> validate workflow.

    Parameters
    ----------
    descriptor:
        Download specification.
    download_client:
        Injectable download abstraction.  Defaults to real Modal client.
    progress_cb:
        Optional callback for human-readable progress messages.

    Returns
    -------
    Report dict with keys:

        ``status`` — ``"ok"`` or ``"fail"``
        ``error`` — error message on failure (only present on ``"fail"``)
        ``bundle_path`` — absolute path to verified ``bundle.tar.gz``
        ``extract_root`` — absolute path to extraction directory
        ``report_path`` — absolute path to ``derived/report.md``
        ``viztracer_path`` — absolute path to ``raw/viztracer.json.gz``
        ``manifest_path`` — absolute path to ``derived/manifest.json``
        ``torch_path`` — absolute path to ``raw/torch_trace.json.gz`` or ``None``
        ``golden_profile_report_path`` — absolute path to the optional
            ``derived/golden_profile_report.md`` or ``None``
        ``golden_profile_gantt_path`` — absolute path to the optional
            ``derived/golden_profile_gantt.txt`` or ``None``
        ``golden_profile_summary_path`` — absolute path to the optional
            ``derived/golden_profile_summary.json`` or ``None``
        ``manifest_validation`` — result of manifest entry validation
        ``required_files_missing`` — list of missing required files
        ``optional_files`` — dict of optional-file presence
        ``strict_completeness`` — whether strict completeness was enforced
        ``unexpected_files`` — files not listed in manifest
        ``trace_id`` — the trace identifier
        ``output_dir`` — absolute output directory
    """
    if download_client is None:
        download_client = DownloadClient()
        # Only the real client resolves the canonical Modal destination, so
        # only it needs credentials.  Injected clients (tests/fakes) carry
        # their own data source and must work offline.
        resolve_volume = True
    else:
        resolve_volume = False

    output_dir = Path(descriptor.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if (
        not descriptor.trace_id
        or descriptor.trace_id in {".", ".."}
        or "/" in descriptor.trace_id
        or "\\" in descriptor.trace_id
        or ":" in descriptor.trace_id
    ):
        return {
            "status": "fail",
            "error": "trace_id must be a safe single path component",
            "trace_id": descriptor.trace_id,
            "output_dir": str(output_dir),
        }

    # Temp prefix for atomic renames
    tmp_tag = secrets.token_hex(4)

    bundle_tmp = output_dir / f"{BUNDLE_FILENAME}.{tmp_tag}"
    bundle_final = output_dir / BUNDLE_FILENAME
    extract_root = output_dir / f"full_trace_{descriptor.trace_id}"

    try:
        # ── Step 1: Download with incremental hash -------------------
        _progress(progress_cb, "Downloading bundle ...")
        vol = _get_volume(descriptor.volume) if resolve_volume else None
        chunks = download_client.read_file_chunks(vol, descriptor.remote_path)
        _incremental_verify(chunks, bundle_tmp, descriptor.sha256)

        # ── Step 2: Atomic rename ------------------------------------
        _progress(progress_cb, "SHA-256 verified, staging bundle ...")
        if bundle_final.exists():
            bundle_final.unlink()
        os.rename(str(bundle_tmp), str(bundle_final))

        # ── Step 3: Safe extraction ----------------------------------
        _progress(progress_cb, "Extracting bundle ...")
        extract_root.mkdir(parents=True, exist_ok=True)
        _safe_extract(bundle_final, extract_root)

        # ── Step 4: Load and validate manifest -----------------------
        _progress(progress_cb, "Validating manifest ...")
        manifest_data = _load_manifest(extract_root)

        # ── Step 5: Validate manifest entries against disk -----------
        manifest_validation = _validate_manifest_entries(manifest_data, extract_root)

        # ── Step 6: Check required files -----------------------------
        missing_required = _check_required_files(extract_root)

        # ── Step 7: Check optional files (info only) -----------------
        optional_files = _check_optional_files(extract_root)

        # ── Collect absolute paths for report ------------------------
        def _abs_if(rel: str) -> str:
            p = extract_root / rel
            return str(p.resolve()) if p.is_file() else ""

        report_path = _abs_if("derived/report.md")
        viztracer_path = _abs_if("raw/viztracer.json.gz")
        manifest_path = _abs_if("derived/manifest.json")
        torch_abs = extract_root / "raw/torch_trace.json.gz"
        torch_path: Optional[str] = str(torch_abs.resolve()) if torch_abs.is_file() else None

        def _optional_abs(rel: str) -> Optional[str]:
            p = extract_root / rel
            return str(p.resolve()) if p.is_file() else None

        golden_profile_report_path = _optional_abs(
            "derived/golden_profile_report.md"
        )
        golden_profile_gantt_path = _optional_abs(
            "derived/golden_profile_gantt.txt"
        )
        golden_profile_summary_path = _optional_abs(
            "derived/golden_profile_summary.json"
        )

        # ── Determine overall success --------------------------------
        errors: List[str] = []
        errors.extend(manifest_validation["errors"])
        errors.extend(f"Missing required file: {p}" for p in missing_required)

        base_report: Dict[str, Any] = {
            "bundle_path": str(bundle_final.resolve()),
            "extract_root": str(extract_root.resolve()),
            "report_path": report_path,
            "viztracer_path": viztracer_path,
            "manifest_path": manifest_path,
            "torch_path": torch_path,
            "golden_profile_report_path": golden_profile_report_path,
            "golden_profile_gantt_path": golden_profile_gantt_path,
            "golden_profile_summary_path": golden_profile_summary_path,
            "manifest_validation": manifest_validation,
            "required_files_missing": missing_required,
            "optional_files": optional_files,
            "strict_completeness": manifest_data.get("strict_completeness", False),
            "unexpected_files": manifest_validation.get("unexpected_files", []),
            "trace_id": descriptor.trace_id,
            "output_dir": str(output_dir),
        }

        if errors:
            base_report["status"] = "fail"
            base_report["error"] = "; ".join(errors)
            return base_report

        base_report["status"] = "ok"
        return base_report

    except Exception as exc:
        # Clean up partial temp file if it still exists
        if bundle_tmp.exists():
            bundle_tmp.unlink(missing_ok=True)
        return {
            "status": "fail",
            "error": str(exc),
            "trace_id": descriptor.trace_id,
            "output_dir": str(output_dir),
        }


@contextmanager
def _canonical_modal_destination_environment() -> Iterator[Dict[str, Any]]:
    """Temporarily bind the process env to the config-owned Modal destination.

    Resolves the canonical destination from the shared workspace registry,
    then drops every ``MODAL_*`` variable and known COMFYMODAL selection
    variable so an ambient profile/token cannot redirect the client.  The
    destination's credentials and (non-default) environment are bound for
    the duration of the context; the caller's environment is restored on
    exit, including when the body raises.
    """
    import modal_workspaces

    destination = modal_workspaces.resolve_modal_destination(_REPO_ROOT)
    original = dict(os.environ)
    try:
        for name in list(os.environ):
            if name.startswith("MODAL_") or name in _AMBIENT_MODAL_SELECTORS:
                os.environ.pop(name, None)
        os.environ["MODAL_TOKEN_ID"] = str(destination.get("token_id") or "")
        os.environ["MODAL_TOKEN_SECRET"] = str(destination.get("token_secret") or "")
        environment = str(destination.get("environment") or "(default)")
        if environment != "(default)":
            os.environ["MODAL_ENVIRONMENT"] = environment
            os.environ["COMFYMODAL_ENVIRONMENT"] = environment
            os.environ["COMFYMODAL_V2_ENVIRONMENT"] = environment
        yield destination
    finally:
        os.environ.clear()
        os.environ.update(original)


def _get_volume(volume_name: str) -> Any:
    """Resolve a Modal Volume by name against the canonical destination.

    Ambient ``MODAL_*`` selection is scrubbed and the config-owned
    workspace credentials/environment are bound for the duration of the
    lookup, then the caller's environment is restored.  Raises
    ``SystemExit(1)`` if Modal is not installed, the destination cannot be
    resolved, or the volume cannot be found.
    """
    try:
        import modal
    except ImportError as exc:
        print(
            f"ERROR: Modal package not available ({exc}).  "
            f"Install with: pip install modal",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    try:
        with _canonical_modal_destination_environment():
            return modal.Volume.from_name(volume_name, create_if_missing=False)
    except Exception as exc:
        print(
            f"ERROR: Cannot resolve Modal Volume {volume_name!r}: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc


def _progress(cb: Optional[Callable[[str], None]], msg: str) -> None:
    """Emit progress message if callback is set."""
    if cb:
        cb(msg)


# ── CLI ─────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download and validate a V2 full-trace bundle from a Modal Volume.",
    )
    parser.add_argument(
        "--volume", type=str, default=None,
        help="Modal Volume name.",
    )
    parser.add_argument(
        "--remote-path", type=str, default=None,
        help="Remote path within the Volume (e.g. /traces/bundle.tar.gz).",
    )
    parser.add_argument(
        "--sha256", type=str, default=None,
        help="Expected SHA-256 hex digest of the bundle.",
    )
    parser.add_argument(
        "--trace-id", type=str, default=None,
        help="Trace identifier (used as extraction subdirectory name).",
    )
    parser.add_argument(
        "--output-dir", type=str, default=None,
        help="Local directory for downloaded bundle and extracted files.",
    )
    parser.add_argument(
        "--descriptor-path", type=str, default=None,
        help="Path to a JSON descriptor file with all above fields.",
    )
    return parser


def _validate_args(args: argparse.Namespace) -> ArtifactDescriptor:
    """Validate and normalise CLI arguments.

    If ``--descriptor-path`` is given, it takes precedence and all other
    explicit arguments are ignored (they remain optional).
    """
    if args.descriptor_path:
        if not os.path.isfile(args.descriptor_path):
            print(
                f"ERROR: Descriptor file not found: {args.descriptor_path}",
                file=sys.stderr,
            )
            raise SystemExit(1)
        return ArtifactDescriptor.from_descriptor_file(args.descriptor_path)

    missing: List[str] = []
    for arg_name in ("volume", "remote_path", "sha256", "trace_id", "output_dir"):
        if getattr(args, arg_name, None) is None:
            missing.append(f"--{arg_name.replace('_', '-')}")
    if missing:
        print(
            f"ERROR: Missing required arguments: {', '.join(missing)}.  "
            f"Either provide all named arguments or use --descriptor-path.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    return ArtifactDescriptor.from_cli_args(args)


def _format_report(report: Dict[str, Any]) -> str:
    """Return the stdout string for a download report.

    On success returns exactly six ``FULL_TRACE_*`` KEY=value lines and
    nothing else.  On failure returns an empty string (error details go
    to stderr only).
    """
    if report["status"] != "ok":
        return ""

    torch_val = report.get("torch_path") or "absent"

    lines = [
        f"FULL_TRACE_BUNDLE={report['bundle_path']}",
        f"FULL_TRACE_REPORT={report['report_path']}",
        f"FULL_TRACE_VIZTRACER={report['viztracer_path']}",
        f"FULL_TRACE_TORCH={torch_val}",
        f"FULL_TRACE_MANIFEST={report['manifest_path']}",
        f"FULL_TRACE_EXTRACT_DIR={report['extract_root']}",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    descriptor = _validate_args(args)

    # Do NOT print credentials or volume content to stdout -- only
    # the structured report lines and progress to stderr.
    def progress(msg: str) -> None:
        print(f"  {msg}", file=sys.stderr)

    report = run_download(descriptor, progress_cb=progress)
    output = _format_report(report)
    if output:
        print(output, end="")

    if report["status"] != "ok":
        print(
            f"ERROR: {report.get('error', 'trace bundle download failed')}",
            file=sys.stderr,
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
