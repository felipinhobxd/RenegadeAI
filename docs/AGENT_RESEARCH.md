# RenegadeAI autonomy research notes

This document records the design choices behind the autonomous campaign agent. The goal is not to copy one Pokémon bot; it is to combine the strongest ideas that transfer to Nintendo DS / Renegade Platinum while keeping the running save safe and the behavior explainable.

## Sources reviewed

### melonDS itself

- melonDS GDB stub implementation (`src/debug/GdbStub.cpp`, `src/debug/GdbCmds.cpp`, `src/ARM.cpp`): a newly accepted debugger connection enters the debugger loop and needs Continue/Step/Disconnect before normal execution resumes. Read-memory (`m`) packets can be serviced from the normal GDB polling path, so normal RenegadeAI state reads do not need a Ctrl-C halt around every request.
  - https://github.com/melonDS-emu/melonDS
- melonDS issue #2144: historical GDB TOML compatibility problem where some builds required `Enable = true`; the project now writes both `Enable` and `Enabled` during the one-time offline configuration step.
  - https://github.com/melonDS-emu/melonDS/issues/2144
- melonDS Lua scripting PR #1671: active/experimental scripting support with memory functions. This is promising as a future direct bridge, but it is not yet treated as a stable stock-melonDS dependency.
  - https://github.com/melonDS-emu/melonDS/pull/1671

### Pokémon autonomous-agent projects

- NousResearch `pokemon-agent`: uses structured RAM truth, ground-truth collision, objectives, telemetry and a stuck meter instead of asking vision to infer walkability.
  - https://github.com/NousResearch/pokemon-agent
- `pokemon-agent-os`: explicitly treats RAM as the source of truth, externalizes map knowledge and uses deterministic A* plus stuck memory/recovery.
  - https://github.com/nori00000/pokemon-agent-os
- PCC Labs Pokémon / Pokémon Kafka: structured game telemetry, explicit stuck/deadlock/no-progress detection, bounded recovery and measured parameter tuning rather than silently repeating the same behavior.
  - https://github.com/pcc-labs/pokemon
  - https://github.com/pcc-labs/pokemon-kafka
- `rappter-plays-pokemon`: bounded web research only after repeated no-progress and only while the map/coordinates still match. This supports the principle that external research should be a fallback to trusted local game state, not the controller itself.
  - https://github.com/kody-w/rappter-plays-pokemon

### Research papers

- *Playing Pokémon Red via Deep Reinforcement Learning* (2025, arXiv:2502.19920): Pokémon is a long-horizon, hard-exploration problem and reward shaping can be exploited. This argues against making one unconstrained scalar reward the sole controller.
  - https://arxiv.org/abs/2502.19920
- *PokeRL: Reinforcement Learning for Pokemon Red* (2026, arXiv:2604.10812): reports action loops, menu spam and unproductive wandering as practical failure modes; uses loop-aware wrappers, anti-loop/anti-spam mechanisms and hierarchical rewards.
  - https://arxiv.org/abs/2604.10812
- *PokéAI: A Goal-Generating, Battle-Optimizing Multi-agent System for Pokemon Red* (2025): separates planning, execution and critique, then verifies whether an objective actually succeeded before choosing the next goal. RenegadeAI uses the same closed-loop principle without requiring three LLM calls per step.
- *Strict Subgoal Execution: Reliable Long-Horizon Planning in Hierarchical Reinforcement Learning* (ICLR 2026): uses failure/partial-success experience to distinguish unreliable subgoals and refine graph edge costs. RenegadeAI's outcome memory applies the same high-level idea to map tiles, actions and story targets.
  - https://proceedings.iclr.cc/paper_files/paper/2026/hash/ec94195bca07a55e83968fbfa6efb8b0-Abstract-Conference.html

## Architecture chosen for RenegadeAI

### 1. Facts before guesses

Priority order:

```text
validated live RAM
> observed Renegade transitions/outcomes
> pinned Platinum static map/event data
> vision/OCR
> exploration fallback
```

Vision is excellent for identifying text, menu layout and visual state. It is a poor replacement for exact map coordinates or collision when those facts can be read safely.

### 2. Hierarchical controller instead of one giant policy

```text
story state
  -> choose objective
  -> choose target map / event / NPC
  -> choose map transition
  -> A* local route
  -> one DS action
  -> observe actual result
  -> critique result
  -> update memory / replan
```

The battle controller is separate because movement and Pokémon combat have different state/action spaces and different reliable mechanics.

### 3. Learn outcomes, not only rewards

Every structured overworld move can produce one of several useful facts:

- changed coordinate: the edge is traversable;
- same coordinate: blocked/no-effect evidence;
- changed map: observed Renegade portal;
- repeated recent states: loop evidence;
- story flag/objective/badge changed: real progression;
- story NPC/event attempted with no state change: objective-specific no-effect target.

These facts are persisted in `data/campaign_outcomes.json` and detailed events are written to `runs/campaign_telemetry.jsonl`.

### 4. Adaptive A* rather than random anti-stuck movement

Static collision remains the hard prior. Live failed movement can block a dynamic edge. Recent repeated tiles receive temporary cost so A* tries a different route. A story target that repeatedly produces no state change is deprioritized for that objective. Successful live Renegade warps override vanilla topology.

Random/frontier movement remains only a bounded fallback when the world model genuinely lacks enough information.

### 5. Closed-loop objective verification

Getting next to an NPC is not considered success. After the interaction/dialogue sequence, RenegadeAI checks whether at least one meaningful fact changed: story digest, objective, badge count or map. Repeated no-effect interactions are remembered so the planner does not keep talking to the same irrelevant NPC forever.

### 6. Small, bounded learning corrections

The deterministic world model and Pokémon mechanics remain primary. Learned signals change routing cost/target order and add small ASI-Evolve corrections. This deliberately avoids a common reward-shaping failure where an agent discovers a repeatable reward exploit that has nothing to do with completing the game.

## Remaining high-value work

The next reliability gains should come from live field-object manager state, richer dynamic-tile/interaction semantics, direct party/inventory/battle RAM structs, explicit puzzle solvers for moving-platform/strength/bike/surf edge cases, and repeatable end-to-end benchmark runs from multiple saves.

A future stable melonDS Lua/direct IPC bridge could replace GDB as the structured read transport. Until then, v0.8's non-stop read-only GDB connection is designed to fail open to vision/OCR rather than freeze a running game.
