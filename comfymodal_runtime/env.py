"""Environment value helpers shared by V2 runtime modules.

Single shared boolean-flag parser for every runtime env flag read.  All
module-local parsers were consolidated onto :func:`env_flag` in commit
9628c51 ("Complete V2 cache snapshot and timing fixes"); see
``tests/test_env_flags.py`` for the audited conversion table.

Exact semantics (do not change without updating the audit tests):

* Signature: ``env_flag(name: str, default: bool = False)``.
* If the variable is **absent** from the environment, ``default`` is
  returned unchanged (this preserves each call site's pre-commit absent
  semantics, e.g. ``os.environ.get(name, "1") == "1"`` → ``default=True``).
* Otherwise the raw value is stripped of surrounding whitespace and
  lowercased.  ``True`` only for the exact strings ``1``, ``true``,
  ``yes``, ``on``.
* Any other explicit value — ``0``, ``false``, ``no``, ``off``, the empty
  string, or an unrecognised token — is ``False``.  Explicit values are
  never ``None`` and never raise.
"""

from __future__ import annotations

import os


TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
"""Canonical truth set accepted by :func:`env_flag` after trim + lower."""


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in TRUE_VALUES
