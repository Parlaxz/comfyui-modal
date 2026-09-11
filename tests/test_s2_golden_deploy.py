"""Focused S2 publication and native Golden deploy contracts."""

from __future__ import annotations

import io
import hashlib
import asyncio
import json
import os
import stat
import sys
import tarfile
import tempfile
import types
from types import SimpleNamespace
from pathlib import Path

import pytest

from tools.v2_control import backend
from tools.v2_control.custom_nodes import (
    GENERATION_RECORD_PATH,
    PACKAGING_POLICY_VERSION,
    PublicationReceipt,
    RECEIPT_PATH,
    RECEIPT_SCHEMA_VERSION,
    build_archive,
    build_source_identity,
    collect_semantic_files,
    evaluate_receipt,
    get_volume,
    prepare_publication,
    publish_or_skip,
    read_receipt,
    read_receipt_async,
)


class FakeVolume:
    def __init__(self, name="test-volume"):
        self.name = name
        self.files = {}

    def read_file(self, path):
        if path not in self.files:
            raise FileNotFoundError(path)
        return iter((self.files[path],))

    class _Batch:
        def __init__(self, volume):
            self.volume = volume

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def put_file(self, handle, path):
            self.volume.files[path] = handle.read()

    def batch_upload(self, *, force):
        assert force is True
        return self._Batch(self)


class AsyncFakeVolume(FakeVolume):
    async def _read_chunks(self, path):
        if path not in self.files:
            raise FileNotFoundError(path)
        yield self.files[path]

    def read_file(self, path):  # type: ignore[override]
        return self._read_chunks(path)


class AsyncBatchVolume(AsyncFakeVolume):
    class _AsyncBatch:
        def __init__(self, volume):
            self.volume = volume

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def put_file(self, handle, path):
            self.volume.files[path] = handle.read()

    def batch_upload(self, *, force):  # type: ignore[override]
        assert force is True
        return self._AsyncBatch(self)


class _AioMethod:
    """Small double for Modal's sync callable plus ``.aio`` method shape."""

    def __init__(self, sync_call, async_call):
        self._sync_call = sync_call
        self.aio = async_call

    def __call__(self, *args, **kwargs):
        return self._sync_call(*args, **kwargs)


class ModalShapeVolume(AsyncBatchVolume):
    """Model Modal 1.4.3 live methods: sync wrappers and native async APIs."""

    def __init__(self, name="test-volume"):
        super().__init__(name)
        self.sync_calls = []
        self.read_file = _AioMethod(self._sync_read, self._read_chunks)
        self.batch_upload = _AioMethod(self._sync_batch, self._async_batch)

    def _sync_read(self, path):
        self.sync_calls.append(("read", path))
        raise AssertionError("blocking read_file interface was used")

    def _sync_batch(self, **_kwargs):
        self.sync_calls.append(("batch",))
        raise AssertionError("blocking batch_upload interface was used")

    def _async_batch(self, *, force):
        assert force is True
        return self._AsyncBatch(self)


def _root(tmp_path: Path) -> Path:
    node = tmp_path / "node-a"
    node.mkdir()
    (node / "main.py").write_bytes(b"main")
    (node / "README.md").write_bytes(b"metadata")
    return tmp_path


def _generation_record(volume: FakeVolume, identity) -> None:
    volume.files[GENERATION_RECORD_PATH] = json.dumps({
        "schema_version": 2,
        "content_generation": identity.content_generation,
    }).encode()


def test_exact_trusted_skip_does_not_call_compatibility_publisher(tmp_path):
    root = _root(tmp_path)
    identity, _archive, _files = prepare_publication(root)
    volume = FakeVolume()
    volume.files[RECEIPT_PATH] = PublicationReceipt.create(
        identity, volume.name
    ).to_bytes()
    calls = []

    async def publisher(_archive):
        calls.append(True)
        return {"status": "ok", "content_generation": identity.content_generation}

    decision = __import__("asyncio").run(publish_or_skip(
        root, volume_name=volume.name, volume=volume, publisher=publisher
    ))
    assert decision.skip and decision.reason == "exact_match"
    assert calls == []


@pytest.mark.parametrize("receipt_state", ["missing", "stale", "malformed"])
def test_generation_match_recovers_receipt_without_republishing(tmp_path, monkeypatch, receipt_state):
    root = _root(tmp_path)
    identity, _archive, _files = prepare_publication(root)
    volume = FakeVolume()
    _generation_record(volume, identity)
    if receipt_state == "stale":
        stale = PublicationReceipt.create(identity, volume.name)
        values = dict(stale.__dict__)
        values["manifest_digest"] = "stale-manifest"
        volume.files[RECEIPT_PATH] = PublicationReceipt(**values).to_bytes()
    elif receipt_state == "malformed":
        volume.files[RECEIPT_PATH] = b"not-json"

    monkeypatch.setattr(
        "tools.v2_control.custom_nodes.build_archive",
        lambda _files: (_ for _ in ()).throw(AssertionError("archive built")),
    )

    async def publisher(_archive):
        raise AssertionError("publisher resolved")

    decision = __import__("asyncio").run(publish_or_skip(
        root, volume_name=volume.name, volume=volume, publisher=publisher,
    ))
    assert decision.action == "recovered"
    assert decision.reason == "receipt_only_generation_match"
    assert decision.receipt is not None


def test_exact_trusted_skip_does_not_build_archive(tmp_path, monkeypatch):
    root = _root(tmp_path)
    identity, _archive, _files = prepare_publication(root)
    volume = FakeVolume()
    volume.files[RECEIPT_PATH] = PublicationReceipt.create(
        identity, volume.name
    ).to_bytes()

    import tools.v2_control.custom_nodes as custom_nodes
    monkeypatch.setattr(
        custom_nodes, "build_archive",
        lambda _files: (_ for _ in ()).throw(AssertionError("archive built")),
    )
    decision = __import__("asyncio").run(publish_or_skip(
        root, volume_name=volume.name, volume=volume,
        publisher=lambda _archive: {"status": "ok"},
    ))
    assert decision.skip and decision.reason == "exact_match"


def test_async_volume_reads_are_used_for_publication(tmp_path):
    root = _root(tmp_path)
    identity, _archive, _files = prepare_publication(root)
    volume = AsyncFakeVolume()

    async def publisher(_archive):
        _generation_record(volume, identity)
        return {"status": "ok", "content_generation": identity.content_generation}

    decision = __import__("asyncio").run(publish_or_skip(
        root, volume_name=volume.name, volume=volume, publisher=publisher,
    ))
    assert decision.reason == "published_verified"


def test_async_volume_batch_upload_is_awaited_for_receipt(tmp_path):
    root = _root(tmp_path)
    identity, _archive, _files = prepare_publication(root)
    volume = AsyncBatchVolume()

    async def publisher(_archive):
        _generation_record(volume, identity)
        return {"status": "ok", "content_generation": identity.content_generation}

    decision = __import__("asyncio").run(publish_or_skip(
        root, volume_name=volume.name, volume=volume, publisher=publisher,
    ))
    assert decision.reason == "published_verified"
    assert RECEIPT_PATH in volume.files


def test_host_modal_volume_does_not_reload_before_committed_readback(tmp_path, monkeypatch):
    root = _root(tmp_path)
    identity, _archive, _files = prepare_publication(root)
    monkeypatch.delenv("MODAL_IS_REMOTE", raising=False)

    class Volume(ModalShapeVolume):
        __module__ = "modal.volume"

        def __init__(self):
            super().__init__()
            self.reload = _AioMethod(
                lambda: (_ for _ in ()).throw(
                    AssertionError("host Modal Volume must not reload")
                ),
                lambda: (_ for _ in ()).throw(
                    RuntimeError("reload() can only be called from within a running function")
                ),
            )

    volume = Volume()

    async def publisher(_archive):
        _generation_record(volume, identity)
        return {"status": "ok", "content_generation": identity.content_generation}

    decision = __import__("asyncio").run(publish_or_skip(
        root, volume_name=volume.name, volume=volume, publisher=publisher,
    ))
    assert decision.reason == "published_verified"


def test_modal_143_aio_interfaces_avoid_blocking_volume_wrappers(tmp_path):
    root = _root(tmp_path)
    identity, _archive, _files = prepare_publication(root)
    volume = ModalShapeVolume()

    async def publisher(_archive):
        _generation_record(volume, identity)
        return {"status": "ok", "content_generation": identity.content_generation}

    decision = __import__("asyncio").run(publish_or_skip(
        root, volume_name=volume.name, volume=volume, publisher=publisher,
    ))
    assert decision.reason == "published_verified"
    assert volume.sync_calls == []


def test_sync_volume_factory_runs_outside_async_event_loop(tmp_path):
    root = _root(tmp_path)
    volume = FakeVolume()
    identity, _archive, _files = prepare_publication(root)
    factory_calls = []

    def factory(name):
        factory_calls.append(name)
        with pytest.raises(RuntimeError):
            __import__("asyncio").get_running_loop()
        return volume

    async def publisher(_archive):
        _generation_record(volume, identity)
        return {"status": "ok", "content_generation": identity.content_generation}

    decision = __import__("asyncio").run(publish_or_skip(
        root, volume_name=volume.name, volume_factory=factory, publisher=publisher,
    ))
    assert decision.reason == "published_verified"
    assert factory_calls == [volume.name]


def test_consumer_name_does_not_change_canonical_custom_node_identity(tmp_path):
    root = _root(tmp_path)
    identity_a, _archive, _files = prepare_publication(root)
    identity_b, _archive, _files = prepare_publication(root)
    assert identity_a.to_dict() == identity_b.to_dict()


def test_identity_and_receipt_name_full_content_explicitly(tmp_path):
    identity, _archive, _files = prepare_publication(_root(tmp_path))
    receipt = PublicationReceipt.create(identity, "test-volume")
    assert identity.to_dict()["content_generation"] == identity.manifest_digest
    assert "generation" not in identity.to_dict()
    assert receipt.to_dict()["content_generation"] == identity.content_generation
    assert "generation" not in receipt.to_dict()


def test_receipt_read_transient_error_is_not_missing_receipt():
    class PermissionVolume:
        def read_file(self, _path):
            raise PermissionError("credentials temporarily unavailable")

    with pytest.raises(PermissionError, match="credentials"):
        read_receipt(PermissionVolume(), volume_name="test-volume")

    async def read():
        await read_receipt_async(PermissionVolume(), volume_name="test-volume")

    with pytest.raises(PermissionError, match="credentials"):
        __import__("asyncio").run(read())


def test_excluded_only_node_is_skipped_and_valid_sibling_remains(tmp_path, caplog):
    node = tmp_path / "node-a"
    node.mkdir()
    (node / "README.md").write_text("excluded metadata", encoding="utf-8")
    sibling = tmp_path / "node-b"
    sibling.mkdir()
    (sibling / "main.py").write_text("VALUE = 1\n", encoding="utf-8")

    with caplog.at_level("WARNING", logger="comfymodal_runtime.publication_policy"):
        _identity, _archive, files = prepare_publication(tmp_path)

    assert [item.path for item in files] == ["node-b/main.py"]
    assert (
        "[v2.custom_node_publish] name=node-a status=skipped "
        "reason=no_publishable_files"
    ) in caplog.text


def test_malformed_nonempty_node_still_fails(tmp_path, monkeypatch):
    node = tmp_path / "node-a"
    node.mkdir()
    (node / "main.py").write_text("VALUE = 1\n", encoding="utf-8")
    malformed = node / "special.py"
    malformed.write_text("not a special file on this host\n", encoding="utf-8")
    real_lstat = Path.lstat

    def fake_lstat(path):
        if path == malformed:
            return os.stat_result((stat.S_IFCHR, 0, 0, 1, 0, 0, 0, 0, 0, 0))
        return real_lstat(path)

    monkeypatch.setattr(Path, "lstat", fake_lstat)

    with pytest.raises(ValueError, match="special file"):
        collect_semantic_files(tmp_path)


def test_semantic_collection_rejects_missing_root(tmp_path):
    with pytest.raises(OSError):
        collect_semantic_files(tmp_path / "missing")


def test_get_volume_constructs_handle_with_active_workspace_credentials(monkeypatch):
    calls = []
    client = object()

    class FakeClient:
        @staticmethod
        def from_credentials(token_id, token_secret):
            calls.append(("credentials", token_id, token_secret))
            return client

    class FakeVolume:
        @staticmethod
        def from_name(name, *, client):
            calls.append(("volume", name, client))
            return "volume-handle"

    monkeypatch.setenv("MODAL_TOKEN_ID", "ambient-id")
    monkeypatch.setenv("MODAL_TOKEN_SECRET", "ambient-secret")
    monkeypatch.setitem(
        sys.modules,
        "modal",
        types.SimpleNamespace(Client=FakeClient, Volume=FakeVolume),
    )

    result = get_volume(
        "comfyui-custom-nodes",
        workspace={"token_id": "ak-active", "token_secret": "as-active"},
    )

    assert result == "volume-handle"
    assert calls == [
        ("credentials", "ak-active", "as-active"),
        ("volume", "comfyui-custom-nodes", client),
    ]


def test_fallback_generation_matches_canonical_remote_hash(tmp_path):
    root = _root(tmp_path)
    files = collect_semantic_files(root)
    identity = build_source_identity(root, semantic_files=files)
    from comfymodal_runtime.publication_policy import compute_publication_generation

    assert identity.generation == compute_publication_generation(root)


def test_archive_generation_matches_remote_generation_helper(tmp_path):
    root = _root(tmp_path)
    identity, archive, _files = prepare_publication(root)
    extracted = Path(tempfile.mkdtemp()) / "extracted"
    extracted.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        tar.extractall(extracted, filter="data")
    from comfymodal_runtime.publication_policy import compute_publication_generation

    assert compute_publication_generation(root) == compute_publication_generation(extracted)
    assert identity.generation == compute_publication_generation(extracted)


@pytest.mark.parametrize("reason", [
    "missing_receipt", "schema_mismatch", "policy_mismatch", "malformed_receipt",
    "volume_mismatch", "publication_incomplete", "integrity_mismatch", "ownership_unproven",
])
def test_receipt_cases_fail_closed(reason, tmp_path):
    identity, _archive, _files = prepare_publication(_root(tmp_path))
    volume = FakeVolume()
    receipt = PublicationReceipt.create(identity, volume.name)
    if reason == "missing_receipt":
        raw = None
    elif reason == "malformed_receipt":
        raw = b"not-json"
    else:
        values = dict(receipt.__dict__)
        if reason == "schema_mismatch":
            values["schema_version"] = 99
        elif reason == "policy_mismatch":
            values["packaging_policy_version"] = 99
        elif reason == "volume_mismatch":
            values["volume_name"] = "other"
        elif reason == "publication_incomplete":
            values["state"] = "pending"
        elif reason == "integrity_mismatch":
            values["integrity_digest"] = "0" * 64
        elif reason == "ownership_unproven":
            values["ownership_marker"] = "unknown"
        raw = PublicationReceipt(**values)
    decision = evaluate_receipt(raw, identity, volume_name=volume.name)
    assert decision.skip is False
    assert decision.reason == reason


def test_publication_finalizes_receipt_only_after_verified_content(tmp_path):
    root = _root(tmp_path)
    identity, _archive, _files = prepare_publication(root)
    volume = FakeVolume()

    async def publisher(_archive):
        _generation_record(volume, identity)
        return {"status": "ok", "content_generation": identity.content_generation}

    decision = __import__("asyncio").run(publish_or_skip(
        root, volume_name=volume.name, volume=volume, publisher=publisher
    ))
    assert decision.reason == "published_verified"
    assert decision.result == {
        "status": "ok",
        "content_generation": identity.content_generation,
    }
    record = json.loads(volume.files[GENERATION_RECORD_PATH].decode())
    assert record["schema_version"] == 2
    assert record["content_generation"] == identity.content_generation
    assert RECEIPT_PATH in volume.files


def test_failed_publication_and_receipt_write_failure_retry(tmp_path, monkeypatch):
    root = _root(tmp_path)
    identity, _archive, _files = prepare_publication(root)
    volume = FakeVolume()

    async def failed(_archive):
        return {"status": "error"}

    failed_decision = __import__("asyncio").run(publish_or_skip(
        root, volume_name=volume.name, volume=volume, publisher=failed
    ))
    assert failed_decision.reason == "publication_incomplete"
    assert RECEIPT_PATH not in volume.files

    async def successful(_archive):
        _generation_record(volume, identity)
        return {"status": "ok", "content_generation": identity.content_generation}

    import tools.v2_control.custom_nodes as custom_nodes
    monkeypatch.setattr(custom_nodes, "write_receipt", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk")))
    retry_decision = __import__("asyncio").run(publish_or_skip(
        root, volume_name=volume.name, volume=volume, publisher=successful
    ))
    assert retry_decision.reason == "publication_incomplete"


def test_metadata_excluded_archive_and_identity_share_manifest(tmp_path):
    root = _root(tmp_path)
    (root / "node-a" / "custom_nodes_generation.json").write_text("old")
    identity, archive, files = prepare_publication(root)
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        names = [member.name for member in tar.getmembers()]
    assert names == [item.path for item in files]
    assert identity.file_count == len(names)
    assert identity.total_bytes == sum(item.size for item in files)
    assert all("generation" not in name for name in names)


def test_identity_provider_and_semantic_walk_are_single_pass(tmp_path):
    calls = []
    root = _root(tmp_path)

    def provider(root, files, entries):
        calls.append((root, files, entries))
        return "s1-adapter-generation"

    files = collect_semantic_files(root)
    identity = build_source_identity(root, semantic_files=files, identity_provider=provider)
    assert identity.generation == identity.manifest_digest
    assert identity.source_generation == "s1-adapter-generation"
    assert len(calls) == 1


def test_changed_json_does_not_recover_from_narrow_generation_record(tmp_path):
    """A narrow source hash must not bless a full-content publication."""
    from comfymodal_runtime.deployment_spec import compute_custom_node_hash

    root = _root(tmp_path)
    config = root / "node-a" / "node_config.json"
    config.write_text('{"mode": "one"}\n', encoding="utf-8")
    narrow_generation = compute_custom_node_hash([root])
    config.write_text('{"mode": "two"}\n', encoding="utf-8")
    identity = build_source_identity(root)
    assert narrow_generation != identity.generation

    volume = FakeVolume()
    volume.files[GENERATION_RECORD_PATH] = json.dumps({
        "schema_version": 2,
        "generation": narrow_generation,
    }).encode()
    calls = []

    async def publisher(archive):
        calls.append(archive)
        _generation_record(volume, identity)
        return {"status": "ok", "content_generation": identity.content_generation}

    decision = __import__("asyncio").run(publish_or_skip(
        root, volume_name=volume.name, volume=volume, publisher=publisher,
    ))
    assert calls
    assert decision.reason == "published_verified"


def test_receipt_is_written_after_generation_readback(tmp_path, monkeypatch):
    root = _root(tmp_path)
    identity, _archive, _files = prepare_publication(root)
    volume = FakeVolume()
    write_observations = []

    async def publisher(_archive):
        _generation_record(volume, identity)
        return {"status": "ok", "content_generation": identity.content_generation}

    import tools.v2_control.custom_nodes as custom_nodes

    async def write_receipt_after_readback(volume_arg, receipt):
        write_observations.append(GENERATION_RECORD_PATH in volume_arg.files)
        volume_arg.files[RECEIPT_PATH] = receipt.to_bytes()

    monkeypatch.setattr(custom_nodes, "write_receipt_async", write_receipt_after_readback)
    decision = __import__("asyncio").run(publish_or_skip(
        root, volume_name=volume.name, volume=volume, publisher=publisher,
    ))
    assert decision.reason == "published_verified"
    assert write_observations == [True]


def test_publisher_must_return_explicit_content_generation(tmp_path):
    root = _root(tmp_path)
    identity, _archive, _files = prepare_publication(root)
    volume = FakeVolume()

    async def publisher(_archive):
        _generation_record(volume, identity)
        return {"status": "ok", "generation": "narrow-source-id"}

    decision = __import__("asyncio").run(publish_or_skip(
        root, volume_name=volume.name, volume=volume, publisher=publisher,
    ))
    assert decision.action == "publish"
    assert decision.reason == "publication_incomplete"
    assert RECEIPT_PATH not in volume.files


def test_injected_fake_volume_refreshes_off_loop_before_readback(tmp_path):
    root = _root(tmp_path)
    identity, _archive, _files = prepare_publication(root)

    class ReloadingVolume(FakeVolume):
        def __init__(self):
            super().__init__()
            self.reload_count = 0
            self.reload_off_loop = True

        def reload(self):
            self.reload_count += 1
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                pass
            else:
                self.reload_off_loop = False

    volume = ReloadingVolume()

    async def publisher(_archive):
        _generation_record(volume, identity)
        return {"status": "ok", "content_generation": identity.content_generation}

    decision = __import__("asyncio").run(publish_or_skip(
        root, volume_name=volume.name, volume=volume, publisher=publisher,
    ))
    assert decision.reason == "published_verified"
    assert volume.reload_count == 1
    assert volume.reload_off_loop
    record = json.loads(volume.files[GENERATION_RECORD_PATH].decode())
    assert record["schema_version"] == 2
    assert record["content_generation"] == identity.content_generation


def test_archive_transport_metadata_does_not_replace_content_generation(tmp_path):
    root = _root(tmp_path)
    identity, archive, _files = prepare_publication(root)
    volume = FakeVolume()

    async def publisher(published_archive):
        _generation_record(volume, identity)
        return {
            "status": "ok",
            "content_generation": identity.content_generation,
            "archive_sha256": hashlib.sha256(published_archive).hexdigest(),
            "transport_sha256": "narrow-source-or-transport-id",
        }

    decision = __import__("asyncio").run(publish_or_skip(
        root, volume_name=volume.name, volume=volume, publisher=publisher,
    ))
    assert decision.reason == "published_verified"
    assert decision.identity.content_generation == identity.manifest_digest
    assert archive


def test_native_golden_backend_is_not_a_bat(tmp_path):
    spec = backend.BackendRegistry(tmp_path).native_golden_deploy()
    assert spec.bat_path is None
    assert spec.executable == ["modal", "deploy", "-m", "comfymodal_runtime.modal_app"]
    assert spec.kind == "deploy"
    assert spec.executable is not None
    assert "benchmark" not in " ".join(spec.executable)


def test_native_golden_deploy_publishes_before_backend(tmp_path, monkeypatch):
    from tools.v2_control import cli
    from tools.v2_control.backend import BackendResult

    events = []
    identity, _archive, _files = prepare_publication(_root(tmp_path))
    publication = SimpleNamespace(
        action="skip", reason="exact_match", identity=identity,
    )

    class FakeLock:
        def __init__(self, _path):
            pass

        def acquire(self, **_kwargs):
            events.append("lock")

        def release(self):
            events.append("unlock")

    class FakeRunner:
        def __init__(self, _repo_root, _env_builder):
            pass

        @staticmethod
        def build_command_line(_spec, _extra_args):
            return "modal deploy"

        def run(self, *_args, **_kwargs):
            events.append("backend")
            return BackendResult(
                exit_code=0, stdout="", stderr="", command="modal deploy",
                started_at="2026-01-01T00:00:00+00:00",
                ended_at="2026-01-01T00:00:01+00:00", elapsed_seconds=1.0,
            )

    monkeypatch.setattr(cli, "_publish_golden_custom_nodes", lambda _root: events.append("publish") or publication)
    monkeypatch.setattr(cli, "_active_workspace_credentials", lambda _root: {
        "MODAL_TOKEN_ID": "id", "MODAL_TOKEN_SECRET": "secret",
    })
    versions = iter((0, 1))
    monkeypatch.setattr(cli, "_app_version_number", lambda _app: events.append("version") or next(versions))
    monkeypatch.setattr(cli.backend_mod, "BackendRunner", FakeRunner)
    monkeypatch.setattr(cli.locking_mod, "DeployLock", FakeLock)
    monkeypatch.setattr(cli, "write_deployment_manifest", lambda *args, **kwargs: tmp_path / "deploy.json")
    args = SimpleNamespace(
        profile="golden_p1", app="golden-experimental", set=[], inherit=[],
        owner=None, dry_run=False, gpu=None, memory_mb=None, cpu=None,
    )

    assert cli.cmd_deploy(args, cli.Path(__file__).resolve().parents[1]) == 0
    assert events.index("publish") < events.index("version") < events.index("backend")


def test_deploy_manifest_uses_identity_captured_after_verified_publication(
    tmp_path, monkeypatch
):
    from tools.v2_control import cli
    from tools.v2_control.backend import BackendResult

    repo_root = Path(__file__).resolve().parents[1]
    components = cli.build_components(
        repo_root, "golden_p1", cli_options={"target.app": "golden-experimental"}
    )
    config, fingerprints = components[3], components[4]
    captured_before_publication = cli.capture_deploy_identity(fingerprints)
    captured_after_publication: list = []

    class FakeLock:
        def __init__(self, _path):
            pass

        def acquire(self, **_kwargs):
            pass

        def release(self):
            pass

    class FakeRunner:
        def __init__(self, _repo_root, _env_builder):
            pass

        @staticmethod
        def build_command_line(_spec, _extra_args):
            return "modal deploy"

        def run(self, *_args, **_kwargs):
            # A backend mutation must never leak into the captured identity.
            config.git.head = "backend-mutated"
            return BackendResult(
                exit_code=0, stdout="", stderr="", command="modal deploy",
                started_at="2026-01-01T00:00:00+00:00",
                ended_at="2026-01-01T00:00:01+00:00", elapsed_seconds=1.0,
            )

    def publish(_root):
        # The verified publication resolves before the final deploy fingerprint
        # is captured, so this mutation is part of the captured identity.
        config.git.head = "publication-mutated"
        captured_after_publication.append(cli.capture_deploy_identity(fingerprints))
        return SimpleNamespace(
            action="skip", reason="exact_match", identity=SimpleNamespace(
                generation="generation", identity_schema=1,
                packaging_policy_version=1, file_count=0, total_bytes=0,
                manifest_digest="digest",
            )
        )

    monkeypatch.setattr(cli, "_build_components_for_args", lambda *_args: components)
    monkeypatch.setattr(cli, "_publish_golden_custom_nodes", publish)
    monkeypatch.setattr(cli, "_active_workspace_credentials", lambda _root: {
        "MODAL_TOKEN_ID": "id", "MODAL_TOKEN_SECRET": "secret",
    })
    monkeypatch.setattr(cli.backend_mod, "BackendRunner", FakeRunner)
    monkeypatch.setattr(cli.locking_mod, "DeployLock", FakeLock)
    # Keep this identity-ordering test isolated from the repository's
    # persistent Golden receipt ledger.
    monkeypatch.setattr(
        cli, "_write_golden_deployment_receipt",
        lambda *args, **kwargs: tmp_path / "deployment-receipt.json",
    )
    args = SimpleNamespace(
        profile="golden_p1", app="golden-experimental", set=[], inherit=[],
        owner=None, dry_run=False, gpu=None, memory_mb=None, cpu=None,
    )

    versions = iter((0, 1))
    monkeypatch.setattr(cli, "_app_version_number", lambda _app: next(versions))
    assert cli.cmd_deploy(args, tmp_path) == 0

    captured = captured_after_publication[0]
    manifests = sorted((tmp_path / ".v2ctl" / "deployments").glob("deploy_*.json"))
    assert len(manifests) == 1
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert manifest["deployment_hash"] == captured.deploy_fingerprint
    assert manifest["deploy_fingerprint"] == captured.deploy_fingerprint
    assert manifest["deploy_inputs"] == cli._thaw_deploy_identity(captured.deploy_inputs)
    assert manifest["profile_config_fingerprint"] == captured.profile_config_fingerprint
    effective_env = manifest["effective_environment"]
    assert effective_env["COMFYMODAL_V2CTL_DEPLOYMENT_HASH"] == captured.deploy_fingerprint
    assert effective_env["COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT"] == captured.deploy_fingerprint
    assert effective_env["COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT"] == captured.profile_config_fingerprint
    # The publication mutation is captured; the backend mutation is not.
    assert captured.deploy_fingerprint != captured_before_publication.deploy_fingerprint
    assert fingerprints.deploy_fingerprint() != captured.deploy_fingerprint


def test_source_probe_skips_malformed_unrelated_manifest(tmp_path, monkeypatch):
    from tools.v2_control import cli

    repo_root = Path(__file__).resolve().parents[1]
    components = cli.build_components(
        repo_root, "production", cli_options={"target.app": "probe-experimental"}
    )
    fingerprints = components[4]
    deploy_fp = fingerprints.deploy_fingerprint()
    manifest_dir = tmp_path / "deployments"
    manifest_dir.mkdir()
    current = manifest_dir / "deploy_20260830-120000_current.json"
    current.write_text(json.dumps({"deploy_fingerprint": deploy_fp}), encoding="utf-8")
    (manifest_dir / "deploy_20260830-130000_unrelated.json").write_text(
        "{malformed", encoding="utf-8"
    )

    monkeypatch.setattr(cli, "_build_components_for_args", lambda *_args: components)
    monkeypatch.setattr(cli, "_deployment_manifest_dir", lambda _root: manifest_dir)
    import tools.v2_control.source_probe as source_probe
    monkeypatch.setattr(source_probe, "_load_workspace", lambda _root: {})
    monkeypatch.setattr(source_probe, "run_source_probe", lambda *_args, **_kwargs: (
        0,
        {
            "expected": {"git_head": "head"},
            "remote_summary": {
                "class_name": "ModalRuntimeEntrypointV2", "image_id": "image",
                "container_session_id": "container", "deployment_combined_hash": deploy_fp,
                "cwd": "/tmp", "comfymodal_runtime_file": "/tmp/runtime.py",
                "comfymodal_runtime_path": [],
            },
            "classification": {
                "modules": [], "ledger_flag": "0", "ledger_enabled": False,
                "ledger_record_event": False, "verdict": "MATCH",
            },
        },
    ))
    args = SimpleNamespace(
        profile="production", app="probe-experimental", set=[], inherit=[],
        owner=None, dry_run=False, gpu=None, memory_mb=None, cpu=None,
    )

    assert cli.cmd_source_probe(args, tmp_path) == 0
    updated = json.loads(current.read_text(encoding="utf-8"))
    assert updated["source_identity_status"] == "verified"


def test_native_golden_deploy_refuses_backend_when_publication_fails(monkeypatch):
    from tools.v2_control import cli

    backend_calls = []
    monkeypatch.setattr(cli, "_publish_golden_custom_nodes", lambda _root: (_ for _ in ()).throw(RuntimeError("publish failed")))
    monkeypatch.setattr(cli, "_active_workspace_credentials", lambda _root: {
        "MODAL_TOKEN_ID": "id", "MODAL_TOKEN_SECRET": "secret",
    })
    monkeypatch.setattr(cli.backend_mod, "BackendRunner", SimpleNamespace(
        build_command_line=lambda *_args: "modal deploy",
        __init__=lambda *_args: None,
        run=lambda *_args, **_kwargs: backend_calls.append(True),
    ))
    class FakeLock:
        def __init__(self, _path):
            pass
        def acquire(self, **_kwargs):
            pass
        def release(self):
            pass
    monkeypatch.setattr(cli.locking_mod, "DeployLock", FakeLock)
    args = SimpleNamespace(
        profile="golden_p1", app="golden-experimental", set=[], inherit=[],
        owner=None, dry_run=False, gpu=None, memory_mb=None, cpu=None,
    )
    assert cli.cmd_deploy(args, Path(__file__).resolve().parents[1]) == 1
    assert backend_calls == []
