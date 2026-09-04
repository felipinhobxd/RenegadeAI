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
           +<-- DS buttons/touch <-- campaign + battle planners
                                      |
                 OCR + exact scanned Pokemon state
                                      |
                      Renegade Dex + mechanics
                                      |
                ASI-Evolve + campaign memory
```

The stock-melonDS backend works through the normal desktop window. Windows keyboard input uses native scan codes, and the lower DS screen can also be controlled by normalized touch/click coordinates.

## Current version: 0.5.0

### Zero-command autoplay after one-time setup

Version 0.5 adds an unattended campaign director and a Windows startup watcher. On Windows, after pulling this branch, double-click once:

```text
scripts\install_autoplay.cmd
```

The installer updates/creates `.venv`, installs the vision dependencies and starts a per-user background watcher. After that, the intended workflow is simply:

1. open melonDS;
2. load Renegade Platinum;
3. RenegadeAI detects the emulator and starts observing/playing automatically.

The first run also builds the local Renegade knowledge cache automatically if it is missing, so `knowledge-sync` is no longer required before autoplay.

The unattended director currently combines:

- automatic screenshot/calibration collection and semantic naming;
- OCR-based dialogue/milestone recognition;
- persistent visual topological exploration of the overworld;
- battle handoff to the mechanics-first smart battle planner;
- ASI-Evolve rewards and persistent learning;
- automatic reattachment when melonDS is restarted;
- Hall of Fame/game-completion detection when the completion screen is recognized.

Runtime log: `runs/autoplay.log`  
Automatic captures: `captures/auto-calibration/`  
Persistent visual exploration map: `data/campaign_map.json`

This is an **experimental full-campaign foundation**, not a claim that the current pixel-only navigator can already guarantee a complete Renegade Platinum playthrough. The next reliability step is a read-only melonDS RAM/map backend plus A* objective navigation; see `docs/AUTOPLAY_RESEARCH.md`.

### Foundation

- [x] melonDS desktop-window discovery and RGB capture
- [x] configurable DS input + native Windows scan-code backend
- [x] normalized lower-screen touch input
- [x] SQLite experience history + Q-learning correction layer
- [x] Windows GitHub Actions CI
- [x] background autoplay watcher for melonDS
- [x] automatic first-run knowledge bootstrap

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
- [x] automatically save new/unknown screens for future calibration
- [x] semantically name several milestones such as level-up/evolution/badge/game completion

### National Dex strategy layer

- [x] sync Renegade-specific data for National Dex **1-493**
- [x] automatically sync on first autonomous run if the cache is absent
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
- [x] advance stable battle narration without repeated-A spam
- [x] conservative emergency-switch scoring exists for a scanned multi-Pokemon party
- [ ] autonomous switch execution after full real-game calibration
- [ ] autonomous healing/status-item selection after full real-game calibration
- [ ] autonomous Pokeball selection/capture policy
- [ ] full trainer-team search / multi-turn lookahead

### Campaign autonomy

- [x] unattended campaign loop
- [x] persistent visual-state graph
- [x] deterministic frontier exploration rather than random movement
- [x] dialogue/event interaction without continuous A spam
- [x] automatic battle takeover and return to exploration
- [x] automatic safe calibration from battle menus
- [x] persistent ASI-Evolve campaign rewards
- [x] background reattachment when melonDS appears/restarts
- [ ] direct player map ID/X/Z/facing reader from melonDS RAM
- [ ] collision/warp/object map extraction
- [ ] A* overworld navigation
- [ ] structured story/objective planner
- [ ] reliable shops/TMs/evolution/resource planning
- [ ] measured end-to-end Hall-of-Fame completion rate

The generated build is a **general target build**, not a rigid rule. The live battle planner can override it based on the Pokemon actually in your save, its real stats/ability/item/moves/PP, the opponent, current HP and battle risk.

## Install / update on Windows

Python 3.11+ is supported.

### Recommended: unattended autoplay

For an existing clone, update the branch and then double-click:

```text
scripts\install_autoplay.cmd
```

No administrator permission is required. The script installs a launcher in your own Windows Startup folder. To remove it later without deleting learning/captures, run:

```text
scripts\uninstall_autoplay.ps1
```

### Manual developer setup

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

## Manual commands (optional diagnostics/development)

Autoplay does not require these commands after installation. They remain useful when debugging individual layers.

### Build the local Renegade knowledge base manually

Usually unnecessary now because autonomous mode bootstraps it automatically. To force a manual rebuild/cached sprites:

```powershell
renegade-ai knowledge-sync --sprites
```

### Inspect any Pokemon's generated strategy

```powershell
renegade-ai strategy chimchar
renegade-ai strategy garchomp
renegade-ai strategy rotom-heat
```

### Verify scene recognition

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

### Scan the party / exact Pokemon state

During a battle, open `POKEMON` so the six-slot party page is visible:

```powershell
renegade-ai party-scan
```

Open a Pokemon's **Dados** or **Movimentos** page:

```powershell
renegade-ai summary-scan
```

Inspect remembered state:

```powershell
renegade-ai state-show
```

### Identify or plan the current battle

```powershell
renegade-ai identify
renegade-ai battle-plan
```

`battle-plan` ranks recognized moves but makes no game input.

### Run only the battle autopilot

```powershell
renegade-ai battle-auto --smart --max-seconds 120
```

### Run ASI-Evolve battle mode manually

```powershell
renegade-ai evolve battle --max-seconds 180
renegade-ai evolve status
```

If the knowledge cache does not exist, it is now created automatically instead of raising the old `Renegade knowledge is not synced yet` error.

### Run the background watcher manually

Normally the startup installer handles this:

```powershell
renegade-ai-autoplay
```

### Useful diagnostics

```powershell
renegade-ai doctor
renegade-ai capture --split
renegade-ai db-init
```

## Automatic calibration

The agent can capture its own calibration data. Separate manual screenshot collection is no longer the primary workflow.

During unattended play it saves known and unknown states automatically. At battle-command screens it may safely explore reversible menus to capture missing Bag/party geometry without using an item, choosing a move, running away or confirming a switch.

Each capture can include full/viewport/top/bottom PNGs plus JSON metadata and a shared manifest under:

```text
captures/auto-calibration/
```

Unknown screens are OCR-analyzed and receive semantic labels when confidence is sufficient; otherwise they enter the calibration inbox as `needed_unknown_###`.

Do not commit ROMs, saves, BIOS/firmware or extracted copyrighted game assets.

See:

- `docs/ARCHITECTURE.md`
- `docs/ASI_EVOLVE.md`
- `docs/AUTO_CALIBRATION.md`
- `docs/AUTOPLAY_RESEARCH.md`
- `docs/SOURCES.md`
