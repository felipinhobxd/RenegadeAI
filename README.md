# RenegadeAI

Autonomous AI agent for **Pokemon Renegade Platinum** running in **melonDS**.

> The repository does not include the game ROM, BIOS/firmware, save files, emulator binaries, or a bundled extracted game-asset pack. Provide your own legally obtained copy and melonDS installation.

## Goal

The long-term target is an agent that can complete Renegade Platinum autonomously while observing the game, planning battles/routes, building strong teams and learning from previous attempts.

```text
melonDS
   |
   +--> EmulatorAdapter
           |
           +--> RGB frame --> viewport crop --> calibrated scene perception
           |                                      |
           +<-- DS buttons/touch <-- tactical planner
                                      |
                 OCR + exact scanned Pokemon state
                                      |
                      Renegade Dex + mechanics
                                      |
                       strategy + learning memory
```

The stock-melonDS backend works through the normal desktop window. Windows keyboard input uses native scan codes, and the lower DS screen can also be controlled by normalized touch/click coordinates.

## Current version: 0.3.0

### Foundation

- [x] melonDS desktop-window discovery and RGB capture
- [x] configurable DS input + native Windows scan-code backend
- [x] normalized lower-screen touch input
- [x] SQLite experience history + Q-learning correction layer
- [x] Windows GitHub Actions CI

### Real Renegade Platinum perception

Calibrated from real melonDS 1.1 Renegade Platinum captures.

- [x] automatically isolate the centered DS viewport
- [x] split top/bottom DS screens after cropping
- [x] recognize early overworld
- [x] recognize the battle command / `LUTAR` screen
- [x] distinguish the real battle move selector from Pokemon Summary -> Movimentos
- [x] recognize the Bag category screen
- [x] recognize the six-slot party screen
- [x] recognize Pokemon Summary -> Dados
- [x] recognize Pokemon Summary -> Movimentos
- [x] read exact player HP such as `14/20` when visible
- [x] estimate opponent HP from its bar
- [x] read battle status such as `PSN`
- [x] read current move PP

### National Dex strategy layer

- [x] sync Renegade-specific data for National Dex **1-493**
- [x] refuse an incomplete sync if any National Dex ID 1-493 is missing
- [x] parse Renegade typing, abilities, base stats and learnsets
- [x] generate a strategic profile for every synced Pokemon/form
- [x] generate role, physical/special orientation, Nature, EVs, held item and moves
- [x] score ability choice against the Pokemon's actual Renegade learnset
- [x] keep gendered species such as `Nidoran♀` and `Nidoran♂` distinct
- [x] optional local Platinum front/back sprite cache for future visual fallback

### Live battle intelligence

- [x] OCR player/opponent Pokemon and levels
- [x] OCR four battle move slots and PP
- [x] use exact scanned own stats from Pokemon Summary instead of only base-stat estimates
- [x] persist scanned party/profile state locally in `data/runtime_state.json`
- [x] approximate the Generation IV damage range instead of only ranking raw move power
- [x] account for STAB, typing, accuracy, PP and HP pressure
- [x] account for several important abilities/status interactions, including Iron Fist, Technician, Adaptability, Huge/Pure Power, Guts, Hustle, Levitate, Flash Fire, Water/Volt Absorb, No Guard, Wonder Guard, Tinted Lens, Thick Fat, Filter/Solid Rock and Blaze/Torrent/Overgrow/Swarm
- [x] account for some common held-item damage modifiers when the held item is known
- [x] fixed-damage handling for moves such as Dragon Rage, Sonic Boom, Night Shade, Seismic Toss and Super Fang
- [x] smart battle mode touches the selected move slot directly
- [x] safely pauses on Bag/party/summary screens instead of blindly pressing A
- [x] conservative emergency-switch scoring exists for a scanned multi-Pokemon party
- [ ] autonomous switch execution (needs post-selection submenu calibration)
- [ ] autonomous healing/status-item selection (needs actual item-list calibration)
- [ ] autonomous Pokeball selection/capture policy
- [ ] full trainer-team search / multi-turn lookahead
- [ ] overworld route navigation

The generated build is a **general target build**, not a rigid rule. The live battle planner can override it based on the Pokemon actually in your save, its real stats/ability/item/moves/PP, the opponent, current HP and battle risk.

## Install / update on Windows

Python 3.11+ is supported.

Fresh clone:

```powershell
git clone https://github.com/felipinhobxd/RenegadeAI.git
cd RenegadeAI
git checkout feat/agent-foundation
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,vision]"
Copy-Item config.example.toml config.toml
```

Existing clone:

```powershell
cd $HOME\Documents\RenegadeAI
git checkout feat/agent-foundation
git pull
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,vision]"
```

## 1. Build the local Renegade knowledge base

Run once after installing:

```powershell
renegade-ai knowledge-sync --sprites
```

This downloads the pinned Renegade Platinum data, parses every available Pokemon/form, verifies National Dex IDs 1-493, builds move data and generates strategy profiles. `--sprites` is optional and caches Platinum front/back sprites locally.

Generated knowledge, sprites and your scanned save-state metadata stay under `data/` and are ignored by Git.

## 2. Inspect any Pokemon's generated strategy

```powershell
renegade-ai strategy chimchar
renegade-ai strategy garchomp
renegade-ai strategy rotom-heat
```

The output includes role, offense style, preferred ability, Nature, EVs, target held item and ideal moves from the synced Renegade data.

## 3. Verify scene recognition

Open melonDS and stop on one of the known screens:

```powershell
renegade-ai observe
```

Expected scene names include:

```text
overworld
battle_command
move_menu
bag_menu
party_menu
summary_stats
summary_moves
unknown
```

`summary_moves` and `move_menu` are intentionally separate. This prevents the AI from accidentally selecting a Summary-page move as if it were currently fighting.

## 4. Scan the party

During a battle, open `POKEMON` so the six-slot party page is visible and run:

```powershell
renegade-ai party-scan
```

This records occupied slots, Pokemon names, exact visible HP and status.

Run it again after major party changes so the local state stays fresh.

## 5. Scan exact Pokemon data

Open a Pokemon's **Dados** page and run:

```powershell
renegade-ai summary-scan
```

It attempts to store:

```text
Pokemon
level
HP
status
ability
held item
Attack
Defense
Sp. Atk
Sp. Def
Speed
```

Then open the same Pokemon's **Movimentos** page and run the same command again:

```powershell
renegade-ai summary-scan
```

That stores the four moves and current/max PP.

Inspect everything remembered locally:

```powershell
renegade-ai state-show
```

For the first calibrated Chimchar example, the game showed values such as Lv.5, `14/20`, `PSN`, Iron Fist and Scratch/Leer/Ember. RenegadeAI is designed to read the actual values from each user's save instead of hard-coding those example values.

## 6. Identify the current battle

On a battle move-selection screen:

```powershell
renegade-ai identify
```

It reports the player/opponent match, levels, HP, status, moves, PP and OCR confidence. If OCR is uncertain, raw OCR text is exposed for debugging rather than silently inventing a Pokemon.

## 7. Ask for a battle plan without pressing anything

Keep `LUTAR` -> move selection visible:

```powershell
renegade-ai battle-plan
```

This ranks recognized moves using:

```text
actual scanned stats when known
+ level
+ move power/category
+ PP
+ STAB
+ type effectiveness
+ accuracy
+ damage-roll range
+ selected ability/status/item mechanics
+ current HP
```

This is the safest command to test first because it makes **no game input**.

## 8. Run smart battle mode

Only after `identify` and `battle-plan` look correct:

```powershell
renegade-ai battle-auto --smart --max-seconds 120
```

Current loop:

```text
capture
 -> classify screen
 -> enter LUTAR
 -> read Pokemon / HP / status / moves / PP
 -> merge exact cached Summary stats
 -> simulate and rank moves
 -> touch best move slot
 -> observe next state
```

If a Bag, party or Summary page appears unexpectedly, smart mode pauses safely instead of mashing buttons. Stop manually at any time with `Ctrl+C`.

## Useful diagnostics

Check everything:

```powershell
renegade-ai doctor
```

Test D-pad input:

```powershell
renegade-ai press up --seconds 0.30
renegade-ai press down --seconds 0.30
renegade-ai press left --seconds 0.30
renegade-ai press right --seconds 0.30
```

Capture cleaned screens:

```powershell
renegade-ai capture --split
```

Test a normalized lower-screen touch manually:

```powershell
renegade-ai touch 0.25 0.27
```

Initialize learning storage:

```powershell
renegade-ai db-init
```

## Next calibration captures needed

The main battle-command, Bag categories, party, Dados, Movimentos and damaged-HP states are now calibrated.

To enable safe autonomous **items, capture and switching**, the most useful next screenshots are:

1. inside `RESTAURAR PS/PP`, with its actual item list visible;
2. inside `POKEBOLAS`, with the Pokeball item list visible;
3. inside `ESTADO E MEDICAMENTOS`, with its item list visible;
4. after selecting a Pokemon from a party containing at least two usable Pokemon during battle, so the post-selection switch/menu flow is visible;
5. later, the ordinary Start menu and a few overworld/map screens for route navigation.

Do not commit ROMs, saves, BIOS/firmware or extracted copyrighted game assets.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/SOURCES.md`](docs/SOURCES.md).
