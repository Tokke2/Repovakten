"""Startpunkt för Repovakten GUI: ``python -m repovakten.gui`` eller ``repovakten-gui``."""
from __future__ import annotations

import sys

from . import __version__


def main(argv: list[str] | None = None) -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print(
            "Repovakten GUI kräver PySide6. Installera med:\n"
            "  pip install \"repovakten[gui]\"",
            file=sys.stderr,
        )
        return 2

    from .ui import MainWindow

    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("Repovakten")
    app.setApplicationVersion(__version__)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
