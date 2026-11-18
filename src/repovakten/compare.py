"""Filjämförelse mellan en release och den lokalt installerade kopian.

Varje programfil i releasen hashas med SHA-256 och jämförs med motsvarande
fil på disk. Även när båda parterna heter t.ex. ``v1.2.0`` redovisas exakt
*vilka* filer som skiljer sig – inte bara att något gör det.

Kategorier:
* **nya** – finns i releasen, saknas lokalt (läggs till vid installation)
* **ändrade** – finns i båda men SHA-256 skiljer sig (ersätts)
* **saknade** – finns i hanterarens installationsmanifest men saknas på disk
  (installationen är skadad/manipulerad)
* **utgående** – finns lokalt (utanför bevarade sökvägar) men inte i
  releasen (försvinner först efter uttryckligt godkännande, med backup)

Bevarade sökvägar (t.ex. ``storage/`` för användardata) exkluderas på båda
sidor och rapporteras aldrig.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable, Mapping

from .hashing import hash_tree, hash_zip, normalize_relpath, is_preserved
from .models import DEFAULT_PRESERVE_PATHS


class DifferenceKind(str, Enum):
    NEW = "ny"
    CHANGED = "andrad"
    MISSING = "saknad"
    REMOVED = "utgaende"


@dataclass(frozen=True)
class FileDifference:
    path: str
    kind: DifferenceKind
    release_sha256: str | None = None
    local_sha256: str | None = None


@dataclass
class FileReport:
    differences: list[FileDifference] = field(default_factory=list)
    identical_files: int = 0
    preserved_in_release: int = 0
    preserved_local_only: int = 0
    preserved: tuple[str, ...] = DEFAULT_PRESERVE_PATHS

    # ------------------------------------------------------------- åtkomst

    def by_kind(self, kind: DifferenceKind) -> list[FileDifference]:
        return [d for d in self.differences if d.kind is kind]

    @property
    def changed(self) -> list[FileDifference]:
        return self.by_kind(DifferenceKind.CHANGED)

    @property
    def new(self) -> list[FileDifference]:
        return self.by_kind(DifferenceKind.NEW)

    @property
    def missing(self) -> list[FileDifference]:
        return self.by_kind(DifferenceKind.MISSING)

    @property
    def removed(self) -> list[FileDifference]:
        return self.by_kind(DifferenceKind.REMOVED)

    def counts(self) -> dict[str, int]:
        return {
            "ny": len(self.new),
            "andrad": len(self.changed),
            "saknad": len(self.missing),
            "utgaende": len(self.removed),
            "identisk": self.identical_files,
        }

    @property
    def has_changes(self) -> bool:
        return bool(self.differences)

    @property
    def ok(self) -> bool:
        return not self.has_changes

    # --------------------------------------------------------- presentation

    def format_swedish(self) -> str:
        lines = ["Filrapport", "=========="]
        labels = [
            (DifferenceKind.CHANGED, "Ändrade filer"),
            (DifferenceKind.NEW, "Nya filer"),
            (DifferenceKind.MISSING, "Saknade filer"),
            (DifferenceKind.REMOVED, "Utgående filer"),
        ]
        for kind, label in labels:
            items = self.by_kind(kind)
            lines.append(f"{label} ({len(items)}):")
            for item in items:
                if kind is DifferenceKind.CHANGED:
                    lines.append(
                        f"  {item.path}  ({(item.local_sha256 or '')[:8]}… → {(item.release_sha256 or '')[:8]}…)"
                    )
                else:
                    lines.append(f"  {item.path}")
        lines.append(f"Oförändrade filer: {self.identical_files}")
        if self.preserved:
            lines.append(f"Bevarade sökvägar (rörs aldrig): {', '.join(self.preserved)}")
        return "\n".join(lines)


# ---------------------------------------------------------------- jämförelse

def normalize_mapping(mapping: Mapping[str, str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_path, digest in mapping.items():
        result[normalize_relpath(raw_path)] = digest.lower()
    return result


def compare_files(
    release_files: Mapping[str, str],
    local_files: Mapping[str, str],
    *,
    manifest_files: Mapping[str, str] | None = None,
    preserved: Iterable[str] = DEFAULT_PRESERVE_PATHS,
) -> FileReport:
    """Jämför ``{relpath: sha256}`` för release och lokal kopia.

    ``manifest_files`` (valfritt) är den installerade kopians förväntade
    filer (hanterarens eget register) och används för att hitta filer som
    *saknas på disk*. Releasen hashas inte om, utan skickas in färdigförpackad.
    """
    preserved_tuple = tuple(preserved)
    release = {r: h for r, h in normalize_mapping(release_files).items() if not is_preserved(r, preserved_tuple)}
    local = {r: h for r, h in normalize_mapping(local_files).items() if not is_preserved(r, preserved_tuple)}
    manifest = (
        {r: h for r, h in normalize_mapping(manifest_files).items() if not is_preserved(r, preserved_tuple)}
        if manifest_files
        else {}
    )

    differences: list[FileDifference] = []
    identical = 0

    all_paths = set(release) | set(local) | set(manifest)
    for path in sorted(all_paths):
        rel_hash = release.get(path)
        loc_hash = local.get(path)
        in_manifest = path in manifest

        if rel_hash is not None and loc_hash is not None:
            if rel_hash == loc_hash:
                identical += 1
            else:
                differences.append(FileDifference(path, DifferenceKind.CHANGED, rel_hash, loc_hash))
            continue
        if rel_hash is None and loc_hash is not None:
            # Lokal fil utan motsvarighet i releasen: utgående (försvinner vid uppdatering).
            differences.append(FileDifference(path, DifferenceKind.REMOVED, None, loc_hash))
            continue
        if rel_hash is not None and loc_hash is None:
            if in_manifest:
                # Vi förväntade oss filen på disk, men den är borta.
                differences.append(FileDifference(path, DifferenceKind.MISSING, rel_hash, None))
            else:
                differences.append(FileDifference(path, DifferenceKind.NEW, rel_hash, None))
            continue
        # Finns bara i manifestet (varken release eller disk): saknad.
        differences.append(FileDifference(path, DifferenceKind.MISSING, None, None))

    return FileReport(
        differences=differences,
        identical_files=identical,
        preserved=preserved_tuple,
    )


def compare_install(
    zip_path: Path,
    install_dir: Path | None,
    *,
    manifest_files: Mapping[str, str] | None = None,
    preserved: Iterable[str] = DEFAULT_PRESERVE_PATHS,
) -> FileReport:
    """Jämför en release-ZIP med den installerade kopian på disk.

    ``install_dir=None`` (eller en icke-existerande katalog) innebär att inget
    är installerat – allt räknas som nytt.
    """
    release_files = hash_zip(zip_path, preserved)
    install_dir = Path(install_dir) if install_dir else None
    if install_dir and install_dir.is_dir():
        local_files = hash_tree(install_dir, preserved)
    else:
        local_files = {}
    report = compare_files(release_files, local_files, manifest_files=manifest_files, preserved=preserved)
    return report
