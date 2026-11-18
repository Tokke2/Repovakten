"""Tester för release-bygget – ZIP:en ska bara innehålla aktiva filer."""
from __future__ import annotations

import importlib.util
import zipfile
from pathlib import Path


def _load_build():
    path = Path(__file__).resolve().parent.parent / "scripts" / "build_release.py"
    spec = importlib.util.spec_from_file_location("build_release", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_zip_innehaller_endast_aktiva_filer(tmp_path):
    mod = _load_build()
    zip_path = mod.build_zip(tmp_path)
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())

    root = f"Repovakten-{mod.read_version()}"
    expected = {f"{root}/Repovakten.bat", f"{root}/repovakten.sh"}
    for path in mod.active_package_files():
        expected.add(f"{root}/repovakten/{path.relative_to(mod.SRC)}")
    assert names == expected

    # Inaktiva filer får aldrig smyga sig med i releasen.
    for inactive in ("README.md", "VERSION", "py.typed", "__pycache__", ".log"):
        assert not any(inactive in name for name in names), inactive


def test_startskripten_startar_gemensam_main():
    mod = _load_build()
    assert "-m repovakten" in mod.BAT
    assert "-m repovakten" in mod.SH
    assert "repovakten.gui" not in mod.BAT + mod.SH


def test_valideringen_krav_aktiva_filer(tmp_path):
    mod = _load_build()
    zip_path = mod.build_zip(tmp_path)  # inbyggd validate() kraschar vid bortfall
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    root = f"Repovakten-{mod.read_version()}"
    for required in (f"{root}/repovakten/__main__.py", f"{root}/repovakten/applog.py"):
        assert required in names
