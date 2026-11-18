"""Dialoger för Repovakten (svenska)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QVBoxLayout,
)

from ..catalog import CatalogRow
from ..compare import FileReport
from ..releases import AssetSuggestion, describe_asset


class AssetPickerDialog(QDialog):
    """Flera ZIP-paket finns i releasen – användaren väljer det för sin dator."""

    def __init__(self, parent, suggestions: list[AssetSuggestion], tag: str) -> None:
        super().__init__(parent)
        self.setWindowTitle("Välj paket")
        self._suggestions = suggestions

        layout = QVBoxLayout(self)
        label = QLabel(
            f"Releasen <b>{tag}</b> innehåller flera paket.\n"
            "Välj det som passar din dator – paketen är rangordnade efter din plattform:"
        )
        label.setWordWrap(True)
        layout.addWidget(label)

        self._list = QListWidget(self)
        for suggestion in suggestions:
            reasons = " · ".join(suggestion.reasons)
            item = QListWidgetItem(f"{describe_asset(suggestion.asset)}\n    {reasons}")
            item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self._list.addItem(item)
        self._list.setCurrentRow(0)  # redan rangordnad, bästa förslaget först
        layout.addWidget(self._list)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok, self)
        buttons.button(QDialogButtonBox.Ok).setText("Använd det här paketet")
        buttons.button(QDialogButtonBox.Cancel).setText("Avbryt")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(560, 320)

    def chosen(self) -> AssetSuggestion | None:
        row = self._list.currentRow()
        if row < 0:
            return None
        return self._suggestions[row]

    @staticmethod
    def choose(parent, suggestions: list[AssetSuggestion], tag: str) -> AssetSuggestion | None:
        dialog = AssetPickerDialog(parent, suggestions, tag)
        if dialog.exec() == QDialog.Accepted:
            return dialog.chosen()
        return None


class FileReportDialog(QDialog):
    """Filrapporten – visas INNAN något ändras. Inget installeras om den stängs."""

    def __init__(self, parent, *, title: str, tag: str, report: FileReport, is_update: bool) -> None:
        super().__init__(parent)
        self.setWindowTitle("Filrapport")
        self._do_install = False

        layout = QVBoxLayout(self)
        header = QLabel(f"<b>{title}</b> – rapporten visar exakt vad som ändras mot din dator:")
        header.setWordWrap(True)
        layout.addWidget(header)

        view = QPlainTextEdit(self)
        view.setReadOnly(True)
        view.setPlainText(report.format_swedish())
        view.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addWidget(view)

        note = QLabel(
            "Inget ändras förrän du trycker på knappen nedan. "
            "Den tidigare kopian sparas som backup och <code>storage/</code> bevaras alltid.\n"
            "Nedladdade program körs aldrig automatiskt."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QDialogButtonBox(self)
        close_button = buttons.addButton("Stäng (installera inte)", QDialogButtonBox.RejectRole)
        action_label = f"Uppdatera till {tag}" if is_update else f"Installera {tag}"
        install_button = buttons.addButton(action_label, QDialogButtonBox.AcceptRole)
        install_button.setDefault(True)
        buttons.accepted.connect(self._accept_install)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._install_button = install_button
        self._close_button = close_button
        self.resize(640, 480)

    def _accept_install(self) -> None:
        self._do_install = True
        self.accept()

    def install_requested(self) -> bool:
        return self._do_install


class AppUpdatesDialog(QDialog):
    """Installerade appar med nyare stabil release – välj vilken som uppdateras."""

    def __init__(self, parent, rows: list[CatalogRow]) -> None:
        super().__init__(parent)
        self.setWindowTitle("Uppdateringar finns")
        self._rows = rows
        self._chosen: CatalogRow | None = None

        layout = QVBoxLayout(self)
        header = QLabel(
            "<b>Dina installerade appar har nyare stabila releaser.</b><br>"
            "Välj en app att uppdatera – filrapporten visas före varje ändring "
            "och den gamla kopian sparas som backup."
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        self._list = QListWidget(self)
        for row in rows:
            item = QListWidgetItem(
                f"{row.repo.full_name}\n"
                f"    installerad {row.installed_version} → senaste stabila "
                f"{row.latest_stable_tag}"
            )
            item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self._list.addItem(item)
        self._list.setCurrentRow(0)
        self._list.itemDoubleClicked.connect(lambda _item: self.accept())
        layout.addWidget(self._list)

        buttons = QDialogButtonBox(self)
        update_button = buttons.addButton("Uppdatera vald app", QDialogButtonBox.AcceptRole)
        update_button.setDefault(True)
        buttons.addButton("Stäng", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self._accept_choice)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(560, 340)

    def _accept_choice(self) -> None:
        row = self._list.currentRow()
        if 0 <= row < len(self._rows):
            self._chosen = self._rows[row]
        self.accept()

    def chosen(self) -> CatalogRow | None:
        return self._chosen

    @staticmethod
    def choose(parent, rows: list[CatalogRow]) -> CatalogRow | None:
        dialog = AppUpdatesDialog(parent, rows)
        if dialog.exec() == QDialog.Accepted:
            return dialog.chosen()
        return None
