"""Contracts for the A/A2/A3 source population isolation arms.

The previous phase proved two harness defects that both produced confidently
wrong evidence while every available check passed, so these tests are mostly
about the arms being *provable* rather than about arithmetic:

* an arm whose declared treatment did not happen must fail closed, never
  downgrade to the control;
* the control must carry no treatment at all, provably;
* the three arms must differ in exactly one thing and share every other
  production property;
* arm identity is deploy-level, so a run-time override cannot request an arm
  different from the one that was deployed.
"""

from __future__ import annotations

import ctypes
import inspect
import mmap as _mmap
import os
import pathlib
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from comfymodal_runtime import golden_source_threads as gsrc  # noqa: E402
from comfymodal_runtime import source_copy_isolation as sci  # noqa: E402
from comfymodal_runtime import source_population_policy as policy  # noqa: E402

_MIB = 1024 * 1024
ROOT = pathlib.Path(__file__).resolve().parents[1]


# ── fakes: a libc with posix_fadvise, and an mmapper that records flags ──

def _int(value) -> int:  # noqa: ANN001
    """Accept both a plain int and a ctypes integer the way build_plan passes it."""
    return int(getattr(value, "value", value))


class _FakeFadvise:
    """Callable stand-in whose ``argtypes``/``restype`` are settable."""

    def __init__(self, owner: "_FakeLibc") -> None:
        self._owner = owner
        self.argtypes = None
        self.restype = None

    def __call__(self, fd, offset, length, advice):  # noqa: ANN001
        self._owner.calls.append(
            (_int(fd), _int(offset), _int(length), _int(advice))
        )
        return self._owner.rc


class _FakeLibc:
    """Records every ``posix_fadvise`` call and can be made to fail."""

    def __init__(self, rc: int = 0) -> None:
        self.calls: list[tuple[int, int, int, int]] = []
        self.rc = rc
        self.posix_fadvise = _FakeFadvise(self)


class _FakeMapper:
    """A ``_MAPPER`` stand-in that records the flags each mapping was made with."""

    def __init__(self, fail_errno: int | None = None) -> None:
        self.mmap_calls: list[dict] = []
        self.munmap_calls: list[dict] = []
        self.fail_errno = fail_errno

    def mmap(self, addr, length, prot, flags, fd, offset):  # noqa: ANN001
        self.mmap_calls.append({
            "length": _int(length), "prot": _int(prot), "flags": _int(flags),
            "fd": _int(fd), "offset": _int(offset),
        })
        if self.fail_errno is not None:
            ctypes.set_errno(self.fail_errno)
            return ctypes.c_void_p(-1)
        # A small, real anonymous address so the plan carries a usable pointer.
        self._backing = _mmap.mmap(-1, 4096)
        return ctypes.c_void_p(
            ctypes.addressof(ctypes.c_char.from_buffer(memoryview(self._backing)))
        )

    def memmove(self, dst, src, length):  # noqa: ANN001
        return dst

    def munmap(self, addr, length):  # noqa: ANN001
        self.munmap_calls.append({"length": int(length)})
        return 0


def _plan_message(path: pathlib.Path, size: int) -> dict:
    ranges = sci.file_block_ranges(size)
    stat = path.stat()
    return {
        "generation": 1,
        "path": str(path),
        "identity": [int(stat.st_dev), int(stat.st_ino), int(stat.st_size), int(stat.st_mtime_ns)],
        "destination_size": int(stat.st_size),
        "mmap_lifecycle": "whole",
        "ranges": [
            {
                "source_offset": item[0], "length": item[1],
                "destination_offset": item[2], "record_id": item[3],
            }
            for item in ranges
        ],
    }


def _build(tmp_path: pathlib.Path, monkeypatch, arm: str, *, gate: bool = True,
           libc_rc: int = 0, mapper_fail: int | None = None):
    """Run the real ``build_plan`` under the real policy for one arm."""
    source = tmp_path / "model.bin"
    size = 4 * _MIB
    source.write_bytes(b"\x5a" * size)
    fake_libc = _FakeLibc(rc=libc_rc)
    fake_mapper = _FakeMapper(fail_errno=mapper_fail)
    monkeypatch.setattr(policy, "_libc", lambda: fake_libc)
    monkeypatch.setattr(gsrc, "_MAPPER", fake_mapper)
    monkeypatch.setenv(policy.ARM_ENV, arm)
    if gate:
        monkeypatch.setenv(policy.POPULATION_GATE_ENV, "1")
    else:
        monkeypatch.delenv(policy.POPULATION_GATE_ENV, raising=False)
    plan = gsrc.build_plan(_plan_message(source, size), open_source=True)
    return plan, fake_libc, fake_mapper


# ── arm A: the control carries no treatment at all ──────────────────────

def test_control_arm_does_not_call_fadvise(tmp_path, monkeypatch):
    plan, fake_libc, fake_mapper = _build(tmp_path, monkeypatch, "A")
    assert fake_libc.calls == []
    assert plan.population_evidence["fadvise_called"] is False
    assert plan.population_evidence["fadvise_call_count"] == 0


def test_control_arm_does_not_set_map_populate(tmp_path, monkeypatch):
    plan, _libc, fake_mapper = _build(tmp_path, monkeypatch, "A")
    assert len(fake_mapper.mmap_calls) == 1
    call = fake_mapper.mmap_calls[0]
    assert call["flags"] == policy.MAP_PRIVATE
    assert not call["flags"] & policy.MAP_POPULATE
    assert plan.population_evidence["map_populate_requested"] is False
    assert plan.population_evidence["map_populate_in_flags"] is False


# ── arm A2: exactly one POSIX_FADV_WILLNEED per generation ──────────────

def test_a2_calls_posix_fadvise_willneed_exactly_once(tmp_path, monkeypatch):
    plan, fake_libc, fake_mapper = _build(tmp_path, monkeypatch, "A2")
    assert len(fake_libc.calls) == 1
    fd, offset, length, advice = fake_libc.calls[0]
    assert advice == policy.POSIX_FADV_WILLNEED
    assert offset == 0 and length == 0, "whole-file advice, not a per-block window"
    assert fd == plan.fd, "the same persistent descriptor the mapping uses"
    assert plan.population_evidence["fadvise_call_count"] == 1
    assert plan.population_evidence["fadvise_return_code"] == 0
    assert plan.population_evidence["fadvise_wall_ms"] is not None


def test_a2_is_called_once_per_generation_not_per_block(tmp_path, monkeypatch):
    source = tmp_path / "model.bin"
    size = 4 * _MIB
    source.write_bytes(b"\x5a" * size)
    fake_libc = _FakeLibc()
    fake_mapper = _FakeMapper()
    monkeypatch.setattr(policy, "_libc", lambda: fake_libc)
    monkeypatch.setattr(gsrc, "_MAPPER", fake_mapper)
    monkeypatch.setenv(policy.ARM_ENV, "A2")
    monkeypatch.setenv(policy.POPULATION_GATE_ENV, "1")
    stat = source.stat()
    identity = [int(stat.st_dev), int(stat.st_ino), int(stat.st_size), int(stat.st_mtime_ns)]
    for generation in (1, 2, 3):
        message = _plan_message(source, size)
        message["generation"] = generation
        message["identity"] = identity
        gsrc.build_plan(message, open_source=True)
    assert len(fake_libc.calls) == 3, "one per generation"
    assert len(fake_mapper.mmap_calls) == 3


def test_a2_keeps_the_original_map_private_flags(tmp_path, monkeypatch):
    _plan, _libc, fake_mapper = _build(tmp_path, monkeypatch, "A2")
    assert len(fake_mapper.mmap_calls) == 1
    assert fake_mapper.mmap_calls[0]["flags"] == policy.MAP_PRIVATE
    assert not fake_mapper.mmap_calls[0]["flags"] & policy.MAP_POPULATE


def test_a2_failure_is_fail_closed(tmp_path, monkeypatch):
    with pytest.raises(policy.SourcePopulationError) as excinfo:
        _build(tmp_path, monkeypatch, "A2", libc_rc=22)
    assert "posix_fadvise_willneed_failed" in str(excinfo.value)
    assert "errno" in str(excinfo.value)


def test_a2_without_the_gate_fails_closed_rather_than_downgrading(monkeypatch):
    monkeypatch.setenv(policy.ARM_ENV, "A2")
    monkeypatch.delenv(policy.POPULATION_GATE_ENV, raising=False)
    with pytest.raises(policy.SourcePopulationError) as excinfo:
        policy.active_arm()
    assert "requires_gate" in str(excinfo.value)


# ── arm A3: MAP_POPULATE set exactly once at mapping creation ────────────

def test_a3_sets_map_populate_exactly_once(tmp_path, monkeypatch):
    plan, fake_libc, fake_mapper = _build(tmp_path, monkeypatch, "A3")
    assert len(fake_mapper.mmap_calls) == 1
    flags = fake_mapper.mmap_calls[0]["flags"]
    assert flags == policy.MAP_PRIVATE | policy.MAP_POPULATE
    assert flags & policy.MAP_POPULATE
    assert plan.population_evidence["map_populate_requested"] is True
    assert plan.population_evidence["map_populate_in_flags"] is True
    assert plan.population_evidence["map_populate_accepted_by_mmap"] is True


def test_a3_does_not_call_fadvise(tmp_path, monkeypatch):
    _plan, fake_libc, _mapper = _build(tmp_path, monkeypatch, "A3")
    assert fake_libc.calls == []


def test_a3_otherwise_uses_the_identical_whole_file_mapping(tmp_path, monkeypatch):
    control, _libc, control_mapper = _build(tmp_path, monkeypatch, "A")
    populate = pathlib.Path(tmp_path / "second")
    populate.mkdir()
    populated, _libc2, populate_mapper = _build(populate, monkeypatch, "A3")
    left = control_mapper.mmap_calls[0]
    right = populate_mapper.mmap_calls[0]
    for field in ("length", "prot", "offset"):
        assert left[field] == right[field], f"A3 changed {field}"
    # The descriptor number is per-plan, so identity is "each mapping used its
    # own plan's descriptor", not "both mappings saw the same number".
    assert left["fd"] == control.fd
    assert right["fd"] == populated.fd
    assert left["fd"] != right["fd"]
    assert control.map_length == populated.map_length == 4 * _MIB
    assert control.mmap_lifecycle == populated.mmap_lifecycle == "whole"
    assert control.map_address and populated.map_address


def test_a3_mapping_failure_is_fail_closed(tmp_path, monkeypatch):
    with pytest.raises(gsrc.SourceProtocolError):
        _build(tmp_path, monkeypatch, "A3", mapper_fail=12)


def test_a3_population_observability_is_declared_unavailable(tmp_path, monkeypatch):
    plan, _libc, _mapper = _build(tmp_path, monkeypatch, "A3")
    evidence = plan.population_evidence
    # Requesting the flag and having mmap accept it is observable. Whether
    # gVisor's Sentry actually faulted the range in is not, and saying so is
    # required: mincore on a mounted Volume is exactly the unreliable probe
    # Phase-1 already flagged.
    assert evidence["page_population_observable"] is False
    assert "unavailable" in str(evidence["page_population_evidence"])


# ── shared production properties across all three arms ───────────────────

def test_all_three_arms_share_every_production_copy_property():
    for arm in ("A", "A2", "A3"):
        layout = sci.arm_layout(arm)
        assert layout["source"] == "model_mmap"
        assert layout["destination"] == "pinned_shared_arena"
        assert layout["variants"] == ("concurrent4",)
    assert gsrc.SLOT_BYTES == 64 * _MIB
    assert gsrc.SLOT_COUNT == 16
    assert gsrc.ARENA_BYTES == 16 * 64 * _MIB == 1073741824
    assert gsrc.READER_COUNT == 4
    assert gsrc.PACER_GAP_NS == 4_000_000


def test_the_experiment_does_not_own_the_copy_kernel_or_the_hooks():
    source = inspect.getsource(sci)
    assert "def execute_block" not in source
    assert "def _run_reader_loop" not in source
    assert "def posix_fadvise" not in source
    # It drives the production hooks; it does not reimplement them.
    assert "gsrc.build_plan" in source
    assert "population_contract" in source


def test_the_two_hooks_stay_in_build_plan_at_the_two_measured_sites():
    # The docstring names both hooks on purpose, so the ordering is asserted on
    # the executable body rather than on the prose.
    body = inspect.getsource(gsrc.build_plan).split('"""', 2)[-1]
    open_at = body.index("os.open(")
    fadvise_at = body.index("_population_policy().fadvise_willneed(")
    mmap_at = body.index("_MAPPER.mmap(")
    assert open_at < fadvise_at < mmap_at, (
        "fadvise must sit between the descriptor open and the mapping"
    )
    assert body.count("_population_policy().fadvise_willneed(") == 1
    assert body.count("_MAPPER.mmap(") == 1
    assert body.count("_population_policy().mapping_flags(") == 1
    assert body.count("_population_policy().confirm_mapping(") == 1


def test_pinned_arena_teardown_ordering_is_preserved():
    close = inspect.getsource(sci.PinnedSharedArena.close)
    assert close.index("cudaHostUnregister") < close.index("self.buffer.release()")
    assert close.index("self.buffer.release()") < close.index("self.shm.close()")


# ── arm identity reaches the container, at deploy level ────────────────

def test_arm_selector_is_deploy_level_not_run_only():
    registry = (ROOT / "config" / "v2" / "flag_registry.toml").read_text(encoding="utf-8")
    index = registry.index('name = "COMFYMODAL_GOLDEN_SOURCE_COPY_ISOLATION_ARM"')
    block = registry[index:registry.index("[[flag]]", index)]
    assert 'change_requires = "deploy"' in block
    assert 'change_requires = "run"' not in block
    for arm in ("A", "A2", "A3"):
        assert f'"{arm}"' in block


@pytest.mark.parametrize(
    "slug,arm,app",
    [
        ("a-control", "A", "batch-p9srccopy-a-control-h100"),
        ("a2-willneed", "A2", "batch-p9srccopy-a2-willneed-h100"),
        ("a3-populate", "A3", "batch-p9srccopy-a3-populate-h100"),
    ],
)
def test_each_arm_owns_a_deploy_level_profile_and_app(slug, arm, app):
    path = ROOT / "config" / "v2" / "profiles" / f"golden_p1_parallel_p9_srccopy_{slug}_h100.toml"
    text = path.read_text(encoding="utf-8")
    assert f'app = "{app}"' in text
    assert f'COMFYMODAL_GOLDEN_SOURCE_COPY_ISOLATION_ARM = "{arm}"' in text
    assert 'extends = "golden_p1_parallel_p9_srccopy_iso_h100"' in text
    # The gate is never baked into the container env: it is process-local, so
    # the real Golden source owner in the same container stays untreated.
    assert "COMFYMODAL_GOLDEN_SOURCE_COPY_ISOLATION_POPULATION =" not in text


def test_population_gate_is_never_a_deployed_environment_value():
    profiles = (ROOT / "config" / "v2" / "profiles")
    for path in profiles.glob("*srccopy*.toml"):
        text = path.read_text(encoding="utf-8")
        assert "COMFYMODAL_GOLDEN_SOURCE_COPY_ISOLATION_POPULATION" not in text.split(
            "[environment]"
        )[-1]


# ── reported treatment identity matches actual behaviour ────────────────

def test_population_contract_rejects_an_arm_whose_treatment_did_not_happen():
    # Arm A2 with no fadvise call in the payload.
    contract = sci.population_contract(
        {"arm": "A2", "fadvise_called": False, "fadvise_call_count": 0},
        "A2",
    )
    assert contract["satisfied"] is False
    assert contract["error"] == "arm_treatment_not_observed"


def test_population_contract_rejects_an_arm_observed_under_a_different_name():
    contract = sci.population_contract({"arm": "A"}, "A2")
    assert contract["satisfied"] is False
    assert "arm_treatment_mismatch" in str(contract["error"])


def test_population_contract_rejects_a_control_that_carries_a_treatment():
    contract = sci.population_contract(
        {"arm": "A", "fadvise_called": True}, "A"
    )
    assert contract["satisfied"] is False
    assert contract["error"] == "control_arm_carries_treatment"
    clean = sci.population_contract({"arm": "A", "fadvise_called": False}, "A")
    assert clean["satisfied"] is True


def test_population_contract_accepts_a2_only_with_one_successful_call(monkeypatch):
    monkeypatch.setenv(policy.ARM_ENV, "A2")
    good = sci.population_contract(
        {"arm": "A2", "fadvise_called": True, "fadvise_call_count": 1,
         "fadvise_return_code": 0, "fadvise_wall_ms": 12.5},
        "A2",
    )
    assert good["satisfied"] is True
    assert good["fadvise_wall_ms"] == 12.5
    twice = sci.population_contract(
        {"arm": "A2", "fadvise_called": True, "fadvise_call_count": 2,
         "fadvise_return_code": 0},
        "A2",
    )
    assert twice["satisfied"] is False, "exactly once per generation"


def test_population_contract_accepts_a3_only_with_an_accepted_populate(monkeypatch):
    monkeypatch.setenv(policy.ARM_ENV, "A3")
    good = sci.population_contract(
        {"arm": "A3", "map_populate_in_flags": True,
         "map_populate_accepted_by_mmap": True, "mmap_flags": 0x8002},
        "A3",
    )
    assert good["satisfied"] is True
    assert good["mmap_flags"] == 0x8002
    unaccepted = sci.population_contract(
        {"arm": "A3", "map_populate_in_flags": True,
         "map_populate_accepted_by_mmap": False},
        "A3",
    )
    assert unaccepted["satisfied"] is False


def test_population_contract_validates_the_declared_arm_even_when_gated_off(monkeypatch):
    monkeypatch.delenv(policy.POPULATION_GATE_ENV, raising=False)
    monkeypatch.setenv(policy.ARM_ENV, "A")
    assert sci.population_contract({"arm": "A"}, "A")["satisfied"] is True


# ── setup cost accounting, so a fast copy loop cannot hide a slow setup ──

def test_setup_costs_separates_treatment_cost_from_the_copy_loop():
    costs = sci.setup_costs(
        population={
            "fd_open_wall_ms": 1.0, "fadvise_wall_ms": 900.0,
            "mmap_wall_ms": 3.0, "plan_build_total_ms": 904.0,
        },
        generation_open_ns=1_000_000_000,
        setup_done_ns=1_905_000_000,
        copy_started_ns=1_910_000_000,
        copy_ended_ns=1_910_000_000 + 2_000_000_000,
        copies=[{"memcpy_start_ns": 1_950_000_000, "wall_ms": 40.0}],
    )
    assert costs["fadvise_wall_ms"] == 900.0
    assert costs["generation_open_to_setup_done_ms"] == 905.0
    assert costs["generation_open_to_first_copy_ms"] == 950.0
    assert costs["copy_loop_wall_ms"] == 2000.0
    assert costs["setup_plus_copy_loop_total_ms"] == 2905.0


def test_setup_costs_report_none_when_no_copy_ever_started():
    costs = sci.setup_costs(
        population={}, generation_open_ns=0, setup_done_ns=10,
        copy_started_ns=10, copy_ended_ns=10, copies=[],
    )
    assert costs["generation_open_to_first_copy_ms"] is None
    assert costs["setup_to_first_copy_ms"] is None


def test_ordinal_head_separates_the_first_eight_copies_from_the_rest():
    copies = [
        {"copy_ordinal": index, "wall_ms": float(100 - index) if index < 8 else 40.0}
        for index in range(32)
    ]
    head = sci.ordinal_head(copies, head=8)
    assert head["head_size"] == 8
    assert head["head_max_wall_ms"] == 100.0
    assert head["head_wall_ms"]["count"] == 8
    assert head["tail_wall_ms"]["count"] == 24
    assert head["per_ordinal"]["0"]["wall_ms"]["max"] == 100.0
    assert set(head["per_ordinal"]) == {str(index) for index in range(8)}
    assert head["per_ordinal"]["7"]["wall_ms"]["max"] == 93.0
    assert head["tail_wall_ms"]["max"] == 40.0


def test_ordinal_head_of_an_empty_run_is_not_a_crash():
    head = sci.ordinal_head([], head=8)
    assert head["head_max_wall_ms"] == 0.0
    assert head["head_wall_ms"]["count"] == 0


# ── the population gate is process-local and self-cleaning ──────────────

def test_population_gate_is_raised_only_inside_the_context(monkeypatch):
    monkeypatch.delenv(policy.POPULATION_GATE_ENV, raising=False)
    with sci._PopulationGate("A2"):
        assert os.environ.get(policy.POPULATION_GATE_ENV) == "1"
    assert policy.POPULATION_GATE_ENV not in os.environ


def test_population_gate_leaves_the_control_untouched(monkeypatch):
    monkeypatch.delenv(policy.POPULATION_GATE_ENV, raising=False)
    with sci._PopulationGate("A"):
        assert policy.POPULATION_GATE_ENV not in os.environ
    assert policy.POPULATION_GATE_ENV not in os.environ


def test_population_gate_restores_a_pre_existing_value(monkeypatch):
    monkeypatch.setenv(policy.POPULATION_GATE_ENV, "0")
    with sci._PopulationGate("A3"):
        assert os.environ[policy.POPULATION_GATE_ENV] == "1"
    assert os.environ[policy.POPULATION_GATE_ENV] == "0"


def test_population_gate_raises_the_exception_it_was_given(monkeypatch):
    monkeypatch.delenv(policy.POPULATION_GATE_ENV, raising=False)
    with pytest.raises(RuntimeError):
        with sci._PopulationGate("A2"):
            raise RuntimeError("inner failure")
    assert policy.POPULATION_GATE_ENV not in os.environ


# ── the A/B/C/D arms and their contracts are all still present ──────────

def test_prior_arms_are_unchanged_and_still_selectable():
    assert sci.arm_layout("B")["destination"] == "anonymous"
    assert sci.arm_layout("C")["source"] == "anonymous"
    assert sci.arm_layout("D")["source"] == "anonymous"
    assert sci.arm_layout("C")["variants"] == ("single", "concurrent4")
    assert sci.arm_layout("D")["variants"] == ("single", "concurrent4")
    assert sci.MAPPED_SOURCE_ARMS == ("A", "A2", "A3")
    assert sci.POPULATION_TREATMENT_ARMS == ("A2", "A3")
    assert set(sci.ARMS) >= {"A", "A2", "A3", "B", "C", "D"}


@pytest.mark.parametrize("arm", ["A", "A2", "A3", "B", "C", "D"])
def test_the_policy_accepts_every_arm_the_selector_offers(arm, monkeypatch):
    # A/B/C/D share one deploy-level selector.  If the population policy rejected
    # the arms that carry no population arm, the already-completed cohort would
    # silently become unrunnable the moment this module was imported.
    monkeypatch.setenv(policy.ARM_ENV, arm)
    assert policy.declared_arm() == arm


@pytest.mark.parametrize("arm", ["A", "B", "C", "D"])
def test_arms_without_a_population_treatment_resolve_to_the_control(arm, monkeypatch):
    monkeypatch.delenv(policy.POPULATION_GATE_ENV, raising=False)
    monkeypatch.setenv(policy.ARM_ENV, arm)
    assert policy.active_arm() == "A"


@pytest.mark.parametrize("arm", ["A2", "A3"])
def test_a_declared_treatment_arm_still_refuses_to_run_without_the_gate(arm, monkeypatch):
    monkeypatch.delenv(policy.POPULATION_GATE_ENV, raising=False)
    monkeypatch.setenv(policy.ARM_ENV, arm)
    with pytest.raises(policy.SourcePopulationError):
        policy.active_arm()


@pytest.mark.parametrize("value", ["", "  ", "A9", "arm", "A;A", "A-"])
def test_a_malformed_arm_is_a_hard_error_not_a_silent_control(value, monkeypatch):
    monkeypatch.setenv(policy.ARM_ENV, value)
    with pytest.raises(policy.SourcePopulationError):
        policy.declared_arm()


@pytest.mark.parametrize("arm", ["C", "D"])
def test_an_arm_with_no_population_contract_is_not_an_unsatisfied_one(arm, monkeypatch):
    # C/D map no source at all, so the contract reports "not applicable" instead
    # of failing a run that was never treated.  B keeps the mapped source and is
    # covered by the mapped-control test below.
    monkeypatch.setenv(policy.ARM_ENV, arm)
    contract = sci.population_contract({}, arm)
    assert contract["applicable"] is False
    assert contract["satisfied"] is True
    assert contract["reason"] == "arm_maps_no_source"


def test_b_is_still_checked_as_the_untreated_mapped_control(monkeypatch):
    monkeypatch.delenv(policy.POPULATION_GATE_ENV, raising=False)
    monkeypatch.setenv(policy.ARM_ENV, "B")
    clean = sci.population_contract({"arm": "A"}, "B")
    assert clean["applicable"] is True
    assert clean["satisfied"] is True
    treated = sci.population_contract({"arm": "A", "fadvise_called": True}, "B")
    assert treated["satisfied"] is False
    assert treated["error"] == "control_arm_carries_treatment"


def test_population_module_carries_no_import_of_the_source_owner():
    text = (ROOT / "comfymodal_runtime" / "source_population_policy.py").read_text(
        encoding="utf-8"
    )
    # Only executable import statements matter; the module docstring explains
    # why the constraint exists and names the module on purpose.
    statements = [
        line.strip() for line in text.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    assert statements == [
        "from __future__ import annotations",
        "import ctypes", "import os", "import time", "from typing import Any",
    ]
    for line in statements:
        assert "golden_source_threads" not in line
        assert "comfymodal_runtime" not in line
        assert not line.startswith("from .")


def test_child_safe_loader_resolves_the_policy_module():
    module = gsrc._load_sibling_module(
        "comfymodal_runtime.source_population_policy",
        "source_population_policy.py",
    )
    assert module.MAP_POPULATE == 0x8000
    assert module.POSIX_FADV_WILLNEED == 3
    assert callable(module.fadvise_willneed)
    assert callable(module.mapping_flags)
    assert callable(module.confirm_mapping)
