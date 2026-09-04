# RenegadeAI

Autonomous AI agent for **Pokemon Renegade Platinum** running in **melonDS**.

> The repository does not include the game ROM, BIOS/firmware, save files, emulator binaries, or a bundled extracted game-asset pack. Provide your own legally obtained copy and melonDS installation.

## Target

The long-term target is an agent that can complete Renegade Platinum autonomously while observing the game, planning battles/routes, building strong teams and learning from previous attempts.

```text
melonDS
   |
   +--> EmulatorAdapter
           |
           +--> RGB frame --> viewport crop --> scene + battle vision
           |                                      |
           +<-- DS buttons/touch <-- smart planner+
                                      |
                          Renegade Dex + strategies
                                      |
                              learning + SQLite
```

The stock-melonDS backend works through the normal desktop window. Windows keyboard input uses native scan codes, and the lower DS screen can also be controlled by normalized touch/click coordinates.

## Current progress

### Milestone 0 - foundation

- [x] melonDS desktop-window discovery and RGB capture
- [x] configurable DS input + native Windows scan-code backend
- [x] SQLite experience history + Q-learning correction layer
- [x] unit tests and Windows GitHub Actions CI

### Milestone 1 - real game perception

Calibrated from real melonDS 1.1 Renegade Platinum captures.

- [x] automatically isolate the centered DS viewport
- [x] split top/bottom DS screens after cropping
- [x] recognize early-game overworld
- [x] recognize `LUTAR` battle command
- [x] recognize move-selection screen
- [x] direct normalized touch on the lower DS screen

### Milestone 2 - all-Pokemon battle intelligence

- [x] sync Renegade-specific data for National Dex **1-493**
- [x] validate all 493 National Dex IDs before accepting a sync
- [x] parse Renegade typing, abilities, base stats and learnsets
- [x] full Fairy-era type-effectiveness engine
- [x] generate a strategic profile for every synced species/form
- [x] generate role, offense style, nature, EVs, item, ability and ideal moves
- [x] OCR current player/opponent Pokemon and levels from battle HUD
- [x] OCR the four visible moves
- [x] estimate player/opponent HP bars
- [x] score moves by STAB, effectiveness, power, accuracy, physical/special fit, HP and PP pressure
- [x] smart battle mode chooses the best recognized move and touches its slot directly
- [x] optional local Platinum front/back sprite cache for future visual fallback
- [ ] calibrated Bag actions
- [ ] calibrated party/switch actions
- [ ] calibrated Run action
- [ ] battle status/weather/ability/item inference
- [ ] overworld route navigation

The generated build is a strong default profile, not a rigid command. The live battle planner is allowed to choose a different move or, later, a different Pokemon/item when the actual matchup makes that better.

## Install / update on Windows

Python 3.11+ is recommended.

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

## 1. Build the complete local Renegade knowledge base

Run once after installing, and again whenever RenegadeAI changes its pinned data revision:

```powershell
renegade-ai knowledge-sync --sprites
```

This downloads the pinned Renegade Platinum wiki data, parses every available Pokemon/form, verifies National Dex IDs 1-493, builds move data and generates strategy profiles. `--sprites` also caches the Generation IV Platinum front/back sprites locally for optional visual fallback.

Generated knowledge/sprites stay under `data/` and are ignored by Git.

## 2. Inspect any Pokemon's generated strategy

```powershell
renegade-ai strategy chimchar
renegade-ai strategy garchomp
renegade-ai strategy rotom-heat
```

The output includes role, physical/special orientation, preferred ability, nature, EVs, held item and four ideal moves based on the synced Renegade data.

## 3. Check melonDS and the current scene

Open melonDS and load Renegade Platinum, then:

```powershell
renegade-ai doctor
renegade-ai observe
```

The doctor reports the emulator window, input backend, capture size, automatically detected DS viewport and current scene.

## 4. Identify the live battle

Stop on a battle screen and run:

```powershell
renegade-ai identify
```

It attempts to report:

```text
Own: Chimchar level=5 hp=100%
Opponent: Piplup level=5 hp=100%
Move 1: Scratch
Move 2: Leer
Move 3: Ember
Move 4: unknown/empty
```

OCR confidence is printed as well. If recognition is uncertain, the command keeps the raw OCR text available for debugging instead of pretending it knows the answer.

## 5. Ask for a battle plan without pressing anything

Open `LUTAR` so the move-selection screen is visible:

```powershell
renegade-ai battle-plan
```

The planner ranks every recognized move and prints why it prefers one. For example, a STAB move can still lose to a neutral move when the opponent resists that type.

## 6. Run smart battle mode

Start from the battle command / `LUTAR` screen:

```powershell
renegade-ai battle-auto --smart --max-seconds 120
```

The loop is now:

```text
capture pixels
 -> recognize battle state
 -> enter LUTAR
 -> OCR Pokemon + moves
 -> read HP approximately
 -> calculate matchup scores
 -> choose best move slot
 -> touch the slot
 -> observe the next state
```

If OCR is uncertain, smart mode falls back conservatively instead of inventing a species/move. Stop at any time with `Ctrl+C`.

## Useful diagnostics

Test D-pad input:

```powershell
renegade-ai press up --seconds 0.30
renegade-ai press down --seconds 0.30
renegade-ai press left --seconds 0.30
renegade-ai press right --seconds 0.30
```

Capture the cleaned screens:

```powershell
renegade-ai capture --split
```

Directly test a normalized touch point on the lower screen:

```powershell
renegade-ai touch 0.25 0.27
```

Initialize learning storage:

```powershell
renegade-ai db-init
```

## Next calibration data needed

To make the planner use every battle command instead of only moves, the next real-game captures needed are:

1. full four-option battle command screen with `LUTAR`, `MOCHILA`, `POKEMON` and `FUGIR`;
2. Bag opened;
3. Pokemon party screen opened;
4. Pokemon Summary stats screen;
5. Pokemon Summary moves screen;
6. a battle where the player's HP is partially depleted;
7. a battle where the opponent's HP is partially depleted.

Those captures will calibrate healing/item selection, switching, fleeing and refine HP measurement. After that comes party matchup scoring, trainer planning, capture/team building and overworld navigation.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/SOURCES.md`](docs/SOURCES.md).
