"""Tester för repovakten.autostart – multi-OS-autostart (Qt-fri)."""
from __future__ import annotations

import plistlib

import pytest

from repovakten import autostart
from repovakten.errors import RepovaktenError


@pytest.fixture()
def fake_python(monkeypatch):
    monkeypatch.setattr(autostart, "python_executable", lambda: "/usr/bin/python3")


# --------------------------------------------------------------- linux

def test_linux_enable_skriver_desktop_fil(tmp_path, monkeypatch, fake_python):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    where = autostart.enable(platform="linux", home=tmp_path)
    path = tmp_path / "cfg" / "autostart" / "repovakten.desktop"
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "[Desktop Entry]" in text
    assert "Type=Application" in text
    assert "/usr/bin/python3" in text
    assert "__main__.py" in text and "--autostart" in text
    assert autostart.is_enabled(platform="linux", home=tmp_path)
    assert str(path) in where
    assert autostart.disable(platform="linux", home=tmp_path) is True
    assert not path.exists()
    assert autostart.disable(platform="linux", home=tmp_path) is False


def test_linux_utan_xdg_agerar_hemkatalogen(tmp_path, monkeypatch, fake_python):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    autostart.enable(platform="linux", home=tmp_path)
    assert (tmp_path / ".config" / "autostart" / "repovakten.desktop").exists()


# --------------------------------------------------------------- macos

def test_macos_enable_skriver_plist(tmp_path, fake_python):
    autostart.enable(platform="macos", home=tmp_path)
    path = tmp_path / "Library" / "LaunchAgents" / "se.repovakten.autostart.plist"
    assert path.exists()
    data = plistlib.loads(path.read_bytes())
    assert data["Label"] == "se.repovakten.autostart"
    assert data["RunAtLoad"] is True
    assert data["ProgramArguments"][0] == "/usr/bin/python3"
    assert data["ProgramArguments"][-1] == "--autostart"
    assert autostart.is_enabled(platform="macos", home=tmp_path)
    assert autostart.disable(platform="macos", home=tmp_path) is True
    assert not autostart.is_enabled(platform="macos", home=tmp_path)


# --------------------------------------------------------------- windows

@pytest.fixture()
def fake_registry(monkeypatch):
    store: dict[str, str] = {}
    monkeypatch.setattr(autostart, "_win_read", lambda: store.get("Repovakten"))
    monkeypatch.setattr(autostart, "_win_write", lambda value: store.__setitem__("Repovakten", value))
    monkeypatch.setattr(autostart, "_win_delete", lambda: store.pop("Repovakten"))
    return store


def test_windows_enable_skriver_run_varde(tmp_path, fake_python, fake_registry):
    where = autostart.enable(platform="windows", home=tmp_path)
    value = fake_registry["Repovakten"]
    assert value == autostart._windows_command(autostart.command_argv())
    assert "--autostart" in value
    assert autostart.is_enabled(platform="windows", home=tmp_path)
    assert autostart.disable(platform="windows", home=tmp_path) is True
    assert not autostart.is_enabled(platform="windows", home=tmp_path)
    assert autostart.disable(platform="windows", home=tmp_path) is False
    assert "registret" in where


def test_windows_citerar_sokvagar_med_mellanslag(tmp_path, fake_python, monkeypatch):
    monkeypatch.setattr(autostart, "command_argv", lambda: ["C:\\Python 3\\pythonw.exe", "C:\\Min App\\__main__.py", "--autostart"])
    value = autostart._windows_command(autostart.command_argv())
    assert value == '"C:\\Python 3\\pythonw.exe" "C:\\Min App\\__main__.py" --autostart'


# --------------------------------------------------------------- allmänt

def test_okant_plattform_felar(tmp_path):
    with pytest.raises(RepovaktenError):
        autostart.enable(platform="plan9", home=tmp_path)


def test_enable_felar_snyggt_vid_skrivfel(tmp_path, fake_python):
    # 'home' är en fil – katalogskapandet måste falla och ge RepovaktenError.
    blocker = tmp_path / "fil"
    blocker.write_text("x")
    with pytest.raises(RepovaktenError):
        autostart.enable(platform="macos", home=blocker)


def test_pythonw_anvands_pa_windows(tmp_path, monkeypatch):
    python = tmp_path / "python.exe"
    pythonw = tmp_path / "pythonw.exe"
    python.write_bytes(b"")
    pythonw.write_bytes(b"")
    monkeypatch.setattr(autostart, "current_os", lambda: "windows")
    monkeypatch.setattr(autostart.sys, "executable", str(python))
    assert autostart.python_executable() == str(pythonw)


def test_command_argv_pekar_pa_main_och_autostartlage(fake_python):
    argv = autostart.command_argv()
    assert argv[0] == "/usr/bin/python3"
    assert argv[1].endswith("__main__.py")
    assert argv[2] == "--autostart"
