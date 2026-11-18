"""Avancerad loggning med felkoder för Repovakten.

Loggen ligger i en egen mapp i appmappen: ``<appmapp>/logs/repovakten.log``
(roteras, 4 × 1 MB). Varje fel får en stabil **felkod** (t.ex. ``SYNK-001``)
som både skrivs till loggen och visas för användaren – då går fel att
rapportera exakt, utan att känna till tekniska detaljer.

Modulen är Qt-fri och kraschar aldrig appen: om appmappen inte går att
skriva i används ``~/.repovakten/logs`` i stället. Sessionen börjar med en
rad med version och miljö.
"""
from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# ------------------------------------------------------------ felkoder
# Stabila strängar – citeras i felrapporter och finns kvar mellan versioner.

SYNK_FEL = "SYNK-001"                  # synk mot GitHub misslyckades
INSTALL_FORBEREDELSE_FEL = "INSTALL-001"  # paketet kunde inte hämtas/jämföras
INSTALL_FEL = "INSTALL-002"            # installationen misslyckades (återställd)
INSTALL_SPARRAD = "INSTALL-003"        # appen är spärrad av admin
UPPDATERA_SOK_FEL = "UPPDATERA-001"    # kunde inte söka uppdatering
UPPDATERA_FEL = "UPPDATERA-002"        # självuppdateringen misslyckades
AUTOSTART_FEL = "AUTOSTART-001"        # autostart kunde inte ställas in
LAGRING_FEL = "LAGRING-001"            # state.json kunde inte läsas/skrivas
DONATION_FEL = "DONATION-001"          # donationsdialogen kunde inte visas
QT_VARNING = "QT-001"                  # varning från Qt-ramverket
QT_KRITISK = "QT-002"                  # kritiskt Qt-fel
ALLMANT_FEL = "ALLMANT-001"            # övriga fel

#: Alla felkoder – testar att de är unika och finns med i dokumentationen.
CODES = (
    SYNK_FEL,
    INSTALL_FORBEREDELSE_FEL,
    INSTALL_FEL,
    INSTALL_SPARRAD,
    UPPDATERA_SOK_FEL,
    UPPDATERA_FEL,
    AUTOSTART_FEL,
    LAGRING_FEL,
    DONATION_FEL,
    QT_VARNING,
    QT_KRITISK,
    ALLMANT_FEL,
)

# ------------------------------------------------------------ konfiguration

LOG_FILENAME = "repovakten.log"
_LOGGER_NAME = "repovakten"
_MAX_BYTES = 1_000_000
_BACKUP_COUNT = 3
_configured: Path | None = None


class _CodeFilter(logging.Filter):
    """Se till att varje post har ett ``code``-fält för formatsträngen."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "code"):
            record.code = "-----"
        return True


def app_root() -> Path:
    """Appmappen – katalogen som innehåller ``repovakten``-paketet."""
    import repovakten

    return Path(repovakten.__file__).resolve().parent.parent


def log_dir(root: Path | None = None) -> Path:
    """Loggmappen – en undermapp till appmappen.

    ``REPOVAKTEN_LOGS`` åsidosätter läget (tester och CI skriver aldrig i
    den riktiga appmappen).
    """
    if root is not None:
        return Path(root) / "logs"
    override = os.environ.get("REPOVAKTEN_LOGS")
    if override:
        return Path(override)
    return app_root() / "logs"


def setup(*, root: Path | None = None, level: int = logging.INFO) -> Path:
    """Konfigurera loggningen (idempotent). Returnerar loggmappen."""
    global _configured
    if _configured is not None:
        return _configured

    logger = logging.getLogger(_LOGGER_NAME)
    directory = log_dir(root)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".write-test"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
    except OSError:
        # Appmappen skrivskyddad – logga i hemmet i stället, aldrig krascha.
        directory = Path.home() / ".repovakten" / "logs"
        directory.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-7s [%(code)s] %(name)s: %(message)s"
    )
    code_filter = _CodeFilter()

    file_handler = RotatingFileHandler(
        directory / LOG_FILENAME,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(code_filter)
    logger.addHandler(file_handler)

    # Varningar och värre syns även i konsolen.
    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    console.setFormatter(formatter)
    console.addFilter(code_filter)
    logger.addHandler(console)

    logger.setLevel(level)
    logger.propagate = False
    _configured = directory
    session()
    return directory


def session() -> None:
    """Skriv en sessionsrad med version och miljö i början av varje körning."""
    try:
        from . import __version__
        from .platforminfo import current_arch, current_os

        info(
            f"Session: Repovakten {__version__} "
            f"({current_os()} {current_arch()}, Python {sys.version.split()[0]})"
        )
    except Exception:  # loggning ska aldrig krascha appen
        pass


# ------------------------------------------------------------ skrivning


def _logger() -> logging.Logger:
    if _configured is None:
        setup()
    return logging.getLogger(_LOGGER_NAME)


def error(code: str, message: str, *, exc: BaseException | None = None) -> str:
    """Logga ett fel med felkod och eventuellt undantag. Returnerar koden."""
    _logger().error("%s", message, extra={"code": code}, exc_info=exc)
    return code


def warning(code: str, message: str) -> str:
    """Logga en varning med felkod. Returnerar koden."""
    _logger().warning("%s", message, extra={"code": code})
    return code


def info(message: str) -> None:
    """Logga en händelse (ingen felkod)."""
    _logger().info("%s", message)
