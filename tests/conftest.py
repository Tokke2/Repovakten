"""Delade testfixtures och hjälpfunktioner."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from repovakten.github import HttpResponse
from repovakten.store import Store


# ---------------------------------------------------------------- API-JSON

def api_repo(
    repo_id: int,
    name: str,
    owner: str = "tokke2",
    *,
    private: bool = False,
    language: str | None = "Python",
    full_name: str | None = None,
) -> dict:
    return {
        "id": repo_id,
        "name": name,
        "full_name": full_name or f"{owner}/{name}",
        "owner": {"login": owner},
        "private": private,
        "html_url": f"https://github.com/{owner}/{name}",
        "language": language,
        "description": f"Beskrivning av {name}",
        "fork": False,
        "archived": False,
        "default_branch": "main",
        "pushed_at": "2026-11-01T10:00:00Z",
        "updated_at": "2026-11-01T10:00:00Z",
    }


def api_asset(asset_id: int, name: str, size: int = 2048) -> dict:
    return {
        "id": asset_id,
        "name": name,
        "size": size,
        "browser_download_url": f"https://github.com/tokke2/app/releases/download/v-release/{name}",
        "content_type": "application/zip",
    }


def api_release(
    release_id: int,
    tag: str,
    *,
    draft: bool = False,
    prerelease: bool = False,
    published: str = "2026-11-01T10:00:00Z",
    assets: list[dict] | None = None,
) -> dict:
    return {
        "id": release_id,
        "tag_name": tag,
        "name": tag,
        "draft": draft,
        "prerelease": prerelease,
        "published_at": published,
        "created_at": published,
        "html_url": f"https://github.com/tokke2/app/releases/tag/{tag}",
        "assets": assets or [],
    }


# ----------------------------------------------------------- fejktransport

class FakeTransport:
    """Transport som svarar med fördefinierade svar per (sökväg + query)."""

    def __init__(self) -> None:
        self.routes: dict[str, HttpResponse] = {}
        self.calls: list[dict] = []

    def add(self, path_with_query: str, payload, *, status: int = 200, headers: dict | None = None):
        if isinstance(payload, bytes):
            body = payload
        elif isinstance(payload, str):
            body = payload.encode("utf-8")
        else:
            body = json.dumps(payload).encode("utf-8")
        self.routes[path_with_query] = HttpResponse(status, headers or {}, body)

    def request(self, method, url, headers):
        from urllib.parse import urlparse

        self.calls.append({"method": method, "url": url, "headers": dict(headers)})
        parsed = urlparse(url)
        key = parsed.path + (("?" + parsed.query) if parsed.query else "")
        if key in self.routes:
            return self.routes[key]
        return HttpResponse(404, {}, json.dumps({"message": f"ingen fejk-rutt för {key}"}).encode())


@pytest.fixture
def transport() -> FakeTransport:
    return FakeTransport()


@pytest.fixture
def store(tmp_path) -> Store:
    return Store(tmp_path / "state.json")


# ------------------------------------------------------------------- zip

def make_zip(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return path


def make_tree(root: Path, files: dict[str, bytes]) -> Path:
    for rel, data in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return root
