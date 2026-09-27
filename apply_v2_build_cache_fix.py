from __future__ import annotations

import argparse
import ast
import codecs
import os
import re
from pathlib import Path

FIX_TEST = r'''from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dependency_build_context_is_metadata_stable():
    source = (ROOT / "comfyapp.py").read_text(encoding="utf-8-sig")
    assert "def _normalize_requirements_context_metadata" in source
    assert "_REQUIREMENTS_CONTEXT_MTIME = 946684800" in source
    assert "shutil.copyfile(src, dst)" in source
    assert "_normalize_requirements_context_metadata(target_root)" in source


def test_cachedit_lock_is_ensured_not_force_reinstalled():
    source = (ROOT / "comfyapp.py").read_text(encoding="utf-8-sig")
    assert 'pip install --force-reinstall --no-deps -r "$_lock"' not in source
    assert "CACHEDIT_LOCK_FAMILY_REINSTALL_START" not in source
    assert "CACHEDIT_LOCK_FAMILY_ENSURE_START" in source
    assert "--disable-pip-version-check --no-input --no-deps" in source


def test_build_gate_never_touches_runtime_state_mount():
    source = (ROOT / "comfyapp.py").read_text(encoding="utf-8-sig")
    assert 'shutil.rmtree("/root/comfymodal_runtime_state"' not in source


def test_v2_runtime_state_uses_clean_mount_namespace():
    source = (ROOT / "comfymodal_runtime" / "modal_app.py").read_text(encoding="utf-8-sig")
    assert 'RUNTIME_STATE_PATH = "/mnt/comfymodal_runtime_state"' in source
    assert 'RUNTIME_STATE_PATH = "/root/comfymodal_runtime_state"' not in source


def test_changed_python_files_parse():
    for relative in ("comfyapp.py", "comfymodal_runtime/modal_app.py"):
        source = (ROOT / relative).read_text(encoding="utf-8-sig")
        ast.parse(source, filename=relative)
'''

HELPER = '''_REQUIREMENTS_CONTEXT_MTIME = 946684800  # 2000-01-01 UTC


def _normalize_requirements_context_metadata(root: str) -> None:
    """Make staged dependency context metadata deterministic for Modal caching.

    Fresh checkouts and regenerated staging trees can carry different mtimes
    and modes even when every dependency file is byte-for-byte unchanged.
    Normalize files and directories so metadata-only changes cannot invalidate
    the custom-node dependency image layer.
    """
    if not os.path.isdir(root):
        return
    for dirpath, dirnames, filenames in os.walk(root):
        for dirname in dirnames:
            directory = os.path.join(dirpath, dirname)
            if os.path.islink(directory):
                continue
            os.chmod(directory, 0o755)
            os.utime(directory, (_REQUIREMENTS_CONTEXT_MTIME, _REQUIREMENTS_CONTEXT_MTIME))
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            if os.path.islink(file_path):
                continue
            os.chmod(file_path, 0o644)
            os.utime(file_path, (_REQUIREMENTS_CONTEXT_MTIME, _REQUIREMENTS_CONTEXT_MTIME))
    os.chmod(root, 0o755)
    os.utime(root, (_REQUIREMENTS_CONTEXT_MTIME, _REQUIREMENTS_CONTEXT_MTIME))


'''


def read_text(path: Path) -> tuple[str, bool]:
    raw = path.read_bytes()
    return raw.decode("utf-8-sig"), raw.startswith(codecs.BOM_UTF8)


def write_text(path: Path, text: str, had_bom: bool) -> None:
    raw = text.encode("utf-8")
    if had_bom:
        raw = codecs.BOM_UTF8 + raw
    path.write_bytes(raw)


def replace_once(text: str, old: str, new: str, label: str) -> tuple[str, bool]:
    count = text.count(old)
    if count == 0:
        return text, False
    if count != 1:
        raise RuntimeError(f"Expected one {label}, found {count}")
    return text.replace(old, new, 1), True


def patch_comfyapp(path: Path) -> list[str]:
    text, bom = read_text(path)
    original = text
    nl = "\r\n" if "\r\n" in text else "\n"
    changes: list[str] = []

    if "def _normalize_requirements_context_metadata(" not in text:
        marker = "def _build_requirements_context_manifest(root: str) -> dict[str, str]:"
        if marker not in text:
            raise RuntimeError("Could not locate requirements-context manifest helper")
        text = text.replace(marker, HELPER.replace("\n", nl) + marker, 1)
        changes.append("added deterministic dependency-context metadata normalization")

    old = "            shutil.copy2(src, dst)" + nl
    new = (
        "            shutil.copyfile(src, dst)" + nl
        + "            os.chmod(dst, 0o644)" + nl
        + "            os.utime(dst, (_REQUIREMENTS_CONTEXT_MTIME, _REQUIREMENTS_CONTEXT_MTIME))" + nl
    )
    text, changed = replace_once(text, old, new, "requirements file copy")
    if changed:
        changes.append("stopped preserving source mtimes in staged requirement files")

    old = "        shutil.copytree(staged_dir, dst_node_dir)" + nl
    new = old + "        _normalize_requirements_context_metadata(dst_node_dir)" + nl
    text, changed = replace_once(text, old, new, "requirements tree copy")
    if changed:
        changes.append("normalized copied dependency-tree metadata")

    fn_start = text.find("def _prepare_custom_node_requirements_build_context(")
    if fn_start < 0:
        raise RuntimeError("Could not locate requirements build-context function")
    next_block = text.find(nl + nl + "if not _INSIDE_MODAL_CONTAINER:", fn_start)
    if next_block < 0:
        raise RuntimeError("Could not locate end of requirements build-context function")
    fn_body = text[fn_start:next_block]
    root_normalize = nl + "    _normalize_requirements_context_metadata(target_root)" + nl
    if "_normalize_requirements_context_metadata(target_root)" not in fn_body:
        text = text[:next_block] + root_normalize + text[next_block:]
        changes.append("normalized staging-root metadata before Modal hashes it")

    old_cmd = 'pip install -r requirements.txt -c "$_lock" --quiet;'
    new_cmd = 'python -m pip install --disable-pip-version-check --no-input -r requirements.txt -c "$_lock" --quiet;'
    if old_cmd in text:
        text = text.replace(old_cmd, new_cmd, 1)
        changes.append("disabled repeated pip version checks for node installs")

    old_force = 'pip install --force-reinstall --no-deps -r "$_lock" --quiet;'
    new_ensure = 'python -m pip install --disable-pip-version-check --no-input --no-deps -r "$_lock" --quiet;'
    if old_force in text:
        text = text.replace(old_force, new_ensure, 1)
        changes.append("removed redundant CacheDiT family force reinstall")

    if "CACHEDIT_LOCK_FAMILY_REINSTALL_START" in text:
        text = text.replace("CACHEDIT_LOCK_FAMILY_REINSTALL_START", "CACHEDIT_LOCK_FAMILY_ENSURE_START")
        text = text.replace("CACHEDIT_LOCK_FAMILY_REINSTALL_END", "CACHEDIT_LOCK_FAMILY_ENSURE_END")

    heavy_import = "import transformers, diffusers, cache_dit" + nl
    if heavy_import in text:
        text = text.replace(heavy_import, "import importlib.util" + nl, 1)
        changes.append("made dependency gate avoid importing diffusers and CacheDiT")

    old_module_check = (
        "        mod = __import__(imp)" + nl
        + "        _mp = getattr(mod, \"__file__\", \"?\")" + nl
    )
    new_module_check = (
        "        spec = importlib.util.find_spec(imp)" + nl
        + "        if spec is None:" + nl
        + "            raise ModuleNotFoundError(imp)" + nl
        + "        _mp = spec.origin or \"?\"" + nl
    )
    if old_module_check in text:
        text = text.replace(old_module_check, new_module_check, 1)

    # The cleanup command has appeared in several source representations:
    # directly inside a heredoc, indented inside a triple-quoted command, and
    # inside a concatenated Python string fragment.  Replace the call itself
    # rather than requiring one exact surrounding three-line block.  ``None``
    # remains valid in every representation and cannot mutate the mount path.
    cleanup_pattern = re.compile(
        r"shutil\.rmtree\(\s*\\?[\"']/root/comfymodal_runtime_state\\?[\"']"
        r"\s*,\s*ignore_errors\s*=\s*True\s*\)"
    )
    text, cleanup_count = cleanup_pattern.subn("None", text)
    if cleanup_count:
        changes.append(
            f"removed {cleanup_count} image-build mutation(s) of the V2 volume mount target"
        )

    forbidden = [
        'pip install --force-reinstall --no-deps -r "$_lock"',
    ]
    for item in forbidden:
        if item in text:
            raise RuntimeError(f"Patch incomplete; still found: {item}")
    if cleanup_pattern.search(text):
        raise RuntimeError(
            "Patch incomplete; a runtime-state cleanup call remains. "
            'Run: findstr /n /c:"comfymodal_runtime_state" comfyapp.py'
        )

    ast.parse(text, filename=str(path))
    if text != original:
        write_text(path, text, bom)
    return changes


def patch_modal_app(path: Path) -> list[str]:
    text, bom = read_text(path)
    original = text
    changes: list[str] = []
    old = 'RUNTIME_STATE_PATH = "/root/comfymodal_runtime_state"'
    new = 'RUNTIME_STATE_PATH = "/mnt/comfymodal_runtime_state"'
    if old in text:
        text = text.replace(old, new, 1)
        changes.append("moved V2 runtime-state volume to a clean /mnt mount target")
    elif new not in text:
        raise RuntimeError("Could not locate V2 runtime-state path")
    ast.parse(text, filename=str(path))
    if text != original:
        write_text(path, text, bom)
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply the V2 Modal deploy build-cache fix")
    parser.add_argument("repo", nargs="?", default=".", help="Path to comfyui-modal checkout")
    args = parser.parse_args()
    root = Path(args.repo).resolve()
    comfyapp = root / "comfyapp.py"
    modal_app = root / "comfymodal_runtime" / "modal_app.py"
    if not comfyapp.is_file() or not modal_app.is_file():
        parser.error(f"Not a comfyui-modal checkout: {root}")

    changes = patch_comfyapp(comfyapp) + patch_modal_app(modal_app)
    test_path = root / "tests" / "test_v2_deploy_build_cache.py"
    test_path.write_text(FIX_TEST, encoding="utf-8")
    changes.append("added focused regression tests")

    print("Applied V2 deploy build-cache fix:")
    for change in changes:
        print(f"- {change}")
    print("\nRun:")
    print("  python -m pytest tests/test_v2_deploy_build_cache.py tests/test_comfyapp_build_context.py tests/test_comfyapp_packaging.py -q")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())