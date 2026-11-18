"""Katalog-vy: det gränssnittet behöver för att visa *vad* en app är.

Kombinerar katalogen (repon), cachade releaser, installationer och spärrar
till en :class:`CatalogRow` per repo. Innehåller ingen GUI-kod men all
logik för att avgöra vad som ska visas och om installation är tillåten.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .blocking import is_blocked
from .models import DEFAULT_PRESERVE_PATHS, GitHubRepo
from .releases import installable_assets, select_latest_any, select_latest_stable
from .store import Store


class InstallStatus(str, Enum):
    READY = "ready"  # installation möjlig och tillåten
    BLOCKED = "blocked"  # spärrad av administratör
    NO_RELEASE = "no_release"  # repot har inga releaser – visas ändå
    NO_STABLE_RELEASE = "no_stable_release"  # bara pre-releaser/utkast
    NO_INSTALLABLE_ASSET = "no_installable_asset"  # stabil release utan ZIP-tillgång
    MISSING = "missing"  # repo försvunnet ur synken


@dataclass(frozen=True)
class CatalogRow:
    repo: GitHubRepo
    status: InstallStatus
    install_allowed: bool
    sync_state: str
    installed_version: str | None
    latest_stable_tag: str | None
    latest_any_tag: str | None
    stable_published_at: str | None
    installable_assets: int
    preserve_paths: tuple[str, ...] = field(default_factory=lambda: DEFAULT_PRESERVE_PATHS)

    @property
    def can_install(self) -> bool:
        return self.status is InstallStatus.READY and self.install_allowed

    @property
    def has_update_candidate(self) -> bool:
        return (
            self.installed_version is not None
            and self.latest_stable_tag is not None
            and self.installed_version != self.latest_stable_tag
        )


def build_catalog_rows(store: Store) -> list[CatalogRow]:
    rows: list[CatalogRow] = []
    for entry in store.repo_entries():
        repo = entry.repo
        blocked = is_blocked(store, repo.id)
        install = store.get_install(repo.id)

        stable = select_latest_stable(entry.releases)
        any_rel = select_latest_any(entry.releases)
        latest_any = any_rel.tag_name if any_rel else None

        n_installable = len(installable_assets(stable)) if stable else 0

        # Ordning: försvunnet > spärrat > release-status.
        if not entry.available:
            status = InstallStatus.MISSING
        elif blocked:
            status = InstallStatus.BLOCKED
        elif not entry.releases:
            status = InstallStatus.NO_RELEASE
        elif stable is None:
            status = InstallStatus.NO_STABLE_RELEASE
        elif n_installable == 0:
            status = InstallStatus.NO_INSTALLABLE_ASSET
        else:
            status = InstallStatus.READY

        rows.append(
            CatalogRow(
                repo=repo,
                status=status,
                install_allowed=not blocked,
                sync_state=entry.sync_state,
                installed_version=install.installed_tag if install else None,
                latest_stable_tag=stable.tag_name if stable else None,
                latest_any_tag=latest_any,
                stable_published_at=stable.published_at if stable else None,
                installable_assets=n_installable,
                preserve_paths=tuple(entry.preserve_paths),
            )
        )
    return rows


def updates_for_installed_apps(store: Store) -> list[CatalogRow]:
    """Installerade appar som har en nyare, installerbar stabil release.

    Används av uppdateringskontrollen (menyn Hjälp → Sök uppdateringar):
    när Repovakten kollar efter nyare kod kollas också de installerade
    apparna. Spärrade appar och releaser utan ZIP-paket hoppas över –
    de kan ändå inte uppdateras.
    """
    return [
        row
        for row in build_catalog_rows(store)
        if row.has_update_candidate and row.install_allowed and row.installable_assets > 0
    ]
