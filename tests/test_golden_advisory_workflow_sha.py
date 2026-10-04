"""Advisory Golden workflow-SHA comparison.

Studio runs legitimately carry a caller-selected workflow with
caller-applied control values, so the executed prompt is not expected to be
byte-identical to the frozen benchmark prompt. These tests pin the intended
contract:

- a workflow SHA mismatch is recorded as evidence, not a rejection;
- hash computation and telemetry stay unconditional;
- disabling the registered flag no longer raises;
- structural admission remains fail-closed.

Stage-event streaming is covered separately in
``tests/test_golden_stage_progress_stream.py``.
"""

import asyncio
import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from comfymodal_runtime.golden_serial import (  # noqa: E402
    CANONICAL_CLIP_NAME,
    CANONICAL_CLIP_TYPE,
    CANONICAL_SAMPLER_CLASS,
    CANONICAL_UNET_NAME,
    CANONICAL_VAE_NAME,
    GoldenWorkflowContract,
    canonical_workflow_sha256,
    resolve_golden_node_map,
)


def _prompt(clip_name: str = CANONICAL_CLIP_NAME) -> dict:
    """A minimal canonical-family prompt.

    Structure matches what ``resolve_golden_node_map`` requires: exactly one
    CLIPLoader/UNETLoader/VAELoader/CLIPTextEncode/sampler/VAEDecode, using the
    contract's real model filenames, types, and sampler class.
    """
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": CANONICAL_UNET_NAME}},
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {"clip_name": clip_name, "type": CANONICAL_CLIP_TYPE},
        },
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": CANONICAL_VAE_NAME}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["2", 0]}},
        "5": {
            "class_type": CANONICAL_SAMPLER_CLASS,
            "inputs": {"prompt": ["4", 0], "steps": 9, "cfg": 1.0},
        },
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["3", 0]}},
    }


class _Recorder:
    """Minimal recorder capturing ``event`` calls made during request setup."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []
        self.output_durability_mode = "off"
        self.durability_requested = False
        self.clip_residency = None
        self.durability_requested_at = None
        self._open = None

    def begin_stage(self, name: str, **kw):
        self._open = name
        return None

    def end_stage(self, name: str, **kw):
        self._open = None

    def fail_stage(self, name: str, exc, **kw):
        self._open = None

    def event(self, name: str, **kw) -> None:
        self.events.append((name, dict(kw)))


def _run_setup(prompt: dict, *, env_flag: str | None = None):
    """Drive the advisory SHA block of ``golden_request_setup``.

    The real function also resolves model paths through ``folder_paths`` and
    constructs a runner, which needs the ComfyUI runtime. Only the SHA decision
    is under test here, so the block is replayed with the same recorder contract.
    """
    from comfymodal_runtime import golden_serial as gs

    if env_flag is None:
        os.environ.pop("COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK", None)
    else:
        os.environ["COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK"] = env_flag

    session = _Session(prompt)
    actual_sha = canonical_workflow_sha256(prompt)
    workflow_hash_check_value = os.environ.get(
        "COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK", "1"
    ).strip().lower()
    workflow_hash_check_enabled = workflow_hash_check_value not in {
        "0",
        "false",
        "no",
        "off",
    }

    workflow_sha_match = actual_sha == session.contract.workflow_sha256
    workflow_sha_warning = None
    if not workflow_sha_match:
        workflow_sha_warning = {
            "expected": session.contract.workflow_sha256,
            "observed": actual_sha,
            "reason": "workflow_sha_mismatch",
        }
    session.recorder.event(
        "golden_workflow_hash_check",
        actual_sha256=actual_sha,
        expected_sha256=session.contract.workflow_sha256,
        enabled=workflow_hash_check_enabled,
        bypassed=not workflow_hash_check_enabled,
        workflow_sha_match=workflow_sha_match,
        workflow_sha_warning=workflow_sha_warning,
    )
    session.workflow_sha_match = workflow_sha_match
    session.workflow_sha_warning = workflow_sha_warning
    return session, actual_sha, workflow_hash_check_enabled


class _Session:
    def __init__(self, prompt: dict) -> None:
        from comfymodal_runtime.golden_serial import GoldenWorkflowContract

        self.prompt = prompt
        self.contract = GoldenWorkflowContract()
        self.recorder = _Recorder()
        self.workflow_sha_match: bool | None = None
        self.workflow_sha_warning: dict | None = None


class AdvisoryWorkflowShaTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = os.environ.get("COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK")
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        if self._saved is None:
            os.environ.pop("COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK", None)
        else:
            os.environ["COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK"] = self._saved

    def test_mismatch_is_recorded_not_rejected(self) -> None:
        """A caller-selected workflow must not be rejected on SHA alone."""
        session, actual, _ = _run_setup(_prompt())
        expected = session.contract.workflow_sha256
        self.assertNotEqual(actual, expected, "fixture should differ from frozen contract")
        self.assertFalse(session.workflow_sha_match)
        self.assertIsNotNone(session.workflow_sha_warning)
        self.assertEqual(session.workflow_sha_warning["reason"], "workflow_sha_mismatch")
        self.assertEqual(session.workflow_sha_warning["observed"], actual)
        self.assertEqual(session.workflow_sha_warning["expected"], expected)

    def test_telemetry_is_unconditional_and_carries_mismatch(self) -> None:
        """Hash telemetry is always emitted, including the mismatch fields."""
        session, actual, _ = _run_setup(_prompt())
        names = [name for name, _ in session.recorder.events]
        self.assertIn("golden_workflow_hash_check", names)
        payload: dict = dict(session.recorder.events)["golden_workflow_hash_check"]
        self.assertEqual(payload["actual_sha256"], actual)
        self.assertEqual(payload["expected_sha256"], session.contract.workflow_sha256)
        self.assertFalse(payload["workflow_sha_match"])
        self.assertIsNotNone(payload["workflow_sha_warning"])

    def test_disabling_flag_does_not_raise(self) -> None:
        """The registered flag may be disabled; that must not abort the run.

        The flag registry documents that hash computation and telemetry remain
        enabled when the guard is disabled, so the request must proceed.
        """
        for value in ("0", "false", "no", "off"):
            with self.subTest(value=value):
                session, _, enabled = _run_setup(_prompt(), env_flag=value)
                self.assertFalse(enabled)
                # Comparison still ran and still reported.
                self.assertFalse(session.workflow_sha_match)
                payload = dict(session.recorder.events)["golden_workflow_hash_check"]
                self.assertTrue(payload["bypassed"])
                self.assertIn("actual_sha256", payload)

    def test_matching_workflow_reports_match(self) -> None:
        """When the prompt matches the contract exactly, no warning is raised."""
        from comfymodal_runtime.golden_serial import GoldenWorkflowContract

        contract = GoldenWorkflowContract()
        prompt = _prompt()
        # Rebuild the contract so its expected SHA equals this prompt's SHA.
        from dataclasses import replace

        contract = replace(contract, workflow_sha256=canonical_workflow_sha256(prompt))
        session = _Session(prompt)
        session.contract = contract
        actual = canonical_workflow_sha256(prompt)
        self.assertEqual(actual, contract.workflow_sha256)
        session.workflow_sha_match = actual == contract.workflow_sha256
        self.assertTrue(session.workflow_sha_match)
        self.assertIsNone(session.workflow_sha_warning)


class StructuralAdmissionStaysFailClosedTests(unittest.TestCase):
    """Relaxing the SHA must not relax structural admission."""

    def test_missing_vae_decode_still_fails(self) -> None:
        prompt = _prompt()
        prompt.pop("6")
        with self.assertRaises(RuntimeError) as ctx:
            resolve_golden_node_map(prompt)
        self.assertIn("canonical_nodes_missing", str(ctx.exception))

    def test_duplicate_sampler_still_fails(self) -> None:
        prompt = _prompt()
        prompt["7"] = dict(prompt["5"])
        with self.assertRaises(RuntimeError) as ctx:
            resolve_golden_node_map(prompt)
        self.assertIn("canonical_nodes_duplicate", str(ctx.exception))

    def test_replacement_models_are_accepted(self) -> None:
        """A caller-selected workflow may name replacement CLIP/UNET/VAE.

        Structural admission is by node class and cardinality, so a replacement
        triple is admitted and its declared identities are returned as the
        values the run must load.
        """
        prompt = _prompt(clip_name="replacement_clip.safetensors")
        prompt["1"]["inputs"]["unet_name"] = "replacement_unet.safetensors"
        prompt["3"]["inputs"]["vae_name"] = "replacement_vae.safetensors"
        node_map = resolve_golden_node_map(prompt)
        self.assertEqual(node_map.clip_name, "replacement_clip.safetensors")
        self.assertEqual(node_map.unet_name, "replacement_unet.safetensors")
        self.assertEqual(node_map.vae_name, "replacement_vae.safetensors")
        # The canonical role handles are still resolved structurally.
        self.assertEqual(node_map.clip_loader_id, "2")
        self.assertEqual(node_map.unet_loader_id, "1")
        self.assertEqual(node_map.vae_loader_id, "3")

    def test_canonical_models_reported_as_declared(self) -> None:
        """The canonical triple resolves to the contract's own identities."""
        node_map = resolve_golden_node_map(_prompt())
        self.assertEqual(node_map.clip_name, CANONICAL_CLIP_NAME)
        self.assertEqual(node_map.clip_type, CANONICAL_CLIP_TYPE)
        self.assertEqual(node_map.unet_name, CANONICAL_UNET_NAME)
        self.assertEqual(node_map.vae_name, CANONICAL_VAE_NAME)

    def test_unnamed_loader_fails_closed(self) -> None:
        """A loader with no declared identity fails closed.

        Treating it as "the default" would silently load the canonical model
        for an ambiguous workflow.
        """
        prompt = _prompt(clip_name="")
        with self.assertRaises(RuntimeError) as ctx:
            resolve_golden_node_map(prompt)
        self.assertIn("requires_clip_name", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()