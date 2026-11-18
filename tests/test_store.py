"""Tester för repovakten.store – beständig lagring."""
from __future__ import annotations

import json

import pytest

from repovakten.errors import StoreError
from repovakten.models import BlockRule, GitHubRepo, InstallRecord, Release, ReleaseAsset
from repovakten.store import Store, default_state_dir


def repo(repo_id: int, name: str, owner: str = "tokke2") -> GitHubRepo:
    return GitHubRepo(
        id=repo_id,
        name=name,
        full_name=f"{owner}/{name}",
        owner=owner,
        html_url=f"https://github.com/{owner}/{name}",
        language="Python",
    )


def test_ny_store_ar_tom(store: Store):
    assert store.accounts() == []
    assert store.repo_entries() == []
    assert store.list_blocks() == []
    assert store.get_last_sync() is None


def test_konton_rundtrip(store: Store):
    store.add_account("Tokke2")
    assert store.accounts() == ["Tokke2"]
    # Omladdning från disk
    andel = Store(store.path)
    assert andel.accounts() == ["Tokke2"]


def test_add_account_validerar_och_deduplikerar(store: Store):
    store.add_account("@Tokke2")
    store.add_account("tokke2")  # samma konto, annan skiftläge
    assert store.accounts() == ["Tokke2"]
    with pytest.raises(ValueError):
        store.add_account("inte ett giltigt namn!!")


def test_remove_account_behaller_katalogen(store: Store):
    store.add_account("tokke2")
    store.upsert_repo(repo(42, "Appen"))
    assert store.remove_account("tokke2")
    assert store.repo_entries()  # katalogposten är kvar
    assert store.accounts() == []


def test_namnbyte_behaller_post_och_seen(store: Store):
    store.upsert_repo(repo(42, "GamlaNamnet"), seen_at="2026-01-01T00:00:00Z")
    entry, created = store.upsert_repo(repo(42, "NyaNamnet"), seen_at="2026-02-01T00:00:00Z")
    assert not created
    assert entry.repo.name == "NyaNamnet"
    assert entry.first_seen_at == "2026-01-01T00:00:00Z"
    assert len(store.repo_entries()) == 1


def test_mark_missing_raderar_inte(store: Store):
    store.upsert_repo(repo(42, "Appen"))
    assert store.mark_missing(42)
    entry = store.get_entry(42)
    assert entry is not None and entry.sync_state == "missing"


def test_release_cachas_och_rundtrippar(store: Store):
    store.upsert_repo(repo(42, "Appen"))
    assets = (ReleaseAsset(id=1, name="Appen-win64.zip", size=100, download_url="https://x/y.zip"),)
    rels = [Release(id=7, repo_id=0, tag_name="v1.2.0", assets=assets)]
    store.set_releases(42, rels, fetched_at="2026-11-18T10:00:00Z")
    entry = Store(store.path).get_entry(42)
    assert entry.releases[0].tag_name == "v1.2.0"
    assert entry.releases[0].repo_id == 42  # alltid nycklat mot katalogens repo-ID
    assert entry.releases[0].assets[0].name == "Appen-win64.zip"
    assert entry.releases_fetched_at == "2026-11-18T10:00:00Z"


def test_installation_rundtrip(store: Store):
    record = InstallRecord(
        repo_id=42,
        repo_full_name="tokke2/Appen",
        installed_tag="v1.2.0",
        install_dir="/tmp/x",
        installed_at="2026-11-01T00:00:00Z",
        updated_at="2026-11-01T00:00:00Z",
        files={"app.py": "abc123"},
        preserve_paths=["storage/"],
    )
    store.set_install(record)
    loaded = Store(store.path).get_install(42)
    assert loaded.installed_tag == "v1.2.0"
    assert loaded.files == {"app.py": "abc123"}
    assert loaded.preserve_paths == ["storage/"]


def test_save_skapar_reservfil(store: Store):
    store.add_account("tokke2")
    store.set_install(
        InstallRecord(
            repo_id=1,
            repo_full_name="tokke2/x",
            installed_tag="v1",
            install_dir="/tmp/x",
            installed_at="a",
            updated_at="a",
        )
    )
    assert store.backup_path.exists()
    backup = json.loads(store.backup_path.read_text(encoding="utf-8"))
    assert backup["installs"] == {}  # reserven speglar tillståndet *före* senaste sparningen


def test_skadad_huvudfil_faller_tillbaka_pa_backup(store: Store):
    store.add_account("tokke2")
    store.add_account("annan")  # triggar reservkopia med bägge? nej – en i taget
    store.path.write_text("{{{ inte json", encoding="utf-8")
    fresh = Store(store.path)
    with pytest.warns(RuntimeWarning):
        assert "tokke2" in fresh.accounts()


def test_skadad_huvud_och_backup_ger_storeerror(store: Store):
    store.save()
    store.path.write_text("{{{", encoding="utf-8")
    store.backup_path.write_text("inte heller json", encoding="utf-8")
    fresh = Store(store.path)
    with pytest.raises(StoreError):
        fresh.load()


def test_nyare_formatversion_vagras(store: Store):
    store.save()
    data = json.loads(store.path.read_text(encoding="utf-8"))
    data["version"] = 999
    store.path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(StoreError):
        Store(store.path).load()


def test_reipo_id_nycklar_i_json(store: Store):
    store.upsert_repo(repo(42, "Appen"))
    store.set_block(BlockRule(repo_id=42, reason="test", blocked_at="2026-11-18T00:00:00Z"))
    raw = json.loads(store.path.read_text(encoding="utf-8"))
    assert "42" in raw["repos"] and "42" in raw["blocks"]


def test_default_state_dir_respekterar_env(monkeypatch, tmp_path):
    monkeypatch.setenv("REPOVAKTEN_HOME", str(tmp_path / "anpassad"))
    assert default_state_dir() == tmp_path / "anpassad"
