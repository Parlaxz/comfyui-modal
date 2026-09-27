"""Canonical runtime policy and in-memory output identity for generated results.

``COMFYMODAL_OUTPUT_DURABILITY`` is intentionally strict: a missing value or
the value ``off`` (case-insensitive, after surrounding whitespace is removed)
selects ``off``; ``strict`` selects ``strict``.  Any other non-empty explicit
value raises :class:`ConfigurationError` and never silently selects strict.
The selector is evaluated at runtime rather than baked into a Golden-only
caller so every runtime path can share this contract.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Mapping, Optional


OUTPUT_DURABILITY_ENV = "COMFYMODAL_OUTPUT_DURABILITY"
OUTPUT_DURABILITY_OFF = "off"
OUTPUT_DURABILITY_STRICT = "strict"


class ConfigurationError(ValueError):
    """Raised when an explicit runtime configuration value is invalid."""


@dataclass(frozen=True)
class OutputDurabilityPolicy:
    """Resolved output policy used by request execution and telemetry."""

    mode: str
    durability_requested: bool


def resolve_output_durability(
    environ: Optional[Mapping[str, str]] = None,
) -> OutputDurabilityPolicy:
    """Resolve the canonical generated-output durability policy.

    Missing/empty/``off`` values mean no generated-output Volume persistence;
    only explicit ``strict`` requests Volume write, commit, and reopen proof.
    Invalid non-empty values fail closed with :class:`ConfigurationError`.
    """
    source = os.environ if environ is None else environ
    raw = source.get(OUTPUT_DURABILITY_ENV)
    value = str(raw or "").strip().lower()
    if not value or value == OUTPUT_DURABILITY_OFF:
        return OutputDurabilityPolicy(OUTPUT_DURABILITY_OFF, False)
    if value == OUTPUT_DURABILITY_STRICT:
        return OutputDurabilityPolicy(OUTPUT_DURABILITY_STRICT, True)
    raise ConfigurationError(
        f"configuration error: {OUTPUT_DURABILITY_ENV} must be off or strict"
    )


@dataclass(frozen=True)
class ReadyOutputArtifact:
    """Validated encoded output that is ready for inline result delivery.

    This object deliberately owns bytes, count, and SHA together.  It is used
    for ``off`` mode and is not a claim that the bytes are Volume-durable.
    """

    raw_bytes: bytes
    sha256: str
    byte_count: int
    filename: str
    mime_type: str = "image/png"
    width: int = 0
    height: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.raw_bytes, (bytes, bytearray)):
            raise ValueError("output_bytes_invalid")
        observed_count = len(self.raw_bytes)
        observed_sha = hashlib.sha256(self.raw_bytes).hexdigest()
        if int(self.byte_count) != observed_count:
            raise RuntimeError(
                f"output_byte_count_mismatch:{self.byte_count}!={observed_count}"
            )
        if str(self.sha256).lower() != observed_sha:
            raise RuntimeError(f"output_sha_mismatch:{self.sha256}!={observed_sha}")
        if not self.filename or "/" in self.filename or "\\" in self.filename:
            raise ValueError("output_filename_invalid")


__all__ = [
    "ConfigurationError",
    "OUTPUT_DURABILITY_ENV",
    "OUTPUT_DURABILITY_OFF",
    "OUTPUT_DURABILITY_STRICT",
    "OutputDurabilityPolicy",
    "ReadyOutputArtifact",
    "resolve_output_durability",
]
