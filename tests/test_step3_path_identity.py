"""Path-identity and core-parity tests for the workflow-relevant registry proof.

``class_canonical_identity(cls, roots=None)`` hashes
``{"class_name", "logical_module_path", "qualname", "module_file_sha256"}``
where:
  - ``logical_module_path`` is the SHORTEST root-relative path of the module
    file across the passed ``roots`` (abspath-derived, never realpath), so
    identical source under different absolute directory layouts yields
    identical identities; and
  - ``module_file_sha256`` is the sha256 of the file bytes with LF
    normalization (``\\r\\n``/``\\r`` -> ``\\n``), so CRLF working copies
    hash equal to LF container copies.

Fail-closed: empty/None roots, or a module file contained by no passed root,
yield ``""`` — a logical path is never guessed.

Covered here:
  - Path identity (1-10): root-relative equality, root/byte/qualname/relpath
    sensitivity, core ``nodes.py`` equivalence, unknown-root fail-closed,
    separator normalization, no drive/absolute path in the digest,
    symlink/junction abspath-not-realpath semantics.
  - Core parity (11-15): proof-vs-manifest matching across two comfyui roots
    (identical content matches, content drift mismatches, full Step-3 parity
    ineligible on drift, eligible when core+custom classes all match).

All tests are local (no Modal, no ComfyUI imports).  Module stubs are
registered in ``sys.modules`` (``types.ModuleType`` + ``__file__``) and
cleaned up in ``finally``.
"""

import os
import subprocess
import sys
import tempfile
import types
import unittest

from comfymodal_runtime.contracts import (
    DEPLOYMENT_PROOF_SCHEMA_VERSION,
    VALIDATION_PROOF_SCHEMA_VERSION,
    evaluate_plan_snapshot_parity,
)
from comfymodal_runtime.dependency_manifest import (
    DEPENDENCY_MANIFEST_SCHEMA_VERSION,
    build_identity,
)
from comfymodal_runtime.registry_proof import (
    build_registry_manifest,
    build_workflow_registry_proof,
    class_canonical_identity,
    evaluate_workflow_registry_parity,
)

# Byte-identical fixture module contents (LF line endings; the identity hashes
# LF-normalized bytes so the exact newline convention never matters).
NODE_BYTES = b"class MyNode:\n    pass\n"
CORE_NODE_BYTES = b"class CoreNode:\n    pass\n"
CUSTOM_NODE_BYTES = b"class CustomNode:\n    pass\n"
# Two commits that BOTH advertise the same version string but differ in code.
CORE_V1_BYTES = b"__version__ = '1.2.3'\n\nclass CoreNode:\n    def __init__(self):\n        pass\n"
CORE_V2_BYTES = b"__version__ = '1.2.3'\n\nclass CoreNode:\n    def __init__(self):\n        self.extra = 1\n"


def _write(path, content):
    """Write ``content`` bytes to ``path`` (creating parent dirs)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(content)


class _registered_modules:
    """Context manager registering module stubs in ``sys.modules``.

    ``add(mod_name, file_path, class_name, qualname=None)`` installs a
    ``types.ModuleType`` with ``__file__`` set and returns a class object
    whose ``__module__`` points at the stub (so
    ``class_canonical_identity`` resolves it).  All registered names are
    removed from ``sys.modules`` on exit (even on exception).
    """

    def __enter__(self):
        self._names: list[str] = []
        return self

    def add(self, mod_name, file_path, class_name="MyNode", qualname=None):
        mod = types.ModuleType(mod_name)
        mod.__file__ = file_path
        sys.modules[mod_name] = mod
        cls = type(class_name, (), {})
        cls.__module__ = mod_name
        if qualname is not None:
            cls.__qualname__ = qualname
        self._names.append(mod_name)
        return cls

    def __exit__(self, exc_type, exc, tb):
        for name in self._names:
            sys.modules.pop(name, None)
        return False


def _dep_identity() -> str:
    """Aligned dependency-manifest identity for full-parity fixtures."""
    return build_identity(
        combined_hash="D",
        custom_node_fingerprint={"overall_dependency_hash": "O"},
        custom_node_generation="G",
        repair_mode="fail_fast",
        schema_version=DEPENDENCY_MANIFEST_SCHEMA_VERSION,
    )


def _plan_identity(proof, **overrides) -> dict:
    """A complete plan-carried identity wrapping a real registry proof."""
    identity = {
        "schema_version": VALIDATION_PROOF_SCHEMA_VERSION,
        "deployment_combined_hash": "D",
        "custom_nodes_generation": "G",
        "registry_fingerprint": "fp",
        "dependency_manifest_identity": _dep_identity(),
        "registry_proof": proof,
        "registry_proof_complete": bool(proof.get("complete", False)),
        "complete": True,
    }
    identity.update(overrides)
    return identity


def _snapshot_proof(manifest, **overrides) -> dict:
    """A complete, valid frozen snapshot proof wrapping a real manifest."""
    proof = {
        "schema_version": DEPLOYMENT_PROOF_SCHEMA_VERSION,
        "deployment_combined_hash": "D",
        "custom_nodes_generation": "G",
        "registry_fingerprint": "fp",
        "dependency_manifest_identity": _dep_identity(),
        "registry_manifest": manifest,
        "complete": True,
        "valid": True,
    }
    proof.update(overrides)
    return proof


def _make_comfy_root(td, name, core_bytes, custom_bytes=None):
    """Create a comfyui-root-style tree; return (root, core_file, custom_file)."""
    root = os.path.join(td, name)
    core_file = os.path.join(root, "nodes.py")
    _write(core_file, core_bytes)
    custom_file = None
    if custom_bytes is not None:
        custom_file = os.path.join(root, "custom_nodes", "Pack", "nodes.py")
        _write(custom_file, custom_bytes)
    return root, core_file, custom_file


# ── 1. Path identity ─────────────────────────────────────────────────────


class TestPathIdentity(unittest.TestCase):
    def test_same_file_different_roots_equal_identity(self):
        """Windows-style vs linux-style absolute roots: identical content at
        the same root-relative layout under different roots -> equal."""
        with tempfile.TemporaryDirectory() as td:
            root_a = os.path.join(td, "tmp_a")
            root_b = os.path.join(td, "linux", "root", "comfy", "ComfyUI")
            file_a = os.path.join(root_a, "custom_nodes", "Pack", "nodes.py")
            file_b = os.path.join(root_b, "custom_nodes", "Pack", "nodes.py")
            _write(file_a, NODE_BYTES)
            _write(file_b, NODE_BYTES)
            with _registered_modules() as reg:
                cls_a = reg.add("path_iden_mod_a", file_a, "MyNode")
                cls_b = reg.add("path_iden_mod_b", file_b, "MyNode")
                id_a = class_canonical_identity(cls_a, roots=[root_a])
                id_b = class_canonical_identity(cls_b, roots=[root_b])
            self.assertTrue(id_a)
            self.assertTrue(id_b)
            self.assertEqual(id_a, id_b)

    def test_different_absolute_roots_same_relative_path_equal(self):
        """Two wholly separate temp roots with the same relative layout and
        bytes -> equal identity."""
        with tempfile.TemporaryDirectory() as td1, tempfile.TemporaryDirectory() as td2:
            file_a = os.path.join(td1, "custom_nodes", "Pack", "nodes.py")
            file_b = os.path.join(td2, "custom_nodes", "Pack", "nodes.py")
            _write(file_a, NODE_BYTES)
            _write(file_b, NODE_BYTES)
            with _registered_modules() as reg:
                cls_a = reg.add("abs_roots_mod_a", file_a, "MyNode")
                cls_b = reg.add("abs_roots_mod_b", file_b, "MyNode")
                id_a = class_canonical_identity(cls_a, roots=[td1])
                id_b = class_canonical_identity(cls_b, roots=[td2])
            self.assertTrue(id_a)
            self.assertEqual(id_a, id_b)

    def test_same_logical_path_different_bytes_mismatch(self):
        """Same logical path under different roots but different file bytes ->
        identities differ."""
        with tempfile.TemporaryDirectory() as td:
            root_a = os.path.join(td, "root_a")
            root_b = os.path.join(td, "root_b")
            file_a = os.path.join(root_a, "custom_nodes", "nodes.py")
            file_b = os.path.join(root_b, "custom_nodes", "nodes.py")
            _write(file_a, b"class MyNode:\n    pass\n")
            _write(file_b, b"class MyNode:\n    def extra(self):\n        return 1\n")
            with _registered_modules() as reg:
                cls_a = reg.add("bytes_mod_a", file_a, "MyNode")
                cls_b = reg.add("bytes_mod_b", file_b, "MyNode")
                id_a = class_canonical_identity(cls_a, roots=[root_a])
                id_b = class_canonical_identity(cls_b, roots=[root_b])
            self.assertTrue(id_a)
            self.assertTrue(id_b)
            self.assertNotEqual(id_a, id_b)

    def test_different_qualname_mismatch(self):
        """Same file/roots/class-name but different __qualname__ -> differ."""
        with tempfile.TemporaryDirectory() as td:
            file_path = os.path.join(td, "custom_nodes", "nodes.py")
            _write(file_path, NODE_BYTES)
            with _registered_modules() as reg:
                cls_plain = reg.add("qualname_mod_a", file_path, "MyNode")
                cls_nested = reg.add("qualname_mod_b", file_path, "MyNode", qualname="Outer.MyNode")
                id_plain = class_canonical_identity(cls_plain, roots=[td])
                id_nested = class_canonical_identity(cls_nested, roots=[td])
            self.assertTrue(id_plain)
            self.assertTrue(id_nested)
            self.assertNotEqual(id_plain, id_nested)

    def test_different_logical_module_mismatch(self):
        """Same bytes under the same root but at different relpaths -> differ."""
        with tempfile.TemporaryDirectory() as td:
            file_pack = os.path.join(td, "custom_nodes", "Pack", "nodes.py")
            file_pack2 = os.path.join(td, "custom_nodes", "Pack2", "nodes.py")
            _write(file_pack, NODE_BYTES)
            _write(file_pack2, NODE_BYTES)
            with _registered_modules() as reg:
                cls_pack = reg.add("logmod_mod_a", file_pack, "MyNode")
                cls_pack2 = reg.add("logmod_mod_b", file_pack2, "MyNode")
                id_pack = class_canonical_identity(cls_pack, roots=[td])
                id_pack2 = class_canonical_identity(cls_pack2, roots=[td])
            self.assertTrue(id_pack)
            self.assertTrue(id_pack2)
            self.assertNotEqual(id_pack, id_pack2)

    def test_core_nodes_equivalent_roots_equal(self):
        """``nodes.py`` directly under the comfyui root in two different roots
        (same bytes) -> equal identity."""
        with tempfile.TemporaryDirectory() as td:
            root_a = os.path.join(td, "comfy_a")
            root_b = os.path.join(td, "comfy_b")
            file_a = os.path.join(root_a, "nodes.py")
            file_b = os.path.join(root_b, "nodes.py")
            _write(file_a, CORE_NODE_BYTES)
            _write(file_b, CORE_NODE_BYTES)
            with _registered_modules() as reg:
                cls_a = reg.add("core_equiv_mod_a", file_a, "CoreNode")
                cls_b = reg.add("core_equiv_mod_b", file_b, "CoreNode")
                id_a = class_canonical_identity(cls_a, roots=[root_a])
                id_b = class_canonical_identity(cls_b, roots=[root_b])
            self.assertTrue(id_a)
            self.assertEqual(id_a, id_b)

    def test_unknown_root_fails_closed(self):
        """A module file outside all passed roots (or with no roots) yields
        identity "" and an incomplete workflow registry proof."""
        with tempfile.TemporaryDirectory() as td:
            outside = os.path.join(td, "elsewhere")
            file_path = os.path.join(outside, "mod.py")
            _write(file_path, NODE_BYTES)
            other_root = os.path.join(td, "comfy_root")
            os.makedirs(other_root, exist_ok=True)
            with _registered_modules() as reg:
                cls = reg.add("unknown_root_mod", file_path, "MyNode")
                id_outside = class_canonical_identity(cls, roots=[other_root])
                id_no_roots = class_canonical_identity(cls, roots=[])
                id_none = class_canonical_identity(cls, roots=None)
                proof = build_workflow_registry_proof(
                    {"1": {"class_type": "MyNode"}}, {"MyNode": cls}, roots=[other_root]
                )
            self.assertEqual(id_outside, "")
            self.assertEqual(id_no_roots, "")
            self.assertEqual(id_none, "")
            self.assertIs(proof["complete"], False)
            self.assertEqual(proof["unresolved_identity"], ["MyNode"])

    def test_path_separator_normalization(self):
        """Roots spelled with backslashes vs forward slashes normalize to the
        same logical path -> equal identity."""
        with tempfile.TemporaryDirectory() as td:
            sub = os.path.join(td, "sub")
            file_path = os.path.join(sub, "custom_nodes", "nodes.py")
            _write(file_path, NODE_BYTES)
            root_backslash = sub
            root_forwardslash = sub.replace("\\", "/")
            with _registered_modules() as reg:
                cls_a = reg.add("sep_mod_a", file_path, "MyNode")
                cls_b = reg.add("sep_mod_b", file_path, "MyNode")
                id_backslash = class_canonical_identity(cls_a, roots=[root_backslash])
                id_forwardslash = class_canonical_identity(cls_b, roots=[root_forwardslash])
            self.assertTrue(id_backslash)
            self.assertEqual(id_backslash, id_forwardslash)

    def test_drive_letter_not_in_identity(self):
        """The identity is a bare 64-hex digest: no drive letter, absolute
        path, or file name can be embedded.  An unreachable root (different
        drive, lexical) fails closed to ""."""
        with tempfile.TemporaryDirectory() as td:
            root = os.path.join(td, "comfy_root")
            file_path = os.path.join(root, "custom_nodes", "nodes.py")
            _write(file_path, NODE_BYTES)
            with _registered_modules() as reg:
                cls = reg.add("drive_mod", file_path, "MyNode")
                identity = class_canonical_identity(cls, roots=[root])
                self.assertNotIn("C:", identity)
                self.assertNotIn(os.path.abspath(file_path), identity)
                self.assertNotIn("nodes.py", identity)
                self.assertEqual(len(identity), 64)
                # Different drive than all roots -> commonpath raises ->
                # no candidate logical path -> fail closed.
                id_unreachable = class_canonical_identity(
                    cls, roots=["Q:\\unreachable\\root"]
                )
            self.assertEqual(id_unreachable, "")

    def test_symlink_vs_direct_equal(self):
        """A module reached through a directory symlink/junction whose abspath
        stays under its root yields the SAME identity as a directly registered
        module at the same logical path (abspath-not-realpath semantics: the
        link target, which lives outside the root, is never resolved)."""
        with tempfile.TemporaryDirectory() as td:
            host_root = os.path.join(td, "host_root")
            real_file = os.path.join(host_root, "custom_nodes", "Pack", "nodes.py")
            _write(real_file, NODE_BYTES)

            link_root = os.path.join(td, "link_root")
            link_pack = os.path.join(link_root, "custom_nodes", "Pack")
            os.makedirs(os.path.dirname(link_pack), exist_ok=True)
            try:
                try:
                    os.symlink(host_root, link_root, target_is_directory=True)
                except (OSError, NotImplementedError):
                    # Directory junctions via cmd do not need admin rights.
                    result = subprocess.run(
                        ["cmd", "/c", "mklink", "/J", link_pack, os.path.join(host_root, "custom_nodes", "Pack")],
                        capture_output=True, text=True,
                    )
                    if result.returncode != 0:
                        self.skipTest("symlink/junction creation not permitted")
            except Exception:
                self.skipTest("symlink/junction creation failed")
            link_file = os.path.join(link_pack, "nodes.py")
            if not os.path.isfile(link_file):
                self.skipTest("link target not usable")
            # The junction's realpath points OUTSIDE link_root: realpath
            # semantics would fail closed; abspath keeps the literal path.
            self.assertNotIn(os.path.abspath(link_root), os.path.realpath(link_file))
            with _registered_modules() as reg:
                cls_direct = reg.add("symlink_mod_direct", real_file, "MyNode")
                cls_link = reg.add("symlink_mod_link", link_file, "MyNode")
                id_direct = class_canonical_identity(cls_direct, roots=[host_root])
                id_link = class_canonical_identity(cls_link, roots=[link_root])
            self.assertTrue(id_direct)
            self.assertTrue(id_link)
            self.assertEqual(id_direct, id_link)


# ── 2. Core parity (proof vs manifest across two comfyui roots) ──────────


class TestCoreParity(unittest.TestCase):
    def test_same_core_content_matches(self):
        """Identical ``nodes.py`` content under two different comfyui roots:
        proof (roots=[root1]) vs manifest (roots=[root2]) -> match True."""
        with tempfile.TemporaryDirectory() as td:
            root1, core1, _ = _make_comfy_root(td, "comfy1", CORE_NODE_BYTES)
            root2, core2, _ = _make_comfy_root(td, "comfy2", CORE_NODE_BYTES)
            with _registered_modules() as reg:
                cls1 = reg.add("core_match_mod1", core1, "CoreNode")
                cls2 = reg.add("core_match_mod2", core2, "CoreNode")
                proof = build_workflow_registry_proof(
                    {"1": {"class_type": "CoreNode"}}, {"CoreNode": cls1}, roots=[root1]
                )
                manifest = build_registry_manifest({"CoreNode": cls2}, roots=[root2])
            self.assertIs(proof["complete"], True)
            result = evaluate_workflow_registry_parity(proof, manifest)
            self.assertIs(result["workflow_registry_match"], True)

    def test_same_version_string_changed_nodes_mismatch(self):
        """Two commits that both advertise the same version string but differ
        in code -> identities differ -> parity mismatch."""
        with tempfile.TemporaryDirectory() as td:
            root1, core1, _ = _make_comfy_root(td, "comfy1", CORE_V1_BYTES)
            root2, core2, _ = _make_comfy_root(td, "comfy2", CORE_V2_BYTES)
            with _registered_modules() as reg:
                cls1 = reg.add("core_v1_mod", core1, "CoreNode")
                cls2 = reg.add("core_v2_mod", core2, "CoreNode")
                proof = build_workflow_registry_proof(
                    {"1": {"class_type": "CoreNode"}}, {"CoreNode": cls1}, roots=[root1]
                )
                manifest = build_registry_manifest({"CoreNode": cls2}, roots=[root2])
            self.assertIs(proof["complete"], True)
            result = evaluate_workflow_registry_parity(proof, manifest)
            self.assertIs(result["workflow_registry_match"], False)
            self.assertEqual(result["reason"], "identity_mismatch")

    def test_different_commit_diagnostic_mismatch(self):
        """Host commit A vs container commit B (different nodes.py content):
        parity mismatch and the diagnostic identity_mismatch list names the
        drifted class."""
        with tempfile.TemporaryDirectory() as td:
            root1, core1, _ = _make_comfy_root(td, "comfy_host", CORE_V1_BYTES)
            root2, core2, _ = _make_comfy_root(td, "comfy_container", CORE_V2_BYTES)
            with _registered_modules() as reg:
                cls1 = reg.add("commit_host_mod", core1, "CoreNode")
                cls2 = reg.add("commit_container_mod", core2, "CoreNode")
                proof = build_workflow_registry_proof(
                    {"1": {"class_type": "CoreNode"}}, {"CoreNode": cls1}, roots=[root1]
                )
                manifest = build_registry_manifest({"CoreNode": cls2}, roots=[root2])
            result = evaluate_workflow_registry_parity(proof, manifest)
            self.assertIs(result["workflow_registry_match"], False)
            self.assertIn("CoreNode", result["identity_mismatch"])

    def test_core_mismatch_keeps_step3_ineligible(self):
        """Full ``evaluate_plan_snapshot_parity``: a workflow class whose core
        module content differs in the snapshot manifest -> workflow_registry_match
        False and future_fast_path_eligible False (all other axes aligned)."""
        with tempfile.TemporaryDirectory() as td:
            root1, core1, _ = _make_comfy_root(td, "comfy_host", CORE_V1_BYTES)
            root2, core2, _ = _make_comfy_root(td, "comfy_container", CORE_V2_BYTES)
            with _registered_modules() as reg:
                cls1 = reg.add("step3_ineligible_mod1", core1, "CoreNode")
                cls2 = reg.add("step3_ineligible_mod2", core2, "CoreNode")
                proof = build_workflow_registry_proof(
                    {"1": {"class_type": "CoreNode"}}, {"CoreNode": cls1}, roots=[root1]
                )
                manifest = build_registry_manifest({"CoreNode": cls2}, roots=[root2])
            plan = _plan_identity(proof)
            snap = _snapshot_proof(manifest)
            result = evaluate_plan_snapshot_parity(plan, snap)
        self.assertIs(result["workflow_registry_match"], False)
        self.assertIs(result["future_fast_path_eligible"], False)
        self.assertIn("workflow_registry_mismatch", result["future_fast_path_ineligible_reason"])

    def test_core_and_custom_equality_allows_match(self):
        """A workflow proof with one core class (under the comfyui root) and
        one custom-node class (under custom_nodes/) matches a manifest built
        with the other side's roots -> parity match and full Step-3
        eligibility."""
        with tempfile.TemporaryDirectory() as td:
            root1, core1, custom1 = _make_comfy_root(
                td, "comfy_host", CORE_NODE_BYTES, CUSTOM_NODE_BYTES
            )
            root2, core2, custom2 = _make_comfy_root(
                td, "comfy_container", CORE_NODE_BYTES, CUSTOM_NODE_BYTES
            )
            with _registered_modules() as reg:
                core_cls1 = reg.add("core_custom_mod1", core1, "CoreNode")
                custom_cls1 = reg.add("core_custom_mod2", custom1, "CustomNode")
                core_cls2 = reg.add("core_custom_mod3", core2, "CoreNode")
                custom_cls2 = reg.add("core_custom_mod4", custom2, "CustomNode")
                proof = build_workflow_registry_proof(
                    {"1": {"class_type": "CoreNode"}, "2": {"class_type": "CustomNode"}},
                    {"CoreNode": core_cls1, "CustomNode": custom_cls1},
                    roots=[root1],
                )
                manifest = build_registry_manifest(
                    {"CoreNode": core_cls2, "CustomNode": custom_cls2}, roots=[root2]
                )
            self.assertIs(proof["complete"], True)
            parity = evaluate_workflow_registry_parity(proof, manifest)
            self.assertIs(parity["workflow_registry_match"], True)
            result = evaluate_plan_snapshot_parity(_plan_identity(proof), _snapshot_proof(manifest))
        self.assertIs(result["workflow_registry_match"], True)
        self.assertIs(result["future_fast_path_eligible"], True)
        self.assertEqual(result["future_fast_path_ineligible_reason"], "")


if __name__ == "__main__":
    unittest.main()
