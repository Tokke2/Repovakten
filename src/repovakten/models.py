"""Repovakten – gemensamma datamodeller.

Alla modeller är enkla dataclasses som serialiseras explicit till/från
JSON i :mod:`repovakten.store`. GitHubs egna ISO-tidsstämplar sparas som
strängar så att de överlever en tur genom tillståndsfilen oförändrade.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

GITHUB_USERNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")

#: Katalogprefix som bevaras vid installation/uppdatering (användardata).
DEFAULT_PRESERVE_PATHS: tuple[str, ...] = ("storage/",)


def utcnow_iso() -> str:
    """Aktuell UTC-tid som ``2026-11-18T10:30:00Z``."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_github_time(value: str | None) -> datetime | None:
    """Tolka GitHubs tidsstämplar (``...Z`` eller med offset) till datetime."""
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def validate_github_username(name: str) -> str:
    """Normalisera (``@namn`` → ``namn``) och validera ett GitHub-användarnamn."""
    cleaned = name.strip().lstrip("@")
    if not GITHUB_USERNAME_RE.match(cleaned):
        raise ValueError(f"Ogiltigt GitHub-användarnamn: {name!r}")
    return cleaned


@dataclass(frozen=True)
class GitHubRepo:
    """Ett publikt repo som bevakas. ``id`` är GitHubs numeriska repo-ID och
    är stabilt även om repot byter namn – spärrar och installationer nycklas på det."""

    id: int
    name: str
    full_name: str
    owner: str
    html_url: str
    language: str | None = None
    description: str | None = None
    private: bool = False
    fork: bool = False
    archived: bool = False
    default_branch: str | None = None
    pushed_at: str | None = None
    updated_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "full_name": self.full_name,
            "owner": self.owner,
            "html_url": self.html_url,
            "language": self.language,
            "description": self.description,
            "private": self.private,
            "fork": self.fork,
            "archived": self.archived,
            "default_branch": self.default_branch,
            "pushed_at": self.pushed_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GitHubRepo":
        return cls(
            id=int(data["id"]),
            name=str(data["name"]),
            full_name=str(data["full_name"]),
            owner=str(data["owner"]),
            html_url=str(data.get("html_url") or ""),
            language=data.get("language"),
            description=data.get("description"),
            private=bool(data.get("private", False)),
            fork=bool(data.get("fork", False)),
            archived=bool(data.get("archived", False)),
            default_branch=data.get("default_branch"),
            pushed_at=data.get("pushed_at"),
            updated_at=data.get("updated_at"),
        )


@dataclass(frozen=True)
class ReleaseAsset:
    """En uppladdad tillgång till en release (inte GitHubs autogenererade källkodsarkiv)."""

    id: int
    name: str
    size: int
    download_url: str
    content_type: str | None = None

    @property
    def is_zip(self) -> bool:
        return self.name.lower().endswith(".zip")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "size": self.size,
            "download_url": self.download_url,
            "content_type": self.content_type,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ReleaseAsset":
        return cls(
            id=int(data["id"]),
            name=str(data["name"]),
            size=int(data.get("size") or 0),
            download_url=str(data.get("download_url") or ""),
            content_type=data.get("content_type"),
        )


@dataclass(frozen=True)
class Release:
    id: int
    repo_id: int
    tag_name: str
    name: str | None = None
    draft: bool = False
    prerelease: bool = False
    published_at: str | None = None
    html_url: str | None = None
    assets: tuple[ReleaseAsset, ...] = ()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "repo_id": self.repo_id,
            "tag_name": self.tag_name,
            "name": self.name,
            "draft": self.draft,
            "prerelease": self.prerelease,
            "published_at": self.published_at,
            "html_url": self.html_url,
            "assets": [asset.to_dict() for asset in self.assets],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Release":
        assets = tuple(ReleaseAsset.from_dict(a) for a in data.get("assets", []))
        return cls(
            id=int(data["id"]),
            repo_id=int(data["repo_id"]),
            tag_name=str(data["tag_name"]),
            name=data.get("name"),
            draft=bool(data.get("draft", False)),
            prerelease=bool(data.get("prerelease", False)),
            published_at=data.get("published_at"),
            html_url=data.get("html_url"),
            assets=assets,
        )


@dataclass(frozen=True)
class BlockRule:
    """Adminspärr för ett repo, nycklad på GitHubs repo-ID.

    Spärren gäller install och uppdatering men **raderar inte** en redan
    installerad kopia och påverkar inte användarens data.
    """

    repo_id: int
    reason: str = ""
    blocked_at: str = ""

    def to_dict(self) -> dict:
        return {"repo_id": self.repo_id, "reason": self.reason, "blocked_at": self.blocked_at}

    @classmethod
    def from_dict(cls, data: dict) -> "BlockRule":
        return cls(
            repo_id=int(data["repo_id"]),
            reason=str(data.get("reason") or ""),
            blocked_at=str(data.get("blocked_at") or ""),
        )


@dataclass
class InstallRecord:
    """Hanterarens lokala kopia: vilken release som installerats och vilka filer
    den består av (relativ sökväg → SHA-256). Används för filjämförelser och
    för att upptäcka saknade filer."""

    repo_id: int
    repo_full_name: str
    installed_tag: str
    install_dir: str
    installed_at: str
    updated_at: str
    files: dict[str, str] = field(default_factory=dict)
    preserve_paths: list[str] = field(default_factory=lambda: list(DEFAULT_PRESERVE_PATHS))

    def to_dict(self) -> dict:
        return {
            "repo_id": self.repo_id,
            "repo_full_name": self.repo_full_name,
            "installed_tag": self.installed_tag,
            "install_dir": self.install_dir,
            "installed_at": self.installed_at,
            "updated_at": self.updated_at,
            "files": dict(self.files),
            "preserve_paths": list(self.preserve_paths),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InstallRecord":
        return cls(
            repo_id=int(data["repo_id"]),
            repo_full_name=str(data["repo_full_name"]),
            installed_tag=str(data["installed_tag"]),
            install_dir=str(data["install_dir"]),
            installed_at=str(data["installed_at"]),
            updated_at=str(data["updated_at"]),
            files={str(k): str(v) for k, v in (data.get("files") or {}).items()},
            preserve_paths=list(data.get("preserve_paths") or DEFAULT_PRESERVE_PATHS),
        )


@dataclass
class CatalogEntry:
    """Ett repo så som det ser ut i katalogen: repot självt, synkstatus,
    cachade releaser och vilka sökvägar som ska bevaras vid uppdatering."""

    repo: GitHubRepo
    first_seen_at: str
    last_seen_at: str
    sync_state: str = "available"  # "available" | "missing" (försvunnet ur synken)
    preserve_paths: list[str] = field(default_factory=lambda: list(DEFAULT_PRESERVE_PATHS))
    releases_fetched_at: str | None = None
    releases: list[Release] = field(default_factory=list)

    @property
    def available(self) -> bool:
        return self.sync_state == "available"

    def to_dict(self) -> dict:
        return {
            "repo": self.repo.to_dict(),
            "first_seen_at": self.first_seen_at,
            "last_seen_at": self.last_seen_at,
            "sync_state": self.sync_state,
            "preserve_paths": list(self.preserve_paths),
            "releases_fetched_at": self.releases_fetched_at,
            "releases": [release.to_dict() for release in self.releases],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CatalogEntry":
        return cls(
            repo=GitHubRepo.from_dict(data["repo"]),
            first_seen_at=str(data["first_seen_at"]),
            last_seen_at=str(data["last_seen_at"]),
            sync_state=str(data.get("sync_state") or "available"),
            preserve_paths=list(data.get("preserve_paths") or DEFAULT_PRESERVE_PATHS),
            releases_fetched_at=data.get("releases_fetched_at"),
            releases=[Release.from_dict(r) for r in data.get("releases", [])],
        )
