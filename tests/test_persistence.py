"""Tests for persistent profile helpers."""

from __future__ import annotations

import json

import pytest

from stealth_browser.persistence import (
    delete_profile,
    get_storage_state_path,
    list_profiles,
    profile_exists,
    read_profile_meta,
    validate_profile_name,
    write_profile_meta,
)


def test_validate_profile_name_accepts_safe_values():
    assert validate_profile_name("x-main") == "x-main"
    assert validate_profile_name("x.main_01") == "x.main_01"


@pytest.mark.parametrize("name", ["", "../bad", "bad/slash", " space", "*"])
def test_validate_profile_name_rejects_unsafe_values(name):
    with pytest.raises(ValueError):
        validate_profile_name(name)


def test_write_and_read_profile_meta(monkeypatch, tmp_path):
    monkeypatch.setenv("STEALTH_BROWSER_HOME", str(tmp_path))

    meta = write_profile_meta("x-main", {"engine": "chromium", "last_url": "https://x.com"})
    assert meta["profile_name"] == "x-main"
    assert meta["engine"] == "chromium"
    assert "created_at" in meta
    assert "updated_at" in meta

    read_back = read_profile_meta("x-main")
    assert read_back["last_url"] == "https://x.com"


def test_list_profiles_reports_existing_storage_state(monkeypatch, tmp_path):
    monkeypatch.setenv("STEALTH_BROWSER_HOME", str(tmp_path))

    path = get_storage_state_path("x-main")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"cookies": [], "origins": []}))
    write_profile_meta("x-main", {"engine": "firefox"})

    profiles = list_profiles()
    assert len(profiles) == 1
    assert profiles[0]["profile_name"] == "x-main"
    assert profiles[0]["exists"] is True
    assert profiles[0]["meta"]["engine"] == "firefox"
    assert profile_exists("x-main") is True


def test_delete_profile_removes_profile_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("STEALTH_BROWSER_HOME", str(tmp_path))

    path = get_storage_state_path("x-main")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}")
    write_profile_meta("x-main", {"engine": "chromium"})

    assert delete_profile("x-main") is True
    assert profile_exists("x-main") is False
    assert delete_profile("x-main") is False
