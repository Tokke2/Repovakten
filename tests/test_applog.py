"""Tester för repovakten.applog – loggmapp, felkoder och rotation (Qt-fri)."""
from __future__ import annotations

import logging

import pytest

from repovakten import applog


@pytest.fixture()
def fresh_log(monkeypatch):
    """Nollställ loggkonfigurationen och stäng gamla handlers."""
    logger = logging.getLogger(applog._LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    monkeypatch.setattr(applog, "_configured", None)
    yield
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    monkeypatch.setattr(applog, "_configured", None)


# --------------------------------------------------------------- skrivning

def test_setup_skriver_i_appmappens_loggmapp(tmp_path, fresh_log):
    directory = applog.setup(root=tmp_path)
    assert directory == tmp_path / "logs"
    log_file = directory / "repovakten.log"
    assert log_file.exists()


def test_error_skriver_felkod_och_meddelande(tmp_path, fresh_log):
    applog.setup(root=tmp_path)
    code = applog.error("SYNK-001", "synken strulade")
    assert code == "SYNK-001"
    text = (tmp_path / "logs" / "repovakten.log").read_text(encoding="utf-8")
    assert "[SYNK-001]" in text
    assert "synken strulade" in text
    assert "ERROR" in text


def test_error_med_undantager_skrivare_stacksparet(tmp_path, fresh_log):
    applog.setup(root=tmp_path)
    try:
        raise ValueError("kaboom")
    except ValueError as exc:
        applog.error("INSTALL-002", "installationen föll", exc=exc)
    text = (tmp_path / "logs" / "repovakten.log").read_text(encoding="utf-8")
    assert "installationen föll" in text
    assert "ValueError: kaboom" in text  # tracebacken med


def test_info_utan_felkod_far_platshallare(tmp_path, fresh_log):
    applog.setup(root=tmp_path)
    applog.info("allt väl")
    text = (tmp_path / "logs" / "repovakten.log").read_text(encoding="utf-8")
    assert "allt väl" in text
    assert "[-----]" in text


def test_session_rad_med_version_och_miljo(tmp_path, fresh_log):
    applog.setup(root=tmp_path)
    text = (tmp_path / "logs" / "repovakten.log").read_text(encoding="utf-8")
    assert "Session: Repovakten" in text


def test_setup_ar_idempotent(tmp_path, fresh_log):
    logger = logging.getLogger(applog._LOGGER_NAME)
    base = len(logger.handlers)  # pytest kan ha egna capture-handlers
    first = applog.setup(root=tmp_path)
    assert len(logger.handlers) == base + 2  # fil + konsol
    second = applog.setup(root=tmp_path)
    assert first == second
    assert len(logger.handlers) == base + 2  # inga dubbletter vid nya anrop


# --------------------------------------------------------------- platser

def test_env_overrides_loggplats(monkeypatch, tmp_path, fresh_log):
    monkeypatch.setenv("REPOVAKTEN_LOGS", str(tmp_path / "annan"))
    assert applog.log_dir() == tmp_path / "annan"


def test_fallback_till_hemmet_om_appmappen_ar_skivskyddad(tmp_path, monkeypatch, fresh_log):
    # 'root' är en fil – katalogen går inte att skapa.
    blocker = tmp_path / "fil"
    blocker.write_text("x")
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    directory = applog.setup(root=blocker)
    assert directory == home / ".repovakten" / "logs"
    assert (directory / "repovakten.log").exists()


# --------------------------------------------------------------- felkoder

def test_felkoderna_ar_unika():
    assert len(applog.CODES) == len(set(applog.CODES))
    assert "SYNK-001" in applog.CODES


def test_felkoder_har_ratt_format():
    import re

    for code in applog.CODES:
        assert re.fullmatch(r"[A-ZÅÄÖ]+-\d{3}", code), code
