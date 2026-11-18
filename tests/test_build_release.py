"""Tester för scripts/build_release.py – releasens ZIP måste vara installerbar."""
from __future__ import annotations

import importlib.util
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
    version = (install_dir / "VERSION").read_text(encoding="utf-8").strip()
    assert version
    assert f"Repovakten-{version}-portable.zip" == zip_path.name
    # Rotkatalogen strippas – inget dubbelt Repovakten-0.0.1/-lager.
    assert not (install_dir / "Repovakten-0.0.1").exists()
    assert result.record.installed_tag == "v0.0.1"
