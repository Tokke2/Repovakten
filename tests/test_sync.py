"""Tester för repovakten.sync – bevakning och synk."""
from __future__ import annotations

from repovakten.blocking import assert_install_allowed, block_app, is_blocked
from repovakten.github import GitHubClient
from repovakten.models import InstallRecord
from repovakten.store import Store
from repovakten.sync import SYNC_INTERVAL_SECONDS, sync_accounts

import pytest

from conftest import FakeTransport, api_asset, api_release, api_repo


def repos_path(user: str, page: int = 1) -> str:
    return f"/users/{user}/repos?type=owner&sort=created&direction=desc&per_page=100&page={page}"


def releases_path(owner: str, repo: str, page: int = 1) -> str:
    return f"/repos/{owner}/{repo}/releases?per_page=100&page={page}"


def make_client(transport: FakeTransport) -> GitHubClient:
    return GitHubClient(transport, token=None, api_base="https://api.github.test")


def prime_repo(transport: FakeTransport, owner: str, repo: str, repo_id: int, *, assets=None):
    transport.add(releases_path(owner, repo), [
        api_release(100 + repo_id, "v1.0.0", assets=assets or [api_asset(repo_id + 1000, f"{repo}-win64.zip")]),
    ])


def test_sync_intervall_ar_15_minuter():
    assert SYNC_INTERVAL_SECONDS == 900


def test_forsta_synken_fyller_katalogen(store: Store, transport: FakeTransport):
    transport.add(repos_path("tokke2"), [api_repo(1, "Appen")])
    prime_repo(transport, "tokke2", "Appen", 1)
    store.add_account("tokke2")

    report = sync_accounts(store, make_client(transport))

    assert report.synced_accounts == ["tokke2"]
    assert report.added == ["tokke2/Appen"]
    entries = store.repo_entries()
    assert [e.repo.name for e in entries] == ["Appen"]
    assert entries[0].releases[0].tag_name == "v1.0.0"
    assert store.get_last_sync() is not None


def test_nytt_publikt_repo_dyker_upp_vid_nasta_synk(store: Store, transport: FakeTransport):
    transport.add(repos_path("tokke2"), [api_repo(1, "Appen")])
    prime_repo(transport, "tokke2", "Appen", 1)
    store.add_account("tokke2")
    sync_accounts(store, make_client(transport))

    # Användaren skapar "NyaAppen" på GitHub – den ska synas vid nästa synk.
    transport.add(repos_path("tokke2"), [api_repo(1, "Appen"), api_repo(2, "NyaAppen")])
    prime_repo(transport, "tokke2", "NyaAppen", 2)

    report = sync_accounts(store, make_client(transport))

    assert report.added == ["tokke2/NyaAppen"]
    assert {e.repo.name for e in store.repo_entries()} == {"Appen", "NyaAppen"}


def test_repo_utan_release_syns_i_katalogen(store: Store, transport: FakeTransport):
    transport.add(repos_path("tokke2"), [api_repo(1, "UtanRelease")])
    transport.add(releases_path("tokke2", "UtanRelease"), [])
    store.add_account("tokke2")

    sync_accounts(store, make_client(transport))

    entries = store.repo_entries()
    assert [e.repo.name for e in entries] == ["UtanRelease"]
    assert entries[0].releases == []


def test_namnbyte_pa_github_behaller_sparr(store: Store, transport: FakeTransport):
    transport.add(repos_path("tokke2"), [api_repo(42, "GammaltNamn")])
    prime_repo(transport, "tokke2", "GammaltNamn", 42)
    store.add_account("tokke2")
    sync_accounts(store, make_client(transport))
    block_app(store, 42, reason="Väntar på signering")

    # Samma repo-ID, annat namn – som efter ett namnbyte på GitHub.
    transport.add(repos_path("tokke2"), [api_repo(42, "NyttNamn", full_name="tokke2/NyttNamn")])
    prime_repo(transport, "tokke2", "NyttNamn", 42)
    sync_accounts(store, make_client(transport))

    assert is_blocked(store, 42)
    assert store.get_entry(42).repo.name == "NyttNamn"
    with pytest.raises(Exception):
        assert_install_allowed(store, 42)


def test_forsvunnet_repo_markeras_men_raderas_aldrig(store: Store, transport: FakeTransport):
    transport.add(repos_path("tokke2"), [api_repo(1, "Appen"), api_repo(2, "Borta")])
    prime_repo(transport, "tokke2", "Appen", 1)
    prime_repo(transport, "tokke2", "Borta", 2)
    store.add_account("tokke2")
    sync_accounts(store, make_client(transport))
    store.set_install(
        InstallRecord(
            repo_id=2,
            repo_full_name="tokke2/Borta",
            installed_tag="v1.0.0",
            install_dir="/tmp/Borta",
            installed_at="2026-11-01T00:00:00Z",
            updated_at="2026-11-01T00:00:00Z",
        )
    )
    block_app(store, 2)

    # Repot försvinner ur synken (raderat/privatiserat).
    transport.add(repos_path("tokke2"), [api_repo(1, "Appen")])
    report = sync_accounts(store, make_client(transport))

    entry = store.get_entry(2)
    assert entry is not None and entry.sync_state == "missing"
    assert store.get_install(2) is not None  # installationen finns kvar
    assert is_blocked(store, 2)  # spärren finns kvar
    assert report.marked_missing == ["tokke2/Borta"]


def test_misslyckat_konto_markerar_inte_andra_repon_som_forsvunna(
    store: Store, transport: FakeTransport
):
    transport.add(repos_path("tokke2"), [api_repo(1, "Appen", owner="tokke2")])
    transport.add(repos_path("ananan"), [api_repo(9, "Extern", owner="ananan")])
    prime_repo(transport, "tokke2", "Appen", 1)
    prime_repo(transport, "ananan", "Extern", 9)
    store.add_account("tokke2")
    store.add_account("ananan")
    sync_accounts(store, make_client(transport))

    # Nu dör anslutningen för "ananan" – dess repo får inte markeras som försvunnet.
    transport.add(repos_path("ananan"), {"message": "Bad credentials"}, status=401)
    report = sync_accounts(store, make_client(transport))

    assert "ananan" in report.failed_accounts
    assert report.synced_accounts == ["tokke2"]
    assert store.get_entry(9).sync_state == "available"


def test_releasefel_stoppar_inte_synken(store: Store, transport: FakeTransport):
    transport.add(repos_path("tokke2"), [api_repo(1, "Appen")])
    transport.add(releases_path("tokke2", "Appen"), "internt fel", status=500)
    store.add_account("tokke2")

    report = sync_accounts(store, make_client(transport))

    assert "tokke2/Appen" in report.release_errors
    assert store.get_entry(1) is not None  # repot syns ändå


def test_synken_installerar_aldrig_nagot(store: Store, transport: FakeTransport):
    transport.add(repos_path("tokke2"), [api_repo(1, "Appen")])
    prime_repo(transport, "tokke2", "Appen", 1)
    store.add_account("tokke2")

    sync_accounts(store, make_client(transport))

    assert store.list_installs() == []  # inget installeras av en synk
