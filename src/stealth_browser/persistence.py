"""Persistent profile/session state helpers."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

PROFILE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_app_dir() -> Path:
    """Return the base app data directory for persisted session state."""
    env = os.getenv("STEALTH_BROWSER_HOME")
    if env:
        return Path(env).expanduser()

    xdg = os.getenv("XDG_DATA_HOME")
    if xdg:
        return Path(xdg).expanduser() / "stealth-browser-mcp"

    return Path.home() / ".local" / "share" / "stealth-browser-mcp"


def get_profiles_dir() -> Path:
    path = get_app_dir() / "profiles"
    path.mkdir(parents=True, exist_ok=True)
    return path


def validate_profile_name(profile_name: str) -> str:
    if not profile_name or not PROFILE_NAME_RE.fullmatch(profile_name):
        raise ValueError(
            "Invalid profile_name. Use 1-64 chars: letters, numbers, dot, underscore, dash"
        )
    return profile_name


def get_profile_dir(profile_name: str) -> Path:
    profile_name = validate_profile_name(profile_name)
    return get_profiles_dir() / profile_name


def get_storage_state_path(profile_name: str) -> Path:
    return get_profile_dir(profile_name) / "storage_state.json"


def get_profile_meta_path(profile_name: str) -> Path:
    return get_profile_dir(profile_name) / "meta.json"


def profile_exists(profile_name: str) -> bool:
    return get_storage_state_path(profile_name).exists()


def read_profile_meta(profile_name: str) -> dict:
    path = get_profile_meta_path(profile_name)
    if not path.exists():
        return {}

    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def write_profile_meta(profile_name: str, meta: dict) -> dict:
    profile_dir = get_profile_dir(profile_name)
    profile_dir.mkdir(parents=True, exist_ok=True)

    existing = read_profile_meta(profile_name)
    merged = {**existing, **meta}
    merged.setdefault("profile_name", profile_name)
    merged.setdefault("created_at", _now_iso())
    merged["updated_at"] = _now_iso()

    path = get_profile_meta_path(profile_name)
    path.write_text(json.dumps(merged, indent=2, sort_keys=True))
    return merged


def list_profiles() -> list[dict]:
    profiles_dir = get_profiles_dir()
    results: list[dict] = []

    for entry in sorted(profiles_dir.iterdir(), key=lambda p: p.name):
        if not entry.is_dir():
            continue
        storage_path = entry / "storage_state.json"
        meta = read_profile_meta(entry.name)
        results.append(
            {
                "profile_name": entry.name,
                "storage_state_path": str(storage_path),
                "exists": storage_path.exists(),
                "meta": meta,
            }
        )

    return results


def delete_profile(profile_name: str) -> bool:
    profile_dir = get_profile_dir(profile_name)
    if not profile_dir.exists():
        return False

    for child in profile_dir.iterdir():
        child.unlink()
    profile_dir.rmdir()
    return True
