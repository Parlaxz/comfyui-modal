"""FAST_UNIT tests for the Studio Phase 9 Guidance backend (studio_guidance.py).

All graphs, node types, checkpoints, and model digests are synthetic.  No
model weights are downloaded; file hashing covers only tiny temp files.
"""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
import re
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tests import _test_env  # noqa: F401  (hide real ComfyUI from sys.path)

import studio_guidance
import studio_models
from studio_guidance import (
    ADAPTERS,
    GUIDANCE_MODES,
    GuidanceMappingStore,
    GuidanceRefusal,
    apply_guidance,
    attach_guidance_provenance,
    build_guided_execution_copy,
    discover_anchors,
    guidance_provenance,
    is_refusal,
    resolve_anchors,
    resolve_model_identity,
    validate_guided_copy,
    validate_mapping,
)
from studio_workflow_manifest import graph_hash

# ── Synthetic fixtures ─────────────────────────────────────────────────────

LOADER_CLS = "SynthControlLoader"
APPLY_CLS = "SynthControlApply"
PREPROC_CLS = "SynthEdgePreprocessor"

OBJECT_INFO = {
    LOADER_CLS: {"input": {"required": {"control_net_name": ("STRING", {})}}},
    APPLY_CLS: {
        "input": {
            "required": {
                "conditioning": ("CONDITIONING", {}),
                "control_net": ("CONTROL_NET", {}),
                "image": ("IMAGE", {}),
                "strength": ("FLOAT", {"default": 1.0}),
                "start_percent": ("FLOAT", {"default": 0.0}),
                "end_percent": ("FLOAT", {"default": 1.0}),
            }
        },
        "output": ["CONDITIONING"],
    },
    PREPROC_CLS: {"input": {"required": {"image": ("IMAGE", {})}}},
    "SynthModelLoader": {"input": {"required": {"ckpt_name": ("STRING", {})}}},
    "SynthClipEncode": {"input": {"required": {"text": ("STRING", {})}}},
    "SynthSampler": {"input": {"required": {}}},
    "SynthLoadImage": {"input": {"required": {}}},
    "SynthEmptyLatent": {"input": {"required": {}}},
}


def make_workflow() -> dict:
    return {
        "1": {"class_type": "SynthModelLoader", "inputs": {"ckpt_name": "base.safetensors"}},
        "2": {
            "class_type": "SynthSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["3", 0],
                "negative": ["4", 0],
                "latent_image": ["5", 0],
            },
        },
        "3": {"class_type": "SynthClipEncode", "inputs": {"text": "a cat"}},
        "4": {"class_type": "SynthClipEncode", "inputs": {"text": "blurry"}},
        "5": {"class_type": "SynthEmptyLatent", "inputs": {}},
        "6": {"class_type": "SynthLoadImage", "inputs": {}},
    }


def make_mapping(sha: str, mode: str = "canny") -> dict:
    return {
        "model_sha256": sha,
        "mode": mode,
        "mechanism": "CONTROLNET_CONDITIONING",
        "controller": {
            "checkpoint": "guide-controller-v1.safetensors",
            "folder": "controlnet",
            "checkpoint_sha256": "abc123",
            "source_url": "https://example.invalid/controller",
            "license": "permissive-example",
        },
        "nodes": {
            "loader": LOADER_CLS,
            "apply": APPLY_CLS,
            "preprocessor": PREPROC_CLS,
        },
        "conditioning": {"strength": 0.7, "start": 0.0, "end": 0.8},
        "suggest": {"family": "hint-only", "display_filename": "base.safetensors"},
        "evidence": {"workflow_url": "https://example.invalid/workflow"},
        "confirmed": True,
    }


def sha_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class GuidanceTempDir(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.store = GuidanceMappingStore(self.root / "guidance")
        self.models_dir = self.root / "models"
        self.models_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write_model(self, folder: str, filename: str, content: bytes) -> Path:
        path = self.models_dir / folder / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def library_record(self, folder: str, filename: str, path: Path) -> dict:
        digest = sha_of(path.read_bytes())
        return {
            "model_id": f"ml_{filename}",
            "folder": folder,
            "filename": filename,
            "local_path": str(path),
            "hash": digest,
            "size": path.stat().st_size,
        }


# ── 1. Mapping store ───────────────────────────────────────────────────────


class MappingStoreTests(GuidanceTempDir):
    def test_round_trip_and_exact_key(self):
        sha = sha_of(b"weights-a")
        saved = self.store.save(make_mapping(sha))
        self.assertEqual(saved["audit"]["mapping_revision"], 1)
        self.assertTrue(saved["audit"]["confirmed_at"])
        fetched = self.store.get(sha, "canny")
        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertEqual(fetched["controller"]["checkpoint"], "guide-controller-v1.safetensors")
        # Exact key: different digest and different mode both miss.
        self.assertIsNone(self.store.get(sha_of(b"weights-b"), "canny"))
        self.assertIsNone(self.store.get(sha, "depth"))

    def test_revision_bumps_on_resave(self):
        sha = sha_of(b"weights-a")
        first = self.store.save(make_mapping(sha))
        second = self.store.save(make_mapping(sha))
        self.assertEqual(first["audit"]["mapping_revision"], 1)
        self.assertEqual(second["audit"]["mapping_revision"], 2)

    def test_delete(self):
        sha = sha_of(b"weights-a")
        self.store.save(make_mapping(sha))
        self.assertTrue(self.store.delete(sha, "canny"))
        self.assertIsNone(self.store.get(sha, "canny"))
        self.assertFalse(self.store.delete(sha, "canny"))

    def test_unconfirmed_record_rejected(self):
        sha = sha_of(b"weights-a")
        record = make_mapping(sha)
        record["confirmed"] = False
        with self.assertRaises(ValueError):
            self.store.save(record)
        self.assertTrue(validate_mapping(record))

    def test_workflow_id_cannot_select_a_mapping(self):
        # The lookup signature admits only (model_sha256, mode): there is no
        # workflow parameter, so no workflow identity can select a mapping.
        params = list(inspect.signature(GuidanceMappingStore.get).parameters)
        self.assertEqual(params, ["self", "model_sha256", "mode"])
        sha = sha_of(b"weights-a")
        self.store.save(make_mapping(sha))
        self.assertEqual(
            self.store.get(sha, "canny"),
            self.store.get(sha, "canny"),
        )


# ── 2. Identity seam ───────────────────────────────────────────────────────


class IdentityTests(GuidanceTempDir):
    def test_resolves_verified_sha(self):
        path = self.write_model("diffusion_models", "base.safetensors", b"weights-a")
        identity = resolve_model_identity(
            "diffusion_models", "base.safetensors", [self.library_record("diffusion_models", "base.safetensors", path)]
        )
        self.assertFalse(is_refusal(identity))
        assert isinstance(identity, dict)
        self.assertEqual(identity["model_sha256"], sha_of(b"weights-a"))

    def test_rename_same_hash_reuses_mapping(self):
        sha = sha_of(b"weights-a")
        self.store.save(make_mapping(sha))
        first = self.write_model("diffusion_models", "base.safetensors", b"weights-a")
        renamed = self.write_model("diffusion_models", "renamed.safetensors", b"weights-a")
        records = [
            self.library_record("diffusion_models", "base.safetensors", first),
            self.library_record("diffusion_models", "renamed.safetensors", renamed),
        ]
        identity = resolve_model_identity("diffusion_models", "renamed.safetensors", records)
        self.assertFalse(is_refusal(identity))
        assert isinstance(identity, dict)
        # Same digest -> the confirmed mapping is reused under the new name.
        self.assertIsNotNone(self.store.get(identity["model_sha256"], "canny"))

    def test_same_filename_changed_hash_blocked(self):
        path = self.write_model("diffusion_models", "base.safetensors", b"weights-a")
        record = self.library_record("diffusion_models", "base.safetensors", path)
        path.write_bytes(b"weights-a-MODIFIED")
        identity = resolve_model_identity("diffusion_models", "base.safetensors", [record])
        self.assertTrue(is_refusal(identity))
        assert isinstance(identity, GuidanceRefusal)
        self.assertEqual(identity.reason, "model_content_changed")

    def test_unresolvable_refuses_without_guessing(self):
        identity = resolve_model_identity("diffusion_models", "ghost.safetensors", [])
        self.assertTrue(is_refusal(identity))
        assert isinstance(identity, GuidanceRefusal)
        self.assertIn("will not guess from its filename", identity.detail)


# ── 3. Adapter happy path ──────────────────────────────────────────────────


class AdapterHappyPathTests(GuidanceTempDir):
    def _run_hook(self, workflow, sha, mode="canny"):
        path = self.write_model("diffusion_models", "base.safetensors", b"weights-a")
        records = [self.library_record("diffusion_models", "base.safetensors", path)]
        self.store.save(make_mapping(sha, mode))
        return build_guided_execution_copy(
            workflow,
            mode=mode,
            model_folder="diffusion_models",
            model_filename="base.safetensors",
            library_records=records,
            mapping_store=self.store,
            guide_image="6",
            object_info=copy.deepcopy(OBJECT_INFO),
        )

    def test_happy_path_wires_guidance(self):
        sha = sha_of(b"weights-a")
        stored = make_workflow()
        stored_hash = graph_hash(stored)
        result = self._run_hook(stored, sha)
        self.assertFalse(is_refusal(result))
        assert isinstance(result, dict)
        guided = result["workflow"]
        # Stored workflow untouched; only the copy gained four nodes.
        self.assertEqual(graph_hash(stored), stored_hash)
        self.assertEqual(len(guided), len(stored) + 4)
        sampler = guided["2"]["inputs"]
        pos_id, neg_id = sampler["positive"][0], sampler["negative"][0]
        self.assertNotEqual(pos_id, neg_id)
        for apply_id, source in ((pos_id, "3"), (neg_id, "4")):
            apply = guided[apply_id]
            self.assertEqual(apply["class_type"], APPLY_CLS)
            self.assertEqual(apply["inputs"]["conditioning"], [source, 0])
            self.assertEqual(apply["inputs"]["strength"], 0.7)
            self.assertEqual(apply["inputs"]["start_percent"], 0.0)
            self.assertEqual(apply["inputs"]["end_percent"], 0.8)
        pre_ids = [nid for nid, n in guided.items() if n["class_type"] == PREPROC_CLS]
        load_ids = [nid for nid, n in guided.items() if n["class_type"] == LOADER_CLS]
        self.assertEqual(len(pre_ids), 1)
        self.assertEqual(len(load_ids), 1)
        self.assertEqual(guided[pre_ids[0]]["inputs"]["image"], ["6", 0])
        self.assertEqual(
            guided[load_ids[0]]["inputs"]["control_net_name"],
            "guide-controller-v1.safetensors",
        )
        # The mutated copy validates structurally.
        self.assertEqual(validate_guided_copy(guided, OBJECT_INFO), [])
        # Provenance carries generic fields only.
        provenance = result["provenance"]
        self.assertEqual(provenance["mode"], "canny")
        self.assertEqual(provenance["model_sha256"], sha)
        self.assertEqual(provenance["mechanism"], "CONTROLNET_CONDITIONING")
        self.assertEqual(provenance["mapping_revision"], 1)
        self.assertNotIn("refusal_reason", provenance)


# ── 4. Refusal matrix ──────────────────────────────────────────────────────


class RefusalMatrixTests(GuidanceTempDir):
    def _hook(self, workflow, object_info=None, sha=None, mode="canny",
              guide_image="6", binding=None, records=None, save_mapping=True):
        sha = sha or sha_of(b"weights-a")
        path = self.write_model("diffusion_models", "base.safetensors", b"weights-a")
        if records is None:
            records = [self.library_record("diffusion_models", "base.safetensors", path)]
        if save_mapping:
            try:
                self.store.save(make_mapping(sha, mode if mode in GUIDANCE_MODES else "canny"))
            except ValueError:
                pass
        return build_guided_execution_copy(
            workflow,
            mode=mode,
            model_folder="diffusion_models",
            model_filename="base.safetensors",
            library_records=records,
            mapping_store=self.store,
            guide_image=guide_image,
            object_info=copy.deepcopy(OBJECT_INFO if object_info is None else object_info),
            anchor_binding=binding,
        )

    def _assert_refusal(self, result, reason):
        self.assertTrue(is_refusal(result), f"expected refusal, got {result!r}")
        assert isinstance(result, GuidanceRefusal)
        self.assertEqual(result.reason, reason)
        return result

    def test_zero_sampler(self):
        workflow = {"1": {"class_type": "SynthLoadImage", "inputs": {}}}
        self._assert_refusal(discover_anchors(workflow), "no_sampler")

    def test_multi_sampler(self):
        workflow = make_workflow()
        workflow["7"] = copy.deepcopy(workflow["2"])
        refusal = self._assert_refusal(discover_anchors(workflow), "multiple_samplers")
        self.assertEqual(len(refusal.candidates), 2)

    def test_custom_sampler(self):
        workflow = {
            "1": {
                "class_type": "SynthCustomSampler",
                "inputs": {"model": ["9", 0], "conditioning": ["8", 0]},
            },
            "8": {"class_type": "SynthClipEncode", "inputs": {}},
            "9": {"class_type": "SynthModelLoader", "inputs": {}},
        }
        self._assert_refusal(discover_anchors(workflow), "custom_sampler")

    def test_ambiguous_conditioning(self):
        workflow = make_workflow()
        workflow["2"]["inputs"]["positive"] = "a raw string, not a link"
        self._assert_refusal(discover_anchors(workflow), "conditioning_not_found")

    def test_already_controlled(self):
        workflow = make_workflow()
        workflow["9"] = {"class_type": "SynthControlNetApply", "inputs": {}}
        refusal = self._assert_refusal(discover_anchors(workflow), "already_controlled")
        self.assertIn("9", refusal.detail)

    def test_slot_mismatch_names_slot(self):
        bad_info = copy.deepcopy(OBJECT_INFO)
        del bad_info[APPLY_CLS]["input"]["required"]["image"]
        sha = sha_of(b"weights-a")
        workflow = make_workflow()
        result = self._hook(workflow, object_info=bad_info, sha=sha)
        refusal = self._assert_refusal(result, "slot_mismatch")
        self.assertIn("IMAGE", refusal.detail)

    def test_missing_apply_node(self):
        bad_info = {k: v for k, v in OBJECT_INFO.items() if k != APPLY_CLS}
        result = self._hook(make_workflow(), object_info=bad_info)
        refusal = self._assert_refusal(result, "missing_node")
        self.assertIn(APPLY_CLS, refusal.detail)

    def test_missing_preprocessor_node(self):
        bad_info = {k: v for k, v in OBJECT_INFO.items() if k != PREPROC_CLS}
        result = self._hook(make_workflow(), object_info=bad_info)
        self._assert_refusal(result, "missing_node")

    def test_missing_checkpoint(self):
        mapping = make_mapping(sha_of(b"weights-a"))
        del mapping["controller"]["checkpoint"]
        anchors = discover_anchors(make_workflow())
        assert not is_refusal(anchors)
        assert isinstance(anchors, dict)
        result = apply_guidance(make_workflow(), anchors, mapping, "6", OBJECT_INFO)
        self._assert_refusal(result, "controller_checkpoint_missing")

    def test_unknown_mechanism(self):
        mapping = make_mapping(sha_of(b"weights-a"))
        mapping["mechanism"] = "FUTURE_MECHANISM"
        anchors = discover_anchors(make_workflow())
        assert not is_refusal(anchors)
        assert isinstance(anchors, dict)
        result = apply_guidance(make_workflow(), anchors, mapping, "6", OBJECT_INFO)
        self._assert_refusal(result, "unknown_mechanism")

    def test_unresolved_sha_blocks_run(self):
        result = self._hook(make_workflow(), records=[], save_mapping=False)
        self._assert_refusal(result, "identity_unresolvable")

    def test_no_mapping_blocks_run(self):
        result = self._hook(make_workflow(), save_mapping=False)
        self._assert_refusal(result, "no_confirmed_mapping")

    def test_stale_anchor_binding(self):
        workflow = make_workflow()
        binding = {"sampler_id": "2", "graph_hash": "deadbeef"}
        result = self._hook(workflow, binding=binding)
        self._assert_refusal(result, "stale_anchor_binding")

    def test_valid_anchor_binding_passes(self):
        workflow = make_workflow()
        binding = {"sampler_id": "2", "graph_hash": graph_hash(workflow)}
        result = self._hook(workflow, binding=binding)
        self.assertFalse(is_refusal(result))

    def test_unsupported_mode(self):
        result = self._hook(make_workflow(), mode="lineart")
        refusal = self._assert_refusal(result, "unsupported_mode")
        self.assertIn("canny", refusal.detail)

    def test_missing_guide_image(self):
        result = self._hook(make_workflow(), guide_image="999")
        self._assert_refusal(result, "guide_image_missing")


# ── 5. Poisoning: suggest/evidence/license never decide ────────────────────


class PoisoningTests(GuidanceTempDir):
    def test_poisoned_hint_fields_change_nothing(self):
        sha = sha_of(b"weights-a")
        clean = make_mapping(sha)
        poisoned = copy.deepcopy(clean)
        # Poison ONLY the hint/metadata fields the executor must never read
        # for decisions (suggest.*, evidence.*, source_url, license).
        # controller.checkpoint_sha256 is NOT poisoned: it is a generic
        # expected-identity field honestly recorded in provenance.
        poisoned["suggest"] = {"family": "POISON", "display_filename": "poison.safetensors"}
        poisoned["evidence"] = {"workflow_url": "https://poison.invalid"}
        poisoned["controller"]["source_url"] = "https://poison.invalid/x"
        poisoned["controller"]["license"] = "POISON-LICENSE"
        workflow = make_workflow()
        anchors = discover_anchors(workflow)
        assert not is_refusal(anchors)
        assert isinstance(anchors, dict)
        frozen: dict[str, Any] = copy.deepcopy(anchors)
        left = apply_guidance(
            copy.deepcopy(workflow), copy.deepcopy(frozen), clean, "6", OBJECT_INFO
        )
        right = apply_guidance(
            copy.deepcopy(workflow), copy.deepcopy(frozen), poisoned, "6", OBJECT_INFO
        )
        self.assertFalse(is_refusal(left))
        self.assertFalse(is_refusal(right))
        self.assertEqual(
            json.dumps(left, sort_keys=True), json.dumps(right, sort_keys=True)
        )
        # Provenance never carries the poisoned hint fields.
        for prov in (
            guidance_provenance(mode="canny", model_sha256=sha, mapping=clean, anchors=anchors),
            guidance_provenance(mode="canny", model_sha256=sha, mapping=poisoned, anchors=anchors),
        ):
            self.assertNotIn("suggest", prov)
            self.assertNotIn("evidence", prov)
            self.assertNotIn("source_url", prov)
            self.assertNotIn("license", prov)
        self.assertEqual(
            guidance_provenance(mode="canny", model_sha256=sha, mapping=clean, anchors=anchors),
            guidance_provenance(mode="canny", model_sha256=sha, mapping=poisoned, anchors=anchors),
        )


# ── 6. Future model: unseen SHA via manual mapping, no code change ──────────


class FutureModelTests(GuidanceTempDir):
    def test_unseen_sha_manual_mapping_runs(self):
        future_sha = sha_of(b"future-weights-never-seen")
        manual = make_mapping(future_sha, mode="depth")
        manual["evidence"] = {"note": "manual mapping, user-confirmed"}
        self.store.save(manual)
        path = self.write_model("diffusion_models", "future.safetensors", b"future-weights-never-seen")
        records = [self.library_record("diffusion_models", "future.safetensors", path)]
        result = build_guided_execution_copy(
            make_workflow(),
            mode="depth",
            model_folder="diffusion_models",
            model_filename="future.safetensors",
            library_records=records,
            mapping_store=self.store,
            guide_image="6",
            object_info=copy.deepcopy(OBJECT_INFO),
        )
        self.assertFalse(is_refusal(result))
        assert isinstance(result, dict)
        self.assertEqual(result["provenance"]["mode"], "depth")
        self.assertEqual(result["provenance"]["model_sha256"], future_sha)


# ── 7. RUN gate: engaged-but-refused blocks via the shared status path ──────


class RunGateTests(unittest.TestCase):
    def _payload(self, guidance=None):
        payload = {
            "compatibleFeatures": ["txt2img"],
            "nodeBindings": {"prompt": {"kind": "node", "nodeId": "3"}},
            "outputNodeId": "9",
            "apiPromptJson": {"3": {"class_type": "SynthClipEncode", "inputs": {}}},
        }
        if guidance is not None:
            payload["guidance"] = guidance
        return payload

    def test_no_guidance_unchanged(self):
        result = studio_models.normalize_snapshot_payload(self._payload())
        self.assertEqual(result["status"], "runnable")

    def test_engaged_ready_runs(self):
        result = studio_models.normalize_snapshot_payload(
            self._payload({"engaged": True, "ready": True})
        )
        self.assertEqual(result["status"], "runnable")

    def test_engaged_refused_blocks(self):
        result = studio_models.normalize_snapshot_payload(
            self._payload({"engaged": True, "ready": False, "reason": "no_confirmed_mapping"})
        )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["featureStatus"]["txt2img"]["status"], "blocked")
        self.assertIn("no_confirmed_mapping", result["disabledReason"])
        # Blocked is enforced through the SAME aggregate gate.
        self.assertIn("blocked", studio_models._STATUS_PRIORITY)


# ── 8. Hardcoding gate + provenance shape ───────────────────────────────────


class HardcodingGateTests(unittest.TestCase):
    BANNED = [
        "qwen", "flux", "krea", "instantx", "shakker",
        "xlabs", "diffsynth", "bfl", "black.forest",
    ]

    def test_no_family_strings_in_production_code(self):
        source = Path(studio_guidance.__file__).read_text(encoding="utf-8")
        lowered = source.lower()
        for token in self.BANNED:
            self.assertNotIn(
                token, lowered, f"banned family/provider token {token!r} in studio_guidance.py"
            )

    def test_dispatch_is_plain_mechanism_dict(self):
        self.assertEqual(set(ADAPTERS), {"CONTROLNET_CONDITIONING"})
        self.assertEqual(list(GUIDANCE_MODES), ["canny", "depth", "pose"])

    def test_provenance_schema_is_generic(self):
        prov = guidance_provenance(
            mode="canny",
            model_sha256="abc",
            mapping=make_mapping("abc"),
            anchors={"binding_id": "anchor:2", "sampler_id": "2"},
        )
        allowed = {
            "mode", "model_sha256", "mechanism", "controller_checkpoint",
            "controller_checkpoint_sha256", "controller_folder", "preprocessor",
            "mapping_revision", "anchor_binding_id", "sampler_id",
            "strength", "start", "end",
        }
        self.assertEqual(set(prov), allowed)
        meta: dict = {}
        attach_guidance_provenance(meta, prov)
        self.assertEqual(meta["guidance_provenance"], prov)


if __name__ == "__main__":
    unittest.main()
