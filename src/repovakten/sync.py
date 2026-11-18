"""Synkning av bevakade GitHub-konton.

Synken läser ENBART metadata (repon och releaser) och skriver aldrig
programmets filer – att ett repo dyker upp i katalogen innebär aldrig att
något installeras.

Synk sker: vid appstart, var 15:e minut medan appen är öppen
(:data:`SYNC_INTERVAL_SECONDS`) samt när användaren trycker på "Synka nu"
(det senare ligger i GUI-lagret).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .errors import GitHubApiError, RepovaktenError
from .github import GitHubClient
from .models import utcnow_iso
from .store import Store

SYNC_INTERVAL_SECONDS = 15 * 60  # 15 minuter


@dataclass
class SyncReport:
    started_at: str
    finished_at: str = ""
    synced_accounts: list[str] = field(default_factory=list)
    failed_accounts: dict[str, str] = field(default_factory=dict)
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    marked_missing: list[str] = field(default_factory=list)
    releases_fetched: int = 0
    release_errors: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.failed_accounts and not self.release_errors

    def summary_swedish(self) -> str:
        parts = [
            f"Konton som synkats: {', '.join(self.synced_accounts) or 'inga'}",
            f"Nya repon: {len(self.added)}",
            f"Uppdaterade repon: {len(self.updated)}",
        ]
        if self.marked_missing:
            parts.append(f"Försvunna ur synken: {len(self.marked_missing)}")
        if self.failed_accounts:
            parts.append(f"Konton som misslyckades: {len(self.failed_accounts)}")
        if self.release_errors:
            parts.append(f"Releasehämtning misslyckades: {len(self.release_errors)}")
        return " · ".join(parts)


def sync_accounts(store: Store, client: GitHubClient, *, now: str | None = None) -> SyncReport:
    """Hämta om alla bevakade konton och slå ihop resultatet med katalogen.

    * Nya publika repon läggs till automatiskt i katalogen.
    * Befintliga poster uppdateras (namnbyte behåller ID – och därmed spärrar/installationer).
    * Repon som försvunnit ur en *lyckad* synk markeras som ``missing`` men
      raderas aldrig (installationsregister och spärrar bevaras).
    * Misslyckas ett konto hämtas det övriga som vanligt, och repot markeras
      INTE som försvunnet (det får inte tolkas som en radering/privatisering).
    """
    started = now or utcnow_iso()
    report = SyncReport(started_at=started)

    seen_ids: set[int] = set()
    synced_owners: set[str] = set()

    for account in store.accounts():
        try:
            repos = client.list_public_repos(account)
        except RepovaktenError as exc:
            report.failed_accounts[account] = str(exc)
            continue
        synced_owners.add(account.lower())
        report.synced_accounts.append(account)
        for repo in repos:
            if repo.private:
                continue  # bevaka endast publika repon
            _, created = store.upsert_repo(repo, seen_at=started)
            seen_ids.add(repo.id)
            (report.added if created else report.updated).append(repo.full_name)

    # Markera försvunna repon – men bara för konton vars synk lyckades.
    for entry in store.repo_entries():
        owner = entry.repo.owner.lower()
        if owner in synced_owners and entry.repo.id not in seen_ids:
            if store.mark_missing(entry.repo.id):
                report.marked_missing.append(entry.repo.full_name)

    # Hämta senaste releaser för de tillgängliga repona.
    for entry in store.repo_entries():
        if not entry.available or entry.repo.owner.lower() not in synced_owners:
            continue
        try:
            releases = client.list_releases(
                entry.repo.owner, entry.repo.name, repo_id=entry.repo.id
            )
        except GitHubApiError as exc:
            report.release_errors[entry.repo.full_name] = str(exc)
            continue
        store.set_releases(entry.repo.id, releases, fetched_at=utcnow_iso())
        report.releases_fetched += 1

    store.set_last_sync()
    report.finished_at = utcnow_iso()
    return report
