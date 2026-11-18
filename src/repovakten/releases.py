"""Val av rätt release och rätt ZIP-paket.

* "Senaste stabila release" = senaste releasen som varken är utkast (draft)
  eller pre-release, sorterad på publiceringstid och därefter versionstagg.
* GitHubs automatiskt genererade "Source code (zip)" är aldrig en uppladdad
  tillgång – den listas alltså aldrig av API:et. Som skydd på djupet filtreras
  dessutom alla tillgångar vars namn börjar på "source code"/"sources" bort.
* Endast uppladdade ``.zip``-paket räknas som installationsbara i v1.
* :func:`rank_assets_for_platform` rangordnar flera paket för den aktuella
  datorn; användaren gör alltid det slutliga valet.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .models import Release, ReleaseAsset, parse_github_time
from .platforminfo import current_os, current_arch
from .versions import stable_sort_key

_SOURCE_CODE_RE = re.compile(r"^\s*(source[\s_-]*code|sources?)\b", re.IGNORECASE)


def is_source_code_asset(name: str) -> bool:
    return bool(_SOURCE_CODE_RE.match(name))


def zip_assets(release: Release) -> list[ReleaseAsset]:
    """Alla uppladdade ZIP-tillgångar (utan eventuella källkodsarkiv)."""
    return [a for a in release.assets if a.is_zip and not is_source_code_asset(a.name)]


def installable_assets(release: Release) -> list[ReleaseAsset]:
    """Tillgångar som v1 kan installera: uppladdade ZIP-paket."""
    return zip_assets(release)


def select_latest_stable(releases: list[Release]) -> Release | None:
    """Senaste stabila releasen, eller ``None`` om ingen finns."""
    stable = [r for r in releases if not r.draft and not r.prerelease]
    if not stable:
        return None

    def sort_key(rel: Release):
        published = parse_github_time(rel.published_at)
        published_ts = published.timestamp() if published else 0.0
        return (published_ts, stable_sort_key(rel.tag_name))

    return max(stable, key=sort_key)


def select_latest_any(releases: list[Release]) -> Release | None:
    """Senaste releasen oavsett typ (för visning). Utkast räknas inte."""
    published = [r for r in releases if not r.draft]
    if not published:
        return None
    return select_latest_stable(published) or max(
        published,
        key=lambda r: (
            (parse_github_time(r.published_at) or parse_github_time("1970-01-01")).timestamp(),
            stable_sort_key(r.tag_name),
        ),
    )


_OS_TOKENS: dict[str, tuple[str, ...]] = {
    "windows": ("windows", "win64", "win32", "win"),
    "macos": ("macos", "darwin", "osx", "mac", "universal"),
    "linux": ("linux", "glibc", "x11"),
}
_ARCH_TOKENS: dict[str, tuple[str, ...]] = {
    "x86_64": ("x86_64", "amd64", "x64", "win64"),
    "arm64": ("arm64", "aarch64"),
    "x86": ("i386", "i686", "win32", "x86"),
    "arm": ("armv7l", "armv7", "armhf"),
}


def _token_in(name: str, token: str) -> bool:
    pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])")
    return bool(pattern.search(name))


@dataclass(frozen=True)
class AssetSuggestion:
    """En rangordnad kandidat. ``score`` är sorteringsnyckel, ``reasons``
    förklarar poängen på svenska så att användaren kan fatta beslutet."""

    asset: ReleaseAsset
    score: int
    reasons: tuple[str, ...]

    @property
    def likely(self) -> bool:
        # Träff på både operativsystem och (för olikartade arkitekturer) arkitektur.
        return any(r.startswith("Passar ") for r in self.reasons) and self.score >= 6


def rank_assets_for_platform(
    assets: list[ReleaseAsset],
    os_name: str | None = None,
    arch: str | None = None,
) -> list[AssetSuggestion]:
    """Rangordna ZIP-tillgångar för den givna (eller aktuella) plattformen.

    Tillgångar som uppenbart är byggda för ett annat OS/arkitektur nedvärderas
    kraftigt men slängs inte – användaren väljer alltid själv i slutänden.
    """
    os_name = (os_name or current_os()).lower()
    arch = (arch or current_arch()).lower()
    wanted_os = _OS_TOKENS.get(os_name, ())
    wanted_arch = _ARCH_TOKENS.get(arch, ())

    other_os_tokens = [
        token
        for name, tokens in _OS_TOKENS.items()
        if name != os_name
        for token in tokens
    ]
    other_arch_tokens = [
        token
        for name, tokens in _ARCH_TOKENS.items()
        if name != arch
        for token in tokens
    ]

    suggestions: list[AssetSuggestion] = []
    for asset in assets:
        name = asset.name.lower()
        score = 0
        reasons: list[str] = []

        os_hits = [t for t in wanted_os if _token_in(name, t)]
        if os_hits:
            score += 4
            reasons.append(f"Passar {os_name} ({', '.join(sorted(set(os_hits)))})")
        elif any(_token_in(name, t) for t in other_os_tokens):
            score -= 10
            reasons.append("Verkar vara byggd för ett annat operativsystem")
        else:
            score += 1
            reasons.append("Ingen plattformsmarkering – kan vara generisk/portabel")

        arch_hits = [t for t in wanted_arch if _token_in(name, t)]
        if arch_hits:
            score += 3
            reasons.append(f"Passar arkitektur {arch} ({', '.join(sorted(set(arch_hits)))})")
        elif any(_token_in(name, t) for t in other_arch_tokens):
            score -= 6
            reasons.append("Verkar vara byggd för en annan processorarkitektur")
        else:
            reasons.append("Ingen arkitekturmarkering")

        if _token_in(name, "portable"):
            score += 2
            reasons.append("Markerad som portabel")

        suggestions.append(AssetSuggestion(asset=asset, score=score, reasons=tuple(reasons)))

    suggestions.sort(key=lambda s: (s.score, -s.asset.size), reverse=True)
    return suggestions


def describe_asset(asset: ReleaseAsset) -> str:
    size_kib = asset.size / 1024
    if size_kib >= 1024:
        size_text = f"{size_kib / 1024:.1f} MiB"
    else:
        size_text = f"{size_kib:.0f} KiB"
    return f"{asset.name} ({size_text})"


def install_root_default() -> Path:
    """Förval för var appar installeras (per-användare, inte systemet)."""
    return Path.home() / "Repovakten" / "apps"
