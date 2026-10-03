"""Audit-only contracts for the Golden C0 CUDA arena lifecycle.

These tests assert facts the P9 CUDA-arena-lifecycle audit depends on.  They
change nothing: every production-facing assertion is either a pure analysis of
recorded telemetry or a structural check that a specific contract still holds
in the shipped source.  The one behavioural assertion that constructs a real
object (``SharedArenaRing.__init__``) touches no CUDA, allocates no shared
memory, and forks nothing.

Nothing here is a regression test for deleted behaviour, and nothing here
would pass vacuously: each structural test names the exact call site, the
exact gate, or the exact default it is pinning.
"""

from __future__ import annotations

import ast
import functools
import inspect
import types
from pathlib import Path

import pytest

from comfymodal_runtime import cuda_arena_lifecycle_audit as audit
from comfymodal_runtime import golden_io_process_v2 as c0
from comfymodal_runtime import golden_source_threads as source

pytestmark = pytest.mark.fast_unit


# â”€â”€ audit analysis module â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def test_audit_analysis_is_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv(audit.AUDIT_ENV, raising=False)
    assert audit.enabled() is False
    monkeypatch.setenv(audit.AUDIT_ENV, "1")
    assert audit.enabled() is True
    monkeypatch.setenv(audit.AUDIT_ENV, "0")
    assert audit.enabled() is False


def test_audit_analysis_is_imported_by_no_production_module() -> None:
    """The analysis must be inert: nothing on the request path may import it."""
    runtime = Path(inspect.getfile(c0)).parent
    importers = [
        path.name
        for path in runtime.glob("*.py")
        if "cuda_arena_lifecycle_audit" in path.read_text(encoding="utf-8")
    ]
    assert importers == []


def _ensure(**overrides) -> dict:
    """One recorded arena_ensure block, 1 GiB / 16 x 64 MiB, default overlap."""
    base = {
        "arena_bytes": 1073741824,
        "slot_count": 16,
        "slot_bytes": 67108864,
        "register_ms": 713.0,
        "registration_order": "overlap",
        "registered": True,
        "child_startup_ms": 684.0,
        "startup_marks": {
            "c0_ensure_enter": 1_000_000_000,
            "torch_required": 1_012_000_000,
            "shm_create_begin": 1_013_000_000,
            "shm_create_end": 1_019_500_000,
            "torch_frombuffer_begin": 1_019_600_000,
            "torch_frombuffer_end": 1_021_000_000,
            "slot_views_begin": 1_021_100_000,
            "slot_views_end": 1_030_000_000,
            "source_thread_spawn_begin": 1_031_000_000,
            "source_thread_spawn_end": 1_034_000_000,
            "source_thread_register_begin": 1_034_100_000,
            "cuda_host_register_begin": 1_034_200_000,
            "cuda_host_register_end": 1_747_200_000,
            "source_thread_register_end": 1_747_300_000,
            "source_thread_ready": 1_790_000_000,
        },
    }
    base.update(overrides)
    return base


def test_decompose_splits_establishment_into_measured_phases() -> None:
    phases = audit.decompose(_ensure())
    assert phases["backing_create_ms"] == 6.5
    assert phases["pre_register_ms"] == 34.2
    assert phases["register_call_ms"] == 713.0
    assert phases["post_register_ms"] == 42.8
    assert phases["child_boot_ms"] == 759.0
    assert phases["establishment_total_ms"] == 790.0
    assert phases["spawn_precedes_register"] is True
    assert phases["establishment_owner"] == "source_process_boot"


def test_decompose_reports_unknown_rather_than_inventing_missing_phases() -> None:
    phases = audit.decompose({})
    for key in (
        "establishment_total_ms",
        "pre_register_ms",
        "register_call_ms",
        "post_register_ms",
        "child_boot_ms",
        "register_child_overlap_ms",
        "spawn_precedes_register",
    ):
        assert phases[key] is None or phases[key] == "unknown"


def test_decompose_proves_register_ms_is_the_call_only_boundary() -> None:
    """`register_ms` must bracket the call, not the surrounding setup."""
    phases = audit.decompose(_ensure())
    assert phases["register_boundary_agrees_with_marks"] is True
    # The surrounding setup is measured separately and must not be inside it.
    assert phases["backing_create_ms"] + phases["slot_views_ms"] > 0
    assert phases["pre_register_ms"] > 0
    assert phases["post_register_ms"] > 0


def test_overlap_ceiling_never_credits_time_already_hidden() -> None:
    """Root-wall credit is non-overlapping only.

    The source-process boot (759 ms) is longer than the register call
    (713 ms), so a perfect schedule would hide the whole call.  Crediting more
    than the call itself would be double counting.
    """
    timeline = audit.overlap_timeline(_ensure())
    assert timeline["already_overlapped_today"] is True
    assert timeline["root_wall_saving_ceiling_ms"] == 0.0
    assert timeline["registration_on_critical_path"] is True


def test_overlap_ceiling_is_bounded_when_registration_dominates() -> None:
    """When the register call outlives the boot window, only the tail is creditable."""
    marks = _ensure()["startup_marks"]
    marks["source_thread_ready"] = 1_600_000_000  # boot window ends inside the call
    timeline = audit.overlap_timeline(_ensure(startup_marks=marks))
    assert timeline["source_process_boot_ms"] == 569.0
    assert timeline["register_call_ms"] == 713.0
    assert 0 < timeline["root_wall_saving_ceiling_ms"] < 713.0


def test_context_evidence_is_unknown_without_the_opt_in_diag_arm() -> None:
    evidence = audit.registration_context_evidence(_ensure())
    assert evidence["sampled"] is False
    assert evidence["lazy_context_init_inside_call"] == "unknown"


def test_context_evidence_detects_lazy_context_creation_inside_the_call() -> None:
    ensure = _ensure(
        registration_diagnostic={
            "api": "torch.cuda.cudart().cudaHostRegister",
            "flags": 0,
            "return_code": 0,
            "before": {"identity": {"context_handle_before_or_after": "0x0"}},
            "after": {"identity": {"context_handle_before_or_after": "0x55f1a2b3c400"}},
        }
    )
    evidence = audit.registration_context_evidence(ensure)
    assert evidence["lazy_context_init_inside_call"] == "yes"
    assert evidence["flags"] == 0


def test_context_evidence_detects_a_context_that_was_already_current() -> None:
    ensure = _ensure(
        registration_diagnostic={
            "before": {"identity": {"context_handle_before_or_after": "0x55f1a2b3c400"}},
            "after": {"identity": {"context_handle_before_or_after": "0x55f1a2b3c400"}},
        }
    )
    evidence = audit.registration_context_evidence(ensure)
    assert evidence["lazy_context_init_inside_call"] == "no"


def test_context_evidence_reads_registration_as_the_first_touch_of_the_arena() -> None:
    ensure = _ensure(
        registration_diagnostic={
            "before": {
                "identity": {"context_handle_before_or_after": "0x0"},
                "proc_status": {"rss_kb": 0},
            },
            "after": {
                "identity": {"context_handle_before_or_after": "0x55f1a2b3c400"},
                "proc_status": {"rss_kb": 327680},
            },
        }
    )
    evidence = audit.registration_context_evidence(ensure)
    assert evidence["first_touch_by_registration"] == "yes"


def test_slot_registration_plan_is_disjoint_and_page_aligned() -> None:
    plan = audit.slot_registration_plan(_ensure(), prefix_slots=4)
    assert plan["strict_product_holds"] is True
    assert plan["prefix_slots"] == 4
    assert plan["registered_bytes"] == 268435456
    assert plan["unregistered_tail_bytes"] == 805306368
    assert plan["slot_stride_page_aligned"] is True
    assert plan["all_prefix_ranges_disjoint"] is True
    assert plan["feasible"] == "arithmetically"
    # Feasibility is arithmetic only; acceptance and cost are not claimed.
    assert "NOT established" in plan["note"]


def test_slot_registration_plan_is_clamped_to_the_real_slot_count() -> None:
    plan = audit.slot_registration_plan(_ensure(), prefix_slots=99)
    assert plan["prefix_slots"] == 16
    assert plan["unregistered_tail_bytes"] == 0


def test_slot_registration_plan_fails_closed_on_a_geometry_mismatch() -> None:
    plan = audit.slot_registration_plan(_ensure(arena_bytes=805306368), prefix_slots=4)
    assert plan["strict_product_holds"] is False
    assert plan["feasible"] is False
    assert plan["reason"] == "c0_arena_geometry_mismatch"


def test_slot_registration_plan_reports_unknown_without_geometry() -> None:
    assert audit.slot_registration_plan({}, prefix_slots=4)["feasible"] == "unknown"


# â”€â”€ shipped-code contracts the audit conclusions rest on â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@functools.lru_cache(maxsize=None)
def _tree_of(path: str) -> ast.Module:
    """Parse once per source file.

    ``golden_io_process_v2`` is ~11k lines, and several contracts below walk
    the whole tree.  Re-parsing it per test dominated this file's wall time.
    """
    return ast.parse(Path(path).read_text(encoding="utf-8"))


def _function_node_from(module: types.ModuleType, name: str) -> ast.FunctionDef:
    tree = _tree_of(inspect.getfile(module))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found in {module.__name__}")


def _method_node_from(module: types.ModuleType, class_name: str, name: str) -> ast.FunctionDef:
    """Scope the lookup to one class.

    Several C0 classes define an ``ensure``/``close`` with different bodies, so
    an unscoped name lookup would silently pin the wrong class.
    """
    tree = _tree_of(inspect.getfile(module))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == name:
                    return child
    raise AssertionError(f"{class_name}.{name} not found in {module.__name__}")


def _function_node(name: str) -> ast.FunctionDef:
    return _function_node_from(c0, name)


def _arena_ensure_node() -> ast.FunctionDef:
    return _method_node_from(c0, "SharedArenaRing", "ensure")


def test_no_cuda_registration_symbol_is_called_directly_in_the_c0_runtime() -> None:
    """No hidden second registration, in any alias or spelling.

    The runtime resolves ``cudaHostRegister`` through ``getattr`` and injects
    it as the ``register`` parameter, so a direct symbol call anywhere in this
    module would be an unregistered second registration path.
    """
    tree = _tree_of(inspect.getfile(c0))
    direct = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"cudaHostRegister", "cuMemHostRegister", "cuMemHostRegister_v2"}
    ]
    assert direct == []


def test_exactly_one_injected_registration_call_exists_module_wide() -> None:
    """The one and only registration is `_register_arena`'s injected callable."""
    tree = _tree_of(inspect.getfile(c0))
    arena_registrations = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "register"
        and "_arena_address" in ast.unparse(node)
    ]
    assert len(arena_registrations) == 1
    owner = next(
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and any(child is arena_registrations[0] for child in ast.walk(node))
    )
    assert owner == "_register_arena"
    # The cudart registration symbol is resolved from exactly two places:
    # `ensure` for the arena, and `run_primitive_probe`, which is a standalone
    # diagnostic that allocates its own buffers and never touches the arena.
    owners = _getattr_symbol_owners(tree, "cudaHostRegister")
    assert owners == {"ensure", "run_primitive_probe"}
    probe = ast.unparse(_function_node_from(c0, "run_primitive_probe"))
    assert "_arena_address" not in probe
    assert "SharedArenaRing" not in probe
    # cudaHostUnregister is reached from teardown only, never from ensure.
    assert "ensure" not in _getattr_symbol_owners(tree, "cudaHostUnregister")


def _getattr_symbol_owners(tree: ast.AST, symbol: str) -> set[str]:
    """Names of the functions that resolve ``symbol`` off a cudart-like object."""
    nodes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
        and node.args[1].value == symbol
    ]
    owners: set[str] = set()
    for candidate in ast.walk(tree):
        if isinstance(candidate, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
            child is node for child in ast.walk(candidate) for node in nodes
        ):
            owners.add(candidate.name)
    return owners


def test_registration_covers_the_whole_arena_in_one_call() -> None:
    """The registered range is the entire arena, not a sub-range or a loop."""
    node = _function_node("_register_arena")
    calls = [
        child
        for child in ast.walk(node)
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
        and child.func.id == "register"
    ]
    assert len(calls) == 1
    args = [ast.unparse(argument) for argument in calls[0].args]
    assert args == ["self._arena_address", "self.size_bytes", "_CUDA_HOST_REGISTER_DEFAULT"]


def test_registration_is_guarded_by_the_single_shipped_selector() -> None:
    """`register_ms`/`registered` must stay owned by `_register_arena` alone."""
    node = _function_node("_register_arena")
    assert "self.register_ms = " in ast.unparse(node)
    assert "self.registered = True" in ast.unparse(node)


def test_unregister_uses_the_same_address_as_register() -> None:
    node = _function_node("_unregister")
    calls = [
        child
        for child in ast.walk(node)
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
        and child.func.id == "unregister"
    ]
    assert len(calls) == 1
    assert [ast.unparse(argument) for argument in calls[0].args] == ["self._arena_address"]
    assert "if not self.registered" in ast.unparse(node)


def test_arena_ensure_has_three_but_executes_at_most_one_registration() -> None:
    """`ensure` carries three mutually exclusive registration sites.

    One `register_first` site, one source-thread overlap site, and one legacy
    child site behind `!= "register_first"`.  Exactly one of them can run in
    any container, and `ensure` short-circuits once the arena exists.
    """
    ensure_node = _arena_ensure_node()
    calls = [
        child
        for child in ast.walk(ensure_node)
        if isinstance(child, ast.Call)
        and isinstance(child.func, ast.Attribute)
        and child.func.attr == "_register_arena"
    ]
    assert len(calls) == 3
    unparsed = ast.unparse(ensure_node)
    # The three guards, exactly.  One `register_first` branch, one
    # source-thread overlap branch, one legacy child branch; the first two are
    # mutually exclusive on `registration_order` and the source-thread branch
    # returns before the legacy branch is reachable.
    assert unparsed.count("if _do_register and self.registration_order == 'register_first':") == 1
    assert unparsed.count("if self.registration_order != 'register_first':") == 1
    assert unparsed.count("if _do_register and self.registration_order != 'register_first':") == 1
    # Two overlap guards plus the `overlapped_spawn_and_register` evidence flag.
    assert unparsed.count("self.registration_order != 'register_first'") == 3
    assert "overlapped_spawn_and_register" in unparsed
    assert "if self.created:" in unparsed
    assert unparsed.index("if self.created:") < unparsed.index("self._register_arena(")
    # The source-thread branch returns before the legacy registration site.
    assert unparsed.index("await_ready()") < unparsed.rindex("self._register_arena(")


def test_ensure_arena_runtime_is_idempotent_across_clip_and_unet(monkeypatch) -> None:
    """One arena, one registration, reused for every model stage."""
    source_text = Path(inspect.getfile(c0)).read_text(encoding="utf-8")
    unparsed = ast.unparse(ast.parse(source_text))
    assert unparsed.count("def ensure_arena_runtime(") == 1
    assert "if _C0_RUNTIME is not None and _C0_RUNTIME.created:" in unparsed
    assert "return _C0_RUNTIME" in unparsed
    # The module-level singleton is what makes reuse across model stages real.
    assert "_C0_RUNTIME: Optional[SharedArenaRing] = None" in unparsed


def test_source_thread_mode_fails_closed_without_registration(monkeypatch) -> None:
    """Registration is a hard precondition of the shipped source architecture."""
    monkeypatch.setenv("COMFYMODAL_GOLDEN_C0_SOURCE_THREADS", "1")
    monkeypatch.setenv(c0.IO_PROCESS_V2_C0_HOST_REGISTER_ENV, "0")
    with pytest.raises(RuntimeError, match="source_threads_requires_cuda_host_register"):
        c0.SharedArenaRing(
            size_bytes=source.ARENA_BYTES,
            slot_count=source.SLOT_COUNT,
            slot_bytes=source.SLOT_BYTES,
        )


def test_source_thread_mode_constructs_with_registration_on(monkeypatch) -> None:
    monkeypatch.setenv("COMFYMODAL_GOLDEN_C0_SOURCE_THREADS", "1")
    monkeypatch.setenv(c0.IO_PROCESS_V2_C0_HOST_REGISTER_ENV, "1")
    runtime = c0.SharedArenaRing(
        size_bytes=source.ARENA_BYTES,
        slot_count=source.SLOT_COUNT,
        slot_bytes=source.SLOT_BYTES,
    )
    assert runtime.size_bytes == 1073741824
    assert runtime.slot_count == 16
    assert runtime.host_register_enabled is True
    assert runtime.registered is False
    assert runtime.created is False


def test_shipped_registration_defaults_are_unchanged_by_this_audit(monkeypatch) -> None:
    monkeypatch.delenv(c0.IO_PROCESS_V2_C0_HOST_REGISTER_ENV, raising=False)
    monkeypatch.delenv(c0.C0_REGISTRATION_ORDER_ENV, raising=False)
    monkeypatch.delenv(c0.C0_REGISTRATION_DIAG_ENV, raising=False)
    monkeypatch.delenv(c0.C0_REGISTRATION_CONTEXT_PREINIT_ENV, raising=False)
    assert c0.c0_host_register_enabled() is True
    assert c0.c0_registration_order() == "overlap"
    assert c0.c0_registration_diag_enabled() is False
    assert c0.c0_registration_context_preinit_enabled() is False


def test_source_process_stays_cuda_sterile_and_writes_the_registered_arena() -> None:
    """The child is exec'd fresh, so it must attach by name and stay CUDA-free."""
    spawn = ast.unparse(_method_node_from(source, "SourceThreadProcess", "spawn"))
    assert "CUDA_VISIBLE_DEVICES" in spawn
    assert "'--source-child'" in spawn
    assert "self.arena_name" in spawn
    # The arena is reached by NAME, never inherited across exec.
    assert "self.arena_name," in spawn
    child_main = ast.unparse(_function_node_from(source, "_child_main"))
    assert "_PosixAttachment(arena_name, ARENA_BYTES)" in child_main
    assert "cudaHostRegister" not in child_main
    assert "cudart" not in child_main
    assert "torch" not in child_main


def test_registration_precedes_any_source_write_to_the_arena() -> None:
    """Ordering invariant: mapping, then spawn, then registration, then READY.

    The child only maps the arena by name.  It is given no plan during
    establishment, and the parent joins READY after the registration call, so
    no reader can write a slot before the range is registered.
    """
    unparsed = ast.unparse(_arena_ensure_node())
    shm_index = unparsed.index("shared_memory.SharedMemory(create=True")
    address_index = unparsed.index("self._arena_address = _shm_address(")
    spawn_index = unparsed.index("source_thread_spawn_begin")
    register_index = unparsed.index("source_thread_register_begin")
    ready_index = unparsed.index("await_ready()")
    assert shm_index < address_index < spawn_index < register_index < ready_index
    # No plan is installed during establishment, so no copy can start early.
    assert "plan_once" not in unparsed
    assert "publish_all" not in unparsed


def test_h2d_submission_is_non_blocking_on_a_cpu_staging_tensor() -> None:
    """The property registration buys: a truly async H2D off a CPU tensor."""
    from comfymodal_runtime import golden_qd_transport as qd

    submit = ast.unparse(_function_node_from(qd, "_submit"))
    assert "non_blocking=True" in submit
    assert "with torch.cuda.stream(stream):" in submit
    assert "record_start(stream)" in submit
    assert "record_end(stream)" in submit


def test_h2d_source_is_the_registered_arena_slot_not_a_private_copy() -> None:
    """`create_shared` must never allocate its own pinned host staging."""
    from comfymodal_runtime import golden_qd_transport as qd

    shared = ast.unparse(_function_node_from(qd, "create_shared"))
    assert "pin_memory" not in shared
    assert "cudaHostAlloc" not in shared
    assert "torch.empty" not in shared
    pool = ast.unparse(_method_node_from(c0, "SharedArenaRing", "new_stage_pool"))
    assert "self._slot_tensors" in pool
    assert "pin_memory" not in pool


def test_audit_branch_left_the_timed_registration_call_site_untouched() -> None:
    """Belt-and-braces: this branch must not have edited a timed call site."""
    unparsed = ast.unparse(_function_node("_register_arena"))
    assert unparsed.count("time.perf_counter()") == 2
    assert "time.perf_counter() - t0" in unparsed
    ensure_unparsed = ast.unparse(_arena_ensure_node())
    # The overlap arm records its own bracket, and the legacy branch overwrites
    # the same two marks from the recorded register stamps: still two marks.
    assert ensure_unparsed.count("cuda_host_register_begin") == 1
    assert ensure_unparsed.count("cuda_host_register_end") == 1