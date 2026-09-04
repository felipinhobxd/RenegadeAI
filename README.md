# RenegadeAI

Autonomous AI agent for **Pokemon Renegade Platinum** running in **melonDS**.

> The repository does not include the game ROM, copyrighted game assets, BIOS/firmware files, save files, or emulator binaries. Provide your own legally obtained copy and melonDS installation.

## Target

The long-term target is an agent that can complete Renegade Platinum autonomously while controlling the game, observing state, planning routes/battles, building strong teams and learning from previous attempts.

## Architecture

```text
melonDS
   |
   +--> EmulatorAdapter
           |
           +--> RGB frame --> auto viewport crop --> scene perception
           |                                      |
           +<-- DS buttons <-- battle/route agent <+
                                   |
                              learning + SQLite
```

The first backend targets stock melonDS through its desktop window. On Windows, RenegadeAI now uses native scan-code input for more reliable D-pad control. A future direct-memory/scripting backend can replace only the emulator adapter without rewriting the agent.

## Current progress

### Milestone 0 - foundation

- [x] melonDS desktop-window discovery
- [x] RGB screenshot capture
- [x] configurable Nintendo DS keyboard mapping
- [x] persistent SQLite experience database
- [x] Q-learning correction layer
- [x] first battle heuristic/planner
- [x] unit tests + GitHub Actions

### Milestone 1 - real Renegade Platinum perception

Calibrated from real melonDS 1.1 Renegade Platinum captures.

- [x] automatically find the centered DS viewport and remove black bars/window chrome
- [x] split top/bottom DS screens after cropping
- [x] recognize early-game overworld
- [x] recognize the red `LUTAR` battle command
- [x] recognize the move-selection screen
- [x] native Windows scan-code input for arrows
- [x] longer configurable D-pad hold time
- [x] first pixel-driven battle autopilot
- [ ] HP-bar measurement
- [ ] species/move recognition
- [ ] proper damage simulation connected to perception
- [ ] party/bag/start-menu perception
- [ ] overworld navigation

## Install / update on Windows

Python 3.11+ is recommended.

Fresh clone:

```powershell
git clone https://github.com/felipinhobxd/RenegadeAI.git
cd RenegadeAI
git checkout feat/agent-foundation
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item config.example.toml config.toml
```

If you already cloned the project:

```powershell
cd $HOME\Documents\RenegadeAI
git checkout feat/agent-foundation
git pull
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Open melonDS and load Renegade Platinum.

## Check everything

```powershell
renegade-ai doctor
```

The doctor now reports:

- melonDS window;
- RGB capture size;
- input backend;
- automatically detected DS viewport;
- currently recognized scene;
- perception metrics.

## Test the D-pad

First make `config.toml` match **melonDS > Config > Input and hotkeys > DS keypad**.

On Windows the default `input_backend = "auto"` selects the native scan-code backend.

Try a longer directional press:

```powershell
renegade-ai press up --seconds 0.30
renegade-ai press down --seconds 0.30
renegade-ai press left --seconds 0.30
renegade-ai press right --seconds 0.30
```

If these still do not move the character, the most likely cause is that melonDS is not mapped to the arrow keys. Change `[melonds.keys]` in `config.toml` to the exact keys shown by melonDS.

## See what the AI thinks is on screen

```powershell
renegade-ai observe
```

Expected states currently include:

```text
overworld
battle_command
move_menu
unknown
```

## Capture the cleaned DS screens

```powershell
renegade-ai capture --split
```

This now creates:

```text
captures/melonds.png
captures/melonds-viewport.png
captures/melonds-top.png
captures/melonds-bottom.png
```

The top/bottom images are cropped from the real DS viewport instead of simply cutting the whole Windows window in half.

## First automatic battle test

The first autopilot proves the complete loop:

```text
pixels -> recognize LUTAR -> press A -> recognize moves -> choose slot 1 -> repeat
```

Run it while already stopped at the red `LUTAR` screen:

```powershell
renegade-ai battle-auto --max-seconds 120
```

For the current starter battle this selects the first move slot (Scratch) repeatedly. This is intentionally conservative: the next stage will read HP/species/moves and use the real battle planner instead of a fixed move slot.

To stop it manually, use `Ctrl+C` in PowerShell.

## Learning storage

```powershell
renegade-ai db-init
```

Local experience data is kept out of Git.

## Next development targets

1. Read player/enemy HP bars from the battle HUD.
2. Recognize the current Pokemon and four moves.
3. Connect those observations to type effectiveness and the damage simulator.
4. Detect party, bag, start menu and Pokemon summary screens.
5. Add overworld navigation and objective planning.
6. Add team/build optimization and learned strategy memory.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the design.
