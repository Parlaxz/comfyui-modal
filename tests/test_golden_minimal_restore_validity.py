"""Compact architectural guard for Golden Minimal Restore routing and purity.

Preserves the original validity contract (snapshot proof + backend-aware Sage
rules) and pins the minimal contract: Golden Serial routes to minimal by
default, an explicit falsy override falls back to legacy, the minimal body does
only reset + logical GPU repair + one models-generation guard and fails closed,
and even the explicit Golden legacy escape gates restore-time diagnostics.
"""

from __future__ import annotations

import ast
import functools
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "tools" / "benchmark_v2_direct.py"
MODAL = ROOT / "comfymodal_runtime" / "modal_app.py"
PRELOAD = ROOT / "comfymodal_runtime" / "model_preload.py"
ENV = ROOT / "comfymodal_runtime" / "env.py"
SERIAL = "_golden_serial_profile_active"
RUN = "_golden_minimal_restore"
BENCH_SRC = BENCH.read_text(encoding="utf-8", errors="replace")


@functools.lru_cache(maxsize=None)
def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8", errors="replace"))


def _fn(path: Path, name: str) -> ast.FunctionDef:
    match = next((n for n in ast.walk(_tree(path)) if isinstance(n, ast.FunctionDef) and n.name == name), None)
    if match is None:
        raise AssertionError(f"function not found: {name} in {path.name}")
    return match


@functools.lru_cache(maxsize=None)
def _lines(path: Path) -> tuple[str, ...]:
    return tuple(path.read_text(encoding="utf-8", errors="replace").splitlines())


def _src(path: Path, node: ast.stmt) -> str:
    lines = _lines(path)
    start, end = node.lineno - 1, (node.end_lineno or node.lineno) - 1
    if start == end:
        return lines[start][node.col_offset : node.end_col_offset]
    return "\n".join([lines[start][node.col_offset :], *lines[start + 1 : end], lines[end][: node.end_col_offset]])


@functools.lru_cache(maxsize=None)
def _body(path: Path, name: str) -> str:
    stmts = _fn(path, name).body
    if stmts and isinstance(stmts[0], ast.Expr) and isinstance(stmts[0].value, ast.Constant) and isinstance(stmts[0].value.value, str):
        stmts = stmts[1:]
    return "\n".join(_src(path, stmt) for stmt in stmts)


def _callee(call: ast.Call) -> str | None:
    func = call.func
    return func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None


def _calls_to(node: ast.AST, name: str) -> list[ast.Call]:
    return [sub for sub in ast.walk(node) if isinstance(sub, ast.Call) and _callee(sub) == name]


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    return next((kw.value for kw in call.keywords if kw.arg == name), None)


def _ids_under(func: ast.AST, pred) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.If) and pred(node.test):
            ids.update(id(sub) for sub in ast.walk(node))
    return ids


def _mentions_not_gate(test: ast.expr, gate: str) -> bool:
    return any(
        isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not)
        and isinstance(n.operand, ast.Call) and isinstance(n.operand.func, ast.Name)
        and n.operand.func.id == gate
        for n in ast.walk(test)
    )


@functools.lru_cache(maxsize=None)
def _routing_ns() -> dict[str, object]:
    ns: dict[str, object] = {"os": os}
    exec(ENV.read_text(encoding="utf-8"), ns)
    for name in (SERIAL, "_golden_minimal_restore_enabled"):
        exec(_src(MODAL, _fn(MODAL, name)), ns)
    return ns


@pytest.fixture()
def routing(monkeypatch):
    for name in (
        "COMFYMODAL_GOLDEN_MINIMAL_RESTORE",
        "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM",
        "COMFYMODAL_V2CTL_PROFILE",
    ):
        monkeypatch.delenv(name, raising=False)
    return _routing_ns()


def test_routing_selects_minimal_and_legacy(routing, monkeypatch):
    en = routing["_golden_minimal_restore_enabled"]
    serial = routing[SERIAL]
    assert serial() is False and en() is False  # non-Golden absent -> legacy
    monkeypatch.setenv("COMFYMODAL_GOLDEN_MINIMAL_RESTORE", "1")
    assert en() is True  # explicit truthy -> minimal outside Golden
    monkeypatch.setenv("COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM", "1")
    monkeypatch.delenv("COMFYMODAL_GOLDEN_MINIMAL_RESTORE")
    assert serial() is True and en() is True  # Golden Serial default -> minimal
    monkeypatch.delenv("COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM")
    monkeypatch.setenv("COMFYMODAL_V2CTL_PROFILE", "golden_p1")
    assert serial() is True and en() is True  # profile-only Golden -> minimal
    for falsy in ("0", "false", "no", "off", ""):
        monkeypatch.setenv("COMFYMODAL_GOLDEN_MINIMAL_RESTORE", falsy)
        assert en() is False, falsy  # explicit falsy override -> legacy


def test_snapshot_proof_requirement_unchanged_and_fail_closed():
    src = BENCH_SRC
    body = src[src.index("def _golden_p1_snapshot_proof_present") :][:2600]
    for needle in (
        "GOLDEN_P1_SNAPSHOT_PROOF_SCHEMA", 'proof.get("passive") is not True', 'proof.get("proven") is not True',
        "surface_count", "snapshot_size_bytes", "snapshot_size_limit_bytes",
    ):
        assert needle in body, f"snapshot proof requirement lost: {needle}"
    assert 'if not _golden_p1_snapshot_proof_present(scan["snapshot_proof"]):' in src
    assert "snapshot proof absent, unproven, malformed, or contaminated" in src


def test_sage_validity_rule_is_backend_aware():
    src = BENCH_SRC
    assert 'rec.get("attention_backend_resolved") == "sage"' in src
    assert "sage_runtime_mode_resolved_missing" in src and "sage_resolved_is_auto_invalid" in src


def test_missing_or_unknown_attention_backend_fails_closed():
    src = BENCH_SRC
    assert 'rec.get("attention_backend_resolved") in {"missing", "mixed"}' in src
    assert "attention_backend_resolved_missing" in src


def test_minimal_restore_projects_existing_snapshot_proof_only():
    body = _body(MODAL, RUN)
    assert "_preserved_snapshot_proof" in body
    assert 'telemetry["golden_snapshot_content_proof"] = dict(_preserved_snapshot_proof)' in body
    assert 'getattr(self, "_restore_timing", None)' in body


def test_minimal_restore_does_not_fabricate_sage_resolution():
    body = _body(MODAL, RUN)
    assert "sage_runtime_mode_resolved" not in body and "baked_cuda" not in body


def test_minimal_restore_return_marker_opts_out_of_host_info():
    calls = _calls_to(_fn(MODAL, RUN), "set_restore_return_marker")
    assert len(calls) == 1
    assert isinstance(value := _keyword(calls[0], "include_host_info"), ast.Constant) and value.value is False


def test_set_restore_return_marker_preserves_host_info_by_default():
    func = _fn(PRELOAD, "set_restore_return_marker")
    default = dict(zip((a.arg for a in func.args.kwonlyargs), func.args.kw_defaults)).get("include_host_info")
    assert isinstance(default, ast.Constant) and default.value is True
    assert "include_host_info" not in {a.arg for a in func.args.args}
    host_calls = _calls_to(func, "_capture_host_info")
    assert len(host_calls) == 1
    assert id(host_calls[0]) in _ids_under(func, lambda t: isinstance(t, ast.Name) and t.id == "include_host_info")


def test_minimal_restore_body_is_pure_and_fail_closed():
    func = _fn(MODAL, RUN)
    body = _body(MODAL, RUN)
    forbidden = {
        "open", "Path", "read_text", "write_text", "read_bytes", "recursive_search", "Volume", "load_volume",  # filesystem / Volume
        "_sync_custom_nodes_from_volume", "_install_custom_node_requirements", "_resolve_custom_nodes_generation",  # custom-node reconciliation
        "warm_registered_folders", "_start_restore_preload", "_join_restore_preload", "_maybe_submit_restore_background_unet", "_start_production_restore_unet",  # warming / preload
        "Thread",  # transport / executor / threads
        "restore_gpu_state", "initialize_cuda", "_apply_torch_thread_limit", "_configure_runtime", "_lazy_init_snapshot_state", "_restore_eviction_boundary",  # legacy full repair
        "sync_observability_gates", "_emit_golden_diagnostics_config", "_capture_remote_identity", "clip_state_checkpoint", "_run_restore_clip_qd2_probe",  # restore-time diagnostics
    }
    called = {_callee(c) for c in ast.walk(func) if isinstance(c, ast.Call)}
    leaked = forbidden & called
    assert not leaked, f"minimal restore launched pollution: {sorted(leaked)}"
    for helper in ("_golden_minimal_reset_container_state", "_golden_minimal_restore_logical_gpu_state", "_golden_minimal_assert_models_generation"):
        assert body.count(helper) == 1  # reset + logical GPU repair + one guard, exactly
    raises = [n for n in ast.walk(func) if isinstance(n, ast.Raise)]
    assert raises and any(n.exc is None for n in raises)  # fail closed, never fall back
    repair = _body(MODAL, "_golden_minimal_restore_logical_gpu_state")
    assert "comfy.cli_args" in repair and "model_management" in repair  # logical flip only
    for probe in ("torch.cuda", "synchronize", "get_device_properties", "memory_allocated"):
        assert probe not in body and probe not in repair, probe  # no CUDA probe/sync/query
    guard = _body(MODAL, "_golden_minimal_assert_models_generation")
    assert "_decide_models_reload" in guard and '!= "skipped_generation_match"' in guard and "raise RuntimeError" in guard


def test_golden_legacy_escape_gates_restore_diagnostics():
    func = _fn(MODAL, "restore")
    gated = _ids_under(func, lambda t: _mentions_not_gate(t, SERIAL))

    def thread_named(name: str) -> ast.Call:
        found = [c for c in _calls_to(func, "Thread") if isinstance((kw := _keyword(c, "name")), ast.Constant) and kw.value == name]
        assert len(found) == 1, f"expected one {name!r} thread"
        return found[0]

    assert id(thread_named("restore_clip_qd2_probe")) in gated
    assert id(thread_named("comfymodal-folder-warm")) in gated
    resolver = _calls_to(func, "_resolve_custom_nodes_generation")
    assert len(resolver) == 1 and id(resolver[0]) in gated
    boot = [n for n in ast.walk(func) if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_boot_cn_gen" for t in n.targets)]
    assert boot and all(id(n) in gated for n in boot)
