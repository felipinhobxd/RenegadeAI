# RenegadeAI

Autonomous AI agent for **Pokemon Renegade Platinum** running in **melonDS**.

> The repository does not include the game ROM, copyrighted game assets, BIOS/firmware files, save files, or emulator binaries. Provide your own legally obtained copy and melonDS installation.

## Target

The long-term target is an agent that can complete Renegade Platinum autonomously while controlling the game, observing state, planning routes/battles, building strong teams and learning from previous attempts.

## Why the first backend uses the desktop window

Upstream native Lua scripting in melonDS is still experimental. RenegadeAI therefore starts with an emulator abstraction and a **stock melonDS desktop backend**: keyboard input + RGB capture. A direct memory/scripting backend can be added later without replacing the agent.

```text
melonDS
   |
   +--> EmulatorAdapter
           |
           +--> RGB frame --> perception --> structured state
           |                                  |
           +<-- DS buttons <-- planner <-------+
                                 |
                           learning + SQLite
```

## Milestone 0 - foundation

- [x] melonDS desktop-window discovery
- [x] RGB screenshot capture
- [x] configurable Nintendo DS keyboard mapping
- [x] normalized action model
- [x] approximate top/bottom DS screen split
- [x] persistent SQLite experience database
- [x] Q-learning correction layer
- [x] first battle heuristic/planner
- [x] CLI diagnostics and capture tools
- [x] unit tests + GitHub Actions
- [ ] calibrated Renegade Platinum battle detection
- [ ] automatic battle-menu control

## Install on Windows

Python 3.11+ is recommended.

```powershell
git clone https://github.com/felipinhobxd/RenegadeAI.git
cd RenegadeAI
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .[dev]
Copy-Item config.example.toml config.toml
```

Open melonDS and load Renegade Platinum. Then run:

```powershell
renegade-ai doctor
```

A successful check should report the melonDS window and the RGB capture size.

### Capture what the AI sees

```powershell
renegade-ai capture --split
```

This creates `captures/melonds.png`, plus approximate top/bottom screen captures. These images are the next calibration input for battle/menu perception.

### Test a DS button

First make `config.toml` match **melonDS > Config > Input and hotkeys > DS keypad**. Then:

```powershell
renegade-ai press a
renegade-ai press down
```

The example config contains common keyboard bindings, but they are deliberately configurable because melonDS lets the user remap every DS key.

### Initialize learning storage

```powershell
renegade-ai db-init
```

The generated learning data stays local and is ignored by Git.

## Next milestone

1. Calibrate the exact two DS screen rectangles from your melonDS layout.
2. Detect `overworld`, `dialog`, `battle`, and `menu` scenes.
3. Detect HP bars and the four-move battle menu.
4. Convert the selected battle decision into reliable menu button sequences.
5. Feed battle outcomes into SQLite + Q-values.
6. Add Renegade Platinum species/move/trainer knowledge and a proper damage simulator.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the design.
