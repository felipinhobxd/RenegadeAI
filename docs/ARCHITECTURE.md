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

Cheap color/geometry scene classification recognizes the currently calibrated overworld/battle/menu families. This stage intentionally stays independent from OCR so it can run on every frame at low cost.

Unknown screens are not discarded: the autonomous campaign/scout layer can capture them, OCR them and assign conservative semantic labels when enough text evidence exists.

## 3. Battle vision

`BattleVision` is the richer on-demand perception layer. It uses optional RapidOCR on calibrated battle-HUD regions to read:

- player Pokemon name and level;
- opponent Pokemon name and level;
- up to four visible move names;
- exact/approximate HP;
- status and PP where visible.

OCR text is fuzzy-matched against the local `RenegadeDex`; unknown or low-confidence observations remain unknown instead of being invented.

## 4. Renegade knowledge sync

`knowledge-sync` builds reproducible local knowledge from a pinned revision of the Renegade Platinum wiki. The sync parses the per-Pokemon Pokedex pages and writes structured local JSON containing:

- current Renegade types;
- abilities;
- base stats;
- Level-Up / TM-HM / Tutor / Egg learnsets;
- move type/category/power/accuracy/PP.

Before accepting the result it verifies that National Dex IDs 1 through 493 are all represented. Form records can exist in addition to those 493 base IDs.

Autonomous modes now call `ensure_renegade_dex()`: a clean first run automatically performs the sync instead of stopping with a `FileNotFoundError` and requiring a separate user command.

## 5. Strategy-profile generation

A static strategy profile is generated for every synced species/form from its actual Renegade data. The generator estimates:

- battle role;
- physical/special/mixed orientation;
- preferred ability;
- nature;
- EV spread;
- held item;
- four ideal learnable moves.

This is a strong default build recommendation, not a hard-coded battle script. Progression constraints are handled by higher campaign layers as they are added.

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
- selected setup/recovery/status utility;
- known ability/item interactions;
- bounded learned corrections from previous outcomes.

The best recognized move is selected by touching its lower-screen slot directly. This avoids relying on remembered cursor position.

Stable unknown battle-text frames are advanced one frame/state at a time rather than by blindly spamming A. If an unrecognized transition persists, battle control returns to the campaign director rather than hanging indefinitely.

## 7. ASI-Evolve learning

Learning has several persistent pieces:

- SQLite episode/transition history (`ExperienceStore`);
- tactical battle Q-values;
- an ASI-Evolve reward ledger/state;
- confidence-weighted learned corrections;
- campaign exploration memory.

Reward signals include damage dealt/taken, KO/faint/status results and larger campaign milestones such as capture, level-up, evolution, badges, boss progress and game completion.

The agent should not waste millions of actions rediscovering known mechanics. Type matchups, move data and Renegade changes are knowledge; learning focuses on strategy corrections, uncertain behavior, resource value, route performance and recovery.

## 8. Autonomous campaign director

`CampaignAutopilot` is the long-running orchestrator introduced in v0.5.

It continuously performs:

```text
capture game
 -> classify scene
 -> save/name novel calibration screen if useful
 -> OCR unknown text / detect milestones
 -> battle? hand off to BattleAutopilot
 -> safe non-battle menu? back out instead of guessing
 -> dialogue/event? advance conservatively
 -> overworld? choose a deterministic exploration action
 -> record transition + reward/memory
 -> repeat
```

At the first suitable battle-command screen it can run reversible calibration paths automatically, so screenshots for new Bag/party states do not require a separate user command.

`renegade-ai-autoplay` wraps the campaign director in a daemon that waits for melonDS. The Windows startup installer launches that daemon for the current user, making the normal post-install interaction simply opening melonDS and loading the game.

## 9. Visual topological navigation

`VisualTopoNavigator` is the current stock-melonDS fallback for overworld exploration.

It:

- fingerprints coarse top-screen visual states;
- records directional transitions;
- remembers blocked directions;
- explores previously untried directions first;
- runs BFS over known transitions to return to the nearest unexplored frontier;
- persists its graph in `data/campaign_map.json`.

It is deliberately deterministic rather than random. This gives the campaign agent a reusable exploration memory without requiring an emulator modification.

This layer is useful as a fallback/bootstrapping mechanism, but pure visual topology is not considered sufficient for a guaranteed full-game completion target.

## 10. Planned structured navigation backend

Research into successful Pokemon agents points strongly toward hybrid visual + structured-state navigation.

The intended next backend is read-only game-state extraction using melonDS debugging facilities plus the public `pret/pokeplatinum` decompilation/map data. The target state includes:

1. current map ID;
2. player X/Z position and facing;
3. collision/walkability;
4. warps/doors/transitions;
5. NPC/object positions;
6. badges/story/objective flags where they can be identified reliably;
7. A* routes between high-level objective waypoints.

The current screenshot/OCR system remains important as an independent verifier, UI sensor and fallback for states that are awkward to read structurally.

See `docs/AUTOPLAY_RESEARCH.md` for the public agent projects that informed this direction.

## 11. Campaign planning roadmap

After the structured navigation backend, the remaining high-value layers are:

1. progression/objective graph for Platinum/Renegade Platinum;
2. safe healing/capture/switch execution;
3. trainer/wild battle classification and Run policy;
4. team/capture/value optimization;
5. shops/TMs/evolution management;
6. grinding and resource decisions;
7. recovery from blackouts/navigation loops;
8. repeatable end-to-end Hall-of-Fame evaluation.

## Safety and repository hygiene

ROMs, save files, BIOS/firmware, emulator binaries, generated knowledge caches, screenshots and learned runtime state are intentionally not committed.
