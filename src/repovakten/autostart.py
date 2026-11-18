"""Autostart – starta Repovakten automatiskt vid inloggning, på alla OS.

* **Windows**: registret ``HKCU\\...\\Run`` (via ``winreg``).
* **macOS**: LaunchAgent i ``~/Library/LaunchAgents``.
* **Linux**: XDG-autostart (``$XDG_CONFIG_HOME/autostart`` eller
  ``~/.config/autostart``).

Kommandot som registreras startar den körande Python-tolken med
``repovakten/__main__.py --autostart`` (appen startar minimerat) –
samma fil funkar från både pip-installation och portabel ZIP, på alla
operativsystem, utan miljövariabler. Registreringen gäller från nästa
inloggning.
"""
from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path

from .errors import RepovaktenError
from .platforminfo import current_os

APP_NAME = "Repovakten"
PLIST_LABEL = "se.repovakten.autostart"
DESKTOP_FILE = "repovakten.desktop"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def python_executable() -> str:
    """Python-tolken som startar appen – ``pythonw`` på Windows utan konsol."""
    exe = sys.executable or "python3"
    if current_os() == "windows":
        candidate = Path(exe).with_name("pythonw.exe")
        if candidate.exists():
            exe = str(candidate)
    return exe


def command_argv() -> list[str]:
    """Kommandoargumenten som registreras: [python, __main__.py, --autostart]."""
    import repovakten

    entry = Path(repovakten.__file__).resolve().parent / "__main__.py"
    return [python_executable(), str(entry), "--autostart"]


# --------------------------------------------------------------- platser

def _desktop_path(home: Path, environ) -> Path:
    base = Path(environ.get("XDG_CONFIG_HOME") or (home / ".config"))
    return base / "autostart" / DESKTOP_FILE


def _plist_path(home: Path) -> Path:
    return home / "Library" / "LaunchAgents" / f"{PLIST_LABEL}.plist"


# --------------------------------------------------------------- windows

def _win_read() -> str | None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            return str(value)
    except OSError:
        return None


def _win_write(value: str) -> None:
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, value)


def _win_delete() -> None:
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.DeleteValue(key, APP_NAME)


# --------------------------------------------------------------- format

def _windows_command(argv: list[str]) -> str:
    return " ".join(f'"{arg}"' if " " in arg or not arg else arg for arg in argv)


def _linux_command(argv: list[str]) -> str:
    return " ".join(shlex.quote(arg) for arg in argv)


def _desktop_entry(argv: list[str]) -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        "Comment=Installationshanterare för GitHub-appar\n"
        f"Exec={_linux_command(argv)}\n"
        "X-GNOME-Autostart-enabled=true\n"
    )


def _plist_bytes(argv: list[str]) -> bytes:
    import plistlib

    return plistlib.dumps(
        {
            "Label": PLIST_LABEL,
            "ProgramArguments": argv,
            "RunAtLoad": True,
        }
    )


# --------------------------------------------------------------- API

def _platform(platform: str | None) -> str:
    return platform or current_os()


def enable(*, platform: str | None = None, home: Path | None = None) -> str:
    """Registrera autostart och returnera en beskrivning av var det ligger."""
    name = _platform(platform)
    home = Path(home) if home else Path.home()
    argv = command_argv()
    try:
        if name == "windows":
            _win_write(_windows_command(argv))
            return f"Autostart på (registret, {APP_NAME})"
        if name == "macos":
            path = _plist_path(home)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(_plist_bytes(argv))
            return f"Autostart på ({path})"
        if name == "linux":
            path = _desktop_path(home, os.environ)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_desktop_entry(argv), encoding="utf-8")
            return f"Autostart på ({path})"
        raise RepovaktenError(f"Autostart stöds inte på {name!r}.")
    except OSError as exc:
        raise RepovaktenError(f"Kunde inte ställa in autostart: {exc}") from exc


def disable(*, platform: str | None = None, home: Path | None = None) -> bool:
    """Avregistrera autostart. Returnerar True om något faktiskt togs bort."""
    name = _platform(platform)
    home = Path(home) if home else Path.home()
    try:
        if name == "windows":
            if _win_read() is None:
                return False
            _win_delete()
            return True
        if name == "macos":
            path = _plist_path(home)
        elif name == "linux":
            path = _desktop_path(home, os.environ)
        else:
            raise RepovaktenError(f"Autostart stöds inte på {name!r}.")
        if not path.exists():
            return False
        path.unlink()
        return True
    except OSError as exc:
        raise RepovaktenError(f"Kunde inte stänga av autostart: {exc}") from exc


def is_enabled(*, platform: str | None = None, home: Path | None = None) -> bool:
    """Sant om autostart är registrerat."""
    name = _platform(platform)
    home = Path(home) if home else Path.home()
    if name == "windows":
        return _win_read() is not None
    if name == "macos":
        return _plist_path(home).exists()
    if name == "linux":
        return _desktop_path(home, os.environ).exists()
    return False
