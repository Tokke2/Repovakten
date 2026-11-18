"""Tester för repovakten.github med fejkad transport."""
from __future__ import annotations

import json

import pytest

from repovakten.errors import (
    AuthenticationError,
    GitHubApiError,
    NotFoundError,
    RateLimitError,
)
from repovakten.github import GitHubClient

from conftest import FakeTransport, api_asset, api_release, api_repo


def client(transport: FakeTransport) -> GitHubClient:
    return GitHubClient(transport, token="test-token", api_base="https://api.github.test")


def test_list_public_repos_paginerar(transport: FakeTransport):
    transport.add(
        "/users/tokke2/repos?type=owner&sort=created&direction=desc&per_page=2&page=1",
        [api_repo(1, "A"), api_repo(2, "B")],
    )
    transport.add(
        "/users/tokke2/repos?type=owner&sort=created&direction=desc&per_page=2&page=2",
        [api_repo(3, "C"), api_repo(4, "D")],
    )
    transport.add(
        "/users/tokke2/repos?type=owner&sort=created&direction=desc&per_page=2&page=3",
        [api_repo(5, "E")],
    )
    repos = client(transport).list_public_repos("tokke2", per_page=2)
    assert [r.name for r in repos] == ["A", "B", "C", "D", "E"]


def test_list_public_repos_filtrerar_privata(transport: FakeTransport):
    transport.add(
        "/users/tokke2/repos?type=owner&sort=created&direction=desc&per_page=100&page=1",
        [api_repo(1, "Publik"), api_repo(2, "Hemlig", private=True)],
    )
    repos = client(transport).list_public_repos("tokke2")
    assert [r.name for r in repos] == ["Publik"]


def test_ogiltigt_anvandarnamn_avvisas(transport: FakeTransport):
    with pytest.raises(ValueError):
        client(transport).list_public_repos("dåligt namn!")


def test_headern_innehaller_token_och_user_agent(transport: FakeTransport):
    transport.add(
        "/users/tokke2/repos?type=owner&sort=created&direction=desc&per_page=100&page=1", []
    )
    client(transport).list_public_repos("tokke2")
    headers = transport.calls[0]["headers"]
    assert headers["Authorization"] == "Bearer test-token"
    assert headers["User-Agent"].startswith("Repovakten/")
    assert headers["Accept"] == "application/vnd.github+json"


def test_token_las_fran_miljo(monkeypatch, transport: FakeTransport):
    monkeypatch.setenv("REPOVAKTEN_GITHUB_TOKEN", "miljo-token")
    c = GitHubClient(transport, api_base="https://api.github.test")
    transport.add(
        "/users/tokke2/repos?type=owner&sort=created&direction=desc&per_page=100&page=1", []
    )
    c.list_public_repos("tokke2")
    assert transport.calls[0]["headers"]["Authorization"] == "Bearer miljo-token"


def test_401_ger_authentication_error(transport: FakeTransport):
    transport.add(
        "/users/tokke2/repos?type=owner&sort=created&direction=desc&per_page=100&page=1",
        {"message": "Bad credentials"},
        status=401,
    )
    with pytest.raises(AuthenticationError):
        client(transport).list_public_repos("tokke2")


def test_404_ger_notfound(transport: FakeTransport):
    transport.add(
        "/users/ingen/repos?type=owner&sort=created&direction=desc&per_page=100&page=1",
        {"message": "Not Found"},
        status=404,
    )
    with pytest.raises(NotFoundError):
        client(transport).list_public_repos("ingen")


def test_403_med_tom_kvot_ger_rate_limit(transport: FakeTransport):
    transport.add(
        "/users/tokke2/repos?type=owner&sort=created&direction=desc&per_page=100&page=1",
        {"message": "API rate limit exceeded"},
        status=403,
        headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1893456000"},
    )
    with pytest.raises(RateLimitError) as excinfo:
        client(transport).list_public_repos("tokke2")
    assert excinfo.value.reset_at is not None


def test_500_ger_generiskt_api_fel(transport: FakeTransport):
    transport.add(
        "/users/tokke2/repos?type=owner&sort=created&direction=desc&per_page=100&page=1",
        "internt fel",
        status=500,
    )
    with pytest.raises(GitHubApiError):
        client(transport).list_public_repos("tokke2")


def test_ogiltig_json_ger_api_fel(transport: FakeTransport):
    transport.add(
        "/users/tokke2/repos?type=owner&sort=created&direction=desc&per_page=100&page=1",
        b"<html>fel</html>",
    )
    with pytest.raises(GitHubApiError):
        client(transport).list_public_repos("tokke2")


def test_list_releases_parsar_tillgangar(transport: FakeTransport):
    rels = [
        api_release(
            11,
            "v1.2.0",
            assets=[api_asset(101, "Appen-win64.zip", size=1234)],
        ),
        api_release(10, "v1.1.0", published="2026-09-01T00:00:00Z", assets=[]),
    ]
    transport.add("/repos/tokke2/Appen/releases?per_page=100&page=1", rels)
    releases = client(transport).list_releases("tokke2", "Appen", repo_id=42)
    assert [r.tag_name for r in releases] == ["v1.2.0", "v1.1.0"]
    assert releases[0].repo_id == 42
    assert releases[0].assets[0].name == "Appen-win64.zip"
    assert releases[0].assets[0].size == 1234


def test_list_releases_utan_tillgangar(transport: FakeTransport):
    transport.add("/repos/tokke2/Appen/releases?per_page=100&page=1", [])
    assert client(transport).list_releases("tokke2", "Appen") == []


def test_release_utan_tagg_hoppas_over(transport: FakeTransport):
    raw = api_release(11, "")
    raw["tag_name"] = ""
    transport.add("/repos/tokke2/Appen/releases?per_page=100&page=1", [raw])
    assert client(transport).list_releases("tokke2", "Appen") == []
