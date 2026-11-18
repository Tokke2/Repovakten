"""Tunn klient för GitHubs REST-API.

Endast den publika läs-API:en används, och tokens läses enbart från
miljövariabler (``REPOVAKTEN_GITHUB_TOKEN`` eller ``GITHUB_TOKEN``) – aldrig
från filer som appen sparar. Transporten kan bytas ut i tester.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from . import __version__
from .errors import (
    AuthenticationError,
    GitHubApiError,
    NotFoundError,
    RateLimitError,
)
from .models import GitHubRepo, Release, ReleaseAsset, validate_github_username

API_BASE = "https://api.github.com"
MAX_BODY_BYTES = 32 * 1024 * 1024  # 32 MiB tak för API-svar
MAX_PAGES = 20  # skyddsräcke mot orimliga listor


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


class Transport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
    ) -> HttpResponse: ...


class UrllibTransport:
    def __init__(self, timeout: float = 30.0, max_body_bytes: int = MAX_BODY_BYTES) -> None:
        self.timeout = timeout
        self.max_body_bytes = max_body_bytes

    def request(self, method: str, url: str, headers: Mapping[str, str]) -> HttpResponse:
        request = urllib.request.Request(url, method=method, headers=dict(headers))
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read(self.max_body_bytes + 1)
                if len(body) > self.max_body_bytes:
                    raise GitHubApiError("GitHubs svar är större än tillåtet.")
                return HttpResponse(
                    status=response.status,
                    headers={k.lower(): v for k, v in response.headers.items()},
                    body=body,
                )
        except urllib.error.HTTPError as exc:
            body = exc.read(self.max_body_bytes + 1) if exc.fp else b""
            return HttpResponse(
                status=exc.code,
                headers={k.lower(): v for k, v in (exc.headers or {}).items()},
                body=body[: self.max_body_bytes],
            )
        except urllib.error.URLError as exc:
            raise GitHubApiError(f"Nätverksfel mot GitHub: {exc.reason}") from exc


def _bearer_from_env() -> str | None:
    return os.environ.get("REPOVAKTEN_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN") or None


def _snippet(body: bytes, limit: int = 300) -> str:
    text = body[:limit].decode("utf-8", errors="replace").strip()
    return text if text else "(tomt svar)"


class GitHubClient:
    """Läser publika repon och releaser från GitHub."""

    def __init__(
        self,
        transport: Transport | None = None,
        *,
        token: str | None = None,
        api_base: str = API_BASE,
    ) -> None:
        self._transport = transport or UrllibTransport()
        self._token = token if token is not None else _bearer_from_env()
        self._api_base = api_base.rstrip("/")

    # ------------------------------------------------------------------ intern

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": f"Repovakten/{__version__}",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _get_json(self, path: str) -> Any:
        url = f"{self._api_base}{path}"
        response = self._transport.request("GET", url, self._headers())
        return self._parse_response(response, url)

    def _parse_response(self, response: HttpResponse, url: str) -> Any:
        headers = {k.lower(): v for k, v in response.headers.items()}
        if response.status == 401:
            raise AuthenticationError(
                "GitHub avvisade inloggningen (401). Kontrollera REPOVAKTEN_GITHUB_TOKEN.",
                status_code=401,
            )
        if response.status == 404:
            raise NotFoundError(
                f"Hittades inte hos GitHub: {url}", status_code=404
            )
        remaining = headers.get("x-ratelimit-remaining", "")
        body_text = response.body.decode("utf-8", errors="replace").lower()
        if response.status in (403, 429) and (
            remaining == "0" or "rate limit" in body_text or response.status == 429
        ):
            reset_at = self._rate_limit_reset(headers)
            message = "GitHubs hastighetsgräns är nådd."
            if reset_at:
                message += f" Återställs {reset_at}."
            raise RateLimitError(message, status_code=response.status, reset_at=reset_at)
        if response.status >= 400:
            raise GitHubApiError(
                f"GitHub svarade med {response.status}: {_snippet(response.body)}",
                status_code=response.status,
            )
        try:
            return json.loads(response.body)
        except json.JSONDecodeError as exc:
            raise GitHubApiError(
                f"GitHubs svar kunde inte tolkas som JSON: {exc}", status_code=response.status
            ) from exc

    @staticmethod
    def _rate_limit_reset(headers: Mapping[str, str]) -> str | None:
        raw = headers.get("x-ratelimit-reset")
        if not raw:
            return None
        try:
            from datetime import datetime, timezone

            moment = datetime.fromtimestamp(int(raw), tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return raw
        return moment.replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def _get_paginated(self, path: str, *, per_page: int, max_pages: int) -> list[dict]:
        items: list[dict] = []
        separator = "&" if "?" in path else "?"
        for page in range(1, max_pages + 1):
            url = f"{path}{separator}per_page={per_page}&page={page}"
            data = self._get_json(url)
            if not isinstance(data, list):
                raise GitHubApiError("Oväntat svar från GitHub: förväntade en lista.")
            items.extend(data)
            if len(data) < per_page:
                break
        return items

    # ------------------------------------------------------------------ publikt

    def list_public_repos(self, username: str, *, per_page: int = 100) -> list[GitHubRepo]:
        """Alla publika repon för ``username`` (privat information filtreras bort)."""
        login = validate_github_username(username)
        quoted = urllib.parse.quote(login, safe="")
        per_page = max(1, min(int(per_page), 100))
        raw_repos = self._get_paginated(
            f"/users/{quoted}/repos?type=owner&sort=created&direction=desc",
            per_page=per_page,
            max_pages=MAX_PAGES,
        )
        repos: list[GitHubRepo] = []
        for item in raw_repos:
            if item.get("private", False):
                continue  # bevaka endast publika repon
            owner = item.get("owner") or {}
            try:
                repo = GitHubRepo(
                    id=int(item["id"]),
                    name=str(item["name"]),
                    full_name=str(item["full_name"]),
                    owner=str(owner.get("login") or login),
                    html_url=str(item.get("html_url") or ""),
                    language=item.get("language"),
                    description=item.get("description"),
                    private=bool(item.get("private", False)),
                    fork=bool(item.get("fork", False)),
                    archived=bool(item.get("archived", False)),
                    default_branch=item.get("default_branch"),
                    pushed_at=item.get("pushed_at"),
                    updated_at=item.get("updated_at"),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise GitHubApiError(f"Oväntat repo-format från GitHub: {exc}") from exc
            repos.append(repo)
        return repos

    def list_releases(
        self, owner: str, repo: str, *, repo_id: int = 0, per_page: int = 100
    ) -> list[Release]:
        """Alla releaser (utkast markerade) för repot ``owner/repo``.

        ``repo_id`` sätts när det är känt så att releaserna kan nycklas mot katalogen.
        """
        quoted_owner = urllib.parse.quote(owner, safe="")
        quoted_repo = urllib.parse.quote(repo, safe="")
        per_page = max(1, min(int(per_page), 100))
        raw_releases = self._get_paginated(
            f"/repos/{quoted_owner}/{quoted_repo}/releases",
            per_page=per_page,
            max_pages=10,
        )
        releases: list[Release] = []
        for item in raw_releases:
            if not item.get("tag_name"):
                continue  # release utan tagg kan inte installeras ändå
            assets = tuple(
                ReleaseAsset(
                    id=int(a["id"]),
                    name=str(a["name"]),
                    size=int(a.get("size") or 0),
                    download_url=str(a.get("browser_download_url") or ""),
                    content_type=a.get("content_type"),
                )
                for a in item.get("assets", []) or []
                if a.get("id") is not None and a.get("name")
            )
            releases.append(
                Release(
                    id=int(item["id"]),
                    repo_id=repo_id,
                    tag_name=str(item["tag_name"]),
                    name=item.get("name"),
                    draft=bool(item.get("draft", False)),
                    prerelease=bool(item.get("prerelease", False)),
                    published_at=item.get("published_at") or item.get("created_at"),
                    html_url=item.get("html_url"),
                    assets=assets,
                )
            )
        return releases

