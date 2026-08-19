"""V2 snapshot manifest R2a extensions: targeted local validation.

Covers the snapshot-build manifest additions in
``comfymodal_runtime.snapshot_build_manifest``:

- ``_capture_status`` parses ``RssAnon`` -> ``rss_anon`` and
  ``RssFile`` -> ``rss_file`` (kB ints) alongside the Vm* fields.
- ``_capture_cgroup`` returns ``{"available", "memory_current_bytes"}``.
- ``capture_snapshot_manifest(hygiene=...)`` stores the hygiene event under
  ``manifest["capture_hygiene"]`` (absent when ``hygiene`` is None).
- Unreadable /proc never raises; heavy capture helpers are stubbed so the
  captures are fast and deterministic (no Modal, no ComfyUI graph).
- The compact ``[v2.snapshot_manifest]`` console line carries the new
  ``rss_anon_kb=`` / ``rss_file_kb=`` fields.
"""

from __future__ import annotations

import builtins
import io

from comfymodal_runtime import snapshot_build_manifest as sbm

FAKE_STATUS = """\
Name:\ttest
VmRSS:\t 12345 kB
RssAnon:\t 8000 kB
RssFile:\t 4000 kB
VmSize:\t 99999 kB
VmData:\t 50000 kB
Threads:\t 7
"""


def _install_capture_stubs(monkeypatch, *, status: dict, cgroup: dict) -> None:
    """Cheap deterministic stand-ins for every heavy capture helper."""
    monkeypatch.setattr(sbm, "_capture_status", lambda: status)
    monkeypatch.setattr(sbm, "_capture_smaps_rollup", lambda: None)
    monkeypatch.setattr(sbm, "_capture_mappings", lambda: {})
    monkeypatch.setattr(sbm, "_capture_modules", lambda: {"count": 0})
    monkeypatch.setattr(sbm, "_capture_threads", lambda: {})
    monkeypatch.setattr(sbm, "_capture_children", lambda: {"children": []})
    monkeypatch.setattr(sbm, "_capture_fds", lambda: {})
    monkeypatch.setattr(sbm, "_capture_torch_threads", lambda: {})
    monkeypatch.setattr(sbm, "_capture_retained_models", lambda model_ctx: {})
    monkeypatch.setattr(sbm, "_capture_executors", lambda: {})
    monkeypatch.setattr(sbm, "_capture_gc", lambda: {})
    monkeypatch.setattr(sbm, "_capture_modal_identity", lambda: {})
    monkeypatch.setattr(sbm, "_capture_cgroup", lambda: cgroup)


# ── 1. _capture_status parses rss_anon / rss_file ───────────────────────────


def test_capture_status_parses_rss_anon_and_rss_file(monkeypatch):
    monkeypatch.setattr(sbm, "_read_proc", lambda *args, **kwargs: FAKE_STATUS)
    status = sbm._capture_status()
    assert status["vmrss"] == 12345
    assert status["rss_anon"] == 8000
    assert status["rss_file"] == 4000
    assert status["vmsize"] == 99999
    assert status["vmdata"] == 50000
    assert status["threads"] == 7


# ── 2. Unreadable proc -> empty dict, never raises ──────────────────────────


def test_capture_status_unreadable_proc_returns_empty(monkeypatch):
    monkeypatch.setattr(sbm, "_read_proc", lambda *args, **kwargs: None)
    assert sbm._capture_status() == {}


# ── 3. _capture_cgroup: available / unavailable ─────────────────────────────


def test_capture_cgroup_v2_memory_current(monkeypatch):
    # _capture_cgroup opens the two candidate paths directly; patch open() so
    # the v2 path is readable and the v1 fallback is not.
    def _fake_open(path, *args, **kwargs):
        if str(path).endswith("memory.current"):
            return io.StringIO("1048576\n")
        raise FileNotFoundError(str(path))

    monkeypatch.setattr(builtins, "open", _fake_open)
    assert sbm._capture_cgroup() == {"available": True, "memory_current_bytes": 1048576}


def test_capture_cgroup_unreadable(monkeypatch):
    def _fake_open(path, *args, **kwargs):
        raise FileNotFoundError(str(path))

    monkeypatch.setattr(builtins, "open", _fake_open)
    assert sbm._capture_cgroup() == {"available": False, "memory_current_bytes": None}


# ── 4. capture_snapshot_manifest embeds the hygiene event ───────────────────


def test_capture_snapshot_manifest_embeds_hygiene(monkeypatch):
    _install_capture_stubs(
        monkeypatch,
        status={"vmrss": 1},
        cgroup={"available": False, "memory_current_bytes": None},
    )

    hygiene_event = {"enabled": 1}
    manifest = sbm.capture_snapshot_manifest("before_capture", hygiene=hygiene_event)
    assert isinstance(manifest, dict)
    assert manifest["capture_hygiene"] == hygiene_event
    assert manifest["cgroup"] == {"available": False, "memory_current_bytes": None}
    assert sbm.latest_manifests()["before_capture"] == manifest

    # hygiene=None -> the key is absent entirely.
    plain = sbm.capture_snapshot_manifest("no_hygiene")
    assert "capture_hygiene" not in plain
    assert "cgroup" in plain


# ── 5. Never raises on unreadable proc ──────────────────────────────────────


def test_capture_never_raises_on_unreadable_proc(monkeypatch):
    _install_capture_stubs(
        monkeypatch,
        status={},
        cgroup={"available": False, "memory_current_bytes": None},
    )
    manifest = sbm.capture_snapshot_manifest("x")  # must not raise
    assert isinstance(manifest, dict)


# ── 6. Compact print line carries anon/file kB ──────────────────────────────


def test_compact_print_line_carries_anon_and_file_kb(monkeypatch, capsys):
    status = {"vmrss": 12345, "vmhwm": 13000, "vmsize": 500000, "rss_anon": 8000, "rss_file": 4000}
    _install_capture_stubs(
        monkeypatch,
        status=status,
        cgroup={"available": False, "memory_current_bytes": None},
    )
    capsys.readouterr()
    sbm.capture_snapshot_manifest("print_stage")
    out = capsys.readouterr().out
    lines = [l for l in out.splitlines() if l.startswith("[v2.snapshot_manifest]")]
    assert len(lines) == 1
    assert "rss_anon_kb=8000" in lines[0]
    assert "rss_file_kb=4000" in lines[0]
