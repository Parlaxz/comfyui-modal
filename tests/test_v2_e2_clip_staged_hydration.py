from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import torch

from comfymodal_runtime import clip_fast_hydration as cfh
from comfymodal_runtime import clip_fast_hydration_wiring as wiring
from comfymodal_runtime import staged_safetensors as staged


class _Leaf(torch.nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.transformer = torch.nn.Linear(8, 8, dtype=torch.float32)

    def load_sd(self, sd: dict) -> None:
        self.transformer.load_state_dict(
            sd, strict=False, assign=getattr(self, "can_assign_sd", False)
        )


class _CSM(torch.nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.clip_l = _Leaf()

    def load_sd(self, sd: dict) -> None:
        self.clip_l.load_sd(sd)


class _Patcher:
    def __init__(self, model: torch.nn.Module) -> None:
        self.model = model
        self.load_device = torch.device("cpu")


class _Clip:
    def __init__(self) -> None:
        self.cond_stage_model = _CSM()
        self.patcher = _Patcher(self.cond_stage_model)

    def load_model(self, tokens=None):
        return self.patcher


class _Owner:
    def __init__(self) -> None:
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


class _StagedCore:
    def __init__(self, state_dict: dict, owner: _Owner) -> None:
        self.state_dict = state_dict
        self.owner = owner
        self.calls: list[str] = []

    def plan(self, paths, target_device=None):
        self.calls.append("plan")
        return {"paths": list(paths), "target_device": target_device, "eligible": True}

    def prepare(self, plan):
        self.calls.append("prepare")
        return {"plan": plan}

    def commit(self, prepared):
        self.calls.append("commit")
        return {
            "success": True,
            "prepared": prepared,
            "state_dicts": [self.state_dict],
            "owner": self.owner,
            "h2d_ms": 2.5,
        }

    def result(self, committed):
        self.calls.append("result")
        return committed


class _StageResultCore(_StagedCore):
    def __init__(self, state_dict: dict, owner: _Owner, *, success: bool, reason: str = ""):
        super().__init__(state_dict, owner)
        self.success = success
        self.reason = reason

    def commit(self, prepared):
        self.calls.append("commit")
        return staged.StageResult(
            success=self.success,
            tensors=self.state_dict,
            checkpoint_bytes=1,
            disk_to_stage_ms=1.0,
            cpu_cast_ms=0.0,
            h2d_enqueue_ms=1.0,
            h2d_device_ms=1.0,
            bind_independent_transfer=True,
            peak_pinned_bytes=1,
            producer_wait_ms=0.0,
            consumer_wait_ms=0.0,
            effective_h2d_gbps=1.0,
            fallback_reason=self.reason or None,
            _owner=self.owner,
        )


def _fixture(tmp_path: Path) -> tuple[_Clip, SimpleNamespace, dict]:
    import safetensors.torch

    source = _Leaf().transformer.state_dict()
    state_dict = {key: value.detach().clone() for key, value in source.items()}
    path = tmp_path / "clip.safetensors"
    safetensors.torch.save_file(state_dict, str(path))
    clip = _Clip()
    models = SimpleNamespace(
        clip=clip,
        file_facts=(SimpleNamespace(role="clip1", path=str(path)),),
        model_spec={"loaders": {"clip": [{"clip_name": "clip.safetensors", "type": "generic"}]}},
    )
    return clip, models, state_dict


def _flags():
    return {
        wiring._FLAG_STAGED: "1",
        wiring._FLAG_FAST: "0",
        wiring._FLAG_EXCLUDE: "1",
    }


def _reset() -> None:
    wiring._RECORD.clear()
    wiring._LAST_EXCLUDED.clear()
    wiring._LAST_CLIP = None


def test_staged_cold_miss_uses_four_phase_core_and_generic_bind(tmp_path: Path) -> None:
    _reset()
    clip, models, state_dict = _fixture(tmp_path)
    owner = _Owner()
    core = _StagedCore(state_dict, owner)
    with patch.dict(os.environ, _flags(), clear=False), patch.object(
        wiring, "_staged_core", return_value=core
    ), patch.object(wiring, "_try_fast_hydrate", side_effect=AssertionError("fast fallback")):
        prepared = wiring.maybe_prepare_clip_snapshot_exclusion(models)
        assert prepared["status"] == "excluded"
        outcome = wiring._hydrate_clip_on_demand(clip)

    assert core.calls == ["plan", "prepare", "commit", "result"]
    assert outcome["mode"] == cfh.MODE_STAGED
    assert outcome["ok"] is True
    assert "zero-copy: 2/2" in outcome["zero_copy_evidence"]
    assert outcome["clip_staged_h2d_ms"] == 2.5
    assert outcome["clip_staged_bind_ms"] is not None
    assert getattr(clip.patcher, cfh.STAGED_OWNER_ATTR)[0] is owner
    assert cfh.release_owner(clip) is True
    assert owner.close_calls == 1


def test_staged_failure_calls_existing_fast_path_once(tmp_path: Path) -> None:
    _reset()
    clip, models, _ = _fixture(tmp_path)
    core = _StagedCore({}, _Owner())
    fast = {"ok": True, "mode": cfh.MODE_FASTSAFE, "fallback_count": 0}
    with patch.dict(os.environ, _flags(), clear=False), patch.object(
        wiring, "_staged_core", return_value=core
    ), patch.object(wiring, "_try_fast_hydrate", return_value=fast) as fast_hydrate:
        prepared = wiring.maybe_prepare_clip_snapshot_exclusion(models)
        assert prepared["status"] == "excluded"
        outcome = wiring._hydrate_clip_on_demand(clip)

    fast_hydrate.assert_called_once()
    assert outcome["mode"] == cfh.MODE_FASTSAFE
    assert outcome["clip_staged_fallback_reason"]
    assert core.calls == ["plan", "prepare", "commit", "result"]


def test_staged_enabled_cache_hit_does_zero_hydration(tmp_path: Path) -> None:
    _reset()
    clip, models, _ = _fixture(tmp_path)
    core = _StagedCore({}, _Owner())
    with patch.dict(os.environ, _flags(), clear=False), patch.object(
        wiring, "_staged_core", return_value=core
    ):
        prepared = wiring.maybe_prepare_clip_snapshot_exclusion(models)
        assert prepared["status"] == "excluded"
        status = wiring.maybe_install_clip_fh_demand(models)
        assert status["status"] == "installed"
        assert core.calls == []
        assert not cfh.clip_hydrated(clip)
        assert wiring.clip_fh_request_summary("")["hydration_source"] == cfh.MODE_CACHE_HIT


def test_real_stage_result_transfers_owner_through_model_lifetime(tmp_path: Path) -> None:
    _reset()
    clip, models, state_dict = _fixture(tmp_path)
    owner = _Owner()
    core = _StageResultCore(state_dict, owner, success=True)
    with patch.dict(os.environ, _flags(), clear=False), patch.object(
        wiring, "_staged_core", return_value=core
    ):
        prepared = wiring.maybe_prepare_clip_snapshot_exclusion(models)
        assert prepared["status"] == "excluded"
        outcome = wiring._hydrate_clip_on_demand(clip)

    assert outcome["mode"] == cfh.MODE_STAGED
    assert outcome["ok"] is True
    assert owner.close_calls == 0
    assert getattr(clip.patcher, cfh.STAGED_OWNER_ATTR)[0] is owner
    assert outcome["clip_staged_h2d_ms"] == 1.0
    assert cfh.release_owner(clip) is True
    assert owner.close_calls == 1


def test_stage_result_failure_reason_precedes_empty_tensor_diagnostic(tmp_path: Path) -> None:
    _reset()
    clip, models, _ = _fixture(tmp_path)
    owner = _Owner()
    core = _StageResultCore(
        {}, owner, success=False, reason="native_pin_budget_uninitialized"
    )
    fast = {"ok": True, "mode": cfh.MODE_FASTSAFE, "fallback_count": 0}
    with patch.dict(os.environ, _flags(), clear=False), patch.object(
        wiring, "_staged_core", return_value=core
    ), patch.object(wiring, "_try_fast_hydrate", return_value=fast) as fast_hydrate:
        prepared = wiring.maybe_prepare_clip_snapshot_exclusion(models)
        assert prepared["status"] == "excluded"
        outcome = wiring._hydrate_clip_on_demand(clip)

    fast_hydrate.assert_called_once()
    assert "native_pin_budget_uninitialized" in outcome["clip_staged_fallback_reason"]
