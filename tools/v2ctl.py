"""v2ctl — canonical ComfyUI Modal V2 deploy/run control plane (Batch E32).

Local-only entrypoint.  Read docs/V2_CANONICAL_DEPLOY_RUN_CONTROL_PLANE.md
before deploying or running.  This tool is the ONLY supported deploy/run
interface for V2 agent work; do not invent ad-hoc Modal SDK deploys, direct
BAT invocations, or PowerShell set chains.
"""

import sys
from pathlib import Path

# ``python tools/v2ctl.py`` puts ``tools/`` on sys.path, not the repository
# root.  Make the package import deterministic without relying on PYTHONPATH.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from v2_control.cli import main

if __name__ == "__main__":
    sys.exit(main())
