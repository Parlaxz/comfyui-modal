"""v2ctl flag registry (Batch E32, Agent A).

The registry is *metadata, not a whitelist* (design §7): it records every
known flag's type, lifecycle and owner so the CLI can validate values,
explain flags and audit consumption.  Unknown flags are deliberately NOT
rejected by the registry — they flow through as ``unregistered``.

Python 3.11 stdlib only (tomllib for TOML).  No network, no project
runtime imports.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .errors import FlagError

FLAG_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,127}$")
CONSUMED_AT_VALUES = ("build", "module_import", "restore", "method_entry", "request", "harness")
CHANGE_REQUIRES_VALUES = ("build", "deploy", "run", "none", "unknown")
FLAG_TYPES = ("bool", "int", "float", "string", "enum", "path", "json")

_BOOL_TRUE = frozenset({"1", "true", "yes", "on"})
_BOOL_FALSE = frozenset({"0", "false", "no", "off"})

# Where the registry TOML lives relative to the repository root.
_DEFAULT_REL_PATH = Path("config") / "v2" / "flag_registry.toml"


def _repo_root() -> Path:
    """Locate the repository root as the parent of the ``tools`` package."""
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class FlagDef:
    """One registered flag (frozen; values are normalized at load time)."""

    name: str
    type: str
    default: str
    consumed_at: str
    change_requires: str
    owner: str
    description: str
    enum_values: tuple[str, ...] | None = None
    min: int | None = None
    max: int | None = None
    regex: str | None = None
    aliases: tuple[str, ...] = ()
    deprecated: bool = False

    def validate_value(self, value: str) -> str:
        """Coerce/validate ``value`` and return the normalized form.

        Raises :class:`FlagError` with a clear message on any failure.
        """
        if self.type == "bool":
            return _coerce_bool(value, self.name)
        if self.type == "int":
            return _coerce_int(value, self.name, self.min, self.max)
        if self.type == "float":
            return _coerce_float(value, self.name)
        if self.type == "enum":
            if self.enum_values is None:
                raise FlagError(f"flag {self.name}: enum type declared without enum_values")
            if value not in self.enum_values:
                allowed = ", ".join(sorted(self.enum_values))
                raise FlagError(
                    f"flag {self.name}: invalid enum value {value!r}; expected one of: {allowed}"
                )
            return value
        if self.type == "string":
            # Empty string is the "unset" sentinel for string flags; a value
            # is only checked against the regex when it is non-empty.
            if value == "":
                return value
            if self.regex is not None:
                try:
                    pattern = re.compile(self.regex)
                except re.error as exc:
                    raise FlagError(
                        f"flag {self.name}: invalid regex in registry metadata: {exc}"
                    ) from exc
                if not pattern.fullmatch(value):
                    raise FlagError(
                        f"flag {self.name}: value {value!r} does not match required pattern {self.regex!r}"
                    )
            return value
        if self.type == "path":
            if not value:
                raise FlagError(f"flag {self.name}: path value must be non-empty")
            return value
        if self.type == "json":
            try:
                json.loads(value)
            except json.JSONDecodeError as exc:
                raise FlagError(f"flag {self.name}: invalid JSON value {value!r}: {exc}") from exc
            return value
        raise FlagError(f"flag {self.name}: unknown type {self.type!r}")


def _coerce_bool(value: str, name: str) -> str:
    lowered = value.strip().lower()
    if lowered in _BOOL_TRUE:
        return "1"
    if lowered in _BOOL_FALSE:
        return "0"
    raise FlagError(
        f"flag {name}: invalid boolean {value!r}; expected one of: "
        "1/0/true/false/yes/no/on/off (case-insensitive)"
    )


def _coerce_int(value: str, name: str, min_: int | None, max_: int | None) -> str:
    stripped = value.strip()
    try:
        parsed = int(stripped, 10)
    except ValueError as exc:
        raise FlagError(f"flag {name}: invalid integer {value!r}") from exc
    if min_ is not None and parsed < min_:
        raise FlagError(f"flag {name}: value {parsed} is below minimum {min_}")
    if max_ is not None and parsed > max_:
        raise FlagError(f"flag {name}: value {parsed} is above maximum {max_}")
    return str(parsed)


def _coerce_float(value: str, name: str) -> str:
    stripped = value.strip()
    try:
        parsed = float(stripped)
    except ValueError as exc:
        raise FlagError(f"flag {name}: invalid float {value!r}") from exc
    if not _is_finite(parsed):
        raise FlagError(f"flag {name}: float value must be finite, got {value!r}")
    return repr(parsed)


def _is_finite(value: float) -> bool:
    # float('nan').is_integer() raises; guard the standard way.
    return value == value and value not in (float("inf"), float("-inf"))


@dataclass
class AuditReport:
    """Result of :meth:`FlagRegistry.audit`."""

    consumed_registered: list[str]
    consumed_unregistered: list[str]
    registered_no_consumer: list[str]
    profile_set_no_consumer: list[str]


class FlagRegistry:
    """Loads and queries ``config/v2/flag_registry.toml``.

    ``load()`` is idempotent; the registry caches the parsed flags so
    repeated lookups never re-read the file.
    """

    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            path = _repo_root() / _DEFAULT_REL_PATH
        self.path = Path(path)
        self._flags: dict[str, FlagDef] = {}
        self._alias_map: dict[str, str] = {}
        self._loaded = False

    # -- loading ----------------------------------------------------------

    def load(self) -> None:
        """Parse the registry TOML.  Raises FlagError on bad TOML/schema."""
        if self._loaded:
            return
        try:
            with self.path.open("rb") as handle:
                data = tomllib.load(handle)
        except FileNotFoundError as exc:
            raise FlagError(f"flag registry not found: {self.path}") from exc
        except tomllib.TOMLDecodeError as exc:
            raise FlagError(f"flag registry {self.path} is not valid TOML: {exc}") from exc

        if data.get("schema_version") != 1:
            raise FlagError(
                f"flag registry {self.path}: unsupported schema_version "
                f"{data.get('schema_version')!r} (expected 1)"
            )

        raw_flags = data.get("flag")
        if not isinstance(raw_flags, list) or not raw_flags:
            raise FlagError(f"flag registry {self.path}: no [[flag]] entries found")

        parsed: dict[str, FlagDef] = {}
        alias_map: dict[str, str] = {}
        for raw in raw_flags:
            flag = self._parse_flag(raw)
            if flag.name in parsed:
                raise FlagError(f"flag registry {self.path}: duplicate flag {flag.name!r}")
            parsed[flag.name] = flag
            for alias in flag.aliases:
                if alias in parsed or alias in alias_map:
                    raise FlagError(
                        f"flag registry {self.path}: alias {alias!r} (for {flag.name}) conflicts"
                    )
                alias_map[alias] = flag.name

        self._flags = parsed
        self._alias_map = alias_map
        self._loaded = True

    def _parse_flag(self, raw: object) -> FlagDef:
        if not isinstance(raw, dict):
            raise FlagError(f"flag registry {self.path}: [[flag]] entry is not a table")
        name = raw.get("name")
        if not isinstance(name, str) or not name:
            raise FlagError(f"flag registry {self.path}: flag entry missing 'name'")
        self.validate_name(name)

        ftype = raw.get("type")
        if ftype not in FLAG_TYPES:
            raise FlagError(
                f"flag registry {self.path}: flag {name} has unknown type {ftype!r}; "
                f"expected one of {', '.join(FLAG_TYPES)}"
            )
        consumed_at = raw.get("consumed_at")
        if consumed_at not in CONSUMED_AT_VALUES:
            raise FlagError(
                f"flag registry {self.path}: flag {name} has invalid consumed_at "
                f"{consumed_at!r}; expected one of {', '.join(CONSUMED_AT_VALUES)}"
            )
        change_requires = raw.get("change_requires")
        if change_requires not in CHANGE_REQUIRES_VALUES:
            raise FlagError(
                f"flag registry {self.path}: flag {name} has invalid change_requires "
                f"{change_requires!r}; expected one of {', '.join(CHANGE_REQUIRES_VALUES)}"
            )
        default = raw.get("default")
        if not isinstance(default, str):
            raise FlagError(f"flag registry {self.path}: flag {name} 'default' must be a string")
        owner = raw.get("owner")
        if not isinstance(owner, str) or not owner:
            raise FlagError(f"flag registry {self.path}: flag {name} missing 'owner'")
        description = raw.get("description")
        if not isinstance(description, str) or not description:
            raise FlagError(f"flag registry {self.path}: flag {name} missing 'description'")

        enum_values = _parse_str_tuple(raw.get("enum_values"), name, "enum_values")
        min_ = raw.get("min")
        max_ = raw.get("max")
        if min_ is not None and not isinstance(min_, int):
            raise FlagError(f"flag registry {self.path}: flag {name} 'min' must be an integer")
        if max_ is not None and not isinstance(max_, int):
            raise FlagError(f"flag registry {self.path}: flag {name} 'max' must be an integer")
        regex = raw.get("regex")
        if regex is not None and not isinstance(regex, str):
            raise FlagError(f"flag registry {self.path}: flag {name} 'regex' must be a string")
        if regex is not None:
            try:
                re.compile(regex)
            except re.error as exc:
                raise FlagError(
                    f"flag registry {self.path}: flag {name} has invalid regex {regex!r}: {exc}"
                ) from exc
        aliases = _parse_str_tuple(raw.get("aliases"), name, "aliases") or ()
        deprecated = raw.get("deprecated", False)
        if not isinstance(deprecated, bool):
            raise FlagError(f"flag registry {self.path}: flag {name} 'deprecated' must be a boolean")

        flag = FlagDef(
            name=name,
            type=ftype,
            default=default,
            consumed_at=consumed_at,
            change_requires=change_requires,
            owner=owner,
            description=description,
            enum_values=enum_values,
            min=min_,
            max=max_,
            regex=regex,
            aliases=aliases,
            deprecated=deprecated,
        )
        # The registered default must itself be valid for the declared type.
        # An empty default string is the "no registered default" sentinel
        # (the runtime/code default applies) and is always legal; explicit
        # values are validated strictly via validate_explicit_value.
        if default != "":
            try:
                flag.validate_value(default)
            except FlagError as exc:
                raise FlagError(
                    f"flag registry {self.path}: flag {name} default is invalid: {exc}"
                ) from exc
        return flag

    # -- queries ----------------------------------------------------------

    def get(self, name: str) -> FlagDef | None:
        """Return the FlagDef for ``name`` (exact name or alias) or None."""
        self.load()
        flag = self._flags.get(name)
        if flag is not None:
            return flag
        canonical = self._alias_map.get(name)
        if canonical is not None:
            return self._flags.get(canonical)
        return None

    def registered_names(self) -> list[str]:
        """Sorted list of registered flag names."""
        self.load()
        return sorted(self._flags)

    def all_flags(self) -> list[FlagDef]:
        """All registered flags (sorted by name)."""
        self.load()
        return [self._flags[name] for name in sorted(self._flags)]

    def audit(
        self,
        consumed_names: Iterable[str],
        profile_set_names: Iterable[str],
    ) -> AuditReport:
        """Cross-check which registered flags are consumed/set.

        ``consumed_names``: env vars the runtime/harness actually reads.
        ``profile_set_names``: env keys set by the active profile chain.
        """
        self.load()
        consumed = list(consumed_names)
        profile_set = list(profile_set_names)
        registered = set(self._flags)

        consumed_registered = sorted(n for n in consumed if n in registered)
        consumed_unregistered = sorted(
            n for n in consumed if n not in registered and n not in consumed_registered
        )
        registered_no_consumer = sorted(registered - set(consumed))
        profile_set_no_consumer = sorted(
            n for n in profile_set if n not in registered and n not in set(consumed)
        )
        return AuditReport(
            consumed_registered=consumed_registered,
            consumed_unregistered=consumed_unregistered,
            registered_no_consumer=registered_no_consumer,
            profile_set_no_consumer=profile_set_no_consumer,
        )

    @staticmethod
    def validate_name(name: str) -> str:
        """Syntax-check a flag name (``^[A-Z][A-Z0-9_]{1,127}$``)."""
        if not isinstance(name, str) or not FLAG_NAME_RE.fullmatch(name):
            raise FlagError(
                f"invalid flag name {name!r}: must match {FLAG_NAME_RE.pattern} "
                "(uppercase letter, then uppercase letters/digits/underscores, 2-128 chars)"
            )
        return name


def _parse_str_tuple(
    raw: object, name: str, key: str
) -> tuple[str, ...] | None:
    if raw is None:
        return None
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise FlagError(f"flag registry {name!r}: '{key}' must be an array of strings")
    return tuple(raw)
