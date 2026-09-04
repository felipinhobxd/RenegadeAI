from __future__ import annotations

import json
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

from renegade_ai.knowledge.models import MoveData, PokemonData, StrategyProfile

DEFAULT_KNOWLEDGE_DIR = Path("data/knowledge")


def normalize_name(value: str) -> str:
    # Preserve gender before stripping punctuation: otherwise Nidoran♀ and
    # Nidoran♂ both collapse to "nidoran" and one silently overwrites the other.
    value = value.replace("♀", " female ").replace("♂", " male ")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", value.lower())


class RenegadeDex:
    def __init__(self, root: str | Path = DEFAULT_KNOWLEDGE_DIR) -> None:
        root = Path(root)
        dex_path = root / "pokemon.json"
        moves_path = root / "moves.json"
        strategies_path = root / "strategies.json"
        if not dex_path.exists() or not moves_path.exists():
            raise FileNotFoundError(
                "Renegade knowledge is not synced yet. Run: renegade-ai knowledge-sync"
            )

        pokemon_raw = json.loads(dex_path.read_text(encoding="utf-8"))
        moves_raw = json.loads(moves_path.read_text(encoding="utf-8"))
        strategy_raw = (
            json.loads(strategies_path.read_text(encoding="utf-8"))
            if strategies_path.exists()
            else {}
        )

        self.pokemon: dict[str, PokemonData] = {
            slug: PokemonData.from_dict(value) for slug, value in pokemon_raw.items()
        }
        self.moves: dict[str, MoveData] = {
            slug: MoveData.from_dict(value) for slug, value in moves_raw.items()
        }
        self.strategies: dict[str, StrategyProfile] = {
            slug: StrategyProfile.from_dict(value) for slug, value in strategy_raw.items()
        }

        self._pokemon_aliases: dict[str, str] = {}
        for slug, pokemon in self.pokemon.items():
            aliases = {
                slug,
                pokemon.name,
                pokemon.name.replace("♀", " female"),
                pokemon.name.replace("♂", " male"),
            }
            for alias in aliases:
                self._pokemon_aliases[normalize_name(alias)] = slug

        self._move_aliases: dict[str, str] = {}
        for slug, move in self.moves.items():
            self._move_aliases[normalize_name(slug)] = slug
            self._move_aliases[normalize_name(move.name)] = slug

    def pokemon_by_name(self, value: str) -> PokemonData | None:
        key = normalize_name(value)
        slug = self._pokemon_aliases.get(key)
        return None if slug is None else self.pokemon.get(slug)

    def move_by_name(self, value: str) -> MoveData | None:
        key = normalize_name(value)
        slug = self._move_aliases.get(key)
        return None if slug is None else self.moves.get(slug)

    def strategy_for(self, value: str) -> StrategyProfile | None:
        pokemon = self.pokemon_by_name(value)
        if pokemon is None:
            return None
        return self.strategies.get(pokemon.slug)

    def fuzzy_pokemon(self, text: str, *, minimum: float = 0.62) -> tuple[PokemonData | None, float]:
        return self._fuzzy_lookup(text, self._pokemon_aliases, self.pokemon, minimum)

    def fuzzy_move(self, text: str, *, minimum: float = 0.58) -> tuple[MoveData | None, float]:
        return self._fuzzy_lookup(text, self._move_aliases, self.moves, minimum)

    @staticmethod
    def _fuzzy_lookup(text, aliases, records, minimum):
        needle = normalize_name(text)
        if not needle:
            return None, 0.0
        direct = aliases.get(needle)
        if direct is not None:
            return records[direct], 1.0

        best_slug: str | None = None
        best_score = 0.0
        for alias, slug in aliases.items():
            score = SequenceMatcher(None, needle, alias).ratio()
            if score > best_score:
                best_score = score
                best_slug = slug
        if best_slug is None or best_score < minimum:
            return None, best_score
        return records[best_slug], best_score

    def base_species_count(self) -> int:
        return len({pokemon.dex for pokemon in self.pokemon.values() if 1 <= pokemon.dex <= 493})
