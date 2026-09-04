# Architecture

RenegadeAI is split into replaceable layers so the project can start on normal melonDS today and later gain a faster memory/scripting backend.

## 1. Emulator adapter

`EmulatorAdapter` exposes only four primitives at first:

- locate emulator window;
- focus emulator;
- capture RGB pixels;
- press a Nintendo DS button.

`DesktopMelonDSAdapter` implements those primitives without modifying melonDS. A future memory adapter can expose richer state while keeping the rest of the agent unchanged.

## 2. Perception

Current perception only normalizes captured frames and separates the two DS screens. Planned detectors:

1. exact screen-bound calibration;
2. battle/menu/overworld scene classification;
3. HP bars and battle-menu state;
4. Pokemon/move/menu recognition;
5. overworld landmarks and collision-aware navigation.

The agent should prefer deterministic game-state reads where legally/technically available and fall back to visual perception when not available.

## 3. State + planning

The battle planner accepts structured state rather than raw pixels. This makes it independently testable and lets us improve perception without changing battle strategy code.

The first heuristic scores expected damage, KOs, priority, PP conservation, switching matchup, and survival. It is intentionally simple; later versions will add real Renegade Platinum data, speed order, status, weather, abilities, items, setup moves, hazards and multi-turn search.

## 4. Learning

Learning has two persistent pieces:

- SQLite transition/episode history (`ExperienceStore`);
- a small Q-table (`QTable`) used as a correction on top of safe battle heuristics.

The important design rule is that learned values complement Pokemon mechanics instead of forcing the agent to rediscover the entire type chart and damage system through millions of random inputs.

## 5. Planned training modes

### Run mode
One continuous playthrough. No state rewind for decision search.

### Training mode
Repeat controlled situations/save states, evaluate alternatives and retain policies that improve win rate, resource usage and consistency.

## Safety and repository hygiene

ROMs, save files, BIOS/firmware, emulator binaries and copyrighted extracted assets are intentionally ignored and must not be committed.
