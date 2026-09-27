import importlib.util
import json
import sys
from pathlib import Path

import pytest

from tools.v2_control import cli


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "run_exp07_decoupled_integrated.py"
spec = importlib.util.spec_from_file_location("run_exp07_decoupled_integrated", MODULE_PATH)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_schedule_is_80_requests_and_round_major_interleaved():
    schedule = module.campaign_schedule()
    assert len(schedule) == 80
    assert [item["round"] for item in schedule[:8]] == [1] * 8
    assert [item["round"] for item in schedule[8:16]] == [2] * 8
    assert [item["cell_id"] for item in schedule[:8]] == [
        cell["cell_id"] for cell in module.experiment_cells()
    ]
    assert schedule[0]["cell_id"] != schedule[1]["cell_id"]
    assert schedule[0]["cell_id"] == schedule[8]["cell_id"]


def test_accounting_is_160_model_observations():
    manifest = module.new_manifest()
    assert manifest == module.new_manifest()
    assert manifest["accounting"] == {
        "cell_count": 8,
        "observations_per_cell": 10,
        "request_count": 80,
        "model_observations_per_request": 2,
        "observation_count": 160,
    }
    assert all(item["models"] == ["clip", "unet"] for item in manifest["schedule"])


def test_source_qd_and_capacity_are_separate_fields():
    manifest = module.new_manifest()
    configs = [cell["configuration"] for cell in manifest["cells"]]
    assert {config["source_qd"] for config in configs} == {8}
    assert {config["source_capacity"] for config in configs} == {8}
    # A different configured QD is not allowed to rewrite capacity.
    assert module.expected_identity({**configs[0], "source_qd": 4})["source_capacity"] == 8


def test_each_cell_uses_an_accepted_profile_with_exact_runtime_identity():
    manifest = module.new_manifest()
    profiles = manifest["profile_strategy"]["profile_names"]
    assert len(profiles) == len(set(profiles)) == 8
    assert all(cli.is_golden_profile_name(profile) for profile in profiles)
    assert manifest["profile_strategy"]["baseline_profile"] == "golden_p1"
    assert manifest["profile_strategy"]["baseline_preserved"] is True

    for cell in manifest["cells"]:
        deployment = cell["deployment_manifest"]
        profile = deployment["profile"]
        config = cli.build_components(ROOT, profile)[3]
        assert config.target.app == module.APP
        assert config.target.class_name == module.CONTRACT_CLASS
        assert config.target.method == module.CONTRACT_METHOD
        assert config.resources.cpu == module.CPU_ALLOCATION
        assert config.resources.memory_mb == module.MEMORY_MB
        for name, value in deployment["deploy_baked_environment"].items():
            flag = config.flag(name)
            assert flag is not None
            assert flag.value == value


def test_plan_records_per_cell_profile_commands_and_restoration():
    manifest = module.new_manifest()
    assert manifest["execution_policy"]["subprocesses_launched"] is False
    assert manifest["execution_policy"]["modal_api_called"] is False
    assert manifest["execution_policy"]["public_run_requests_per_invocation"] == 1
    assert manifest["execution_policy"]["schedule_order"] == "round_major_interleaved"
    assert manifest["profile_strategy"]["restoration_required"] is True
    assert "golden_p1.toml" in manifest["profile_strategy"]["restoration_requirement"]

    for cell in manifest["cells"]:
        profile = cell["deployment_manifest"]["profile"]
        commands = manifest["public_commands_by_cell"][cell["cell_id"]]
        assert len(commands) == 5
        assert all(f"--profile {profile}" in command for command in commands)
        assert all(f"--app {module.APP}" in command for command in commands)
        assert commands[-1].endswith(f"golden run --app {module.APP}")

    assert len(manifest["public_commands_for_parent"]) == 8 * 5

    for request in manifest["schedule"]:
        profile = request["deployment_identity_expected"]["profile"]
        assert request["invocation_command"] == (
            f"python tools/v2ctl.py --profile {profile} golden run --app {module.APP}"
        )


def test_each_cell_has_its_own_identity_binding():
    manifest = module.new_manifest()
    first = manifest["cells"][0]
    identity = {
        **first["deployment_identity"]["expected"],
        "deployment_id": "deployment-a",
        "source_identity": "source-a",
    }
    module.bind_cell_identity(manifest, first["cell_id"], identity)
    assert manifest["cells"][0]["deployment_identity"]["actual"] == identity
    assert manifest["cells"][1]["deployment_identity"]["actual"] is None
    with pytest.raises(ValueError, match="already bound"):
        module.bind_cell_identity(manifest, first["cell_id"], {**identity, "deployment_id": "deployment-b"})


def _valid_artifact(manifest, request):
    cell = next(item for item in manifest["cells"] if item["cell_id"] == request["cell_id"])
    expected = cell["deployment_identity"]["expected"]
    identity = {**expected, "deployment_id": "deployment-a", "source_identity": "source-a"}
    config = {key: expected[key] for key in (
        "source_block_mib", "source_qd", "source_capacity", "h2d_copy_mib", "h2d_inflight_depth"
    )}
    return {
        "status": "ok",
        "identity": identity,
        "configuration": config,
        "source_qd_timeline": [{"configured_qd": 8, "achieved_qd": 8}],
        "achieved_h2d_depth": expected["h2d_inflight_depth"],
        "wait_dimensions": {"source_wait_ms": 1, "h2d_wait_ms": 2, "join_wait_ms": 3},
        "cpu_allocation": 4,
        "physical_reads": [{"requested_bytes": 128, "returned_bytes": 128}],
        "e27_proof_classification": "PROVEN",
    }


def test_resume_retains_explicit_artifact_and_never_discovers_newest(tmp_path):
    manifest = module.new_manifest()
    request = manifest["schedule"][0]
    artifact = tmp_path / "old-explicit-artifact.json"
    artifact.write_text(json.dumps(_valid_artifact(manifest, request)), encoding="utf-8")
    module.record_artifact(manifest, request["request_id"], artifact)
    assert manifest["schedule"][0]["status"] == "ELIGIBLE"
    assert manifest["schedule"][0]["artifact_path"] == str(artifact)
    assert module.next_pending_request(manifest)["request_id"] == manifest["schedule"][1]["request_id"]
    assert module.resume_manifest(manifest) == 0
    assert manifest["schedule"][0]["attempts"][0]["artifact_path"] == str(artifact)

    interrupted = module.new_manifest()
    module.start_request(interrupted, interrupted["schedule"][0]["request_id"])
    assert module.resume_manifest(interrupted) == 1
    assert interrupted["schedule"][0]["status"] == "FAILED"
    assert module.next_pending_request(interrupted)["request_id"] == interrupted["schedule"][1]["request_id"]


def test_proof_no_is_retained_but_fail_closed_as_not_mechanism_proven():
    manifest = module.new_manifest()
    request = manifest["schedule"][0]
    artifact = _valid_artifact(manifest, request)
    artifact["e27_proof_classification"] = "PROOF-NO"
    result = module.classify_artifact(artifact, manifest["cells"][0]["deployment_identity"]["expected"])
    assert result["status"] == "INVALID"
    assert result["result_classification"] == "PROOF_NO"
    assert result["mechanism_proven"] is False
