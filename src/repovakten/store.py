"""Lokalt, beständigt tillstånd för Repovakten.

Allt sparas i en JSON-fil (``state.json``) i en plattformsanpassad
konfigurationskatalog. Skrivningar är atomiska (temporär fil + ``os.replace``)
och den tidigare filen sparas som ``state.json.bak`` som reserv om
huvudfilen skulle bli skadad.

Nyckling: alla regler och installationer nycklas på GitHubs numeriska repo-ID,
så att de överlever namnbyten och synkar.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import warnings
from pathlib import Path

from .errors import StoreError
from .models import (
    BlockRule,
    CatalogEntry,
    GitHubRepo,
    InstallRecord,
    Release,
    validate_github_username,
    utcnow_iso,
)

STATE_VERSION = 1
STATE_FILENAME = "state.json"
BACKUP_SUFFIX = ".bak"


def default_state_dir() -> Path:
    override = os.environ.get("REPOVAKTEN_HOME")
    if override:
        return Path(override).expanduser()
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA")
        return (Path(base) if base else Path.home() / "AppData" / "Roaming") / "Repovakten"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Repovakten"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return (Path(xdg) if xdg else Path.home() / ".config") / "repovakten"


def default_state_path() -> Path:
    return default_state_dir() / STATE_FILENAME


class Store:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else default_state_path()
        self._data: dict | None = None

    # -------------------------------------------------------------- grund

    @property
    def backup_path(self) -> Path:
        return self.path.with_name(self.path.name + BACKUP_SUFFIX)

    def _fresh(self) -> dict:
        return {
            "version": STATE_VERSION,
            "accounts": [],
            "repos": {},
            "blocks": {},
            "installs": {},
            "last_sync_at": None,
        }

    def load(self, *, force: bool = False) -> None:
        if self._data is not None and not force:
            return
        if not self.path.exists():
            self._data = self._fresh()
            return
        try:
            self._data = self._read(self.path)
            return
        except StoreError as primary_error:
            if self.backup_path.exists():
                try:
                    self._data = self._read(self.backup_path)
                    warnings.warn(
                        f"Tillståndsfilen var skadad ({primary_error}); "
                        f"reserven {self.backup_path.name} användes.",
                        RuntimeWarning,
                        stacklevel=2,
                    )
                    return
                except StoreError:
                    pass
            raise primary_error

    def _read(self, path: Path) -> dict:
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise StoreError(f"{path} innehåller ogiltig JSON: {exc}") from exc
        except OSError as exc:
            raise StoreError(f"{path} kunde inte läsas: {exc}") from exc
        if not isinstance(data, dict):
            raise StoreError(f"{path} har oväntat format (expected JSON object).")
        version = data.get("version", STATE_VERSION)
        if int(version) > STATE_VERSION:
            raise StoreError(
                f"{path} är skapad av en nyare Repovakten (version {version}); "
                "uppdatera appen istället för att skriva över den."
            )
        for key in ("accounts", "repos", "blocks", "installs"):
            data.setdefault(key, {} if key != "accounts" else [])
        data.setdefault("last_sync_at", None)
        return data

    def save(self) -> None:
        self.load()
        assert self._data is not None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self._data, ensure_ascii=False, indent=2)
        tmp_path = self.path.with_name(self.path.name + ".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            if self.path.exists():
                shutil.copy2(self.path, self.backup_path)
            os.replace(tmp_path, self.path)
        except OSError as exc:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise StoreError(f"{self.path} kunde inte skrivas: {exc}") from exc

    def reload(self) -> None:
        self._data = None
        self.load()

    # ----------------------------------------------------------- konton

    def accounts(self) -> list[str]:
        self.load()
        assert self._data is not None
        return list(self._data["accounts"])

    def add_account(self, username: str) -> str:
        cleaned = validate_github_username(username)
        self.load()
        assert self._data is not None
        if cleaned.lower() not in (a.lower() for a in self._data["accounts"]):
            self._data["accounts"].append(cleaned)
            self._data["accounts"].sort(key=str.lower)
            self.save()
        return cleaned

    def remove_account(self, username: str) -> bool:
        """Ta bort ett konto från bevakningen. Repo-poster i katalogen,
        spärrar och installationer behålls (inget raderas av misstag)."""
        self.load()
        assert self._data is not None
        before = len(self._data["accounts"])
        self._data["accounts"] = [
            a for a in self._data["accounts"] if a.lower() != username.strip().lstrip("@").lower()
        ]
        if len(self._data["accounts"]) != before:
            self.save()
            return True
        return False

    # ------------------------------------------------------ katalog

    def _entries(self) -> dict:
        self.load()
        assert self._data is not None
        return self._data["repos"]

    def repo_entries(self) -> list[CatalogEntry]:
        entries = [CatalogEntry.from_dict(raw) for raw in self._entries().values()]
        return sorted(entries, key=lambda e: e.repo.full_name.lower())

    def get_entry(self, repo_id: int) -> CatalogEntry | None:
        raw = self._entries().get(str(repo_id))
        return CatalogEntry.from_dict(raw) if raw else None

    def upsert_repo(self, repo: GitHubRepo, *, seen_at: str | None = None) -> tuple[CatalogEntry, bool]:
        """Lägg till eller uppdatera ett repo i katalogen.

        Byter repot namn behålls katalogposten (repo-ID är konstant), liksom
        eventuella spärrar och installationer. Returnerar (entry, skapad).
        """
        seen_at = seen_at or utcnow_iso()
        entries = self._entries()
        key = str(repo.id)
        created = key not in entries
        if created:
            entry = CatalogEntry(
                repo=repo,
                first_seen_at=seen_at,
                last_seen_at=seen_at,
                sync_state="available",
            )
        else:
            old = CatalogEntry.from_dict(entries[key])
            entry = CatalogEntry(
                repo=repo,  # namnet kan ha bytts – ID:et är konstant
                first_seen_at=old.first_seen_at,
                last_seen_at=seen_at,
                sync_state="available",
                preserve_paths=old.preserve_paths,
                releases_fetched_at=old.releases_fetched_at,
                releases=old.releases,
            )
        entries[key] = entry.to_dict()
        self.save()
        return entry, created

    def mark_missing(self, repo_id: int) -> bool:
        entries = self._entries()
        key = str(repo_id)
        raw = entries.get(key)
        if not raw:
            return False
        entry = CatalogEntry.from_dict(raw)
        if entry.sync_state == "missing":
            return False
        entry.sync_state = "missing"
        entries[key] = entry.to_dict()
        self.save()
        return True

    def set_releases(
        self, repo_id: int, releases: list[Release], *, fetched_at: str | None = None
    ) -> None:
        entries = self._entries()
        key = str(repo_id)
        raw = entries.get(key)
        if not raw:
            return
        entry = CatalogEntry.from_dict(raw)
        # Nyckla alltid releaserna mot repo-ID:t som katalogen känner till.
        entry.releases = [
            Release(
                id=r.id,
                repo_id=repo_id,
                tag_name=r.tag_name,
                name=r.name,
                draft=r.draft,
                prerelease=r.prerelease,
                published_at=r.published_at,
                html_url=r.html_url,
                assets=r.assets,
            )
            for r in releases
        ]
        entry.releases_fetched_at = fetched_at or utcnow_iso()
        entries[key] = entry.to_dict()  # repon utan releaser sparas också
        self.save()

    def set_preserve_paths(self, repo_id: int, preserve_paths: list[str]) -> None:
        entries = self._entries()
        key = str(repo_id)
        raw = entries.get(key)
        if not raw:
            return
        entry = CatalogEntry.from_dict(raw)
        entry.preserve_paths = list(preserve_paths)
        entries[key] = entry.to_dict()
        self.save()

    # ------------------------------------------------------------ spärrar

    def set_block(self, rule: BlockRule) -> None:
        self.load()
        assert self._data is not None
        self._data["blocks"][str(rule.repo_id)] = rule.to_dict()
        self.save()

    def remove_block(self, repo_id: int) -> bool:
        self.load()
        assert self._data is not None
        existed = self._data["blocks"].pop(str(repo_id), None) is not None
        if existed:
            self.save()
        return existed

    def get_block(self, repo_id: int) -> BlockRule | None:
        self.load()
        assert self._data is not None
        raw = self._data["blocks"].get(str(repo_id))
        return BlockRule.from_dict(raw) if raw else None

    def list_blocks(self) -> list[BlockRule]:
        self.load()
        assert self._data is not None
        return [BlockRule.from_dict(r) for r in self._data["blocks"].values()]

    # ------------------------------------------------------ installationer

    def get_install(self, repo_id: int) -> InstallRecord | None:
        self.load()
        assert self._data is not None
        raw = self._data["installs"].get(str(repo_id))
        return InstallRecord.from_dict(raw) if raw else None

    def set_install(self, record: InstallRecord) -> None:
        self.load()
        assert self._data is not None
        self._data["installs"][str(record.repo_id)] = record.to_dict()
        self.save()

    def list_installs(self) -> list[InstallRecord]:
        self.load()
        assert self._data is not None
        records = [InstallRecord.from_dict(r) for r in self._data["installs"].values()]
        return sorted(records, key=lambda r: r.repo_full_name.lower())

    # ------------------------------------------------------------- synk

    def get_last_sync(self) -> str | None:
        self.load()
        assert self._data is not None
        return self._data.get("last_sync_at")

    def set_last_sync(self, moment: str | None = None) -> None:
        self.load()
        assert self._data is not None
        self._data["last_sync_at"] = moment or utcnow_iso()
        self.save()
