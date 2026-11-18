"""Repovakten – felhierarki.

Alla fel som Repovakten själv genererar ärver från :class:`RepovaktenError`,
så att gränssnittet enkelt kan fånga allt utan att svälja oväntade buggar.
"""
from __future__ import annotations


class RepovaktenError(Exception):
    """Basklass för fel som hört till Repovakten."""


class GitHubApiError(RepovaktenError):
    """GitHub API svarade med ett fel eller kunde inte nås."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        reset_at: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.reset_at = reset_at


class RateLimitError(GitHubApiError):
    """GitHubs hastighetsgräns är nådd. ``reset_at`` anger när gränsen återställs (ISO-tid)."""


class AuthenticationError(GitHubApiError):
    """Autentisering misslyckades (ogiltig eller utgången token)."""


class NotFoundError(GitHubApiError):
    """Resursen hittades inte (t.ex. okänt repo eller användare)."""


class StoreError(RepovaktenError):
    """Det lokala tillståndsfilen (state.json) kunde inte läsas eller skrivas."""


class InstallationBlockedError(RepovaktenError):
    """Repot är spärrat av administratör och får varken installeras eller uppdateras."""

    def __init__(self, repo_id: int, reason: str = "") -> None:
        self.repo_id = repo_id
        self.reason = reason
        message = f"Installationen är spärrad av administratör (repo-ID {repo_id})."
        if reason:
            message += f" Orsak: {reason}"
        message += " En befintlig installation påverkas inte."
        super().__init__(message)


class ReleaseError(RepovaktenError):
    """Releasen är oanvändbar (saknas, fel format o.s.v.)."""


class UnsafeArchiveError(RepovaktenError):
    """ZIP-paketet är osäkert eller ogiltigt och får därför inte användas."""


class VersionParseError(RepovaktenError, ValueError):
    """Versionstaggen kunde inte tolkas."""
