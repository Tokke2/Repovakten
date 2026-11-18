"""Huvudfönstret för Repovakten (svenska).

Katalogen visar alla bevakade repon – även de utan release. Installation
kräver alltid: (1) att appen inte är spärrad, (2) att användaren väljer
paket om releasen har flera, och (3) att användaren godkänner filrapporten
innan något ändras på datorn. Nätverk och installation körs i bakgrunds-
trådar så gränssnittet aldrig fryser.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Qt, QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import applog, autostart
from ..blocking import block_app, is_blocked, unblock_app
from ..catalog import InstallStatus, build_catalog_rows, updates_for_installed_apps
from ..errors import InstallationBlockedError, RepovaktenError
from ..models import validate_github_username
from ..releases import installable_assets, rank_assets_for_platform, select_latest_stable
from ..store import Store, default_state_path
from ..sync import SYNC_INTERVAL_SECONDS
from .dialogs import AppUpdatesDialog, AssetPickerDialog, FileReportDialog
from .donation_dialog import DonationDialog
from .status import install_allowed_text, row_color, status_text
from .workers import (
    InstallWorker,
    PrepareInstallWorker,
    PreparedInstall,
    SelfCheckWorker,
    SelfInstallWorker,
    SyncWorker,
)

_COLUMNS = ["App", "Språk", "Installerad version", "Senaste stabila", "Status", "Tillåtet"]


class MainWindow(QMainWindow):
    def __init__(
        self,
        store: Store | None = None,
        *,
        client_factory=None,
        state_path: Path | None = None,
    ) -> None:
        super().__init__()
        self._store = store or Store(state_path or default_state_path())
        self._client_factory = client_factory
        self._state_path = Path(state_path or self._store.path)
        self._rows = []  # CatalogRow-lista, speglar tabellens rader
        self._thread: QThread | None = None
        self._worker: object | None = None
        self._busy = False
        # Självuppdatering körs i egen tråd så den aldrig blockerar appen.
        self._self_thread: QThread | None = None
        self._self_worker: object | None = None
        self._self_plan: object | None = None

        self.setWindowTitle("Repovakten")
        self.resize(960, 560)
        self._build_ui()

        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(SYNC_INTERVAL_SECONDS * 1000)
        self._sync_timer.timeout.connect(self.sync_now)
        self._sync_timer.start()

        self.refresh()
        self._pending_startup_check = True  # uppdateringskontroll efter första synken
        self.sync_now()  # synk vid appstart

    # ------------------------------------------------------------- UI-bygge

    def _build_ui(self) -> None:
        self._build_menu()
        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Bevakade konton:"))
        self._account_combo = QComboBox(self)
        self._account_combo.currentTextChanged.connect(self._on_account_changed)
        toolbar.addWidget(self._account_combo)

        add_account = QPushButton("Lägg till konto…")
        add_account.clicked.connect(self.add_account)
        toolbar.addWidget(add_account)

        remove_account = QPushButton("Ta bort konto")
        remove_account.clicked.connect(self.remove_account)
        toolbar.addWidget(remove_account)

        toolbar.addStretch(1)
        self._sync_button = QPushButton("Synka nu")
        self._sync_button.clicked.connect(self.sync_now)
        toolbar.addWidget(self._sync_button)
        layout.addLayout(toolbar)

        self._table = QTableWidget(0, len(_COLUMNS), self)
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSelectionMode(QTableWidget.SingleSelection)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.itemSelectionChanged.connect(self._update_action_buttons)
        layout.addWidget(self._table)

        actions = QHBoxLayout()
        self._install_button = QPushButton("Installera / Uppdatera…")
        self._install_button.clicked.connect(self.install_selected)
        actions.addWidget(self._install_button)

        self._block_button = QPushButton("Spärra installation")
        self._block_button.clicked.connect(self.toggle_block_selected)
        actions.addWidget(self._block_button)

        github_button = QPushButton("Öppna på GitHub")
        github_button.clicked.connect(self.open_selected_on_github)
        actions.addWidget(github_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self._status_label = QLabel("Redo.")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        open_action = QAction("Synka nu", self)
        open_action.triggered.connect(self.sync_now)
        self.addAction(open_action)

    def _build_menu(self) -> None:
        """Menyrad – donation, uppdateringar och autostart nås via menyn."""
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&Arkiv")
        self._autostart_action = QAction("Starta med datorn", self)
        self._autostart_action.setCheckable(True)
        self._autostart_action.setChecked(autostart.is_enabled())
        self._autostart_action.triggered.connect(self._toggle_autostart)
        file_menu.addAction(self._autostart_action)
        file_menu.addSeparator()
        quit_action = QAction("&Avsluta", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        help_menu = menubar.addMenu("&Hjälp")
        donate_action = QAction("&Stöd projektet… 💚", self)
        donate_action.triggered.connect(self.show_donation_dialog)
        help_menu.addAction(donate_action)
        help_menu.addSeparator()
        update_action = QAction("&Sök uppdateringar…", self)
        update_action.triggered.connect(lambda: self.check_self_update())
        help_menu.addAction(update_action)
        help_menu.addSeparator()
        about_action = QAction("&Om Repovakten", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def _toggle_autostart(self, checked: bool = False) -> None:
        """Starta med datorn: registrera/avregistrera autostart (alla OS)."""
        try:
            if checked:
                message = autostart.enable()
            else:
                autostart.disable()
                message = "Autostart av – Repovakten startas inte längre med datorn."
        except RepovaktenError as exc:
            self._fail("Autostart", str(exc), applog.AUTOSTART_FEL, exc=exc)
            self._autostart_action.setChecked(autostart.is_enabled())
            return
        self._status_label.setText(message)
        self._autostart_action.setChecked(autostart.is_enabled())

    def _fail(
        self,
        title: str,
        message: str,
        code: str,
        *,
        critical: bool = False,
        exc: BaseException | None = None,
    ) -> None:
        """Logga felet med felkod och visa det – användaren kan citera koden."""
        applog.error(code, f"{title}: {message}", exc=exc)
        text = f"{message}\n\nFelkod: {code} (finns även i loggen)"
        if critical:
            QMessageBox.critical(self, title, text)
        else:
            QMessageBox.warning(self, title, text)

    def show_donation_dialog(self) -> None:
        """Öppna donator-dialogen (Swish-QR, PayPal, Ko-fi)."""
        DonationDialog(self).exec()

    def show_about(self) -> None:
        from .. import __version__

        QMessageBox.about(
            self,
            "Om Repovakten",
            f"<b>Repovakten {__version__}</b><br><br>"
            "Installations- och uppdateringshanterare för GitHub-appar.<br>"
            "Gratis, utan reklam – öppen källkod på "
            '<a href="https://github.com/Tokke2/Repovakten">GitHub</a>.<br><br>'
            "Vill du stödja utvecklingen? Menyn Hjälp → Stöd projektet 💚",
        )

    # ------------------------------------------------------- självuppdatering

    def check_self_update(self, auto: bool = False) -> None:
        """Sök nyare kod i den rullande releasen och föreslå uppdatering.

        Filrapporten visas alltid INNAN något ändras; avslutas dialogen
        sker ingenting. ``auto=True`` används vid appstart och visar
        tystare statusmeddelanden vid fel.
        """
        if self._self_thread is not None:
            return  # en sökning pågår redan
        if not auto:
            self._status_label.setText("Söker uppdatering av Repovakten…")
        worker = SelfCheckWorker(self._state_path, client_factory=self._client_factory)
        self._start_worker(
            worker,
            lambda result: self._on_self_check_finished(result, auto),
            self_update=True,
        )

    def _clear_self_check_thread(self) -> None:
        self._self_thread = None
        self._self_worker = None

    def _on_self_check_finished(self, result, auto: bool) -> None:
        if isinstance(result, Exception):
            message = f"Kunde inte söka uppdatering av Repovakten: {result}"
            if auto:
                applog.error(applog.UPPDATERA_SOK_FEL, message, exc=result)
                self._status_label.setText(message)
            else:
                self._fail("Sök uppdatering", message, applog.UPPDATERA_SOK_FEL, exc=result)
            self._show_app_updates(quiet=auto)
            return
        plan = result
        self._self_plan = plan
        if not plan.has_changes:
            text = f"Repovakten kör redan koden från {plan.tag} – inga filer skiljer sig."
            if auto:
                self._status_label.setText(text)
            else:
                QMessageBox.information(self, "Sök uppdatering", text)
            self._discard_self_plan()
            self._show_app_updates(quiet=auto)
            return
        # Föreslå uppdateringen – inget ändras utan godkännande.
        dialog = FileReportDialog(
            self,
            title=f"Självuppdatering – Repovakten {plan.tag}",
            tag=plan.tag,
            report=plan.report,
            is_update=True,
        )
        dialog.setWindowTitle("Uppdatera Repovakten")
        if dialog.exec() and dialog.install_requested():
            self._status_label.setText(f"Uppdaterar Repovakten till {plan.tag}…")
            worker = SelfInstallWorker(self._state_path, zip_path=plan.zip_path, tag=plan.tag)
            self._start_worker(worker, self._on_self_install_finished)
            # Appkontrollen körs när självuppdateringen är klar.
        else:
            self._status_label.setText("Ingen ändring gjord – du kör samma kod som förut.")
            self._discard_self_plan()
            self._show_app_updates(quiet=auto)

    def _on_self_install_finished(self, result) -> None:
        if isinstance(result, Exception):
            self._fail(
                "Självuppdatering",
                f"Uppdateringen misslyckades: {result}\n\nDen gamla kopian är återställd.",
                applog.UPPDATERA_FEL,
                exc=result,
            )
            self._status_label.setText("Självuppdateringen misslyckades – gamla kopian kvar.")
            self._discard_self_plan()
            return
        applog.info(f"Självuppdaterad till {result.tag}")
        backup_text = (
            f"\n\nTidigare kopia sparad i:\n{result.backup_dir}" if result.backup_dir else ""
        )
        QMessageBox.information(
            self,
            "Repovakten är uppdaterad",
            f"Programfilerna är uppdaterade till {result.tag}.{backup_text}\n\n"
            "Starta om Repovakten för att använda den nya koden.",
        )
        self._status_label.setText(f"Repovakten {result.tag} uppdaterad – starta om appen.")
        self._discard_self_plan()
        self._show_app_updates()  # kolla även installerade appar efter uppdateringar

    def _discard_self_plan(self) -> None:
        plan, self._self_plan = self._self_plan, None
        if plan is not None:
            shutil.rmtree(plan.temp_dir, ignore_errors=True)

    def _show_app_updates(self, quiet: bool = False) -> None:
        """Kolla installerade appar efter uppdateringar och erbjud dem."""
        self._store.reload()  # färsk data från senaste synken
        updates = updates_for_installed_apps(self._store)
        if not updates:
            if not quiet:
                self._status_label.setText("Inga installerade appar har uppdateringar.")
            return
        names = ", ".join(row.repo.full_name for row in updates)
        self._status_label.setText(f"Uppdateringar finns för: {names}")
        chosen = AppUpdatesDialog.choose(self, updates)
        if chosen is not None:
            self._install_row(chosen)

    # ------------------------------------------------------------- data

    def refresh(self) -> None:
        """Ladda om katalogen från lagret och rita om tabellen."""
        self._rows = build_catalog_rows(self._store)
        self._table.setRowCount(len(self._rows))
        for index, row in enumerate(self._rows):
            values = [
                row.repo.full_name,
                row.repo.language or "–",
                row.installed_version or "–",
                row.latest_stable_tag or "–",
                status_text(row.status),
                install_allowed_text(row.install_allowed),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if column == 4:  # statuscellen färgas
                    color = row_color(row.status)
                    if color:
                        item.setBackground(color)
                self._table.setItem(index, column, item)

        accounts = self._store.accounts()
        current = self._account_combo.currentText()
        self._account_combo.blockSignals(True)
        self._account_combo.clear()
        self._account_combo.addItems(accounts)
        if current in accounts:
            self._account_combo.setCurrentText(current)
        self._account_combo.blockSignals(False)
        self._update_action_buttons()

    def _selected_row(self):
        row = self._table.currentRow()
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

    def _update_action_buttons(self) -> None:
        row = self._selected_row()
        if row is None:
            self._install_button.setEnabled(False)
            self._block_button.setEnabled(False)
            return
        self._install_button.setEnabled(row.can_install and not self._busy)
        self._block_button.setEnabled(not self._busy)
        blocked = is_blocked(self._store, row.repo.id)
        self._block_button.setText("Tillåt igen" if blocked else "Spärra installation")

    def _on_account_changed(self, _text: str) -> None:
        # Att byta konto ändrar ingenting i katalogen – alla bevakade konton
        # visas samtidigt. (Kombon är bara en snabbvy/förval.)
        pass

    # ------------------------------------------------------------- konton

    def add_account(self) -> None:
        name, ok = QInputDialog.getText(self, "Lägg till konto", "GitHub-användarnamn:")
        if not ok:
            return
        name = name.strip()
        if not name:
            return
        try:
            normalized = validate_github_username(name)
        except RepovaktenError as exc:
            QMessageBox.warning(self, "Ogiltigt användarnamn", str(exc))
            return
        self._store.add_account(normalized)
        self.refresh()
        self._status_label.setText(f"Konto {normalized} bevakas. Synkar…")
        self.sync_now()

    def remove_account(self) -> None:
        account = self._account_combo.currentText()
        if not account:
            return
        answer = QMessageBox.question(
            self,
            "Ta bort konto",
            f"Sluta bevaka {account}?\n\n"
            "Katalogen behålls, men kontot synkas inte längre. "
            "Spärrar och installationer påverkas inte.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._store.remove_account(account)
        self.refresh()
        self._status_label.setText(f"Konto {account} borttaget.")

    # ------------------------------------------------------------- synk

    def sync_now(self) -> None:
        if self._busy:
            return
        self._set_busy(True, "Synkar mot GitHub…")
        worker = SyncWorker(self._state_path, client_factory=self._client_factory)
        self._start_worker(worker, self._on_sync_finished)

    def _on_sync_finished(self, result) -> None:
        self._set_busy(False)
        if isinstance(result, Exception):
            self._fail("Synk misslyckades", str(result), applog.SYNK_FEL, exc=result)
            self._status_label.setText(f"Synk misslyckades: {result}")
        else:
            applog.info(f"Synk klar: {result.summary_swedish()}")
            self.refresh()
            self._status_label.setText(result.summary_swedish())
        if getattr(self, "_pending_startup_check", False):
            self._pending_startup_check = False
            self.check_self_update(auto=True)  # själv + installerade appar

    # ------------------------------------------------------------- installation

    def install_selected(self) -> None:
        row = self._selected_row()
        if row is not None:
            self._install_row(row)

    def _install_row(self, row) -> None:
        """Installera/uppdatera en katalograd (samma flöde som tabellknappen)."""
        if row is None or self._busy:
            return
        if not row.can_install:
            if row.status is InstallStatus.BLOCKED:
                QMessageBox.information(
                    self,
                    "Spärrad",
                    "Denna app är spärrad av admin och kan inte installeras eller uppdateras.",
                )
            else:
                QMessageBox.information(
                    self,
                    "Kan inte installeras",
                    f"Status: {status_text(row.status)}. "
                    "Det finns inget installerbart ZIP-paket i den senaste stabila releasen.",
                )
            return

        entry = self._store.get_entry(row.repo.id)
        stable = select_latest_stable(entry.releases) if entry else None
        assets = installable_assets(stable) if stable else []
        if not assets:
            QMessageBox.information(
                self,
                "Inget paket",
                "Den senaste stabila releasen innehåller inget ZIP-paket att installera.",
            )
            return

        if len(assets) == 1:
            asset = assets[0]
        else:
            suggestions = rank_assets_for_platform(assets)
            chosen = AssetPickerDialog.choose(self, suggestions, stable.tag_name)
            if chosen is None:
                return
            asset = chosen.asset

        self._set_busy(True, f"Laddar ner {asset.name}…")
        worker = PrepareInstallWorker(
            self._state_path,
            repo_id=row.repo.id,
            tag=stable.tag_name,
            asset=asset,
        )
        self._start_worker(worker, lambda result: self._on_prepare_finished(result, row.repo.id))

    def _on_prepare_finished(self, result, repo_id: int) -> None:
        self._set_busy(False)
        if isinstance(result, Exception):
            self._fail(
                "Kunde inte förbereda installation",
                str(result),
                applog.INSTALL_FORBEREDELSE_FEL,
                exc=result,
            )
            self._status_label.setText(f"Förberedelse misslyckades: {result}")
            return
        prepared: PreparedInstall = result
        is_update = self._store.get_install(repo_id) is not None
        dialog = FileReportDialog(
            self,
            title=prepared.full_name,
            tag=prepared.tag,
            report=prepared.report,
            is_update=is_update,
        )
        accepted = dialog.exec() == dialog.Accepted
        if not accepted or not dialog.install_requested():
            self._status_label.setText("Avbrutet – inget ändrat.")
            return

        self._set_busy(True, f"Installerar {prepared.tag}…")
        worker = InstallWorker(
            self._state_path,
            zip_path=prepared.zip_path,
            repo_id=prepared.repo_id,
            tag=prepared.tag,
            full_name=prepared.full_name,
            install_dir=prepared.install_dir,
        )
        self._start_worker(worker, self._on_install_finished)

    def _on_install_finished(self, result) -> None:
        self._set_busy(False)
        if isinstance(result, InstallationBlockedError):
            self._fail("Spärrad", str(result), applog.INSTALL_SPARRAD)
            self._status_label.setText("Installation avbruten – appen är spärrad.")
            self.refresh()
            return
        if isinstance(result, Exception):
            self._fail(
                "Installation misslyckades",
                str(result),
                applog.INSTALL_FEL,
                critical=True,
                exc=result,
            )
            self._status_label.setText(f"Installation misslyckades: {result}")
            return
        applog.info(
            f"Installerad: {result.record.repo_full_name} {result.record.installed_tag}"
        )
        self.refresh()
        backup_text = f"\nTidigare kopia sparad i:\n{result.backup_dir}" if result.backup_dir else ""
        QMessageBox.information(
            self,
            "Klart",
            f"{result.record.repo_full_name} {result.record.installed_tag} är installerad.{backup_text}",
        )
        self._status_label.setText(
            f"{result.record.repo_full_name} {result.record.installed_tag} installerad."
        )

    # ------------------------------------------------------------- spärr

    def toggle_block_selected(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        repo_id = row.repo.id
        if is_blocked(self._store, repo_id):
            unblock_app(self._store, repo_id)
            self._status_label.setText(f"{row.repo.full_name} är tillåten igen.")
        else:
            reason, ok = QInputDialog.getText(
                self,
                "Spärra installation",
                f"Spärra {row.repo.full_name}?\n\n"
                "En spärrad app kan visas men inte installeras eller uppdateras. "
                "En redan installerad kopia raderas INTE.\n\nOrsak (valfritt):",
            )
            if not ok:
                return
            block_app(self._store, repo_id, reason=reason.strip())
            self._status_label.setText(f"{row.repo.full_name} är spärrad.")
        self.refresh()

    # ------------------------------------------------------------- övrigt

    def open_selected_on_github(self) -> None:
        row = self._selected_row()
        if row is None or not row.repo.html_url:
            return
        QDesktopServices.openUrl(QUrl(row.repo.html_url))

    # ------------------------------------------------------------- trådar

    def _start_worker(self, worker, on_finished, *, self_update: bool = False) -> None:
        """Starta arbetaren i egen tråd – klart-signalen hanteras i huvudtråden.

        Vi kopplar via en QMainWindow-metod med QueuedConnection. En lambda
        eller partial kopplad direkt mot ``finished`` kan annars köras i
        arbetstråden (beror på PySide6-version) – då skapas dialoger och
        widgets i fel tråd, vilket ger Qt-varningar om föräldrar, timrar
        och omritningar.
        """
        worker._ui_callback = on_finished
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._worker_finished, Qt.QueuedConnection)
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        if self_update:
            thread.finished.connect(self._clear_self_check_thread)
            self._self_thread = thread
            self._self_worker = worker  # behåll referens tills tråden är klar
        else:
            self._thread = thread
            self._worker = worker
        thread.start()

    def _worker_finished(self, result) -> None:
        """Körs alltid i huvudtråden – anropar det sparade klart-callbacket."""
        worker = self.sender()
        callback = getattr(worker, "_ui_callback", None) if worker is not None else None
        if callback is not None:
            worker._ui_callback = None
            callback(result)

    def _set_busy(self, busy: bool, message: str | None = None) -> None:
        self._busy = busy
        self._sync_button.setEnabled(not busy)
        if message:
            self._status_label.setText(message)
        self._update_action_buttons()
