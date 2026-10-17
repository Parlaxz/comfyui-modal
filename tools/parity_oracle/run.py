"""Runner entry: build comprehensive manifest + generated report + coverage.

Usage: python -m tools.parity_oracle.run  (repo root as CWD)
Outputs: parity/manifest.json, parity/REPORT.md, parity/coverage.md
"""
from __future__ import annotations

from .build_manifest import main

if __name__ == "__main__":
    raise SystemExit(main())
