"""source-probe is diagnostic tooling and must never gate anything.

It used to be an admission requirement in five places:

  1. ``v2ctl run`` refused to start without probe evidence on the receipt
  2. ``v2ctl gate`` required the same
  3. ``v2ctl confirm`` required the same
  4. ``golden status`` reported not-ready unless source_identity_status was
     "verified", which only the probe ever set
  5. ``golden profile`` aborted the whole experiment when the probe did not pass

Plus the probe flipped ``source_identity_status`` to "verified" on the deployment
manifest, so a later run's validity depended on a debug command having been run.

All of that stood in for one question, now answered directly: the serving request
reports the deploy_id of the deployment that served it, and acceptance compares
that against the expected id. A probe can only describe the mounted filesystem of
a container it starts, which is weaker evidence -- it cannot see what code a
restored snapshot is executing.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.fast_unit

CLI = Path(__file__).resolve().parents[1] / "tools" / "v2_control" / "cli.py"
VALIDATION = (
    Path(__file__).resolve().parents[1] / "tools" / "v2_control" / "validation.py"
)


def _functions(path: Path) -> dict[str, ast.FunctionDef]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    }


def test_no_run_path_requires_source_probe_evidence():
    """run, gate and confirm must not demand a probe receipt."""
    for path in (CLI, VALIDATION):
        source = path.read_text(encoding="utf-8")
        assert "require_source_probe_evidence" not in source, (
            "%s still calls require_source_probe_evidence" % path.name
        )


def test_probe_does_not_flip_deployment_validity():
    """The probe must not write a verdict back into the deployment ledger."""
    source = CLI.read_text(encoding="utf-8")
    fn = _functions(CLI)["cmd_source_probe"]
    body = ast.get_source_segment(source, fn) or ""
    assert 'manifest["source_identity_status"] = "verified"' not in body
    assert "source_identity_status=verified" not in body


def test_probe_failure_does_not_abort_the_experiment():
    """golden profile must continue past a failed probe."""
    source = CLI.read_text(encoding="utf-8")
    fn = _functions(CLI)["cmd_golden_profile"]
    body = ast.get_source_segment(source, fn) or ""
    assert "RESULT=PASS" in body, "the probe result should still be inspected"
    # The abort-on-probe-failure path must be gone.
    assert "so a run now would not measure this source" not in body
    assert "ERROR: source-probe did not report" not in body


def test_golden_status_does_not_require_verified_source_identity():
    source = CLI.read_text(encoding="utf-8")
    fn = _functions(CLI)["cmd_golden_status"]
    body = ast.get_source_segment(source, fn) or ""
    ready_expr = body.split('out["ready"]', 1)[-1].split(")", 1)[0]
    assert 'source_identity_status"] == "verified"' not in ready_expr


def test_source_probe_is_reachable_under_debug():
    """The command exists under `debug`, with the old spelling as an alias."""
    from tools.v2_control.cli import build_parser

    parser = build_parser()
    assert parser.parse_args(["debug"]).func.__name__ == "cmd_debug"
    assert (
        parser.parse_args(["debug", "source-probe"]).func.__name__
        == "cmd_source_probe"
    )
    # Existing saved command lines keep working.
    assert parser.parse_args(["source-probe"]).func.__name__ == "cmd_source_probe"


def test_debug_namespace_documents_that_it_cannot_admit():
    source = CLI.read_text(encoding="utf-8")
    body = ast.get_source_segment(source, _functions(CLI)["cmd_debug"]) or ""
    assert "can make a deployment or a result valid" in body


def test_probe_help_does_not_claim_to_prove_executing_code():
    flat = " ".join(CLI.read_text(encoding="utf-8").split())
    assert "Does not gate deploy/run" in flat
    assert "establish which code served a request" in flat


def test_deploy_id_is_the_acceptance_authority_instead():
    """The replacement for the probe gate is present and enforcing."""
    source = VALIDATION.read_text(encoding="utf-8")
    tree = ast.parse(source)
    structural = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "StructuralValidator"
    )
    fn = next(
        node
        for node in structural.body
        if isinstance(node, ast.FunctionDef) and node.name == "validate"
    )
    body = ast.get_source_segment(source, fn) or ""
    assert "deploy_id mismatch" in body
    assert "served_deploy_id" in body and "expected_deploy_id" in body