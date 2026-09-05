# RenegadeAI

Autonomous AI agent for **Pokemon Renegade Platinum** running in **melonDS**.

> The repository does not include the game ROM, BIOS/firmware, save files, emulator binaries, or a bundled extracted game-asset pack. Provide your own legally obtained copy and melonDS installation.

## Goal

The long-term target is an agent that can complete Renegade Platinum autonomously while observing the game, planning battles/routes, building strong teams and learning from previous attempts.

```text
melonDS
   |
   +--> non-stop read-only ARM9 state -----+
   |      map / X / Z / facing             |
   |      badges / story vars+flags        |
   |      persisted NPC/object hints       |
   |                                       v
   +--> RGB frame / OCR ------------> Story Objective Planner
                                         |
                            Platinum collision + warps
                                         |
                            live Renegade warp overlay
                                         |
                          persistent outcome memory
                         /       |          |       \
                 blocked edge  loop    useless NPC  success
                         \       |          |       /
                              adaptive A*
                                         |
                           Battle AI + ASI-Evolve
                                         |
                           DS buttons / touchscreen
```

## Current version: 0.8.0

### Zero-command autoplay after one-time setup

On Windows, after pulling this branch, double-click once:

```text
scripts\install_autoplay.cmd
```

The installer creates/updates `.venv`, installs vision dependencies, configures melonDS for the read-only ARM9 backend when possible, and installs a per-user background watcher. Normal use is then simply:

1. open melonDS;
2. load Renegade Platinum;
3. RenegadeAI detects the emulator and starts observing/playing automatically.

Runtime log: `runs/autoplay.log`  
Detailed movement/learning telemetry: `runs/campaign_telemetry.jsonl`  
Learned campaign outcomes: `data/campaign_outcomes.json`  
Automatic captures: `captures/auto-calibration/`  
Visual fallback map: `data/campaign_map.json`  
Structured coordinate map: `data/structured_map.json`  
Static world cache: `data/world/`

## v0.8: attach to a running game without freezing + real no-progress learning

### Freeze-safe melonDS attachment

Previous versions halted ARM9 with a GDB Ctrl-C around every memory read. melonDS enters its debugger loop when a debugger connects and waits for a Continue/Step/Disconnect command, so attaching to a game already in progress could visibly freeze or stutter the emulator and a failed transaction could leave the session looking stuck.

v0.8 changes the transport:

- performs melonDS' connection handshake explicitly;
- immediately sends `continue` after attachment before doing capability discovery;
- normal memory reads use read-only `m` packets while the game keeps running;
- `Ctrl-C` is reserved for explicit diagnostic mode (`halt_reads = true`), not normal autoplay;
- transport failures use a best-effort fail-open `continue` before disconnecting and fall back to vision/OCR;
- the autoplay log exposes read counts and interrupt counts so normal play can verify `interrupts=0`;
- RenegadeAI never rewrites `melonDS.toml` while melonDS is already running. First-time configuration changes are deferred until the emulator is closed.

The one-time config writer also emits both `Enabled = true` and the older `Enable = true` compatibility key while keeping `BreakOnStartup = false` and the ARM9/ARM7 ports explicit.

Normal configuration:

```toml
[memory]
enabled = true
halt_reads = false
```

### Persistent outcome memory

The agent now learns from **what happened after an action**, not only from positive game milestones.

For each structured overworld decision it remembers the objective, exact `(map, x, z)`, chosen action and result. If a direction repeatedly leaves the player on the same tile, that state/action becomes a known no-progress result. If the agent revisits the same few tiles repeatedly, those tiles gain temporary A* cost. If a likely story NPC or coordinate event is attempted repeatedly without changing the story state, objective or badge count, that target is deprioritized for the current objective.

Useful outcomes are remembered too: successful movement, real Renegade map transitions, story changes and objective changes remain preferred evidence. Story/objective progress clears short-term loop pressure so a legitimate route is not permanently punished just because it was revisited earlier.

The learned layer is deliberately bounded and interpretable. It adjusts routing costs and target ordering; it does not rewrite its own source code or override deterministic collision, Pokémon mechanics or verified RAM facts.

### Loop and no-progress detection

Recent structured locations are tracked as a short state history. The runtime identifies escalating loop levels when the agent keeps returning to the same one, two or few positions. A detected loop can trigger replanning/stuck capture earlier than the old fixed blocked-move counter.

Examples of facts v0.8 can learn:

```text
objective=get_pokedex | map=Route201 | (x=33,z=18) | UP
3 attempts -> same coordinate
=> bad edge / replan instead of repeating UP

objective=return_home | target NPC=(7,4)
2 interactions -> no story flag, no badge, no map/objective change
=> suppress this NPC for this objective and try another target/event

recent path:
A -> B -> A -> B -> A -> B
=> loop pressure rises; adaptive A* makes recently revisited tiles more expensive
```

Outcome checkpoints are batched during ordinary walking to avoid unnecessary disk I/O, but failures, loops, target results and map/story transitions are persisted immediately.

## v0.7: objective-driven progression, collision/warps and A*

Version 0.7 changed the campaign from primarily frontier exploration to a hierarchical progression planner:

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

The world model reads the actual `pret/pokeplatinum` field-data schema: authoritative map-header metadata, all 289 map matrices, 32x32 terrain attributes from `map_data_###.bin`, the `0x8000` collision bit, static WarpEvents, outdoor matrix boundaries and coordinate-triggered story events.

Observed cross-map transitions from the user's running Renegade Platinum save are stored by the exact-coordinate navigator and preferred over vanilla static warp data when available. This gives the planner a live correction layer when Renegade differs from base Platinum.

The story objective planner covers the main campaign hierarchy from the opening/Pokedex sequence through Roark, Galactic/Windworks, Eterna, Hearthome, Veilstone, Pastoria, Celestic/Canalave, Snowpoint, Galactic HQ, Spear Pillar, Distortion World, Sunyshore, Victory Road and the Pokemon League/Hall of Fame. Flags and badge state are preferred over simply remembering that a map was visited.

### Dialogue handling

Dialogue detection is active. The agent reads the **upper DS screen**, where Platinum normally renders conversations even when the lower Poketch still resembles overworld. It checks for a dialogue-box cue before movement, confirms with OCR, presses `A` once, then observes again rather than blindly mashing through choices.

If progression stalls, automatic `stuck_...` captures include the screen, RAM map/X/Z/facing, attempted direction, nearby objects, OCR, loop level, learned outcome statistics and current objective/A* state.

## Structured state

Before trusting an address, RenegadeAI validates the Platinum-compatible game code, language-specific SaveData pointer, SaveData page-table entries and Party structure. If validation or transport fails, the campaign continues with screenshot/OCR navigation instead of guessing.

Structured state currently includes:

- exact `map_header_id`, map name, player `X/Z` and facing;
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
- [x] validated read-only ARM9 state
- [x] non-stop GDB reads for live attachment
- [x] fail-open resume on debugger transport errors
- [x] never rewrite melonDS config during a live game
- [x] exact map ID / X / Z / facing reader
- [x] persistent story vars/flags reader
- [x] persisted field-object/NPC hints
- [x] real Platinum terrain collision decoding
- [x] real static warp-event parsing
- [x] outdoor matrix-boundary graph
- [x] live observed Renegade warp overlay
- [x] hierarchical main-story objective planner
- [x] objective-aware adaptive A* routing
- [x] scripted coordinate-event targeting
- [x] proactive upper-screen dialogue detection
- [x] persistent state/action no-progress memory
- [x] short-loop/revisit detection
- [x] learned useless-NPC / useless-event suppression per objective
- [x] JSONL gameplay/learning telemetry
- [x] vision/OCR fallback if structured state is unavailable
- [x] automatic battle takeover and return to campaign progression
- [x] bounded ASI-Evolve reward/learning memory
- [x] automatic stuck screenshots with objective/navigation context
- [x] automatic reattachment when melonDS closes/reopens
- [ ] live field-object manager state instead of only persisted object hints
- [ ] exact dynamic collision for every special puzzle/moving platform
- [ ] full inventory/party/battle structs directly from RAM
- [ ] objective-specific solutions for every puzzle/minigame edge case
- [ ] measured repeatable end-to-end Hall-of-Fame completion rate

RenegadeAI is still an **experimental autonomous agent**. The project does not claim a measured 100% Hall-of-Fame completion rate yet. The important difference is that unresolved navigation now leaves persistent negative evidence and telemetry instead of simply repeating the same wandering behavior forever.

## National Dex strategy layer

The knowledge layer is designed for National Dex **1-493**, not only the current starter. It includes Renegade-specific typing, abilities, base stats and learnsets plus strategic role/orientation, Nature, EV, ability, item and move targets. Live decisions can override target builds using actual HP, moves, PP, stats, matchup and learned outcomes.

## Live battle intelligence

The battle agent combines OCR/scanned state with Renegade mechanics to rank moves using Generation IV-style approximate damage ranges, STAB/type effectiveness, power, accuracy, PP, physical/special stats, HP pressure and selected ability/status/item interactions.

ASI-Evolve rewards damage dealt, low damage received, KOs, avoiding faints, wins, captures, level-ups, evolutions, objective progress, bosses, badges and completion. v0.8 also feeds small bounded negative signals for exact overworld actions/targets that demonstrably produce no progress. Deterministic mechanics remain the primary signal.

## Install / update on Windows

Python 3.11+ is supported.

```powershell
cd $HOME\Documents\RenegadeAI
git checkout feat/agent-foundation
git pull
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,vision]"
```

Then run once after the update:

```text
scripts\install_autoplay.cmd
```

If melonDS is already running and its debugger was never configured, v0.8 deliberately **does not edit its config live**. The current session keeps the visual fallback; close melonDS, run/install once so the config can be patched safely, then reopen melonDS. If GDB was already configured, v0.8 can attach to the already-running game with non-stop reads.

## Diagnostics

Useful commands:

```powershell
renegade-ai doctor
renegade-ai memory configure
renegade-ai memory status
renegade-ai memory location
renegade-ai memory story
renegade-ai memory objects
renegade-ai memory world
renegade-ai observe
renegade-ai identify
renegade-ai battle-plan
renegade-ai evolve status
renegade-ai capture --split
renegade-ai state-show
```

Normal autoplay log should report something similar to:

```text
Structured ARM9 read-only mode active: ... transport=non-stop live reads, interrupts=0
Current story objective: ...
World planner ready: ... outcomes=...
Autonomous campaign started: navigation=... adaptive A* ... no-progress/loop learning ...
```

Do not commit ROMs, saves, BIOS/firmware or extracted copyrighted game assets.

See:

- `docs/ARCHITECTURE.md`
- `docs/ASI_EVOLVE.md`
- `docs/AUTO_CALIBRATION.md`
- `docs/AUTOPLAY_RESEARCH.md`
- `docs/STRUCTURED_MEMORY.md`
- `docs/AGENT_RESEARCH.md`
- `docs/SOURCES.md`
