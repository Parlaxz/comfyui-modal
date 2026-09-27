"""Part 11 unit tests for comfymodal_runtime.host_hardware_telemetry.

Covers (all must pass on a Windows dev machine — no /proc, no CUDA, no
lscpu — AND logically cover the Linux/gVisor paths via monkeypatched
fixtures):

   1  parse_cpuinfo: Sapphire Rapids (avx512_vnni True), Cascade Lake
      (avx512_vnni False), AMD Zen 3 (no avx512), heterogeneous blocks
      -> homogeneous False, single-processor file, empty/None input
   2  missing/unreadable cpuinfo -> no identity fields, count 0, no raise
   3  fingerprint hash: stable under cpu MHz / model-name changes, changes
      under stepping / flags changes, 64-hex lowercase
   4  lscpu absent (FileNotFoundError) and fake ``lscpu -J`` JSON parsing
    5  PSI absent -> per-source unavailable, no fake zeros, and the single
      /proc/pressure existence gate means NO pressure file opens; valid PSI
      files -> avg10/avg60/avg300 floats + total ints
    6  cgroup: v2 via mountinfo discovery, v1 detected from /proc/self/cgroup
      ALONE (sentry-virtualized paths -> no mountinfo/controller reads),
      and unavailable
   7  GPU: nvidia-smi/nvml absent -> gpu_source unavailable; fake nvidia-smi
      CSV -> parsed fields + 16-hex sha256 uuid hash, raw UUID never stored
   8  no fake zeros: rusage getrusage failure and unreadable /proc/self/stat
      -> every field individually None
   9  failure non-fatal + overhead bounded: collect_host_fingerprint with
      everything failing -> dict, probe_statuses, bounded probe_wall_ms
  10  diagnostics do not alter execution: fake trace object, once-per-process
      fingerprint guard, flat scalar snapshot metadata, positive deltas
  11  integration with the fixed model_preload fault code
      (_PageFaultSnapshot.now / _pagefault_delta)
  12  two-tier H2D gating: classify_h2d (TRAILING_SYNC_STALL /
      COPY_INTERVAL_SLOW / HOST_OVERHEAD_AROUND_COPY / UNKNOWN/MIXED) and
      should_trigger_slow_probe (default/env threshold + diag flag)
  13  two-tier forensics: emit_slow_h2d_forensics emits host_forensic_slow_h2d
      with classification + Tier B gpu/lscpu fields, never raises
  14  Tier A is subprocess-free: fingerprint + all 4 snapshot phases with
      subprocess.run patched to raise; capability cache probes psi/cgroup once
      and snapshots skip repeat file reads; lscpu deferred unless diag mode;
      opened-path reduction (psi gate + v1 short-circuit)
  15  static GPU identity via already-loaded torch (torch_only / unavailable);
      no ctypes/driver calls anywhere on the healthy path
"""

from __future__ import annotations

import io
import json
import os
import re
import sys
import types
from types import SimpleNamespace

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.normpath(os.path.join(_HERE, ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from comfymodal_runtime import host_hardware_telemetry as hht
from comfymodal_runtime.model_preload import _PageFaultSnapshot, _pagefault_delta


# ---------------------------------------------------------------------------
# CPUINFO fixtures (real-world layouts)
# ---------------------------------------------------------------------------

SPR_CPUINFO = """processor       : 0
vendor_id       : GenuineIntel
cpu family      : 6
model           : 143
model name      : Intel(R) Xeon(R) Platinum 8480+
stepping        : 6
microcode       : 0x2b000181
cpu MHz         : 2700.000
cache size      : 1050624 KB
physical id     : 0
siblings        : 8
cpu cores       : 8
core id         : 0
flags           : fpu vme de pse tsc msr pae mce cx8 apic sep mtrr pge mca cmov pat pse36 clflush dts acpi mmx fxsr sse sse2 ss ht tm pbe syscall nx pdpe1gb rdtscp lm constant_tsc art arch_perfmon pebs bts rep_good nopl xtopology nonstop_tsc cpuid aperfmperf pni pclmulqdq dtes64 monitor ds_cpl vmx smx est tm2 ssse3 sdbg fma cx16 xtpr pdcm pcid dca sse4_1 sse4_2 x2apic movbe popcnt tsc_deadline_timer aes xsave avx f16c rdrand lahf_lm abm 3dnowprefetch cpuid_fault epb cat_l3 cdp_l3 invpcid_single intel_ppin ssbd mba ibrs ibpb stibp ibrs_enhanced fsgsbase tsc_adjust bmi1 avx2 smep bmi2 erms invpcid cqm rdt_a avx512f avx512dq rdseed adx smap avx512ifma clflushopt clwb intel_pt avx512cd sha_ni avx512bw avx512vl xsaveopt xsavec xgetbv1 xsaves split_lock_detect user_shstk avx_vnni avx512_bf16 dtherm ida arat pln pts hwp hwp_act_window hwp_epp hwp_pkg_req hfi vnni umip pku ospke waitpkg gfni vaes vpclmulqdq tme rdpid movdiri movdir64b fsrm serialize avx512_vnni pconfig arch_lbr ibt flush_l1d arch_capabilities

processor       : 1
vendor_id       : GenuineIntel
cpu family      : 6
model           : 143
model name      : Intel(R) Xeon(R) Platinum 8480+
stepping        : 6
microcode       : 0x2b000181
cpu MHz         : 2700.000
cache size      : 1050624 KB
physical id     : 0
siblings        : 8
cpu cores       : 8
core id         : 1
flags           : fpu vme de pse tsc msr pae mce cx8 apic sep mtrr pge mca cmov pat pse36 clflush dts acpi mmx fxsr sse sse2 ss ht tm pbe syscall nx pdpe1gb rdtscp lm constant_tsc art arch_perfmon pebs bts rep_good nopl xtopology nonstop_tsc cpuid aperfmperf pni pclmulqdq dtes64 monitor ds_cpl vmx smx est tm2 ssse3 sdbg fma cx16 xtpr pdcm pcid dca sse4_1 sse4_2 x2apic movbe popcnt tsc_deadline_timer aes xsave avx f16c rdrand lahf_lm abm 3dnowprefetch cpuid_fault epb cat_l3 cdp_l3 invpcid_single intel_ppin ssbd mba ibrs ibpb stibp ibrs_enhanced fsgsbase tsc_adjust bmi1 avx2 smep bmi2 erms invpcid cqm rdt_a avx512f avx512dq rdseed adx smap avx512ifma clflushopt clwb intel_pt avx512cd sha_ni avx512bw avx512vl xsaveopt xsavec xgetbv1 xsaves split_lock_detect user_shstk avx_vnni avx512_bf16 dtherm ida arat pln pts hwp hwp_act_window hwp_epp hwp_pkg_req hfi vnni umip pku ospke waitpkg gfni vaes vpclmulqdq tme rdpid movdiri movdir64b fsrm serialize avx512_vnni pconfig arch_lbr ibt flush_l1d arch_capabilities
"""

CLX_CPUINFO = """processor       : 0
vendor_id       : GenuineIntel
cpu family      : 6
model           : 85
model name      : Intel(R) Xeon(R) Gold 6248R CPU @ 3.00GHz
stepping        : 7
microcode       : 0x500320a
cpu MHz         : 3000.000
cache size      : 28160 KB
physical id     : 0
siblings        : 8
cpu cores       : 8
core id         : 0
flags           : fpu vme de pse tsc msr pae mce cx8 apic sep mtrr pge mca cmov pat pse36 clflush dts acpi mmx fxsr sse sse2 ss ht tm pbe syscall nx pdpe1gb rdtscp lm constant_tsc art arch_perfmon pebs bts rep_good nopl xtopology nonstop_tsc cpuid aperfmperf pni pclmulqdq dtes64 monitor ds_cpl vmx smx est tm2 ssse3 sdbg fma cx16 xtpr pdcm pcid dca sse4_1 sse4_2 x2apic movbe popcnt tsc_deadline_timer aes xsave avx f16c rdrand lahf_lm abm 3dnowprefetch cpuid_fault epb cat_l3 cdp_l3 invpcid_single intel_ppin ssbd mba ibrs ibpb stibp fsgsbase tsc_adjust bmi1 avx2 smep bmi2 erms invpcid cqm rdt_a avx512f avx512dq rdseed adx smap avx512ifma clflushopt clwb intel_pt avx512cd sha_ni avx512bw avx512vl xsaveopt xsavec xgetbv1 xsaves split_lock_detect dtherm ida arat pln pts hwp hwp_act_window hwp_epp hwp_pkg_req vnni umip pku ospke waitpkg gfni vaes vpclmulqdq tme rdpid movdiri movdir64b fsrm serialize pconfig arch_lbr ibt flush_l1d arch_capabilities
"""

ZEN3_CPUINFO = """processor       : 0
vendor_id       : AuthenticAMD
cpu family      : 25
model           : 33
model name      : AMD Ryzen 9 5950X 16-Core Processor
stepping        : 0
microcode       : 0xa201016
cpu MHz         : 3591.000
cache size      : 512 KB
physical id     : 0
siblings        : 2
cpu cores       : 2
core id         : 0
apicid          : 0
initial apicid  : 0
fpu             : yes
fpu_exception   : yes
cpuid level     : 16
wp              : yes
flags           : fpu vme de pse tsc msr pae mce cx8 apic sep mtrr pge mca cmov pat pse36 clflush mmx fxsr sse sse2 ht syscall nx mmxext fxsr_opt pdpe1gb rdtscp lm constant_tsc rep_good nopl nonstop_tsc cpuid extd_apicid aperfmperf rapl pni pclmulqdq monitor ssse3 fma cx16 sse4_1 sse4_2 movbe popcnt aes xsave avx f16c rdrand lahf_lm cmp_legacy svm extapic cr8_legacy abm sse4a misalignsse 3dnowprefetch osvw ibs skinit wdt tce topoext perfctr_core perfctr_nb bpext perfctr_llc mwaitx cpb cat_l3 cdp_l3 hw_pstate ssbd mba ibrs ibpb stibp vmmcall fsgsbase bmi1 avx2 smep bmi2 erms invpcid cqm rdt_a rdseed adx smap clflushopt clwb ibt umip pku ospke vaes vpclmulqdq rdpid overflow_recov succor smca fsrm
"""

SINGLE_CPUINFO = """processor       : 0
vendor_id       : GenuineIntel
cpu family      : 6
model           : 158
model name      : Intel(R) Core(TM) i7-9750H CPU @ 2.60GHz
stepping        : 10
microcode       : 0xea
cpu MHz         : 2600.000
cache size      : 12288 KB
physical id     : 0
siblings        : 1
cpu cores       : 1
core id         : 0
flags           : fpu vme de pse tsc msr pae mce cx8 apic sep mtrr pge mca cmov pat pse36 clflush dts acpi mmx fxsr sse sse2 ss ht tm pbe syscall nx pdpe1gb rdtscp lm constant_tsc art arch_perfmon pebs bts rep_good nopl xtopology nonstop_tsc cpuid aperfmperf pni pclmulqdq dtes64 monitor ds_cpl vmx smx est tm2 ssse3 sdbg fma cx16 xtpr pdcm pcid sse4_1 sse4_2 x2apic movbe popcnt aes xsave avx f16c rdrand lahf_lm abm 3dnowprefetch cpuid_fault epb invpcid_single ssbd ibrs ibpb stibp ibrs_enhanced fsgsbase bmi1 avx2 smep bmi2 erms invpcid cqm rdt_a rdseed adx smap clflushopt clwb intel_pt sha_ni xsaveopt xsavec xgetbv1 xsaves split_lock_detect dtherm ida arat pln pts hwp hwp_notify hwp_act_window hwp_epp pku ospke waitpkg gfni vaes vpclmulqdq rdpid movdiri movdir64b fsrm serialize tsxldtrk arch_capabilities
"""

HETEROGENEOUS_CPUINFO = """processor       : 0
vendor_id       : GenuineIntel
cpu family      : 6
model           : 143
model name      : Intel(R) Xeon(R) Platinum 8480+
stepping        : 6
flags           : fpu avx avx2 avx512f avx512_vnni fma bmi1 bmi2

processor       : 1
vendor_id       : AuthenticAMD
cpu family      : 25
model           : 33
model name      : AMD EPYC 7763
stepping        : 1
flags           : fpu avx avx2 fma bmi1 bmi2
"""

# proc_pid_stat(5) field 10 (minflt) -> after[7], 12 (majflt) -> after[9],
# 14 (utime) -> after[13], 15 (stime) -> after[14], 20 (num_threads) -> after[19].
PROC_SELF_STAT_LINE = (
    "99999 (my comm) R 888 7 6 5 4 3 111 100 222 90 333 444 80 70 60 50 8 "
    "1 55 77 88 99 66 44\n"
)

CGROUP2_MOUNTINFO = (
    "35 33 0:30 / /sys/fs/cgroup rw,relatime - cgroup2 cgroup2 "
    "rw,seclabel,nsdelegate,memory_recursiveprot\n"
)

PSI_FILES = {
    "/proc/pressure/cpu": (
        "some avg10=0.05 avg60=0.02 avg300=0.01 total=1234\n"
        "full avg10=0.00 avg60=0.00 avg300=0.00 total=0\n"
    ),
    "/proc/pressure/memory": (
        "some avg10=1.23 avg60=0.50 avg300=0.20 total=5000000\n"
        "full avg10=0.10 avg60=0.05 avg300=0.01 total=10000\n"
    ),
    "/proc/pressure/io": (
        "some avg10=0.00 avg60=0.00 avg300=0.00 total=0\n"
        "full avg10=0.00 avg60=0.00 avg300=0.00 total=0\n"
    ),
}

NVIDIA_SMI_CSV_LINE = (
    "NVIDIA A100-SXM4-80GB,GPU-abc123def456ghi789jkl012mno345pqr,550.54.15,0,"
    "00000000:00:04.0,4,4,16,16,P0,1410,1593,225.5,85,70,81920 MiB"
)


# ---------------------------------------------------------------------------
# Test doubles / helpers
# ---------------------------------------------------------------------------

def _norm(path):
    return str(path).replace("\\", "/")


class _FakeFS:
    """Dict-backed fake filesystem backing builtins.open.

    Registered paths return a fresh ``io.StringIO`` per call; anything else
    raises ``FileNotFoundError`` (or always when ``fail_all=True``).
    """

    def __init__(self, files=None, fail_all=False):
        self.files = {_norm(k): v for k, v in (files or {}).items()}
        self.fail_all = fail_all
        self.opened_paths = []

    def open(self, path, mode="r", **kwargs):
        key = _norm(path)
        self.opened_paths.append(key)
        if self.fail_all or key not in self.files:
            raise FileNotFoundError(2, "No such file or directory", str(path))
        return io.StringIO(self.files[key])


class _FakeRusage:
    def __init__(self, majflt=0, minflt=0, utime=0.0, stime=0.0,
                 nvcsw=0, nivcsw=0, maxrss=0):
        self.ru_majflt = majflt
        self.ru_minflt = minflt
        self.ru_utime = utime
        self.ru_stime = stime
        self.ru_nvcsw = nvcsw
        self.ru_nivcsw = nivcsw
        self.ru_maxrss = maxrss


class _FakeTrace:
    def __init__(self):
        self.events = []  # (name, phase, metadata_dict)

    def emit(self, name, *, process=None, phase="", metadata=None):
        self.events.append((name, phase, dict(metadata or {})))


_UNAVAILABLE_GPU = {
    "gpu_source": "unavailable",
    "gpu_query_wall_ms": 0.0,
    "gpu_error": None,
    "gpu_pcie_error": None,
    "gpu_uuid_hash": None,
    "gpu_name": None,
    "gpu_driver_version": None,
    "gpu_index": None,
    "gpu_pci_bus": None,
    "gpu_pcie_gen_current": None,
    "gpu_pcie_gen_max": None,
    "gpu_pcie_width_current": None,
    "gpu_pcie_width_max": None,
    "gpu_pstate": None,
    "gpu_sm_clock_mhz": None,
    "gpu_mem_clock_mhz": None,
    "gpu_power_w": None,
    "gpu_util": None,
    "gpu_mem_util": None,
    "gpu_bar1_used_mib": None,
}

_ALLOWED_CONFIDENCE = {
    "multi_source_consistent", "proc_only", "virtualized_or_inconsistent", "unavailable",
}

_UNAVAILABLE_TORCH_GPU = {
    "gpu_name": None,
    "gpu_static_source": "unavailable",
    "torch_device_capability": None,
    "torch_total_memory_bytes": None,
    "torch_multi_processor_count": None,
}


def _raising_getrusage(who):
    raise RuntimeError("getrusage unavailable")


def _raising_subprocess(*args, **kwargs):
    raise FileNotFoundError(2, "No such file or directory", str(args[0] if args else ""))


def _patch_resource(monkeypatch, getrusage_fn):
    fake = types.ModuleType("resource")
    setattr(fake, "RUSAGE_SELF", 0)
    setattr(fake, "getrusage", getrusage_fn)
    monkeypatch.setitem(sys.modules, "resource", fake)


def _parse_any(text):
    """Call parse_cpuinfo with an untyped argument (robustness check)."""
    return hht.parse_cpuinfo(text)


def _patch_fast_fingerprint_collection(monkeypatch):
    """Make collect_host_fingerprint fast/deterministic on any host."""
    monkeypatch.setattr(hht, "_add_topology_env", lambda result: None)
    monkeypatch.setattr(
        hht, "try_direct_cpuid",
        lambda: {"cpuid_status": "unavailable", "cpuid_source": None,
                 "cpuid_vendor": None, "cpuid_brand": None, "cpuid_family": None,
                 "cpuid_model": None, "cpuid_stepping": None, "cpuid_flags": None},
    )
    monkeypatch.setattr(hht, "nvidia_gpu_snapshot", lambda: dict(_UNAVAILABLE_GPU))
    monkeypatch.setattr(hht, "_torch_gpu_identity", lambda: dict(_UNAVAILABLE_TORCH_GPU))


@pytest.fixture(autouse=True)
def _reset_module_state(monkeypatch):
    """Reset all module-level caches/guards before every test."""
    monkeypatch.setattr(hht, "_TRACE", None)
    monkeypatch.setattr(hht, "_fingerprint_emitted", False)
    monkeypatch.setattr(hht, "_LAST_SNAPSHOT", None)
    monkeypatch.setattr(hht, "_LAST_SNAPSHOT_WALL_MONO", None)
    monkeypatch.setattr(hht, "_GPU_CACHE", None)
    monkeypatch.setattr(hht, "_GPU_CACHE_AT", 0.0)
    monkeypatch.setattr(
        hht, "_CAP_CACHE",
        {"psi_done": False, "psi": None, "cgroup_done": False, "cgroup": None},
    )
    yield


# ---------------------------------------------------------------------------
# 1. cpuinfo parsing
# ---------------------------------------------------------------------------

def test_parse_cpuinfo_sapphire_rapids():
    parsed = hht.parse_cpuinfo(SPR_CPUINFO)
    assert parsed["vendor_id"] == "GenuineIntel"
    assert parsed["cpu_family"] == "6"
    assert parsed["cpu_model"] == "143"
    assert parsed["cpu_stepping"] == "6"
    assert parsed["cpu_mhz"] == 2700.0
    assert parsed["cpu_count_proc"] == 2
    assert parsed["cpu_entries_homogeneous"] is True
    assert parsed["cpu_flags"] is not None
    for feature in ("avx", "avx2", "avx512f", "avx512bw", "avx512vl",
                    "avx512dq", "avx512_vnni", "fma", "bmi1", "bmi2"):
        assert parsed[feature] is True, feature


def test_parse_cpuinfo_cascade_lake_no_vnni():
    parsed = hht.parse_cpuinfo(CLX_CPUINFO)
    assert parsed["vendor_id"] == "GenuineIntel"
    assert parsed["cpu_family"] == "6"
    assert parsed["cpu_model"] == "85"
    assert parsed["cpu_stepping"] == "7"
    assert parsed["cpu_count_proc"] == 1
    assert parsed["cpu_entries_homogeneous"] is True
    assert parsed["avx512f"] is True
    assert parsed["avx512bw"] is True
    assert parsed["avx512vl"] is True
    assert parsed["avx512dq"] is True
    assert parsed["avx512_vnni"] is False
    assert parsed["fma"] is True
    assert parsed["bmi1"] is True
    assert parsed["bmi2"] is True


def test_parse_cpuinfo_amd_zen3_no_avx512():
    parsed = hht.parse_cpuinfo(ZEN3_CPUINFO)
    assert parsed["vendor_id"] == "AuthenticAMD"
    assert parsed["cpu_family"] == "25"
    assert parsed["cpu_model"] == "33"
    assert parsed["cpu_stepping"] == "0"
    assert parsed["cpu_count_proc"] == 1
    assert parsed["cpu_entries_homogeneous"] is True
    assert parsed["avx2"] is True
    assert parsed["fma"] is True
    assert parsed["bmi1"] is True
    assert parsed["bmi2"] is True
    assert parsed["avx512f"] is False
    assert parsed["avx512_vnni"] is False


def test_parse_cpuinfo_heterogeneous_blocks():
    parsed = hht.parse_cpuinfo(HETEROGENEOUS_CPUINFO)
    assert parsed["cpu_count_proc"] == 2
    assert parsed["cpu_entries_homogeneous"] is False
    assert parsed["vendor_id"] == "GenuineIntel"


def test_parse_cpuinfo_single_processor():
    parsed = hht.parse_cpuinfo(SINGLE_CPUINFO)
    assert parsed["cpu_count_proc"] == 1
    assert parsed["cpu_entries_homogeneous"] is True
    assert parsed["vendor_id"] == "GenuineIntel"
    assert parsed["cpu_model"] == "158"


def test_parse_cpuinfo_empty_and_none():
    parsed = hht.parse_cpuinfo("")
    assert parsed["cpu_count_proc"] == 0
    assert parsed["cpu_entries_homogeneous"] is None
    assert "vendor_id" not in parsed
    assert "cpu_family" not in parsed
    assert "avx" not in parsed
    assert "cpu_flags" not in parsed

    parsed_non_str = _parse_any(None)
    assert parsed_non_str["cpu_count_proc"] == 0
    assert parsed_non_str["cpu_entries_homogeneous"] is None


# ---------------------------------------------------------------------------
# 3. fingerprint hash
# ---------------------------------------------------------------------------

def test_fingerprint_hash_stability_and_format():
    h1 = hht.cpuinfo_fingerprint_hash(hht.parse_cpuinfo(SPR_CPUINFO))
    h2 = hht.cpuinfo_fingerprint_hash(hht.parse_cpuinfo(SPR_CPUINFO))
    assert h1 == h2
    assert re.fullmatch(r"[0-9a-f]{64}", h1)

    # cpu MHz and model name must NOT change the identity hash.
    changed_mhz = SPR_CPUINFO.replace("2700.000", "3400.000")
    changed_name = SPR_CPUINFO.replace("Intel(R) Xeon(R) Platinum 8480+", "Opaque Brand String")
    assert hht.cpuinfo_fingerprint_hash(hht.parse_cpuinfo(changed_mhz)) == h1
    assert hht.cpuinfo_fingerprint_hash(hht.parse_cpuinfo(changed_name)) == h1

    # stepping and flags MUST change the identity hash.
    changed_stepping = SPR_CPUINFO.replace("stepping        : 6", "stepping        : 7")
    changed_flags = SPR_CPUINFO.replace("avx512dq", "avx512dq_extraflag")
    assert hht.cpuinfo_fingerprint_hash(hht.parse_cpuinfo(changed_stepping)) != h1
    assert hht.cpuinfo_fingerprint_hash(hht.parse_cpuinfo(changed_flags)) != h1


def test_fingerprint_hash_partial_dict_never_raises():
    for partial in (
        {},
        {"vendor_id": "GenuineIntel"},
        {"cpu_flags": "avx fma bmi1"},
        {"cpu_mhz": 2700.0, "cpu_model_name": "ignored"},
        {"vendor_id": "GenuineIntel", "cpu_family": "6", "cpu_model": "143",
         "cpu_stepping": "6", "cpu_microcode": "0xdead", "cpu_flags": "avx2"},
    ):
        digest = hht.cpuinfo_fingerprint_hash(partial)
        assert re.fullmatch(r"[0-9a-f]{64}", digest)


# ---------------------------------------------------------------------------
# 4. lscpu
# ---------------------------------------------------------------------------

def test_read_lscpu_unavailable(monkeypatch):
    monkeypatch.setattr(hht.subprocess, "run", _raising_subprocess)
    result = hht.read_lscpu()
    assert result["lscpu_status"] == "unavailable"
    assert "lscpu_reason" in result
    assert result["lscpu_reason"] == "FileNotFoundError"


def test_read_lscpu_parses_json(monkeypatch):
    payload = {"lscpu": [
        {"field": "Architecture", "data": "x86_64"},
        {"field": "CPU(s)", "data": 8},
        {"field": "On-line CPU(s) list", "data": "0-7"},
        {"field": "Vendor ID", "data": "GenuineIntel"},
        {"field": "Model name", "data": "Intel(R) Xeon(R) Platinum 8480+ @ 2.70GHz"},
        {"field": "CPU family", "data": 6},
        {"field": "Model", "data": 143},
        {"field": "Thread(s) per core", "data": 1},
        {"field": "Core(s) per socket", "data": 8},
        {"field": "Socket(s)", "data": 1},
        {"field": "NUMA node(s)", "data": 2},
        {"field": "NUMA node0 CPU(s)", "data": "0-3"},
        {"field": "Hypervisor vendor", "data": "KVM"},
        {"field": "Flags", "data": "fpu vme avx avx2 avx512f"},
    ]}
    fake_proc = SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")

    def fake_run(cmd, *args, **kwargs):
        assert cmd == ["lscpu", "-J"]
        return fake_proc

    monkeypatch.setattr(hht.subprocess, "run", fake_run)
    result = hht.read_lscpu()
    assert result["lscpu_status"] == "available"
    assert result["architecture"] == "x86_64"
    assert result["cpu_count"] == 8
    assert result["vendor_id"] == "GenuineIntel"
    assert result["model_name"].startswith("Intel(R)")
    assert result["cpu_family"] == 6
    assert result["cpu_model"] == 143
    assert result["numa_nodes"] == 2
    assert result["numa_node0_cpus"] == "0-3"
    assert result["hypervisor_vendor"] == "KVM"
    assert result["flags"] == "fpu vme avx avx2 avx512f"


# ---------------------------------------------------------------------------
# 5. PSI
# ---------------------------------------------------------------------------

def test_read_psi_absent_no_fake_zeros(monkeypatch):
    fs = _FakeFS(files={}, fail_all=True)
    monkeypatch.setattr("builtins.open", fs.open)
    # Force the /proc/pressure tree to be absent so the existence gate
    # short-circuits before any file open.
    monkeypatch.setattr(
        hht.os.path, "exists",
        lambda path: False if path == "/proc/pressure" else os.path.exists(path),
    )
    result = hht.read_psi()
    assert result["psi_status"] == "unavailable"
    for source in ("cpu", "memory", "io"):
        assert result[f"{source}_psi_status"] == "unavailable"
        assert f"{source}_psi_some_avg10" not in result
        assert f"{source}_psi_some_total" not in result
        assert result.get(f"{source}_psi_some_avg10") is None
    assert result["psi_looks_synthetic"] is False
    # One stat gate replaced the three ENOENT opens.
    assert not any("pressure" in p for p in fs.opened_paths)


def test_read_psi_parses_values(monkeypatch):
    fs = _FakeFS(files=PSI_FILES)
    monkeypatch.setattr("builtins.open", fs.open)
    # Make the /proc/pressure tree "exist" so the gate lets the opens through.
    monkeypatch.setattr(
        hht.os.path, "exists",
        lambda path: True if path == "/proc/pressure" else os.path.exists(path),
    )
    result = hht.read_psi()
    assert result["psi_status"] == "available"
    assert result["cpu_psi_some_avg10"] == 0.05
    assert result["cpu_psi_some_avg60"] == 0.02
    assert result["cpu_psi_some_avg300"] == 0.01
    assert result["cpu_psi_some_total"] == 1234
    assert result["cpu_psi_full_total"] == 0
    assert result["memory_psi_some_avg10"] == 1.23
    assert result["memory_psi_some_total"] == 5000000
    assert result["memory_psi_full_avg10"] == 0.10
    assert result["io_psi_some_total"] == 0
    # Static fixture: both reads 200ms apart return identical totals.
    assert result["psi_looks_synthetic"] is True


# ---------------------------------------------------------------------------
# 6. cgroup discovery
# ---------------------------------------------------------------------------

def test_read_cgroup_fields_v2(monkeypatch):
    files = {
        "/proc/self/cgroup": "0::/session-123/container-456\n",
        "/proc/self/mountinfo": CGROUP2_MOUNTINFO,
        "/sys/fs/cgroup/session-123/container-456/cpu.stat": (
            "usage_usec 123456\nuser_usec 100000\nsystem_usec 23456\n"
            "nr_periods 100\nnr_throttled 3\nthrottled_usec 5000\n"
        ),
        "/sys/fs/cgroup/session-123/container-456/memory.current": "1073741824\n",
        "/sys/fs/cgroup/session-123/container-456/memory.events": (
            "low 0\nhigh 0\nmax 0\noom 0\noom_kill 0\n"
        ),
        "/sys/fs/cgroup/session-123/container-456/memory.stat": (
            "anon 536870912\nfile 268435456\nkernel_stack 8192\nslab 1000000\n"
            "pgfault 12345\npgmajfault 6\n"
        ),
        "/sys/fs/cgroup/session-123/container-456/io.stat": (
            "253:0 rbytes=1048576 wbytes=2097152 rios=5 wios=3\n"
        ),
    }
    fs = _FakeFS(files=files)
    monkeypatch.setattr("builtins.open", fs.open)
    result = hht.read_cgroup_fields()
    assert result["cgroup_source"] == "v2"
    assert result["cgroup_likely_virtualized"] is True
    assert isinstance(result["cgroup_virtualization_reason"], str)
    assert "gVisor" in result["cgroup_virtualization_reason"]
    assert result["cgroup_cpu_usage_usec"] == 123456
    assert result["cgroup_cpu_user_usec"] == 100000
    assert result["cgroup_cpu_system_usec"] == 23456
    assert result["cgroup_cpu_nr_periods"] == 100
    assert result["cgroup_cpu_nr_throttled"] == 3
    assert result["cgroup_cpu_throttled_usec"] == 5000
    assert result["cgroup_memory_current"] == 1073741824
    assert result["cgroup_memory_events_low"] == 0
    assert result["cgroup_memory_events_oom_kill"] == 0
    assert result["cgroup_memory_anon"] == 536870912
    assert result["cgroup_memory_pgfault"] == 12345
    assert result["cgroup_memory_pgmajfault"] == 6
    assert result["cgroup_io_stat_snippet"].startswith("253:0")


def test_read_cgroup_fields_v1(monkeypatch):
    # Sentry-virtualized v1-style /proc/self/cgroup (Modal task-ID paths).
    files = {
        "/proc/self/cgroup": (
            "4:cpu,cpuacct:/ta-abcd1234/container-xyz\n"
            "3:memory:/ta-abcd1234/container-xyz\n"
            "2:blkio:/ta-abcd1234/container-xyz\n"
        ),
    }
    fs = _FakeFS(files=files)
    monkeypatch.setattr("builtins.open", fs.open)
    result = hht.read_cgroup_fields()
    assert result["cgroup_source"] == "v1"
    assert result["cgroup_likely_virtualized"] is True
    assert isinstance(result["cgroup_virtualization_reason"], str)
    assert "gVisor" in result["cgroup_virtualization_reason"]
    assert result["cgroup_lines_snippet"]
    # v1 detection uses /proc/self/cgroup ALONE: mountinfo and per-controller
    # files are never opened on the healthy path.
    opened = fs.opened_paths
    assert "/proc/self/cgroup" in opened
    assert not any("mountinfo" in p for p in opened)
    assert not any("cpuacct.usage" in p for p in opened)
    assert not any("memory.usage_in_bytes" in p for p in opened)
    assert not any("oom_control" in p for p in opened)


def test_read_cgroup_fields_unavailable(monkeypatch):
    files = {
        "/proc/self/mountinfo": "12 1 0:5 / / rw,relatime - overlay overlay rw\n",
        "/proc/self/cgroup": "0::/\n",
    }
    fs = _FakeFS(files=files)
    monkeypatch.setattr("builtins.open", fs.open)
    result = hht.read_cgroup_fields()
    assert result["cgroup_source"] == "unavailable"
    assert result["cgroup_likely_virtualized"] is True
    assert result.get("cgroup_cpu_usage_usec") is None


# ---------------------------------------------------------------------------
# 7. GPU / PCIe
# ---------------------------------------------------------------------------

def test_nvidia_gpu_snapshot_unavailable(monkeypatch):
    monkeypatch.setattr(hht.subprocess, "run", _raising_subprocess)
    result = hht.nvidia_gpu_snapshot()
    assert result["gpu_source"] == "unavailable"
    assert result["gpu_uuid_hash"] is None
    assert result["gpu_name"] is None
    assert result["gpu_power_w"] is None
    assert result["gpu_pcie_gen_current"] is None
    assert result["gpu_query_wall_ms"] >= 0
    # FileNotFoundError -> descriptive gpu_error, not None.
    assert isinstance(result["gpu_error"], str)
    assert "not found" in result["gpu_error"]


def test_nvidia_gpu_snapshot_smi_csv(monkeypatch):
    fake_proc = SimpleNamespace(returncode=0, stdout=NVIDIA_SMI_CSV_LINE, stderr="")

    def fake_run(cmd, *args, **kwargs):
        assert cmd[0] == "nvidia-smi"
        return fake_proc

    monkeypatch.setattr(hht.subprocess, "run", fake_run)
    result = hht.nvidia_gpu_snapshot()
    assert result["gpu_source"] == "nvidia_smi"
    assert result["gpu_name"] == "NVIDIA A100-SXM4-80GB"
    assert result["gpu_driver_version"] == "550.54.15"
    assert result["gpu_index"] == 0
    assert result["gpu_pci_bus"] == "00000000:00:04.0"
    assert result["gpu_pcie_gen_current"] == 4.0
    assert result["gpu_pcie_gen_max"] == 4.0
    assert result["gpu_pcie_width_current"] == 16.0
    assert result["gpu_pcie_width_max"] == 16.0
    assert result["gpu_pstate"] == "P0"
    assert result["gpu_sm_clock_mhz"] == 1410.0
    assert result["gpu_mem_clock_mhz"] == 1593.0
    assert result["gpu_power_w"] == 225.5
    assert result["gpu_util"] == 85
    assert result["gpu_mem_util"] == 70
    assert result["gpu_bar1_used_mib"] == 81920.0
    # UUID is only ever stored hashed (sha256 prefix, 16 hex chars).
    assert re.fullmatch(r"[0-9a-f]{16}", result["gpu_uuid_hash"])
    assert "GPU-abc123def456ghi789jkl012mno345pqr" not in str(result)
    # Full query succeeded on the first level -> no error recorded.
    assert result["gpu_error"] is None


def test_nvidia_gpu_snapshot_fallback_chain(monkeypatch):
    """FULL query fails (nvproxy-rejected field) -> CORE succeeds, error kept.

    The CORE level carries no PCIe data, so the standalone PCIe probe runs and
    also fails (rc=2), leaving the pcie fields None with ``gpu_pcie_error``.
    """
    spawns = {"count": 0}

    def fake_run(cmd, *args, **kwargs):
        spawns["count"] += 1
        query = cmd[1]
        if "memory.bar1.used" in query:
            return SimpleNamespace(
                returncode=1, stdout="", stderr="Failed to query memory.bar1.used\n"
            )
        if hht._SMI_QUERY_PCIE in query:
            return SimpleNamespace(
                returncode=2, stdout="", stderr="Failed to query pcie.link.gen.current\n"
            )
        # CORE-level row: name,uuid,driver_version,pci.bus_id,pstate,clocks.sm,
        # clocks.mem,power.draw,utilization.gpu,utilization.memory
        return SimpleNamespace(
            returncode=0,
            stdout=(
                "NVIDIA RTX PRO 6000,GPU-rtxpro6000abcdef0123456789abcdef,"
                "550.54.15,00000000:00:03.0,P0,1410,1593,225.5,85,70\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(hht.subprocess, "run", fake_run)
    result = hht.nvidia_gpu_snapshot()
    assert spawns["count"] == 3  # full (failed) + core (succeeded) + pcie (failed)
    assert result["gpu_source"] == "nvidia_smi"
    assert result["gpu_name"] == "NVIDIA RTX PRO 6000"
    assert re.fullmatch(r"[0-9a-f]{16}", result["gpu_uuid_hash"])
    assert result["gpu_driver_version"] == "550.54.15"
    assert result["gpu_pci_bus"] == "00000000:00:03.0"
    assert result["gpu_pstate"] == "P0"
    assert result["gpu_sm_clock_mhz"] == 1410.0
    assert result["gpu_mem_clock_mhz"] == 1593.0
    assert result["gpu_power_w"] == 225.5
    assert result["gpu_util"] == 85
    assert result["gpu_mem_util"] == 70
    # Fields that only exist on the FULL level stay None.
    assert result["gpu_bar1_used_mib"] is None
    assert result["gpu_pcie_gen_max"] is None
    assert result["gpu_pcie_gen_current"] is None
    assert result["gpu_pcie_width_current"] is None
    assert result["gpu_pcie_width_max"] is None
    # The failed level's stderr is surfaced for diagnostics.
    assert isinstance(result["gpu_error"], str)
    assert "Failed to query memory.bar1.used" in result["gpu_error"]
    # The failed standalone PCIe probe's stderr is surfaced too.
    assert isinstance(result["gpu_pcie_error"], str)
    assert "Failed to query pcie.link.gen.current" in result["gpu_pcie_error"]


def test_nvidia_gpu_snapshot_pcie_probe_success(monkeypatch):
    """CORE succeeds (no PCIe data) -> standalone PCIe probe fills the fields."""
    spawns = {"count": 0}

    def fake_run(cmd, *args, **kwargs):
        spawns["count"] += 1
        query = cmd[1]
        if "memory.bar1.used" in query:
            return SimpleNamespace(
                returncode=1, stdout="", stderr="Failed to query memory.bar1.used\n"
            )
        if hht._SMI_QUERY_PCIE in query:
            return SimpleNamespace(returncode=0, stdout="5,5,16,16\n", stderr="")
        return SimpleNamespace(
            returncode=0,
            stdout=(
                "NVIDIA RTX PRO 6000,GPU-rtxpro6000abcdef0123456789abcdef,"
                "550.54.15,00000000:00:03.0,P0,1410,1593,225.5,85,70\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(hht.subprocess, "run", fake_run)
    result = hht.nvidia_gpu_snapshot()
    assert spawns["count"] == 3  # full (failed) + core + pcie probe
    assert result["gpu_source"] == "nvidia_smi"
    assert result["gpu_name"] == "NVIDIA RTX PRO 6000"
    assert result["gpu_pstate"] == "P0"
    # PCIe fields populated by the standalone probe.
    assert result["gpu_pcie_gen_current"] == 5.0
    assert result["gpu_pcie_gen_max"] == 5.0
    assert result["gpu_pcie_width_current"] == 16.0
    assert result["gpu_pcie_width_max"] == 16.0
    assert result["gpu_pcie_error"] is None
    # The FULL-only bar1 field is still None (never parsed).
    assert result["gpu_bar1_used_mib"] is None
    # Prior level error (rejected bar1 field) still carried in gpu_error.
    assert isinstance(result["gpu_error"], str)
    assert "Failed to query memory.bar1.used" in result["gpu_error"]


def test_nvidia_gpu_snapshot_pcie_unknown_error_tolerated(monkeypatch):
    """PCIe probe row of '[Unknown Error]' tokens -> None fields, no crash."""
    spawns = {"count": 0}

    def fake_run(cmd, *args, **kwargs):
        spawns["count"] += 1
        query = cmd[1]
        if "memory.bar1.used" in query:
            return SimpleNamespace(
                returncode=1, stdout="", stderr="Failed to query memory.bar1.used\n"
            )
        if hht._SMI_QUERY_PCIE in query:
            return SimpleNamespace(
                returncode=0,
                stdout="[Unknown Error],[Unknown Error],[Unknown Error],[Unknown Error]\n",
                stderr="",
            )
        return SimpleNamespace(
            returncode=0,
            stdout=(
                "NVIDIA RTX PRO 6000,GPU-rtxpro6000abcdef0123456789abcdef,"
                "550.54.15,00000000:00:03.0,P0,1410,1593,225.5,85,70\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(hht.subprocess, "run", fake_run)
    result = hht.nvidia_gpu_snapshot()
    assert result["gpu_source"] == "nvidia_smi"
    assert result["gpu_name"] == "NVIDIA RTX PRO 6000"
    # No bogus numbers, no crash.
    assert result["gpu_pcie_gen_current"] is None
    assert result["gpu_pcie_gen_max"] is None
    assert result["gpu_pcie_width_current"] is None
    assert result["gpu_pcie_width_max"] is None
    # The probe row existed but yielded nothing usable -> flagged.
    assert isinstance(result["gpu_pcie_error"], str)
    assert result["gpu_pcie_error"] == "pcie fields unavailable"


def test_nvidia_gpu_snapshot_full_success_skips_pcie_probe(monkeypatch):
    """When FULL already carries PCIe data the standalone probe must NOT run."""
    spawns = {"count": 0}

    def fake_run(cmd, *args, **kwargs):
        spawns["count"] += 1
        return SimpleNamespace(returncode=0, stdout=NVIDIA_SMI_CSV_LINE, stderr="")

    monkeypatch.setattr(hht.subprocess, "run", fake_run)
    result = hht.nvidia_gpu_snapshot()
    assert spawns["count"] == 1  # full success -> no pcie probe
    assert result["gpu_pcie_gen_current"] == 4.0
    assert result["gpu_pcie_gen_max"] == 4.0
    assert result["gpu_pcie_width_current"] == 16.0
    assert result["gpu_pcie_width_max"] == 16.0
    assert result["gpu_pcie_error"] is None


def test_nvidia_smi_number_parser_unknown_error_tolerance():
    assert hht._parse_nvidia_number("[Unknown Error]") is None
    assert hht._parse_nvidia_number("5") == 5.0
    assert hht._parse_nvidia_number("[Unknown Error] 4") is None
    assert hht._parse_nvidia_number("N/A") is None


def test_nvidia_gpu_snapshot_failure_cached_5s(monkeypatch):
    """Failures are cached 5s; a later phase snapshot retries the probe."""
    spawns = {"count": 0}

    def fake_run(*args, **kwargs):
        spawns["count"] += 1
        raise FileNotFoundError(2, "no nvidia-smi")

    monkeypatch.setattr(hht.subprocess, "run", fake_run)
    clock = {"t": 0.0}
    monkeypatch.setattr(hht.time, "monotonic", lambda: clock["t"])

    first = hht.nvidia_gpu_snapshot()
    assert first["gpu_source"] == "unavailable"
    assert first["gpu_error"] == "nvidia-smi not found"
    assert spawns["count"] == 1

    # Immediate second call reuses the cached failure (no new spawn).
    second = hht.nvidia_gpu_snapshot()
    assert second["gpu_source"] == "unavailable"
    assert spawns["count"] == 1

    # After the 5s failure TTL elapses the probe runs again.
    clock["t"] = 5.5
    third = hht.nvidia_gpu_snapshot()
    assert third["gpu_source"] == "unavailable"
    assert spawns["count"] == 2


# ---------------------------------------------------------------------------
# 8. no fake zeros
# ---------------------------------------------------------------------------

def test_rusage_snapshot_unavailable_no_zeros(monkeypatch):
    _patch_resource(monkeypatch, getrusage_fn=_raising_getrusage)
    result = hht.rusage_snapshot()
    assert result["rusage_status"] == "unavailable"
    for key in ("ru_utime", "ru_stime", "ru_minflt", "ru_majflt",
                "ru_nvcsw", "ru_nivcsw", "ru_maxrss"):
        assert result[key] is None, key
        assert result[key] != 0, key


def test_read_proc_self_stat_unavailable(monkeypatch):
    fs = _FakeFS(files={}, fail_all=True)
    monkeypatch.setattr("builtins.open", fs.open)
    result = hht.read_proc_self_stat()
    assert result["status"] == "unavailable"
    for key in ("pid", "comm", "state", "ppid", "minflt", "majflt",
                "utime_ticks", "stime_ticks", "num_threads"):
        assert result[key] is None, key
    assert result["ticks_per_sec"] is not None


def test_read_proc_self_stat_parses_fields(monkeypatch):
    fs = _FakeFS(files={"/proc/self/stat": PROC_SELF_STAT_LINE})
    monkeypatch.setattr("builtins.open", fs.open)
    result = hht.read_proc_self_stat()
    assert result["status"] == "available"
    assert result["pid"] == 99999
    assert result["comm"] == "my comm"
    assert result["state"] == "R"
    assert result["ppid"] == 888
    assert result["minflt"] == 111
    assert result["majflt"] == 222
    assert result["utime_ticks"] == 333
    assert result["stime_ticks"] == 444
    assert result["num_threads"] == 8


# ---------------------------------------------------------------------------
# 9. failure non-fatal + overhead bounded
# ---------------------------------------------------------------------------

def test_collect_host_fingerprint_all_fail_bounded(monkeypatch):
    monkeypatch.setattr(hht.subprocess, "run", _raising_subprocess)
    fs = _FakeFS(files={}, fail_all=True)
    monkeypatch.setattr("builtins.open", fs.open)
    _patch_resource(monkeypatch, getrusage_fn=_raising_getrusage)
    _patch_fast_fingerprint_collection(monkeypatch)

    result = hht.collect_host_fingerprint()
    assert isinstance(result, dict)
    assert "probe_statuses" in result and ";" in result["probe_statuses"]
    assert result["probe_wall_ms"] >= 0
    assert result["cpu_identity_confidence"] in _ALLOWED_CONFIDENCE
    assert result["cpu_identity_confidence"] == "unavailable"
    # Tier A defers the lscpu subprocess unless diagnostics are enabled.
    assert result["lscpu_status"] == "deferred"
    assert result["gpu_static_source"] == "unavailable"
    assert result["probe_wall_ms"] < 5.0


# ---------------------------------------------------------------------------
# 10. diagnostics do not alter execution / once-per-container guard
# ---------------------------------------------------------------------------

def test_emit_host_fingerprint_once_and_flat_metadata(monkeypatch):
    monkeypatch.setattr(hht.subprocess, "run", _raising_subprocess)
    fs = _FakeFS(files={}, fail_all=True)
    monkeypatch.setattr("builtins.open", fs.open)
    _patch_resource(monkeypatch, getrusage_fn=_raising_getrusage)
    _patch_fast_fingerprint_collection(monkeypatch)

    trace = _FakeTrace()
    hht.emit_host_fingerprint(trace)
    hht.emit_host_fingerprint(trace)

    names = [event[0] for event in trace.events]
    assert names.count("host_hardware_fingerprint") == 1

    name, phase, metadata = trace.events[0]
    assert name == "host_hardware_fingerprint"
    assert phase == "host"
    assert "probe_statuses" in metadata
    for key, value in metadata.items():
        assert isinstance(value, (str, int, float, bool, type(None))), key


def test_capture_resource_snapshot_emits_flat_metadata(monkeypatch):
    monkeypatch.setattr(hht.subprocess, "run", _raising_subprocess)
    fs = _FakeFS(files={}, fail_all=True)
    monkeypatch.setattr("builtins.open", fs.open)
    _patch_resource(monkeypatch, getrusage_fn=_raising_getrusage)
    monkeypatch.setattr(hht, "nvidia_gpu_snapshot", lambda: dict(_UNAVAILABLE_GPU))

    trace = _FakeTrace()
    snap = hht.capture_resource_snapshot("post_restore", trace)
    assert snap["phase"] == "post_restore"
    assert len(trace.events) == 1
    name, phase, metadata = trace.events[0]
    assert name == "host_resource_snapshot"
    assert phase == "post_restore"
    assert metadata["phase"] == "post_restore"
    for key, value in metadata.items():
        assert isinstance(value, (str, int, float, bool, type(None))), key


def test_capture_resource_snapshot_no_trace_no_raise(monkeypatch):
    monkeypatch.setattr(hht.subprocess, "run", _raising_subprocess)
    fs = _FakeFS(files={}, fail_all=True)
    monkeypatch.setattr("builtins.open", fs.open)
    _patch_resource(monkeypatch, getrusage_fn=_raising_getrusage)
    monkeypatch.setattr(hht, "nvidia_gpu_snapshot", lambda: dict(_UNAVAILABLE_GPU))

    snap = hht.capture_resource_snapshot("sampling_start", None)
    assert isinstance(snap, dict)
    assert snap["phase"] == "sampling_start"
    assert snap["probe_wall_ms"] >= 0


def test_snapshot_deltas_positive_between_calls(monkeypatch):
    monkeypatch.setattr(hht.subprocess, "run", _raising_subprocess)
    fs = _FakeFS(files={}, fail_all=True)
    monkeypatch.setattr("builtins.open", fs.open)
    monkeypatch.setattr(hht, "nvidia_gpu_snapshot", lambda: dict(_UNAVAILABLE_GPU))

    pf_counters = {"minflt": 1000, "majflt": 10}
    ru_counters = {"nvcsw": 100, "nivcsw": 20}

    def fake_proc_stat():
        pf_counters["minflt"] += 100
        pf_counters["majflt"] += 2
        return {
            "status": "available", "pid": 1, "comm": "py", "state": "R", "ppid": 0,
            "minflt": pf_counters["minflt"], "majflt": pf_counters["majflt"],
            "utime_ticks": 100, "stime_ticks": 50, "num_threads": 8,
            "ticks_per_sec": 100.0,
        }

    def fake_rusage():
        ru_counters["nvcsw"] += 5
        ru_counters["nivcsw"] += 1
        return {
            "rusage_status": "available", "ru_utime": 0.1, "ru_stime": 0.2,
            "ru_minflt": pf_counters["minflt"], "ru_majflt": pf_counters["majflt"],
            "ru_nvcsw": ru_counters["nvcsw"], "ru_nivcsw": ru_counters["nivcsw"],
            "ru_maxrss": 4096,
        }

    monkeypatch.setattr(hht, "read_proc_self_stat", fake_proc_stat)
    monkeypatch.setattr(hht, "rusage_snapshot", fake_rusage)

    first = hht.capture_resource_snapshot("pre_h2d")
    assert first["delta_minflt"] is None
    assert first["delta_majflt"] is None
    assert first["delta_nvcsw"] is None
    assert first["delta_nivcsw"] is None
    assert first["delta_utime_ms"] is None
    assert first["delta_stime_ms"] is None
    assert first["delta_wall_ms"] is None

    second = hht.capture_resource_snapshot("post_h2d")
    assert second["delta_minflt"] == 100
    assert second["delta_majflt"] == 2
    assert second["delta_nvcsw"] == 5
    assert second["delta_nivcsw"] == 1
    assert second["delta_utime_ms"] == 0.0
    assert second["delta_stime_ms"] == 0.0
    assert isinstance(second["delta_wall_ms"], (int, float))
    assert second["delta_wall_ms"] >= 0


# ---------------------------------------------------------------------------
# 11. integration with the fixed model_preload fault code
# ---------------------------------------------------------------------------

def test_model_preload_pagefault_unavailable_no_zeros(monkeypatch):
    _patch_resource(monkeypatch, getrusage_fn=_raising_getrusage)
    fs = _FakeFS(files={}, fail_all=True)
    monkeypatch.setattr("builtins.open", fs.open)

    before = _PageFaultSnapshot.now()
    after = _PageFaultSnapshot.now()
    assert before.unavailable is True
    assert after.unavailable is True
    delta = _pagefault_delta(before, after)
    assert delta == {"major_faults": None, "minor_faults": None}


def test_model_preload_pagefault_delta_positive(monkeypatch):
    counters = {"major": 0, "minor": 0}

    def fake_getrusage(who):
        counters["major"] += 3
        counters["minor"] += 40
        return _FakeRusage(majflt=counters["major"], minflt=counters["minor"])

    _patch_resource(monkeypatch, getrusage_fn=fake_getrusage)

    before = _PageFaultSnapshot.now()
    after = _PageFaultSnapshot.now()
    assert before.unavailable is False
    delta = _pagefault_delta(before, after)
    assert delta["major_faults"] == 3
    assert delta["minor_faults"] == 40


# ---------------------------------------------------------------------------
# 12. two-tier: classify_h2d / should_trigger_slow_probe
# ---------------------------------------------------------------------------

def test_classify_h2d_copy_interval_slow():
    record = {"h2d_cuda_elapsed_ms": 9000.0, "h2d_enqueue_host_ms": 8990.0,
              "h2d_sync_wait_host_ms": 10.0}
    assert hht.classify_h2d(record) == "COPY_INTERVAL_SLOW"


def test_classify_h2d_trailing_sync_stall():
    record = {"h2d_cuda_elapsed_ms": 1000.0, "h2d_enqueue_host_ms": 1000.0,
              "h2d_sync_wait_host_ms": 8000.0}
    assert hht.classify_h2d(record) == "TRAILING_SYNC_STALL"


def test_classify_h2d_host_overhead_around_copy():
    record = {"h2d_cuda_elapsed_ms": 1000.0, "h2d_enqueue_host_ms": 3000.0,
              "h2d_sync_wait_host_ms": 5.0}
    assert hht.classify_h2d(record) == "HOST_OVERHEAD_AROUND_COPY"


def test_classify_h2d_missing_or_nonpositive():
    assert hht.classify_h2d({}) == "UNKNOWN/MIXED"
    assert hht.classify_h2d({"h2d_cuda_elapsed_ms": 1000.0}) == "UNKNOWN/MIXED"
    assert hht.classify_h2d({"h2d_cuda_elapsed_ms": 0.0, "h2d_enqueue_host_ms": 100.0,
                             "h2d_sync_wait_host_ms": 10.0}) == "UNKNOWN/MIXED"
    assert hht.classify_h2d({"h2d_cuda_elapsed_ms": "1000", "h2d_enqueue_host_ms": 900.0,
                             "h2d_sync_wait_host_ms": 5.0}) == "UNKNOWN/MIXED"


def test_classify_h2d_healthy_copy_is_interval_slow():
    record = {"h2d_cuda_elapsed_ms": 2983.0, "h2d_enqueue_host_ms": 2982.0,
              "h2d_sync_wait_host_ms": 1.2}
    assert hht.classify_h2d(record) == "COPY_INTERVAL_SLOW"


def test_classify_h2d_zero_sync_wait_is_interval_slow():
    # Real container data: sync_wait rounded to 0.0 (sub-ms) must NOT be
    # treated as missing/unmeasurable -- it means no trailing stall.
    record = {"h2d_cuda_elapsed_ms": 2821.225, "h2d_enqueue_host_ms": 2821.286,
              "h2d_sync_wait_host_ms": 0.0}
    assert hht.classify_h2d(record) == "COPY_INTERVAL_SLOW"


def test_should_trigger_slow_probe_thresholds(monkeypatch):
    monkeypatch.delenv("COMFYMODAL_V2_SLOW_H2D_THRESHOLD_MS", raising=False)
    monkeypatch.delenv("COMFYMODAL_V2_HOST_DIAGNOSTICS", raising=False)
    assert hht.should_trigger_slow_probe(2500.0) is False
    assert hht.should_trigger_slow_probe(4100.0) is True
    assert hht.should_trigger_slow_probe(9200.0) is True
    assert hht.should_trigger_slow_probe(4000.0) is True  # >= threshold


def test_should_trigger_slow_probe_env_threshold(monkeypatch):
    monkeypatch.setenv("COMFYMODAL_V2_SLOW_H2D_THRESHOLD_MS", "5000")
    monkeypatch.delenv("COMFYMODAL_V2_HOST_DIAGNOSTICS", raising=False)
    assert hht.should_trigger_slow_probe(4100.0) is False
    assert hht.should_trigger_slow_probe(5200.0) is True


def test_should_trigger_slow_probe_diag_flag(monkeypatch):
    monkeypatch.delenv("COMFYMODAL_V2_SLOW_H2D_THRESHOLD_MS", raising=False)
    monkeypatch.setenv("COMFYMODAL_V2_HOST_DIAGNOSTICS", "1")
    assert hht.should_trigger_slow_probe(2500.0) is True


# ---------------------------------------------------------------------------
# 13. two-tier: emit_slow_h2d_forensics (Tier B)
# ---------------------------------------------------------------------------

def _force_smi_path(monkeypatch):
    """Make nvidia_gpu_snapshot take the nvidia-smi path (never real NVML)."""
    nvml_out = dict(_UNAVAILABLE_GPU)
    nvml_out["gpu_error"] = "nvml unavailable (pynvml import failed)"
    monkeypatch.setattr(hht, "_nvml_query", lambda: nvml_out)


def test_emit_slow_h2d_forensics_success(monkeypatch):
    record = {
        "h2d_to_wall_ms": 5234.5, "h2d_cuda_elapsed_ms": 1000.0,
        "h2d_enqueue_host_ms": 3000.0, "h2d_sync_wait_host_ms": 5.0,
        "h2d_copy_count": 12, "h2d_total_bytes": 104857600,
    }
    spawns = {"count": 0}

    def fake_run(cmd, *args, **kwargs):
        spawns["count"] += 1
        if cmd[0] == "lscpu":
            payload = {"lscpu": [
                {"field": "Architecture", "data": "x86_64"},
                {"field": "CPU(s)", "data": 8},
                {"field": "Vendor ID", "data": "GenuineIntel"},
                {"field": "Model name", "data": "Intel(R) Xeon(R) Platinum 8480+ @ 2.70GHz"},
                {"field": "Hypervisor vendor", "data": "KVM"},
            ]}
            return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")
        query = cmd[1]
        if "memory.bar1.used" in query:
            return SimpleNamespace(
                returncode=1, stdout="", stderr="Failed to query memory.bar1.used\n"
            )
        if hht._SMI_QUERY_PCIE in query:
            return SimpleNamespace(returncode=0, stdout="5,5,16,16\n", stderr="")
        return SimpleNamespace(
            returncode=0,
            stdout=(
                "NVIDIA RTX PRO 6000,GPU-rtxpro6000abcdef0123456789abcdef,"
                "550.54.15,00000000:00:03.0,P0,1410,1593,225.5,85,70\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(hht.subprocess, "run", fake_run)
    _force_smi_path(monkeypatch)
    monkeypatch.delenv("COMFYMODAL_V2_SLOW_H2D_THRESHOLD_MS", raising=False)
    monkeypatch.delenv("COMFYMODAL_V2_HOST_DIAGNOSTICS", raising=False)

    trace = _FakeTrace()
    meta = hht.emit_slow_h2d_forensics(record, trace)
    assert spawns["count"] == 4  # full + core + pcie + lscpu
    assert len(trace.events) == 1
    name, phase, event_meta = trace.events[0]
    assert name == "host_forensic_slow_h2d"
    assert phase == "host"
    assert event_meta["h2d_classification"] == "HOST_OVERHEAD_AROUND_COPY"
    assert event_meta["gpu_name"] == "NVIDIA RTX PRO 6000"
    assert event_meta["gpu_pcie_gen_current"] == 5.0
    assert event_meta["gpu_pcie_width_current"] == 16.0
    assert event_meta["trigger_reason"] == "h2d_threshold"
    assert event_meta["lscpu_architecture"] == "x86_64"
    assert event_meta["lscpu_cpu_count"] == 8
    assert event_meta["lscpu_model_name"].startswith("Intel(R)")
    assert event_meta["lscpu_hypervisor_vendor"] == "KVM"
    assert event_meta["h2d_copy_count"] == 12
    assert event_meta["h2d_total_bytes"] == 104857600
    assert event_meta["h2d_to_wall_ms"] == 5234.5
    assert event_meta["probe_wall_ms"] is not None
    assert meta == event_meta


def test_emit_slow_h2d_forensics_all_fail(monkeypatch):
    record = {"h2d_to_wall_ms": 9000.0, "h2d_cuda_elapsed_ms": 500.0,
              "h2d_enqueue_host_ms": 100.0, "h2d_sync_wait_host_ms": 50.0}
    monkeypatch.setattr(hht.subprocess, "run", _raising_subprocess)
    monkeypatch.setattr(hht, "nvidia_gpu_snapshot", lambda: dict(_UNAVAILABLE_GPU))
    monkeypatch.delenv("COMFYMODAL_V2_SLOW_H2D_THRESHOLD_MS", raising=False)
    monkeypatch.delenv("COMFYMODAL_V2_HOST_DIAGNOSTICS", raising=False)

    trace = _FakeTrace()
    meta = hht.emit_slow_h2d_forensics(record, trace)
    assert len(trace.events) == 1
    name, phase, event_meta = trace.events[0]
    assert name == "host_forensic_slow_h2d"
    assert phase == "host"
    assert "gpu_name" not in event_meta
    assert "lscpu_architecture" not in event_meta
    assert event_meta["h2d_classification"] == "UNKNOWN/MIXED"
    assert event_meta["trigger_reason"] == "h2d_threshold"
    assert event_meta["probe_wall_ms"] >= 0


# ---------------------------------------------------------------------------
# 14. two-tier: Tier A is subprocess-free and single-digit-ish
# ---------------------------------------------------------------------------

def test_tier_a_healthy_path_zero_subprocesses(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("subprocess.run called on the Tier A healthy path")

    monkeypatch.setattr(hht.subprocess, "run", boom)
    monkeypatch.setattr(
        hht, "try_direct_cpuid",
        lambda: {"cpuid_status": "unavailable", "cpuid_source": None,
                 "cpuid_vendor": None, "cpuid_brand": None, "cpuid_family": None,
                 "cpuid_model": None, "cpuid_stepping": None, "cpuid_flags": None},
    )
    monkeypatch.setattr(hht, "_add_topology_env", lambda result: None)
    monkeypatch.setattr(hht, "_torch_gpu_identity", lambda: dict(_UNAVAILABLE_TORCH_GPU))

    fingerprint = hht.collect_host_fingerprint()
    assert fingerprint["gpu_static_source"] == "unavailable"
    assert fingerprint["lscpu_status"] == "deferred"

    for phase in ("post_restore", "pre_h2d", "post_h2d", "sampling_start"):
        snap = hht.capture_resource_snapshot(phase)
        assert snap["phase"] == phase
        assert snap["probe_wall_ms"] >= 0

    # The healthy path carries NO ctypes/driver calls at all (removed probe).
    assert not hasattr(hht, "ctypes")


def test_capability_cache_skips_repeat_probes(monkeypatch):
    fs = _FakeFS(files={}, fail_all=True)
    monkeypatch.setattr("builtins.open", fs.open)
    monkeypatch.setattr(hht.subprocess, "run", _raising_subprocess)
    # Let the psi gate pass so the first probe actually opens the pressure
    # files (which then fail through the fake fs).
    monkeypatch.setattr(
        hht.os.path, "exists",
        lambda path: True if path == "/proc/pressure" else os.path.exists(path),
    )

    hht.capture_resource_snapshot("post_restore")
    pressure_first = [p for p in fs.opened_paths if "pressure" in p]
    cgroup_first = [p for p in fs.opened_paths if "cgroup" in p or "mountinfo" in p]
    assert pressure_first
    assert cgroup_first

    hht.capture_resource_snapshot("pre_h2d")
    pressure_second = [p for p in fs.opened_paths if "pressure" in p]
    cgroup_second = [p for p in fs.opened_paths if "cgroup" in p or "mountinfo" in p]
    assert len(pressure_second) == len(pressure_first)
    assert len(cgroup_second) == len(cgroup_first)


def test_fingerprint_opened_path_reduction(monkeypatch):
    """psi gate + v1 cgroup short-circuit minimize Tier A file opens."""
    fs = _FakeFS(files={}, fail_all=True)
    monkeypatch.setattr("builtins.open", fs.open)
    monkeypatch.setattr(hht.subprocess, "run", _raising_subprocess)
    # Force the /proc/pressure tree absent (as under gVisor) so the single
    # existence gate replaces the three ENOENT opens.
    monkeypatch.setattr(
        hht.os.path, "exists",
        lambda path: False if path == "/proc/pressure" else os.path.exists(path),
    )
    _patch_fast_fingerprint_collection(monkeypatch)

    hht.collect_host_fingerprint()

    assert not any("pressure" in p for p in fs.opened_paths)
    cgroup_opens = [p for p in fs.opened_paths if "cgroup" in p or "mountinfo" in p]
    assert "/proc/self/cgroup" in cgroup_opens
    assert not any("mountinfo" in p for p in cgroup_opens)
    assert not any("cpuacct.usage" in p for p in fs.opened_paths)
    assert not any("memory.usage_in_bytes" in p for p in fs.opened_paths)


def test_fingerprint_lscpu_deferred_by_default(monkeypatch):
    monkeypatch.delenv("COMFYMODAL_V2_HOST_DIAGNOSTICS", raising=False)
    _patch_fast_fingerprint_collection(monkeypatch)
    result = hht.collect_host_fingerprint()
    assert result["lscpu_status"] == "deferred"
    assert "lscpu_architecture" not in result
    assert "lscpu_cpu_count" not in result


def test_fingerprint_lscpu_diag_mode(monkeypatch):
    monkeypatch.setenv("COMFYMODAL_V2_HOST_DIAGNOSTICS", "1")
    payload = {"lscpu": [
        {"field": "Architecture", "data": "x86_64"},
        {"field": "CPU(s)", "data": 8},
        {"field": "Vendor ID", "data": "GenuineIntel"},
        {"field": "Model name", "data": "Intel(R) Xeon(R) Platinum 8480+ @ 2.70GHz"},
        {"field": "Hypervisor vendor", "data": "KVM"},
    ]}

    def fake_run(cmd, *args, **kwargs):
        assert cmd[0] == "lscpu"
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(hht.subprocess, "run", fake_run)
    _patch_fast_fingerprint_collection(monkeypatch)
    result = hht.collect_host_fingerprint()
    assert result["lscpu_status"] == "available"
    assert result["lscpu_architecture"] == "x86_64"
    assert result["lscpu_cpu_count"] == 8
    assert result["lscpu_hypervisor_vendor"] == "KVM"


# ---------------------------------------------------------------------------
# 15. two-tier: static GPU identity via already-loaded torch (no driver calls)
# ---------------------------------------------------------------------------

class _FakeDeviceProps:
    def __init__(self):
        self.major = 8
        self.minor = 6
        self.total_memory = 8589934592
        self.multi_processor_count = 46


class _FakeCuda:
    def is_available(self):
        return True

    def get_device_name(self, index):
        return "NVIDIA GeForce RTX 3070"

    def get_device_properties(self, index):
        return _FakeDeviceProps()


_FAKE_TORCH = SimpleNamespace(cuda=_FakeCuda())


def test_torch_gpu_identity_available(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", _FAKE_TORCH)
    monkeypatch.setattr(hht, "_add_topology_env", lambda result: None)

    result = hht._torch_gpu_identity()
    assert result["gpu_static_source"] == "torch_only"
    assert result["gpu_name"] == "NVIDIA GeForce RTX 3070"
    assert result["torch_device_capability"] == "8.6"
    assert result["torch_total_memory_bytes"] == 8589934592
    assert result["torch_multi_processor_count"] == 46
    # Tier B-only fields (UUID/driver/PCIe) are NOT part of the Tier A identity.
    assert "gpu_uuid_hash" not in result
    assert "gpu_pcie_gen_max" not in result

    # The fingerprint surfaces the torch identity and no subprocess is needed.
    fingerprint = hht.collect_host_fingerprint()
    assert fingerprint["gpu_static_source"] == "torch_only"
    assert fingerprint["gpu_name"] == "NVIDIA GeForce RTX 3070"
    assert fingerprint["torch_device_capability"] == "8.6"


def test_torch_gpu_identity_unavailable(monkeypatch):
    if "torch" in sys.modules:
        monkeypatch.setitem(sys.modules, "torch", None)
    result = hht._torch_gpu_identity()
    assert result["gpu_static_source"] == "unavailable"
    assert result["gpu_name"] is None
    assert result["torch_device_capability"] is None
    assert result["torch_total_memory_bytes"] is None
    assert result["torch_multi_processor_count"] is None
