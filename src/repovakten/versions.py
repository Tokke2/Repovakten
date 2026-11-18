"""Tolkning och jämförelse av GitHubs versionstaggar (``v1.2.0`` o.s.v.).

Designbeslut:
* En inledande ``v``/``V`` framför siffror ignoreras (``v1.2.0`` == ``1.2.0``).
* Byggmetadata efter ``+`` ignoreras helt.
* Ett eventuellt suffix med bindestreck (``1.2.0-rc.1``) tolkas som
  pre-release och sorteras *före* motsvarande stabila version.
* Taggar som inte kan tolkas kraschar aldrig sorteringen – de sorteras
  under allt annat via :func:`try_version_key`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import VersionParseError

_NUMERIC_RE = re.compile(r"^\d+$")
_TRAILING_ALPHA_RE = re.compile(r"^(\d+)([A-Za-z][A-Za-z0-9.-]*)$")
_MIN_CORE_PARTS = 4  # jämför alltid (a, b, c, d, …) med minst fyra platser


@dataclass(frozen=True)
class ParsedVersion:
    raw: str
    numbers: tuple[int, ...]
    prerelease: tuple[int | str, ...]
    key: tuple


def _prerelease_id(part: str) -> int | str:
    if _NUMERIC_RE.match(part):
        # Numeriska identiteter jämförs numeriskt.
        return int(part)
    return part.lower()


def _prerelease_key(ids: tuple[int | str, ...]) -> tuple:
    # (0, n) < (1, "text"): numeriska före alfanumeriska, enligt semver-anda.
    return tuple((0, i) if isinstance(i, int) else (1, i) for i in ids)


def parse_version(tag: str) -> ParsedVersion:
    raw = tag
    text = tag.strip()
    text = re.sub(r"^[vV](?=\d)", "", text)
    text = text.split("+", 1)[0].strip()
    if not text:
        raise VersionParseError(f"Tom versionstagg: {raw!r}")

    core, dash, pre_part = text.partition("-")

    numbers: list[int] = []
    core_parts = core.split(".")
    for index, part in enumerate(core_parts):
        if _NUMERIC_RE.match(part):
            numbers.append(int(part))
            continue
        match = _TRAILING_ALPHA_RE.match(part)
        if match and index == len(core_parts) - 1:
            # T.ex. "1.2rc1" → 1.2, pre-release "rc1".
            numbers.append(int(match.group(1)))
            pre_part = match.group(2) + (("-" + pre_part) if pre_part else "")
            continue
        raise VersionParseError(f"Ogiltig versionstagg: {raw!r}")

    prerelease: tuple[int | str, ...] = ()
    if pre_part or dash:
        if not pre_part:
            raise VersionParseError(f"Tom pre-release i tagg: {raw!r}")
        pieces = re.split(r"[.-]", pre_part)
        ids: list[int | str] = []
        for piece in pieces:
            if not piece:
                raise VersionParseError(f"Ogiltigt pre-release-suffix i tagg: {raw!r}")
            ids.append(_prerelease_id(piece))
        prerelease = tuple(ids)

    padded = tuple(numbers) + (0,) * max(0, _MIN_CORE_PARTS - len(numbers))
    # 1 = stabil (utan pre-release) sorteras efter 0 = pre-release.
    release_marker = 1 if not prerelease else 0
    key = (padded, release_marker, _prerelease_key(prerelease))
    return ParsedVersion(raw=raw, numbers=tuple(numbers), prerelease=prerelease, key=key)


def version_key(tag: str) -> tuple:
    """Jämförbar nyckel för en tagg. Kastar :class:`VersionParseError`."""
    return parse_version(tag).key


def try_version_key(tag: str | None) -> tuple | None:
    """Som :func:`version_key` men returnerar ``None`` istället för att kasta."""
    if not tag:
        return None
    try:
        return version_key(tag)
    except VersionParseError:
        return None


# Nyckel som sorterar under alla tolkningsbara versioner.
_FALLBACK_KEY = ((-1, -1, -1, -1), 1, ())


def stable_sort_key(tag: str | None) -> tuple:
    """Nyckel som kan användas för blandade listor; otydbara taggar hamnar sist."""
    key = try_version_key(tag)
    return key if key is not None else _FALLBACK_KEY


def newest_tag(tags: list[str]) -> str | None:
    """Returnera den nyaste taggen, eller ``None`` för en tom lista."""
    if not tags:
        return None
    return max(tags, key=stable_sort_key)


def is_newer(candidate: str, current: str) -> bool:
    """Sant om ``candidate`` är en nyare version än ``current``."""
    return stable_sort_key(candidate) > stable_sort_key(current)
