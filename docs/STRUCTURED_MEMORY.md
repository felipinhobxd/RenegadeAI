# Structured read-only memory backend (v0.6)

RenegadeAI can now combine its existing screenshots/OCR with validated structured state from melonDS' ARM9 GDB stub.

## Why this exists

Pure visual navigation has to rediscover where the player is after every camera change. Pokemon Platinum already keeps the current field location in RAM, so v0.6 reads a very small, validated subset of that state and uses vision as a verifier/fallback.

The backend is intentionally **read-only**. `GDBRemoteClient` exposes `mADDR,LEN` memory reads and does not implement memory/register write operations.

## melonDS setup

Current melonDS exposes the ARM9 GDB port on 3333. The GDB stub is not active while JIT is enabled, so the RenegadeAI installer/configurator patches `melonDS.toml` to:

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
```

## How the Platinum anchor is validated

The reader first checks the Nintendo DS game code at `0x02FFFE0C` and requires a Platinum-compatible `CPU?` code. It then selects the known Platinum SaveData pointer address for the ROM language.

That pointer is **not trusted blindly**. RenegadeAI parses Platinum's in-memory `SaveData.pageInfo` table and verifies:

1. Player page ID/size/location;
2. Party page ID/size/location;
3. Party capacity is exactly 6 and count is 0..6;
4. Field-player-state page ID/size/location;
5. map/warp/X/Z/facing values are structurally plausible.

Only after those checks does the reader expose structured state.

This layout is derived from `pret/pokeplatinum`'s `SaveData`, `PlayerSave`, `Party`, `FieldOverworldState` and `Location` structures. The language-specific SaveData pointer table is cross-checked against the public Pokemon-Lua Platinum tooling.

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
```

Map names are cached from the pinned `pret/pokeplatinum` generated map-header list. If that download is unavailable, navigation still works with numeric map IDs.

## Structured navigation

`StructuredGridNavigator` stores an exact graph keyed by:

```text
(map_header_id, x, z)
```

For each coordinate it remembers attempted directions, successful edges and blocked directions. It deterministically explores the nearest known frontier instead of performing random movement. The graph persists in `data/structured_map.json`.

When structured RAM is not available, `CampaignAutopilot` automatically falls back to the existing visual-topology navigator instead of stopping the run.

## ASI-Evolve integration

New map discovery produces a small, deduplicated objective-progress reward. Badge changes are detected directly from `TrainerInfo.badgeMask` and rewarded when they occur. The official `isMainStoryCleared` flag is also monitored, giving the campaign a structured completion signal instead of relying only on Hall-of-Fame OCR.

These signals remain bounded by the existing ASI-Evolve policy: deterministic game mechanics and validated state remain primary, while learned corrections are secondary.

## Next structured layers

The same architecture can later add read-only access to:

- event/story vars and flags;
- field objects/NPC coordinates;
- map collision and warp metadata;
- inventory and party state without OCR;
- current battle state;
- objective-aware A* routing across known maps.

No ROM, BIOS, save file or extracted proprietary game asset is committed to this repository.
