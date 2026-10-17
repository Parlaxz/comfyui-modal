"""Comparator: PASS only from executable evidence. No hand-typed PASS.

Verdicts: PASS | FAIL | INTENTIONAL_DIFFERENCE | RETIRED_BY_AHMED | BLOCKED_ENVIRONMENT | UNKNOWN
The last three require explicit approval fields; the harness itself only ever
emits PASS / FAIL / UNKNOWN / BLOCKED_ENVIRONMENT.
"""
from __future__ import annotations

ALLOWED = {"PASS", "FAIL", "INTENTIONAL_DIFFERENCE", "RETIRED_BY_AHMED",
           "BLOCKED_ENVIRONMENT", "UNKNOWN"}


def compare(check_id: str, legacy, vue) -> tuple[str, str]:
    """Compare one named field of two traces. Returns (verdict, detail)."""
    for side in (legacy, vue):
        if isinstance(side, str) and side.startswith("UNPROVEN:"):
            return "UNKNOWN", f"{check_id}: {side}"
    if legacy == "UNKNOWN" or vue == "UNKNOWN" or legacy in ("", None) or vue in ("", None):
        if legacy in ("", None) and vue in ("", None):
            return "UNKNOWN", f"{check_id}: both sides empty"
        # One side UNKNOWN with the other present is not parity.
        if legacy == "UNKNOWN" or vue == "UNKNOWN":
            return "UNKNOWN", f"{check_id}: legacy={legacy!r} vue={vue!r}"
    if legacy == vue:
        return "PASS", f"{check_id}: match ({legacy!r})"
    return "FAIL", f"{check_id}: legacy={legacy!r} vue={vue!r}"


def roll_up(check_verdicts: list[str]) -> str:
    if any(v == "FAIL" for v in check_verdicts):
        return "FAIL"
    if any(v == "UNKNOWN" for v in check_verdicts):
        return "UNKNOWN"
    if check_verdicts and all(v == "PASS" for v in check_verdicts):
        return "PASS"
    return "UNKNOWN"
