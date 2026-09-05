# Full-game autoplay research

RenegadeAI v0.5 moves from a battle-only agent toward an unattended campaign director.
This design was informed by several public Pokemon-agent projects rather than assuming that
pure pixel reinforcement learning alone will reliably solve a long JRPG.

## Strong reference systems

### Continual Harness / PokeAgent

- Repository: https://github.com/sethkarten/continual-harness
- Uses structured game state, ASCII maps, objectives, long-term memory, pathfinding and
  specialized sub-agents.
- Its repository reports full-game completions across multiple Pokemon RPGs.
- The Continual Harness variant can refine prompt, skills, sub-agents and memory during a
  continuous episode.

**Lesson for RenegadeAI:** long-horizon Pokemon autonomy benefits from a hierarchical split:
route/objective planning, navigation, battle tactics, memory and recovery should be separate
layers. Learning should improve those layers instead of replacing known game mechanics.

### NousResearch pokemon-agent

- Repository: https://github.com/NousResearch/pokemon-agent
- Reads structured emulator memory, exposes player/party/bag/badges/battle/dialog state,
  derives a collision map and supports A* navigation.
- Persists game sessions, objectives, milestones and agent memory.

**Lesson for RenegadeAI:** direct structured state is much more reliable for navigation and
story progression than trying to infer every coordinate and flag from screenshots.

### Claude Plays Pokemon starter/scaffolds

- Starter: https://github.com/davidhershey/ClaudePlaysPokemonStarter
- Extended scaffold example: https://github.com/cicero225/llm_pokemon_scaffold

These systems combine screenshots with emulator-memory state and a model that chooses actions.
More elaborate scaffolds add planning/critique/memory because a raw screenshot-to-button loop
loses track of long objectives easily.

### GeminiPlaysPokemonLive

- Repository: https://github.com/nichosta/GeminiPlaysPokemonLive
- Combines screenshots, RAM-derived state and emulator controls for FireRed/LeafGreen/Emerald.

**Lesson for RenegadeAI:** visual perception remains valuable, but RAM state is an excellent
second sensor for grounding what the agent thinks it sees.

### PokemonRedExperiments / deep RL

- Repository: https://github.com/PWhiddy/PokemonRedExperiments
- Paper: https://arxiv.org/abs/2502.19920
- Demonstrates useful reinforcement-learning techniques and coordinate-based exploration, but
  the published baseline only completes an early portion of Pokemon Red and discusses reward
  exploitation problems.

**Lesson for RenegadeAI:** rewards such as damage, survival, badges and objective progress are
useful, but a full-game agent still needs explicit hierarchical navigation/objective structure.

## Nintendo DS / Platinum-specific path

RenegadeAI currently controls stock melonDS through the desktop window. For a much stronger
full-game navigator, the next backend should combine:

1. melonDS GDB remote debugging support for safe read-only RAM inspection;
2. the `pret/pokeplatinum` decompilation for field/map structures and map metadata;
3. player map ID + X/Z/facing extraction;
4. collision, warp and object graphs;
5. A* navigation between map goals;
6. story/badge/objective flags where they can be identified reliably;
7. the existing screenshot/OCR system as an independent visual verifier and fallback.

Relevant upstream projects:

- melonDS: https://github.com/melonDS-emu/melonDS
- Pokemon Platinum decompilation: https://github.com/pret/pokeplatinum
- Platinum Lua tooling showing that useful live game data can be read from emulator memory:
  https://github.com/hzla/Pokemon-Lua

## What v0.5 does now

The current unattended baseline deliberately works without an API key or modified emulator:

- waits for melonDS automatically;
- auto-builds the Renegade knowledge cache on first use;
- automatically captures and names calibration screens;
- uses OCR to label campaign milestones;
- hands battles to the existing mechanics-first ASI-Evolve battle agent;
- advances stable text without blindly spamming A;
- builds a persistent visual topological exploration graph;
- returns to exploration after battles/menus;
- keeps screenshots, map memory and learned rewards across sessions.

This is an experimental full-campaign foundation, not a claim that pixel-only v0.5 already has
a guaranteed Hall-of-Fame completion rate. The direct-memory/map backend above is the main next
step for making long-route progression reliable enough to target complete autonomous runs.

## One-time Windows setup

Double-click:

```text
scripts\install_autoplay.cmd
```

The installer updates the virtual environment and places a per-user launcher in the Windows
Startup folder. After that, the intended workflow is simply:

1. open melonDS;
2. load Renegade Platinum;
3. RenegadeAI detects the emulator and begins the campaign automatically.

Runtime logs are written to `runs/autoplay.log`; automatic calibration captures are stored in
`captures/auto-calibration/`.
