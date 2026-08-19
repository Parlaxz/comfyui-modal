"""Canonical backend registry/runner for the v2ctl control plane (E32).

Backends are the existing known-good BAT entry points:

* ``deploy_and_run_v2_single.bat`` — combined deploy+run (``kind="combined"``);
  the same BAT invoked with ``COMFYMODAL_DEPLOY_ONLY=1`` performs a
  deploy-only run (``kind="deploy_only_via_env"``);
* ``run_v2_single.bat`` — run-only backend (``kind="run"``).

``BackendRunner.run`` invokes the backend through ``subprocess`` with the
sanitized child environment and the repo root as cwd.  On win32 the command
is ``f'"{bat_path}" {list2cmdline(extra_args)}'`` executed via
``subprocess.run(..., shell=True)``; on posix it is a plain argv list
``[exe, *extra_args]``.

Artifacts are discovered best-effort under the well-known experiment output
candidates plus any ``output dir`` / ``output_dir`` line in the backend
stdout.

Python 3.11 stdlib only; no network calls, no modal/deploy invocations.
"""

from __future__ import annotations

import os
import platform
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .environment import EnvironmentBuilder
from .errors import BackendError

_OUTPUT_DIR_RE = re.compile(r"[Oo]utput[ _]?dir[=: ]+(\S+)")


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
        for spec in (self.canonical(), self.deploy_only(), self.run_only()):
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
    ) -> BackendResult:
        """Invoke the backend and return a BackendResult.

        ``extra_env`` is merged into the child environment AFTER config
        flags (e.g. ``COMFYMODAL_DEPLOY_ONLY=1`` from ``spec.deploy_only_env``
        and ``V2_BENCHMARK_RUNS=1`` from the gate runner).
        """
        child_env = self._env_builder.build(config, host_env=os.environ)
        if spec.deploy_only_env:
            child_env.update(spec.deploy_only_env)
        if extra_env:
            child_env.update(extra_env)

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
                        command,
                        shell=True,
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
        artifacts = self.discover_artifacts(config, stdout) if capture else ArtifactSet()
        return BackendResult(
            exit_code=completed.returncode,
            stdout=stdout,
            stderr=stderr,
            command=command,
            started_at=started_at,
            ended_at=ended_at,
            elapsed_seconds=elapsed_seconds,
            artifacts=artifacts,
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
        candidates.append(benchmark_runs_root)
        return [c for c in candidates if c.is_dir()]

    def discover_artifacts(
        self, config: "ResolvedConfig", backend_result_stdout: str
    ) -> ArtifactSet:
        """Best-effort artifact discovery.

        Candidates: the well-known experiment output dirs plus any path named
        by an ``output dir`` / ``output_dir`` line in the backend stdout
        matching the regex ``[Oo]utput[ _]?dir[=: ]+(\\S+)``.  Inside each
        candidate the newest ``run_*.json`` / ``summary*.json`` /
        ``campaign_manifest.json`` (by mtime) wins.  When no recognized
        artifact is found anywhere, every ArtifactSet field is ``None``.
        """
        candidate_dirs: list[Path] = []
        seen: set[Path] = set()
        for d in self._candidate_dirs(config):
            if d not in seen:
                candidate_dirs.append(d)
                seen.add(d)
        for match in _OUTPUT_DIR_RE.finditer(backend_result_stdout or ""):
            raw = match.group(1).strip().strip('"').strip("'")
            if not raw:
                continue
            p = Path(raw)
            if not p.is_absolute():
                p = self._repo_root / p
            if p not in seen:
                candidate_dirs.append(p)
                seen.add(p)

        output_dir: Path | None = None
        run_artifact: Path | None = None
        summary_artifact: Path | None = None
        campaign_manifest: Path | None = None
        now = time.time()

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
                    if name == "campaign_manifest.json":
                        if campaign_manifest is None or entry.stat().st_mtime > campaign_manifest.stat().st_mtime:
                            campaign_manifest = entry
                    elif name.startswith("run_") and name.endswith(".json"):
                        if run_artifact is None or entry.stat().st_mtime > run_artifact.stat().st_mtime:
                            run_artifact = entry
                    elif name.startswith("summary") and name.endswith(".json"):
                        if summary_artifact is None or entry.stat().st_mtime > summary_artifact.stat().st_mtime:
                            summary_artifact = entry

        # output_dir = parent of the winning artifact, else None (no
        # recognized artifacts -> every field stays None).
        for artifact in (run_artifact, summary_artifact, campaign_manifest):
            if artifact is not None:
                output_dir = artifact.parent
                break

        console_capture = None
        return ArtifactSet(
            output_dir=output_dir,
            run_artifact=run_artifact,
            summary_artifact=summary_artifact,
            campaign_manifest=campaign_manifest,
            console_capture=console_capture,
        )
