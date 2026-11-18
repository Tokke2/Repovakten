"""Qt-gränssnittet för Repovakten (PySide6).

``MainWindow`` laddas lat så att Qt-fria hjälpfunktioner (t.ex.
:mod:`repovakten.ui.status`) kan importeras och testas utan Qt installerat.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # endast för typkontroll, ingen körtidskostnad
    from .main_window import MainWindow

__all__ = ["MainWindow"]


def __getattr__(name: str):
    if name == "MainWindow":
        from .main_window import MainWindow

        return MainWindow
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
