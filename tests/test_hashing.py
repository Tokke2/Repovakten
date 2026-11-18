"""Tester för repovakten.hashing."""
from __future__ import annotations

import hashlib

import pytest

from repovakten.errors import UnsafeArchiveError
from repovakten.hashing import (
    hash_tree,
    hash_zip,
    is_preserved,
    normalize_relpath,
    sha256_file,
)

from conftest import make_tree, make_zip


def test_sha256_file(tmp_path):
    target = tmp_path / "hej.txt"
    target.write_bytes(b"hello world")
    assert sha256_file(target) == hashlib.sha256(b"hello world").hexdigest()


def test_normalize_relpath_normaliserar():
    assert normalize_relpath("./app.py") == "app.py"
    assert normalize_relpath("a//b/c") == "a/b/c"
    assert normalize_relpath("a/./b") == "a/b"
    assert normalize_relpath("a\\b\\c") == "a/b/c"


@pytest.mark.parametrize(
    "bad",
    ["../evil", "a/../../evil", "/abs/path", "C:/evil", "c:\\evil", "..", "", ".", "a\x00b"],
)
def test_normalize_relpath_avvisar_osäkra(bad):
    with pytest.raises(UnsafeArchiveError):
        normalize_relpath(bad)


def test_is_preserved():
    assert is_preserved("storage/db.sqlite", ["storage/"])
    assert is_preserved("storage", ["storage/"])
    assert not is_preserved("storagex/db", ["storage/"])
    assert is_preserved("config.json", ["config.json"])
    assert not is_preserved("config.json.bak", ["config.json"])


def test_hash_tree(tmp_path):
    root = make_tree(
        tmp_path / "app",
        {
            "app.py": b"print('hej')\n",
            "lib/dub.py": b"x = 1\n",
            "storage/hemlighet.db": b"USERDATA",
        },
    )
    result = hash_tree(root, preserved=["storage/"])
    assert set(result) == {"app.py", "lib/dub.py"}
    assert result["app.py"] == hashlib.sha256(b"print('hej')\n").hexdigest()


def test_hash_tree_saknas_katalog(tmp_path):
    with pytest.raises(NotADirectoryError):
        hash_tree(tmp_path / "finns-inte")


def test_hash_zip(tmp_path):
    archive = make_zip(
        tmp_path / "release.zip",
        {
            "app.py": b"print('v1')\n",
            "assets/ikon.png": b"\x89PNGdata",
            "storage/data.db": b"ANVANDARE",
        },
    )
    result = hash_zip(archive, preserved=["storage/"])
    assert set(result) == {"app.py", "assets/ikon.png"}
    assert result["app.py"] == hashlib.sha256(b"print('v1')\n").hexdigest()


def test_hash_zip_normaliserar_punktslash(tmp_path):
    archive = make_zip(tmp_path / "release.zip", {"./app.py": b"data"})
    assert set(hash_zip(archive)) == {"app.py"}


def test_hash_zip_avvisar_dubbletter_efter_normalisering(tmp_path):
    archive = make_zip(tmp_path / "release.zip", {"app.py": b"a", "./app.py": b"b"})
    with pytest.raises(UnsafeArchiveError):
        hash_zip(archive)


def test_hash_zip_avvisar_zip_slip(tmp_path):
    archive = make_zip(tmp_path / "release.zip", {"../../evil.sh": b"rm -rf /"})
    with pytest.raises(UnsafeArchiveError):
        hash_zip(archive)


def test_hash_zip_avvisar_absolut_sokvag(tmp_path):
    archive = make_zip(tmp_path / "release.zip", {"/etc/passwd": b"root"})
    with pytest.raises(UnsafeArchiveError):
        hash_zip(archive)


def test_hash_zip_inte_ett_zip(tmp_path):
    not_zip = tmp_path / "release.zip"
    not_zip.write_bytes("det här är ingen zip-fil".encode())
    with pytest.raises(UnsafeArchiveError):
        hash_zip(not_zip)


def test_hash_zip_taket_pa_antal_filer(tmp_path):
    members = {f"fil-{i}.txt": b"x" for i in range(10)}
    archive = make_zip(tmp_path / "release.zip", members)
    with pytest.raises(UnsafeArchiveError):
        hash_zip(archive, max_members=5)


def test_hash_zip_stripar_gemensam_rot(tmp_path):
    archive = make_zip(
        tmp_path / "release.zip",
        {"MyApp-1.0/app.py": b"a", "MyApp-1.0/lib/b.py": b"b"},
    )
    assert set(hash_zip(archive)) == {"app.py", "lib/b.py"}


def test_hash_zip_rot_med_toppfiler_strippas_inte(tmp_path):
    archive = make_zip(
        tmp_path / "release.zip",
        {"MyApp-1.0/app.py": b"a", "README": b"r"},
    )
    assert set(hash_zip(archive)) == {"MyApp-1.0/app.py", "README"}


def test_hash_zip_bevarad_inne_i_rot_hoppas_over(tmp_path):
    archive = make_zip(
        tmp_path / "release.zip",
        {"MyApp-1.0/app.py": b"a", "MyApp-1.0/storage/db": b"x"},
    )
    assert set(hash_zip(archive, preserved=["storage/"])) == {"app.py"}
