"""Tester för repovakten.__main__ – den gemensamma startpunkten."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from repovakten import __version__
from repovakten.__main__ import main


def test_version_flagga(capsys):
    assert main(["--version"]) == 0
    assert f"Repovakten {__version__}" in capsys.readouterr().out


def test_enable_och_disable_autostart(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert main(["--enable-autostart"]) == 0
    desktop = tmp_path / "autostart" / "repovakten.desktop"
    assert desktop.exists()
    assert "Autostart på" in capsys.readouterr().out

    assert main(["--disable-autostart"]) == 0
    assert not desktop.exists()
    assert "Autostart av." in capsys.readouterr().out

    assert main(["--disable-autostart"]) == 0
    assert "redan av" in capsys.readouterr().out


def test_filkan_kan_koras_direkt():
    """__main__.py fungerar körningsbar direkt – så gör autostart på alla OS."""
    import repovakten

    entry = Path(repovakten.__file__).resolve().parent / "__main__.py"
    result = subprocess.run(
        [sys.executable, str(entry), "--version"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0
    assert f"Repovakten {__version__}" in result.stdout
