import os


_EXCLUDED_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv"}


def _safe_listdir(path: str) -> list[str]:
    if not os.path.isdir(path):
        return []
    return sorted(os.listdir(path))


def _is_volume_managed_link(link_path: str, volume_root: str) -> bool:
    if not os.path.islink(link_path):
        return False
    target = os.path.realpath(link_path)
    try:
        common = os.path.commonpath([os.path.abspath(volume_root), os.path.abspath(target)])
    except ValueError:
        return False
    return common == os.path.abspath(volume_root)


def custom_node_volume_state(volume_root: str) -> tuple:
    volume_root = os.path.abspath(volume_root)
    state = []
    for name in _safe_listdir(volume_root):
        path = os.path.join(volume_root, name)
        if not os.path.isdir(path) or name in _EXCLUDED_DIRS:
            continue
        stat = os.stat(path)
        req_file = os.path.join(path, "requirements.txt")
        req_mtime_ns = os.stat(req_file).st_mtime_ns if os.path.isfile(req_file) else None
        state.append((name, stat.st_mtime_ns, req_mtime_ns))
    return tuple(state)


def missing_expected_nodes(state: tuple, expected_nodes: list[str]) -> list[str]:
    visible = {name for name, *_ in state}
    return [name for name in expected_nodes if name not in visible]


def sync_custom_nodes_into_comfy(volume_root: str, comfy_custom_nodes_root: str) -> dict:
    volume_root = os.path.abspath(volume_root)
    comfy_custom_nodes_root = os.path.abspath(comfy_custom_nodes_root)
    os.makedirs(comfy_custom_nodes_root, exist_ok=True)

    volume_dirs = {
        name
        for name in _safe_listdir(volume_root)
        if os.path.isdir(os.path.join(volume_root, name))
        and name not in _EXCLUDED_DIRS
    }

    removed = []
    created = []
    kept = []
    blocked = []

    for name in _safe_listdir(comfy_custom_nodes_root):
        dst = os.path.join(comfy_custom_nodes_root, name)
        if not _is_volume_managed_link(dst, volume_root):
            continue
        expected_src = os.path.join(volume_root, name)
        if name not in volume_dirs or os.path.realpath(dst) != os.path.realpath(expected_src):
            os.unlink(dst)
            removed.append(name)

    for name in sorted(volume_dirs):
        src = os.path.join(volume_root, name)
        dst = os.path.join(comfy_custom_nodes_root, name)
        if os.path.islink(dst) and os.path.realpath(dst) == os.path.realpath(src):
            kept.append(name)
            continue
        if os.path.lexists(dst):
            blocked.append(name)
            continue
        os.symlink(src, dst)
        created.append(name)

    return {
        "created": created,
        "removed": removed,
        "kept": kept,
        "blocked": blocked,
    }
