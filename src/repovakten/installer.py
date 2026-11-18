"""Installation och uppdatering av appar – på begäran, aldrig automatiskt.

Flöde i :func:`install_from_zip`:

1. **Spärren kontrolleras först** (``assert_install_allowed``) – innan något hämtas,
   skrivs eller backas upp. Installationsflödet får varken installera eller
   uppdatera en spärrad app.
2. Paketet valideras i sin helhet (zip-slip, dubbletter, storlekstak) innan
   någon fil skapas eller skrivs över.
3. Befintlig installation kopieras till en backup (bevaras – även efter lyckad
   uppdatering) så att "den tidigare kopian sparas".
4. Filerna packas upp; **bevarade sökvägar (t.ex. ``storage/``) skrivs aldrig över**
   och kan aldrig raderas.
5. Utgående filer (finns lokalt, inte i releasen, ej bevarade) tas bort först
   efter att de nya filerna ligger på plats.
6. Installationsregistret skrivs om (manifest med SHA-256 per fil).
7. Alla fel ⇒ fullständig återställning från backup.

Ingenting som packas upp körs någonsin automatiskt.
"""
from __future__ import annotations

import os
import re
import shutil
import stat
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .blocking import assert_install_allowed
from .compare import FileReport, compare_install
from .errors import RepovaktenError, UnsafeArchiveError
from .hashing import (
    MAX_MEMBERS,
    MAX_UNCOMPRESSED_BYTES,
    is_preserved,
    normalize_relpath,
    sha256_file,
    zip_entries,
)
from .models import DEFAULT_PRESERVE_PATHS, InstallRecord, utcnow_iso
from .store import Store, default_state_dir

MAX_DOWNLOAD_BYTES = 2 * 1024**3  # 2 GiB
_DOWNLOAD_CHUNK = 1024 * 1024


# ------------------------------------------------------------ platser

def default_install_root() -> Path:
    """Var appar installeras om användaren inte väljer själv.

    Programfilerna läggs i en per-OS datamapp (inte i repot, inte i
    projektkloner): Windows %APPDATA%\\Repovakten\\apps, macOS
    ~/Library/Application Support/Repovakten/apps, Linux
    ${XDG_DATA_HOME:-~/.local/share}/repovakten/apps.
    """
    override = os.environ.get("REPOVAKTEN_APPS")
    if override:
        return Path(override).expanduser()
    import sys

    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA")
        return (Path(base) if base else Path.home() / "AppData" / "Roaming") / "Repovakten" / "apps"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Repovakten" / "apps"
    xdg = os.environ.get("XDG_DATA_HOME")
    return (Path(xdg) if xdg else Path.home() / ".local" / "share") / "repovakten" / "apps"


def default_backup_root() -> Path:
    override = os.environ.get("REPOVAKTEN_BACKUPS")
    return Path(override).expanduser() if override else default_state_dir() / "backups"


def _sanitize_segment(part: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", part).strip(".")
    return cleaned or "app"


def app_install_dir(full_name: str, root: Path | None = None) -> Path:
    """Standardplacering för en app: ``<root>/<ägare>/<namn>``."""
    base = Path(root) if root else default_install_root()
    parts = full_name.split("/", 1)
    if len(parts) == 2:
        return base / _sanitize_segment(parts[0]) / _sanitize_segment(parts[1])
    return base / _sanitize_segment(full_name)


def install_root_for(store: "Store | None" = None) -> Path:
    """Rotmapp för installationer: användarval, annars standard per OS."""
    if store is not None:
        custom = store.get_install_root()
        if custom:
            return Path(custom).expanduser()
    return default_install_root()


# ---------------------------------------------------------- nedladdning

def download_asset(
    url: str,
    dest: Path,
    *,
    timeout: float = 60.0,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
) -> Path:
    """Ladda ner en releasetillgång. Endast HTTPS; storlekstak; atomisk skrivning."""
    if not url.lower().startswith("https://"):
        raise RepovaktenError("Nedladdning tillåts endast över HTTPS.")
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"Repovakten/{__version__}",
            "Accept": "application/octet-stream",
        },
    )
    try:
        total = 0
        with urllib.request.urlopen(request, timeout=timeout) as response:
            with open(tmp, "wb") as handle:
                while True:
                    chunk = response.read(_DOWNLOAD_CHUNK)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise RepovaktenError("Paketet är större än tillåtet.")
                    handle.write(chunk)
    except RepovaktenError:
        tmp.unlink(missing_ok=True)
        raise
    except urllib.error.URLError as exc:
        tmp.unlink(missing_ok=True)
        raise RepovaktenError(f"Nedladdningen misslyckades: {exc.reason}") from exc
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise RepovaktenError(f"Nedladdningen misslyckades: {exc}") from exc
    if total == 0:
        tmp.unlink(missing_ok=True)
        raise RepovaktenError("Paketet var tomt.")
    os.replace(tmp, dest)
    return dest


# ------------------------------------------------------------------ zip

def _validated_members(
    zip_path: Path, preserved: list[str]
) -> list[tuple[str, zipfile.ZipInfo]]:
    """Validera hela arkivet och returnera [(relpath, ZipInfo)] – UTAN enhetsrot.

    Om ALLA filer i arkivet ligger under exakt en gemensam rotkatalog
    (t.ex. ``MyApp-1.2.0/…``) strippas den, så att innehållet landar direkt
    i installationskatalogen. Bevarade sökvägar hoppas över efter
    rottstrippningen (``MyApp-1.2.0/storage/…`` skrivs aldrig över).
    Kastar UnsafeArchiveError innan något skrivits.

    Själva valideringen delas med :func:`repovakten.hashing.zip_entries`,
    så att jämförelsen och uppackningen alltid ser samma filer.
    """
    return zip_entries(
        zip_path,
        preserved,
        max_members=MAX_MEMBERS,
        max_uncompressed=MAX_UNCOMPRESSED_BYTES,
    )


def _checked_destination(base: Path, rel: str) -> Path:
    """Defense-in-depth ovanpå normalize_relpath: målet måste ligga i base."""
    base_resolved = base.resolve()
    dest = base_resolved / rel
    resolved = dest.resolve()
    if resolved != base_resolved and base_resolved not in resolved.parents:
        raise UnsafeArchiveError(f"Sökväg utanför installationskatalogen: {rel!r}")
    return resolved


def _extract(
    zip_path: Path,
    members: list[tuple[str, zipfile.ZipInfo]],
    install_dir: Path,
) -> list[str]:
    install_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    with zipfile.ZipFile(zip_path) as archive:
        for rel, info in members:
            dest = _checked_destination(install_dir, rel)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, open(dest, "wb") as dst:
                shutil.copyfileobj(src, dst, _DOWNLOAD_CHUNK)
            mode = stat.S_IMODE(info.external_attr >> 16)
            if mode:
                try:
                    os.chmod(dest, mode)
                except OSError:
                    pass
            written.append(rel)
    return written


# ---------------------------------------------------------------- backup

def backup_install(
    install_dir: Path,
    backup_root: Path,
    full_name: str,
    tag: str,
) -> Path | None:
    """Kopiera den befintliga installationen till backup-roten. None om ingen finns."""
    install_dir = Path(install_dir)
    if not install_dir.exists():
        return None
    segment = _sanitize_segment(full_name.replace("/", "__"))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dest = Path(backup_root) / segment / f"{stamp}-{_sanitize_segment(tag)}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(install_dir, dest)
    return dest


def _rollback(install_dir: Path, backup: Path | None, existed_before: bool) -> None:
    if existed_before and backup is not None:
        try:
            shutil.rmtree(install_dir, ignore_errors=True)
            shutil.copytree(backup, install_dir)
            return
        except OSError:
            pass  # originalet finns kvar i backupen oavsett
    if not existed_before:
        # Halvfärdig färskinstallation – lämna inget skräp.
        shutil.rmtree(install_dir, ignore_errors=True)


def remove_outgoing(install_dir: Path, outgoing: list[str], preserved: list[str]) -> list[str]:
    removed: list[str] = []
    install_dir = Path(install_dir)
    for rel in outgoing:
        if is_preserved(rel, preserved):
            continue
        target = install_dir / rel
        try:
            if target.is_file() or target.is_symlink():
                target.unlink()
                removed.append(rel)
        except OSError:
            continue
        parent = target.parent
        while parent != install_dir and install_dir in parent.parents:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
    return removed


# ------------------------------------------------------------- installation

@dataclass
class InstallResult:
    repo_id: int
    install_dir: Path
    tag: str
    backup_dir: Path | None
    report: FileReport
    removed_files: list[str]
    record: InstallRecord


def install_from_zip(
    zip_path: Path,
    *,
    store: Store,
    repo_id: int,
    tag: str,
    repo_full_name: str | None = None,
    install_dir: Path | None = None,
    backup_root: Path | None = None,
    preserved: list[str] | None = None,
) -> InstallResult:
    """Installera/uppdatera appen från en lokal ZIP. Se moduldocstringen."""
    # 1. Spärren kontrolleras FÖRST – före nedladdning, backup och skrivning.
    assert_install_allowed(store, repo_id)

    zip_path = Path(zip_path)
    entry = store.get_entry(repo_id)
    full_name = repo_full_name or (entry.repo.full_name if entry else f"repo-{repo_id}")
    if preserved is None:
        preserved = list(entry.preserve_paths) if entry else list(DEFAULT_PRESERVE_PATHS)
    old_record = store.get_install(repo_id)
    manifest = old_record.files if old_record else None
    # Var appen läggs: explicit val > redan registrerad mapp > användarval/standard.
    if install_dir is not None:
        target_dir = Path(install_dir)
    elif old_record is not None and old_record.install_dir:
        target_dir = Path(old_record.install_dir)
    else:
        target_dir = app_install_dir(full_name, root=install_root_for(store))
    backups = Path(backup_root) if backup_root else default_backup_root()

    # 2. Rapporten beräknas FÖRE någon ändring – samma rapport som visas för användaren.
    report = compare_install(zip_path, target_dir, manifest_files=manifest, preserved=preserved)

    # 3. Hela paketet valideras innan något skrivs.
    members = _validated_members(zip_path, preserved)

    existed_before = target_dir.exists()
    backup = backup_install(target_dir, backups, full_name, tag) if existed_before else None
    try:
        # 4–5. Packa upp; bevarade sökvägar skrivs aldrig över; sedan utgående filer.
        _extract(zip_path, members, target_dir)
        outgoing = [d.path for d in report.removed]
        removed = remove_outgoing(target_dir, outgoing, preserved)

        files = {rel: sha256_file(target_dir / rel) for rel, _ in members}
        now = utcnow_iso()
        record = InstallRecord(
            repo_id=int(repo_id),
            repo_full_name=full_name,
            installed_tag=tag,
            install_dir=str(target_dir),
            installed_at=old_record.installed_at if old_record else now,
            updated_at=now,
            files=files,
            preserve_paths=list(preserved),
        )
        store.set_install(record)
    except Exception:
        _rollback(target_dir, backup, existed_before)
        raise

    return InstallResult(
        repo_id=int(repo_id),
        install_dir=target_dir,
        tag=tag,
        backup_dir=backup,
        report=report,
        removed_files=removed,
        record=record,
    )
