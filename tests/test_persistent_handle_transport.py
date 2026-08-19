"""Persistent local-handle transport regression suite (Step-3 payload proof).

Builds on the REAL persistent local-handle machinery:

  - ``comfymodal_runtime.local_handle_owner``: an in-process
    ``LocalHandleOwner`` server whose ``_resolve_modal`` is monkeypatched to a
    fake Modal handle whose ``run_plan_stream.remote_gen.aio(payload,
    request_id=...)`` captures the forwarded payload and returns a fake
    stream yielding one result event (mirroring the owner's real
    ``_open_plan_stream`` contract).
  - the state file is written with ``owner_mod._atomic_write_json`` and the
    REAL ``PersistentHandleClient(state_path=..., auth_token=...)`` adopts it
    via ``_ensure_owner`` (no subprocess is spawned — the state race is won
    by the in-process server).

The forwarded payload is the full Step-3 plan dict: a realistic 41-class
``registry_proof`` built by the REAL ``build_workflow_registry_proof`` over
41 real classes in this test module (roots = the repo root), plus the
transport's direct path (``ModalTransport`` with a fake handle) for
persistent/direct equivalence.

All tests are local (no Modal calls, no paid anything, no ComfyUI imports).
"""

import asyncio
import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from comfymodal_runtime import local_handle_owner as owner_mod
from comfymodal_runtime.contracts import (
    DEPLOYMENT_PROOF_SCHEMA_VERSION,
    ExecutionPlan,
    evaluate_plan_snapshot_parity,
)
from comfymodal_runtime.local_handle_client import (
    IPC_STREAM_LIMIT as CLIENT_IPC_STREAM_LIMIT,
    PersistentHandleClient,
)
from comfymodal_runtime.modal_transport import ModalTransport
from comfymodal_runtime.registry_proof import (
    build_workflow_registry_proof,
    evaluate_workflow_registry_parity,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
COMFYUI_ROOT = REPO_ROOT.parents[1]  # the parent ComfyUI directory

_PROOF_CLASS_COUNT = 41
_AUTH = "test-auth-token"

# 41 real classes in THIS module file: each resolves to a canonical identity
# through the real class_canonical_identity (module file under the repo root).
for _i in range(_PROOF_CLASS_COUNT):
    globals()[f"_ProofClass{_i:02d}"] = type(
        f"_ProofClass{_i:02d}", (), {"__module__": __name__, "__qualname__": f"_ProofClass{_i:02d}"}
    )


def _proof_class_mappings() -> dict[str, type]:
    return {f"ProofClass{i:02d}": globals()[f"_ProofClass{i:02d}"] for i in range(_PROOF_CLASS_COUNT)}


def _proof_class_workflow() -> dict[str, dict]:
    return {str(i): {"class_type": f"ProofClass{i:02d}", "inputs": {}} for i in range(_PROOF_CLASS_COUNT)}


_PROOF_CACHE: dict | None = None


def _build_41_class_proof() -> dict:
    """Real 41-class workflow registry proof (deterministic, cached)."""
    global _PROOF_CACHE
    if _PROOF_CACHE is None:
        _PROOF_CACHE = build_workflow_registry_proof(
            _proof_class_workflow(), _proof_class_mappings(), roots=[str(REPO_ROOT)]
        )
    return _PROOF_CACHE


def _make_identity(proof=None, **overrides) -> dict:
    identity = {
        "complete": True,
        "schema_version": 1,
        "deployment_combined_hash": "X",
        "custom_nodes_generation": "G",
        "dependency_manifest_identity": "D1",
        "registry_fingerprint": "F",
        "registry_proof_complete": True,
        "registry_proof": proof if proof is not None else _build_41_class_proof(),
    }
    identity.update(overrides)
    return identity


def _make_plan_dict(identity=None, proof=None) -> dict:
    return {
        "workflow": _proof_class_workflow(),
        "workflow_hash": "h",
        "source_workflow_hash": "h",
        "output_node_ids": ["40"],
        "input_images": {},
        "production_report": {},
        "request_metadata": {},
        "deployment_identity": identity if identity is not None else _make_identity(proof=proof),
    }


# ── Fake Modal handle machinery ─────────────────────────────────────────────


class _FakeEventStream:
    """A single-result async iterator (mirrors remote_gen.aio's stream)."""

    def __init__(self, events=None):
        self._events = list(events) if events is not None else [{"type": "result", "data": {"status": "ok"}}]
        self._i = 0
        self.input_id = "fake-input"
        self.input_created_at = 123.0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._i >= len(self._events):
            raise StopAsyncIteration
        event = self._events[self._i]
        self._i += 1
        return event

    async def aclose(self):
        pass


class _FakeRemoteGen:
    def __init__(self, handle):
        self._handle = handle

    def aio(self, payload, request_id=""):
        self._handle.captured = {"payload": payload, "request_id": request_id}
        return _FakeEventStream()


class _FakeMethodStub:
    def __init__(self, handle):
        self.remote_gen = _FakeRemoteGen(handle)


class _FakeHandle:
    """``run_plan_stream.remote_gen.aio(...)`` compatible fake handle.

    ``captured`` stays ``{}`` until a forward happens, so "no forward" is
    ``{}`` and a successful forward is ``{"payload": ..., "request_id": ...}``.
    """

    def __init__(self):
        self.captured: dict = {}
        self.run_plan_stream = _FakeMethodStub(self)


# ── canonical_execution load (for the production plan builder) ──────────────


def _load_canonical():
    spec = importlib.util.spec_from_file_location(
        "canonical_execution", REPO_ROOT / "canonical_execution.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["canonical_execution"] = mod
    spec.loader.exec_module(mod)
    return mod


_REMOVE = object()


class _stub_modules:
    """Context manager installing module stubs into sys.modules."""

    def __init__(self, stubs):
        self._stubs = stubs
        self._saved = {}

    def __enter__(self):
        for name, value in self._stubs.items():
            self._saved[name] = sys.modules.get(name)
            if value is _REMOVE:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value
        return self

    def __exit__(self, exc_type, exc, tb):
        for name, value in self._saved.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value
        return False


# ── Owner server fixture ────────────────────────────────────────────────────


class TestPersistentHandleTransport(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.td = self._td.name
        self._clients: list[PersistentHandleClient] = []

    def tearDown(self):
        for client in self._clients:
            client.shutdown()
        self._td.cleanup()

    async def _start_owner(self, limit=None, resolve=None):
        """Start an in-process owner server with a fake Modal handle."""
        owner = owner_mod.LocalHandleOwner()
        fake = _FakeHandle()

        async def _resolve(key, workspace):
            return (fake, False)

        owner._resolve_modal = resolve or _resolve
        server = await asyncio.start_server(
            lambda reader, writer: owner_mod._handle_connection(reader, writer, _AUTH, owner),
            host="127.0.0.1",
            port=0,
            limit=limit or owner_mod.IPC_STREAM_LIMIT,
        )
        port = server.sockets[0].getsockname()[1]
        state_path = os.path.join(self.td, "owner.json")
        owner_mod._atomic_write_json(Path(state_path), {
            "schema_version": 1,
            "status": "ready",
            "pid": os.getpid(),
            "port": port,
            "auth_token": _AUTH,
            "started_at": 0.0,
        })
        return server, fake, state_path, port

    async def _forward_persistent(self, plan_dict, request_id="req-1"):
        """Real PersistentHandleClient round trip through the owner server."""
        server, fake, state_path, port = await self._start_owner()
        try:
            client = PersistentHandleClient(
                state_path=state_path, auth_token=_AUTH, repo_root=str(REPO_ROOT)
            )
            self._clients.append(client)
            await client._ensure_owner()
            proxy = await client.run_plan_stream(
                key={}, workspace={}, payload=plan_dict, request_id=request_id
            )
            events = [ev async for ev in proxy]
            await proxy.aclose()
        finally:
            server.close()
            await server.wait_closed()
        return fake, events

    # ── 1. Payload fidelity through the persistent IPC ─────────────────

    async def test_persistent_ipc_preserves_registry_proof(self):
        """The forwarded payload carries the 41-class registry_proof intact."""
        plan_dict = _make_plan_dict()
        fake, events = await self._forward_persistent(plan_dict)
        self.assertNotEqual(fake.captured, {})  # a forward happened
        self.assertEqual(fake.captured["request_id"], "req-1")
        identity = fake.captured["payload"]["deployment_identity"]
        proof = identity["registry_proof"]
        self.assertEqual(proof["workflow_class_count"], 41)
        self.assertEqual(len(proof["classes"]), 41)
        self.assertIs(proof["complete"], True)
        self.assertIs(identity["registry_proof_complete"], True)
        self.assertEqual(len(events), 1)

    async def test_nested_deployment_identity_survives(self):
        """ALL deployment_identity keys and values survive the round trip
        unchanged (deep equality on the whole dict)."""
        identity = _make_identity()
        plan_dict = _make_plan_dict(identity=identity)
        fake, _ = await self._forward_persistent(plan_dict)
        forwarded = fake.captured["payload"]["deployment_identity"]
        self.assertEqual(forwarded, identity)
        self.assertEqual(sorted(forwarded.keys()), sorted(identity.keys()))

    async def test_41_class_realistic_proof_survives(self):
        """The realistic 41-class proof's identities dict equals the input
        byte-for-byte after the JSON IPC round trip."""
        proof = _build_41_class_proof()
        plan_dict = _make_plan_dict(identity=_make_identity(proof=proof))
        fake, _ = await self._forward_persistent(plan_dict)
        forwarded_proof = fake.captured["payload"]["deployment_identity"]["registry_proof"]
        self.assertEqual(forwarded_proof, proof)
        self.assertEqual(forwarded_proof["identities"], proof["identities"])
        self.assertEqual(forwarded_proof["classes"], proof["classes"])

    async def test_empty_proof_survives_as_empty(self):
        """An empty registry_proof survives as empty, and a later evaluator
        call on it still fails closed."""
        plan_dict = _make_plan_dict(identity=_make_identity(proof={}))
        fake, _ = await self._forward_persistent(plan_dict)
        forwarded_proof = fake.captured["payload"]["deployment_identity"]["registry_proof"]
        self.assertEqual(forwarded_proof, {})
        result = evaluate_workflow_registry_parity(
            {}, {"schema_version": 1, "class_count": 1, "classes": {"A": "I1"}, "incomplete_classes": []}
        )
        self.assertIs(result["workflow_registry_match"], False)
        self.assertEqual(result["reason"], "plan_registry_proof_unavailable")

    # ── 2. Protocol failures close explicitly ───────────────────────────

    async def test_malformed_payload_fails_explicitly(self):
        """A non-dict (unparseable) request body over the raw socket closes
        the connection WITHOUT forwarding anything."""
        server, fake, state_path, port = await self._start_owner()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(b"not-json\n")
            await writer.drain()
            data = await reader.read()
            self.assertEqual(data, b"")  # EOF: server closed without a frame
            writer.close()
            await writer.wait_closed()
        finally:
            server.close()
            await server.wait_closed()
        self.assertEqual(fake.captured, {})  # nothing was forwarded

    async def test_oversize_payload_fails_explicitly(self):
        """A request line beyond the server stream limit closes the
        connection (LimitOverrunError path) without forwarding anything."""
        self.assertEqual(owner_mod.IPC_STREAM_LIMIT, 128 * 1024 * 1024)
        self.assertEqual(CLIENT_IPC_STREAM_LIMIT, 128 * 1024 * 1024)
        server, fake, state_path, port = await self._start_owner(limit=1024)
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port, limit=65536)
            writer.write(b"x" * 4096 + b"\n")
            await writer.drain()
            data = await reader.read()
            self.assertEqual(data, b"")
            writer.close()
            await writer.wait_closed()
        finally:
            server.close()
            await server.wait_closed()
        self.assertEqual(fake.captured, {})  # nothing was forwarded

    async def test_normal_payload_below_size_bound(self):
        """The serialized client request (incl. the 41-class proof) is far
        below the 128 MiB IPC stream limit."""
        plan_dict = _make_plan_dict()
        request = {
            "op": "run_plan_stream",
            "auth": _AUTH,
            "key": {},
            "workspace": {},
            "payload": dict(plan_dict),
            "request_id": "req-1",
            "gpu": None,
        }
        raw = json.dumps(request, default=str, ensure_ascii=False).encode("utf-8")
        self.assertGreater(len(raw), 0)
        self.assertLess(len(raw), owner_mod.IPC_STREAM_LIMIT)

    # ── 3. Unknown / future fields ──────────────────────────────────────

    async def test_unknown_future_fields_survive(self):
        """A synthetic future field in deployment_identity survives the round
        trip unchanged (no shadow-schema reconstruction)."""
        identity = _make_identity(future_field={"x": 1})
        plan_dict = _make_plan_dict(identity=identity)
        fake, _ = await self._forward_persistent(plan_dict)
        forwarded = fake.captured["payload"]["deployment_identity"]
        self.assertEqual(forwarded["future_field"], {"x": 1})
        self.assertEqual(forwarded, identity)

    # ── 4. Direct transport path ────────────────────────────────────────

    async def test_direct_modal_path_preserves_proof(self):
        """The V2 direct path (ModalTransport with a fake handle) forwards a
        plan built by the production plan builder whose registry_proof is
        present and complete."""
        workflow = _proof_class_workflow()
        nodes_mod = types.ModuleType("nodes")
        setattr(nodes_mod, "NODE_CLASS_MAPPINGS", _proof_class_mappings())
        canonical = _load_canonical()
        with _stub_modules({"nodes": nodes_mod}):
            plan = canonical.build_execution_plan(
                workflow, prompt_id="t9", validate=False, collect_validation_proof=False
            )
        self.assertIs(plan.deployment_identity["registry_proof_complete"], True)
        transport = ModalTransport()
        fake = _FakeHandle()
        with mock.patch.object(transport, "_v2_handle", return_value=fake), \
             mock.patch.object(ModalTransport, "_persistent_enabled", return_value=False):
            events = []
            async for ev in transport.run_plan_stream(plan, trace={}, gpu=None, workspace=None):
                events.append(ev)
        self.assertEqual(len(events), 1)
        captured = fake.captured["payload"]
        proof = captured["deployment_identity"]["registry_proof"]
        self.assertEqual(len(proof["classes"]), 41)
        self.assertIs(proof["complete"], True)
        self.assertIs(captured["deployment_identity"]["registry_proof_complete"], True)

    async def test_persistent_and_direct_forwarded_payloads_equivalent(self):
        """Both transport paths forward a plan dict whose deployment_identity
        deep-equals the input."""
        plan_dict = _make_plan_dict()
        # Persistent path.
        fake_persistent, _ = await self._forward_persistent(plan_dict, request_id="eq-1")
        persistent_identity = fake_persistent.captured["payload"]["deployment_identity"]
        self.assertEqual(persistent_identity, plan_dict["deployment_identity"])
        # Direct path over the same plan.
        plan = ExecutionPlan.from_dict(plan_dict)
        transport = ModalTransport()
        fake_direct = _FakeHandle()
        with mock.patch.object(transport, "_v2_handle", return_value=fake_direct), \
             mock.patch.object(ModalTransport, "_persistent_enabled", return_value=False):
            events = []
            async for ev in transport.run_plan_stream(plan, trace={}, gpu=None, workspace=None):
                events.append(ev)
        direct_identity = fake_direct.captured["payload"]["deployment_identity"]
        self.assertEqual(direct_identity, plan_dict["deployment_identity"])
        self.assertEqual(persistent_identity, direct_identity)

    # ── 5. Backward compatibility ───────────────────────────────────────

    async def test_plan_without_registry_proof_backward_compatible(self):
        """A deployment identity without registry_proof keeps the legacy
        fallback (parity ineligible, proof-less identity preserved through the
        transport)."""
        identity = _make_identity()
        identity.pop("registry_proof")
        identity.pop("registry_proof_complete")
        plan = ExecutionPlan.from_dict(_make_plan_dict(identity=identity))
        snapshot = {
            "schema_version": DEPLOYMENT_PROOF_SCHEMA_VERSION,
            "valid": True,
            "complete": True,
            "deployment_combined_hash": "X",
            "custom_nodes_generation": "G",
            "dependency_manifest_identity": "D1",
            "registry_fingerprint": "F",
            "registry_manifest": {
                "schema_version": 1, "class_count": 1,
                "classes": {"A": "IA"}, "incomplete_classes": [],
            },
        }
        result = evaluate_plan_snapshot_parity(plan.deployment_identity, snapshot)
        self.assertIs(result["workflow_registry_match"], False)
        self.assertIs(result["future_fast_path_eligible"], False)
        self.assertIn("workflow_registry_mismatch", result["future_fast_path_ineligible_reason"])
        # Transport round trip preserves the proof-less identity unchanged.
        plan_dict = _make_plan_dict(identity=identity)
        fake, _ = await self._forward_persistent(plan_dict)
        forwarded = fake.captured["payload"]["deployment_identity"]
        self.assertEqual(forwarded, identity)
        self.assertNotIn("registry_proof", forwarded)

    async def test_future_deployment_identity_field_not_discarded(self):
        """A future deployment-identity key survives BOTH the transport round
        trip and the ExecutionPlan.from_dict/to_dict round trip."""
        identity = _make_identity(future_field={"x": 1}, another_future="v")
        plan_dict = _make_plan_dict(identity=identity)
        fake, _ = await self._forward_persistent(plan_dict)
        forwarded = fake.captured["payload"]["deployment_identity"]
        self.assertEqual(forwarded["future_field"], {"x": 1})
        self.assertEqual(forwarded["another_future"], "v")
        # ExecutionPlan serialization round trip also preserves the key.
        plan = ExecutionPlan.from_dict(plan_dict)
        round_tripped = plan.to_dict()["deployment_identity"]
        self.assertEqual(round_tripped["future_field"], {"x": 1})
        self.assertEqual(round_tripped["another_future"], "v")


if __name__ == "__main__":
    unittest.main()

# -- D1 registry-proof store isolation (never write the real shared store;
#    see tests/d1_store_isolation.py) -----------------------------------
import sys as _d1_sys
from pathlib import Path as _d1_Path

if str(_d1_Path(__file__).resolve().parents[1]) not in _d1_sys.path:
    _d1_sys.path.insert(0, str(_d1_Path(__file__).resolve().parents[1]))
from tests.d1_store_isolation import isolate_module_store, restore_module_store


def setUpModule():
    isolate_module_store()


def tearDownModule():
    restore_module_store()
