"""Skanna en mapp efter appar som redan är installerade (Qt-fri).

Användaren pekar ut en mapp – Repovakten letar upp kataloger som hör till
bevakade appar och registrerar dem som installerade kopior med ett
SHA-256-manifest per fil. Då kan de gamla kopiorna uppdateras på plats via
vanliga flödet (filrapport, backup, rollback).

Sökmönster per app (första katalogen med filer vinner):

1. ``<mapp>/<ägare>/<namn>`` – samma layout som Repovakten installerar med.
2. ``<mapp>/<namn>`` – löst placerad kopia.
3. mappen själv, om dess namn matchar appen (en app per mapp).

Bevarade sökvägar (t.ex. ``storage/``) räknas aldrig in i manifestet.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .errors import RepovaktenError
from .hashing import hash_tree
from .installer import _sanitize_segment, app_install_dir
from .models import DEFAULT_PRESERVE_PATHS, InstallRecord, utcnow_iso
from .store import Store

#: Etikett för kopior som hittats av skanningen (versionsnumret okänt).
LOCAL_TAG = "lokal kopia"


@dataclass
class ScanHit:
    """En katalog som matchar en bevakad app."""

    repo_id: int
    full_name: str
    path: Path
    file_count: int
    registered: bool  # False = appen fanns redan i installationsregistret


@dataclass
class ScanReport:
    """Resultatet av en skanning."""

    folder: Path
    hits: list[ScanHit] = field(default_factory=list)
    unknown_dirs: list[Path] = field(default_factory=list)

    @property
    def registered(self) -> list[ScanHit]:
        return [hit for hit in self.hits if hit.registered]

    @property
    def already_known(self) -> list[ScanHit]:
        return [hit for hit in self.hits if not hit.registered]

    def summary_swedish(self) -> str:
        lines = []
        if self.registered:
            names = ", ".join(
                f"{hit.full_name} ({hit.file_count} filer)" for hit in self.registered
            )
            lines.append(f"Registrerade som installerade: {names}.")
        if self.already_known:
            names = ", ".join(hit.full_name for hit in self.already_known)
            lines.append(f"Redan kända för Repovakten (hoppades över): {names}.")
        if self.unknown_dirs:
            names = ", ".join(d.name for d in self.unknown_dirs)
            lines.append(f"Kataloger utan matchande app (hoppades över): {names}.")
        if not self.hits:
            lines.insert(0, f"Inga installerade appar hittades i {self.folder}.")
        return "\n".join(lines)


def _candidate_dirs(folder: Path, full_name: str, name: str) -> list[Path]:
    """Kandidatkataloger för appen, i prioritetsordning."""
    candidates = [
        app_install_dir(full_name, root=folder),  # <mapp>/<ägare>/<namn>
        folder / _sanitize_segment(name),  # <mapp>/<namn>
    ]
    if _sanitize_segment(folder.name) == _sanitize_segment(name):
        candidates.append(folder)  # mappen själv är appen
    return candidates


def scan_folder(folder: Path, store: Store) -> ScanReport:
    """Sök igenom ``folder`` och registrera appar som redan är installerade.

    Appar som redan finns i installationsregistret rörs inte. Okända
    kataloger rapporteras men ändras aldrig.
    """
    folder = Path(folder)
    if not folder.is_dir():
        raise RepovaktenError(f"Mappen {folder} finns inte eller är ingen mapp.")

    report = ScanReport(folder=folder)
    consumed: set[Path] = set()

    for entry in store.repo_entries():
        name = entry.repo.name
        full_name = entry.repo.full_name
        preserve = list(entry.preserve_paths) or list(DEFAULT_PRESERVE_PATHS)
        for path in _candidate_dirs(folder, full_name, name):
            if not path.is_dir():
                continue
            files = hash_tree(path, preserve)
            if not files:
                continue  # tom katalog (eller bara bevarat innehåll) räknas inte
            existing = store.get_install(entry.repo.id)
            if existing is not None:
                report.hits.append(
                    ScanHit(entry.repo.id, full_name, path, len(files), registered=False)
                )
            else:
                store.set_install(
                    InstallRecord(
                        repo_id=entry.repo.id,
                        repo_full_name=full_name,
                        installed_tag=LOCAL_TAG,
                        install_dir=str(path),
                        installed_at=utcnow_iso(),
                        updated_at=utcnow_iso(),
                        files=files,
                        preserve_paths=preserve,
                    )
                )
                report.hits.append(
                    ScanHit(entry.repo.id, full_name, path, len(files), registered=True)
                )
            consumed.add(path)
            consumed.add(path.parent)
            consumed.add(folder)
            break  # första katalogen med filer räcker

    report.unknown_dirs = [
        item
        for item in sorted(folder.iterdir())
        if item.is_dir() and item not in consumed and not item.name.startswith(".")
    ]
    return report
