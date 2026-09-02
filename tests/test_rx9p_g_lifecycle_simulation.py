"""Local RX9P-G lifecycle simulation for the repaired observability gates.

This deliberately drives the real direct-Golden adapter while replacing only
the model/GPU execution with a deterministic async result.  Trace finalization,
report generation, bundle persistence, descriptor attachment, and the Modal
profiler projection remain the production implementations.
"""

from __future__ import annotations

import asyncio
import gzip
import io
import json
import os
import sys
import tarfile
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

import pytest

from comfymodal_runtime import full_execution_trace as ft
from comfymodal_runtime import modal_app
from comfymodal_runtime.full_execution_trace import FullExecutionTraceSession
from comfymodal_runtime.golden_serial import GoldenFinalResult
from comfymodal_runtime.runtime_state import FakeVolume
from tools.v2_control import experiment_evidence
from tools.v2_control.experiment_evidence import finalize_experiment_evidence


REQUEST_ID = "rx9p-g-request"
INVOCATION_ID = "rx9p-g-invocation"
E27_RAW_RELATIVE_PATH = "raw/e27_source_mechanism.json"

pytestmark = pytest.mark.heavy_local


def _synthetic_trace() -> dict:
    """Return one root and all non-durable canonical Golden stages."""
    stages = (
        "golden_restore",
        "golden_request_setup",
        "golden_clip_load",
        "golden_clip_forward",
        "golden_unet_load",
        "golden_sampler_prepare",
        "golden_vae_load",
        "golden_sampling",
        "golden_sampler_tail",
        "golden_vae_decode",
        "golden_output",
    )
    return {
        "traceEvents": [
            {
                "ph": "X",
                "name": "golden_serial_execute",
                "ts": 1_000_000,
                "dur": 1_200_000,
                "pid": 1,
                "tid": 1,
            },
            *[
                {
                    "ph": "X",
                    "name": name,
                    "ts": 1_010_000 + index * 100_000,
                    "dur": 80_000,
                    "pid": 1,
                    "tid": 1,
                }
                for index, name in enumerate(stages)
            ],
        ],
        "metadata": {
            "dump_counter": 1,
            "tracer_args": {"entry_capacity": 1000},
        },
    }


def _consume(async_stream) -> list[dict]:
    async def drain() -> list[dict]:
        return [item async for item in async_stream]

    return asyncio.run(drain())


def test_direct_golden_repaired_lifecycle_persists_and_projects_every_gate(tmp_path: Path, capsys):
    trace_base = tmp_path / "trace-base"
    runtime_state_root = tmp_path / "runtime-state"
    runtime_state_root.mkdir()
    profile_volume = FakeVolume()
    original_trace_base = ft._TEST_TRACE_BASE
    FullExecutionTraceSession.reset_instance()
    ft._TEST_TRACE_BASE = str(trace_base)

    try:
        with patch.dict(
            os.environ,
            {
                "COMFYMODAL_V2_FULL_TRACE": "1",
                "COMFYMODAL_V2_FULL_TRACE_TORCH": "0",
                "COMFYMODAL_V2_FULL_TRACE_RESOURCE_INTERVAL_MS": "10000",
                "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": "1",
                "COMFYMODAL_V2CTL_INVOCATION_ID": INVOCATION_ID,
            },
            clear=False,
        ):
            session = FullExecutionTraceSession.create_if_enabled(
                container_session_id="rx9p-g-container",
                restored_instance_id="restored-rx9p-g",
                restore_session_id="restore-rx9p-g",
                _trace_id_override="rx9p-g-trace",
            )
            assert session is not None
            captured_invocation_id = os.environ["COMFYMODAL_V2CTL_INVOCATION_ID"]
            assert captured_invocation_id == INVOCATION_ID

            # These are the real restore lifecycle calls used by the runtime.
            session.start_restore()
            assert session.state == "restore_tracing"
            session.set_restore_complete()
            assert session.state == "restore_complete"

            # The local fixture supplies the raw VizTracer evidence that a
            # real profiler would have written.  Disable an installed local
            # VizTracer instance so it cannot overwrite this deterministic
            # synthetic trace during stop_tracing().
            session._viztracer = None
            raw_dir = session.base_dir / "raw"
            (raw_dir / "viztracer.json.gz").write_bytes(
                gzip.compress(json.dumps(_synthetic_trace()).encode("utf-8"))
            )
            (raw_dir / E27_RAW_RELATIVE_PATH.removeprefix("raw/")).write_text(
                json.dumps(
                    {
                        "E27_SOURCE_MECHANISM_PROVEN": "YES",
                        "actual_source_events": [
                            {"producer_id": 0, "requested_bytes": 4, "returned_bytes": 4}
                        ],
                        "provenance": "synthetic-local-direct-adapter",
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            lifecycle: list[str] = []
            original_torch_start = session.start_torch_profiler
            original_torch_stop = session.stop_torch_profiler

            def torch_start() -> None:
                lifecycle.append("torch_begin")
                original_torch_start()

            def torch_stop() -> None:
                lifecycle.append("torch_end")
                original_torch_stop()

            async def fake_golden_execute(request, *, telemetry_path, **_kwargs):
                lifecycle.append("golden_enter")
                telemetry = {
                    "schema": "golden_p1_telemetry_v1",
                    "run_identity": {"request_id": request.request_id},
                    "attention_backend_configured": "pytorch",
                    "attention_backend_resolved": "pytorch",
                    "sage_runtime_mode_configured": "auto",
                    "sage_runtime_mode_effective_input": "auto",
                    "sage_runtime_mode_resolution_source": "auto_resolution",
                    "sage_runtime_mode_resolved": "baked_cuda",
                    "e27_raw_evidence_path": E27_RAW_RELATIVE_PATH,
                    "E27_SOURCE_MECHANISM_PROVEN": "YES",
                }
                Path(telemetry_path).write_text(
                    json.dumps(telemetry), encoding="utf-8"
                )
                lifecycle.append("golden_return")
                return GoldenFinalResult(
                    request_id=request.request_id,
                    image_sha256="a" * 64,
                    asset_path="",
                    volume_rel_path="",
                    true_durable=False,
                    seriality_violation_count=0,
                    executed_nodes=[],
                    run_identity={"request_id": request.request_id},
                    output_durability_mode="off",
                    durability_requested=False,
                    filename="synthetic.png",
                    mime_type="image/png",
                    byte_count=4,
                    width=1,
                    height=1,
                    output_node_id="output",
                    image_data="cG5n",
                )

            adapter = modal_app.ModalRuntimeEntrypoint()
            adapter._full_trace_session = session
            adapter._restore_timing = {
                "restore_method_status": "success",
                "remote_python_resume_wall_unix_ns": 1,
                "remote_python_resume_mono_ns": 1,
                "restore_method_start_wall_unix_ns": 2,
                "restore_method_start_mono_ns": 2,
                "restore_method_end_wall_unix_ns": 3,
                "restore_method_end_mono_ns": 3,
            }
            adapter._post_restore_nonce = "post-restore-rx9p-g"
            adapter._legacy_api = SimpleNamespace(
                _ensure_gpu_ready_for_request=lambda: lifecycle.append("gpu_ready")
            )

            nodes_module = ModuleType("nodes")
            setattr(nodes_module, "NODE_CLASS_MAPPINGS", {})
            resources = {
                "runtime_state_volume": FakeVolume(),
                "profile_volume": profile_volume,
                "runtime_state_mount_root": str(runtime_state_root),
            }
            activation = {
                "activated": True,
                "already_activated": False,
                "is_dynamic_alias": True,
            }
            request = {
                "request_id": REQUEST_ID,
                "attention_backend": "pytorch",
                "sage_runtime_mode": "auto",
                "prompt": {"1": {"class_type": "Synthetic"}},
                "extra_data": {},
            }

            with (
                patch.object(modal_app, "RUNTIME_STATE_PATH", str(runtime_state_root)),
                patch.object(modal_app, "PROFILE_PATH", str(tmp_path / "profiles")),
                patch.object(modal_app, "PROFILE_VOLUME_NAME", "rx9p-g-profiles"),
                patch.object(modal_app, "_MODAL_RESOURCES", resources),
                patch.object(modal_app, "_capture_remote_identity", return_value={}),
                patch.object(modal_app, "_capture_host_info", return_value={"pid": 1}),
                patch.object(modal_app, "_V2_FULL_TRACE_ENABLED", True),
                patch.object(session, "start_torch_profiler", side_effect=torch_start) as torch_begin,
                patch.object(session, "stop_torch_profiler", side_effect=torch_stop) as torch_end,
                patch.object(
                    modal_app,
                    "_finalize_full_trace",
                    wraps=modal_app._finalize_full_trace,
                ) as finalizer,
                patch.dict(sys.modules, {"nodes": nodes_module}),
                patch(
                    "comfymodal_runtime.golden_aimdo_activation.activate_golden_dynamic_vram",
                    return_value=activation,
                ),
                patch(
                    "comfymodal_runtime.golden_serial.golden_serial_execute",
                    new=fake_golden_execute,
                ),
            ):
                events = _consume(adapter.run_golden_serial_stream(request))

            # Actual adapter lifecycle: one claim, one Torch boundary around
            # the Golden await, then one finalizer invocation.
            assert lifecycle == [
                "gpu_ready",
                "torch_begin",
                "golden_enter",
                "golden_return",
                "torch_end",
            ]
            assert torch_begin.call_count == 1
            assert torch_end.call_count == 1
            assert finalizer.call_count == 1
            assert sum(event.get("event") == "request_claimed" for event in session.events) == 1
            assert session._claimed_request_id == REQUEST_ID
            assert session.state == "trace_stopped"

            result_events = [event for event in events if event.get("type") == "result"]
            assert len(result_events) == 1
            result_data = result_events[0]["data"]
            artifact = result_data["full_trace_artifact"]
            assert artifact["status"] == "ready"  # descriptor attached
            assert profile_volume.commit_count == 1  # exactly one finalization

            descriptor = json.loads(
                profile_volume.read_bytes(artifact["remote_descriptor_path"])
            )
            assert descriptor == artifact

            # E27 raw evidence is referenced at the direct result boundary and
            # preserved in the persisted bundle, rather than reconstructed from
            # a summary.
            assert result_data["golden_telemetry"]["e27_raw_evidence_path"] == E27_RAW_RELATIVE_PATH
            assert result_data["golden_telemetry"]["attention_backend_configured"] == "pytorch"
            assert result_data["golden_telemetry"]["attention_backend_resolved"] == "pytorch"
            assert result_data["golden_telemetry"]["sage_runtime_mode_configured"] == "auto"
            assert result_data["golden_telemetry"]["sage_runtime_mode_effective_input"] == "auto"
            assert result_data["golden_telemetry"]["sage_runtime_mode_resolution_source"] == "auto_resolution"
            assert result_data["golden_telemetry"]["sage_runtime_mode_resolved"] in {
                "baked_cuda",
                "triton_fallback",
            }
            bundle = tarfile.open(
                fileobj=io.BytesIO(profile_volume.read_bytes(artifact["remote_bundle_path"])),
                mode="r:gz",
            )
            with bundle:
                names = bundle.getnames()
                assert E27_RAW_RELATIVE_PATH in names
                assert "derived/golden_profile_summary.json" in names
                assert "derived/golden_profile_gantt.txt" in names
                manifest_file = bundle.extractfile("bundle_manifest.json")
                assert manifest_file is not None
                manifest = json.loads(manifest_file.read())
            assert any(entry["path"] == E27_RAW_RELATIVE_PATH for entry in manifest["entries"])

            # The projection is derived from the persisted Gantt, not a second
            # renderer: the exact file content must be between its delimiters.
            gantt_path = session.base_dir / "derived" / "golden_profile_gantt.txt"
            gantt = gantt_path.read_text(encoding="utf-8")
            stdout = capsys.readouterr().out
            assert stdout.count("[v2.golden_profiler] BEGIN") == 1
            assert stdout.count("[v2.golden_profiler] END") == 1
            assert stdout.count("GANTT_BEGIN") == 1
            assert stdout.count("GANTT_END") == 1
            assert f"GANTT_BEGIN\n{gantt}GANTT_END" in stdout

            # The repaired invocation identity survives the attempt/evidence
            # chain independently of the remote adapter's model result.
            evidence_root = tmp_path / "artifacts" / "phase_p1_serial_golden_v1"
            cohort = evidence_root / "rx9p-g-cohort"
            cohort.mkdir(parents=True)
            attempt = {
                "request_id": REQUEST_ID,
                "v2ctl_invocation_id": INVOCATION_ID,
                "attention_backend_configured": "pytorch",
                "attention_backend_resolved": "pytorch",
                "sage_runtime_mode_configured": "auto",
                "sage_runtime_mode_effective_input": "auto",
                "sage_runtime_mode_resolution_source": "auto_resolution",
                "sage_runtime_mode_resolved": "baked_cuda",
                "valid": True,
                "dnf": False,
                "failures": [],
                "validation": {"observed_output_shas": ["a" * 64]},
                "full_trace_artifact": artifact,
            }
            (cohort / "attempt_0.json").write_text(json.dumps(attempt), encoding="utf-8")
            (cohort / "summary.json").write_text(
                json.dumps(
                    {
                        "v2ctl_invocation_id": INVOCATION_ID,
                        "request_id": REQUEST_ID,
                        "attention_backend_configured": "pytorch",
                        "attention_backend_resolved": "pytorch",
                        "sage_runtime_mode_configured": "auto",
                        "sage_runtime_mode_effective_input": "auto",
                        "sage_runtime_mode_resolution_source": "auto_resolution",
                        "sage_runtime_mode_resolved": "baked_cuda",
                        "attempts": [
                            {
                                "v2ctl_invocation_id": INVOCATION_ID,
                                "request_id": REQUEST_ID,
                                "attention_backend_configured": "pytorch",
                                "attention_backend_resolved": "pytorch",
                                "sage_runtime_mode_configured": "auto",
                                "sage_runtime_mode_effective_input": "auto",
                                "sage_runtime_mode_resolution_source": "auto_resolution",
                                "sage_runtime_mode_resolved": "baked_cuda",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (cohort / "manifest.json").write_text(
                json.dumps(
                    {
                        "v2ctl_invocation_id": INVOCATION_ID,
                        "profile": "golden_p1",
                        "profile_config_fingerprint": "rx9p-g-profile",
                        "run_fingerprint": "rx9p-g-run",
                        "expected_output_sha": "a" * 64,
                        "attention_backend_configured": "pytorch",
                        "attention_backend_resolved": "pytorch",
                        "sage_runtime_mode_configured": "auto",
                        "sage_runtime_mode_effective_input": "auto",
                        "sage_runtime_mode_resolution_source": "auto_resolution",
                        "sage_runtime_mode_resolved": "baked_cuda",
                        "full_trace_claim": "claimed",
                        "e27_raw_evidence_path": E27_RAW_RELATIVE_PATH,
                        "profiler_descriptor": artifact,
                        "attempts": [
                            {
                                "v2ctl_invocation_id": INVOCATION_ID,
                                "request_id": REQUEST_ID,
                                "attention_backend_configured": "pytorch",
                                "attention_backend_resolved": "pytorch",
                                "sage_runtime_mode_configured": "auto",
                                "sage_runtime_mode_effective_input": "auto",
                                "sage_runtime_mode_resolution_source": "auto_resolution",
                                "sage_runtime_mode_resolved": "baked_cuda",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            manifest = json.loads((cohort / "manifest.json").read_text(encoding="utf-8"))
            summary = json.loads((cohort / "summary.json").read_text(encoding="utf-8"))
            persisted_attempt = json.loads(
                (cohort / "attempt_0.json").read_text(encoding="utf-8")
            )

            # One immutable invocation identity spans control-plane, cohort,
            # attempt, summary, and the summary's attempt projection.
            invocation_chain = [
                manifest["v2ctl_invocation_id"],
                persisted_attempt["v2ctl_invocation_id"],
                summary["v2ctl_invocation_id"],
                summary["attempts"][0]["v2ctl_invocation_id"],
            ]
            assert invocation_chain == [INVOCATION_ID] * 4
            request_chain = [
                manifest["attempts"][0]["request_id"],
                persisted_attempt["request_id"],
                summary["request_id"],
                summary["attempts"][0]["request_id"],
            ]
            assert request_chain == [REQUEST_ID] * 4
            assert session._claimed_request_id == REQUEST_ID  # full-trace claim
            assert artifact["status"] == "ready"  # profiler descriptor attached
            assert all(
                persisted_attempt[field] == expected
                for field, expected in (
                    ("attention_backend_configured", "pytorch"),
                    ("attention_backend_resolved", "pytorch"),
                    ("sage_runtime_mode_configured", "auto"),
                    ("sage_runtime_mode_effective_input", "auto"),
                    ("sage_runtime_mode_resolution_source", "auto_resolution"),
                    ("sage_runtime_mode_resolved", "baked_cuda"),
                )
            )
            evidence = finalize_experiment_evidence(
                tmp_path,
                identity={
                    "profile": "golden_p1",
                    "v2ctl_invocation_id": INVOCATION_ID,
                    "request_id": REQUEST_ID,
                    "profile_config_fingerprint": "rx9p-g-profile",
                    "run_fingerprint": "rx9p-g-run",
                    "attention_backend_configured": "pytorch",
                    "attention_backend_resolved": "pytorch",
                    "sage_runtime_mode_configured": "auto",
                    "sage_runtime_mode_effective_input": "auto",
                    "sage_runtime_mode_resolution_source": "auto_resolution",
                    "sage_runtime_mode_resolved": "baked_cuda",
                },
                verdict="ACCEPT",
            )
            assert evidence.status == "OK"
            evidence_index = json.loads(
                (evidence.bundle_dir / "evidence_index.json").read_text(encoding="utf-8")
            )
            assert evidence_index["identity"]["v2ctl_invocation_id"] == INVOCATION_ID
            assert evidence_index["cohorts"][0]["exact"] == "EXACT"
            indexed = evidence_index["cohorts"][0]
            assert indexed["attention_backend_configured"] == "pytorch"
            assert indexed["attention_backend_resolved"] == "pytorch"
            assert indexed["attention_backend_resolved"] not in {"", "missing", "mixed"}
            assert indexed["sage_runtime_mode_configured"] == "auto"
            assert indexed["sage_runtime_mode_effective_input"] == "auto"
            assert indexed["sage_runtime_mode_resolution_source"] == "auto_resolution"
            assert indexed["sage_runtime_mode_resolved"] in {"baked_cuda", "triton_fallback"}
            assert indexed["sage_runtime_mode_resolved"] != "auto"
            assert indexed["source_artifacts"]
            compact = experiment_evidence._compact_cohort(
                cohort,
                {
                    "profile": "golden_p1",
                    "v2ctl_invocation_id": INVOCATION_ID,
                    "request_id": REQUEST_ID,
                    "profile_config_fingerprint": "rx9p-g-profile",
                    "run_fingerprint": "rx9p-g-run",
                    "attention_backend_configured": "pytorch",
                    "attention_backend_resolved": "pytorch",
                    "sage_runtime_mode_configured": "auto",
                    "sage_runtime_mode_effective_input": "auto",
                    "sage_runtime_mode_resolution_source": "auto_resolution",
                    "sage_runtime_mode_resolved": "baked_cuda",
                },
            )
            assert compact["exact"] == "EXACT"

            # Every identity dimension is independently adversarial: no wrong
            # value may be accepted as an EXACT cohort.
            identity_fields = {
                "invocation_id": (
                    "v2ctl_invocation_id",
                    "wrong-invocation",
                    ("manifest", "manifest_attempt", "attempt", "summary", "summary_attempt"),
                ),
                "request_id": (
                    "request_id",
                    "wrong-request",
                    ("manifest_attempt", "attempt", "summary", "summary_attempt"),
                ),
                "attention_backend_configured": (
                    "attention_backend_configured",
                    "sage",
                    ("manifest", "manifest_attempt", "attempt", "summary", "summary_attempt"),
                ),
                "attention_backend_resolved": (
                    "attention_backend_resolved",
                    "sage",
                    ("manifest", "manifest_attempt", "attempt", "summary", "summary_attempt"),
                ),
                "sage_configured": (
                    "sage_runtime_mode_configured",
                    "baked_cuda",
                    ("manifest", "manifest_attempt", "attempt", "summary", "summary_attempt"),
                ),
                "sage_effective": (
                    "sage_runtime_mode_effective_input",
                    "baked_cuda",
                    ("manifest", "manifest_attempt", "attempt", "summary", "summary_attempt"),
                ),
                "sage_source": (
                    "sage_runtime_mode_resolution_source",
                    "environment_override",
                    ("manifest", "manifest_attempt", "attempt", "summary", "summary_attempt"),
                ),
                "sage_resolved": (
                    "sage_runtime_mode_resolved",
                    "auto",
                    ("manifest", "manifest_attempt", "attempt", "summary", "summary_attempt"),
                ),
            }
            source_documents = {
                "manifest": manifest,
                "attempt": persisted_attempt,
                "summary": summary,
                "summary_attempt": summary["attempts"][0],
                "manifest_attempt": manifest["attempts"][0],
            }
            for label, (field, wrong_value, locations) in identity_fields.items():
                mutated_documents = json.loads(json.dumps(source_documents))
                for location in locations:
                    mutated_documents[location][field] = wrong_value
                mutated_cohort = tmp_path / "identity-mutations" / label
                mutated_cohort.mkdir(parents=True)
                for filename, document in (
                    ("manifest.json", mutated_documents["manifest"]),
                    ("summary.json", mutated_documents["summary"]),
                    ("attempt_0.json", mutated_documents["attempt"]),
                ):
                    (mutated_cohort / filename).write_text(
                        json.dumps(document), encoding="utf-8"
                    )
                classification = experiment_evidence._compact_cohort(
                    mutated_cohort,
                    {
                        "profile": "golden_p1",
                        "v2ctl_invocation_id": INVOCATION_ID,
                        "request_id": REQUEST_ID,
                        "profile_config_fingerprint": "rx9p-g-profile",
                        "run_fingerprint": "rx9p-g-run",
                        "attention_backend_configured": "pytorch",
                        "attention_backend_resolved": "pytorch",
                        "sage_runtime_mode_configured": "auto",
                        "sage_runtime_mode_effective_input": "auto",
                        "sage_runtime_mode_resolution_source": "auto_resolution",
                        "sage_runtime_mode_resolved": "baked_cuda",
                    },
                )
                assert classification["exact"] in {"MISMATCH", "INCOMPLETE"}, label

            # A repeated finalizer call is inert: the lifecycle has exactly one
            # real finalization and no second commit.
            assert modal_app._safe_full_trace_artifact(
                session, profile_volume, REQUEST_ID
            )["status"] == "absent"
            assert profile_volume.commit_count == 1
    finally:
        FullExecutionTraceSession.reset_instance()
        ft._TEST_TRACE_BASE = original_trace_base


def test_full_trace_off_remains_inert(tmp_path: Path):
    original_trace_base = ft._TEST_TRACE_BASE
    FullExecutionTraceSession.reset_instance()
    ft._TEST_TRACE_BASE = str(tmp_path / "trace-base")
    try:
        with patch.dict(os.environ, {"COMFYMODAL_V2_FULL_TRACE": "0"}, clear=False):
            assert FullExecutionTraceSession.create_if_enabled(
                container_session_id="rx9p-g-off"
            ) is None
        assert not (tmp_path / "trace-base").exists()
    finally:
        FullExecutionTraceSession.reset_instance()
        ft._TEST_TRACE_BASE = original_trace_base
