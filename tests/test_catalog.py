"""Tester för repovakten.catalog – vy-modellen för gränssnittet."""
from __future__ import annotations

from repovakten.blocking import block_app
from repovakten.catalog import InstallStatus, build_catalog_rows, updates_for_installed_apps
from repovakten.models import GitHubRepo, InstallRecord, Release, ReleaseAsset
from repovakten.store import Store


def make_repo(store: Store, repo_id: int = 1, name: str = "Appen", language="Python"):
    repo = GitHubRepo(
        id=repo_id,
        name=name,
        full_name=f"tokke2/{name}",
        owner="tokke2",
        html_url=f"https://github.com/tokke2/{name}",
        language=language,
    )
    store.upsert_repo(repo)
    return repo


def zip_release(store: Store, repo_id: int, tag: str = "v1.2.0"):
    release = Release(
        id=100,
        repo_id=repo_id,
        tag_name=tag,
        published_at="2026-11-01T10:00:00Z",
        assets=(ReleaseAsset(id=1, name=f"Appen-win64.zip", size=100, download_url="https://x/y.zip"),),
    )
    store.set_releases(repo_id, [release])


def install(store: Store, repo_id: int, tag: str = "v1.0.0"):
    store.set_install(
        InstallRecord(
            repo_id=repo_id,
            repo_full_name="tokke2/Appen",
            installed_tag=tag,
            install_dir="/tmp/Appen",
            installed_at="2026-10-01T00:00:00Z",
            updated_at="2026-10-01T00:00:00Z",
        )
    )


def rows_by_id(store: Store):
    return {row.repo.id: row for row in build_catalog_rows(store)}


def test_repo_med_stabil_release_och_zip_ar_klar(store: Store):
    make_repo(store, 1)
    zip_release(store, 1)
    row = rows_by_id(store)[1]
    assert row.status is InstallStatus.READY
    assert row.can_install
    assert row.install_allowed
    assert row.installed_version is None
    assert row.latest_stable_tag == "v1.2.0"
    assert row.installable_assets == 1


def test_repo_utan_release_syns_andak(store: Store):
    make_repo(store, 1, language="PHP")
    row = rows_by_id(store)[1]
    assert row.status is InstallStatus.NO_RELEASE
    assert not row.can_install
    assert row.repo.language == "PHP"


def test_bara_prerelease_ger_no_stable_release(store: Store):
    make_repo(store, 1)
    store.set_releases(
        1,
        [Release(id=1, repo_id=1, tag_name="v2.0.0-rc.1", prerelease=True,
                 published_at="2026-11-01T00:00:00Z",
                 assets=(ReleaseAsset(id=1, name="a.zip", size=1, download_url="u"),))],
    )
    row = rows_by_id(store)[1]
    assert row.status is InstallStatus.NO_STABLE_RELEASE
    assert row.latest_any_tag == "v2.0.0-rc.1"


def test_stabil_release_utan_zip_ger_no_installable_asset(store: Store):
    make_repo(store, 1)
    store.set_releases(
        1,
        [Release(id=1, repo_id=1, tag_name="v1.0.0",
                 published_at="2026-11-01T00:00:00Z",
                 assets=(ReleaseAsset(id=1, name="app.tar.gz", size=1, download_url="u"),))],
    )
    row = rows_by_id(store)[1]
    assert row.status is InstallStatus.NO_INSTALLABLE_ASSET


def test_source_code_zip_raknas_inte_som_app(store: Store):
    make_repo(store, 1)
    store.set_releases(
        1,
        [Release(id=1, repo_id=1, tag_name="v1.0.0",
                 published_at="2026-11-01T00:00:00Z",
                 assets=(ReleaseAsset(id=1, name="Source code (zip).zip", size=1, download_url="u"),))],
    )
    row = rows_by_id(store)[1]
    assert row.status is InstallStatus.NO_INSTALLABLE_ASSET


def test_spärrad_app_visas_men_far_inte_installeras(store: Store):
    make_repo(store, 1)
    zip_release(store, 1)
    block_app(store, 1, reason="Instabil")
    row = rows_by_id(store)[1]
    assert row.status is InstallStatus.BLOCKED
    assert not row.install_allowed
    assert not row.can_install


def test_forsvunnet_repo_markeras(store: Store):
    make_repo(store, 1)
    zip_release(store, 1)
    store.mark_missing(1)
    row = rows_by_id(store)[1]
    assert row.status is InstallStatus.MISSING


def test_installerad_version_och_uppdateringskandidat(store: Store):
    make_repo(store, 1)
    zip_release(store, 1, "v1.2.0")
    install(store, 1, "v1.0.0")
    row = rows_by_id(store)[1]
    assert row.installed_version == "v1.0.0"
    assert row.has_update_candidate


def test_samma_version_ar_ingen_uppdateringskandidat(store: Store):
    make_repo(store, 1)
    zip_release(store, 1, "v1.2.0")
    install(store, 1, "v1.2.0")
    row = rows_by_id(store)[1]
    assert not row.has_update_candidate


# --------------------------------------------- uppdateringar för installerade appar

def test_uppdatering_for_installerad_app(store: Store):
    make_repo(store, 1)
    zip_release(store, 1, tag="v1.2.0")
    install(store, 1, tag="v1.0.0")
    updates = updates_for_installed_apps(store)
    assert [r.repo.id for r in updates] == [1]
    assert updates[0].installed_version == "v1.0.0"
    assert updates[0].latest_stable_tag == "v1.2.0"


def test_samma_version_ger_ingen_uppdatering(store: Store):
    make_repo(store, 1)
    zip_release(store, 1, tag="v1.2.0")
    install(store, 1, tag="v1.2.0")
    assert updates_for_installed_apps(store) == []


def test_ej_installerad_app_listas_inte(store: Store):
    make_repo(store, 1)
    zip_release(store, 1)
    assert updates_for_installed_apps(store) == []


def test_sparrad_app_listas_inte(store: Store):
    make_repo(store, 1)
    zip_release(store, 1, tag="v1.2.0")
    install(store, 1, tag="v1.0.0")
    block_app(store, 1)
    assert updates_for_installed_apps(store) == []


def test_release_utan_zip_paket_listas_inte(store: Store):
    make_repo(store, 1)
    store.set_releases(
        1,
        [Release(id=100, repo_id=1, tag_name="v1.3.0",
                 published_at="2026-11-01T10:00:00Z", assets=())],
    )
    install(store, 1, tag="v1.0.0")
    assert updates_for_installed_apps(store) == []
