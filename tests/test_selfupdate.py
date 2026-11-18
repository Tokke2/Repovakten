"""Tester för repovakten.selfupdate – självuppdatering från den rullande releasen."""
from __future__ import annotations

import hashlib
import zipfile

import pytest

from repovakten import installer, selfupdate
from repovakten.errors import UnsafeArchiveError
from repovakten.models import Release, ReleaseAsset
from repovakten.store import Store

from conftest import make_tree, make_zip


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def release_zip(path, *, pkg: dict[str, bytes], extras: dict[str, bytes] | None = None,
                root: str = "Repovakten-0.0.1"):
    """Bygg en release-ZIP i samma form som scripts/build_release.py."""
    members = {f"{root}/repovakten/{rel}": data for rel, data in pkg.items()}
    members.update({f"{root}/{rel}": data for rel, data in (extras or {}).items()})
    return make_zip(path, members)


class StubClient:
    def __init__(self, releases: list[Release]) -> None:
        self._releases = releases
        self.calls: list[tuple[str, str]] = []

    def list_releases(self, owner: str, repo: str, *, repo_id: int = 0, per_page: int = 100):
        self.calls.append((owner, repo))
        return list(self._releases)


def make_release(tag="v0.0.1", *, draft=False, prerelease=False,
                 asset_name="Repovakten-0.0.1-portable.zip") -> Release:
    asset = ReleaseAsset(
        id=1, name=asset_name, size=42, download_url="https://example.com/paket.zip",
        content_type="application/zip",
    )
    return Release(
        id=10, repo_id=1462613139, tag_name=tag, draft=draft, prerelease=prerelease,
        published_at="2026-11-18T00:00:00Z", assets=(asset,),
    )


# ------------------------------------------------------- zip-urval

def test_package_files_in_zip(tmp_path):
    archive = release_zip(
        tmp_path / "rel.zip",
        pkg={"__init__.py": b"v", "gui.py": b"g", "ui/app.py": b"u"},
        extras={"README.md": b"r", "repovakten.sh": b"#!/bin/sh", "VERSION": b"0.0.1"},
    )
    files = selfupdate.package_files_in_zip(archive)
    assert set(files) == {"__init__.py", "gui.py", "ui/app.py"}
    assert files["__init__.py"] == sha(b"v")


def test_build_self_zip_endast_paketet(tmp_path):
    archive = release_zip(
        tmp_path / "rel.zip",
        pkg={"__init__.py": b"v", "ui/app.py": b"u"},
        extras={"README.md": b"r", "VERSION": b"0.0.1"},
    )
    dest = selfupdate.build_self_zip(archive, tmp_path / "själv.zip")
    with zipfile.ZipFile(dest) as zf:
        assert sorted(zf.namelist()) == ["__init__.py", "ui/app.py"]


def test_build_self_zip_utan_paket_avvisas(tmp_path):
    archive = make_zip(tmp_path / "rel.zip", {"README.md": b"r", "Repovakten.bat": b"@echo"})
    with pytest.raises(UnsafeArchiveError):
        selfupdate.build_self_zip(archive, tmp_path / "själv.zip")


# ------------------------------------------------------- jämförelse

def test_compare_self_identisk(tmp_path):
    archive = release_zip(tmp_path / "rel.zip", pkg={"__init__.py": b"samma", "gui.py": b"samma"})
    pkg = make_tree(tmp_path / "repovakten", {"__init__.py": b"samma", "gui.py": b"samma"})
    report = selfupdate.compare_self(archive, pkg_dir=pkg)
    assert not report.differences
    assert report.identical_files == 2


def test_compare_self_visar_vilka_filer_som_skiljer(tmp_path):
    archive = release_zip(
        tmp_path / "rel.zip",
        pkg={"__init__.py": b"ny", "tillagg.py": b"ny", "gui.py": b"samma"},
    )
    pkg = make_tree(
        tmp_path / "repovakten",
        {"__init__.py": b"gammal", "gammal.py": b"gammal", "gui.py": b"samma"},
    )
    report = selfupdate.compare_self(archive, pkg_dir=pkg)
    assert [d.path for d in report.changed] == ["__init__.py"]
    assert [d.path for d in report.new] == ["tillagg.py"]
    assert [d.path for d in report.removed] == ["gammal.py"]
    assert report.identical_files == 1
    assert report.has_changes


def test_compare_self_ignorerar_pycache(tmp_path):
    archive = release_zip(tmp_path / "rel.zip", pkg={"__init__.py": b"samma"})
    pkg = make_tree(
        tmp_path / "repovakten",
        {"__init__.py": b"samma", "__pycache__/__init__.cpython-311.pyc": b"cache"},
    )
    report = selfupdate.compare_self(archive, pkg_dir=pkg)
    assert not report.differences


def test_compare_self_manifest_hittar_saknad_fil(tmp_path):
    archive = release_zip(tmp_path / "rel.zip", pkg={"__init__.py": b"samma"})
    pkg = make_tree(tmp_path / "repovakten", {"__init__.py": b"samma"})
    manifest = {"__init__.py": sha(b"samma"), "borta.py": sha(b"borta")}
    report = selfupdate.compare_self(archive, pkg_dir=pkg, manifest_files=manifest)
    assert [d.path for d in report.missing] == ["borta.py"]


# ------------------------------------------------------- installation

def test_install_update_uppdaterar_med_backup(tmp_path):
    archive = release_zip(
        tmp_path / "rel.zip",
        pkg={"__init__.py": b"v2", "ui/app.py": b"u2"},
        extras={"README.md": b"r", "VERSION": b"0.0.1"},
    )
    pkg = make_tree(
        tmp_path / "repovakten",
        {"__init__.py": b"v1", "gammal.py": b"gammal", "ui/app.py": b"u1",
         "__pycache__/x.pyc": b"cache"},
    )
    store = Store(tmp_path / "state.json")

    result = selfupdate.install_update(
        archive, store=store, tag="v0.0.1", pkg_dir=pkg, backup_root=tmp_path / "backups"
    )

    # Ny kod på plats, utgående borttagen, cache bevarad.
    assert (pkg / "__init__.py").read_bytes() == b"v2"
    assert (pkg / "ui" / "app.py").read_bytes() == b"u2"
    assert not (pkg / "gammal.py").exists()
    assert (pkg / "__pycache__" / "x.pyc").read_bytes() == b"cache"
    # Inga syskonfiler skapades bredvid paketet.
    assert not (tmp_path / "README.md").exists()
    assert not (tmp_path / "VERSION").exists()
    # Backup med gamla filer.
    assert result.backup_dir is not None
    assert (result.backup_dir / "__init__.py").read_bytes() == b"v1"
    assert (result.backup_dir / "gammal.py").read_bytes() == b"gammal"
    # Installationsregistret ligger under det syntetiska ID:t.
    record = store.get_install(selfupdate.SELF_RECORD_ID)
    assert record is not None
    assert record.installed_tag == "v0.0.1"
    assert set(record.files) == {"__init__.py", "ui/app.py"}


def test_install_update_rullar_tillbaka_vid_fel(tmp_path, monkeypatch):
    archive = release_zip(tmp_path / "rel.zip", pkg={"__init__.py": b"v2", "extra.py": b"ny"})
    pkg = make_tree(tmp_path / "repovakten", {"__init__.py": b"v1"})
    store = Store(tmp_path / "state.json")

    def boom(*_args, **_kwargs):
        raise RuntimeError("disken krånglar")

    monkeypatch.setattr(installer, "_extract", boom)
    with pytest.raises(RuntimeError):
        selfupdate.install_update(
            archive, store=store, tag="v0.0.1", pkg_dir=pkg, backup_root=tmp_path / "backups"
        )
    # Ingen fil ändrades.
    assert (pkg / "__init__.py").read_bytes() == b"v1"
    assert not (pkg / "extra.py").exists()


# ------------------------------------------------------- kontroll mot GitHub

def test_find_self_release_valjer_stabil_och_basta_zip():
    draft = make_release("v0.0.2", draft=True)
    stable = make_release("v0.0.1")
    client = StubClient([draft, stable])
    release, asset = selfupdate.find_self_release(client)
    assert release.tag_name == "v0.0.1"
    assert asset.name == "Repovakten-0.0.1-portable.zip"
    assert client.calls == [("Tokke2", "Repovakten")]


def test_find_self_release_utan_release_felar():
    with pytest.raises(Exception):
        selfupdate.find_self_release(StubClient([]))


def test_check_for_update_med_stubs(tmp_path):
    archive = release_zip(
        tmp_path / "rel.zip",
        pkg={"__init__.py": b"v2", "gui.py": b"samma"},
    )
    pkg = make_tree(tmp_path / "repovakten", {"__init__.py": b"v1", "gui.py": b"samma"})

    def fake_fetch(url: str, dest) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(archive.read_bytes())

    plan = selfupdate.check_for_update(
        StubClient([make_release()]), pkg_dir=pkg, temp_dir=tmp_path / "dl", fetch=fake_fetch
    )
    assert plan.tag == "v0.0.1"
    assert plan.has_changes
    assert [d.path for d in plan.report.changed] == ["__init__.py"]

    # Och när koden redan är identisk: inga ändringar.
    same = make_tree(tmp_path / "samma", {"__init__.py": b"v2", "gui.py": b"samma"})
    plan2 = selfupdate.check_for_update(
        StubClient([make_release()]), pkg_dir=same, temp_dir=tmp_path / "dl2", fetch=fake_fetch
    )
    assert not plan2.has_changes
