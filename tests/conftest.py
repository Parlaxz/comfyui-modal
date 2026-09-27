"""Test-tier contract.

FAST_UNIT: under one second; pure policy/config tests only, with no ComfyUI,
Modal, model scans, custom-node discovery, or CUDA imports.
COMPONENT: under five seconds; a bounded local subsystem integration.
HEAVY_LOCAL: explicit opt-in for comfyapp/ComfyUI/model lifecycle coverage.
REMOTE: explicit deployment or Modal validation, never part of the fast suite.
"""


def pytest_configure(config):
    for name, description in (
        ("fast_unit", "dependency-free fast unit test"),
        ("component", "bounded component integration test"),
        ("heavy_local", "explicit heavy local runtime test"),
        ("remote", "remote deployment/runtime test"),
    ):
        config.addinivalue_line("markers", f"{name}: {description}")
