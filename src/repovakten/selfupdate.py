"""Självuppdatering – Repovakten uppdaterar sig själv från den rullande releasen.

Flödet är detsamma som för appar i katalogen, men *mottagaren* är den
körande koden själv:

1. Hämta senaste **stabila** releasen av ``Tokke2/Repovakten`` och bästa
   portabla ZIP-paketet för plattformen.
2. Jämför paketets ``repovakten/``-filer mot den körande katalogen med
   SHA-256 – *även när versionsnumret är samma* (den rullande releasen
   byts ut vid ny kod utan nytt versionsnummer).
3. Visa filrapporten och låt användaren godkänna – inget ändras annars.
4. Installera med backup och rullning tillbaka precis som alltid.

Endast ``repovakten/``-paketet uppdateras (startskript, VERSION och
README runt omkring rörs inte). ``__pycache__`` bevaras alltid.
"""
from __future__ import annotations

import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .compare import FileReport, compare_files
from .errors import RepovaktenError, UnsafeArchiveError
from .hashing import hash_tree, hash_zip, zip_entries
from .installer import download_asset, install_from_zip
from .models import Release, ReleaseAsset
from .releases import installable_assets, rank_assets_for_platform, select_latest_stable
from .store import Store

SELF_OWNER = "Tokke2"
SELF_NAME = "Repovakten"

# Syntetiskt repo-ID för installationsregistret – kan aldrig krocka med
# GitHubs repo-ID:n, så självuppdateringen påverkar inte katalogens poster.
SELF_RECORD_ID = -1

_PKG_PREFIX = "repovakten/"
# Python kompilerar om __pycache__ själv – jämför eller radera aldrig.
_PRESERVED = ("__pycache__/",)


def package_dir() -> Path:
    """Katalogen för det körande ``repovakten``-paketet."""
    import repovakten

    return Path(repovakten.__file__).resolve().parent


def package_files_in_zip(zip_path: Path) -> dict[str, str]:
    """``{sökväg i paketet: sha256}`` för releasens ``repovakten/``-filer.

    Övriga filer i ZIP:en (README, startskript …) hör inte till
    självuppdateringen. Arkivet valideras (zip-slip med flera avvisas).
    """
    files = hash_zip(Path(zip_path), _PRESERVED)
    return {
        rel[len(_PKG_PREFIX):]: digest
        for rel, digest in files.items()
        if rel.startswith(_PKG_PREFIX)
    }


def compare_self(
    zip_path: Path,
    *,
    pkg_dir: Path | None = None,
    manifest_files: dict[str, str] | None = None,
) -> FileReport:
    """Jämför releasens paketfiler mot den körande kopian (SHA-256 per fil)."""
    release = package_files_in_zip(Path(zip_path))
    local = hash_tree(Path(pkg_dir) if pkg_dir else package_dir(), _PRESERVED)
    return compare_files(release, local, manifest_files=manifest_files, preserved=_PRESERVED)


def build_self_zip(zip_path: Path, dest: Path) -> Path:
    """Validera release-ZIP:en och packa om endast paketet till ``dest``.

    Den ombyggda ZIP:en har filerna relativt paketkatalogen, så den kan
    installeras direkt ovanpå den körande kopian med den vanliga
    säkra installationspipelinen.
    """
    entries = zip_entries(Path(zip_path), _PRESERVED)
    pkg_entries = [(rel, info) for rel, info in entries if rel.startswith(_PKG_PREFIX)]
    if not pkg_entries:
        raise UnsafeArchiveError("Releasen innehåller inget repovakten-paket att uppdatera.")
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as out:
        with zipfile.ZipFile(zip_path) as src:
            for rel, info in pkg_entries:
                out.writestr(rel[len(_PKG_PREFIX):], src.read(info))
    return dest


def install_update(
    zip_path: Path,
    *,
    store: Store,
    tag: str,
    pkg_dir: Path | None = None,
    backup_root: Path | None = None,
):
    """Uppdatera det körande paketet från release-ZIP:en.

    Returnerar :class:`repovakten.installer.InstallResult` – backup,
    manifest och rullning tillbaka sköts av den vanliga pipeline:n.
    """
    pkg = Path(pkg_dir) if pkg_dir else package_dir()
    with tempfile.TemporaryDirectory(prefix="repovakten-själv-") as tmp:
        self_zip = build_self_zip(Path(zip_path), Path(tmp) / "repovakten-själv.zip")
        return install_from_zip(
            self_zip,
            store=store,
            repo_id=SELF_RECORD_ID,
            tag=tag,
            repo_full_name=f"{SELF_OWNER}/{SELF_NAME}",
            install_dir=pkg,
            backup_root=backup_root,
            preserved=list(_PRESERVED),
        )


@dataclass(frozen=True)
class SelfUpdatePlan:
    """En funnen uppdatering: tagg, paket och filrapport mot den körande koden."""

    tag: str
    asset_name: str
    zip_path: Path
    temp_dir: Path
    report: FileReport

    @property
    def has_changes(self) -> bool:
        return bool(self.report.differences)


def find_self_release(client) -> tuple[Release, ReleaseAsset]:
    """Senaste stabila releasen av Repovakten och bästa ZIP-paketet."""
    releases = client.list_releases(SELF_OWNER, SELF_NAME)
    stable = select_latest_stable(releases)
    if stable is None:
        raise RepovaktenError("Repovakten har ingen stabil release ännu.")
    ranked = rank_assets_for_platform(installable_assets(stable))
    if not ranked:
        raise RepovaktenError(f"Releasen {stable.tag_name} saknar portabel ZIP-tillgång.")
    return stable, ranked[0].asset


def check_for_update(
    client,
    *,
    pkg_dir: Path | None = None,
    manifest_files: dict[str, str] | None = None,
    temp_dir: Path | None = None,
    fetch=None,
) -> SelfUpdatePlan:
    """Sök uppdatering: hämta paketet och jämför mot den körande koden."""
    stable, asset = find_self_release(client)
    temp = Path(temp_dir) if temp_dir else Path(tempfile.mkdtemp(prefix="repovakten-själv-"))
    temp.mkdir(parents=True, exist_ok=True)
    zip_path = temp / asset.name
    (fetch or download_asset)(asset.download_url, zip_path)
    report = compare_self(zip_path, pkg_dir=pkg_dir, manifest_files=manifest_files)
    return SelfUpdatePlan(
        tag=stable.tag_name,
        asset_name=asset.name,
        zip_path=zip_path,
        temp_dir=temp,
        report=report,
    )
