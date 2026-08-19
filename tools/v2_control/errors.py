"""Exception hierarchy for the v2ctl control plane (Batch E32)."""


class V2CtlError(Exception):
    """Base class for all v2ctl failures."""


class FlagError(V2CtlError):
    """Invalid flag syntax, type, or lifecycle violation."""


class ProtectedVarError(V2CtlError):
    """Attempt to override a protected variable."""


class ProfileError(V2CtlError):
    """Profile missing, cyclic, or with multiple parents."""


class LockHeldError(V2CtlError):
    """Deploy lock is held by a conflicting owner."""

    def __init__(
        self,
        message: str,
        *,
        owner: str | None = None,
        pid: int | None = None,
        host: str | None = None,
        target: str | None = None,
        profile: str | None = None,
        timestamp: str | None = None,
    ) -> None:
        super().__init__(message)
        self.owner = owner
        self.pid = pid
        self.host = host
        self.target = target
        self.profile = profile
        self.timestamp = timestamp


class LockStaleError(V2CtlError):
    """Lock exists but is stale; explicit force is required."""


class RuntimeOverrideViolation(V2CtlError):
    """Runtime flag files would silently contaminate a benchmark."""

    def __init__(self, message: str, overrides: list | None = None) -> None:
        super().__init__(message)
        self.overrides = overrides or []


class BackendError(V2CtlError):
    """Canonical backend invocation failed."""


class DeployCrashLoopError(V2CtlError):
    """The deployed container is crash-looping (repeated identical
    tracebacks observed in the deploy output).  The deployment must not be
    treated as successful: STOP, diagnose the root cause, fix locally, and
    redeploy.  Never auto-retry a crash loop."""

    def __init__(self, message: str, *, exception_type: str = "", count: int = 0) -> None:
        super().__init__(message)
        self.exception_type = exception_type
        self.count = count


class GateError(V2CtlError):
    """Gate/confirm protocol violation."""
