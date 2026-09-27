import json
import os
import re
import subprocess
import tomllib
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


DEFAULT_MODAL_ENVIRONMENT = "(default)"
TARGET_CONFIG_RELATIVE_PATH = Path("config") / "v2" / "modal_target.toml"
REGISTRY_RELATIVE_PATH = Path("comfymodal") / "modal_workspaces.json"
_ENVIRONMENT_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$")


@dataclass(frozen=True)
class ModalTargetConfig:
    schema_version: int
    workspace_id: str
    workspace_label: str
    environment: str = DEFAULT_MODAL_ENVIRONMENT

    @property
    def public(self) -> dict[str, str]:
        return {
            "workspace_id": self.workspace_id,
            "workspace_label": self.workspace_label,
            "environment": self.environment,
            "source": str(TARGET_CONFIG_RELATIVE_PATH).replace("\\", "/"),
        }


def _git_common_dir(repo_root: Path) -> Path:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=str(repo_root), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"cannot resolve git common directory for {repo_root}") from exc
    value = result.stdout.strip()
    if result.returncode != 0 or not value:
        raise RuntimeError(
            f"git rev-parse --git-common-dir failed for {repo_root}: "
            f"{result.stderr.strip()}"
        )
    common = Path(value)
    return (Path(repo_root) / common).resolve() if not common.is_absolute() else common.resolve()


def _atomic_copy_once(source: Path, target: Path) -> None:
    """Copy a legacy registry without deleting it and without overwriting a race."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(source.read_bytes())
        try:
            # A same-directory hard-link is an atomic create-without-replace
            # on the supported local filesystems.  Never overwrite a shared
            # registry that another worktree/process created first.
            os.link(temporary, target)
        except FileExistsError:
            return
    finally:
        temporary.unlink(missing_ok=True)


def resolve_workspace_registry_path(repo_root: str | Path) -> Path:
    """Return the worktree-shared registry path and perform safe legacy migration."""
    root = Path(repo_root).resolve()
    common_dir = _git_common_dir(root)
    shared = common_dir / REGISTRY_RELATIVE_PATH
    legacy = root / ".modal_workspaces.json"
    if not shared.exists() and legacy.exists():
        # Validate before publication so malformed legacy state is never copied
        # into the shared authority or silently replaced by defaults.
        load_workspace_registry(legacy)
        _atomic_copy_once(legacy, shared)
    if shared.exists():
        load_workspace_registry(shared)
    return shared


def _default_registry() -> dict:
    return {
        "version": 1,
        "active_workspace_id": None,
        "workspaces": [],
        "deploy_state_by_workspace": {},
    }


def load_workspace_registry(path: str | Path) -> dict:
    target = Path(path)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _default_registry()
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"workspace registry is unreadable or malformed: {target}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"workspace registry must be an object: {target}")
    _validate_registry(payload, target)
    return dict(payload)


def _validate_registry(payload: Mapping[str, Any], path: Path | None = None) -> None:
    location = f": {path}" if path is not None else ""
    if payload.get("version") != 1:
        raise ValueError(f"workspace registry has unsupported version{location}")
    active = payload.get("active_workspace_id")
    if active is not None and (not isinstance(active, str) or not active.strip()):
        raise ValueError(f"workspace registry active_workspace_id is malformed{location}")
    workspaces = payload.get("workspaces")
    if not isinstance(workspaces, list):
        raise ValueError(f"workspace registry workspaces is malformed{location}")
    ids: set[str] = set()
    for item in workspaces:
        if not isinstance(item, Mapping):
            raise ValueError(f"workspace registry entry is malformed{location}")
        workspace_id = item.get("id")
        label = item.get("label")
        if not isinstance(workspace_id, str) or not workspace_id.strip():
            raise ValueError(f"workspace registry entry id is missing{location}")
        if workspace_id in ids:
            raise ValueError(f"workspace registry contains duplicate workspace id{location}")
        ids.add(workspace_id)
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"workspace registry entry label is missing{location}")
        for name in ("token_id", "token_secret"):
            if not isinstance(item.get(name), str) or not str(item[name]).strip():
                raise ValueError(f"workspace registry entry {workspace_id!r} lacks {name}{location}")
        raw_environment = item.get("environment")
        if raw_environment is not None and not isinstance(raw_environment, str):
            raise ValueError(f"workspace registry entry environment is malformed{location}")
        environment = str(raw_environment or DEFAULT_MODAL_ENVIRONMENT).strip()
        _validate_environment(environment)
    if active is not None and active not in ids:
        raise ValueError(f"workspace registry active workspace is not registered{location}")
    deploy_state = payload.get("deploy_state_by_workspace")
    if not isinstance(deploy_state, dict):
        raise ValueError(f"workspace registry deploy_state_by_workspace is malformed{location}")


def _validate_environment(value: str) -> str:
    if value == DEFAULT_MODAL_ENVIRONMENT:
        return value
    if not _ENVIRONMENT_TOKEN.fullmatch(value):
        raise ValueError(f"unsafe Modal environment token: {value!r}")
    return value


def load_workspace_registry_for_repo(repo_root: str | Path) -> dict:
    """Load the shared registry, migrating a valid root-local legacy copy once."""
    return load_workspace_registry(resolve_workspace_registry_path(repo_root))


def load_modal_target_config(repo_root: str | Path) -> ModalTargetConfig:
    path = Path(repo_root) / TARGET_CONFIG_RELATIVE_PATH
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"Modal target config is missing or malformed: {path}") from exc
    if not isinstance(raw, dict) or set(raw) != {"schema_version", "modal"}:
        raise ValueError(
            "Modal target config must contain exactly schema_version and [modal]"
        )
    if raw["schema_version"] != 1:
        raise ValueError("Modal target config has unsupported schema_version")
    modal = raw["modal"]
    if not isinstance(modal, dict) or set(modal) != {
        "workspace_id", "workspace_label", "environment"
    }:
        raise ValueError(
            "Modal target config [modal] must contain exactly workspace_id, "
            "workspace_label, environment"
        )
    workspace_id = modal["workspace_id"]
    label = modal["workspace_label"]
    environment = modal["environment"]
    if not isinstance(workspace_id, str) or not workspace_id.strip():
        raise ValueError("Modal target config workspace_id is required")
    if not isinstance(label, str) or not label.strip():
        raise ValueError("Modal target config workspace_label is required")
    if not isinstance(environment, str):
        raise ValueError("Modal target config environment must be a string")
    _validate_environment(environment.strip())
    return ModalTargetConfig(1, workspace_id.strip(), label.strip(), environment.strip())


def resolve_modal_destination(repo_root: str | Path) -> dict[str, Any]:
    """Resolve config-owned destination and credentials from the shared registry."""
    root = Path(repo_root).resolve()
    target = load_modal_target_config(root)
    registry_path = resolve_workspace_registry_path(root)
    registry = load_workspace_registry(registry_path)
    workspace = get_workspace(registry, target.workspace_id)
    if workspace is None:
        raise ValueError(f"configured Modal workspace {target.workspace_id!r} is not registered")
    if str(workspace.get("label", "")) != target.workspace_label:
        raise ValueError(
            f"configured Modal workspace label {target.workspace_label!r} does not match "
            f"registry label {workspace.get('label')!r}"
        )
    token_id = str(workspace.get("token_id") or "").strip()
    token_secret = str(workspace.get("token_secret") or "").strip()
    if not token_id or not token_secret:
        raise ValueError(f"configured Modal workspace {target.workspace_id!r} has no credentials")
    return {
        "workspace_id": target.workspace_id,
        "workspace_label": target.workspace_label,
        "environment": target.environment,
        "token_id": token_id,
        "token_secret": token_secret,
        "source": str(TARGET_CONFIG_RELATIVE_PATH).replace("\\", "/"),
        "registry": str(registry_path),
    }


# Descriptive aliases used by control-plane integrations.
parse_modal_target_config = load_modal_target_config
resolve_workspace_destination = resolve_modal_destination


def save_workspace_registry(path: str | Path, payload: dict) -> dict:
    target = Path(path)
    if not isinstance(payload, Mapping):
        raise ValueError("workspace registry must be an object")
    _validate_registry(payload, target)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(target)
    return payload


def _validate_workspace(label: str, token_id: str, token_secret: str) -> tuple[str, str, str]:
    safe_label = (label or "").strip()
    safe_token_id = (token_id or "").strip()
    safe_token_secret = (token_secret or "").strip()
    if not safe_label:
        raise ValueError("label required")
    if not safe_token_id.startswith("ak-"):
        raise ValueError("token_id must start with ak-")
    if not safe_token_secret.startswith("as-"):
        raise ValueError("token_secret must start with as-")
    return safe_label, safe_token_id, safe_token_secret


def _mask_token(token: str) -> str:
    if not token:
        return ""
    if len(token) <= 10:
        return token[:4] + "\u2026"
    return f"{token[:7]}\u2026{token[-4:]}"


def workspace_summary(workspace: dict) -> dict:
    return {
        "id": workspace["id"],
        "label": workspace["label"],
        "token_id_masked": _mask_token(workspace.get("token_id", "")),
        "token_secret_masked": _mask_token(workspace.get("token_secret", "")),
        "last_used_at": workspace.get("last_used_at"),
        "last_deploy_status": workspace.get("last_deploy_status", "idle"),
        "notes": workspace.get("notes", ""),
    }


def upsert_workspace(path: str | Path, label: str, token_id: str, token_secret: str, *,
                     workspace_id: str | None = None, notes: str = "", set_active: bool = False) -> dict:
    registry = load_workspace_registry(path)
    existing_workspace = None
    for existing in registry["workspaces"]:
        if workspace_id and existing["id"] == workspace_id:
            existing_workspace = existing
            break
    if existing_workspace is not None:
        token_id = (token_id or "").strip() or existing_workspace.get("token_id", "")
        token_secret = (token_secret or "").strip() or existing_workspace.get("token_secret", "")
    safe_label, safe_token_id, safe_token_secret = _validate_workspace(label, token_id, token_secret)
    workspaces = []
    matched_id = None
    for existing in registry["workspaces"]:
        if workspace_id and existing["id"] == workspace_id:
            matched_id = existing["id"]
            workspaces.append({
                **existing,
                "label": safe_label,
                "token_id": safe_token_id,
                "token_secret": safe_token_secret,
                "notes": notes,
            })
        else:
            workspaces.append(existing)
    if matched_id is None:
        matched_id = f"ws_{uuid.uuid4().hex[:12]}"
        workspaces.append({
            "id": matched_id,
            "label": safe_label,
            "token_id": safe_token_id,
            "token_secret": safe_token_secret,
            "last_used_at": None,
            "last_deploy_status": "idle",
            "notes": notes,
        })
    registry["workspaces"] = workspaces
    if set_active or registry["active_workspace_id"] is None:
        registry["active_workspace_id"] = matched_id
        for workspace in registry["workspaces"]:
            if workspace["id"] == matched_id:
                workspace["last_used_at"] = time.time()
    return save_workspace_registry(path, registry)


def set_active_workspace(path: str | Path, workspace_id: str) -> dict:
    registry = load_workspace_registry(path)
    for workspace in registry["workspaces"]:
        if workspace["id"] == workspace_id:
            workspace["last_used_at"] = time.time()
            registry["active_workspace_id"] = workspace_id
            return save_workspace_registry(path, registry)
    raise KeyError(f"unknown workspace: {workspace_id}")


def get_active_workspace(registry: dict) -> dict | None:
    active_id = registry.get("active_workspace_id")
    if active_id is not None:
        for workspace in registry.get("workspaces", []):
            if workspace.get("id") == active_id:
                return workspace
    workspaces = registry.get("workspaces", [])
    if len(workspaces) == 1:
        return workspaces[0]
    return None


def _parse_legacy_toml(path: str | Path) -> dict:
    """Parse a simple TOML file and extract token_id/token_secret from [default]."""
    try:
        content = Path(path).read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return {}
    token_id = None
    token_secret = None
    for m in re.finditer(r'^token_id\s*=\s*"([^"]*)"\s*$', content, re.MULTILINE):
        token_id = m.group(1)
    for m in re.finditer(r'^token_secret\s*=\s*"([^"]*)"\s*$', content, re.MULTILINE):
        token_secret = m.group(1)
    if not token_id or not token_secret:
        return {}
    return {"token_id": token_id, "token_secret": token_secret}


def migrate_from_legacy_toml(registry_path: str | Path, toml_path: str | Path) -> dict:
    """Migrate credentials from ~/.modal.toml into the workspace registry.

    Only migrates when the registry has zero workspaces and the toml file
    contains a valid token_id / token_secret pair. Returns the registry dict.
    """
    registry = load_workspace_registry(registry_path)
    if registry.get("workspaces"):
        return registry
    legacy = _parse_legacy_toml(toml_path)
    if not legacy:
        return registry
    try:
        return upsert_workspace(
            registry_path,
            label="Legacy Modal Token",
            token_id=legacy["token_id"],
            token_secret=legacy["token_secret"],
            set_active=True,
        )
    except ValueError:
        return registry


def get_workspace(registry: dict, workspace_id: str) -> dict | None:
    for workspace in registry.get("workspaces", []):
        if workspace.get("id") == workspace_id:
            return workspace
    return None
