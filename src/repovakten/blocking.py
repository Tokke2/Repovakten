"""Adminspärrar.

Reglerna nycklas på GitHubs repo-ID och lagras i tillståndsfilen. En spärr:

* blockerar installation, uppdatering och ominstallation, men
* påverkar **inte** en redan installerad kopia (den raderas aldrig), och
* följer med vid namnbyten och synkar eftersom ID:t är konstant.
"""
from __future__ import annotations

from .errors import InstallationBlockedError
from .models import BlockRule, utcnow_iso
from .store import Store


def block_app(store: Store, repo_id: int, *, reason: str = "") -> BlockRule:
    """Spärra installation/uppdatering av repot. Raderar eller rör aldrig filer."""
    rule = BlockRule(repo_id=int(repo_id), reason=reason.strip(), blocked_at=utcnow_iso())
    store.set_block(rule)
    return rule


def unblock_app(store: Store, repo_id: int) -> bool:
    """Tillåt igen. Returnerar True om en spärr fanns och togs bort."""
    return store.remove_block(int(repo_id))


def is_blocked(store: Store, repo_id: int) -> bool:
    return store.get_block(int(repo_id)) is not None


def blocked_repo_ids(store: Store) -> set[int]:
    return {rule.repo_id for rule in store.list_blocks()}


def list_blocked(store: Store) -> list[BlockRule]:
    return sorted(store.list_blocks(), key=lambda r: (r.blocked_at, r.repo_id))


def install_block_reason(store: Store, repo_id: int) -> str | None:
    """Orsaken till att installationen är spärrad, eller ``None`` om den är tillåten."""
    rule = store.get_block(int(repo_id))
    return rule.reason if rule else None


def assert_install_allowed(store: Store, repo_id: int) -> None:
    """Kastar :class:`InstallationBlockedError` om repot är spärrat.

    SKA anropas av installations- och uppdateringsflödet *precis innan*
    något skrivs – inte bara vid visning i gränssnittet – så att en spärr
    som lagts efter att en dialog öppnades ändå respekteras.
    """
    rule = store.get_block(int(repo_id))
    if rule is not None:
        raise InstallationBlockedError(int(repo_id), rule.reason)
