"""Ikoner utan bildfiler – Qt:s standardikoner följer tema och plattform.

Varje semantiskt namn pekar på ett QStyle-standardikon, så färg och stil
följer operativsystemet och det aktiva temat automatiskt. Appens fönsterikon
målas i kod (sköld i accentfärg).
"""
from __future__ import annotations

from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtWidgets import QStyle

_STANDARD = {
    "synka": QStyle.StandardPixmap.SP_BrowserReload,
    "uppdatera": QStyle.StandardPixmap.SP_BrowserReload,
    "installera": QStyle.StandardPixmap.SP_ArrowDown,
    "sparra": QStyle.StandardPixmap.SP_BrowserStop,
    "github": QStyle.StandardPixmap.SP_DialogOpenButton,
    "konto_nytt": QStyle.StandardPixmap.SP_FileDialogNewFolder,
    "konto_bort": QStyle.StandardPixmap.SP_TrashIcon,
    "mapp": QStyle.StandardPixmap.SP_DirOpenIcon,
    "sok": QStyle.StandardPixmap.SP_FileDialogContentsView,
    "dator": QStyle.StandardPixmap.SP_ComputerIcon,
    "avsluta": QStyle.StandardPixmap.SP_DialogCloseButton,
    "hjalp": QStyle.StandardPixmap.SP_DialogHelpButton,
    "info": QStyle.StandardPixmap.SP_MessageBoxInformation,
}


def icon(widget, name: str) -> QIcon:
    """Standardikon för det semantiska namnet, anpassad efter widgetens stil."""
    pixmap = _STANDARD.get(name)
    if pixmap is None:
        return QIcon()
    return widget.style().standardIcon(pixmap)


def app_icon() -> QIcon:
    """Fönsterikonen: rundad ruta i accentfärg med vit sköld/check."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Bakgrund: rundad ruta i accentfärg.
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#4c8dff"))
    painter.drawRoundedRect(QRectF(2, 2, 60, 60), 14, 14)

    # Sköld: vit kontur med avrundad botten.
    shield = QPainterPath()
    shield.moveTo(32, 12)
    shield.lineTo(50, 19)
    shield.lineTo(50, 33)
    shield.cubicTo(50, 44, 42, 51, 32, 55)
    shield.cubicTo(22, 51, 14, 44, 14, 33)
    shield.lineTo(14, 19)
    shield.closeSubpath()
    painter.setPen(QPen(QColor("#ffffff"), 3))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(shield)

    # Check-mark i skölden.
    pen = QPen(QColor("#ffffff"), 4.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.drawLine(QPointF(23, 33), QPointF(30, 40))
    painter.drawLine(QPointF(30, 40), QPointF(42, 25))

    painter.end()
    return QIcon(pixmap)
