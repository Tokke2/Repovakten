"""Donator-dialogen – öppnas via menyn Hjälp → Stöd projektet.

Layouten följer stod.html: (1) välj belopp (förinställda knappar eller
eget), (2) välj sätt – Swish-QR enligt Swish C-standard, PayPal och
Ko-fi. Swish-numret visas aldrig i klartext; QR-koden innehåller det.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from .. import donation
from ..errors import RepovaktenError

# Tyst zon runt QR-koden (QR-standarden kräver minst 4 moduler).
_QR_QUIET = 4
_QR_SCALE = 6  # pixlar per modul


def _qr_pixmap(matrix: list[list[int]]) -> QPixmap:
    """Rita QR-matrisen till en QPixmap med vit tyst zon."""
    n = len(matrix)
    side = (n + 2 * _QR_QUIET) * _QR_SCALE
    image = QImage(side, side, QImage.Format_RGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("black"))
    for y, row in enumerate(matrix):
        for x, dark in enumerate(row):
            if dark:
                painter.drawRect(
                    (x + _QR_QUIET) * _QR_SCALE,
                    (y + _QR_QUIET) * _QR_SCALE,
                    _QR_SCALE,
                    _QR_SCALE,
                )
    painter.end()
    return QPixmap.fromImage(image)


_CHIP_STYLE = """
QPushButton {
    border: 2px solid #d0d7de; border-radius: 14px;
    padding: 8px 18px; font-weight: 700; background: white;
}
QPushButton:hover { border-color: #bfe8cf; }
QPushButton:checked { background: #27ae60; color: white; border-color: #1e8449; }
"""

_FRAME_STYLE = """
QFrame {
    border: 1px solid #e0e0e0; border-top: 4px solid %s;
    border-radius: 10px; background: white;
}
"""


class DonationDialog(QDialog):
    """Valfri gåva: Swish-QR (C-format), PayPal eller Ko-fi."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Stöd Repovakten")
        self.setMinimumWidth(680)
        self._amount = donation.DEFAULT_AMOUNT
        self._chip_buttons: list[tuple[QPushButton, int]] = []
        self._build_ui()
        self._apply_amount(donation.DEFAULT_AMOUNT)

    # ------------------------------------------------------------- UI-bygge

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        title = QLabel("💚 Stöd Repovakten")
        font = QFont()
        font.setPointSize(16)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)

        intro = QLabel(
            "Repovakten är gratis, utan reklam och öppen källkod. En gåva är helt "
            "frivillig, låser upp ingenting och ändrar ingenting i appen – men hjälper "
            "till med utveckling, test och nya funktioner. Tack! 💚"
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        # 1. Belopp
        step1 = QLabel("1. Välj belopp – eller skriv ett eget")
        step1_font = QFont()
        step1_font.setBold(True)
        step1.setFont(step1_font)
        layout.addWidget(step1)

        amount_row = QHBoxLayout()
        for kr in donation.PRESET_AMOUNTS:
            chip = QPushButton(f"{kr} kr")
            chip.setCheckable(True)
            chip.setStyleSheet(_CHIP_STYLE)
            chip.clicked.connect(lambda _checked=False, v=kr: self._apply_amount(v))
            self._chip_buttons.append((chip, kr))
            amount_row.addWidget(chip)
        amount_row.addWidget(QLabel("Eget:"))
        self._amount_spin = QSpinBox(self)
        self._amount_spin.setRange(1, donation.MAX_AMOUNT)
        self._amount_spin.setSuffix(" kr")
        self._amount_spin.setAccelerated(True)
        self._amount_spin.valueChanged.connect(self._apply_amount)
        amount_row.addWidget(self._amount_spin)
        amount_row.addStretch(1)
        layout.addLayout(amount_row)

        self._info_label = QLabel()
        layout.addWidget(self._info_label)

        # 2. Sätt
        step2 = QLabel("2. Välj sätt – skanna QR-koden eller klicka på knappen")
        step2.setFont(step1_font)
        layout.addWidget(step2)

        methods = QHBoxLayout()

        # Swish med QR
        swish_frame = QFrame()
        swish_frame.setStyleSheet(_FRAME_STYLE % "#00b06c")
        swish_layout = QVBoxLayout(swish_frame)
        swish_title = QLabel("💚 Swish")
        swish_title.setFont(step1_font)
        swish_layout.addWidget(swish_title, alignment=Qt.AlignHCenter)
        self._qr_label = QLabel()
        self._qr_label.setAlignment(Qt.AlignHCenter)
        self._qr_label.setMinimumHeight(200)
        swish_layout.addWidget(self._qr_label)
        swish_note = QLabel(
            "Skanna med Swish-appen – beloppet är\n"
            "förifyllt men kan ändras.\n"
            "Numret visas aldrig i klartext."
        )
        swish_note.setAlignment(Qt.AlignHCenter)
        swish_note.setWordWrap(True)
        swish_layout.addWidget(swish_note)
        methods.addWidget(swish_frame, stretch=1)

        # PayPal
        paypal_frame = QFrame()
        paypal_frame.setStyleSheet(_FRAME_STYLE % "#0070BA")
        paypal_layout = QVBoxLayout(paypal_frame)
        paypal_title = QLabel("💙 PayPal")
        paypal_title.setFont(step1_font)
        paypal_layout.addWidget(paypal_title, alignment=Qt.AlignHCenter)
        paypal_note = QLabel("Öppnar paypal.me i webbläsaren\nmed valt belopp.")
        paypal_note.setAlignment(Qt.AlignHCenter)
        paypal_note.setWordWrap(True)
        paypal_layout.addWidget(paypal_note)
        paypal_layout.addStretch(1)
        self._paypal_button = QPushButton()
        self._paypal_button.setStyleSheet(
            "QPushButton { background: #0070BA; color: white; font-weight: 700;"
            " border: none; border-radius: 10px; padding: 10px 16px; }"
            "QPushButton:hover { background: #1a8ad6; }"
        )
        self._paypal_button.clicked.connect(self._open_paypal)
        paypal_layout.addWidget(self._paypal_button)
        methods.addWidget(paypal_frame, stretch=1)

        # Ko-fi
        kofi_frame = QFrame()
        kofi_frame.setStyleSheet(_FRAME_STYLE % "#FF5E5B")
        kofi_layout = QVBoxLayout(kofi_frame)
        kofi_title = QLabel("☕ Ko-fi")
        kofi_title.setFont(step1_font)
        kofi_layout.addWidget(kofi_title, alignment=Qt.AlignHCenter)
        kofi_note = QLabel("Engångs- eller månadsstöd –\nvälj belopp på Ko-fi.")
        kofi_note.setAlignment(Qt.AlignHCenter)
        kofi_note.setWordWrap(True)
        kofi_layout.addWidget(kofi_note)
        kofi_layout.addStretch(1)
        kofi_button = QPushButton("Öppna Ko-fi")
        kofi_button.setStyleSheet(
            "QPushButton { background: #FF5E5B; color: white; font-weight: 700;"
            " border: none; border-radius: 10px; padding: 10px 16px; }"
            "QPushButton:hover { background: #ff7572; }"
        )
        kofi_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(donation.KOFI_URL))
        )
        kofi_layout.addWidget(kofi_button)
        methods.addWidget(kofi_frame, stretch=1)

        layout.addLayout(methods)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        close_button = QPushButton("Stäng")
        close_button.setDefault(True)
        close_button.clicked.connect(self.accept)
        bottom.addWidget(close_button)
        layout.addLayout(bottom)

    # ------------------------------------------------------------- logik

    def _apply_amount(self, value: int) -> None:
        """Uppdatera valt belopp, QR-kod och knapptexter."""
        self._amount = donation.normalize_amount(value)
        if self._amount_spin.value() != self._amount:
            self._amount_spin.blockSignals(True)
            self._amount_spin.setValue(self._amount)
            self._amount_spin.blockSignals(False)
        for chip, kr in self._chip_buttons:
            chip.setChecked(kr == self._amount)
        self._info_label.setText(f"Valt: {self._amount} kr – tack! 💚")
        self._paypal_button.setText(f"PayPal – {self._amount} kr")
        self._refresh_qr()

    def _refresh_qr(self) -> None:
        try:
            matrix = donation.qr_matrix(self._amount)
        except RepovaktenError as exc:
            self._qr_label.setPixmap(QPixmap())
            self._qr_label.setText(f"QR-koden kunde inte ritas.\n{exc}")
            return
        self._qr_label.setText("")
        self._qr_label.setPixmap(_qr_pixmap(matrix))

    def _open_paypal(self) -> None:
        QDesktopServices.openUrl(QUrl(donation.paypal_url(self._amount)))
