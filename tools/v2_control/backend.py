"""Canonical backend registry/runner for the v2ctl control plane (E32).

Backends include the historical BAT entry points and the native Golden deploy:

* ``deploy_and_run_v2_single.bat`` — combined deploy+run (``kind="combined"``);
  the same BAT invoked with ``COMFYMODAL_DEPLOY_ONLY=1`` performs a
  deploy-only run (``kind="deploy_only_via_env"``);
* ``run_v2_single.bat`` — run-only backend (``kind="run"``).
* ``modal deploy -m comfymodal_runtime.modal_app`` — native Golden deploy
  (``kind="deploy"``); it deliberately does not enter the benchmark harness.

``BackendRunner.run`` invokes the backend through ``subprocess`` with the
sanitized child environment and the repo root as cwd.  On win32 the command
is ``f'"{bat_path}" {list2cmdline(extra_args)}'`` executed via
``cmd.exe`` with an argv list; on posix it is a plain argv list
``[exe, *extra_args]``.

Artifacts are discovered best-effort under the well-known experiment output
candidates plus any ``output dir`` / ``output_dir`` line in the backend
stdout.  The dedicated Golden profile is bound separately to the cohort
manifest and attempt artifact emitted by that invocation.

Python 3.11 stdlib only; no network calls, no modal/deploy invocations.
"""

from __future__ import annotations

import os
import platform
import re
import json
import hashlib
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .environment import EnvironmentBuilder
from .errors import BackendError, ProvenanceError
from .provenance import read_provenance_sibling

_OUTPUT_DIR_RE = re.compile(
    r"[Oo]utput[ _]?dir[=: ]+(?:\"([^\"]+)\"|'([^']+)'|(\S+))"
)
_MANIFEST_PATH_RE = re.compile(
    r"[\"']manifest[\"']\s*:\s*[\"']([^\"']+)"
)


def _is_golden_config(config: "ResolvedConfig") -> bool:
    """Return whether this request uses the dedicated Golden harness."""
    profile = str(getattr(config, "profile_name", "") or "").strip().lower()
    return profile in {"golden_p1", "golden_p1_parallel"} or profile.startswith("golden_p1_direct")


def _normalize_logged_path(raw: str) -> Path:
    """Normalize a path copied from JSON/log output without guessing a file."""
    # json.dumps escapes Windows separators.  Path accepts repeated separators
    # on Windows, but collapsing them also keeps the helper deterministic in
    # POSIX test runs that consume Windows-shaped logs.
    normalized = raw.replace("\\\\", "\\").strip()
    path = Path(normalized)
    if not path.exists() and "\\" in normalized:
        path = Path(normalized.replace("\\", os.sep))
    return path


def _first_nonempty_value(data: dict, *names: str) -> str | None:
    """Return the first non-empty scalar value from an artifact projection."""
    nested = data.get("v2ctl")
    sources = (data, nested) if isinstance(nested, dict) else (data,)
    for source in sources:
        for name in names:
            value = source.get(name)
            if value is not None and str(value).strip():
                return str(value).strip()
    return None


def _artifact_generation(data: dict) -> tuple[str, ...]:
    """Read generation identities from raw and canonical output projections."""
    generations: list[str] = []

    def add_from(value: object) -> None:
        if not isinstance(value, dict):
            return
        generation = _first_nonempty_value(
            value, "generation", "custom_nodes_generation", "observed_generation"
        )
        if generation and generation not in generations:
            generations.append(generation)

    add_from(data)
    for value in (data.get("output_descriptor"), data.get("asset_descriptors")):
        if isinstance(value, dict):
            add_from(value)
        elif isinstance(value, list):
            for item in value:
                add_from(item)
    result = data.get("result")
    if isinstance(result, dict):
        for key in ("images", "asset_descriptors", "output_descriptor"):
            value = result.get(key)
            if isinstance(value, dict):
                add_from(value)
            elif isinstance(value, list):
                for item in value:
                    add_from(item)
    return tuple(generations)


def _asset_ids(value: object) -> list[str]:
    """Extract ordered asset IDs from a descriptor or image collection."""
    if isinstance(value, dict):
        asset_id = value.get("asset_id")
        return [str(asset_id).strip()] if isinstance(asset_id, str) and asset_id.strip() else []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            for asset_id in _asset_ids(item):
                if asset_id not in result:
                    result.append(asset_id)
        return result
    return []


def _artifact_output_identity(data: dict) -> tuple[str, ...]:
    """Return the output asset identity across raw and canonical projections."""
    asset_ids: list[str] = []
    output_sha = _first_nonempty_value(data, "output_sha")
    if output_sha:
        asset_ids.append(output_sha)
    for key in ("output_descriptor",):
        for asset_id in _asset_ids(data.get(key)):
            if asset_id not in asset_ids:
                asset_ids.append(asset_id)

    result = data.get("result")
    if isinstance(result, dict):
        for key in ("images", "asset_descriptors", "output_descriptor"):
            for asset_id in _asset_ids(result.get(key)):
                if asset_id not in asset_ids:
                    asset_ids.append(asset_id)
    return tuple(asset_ids)


def _canonical_ledger_identity(data: dict) -> tuple[object, object] | None:
    """Return a stable ledger projection, when one is present."""
    status = _first_nonempty_value(data, "canonical_ledger_status")
    ledger = data.get("canonical_ledger")
    if status is None and ledger is None:
        return None
    try:
        stable_ledger = json.dumps(ledger, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        stable_ledger = repr(ledger)
    return status, stable_ledger


def _projection_equivalence_key(data: dict, ident: dict[str, str | None]) -> tuple | None:
    """Build proof that two files are equivalent projections of one request.

    A same-request identity alone is intentionally insufficient: two files may
    represent different generations or outputs.  Requiring both generation and
    output identity also preserves the historical fail-closed ambiguity for
    sparse artifacts that cannot prove they are projections of one another.
    """
    generation = _artifact_generation(data)
    output_identity = _artifact_output_identity(data)
    if not generation or not output_identity:
        return None
    ledger_identity = _canonical_ledger_identity(data)
    return (
        ident.get("invocation_id"),
        ident.get("profile"),
        ident.get("profile_config_fingerprint"),
        ident.get("request_id"),
        generation,
        output_identity,
        ledger_identity,
    )


def _has_explicit_output_projection(data: dict) -> bool:
    """Whether an artifact explicitly carries canonical output proof."""
    return bool(
        _first_nonempty_value(data, "output_sha")
        or _asset_ids(data.get("output_descriptor"))
    )


def new_invocation_id() -> str:
    """Return an operation identity independent of wall-clock resolution."""
    return uuid.uuid4().hex


@dataclass
class BackendSpec:
    """Description of one backend executable.

    Exactly one of ``bat_path`` / ``executable`` must be provided.
    ``deploy_only_env`` is merged into the child environment for deploy-only
    invocations (e.g. ``{"COMFYMODAL_DEPLOY_ONLY": "1"}`` on the combined
    BAT).  ``kind`` is one of ``"deploy" | "run" | "combined" |
    "deploy_only_via_env" | "test_fake"``.
    """

    name: str
    bat_path: Path | None = None
    executable: list[str] | None = None
    kind: str = "combined"
    description: str = ""
    deploy_only_env: dict[str, str] = field(default_factory=dict)


@dataclass
class ArtifactSet:
    """Authoritative persisted artifact references for a backend run.

    All fields are best-effort; an empty set is legal.
    """

    output_dir: Path | None = None
    run_artifact: Path | None = None
    summary_artifact: Path | None = None
    campaign_manifest: Path | None = None
    console_capture: Path | None = None
    run_artifacts: list[Path] = field(default_factory=list)
    v2ctl_invocation_id: str | None = None
    request_id: str | None = None
    request_ids: list[str] = field(default_factory=list)
    profile: str | None = None
    profile_config_fingerprint: str | None = None
    attention_backend: str | None = None
    experiment_identity: dict[str, Any] = field(default_factory=dict)
    provenance_validation_status: str = "not_checked"


@dataclass
class BackendResult:
    """Outcome of one backend invocation."""

    exit_code: int
    stdout: str
    stderr: str
    command: str
    started_at: str
    ended_at: str
    elapsed_seconds: float
    artifacts: ArtifactSet = field(default_factory=ArtifactSet)
    v2ctl_invocation_id: str | None = None
    request_id: str | None = None
    request_ids: list[str] = field(default_factory=list)
    profile: str | None = None
    profile_config_fingerprint: str | None = None
    provenance_validation_status: str = "not_checked"
    crash_loop: dict | None = None
    attention_backend: str | None = None
    experiment_identity: dict[str, Any] = field(default_factory=dict)

    def ok(self) -> bool:
        return self.exit_code == 0


class BackendRegistry:
    """Resolves the canonical backend specs for this repo."""

    def __init__(self, repo_root: Path) -> None:
        self._repo_root = Path(repo_root)

    def _bat(self, filename: str) -> Path:
        return self._repo_root / filename

    def canonical(self) -> BackendSpec:
        """Combined deploy+run backend (deploy_and_run_v2_single.bat)."""
        return BackendSpec(
            name="deploy_and_run_v2_single",
            bat_path=self._bat("deploy_and_run_v2_single.bat"),
            kind="combined",
            description="Canonical combined deploy+run backend (deploy_and_run_v2_single.bat).",
        )

    def deploy_only(self) -> BackendSpec:
        """Deploy-only via the combined BAT + COMFYMODAL_DEPLOY_ONLY=1."""
        return BackendSpec(
            name="deploy_and_run_v2_single_deploy_only",
            bat_path=self._bat("deploy_and_run_v2_single.bat"),
            kind="deploy_only_via_env",
            description=(
                "Deploy-only backend: deploy_and_run_v2_single.bat with "
                "COMFYMODAL_DEPLOY_ONLY=1 (no standalone deploy script exists)."
            ),
            deploy_only_env={"COMFYMODAL_DEPLOY_ONLY": "1"},
        )

    def native_deploy(self) -> BackendSpec:
        """Native Modal deploy for Golden; no BAT or benchmark machinery."""
        return BackendSpec(
            name="modal_native_golden_deploy",
            executable=["modal", "deploy", "-m", "comfymodal_runtime.modal_app"],
            kind="deploy",
            description="Native Golden deploy through Modal's module deploy command.",
        )

    # Descriptive spelling for callers that want to make the Golden binding
    # explicit without maintaining a second spec.
    def native_golden_deploy(self) -> BackendSpec:
        return self.native_deploy()

    def publisher_bootstrap(self) -> BackendSpec:
        """Native Modal deploy for the shared custom-node publisher app."""
        return BackendSpec(
            name="modal_native_publisher_bootstrap",
            executable=["modal", "deploy", "-m", "comfyapp"],
            kind="deploy",
            description=(
                "Native publisher bootstrap through comfyapp's Modal module; "
                "the caller supplies the stable shared app name."
            ),
        )

    def native_publisher_bootstrap(self) -> BackendSpec:
        """Descriptive alias for the shared publisher bootstrap spec."""
        return self.publisher_bootstrap()

    def run_only(self) -> BackendSpec:
        """Run-only backend (run_v2_single.bat)."""
        return BackendSpec(
            name="run_v2_single",
            bat_path=self._bat("run_v2_single.bat"),
            kind="run",
            description="Canonical run-only backend (run_v2_single.bat).",
        )

    def by_name(self, name: str) -> BackendSpec:
        """Look up a backend by its BAT stem name (independent of file existence)."""
        for spec in (
            self.canonical(), self.deploy_only(), self.run_only(),
            self.native_deploy(), self.publisher_bootstrap()
        ):
            if spec.name == name:
                return spec
        raise KeyError(f"unknown backend {name!r}")

    def available(self) -> list[BackendSpec]:
        """All canonical backends whose BAT files exist in the repo."""
        out = []
        for spec in (self.canonical(), self.deploy_only(), self.run_only()):
            if spec.bat_path is not None and spec.bat_path.is_file():
                out.append(spec)
        return out


# ── Crash-loop detection (deploy-time) ─────────────────────────────────────
# A crash-looping container repeats the SAME traceback (same exception line)
# across restart attempts.  The backend (deploy BAT) may exit 0 while the
# deployed image is broken; this detector surfaces that so v2ctl never
# writes a "successful" deployment manifest for a crash-looping build.

_CRASHLOOP_MIN_REPEATS = 3


# Artifact discovery errors happen after the child process has exited, so the
# normal BackendResult diagnostic path is not available. Keep this fallback
# bounded and apply the same credential-shaped redaction used by the CLI.
_BACKEND_DIAGNOSTIC_MAX_CHARS = 8 * 1024
_BACKEND_DIAGNOSTIC_TRUNCATION_MARKER = (
    "...[diagnostic output truncated; showing bounded head and tail]"
)
_DIAGNOSTIC_SECRET_RE = re.compile(
    r"(?i)((?:[a-z0-9_]*)(?:token|secret|password|api[_-]?key|credential)"
    r"(?:[a-z0-9_]*\s*[=:]\s*))"
    r"([^\s,;\"']+)"
)
_DIAGNOSTIC_QUOTED_SECRET_RE = re.compile(
    r"(?i)((?:[\"']?)[a-z0-9_]*(?:token|secret|password|api[_-]?key|credential)"
    r"[a-z0-9_]*[\"']?\s*[=:]\s*[\"'])"
    r"([^\"']+)([\"'])"
)


def _redact_backend_diagnostic(text: str, env: dict[str, str]) -> str:
    """Redact credential-shaped values from one captured backend stream."""
    output = text or ""
    protected = EnvironmentBuilder().display(env)
    for name, value in env.items():
        if value and protected.get(name) == "<redacted>":
            output = output.replace(str(value), "<redacted>")
    output = _DIAGNOSTIC_QUOTED_SECRET_RE.sub(r"\1<redacted>\3", output)
    return _DIAGNOSTIC_SECRET_RE.sub(r"\1<redacted>", output)


def _bounded_backend_diagnostic(text: str, env: dict[str, str]) -> str:
    """Return redacted output with a bounded head and tail."""
    output = _redact_backend_diagnostic(text, env)
    if len(output) <= _BACKEND_DIAGNOSTIC_MAX_CHARS:
        return output
    marker = "\n" + _BACKEND_DIAGNOSTIC_TRUNCATION_MARKER + "\n"
    available = max(0, _BACKEND_DIAGNOSTIC_MAX_CHARS - len(marker))
    head = available // 2
    tail = available - head
    return output[:head] + marker + output[-tail:]


def _artifact_discovery_diagnostic(
    error: ProvenanceError,
    stdout: str,
    stderr: str,
    env: dict[str, str],
) -> str:
    """Attach safe child streams to a strict artifact-discovery failure."""
    return (
        f"{error}\n"
        "captured stdout (redacted, bounded):\n"
        f"{_bounded_backend_diagnostic(stdout, env) or '(no output)'}\n"
        "captured stderr (redacted, bounded):\n"
        f"{_bounded_backend_diagnostic(stderr, env) or '(no output)'}"
    )


def detect_crash_loop(output: str) -> dict[str, str] | None:
    """Scan captured backend output for repeated identical tracebacks.

    Returns ``{"exception_type": ..., "count": ...}`` when the SAME
    ``Traceback (most recent call last):`` block's final exception line
    appears at least ``_CRASHLOOP_MIN_REPEATS`` times; None otherwise.
    """
    if not output:
        return None
    try:
        exc_lines: list[str] = []
        lines = output.splitlines()
        for i, line in enumerate(lines):
            if "Traceback (most recent call last)" in line:
                # The exception type line is the last line of the traceback
                # block (typically ``<Type>: <message>`` or ``<Type>``).
                for j in range(i + 1, min(len(lines), i + 24)):
                    cand = lines[j].strip()
                    if not cand:
                        break
                    if "Traceback (most recent call last)" in cand or cand.startswith("During handling"):
                        break
                    if "Error" in cand or "Exception" in cand or "error" in cand.lower():
                        exc_lines.append(cand)
                        break
        if len(exc_lines) < _CRASHLOOP_MIN_REPEATS:
            return None
        # Group by identical exception line; crash loops repeat the SAME one.
        from collections import Counter

        counts = Counter(exc_lines)
        top, count = counts.most_common(1)[0]
        if count >= _CRASHLOOP_MIN_REPEATS:
            return {"exception_type": top[:200], "count": str(count)}
        return None
    except Exception:
        return None


class BackendRunner:
    """Runs a BackendSpec through subprocess with a sanitized child env."""

    def __init__(self, repo_root: Path, env_builder: EnvironmentBuilder) -> None:
        self._repo_root = Path(repo_root)
        self._env_builder = env_builder

    @staticmethod
    def _iso_now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    @staticmethod
    def build_command_line(spec: BackendSpec, extra_args: list[str]) -> str:
        """Pure function: the exact command line that will be executed.

        win32: ``"<bat>" <args...>`` (each extra arg quoted per
        ``subprocess.list2cmdline``).  posix: shell-joined argv.
        """
        if spec.bat_path is not None:
            bat = str(spec.bat_path)
            if os.name == "nt":
                return f'"{bat}" {subprocess.list2cmdline(list(extra_args))}'
            import shlex

            return " ".join([bat] + [shlex.quote(a) for a in extra_args])
        exe = list(spec.executable or [])
        if os.name == "nt":
            return subprocess.list2cmdline(exe + list(extra_args))
        import shlex

        return " ".join(shlex.quote(a) for a in (exe + list(extra_args)))

    def run(
        self,
        spec: BackendSpec,
        *,
        config: "ResolvedConfig",
        extra_args: list[str] = (),
        extra_env: dict[str, str] | None = None,
        capture: bool = True,
        timeout_seconds: float | None = None,
        invocation_id: str | None = None,
        invocation_context: str | None = None,
        canonical_identity: Mapping[str, str] | None = None,
        strict_canonical_discovery: bool = False,
        allow_multiple_run_artifacts: bool = False,
    ) -> BackendResult:
        """Invoke the backend and return a BackendResult.

        ``extra_env`` is merged into the child environment AFTER config
        flags (e.g. ``COMFYMODAL_DEPLOY_ONLY=1`` from ``spec.deploy_only_env``
        and ``V2_BENCHMARK_RUNS=1`` from the gate runner).
        """
        # A direct caller gets a fresh collision-resistant context.  CLI and
        # Gate/Confirm runners pass their already-created operation ID.
        if invocation_id is None and invocation_context is not None:
            if isinstance(invocation_context, dict):
                invocation_id = str(
                    invocation_context.get("v2ctl_invocation_id")
                    or invocation_context.get("invocation_id")
                    or ""
                )
            else:
                invocation_id = str(
                    getattr(invocation_context, "v2ctl_invocation_id", "")
                    or getattr(invocation_context, "invocation_id", "")
                    or invocation_context
                )
        invocation_id = str(invocation_id or new_invocation_id())
        if not invocation_id.strip():
            raise BackendError("empty v2ctl invocation context")
        child_env = self._env_builder.build(config, host_env=os.environ)
        if spec.deploy_only_env:
            child_env.update(spec.deploy_only_env)
        if extra_env:
            child_env.update(extra_env)
        # Reserved identity is injected LAST.  User extras, profiles, and the
        # ambient shell therefore cannot spoof canonical provenance.
        try:
            from .fingerprints import FingerprintEngine

            fp = FingerprintEngine(config)
            profile_config_fp = fp.profile_config_fingerprint()
            deploy_fp = fp.deploy_fingerprint()
            run_fp = fp.run_fingerprint()
        except Exception as exc:  # pragma: no cover - duck-typed test config
            raise BackendError(f"cannot compute canonical fingerprints: {exc}") from exc
        # Receipt-bound requests use the immutable deployment identity while
        # retaining this invocation's current request fingerprint.  This is a
        # narrow channel; arbitrary extra_env values cannot spoof provenance.
        profile = str(getattr(config, "profile_name", "") or "")
        if canonical_identity is not None:
            allowed = {
                "profile", "profile_config_fingerprint", "deploy_fingerprint",
                "run_fingerprint",
            }
            unknown = set(canonical_identity) - allowed
            if unknown:
                raise BackendError(
                    "canonical identity contains unsupported fields: "
                    + ", ".join(sorted(unknown))
                )
            profile = str(canonical_identity.get("profile", profile) or "")
            profile_config_fp = str(
                canonical_identity.get("profile_config_fingerprint", profile_config_fp) or ""
            )
            deploy_fp = str(canonical_identity.get("deploy_fingerprint", deploy_fp) or "")
            run_fp = str(canonical_identity.get("run_fingerprint", run_fp) or "")
            if not profile or not profile_config_fp or not deploy_fp or not run_fp:
                raise BackendError("canonical identity override is incomplete")
        child_env.update({
            "COMFYMODAL_V2CTL_INVOCATION_ID": invocation_id,
            "COMFYMODAL_V2CTL_PROFILE": profile,
            "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": profile_config_fp,
            "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": deploy_fp,
            "COMFYMODAL_V2CTL_RUN_FINGERPRINT": run_fp,
        })
        if _is_golden_config(config):
            # The accepted PyTorch default is explicit at the dispatch
            # boundary; the child must not resolve a different backend later.
            try:
                from .experiment_evidence import resolved_attention_backend

                child_env["COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND"] = (
                    resolved_attention_backend(config)
                )
            except ValueError as exc:
                raise BackendError(str(exc)) from exc

        command = self.build_command_line(spec, list(extra_args))
        started_mono = time.monotonic()
        started_at = self._iso_now()

        kwargs = dict(
            cwd=str(self._repo_root),
            env=child_env,
            capture_output=capture,
        )
        if timeout_seconds is not None:
            kwargs["timeout"] = timeout_seconds

        try:
            if os.name == "nt":
                if spec.bat_path is not None:
                    completed = subprocess.run(
                        [
                            "cmd.exe",
                            "/d",
                            "/c",
                            "call",
                            str(spec.bat_path),
                            *list(extra_args),
                        ],
                        shell=False,
                        **kwargs,
                    )
                else:
                    completed = subprocess.run(
                        list(spec.executable or []) + list(extra_args),
                        shell=False,
                        **kwargs,
                    )
            else:
                if spec.bat_path is not None:
                    import shlex

                    completed = subprocess.run(
                        shlex.split(command),
                        shell=False,
                        **kwargs,
                    )
                else:
                    completed = subprocess.run(
                        list(spec.executable or []) + list(extra_args),
                        shell=False,
                        **kwargs,
                    )
        except subprocess.TimeoutExpired as exc:
            raise BackendError(
                f"backend {spec.name} timed out after {timeout_seconds}s"
            ) from exc
        except OSError as exc:
            raise BackendError(
                f"backend {spec.name} failed to spawn: {exc}"
            ) from exc

        ended_at = self._iso_now()
        elapsed_seconds = time.monotonic() - started_mono
        stdout = completed.stdout.decode("utf-8", errors="replace") if capture else ""
        stderr = completed.stderr.decode("utf-8", errors="replace") if capture else ""
        # ── E40: crash-loop accounting ────────────────────────────────────
        # A remote container that dies at startup is restarted by Modal;
        # the same fatal traceback then repeats in captured output. Detect
        # it here so the operator sees CRASH_LOOP + signature instead of a
        # generic timeout/failure, and so retry logic can refuse to burn
        # another full invocation on a deterministic startup crash.
        _crash_loop = (
            detect_crash_loop(f"{stdout or ''}\n{stderr or ''}") if capture else None
        )
        if _crash_loop is not None:
            print(
                f"[v2ctl.crash-loop] detected exception={_crash_loop.get('exception_type')!r} "
                f"count={_crash_loop.get('count')} backend={spec.name}"
            )
        # Deploy-only backends intentionally produce no workload artifacts.
        # Golden discovery is strict even for non-canonical calls, so trying
        # to discover artifacts here would reject a successful deploy before
        # the subsequent run-only Golden backend can create its cohort.
        deploy_only = str(child_env.get("COMFYMODAL_DEPLOY_ONLY", "")).strip().lower() in (
            "1", "true", "yes", "on"
        )
        # Native deploys are transport-only too.  Golden deploy must not enter
        # generic run-artifact discovery: there is no request artifact to
        # discover during deployment.
        if capture and not deploy_only and spec.kind != "deploy":
            try:
                artifacts = self.discover_artifacts(
                    config,
                    stdout,
                    invocation_id=invocation_id,
                    strict_canonical=strict_canonical_discovery,
                    allow_multiple_run_artifacts=allow_multiple_run_artifacts,
                    expected_profile=str(getattr(config, "profile_name", "") or ""),
                    expected_profile_config_fingerprint=profile_config_fp,
                )
            except ProvenanceError as exc:
                if not strict_canonical_discovery:
                    raise
                raise ProvenanceError(
                    _artifact_discovery_diagnostic(exc, stdout, stderr, child_env)
                ) from exc
        else:
            artifacts = ArtifactSet(
                v2ctl_invocation_id=invocation_id,
                profile=str(getattr(config, "profile_name", "") or ""),
                profile_config_fingerprint=profile_config_fp,
            )
        return BackendResult(
            exit_code=completed.returncode,
            stdout=stdout,
            stderr=stderr,
            command=command,
            started_at=started_at,
            ended_at=ended_at,
            elapsed_seconds=elapsed_seconds,
            artifacts=artifacts,
            v2ctl_invocation_id=invocation_id,
            request_id=artifacts.request_id,
            request_ids=list(artifacts.request_ids),
            profile=artifacts.profile,
            profile_config_fingerprint=artifacts.profile_config_fingerprint,
            crash_loop=_crash_loop,
            attention_backend=getattr(artifacts, "attention_backend", None),
            experiment_identity=dict(getattr(artifacts, "experiment_identity", {}) or {}),
            provenance_validation_status=artifacts.provenance_validation_status,
        )

    # -- artifact discovery ------------------------------------------------

    def _candidate_dirs(self, config: "ResolvedConfig") -> list[Path]:
        repo_root = self._repo_root
        candidates = [
            repo_root / ".comfymodal_experiments",
            repo_root / ".experiments",
            repo_root / "comfymodal-runtime",
            repo_root / "output",
            repo_root / "output" / "studio",
        ]
        # The benchmark harness writes authoritative run artifacts to
        # <repo_root>/../../comfymodal-data/benchmarks/runs/v2_<utc>/ (its
        # ROOT.parent.parent path) — OUTSIDE the repo.  Include that root so
        # gate/run artifact discovery finds the real persisted artifacts.
        benchmark_runs_root = (
            repo_root.resolve().parent.parent / "comfymodal-data" / "benchmarks" / "runs"
        )
        # A temporary/fake repo should not accidentally scan a sibling user's
        # real benchmark archive.  The external root is a canonical project
        # root only when the v2 control-plane layout is present.
        if (repo_root / "tools").is_dir() or (repo_root / "deploy_and_run_v2_single.bat").is_file():
            candidates.append(benchmark_runs_root)
        return [c for c in candidates if c.is_dir()]

    def discover_artifacts(
        self,
        config: "ResolvedConfig",
        backend_result_stdout: str,
        *,
        invocation_id: str | None = None,
        strict_canonical: bool = False,
        allow_multiple_run_artifacts: bool = False,
        expected_profile: str | None = None,
        expected_profile_config_fingerprint: str | None = None,
        legacy: bool | None = None,
        canonical: bool | None = None,
        strict: bool | None = None,
        allow_multiple: bool | None = None,
    ) -> ArtifactSet:
        """Discover persisted artifacts, binding canonical calls by identity.

        The old mtime selector is retained only for explicit ``legacy=True``
        (and the compatibility default used by direct unit callers).  A
        canonical call parses only plausible JSON and requires the exact
        persisted invocation ID; mtime never participates in selection.
        """
        if canonical is not None:
            strict_canonical = canonical
        if strict is not None:
            strict_canonical = strict
        if allow_multiple is not None:
            allow_multiple_run_artifacts = allow_multiple
        # Omitted mode preserves the historical direct-helper behavior for
        # compatibility tests.  Production callers select strict canonical
        # mode; callers that explicitly choose legacy/noncanonical behavior
        # get a labeled result.
        legacy_mode = True if legacy is None else bool(legacy)
        if strict_canonical and not invocation_id:
            raise ProvenanceError("canonical artifact discovery requires an invocation ID")
        # The Golden backend persists a cohort manifest plus attempt_N.json
        # rather than the generic run_N.json/campaign_manifest.json shape.
        # More importantly, old generic artifacts are present in the external
        # benchmark archive.  Never let that archive win a Golden call: the
        # Golden harness prints the cohort output directory for this exact
        # invocation, which is the only discovery root accepted here.
        if _is_golden_config(config):
            return self._discover_golden_artifacts(
                config,
                backend_result_stdout,
                invocation_id=invocation_id,
                strict_canonical=strict_canonical,
                expected_profile=expected_profile,
                expected_profile_config_fingerprint=expected_profile_config_fingerprint,
            )
        candidate_dirs: list[Path] = []
        seen: set[Path] = set()
        for d in self._candidate_dirs(config):
            if d not in seen:
                candidate_dirs.append(d)
                seen.add(d)
        for match in _OUTPUT_DIR_RE.finditer(backend_result_stdout or ""):
            raw = next((group for group in match.groups() if group), "").strip()
            if not raw:
                continue
            p = Path(raw)
            # Backend logs commonly contain Windows paths even when tests run
            # on POSIX.  Normalize separators without rejecting a valid Path.
            if not p.exists() and "\\" in raw:
                p = Path(raw.replace("\\", os.sep))
            if not p.is_absolute():
                p = self._repo_root / p
            if p not in seen:
                candidate_dirs.append(p)
                seen.add(p)

        output_dir: Path | None = None
        run_artifact: Path | None = None
        summary_artifact: Path | None = None
        campaign_manifest: Path | None = None
        candidates_by_kind: dict[str, list[tuple[Path, dict]]] = {
            "run": [], "summary": [], "manifest": []
        }

        def identity(data: dict) -> dict[str, str | None]:
            nested = data.get("v2ctl")
            nested = nested if isinstance(nested, dict) else {}
            def get(*names):
                for source in (data, nested):
                    for name in names:
                        value = source.get(name)
                        if value is not None and str(value).strip():
                            return str(value).strip()
                return None
            return {
                "invocation_id": get("v2ctl_invocation_id", "invocation_id"),
                "profile": get("profile", "profile_name"),
                "profile_config_fingerprint": get(
                    "profile_config_fingerprint", "config_fingerprint",
                    "profile_fingerprint",
                ),
                "request_id": get("request_id", "prompt_id"),
            }

        def identity_with_provenance(path: Path, data: dict) -> dict[str, str | None]:
            """Resolve a run's identity from its embedded data and sibling.

            Runtime artifacts may predate embedded v2ctl identity.  A sibling
            written for this exact artifact is authoritative when its optional
            digest is valid; an invalid sibling must not be allowed to replace
            identity that is already embedded in the artifact.
            """
            ident = identity(data)
            provenance = read_provenance_sibling(path)
            if provenance is None:
                return ident

            if provenance.artifact_sha256:
                try:
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
                except OSError:
                    return ident
                expected_digest = provenance.artifact_sha256.strip().lower()
                if expected_digest.startswith("sha256:"):
                    expected_digest = expected_digest[len("sha256:"):]
                if expected_digest != digest:
                    return ident

            sibling_identity = {
                "invocation_id": provenance.v2ctl_invocation_id,
                "profile": provenance.profile,
                "profile_config_fingerprint": provenance.profile_config_fingerprint,
                "request_id": provenance.request_id,
            }
            for key, value in sibling_identity.items():
                if value is not None and str(value).strip():
                    ident[key] = str(value).strip()
            return ident

        for directory in candidate_dirs:
            try:
                entries = list(directory.iterdir())
            except OSError:
                continue
            # The benchmark writes per-run subdirectories (v2_<utc>/, etc.);
            # scan both the root and its immediate subdirectories.
            scan_dirs = [directory]
            for entry in entries:
                if entry.is_dir():
                    scan_dirs.append(entry)
            for d in scan_dirs:
                try:
                    sub_entries = list(d.iterdir())
                except OSError:
                    continue
                for entry in sub_entries:
                    if not entry.is_file():
                        continue
                    name = entry.name
                    if name.endswith(".v2ctl-provenance.json"):
                        continue
                    kind = None
                    if name == "campaign_manifest.json":
                        kind = "manifest"
                    elif name.startswith("run_") and name.endswith(".json"):
                        kind = "run"
                    elif name.startswith("summary") and name.endswith(".json"):
                        kind = "summary"
                    if kind is None:
                        continue
                    try:
                        data = json.loads(entry.read_text(encoding="utf-8", errors="replace"))
                    except (OSError, ValueError, TypeError):
                        # Malformed candidates are safely ignored; they must
                        # never become an accidental newest-artifact choice.
                        continue
                    if isinstance(data, dict):
                        candidates_by_kind[kind].append((entry, data))

        expected_profile = expected_profile if expected_profile is not None else str(
            getattr(config, "profile_name", "") or ""
        )
        matching_runs: list[tuple[Path, dict, dict]] = []
        for path, data in candidates_by_kind["run"]:
            ident = identity_with_provenance(path, data)
            if not strict_canonical:
                matching_runs.append((path, data, ident))
                continue
            # Unbound historical artifacts are not candidates for a strict
            # invocation.  They must not fail discovery before a current
            # sibling-identified artifact can be considered.
            if not ident["invocation_id"]:
                continue
            if ident["invocation_id"] != invocation_id:
                continue
            if expected_profile and ident["profile"] != expected_profile:
                raise ProvenanceError(
                    f"canonical run artifact has wrong profile: {path} "
                    f"({ident['profile']!r}, expected {expected_profile!r})"
                )
            if expected_profile_config_fingerprint and ident["profile_config_fingerprint"] != expected_profile_config_fingerprint:
                raise ProvenanceError(
                    f"canonical run artifact has wrong profile/config fingerprint: {path}"
                )
            matching_runs.append((path, data, ident))

        if strict_canonical and not matching_runs:
            raise ProvenanceError(
                f"no canonical run artifact found for v2ctl invocation {invocation_id}"
            )
        matching_request_ids = {
            ident["request_id"] for _, _, ident in matching_runs if ident["request_id"]
        }
        selected_run_artifact: Path | None = None
        stdout_request_ids = {
            value.strip()
            for value in re.findall(
                r"['\"]?(?:request_id|REQUEST_ID)['\"]?\s*[=:]\s*['\"]?([^\s,'\"}]+)",
                backend_result_stdout or "",
                flags=re.MULTILINE,
            )
            if value.strip()
        }
        if strict_canonical and len(stdout_request_ids) > 1:
            raise ProvenanceError(
                f"stdout contains conflicting request IDs: {sorted(stdout_request_ids)}"
            )

        # A single invocation may persist several run artifacts (for example,
        # a confirmation with multiple requests).  Never let the deterministic
        # path order silently choose the first one.  The backend's request line
        # is the current request identity and must bind the selected artifact.
        if strict_canonical:
            current_request_id = next(iter(stdout_request_ids), None)
            if current_request_id is None and len(matching_request_ids) > 1:
                raise ProvenanceError(
                    f"matching canonical artifacts have conflicting request IDs: "
                    f"{sorted(matching_request_ids)}"
                )
            missing_request_id = [
                path for path, _, ident in matching_runs if not ident["request_id"]
            ]
            if missing_request_id:
                raise ProvenanceError(
                    "canonical run artifact missing request ID: "
                    + ", ".join(str(path) for path in missing_request_id)
                )
            if current_request_id is not None:
                if current_request_id not in matching_request_ids:
                    raise ProvenanceError(
                        f"stdout request ID {current_request_id!r} does not match "
                        f"canonical artifact request IDs {sorted(matching_request_ids)}"
                    )
                matching_runs = [
                    item for item in matching_runs
                    if item[2]["request_id"] == current_request_id
                ]
            if len(matching_runs) > 1:
                # A single request can have a full raw artifact and a smaller
                # canonical projection.  Collapse only when the files prove
                # that they are equivalent projections of the same generation,
                # ledger, and output.  The raw paths remain visible below in
                # ``run_artifacts`` for provenance/audit consumers.
                groups: dict[tuple, list[tuple[Path, dict, dict]]] = {}
                ungrouped: list[tuple[Path, dict, dict]] = []
                for item in matching_runs:
                    key = _projection_equivalence_key(item[1], item[2])
                    if key is None:
                        ungrouped.append(item)
                    else:
                        groups.setdefault(key, []).append(item)

                if ungrouped or len(groups) != 1:
                    raise ProvenanceError(
                        f"ambiguous canonical run artifacts for invocation {invocation_id}"
                        + (
                            f" and request {current_request_id!r}: "
                            if current_request_id
                            else ": "
                        )
                        + ", ".join(str(p) for p, _, _ in matching_runs)
                    )

                equivalent = next(iter(groups.values()))
                equivalent.sort(
                    key=lambda item: (
                        not _has_explicit_output_projection(item[1]),
                        item[0].name.casefold() != "run_001_sample.json",
                        str(item[0]).casefold(),
                    )
                )
                # Keep the complete equivalent set for ``run_artifacts``;
                # selecting the first member only affects ``run_artifact``.
                selected_run_artifact = equivalent[0][0]
                matching_runs = [equivalent[0]] + [
                    item for item in equivalent[1:]
                ]

        # Deterministic path order is intentional.  It is not an mtime choice.
        matching_runs.sort(key=lambda item: str(item[0]).casefold())
        run_paths = [item[0] for item in matching_runs]
        if not strict_canonical and matching_runs and legacy_mode:
            # Compatibility-only legacy selector: preserve historical mtime
            # semantics, but never enter this branch for canonical calls.
            matching_runs.sort(key=lambda item: item[0].stat().st_mtime, reverse=True)
            run_paths = [item[0] for item in matching_runs]

        # output_dir = parent of the winning artifact, else None (no
        # recognized artifacts -> every field stays None).
        if matching_runs:
            run_artifact = selected_run_artifact or matching_runs[0][0]
        for kind, entries_for_kind in candidates_by_kind.items():
            if strict_canonical and kind != "run":
                exact = []
                for path, data in entries_for_kind:
                    ident = identity(data)
                    if ident["invocation_id"] == invocation_id:
                        if expected_profile and ident["profile"] != expected_profile:
                            raise ProvenanceError(
                                f"canonical {kind} artifact has wrong profile: {path}"
                            )
                        if expected_profile_config_fingerprint and ident["profile_config_fingerprint"] != expected_profile_config_fingerprint:
                            raise ProvenanceError(
                                f"canonical {kind} artifact has wrong profile/config fingerprint: {path}"
                            )
                        exact.append((path, ident))
                if exact:
                    exact.sort(key=lambda item: str(item[0]).casefold())
                    chosen = exact[0][0]
                    if kind == "summary":
                        summary_artifact = chosen
                    elif kind == "manifest":
                        campaign_manifest = chosen
            elif not strict_canonical and entries_for_kind:
                chosen = (
                    max(entries_for_kind, key=lambda item: item[0].stat().st_mtime)[0]
                    if legacy_mode
                    else sorted(entries_for_kind, key=lambda item: str(item[0]).casefold())[0][0]
                )
                if kind == "summary":
                    summary_artifact = chosen
                elif kind == "manifest":
                    campaign_manifest = chosen
        for artifact in (run_artifact, summary_artifact, campaign_manifest):
            if artifact is not None:
                output_dir = artifact.parent
                break

        console_capture = None
        request_ids = {ident["request_id"] for _, _, ident in matching_runs if ident["request_id"]}
        request_id = next(iter(request_ids), None)
        if len(request_ids) > 1:
            request_id = None
        if strict_canonical and request_id and stdout_request_ids and request_id not in stdout_request_ids:
            raise ProvenanceError(
                f"stdout request_id {sorted(stdout_request_ids)!r} disagrees with "
                f"artifact request_id {request_id!r}"
            )
        if request_id is None and len(stdout_request_ids) == 1:
            request_id = next(iter(stdout_request_ids))
        status = "validated" if strict_canonical else ("legacy_mtime" if legacy_mode else "noncanonical")
        return ArtifactSet(
            output_dir=output_dir,
            run_artifact=run_artifact,
            summary_artifact=summary_artifact,
            campaign_manifest=campaign_manifest,
            console_capture=console_capture,
            run_artifacts=run_paths,
            v2ctl_invocation_id=invocation_id,
            request_id=request_id,
            request_ids=sorted(request_ids),
            profile=expected_profile if strict_canonical else None,
            profile_config_fingerprint=expected_profile_config_fingerprint,
            provenance_validation_status=status,
        )

    def _discover_golden_artifacts(
        self,
        config: "ResolvedConfig",
        backend_result_stdout: str,
        *,
        invocation_id: str | None,
        strict_canonical: bool,
        expected_profile: str | None,
        expected_profile_config_fingerprint: str | None,
    ) -> ArtifactSet:
        """Bind one Golden cohort emitted by the current backend process.

        Golden artifacts intentionally have their own schema.  They are not
        interchangeable with a generic ``run_*.json`` projection: selecting a
        stale external run would make the gate validate the wrong method and
        output.  The child must therefore identify its cohort in stdout, and
        that cohort must prove the resolved Golden identity and request ID.
        Detailed cohort validity remains the responsibility of the Golden
        validator; discovery only establishes the artifact binding.
        """
        if not strict_canonical:
            raise ProvenanceError(
                "Golden artifact discovery requires canonical invocation binding"
            )

        cohort_paths = {
            _normalize_logged_path(raw)
            for match in _OUTPUT_DIR_RE.finditer(backend_result_stdout or "")
            for raw in match.groups()
            if raw
        }
        manifest_paths = {
            _normalize_logged_path(match.group(1))
            for match in _MANIFEST_PATH_RE.finditer(backend_result_stdout or "")
        }
        if len(cohort_paths) > 1:
            raise ProvenanceError(
                "Golden backend stdout identifies multiple cohort output directories"
            )
        if len(manifest_paths) > 1:
            raise ProvenanceError(
                "Golden backend stdout identifies multiple cohort manifests"
            )
        if manifest_paths:
            manifest_from_stdout = next(iter(manifest_paths))
            manifest_cohort = manifest_from_stdout.parent
            if cohort_paths and next(iter(cohort_paths)).resolve() != manifest_cohort.resolve():
                raise ProvenanceError(
                    "Golden backend stdout cohort directory and manifest disagree"
                )
            cohort_paths.add(manifest_cohort)
        if len(cohort_paths) != 1:
            raise ProvenanceError(
                "Golden backend did not identify the current cohort output directory"
            )

        cohort_dir = next(iter(cohort_paths))
        if not cohort_dir.is_absolute():
            cohort_dir = self._repo_root / cohort_dir
        cohort_dir = cohort_dir.resolve()
        expected_profile_value = expected_profile or "golden_p1"
        target = getattr(config, "target", None)
        parallel = (
            expected_profile_value.strip().lower() == "golden_p1_parallel"
            or str(getattr(target, "method", "") or "").strip()
            == "run_golden_parallel_stream"
        )
        expected_mode = "golden_p1_parallel" if parallel else "golden_p1_serial"
        expected_method = (
            "run_golden_parallel_stream" if parallel else "run_golden_serial_stream"
        )
        expected_root = (
            self._repo_root / "artifacts" /
            ("phase_p1_parallel_golden_v1" if parallel else "phase_p1_serial_golden_v1")
        ).resolve()
        try:
            cohort_dir.relative_to(expected_root)
        except ValueError as exc:
            raise ProvenanceError(
                f"Golden cohort is outside the canonical artifact root: {cohort_dir}"
            ) from exc

        manifest = cohort_dir / "manifest.json"
        if manifest_paths and manifest.resolve() != next(iter(manifest_paths)).resolve():
            raise ProvenanceError(
                "Golden backend manifest path does not name cohort manifest.json"
            )
        try:
            manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as exc:
            raise ProvenanceError(f"Golden cohort manifest is unreadable: {manifest}") from exc
        if not isinstance(manifest_data, dict):
            raise ProvenanceError(f"Golden cohort manifest is not an object: {manifest}")

        def manifest_value(*names: str) -> str:
            nested = manifest_data.get("v2ctl")
            sources = (manifest_data, nested) if isinstance(nested, dict) else (manifest_data,)
            for source in sources:
                for name in names:
                    value = source.get(name)
                    if value is not None and str(value).strip():
                        return str(value).strip()
            return ""

        expected_invocation = str(invocation_id or "").strip()
        observed_invocation = manifest_value("v2ctl_invocation_id", "invocation_id")
        if observed_invocation != expected_invocation:
            raise ProvenanceError(
                "Golden cohort manifest invocation ID mismatch: "
                f"expected {expected_invocation!r}, observed {observed_invocation or '(missing)'} "
                f"at {manifest}"
            )
        observed_profile = manifest_value("profile", "profile_name")
        if observed_profile != expected_profile_value:
            raise ProvenanceError(
                "Golden cohort manifest profile mismatch: "
                f"expected {expected_profile_value!r}, observed {observed_profile or '(missing)'}"
            )
        if expected_profile_config_fingerprint:
            observed_profile_fp = manifest_value(
                "profile_config_fingerprint", "config_fingerprint", "profile_fingerprint"
            )
            if observed_profile_fp != expected_profile_config_fingerprint:
                raise ProvenanceError(
                    "Golden cohort manifest profile/config fingerprint mismatch: "
                    f"expected {expected_profile_config_fingerprint!r}, "
                    f"observed {observed_profile_fp or '(missing)'}"
                )

        expected_target = {
            "app_name": str(getattr(target, "app", "") or ""),
            "class_name": str(getattr(target, "class_name", "") or ""),
            "gpu": str(getattr(getattr(config, "resources", None), "gpu", "") or ""),
        }
        observed_target = manifest_data.get("target")
        if (
            manifest_data.get("mode") != expected_mode
            or manifest_data.get("method") != expected_method
            or (parallel and manifest_data.get("golden_mode") != "parallel")
            or not isinstance(observed_target, dict)
            or any(observed_target.get(key) != value for key, value in expected_target.items())
        ):
            raise ProvenanceError(
                f"Golden cohort identity does not match the requested configuration: {manifest}"
            )

        attempts = manifest_data.get("attempts")
        if not isinstance(attempts, list) or len(attempts) != 1:
            raise ProvenanceError(
                f"Golden cohort must contain exactly one gate/confirmation attempt: {manifest}"
            )
        attempt_files = sorted(
            (p for p in cohort_dir.glob("attempt_*.json") if not p.stem.endswith("_events")),
            key=lambda p: p.name.casefold(),
        )
        missing_expected = []
        if not attempt_files:
            missing_expected.append("attempt_*.json")
        if not (cohort_dir / "summary.json").is_file():
            missing_expected.append("summary.json")
        if missing_expected:
            raise ProvenanceError(
                "Golden expected artifacts missing: "
                + ", ".join(missing_expected)
                + f" at {cohort_dir}"
            )
        if len(attempt_files) != 1:
            raise ProvenanceError(
                f"Golden cohort must contain exactly one attempt artifact: {cohort_dir}"
            )
        attempt = attempt_files[0]
        try:
            attempt_data = json.loads(attempt.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as exc:
            raise ProvenanceError(f"Golden attempt artifact is unreadable: {attempt}") from exc
        if not isinstance(attempt_data, dict):
            raise ProvenanceError(f"Golden attempt artifact is not an object: {attempt}")
        request_id = str(attempt_data.get("request_id") or "").strip()
        if not request_id or str(attempts[0].get("request_id") or "").strip() != request_id:
            raise ProvenanceError(
                f"Golden cohort attempt/request identity is incomplete or inconsistent: {attempt}"
            )

        summary = cohort_dir / "summary.json"
        if not summary.is_file():
            raise ProvenanceError(
                f"Golden expected artifact missing: summary.json at {summary}"
            )
        try:
            summary_data = json.loads(summary.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as exc:
            raise ProvenanceError(f"Golden summary artifact is unreadable: {summary}") from exc
        if not isinstance(summary_data, dict):
            raise ProvenanceError(f"Golden summary artifact is not an object: {summary}")
        if not expected_invocation:
            raise ProvenanceError(
                "Golden cohort invocation ID is missing from the v2ctl binding"
            )
        for label, data in (("summary", summary_data), ("attempt", attempt_data)):
            observed = str(data.get("v2ctl_invocation_id") or "").strip()
            if not observed:
                raise ProvenanceError(
                    f"Golden {label} invocation ID is missing: "
                    f"{summary if label == 'summary' else attempt}"
                )
            if observed != expected_invocation:
                raise ProvenanceError(
                    f"Golden {label} invocation ID mismatch: expected {expected_invocation!r}, "
                    f"observed {observed!r} at {summary if label == 'summary' else attempt}"
                )
            observed_request = str(data.get("request_id") or "").strip()
            if observed_request and observed_request != request_id:
                raise ProvenanceError(
                    f"Golden {label} request ID mismatch: expected {request_id!r}, "
                    f"observed {observed_request!r}"
                )

        expected_backend = "pytorch"
        try:
            flag = config.flag("COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND")
            if flag is not None:
                expected_backend = str(getattr(flag, "value", flag)).strip().lower()
        except Exception:
            pass
        observed_backends: set[str] = set()
        for data in (manifest_data, summary_data, attempt_data):
            for key in ("attention_backend", "resolved_attention_backend"):
                value = data.get(key)
                if value not in (None, ""):
                    observed_backends.add(str(value).strip().lower())
            nested = data.get("golden_telemetry")
            if isinstance(nested, dict) and nested.get("attention_backend") not in (None, ""):
                observed_backends.add(str(nested["attention_backend"]).strip().lower())
        if len(observed_backends) > 1:
            raise ProvenanceError(
                "Golden cohort contains mixed attention backends: "
                + ", ".join(sorted(observed_backends))
            )
        if observed_backends and observed_backends != {expected_backend}:
            raise ProvenanceError(
                "Golden attention backend mismatch: "
                f"expected {expected_backend!r}, observed {sorted(observed_backends)}"
            )
        expected_qd2 = False
        try:
            flag = config.flag("COMFYMODAL_V2_GOLDEN_CPU_QD2_PREFETCH")
            expected_qd2 = str(getattr(flag, "value", flag) if flag is not None else "0") == "1"
        except Exception:
            pass
        expected_arm = "cpu_qd2_prefetch" if expected_qd2 else "control"
        observed_arms: set[str] = set()
        for data in (manifest_data, summary_data, attempt_data):
            if data.get("golden_arm") not in (None, ""):
                observed_arms.add(str(data["golden_arm"]).strip().lower())
            if "cpu_qd2_prefetch" in data:
                raw_qd2 = data["cpu_qd2_prefetch"]
                qd2_selected = (
                    raw_qd2 is True
                    or str(raw_qd2).strip().lower() in {"1", "true", "yes", "on"}
                )
                observed_arms.add(
                    "cpu_qd2_prefetch" if qd2_selected else "control"
                )
            nested_attempts = data.get("attempts")
            if isinstance(nested_attempts, list):
                for nested in nested_attempts:
                    if isinstance(nested, dict) and nested.get("golden_arm") not in (None, ""):
                        observed_arms.add(str(nested["golden_arm"]).strip().lower())
        if len(observed_arms) > 1:
            raise ProvenanceError(
                "Golden cohort contains mixed request arms: "
                + ", ".join(sorted(observed_arms))
            )
        if observed_arms and observed_arms != {expected_arm}:
            raise ProvenanceError(
                f"Golden request arm mismatch: expected {expected_arm!r}, "
                f"observed {sorted(observed_arms)}"
            )
        from .experiment_evidence import sage_runtime_identity

        sage_identity = sage_runtime_identity(
            config, manifest_data, summary_data, attempt_data,
        )
        stdout_request_ids = {
            value.strip()
            for value in re.findall(
                r"['\"]?(?:request_id|REQUEST_ID)['\"]?\s*[=:]\s*['\"]?([^\s,'\"}]+)",
                backend_result_stdout or "",
                flags=re.MULTILINE,
            )
            if value.strip()
        }
        # The Golden harness binds the current invocation through its unique
        # cohort directory and does not print the per-attempt request ID.  If
        # a request ID is present in stdout, still require an exact match; an
        # absent ID is not evidence of a second/stale cohort because the
        # printed cohort path was already required to be current and unique.
        if stdout_request_ids and stdout_request_ids != {request_id}:
            raise ProvenanceError(
                f"Golden stdout request ID does not bind the current attempt: "
                f"expected {request_id!r}, observed {sorted(stdout_request_ids)}"
            )

        return ArtifactSet(
            output_dir=cohort_dir,
            run_artifact=attempt,
            summary_artifact=summary,
            campaign_manifest=manifest,
            run_artifacts=[attempt],
            v2ctl_invocation_id=invocation_id,
            request_id=request_id,
            request_ids=[request_id],
            profile=expected_profile or "golden_p1",
            profile_config_fingerprint=expected_profile_config_fingerprint,
            attention_backend=next(iter(observed_backends), expected_backend),
            experiment_identity={
                "v2ctl_invocation_id": expected_invocation,
                "request_id": request_id,
                "profile": expected_profile_value,
                "profile_config_fingerprint": expected_profile_config_fingerprint or "",
                "attention_backend": next(iter(observed_backends), expected_backend),
                "golden_arm": next(iter(observed_arms), expected_arm),
                "cpu_qd2_prefetch": expected_qd2,
                **sage_identity,
            },
            provenance_validation_status="validated",
        )
