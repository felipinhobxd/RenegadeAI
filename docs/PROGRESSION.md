# Objective-driven campaign progression (v0.7)

RenegadeAI no longer treats overworld exploration as the campaign objective when validated ARM9 state is available. The progression stack is hierarchical:

```text
read-only ARM9 state
  -> badge/story state
  -> main-story objective
  -> map/warp route
  -> real static Platinum collision grid
  -> local A* path
  -> DS movement
  -> dialogue / trainer / battle handoff
  -> re-read RAM and replan
```

## Real field geometry

The static world model is generated locally from a pinned public `pret/pokeplatinum` revision. Nothing from a ROM is committed to this repository.

It uses the documented Platinum land-data format:

- every loaded land block is 32x32 tiles;
- terrain attributes begin at byte `0x10`;
- there are 1024 little-endian `u16` terrain attributes (`0x800` bytes);
- bit 15 (`0x8000`) is the collision flag;
- the low byte contains the tile-behavior value.

Map-matrix JSON files map world matrix cells to both map headers and land-data block IDs. The matrix therefore gives the relationship between an ARM9 `(mapHeaderID, x, z)` location and the correct 32x32 collision block.

## Warps and map graph

Per-map event JSON files provide exact `warp_events` with source X/Z, destination map header and destination warp ID. Outdoor city/route boundaries are also derived from adjacent map-matrix cells. A boundary is considered a candidate portal only where both sides of the shared edge are statically non-colliding.

The global planner runs a map-level graph search first. It then chooses the next warp/boundary portal and runs local A* to that portal.

## A*

The local A* planner combines:

1. static terrain collision from Platinum;
2. live blocked directions learned from actual Renegade movement;
3. current persisted field-object/NPC tiles from read-only RAM;
4. unknown static tiles as higher-cost candidates rather than permanent walls.

Live game behavior has priority over vanilla static data. This is important because Renegade Platinum can alter scripts/objects and because dynamic NPCs are not static collision.

## Story objectives

`StoryObjectivePlanner` chooses a main-story target using badge count, symbolic story flags/variables and maps already reached. The current hierarchy covers the route from the opening/Sandgem sequence through:

- Sandgem / Pokedex setup;
- Jubilife and Oreburgh / Roark;
- Floaroma / Valley Windworks;
- Eterna / Gardenia / Galactic building;
- Hearthome / Fantina;
- Veilstone / Maylene;
- Pastoria / Crasher Wake;
- Celestic / Canalave / Byron;
- Snowpoint / Candice;
- Lake Acuity / Galactic HQ;
- Spear Pillar / Distortion World;
- Sunyshore / Volkner;
- Victory Road;
- Elite Four / Cynthia / Hall of Fame.

This is not a prerecorded button macro. The objective says *what* must be achieved; the live state, map graph, A*, dialogue handling and battle agent determine *how* to achieve it.

## Dialogues

Dialogues are checked independently of the lower-screen scene classifier. Platinum commonly renders dialogue on the top screen while the bottom still resembles the normal Poketch. The smart campaign runtime scans the top screen with OCR, presses `A` once, observes again, and only then decides whether another advance is appropriate.

A failed movement toward a planned target is treated as possible scripted interaction/NPC evidence before it becomes a navigation block.

## Recovery and automatic screenshots

If the objective route cannot make progress, the agent falls back to structured frontier exploration instead of freezing. Repeated failure creates an automatic `stuck_*` capture under `captures/auto-calibration/` with:

- map ID/name;
- exact X/Z/facing;
- attempted action;
- nearby field objects;
- OCR text;
- navigation graph statistics;
- current story objective;
- A* target/path reason.

That context is designed so a remaining Renegade-specific puzzle can be calibrated without asking the player to manually collect ordinary screenshots.

## Generated cache

The first structured autoplay run prepares public static world data under:

```text
data/world/
```

The cache is ignored by Git. Future launches reuse it. If public static data is unavailable, the agent keeps the existing read-only RAM + vision/frontier fallback rather than treating missing data as a valid path.

## Remaining limitations

The v0.7 planner is a major shift from random/frontier wandering to directed progression, but it is not yet a measured 100% completion guarantee. Complex one-off puzzles, movement modes (surf/bike/rock climb), menu choices, and Renegade-specific script changes still need live validation. The design intentionally replans from observed state instead of forcing a stale static route.
