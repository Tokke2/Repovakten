"""Tester för scripts/build_release.py – releasens ZIP måste vara installerbar."""
from __future__ import annotations

import importlib.util
import zipfile
from pathlib import Path

from repovakten.installer import install_from_zip
from repovakten.store import Store

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def load_build_module():
    path = SCRIPTS_DIR / "build_release.py"
    spec = importlib.util.spec_from_file_location("build_release", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_zip_is_installable(tmp_path, store: Store):
    module = load_build_module()
    zip_path = module.build_zip(tmp_path)
    assert zip_path.name.startswith("Repovakten-")
    assert zip_path.name.endswith("-portable.zip")

    result = install_from_zip(
        zip_path,
        store=store,
        repo_id=1,
        tag="v0.0.1",
        repo_full_name="Tokke2/Repovakten",
        install_dir=tmp_path / "install",
        backup_root=tmp_path / "backups",
    )
    install_dir = tmp_path / "install"
    assert (install_dir / "repovakten" / "__init__.py").exists()
    assert (install_dir / "repovakten" / "gui.py").exists()
    assert (install_dir / "Repovakten.bat").exists()
    assert (install_dir / "repovakten.sh").exists()
    # Rotkatalogen strippas – inget dubbelt Repovakten-0.0.1/-lager.
    assert not (install_dir / "Repovakten-0.0.1").exists()
    assert result.record.installed_tag == "v0.0.1"


def test_release_zip_innehaller_endast_aktiva_filer(tmp_path):
    mod = load_build_module()
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
    mod = load_build_module()
    assert "-m repovakten" in mod.BAT
    assert "-m repovakten" in mod.SH
    assert "repovakten.gui" not in mod.BAT + mod.SH


def test_valideringen_krav_aktiva_filer(tmp_path):
    mod = load_build_module()
    zip_path = mod.build_zip(tmp_path)  # inbyggd validate() kraschar vid bortfall
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    root = f"Repovakten-{mod.read_version()}"
    for required in (f"{root}/repovakten/__main__.py", f"{root}/repovakten/applog.py"):
        assert required in names
