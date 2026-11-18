"""Identifiering av operativsystem och arkitektur för val av release-paket."""
from __future__ import annotations

import platform
import sys


def current_os() -> str:
    """``windows``, ``macos``, ``linux`` eller råvärdet för okända plattformar."""
    value = sys.platform.lower()
    if value.startswith(("win32", "cygwin", "msys")):
        return "windows"
    if value == "darwin":
        return "macos"
    if value.startswith("linux"):
        return "linux"
    return value


def current_arch() -> str:
    """Normaliserad arkitektur: ``x86_64``, ``arm64``, ``x86``, ``arm`` eller råvärdet."""
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64", "x64"}:
        return "x86_64"
    if machine in {"aarch64", "arm64"}:
        return "arm64"
    if machine in {"i386", "i486", "i586", "i686", "x86"}:
        return "x86"
    if machine.startswith(("armv7", "armv8")):
        return "arm"
    return machine


def current_platform() -> tuple[str, str]:
    return current_os(), current_arch()
