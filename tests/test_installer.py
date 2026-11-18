"""Tester för repovakten.installer – installation med backup och rullning tillbaka."""
from __future__ import annotations

import hashlib
import os

import pytest

from repovakten import installer
from repovakten.blocking import block_app, is_blocked
from repovakten.compare import compare_install
from repovakten.errors import InstallationBlockedError, RepovaktenError, UnsafeArchiveError
from repovakten.installer import (
    app_install_dir,
    backup_install,
    download_asset,
    install_from_zip,
)
from repovakten.models import GitHubRepo, InstallRecord
from repovakten.store import Store

from conftest import make_tree, make_zip


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def seed_install(
    tmp_path,
    store: Store,
    *,
    repo_id: int = 42,
    files: dict[str, bytes] | None = None,
    storage: dict[str, bytes] | None = None,
    tag: str = "v1.2.0",
):
    files = files or {"app.exe": b"gammal-binar"}
    storage = storage if storage is not None else {"storage/data.db": b"ANVANDARDATA"}
    install_dir = tmp_path / "apps" / "Tokke2" / "Appen"
    all_files = dict(files) | dict(storage)
    make_tree(install_dir, all_files)
    store.set_install(
        InstallRecord(
            repo_id=repo_id,
            repo_full_name="Tokke2/Appen",
            installed_tag=tag,
            install_dir=str(install_dir),
            installed_at="2026-10-01T00:00:00Z",
            updated_at="2026-10-01T00:00:00Z",
            files={rel: sha(data) for rel, data in files.items()},
            preserve_paths=["storage/"],
        )
    )
    return install_dir


# ---------------------------------------------------------------- plats

def test_app_install_dir_saniterar(tmp_path, monkeypatch):
    monkeypatch.setenv("REPOVAKTEN_APPS", str(tmp_path))
    # Platt layout: appens namn direkt i roten – ingen ägar- eller
    # versionsnivå i mappnamnet.
    assert app_install_dir("Tokke2/Appen") == tmp_path / "Appen"


def test_blandat_zip_landar_utan_versionsmapp(tmp_path, store: Store):
    """Rotmapp + lösa filer: innehållet landar rent, utan versionsmapp."""
    archive = make_zip(
        tmp_path / "paket.zip",
        {"MinApp-2.1.0/app.exe": b"bin", "MinApp-2.1.0/lib/x.dll": b"dll", "README.md": b"r"},
    )
    install_dir = tmp_path / "install"
    install_from_zip(
        archive,
        store=store,
        repo_id=7,
        tag="v2.1.0",
        repo_full_name="tokke2/MinApp",
        install_dir=install_dir,
        backup_root=tmp_path / "backups",
    )
    assert (install_dir / "app.exe").read_bytes() == b"bin"
    assert (install_dir / "lib" / "x.dll").exists()
    assert (install_dir / "README.md").exists()
    assert not (install_dir / "MinApp-2.1.0").exists()  # ingen Vnr-mapp


# ------------------------------------------------------------- install

def test_färsk_installation(tmp_path, store: Store):
    archive = make_zip(
        tmp_path / "paket.zip",
        {"app.exe": b"ny-binar", "lib/hjälp.dll": b"dll"},
    )
    result = install_from_zip(
        archive,
        store=store,
        repo_id=42,
        tag="v1.3.0",
        repo_full_name="Tokke2/Appen",
        install_dir=tmp_path / "inst",
        backup_root=tmp_path / "backups",
    )
    install_dir = tmp_path / "inst"
    assert (install_dir / "app.exe").read_bytes() == b"ny-binar"
    assert (install_dir / "lib" / "hjälp.dll").read_bytes() == b"dll"
    assert result.record.installed_tag == "v1.3.0"
    assert result.record.files == {
        "app.exe": sha(b"ny-binar"),
        "lib/hjälp.dll": sha(b"dll"),
    }
    assert result.backup_dir is None  # ingen tidigare kopia att säkerhetskopiera
    assert sorted(d.path for d in result.report.new) == ["app.exe", "lib/hjälp.dll"]


def test_gemensam_rotkatalog_strippas(tmp_path, store: Store):
    archive = make_zip(
        tmp_path / "paket.zip",
        {"MyApp-1.3.0/app.exe": b"binar", "MyApp-1.3.0/readme.txt": b"hej"},
    )
    result = install_from_zip(
        archive,
        store=store,
        repo_id=42,
        tag="v1.3.0",
        repo_full_name="Tokke2/Appen",
        install_dir=tmp_path / "inst",
        backup_root=tmp_path / "backups",
    )
    install_dir = tmp_path / "inst"
    assert (install_dir / "app.exe").exists()
    assert not (install_dir / "MyApp-1.3.0").exists()
    assert set(result.record.files) == {"app.exe", "readme.txt"}
    # Rapporten visar samma sökvägar som hamnar på disk (utan rot).
    assert sorted(d.path for d in result.report.new) == ["app.exe", "readme.txt"]


def test_gemensam_rot_strippas_inte_nar_filer_ligger_pa_toppniva(tmp_path, store: Store):
    archive = make_zip(
        tmp_path / "paket.zip",
        {"app.exe": b"binar", "undermapp/hjälp.dll": b"dll"},
    )
    install_from_zip(
        archive,
        store=store,
        repo_id=42,
        tag="v1.3.0",
        repo_full_name="Tokke2/Appen",
        install_dir=tmp_path / "inst",
        backup_root=tmp_path / "backups",
    )
    assert (tmp_path / "inst" / "app.exe").exists()
    assert (tmp_path / "inst" / "undermapp" / "hjälp.dll").exists()


def test_storage_skrivs_aldrig_över(tmp_path, store: Store):
    install_dir = seed_install(tmp_path, store)
    archive = make_zip(
        tmp_path / "paket.zip",
        {"app.exe": b"ny-binar", "storage/data.db": b"FRAN-RELEASE"},
    )
    install_from_zip(
        archive,
        store=store,
        repo_id=42,
        tag="v1.3.0",
        install_dir=install_dir,
        backup_root=tmp_path / "backups",
    )
    assert (install_dir / "storage" / "data.db").read_bytes() == b"ANVANDARDATA"
    assert store.get_install(42).files.get("storage/data.db") is None


def test_utgaende_filer_tas_bort_men_storage_ligger_kvar(tmp_path, store: Store):
    install_dir = seed_install(tmp_path, store, files={"app.exe": b"gammal", "gammal.dll": b"borta"})
    archive = make_zip(tmp_path / "paket.zip", {"app.exe": b"ny"})
    result = install_from_zip(
        archive,
        store=store,
        repo_id=42,
        tag="v1.3.0",
        install_dir=install_dir,
        backup_root=tmp_path / "backups",
    )
    assert not (install_dir / "gammal.dll").exists()
    assert (install_dir / "storage" / "data.db").exists()
    assert "gammal.dll" in result.removed_files


def test_backup_skapar_kopia_av_tidigare_installation(tmp_path, store: Store):
    install_dir = seed_install(tmp_path, store)
    archive = make_zip(tmp_path / "paket.zip", {"app.exe": b"ny"})
    result = install_from_zip(
        archive,
        store=store,
        repo_id=42,
        tag="v1.3.0",
        install_dir=install_dir,
        backup_root=tmp_path / "backups",
    )
    assert result.backup_dir is not None
    assert (result.backup_dir / "app.exe").read_bytes() == b"gammal-binar"
    assert (result.backup_dir / "storage" / "data.db").read_bytes() == b"ANVANDARDATA"


def test_sparrad_app_kan_inte_installeras(tmp_path, store: Store):
    install_dir = seed_install(tmp_path, store)
    block_app(store, 42, reason="Instabil")
    archive = make_zip(tmp_path / "paket.zip", {"app.exe": b"ny"})
    with pytest.raises(InstallationBlockedError):
        install_from_zip(
            archive,
            store=store,
            repo_id=42,
            tag="v1.3.0",
            install_dir=install_dir,
            backup_root=tmp_path / "backups",
        )
    assert (install_dir / "app.exe").read_bytes() == b"gammal-binar"  # oförändrad
    assert store.get_install(42).installed_tag == "v1.2.0"
    assert not (tmp_path / "backups").exists()  # spärren kollas före backup


def test_trasigt_paket_paverkar_inte_befintlig_installation(tmp_path, store: Store):
    install_dir = seed_install(tmp_path, store)
    trasig = tmp_path / "trasig.zip"
    trasig.write_bytes(b"detta ar ingen zip-fil")
    with pytest.raises(UnsafeArchiveError):
        install_from_zip(
            trasig,
            store=store,
            repo_id=42,
            tag="v1.3.0",
            install_dir=install_dir,
            backup_root=tmp_path / "backups",
        )
    assert (install_dir / "app.exe").read_bytes() == b"gammal-binar"
    assert store.get_install(42).installed_tag == "v1.2.0"


def test_zip_slip_avvisas_fore_skrivning(tmp_path, store: Store):
    install_dir = seed_install(tmp_path, store)
    archive = make_zip(tmp_path / "elak.zip", {"../../elakt.sh": b"rm -rf ~"})
    with pytest.raises(UnsafeArchiveError):
        install_from_zip(
            archive,
            store=store,
            repo_id=42,
            tag="v1.3.0",
            install_dir=install_dir,
            backup_root=tmp_path / "backups",
        )
    assert (install_dir / "app.exe").read_bytes() == b"gammal-binar"


def test_extraktionsfel_rullar_tillbaka_allt(tmp_path, store: Store, monkeypatch):
    install_dir = seed_install(tmp_path, store, files={"app.exe": b"gammal-binar", "behall.txt": b"gammal"})

    def trassel(zip_path, members, target_dir):
        # Simulera krasch mitt i uppackningen: en ny fil skrivs, sedan fel.
        (target_dir / "korrupt.bin").write_bytes("skräp".encode())
        raise RuntimeError("simulerad krasch")

    monkeypatch.setattr(installer, "_extract", trassel)
    archive = make_zip(tmp_path / "paket.zip", {"app.exe": b"ny"})
    with pytest.raises(RuntimeError):
        install_from_zip(
            archive,
            store=store,
            repo_id=42,
            tag="v1.3.0",
            install_dir=install_dir,
            backup_root=tmp_path / "backups",
        )
    assert (install_dir / "app.exe").read_bytes() == b"gammal-binar"
    assert (install_dir / "behall.txt").read_bytes() == b"gammal"
    assert not (install_dir / "korrupt.bin").exists()


def test_färskinstallation_som_kraschar_lamnar_inget_skrap(tmp_path, store: Store, monkeypatch):
    def trassel(zip_path, members, target_dir):
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "korrupt.bin").write_bytes("skräp".encode())
        raise RuntimeError("simulerad krasch")

    monkeypatch.setattr(installer, "_extract", trassel)
    archive = make_zip(tmp_path / "paket.zip", {"app.exe": b"ny"})
    with pytest.raises(RuntimeError):
        install_from_zip(
            archive,
            store=store,
            repo_id=42,
            tag="v1.3.0",
            repo_full_name="Tokke2/Appen",
            install_dir=tmp_path / "ny-app",
            backup_root=tmp_path / "backups",
        )
    assert not (tmp_path / "ny-app").exists()


def test_saknad_fil_i_installationen_repareras_men_redovisas(tmp_path, store: Store):
    install_dir = seed_install(tmp_path, store, files={"app.exe": b"gammal-binar"})
    os.remove(install_dir / "app.exe")  # installationen är skadad
    archive = make_zip(tmp_path / "paket.zip", {"app.exe": b"ny-binar"})
    result = install_from_zip(
        archive,
        store=store,
        repo_id=42,
        tag="v1.3.0",
        install_dir=install_dir,
        backup_root=tmp_path / "backups",
    )
    assert [d.path for d in result.report.missing] == ["app.exe"]  # syns före installation
    assert (install_dir / "app.exe").read_bytes() == b"ny-binar"


def test_uppdatering_behaller_installsdatum(tmp_path, store: Store):
    seed_install(tmp_path, store, tag="v1.2.0")
    install_dir = store.get_install(42).install_dir
    archive = make_zip(tmp_path / "paket.zip", {"app.exe": b"ny"})
    result = install_from_zip(
        archive,
        store=store,
        repo_id=42,
        tag="v1.3.0",
        install_dir=install_dir,
        backup_root=tmp_path / "backups",
    )
    assert result.record.installed_at == "2026-10-01T00:00:00Z"
    assert result.record.updated_at != "2026-10-01T00:00:00Z"


def test_nedladdning_kraver_https(tmp_path):
    with pytest.raises(RepovaktenError):
        download_asset("http://osäkrad/paket.zip", tmp_path / "x.zip")


def test_backup_install_utan_installation(tmp_path):
    assert backup_install(tmp_path / "finns-inte", tmp_path / "backups", "A/B", "v1") is None


def test_uppdatering_med_rotkatalog_raderar_inte_filer(tmp_path, store: Store):
    """Uppdatering av en release med rotkatalog: bara ändrade filer rapporteras,
    inga filer raderas och den gamla kopian sparas som backup."""
    install_dir = tmp_path / "inst"
    backups = tmp_path / "backups"
    v1 = make_zip(
        tmp_path / "v1.zip",
        {"MyApp-1.0/app.exe": b"gammal", "MyApp-1.0/lib.py": b"lib"},
    )
    r1 = install_from_zip(
        v1,
        store=store,
        repo_id=42,
        tag="v1.0",
        repo_full_name="Tokke2/Appen",
        install_dir=install_dir,
        backup_root=backups,
    )
    v2 = make_zip(
        tmp_path / "v2.zip",
        {"MyApp-1.0/app.exe": b"ny", "MyApp-1.0/lib.py": b"lib", "MyApp-1.0/tillagg.py": b"ny"},
    )
    # Samma jämförelse som GUI:t gör FÖRE installationen.
    report = compare_install(v2, install_dir, manifest_files=r1.record.files)
    assert [d.path for d in report.changed] == ["app.exe"]
    assert [d.path for d in report.new] == ["tillagg.py"]
    assert report.removed == [] and report.missing == []
    assert report.identical_files == 1

    r2 = install_from_zip(
        v2,
        store=store,
        repo_id=42,
        tag="v1.1",
        repo_full_name="Tokke2/Appen",
        install_dir=install_dir,
        backup_root=backups,
    )
    # Ingenting raderades – tvärtom lades en fil till.
    assert (install_dir / "app.exe").read_bytes() == b"ny"
    assert (install_dir / "lib.py").read_bytes() == b"lib"
    assert (install_dir / "tillagg.py").read_bytes() == b"ny"
    assert r2.removed_files == []
    # Den gamla versionen finns kvar som backup.
    assert r2.backup_dir is not None
    assert (r2.backup_dir / "app.exe").read_bytes() == b"gammal"
    assert r2.record.files == {
        "app.exe": sha(b"ny"),
        "lib.py": sha(b"lib"),
        "tillagg.py": sha(b"ny"),
    }


def test_rotkatalog_med_storage_skrivs_inte_over(tmp_path, store: Store):
    """Användardata inne i paketets rotkatalog får aldrig skriva över lagrat innehåll."""
    install_dir = tmp_path / "inst"
    make_tree(install_dir, {"storage/secret.db": b"USERDATA", "gammal.txt": b"ska bort"})
    archive = make_zip(
        tmp_path / "paket.zip",
        {"MyApp-1.0/app.exe": b"bin", "MyApp-1.0/storage/secret.db": b"RELEASE-VERSION"},
    )
    result = install_from_zip(
        archive,
        store=store,
        repo_id=42,
        tag="v1.3.0",
        repo_full_name="Tokke2/Appen",
        install_dir=install_dir,
        backup_root=tmp_path / "backups",
    )
    assert (install_dir / "app.exe").read_bytes() == b"bin"
    assert (install_dir / "storage" / "secret.db").read_bytes() == b"USERDATA"
    assert "storage/secret.db" not in result.record.files
