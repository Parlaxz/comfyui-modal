from __future__ import annotations

import pytest

from comfymodal_runtime.golden_io_process_v2 import (
    C0ControlLayout,
    C0FillRequest,
    C0ProtocolError,
    C0SourceSession,
    reconcile_destination_coverage,
)


pytestmark = pytest.mark.fast_unit


def _request(request_id: int, producer_id: int = 0) -> C0FillRequest:
    return C0FillRequest(
        request_id=request_id,
        arena_epoch=7,
        role="clip",
        source="/tmp/checkpoint.safetensors",
        slot_index=request_id % 4,
        slot_generation=1,
        source_offset=request_id * 8,
        destination_offset=request_id * 8,
        length=8,
        producer_id=producer_id,
    )


def _ready(session: C0SourceSession, ticket) -> None:
    request = C0ControlLayout.read_request(session.shm.buf, ticket.lane)
    C0ControlLayout.write_response(
        session.shm.buf,
        ticket.lane,
        ticket.sequence,
        {
            "op": "ready",
            "request_id": request["request_id"],
            "arena_epoch": request["arena_epoch"],
            "slot_index": request["slot_index"],
            "slot_generation": request["slot_generation"],
            "returned_bytes": request["length"],
        },
    )


def test_control_descriptor_crc_and_stale_identity_fail_closed():
    session = C0SourceSession(arena_epoch=7, child_alive=lambda: True)
    try:
        ticket = session.submit(_request(1))
        assert C0ControlLayout.request_crc_valid(session.shm.buf, ticket.lane)
        base = C0ControlLayout.lane_offset(ticket.lane)
        assert C0ControlLayout._U64.unpack_from(session.shm.buf, base + 8)[0] == 0
        C0ControlLayout._U64.pack_into(session.shm.buf, base + 24, 999)
        assert not C0ControlLayout.request_crc_valid(session.shm.buf, ticket.lane)
    finally:
        session.close()


def test_four_sticky_lanes_steal_and_reuse_only_after_consume():
    session = C0SourceSession(arena_epoch=7, child_alive=lambda: True)
    try:
        tickets = [session.submit(_request(i + 1, producer_id=0)) for i in range(4)]
        assert [ticket.lane for ticket in tickets] == [0, 1, 2, 3]
        with pytest.raises(C0ProtocolError, match="no_free_lane"):
            session.submit(_request(5), timeout_s=0.001)
        _ready(session, tickets[0])
        with pytest.raises(C0ProtocolError, match="consume_before_done"):
            # The descriptor is DONE, but this assertion is intentionally made
            # against a different sequence and proves reuse is ticket-gated.
            session.consume(type(tickets[0])(tickets[0].lane, tickets[0].sequence + 1, tickets[0].request_id))
        session.consume(tickets[0])
        stolen = session.submit(_request(6, producer_id=0), timeout_s=0.1)
        assert stolen.lane == 0
    finally:
        session.close()


def test_payload_metadata_is_complete_before_done_publication():
    session = C0SourceSession(arena_epoch=7, child_alive=lambda: True)
    try:
        ticket = session.submit(_request(1))
        _ready(session, ticket)
        base = C0ControlLayout.lane_offset(ticket.lane)
        assert C0ControlLayout._U32.unpack_from(session.shm.buf, base + 16)[0] == C0ControlLayout.STATE_DONE
        assert C0ControlLayout.response_crc_valid(session.shm.buf, ticket.lane)
        response = C0ControlLayout.read_response(session.shm.buf, ticket.lane)
        assert response["returned_bytes"] == 8
    finally:
        session.close()


def test_child_error_and_exact_coverage_are_not_downgraded():
    session = C0SourceSession(arena_epoch=7, child_alive=lambda: True)
    try:
        ticket = session.submit(_request(1))
        request = C0ControlLayout.read_request(session.shm.buf, ticket.lane)
        C0ControlLayout.write_response(
            session.shm.buf,
            ticket.lane,
            ticket.sequence,
            {
                "op": "error",
                "request_id": request["request_id"],
                "arena_epoch": request["arena_epoch"],
                "slot_index": request["slot_index"],
                "slot_generation": request["slot_generation"],
                "returned_bytes": 0,
                "error": "child_failed",
            },
        )
        with pytest.raises(C0ProtocolError, match="child_failed"):
            session.wait(ticket, timeout_s=0.1)
        assert reconcile_destination_coverage([(0, 8), (8, 16)], 16)["ok"]
        assert not reconcile_destination_coverage([(0, 8), (9, 16)], 16)["ok"]
    finally:
        session.close()
