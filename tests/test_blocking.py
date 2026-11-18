"""Tester för repovakten.blocking – adminspärrar."""
from __future__ import annotations

import pytest

from repovakten.blocking import (
    assert_install_allowed,
    block_app,
    blocked_repo_ids,
    install_block_reason,
    is_blocked,
    list_blocked,
    unblock_app,
)
from repovakten.errors import InstallationBlockedError
from repovakten.models import GitHubRepo, InstallRecord
from repovakten.store import Store


def test_blockera_och_tillata_igen(store: Store):
    assert not is_blocked(store, 42)
    rule = block_app(store, 42, reason="Instabil build")
    assert rule.reason == "Instabil build"
    assert is_blocked(store, 42)
    assert blocked_repo_ids(store) == {42}
    assert install_block_reason(store, 42) == "Instabil build"
    assert unblock_app(store, 42)
    assert not is_blocked(store, 42)


def test_assert_install_allowed_kastar_for_spärrad(store: Store):
    block_app(store, 42, reason="Väntar på signering")
    with pytest.raises(InstallationBlockedError) as excinfo:
        assert_install_allowed(store, 42)
    assert "42" in str(excinfo.value)
    assert "Väntar på signering" in str(excinfo.value)


def test_assert_install_allowed_tillater_vanlig(store: Store):
    assert_install_allowed(store, 42)  # kastar inte


def test_sparr_overlever_omladdning(store: Store):
    block_app(store, 42, reason="permanent")
    fresh = Store(store.path)
    assert is_blocked(fresh, 42)
    assert install_block_reason(fresh, 42) == "permanent"


def test_sparr_nycklas_pa_repo_id_och_overlever_namnbyte(store: Store):
    store.upsert_repo(
        GitHubRepo(id=42, name="GammaltNamn", full_name="tokke2/GammaltNamn",
                   owner="tokke2", html_url="https://github.com/tokke2/GammaltNamn")
    )
    block_app(store, 42)
    # Samma repo-ID, nytt namn:
    store.upsert_repo(
        GitHubRepo(id=42, name="NyttNamn", full_name="tokke2/NyttNamn",
                   owner="tokke2", html_url="https://github.com/tokke2/NyttNamn")
    )
    assert is_blocked(store, 42)
    with pytest.raises(InstallationBlockedError):
        assert_install_allowed(store, 42)


def test_sparr_raderar_inte_installerad_kopia(store: Store, tmp_path):
    install_dir = tmp_path / "installed"
    install_dir.mkdir()
    payload = install_dir / "app.exe"
    payload.write_bytes(b"programbytes")
    store.set_install(
        InstallRecord(
            repo_id=42,
            repo_full_name="tokke2/Appen",
            installed_tag="v1.2.0",
            install_dir=str(install_dir),
            installed_at="2026-11-01T00:00:00Z",
            updated_at="2026-11-01T00:00:00Z",
            files={"app.exe": "abc"},
        )
    )
    block_app(store, 42, reason="temporärt")
    assert payload.read_bytes() == b"programbytes"  # filerna finns kvar
    assert store.get_install(42) is not None  # installationsregistret finns kvar


def test_unblock_returnerar_false_om_ingen_sparr(store: Store):
    assert not unblock_app(store, 999)


def test_list_blocked_sorterad(store: Store):
    block_app(store, 3, reason="c")
    block_app(store, 1, reason="a")
    block_app(store, 2, reason="b")
    ids = [r.repo_id for r in list_blocked(store)]
    assert ids == sorted(ids)
