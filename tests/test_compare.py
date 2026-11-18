"""Tester för repovakten.compare – SHA-256-filjämförelsen."""
from __future__ import annotations

import hashlib

from repovakten.compare import (
    DifferenceKind,
    compare_files,
    compare_install,
)

from conftest import make_tree, make_zip


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_identiska_traer_ger_inga_andringar():
    files = {"app.py": sha(b"a"), "lib/x.py": sha(b"b")}
    report = compare_files(files, dict(files))
    assert report.ok
    assert report.identical_files == 2
    assert report.differences == []


def test_andrad_fil_visar_vilken_fil():
    release = {"app.py": sha(b"ny-version"), "lib/x.py": sha(b"samma")}
    local = {"app.py": sha(b"gammal-version"), "lib/x.py": sha(b"samma")}
    report = compare_files(release, local)
    assert [d.path for d in report.changed] == ["app.py"]
    diff = report.changed[0]
    assert diff.kind is DifferenceKind.CHANGED
    assert diff.release_sha256 == sha(b"ny-version")
    assert diff.local_sha256 == sha(b"gammal-version")
    assert report.identical_files == 1


def test_nya_och_utgaende_filer():
    release = {"app.py": sha(b"a"), "ny-modul.py": sha(b"ny")}
    local = {"app.py": sha(b"a"), "gammal-modul.py": sha(b"gammal")}
    report = compare_files(release, local)
    assert [d.path for d in report.new] == ["ny-modul.py"]
    assert [d.path for d in report.removed] == ["gammal-modul.py"]


def test_saknad_fil_upptacks_via_manifest():
    release = {"app.py": sha(b"a")}
    local = {"app.py": sha(b"a")}
    manifest = {"app.py": sha(b"a"), "borta.txt": sha(b"borta")}
    report = compare_files(release, local, manifest_files=manifest)
    missing = [d.path for d in report.missing]
    assert missing == ["borta.txt"]


def test_saknad_vinner_over_ny_nar_manifestet_forvantar_filen():
    # Filen förväntas enligt manifestet, finns inte på disk men i releasen:
    # rapportera som saknad (installationen är skadad), inte som ny.
    release = {"app.py": sha(b"a")}
    local: dict[str, str] = {}
    manifest = {"app.py": sha(b"a")}
    report = compare_files(release, local, manifest_files=manifest)
    assert [d.path for d in report.missing] == ["app.py"]
    assert report.new == []


def test_bevarade_sokvagar_rors_aldrig():
    release = {"app.py": sha(b"a")}
    local = {"app.py": sha(b"a"), "storage/data.db": sha(("användardata".encode()))}
    report = compare_files(release, local, preserved=["storage/"])
    assert report.ok
    assert all(not d.path.startswith("storage/") for d in report.differences)


def test_bevarad_fil_i_releasen_ignoreras_ocksa():
    release = {"app.py": sha(b"a"), "storage/data.db": sha(b"release-version")}
    local = {"app.py": sha(b"a"), "storage/data.db": sha(("användardata".encode()))}
    report = compare_files(release, local, preserved=["storage/"])
    assert report.ok


def test_format_swedish_innehaller_filnamn():
    release = {"app.py": sha(b"ny")}
    local = {"app.py": sha(b"gammal")}
    text = compare_files(release, local).format_swedish()
    assert "app.py" in text
    assert "Ändrade filer" in text


def test_compare_install_med_riktiga_filer(tmp_path):
    archive = make_zip(
        tmp_path / "release.zip",
        {"app.py": b"print('ny')\n", "ny.txt": b"ny fil"},
    )
    install_dir = make_tree(
        tmp_path / "install",
        {"app.py": b"print('gammal')\n", "utgaende.txt": b"ska bort", "storage/data.db": b"DATA"},
    )
    report = compare_install(archive, install_dir, preserved=["storage/"])
    assert [d.path for d in report.changed] == ["app.py"]
    assert [d.path for d in report.new] == ["ny.txt"]
    assert [d.path for d in report.removed] == ["utgaende.txt"]
    assert report.has_changes


def test_compare_install_utan_installation(tmp_path):
    archive = make_zip(tmp_path / "release.zip", {"app.py": b"a", "lib.py": b"b"})
    report = compare_install(archive, tmp_path / "finns-inte")
    assert sorted(d.path for d in report.new) == ["app.py", "lib.py"]


def test_samma_version_men_olika_fil_upptacks(tmp_path):
    """Krav 5: båda v1.2.0, men en fil skiljer – det ska synas vilken."""
    innehall = b"exakt samma bytes, nej inte nu"
    release_innehall = innehall + b"!!!"
    archive = make_zip(tmp_path / "v1.2.0.zip", {"Lager.exe": release_innehall, "README.txt": b"samma"})
    install_dir = make_tree(
        tmp_path / "Lager",
        {"Lager.exe": innehall, "README.txt": b"samma"},
    )
    manifest = {"Lager.exe": sha(innehall), "README.txt": sha(b"samma")}
    report = compare_install(archive, install_dir, manifest_files=manifest)
    assert [d.path for d in report.changed] == ["Lager.exe"]
    assert "Lager.exe" in report.format_swedish()
