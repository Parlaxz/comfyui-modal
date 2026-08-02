"""Environment value helpers shared by V2 runtime modules."""

from __future__ import annotations

import os


TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in TRUE_VALUES
