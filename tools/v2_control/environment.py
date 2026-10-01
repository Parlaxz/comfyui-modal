"""Environment sanitization for the v2ctl control plane (Batch E32).

Builds the child process environment for backend invocations from a
controlled baseline:

1. required host/tool variables (PATH, TEMP, ...) inherited from the host;
2. Modal auth/internal variables are deliberately removed from the host;
   canonical v2ctl injects the already-frozen destination explicitly;
3. resolved config flags + explicit unregistered values (the EXPERIMENTAL
   ``COMFYMODAL_*`` / ``V2_*`` namespace);
4. explicit backend extras (e.g. ``COMFYMODAL_DEPLOY_ONLY=1``).

``COMFYMODAL_*`` / ``V2_*`` values from the ambient shell are NEVER silently
copied into the child environment; only an explicit ``--inherit NAME`` /
``--set NAME=VALUE`` may introduce them.

Any variable whose name is protected (ProtectedPolicy) raises
``ProtectedVarError`` before it can be placed in the environment, and
secret-shaped names are redacted by ``display`` / ``provenance_env``.

Python 3.11 stdlib only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from .errors import ProtectedVarError

# Host variables required for PATH/tool discovery, Python, and OS operation.
REQUIRED_HOST_VARS = (
    "PATH",
    "COMSPEC",
    "SYSTEMROOT",
    "WINDIR",
    "TEMP",
    "TMP",
    "PATHEXT",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "HOMEDRIVE",
    "HOMEPATH",
    "OS",
    "PROCESSOR_ARCHITECTURE",
    "NUMBER_OF_PROCESSORS",
    "PYTHONIOENCODING",
    "PYTHONUTF8",
    "PYTHONHOME",
    "COMPUTERNAME",
    "USERNAME",
)

# Modal auth / internal variables injected only after v2ctl freezes the
# config-owned destination. They are never inherited from the host.
AUTH_INTERNAL_VARS = (
    "MODAL_TOKEN_ID",
    "MODAL_TOKEN_SECRET",
    "MODAL_ENVIRONMENT",
    "MODAL_CLIENT_ID",
    "MODAL_CLIENT_SECRET",
    "MODAL_AUTH",
)

# The EXPERIMENTAL namespace: config flags / unregistered values live here.
EXPERIMENTAL_PREFIXES = ("COMFYMODAL_", "V2_")

# Reserved canonical identity channel.  BackendRunner is the final injector;
# these names are exposed here so policy/tests/writers share one spelling.
V2CTL_INVOCATION_ID_ENV = "COMFYMODAL_V2CTL_INVOCATION_ID"
V2CTL_PROFILE_ENV = "COMFYMODAL_V2CTL_PROFILE"
V2CTL_PROFILE_CONFIG_FINGERPRINT_ENV = "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT"
V2CTL_DEPLOY_FINGERPRINT_ENV = "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT"
V2CTL_RUN_FINGERPRINT_ENV = "COMFYMODAL_V2CTL_RUN_FINGERPRINT"
V2CTL_DESTINATION_FROZEN_ENV = "COMFYMODAL_V2CTL_DESTINATION_FROZEN"
V2CTL_WORKSPACE_ID_ENV = "COMFYMODAL_V2CTL_WORKSPACE_ID"
V2CTL_WORKSPACE_LABEL_ENV = "COMFYMODAL_V2CTL_WORKSPACE_LABEL"
V2CTL_RESERVED_ENV = (
    V2CTL_INVOCATION_ID_ENV,
    V2CTL_PROFILE_ENV,
    V2CTL_PROFILE_CONFIG_FINGERPRINT_ENV,
    V2CTL_DEPLOY_FINGERPRINT_ENV,
    V2CTL_RUN_FINGERPRINT_ENV,
    V2CTL_DESTINATION_FROZEN_ENV,
    V2CTL_WORKSPACE_ID_ENV,
    V2CTL_WORKSPACE_LABEL_ENV,
)

# Secret-shaped names: redacted in display output and refused as overrides.
_SECRET_MARKERS = ("TOKEN", "SECRET", "PASSWORD", "API_KEY", "CREDENTIAL")

_DEFAULT_PREFIXES = ("MODAL_", "V2CTL_")
_DEFAULT_REGEXES = (
    r"^(?:AWS|AZURE|GOOGLE|GITHUB|HF|HUGGINGFACE).*(?:TOKEN|SECRET|KEY|PASSWORD)$",
)


@dataclass(frozen=True)
class ProtectedPolicy:
    """Deny-policy for variables that may never be overridden.

    A name is protected when it matches any of:
    * an exact protected name (app/class/gpu/memory/cpu identity, harness
      internals, v2ctl provenance namespace);
    * a protected prefix (``MODAL_`` auth, ``V2CTL_`` v2ctl-internal);
    * a secret marker substring (TOKEN/SECRET/PASSWORD/API_KEY/CREDENTIAL);
    * a protected regex (cloud-provider credential patterns).
    """

    exact_names: frozenset[str]
    prefixes: tuple[str, ...]
    regexes: tuple[str, ...]

    # -- matching ---------------------------------------------------------

    def _matched_rule(self, name: str) -> str | None:
        if name in self.exact_names:
            return f'exact protected name "{name}"'
        for prefix in self.prefixes:
            if name.startswith(prefix):
                return f'protected prefix "{prefix}"'
        for marker in _SECRET_MARKERS:
            if marker in name:
                return f'secret marker "{marker}"'
        for rx in self.regexes:
            if re.search(rx, name):
                return f'protected regex "{rx}"'
        return None

    def is_protected(self, name: str) -> bool:
        return self._matched_rule(name) is not None

    def check(self, name: str) -> None:
        rule = self._matched_rule(name)
        if rule is not None:
            raise ProtectedVarError(f"refusing protected variable {name}: {rule}")

    # -- redaction --------------------------------------------------------

    def _is_secret(self, name: str) -> bool:
        """Secret rules: secret marker substring, or any protected regex."""
        for marker in _SECRET_MARKERS:
            if marker in name:
                return True
        for rx in self.regexes:
            if re.search(rx, name):
                return True
        return False

    def redact_value(self, name: str, value: str) -> str:
        if self._is_secret(name):
            return "<redacted>"
        return value

    # -- factories / introspection ----------------------------------------

    @staticmethod
    def default() -> "ProtectedPolicy":
        return ProtectedPolicy(
            exact_names=frozenset(
                {
                    # Modal auth identity
                    "MODAL_TOKEN_ID",
                    "MODAL_TOKEN_SECRET",
                    "MODAL_CLIENT_SECRET",
                    "MODAL_ENVIRONMENT",
                    # Deploy identity / target — CLI-controlled, never via env
                    "V2_DEPLOY_IDENT",
                    "COMFYMODAL_V2_APP_NAME",
                    "COMFYMODAL_V2_CLASS_NAME",
                    "COMFYMODAL_V2_GPU",
                    "COMFYMODAL_V2_MEMORY_MB",
                    "COMFYMODAL_V2_CPU_REQUEST",
                    "COMFYMODAL_V2_RESTORE_ONLY_APP_NAME",
                    # Harness internals; publisher-only is injected solely by
                    # the trusted publisher-bootstrap backend extra.
                    "COMFYMODAL_PUBLISHER_ONLY",
                    "COMFYMODAL_COMMAND_START_UNIX_MS",
                    "COMFYMODAL_DEPLOY_TIMEOUT_SECONDS",
                    # v2ctl provenance namespace
                    "V2CTL_PROVENANCE",
                    "V2CTL_DEPLOY_FINGERPRINT",
                    "V2CTL_RUN_FINGERPRINT",
                    "V2CTL_OWNER",
                    "V2CTL_PROFILE",
                    # Canonical invocation/profile channel.  These are set
                    # by v2ctl after all caller-provided extras and can never
                    # be supplied through --set/--inherit.
                    "COMFYMODAL_V2CTL_INVOCATION_ID",
                    "COMFYMODAL_V2CTL_PROFILE",
                    "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT",
                    "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT",
                    "COMFYMODAL_V2CTL_RUN_FINGERPRINT",
                    "COMFYMODAL_V2CTL_WORKSPACE_ID",
                    "COMFYMODAL_V2CTL_WORKSPACE_LABEL",
                }
            ),
            prefixes=_DEFAULT_PREFIXES,
            regexes=_DEFAULT_REGEXES,
        )

    def to_dict(self) -> dict:
        """JSON-safe policy dump for ``doctor`` output."""
        return {
            "exact_names": sorted(self.exact_names),
            "prefixes": list(self.prefixes),
            "secret_markers": list(_SECRET_MARKERS),
            "regexes": list(self.regexes),
        }


class EnvironmentBuilder:
    """Builds the sanitized child environment for a backend invocation."""

    def __init__(self, protected: ProtectedPolicy | None = None) -> None:
        self._protected = protected if protected is not None else ProtectedPolicy.default()

    def build(
        self,
        config: "ResolvedConfig",
        *,
        host_env: Mapping[str, str],
        backend_extra: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """Return the child env dict.

        Order: REQUIRED_HOST_VARS from ``host_env`` (present only), then
        AUTH_INTERNAL_VARS from ``host_env`` (present only), then
        ``config.flags`` + ``config.unregistered`` (EXPERIMENTAL namespace),
        then ``backend_extra``.

        Ambient ``COMFYMODAL_*`` / ``V2_*`` from ``host_env`` are never
        copied.  Protected names (credentials, Modal auth, v2ctl internals,
        CLI-controlled target identity) are refused when they arrive through
        an explicit override channel (``--set`` / ``--inherit`` — a flag
        whose ``source`` is cli/inherit/set).  Profile/default values with
        protected names (e.g. the production profile's resource pins) are
        part of the canonical configuration and pass through;
        ``backend_extra`` is v2ctl's own canonical-identity channel and is
        trusted.  ``display()``/``provenance_env()`` redact secret-shaped
        values everywhere.
        """
        env: dict[str, str] = {}
        for name in REQUIRED_HOST_VARS:
            if name in host_env:
                env[name] = str(host_env[name])
        # Keep the historical projection for local diagnostics/provenance;
        # BackendRunner removes these values at the final child boundary and
        # replaces them only with a frozen destination.
        for name in AUTH_INTERNAL_VARS:
            if name in host_env:
                env[name] = str(host_env[name])
        # ── Windows Modal-client crash prevention (E29 root-cause fix) ─────
        # The Modal CLI prints emoji/unicode (e.g. the 🔨 build icon,
        # U+1F528) and crashes with a 'charmap' codec error on Windows when
        # the child process encoding is cp1252.  That crash can surface as a
        # deploy that exits 0 while the app was NOT updated — the silent
        # failure class that wasted many gate runs.  Force UTF-8 everywhere
        # so every modal invocation (deploy/rollover/run) works.
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        flags = list(getattr(config, "flags", ()) or ())
        flags += list(getattr(config, "unregistered", ()) or ())
        for flag in flags:
            name = flag.name
            value = str(flag.value)
            if getattr(flag, "source", "") in ("cli", "inherit", "set"):
                self._protected.check(name)
            env[name] = value
        for name, value in (backend_extra or {}).items():
            env[name] = str(value)
        return env

    def display(self, env: Mapping[str, str]) -> dict[str, str]:
        """Redacted copy for console/provenance output.

        AUTH variables are always redacted; any other secret-shaped value
        (TOKEN/SECRET/PASSWORD/API_KEY/CREDENTIAL or a protected regex) is
        redacted too.
        """
        out: dict[str, str] = {}
        for name, value in env.items():
            if name in AUTH_INTERNAL_VARS:
                out[name] = "<redacted>"
            else:
                out[name] = self._protected.redact_value(name, str(value))
        return out

    def provenance_env(self, env: Mapping[str, str]) -> dict[str, str]:
        """Redacted copy persisted with run artifacts (same policy)."""
        return self.display(env)

    @staticmethod
    def classify(name: str) -> str:
        """Namespace classification: required | auth | experimental | protected.

        Protected names win over every other classification; names that
        belong to no namespace classify as ``"other"``.
        """
        if ProtectedPolicy.default().is_protected(name):
            return "protected"
        if name in REQUIRED_HOST_VARS:
            return "required"
        if name in AUTH_INTERNAL_VARS:
            return "auth"
        if name.startswith(EXPERIMENTAL_PREFIXES):
            return "experimental"
        return "other"
