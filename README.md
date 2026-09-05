# RenegadeAI

Autonomous AI agent for **Pokemon Renegade Platinum** running in **melonDS**.

> The repository does not include the game ROM, BIOS/firmware, save files, emulator binaries, or a bundled extracted game-asset pack. Provide your own legally obtained copy and melonDS installation.

## Goal

The long-term target is an agent that can complete Renegade Platinum autonomously while observing the game, planning battles/routes, building strong teams and learning from previous attempts.

```text
melonDS
   |
   +--> read-only ARM9 GDB state --------+
   |      map / X / Z / facing           |
   |      badges / story vars+flags      |
   |      persisted NPC/object hints     |
   |                                     v
   +--> RGB frame / OCR ----------> Story Objective Planner
                                      |
                         Platinum collision + warps
                                      |
                         live Renegade warp overlay
                                      |
                               local A* routing
                                      |
                         Battle AI + ASI-Evolve
                                      |
                         DS buttons / touchscreen
```

## Current version: 0.7.0

### Zero-command autoplay after one-time setup

On Windows, after pulling this branch, double-click once:

```text
scripts\install_autoplay.cmd
```

The installer creates/updates `.venv`, installs vision dependencies, configures melonDS for the read-only ARM9 GDB backend when possible, and installs a per-user background watcher. After any requested melonDS restart, the intended workflow is simply:

1. open melonDS;
2. load Renegade Platinum;
3. RenegadeAI detects the emulator and starts observing/playing automatically.

If the local Renegade knowledge cache does not exist, it is generated automatically.

Runtime log: `runs/autoplay.log`  
Automatic captures: `captures/auto-calibration/`  
Visual fallback map: `data/campaign_map.json`  
Structured coordinate map: `data/structured_map.json`  
Validated memory profile: `data/memory_profile.json`  
Static world cache: `data/world/`

## v0.7: objective-driven progression, collision/warps and A*

Version 0.7 changes the campaign from primarily frontier exploration to a hierarchical progression planner:

```text
story flags + badges + visited maps
              |
              v
       current story objective
              |
              v
      target map / NPC / event
              |
              v
 static Platinum map graph + live observed Renegade warps
              |
              v
       real collision grid
              |
              v
            A*
              |
              v
       exact DS movement
```

The world model now reads the actual `pret/pokeplatinum` field-data schema:

- authoritative map-header -> map-matrix and event-archive metadata;
- all 289 map matrices using their real `maps` land-data grid;
- 32x32 terrain attributes from `map_data_###.bin`;
- the real `0x8000` collision bit;
- static `WarpEvent` destinations and coordinates;
- matrix-boundary transitions between outdoor maps;
- scripted coordinate-event rectangles used by automatic story scenes.

Observed cross-map transitions from the user's running Renegade Platinum save are stored by the exact-coordinate navigator and are preferred over vanilla static warp data when available. This gives the planner a live correction layer if Renegade changes an event or transition.

The story objective planner covers the main campaign hierarchy from the opening/Pokedex sequence through Roark, Galactic/Windworks, Eterna, Hearthome, Veilstone, Pastoria, Celestic/Canalave, Snowpoint, Galactic HQ, Spear Pillar, Distortion World, Sunyshore, Victory Road and the Pokemon League/Hall of Fame. Flags and badge state are preferred over merely remembering that a map was visited.

When the intended map is reached, the planner tries known objective NPCs/objects first and can A* toward scripted coordinate events before falling back to local frontier exploration.

### Dialogue handling

Dialogue detection is active. The agent reads the **upper DS screen**, where Platinum normally renders conversations even when the lower Poketch still looks like ordinary overworld. v0.7 adds a cheap upper-screen dialogue-box cue so OCR can check for dialogue **before** sending another movement command. A dialogue is advanced one `A` press at a time with a new observation between presses.

If progression still stalls, automatic `stuck_...` captures include the screen, RAM map/X/Z/facing, attempted direction, nearby objects, OCR and current objective/A* state.

## v0.6: read-only structured melonDS state

Version 0.6 added a **read-only GDB Remote Protocol client** for melonDS ARM9. It implements memory reads but deliberately does not expose memory/register write operations.

Before trusting any address, RenegadeAI validates the Platinum-compatible game code, the language-specific SaveData pointer, SaveData page-table entries, and the party structure. If any validation fails, the campaign continues with screenshot/OCR navigation instead of guessing.

Structured state currently includes:

- exact `map_header_id` and symbolic map name;
- exact player `X/Z` and facing direction;
- party count;
- money, badge mask/count, National Dex and main-story-cleared state;
- persistent story/script variables and flags;
- persisted current-map NPC/object hints including coordinates, script/flag IDs and trainer type.

## Autonomous campaign stack

- [x] melonDS window discovery and RGB capture
- [x] native Windows DS keyboard input
- [x] normalized lower-screen touchscreen clicks
- [x] automatic DS viewport isolation
- [x] screenshot/OCR scene recognition and semantic auto-capture
- [x] read-only ARM9 GDB client
- [x] validated Platinum/Renegade SaveData anchor
- [x] exact map ID / X / Z / facing reader
- [x] persistent exact-coordinate exploration graph
- [x] persistent story vars/flags reader
- [x] persisted field-object/NPC hints
- [x] direct badge and main-story-completion signals
- [x] proactive upper-screen dialogue detection + one-step advancement
- [x] real Platinum terrain collision decoding
- [x] real static warp-event parsing
- [x] outdoor matrix-boundary graph
- [x] live observed Renegade warp overlay
- [x] local objective-aware A* routing
- [x] hierarchical main-story objective planner
- [x] scripted coordinate-event targeting on objective maps
- [x] vision/OCR fallback if structured state is unavailable
- [x] automatic battle takeover and return to campaign progression
- [x] bounded ASI-Evolve reward/learning memory
- [x] automatic stuck screenshots with objective/navigation context
- [x] automatic screenshot calibration inbox
- [x] automatic reattachment when melonDS closes/reopens
- [ ] live field-object manager state instead of only persisted object hints
- [ ] exact dynamic collision for every special puzzle/moving platform
- [ ] full inventory/party/battle structs directly from RAM
- [ ] objective-specific solutions for every puzzle/minigame edge case
- [ ] measured repeatable end-to-end Hall-of-Fame completion rate

The v0.7 planner is intended to make real campaign progress rather than wander randomly, but it is still an **experimental autonomous agent**. A full Hall-of-Fame run has not yet been measured end to end, so unsupported local puzzles/events can still fall back to exploration and automatic stuck capture.

## National Dex strategy layer

The knowledge layer is designed for National Dex **1-493**, not only the current starter.

- Renegade-specific typing, abilities, base stats and learnsets;
- completeness check for IDs 1-493;
- strategic role/orientation, Nature, EV, ability, item and move targets;
- gendered species such as `Nidoran♀` / `Nidoran♂` kept distinct;
- optional local Platinum sprite cache as a future visual fallback.

The generated build is a general target rather than a rigid battle rule. Live decisions can override it using actual HP, moves, PP, stats, matchup and learned outcomes.

## Live battle intelligence

The battle agent can combine OCR/scanned state with Renegade mechanics to rank moves using:

- Generation IV-style approximate damage ranges;
- STAB and type effectiveness;
- power, accuracy and PP;
- physical/special stats;
- current HP pressure;
- selected ability/status/item interactions;
- fixed-damage move handling;
- bounded learned matchup corrections.

ASI-Evolve rewards damage dealt, low damage received, KOs, avoiding faints, wins, captures, level-ups, evolutions, objective progress, bosses, badges and game completion. Deterministic Pokémon mechanics remain the primary signal; learned corrections stay bounded.

## Install / update on Windows

Python 3.11+ is supported.

### Recommended: unattended autoplay

Update the branch:

```powershell
cd $HOME\Documents\RenegadeAI
git checkout feat/agent-foundation
git pull
```

Then double-click:

```text
scripts\install_autoplay.cmd
```

No administrator permission is required. If the installer changes melonDS debugger/JIT settings, restart melonDS once.

To remove the startup watcher later without deleting learning/captures:

```powershell
.\scripts\uninstall_autoplay.ps1
```

### Manual developer setup

```powershell
git clone https://github.com/felipinhobxd/RenegadeAI.git
cd RenegadeAI
git checkout feat/agent-foundation
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,vision]"
Copy-Item config.example.toml config.toml
```

## Structured-memory diagnostics

Normal autoplay does not require these after installation, but they are useful to verify the new layer:

```powershell
renegade-ai memory configure
renegade-ai memory status
renegade-ai memory location
renegade-ai memory story
renegade-ai memory objects
renegade-ai memory world
```

For every active story flag:

```powershell
renegade-ai memory story --all
```

A working `memory location` result should contain a real map name/ID, exact X/Z and facing direction. `memory world` combines location, badges/progress, party count, story-state summary and current-map object hints.

## Other optional diagnostics

```powershell
renegade-ai doctor
renegade-ai observe
renegade-ai identify
renegade-ai battle-plan
renegade-ai evolve status
renegade-ai capture --split
renegade-ai state-show
```

Manual knowledge rebuild, usually unnecessary:

```powershell
renegade-ai knowledge-sync --sprites
```

Manual battle-only autonomy:

```powershell
renegade-ai battle-auto --smart --max-seconds 120
```

Manual full campaign watcher:

```powershell
renegade-ai-autoplay
```

## Automatic calibration

During unattended play RenegadeAI saves known/new screens automatically under:

```text
captures/auto-calibration/
```

Captures can include full window, cleaned DS viewport, top/bottom screen, JSON metadata and semantic names. Structured RAM annotations can add map/X/Z/facing and story-state context to those captures. If a screen cannot be safely identified it is kept as `needed_unknown_###` instead of inventing a label.

Do not commit ROMs, saves, BIOS/firmware or extracted copyrighted game assets.

See:

- `docs/ARCHITECTURE.md`
- `docs/ASI_EVOLVE.md`
- `docs/AUTO_CALIBRATION.md`
- `docs/AUTOPLAY_RESEARCH.md`
- `docs/STRUCTURED_MEMORY.md`
- `docs/SOURCES.md`
