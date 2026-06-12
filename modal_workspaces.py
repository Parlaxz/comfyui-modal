import json
import time
import uuid
from pathlib import Path


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
    except json.JSONDecodeError:
        return _default_registry()
    if not isinstance(payload, dict):
        return _default_registry()
    merged = _default_registry()
    merged.update({k: payload.get(k, merged[k]) for k in merged})
    if not isinstance(merged["workspaces"], list):
        merged["workspaces"] = []
    if not isinstance(merged["deploy_state_by_workspace"], dict):
        merged["deploy_state_by_workspace"] = {}
    return merged


def save_workspace_registry(path: str | Path, payload: dict) -> dict:
    target = Path(path)
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
    safe_label, safe_token_id, safe_token_secret = _validate_workspace(label, token_id, token_secret)
    registry = load_workspace_registry(path)
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
    for workspace in registry.get("workspaces", []):
        if workspace.get("id") == active_id:
            return workspace
    return None


def get_workspace(registry: dict, workspace_id: str) -> dict | None:
    for workspace in registry.get("workspaces", []):
        if workspace.get("id") == workspace_id:
            return workspace
    return None
