"""Fast unit tests for the unwired torch.compile policy + compiler cache.

Dependency-free: stdlib plus the two new runtime modules only.  No
torch / Comfy / Modal imports at module scope (top-level heavy imports
would trip the FAST_UNIT collection guard).

Coverage: policy resolution (invalid / legacy-conflict / hard disables),
structural discovery over synthetic module trees (five family fixtures,
unfamiliar / heterogeneous / alias / overlap / leaf cases), lifecycle
ordering via fakes, latch terminality, cache namespace purity and prune
ordering, and the aggregate diagnostics shape.

The ``RealKjWrapperIntegrationTests`` class at the end is explicitly
NOT fast_unit (marked heavy_local, torch/comfy imported lazily inside
the tests and skipped when absent).  It exercises the real KJ wrapper
probe path and documents any KJ capability gap.
"""

from __future__ import annotations

import dataclasses
import os
import sys
import tempfile
import time
import unittest
from typing import Any

import pytest

from comfymodal_runtime import compiler_cache as cc
from comfymodal_runtime import torch_compile_policy as tcp

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


# ---------------------------------------------------------------------------
# Synthetic module-tree fakes (structural only — never model names)
# ---------------------------------------------------------------------------


class _Leaf:
    """Callable leaf with no children (must be rejected as a region)."""

    def __call__(self, *args, **kwargs):
        return ("leaf", args, kwargs)


class _Block:
    """Callable block with nontrivial children."""

    def __init__(self, tag: str = "block", width: int = 2):
        self.tag = tag
        self._modules = {f"sub{i}": object() for i in range(width)}

    def __call__(self, *args, **kwargs):
        return ("eager", self.tag)


class _OtherBlock(_Block):
    """Distinct type used to build heterogeneous containers."""


class _ForwardOnlyBlock:
    """Not callable itself, but exposes a callable forward + children."""

    def __init__(self):
        self._modules = {"proj": object()}

    def forward(self, *args, **kwargs):
        return ("forward-eager",)


class _Model:
    def __init__(self, **containers):
        for name, value in containers.items():
            setattr(self, name, value)


def _blocks(n, cls=_Block):
    return [cls(tag=f"b{i}") for i in range(n)]


def _kj_available(**overrides):
    probe = {"available": True, "reason": "ok", "wrapper": object(), "source": "fake"}
    probe.update(overrides)
    return lambda: dict(probe)


def _regional_policy(**overrides: Any):
    kwargs: dict[str, Any] = {"requested_mode": "regional", "mode": "regional"}
    kwargs.update(overrides)
    return tcp.CompilePolicy(**kwargs)


# ---------------------------------------------------------------------------
# Policy resolution
# ---------------------------------------------------------------------------


@pytest.mark.fast_unit
class PolicyResolutionTests(unittest.TestCase):
    def test_defaults_are_off(self):
        policy, diag = tcp.resolve_compile_policy(env={}, argv=[])
        self.assertEqual(policy.mode, "off")
        self.assertEqual(policy.requested_mode, "off")
        self.assertEqual(policy.dynamic, "auto")
        self.assertFalse(policy.debug)
        self.assertEqual(policy.recompile_budget, 8)
        self.assertEqual(policy.backend, "inductor")
        self.assertFalse(policy.fullgraph)
        self.assertFalse(policy.use_cuda_graphs)
        self.assertTrue(policy.retain_upstream_guards)
        self.assertFalse(policy.hard_disabled)
        self.assertEqual(diag["actual_mode"], "off")

    def test_regional_and_full_accepted(self):
        for mode in ("regional", "full"):
            policy, _ = tcp.resolve_compile_policy(env={tcp.ENV_MODE: mode}, argv=[])
            self.assertEqual(policy.requested_mode, mode)
            self.assertEqual(policy.mode, mode)

    def test_invalid_mode_fails_closed_to_off(self):
        policy, diag = tcp.resolve_compile_policy(env={tcp.ENV_MODE: "turbo"}, argv=[])
        self.assertEqual(policy.mode, "off")
        self.assertTrue(diag["invalid_mode"])
        self.assertIn("invalid_mode", diag["reasons"])

    def test_invalid_dynamic_and_budget_fall_back(self):
        policy, diag = tcp.resolve_compile_policy(
            env={tcp.ENV_DYNAMIC: "sometimes", tcp.ENV_BUDGET: "many"}, argv=[]
        )
        self.assertEqual(policy.dynamic, "auto")
        self.assertEqual(policy.recompile_budget, 8)
        self.assertTrue(diag["invalid_dynamic"])
        self.assertTrue(diag["invalid_budget"])

    def test_legacy_flag_alone_never_enables(self):
        # Deprecate-not-OR: legacy=1 with no new-mode request stays off.
        policy, diag = tcp.resolve_compile_policy(env={tcp.LEGACY_ENV: "1"}, argv=[])
        self.assertEqual(policy.mode, "off")
        self.assertTrue(diag["legacy_flag_set"])
        self.assertFalse(diag["legacy_conflict"])
        self.assertIn("legacy_compile_flag_deprecated", diag["reasons"])

    def test_legacy_conflict_diagnostic_new_policy_wins(self):
        policy, diag = tcp.resolve_compile_policy(
            env={tcp.LEGACY_ENV: "1", tcp.ENV_MODE: "regional"}, argv=[]
        )
        self.assertEqual(policy.mode, "regional")
        self.assertTrue(diag["legacy_conflict"])
        self.assertIn("legacy_compile_flag_conflict", diag["reasons"])

    def test_external_owner_is_hard_disable(self):
        policy, diag = tcp.resolve_compile_policy(
            env={tcp.ENV_MODE: "full"}, argv=[], external_compile_owner="sage_attention"
        )
        self.assertEqual(policy.mode, "off")
        self.assertTrue(policy.hard_disabled)
        self.assertEqual(policy.hard_disable_reason, "external_compile_owner")
        self.assertEqual(policy.external_compile_owner, "sage_attention")

    def test_disable_flag_is_hard_disable_via_param_env_and_argv(self):
        policy, _ = tcp.resolve_compile_policy(
            env={tcp.ENV_MODE: "regional"}, argv=[], disable_comfy_compiler=True
        )
        self.assertEqual(policy.mode, "off")
        self.assertEqual(policy.hard_disable_reason, "disable_comfy_compiler")

        policy, _ = tcp.resolve_compile_policy(
            env={tcp.ENV_MODE: "regional", tcp.ENV_DISABLE: "1"}, argv=[]
        )
        self.assertEqual(policy.mode, "off")

        policy, _ = tcp.resolve_compile_policy(
            env={tcp.ENV_MODE: "regional"}, argv=["--disable-comfy-compiler"]
        )
        self.assertEqual(policy.mode, "off")

    def test_policy_is_immutable(self):
        policy, _ = tcp.resolve_compile_policy(env={}, argv=[])
        with self.assertRaises(dataclasses.FrozenInstanceError):
            policy.mode = "full"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Structural region discovery
# ---------------------------------------------------------------------------


@pytest.mark.fast_unit
class RegionDiscoveryTests(unittest.TestCase):
    def test_single_region(self):
        model = _Model(blocks=_blocks(4))
        result = tcp.discover_compile_regions(model)
        self.assertTrue(result["supported"])
        self.assertEqual(len(result["regions"]), 1)
        self.assertEqual(result["regions"][0]["container"], "blocks")
        self.assertEqual(result["regions"][0]["block_count"], 4)
        self.assertEqual(result["reason"], "ok")

    def test_five_family_fixtures_all_structurally_supported(self):
        # Five known family *layouts* as pure structural fixtures.  The
        # implementation never sees family names — only containers.
        families = {
            "flux_like": _Model(double_blocks=_blocks(4), single_blocks=_blocks(6)),
            "sdxl_like": _Model(blocks=_blocks(5)),
            "layered_like": _Model(layers=_blocks(3)),
            "transformer_like": _Model(transformer_blocks=_blocks(8)),
            "dual_like": _Model(double_blocks=_blocks(2), blocks=_blocks(2)),
        }
        for name, model in families.items():
            result = tcp.discover_compile_regions(model)
            self.assertTrue(result["supported"], f"fixture {name}: {result}")
            self.assertGreaterEqual(len(result["regions"]), 1)

    def test_flux_like_yields_two_non_overlapping_regions(self):
        model = _Model(double_blocks=_blocks(4), single_blocks=_blocks(6))
        result = tcp.discover_compile_regions(model)
        self.assertTrue(result["supported"])
        names = sorted(region["container"] for region in result["regions"])
        self.assertEqual(names, ["double_blocks", "single_blocks"])

    def test_unfamiliar_containers_yield_no_regions(self):
        model = _Model(mamba_blocks=_blocks(4), attention_mixers=_blocks(4))
        result = tcp.discover_compile_regions(model)
        self.assertFalse(result["supported"])
        self.assertEqual(result["regions"], [])
        self.assertEqual(result["reason"], "no_supported_regions")

    def test_heterogeneous_container_rejected(self):
        mixed = [_Block(tag="a"), _OtherBlock(tag="b"), _Block(tag="c")]
        result = tcp.discover_compile_regions(_Model(blocks=mixed))
        self.assertFalse(result["supported"])
        self.assertEqual(result["rejected"].get("blocks"), "heterogeneous_blocks")

    def test_aliased_containers_deduped_to_first(self):
        shared = _blocks(4)
        model = _Model(double_blocks=shared, single_blocks=shared)
        result = tcp.discover_compile_regions(model)
        self.assertTrue(result["supported"])
        self.assertEqual(len(result["regions"]), 1)
        self.assertEqual(result["regions"][0]["container"], "double_blocks")
        self.assertIn("single_blocks", result["deduped_aliases"])

    def test_partial_overlap_is_ambiguous_no_regions(self):
        shared = _Block(tag="shared")
        model = _Model(
            double_blocks=[_Block(tag="a"), _Block(tag="b"), shared],
            single_blocks=[shared, _Block(tag="c"), _Block(tag="d")],
        )
        result = tcp.discover_compile_regions(model)
        self.assertFalse(result["supported"])
        self.assertEqual(result["reason"], "ambiguous_overlapping_regions")
        self.assertEqual(result["regions"], [])

    def test_leaf_and_scalar_containers_rejected(self):
        self.assertFalse(tcp.discover_compile_regions(_Model(blocks=[1, 2, 3]))["supported"])
        self.assertFalse(
            tcp.discover_compile_regions(_Model(blocks=[_Leaf(), _Leaf()]))["supported"]
        )

    def test_too_few_blocks_rejected(self):
        result = tcp.discover_compile_regions(_Model(blocks=_blocks(1)))
        self.assertFalse(result["supported"])
        self.assertEqual(result["rejected"].get("blocks"), "too_few_blocks")

    def test_forward_only_blocks_accepted(self):
        model = _Model(layers=[_ForwardOnlyBlock(), _ForwardOnlyBlock()])
        result = tcp.discover_compile_regions(model)
        self.assertTrue(result["supported"])

    def test_no_model_name_switches(self):
        # A model literally named like a known family but with no valid
        # containers must still be unsupported: names are never consulted.
        model = _Model()
        model.__class__.__name__ = "FluxLikeTransformer"
        result = tcp.discover_compile_regions(model)
        self.assertFalse(result["supported"])


# ---------------------------------------------------------------------------
# KJ capability probe
# ---------------------------------------------------------------------------


@pytest.mark.fast_unit
class KjProbeTests(unittest.TestCase):
    def test_missing_module_reports_capability_missing(self):
        def _raise(name):
            raise ImportError(name)

        result = tcp.probe_kj_compile_capability(importer=_raise)
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], tcp.KJ_CAPABILITY_MISSING)
        self.assertIsNone(result["wrapper"])

    def test_missing_attribute_reports_capability_missing(self):
        result = tcp.probe_kj_compile_capability(importer=lambda name: object())
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], tcp.KJ_CAPABILITY_MISSING)

    def test_present_wrapper_returns_borrowed_reference(self):
        def _sentinel(*args, **kwargs):
            return ("compiled", args, kwargs)

        class _Helpers:
            set_torch_compile_wrapper = _sentinel

        result = tcp.probe_kj_compile_capability(importer=lambda name: _Helpers)
        self.assertTrue(result["available"])
        self.assertIs(result["wrapper"], _sentinel)
        self.assertIn("set_torch_compile_wrapper", result["source"])


# ---------------------------------------------------------------------------
# Latch terminality
# ---------------------------------------------------------------------------


@pytest.mark.fast_unit
class FallbackLatchTests(unittest.TestCase):
    def test_terminal_transitions_stick(self):
        latch = tcp.CompileFallbackLatch()
        self.assertEqual(latch.state, tcp.LATCH_UNTRIED)
        self.assertFalse(latch.terminal)
        self.assertTrue(latch.mark_ready())
        self.assertTrue(latch.terminal)
        self.assertTrue(latch.should_attempt_compile)
        # One-way trip: an armed scope can still disarm permanently ...
        self.assertTrue(latch.mark_eager_failed("late_failure"))
        self.assertEqual(latch.state, tcp.LATCH_EAGER_FAILED)
        self.assertFalse(latch.should_attempt_compile)
        # ... but nothing leaves a terminal EAGER_* state.
        self.assertFalse(latch.mark_ready("retry"))
        self.assertFalse(latch.mark_eager_skipped("late"))
        self.assertEqual(latch.state, tcp.LATCH_EAGER_FAILED)
        self.assertEqual(latch.ignored_transitions, 2)

    def test_failed_and_skipped_are_terminal(self):
        failed = tcp.CompileFallbackLatch()
        self.assertTrue(failed.mark_eager_failed("boom"))
        self.assertFalse(failed.should_attempt_compile)
        self.assertFalse(failed.mark_ready("retry"))
        self.assertEqual(failed.state, tcp.LATCH_EAGER_FAILED)

        skipped = tcp.CompileFallbackLatch()
        self.assertTrue(skipped.mark_eager_skipped("kj_capability_missing"))
        self.assertFalse(skipped.mark_eager_failed("later"))
        self.assertEqual(skipped.state, tcp.LATCH_EAGER_SKIPPED)


# ---------------------------------------------------------------------------
# Lifecycle ordering via fakes
# ---------------------------------------------------------------------------


@pytest.mark.fast_unit
class LifecycleOrderingTests(unittest.TestCase):
    def _scope(self, **overrides):
        scope = tcp.install_sampling_compile_scope(policy=_regional_policy())
        scope.update(overrides)
        return scope

    def test_install_never_compiles(self):
        calls: list = []

        def _compile(block, policy):
            calls.append(block)
            raise AssertionError("must not compile at install/prepare time")

        scope = tcp.install_sampling_compile_scope(policy=_regional_policy())
        self.assertFalse(scope["ready"])
        self.assertFalse(scope["released"])
        model = _Model(blocks=_blocks(3))
        summary = tcp.prepare_compile_targets(
            scope, diffusion_model=model, kj_probe=_kj_available(), compile_fn=_compile
        )
        self.assertTrue(summary["prepared"])
        self.assertEqual(calls, [])

    def test_prepare_requires_explicit_readiness(self):
        scope = self._scope()
        model = _Model(blocks=_blocks(3))
        summary = tcp.prepare_compile_targets(
            scope, diffusion_model=model, kj_probe=_kj_available(), compile_fn=lambda b, p: b
        )
        self.assertTrue(summary["ready"])
        self.assertEqual(summary["targets_built"], 3)
        self.assertEqual(scope["latch"].state, tcp.LATCH_READY)

    def test_snapshot_capture_forces_eager(self):
        calls: list = []

        def _compile(block, policy):
            calls.append(block)
            return block

        scope = self._scope()
        summary = tcp.prepare_compile_targets(
            scope,
            diffusion_model=_Model(blocks=_blocks(3)),
            kj_probe=_kj_available(),
            compile_fn=_compile,
            snapshot_capturing=True,
        )
        self.assertFalse(summary["prepared"])
        self.assertEqual(summary["reason"], "snapshot_capture_active")
        self.assertEqual(scope["latch"].state, tcp.LATCH_EAGER_SKIPPED)
        self.assertEqual(calls, [])

    def test_missing_kj_capability_stays_eager(self):
        scope = self._scope()
        summary = tcp.prepare_compile_targets(
            scope,
            diffusion_model=_Model(blocks=_blocks(3)),
            kj_probe=_kj_available(available=False, reason=tcp.KJ_CAPABILITY_MISSING),
            compile_fn=lambda b, p: b,
        )
        self.assertFalse(summary["prepared"])
        self.assertEqual(summary["reason"], tcp.KJ_CAPABILITY_MISSING)
        self.assertEqual(scope["latch"].state, tcp.LATCH_EAGER_SKIPPED)

    def test_mode_off_stays_eager(self):
        off_policy, _ = tcp.resolve_compile_policy(env={}, argv=[])
        scope = tcp.install_sampling_compile_scope(policy=off_policy)
        summary = tcp.prepare_compile_targets(
            scope, diffusion_model=_Model(blocks=_blocks(3)), kj_probe=_kj_available()
        )
        self.assertEqual(summary["reason"], "mode_off")

    def test_factory_lazy_failure_latch_is_terminal(self):
        calls: list = []

        def _failing(block, policy):
            calls.append(block)
            raise RuntimeError("inductor boom")

        latch = tcp.CompileFallbackLatch()
        latch.mark_ready()
        block = _Block(tag="victim")
        target = tcp.make_compile_target(block, policy=_regional_policy(),
                                         compile_fn=_failing, latch=latch)
        self.assertEqual(target(), ("eager", "victim"))
        self.assertEqual(latch.state, tcp.LATCH_EAGER_FAILED)
        # No retry per step: exactly one attempt, eager ever after.
        self.assertEqual(target(), ("eager", "victim"))
        self.assertEqual(len(calls), 1)

    def test_factory_success_caches_compiled_target(self):
        calls: list = []
        compiled = _Block(tag="compiled")

        def _compile(block, policy):
            calls.append(block)
            return compiled

        latch = tcp.CompileFallbackLatch()
        latch.mark_ready()
        target = tcp.make_compile_target(_Block(tag="orig"), policy=_regional_policy(),
                                         compile_fn=_compile, latch=latch)
        self.assertEqual(target(), ("eager", "compiled"))
        self.assertEqual(target(), ("eager", "compiled"))
        self.assertEqual(len(calls), 1)
        self.assertEqual(latch.state, tcp.LATCH_READY)

    def test_unwired_factory_stays_eager_with_clear_reason(self):
        latch = tcp.CompileFallbackLatch()
        latch.mark_ready()
        target = tcp.make_compile_target(
            _Block(tag="x"), policy=_regional_policy(), latch=latch,
            kj_probe=_kj_available(),
        )
        self.assertEqual(target(), ("eager", "x"))
        self.assertEqual(latch.state, tcp.LATCH_EAGER_SKIPPED)
        self.assertEqual(latch.reason, "no_compile_applier_wired")

    def test_recompile_budget_trips_latch(self):
        scope = self._scope()
        model = _Model(blocks=_blocks(2))
        tcp.prepare_compile_targets(
            scope, diffusion_model=model, kj_probe=_kj_available(), compile_fn=lambda b, p: b
        )
        on_budget = tcp.finish_compile_sample(scope, recompiles_observed=8)
        self.assertFalse(on_budget["over_budget"])
        self.assertEqual(scope["latch"].state, tcp.LATCH_READY)
        over = tcp.finish_compile_sample(scope, recompiles_observed=9)
        self.assertTrue(over["over_budget"])
        self.assertEqual(scope["latch"].state, tcp.LATCH_EAGER_FAILED)

    def test_release_is_idempotent_and_drops_targets(self):
        scope = self._scope()
        tcp.prepare_compile_targets(
            scope, diffusion_model=_Model(blocks=_blocks(2)),
            kj_probe=_kj_available(), compile_fn=lambda b, p: b,
        )
        first = tcp.release_compile_targets(scope)
        self.assertEqual(first, {"released": True, "already": False})
        self.assertEqual(scope["targets"], [])
        second = tcp.release_compile_targets(scope)
        self.assertEqual(second, {"released": True, "already": True})

    def test_attach_policy_mapping_and_attribute(self):
        policy = _regional_policy()
        mapping: dict = {}
        result = tcp.attach_compile_policy(mapping, policy)
        self.assertTrue(result["attached"])
        self.assertIs(mapping["compile_policy"], policy)

        class _Executor:
            pass

        executor = _Executor()
        result = tcp.attach_compile_policy(executor, policy)
        self.assertTrue(result["attached"])
        self.assertIs(getattr(executor, "compile_policy"), policy)


# ---------------------------------------------------------------------------
# Compiler cache: namespace purity + prune ordering
# ---------------------------------------------------------------------------


@pytest.mark.fast_unit
class CompilerCacheNamespaceTests(unittest.TestCase):
    TOOLCHAIN = {
        "torch_version": "2.5.1",
        "cuda_version": "12.4",
        "triton_version": "3.1.0",
        "arch": "sm_100",
        "python_version": "3.12",
    }

    def test_no_model_checkpoint_request_shape_contamination(self):
        base = cc.compiler_cache_namespace(dict(self.TOOLCHAIN))
        for extra in (
            {"model": "flux.safetensors"},
            {"checkpoint": "x.safetensors", "shape": [1, 4, 64, 64]},
            {"request_id": "abc", "seed": 7, "prompt": "hello"},
            {"model": "other.safetensors", "checkpoint": "y", "request_id": "z"},
        ):
            polluted = dict(self.TOOLCHAIN)
            polluted.update(extra)
            self.assertEqual(cc.compiler_cache_namespace(polluted), base,
                             f"contamination from {sorted(extra)}")

    def test_toolchain_changes_change_namespace(self):
        base = cc.compiler_cache_namespace(dict(self.TOOLCHAIN))
        for key in cc.TOOLCHAIN_KEYS:
            mutated = dict(self.TOOLCHAIN)
            mutated[key] = "different"
            self.assertNotEqual(cc.compiler_cache_namespace(mutated), base, key)

    def test_missing_keys_degrade_to_unknown(self):
        first = cc.compiler_cache_namespace({})
        second = cc.compiler_cache_namespace(None)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_paths_and_bind_routing(self):
        namespace = cc.compiler_cache_namespace(dict(self.TOOLCHAIN))
        with tempfile.TemporaryDirectory() as root:
            paths = cc.compiler_cache_paths(namespace, root=root)
            self.assertEqual(paths["root"], root)
            self.assertTrue(paths["namespace_dir"].startswith(root))
            self.assertTrue(paths["inductor_dir"].startswith(paths["namespace_dir"]))
            self.assertTrue(paths["triton_dir"].startswith(paths["namespace_dir"]))

            saved_inductor = os.environ.get(cc.ENV_INDUCTOR_DIR)
            saved_triton = os.environ.get(cc.ENV_TRITON_DIR)
            try:
                bound = cc.bind_compiler_cache(namespace, root=root)
                self.assertTrue(os.path.isdir(paths["inductor_dir"]))
                self.assertTrue(os.path.isdir(paths["triton_dir"]))
                self.assertEqual(bound["applied"][cc.ENV_INDUCTOR_DIR], paths["inductor_dir"])
                self.assertEqual(bound["applied"][cc.ENV_TRITON_DIR], paths["triton_dir"])
            finally:
                if saved_inductor is None:
                    os.environ.pop(cc.ENV_INDUCTOR_DIR, None)
                else:
                    os.environ[cc.ENV_INDUCTOR_DIR] = saved_inductor
                if saved_triton is None:
                    os.environ.pop(cc.ENV_TRITON_DIR, None)
                else:
                    os.environ[cc.ENV_TRITON_DIR] = saved_triton

    def test_empty_namespace_rejected(self):
        with self.assertRaises(ValueError):
            cc.compiler_cache_paths("")


@pytest.mark.fast_unit
class CachePruneTests(unittest.TestCase):
    def _seed(self, root, name, size, idle_days, now):
        path = os.path.join(root, name)
        os.makedirs(path)
        with open(os.path.join(path, "blob.bin"), "wb") as handle:
            handle.write(b"x" * size)
        stamp = now - idle_days * 86400.0
        os.utime(os.path.join(path, "blob.bin"), (stamp, stamp))
        os.utime(path, (stamp, stamp))
        return path

    def test_prune_ordering_stalest_first_whole_namespace(self):
        now = time.time()
        with tempfile.TemporaryDirectory() as root:
            self._seed(root, "fresh_big", size=4000, idle_days=1, now=now)
            self._seed(root, "stale_small", size=1000, idle_days=40, now=now)
            self._seed(root, "stale_big", size=3000, idle_days=60, now=now)
            plan = cc.plan_cache_prune(root, target_bytes=4500, max_idle_days=30)
            self.assertTrue(plan["dry_run"])  # dry-run is the default
            ordered = [item["namespace"] for item in plan["planned"]]
            self.assertEqual(ordered, ["stale_big", "stale_small"])
            self.assertLessEqual(plan["projected_bytes"], 4500)
            # Dry-run deletes nothing.
            self.assertTrue(os.path.isdir(os.path.join(root, "stale_big")))

    def test_fresh_namespaces_never_eligible(self):
        now = time.time()
        with tempfile.TemporaryDirectory() as root:
            self._seed(root, "fresh", size=9000, idle_days=2, now=now)
            plan = cc.plan_cache_prune(root, target_bytes=1, max_idle_days=30)
            self.assertEqual(plan["planned"], [])

    def test_bounded_plan_and_symlink_safety(self):
        now = time.time()
        with tempfile.TemporaryDirectory() as root:
            self._seed(root, "stale_a", size=2000, idle_days=40, now=now)
            self._seed(root, "stale_b", size=2000, idle_days=50, now=now)
            real_target = os.path.join(root, "stale_a")
            try:
                os.symlink(real_target, os.path.join(root, "link_ns"))
            except OSError as exc:
                # Windows without developer-mode privileges cannot create
                # symlinks; the symlink-safe path is then untestable here.
                self.skipTest(f"symlinks unavailable: {exc}")
            plan = cc.plan_cache_prune(root, target_bytes=1, max_idle_days=30,
                                       limit_entries=1)
            self.assertIn("link_ns", plan["skipped_symlinks"])
            self.assertEqual(len(plan["planned"]), 1)
            self.assertTrue(plan["bounded"])

    def test_prune_entrypoint_deletes_only_when_not_dry_run(self):
        now = time.time()
        with tempfile.TemporaryDirectory() as root:
            victim = self._seed(root, "stale_victim", size=2000, idle_days=40, now=now)
            dry = cc.prune_compiler_cache(root, target_bytes=1, max_idle_days=30)
            self.assertEqual(dry["deleted"], [])
            self.assertTrue(os.path.isdir(victim))
            live = cc.prune_compiler_cache(root, target_bytes=1, max_idle_days=30,
                                           dry_run=False)
            self.assertEqual(live["deleted"], [victim])
            self.assertFalse(os.path.exists(victim))
            self.assertEqual(live["errors"], [])


# ---------------------------------------------------------------------------
# Aggregate diagnostics shape
# ---------------------------------------------------------------------------


@pytest.mark.fast_unit
class DiagnosticsShapeTests(unittest.TestCase):
    def _ready_scope(self):
        scope = tcp.install_sampling_compile_scope(
            policy=_regional_policy(), cache_namespace="ns123", cache_dir="/tmp/ns123")
        tcp.prepare_compile_targets(
            scope, diffusion_model=_Model(blocks=_blocks(2)),
            kj_probe=_kj_available(), compile_fn=lambda b, p: b,
        )
        tcp.finish_compile_sample(scope, recompiles_observed=2)
        return scope

    def test_single_aggregate_line_with_honest_fields(self):
        summary = tcp.summarize_compile_sample(self._ready_scope())
        line = summary["line"]
        self.assertTrue(line.startswith("[compile]"))
        for token in ("requested=regional", "actual=regional", "regions=1",
                      "ready=", "eager=", "failed=", "recompiles=2/8", "cache=ns123"):
            self.assertIn(token, line)
        details = summary["details"]
        self.assertEqual(details["regions_total"], 1)
        self.assertEqual(details["ready"], 2)
        self.assertEqual(details["failed"], 0)
        # Cache routing is reported; hits are never claimed here.
        self.assertFalse(details["cache"]["hits_claimed"])
        self.assertEqual(details["cache"]["namespace"], "ns123")
        # Debug-gated detail: no per-block spam by default.
        self.assertNotIn("targets", details)

    def test_debug_gates_per_region_detail(self):
        summary = tcp.summarize_compile_sample(self._ready_scope(), debug=True)
        self.assertIn("targets", summary["details"])
        self.assertEqual(len(summary["details"]["targets"]), 2)

    def test_eager_scope_line_shape(self):
        off_policy, _ = tcp.resolve_compile_policy(env={}, argv=[])
        scope = tcp.install_sampling_compile_scope(policy=off_policy)
        tcp.prepare_compile_targets(
            scope, diffusion_model=_Model(blocks=_blocks(2)), kj_probe=_kj_available())
        summary = tcp.summarize_compile_sample(scope)
        self.assertIn("requested=off", summary["line"])
        self.assertIn("actual=off", summary["line"])
        self.assertIn("cache=unrouted", summary["line"])


# ---------------------------------------------------------------------------
# Integration (NOT fast_unit): real KJ wrapper path, skipped without deps
# ---------------------------------------------------------------------------


@pytest.mark.heavy_local
class RealKjWrapperIntegrationTests(unittest.TestCase):
    """Real torch/Comfy KJ probe behavior.

    Skipped automatically when torch is unavailable.  When torch exists
    but KJNodes' public wrapper path is absent, the probe must honestly
    report ``kj_capability_missing`` (that gap is the residual risk owned
    by the parent wiring lane) rather than raise.
    """

    def test_real_kj_capability_probe(self):
        pytest.importorskip("torch")
        result = tcp.probe_kj_compile_capability()
        self.assertIn(result["reason"], ("ok", tcp.KJ_CAPABILITY_MISSING))
        if result["reason"] == tcp.KJ_CAPABILITY_MISSING:
            self.assertFalse(result["available"])
            self.assertIsNone(result["wrapper"])
        else:
            self.assertTrue(result["available"])
            self.assertTrue(callable(result["wrapper"]))

    def test_structural_discovery_over_real_torch_modules(self):
        torch = pytest.importorskip("torch")

        class _TorchBlock(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.body = torch.nn.Sequential(torch.nn.Linear(4, 4), torch.nn.ReLU())

            def forward(self, value):
                return self.body(value)

        class _TorchModel(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.double_blocks = torch.nn.ModuleList(_TorchBlock() for _ in range(2))

        result = tcp.discover_compile_regions(_TorchModel())
        self.assertTrue(result["supported"])
        self.assertEqual(result["regions"][0]["container"], "double_blocks")

    def test_no_compile_factory_added_to_kj(self):
        pytest.importorskip("torch")
        try:
            import comfy_api.torch_helpers as helpers  # type: ignore[import-not-found]
        except Exception:
            self.skipTest("comfy_api unavailable; KJ registry untouched by construction")
        self.assertFalse(hasattr(helpers, "comfymodal_compile_factory"))


if __name__ == "__main__":
    unittest.main()
