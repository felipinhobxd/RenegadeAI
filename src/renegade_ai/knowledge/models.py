from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class MoveData:
    slug: str
    name: str
    type: str
    category: str
    power: int | None
    accuracy: int | None
    pp: int | None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> MoveData:
        return cls(
            slug=str(raw["slug"]),
            name=str(raw["name"]),
            type=str(raw["type"]),
            category=str(raw["category"]),
            power=None if raw.get("power") is None else int(raw["power"]),
            accuracy=None if raw.get("accuracy") is None else int(raw["accuracy"]),
            pp=None if raw.get("pp") is None else int(raw["pp"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class LearnMove:
    move: str
    method: str
    level: int | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> LearnMove:
        level = raw.get("level")
        return cls(
            move=str(raw["move"]),
            method=str(raw["method"]),
            level=None if level is None else int(level),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PokemonData:
    dex: int
    slug: str
    name: str
    types: tuple[str, ...]
    abilities: tuple[str, ...]
    hp: int
    attack: int
    defense: int
    special_attack: int
    special_defense: int
    speed: int
    learnset: tuple[LearnMove, ...] = ()
    source_url: str = ""

    @property
    def base_stat_total(self) -> int:
        return (
            self.hp
            + self.attack
            + self.defense
            + self.special_attack
            + self.special_defense
            + self.speed
        )

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> PokemonData:
        return cls(
            dex=int(raw["dex"]),
            slug=str(raw["slug"]),
            name=str(raw["name"]),
            types=tuple(str(value) for value in raw.get("types", ())),
            abilities=tuple(str(value) for value in raw.get("abilities", ())),
            hp=int(raw["hp"]),
            attack=int(raw["attack"]),
            defense=int(raw["defense"]),
            special_attack=int(raw["special_attack"]),
            special_defense=int(raw["special_defense"]),
            speed=int(raw["speed"]),
            learnset=tuple(LearnMove.from_dict(item) for item in raw.get("learnset", ())),
            source_url=str(raw.get("source_url", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        raw = asdict(self)
        raw["types"] = list(self.types)
        raw["abilities"] = list(self.abilities)
        raw["learnset"] = [entry.to_dict() for entry in self.learnset]
        return raw


@dataclass(frozen=True, slots=True)
class StrategyProfile:
    pokemon: str
    role: str
    offense: str
    nature: str
    evs: str
    item: str
    ability: str | None
    ideal_moves: tuple[str, ...]
    notes: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> StrategyProfile:
        return cls(
            pokemon=str(raw["pokemon"]),
            role=str(raw["role"]),
            offense=str(raw["offense"]),
            nature=str(raw["nature"]),
            evs=str(raw["evs"]),
            item=str(raw["item"]),
            ability=None if raw.get("ability") is None else str(raw["ability"]),
            ideal_moves=tuple(str(value) for value in raw.get("ideal_moves", ())),
            notes=tuple(str(value) for value in raw.get("notes", ())),
        )

    def to_dict(self) -> dict[str, Any]:
        raw = asdict(self)
        raw["ideal_moves"] = list(self.ideal_moves)
        raw["notes"] = list(self.notes)
        return raw
