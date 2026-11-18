"""Bygg en portabel ZIP av Repovakten för GitHub-releasen.

ZIP:en innehåller paketet ``repovakten/``, startskript för Windows och
Unix, README och VERSION – allt under en gemensam rotkatalog så att
Repovaktens egen installerare kan packa upp den korrekt (roten strippas
vid installation).

Körs av GitHub Actions vid varje push till branchen för att hålla
releasen v0.0.1 uppdaterad med ny kod. Versionsnumret höjs endast när
användaren säger till.
"""
from __future__ import annotations

import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "repovakten"
DIST = ROOT / "dist"

BAT = """@echo off
rem Starta Repovakten (kräver Python 3.11+ och PySide6).
set PYTHONPATH=%~dp0
python -m repovakten.gui %*
"""

SH = """#!/bin/sh
# Starta Repovakten (kräver Python 3.11+ och PySide6).
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHONPATH="$DIR" exec python3 -m repovakten.gui "$@"
"""


def read_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def build_zip(output_dir: Path) -> Path:
    version = read_version()
    root_name = f"Repovakten-{version}"
    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / f"Repovakten-{version}-portable.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(SRC.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                zf.write(path, f"{root_name}/repovakten/{path.relative_to(SRC)}")
        zf.writestr(f"{root_name}/Repovakten.bat", BAT)
        sh_info = zipfile.ZipInfo(f"{root_name}/repovakten.sh")
        sh_info.external_attr = 0o755 << 16
        zf.writestr(sh_info, SH)
        zf.writestr(f"{root_name}/VERSION", version + "\n")
        zf.writestr(f"{root_name}/README.md", (ROOT / "README.md").read_text(encoding="utf-8"))
    validate(zip_path)
    return zip_path


def validate(zip_path: Path) -> None:
    """Kontrollera att ZIP:en är installerbar av Repovakten själv."""
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    roots = {n.split("/", 1)[0] for n in names if "/" in n}
    assert len(roots) == 1, f"ZIP:en måste ha exakt en rotkatalog, fick {sorted(roots)}"
    root = roots.pop()
    for required in (
        f"{root}/repovakten/__init__.py",
        f"{root}/repovakten/gui.py",
        f"{root}/Repovakten.bat",
        f"{root}/repovakten.sh",
    ):
        assert required in names, f"Saknas i ZIP:en: {required}"


def main() -> None:
    zip_path = build_zip(DIST)
    print(f"Byggde {zip_path} ({zip_path.stat().st_size} byte)")


if __name__ == "__main__":
    main()
