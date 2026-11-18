"""Svenska status- och tillåtelsetexter – ren logik utan Qt."""
from __future__ import annotations

from ..catalog import InstallStatus

_STATUS_SV: dict[InstallStatus, str] = {
    InstallStatus.READY: "Klar att installeras",
    InstallStatus.BLOCKED: "Spärrad av admin",
    InstallStatus.NO_RELEASE: "Ingen release",
    InstallStatus.NO_STABLE_RELEASE: "Ingen stabil release",
    InstallStatus.NO_INSTALLABLE_ASSET: "Ingen ZIP i releasen",
    InstallStatus.MISSING: "Försvunnen från GitHub",
}


def status_text(status: InstallStatus) -> str:
    return _STATUS_SV.get(status, status.value)


def install_allowed_text(allowed: bool) -> str:
    return "Tillåten" if allowed else "Nej – spärrad"


def row_color(status: InstallStatus) -> str | None:
    """Bakgrundsfärg för statuscellen (None = standard)."""
    if status is InstallStatus.READY:
        return "#d4edda"  # grönt
    if status is InstallStatus.BLOCKED:
        return "#f8d7da"  # rött
    if status is InstallStatus.MISSING:
        return "#e2e3e5"  # grått
    return "#fff3cd"  # gult: finns men går inte att installera just nu
