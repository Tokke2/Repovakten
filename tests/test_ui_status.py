"""Tester för repovakten.ui.status – svenska texter utan Qt."""
from repovakten.catalog import InstallStatus
from repovakten.ui.status import install_allowed_text, row_color, status_text


def test_status_text_svenska_for_alla_statusar():
    expected = {
        InstallStatus.READY: "Klar att installeras",
        InstallStatus.BLOCKED: "Spärrad av admin",
        InstallStatus.NO_RELEASE: "Ingen release",
        InstallStatus.NO_STABLE_RELEASE: "Ingen stabil release",
        InstallStatus.NO_INSTALLABLE_ASSET: "Ingen ZIP i releasen",
        InstallStatus.MISSING: "Försvunnen från GitHub",
    }
    for status, text in expected.items():
        assert status_text(status) == text


def test_install_allowed_text():
    assert install_allowed_text(True) == "Tillåten"
    assert install_allowed_text(False) == "Nej – spärrad"


def test_row_color():
    assert row_color(InstallStatus.READY) == "#d4edda"
    assert row_color(InstallStatus.BLOCKED) == "#f8d7da"
    assert row_color(InstallStatus.MISSING) == "#e2e3e5"
    assert row_color(InstallStatus.NO_RELEASE) == "#fff3cd"
