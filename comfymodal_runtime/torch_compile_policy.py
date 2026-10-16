"""Region-scoped torch.compile policy (UNWIRED — wire-ready only).

This module owns the compile *policy*: resolution, structural region
discovery, a thin lazy failure-aware target factory, a terminal fallback
latch, sampling-scope lifecycle helpers, and one-line aggregate
diagnostics.  It owns no executor wiring.

WIRE-READY ATTACH POINTS (owned by the sibling modal_app.py lane; this
module must stay unwired)::

    ON_PRE_RUN -> prepare_compile_targets(scope, diffusion_model=...)
    ON_DETACH  -> release_compile_targets(scope)
    install    -> install_sampling_compile_scope(policy=...)
    attach     -> attach_compile_policy(executor_state, policy)

Execution goes through KJNodes' EXISTING public wrapper path
(``comfy_api.torch_helpers.set_torch_compile_wrapper``).  This module
never copies KJ's registry and never adds a ``compile_factory`` to KJ
(third-party code).  It only holds a *reference* to the public wrapper
callable when the wiring lane injects one via ``compile_fn``.  Until the
wiring lane injects an applier, targets stay eager with reason
``no_compile_applier_wired``.

Hard rules:

* Default mode is ``off``.  Compile happens only after explicit
  readiness (``prepare_compile_targets``); never during snapshot capture
  (``snapshot_capturing=True`` forces eager).
* ``external_compile_owner`` (non-empty) and ``--disable-comfy-compiler``
  are hard disables: effective mode becomes ``off``.
* The legacy ``COMFYMODAL_ENABLE_TORCH_COMPILE`` flag is
  deprecate-not-OR: it never enables compilation.  When set it only
  produces diagnostics (``legacy_compile_flag_deprecated``, plus
  ``legacy_compile_flag_conflict`` when the new policy also requests a
  non-off mode).
* Fixed codegen contract: backend Inductor, ``fullgraph=False``, CUDA
  graphs off initially, upstream guards retained
  (``retain_upstream_guards=True``).
* Recompile budget is 8.  Exceeding it trips the scope latch terminally.

Definitions used by the aggregate ``[compile]`` line:

* ``requested`` — mode asked for by configuration.
* ``actual`` — effective mode after hard disables and validation.
* ``regions`` — structurally discovered compile regions.
* ``ready`` — regions with built lazy targets while the scope latch is
  READY (compile attempted at most once per region, lazily).
* ``eager`` — regions served without compilation.
* ``failed`` — scope-level flag (1 when the latch is EAGER_FAILED).
* ``recompiles`` — observed recompiles this scope vs budget.
* ``cache`` — cache *routing* (namespace/dir to use).  Hits are owned
  and reported upstream; this module never claims hits.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .env import env_flag


# ---------------------------------------------------------------------------
# Policy constants
# ---------------------------------------------------------------------------

COMPILE_MODES = ("off", "regional", "full")
COMPILE_DYNAMIC_MODES = ("auto", "true", "false")

DEFAULT_MODE = "off"
DEFAULT_DYNAMIC = "auto"
DEFAULT_RECOMPILE_BUDGET = 8

COMPILE_BACKEND = "inductor"
COMPILE_FULLGRAPH = False
COMPILE_USE_CUDA_GRAPHS = False
RETAIN_UPSTREAM_GUARDS = True

ENV_MODE = "COMFYMODAL_TORCH_COMPILE_MODE"
ENV_DYNAMIC = "COMFYMODAL_TORCH_COMPILE_DYNAMIC"
ENV_DEBUG = "COMFYMODAL_TORCH_COMPILE_DEBUG"
ENV_BUDGET = "COMFYMODAL_TORCH_COMPILE_RECOMPILE_BUDGET"
ENV_DISABLE = "COMFYMODAL_DISABLE_COMFY_COMPILER"
LEGACY_ENV = "COMFYMODAL_ENABLE_TORCH_COMPILE"
DISABLE_CLI_FLAG = "--disable-comfy-compiler"

# Structural container names examined on the effective patched
# diffusion_model, in priority order.  This is a structural allow-list,
# never a model-name switch: model class/checkpoint names are ignored.
CANDIDATE_CONTAINERS = (
    "double_blocks",
    "single_blocks",
    "layers",
    "transformer_blocks",
    "blocks",
)

MIN_BLOCKS_PER_REGION = 2

# Fallback latch states.  UNTRIED is the pre-prepare state.  READY is the
# armed state (prepare succeeded).  EAGER_FAILED / EAGER_SKIPPED are
# terminal: no whole-executor replay, no retry-per-step.  The only allowed
# moves are UNTRIED -> READY / EAGER_* and the one-way trip
# READY -> EAGER_FAILED / EAGER_SKIPPED (a runtime failure or budget trip
# disarms an armed scope permanently).
LATCH_UNTRIED = "UNTRIED"
LATCH_READY = "READY"
LATCH_EAGER_FAILED = "EAGER_FAILED"
LATCH_EAGER_SKIPPED = "EAGER_SKIPPED"

KJ_CAPABILITY_MISSING = "kj_capability_missing"


# ---------------------------------------------------------------------------
# Immutable policy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CompilePolicy:
    """Immutable compile policy (requested vs effective mode)."""

    requested_mode: str = DEFAULT_MODE
    mode: str = DEFAULT_MODE
    dynamic: str = DEFAULT_DYNAMIC
    debug: bool = False
    recompile_budget: int = DEFAULT_RECOMPILE_BUDGET
    backend: str = COMPILE_BACKEND
    fullgraph: bool = COMPILE_FULLGRAPH
    use_cuda_graphs: bool = COMPILE_USE_CUDA_GRAPHS
    retain_upstream_guards: bool = RETAIN_UPSTREAM_GUARDS
    external_compile_owner: str = ""
    hard_disabled: bool = False
    hard_disable_reason: str = ""


def _coerce_mode(raw: Any) -> str | None:
    if isinstance(raw, str) and raw.strip().lower() in COMPILE_MODES:
        return raw.strip().lower()
    return None


def _coerce_dynamic(raw: Any) -> str | None:
    if isinstance(raw, str) and raw.strip().lower() in COMPILE_DYNAMIC_MODES:
        return raw.strip().lower()
    return None


def _coerce_budget(raw: Any) -> int | None:
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError, AttributeError):
        return None
    return value if value >= 0 else None


def resolve_compile_policy(
    *,
    env: Mapping[str, str] | None = None,
    argv: Any = None,
    external_compile_owner: str = "",
    disable_comfy_compiler: bool | None = None,
) -> tuple[CompilePolicy, dict[str, Any]]:
    """Resolve the effective compile policy from configuration.

    ``env`` defaults to ``os.environ``; pass an explicit mapping in
    tests.  ``argv`` defaults to ``sys.argv[1:]`` and is scanned
    read-only for ``--disable-comfy-compiler``.  ``disable_comfy_compiler``
    explicitly passed by the wiring lane wins over the environment.
    """
    source = os.environ if env is None else env
    reasons: list[str] = []

    raw_mode = source.get(ENV_MODE) if isinstance(source, Mapping) else None
    mode_explicit = raw_mode is not None and str(raw_mode).strip() != ""
    requested = _coerce_mode(raw_mode) if mode_explicit else DEFAULT_MODE
    invalid_mode = mode_explicit and requested is None
    if invalid_mode:
        reasons.append("invalid_mode")
        requested = DEFAULT_MODE

    raw_dynamic = source.get(ENV_DYNAMIC) if isinstance(source, Mapping) else None
    dynamic = _coerce_dynamic(raw_dynamic) if raw_dynamic is not None else DEFAULT_DYNAMIC
    invalid_dynamic = raw_dynamic is not None and dynamic is None
    if invalid_dynamic:
        reasons.append("invalid_dynamic")
        dynamic = DEFAULT_DYNAMIC

    debug = bool(env_flag(ENV_DEBUG)) if env is None else _mapping_flag(source, ENV_DEBUG)

    raw_budget = source.get(ENV_BUDGET) if isinstance(source, Mapping) else None
    budget = _coerce_budget(raw_budget) if raw_budget is not None else DEFAULT_RECOMPILE_BUDGET
    invalid_budget = raw_budget is not None and budget is None
    if invalid_budget:
        reasons.append("invalid_recompile_budget")
        budget = DEFAULT_RECOMPILE_BUDGET

    legacy_set = bool(env_flag(LEGACY_ENV)) if env is None else _mapping_flag(source, LEGACY_ENV)
    legacy_conflict = bool(legacy_set and (requested != DEFAULT_MODE))
    if legacy_set:
        # Deprecate-not-OR: the legacy flag never enables compilation.
        reasons.append("legacy_compile_flag_deprecated")
    if legacy_conflict:
        reasons.append("legacy_compile_flag_conflict")

    owner = (external_compile_owner or "").strip()
    if argv is None:
        cli_args: list[str] = list(sys.argv[1:])
    elif isinstance(argv, str):
        cli_args = argv.split()
    else:
        cli_args = list(argv)
    if disable_comfy_compiler is None:
        if env is None:
            cli_disabled = env_flag(ENV_DISABLE) or DISABLE_CLI_FLAG in cli_args
        else:
            cli_disabled = _mapping_flag(source, ENV_DISABLE) or DISABLE_CLI_FLAG in cli_args
    else:
        cli_disabled = bool(disable_comfy_compiler)

    hard_disabled = False
    hard_disable_reason = ""
    if owner:
        hard_disabled = True
        hard_disable_reason = "external_compile_owner"
        reasons.append("external_compile_owner")
    elif cli_disabled:
        hard_disabled = True
        hard_disable_reason = "disable_comfy_compiler"
        reasons.append("disable_comfy_compiler")

    actual = DEFAULT_MODE if hard_disabled else str(requested)
    if not hard_disabled and actual == DEFAULT_MODE and not reasons:
        reasons.append("off_by_default")

    if budget is None:
        effective_budget = DEFAULT_RECOMPILE_BUDGET
    else:
        effective_budget = int(budget)
    policy = CompilePolicy(
        requested_mode=str(requested),
        mode=actual,
        dynamic=str(dynamic),
        debug=debug,
        recompile_budget=effective_budget,
        external_compile_owner=owner,
        hard_disabled=hard_disabled,
        hard_disable_reason=hard_disable_reason,
    )
    diagnostics = {
        "requested_mode": policy.requested_mode,
        "actual_mode": policy.mode,
        "dynamic": policy.dynamic,
        "debug": policy.debug,
        "recompile_budget": policy.recompile_budget,
        "hard_disabled": hard_disabled,
        "hard_disable_reason": hard_disable_reason,
        "legacy_flag_set": legacy_set,
        "legacy_conflict": legacy_conflict,
        "invalid_mode": bool(invalid_mode),
        "invalid_dynamic": bool(invalid_dynamic),
        "invalid_budget": bool(invalid_budget),
        "reasons": reasons,
    }
    return policy, diagnostics


def _mapping_flag(source: Mapping[str, str], name: str) -> bool:
    raw = source.get(name)
    if raw is None:
        return False
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# Structural region discovery (no model-name switches)
# ---------------------------------------------------------------------------


def _as_block_sequence(value: Any) -> list[Any] | None:
    """Return container contents as a list, or None if not sequence-like."""
    if value is None or isinstance(value, (str, bytes, bytearray, dict)):
        return None
    if isinstance(value, (list, tuple)):
        return list(value)
    if hasattr(value, "__len__") and hasattr(value, "__getitem__"):
        try:
            raw_count: Any = len(value)  # type: ignore[arg-type]
            count = int(raw_count)
        except Exception:
            return None
        try:
            return [value[i] for i in range(count)]
        except Exception:
            return None
    return None


def _is_compatible_block(block: Any) -> bool:
    """A block is compatible when it is callable or exposes ``forward``."""
    if callable(block):
        return True
    return callable(getattr(block, "forward", None))


def _block_has_children(block: Any) -> bool:
    """Structural nontriviality probe (no framework imports)."""
    modules = getattr(block, "_modules", None)
    if isinstance(modules, Mapping) and len(modules) > 0:
        return True
    for accessor in ("children", "named_children"):
        probe = getattr(block, accessor, None)
        if callable(probe):
            try:
                produced: Any = probe()
                items = list(produced)
            except Exception:
                continue
            if len(items) > 0:
                return True
    try:
        namespace = vars(block)
    except TypeError:
        return False
    for value in namespace.values():
        if value is block:
            continue
        if callable(getattr(value, "forward", None)):
            return True
        if isinstance(value, (list, tuple)) and value and all(
            callable(getattr(item, "forward", None)) for item in value
        ):
            return True
    return False


def _validate_container(name: str, value: Any) -> tuple[list[Any] | None, str]:
    """Validate one candidate container; return (blocks, reject_reason)."""
    items = _as_block_sequence(value)
    if items is None:
        return None, "not_sequence"
    if len(items) < MIN_BLOCKS_PER_REGION:
        return None, "too_few_blocks"
    for block in items:
        if not _is_compatible_block(block):
            return None, "incompatible_block"
        if not _block_has_children(block):
            return None, "leaf_blocks"
    type_names = {type(block).__name__ for block in items}
    if len(type_names) > 1:
        return None, "heterogeneous_blocks"
    return items, ""


def discover_compile_regions(diffusion_model: Any) -> dict[str, Any]:
    """Discover compile regions structurally over ``diffusion_model``.

    Only the attribute names in :data:`CANDIDATE_CONTAINERS` are examined;
    model class names, checkpoint names, and request metadata are never
    consulted.  Overlapping-but-not-identical containers are ambiguous and
    yield ``supported=False`` with reason
    ``ambiguous_overlapping_regions``.  Fully aliased containers (same
    blocks reachable under two names) are deduped to the first candidate.
    """
    examined: list[str] = []
    rejected: dict[str, str] = {}
    valid: list[tuple[str, list[Any]]] = []
    for name in CANDIDATE_CONTAINERS:
        try:
            value = getattr(diffusion_model, name, None)
        except Exception:
            rejected[name] = "unreadable"
            continue
        if value is None:
            continue
        examined.append(name)
        blocks, reason = _validate_container(name, value)
        if blocks is None:
            rejected[name] = reason
        else:
            valid.append((name, blocks))

    deduped_aliases: list[str] = []
    regions: list[dict[str, Any]] = []
    covered: set[int] = set()
    for name, blocks in valid:
        ids = {id(block) for block in blocks}
        if ids <= covered:
            deduped_aliases.append(name)
            continue
        if ids & covered:
            return {
                "supported": False,
                "regions": [],
                "reason": "ambiguous_overlapping_regions",
                "examined": examined,
                "rejected": rejected,
                "deduped_aliases": deduped_aliases,
            }
        covered |= ids
        regions.append(
            {
                "container": name,
                "path": f"diffusion_model.{name}",
                "block_count": len(blocks),
                "block_type": type(blocks[0]).__name__,
            }
        )

    if not regions:
        return {
            "supported": False,
            "regions": [],
            "reason": "no_supported_regions",
            "examined": examined,
            "rejected": rejected,
            "deduped_aliases": deduped_aliases,
        }
    return {
        "supported": True,
        "regions": regions,
        "reason": "ok",
        "examined": examined,
        "rejected": rejected,
        "deduped_aliases": deduped_aliases,
    }


# ---------------------------------------------------------------------------
# KJ capability probe (reference only — never copy KJ's registry)
# ---------------------------------------------------------------------------

KJ_WRAPPER_PROBES = (
    ("comfy_api.torch_helpers", "set_torch_compile_wrapper"),
)


def probe_kj_compile_capability(
    *,
    importer: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    """Check whether KJNodes' existing public wrapper path is importable.

    Returns ``{"available", "reason", "wrapper", "source"}``.  ``wrapper``
    is a borrowed reference to the public callable, never a copy of any
    registry.  Missing capability reports reason ``kj_capability_missing``
    and callers must stay eager.
    """
    def _default_import(name: str) -> Any:
        import importlib

        return importlib.import_module(name)

    load = importer if importer is not None else _default_import
    for module_name, attr in KJ_WRAPPER_PROBES:
        try:
            module = load(module_name)
        except Exception:
            continue
        wrapper = getattr(module, attr, None)
        if callable(wrapper):
            return {
                "available": True,
                "reason": "ok",
                "wrapper": wrapper,
                "source": f"{module_name}.{attr}",
            }
        return {
            "available": False,
            "reason": KJ_CAPABILITY_MISSING,
            "wrapper": None,
            "source": f"{module_name}.{attr}",
        }
    return {
        "available": False,
        "reason": KJ_CAPABILITY_MISSING,
        "wrapper": None,
        "source": "",
    }


# ---------------------------------------------------------------------------
# Terminal fallback latch
# ---------------------------------------------------------------------------


class CompileFallbackLatch:
    """Scope-level latch: UNTRIED -> READY -> EAGER_* (one-way, terminal)."""

    STATES = (LATCH_UNTRIED, LATCH_READY, LATCH_EAGER_FAILED, LATCH_EAGER_SKIPPED)

    _ALLOWED_MOVES = frozenset(
        {
            (LATCH_UNTRIED, LATCH_READY),
            (LATCH_UNTRIED, LATCH_EAGER_FAILED),
            (LATCH_UNTRIED, LATCH_EAGER_SKIPPED),
            # One-way trip: a runtime failure or budget trip permanently
            # disarms an armed scope.  Nothing leaves EAGER_*.
            (LATCH_READY, LATCH_EAGER_FAILED),
            (LATCH_READY, LATCH_EAGER_SKIPPED),
        }
    )

    def __init__(self) -> None:
        self._state = LATCH_UNTRIED
        self._reason = ""
        self._ignored_transitions = 0

    @property
    def state(self) -> str:
        return self._state

    @property
    def reason(self) -> str:
        return self._reason

    @property
    def terminal(self) -> bool:
        return self._state != LATCH_UNTRIED

    @property
    def should_attempt_compile(self) -> bool:
        return self._state == LATCH_READY

    @property
    def ignored_transitions(self) -> int:
        return self._ignored_transitions

    def transition(self, to_state: str, reason: str = "") -> bool:
        if to_state not in self.STATES or to_state == LATCH_UNTRIED:
            return False
        if (self._state, to_state) not in self._ALLOWED_MOVES:
            self._ignored_transitions += 1
            return False
        self._state = to_state
        self._reason = reason
        return True

    def mark_ready(self, reason: str = "prepared") -> bool:
        return self.transition(LATCH_READY, reason)

    def mark_eager_failed(self, reason: str) -> bool:
        return self.transition(LATCH_EAGER_FAILED, reason)

    def mark_eager_skipped(self, reason: str) -> bool:
        return self.transition(LATCH_EAGER_SKIPPED, reason)

    def reset(self) -> None:
        """Explicit reset for a brand-new scope only; never per-step."""
        self._state = LATCH_UNTRIED
        self._reason = ""


# ---------------------------------------------------------------------------
# Thin lazy failure-aware target factory
# ---------------------------------------------------------------------------


def make_compile_target(
    block: Any,
    *,
    policy: CompilePolicy,
    compile_fn: Callable[[Any, CompilePolicy], Any] | None = None,
    latch: CompileFallbackLatch | None = None,
    kj_probe: Callable[[], dict[str, Any]] | None = None,
    region: str = "",
) -> Callable[..., Any]:
    """Build a lazy per-block target that falls back to eager on failure.

    Nothing is compiled at build time.  On first invocation the factory
    attempts ``compile_fn(block, policy)`` exactly once when the latch is
    READY; any exception trips the latch to EAGER_FAILED (terminal) and
    all calls — current and future — run eager.  There is no retry
    per-step and no whole-executor replay.
    """
    own_latch = latch if latch is not None else CompileFallbackLatch()
    slot: dict[str, Any] = {"attempted": False, "compiled": None}

    def _eager(*args: Any, **kwargs: Any) -> Any:
        if callable(block):
            return block(*args, **kwargs)
        forward = getattr(block, "forward", None)
        if callable(forward):
            return forward(*args, **kwargs)
        raise TypeError(f"region {region!r}: block is not callable")

    def target(*args: Any, **kwargs: Any) -> Any:
        if own_latch.state != LATCH_READY:
            return _eager(*args, **kwargs)
        if slot["compiled"] is not None:
            compiled = slot["compiled"]
            if callable(compiled):
                return compiled(*args, **kwargs)
            forward = getattr(compiled, "forward", None)
            if callable(forward):
                return forward(*args, **kwargs)
            return _eager(*args, **kwargs)
        if slot["attempted"]:
            return _eager(*args, **kwargs)
        slot["attempted"] = True
        applier = compile_fn
        if applier is None:
            probe = (kj_probe() if kj_probe is not None else probe_kj_compile_capability())
            if not probe.get("available"):
                own_latch.mark_eager_skipped(KJ_CAPABILITY_MISSING)
                return _eager(*args, **kwargs)
            own_latch.mark_eager_skipped("no_compile_applier_wired")
            return _eager(*args, **kwargs)
        try:
            slot["compiled"] = applier(block, policy)
        except Exception as exc:
            own_latch.mark_eager_failed(f"compile_failed:{type(exc).__name__}")
            return _eager(*args, **kwargs)
        return target(*args, **kwargs)

    return target


# ---------------------------------------------------------------------------
# Sampling-scope lifecycle (attach points for the modal_app.py lane)
# ---------------------------------------------------------------------------


def install_sampling_compile_scope(
    *,
    policy: CompilePolicy,
    cache_namespace: str = "",
    cache_dir: str = "",
    scope_id: str = "",
) -> dict[str, Any]:
    """Create a sampling scope.  Never compiles; readiness comes later."""
    return {
        "scope_id": scope_id,
        "policy": policy,
        "requested_mode": policy.requested_mode,
        "actual_mode": policy.mode,
        "ready": False,
        "regions": [],
        "targets": [],
        "latch": CompileFallbackLatch(),
        "recompiles_observed": 0,
        "over_budget": False,
        "cache_namespace": cache_namespace,
        "cache_dir": cache_dir,
        "released": False,
        "events": ["installed"],
    }


def attach_compile_policy(executor_state: Any, policy: CompilePolicy) -> dict[str, Any]:
    """Attach ``policy`` to executor state (mapping or attribute object)."""
    try:
        if hasattr(executor_state, "__setitem__"):
            executor_state["compile_policy"] = policy
            return {"attached": True, "via": "mapping", "policy_mode": policy.mode}
        setattr(executor_state, "compile_policy", policy)
        return {"attached": True, "via": "attribute", "policy_mode": policy.mode}
    except Exception as exc:
        return {"attached": False, "via": "none", "reason": type(exc).__name__}


def prepare_compile_targets(
    scope: dict[str, Any],
    *,
    diffusion_model: Any = None,
    kj_probe: Callable[[], dict[str, Any]] | None = None,
    compile_fn: Callable[[Any, CompilePolicy], Any] | None = None,
    snapshot_capturing: bool = False,
    external_compile_owner: str = "",
) -> dict[str, Any]:
    """ON_PRE_RUN attach point: arm lazy targets after explicit readiness.

    Never runs during snapshot capture.  Builds lazy factories only; the
    first real compilation attempt happens on first block invocation.
    """
    policy = scope.get("policy")
    latch = scope.get("latch")
    if not isinstance(policy, CompilePolicy) or not isinstance(latch, CompileFallbackLatch):
        return {"prepared": False, "ready": False, "reason": "invalid_scope"}
    if scope.get("released"):
        latch.mark_eager_skipped("already_released")
        return {"prepared": False, "ready": False, "reason": "already_released",
                "latch_state": latch.state}
    if snapshot_capturing:
        latch.mark_eager_skipped("snapshot_capture_active")
        scope["events"].append("prepare_skipped_snapshot_capture")
        return {"prepared": False, "ready": False, "reason": "snapshot_capture_active",
                "latch_state": latch.state}
    if policy.mode == DEFAULT_MODE:
        latch.mark_eager_skipped("mode_off")
        scope["events"].append("prepare_skipped_mode_off")
        return {"prepared": False, "ready": False, "reason": "mode_off",
                "latch_state": latch.state}
    owner = (external_compile_owner or policy.external_compile_owner or "").strip()
    if owner:
        latch.mark_eager_skipped("external_compile_owner")
        scope["events"].append("prepare_skipped_external_owner")
        return {"prepared": False, "ready": False, "reason": "external_compile_owner",
                "latch_state": latch.state}
    if diffusion_model is None:
        latch.mark_eager_skipped("no_diffusion_model")
        return {"prepared": False, "ready": False, "reason": "no_diffusion_model",
                "latch_state": latch.state}

    discovery = discover_compile_regions(diffusion_model)
    scope["regions"] = discovery["regions"]
    if not discovery["supported"]:
        latch.mark_eager_skipped(discovery["reason"])
        scope["events"].append(f"prepare_skipped_{discovery['reason']}")
        return {"prepared": False, "ready": False, "reason": discovery["reason"],
                "latch_state": latch.state, "discovery": discovery}

    probe = kj_probe() if kj_probe is not None else probe_kj_compile_capability()
    if not probe.get("available"):
        latch.mark_eager_skipped(KJ_CAPABILITY_MISSING)
        scope["events"].append("prepare_skipped_kj_capability_missing")
        return {"prepared": False, "ready": False, "reason": KJ_CAPABILITY_MISSING,
                "latch_state": latch.state, "discovery": discovery,
                "kj_available": False}

    # Resolve the concrete blocks for factory construction by re-reading
    # the validated containers (structural only, same accessors).
    targets: list[dict[str, Any]] = []
    for region in discovery["regions"]:
        container = getattr(diffusion_model, region["container"])
        items = _as_block_sequence(container) or []
        for index, block in enumerate(items):
            targets.append(
                {
                    "region": region["container"],
                    "block_index": index,
                    "factory": make_compile_target(
                        block,
                        policy=policy,
                        compile_fn=compile_fn,
                        latch=latch,
                        region=region["container"],
                    ),
                }
            )
    scope["targets"] = targets
    latch.mark_ready("prepared")
    scope["ready"] = True
    scope["events"].append("prepared")
    return {
        "prepared": True,
        "ready": True,
        "reason": "prepared",
        "regions": discovery["regions"],
        "targets_built": len(targets),
        "latch_state": latch.state,
        "discovery": discovery,
        "kj_available": True,
    }


def finish_compile_sample(scope: dict[str, Any], *, recompiles_observed: int = 0) -> dict[str, Any]:
    """Record end-of-sample recompile counts; trip the latch over budget."""
    policy = scope.get("policy")
    latch = scope.get("latch")
    budget = policy.recompile_budget if isinstance(policy, CompilePolicy) else DEFAULT_RECOMPILE_BUDGET
    try:
        observed = int(recompiles_observed)
    except (TypeError, ValueError):
        observed = 0
    observed = max(0, observed)
    scope["recompiles_observed"] = observed
    over_budget = observed > budget
    scope["over_budget"] = over_budget
    if over_budget and isinstance(latch, CompileFallbackLatch) and latch.state == LATCH_READY:
        latch.mark_eager_failed("recompile_budget_exceeded")
    scope["events"].append("finished")
    return {
        "recompiles_observed": observed,
        "recompile_budget": budget,
        "over_budget": over_budget,
        "latch_state": latch.state if isinstance(latch, CompileFallbackLatch) else "unknown",
    }


def release_compile_targets(scope: dict[str, Any]) -> dict[str, Any]:
    """ON_DETACH attach point: drop compiled refs; idempotent, never raises."""
    try:
        if scope.get("released"):
            return {"released": True, "already": True}
        scope["targets"] = []
        scope["ready"] = False
        scope["released"] = True
        events = scope.get("events")
        if isinstance(events, list):
            events.append("released")
        return {"released": True, "already": False}
    except Exception:
        return {"released": False, "already": False}


# ---------------------------------------------------------------------------
# Diagnostics: one aggregate [compile] line per sampling scope
# ---------------------------------------------------------------------------


def summarize_compile_sample(scope: dict[str, Any], *, debug: bool = False) -> dict[str, Any]:
    """Build the single aggregate diagnostic for one sampling scope."""
    policy = scope.get("policy")
    latch = scope.get("latch")
    regions = scope.get("regions") or []
    targets = scope.get("targets") or []
    observed = int(scope.get("recompiles_observed") or 0)
    latch_state = latch.state if isinstance(latch, CompileFallbackLatch) else "unknown"
    if isinstance(policy, CompilePolicy):
        requested = policy.requested_mode
        actual = policy.mode
        budget = policy.recompile_budget
    else:
        requested, actual, budget = "unknown", "unknown", DEFAULT_RECOMPILE_BUDGET
    ready_count = len(targets) if (latch_state == LATCH_READY and scope.get("ready")) else 0
    eager_count = max(0, len(regions) - ready_count) if regions else (0 if ready_count else 0)
    if not regions and latch_state in (LATCH_EAGER_SKIPPED, LATCH_EAGER_FAILED):
        eager_count = 0
    failed = 1 if latch_state == LATCH_EAGER_FAILED else 0
    namespace = scope.get("cache_namespace") or "unrouted"
    line = (
        f"[compile] requested={requested} actual={actual} "
        f"regions={len(regions)} ready={ready_count} eager={eager_count} "
        f"failed={failed} recompiles={observed}/{budget} cache={namespace}"
    )
    details: dict[str, Any] = {
        "requested": requested,
        "actual": actual,
        "regions_total": len(regions),
        "ready": ready_count,
        "eager": eager_count,
        "failed": failed,
        "recompiles_observed": observed,
        "recompile_budget": budget,
        "latch_state": latch_state,
        "latch_reason": latch.reason if isinstance(latch, CompileFallbackLatch) else "",
        # Cache ROUTING only — never a hit claim (hits are upstream-owned).
        "cache": {
            "namespace": scope.get("cache_namespace") or "",
            "dir": scope.get("cache_dir") or "",
            "hits_claimed": False,
        },
    }
    if debug:
        details["targets"] = [
            {"region": item.get("region"), "block_index": item.get("block_index")}
            for item in targets
        ]
        details["regions"] = regions
        details["events"] = list(scope.get("events") or [])
    return {"line": line, "details": details}
