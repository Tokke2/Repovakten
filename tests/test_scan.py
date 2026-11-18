"""Tester för repovakten.scan – hitta appar som redan är installerade."""
from __future__ import annotations

import hashlib

import pytest

from repovakten.errors import RepovaktenError
from repovakten.installer import install_from_zip
from repovakten.models import GitHubRepo, InstallRecord
from repovakten.scan import LOCAL_TAG, scan_folder
from repovakten.store import Store

from conftest import make_zip


def add_repo(store: Store, repo_id: int = 1, name: str = "recept", owner: str = "tokke2"):
    repo = GitHubRepo(
        id=repo_id,
        name=name,
        full_name=f"{owner}/{name}",
        owner=owner,
        html_url=f"https://github.com/{owner}/{name}",
        language="Python",
    )
    store.upsert_repo(repo)
    return repo


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------- skanning

def test_standardlayout_registreras_med_manifest(tmp_path, store):
    add_repo(store)
    folder = tmp_path / "appar"
    app_dir = folder / "recept"
    app_dir.mkdir(parents=True)
    (app_dir / "app.py").write_bytes(b"print(1)\n")
    (app_dir / "storage").mkdir()
    (app_dir / "storage" / "data.json").write_bytes(b"{}")

    report = scan_folder(folder, store)
    assert len(report.hits) == 1
    hit = report.hits[0]
    assert hit.registered is True
    assert hit.full_name == "tokke2/recept"
    assert hit.path == app_dir
    assert hit.file_count == 1  # storage/ bevaras och räknas inte

    record = store.get_install(1)
    assert record is not None
    assert record.installed_tag == LOCAL_TAG
    assert record.install_dir == str(app_dir)
    assert record.files == {"app.py": sha(b"print(1)\n")}
    assert "Registrerade som installerade" in report.summary_swedish()


def test_lost_lage_mapp_med_namn(tmp_path, store):
    add_repo(store, name="kalkyl")
    folder = tmp_path / "blandat"
    app_dir = folder / "kalkyl"
    app_dir.mkdir(parents=True)
    (app_dir / "main.py").write_bytes(b"x")

    report = scan_folder(folder, store)
    assert [hit.path for hit in report.hits] == [app_dir]
    assert store.get_install(1) is not None


def test_mappen_sjalv_kan_vara_appen(tmp_path, store):
    add_repo(store, name="spelet")
    folder = tmp_path / "spelet"
    folder.mkdir()
    (folder / "start.py").write_bytes(b"x")

    report = scan_folder(folder, store)
    assert [hit.path for hit in report.hits] == [folder]


def test_aldre_layout_med_agare_hittas_också(tmp_path, store):
    add_repo(store)
    folder = tmp_path / "appar"
    app_dir = folder / "tokke2" / "recept"  # äldre layout
    app_dir.mkdir(parents=True)
    (app_dir / "app.py").write_bytes(b"x")

    report = scan_folder(folder, store)
    assert [hit.path for hit in report.hits] == [app_dir]


def test_registrerad_mapp_har_foretrede(tmp_path, store):
    add_repo(store)
    folder = tmp_path / "appar"
    flat = folder / "recept"
    legacy = folder / "tokke2" / "recept"
    flat.mkdir(parents=True)
    legacy.mkdir(parents=True)
    (flat / "a.py").write_bytes(b"flat")
    (legacy / "a.py").write_bytes(b"legacy")
    store.set_install(
        InstallRecord(
            repo_id=1,
            repo_full_name="tokke2/recept",
            installed_tag="v2.0.0",
            install_dir=str(legacy),
            installed_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
            files={"a.py": sha(b"legacy")},
        )
    )

    report = scan_folder(folder, store)
    assert [hit.path for hit in report.hits] == [legacy]  # den gamla vinner


def test_redan_kand_app_hoppas_over(tmp_path, store):
    add_repo(store)
    folder = tmp_path / "appar"
    app_dir = folder / "recept"
    app_dir.mkdir(parents=True)
    (app_dir / "app.py").write_bytes(b"x")
    store.set_install(
        InstallRecord(
            repo_id=1,
            repo_full_name="tokke2/recept",
            installed_tag="v2.0.0",
            install_dir=str(app_dir),
            installed_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
            files={"app.py": sha(b"x")},
        )
    )

    report = scan_folder(folder, store)
    assert report.hits[0].registered is False
    assert store.get_install(1).installed_tag == "v2.0.0"  # rörs inte
    assert "Redan kända" in report.summary_swedish()


def test_okanda_kataloger_rapporteras_men_rors_inte(tmp_path, store):
    add_repo(store)
    folder = tmp_path / "appar"
    folder.mkdir()
    unknown = folder / "framling"
    unknown.mkdir()
    (unknown / "secret.txt").write_bytes(b"y")

    report = scan_folder(folder, store)
    assert report.hits == []
    assert report.unknown_dirs == [unknown]
    assert (unknown / "secret.txt").read_bytes() == b"y"  # inget ändrat
    assert "hoppades över" in report.summary_swedish()
    assert "Inga installerade appar" in report.summary_swedish()


def test_tom_eller_endast_bevarad_katalog_raknas_inte(tmp_path, store):
    add_repo(store)
    folder = tmp_path / "appar"
    (folder / "recept" / "storage").mkdir(parents=True)
    (folder / "recept" / "storage" / "d.json").write_bytes(b"{}")

    report = scan_folder(folder, store)
    assert report.hits == []
    assert store.get_install(1) is None


def test_saknad_mapp_felar_snyggt(tmp_path, store):
    with pytest.raises(RepovaktenError):
        scan_folder(tmp_path / "finns-ej", store)


# -------------------------------------------------- installationsrot i store

def test_install_root_sparas_och_laddas(tmp_path):
    store = Store(tmp_path / "state.json")
    assert store.get_install_root() is None
    store.set_install_root(str(tmp_path / "appar"))
    assert store.get_install_root() == str(tmp_path / "appar")

    igen = Store(tmp_path / "state.json")
    assert igen.get_install_root() == str(tmp_path / "appar")
    igen.set_install_root(None)  # återställ till standard
    assert igen.get_install_root() is None
    assert Store(tmp_path / "state.json").get_install_root() is None


def test_install_from_zip_utan_install_dir_foljer_vald_rot(tmp_path, store):
    store.set_install_root(str(tmp_path / "appar"))
    zip_path = make_zip(tmp_path / "paket.zip", {"app.py": b"print(1)\n"})

    install_from_zip(
        zip_path, store=store, repo_id=5, tag="v1.0.0", repo_full_name="tokke2/recept"
    )
    assert (tmp_path / "appar" / "recept" / "app.py").exists()


def test_uppdatering_star_kvar_i_registrerad_mapp(tmp_path, store):
    store.set_install_root(str(tmp_path / "appar"))
    zip1 = make_zip(tmp_path / "a.zip", {"app.py": b"v1\n"})
    install_from_zip(
        zip1, store=store, repo_id=5, tag="v1.0.0", repo_full_name="tokke2/recept"
    )

    # Användaren byter installationsrot – uppdateringen ska ändå hamna
    # där appen redan ligger (annars blir det dubbletter).
    store.set_install_root(str(tmp_path / "annat"))
    zip2 = make_zip(tmp_path / "b.zip", {"app.py": b"v2\n"})
    install_from_zip(
        zip2, store=store, repo_id=5, tag="v1.1.0", repo_full_name="tokke2/recept"
    )

    target = tmp_path / "appar" / "recept" / "app.py"
    assert target.read_text(encoding="utf-8") == "v2\n"
    assert not (tmp_path / "annat").exists()
