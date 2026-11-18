"""SHA-256-hashning och säker ZIP-hantering.

Funktionerna här delar samma vägnormalisering så att jämförelsen blir
robust oavsett om paketet skapats på Windows, macOS eller Linux:

* ``\\`` normaliseras till ``/``.
* Absoluta sökvägar, enhetsbokstäver, ``..`` och NUL-byte avvisas (zip-slip).
* Efter normalisering avvisas dubbletter (t.ex. ``./x`` och ``x``).
* Bevarade sökvägar (användardata, t.ex. ``storage/``) hoppas alltid över.
* En gemensam rotkatalog (t.ex. ``MyApp-1.2.0/…``) strippas, så att
  hashning och uppackning använder samma sökvägsnamnrum.
"""
from __future__ import annotations

import hashlib
import os
import posixpath
import re
import zipfile
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Iterable

from .errors import UnsafeArchiveError

CHUNK_SIZE = 1024 * 1024  # 1 MiB

# Skyddsgränser för nedladdade paket.
MAX_MEMBERS = 20_000
MAX_UNCOMPRESSED_BYTES = 4 * 1024**3  # 4 GiB


def sha256_stream(stream: BinaryIO) -> str:
    digest = hashlib.sha256()
    while True:
        chunk = stream.read(CHUNK_SIZE)
        if not chunk:
            break
        digest.update(chunk)
    return digest.hexdigest()


def sha256_file(path: Path) -> str:
    with open(path, "rb") as handle:
        return sha256_stream(handle)


def normalize_relpath(path: str) -> str:
    """Normalisera en relativ sökväg till posix-form.

    Kastar :class:`UnsafeArchiveError` för absolut sökväg, enhetsbokstav,
    ``..`` som pekar utanför roten, eller NUL-byte.
    """
    if not path or not path.strip():
        raise UnsafeArchiveError("Tom sökväg i arkivet.")
    if "\x00" in path:
        raise UnsafeArchiveError("NUL-byte i sökväg.")
    text = path.replace("\\", "/")
    if re.match(r"^[A-Za-z]:(/|$)", text):
        raise UnsafeArchiveError(f"Enhetsbokstav i sökväg: {path!r}")
    text = posixpath.normpath(text)
    if text == ".":
        raise UnsafeArchiveError(f"Ogiltig sökväg: {path!r}")
    if text.startswith("/"):
        raise UnsafeArchiveError(f"Absolut sökväg: {path!r}")
    if text == ".." or text.startswith("../"):
        raise UnsafeArchiveError(f"Sökväg utanför installationskatalogen: {path!r}")
    return text


def is_preserved(relpath: str, preserved: Iterable[str]) -> bool:
    """Sant om ``relpath`` ligger under en bevarad sökväg."""
    for raw in preserved:
        item = raw.strip()
        if not item:
            continue
        is_dir = item.endswith(("/", "\\"))
        try:
            normalized = normalize_relpath(item).rstrip("/")
        except UnsafeArchiveError:
            continue
        if is_dir:
            if relpath == normalized or relpath.startswith(normalized + "/"):
                return True
        elif relpath == normalized:
            return True
    return False


def iter_tree(root: Path, preserved: Iterable[str] = ()) -> Iterable[tuple[str, Path]]:
    """Gå igenom ``root`` och ge ``(relpath, fil)`` för alla filer (sorterade).

    Bevarade kataloger skippas helt (de genomsöks inte ens).
    """
    root = Path(root)
    if not root.is_dir():
        raise NotADirectoryError(f"Ingen katalog: {root}")
    prefix_len = len(str(root)) + 1
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        base = Path(dirpath)
        kept: list[str] = []
        for dirname in dirnames:
            rel_dir = (base / dirname).relative_to(root).as_posix()
            if is_preserved(rel_dir + "/", preserved) or is_preserved(rel_dir, preserved):
                continue  # användardata – sök inte igenom
            kept.append(dirname)
        dirnames[:] = kept
        for filename in sorted(filenames):
            full = base / filename
            rel = full.relative_to(root).as_posix()
            if is_preserved(rel, preserved):
                continue
            yield rel, full


def hash_tree(root: Path, preserved: Iterable[str] = ()) -> dict[str, str]:
    """Hasha alla filer under ``root`` (utom bevarade) till {relpath: sha256}."""
    return {rel: sha256_file(path) for rel, path in iter_tree(root, preserved)}


_VERSIONED_NAME = re.compile(r"[-_. ]v?\d[\d.]*$")
_VERSION_ONLY_NAME = re.compile(r"v?\d[\d.]*")


def _looks_versioned(name: str) -> bool:
    """Sant om namnet ser ut som en versionsmapp (t.ex. ``MinApp-2.1.0``)."""
    return bool(_VERSIONED_NAME.search(name) or _VERSION_ONLY_NAME.fullmatch(name))


def common_root_prefix(paths: Iterable[str]) -> str | None:
    """Returnera den rotkatalog som ska strippas, om någon.

    Reglerna är desamma för hashning och uppackning:

    * Alla filer under samma toppnivåkatalog och ingen direkt i roten –
      katalognamnet strippas (t.ex. ``MyApp-1.2.0``).
    * Arkiv som blandar **en** versionslik toppnivåkatalog (t.ex.
      ``MinApp-2.1.0``) med lösa filer direkt i roten – katalognamnet
      strippas för sitt innehåll medan de lösa filerna behålls. Då landar
      innehållet rent utan versionsmappar. Riktiga innehållskataloger
      (``lib/``, ``ui/``) strippas aldrig på det här sättet.
    * Annars (flera toppnivåkataloger, icke-versionslik katalog blandad med
      lösa filer, eller en lös fil med samma namn som katalogen) strippas
      ingenting.
    """
    entries = [rel for rel in paths if rel]
    if not entries:
        return None
    first_components = {rel.split("/", 1)[0] for rel in entries}
    if len(first_components) == 1 and all("/" in rel for rel in entries):
        return next(iter(first_components))
    dir_names = {rel.split("/", 1)[0] for rel in entries if "/" in rel}
    loose_names = {rel for rel in entries if "/" not in rel}
    if len(dir_names) == 1 and not (dir_names & loose_names):
        (name,) = dir_names
        if _looks_versioned(name):
            return name
    return None


def zip_entries(
    zip_path: Path,
    preserved: Iterable[str],
    *,
    max_members: int = MAX_MEMBERS,
    max_uncompressed: int = MAX_UNCOMPRESSED_BYTES,
) -> list[tuple[str, zipfile.ZipInfo]]:
    """Validera hela arkivet och returnera ``[(relpath, ZipInfo)]``.

    Sökvägarna normaliseras och valideras (zip-slip med flera avvisas).
    Om alla filer delar en gemensam rotkatalog strippas den, så att
    relsökvägarna motsvarar filerna som de landar på disk. Bevarade
    sökvägar hoppas över *efter* rottstrippningen – användardata inne i
    en rotkatalog (t.ex. ``MyApp-1.0/storage/…``) skrivs alltså aldrig
    över. Dubbletter och säkerhetsgränser kontrolleras sist. Kastar
    :class:`UnsafeArchiveError` innan något skrivits.
    """
    try:
        archive = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:
        raise UnsafeArchiveError(f"{Path(zip_path).name} är inte ett giltigt ZIP-arkiv.") from exc

    raw: list[tuple[str, zipfile.ZipInfo]] = []
    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            raw.append((normalize_relpath(info.filename), info))

    prefix = common_root_prefix([rel for rel, _ in raw])
    entries: list[tuple[str, zipfile.ZipInfo]] = []
    seen: set[str] = set()
    total_uncompressed = 0
    for rel, info in raw:
        if prefix and rel.startswith(prefix + "/"):
            rel = rel[len(prefix) + 1:]
        if is_preserved(rel, preserved):
            continue
        if rel in seen:
            raise UnsafeArchiveError(f"Dubblettpost i arkivet efter normalisering: {rel!r}")
        seen.add(rel)
        if len(entries) + 1 > max_members:
            raise UnsafeArchiveError(
                f"Arkivet innehåller fler än {max_members} filer; avbryter av säkerhetsskäl."
            )
        total_uncompressed += info.file_size
        if total_uncompressed > max_uncompressed:
            raise UnsafeArchiveError(
                "Arkivet är större än tillåtet i uppackad form; avbryter av säkerhetsskäl."
            )
        entries.append((rel, info))
    return entries


def hash_zip(
    zip_path: Path,
    preserved: Iterable[str] = (),
    *,
    max_members: int = MAX_MEMBERS,
    max_uncompressed: int = MAX_UNCOMPRESSED_BYTES,
) -> dict[str, str]:
    """Hasha alla filer i ett ZIP-arkiv utan att packa upp det.

    Sökvägarna normaliseras och valideras – se modulens dokumenation.
    En gemensam rotkatalog i arkivet strippas (samma regel som
    installationen använder), så att nycklarna motsvarar filerna
    på disk. Bevarade sökvägar hoppas över.
    """
    zip_path = Path(zip_path)
    entries = zip_entries(zip_path, preserved, max_members=max_members, max_uncompressed=max_uncompressed)
    result: dict[str, str] = {}
    with zipfile.ZipFile(zip_path) as archive:
        for rel, info in entries:
            with archive.open(info) as member:
                result[rel] = sha256_stream(member)
    return result
