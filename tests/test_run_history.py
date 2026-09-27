import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "run_history.py"


def load_module():
    if not MODULE_PATH.exists():
        raise AssertionError("run_history.py missing")
    spec = importlib.util.spec_from_file_location("run_history", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class RedactionTests(unittest.TestCase):
    def test_redacts_modal_token_id(self):
        m = load_module()
        out = m.redact_log("auth: ak-1234567890abcdefghij")
        self.assertIn("ak-REDACTED", out)
        self.assertNotIn("ak-1234567890abcdefghij", out)

    def test_redacts_modal_token_secret(self):
        m = load_module()
        out = m.redact_log("secret: as-abcdefghijklmnopqrstuvwxyz")
        self.assertIn("as-REDACTED", out)

    def test_redacts_hf_token(self):
        m = load_module()
        out = m.redact_log("Authorization: Bearer hf_abc123def456ghi789jkl012mno345pqr")
        self.assertIn("REDACTED", out)
        self.assertNotIn("hf_abc123", out)

    def test_redacts_bearer_token(self):
        m = load_module()
        out = m.redact_log("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature")
        # Either form is acceptable: the line is fully redacted, or the
        # Bearer part is replaced. The credential is no longer present.
        self.assertNotIn("eyJhbGciOiJIUzI1NiJ9", out)
        self.assertIn("REDACTED", out)

    def test_redacts_authorization_header(self):
        m = load_module()
        out = m.redact_log("Authorization: Basic dXNlcjpwYXNz")
        self.assertIn("REDACTED", out)

    def test_leaves_normal_text_alone(self):
        m = load_module()
        text = "Starting model load. UNET: 2.5GB. CLIP: 1.0GB."
        self.assertEqual(m.redact_log(text), text)


class RecordRunTests(unittest.TestCase):
    def test_record_ordinary_run(self):
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            rid = m.record_run(
                root=tmp, kind="ordinary",
                workflow_name="test_workflow",
                workflow_hash="abc",
                model_stack={"unet": "x.safetensors"},
                prompt="hello",
                seed=42, steps=20, guidance=3.5,
                sampler="euler", scheduler="normal",
                output_path="/tmp/out.png",
            )
            self.assertTrue(rid.startswith("run_"))
            run = m.get_run(root=tmp, run_id=rid)
            self.assertEqual(run["workflow_name"], "test_workflow")
            self.assertEqual(run["seed"], 42)

    def test_record_experiment_cell_run(self):
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            rid = m.record_run(
                root=tmp, kind="experiment_cell",
                experiment_id="exp_1", cell_key="cell_a", checkpoint_id="ck_1",
                workflow_name="w",
                prompt="hello",
            )
            run = m.get_run(root=tmp, run_id=rid)
            self.assertEqual(run["kind"], "experiment_cell")
            self.assertEqual(run["experiment_id"], "exp_1")
            self.assertEqual(run["cell_key"], "cell_a")

    def test_record_warmup_run(self):
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            rid = m.record_run(root=tmp, kind="warmup", workflow_name="warmup_w")
            run = m.get_run(root=tmp, run_id=rid)
            self.assertEqual(run["kind"], "warmup")

    def test_experiment_cell_full_metadata(self):
        """Goal 5: run history for experiment cells records complete resolved metadata."""
        m = load_module()
        meta = {
            "experiment_id": "exp_full",
            "checkpoint_id": "ck_main",
            "cell_key": "cell_42",
            "attempt_id": "a_001",
            "asset_ids": ["uuid-1", "uuid-2"],
            "primary_asset_id": "uuid-1",
            "prompt": "a majestic cat",
            "negative_prompt": "blurry",
            "seed": 42,
            "steps": 20,
            "guidance": 3.5,
            "sampler": "euler",
            "scheduler": "normal",
            "denoise": 1.0,
            "width": 512,
            "height": 768,
            "unet": "flux1-dev.safetensors",
            "clip": "t5xxl_fp16.safetensors",
            "vae": "ae.safetensors",
            "lora_chain": [{"file": "style.safetensors", "model_strength": 0.8, "clip_strength": 0.6}],
            "workflow_hash": "wh_abc123",
            "error": "",
        }
        with tempfile.TemporaryDirectory() as tmp:
            rid = m.record_run(
                root=tmp,
                kind="experiment_cell",
                experiment_id=meta["experiment_id"],
                cell_key=meta["cell_key"],
                checkpoint_id=meta["checkpoint_id"],
                workflow_name="test",
                workflow_hash=meta["workflow_hash"],
                model_stack={"unet": meta["unet"], "clip": meta["clip"], "vae": meta["vae"]},
                loras=meta["lora_chain"],
                prompt=meta["prompt"],
                negative_prompt=meta["negative_prompt"],
                seed=meta["seed"],
                steps=meta["steps"],
                guidance=meta["guidance"],
                sampler=meta["sampler"],
                scheduler=meta["scheduler"],
                denoise=meta["denoise"],
                width=meta["width"],
                height=meta["height"],
                status="completed",
            )
            run = m.get_run(root=tmp, run_id=rid)
            self.assertEqual(run["kind"], "experiment_cell")
            self.assertEqual(run["experiment_id"], "exp_full")
            self.assertEqual(run["cell_key"], "cell_42")
            self.assertEqual(run["checkpoint_id"], "ck_main")
            self.assertEqual(run["workflow_hash"], "wh_abc123")
            self.assertEqual(run["seed"], 42)
            self.assertEqual(run["steps"], 20)
            self.assertEqual(run["guidance"], 3.5)
            self.assertEqual(run["sampler"], "euler")
            self.assertEqual(run["scheduler"], "normal")
            self.assertEqual(run["denoise"], 1.0)
            self.assertEqual(run["width"], 512)
            self.assertEqual(run["height"], 768)
            self.assertEqual(run["status"], "completed")

    def test_invalid_kind_raises(self):
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(m.HistoryError):
                m.record_run(root=tmp, kind="bogus")

    def test_log_is_redacted_on_write(self):
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            rid = m.record_run(
                root=tmp, kind="ordinary",
                workflow_name="w", log_lines=["auth: ak-1234567890abcdefghij"],
            )
            log = m.get_log(root=tmp, run_id=rid)
            self.assertIn("ak-REDACTED", log)
            self.assertNotIn("ak-1234567890abcdefghij", log)


class ListRunsTests(unittest.TestCase):
    def test_lists_recent_first(self):
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(5):
                m.record_run(root=tmp, kind="ordinary", workflow_name=f"w{i}")
                # ensure mtime ordering is observable
                import time
                time.sleep(0.01)
            runs = m.list_runs(root=tmp, limit=5)
            self.assertEqual(len(runs), 5)
            # newest first
            self.assertEqual(runs[0]["workflow_name"], "w4")

    def test_limit_truncates(self):
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(10):
                m.record_run(root=tmp, kind="ordinary", workflow_name=f"w{i}")
            runs = m.list_runs(root=tmp, limit=3)
            self.assertEqual(len(runs), 3)


class TimingFormatTests(unittest.TestCase):
    def test_format_timing_text(self):
        m = load_module()
        meta = {
            "run_id": "run_1",
            "workflow_name": "w",
            "timings": {"queue_ms": 100, "sampling_ms": 2000},
        }
        out = m.format_timing(meta, fmt="text")
        self.assertIn("queue_ms: 100", out)
        self.assertIn("sampling_ms: 2000", out)

    def test_format_timing_json(self):
        m = load_module()
        meta = {
            "run_id": "run_1",
            "workflow_name": "w",
            "timings": {"queue_ms": 100},
        }
        out = m.format_timing(meta, fmt="json")
        parsed = json.loads(out)
        self.assertEqual(parsed["queue_ms"], 100)


if __name__ == "__main__":
    unittest.main()
