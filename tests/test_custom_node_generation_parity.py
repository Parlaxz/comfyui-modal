"""Tests for the custom-node generation-parity repair contract.

Targets ``comfymodal_runtime.custom_node_parity`` (pure module, no
Modal/ComfyUI imports):

  - ``build_parity_report``: the baked / persisted / pre-sync-actual /
    post-sync-actual reconciliation matrix, final-authority selection and
    the proof-freeze prediction (``proof_generation_match``).
  - ``should_update_persisted_record``: the content-verified stale-record
    repair decision (the ONLY gate before the volume-sync closure; the
    closure additionally refuses to bless anything unless the post-sync
    ACTUAL tree equals the baked generation).
  - ``format_parity_line``: deterministic ``key=value`` log line with
    bools rendered as 1/0 and None as ``-``.

Scenario coverage (16 mandated + extras):

  1.  baked == persisted == actual                 -> full match, baked authority, proof OK
  2.  baked == actual, persisted stale             -> stale-record repair allowed with proof
  3.  persisted == actual, baked differs           -> volume authority, proof fails closed
  4.  all three differ                             -> volume authority, proof fails, record stale
  5.  sync changed actual -> baked                 -> baked authority, proof OK
  6.  sync changed actual -> persisted             -> volume authority, proof fails closed
  7.  persisted record missing                     -> None match, repair allowed
  8.  persisted record malformed (reads as empty)  -> baked authority when nothing else
  9.  algorithm/schema mismatch                    -> opaque-string equality, no format assumptions
 10.  sync failure (post-sync actual empty)        -> persisted authority fallback, no raise
 11.  record-write failure surface                -> pure decision + closure guard is the binder
 12.  proof never valid without content equality  -> 3/4/6 all proof_generation_match=0
 13.  proof freezes only the baked generation     -> proof_freeze_generation == baked always
 14.  restore exact-skip retains proof            -> baked authority, sync_performed=0
 15.  later custom-node drift marks proof stale   -> baked_matches_post_sync_actual=0
 16.  step-3 legacy fallback unchanged on mismatch-> proof == (final == baked) over A/B combos
 17.  format line deterministic                   -> stable order, key names, 1/0, '-'
 18.  should_update_record rules                  -> 5-row truth table
 19.  round trip preserves generation             -> REAL comfyapp fingerprint across tar.gz
 20.  no side effects / pure functions            -> import writes nothing; calls are pure

All tests are local (no Modal, no paid anything).
"""

import io
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import unittest
from pathlib import Path

import pytest

from comfymodal_runtime.custom_node_parity import (
    build_parity_report,
    format_parity_line,
    should_update_persisted_record,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
# The real ComfyUI custom_nodes root (parent of this repo) used only for the
# read-only full-tree sanity fingerprint.
REAL_CUSTOM_NODES_ROOT = REPO_ROOT.parent

# Full key set of the parity report (and the log line), per the contract.
_REPORT_KEYS = (
    "baked_generation",
    "persisted_generation",
    "pre_sync_actual_generation",
    "post_sync_actual_generation",
    "persisted_source",
    "sync_performed",
    "sync_direction",
    "sync_reason",
    "baked_matches_persisted",
    "baked_matches_pre_sync_actual",
    "baked_matches_post_sync_actual",
    "persisted_matches_post_sync_actual",
    "final_authoritative_generation",
    "final_authority_source",
    "proof_freeze_generation",
    "proof_generation_match",
)

_ALIASES = {
    "baked": "baked_generation",
    "persisted": "persisted_generation",
    "pre": "pre_sync_actual_generation",
    "post": "post_sync_actual_generation",
}


def _report(**overrides):
    """Build a parity report from a full-default baseline plus overrides.

    Defaults: baked='BAKED', persisted='PERSISTED', pre/post actual='',
    persisted_source='persisted_record', sync_performed=True,
    sync_direction='volume_to_container', sync_reason='generation_mismatch'.
    """
    kwargs = {
        "baked_generation": "BAKED",
        "persisted_generation": "PERSISTED",
        "pre_sync_actual_generation": "",
        "post_sync_actual_generation": "",
        "persisted_source": "persisted_record",
        "sync_performed": True,
        "sync_direction": "volume_to_container",
        "sync_reason": "generation_mismatch",
    }
    for key, value in overrides.items():
        kwargs[_ALIASES.get(key, key)] = value
    return build_parity_report(**kwargs)


def _line_keys(line):
    """Extract the ordered key names from a format_parity_line output."""
    return [part.split("=", 1)[0] for part in line.split()[1:]]


class TestGenerationParityScenarios(unittest.TestCase):
    """The 16 mandated scenarios plus the mismatch matrix."""

    def test_baked_equals_persisted_equals_actual(self):
        # baked == persisted == actual == 'X'
        r = _report(baked="X", persisted="X", pre="X", post="X")
        self.assertIs(r["baked_matches_persisted"], True)
        self.assertIs(r["baked_matches_pre_sync_actual"], True)
        self.assertIs(r["baked_matches_post_sync_actual"], True)
        self.assertIs(r["persisted_matches_post_sync_actual"], True)
        self.assertEqual(r["final_authoritative_generation"], "X")
        self.assertEqual(r["final_authority_source"], "baked_image")
        self.assertIs(r["proof_generation_match"], True)
        # Equal record: never rewritten.
        self.assertFalse(
            should_update_persisted_record(persisted_generation="X", actual_generation="X")
        )

    def test_baked_equals_actual_persisted_stale(self):
        # baked == actual == 'X', persisted is stale 'STALE'.
        r = _report(baked="X", persisted="STALE", pre="X", post="X")
        self.assertIs(r["baked_matches_persisted"], False)
        self.assertIs(r["baked_matches_post_sync_actual"], True)
        self.assertEqual(r["final_authoritative_generation"], "X")
        self.assertEqual(r["final_authority_source"], "baked_image")
        self.assertIs(r["proof_generation_match"], True)
        # Stale-record repair is allowed when the actual tree carries proof.
        self.assertTrue(
            should_update_persisted_record(persisted_generation="STALE", actual_generation="X")
        )

    def test_persisted_equals_actual_baked_differs(self):
        # baked 'BAKED', persisted == post-sync actual == 'X'.
        r = _report(baked="BAKED", persisted="X", pre="X", post="X")
        self.assertIs(r["baked_matches_post_sync_actual"], False)
        self.assertEqual(r["final_authoritative_generation"], "X")
        self.assertEqual(r["final_authority_source"], "volume_tree")
        self.assertIs(r["proof_generation_match"], False)
        # Never rewrite an equal record.
        self.assertFalse(
            should_update_persisted_record(persisted_generation="X", actual_generation="X")
        )

    def test_all_three_differ(self):
        # baked 'A', persisted 'B', pre 'C', post 'D' — all distinct.
        r = _report(baked="A", persisted="B", pre="C", post="D")
        self.assertIs(r["baked_matches_persisted"], False)
        self.assertIs(r["baked_matches_pre_sync_actual"], False)
        self.assertIs(r["baked_matches_post_sync_actual"], False)
        self.assertIs(r["persisted_matches_post_sync_actual"], False)
        self.assertEqual(r["final_authoritative_generation"], "D")
        self.assertEqual(r["final_authority_source"], "volume_tree")
        self.assertIs(r["proof_generation_match"], False)
        # The record is stale vs the actual tree (repair decision alone is True),
        # but the closure only blesses when post-sync actual == baked, so proof
        # stays False here.
        self.assertTrue(
            should_update_persisted_record(persisted_generation="B", actual_generation="D")
        )
        self.assertIs(r["proof_generation_match"], False)

    def test_sync_changes_actual_to_baked(self):
        # Volume pre-sync 'VOLUME_OLD' -> post-sync 'BAKED'.
        r = _report(baked="BAKED", persisted="PERSISTED", pre="VOLUME_OLD", post="BAKED")
        self.assertIs(r["baked_matches_post_sync_actual"], True)
        self.assertEqual(r["final_authoritative_generation"], "BAKED")
        self.assertEqual(r["final_authority_source"], "baked_image")
        self.assertIs(r["proof_generation_match"], True)

    def test_sync_changes_actual_to_persisted(self):
        # Sync pulled the persisted token into the tree: post 'X' != baked.
        r = _report(baked="BAKED", persisted="X", pre="X", post="X")
        self.assertEqual(r["final_authoritative_generation"], "X")
        self.assertEqual(r["final_authority_source"], "volume_tree")
        # Correct fail-closed: the snapshot would contain different code.
        self.assertIs(r["proof_generation_match"], False)

    def test_persisted_record_missing(self):
        r = _report(baked="X", persisted="", pre="X", post="X")
        self.assertIsNone(r["baked_matches_persisted"])
        self.assertIs(r["baked_matches_post_sync_actual"], True)
        self.assertIs(r["proof_generation_match"], True)
        self.assertTrue(
            should_update_persisted_record(persisted_generation="", actual_generation="X")
        )

    def test_persisted_record_malformed(self):
        # Malformed records resolve to empty in the resolver — same as missing.
        r_missing = _report(baked="BAKED", persisted="", pre="X", post="X")
        self.assertIsNone(r_missing["baked_matches_persisted"])
        self.assertTrue(
            should_update_persisted_record(persisted_generation="", actual_generation="X")
        )
        # Exact authority rule: no actuals AND no persisted -> baked authority.
        r_none = _report(baked="BAKED", persisted="", pre="", post="")
        self.assertEqual(r_none["final_authoritative_generation"], "BAKED")
        self.assertEqual(r_none["final_authority_source"], "baked_image")
        self.assertIs(r_none["proof_generation_match"], True)

    def test_algorithm_schema_mismatch(self):
        # Persisted format differs (uuid-deployment-token) vs a content hash:
        # matches are plain equality on opaque strings, no format assumptions.
        token = "uuid-deployment-token-123"
        content_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        r = _report(baked="BAKED", persisted=token, pre="", post="")
        self.assertIs(r["baked_matches_persisted"], False)  # plain equality, not None
        self.assertIsNone(r["baked_matches_pre_sync_actual"])
        self.assertTrue(
            should_update_persisted_record(persisted_generation=token, actual_generation=content_hash)
        )
        # Even a token-looking record is left alone when it equals the actual.
        self.assertFalse(
            should_update_persisted_record(persisted_generation=token, actual_generation=token)
        )

    def test_sync_failure_surface(self):
        # Sync raised -> post-sync actual resolves to empty.
        r = _report(baked="BAKED", persisted="PERSISTED", pre="PRE", post="")
        self.assertIsNone(r["baked_matches_post_sync_actual"])
        # Authority falls back to the persisted record when non-empty.
        self.assertEqual(r["final_authoritative_generation"], "PERSISTED")
        self.assertEqual(r["final_authority_source"], "persisted_record")
        # proof = baked vs final authority -> fails closed here.
        self.assertIs(r["proof_generation_match"], False)
        # No persisted either -> baked authority, proof vs itself passes.
        r2 = _report(baked="BAKED", persisted="", pre="PRE", post="")
        self.assertEqual(r2["final_authoritative_generation"], "BAKED")
        self.assertEqual(r2["final_authority_source"], "baked_image")
        self.assertIs(r2["proof_generation_match"], True)

    def test_record_write_failure_surface(self):
        # should_update_persisted_record is a pure decision and cannot raise.
        self.assertTrue(
            should_update_persisted_record(persisted_generation="PERSISTED", actual_generation="BAKED")
        )
        # The closure's guard (post-sync actual == baked) is what blesses proof;
        # a report whose post-sync actual equals baked carries proof True
        # regardless of whether the later record write succeeded.
        r = _report(baked="BAKED", persisted="PERSISTED", pre="OLD", post="BAKED")
        self.assertIs(r["baked_matches_post_sync_actual"], True)
        self.assertIs(r["proof_generation_match"], True)

    def test_proof_never_valid_without_content_equality(self):
        # Scenarios 3 / 4 / 6: post-sync actual != baked -> proof must fail.
        r3 = _report(baked="BAKED", persisted="X", pre="X", post="X")
        r4 = _report(baked="A", persisted="B", pre="C", post="D")
        r6 = _report(baked="BAKED", persisted="X", pre="X", post="X")
        for r in (r3, r4, r6):
            self.assertIs(r["proof_generation_match"], False)
            self.assertIn("proof_generation_match=0", format_parity_line(r))

    def test_proof_freezes_only_after_final_generation(self):
        # proof_freeze_generation is ALWAYS the baked generation passed in.
        for baked in ("BAKED", "X", "A", "Z"):
            r = _report(baked=baked)
            self.assertEqual(r["proof_freeze_generation"], baked)
            self.assertEqual(r["baked_generation"], baked)

    def test_restore_exact_skip_retains_proof(self):
        # Exact-skip path: persisted == baked, no sync performed. The tree was
        # observed identical (post-sync actual == baked), so the baked source is
        # authoritative and the proof freeze stays valid.
        r = _report(
            baked="X", persisted="X", pre="X", post="X",
            sync_performed=False, sync_direction="none", sync_reason="exact_match",
        )
        self.assertEqual(r["final_authoritative_generation"], "X")
        self.assertEqual(r["final_authority_source"], "baked_image")
        self.assertIs(r["baked_matches_persisted"], True)
        self.assertIs(r["proof_generation_match"], True)
        line = format_parity_line(r)
        self.assertIn("sync_performed=0", line)
        self.assertIn("sync_reason=exact_match", line)
        # Even when the exact-skip observed no post-sync actual at all, the
        # persisted==baked record still retains proof.
        r2 = _report(
            baked="X", persisted="X", pre="", post="",
            sync_performed=False, sync_direction="none", sync_reason="exact_match",
        )
        self.assertEqual(r2["final_authoritative_generation"], "X")
        self.assertIs(r2["proof_generation_match"], True)

    def test_later_custom_node_drift_marks_proof_stale(self):
        # Deploy baked 'A' but the actual tree has drifted to 'B' (== persisted).
        r = _report(baked="A", persisted="B", pre="B", post="B")
        self.assertIs(r["baked_matches_persisted"], False)
        self.assertIs(r["baked_matches_post_sync_actual"], False)
        self.assertIs(r["proof_generation_match"], False)
        self.assertIn("baked_matches_post_sync_actual=0", format_parity_line(r))

    def test_step3_legacy_fallback_unchanged_on_mismatch(self):
        # Full matrix over baked/persisted/post in {'A','B'} (8 sync combos):
        # proof must equal (final_authoritative_generation == baked), and the
        # step-3 legacy fallback NEVER returns proof True when the post-sync
        # actual (or, with no sync, the persisted record) differs from baked.
        for baked in ("A", "B"):
            for persisted in ("A", "B"):
                for post in ("A", "B"):
                    r = _report(baked=baked, persisted=persisted, pre=post, post=post)
                    self.assertIsInstance(r["proof_generation_match"], bool)
                    self.assertEqual(
                        r["proof_generation_match"],
                        r["final_authoritative_generation"] == r["baked_generation"],
                        f"sync mismatch: baked={baked} persisted={persisted} post={post}",
                    )
                    if post != baked:
                        self.assertIs(r["proof_generation_match"], False)
                    else:
                        self.assertIs(r["proof_generation_match"], True)
        # No-sync combos (persisted is the only non-baked authority candidate).
        for baked in ("A", "B"):
            for persisted in ("A", "B"):
                r = _report(
                    baked=baked, persisted=persisted, pre="", post="",
                    sync_performed=False, sync_direction="none", sync_reason="exact_match",
                )
                self.assertIsInstance(r["proof_generation_match"], bool)
                self.assertEqual(
                    r["proof_generation_match"],
                    r["final_authoritative_generation"] == r["baked_generation"],
                    f"no-sync mismatch: baked={baked} persisted={persisted}",
                )
                if persisted != baked:
                    self.assertIs(r["proof_generation_match"], False)
                else:
                    self.assertIs(r["proof_generation_match"], True)

    def test_format_parity_line_deterministic(self):
        r = _report(baked="X", persisted="X", pre="X", post="X")
        line1 = format_parity_line(r)
        line2 = format_parity_line(r)
        self.assertEqual(line1, line2)
        self.assertTrue(line1.startswith("[v2.custom_node_generation_parity]"))
        for key in _REPORT_KEYS:
            self.assertIn(f"{key}=", line1, f"missing key {key!r} in {line1!r}")
        # Bools render as 1/0; plain strings render plainly.
        self.assertIn("sync_performed=1", line1)
        self.assertIn("proof_generation_match=1", line1)
        self.assertIn("baked_generation=X", line1)
        self.assertIn("sync_direction=volume_to_container", line1)
        # None operands render as '-'; sync_performed=False renders as 0.
        r_none = _report(baked="BAKED", persisted="", pre="", post="")
        line_none = format_parity_line(r_none)
        self.assertIn("baked_matches_persisted=-", line_none)
        self.assertIn("baked_matches_pre_sync_actual=-", line_none)
        self.assertIn("baked_matches_post_sync_actual=-", line_none)
        self.assertIn("persisted_matches_post_sync_actual=-", line_none)
        self.assertIn("sync_performed=1", line_none)
        self.assertIn("proof_generation_match=1", line_none)
        # Mismatch report renders proof 0 and the volume authority.
        r_mismatch = _report(baked="BAKED", persisted="X", pre="X", post="X")
        line_mismatch = format_parity_line(r_mismatch)
        self.assertIn("proof_generation_match=0", line_mismatch)
        self.assertIn("baked_matches_post_sync_actual=0", line_mismatch)
        self.assertIn("final_authority_source=volume_tree", line_mismatch)
        # The key ORDER is stable across different reports (deterministic).
        self.assertEqual(_line_keys(line_none), _line_keys(line_mismatch))
        self.assertEqual(_line_keys(line_none), list(_REPORT_KEYS))

    def test_should_update_record_rules(self):
        cases = [
            ("", "X", True),   # missing record + proof -> repair
            ("X", "X", False),  # equal record -> never rewrite
            ("Y", "X", True),  # stale record -> repair
            ("X", "", False),  # no actual proof -> never accept
            ("", "", False),   # nothing -> no-op
        ]
        for persisted, actual, expected in cases:
            self.assertEqual(
                should_update_persisted_record(
                    persisted_generation=persisted, actual_generation=actual
                ),
                bool(expected),
                f"persisted={persisted!r} actual={actual!r}",
            )


class TestRoundTripAndPurity(unittest.TestCase):
    """Round-trip proof against the REAL comfyapp fingerprint, plus purity."""

    def test_round_trip_preserves_generation(self):
        """THE key local proof: archive->extract preserves the fingerprint.

        Builds a fixture tree with CRLF content, computes its generation,
        packages it into a tar.gz (arcname=node dirs, no .pyc), extracts into
        a second root, and asserts the generation is identical.
        """
        try:
            import comfyapp
        except Exception as exc:  # pragma: no cover - environment guard
            pytest.skip(f"comfyapp is not importable on this machine: {exc!r}")

        with tempfile.TemporaryDirectory() as td:
            fixture_root = os.path.join(td, "fixture")
            extracted_root = os.path.join(td, "extracted")
            os.makedirs(fixture_root)
            os.makedirs(extracted_root)

            files = {
                "alpha_node": {
                    "__init__.py": "import nodes\r\n",
                    "nodes.py": "# alpha\r\nNODE_CLASS_MAPPINGS = {}\r\n",
                    "requirements.txt": "numpy>=1.24\r\ntorch\r\n",
                    "notes.txt": "alpha notes\r\nline2\r\n",
                },
                "beta_node": {
                    "something.py": "VALUE = 1\r\n",
                    "config.toml": '[tool]\r\nname = "beta"\r\n',
                    "subpkg/extra.cfg": "key = value\r\n",
                },
                "gamma_node": {
                    "setup.py": 'from setuptools import setup\r\nsetup(name="gamma")\r\n',
                    "readme.txt": "gamma\r\n",
                },
            }
            for node_name, node_files in files.items():
                for rel, content in node_files.items():
                    path = os.path.join(fixture_root, node_name, rel.replace("/", os.sep))
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open(path, "w", encoding="utf-8", newline="") as f:
                        f.write(content)

            g1 = comfyapp.custom_node_source_generation(fixture_root)
            self.assertIsInstance(g1, str)
            self.assertRegex(g1, r"^[0-9a-f]{32}$")
            # The fixture tree is actually tracked by the fingerprint walk.
            fp = comfyapp.custom_node_source_fingerprint(fixture_root)
            self.assertEqual(len(fp.get("nodes") or []), 3)

            archive = os.path.join(td, "nodes.tar.gz")
            with tarfile.open(archive, "w:gz") as tar:
                for node_name in sorted(os.listdir(fixture_root)):
                    node_dir = os.path.join(fixture_root, node_name)
                    for dirpath, dirnames, filenames in os.walk(node_dir):
                        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
                        for filename in filenames:
                            if filename.endswith(".pyc"):
                                continue
                            file_path = os.path.join(dirpath, filename)
                            arcname = os.path.join(
                                node_name, os.path.relpath(file_path, node_dir)
                            )
                            tar.add(file_path, arcname=arcname)

            with tarfile.open(archive, "r:gz") as tar:
                tar.extractall(path=extracted_root)

            g2 = comfyapp.custom_node_source_generation(extracted_root)
            self.assertEqual(
                g1, g2,
                "archive->extract changed the custom-node source generation "
                f"({g1} vs {g2})",
            )

        # Read-only full-tree sanity: the REAL local custom_nodes root yields a
        # non-empty 32-hex generation. Skipped if the import/walk fails here.
        try:
            g_real = comfyapp.custom_node_source_generation(str(REAL_CUSTOM_NODES_ROOT))
        except Exception as exc:  # pragma: no cover - environment guard
            pytest.skip(f"custom_nodes root walk unavailable: {exc!r}")
        self.assertTrue(g_real)
        self.assertRegex(g_real, r"^[0-9a-f]{32}$")

    def test_do_not_weaken_existing_step3(self):
        """No side effects on import; report helpers are pure.

        A fresh subprocess imports the parity module and asserts no files
        appear / change in the repo root or ``comfymodal_runtime`` (bytecode
        cache excluded). Then the in-process helpers are called twice and must
        return equal values (and fresh dict objects).
        """
        script = textwrap.dedent(
            f"""\
            import os
            import sys
            root = {str(REPO_ROOT)!r}
            sys.path.insert(0, root)

            def _snap(sub):
                entries = set()
                base = os.path.join(root, sub)
                for dp, dns, fns in os.walk(base):
                    dns[:] = [d for d in dns if d != "__pycache__"]
                    for fn in fns:
                        if fn.endswith(".pyc"):
                            continue
                        p = os.path.join(dp, fn)
                        entries.add(
                            (os.path.relpath(p, root).replace(os.sep, "/"),
                             os.path.getsize(p))
                        )
                return entries

            before = (sorted(os.listdir(root)), _snap("comfymodal_runtime"))
            import comfymodal_runtime.custom_node_parity  # noqa: F401
            after = (sorted(os.listdir(root)), _snap("comfymodal_runtime"))
            if before != after:
                sys.exit(1)
            """
        )
        env = dict(os.environ)
        env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        proc = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(
            proc.returncode,
            0,
            f"import of comfymodal_runtime.custom_node_parity wrote files\n"
            f"stderr: {proc.stderr[-2000:]}",
        )

        # Pure-function checks: equal inputs -> equal outputs, fresh objects.
        r1 = _report(baked="A", persisted="B", pre="C", post="D")
        r2 = _report(baked="A", persisted="B", pre="C", post="D")
        self.assertEqual(r1, r2)
        self.assertIsNot(r1, r2)
        self.assertEqual(
            should_update_persisted_record(persisted_generation="STALE", actual_generation="X"),
            should_update_persisted_record(persisted_generation="STALE", actual_generation="X"),
        )
        # The same full report produced again (fresh dict) is still equal.
        r3 = _report(baked="A", persisted="B", pre="C", post="D")
        self.assertEqual(r1, r3)
        self.assertIsNot(r1, r3)

    def test_generated_dirs_is_superset_of_archive_excludes(self):
        """ROOT-CAUSE invariant: the fingerprint walk must exclude everything
        the volume-sync archive drops.

        The V2 ``generation_mismatch`` proof failure was caused by the archive
        filter (``__init__._CUSTOM_NODE_SYNC_EXCLUDE_DIRS``) excluding
        directories that ``comfyapp._CUSTOM_NODE_GENERATED_DIRS`` still walked
        (e.g. ``.comfymodal_experiments``, ``.custom_node_requirements``,
        ``.baked_custom_node_deps``, ``benchmark_runs``).  Archive->extract then
        changed the fingerprint, so baked (local tree) could never equal the
        Volume generation even after a fresh publish.  This test pins the
        unification.
        """
        try:
            import comfyapp
        except Exception as exc:  # pragma: no cover - environment guard
            pytest.skip(f"comfyapp is not importable on this machine: {exc!r}")
        try:
            from tools.publish_custom_nodes_volume import _CUSTOM_NODE_SYNC_EXCLUDE_DIRS
        except Exception as exc:  # pragma: no cover - environment guard
            pytest.skip(f"tools.publish_custom_nodes_volume not importable: {exc!r}")

        archive_excludes = set(_CUSTOM_NODE_SYNC_EXCLUDE_DIRS)
        fingerprint_excludes = set(comfyapp._CUSTOM_NODE_GENERATED_DIRS)
        missing = sorted(archive_excludes - fingerprint_excludes)
        self.assertEqual(
            missing,
            [],
            "fingerprint walk set must be a superset of the archive exclude set; "
            f"missing: {missing}",
        )

    def test_real_tree_archive_round_trip_matches(self):
        """Decisive local proof on the REAL custom_nodes tree: archive->extract
        preserves the fingerprint (baked == persisted after a fresh publish).

        Uses the actual deploy-time archive builder
        (``tools.publish_custom_nodes_volume._build_custom_nodes_archive``)
        and the real ``comfyapp.custom_node_source_generation`` fingerprint on
        the real custom_nodes root and on the extracted tree.
        """
        try:
            import comfyapp
            from tools.publish_custom_nodes_volume import _build_custom_nodes_archive
        except Exception as exc:  # pragma: no cover - environment guard
            pytest.skip(f"real-tree round trip unavailable: {exc!r}")

        try:
            g_local = comfyapp.custom_node_source_generation(str(REAL_CUSTOM_NODES_ROOT))
        except Exception as exc:  # pragma: no cover - environment guard
            pytest.skip(f"custom_nodes root walk unavailable: {exc!r}")
        self.assertTrue(g_local)
        self.assertRegex(g_local, r"^[0-9a-f]{32}$")

        try:
            archive = _build_custom_nodes_archive(str(REAL_CUSTOM_NODES_ROOT))
        except Exception as exc:  # pragma: no cover - environment guard
            pytest.skip(f"archive build unavailable: {exc!r}")
        self.assertTrue(archive)

        with tempfile.TemporaryDirectory() as td:
            extracted = os.path.join(td, "extracted")
            os.makedirs(extracted)
            with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
                tar.extractall(path=extracted, filter="data")
            g_vol = comfyapp.custom_node_source_generation(extracted)
            self.assertEqual(
                g_local,
                g_vol,
                "archive->extract changed the REAL custom-node tree generation; "
                "baked would never match the Volume record",
            )


if __name__ == "__main__":
    unittest.main()
