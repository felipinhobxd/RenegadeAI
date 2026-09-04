from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_RUNTIME_STATE = Path("data/runtime_state.json")


@dataclass(slots=True)
class RuntimeMove:
    slug: str
    name: str
    pp_current: int | None = None
    pp_max: int | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> RuntimeMove:
        return cls(
            slug=str(raw.get("slug", "")),
            name=str(raw.get("name", "")),
            pp_current=None if raw.get("pp_current") is None else int(raw["pp_current"]),
            pp_max=None if raw.get("pp_max") is None else int(raw["pp_max"]),
        )


@dataclass(slots=True)
class RuntimePokemon:
    slug: str
    name: str
    level: int | None = None
    hp_current: int | None = None
    hp_max: int | None = None
    status: str | None = None
    ability: str | None = None
    item: str | None = None
    attack: int | None = None
    defense: int | None = None
    special_attack: int | None = None
    special_defense: int | None = None
    speed: int | None = None
    moves: list[RuntimeMove] = field(default_factory=list)

    @property
    def hp_fraction(self) -> float | None:
        if self.hp_current is None or not self.hp_max:
            return None
        return max(0.0, min(1.0, self.hp_current / self.hp_max))

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> RuntimePokemon:
        integer_fields = {
            name: None if raw.get(name) is None else int(raw[name])
            for name in (
                "level",
                "hp_current",
                "hp_max",
                "attack",
                "defense",
                "special_attack",
                "special_defense",
                "speed",
            )
        }
        return cls(
            slug=str(raw.get("slug", "")),
            name=str(raw.get("name", "")),
            status=None if raw.get("status") is None else str(raw["status"]),
            ability=None if raw.get("ability") is None else str(raw["ability"]),
            item=None if raw.get("item") is None else str(raw["item"]),
            moves=[RuntimeMove.from_dict(item) for item in raw.get("moves", ())],
            **integer_fields,
        )


class RuntimeStateStore:
    """Small local memory for information the UI exposes outside battle.

    Summary pages reveal exact stats/ability/item that the battle HUD does not.
    Once scanned, those values are persisted locally and can improve damage
    planning in later battles. This file is intentionally ignored by Git.
    """

    def __init__(self, path: str | Path = DEFAULT_RUNTIME_STATE) -> None:
        self.path = Path(path)
        self.party_slots: list[str | None] = [None] * 6
        self.pokemon: dict[str, RuntimePokemon] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        slots = list(raw.get("party_slots", ()))[:6]
        self.party_slots = [None if value is None else str(value) for value in slots]
        self.party_slots.extend([None] * (6 - len(self.party_slots)))
        self.pokemon = {
            str(slug): RuntimePokemon.from_dict(value)
            for slug, value in raw.get("pokemon", {}).items()
        }

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "party_slots": self.party_slots,
            "pokemon": {slug: asdict(value) for slug, value in self.pokemon.items()},
        }
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def profile_for(self, slug: str) -> RuntimePokemon | None:
        return self.pokemon.get(slug)

    def upsert(self, slug: str, name: str, **fields: Any) -> RuntimePokemon:
        profile = self.pokemon.get(slug)
        if profile is None:
            profile = RuntimePokemon(slug=slug, name=name)
            self.pokemon[slug] = profile
        else:
            profile.name = name

        for key, value in fields.items():
            if value is not None and hasattr(profile, key):
                setattr(profile, key, value)
        return profile

    def set_party_slot(self, slot: int, slug: str | None) -> None:
        if not 0 <= slot < 6:
            raise ValueError("party slot must be between 0 and 5")
        self.party_slots[slot] = slug

    def party(self) -> list[RuntimePokemon]:
        result: list[RuntimePokemon] = []
        for slug in self.party_slots:
            if slug is not None and slug in self.pokemon:
                result.append(self.pokemon[slug])
        return result
