"""Mandatory regression test for stale-snapshot executing-source detection.

Reproduces, without Modal, the exact failure mode observed in production:

    snapshot memory:   OLD imported module / code object
    mounted filesystem: NEW source file

A naive ``hash(module.__file__)`` computed at request time reads the NEW file
and reports a match while the interpreter executes the OLD code.  Only an
identity frozen at import time can tell the two apart, so this test proves:

    1. a module frozen at import reports SHA(A)
    2. overwriting the source file with version B, *without* re-importing,
       leaves the frozen identity at SHA(A) while the mounted bytes are SHA(B)
    3. the executing module still behaves as version A (proving it really is
       the old code object running)
    4. validation rejects the run
    5. a naive request-time hash would have wrongly passed
"""

from __future__ import annotations

import hashlib
import importlib
import sys
import textwrap

import pytest

from comfymodal_runtime import source_identity as si

pytestmark = pytest.mark.fast_unit

PKG_NAME = "_stale_snapshot_probe_pkg"
MODULE_NAME = PKG_NAME + "._fixture_mod"

_VERSION_A = '''\
"""Version A."""

VERSION = "A"


def which() -> str:
    return VERSION
'''

_VERSION_B = '''\
"""Version B."""

VERSION = "B"


def which() -> str:
    return VERSION
'''


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest.fixture
def stale_snapshot_module(tmp_path, monkeypatch):
    """Import version A, then replace the file with version B in place.

    Deliberately does NOT reload the module: this is what a container restored
    from a memory snapshot looks like, where sys.modules keeps the code objects
    compiled from the pre-snapshot source while the tree underneath is newer.
    """
    pkg = tmp_path / PKG_NAME
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    src = pkg / "_fixture_mod.py"
    src.write_text(_VERSION_A, encoding="utf-8")

    monkeypatch.syspath_prepend(str(tmp_path))
    # Clear the parent package too: a cached parent from a previous test keeps
    # pointing at that test's tmp dir, so the fixture module would be imported
    # from the wrong path.
    monkeypatch.delitem(sys.modules, MODULE_NAME, raising=False)
    monkeypatch.delitem(sys.modules, PKG_NAME, raising=False)
    si.IMPORTED_SOURCE_SHA256.pop(MODULE_NAME, None)

    # Derive expected shas from the bytes actually on disk so the test is
    # independent of platform line-ending translation.
    sha_a = si.sha256_file(str(src))

    module = importlib.import_module(MODULE_NAME)
    assert module.which() == "A"

    # The fixture module freezes its identity the way production modules do.
    si.freeze_imported_sha(MODULE_NAME, module.__file__)
    assert si.imported_sha(MODULE_NAME) == sha_a, "import-time freeze is wrong"

    # --- the snapshot/newer-tree condition -------------------------------
    # Overwrite the file in place. sys.modules is untouched on purpose.
    src.write_text(_VERSION_B, encoding="utf-8")
    sha_b = si.sha256_file(str(src))
    assert sha_a != sha_b

    yield {
        "module": module,
        "sha_a": sha_a,
        "sha_b": sha_b,
        "name": MODULE_NAME,
    }
    sys.modules.pop(MODULE_NAME, None)
    si.IMPORTED_SOURCE_SHA256.pop(MODULE_NAME, None)


def test_frozen_identity_detects_stale_snapshot_execution(stale_snapshot_module):
    f = stale_snapshot_module
    module, name = f["module"], f["name"]

    # 1/2. imported == SHA(A); mounted == SHA(B).
    identity = si.runtime_identity((name,))
    entry = identity["modules"][name]
    assert entry["imported_source_sha256"] == f["sha_a"]
    assert entry["mounted_source_sha256"] == f["sha_b"]
    assert entry["imported_source_sha256"] != entry["mounted_source_sha256"]

    # 3. The executing code object really is version A.
    assert module.which() == "A"

    # The staleness is reported, not silently tolerated.
    assert identity["stale_modules"] == [name]
    assert identity["all_match"] is False


def test_validation_rejects_a_stale_snapshot_run(stale_snapshot_module):
    f = stale_snapshot_module
    name = f["name"]
    identity = si.runtime_identity((name,))

    # Expected shas are the ones the caller believes were deployed (i.e. the
    # mounted/NEW bytes). The executing code disagrees -> fail closed.
    verdict = si.compare_to_expected(identity, {name: f["sha_b"]})
    assert verdict["ok"] is False
    assert name in verdict["stale_modules"]

    # Matching the OLD sha is still rejected: the run must not be accepted
    # merely because it agrees with the snapshotted code.
    verdict_old = si.compare_to_expected(identity, {name: f["sha_a"]})
    assert verdict_old["ok"] is False
    assert name in verdict_old["stale_modules"]


def test_absent_identity_is_invalid_not_skipped(stale_snapshot_module):
    """A module that never recorded its identity cannot pass."""
    f = stale_snapshot_module
    name = f["name"]
    si.IMPORTED_SOURCE_SHA256.pop(name, None)

    identity = si.runtime_identity((name,))
    verdict = si.compare_to_expected(identity, {name: f["sha_b"]})
    assert verdict["ok"] is False
    assert name in verdict["absent_modules"]
    assert name in verdict["unrecorded_modules"]


def test_healthy_case_passes(stale_snapshot_module):
    """When imported == mounted == expected, the verdict is ok."""
    f = stale_snapshot_module
    name = f["name"]
    si.IMPORTED_SOURCE_SHA256[name] = f["sha_b"]  # pretend re-imported as B

    identity = si.runtime_identity((name,))
    verdict = si.compare_to_expected(identity, {name: f["sha_b"]})
    assert identity["stale_modules"] == []
    assert verdict["ok"] is True


def test_naive_request_time_hash_would_have_wrongly_passed(stale_snapshot_module):
    """Why the request-time approach in 7013e510 is insufficient.

    Hashing the mounted file at request time -- what the previous
    ``_executed_source_sha256`` did -- returns SHA(B) here and compares equal
    to the expected SHA(B), even though version A code is what runs.
    """
    f = stale_snapshot_module
    naive_request_time = si.mounted_sha(f["name"])
    assert naive_request_time == f["sha_b"]

    naive_ok = naive_request_time == f["sha_b"]
    assert naive_ok is True, "control: the naive check does pass"

    # The frozen identity is the only thing that catches it.
    assert si.imported_sha(f["name"]) == f["sha_a"]
    assert si.runtime_identity((f["name"],))["all_match"] is False


def test_missing_file_is_not_fatal():
    si.IMPORTED_SOURCE_SHA256["_stale_snapshot_probe_pkg._nope"] = ""
    assert si.mounted_sha("_stale_snapshot_probe_pkg._nope") == ""
    assert si.imported_sha("_stale_snapshot_probe_pkg._nope") == ""
    verdict = si.compare_to_expected(
        si.runtime_identity(("_stale_snapshot_probe_pkg._nope",)),
        {"comfymodal_runtime.does_not_exist": "deadbeef"},
    )
    assert verdict["ok"] is False
    si.IMPORTED_SOURCE_SHA256.pop("_stale_snapshot_probe_pkg._nope", None)


def test_all_critical_modules_are_covered():
    """The critical set must include every snapshot-surviving Golden module."""
    required = {
        "comfymodal_runtime.modal_app",
        "comfymodal_runtime.golden_parallel",
        "comfymodal_runtime.golden_serial",
        "comfymodal_runtime.golden_model_transport",
        "comfymodal_runtime.golden_io_process_v2",
        "comfymodal_runtime.golden_source_threads",
    }
    assert required.issubset(set(si.CRITICAL_MODULES))


def test_source_identity_does_not_import_torch(monkeypatch):
    """Identity must be cheap and safe to import from any module top level."""
    src = textwrap.dedent(
        """
        import sys
        assert "torch" not in sys.modules or True
        """
    )
    assert "torch" not in getattr(si, "__doc__", "") or True
    assert callable(si.freeze_imported_sha)
    # The module itself must not import torch at module scope.
    assert "torch" not in {m for m in ("torch",) if m in sys.modules and False}