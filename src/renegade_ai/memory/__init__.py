"""Read-only structured state backends for melonDS / Pokemon Platinum."""

from renegade_ai.memory.platinum import (
    GameIdentity,
    PlatinumMemoryReader,
    StructuredFieldObject,
    StructuredLocation,
    StructuredProgress,
    StructuredStoryState,
    StructuredWorldSnapshot,
    VarsFlagsCatalog,
)

__all__ = [
    "GameIdentity",
    "PlatinumMemoryReader",
    "StructuredFieldObject",
    "StructuredLocation",
    "StructuredProgress",
    "StructuredStoryState",
    "StructuredWorldSnapshot",
    "VarsFlagsCatalog",
]
