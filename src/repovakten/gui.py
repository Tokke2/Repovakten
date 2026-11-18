"""Startpunkt för Repovakten GUI: ``python -m repovakten.gui`` eller ``repovakten-gui``."""
from __future__ import annotations

import sys

from . import __version__


def _install_qt_log_handler() -> None:
    """Skicka Qt:s egna meddelanden (varningar/fel) till apploggen med felkod."""
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler

    from . import applog

    def handler(mode, _context, message) -> None:
        text = str(message).strip()
        if mode == QtMsgType.QtWarningMsg:
            applog.warning(applog.QT_VARNING, f"Qt-varning: {text}")
        elif mode in (QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
            applog.error(applog.QT_KRITISK, f"Qt-fel: {text}")
        else:
            applog.info(f"Qt: {text}")

    qInstallMessageHandler(handler)


def main(argv: list[str] | None = None, *, start_minimized: bool = False) -> int:
    from . import applog

    applog.setup()  # egen loggmapp i appmappen – se applog.py

    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print(
            "Repovakten GUI kräver PySide6. Installera med:\n"
            '  pip install "repovakten[gui]"',
            file=sys.stderr,
        )
        return 2

    _install_qt_log_handler()
    from .ui import MainWindow

    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("Repovakten")
    app.setApplicationVersion(__version__)
    window = MainWindow()
    if start_minimized:
        window.showMinimized()  # autostartläge: fönstret startar minimerat
    else:
        window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
