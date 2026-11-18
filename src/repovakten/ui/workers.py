"""Bakgrundsarbetare för nätverks- och filoperationer.

Endast QtCore – ingen widget-kod. Arbetarna skapar egna Store- och
GitHubClient-instanser inne i tråden, så inga delade objekt korsar
trådgränser. Varje ``finished``-signal bär antingen resultatet eller
undantaget (gränssnittet skiljer dem med ``isinstance(result, Exception)``).
"""
from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from ..compare import FileReport, compare_install
from ..installer import app_install_dir, download_asset, install_from_zip
from ..models import ReleaseAsset
from ..store import Store


class SyncWorker(QObject):
    finished = Signal(object)  # SyncReport eller Exception

    def __init__(self, store_path, client_factory=None, parent=None) -> None:
        super().__init__(parent)
        self._store_path = Path(store_path)
        self._client_factory = client_factory

    @Slot()
    def run(self) -> None:
        try:
            from ..github import GitHubClient
            from ..sync import sync_accounts

            store = Store(self._store_path)
            factory = self._client_factory or GitHubClient
            report = sync_accounts(store, factory())
            self.finished.emit(report)
        except Exception as exc:  # gränssnittet visar felmeddelandet
            self.finished.emit(exc)


@dataclass
class PreparedInstall:
    repo_id: int
    tag: str
    full_name: str
    asset_name: str
    zip_path: Path
    temp_dir: Path
    install_dir: Path
    report: FileReport


class PrepareInstallWorker(QObject):
    """Ladda ner paketet (om ingen lokal zip skickas in) och bygg filrapporten."""

    finished = Signal(object)  # PreparedInstall eller Exception

    def __init__(
        self,
        store_path,
        *,
        repo_id: int,
        tag: str,
        asset: ReleaseAsset,
        zip_path: Path | None = None,
        install_dir: Path | None = None,
        temp_dir: Path | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._store_path = Path(store_path)
        self._repo_id = int(repo_id)
        self._tag = tag
        self._asset = asset
        self._zip_path = Path(zip_path) if zip_path else None
        self._install_dir = Path(install_dir) if install_dir else None
        self._temp_dir = Path(temp_dir) if temp_dir else None

    @Slot()
    def run(self) -> None:
        temp_dir = self._temp_dir or Path(tempfile.mkdtemp(prefix="repovakten-"))
        try:
            store = Store(self._store_path)
            entry = store.get_entry(self._repo_id)
            full_name = entry.repo.full_name if entry else f"repo-{self._repo_id}"

            if self._zip_path is not None:
                zip_path = self._zip_path
            else:
                zip_path = temp_dir / self._asset.name
                download_asset(self._asset.download_url, zip_path)

            install_dir = self._install_dir or app_install_dir(full_name)
            preserved = list(entry.preserve_paths) if entry else None
            old_record = store.get_install(self._repo_id)
            manifest = old_record.files if old_record else None
            report = compare_install(
                zip_path,
                install_dir,
                manifest_files=manifest,
                preserved=preserved or ("storage/",),
            )
            self.finished.emit(
                PreparedInstall(
                    repo_id=self._repo_id,
                    tag=self._tag,
                    full_name=full_name,
                    asset_name=self._asset.name,
                    zip_path=zip_path,
                    temp_dir=temp_dir,
                    install_dir=install_dir,
                    report=report,
                )
            )
        except Exception as exc:
            if self._temp_dir is None:
                # Rensa bara om vi själva skapat katalogen.
                import shutil

                shutil.rmtree(temp_dir, ignore_errors=True)
            self.finished.emit(exc)


class InstallWorker(QObject):
    """Utför själva installationen (spärrkollas inuti, med backup och rollback)."""

    finished = Signal(object)  # InstallResult eller Exception

    def __init__(
        self,
        store_path,
        *,
        zip_path: Path,
        repo_id: int,
        tag: str,
        full_name: str,
        install_dir: Path | None = None,
        backup_root: Path | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._store_path = Path(store_path)
        self._zip_path = Path(zip_path)
        self._repo_id = int(repo_id)
        self._tag = tag
        self._full_name = full_name
        self._install_dir = Path(install_dir) if install_dir else None
        self._backup_root = Path(backup_root) if backup_root else None

    @Slot()
    def run(self) -> None:
        try:
            store = Store(self._store_path)
            result = install_from_zip(
                self._zip_path,
                store=store,
                repo_id=self._repo_id,
                tag=self._tag,
                repo_full_name=self._full_name,
                install_dir=self._install_dir,
                backup_root=self._backup_root,
            )
            self.finished.emit(result)
        except Exception as exc:
            self.finished.emit(exc)
