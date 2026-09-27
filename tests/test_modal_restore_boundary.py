"""Pure tests for Modal snapshot-restore-begin boundary ingestion.

Covers:

  1. ``HH:MM:SS.mmm`` line resolved against a window → exact unix ns
  2. ISO8601 line
  3. dict-record input
  4. window enforcement (outside-window ignored; no window → last match)
  5. task association (task-tagged line preferred)
  6. 12h ambiguity (line near midnight)
  7. malformed lines ignored, no crash
  8. ``extract_restore_begin_from_result`` source precedence
  9. ``resolve_modal_restore_begin``: result-carried (no fetch), fetch
     failure → None, and log_lines parsing

No network, no Modal import — the fetch helper is monkeypatched.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest import mock

from comfymodal_runtime.modal_restore_boundary import (
    KEY,
    extract_restore_begin_from_result,
    parse_modal_restore_begin,
)
from tools.benchmark_v2_direct import resolve_modal_restore_begin

# Real-run reference timestamps (UTC): Modal log line at 01:12:57.388, python
# resume at 01:13:04.718 (command → response ≈ 21.994s).
_ANCHOR = datetime(2026, 8, 12, 1, 12, 40, tzinfo=timezone.utc)
_ANCHOR_NS = int(_ANCHOR.timestamp() * 1_000_000_000)
_WINDOW_END_NS = _ANCHOR_NS + 60_000_000_000
_EXPECTED_NS = int(
    datetime(2026, 8, 12, 1, 12, 57, 388000, tzinfo=timezone.utc).timestamp() * 1_000_000_000
)

_BANNER = "Restoring Function from memory snapshot"


def _ns(year: int, month: int, day: int, hour: int, minute: int, second: int,
        micro: int = 0) -> int:
    return int(
        datetime(year, month, day, hour, minute, second, micro, tzinfo=timezone.utc)
        .timestamp()
        * 1_000_000_000
    )


class ParseTimeOnlyLineTests(unittest.TestCase):
    def test_hh_mm_ss_mmm_line_resolved_against_window(self):
        parsed = parse_modal_restore_begin(
            [f"01:12:57.388  {_BANNER}"],
            window_start_unix_ns=_ANCHOR_NS,
            window_end_unix_ns=_WINDOW_END_NS,
        )
        self.assertEqual(parsed[KEY], _EXPECTED_NS)
        self.assertEqual(parsed["matches"], 1)
        self.assertFalse(parsed["matched_task"])
        self.assertIn(_BANNER, parsed["source_line"])

    def test_single_digit_hour_line(self):
        # 1:12:57.388 (1-digit hour) resolves identically.
        parsed = parse_modal_restore_begin(
            [f"1:12:57.388  {_BANNER}"],
            window_start_unix_ns=_ANCHOR_NS,
            window_end_unix_ns=_WINDOW_END_NS,
        )
        self.assertEqual(parsed[KEY], _EXPECTED_NS)

    def test_case_insensitive_and_partial_message_match(self):
        parsed = parse_modal_restore_begin(
            [f"01:12:57.388  restoring function from memory snapshot."],
            window_start_unix_ns=_ANCHOR_NS,
            window_end_unix_ns=_WINDOW_END_NS,
        )
        self.assertEqual(parsed[KEY], _EXPECTED_NS)
        # Tolerates a split variant of the marker.
        parsed2 = parse_modal_restore_begin(
            ["01:12:57.388  Restoring Function"] ,
            window_start_unix_ns=_ANCHOR_NS,
            window_end_unix_ns=_WINDOW_END_NS,
        )
        # "Restoring Function" alone does NOT contain the full marker → ignored.
        self.assertIsNone(parsed2[KEY])


class ParseIsoLineTests(unittest.TestCase):
    def test_iso8601_z_line(self):
        parsed = parse_modal_restore_begin(
            [f"2026-08-12T01:12:57.388Z  {_BANNER}"],
            window_start_unix_ns=_ANCHOR_NS,
            window_end_unix_ns=_WINDOW_END_NS,
        )
        self.assertEqual(parsed[KEY], _EXPECTED_NS)

    def test_space_date_form_line(self):
        parsed = parse_modal_restore_begin(
            [f"2026-08-12 01:12:57.388  {_BANNER}"],
            window_start_unix_ns=_ANCHOR_NS,
            window_end_unix_ns=_WINDOW_END_NS,
        )
        self.assertEqual(parsed[KEY], _EXPECTED_NS)

    def test_offset_iso_line(self):
        parsed = parse_modal_restore_begin(
            [f"2026-08-12T03:12:57.388+02:00  {_BANNER}"],
            window_start_unix_ns=_ANCHOR_NS,
            window_end_unix_ns=_WINDOW_END_NS,
        )
        self.assertEqual(parsed[KEY], _EXPECTED_NS)


class ParseDictRecordTests(unittest.TestCase):
    def test_dict_record_epoch_seconds(self):
        parsed = parse_modal_restore_begin(
            [
                {
                    "timestamp": _EXPECTED_NS / 1_000_000_000,
                    "message": _BANNER,
                    "task_id": "task-1",
                }
            ],
            window_start_unix_ns=_ANCHOR_NS,
            window_end_unix_ns=_WINDOW_END_NS,
        )
        self.assertEqual(parsed[KEY], _EXPECTED_NS)

    def test_dict_record_timestamp_ns(self):
        parsed = parse_modal_restore_begin(
            [
                {
                    "timestamp_ns": _EXPECTED_NS,
                    "message": _BANNER,
                }
            ],
            window_start_unix_ns=_ANCHOR_NS,
            window_end_unix_ns=_WINDOW_END_NS,
        )
        self.assertEqual(parsed[KEY], _EXPECTED_NS)

    def test_dict_record_iso_timestamp(self):
        parsed = parse_modal_restore_begin(
            [
                {
                    "timestamp": "2026-08-12T01:12:57.388Z",
                    "message": _BANNER,
                }
            ],
            window_start_unix_ns=_ANCHOR_NS,
            window_end_unix_ns=_WINDOW_END_NS,
        )
        self.assertEqual(parsed[KEY], _EXPECTED_NS)


class WindowEnforcementTests(unittest.TestCase):
    def test_outside_window_match_ignored(self):
        lines = [
            f"01:12:50.000  {_BANNER}",
            f"01:12:57.388  {_BANNER}",
        ]
        # Window ends at 01:12:52 — the later 01:12:57.388 line is outside.
        parsed = parse_modal_restore_begin(
            lines,
            window_start_unix_ns=_ANCHOR_NS,
            window_end_unix_ns=_ANCHOR_NS + 12_000_000_000,  # 01:12:52
        )
        self.assertEqual(parsed[KEY], _ns(2026, 8, 12, 1, 12, 50))

    def test_all_outside_window_returns_none(self):
        parsed = parse_modal_restore_begin(
            [f"01:14:00.000  {_BANNER}"],
            window_start_unix_ns=_ANCHOR_NS,
            window_end_unix_ns=_WINDOW_END_NS,
        )
        self.assertIsNone(parsed[KEY])

    def test_no_window_last_match_wins(self):
        lines = [
            f"01:12:50.000  {_BANNER}",
            f"01:12:57.388  {_BANNER}",
        ]
        parsed = parse_modal_restore_begin(lines, window_start_unix_ns=_ANCHOR_NS)
        self.assertEqual(parsed[KEY], _EXPECTED_NS)
        self.assertFalse(parsed["matched_task"])


class TaskAssociationTests(unittest.TestCase):
    def test_task_tagged_line_preferred(self):
        records = [
            {
                "timestamp": _EXPECTED_NS / 1_000_000_000,
                "message": _BANNER,
                "task_id": "task-other",
            },
            {
                "timestamp": (_EXPECTED_NS + 1_000_000_000) / 1_000_000_000,
                "message": _BANNER,
                "task_id": "task-9",
            },
        ]
        parsed = parse_modal_restore_begin(
            records,
            task_id="task-9",
            window_start_unix_ns=_ANCHOR_NS,
            window_end_unix_ns=_WINDOW_END_NS,
        )
        self.assertEqual(parsed[KEY], _EXPECTED_NS + 1_000_000_000)
        self.assertTrue(parsed["matched_task"])

    def test_task_mentioned_in_message_preferred(self):
        records = [
            {
                "timestamp": _EXPECTED_NS / 1_000_000_000,
                "message": _BANNER,
            },
            {
                "timestamp": (_EXPECTED_NS + 1_000_000_000) / 1_000_000_000,
                "message": f"{_BANNER} (task task-9)",
            },
        ]
        parsed = parse_modal_restore_begin(
            records,
            task_id="task-9",
            window_start_unix_ns=_ANCHOR_NS,
            window_end_unix_ns=_WINDOW_END_NS,
        )
        self.assertEqual(parsed[KEY], _EXPECTED_NS + 1_000_000_000)
        self.assertTrue(parsed["matched_task"])

    def test_no_task_match_falls_back_to_last_in_window(self):
        records = [
            {
                "timestamp": _EXPECTED_NS / 1_000_000_000,
                "message": _BANNER,
                "task_id": "task-other",
            },
        ]
        parsed = parse_modal_restore_begin(
            records,
            task_id="task-9",
            window_start_unix_ns=_ANCHOR_NS,
            window_end_unix_ns=_WINDOW_END_NS,
        )
        self.assertEqual(parsed[KEY], _EXPECTED_NS)
        self.assertFalse(parsed["matched_task"])


class TwelveHourAmbiguityTests(unittest.TestCase):
    def _parse_at(self, anchor: datetime, line: str) -> dict:
        # No window → the HH:MM:SS.mmm resolution anchors on time.time().
        with mock.patch("time.time", return_value=anchor.timestamp()):
            return parse_modal_restore_begin([line])

    def test_time_before_anchor_by_more_than_12h_rolls_forward(self):
        # Anchor at 23:50 — the 00:10 line belongs to the NEXT day.
        parsed = self._parse_at(
            datetime(2026, 8, 12, 23, 50, tzinfo=timezone.utc),
            f"00:10:00.000  {_BANNER}",
        )
        self.assertEqual(parsed[KEY], _ns(2026, 8, 13, 0, 10, 0))

    def test_time_after_anchor_by_more_than_12h_rolls_backward(self):
        # Anchor at 01:00 — the 14:10 line belongs to the PREVIOUS day.
        parsed = self._parse_at(
            datetime(2026, 8, 12, 1, 0, tzinfo=timezone.utc),
            f"14:10:00.000  {_BANNER}",
        )
        self.assertEqual(parsed[KEY], _ns(2026, 8, 11, 14, 10, 0))

    def test_within_12h_no_roll(self):
        parsed = self._parse_at(
            datetime(2026, 8, 12, 1, 0, tzinfo=timezone.utc),
            f"06:00:00.000  {_BANNER}",
        )
        self.assertEqual(parsed[KEY], _ns(2026, 8, 12, 6, 0, 0))


class MalformedInputTests(unittest.TestCase):
    def test_malformed_lines_ignored_no_crash(self):
        parsed = parse_modal_restore_begin(
            [
                "junk line without timestamp",
                "",
                None,
                12345,
                {"message": _BANNER},  # no timestamp
                {"timestamp": "not-a-timestamp", "message": _BANNER},
                "99:99:99.000  " + _BANNER,  # invalid clock time
                "2026-13-99 01:12:57.388  " + _BANNER,  # invalid date
            ],
            window_start_unix_ns=_ANCHOR_NS,
            window_end_unix_ns=_WINDOW_END_NS,
        )
        self.assertIsNone(parsed[KEY])
        self.assertEqual(parsed["matches"], 0)

    def test_non_matching_message_ignored(self):
        parsed = parse_modal_restore_begin(
            ["01:12:57.388  Some unrelated log line"],
            window_start_unix_ns=_ANCHOR_NS,
            window_end_unix_ns=_WINDOW_END_NS,
        )
        self.assertIsNone(parsed[KEY])
        self.assertEqual(parsed["matches"], 0)

    def test_empty_lines(self):
        parsed = parse_modal_restore_begin([], window_start_unix_ns=_ANCHOR_NS)
        self.assertIsNone(parsed[KEY])
        self.assertEqual(parsed["matches"], 0)


class ExtractRestoreBeginFromResultTests(unittest.TestCase):
    def test_result_root_key(self):
        result = {KEY: 111}
        self.assertEqual(extract_restore_begin_from_result(result), 111)

    def test_timing_dict(self):
        result = {}
        timing = {KEY: 222}
        self.assertEqual(extract_restore_begin_from_result(result, timing), 222)

    def test_result_root_beats_timing(self):
        result = {KEY: 111}
        timing = {KEY: 222}
        self.assertEqual(extract_restore_begin_from_result(result, timing), 111)

    def test_local_timing(self):
        result = {"local_timing": {KEY: 333}}
        self.assertEqual(extract_restore_begin_from_result(result), 333)

    def test_trace_metadata(self):
        result = {"trace": {"metadata": {KEY: 444}}}
        self.assertEqual(extract_restore_begin_from_result(result), 444)

    def test_first_found_wins_order(self):
        result = {"local_timing": {KEY: 333}, "trace": {"metadata": {KEY: 444}}}
        self.assertEqual(extract_restore_begin_from_result(result), 333)

    def test_invalid_values_ignored(self):
        result = {KEY: "not-a-number"}
        self.assertIsNone(extract_restore_begin_from_result(result))
        result = {KEY: -5}
        self.assertIsNone(extract_restore_begin_from_result(result))
        self.assertIsNone(extract_restore_begin_from_result(None))
        self.assertIsNone(extract_restore_begin_from_result({}, {}))


class ResolveModalRestoreBeginTests(unittest.TestCase):
    def test_result_carried_value_no_fetch(self):
        result = {KEY: 123456789}
        with mock.patch(
            "tools.benchmark_v2_direct._fetch_modal_restore_begin_logs_async",
        ) as fetch_mock:
            value = resolve_modal_restore_begin(result)
        self.assertEqual(value, 123456789)
        fetch_mock.assert_not_called()

    def test_fetch_failure_returns_none(self):
        async def _boom(*args: object, **kwargs: object):
            raise RuntimeError("no network")

        with mock.patch(
            "tools.benchmark_v2_direct._fetch_modal_restore_begin_logs_async",
            _boom,
        ):
            value = resolve_modal_restore_begin(
                {},
                window_start_unix_ns=_ANCHOR_NS,
                window_end_unix_ns=_WINDOW_END_NS,
            )
        self.assertIsNone(value)

    def test_log_lines_parsed(self):
        with mock.patch(
            "tools.benchmark_v2_direct._fetch_modal_restore_begin_logs_async",
        ) as fetch_mock:
            value = resolve_modal_restore_begin(
                {},
                log_lines=[f"01:12:57.388  {_BANNER}"],
                task_id="task-9",
                window_start_unix_ns=_ANCHOR_NS,
                window_end_unix_ns=_WINDOW_END_NS,
            )
        self.assertEqual(value, _EXPECTED_NS)
        fetch_mock.assert_not_called()

    def test_log_lines_parse_none(self):
        with mock.patch(
            "tools.benchmark_v2_direct._fetch_modal_restore_begin_logs_async",
        ) as fetch_mock:
            value = resolve_modal_restore_begin(
                {},
                log_lines=["no match here"],
                window_start_unix_ns=_ANCHOR_NS,
                window_end_unix_ns=_WINDOW_END_NS,
            )
        self.assertIsNone(value)
        fetch_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
