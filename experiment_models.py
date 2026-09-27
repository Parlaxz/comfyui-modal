"""Schema dataclasses, validators, canonical serialization, migrations.

The authoritative spec is the Phase 1 section of
docs/superpowers/plans/2026-06-17-modal-comfy-testing-suite.md.

Conventions:
- canonical_dump / canonical_hash use sort_keys=True and reject unknown types.
- dataclasses are frozen for inputs (CellKey) and mutable for internal state
  (ExperimentDefinition is treated as immutable at the API layer via replace()).
- validate_definition() and SchemaError are public.
- migrate(from_version, to_version) is the only sanctioned way to upgrade
  stored state. Each migration function is named migrate_v0_to_v1 etc.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Iterable, Mapping


CURRENT_SCHEMA_VERSION = 1


# ── Errors ────────────────────────────────────────────────────────────────

class SchemaError(ValueError):
    """Raised when a stored or constructed definition is structurally invalid."""


class MigrationError(RuntimeError):
    """Raised when no migration path exists between two schema versions."""


# ── Canonical serialization ──────────────────────────────────────────────

def canonical_dump(obj: Any) -> str:
    """Serialize ``obj`` to a canonical JSON string.

    - Keys are sorted at every level.
    - No whitespace separators.
    - Unknown types raise TypeError (we do not silently str() them).
    """
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def canonical_hash(obj: Any) -> str:
    """Return sha256 of the canonical JSON form of ``obj``."""
    return hashlib.sha256(canonical_dump(obj).encode("utf-8")).hexdigest()


# ── Cell key (the canonical cell identity, §9 of the parent plan) ───────

@dataclass(frozen=True)
class CellKey:
    experiment_id: str
    profile_id: str
    loader_target_group_id: str
    unet: str
    clip: str
    vae: str
    # tuple of (lora_filename, model_strength, clip_strength) per slot, in order
    lora_signature: tuple[tuple[str, float, float], ...]
    prompt_text: str
    negative_prompt_text: str
    input_image_hash: str
    seed: int
    steps: int
    guidance: float
    sampler: str
    scheduler: str
    denoise: float
    width: int
    height: int


def cell_key_to_dict(k: CellKey) -> dict:
    return {
        "experiment_id": k.experiment_id,
        "profile_id": k.profile_id,
        "loader_target_group_id": k.loader_target_group_id,
        "unet": k.unet,
        "clip": k.clip,
        "vae": k.vae,
        # lora_signature is a tuple-of-tuples; convert to nested lists for JSON
        "lora_signature": [[f, ms, cs] for (f, ms, cs) in k.lora_signature],
        "prompt_text": k.prompt_text,
        "negative_prompt_text": k.negative_prompt_text,
        "input_image_hash": k.input_image_hash,
        "seed": k.seed,
        "steps": k.steps,
        "guidance": k.guidance,
        "sampler": k.sampler,
        "scheduler": k.scheduler,
        "denoise": k.denoise,
        "width": k.width,
        "height": k.height,
    }


def cell_key_from_dict(d: Mapping[str, Any]) -> CellKey:
    raw_loras = d.get("lora_signature", [])
    if not isinstance(raw_loras, list):
        raise SchemaError("lora_signature must be a list")
    lora_signature: list[tuple[str, float, float]] = []
    for entry in raw_loras:
        if not isinstance(entry, (list, tuple)) or len(entry) != 3:
            raise SchemaError(f"lora_signature entry must be [file, model_str, clip_str], got {entry!r}")
        lora_signature.append((str(entry[0]), float(entry[1]), float(entry[2])))
    return CellKey(
        experiment_id=str(d.get("experiment_id", "")),
        profile_id=str(d.get("profile_id", "")),
        loader_target_group_id=str(d.get("loader_target_group_id", "")),
        unet=str(d.get("unet", "")),
        clip=str(d.get("clip", "")),
        vae=str(d.get("vae", "")),
        lora_signature=tuple(lora_signature),
        prompt_text=str(d.get("prompt_text", "")),
        negative_prompt_text=str(d.get("negative_prompt_text", "")),
        input_image_hash=str(d.get("input_image_hash", "")),
        seed=int(d.get("seed", 0)),
        steps=int(d.get("steps", 0)),
        guidance=float(d.get("guidance", 0.0)),
        sampler=str(d.get("sampler", "")),
        scheduler=str(d.get("scheduler", "")),
        denoise=float(d.get("denoise", 1.0)),
        width=int(d.get("width", 0)),
        height=int(d.get("height", 0)),
    )


def cell_key_hash(k: CellKey) -> str:
    """Convenience: canonical hash of a CellKey's dict form."""
    return canonical_hash(cell_key_to_dict(k))


# ── Experiment definition ────────────────────────────────────────────────

@dataclass(frozen=True)
class ExperimentDefinition:
    schema_version: int
    experiment_id: str
    revision: int
    name: str
    notes: str
    created_at: str
    updated_at: str


def definition_to_dict(d: ExperimentDefinition) -> dict:
    return asdict(d)


def definition_from_dict(d: Mapping[str, Any]) -> ExperimentDefinition:
    return ExperimentDefinition(
        schema_version=int(d.get("schema_version", 0)),
        experiment_id=str(d.get("experiment_id", "")),
        revision=int(d.get("revision", 0)),
        name=str(d.get("name", "")),
        notes=str(d.get("notes", "")),
        created_at=str(d.get("created_at", "")),
        updated_at=str(d.get("updated_at", "")),
    )


def validate_definition(d: ExperimentDefinition) -> None:
    if d.schema_version != CURRENT_SCHEMA_VERSION:
        raise SchemaError(
            f"unsupported schema_version={d.schema_version}, "
            f"expected {CURRENT_SCHEMA_VERSION}"
        )
    if not d.experiment_id:
        raise SchemaError("experiment_id must not be empty")
    if d.revision < 1:
        raise SchemaError("revision must be >= 1")
    if not d.created_at or not d.updated_at:
        raise SchemaError("created_at and updated_at must be set")


# ── Migrations ───────────────────────────────────────────────────────────

def _migrate_v0_to_v1(legacy: Mapping[str, Any]) -> dict:
    """Promote a pre-v1 (informal) blob to the v1 schema.

    v0 had no schema_version, no revision, no created_at/updated_at.
    Backfilling is best-effort: missing required v1 fields become safe
    defaults. Callers that need stricter migration should write a v0→v1
    upgrader that returns a fully populated dict.
    """
    out = dict(legacy)
    out["schema_version"] = 1
    out.setdefault("experiment_id", "")
    out.setdefault("revision", 1)
    out.setdefault("name", "")
    out.setdefault("notes", "")
    out.setdefault("created_at", "")
    out.setdefault("updated_at", "")
    return out


_MIGRATIONS = {
    (0, 1): _migrate_v0_to_v1,
}


def migrate(legacy: Mapping[str, Any], from_version: int, to_version: int) -> dict:
    if from_version == to_version:
        return dict(legacy)
    if from_version > to_version:
        raise MigrationError(
            f"downgrade not supported: {from_version} -> {to_version}"
        )
    out: dict = dict(legacy)
    for v in range(from_version, to_version):
        step = _MIGRATIONS.get((v, v + 1))
        if step is None:
            raise MigrationError(f"no migration from v{v} to v{v + 1}")
        out = step(out)
    if int(out.get("schema_version", -1)) != to_version:
        raise MigrationError(
            f"migration did not produce schema_version={to_version}"
        )
    return out
