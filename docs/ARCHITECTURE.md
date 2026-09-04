# Architecture

RenegadeAI is split into replaceable layers so it can work with stock melonDS today and later gain a faster direct-memory/scripting backend without rewriting the planner.

## 1. Emulator adapter

`EmulatorAdapter` exposes the hardware-facing primitives:

- locate/focus emulator window;
- capture RGB pixels;
- press a Nintendo DS button;
- touch normalized coordinates on the lower DS screen.

`DesktopMelonDSAdapter` implements those primitives without modifying melonDS. Windows keyboard input uses scan-code `SendInput`; touch actions map normalized DS coordinates back into the automatically detected viewport and click the corresponding melonDS point.

## 2. Frame normalization and scene perception

The visual pipeline first removes melonDS chrome/black borders and finds the centered DS viewport. It then splits the upper and lower screens.

Cheap color/geometry scene classification currently recognizes:

- early-game overworld;
- battle command / `LUTAR`;
- move-selection menu.

This stage intentionally stays independent from OCR so it can run on every frame at low cost.

## 3. Battle vision

`BattleVision` is the richer on-demand perception layer. It uses optional RapidOCR on calibrated battle-HUD regions to read:

- player Pokemon name and level;
- opponent Pokemon name and level;
- up to four visible move names;
- approximate player/opponent HP-bar fill.

OCR text is fuzzy-matched against the local `RenegadeDex`; unknown or low-confidence observations remain unknown instead of being invented.

An optional local Generation IV Platinum sprite cache is available as a future fallback when HUD OCR is unreliable.

## 4. Renegade knowledge sync

`knowledge-sync` builds reproducible local knowledge from a pinned revision of the Renegade Platinum wiki. The sync parses the per-Pokemon Pokedex pages and writes structured local JSON containing:

- current Renegade types;
- abilities;
- base stats;
- Level-Up / TM-HM / Tutor / Egg learnsets;
- move type/category/power/accuracy/PP.

Before accepting the result it verifies that National Dex IDs 1 through 493 are all represented. Form records can exist in addition to those 493 base IDs.

The external revision and sprite source are documented in `docs/SOURCES.md`. Generated caches are ignored by Git.

## 5. Strategy-profile generation

A static strategy profile is generated for every synced species/form from its actual Renegade data. The generator estimates:

- battle role;
- physical/special/mixed orientation;
- preferred ability;
- nature;
- EV spread;
- held item;
- four ideal learnable moves.

This is a strong default build recommendation, not a hard-coded battle script. Progression constraints (whether a TM/item is currently obtainable) will be added to route planning.

## 6. Live battle planner

The smart move planner evaluates what the Pokemon actually knows right now. Its score includes:

- complete Fairy-era type effectiveness;
- STAB;
- move power;
- accuracy/reliability;
- physical vs special stat fit;
- approximate KO pressure;
- HP urgency;
- PP conservation;
- selected setup/recovery/status utility.

The best recognized move is selected by touching its lower-screen slot directly. This avoids relying on remembered cursor position.

The next planner expansion is action search across **move / Bag / switch / run**. The canonical Platinum battle-command touch geometry is already represented, but Bag and party contents require calibration before the AI is allowed to spend items or switch automatically.

## 7. Learning

Learning has two persistent pieces:

- SQLite episode/transition history (`ExperienceStore`);
- a Q-table (`QTable`) used as a learned correction on top of deterministic Pokemon mechanics.

The agent should not waste millions of actions rediscovering known mechanics. Type matchups, move data and Renegade changes are knowledge; learning focuses on strategy corrections, uncertain opponent behavior, resource value and repeated-route performance.

## 8. Planned training modes

### Run mode

One continuous playthrough. No rewind for decision search.

### Training mode

Repeat controlled situations/save states, compare alternatives and retain policies that improve win rate, resource use and consistency.

## 9. Remaining autonomy layers

1. Bag-category/item OCR and safe healing/capture policy.
2. Party OCR, switch confirmation and whole-party matchup scoring.
3. Trainer/wild battle classification and safe Run policy.
4. Status, weather, abilities, held items and multi-turn search.
5. Pokemon capture/value evaluation and team building.
6. Overworld landmark/collision perception and route planning.
7. Objective memory, grinding decisions, shops/TMs/evolution management.
8. Full-game completion policy and long-run learning.

## Safety and repository hygiene

ROMs, save files, BIOS/firmware, emulator binaries, generated knowledge caches and downloaded sprite caches are intentionally not committed.
