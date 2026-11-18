"""Tester för repovakten.releases."""
from __future__ import annotations

from repovakten.models import Release, ReleaseAsset
from repovakten.releases import (
    installable_assets,
    is_source_code_asset,
    rank_assets_for_platform,
    select_latest_stable,
    select_latest_any,
    zip_assets,
)


def asset(name: str, asset_id: int = 1, size: int = 1024) -> ReleaseAsset:
    return ReleaseAsset(id=asset_id, name=name, size=size, download_url=f"https://example.com/{name}")


def release(tag: str, *, draft=False, prerelease=False, published="2026-11-01T10:00:00Z", assets=()) -> Release:
    return Release(
        id=hash(tag) & 0x7FFFFFFF,
        repo_id=1,
        tag_name=tag,
        draft=draft,
        prerelease=prerelease,
        published_at=published,
        assets=tuple(assets),
    )


def test_valjer_senaste_stabila():
    rels = [
        release("v1.0.0", published="2026-01-01T00:00:00Z"),
        release("v1.2.0", published="2026-03-01T00:00:00Z"),
        release("v1.1.0", published="2026-02-01T00:00:00Z"),
    ]
    assert select_latest_stable(rels).tag_name == "v1.2.0"


def test_prerelease_raknas_inte_som_stabil():
    rels = [
        release("v1.0.0", published="2026-01-01T00:00:00Z"),
        release("v2.0.0-rc.1", prerelease=True, published="2026-06-01T00:00:00Z"),
    ]
    assert select_latest_stable(rels).tag_name == "v1.0.0"


def test_utkast_raknas_aldrig():
    rels = [
        release("v1.0.0", published="2026-01-01T00:00:00Z"),
        release("v2.0.0", draft=True, published="2026-06-01T00:00:00Z"),
    ]
    assert select_latest_stable(rels).tag_name == "v1.0.0"


def test_ingen_stabil_release():
    rels = [release("v2.0.0-rc.1", prerelease=True), release("v3.0.0", draft=True)]
    assert select_latest_stable(rels) is None


def test_publiceringstid_vager_tyngre_an_tagg():
    # v9.9.9 taggad men publicerad *före* v1.0.0: senaste tiden vinner.
    rels = [
        release("v9.9.9", published="2026-01-01T00:00:00Z"),
        release("v1.0.0", published="2026-05-01T00:00:00Z"),
    ]
    assert select_latest_stable(rels).tag_name == "v1.0.0"


def test_select_latest_any_faller_tillbaka_pa_prerelease():
    rels = [release("v2.0.0-rc.1", prerelease=True, published="2026-06-01T00:00:00Z")]
    assert select_latest_any(rels).tag_name == "v2.0.0-rc.1"
    assert select_latest_any([]) is None


def test_source_code_tillgangen_filtreras_bort():
    assert is_source_code_asset("Source code (zip).zip")
    assert is_source_code_asset("source-code.zip")
    assert not is_source_code_asset("MyApp-1.2.0-win64.zip")
    rel = release("v1.0.0", assets=[asset("Source code (zip).zip"), asset("MyApp-win64.zip")])
    assert [a.name for a in zip_assets(rel)] == ["MyApp-win64.zip"]


def test_installable_assets_kraver_zip():
    rel = release(
        "v1.0.0",
        assets=[asset("app.zip"), asset("app.tar.gz"), asset("app.exe", 2)],
    )
    assert [a.name for a in installable_assets(rel)] == ["app.zip"]


def test_rank_assets_windows():
    assets = [
        asset("MyApp-1.2.0-win64.zip", 1),
        asset("MyApp-1.2.0-macos-universal.zip", 2),
        asset("MyApp-1.2.0-linux-x86_64.zip", 3),
        asset("MyApp-1.2.0.zip", 4),
    ]
    ranked = rank_assets_for_platform(assets, os_name="windows", arch="x86_64")
    assert ranked[0].asset.name == "MyApp-1.2.0-win64.zip"
    assert ranked[0].likely
    # linux-paketet nedvärderas under det generiska
    names = [s.asset.name for s in ranked]
    assert names.index("MyApp-1.2.0.zip") < names.index("MyApp-1.2.0-linux-x86_64.zip")


def test_rank_assets_mac_arm():
    assets = [
        asset("MyApp-mac-arm64.zip", 1),
        asset("MyApp-mac-x86_64.zip", 2),
        asset("MyApp-win64.zip", 3),
    ]
    ranked = rank_assets_for_platform(assets, os_name="macos", arch="arm64")
    assert ranked[0].asset.name == "MyApp-mac-arm64.zip"


def test_rank_assets_linux_x86_64():
    assets = [
        asset("app-linux-x86_64.zip", 1),
        asset("app-linux-aarch64.zip", 2),
    ]
    ranked = rank_assets_for_platform(assets, os_name="linux", arch="x86_64")
    assert ranked[0].asset.name == "app-linux-x86_64.zip"


def test_rank_assets_portable_bonus():
    generic = asset("MyApp.zip", 1)
    portable = asset("MyApp-portable.zip", 2)
    ranked = rank_assets_for_platform([generic, portable], os_name="windows", arch="x86_64")
    assert ranked[0].asset.name == "MyApp-portable.zip"
