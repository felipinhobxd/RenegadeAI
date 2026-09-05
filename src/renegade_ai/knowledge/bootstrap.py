from __future__ import annotations

from collections.abc import Callable

from renegade_ai.knowledge.dex import RenegadeDex


def ensure_renegade_dex(
    *,
    auto_sync: bool = True,
    reporter: Callable[[str], None] | None = print,
) -> RenegadeDex:
    """Load the local Renegade dex and build it automatically when missing.

    The first autonomous run should not fail just because ``knowledge-sync`` was
    not executed manually. A missing cache is recoverable, while a broken or
    incomplete cache still raises after one clean sync attempt.
    """
    try:
        return RenegadeDex()
    except FileNotFoundError:
        if not auto_sync:
            raise

    if reporter is not None:
        reporter("Renegade knowledge cache is missing; syncing it automatically...")

    from renegade_ai.knowledge.sync import sync_knowledge

    result = sync_knowledge()
    if reporter is not None:
        reporter(
            "Knowledge ready: "
            f"National Dex={result['national_dex_species']}/493, "
            f"records={result['pokemon_records']}, moves={result['moves']}"
        )
    return RenegadeDex()
