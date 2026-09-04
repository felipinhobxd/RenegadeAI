# Structured read-only memory backend (v0.6)

RenegadeAI can now combine its existing screenshots/OCR with validated structured state from melonDS' ARM9 GDB stub.

## Why this exists

Pure visual navigation has to rediscover where the player is after every camera change. Pokemon Platinum already keeps the current field location, progress and persistent world state in RAM, so v0.6 reads a small validated subset of that state and uses vision as a verifier/fallback.

The backend is intentionally **read-only**. `GDBRemoteClient` exposes `mADDR,LEN` memory reads and does not implement memory/register write operations. The client briefly pauses the emulated ARM9 while taking a consistent read and resumes it immediately afterwards.

## melonDS setup

Current melonDS exposes the ARM9 GDB port on 3333 and ARM7 on 3334. The GDB stub is not active while JIT is enabled in the configuration used by RenegadeAI, so the installer/configurator patches `melonDS.toml` to:

- enable GDB;
- set ARM9 port 3333 and ARM7 port 3334;
- disable break-on-startup;
- disable JIT;
- keep a `.renegadeai.bak` copy before the first edit.

A melonDS restart is required after changing these settings.

Normal autoplay performs this setup automatically when it can locate `melonDS.toml`. Diagnostic commands remain available:

```powershell
renegade-ai memory configure
renegade-ai memory status
renegade-ai memory location
renegade-ai memory story
renegade-ai memory objects
renegade-ai memory world
```

`memory story --all` prints every active persistent flag. The default `memory story` output keeps the list focused on likely campaign-progress flags.

## How the Platinum anchor is validated

The reader first checks the Nintendo DS game code at `0x02FFFE0C` and requires a Platinum-compatible `CPU?` code. It then selects the known Platinum SaveData pointer address for the ROM language.

That pointer is **not trusted blindly**. RenegadeAI parses Platinum's in-memory `SaveData.pageInfo` table and verifies:

1. Player page ID/size/location;
2. Party page ID/size/location;
3. Party capacity is exactly 6 and count is 0..6;
4. Field-player-state page ID/size/location;
5. map/warp/X/Z/facing values are structurally plausible.

Only after those checks does the reader expose structured state.

This layout is derived from `pret/pokeplatinum`'s `SaveData`, `PlayerSave`, `TrainerInfo`, `Party`, `FieldOverworldState`, `Location`, `VarsFlags` and `MapObjectSave` structures. The language-specific SaveData pointer table is cross-checked against the public Pokemon-Lua Platinum tooling.

## State currently exposed

```text
map_header_id
map_name
warp_id
x
z
face_direction
party_count
badge_mask
badge_count
money
main_story_cleared
has_national_dex
persistent story/script flags
persistent story/script vars
persisted current-map NPC/object hints
```

Map names are cached from the pinned `pret/pokeplatinum` generated map-header list. Flag/variable names are cached from the pinned generated vars/flags list. If either download is unavailable, the underlying numeric IDs can still be used.

## Story-state reader

`SAVE_TABLE_ENTRY_VARS_FLAGS` contains Platinum's persistent script variables followed by 2912 bits of flags. RenegadeAI reads that page directly and produces:

```text
story digest
active flag IDs
symbolic active flag names
non-zero persistent variables
```

This lets the campaign layer notice progress such as defeated trainers/bosses, unlocked doors/events, conversations and received key progression items without depending entirely on OCR.

ASI-Evolve gives only a **small deduplicated reward** to newly activated progress-like flags. A badge, boss victory or game completion remains vastly more valuable, preventing the AI from optimizing for arbitrary flag churn.

## Persisted field objects / NPC hints

`SAVE_TABLE_ENTRY_FIELD_OVERWORLD_STATE` stores 64 `MapObjectSave` records. RenegadeAI can read useful fields such as:

```text
local object ID
map ID
movement type
facing
trainer type
script ID
flag ID
X/Z coordinates
```

The structured navigator uses these records conservatively. If a movement attempt does not change exact coordinates and a known object occupies the target tile, it tries `A` immediately instead of treating that tile as an ordinary wall. This improves NPC/sign/event discovery.

These are **hints**, not absolute truth: moving objects can be newer than their persisted save snapshot between field-save operations. Vision/OCR still verifies the resulting screen before the agent continues.

## Structured navigation

`StructuredGridNavigator` stores an exact graph keyed by:

```text
(map_header_id, x, z)
```

For each coordinate it remembers attempted directions, successful edges and blocked directions. It deterministically explores the nearest known frontier instead of performing random movement. The graph persists in `data/structured_map.json`.

When structured RAM is not available, `CampaignAutopilot` automatically falls back to the existing visual-topology navigator instead of stopping the run.

## ASI-Evolve integration

New map discovery produces a small, deduplicated objective-progress reward. Selected persistent story flags can produce a much smaller progress reward. Badge changes are detected directly from `TrainerInfo.badgeMask` and rewarded when they occur. The official `isMainStoryCleared` flag is monitored as a structured completion signal instead of relying only on Hall-of-Fame OCR.

These signals remain bounded by the existing ASI-Evolve policy: deterministic game mechanics and validated state remain primary, while learned corrections are secondary.

## Next structured layers

The same architecture can later add read-only access to:

- live (not only persisted) field-object manager state;
- collision/behavior grid and warp metadata;
- inventory and full party/Pokemon data without OCR;
- current battle structs without OCR;
- a story objective graph derived from scripts/flags;
- objective-aware A* routing across maps and warps.

No ROM, BIOS, save file or extracted proprietary game asset is committed to this repository.
